"""O lado direito da janela no segundo frontend: o PDF, a navegação e a seleção (S-31/S-503).

**O que ele guarda.** O documento aberto, a página rasterizada e o zoom. **O que ele não faz:**
não reconhece nada. A seleção de área devolve um retângulo em coordenadas de **pixel da página**;
recortar, grampear aos limites e decidir o que fazer quando não há contorno é do `OcrService`.

**Quase nada do desenho é escrito aqui.** `qt/visor.py` já mostra a página, rola, dá zoom, marca
os diagramas, distingue clique de arrasto e devolve a área selecionada -- e ele, por sua vez,
chama `ui/page_overlay.py` e `ui/viewport.py` inteiros. O que este arquivo escreve é o **cromo**:
as barras, o campo de página, os controles de zoom, os dois interruptores de vista e o vaivém com
o `pdf_io`.

---

**Três diferenças do Qt, e as três são de mecanismo.**

1. **O campo de página é um `QSpinBox` em base 1**, e ele não tem os dois defeitos que a S-305 e a
   S-328 mediram no `ttk.Spinbox`: `valueChanged` chega tanto da seta quanto da digitação, e o
   widget recusa texto não numérico sozinho -- então não há o caminho em que `abc` no campo
   derruba as cinco funções que leem o índice. O que continua sendo decisão é *contra o quê*
   comparar: a folha que está na tela, e não o índice que já mudou. Ver `_pagina_digitada`.
2. **A espera do DPI é um `QTimer` de disparo único**, e existe pela mesma medição da S-329:
   digitar `220` passa por `2`, `22` e `220`, e cada disparo custaria ~0,3 s de rasterização em
   dois DPI que ninguém pediu.
3. **A centralização é do `QScrollArea`** (`AlignCenter`), e não uma conta de desvio. É a S-157
   resolvida pelo leiaute: some com ela some a fronteira `_para_pagina`/`_para_canvas` que o outro
   frontend tem de atravessar em oito pontos de conversão.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.pdf_io import get_pdf_page_count, render_pdf_page
from chess_diagram_ocr.qt.barra import BarraEmFila
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.visor import VisorDePagina
from chess_diagram_ocr.ui import barra_do_pdf, comandos, espaco, formato
from chess_diagram_ocr.ui.leitura_do_pdf import PASSO_DE_ZOOM, open_in_system_reader
from chess_diagram_ocr.ui.page_overlay import PageBoxes
from chess_diagram_ocr.ui.viewport import LADO_DO_DESLIZADOR, clamp_zoom, posicao_do_zoom, zoom_da_posicao

logger = logging.getLogger(__name__)

__all__ = ["ESPERA_DO_DPI_MS", "PainelDoPdf"]

ESPERA_DO_DPI_MS = 400
"""Quanto esperar o campo de DPI parar de mudar antes de re-rasterizar (S-329)."""


def sufixo_de_paginas(total: int) -> str:
    """O ` de 289` que o campo de página escreve depois do número (S-528).

    Era um `QLabel` ao lado do campo, e o par vivia numa fila que quebrava: o rótulo ia para a
    fileira de baixo e o número ficava sem o total. Dentro do campo eles não se separam, e o
    controle inteiro pesa um widget em vez de dois.
    """
    return f" de {max(0, int(total))}"


class PainelDoPdf(QWidget):
    """Visualização e navegação do PDF, com seleção de área para OCR."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status. A janela decide onde ela aparece."""

    abriu_pdf = pyqtSignal(object)
    """O livro que passou a estar aberto -- um `Path`. Emitido **depois** de ele abrir de verdade."""

    antes_de_trocar_de_pagina = pyqtSignal()
    """A janela de tempo em que o editor ainda tem o reconhecimento da página de origem."""

    pagina_desenhada = pyqtSignal(int)
    """A folha apareceu. É onde a janela traz de volta o reconhecimento guardado desta página --
    fazê-lo antes do desenho restauraria o editor para uma página que ainda não está na tela."""

    zoom_mudou = pyqtSignal(float)
    caixa_clicada = pyqtSignal(int)
    caixa_dispensada = pyqtSignal(int)
    caixa_para_estudo = pyqtSignal(int)
    """Duplo clique num retângulo: o diagrama vai para a sala de estudo. Retransmitido do visor."""
    regiao_pedida = pyqtSignal(object, object)
    """`(página RGB, (x0, y0, x1, y1))` -- o recorte que a seleção de área devolveu."""

    preferencias_mudaram = pyqtSignal()
    """Um interruptor de visualização mudou. O estado da aplicação lembra dele entre execuções."""

    leitura_pedida = pyqtSignal(bool)
    """Pediram para ler a página exibida. O `bool` é **"só o melhor"**.

    Este painel não conhece o serviço nem o modelo: quem lê é a janela. Ele diz que pediram, e o
    `bool` carrega a única diferença entre os dois botões -- `ler_melhor` é um diagrama só
    (`max_boards=1`), `ler_pagina` é a preferência inteira. Era assim que o `ocr_best` e o
    `ocr_all` do Tk se distinguiam, e no porte os dois tinham ficado no mesmo método (S-506).
    """

    exportacao_pedida = pyqtSignal()
    exportacao_cancelada = pyqtSignal()
    """Os dois lados da exportação para PGN. Quem exporta é `qt/exportador.py`, pela janela."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        dpi: Callable[[], int],
        pagina_inicial_de: Callable[[Path], int] = lambda _livro: 0,
        pasta_inicial: Path = Path("."),
    ) -> None:
        super().__init__(parent)
        self._dpi = dpi
        self._pagina_inicial_de = pagina_inicial_de
        self._pasta_inicial = Path(pasta_inicial)

        self.source: Path | None = None
        self.name = ""
        self.page_count = 0
        self.page_rgb: np.ndarray | None = None
        self.page_loaded_for_index: int | None = None
        self._page_index = 0
        self._dpi_rasterizado: int | None = None
        """O DPI com que a folha na tela foi rasterizada. `None` até a primeira (S-329)."""
        self._movendo_o_deslizador = False
        """Guarda contra o laço: mover o deslizador aplica o zoom, e aplicar o zoom repõe o
        deslizador -- que dispararia de novo. É o mesmo `_movendo_o_deslizador` do outro lado."""
        self._montando = False
        self._trancado = False
        """Se uma operação longa da janela está em curso. Ver `trancar`."""
        self._exportando = False
        """Se há exportação para PGN rodando. Ver `exportacao_em_curso`."""

        self._relogio_do_dpi = QTimer(self)
        self._relogio_do_dpi.setSingleShot(True)
        self._relogio_do_dpi.timeout.connect(self._aplicar_dpi)

        self._montar()

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.folga(),) * 4)
        fora.setSpacing(espaco.folga())

        # **Uma fila, agrupada por tarefa** (S-528). Eram duas `BarraFluida` com dezesseis
        # controles de texto -- `QPushButton` e `QCheckBox` -- que quebravam em duas fileiras a
        # 675 px e em três a 520, o piso do painel: 176 px de cromo antes da folha, ao lado de uma
        # sala de estudo cuja barra tem 32. Quem decide grupo, principal, ícone, dica e quem cabe
        # é `ui/barra_do_pdf.py`; o widget é o mesmo `BarraEmFila` da sala.
        self.barra = BarraEmFila(
            self, tabela=barra_do_pdf, registros=barra_do_pdf.ACOES, executar=self.executar
        )
        # Os nomes pelos quais o resto do painel, a janela e os testes chamam estes controles
        # apontam agora para as `QAction`s da fila: `setEnabled`, `isEnabled`, `setChecked`,
        # `isChecked`, `setText` e `toggle` são os mesmos, e é isso que deixa `qt/janela.py`
        # inalterado -- ele faz `pdf.marcar_diagramas.toggle()` e continua funcionando.
        self.btn_abrir = self.barra.acoes["abrir_pdf"]
        self.btn_leitor = self.barra.acoes["abrir_no_leitor"]
        self.btn_ler_melhor = self.barra.acoes["ler_melhor"]
        self.btn_ler_pagina = self.barra.acoes["ler_pagina"]
        self.btn_tirar_caixa = self.barra.acoes["tirar_caixa"]
        self.btn_exportar = self.barra.acoes["exportar_pgn"]
        self.btn_cancelar_exportacao = self.barra.acoes["cancelar_exportacao"]
        self.btn_selecionar = self.barra.acoes["selecionar_area"]
        self.marcar_diagramas = self.barra.acoes["marcar_diagramas"]
        self.roda_vira_pagina = self.barra.acoes["roda_vira_pagina"]
        # As duas preferências nascem marcadas **sem avisar**: o `toggled` já está ligado ao
        # método, e o método fala com o visor -- que tem os mesmos padrões e ainda não precisa
        # ouvir nada. Era o que a montagem antiga conseguia de graça, marcando antes de ligar.
        for interruptor in (self.marcar_diagramas, self.roda_vira_pagina):
            interruptor.blockSignals(True)
            interruptor.setChecked(True)
            interruptor.blockSignals(False)

        # **O campo de página fica na mesma fila** (S-528), pendurado depois de "Página anterior":
        # a seta, o número e a outra seta são um controle só, e separá-los em duas linhas era
        # metade do defeito. **Base 1, e a faixa nunca é `0..0`** (S-328): "página 0" não existe na
        # contagem que o campo usa, e um campo vazio com teto zero é o que fazia a seta escrever o
        # número que o resto da tela nega. O total é o **sufixo** do campo, e não um `QLabel` ao
        # lado: eram dois widgets para um número, e o de fora não sabia sumir junto com as setas.
        self.campo_pagina = QSpinBox(self.barra)
        self.campo_pagina.setRange(1, 1)
        self.campo_pagina.setSuffix(sufixo_de_paginas(0))
        # **Sem as setinhas próprias do `QSpinBox`**: os dois botões do grupo `PAGINA` estão
        # colados nele e fazem exatamente isso, com 16 px de traço em vez de duas meias-setas de
        # 6 px. Tirá-las devolve ~18 px à fila, que é largura que "Abrir PDF" usa para caber.
        self.campo_pagina.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.campo_pagina.valueChanged.connect(self._pagina_digitada)
        dica_em(
            self.campo_pagina,
            "A folha que está na tela, em base 1. Digitar o número vai para ela; os dois\n"
            "botões ao lado, Page Up e Page Down viram uma de cada vez.",
        )
        self.barra.encaixar(self.campo_pagina, depois_de="pagina_anterior")
        fora.addWidget(self.barra)

        self.visor = VisorDePagina(self)
        self.visor.caixa_clicada.connect(self.caixa_clicada)
        self.visor.caixa_dispensada.connect(self.caixa_dispensada)
        self.visor.caixa_para_estudo.connect(self.caixa_para_estudo)
        self.visor.pagina_pedida.connect(self._roda_pediu_pagina)
        self.visor.zoom_mudou.connect(self._zoom_do_visor)
        self.visor.area_selecionada.connect(self._area_selecionada)
        self.visor.selecao_pequena.connect(
            lambda: self.estado.emit("Seleção muito pequena. Tente novamente.")
        )
        fora.addWidget(self.visor, 1)
        fora.addLayout(self._rodape_de_zoom())
        self._reavaliar_controles()

    def executar(self, acao: str) -> None:
        """Roda o método que `barra_do_pdf.METODOS_DO_PAINEL` liga àquela ação.

        É o único caminho de volta da barra ao painel, e é a mesma forma de
        `PainelDeEstudo.executar` (S-280): o par comando-método é declarado **uma** vez, na tabela,
        e não num `lambda` escrito no meio da montagem. Levanta para ação que a tabela não tem.
        """
        getattr(self, barra_do_pdf.METODOS_DO_PAINEL[acao])()

    # -------------------------------------------------- o que cada ação da barra faz (S-528)

    def ler_o_melhor(self) -> None:
        """Pede o reconhecimento de **um** diagrama (`max_boards=1`). Quem lê é a janela."""
        self.leitura_pedida.emit(True)

    def ler_a_pagina(self) -> None:
        """Pede o reconhecimento da página inteira, na preferência configurada."""
        self.leitura_pedida.emit(False)

    def pedir_exportacao(self) -> None:
        self.exportacao_pedida.emit()

    def pedir_cancelamento(self) -> None:
        self.exportacao_cancelada.emit()

    def alternou_marcacao(self) -> None:
        """O interruptor "Marcar diagramas" mudou.

        O método **lê** o estado, e não o inverte -- ver `ui/barra.Acao.alterna_no_metodo`: quem
        alterna é o próprio item, como no `QCheckBox` que ele substitui.
        """
        self.visor.alternar_caixas(self.marcar_diagramas.isChecked())
        self.preferencias_mudaram.emit()

    def alternou_virada(self) -> None:
        self.visor.virar_paginas = self.roda_vira_pagina.isChecked()
        self.preferencias_mudaram.emit()

    # ------------------------------------------------------------- quem fica cinza, e por quê

    def _reavaliar_controles(self) -> None:
        """O estado de cada controle, resolvido **num lugar só**, a partir de três fatos.

        Os fatos são: há livro aberto, há operação longa em curso, há exportação rodando. Espalhar
        isto por quem causa cada mudança é como o Tk tinha três métodos (`set_ocr_controls_enabled`,
        `set_export_controls_enabled`, `disable_cancel_button`) que se sobrescreviam pela ordem de
        chamada -- e o botão de cancelar ficava cinza porque a última a falar não sabia da
        exportação.

        **A regra grossa é do modo e a fina é da condição** (S-528), como na sala: `SEM_LIVRO`
        desliga os grupos que falam da folha, `TRANCADO` desliga tudo menos `EXPORTAR`, e as três
        condições dizem o que só o painel sabe. O cancelar não olha `_trancado`, e é o item: ele
        só existe durante a exportação, que é justamente quando tudo o mais está trancado --
        obedecê-la faria o botão ficar cinza exatamente na única situação em que ele serve.
        """
        livro = self.source is not None
        util = livro and not self._trancado
        self.barra.aplicar_modo(
            barra_do_pdf.modo(livro=livro, trancado=self._trancado),
            {
                "abrir_no_leitor": util,
                "exportar_pgn": util and not self._exportando,
                "cancelar_exportacao": self._exportando,
            },
        )
        self.campo_pagina.setEnabled(util)
        self.visor.setEnabled(not self._trancado)
        self.deslizador.setEnabled(not self._trancado)

    def trancar(self, liberado: bool) -> None:
        """Liga e desliga o painel durante uma operação longa da janela.

        **Não é `setEnabled` no painel inteiro**, que era o que a janela fazia antes de o botão de
        cancelar existir aqui: no Qt um filho de widget desabilitado não pode ser reabilitado, e o
        cancelar morreria junto com o resto.
        """
        self._trancado = not liberado
        self._reavaliar_controles()

    def exportacao_em_curso(self, em_curso: bool) -> None:
        """A exportação começou ou acabou. Troca o par exportar/cancelar."""
        self._exportando = em_curso
        self._reavaliar_controles()

    def _rodape_de_zoom(self) -> QHBoxLayout:
        """O deslizador de zoom, em escala **logarítmica** (S-225).

        Numa escala linear entre 25% e 200%, metade do curso fica acima de 112% -- e a metade que
        importa, a de enquadrar um diagrama pequeno, se espreme nos primeiros milímetros. Quem
        converte posição em zoom é `ui/viewport.py`, e é por isso que a faixa pode mudar sem
        ninguém tocar no widget.
        """
        linha = QHBoxLayout()
        linha.setSpacing(espaco.folga())
        self.deslizador = QSlider(Qt.Orientation.Horizontal, self)
        self.deslizador.setRange(0, int(LADO_DO_DESLIZADOR))
        self.deslizador.valueChanged.connect(self._arrastou_o_zoom)
        linha.addWidget(self.deslizador, 1)
        self.lbl_zoom = QLabel("", self)
        linha.addWidget(self.lbl_zoom)
        self._sincronizar_deslizador()
        return linha

    # ---------------------------------------------------------------------------------- zoom

    @property
    def zoom(self) -> float:
        return self.visor.zoom

    def aplicar_zoom(self, valor: float) -> None:
        self.visor.definir_zoom(clamp_zoom(valor))

    def aumentar_zoom(self) -> None:
        self.aplicar_zoom(self.zoom + PASSO_DE_ZOOM)

    def diminuir_zoom(self) -> None:
        self.aplicar_zoom(self.zoom - PASSO_DE_ZOOM)

    def ajustar_a_largura(self) -> None:
        self.visor.ajustar_a_largura()

    def ajustar_a_pagina(self) -> None:
        self.visor.ajustar_a_pagina()

    def _zoom_do_visor(self, valor: float) -> None:
        self._sincronizar_deslizador()
        self.zoom_mudou.emit(valor)

    def _arrastou_o_zoom(self, posicao: int) -> None:
        if self._movendo_o_deslizador:
            return
        self.aplicar_zoom(zoom_da_posicao(float(posicao)))

    def _sincronizar_deslizador(self) -> None:
        """Repõe a posição e o rótulo sem redisparar o `valueChanged` (S-225)."""
        self._movendo_o_deslizador = True
        try:
            self.deslizador.setValue(int(round(posicao_do_zoom(self.zoom))))
            # `formato.porcentagem` e não um `f"{int(...)}%"` cravado (S-225): duas formatações
            # do mesmo número é como elas divergem, e este número aparece em dois rótulos.
            self.lbl_zoom.setText(formato.porcentagem(self.zoom, casas=0))
        finally:
            self._movendo_o_deslizador = False

    # ---------------------------------------------------------------------------- o livro

    def abrir_pdf(self) -> None:
        caminho, _filtro = QFileDialog.getOpenFileName(
            self, "Selecione o PDF", str(self._pasta_inicial), "PDF (*.pdf);;Todos (*.*)"
        )
        if caminho:
            self.load_pdf(Path(caminho))

    def abrir_no_leitor_do_sistema(self) -> None:
        """Manda o PDF para o leitor do sistema. Falhar aqui é aviso, e não erro do app."""
        if self.source is None:
            return
        try:
            open_in_system_reader(self.source)
            self.estado.emit(f"{self.name} enviado para o leitor do sistema.")
        except Exception as exc:  # noqa: BLE001 - `startfile` e `Popen` levantam tipos diversos
            logger.warning("Não foi possível abrir %s no leitor do sistema: %s", self.source, exc)
            QMessageBox.warning(
                self, "Leitor do sistema", f"Não foi possível abrir o PDF no leitor do sistema:\n{exc}"
            )

    def load_pdf(self, pdf_path: Path) -> None:
        """Troca o livro aberto. **Abre antes de trocar** (S-123).

        A ordem é a correção. Com o aviso antes da abertura, um PDF que não abria já tinha limpado
        as caixas da página, descartado os resultados do livro anterior e apontado a Galeria para
        o arquivo quebrado: **a tela continuava mostrando o livro anterior e o programa, por
        dentro, estava no que não abriu.** O `Ctrl+S` seguinte gravava a amostra sob o nome errado.

        Contar as páginas é abrir o documento de verdade, então serve de validação sem custo
        próprio: o `page_count` que ela devolve é o mesmo que seria usado adiante.
        """
        try:
            page_count = get_pdf_page_count(pdf_path)

            self.source = pdf_path
            self.name = pdf_path.name
            self.page_count = page_count
            # **O nome do livro não volta para a barra** (S-528): o rodapé da janela já escreve
            # `1937 Kemeri.pdf · p. 21 de 289` em toda tela, e o rótulo daqui repetia isso em
            # ~210 px permanentes de uma fila que não tinha para onde crescer.
            self.campo_pagina.setSuffix(sufixo_de_paginas(self.page_count))
            self._reavaliar_controles()
            self.abriu_pdf.emit(pdf_path)

            alvo = max(0, min(self.page_count - 1, self._pagina_inicial_de(pdf_path)))
            self._page_index = alvo
            self._faixa_do_campo_de_pagina()
            self.page_loaded_for_index = None
            self.desenhar_pagina()
        except Exception as exc:  # noqa: BLE001 - PDF de terceiro, e o bundle não deixa rastro
            logger.exception("Falha ao abrir %s.", pdf_path)
            preservado = self.source is not None and self.source != pdf_path
            resto = f"\n\n{self.name} continua aberto." if preservado else ""
            QMessageBox.critical(self, "Abrir PDF", f"Falha ao abrir {pdf_path.name}:\n{exc}{resto}")

    # ------------------------------------------------------------------------------ páginas

    @property
    def page_index(self) -> int:
        return self._page_index

    def _faixa_do_campo_de_pagina(self) -> None:
        """A faixa do campo em base 1: de 1 até o total de folhas (S-328)."""
        self._montando = True
        try:
            self.campo_pagina.setRange(1, max(self.page_count, 1))
            self.campo_pagina.setValue(self._page_index + 1)
        finally:
            self._montando = False

    def _pagina_digitada(self, valor: int) -> None:
        """O número do campo vira navegação -- da seta **e** da digitação (S-305).

        **A comparação é contra `page_loaded_for_index`, e não contra `page_index`.** Ir por
        `ir_para_pagina` recusaria a digitação de uma folha que o índice já aponta mas a tela ainda
        não mostra -- que é exatamente o estado em que a S-305 encontrou o programa: `page_index`
        na folha 16, a imagem da folha 1 na tela, e o rodapé dizendo "p. 16 de 20".
        """
        if self._montando or self.page_count == 0:
            return
        alvo = max(0, min(self.page_count - 1, int(valor) - 1))
        self._page_index = alvo
        if alvo != self.page_loaded_for_index or self.page_rgb is None:
            self.page_loaded_for_index = None
            self.desenhar_pagina()

    def pagina_anterior(self) -> None:
        self._ir_para(self._page_index - 1)

    def proxima_pagina(self) -> None:
        self._ir_para(self._page_index + 1)

    def _roda_pediu_pagina(self, direcao: int) -> None:
        self._ir_para(self._page_index + int(direcao))

    def _ir_para(self, alvo: int) -> None:
        """A virada de uma folha, e o que ela faz quando **não há folha para onde virar** (S-304).

        Sem a guarda, cada giro da roda na última página re-rasterizava a **mesma** folha e a
        vista voltava ao topo: quem lia o fim de uma página larga era jogado para o começo dela,
        repetidamente, sem que nada mudasse na tela. A 220 DPI cada uma dessas viagens é uma
        rasterização inteira jogada fora.

        A guarda testa `page_rgb` além do índice de propósito: só o índice tiraria também o único
        jeito de tentar de novo depois de um render que falhou.
        """
        if self.page_count == 0:
            return
        alvo = max(0, min(self.page_count - 1, int(alvo)))
        if alvo == self._page_index and self.page_rgb is not None:
            return
        self._page_index = alvo
        self._faixa_do_campo_de_pagina()
        self.page_loaded_for_index = None
        self.desenhar_pagina()

    def ir_para_pagina(self, page_index: int) -> bool:
        """Vai para uma página qualquer. Devolve se **mudou** de página.

        Existe para a galeria (S-67), que navega por diagrama e precisa arrastar o visualizador
        junto. Devolver "mudou" e não "conseguiu" é o que impede o vaivém: a galeria só reage
        quando algo de fato se moveu.
        """
        if self.page_count == 0:
            return False
        alvo = max(0, min(self.page_count - 1, int(page_index)))
        if alvo == self._page_index:
            return False
        self._ir_para(alvo)
        return True

    # -------------------------------------------------------------------------- rasterização

    def observar_dpi(self) -> None:
        """Marca que o DPI mudou -- e só re-rasteriza quando ele **parar** de mudar (S-329).

        O campo de DPI dispara a cada tecla: digitar `220` passa por `2`, `22` e `220`, e cada
        disparo custaria uma rasterização de ~0,3 s em dois DPI que ninguém pediu. O relógio de
        disparo único espera a pessoa terminar, e recomeçar a contagem é o que impede a fila.

        Mora no painel, e não na janela, porque quem sabe que a imagem em memória envelheceu é
        quem a rasterizou.
        """
        self._relogio_do_dpi.start(ESPERA_DO_DPI_MS)

    def _aplicar_dpi(self) -> None:
        try:
            dpi = int(self._dpi())
        except (TypeError, ValueError):
            return  # campo vazio no meio da digitação: não há DPI para aplicar
        if dpi == self._dpi_rasterizado:
            return
        self._dpi_rasterizado = dpi
        self.invalidar_rasterizacao()

    def invalidar_rasterizacao(self) -> None:
        """A imagem em memória não vale mais: rasteriza de novo agora (S-329).

        Quem chama é quem mudou uma decisão de **rasterização** -- hoje só o DPI. Zoom não entra
        aqui: ele reescala a mesma imagem, de propósito, e re-renderizar a cada passo de zoom
        seria trocar a fluidez por nitidez que o visor já dá.
        """
        self.page_loaded_for_index = None
        if self.source is not None:
            self.desenhar_pagina()

    def desenhar_pagina(self) -> bool:
        """Rasteriza a página atual, se ainda não estiver em memória. `True` se há imagem.

        Devolve booleano porque quem chama precisa saber se pode seguir para o OCR: falhar aqui e
        prosseguir mandaria o serviço reconhecer a página anterior.
        """
        if self.source is None:
            return False

        indice = self._page_index
        if self.page_loaded_for_index == indice and self.page_rgb is not None:
            return True

        # As caixas da página anterior morrem aqui, e não quando as novas chegarem: a detecção
        # roda em thread, e deixá-las na tela nesse intervalo apontaria para diagramas da página
        # que acabou de sair -- sobre a imagem da que entrou.
        self.limpar_caixas()
        # Antes de trocar de página, o que está no editor tem de ir para o cache da página de
        # origem -- inclusive o texto que a pessoa acabou de digitar no campo de FEN.
        self.antes_de_trocar_de_pagina.emit()
        try:
            self.estado.emit(f"Renderizando página {indice + 1}...")
            dpi = int(self._dpi())
            self.page_rgb = render_pdf_page(self.source, indice, dpi=dpi)
            self.page_loaded_for_index = indice
            self._dpi_rasterizado = dpi
            self.visor.mostrar_pagina(self.page_rgb, dpi=dpi)
            self.estado.emit(f"Página {indice + 1} pronta.")
        except Exception as exc:  # noqa: BLE001 - PDF de terceiro; a janela não pode cair
            self.page_rgb = None
            self.page_loaded_for_index = None
            QMessageBox.critical(self, "Mostrar a página", f"Falha ao renderizar página:\n{exc}")
            return False

        self.pagina_desenhada.emit(indice)
        return True

    # ------------------------------------------------------------ diagramas marcados (S-68)

    @property
    def boxes(self) -> PageBoxes | None:
        return self.visor.caixas

    def definir_caixas(self, caixas: PageBoxes) -> bool:
        """Recebe as caixas de uma página. Devolve se elas eram **desta** página.

        A recusa é o que protege a tela do resultado atrasado: a detecção roda em thread, e quem a
        pediu para a página 16 pode já estar na 17 quando ela responde. Devolver booleano em vez
        de ignorar em silêncio deixa a janela registrar o descarte.
        """
        if caixas.page_index != self._page_index:
            logger.debug(
                "Caixas da página %d descartadas: a tela está na %d.", caixas.page_index, self._page_index
            )
            return False
        self.visor.definir_caixas(caixas)
        return True

    def limpar_caixas(self) -> None:
        self.visor.definir_caixas(None)
        self.visor.selecionar(None)

    def selecionar_caixa(self, indice: int | None) -> None:
        """Marca qual diagrama está aberto no editor. `None` quando não é nenhum daqui."""
        self.visor.selecionar(indice)

    @property
    def caixa_selecionada(self) -> int | None:
        return self.visor.selecionada

    def dispensar_a_selecionada(self) -> None:
        """Pede à janela que tire o retângulo do diagrama selecionado (S-177).

        Sem seleção não há o que tirar, e dizer isso é melhor que tirar "o primeiro": até a página
        ser lida, seleção nenhuma existe, e é aí que o botão direito é o caminho.
        """
        caixas = self.visor.caixas
        if caixas is None or not len(caixas):
            self.estado.emit("Nenhuma caixa nesta página para tirar.")
            return
        if self.visor.selecionada is None:
            self.estado.emit(
                "Nenhum diagrama selecionado. Clique com o botão direito sobre a caixa que "
                "você quer tirar."
            )
            return
        self.caixa_dispensada.emit(self.visor.selecionada)

    @property
    def interruptores_de_vista(self) -> dict[str, QAction]:
        """Os interruptores de visualização, por nome de comando do menu (S-161).

        Mora aqui e não na janela porque eles são deste painel: quem acrescentar uma terceira
        preferência a declara em `ui/barra_do_pdf.ACOES` com `marcavel=True`, e ela aparece aqui
        sem ninguém lembrar de ir mexer no arquivo da janela. Desde a S-528 a lista sai da tabela
        em vez de ser escrita de novo -- eram duas linhas com o mesmo nome que a tabela já diz.
        """
        return {
            registro.acao: self.barra.acoes[registro.acao]
            for registro in barra_do_pdf.ACOES
            if registro.marcavel and registro.grupo == barra_do_pdf.VISTA
        }

    # ------------------------------------------------------------------- seleção de área

    def alternar_selecao(self) -> None:
        """Liga e desliga o modo em que o arrasto recorta em vez de mover a página.

        **"Selecionar área" é um modo, e o botão tem de dizer em qual estado ele está** (S-396):
        o rótulo troca, e `comandos.alternou` avisa as outras peles que desenham o mesmo comando.
        Ligar e desligar com a mesma aparência deixava a pessoa descobrir o estado arrastando o
        mouse sobre a folha para ver o que acontecia.
        """
        if self.visor.selecionando:
            self.desligar_selecao("Seleção de área cancelada.")
            return
        if self.source is None or self.page_rgb is None:
            # Pré-condição no rodapé (S-164). O botão volta ao estado de antes: o clique já o
            # tinha marcado, e um botão pressionado sobre um modo que não ligou é a mentira que
            # a S-396 existe para não contar.
            self.btn_selecionar.setChecked(False)
            self.estado.emit("Abra um PDF antes de selecionar uma área.")
            return
        self.visor.ativar_selecao(True)
        self._marcar_selecao(ligado=True)
        self.estado.emit("Seleção ativa: arraste no PDF para reconhecer a área automaticamente.")

    def desligar_selecao(self, frase: str = "") -> None:
        self.visor.ativar_selecao(False)
        self._marcar_selecao(ligado=False)
        if frase:
            self.estado.emit(frase)

    def _marcar_selecao(self, *, ligado: bool) -> None:
        """Põe o modo na tela nos três lugares em que ele aparece (S-396/S-528).

        **O botão pressionado é o sinal principal desde a S-528**: na fila ele desenha só o ícone,
        e um rótulo que troca não é visto por ninguém. O texto continua trocando porque a ação é
        também um item de menu -- e ali "Cancelar seleção" é o que se lê. `comandos.alternou`
        avisa as outras peles que desenham o mesmo comando.
        """
        self.btn_selecionar.setChecked(ligado)
        self.btn_selecionar.setText(
            comandos.rotulo_alternado("selecionar_area") if ligado else comandos.rotulo("selecionar_area")
        )
        comandos.alternou("selecionar_area", ligado=ligado)

    def _area_selecionada(self, regiao: tuple[int, int, int, int]) -> None:
        """A área saiu do visor em pixel de página; o painel só a entrega com a folha junto."""
        self.desligar_selecao()
        if self.page_rgb is None:  # pragma: no cover - não há seleção sem página
            return
        self.regiao_pedida.emit(np.asarray(self.page_rgb).copy(), regiao)

