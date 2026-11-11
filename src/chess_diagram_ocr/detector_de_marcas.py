"""Acha as marcas de casa de um tabuleiro recortado pela forma, sem modelo.

**O que ele é.** A primeira opinião do dataset de marcas: sugere rótulos para uma pessoa confirmar e
é a base que o modelo de marcas vai precisar superar. Uma sugestão não vira rótulo sozinha, e o
detector não muda a FEN de ninguém.

**Como vê a marca.** A casa vazia típica é a mediana das casas da mesma cor no próprio tabuleiro. Ela
carrega a hachura, então a diferença contra ela cancela o fundo e deixa só o que foi impresso por
cima: peça, marca ou traço. Do maior borrão central saem as medidas da forma, e a forma decide:

- estrela: cinco pontas (`harmonico_5` do perfil radial), a regra do censo de 2026-10-24;
- bolinha: redonda, e lisa por dentro;
- X e cruz: tinta só ao longo das diagonais, ou só ao longo dos eixos.

Preenchida ou oca, branca ou preta, vem do brilho do miolo.

**O que ele não vê.** Só marca em casa sem peça: o que está sobre uma peça sai misturado com a peça.
Seta, reta e moldura atravessam casas e são outro problema. A bolinha oca em casa de hachura forte
também não foi medida: as reais que há são de hachura clara.

**Medido em 2026-11-04**, em recortes reais que não entram no repositório: 405 de 430 estrelas, 25 de
26 X, 7 de 7 cruzes, 9 de 12 pontos e 14 de 14 bolinhas ocas, sem falso alarme nos 58 tabuleiros do
gabarito. Em 19.370 amostras do dataset, 16 tabuleiros apontados, com 14 verdadeiros e 2 falsos: uma
peça de revista antiga, com o corpo em ampulheta, lida como X. A estrela branca não foi vista em
nenhum recorte real: só há desenho. Em 16.483 imagens de fora do dataset, 44 apontadas: nos livros
limpos, 28 de 28 verdadeiras; nas revistas antigas do jbc, 16 de 16 falsas (sujeira de impressão,
peças desbotadas). Nas revistas, a sugestão é mais ruído que ajuda. Ela só aparece e espera a pessoa.
Nos 43.389 diagramas dos PDFs, os 27 tabuleiros de estrela do Nunn foram apontados, os mesmos do censo
de outubro, embora nem toda estrela deles seja achada.

O módulo não importa Qt nem torch.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

import cv2
import numpy as np

from . import marcas_de_casa as mc
from .fen_utils import square_name

__all__ = ["MedidasDaCasa", "classificar", "medir_casas", "sugerir_marcas"]

LADO_DA_CASA = 80
"""O tabuleiro é medido a 640 px, seja qual for o recorte: os limiares valem em fração da casa."""

FOLGA_DE_ALINHAMENTO = 3
"""Quantos pixels a casa pode andar contra a casa típica: a grade do recorte nunca é exata."""

MARGEM_DA_CASA = 0.05
"""A faixa da borda da casa que não conta: é onde moram a moldura e as casas vizinhas."""

DIFERENCA_MINIMA = 45
"""A diferença de brilho, de 0 a 255, que conta como tinta nova sobre a casa típica."""

DESVIO_MAXIMO = 0.10
DESVIO_DA_ESTRELA = 0.18
"""Quanto a marca pode sair do centro, em fração da casa. A estrela aguenta mais: a forma dela é
inconfundível, e o recorte com a grade deslocada leva todas as estrelas do tabuleiro para o mesmo lado."""

ENCHIMENTO_DO_CIRCULO = 0.98
"""A área da forma contra a da elipse na caixa dela. Bolinhas reais: 0,91 a 0,97; a torre branca do
tema azul do *Chess Evolution*, que passa em todo o resto: 0,99 a 1,12."""

VARIACAO_DO_OCO = 12.0
"""O desvio de brilho até onde o miolo claro ainda é vazio. Verdadeiras: de 3 a 8; o bispo branco, ~39."""

LARGURA_DO_BRACO = 0.28
"""A meia largura da faixa de um braço do X ou da cruz, em fração da meia largura da forma."""

LADO_DO_MIOLO = 7
"""O que é mais fino que isto, em pixels da casa de 80, não é miolo de marca sólida: é hachura."""

_CASA_INTERNA = LADO_DA_CASA - 2 * FOLGA_DE_ALINHAMENTO


@dataclass(frozen=True)
class MedidasDaCasa:
    """A forma do borrão central de uma casa, em fração do lado da casa."""

    largura: float
    altura: float
    desvio_x: float
    desvio_y: float
    area: float
    solidez: float
    circularidade: float
    harmonico_5: float
    miolo_claro: bool
    variacao_do_miolo: float
    """O desvio de brilho por dentro da forma. Bolinha e estrela são lisas por dentro; peça não é."""
    tinta_nas_diagonais: float
    """A fração da tinta da forma ao longo das duas diagonais dela: quase toda, num X."""
    tinta_nos_eixos: float
    """A fração da tinta da forma ao longo do eixo vertical e do horizontal: quase toda, numa cruz."""
    menor_diagonal: float
    """A fração na diagonal menos pintada. Um traço solto da hachura pinta só uma; um X, as duas."""
    menor_eixo: float
    """A fração no eixo menos pintado: o mesmo, para a cruz."""
    centro_escuro: bool
    """Se o meio da forma tem tinta. Os braços do X e da cruz se cruzam ali; o da torre branca é claro."""
    toca_a_borda: bool
    outras_manchas: float
    """A área das outras manchas da casa, em relação à do borrão: marca limpa quase não tem."""


def _harmonico_5(contorno: np.ndarray) -> float:
    """O harmônico 5 do raio em função do ângulo, relativo ao raio médio: as cinco pontas da estrela."""
    pontos = contorno[:, 0].astype(np.float64)
    momentos = cv2.moments(contorno)
    if momentos["m00"] == 0:
        return 0.0
    cx, cy = momentos["m10"] / momentos["m00"], momentos["m01"] / momentos["m00"]
    angulos = np.degrees(np.arctan2(pontos[:, 1] - cy, pontos[:, 0] - cx)) % 360
    raios = np.hypot(pontos[:, 0] - cx, pontos[:, 1] - cy)
    faixas = np.full(120, np.nan)
    for faixa, raio in zip((angulos / 3).astype(int) % 120, raios, strict=True):
        faixas[faixa] = raio if np.isnan(faixas[faixa]) else max(faixas[faixa], raio)
    validas = ~np.isnan(faixas)
    if validas.sum() < 40:
        return 0.0
    eixo = np.arange(120)
    perfil = np.interp(eixo, eixo[validas], faixas[validas], period=120)
    espectro = np.fft.rfft(perfil) / len(perfil)
    return float(np.abs(espectro[5])) / max(float(np.abs(espectro[0])), 1e-6)


def _tinta_nos_bracos(tinta: np.ndarray, contorno: np.ndarray) -> tuple[float, float, float, float]:
    """Quanto da tinta na caixa da forma cai nas diagonais e nos eixos: junto, e no braço mais fraco."""
    x, y, w, h = cv2.boundingRect(contorno)
    caixa = tinta[y : y + h, x : x + w] > 0
    total = int(caixa.sum())
    if total == 0:
        return 0.0, 0.0, 0.0, 0.0
    linhas, colunas = np.mgrid[0:h, 0:w]
    u, v = (colunas - (w - 1) / 2) / max(w / 2, 1), (linhas - (h - 1) / 2) / max(h / 2, 1)
    descendo, subindo = np.abs(u - v) <= LARGURA_DO_BRACO, np.abs(u + v) <= LARGURA_DO_BRACO
    em_pe, deitado = np.abs(u) <= LARGURA_DO_BRACO, np.abs(v) <= LARGURA_DO_BRACO

    def fracao(faixa: np.ndarray) -> float:
        return float(caixa[faixa].sum()) / total

    return (
        fracao(descendo | subindo),
        fracao(em_pe | deitado),
        min(fracao(descendo), fracao(subindo)),
        min(fracao(em_pe), fracao(deitado)),
    )


def _medir(tinta: np.ndarray, celula: np.ndarray, limiar_do_miolo: float) -> MedidasDaCasa | None:
    """As medidas do borrão central da máscara, ou `None` quando ela não tem tinta."""
    lado = tinta.shape[0]
    corte = max(round(LADO_DA_CASA * MARGEM_DA_CASA) - FOLGA_DE_ALINHAMENTO, 0)
    tinta = tinta[corte : lado - corte, corte : lado - corte]
    interna = tinta
    contornos, _ = cv2.findContours(tinta, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contornos = [c for c in contornos if cv2.contourArea(c) >= (0.08 * LADO_DA_CASA) ** 2]
    if not contornos:
        return None
    meio = (interna.shape[0] - 1) / 2

    def distancia_ao_meio(contorno: np.ndarray) -> float:
        x, y, w, h = cv2.boundingRect(contorno)
        return float(np.hypot(x + w / 2 - meio, y + h / 2 - meio))

    contorno = min(contornos, key=lambda c: distancia_ao_meio(c) - 0.5 * float(np.sqrt(cv2.contourArea(c))))
    x, y, w, h = cv2.boundingRect(contorno)
    area = float(cv2.contourArea(contorno))
    casca = max(float(cv2.contourArea(cv2.convexHull(contorno))), 1.0)
    perimetro = max(float(cv2.arcLength(contorno, closed=True)), 1.0)
    harmonico_5 = _harmonico_5(contorno)

    cheio = np.zeros(interna.shape, np.uint8)
    cv2.drawContours(cheio, [contorno], -1, 1, thickness=cv2.FILLED)
    raio_interno = max(1, round(min(w, h) * 0.18))
    nucleo = cv2.erode(cheio, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * raio_interno + 1,) * 2))
    pixels_do_nucleo = celula[corte : lado - corte, corte : lado - corte][nucleo > 0]
    miolo_claro = bool(pixels_do_nucleo.size) and float(np.median(pixels_do_nucleo)) >= limiar_do_miolo
    variacao = float(pixels_do_nucleo.std()) if pixels_do_nucleo.size else 255.0
    nas_diagonais, nos_eixos, menor_diagonal, menor_eixo = _tinta_nos_bracos(tinta, contorno)
    celula_interna = celula[corte : lado - corte, corte : lado - corte]
    meio_x, meio_y, raio = x + w // 2, y + h // 2, max(1, round(min(w, h) * 0.05))
    centro = celula_interna[max(meio_y - raio, 0) : meio_y + raio + 1, max(meio_x - raio, 0) : meio_x + raio + 1]
    centro_escuro = bool(centro.size) and float(np.median(centro)) < limiar_do_miolo
    outras = sum(float(cv2.contourArea(c)) for c in contornos if c is not contorno)

    return MedidasDaCasa(
        largura=w / LADO_DA_CASA,
        altura=h / LADO_DA_CASA,
        desvio_x=(x + w / 2 - meio) / LADO_DA_CASA,
        desvio_y=(y + h / 2 - meio) / LADO_DA_CASA,
        area=area / LADO_DA_CASA**2,
        solidez=area / casca,
        circularidade=4 * np.pi * area / perimetro**2,
        harmonico_5=harmonico_5,
        miolo_claro=miolo_claro,
        variacao_do_miolo=variacao,
        tinta_nas_diagonais=nas_diagonais,
        tinta_nos_eixos=nos_eixos,
        menor_diagonal=menor_diagonal,
        menor_eixo=menor_eixo,
        centro_escuro=centro_escuro,
        toca_a_borda=x == 0 or y == 0 or x + w >= interna.shape[1] or y + h >= interna.shape[0],
        outras_manchas=outras / max(area, 1.0),
    )


def _casa_tipica(celulas: list[np.ndarray], paridade: int) -> np.ndarray:
    """A casa vazia desta cor: a mediana das casas de centro mais liso, e não a de todas.

    A mediana de todas vira estrela no diagrama com 20 estrelas na mesma cor, e aí a estrela se cancela
    contra ela mesma. Hachura tem variação pequena e igual em todas as casas vazias; peça e marca têm
    variação grande no centro.
    """
    meio = LADO_DA_CASA // 4
    casas = [celulas[casa] for casa in range(64) if (casa // 8 + casa % 8) % 2 == paridade]
    casas.sort(key=lambda celula: float(celula[meio:-meio, meio:-meio].std()))
    return np.median(np.stack(casas[: max(3, len(casas) // 4)]), axis=0).astype(np.uint8)


def medir_casas(tabuleiro_rgb: np.ndarray) -> list[MedidasDaCasa | None]:
    """As medidas das 64 casas, na ordem de leitura. `None` é casa igual à casa típica."""
    cinza = cv2.cvtColor(tabuleiro_rgb, cv2.COLOR_RGB2GRAY)
    lado = 8 * LADO_DA_CASA
    cinza = cv2.resize(cinza, (lado, lado), interpolation=cv2.INTER_AREA)
    cinza = cv2.GaussianBlur(cinza, (3, 3), 0.8)
    celulas = [
        cinza[fila * LADO_DA_CASA : (fila + 1) * LADO_DA_CASA, coluna * LADO_DA_CASA : (coluna + 1) * LADO_DA_CASA]
        for fila in range(8)
        for coluna in range(8)
    ]
    tipicas = {paridade: _casa_tipica(celulas, paridade) for paridade in (0, 1)}
    papel, tinta = np.percentile(np.asarray(cinza), 90), np.percentile(np.asarray(cinza), 2)
    limiar_do_miolo = (float(papel) + float(tinta)) / 2

    medidas: list[MedidasDaCasa | None] = []
    f = FOLGA_DE_ALINHAMENTO
    for casa, celula in enumerate(celulas):
        tipica = tipicas[(casa // 8 + casa % 8) % 2]
        interna = celula[f:-f, f:-f]
        custos = cv2.matchTemplate(tipica, interna, cv2.TM_SQDIFF)
        _, _, (dx, dy), _ = cv2.minMaxLoc(custos)
        alinhada = tipica[dy : dy + _CASA_INTERNA, dx : dx + _CASA_INTERNA]
        diferenca = interna.astype(np.int16) - alinhada.astype(np.int16)
        medidas.append(_melhor_medida(diferenca, interna, limiar_do_miolo))
    return medidas


def _mascara_da_diferenca(diferenca: np.ndarray) -> np.ndarray:
    """O que mudou contra a casa típica. Enxerga traço fino, como a bolinha oca e o X."""
    return cv2.morphologyEx(
        (np.abs(diferenca) > DIFERENCA_MINIMA).astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    )


def _mascara_solida(celula: np.ndarray, limiar_do_miolo: float) -> np.ndarray:
    """A tinta grossa e o que encosta nela: a estrela e a bolinha pretas, sem a hachura em volta.

    A hachura muda de fase de uma casa para outra e a casa típica não a cancela, mas ela é fina. O
    miolo que sobrevive à abertura é a marca, e crescer dele de volta só dentro da tinta devolve as
    pontas da estrela sem trazer a hachura junto.
    """
    tinta = (celula < limiar_do_miolo).astype(np.uint8)
    miolo = cv2.morphologyEx(tinta, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (LADO_DO_MIOLO,) * 2))
    crescido = cv2.dilate(miolo, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (LADO_DO_MIOLO,) * 2))
    return np.bitwise_and(np.asarray(crescido), tinta)


def _melhor_medida(diferenca: np.ndarray, celula: np.ndarray, limiar_do_miolo: float) -> MedidasDaCasa | None:
    """A primeira leitura que dá marca: a da diferença, e depois a da tinta grossa.

    A da tinta grossa não vale para a cruz: ela reduz a um miolo qualquer coisa com tinta, e aí o
    cruzamento das linhas de uma grade vira cruz.
    """
    primeira = _medir(_mascara_da_diferenca(diferenca), celula, limiar_do_miolo)
    if primeira is None or classificar(primeira) is not None:
        return primeira
    solida = _medir(_mascara_solida(celula, limiar_do_miolo), celula, limiar_do_miolo)
    if solida is not None and classificar(solida) in (mc.ESTRELA_PRETA, mc.BOLINHA_PRETA, mc.X):
        return solida
    return primeira


PROPORCAO_MAXIMA = 1.25
"""Lado maior sobre lado menor da forma, acima do qual ela não é marca: as marcas são redondas ou quadradas."""

LADO_MINIMO = 0.14
LADO_MAXIMO = 0.72
"""O lado maior da forma, em fração da casa. O X só tem o mínimo: os dos livros chegam a 90% da casa."""

OUTRAS_MANCHAS_MAXIMAS = 0.25
"""A área das outras manchas da casa contra a do borrão, acima da qual a casa está suja demais."""

SOLIDEZ_DOS_BRACOS = 0.72
"""Abaixo disto a forma é de braços, o X e a cruz: a tinta não enche a casca convexa."""

DIAGONAIS_DO_X = 0.75
EIXOS_DA_CRUZ = 0.85
"""A fração da tinta ao longo das duas diagonais (X) ou dos dois eixos (cruz)."""

BRACO_MAIS_FRACO = 0.4
"""A fração mínima no braço menos pintado: um traço solto da hachura pinta um braço só."""

HARMONICO_DA_ESTRELA = 0.13
SOLIDEZ_DA_ESTRELA = (0.55, 0.85)
"""As cinco pontas (`harmonico_5`) e a faixa de solidez da estrela: entre os braços e o disco."""

EIXOS_DA_ESTRELA_PRETA = 0.62
"""A tinta mínima nos eixos da estrela preta, que é cheia; a oca é julgada pelo miolo liso."""

SOLIDEZ_DO_DISCO = 0.9
"""A partir daqui a forma é cheia: a bolinha."""

CIRCULARIDADE_DA_BOLINHA_BRANCA = 0.85
CIRCULARIDADE_DA_BOLINHA_PRETA = 0.72

EIXOS_DA_BOLINHA_BRANCA = 0.53
"""A tinta máxima nos eixos da bolinha oca: o miolo dela é vazio."""

EIXOS_DA_BOLINHA_PRETA = 0.55
"""A tinta mínima nos eixos da bolinha cheia."""


@dataclass(frozen=True)
class _Forma:
    """O que as regras de forma olham: o lado maior, o menor e o desvio do centro, em fração da casa."""

    maior: float
    menor: float
    desvio: float


def _forma(medidas: MedidasDaCasa) -> _Forma:
    return _Forma(
        maior=max(medidas.largura, medidas.altura),
        menor=min(medidas.largura, medidas.altura),
        desvio=max(abs(medidas.desvio_x), abs(medidas.desvio_y)),
    )


def _desproporcional(medidas: MedidasDaCasa, forma: _Forma) -> bool:
    return forma.menor <= 0 or forma.maior / forma.menor > PROPORCAO_MAXIMA


def _tem_as_duas_diagonais(medidas: MedidasDaCasa, forma: _Forma) -> bool:
    return (
        forma.maior >= LADO_MINIMO
        and medidas.solidez < SOLIDEZ_DOS_BRACOS
        and medidas.tinta_nas_diagonais >= DIAGONAIS_DO_X
        and medidas.menor_diagonal >= BRACO_MAIS_FRACO
        and medidas.centro_escuro
        and forma.desvio <= DESVIO_MAXIMO
    )


def _na_borda_ou_suja(medidas: MedidasDaCasa, forma: _Forma) -> bool:
    return medidas.toca_a_borda or medidas.outras_manchas > OUTRAS_MANCHAS_MAXIMAS


def _fora_do_tamanho(medidas: MedidasDaCasa, forma: _Forma) -> bool:
    return not LADO_MINIMO <= forma.maior <= LADO_MAXIMO


def _tem_cinco_pontas(medidas: MedidasDaCasa, forma: _Forma) -> bool:
    minima, maxima = SOLIDEZ_DA_ESTRELA
    return (
        medidas.harmonico_5 >= HARMONICO_DA_ESTRELA
        and minima <= medidas.solidez <= maxima
        and forma.desvio <= DESVIO_DA_ESTRELA
    )


def _fora_do_centro(medidas: MedidasDaCasa, forma: _Forma) -> bool:
    return forma.desvio > DESVIO_MAXIMO


def _e_cheia(medidas: MedidasDaCasa, forma: _Forma) -> bool:
    return medidas.solidez >= SOLIDEZ_DO_DISCO


def _tem_os_dois_eixos(medidas: MedidasDaCasa, forma: _Forma) -> bool:
    return (
        medidas.solidez < SOLIDEZ_DOS_BRACOS
        and medidas.tinta_nos_eixos >= EIXOS_DA_CRUZ
        and medidas.menor_eixo >= BRACO_MAIS_FRACO
        and medidas.centro_escuro
    )


def _nenhuma(medidas: MedidasDaCasa) -> str | None:
    return None


def _x(medidas: MedidasDaCasa) -> str | None:
    return mc.X


def _cruz(medidas: MedidasDaCasa) -> str | None:
    return mc.CRUZ


def _estrela(medidas: MedidasDaCasa) -> str | None:
    """A variante pelo centro claro: a oca tem o miolo liso, a cheia tem tinta nos eixos."""
    if medidas.miolo_claro:
        return mc.ESTRELA_BRANCA if medidas.variacao_do_miolo <= VARIACAO_DO_OCO else None
    return mc.ESTRELA_PRETA if medidas.tinta_nos_eixos >= EIXOS_DA_ESTRELA_PRETA else None


def _bolinha(medidas: MedidasDaCasa) -> str | None:
    """A variante pelo centro claro. A oca precisa ser redonda e vazia: é o que a separa do bispo branco."""
    if medidas.miolo_claro:
        # Cantos enchem mais que a elipse da caixa: é o que separa a torre branca do círculo.
        elipse = np.pi / 4 * medidas.largura * medidas.altura
        redonda = medidas.circularidade >= CIRCULARIDADE_DA_BOLINHA_BRANCA and medidas.area / elipse <= ENCHIMENTO_DO_CIRCULO
        vazia = medidas.variacao_do_miolo <= VARIACAO_DO_OCO and medidas.tinta_nos_eixos <= EIXOS_DA_BOLINHA_BRANCA
        return mc.BOLINHA_BRANCA if redonda and vazia else None
    cheia = medidas.circularidade >= CIRCULARIDADE_DA_BOLINHA_PRETA and medidas.tinta_nos_eixos >= EIXOS_DA_BOLINHA_PRETA
    return mc.BOLINHA_PRETA if cheia else None


class _Regra(NamedTuple):
    nome: str
    vale: Callable[[MedidasDaCasa, _Forma], bool]
    tipo: Callable[[MedidasDaCasa], str | None]


_REGRAS = (
    _Regra("proporção", _desproporcional, _nenhuma),
    # O X vem antes da borda e do tamanho: ele pode tocar a borda, os dos livros chegam a 90% da
    # casa. As duas diagonais já bastam.
    _Regra("x", _tem_as_duas_diagonais, _x),
    _Regra("borda ou sujeira", _na_borda_ou_suja, _nenhuma),
    _Regra("tamanho", _fora_do_tamanho, _nenhuma),
    _Regra("estrela", _tem_cinco_pontas, _estrela),
    _Regra("fora do centro", _fora_do_centro, _nenhuma),
    _Regra("bolinha", _e_cheia, _bolinha),
    _Regra("cruz", _tem_os_dois_eixos, _cruz),
)
"""As regras de `classificar`, na ordem: a primeira que vale decide, e nenhuma valer é `None`.

