"""O exercício de tática montado do próprio acervo: FEN reconhecida + solução impressa (S-539).

**A pergunta que isto responde.** Quem tem o `1001 Winning Chess Sacrifices` e o `Manual of Chess
Combinations` digitalizados já tem, depois da varredura, mil FENs reconhecidas -- e nenhuma delas é
um exercício, porque exercício é posição **mais** gabarito. O gabarito está impresso: às vezes ao
lado do diagrama, quase sempre numa lista no fim do capítulo, atada ao diagrama pelo **número**.
Este módulo é o que casa os dois e diz, de cada diagrama, se ele virou exercício ou por que não.

## As quatro decisões, e por que cada uma é assim

1. **A lista de soluções é lida contra os números que os diagramas reivindicam, e não em branco.**
   Uma varredura cega de `^\\d+\\.` numa página de soluções acha `1.`, `2.` e `3.` **dentro** de
   cada solução -- os números de lance --, e um livro em que a solução 12 chega ao lance 34 daria
   uma entrada 34 falsa. `solucoes_da_folha` recebe os números esperados e caminha por eles em
   ordem crescente: só abre entrada quando o token é exatamente o próximo número que algum
   diagrama pediu. É a mesma ideia de `text/notacao.validar` -- o contexto é o dicionário.
2. **A solução decide o lado a jogar, e vence a dedução da S-17.** O diagrama de livro não diz de
   quem é a vez, e `semantics.infer_side_to_move` chuta pela legalidade; a linha impressa é prova:
   se `1.Qxh7+` só é legal com as brancas, é das brancas. `validar_solucao` joga a linha nos dois
   lados e fica com o que sustenta mais lances -- e é o resultado mais barato deste módulo, porque
   ele conserta o campo que mais errava no PGN exportado.
3. **Uma solução que não fecha não vira exercício, e o motivo é guardado.** `text/notacao.validar`
   já para no primeiro lance que a posição não sustenta e diz qual foi. Um exercício com gabarito
   errado é pior que exercício nenhum: quem treina aprende o lance errado, e a recusa com o motivo
   é o que permite consertar a leitura em vez de desconfiar do programa.
4. **O motor confirma, e não decide.** `confirmar` pergunta quanto o primeiro lance impresso perde
   contra o que o motor prefere, pela régua da S-537 -- abaixo do corte de imprecisão, confirmado.
   Ele **não** substitui a solução do livro: um livro de 1934 propõe combinações que o Stockfish
   refuta, e apagar o gabarito por isso seria trocar o acervo pelo motor. O que a discordância faz
   é marcar o exercício, e a marca é o que o crítico deste projeto pediria para ver.

## O que este módulo não faz

Não abre PDF, não roda modelo e não desenha nada: `de_pdf` é um adaptador de dez linhas com import
tardio, para que quem só quer casar texto com diagrama não pague `torch`. Quem grava o resultado é
`taticas_arquivo.py`, e quem o mostra é `qt/painel_de_treino.py`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import chess

from .semantics import compose_fen
from .text import notacao
from .text.pagina import BlocoDeTexto, PaginaLida
from .ui import analise_da_partida as regua

logger = logging.getLogger(__name__)

__all__ = [
    "AO_LADO",
    "CONFIRMADA",
    "DISCORDOU",
    "DISTANCIA_DO_NUMERO",
    "FILEIRAS_MINIMAS",
    "FOLGA_DA_COLUNA",
    "FOLGA_DA_FILEIRA",
    "GANHA_MATERIAL",
    "LADOS",
    "LADO_ABAIXO",
    "LADO_ACIMA",
    "MATE",
    "NAO_PERGUNTADO",
    "NO_FIM",
    "NUMERO_MAXIMO",
    "PARTE_DE_LANCES",
    "PLIES_MINIMOS",
    "SEM_GANHO",
    "VALOR_DA_PECA",
    "DiagramaLido",
    "Exercicio",
    "Extracao",
    "Folha",
    "Procedencia",
    "Recusa",
    "Solucao",
    "confirmar",
    "de_pdf",
    "desfecho",
    "extrair",
    "lance_da_celula",
    "linha_ao_lado",
    "nome_curto",
    "numero_junto_ao_diagrama",
    "numeros_da_folha",
    "solucoes_da_folha",
    "tabela_de_solucoes",
    "validar_solucao",
]

# ------------------------------------------------------------------------- os vocabulários

AO_LADO = "ao_lado"
NO_FIM = "no_fim"
"""De onde veio o gabarito. Minúsculos e sem acento porque são chave, e não texto de tela -- a
mesma regra de `analise_da_partida.IMPRECISAO`; quem os escreve para o usuário é
`ui/treino_declarado.py`."""

ORIGENS: tuple[str, ...] = (AO_LADO, NO_FIM)

MATE = "mate"
GANHA_MATERIAL = "ganha_material"
SEM_GANHO = "sem_ganho"
"""O que a solução produz no tabuleiro. Ver `desfecho` para o que "sem ganho" quer dizer -- e para
por que ele **não** é motivo de recusa."""

CONFIRMADA = "confirmada"
DISCORDOU = "discordou"
NAO_PERGUNTADO = "nao_perguntado"
"""O que o motor disse do primeiro lance da solução. `NAO_PERGUNTADO` é o estado de quem extraiu
sem motor, e é o padrão: a extração de um livro inteiro não pode depender de um binário opcional."""

NUMERO_MAXIMO = 9999
"""O maior número de exercício que um livro imprime. Quatro dígitos porque o `Polgar 5334` existe;
acima disso o token é ano, página ou Elo, e não número de exercício."""

DISTANCIA_DO_NUMERO = 0.45
"""Quão longe do diagrama o número impresso pode estar, em frações da **altura do diagrama**.

Fração e não pixel, porque a mesma folha vale a 150 e a 300 dpi -- é a regra de
`text/colunas.py`. Quase meia altura de tabuleiro é generoso de propósito: o número costuma vir
colado, e o que este teto impede é o número do exercício **seguinte**, que está a uma altura
inteira de distância."""

PLIES_MINIMOS = 1
"""Quantos meios-lances a solução precisa ter para o diagrama virar exercício.

Um, e não dois. Metade das combinações de livro é `1.Qxh7+!` seguido de `+-` -- o autor não
imprime a continuação porque ela é óbvia --, e exigir a resposta das pretas jogaria fora a
população que o livro considera a mais limpa. Ver `linha_ao_lado`, que pede **dois**, e o
comentário de lá diz por que a régua muda de lado quando não há número para atar."""

PLIES_MINIMOS_AO_LADO = 2
"""E a linha ao lado do diagrama pede dois. Sem número que a ate ao diagrama, o único vínculo é a
vizinhança na página -- e um lance solto perto de um tabuleiro é a legenda de uma partida tanto
quanto o gabarito de um exercício. Dois meios-lances que a posição sustenta já não são acaso."""

VALOR_DA_PECA: dict[chess.PieceType, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
"""A tabela de sempre, e o rei vale zero porque ele não se captura.

