"""A aba de texto no Qt: a página inteira num editor, com os diagramas onde eles estão (S-211/S-504).

**Quase nada é decidido aqui**, e é a mesma frase do cabeçalho de `ui/texto_panel.py`. Onde o
diagrama entra no fluxo, o que merece destaque e o que vai para o arquivo são de
`text/documento.py`; o que a edição faz com um trecho é de `text/rico.py`; o que a busca acha é de
`text/busca.py`. Nenhum dos três importa toolkit nenhum. O que sobra são widgets, threads e o vaivém
entre o deslocamento do documento e a posição do cursor.

---

**O que o porte apagou, e vale medir.** `ui/texto_panel.py` tem 2.600 linhas, e uma parte delas
existe só para contornar o `tk.Text`:

- **as etiquetas combinadas de fonte.** Uma etiqueta do Tk dá **uma** fonte ao trecho, e a última
  criada vence -- daí `NEGRITO_ITALICO`, daí `fonte:titulo:bi:2` gerada sob demanda, daí o cache
  `_fontes_desenhadas` refeito a cada zoom. `QTextCharFormat` guarda peso, pendor e corpo
  separados, e os três somem. Ver `qt/texto_formato.py`.
- **`edit_reset()` depois de todo redesenho.** A pilha de desfazer do Tk guarda **índice**, não
  conteúdo: trocar o texto inteiro e não zerá-la faria o desfazer apagar um pedaço qualquer do
  texto novo. Aqui a pilha é o próprio histórico de documentos, e redesenhar não a corrompe.
- **a leitura do documento de volta do widget**, etiqueta por etiqueta, para gravar -- era
  `ui/texto_etiquetas.de_despejo`, e ela saiu junto com o toolkit (S-506). Aqui o documento
  **é** o estado; o widget é só o desenho dele.

O que **não** muda é a fronteira: toda ferramenta chama uma função pura de `rico`, recebe um
documento novo e o redesenha. É o que faz o negrito sobreviver ao arquivo em vez de existir só
enquanto o widget existir.

---

**A aba é a composição de sete partes** (S-865), cada uma um `QObject` filho dela com o estado que só
ela usa: `qt/texto_espelho.py` (o documento desenhado no editor, a digitação de volta e a pilha do
desfazer), `qt/texto_leitura.py` (as tarefas: a leitura da folha, as exportações, a volta da
Revisão), `qt/texto_caderno.py` (o caderno do livro, o rascunho, o `.cvtxt` e a mesa),
`qt/texto_miniaturas.py` (os diagramas no texto, a miniatura, a dica e o menu),
`qt/texto_correcao.py` (o léxico, o pincel, a busca, os símbolos e o painel de navegação),
`qt/texto_vista.py` (o zoom, a letra, o modo foco e a barra de estado) e `qt/texto_ferramentas.py`
(o formato do trecho e os controles da fita que o aplicam). Aqui fica o que elas dividem -- o
documento, a folha e o livro --, a montagem, o filtro de eventos e a fachada: **os comandos do
catálogo continuam sendo métodos deste painel**, que delegam, porque `COMANDOS_DA_ABA` é uma tabela
só para os dois frontends e a janela os liga por nome.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Sequence
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMenu, QTextEdit, QVBoxLayout, QWidget

from chess_diagram_ocr.config import DEFAULT_DPI
from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import texto_correcao, texto_leitura
from chess_diagram_ocr.qt.fita_do_texto import FitaDoTexto
from chess_diagram_ocr.qt.painel_de_navegacao import PainelDeNavegacao
from chess_diagram_ocr.qt.texto_caderno import CadernoDaAba, FolhasDaSuite
from chess_diagram_ocr.qt.texto_correcao import CorrecaoDoTexto, JanelaDeBusca
from chess_diagram_ocr.qt.texto_espelho import OBJETO, EspelhoDaFolha
from chess_diagram_ocr.qt.texto_ferramentas import FerramentasDeFormato
from chess_diagram_ocr.qt.texto_leitura import CANCELADA, ExecutorDaAba
from chess_diagram_ocr.qt.texto_miniaturas import LARGURA_DA_MINIATURA, MiniaturasDoTexto
from chess_diagram_ocr.qt.texto_vista import VistaDaFolha
from chess_diagram_ocr.qt.vazio import EstadoVazio
from chess_diagram_ocr.text import rico
from chess_diagram_ocr.text.documento import PaginaLida
from chess_diagram_ocr.ui import atalhos, comandos, espaco, strings, texto_cores
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.livros import ChaveDoLivro, chave_do_livro
from chess_diagram_ocr.ui.state import AppState
from chess_diagram_ocr.ui.texto_declarado import ACOES_PROPRIAS, COMANDOS_DA_ABA

logger = logging.getLogger(__name__)

__all__ = ["CANCELADA", "LARGURA_DA_MINIATURA", "OBJETO", "JanelaDeBusca", "PainelDeTexto"]

TECLAS_DO_HISTORICO: tuple[str, ...] = ("desfazer", "refazer")
"""As ações cuja tecla, **dentro do editor**, é deste painel e não do `QTextEdit`.

