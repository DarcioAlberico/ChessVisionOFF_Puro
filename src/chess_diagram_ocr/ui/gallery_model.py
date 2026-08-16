"""O estado da galeria: onde estou, o que edito e o que isso grava (S-67).

Sem `import tkinter`, pela regra que organizou a Fase 6: o que dá para testar não mora na
janela. O que está aqui é justamente o que erra sem alarde -- navegar até o fim da lista,
trocar de diagrama com o campo pela metade, "aplicar a todos" -- e nada disso deveria exigir
abrir um Tk para ser verificado.

**A regra que atravessa o módulo: o campo em branco apaga a declaração.** Não é o mesmo que
declarar vazio. Um `[White]` em branco significa "não declarei, use o que o PDF disser", e
por isso a anotação some do JSON em vez de virar uma entrada com string vazia -- senão o
arquivo cresceria com uma linha por diagrama visitado, e "visitei" não é "anotei".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from chess_diagram_ocr.gallery import (
    RESERVED_HEADERS,
    DiagramAnnotation,
    GalleryAnnotations,
    lichess_analysis_url,
    save_annotations,
)
from chess_diagram_ocr.gallery_scan import GalleryEntry, GalleryIndex
from chess_diagram_ocr.games_cache import PositionCache
from chess_diagram_ocr.games_db import (
    DiagramMatch,
    PositionHit,
    agrees_with_caption,
    kept_headers,
    pair_from_caption,
    rank_candidates,
)
from chess_diagram_ocr.games_index import lookup_pair, positions_of
from chess_diagram_ocr.semantics import compose_fen

__all__ = ["FIELD_LABELS", "HEADER_FIELDS", "ApplyReport", "GalleryModel", "describe_origin"]

HEADER_FIELDS: tuple[str, ...] = (
    "White",
    "Black",
    "Event",
    "Site",
    "Date",
    "Round",
    "Result",
    "Annotator",
)
"""Os headers com campo fixo no frame lateral.