**Não é a régua do motor, e não quer ser.** Ela existe para uma pergunta binária -- a solução
termina com material a mais para quem a jogou? --, e para essa pergunta 3 para bispo e cavalo
basta. Quem quer saber quanto a posição vale pergunta ao motor, que é o que `confirmar` faz."""

_SO_NUMERO = re.compile(r"^\(?\s*(\d{1,4})\s*[.)]?\s*$")
"""Um bloco de texto que é **só** o número do exercício, com o ponto ou o parêntese que o livro
põe. `97.`, `(214)`, `130` -- e nada mais: um bloco com `97. Alekhine` é legenda, e atá-lo ao
diagrama pelo número faria a legenda virar gabarito."""


# --------------------------------------------------------------------------------- os dados


@dataclass(frozen=True)
class Procedencia:
    """De onde este exercício saiu. É o que a tela mostra embaixo do tabuleiro.

    **Cinco campos e não um texto pronto**, porque a frase é uma vista e a procedência é o dado:
    quem quiser reabrir a folha do livro precisa do índice, e quem quiser mostrá-la ao usuário
    precisa do número impresso -- que não é o índice, e essa distinção é a de
    `PaginaLida.numero_impresso`.
    """

    livro: str = ""
    """O caminho ou o nome do livro, como o resto do projeto o identifica (`Ancora.documento`)."""

    pagina: int = -1
    """Índice 0-based da folha, que é a chave com que o visualizador abre a página."""

    diagrama: int = -1
    numero: int | None = None
    """O número que o livro imprimiu ao lado do diagrama. `None` = o livro não numerou."""

    folha_impressa: int | None = None
    """O número que a folha **mostra**, que quase nunca é `pagina + 1` (S-16)."""

    def chave(self) -> str:
        """A identidade estável do exercício, e é ela que a repetição espaçada agenda.

        Livro, folha e diagrama -- e **não** o número impresso: dois capítulos de um livro podem
        recomeçar a numeração em 1, e uma chave que colidisse faria a agenda de amanhã mostrar o
        exercício errado. O caminho do livro entra inteiro porque é o que `estudo_arquivo.chave_de`
        já usa para separar dois livros de mesmo nome.
        """
        return f"{self.livro}#{self.pagina}#{self.diagrama}"

    def frase(self) -> str:
        """`Reinfeld 1001, p. 63, exercício 214`. A linha que aparece com a solução.

        A folha impressa vence o índice, porque é ela que está escrita no papel: mandar quem
        estuda procurar a "página 71" de um PDF cuja página 71 mostra 63 é mandá-lo procurar duas
        vezes. Sem folha impressa, o índice sai como `folha N`, que é honesto sobre o que ele é.
        """
        partes = [nome_curto(self.livro) or "livro não identificado"]
        if self.folha_impressa is not None:
            partes.append(f"p. {self.folha_impressa}")
        elif self.pagina >= 0:
            partes.append(f"folha {self.pagina + 1}")
        if self.numero is not None:
            partes.append(f"exercício {self.numero}")
        return ", ".join(partes)

    def para_json(self) -> dict[str, Any]:
        return {
            "livro": self.livro,
            "pagina": self.pagina,
            "diagrama": self.diagrama,
            "numero": self.numero,
            "folha_impressa": self.folha_impressa,
        }

    @classmethod
    def de_json(cls, dados: Any) -> Procedencia:
        bruto = dados if isinstance(dados, dict) else {}
        numero = bruto.get("numero")
        folha = bruto.get("folha_impressa")
        return cls(
            livro=str(bruto.get("livro", "")),
            pagina=int(bruto.get("pagina", -1)),
            diagrama=int(bruto.get("diagrama", -1)),
            numero=int(numero) if numero is not None else None,
            folha_impressa=int(folha) if folha is not None else None,
        )


def nome_curto(livro: str) -> str:
    """O nome do arquivo sem a pasta e sem a extensão -- o que cabe numa linha de tela.

    **Público porque a tela do placar precisa do mesmo corte** (S-541). O caminho inteiro de um
    livro do acervo tem 80 caracteres e uma extensão; escrito na linha do placar, ele empurra o
    número para fora da janela -- foi o que a primeira fotografia mostrou.
    """
    bruto = str(livro or "").replace("\\", "/").rstrip("/")
    nome = bruto.rsplit("/", 1)[-1]
    return nome[:-4] if nome.lower().endswith(".pdf") else nome


@dataclass(frozen=True)
class DiagramaLido:
    """Um diagrama que o modelo já leu: o campo de peças e o que o pipeline achou da vez.

    `vez` vazia é "não se sabe", e é o caso comum -- e é justamente o que a solução resolve.
    """

    indice: int
    """A posição do diagrama na folha, **em base zero** -- a mesma de `PaginaLida.diagramas`.

    **E não a de `DiagramPosition.diagram_index`, que começa em 1** (`pdf_to_pgn.py:566`,
    `enumerate(candidates, start=1)`). As duas metades deste módulo se encontram por este número:
    o campo de peças vem da varredura e a caixa na folha vem da leitura, e com bases diferentes
    cada diagrama recebia a caixa -- e portanto o número impresso -- **do seguinte**. Medido no
    `Big Book of Combinations`: os 963 números saíam deslocados de um, e o último de cada folha
    ficava sem caixa nenhuma. Quem converte é `de_pdf`, que é o adaptador entre os dois mundos."""

    placement: str
    vez: str = ""


@dataclass(frozen=True)
class Folha:
    """Uma folha do livro como este módulo a recebe: o texto lido e os diagramas reconhecidos.

    **As duas metades vêm de lugares diferentes de propósito.** O texto sai de `text/leitor.py`
    (ou da camada do PDF); os diagramas saem de `pdf_to_pgn.scan_pdf_positions`, que roda o
    classificador. Juntá-los numa estrutura só aqui dentro obrigaria este módulo a conhecer os
    dois caminhos -- e é ele que precisa continuar afirmável sem PDF nenhum.
    """

    pagina: int
    texto: PaginaLida | None = None
    diagramas: tuple[DiagramaLido, ...] = ()

    @property
    def folha_impressa(self) -> int | None:
        return self.texto.numero_impresso if self.texto is not None else None


@dataclass(frozen=True)
class Solucao:
    """O que a linha impressa deu quando jogada sobre o diagrama.

    Irmã de `text/notacao.LinhaValidada`, com o lado a jogar por cima: lá a posição entra pronta,
    e aqui descobrir de quem é a vez **é** metade do trabalho.
    """

    lances: tuple[str, ...] = ()
    """Em SAN, já normalizado pelo `chess` -- é o que vai para o arquivo e para a tela."""

    vez: str = ""
    """`w` ou `b`: o lado com que a linha fechou. Vazio quando ela não fechou de lado nenhum."""

    motivo: str = ""
    """Por que a linha parou. Vazio = ela fechou inteira. **Motivo com lance é o caso comum**: a
    lista de soluções põe variante e sujeira de OCR depois do gabarito, e parar ali é acertar."""

    token: str = ""

    @property
    def fechou(self) -> bool:
        return bool(self.lances) and not self.motivo


@dataclass(frozen=True)
class Exercicio:
    """Uma posição, o gabarito dela e de onde os dois saíram."""

    fen: str
    """A FEN **inteira**, com o lado a jogar que a solução provou e o roque inferido (S-05)."""

    lances: tuple[str, ...]
    """A solução em SAN, na ordem. O primeiro é o que o treino cobra."""

    procedencia: Procedencia
    origem: str = NO_FIM
    folha_da_solucao: int = -1
    """Índice da folha em que o gabarito estava impresso. Igual à do diagrama no caso `AO_LADO`."""

    desfecho: str = SEM_GANHO
    motor: str = NAO_PERGUNTADO
    perda_do_motor: int = -1
    """Quanto o primeiro lance impresso perde contra o que o motor prefere, em centipeões.
    `-1` = não perguntado. Zero é resposta legítima e diferente disso."""

    @property
    def chave(self) -> str:
        return self.procedencia.chave()

    @property
    def lado(self) -> str:
        """`w` ou `b`, tirado da própria FEN -- e não de um campo que possa discordar dela."""
        partes = self.fen.split()
        return partes[1] if len(partes) > 1 else "w"

    @property
    def primeiro(self) -> str:
        return self.lances[0] if self.lances else ""

    def tabuleiro(self) -> chess.Board:
        return chess.Board(self.fen)

    def para_json(self) -> dict[str, Any]:
        return {
            "fen": self.fen,
            "lances": list(self.lances),
            "procedencia": self.procedencia.para_json(),
            "origem": self.origem,
            "folha_da_solucao": self.folha_da_solucao,
            "desfecho": self.desfecho,
            "motor": self.motor,
            "perda_do_motor": self.perda_do_motor,
        }

    @classmethod
    def de_json(cls, dados: Any) -> Exercicio:
        bruto = dados if isinstance(dados, dict) else {}
        return cls(
            fen=str(bruto.get("fen", "")),
            lances=tuple(str(x) for x in bruto.get("lances", ())),
            procedencia=Procedencia.de_json(bruto.get("procedencia")),
            origem=str(bruto.get("origem", NO_FIM)),
            folha_da_solucao=int(bruto.get("folha_da_solucao", -1)),
            desfecho=str(bruto.get("desfecho", SEM_GANHO)),
            motor=str(bruto.get("motor", NAO_PERGUNTADO)),
            perda_do_motor=int(bruto.get("perda_do_motor", -1)),
        )


@dataclass(frozen=True)
class Recusa:
    """Um diagrama que **não** virou exercício, e por quê.

    **Vale tanto quanto o exercício, e é a metade que costuma sumir.** Um extrator que devolve só
    o que deu certo não deixa medir a própria taxa: 300 exercícios de um livro de 1001 podem ser
    um bom resultado ou um defeito de leitura, e a diferença está nos 701 motivos.
    """

    procedencia: Procedencia
    motivo: str


@dataclass(frozen=True)
class Extracao:
    """O resultado de passar um livro por aqui."""

    exercicios: tuple[Exercicio, ...] = ()
    recusas: tuple[Recusa, ...] = ()
    diagramas: int = 0
    """Quantos diagramas entraram. `exercicios + recusas` tem de dar isto, e o teste cobra."""

    def por_motivo(self) -> dict[str, int]:
        """Quantas recusas de cada motivo, para o relatório dizer **onde** o casamento falhou."""
        contagem: dict[str, int] = {}
        for recusa in self.recusas:
            contagem[recusa.motivo] = contagem.get(recusa.motivo, 0) + 1
        return dict(sorted(contagem.items(), key=lambda par: (-par[1], par[0])))

    def resumo(self) -> str:
        """A linha do relatório: quantos diagramas, quantos viraram exercício, quantos ficaram.

        **E quantos o motor recusou, quando houve motor** -- porque é o número que muda a leitura
        do primeiro. Num livro cuja camada de texto é ruim, "10 com solução" e "10 recusadas pelo
        motor" são a mesma frase dita duas vezes, e sem a segunda metade o relatório mente.
        """
        if not self.diagramas:
            return "Nenhum diagrama nesta varredura."
        quantos = len(self.exercicios)
        frase = (
            f"{self.diagramas} diagrama(s), {quantos} com solução "
            f"({100.0 * quantos / self.diagramas:.1f}%), {len(self.recusas)} sem."
        )
        perguntados = [e for e in self.exercicios if e.motor != NAO_PERGUNTADO]
        if perguntados:
            confirmados = sum(1 for e in perguntados if e.motor == CONFIRMADA)
            frase += f" O motor confirmou {confirmados} de {len(perguntados)}."
        return frase


# ------------------------------------------------------------------- o número junto ao diagrama


def _numero_do_bloco(texto: str) -> int | None:
    achado = _SO_NUMERO.match(str(texto or "").strip())
    if achado is None:
        return None
    valor = int(achado.group(1))
    return valor if 1 <= valor <= NUMERO_MAXIMO else None


def _sobrepoe(a: Sequence[float], b: Sequence[float]) -> bool:
    """As duas caixas se cruzam **na horizontal**. É o que ata um rótulo à coluna dele."""
    return min(a[2], b[2]) > max(a[0], b[0])


LADO_ACIMA = "acima"
LADO_ABAIXO = "abaixo"
"""De que lado do tabuleiro o livro imprime o número (S-539, r2).

