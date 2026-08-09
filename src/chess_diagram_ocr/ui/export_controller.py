"""Exportação de um PDF inteiro para PGN, disparada pela interface (S-24/S-31).

**O que vale a pena ter fora da janela.** Duas coisas, e nenhuma delas é o `Thread`:

1. **A decisão sobre o parcial.** A S-24 grava `.partial.jsonl` a cada página, e ao exportar
   de novo para o mesmo arquivo é preciso escolher entre retomar, recomeçar e abortar. São
   três respostas, e a que o diálogo oferece por padrão -- retomar -- é a certa só porque
   recomeçar em silêncio jogaria fora horas de varredura.
2. **O texto do relatório final.** O gate da S-15 só ajuda se o usuário souber o que ficou de
   fora: quantos foram para revisão, quantos foram rejeitados e em que arquivo. Montar essas
   linhas é lógica, não layout, e aqui ela é testável.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox

from chess_diagram_ocr.export_checkpoint import partial_path_for
from chess_diagram_ocr.pdf_to_pgn import ExportReport, default_pgn_output_path, save_pdf_positions_to_pgn
from chess_diagram_ocr.service import OcrService

from .busy import BusyRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportSettings:
    """O que a tela decide sobre *como* ler. O destino e a retomada são do diálogo."""

    model_path: Path
    dpi: int
    max_boards_per_page: int
    orientation: str


def describe_report(report: ExportReport) -> list[str]:
    """As linhas do aviso final. Sem Tk, para poderem ser conferidas.

    O que o gate rejeitou aparece **sempre** que houve rejeição: uma exportação que
    silenciosamente entrega menos diagramas do que o livro tem é indistinguível de um livro
    com menos diagramas.
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


