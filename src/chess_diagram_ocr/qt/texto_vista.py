"""A vista da folha: o zoom, a quebra, a letra, o modo foco, as marcas e a barra de estado (S-865).

**Saiu de `qt/painel_de_texto.py` com o estado dela**, que é vista e não documento: o degrau do zoom
e as paradas da régua, a letra de leitura, o modo foco, as marcas de formatação, e a barra de estado
com o recado transitório. Nada disto é gravado na folha nem exportado; o que a sessão guarda passa
por `PainelDeTexto.aplicar_estado`/`anotar_estado`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QTextCursor, QWheelEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTextEdit, QToolButton, QWidget

from chess_diagram_ocr.qt import tema, texto_leitura
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.text import correcao
from chess_diagram_ocr.ui import atalhos, comandos, strings, tokens
from chess_diagram_ocr.ui.texto_declarado import (
    FAMILIA_DA_LETRA_PADRAO,
    FAMILIAS_DA_LETRA,
    NOME_DA_FAMILIA,
    ZOOM_MAXIMO,
    ZOOM_MINIMO,
    contar_palavras,
    frase_das_palavras,
    frase_do_rodape,
    paradas_do_zoom,
    porcentagem_do_zoom,
    proxima_familia_da_letra,
)

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

logger = logging.getLogger(__name__)

__all__ = ["SEGUNDOS_DO_RECADO", "VistaDaFolha"]

SEGUNDOS_DO_RECADO = 6.0
"""Quanto o recado transitório fica na barra de estado (S-655): a regra do WordCraft. O texto
inteiro fica na dica, para quem não o leu a tempo."""


class VistaDaFolha(QObject):
    """Como a folha aparece -- zoom, quebra, letra, foco, marcas -- e a barra de estado embaixo dela."""

    def __init__(self, aba: PainelDeTexto) -> None:
        super().__init__(aba)
        self._aba = aba
        self._zoom_da_vista = 0
        self.corpo_de_base = 0
        """O corpo da fonte antes de qualquer zoom da vista, posto pela montagem do editor.
        `aplicar_zoom` soma o degrau **a ele**, e não ao que está na tela -- somar ao desenhado
        acumularia o degrau anterior a cada chamada, e a letra cresceria sozinha."""
        self._familia_da_letra = FAMILIA_DA_LETRA_PADRAO
        """A letra de leitura (S-632): `ui/texto_declarado.FAMILIAS_DA_LETRA`. Vista, como o zoom."""
        self.modo_foco = False
        self._navegacao_antes_do_foco = False
        self._marcas_de_formatacao = False
        self._palavras_cache: tuple[object, int] = (None, 0)

    def montar_rodape(self) -> QHBoxLayout:
        """A barra de estado da aba, com o zoom à vista na ponta direita (S-655, S-630)."""
        # A barra de estado da mesa (S-655): a folha e o que ela tem, as palavras, o léxico, e o
        # zoom na ponta direita. O recado transitório toma o lugar das do meio por 6 s.
        rodape = QHBoxLayout()
        self.status = QLabel("", self._aba)
        self.status.setAccessibleName("Estado da folha")
        # O clique na folha do rodapé leva ao campo da folha (S-655): «Folha 12» é onde se olha para
        # saber em que folha se está, e é dali que se quer ir à outra.
        self.status.setCursor(Qt.CursorShape.PointingHandCursor)
        dica_em(self.status, strings.DICA_DO_RODAPE_DA_FOLHA)
        self.status.installEventFilter(self._aba)
        rodape.addWidget(self.status, 1)
        self.caixa_de_palavras = QLabel("", self._aba)
        self.caixa_de_palavras.setAccessibleName("Palavras da folha")
        rodape.addWidget(self.caixa_de_palavras)
        self.caixa_do_lexico = QToolButton(self._aba)
        self.caixa_do_lexico.setAccessibleName(comandos.nome_acessivel("proxima_fora_do_lexico"))
        self.caixa_do_lexico.setAutoRaise(True)
        self.caixa_do_lexico.clicked.connect(lambda _marcado=False: self._aba.correcao.proxima_fora_do_lexico())
        self.caixa_do_lexico.hide()
        rodape.addWidget(self.caixa_do_lexico)
        self.recado = QLabel("", self._aba)
        self.recado.setAccessibleName("Recado da aba")
        self.recado.hide()
        rodape.addWidget(self.recado, 1)
        rodape.addWidget(self.montar_zoom())
        self._relogio_do_recado = QTimer(self._aba)
        self._relogio_do_recado.setSingleShot(True)
        self._relogio_do_recado.setInterval(int(SEGUNDOS_DO_RECADO * 1000))
        self._relogio_do_recado.timeout.connect(self._apagar_recado)
        self._aba.estado.connect(self.mostrar_recado)
        return rodape

    # ----------------------------------------- o zoom à vista (S-630) e a barra de estado (S-655)

    def montar_zoom(self) -> QWidget:
        """O zoom à vista, no rodapé (S-630): `−`, a régua, `+` e a porcentagem.

        **O zoom já existia e ninguém o achava** -- `Ctrl+roda`, `Ctrl++`, `Ctrl+-` e três itens de
        menu (S-264) --, e o pedido "opção para aumentar e diminuir a fonte da aba" foi a medida
        disso. O desenho é o da barra de estado do WordCraft. A régua tem uma parada por **letra
        diferente** (`paradas_do_zoom`), e não uma por degrau; a porcentagem é a letra da vista
        sobre a letra sem zoom, e o clique nela volta a 100%. Os nomes que o leitor de tela anuncia
        vêm do catálogo, e o catálogo diz que o zoom "não muda o documento" -- é o que separa este
        controle do corpo do parágrafo, que muda.
        """
        from PyQt6.QtWidgets import QSlider, QToolButton

        zoom = QWidget(self._aba)
        linha = QHBoxLayout(zoom)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(2)
        self._paradas_do_zoom = paradas_do_zoom(tema.fonte_base()[0])

        def botao(texto: str, acao: str, alvo: Callable[[], object]) -> QToolButton:
            feito = QToolButton(zoom)
            feito.setText(texto)
            feito.setAccessibleName(comandos.nome_acessivel(acao))
            tecla = atalhos.acelerador(acao)
            dica_em(feito, f"{comandos.rotulo(acao)}\nTecla: {tecla}" if tecla else comandos.rotulo(acao))
            feito.clicked.connect(lambda _marcado=False: alvo())
            return feito

        self.botao_de_afastar = botao("−", "afastar_texto", self.afastar_texto)
        self.regua_do_zoom = QSlider(Qt.Orientation.Horizontal, zoom)
        self.regua_do_zoom.setRange(0, len(self._paradas_do_zoom) - 1)
        self.regua_do_zoom.setPageStep(1)
        self.regua_do_zoom.setAccessibleName("Zoom do texto")
        self.regua_do_zoom.setMaximumWidth(self._aba.fontMetrics().horizontalAdvance("M") * 10)
        self.regua_do_zoom.valueChanged.connect(self._zoom_pela_regua)
        self.botao_de_aproximar = botao("+", "aproximar_texto", self.aproximar_texto)
        self.porcentagem_do_zoom = botao("100%", "zoom_do_texto_normal", self.zoom_do_texto_normal)
        # Largura do maior valor possível: o rodapé não pula quando o número ganha um dígito.
        self.porcentagem_do_zoom.setMinimumWidth(self._aba.fontMetrics().horizontalAdvance("000%") + 12)
        for parte in (self.botao_de_afastar, self.regua_do_zoom, self.botao_de_aproximar, self.porcentagem_do_zoom):
            linha.addWidget(parte)
        self._mostrar_zoom()
        return zoom

    def _zoom_pela_regua(self, indice: int) -> None:
        """A régua mexida pela pessoa. A régua reposta por `_mostrar_zoom` chega com o sinal bloqueado."""
        self.aplicar_zoom(self._paradas_do_zoom[max(0, min(indice, len(self._paradas_do_zoom) - 1))])

    def _mostrar_zoom(self) -> None:
        """Põe a régua, a porcentagem e os dois botões no zoom que vale -- sem disparar nada."""
        base = tema.fonte_base()[0]
        paradas = self._paradas_do_zoom
        # O degrau gravado pode não ser parada (empatou com um vizinho no piso de legibilidade):
        # a régua mostra a parada de mesma letra, que é a mais próxima.
        indice = min(range(len(paradas)), key=lambda i: abs(paradas[i] - self._zoom_da_vista))
        self.regua_do_zoom.blockSignals(True)
        try:
            self.regua_do_zoom.setValue(indice)
        finally:
            self.regua_do_zoom.blockSignals(False)
        porcentagem = porcentagem_do_zoom(self._zoom_da_vista, base)
        self.porcentagem_do_zoom.setText(f"{porcentagem}%")
        self.regua_do_zoom.setAccessibleDescription(f"{porcentagem} por cento")
        self.botao_de_afastar.setEnabled(self._zoom_da_vista > paradas[0])
        self.botao_de_aproximar.setEnabled(self._zoom_da_vista < paradas[-1])

    def atualizar_status(self) -> None:
        """O rodapé da aba, refeito a cada mudança do documento e a cada gravação.

        A frase é de `ui/texto_declarado.frase_do_rodape`; aqui só se contam as miniaturas, que
        são do desenho e não do documento.
        """
        diagramas = self._aba.documento.diagramas
        cad = self._aba.caderno.caderno_da_tela()
        guardada = None if cad is None or self._aba._pagina is None else cad.estado(self._aba._pagina.pagina)
        self.status.setText(
            frase_do_rodape(
                folha=None if self._aba._pagina is None else int(self._aba._pagina.pagina),
                trechos=len(self._aba.documento.corridas),
                diagramas=len(diagramas),
                miniaturas=sum(1 for c in diagramas if self._aba.miniaturas.tem_miniatura(c)),
                por_gravar=self._aba.tem_alteracoes,
                correcoes=self._aba._correcoes,
                do_caderno=guardada is not None,
                conferidas=None if cad is None else (cad.conferidas(), self.quantas_folhas()),
                # A hora vem do índice do caderno (`gravada_em`, ISO), e não de um relógio do painel:
                # é a hora da gravação de verdade, e a folha reaberta amanhã diz a de hoje.
                gravado_as=guardada.gravada_em[11:16] if guardada is not None else "",
            )
        )
        self._mostrar_selo()

    def _mostrar_selo(self) -> None:
        """O selo da folha (S-710): o que a leitura sabe de si, de cima do texto. Some sem aviso nenhum.

        **Lê do documento, e não da última leitura**: a origem dele atravessa o arquivo, então a folha
        reaberta do caderno amanhã continua dizendo que não foi lida inteira.
        """
        origem = self._aba.documento.origem
        avisos = () if origem is None else origem.avisos
        self._aba.selo_da_folha.setText("\n".join(aviso.mensagem for aviso in avisos))
        # A cor é lida aqui, e não na montagem: a pele pode ter mudado desde a última folha.
        self._aba.selo_da_folha.setStyleSheet(f"color: {tema.cor_atual(tokens.ATENCAO)}; font-weight: 600; padding: 4px 8px;")
        self._aba.selo_da_folha.setVisible(bool(avisos))

    def ir_ao_campo_de_folha(self) -> None:
        """O clique na folha do rodapé (S-655): a aba Leitura da fita à frente e o campo da folha pronto."""
        from chess_diagram_ocr.ui import fita_do_texto

        leitura = next(i for i, aba in enumerate(fita_do_texto.ABAS) if "@folha" in (it for g in aba.grupos for it in g.itens))
        if self._aba.fita.recolhida:
            self._aba.fita.definir_recolhida(False)
        self._aba.fita.setCurrentIndex(leitura)
        self._aba.leitura.campo_de_folha.setFocus()
        self._aba.leitura.campo_de_folha.selectAll()

    def quantas_folhas(self) -> int:
        """Quantas folhas o livro tem, pelo teto do campo; sem ele, até a última folha do caderno."""
        teto = int(self._aba.leitura.campo_de_folha.maximum())
        if teto < texto_leitura.TETO_DE_FOLHAS:
            return teto
        folhas = () if self._aba.caderno.aberto is None else self._aba.caderno.aberto.folhas()
        return folhas[-1].pagina + 1 if folhas else 0

    def contar_correcoes(self) -> None:
        """Refaz a conta das correções e o rodapé. Na pausa, na gravação e na abertura -- não por tecla."""
        self._aba._correcoes = len(correcao.correcoes(self._aba.documento)) if self._aba.documento.origem is not None else 0
        self.atualizar_status()

    # ---------------------------------------------------------------------------- a fonte de base

    def base_da_vista(self) -> tuple[int, str, str]:
        """A fonte de base **com o zoom da vista** (S-264).

        O zoom é um degrau somado ao corpo do sistema, e é aqui que ele entra na folha: toda
        corrida é desenhada por `formato_de` a partir desta base, então aplicá-lo só à fonte do
        editor -- como o porte fazia -- não mudava letra nenhuma, porque cada trecho sai com o seu
        corpo explícito. O degrau parte sempre da origem, nunca do que está na tela.
        """
        from chess_diagram_ocr.ui import tipografia

        tamanho, proporcional, monoespacada = tema.fonte_base()
        # A letra de leitura (S-632) troca só a proporcional: o papel DADO -- a notação -- continua
        # na monoespaçada nas três, porque `texto_formato._fonte` a escolhe pela outra metade da base.
        if self._familia_da_letra == "monoespacada":
            proporcional = monoespacada
        elif self._familia_da_letra == "serifada":
            proporcional = tema.familia_serifada(proporcional)
        return tipografia.corpo(self._zoom_da_vista, base=tamanho), proporcional, monoespacada

    # ------------------------------------------------------------------ a quebra de linha (S-265)

    @property
    def quebra(self) -> bool:
        """As linhas estão quebrando na largura da janela? É o que o estado guarda (S-291)."""
        return self._aba.editor.lineWrapMode() != QTextEdit.LineWrapMode.NoWrap

    def definir_quebra(self, quebrando: bool, *, avisar: bool = False) -> None:
        """Põe a quebra naquele estado. Silencioso por padrão.

        **Separada de `quebrar_linha` porque restaurar não é alternar.** A restauração da abertura
        põe o que a sessão anterior tinha, e uma frase no rodapé anunciando isso seria um recado
        sobre algo que a pessoa não acabou de fazer -- é a mesma razão do `avisar=False` de
        `aplicar_zoom`.
        """
        self._aba.editor.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth if quebrando else QTextEdit.LineWrapMode.NoWrap
        )
        if not avisar:
            return
        if quebrando:
            self._aba.estado.emit("As linhas voltam a quebrar na largura da janela.")
        else:
            self._aba.estado.emit("Linha inteira: use a rolagem de baixo para ver o fim das linhas longas.")

    def quebrar_linha(self) -> None:
        """Liga ou desliga a quebra na largura da janela (S-265)."""
        self.definir_quebra(not self.quebra, avisar=True)

    # ------------------------------------------------------------------- o zoom da vista (S-264)

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
        """Um passo de zoom, **de parada em parada** (S-630): o degrau que não muda a letra é pulado.

        Andar degrau a degrau fazia o `−` não mudar nada perto do piso de legibilidade, onde dois
        degraus dão a mesma letra -- e um clique que não muda nada parece controle quebrado.
        """
        atual = self._zoom_da_vista
        adiante = [parada for parada in self._paradas_do_zoom if (parada > atual if passo > 0 else parada < atual)]
        if not adiante:
            limite = self._paradas_do_zoom[-1] if passo > 0 else self._paradas_do_zoom[0]
            self._aba.estado.emit(f"O zoom do texto já está no limite ({limite:+d} degraus).")
            return
        self.aplicar_zoom(adiante[0] if passo > 0 else adiante[-1])

    def _zoom_ancorado(self, ponto: QPoint, passo: int) -> None:
        """O zoom da roda, **com a linha sob o ponteiro parada sob ele** (S-630).

        Sem âncora a folha cresce a partir do topo e o que a pessoa estava olhando foge para baixo
        a cada passo -- é a regra da roda do WordCraft. O caractere sob o ponteiro é lembrado antes
        e, depois do redesenho, a rolagem é acertada para ele voltar à mesma altura.
        """
        sob = self._aba.editor.cursorForPosition(ponto)
        posicao = sob.position()
        antes = self._aba.editor.cursorRect(sob)
        # Em que altura da linha o ponteiro estava: o meio da linha continua sendo o meio dela.
        fracao = (ponto.y() - antes.top()) / max(1, antes.height())
        self._mudar_zoom(passo)
        documento = self._aba.editor.document()
        barra = self._aba.editor.verticalScrollBar()
        if documento is None or barra is None or posicao >= documento.characterCount():
            return
        cursor = QTextCursor(documento)
        cursor.setPosition(posicao)
        depois = self._aba.editor.cursorRect(cursor)
        barra.setValue(barra.value() + round(depois.top() + fracao * depois.height()) - ponto.y())

    def aplicar_zoom(self, degraus: int, *, avisar: bool = True) -> None:
        """Troca a fonte de base do editor e redesenha.

        **Aqui o redesenho é barato, e é a diferença de fundo com o outro frontend.** Lá redesenhar
        zera a pilha de desfazer do Tk -- ela guarda índice, não conteúdo --, e por isso o zoom tem
        de refazer cada etiqueta de fonte à mão, com o cache de atributos de origem que a S-336
        conserta. Aqui a pilha é de documentos e sobrevive ao redesenho, então o zoom é uma fonte
        nova e um `EspelhoDaFolha.desenhar`.

        **Grampeia aqui** (S-291): os limites são desta aba, e validá-los no arquivo de estado os
        declararia num segundo lugar.
        """
        from chess_diagram_ocr.ui import tipografia

        degraus = max(ZOOM_MINIMO, min(ZOOM_MAXIMO, int(degraus)))
        self._zoom_da_vista = degraus
        selecao = self._aba.espelho.selecao_atual()
        fonte = self._aba.editor.font()
        fonte.setPointSize(tipografia.corpo(degraus, base=self.corpo_de_base))
        self._aba.editor.setFont(fonte)
        self._aba.espelho.desenhar(selecao=selecao)
        self._mostrar_zoom()
        if avisar:
            self._aba.estado.emit(f"Zoom do texto: {degraus:+d} degrau(s).")

    # ----------------------------------------------------------- o modo foco e as marcas (S-658)

    def alternar_modo_foco(self) -> None:
        """Só a folha: a fita e o painel de navegação somem, e a mesa esconde o visualizador. `Esc` sai."""
        self.modo_foco = not self.modo_foco
        self._aba.fita.setVisible(not self.modo_foco)
        self._aba.barra_do_foco.setVisible(self.modo_foco)
        if self.modo_foco:
            self._navegacao_antes_do_foco = self._aba.navegacao.isVisible()
            self._aba.navegacao.hide()
        elif self._navegacao_antes_do_foco:
            self._aba.navegacao.show()
        self._aba.foco_mudou.emit(self.modo_foco)
        self._aba.editor.setFocus()

    def alternar_marcas_de_formatacao(self) -> None:
        """¶ no fim do parágrafo e o ponto no espaço: é vista, não grava, e acha o espaço duplo do OCR."""
        self._marcas_de_formatacao = not self._marcas_de_formatacao
        self.aplicar_marcas()
        self._aba.fita.marcar({"marcas_de_formatacao": self._marcas_de_formatacao})

    def aplicar_marcas(self) -> None:
        """Repõe a opção do documento: `EspelhoDaFolha.desenhar` cria um `QTextDocument` novo a cada redesenho."""
        from PyQt6.QtGui import QTextOption

        documento = self._aba.editor.document()
        if documento is None:
            return
        opcao = documento.defaultTextOption()
        marcas = QTextOption.Flag.ShowTabsAndSpaces | QTextOption.Flag.ShowLineAndParagraphSeparators
        opcao.setFlags(opcao.flags() | marcas if self._marcas_de_formatacao else opcao.flags() & ~marcas)
        documento.setDefaultTextOption(opcao)

    def alternar_fita(self) -> None:
        """`Ctrl+F1`: recolhe a fita deixando só as abas, como no Word (S-652)."""
        self._aba.fita.alternar_recolhida()

    # ------------------------------------------------------------- o recado e as palavras (S-655)

    def mostrar_recado(self, frase: str) -> None:
        """A frase transitória toma o lugar das caixas do meio por 6 s, com o texto inteiro na dica."""
        self.recado.setText(frase)
        self.recado.setToolTip(frase)
        self.recado.show()
        self.status.hide()
        self.caixa_de_palavras.hide()
        self.caixa_do_lexico.hide()
        self._relogio_do_recado.start()

    def _apagar_recado(self) -> None:
        self.recado.hide()
        self.status.show()
        self.caixa_de_palavras.show()
        self.caixa_do_lexico.setVisible(self._aba.correcao.conferindo_lexico)

    def contar_palavras_da_selecao(self) -> None:
        inicio, fim = self._aba.espelho.selecao_atual()
        total = self._palavras_da_folha()
        selecionadas = contar_palavras(self._aba.documento.para_texto()[inicio:fim]) if fim > inicio else None
        self.caixa_de_palavras.setText(frase_das_palavras(total, selecionadas) if total else "")

    def _palavras_da_folha(self) -> int:
        """A contagem da folha, cacheada pela edição: refeita só quando o documento é outro."""
        if self._palavras_cache[0] is not self._aba.documento:
            self._palavras_cache = (self._aba.documento, contar_palavras(self._aba.documento.para_texto()))
        return self._palavras_cache[1]

    # ----------------------------------------------------------------- a letra de leitura (S-632)

    @property
    def familia_da_letra(self) -> str:
        return self._familia_da_letra

    def definir_familia_da_letra(self, familia: str) -> None:
        """A letra de leitura (S-632). Vista, e não documento: redesenha sem tornar a folha «por gravar»."""
        familia = familia if familia in FAMILIAS_DA_LETRA else FAMILIA_DA_LETRA_PADRAO
        if familia == self._familia_da_letra:
            return
        self._familia_da_letra = familia
        self.redesenhar()

    def mudar_familia_da_letra(self) -> None:
        self.definir_familia_da_letra(proxima_familia_da_letra(self._familia_da_letra))
        nome = NOME_DA_FAMILIA[self._familia_da_letra]
        familia = self._aba.espelho.base[1] if self._aba.espelho.base is not None else ""
        self._aba.estado.emit(f"Letra da folha: {nome} ({familia})." if familia else f"Letra da folha: {nome}.")

    def redesenhar(self) -> None:
        """Redesenha a folha como está, por uma mudança de vista: nem pilha, nem rascunho, nem caderno."""
        barra = self._aba.editor.verticalScrollBar()
        rolagem = barra.value() if barra is not None else 0
        self._aba.espelho.desenhar(selecao=self._aba.espelho.selecao_atual())
        if barra is not None:
            barra.setValue(rolagem)
        self.atualizar_status()

    # ---------------------------------------------------------------- os eventos da folha (S-825)

    def clique_no_rodape(self, _evento: QEvent) -> bool:
        """O clique na folha do rodapé leva ao campo da folha (S-655), com qualquer botão."""
        self.ir_ao_campo_de_folha()
        return True

    def folha_mudou_de_tamanho(self, _evento: QEvent) -> bool:
        """O estado vazio acompanha a área da folha; o `Resize` segue para o editor."""
        self._aba.vazio.setGeometry(self.area_da_folha())
        return False

    def roda_na_folha(self, evento: QEvent) -> bool:
        """Ctrl+roda é o zoom da vista (item 13); sem `Ctrl` a roda rola a folha.

        O `QTextEdit` responderia mudando a fonte do editor -- que nenhuma letra segue, porque cada
        trecho sai com corpo explícito (S-264).
        """
        if not isinstance(evento, QWheelEvent) or not evento.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False
        passo = evento.angleDelta().y()
        if passo:
            self._zoom_ancorado(evento.position().toPoint(), +1 if passo > 0 else -1)
        return True

    # --------------------------------------------------------------------- o estado vazio (F9-C2)

    def mostrar_vazio(self) -> None:
        """Mostra o estado vazio enquanto não há folha nenhuma no editor (F9-C2, §7 item 14).

        Some no primeiro caractere, e é isso que o mantém fora da exportação: o `EstadoVazio` é um
        widget **sobre** o editor, e não texto dentro dele -- que era a razão de o ciclo 1 ter
        escolhido `placeholderText`, e que continua valendo.
        """
        self._aba.vazio.setGeometry(self.area_da_folha())
        # O vazio da mesa que virou a página para uma folha sem caderno diz **qual** folha (S-644).
        por_ler = self._aba._folha_por_ler
        self._aba.vazio.titulo.setText(strings.TEXTO_VAZIO_TITULO if por_ler is None else strings.folha_por_ler(por_ler + 1))
        self._aba.vazio.frase.setText(strings.TEXTO_VAZIO_FRASE if por_ler is None else strings.FOLHA_POR_LER_FRASE)
        if self._aba.vazio.botao is not None:
            self._aba.vazio.botao.setText(
                comandos.rotulo_de_botao("ler_folha") if por_ler is None else strings.ler_a_folha(por_ler + 1)
            )
        self._aba.vazio.setVisible(not self._aba.editor.toPlainText().strip())

    def area_da_folha(self) -> QRect:
        """O retângulo da área de desenho do editor, sem o `Optional` de `viewport()`."""
        folha = self._aba.editor.viewport()
        return folha.rect() if folha is not None else self._aba.editor.rect()