São os oito que um diagrama de livro costuma ter declarável. Qualquer outro header continua
possível pelo par livre da tela -- `DiagramAnnotation.headers` é um dicionário, não um
conjunto fechado.
"""


@dataclass
class ApplyReport:
    """O que uma busca na base fez com as anotações do livro (S-72/S-74).

    Quatro números, e não um, porque eles respondem perguntas diferentes: `confirmed` diz
    quantas leituras a base deu por certas -- que é o que esvazia a fila de revisão --, e
    `touched`/`fields` dizem quanto trabalho de digitação ela poupou. Um casamento ambíguo
    conta no primeiro e não nos outros.
    """

    confirmed: int = 0
    ambiguous: int = 0
    touched: int = 0
    fields: int = 0
    recovered: int = 0
    """Campos que a base já havia escrito e cuja procedência foi recuperada (ver
    `_recover_provenance`). Separado de `fields` porque não é trabalho novo: é conserto."""

    respected: int = 0
    """Diagramas em que uma escolha humana já existia e foi **preservada** (S-86).

    Conta separado porque não é nem trabalho poupado nem trabalho feito: é trabalho *não
    desfeito*. Um número alto aqui numa varredura é sinal de que ela está passando por cima de
    um livro já revisado à mão -- e é bom que ele apareça no relatório."""

    by_caption: int = 0
    """Diagramas cuja partida foi escolhida pela legenda, e não pela data (S-91).

    Separado de `touched` porque mede outra coisa: `touched` é trabalho poupado, este é
    **precisão**. Um preenchimento que a legenda confirma tem duas fontes independentes de
    acordo; um que a data escolheu tem uma fonte e um critério de desempate."""


FIELD_LABELS = {"move_number": "lance", "side_to_move": "vez"}
"""Como cada campo da S-72 aparece na linha de procedência. Header vira o nome dele."""

RULE_LABELS = {
    "unique": "partida única na base",
    "caption": "confirmada pela legenda",
    "date": "a mais antiga entre várias",
    "human": "escolhida por você",
}
"""Como cada regra da S-91 aparece na tela. `date` é o único que o texto trata como ressalva --
e é o que ele é: 72,3% de discordância com a legenda onde há legenda para conferir."""


def _provenance_after(previous: DiagramAnnotation, remaining: tuple[str, ...]) -> dict[str, Any]:
    """O que sobra da procedência quando campos deixam de ser da base (S-94).

    **`filled_from` e `filled_rule` andam em par**: um diz *de que* partida veio o
    preenchimento, o outro *por que* foi ela. Sem nenhum campo preenchido sobrando, os dois
    descrevem coisa nenhuma -- e deixar a regra para trás faz o censo da S-89 contar como
    "preenchido pelo desempate por data" um diagrama que não tem nada preenchido.

    Existe como função porque a mesma conta aparece em quatro lugares -- editar um campo,
    apagar um header, desfazer a cópia e limpar tudo --, e quatro cópias dela divergiriam na
    primeira vez que uma fosse corrigida.
    """
    return {
        "filled_fields": remaining,
        "filled_from": previous.filled_from if remaining else "",
        "filled_rule": previous.filled_rule if remaining else "",
    }


_AUSENTE = object()


def _apenas_o_que_mudou(previous: DiagramAnnotation, fields: dict[str, Any]) -> dict[str, Any]:
    """Dos campos pedidos, os que de fato diferem do que já está gravado (S-109).

    **Existe porque gesto de leitura não é edição.** O `<FocusOut>` de um `Entry` dispara ao
    sair do campo, tenha-se digitado nele ou não -- e percorrer os oito headers com `Tab`, que
    é o gesto de *conferir* o que a base preencheu, chamava `set_header` oito vezes com o
    mesmo valor. Cada chamada tirava o campo de `filled_fields`, e o diagrama saía da
    procedência `database` para `manual` sem que ninguém tivesse corrigido nada. Eram 4.906
    anotações com header preenchido pela base expostas a isso, e o efeito no censo da S-89 é o
    contrário do que ele existe para medir: a coluna "a revisar" **subia** com o trabalho de
    revisar.

    A guarda mora aqui, e não só no painel, porque é aqui que ela pode ser testada sem abrir
    janela -- e porque `edit` tem quatro chamadores, não um.
    """
    return {nome: valor for nome, valor in fields.items() if getattr(previous, nome, _AUSENTE) != valor}


def _evidence(match: DiagramMatch) -> str:
    """O que vai para o `confirmed_from`: a partida quando ela é única, a contagem quando não."""
    return match.game_label if match.games_matched == 1 else f"{match.games_matched} partidas da base"


def _candidate_key(match: DiagramMatch) -> str:
    """A chave da partida que este casamento propõe, na forma que `chosen_game` guarda."""
    return match.candidates[0].key if match.candidates else ""


def _fill_rule(match: DiagramMatch) -> str:
    """Por que **esta** partida, e não outra (S-91).

    A ordem das perguntas é a ordem da força da evidência: partida única não teve escolha,
    legenda é uma segunda fonte independente, e o resto é o desempate por data -- que precisa
    ficar marcado como tal justamente por ser o fraco.
    """
    if match.games_matched == 1:
        return "unique"
    if match.caption_confirmed:
        return "caption"
    return "date"


def _recover_provenance(annotation: DiagramAnnotation, match: DiagramMatch) -> tuple[str, ...]:
    """Campos que a base escreveu antes de existir `filled_fields`, e que ela reconhece.

    **Isto é reparo, e a inferência está declarada.** Uma anotação com `filled_from` e sem
    `filled_fields` só pode ter sido gravada pela versão do `apply_matches` anterior à correção
    de procedência -- e, sem este reparo, o PGN sairia dizendo `[SideToMoveSource "manual"]`
    para 1.409 diagramas que ninguém conferiu, que é exatamente o defeito que a correção
    existe para eliminar.

    O crivo é estreito de propósito: só campos **iguais** ao que este casamento diz. Se a
    pessoa mudou o valor depois, ele não bate e continua sendo dela. O erro que sobra é
    atribuir à base um valor que alguém digitou por acaso idêntico -- num diagrama que a base
    já preencheu.
    """
    if not annotation.filled_from or annotation.filled_fields:
        return ()
    recuperados = []
    if annotation.move_number == match.move_number:
        recuperados.append("move_number")
    if annotation.side_to_move == match.side_to_move:
        recuperados.append("side_to_move")
    recuperados += [
        f"header:{nome}"
        for nome, valor in sorted(match.headers.items())
        if valor and annotation.headers.get(nome) == valor
    ]
    return tuple(recuperados)


def describe_origin(annotation: DiagramAnnotation) -> str:
    """A linha verde da aba: **o que** veio da base, e de que partida.

    Dizer só "da base" seria insuficiente depois que a pessoa começa a corrigir: numa anotação
    onde a base deu o lance e a mão deu a vez, "da base" atribuiria as duas coisas a ela.
    """
    if not annotation.filled_from or not annotation.filled_fields:
        return ""
    campos = [
        FIELD_LABELS.get(campo, campo.removeprefix("header:")) for campo in annotation.filled_fields
    ]
    # A regra vai na mesma linha porque ela muda o que a linha significa: "a mais antiga entre
    # várias" é um palpite, e uma tela que o mostre igual a "partida única" mente por omissão.
    regra = RULE_LABELS.get(annotation.filled_rule, "")
    sufixo = f" — {regra}" if regra else ""
    return f"da base ({', '.join(campos)}): {annotation.filled_from}{sufixo}"


@dataclass
class GalleryModel:
    """O índice varrido, a posição atual e as anotações -- os três juntos e sem widget."""

    index: GalleryIndex = field(default_factory=GalleryIndex)
    annotations: GalleryAnnotations = field(default_factory=GalleryAnnotations)
    pdf_path: Path | None = None
    position: int = 0

    position_cache: PositionCache | None = None
    """O que a base respondeu, por posição (S-84). `None` é "ninguém varreu ainda".

    Injetado e não carregado aqui pela mesma razão do `gallery_dir`: quem decide de onde ler é
    quem monta o painel, e um modelo que abrisse `data/games_positions.json` sozinho não teria
    como ser testado sem o arquivo de verdade."""

    database_paths: tuple[Path, ...] = ()
    index_path: Path | None = None
    """As bases e o índice por nome (S-87), para a busca sob demanda. Vazio desliga o caminho.

    **Plural desde a S-93**: a pasta pode ter mais de uma gigabase, e a que ficava de fora era
    justamente onde estava a partida procurada. O índice é um só e sabe de que arquivo é cada
    offset.

    Injetados como o `position_cache`: um modelo que fosse abrir a base sozinho não teria como
    ser testado sem um PGN de 10,3 GB por perto."""

    gallery_dir: Path | None = None
    """Onde gravar. `None` usa `data/gallery/`.

    Existe para ser injetável, e não por configuração: `save_annotations` recebe o diretório
    por argumento padrão, que é resolvido na definição -- sem este campo, testar a gravação
    exigiria remendar um global, e o teste que tentou isso gravou no `data/` de verdade."""

    # ------------------------------------------------------------------------ navegação

    def __len__(self) -> int:
        return len(self.index)

    @property
    def is_empty(self) -> bool:
        return len(self.index) == 0

    @property
    def current(self) -> GalleryEntry | None:
        """O diagrama selecionado, ou `None` quando o livro não foi varrido."""
        if self.is_empty:
            return None
        return self.index.entries[self.clamped_position()]

    def clamped_position(self) -> int:
        """A posição corrigida para dentro da lista. Nunca levanta."""
        if self.is_empty:
            return 0
        return max(0, min(self.position, len(self.index) - 1))

    def go_to(self, position: int) -> bool:
        """Vai para uma posição. Devolve se mudou -- quem chama redesenha só quando mudou."""
        if self.is_empty:
            return False
        alvo = max(0, min(int(position), len(self.index) - 1))
        if alvo == self.clamped_position():
            self.position = alvo
            return False
        self.position = alvo
        return True

    def step(self, delta: int) -> bool:
        """Anterior/próximo. **Não circula**: chegar ao fim da lista é informação.

        Circular faria o último diagrama do livro parecer o primeiro, e numa galeria de
        centenas ninguém percebe a volta -- percebe que "o livro tem menos do que eu pensava".
        """
        return self.go_to(self.clamped_position() + int(delta))

    def sync_to_page(self, page_index: int) -> bool:
        """Segue o visualizador de PDF: mostra o diagrama daquela página, se houver.

        Página sem diagrama **não move a galeria**. Virar para uma página de texto e ver o
        diagrama saltar para outro lugar seria pior que não seguir: a pessoa perderia o que
        estava anotando por ter rolado o PDF.
        """
        posicao = self.index.position_of(int(page_index))
        return self.go_to(posicao) if posicao is not None else False

    @property
    def page_index(self) -> int | None:
        """A página do diagrama atual, para o visualizador de PDF seguir a galeria."""
        atual = self.current
        return None if atual is None else atual.page_index

    # ------------------------------------------------------------------------ anotação

    @property
    def current_annotation(self) -> DiagramAnnotation:
        atual = self.current
        return DiagramAnnotation() if atual is None else self.annotations.get(*atual.key)

    def edit(self, **campos: object) -> DiagramAnnotation | None:
        """Muda campos da anotação do diagrama atual. `None` se não há diagrama.

        **Editar à mão tira o campo da procedência da base** (S-72). O `filled_fields` é o que
        faz o PGN dizer `[SideToMoveSource "database"]` em vez de `"manual"`; deixá-lo intacto
        depois de a pessoa corrigir a vez faria o header atribuir à base uma resposta que ela
        não deu -- e o header existe justamente para não haver esse tipo de dúvida.
        """
        atual = self.current
        if atual is None:
            return None
        anterior = self.annotations.get(atual.page_index, atual.diagram_index)

        campos = _apenas_o_que_mudou(anterior, campos)
        if not campos:
            return anterior

        if anterior.filled_fields and "filled_fields" not in campos:
            restantes = tuple(nome for nome in anterior.filled_fields if nome not in campos)
            if restantes != anterior.filled_fields:
                # Sem campo nenhum da base sobrando, a evidência não descreve mais nada.
                campos = {**campos, **_provenance_after(anterior, restantes)}
        return self.annotations.update(atual.page_index, atual.diagram_index, **campos)

    def set_header(self, name: str, value: str) -> DiagramAnnotation | None:
        """Grava um header. Valor em branco **remove** a declaração -- ver o docstring."""
        atual = self.current
        if atual is None:
            return None
        nome = name.strip()
        if not nome or nome in RESERVED_HEADERS:
            return self.current_annotation

        anotacao = self.current_annotation
        headers = dict(anotacao.headers)
        texto = value.strip()
        if texto:
            headers[nome] = texto
        else:
            headers.pop(nome, None)

        # S-109: sair do campo sem digitar nada não é editar. A guarda precisa estar aqui, e
        # não só no `edit`, porque a linha seguinte já calcula a procedência nova -- e é ela,
        # e não o header, que `edit` veria como mudança.
        if headers == anotacao.headers:
            return anotacao

        # Editar *este* header o tira da procedência da base, e deixa os outros como estavam --
        # a base pode ter preenchido `Event` e a pessoa corrigir só o `White`.
        restantes = tuple(campo for campo in anotacao.filled_fields if campo != f"header:{nome}")
        if restantes != anotacao.filled_fields:
            return self.edit(headers=headers, **_provenance_after(anotacao, restantes))
        return self.edit(headers=headers)

    def clear_headers(self) -> tuple[str, ...]:
        """Apaga **todos** os headers deste diagrama. Devolve os nomes que saíram (S-94).

        **É o mesmo gesto que apagar campo a campo, feito de uma vez** -- inclusive na
        procedência, que segue a regra do `set_header`: header removido deixa de ter origem, e
        sem nenhum campo da base sobrando o `filled_from` não descreve mais nada. Não há
        semântica nova aqui, e é de propósito: um botão que limpasse "de outro jeito" criaria
        dois estados possíveis para a mesma tela.

        **Existe porque a base pode preencher com a partida errada.** Uma posição em 47
        partidas identifica a partida pela legenda ou pela data, e a data discorda da legenda
        72,3% das vezes (S-91); quando ela erra, são oito campos para limpar um a um, saindo de
        cada `Entry` para que o `<FocusOut>` grave. Ninguém faz isso oito vezes -- deixa errado.

        **O lance, a vez e a partida escolhida ficam.** Os headers são o que a base escreve
        sobre *qual* partida é; o lance e a vez a pessoa costuma ter contado no livro, e apagar
        trabalho humano que ninguém pediu para apagar é o defeito da S-76. Quem quiser trocar a
        partida inteira usa a lista de candidatas, que reescreve tudo junto.

        Os livres saem também: `headers` é um dicionário, e "todos" quer dizer todos.
        """
        atual = self.current
        anotacao = self.current_annotation
        if atual is None or not anotacao.headers:
            return ()
        apagados = tuple(sorted(anotacao.headers))
        restantes = tuple(campo for campo in anotacao.filled_fields if not campo.startswith("header:"))
        self.edit(headers={}, **_provenance_after(anotacao, restantes))
        return apagados

    def headers_to_apply(self, names: tuple[str, ...] = HEADER_FIELDS) -> dict[str, str]:
        """O que um "aplicar a todos" copiaria daqui. Existe para a tela poder **mostrar**.

        A ação é a mais destrutiva da aba -- ela sobrescreve o mesmo campo em centenas de
        diagramas --, e até aqui o usuário só descobria o que tinha feito depois de feito. Uma
        pergunta que não diz quais valores vão para quantos diagramas não é uma confirmação, é
        um obstáculo.
        """
        return {
            nome: valor
            for nome, valor in self.current_annotation.headers.items()
            if nome in names and valor
        }

    def revert_headers(self, values: Mapping[str, str]) -> int:
        """Remove de **todo** diagrama os headers cujo valor é exatamente este. Devolve quantos.

        É o desfazer do "aplicar a todos", e o critério é o valor e não a chave: apagar todo
        `Event` do livro tiraria junto o que a base preencheu certo e o que a pessoa digitou
        diagrama a diagrama. Apagar só onde `Event == "Amsterdam"` desfaz exatamente o que
        aquele gesto espalhou.

        O que ele não recupera é o que a cópia **sobrescreveu**: `apply_headers_to_all` grava
        por cima, e o valor anterior não existe mais em lugar nenhum. É por isso que a
        confirmação da tela vale mais que este desfazer.
        """
        alvos = {nome: valor for nome, valor in values.items() if valor}
        if not alvos:
            return 0
        atingidos = 0
        for chave, anotacao in list(self.annotations.entries.items()):
            headers = {
                nome: valor
                for nome, valor in anotacao.headers.items()
                if alvos.get(nome) != valor
            }
            if headers != anotacao.headers:
                # Um header removido também deixa de ter procedência: se a base o escreveu, o
                # que sobra depois de apagá-lo não é dela.
                restantes = tuple(
                    campo
                    for campo in anotacao.filled_fields
                    if not (campo.startswith("header:") and campo.removeprefix("header:") not in headers)
                )
                self.annotations.set(
                    *chave, replace(anotacao, headers=headers, **_provenance_after(anotacao, restantes))
                )
                atingidos += 1
        return atingidos

    def apply_headers_to_all(self, names: tuple[str, ...] = HEADER_FIELDS) -> int:
        """Copia os headers declarados neste diagrama para todos os outros. Devolve quantos.

        Só os **declarados**: um campo em branco aqui não apaga o que outro diagrama tem.
        Aplicar a todos é para preencher `Event` e `Site` de um livro inteiro de uma vez, e
        transformar isso num apagador em massa seria um jeito caro de perder trabalho.

        **O que ele faz com campo já preenchido é sobrescrever**, e foi assim que um clique
        espalhou "Ljubojevic / Browne / Amsterdam / 1972" por 1.405 diagramas de um livro. Quem
        chama tem de perguntar antes -- ver `headers_to_apply` e `revert_headers`.
        """
        origem = {
            nome: valor
            for nome, valor in self.current_annotation.headers.items()
            if nome in names and valor
        }
        if not origem or self.is_empty:
            return 0

        atingidos = 0
        for entrada in self.index.entries:
            if entrada.key == (self.current.key if self.current else None):
                continue
            anterior = self.annotations.get(*entrada.key)
            headers = {**anterior.headers, **origem}
            if headers != anterior.headers:
                self.annotations.set(entrada.page_index, entrada.diagram_index, replace(anterior, headers=headers))
                atingidos += 1
        return atingidos

    def apply_matches(self, matches: Sequence[DiagramMatch], *, max_games: int = 5) -> ApplyReport:
        """Preenche com o que a base disse, **só onde está vazio** (S-72), e confirma (S-74).

        **Confirmar não é preencher.** Uma posição que aparece em 300 partidas não diz qual
        delas é, então não preenche header nenhum -- mas ela responde a pergunta que a fila de
        revisão faz: aquelas 64 casas aconteceram num tabuleiro de verdade, logo a leitura está
        certa. Por isso todo casamento grava `confirmed_from`, e só o não-ambíguo preenche.

        **Nunca sobrescreve.** É a regra que a S-17 estabeleceu para o lado a jogar e que vale
        aqui inteira: a base é uma fonte a mais, não a autoridade. Se você digitou `Event` e a
        base discorda, quem está com o livro na mão é você -- e uma ferramenta que apaga o que
        a pessoa escreveu deixa de ser usada, com razão.

        **Posição comum não preenche nada.** Acima de `max_games` partidas contendo a mesma
        colocação, o casamento deixou de identificar *qual* partida: um final de rei e peão
        aparece em centenas, com número de lance diferente em cada uma. Preencher dali seria
        inventar procedência -- e procedência inventada é pior que campo vazio, porque o campo
        vazio ninguém confunde com dado conferido.
        """
        relatorio = ApplyReport()
        for casamento in matches:
            anterior = self.annotations.get(*casamento.key)
            relatorio.confirmed += 1

            if anterior.chosen_game and anterior.chosen_game != _candidate_key(casamento):
                # Uma pessoa já escolheu outra partida aqui (S-86). Confirmar a leitura ainda
                # vale -- as 64 casas bateram --, mas trocar a procedência por baixo dela seria
                # desfazer trabalho humano com um palpite, que é o defeito que a S-77 consertou.
                relatorio.respected += 1
                if anterior.confirmed_from != _evidence(casamento):
                    self.annotations.update(*casamento.key, confirmed_from=_evidence(casamento))
                continue

            evidencia = _evidence(casamento)
            mudancas: dict[str, Any] = {}
            if anterior.confirmed_from != evidencia:
                mudancas["confirmed_from"] = evidencia

            if casamento.games_matched > max_games and not casamento.caption_confirmed:
                # Confirma e para: a posição é real, mas não se sabe de qual partida ela veio.
                relatorio.ambiguous += 1
                if mudancas:
                    self.annotations.update(*casamento.key, **mudancas)
                continue

            if anterior.move_number is None:
                mudancas["move_number"] = casamento.move_number
            if anterior.side_to_move is None:
                mudancas["side_to_move"] = casamento.side_to_move
            novos = {
                nome: valor
                for nome, valor in casamento.headers.items()
                if valor and not anterior.headers.get(nome) and nome not in RESERVED_HEADERS
            }
            recuperados = _recover_provenance(anterior, casamento)
            if novos:
                mudancas["headers"] = {**anterior.headers, **novos}

            preenchidos: tuple[str, ...] = tuple(
                chave for chave in ("move_number", "side_to_move") if chave in mudancas
            )
            preenchidos += tuple(f"header:{nome}" for nome in sorted(novos))
            relatorio.fields += len(preenchidos)
            relatorio.recovered += len(recuperados)
            preenchidos += recuperados
            if not preenchidos:
                if mudancas:
                    self.annotations.update(*casamento.key, **mudancas)
                continue

            relatorio.touched += 1
            if casamento.caption_confirmed:
                relatorio.by_caption += 1
            self.annotations.update(
                *casamento.key,
                filled_from=casamento.game_label,
                filled_rule=_fill_rule(casamento),
                # A união com o que já havia: rodar a busca duas vezes, ou rodar a por nome
                # depois da por posição, não pode apagar a procedência da primeira.
                filled_fields=tuple(dict.fromkeys((*anterior.filled_fields, *preenchidos))),
                **mudancas,
            )
        return relatorio

    # ------------------------------------------------- a escolha da partida (S-86)

    def candidates_for(self, entry: GalleryEntry | None) -> tuple[tuple[PositionHit, ...], int]:
        """As candidatas daquele diagrama e **quantas existem**, do cache. `(lista, total)`.

        Os dois números, e não um: a lista para de crescer em 32 e o total não, e uma tela que
        mostrasse só a lista faria 32 de 147 passar por completo.

        A ordem é a da S-91 -- quem a legenda confirma vem primeiro --, então a candidata que a
        pessoa mais provavelmente quer já está no topo antes de ela filtrar qualquer coisa.
        """
        if entry is None or self.position_cache is None:
            return (), 0
        guardada = self.position_cache.positions.get(getattr(entry, "placement", ""))
        if guardada is None or not guardada.count:
            return (), 0
        ordenadas, _ = rank_candidates(guardada.games, pair_from_caption(entry.caption or ""))
        return ordenadas, guardada.count

    def neighbour_game_keys(self, *, radius: int = 3) -> frozenset[str]:
        """As partidas que os diagramas **vizinhos** também têm entre as candidatas (S-88).

        **Isto é dica de ordenação, e não regra de preenchimento -- a medição reprovou a
        segunda.** A hipótese era que a partida que explica os vizinhos explica este diagrama.
        Medida no acervo em 2026-08-15: ela aponta uma candidata única em **62 dos 373**
        ambíguos (16,6%, no melhor raio), contra o critério de 20% fixado antes de medir. E o
        que a reprovou de vez não foi o rendimento: dos 62, só **3** têm legenda com nomes para
        conferir a resposta -- ou seja, ela preencheria procedência sem meio de saber se acerta.

        Como ordenação ela não pode errar: no máximo põe a candidata errada em segundo lugar
        numa lista que a pessoa está lendo de qualquer forma.
        """
        if self.is_empty:
            return frozenset()
        centro = self.clamped_position()
        chaves: set[str] = set()
        for posicao in range(max(0, centro - radius), min(len(self.index), centro + radius + 1)):
            if posicao == centro:
                continue
            candidatas, _ = self.candidates_for(self.index.entries[posicao])
            chaves.update(candidata.key for candidata in candidatas)
        return frozenset(chaves)

    def current_candidates(self, *, radius: int = 3) -> tuple[tuple[PositionHit, ...], int]:
        """As candidatas do diagrama atual, na ordem em que a tela deve mostrá-las.

        Três critérios, do mais forte para o mais fraco: a legenda confirma (S-91), os vizinhos
        também a têm (S-88, só como dica), e a data (S-73). Nenhum deles descarta candidata.
        """
        candidatas, total = self.candidates_for(self.current)
        if len(candidatas) < 2:
            return candidatas, total
        vizinhas = self.neighbour_game_keys(radius=radius)
        par = self.current_caption_pair()
        # `sorted` é estável, então quem empata nos dois critérios mantém a ordem por data.
        ordenadas = sorted(
            candidatas,
            key=lambda hit: (
                not (par is not None and agrees_with_caption(hit, par)),
                hit.key not in vizinhas,
            ),
        )
        return tuple(ordenadas), total

    def current_caption_pair(self) -> tuple[str, str] | None:
        """Os dois sobrenomes que a legenda deste diagrama declara, se ela declarar.

        A tela usa isto para **marcar** as candidatas que a legenda confirma. Marcar e não
        filtrar: 26,5% das legendas discordam da base mesmo quando a posição está numa partida
        só, e uma lista filtrada por elas esconderia a partida certa em um caso a cada quatro.
        """
        atual = self.current
        return None if atual is None else pair_from_caption(atual.caption or "")

    def search_games_by_name(self, pair: tuple[str, str] | None = None) -> tuple[PositionHit, ...]:
        """Pergunta à base **pelos nomes**, agora, e devolve as que contêm esta posição (S-87).

        É o caminho que a lista do cache não alcança, e são dois casos medidos:

        - a lista foi **truncada em 32** e a partida certa ficou de fora -- 9 dos 22 diagramas
          em que a legenda não acha candidata nenhuma;
        - a posição **não casou com partida nenhuma** (1.922 diagramas do acervo, 53,9%), mas a
          base tem a partida, e a legenda diz quem jogou.

        Custa milissegundos porque o índice diz onde cada partida mora: são até 40 leituras com
        `seek`, e não uma passada pelos 10,3 GB. Sem índice devolve vazio, e a lista do cache
        continua sendo a resposta -- é caminho a mais, não substituto.
        """
        atual = self.current
        if atual is None or not self.database_paths or self.index_path is None:
            return ()
        par = pair or self.current_caption_pair()
        if par is None:
            return ()
        partidas = lookup_pair(par, list(self.database_paths), self.index_path)
        casadas = positions_of(partidas, getattr(atual, "placement", ""))
        achadas = [
            PositionHit(
                move_number=int(lance),
                side_to_move="w" if vez else "b",
                headers=kept_headers(partida.headers),
            )
            for partida, lance, vez in casadas
        ]
        # As partidas do par em que a posição **não** aparece entram como não verificadas: elas
        # não podem dar o lance, e podem dar evento, data e resultado. Medido: em 68 dos 140
        # diagramas do acervo nessa situação, é a única coisa que a base tem a oferecer.
        casadas_ids = {id(partida) for partida, _, _ in casadas}
        achadas += [
            PositionHit(
                move_number=0,
                side_to_move="",
                headers=kept_headers(partida.headers),
                verified=False,
            )
            for partida in partidas
            if id(partida) not in casadas_ids
        ]
        return tuple(achadas)

    def conflicts_with(self, hit: PositionHit) -> tuple[str, ...]:
        """Os campos que **a pessoa digitou** e que esta partida mudaria, se aplicada.

        A regra da S-72 -- "a base nunca sobrescreve" -- vale para a base decidindo sozinha.
        Uma pessoa escolhendo na lista é outra coisa, e pode trocar o que a base escreveu sem
        perguntar: mesma origem, versão melhor. O que ela não pode é apagar em silêncio o que
        *ela* digitou -- e é isso que esta lista existe para a tela perguntar antes.
        """
        anotacao = self.current_annotation
        da_base = set(anotacao.filled_fields)
        conflitos = []
        # Uma candidata não verificada não propõe lance nem vez, então não há o que conflitar:
        # ela não sabe esses dois campos, e o que ela não sabe não pode discordar de ninguém.
        if hit.verified:
            if anotacao.move_number not in (None, hit.move_number) and "move_number" not in da_base:
                conflitos.append("move_number")
            if anotacao.side_to_move not in (None, hit.side_to_move) and "side_to_move" not in da_base:
                conflitos.append("side_to_move")
        conflitos += [
            f"header:{nome}"
            for nome, valor in sorted(hit.headers.items())
            if valor
            and anotacao.headers.get(nome)
            and anotacao.headers[nome] != valor
            and f"header:{nome}" not in da_base
        ]
        return tuple(conflitos)

    def choose_game(self, hit: PositionHit, *, overwrite: bool = False) -> tuple[str, ...]:
        """Aplica a partida escolhida ao diagrama atual. Devolve os campos que ela mudou.

        `overwrite` decide o que fazer com o que a pessoa digitou -- ver `conflicts_with`. O
        que veio da base é trocado nos dois casos.

        Grava `chosen_game`, e é ele que faz a escolha sobreviver: um `cvoff-games --apply`
        depois disto respeita a partida escolhida em vez de reimpor a que o desempate prefere.
        """
        atual = self.current
        if atual is None:
            return ()
        anotacao = self.current_annotation
        protegidos = () if overwrite else self.conflicts_with(hit)

        mudancas: dict[str, Any] = {}
        campos: list[str] = []
        # Lance e vez vêm da **posição**, e sem posição eles seriam invenção. Evento, data e
        # resultado vêm da partida, e continuam sendo verdade sobre ela -- ver `PositionHit`.
        if hit.verified:
            if "move_number" not in protegidos and anotacao.move_number != hit.move_number:
                mudancas["move_number"] = hit.move_number
                campos.append("move_number")
            if "side_to_move" not in protegidos and anotacao.side_to_move != hit.side_to_move:
                mudancas["side_to_move"] = hit.side_to_move
                campos.append("side_to_move")

        headers = dict(anotacao.headers)
        for nome, valor in sorted(hit.headers.items()):
            if not valor or nome in RESERVED_HEADERS or f"header:{nome}" in protegidos:
                continue
            if headers.get(nome) != valor:
                headers[nome] = valor
                campos.append(f"header:{nome}")
        if headers != anotacao.headers:
            mudancas["headers"] = headers

        self.annotations.update(
            *atual.key,
            chosen_game=hit.key,
            filled_from=hit.label,
            filled_rule="human",
            # Os campos que **esta** escolha põe, e não a união com os de antes: a partida
            # trocou, então a procedência da anterior descreve valores que não estão mais aqui.
            filled_fields=tuple(campos),
            confirmed_from=anotacao.confirmed_from or hit.label,
            **mudancas,
        )
        return tuple(campos)

    def neighbours_with_game(self, hit: PositionHit, *, radius: int = 3) -> list[GalleryEntry]:
        """Os diagramas vizinhos que têm **esta mesma partida** entre as candidatas deles.

        Um capítulo analisa uma partida em cinco ou seis diagramas seguidos, e escolher a mesma
        coisa seis vezes é o trabalho que a S-86 existe para poupar.

        **Só os que a têm entre as candidatas**, e é a trava que faltou no "aplicar a todos" da
        S-76 -- aquele clique espalhou quatro campos por 1.405 diagramas. Aqui o vizinho que
        não contém a posição daquela partida simplesmente não entra.
        """
        if self.is_empty:
            return []
        centro = self.clamped_position()
        alcance = range(max(0, centro - radius), min(len(self.index), centro + radius + 1))
        vizinhos = []
        for posicao in alcance:
            if posicao == centro:
                continue
            entrada = self.index.entries[posicao]
            candidatas, _ = self.candidates_for(entrada)
            if any(candidata.key == hit.key for candidata in candidatas):
                vizinhos.append(entrada)
        return vizinhos

    def apply_game_to_neighbours(self, hit: PositionHit, *, radius: int = 3) -> int:
        """Aplica a partida aos vizinhos que a contêm. Devolve quantos foram tocados.

        Cada vizinho recebe **o lance dele**, não o do diagrama de origem: é a mesma partida em
        outro momento dela, e copiar o número do lance seria escrever o dado errado com a
        confiança de quem escolheu a partida certa.
        """
        posicao_original = self.position
        tocados = 0
        try:
            for entrada in self.neighbours_with_game(hit, radius=radius):
                self.position = self.index.entries.index(entrada)
                candidatas, _ = self.candidates_for(entrada)
                dele = next(c for c in candidatas if c.key == hit.key)
                if self.choose_game(dele):
                    tocados += 1
        finally:
            self.position = posicao_original
        return tocados

    def pending_pairs(self) -> set[tuple[str, str]]:
        """Os pares de nomes que as legendas do livro declaram, para a busca na base.

        Conjunto e não lista: 178 diagramas do `Secrets of Chess Training` rendem 167 pares
        distintos, e varrer a base atrás do mesmo par duas vezes custaria o dobro por nada.
        """
        pares = {pair_from_caption(entrada.caption) for entrada in self.index.entries}
        return {par for par in pares if par is not None}

    def save(self) -> Path | None:
        """Grava as anotações do livro. `None` quando não há livro aberto."""
        if self.pdf_path is None:
            return None
        if self.gallery_dir is None:
            return save_annotations(self.pdf_path, self.annotations)
        return save_annotations(self.pdf_path, self.annotations, directory=self.gallery_dir)

    # ------------------------------------------------------------------------ derivados

    def effective_fen(self) -> str:
        """A FEN que este diagrama terá no PGN, já com a declaração por cima.

        É o que a galeria mostra e o que alimenta o link do Lichess. Recalcular aqui em vez
        de guardar evita o defeito clássico: mudar o lance e o link continuar apontando para
        a posição antiga.
        """
        atual = self.current
        if atual is None:
            return ""
        anotacao = self.current_annotation
        lado = anotacao.side_to_move or atual.side_to_move
        return compose_fen(atual.placement, lado == "w", fullmove=anotacao.move_number or 1)

    def lichess_url(self) -> str:
        return lichess_analysis_url(self.effective_fen()) if self.current is not None else ""

    def exports_lichess_link(self, *, default: bool) -> bool:
        """Se este diagrama sai com link, dado o padrão da exportação."""
        declarado = self.current_annotation.lichess_link
        return default if declarado is None else declarado

    def annotated_count(self) -> int:
        """Quantos diagramas do livro têm alguma declaração. Vai para a barra de status."""
        return len(self.annotations.entries)

    def describe_position(self) -> str:
        """`"diagrama 12 de 340 — página 47"`, para o rótulo de navegação."""
        if self.is_empty:
            return "nenhum diagrama varrido"
        atual = self.index.entries[self.clamped_position()]
        return f"diagrama {self.clamped_position() + 1} de {len(self.index)} — página {atual.page_number}"
