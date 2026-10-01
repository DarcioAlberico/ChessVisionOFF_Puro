"""A paleta de peças da aba Resultado: doze peças, apagar e o pincel visível (S-65/S-506).

**Ela não foi inventada aqui: ela voltou.** A paleta é o item da S-65, morava em
`ui/board_widget.py::_build_palette` e saiu inteira no corte do Tk (S-506), junto com o arquivo
que a hospedava. O que sobreviveu do outro lado foi `TabuleiroEditavel.definir_pincel` -- um
pincel que nada na tela sabia carregar. O modelo aceita `paint`, o widget roteia o clique, e a
única forma de escolher a peça era nenhuma: `definir_pincel` não tinha chamador no produto, e
trocar a classe de uma peça mal lida voltou a custar arrastar a errada para fora sem ter como pôr
a certa. O critério de aceite da S-65 -- "os 12 botões, com imagem e sem texto; o pincel ativo
distinguível em tema claro e escuro" -- ficou vermelho sem que nada acusasse.

**Aqui, e não dentro de `qt/tabuleiro_editavel.py`.** No Tk os dois moravam no mesmo widget
porque lá o tabuleiro era um `Canvas` **dentro** de um `Frame`, e sobrava onde pendurar botão. O
`TabuleiroEditavel` do Qt é o desenho: ele pinta a própria área inteira no `paintEvent`, e um
botão filho seria um botão *sobre* o tabuleiro. A paleta é irmã dele, e quem liga uma coisa na
outra é o painel -- a mesma fronteira que `on_change` marcava lá.

**O achado da S-65 se repete no Qt, e a medição é outra.** Lá nenhuma variante de `Toolbutton`
desenhava estado selecionado num botão com imagem e sem texto: os doze saíam idênticos, e o
pincel ativo era invisível. Aqui o Qt **desenha** o `:checked` -- e desenha de leve demais.
Fotografado sob a folha de `qt/tema.py` no estilo `Fusion`, o botão aceso separa-se do apagado
por uma razão de contraste de **1,26** no cromo claro e **1,11** no escuro, contra o piso de 3,0
que `tokens.AA_GRAFICO` fixa para elemento gráfico -- num controle cujo trabalho inteiro é dizer
qual peça está na mão. E o programa não fixa estilo: ele embrulha o da plataforma em
`qt/dica._EstiloComAtrasoDeDica`, então o quanto aquele afundado aparece passaria a depender da
máquina de quem corrige. O conserto é o mesmo dos dois lados -- dizer o estado à mão, com cor
tirada do tema e não cravada --, e é o que `_repintar` faz: com ele são 3,28 e 3,81.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QGridLayout, QSizePolicy, QToolButton, QWidget

from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.tabuleiro import (
    GLIFOS,
    ao_trocar_de_conjunto,
    carregar_pecas,
    conjunto_em_vigor,
    engrossada,
    pasta_do_conjunto,
)
from chess_diagram_ocr.ui import board_edit, conjuntos, espaco, estilos, tokens

__all__ = ["APAGAR", "LADO_DO_ICONE", "PaletaDePecas"]

APAGAR = ""
"""O pincel que esvazia a casa. É o mesmo valor que `BoardModel.brush` já usa para isso -- a
paleta não traduz nada: o que ela emite é o que o modelo entende."""

LADO_DO_ICONE = 26
"""Lado do ícone de peça, em pixel. É o `PALETTE_ICON_SIZE` da S-65, e o número tem medição:
os PNGs de `assets/piece_images/` são 70x70, e 26 px dá um botão do tamanho de um de três
caracteres -- que é o que a paleta ocupava antes de ter imagem."""

PESO_DO_SELECIONADO = 0.45
PESO_SOB_O_PONTEIRO = 0.15
"""Quanto o fundo do botão anda na direção da letra, aceso e sob o ponteiro.

**São os dois pesos da S-65, e eles vêm de lá inteiros.** A conta é a mesma -- misturar a
superfície com o texto do tema em vez de cravar hexadecimal -- e ela existe pela mesma razão nos
dois frontends: a pele escura e a clara precisam de contraste pela **mesma** regra, ou o botão
aceso vira um retângulo branco no meio de uma janela preta."""

ROTULO_APAGAR = "✕"
ROTULO_SEM_PINCEL = "Largar"
"""Os dois controles que não são peça, e os dois são curtos por causa de onde a paleta mora.