A guarda de atalhos cede `Ctrl+Z` a todo campo de texto (`ui/atalhos.ACOES_DO_CAMPO`), porque o
campo tem o desfazer dele -- e este não tem: ele está desligado de propósito (ver `_montar`). Sem
pegar a tecla aqui, `Ctrl+Z` no meio da folha chegaria a um desfazer desligado e não faria nada.
A tecla sai da tabela (`ui/atalhos.por_acao`), e não daqui."""


class PainelDeTexto(QWidget):
    """O editor da página lida: desenha o documento e devolve cada gesto a `text/rico.py`."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status."""

    documento_mudou = pyqtSignal()
    """A folha foi editada. A janela usa para saber que há o que gravar."""

    diagrama_ativado = pyqtSignal(int, int)
    """Duplo clique numa miniatura: `(folha 0-based, índice do diagrama)`. A janela leva o
    diagrama à sala de estudo, como o duplo clique na caixa do visualizador (item 8)."""

    diagrama_sem_caixa_ativado = pyqtSignal(int, str)
    """O mesmo duplo clique num diagrama que não tem caixa na página -- o que o PGN do livro pôs na
    folha (S-595): `(folha 0-based, campo de peças)`. Sem caixa não há o que ler nem selecionar no
    Resultado; quem sabe abri-lo é o PGN do livro, que o leva à árvore do autor."""

    bloco_destacado = pyqtSignal(object)
    """O `bbox`, em pontos, do bloco da página de onde veio o trecho sob o cursor -- ou `None` (S-642).
    A mesa o contorna no visualizador. Sai só quando o bloco muda, e não a cada tecla."""

    foco_mudou = pyqtSignal(bool)
    """O modo foco ligou ou desligou (S-658): a mesa esconde ou devolve o visualizador."""

    destacada_mudou = pyqtSignal(bool)
    """A aba foi para a janela da mesa ou voltou dela (S-646): a janela principal rearruma o divisor."""

    folha_pedida = pyqtSignal(int)
    """Um `.cvtxt` do livro aberto acabou de entrar na tela: a folha dele (0-based), para o
    visualizador ir até ela (item 9). Não sai para um `.cvtxt` de outro livro."""

    def __init__(
        self,
        *,
        pdf: Path | None = None,
        pagina: int = 0,
        dpi: int | None = None,
        busy: BusyRegistry | None = None,
        pasta_de_rascunhos: Path | None = None,
        pasta_de_cadernos: Path | None = None,
        com_caderno: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.caderno = CadernoDaAba(
            self, pasta_de_rascunhos=pasta_de_rascunhos, pasta_de_cadernos=pasta_de_cadernos, com_caderno=com_caderno
        )
        self.leitura = ExecutorDaAba(self, busy=busy, dpi_fixo=dpi)
        self.espelho = EspelhoDaFolha(self)
        self.miniaturas = MiniaturasDoTexto(self)
        self.correcao = CorrecaoDoTexto(self)
        self.vista = VistaDaFolha(self)
        self.ferramentas = FerramentasDeFormato(self)
        self._pdf = pdf
        self._pagina_indice = pagina
        self._dpi = dpi or DEFAULT_DPI
        """O DPI da folha que está na tela -- o que liga ponto a pixel nos recortes. Muda quando
        uma folha chega (leitura ou arquivo), e **não** quando a configuração muda: a folha já
        renderizada continua na escala em que foi renderizada."""
        self._pagina: PaginaLida | None = None
        self._pagina_rgb: np.ndarray | None = None
        self.documento = rico.DocumentoRico()
        """**O estado é o documento, e não o widget.** É a diferença de fundo com o lado do Tk,
        onde gravar exigia reler o `dump` do editor etiqueta por etiqueta (`de_despejo`)."""
        self._documento_gravado = self.documento
        """O documento como está no disco -- ou como a leitura o entregou. É contra ele que
        `tem_alteracoes` compara, e não contra a pilha: gravar não esvazia a pilha, e desfazer até
        o que foi gravado não deixa nada a perder."""
        self._executor: Callable[[str], object] | None = None
        self._caminho_do_documento: Path | None = None
        self._relogio: Callable[[], float] = time.monotonic
        """De onde vem o "agora" da pausa que fecha o passo, do pincel e do caderno. Atributo para o
        teste poder parar o tempo -- esperar um segundo de verdade numa suíte é o teste que ninguém quer rodar."""
        self._folha_por_ler: int | None = None
        """A folha que a mesa mostrou sem texto, porque ela não está no caderno (S-644)."""
        self._correcoes = 0
        """Quantas correções a mão fez sobre o que o motor leu, contadas na pausa e na gravação
        (item 24). Não a cada tecla: `correcao.correcoes` compara bloco a bloco por `difflib`."""
        self._posicoes: dict[tuple[ChaveDoLivro | None, int], tuple[str, ...]] = {}
        """O campo de peças de cada diagrama, por `(livro, folha)`, como o OCR de diagramas do
        produto leu. Por folha porque a leitura dos diagramas e a do texto chegam em qualquer
        ordem; **por livro** porque a folha 14 de um livro não é a folha 14 do outro -- com a chave
        só pela folha, trocar de livro levava as posições do anterior para as folhas do novo
        (item 11). `definir_livro` para outro livro esquece tudo."""
        self.transcricao: Any = None
        """O modo transcrição do scan-ouro (S-703), que nasce na primeira vez que é pedido. Ver `qt/modo_transcricao.py`."""
        self._pasta_da_transcricao = ""
        self._filtros: dict[tuple[object, QEvent.Type], Callable[[QEvent], bool]] = {}
        """Quem trata cada evento filtrado (S-825): vazia durante `_montar`. Ver `eventFilter`."""
        self._montar()
        self._filtros = self._tabela_de_filtros()
        self.espelho.desenhar()
        # Toda edição -- tecla ou ferramenta -- reinicia o relógio do rascunho. É o único ouvinte
        # deste sinal dentro do painel; o `desenhar_documento` de uma folha recém-lida também o
        # emite, e aí `gravar_rascunho` não grava: não há alteração.
        self.documento_mudou.connect(self.caderno.agendar_rascunho)
        self.documento_mudou.connect(self.vista.atualizar_status)
        self.editor.cursorPositionChanged.connect(self.caderno.anotar_cursor)
        self.leitura.campo_de_folha.valueChanged.connect(lambda _valor: self.caderno.rotular_leitura())
        atalhos.conferir_dono(self, "PainelDeTexto")

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        caixa = QVBoxLayout(self)
        caixa.setContentsMargins(*(espaco.margem_da_aba(),) * 4)
        caixa.setSpacing(espaco.linha())
        self.ferramentas.montar()
        self.leitura.montar()
        self.fita = FitaDoTexto(
            self,
            alvo=self._alvo_da_fita,
            controles={
                "@corpo": self.ferramentas.caixa_de_corpo,
                "@cor": self.ferramentas.escolha_de_cor,
                "@realce": self.ferramentas.escolha_de_realce,
                "@cor_rapida": self.ferramentas.cor_rapida,
                "@realce_rapido": self.ferramentas.realce_rapido,
                "@galeria": self.ferramentas.galeria,
                "@folha": self.leitura.campo_de_folha,
                "@motor": self.leitura.escolha_de_motor,
                "@lingua": self.leitura.escolha_de_lingua,
            },
            rotulos_do_desfazer=self.espelho.rotulos_do_desfazer,
            desfazer_ate=self.desfazer_ate,
        )
        self.botao_de_ler = self.fita.botao("ler_folha")
        caixa.addWidget(self.fita)
        # A barra fina do modo foco (S-658): o que sobra no lugar da fita, e como sair dele.
        self.barra_do_foco = QLabel(strings.MODO_FOCO_BARRA, self)
        self.barra_do_foco.setAccessibleName("Modo foco")
        self.barra_do_foco.hide()
        caixa.addWidget(self.barra_do_foco)
        # O bloco impresso sob o cursor, na largura do editor (S-643): quem corrige OCR compara a
        # letra impressa e a lida sem atravessar a tela com os olhos. Só na mesa, e só com a folha.
        self.faixa_impressa = QLabel(self)
        self.faixa_impressa.setAccessibleName("Bloco impresso sob o cursor")
        self.faixa_impressa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.faixa_impressa.hide()
        caixa.addWidget(self.faixa_impressa)

        self.selo_da_folha = QLabel("", self)
        self.selo_da_folha.setObjectName("seloDaFolha")
        self.selo_da_folha.setWordWrap(True)
        self.selo_da_folha.setAccessibleName("Aviso sobre a leitura desta folha")
        self.selo_da_folha.setVisible(False)
        caixa.addWidget(self.selo_da_folha)
        self.editor = QTextEdit(self)
        self.editor.setAccessibleName("Folha transcrita")
        # O `Tab` sai da folha, como da caixa do comentário do Estudo. Guardado pelo editor, ele
        # escrevia uma tabulação no texto e a tecla nunca passava dali: quem anda pelo teclado não
        # alcançava o resto da aba (OCR_UI ciclo 2, fase 5, crítico do ciclo 4, portão `teclado`).
        # A tabulação que precisar entrar na folha entra colada.
        self.editor.setTabChangesFocus(True)
        self.vista.corpo_de_base = self.editor.font().pointSize()
        self.editor.setAcceptRichText(False)
        # O menu do botão direito é o do próprio editor, mais o que a miniatura sabe fazer (item 10).
        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self.miniaturas.abrir_menu_de_contexto)
        # **O estado vazio deixou de ser `placeholderText`** (F9-C2, §7 item 3). A frase continua
        # sendo texto de interface e continua em `ui/strings.py`; o que mudou é o desenho:
        # `placeholderText` não elide **nem quebra linha**, e o crítico do ciclo 1 mediu a dica
        # **cortada em 77 px** em toda janela de 1280 px ou menos -- inclusive no tamanho mínimo,
        # ou seja, num tamanho em que ela nunca é legível. `EstadoVazio` quebra linha, tem título
        # e traz o botão que resolve para dentro do vazio. Ele é sobreposto ao editor e some no
        # primeiro caractere, então continua sem ser exportado com a folha.
        self.editor.setUndoRedoEnabled(False)
        """**O desfazer do Qt fica desligado de propósito.** A pilha deste painel é de
        *documentos* (`rico.DocumentoRico`), e não de edições de texto: uma ferramenta de formato
        não muda um caractere, e o desfazer nativo não a veria. Duas pilhas dariam um `Ctrl+Z` que
        às vezes desfaz o negrito e às vezes a palavra."""
        self.vazio = EstadoVazio(
            self.editor,
            titulo=strings.TEXTO_VAZIO_TITULO,
            # A frase **sem** o "Nenhuma folha lida." da frente: o título já o diz, e repeti-lo
            # a 20 px de distância é a mesma duplicação que o §7 mandou apagar na Galeria.
            frase=strings.TEXTO_VAZIO_FRASE,
            rotulo_do_botao=comandos.rotulo_de_botao("ler_folha"),
            nome_acessivel="Ler a folha da página aberta",
            acao=self.ler,
        )
        self.editor.textChanged.connect(self.vista.mostrar_vazio)
        # A barra diz o estilo, a cor e o realce que valem sob o cursor (S-292, item 22).
        self.editor.cursorPositionChanged.connect(self.ferramentas.seguir_o_cursor)
        folha = self.editor.viewport()
        assert folha is not None  # o editor recém-montado sempre tem a área de desenho
        folha.installEventFilter(self)
        # O `Ctrl+Z` de dentro da folha. Ver `TECLAS_DO_HISTORICO`.
        self.editor.installEventFilter(self)
        self._teclas_do_historico = _teclas_da_tabela(TECLAS_DO_HISTORICO)
        self._teclas_do_editor = _teclas_do_editor()
        """As teclas que só valem dentro da folha (`atalhos.TECLAS_DO_EDITOR`), já traduzidas para o
        Qt: `Ctrl+B`, `Ctrl+I`, `F7`, `Alt+X`... É a tabela de onde `_ligar_teclas_do_editor` monta
        um `QShortcut` por tecla -- e o único caminho por onde elas disparam. A que não traduz sai
        no log em vez de custar o painel."""
        self._ligar_teclas_do_editor()
        corpo = QHBoxLayout()
        # O painel de navegação à esquerda da folha (S-654), com o índice das folhas do caderno
        # numa das abas (S-613); nasce escondido, como a paleta.
        self.navegacao = PainelDeNavegacao(self)
        self.indice = self.navegacao.indice
        self.indice.folha_escolhida.connect(self.caderno.abrir_do_indice)
        self.indice.alinhar_pedido.connect(self.miniaturas.alinhar_diagramas_do_caderno)
        self.navegacao.ir_para.connect(self.correcao.ir_para_intervalo)
        self.navegacao.busca_mudou.connect(self.correcao.refazer_resultados)
        self.navegacao.currentChanged.connect(lambda _i: self.correcao.refazer_navegacao())
        self._corpo = corpo
        corpo.addWidget(self.navegacao)
        corpo.addWidget(self.editor, 1)
        corpo.addWidget(self.correcao.montar_paleta())
        caixa.addLayout(corpo, 1)
        caixa.addLayout(self.vista.montar_rodape())

    def _ligar_teclas_do_editor(self) -> None:
        """As teclas próprias do editor (S-241/S-259/S-263), ligadas **no widget** (S-511).

        `atalhos.TECLAS_DO_EDITOR` é a única declaração delas, e do lado do Tk quem as ligava era
        o `Text.bind`. O porte trouxe a tabela e não o `bind`: `Ctrl+B` não fazia nada no Qt, sem
        erro nenhum, porque a tabela continuava lá e nenhuma guarda perguntava se alguém a lia.

        Duas coisas, e as duas vêm de `ui/atalhos.py`. Um `QShortcut` por linha da tabela, com
        alcance no editor, disparando o método de `COMANDOS_DA_ABA` -- o mesmo do botão. E
        `teclas_proprias` no próprio widget, que é o que `qt/atalhos.cede_a_tecla` lê para
        entregar ao editor as teclas que ele **divide** com a janela (`Ctrl+R`, `Ctrl++`,
        `Ctrl+-`) e não a que a janela ganha (`Ctrl+H`, que chega por `acoes_proprias`).
        `teclas_cedidas_ao_editor` levanta na montagem se uma tecla nova entrar nas duas tabelas
        sem `SOBREPOSICOES_NO_EDITOR` dizer de quem ela é.
        """
        self.editor.teclas_proprias = atalhos.teclas_cedidas_ao_editor()  # type: ignore[attr-defined]
        for acao, tecla in self._teclas_do_editor.items():
            atalho = QShortcut(tecla, self.editor)
            atalho.setContext(Qt.ShortcutContext.WidgetShortcut)
            atalho.activated.connect(partial(self.executar, acao))

    def _alvo_da_fita(self, acao: str) -> Callable[[], object]:
        """Quem atende um botão da fita: o painel (pela tabela ou pelas ações próprias), ou a janela."""
        if acao in COMANDOS_DA_ABA:
            return lambda: self.executar(acao)
        proprio = self.atender(acao)
        if proprio is not None:
            return proprio
        return lambda: self._executar_fora(acao)

    def definir_executor(self, executor: Callable[[str], object] | None) -> None:
        """Quem roda os comandos da fita que são da janela -- a mesa, por exemplo. `None` os desliga."""
        self._executor = executor

    def _executar_fora(self, acao: str) -> None:
        if self._executor is None:
            self.estado.emit(f"«{comandos.rotulo(acao)}» é da janela, e esta aba está sozinha.")
            return
        self._executor(acao)

    # ------------------------------------------------------------------------ o documento na tela

    def desenhar_documento(self, doc: rico.DocumentoRico, *, selecao: tuple[int, int] | None = None) -> None:
        """Troca o documento e o desenha. **Este laço não decide nada.**

        Faixa, ordem, separador e atributo já vieram decididos por `text/rico.py`; o que sobra
        aqui é escrever no cursor e pôr a miniatura. É a mesma fronteira do outro frontend.

        `selecao` é `(âncora, ponta)` em deslocamento do documento novo: onde o cursor fica depois
        do desenho. `None` é folha nova -- o cursor volta ao começo, que é o certo para a leitura
        e para o arquivo aberto, e o errado para o negrito no meio da página.
        """
        self.documento = doc
        self.espelho.desenhar(selecao=selecao)
        self.documento_mudou.emit()

    def contem(self, widget: object) -> bool:
        """Este widget está dentro desta aba? É o que decide de quem é o `Ctrl+Z` (S-243)."""
        return qt_atalhos.contem(self, widget)

    def texto(self) -> str:
        """O texto puro do documento -- **do documento, e não do widget**.

        O widget tem a miniatura e a quebra do desenho; o documento não. É a mesma distinção que
        `texto_espelho.Mapa` mantém, do lado da exportação.
        """
        return self.documento.para_texto()

    @property
    def tem_alteracoes(self) -> bool:
        """A folha tem edição que ainda não está no disco? É o que o fechamento e a releitura perguntam.

        **Comparada com o que foi gravado, e não com a pilha.** A pilha dizia "editado" também
        depois de gravar -- e aí a pergunta "descarta as alterações?" chegava sobre um texto que já
        estava salvo, que é o jeito de ensinar a clicar "Sim" sem ler. Desfazer até o que estava
        gravado também não deixa nada a perder, e a comparação por valor vê isso.
        """
        return self.documento != self._documento_gravado

    # --------------------------------------------------------------------------- a sessão (S-291)

    def aplicar_estado(self, estado: AppState) -> None:
        """A vista da aba como a sessão anterior a deixou: zoom, quebra, motor, os diagramas e a letra.

        **Os padrões são os do `AppState`** (S-828): o campo que o disco não trouxe já chega com
        ele, e repeti-lo aqui num `getattr` era um segundo lugar para a mesma decisão.
        """
        self.vista.aplicar_zoom(estado.texto_zoom, avisar=False)
        self.vista.definir_quebra(estado.texto_quebra)
        self.leitura.definir_motor(estado.texto_motor)  # o motor da sessão anterior (item 17)
        self.leitura.definir_lingua(estado.texto_lingua)
        self.miniaturas.definir_diagramas(estado.texto_diagramas)
        self.miniaturas.definir_tamanho_da_miniatura(estado.texto_miniatura)
        self.vista.definir_familia_da_letra(estado.texto_familia)
        self.miniaturas.definir_texto_ao_lado(estado.texto_ao_lado)
        self.caderno.ler_ao_chegar = estado.texto_ler_ao_chegar
        self._pasta_da_transcricao = estado.texto_transcricao_pasta
        for canal, nome in (("letra", estado.texto_ultima_cor), ("realce", estado.texto_ultimo_realce)):
            if nome in texto_cores.nomes():
                self.ferramentas.ultimas_cores[canal] = nome
        self.ferramentas.mostrar_ultima_cor(self.ferramentas.cor_rapida, "letra")
        self.ferramentas.mostrar_ultima_cor(self.ferramentas.realce_rapido, "realce")
        self.fita.definir_recolhida(estado.texto_fita_recolhida)
        self.correcao.glifos_recentes = list(estado.texto_glifos_recentes)[:texto_correcao.GLIFOS_RECENTES]
        self.correcao.encher_a_paleta()

    def anotar_estado(self, estado: AppState) -> None:
        """O contrário de `aplicar_estado`: a vista da aba vai ao estado que a janela grava."""
        estado.texto_zoom = int(self.vista.zoom_da_vista)
        estado.texto_quebra = bool(self.vista.quebra)
        estado.texto_motor = self.leitura.motor
        # **O padrão, e não a língua do livro aberto**: esta mora no caderno, e não pode vazar para o livro seguinte (S-723).
        estado.texto_lingua = self.leitura.lingua_padrao
        estado.texto_diagramas = self.miniaturas.diagramas
        estado.texto_miniatura = self.miniaturas.tamanho_da_miniatura
        estado.texto_familia = self.vista.familia_da_letra
        estado.texto_ao_lado = self.miniaturas.texto_ao_lado
        estado.texto_ler_ao_chegar = self.caderno.ler_ao_chegar
        estado.texto_transcricao_pasta = self._pasta_da_transcricao
        estado.texto_ultima_cor = self.ferramentas.ultimas_cores["letra"]
        estado.texto_ultimo_realce = self.ferramentas.ultimas_cores["realce"]
        estado.texto_fita_recolhida = self.fita.recolhida
        estado.texto_glifos_recentes = list(self.correcao.glifos_recentes)

    # ------------------------------------------------------------------ o livro e a folha (S-283)

    def definir_livro(self, pdf: Path | None, *, pagina: int | None = None, paginas: int | None = None) -> None:
        """Diz à aba qual livro está aberto, em que folha o visualizador está e quantas folhas há.

        **A folha lida não cai junto**, e é de propósito: trocar de livro com uma folha corrigida
        na tela e ainda por gravar jogaria fora o trabalho sem perguntar. Quem descarta é `ler`,
        que pergunta antes.

        `paginas` é o teto do campo «Folha a ler» (item 15): com 9.999 cravado, quem digitava 500
        num livro de 289 folhas só descobria o erro na leitura, com a caixa vermelha do PyMuPDF.
        Sem o número (livro fechado, ou chamada antiga) o teto fica largo, como era.
        """
        novo = None if pdf is None else Path(pdf)
        if chave_do_livro(novo) != chave_do_livro(self._pdf):
            self._posicoes.clear()  # as posições são do livro que saiu (item 11)
            self.caderno.abrir_caderno(novo)
            self.leitura.carregar_lingua_do_livro()
            if self.caderno.aberto is None:
                self.caderno.anunciar_rascunhos(novo)
            self.caderno.rotular_leitura()
        self._pdf = novo
        # O teto só muda quando se sabe o número ou quando o livro fecha: a virada de página chama
        # isto sem `paginas`, e não pode devolver o campo ao teto largo.
        if paginas:
            self.leitura.campo_de_folha.setMaximum(max(1, int(paginas)))
        elif novo is None:
            self.leitura.campo_de_folha.setMaximum(texto_leitura.TETO_DE_FOLHAS)
        if pagina is not None:
            self._pagina_indice = int(pagina)
            self.leitura.campo_de_folha.setValue(self._pagina_indice + 1)
            if self.caderno.na_mesa and novo is not None:
                self.caderno.seguir_a_pagina(int(pagina))

    # ---------------------------------------------------- os eventos da folha e o teclado (S-825)

    def eventFilter(self, a0: object, a1: object) -> bool:  # noqa: N802 - assinatura do Qt
        """O evento vai ao tratador do par `(objeto, tipo)` da tabela (S-825); o que ela não tem é do Qt.

        O tratador que devolve `False` deixa o evento seguir: é o `Esc` sem nada armado, o `Enter`
        fora de uma marca, a roda sem `Ctrl`. Uma exceção num tratador vai ao `sys.excepthook` pela
        borda da S-800, como em qualquer slot.
        """
        if isinstance(a1, QEvent):
            tratador = self._filtros.get((a0, a1.type()))
            if tratador is not None and tratador(a1):
                return True
        return super().eventFilter(a0, a1)  # type: ignore[arg-type]

    def _tabela_de_filtros(self) -> dict[tuple[object, QEvent.Type], Callable[[QEvent], bool]]:
        """Quem trata o quê, nos três objetos em que o filtro está instalado (`_montar`).

        Montada **depois** de `_montar`, e por isso sem o `getattr` de antes: o filtro já está no
        editor quando o corpo é montado, e os eventos dessa montagem chegam com a tabela vazia.
        """
        folha = self.editor.viewport()
        return {
            (self.editor, QEvent.Type.KeyPress): self._tecla_na_folha,
            (self.vista.status, QEvent.Type.MouseButtonRelease): self.vista.clique_no_rodape,
            (folha, QEvent.Type.Resize): self.vista.folha_mudou_de_tamanho,
            (folha, QEvent.Type.ToolTip): self.miniaturas.dica_na_folha,
            (folha, QEvent.Type.Wheel): self.vista.roda_na_folha,
            (folha, QEvent.Type.MouseButtonPress): self.miniaturas.clique_na_folha,
            (folha, QEvent.Type.MouseButtonDblClick): self.miniaturas.duplo_clique_na_folha,
        }

    def _tecla_na_folha(self, evento: QEvent) -> bool:
        """`Ctrl+Z` e `Ctrl+Y` dentro da folha são deste painel; `Esc` desarma; `Enter` ativa a marca.

        A tecla de desfazer chega ao editor porque a guarda de atalhos a cede a todo campo de
        texto -- e o desfazer do `QTextEdit` está desligado. Ver `TECLAS_DO_HISTORICO`.
        """
        if not isinstance(evento, QKeyEvent):
            return False
        combinacao = QKeySequence(evento.keyCombination())
        for acao, tecla in self._teclas_do_historico.items():
            alvo = self.atender(acao) if tecla == combinacao else None
            if alvo is not None:
                alvo()
                return True
        if evento.key() == Qt.Key.Key_Escape:
            return self.correcao.sair_com_esc()
        # Enter com a marca inteira selecionada abre o diagrama no Estudo (item 30): é o duplo
        # clique do item 8 para quem anda pelo teclado -- o clique (ou Shift+setas) seleciona a
        # marca, o Enter a ativa. Com qualquer outra seleção o Enter é o Enter.
        if evento.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not evento.modifiers():
            return self.miniaturas.ativar_marca_selecionada()
        return False

    # ------------------------------------------------------- as ações e o catálogo (S-240, S-244)

    def acoes_proprias(self) -> frozenset[str]:
        """As ações globais que este painel atende enquanto tem o foco (S-244).

        A lista é `ui/texto_declarado.ACOES_PROPRIAS`, a mesma do outro frontend: `Ctrl+S` com o
        cursor no texto salva o texto, e não a posição do tabuleiro.
        """
        return ACOES_PROPRIAS

    def atender(self, acao: str) -> Callable[[], object] | None:
        """A função deste painel para aquela ação. Declarar e não atender come a tecla."""
        return {
            "salvar": self.salvar_documento,
            "desfazer": self.desfazer,
            "refazer": self.refazer,
            "achar": self.achar,
            "substituir": self.substituir,
        }.get(acao)

    def executar(self, acao: str) -> None:
        """Roda o método que `COMANDOS_DA_ABA` liga àquela ação.

        **A tabela é a mesma dos dois frontends**, e é por isso que os métodos deste painel se
        chamam como os de `ui/texto_panel.py`. Um método com outro nome deixaria o comando no menu,
        na paleta e nas três peles -- sem fazer nada, e sem nada acusar (S-240).
        """
        self.espelho.rotulo_corrente = comandos.rotulo_de_botao(acao) if _no_catalogo(acao) else acao
        try:
            getattr(self, COMANDOS_DA_ABA[acao])()
        finally:
            self.espelho.rotulo_corrente = ""

    # --------------------------------------------- a pilha do desfazer, em qt/texto_espelho.py (S-865)

    @property
    def edicao(self) -> int:
        """Contador que só cresce, como manda `ui/desfazivel.Desfazivel`. Zero = nunca editado."""
        return self.espelho.edicao

    def desfazer(self) -> None:
        self.espelho.desfazer()

    def refazer(self) -> None:
        self.espelho.refazer()

    def desfazer_ate(self, passos: int) -> None:
        self.espelho.desfazer_ate(passos)

    # ------------------------------------------------ o formato, em qt/texto_ferramentas.py (S-865)

    def negrito(self) -> None:
        self.ferramentas.alternar("negrito")

    def italico(self) -> None:
        self.ferramentas.alternar("italico")

    def sublinhado(self) -> None:
        self.ferramentas.alternar("sublinhado")

    def tachado(self) -> None:
        self.ferramentas.alternar("tachado")

    def limpar_formato(self) -> None:
        self.ferramentas.limpar_formato()

    def limpar_cor(self) -> None:
        """Tira a cor do autor. **Não** toca a faixa de confiança (S-242)."""
        self.ferramentas.pintar_letra("")

    def escolher_cor(self) -> None:
        self.ferramentas.escolher_cor()

    def escolher_realce(self) -> None:
        self.ferramentas.escolher_realce()

    def estilo_titulo(self) -> None:
        self.ferramentas.aplicar_estilo(rico.ESTILO_TITULO)

    def estilo_prosa(self) -> None:
        self.ferramentas.aplicar_estilo(rico.ESTILO_PROSA)

    def estilo_notacao(self) -> None:
        self.ferramentas.aplicar_estilo(rico.ESTILO_NOTACAO)

    def estilo_legenda(self) -> None:
        self.ferramentas.aplicar_estilo(rico.ESTILO_LEGENDA)

    def alinhar_esquerda(self) -> None:
        self.ferramentas.alinhar(rico.ALINHAMENTO_ESQUERDA)

    def alinhar_centro(self) -> None:
        self.ferramentas.alinhar(rico.ALINHAMENTO_CENTRO)

    def alinhar_direita(self) -> None:
        self.ferramentas.alinhar(rico.ALINHAMENTO_DIREITA)

    def justificar(self) -> None:
        self.ferramentas.alinhar(rico.ALINHAMENTO_JUSTIFICADO)

    def aumentar_corpo(self) -> None:
        self.ferramentas.mudar_corpo(+1)

    def diminuir_corpo(self) -> None:
        self.ferramentas.mudar_corpo(-1)

    def corpo_normal(self) -> None:
        self.ferramentas.corpo_normal()

    def maiusculas(self) -> None:
        self.ferramentas.mudar_caixa(rico.CAIXA_ALTA)

    def minusculas(self) -> None:
        self.ferramentas.mudar_caixa(rico.CAIXA_BAIXA)

    def capitular(self) -> None:
        self.ferramentas.mudar_caixa(rico.CAIXA_INICIAIS)

    def selecionar_tudo(self) -> None:
        self.ferramentas.selecionar_tudo()

    def recortar(self) -> None:
        self.ferramentas.recortar()

    def copiar(self) -> None:
        self.ferramentas.copiar()

    def colar(self) -> None:
        self.ferramentas.colar()

    # ------------------------------------------------------- a vista, em qt/texto_vista.py (S-865)

    def aproximar_texto(self) -> None:
        self.vista.aproximar_texto()

    def afastar_texto(self) -> None:
        self.vista.afastar_texto()

    def zoom_do_texto_normal(self) -> None:
        self.vista.zoom_do_texto_normal()

    def quebrar_linha(self) -> None:
        self.vista.quebrar_linha()

    def mudar_familia_da_letra(self) -> None:
        self.vista.mudar_familia_da_letra()

    def alternar_modo_foco(self) -> None:
        self.vista.alternar_modo_foco()

    def alternar_marcas_de_formatacao(self) -> None:
        self.vista.alternar_marcas_de_formatacao()

    def alternar_fita(self) -> None:
        self.vista.alternar_fita()

    # ---------------------------------------------- a correção, em qt/texto_correcao.py (S-865)

    def achar(self) -> JanelaDeBusca:
        return self.correcao.achar()

    def substituir(self) -> JanelaDeBusca:
        return self.correcao.substituir()

    def marcar_fora_do_lexico(self) -> None:
        self.correcao.marcar_fora_do_lexico()

    def limpar_marcas_do_lexico(self) -> None:
        self.correcao.limpar_marcas_do_lexico()

    def proxima_fora_do_lexico(self) -> None:
        self.correcao.proxima_fora_do_lexico()

    def proxima_a_revisar(self) -> None:
        self.correcao.proxima_a_revisar()

    def inserir_simbolo(self, simbolo: str) -> None:
        self.correcao.inserir_simbolo(simbolo)

    def inserir_figurina(self) -> QMenu:
        return self.correcao.inserir_figurina()

    def inserir_avaliacao(self) -> QMenu:
        return self.correcao.inserir_avaliacao()

    def alternar_paleta(self) -> None:
        self.correcao.alternar_paleta()

    def pincel_de_formatacao(self) -> None:
        self.correcao.pincel_de_formatacao()

    def copiar_formato(self) -> None:
        self.correcao.copiar_formato()

    def colar_formato(self) -> None:
        self.correcao.colar_formato()

    def alternar_navegacao(self) -> None:
        self.correcao.alternar_navegacao()

    def mostrar_correcoes(self) -> None:
        self.correcao.mostrar_correcoes()

    def mover_paragrafo_acima(self) -> None:
        self.correcao.mover_paragrafo(-1)

    def mover_paragrafo_abaixo(self) -> None:
        self.correcao.mover_paragrafo(+1)

    def codigo_unicode(self) -> None:
        self.correcao.codigo_unicode()

    # --------------------------------------------- os diagramas, em qt/texto_miniaturas.py (S-865)

    def definir_diagramas(self, preferencia: str) -> None:
        self.miniaturas.definir_diagramas(preferencia)

    def definir_texto_ao_lado(self, ligado: bool) -> None:
        self.miniaturas.definir_texto_ao_lado(ligado)

    def alternar_diagramas_a_esquerda(self) -> None:
        self.miniaturas.alternar_diagramas_a_esquerda()

    def alternar_texto_ao_lado(self) -> None:
        self.miniaturas.alternar_texto_ao_lado()

    def mudar_tamanho_da_miniatura(self) -> None:
        self.miniaturas.mudar_tamanho_da_miniatura()

    def diagramas_da_folha_a_esquerda(self) -> None:
        self.miniaturas.alinhar_os_diagramas_da_folha(rico.ALINHAMENTO_ESQUERDA)

    def diagramas_da_folha_ao_centro(self) -> None:
        self.miniaturas.alinhar_os_diagramas_da_folha(rico.ALINHAMENTO_CENTRO)

    def diagramas_da_folha_como_a_preferencia(self) -> None:
        self.miniaturas.alinhar_os_diagramas_da_folha("")

    def interruptores_da_vista(self) -> dict[str, bool]:
        return self.miniaturas.interruptores_da_vista()

    def definir_posicoes(self, pagina: int, posicoes: Sequence[str]) -> None:
        self.miniaturas.definir_posicoes(pagina, posicoes)

    def inserir_diagramas_do_livro(self, pagina: int, faltam: Sequence[tuple[str, str]]) -> int:
        return self.miniaturas.inserir_diagramas_do_livro(pagina, faltam)

    def notacao_do_diagrama(self, pagina: int, diagrama: int) -> str:
        return self.miniaturas.notacao_do_diagrama(pagina, diagrama)

    # ------------------------------------------------ as tarefas, em qt/texto_leitura.py (S-865)

    def ler(self) -> None:
        self.leitura.ler()

    def ler_de_novo(self) -> None:
        self.leitura.ler_de_novo()

    def sincronizar_com_a_pagina(self) -> None:
        self.leitura.sincronizar_com_a_pagina()

    def escolher_lingua_do_livro(self) -> None:
        self.leitura.escolher_lingua_do_livro()

    def limpar_cache_de_leitura(self) -> None:
        self.leitura.limpar_cache_de_leitura()

    def salvar(self) -> None:
        """O `.txt` puro, ao lado do `.cvtxt`: quem quer colar num e-mail quer este."""
        self.leitura.exportar(".txt")

    def exportar_md(self) -> None:
        """`.md` **porque ele diffa**: duas correções da mesma folha comparam linha a linha."""
        self.leitura.exportar(".md")

    def exportar_html(self) -> None:
        self.leitura.exportar(".html")

    def exportar_rtf(self) -> None:
        self.leitura.exportar(".rtf")

    def exportar_pdf_pesquisavel(self) -> None:
        """O livro com a camada de texto por cima -- o que faz o PDF ser pesquisável."""
        self.leitura.exportar(".pdf")

    def exportar_caderno(self) -> None:
        self.leitura.exportar_caderno()

    def trazer_da_revisao(self) -> bool:
        return self.leitura.trazer_da_revisao()

    def definir_fornecedor_de_folha(self, fornecedor: Callable[[int], tuple[np.ndarray, int] | None] | None) -> None:
        self.leitura.definir_fornecedor_de_folha(fornecedor)

    def definir_importacao(self, fornecedor: texto_leitura.Importacao | None) -> None:
        self.leitura.definir_importacao(fornecedor)

    # ----------------------------------------- o caderno e a mesa, em qt/texto_caderno.py (S-865)

    def mostrar_pagina(self, pagina: PaginaLida, *, folha_rgb: np.ndarray | None = None, dpi: int | None = None) -> None:
        self.caderno.mostrar_pagina(pagina, folha_rgb=folha_rgb, dpi=dpi)

    def confirmar_fechamento(self) -> bool:
        # São horas de alguém, e o relógio de gravação pode não ter disparado (S-703). O que não gravou pergunta antes de se perder.
        if self.transcricao is not None and not self.transcricao.desativar() and not self.caderno.confirmar_descarte(
            "Fechar a janela descarta a transcrição que não foi gravada.", ao_fechar=True
        ):
            return False
        return self.caderno.confirmar_fechamento()

    def abrir(self, doc: rico.DocumentoRico, *, folha_rgb: np.ndarray | None = None, renderizar: bool = True) -> None:
        self.caderno.abrir(doc, folha_rgb=folha_rgb, renderizar=renderizar)

    def abrir_documento(self) -> None:
        self.caderno.abrir_documento()

    def salvar_documento(self) -> None:
        self.caderno.salvar_documento()

    def salvar_documento_como(self) -> None:
        self.caderno.salvar_documento_como()

    def voltar_a_anterior(self) -> bool:
        return self.caderno.voltar_a_anterior()

    def corrigir_em_todas_as_folhas(self) -> QDialog | None:
        return self.caderno.corrigir_em_todas_as_folhas()

    def folhas_corrigidas_no_livro(self, feito: Any) -> None:
        self.caderno.folhas_corrigidas_no_livro(feito)

    def descartar_correcoes(self) -> bool:
        return self.caderno.descartar_correcoes()

    def marcar_conferida(self) -> bool:
        return self.caderno.marcar_conferida()

    def alternar_indice(self) -> None:
        self.caderno.alternar_indice()

    def alternar_ler_ao_chegar(self) -> None:
        self.caderno.alternar_ler_ao_chegar()

    def alternar_bloco_impresso(self) -> None:
        self.caderno.alternar_bloco_impresso()

    def folhas_para_a_suite(self, paginas: Sequence[int] | None) -> FolhasDaSuite:
        return self.caderno.folhas_para_a_suite(paginas)

    def folhas_do_livro(self, livro: Path | str, paginas: Sequence[int] | None) -> FolhasDaSuite:
        return self.caderno.folhas_do_livro(livro, paginas)

    @property
    def destacada(self) -> bool:
        return self.caderno.destacada

    def definir_mesa(self, ligada: bool) -> None:
        self.caderno.definir_mesa(ligada)

    def definir_destacada(self, destacada: bool) -> None:
        self.caderno.definir_destacada(destacada)

    def folha_rasterizada(self) -> tuple[np.ndarray | None, int]:
        return self.caderno.folha_rasterizada()

    def folha_atual(self) -> tuple[int, int]:
        return self.caderno.folha_atual()

    def folha_por_ler(self) -> bool:
        return self.caderno.folha_por_ler()

    def virar_folha(self, passo: int) -> bool:
        return self.caderno.virar_folha(passo)

    def ir_ao_ponto(self, x: float, y: float) -> bool:
        return self.caderno.ir_ao_ponto(x, y)

    # ------------------------------------------------------------- o modo transcrição (S-703)

    @property
    def em_transcricao(self) -> bool:
        return self.transcricao is not None and self.transcricao.isVisibleTo(self)

    def alternar_transcricao(self) -> None:
        """Liga ou desliga o modo. **O editor sai de cena**: ele mostra a leitura de um motor, e quem transcreve não pode vê-la."""
        if self.transcricao is None:
            from chess_diagram_ocr.qt.modo_transcricao import ModoTranscricao

            self.transcricao = ModoTranscricao(self)
            self.transcricao.fechar_pedido.connect(self.alternar_transcricao)
            self.transcricao.pasta_mudou.connect(self._anotar_pasta_da_transcricao)
            self._corpo.insertWidget(self._corpo.indexOf(self.editor) + 1, self.transcricao, 1)
            self.transcricao.hide()
            if self._pasta_da_transcricao:
                self.transcricao.definir_pasta(self._pasta_da_transcricao)
        ligar = not self.em_transcricao
        if ligar:
            self.transcricao.definir_livro(self._pdf)
            self.transcricao.ativar()
        elif not self.transcricao.desativar():
            self.transcricao.ativar()  # o digitado não foi gravado: o modo fica, com a frase da recusa
            return
        self.editor.setVisible(not ligar)
        self.transcricao.setVisible(ligar)

    def _anotar_pasta_da_transcricao(self, pasta: str) -> None:
        self._pasta_da_transcricao = pasta


