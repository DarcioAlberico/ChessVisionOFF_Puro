"""Protótipo (sonda, não produto): as correções candidatas do detector de colunas do tronco.

Aplicadas por monkeypatch ao importar, conforme a variável de ambiente COLUNAS_VARIANTE:
  ""     nada (a produção de hoje)
  "p1"   corpo sem as bandas isoladas das bordas, quando a folha inteira não tem calha
  "p2"   COLUNA_MINIMA 0,10 -> 0,20
  "p12"  as duas
  "p5"   P1 com bloco de borda (até 40 % das bandas) em vez de 1-2 bandas
  "p6"   P4 também na busca da maior corrida (`_maior_corrida`)
  "p4"   P2 só nos pedaços da recursão (não na folha nem no corpo)
  "p3"   colunas de largura quase igual dispensam o preenchimento (combinável: "p123")
"""
import os

import numpy as np

from chess_diagram_ocr.text import colunas as C
from chess_diagram_ocr.text import regioes as R
from chess_diagram_ocr.text.linhas import bandas

VARIANTE = os.environ.get("COLUNAS_VARIANTE", "")
#: Quantas bandas, no máximo, cada borda pode ceder.
BORDA_MAX = 2
#: O vão que isola uma banda de borda, em passos medianos entre bandas.
VAO_DE_BORDA = float(os.environ.get("VAO_DE_BORDA", "2.5"))


def _corpo(grupos):
    """(a, b): as bandas do corpo, sem as isoladas do topo e da base."""
    n = len(grupos)
    if n < 4:
        return 0, n
    topos = [min(c.y1 for c in g) for g in grupos]
    passos = np.diff(topos)
    passo = float(np.median(passos)) if len(passos) else 0.0
    if passo <= 0:
        return 0, n
    a = 0
    while a < BORDA_MAX and a + 1 < n and (topos[a + 1] - topos[a]) >= VAO_DE_BORDA * passo:
        a += 1
    b = n
    while n - b < BORDA_MAX and b - 1 > a and (topos[b - 1] - topos[b - 2]) >= VAO_DE_BORDA * passo:
        b -= 1
    return a, b


_original = R.detectar_regioes


def detectar_regioes_p1(caixas, *, calha_minima=None):
    if not caixas:
        return []
    grupos = bandas(caixas)
    x_min = min(c.x1 for c in caixas)
    x_max = max(c.x2 for c in caixas)
    y_min = min(c.y1 for c in caixas)
    y_max = max(c.y2 for c in caixas)
    largura = x_max - x_min
    if largura <= 1:
        return [R.Regiao(y_min, y_max, ((x_min, x_max),))]
    if calha_minima is None:
        calha_minima = C.piso_de_calha(caixas)
    mascaras = [R._mascara(g, x_min, largura) for g in grupos]
    # A folha inteira primeiro, como hoje: onde ela acha calha, nada muda.
    cortes, faixas = R._calhas(np.sum(mascaras, axis=0), x_min, x_max, calha_minima, len(grupos))
    a, b = _corpo(grupos)
    if faixas or (a, b) == (0, len(grupos)):
        return _original(caixas, calha_minima=calha_minima)
    cortes, faixas = R._calhas(np.sum(mascaras[a:b], axis=0), x_min, x_max, calha_minima, b - a)
    if not faixas:
        return _original(caixas, calha_minima=calha_minima)
    cortadas = []
    if a:
        cortadas.append((0, a, ((x_min, x_max),)))
    R._quebrar_nas_transversais(mascaras, a, b, x_min, x_max, cortes, faixas, calha_minima, cortadas)
    if b < len(grupos):
        cortadas.append((b, len(grupos), ((x_min, x_max),)))
    return R._com_cortes_em_y(R._fundir_iguais(cortadas), grupos, y_min, y_max)


if "1" in VARIANTE:
    R.detectar_regioes = detectar_regioes_p1
    import chess_diagram_ocr.text.leitor as L

    L._regioes.detectar_regioes = detectar_regioes_p1  # o leitor chama pelo módulo
if "2" in VARIANTE:
    C.COLUNA_MINIMA = 0.20


#: Quanto a coluna mais larga da região pode exceder a mais estreita para contar como "iguais".
LARGURAS_IGUAIS = 1.20
_cheias_original = R._colunas_cheias