**O acervo faz os dois, e a diferença não é de estilo: ela troca o gabarito de diagrama.** O `Big
Book of Combinations` imprime **em cima**; o `Manual of Chess Combinations` imprime **embaixo**.
Numa folha de seis tabuleiros empilhados os dois candidatos existem sempre -- o número de cima é o
deste diagrama e o de baixo é o do seguinte --, e escolher pelo mais próximo escolhe errado toda
vez que a folga de baixo for menor, que é o caso do `Big Book`: 14,6 pt contra 29,2 pt. Quem
decide é a folha inteira (ver `numeros_da_folha`), e não cada tabuleiro sozinho."""

LADOS: tuple[str, ...] = (LADO_ACIMA, LADO_ABAIXO)


def numero_junto_ao_diagrama(
    pagina: PaginaLida | None, indice: int, *, lado: str = ""
) -> int | None:
    """O número que o livro imprimiu junto daquele diagrama, ou `None` (S-539).

    **A régua é geométrica porque a informação é geométrica**: o que faz `97` ser o número deste
    tabuleiro e não do vizinho é estar junto dele e não junto do outro. Três condições, e as três
    medidas contra a caixa do diagrama:

    1. o bloco é **só** o número (ver `_SO_NUMERO`);
    2. ele cruza a faixa horizontal do diagrama -- é da mesma coluna;
    3. a distância vertical cabe em `DISTANCIA_DO_NUMERO` da altura do tabuleiro.

    **`lado` é a correção da segunda rodada, e ela vale 82,2% contra 94,8%.** Sem ele a escolha é o
    candidato mais próximo, e no `Big Book of Combinations` o mais próximo é o número **do diagrama
    seguinte**: a folha imprime `95` a 29,2 pt acima do primeiro tabuleiro e `96` a 14,6 pt abaixo
    dele, e os 963 números do livro saíam todos deslocados de um. `LADO_ACIMA` e `LADO_ABAIXO`
    pedem um lado só; vazio mantém a régua do mais próximo, com **empate para cima**, que é o que
    um diagrama sozinho -- sem folha para votar -- consegue afirmar.

    **O número da própria folha não é número de exercício**, e a exclusão é de uma linha (S-539,
    r2). Num livro de um diagrama por folha -- o `Great Chess Combinations` do Anand -- o tabuleiro
    ocupa metade da página e o número de página impresso na margem cai dentro do teto de distância:
    **78 dos 83 números** que aquele livro dava eram o número da folha, e três deles chegaram a
    virar exercício com um gabarito de peão tirado de uma folha de prosa. No `Big Book`, onde a
    numeração de exercício e a de página são duas colunas distantes, a exclusão custa **um** número
    em 1.002; no `Manual of Chess Combinations` e no Koblenz, nenhum.

    **O candidato é a linha, e não o parágrafo, e isto foi medido** (2026-09-04). No `Big Book of
    Combinations` o número e a legenda da partida são **um** bloco -- `5 / Morphy-De Riviere /
    Paris, 1858` --, porque a leitura agrupa linhas vizinhas em parágrafo. Perguntando ao parágrafo,
    nenhum dos 1.000 exercícios daquele livro tem número; perguntando à linha, todos têm. O número
    impresso é uma linha por natureza: ele está sozinho no seu tipo, centrado sobre o tabuleiro.
    """
    if pagina is None:
        return None
    caixa = _caixa_do_diagrama(pagina, indice)
    if caixa is None:
        return None
    altura = max(1.0, caixa[3] - caixa[1])
    teto = DISTANCIA_DO_NUMERO * altura

    melhor: tuple[float, int, int] | None = None
    for bbox, texto in _candidatos_a_numero(pagina):
        numero = _numero_do_bloco(texto)
        if numero is None or numero == pagina.numero_impresso or not _sobrepoe(bbox, caixa):
            continue
        acima = caixa[1] - bbox[3]
        abaixo = bbox[1] - caixa[3]
        if lado == LADO_ACIMA:
            distancia, de_que_lado = acima, 0
        elif lado == LADO_ABAIXO:
            distancia, de_que_lado = abaixo, 1
        else:
            distancia, de_que_lado = (acima, 0) if acima >= abaixo else (abaixo, 1)
        if distancia < -altura * 0.1 or distancia > teto:
            continue
        candidato = (max(0.0, distancia), de_que_lado, numero)
        if melhor is None or candidato[:2] < melhor[:2]:
            melhor = candidato
    return melhor[2] if melhor is not None else None


def _candidatos_a_numero(pagina: PaginaLida) -> list[tuple[tuple[float, float, float, float], str]]:
    """As caixas de texto que podem ser o número: cada **linha**, e o bloco quando ele não tem.

    O bloco sem linha é o que vem de um arquivo gravado por um caminho que não as guardou; ali a
    caixa do parágrafo é tudo o que há, e usá-la é melhor que ignorar a folha.
    """
    candidatos: list[tuple[tuple[float, float, float, float], str]] = []
    for bloco in pagina.blocos:
        if not isinstance(bloco, BlocoDeTexto):
            continue
        linhas = getattr(bloco, "linhas", ())
        if linhas:
            candidatos += [(linha.bbox, linha.texto) for linha in linhas]
        else:
            candidatos.append((bloco.bbox, bloco.texto))
    return candidatos


def _caixa_do_diagrama(pagina: PaginaLida, indice: int) -> tuple[float, float, float, float] | None:
    for bloco in pagina.diagramas:
        if bloco.indice == indice:
            return bloco.bbox
    return None


def _corrida(achados: Mapping[int, int], ordem: Mapping[int, int]) -> tuple[int | None, int]:
    """O deslocamento `numero - posição` da maioria, e de quantos ele é. `None` = não há maioria."""
    contagem: dict[int, int] = {}
    for indice, numero in achados.items():
        if indice in ordem:
            deslocamento = numero - ordem[indice]
            contagem[deslocamento] = contagem.get(deslocamento, 0) + 1
    if not contagem:
        return None, 0
    base, quantos = max(contagem.items(), key=lambda par: (par[1], -par[0]))
    if quantos * 2 <= sum(contagem.values()) and len(contagem) > 1:
        # Sem maioria, não há corrida: os números achados discordam entre si, e escolher um deles
        # para preencher os outros seria inventar gabarito.
        return None, quantos
    return base, quantos


def _lidos_de_um_lado(
    pagina: PaginaLida | None, diagramas: Sequence[DiagramaLido], lado: str
) -> dict[int, int]:
    return {
        diagrama.indice: numero
        for diagrama in diagramas
        if (numero := numero_junto_ao_diagrama(pagina, diagrama.indice, lado=lado)) is not None
    }


def numeros_da_folha(
    pagina: PaginaLida | None, diagramas: Sequence[DiagramaLido]
) -> dict[int, int]:
    """Índice do diagrama -> número impresso, com os buracos preenchidos pela **corrida** (S-539).

    **De que lado está o número é decidido pela folha, e é a correção da segunda rodada.** Um
    tabuleiro sozinho não sabe: numa coluna de três, o número de cima é o dele e o de baixo é o do
    vizinho, e os dois cabem no teto de distância. A folha sabe, porque um livro numera em
    sequência: o lado certo é o que produz uma **corrida** -- `numero - posição` igual para todos --
    e o errado produz números embaralhados. Medido no `Big Book of Combinations`, onde o número é
    impresso em cima e o de baixo fica mais perto: escolhendo pelo mais próximo, 82,2% de acerto
    contra a folha impressa; deixando a folha votar, **94,8%**. Empate fica com `LADO_ACIMA`.

    **O preenchimento é a parte que rende, e ele é conservador.** Um livro de exercícios numera em
    sequência, e uma folha com `97 98 ? 100` perdeu o `99` por leitura, não por o livro não o ter
    impresso. Quando os números achados são consecutivos na ordem de leitura, a corrida é conhecida
    e os que faltam saem dela.

    **O que foi lido não é sobrescrito, e é o outro defeito da segunda rodada.** A versão anterior
    devolvia a corrida inteira -- `base + posição` para **todos** os diagramas --, de modo que um
    número mal lido em qualquer posição deslocava a folha toda e um diagrama a mais na varredura
    inventava um número que outra folha já tinha: 57 números do `Big Book` eram dados a dois
    diagramas diferentes, e um deles era `1002` num livro de 1001. Agora a corrida só entra onde
    não houve leitura, e nunca repete um número que a própria folha já usou.

    **Nem o intruso é corrigido, e isto foi medido nos dois sentidos.** A versão de ontem
    substituía um `1858` -- o ano de `Paris, 1858` quebrado em duas linhas -- pelo que a corrida
    dizia, e a tentação é manter a correção só para quem cai fora do intervalo da folha. Medido no
    `Big Book`: corrigir custa **quatro números certos** (939 contra 943 em 944 conferíveis) e
    poupa quatro repetições, porque a corrida também erra -- na folha 64 ela apagou um `251`
    impresso e pôs `257`. Onde o papel afirma, o papel vence; o intruso vira um número que nenhuma
    lista de soluções responde, e o diagrama sai como recusa em vez de sair com o gabarito de
    outro exercício.

    Basta **um** número achado para a corrida existir, e é de propósito: numa folha de um diagrama
    só não há o que confirmar, e ali a corrida não inventa nada -- ela devolve o próprio número.
    Sem maioria -- dois deslocamentos empatados, ou todos diferentes --, nada é preenchido: ali a
    leitura não sabe o bastante, e inventar gabarito é o pior resultado possível deste módulo.
    """
    ordem = {diagrama.indice: posicao for posicao, diagrama in enumerate(diagramas)}
    por_lado = {lado: _lidos_de_um_lado(pagina, diagramas, lado) for lado in LADOS}
    corridas = {lado: _corrida(achados, ordem) for lado, achados in por_lado.items()}
    # A folha vota: vence o lado cuja maioria é maior. Empate fica com o de cima, que é o lado do
    # livro mais comum do acervo -- e é o mesmo desempate de `numero_junto_ao_diagrama`.
    escolhido = max(LADOS, key=lambda lado: (corridas[lado][1], lado == LADO_ACIMA))
    achados = dict(por_lado[escolhido])
    if not achados:
        return {}
    base = corridas[escolhido][0]
    if base is None:
        return achados
    usados = set(achados.values())
    for indice, posicao in ordem.items():
        candidato = base + posicao
        if indice in achados or not 1 <= candidato <= NUMERO_MAXIMO or candidato in usados:
            continue
        achados[indice] = candidato
        usados.add(candidato)
    return achados


# ------------------------------------------------------------------------ a lista de soluções


FILEIRAS_MINIMAS = 6
"""Quantas fileiras uma folha precisa ter para ser lida como **tabela** e não como fluxo (S-539).