def _no_catalogo(acao: str) -> bool:
    """Se o catálogo de comandos conhece esta ação. Ver `_botao`."""
    try:
        comandos.rotulo(acao)
    except KeyError:
        return False
    return True


def _teclas_do_editor() -> dict[str, QKeySequence]:
    """`ação -> QKeySequence` das teclas próprias do editor (`atalhos.TECLAS_DO_EDITOR`)."""
    teclas: dict[str, QKeySequence] = {}
    for acao, sequencia in atalhos.TECLAS_DO_EDITOR.items():
        try:
            teclas[acao] = QKeySequence(qt_atalhos.sequencia_qt(sequencia))
        except ValueError as erro:
            logger.warning("A tecla de %s não traduziu para o Qt (%s).", acao, erro)
    return teclas


def _teclas_da_tabela(acoes: Iterable[str]) -> dict[str, QKeySequence]:
    """`ação -> QKeySequence`, **da tabela** (`ui/atalhos`). Ação sem tecla fica de fora, sem levantar.

    Uma tecla que não traduz não pode custar o painel: ela sai no log, e o botão da barra continua
    desfazendo -- é a disciplina de `qt/menu._acao`.
    """
    teclas: dict[str, QKeySequence] = {}
    for acao in acoes:
        atalho = atalhos.por_acao.get(acao)
        if atalho is None:
            continue
        try:
            teclas[acao] = QKeySequence(qt_atalhos.sequencia_qt(atalho.sequencia))
        except ValueError as erro:
            logger.warning("A tecla de %s não traduziu para o Qt (%s).", acao, erro)
    return teclas
