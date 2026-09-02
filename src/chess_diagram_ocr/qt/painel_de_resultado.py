"""O painel "Resultado": o editor de diagramas reconhecidos, no Qt (S-31/S-49/S-503).

**O que ele é.** O lugar onde se conserta o que o OCR leu -- o tabuleiro editável da S-20, o
painel de legalidade da S-21, o histórico por diagrama da S-229 e a gravação da amostra. É o
porte de `ui/result_panel.py`, e a comparação de tamanho diz o que a migração de fato é: **1.402
linhas lá, e nem um terço aqui.** A diferença não é código omitido; é o que já estava fora do Tk
e agora é chamado em vez de reescrito.

O que este arquivo **não** escreve, porque já existe e é puro:

- `ui/editor_model.DiagramEditorModel` -- as três listas paralelas, o vínculo e, sobretudo,
  `save_target()`: se `Ctrl+S` grava amostra nova ou regrava a linha existente. É a regra mais
  delicada da interface (S-49), e os dois frontends a obedecem.
- `ui/historico.Historico` -- a pilha de desfazer, **por diagrama** (S-229).
- `ui/legality.explain_position` -- o problema em pt-BR e as casas culpadas.
- `ui/board_edit` e `ui/board_model` -- as operações sobre o campo de peças e a máquina de
  estados do tabuleiro, já usadas por `qt/tabuleiro_editavel.py`.
- `ui/comandos`, `ui/strings`, `ui/estilos`, `ui/espaco` -- rótulo, papel e espaço.

**Por que ele é um widget e não parte da janela.** Era parte dela: `qt/janela.py` tinha a lista, o
tabuleiro, a FEN e o salvar embutidos, e foi assim que a gravação chegou na S-502. Isso não
escala pela mesma razão que fez a S-31 tirar o editor do `ChessOcrTkApp`: com o estado do PDF, o
do editor e o do estudo no mesmo objeto, um método de navegação de página mexe no que está sendo
editado sem que nada diga. A janela passa a conversar com este painel por sinal.

**As quatro origens estão aqui (S-505).** Página de PDF (`carregar_pagina`), item da fila de
revisão (`carregar_item_de_revisao`), amostra do dataset (`carregar_amostra`) e imagem avulsa
(`carregar_avulsos`). Cada uma declara o seu vínculo, e é o vínculo que impede `Ctrl+S` de gravar
pelo caminho errado: a amostra do dataset **regrava a linha** em vez de criar uma segunda com o
rótulo velho ao lado do novo -- ver `salvar_atual` e `ui/editor_model.save_target()`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.config import DEFAULT_DPI, DEFAULT_MAX_BOARDS
from chess_diagram_ocr.fen_utils import is_valid_fen, square_name
from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.atalhos import sequencia_qt
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import DicaEmDesabilitado, dica_em
from chess_diagram_ocr.qt.tabuleiro_editavel import TabuleiroEditavel
from chess_diagram_ocr.semantics import compose_fen
from chess_diagram_ocr.service import OcrService, RecognitionOrigin, RecognizedDiagram
from chess_diagram_ocr.ui import atalhos, board_edit, comandos, espaco, estilos, strings, tipografia, tokens
from chess_diagram_ocr.ui.editor_model import DiagramEditorModel, EditorBinding, SaveKind, SaveTarget
from chess_diagram_ocr.ui.historico import Historico
from chess_diagram_ocr.ui.legality import ILLEGAL_SAVE_TITLE, explain_position, illegal_save_question
from chess_diagram_ocr.ui.page_results import (
    PageOcrParams,
    PageResults,
    PageResultsCache,
    PageSwitch,
    decide_page_switch,
)
from chess_diagram_ocr.ui.sala_declarada import posicao_de_estudo

logger = logging.getLogger(__name__)

__all__ = ["MENSAGEM_VAZIA", "PainelDeResultado"]

MENSAGEM_VAZIA = (
    "Nenhum diagrama aberto. Clique num diagrama marcado da página, "
    'ou use "Ler página" para ler a página inteira.'
)
"""O mesmo texto de `ui/result_panel.MENSAGEM_VAZIA`, com o nome do botão desta janela.

