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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtCore import QEventLoop, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractButton,
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
from chess_diagram_ocr.processo_de_trabalho import processo_de_trabalho
from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.rotulo import RotuloElidido, separador
from chess_diagram_ocr.qt.trabalho import Tarefa, manter_viva
from chess_diagram_ocr.qt.visor import FolhaPreparada, VisorDePagina, preparar_folha
from chess_diagram_ocr.ui import atalhos, comandos, espaco, estilos, folha_de_estilo, formato, strings, tipografia
from chess_diagram_ocr.ui.leitura_do_pdf import PASSO_DE_ZOOM, open_in_system_reader
from chess_diagram_ocr.ui.page_overlay import PageBoxes
from chess_diagram_ocr.ui.viewport import LADO_DO_DESLIZADOR, clamp_zoom, posicao_do_zoom, zoom_da_posicao

logger = logging.getLogger(__name__)

__all__ = ["ESPERA_DA_FOLHA_MS", "ESPERA_DO_DPI_MS", "FolhaRasterizada", "PainelDoPdf"]

ESPERA_DO_DPI_MS = 400
"""Quanto esperar o campo de DPI parar de mudar antes de re-rasterizar (S-329)."""

RASTERIZAR_AO_FUNDO = True
"""A bandeira do passo 15: abrir, rasterizar e reescalar fora da thread da janela.

É o padrão do produto e dos arnês. A suíte de testes do tronco a desliga uma vez, no
`conftest`, porque os testes de janela perguntam pela folha na linha seguinte a `abrir_pdf`; o
caminho ao fundo tem testes próprios, que ligam a bandeira na construção. **Desfazer o passo é
pôr `False` aqui** -- e o visor volta ao que era."""

ESPERA_DA_FOLHA_MS = 15_000
"""Quanto `aguardar_pagina` espera, no máximo, por uma rasterização que está correndo ao fundo.

Quinze segundos porque é o teto de um PDF patológico a 300 DPI num disco frio, e não um valor
de produto: o produto não espera -- quem espera são os testes e os arnês, que precisam da folha
na tela antes de medir."""


@dataclass(frozen=True)
class FolhaRasterizada:
    """O que a thread de rasterização devolve, com a chave do pedido que ela atendeu.

    A chave (`source`, `indice`, `dpi`) é o que deixa o painel recusar uma folha atrasada: virar
    dez páginas com a roda pede dez rasterizações e só a última interessa, e a resposta da
    terceira, chegando depois da décima, mostraria a folha errada sob o número certo -- o
    mesmo defeito da S-305, por outro caminho.
    """

    source: Path
    indice: int
    dpi: int
    page_rgb: np.ndarray
    folha: FolhaPreparada


def _rasterizar(
    pedido: tuple[Path, int, int],
    *,
    zoom: float,
    enquadramento: str,
    area: tuple[int, int],
    em_processo: bool,
) -> FolhaRasterizada:
    """O trabalho da thread de rasterização: o PDF vira array, e o array vira folha do Qt.

    Sem `self` de propósito -- ver `qt/visor.preparar_folha`: o que roda fora da thread da
    janela não pode ter como tocar num widget. O array vem do processo filho
    (`processo_de_trabalho.ProcessoDeTrabalho`, que explica por que uma thread não bastava) ou, em linha,
    do `render_pdf_page` de sempre.
    """
    source, indice, dpi = pedido
    if em_processo:
        page_rgb = processo_de_trabalho().rasterizar(source, indice, dpi=dpi)
    else:
        page_rgb = render_pdf_page(source, indice, dpi=dpi)
    folha = preparar_folha(page_rgb, zoom=zoom, enquadramento=enquadramento, area=area)
    return FolhaRasterizada(source=source, indice=indice, dpi=dpi, page_rgb=page_rgb, folha=folha)


def _e_outro_nome(no_botao: str, rotulo: str) -> bool:
    """Se o rotulo do botao e um **nome diferente**, e nao um glifo nem um encurtamento.

    Tres casos, e os tres apareceram relendo a saida do `c5_casos.py` depois da primeira versao
    deste conserto:

    * `zoom_mais` e `zoom_menos` tem `rotulo_curto` `"+"` e `"-"` -- o botao desenha o sinal, e nao
      ha nome nenhum ali. A dica saia `"- — Diminuir o zoom da pagina"`, que e ruido.
    * `tirar_caixa` mostra "Tirar a caixa" e se chama "Tirar a caixa do diagrama selecionado":
      o curto e o comeco do longo, e repeti-lo antes do travessao nao acrescenta nada.
    * `ler_pagina` mostra "OCR todos diagramas" e se chama "Ler esta pagina" -- **dois nomes sem
      uma palavra em comum**. Este e o unico caso em que a dica precisa dizer os dois, porque e o
      unico em que quem procura um deles nao acha o outro.
    """
    if len(no_botao) < 3 or not any(letra.isalpha() for letra in no_botao):
        return False
    comeco = no_botao.split(" (")[0].strip().lower()
    return bool(comeco) and not rotulo.lower().startswith(comeco)


