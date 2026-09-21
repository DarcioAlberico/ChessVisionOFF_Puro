"""O trilho de páginas: uma miniatura por página, com estado, ao lado do visor (OCR_UI passo 17).

**O que ele é.** O mapa do livro. Cada página é uma miniatura com o número e três marcas --
diagramas (lidos/achados), texto, revisado -- e a cor da linha diz se há trabalho ali. Clicar
numa página é ir para ela; a página exibida está sempre marcada; a primeira duvidosa tem um botão
próprio, porque é para lá que o fluxo principal leva (U6: abrir o livro → ver o primeiro diagrama
duvidoso → corrigir → exportar, em ≤ 6 ações).

**O que ele não decide.** Qual página é duvidosa é `caissa.ui.trilho` (suíte), a partir do
relatório da importação e das decisões do revisor; como isso vira texto e cor é `ui/trilho.py`
(tronco). Este arquivo pinta e encaminha. A importação em si é `caissa.ui.views.importacao`
(progresso por página, cancelável, parcial aproveitável -- R3.5) e chega aqui por sinal; sem a
suíte ao alcance os dois botões ficam desabilitados com o motivo na dica, como os itens de
exportação de livro (`qt/exportador_de_livro.py`).

**As miniaturas vêm do processo de trabalho**, a 18 DPI, uma de cada vez, começando pelas que
estão à vista: o PyMuPDF segura o GIL (passo 15), e 289 miniaturas numa thread seriam 289
travamentos de alguns milissegundos na thread da janela. A fila é a mesma forma de
`DeteccaoDeFundo`: uma tarefa por vez, e quem rolou por último passa na frente.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.processo_de_trabalho import processo_de_trabalho
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.imagens import qimage_de_rgb
from chess_diagram_ocr.qt.trabalho import Tarefa, manter_viva
from chess_diagram_ocr.ui import comandos, espaco, tokens
from chess_diagram_ocr.ui.trilho import (
    MarcaDaPagina,
    dica_da_pagina,
    papel_da_pagina,
    primeira_duvidosa,
    rotulo_da_pagina,
    anterior_duvidosa,
    proxima_duvidosa,
)

logger = logging.getLogger(__name__)

__all__ = ["DPI_DA_MINIATURA", "LARGURA_DO_TRILHO", "TrilhoDoLivro"]

DPI_DA_MINIATURA = 18
"""Uma página A4 a 18 DPI tem ~150×210 px: cabe na largura do trilho com folga e custa ~5 ms."""

LARGURA_DO_TRILHO = 176
"""Largura fixa. O trilho é um índice, não um visor: ele não disputa largura com a página."""

LADO_DO_ICONE = 112
ALTURA_DO_ITEM = LADO_DO_ICONE + 26
"""Miniatura mais uma linha de rótulo. Declarada, e não deduzida: com `uniformItemSizes` o Qt
mede o primeiro item na criação -- antes de a miniatura existir -- e todas as linhas ficariam
com a altura do texto sozinho, e a miniatura, quando chegasse, não caberia nelas."""

MOTIVO_SEM_SUITE = (
    "Precisa da suíte Caïssa (caissa.ui.views.importacao), que não está ao alcance deste "
    "programa. No Caissa.exe ela vem junto; num checkout, rode com o Python 3.11 da suíte."
)


def suite_disponivel() -> bool:
    """Se a importação da suíte está importável daqui. É o que habilita os dois botões."""
    try:
        import caissa.ui.views.importacao  # noqa: F401 - só a pergunta "existe?"
    except Exception:  # noqa: BLE001 - ImportError, SyntaxError num Python antigo, tudo é "não"
        return False
    return True


class TrilhoDoLivro(QWidget):
    """A coluna de miniaturas, os três botões do fluxo e a barra da importação."""

    pagina_pedida = pyqtSignal(int)
    """A pessoa clicou numa página (base 0)."""

    importar_pedido = pyqtSignal()
    cancelar_pedido = pyqtSignal()
    exportar_pedido = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        miniaturas_ao_fundo: bool = True,
        rasterizar: Callable[[Path, int, int], Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self._pdf: Path | None = None
        self._paginas = 0
        self._marcas: dict[int, MarcaDaPagina] = {}
        self._miniaturas: dict[int, QPixmap] = {}
        self._fila: list[int] = []
        self._tarefa: Tarefa | None = None
        self._pagina_em_curso: int | None = None
        self._refletindo = False
        self._miniaturas_ao_fundo = miniaturas_ao_fundo
        """Ao fundo no produto; em linha nos testes, que perguntam pela miniatura na linha seguinte."""
        self._rasterizar = rasterizar or (
            lambda pdf, pagina, dpi: processo_de_trabalho().rasterizar(pdf, pagina, dpi=dpi)
        )
        self.setFixedWidth(LARGURA_DO_TRILHO)
        self._montar()

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(espaco.minima())

        botoes = QHBoxLayout()
        botoes.setSpacing(espaco.minima())
        self.btn_importar = self._botao("importar_livro", self.importar_pedido.emit)
        self.btn_cancelar = self._botao("cancelar_importacao", self.cancelar_pedido.emit)
        self.btn_cancelar.setVisible(False)
        botoes.addWidget(self.btn_importar, 1)
        botoes.addWidget(self.btn_cancelar, 1)
        coluna.addLayout(botoes)

        self.progresso = QProgressBar(self)
        self.progresso.setRange(0, 1)
        self.progresso.setValue(0)
        self.progresso.setTextVisible(False)
        self.progresso.setVisible(False)
        self.progresso.setAccessibleName("Progresso da importação do livro")
        coluna.addWidget(self.progresso)

        self.lista = QListWidget(self)
        self.lista.setViewMode(QListWidget.ViewMode.IconMode)
        self.lista.setFlow(QListWidget.Flow.TopToBottom)
        self.lista.setWrapping(False)
        self.lista.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.lista.setMovement(QListWidget.Movement.Static)
        self.lista.setIconSize(QSize(LADO_DO_ICONE, LADO_DO_ICONE))
        self.lista.setUniformItemSizes(True)
        self.lista.setWordWrap(True)
        self.lista.setSpacing(2)
        self.lista.setAccessibleName("Páginas do livro")
        self.lista.currentRowChanged.connect(self._linha_mudou)
        self.lista.verticalScrollBar().valueChanged.connect(lambda _v: self._pedir_as_visiveis())
        coluna.addWidget(self.lista, 1)

        self.btn_duvidosa = self._botao("primeira_duvidosa", self._ir_para_a_primeira_duvidosa)
        self.btn_duvidosa.setEnabled(False)
        coluna.addWidget(self.btn_duvidosa)
        self.btn_exportar = self._botao("exportar_epub", self.exportar_pedido.emit)
        self.btn_exportar.setEnabled(False)
        coluna.addWidget(self.btn_exportar)

        self.resumo = QLabel("", self)
        self.resumo.setWordWrap(True)
        self.resumo.setProperty("apoio", "true")
        coluna.addWidget(self.resumo)

        if not suite_disponivel():
            for botao in (self.btn_importar, self.btn_exportar):
                botao.setEnabled(False)
                botao.setToolTip(MOTIVO_SEM_SUITE)

    def _botao(self, acao: str, funcao: Callable[[], object]) -> QPushButton:
        """Um botão do trilho: rótulo, nome e papel vêm do catálogo -- nada é escrito à mão aqui."""
        botao = QPushButton(comandos.rotulo_de_botao(acao), self)
        botao.setAccessibleName(comandos.nome_acessivel(acao))
        botao.setToolTip(comandos.rotulo(acao))
        botao.clicked.connect(lambda _c=False: funcao())
        tema.aplicar_papel(botao, comandos.papel(acao))
        return botao

    # ------------------------------------------------------------------------------- o livro

    def abrir_livro(self, pdf: Path | None, paginas: int) -> None:
        """Um item por página, sem miniatura ainda; elas vêm conforme a pessoa rola."""
        self._pdf = pdf
        self._paginas = max(0, int(paginas))
        self._marcas = {}
        self._miniaturas = {}
        self._fila = []
        self._refletindo = True
        try:
            self.lista.clear()
            vazia = self._miniatura_vazia()
            for pagina in range(self._paginas):
                item = QListWidgetItem(vazia, rotulo_da_pagina(MarcaDaPagina(pagina)))
                item.setToolTip(dica_da_pagina(MarcaDaPagina(pagina)))
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                item.setSizeHint(QSize(LARGURA_DO_TRILHO - 24, ALTURA_DO_ITEM))
                self.lista.addItem(item)
        finally:
            self._refletindo = False
        self.btn_duvidosa.setEnabled(False)
        self.btn_exportar.setEnabled(False)
        self.resumo.setText("" if pdf is None else f"{self._paginas} página(s); livro ainda não importado.")
        self._pedir_as_visiveis()

    @property
    def paginas(self) -> int:
        return self._paginas

    def _miniatura_vazia(self) -> QIcon:
        """A página que ainda não foi rasterizada: um retângulo liso na superfície do documento.

        Um item sem ícone e um item com ícone têm alturas diferentes, e a lista mediria a
        primeira; o retângulo vazio dá a toda página o mesmo lugar desde o início.
        """
        folha = QPixmap(int(LADO_DO_ICONE * 0.71), LADO_DO_ICONE)
        # A superfície **elevada**, e não a afundada: a lista já é afundada, e uma folha da
        # mesma cor seria invisível -- foi o que a primeira fotografia mostrou.
        folha.fill(QColor(tema.cor_atual(tokens.SUPERFICIE_ELEVADA)))
        return QIcon(folha)

    def marcar_pagina_atual(self, pagina: int) -> None:
        """A página exibida no visor. Não emite `pagina_pedida`: é reflexo, não pedido."""
        if not 0 <= pagina < self._paginas or self.lista.currentRow() == pagina:
            return
        self._refletindo = True
        try:
            self.lista.setCurrentRow(pagina)
            self.lista.scrollToItem(self.lista.item(pagina), QListWidget.ScrollHint.PositionAtCenter)
        finally:
            self._refletindo = False
        self._pedir_as_visiveis()

    def showEvent(self, a0: object) -> None:  # noqa: N802 - assinatura do Qt
        """Ao aparecer, a página atual volta ao centro: a rolagem feita antes do leiaute não vale."""
        super().showEvent(a0)  # type: ignore[arg-type]
        atual = self.lista.currentRow()
        if atual >= 0:
            self.lista.scrollToItem(self.lista.item(atual), QListWidget.ScrollHint.PositionAtCenter)
        self._pedir_as_visiveis()

    def _linha_mudou(self, linha: int) -> None:
        if self._refletindo or linha < 0:
            return
        self.pagina_pedida.emit(linha)

    # --------------------------------------------------------------------------- as marcas

    def definir_estados(self, estados: list[Any], *, resumo: str = "") -> None:
        """Recebe os estados da importação (objetos com os campos de `MarcaDaPagina`)."""
        self._marcas = {int(e.pagina): MarcaDaPagina.de(e) for e in estados}
        for pagina, marca in self._marcas.items():
            self._pintar_marca(pagina, marca)
        alvo = primeira_duvidosa([self._marcas[p] for p in sorted(self._marcas)])
        self.btn_duvidosa.setEnabled(alvo is not None)
        self.btn_exportar.setEnabled(bool(self._marcas) and suite_disponivel())
        if resumo:
            self.resumo.setText(resumo)

    def marcar_montada(self, pagina: int) -> None:
        """A importação acabou de montar esta página: a linha acende antes do relatório final."""
        if pagina in self._marcas or not 0 <= pagina < self._paginas:
            return
        self._pintar_marca(pagina, MarcaDaPagina(pagina, montada=True))

    def _pintar_marca(self, pagina: int, marca: MarcaDaPagina) -> None:
        item = self.lista.item(pagina)
        if item is None:
            return
        item.setText(rotulo_da_pagina(marca))
        item.setToolTip(dica_da_pagina(marca))
        item.setForeground(QColor(tema.cor_atual(papel_da_pagina(marca))))

    def marcas(self) -> dict[int, MarcaDaPagina]:
        return dict(self._marcas)

    def _ir_para_a_primeira_duvidosa(self) -> None:
        alvo = primeira_duvidosa([self._marcas[p] for p in sorted(self._marcas)])
        if alvo is not None:
            self.pagina_pedida.emit(alvo)
            self.marcar_pagina_atual(alvo)

    def ir_para_a_proxima_duvidosa(self) -> int | None:
        """A duvidosa depois da página atual (passo C8); devolve a página, ou `None`."""
        alvo = proxima_duvidosa([self._marcas[p] for p in sorted(self._marcas)], self.lista.currentRow())
        if alvo is not None:
            self.pagina_pedida.emit(alvo)
            self.marcar_pagina_atual(alvo)
        return alvo

    def ir_para_a_anterior_duvidosa(self) -> int | None:
        """A duvidosa antes da página atual (passo C8); devolve a página, ou `None`."""
        alvo = anterior_duvidosa([self._marcas[p] for p in sorted(self._marcas)], self.lista.currentRow())
        if alvo is not None:
            self.pagina_pedida.emit(alvo)
            self.marcar_pagina_atual(alvo)
        return alvo

    # ----------------------------------------------------------------------- a importação

    def importacao_comecou(self, total: int) -> None:
        self.btn_importar.setVisible(False)
        self.btn_cancelar.setVisible(True)
        self.progresso.setRange(0, max(1, total))
        self.progresso.setValue(0)
        self.progresso.setVisible(True)

    def importacao_avancou(self, feito: int, total: int) -> None:
        self.progresso.setRange(0, max(1, total))
        self.progresso.setValue(min(feito, total))

    def importacao_terminou(self) -> None:
        self.btn_cancelar.setVisible(False)
        self.btn_importar.setVisible(True)
        self.progresso.setVisible(False)

    # ----------------------------------------------------------------------- as miniaturas

    def _visiveis(self) -> list[int]:
        """As páginas à vista, pela barra de rolagem e pela altura uniforme das linhas.

        `indexAt` cairia no vão entre duas linhas (o `spacing`) e responderia -1; com todas as
        linhas do mesmo tamanho, a conta é direta e não erra.
        """
        area = self.lista.viewport()
        if area is None or self._paginas == 0:
            return []
        passo = ALTURA_DO_ITEM + 2 * self.lista.spacing()
        primeiro = max(0, self.lista.verticalScrollBar().value() // max(1, passo))
        quantas = max(1, area.height() // max(1, passo) + 2)
        return list(range(primeiro, min(self._paginas, primeiro + quantas)))

    def _pedir_as_visiveis(self) -> None:
        if self._pdf is None:
            return
        # Quem está à vista passa na frente da fila; o resto fica para depois.
        pendentes = [p for p in self._visiveis() if p not in self._miniaturas]
        self._fila = pendentes + [p for p in self._fila if p not in pendentes]
        self._proxima_miniatura()

    def _proxima_miniatura(self) -> None:
        if self._tarefa is not None or self._pdf is None:
            return
        while self._fila and self._fila[0] in self._miniaturas:
            self._fila.pop(0)
        if not self._fila:
            return
        pagina = self._fila.pop(0)
        pdf, dpi = self._pdf, DPI_DA_MINIATURA
        self._pagina_em_curso = pagina
        if not self._miniaturas_ao_fundo:
            try:
                self._miniatura_chegou(self._rasterizar(pdf, pagina, dpi))
            except Exception as exc:  # noqa: BLE001 - a miniatura é enfeite; a falha vai ao log
                self._miniatura_falhou(str(exc), exc)
            return
        tarefa = manter_viva(Tarefa(lambda: self._rasterizar(pdf, pagina, dpi), nome=f"miniatura {pagina + 1}"))
        tarefa.pronto.connect(self._miniatura_chegou)
        tarefa.falhou.connect(self._miniatura_falhou)
        self._tarefa = tarefa
        tarefa.start()

    def _miniatura_chegou(self, rgb: object) -> None:
        pagina, self._pagina_em_curso = self._pagina_em_curso, None
        self._tarefa = None
        if pagina is not None and rgb is not None:
            try:
                pixmap = QPixmap.fromImage(qimage_de_rgb(rgb))  # type: ignore[arg-type]
                self._miniaturas[pagina] = pixmap
                item = self.lista.item(pagina)
                if item is not None:
                    item.setIcon(QIcon(pixmap))
            except Exception:  # noqa: BLE001 - a miniatura é enfeite
                logger.debug("miniatura da página %d não pintada", pagina + 1, exc_info=True)
        self._proxima_miniatura()

    def _miniatura_falhou(self, mensagem: str, _exc: object) -> None:
        pagina, self._pagina_em_curso = self._pagina_em_curso, None
        self._tarefa = None
        logger.debug("miniatura da página %s falhou: %s", pagina, mensagem)
        self._proxima_miniatura()

    @property
    def ocupado(self) -> bool:
        return self._tarefa is not None

    def miniatura(self, pagina: int) -> QPixmap | None:
        return self._miniaturas.get(pagina)


def marcas_do_tronco(paginas: int, caixas_por_pagina: dict[int, int], salvos: dict[int, set[int]]) -> list[MarcaDaPagina]:
    """O que o tronco sabe sem a suíte: diagramas detectados por página e amostras gravadas.

    Não diz nada de texto nem de dúvida -- só a suíte lê o livro --, e por isso não acende o
    botão da primeira duvidosa: sem importação não há fila.
    """
    marcas = []
    for pagina in range(paginas):
        achados = int(caixas_por_pagina.get(pagina, 0))
        gravados = len(salvos.get(pagina, ()))
        marcas.append(MarcaDaPagina(pagina, montada=achados > 0 or gravados > 0, diagramas=achados, diagramas_lidos=min(achados, gravados)))
    return marcas


