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
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.pdf_io import get_pdf_page_count, render_pdf_page
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.visor import VisorDePagina
from chess_diagram_ocr.ui import atalhos, comandos, espaco, estilos, formato
from chess_diagram_ocr.ui.leitura_do_pdf import PASSO_DE_ZOOM, open_in_system_reader
from chess_diagram_ocr.ui.page_overlay import PageBoxes
from chess_diagram_ocr.ui.viewport import LADO_DO_DESLIZADOR, clamp_zoom, posicao_do_zoom, zoom_da_posicao

logger = logging.getLogger(__name__)

__all__ = ["ESPERA_DO_DPI_MS", "PainelDoPdf"]

ESPERA_DO_DPI_MS = 400
"""Quanto esperar o campo de DPI parar de mudar antes de re-rasterizar (S-329)."""


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
    regiao_pedida = pyqtSignal(object, object)
    """`(página RGB, (x0, y0, x1, y1))` -- o recorte que a seleção de área devolveu."""

    preferencias_mudaram = pyqtSignal()
    """Um interruptor de visualização mudou. O estado da aplicação lembra dele entre execuções."""

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

        self._relogio_do_dpi = QTimer(self)
        self._relogio_do_dpi.setSingleShot(True)
        self._relogio_do_dpi.timeout.connect(self._aplicar_dpi)

        self._montar()

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.folga(),) * 4)
        fora.setSpacing(espaco.folga())

        barra = BarraFluida(self)
        self.btn_abrir = self._botao(barra, "abrir_pdf", self.abrir_pdf, estilos.PRIMARIO)
        self.lbl_pdf = QLabel("nenhum PDF aberto", barra)
        barra.adicionar(self.lbl_pdf)
        self.btn_leitor = QPushButton(comandos.rotulo_de_botao("abrir_no_leitor"), barra)
        self.btn_leitor.clicked.connect(self.abrir_no_leitor_do_sistema)
        self.btn_leitor.setEnabled(False)
        tema.aplicar_papel(self.btn_leitor, estilos.NEUTRO)
        dica_em(
            self.btn_leitor,
            "Abre o livro no leitor de PDF do sistema, na janela dele: rolagem contínua e busca "
            "de texto.\nFica cinza enquanto não há livro aberto.",
        )
        barra.adicionar(self.btn_leitor)
        fora.addWidget(barra)

        navegacao = BarraFluida(self)
        self._botao(navegacao, "pagina_anterior", self.pagina_anterior)
        # **Base 1, e a faixa nunca é `0..0`** (S-328): "página 0" não existe na contagem que o
        # campo usa, e um campo vazio com teto zero é o que fazia a seta escrever o número que o
        # resto da tela nega.
        self.campo_pagina = QSpinBox(navegacao)
        self.campo_pagina.setRange(1, 1)
        self.campo_pagina.valueChanged.connect(self._pagina_digitada)
        navegacao.adicionar(self.campo_pagina)
        self.lbl_total = QLabel("de 0", navegacao)
        navegacao.adicionar(self.lbl_total)
        self._botao(navegacao, "proxima_pagina", self.proxima_pagina)
        self._botao(navegacao, "zoom_menos", self.diminuir_zoom)
        self._botao(navegacao, "zoom_mais", self.aumentar_zoom)
        self._botao(navegacao, "ajustar_largura", self.ajustar_a_largura)
        self._botao(navegacao, "ajustar_pagina", self.ajustar_a_pagina)
        self.btn_selecionar = self._botao(navegacao, "selecionar_area", self.alternar_selecao)

        self.marcar_diagramas = QCheckBox(comandos.rotulo_de_botao("marcar_diagramas"), navegacao)
        self.marcar_diagramas.setChecked(True)
        self.marcar_diagramas.toggled.connect(self._alternou_caixas)
        navegacao.adicionar(self.marcar_diagramas)
        self.roda_vira_pagina = QCheckBox(comandos.rotulo_de_botao("roda_vira_pagina"), navegacao)
        self.roda_vira_pagina.setChecked(True)
        self.roda_vira_pagina.toggled.connect(self._alternou_virada)
        navegacao.adicionar(self.roda_vira_pagina)
        fora.addWidget(navegacao)

        self.visor = VisorDePagina(self)
        self.visor.caixa_clicada.connect(self.caixa_clicada)
        self.visor.caixa_dispensada.connect(self.caixa_dispensada)
        self.visor.pagina_pedida.connect(self._roda_pediu_pagina)
        self.visor.zoom_mudou.connect(self._zoom_do_visor)
        self.visor.area_selecionada.connect(self._area_selecionada)
        self.visor.selecao_pequena.connect(
            lambda: self.estado.emit("Seleção muito pequena. Tente novamente.")
        )
        fora.addWidget(self.visor, 1)
        fora.addLayout(self._rodape_de_zoom())

    def _botao(self, barra: BarraFluida, acao: str, funcao: Callable[[], object], papel: str = estilos.NEUTRO) -> QPushButton:
        """Um botão do catálogo: rótulo, papel e **tecla** vêm da tabela, e não escritos aqui.

        É a regra da S-165 e da S-324 -- a mesma que `qt/janela.py` registra: antes dela, seis dos
        oito botões repetiam `ui/atalhos.py` literalmente, dois eram inventados, e **dois estavam
        trocados**.
        """
        botao = QPushButton(comandos.rotulo_de_botao(acao), barra)
        botao.clicked.connect(funcao)
        tema.aplicar_papel(botao, papel)
        tecla = atalhos.acelerador(acao)
        motivo = comandos.rotulo(acao)
        dica_em(botao, f"{motivo}\nTecla: {tecla}" if tecla else motivo)
        barra.adicionar(botao)
        return botao

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
            self.lbl_pdf.setText(f"{self.name} ({self.page_count} págs)")
            self.lbl_total.setText(f"de {self.page_count}")
            self.btn_leitor.setEnabled(True)
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

    def _alternou_caixas(self, ligado: bool) -> None:
        self.visor.alternar_caixas(ligado)
        self.preferencias_mudaram.emit()

    def _alternou_virada(self, ligado: bool) -> None:
        self.visor.virar_paginas = ligado
        self.preferencias_mudaram.emit()

    @property
    def interruptores_de_vista(self) -> dict[str, QCheckBox]:
        """Os dois interruptores de visualização, por nome de comando do menu (S-161).

        Mora aqui e não na janela porque as duas caixas são deste painel: quem acrescentar uma
        terceira preferência a declara ao lado das outras duas, e ela aparece no menu sem ninguém
        lembrar de ir mexer no arquivo da janela.
        """
        return {
            "marcar_diagramas": self.marcar_diagramas,
            "roda_vira_pagina": self.roda_vira_pagina,
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
            # Pré-condição no rodapé (S-164).
            self.estado.emit("Abra um PDF antes de selecionar uma área.")
            return
        self.visor.ativar_selecao(True)
        self.btn_selecionar.setText(comandos.rotulo_alternado("selecionar_area"))
        comandos.alternou("selecionar_area", ligado=True)
        self.estado.emit("Seleção ativa: arraste no PDF para reconhecer a área automaticamente.")

    def desligar_selecao(self, frase: str = "") -> None:
        self.visor.ativar_selecao(False)
        self.btn_selecionar.setText(comandos.rotulo_de_botao("selecionar_area"))
        comandos.alternou("selecionar_area", ligado=False)  # S-396
        if frase:
            self.estado.emit(frase)

    def _area_selecionada(self, regiao: tuple[int, int, int, int]) -> None:
        """A área saiu do visor em pixel de página; o painel só a entrega com a folha junto."""
        self.desligar_selecao()
        if self.page_rgb is None:  # pragma: no cover - não há seleção sem página
            return
        self.regiao_pedida.emit(np.asarray(self.page_rgb).copy(), regiao)