class ExportController:
    """Conduz a exportação: escolhe o destino, decide sobre o parcial e roda a thread."""

    def __init__(
        self,
        root: tk.Misc,
        *,
        settings: Callable[[], ExportSettings],
        on_status: Callable[[str], None],
        on_controls_enabled: Callable[[bool], None],
        service: OcrService | None = None,
        busy: BusyRegistry | None = None,
    ) -> None:
        """`service` empresta o modelo sob o lock da S-31 durante a varredura inteira (S-57).

        Sem ele a exportação carregava o próprio `.pt` -- e o treino, que roda noutra thread
        e reescreve esse mesmo arquivo, podia trocá-lo debaixo de uma exportação de dezenas
        de minutos. `None` mantém o comportamento antigo, para quem monta o controlador sem
        serviço (os testes).
        """
        self.root = root
        self._service = service
        self._busy = busy
        self._busy_token: object | None = None
        self._settings = settings
        self._on_status = on_status
        self._on_controls_enabled = on_controls_enabled
        self._cancel: threading.Event | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def choose_output(self, pdf_path: Path) -> tuple[Path, bool] | None:
        """Pergunta o destino e o que fazer com um parcial. `None` se o usuário desistir.

        Devolve `(caminho, retomar)`. A pergunta sobre o parcial vem antes da de
        sobrescrever porque as duas se excluem: havendo parcial, o `.pgn` final ainda não
        existe.
        """
        padrao = default_pgn_output_path(pdf_path)
        filename = filedialog.asksaveasfilename(
            title="Exportar PDF inteiro para PGN",
            defaultextension=".pgn",
            filetypes=[("PGN", "*.pgn"), ("Todos", "*.*")],
            initialdir=str(padrao.parent),
            initialfile=padrao.name,
        )
        if not filename:
            return None

        output_path = Path(filename)
        parcial = partial_path_for(output_path)
        if parcial.exists():
            # Retomar e o padrão, mas não em silencio: quem esta refazendo a exportação de
            # proposito precisa poder dizer "comeca do zero" (S-24).
            resposta = messagebox.askyesnocancel(
                "Exportação interrompida encontrada",
                f"Existe um progresso parcial em:\n{parcial}\n\n"
                "Sim: retomar de onde parou.\n"
                "Não: recomecar do zero, descartando o parcial.\n"
                "Cancelar: abortar.",
            )
            if resposta is None:
                return None
            if not resposta:
                parcial.unlink(missing_ok=True)
                return output_path, False
            return output_path, True

        if output_path.exists():
            sobrescrever = messagebox.askyesno(
                "Sobrescrever PGN",
                f"O arquivo já existe:\n{output_path}\n\nDeseja sobrescrever?",
            )
            if not sobrescrever:
                return None
        return output_path, True

    def start(self, pdf_path: Path | None) -> None:
        if pdf_path is None:
            messagebox.showwarning("Aviso", "Abra um PDF antes de exportar o PGN.")
            return
        if self._running:
            messagebox.showinfo(
                "Exportação em andamento", "Já existe uma exportação de PDF para PGN em execução."
            )
            return

        escolha = self.choose_output(pdf_path)
        if escolha is None:
            return
        output_path, resume = escolha

        self._running = True
        self._cancel = threading.Event()
        if self._busy is not None:
            self._busy_token = self._busy.register(
                "exportação para PGN",
                # A S-24 grava um parcial a cada 5 paginas: fechar custa tempo, nao trabalho.
                loses_work=False,
                cancellable=True,
                detail=pdf_path.name,
                cancel=self.cancel,
            )
        self._on_controls_enabled(False)
        self._on_status("Iniciando exportação do PDF para PGN...")
        threading.Thread(
            target=self._worker,
            args=(pdf_path, output_path, self._settings(), resume, self._cancel),
            daemon=True,
        ).start()

    def cancel(self) -> None:
        """Pede o cancelamento. A resposta vem entre páginas, não no meio de uma (S-24)."""
        if self._cancel is None:
            return
        self._cancel.set()
        self._on_status("Cancelando exportação... o progresso da página atual será preservado.")

    # ----------------------------------------------------------------------------- worker

    def _worker(
        self,
        pdf_path: Path,
        output_path: Path,
        settings: ExportSettings,
        resume: bool,
        cancel: threading.Event,
    ) -> None:
        def _progress(page_index: int, total_pages: int, page_boards: int, total_positions: int) -> None:
            self.root.after(
                0,
                partial(
                    self._on_status,
                    f"Exportando PDF -> PGN... página {page_index + 1}/{total_pages} | "
                    f"diagramas na página: {page_boards} | total: {total_positions}",
                ),
            )

        try:
            report = save_pdf_positions_to_pgn(
                pdf_source=pdf_path,
                output_path=output_path,
                model_path=settings.model_path,
                dpi=settings.dpi,
                max_boards_per_page=settings.max_boards_per_page,
                orientation=settings.orientation,  # type: ignore[arg-type]
                resume=resume,
                cancel_event=cancel,
                progress_callback=_progress,
                model_session=(
                    self._service.model_session(settings.model_path) if self._service is not None else None
                ),
            )
            self.root.after(0, partial(self._on_success, report))
        except Exception as exc:
            logger.exception("Falha na exportação de PDF para PGN.")
            self.root.after(0, partial(self._on_error, exc))
        finally:
            self.root.after(0, self._finish)

    def _on_success(self, report: ExportReport) -> None:
        self._on_status(f"Exportação concluida. {report.summary()}.")
        messagebox.showinfo("Exportar PDF para PGN", "\n".join(describe_report(report)))

    def _on_error(self, exc: Exception) -> None:
        self._on_status("Falha na exportação do PDF para PGN.")
        messagebox.showerror("Exportar PDF para PGN", f"Não foi possível exportar o PDF:\n{exc}")

    def _finish(self) -> None:
        self._running = False
        self._cancel = None
        if self._busy_token is not None:
            self._busy_token.release()  # type: ignore[attr-defined]
            self._busy_token = None
        self._on_controls_enabled(True)

