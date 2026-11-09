"""As ferramentas de formato da aba de texto e os controles da fita que as aplicam (S-865).

**Saiu de `qt/painel_de_texto.py` com os controles que colhem valor** -- a galeria de estilos, o
corpo do parágrafo em pontos, as listas de cor e realce e os botões partidos que lembram a última
cor (S-650) -- e com o que a barra mostra sob o cursor (S-292). Toda ferramenta chama uma função
pura de `text/rico.py`, recebe um documento novo e o entrega à pilha do `EspelhoDaFolha`: é o que faz
o negrito sobreviver ao arquivo em vez de existir só enquanto o widget existir.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QMenu, QSpinBox, QToolButton, QWidget

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.texto_formato import formato_de
from chess_diagram_ocr.text import rico
from chess_diagram_ocr.ui import strings, texto_cores, tipografia
from chess_diagram_ocr.ui.texto_declarado import ROTULO_DO_CORPO_MISTO, alinhamento_dos_diagramas

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

logger = logging.getLogger(__name__)

__all__ = ["FerramentasDeFormato"]


class FerramentasDeFormato(QObject):
    """O formato do trecho -- ênfase, cor, estilo, alinhamento, corpo, caixa -- e os controles que o aplicam."""

    def __init__(self, aba: PainelDeTexto) -> None:
        super().__init__(aba)
        self._aba = aba
        self.ultimas_cores: dict[str, str] = {"letra": texto_cores.nomes()[0], "realce": texto_cores.nomes()[0]}
        """A última cor de letra e de realce aplicadas pelos botões partidos (S-650), guardadas na sessão."""

    def montar(self) -> None:
        """Os controles que colhem valor, que a fita põe nos grupos dela (S-650). Ver `ui/fita_do_texto`."""
        barra = self._aba
        self.galeria = self._montar_galeria()
        self.caixa_de_corpo = self._montar_caixa_de_corpo()

        self.escolha_de_cor = QComboBox(barra)
        self.escolha_de_cor.setAccessibleName("Cor da letra")
        self.escolha_de_cor.addItem("(sem cor)", "")
        for nome in texto_cores.nomes():
            self.escolha_de_cor.addItem(nome.capitalize(), nome)
        self.escolha_de_cor.activated.connect(
            lambda _i: self.pintar_letra(str(self.escolha_de_cor.currentData()))
        )

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
        # Os botões partidos que lembram a última cor (S-650), o conforto do WordCraft: o clique
        # aplica a mesma de antes, e a seta abre a lista. As listas de cima ficam, porque são elas
        # que mostram a cor **sob o cursor**; o botão mostra a que o clique vai pôr.
        self.cor_rapida = self._botao_partido("letra")
        self.realce_rapido = self._botao_partido("realce")

    # --------------------------------------- montagem e o que a barra mostra sob o cursor (S-292)

    def seguir_o_cursor(self) -> None:
        """As três escolhas da barra mostram o que vale sob o cursor -- ou na seleção inteira.

        O Tk tinha isto desde a S-292 e o porte deixou as caixas paradas em «(sem estilo)»: a
        pessoa punha o cursor num título e a barra dizia que não havia estilo. `valor_em_todo`
        responde `None` quando a seleção mistura valores, e aí a caixa volta ao vazio -- a mesma
        regra do negrito misto. As caixas disparam só por `activated` (o clique da pessoa), então
        repô-las aqui não aplica nada.
        """
        if self._aba.espelho.redesenhando:
            return
        inicio, fim = self._aba.espelho.intervalo()
        if inicio == fim:
            fim = min(len(self._aba.documento.para_texto()), inicio + 1)
        for caixa, atributo in ((self.escolha_de_cor, "cor"), (self.escolha_de_realce, "realce")):
            valor = rico.valor_em_todo(self._aba.documento, inicio, fim, atributo) if fim > inicio else None
            indice = caixa.findData(valor or "")
            caixa.setCurrentIndex(indice if indice >= 0 else 0)
        doc = self._aba.documento
        estilo = rico.valor_em_todo(doc, inicio, fim, "estilo") if fim > inicio else ""
        for nome, amostra in self.amostras.items():
            amostra.setChecked(estilo is not None and nome == (estilo or ""))
        # Os botões de estado (S-650): marcados com o que vale em todo o trecho, desmarcados no misto.
        estados = {a: fim > inicio and rico.vale_em_todo(doc, inicio, fim, a) for a in ("negrito", "italico", "sublinhado", "tachado")}
        alinhamento = rico.valor_em_todo(doc, inicio, fim, "alinhamento") if fim > inicio else None
        marca = self._aba.miniaturas.marca_em(inicio)
        if marca is not None:  # `valor_em_todo` pula a marca do diagrama: sobre ela vale o efetivo (S-620)
            alinhamento = rico.alinhamento_efetivo(marca[2], padrao_do_diagrama=alinhamento_dos_diagramas(self._aba.miniaturas.diagramas))
        for nome, valor in (("alinhar_esquerda", "esquerda"), ("alinhar_centro", "centro"), ("alinhar_direita", "direita"), ("justificar", "justificado")):
            estados[nome] = alinhamento == valor or (valor == "esquerda" and alinhamento == "")
        self._aba.fita.marcar(estados)
        self._mostrar_corpo(inicio, fim)
        self._aba.vista.contar_palavras_da_selecao()

    def _botao_partido(self, canal: str) -> QToolButton:
        """Um botão partido de cor: o corpo aplica a última, a seta abre os nomes do autor."""
        botao = QToolButton(self._aba)
        botao.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        botao.setAccessibleName(strings.COR_RAPIDA[canal])
        menu = QMenu(botao)
        for nome in texto_cores.nomes():
            acao = QAction(nome.capitalize(), menu)
            acao.triggered.connect(lambda _m=False, n=nome, c=canal: self._pintar_e_lembrar(c, n))
            menu.addAction(acao)
        botao.setMenu(menu)
        botao.clicked.connect(lambda _m=False, c=canal: self._pintar_e_lembrar(c, self.ultimas_cores[c]))
        self.mostrar_ultima_cor(botao, canal)
        return botao

    def _pintar_e_lembrar(self, canal: str, nome: str) -> None:
        self.ultimas_cores[canal] = nome
        (self.pintar_letra if canal == "letra" else self.pintar_realce)(nome)
        self.mostrar_ultima_cor(self.cor_rapida if canal == "letra" else self.realce_rapido, canal)

    def mostrar_ultima_cor(self, botao: QToolButton, canal: str) -> None:
        """O botão diz e desenha a cor que o clique vai pôr: o nome e uma amostra pela função da folha."""
        from PyQt6.QtGui import QIcon, QPixmap

        nome = self.ultimas_cores[canal]
        atributos = rico.Atributos(cor=nome) if canal == "letra" else rico.Atributos(realce=nome)
        formato = formato_de(rico.Corrida("A", atributos))
        amostra = QPixmap(14, 14)
        amostra.fill(formato.foreground().color() if canal == "letra" else formato.background().color())
        botao.setIcon(QIcon(amostra))
        botao.setText(nome.capitalize())
        botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        dica_em(botao, strings.dica_da_cor_rapida(canal, nome))

    def _montar_galeria(self) -> QWidget:
        """A galeria de estilos (S-651): cada amostra desenhada **no próprio estilo**, pela função da folha.

        A fonte de cada botão sai de `texto_formato.formato_de`, a mesma que desenha a folha: a galeria
        não pode mostrar um estilo que a folha não desenha, que é a guarda S-603 aplicada à amostra.
        """
        from PyQt6.QtWidgets import QButtonGroup, QToolButton

        galeria = QWidget(self._aba)
        galeria.setAccessibleName("Galeria de estilos")
        linha = QHBoxLayout(galeria)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(2)
        grupo = QButtonGroup(galeria)
        grupo.setExclusive(True)
        self.amostras: dict[str, QToolButton] = {}
        for estilo in ("", *rico.ESTILOS):
            amostra = QToolButton(galeria)
            amostra.setText(strings.NOME_DO_ESTILO.get(estilo, estilo.capitalize()))
            amostra.setAccessibleName(f"Estilo {strings.NOME_DO_ESTILO.get(estilo, estilo)}")
            amostra.setCheckable(True)
            amostra.setAutoRaise(True)
            amostra.setFont(formato_de(rico.Corrida(estilo or "Normal", rico.Atributos(estilo=estilo))).font())
            amostra.clicked.connect(lambda _marcado=False, e=estilo: self.aplicar_estilo(e))
            grupo.addButton(amostra)
            linha.addWidget(amostra)
            self.amostras[estilo] = amostra
        return galeria

    def estilo_na_galeria(self) -> str | None:
        """O estilo marcado na galeria, ou `None` quando a seleção mistura estilos."""
        for estilo, amostra in self.amostras.items():
            if amostra.isChecked():
                return estilo
        return None

    def _papel_e_base(self, estilo: str) -> tuple[str, int]:
        from chess_diagram_ocr.qt.texto_formato import PAPEL_DO_ESTILO

        base = self._aba.espelho.base[0] if self._aba.espelho.base is not None else tema.fonte_base()[0]
        return (PAPEL_DO_ESTILO[estilo] if estilo else tipografia.CORPO), base

    def _mostrar_corpo(self, inicio: int, fim: int) -> None:
        """A caixa mostra o corpo do parágrafo sob o cursor em pontos -- vazia quando a seleção mistura (S-631)."""
        comeco, final = rico.intervalo_de_paragrafo(self._aba.documento, inicio, fim)
        degrau = rico.valor_em_todo(self._aba.documento, comeco, final, "corpo") if final > comeco else None
        estilo = rico.valor_em_todo(self._aba.documento, comeco, final, "estilo") if final > comeco else ""
        self.caixa_de_corpo.blockSignals(True)
        try:
            if degrau is None or estilo is None:
                self.caixa_de_corpo.setValue(self.caixa_de_corpo.minimum())
            else:
                papel, base = self._papel_e_base(estilo)
                self.caixa_de_corpo.setValue(tipografia.corpo(int(degrau), base=base, papel=papel))
        finally:
            self.caixa_de_corpo.blockSignals(False)
        self._corpo_mostrado = self.caixa_de_corpo.value()

    def _corpo_digitado(self) -> None:
        """O valor digitado vira o degrau mais próximo, no parágrafo inteiro, num passo de desfazer."""
        valor = self.caixa_de_corpo.value()
        if valor == getattr(self, "_corpo_mostrado", None) or valor < tipografia.MINIMO_LEGIVEL:
            return
        inicio, fim = self._aba.espelho.intervalo()
        comeco, final = rico.intervalo_de_paragrafo(self._aba.documento, inicio, fim)
        estilo = rico.valor_em_todo(self._aba.documento, comeco, final, "estilo") or ""
        papel, base = self._papel_e_base(estilo)
        degrau = rico.corpo_no_limite(valor - tipografia.corpo(0, base=base, papel=papel))
        self._aba.espelho.rotulo_corrente = "Corpo do parágrafo"
        try:
            self._aba.espelho.aplicar(rico.aplicar_no_paragrafo(self._aba.documento, inicio, fim, corpo=degrau))
        finally:
            self._aba.espelho.rotulo_corrente = ""

    def _montar_caixa_de_corpo(self) -> QSpinBox:
        """O corpo do **parágrafo** em pontos (S-631). Não é o zoom: ele muda o documento e a exportação."""
        caixa = QSpinBox(self._aba)
        caixa.setAccessibleName("Corpo do parágrafo (pt)")
        caixa.setRange(tipografia.MINIMO_LEGIVEL - 1, 96)
        caixa.setSpecialValueText(ROTULO_DO_CORPO_MISTO)  # o valor de baixo é "misto" (S-292)
        caixa.setSuffix(" pt")
        dica_em(caixa, strings.DICA_DO_CORPO_EM_PONTOS)
        caixa.editingFinished.connect(self._corpo_digitado)
        return caixa

    # --------------------------------------------------- ênfase, cor, estilo, alinhamento e corpo

    def alternar(self, atributo: str) -> None:
        """Liga o atributo no intervalo -- ou desliga, se ele já vale em todo ele (S-241)."""
        inicio, fim = self._aba.espelho.intervalo()
        self._aba.espelho.aplicar(rico.alternar(self._aba.documento, inicio, fim, atributo))

    def limpar_formato(self) -> None:
        """Tira negrito, itálico e sublinhado. **Não** toca em cor nem em estilo (S-242)."""
        inicio, fim = self._aba.espelho.intervalo()
        self._aba.espelho.aplicar(rico.limpar_formato(self._aba.documento, inicio, fim))

    def pintar_letra(self, nome: str) -> None:
        """A cor do autor. `""` limpa -- e limpar cor **não** toca a faixa de confiança (S-242)."""
        inicio, fim = self._aba.espelho.intervalo()
        if not nome:
            self._aba.espelho.aplicar(rico.limpar_cor(self._aba.documento, inicio, fim))
            return
        self._aba.espelho.aplicar(rico.aplicar(self._aba.documento, inicio, fim, cor=nome))

    def pintar_realce(self, nome: str) -> None:
        inicio, fim = self._aba.espelho.intervalo()
        self._aba.espelho.aplicar(rico.aplicar(self._aba.documento, inicio, fim, realce=nome))

    def aplicar_estilo(self, estilo: str) -> None:
        """O estilo do **parágrafo** que o intervalo toca (S-249).

        O alcance passa do que foi selecionado de propósito: o parágrafo é o conjunto de corridas
        do mesmo bloco, e marcar meia frase deixaria dois corpos de fonte na mesma linha.
        """
        inicio, fim = self._aba.espelho.intervalo()
        self._aba.espelho.aplicar(rico.aplicar_estilo(self._aba.documento, inicio, fim, estilo))

    def alinhar(self, alinhamento: str) -> None:
        inicio, fim = self._aba.espelho.intervalo()
        self._aba.espelho.aplicar(rico.aplicar_alinhamento(self._aba.documento, inicio, fim, alinhamento))

    def mudar_corpo(self, degrau: int) -> None:
        """Aumenta ou diminui o corpo do parágrafo, em degraus (S-260).

        **O degrau é somado ao que o documento guarda, e não ao que está na tela.** Somar ao
        tamanho desenhado acumularia o degrau anterior a cada redesenho, e a fonte cresceria
        sozinha -- é a razão que `texto_formato._fonte` documenta do outro lado.
        """
        inicio, fim = self._aba.espelho.intervalo()
        atual = self._corpo_em(inicio)
        self._aba.espelho.aplicar(
            rico.aplicar_no_paragrafo(self._aba.documento, inicio, fim, corpo=rico.corpo_no_limite(atual + degrau))
        )

    def _corpo_em(self, deslocamento: int) -> int:
        percorrido = 0
        for corrida in self._aba.documento.corridas:
            if percorrido <= deslocamento < percorrido + len(corrida.texto):
                return corrida.atributos.corpo
            percorrido += len(corrida.texto)
        return 0

    def corpo_normal(self) -> None:
        """Volta o parágrafo ao corpo do estilo dele -- degrau zero, e não "sem corpo"."""
        inicio, fim = self._aba.espelho.intervalo()
        self._aba.espelho.aplicar(rico.aplicar_no_paragrafo(self._aba.documento, inicio, fim, corpo=0))

    def escolher_cor(self) -> None:
        """Abre a lista de cores da barra. O comando é a porta de menu do mesmo gesto."""
        self.escolha_de_cor.showPopup()

    def escolher_realce(self) -> None:
        """O mesmo para o realce. Sem lista na barra, o comando pinta com o primeiro papel."""
        self.escolha_de_realce.showPopup()

    # --------------------------------------------------------------------------- a caixa (S-262)

    def mudar_caixa(self, caixa: str) -> None:
        """MAIÚSCULAS, minúsculas ou Iniciais no alvo.

        **Muda o texto**, e por isso passa pela mesma pilha das outras ferramentas: o documento
        anterior é guardado antes do redesenho. Sem isso, desfazer uma troca de caixa sobre um
        parágrafo seria impossível. A seleção segue o texto trocado, que pode ter crescido (S-904);
        sem seleção, o cursor fica onde estava, como nas outras ferramentas.
        """
        inicio, fim = self._aba.espelho.intervalo()
        novo, selecao = rico.mudar_caixa_com_selecao(self._aba.documento, inicio, fim, caixa)
        self._aba.espelho.aplicar(novo, selecao=selecao if inicio != fim else None)

    # ----------------------------------------------------------- a área de transferência (S-263)

    def selecionar_tudo(self) -> None:
        """Seleciona o texto inteiro da folha.

        **É uma correção, e não um acréscimo**: no `tk.Text` de fábrica `Ctrl+A` leva o cursor ao
        início da linha, e selecionar tudo não tinha tecla nem comando. O `QTextEdit` já faz o
        certo; o comando existe para ele ter menu, paleta e tecla como os outros quarenta e sete.
        """
        self._aba.editor.selectAll()
        self._aba.editor.setFocus()

    def recortar(self) -> None:
        self._aba.editor.cut()

    def copiar(self) -> None:
        self._aba.editor.copy()

    def colar(self) -> None:
        """Cola no cursor. **O texto colado herda os atributos dos dois lados**, como o digitado.

        O que **não** vem junto é formatação de outro programa: `setAcceptRichText(False)` recusa
        HTML colado, e o que entra é texto -- que é o mesmo contrato do outro frontend, onde a
        área de transferência do Tk carrega texto e não corridas.
        """
        self._aba.editor.paste()
