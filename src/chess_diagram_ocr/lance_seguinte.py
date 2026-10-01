"""O lance seguinte como evidência sobre a posição (C11 do ciclo 2 OCR/UI).

`pdf_text` já lê a primeira linha de lances impressa **sob** o diagrama -- é de lá que sai o
lado a jogar pela numeração (passo 7) -- e `text.notacao.validar` já joga uma linha impressa
sobre uma posição. Ninguém devolvia a resposta à posição: quando o `...♛xe5` do Burgess p60
é ilegal na leitura, é porque a dama de e5 saiu branca (`Q`, a 1,00), e o lance prova a cor.

**O que este módulo faz, e só isto.** Joga o primeiro lance impresso na posição lida. Se
fecha, o sinal é `replicou=True`. Se não fecha **no primeiro lance**, tenta as segundas opções
do classificador nas casas de menor margem -- uma troca, depois duas -- e adota a troca quando
ela é **única** a fazer a linha fechar: a evidência é externa à matriz de probabilidades, e é
por isso que este reparo é de outra natureza que o de `decode.decode_constrained`, que só
sabe o que a matriz sabe.

**O que ele não faz.** Não inventa: as trocas vêm das segundas opções do modelo nas casas em
que ele hesitou, nunca de uma casa em que ele tinha certeza contra a qual só o lance fala
(`max_casas` limita às de menor margem). Não decide sozinho: duas trocas diferentes que fechem
a linha são um empate, e um empate não repara nada -- vai para a revisão como "ambíguo". E
não mente sobre a probabilidade: a casa trocada continua com a confiança da segunda opção em
`square_confidences`; o que muda é que `RecognizedDiagram.next_move_repairs` a nomeia, e o
gate de exportação (`field_eval`, `pdf_to_pgn`) julga a confiança das **outras** casas -- é o
que a análise chama de "contornar *reparado nunca exporta* sem mentir".

**A guarda contra o lance errado.** Uma linha de OCR pode ter o lance errado; um lance errado
que por acaso fecha com uma troca plausível seria um reparo inventado. Por isso a linha tem de
fechar **inteira até `min_lances`** (3 quando os tem): o segundo e o terceiro lances impressos
têm de continuar legais a partir da troca. Um lance solto errado raramente puxa dois certos.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

import chess
import numpy as np

from .config import PIECE_CLASSES
from .fen_utils import check_position, fen_from_class_indices
from .text.notacao import (
    RESULTADOS,
    RETICENCIA,
    LinhaValidada,
    _sem_envoltorio,
    e_numero_de_lance,
    peso_de_notacao,
    validar,
)

if TYPE_CHECKING:
    from .inference import BoardPrediction
    from .pdf_text import DiagramContext
    from .semantics import SideToMove

MAX_TROCAS = 2
"""Trocas no máximo: uma casa de cor trocada é o caso do campo; duas cobrem um rei recolorido
e a casa que o decodificador estragou a partir dele. Três já é reconstruir a posição."""

MAX_CASAS = 6
"""Casas candidatas: as de menor margem top-1/top-2. Seis é o teto para a busca de pares
(15 pares) continuar barata numa página de nove diagramas."""

MIN_LANCES = 3
"""Quantos lances impressos têm de fechar para a troca contar (ou todos, se a linha é mais
curta). É a guarda contra o lance de OCR errado que por acaso fecha."""

MIN_LANCES_PARA_REPARO = 2
"""Uma linha de um lance só confirma (`replicou=True`); para **trocar** uma casa ela tem de
imprimir pelo menos dois lances que fechem. Um lance solto que fecha com uma troca é evidência
fraca demais para mexer no que o modelo leu."""

MARGEM_HESITANTE = 0.90
"""Abaixo desta margem top-1/top-2 a segunda opção da casa é candidata, seja ela qual for. Acima,
o modelo não hesitou -- e a única troca que ainda faz sentido é a **cor** da mesma peça (`Q`↔`q`),
o erro de OCR que o campo mede (10 das 27 casas erradas, análise §3.1): um contorno lido como
preenchido. Trocar uma casa vazia a 0,99 por uma dama porque o lance fecharia seria inventar."""


@dataclass(frozen=True)
class ReparoPeloLance:
    """O que o primeiro lance impresso disse sobre a posição."""

    replicou: bool | None
    """`True`: a linha fecha na posição lida. `False`: não fecha, nem com trocas. `None`: não
    havia lance sob o diagrama, ou o lado a jogar não permite jogar (sem evidência)."""

    lance: str = ""
    """O primeiro lance impresso, como o livro o escreveu."""

    trocas: tuple[tuple[int, int, int], ...] = ()
    """`(casa em ordem de leitura, classe lida, classe adotada)` das trocas que fizeram a linha
    fechar. Vazio quando ela já fechava, ou quando nada a fez fechar."""

    placement: str = ""
    """O campo de peças depois das trocas (igual ao lido quando não há troca)."""

    motivo: str = ""
    """Em pt-BR, para o rodapé e para o PGN: por que replicou, o que trocou, ou por que não."""

    ambiguo: bool = False
    """Mais de uma troca fecha a linha: nenhuma foi adotada, e a revisão precisa olhar."""

    @property
    def casas(self) -> list[int]:
        return [casa for casa, _, _ in self.trocas]


def _tokens_de(linha: str) -> list[str]:
    return [token for token in str(linha or "").split() if token]


def _lances_impressos(tokens: list[str]) -> int:
    """Quantos lances a linha imprime **antes da prosa** -- o que `validar` pode conferir.

    Conta a corrida inicial de tokens de notação (`peso_de_notacao`), com o composto
    `19...♖g8` valendo um lance; a primeira palavra de prosa encerra a conta, e o que vem
    depois dela não é exigido de ninguém.
    """
    lances = 0
    for token in tokens:
        peso = peso_de_notacao(token)
        if peso == 0:
            break
        if peso == 2 or (not e_numero_de_lance(token) and not RETICENCIA.match(_sem_envoltorio(token))
                         and _sem_envoltorio(token) not in RESULTADOS):
            lances += 1
    return lances


def _tabuleiro(placement: str, turn: chess.Color, fullmove: int) -> chess.Board | None:
    try:
        board = chess.Board(f"{placement} {'w' if turn == chess.WHITE else 'b'} - - 0 {max(1, fullmove)}")
    except ValueError:
        return None
    return board


def _fecha(placement: str, turn: chess.Color, fullmove: int, tokens: list[str],
           exigidos: int) -> LinhaValidada | None:
    """A linha jogada sobre `placement`, quando fecha pelo menos `exigidos` lances."""
    board = _tabuleiro(placement, turn, fullmove)
    if board is None:
        return None
    if check_position(board.fen()).is_fatal:
        return None
    validada = validar(tokens, board)
    if len(validada.lances) >= exigidos:
        return validada
    return None


def _menor_margem(probs: np.ndarray, limite: int) -> list[int]:
    """As casas de menor margem top-1/top-2, da mais hesitante para a mais segura."""
    ordenadas = np.sort(probs, axis=1)
    margem = ordenadas[:, -1] - ordenadas[:, -2]
    return [int(casa) for casa in np.argsort(margem, kind="stable")[:limite]]


def _segunda(probs: np.ndarray, casa: int) -> int:
    ordem = np.argsort(probs[casa])[::-1]
    return int(ordem[1])


def _outra_cor(classe: int) -> int | None:
    """A mesma peça na outra cor (`Q` ↔ `q`); `None` para a casa vazia."""
    nome = PIECE_CLASSES[int(classe)]
    if nome == "empty":
        return None
    return PIECE_CLASSES.index(nome.swapcase())


def _candidatas(probs: np.ndarray, class_indices: list[int], max_casas: int) -> list[tuple[int, int]]:
    """As trocas `(casa, classe nova)` que a busca pode tentar, na ordem da hesitação.

    Casas hesitantes (margem < `MARGEM_HESITANTE`, até `max_casas`): a segunda opção. Toda casa
    ocupada: a outra cor da peça lida, quando ainda não está na lista.
    """
    ordenadas = np.sort(probs, axis=1)
    margem = ordenadas[:, -1] - ordenadas[:, -2]
    trocas: list[tuple[int, int]] = []
    vistas: set[tuple[int, int]] = set()
    for casa in _menor_margem(probs, max_casas):
        if margem[casa] >= MARGEM_HESITANTE:
            break
        segunda = _segunda(probs, casa)
        if segunda != class_indices[casa] and (casa, segunda) not in vistas:
            trocas.append((casa, segunda))
            vistas.add((casa, segunda))
    for casa in np.argsort(margem, kind="stable"):
        casa = int(casa)
        outra = _outra_cor(class_indices[casa])
        if outra is not None and (casa, outra) not in vistas:
            trocas.append((casa, outra))
            vistas.add((casa, outra))
    return trocas


def conferir(
    probs: np.ndarray,
    class_indices: list[int],
    *,
    linha: str,
    turn: chess.Color,
    fullmove: int = 1,
    max_trocas: int = MAX_TROCAS,
    max_casas: int = MAX_CASAS,
    min_lances: int = MIN_LANCES,
) -> ReparoPeloLance:
    """Joga a primeira linha impressa sobre a leitura e, se não fecha, procura a troca única.

    `probs` é a matriz (64, 13) do classificador e `class_indices` a leitura decidida (já com
    o reparo do decodificador, se houve); `linha` é o texto sob o diagrama que abre com lance
    numerado (`DiagramContext.first_moves_text`); `turn` e `fullmove` são o lado e o número
    que a página deu.
    """
    tokens = _tokens_de(linha)
    if not tokens:
        return ReparoPeloLance(None, motivo="nenhum lance impresso sob o diagrama")
    impressos = _lances_impressos(tokens)
    if impressos == 0:
        return ReparoPeloLance(None, motivo="nenhum lance impresso sob o diagrama")
    exigidos = min(min_lances, impressos)
    lance = next((token for token in tokens if not e_numero_de_lance(token)), tokens[0])

    placement = fen_from_class_indices(class_indices)
    fechada = _fecha(placement, turn, fullmove, tokens, exigidos)
    if fechada is not None:
        return ReparoPeloLance(True, lance=lance, placement=placement,
                               motivo=f"o lance impresso {lance!r} replica na posição lida")

    probs = np.asarray(probs, dtype=np.float64)
    if probs.shape != (64, len(PIECE_CLASSES)):
        return ReparoPeloLance(False, lance=lance, placement=placement,
                               motivo="sem matriz de probabilidades para tentar trocas")

    if impressos < MIN_LANCES_PARA_REPARO:
        return ReparoPeloLance(False, lance=lance, placement=placement,
                               motivo=f"o lance impresso {lance!r} não replica na posição lida "
                                      "(um lance só não basta para trocar uma casa)")
    candidatas = _candidatas(probs, list(class_indices), max_casas)
    base = list(class_indices)
    for tamanho in range(1, max(0, max_trocas) + 1):
        fecham: list[tuple[tuple[int, int, int], ...]] = []
        for escolha in combinations(candidatas, tamanho):
            if len({casa for casa, _ in escolha}) != tamanho:
                continue
            estado = list(base)
            trocas: list[tuple[int, int, int]] = []
            for casa, nova in escolha:
                trocas.append((casa, estado[casa], nova))
                estado[casa] = nova
            if _fecha(fen_from_class_indices(estado), turn, fullmove, tokens, exigidos) is not None:
                fecham.append(tuple(trocas))
        if len(fecham) == 1:
            trocas = fecham[0]
            estado = list(base)
            for casa, _de, para in trocas:
                estado[casa] = para
            reparado = fen_from_class_indices(estado)
            descricao = ", ".join(
                f"{_nome(casa)} {_letra(de)}→{_letra(para)}" for casa, de, para in trocas)
            return ReparoPeloLance(
                False, lance=lance, trocas=trocas, placement=reparado,
                motivo=f"o lance impresso {lance!r} só replica com {descricao}")
        if len(fecham) > 1:
            return ReparoPeloLance(
                False, lance=lance, placement=placement, ambiguo=True,
                motivo=f"o lance impresso {lance!r} replica com {len(fecham)} trocas diferentes: "
                       "nenhuma foi adotada")
    return ReparoPeloLance(False, lance=lance, placement=placement,
                           motivo=f"o lance impresso {lance!r} não replica na posição lida, "
                                  f"nem com até {max_trocas} troca(s) nas casas hesitantes")


def _nome(casa: int) -> str:
    return f"{'abcdefgh'[casa % 8]}{8 - casa // 8}"


def _letra(classe: int) -> str:
    nome = PIECE_CLASSES[int(classe)]
    return "·" if nome == "empty" else nome


def apply_next_move(
    prediction: BoardPrediction,
    context: DiagramContext | None,
    side: SideToMove,
) -> tuple[BoardPrediction, ReparoPeloLance | None]:
    """O lance seguinte devolvido à posição (C11): a leitura, trocada quando ele a prova.

    `None` quando a página não imprime lance sob o diagrama. Partilhado pela leitura da
    janela (`_predict_boards`) e pela exportação (`pdf_to_pgn`), para o PGN e a tela dizerem a
    mesma coisa -- o mesmo motivo da S-16.
    """
    from .inference import prediction_with_squares

    if context is None or not getattr(context, "first_moves_text", ""):
        return prediction, None
    numero = context.first_move_number[0] if context.first_move_number else 1
    reparo = conferir(
        prediction.probs,
        prediction.class_indices,
        linha=context.first_moves_text,
        turn=side.color,
        fullmove=numero,
    )
    if reparo.trocas:
        prediction = prediction_with_squares(prediction, reparo.trocas)
    return prediction, reparo
