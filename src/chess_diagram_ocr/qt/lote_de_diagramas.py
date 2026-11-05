"""O diálogo do lote de diagramas: as escolhas, a prévia, a pasta e a thread (S-544).

**O que ele não decide.** Formato, tamanho, pele, conjunto, o que o lote contém e como cada arquivo
se chama são de `ui/lote_de_diagramas.py`; gravar é de `diagramas_em_lote.py`. Aqui há widget,
sinal e thread -- a mesma fronteira de `qt/fila_de_livros.py`.

**A prévia desenha com as opções correntes, e num tamanho fixo.** Ela responde "que figura vai
sair", e não "de que tamanho": renderizar 2.400 pixels a cada clique numa caixa de marcar tornaria
a janela lenta para responder à pergunta errada. O tamanho está escrito por extenso logo abaixo,
com o **lado real** -- que difere do pedido por até quatro pixels, porque as oito casas têm de ter
o mesmo número inteiro de pixels (ver `Opcoes.casa_px`).

**A prévia é do formato escolhido, e não sempre um PNG.** O SVG é desenhado pelo `QSvgRenderer`, o
mesmo caminho por que o PDF da S-545 põe o diagrama em vetor: se a prévia fosse sempre bitmap, o
SVG seria o único artefato do programa que ninguém olha antes de gravar quinhentos deles.

**Cancelar responde entre arquivos.** Um diagrama leva milissegundos, então "entre arquivos" é
imediato para quem clicou -- e é o que permite ao teste exigir a parada em menos de um segundo e
meio com a thread já morta.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.diagramas_em_lote import RelatorioDoLote, bytes_do_item, frase_do_relatorio, gravar_lote
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.ui import conjuntos, estilos
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.lote_de_diagramas import (
    FORMATOS,
    MARGEM_MAXIMA,
    MARGEM_PADRAO,
    PELES_DO_DIAGRAMA,
    SVG,
    TAMANHO_MAXIMO,
    TAMANHO_MINIMO,
    TAMANHO_PADRAO,
    TAMANHOS,
    ItemDoLote,
    Opcoes,
    frase_do_lote,
)

logger = logging.getLogger(__name__)

__all__ = ["DialogoDoLote", "ExportacaoDoLote", "abrir_lote_de_diagramas"]

LADO_DA_PREVIA = 220
"""O lado da prévia, em pixel. Ver o cabeçalho: ela mostra a figura, e não o tamanho."""

POR_MIL = 1000
"""A escala da barra, como em `qt/fila_de_livros.py`: mil passos andam sem saltar num lote de
centenas e cabem num `int` de `QProgressBar` sem conversão."""


class ExportacaoDoLote(QObject):
    """Grava o lote numa thread e conta o andamento por sinal.

    Os avisos de progresso vêm **de dentro da thread** e só emitem; quem toca widget é o slot do
    outro lado. É a forma de `qt/fila_de_livros.VarreduraDeLivros`, e pela mesma razão: tocar
    widget da thread de trabalho derruba o processo sem exceção.
    """

    andou = pyqtSignal(int, int, str)
    terminou = pyqtSignal(object)
    falhou = pyqtSignal(str, object)

    mudou = pyqtSignal()
    """"Alguma coisa mudou, redesenhe" -- e é emitido **depois** de a thread ser solta.

    `terminou` chega antes disso: ele vem do `pronto` da `Tarefa`, e ali `_tarefa` ainda não é
    `None`. Um diálogo que redesenhasse só com ele leria `ocupado` verdadeiro e deixaria o botão
    Exportar cinza para sempre. É a mesma razão do `mudou` de `qt/fila_de_livros.py`."""

    def __init__(self, parent: QObject | None = None, *, busy: BusyRegistry | None = None) -> None:
        super().__init__(parent)
        self._tarefa: Tarefa | None = None
        self._cancelar = threading.Event()
        self._busy = busy
        self._token: BusyToken | None = None
        self.relatorio: RelatorioDoLote | None = None

    @property
    def ocupado(self) -> bool:
        return self._tarefa is not None

    def iniciar(self, itens: Sequence[ItemDoLote], opcoes: Opcoes, pasta: Path) -> bool:
        """Começa a gravação. Falso se já há uma em curso, ou se não há diagrama nenhum."""
        if self._tarefa is not None or not itens:
            return False
        self._cancelar = threading.Event()
        self.relatorio = None
        cancelar = self._cancelar
        lote, escolhas, destino = tuple(itens), opcoes, Path(pasta)

        def _trabalho() -> RelatorioDoLote:
            return gravar_lote(lote, escolhas, destino, cancelar=cancelar, progresso=self._relatar)

        tarefa = Tarefa(_trabalho, parent=self, nome="lote de diagramas")
        tarefa.pronto.connect(self._pronto)
        tarefa.falhou.connect(self._deu_errado)
        tarefa.finished.connect(self._acabou)
        self._registrar_ocupado(len(lote))
        self._tarefa = tarefa
        tarefa.start()
        return True

    def cancelar(self) -> None:
        """Pede parada. O arquivo em curso termina, e o que já saiu fica gravado."""
        self._cancelar.set()

    def esperar(self, espera_ms: int) -> bool:
        """Espera a gravação em curso. Devolve se ela terminou."""
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(espera_ms))

    def _relatar(self, feitos: int, total: int, nome: str) -> None:
        """Chamado **na thread de trabalho** por `gravar_lote`. Só emite."""
        if self._token is not None:
            # O `BusyRegistry` tem lock próprio, e é para isto que ele existe (S-164).
            self._token.update(f"{feitos} de {total}", feito=feitos, total=total)
        self.andou.emit(feitos, total, nome)

    def _pronto(self, relatorio: Any) -> None:
        self.relatorio = relatorio if isinstance(relatorio, RelatorioDoLote) else None
        self.terminou.emit(relatorio)

    def _deu_errado(self, mensagem: str, excecao: object) -> None:
        logger.warning("O lote de diagramas falhou: %s", mensagem)
        self.falhou.emit(mensagem, excecao)

    def _acabou(self) -> None:
        self._soltar_ocupado()
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.deleteLater()
        self.mudou.emit()

    def _registrar_ocupado(self, quantos: int) -> None:
        if self._busy is None:
            return
        self._token = self._busy.register(
            "lote de diagramas",
            # Cada arquivo pronto está no disco: fechar custa o que falta, não o que já saiu.
            loses_work=False,
            cancellable=True,
            detail=f"{quantos} diagrama(s)",
            total=quantos,
            cancel=self.cancelar,
        )

    def _soltar_ocupado(self) -> None:
        if self._token is not None:
            self._token.release()
            self._token = None


def previa(item: ItemDoLote, opcoes: Opcoes, lado: int = LADO_DA_PREVIA) -> QPixmap:
    """O diagrama daquele item, com aquelas opções, num quadrado de `lado` pixels.

    **Desenhado no tamanho da prévia, e não reduzido do tamanho final.** As duas coisas diferem
    exatamente onde a escolha importa: o conjunto de traço grosso existe para a peça **reduzida**
    (S-230), e uma prévia que encolhesse um PNG de 2.400 px mostraria a peça fina que o arquivo
    grande vai ter, não a que a tela está prometendo.

    O piso é `TAMANHO_MINIMO`, e não o do tabuleiro: `Opcoes` recusa o que está fora da faixa, e
    uma prévia menor que o mínimo levantaria em vez de desenhar pequeno. Abaixo dele o quadrado
    ainda encolhe -- o que muda é que a figura é desenhada em 120 px e reduzida a partir dali.
    """
    escolhas = replace(opcoes, tamanho=max(lado, TAMANHO_MINIMO))
    dados = bytes_do_item(item, escolhas)
    if escolhas.formato == SVG:
        imagem = QImage(lado, lado, QImage.Format.Format_ARGB32_Premultiplied)
        imagem.fill(Qt.GlobalColor.transparent)
        pintor = QPainter(imagem)
        QSvgRenderer(dados).render(pintor)
        pintor.end()
        return QPixmap.fromImage(imagem)
    mapa = QPixmap()
    mapa.loadFromData(dados, "PNG")
    return mapa.scaled(
        lado,
        lado,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class DialogoDoLote(QDialog):
    """As escolhas do lote, a prévia, a pasta de destino e a barra.

    Não é modal à aplicação: um lote de quinhentos diagramas é o que se deixa gravando enquanto se
    faz outra coisa (S-164). Fechar não para a gravação -- **Cancelar** é que para --, e por isso
    ele não é `WA_DeleteOnClose`: uma thread destruída rodando derruba o processo.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        itens: Sequence[ItemDoLote] = (),
        origem: str = "",
        pasta: Path | None = None,
        exportacao: ExportacaoDoLote | None = None,
    ) -> None:
        super().__init__(parent)
        self.itens = tuple(itens)
        self.exportacao = exportacao or ExportacaoDoLote(self)
        self._pasta = Path(pasta) if pasta is not None else Path.cwd()
        self._recado = ""
        """A frase de fim ou de falha, guardada e não escrita direto: o `finished` da tarefa chega
        depois e redesenharia por cima. É a regra de `DialogoDaFila._parada`."""

        self.setWindowTitle("Exportar os diagramas em lote")
        self.setMinimumWidth(620)

        fora = QVBoxLayout(self)
        self.lbl_origem = QLabel(origem or "Diagramas escolhidos", self)
        self.lbl_origem.setWordWrap(True)
        fora.addWidget(self.lbl_origem)

        # **O formulário tem teto de largura, e o resto do corpo é ar à direita.** Sete campos de
        # escolha esticados por uma janela larga viram sete caixas de mil pixels para guardar
        # "PNG" -- e a prévia, que é o que se olha, encolhe no canto. O teto é o dobro da prévia:
        # cabe "Coordenadas (a–h, 8–1)" sem quebrar e ainda deixa a figura ao lado dela.
        corpo = QHBoxLayout()
        formulario = QWidget(self)
        formulario.setLayout(self._formulario())
        formulario.setMaximumWidth(2 * LADO_DA_PREVIA + 100)
        corpo.addWidget(formulario, 0, Qt.AlignmentFlag.AlignTop)
        self.lbl_previa = QLabel(self)
        self.lbl_previa.setFixedSize(LADO_DA_PREVIA, LADO_DA_PREVIA)
        self.lbl_previa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        corpo.addWidget(self.lbl_previa, 0, Qt.AlignmentFlag.AlignTop)
        corpo.addStretch(1)
        fora.addLayout(corpo)
        # O que sobra de altura fica **entre** as escolhas e o rodapé: a barra e o resumo andam
        # com os botões, que é onde se olha depois de clicar em Exportar.
        fora.addStretch(1)

        self.lbl_resumo = QLabel("", self)
        self.lbl_resumo.setWordWrap(True)
        self.lbl_resumo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fora.addWidget(self.lbl_resumo)

        self.barra = QProgressBar(self)
        self.barra.setRange(0, POR_MIL)
        self.barra.setFormat("%p% do lote")
        fora.addWidget(self.barra)

        linha = QHBoxLayout()
        self.botao_pasta = QPushButton("Escolher a pasta…", self)
        self.botao_exportar = QPushButton("Exportar", self)
        self.botao_cancelar = QPushButton("Cancelar", self)
        self.botao_fechar = QPushButton("Fechar", self)
        papeis = [estilos.NEUTRO, estilos.PRIMARIO, estilos.NEUTRO, estilos.NEUTRO]
        for botao, papel in zip(
            (self.botao_pasta, self.botao_exportar, self.botao_cancelar, self.botao_fechar), papeis, strict=True
        ):
            tema.aplicar_papel(botao, papel)
            linha.addWidget(botao)
        estilos.conferir_barra(papeis, onde="o lote de diagramas")
        linha.addStretch(1)
        fora.addLayout(linha)

        self.botao_pasta.clicked.connect(self.escolher_pasta)
        self.botao_exportar.clicked.connect(self.exportar)
        self.botao_cancelar.clicked.connect(self.exportacao.cancelar)
        self.botao_fechar.clicked.connect(self.close)
        self.exportacao.andou.connect(self._andou)
        self.exportacao.terminou.connect(self._terminou)
        self.exportacao.falhou.connect(self._falhou)
        self.exportacao.mudou.connect(self.redesenhar)
        self.redesenhar()

    # ------------------------------------------------------------------------ a montagem

    def _formulario(self) -> QFormLayout:
        formulario = QFormLayout()
        self.cmb_formato = QComboBox(self)
        for registro in FORMATOS:
            self.cmb_formato.addItem(registro.rotulo, registro.nome)
        # Editável, e é o que `TAMANHOS` sempre declarou: "os tamanhos oferecidos na escolha, que
        # continua aceitando qualquer valor da faixa". Uma caixa fechada em oito valores fazia a
        # declaração mentir -- e o tamanho é justamente a escolha que depende da diagramação de
        # quem exporta, não da nossa lista. `tamanho_pedido` apara o digitado contra a faixa.
        self.cmb_tamanho = QComboBox(self)
        self.cmb_tamanho.setEditable(True)
        self.cmb_tamanho.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for tamanho in TAMANHOS:
            self.cmb_tamanho.addItem(f"{tamanho} px", tamanho)
        self.cmb_tamanho.setCurrentIndex([*TAMANHOS].index(TAMANHO_PADRAO))
        self.cmb_pele = QComboBox(self)
        for registro_de_pele in PELES_DO_DIAGRAMA:
            self.cmb_pele.addItem(registro_de_pele.rotulo, registro_de_pele.nome)
        self.cmb_conjunto = QComboBox(self)
        for conjunto in conjuntos.CONJUNTOS:
            self.cmb_conjunto.addItem(conjunto.rotulo, conjunto.nome)
        # O conjunto em vigor na janela, e não o padrão: quem trocou as peças da tela quer as
        # mesmas peças no arquivo, e reoferecer o padrão faria a exportação discordar do que está
        # sendo olhado. Ver `qt/tabuleiro.conjunto_em_vigor`.
        self.cmb_conjunto.setCurrentIndex(max(0, self.cmb_conjunto.findData(qt_conjunto_em_vigor())))
        self.chk_coordenadas = QCheckBox("Coordenadas (a–h, 8–1)", self)
        self.chk_coordenadas.setChecked(True)
        self.chk_plaqueta = QCheckBox("Marca de quem joga", self)
        self.chk_plaqueta.setChecked(True)
        self.spn_margem = QSpinBox(self)
        self.spn_margem.setRange(0, MARGEM_MAXIMA)
        self.spn_margem.setValue(MARGEM_PADRAO)
        self.spn_margem.setSuffix(" % da casa")
        self.lbl_pasta = QLabel(str(self._pasta), self)
        self.lbl_pasta.setWordWrap(True)

        formulario.addRow("Formato", self.cmb_formato)
        formulario.addRow("Tamanho", self.cmb_tamanho)
        formulario.addRow("Pele", self.cmb_pele)
        formulario.addRow("Peças", self.cmb_conjunto)
        formulario.addRow("Moldura", self.spn_margem)
        formulario.addRow("", self.chk_coordenadas)
        formulario.addRow("", self.chk_plaqueta)
        formulario.addRow("Pasta", self.lbl_pasta)

        for caixa in (self.cmb_formato, self.cmb_tamanho, self.cmb_pele, self.cmb_conjunto):
            caixa.currentIndexChanged.connect(self.redesenhar)
        # A caixa de tamanho é editável: o índice não muda quando se digita, e sem o
        # `editTextChanged` a prévia continuaria mostrando o tamanho anterior.
        self.cmb_tamanho.editTextChanged.connect(self.redesenhar)
        for marca in (self.chk_coordenadas, self.chk_plaqueta):
            marca.toggled.connect(self.redesenhar)
        self.spn_margem.valueChanged.connect(self.redesenhar)
        return formulario

    # -------------------------------------------------------------------------- as escolhas

    def tamanho_pedido(self) -> int:
        """O lado pedido, **aparado na faixa** -- o digitado pode ser qualquer coisa (S-544).

        Aparar e não recusar: quem digita `40000` quer o maior que houver, e uma caixa vermelha
        no meio de sete escolhas para dizer "no máximo 4000" interrompe o gesto para informar o
        que o próprio campo pode simplesmente entregar. Texto sem número nenhum volta ao padrão.
        """
        texto = "".join(letra for letra in self.cmb_tamanho.currentText() if letra.isdigit())
        pedido = int(texto) if texto else TAMANHO_PADRAO
        return max(TAMANHO_MINIMO, min(TAMANHO_MAXIMO, pedido))

    def opcoes(self) -> Opcoes:
        """As escolhas correntes. `Opcoes` valida na construção, e a tela só oferece o válido."""
        return Opcoes(
            formato=str(self.cmb_formato.currentData()),
            tamanho=self.tamanho_pedido(),
            pele=str(self.cmb_pele.currentData()),
            conjunto=str(self.cmb_conjunto.currentData()),
            pasta_de_pecas=qt_pasta_de_pecas(),
            coordenadas=self.chk_coordenadas.isChecked(),
            plaqueta=self.chk_plaqueta.isChecked(),
            margem=self.spn_margem.value(),
        )

    def escolher_pasta(self) -> Path | None:
        """Pergunta onde gravar. `None` se a pessoa desistir."""
        nome = QFileDialog.getExistingDirectory(self, "Pasta do lote de diagramas", str(self._pasta))
        if not nome:
            return None
        self._pasta = Path(nome)
        self.redesenhar()
        return self._pasta

    def exportar(self) -> bool:
        """Começa a gravação com as escolhas correntes. Falso quando não há o que gravar."""
        comecou = self.exportacao.iniciar(self.itens, self.opcoes(), self._pasta)
        if comecou:
            self._recado = ""
            self.barra.setValue(0)
            self.redesenhar()
        return comecou

    # ----------------------------------------------------------------------------- o desenho

    def redesenhar(self) -> None:
        """Reescreve a prévia, o resumo, a pasta, a barra e o que está ligado."""
        escolhas = self.opcoes()
        self.lbl_pasta.setText(str(self._pasta))
        self.cmb_conjunto.setEnabled(escolhas.formato != SVG)
        partes = [self._recado, frase_do_lote(self.itens, escolhas)]
        if escolhas.formato == SVG:
            # O SVG desenha as peças do `python-chess`, que são caminho: o conjunto de peças de
            # `assets/` não entra nele, e dizê-lo é melhor que desabilitar a caixa em silêncio.
            partes.append("O SVG usa as peças vetoriais do formato; o conjunto vale para o PNG.")
        self.lbl_resumo.setText(" ".join(parte for parte in partes if parte))
        self._pintar_previa(escolhas)
        rodando = self.exportacao.ocupado
        self.botao_exportar.setEnabled(not rodando and bool(self.itens))
        self.botao_cancelar.setEnabled(rodando)
        self.botao_pasta.setEnabled(not rodando)

    def _pintar_previa(self, escolhas: Opcoes) -> None:
        if not self.itens:
            self.lbl_previa.setText("Sem diagrama")
            return
        try:
            self.lbl_previa.setPixmap(previa(self.itens[0], escolhas))
        except Exception as erro:  # noqa: BLE001 - a prévia não pode impedir a exportação
            logger.warning("A prévia do lote não desenhou: %s", erro)
            self.lbl_previa.setText("Sem prévia")

    def _andou(self, feitos: int, total: int, _nome: str) -> None:
        self.barra.setValue(round(POR_MIL * feitos / total) if total else 0)

    def _terminou(self, relatorio: Any) -> None:
        if isinstance(relatorio, RelatorioDoLote):
            self._recado = frase_do_relatorio(relatorio)
        self.barra.setValue(POR_MIL)
        self.redesenhar()

    def _falhou(self, mensagem: str, _excecao: object) -> None:
        """A falha vai para o resumo, e não para uma caixa: é o critério da S-164."""
        self._recado = f"O lote parou: {mensagem}"
        self.redesenhar()


