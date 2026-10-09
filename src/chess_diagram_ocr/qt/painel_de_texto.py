"""A aba de texto no Qt: a página inteira num editor, com os diagramas onde eles estão (S-211/S-504).

**Quase nada é decidido aqui**, e é a mesma frase do cabeçalho de `ui/texto_panel.py`. Onde o
diagrama entra no fluxo, o que merece destaque e o que vai para o arquivo são de
`text/documento.py`; o que a edição faz com um trecho é de `text/rico.py`; o que a busca acha é de
`text/busca.py`. Nenhum dos três importa toolkit nenhum. Este arquivo é o que sobra: widgets, uma
thread e o vaivém entre o deslocamento do documento e a posição do cursor.

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

**O deslocamento é a fronteira estreita.** As funções puras falam em deslocamento de caractere do
*documento*; o `QTextEdit` fala em posição do *cursor*. Os dois divergem porque a miniatura do
diagrama vale um caractere para o Qt e nenhum para o documento -- exatamente o que
`ui/texto_etiquetas.deslocamento` resolvia do outro lado, percorrendo o `dump` do widget a cada
pergunta. Ver `_Mapa`.

**A digitação atravessa a mesma fronteira, no outro sentido.** O editor é editável, e o que se
digita nele acontece primeiro no widget. O porte deixou só essa metade: a letra ficava na tela e
fora do documento, e o primeiro redesenho -- o negrito seguinte, o `Ctrl+Z`, o zoom -- a apagava
sem dizer nada; gravar e exportar levavam a folha de antes. Agora cada mudança do texto chega por
`QTextDocument.contentsChange` e vira uma função pura de `rico` (`editar`, `mover`), pela mesma
tradução de `_Mapa`. Quem decide o que a tecla faz com a corrida -- de quem herda, que faixa leva, o
que acontece com a marca do diagrama -- é `rico`; quando a tecla fecha um passo de desfazer é
`ui/texto_declarado`. Aqui fica o vaivém -- e **sem redesenho por tecla**: o widget já tem a letra,
o mapa anda junto com ela e só o trecho digitado é repintado. Redesenhar a folha inteira, com as
miniaturas, é o que o portão de bloqueio da thread da janela não deixaria passar a cada tecla.

**O diagrama é recorte da folha, e a folha vem da leitura.** `ler_pagina` rasteriza a página para
ler o texto, e a miniatura de cada `[Diagrama N]` é o pedaço dessa mesma imagem no `bbox` do bloco
-- em pontos, convertidos pelo mesmo DPI dos dois lados (`_recorte_da_folha`). O porte inicial
descartava a imagem na volta da thread, e a aba mostrava a marca sem figura nenhuma; agora a folha
é rasterizada **uma vez**, na thread de trabalho (S-352), entregue a `ler_pagina` por `imagem_rgb`
e guardada para as miniaturas, para os recortes da exportação (`_gravar_recortes`, S-338) e para o
`.cvtxt` reaberto, que a refaz do livro se ele ainda estiver onde estava (`abrir`). O rascunho
automático (S-255) e a procedência humana ao gravar (S-239) vieram no mesmo movimento: eles moram
em `text/rascunho.py` e `text/correcao.py`, e aqui ficam só o relógio de inatividade e a pergunta.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPixmap,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextImageFormat,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.imagens import pixmap_de_rgb
from chess_diagram_ocr.qt.texto_formato import bloco_de, formato_de
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.qt.vazio import EstadoVazio
from chess_diagram_ocr.text import busca, correcao, rascunho, rico
from chess_diagram_ocr.text.documento import PaginaLida
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama
from chess_diagram_ocr.ui import atalhos, comandos, espaco, estilos, strings, texto_cores, tokens
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.texto_declarado import (
    ACOES_PROPRIAS,
    COMANDOS_DA_ABA,
    MOTORES,
    ZOOM_MAXIMO,
    ZOOM_MINIMO,
    Digitacao,
    continua_a_digitacao,
    digitacao_depois,
    fora_do_livro,
    frase_do_rodape,
)

logger = logging.getLogger(__name__)

__all__ = ["CANCELADA", "LARGURA_DA_MINIATURA", "JanelaDeBusca", "PainelDeTexto"]

CANCELADA = "exportação cancelada pela pessoa"
"""O que a tarefa de exportação devolve quando a pessoa desistiu (F9-C2, §7 item 7).

Um valor de retorno e não uma exceção: desistir não é falhar, e uma exceção cairia em
`_exportacao_falhou`, que abre caixa vermelha. O `\u0001` na frente é o que impede uma frase de
relatório legítima de coincidir com ela."""

LARGURA_DA_MINIATURA = 160
"""A miniatura do diagrama dentro do texto, em pixel.

Grande o bastante para reconhecer a posição, pequena o bastante para a linha seguinte caber na
tela. É o mesmo alvo de `texto_panel._miniatura`."""

TETO_DE_FOLHAS = 9999
"""O teto do campo \u00abFolha a ler\u00bb enquanto a aba n\u00e3o sabe quantas folhas o livro tem (item 15)."""

OBJETO = "\ufffc"
"""Como o texto do widget conta a miniatura: um caractere que **nunca** entra no documento.

Chega também colado: o texto que o `QTextEdit` põe na área de transferência traz a miniatura
copiada como este caractere solto, sem imagem nenhuma atrás dele."""

TECLAS_DO_HISTORICO: tuple[str, ...] = ("desfazer", "refazer")
"""As ações cuja tecla, **dentro do editor**, é deste painel e não do `QTextEdit`.

