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

from collections.abc import Sequence
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
from chess_diagram_ocr.games_db import DiagramMatch, pair_from_caption
from chess_diagram_ocr.semantics import compose_fen

__all__ = ["FIELD_LABELS", "HEADER_FIELDS", "GalleryModel", "describe_origin"]

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


FIELD_LABELS = {"move_number": "lance", "side_to_move": "vez"}
"""Como cada campo da S-72 aparece na linha de procedência. Header vira o nome dele."""


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
    return f"da base ({', '.join(campos)}): {annotation.filled_from}"


@dataclass
class GalleryModel:
    """O índice varrido, a posição atual e as anotações -- os três juntos e sem widget."""

    index: GalleryIndex = field(default_factory=GalleryIndex)
    annotations: GalleryAnnotations = field(default_factory=GalleryAnnotations)
    pdf_path: Path | None = None
    position: int = 0

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
        if anterior.filled_fields and "filled_fields" not in campos:
            restantes = tuple(nome for nome in anterior.filled_fields if nome not in campos)
            if restantes != anterior.filled_fields:
                campos = {
                    **campos,
                    "filled_fields": restantes,
                    # Sem campo nenhum da base sobrando, a evidência não descreve mais nada.
                    "filled_from": anterior.filled_from if restantes else "",
                }
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

        # Editar *este* header o tira da procedência da base, e deixa os outros como estavam --
        # a base pode ter preenchido `Event` e a pessoa corrigir só o `White`.
        restantes = tuple(campo for campo in anotacao.filled_fields if campo != f"header:{nome}")
        if restantes != anotacao.filled_fields:
            return self.edit(
                headers=headers,
                filled_fields=restantes,
                filled_from=anotacao.filled_from if restantes else "",
            )
        return self.edit(headers=headers)

    def apply_headers_to_all(self, names: tuple[str, ...] = HEADER_FIELDS) -> int:
        """Copia os headers declarados neste diagrama para todos os outros. Devolve quantos.

        Só os **declarados**: um campo em branco aqui não apaga o que outro diagrama tem.
        Aplicar a todos é para preencher `Event` e `Site` de um livro inteiro de uma vez, e
        transformar isso num apagador em massa seria um jeito caro de perder trabalho.
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

    def apply_matches(self, matches: Sequence[DiagramMatch], *, max_games: int = 5) -> tuple[int, int]:
        """Preenche com o que a base disse, **só onde está vazio** (S-72).

        Devolve `(diagramas tocados, campos preenchidos)`.

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
        tocados = campos = 0
        for casamento in matches:
            if casamento.games_matched > max_games:
                continue
            anterior = self.annotations.get(*casamento.key)
            mudancas: dict[str, Any] = {}
            if anterior.move_number is None:
                mudancas["move_number"] = casamento.move_number
            if anterior.side_to_move is None:
                mudancas["side_to_move"] = casamento.side_to_move
            novos = {
                nome: valor
                for nome, valor in casamento.headers.items()
                if valor and not anterior.headers.get(nome) and nome not in RESERVED_HEADERS
            }
            if novos:
                mudancas["headers"] = {**anterior.headers, **novos}
            if not mudancas:
                continue
            campos += sum(1 for chave in ("move_number", "side_to_move") if chave in mudancas) + len(novos)
            tocados += 1
            preenchidos: tuple[str, ...] = tuple(
                chave for chave in ("move_number", "side_to_move") if chave in mudancas
            )
            preenchidos += tuple(f"header:{nome}" for nome in sorted(novos))
            self.annotations.update(
                *casamento.key,
                filled_from=casamento.game_label,
                # A união com o que já havia: rodar a busca duas vezes, ou rodar a por nome
                # depois da por posição, não pode apagar a procedência da primeira.
                filled_fields=tuple(dict.fromkeys((*anterior.filled_fields, *preenchidos))),
                **mudancas,
            )
        return tocados, campos

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
