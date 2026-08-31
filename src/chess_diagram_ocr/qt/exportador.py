"""A exportação do livro inteiro para PGN, no segundo frontend (S-24/S-31/S-505).

**Duas decisões já vêm prontas** de `ui/exportacao_de_pgn.py`: o que a tela decide sobre *como*
ler (`ExportSettings`) e o texto do relatório final (`describe_report`). O que sobra aqui é o
diálogo do destino, a pergunta sobre o parcial e a thread.

**A pergunta sobre o parcial vem antes da de sobrescrever, e as duas se excluem**: havendo
parcial, o `.pgn` final ainda não existe. Retomar é o padrão -- recomeçar em silêncio jogaria fora
horas de varredura --, mas não é automático: quem está refazendo a exportação de propósito precisa
poder dizer "começa do zero" (S-24).

**Termina no rodapé, e não numa caixa que precisa de clique** (S-164). É o critério de aceite do
item: uma exportação de 402 páginas é justamente o que se deixa rodando enquanto se faz outra
coisa; terminar numa caixa modal fazia dela uma operação que não pode ser deixada só.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from chess_diagram_ocr.export_checkpoint import partial_path_for
from chess_diagram_ocr.pdf_to_pgn import ExportReport, default_pgn_output_path, save_pdf_positions_to_pgn
from chess_diagram_ocr.service import OcrService
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.exportacao_de_pgn import ExportSettings, describe_report

logger = logging.getLogger(__name__)

__all__ = ["Exportador"]


class Exportador(QObject):
    """Conduz a exportação: escolhe o destino, decide sobre o parcial e roda a thread."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status."""

    controles = pyqtSignal(bool)
    """Liga e desliga os controles enquanto a exportação roda."""

    _terminou = pyqtSignal(object)
    """Interno: o `ExportReport`, ou `None` quando falhou. Vem da thread da exportação."""

    _falhou = pyqtSignal(str)

    def __init__(
        self,
        pai: QWidget,
        *,
        configuracao: Callable[[], ExportSettings],
        servico: OcrService | None = None,
        busy: BusyRegistry | None = None,
    ) -> None:
        """`servico` empresta o modelo sob o lock da S-31 durante a varredura inteira (S-57).

        Sem ele a exportação carregaria o próprio `.pt` -- e o treino, que roda noutra thread e
        reescreve esse mesmo arquivo, podia trocá-lo debaixo de uma exportação de dezenas de
        minutos.
        """
        super().__init__(pai)
        self._pai = pai
        self._configuracao = configuracao
        self._servico = servico
        self._busy = busy
        self._busy_token: BusyToken | None = None
        self._cancelar: threading.Event | None = None
        self._rodando = False
        self._terminou.connect(self._concluiu)
        self._falhou.connect(self._deu_errado)

    @property
    def rodando(self) -> bool:
        return self._rodando

    def escolher_destino(self, pdf_path: Path) -> tuple[Path, bool] | None:
        """Pergunta o destino e o que fazer com um parcial. `None` se a pessoa desistir.

        Devolve `(caminho, retomar)`. A pergunta sobre o parcial vem **antes** da de sobrescrever
        porque as duas se excluem: havendo parcial, o `.pgn` final ainda não existe.
        """
        padrao = default_pgn_output_path(pdf_path)
        nome, _filtro = QFileDialog.getSaveFileName(
            self._pai, "Exportar PDF inteiro para PGN", str(padrao), "PGN (*.pgn);;Todos (*.*)"
        )
        if not nome:
            return None

        destino = Path(nome)
        parcial = partial_path_for(destino)
        if not parcial.exists():
            # O diálogo de salvar do Qt já pergunta sobre sobrescrever; o do Tk não, e é por isso
            # que o outro frontend tem uma segunda caixa aqui.
            return destino, True

        # Retomar é o padrão, mas não em silêncio: quem está refazendo a exportação de propósito
        # precisa poder dizer "começa do zero" (S-24).
        caixa = QMessageBox(self._pai)
        caixa.setWindowTitle("Exportação interrompida encontrada")
        caixa.setText(f"Existe um progresso parcial em:\n{parcial}")
        retomar = caixa.addButton("Retomar de onde parou", QMessageBox.ButtonRole.AcceptRole)
        recomecar = caixa.addButton("Recomeçar do zero", QMessageBox.ButtonRole.DestructiveRole)
        caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        caixa.setDefaultButton(retomar)
        caixa.exec()
        escolhido = caixa.clickedButton()
        if escolhido is retomar:
            return destino, True
        if escolhido is recomecar:
            parcial.unlink(missing_ok=True)
            return destino, False
        return None

    def comecar(self, pdf_path: Path | None) -> None:
        if pdf_path is None:
            # Pré-condição e "já está rodando" vão para o rodapé (S-164): a primeira é um passo
            # que falta, a segunda é o que a zona de operação ao lado já está mostrando -- e
            # nenhuma das duas é uma decisão a tomar.
            self.estado.emit("Abra um PDF antes de exportar o PGN.")
            return
        if self._rodando:
            self.estado.emit("Já existe uma exportação de PDF para PGN em execução.")
            return

        escolha = self.escolher_destino(pdf_path)
        if escolha is None:
            return
        destino, retomar = escolha

        self._rodando = True
        self._cancelar = threading.Event()
        if self._busy is not None:
            self._busy_token = self._busy.register(
                "exportação para PGN",
                # A S-24 grava um parcial a cada 5 páginas: fechar custa tempo, não trabalho.
                loses_work=False,
                cancellable=True,
                detail=pdf_path.name,
                cancel=self.cancelar,
            )
        self.controles.emit(False)
        self.estado.emit("Iniciando exportação do PDF para PGN...")
        threading.Thread(
            target=self._trabalho,
            args=(pdf_path, destino, self._configuracao(), retomar, self._cancelar),
            daemon=True,
        ).start()

    def cancelar(self) -> None:
        """Pede o cancelamento. A resposta vem entre páginas, não no meio de uma (S-24)."""
        if self._cancelar is None:
            return
        self._cancelar.set()
        self.estado.emit("Cancelando exportação... o progresso da página atual será preservado.")

    def _trabalho(
        self,
        pdf_path: Path,
        destino: Path,
        configuracao: ExportSettings,
        retomar: bool,
        cancelar: threading.Event,
    ) -> None:
        def _progresso(pagina: int, total: int, na_pagina: int, posicoes: int) -> None:
            # O número vai para o registro, e é ele que o rodapé transforma em barra determinada
            # (S-164): "página 120 de 402" na tela é frase, e frase não dá para desenhar sem
            # interpretá-la. O `BusyRegistry` tem lock próprio, então isto pode ser chamado da
            # thread de trabalho -- é para isso que ele existe.
            if self._busy_token is not None:
                self._busy_token.update(f"página {pagina + 1} de {total}", feito=pagina + 1, total=total)
            self.estado.emit(
                f"Exportando PDF -> PGN... página {pagina + 1}/{total} | "
                f"diagramas na página: {na_pagina} | total: {posicoes}"
            )

        try:
            relatorio = save_pdf_positions_to_pgn(
                pdf_source=pdf_path,
                output_path=destino,
                model_path=configuracao.model_path,
                dpi=configuracao.dpi,
                max_boards_per_page=configuracao.max_boards_per_page,
                orientation=configuracao.orientation,  # type: ignore[arg-type]
                resume=retomar,
                cancel_event=cancelar,
                progress_callback=_progresso,
                # O mesmo OCR de legenda que a tela usa ao reconhecer uma página (S-43): ter um
                # na tela e outro no PGN recriaria, na procedência do lado a jogar, o desencontro
                # que a S-14 corrigiu na numeração dos diagramas.
                caption_reader=getattr(self._servico, "caption_reader", None),
                model_session=(
                    self._servico.model_session(configuracao.model_path)
                    if self._servico is not None
                    else None
                ),
            )
        except Exception as exc:  # noqa: BLE001 - a thread não pode derrubar a janela
            logger.exception("Falha na exportação de PDF para PGN.")
            self._falhou.emit(str(exc))
            return
        self._terminou.emit(relatorio)

    def _concluiu(self, relatorio: Any) -> None:
        """Termina no rodapé. O detalhe linha a linha vai para o log, que é onde ele já ia."""
        self._encerrar()
        assert isinstance(relatorio, ExportReport)
        self.estado.emit(f"Exportação concluída. {relatorio.summary()}.")
        logger.info("Exportação para PGN concluída:\n%s", "\n".join(describe_report(relatorio)))

    def _deu_errado(self, detalhe: str) -> None:
        self._encerrar()
        self.estado.emit("Falha na exportação do PDF para PGN.")
        QMessageBox.critical(
            self._pai, "Exportar PDF para PGN", f"Não foi possível exportar o PDF:\n{detalhe}"
        )

    def _encerrar(self) -> None:
        self._rodando = False
        self._cancelar = None
        if self._busy_token is not None:
            self._busy_token.release()
            self._busy_token = None
        self.controles.emit(True)
