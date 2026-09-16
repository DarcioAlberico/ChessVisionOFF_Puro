"""O recorte do diagrama ao lado do tabuleiro: casa ↔ pixel, as três leituras e a margem.

**Sem toolkit** (R3.2): tudo o que aqui se decide -- em que casa do recorte o ponteiro está, o
que a dica diz, que casas merecem âmbar -- é regra, e é afirmada em `tests/test_ui_recorte_do_diagrama.py`
sem abrir janela. A pintura mora em `qt/painel_de_recorte.py`.

**O problema que o recorte resolve** (OCR_UI_ANALISE §5.2, U1). Na aba Resultado o lado direito da
janela é a **página inteira**: para conferir uma casa a pessoa achava o diagrama na página, dava
zoom e voltava. O recorte é o diagrama como o classificador o viu -- `RecognizedDiagram.board_rgb`,
o tabuleiro retificado --, ampliado ao lado do tabuleiro editável, com a casa sob o ponteiro
espelhada nos dois e a leitura da casa numa dica.

**Âmbar por margem, e não por confiança.** A tinta de incerteza (S-21) tingia a casa cuja
confiança máxima ficava abaixo de `UNCERTAIN_SQUARE_THRESHOLD`. A margem -- a probabilidade da
classe vencedora **menos** a da segunda -- é o sinal que a análise do passo 8 nomeia como o mais
discriminante e o mais barato: uma casa a 0,60 contra 0,38 é uma casa em que o modelo hesitou entre
duas peças, e a segunda é quase sempre a resposta; uma casa a 0,85 com o resto espalhado por doze
classes é uma casa lida sem alternativa. A rampa de calor continua sendo a do produto
(`desenho_do_tabuleiro.heatmap_color`): âmbar no limiar, vermelho na moeda ao ar. Quando não há
matriz de probabilidades (item da fila, amostra do dataset), vale a régua antiga -- as casas
incertas que a origem trouxe.

O que a margem **não** é: p(exato) do diagrama. Isso é o passo 8, bloqueado pela população do
conjunto de campo (`OCR_UI_REPORT_C1.md` §4); até lá o âmbar diz "aqui o modelo hesitou", que é
verdade e é útil, e não diz "este diagrama está certo".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from chess_diagram_ocr.config import PIECE_CLASSES, UNCERTAIN_SQUARE_THRESHOLD
from chess_diagram_ocr.fen_utils import square_name
from chess_diagram_ocr.ui.board_edit import PIECE_NAMES_PT

__all__ = [
    "LIMIAR_DE_MARGEM",
    "Alternativa",
    "Tinta",
    "alternativas",
    "casa_em",
    "casas_ambar",
    "dica_da_casa",
    "e_duvidoso",
    "margem",
    "margens",
    "nome_da_classe",
    "retangulo_da_casa",
    "tinta_do_diagrama",
]

LIMIAR_DE_MARGEM = 0.5
"""Abaixo disto a casa fica âmbar: a segunda leitura tem mais da metade do peso da primeira.

