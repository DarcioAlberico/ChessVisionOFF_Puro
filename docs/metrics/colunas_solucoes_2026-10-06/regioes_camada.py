"""As regiões que o detector acha nas linhas da camada (o caminho da régua S-194), numa variante."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[0]).parent))
import patch_colunas  # noqa: E402,F401
import pymupdf  # noqa: E402

from chess_diagram_ocr.cli.texto_ordem import _linhas_da_camada  # noqa: E402
from chess_diagram_ocr.text import regioes as R  # noqa: E402
from chess_diagram_ocr.text.boxes import Caixa  # noqa: E402
from chess_diagram_ocr.text.leitor import calha_de_linhas  # noqa: E402

for alvo in sys.argv[1:]:
    pdf, pagina = alvo.rsplit("|", 1)
    page = pymupdf.open(pdf)[int(pagina) - 1]
    linhas = _linhas_da_camada(page)
    caixas = [Caixa(int(b[0]), int(b[1]), int(b[2]), int(b[3])) for _, b in linhas]
    regioes = R.detectar_regioes(caixas, calha_minima=calha_de_linhas(caixas))
    print(f"{Path(pdf).stem[:40]} p{pagina} [{patch_colunas.VARIANTE or 'hoje'}]  {len(regioes)} região(ões)")
    for r in regioes:
        cols = r.colunas
        calhas = [cols[k + 1][0] - cols[k][1] for k in range(len(cols) - 1)]
        print(f"   y {r.topo}-{r.base}  colunas {list(cols)}  larguras {[b - a for a, b in cols]}  calhas {calhas}")