A guarda de atalhos cede `Ctrl+Z` a todo campo de texto (`ui/atalhos.ACOES_DO_CAMPO`), porque o
campo tem o desfazer dele -- e este não tem: ele está desligado de propósito (ver `_montar`). Sem
pegar a tecla aqui, `Ctrl+Z` no meio da folha chegaria a um desfazer desligado e não faria nada.
A tecla sai da tabela (`ui/atalhos.por_acao`), e não daqui."""


@dataclass(frozen=True)
class _Trecho:
    """Onde uma corrida caiu no widget: começo no documento, começo no Qt, tamanho."""

    documento: int
    janela: int
    tamanho: int


class _Mapa:
    """A tradução entre o deslocamento do documento e a posição do cursor do Qt.

    **Os dois divergem, e a razão é a mesma do Tk.** A miniatura do diagrama é um caractere para o
    widget e nenhum para o documento; a quebra que o desenho acrescenta embaixo dela também não é
    do documento. Contar `len` do texto do widget erraria as duas, e o erro cresce a cada diagrama
    -- numa folha de nove, o negrito aplicado no fim cairia nove caracteres adiante.

    A tabela é construída no desenho, que é o único momento em que se sabe as duas coordenadas ao
    mesmo tempo. Era o papel de `ui/texto_etiquetas.deslocamento`, com a diferença de que lá ele
    era recalculado a cada pergunta, percorrendo o `dump` inteiro do widget.
    """

    def __init__(self) -> None:
        self._trechos: list[_Trecho] = []
        self._fim_documento = 0

    def registrar(self, documento: int, janela: int, tamanho: int) -> None:
        if tamanho > 0:
            self._trechos.append(_Trecho(documento, janela, tamanho))
            self._fim_documento = max(self._fim_documento, documento + tamanho)

    def limpar(self) -> None:
        self._trechos.clear()
        self._fim_documento = 0

    def deslocamento(self, posicao: int) -> int:
        """Da posição do cursor para o deslocamento do documento.

        Uma posição que caia **numa** miniatura -- entre dois trechos -- resolve para o começo do
        trecho seguinte: o cursor está antes do texto que vem depois da imagem, e é ali que uma
        inserção deve cair.
        """
        for trecho in self._trechos:
            if trecho.janela <= posicao < trecho.janela + trecho.tamanho:
                return trecho.documento + (posicao - trecho.janela)
            if posicao < trecho.janela:
                return trecho.documento
        return self._fim_documento

    def posicao(self, deslocamento: int) -> int:
        """A inversa. Deslocamento além do fim resolve para o fim do último trecho."""
        for trecho in self._trechos:
            if trecho.documento <= deslocamento < trecho.documento + trecho.tamanho:
                return trecho.janela + (deslocamento - trecho.documento)
        if not self._trechos:
            return 0
        ultimo = self._trechos[-1]
        return ultimo.janela + ultimo.tamanho

    def trocar(self, janela: int, removidos: int, deslocamento: int, tamanho: int) -> None:
        """Acompanha uma digitação **fiel**, sem redesenho: `removidos` saíram em `janela`, `tamanho` entraram.

        Fiel é a troca em que todo caractere que saiu e todo que entrou é do documento -- nenhuma
        miniatura, nenhuma quebra do desenho. Aí as duas coordenadas andam juntas: o que está antes
        da troca não se mexe, o que está depois anda o mesmo tanto nas duas, e o texto novo vira um
        trecho em `(deslocamento, janela)`. Os trechos que ficam colados nas duas coordenadas se
        fundem de novo -- sem isso cada tecla deixaria um trecho de uma letra, e a tabela que se
        percorre a cada pergunta cresceria com a digitação.
        """
        fim = janela + removidos
        passo = tamanho - removidos
        novos: list[_Trecho] = []
        for trecho in self._trechos:
            termino = trecho.janela + trecho.tamanho
            if termino <= janela:
                novos.append(trecho)
                continue
            if trecho.janela >= fim:
                novos.append(_Trecho(trecho.documento + passo, trecho.janela + passo, trecho.tamanho))
                continue
            if trecho.janela < janela:
                novos.append(_Trecho(trecho.documento, trecho.janela, janela - trecho.janela))
            if termino > fim:
                corte = fim - trecho.janela
                novos.append(_Trecho(trecho.documento + corte + passo, fim + passo, termino - fim))
        if tamanho > 0:
            novos.append(_Trecho(deslocamento, janela, tamanho))
        novos.sort(key=lambda trecho: trecho.janela)
        self._trechos = []
        for trecho in novos:
            anterior = self._trechos[-1] if self._trechos else None
            if (
                anterior is not None
                and anterior.documento + anterior.tamanho == trecho.documento
                and anterior.janela + anterior.tamanho == trecho.janela
            ):
                self._trechos[-1] = _Trecho(anterior.documento, anterior.janela, anterior.tamanho + trecho.tamanho)
                continue
            self._trechos.append(trecho)
        ultimo = self._trechos[-1] if self._trechos else None
        self._fim_documento = ultimo.documento + ultimo.tamanho if ultimo is not None else 0


class PainelDeTexto(QWidget):
    """O editor da página lida: desenha o documento e devolve cada gesto a `text/rico.py`."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status."""

    documento_mudou = pyqtSignal()
    """A folha foi editada. A janela usa para saber que há o que gravar."""

    diagrama_ativado = pyqtSignal(int, int)
    """Duplo clique numa miniatura: `(folha 0-based, índice do diagrama)`. A janela leva o
    diagrama à sala de estudo, como o duplo clique na caixa do visualizador (item 8)."""

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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._busy = busy
        self._pasta_de_rascunhos: Path | None = pasta_de_rascunhos
        """Onde o rascunho da S-255 é gravado. `None` usa `text/rascunho.PASTA_PADRAO`; o teste
        passa uma pasta própria, senão leria `data/rascunhos/` da máquina de quem o roda -- e um
        rascunho ali abriria a pergunta de recuperação no meio da suíte."""
        self._rascunho = QTimer(self)
        """O relógio de **inatividade** do rascunho: cada edição o reinicia, e ele grava alguns
        segundos depois da última (S-255). Um relógio fixo gravaria no meio da digitação."""
        self._rascunho.setSingleShot(True)
        self._rascunho.setInterval(int(rascunho.ESPERA_SEGUNDOS * 1000))
        self._rascunho.timeout.connect(self._depois_da_pausa)
        """O registro de ocupação (S-112). `None` é a aba montada sozinha num teste.

        **As duas operações longas desta aba precisam estar nele**, e no corte do Tk elas quase
        não ficaram: o painel de lá registrava as duas, e o porte inicial não. Ler uma folha é
        dezenas de segundos com o motor glifo, e exportar um PDF pesquisável abre o livro inteiro
        -- fechar a janela no meio de qualquer uma delas joga fora trabalho que não volta de
        graça, e o rodapé só sabe perguntar sobre o que está registrado."""
        self._ocupado: BusyToken | None = None
        self._pdf = pdf
        self._pagina_indice = pagina
        self._dpi_fixo = dpi
        """O DPI cravado por quem montou o painel -- o teste, que dá a folha sintética. `None` é o
        produto: a leitura pergunta às Configurações (`ui/configuracoes.dpi`), como o visualizador
        e a leitura dos diagramas fazem, em vez de um 220 cravado que ignorava a janela
        «Ferramentas ▸ Configurações…»."""
        self._dpi = dpi or 220
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
        self._historico: list[rico.DocumentoRico] = []
        self._edicao = 0
        """Quantas edições esta aba recebeu. É o desempate do `Ctrl+Z` sem foco (S-243)."""
        self._refeitos: list[rico.DocumentoRico] = []
        self._mapa = _Mapa()
        self._redesenhando = False
        self._tarefa: Tarefa | None = None
        self._caminho_do_documento: Path | None = None
        self._zoom_da_vista = 0
        self._conferindo_lexico = False
        """**Ligar, e não marcar uma vez** (S-293). Toda ferramenta que muda texto redesenha, e o
        redesenho apaga a marcação inteira -- então corrigir a primeira palavra marcada apagava as
        outras, e a pessoa tinha de reconferir a cada correção. Com o interruptor, a conferência se
        refaz sozinha depois de cada redesenho."""
        self._janela_de_busca: QWidget | None = None
        self._paleta: object | None = None
        self._motor = MOTORES[0]
        """O motor de leitura. O primeiro da lista é o padrão, e a S-423 explica por que ele é o
        `auto` e não o `glifo`."""
        self._modo_bloco = False
        self._tela = ""
        """O texto do widget na última mudança vista -- o `antes` de cada tecla. `contentsChange`
        diz onde mudou; é comparando com isto que se sabe **o que** saiu, e se o Qt disse a
        verdade sobre onde."""
        self._digitacao: Digitacao | None = None
        """O passo de desfazer que a digitação deixou aberto. Toda ferramenta o fecha."""
        self._relogio: Callable[[], float] = time.monotonic
        """De onde vem o "agora" da pausa que fecha o passo. Atributo para o teste poder parar o
        tempo -- esperar um segundo de verdade numa suíte é o teste que ninguém quer rodar."""
        self._sincronizando = False
        """O painel está repintando o que acabou de ser digitado: a mudança de formato que isso
        gera não é digitação."""
        self._base: tuple[int, str, str] | None = None
        """A fonte de base do último desenho. O trecho digitado é pintado com **a mesma** -- a
        tecla não relê as famílias do sistema, e o redesenho seguinte não muda o que já estava."""
        self._posicoes: dict[tuple[str, int], tuple[str, ...]] = {}
        """O campo de peças de cada diagrama, por `(livro, folha)`, como o OCR de diagramas do
        produto leu. Por folha porque a leitura dos diagramas e a do texto chegam em qualquer
        ordem; **por livro** porque a folha 14 de um livro não é a folha 14 do outro -- com a chave
        só pela folha, trocar de livro levava as posições do anterior para as folhas do novo
        (item 11). `definir_livro` para outro livro esquece tudo."""
        self._documento_ao_ler: rico.DocumentoRico | None = None
        """O documento na tela quando a leitura em curso partiu. Ver `_leitura_terminou`."""

        self._montar()
        self._desenhar()
        # Toda edição -- tecla ou ferramenta -- reinicia o relógio do rascunho. É o único ouvinte
        # deste sinal dentro do painel; o `desenhar_documento` de uma folha recém-lida também o
        # emite, e aí `gravar_rascunho` não grava: não há alteração.
        self.documento_mudou.connect(self._agendar_rascunho)
        self.documento_mudou.connect(self._atualizar_status)

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        caixa = QVBoxLayout(self)
        caixa.setContentsMargins(*(espaco.margem_da_aba(),) * 4)
        caixa.setSpacing(espaco.linha())
        caixa.addWidget(self._barra_de_ferramentas())

        self.editor = QTextEdit(self)
        self.editor.setAccessibleName("Folha transcrita")
        # O `Tab` sai da folha, como da caixa do comentário do Estudo. Guardado pelo editor, ele
        # escrevia uma tabulação no texto e a tecla nunca passava dali: quem anda pelo teclado não
        # alcançava o resto da aba (OCR_UI ciclo 2, fase 5, crítico do ciclo 4, portão `teclado`).
        # A tabulação que precisar entrar na folha entra colada.
        self.editor.setTabChangesFocus(True)
        self._corpo_de_base = self.editor.font().pointSize()
        """O corpo da fonte antes de qualquer zoom da vista. `aplicar_zoom` soma o degrau **a
        ele**, e não ao que está na tela -- somar ao desenhado acumularia o degrau anterior a cada
        chamada, e a letra cresceria sozinha."""
        self.editor.setAcceptRichText(False)
        # O menu do botão direito é o do próprio editor, mais o que a miniatura sabe fazer (item 10).
        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._abrir_menu_de_contexto)
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
            # `EDITOR_VAZIO` continua inteiro, porque ele é a frase de quem não tem título.
            frase=strings.TEXTO_VAZIO_FRASE,
            rotulo_do_botao=comandos.rotulo_de_botao("ler_folha"),
            nome_acessivel="Ler a folha da página aberta",
            acao=self.ler,
        )
        self.editor.textChanged.connect(self._mostrar_vazio)
        self.editor.viewport().installEventFilter(self)
        # O `Ctrl+Z` de dentro da folha. Ver `TECLAS_DO_HISTORICO`.
        self.editor.installEventFilter(self)
        self._teclas_do_historico = _teclas_da_tabela(TECLAS_DO_HISTORICO)
        corpo = QHBoxLayout()
        corpo.addWidget(self.editor, 1)
        corpo.addWidget(self._montar_paleta())
        caixa.addLayout(corpo, 1)

        self.status = QLabel("", self)
        self.status.setAccessibleName("Estado da folha")
        caixa.addWidget(self.status)

    def _atualizar_status(self) -> None:
        """O rodapé da aba, refeito a cada mudança do documento e a cada gravação.

        A frase é de `ui/texto_declarado.frase_do_rodape`; aqui só se contam as miniaturas, que
        são do desenho e não do documento.
        """
        diagramas = self.documento.diagramas
        self.status.setText(
            frase_do_rodape(
                folha=None if self._pagina is None else int(self._pagina.pagina),
                trechos=len(self.documento.corridas),
                diagramas=len(diagramas),
                miniaturas=sum(1 for c in diagramas if self._tem_miniatura(c)),
                por_gravar=self.tem_alteracoes,
            )
        )

    def _montar_paleta(self) -> QListWidget:
        """O painel lateral de glifos (S-248). Nasce escondido: ele é um caminho a mais.

        Uma lista e não uma grade de botões: os glifos são muitos, a lista rola, e clicar num item
        é o mesmo gesto que clicar num botão -- com a diferença de que a lista não precisa de uma
        decisão de quantas colunas.
        """
        from chess_diagram_ocr.text import paleta as _paleta

        self.paleta_lateral = QListWidget(self)
        # **`"Lista"` não nomeia** (F9-C2, defeito nº 1): era o nome genérico da classe, e o
        # portão do `teclado.py` reprova eco do papel. O que esta lista guarda são os símbolos
        # de anotação que se inserem no texto.
        self.paleta_lateral.setAccessibleName("Símbolos de anotação")
        self.paleta_lateral.setFixedWidth(72)
        self.paleta_lateral.hide()
        for simbolo in _paleta.MINIMA:
            self.paleta_lateral.addItem(simbolo)
        self.paleta_lateral.itemClicked.connect(lambda item: self.inserir_simbolo(item.text()))
        return self.paleta_lateral

    def _barra_de_ferramentas(self) -> BarraFluida:
        barra = BarraFluida(self)
        botoes_de_estilo: tuple[tuple[str, Callable[[], object]], ...] = (
            ("negrito", self.negrito),
            ("italico", self.italico),
            ("sublinhado", self.sublinhado),
            ("tachado", self.tachado),
            ("limpar_formato", self.limpar_formato),
        )
        for acao, alvo in botoes_de_estilo:
            self._botao(barra, acao, alvo)

        self.escolha_de_estilo = QComboBox(barra)
        # **As quatro escolhas desta barra não têm rótulo na tela** (F9-C2): elas são compactas
        # de propósito, e o preço era que a cascata de `ui/nomes_acessiveis.py` caía no último
        # degrau e o leitor de tela anunciava `"Escolha"` -- duas delas na mesma barra, sem nada
        # que as distinga. O nome vai aqui, uma vez, ao lado de quem sabe o que a escolha escolhe.
        self.escolha_de_estilo.setAccessibleName("Estilo do parágrafo")
        self.escolha_de_estilo.addItem("(sem estilo)", "")
        for estilo in rico.ESTILOS:
            self.escolha_de_estilo.addItem(estilo.capitalize(), estilo)
        self.escolha_de_estilo.activated.connect(
            lambda _i: self.aplicar_estilo(str(self.escolha_de_estilo.currentData()))
        )
        dica_em(self.escolha_de_estilo, "O estilo do parágrafo inteiro, e não do trecho selecionado.")
        barra.adicionar(self.escolha_de_estilo)

        self.escolha_de_cor = QComboBox(barra)
        self.escolha_de_cor.setAccessibleName("Cor da letra")
        self.escolha_de_cor.addItem("(sem cor)", "")
        for nome in texto_cores.nomes():
            self.escolha_de_cor.addItem(nome.capitalize(), nome)
        self.escolha_de_cor.activated.connect(
            lambda _i: self.pintar_letra(str(self.escolha_de_cor.currentData()))
        )
        barra.adicionar(self.escolha_de_cor)

        self.escolha_de_realce = QComboBox(barra)
        self.escolha_de_realce.setAccessibleName("Cor do realce")
        self.escolha_de_realce.addItem("(sem realce)", "")
        # Os mesmos nomes da cor da letra: o realce é o **canal** do autor, e não uma
        # segunda paleta -- `texto_cores.papel_de_realce` resolve o mesmo nome noutro papel.
        for nome in texto_cores.nomes():
            self.escolha_de_realce.addItem(nome.capitalize(), nome)
        self.escolha_de_realce.activated.connect(
            lambda _i: self.pintar_realce(str(self.escolha_de_realce.currentData()))
        )
        barra.adicionar(self.escolha_de_realce)

        # **A folha, o motor e o modo bloco ficam na mesma barra que o "Ler".** É a linha do gesto:
        # escolher a folha, escolher como lê-la, e ler -- e separá-la em duas faria a escolha do
        # motor parecer configuração, que é o que a S-423 mostrou custar a primeira leitura de quem
        # instala o programa.
        self.campo_de_folha = QSpinBox(barra)
        # O nome diz o que o número é, e não qual número é -- ver `nomes_acessiveis.CLASSES_COM_VALOR`.
        self.campo_de_folha.setAccessibleName("Folha a ler")
        self.campo_de_folha.setMinimum(1)
        self.campo_de_folha.setMaximum(TETO_DE_FOLHAS)  # até a janela dizer quantas folhas o livro tem
        self.campo_de_folha.setValue(self._pagina_indice + 1)
        barra.adicionar(self.campo_de_folha)

        self.escolha_de_motor = QComboBox(barra)
        self.escolha_de_motor.setAccessibleName("Motor de leitura")
        for motor in MOTORES:
            self.escolha_de_motor.addItem(motor, motor)
        self.escolha_de_motor.activated.connect(
            lambda _i: setattr(self, "_motor", str(self.escolha_de_motor.currentData()))
        )
        dica_em(
            self.escolha_de_motor,
            "auto é o glifo com a camada do PDF como reserva. O glifo sozinho precisa de "
            "models/char_classifier.pt, que não vem no repositório.",
        )
        barra.adicionar(self.escolha_de_motor)

        self.caixa_de_bloco = QCheckBox(comandos.rotulo_de_botao("modo_bloco"), barra)
        self.caixa_de_bloco.toggled.connect(lambda _ligado: self.modo_bloco_mudou())
        barra.adicionar(self.caixa_de_bloco)

        alvos: tuple[tuple[str, Callable[[], object]], ...] = (
            ("ler_folha", self.ler),
            ("achar", self.achar),
            ("marcar_fora_do_lexico", self.marcar_fora_do_lexico),
            ("inserir_figurina", self.inserir_figurina),
            ("desfazer", self.desfazer),
            ("refazer", self.refazer),
        )
        for acao, alvo in alvos:
            self._botao(barra, acao, alvo)
        return barra

    def _botao(self, barra: BarraFluida, acao: str, alvo: Callable[[], object]) -> QWidget:
        """Um botão de ferramenta: rótulo e dica do catálogo, tecla da tabela.

        Este arquivo não escreve texto de interface nem sequência de tecla -- é a S-324 e a
        S-165, e vale igual aos dois frontends.
        """
        from PyQt6.QtWidgets import QPushButton

        rotulo = comandos.rotulo_de_botao(acao) if _no_catalogo(acao) else acao.capitalize()
        botao = QPushButton(rotulo, barra)
        # **O nome acessível é o rótulo por extenso, e não o texto do botão** (F9-C2).
        # O crítico do ciclo 1 mediu 28 controles que chegavam ao leitor de tela como "-",
        # "+", "|◀" ou ".md" -- o `rotulo_curto` passando pela cascata de
        # `ui/nomes_acessiveis.py` no passo `text()`. Ver `comandos.Comando.no_leitor`.
        if _no_catalogo(acao):
            botao.setAccessibleName(comandos.nome_acessivel(acao))
        botao.clicked.connect(lambda _marcado=False: alvo())
        tema.aplicar_papel(botao, estilos.NEUTRO)
        motivo = comandos.rotulo(acao) if _no_catalogo(acao) else rotulo
        tecla = atalhos.acelerador(acao)
        dica_em(botao, f"{motivo}\nTecla: {tecla}" if tecla else motivo)
        barra.adicionar(botao)
        return botao

    # ------------------------------------------------------------------------------ desenho

    def desenhar_documento(self, doc: rico.DocumentoRico, *, selecao: tuple[int, int] | None = None) -> None:
        """Troca o documento e o desenha. **Este laço não decide nada.**

        Faixa, ordem, separador e atributo já vieram decididos por `text/rico.py`; o que sobra
        aqui é escrever no cursor e pôr a miniatura. É a mesma fronteira do outro frontend.

        `selecao` é `(âncora, ponta)` em deslocamento do documento novo: onde o cursor fica depois
        do desenho. `None` é folha nova -- o cursor volta ao começo, que é o certo para a leitura
        e para o arquivo aberto, e o errado para o negrito no meio da página.
        """
        self.documento = doc
        self._desenhar(selecao=selecao)
        self.documento_mudou.emit()

    def _desenhar(self, *, selecao: tuple[int, int] | None = None) -> None:
        """Refaz o `QTextDocument` inteiro a partir das corridas -- e devolve o cursor a `selecao`.

        **Devolver o cursor é o que torna o redesenho compatível com a digitação.** O documento
        novo nasce com o cursor no começo e a rolagem no topo; com o texto digitado agora sendo
        documento, um `Ctrl+Z` ou um negrito no meio da folha que jogasse o cursor para o título
        faria a tecla seguinte escrever lá -- e ela passaria a ficar.
        """
        barra = self.editor.verticalScrollBar()
        rolagem = barra.value() if selecao is not None and barra is not None else None
        self._redesenhando = True
        try:
            self._mapa.limpar()
            documento = QTextDocument(self.editor)
            documento.setDefaultFont(self.editor.font())
            # **No documento, e não no editor.** `QTextEdit.setUndoRedoEnabled` vale para o
            # documento em vigor, e `_desenhar` troca o documento -- ajustar só o editor no
            # `_montar` fazia o desfazer nativo voltar a ligar no primeiro redesenho, e aí
            # `Ctrl+Z` teria duas pilhas disputando. Foi um teste que pegou.
            documento.setUndoRedoEnabled(False)
            cursor = QTextCursor(documento)
            base = self._base_da_vista()
            self._base = base
            deslocamento = 0

            for corrida in self.documento.corridas:
                if corrida.e_diagrama:
                    self._inserir_miniatura(cursor, corrida)
                cursor.setBlockFormat(bloco_de(corrida.atributos, base=base))
                inicio = cursor.position()
                cursor.insertText(corrida.texto, formato_de(corrida, base=base))
                self._mapa.registrar(deslocamento, inicio, len(corrida.texto))
                deslocamento += len(corrida.texto)

            # O `setDocument` só apaga o documento que é filho do controle interno do editor -- o da
            # montagem, e na hora --, e os deste painel são filhos do editor: sem soltá-los, cada
            # redesenho deixava a folha anterior inteira, com as miniaturas, pendurada até a janela
            # fechar. Quem é de quem se pergunta **antes** da troca, porque depois dela o da
            # montagem já não existe; e `deleteLater`, e não já, porque o redesenho pode estar
            # acontecendo de dentro de um sinal do documento que sai (`_trocado`).
            anterior = self.editor.document()
            nosso = anterior if anterior is not None and anterior.parent() is self.editor else None
            self.editor.setDocument(documento)
            if nosso is not None:
                nosso.deleteLater()
            # Ligado **depois** de montar: o que o laço acima escreveu é desenho, e não digitação.
            documento.contentsChange.connect(self._digitado)
            self._tela = _texto_da_tela(documento)
        finally:
            self._redesenhando = False
        if selecao is not None:
            self._devolver_selecao(selecao, rolagem)
        # A marcação do léxico não é do documento e morre com o `QTextDocument` que saiu: com a
        # conferência ligada, ela se refaz sobre a folha nova (S-293).
        if self._conferindo_lexico:
            self._conferir_lexico(avisar=False)

    def _base_da_vista(self) -> tuple[int, str, str]:
        """A fonte de base **com o zoom da vista** (S-264).

        O zoom é um degrau somado ao corpo do sistema, e é aqui que ele entra na folha: toda
        corrida é desenhada por `formato_de` a partir desta base, então aplicá-lo só à fonte do
        editor -- como o porte fazia -- não mudava letra nenhuma, porque cada trecho sai com o seu
        corpo explícito. O degrau parte sempre da origem, nunca do que está na tela.
        """
        from chess_diagram_ocr.ui import tipografia

        tamanho, proporcional, monoespacada = tema.fonte_base()
        return tipografia.corpo(self._zoom_da_vista, base=tamanho), proporcional, monoespacada

    def _selecao_atual(self) -> tuple[int, int]:
        """`(âncora, ponta)` do cursor, em deslocamento do documento."""
        cursor = self.editor.textCursor()
        return (self._mapa.deslocamento(cursor.anchor()), self._mapa.deslocamento(cursor.position()))

    def _devolver_selecao(self, selecao: tuple[int, int], rolagem: int | None) -> None:
        """Põe o cursor em `selecao` e a rolagem onde estava; o cursor fora da tela a traz até ele."""
        ancora, ponta = selecao
        cursor = self.editor.textCursor()
        cursor.setPosition(self._mapa.posicao(ancora))
        cursor.setPosition(self._mapa.posicao(ponta), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        barra = self.editor.verticalScrollBar()
        if rolagem is not None and barra is not None:
            barra.setValue(rolagem)
        self.editor.ensureCursorVisible()

    def _inserir_miniatura(self, cursor: QTextCursor, corrida: rico.Corrida) -> None:
        """A imagem do diagrama, **antes** da marca -- e a marca continua no texto.

        Parece redundante numa tela onde a imagem já aparece, e é o contrário: a imagem é do
        widget e morre com ele, a marca é do texto e sobrevive a salvar, copiar e colar. Um
        editor que trocasse a marca pela imagem perderia o diagrama na primeira exportação.

        A imagem **não** entra no mapa: ela não é do documento, e é justamente por isso que
        `_Mapa` existe.
        """
        figura = self._imagem_do_diagrama(corrida)
        if figura is None:
            return
        mapa = figura.scaledToWidth(self._largura_da_miniatura(), Qt.TransformationMode.SmoothTransformation)
        nome = f"diagrama:{corrida.bloco}"
        documento = cursor.document()
        if documento is not None:
            documento.addResource(QTextDocument.ResourceType.ImageResource.value, _url(nome), mapa)
        # Com a medida escrita no formato, e não só no pixmap: é o que o Qt usa para o leiaute, e é
        # o que um teste consegue ler de volta sem desenhar a tela.
        imagem = QTextImageFormat()
        imagem.setName(nome)
        imagem.setWidth(mapa.width())
        imagem.setHeight(mapa.height())
        # O texto alternativo (item 14): é o que o leitor de tela diz no lugar da figura, e o que
        # o `toHtml` escreve no `alt`. A marca vem logo abaixo, mas a marca é texto do documento, e
        # a figura precisa dizer por si o que é.
        numero = int(getattr(self.documento.bloco_de(corrida), "indice", corrida.bloco)) + 1
        folha = "" if self._pagina is None else f" da folha {int(self._pagina.pagina) + 1}"
        imagem.setProperty(QTextFormat.Property.ImageAltText, f"Diagrama {numero}")
        imagem.setProperty(QTextFormat.Property.ImageTitle, f"Diagrama {numero}{folha}")
        cursor.insertImage(imagem)
        cursor.insertBlock()

    def _imagem_do_diagrama(self, corrida: rico.Corrida) -> QPixmap | None:
        """A figura da miniatura: **o recorte da folha, ou o desenho da posição lida**.

        O recorte é a verdade impressa e vem primeiro. Sem folha -- o `.cvtxt` aberto com o livro
        fora do lugar, ou noutra máquina -- a miniatura nascia vazia mesmo quando o OCR de
        diagramas do produto já tinha lido a posição (item 6). Aí ela é desenhada da FEN, com as
        peças que o próprio programa desenha (`desenho_de_diagrama`), e a pessoa vê o diagrama em
        vez de uma marca solta. É desenho e não leitura: quem corrige a posição corrige na aba Livro.
        """
        recorte = self._recorte(corrida)
        if recorte is not None:
            return pixmap_de_rgb(recorte)
        png = _png_da_posicao(_posicao_de(self.documento, corrida), lado_px=self._largura_da_miniatura())
        if png is None:
            return None
        mapa = QPixmap()
        return mapa if mapa.loadFromData(png, "PNG") and not mapa.isNull() else None

    def _tem_miniatura(self, corrida: rico.Corrida) -> bool:
        """Há figura para esta marca -- recorte da folha ou posição lida -- sem desenhá-la."""
        return self._recorte(corrida) is not None or bool(_posicao_de(self.documento, corrida))

    def _largura_da_miniatura(self) -> int:
        """A miniatura **acompanha o zoom da vista** (S-264): a mesma razão que a letra.

        `LARGURA_DA_MINIATURA` é a largura no corpo do sistema; com a vista em +3 degraus sobre
        um corpo de 9 pt a miniatura cresce um terço, e com a vista em -2 ela encolhe. Sem isto,
        aproximar a folha deixava a letra do tamanho que a pessoa pediu e o diagrama do tamanho de
        antes -- cada vez menor em relação ao texto que fala dele.
        """
        corpo_do_sistema = max(1, tema.fonte_base()[0])
        corpo_da_vista = self._base[0] if self._base is not None else corpo_do_sistema
        return max(48, round(LARGURA_DA_MINIATURA * corpo_da_vista / corpo_do_sistema))

    def _recorte(self, corrida: rico.Corrida) -> np.ndarray | None:
        """O pedaço da folha em que o diagrama está, ou `None` sem folha renderizada.

        **O bbox do bloco está em pontos e a folha em pixels**, e o fator entre os dois é o DPI
        com que ela foi renderizada -- é por isso que ele é o mesmo `self._dpi` dos dois lados.
        Usar outro aqui recortaria o lugar errado da folha em silêncio.

        Sem imagem a marca continua no texto e o editor abre igual: é o mesmo contrato de
        `texto_panel._inserir_miniatura`, e é o que faz a aba funcionar num checkout sem PDF.
        """
        if self._pagina_rgb is None:
            return None
        return _recorte_da_folha(self._pagina_rgb, self.documento.bloco_de(corrida), dpi=self._dpi)

    # -------------------------------------------------------------------------- ferramentas

    def _intervalo(self) -> tuple[int, int]:
        """O intervalo selecionado, **em deslocamento de documento**.

        Sem seleção os dois são iguais, e as funções de `rico` tratam isso como "a palavra sob o
        cursor" -- é `rico.intervalo_alvo`, e a decisão é de lá.
        """
        cursor = self.editor.textCursor()
        return (
            self._mapa.deslocamento(cursor.selectionStart()),
            self._mapa.deslocamento(cursor.selectionEnd()),
        )

    def _aplicar(self, novo: rico.DocumentoRico, *, selecao: tuple[int, int] | None = None) -> None:
        """Guarda o documento anterior na pilha e desenha o novo.

        A pilha é de **documentos**, e é o que faz `Ctrl+Z` desfazer um negrito -- que não muda
        caractere nenhum e que uma pilha de texto não veria.

        **Toda ferramenta fecha o passo da digitação**: `Ctrl+Z` depois de "digitar, negritar,
        digitar" desfaz a segunda digitação, e não as duas com o negrito no meio. A seleção fica
        onde estava (ou em `selecao`), para o segundo pincel cair no mesmo trecho que o primeiro.
        """
        self._digitacao = None
        if novo is self.documento:
            return
        selecao = self._selecao_atual() if selecao is None else selecao
        self._historico.append(self.documento)
        # O contador que decide o `Ctrl+Z` quando o foco não está em desfazível nenhum (S-243).
        self._edicao += 1
        self._refeitos.clear()
        self.desenhar_documento(novo, selecao=selecao)

    def alternar(self, atributo: str) -> None:
        """Liga o atributo no intervalo -- ou desliga, se ele já vale em todo ele (S-241)."""
        inicio, fim = self._intervalo()
        self._aplicar(rico.alternar(self.documento, inicio, fim, atributo))

    def negrito(self) -> None:
        self.alternar("negrito")

    def italico(self) -> None:
        self.alternar("italico")

    def sublinhado(self) -> None:
        self.alternar("sublinhado")

    def tachado(self) -> None:
        self.alternar("tachado")

    def limpar_formato(self) -> None:
        """Tira negrito, itálico e sublinhado. **Não** toca em cor nem em estilo (S-242)."""
        inicio, fim = self._intervalo()
        self._aplicar(rico.limpar_formato(self.documento, inicio, fim))

    def pintar_letra(self, nome: str) -> None:
        """A cor do autor. `""` limpa -- e limpar cor **não** toca a faixa de confiança (S-242)."""
        inicio, fim = self._intervalo()
        if not nome:
            self._aplicar(rico.limpar_cor(self.documento, inicio, fim))
            return
        self._aplicar(rico.aplicar(self.documento, inicio, fim, cor=nome))

    def pintar_realce(self, nome: str) -> None:
        inicio, fim = self._intervalo()
        self._aplicar(rico.aplicar(self.documento, inicio, fim, realce=nome))

    def aplicar_estilo(self, estilo: str) -> None:
        """O estilo do **parágrafo** que o intervalo toca (S-249).

        O alcance passa do que foi selecionado de propósito: o parágrafo é o conjunto de corridas
        do mesmo bloco, e marcar meia frase deixaria dois corpos de fonte na mesma linha.
        """
        inicio, fim = self._intervalo()
        self._aplicar(rico.aplicar_estilo(self.documento, inicio, fim, estilo))

    def alinhar(self, alinhamento: str) -> None:
        inicio, fim = self._intervalo()
        self._aplicar(rico.aplicar_alinhamento(self.documento, inicio, fim, alinhamento))

    def mudar_corpo(self, degrau: int) -> None:
        """Aumenta ou diminui o corpo do parágrafo, em degraus (S-260).

        **O degrau é somado ao que o documento guarda, e não ao que está na tela.** Somar ao
        tamanho desenhado acumularia o degrau anterior a cada redesenho, e a fonte cresceria
        sozinha -- é a razão que `texto_formato._fonte` documenta do outro lado.
        """
        inicio, fim = self._intervalo()
        atual = self._corpo_em(inicio)
        self._aplicar(
            rico.aplicar_no_paragrafo(self.documento, inicio, fim, corpo=rico.corpo_no_limite(atual + degrau))
        )

    def _corpo_em(self, deslocamento: int) -> int:
        percorrido = 0
        for corrida in self.documento.corridas:
            if percorrido <= deslocamento < percorrido + len(corrida.texto):
                return corrida.atributos.corpo
            percorrido += len(corrida.texto)
        return 0

    # ---------------------------------------------------------------------------- histórico

    def contem(self, widget: object) -> bool:
        """Este widget está dentro desta aba? É o que decide de quem é o `Ctrl+Z` (S-243)."""
        return qt_atalhos.contem(self, widget)

    @property
    def edicao(self) -> int:
        """Contador que só cresce, como manda `ui/desfazivel.Desfazivel`. Zero = nunca editado."""
        return self._edicao

    def desfazer(self) -> None:
        """`Ctrl+Z`: devolve o documento anterior -- a palavra digitada inteira é **um** passo."""
        if not self._historico:
            self.estado.emit("Não há mudança anterior nesta folha para desfazer.")
            return
        self._digitacao = None
        self._refeitos.append(self.documento)
        self._voltar_a(self._historico.pop())

    def refazer(self) -> None:
        """`Ctrl+Y`: repõe o que o desfazer tirou."""
        if not self._refeitos:
            self.estado.emit("Não há o que refazer: nada foi desfeito.")
            return
        self._digitacao = None
        self._historico.append(self.documento)
        self._voltar_a(self._refeitos.pop())

    def _voltar_a(self, doc: rico.DocumentoRico) -> None:
        """Desenha `doc` com o cursor **onde o texto mudou** -- o fim do trecho que voltou ou saiu.

        É onde qualquer editor põe o cursor depois de desfazer, e é onde a pessoa vai continuar
        escrevendo. Se o texto não mudou (desfazer um negrito), a seleção fica onde estava.
        """
        troca = _janela_da_troca(self.documento.para_texto(), doc.para_texto())
        if troca is None:
            self.desenhar_documento(doc, selecao=self._selecao_atual())
            return
        alvo = troca[0] + troca[2]
        self.desenhar_documento(doc, selecao=(alvo, alvo))

    @property
    def pode_desfazer(self) -> bool:
        return bool(self._historico)

    @property
    def pode_refazer(self) -> bool:
        return bool(self._refeitos)

    # -------------------------------------------------------------------------------- carga

    def mostrar_pagina(
        self, pagina: PaginaLida, *, folha_rgb: np.ndarray | None = None, dpi: int | None = None
    ) -> None:
        """Abre uma `PaginaLida` no editor. É o que a leitura entrega -- e é o ponto de partida
        contra o qual `tem_alteracoes` compara: a folha recém-lida não tem nada por gravar.

        `dpi` é o da `folha_rgb`, quando ela vem: é o que liga os pontos do `bbox` aos pixels dela.
        """
        guardadas = self._posicoes.get((_chave_de_livro(pagina.documento), int(pagina.pagina)))
        if guardadas:
            pagina = pagina.com_posicoes(guardadas)
        self._pagina = pagina
        self._pagina_rgb = folha_rgb
        if dpi:
            self._dpi = int(dpi)
        self._historico.clear()
        self._refeitos.clear()
        self._digitacao = None
        self.desenhar_documento(rico.de_pagina(pagina))
        self._documento_gravado = self.documento
        self._rascunho.stop()  # o desenho emitiu `documento_mudou`; a folha recém-lida não tem o que gravar
        self._atualizar_status()

    def texto(self) -> str:
        """O texto puro do documento -- **do documento, e não do widget**.

        O widget tem a miniatura e a quebra do desenho; o documento não. É a mesma distinção que
        `_Mapa` mantém, do lado da exportação.
        """
        return self.documento.para_texto()


    # ------------------------------------------------------- estilo, alinhamento e corpo

    def estilo_titulo(self) -> None:
        self.aplicar_estilo(rico.ESTILO_TITULO)

    def estilo_prosa(self) -> None:
        self.aplicar_estilo(rico.ESTILO_PROSA)

    def estilo_notacao(self) -> None:
        self.aplicar_estilo(rico.ESTILO_NOTACAO)

    def estilo_legenda(self) -> None:
        self.aplicar_estilo(rico.ESTILO_LEGENDA)

    def alinhar_esquerda(self) -> None:
        self.alinhar(rico.ALINHAMENTO_ESQUERDA)

    def alinhar_centro(self) -> None:
        self.alinhar(rico.ALINHAMENTO_CENTRO)

    def alinhar_direita(self) -> None:
        self.alinhar(rico.ALINHAMENTO_DIREITA)

    def justificar(self) -> None:
        self.alinhar(rico.ALINHAMENTO_JUSTIFICADO)

    def aumentar_corpo(self) -> None:
        self.mudar_corpo(+1)

    def diminuir_corpo(self) -> None:
        self.mudar_corpo(-1)

    def corpo_normal(self) -> None:
        """Volta o parágrafo ao corpo do estilo dele -- degrau zero, e não "sem corpo"."""
        inicio, fim = self._intervalo()
        self._aplicar(rico.aplicar_no_paragrafo(self.documento, inicio, fim, corpo=0))

    def limpar_cor(self) -> None:
        """Tira a cor do autor. **Não** toca a faixa de confiança (S-242)."""
        self.pintar_letra("")

    def escolher_cor(self) -> None:
        """Abre a lista de cores da barra. O comando é a porta de menu do mesmo gesto."""
        self.escolha_de_cor.showPopup()

    def escolher_realce(self) -> None:
        """O mesmo para o realce. Sem lista na barra, o comando pinta com o primeiro papel."""
        self.escolha_de_realce.showPopup()

    # ------------------------------------------------------------------------- a caixa (S-262)

    def mudar_caixa(self, caixa: str) -> None:
        """MAIÚSCULAS, minúsculas ou Iniciais no alvo.

        **Muda o texto**, e por isso passa pela mesma pilha das outras ferramentas: o documento
        anterior é guardado antes do redesenho. Sem isso, desfazer uma troca de caixa sobre um
        parágrafo seria impossível.
        """
        inicio, fim = self._intervalo()
        self._aplicar(rico.mudar_caixa(self.documento, inicio, fim, caixa))

    def maiusculas(self) -> None:
        self.mudar_caixa(rico.CAIXA_ALTA)

    def minusculas(self) -> None:
        self.mudar_caixa(rico.CAIXA_BAIXA)

    def capitular(self) -> None:
        self.mudar_caixa(rico.CAIXA_INICIAIS)


    # ------------------------------------------------- a área de transferência (S-263)

    def selecionar_tudo(self) -> None:
        """Seleciona o texto inteiro da folha.

        **É uma correção, e não um acréscimo**: no `tk.Text` de fábrica `Ctrl+A` leva o cursor ao
        início da linha, e selecionar tudo não tinha tecla nem comando. O `QTextEdit` já faz o
        certo; o comando existe para ele ter menu, paleta e tecla como os outros quarenta e sete.
        """
        self.editor.selectAll()
        self.editor.setFocus()

    def recortar(self) -> None:
        self.editor.cut()

    def copiar(self) -> None:
        self.editor.copy()

    def colar(self) -> None:
        """Cola no cursor. **O texto colado herda os atributos dos dois lados**, como o digitado.

        O que **não** vem junto é formatação de outro programa: `setAcceptRichText(False)` recusa
        HTML colado, e o que entra é texto -- que é o mesmo contrato do outro frontend, onde a
        área de transferência do Tk carrega texto e não corridas.
        """
        self.editor.paste()

    @property
    def quebra(self) -> bool:
        """As linhas estão quebrando na largura da janela? É o que o estado guarda (S-291)."""
        return self.editor.lineWrapMode() != QTextEdit.LineWrapMode.NoWrap

    def definir_quebra(self, quebrando: bool, *, avisar: bool = False) -> None:
        """Põe a quebra naquele estado. Silencioso por padrão.

        **Separada de `quebrar_linha` porque restaurar não é alternar.** A restauração da abertura
        põe o que a sessão anterior tinha, e uma frase no rodapé anunciando isso seria um recado
        sobre algo que a pessoa não acabou de fazer -- é a mesma razão do `avisar=False` de
        `aplicar_zoom`.
        """
        self.editor.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth if quebrando else QTextEdit.LineWrapMode.NoWrap
        )
        if not avisar:
            return
        if quebrando:
            self.estado.emit("As linhas voltam a quebrar na largura da janela.")
        else:
            self.estado.emit("Linha inteira: use a rolagem de baixo para ver o fim das linhas longas.")

    def quebrar_linha(self) -> None:
        """Liga ou desliga a quebra na largura da janela (S-265)."""
        self.definir_quebra(not self.quebra, avisar=True)

    # ------------------------------------------------------------- o zoom da vista (S-264)

    @property
    def zoom_da_vista(self) -> int:
        return self._zoom_da_vista

    def aproximar_texto(self) -> None:
        """Aumenta a letra **na tela**. Não muda o documento, não é gravado, não é exportado."""
        self._mudar_zoom(+1)

    def afastar_texto(self) -> None:
        self._mudar_zoom(-1)

    def zoom_do_texto_normal(self) -> None:
        """Volta a folha ao tamanho de tela normal."""
        self.aplicar_zoom(0)

    def _mudar_zoom(self, passo: int) -> None:
        alvo = max(ZOOM_MINIMO, min(ZOOM_MAXIMO, self._zoom_da_vista + passo))
        if alvo == self._zoom_da_vista:
            limite = ZOOM_MAXIMO if passo > 0 else ZOOM_MINIMO
            self.estado.emit(f"O zoom do texto já está no limite ({limite:+d} degraus).")
            return
        self.aplicar_zoom(alvo)

    def aplicar_zoom(self, degraus: int, *, avisar: bool = True) -> None:
        """Troca a fonte de base do editor e redesenha.

        **Aqui o redesenho é barato, e é a diferença de fundo com o outro frontend.** Lá redesenhar
        zera a pilha de desfazer do Tk -- ela guarda índice, não conteúdo --, e por isso o zoom tem
        de refazer cada etiqueta de fonte à mão, com o cache de atributos de origem que a S-336
        conserta. Aqui a pilha é de documentos e sobrevive ao redesenho, então o zoom é uma fonte
        nova e um `_desenhar`.

        **Grampeia aqui** (S-291): os limites são desta aba, e validá-los no arquivo de estado os
        declararia num segundo lugar.
        """
        from chess_diagram_ocr.ui import tipografia

        degraus = max(ZOOM_MINIMO, min(ZOOM_MAXIMO, int(degraus)))
        self._zoom_da_vista = degraus
        selecao = self._selecao_atual()
        fonte = self.editor.font()
        fonte.setPointSize(tipografia.corpo(degraus, base=self._corpo_de_base))
        self.editor.setFont(fonte)
        self._desenhar(selecao=selecao)
        if avisar:
            self.estado.emit(f"Zoom do texto: {degraus:+d} degrau(s).")


    # --------------------------------------------------- busca e substituição (S-343)

    def achar(self) -> JanelaDeBusca:
        """Abre a janela de busca. Uma por vez -- reabrir traz a que já está aberta."""
        return self._abrir_busca(substituindo=False)

    def substituir(self) -> JanelaDeBusca:
        """Abre a mesma janela, já com o campo de substituição à mostra."""
        return self._abrir_busca(substituindo=True)

    def _abrir_busca(self, *, substituindo: bool) -> JanelaDeBusca:
        janela = self._janela_de_busca
        if isinstance(janela, JanelaDeBusca) and not janela.isHidden():
            janela.mostrar(substituindo=substituindo)
            return janela
        janela = JanelaDeBusca(self, substituindo=substituindo)
        self._janela_de_busca = janela
        return janela

    def mostrar_intervalo(self, inicio: int, fim: int) -> None:
        """Rola até aquele trecho e o seleciona. É o que a lista da busca chama ao clicar."""
        cursor = self.editor.textCursor()
        cursor.setPosition(self._mapa.posicao(inicio))
        cursor.setPosition(self._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self.editor.setFocus()

    def aplicar_substituicao(self, ocorrencias: Sequence[busca.Ocorrencia], novo: str) -> int:
        """Troca as ocorrências escolhidas e redesenha. Devolve quantas trocou.

        O documento anterior vai para a pilha **antes** do redesenho: é o que faz `desfazer`
        reverter a substituição **inteira**, e não troca a troca.
        """
        novo_doc = busca.substituir(self.documento, ocorrencias, novo)
        if novo_doc.para_texto() == self.documento.para_texto():
            return 0
        self._aplicar(novo_doc)
        return len(ocorrencias)

    # ----------------------------------------------------- a conferência do léxico (S-266)

    def marcar_fora_do_lexico(self) -> None:
        """Liga a conferência do léxico da S-209. **Não corrige nada** (S-266).

        A frase da S-209 é a especificação inteira deste comando: *"palavra fora do dicionário é
        sinalizada, nunca aproximada da mais parecida"*. Dos 18 lances tão maltratados que caem no
        léxico, nenhum está no dicionário -- com correção automática seriam 18 lances reescritos
        como palavra.

        **Ligar, e não marcar uma vez** (S-293): toda ferramenta que muda texto redesenha, e o
        redesenho apaga a marcação -- então corrigir a primeira palavra marcada apagava as outras.
        """
        self._conferindo_lexico = True
        self._conferir_lexico(avisar=True)

    def limpar_marcas_do_lexico(self) -> None:
        """Desliga a conferência e tira as marcas. **Não é desfazer**: elas nunca foram documento."""
        self._conferindo_lexico = False
        self._pintar_lexico(())

    def _conferir_lexico(self, *, avisar: bool) -> None:
        """Refaz a marcação. `avisar=False` no redesenho: a conta já foi dita quando se ligou.

        Um rodapé reescrito a cada tecla seria ruído -- e pior, esconderia o que a ferramenta que
        acabou de rodar tinha a dizer.
        """
        from chess_diagram_ocr.text import dicionario

        conteudo = self.documento.para_texto()
        try:
            lexico = dicionario.carregar()
        except OSError as erro:
            logger.debug("Léxico não carregou: %s", erro)
            self.estado.emit(f"O léxico não pôde ser carregado: {erro}")
            return
        achadas = dicionario.desconhecidas(conteudo, lexico, ignorar=fora_do_livro(self.documento))
        self._pintar_lexico([(inicio, fim) for inicio, fim, _palavra in achadas])
        if avisar:
            total = len(dicionario.palavras_de(conteudo))
            self.estado.emit(
                f"{len(achadas)} de {total} palavra(s) fora do léxico. Nada foi corrigido (S-209)."
            )

    def _pintar_lexico(self, intervalos: Iterable[tuple[int, int]]) -> None:
        """A marca é uma **borda ondulada**, e o canal estava livre (S-266).

        A cor da letra é a faixa de confiança, o fundo é o realce do autor, a fonte é o estilo mais
        o corpo, e negrito/itálico/sublinhado/tachado são os quatro pincéis de ênfase. Uma quinta
        marca em qualquer um deles seria a mesma tinta com dois significados na mesma linha.

        **`setExtraSelections` e não formato de caractere**: a marcação não é do documento, e
        escrevê-la no `QTextCharFormat` a faria voltar de `toHtml` e atravessar a gravação.
        """
        from PyQt6.QtGui import QColor, QTextCharFormat

        seletores: list[QTextEdit.ExtraSelection] = []
        for inicio, fim in intervalos:
            selecao = QTextEdit.ExtraSelection()
            formato = QTextCharFormat()
            formato.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            formato.setUnderlineColor(QColor(tema.cor_atual(tokens.PROBLEMA_TEXTO)))
            selecao.format = formato
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(self._mapa.posicao(inicio))
            cursor.setPosition(self._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
            selecao.cursor = cursor
            seletores.append(selecao)
        self.editor.setExtraSelections(seletores)


    # --------------------------------------------------- os símbolos e a paleta (S-248)

    def _paleta_de_glifos(self) -> object:
        """A paleta, carregada uma vez. Ela lê o metadado do modelo, e isso custa disco."""
        if self._paleta is None:
            from chess_diagram_ocr.text import paleta as _paleta

            self._paleta = _paleta.paleta()
        return self._paleta

    def inserir_simbolo(self, simbolo: str) -> None:
        """Insere o glifo no cursor, **marcando a corrida** se o modelo não o lê (S-247).

        A marca é `fora_do_modelo`, e ela viaja com o documento: sobrevive a salvar, reabrir e
        exportar, e é o que diz a quem receber o arquivo que aquele caractere não veio da página.

        Passa pela pilha, como toda mudança de texto: `rico.inserir` herda os atributos de quem
        está à esquerda -- quem põe uma figurina no meio de um lance em negrito quer a figurina em
        negrito --, e `fora_do_modelo` entra por cima, porque é declaração sobre o que foi
        inserido e não sobre o que estava lá.
        """
        if not simbolo:
            return
        inicio, _fim = self._intervalo()
        fora = bool(self._paleta_de_glifos().marca(simbolo))  # type: ignore[attr-defined]
        depois = inicio + len(simbolo)
        self._aplicar(rico.inserir(self.documento, inicio, simbolo, fora_do_modelo=fora), selecao=(depois, depois))
        self.editor.setFocus()

    def _menu_de_simbolos(self, simbolos: tuple[str, ...]) -> QMenu:
        """A lista junto do ponteiro. **Marca o que o modelo não lê**, e é o item.

        Um glifo que o classificador não conhece continua sendo inserível -- ele vai para o
        `.cvtxt` e para a exportação --, mas quem o insere precisa saber que a folha lida nunca vai
        trazê-lo de volta. A marca é do `text/paleta.py`, e não escrita aqui.
        """
        from PyQt6.QtGui import QAction, QCursor
        from PyQt6.QtWidgets import QMenu

        paleta_atual = self._paleta_de_glifos()
        menu = QMenu(self)
        for simbolo in simbolos:
            rotulo = f"{simbolo}  ·  fora do modelo" if paleta_atual.marca(simbolo) else simbolo  # type: ignore[attr-defined]
            acao = QAction(rotulo, menu)
            acao.triggered.connect(lambda _marcado=False, glifo=simbolo: self.inserir_simbolo(glifo))
            menu.addAction(acao)
        menu.popup(QCursor.pos())
        return menu

    def inserir_figurina(self) -> QMenu:
        """Abre a lista de figurinas junto do ponteiro -- a porta de menu do mesmo gesto (S-248)."""
        from chess_diagram_ocr.text import paleta as _paleta

        return self._menu_de_simbolos(_paleta.figurinas(self._paleta_de_glifos()))  # type: ignore[arg-type]

    def inserir_avaliacao(self) -> QMenu:
        """O mesmo para os símbolos de avaliação."""
        from chess_diagram_ocr.text import paleta as _paleta

        return self._menu_de_simbolos(_paleta.avaliacoes(self._paleta_de_glifos()))  # type: ignore[arg-type]

    def alternar_paleta(self) -> None:
        """Abre ou fecha o painel lateral de glifos. **O foco não sai do texto** (S-248)."""
        if self.paleta_lateral.isVisible():
            self.paleta_lateral.hide()
        else:
            self.paleta_lateral.show()
        self.editor.setFocus()

    # ------------------------------------------------------------- o arquivo (S-343)

    def abrir_documento(self) -> None:
        """Abre um `.cvtxt` gravado antes, com os diagramas de volta se o livro ainda estiver lá."""
        from chess_diagram_ocr.text import arquivo

        if not self._confirmar_descarte("Abrir outro arquivo descarta as alterações."):
            return
        origem, _filtro = QFileDialog.getOpenFileName(
            self, "Abrir texto de folha", "", f"{arquivo.NOME_DO_FORMATO} (*{arquivo.EXTENSAO});;Todos (*.*)"
        )
        if not origem:
            return
        try:
            doc = arquivo.carregar(Path(origem))
        except (arquivo.ArquivoInvalido, OSError) as erro:
            logger.debug("Documento não abriu (%s): %s", origem, erro)
            QMessageBox.critical(self, "Texto", str(erro))
            return
        self.abrir(doc)
        self._caminho_do_documento = Path(origem)  # `Salvar` grava de volta aqui (S-343)

    def abrir(self, doc: rico.DocumentoRico, *, folha_rgb: np.ndarray | None = None) -> None:
        """Põe o documento na tela e recupera o que só o PDF pode dar: as miniaturas (S-238).

        **O PDF ausente não é erro.** O texto abre igual, as miniaturas faltam, e o rodapé diz
        qual livro não foi encontrado -- a regra de degradação de `ui/theme.py`. O contrário faria
        uma pasta de trabalho movida de lugar bloquear o acesso ao que se corrigiu nela.

        `folha_rgb` é a folha já renderizada, quando quem chama a tem -- o rascunho recuperado é
        da folha que acabou de ser lida, e renderizá-la de novo seria pagar duas vezes.
        """
        from chess_diagram_ocr.text import arquivo

        self._pagina = doc.origem
        self._pagina_rgb = folha_rgb
        self._historico.clear()
        self._refeitos.clear()
        self._digitacao = None
        # Documento novo na tela, arquivo de destino zerado: gravar aqui é a **primeira** vez
        # deste documento, e "Salvar" volta a perguntar onde (S-343). Quem abriu de um arquivo
        # repõe o caminho logo depois, em `abrir_documento`.
        self._caminho_do_documento = None
        aviso = ""
        caminho = arquivo.pdf_de(doc)
        if folha_rgb is None and caminho is not None and doc.origem is not None:
            if caminho.exists():
                self._dpi = self._dpi_para_ler()
                self._pagina_rgb = _renderizar(caminho, doc.origem.pagina, dpi=self._dpi)
            else:
                aviso = f" · o livro {caminho.name} não está no lugar de antes: sem miniaturas"
        if doc.origem is not None:
            self._pagina_indice = int(doc.origem.pagina)
            self.campo_de_folha.setValue(self._pagina_indice + 1)
        self.desenhar_documento(doc)
        self._documento_gravado = self.documento
        self._rascunho.stop()  # como em `mostrar_pagina`: o que veio do disco não tem o que gravar
        self._atualizar_status()
        # O texto da folha 14 na tela com o visualizador na folha 3 é o que fazia a pessoa
        # procurar a página à mão (item 9). Só para o livro que está aberto: um `.cvtxt` de outro
        # livro não troca o livro de ninguém -- é a mesma regra de `definir_livro`.
        if doc.origem is not None and caminho is not None and self._pdf is not None and _mesmo_livro(caminho, self._pdf):
            self.folha_pedida.emit(self._pagina_indice)
        diagramas = len(self.documento.diagramas)
        figuras = sum(1 for c in self.documento.diagramas if self._tem_miniatura(c))
        resumo = f"Texto aberto: {len(self.documento.corridas)} trecho(s), {diagramas} diagrama(s)"
        if diagramas and not aviso:
            resumo += f" ({figuras} com miniatura)"
        self.estado.emit(resumo + aviso + ".")

    def salvar_documento(self) -> None:
        """Grava o `.cvtxt` **no arquivo já escolhido**, e só pergunta na primeira vez (S-343).

        **"Salvar" e "Salvar como…" eram o mesmo comando**, e os dois perguntavam o destino: o
        catálogo mostrava dois rótulos, o menu dois itens e a paleta duas linhas para uma coisa só.
        Num ciclo de correção, em que se grava a cada trecho conferido, o diálogo repetido é o
        atrito -- e o rótulo "como…" prometia uma escolha que o outro tomava do mesmo jeito.
        """
        self._salvar_documento_em(self._caminho_do_documento)

    def salvar_documento_como(self) -> None:
        """Pergunta o destino e passa a gravar nele."""
        self._salvar_documento_em(None)

    def _salvar_documento_em(self, caminho: Path | None) -> None:
        from chess_diagram_ocr.text import arquivo

        if not self.documento.para_texto().strip():
            # Rodapé e não caixa, como a exportação: é um passo que falta, não uma escolha. O Tk
            # já recusava; o porte gravava um `.cvtxt` vazio e dizia «Texto gravado» (item 19).
            self.estado.emit("Não há texto nesta aba para salvar: leia uma folha ou abra um arquivo.")
            return
        if caminho is None:
            escolhido, _filtro = QFileDialog.getSaveFileName(
                self,
                "Salvar o texto da folha",
                arquivo.sugestao_de_nome(self.documento),
                f"{arquivo.NOME_DO_FORMATO} (*{arquivo.EXTENSAO});;Todos (*.*)",
            )
            if not escolhido:
                return
            caminho = Path(escolhido)
        # **A marcação é aplicada aqui, e não só no arquivo** (S-239): o que se grava é o que fica
        # na tela. Ela é derivada da `PaginaLida`, é idempotente, e não toca no que o motor leu --
        # e o que a mão corrigiu deixa de ser pintado como palpite do motor.
        gravado = correcao.com_procedencia_humana(self.documento)
        try:
            arquivo.gravar(caminho, gravado)
        except OSError as erro:
            QMessageBox.critical(self, "Texto", f"Não foi possível gravar:\n{erro}")
            return
        if gravado is not self.documento:
            # Sem passar pela pilha: a procedência não é edição de ninguém, e um `Ctrl+Z` que a
            # tirasse devolveria a tinta de "revisar" a um trecho já conferido e gravado.
            self._digitacao = None
            self.documento = gravado
            self._desenhar(selecao=self._selecao_atual())
        self._documento_gravado = gravado
        self._caminho_do_documento = caminho
        # O trabalho chegou a um lugar melhor: o rascunho da S-255 sai.
        self._rascunho.stop()
        if self._pagina is not None:
            rascunho.descartar(self._pagina.documento, self._pagina.pagina, pasta=self._pasta_de_rascunhos)
        # A conta aparece porque a correção é o que o `.cvtxt` tem de mais caro -- e porque um
        # número no rodapé é o que faz alguém notar quando ele vem zerado (S-239).
        feitas = len(correcao.correcoes(gravado))
        quanto = f" · {feitas} correção(ões) sobre o que o motor leu" if feitas else ""
        self._atualizar_status()
        self.estado.emit(f"Texto gravado em {caminho.name}{quanto}.")

    @property
    def tem_alteracoes(self) -> bool:
        """A folha tem edição que ainda não está no disco? É o que o fechamento e a releitura perguntam.

        **Comparada com o que foi gravado, e não com a pilha.** A pilha dizia "editado" também
        depois de gravar -- e aí a pergunta "descarta as alterações?" chegava sobre um texto que já
        estava salvo, que é o jeito de ensinar a clicar "Sim" sem ler. Desfazer até o que estava
        gravado também não deixa nada a perder, e a comparação por valor vê isso.
        """
        return self.documento != self._documento_gravado

    def confirmar_fechamento(self) -> bool:
        """A janela vai fechar: `True` se pode, perguntando antes quando há texto por gravar.

        **O rascunho vai para o disco antes da pergunta** (S-255): o relógio de inatividade pode
        não ter disparado, e fechar -- com "Sim", sem tela, ou pela falha que vem a seguir -- é
        exatamente o momento para o qual ele existe. Gravar de novo o que já está lá não custa.
        """
        self.gravar_rascunho()
        return self._confirmar_descarte("Fechar a janela descarta as alterações.", ao_fechar=True)

    # ----------------------------------------------------------- o rascunho automático (S-255)

    def _agendar_rascunho(self) -> None:
        """Reinicia o relógio: o rascunho é gravado alguns segundos depois da **última** edição."""
        self._rascunho.start()

    def _depois_da_pausa(self) -> None:
        """A pausa da digitação: o rascunho vai ao disco e, com a conferência ligada, o léxico se refaz.

        A tecla comum não redesenha a folha (é o caminho rápido de `_trocado`), então a palavra
        recém-escrita só era conferida no redesenho seguinte -- e a conferência ligada prometia o
        contrário (S-293). Reconferir a cada tecla seria carregar e varrer o léxico por letra; na
        pausa, uma vez, é o mesmo relógio do rascunho, e pelo mesmo motivo: quem parou de digitar
        é quem vai olhar a folha.
        """
        self.gravar_rascunho()
        if self._conferindo_lexico:
            self._conferir_lexico(avisar=False)

    def gravar_rascunho(self) -> Path | None:
        """Grava o rascunho **se houver o que gravar**. Devolve o caminho, ou `None`.

        Só com alteração por gravar: reescrever o mesmo arquivo a cada quatro segundos é desgaste
        de disco por nada. E só com folha de origem -- documento sem folha não tem chave estável,
        e `rascunho.gravar` devolve `None` para ele.
        """
        self._rascunho.stop()
        if not self.tem_alteracoes or self._pagina is None:
            return None
        try:
            return rascunho.gravar(correcao.com_procedencia_humana(self.documento), pasta=self._pasta_de_rascunhos)
        except OSError as erro:  # noqa: BLE001 - rascunho é rede de segurança, não função
            logger.debug("Rascunho não pôde ser gravado: %s", erro)
            return None

    def oferecer_rascunho(self, pagina: PaginaLida) -> bool:
        """Se houver rascunho daquela folha, **oferece** recuperá-lo. Devolve se recuperou.

        Oferece e não aplica: sobrescrever o que a pessoa acabou de ler com um rascunho de ontem é
        o contrário do que ela quer. E recusar **não apaga** -- na próxima abertura a oferta volta.
        Sem tela não há quem responda, e a resposta que não perde nada é a mesma: o rascunho fica.
        """
        from chess_diagram_ocr.qt import dialogos

        achado = rascunho.achar(pagina.documento, pagina.pagina, pasta=self._pasta_de_rascunhos)
        if achado is None:
            return False
        if not dialogos.ha_quem_responda():
            logger.warning("Há um rascunho da folha %d e nenhuma tela para oferecê-lo: ele fica.", pagina.pagina + 1)
            return False
        resposta = QMessageBox.question(
            self,
            "Texto",
            rascunho.frase_de_recuperacao(achado),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return False
        try:
            doc = rascunho.carregar(achado)
        except (OSError, ValueError) as erro:  # `arquivo.ArquivoInvalido` é um `ValueError`
            logger.debug("Rascunho não abriu (%s): %s", achado.caminho, erro)
            self.estado.emit(f"O rascunho não pôde ser aberto: {erro}")
            return False
        # A folha é a que acabou de ser lida: a imagem dela serve, e não se renderiza de novo.
        self.abrir(doc, folha_rgb=self._pagina_rgb)
        # **Recuperado é trabalho por gravar, e não trabalho gravado (S-308).** `abrir` iguala o
        # gravado ao que está na tela -- o certo para um arquivo do disco, e o errado para este,
        # que veio de um arquivo que a linha seguinte apaga. Sem isto, o texto resgatado de um
        # travamento voltaria a existir só na memória: as guardas que perguntam antes de descartar
        # passariam direto, e `gravar_rascunho` sairia sem reescrever nada. O segundo travamento
        # perderia tudo -- e o recurso existe exatamente para o segundo travamento.
        self._documento_gravado = rico.de_pagina(pagina)
        # Recuperado é trabalho que chegou a um lugar melhor -- a tela --, e o arquivo sai.
        rascunho.descartar(pagina.documento, pagina.pagina, pasta=self._pasta_de_rascunhos)
        self._agendar_rascunho()
        self.estado.emit(f"Rascunho de {achado.data_legivel} recuperado.")
        return True

    def _confirmar_descarte(self, o_que: str, *, ao_fechar: bool = False) -> bool:
        """Pergunta antes de jogar fora o que foi editado e não foi gravado. Sem isso, não pergunta.

        **Sem tela não há quem responda** (`dialogos.ha_quem_responda`), e a resposta é a mesma de
        `dialogos.perguntar_descarte`: fechar fecha -- não há o que fazer com uma janela que já
        está sendo destruída --, e ler ou abrir outra folha **não** descarta, que é a resposta que
        não perde nada. As duas ficam no log.
        """
        from chess_diagram_ocr.qt import dialogos

        if not self.tem_alteracoes:
            return True
        if not dialogos.ha_quem_responda():
            logger.warning(
                "O texto da aba Texto tem alterações não gravadas e nenhuma tela para perguntar: %s.",
                "o fechamento segue" if ao_fechar else "as alterações ficam",
            )
            return ao_fechar
        onde = "da aba Texto" if ao_fechar else "desta aba"
        resposta = QMessageBox.question(
            self,
            "Texto",
            f"O texto {onde} foi editado e não foi gravado. {o_que} Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resposta == QMessageBox.StandardButton.Yes


    # ------------------------------------------------------------- a exportação (S-254)

    def salvar(self) -> None:
        """O `.txt` puro, ao lado do `.cvtxt`: quem quer colar num e-mail quer este."""
        self._exportar(".txt")

    def exportar_md(self) -> None:
        """`.md` **porque ele diffa**: duas correções da mesma folha comparam linha a linha."""
        self._exportar(".md")

    def exportar_html(self) -> None:
        self._exportar(".html")

    def exportar_rtf(self) -> None:
        self._exportar(".rtf")

    def exportar_pdf_pesquisavel(self) -> None:
        """O livro com a camada de texto por cima -- o que faz o PDF ser pesquisável."""
        self._exportar(".pdf")

    def _exportar(self, extensao: str) -> None:
        """Pergunta o destino e exporta **fora da thread da janela** (S-254).

        O `.txt` de uma folha é imperceptível, e gravá-lo na thread da janela estaria certo. Deixa
        de estar com o `.rtf` de imagens embutidas e com o PDF pesquisável, que abre o livro,
        escreve a camada e grava um arquivo novo.
        """
        from chess_diagram_ocr.text import arquivo, exportacao

        if self._tarefa is not None:
            self.estado.emit("Já há uma exportação em curso nesta aba.")
            return
        if not self.documento.para_texto().strip():
            # Rodapé e não caixa: é um passo que falta, e não uma escolha.
            self.estado.emit("Não há texto nesta aba para exportar.")
            return
        formato = exportacao.formato_de(extensao)
        destino, _filtro = QFileDialog.getSaveFileName(
            self,
            f"Exportar o texto da folha para {formato.nome}",
            arquivo.sugestao_de_nome(self.documento, extensao=extensao),
            f"{formato.nome} (*{extensao});;Todos (*.*)",
        )
        if not destino:
            return
        caminho = Path(destino)
        # O que se exporta é o que se grava: com a procedência da mão (S-239) -- o cabeçalho do
        # `.txt` a declara -- e sem tocar no que está na tela.
        doc = correcao.com_procedencia_humana(self.documento)
        folha = self._pagina_rgb
        dpi = self._dpi
        com_imagens = bool(getattr(formato, "pasta_de_imagens", ""))

        # **Cancelável, e o ponto de corte é antes da escrita** (F9-C2, §7 item 7). A conversão
        # do documento é a parte longa; escrever o arquivo é um `write` só. Então desistir tem um
        # lugar seguro e um só: entre as duas. Cortar **durante** a escrita deixaria em disco o
        # `.pdf` truncado que o comentário de `loses_work=True` descreve -- e um arquivo que abre
        # e mente é pior que nenhum, que é a razão de o cancelamento não interromper o `escrever`.
        desistir = threading.Event()
        self._cancelar_exportacao = desistir

        def _trabalho() -> str:
            # Os recortes dos diagramas saem **antes** do arquivo, na mesma thread: são o que o
            # `.md` e o `.html` apontam (S-338). Sem folha renderizada a marca sai sozinha.
            recortes = _gravar_recortes(doc, caminho, folha, dpi=dpi) if com_imagens else {}
            relatorio = exportacao.exportar(doc, formato, recortes=recortes)
            if desistir.is_set():
                return CANCELADA
            exportacao.escrever(caminho, relatorio)
            return exportacao.texto_do_relatorio(
                caminho, relatorio, tamanho=caminho.stat().st_size
            )

        self.estado.emit(f"Exportando para {caminho.name}…")
        # `loses_work=True`: o arquivo de destino fica pela metade se a janela fechar no meio,
        # e um `.pdf` pesquisável truncado é pior que nenhum -- ele abre e mente.
        self._registrar_ocupado(
            f"Exportando para {formato.nome}",
            loses_work=True,
            detail=caminho.name,
            cancelar=desistir.set,
        )
        self._tarefa = Tarefa(_trabalho, parent=self)
        self._tarefa.pronto.connect(self._exportacao_terminou)
        self._tarefa.falhou.connect(self._exportacao_falhou)
        self._tarefa.finished.connect(self._soltar_ocupado)
        self._tarefa.start()

    def _registrar_ocupado(
        self,
        nome: str,
        *,
        loses_work: bool,
        detail: str = "",
        cancelar: Callable[[], None] | None = None,
    ) -> None:
        """Põe a operação no registro, se a janela deu um. Ver o campo `_busy`.

        `cancelar` é o que o botão do rodapé chama. `busy.register` faz
        `cancellable and cancel is not None`, então passar `None` continua registrando uma
        operação sem cancelamento -- prometer o botão sem a função seria oferecer um cancelamento
        que não cancela.
        """
        if self._busy is None:
            return
        self._ocupado = self._busy.register(
            nome,
            loses_work=loses_work,
            detail=detail,
            cancellable=cancelar is not None,
            cancel=cancelar,
        )

    def _soltar_ocupado(self) -> None:
        """**Sai do registro sempre**, e por isso está no `finished` e não no `pronto` (S-112).

        Um `BusyToken` que ficasse pendurado numa falha faria a janela perguntar "fechar mesmo
        assim?" para sempre, sobre uma operação que já acabou."""
        if self._ocupado is not None:
            self._ocupado.release()
            self._ocupado = None

    def _exportacao_terminou(self, frase: object) -> None:
        """O desfecho da exportação -- **e desistir é um desfecho, não um erro**."""
        self._tarefa = None
        if str(frase) == CANCELADA:
            self.estado.emit("Exportação cancelada. Nada foi gravado.")
            return
        self.estado.emit(str(frase))

    def _exportacao_falhou(self, erro: str) -> None:
        self._tarefa = None
        QMessageBox.critical(self, "Exportar", f"Falha ao exportar:\n{erro}")

    # ---------------------------------------------------------- a leitura, em thread

    @property
    def motor(self) -> str:
        """O motor de leitura escolhido -- o que a janela grava no estado (item 17)."""
        return str(self._motor)

    @property
    def modo_bloco(self) -> bool:
        return bool(self._modo_bloco)

    def definir_motor(self, nome: str) -> None:
        """Repõe o motor gravado na sessão anterior; um nome que a aba não conhece é ignorado."""
        if nome not in MOTORES:
            return
        self._motor = nome
        self.escolha_de_motor.setCurrentIndex(MOTORES.index(nome))

    def definir_modo_bloco(self, ligado: bool) -> None:
        """Repõe o modo bloco gravado -- sem a frase do rodapé, que é para quem acabou de clicar."""
        self._modo_bloco = bool(ligado)
        self.caixa_de_bloco.blockSignals(True)
        try:
            self.caixa_de_bloco.setChecked(bool(ligado))
        finally:
            self.caixa_de_bloco.blockSignals(False)

    def modo_bloco_mudou(self) -> None:
        """Liga e desliga o modo bloco. **O comando não inverte a caixa**: quem a inverte é ela."""
        self._modo_bloco = self.caixa_de_bloco.isChecked()
        self.estado.emit(
            "Modo bloco: a folha é lida em blocos, e não linha a linha."
            if self._modo_bloco
            else "Modo linha: a folha volta a ser lida linha a linha."
        )

    def sincronizar_com_a_pagina(self) -> None:
        """Lê a folha que o visualizador está mostrando -- e não a que o campo diz (S-236)."""
        self.campo_de_folha.setValue(self._pagina_indice + 1)
        self.ler()

    def ler(self) -> None:
        """Lê a folha pedida numa thread e desenha o resultado quando ele chega.

        **O `import` do leitor mora aqui**, e é regra e não descuido: por `text/recognizer.py` ele
        alcança o **torch**, e esta aba é construída na abertura da janela. Pagar o carregamento de
        um framework de aprendizado para desenhar uma barra de botões atrasaria a janela inteira
        por uma aba que talvez ninguém abra.
        """
        if self._tarefa is not None:
            self.estado.emit("Já há uma leitura em curso nesta aba.")
            return
        if self._pdf is None:
            # Rodapé e não caixa: é um passo que falta, e não uma escolha.
            self.estado.emit("Abra um PDF antes de ler o texto da folha.")
            return
        if not self._confirmar_descarte("Ler de novo descarta as alterações."):
            return
        # O que está na tela quando a leitura parte: o que for digitado **durante** ela não foi
        # confirmado por ninguém, e `_leitura_terminou` pergunta de novo antes de trocá-lo.
        self._documento_ao_ler = self.documento

        indice = int(self.campo_de_folha.value()) - 1
        motor = self._motor
        bloco = self._modo_bloco
        caminho = self._pdf
        dpi = self._dpi_para_ler()
        teto = self._teto_de_diagramas()

        def _trabalho() -> tuple[PaginaLida, np.ndarray | None, int, float]:
            # **A folha é rasterizada uma vez, e aqui (S-352).** `ler_pagina` a renderiza sozinha
            # quando ninguém lhe dá a imagem, e as miniaturas precisariam dela de novo -- na thread
            # da janela, que congelava ~355 ms por leitura no outro frontend. O mesmo `dpi` dos
            # dois lados é o que liga pixel a ponto -- e ele viaja com a folha, porque a
            # configuração pode mudar enquanto a leitura corre. O tempo vai junto (item 16): é o
            # número que decide entre o motor rápido e o modo bloco de 40 s.
            inicio = time.perf_counter()
            imagem = _renderizar(caminho, indice, dpi=dpi)
            lida = _ler(caminho, indice, dpi=dpi, motor=motor, modo_bloco=bloco, imagem_rgb=imagem, max_boards=teto)
            return lida, imagem, dpi, time.perf_counter() - inicio

        self.estado.emit(f"Lendo a folha {indice + 1}…")
        self._registrar_ocupado(
            f"Lendo o texto da folha {indice + 1}",
            loses_work=False,
            detail=f"motor {motor}" + (" · modo bloco" if bloco else ""),
        )
        self._tarefa = Tarefa(_trabalho, parent=self)
        self._tarefa.pronto.connect(self._leitura_terminou)
        self._tarefa.falhou.connect(self._leitura_falhou)
        self._tarefa.finished.connect(self._soltar_ocupado)
        self._tarefa.start()

    def _dpi_para_ler(self) -> int:
        """O DPI da próxima leitura: o cravado pelo teste, ou o das Configurações (o produto)."""
        if self._dpi_fixo:
            return int(self._dpi_fixo)
        from chess_diagram_ocr.ui import configuracoes

        return int(configuracoes.dpi())

    def _teto_de_diagramas(self) -> int | None:
        """Quantos diagramas o leitor procura na folha: o mesmo teto das Configurações que o
        visualizador usa. Sem ele a aba Texto e a aba Livro discordavam sobre quantos há na página."""
        if self._dpi_fixo:
            return None  # o teste dá a folha sintética e não lê de verdade
        from chess_diagram_ocr.ui import configuracoes

        return int(configuracoes.max_boards())

    def _leitura_terminou(self, resultado: object) -> None:
        """A folha lida voltou da thread -- **e a imagem vem com ela** (S-352), com o DPI dela."""
        self._tarefa = None
        if isinstance(resultado, tuple):
            pagina, imagem, dpi, segundos = (*resultado, None, None)[:4]
        else:
            pagina, imagem, dpi, segundos = resultado, None, None, None
        assert isinstance(pagina, PaginaLida)
        partida = self._documento_ao_ler
        self._documento_ao_ler = None
        editado_na_leitura = partida is not None and self.documento is not partida
        if editado_na_leitura and not self._confirmar_descarte(
            "A folha lida substitui o que foi editado durante a leitura."
        ):
            self.estado.emit("A folha lida ficou de lado: o texto editado durante a leitura continua na tela.")
            return
        self._pagina_indice = int(self.campo_de_folha.value()) - 1
        self.mostrar_pagina(pagina, folha_rgb=imagem, dpi=dpi)
        diagramas = len(pagina.diagramas)
        figuras = f", {diagramas} diagrama(s)" if diagramas else ""
        # «em 3,9 s»: a pessoa escolhe o motor e o modo bloco pelo preço, e o preço tem de ser dito.
        tempo = "" if segundos is None else f" em {segundos:.1f} s".replace(".", ",")
        self.estado.emit(f"Folha lida{tempo}: {len(self.documento.corridas)} trecho(s){figuras}.")
        # **Depois de desenhar, e não antes**: se a pessoa recusar a oferta, o que fica na tela é
        # a leitura que ela acabou de pedir (S-255).
        self.oferecer_rascunho(pagina)

    def _leitura_falhou(self, erro: str) -> None:
        self._tarefa = None
        self._documento_ao_ler = None
        QMessageBox.critical(self, "Ler a folha", f"Não foi possível ler a folha:\n{erro}")

    # ------------------------------------------------------ o que a janela pergunta (S-283)

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
        if _chave_de_livro(novo) != _chave_de_livro(self._pdf):
            self._posicoes.clear()  # as posições são do livro que saiu (item 11)
            self._anunciar_rascunhos(novo)
        self._pdf = novo
        # O teto só muda quando se sabe o número ou quando o livro fecha: a virada de página chama
        # isto sem `paginas`, e não pode devolver o campo ao teto largo.
        if paginas:
            self.campo_de_folha.setMaximum(max(1, int(paginas)))
        elif novo is None:
            self.campo_de_folha.setMaximum(TETO_DE_FOLHAS)
        if pagina is not None:
            self._pagina_indice = int(pagina)
            self._montando = True
            try:
                self.campo_de_folha.setValue(self._pagina_indice + 1)
            finally:
                self._montando = False

    def _anunciar_rascunhos(self, livro: Path | None) -> None:
        """Na troca de livro, diz quantos rascunhos dele há por recuperar e em que folhas (item 18).

        A oferta de recuperação (S-255) só acontece ao ler a folha certa: quem fecha o programa
        com três folhas corrigidas e volta no dia seguinte não tinha como saber que elas existem,
        nem quais são. Rodapé e não caixa: é informação, e a decisão continua sendo ler a folha.
        """
        if livro is None:
            return
        try:
            achados = rascunho.listar(livro, pasta=self._pasta_de_rascunhos)
        except OSError as erro:  # noqa: BLE001 - a lista é conforto; o livro abre igual
            logger.debug("Rascunhos de %s não listados: %s", livro, erro)
            return
        if not achados:
            return
        folhas = ", ".join(str(r.folha + 1) for r in achados[:6]) + ("…" if len(achados) > 6 else "")
        self.estado.emit(
            f"{len(achados)} rascunho(s) deste livro por recuperar (folha {folhas}): "
            "leia a folha e a aba oferece."
        )

    def definir_posicoes(self, pagina: int, posicoes: Sequence[str]) -> None:
        """O campo de peças de cada diagrama da folha, como o OCR de diagramas do produto leu.

        A aba Livro lê a posição com o classificador de peças; esta aba só sabia **onde** cada
        diagrama está. Com a FEN no bloco, o `.cvtxt` a guarda, o `.md` e o `.html` a escrevem
        (item 5) e a miniatura pode nascer dela quando o livro não está. Chega pela janela a cada
        leitura de diagramas (`_chegaram_itens`), em qualquer ordem em relação à leitura do texto:
        a folha que já está na tela recebe na hora, **sem virar alteração por gravar** -- a posição
        é leitura, não edição.
        """
        chave = (_chave_de_livro(self._pdf), int(pagina))
        self._posicoes[chave] = tuple(str(p or "") for p in posicoes)
        if (
            self._pagina is None
            or int(self._pagina.pagina) != int(pagina)
            or _chave_de_livro(self._pagina.documento) != chave[0]
        ):
            return
        nova = self._pagina.com_posicoes(self._posicoes[chave])
        if nova is self._pagina:
            return
        self._pagina = nova
        self.documento = rico.DocumentoRico(corridas=self.documento.corridas, origem=nova)
        if self._documento_gravado.origem is not None:
            self._documento_gravado = rico.DocumentoRico(corridas=self._documento_gravado.corridas, origem=nova)
        self._desenhar(selecao=self._selecao_atual())
        self._atualizar_status()

    def notacao_do_diagrama(self, pagina: int, diagrama: int) -> str:
        """A notação que o livro imprimiu ao lado daquele diagrama, ou `""` (S-283).

        **É o vínculo da S-249 com um cliente.** `BlocoDeTexto.legenda_de` diz de qual diagrama
        cada parágrafo é a legenda, e até a sala de estudo isso só pintava o estilo `legenda` na
        tela. A sala pergunta a mesma coisa por outro motivo: o parágrafo ao lado do diagrama 3
        costuma trazer a linha que o autor dá para aquela posição.

        **Devolve `""` em três casos, e todos são "ainda não sei"**: não há folha lida, a folha
        lida é de outra página, ou nenhum parágrafo daquele diagrama é notação. Nenhum deles é
        erro -- ler a folha custa de 1 s a 40 s, e é decisão de quem lê.

        O corte "é notação" é o de `text/notacao.e_linha_de_notacao`, o mesmo que a S-249 usa para
        pintar o estilo: a **maioria** dos tokens do parágrafo é lance.
        """
        from chess_diagram_ocr.text import notacao
        from chess_diagram_ocr.text import pagina as pagina_mod

        lida = self._pagina
        if lida is None or int(lida.pagina) != int(pagina):
            return ""
        trechos = [
            bloco.texto
            for bloco in lida.blocos
            if isinstance(bloco, pagina_mod.BlocoDeTexto)
            and bloco.legenda_de == int(diagrama)
            and notacao.e_linha_de_notacao(bloco.texto)
        ]
        return " ".join(trechos).strip()

    # ------------------------------------------------------------------------------ a digitação

    def _digitado(self, posicao: int, removidos: int, acrescidos: int) -> None:
        """Uma mudança do texto na tela -- tecla, colar, recortar, arrastar -- vira mudança do documento.

        `contentsChange` diz **onde** mudou; o que saiu vem de `_tela`, o texto como estava. Os
        números do Qt são conferidos contra os dois textos antes de serem usados, e a conta é
        refeita dos dois quando não batem: uma troca de formato chega pelo mesmo sinal sem mudar
        letra nenhuma, e um arrasto dentro da folha chega como **uma** janela que cobre a origem e
        o destino.
        """
        documento = self.editor.document()
        if self._redesenhando or self._sincronizando or documento is None:
            return
        antes, depois = self._tela, _texto_da_tela(documento)
        self._tela = depois
        janela = _janela_informada(antes, depois, posicao, removidos, acrescidos)
        if janela is None:
            return
        inicio, removido, acrescido = janela
        velho, novo = antes[inicio : inicio + removido], depois[inicio : inicio + acrescido]
        giro = _giro(velho, novo)
        if giro:
            self._arrastado(inicio, len(velho), giro)
            return
        if velho and len(novo) > 1:
            # Colar por cima de uma seleção, ou o Qt anunciando mais do que mudou: o que começa e
            # termina igual não foi trocado, e continua sendo o que era -- com atributo e marca.
            miolo = _janela_da_troca(velho, novo)
            if miolo is None:
                return
            inicio, removido, acrescido = inicio + miolo[0], miolo[1], miolo[2]
            novo = depois[inicio : inicio + acrescido]
        self._trocado(inicio, removido, novo)

    def _trocado(self, inicio: int, removido: int, novo: str) -> None:
        """Os `removido` caracteres em `inicio` deram lugar a `novo`: o documento acompanha, por `rico.editar`.

        **Fiel** é a troca que o documento aceitou como a tela a mostra: nenhuma miniatura saiu, nada
        que não é texto entrou, e `rico` não alargou nem recusou a troca. Aí o mapa anda junto e só o
        trecho novo é repintado -- é o caminho de toda tecla comum. O resto -- a marca do diagrama que
        sai inteira, a letra escrita dentro dela, a miniatura apagada sozinha -- redesenha a folha a
        partir do documento, que é quem manda, com o cursor no lugar da troca.
        """
        de = self._mapa.deslocamento(inicio)
        ate = self._mapa.deslocamento(inicio + removido)
        escrito = novo.replace(OBJETO, "")
        alcance = rico.alcance_da_edicao(self.documento, de, ate, escrito)
        if alcance is None:
            self.estado.emit(
                "A marca do diagrama não se edita por dentro: escreva antes ou depois dela, "
                "ou apague-a inteira."
            )
            self._desenhar(selecao=(de, de))
            return
        editado = rico.editar(self.documento, de, ate, escrito)
        mudou = editado is not self.documento
        if mudou:
            agora = self._relogio()
            passo = not continua_a_digitacao(self._digitacao, alcance[0], alcance[1], escrito, agora=agora)
            self._guardar_digitado(editado, passo=passo)
            self._digitacao = digitacao_depois(alcance[0], alcance[1], escrito, agora=agora)
        if removido == ate - de and escrito == novo and alcance == (de, ate):
            self._mapa.trocar(inicio, removido, de, len(escrito))
            self._pintar_o_digitado(inicio, len(escrito), de)
            return
        if alcance != (de, ate):
            self.estado.emit("O diagrama saiu da folha junto com a marca inteira; desfazer o devolve.")
        elif not mudou and removido > ate - de:
            # Só o desenho saiu -- a miniatura, a quebra embaixo dela --, e ele volta no redesenho.
            self.estado.emit(
                "A miniatura é desenho, e não texto: para tirar o diagrama da folha, apague a marca dele."
            )
        cursor = alcance[0] + len(escrito)
        self._desenhar(selecao=(cursor, cursor))

    def _arrastado(self, inicio: int, tamanho: int, giro: int) -> None:
        """Um trecho arrastado dentro da folha: o documento o leva inteiro, por `rico.mover`.

        A janela `[inicio, inicio + tamanho)` saiu girada de `giro`: os `giro` primeiros caracteres
        foram para o fim, ou os outros vieram para o começo -- as duas leituras dão a mesma tela, e
        a que se usa é a do trecho **menor**, que é o que a pessoa arrastou. Tratar o arrasto como
        apagar e escrever faria o trecho perder o que o Qt também perde ao soltar texto puro -- o
        atributo e, pior, a marca do diagrama, que chegaria como texto comum. Por isso a folha é
        redesenhada a partir do documento: o trecho volta com o que era.
        """
        if giro <= tamanho - giro:
            origem, destino = (inicio, inicio + giro), inicio + tamanho
        else:
            origem, destino = (inicio + giro, inicio + tamanho), inicio
        de, ate = rico.alcance_de_apagar(
            self.documento, self._mapa.deslocamento(origem[0]), self._mapa.deslocamento(origem[1])
        )
        para = self._mapa.deslocamento(destino)
        movido = rico.mover(self.documento, de, ate, para)
        self._digitacao = None
        if movido is self.documento:
            self.estado.emit("O trecho não pode ser solto ali: a marca do diagrama não se parte.")
            self._desenhar(selecao=(de, ate))
            return
        self._guardar_digitado(movido, passo=True)
        fim = para if para >= ate else para + (ate - de)
        self._desenhar(selecao=(fim - (ate - de), fim))

    def _guardar_digitado(self, novo: rico.DocumentoRico, *, passo: bool) -> None:
        """Põe `novo` no lugar do documento; `passo` empilha o anterior -- a tecla abriu um passo novo."""
        if passo:
            self._historico.append(self.documento)
            self._refeitos.clear()
        # Cresce a cada tecla, e não a cada passo: a pergunta de `ui/desfazivel` é "quem foi editado
        # por último", e a última tecla é a resposta mesmo dentro de um passo aberto (S-243).
        self._edicao += 1
        self.documento = novo
        self.documento_mudou.emit()

    def _pintar_o_digitado(self, inicio: int, tamanho: int, deslocamento: int) -> None:
        """Repinta só o trecho digitado, com o formato da corrida em que o documento o pôs.

        O Qt escreve a letra com o formato da vizinha **da tela**, e o documento escolheu outro
        quando as regras divergem: a faixa da mão no lugar do `revisar` herdado, o negrito da
        seleção que foi trocada. Sem isto a tela mostraria uma coisa e o arquivo gravaria outra até o
        próximo redesenho.
        """
        corrida = _corrida_em(self.documento, deslocamento)
        documento = self.editor.document()
        if tamanho <= 0 or corrida is None or documento is None:
            return
        cursor = QTextCursor(documento)
        cursor.setPosition(inicio)
        cursor.setPosition(inicio + tamanho, QTextCursor.MoveMode.KeepAnchor)
        self._sincronizando = True
        try:
            cursor.setCharFormat(formato_de(corrida, base=self._base))
        finally:
            self._sincronizando = False

    # ------------------------------------------------------------------------------ teclado

    def eventFilter(self, a0: object, a1: object) -> bool:  # noqa: N802 - assinatura do Qt
        """`Ctrl+Z` e `Ctrl+Y` dentro da folha são deste painel; o estado vazio acompanha o poço.

        A tecla de desfazer chega ao editor porque a guarda de atalhos a cede a todo campo de
        texto -- e o desfazer do `QTextEdit` está desligado. Ver `TECLAS_DO_HISTORICO`.
        """
        if a0 is self.editor and isinstance(a1, QKeyEvent) and a1.type() == QEvent.Type.KeyPress:
            combinacao = QKeySequence(a1.keyCombination())
            for acao, tecla in self._teclas_do_historico.items():
                alvo = self.atender(acao) if tecla == combinacao else None
                if alvo is not None:
                    alvo()
                    return True
        if a0 is self.editor.viewport() and a1 is not None and a1.type() == QEvent.Type.Resize:
            self.vazio.setGeometry(self.editor.viewport().rect())
        if a0 is self.editor.viewport() and isinstance(a1, QWheelEvent) and a1.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+roda é o zoom da vista (item 13). O `QTextEdit` responderia mudando a fonte do
            # editor -- que nenhuma letra segue, porque cada trecho sai com corpo explícito (S-264).
            passo = a1.angleDelta().y()
            if passo:
                self._mudar_zoom(+1 if passo > 0 else -1)
            return True
        if a0 is self.editor.viewport() and isinstance(a1, QMouseEvent) and a1.button() == Qt.MouseButton.LeftButton:
            ponto = a1.position().toPoint()
            if a1.type() == QEvent.Type.MouseButtonPress and self._clicou_na_miniatura(ponto):
                return True
            if a1.type() == QEvent.Type.MouseButtonDblClick and self._ativou_a_miniatura(ponto):
                return True
        return super().eventFilter(a0, a1)  # type: ignore[arg-type]

    # ------------------------------------------------------------------- a miniatura (item 8)

    def _marca_sob(self, ponto: QPoint) -> tuple[int, int, rico.Corrida] | None:
        """A marca `[Diagrama N]` da miniatura que está sob o ponto: `(começo, fim, corrida)`.

        A miniatura é um caractere do widget que não existe no documento (`_Mapa`); a marca dela
        vem logo depois, no bloco seguinte. O cursor que o Qt dá para o ponto cai antes ou depois
        do caractere da imagem, e por isso se sondam os dois.
        """
        documento = self.editor.document()
        if documento is None:
            return None
        posicao = self.editor.cursorForPosition(ponto).position()
        for p in (posicao, posicao - 1):
            if p < 0:
                continue
            sonda = QTextCursor(documento)
            sonda.setPosition(p + 1)  # `charFormat` é o do caractere **antes** do cursor: o `p`
            if sonda.position() != p + 1 or not sonda.charFormat().isImageFormat():
                continue
            achado = self._marca_em(self._mapa.deslocamento(p + 2))
            if achado is not None:
                return achado
        # Sobre o texto da própria marca (item 12): `[Diagrama 3]` é o diagrama tanto quanto a
        # figura -- e é tudo o que há dele quando não há figura nenhuma.
        return self._marca_em(self._mapa.deslocamento(posicao))

    def _marca_em(self, deslocamento: int) -> tuple[int, int, rico.Corrida] | None:
        """A marca de diagrama que contém o deslocamento do documento, ou `None`."""
        comeco = 0
        for corrida in self.documento.corridas:
            fim = comeco + len(corrida.texto)
            if corrida.e_diagrama and comeco <= deslocamento < fim:
                return comeco, fim, corrida
            comeco = fim
        return None

    def _clicou_na_miniatura(self, ponto: QPoint) -> bool:
        """O clique na miniatura seleciona a marca dela: é a marca que se apaga, move e copia.

        Sem isto o clique punha o cursor ao lado de um caractere invisível, e a pessoa apagava a
        figura sem apagar o diagrama (`_trocado` avisa, mas avisar é o segundo melhor).
        """
        achado = self._marca_sob(ponto)
        if achado is None:
            return False
        comeco, fim, _corrida = achado
        cursor = self.editor.textCursor()
        cursor.setPosition(self._mapa.posicao(comeco))
        cursor.setPosition(self._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        return True

    def _abrir_menu_de_contexto(self, ponto: QPoint) -> None:
        menu = self._menu_de_contexto(ponto)
        menu.exec(self.editor.viewport().mapToGlobal(ponto))
        menu.deleteLater()

    def _menu_de_contexto(self, ponto: QPoint) -> QMenu:
        """O menu do botão direito: o padrão do editor e, sobre uma miniatura, o que ela sabe fazer.

        Três ações, e as três já existiam por outro caminho -- é o que as mantém fora do catálogo
        de comandos (S-256): abrir na sala é o duplo clique (item 8), copiar a imagem é o que a
        aba Livro faz com o recorte, apagar o diagrama é apagar a marca, que o clique já
        seleciona. O menu é onde quem não sabe do duplo clique descobre que a miniatura é viva.
        """
        menu = self.editor.createStandardContextMenu(ponto)
        achado = self._marca_sob(ponto)
        if achado is None:
            return menu
        comeco, fim, corrida = achado
        numero = int(getattr(self.documento.bloco_de(corrida), "indice", -1)) + 1
        menu.addSeparator()
        estudar = QAction(f"Abrir o diagrama {numero} no Estudo", menu)
        estudar.triggered.connect(lambda: self._ativou_a_miniatura(ponto))
        copiar = QAction(f"Copiar a imagem do diagrama {numero}", menu)
        copiar.triggered.connect(lambda: self._copiar_miniatura(corrida))
        apagar = QAction(f"Apagar o diagrama {numero} da folha", menu)
        apagar.triggered.connect(lambda: self._apagar_diagrama(comeco, fim, numero))
        for acao in (estudar, copiar, apagar):
            menu.addAction(acao)
        return menu

    def _copiar_miniatura(self, corrida: rico.Corrida) -> None:
        """A figura do diagrama -- recorte ou desenho -- vai para a área de transferência."""
        figura = self._imagem_do_diagrama(corrida)
        if figura is None:
            self.estado.emit("Este diagrama não tem figura para copiar.")
            return
        QApplication.clipboard().setPixmap(figura)
        self.estado.emit("Imagem do diagrama copiada.")

    def _apagar_diagrama(self, comeco: int, fim: int, numero: int) -> None:
        """Tira a marca inteira -- e com ela a figura. É uma edição: `Ctrl+Z` a devolve."""
        self._aplicar(rico.apagar(self.documento, comeco, fim), selecao=(comeco, comeco))
        self.estado.emit(f"O diagrama {numero} saiu da folha; desfazer o devolve.")

    def _ativou_a_miniatura(self, ponto: QPoint) -> bool:
        """O duplo clique na miniatura pede o diagrama na sala de estudo (`diagrama_ativado`)."""
        achado = self._marca_sob(ponto)
        if achado is None or self._pagina is None:
            return False
        bloco = self.documento.bloco_de(achado[2])
        indice = getattr(bloco, "indice", None)
        if indice is None:
            return False
        self.diagrama_ativado.emit(int(self._pagina.pagina), int(indice))
        return True

    def _mostrar_vazio(self) -> None:
        """Mostra o estado vazio enquanto não há folha nenhuma no editor (F9-C2, §7 item 14).

        Some no primeiro caractere, e é isso que o mantém fora da exportação: o `EstadoVazio` é um
        widget **sobre** o editor, e não texto dentro dele -- que era a razão de o ciclo 1 ter
        escolhido `placeholderText`, e que continua valendo.
        """
        self.vazio.setGeometry(self.editor.viewport().rect())
        self.vazio.setVisible(not self.editor.toPlainText().strip())

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
        getattr(self, COMANDOS_DA_ABA[acao])()


def _renderizar(caminho: Path, indice: int, *, dpi: int) -> np.ndarray | None:
    """A folha renderizada, de onde saem as miniaturas. `None` quando ela não pôde ser aberta.

    Função do módulo, e não método, por dois motivos: ela roda na thread de trabalho, onde nada
    do widget pode ser tocado; e o teste a troca por uma folha sintética sem abrir PDF nenhum.
    """
    try:
        from chess_diagram_ocr.pdf_io import render_pdf_page

        return render_pdf_page(caminho, indice, dpi=dpi)
    except Exception as erro:  # noqa: BLE001 - miniatura é conforto, não função
        logger.debug("Sem imagem da folha %d para as miniaturas: %s", indice + 1, erro)
        return None


def _ler(
    caminho: Path,
    indice: int,
    *,
    dpi: int,
    motor: str,
    modo_bloco: bool,
    imagem_rgb: np.ndarray | None,
    max_boards: int | None = None,
) -> PaginaLida:
    """`ler_pagina` com a folha já renderizada. **O `import` do leitor mora aqui** -- ver `ler`."""
    from chess_diagram_ocr.text.leitor import ler_pagina

    return ler_pagina(
        caminho, indice, dpi=dpi, motor=motor, modo_bloco=modo_bloco, imagem_rgb=imagem_rgb, max_boards=max_boards  # type: ignore[arg-type]
    )


def _recorte_da_folha(folha: np.ndarray, bloco: object, *, dpi: int) -> np.ndarray | None:
    """O pedaço da folha renderizada em que o bloco está, ou `None` sem `bbox` útil.

    **O bbox do bloco está em pontos e a folha em pixels**, e o fator entre os dois é o DPI com
    que ela foi renderizada. Usar outro aqui recortaria o lugar errado da folha em silêncio.
    Pura, e sem Qt: é a mesma função para a miniatura na tela e para o PNG da exportação.
    """
    bbox = getattr(bloco, "bbox", None)
    if bbox is None:
        return None
    fator = dpi / 72.0
    altura, largura = folha.shape[:2]
    x0 = max(0, int(bbox[0] * fator))
    y0 = max(0, int(bbox[1] * fator))
    x1 = min(largura, int(bbox[2] * fator))
    y1 = min(altura, int(bbox[3] * fator))
    if x1 <= x0 or y1 <= y0:
        return None
    return folha[y0:y1, x0:x1]


def _gravar_recortes(
    doc: rico.DocumentoRico, destino: Path, folha: np.ndarray | None, *, dpi: int
) -> dict[int, Path]:
    """Um PNG por diagrama da folha, ao lado do arquivo, e o mapa que `exportar` quer (S-338).

    `diagramas/` ao lado do destino porque é a pasta que os formatos escrevem no caminho da imagem
    (`Markdown.pasta_de_imagens`). Sem folha renderizada -- documento aberto de arquivo, sem o
    livro na tela -- devolve `{}`, e a marca sai sozinha, como o relatório conta.

    **Roda na thread de trabalho, e por isso nada de Qt aqui**: o recorte é numpy e o PNG é da
    Pillow. O `import` fica fora do laço: ele é o mais caro desta função na primeira vez.
    """
    blocos = [(corrida.bloco, doc.bloco_de(corrida)) for corrida in doc.corridas if corrida.e_diagrama]
    if not blocos:
        return {}
    from PIL import Image

    pasta = destino.parent / "diagramas"
    recortes: dict[int, Path] = {}
    for chave, bloco in blocos:
        if not isinstance(bloco, BlocoDeDiagrama):
            continue
        imagem = _recorte_da_folha(folha, bloco, dpi=dpi) if folha is not None else None
        # Sem folha, o desenho da posição lida (item 7) -- a mesma reserva da miniatura na tela.
        desenho = _png_da_posicao(bloco.placement, lado_px=LADO_DO_RECORTE_DESENHADO) if imagem is None else None
        if imagem is None and desenho is None:
            continue
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            arquivo_png = pasta / f"{destino.stem}_d{bloco.indice + 1}.png"
            if imagem is not None:
                Image.fromarray(np.ascontiguousarray(imagem)).convert("RGB").save(arquivo_png)
            else:
                # Atômica, como toda gravação do projeto (`tests/test_atomic_writes.py`).
                from chess_diagram_ocr.atomic_io import atomic_write_bytes

                atomic_write_bytes(arquivo_png, desenho or b"")
        except Exception as erro:  # noqa: BLE001 - recorte é conforto, e a marca sai sem ele
            logger.debug("Recorte do diagrama %d não gravado: %s", bloco.indice + 1, erro)
            continue
        recortes[chave] = arquivo_png
    return recortes


LADO_DO_RECORTE_DESENHADO = 400
"""O lado, em pixel, do diagrama desenhado da FEN para a exportação: perto do que um recorte a
220 dpi mede, para o `.html` não trocar de escala conforme a origem da figura."""


def _chave_de_livro(caminho: Path | str | None) -> str:
    """A identidade de um livro para a aba: o caminho resolvido, ou `""` sem livro."""
    if not caminho:
        return ""
    try:
        return str(Path(caminho).resolve()).casefold()
    except OSError:  # pragma: no cover - caminho que o sistema recusa resolver
        return str(caminho).casefold()


def _mesmo_livro(um: Path, outro: Path) -> bool:
    """O mesmo PDF apesar da grafia do caminho -- a regra de `qt/dialogos._mesmo`."""
    try:
        return Path(um).resolve() == Path(outro).resolve()
    except OSError:  # pragma: no cover - caminho que o sistema recusa resolver
        return str(um).lower() == str(outro).lower()


def _posicao_de(doc: rico.DocumentoRico, corrida: rico.Corrida) -> str:
    """O campo de peças do bloco desta marca, ou `""` quando ninguém o leu."""
    return str(getattr(doc.bloco_de(corrida), "placement", "") or "")


def _png_da_posicao(placement: str, *, lado_px: int) -> bytes | None:
    """O diagrama desenhado da FEN, em PNG, ou `None` sem posição ou quando o desenho falha.

    Desenha com as peças do próprio programa (`desenho_de_diagrama`, sem Qt): a mesma figura que
    a exportação do livro usa. O `import` é tardio porque ele carrega a Pillow e o conjunto de
    peças, e a aba abre sem precisar deles.
    """
    if not placement:
        return None
    try:
        from chess_diagram_ocr.desenho_de_diagrama import png_do_diagrama

        return png_do_diagrama(placement, lado_px=lado_px)
    except Exception as erro:  # noqa: BLE001 - a figura é conforto; a marca fica
        logger.debug("Diagrama não desenhado da posição %r: %s", placement, erro)
        return None


def _no_catalogo(acao: str) -> bool:
    """Se o catálogo de comandos conhece esta ação. Ver `_botao`."""
    try:
        comandos.rotulo(acao)
    except KeyError:
        return False
    return True


def _url(nome: str):  # noqa: ANN202 - QUrl, importado tarde para o módulo abrir sem QtCore
    from PyQt6.QtCore import QUrl

    return QUrl(nome)


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


def _texto_da_tela(documento: QTextDocument) -> str:
    """O texto do widget **posição por posição**, com as quebras escritas como `\\n`.

    `toRawText` e não `toPlainText`: o segundo troca o espaço inseparável por espaço comum, e a
    letra que a pessoa não tocou sairia trocada no documento. As duas quebras do Qt -- a de
    parágrafo (`Enter`) e a de linha (`Shift+Enter`) -- viram a quebra do documento; todas valem um
    caractere, e é isso que mantém as posições.
    """
    return documento.toRawText().replace("\u2029", "\n").replace("\u2028", "\n")


def _comum_no_comeco(a: str, b: str) -> int:
    """Quantos caracteres do começo `a` e `b` dividem. Busca binária sobre fatias: quem compara é o C."""
    baixo, alto = 0, min(len(a), len(b))
    while baixo < alto:
        meio = (baixo + alto + 1) // 2
        if a[:meio] == b[:meio]:
            baixo = meio
        else:
            alto = meio - 1
    return baixo


def _comum_no_fim(a: str, b: str, limite: int) -> int:
    """Quantos caracteres do fim `a` e `b` dividem, até `limite`."""
    baixo, alto = 0, limite
    while baixo < alto:
        meio = (baixo + alto + 1) // 2
        if a[len(a) - meio :] == b[len(b) - meio :]:
            baixo = meio
        else:
            alto = meio - 1
    return baixo


def _janela_da_troca(antes: str, depois: str) -> tuple[int, int, int] | None:
    """`(início, removidos, acrescidos)` da menor janela que leva `antes` a `depois`; `None` se iguais."""
    if antes == depois:
        return None
    comeco = _comum_no_comeco(antes, depois)
    fim = _comum_no_fim(antes, depois, min(len(antes), len(depois)) - comeco)
    return comeco, len(antes) - comeco - fim, len(depois) - comeco - fim


def _janela_informada(
    antes: str, depois: str, posicao: int, removidos: int, acrescidos: int
) -> tuple[int, int, int] | None:
    """A janela que o Qt anunciou, **se ela bate com os dois textos** -- senão a que os dois dizem.

    Bater é: o que vem antes dela e o que vem depois dela são iguais nos dois textos. É o caso de
    toda tecla medida no Qt 6.11; a conta de reserva existe para a versão que anunciar o documento
    inteiro. `None` quando nenhuma letra mudou -- é a troca de formato, que chega pelo mesmo sinal.
    """
    fim_antes, fim_depois = posicao + removidos, posicao + acrescidos
    if (
        0 <= posicao
        and fim_antes <= len(antes)
        and fim_depois <= len(depois)
        and antes[:posicao] == depois[:posicao]
        and antes[fim_antes:] == depois[fim_depois:]
    ):
        if antes[posicao:fim_antes] == depois[posicao:fim_depois]:
            return None
        return posicao, removidos, acrescidos
    return _janela_da_troca(antes, depois)


def _giro(velho: str, novo: str) -> int:
    """Se `novo` é `velho` girado -- o que um arrasto dentro da mesma janela produz --, de quanto.

    `0` quando não é giro. O espaço inseparável é comparado como espaço: o texto que o `QTextEdit`
    arrasta passa pela área de transferência como texto puro, e ali ele já virou espaço comum.
    """
    if len(velho) != len(novo) or len(velho) < 2 or velho == novo:
        return 0
    a, b = velho.replace("\xa0", " "), novo.replace("\xa0", " ")
    giro = (a + a).find(b)
    return giro if 0 < giro < len(a) else 0


def _corrida_em(doc: rico.DocumentoRico, deslocamento: int) -> rico.Corrida | None:
    """A corrida que contém aquele deslocamento, ou `None` fora do texto."""
    comeco = 0
    for corrida in doc.corridas:
        fim = comeco + len(corrida.texto)
        if comeco <= deslocamento < fim:
            return corrida
        comeco = fim
    return None


class JanelaDeBusca(QDialog):
    """Achar e substituir na folha (S-343).

    **A lista é o item, e não o "próximo".** Uma busca que só anda de ocorrência em ocorrência
    obriga a percorrer o texto para saber quantas há e onde elas estão; a lista responde as duas
    perguntas de uma vez, com o contexto de cada uma -- e é ela que torna a substituição em massa
    conferível antes de acontecer.

    **Quem acha é `text/busca.py`**, que é puro: o padrão, a figurina que casa com a letra, o
    contexto em volta e o bloco de cada ocorrência. Esta janela mostra o que ele devolveu.
    """

    def __init__(self, painel: PainelDeTexto, *, substituindo: bool = False) -> None:
        super().__init__(painel)
        self._painel = painel
        self._achadas: tuple[busca.Ocorrencia, ...] = ()
        self.setWindowTitle("Achar e substituir")
        self.resize(520, 400)

        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        pilha.setSpacing(espaco.folga())

        # **Os dois campos dividem a mesma coluna** (F9-C13, §5.8). Eles não compartilhavam nem a
        # borda esquerda (57 px contra 78) nem a direita (505 contra 396): num formulário de duas
        # linhas, as duas caixas desalinhadas nas duas pontas. A esquerda vem dos dois rótulos
        # com a **mesma** largura; a direita, de uma calha do tamanho do botão reservada na linha
        # de cima -- e ela só existe enquanto a linha de baixo existe, porque alinhar com uma
        # linha escondida seria um buraco no lugar de um alinhamento.
        linha = QHBoxLayout()
        linha.setSpacing(espaco.linha())
        rotulo_de_achar = QLabel("Achar", self)
        linha.addWidget(rotulo_de_achar)
        self.campo_agulha = QLineEdit(self)
        self.campo_agulha.textChanged.connect(lambda _t: self.procurar())
        linha.addWidget(self.campo_agulha, 1)
        self.calha_da_troca = QWidget(self)
        linha.addWidget(self.calha_da_troca)
        pilha.addLayout(linha)

        self.linha_de_troca = QWidget(self)
        troca = QHBoxLayout(self.linha_de_troca)
        troca.setContentsMargins(0, 0, 0, 0)
        troca.setSpacing(espaco.linha())
        rotulo_de_troca = QLabel("Trocar por", self.linha_de_troca)
        troca.addWidget(rotulo_de_troca)
        self.campo_novo = QLineEdit(self.linha_de_troca)
        troca.addWidget(self.campo_novo, 1)
        self.btn_trocar = QPushButton("Substituir todos", self.linha_de_troca)
        self.btn_trocar.clicked.connect(self.substituir_todos)
        tema.aplicar_papel(self.btn_trocar, estilos.NEUTRO)
        troca.addWidget(self.btn_trocar)
        pilha.addWidget(self.linha_de_troca)

        largura_do_rotulo = max(
            rotulo_de_achar.sizeHint().width(), rotulo_de_troca.sizeHint().width()
        )
        for etiqueta in (rotulo_de_achar, rotulo_de_troca):
            etiqueta.setFixedWidth(largura_do_rotulo)
        self.calha_da_troca.setFixedWidth(self.btn_trocar.sizeHint().width())

        opcoes = QHBoxLayout()
        self.caixa_de_caixa = QCheckBox("Diferenciar maiúsculas", self)
        self.caixa_de_figurina = QCheckBox("A letra casa a figurina", self)
        dica_em(
            self.caixa_de_figurina,
            "Procurar «Nf3» acha «♘f3» também: a folha lida traz a figurina, e quem digita\n"
            "a busca tem o teclado.",
        )
        for caixa in (self.caixa_de_caixa, self.caixa_de_figurina):
            caixa.toggled.connect(lambda _ligado: self.procurar())
            opcoes.addWidget(caixa)
        opcoes.addStretch(1)
        pilha.addLayout(opcoes)

        self.lista = QListWidget(self)
        # Sem isto a cascata devolve `"Lista"` -- o eco do papel, que o portão do ciclo 2
        # reprova e que o do ciclo 12 passou a ver porque passou a abrir os diálogos.
        self.lista.setAccessibleName("Ocorrências achadas")
        self.lista.currentRowChanged.connect(self._mostrar)
        pilha.addWidget(self.lista, 1)
        # **O mesmo componente da janela principal** (F9-C14, item 4 do §7 do ciclo 13). A lista
        # abria em branco e a única pista era `Nada achado.` num rótulo abaixo dela.
        self.vazio = EstadoVazio(
            self.lista,
            titulo=strings.BUSCA_SEM_AGULHA_TITULO,
            frase=strings.BUSCA_SEM_AGULHA_FRASE,
        )

        self.lbl_conta = QLabel("", self)
        pilha.addWidget(self.lbl_conta)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)

        self._mostrar_vazio()
        self.mostrar(substituindo=substituindo)

    def showEvent(self, a0: object) -> None:  # noqa: N802 - API do Qt
        """Sincroniza a calha com a largura **de verdade** do botão (F9-C14).

        A calha é medida por `sizeHint()` na montagem, e a escala tipográfica chega depois: o
        filtro de `QEvent.Show` de `qt/acessibilidade` põe o degrau `ACAO` -- peso 600 -- no
        `Substituir todos`, e um botão meio-negrito é 1 px mais largo. Um pixel é pouco e é
        exatamente o tipo de diferença que este item existe para não ter: as duas caixas dividem
        a mesma coluna ou não dividem.

        O filtro da aplicação roda **antes** do `event()` do objeto, então aqui o `sizeHint` já é
        o da fonte final.
        """
        super().showEvent(a0)  # type: ignore[arg-type]
        self.calha_da_troca.setFixedWidth(self.btn_trocar.sizeHint().width())

    def mostrar(self, *, substituindo: bool) -> None:
        """Traz a janela para a frente, com o campo de troca à mostra ou escondido.

        A calha some junto com a linha que ela alinha (F9-C14): sem a segunda caixa não há o que
        alinhar, e uma calha sozinha é um buraco de 100 px à direita do campo `Achar`.
        """
        self.linha_de_troca.setVisible(substituindo)
        self.calha_da_troca.setVisible(substituindo)
        self.show()
        self.raise_()
        self.activateWindow()
        self.campo_agulha.setFocus()

    def procurar(self) -> tuple[busca.Ocorrencia, ...]:
        """Refaz a lista a cada tecla. Agulha vazia devolve vazio, e a lista fica vazia junto."""
        self._achadas = busca.achar(
            self._painel.documento,
            self.campo_agulha.text(),
            casar_figurina=self.caixa_de_figurina.isChecked(),
            diferenciar_caixa=self.caixa_de_caixa.isChecked(),
        )
        self.lista.clear()
        for ocorrencia in self._achadas:
            self.lista.addItem(ocorrencia.contexto)
        self.lbl_conta.setText(
            "Nada achado." if not self._achadas else f"{len(self._achadas)} ocorrência(s)."
        )
        self._mostrar_vazio()
        return self._achadas

    def _mostrar_vazio(self) -> None:
        """O vazio da lista, e **qual** vazio ele é: sem agulha digitada ou sem ocorrência."""
        vista = self.lista.viewport()
        self.vazio.setGeometry(vista.rect() if vista is not None else self.lista.rect())
        procurando = bool(self.campo_agulha.text())
        self.vazio.titulo.setText(
            strings.BUSCA_SEM_ACHADO_TITULO if procurando else strings.BUSCA_SEM_AGULHA_TITULO
        )
        self.vazio.frase.setText(
            strings.BUSCA_SEM_ACHADO_FRASE if procurando else strings.BUSCA_SEM_AGULHA_FRASE
        )
        self.vazio.setVisible(not self._achadas)

    def _mostrar(self, linha: int) -> None:
        if 0 <= linha < len(self._achadas):
            achada = self._achadas[linha]
            self._painel.mostrar_intervalo(achada.inicio, achada.fim)

    def substituir_todos(self) -> None:
        """Troca **todas** as achadas de uma vez, e diz quantas foram.

        Uma só chamada, e não uma por ocorrência: a substituição inteira entra na pilha como um
        passo, e `Ctrl+Z` reverte a troca toda -- e não troca a troca.
        """
        if not self._achadas:
            self._painel.estado.emit("Não há ocorrência para substituir.")
            return
        trocadas = self._painel.aplicar_substituicao(self._achadas, self.campo_novo.text())
        self._painel.estado.emit(f"{trocadas} ocorrência(s) substituída(s).")
        self.procurar()