**Por que 0,5, e não o 0,90 da confiança.** Com confiança máxima 0,90 a segunda classe tem no
máximo 0,10 -- margem ≥ 0,80 --, então toda casa "confiante" da régua antiga continua limpa aqui.
Do outro lado, margem 0,5 é `p1 = 0,70, p2 = 0,20` ou `p1 = 0,55, p2 = 0,05`: nas duas o modelo
está mais perto de hesitar do que de afirmar, e a peça alternativa é a que vale mostrar na dica.
É um limiar de tela, escolhido para o **olho**, e não um limiar de exportação -- este continua
sendo `ACCEPT_MIN_CONFIDENCE`, e o passo 8 é quem pode movê-lo com número."""

QUANTAS_ALTERNATIVAS = 3
"""As três leituras da dica: a que está na tela e as duas que perderam."""



@dataclass(frozen=True)
class Alternativa:
    """Uma leitura possível de uma casa: a classe e quanto o modelo apostou nela."""

    classe: str
    probabilidade: float

    @property
    def nome(self) -> str:
        return nome_da_classe(self.classe)


@dataclass(frozen=True)
class Tinta:
    """O que o tabuleiro e o recorte tingem: as casas, o quão quentes e a régua do limiar."""

    casas: tuple[int, ...]
    valores: tuple[float, ...]
    """Um valor por casa (64), na mesma escala do `limiar`; vazio quando a origem não os trouxe."""
    limiar: float
    por_margem: bool
    """Se a tinta é a da margem (há matriz) ou a da confiança (a régua antiga, sem matriz)."""


def nome_da_classe(classe: str) -> str:
    """`"Q"` → `"dama branca"`, `"empty"` → `"vazia"`. O que a dica escreve."""
    if classe == "empty":
        return "vazia"
    return PIECE_NAMES_PT.get(classe, classe)


def _linha(probs: Any, casa: int) -> np.ndarray | None:
    if probs is None or not 0 <= casa < 64:
        return None
    matriz = np.asarray(probs, dtype=float)
    if matriz.ndim != 2 or matriz.shape[0] != 64 or matriz.shape[1] < 2:
        return None
    return matriz[casa]


def alternativas(probs: Any, casa: int, quantas: int = QUANTAS_ALTERNATIVAS) -> tuple[Alternativa, ...]:
    """As `quantas` classes mais prováveis daquela casa, da maior para a menor. Vazio sem matriz."""
    linha = _linha(probs, casa)
    if linha is None:
        return ()
    ordem = np.argsort(linha)[::-1][: max(0, quantas)]
    return tuple(
        Alternativa(PIECE_CLASSES[int(indice)] if int(indice) < len(PIECE_CLASSES) else str(indice), float(linha[int(indice)]))
        for indice in ordem
    )


def margem(probs: Any, casa: int) -> float:
    """Vencedora menos segunda. `1.0` sem matriz: uma casa sem alternativa medida não hesita."""
    linha = _linha(probs, casa)
    if linha is None:
        return 1.0
    ordenada = np.sort(linha)[::-1]
    return float(max(0.0, ordenada[0] - ordenada[1]))


def margens(probs: Any) -> tuple[float, ...]:
    """As 64 margens, em ordem de leitura. Vazio sem matriz."""
    if _linha(probs, 0) is None:
        return ()
    return tuple(margem(probs, casa) for casa in range(64))


def casas_ambar(probs: Any, limiar: float = LIMIAR_DE_MARGEM) -> tuple[int, ...]:
    """As casas em que o modelo hesitou -- margem abaixo do limiar --, da mais apertada à menos."""
    valores = margens(probs)
    if not valores:
        return ()
    return tuple(sorted((casa for casa, valor in enumerate(valores) if valor < limiar), key=lambda c: valores[c]))


def tinta_do_diagrama(
    probs: Any,
    *,
    casas_incertas: Sequence[int] = (),
    confiancas: Sequence[float] = (),
    limiar_de_margem: float = LIMIAR_DE_MARGEM,
    limiar_de_confianca: float = UNCERTAIN_SQUARE_THRESHOLD,
) -> Tinta:
    """O que tingir neste diagrama: por margem quando há matriz, pela régua antiga quando não.

    **Uma decisão, dois clientes**: o tabuleiro editável e o recorte tingem as mesmas casas com a
    mesma rampa porque os dois recebem esta `Tinta`. Decidir em cada widget é como eles divergem.
    """
    valores = margens(probs)
    if valores:
        return Tinta(
            casas=casas_ambar(probs, limiar_de_margem),
            valores=valores,
            limiar=limiar_de_margem,
            por_margem=True,
        )
    return Tinta(
        casas=tuple(int(casa) for casa in casas_incertas if 0 <= int(casa) < 64),
        valores=tuple(float(valor) for valor in confiancas) if len(confiancas) == 64 else (),
        limiar=limiar_de_confianca,
        por_margem=False,
    )


def e_duvidoso(probs: Any, casas_incertas: Sequence[int] = (), limiar: float = LIMIAR_DE_MARGEM) -> bool:
    """Se o diagrama tem alguma casa que mereça olho -- o estado «duvidoso» da caixa na página.

    Pela margem quando há matriz; pelas casas incertas da origem quando não. É a mesma pergunta
    que `tinta_do_diagrama` responde casa a casa, resumida a sim ou não para a caixa.
    """
    return bool(tinta_do_diagrama(probs, casas_incertas=casas_incertas, limiar_de_margem=limiar).casas)


def dica_da_casa(casa: int, leituras: Sequence[Alternativa], folga: float | None = None) -> str:
    """O texto da dica sobre uma casa: o nome dela, as leituras e a margem.

    `e4 · dama branca 0,62 · bispo branco 0,31 · vazia 0,05 · margem 0,31`. Vírgula decimal
    porque a tela é em pt-BR; três casas nas probabilidades porque a diferença entre 0,999 e
    0,990 é a diferença entre casa certa e casa a conferir (`config.UNCERTAIN_SQUARE_THRESHOLD`).
    Sem leituras -- item da fila, amostra do dataset -- a dica é só o nome da casa.
    """
    partes = [square_name(casa)]
    partes.extend(f"{leitura.nome} {leitura.probabilidade:.3f}".replace(".", ",") for leitura in leituras)
    if folga is not None and leituras:
        partes.append(f"margem {folga:.2f}".replace(".", ","))
    return " · ".join(partes)


def casa_em(x: float, y: float, largura: float, altura: float, *, virado: bool = False) -> int | None:
    """Que casa (em ordem de leitura, 0 = a8) está sob o pixel `(x, y)` de um recorte `largura×altura`.

    O recorte é o tabuleiro retificado: oito colunas iguais por oito linhas iguais, sem margem.
    `virado` é o diagrama impresso de cabeça para baixo (`RecognizedDiagram.rotation == 180`): o
    classificador o leu girado, então a casa de leitura 0 está no canto **inferior direito** do
    recorte como impresso. Fora do recorte, `None`.
    """
    if largura <= 0 or altura <= 0 or not (0 <= x < largura and 0 <= y < altura):
        return None
    coluna = min(7, int(x * 8 / largura))
    linha = min(7, int(y * 8 / altura))
    if virado:
        linha, coluna = 7 - linha, 7 - coluna
    return linha * 8 + coluna


def retangulo_da_casa(
    casa: int, largura: float, altura: float, *, virado: bool = False
) -> tuple[float, float, float, float]:
    """`(x0, y0, x1, y1)` da casa no recorte. O inverso de `casa_em`, e afirmado como tal no teste."""
    if not 0 <= casa < 64:
        raise ValueError(f"Índice de casa fora do intervalo 0..63: {casa}")
    linha, coluna = divmod(casa, 8)
    if virado:
        linha, coluna = 7 - linha, 7 - coluna
    passo_x, passo_y = largura / 8.0, altura / 8.0
    return (coluna * passo_x, linha * passo_y, (coluna + 1) * passo_x, (linha + 1) * passo_y)
