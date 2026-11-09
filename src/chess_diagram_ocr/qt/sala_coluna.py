"""A coluna do tabuleiro na sala de estudo: a faixa de navegação e a miniatura do diagrama (S-866).

**Saíram de `qt/painel_de_estudo.py` dois widgets que o painel montava à mão.** A faixa sob o
tabuleiro (S-517) -- os quatro de navegação, o lance corrente, o símbolo, a vez, o ECO e o placar --
e a miniatura do diagrama âncora (S-282), com a régua de só reamostrar quando a âncora muda. O que
cada rótulo diz continua sendo decidido pelo painel, que é quem sabe o estudo aberto.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout, QWidget

from chess_diagram_ocr.estudo import Ancora
from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.ui import atalhos, barra_da_sala, comandos, espaco, tipografia, tokens
from chess_diagram_ocr.ui.sala_declarada import LADO_AMPLIADO, LADO_DO_RECORTE

logger = logging.getLogger(__name__)

LADO_DO_ICONE_DA_SALA = 16
"""Lado do ícone nos botões desta aba, em pixel (S-520).

Menor que o da fita (20 a 32): ali o ícone **é** o botão, com o rótulo embaixo; aqui ele acompanha
um rótulo ao lado, numa barra que já tem 28 botões. Dezesseis é a altura da letra da interface na
base 9, que é o que faz o par ícone-texto parecer uma coisa só em vez de duas."""

__all__ = ["LADO_DO_ICONE_DA_SALA", "FaixaDeNavegacao", "RecorteDoDiagrama"]


class FaixaDeNavegacao(BarraFluida):
    """Os quatro de navegação, **sob o tabuleiro**, com o lance corrente e a vez (S-517).

    As duas informações ao lado não são decoração: o lance corrente só existia como fundo
    amarelo no meio da lista, e a vez a jogar só como sufixo da frase do rodapé -- que é a
    última linha da janela, longe do olho de quem está olhando o tabuleiro.
    """

    def __init__(self, pai: QWidget, *, executar: Callable[[str], None]) -> None:
        super().__init__(pai)
        self._executar = executar
        for acao in barra_da_sala.NAVEGACAO:
            botao = self._botao(acao)
            if not botao.icon().isNull():
                # **Só aqui o ícone substitui o rótulo** (S-520), e é o único grupo em que isso é
                # honesto: o `rotulo_curto` destes quatro **é** um símbolo (`⏮ ◀ ▶ ⏭`), então
                # mantê-lo ao lado do ícone desenharia a mesma seta duas vezes -- uma da fonte de
                # queda e outra do traço vetorial. O rótulo longo e a tecla continuam na dica, que
                # é onde eles sempre estiveram.
                botao.setText("")
                botao.setIconSize(qt_icones.tamanho(2 * LADO_DO_ICONE_DA_SALA))
        self.lbl_lance = QLabel("", self)
        self.lbl_lance.setFont(tema.fonte_atual(tipografia.TITULO))
        self.adicionar(self.lbl_lance)
        # O símbolo do lance corrente **ao lado do lance** (S-527): ele ficava ao lado do botão
        # "Símbolo", na segunda fileira, e o botão foi para a fila de cima. `12. Ba4 !` é como o
        # livro escreve, e é aqui que o olho já está.
        self.lbl_simbolo = QLabel("", self)
        tema.pintar(self.lbl_simbolo, "color", tokens.TEXTO_SECUNDARIO)
        self.adicionar(self.lbl_simbolo)
        self.lbl_vez = QLabel("", self)
        tema.pintar(self.lbl_vez, "color", tokens.TEXTO_SECUNDARIO)
        self.adicionar(self.lbl_vez)
        # **O ECO da posição corrente** (S-534), na mesma faixa e pela mesma razão que a vez: é o
        # que um enxadrista lê para saber *em que abertura ele está*, e ele mudava a cada lance
        # sem aparecer em lugar nenhum da janela. Ao lado do tabuleiro, que é onde o olho está.
        self.lbl_eco = QLabel("", self)
        tema.pintar(self.lbl_eco, "color", tokens.TEXTO_SECUNDARIO)
        dica_em(
            self.lbl_eco,
            "O código ECO da posição. O header [ECO] da partida vence; sem ele, a tabela embutida\n"
            "classifica pela posição -- então uma transposição chega ao mesmo código.",
        )
        self.adicionar(self.lbl_eco)
        # E o placar do treino, pela mesma razão: ele acompanhava o botão "Treinar" na quarta
        # fileira, e o que ele conta acontece no tabuleiro.
        self.lbl_placar = QLabel("", self)
        tema.pintar(self.lbl_placar, "color", tokens.TEXTO_SECUNDARIO)
        self.adicionar(self.lbl_placar)

    def _botao(self, acao: str) -> QPushButton:
        """Um botão do catálogo, ligado ao método que `COMANDOS_DA_ABA` nomeia.

        **O método vem da tabela, e não é escrito aqui.** É o que faz um comando novo da sala
        chegar à barra, ao menu e à paleta de uma vez -- e o que garante que os dois frontends
        chamem exatamente os mesmos métodos.
        """
        botao = QPushButton(comandos.rotulo_de_botao(acao), self)
        # **O nome acessível é o rótulo por extenso, e não o texto do botão** (F9-C2).
        # O crítico do ciclo 1 mediu 28 controles que chegavam ao leitor de tela como "-",
        # "+", "|◀" ou ".md" -- o `rotulo_curto` passando pela cascata de
        # `ui/nomes_acessiveis.py` no passo `text()`. Ver `comandos.Comando.no_leitor`.
        botao.setAccessibleName(comandos.nome_acessivel(acao))
        # Qual ação este botão serve, legível de fora. O rótulo não responde: os quatro de
        # navegação passaram a desenhar só o ícone (S-520), e um teste que perguntasse pelo texto
        # deixaria de achá-los -- que é a guarda medindo o desenho em vez do arranjo.
        botao.setProperty("acao", acao)
        botao.clicked.connect(lambda _marcado=False, nome=acao: self._executar(nome))
        tema.aplicar_papel(botao, comandos.papel(acao))
        # **O ícone quando o catálogo declara um** (S-520), do mesmo jeito que a fita faz. Aqui
        # ele alcança só os quatro de navegação, e não é decoração: `⏮ ◀ ▶ ⏭` não existem na fonte
        # da interface -- `inFont` responde `False` para os quatro em Segoe UI --, então o rótulo
        # deles vinha de uma fonte de queda, com desenho que não é o da janela. O texto **fica**:
        # ícone que não desenhou devolve `None` e o botão continua legível.
        nome_do_icone = comandos.comando(acao).icone
        if nome_do_icone:
            lado = LADO_DO_ICONE_DA_SALA
            desenho = qt_icones.icone(nome_do_icone, 2 * lado, tema.cor_atual(tokens.TEXTO_PADRAO))
            if desenho is not None:
                botao.setIcon(desenho)
                botao.setIconSize(qt_icones.tamanho(lado))
        motivo = comandos.rotulo(acao)
        tecla = atalhos.acelerador(acao)
        dica_em(botao, f"{motivo}\nTecla: {tecla}" if tecla else motivo)
        # **Um glifo de texto nao e um icone** (F9-C7, §4.7). Quando o rotulo do botao nao tem
        # letra nenhuma -- `◀`, `▶|` -- e o catalogo declara um desenho, o desenho entra e o
        # glifo sai: medido, `◀` rendia 5x3 px de tinta contra 6x6 do `▶` ao lado, e "voltar um
        # lance" ficava sem direcao legivel em tres paineis. Rotulo com letra continua texto.
        if not any(letra.isalpha() for letra in botao.text()):
            qt_icones.vestir(botao, comandos.comando(acao).icone, comandos.papel(acao))
        self.adicionar(botao)
        return botao


class RecorteDoDiagrama(QLabel):
    """A miniatura do diagrama âncora (S-282). Nasce escondida: estudo sem âncora não mostra espaço
    reservado para o que não existe. O clique pede a ampliação a quem a montou."""

    def __init__(self, pai: QWidget, *, recorte: Callable[[Ancora], Any], ampliar: Callable[[], object]) -> None:
        super().__init__("", pai)
        self._recorte = recorte
        self._ampliar = ampliar
        self._recorte_de = ""
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide()

    def mousePressEvent(self, ev: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        self._ampliar()

    def mostrar(self, ancora: Ancora, *, ligado: bool) -> None:
        """A miniatura do diagrama âncora, ou nada.

        **Nada, e não um retângulo vazio**: estudo sem âncora não veio de diagrama nenhum, e um
        espaço reservado para o que não existe rouba largura do tabuleiro sem dizer por quê.

        A imagem é reconstruída só quando a **âncora** muda, e não a cada lance: navegar redesenha
        o tabuleiro dezenas de vezes por minuto, e reamostrar o recorte junto seria trabalho por
        nada.
        """
        chave = ancora.chave() if ancora.valida else ""
        if not ligado or not chave:
            self.hide()
            self._recorte_de = ""
            return
        if chave != self._recorte_de:
            pixmap = _miniatura(self._recorte(ancora), LADO_DO_RECORTE)
            if pixmap is None:
                self.hide()
                return
            self.setPixmap(pixmap)
            self._recorte_de = chave
        self.show()

    def ampliado(self, ancora: Ancora, pai: QWidget) -> QDialog | None:
        """O recorte no tamanho em que o modelo o leu, numa janela própria (S-282). `None` quando
        não há recorte.

        A miniatura cabe na coluna e serve para conferir *que* diagrama é; conferir **uma casa**
        pede o recorte inteiro. Uma janela e não um zoom no lugar: a comparação que se está fazendo
        é com o tabuleiro ao lado, e trocar a miniatura por uma imagem grande o empurraria para
        fora.
        """
        imagem = self._recorte(ancora) if ancora.valida else None
        pixmap = _miniatura(imagem, LADO_AMPLIADO)
        if pixmap is None:
            return None
        janela = QDialog(pai)
        janela.setWindowTitle(ancora.rotulo())
        pilha = QVBoxLayout(janela)
        pilha.setContentsMargins(*(espaco.folga(),) * 4)
        rotulo = QLabel(janela)
        rotulo.setPixmap(pixmap)
        pilha.addWidget(rotulo)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=janela)
        botoes.rejected.connect(janela.reject)
        pilha.addWidget(botoes)
        janela.show()
        return janela


def _miniatura(imagem: Any, lado: int) -> Any:
    """O recorte do diagrama como `QPixmap`, ou `None` quando não há o que desenhar (S-282).

    `Any` na assinatura porque a entrada é um `np.ndarray` RGB, e tipá-la obrigaria este módulo a
    importar numpy no topo por causa de uma anotação.

    Falha para o lado do nada: um recorte estragado esconde a miniatura e deixa a aba inteira em
    pé, que é o contrato de degradação do projeto desde a S-53.
    """
    if imagem is None:
        return None
    try:
        from chess_diagram_ocr.qt.imagens import pixmap_de_rgb

        pixmap = pixmap_de_rgb(imagem)
        maior = max(pixmap.width(), pixmap.height()) or 1
        if maior <= lado:
            return pixmap
        return pixmap.scaled(
            lado, lado, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    except Exception as erro:  # noqa: BLE001 - recorte de origem desconhecida
        logger.debug("Recorte do diagrama não pôde ser desenhado: %s", erro)
        return None