def qt_pasta_de_pecas() -> str:
    """A pasta do conjunto do usuário em vigor, ou vazio. Lida de `qt/tabuleiro.py`, que é quem a
    guarda desde a S-230 -- perguntá-la de novo aqui seria a segunda fonte da mesma escolha."""
    from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro

    return qt_tabuleiro.pasta_do_usuario()


def qt_conjunto_em_vigor() -> str:
    """O conjunto de peças que os tabuleiros da janela estão desenhando. Ver `qt/tabuleiro.py`."""
    from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro

    return qt_tabuleiro.conjunto_em_vigor()


def abrir_lote_de_diagramas(
    parent: QWidget | None,
    *,
    itens: Sequence[ItemDoLote] = (),
    origem: str = "",
    pasta: Path | None = None,
    busy: BusyRegistry | None = None,
    mostrar: bool = True,
) -> DialogoDoLote:
    """Monta o diálogo com a exportação ligada e o devolve.

    `mostrar=False` não chama `show()`; é o caminho do teste sob `offscreen`, como em
    `qt/fila_de_livros.abrir_fila_de_livros`.
    """
    exportacao = ExportacaoDoLote(parent, busy=busy)
    dialogo = DialogoDoLote(parent, itens=itens, origem=origem, pasta=pasta, exportacao=exportacao)
    exportacao.setParent(dialogo)
    if mostrar:
        dialogo.show()
    return dialogo