`✕` é um pincel como os outros doze -- ele fica aceso, e o clique esvazia a casa; `Largar` não é
pincel nenhum: ele solta o que estiver na mão e devolve o clique ao arrasto.

**Ao lado do tabuleiro, rótulo é largura tirada do desenho.** Os dois controles ficam sob as duas
colunas de peça, e um texto mais largo que elas empurraria o tabuleiro para trás sem mostrar nada
em troca -- daí o `✕`, que é o mesmo símbolo dos editores de posição que se usam por aí, e daí
`Largar` no lugar de "Sem pincel". Nenhum dos dois é mudo: a dica de cada um diz o que ele faz, e
a frase de status confirma o que aconteceu."""


class PaletaDePecas(QWidget):
    """Os doze botões de peça, o de apagar e o de largar -- e qual deles está aceso."""

    pincel = pyqtSignal(object)
    """O pincel que passou a valer: `"Q"`, `""` (apagar) ou `None` (largar).

    `object` e não `str` porque o pincel tem três estados e um deles é a ausência: um sinal de
    `str` não carrega `None`, e trocar a ausência por uma sentinela de texto obrigaria a outra
    ponta a traduzi-la de volta -- que é a tradução que `BoardModel.set_brush` já não pede.
    """

    def __init__(self, parent: QWidget | None = None, *, pasta_de_pecas: Path | None = None) -> None:
        super().__init__(parent)
        self._pasta_pinada = Path(pasta_de_pecas) if pasta_de_pecas is not None else None
        """Uma pasta cravada por quem construiu, como em `qt/tabuleiro.TabuleiroQt`. `None` segue
        o conjunto em vigor, e é o que o produto faz."""
        self._atual: str | None = None
        self._botoes: dict[str, QToolButton] = {}
        self._montar()
        self._recarregar_icones()
        ao_trocar_de_conjunto(self._recarregar_icones)
        self._repintar()
        tema.ao_repintar(self._repintar)

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        """Duas colunas de seis, aos pares: a peça branca e a preta dela, lado a lado.

        **A forma é a de uma coluna ao lado do tabuleiro, e não a fileira do Tk.** Lá a paleta
        ficava embaixo porque o tabuleiro ocupava a largura do painel; aqui ela é vizinha dele, e
        a grade é alta e estreita para caber nessa vizinhança.

        **Em pares e não em fileiras de cor**: a peça e a contrária dela ficam vizinhas, e trocar
        a cor de uma leitura errada -- que é metade das correções deste painel -- vira o clique ao
        lado em vez de um salto para o outro lado da paleta.
        """
        grade = QGridLayout(self)
        grade.setContentsMargins(espaco.linha(), 0, 0, 0)
        grade.setSpacing(espaco.minima())

        brancas, pretas = board_edit.PIECE_SYMBOLS[:6], board_edit.PIECE_SYMBOLS[6:]
        for fileira, (branca, preta) in enumerate(zip(brancas, pretas, strict=True)):
            grade.addWidget(self._botao_de_pincel(branca), fileira, 0)
            grade.addWidget(self._botao_de_pincel(preta), fileira, 1)
        grade.addWidget(self._alargado(self._botao_de_pincel(APAGAR)), len(brancas), 0, 1, 2)

        self.btn_largar = QToolButton(self)
        self.btn_largar.setText(ROTULO_SEM_PINCEL)
        self.btn_largar.clicked.connect(lambda _marcado=False: self.largar())
        dica_em(self.btn_largar, self._dica(None))
        grade.addWidget(self._alargado(self.btn_largar), len(brancas) + 1, 0, 1, 2)
        # A paleta é mais baixa que o tabuleiro: sem isto os catorze botões se espalhariam pela
        # altura dele, e o par de uma peça deixaria de estar ao lado dela.
        grade.setRowStretch(len(brancas) + 2, 1)

    @staticmethod
    def _alargado(botao: QToolButton) -> QToolButton:
        """Faz o botão ocupar as duas colunas que ele atravessa.

        Ocupar o vão não é o padrão do Qt: um `QToolButton` nasce com largura mínima, e um que
        atravessa duas colunas sem isto encosta na esquerda com o tamanho do rótulo -- o `✕`
        sairia menor que uma peça, e os dois controles teriam larguras diferentes entre si.
        """
        botao.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return botao

    def _botao_de_pincel(self, valor: str) -> QToolButton:
        """Um botão que **fica aceso**: pincel é modo, e modo precisa aparecer na tela (S-65)."""
        botao = QToolButton(self)
        botao.setCheckable(True)
        botao.setIconSize(QSize(LADO_DO_ICONE, LADO_DO_ICONE))
        if valor == APAGAR:
            botao.setText(ROTULO_APAGAR)
            # **O desenho no lugar do glifo** (F9-C7, §4.7). O `✕` rendia **7×7 px de tinta**
            # num botão de 72×25, no meio de doze botões que desenham peça a `LADO_DO_ICONE`:
            # é o defeito do §9.4 do ciclo 5 -- *"um 'ícone' de 4×5 px num botão de 26 px"* --
            # sobrevivendo no único botão da paleta que não é peça. `apagar_casa` já está no
            # catálogo e é exatamente este gesto. O `ROTULO_APAGAR` fica como reserva: sem
            # Pillow, `vestir` devolve `False` e o glifo continua na tela.
            qt_icones.vestir(botao, "apagar_casa", estilos.NEUTRO, lado=LADO_DO_ICONE)
        dica_em(botao, self._dica(valor))
        botao.clicked.connect(lambda _marcado=False, escolhido=valor: self._clicou(escolhido))
        self._botoes[valor] = botao
        return botao

    def _dica(self, valor: str | None) -> str:
        """O que aquele botão põe na mão -- e como se larga o que já está nela."""
        if valor is None:
            return "Larga o pincel: o clique volta a arrastar peças."
        if valor == APAGAR:
            return "Pincel apagar: um clique esvazia a casa.\nClicar no botão aceso larga o pincel."
        nome = board_edit.PIECE_NAMES_PT[valor]
        return f"Pincel: {nome}. Clique numa casa para inserir.\nClicar no botão aceso larga o pincel."

    # ------------------------------------------------------------------------------ escolha

    @property
    def escolhido(self) -> str | None:
        """O pincel na mão agora. `None` quando o clique arrasta em vez de pintar."""
        return self._atual

    def _clicou(self, valor: str) -> None:
        """Clicar no botão já aceso **larga** o pincel, em vez de reafirmá-lo.

        É o `_on_palette_click` do Tk, e a razão de existir é a mesma dos dois lados: o gesto
        natural de quem terminou de pintar é clicar de novo no botão que está aceso, e sem isto
        largar o pincel exige achar o "Sem pincel" do outro lado da fila. Muda só o mecanismo --
        lá o `Radiobutton` reafirmava o valor em silêncio, aqui o `QToolButton` marcável se
        remarcaria sozinho.

        **Ele mora aqui e não em `TabuleiroEditavel.definir_pincel`**, que é o que o docstring
        de lá pediu: alternar é gesto de paleta, e a mesma pergunta com duas respostas em dois
        arquivos é o defeito que aquele comentário existe para evitar.
        """
        self.escolher(None if valor == self._atual else valor)

    def escolher(self, simbolo: str | None) -> None:
        """Põe um pincel na mão e acende só o botão dele. `None` larga o que houver."""
        self._atual = simbolo
        for valor, botao in self._botoes.items():
            botao.setChecked(valor == simbolo)
        self.pincel.emit(simbolo)

    def largar(self) -> None:
        """Sai do modo pincel: o clique volta a arrastar peças.

        Emite mesmo quando não havia pincel nenhum, e é de propósito -- o sinal vira a frase de
        status de `BoardModel.set_brush`, e um botão que responde silêncio a um clique é o que a
        S-165 chama de controle mudo.
        """
        self.escolher(None)

    def habilitar(self, ligado: bool, *, motivo: str = "") -> None:
        """Acende ou apaga a paleta inteira -- e **diz por quê** quando apaga (S-165).

        Sem diagrama aberto a paleta fica cinza, e não por zelo: o painel vazio desenha um
        tabuleiro sem peças que a S-170 escolheu não parecer uma leitura, e pintar uma dama nele
        produziria exatamente a tela que aquele item existe para não deixar acontecer -- um
        diagrama na cara de quem não abriu nenhum, com "Salvar" ao lado.

        Largar o pincel ao apagar é parte da mesma regra: um pincel que sobrevivesse à página
        fechada voltaria armado na próxima, e o primeiro clique de quem só queria arrastar uma
        peça pintaria outra.
        """
        if not ligado and self._atual is not None:
            self.largar()
        for valor, botao in self._botoes.items():
            botao.setEnabled(ligado)
            dica_em(botao, self._dica(valor) if ligado else motivo)
        self.btn_largar.setEnabled(ligado)
        dica_em(self.btn_largar, self._dica(None) if ligado else motivo)

    # ------------------------------------------------------------------------------ desenho

    def _recarregar_icones(self) -> None:
        """Relê os doze PNGs do conjunto em vigor. Uma peça ausente cai no glifo Unicode.

        **A degradação é a da S-65, e ela é por peça e não por paleta**: um checkout sem
        `assets/`, ou um PNG corrompido, não pode impedir a aba de abrir -- e o botão que perdeu
        a imagem continua dizendo qual peça ele põe.
        """
        pasta = self._pasta_pinada if self._pasta_pinada is not None else pasta_do_conjunto()
        pecas = carregar_pecas(pasta)
        for simbolo in board_edit.PIECE_SYMBOLS:
            botao = self._botoes[simbolo]
            mapa = pecas.get(simbolo)
            if mapa is None:
                botao.setIcon(QIcon())
                botao.setText(GLIFOS[simbolo])
            else:
                botao.setText("")
                botao.setIcon(QIcon(self._sobre_a_casa_clara(mapa)))

    def _sobre_a_casa_clara(self, mapa: QPixmap) -> QPixmap:
        """A peça no tamanho do ícone, sobre a cor da casa clara (S-65).

        **O fundo é o item, e não enfeite.** Os PNGs são traço com transparência: sob pele
        escura as seis peças pretas somem no fundo do botão, que é o mesmo defeito que a paleta
        tinha quando desenhava `♟` com a fonte do sistema. Sobre a casa clara elas aparecem em
        qualquer pele -- e é assim que elas se parecem no tabuleiro, que é o que a paleta está
        prometendo ao dizer "isto é o que o clique vai colocar".

        O traço grosso da S-230 vale aqui pela mesma razão que vale no tabuleiro, e é o próprio
        `ui/pecas.engrossar_traco` que nomeia este tamanho: a 20-24 px a redução apaga o contorno
        fino, e as seis brancas viram manchas parecidas entre si.
        """
        if conjuntos.registrado(conjunto_em_vigor()).engrossa:
            peca = engrossada(mapa, LADO_DO_ICONE)
        else:
            peca = mapa.scaled(
                LADO_DO_ICONE,
                LADO_DO_ICONE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        fundo = QPixmap(LADO_DO_ICONE, LADO_DO_ICONE)
        fundo.fill(QColor(tema.cor_atual(tokens.CASA_CLARA)))
        pintor = QPainter(fundo)
        pintor.drawPixmap((LADO_DO_ICONE - peca.width()) // 2, (LADO_DO_ICONE - peca.height()) // 2, peca)
        pintor.end()
        return fundo

    def _repintar(self) -> None:
        """O botão aceso, dito à mão e com cor do tema. Ver o cabeçalho do módulo.

        A folha vai no widget e não na aplicação porque ela é a exceção da regra de
        `qt/tema.pintar`: uma cor que depende de **estado**, e de um estado que só esta paleta
        tem. Um `QToolButton:checked` na folha da aplicação valeria para o botão de recorte e o
        de treino da sala de estudo, que não pediram nada.
        """
        superficie = tema.cor_atual(tokens.SUPERFICIE_PADRAO)
        texto = tema.cor_atual(tokens.TEXTO_PADRAO)
        moldura = tema.cor_atual(tokens.MOLDURA)
        secundario = tema.cor_atual(tokens.TEXTO_SECUNDARIO)
        self.setStyleSheet(
            f"QToolButton {{ border: 1px solid {moldura}; border-radius: {espaco.minima()}px;"
            f" padding: {espaco.minima()}px; }}"
            f"QToolButton:hover {{ background-color: {tokens.mistura(superficie, texto, PESO_SOB_O_PONTEIRO)}; }}"
            f"QToolButton:checked {{ background-color: {tokens.mistura(superficie, texto, PESO_DO_SELECIONADO)}; }}"
            # Pela mesma razão da S-506 no `QPushButton`: a cor de letra da folha vale em todos
            # os estados e anula o acinzentamento que o Qt faria pela paleta.
            f"QToolButton:disabled {{ color: {secundario}; border-color: {secundario}; }}"
        )
