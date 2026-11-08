"""A paleta de marcas da conferência de importação: o que o próximo gesto põe no tabuleiro.

É a irmã de `qt/paleta_de_pecas.py`, com as mesmas decisões e a mesma folha: o botão que fica aceso
porque ferramenta é modo, o clique no aceso que larga, e o `habilitar` que larga ao apagar. Os ícones
são o próprio desenho das marcas (`qt/desenho_de_marcas.py`) sobre a casa clara, para o botão mostrar
o que o clique vai pôr.

As duas paletas não se conhecem: a janela é quem garante que só uma tem algo na mão.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QToolButton, QWidget

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr.qt import desenho_de_marcas as desenho
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.paleta_de_pecas import LADO_DO_ICONE, ROTULO_SEM_PINCEL, folha_da_paleta
from chess_diagram_ocr.ui import espaco, tokens

__all__ = ["PaletaDeMarcas"]

FILEIRAS: tuple[tuple[str, str], ...] = (
    (mc.BOLINHA_BRANCA, mc.BOLINHA_PRETA),
    (mc.ESTRELA_BRANCA, mc.ESTRELA_PRETA),
    (mc.X, mc.CRUZ),
    (mc.SETA, mc.RETA),
    (mc.MOLDURA, mc.OUTRA),
)
"""Aos pares, como na paleta de peças: a branca e a preta da mesma forma ficam vizinhas."""

_TRACO_DO_ICONE: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    mc.SETA: ((0.18, 0.82), (0.86, 0.14)),
    mc.RETA: ((0.18, 0.82), (0.82, 0.18)),
    mc.MOLDURA: ((0.2, 0.25), (0.8, 0.75)),
}


class PaletaDeMarcas(QWidget):
    """Os dez botões de marca e o de largar -- e qual deles está aceso."""

    ferramenta = pyqtSignal(object)
    """A ferramenta que passou a valer: um tipo de `marcas_de_casa`, ou `None` (largar).

    `object` e não `str` pela mesma razão do sinal da paleta de peças: a ausência é uma resposta."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._atual: str | None = None
        self._botoes: dict[str, QToolButton] = {}
        self._montar()
        self._repintar()
        tema.ao_repintar(self._repintar)

    def _montar(self) -> None:
        grade = QGridLayout(self)
        grade.setContentsMargins(espaco.linha(), 0, 0, 0)
        grade.setSpacing(espaco.minima())
        grade.addWidget(QLabel("Marcas", self), 0, 0, 1, 2)
        for fileira, par in enumerate(FILEIRAS, start=1):
            for coluna, tipo in enumerate(par):
                grade.addWidget(self._botao_de_marca(tipo), fileira, coluna)
        self.btn_largar = QToolButton(self)
        self.btn_largar.setText(ROTULO_SEM_PINCEL)
        self.btn_largar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_largar.clicked.connect(lambda _marcado=False: self.largar())
        dica_em(self.btn_largar, "Larga a marca: o clique volta a corrigir peças.")
        grade.addWidget(self.btn_largar, len(FILEIRAS) + 1, 0, 1, 2)
        grade.setRowStretch(len(FILEIRAS) + 2, 1)

    def _botao_de_marca(self, tipo: str) -> QToolButton:
        botao = QToolButton(self)
        botao.setCheckable(True)
        botao.setIconSize(QSize(LADO_DO_ICONE, LADO_DO_ICONE))
        botao.setAccessibleName(f"Marca: {mc.NOMES[tipo]}")
        dica_em(botao, self._dica(tipo))
        botao.clicked.connect(lambda _marcado=False, escolhido=tipo: self._clicou(escolhido))
        self._botoes[tipo] = botao
        return botao

    @staticmethod
    def _dica(tipo: str) -> str:
        nome = mc.NOMES[tipo].capitalize()
        if tipo in mc.TIPOS_DE_TRACO:
            gesto = "Arraste no tabuleiro para desenhar; o botão direito tira o traço."
        else:
            gesto = "Clique numa casa para pôr ou tirar; o botão direito tira a marca."
        return f"{nome}. {gesto}\nClicar no botão aceso larga a marca."

    @property
    def escolhido(self) -> str | None:
        return self._atual

    def _clicou(self, tipo: str) -> None:
        self.escolher(None if tipo == self._atual else tipo)

    def escolher(self, tipo: str | None) -> None:
        """Põe uma ferramenta na mão e acende só o botão dela. `None` larga o que houver."""
        self._atual = tipo
        for valor, botao in self._botoes.items():
            botao.setChecked(valor == tipo)
        self.ferramenta.emit(tipo)

    def largar(self) -> None:
        self.escolher(None)

    def habilitar(self, ligado: bool, *, motivo: str = "") -> None:
        """Acende ou apaga a paleta. Apagar larga a ferramenta, para ela não voltar armada."""
        if not ligado and self._atual is not None:
            self.largar()
        for tipo, botao in self._botoes.items():
            botao.setEnabled(ligado)
            dica_em(botao, self._dica(tipo) if ligado or not motivo else motivo)
        self.btn_largar.setEnabled(ligado)

    def _icone(self, tipo: str) -> QIcon:
        mapa = QPixmap(LADO_DO_ICONE, LADO_DO_ICONE)
        mapa.fill(QColor(tema.cor_atual(tokens.CASA_CLARA)))
        pintor = QPainter(mapa)
        if tipo in mc.TIPOS_DE_TRACO:
            de, para = _TRACO_DO_ICONE[tipo]
            desenho.pintar_traco(pintor, mc.Traco(tipo, de, para), 0.0, 0.0, float(LADO_DO_ICONE))
        else:
            desenho.pintar_marca(pintor, tipo, QRectF(0.0, 0.0, LADO_DO_ICONE, LADO_DO_ICONE))
        pintor.end()
        return QIcon(mapa)

    def _repintar(self) -> None:
        """A folha do botão aceso e os ícones, que usam cores do tema."""
        self.setStyleSheet(folha_da_paleta())
        for tipo, botao in self._botoes.items():
            botao.setIcon(self._icone(tipo))