Seis, e o número é o que separa a folha de soluções do cabeçalho corrente: uma folha de miolo tem
um número solto na margem -- o da própria página, que o `Big Book` imprime como `214 The Big Book
of Combinations` -- e uma folha de soluções tem quarenta empilhados na mesma coluna. Abaixo de
seis não há coluna a detectar: há um número."""

FOLGA_DA_COLUNA = 1.2
"""Quanto dois rótulos podem divergir na horizontal e ainda serem da mesma coluna, em **alturas de
linha**. Medido na tabela do `Big Book`: a coluna do número varia de 34,1 a 38,7 pt com linha de
~10 pt, e a coluna seguinte começa 27 pt adiante -- há folga de sobra entre as duas."""

FOLGA_DA_FILEIRA = 0.6
"""E quanto podem divergir na vertical e ainda serem da mesma fileira. Pouco mais de meia altura:
as células de uma fileira compartilham a linha de base, e a fileira seguinte está a uma altura
inteira. Um teto maior casaria o número de uma fileira com o lance da outra, que é exatamente o
defeito que esta leitura existe para não ter."""

PARTE_DE_LANCES = 0.35
"""Que fração das células de uma coluna precisa ser um lance para ela **ser** a coluna do lance.

Um terço, e não a maioria: a coluna da solução carrega o cabeçalho da tabela, os títulos de seção
e o que o OCR estragou, e exigir maioria a perderia nas folhas ruins -- que são justamente as que
esta leitura precisa aproveitar. O que impede o estrago não é o corte: é a exigência de que a
célula case com `notacao.LANCE` inteira, e de que o lance depois seja legal na posição lida."""

_TROCA_DE_OCR: dict[str, str] = {"S": "5", "s": "5", "l": "1", "I": "1", "O": "0"}
"""As confusões que a camada de texto desta fonte faz **dentro** de um lance (S-539).

`5` sai como `S` ou `s`, `1` como `l` ou `I`, `0` como `O`. São as medidas na tabela do `Big Book`
-- `RxfS`, `QxdS`, `fS`, `es` --, e valem só depois do primeiro caractere (ver `_consertar_digitos`).

