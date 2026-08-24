"""Texto impresso na vertical (S-197).

Livros de xadrez põem rótulos girados ao lado do diagrama -- *"Analysis diagram"* é o caso. Este é
**o caso mais perigoso da Fase 28**, e o motivo não é a frequência: os outros quatro fazem o texto
sumir, e este faz o programa **devolver outra letra com confiança de leitura normal**. Medido no
projeto de origem em 10.606 caracteres rotulados:

    o classificador no recorte de pé      94,2%
    o mesmo recorte girado 90°             8,4%

Não é falhar; é responder outra coisa, com a mesma origem e a mesma confiança de sempre.

## O ângulo é do texto, não do recorte

`Caixa.angulo` são graus **anti-horários do texto impresso**, a convenção do PDF:

    0    texto normal
    90   o texto sobe (lê-se de baixo para cima); o glifo saiu girado 90° AH
    270  o texto desce (lê-se de cima para baixo); o glifo saiu girado 90° H

Quem classifica não quer o recorte como está na página, quer o glifo **de pé** -- `endireitar`
faz essa volta num lugar só, para ninguém ter de refazer o raciocínio do sinal. E **girar por
múltiplo de 90° é transposição**, não reamostragem: medido, os mesmos 9.987 caracteres que o
modelo acerta de pé voltam a ser acertados depois de ir e voltar, um a um.

## A geometria propõe, o classificador dispõe

A geometria sozinha não distingue um rótulo girado de uma coluna de primeiras letras de parágrafo
-- as duas são caixas empilhadas com a mesma faixa de `x`. `candidatos` só recolhe pilhas
plausíveis, e quem decide o ângulo é o classificador, pela confiança **média da pilha inteira**.
Medido em 1.312 linhas simuladas nos quatro ângulos, o argmax da média bate com o ângulo impresso
em **99,7%** -- a única falha é um empate de 0,001.

**Sem árbitro este módulo não mexe em nada**, e isso é a lição de duas fases do projeto de origem:
separar glifo colado sem classificador que confirmasse custou 2,3 pontos de F1. Marcar ângulo por
geometria pura teria o mesmo defeito -- mexeria em texto normal para acertar o raro.

## 180° não é candidato

Livro impresso não traz linha de cabeça para baixo, e cada ângulo a mais é uma chance a mais de
virar uma pilha curta pelo lado errado. A medição mostra que o classificador *saberia* separar
180° (99,7% também); ele não entra por não existir no material, e não por não dar.
"""

from __future__ import annotations

import bisect
import logging
from collections.abc import Callable, Sequence

import numpy as np

from .boxes import Caixa

logger = logging.getLogger(__name__)

ANGULOS = (90, 270)
"""Os ângulos que esta fase reconhece. Ver "180° não é candidato" no cabeçalho."""

MIN_ITENS = 5
"""Mínimo de caixas para uma pilha ser candidata.

**Cinco, e o quinto foi comprado com medição.** Com quatro, 81 páginas reais sem nenhum texto
vertical produzem 5 pilhas aceitas por engano -- e as cinco são **colunas de peças dentro do
diagrama**, não texto. Uma coluna de quatro peças é pilha alta, estreita, encostada e de vão zero:
passa em toda a geometria, e com quatro amostras a média da confiança ainda é ruído.

Cinco não bastou sozinho: numa varredura de 322 páginas ainda sobravam três aceitas. Quem as
recusa é `_com_vizinho_lateral`."""

RAZAO_BBOX = 2.5
"""A pilha tem de ser bem mais alta que larga."""

SOBREPOSICAO_X = 0.55
"""Fração da menor largura que duas caixas vizinhas precisam ter em comum."""

VAO_MAXIMO = 0.8
"""Vão máximo entre letras vizinhas da pilha, em escalas de caractere.

É o joelho da curva, varrido em 81 páginas reais contra uma linha real colada girada: com 0,7 a
pilha colada sai partida (9 das 16 caixas) e com 0,9 as páginas normais passam a propor 554 pilhas
em vez de 103. Em 0,8 a pilha sai inteira e sobra ~1,3 candidata por página -- que o classificador
recusa."""

MARGEM = 0.05
"""Quanto a confiança média no ângulo escolhido precisa superar a do texto de pé.

A mediana da folga medida é 0,074; este valor é conservador de propósito -- **na dúvida, não
mexer**, porque mexer em texto de pé para acertar o raro é o defeito que a fase evita."""

COM_VIZINHO_LATERAL = 0.5
"""Fração das caixas da pilha que pode ter vizinho lateral de tamanho de caractere.

Acima disto a pilha não é palavra girada: é a coluna das primeiras letras de linhas seguidas.
**A diferença é estrutural** -- letra de linha horizontal tem vizinha ao lado; letra de linha
vertical tem vizinha em cima e embaixo."""