def _colunas_cheias_p3(mascaras, i, j, faixas, x_min):
    larguras = [b - a for a, b in faixas]
    if len(larguras) >= 2 and min(larguras) > 0 and max(larguras) / min(larguras) <= LARGURAS_IGUAIS:
        return True
    return _cheias_original(mascaras, i, j, faixas, x_min)


if "3" in VARIANTE:
    R._colunas_cheias = _colunas_cheias_p3


#: P4: o piso de coluna mais alto só nos pedaços que a recursão de `_cortar` sobra em volta de
#: uma região achada -- a folha inteira (e o corpo da P1) ficam com o de hoje.
COLUNA_MINIMA_NO_PEDACO = 0.20
_cortar_original = R._cortar
_prof = {"n": 0}


def _cortar_p4(mascaras, a, b, x_min, x_max, calha_minima, saida):
    _prof["n"] += 1
    antes = C.COLUNA_MINIMA
    if _prof["n"] > 1:
        C.COLUNA_MINIMA = COLUNA_MINIMA_NO_PEDACO
    try:
        return _cortar_original(mascaras, a, b, x_min, x_max, calha_minima, saida)
    finally:
        C.COLUNA_MINIMA = antes
        _prof["n"] -= 1


if "4" in VARIANTE:
    R._cortar = _cortar_p4


#: P5: a fração máxima das bandas que um bloco de borda pode ter.
BLOCO_MAX = 0.40


def _corpo_p5(grupos):
    n = len(grupos)
    if n < 4:
        return 0, n
    topos = [min(c.y1 for c in g) for g in grupos]
    passos = np.diff(topos)
    passo = float(np.median(passos)) if len(passos) else 0.0
    if passo <= 0:
        return 0, n
    vaos = [k + 1 for k, d in enumerate(passos) if d >= VAO_DE_BORDA * passo]  # corte antes da banda k+1
    a = next((v for v in vaos if v <= BLOCO_MAX * n), 0)
    a = max([v for v in vaos if v <= BLOCO_MAX * n], default=0)
    b = min([v for v in vaos if n - v <= BLOCO_MAX * n and v > a], default=n)
    return a, b


def detectar_regioes_p5(caixas, *, calha_minima=None):
    if not caixas:
        return []
    grupos = bandas(caixas)
    x_min = min(c.x1 for c in caixas)
    x_max = max(c.x2 for c in caixas)
    y_min = min(c.y1 for c in caixas)
    y_max = max(c.y2 for c in caixas)
    largura = x_max - x_min
    if largura <= 1:
        return [R.Regiao(y_min, y_max, ((x_min, x_max),))]
    if calha_minima is None:
        calha_minima = C.piso_de_calha(caixas)
    mascaras = [R._mascara(g, x_min, largura) for g in grupos]
    cortes, faixas = R._calhas(np.sum(mascaras, axis=0), x_min, x_max, calha_minima, len(grupos))
    a, b = _corpo_p5(grupos)
    if faixas or (a, b) == (0, len(grupos)) or b - a < R.BANDAS_NA_REGIAO:
        return _original(caixas, calha_minima=calha_minima)
    cortes, faixas = R._calhas(np.sum(mascaras[a:b], axis=0), x_min, x_max, calha_minima, b - a)
    if not faixas:
        return _original(caixas, calha_minima=calha_minima)
    cortadas = []
    R._cortar(mascaras, 0, a, x_min, x_max, calha_minima, cortadas)
    R._quebrar_nas_transversais(mascaras, a, b, x_min, x_max, cortes, faixas, calha_minima, cortadas)
    R._cortar(mascaras, b, len(grupos), x_min, x_max, calha_minima, cortadas)
    return R._com_cortes_em_y(R._fundir_iguais(cortadas), grupos, y_min, y_max)


if "5" in VARIANTE:
    R.detectar_regioes = detectar_regioes_p5


_maior_original = R._maior_corrida


def _maior_corrida_p6(*args, **kwargs):
    antes = C.COLUNA_MINIMA
    C.COLUNA_MINIMA = COLUNA_MINIMA_NO_PEDACO
    try:
        return _maior_original(*args, **kwargs)
    finally:
        C.COLUNA_MINIMA = antes


if "6" in VARIANTE:
    R._maior_corrida = _maior_corrida_p6