def _contar_e_aquecer(pdf_path: Path, *, em_processo: bool) -> int:
    """Conta as páginas -- e, de passagem, faz o processo de rasterização nascer.

    Na mesma tarefa porque o `spawn` custa dezenas de milissegundos e esta é a primeira thread
    que existe quando um livro abre: pagá-lo aqui é pagá-lo fora da janela, antes de a primeira
    página ser pedida.
    """
    if em_processo:
        processo_de_trabalho().aquecer()
    return get_pdf_page_count(pdf_path)


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
        rasterizar_ao_fundo: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self._dpi = dpi
        if rasterizar_ao_fundo is None:
            rasterizar_ao_fundo = RASTERIZAR_AO_FUNDO
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

        self._so_de_icone: dict[str, QPushButton] = {}
        """Os botões da barra que nasceram sem texto, por ação. Ver `nomear_o_que_o_cromo_nao_desenha`."""

        self.rasterizar_ao_fundo = rasterizar_ao_fundo
        """Se abrir o livro e rasterizar a página correm numa `Tarefa` (passo 15) ou em linha.

        Em linha é o caminho dos testes de janela, que perguntam pela folha na linha seguinte;
        o resultado passa pelos **mesmos** `_livro_abriu`/`_folha_chegou` -- a bandeira muda
        onde a conta roda, e não o que acontece com ela."""
        self._abertura: Tarefa | None = None
        self._abrindo: Path | None = None
        """O livro que a tarefa em curso está contando."""
        self._abertura_pedida: Path | None = None
        """O livro pedido enquanto outro ainda era contado. O último vale."""
        self._rasterizacao: Tarefa | None = None
        self._rasterizacao_pedida: tuple[Path, int, int] | None = None
        """`(livro, página, dpi)` da rasterização em curso; ver `FolhaRasterizada`."""
        self._rasterizar_de_novo = False
        """Chegou outro pedido enquanto uma folha era rasterizada: quando ela vier, rasteriza de novo."""

        self._montar()
        self.visor.reescalar_ao_fundo = rasterizar_ao_fundo

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.folga(),) * 4)
        fora.setSpacing(espaco.folga())

        # ------------------------------------------------------ a barra, em blocos (F9-C2)
        #
        # **O que o crítico do ciclo 1 mediu:** 16 controles, **4 filas a 1920 px e 6 a 1243**, e
        # **14 dos 16 (88 %) trocando de fila** entre as duas larguras. Uma barra assim não tem
        # mapa espacial: ela flui como texto, e a pessoa reprocura o botão a cada vez que muda o
        # tamanho da janela. O item 11 do §7 pede três a quatro **blocos nomeados**, separador de
        # 1 px entre eles, e o resto fora de cena.
        #
        # **O bloco é um `QWidget` e não um vão maior**, e é o que faz a conta fechar: o
        # `LeiauteFluido` passa a refluir três itens em vez de dezesseis, então um controle nunca
        # troca de fila **em relação aos vizinhos do bloco dele**. Quatro píxeis de diferença de
        # vão não são agrupamento; um retângulo que anda inteiro é.
        #
        # **O que saiu, e para onde.** `Exportar PDF → PGN` e `Cancelar exportação` para o menu
        # Arquivo, `Marcar diagramas` e `Roda vira a página` para o menu Ver -- **os quatro já
        # estavam lá**, o que faz da barra, nesses quatro, uma segunda cópia do menu. `Abrir no
        # leitor do sistema` também: é o passo de saída do programa, não uma ação sobre a página.
        # Nenhum comando perdeu alcance: `ui/menu.MENUS` os lista, e `ui/atalhos.py` mantém as
        # teclas.
        barra = BarraFluida(self)

        livro = self._bloco(barra, "Livro", primeiro=True)
        self.btn_abrir = self._botao(livro, "abrir_pdf", self.abrir_pdf)
        # **O rótulo é elidido e pede zero de largura mínima** -- item 2 do §7. Ver
        # `qt/rotulo.RotuloElidido`: um nome de livro de 149 caracteres subia a largura mínima da
        # janela de 1243 para 1513 px e desenhava dois botões um sobre o outro.
        self.lbl_pdf = RotuloElidido(strings.NENHUM_PDF_ABERTO, livro)
        livro.layout().addWidget(self.lbl_pdf, 1)

        reconhecer = self._bloco(barra, "Reconhecer")
        # **A única ênfase da tela** (item 10 do §7): ler a página é o que esta janela faz.
        self.btn_ler_melhor = self._botao(
            reconhecer, "ler_melhor", lambda: self.leitura_pedida.emit(True), estilos.PRIMARIO
        )
        # Os três ao lado dela ficam **só com o ícone**: o rótulo por extenso somava 367 px de
        # texto ao lado da ação que manda, e era ele que empurrava a barra para a terceira fila.
        # O nome por extenso continua no `accessibleName`, na dica e no menu -- ver `_botao`.
        self.btn_ler_pagina = self._botao(
            reconhecer, "ler_pagina", lambda: self.leitura_pedida.emit(False), so_icone=True
        )
        self.btn_tirar_caixa = self._botao(
            reconhecer, "tirar_caixa", self.dispensar_a_selecionada, so_icone=True,
            glifo=strings.DISPENSAR,
        )
        # **Um modo desenha-se como modo** (S-396 relida no F9-C2): o rótulo trocava entre
        # "Selecionar área (OCR)" e o alternado, o que muda a largura do botão **e da barra**
        # quando a pessoa liga a seleção. Um botão marcável diz o mesmo estado sem mexer em
        # pixel nenhum de leiaute, e o nome por extenso continua alternando no leitor de tela.
        self.btn_selecionar = self._botao(
            reconhecer, "selecionar_area", self.alternar_selecao, so_icone=True
        )
        self.btn_selecionar.setCheckable(True)
        # **O bloco que só existe enquanto existe o que cancelar** (item 7 do §7). Ele fica
        # escondido em repouso -- é a diferença entre uma barra com um botão cinza permanente e
        # uma barra que ganha uma fila exatamente quando a pessoa precisa dela.
        #
        # **E ele mora na barra do livro, e não na de navegação**, porque a de navegação é
        # desligada **em bloco** durante uma operação longa (`_reavaliar_controles`) -- e a
        # exportação é justamente uma operação longa. O cancelar ali ficaria cinza exatamente no
        # intervalo em que ele serve, que é o defeito que `test_o_cancelar_sobrevive_ao_trancamento`
        # existe para pegar.
        self._bloco_exportacao = self._bloco(barra, "Exportação")
        self.btn_cancelar_exportacao = self._botao(
            self._bloco_exportacao, "cancelar_exportacao", self.exportacao_cancelada.emit
        )
        self._bloco_exportacao.setVisible(False)
        self._barra_do_livro = barra
        fora.addWidget(barra)

        navegacao = BarraFluida(self)
        navegar = self._bloco(navegacao, "Navegar", primeiro=True)
        self._botao(
            navegar, "pagina_anterior", self.pagina_anterior, so_icone=True, glifo=strings.ANTERIOR
        )
        # **Base 1, e a faixa nunca é `0..0`** (S-328): "página 0" não existe na contagem que o
        # campo usa, e um campo vazio com teto zero é o que fazia a seta escrever o número que o
        # resto da tela nega.
        self.campo_pagina = QSpinBox(navegar)
        self.campo_pagina.setProperty(tipografia.PROPRIEDADE_TABULAR, "true")
        self.campo_pagina.setRange(1, 1)
        # **O nome acessível diz a faixa, e nunca o valor** (F9-C2). `QSpinBox.text()` devolve
        # `"121"`, e sem nome próprio a cascata de `ui/nomes_acessiveis.py` cai nele: o leitor de
        # tela anunciava "121, campo de número" e o **nome do controle mudava a cada página**.
        # `_nomear_o_campo_de_pagina` o reescreve quando o livro abre, porque a faixa é o que ele
        # informa e ela só existe depois de contar as páginas.
        self._nomear_o_campo_de_pagina()
        self.campo_pagina.valueChanged.connect(self._pagina_digitada)
        navegar.layout().addWidget(self.campo_pagina)
        self.lbl_total = QLabel("de 0", navegar)
        self.lbl_total.setProperty(tipografia.PROPRIEDADE_TABULAR, "true")
        # Contagem é texto de apoio, não dado: o degrau `AUXILIAR` da escala (item 9 do §7).
        self.lbl_total.setProperty(folha_de_estilo.PROPRIEDADE_DE_APOIO, "true")
        navegar.layout().addWidget(self.lbl_total)
        self._botao(
            navegar, "proxima_pagina", self.proxima_pagina, so_icone=True, glifo=strings.PROXIMO
        )

        zoom = self._bloco(navegacao, "Zoom")
        self._botao(zoom, "zoom_menos", self.diminuir_zoom, so_icone=True)
        self._botao(zoom, "zoom_mais", self.aumentar_zoom, so_icone=True)
        self._botao(zoom, "ajustar_largura", self.ajustar_a_largura, so_icone=True)
        self._botao(zoom, "ajustar_pagina", self.ajustar_a_pagina, so_icone=True)

        self._barra_de_navegacao = navegacao
        fora.addWidget(navegacao)

        # **As duas preferências de vista saíram da barra e ficaram no menu `Ver`** (item 11 do
        # §7), onde elas já estavam declaradas em `ui/menu.MENUS`. As caixas continuam existindo
        # porque elas **são** o estado: o item de menu é marcável e reflete o que está aqui, o
        # estado da aplicação lê `isChecked()` ao fechar e repõe ao abrir, e `_alternou_*` é quem
        # avisa o visor. O que saiu foi o desenho -- 252 px de barra por duas preferências que
        # ninguém troca duas vezes na mesma sessão.
        self.marcar_diagramas = QCheckBox(comandos.rotulo_de_botao("marcar_diagramas"), self)
        self.marcar_diagramas.setChecked(True)
        self.marcar_diagramas.setVisible(False)
        self.marcar_diagramas.toggled.connect(self._alternou_caixas)
        self.roda_vira_pagina = QCheckBox(comandos.rotulo_de_botao("roda_vira_pagina"), self)
        self.roda_vira_pagina.setChecked(True)
        self.roda_vira_pagina.setVisible(False)
        self.roda_vira_pagina.toggled.connect(self._alternou_virada)

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

    # ------------------------------------------------------------- quem fica cinza, e por quê

    def _reavaliar_controles(self) -> None:
        """O estado de cada controle, resolvido **num lugar só**, a partir de três fatos.

        Os fatos são: há livro aberto, há operação longa em curso, há exportação rodando. Espalhar
        isto por quem causa cada mudança é como o Tk tinha três métodos (`set_ocr_controls_enabled`,
        `set_export_controls_enabled`, `disable_cancel_button`) que se sobrescreviam pela ordem de
        chamada -- e o botão de cancelar ficava cinza porque a última a falar não sabia da
        exportação.
        """
        livro = self.source is not None
        util = livro and not self._trancado
        self.btn_abrir.setEnabled(not self._trancado)
        # `selecionar_area` entrou na lista no F9-C2: ele age sobre a **página exibida** como os
        # outros três, e sem livro ele só sabia dizer "abra um PDF antes" pelo rodapé -- um botão
        # aceso que responde com uma pré-condição é um botão que promete o que não tem.
        for botao in (
            self.btn_ler_melhor, self.btn_ler_pagina, self.btn_tirar_caixa, self.btn_selecionar
        ):
            botao.setEnabled(util)
        # **O cancelar não olha `_trancado`, e é o item.** Ele só existe durante a exportação, que
        # é justamente quando tudo o mais está trancado: obedecê-lo faria o botão ficar cinza
        # exatamente na única situação em que ele serve. E agora o bloco inteiro só **aparece**
        # durante ela -- ver `_montar`.
        self.btn_cancelar_exportacao.setEnabled(self._exportando)
        self._bloco_exportacao.setVisible(self._exportando)
        self._barra_de_navegacao.setEnabled(not self._trancado)
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

    def _nomear_o_campo_de_pagina(self) -> None:
        """O nome acessível do campo de página: "Página, 1 a 289". Chamado a cada livro aberto.

        **Derivado da faixa e não do valor**, que é o defeito nº 1 da crítica do ciclo 1: um nome
        que muda quando a pessoa vira a página não identifica o controle, identifica o conteúdo.
        A faixa muda uma vez por livro; o valor muda a cada seta.
        """
        teto = self.campo_pagina.maximum()
        self.campo_pagina.setAccessibleName(f"Página, 1 a {teto}")

    def _bloco(self, barra: BarraFluida, nome: str, *, primeiro: bool = False) -> QWidget:
        """Um bloco nomeado da barra: um retângulo que reflui inteiro. Ver `_montar`.

        `primeiro` é o único que não desenha o traço de 1 px à esquerda -- um separador na borda
        da barra separaria a barra de nada.
        """
        bloco = QWidget(barra)
        # O nome do bloco é o que um leitor de tela anuncia ao entrar nele. Não é decoração:
        # sem ele a pessoa ouve doze botões seguidos sem saber onde um grupo acaba.
        bloco.setAccessibleName(nome)
        linha = QHBoxLayout(bloco)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(espaco.linha())
        if not primeiro:
            linha.addWidget(separador(bloco))
        barra.adicionar(bloco)
        return bloco

    def _botao(
        self,
        barra: BarraFluida | QWidget,
        acao: str,
        funcao: Callable[[], object],
        papel: str = estilos.NEUTRO,
        *,
        so_icone: bool = False,
        glifo: str = "",
    ) -> QPushButton:
        """Um botão do catálogo: rótulo, papel e **tecla** vêm da tabela, e não escritos aqui.

        É a regra da S-165 e da S-324 -- a mesma que `qt/janela.py` registra: antes dela, seis dos
        oito botões repetiam `ui/atalhos.py` literalmente, dois eram inventados, e **dois estavam
        trocados**.

        `so_icone` desenha o botão sem texto. **Ele não tira nada de ninguém**: o nome por extenso
        continua no `accessibleName` (é o que o leitor de tela anuncia), na dica com a tecla, e no
        menu que o `ui/menu.MENUS` monta. O que ele tira é largura de barra -- ver `_montar`.
        """
        rotulo_visivel = "" if so_icone else comandos.rotulo_de_botao(acao)
        botao = QPushButton(rotulo_visivel, barra)
        if so_icone:
            self._so_de_icone[acao] = botao
        # **O nome acessível é o rótulo por extenso, e não o texto do botão** (F9-C2).
        # O crítico do ciclo 1 mediu 28 controles que chegavam ao leitor de tela como "-",
        # "+", "|◀" ou ".md" -- o `rotulo_curto` passando pela cascata de
        # `ui/nomes_acessiveis.py` no passo `text()`. Ver `comandos.Comando.no_leitor`.
        botao.setAccessibleName(comandos.nome_acessivel(acao))
        botao.clicked.connect(funcao)
        tema.aplicar_papel(botao, papel)
        tecla = atalhos.acelerador(acao)
        motivo = self._dica_do_comando(acao, so_icone=so_icone)
        dica_em(botao, f"{motivo}\nTecla: {tecla}" if tecla else motivo)
        if so_icone:
            self._vestir_de_icone(botao, acao, papel, glifo)
        leiaute = barra.layout()
        if isinstance(barra, BarraFluida):
            barra.adicionar(botao)
        elif leiaute is not None:
            leiaute.addWidget(botao)
        return botao

    @staticmethod
    def _dica_do_comando(acao: str, *, so_icone: bool) -> str:
        """O texto da dica: por extenso, e -- no botao so-de-icone -- **com o nome do botao**.

        **O item 2 do ciclo 6, e ele sobreviveu ao primeiro conserto.** `ler_pagina` carrega dois
        nomes de proposito (`ui/comandos.Comando.rotulo_curto`): "Ler esta pagina" no menu e
        "OCR todos diagramas" no botao. O estado vazio da aba principal passou a citar o do menu
        -- um rotulo declarado, e o teste de cruzamento com o catalogo ficou verde --, mas a
        pilula da pele Foco mostra o outro e aqui, na pele classica, o botao **nao mostra nenhum**.
        Quem lia a frase e procurava "Ler esta pagina" na tela continuava nao achando: o defeito
        que o critico do ciclo 5 mediu, com o literal trocado.

        Agora a frase cita o nome do **botao**, e esta dica e o unico lugar em que ele pode
        aparecer na pele classica. O rotulo por extenso nao some: continua na mesma dica, depois
        do travessao, e no `accessibleName`, que e o que o leitor de tela anuncia (F9-C2).
        """
        rotulo = comandos.rotulo(acao)
        no_botao = comandos.rotulo_de_botao(acao)
        if so_icone and _e_outro_nome(no_botao, rotulo):
            return f"{no_botao} — {rotulo}"
        return rotulo

    def nomear_o_que_o_cromo_nao_desenha(self, cromo: QWidget | None) -> list[str]:
        """Põe **texto** no botão só-de-ícone cujo nome a pele corrente não desenha (F9-C7, §3).

        Devolve as ações que passaram a mostrar o nome. Recebe o **contêiner do cromo** e lê dele
        o que a fila ou a fita desenharam de verdade -- os `text()` dos botões montados, e não uma
        segunda lista dizendo quem cada pele mostra. Uma lista dessas divergiria do cromo no dia
        em que alguém tirasse um comando do destaque, que é a forma exata do defeito que este
        método fecha. `None`, ou um contêiner vazio, é a pele clássica: ela não desenha nome
        nenhum acima do divisor, e é por isso que é ela quem ganha o texto no botão.

        **Por que existe.** `MENSAGEM_VAZIA` -- a primeira frase que o produto mostra -- manda
        usar *"OCR todos diagramas"*, o nome de `ler_pagina` no botão. Na pele **Foco** a pílula
        escreve esse nome; na **clássica**, que é o padrão, o botão da barra é só-de-ícone e
        **zero controles visíveis o escrevem**, nas três larguras. O que o olho acha a 40 px, em
        azul, é `OCR melhor diagrama` -- `ler_melhor`, **outro comando**: lê um diagrama, não a
        página. A frase não deixava de orientar; ela orientava para o controle errado, que é a
        forma cara do defeito (F9-C7, §3.1).

        **O ciclo 6 tentou fechar isto pela dica, e a dica não é a tela**: ela exige que o
        ponteiro pouse sobre o ícone certo, e quem lê a frase não sabe qual é o ícone certo --
        é justamente isso que a frase deveria dizer. A régua que o mesmo ciclo escreveu aceitava
        `toolTip()` como "na tela" e ficou verde com nada desenhado. Ver
        `tests/test_qt_janela.EstadoVazioNaTelaTests`.

        **A regra é `_e_outro_nome`, e ela é a mesma da dica**: só ganha texto o botão cujo nome
        de botão é um **nome diferente** do rótulo por extenso -- não um glifo (`+`, `-`) nem um
        encurtamento (`"Tirar a caixa"` de `"Tirar a caixa do diagrama selecionado"`). Hoje o
        catálogo tem exatamente um caso, `ler_pagina`; a regra é escrita para o próximo.

        **E ela não duplica nada**: onde o cromo já escreve o nome -- a pílula da Foco, o rótulo
        da fita --, o botão da barra fica só com o ícone. Dois controles visíveis com o mesmo
        rótulo é o defeito do §4 item 11 do mesmo ciclo, e fechar um item abrindo outro não é
        fechar.
        """
        # **O espaço em branco é normalizado, e isso é uma medição e não zelo.** A fita quebra o
        # rótulo em duas linhas (`ui/medidas_da_fita.quebrar_rotulo`), então o `text()` dela é
        # `"OCR todos\ndiagramas"` -- o **mesmo nome**, com uma quebra no meio. Comparar o
        # literal fazia a barra do visor escrever o nome uma segunda vez na pele fita, que é a
        # duplicação que este método existe para não criar.
        #
        # **E o botão tem de estar VISÍVEL, e isto era o furo** (F9-C9, §1 critério 8). O
        # crítico do ciclo 9 montou seis cromos de mentira e o método respondeu certo em cinco;
        # o caso 5 -- *"um botão escondido com o nome"* -- fazia a barra **não** escrever o nome,
        # porque o `text()` de um botão escondido continua lá. Hoje nenhum dos três cromos monta
        # botão escondido (conferido em `fila.py`, `fita.py` e `barra.py`: nenhum chama `hide()`
        # nem `setVisible(False)`), então o número publicado era verdade -- **e é por isso que
        # esta linha é barata e obrigatória**: o que o portão que cobra este método pergunta é
        # "quantos controles **visíveis** desenham o nome", e o método respondia sobre outra
        # coisa. Um dia de diferença entre as duas perguntas é um estado vazio que manda apertar
        # um nome que ninguém vê.
        #
        # **`isVisibleTo(cromo)` e não `isVisible()`, e a diferença foi medida**: este método é
        # chamado de `_montar_o_cromo`, que corre no `__init__` da janela -- **antes** do
        # `show()`. Com `isVisible()` todos os botões do cromo respondem `False` ali, o conjunto
        # `desenhados` sai vazio, e a barra do visor escreve o nome que a fita já escreve --
        # dois controles com o mesmo rótulo, que é exatamente o item que este método fecha.
        # `isVisibleTo` pergunta o que importa: *este botão aparece quando o cromo aparecer?*
        botoes = cromo.findChildren(QAbstractButton) if cromo is not None else []
        desenhados = {
            " ".join(botao.text().replace("&", "").split())
            for botao in botoes
            if botao.isVisibleTo(cromo)
        }
        nomeados: list[str] = []
        for acao, botao in self._so_de_icone.items():
            rotulo = comandos.rotulo(acao)
            no_botao = comandos.rotulo_de_botao(acao)
            if not _e_outro_nome(no_botao, rotulo):
                continue
            mostra = no_botao not in desenhados
            botao.setText(no_botao if mostra else "")
            tecla = atalhos.acelerador(acao)
            motivo = self._dica_do_comando(acao, so_icone=not mostra)
            dica_em(botao, f"{motivo}\nTecla: {tecla}" if tecla else motivo)
            if mostra:
                nomeados.append(acao)
        return nomeados

    def _vestir_de_icone(self, botao: QPushButton, acao: str, papel: str, glifo: str = "") -> None:
        """Põe o ícone do catálogo no botão sem texto, e um piso de área de clique.

        **Sem ícone o botão fica quadrado e vazio, e isso é pior que o rótulo largo** -- então o
        `so_icone` só vale quando o catálogo declara um desenho. Um comando sem ícone volta ao
        texto, que é a resposta legível. `zoom_menos` e `zoom_mais` têm rótulo de um caractere
        (`-` e `+`) e ícone: nesses o texto vai embora e o desenho fica, que é a troca boa.
        """
        # O desenho ocupa uma linha de texto, e não duas: um ícone maior que o rótulo ao lado
        # dele desequilibra a fila, e cada 12 px a mais em quatro botões é uma fila a mais na
        # barra de 500 px -- que é a conta que o item 11 do §7 pede para fechar.
        lado = espaco.folga() + espaco.linha()
        nome_do_icone = comandos.comando(acao).icone
        desenho = (
            qt_icones.icone(
                nome_do_icone, lado, tema.cor_atual(folha_de_estilo.tinta_do_papel(papel))
            )
            if nome_do_icone
            else None
        )
        if desenho is None:
            # Sem ícone declarado: o glifo, se houver, e o rótulo por extenso se não houver.
            # `ui/icones.ICONES` é fechada contra o catálogo de comandos nos dois sentidos, então
            # acrescentar um desenho aqui não é uma linha -- é uma linha em cada lado, e três
            # comandos deste painel não têm arte. O glifo é `strings`, e vem do mesmo bloco
            # Unicode que a S-506 escolheu justamente para desenhar em qualquer fonte.
            botao.setText(glifo or comandos.rotulo_de_botao(acao))
            if glifo:
                botao.setMinimumWidth(lado + espaco.folga())
            return
        botao.setIcon(desenho)
        botao.setIconSize(QSize(lado, lado))
        # O alvo de clique não pode encolher com o rótulo: o piso da S-442 para um controle de
        # ponteiro, e um botão de ícone sem piso sai com a largura do desenho.
        botao.setMinimumWidth(lado + espaco.folga())

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
        self.lbl_zoom.setProperty(tipografia.PROPRIEDADE_TABULAR, "true")
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

    @property
    def enquadramento(self) -> str:
        """O ajuste em vigor no visor. A janela o grava com o zoom (F9-C3)."""
        return self.visor.enquadramento

    def definir_enquadramento(self, enquadramento: str) -> None:
        self.visor.definir_enquadramento(enquadramento)

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
        """Troca o livro aberto. **Abre antes de trocar** (S-123) -- e abre fora da thread (passo 15).

        A ordem é a correção. Com o aviso antes da abertura, um PDF que não abria já tinha limpado
        as caixas da página, descartado os resultados do livro anterior e apontado a Galeria para
        o arquivo quebrado: **a tela continuava mostrando o livro anterior e o programa, por
        dentro, estava no que não abriu.** O `Ctrl+S` seguinte gravava a amostra sob o nome errado.

        Contar as páginas é abrir o documento de verdade, então serve de validação sem custo
        próprio: o `page_count` que ela devolve é o mesmo que seria usado adiante. Num disco frio
        essa contagem custou 19,5 ms medidos -- por isso ela também vai para a tarefa, e o painel
        só passa a apontar para o livro em `_livro_abriu`, com a contagem na mão.

        **Dois pedidos seguidos: o último vale.** Se alguém abre outro livro enquanto o primeiro
        ainda está sendo contado, o primeiro é descartado quando responder.
        """
        pdf_path = Path(pdf_path)
        if self._abertura is not None:
            self._abertura_pedida = pdf_path
            return
        self._abertura_pedida = None
        self._abrindo = pdf_path
        self.estado.emit(f"Abrindo {pdf_path.name}…")
        # **Métodos ligados, e não `lambda`**: o PyQt desfaz a ligação a um método quando o
        # painel morre, e uma `lambda` chamaria um widget já destruído -- exceção num slot, que
        # derruba o processo (ver `trabalho.DeteccaoDeFundo`).
        self._executar(
            lambda: _contar_e_aquecer(pdf_path, em_processo=self.rasterizar_ao_fundo),
            pronto=self._livro_abriu,
            falhou=self._livro_nao_abriu,
            nome=f"abertura de {pdf_path.name}",
            guardar="_abertura",
        )

    def _livro_abriu(self, page_count: object) -> None:
        """A contagem chegou: agora, e só agora, o painel aponta para o livro novo."""
        self._abertura = None
        pdf_path, self._abrindo = self._abrindo, None
        if pdf_path is None:  # pragma: no cover - não há chegada sem pedido
            return
        if self._abertura_pedida is not None and self._abertura_pedida != pdf_path:
            self._reabrir_o_pedido()
            return
        self.source = pdf_path
        self.name = pdf_path.name
        self.page_count = int(page_count)  # type: ignore[call-overload]
        # **Só o nome do livro.** A contagem de páginas está a uma fila de distância, no
        # `de 289` ao lado do campo de página, e repeti-la aqui custava 51 px da barra mais
        # estreita da janela -- ver `qt/rotulo.LARGURA_DESEJADA`.
        self.lbl_pdf.definir_texto(self.name)
        self.lbl_total.setText(f"de {self.page_count}")
        self._reavaliar_controles()
        self.abriu_pdf.emit(pdf_path)

        alvo = max(0, min(self.page_count - 1, self._pagina_inicial_de(pdf_path)))
        self._page_index = alvo
        self._faixa_do_campo_de_pagina()
        self.page_loaded_for_index = None
        self.desenhar_pagina()

    def _livro_nao_abriu(self, _mensagem: str, exc: object) -> None:
        self._abertura = None
        pdf_path, self._abrindo = self._abrindo, None
        if pdf_path is None:  # pragma: no cover - não há falha sem pedido
            return
        logger.error("Falha ao abrir %s.", pdf_path, exc_info=exc if isinstance(exc, BaseException) else None)
        if self._abertura_pedida is not None and self._abertura_pedida != pdf_path:
            self._reabrir_o_pedido()
            return
        preservado = self.source is not None and self.source != pdf_path
        resto = f"\n\n{self.name} continua aberto." if preservado else ""
        QMessageBox.critical(self, "Abrir PDF", f"Falha ao abrir {pdf_path.name}:\n{exc}{resto}")

    def _reabrir_o_pedido(self) -> None:
        pedido, self._abertura_pedida = self._abertura_pedida, None
        if pedido is not None:
            self.load_pdf(pedido)

    # --------------------------------------------------------- a conta, em linha ou ao fundo

    def _executar(
        self,
        funcao: Callable[[], Any],
        *,
        pronto: Callable[[Any], None],
        falhou: Callable[[str, object], None],
        nome: str,
        guardar: str,
    ) -> None:
        """Roda `funcao` numa `Tarefa` -- ou em linha, se `rasterizar_ao_fundo` está desligado.

        Os dois caminhos entregam pelo mesmo `pronto`/`falhou`, e é isso que faz a bandeira ser
        uma bandeira e não um segundo programa: o teste que roda em linha exercita a mesma
        chegada que o produto recebe por sinal.
        """
        if not self.rasterizar_ao_fundo:
            try:
                resultado = funcao()
            except Exception as exc:  # noqa: BLE001 - é a borda que a `Tarefa` também tem
                falhou(str(exc), exc)
                return
            pronto(resultado)
            return
        tarefa = manter_viva(Tarefa(funcao, nome=nome))
        tarefa.pronto.connect(pronto)
        tarefa.falhou.connect(falhou)
        setattr(self, guardar, tarefa)
        tarefa.start()

    @property
    def ocupado(self) -> bool:
        """Se há abertura ou rasterização correndo ao fundo."""
        return self._abertura is not None or self._rasterizacao is not None

    def aguardar_pagina(self, limite_ms: int = ESPERA_DA_FOLHA_MS) -> bool:
        """Roda a linha de eventos até a folha pedida estar na tela. Devolve se está.

        **Não é chamada pelo produto.** É o que os testes e os arnês (`caissa.ui.audit.*`) chamam
        depois de `load_pdf`/`ir_para_pagina`, porque eles perguntam pela folha na linha seguinte
        e o produto não: ele deixa a página anterior na tela e troca quando a nova chega.
        """
        if self.ocupado:
            laco = QEventLoop(self)
            relogio = QTimer(self)
            relogio.timeout.connect(lambda: laco.quit() if not self.ocupado else None)
            relogio.start(5)
            QTimer.singleShot(limite_ms, laco.quit)
            laco.exec()
            relogio.stop()
        return self.page_loaded_for_index == self._page_index and self.page_rgb is not None

    # ------------------------------------------------------------------------------ páginas

    @property
    def page_index(self) -> int:
        return self._page_index

    def _faixa_do_campo_de_pagina(self) -> None:
        """A faixa do campo em base 1: de 1 até o total de folhas (S-328)."""
        self._montando = True
        try:
            self.campo_pagina.setRange(1, max(self.page_count, 1))
            self._nomear_o_campo_de_pagina()
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
        """Mostra a página atual: em memória, agora; senão, rasteriza ao fundo e troca quando vier.

        Devolve se a folha **já está** na tela. Quem precisa dela para seguir -- o OCR, o detector
        -- lê `page_rgb`, que só deixa de ser `None` quando a folha chega; até lá a página
        anterior continua visível e o rodapé diz o que está acontecendo. É o contrato do §11.3
        para operação longa, e a rasterização a 300 DPI custa 45–68 ms medidos (passo 15).
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
        self.estado.emit(f"Renderizando página {indice + 1}…")
        self._pedir_rasterizacao()
        return self.page_loaded_for_index == indice and self.page_rgb is not None

    def _pedir_rasterizacao(self) -> None:
        """Uma rasterização de cada vez, e só a última espera -- como `DeteccaoDeFundo`."""
        if self._rasterizacao is not None:
            self._rasterizar_de_novo = True
            return
        if self.source is None:
            return
        try:
            dpi = int(self._dpi())
        except (TypeError, ValueError):
            dpi = self._dpi_rasterizado or 220
        pedido = (self.source, self._page_index, dpi)
        enquadramento, area = self.visor.foto_do_enquadramento()
        zoom = self.visor.zoom
        self._rasterizacao_pedida = pedido
        self._rasterizar_de_novo = False
        em_processo = self.rasterizar_ao_fundo
        self._executar(
            lambda: _rasterizar(
                pedido, zoom=zoom, enquadramento=enquadramento, area=area, em_processo=em_processo
            ),
            pronto=self._folha_chegou,
            falhou=self._folha_falhou,
            nome=f"rasterização da página {pedido[1] + 1}",
            guardar="_rasterizacao",
        )

    def _folha_chegou(self, folha: FolhaRasterizada) -> None:
        """A folha rasterizada voltou. Só entra se ainda for a que a tela pede."""
        self._rasterizacao = None
        self._rasterizacao_pedida = None
        atual = self.source is not None and (folha.source, folha.indice) == (self.source, self._page_index)
        de_novo, self._rasterizar_de_novo = self._rasterizar_de_novo, False
        if atual:
            # Mesmo que outro pedido tenha chegado no meio (o DPI mudou), esta folha é desta
            # página: vale mais na tela do que a página anterior, enquanto a outra não vem.
            self._mostrar(folha)
        # O que a tela pede pode ter mudado no meio: outra página, outro livro, ou esta página
        # noutro DPI. Se o pedido do meio era desta página neste DPI, esta folha já o atendeu.
        if self.source is not None and (
            self.page_loaded_for_index != self._page_index
            or (de_novo and self._dpi_rasterizado != self._dpi_pedido())
        ):
            self._pedir_rasterizacao()

    def _dpi_pedido(self) -> int | None:
        try:
            return int(self._dpi())
        except (TypeError, ValueError):
            return None

    def _mostrar(self, folha: FolhaRasterizada) -> None:
        self.page_rgb = folha.page_rgb
        self.page_loaded_for_index = folha.indice
        self._dpi_rasterizado = folha.dpi
        self.visor.mostrar_pagina(folha.page_rgb, dpi=folha.dpi, folha=folha.folha)
        self.estado.emit(f"Página {folha.indice + 1} pronta.")
        self.pagina_desenhada.emit(folha.indice)

    def _folha_falhou(self, _mensagem: str, exc: object) -> None:
        self._rasterizacao = None
        pedido, self._rasterizacao_pedida = self._rasterizacao_pedida, None
        if self._rasterizar_de_novo:
            self._rasterizar_de_novo = False
            self._pedir_rasterizacao()
            return
        self.page_rgb = None
        self.page_loaded_for_index = None
        logger.error("Falha ao renderizar %s.", pedido, exc_info=exc if isinstance(exc, BaseException) else None)
        QMessageBox.critical(self, "Mostrar a página", f"Falha ao renderizar página:\n{exc}")

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
        self._marcar_selecao(ligado=True)
        comandos.alternou("selecionar_area", ligado=True)
        self.estado.emit("Seleção ativa: arraste no PDF para reconhecer a área automaticamente.")

    def desligar_selecao(self, frase: str = "") -> None:
        self.visor.ativar_selecao(False)
        self._marcar_selecao(ligado=False)
        comandos.alternou("selecionar_area", ligado=False)  # S-396
        if frase:
            self.estado.emit(frase)

    def _marcar_selecao(self, *, ligado: bool) -> None:
        """O estado do modo de seleção, no botão. Ver `alternar_selecao`.

        O que muda é a marca e o **nome**, não o texto: o nome é o que um leitor de tela anuncia,
        e é ele que precisa dizer "Sair da seleção de área" quando o modo está ligado.
        """
        self.btn_selecionar.setChecked(ligado)
        nome = (
            comandos.rotulo_alternado("selecionar_area")
            if ligado
            else comandos.nome_acessivel("selecionar_area")
        )
        self.btn_selecionar.setAccessibleName(nome)
        dica_em(self.btn_selecionar, nome)

    def _area_selecionada(self, regiao: tuple[int, int, int, int]) -> None:
        """A área saiu do visor em pixel de página; o painel só a entrega com a folha junto."""
        self.desligar_selecao()
        if self.page_rgb is None:  # pragma: no cover - não há seleção sem página
            return
        self.regiao_pedida.emit(np.asarray(self.page_rgb).copy(), regiao)

