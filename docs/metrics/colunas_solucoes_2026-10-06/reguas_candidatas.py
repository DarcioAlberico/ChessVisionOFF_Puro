"""Para cada corrida candidata que o detector julga (`_colunas_cheias`), duas réguas:

- preenchimento: a de hoje (mediana, por coluna, da fração da largura que a banda ocupa);
- borda: a fração das bandas com tinta na coluna da esquerda de cada calha cuja tinta acaba rente
  à calha (a menos de `RENTE` x o piso da calha) -- o texto justificado e o alinhado à direita.

Caminho: `camada` (linhas da camada, o da régua S-194) ou `glifo` (caixas de caractere).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[0]).parent))
import patch_colunas  # noqa: E402,F401
import numpy as np  # noqa: E402
import pymupdf  # noqa: E402

from chess_diagram_ocr.cli.texto_ordem import _linhas_da_camada  # noqa: E402
from chess_diagram_ocr.text import regioes as R  # noqa: E402
from chess_diagram_ocr.text.boxes import Caixa  # noqa: E402
from chess_diagram_ocr.text.leitor import calha_de_linhas  # noqa: E402

RENTE = 1.0
estado = {"piso": 1}


def borda(mascaras, i, j, faixas, x_min):
    piso = estado["piso"]
    saida = []
    for (a, b), (c, _) in zip(faixas, faixas[1:], strict=False):
        com_tinta = rentes = 0
        for k in range(i, j):
            dentro = np.flatnonzero(mascaras[k][a - x_min : b - x_min + 1])
            if dentro.size:
                com_tinta += 1
                if (b - a) - dentro[-1] <= RENTE * piso:
                    rentes += 1
        saida.append(rentes / com_tinta if com_tinta else 0.0)
    return saida


def dois_lados(mascaras, i, j, faixas, x_min):
    """Fração das bandas com tinta que têm tinta em todas as colunas."""
    com = todas = 0
    for k in range(i, j):
        lados = [bool(np.flatnonzero(mascaras[k][a - x_min : b - x_min + 1]).size) for a, b in faixas]
        if any(lados):
            com += 1
            todas += all(lados)
    return todas / com if com else 0.0


_cheias = R._colunas_cheias


def espiao(mascaras, i, j, faixas, x_min):
    ok = _cheias(mascaras, i, j, faixas, x_min)
    if len(faixas) >= 2:
        enche = [round(R._preenchimento(mascaras, i, j, f, x_min), 2) for f in faixas]
        print(f"      bandas {i}-{j} ({j - i})  larguras {[b - a for a, b in faixas]}  "
              f"preench {enche}  borda {[round(v, 2) for v in borda(mascaras, i, j, faixas, x_min)]}  "
              f"dois_lados {dois_lados(mascaras, i, j, faixas, x_min):.2f}  -> {'aceita' if ok else 'recusa'}")
    return ok


R._colunas_cheias = espiao
_calha_original = R._calhas


for alvo in sys.argv[1:]:
    rotulo, pdf, pagina = alvo.split("|")
    page = pymupdf.open(pdf)[int(pagina) - 1]
    caixas = [Caixa(int(b[0]), int(b[1]), int(b[2]), int(b[3])) for _, b in _linhas_da_camada(page)]
    piso = calha_de_linhas(caixas)
    estado["piso"] = piso
    print(f"{rotulo:6s} {Path(pdf).stem[:34]} p{pagina}  piso {piso}")
    regioes = R.detectar_regioes(caixas, calha_minima=piso)
    print("   -> " + " | ".join(str(list(r.colunas)) for r in regioes))
