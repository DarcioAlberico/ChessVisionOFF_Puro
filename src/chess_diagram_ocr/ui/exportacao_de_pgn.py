"""O que a exportação do livro inteiro decide fora da janela (S-24/S-31/S-505).

Duas coisas, e nenhuma delas é a thread:

1. **`ExportSettings`** -- o que a tela decide sobre *como* ler. O destino e a retomada são do
   diálogo, e por isso não estão aqui.
2. **`describe_report`** -- o texto do relatório final. O gate da S-15 só ajuda se quem exportou
   souber o que ficou de fora: quantos foram para revisão, quantos foram rejeitados e em que
   arquivo. Montar essas linhas é lógica, não leiaute.

**Por que isso mudou de arquivo.** `ui/export_controller.py` importa `tkinter` na primeira linha
do corpo -- ele usa `filedialog`, `messagebox` e `root.after` --, e o segundo frontend precisa das
duas e de widget nenhum. Duas cópias de `describe_report` dariam dois relatórios do mesmo PGN, e a
divergência apareceria justamente no ramo que quase nunca roda: o do cancelamento com parcial.

`ui/export_controller.py` reexporta tudo o que está aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..pdf_to_pgn import ExportReport

__all__ = ["ExportSettings", "describe_report"]


@dataclass(frozen=True)
class ExportSettings:
    """O que a tela decide sobre *como* ler. O destino e a retomada são do diálogo."""

    model_path: Path
    dpi: int
    max_boards_per_page: int
    orientation: str = "auto"


def describe_report(report: ExportReport) -> list[str]:
    """As linhas do aviso final. Sem toolkit, para poderem ser conferidas.

    O que o gate rejeitou aparece **sempre** que houve rejeição: uma exportação que
    silenciosamente entrega menos diagramas do que o livro tem é indistinguível de um livro com
    menos diagramas.
    """
    linhas = [
        "Exportação cancelada" if report.cancelled else "Arquivo gerado com sucesso.",
        "",
        f"PGN: {report.output_path}",
        f"Aceitos: {len(report.accepted)} de {report.total}",
    ]
    if report.resumed_from_page is not None:
        linhas.insert(1, f"(retomada a partir da página {report.resumed_from_page + 1})")
    if report.review_path is not None:
        linhas += [
            "",
            f"Para revisão: {len(report.needs_review)} de baixa confiança, {len(report.rejected)} ilegais.",
            f"Arquivo: {report.review_path}",
        ]
    if report.cancelled and report.partial_path is not None:
        linhas += [
            "",
            "O progresso foi preservado. Exportar de novo para o mesmo arquivo oferece retomar.",
            f"Parcial: {report.partial_path}",
        ]
    return linhas