def _voltas(angulo: int) -> int:
    """Quantos giros anti-horários de 90° desfazem `angulo`."""
    resto = angulo % 360
    if resto == 90:
        return -1
    if resto == 270:
        return 1
    if resto == 180:
        return 2
    return 0


def endireitar(recorte: np.ndarray, angulo: int) -> np.ndarray:
    """O recorte com o glifo de pé, pronto para o classificador.

    Devolve array **contíguo**: `np.rot90` devolve uma vista de passo negativo, e o OpenCV recusa
    isso mais adiante no caminho.
    """
    voltas = _voltas(angulo)
    if voltas == 0:
        return recorte
    return np.ascontiguousarray(np.rot90(recorte, voltas))


def girar(imagem: np.ndarray, caixas: Sequence[Caixa], angulo: int) -> tuple[np.ndarray, list[Caixa]]:
    """A página como se o texto dela tivesse sido impresso em `angulo`. **O avesso de `endireitar`.**

    Existe para a medição do item: a tabela dos quatro ângulos precisa de linhas girada e o acervo
    só tem linhas de pé. Girar o que já se conhece é o único jeito de ter a resposta certa ao lado
    da leitura -- anotar texto girado à mão daria dezenas de amostras, e a régua precisa de
    milhares.

    Gira a imagem **e** as caixas, para que `caixa.recortar` continue pegando o mesmo glifo. É
    transposição, como `endireitar`: nenhum pixel é reamostrado, e por isso a ida e a volta fecham
    byte a byte.

    As caixas saem com `angulo=0`, e isso é deliberado: em produção ninguém sabe o ângulo antes de
    o classificador dizer, e uma simulação que já entregasse a resposta mediria outra coisa.
    """
    voltas = -_voltas(angulo)
    if voltas == 0:
        return imagem, [Caixa(c.x1, c.y1, c.x2, c.y2) for c in caixas]

    altura, largura = imagem.shape[:2]
    virada = np.ascontiguousarray(np.rot90(imagem, voltas))

    if voltas % 4 == 1:  # anti-horário: (x, y) -> (y, largura - 1 - x)
        novas = [Caixa(c.y1, largura - c.x2, c.y2, largura - c.x1) for c in caixas]
    elif voltas % 4 == 2:
        novas = [Caixa(largura - c.x2, altura - c.y2, largura - c.x1, altura - c.y1) for c in caixas]
    else:  # horário: (x, y) -> (altura - 1 - y, x)
        novas = [Caixa(altura - c.y2, c.x1, altura - c.y1, c.x2) for c in caixas]
    return virada, novas


def recorte_de_pe(imagem: np.ndarray, caixa: Caixa) -> np.ndarray:
    """O recorte da caixa na página, já desgirado. **O funil onde a volta acontece.**"""
    return endireitar(caixa.recortar(imagem), caixa.angulo)


