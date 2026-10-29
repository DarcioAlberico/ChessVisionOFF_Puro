"""`cvoff-livro-com-pgn` -- quantos diagramas do PDF digital o PGN do livro resolve (S-589).

    cvoff-livro-com-pgn --pdf "livro.pdf" --pgn "livro.pgn" [--sem-modelo] [--json saida.json]

Casa cada diagrama com o seu nó (`livro_com_pgn.casar_livro`) e, com o modelo, confere a leitura
de cada imagem contra a FEN do nó. O relatório diz quantos em cada estado (confere, corrigido,
discorda, faltando, sem nó) e lista os que discordam -- que são o que a pessoa olha primeiro.

É a conta que a análise de 2026-10-29 fez à mão com scripts no rascunho, agora sobre o código que
a janela usa: se um dia o pareamento ou a resolução mudarem, esta é a régua.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from ..livro_com_pgn import DiagramaDoLivro, casar_livro, contagem
from ..logging_setup import configure_logging
from ..pgn_do_livro import IndiceDoLivro
from . import add_verbose, cli_errors

logger = logging.getLogger(__name__)

DPI_DO_RECORTE = 200
"""A imagem do diagrama é rasterizada da página nesta resolução antes do recorte do tabuleiro."""


def leitor_do_modelo(documento: Any, model_path: Path) -> Callable[[DiagramaDoLivro], str]:
    """`ler(diagrama) -> campo de peças`, rasterizando a caixa da página e passando pelo modelo."""
    import fitz
    import numpy as np

    from ..importacao_de_imagens import recortar
    from ..inference import load_model, predict_board

    modelo, dispositivo = load_model(model_path)

    def ler(diagrama: DiagramaDoLivro) -> str:
        assert diagrama.caixa is not None
        pagina = documento[diagrama.pagina - 1]
        pix = pagina.get_pixmap(clip=fitz.Rect(diagrama.caixa), dpi=DPI_DO_RECORTE)
        rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()
        tabuleiro, _modo = recortar(rgb)
        return str(predict_board(tabuleiro, modelo, dispositivo).fen_board)

    return ler


def medir(pdf: Path, pgn: Path, *, model_path: Path | None) -> dict[str, Any]:
    import fitz

    indice = IndiceDoLivro.do_arquivo(pgn)
    with fitz.open(pdf) as documento:
        ler = leitor_do_modelo(documento, model_path) if model_path is not None else None
        paginas = ((k + 1, documento[k].get_text("dict")) for k in range(documento.page_count))
        diagramas = casar_livro(paginas, indice, sumario=documento.get_toc(), ler=ler)
    return {
        "pdf": pdf.name,
        "pgn": pgn.name,
        "partidas": len(indice.partidas),
        "nos": len(indice.nos),
        "diagramas": len(diagramas),
        "estados": contagem(diagramas),
        "discordam": [
            {"pagina": d.pagina, "legenda": d.legenda, "casas": len(d.casas), "fen_do_pgn": d.fen, "lido": d.lido}
            for d in diagramas
            if d.estado == "discorda"
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    from ..config import DEFAULT_MODEL_PATH

    parser = argparse.ArgumentParser(prog="cvoff-livro-com-pgn", description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", type=Path, required=True, help="O PDF digital do livro.")
    parser.add_argument("--pgn", type=Path, required=True, help="O PGN que acompanha o livro.")
    parser.add_argument("--modelo", type=Path, default=DEFAULT_MODEL_PATH, help="O checkpoint que confere as imagens (padrao: o de producao).")
    parser.add_argument("--sem-modelo", action="store_true", help="Casa so pela legenda, sem ler as imagens.")
    parser.add_argument("--json", type=Path, help="Grava o relatorio neste caminho.")
    add_verbose(parser)
    return parser


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)
    relatorio = medir(args.pdf, args.pgn, model_path=None if args.sem_modelo else args.modelo)
    texto = json.dumps(relatorio, ensure_ascii=False, indent=1)
    if args.json:
        atomic_write_text(args.json, texto + "\n")
    print(json.dumps({k: relatorio[k] for k in ("partidas", "nos", "diagramas", "estados")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