**Nenhuma delas destrói um lance legítimo, e é o que as torna seguras aqui.** Em SAN o primeiro
caractere é peça ou coluna, e do segundo em diante só existem `a`-`h`, `1`-`8`, `x`, `=`, `-`, `O`
e os sufixos: `s`, `S`, `l`, `I` **não ocorrem** num lance bem lido depois da primeira posição, e o
`O` só ocorre no roque, que `_consertar_digitos` recusa pela primeira letra."""


def _consertar_digitos(token: str) -> str:
    """`RxhS` -> `Rxh5`: as trocas de `_TROCA_DE_OCR`, e **só depois da primeira letra** (S-539).

    A primeira fica intacta porque ela é a peça: trocar o `S` de `Sf3` por um dígito apagaria o
    lance alemão que `notacao.FIGURINAS_DA_LETRA` reconhece. E o roque nem entra: `O-O` é o único
    lance cujo `O` é letra, e trocá-lo por zero produziria `0-0`, que o `chess` aceita -- um lance
    certo pelo motivo errado é pior que um ilegível.
    """
    if len(token) < 2 or token[0] in "O0":
        return token
    return token[0] + "".join(_TROCA_DE_OCR.get(letra, letra) for letra in token[1:])


def lance_da_celula(texto: str) -> str:
    """O lance que esta célula da tabela contém, ou vazio (S-539).

    **A célula inteira tem de ser o lance.** `notacao.LANCE` já é a régua conservadora do projeto,
    e ela é o que impede que `1951` -- o ano, que mora duas colunas à esquerda -- ou `56799` -- a
    contagem de nós, que mora três à direita -- entrem como gabarito. O espaço interno é removido
    porque a camada parte `Rxh 7+` em dois pedaços na mesma célula.

    O conserto de OCR é a **segunda** tentativa e nunca a primeira: um token que já é lance não
    passa por ele, e assim `Sf3` continua sendo o cavalo alemão em vez de virar `5f3`.
    """
    bruto = "".join(str(texto or "").split())
    if not bruto:
        return ""
    for candidato in (bruto, _consertar_digitos(bruto)):
        if notacao.LANCE.match(notacao.para_ingles(candidato)):
            return candidato
    return ""


_SUJEIRA_DA_CELULA = " \t:;.,·•()[]{}"


def numero_da_celula(texto: str) -> int | None:
    """O número de exercício de uma célula da tabela, tolerando o espaço que a camada mete dentro.

    **Mais frouxo que `_SO_NUMERO`, e só aqui.** Na folha 193 do `Big Book` a camada devolve
    `':1 07'`, `'1 08'` e `'1 1 2'` onde estão 107, 108 e 112 -- o dígito sai partido e com um
    dois-pontos grudado --, e a régua estrita perde a folha inteira: dezoito exercícios de uma vez.
    A frouxidão é segura **nesta** posição porque a célula ainda tem de estar na coluna que conta
    de um em um e ao lado de um lance legal; ela não vale para o número junto ao diagrama, onde o
    contexto que a segura não existe.
    """
    limpo = str(texto or "").strip(_SUJEIRA_DA_CELULA).replace(" ", "")
    if not limpo.isdecimal():
        return None
    valor = int(limpo)
    return valor if 1 <= valor <= NUMERO_MAXIMO else None


def _x0(celula: tuple[tuple[float, float, float, float], str]) -> float:
    return celula[0][0]


def _meio(celula: tuple[tuple[float, float, float, float], str]) -> float:
    return (celula[0][1] + celula[0][3]) / 2.0


def _colunas_por_x(
    celulas: Sequence[tuple[tuple[float, float, float, float], str]], folga: float
) -> list[list[tuple[tuple[float, float, float, float], str]]]:
    """As células agrupadas em colunas pela borda esquerda, ancoradas na primeira de cada grupo.

    Ancorado e não encadeado: numa folha densa, "cada um a menos de uma folga do anterior" junta a
    página inteira numa coluna só -- é o defeito clássico do agrupamento por vizinhança, e o mesmo
    que `text/colunas.py` evita projetando a calha em vez de encadear caixas.
    """
    grupos: list[list[tuple[tuple[float, float, float, float], str]]] = []
    for celula in sorted(celulas, key=_x0):
        if grupos and _x0(celula) - _x0(grupos[-1][0]) <= folga:
            grupos[-1].append(celula)
        else:
            grupos.append([celula])
    return grupos


def tabela_de_solucoes(pagina: PaginaLida | None) -> dict[int, tuple[str, ...]]:
    """A lista de soluções lida por **faixa de coluna**, quando a folha é uma tabela (S-539).

    **É a correção da segunda rodada, e ela vale 693 pares contra 24.** A lista do `Big Book of
    Combinations` é uma tabela de nove colunas -- número, jogadores, local, ano, solução, o lance
    do Zarkov, a avaliação, a contagem de nós e o nível --, e lê-la como fluxo de tokens
    (`pagina.texto().split()`) achata as nove numa fila só. A caminhada crescente por número então
    ancora em avaliações e contagens de nós: `211`, `539` e `580` são o placar do motor de 1994 e
    entravam como número de exercício. Dos 24 exercícios que a primeira rodada produziu, **nenhum**
    dos 18 conferíveis batia com a tabela impressa -- o 213 saía `Qe4` onde o livro diz `Rxh7+`.

    **Nada é cravado: as colunas são detectadas na própria folha.** Cravar `x < 66` para o número e
    `x ≈ 182` para a solução funciona no livro em que se mediu e em nenhum outro -- e nem nele: a
    tabela desliza de folha para folha, e 258 das 971 fileiras estavam fora da faixa medida numa
    delas. Aqui a coluna do número é o agrupamento com mais células que são **só** um número, e as
    colunas de lance são as que estão à direita dela e em que `PARTE_DE_LANCES` das células casam
    com `notacao.LANCE`. Uma folha sem as duas devolve vazio, e o chamador lê pelo fluxo.

    **A coluna do Zarkov é a segunda leitura, e ela é de graça.** O livro imprime o lance duas
    vezes -- o do autor e o que o programa achou --, e onde a primeira sai ilegível a segunda
    costuma sair inteira. Elas são percorridas da esquerda para a direita, então a do autor vence
    quando as duas estão legíveis: é o gabarito do livro que se quer treinar.
    """
    if pagina is None:
        return {}
    celulas = [(bbox, texto) for bbox, texto in _candidatos_a_numero(pagina) if str(texto).strip()]
    if len(celulas) < FILEIRAS_MINIMAS:
        return {}
    alturas = sorted(max(0.0, bbox[3] - bbox[1]) for bbox, _ in celulas)
    altura = alturas[len(alturas) // 2]
    if altura <= 0:
        return {}

    colunas = _colunas_por_x(celulas, altura * FOLGA_DA_COLUNA)
    de_lance = sorted(
        (
            coluna
            for coluna in colunas
            if sum(1 for celula in coluna if lance_da_celula(celula[1]))
            >= max(FILEIRAS_MINIMAS, PARTE_DE_LANCES * len(coluna))
        ),
        key=lambda coluna: _x0(coluna[0]),
    )
    if not de_lance:
        return {}

    teto = altura * FOLGA_DA_FILEIRA
    limite = _x0(de_lance[0][0])
    melhor: dict[int, tuple[str, ...]] = {}
    marca: tuple[int, int, float] = (0, 0, 0.0)
    for coluna in colunas:
        fileiras = [
            celula
            for celula in coluna
            if _x0(celula) < limite and numero_da_celula(celula[1]) is not None
        ]
        if len(fileiras) < FILEIRAS_MINIMAS:
            continue
        achados = _fileiras_com_lance(fileiras, de_lance, teto)
        nota = (int(_conta_de_um_em_um(achados)), len(achados), -_x0(coluna[0]))
        if achados and nota > marca:
            melhor, marca = achados, nota
    return melhor


def _fileiras_com_lance(
    fileiras: Sequence[tuple[tuple[float, float, float, float], str]],
    de_lance: Sequence[Sequence[tuple[tuple[float, float, float, float], str]]],
    teto: float,
) -> dict[int, tuple[str, ...]]:
    achados: dict[int, tuple[str, ...]] = {}
    for celula in fileiras:
        numero = numero_da_celula(celula[1])
        if numero is None or numero in achados:
            continue
        lance = _lance_na_fileira(de_lance, _meio(celula), teto)
        if lance:
            achados[numero] = (lance,)
    return achados


def _conta_de_um_em_um(numeros: Iterable[int]) -> bool:
    """Esta coluna **conta**? Um livro numera de um em um; o ano salta de oito em oito (S-539).

    É o que separa a coluna do número da coluna do ano quando as duas são só dígitos e as duas
    estão à esquerda do lance -- o caso das cinco folhas do `Big Book` em que os primeiros números
    da lista são glifo e não texto, e a coluna do número fica quase vazia. A régua é a **mediana**
    da diferença entre dois números seguidos: 1 numa coluna que conta, mesmo com buracos de
    leitura, e 6 na coluna dos anos daquela folha (1840, 1848, 1850, 1852, 1858…).
    """
    ordenados = sorted(numeros)
    if len(ordenados) < 2:
        return False
    saltos = sorted(b - a for a, b in zip(ordenados, ordenados[1:], strict=False))
    return saltos[len(saltos) // 2] <= 1


def _lance_na_fileira(
    colunas: Sequence[Sequence[tuple[tuple[float, float, float, float], str]]],
    meio: float,
    teto: float,
) -> str:
    for coluna in colunas:
        for celula in coluna:
            if abs(_meio(celula) - meio) > teto:
                continue
            lance = lance_da_celula(celula[1])
            if lance:
                return lance
    return ""


def _tokens_da_folha(pagina: PaginaLida | None) -> list[str]:
    if pagina is None:
        return []
    return pagina.texto(com_marcas=False).split()


def _abre_entrada(token: str, alvo: int) -> bool:
    """Este token é o cabeçalho da entrada `alvo` da lista de soluções?

    `214.`, `214)` e `214` -- e é preciso aceitar o número **pelado** porque a segmentação de OCR
    perde o ponto com frequência. O que impede o estrago é o chamador: só se pergunta pelo próximo
    número esperado, e nunca por um número qualquer.
    """
    limpo = token.strip().strip("([{)]},;:")
    if limpo.endswith((".", ")")):
        limpo = limpo[:-1]
    # **`isdecimal` e não `isdigit`**, e isto derrubou a primeira medição de campo: `'³'.isdigit()`
    # responde verdadeiro -- expoentes são dígitos para o Unicode -- e o `int()` seguinte levanta
    # `ValueError` no meio da varredura de um livro inteiro. O `Big Book of Combinations` tem
    # expoentes na camada de texto, e uma exceção ali custa dez minutos de leitura.
    return limpo.isdecimal() and int(limpo) == alvo


def solucoes_da_folha(
    pagina: PaginaLida | None, esperados: Iterable[int]
) -> dict[int, tuple[str, ...]]:
    """As entradas da lista de soluções desta folha, entre as que foram pedidas (S-539).

    **Caminha pelos números esperados em ordem, e é isso que a torna robusta.** A alternativa --
    procurar `^\\d+\\.` -- acha os números de lance de dentro de cada solução: `214. Ahues - NN,
    1932. 1.Qxh7+!! Kxh7 2.Ng6+` tem quatro números e uma entrada só. Aqui o `1` só abriria entrada
    se `1` fosse o próximo exercício esperado, e ele não é: o anterior foi 213.

    A cauda de cada entrada é fatiada por `text/notacao.fatiar`, e o que sai é a **primeira fatia
    de lance**. O que vem antes dela é o nome dos jogadores e o ano, que o livro imprime junto; o
    que vem depois é a variante secundária entre parênteses, que não é o gabarito.

    Entrada sem lance nenhum não entra no resultado, e é essa condição que faz uma folha de
    **exercícios** -- onde os mesmos números estão impressos, sozinhos, embaixo dos diagramas --
    não ser lida como folha de soluções.
    """
    alvos = sorted({int(n) for n in esperados if 1 <= int(n) <= NUMERO_MAXIMO})
    if not alvos:
        return {}
    # **A tabela vence o fluxo, e quem decide é a folha.** `tabela_de_solucoes` só devolve alguma
    # coisa quando acha a coluna dos números e a do lance; onde ela devolve, a caminhada por token
    # está lendo a mesma tabela achatada -- e lendo errado, que foi o que a segunda rodada mediu.
    # Onde ela não devolve, a folha é prosa, e a caminhada é o que existe.
    da_tabela = tabela_de_solucoes(pagina)
    if da_tabela:
        return {numero: lance for numero, lance in da_tabela.items() if numero in set(alvos)}
    tokens = _tokens_da_folha(pagina)
    if not tokens:
        return {}

    cortes: list[tuple[int, int]] = []
    proximo = 0
    for posicao, token in enumerate(tokens):
        # **Só para a frente, e nunca para trás.** Um alvo que não aparece nesta folha não trava a
        # caminhada -- o próximo que casar leva a busca até ele --, e um número já usado não pode
        # abrir uma segunda entrada: é o que impede o `2.` de dentro da solução 2 de reabri-la.
        achou = next((i for i in range(proximo, len(alvos)) if _abre_entrada(token, alvos[i])), None)
        if achou is None:
            continue
        cortes.append((alvos[achou], posicao))
        proximo = achou + 1

    achados: dict[int, tuple[str, ...]] = {}
    for ordem, (numero, inicio) in enumerate(cortes):
        fim = cortes[ordem + 1][1] if ordem + 1 < len(cortes) else len(tokens)
        lance = _primeira_fatia_de_lance(tokens[inicio + 1 : fim])
        if lance:
            achados[numero] = lance
    return achados


def _primeira_fatia_de_lance(tokens: Sequence[str]) -> tuple[str, ...]:
    for fatia in notacao.fatiar(tokens):
        if fatia.e_lance:
            return tuple(tokens[fatia.inicio : fatia.fim])
    return ()


def linha_ao_lado(pagina: PaginaLida | None, indice: int) -> tuple[str, ...]:
    """A linha de lances impressa junto daquele diagrama, quando há uma (S-539).

    **É o gabarito dos livros que não têm lista no fim** -- o `Manual of Chess Combinations`
    escreve a combinação no parágrafo ao lado do Diagrama I, e o `Yusupov` a escreve embaixo. Dois
    caminhos, nesta ordem:

    1. o parágrafo que a leitura já **atou** ao diagrama (`BlocoDeTexto.legenda_de`, S-249);
    2. na falta dele, o primeiro parágrafo abaixo do diagrama, na mesma coluna, que
       `text/notacao.e_linha_de_notacao` reconheça como linha de lances.

    A segunda régua é a maioria de tokens de notação, e não "tem um lance": `Ivkov—Dueckstein 1967`
    traz um número que parece número de lance e continua sendo legenda. Ver o docstring de lá, que
    tem a medição.
    """
    if pagina is None:
        return ()
    caixa = _caixa_do_diagrama(pagina, indice)
    atados = [
        bloco
        for bloco in pagina.blocos
        if isinstance(bloco, BlocoDeTexto) and bloco.legenda_de == indice
    ]
    # **Identidade e não igualdade.** `BlocoDeTexto` é um `dataclass` congelado: dois parágrafos de
    # mesmo texto e mesma caixa são iguais para o `in`, e um `not in atados` por valor tiraria da
    # lista o bloco errado. Aqui o que se quer é "este objeto já entrou".
    ja_entraram = {id(bloco) for bloco in atados}
    candidatos = list(atados)
    if caixa is not None:
        abaixo = [
            bloco
            for bloco in pagina.blocos
            if isinstance(bloco, BlocoDeTexto)
            and id(bloco) not in ja_entraram
            and _sobrepoe(bloco.bbox, caixa)
            and bloco.bbox[1] >= caixa[1]
        ]
        candidatos += sorted(abaixo, key=lambda bloco: bloco.bbox[1])
    for bloco in candidatos:
        if notacao.e_linha_de_notacao(bloco.texto):
            return tuple(bloco.texto.split())
    return ()


# ---------------------------------------------------------------------------- a validação


def validar_solucao(placement: str, tokens: Sequence[str], *, vez: str = "") -> Solucao:
    """Joga a linha impressa sobre o diagrama, dos dois lados, e fica com o que ela sustenta.

    **É aqui que a solução decide o lado a jogar** (S-539). O diagrama de livro não diz de quem é
    a vez -- `semantics.infer_side_to_move` deduz pela legalidade e, quando as duas são legais,
    chuta brancas. A linha impressa é prova direta: `1.Qxh7+` não é legal com as pretas na vez, e
    uma linha de quatro lances que fecha de um lado e para no primeiro do outro não deixa dúvida.

    `vez` é o que o pipeline achou, e ela entra como **desempate** e não como ordem: quando os dois
    lados sustentam o mesmo tanto de linha -- o caso de uma linha de um lance simétrico --, o
    palpite anterior fica. Ignorá-lo ali seria trocar informação por moeda.

    O roque é inferido por `semantics.infer_castling_rights`, que é a decisão da S-05 e não uma
    segunda: um diagrama com rei em e1 e torres nos cantos aceita `O-O`, e é o que o livro imprime.
    """
    limpo = [str(t) for t in tokens if str(t).strip()]
    if not limpo:
        return Solucao(motivo="não há lance impresso nesta linha")

    preferido = "b" if str(vez).lower().startswith("b") else "w"
    tentativas: list[tuple[int, str, notacao.LinhaValidada]] = []
    for lado in (preferido, "b" if preferido == "w" else "w"):
        try:
            tabuleiro = chess.Board(
                compose_fen(placement, chess.WHITE if lado == "w" else chess.BLACK)
            )
        except (ValueError, AttributeError, TypeError, IndexError) as erro:
            return Solucao(motivo=f"a posição lida não é uma FEN válida ({erro})")
        validada = notacao.validar(limpo, tabuleiro)
        tentativas.append((len(validada.lances), lado, validada))

    melhor = max(tentativas, key=lambda item: item[0])
    if not melhor[0]:
        pior = tentativas[0][2]
        return Solucao(motivo=pior.motivo or "a linha impressa não tem lance", token=pior.token)
    # **O motivo vem junto mesmo quando houve lance**, e a linha parcial **vale**: numa lista de
    # soluções o que vem depois do gabarito é variante entre parênteses e sujeira de OCR, e parar
    # ali é ler certo. O que a recusa exige é zero lance, não linha inteira -- e o motivo fica
    # gravado para quem for conferir a leitura da folha.
    return Solucao(
        lances=melhor[2].san, vez=melhor[1], motivo=melhor[2].motivo, token=melhor[2].token
    )


def desfecho(fen: str, lances: Sequence[str]) -> str:
    """O que a solução faz com a posição: `MATE`, `GANHA_MATERIAL` ou `SEM_GANHO`.

    **`SEM_GANHO` não é recusa, e a razão está nos livros.** Metade das combinações termina com
    `+-` em vez de com a captura: o autor para quando a vantagem é evidente, e o material só chega
    depois. Um extrator que exigisse material a mais jogaria fora justamente as combinações
    posicionais -- e é por isso que este campo é uma etiqueta e não um filtro.

    O material é contado do ponto de vista de **quem começou**, com a tabela de `VALOR_DA_PECA`.
    Promoção conta: a dama que apareceu está no tabuleiro final.
    """
    try:
        tabuleiro = chess.Board(fen)
    except ValueError:
        return SEM_GANHO
    de_quem = tabuleiro.turn
    antes = _saldo(tabuleiro, de_quem)
    for san in lances:
        try:
            tabuleiro.push_san(str(san))
        except (chess.IllegalMoveError, chess.InvalidMoveError, chess.AmbiguousMoveError, ValueError):
            return SEM_GANHO
    if tabuleiro.is_checkmate():
        return MATE
    return GANHA_MATERIAL if _saldo(tabuleiro, de_quem) > antes else SEM_GANHO


def _saldo(tabuleiro: chess.Board, cor: chess.Color) -> int:
    return sum(
        VALOR_DA_PECA.get(peca.piece_type, 0) * (1 if peca.color == cor else -1)
        for peca in tabuleiro.piece_map().values()
    )


def confirmar(
    exercicio: Exercicio, avaliar: Callable[[chess.Board], tuple[int | None, int | None]]
) -> Exercicio:
    """Pergunta ao motor quanto o primeiro lance impresso perde, e etiqueta o exercício (S-539).

    **A régua é a da S-537, e é a mesma de propósito.** `analise_da_partida.julgar` já sabe medir
    o custo de um lance com o teto de dez peões e a regra da posição decidida; um segundo corte
    aqui discordaria dele no primeiro mate. Abaixo do corte de imprecisão -- meio peão -- o lance
    do livro é tão bom quanto o do motor, e é isso que `CONFIRMADA` afirma.

    **A discordância não apaga o gabarito.** Um livro de 1934 propõe combinações que o Stockfish
    refuta em vinte plies, e trocar a solução impressa pela linha do motor seria treinar o motor e
    não o livro. O que a marca faz é permitir separar as duas populações -- no relatório e na tela.

    `avaliar` devolve `(centipeões, mate)` do ponto de vista das brancas, que é o contrato de
    `engine.Evaluation`. Uma falha do motor deixa o exercício como estava: sem motor, a extração
    continua valendo.
    """
    if not exercicio.lances:
        return exercicio
    tabuleiro = exercicio.tabuleiro()
    brancas = bool(tabuleiro.turn)
    try:
        antes = regua.avaliacao_em_centipeoes(*avaliar(tabuleiro))
        tabuleiro.push_san(exercicio.primeiro)
        depois = regua.avaliacao_em_centipeoes(*avaliar(tabuleiro))
    except Exception as erro:  # noqa: BLE001 - o motor é binário de terceiro
        logger.warning("O motor não confirmou %s: %s", exercicio.chave, erro)
        return exercicio
    # **`julgar` e não um corte escrito aqui**: quem sabe onde fica a imprecisão é a S-537, e uma
    # cópia do número discordaria dela no dia em que alguém a ajustasse -- o que já aconteceu uma
    # vez, quando o juízo trocou de centipeões para expectativa de vitória. `julgar` traz junto o
    # teto de dez peões e a regra da posição já decidida, que valem aqui pelo mesmo motivo.
    perda, juizo = regua.julgar(antes, depois, brancas_jogaram=brancas)
    concorda = not juizo
    return replace(
        exercicio, motor=CONFIRMADA if concorda else DISCORDOU, perda_do_motor=perda
    )


# ------------------------------------------------------------------------------ a extração


SEM_NUMERO = "sem número impresso junto ao diagrama"
SEM_SOLUCAO = "o número não aparece em nenhuma lista de soluções"
SEM_FEN = "o diagrama não foi lido"


def extrair(folhas: Sequence[Folha], *, livro: str = "") -> Extracao:
    """Os exercícios de um livro inteiro, e os diagramas que ficaram de fora com o motivo (S-539).

    **Duas passadas, e a ordem é o item.** A primeira anda por todas as folhas juntando diagrama,
    número e a linha que estiver ao lado; a segunda relê **todas** as folhas procurando as entradas
    dos números que a primeira colecionou. Ela tem de ser a segunda porque a lista de soluções
    costuma estar no fim do livro -- e porque uma folha só é "de soluções" em relação a números que
    já foram vistos em outro lugar. Não há régua de "esta folha é a das soluções": há folhas que
    respondem por números pedidos, e folhas que não respondem por nenhum.

    Um número que apareça em duas listas fica com a **primeira** que o respondeu. Livros de duas
    línguas repetem a lista, e as duas dizem o mesmo lance.
    """
    pedidos: list[tuple[Folha, DiagramaLido, int | None, tuple[str, ...]]] = []
    numeros: set[int] = set()
    onde_esta_o_diagrama: dict[int, set[int]] = {}
    for folha in folhas:
        por_indice = numeros_da_folha(folha.texto, folha.diagramas)
        for diagrama in folha.diagramas:
            numero = por_indice.get(diagrama.indice)
            if numero is not None:
                numeros.add(numero)
                onde_esta_o_diagrama.setdefault(numero, set()).add(folha.pagina)
            pedidos.append((folha, diagrama, numero, linha_ao_lado(folha.texto, diagrama.indice)))

    listas: dict[int, tuple[int, tuple[str, ...]]] = {}
    for folha in folhas:  # noqa: B007 - o laço abaixo é o da segunda passada
        # **A folha do próprio diagrama não responde por ele**, e é o que separa as duas origens.
        # Numa folha de capítulo -- "Diagrama I" com a combinação escrita no parágrafo ao lado --
        # o número e os lances estão os dois ali, e a leitura da lista os casaria: o gabarito
        # sairia certo com a etiqueta errada, e a régua de dois meios-lances da vizinhança
        # (`PLIES_MINIMOS_AO_LADO`) deixaria de valer justamente onde ela existe para valer.
        faltam = [
            numero
            for numero in sorted(numeros)
            if numero not in listas and folha.pagina not in onde_esta_o_diagrama.get(numero, set())
        ]
        if not faltam:
            continue
        for numero, tokens in solucoes_da_folha(folha.texto, faltam).items():
            listas[numero] = (folha.pagina, tokens)

    exercicios: list[Exercicio] = []
    recusas: list[Recusa] = []
    for folha, diagrama, numero, ao_lado in pedidos:
        procedencia = Procedencia(
            livro=livro,
            pagina=folha.pagina,
            diagrama=diagrama.indice,
            numero=numero,
            folha_impressa=folha.folha_impressa,
        )
        if not str(diagrama.placement or "").strip():
            recusas.append(Recusa(procedencia, SEM_FEN))
            continue
        achado = _montar(diagrama, procedencia, numero, ao_lado, listas)
        if isinstance(achado, Exercicio):
            exercicios.append(achado)
        else:
            recusas.append(achado)
    return Extracao(tuple(exercicios), tuple(recusas), diagramas=len(pedidos))


def _montar(
    diagrama: DiagramaLido,
    procedencia: Procedencia,
    numero: int | None,
    ao_lado: tuple[str, ...],
    listas: Mapping[int, tuple[int, tuple[str, ...]]],
) -> Exercicio | Recusa:
    """A lista de soluções vence a linha ao lado, e o motivo é a força do vínculo.

    O número impresso ata o gabarito ao diagrama de forma explícita -- foi o autor quem o escreveu
    nos dois lugares. A vizinhança na página é inferência nossa, e ela é a que erra quando o livro
    põe a continuação da partida anterior embaixo do diagrama seguinte.
    """
    da_lista = listas.get(numero) if numero is not None else None
    if da_lista is not None:
        solucao = validar_solucao(diagrama.placement, da_lista[1], vez=diagrama.vez)
        if len(solucao.lances) >= PLIES_MINIMOS:
            return _exercicio(diagrama, procedencia, solucao, NO_FIM, da_lista[0])
        motivo_da_lista = solucao.motivo or "a solução impressa não fecha nesta posição"
    else:
        motivo_da_lista = SEM_SOLUCAO if numero is not None else SEM_NUMERO

    if ao_lado:
        solucao = validar_solucao(diagrama.placement, ao_lado, vez=diagrama.vez)
        if len(solucao.lances) >= PLIES_MINIMOS_AO_LADO:
            return _exercicio(diagrama, procedencia, solucao, AO_LADO, procedencia.pagina)
    return Recusa(procedencia, motivo_da_lista)


def _exercicio(
    diagrama: DiagramaLido,
    procedencia: Procedencia,
    solucao: Solucao,
    origem: str,
    folha_da_solucao: int,
) -> Exercicio:
    fen = compose_fen(diagrama.placement, chess.WHITE if solucao.vez == "w" else chess.BLACK)
    return Exercicio(
        fen=fen,
        lances=solucao.lances,
        procedencia=procedencia,
        origem=origem,
        folha_da_solucao=folha_da_solucao,
        desfecho=desfecho(fen, solucao.lances),
    )


# ------------------------------------------------------------------------- o adaptador de PDF


def de_pdf(
    caminho: Any,
    *,
    modelo: Any = None,
    inicio: int = 0,
    fim: int | None = None,
    dpi: int = 220,
    progresso: Callable[[int, int], None] | None = None,
    avaliar: Callable[[chess.Board], tuple[int | None, int | None]] | None = None,
) -> Extracao:
    """Varre o PDF e devolve os exercícios dele. **É adaptador, e não decisão** (S-539).

    Tudo o que ele faz é chamar o que já existe -- `pdf_to_pgn.scan_pdf_positions` para os
    diagramas e a FEN, `text/leitor.ler_pagina` para o texto -- e empacotar as duas metades em
    `Folha`. Os imports são tardios de propósito: casar texto com diagrama não pode custar `torch`
    a quem só quer testar o casamento.

    O motor de texto é a **camada do PDF** e não o de glifo, e é a única escolha desta função que
    tem consequência: a camada não representa figurina (ver `text/leitor.py`), então num livro que
    a use a solução chega mutilada. A alternativa custa a leitura de glifo de cada folha -- ordens
    de grandeza mais cara -- e este caminho existe para a varredura de um livro inteiro. Quem
    quiser a leitura boa passa as `Folha` prontas para `extrair`.
    """
    from .config import DEFAULT_MODEL_PATH
    from .pdf_io import opened
    from .pdf_to_pgn import scan_pdf_positions
    from .text.leitor import ler_pagina

    # **O caminho padrão do modelo, e não o do `OcrService`.** A varredura roda fora dele -- o
    # serviço está sob o lock da S-31 servindo à página exibida --, e carregar o classificador por
    # conta própria é o que `cvoff-scan` já faz.
    posicoes = scan_pdf_positions(
        caminho,
        Path(modelo) if modelo is not None else DEFAULT_MODEL_PATH,
        dpi=dpi,
        start_page=inicio,
        end_page=fim,
        read_text=True,
    )
    por_folha: dict[int, list[DiagramaLido]] = {}
    for posicao in posicoes:
        lado = posicao.side_to_move
        por_folha.setdefault(posicao.page_index, []).append(
            DiagramaLido(
                # **O `-1` é a conversão de base, e ela é o item da segunda rodada.**
                # `DiagramPosition.diagram_index` conta de 1 (é o que vai para o header `Diagram`
                # do PGN, onde `Round: 63.1` é o primeiro diagrama da folha 63); `PaginaLida`
                # conta de 0, como toda lista deste projeto. Ver `DiagramaLido.indice`.
                indice=posicao.diagram_index - 1,
                placement=posicao.fen,
                vez="" if lado is None else ("w" if lado.color == chess.WHITE else "b"),
            )
        )

    folhas: list[Folha] = []
    with opened(caminho) as livro:
        total = livro.page_count if fim is None else int(fim)
        for indice in range(int(inicio), min(total, livro.page_count)):
            if progresso is not None:
                progresso(indice - int(inicio) + 1, total - int(inicio))
            try:
                texto = ler_pagina(livro, indice, dpi=dpi, motor="camada")
            except Exception as erro:  # noqa: BLE001 - folha de PDF de origem desconhecida
                logger.warning("A folha %d não foi lida: %s", indice + 1, erro)
                texto = None
            folhas.append(
                Folha(pagina=indice, texto=texto, diagramas=tuple(por_folha.get(indice, ())))
            )
    achado = extrair(folhas, livro=str(caminho))
    if avaliar is None:
        return achado
    # **A confirmação é a última passada, e não uma opção decorativa** (S-539). Medido no
    # `Manual of Chess Combinations`, cuja camada de texto é um OCR quebrado: os 10 exercícios que
    # a extração produziu eram todos falsos -- linhas tiradas da fileira de coordenadas -- e o
    # motor recusou os 10, com perda mediana de 13,9 peões. É a diferença entre um relatório que
    # diz "2,4% de aproveitamento" e um que diz "2,4% de ruído".
    conferidos = []
    for ordem, exercicio in enumerate(achado.exercicios, start=1):
        if progresso is not None:
            progresso(ordem, len(achado.exercicios))
        conferidos.append(confirmar(exercicio, avaliar))
    return Extracao(tuple(conferidos), achado.recusas, diagramas=achado.diagramas)