def _mediana(valores: Sequence[int]) -> float:
    ordenados = sorted(valores)
    return float(ordenados[len(ordenados) // 2]) if ordenados else 0.0


def _com_vizinho_lateral(pilha: Sequence[Caixa], caracteres: Sequence[Caixa], mediana: float) -> float:
    """Fração das caixas da pilha que têm outro caractere **encostado ao lado**.

    Só contam vizinhas de tamanho de caractere -- a caixa do diagrama fica ao lado do rótulo que
    esta fase existe para ler, e ela não é vizinha de palavra.
    """
    identidades = {id(c) for c in pilha}
    alcance = max(4.0, mediana * 1.5)
    com = 0
    for caixa in pilha:
        for outra in caracteres:
            if id(outra) in identidades:
                continue
            sobreposicao = min(caixa.y2, outra.y2) - max(caixa.y1, outra.y1)
            if sobreposicao <= 0.5 * min(caixa.altura, outra.altura):
                continue
            if 0 <= outra.x1 - caixa.x2 <= alcance or 0 <= caixa.x1 - outra.x2 <= alcance:
                com += 1
                break
    return com / max(1, len(pilha))


def candidatos(caixas: Sequence[Caixa], *, min_itens: int | None = None) -> list[list[Caixa]]:
    """Pilhas verticais plausíveis -- **só geometria, sem classificador**.

    Uma pilha é uma cadeia de caixas de tamanho de caractere em que cada uma encosta na de baixo
    (vão pequeno) e divide com ela a faixa de `x`. Nada aqui afirma que a pilha é texto girado:
    quem afirma é `decidir_angulo`.

    Os limiares chegam por parâmetro **lido na chamada**, e não como valor padrão:
    `def f(x=MIN_ITENS)` congela a constante na definição, e quem ajusta o módulo para medir
    mexeria numa variável que ninguém mais lê.
    """
    minimo = MIN_ITENS if min_itens is None else min_itens
    if len(caixas) < minimo:
        return []

    mediana = _mediana([c.altura for c in caixas]) or 1.0
    piso, teto = mediana * 0.25, mediana * 3.0
    plausiveis = [c for c in caixas if piso <= c.altura <= teto and piso <= c.largura <= teto]
    if len(plausiveis) < minimo:
        return []

    plausiveis.sort(key=lambda c: (c.y1, c.x1))
    topos = [c.y1 for c in plausiveis]
    vao_max = max(2.0, mediana * VAO_MAXIMO)

    usados: set[int] = set()
    cadeias: list[list[Caixa]] = []

    for i in range(len(plausiveis)):
        if i in usados:
            continue
        cadeia = [i]
        usados.add(i)

        while True:
            atual = plausiveis[cadeia[-1]]
            lo = bisect.bisect_left(topos, int(atual.y2 - atual.altura * 0.3))
            hi = bisect.bisect_right(topos, int(atual.y2 + vao_max))

            melhor, menor_vao = None, None
            for j in range(lo, hi):
                if j in usados:
                    continue
                outra = plausiveis[j]
                comum = min(atual.x2, outra.x2) - max(atual.x1, outra.x1)
                if comum <= 0 or comum / max(1, min(atual.largura, outra.largura)) < SOBREPOSICAO_X:
                    continue
                vao = outra.y1 - atual.y2
                if menor_vao is None or vao < menor_vao:
                    melhor, menor_vao = j, vao

            if melhor is None:
                break
            cadeia.append(melhor)
            usados.add(melhor)

        if len(cadeia) < minimo:
            continue
        da_cadeia = [plausiveis[j] for j in cadeia]
        largura = max(c.x2 for c in da_cadeia) - min(c.x1 for c in da_cadeia)
        altura = max(c.y2 for c in da_cadeia) - min(c.y1 for c in da_cadeia)
        if altura < RAZAO_BBOX * max(1, largura):
            continue
        if _com_vizinho_lateral(da_cadeia, plausiveis, mediana) > COM_VIZINHO_LATERAL:
            continue
        cadeias.append(da_cadeia)

    return cadeias


Arbitro = Callable[[list[np.ndarray]], list[float]]
"""Recebe recortes já de pé e devolve a confiança de cada um. É o classificador da S-179.

Injetado, e não importado: este módulo não pode depender de `torch` para propor geometria, e a
medição precisa poder trocá-lo por um árbitro travado."""


def confianca_media(imagem: np.ndarray, pilha: Sequence[Caixa], angulo: int, arbitro: Arbitro) -> float:
    """A confiança média da pilha inteira, lida no ângulo dado. Ver o cabeçalho."""
    recortes = [endireitar(c.recortar(imagem), angulo) for c in pilha]
    recortes = [r for r in recortes if r.size]
    if not recortes:
        return 0.0
    confiancas = arbitro(recortes)
    return float(sum(confiancas) / len(confiancas)) if confiancas else 0.0


def decidir_angulo(imagem: np.ndarray, pilha: Sequence[Caixa], arbitro: Arbitro | None) -> int:
    """O ângulo do texto desta pilha. **`0` sempre que não houver árbitro** -- ver o cabeçalho.

    O vencedor precisa superar o texto de pé por `MARGEM`: na dúvida, não mexer.
    """
    if arbitro is None or not pilha:
        return 0

    de_pe = confianca_media(imagem, pilha, 0, arbitro)
    melhor_angulo, melhor = 0, de_pe
    for angulo in ANGULOS:
        media = confianca_media(imagem, pilha, angulo, arbitro)
        if media > melhor:
            melhor_angulo, melhor = angulo, media

    if melhor_angulo == 0 or melhor <= de_pe + MARGEM:
        return 0
    return melhor_angulo


def marcar(
    imagem: np.ndarray,
    caixas: Sequence[Caixa],
    arbitro: Arbitro | None,
    *,
    min_itens: int | None = None,
) -> list[Caixa]:
    """As caixas com o `angulo` preenchido nas pilhas que o classificador aceitou.

    **Sem árbitro devolve a entrada intacta**, e isso é o item: marcar ângulo por geometria pura
    mexeria em texto normal para acertar o raro.
    """
    if arbitro is None:
        return list(caixas)

    girada: dict[int, int] = {}
    for pilha in candidatos(caixas, min_itens=min_itens):
        angulo = decidir_angulo(imagem, pilha, arbitro)
        if angulo:
            logger.info("Pilha de %d caixas aceita como texto a %d graus.", len(pilha), angulo)
            for caixa in pilha:
                girada[id(caixa)] = angulo

    return [
        Caixa(c.x1, c.y1, c.x2, c.y2, girada[id(c)]) if id(c) in girada else c
        for c in caixas
    ]


__all__ = [
    "ANGULOS",
    "COM_VIZINHO_LATERAL",
    "MARGEM",
    "MIN_ITENS",
    "RAZAO_BBOX",
    "SOBREPOSICAO_X",
    "VAO_MAXIMO",
    "Arbitro",
    "candidatos",
    "confianca_media",
    "decidir_angulo",
    "endireitar",
    "girar",
    "marcar",
    "recorte_de_pe",
]
