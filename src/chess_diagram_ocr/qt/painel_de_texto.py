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
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut, QTextCursor, QTextDocument
from PyQt6.QtWidgets import (
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
from chess_diagram_ocr.text import busca, rico
from chess_diagram_ocr.text.documento import PaginaLida
from chess_diagram_ocr.ui import atalhos, comandos, espaco, estilos, texto_cores, tokens
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.texto_declarado import (
    ACOES_PROPRIAS,
    COMANDOS_DA_ABA,
    MOTORES,
    ZOOM_MAXIMO,
    ZOOM_MINIMO,
    fora_do_livro,
)

logger = logging.getLogger(__name__)

__all__ = ["LARGURA_DA_MINIATURA", "JanelaDeBusca", "PainelDeTexto"]

LARGURA_DA_MINIATURA = 160
"""A miniatura do diagrama dentro do texto, em pixel.

Grande o bastante para reconhecer a posição, pequena o bastante para a linha seguinte caber na
tela. É o mesmo alvo de `texto_panel._miniatura`."""


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


class PainelDeTexto(QWidget):
    """O editor da página lida: desenha o documento e devolve cada gesto a `text/rico.py`."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status."""

    documento_mudou = pyqtSignal()
    """A folha foi editada. A janela usa para saber que há o que gravar."""

    def __init__(
        self,
        *,
        pdf: Path | None = None,
        pagina: int = 0,
        dpi: int = 220,
        busy: BusyRegistry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._busy = busy
        """O registro de ocupação (S-112). `None` é a aba montada sozinha num teste.

        **As duas operações longas desta aba precisam estar nele**, e no corte do Tk elas quase
        não ficaram: o painel de lá registrava as duas, e o porte inicial não. Ler uma folha é
        dezenas de segundos com o motor glifo, e exportar um PDF pesquisável abre o livro inteiro
        -- fechar a janela no meio de qualquer uma delas joga fora trabalho que não volta de
        graça, e o rodapé só sabe perguntar sobre o que está registrado."""
        self._ocupado: BusyToken | None = None
        self._pdf = pdf
        self._pagina_indice = pagina
        self._dpi = dpi
        self._pagina: PaginaLida | None = None
        self._pagina_rgb: np.ndarray | None = None

        self.documento = rico.DocumentoRico()
        """**O estado é o documento, e não o widget.** É a diferença de fundo com o lado do Tk,
        onde gravar exigia reler o `dump` do editor etiqueta por etiqueta (`de_despejo`)."""
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

        self._montar()
        self._desenhar()
        atalhos.conferir_dono(self, "PainelDeTexto")

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        caixa = QVBoxLayout(self)
        caixa.setContentsMargins(*(espaco.folga(),) * 4)
        caixa.setSpacing(espaco.linha())
        caixa.addWidget(self._barra_de_ferramentas())

        self.editor = QTextEdit(self)
        self._corpo_de_base = self.editor.font().pointSize()
        """O corpo da fonte antes de qualquer zoom da vista. `aplicar_zoom` soma o degrau **a
        ele**, e não ao que está na tela -- somar ao desenhado acumularia o degrau anterior a cada
        chamada, e a letra cresceria sozinha."""
        self.editor.setAcceptRichText(False)
        self.editor.setUndoRedoEnabled(False)
        """**O desfazer do Qt fica desligado de propósito.** A pilha deste painel é de
        *documentos* (`rico.DocumentoRico`), e não de edições de texto: uma ferramenta de formato
        não muda um caractere, e o desfazer nativo não a veria. Duas pilhas dariam um `Ctrl+Z` que
        às vezes desfaz o negrito e às vezes a palavra."""
        self._ligar_teclas_do_editor()
        corpo = QHBoxLayout()
        corpo.addWidget(self.editor, 1)
        corpo.addWidget(self._montar_paleta())
        caixa.addLayout(corpo, 1)

        self.status = QLabel("", self)
        caixa.addWidget(self.status)

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
        for acao, sequencia in atalhos.TECLAS_DO_EDITOR.items():
            atalho = QShortcut(QKeySequence(qt_atalhos.sequencia_qt(sequencia)), self.editor)
            atalho.setContext(Qt.ShortcutContext.WidgetShortcut)
            atalho.activated.connect(partial(self.executar, acao))

    def _montar_paleta(self) -> QListWidget:
        """O painel lateral de glifos (S-248). Nasce escondido: ele é um caminho a mais.

        Uma lista e não uma grade de botões: os glifos são muitos, a lista rola, e clicar num item
        é o mesmo gesto que clicar num botão -- com a diferença de que a lista não precisa de uma
        decisão de quantas colunas.
        """
        from chess_diagram_ocr.text import paleta as _paleta

        self.paleta_lateral = QListWidget(self)
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
        self.escolha_de_estilo.addItem("(sem estilo)", "")
        for estilo in rico.ESTILOS:
            self.escolha_de_estilo.addItem(estilo.capitalize(), estilo)
        self.escolha_de_estilo.activated.connect(
            lambda _i: self.aplicar_estilo(str(self.escolha_de_estilo.currentData()))
        )
        dica_em(self.escolha_de_estilo, "O estilo do parágrafo inteiro, e não do trecho selecionado.")
        barra.adicionar(self.escolha_de_estilo)

        self.escolha_de_cor = QComboBox(barra)
        self.escolha_de_cor.addItem("(sem cor)", "")
        for nome in texto_cores.nomes():
            self.escolha_de_cor.addItem(nome.capitalize(), nome)
        self.escolha_de_cor.activated.connect(
            lambda _i: self.pintar_letra(str(self.escolha_de_cor.currentData()))
        )
        barra.adicionar(self.escolha_de_cor)

        self.escolha_de_realce = QComboBox(barra)
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
        self.campo_de_folha.setMinimum(1)
        self.campo_de_folha.setMaximum(9999)
        self.campo_de_folha.setValue(self._pagina_indice + 1)
        barra.adicionar(self.campo_de_folha)

        self.escolha_de_motor = QComboBox(barra)
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
        botao.clicked.connect(lambda _marcado=False: alvo())
        tema.aplicar_papel(botao, estilos.NEUTRO)
        motivo = comandos.rotulo(acao) if _no_catalogo(acao) else rotulo
        tecla = atalhos.acelerador(acao)
        dica_em(botao, f"{motivo}\nTecla: {tecla}" if tecla else motivo)
        barra.adicionar(botao)
        return botao

    # ------------------------------------------------------------------------------ desenho

    def desenhar_documento(self, doc: rico.DocumentoRico) -> None:
        """Troca o documento e o desenha. **Este laço não decide nada.**

        Faixa, ordem, separador e atributo já vieram decididos por `text/rico.py`; o que sobra
        aqui é escrever no cursor e pôr a miniatura. É a mesma fronteira do outro frontend.
        """
        self.documento = doc
        self._desenhar()
        self.documento_mudou.emit()

    def _desenhar(self) -> None:
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
            base = tema.fonte_base()
            deslocamento = 0

            for corrida in self.documento.corridas:
                if corrida.e_diagrama:
                    self._inserir_miniatura(cursor, corrida)
                cursor.setBlockFormat(bloco_de(corrida.atributos, base=base))
                inicio = cursor.position()
                cursor.insertText(corrida.texto, formato_de(corrida, base=base))
                self._mapa.registrar(deslocamento, inicio, len(corrida.texto))
                deslocamento += len(corrida.texto)

            self.editor.setDocument(documento)
        finally:
            self._redesenhando = False

    def _inserir_miniatura(self, cursor: QTextCursor, corrida: rico.Corrida) -> None:
        """A imagem do diagrama, **antes** da marca -- e a marca continua no texto.

        Parece redundante numa tela onde a imagem já aparece, e é o contrário: a imagem é do
        widget e morre com ele, a marca é do texto e sobrevive a salvar, copiar e colar. Um
        editor que trocasse a marca pela imagem perderia o diagrama na primeira exportação.

        A imagem **não** entra no mapa: ela não é do documento, e é justamente por isso que
        `_Mapa` existe.
        """
        recorte = self._recorte(corrida)
        if recorte is None:
            return
        mapa = pixmap_de_rgb(recorte).scaledToWidth(
            LARGURA_DA_MINIATURA, Qt.TransformationMode.SmoothTransformation
        )
        nome = f"diagrama:{corrida.bloco}"
        documento = cursor.document()
        if documento is not None:
            documento.addResource(QTextDocument.ResourceType.ImageResource.value, _url(nome), mapa)
        cursor.insertImage(nome)
        cursor.insertBlock()

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
        bloco = self.documento.bloco_de(corrida)
        bbox = getattr(bloco, "bbox", None)
        if bbox is None:
            return None
        fator = self._dpi / 72.0
        altura, largura = self._pagina_rgb.shape[:2]
        x0 = max(0, int(bbox[0] * fator))
        y0 = max(0, int(bbox[1] * fator))
        x1 = min(largura, int(bbox[2] * fator))
        y1 = min(altura, int(bbox[3] * fator))
        if x1 <= x0 or y1 <= y0:
            return None
        return self._pagina_rgb[y0:y1, x0:x1]

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

    def _aplicar(self, novo: rico.DocumentoRico) -> None:
        """Guarda o documento anterior na pilha e desenha o novo.

        A pilha é de **documentos**, e é o que faz `Ctrl+Z` desfazer um negrito -- que não muda
        caractere nenhum e que uma pilha de texto não veria.
        """
        if novo is self.documento:
            return
        self._historico.append(self.documento)
        # O contador que decide o `Ctrl+Z` quando o foco não está em desfazível nenhum (S-243).
        self._edicao += 1
        self._refeitos.clear()
        self.desenhar_documento(novo)

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
        """`Ctrl+Z`: devolve o documento anterior."""
        if not self._historico:
            self.estado.emit("Não há mudança anterior nesta folha para desfazer.")
            return
        self._refeitos.append(self.documento)
        self.desenhar_documento(self._historico.pop())

    def refazer(self) -> None:
        """`Ctrl+Y`: repõe o que o desfazer tirou."""
        if not self._refeitos:
            self.estado.emit("Não há o que refazer: nada foi desfeito.")
            return
        self._historico.append(self.documento)
        self.desenhar_documento(self._refeitos.pop())

    @property
    def pode_desfazer(self) -> bool:
        return bool(self._historico)

    @property
    def pode_refazer(self) -> bool:
        return bool(self._refeitos)

    # -------------------------------------------------------------------------------- carga

    def mostrar_pagina(self, pagina: PaginaLida, *, folha_rgb: np.ndarray | None = None) -> None:
        """Abre uma `PaginaLida` no editor. É o que a leitura entrega."""
        self._pagina = pagina
        self._pagina_rgb = folha_rgb
        self._historico.clear()
        self._refeitos.clear()
        self.desenhar_documento(rico.de_pagina(pagina))

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
        fonte = self.editor.font()
        fonte.setPointSize(tipografia.corpo(degraus, base=self._corpo_de_base))
        self.editor.setFont(fonte)
        self._desenhar()
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
        self._aplicar(rico.inserir(self.documento, inicio, simbolo, fora_do_modelo=fora))
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
        self._historico.clear()
        self._refeitos.clear()
        self.desenhar_documento(doc)
        self._caminho_do_documento = Path(origem)  # `Salvar` grava de volta aqui (S-343)

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
        try:
            arquivo.gravar(caminho, self.documento)
        except OSError as erro:
            QMessageBox.critical(self, "Texto", f"Não foi possível gravar:\n{erro}")
            return
        self._caminho_do_documento = caminho
        self.estado.emit(f"Texto gravado em {caminho.name}.")

    def _confirmar_descarte(self, o_que: str) -> bool:
        """Pergunta antes de jogar fora o que foi editado. Sem edição, não pergunta."""
        if not self._historico:
            return True
        caixa = QMessageBox(self)
        caixa.setIcon(QMessageBox.Icon.Question)
        caixa.setWindowTitle("Texto")
        caixa.setText(f"O texto desta aba foi editado. {o_que} Continuar?")
        caixa.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        caixa.setDefaultButton(QMessageBox.StandardButton.No)
        return caixa.exec() == QMessageBox.StandardButton.Yes


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
        doc = self.documento

        def _trabalho() -> str:
            relatorio = exportacao.exportar(doc, formato)
            exportacao.escrever(caminho, relatorio)
            return exportacao.texto_do_relatorio(
                caminho, relatorio, tamanho=caminho.stat().st_size
            )

        self.estado.emit(f"Exportando para {caminho.name}...")
        # `loses_work=True`: o arquivo de destino fica pela metade se a janela fechar no meio,
        # e um `.pdf` pesquisável truncado é pior que nenhum -- ele abre e mente.
        self._registrar_ocupado(f"Exportando para {formato.nome}", loses_work=True, detail=caminho.name)
        self._tarefa = Tarefa(_trabalho, parent=self)
        self._tarefa.pronto.connect(self._exportacao_terminou)
        self._tarefa.falhou.connect(self._exportacao_falhou)
        self._tarefa.finished.connect(self._soltar_ocupado)
        self._tarefa.start()

    def _registrar_ocupado(self, nome: str, *, loses_work: bool, detail: str = "") -> None:
        """Põe a operação no registro, se a janela deu um. Ver o campo `_busy`."""
        if self._busy is None:
            return
        self._ocupado = self._busy.register(nome, loses_work=loses_work, detail=detail)

    def _soltar_ocupado(self) -> None:
        """**Sai do registro sempre**, e por isso está no `finished` e não no `pronto` (S-112).

        Um `BusyToken` que ficasse pendurado numa falha faria a janela perguntar "fechar mesmo
        assim?" para sempre, sobre uma operação que já acabou."""
        if self._ocupado is not None:
            self._ocupado.release()
            self._ocupado = None

    def _exportacao_terminou(self, frase: object) -> None:
        self._tarefa = None
        self.estado.emit(str(frase))

    def _exportacao_falhou(self, erro: str) -> None:
        self._tarefa = None
        QMessageBox.critical(self, "Exportar", f"Falha ao exportar:\n{erro}")

    # ---------------------------------------------------------- a leitura, em thread

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

        indice = int(self.campo_de_folha.value()) - 1
        motor = self._motor
        bloco = self._modo_bloco
        caminho = self._pdf
        dpi = self._dpi

        def _trabalho() -> PaginaLida:
            from chess_diagram_ocr.text.leitor import ler_pagina

            return ler_pagina(caminho, indice, dpi=dpi, motor=motor, modo_bloco=bloco)

        self.estado.emit(f"Lendo a folha {indice + 1}...")
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

    def _leitura_terminou(self, pagina: object) -> None:
        self._tarefa = None
        assert isinstance(pagina, PaginaLida)
        self._pagina_indice = int(self.campo_de_folha.value()) - 1
        self.mostrar_pagina(pagina)
        self.estado.emit(f"Folha lida: {len(self.documento.corridas)} trecho(s).")

    def _leitura_falhou(self, erro: str) -> None:
        self._tarefa = None
        QMessageBox.critical(self, "Ler a folha", f"Não foi possível ler a folha:\n{erro}")

    # ------------------------------------------------------ o que a janela pergunta (S-283)

    def definir_livro(self, pdf: Path | None, *, pagina: int | None = None) -> None:
        """Diz à aba qual livro está aberto e em que folha o visualizador está.

        **A folha lida não cai junto**, e é de propósito: trocar de livro com uma folha corrigida
        na tela e ainda por gravar jogaria fora o trabalho sem perguntar. Quem descarta é `ler`,
        que pergunta antes.
        """
        self._pdf = None if pdf is None else Path(pdf)
        if pagina is not None:
            self._pagina_indice = int(pagina)
            self._montando = True
            try:
                self.campo_de_folha.setValue(self._pagina_indice + 1)
            finally:
                self._montando = False

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

    # ------------------------------------------------------------------------------ teclado

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

        linha = QHBoxLayout()
        linha.addWidget(QLabel("Achar", self))
        self.campo_agulha = QLineEdit(self)
        self.campo_agulha.textChanged.connect(lambda _t: self.procurar())
        linha.addWidget(self.campo_agulha, 1)
        pilha.addLayout(linha)

        self.linha_de_troca = QWidget(self)
        troca = QHBoxLayout(self.linha_de_troca)
        troca.setContentsMargins(0, 0, 0, 0)
        troca.addWidget(QLabel("Trocar por", self.linha_de_troca))
        self.campo_novo = QLineEdit(self.linha_de_troca)
        troca.addWidget(self.campo_novo, 1)
        self.btn_trocar = QPushButton("Substituir todos", self.linha_de_troca)
        self.btn_trocar.clicked.connect(self.substituir_todos)
        tema.aplicar_papel(self.btn_trocar, estilos.NEUTRO)
        troca.addWidget(self.btn_trocar)
        pilha.addWidget(self.linha_de_troca)

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
        self.lista.currentRowChanged.connect(self._mostrar)
        pilha.addWidget(self.lista, 1)

        self.lbl_conta = QLabel("", self)
        pilha.addWidget(self.lbl_conta)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)

        self.mostrar(substituindo=substituindo)

    def mostrar(self, *, substituindo: bool) -> None:
        """Traz a janela para a frente, com o campo de troca à mostra ou escondido."""
        self.linha_de_troca.setVisible(substituindo)
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
        return self._achadas

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
