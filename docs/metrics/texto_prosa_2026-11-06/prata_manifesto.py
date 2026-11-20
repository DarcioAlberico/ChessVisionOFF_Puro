"""Escreve `assets/texto_prosa/prata.json` (S-705): os dez livros e as trinta folhas da prata de 2026-10-30, por identidade.

As folhas são as de `conjuntos.prata_todas` do relatório daquele dia, e não um sorteio novo: a prata só ordena, e manter
as mesmas folhas deixa a ordenação comparável. O estrato de cada livro sai da produção do PDF, sem leitor nenhum
(`prata.estrato_de_producao`: as fontes e a resolução mediana das imagens de página, em 13 folhas igualmente espaçadas).

Uso: prata_manifesto.py <saida.json>. Raiz com `PDF/`: `CVOFF_RAIZ`.
"""
import json
import os
import statistics
import sys
from pathlib import Path

import fitz

from chess_diagram_ocr.text import prata
from chess_diagram_ocr.text.caderno import identidade_de

AQUI = Path(__file__).resolve().parent
RAIZ = Path(os.environ.get("CVOFF_RAIZ") or AQUI.parents[2])


def perfil_de_producao(pdf: Path) -> tuple[list[str], int]:
    with fitz.open(pdf) as doc:
        n = doc.page_count
        fontes, dpis = set(), []
        for i in range(int(n * 0.1), int(n * 0.9), max(1, int(n * 0.8 / 12))):
            pagina = doc[i]
            fontes.update(f[3] for f in pagina.get_fonts())
            for imagem in pagina.get_image_info():
                x0, _, x1, _ = imagem["bbox"]
                if x1 - x0 > 0.5 * pagina.rect.width:
                    dpis.append(imagem["width"] / ((x1 - x0) / 72))
    return sorted(fontes), int(statistics.median(dpis)) if dpis else 0


def main(saida: str) -> None:
    conjunto = json.loads((AQUI.parent / "texto_prosa_20261030.json").read_text(encoding="utf-8"))["conjuntos"]["prata_todas"]
    livros, folhas = [], []
    for nome, info in conjunto["por_livro"].items():
        pdf = RAIZ / "PDF" / nome
        fontes, dpi = perfil_de_producao(pdf)
        estrato = prata.estrato_de_producao(fontes, dpi)
        assert estrato is not None, (nome, dpi)
        identidade = identidade_de(pdf)
        livros.append(prata.LivroDaPrata(identidade, info["lingua"], estrato, dpi))
        folhas.extend(prata.FolhaDaPrata(identidade, f, info["lingua"], estrato) for f in info["folhas"])
    manifesto = prata.Prata(prata.VERSAO, tuple(livros), tuple(folhas), "as folhas de prata_todas em docs/metrics/texto_prosa_20261030.json")
    erros = prata.problemas(manifesto)
    assert not erros, erros
    prata.gravar(manifesto, saida)
    print({e: sum(x.estrato == e for x in livros) for e in prata.ESTRATOS}, len(folhas), "folhas")


if __name__ == "__main__":
    main(sys.argv[1])