**O estado vazio é um item, e não zelo** (S-170): sem ele o painel abre com um tabuleiro na
posição inicial e o campo de FEN vazio -- parece um diagrama reconhecido, e quem clicasse em
"Salvar" gravaria a posição inicial no `labels.csv` como se fosse leitura de uma página."""

MOTIVO_SEM_DIAGRAMA = "Não há diagrama aberto."
MOTIVO_SEM_DESFAZER = "Não há mudança anterior neste diagrama."
MOTIVO_SEM_REFAZER = "Não há o que refazer: nada foi desfeito."
"""As três razões de um botão estar cinza, ditas na dica -- a regra da S-165, que achou treze
botões cinzas e mudos. As duas do histórico são diferentes entre si, e quem olha precisa saber
qual é a sua: sem diagrama não há posição nenhuma; com diagrama e pilha vazia, não há mudança
anterior **neste** diagrama, que é a consequência de a pilha ser por diagrama."""

ALTURA_MAXIMA_DA_LISTA = 140
"""Cinco linhas. A página mais cheia do acervo tem nove diagramas, e a lista rola."""


class PainelDeResultado(QWidget):
    """O editor inteiro: lista, tabuleiro, FEN, lado, legalidade, histórico e gravação."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status. A janela decide onde ela aparece."""

    salvou = pyqtSignal(int)
    """O índice do diagrama gravado. A janela usa para carimbar a caixa de verde sobre a página."""

    selecionou = pyqtSignal(int)
    """O diagrama que passou a estar em edição, para o visor destacar a caixa dele."""

    posicao_mudou = pyqtSignal()
    """A posição mostrada aqui mudou -- por troca de diagrama, por casa corrigida ou por desfazer.

    **É o `on_sync_study` do outro frontend, com um sinal no lugar de três chamadas** (S-512). Lá o
    `result_panel` o chamava em três pontos e `app_tkinter.py:1537` o repassava à sala; o porte para
    o Qt não trouxe nenhum dos três, e a caixa "Seguir OCR selecionado" -- marcada de fábrica --
    deixou de seguir qualquer coisa.

    Sai de `_atualizar_tudo` porque é ali que os três pontos do Tk se encontram: um lugar só, que é
    a mesma razão de aquele método existir. Quem escuta é a sala, e **quem decide se há o que
    fazer** é `ui/sala_declarada.decidir_sincronia` -- este sinal dispara a cada casa corrigida, e
    reabrir o estudo a cada uma apagaria a pilha de desfazer de quem o estava analisando."""

    revisou = pyqtSignal(int, str, str)
    """`(posição na fila, FEN, lado)` -- o item da fila que acabou de ser corrigido e gravado.

    A janela o repassa à aba de Revisão, que o fecha (S-22). **Sinal e não chamada direta** pela
    razão de sempre neste pacote: o painel de Resultado não conhece o de Revisão, e não deveria --
    são abas irmãs, e quem as liga é a janela."""

    regravou = pyqtSignal()
    """A linha de uma amostra do dataset foi regravada. A aba Dataset relê o que mudou."""

    def __init__(
        self,
        servico: OcrService,
        *,
        csv_de_rotulos: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._servico = servico
        self._csv_de_rotulos = Path(csv_de_rotulos)
        self.modelo = DiagramEditorModel()
        self.historico = Historico()
        self._edicao = 0
        """Quantas edições este painel recebeu. É o desempate do `Ctrl+Z` sem foco (S-243)."""
        """A pilha de desfazer, **por diagrama** (S-229): ela é zerada ao trocar de diagrama, e
        é isso que faz `Ctrl+Z` devolver a posição anterior *deste* diagrama em vez de andar para
        trás na correção do vizinho."""
        self._montando = False
        """Guarda contra o laço: escrever na FEN ou no rádio de lado dispara o sinal deles, que
        chamaria de volta quem acabou de escrever. É o `_montando` do Tk sob outro nome."""

        self.paginas = PageResultsCache()
        """O que já foi lido de cada página, para virar a página e voltar não custar outra leitura.

        **A chave inclui os parâmetros do OCR**, e é o que impede o cache de responder sobre uma
        leitura feita com outro DPI ou outro teto de diagramas -- ver `PageResultsCache.get`."""
        self._parametros: Callable[[], PageOcrParams] = lambda: PageOcrParams(
            dpi=DEFAULT_DPI, max_boards=DEFAULT_MAX_BOARDS, orientation="auto", model_path=""
        )
        """Os parâmetros com que a página foi lida. A janela substitui pelos dela na montagem;
        o padrão existe para o painel montado sozinho num teste ter uma resposta.

        **Os quatro campos são obrigatórios**, então a classe não serve de padrão: `PageOcrParams`
        sem argumento é `TypeError`, e o painel montado sozinho quebraria na primeira virada de
        página em vez de responder."""
        self._documento: Callable[[], str] = str
        self.diagramas_salvos: Callable[[str, int], set[int]] = lambda _doc, _pag: set()
        """Que diagramas daquela página já têm amostra no dataset. A janela substitui pelo dela.

        Existe pela S-451: sem isto, voltar a uma página já feita e clicar "Salvar todos" era
        indistinguível de fazê-la pela primeira vez -- e gravava em silêncio a segunda cópia de
        cada diagrama. `append_training_sample` nomeia por timestamp e sempre acrescenta, então
        o preço é uma linha e um PNG duplicados por diagrama, num arquivo que este projeto existe
        para fazer crescer limpo."""
        """A chave do livro aberto. Mesma razão do de cima."""

        self._montar()
        self._atualizar_tudo()
        atalhos.conferir_dono(self, "PainelDeResultado")

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        caixa = QVBoxLayout(self)
        caixa.setContentsMargins(*(espaco.folga(),) * 4)
        caixa.setSpacing(espaco.linha())

        self.lista = QListWidget(self)
        self.lista.setMaximumHeight(ALTURA_MAXIMA_DA_LISTA)
        self.lista.currentRowChanged.connect(self._trocou_de_item)
        caixa.addWidget(self.lista, 0)

        # O mesmo texto do `LabelFrame` de `ui/result_panel.py`, literal nos dois lados: ele diz
        # o que fazer com o widget que está dentro dele, e é a única frase do painel que não
        # nomeia um comando -- que é o critério de `ui/strings.py`.
        grupo = QGroupBox("Reconhecido (clique e arraste para corrigir)", self)
        dentro = QVBoxLayout(grupo)
        self.tabuleiro = TabuleiroEditavel(grupo)
        self.tabuleiro.posicao_mudou.connect(self._tabuleiro_mudou)
        self.tabuleiro.selecao_mudou.connect(self._casa_selecionada)
        self.tabuleiro.recado.connect(self.estado)
        dentro.addWidget(self.tabuleiro, 1)
        caixa.addWidget(grupo, 3)

        self.legalidade = QLabel("", self)
        self.legalidade.setWordWrap(True)
        caixa.addWidget(self.legalidade)
        self.material = QLabel("", self)
        self.material.setWordWrap(True)
        self.material.setFont(tema.fonte_atual(tipografia.AUXILIAR))
        tema.pintar(self.material, "color", tokens.TEXTO_SECUNDARIO)
        caixa.addWidget(self.material)

        caixa.addLayout(self._linha_de_navegacao())
        caixa.addLayout(self._linha_de_fen())
        caixa.addLayout(self._linha_de_lado())
        caixa.addWidget(self._barra_de_acoes())

        self.detalhes = QLabel("", self)
        self.detalhes.setWordWrap(True)
        self.detalhes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detalhes.setAlignment(Qt.AlignmentFlag.AlignTop)
        caixa.addWidget(self.detalhes, 1)

        # Uma dica por painel, e não por botão: quem a mostra é o pai, porque um controle
        # desabilitado não recebe evento de ponteiro no Qt (S-32).
        self._dicas = DicaEmDesabilitado(self)

    def _linha_de_navegacao(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        self.anterior = QPushButton(strings.ANTERIOR, self)
        self.anterior.clicked.connect(lambda: self.andar(-1))
        tema.aplicar_papel(self.anterior, estilos.NEUTRO)
        linha.addWidget(self.anterior)
        self.proximo = QPushButton(strings.PROXIMO, self)
        self.proximo.clicked.connect(lambda: self.andar(1))
        tema.aplicar_papel(self.proximo, estilos.NEUTRO)
        linha.addWidget(self.proximo)
        linha.addWidget(QLabel("Selecionado", self))
        self.seletor = QSpinBox(self)
        self.seletor.setMinimum(1)
        self.seletor.setMaximum(1)
        self.seletor.valueChanged.connect(self._pediu_diagrama)
        linha.addWidget(self.seletor)
        linha.addStretch(1)
        return linha

    def _linha_de_fen(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.addWidget(QLabel("FEN", self))
        self.campo_fen = QLineEdit(self)
        self.campo_fen.setFont(tema.fonte_atual(tipografia.DADO))
        self.campo_fen.setPlaceholderText("a FEN do diagrama selecionado")
        # **A tecla é declarada no próprio campo**, e é o mecanismo da S-117: quem declara a
        # sequência fica com ela, e a guarda de foco cede. Sem isto `Ctrl+Enter` dentro do campo
        # não aplicaria nada -- a guarda cede a tecla ao campo, e o campo não faria nada com ela.
        aplicar = atalhos.por_acao.get("aplicar_fen")
        if aplicar is not None:
            self.campo_fen.returnPressed.connect(self.aplicar_fen)
            atalho = QKeySequence(sequencia_qt(aplicar.sequencia))
            self.campo_fen.addAction(self._acao_local("aplicar_fen", atalho, self.aplicar_fen))
        linha.addWidget(self.campo_fen, 1)
        self.btn_aplicar = QPushButton(comandos.rotulo_de_botao("aplicar_fen"), self)
        self.btn_aplicar.clicked.connect(self.aplicar_fen)
        tema.aplicar_papel(self.btn_aplicar, comandos.papel("aplicar_fen"))
        linha.addWidget(self.btn_aplicar)
        # Copiar fica ao lado da FEN e **fora** da barra de ações: ele não muda nada, e uma ação
        # inócua no meio de cinco que gravam ou apagam é a que se clica por engano.
        self.copiar = QPushButton("Copiar FEN", self)
        self.copiar.clicked.connect(self._copiar_fen)
        tema.aplicar_papel(self.copiar, estilos.NEUTRO)
        linha.addWidget(self.copiar)
        return linha

    def _acao_local(self, acao: str, tecla: QKeySequence, alvo: Callable[[], object]) -> QAction:
        """Uma `QAction` presa ao widget, com contexto de widget. Ver `_linha_de_fen`."""
        local = QAction(comandos.rotulo(acao), self)
        local.setShortcut(tecla)
        local.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        local.triggered.connect(lambda _marcado=False: alvo())
        return local

    def _linha_de_lado(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.addWidget(QLabel(strings.LADO_A_JOGAR, self))
        self._lados = QButtonGroup(self)
        for valor, rotulo in (("w", "Brancas"), ("b", "Pretas")):
            botao = QRadioButton(rotulo, self)
            botao.setProperty("lado", valor)
            self._lados.addButton(botao)
            linha.addWidget(botao)
        self._lados.buttonClicked.connect(self._trocou_o_lado)
        linha.addStretch(1)
        return linha

    def _barra_de_acoes(self) -> BarraFluida:
        """As ações, numa `BarraFluida` -- que quebra em vez de cortar (S-151).

        Seis botões numa coluna de 360 px não cabem numa linha, e o `QHBoxLayout` responderia
        com uma largura mínima maior que o painel: o divisor da janela deixaria de poder ser
        arrastado. A barra da S-151 existe exatamente para isso.
        """
        barra = BarraFluida(self)
        self.btn_salvar = self._botao(barra, "salvar", self.salvar_atual, estilos.PRIMARIO)
        self.btn_salvar_todos = self._botao(barra, "salvar_todos", self.salvar_todos, estilos.NEUTRO)
        self.btn_desfazer = self._botao(barra, "desfazer", self.desfazer, estilos.NEUTRO)
        self.btn_refazer = self._botao(barra, "refazer", self.refazer, estilos.NEUTRO)
        self.btn_limpar = self._botao(barra, "limpar_tabuleiro", self.limpar_tabuleiro, estilos.NEUTRO)
        # **Uma ênfase por barra, cobrada aqui** (S-446). `estilos.conferir_barra` é pura e
        # recusa a segunda: duas ênfases numa barra é o mesmo que nenhuma, e o teste não tem como
        # saber qual das duas era para ser a ação.
        estilos.conferir_barra(
            [estilos.PRIMARIO, estilos.NEUTRO, estilos.NEUTRO, estilos.NEUTRO, estilos.NEUTRO],
            onde="a barra do painel de resultado",
        )
        # **O mapa de incerteza volta a ser desligavel (S-21/S-506).** Ele existia no painel do Tk
        # e o porte nao o trouxe: a tinta ficava ligada para sempre, e quem confere uma pagina ja
        # revista trabalhava com todas as casas duvidosas pintadas por baixo das pecas. Nao entra
        # em `conferir_barra` porque a regra dela e sobre enfase de **botao**, e uma caixa de
        # marcacao nao tem enfase.
        self.heatmap = QCheckBox(strings.MAPA_DE_INCERTEZA, barra)
        self.heatmap.setChecked(True)
        self.heatmap.toggled.connect(self.tabuleiro.definir_heatmap)
        dica_em(self.heatmap, "Tinge as casas de leitura duvidosa. Desligado, a peça lida aparece limpa.")
        barra.adicionar(self.heatmap)
        return barra

    def _botao(self, barra: BarraFluida, acao: str, alvo: Callable[[], object], papel: str) -> QPushButton:
        """Um botão de comando: rótulo, papel e dica saem do catálogo e da tabela de teclas.

        O rótulo vem de `ui/comandos.py` e a tecla de `ui/atalhos.py`, pela razão da S-324 e da
        S-165 -- este arquivo não escreve texto de interface nem sequência de tecla.
        """
        botao = QPushButton(comandos.rotulo_de_botao(acao), barra)
        botao.clicked.connect(lambda _marcado=False: alvo())
        tema.aplicar_papel(botao, papel)
        self._explicar(botao, acao, comandos.rotulo(acao))
        barra.adicionar(botao)
        return botao

    def _explicar(self, botao: QPushButton, acao: str, motivo: str) -> None:
        """A dica do botão: o que ele faz (ou por que está cinza) e a tecla dele."""
        tecla = atalhos.acelerador(acao)
        dica_em(botao, f"{motivo}\nTecla: {tecla}" if tecla else motivo)

    # ------------------------------------------------------------------------------ carga

    def carregar_pagina(self, itens: Sequence[RecognizedDiagram], *, chave: str, pagina: int) -> None:
        """Abre o resultado de uma página inteira. **Ponto único de troca de vínculo** (S-49).

        O vínculo é `PAGE` e a âncora é o par (documento, página): é ela que faz `Ctrl+S` gravar
        amostra nova em vez de regravar a linha de um dataset que não está aberto.
        """
        self.modelo.load(
            list(itens),
            binding=EditorBinding.PAGE,
            page_key=(chave, pagina),
            origin=RecognitionOrigin.for_page(chave, pagina),
        )
        self._repovoar_lista()
        if self.modelo.items:
            self.lista.setCurrentRow(0)
        else:
            self._atualizar_tudo()

    # ------------------------------------------------------- as outras três origens (S-49)

    def declarar_contexto(
        self, *, documento: Callable[[], str], parametros: Callable[[], PageOcrParams]
    ) -> None:
        """Diz ao painel de que livro e com que parâmetros as páginas estão sendo lidas.

        **Duas funções e não dois valores**, pela razão de sempre: quem sabe o livro aberto é a
        janela, e ela troca de livro sem avisar o painel. Guardar o valor faria o cache responder
        sobre o livro anterior na primeira virada de página depois de abrir outro.
        """
        self._documento = documento
        self._parametros = parametros

    def lembrar_pagina(self) -> None:
        """Guarda o que está no editor no cache da página de onde ele veio.

        As listas vão **por referência**, então a correção feita durante a edição já está no
        cache; o que precisa ser copiado é o índice selecionado, que é escalar.

        Chamado **antes** de a página virar: é a janela de tempo em que o editor ainda tem o
        reconhecimento da página de origem.
        """
        if self.modelo.page_key is None or not self.modelo.items:
            return
        documento, pagina = self.modelo.page_key
        self.paginas.put(
            documento,
            PageResults(
                page_index=pagina,
                params=self._parametros(),
                items=self.modelo.items,
                fen_edits=self.modelo.fen_edits,
                side_edits=self.modelo.side_edits,
                selected_index=self.modelo.clamped_index(),
                origin=self.modelo.origin,
            ),
        )

    def restaurar_pagina(self, pagina: int) -> None:
        """Traz de volta o reconhecimento daquela página, se houver, ao trocar de página.

        Quem decide entre restaurar, limpar e não mexer é `page_results.decide_page_switch`, que é
        puro: **não mexer** é o caso de quem estava editando uma amostra do dataset ou um item da
        fila, e virar a página não pode tirar da tela o que não veio de página nenhuma.
        """
        documento = self._documento()
        guardado = self.paginas.get(documento, pagina, self._parametros())
        acao = decide_page_switch(stored=guardado, current_is_page_result=self.modelo.page_key is not None)
        if acao is PageSwitch.RESTORE:
            assert guardado is not None
            # `adopt` e não `load`: as listas voltam **por referência**, e copiá-las desfaria a
            # correção feita antes de virar a página. A procedência entra junto (S-451) -- sem
            # ela, gravar uma amostra de uma página restaurada escrevia o `source_page` da
            # página errada, e o diagrama nunca ficava verde.
            self.modelo.adopt(
                guardado.items,
                guardado.fen_edits,
                guardado.side_edits,
                page_key=(documento, guardado.page_index),
                origin=guardado.origin,
                selected=guardado.clamped_index(),
            )
            self._repovoar_lista()
            self.lista.setCurrentRow(self.modelo.clamped_index())
        elif acao is PageSwitch.CLEAR:
            self.limpar()
            self.estado.emit(f"Página {pagina + 1}: sem reconhecimento ainda. Rode o OCR.")

    def descartar_livro(self, documento: str) -> None:
        """Esquece o que foi lido daquele livro. Chamado ao abrir outro."""
        self.paginas.discard_document(documento)


    # ------------------------------------------- o que a sala de estudo pergunta (S-269/S-282)

    def posicao_de_estudo(self, *, lance_de: Callable[[int, int], int | None] | None = None) -> Any:
        """A posição do diagrama selecionado, **inteira**: campo, vez, lance e endereço no livro.

        **O adaptador é daqui, e o núcleo é de `ui/sala_declarada.py`.** Montar a posição é
        decisão -- a S-269 mediu que *todo* estudo abria com as brancas a jogar e sem direito a
        roque --, e de onde sai o texto da FEN é do toolkit: no Tk o estado vivo é o widget, aqui é
        o modelo. É a mesma divisão de `linhas_de_fonte` na fita.

        **A página vem do `page_key`, e não da página exibida**: o editor pode estar mostrando o
        diagrama de uma página que o visualizador já deixou para trás, e ancorar o estudo na página
        *exibida* o poria na mesa errada. Item da fila e amostra do dataset não têm par, e ali o
        estudo nasce avulso -- que é o que ele é.
        """
        indice = self.modelo.clamped_index()
        chave = self.modelo.page_key
        lados = self.modelo.side_edits
        fens = self.modelo.fen_edits
        return posicao_de_estudo(
            fens[indice] if 0 <= indice < len(fens) else "",
            lados[indice] if 0 <= indice < len(lados) else "w",
            documento=chave[0] if chave is not None else "",
            pagina=chave[1] if chave is not None else -1,
            diagrama=indice if chave is not None else -1,
            lance=(lance_de(chave[1], indice) if chave is not None and lance_de is not None else None),
        )

    def recorte_de(self, ancora: Any) -> Any:
        """O recorte daquele diagrama, como este painel o tem em memória (S-282).

        `None` quando o editor está mostrando **outra** página: o recorte tem de ser o do diagrama
        que ancorou o estudo, e não o do que está selecionado agora -- mostrar o segundo seria pôr
        lado a lado duas posições diferentes dizendo que são a mesma, que é o defeito exato que a
        miniatura existe para impedir.
        """
        chave = self.modelo.page_key
        if not getattr(ancora, "valida", False) or chave is None:
            return None
        if chave[0] != ancora.documento or int(chave[1]) != int(ancora.pagina):
            return None
        if not 0 <= int(ancora.diagrama) < len(self.modelo.items):
            return None
        return getattr(self.modelo.items[int(ancora.diagrama)], "board_rgb", None)

    def carregar_avulsos(self, itens: Sequence[RecognizedDiagram]) -> None:
        """Abre um recorte de área ou uma imagem local. **Vínculo `NONE`** (S-49).

        `NONE` é "não há nada para onde voltar": o que entrou não veio de página nenhuma, de item
        de fila nenhum e de linha de dataset nenhuma, então `Ctrl+S` grava amostra nova e virar a
        página não pode restaurar coisa alguma por cima disto.
        """
        self.lembrar_pagina()
        self.modelo.load(list(itens), binding=EditorBinding.NONE)
        self._repovoar_lista()
        if self.modelo.items:
            self.lista.setCurrentRow(0)
        else:
            self._atualizar_tudo()

    def carregar_item_de_revisao(self, item: Any, posicao: int) -> bool:
        """Abre um item da fila no editor, **já na casa suspeita** (S-22). `False` se a imagem sumiu.

        Abrir na casa suspeita é o que a fila pede do "corrigir agora": sem isso a pessoa recebe o
        tabuleiro inteiro de novo e a fila não economizou nada.

        **O vínculo é `REVIEW`**, e é ele que faz `Ctrl+S` também fechar o item na fila. O que
        estava aberto antes vai para o cache da página dele -- navegar depois não pode apagar o
        item da fila nem confundi-lo com resultado de página.
        """
        from chess_diagram_ocr.atomic_io import read_board_image

        tabuleiro_rgb = read_board_image(item.board_image)
        if tabuleiro_rgb is None:
            QMessageBox.critical(self, "Fila de revisão", f"Miniatura não encontrada:\n{item.board_image}")
            return False

        placement = str(item.fen).split(" ")[0]
        self.lembrar_pagina()
        # A fila guarda as 64 confianças, e não a matriz (64, 13) -- ela custaria ~5,6 MB por livro
        # em JSON (decisão da S-22). Então vem a rampa de calor, e não a dica das três classes.
        diagrama = RecognizedDiagram.from_label(
            tabuleiro_rgb,
            placement,
            side_to_move=item.side_to_move,
            side_to_move_source="queue",
            side_to_move_reason="; ".join(item.reasons),
            min_confidence=item.min_confidence,
            mean_confidence=item.min_confidence,
            uncertain_squares=list(item.uncertain_squares),
            square_confidences=list(item.square_confidences),
            changed_squares=list(item.changed_squares),
        )
        self.modelo.load(
            [diagrama],
            [placement],
            [str(item.side_to_move)],
            binding=EditorBinding.REVIEW,
            review_position=posicao,
        )
        self._repovoar_lista()
        self.lista.setCurrentRow(0)
        casa = getattr(item, "first_uncertain_square", None)
        if casa is not None:
            self.tabuleiro.modelo.select(int(casa))
            self.tabuleiro.update()
        self.estado.emit(f"Revisão {item.label}: {'; '.join(item.reasons)}")
        return True

    def carregar_amostra(self, row: Any, samples_dir: Path) -> bool:
        """Abre uma amostra do dataset no editor. **Salvar regrava a linha**, não cria outra.

        É o vínculo `SAMPLE`, e ele existe para não repetir o defeito da S-23: uma segunda amostra
        da mesma imagem, com o rótulo velho ao lado do novo.
        """
        from chess_diagram_ocr.atomic_io import read_board_image

        caminho = row.image_path(samples_dir)
        tabuleiro_rgb = read_board_image(str(caminho))
        if tabuleiro_rgb is None:
            QMessageBox.critical(self, "Dataset", f"Imagem não encontrada:\n{caminho}")
            return False

        lado = row.side_to_move if row.side_to_move in ("w", "b") else "w"
        self.lembrar_pagina()
        diagrama = RecognizedDiagram.from_label(
            tabuleiro_rgb,
            row.placement,
            side_to_move=lado,
            side_to_move_source="manual",
            side_to_move_reason="rotulo do dataset",
            detection_source=row.detection_source,
        )
        # A legalidade sai da própria posição rotulada, e não das colunas do CSV: o rótulo foi
        # gravado com um lado a jogar, e é com ele que a checagem tem de bater (S-17).
        diagrama.resolve_legality()
        self.modelo.load(
            [diagrama],
            [row.placement],
            [lado],
            binding=EditorBinding.SAMPLE,
            editing_sample=row.filename,
        )
        self._repovoar_lista()
        self.lista.setCurrentRow(0)
        self.estado.emit(f"Editando amostra {row.filename} (Ctrl+S regrava o rótulo).")
        return True

    def _regravar_linha(self, alvo: SaveTarget, *, permitir_ilegal: bool) -> bool:
        """Regrava o rótulo da amostra aberta, em vez de criar outra (S-23).

        **Sem caixa de sucesso** (S-164): a frase do rodapé diz a mesma coisa, e um clique para
        confirmar que deu certo é o que treina a pessoa a fechar caixas sem ler -- inclusive as
        que perguntam alguma coisa.
        """
        from chess_diagram_ocr.dataset_browser import update_row

        nome = alvo.filename or ""
        try:
            atualizado = update_row(
                self._csv_de_rotulos,
                nome,
                fen=alvo.fen,
                side_to_move=alvo.side,
                corrected_by=alvo.route,
                allow_illegal=permitir_ilegal,
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Dataset", str(exc))
            return False
        if not atualizado:
            QMessageBox.critical(self, "Dataset", f"Amostra não encontrada no CSV: {nome}")
            return False
        self.estado.emit(f"Rótulo de {nome} regravado.")
        # **Não emite `salvou`**, e é resposta: regravar a linha de uma amostra que já existia não
        # faz diagrama nenhum ficar verde na página -- ele já estava. O que mudou foi o rótulo, e
        # disso quem precisa saber é a aba Dataset.
        self.regravou.emit()
        return True


    def limpar(self) -> None:
        """Desfaz o vínculo e esvazia o painel. É o estado de abertura."""
        self.modelo.clear()
        self._repovoar_lista()
        self._atualizar_tudo()

    def _repovoar_lista(self) -> None:
        self._montando = True
        try:
            self.lista.clear()
            for posicao, item in enumerate(self.modelo.items):
                self.lista.addItem(self._texto_do_item(item, posicao))
            self.seletor.setMaximum(max(1, len(self.modelo.items)))
        finally:
            self._montando = False

    # -------------------------------------------------------------------------- navegação

    def andar(self, passo: int) -> None:
        """Anda na lista, **parando nas pontas**.

        Não dá a volta: quem aperta `→` no último diagrama quer o último, e voltar ao primeiro
        faz a pessoa perder onde estava numa página de nove.
        """
        if not self.modelo.items:
            return
        self.lista.setCurrentRow(min(len(self.modelo.items) - 1, max(0, self.lista.currentRow() + passo)))

    def _pediu_diagrama(self, numero: int) -> None:
        if self._montando or not self.modelo.items:
            return
        self.lista.setCurrentRow(min(len(self.modelo.items), max(1, numero)) - 1)

    def _trocou_de_item(self, linha: int) -> None:
        if not 0 <= linha < len(self.modelo.items):
            self._atualizar_tudo()
            return
        self.modelo.select(linha)
        # **A pilha é zerada na troca** (S-229): ela é por diagrama, e `Ctrl+Z` depois de andar
        # tem de devolver a posição anterior *deste* diagrama, não a correção do vizinho.
        self.historico.zerar(self.modelo.fen_at(linha))
        self.selecionou.emit(linha)
        self._atualizar_tudo()

    # ---------------------------------------------------------------------------- edição

    def _tabuleiro_mudou(self, placement: str) -> None:
        """Toda edição no tabuleiro guarda no editor e entra na pilha."""
        linha = self.modelo.clamped_index()
        if not self.modelo.items:
            return
        self.modelo.apply_placement(placement, linha)
        self.historico.registrar(placement)
        # O contador que decide o `Ctrl+Z` quando o foco não está em desfazível nenhum (S-243).
        self._edicao += 1
        self._atualizar_tudo()

    def _casa_selecionada(self, indice: object) -> None:
        """O sinal traz `object` porque `None` -- "nada selecionado" -- é resposta legítima."""
        if not isinstance(indice, int):
            return
        self.estado.emit(f"Casa {square_name(indice)} selecionada.")

    def aplicar_fen(self) -> None:
        """`Ctrl+Enter`: lê o campo de texto e põe no tabuleiro. É a quarta origem da S-229.

        FEN inválida **avisa e não muda nada**: aceitar um campo de peças malformado daria 64
        casas inventadas, e quem digitou não saberia que o que está na tela não é o que escreveu.
        """
        if not self.modelo.items:
            return
        texto = self.campo_fen.text().strip()
        if not board_edit.is_valid_placement(board_edit.placement_of(texto)):
            self.estado.emit("A FEN digitada não descreve um tabuleiro: nada foi aplicado.")
            return
        placement = board_edit.placement_of(texto)
        self.modelo.apply_placement(placement, self.modelo.clamped_index())
        self.historico.registrar(placement)
        self._atualizar_tudo()

    def _trocou_o_lado(self) -> None:
        if self._montando:
            return
        botao = self._lados.checkedButton()
        if botao is None or not self.modelo.set_side(str(botao.property("lado"))):
            return
        # A legalidade depende de quem joga: trocar a vez pode resolver o "xeque invertido" sem
        # mexer em nenhuma peça (S-17).
        self._atualizar_tudo()
        self.estado.emit(f"Diagrama {self.modelo.clamped_index() + 1}: lado a jogar definido.")

    def contem(self, widget: object) -> bool:
        """Este widget está dentro deste painel? É o que decide de quem é o `Ctrl+Z` (S-243)."""
        return qt_atalhos.contem(self, widget)

    @property
    def edicao(self) -> int:
        """Contador que só cresce, como manda `ui/desfazivel.Desfazivel`. Zero = nunca editado."""
        return self._edicao

    def desfazer(self) -> None:
        """`Ctrl+Z`: devolve a posição anterior deste diagrama."""
        self._voltar(self.historico.desfazer(), MOTIVO_SEM_DESFAZER)

    def refazer(self) -> None:
        """`Ctrl+Y`: repõe o que o desfazer tirou."""
        self._voltar(self.historico.refazer(), MOTIVO_SEM_REFAZER)

    def _voltar(self, placement: str | None, motivo: str) -> None:
        if placement is None:
            self.estado.emit(motivo)
            return
        self.modelo.apply_placement(placement, self.modelo.clamped_index())
        self._atualizar_tudo()

    def limpar_tabuleiro(self) -> None:
        """Esvazia as 64 casas -- e a pilha guarda a posição de antes, então é desfazível."""
        if not self.modelo.items:
            return
        self.modelo.apply_placement(board_edit.EMPTY_PLACEMENT, self.modelo.clamped_index())
        self.historico.registrar(board_edit.EMPTY_PLACEMENT)
        self._atualizar_tudo()
        self.estado.emit("Tabuleiro esvaziado. Ctrl+Z devolve a posição.")

    # -------------------------------------------------------------------------- gravação

    def salvar_atual(self) -> None:
        """Grava a posição corrigida. **O que "salvar" significa é decisão do modelo** (S-49)."""
        if not self.modelo.items:
            self.estado.emit("Não há diagrama lido para salvar: leia uma página antes.")
            return
        alvo = self.modelo.save_target()
        if not self._gravar_alvo(alvo):
            return
        self.modelo.settled()
        self._atualizar_tudo()

    def salvar_todos(self) -> None:
        """Grava os diagramas da página, um a um, e **conta o que deu certo** (S-318).

        Parar no primeiro erro deixaria metade da página gravada sem dizer quantos; seguir em
        silêncio esconderia a falha. O laço grava o que dá e a frase final diz os dois números.
        """
        if not self.modelo.items:
            self.estado.emit("Não há diagrama lido para salvar: leia uma página antes.")
            return
        indices = list(range(len(self.modelo.items)))
        repetidos = self._ja_salvos(indices)
        if repetidos and not self._confirmar_repetidos(repetidos, len(indices)):
            indices = [i for i in indices if i not in repetidos]
            if not indices:
                self.estado.emit(
                    f"Salvar todos: nada a gravar, os {len(repetidos)} diagrama(s) desta "
                    "página já estavam salvos."
                )
                return

        gravados = 0
        for indice in indices:
            if self._gravar_alvo(self.modelo.save_target(indice), silencioso=True):
                gravados += 1
        self.modelo.settled()
        self._atualizar_tudo()
        self.estado.emit(f"Salvos {gravados} de {len(indices)} diagramas da página.")

    def _ja_salvos(self, indices: Sequence[int]) -> set[int]:
        """Quais destas posições já têm amostra gravada. Devolve a **posição**, não o nº do diagrama.

        A posição é o índice na lista do editor, que é por onde o laço filtra; o número do
        diagrama (`items[i].index`) é o que a janela conta e o que o CSV grava. Os dois coincidem
        quase sempre, e não é seguro contar com isso -- a conversão fica aqui.

        Vazio quando não há procedência de página -- imagem solta, recorte, item da fila: sem ela
        não há como saber o que já foi salvo, e perguntar sem saber é pior que não perguntar.
        """
        chave = self.modelo.page_key
        if chave is None:
            return set()
        documento, pagina = chave
        salvos = set(self.diagramas_salvos(documento, int(pagina)))
        if not salvos:
            return set()
        return {
            i for i in indices if 0 <= i < len(self.modelo.items) and self.modelo.items[i].index in salvos
        }

    def _confirmar_repetidos(self, repetidos: set[int], total: int) -> bool:
        """A pergunta da S-451, **uma para a página** e não uma por diagrama.

        Uma página de capítulo sobre estrutura tem oito diagramas: perguntar oito vezes a mesma
        coisa treina a pessoa a clicar "sim" sem ler, que é o oposto do que a confirmação existe
        para conseguir.
        """
        numeros = ", ".join(str(self.modelo.items[i].index + 1) for i in sorted(repetidos))
        todos = len(repetidos) == total
        fim = "Salvar novamente?" if todos else 'Salvar novamente? Responder "não" salva apenas os outros.'
        resposta = QMessageBox.question(
            self,
            "Diagramas já salvos",
            f"{len(repetidos)} de {total} diagramas desta página já têm amostra no dataset: "
            f"{numeros}.\n\n"
            "Salvar de novo grava uma segunda linha e uma segunda imagem do mesmo diagrama -- o "
            "que vale a pena se você acabou de corrigir a leitura, e é duplicata se não.\n\n" + fim,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resposta == QMessageBox.StandardButton.Yes

    def _gravar_alvo(self, alvo: SaveTarget, *, silencioso: bool = False) -> bool:
        """Executa uma gravação. Devolve se ela aconteceu.

        `silencioso` é para o "salvar todos": ali a caixa de erro por diagrama viraria nove
        caixas numa página cheia, e o que quem grava a página inteira precisa é do total.
        """
        fen = compose_fen(alvo.fen.split(" ")[0], alvo.side != "b")
        if not is_valid_fen(fen):
            if not silencioso:
                QMessageBox.critical(self, "Salvar a posição", "A FEN atual é inválida.")
            return False

        confirmada = None if silencioso else self._confirmar_ilegal(alvo)
        if confirmada is False:
            self.estado.emit("Gravação cancelada: posição ilegal não confirmada.")
            return False
        if alvo.kind is SaveKind.REWRITE_ROW:
            # **Regravar, e não gravar de novo** (S-23): quem chegou aqui abriu uma amostra do
            # dataset, e criar uma segunda linha da mesma imagem é o defeito que aquele item
            # fechou. Quem decide qual dos dois é `save_target()`, e ele já decidiu.
            return self._regravar_linha(alvo, permitir_ilegal=confirmada is True)

        # **O `try` cobre a gravação, e só ela** (S-318): um erro no que vem depois produziria
        # "falha ao salvar" sobre uma amostra que **está no disco**, e a pessoa refaria -- uma
        # linha e um PNG duplicados no `labels.csv`.
        try:
            caminho = self._servico.save_sample(
                self.modelo.items[alvo.index],
                alvo.fen,
                csv_path=self._csv_de_rotulos,
                samples_dir=self._csv_de_rotulos.parent / "samples",
                origin=self.modelo.origin,
                side_to_move=alvo.side,
                corrected_by=alvo.route,
                allow_illegal=confirmada is True,
            )
        except Exception as exc:  # noqa: BLE001 - a caixa precisa da mensagem, e o log do rastro
            logger.exception("Falha ao gravar a amostra corrigida.")
            if not silencioso:
                QMessageBox.critical(self, "Erro ao salvar a amostra", f"Falha ao salvar:\n{exc}")
            return False

        self.salvou.emit(alvo.index)
        # **Fechar o item da fila vem depois da gravação, e só quando ela aconteceu** (S-22): um
        # item marcado como revisado sobre uma amostra que não entrou no CSV é a fila mentindo
        # sobre o trabalho feito.
        if alvo.settle_position is not None:
            self.revisou.emit(int(alvo.settle_position), alvo.fen, alvo.side)
            self.modelo.settled()
        if not silencioso:
            self.estado.emit(f"Amostra gravada: {Path(caminho).name}")
        return True

    def _confirmar_ilegal(self, alvo: SaveTarget) -> bool | None:
        """`None` quando a posição é legal, senão a resposta da pessoa.

        Três valores e não dois: legal segue sem caixa nenhuma, "sim" grava com a marca de
        ilegal confirmada, "não" cancela. Colapsar legal com "sim" faria toda amostra normal
        ser gravada como ilegal.
        """
        pergunta = illegal_save_question(compose_fen(alvo.fen.split(" ")[0], alvo.side != "b"))
        if pergunta is None:
            return None
        resposta = QMessageBox.warning(
            self,
            ILLEGAL_SAVE_TITLE,
            pergunta,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resposta == QMessageBox.StandardButton.Yes

    # -------------------------------------------------------------------------- a pintura

    def _atualizar_tudo(self) -> None:
        """Repõe tudo o que depende do estado. Um lugar só, e é de propósito.

        Cinco widgets dependem do mesmo estado -- tabuleiro, FEN, lado, legalidade e os botões --
        e atualizá-los de dentro de cada gesto foi o que fez `update_views`, `update_legality` e
        `sync_side_widgets` existirem separados no Tk e serem esquecidos um de cada vez.
        """
        vazio = not self.modelo.items
        self._montando = True
        try:
            if vazio:
                self.tabuleiro.mostrar(board_edit.EMPTY_PLACEMENT)
                self.campo_fen.setText("")
                self.legalidade.setText(MENSAGEM_VAZIA)
                self.material.setText("")
                self.detalhes.setText("")
            else:
                self._pintar_diagrama()
        finally:
            self._montando = False
        self._atualizar_botoes(vazio)
        self.posicao_mudou.emit()

    def _pintar_diagrama(self) -> None:
        indice = self.modelo.clamped_index()
        item = self.modelo.items[indice]
        corrigida = self.modelo.fen_at(indice)
        lado = self.modelo.side_at(indice)

        self.tabuleiro.mostrar(
            corrigida,
            incertas=item.uncertain_squares,
            confiancas=item.square_confidences,
        )
        self.tabuleiro.definir_casas_corrigidas(board_edit.differing_squares(item.placement, corrigida))
        explicacao = explain_position(compose_fen(corrigida, lado != "b"))
        self.tabuleiro.definir_casas_problematicas(explicacao.highlight_squares)
        self.legalidade.setText(explicacao.summary())
        self.material.setText(explicacao.material_line())
        self.campo_fen.setText(compose_fen(corrigida, lado != "b"))
        self.detalhes.setText(self._detalhes_do_item(item))
        self.seletor.setValue(indice + 1)
        for botao in self._lados.buttons():
            botao.setChecked(str(botao.property("lado")) == lado)

    def _atualizar_botoes(self, vazio: bool) -> None:
        """Acende, apaga e **diz por quê** -- a regra da S-165, que achou treze botões cinzas."""
        for botao in (self.btn_salvar, self.btn_salvar_todos, self.btn_limpar, self.btn_aplicar, self.copiar):
            botao.setEnabled(not vazio)
        self.campo_fen.setEnabled(not vazio)
        self.anterior.setEnabled(not vazio and self.modelo.clamped_index() > 0)
        self.proximo.setEnabled(not vazio and self.modelo.clamped_index() < len(self.modelo.items) - 1)
        self.seletor.setEnabled(not vazio)

        for botao, acao, pode, sem in (
            (self.btn_desfazer, "desfazer", self.historico.pode_desfazer, MOTIVO_SEM_DESFAZER),
            (self.btn_refazer, "refazer", self.historico.pode_refazer, MOTIVO_SEM_REFAZER),
        ):
            ligado = (not vazio) and pode
            botao.setEnabled(ligado)
            self._explicar(botao, acao, comandos.rotulo(acao) if ligado else (sem if not vazio else MOTIVO_SEM_DIAGRAMA))
        for botao, acao in (
            (self.btn_salvar, "salvar"),
            (self.btn_salvar_todos, "salvar_todos"),
            (self.btn_limpar, "limpar_tabuleiro"),
        ):
            self._explicar(botao, acao, comandos.rotulo(acao) if not vazio else MOTIVO_SEM_DIAGRAMA)

    # ------------------------------------------------------------------------------ texto
    #
    # Os três vieram de `qt/janela.py` na S-503: eles descrevem o **diagrama selecionado**,
    # que é o assunto deste painel. Na janela eles obrigavam-na a conhecer o que um
    # `RecognizedDiagram` tem dentro para escrever uma linha de lista.

    def _texto_do_item(self, item: RecognizedDiagram, posicao: int) -> str:
        """A linha da lista: número, legalidade, confiança e de quem é a vez."""
        explicacao = explain_position(compose_fen(item.placement, item.side_is_white))
        vez = "brancas" if item.side_is_white else "pretas"
        return f"{posicao + 1} · {explicacao.label} · conf. mín. {item.min_confidence:.2f} · {vez}"

    def _detalhes_do_item(self, item: RecognizedDiagram) -> str:
        """O parágrafo abaixo do tabuleiro: o que se sabe, e **de onde** se sabe.

        A procedência do lado a jogar não é enfeite (S-16/S-17): "pretas jogam" lido de uma
        legenda e "pretas jogam" assumido pelo padrão têm o mesmo texto e valores completamente
        diferentes para quem vai conferir. O rótulo vem de `ui/strings.py`, que existe para que
        as duas telas do projeto não digam isso de dois jeitos.
        """
        explicacao = explain_position(compose_fen(item.placement, item.side_is_white))
        linhas = [
            f"Lado a jogar: {'brancas' if item.side_is_white else 'pretas'}"
            f" — {strings.side_source_label(item.side_to_move_source, conflicting=item.side_conflicting)}",
            explicacao.summary(),
            explicacao.material_line(),
            f"Confiança: mínima {item.min_confidence:.3f} · média {item.mean_confidence:.3f}"
            f" · {len(item.uncertain_squares)} casa(s) incerta(s)",
        ]
        if item.detection_source:
            linhas.append(f"Localizado por: {strings.detection_source_label(item.detection_source)}")
        if item.caption:
            linhas.append(f"Legenda: {item.caption}")
        return "\n".join(linhas)

    def _copiar_fen(self) -> None:
        texto = self.campo_fen.text().strip()
        if not texto:
            return
        area = QApplication.clipboard()
        if area is not None:
            area.setText(texto)
            self.estado.emit("FEN copiada.")

    # ---------------------------------------------------------------------------- teclado

    def acoes_proprias(self) -> frozenset[str]:
        """As ações da tabela que este painel atende enquanto tem o foco (S-244).

        `atalhos.destino` consulta a cadeia de widgets antes de cair no comando global, e é isto
        que faz `Ctrl+S` gravar a posição quando o foco está aqui.
        """
        return frozenset(
            {"salvar", "salvar_todos", "desfazer", "refazer", "aplicar_fen", "diagrama_anterior", "proximo_diagrama"}
        )

    def atender(self, acao: str):  # noqa: ANN201 - assinatura do protocolo `DonoDeAcoes`
        """A função desta ação, ou `None`. O par de `acoes_proprias`."""
        return {
            "salvar": self.salvar_atual,
            "salvar_todos": self.salvar_todos,
            "desfazer": self.desfazer,
            "refazer": self.refazer,
            "aplicar_fen": self.aplicar_fen,
            "diagrama_anterior": lambda: self.andar(-1),
            "proximo_diagrama": lambda: self.andar(1),
        }.get(acao)
