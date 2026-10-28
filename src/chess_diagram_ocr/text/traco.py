"""Ponto, hífen ou travessão, decidido pela **forma do box**.

Irmão de `text/caixa_alta.py` e de `text/marca_fina.py`, e pelo mesmo motivo de fundo: o recorte
que o classificador recebe é o **bbox apertado**, redimensionado para 32x32 sem guardar a
proporção. Lá o que se perdia era o tamanho e a posição; aqui é a **largura**, contra a altura do
próprio box e contra a escala da página.

    .  ponto        um quadrado cheio, 4x5 px a 220 dpi
    -  hífen        um retângulo deitado, 10x2
    —  travessão    o mesmo retângulo, mais comprido

Esticados para 32x32, os três são o mesmo quadrado preto. Duas decisões saem disso, e as duas vão
**num sentido só** -- o que foi medido:

- **o ponto**: o box mais alto que largo que o modelo leu como traço. No negrito do *Xadrez
  Vitorioso - Finais*, `2...Rd6` saía `2.——Rd6`, e `28.Ba6` saía `28—Ba6`;
- **o hífen**: o traço curto que o modelo leu como meia-risca ou travessão. `f4-f8-h4-f4` saía
  `f4—f8-h4—f4`, e numa página de tabela do Dvoretsky eram 298 hífens.

## O ponto, medido em 2026-10-25

Em 21 páginas de 7 livros, todo box que o classificador leu como traço (`-`, `–`, `—`, `_`):

    largura/altura      n     o que era
    >= 1,8             84     traço de verdade, todos
    0,7 a 1,0          48     ponto, todos do Seirawan, em lance -- `.` é a melhor não-traço
    outros              5     duas manchas de 2 px, que viram ponto; um `-+` fundido, um
                              traço em pé e um `v`, que ficam -- a melhor não-traço deles é
                              `-+`, `4` e `v`

**Nenhum traço de verdade tem o box mais alto que largo**, e o corte em 1,5 fica no meio do vão.
O box que não é traço vira o que o modelo põe logo depois dos traços -- **se** isso for o ponto:
trocar o `-+` grudado pela melhor classe que não é traço o deixaria `-+`, que é outro erro.

Conferido depois contra a camada em 60 páginas de 13 livros: das ~200 trocas, 92 caem num `.` da
camada, e **nenhuma** desfaz um caractere certo -- o box já saía traço, errado. O resto é sujeira
de 1x2 a 3x4 px, de figurina partida no Capablanca e de letra esfarelada no Kemeri: saía `—` e
sai `.`, errado dos dois jeitos. Um piso de tamanho não as separa do ponto de verdade, que no
*Secrets of Chess Training* mede 2x2.

## O hífen, medido em 2026-10-25

Cada box lido como traço casado com o caractere da camada **editorada** na mesma posição, em 36
páginas de 6 livros (Dvoretsky, 400 Quebra-cabeças, Capablanca, Fischer, Seirawan, Reinfeld). A
largura vai em unidades da escala de texto da página, que `segmentar` já mede:

    na camada       n     largura / escala
    hífen          806    0,33 a 0,62     o modelo leu `—` em 453 deles
    meia-risca      28    0,85 a 0,92     e `—` em 24

O corte em 0,75 fica no meio do vão. **O travessão de verdade não entra nesta tabela, e não por
escolha**: nesses livros ele some da linha antes de chegar ao classificador -- `toque final —
atrair` sai `toque final atrair`. Nos livros de camada de OCR, onde ele chega, mede de 1,5 a 2,2.

Três livros ficaram de fora da régua porque a camada deles é OCR e não serve de gabarito
(`Ddl—b3` por `Dd1-b3` no Kemeri), e dois porque a camada escreve `-` para todo traço.

**Meia-risca contra travessão não é decidida aqui.** O vão existe na tipografia (meia-risca é meio
eme, travessão um eme), mas não há travessão editorado medido para pôr o corte -- ver acima.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

PONTO = "."
"""O que o quadrado cheio é."""

HIFEN = "-"
"""O que o traço curto é."""

TRACOS = "-–—_"
"""As classes que são um retângulo deitado, e que o resize confunde com o ponto."""

LONGOS = "–—"
"""Os traços que o hífen não pode ser -- e que o modelo escolhia para ele."""

PROPORCAO_MINIMA = 1.5
"""Abaixo desta largura/altura, o box não é traço. Medido: o traço mais estreito tem 1,8, e o ponto
lido como traço vai até 1,0. O corte fica no meio do vão, e não colado numa das pontas."""

LARGURA_DO_HIFEN = 0.75
"""Abaixo desta largura, em escalas de texto da página, o traço é hífen. Medido contra a camada
editorada: o hífen vai até 0,62, a meia-risca começa em 0,85."""


def e_traco_pela_forma(largura: float, altura: float, *, corte: float | None = None) -> bool:
    """O box tem a forma de um traço -- mais largo que alto, pela margem medida?

    `corte=None` lê `PROPORCAO_MINIMA` **na hora da chamada**, e não na definição: a mesma lição de
    `caixa_alta.caixa_pela_altura` -- um limiar amarrado na assinatura faz varredura nenhuma variar.
    Box sem altura não é traço que se possa julgar, e responde `True` para não ser mexido.
    """
    if altura <= 0:
        return True
    return largura / altura >= (PROPORCAO_MINIMA if corte is None else corte)


def e_hifen_pela_largura(largura: float, escala: float, *, corte: float | None = None) -> bool:
    """O traço é curto o bastante para ser hífen? `False` sem escala, que não deixa julgar.

    `corte=None` lê `LARGURA_DO_HIFEN` na hora da chamada -- ver `e_traco_pela_forma`.
    """
    if escala <= 0:
        return False
    return largura / escala < (LARGURA_DO_HIFEN if corte is None else corte)


def corrigir(
    lidos: Sequence[tuple[str, float]],
    probs: np.ndarray,
    caixas: Sequence[object],
    idx_to_char: dict[int, str],
    *,
    escala: float = 0.0,
    corte: float | None = None,
    corte_do_hifen: float | None = None,
) -> list[tuple[str, float]]:
    """Devolve ao ponto o quadrado, e ao hífen o traço curto, que o modelo leu como outro traço.

    Devolve `(char, confiança)`. `escala=0` desliga a decisão do hífen -- é a escala de texto da
    página, e sem ela a largura não tem com que ser comparada.

    **As duas não disputam o mesmo box**: o ponto é decidido no box mais alto que largo, o hífen
    só no box que tem a forma de traço. Um `–` em pé de 7x20 -- que não é traço, e cuja melhor
    alternativa não é o ponto -- fica como está nas duas.

    A confiança devolvida é a da classe escolhida, e não a do traço recusado -- a regra de
    `marca_fina.corrigir`: trocar o caractere e manter a confiança do palpite descartado diria que o
    programa tem certeza de algo sobre o que acabou de mudar de ideia.

    Sem a classe de destino no modelo, aquela decisão devolve a entrada intacta.
    """
    if not lidos:
        return []
    ponto = next((i for i, c in idx_to_char.items() if c == PONTO), None)
    hifen = next((i for i, c in idx_to_char.items() if c == HIFEN), None)

    saida: list[tuple[str, float]] = []
    for k, (char, confianca) in enumerate(lidos):
        if char in TRACOS and k < len(caixas) and k < probs.shape[0]:
            caixa = caixas[k]
            largura = float(caixa.largura)  # type: ignore[attr-defined]
            altura = float(caixa.altura)  # type: ignore[attr-defined]
            if not e_traco_pela_forma(largura, altura, corte=corte):
                ordem = np.argsort(probs[k])[::-1]
                outra = next(
                    (int(i) for i in ordem if idx_to_char.get(int(i), TRACOS[0]) not in TRACOS), None
                )
                if ponto is not None and outra == ponto:
                    saida.append((PONTO, float(probs[k, ponto])))
                    continue
            elif (
                char in LONGOS
                and hifen is not None
                and e_hifen_pela_largura(largura, escala, corte=corte_do_hifen)
            ):
                saida.append((HIFEN, float(probs[k, hifen])))
                continue
        saida.append((char, confianca))
    return saida


__all__ = [
    "HIFEN",
    "LARGURA_DO_HIFEN",
    "LONGOS",
    "PONTO",
    "PROPORCAO_MINIMA",
    "TRACOS",
    "corrigir",
    "e_hifen_pela_largura",
    "e_traco_pela_forma",
]