Primeiro as de forma -- proporção, borda, tamanho --, com o X entre elas; depois a família pela
faixa de solidez: estrela no meio (com as cinco pontas), bolinha cheia em cima, cruz embaixo. A
família decide sozinha: uma estrela que não passa na variante é `None`, e não vira bolinha.
"""


def classificar(medidas: MedidasDaCasa) -> str | None:
    """O tipo da marca pela forma, ou `None` quando não parece marca: peça, traço ou sujeira.

    Os limites saíram de 2026-11-04: as marcas verdadeiras do gabarito (51 tabuleiros de outubro e 7
    enviados) contra as peças que uma versão sem eles apontava em 19 mil amostras. Silhueta sozinha
    não basta: a do bispo branco é tão redonda quanto a de uma bolinha, e o que os separa é o miolo.
    As regras estão em `_REGRAS`.
    """
    forma = _forma(medidas)
    regra = next((regra for regra in _REGRAS if regra.vale(medidas, forma)), None)
    return regra.tipo(medidas) if regra is not None else None


def sugerir_marcas(tabuleiro_rgb: np.ndarray) -> mc.MarcasDoDiagrama:
    """As marcas de casa que a forma sugere neste recorte. É sugestão: a pessoa confirma."""
    casas: dict[str, str] = {}
    for casa, medidas in enumerate(medir_casas(tabuleiro_rgb)):
        tipo = classificar(medidas) if medidas is not None else None
        if tipo is not None:
            casas[square_name(casa)] = tipo
    return mc.MarcasDoDiagrama(casas=casas)
