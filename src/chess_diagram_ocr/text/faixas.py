"""Texto claro sobre faixa preta: achar a faixa e devolvê-la como tinta sobre papel (S-527).

**A queixa.** As páginas «Solutions» do `Yusupov - Build Up Your Chess` trazem o cabeçalho de
cada exercício -- «E.Jackson – D.Baird» -- em letras brancas sobre uma faixa preta. A camada de
texto do próprio PDF carrega «E. ackson» para ela, e o glifo não a lê: para `binarize` a faixa é
um bloco de tinta de 440 x 38 px, as letras são buracos nele, e nenhum contorno de caractere
sai dali. A folha 19 perde os nove cabeçalhos.

**O método é o da suíte** (`caissa.ocr.preprocess.find_reverse_bands`, absorvido em 2026-10-11),
em cinza e antes da binarização, por geometria física:

1.  Otsu, e um fechamento de 0,03 pol sobre a tinta engole os traços claros: a faixa vira **um**
    componente sólido; as letras de um título preto viram um borrão de palavra.
2.  Fica o componente **largo e baixo** (razão >= 2,5; altura entre 0,06 e 0,75 pol), **sólido**
    (>= 80 % da caixa depois do fechamento) e **escuro** (>= 55 % de tinta na caixa *antes* dele).
    Cada critério tira um vizinho: o título em negrito é largo e baixo, mas tem no máximo 45 % de
    tinta; o diagrama é metade escuro, mas quadrado; o filete é largo e escuro, mas tem menos de
    0,06 pol; a foto é escura, mas mais alta que 0,75 pol -- e inverter uma que não fosse não
    custaria nada que um leitor conseguisse ler de qualquer jeito.
3.  O **núcleo** da faixa vai da primeira à última linha inteiramente de tinta (>= 0,95 da
    largura): a faixa tem sempre uma entrelinha sólida acima e abaixo do texto, e a **franja**
    que o scanner deixa na borda é textura em toda parte (medido na folha 19: no máximo 0,85 na
    franja, 1,00 na entrelinha). O que sobra da caixa fora do núcleo é franja, e ela é apagada --
    deixada, vira depois da inversão uma tira de ruído que o leitor toma por uma linha. (As
    margens laterais sólidas, que foi a primeira régua, deixavam passar a última linha da franja,
    colada na faixa e sólida só nas pontas: invertida, ela virava «—» entre as letras.)
4.  Só os pixels da faixa são invertidos, não a caixa: a legenda colada embaixo («England – USA
    1896») continua tinta sobre papel. A borda serrilhada de 2 px em volta vai para papel, para
    não sobrar moldura que pareça sublinhado.

**Tudo é físico** (polegadas a `dpi`), para a mesma faixa sair a 150 e a 600 dpi. Por isso quem
chama tem de saber o DPI da imagem -- e por isso `segmentar` só liga isto quando recebe um: o
`cli/texto_colunas.py` chama sem DPI e continua lendo o que lia.

Medido na suíte sobre a folha 19 a 200 dpi: 9 de 9 faixas em 26 ms; o Tesseract de página
inteira passa de «EJackson» e «ECanal — iia» (com o lixo «~*» da franja) a «E.Jackson — D.Baird»
e «E.Canal — N.N.».
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

FAIXA_INVERTER = 1
"""Valor da máscara de `achar_faixas` nos pixels da faixa: é o que se inverte."""

FAIXA_FRANJA = 2
"""Valor da máscara na franja do scanner em volta da faixa: é o que se apaga."""


@dataclass(frozen=True)
class Faixa:
    """Uma faixa preta com texto claro, em pixels; `x2`/`y2` exclusivos, como fatia de numpy.

    `fracao_escura` é a parte da caixa que era tinta na entrada -- o número que a fez faixa e
    não palavra, guardado para o relatório dizer por quê."""

    x1: int
    y1: int
    x2: int
    y2: int
    fracao_escura: float

    @property
    def largura(self) -> int:
        return self.x2 - self.x1

    @property
    def altura(self) -> int:
        return self.y2 - self.y1

    def como_tupla(self) -> tuple[int, int, int, int]:
        return (self.x1, self.y1, self.x2, self.y2)


def _cinza(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return img


def _impar(valor: float, minimo: int = 3) -> int:
    k = max(minimo, int(round(valor)))
    return k if k % 2 == 1 else k + 1


def _limiar_de_otsu(cinza: np.ndarray) -> int:
    limiar, _ = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return int(limiar)


def _preencher_buracos(mascara: np.ndarray) -> np.ndarray:
    """Preenche todo buraco fechado de uma máscara 0/1 (os olhos das letras)."""
    altura, largura = mascara.shape
    acolchoada = np.zeros((altura + 2, largura + 2), dtype=np.uint8)
    acolchoada[1:-1, 1:-1] = mascara
    fora = (1 - acolchoada).astype(np.uint8)
    inundada = fora.copy()
    cv2.floodFill(inundada, np.zeros((altura + 4, largura + 4), dtype=np.uint8), (0, 0), 2)
    buracos = inundada == 1
    cheia = acolchoada.copy()
    cheia[buracos] = 1
    return cheia[1:-1, 1:-1]


def _nucleo(
    tinta_da_caixa: np.ndarray, margem_solida: float, linha_solida: float = 0.95, recuo: int = 2
) -> tuple[int, int]:
    """`(primeira, última)` linhas do núcleo da faixa: da primeira à última linha **inteiramente**
    de tinta (`linha_solida` da largura, recuados 2 px das pontas).

    A faixa tem sempre uma entrelinha de tinta sólida acima e abaixo do texto; a franja do
    scanner nunca chega a 0,85 (medido a 200 e a 220 dpi na folha 19). Só as margens laterais
    não bastavam: a última linha da franja, colada na faixa, é sólida nas pontas e textura no
    meio, e invertida ela virava um tracejado que o leitor lia como «—» entre as letras.

    Sem linha inteira nenhuma, valem as margens laterais (5 % da largura em cada ponta); sem
    margem sólida nenhuma, a caixa inteira: a faixa cujo texto vai até as pontas não tem
    margem para medir, e mantê-la inteira é a resposta inofensiva."""
    altura, largura = tinta_da_caixa.shape
    esquerda, direita = min(recuo, max(0, largura - 1)), max(largura - recuo, 0)
    if direita - esquerda < 8:
        return 0, altura - 1
    miolo = tinta_da_caixa[:, esquerda:direita]
    inteiras = np.flatnonzero(miolo.mean(axis=1) >= linha_solida)
    if inteiras.size:
        return int(inteiras[0]), int(inteiras[-1])
    m = max(4, round(0.05 * largura))
    if direita - esquerda < 2 * m:
        return 0, altura - 1
    margens = np.concatenate([miolo[:, :m], miolo[:, -m:]], axis=1)
    solidas = np.flatnonzero(margens.mean(axis=1) >= margem_solida)
    if solidas.size == 0:
        return 0, altura - 1
    return int(solidas[0]), int(solidas[-1])


def achar_faixas(
    imagem: np.ndarray,
    dpi: int = 220,
    *,
    largura_minima_pol: float = 0.6,
    altura_minima_pol: float = 0.06,
    altura_maxima_pol: float = 0.75,
    razao_minima: float = 2.5,
    fracao_escura_minima: float = 0.55,
    solidez_minima: float = 0.80,
    fechamento_pol: float = 0.03,
    margem_solida: float = 0.9,
) -> tuple[list[Faixa], np.ndarray]:
    """As faixas pretas com texto claro, e a máscara da página que diz o que fazer com cada pixel.

    `(faixas, mascara)`: na máscara, `FAIXA_INVERTER` marca os pixels da faixa com os buracos
    preenchidos -- exatamente o que se inverte -- e `FAIXA_FRANJA` a franja do scanner, que se
    apaga. O critério está no cabeçalho do módulo."""
    cinza = _cinza(imagem)
    altura, largura = cinza.shape[:2]
    vazia = np.zeros((altura, largura), dtype=np.uint8)
    if cinza.size == 0:
        return [], vazia
    limiar = _limiar_de_otsu(cinza)
    tinta = (cinza <= limiar).astype(np.uint8)
    if not tinta.any():
        return [], vazia
    k = _impar(fechamento_pol * dpi, 3)
    elemento = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    solida = cv2.morphologyEx(tinta, cv2.MORPH_CLOSE, elemento)
    total, rotulos, stats, _ = cv2.connectedComponentsWithStats(solida, connectivity=8)
    largura_minima = max(4, round(largura_minima_pol * dpi))
    altura_minima = max(3, round(altura_minima_pol * dpi))
    altura_maxima = max(altura_minima, round(altura_maxima_pol * dpi))
    faixas: list[Faixa] = []
    mascara = vazia
    for rotulo in range(1, total):
        x, y, w, h, area = (int(v) for v in stats[rotulo])
        if w < largura_minima or h < altura_minima or h > altura_maxima or w < razao_minima * h:
            continue
        if area < solidez_minima * w * h:
            continue
        tinta_da_caixa = tinta[y:y + h, x:x + w]
        fracao_escura = float(tinta_da_caixa.mean())
        if fracao_escura < fracao_escura_minima:
            continue
        componente = (rotulos[y:y + h, x:x + w] == rotulo).astype(np.uint8)
        cheia = _preencher_buracos(componente)
        # A abertura tira o que o fechamento colou na faixa e é mais fino que ela; o corpo
        # retangular sai inteiro de um elemento retangular.
        corpo = cv2.morphologyEx(cheia, cv2.MORPH_OPEN, elemento).astype(bool)
        if not corpo.any():
            continue
        primeira, ultima = _nucleo(tinta_da_caixa, margem_solida)
        # A primeira linha inteira ainda é a última da franja: 95 % de tinta são 5 % de
        # buracos, e invertida ela é um tracejado de 1 px que vira «—» entre as letras
        # (medido a 220 dpi: 48 componentes de 1 px de altura na linha 0 da faixa). A
        # entrelinha de tinta acima e abaixo do texto tem >= 0,04 pol; comer 0,012 pol de
        # cada ponta do núcleo tira o tracejado e não chega perto das letras.
        recorte = max(1, round(0.012 * dpi))
        if ultima - primeira + 1 > 4 * recorte:
            primeira += recorte
            ultima -= recorte
        # As pontas da faixa têm o mesmo serrilhado que a borda de cima e de baixo, e
        # invertido ele saía como um «—» ou um «r» no começo e no fim do cabeçalho; o
        # texto nunca encosta na ponta (há >= 0,1 pol de faixa de cada lado).
        esquerda, direita = recorte, w - recorte
        if mascara is vazia:
            mascara = vazia.copy()
        janela = mascara[y:y + h, x:x + w]
        franja = componente.astype(bool) & ~corpo
        franja[:primeira] |= corpo[:primeira]
        franja[ultima + 1:] |= corpo[ultima + 1:]
        franja[:, :esquerda] |= corpo[:, :esquerda]
        franja[:, direita:] |= corpo[:, direita:]
        corpo[:primeira] = False
        corpo[ultima + 1:] = False
        corpo[:, :esquerda] = False
        corpo[:, direita:] = False
        janela[franja] = FAIXA_FRANJA
        janela[corpo] = FAIXA_INVERTER
        faixas.append(Faixa(x + esquerda, y + primeira, x + direita, y + ultima + 1, fracao_escura))
    faixas.sort(key=lambda f: (f.y1, f.x1))
    return faixas, mascara


def desinverter_faixas(imagem: np.ndarray, dpi: int = 220, **criterios: Any) -> tuple[np.ndarray, list[Faixa]]:
    """A página em cinza com cada faixa de texto claro virada em texto escuro sobre papel.

    `(cinza, faixas)`. Sem faixa nenhuma volta **o mesmo array** que entrou (em cinza), e `saida is
    entrada` responde «nada aconteceu» sem comparar pixel. Só os pixels da faixa são invertidos;
    a franja e os 2 px de borda serrilhada em volta vão para papel."""
    cinza = _cinza(imagem)
    faixas, mascara = achar_faixas(cinza, dpi, **criterios)
    if not faixas:
        return cinza, []
    saida = cinza.copy()
    dentro = mascara == FAIXA_INVERTER
    saida[dentro] = 255 - cinza[dentro]
    borda = cv2.dilate(dentro.astype(np.uint8), np.ones((5, 5), dtype=np.uint8)).astype(bool) & ~dentro
    saida[borda | (mascara == FAIXA_FRANJA)] = 255
    return saida, faixas
