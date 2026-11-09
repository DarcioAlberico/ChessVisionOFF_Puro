"""As ferramentas de correção da aba de texto: o léxico, o pincel, a busca, os símbolos e a navegação (S-865).

**Saiu de `qt/painel_de_texto.py` com o estado delas** -- a conferência ligada e as palavras que ela
marcou, as ignoradas desta folha, o pincel armado, a janela de busca aberta, a paleta de glifos com
os usados por último --, e com a `JanelaDeBusca`. Quem acha é `text/busca.py`, quem diz o que está
fora do léxico é `text/dicionario.py`, e quem sugere é `text/sugestao.py`; aqui fica o desenho do
que eles devolvem, e toda troca de texto passa pela pilha do `EspelhoDaFolha`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QPoint, Qt
from PyQt6.QtGui import QAction, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.painel_de_navegacao import CORRECOES, FOLHAS, RESULTADOS
from chess_diagram_ocr.qt.vazio import EstadoVazio
from chess_diagram_ocr.text import busca, correcao, rico
from chess_diagram_ocr.ui import espaco, estilos, strings, tokens
from chess_diagram_ocr.ui.texto_declarado import codigo_unicode, fora_do_livro, frase_do_lexico

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

logger = logging.getLogger(__name__)

__all__ = ["GLIFOS_RECENTES", "CorrecaoDoTexto", "JanelaDeBusca"]

GLIFOS_RECENTES = 20
"""Quantos glifos usados por último a paleta mostra primeiro (S-650), gravados no estado da sessão."""


class CorrecaoDoTexto(QObject):
    """O léxico, o pincel de formatação, a busca, a paleta de glifos e o painel de navegação da aba."""

    def __init__(self, aba: PainelDeTexto) -> None:
        super().__init__(aba)
        self._aba = aba
        self.conferindo_lexico = False
        """**Ligar, e não marcar uma vez** (S-293). Toda ferramenta que muda texto redesenha, e o
        redesenho apaga a marcação inteira -- então corrigir a primeira palavra marcada apagava as
        outras, e a pessoa tinha de reconferir a cada correção. Com o interruptor, a conferência se
        refaz sozinha depois de cada redesenho."""
        self._fora_do_lexico: list[tuple[int, int]] = []
        """As palavras marcadas pela conferência, em ordem -- o `F7` anda por elas (S-657)."""
        self.ignoradas: set[str] = set()
        """As palavras que a pessoa mandou ignorar nesta folha. Saem com a folha."""
        self._janela_de_busca: QWidget | None = None
        self._paleta: object | None = None
        self.glifos_recentes: list[str] = []
        self._pincel: rico.Atributos | None = None
        """A formatação que o pincel leva (S-653), ou `None` desarmado."""
        self._pincel_fixo = False
        self._pincel_armado_em = 0.0

    # -------------------------------------------------- a paleta lateral de glifos (S-248, S-650)

    def montar_paleta(self) -> QListWidget:
        """O painel lateral de glifos (S-248). Nasce escondido: ele é um caminho a mais.

        Uma lista e não uma grade de botões: os glifos são muitos, a lista rola, e clicar num item
        é o mesmo gesto que clicar num botão -- com a diferença de que a lista não precisa de uma
        decisão de quantas colunas.
        """
        from chess_diagram_ocr.text import paleta as _paleta

        self.paleta_lateral = QListWidget(self._aba)
        # **`"Lista"` não nomeia** (F9-C2, defeito nº 1): era o nome genérico da classe, e o
        # portão do `teclado.py` reprova eco do papel. O que esta lista guarda são os símbolos
        # de anotação que se inserem no texto.
        self.paleta_lateral.setAccessibleName("Símbolos de anotação")
        self.paleta_lateral.setFixedWidth(72)
        self.paleta_lateral.hide()
        self._simbolos_da_paleta = tuple(_paleta.MINIMA)
        self.encher_a_paleta()
        self.paleta_lateral.itemClicked.connect(lambda item: self.inserir_simbolo(item.text()))
        return self.paleta_lateral

    def encher_a_paleta(self) -> None:
        """Os 20 usados por último primeiro, e depois os de sempre (o conforto do WordCraft, S-650)."""
        self.paleta_lateral.clear()
        recentes = list(getattr(self, "glifos_recentes", []))
        for simbolo in [*recentes, *(s for s in self._simbolos_da_paleta if s not in recentes)]:
            self.paleta_lateral.addItem(simbolo)

    def _lembrar_glifo(self, simbolo: str) -> None:
        self.glifos_recentes = [simbolo, *(s for s in self.glifos_recentes if s != simbolo)][:GLIFOS_RECENTES]
        self.encher_a_paleta()

    # -------------------------------------------------------------- busca e substituição (S-343)

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
        janela = JanelaDeBusca(self._aba, substituindo=substituindo)
        self._janela_de_busca = janela
        return janela

    def aplicar_substituicao(self, ocorrencias: Sequence[busca.Ocorrencia], novo: str) -> int:
        """Troca as ocorrências escolhidas e redesenha. Devolve quantas trocou.

        O documento anterior vai para a pilha **antes** do redesenho: é o que faz `desfazer`
        reverter a substituição **inteira**, e não troca a troca.
        """
        novo_doc = busca.substituir(self._aba.documento, ocorrencias, novo)
        if novo_doc.para_texto() == self._aba.documento.para_texto():
            return 0
        self._aba.espelho.aplicar(novo_doc)
        return len(ocorrencias)

    # ----------------------------------------------------------- a conferência do léxico (S-266)

    def marcar_fora_do_lexico(self) -> None:
        """Liga a conferência do léxico da S-209. **Não corrige nada** (S-266).

        A frase da S-209 é a especificação inteira deste comando: *"palavra fora do dicionário é
        sinalizada, nunca aproximada da mais parecida"*. Dos 18 lances tão maltratados que caem no
        léxico, nenhum está no dicionário -- com correção automática seriam 18 lances reescritos
        como palavra.

        **Ligar, e não marcar uma vez** (S-293): toda ferramenta que muda texto redesenha, e o
        redesenho apaga a marcação -- então corrigir a primeira palavra marcada apagava as outras.
        """
        self.conferindo_lexico = True
        self.conferir_lexico(avisar=True)

    def limpar_marcas_do_lexico(self) -> None:
        """Desliga a conferência e tira as marcas. **Não é desfazer**: elas nunca foram documento."""
        self.conferindo_lexico = False
        self._pintar_lexico(())

    def conferir_lexico(self, *, avisar: bool) -> None:
        """Refaz a marcação. `avisar=False` no redesenho: a conta já foi dita quando se ligou.

        Um rodapé reescrito a cada tecla seria ruído -- e pior, esconderia o que a ferramenta que
        acabou de rodar tinha a dizer.
        """
        from chess_diagram_ocr.text import dicionario

        conteudo = self._aba.documento.para_texto()
        try:
            lexico = dicionario.carregar()
        except OSError as erro:
            logger.debug("Léxico não carregou: %s", erro)
            self._aba.estado.emit(f"O léxico não pôde ser carregado: {erro}")
            return
        if self._aba.caderno.aberto is not None:
            lexico = lexico | self._aba.caderno.aberto.lexico()
        achadas = dicionario.desconhecidas(conteudo, lexico, ignorar=fora_do_livro(self._aba.documento))
        achadas = tuple(a for a in achadas if a[2].lower() not in self.ignoradas)
        # **A palavra em digitação não é marcada até terminar** (S-657): com o cursor colado no fim
        # dela e nada que a feche, ela ainda está sendo escrita.
        cursor = self._aba.espelho.mapa.deslocamento(self._aba.editor.textCursor().position())
        achadas = tuple(
            a for a in achadas if not (a[0] <= cursor == a[1] and (a[1] == len(conteudo) or conteudo[a[1]].isalnum()))
        )
        self._pintar_lexico([(inicio, fim) for inicio, fim, _palavra in achadas])
        if avisar:
            total = len(dicionario.palavras_de(conteudo))
            self._aba.estado.emit(frase_do_lexico([palavra for _inicio, _fim, palavra in achadas], total))

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
        intervalos = list(intervalos)
        self._fora_do_lexico = sorted(intervalos)
        if hasattr(self._aba.vista, "caixa_do_lexico"):
            self._aba.vista.caixa_do_lexico.setText(f"{len(intervalos)} fora do léxico")
            self._aba.vista.caixa_do_lexico.setVisible(self.conferindo_lexico and not self._aba.vista.recado.isVisible())
        for inicio, fim in intervalos:
            selecao = QTextEdit.ExtraSelection()
            formato = QTextCharFormat()
            formato.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            formato.setUnderlineColor(QColor(tema.cor_atual(tokens.PROBLEMA_TEXTO)))
            selecao.format = formato
            cursor = QTextCursor(self._aba.editor.document())
            cursor.setPosition(self._aba.espelho.mapa.posicao(inicio))
            cursor.setPosition(self._aba.espelho.mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
            selecao.cursor = cursor
            seletores.append(selecao)
        self._aba.editor.setExtraSelections(seletores)

    # ------------------------------------------------------------ os símbolos e a paleta (S-248)

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
        inicio, _fim = self._aba.espelho.intervalo()
        fora = bool(self._paleta_de_glifos().marca(simbolo))  # type: ignore[attr-defined]
        self._lembrar_glifo(simbolo)
        depois = inicio + len(simbolo)
        self._aba.espelho.aplicar(rico.inserir(self._aba.documento, inicio, simbolo, fora_do_modelo=fora), selecao=(depois, depois))
        self._aba.editor.setFocus()

    def _menu_de_simbolos(self, simbolos: tuple[str, ...]) -> QMenu:
        """A lista junto do ponteiro. **Marca o que o modelo não lê**, e é o item.

        Um glifo que o classificador não conhece continua sendo inserível -- ele vai para o
        `.cvtxt` e para a exportação --, mas quem o insere precisa saber que a folha lida nunca vai
        trazê-lo de volta. A marca é do `text/paleta.py`, e não escrita aqui.
        """
        from PyQt6.QtGui import QAction, QCursor
        from PyQt6.QtWidgets import QMenu

        paleta_atual = self._paleta_de_glifos()
        menu = QMenu(self._aba)
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
        self._aba.editor.setFocus()

    # -------------------------------------------------------------- o painel de navegação (S-654)

    def alternar_navegacao(self) -> None:
        """Abre ou fecha o painel de navegação (S-654). O foco não sai do texto."""
        if self._aba.navegacao.isVisible():
            self._aba.navegacao.hide()
        else:
            self.mostrar_navegacao(None)
        self._aba.editor.setFocus()

    def mostrar_correcoes(self) -> None:
        """A lista das correções da folha (Revisão › Correções), na aba Correções do painel."""
        self.mostrar_navegacao(CORRECOES)

    def mostrar_navegacao(self, aba: int | None) -> None:
        self._aba.navegacao.show()
        if aba is not None:
            self._aba.navegacao.setCurrentIndex(aba)
        self.refazer_navegacao()

    def refazer_navegacao(self) -> None:
        """Refaz a aba à vista do painel. Na pausa da digitação, e não por tecla (S-654)."""
        if not self._aba.navegacao.isVisible():
            return
        aba = self._aba.navegacao.currentIndex()
        if aba == FOLHAS:
            self._aba.caderno.mostrar_indice()
        elif aba == RESULTADOS:
            self.refazer_resultados()
        elif aba == CORRECOES:
            linhas = []
            for achada in correcao.correcoes(self._aba.documento) if self._aba.documento.origem is not None else ():
                onde = rico.deslocamento_do_bloco(self._aba.documento, achada.bloco)
                linhas.append((-1 if onde is None else onde, f"«{achada.antes}» → «{achada.depois}»"))
            self._aba.navegacao.mostrar_correcoes(linhas)
        else:
            self._aba.navegacao.mostrar_titulos(rico.titulos(self._aba.documento))

    def refazer_resultados(self) -> None:
        agulha, inteira, curinga = self._aba.navegacao.opcoes_da_busca()
        texto = self._aba.documento.para_texto()
        try:
            achados = busca.achar(self._aba.documento, agulha, palavra_inteira=inteira, curinga=curinga)
        except (ValueError, re.error) as erro:
            self._aba.navegacao.mostrar_resultados(texto, (), recado=f"Curinga inválido: {erro}")
            return
        self._aba.navegacao.mostrar_resultados(texto, achados)

    def ir_para_intervalo(self, inicio: int, fim: int) -> None:
        """Uma linha do painel clicada: o cursor (ou a seleção) vai para lá, e a folha rola até ela."""
        self._aba.espelho.mostrar_intervalo(inicio, fim) if fim > inicio else self._aba.espelho.por_o_cursor(inicio)

    # ------------------------------------------------------------ o pincel de formatação (S-653)

    def pincel_de_formatacao(self) -> None:
        """Um clique arma o pincel para um uso; o segundo clique logo em seguida o fixa; `Esc` desarma."""
        from PyQt6.QtWidgets import QApplication

        agora = self._aba._relogio()
        if self._pincel is not None:
            if agora - self._pincel_armado_em <= QApplication.doubleClickInterval() / 1000:
                self._pincel_fixo = True
                self._aba.estado.emit("Pincel fixo: cada seleção recebe a formatação. Esc desarma.")
                return
            self._desarmar_pincel()
            return
        self.copiar_formato()
        self._pincel_armado_em = agora

    def copiar_formato(self) -> None:
        """`Ctrl+Shift+C`: guarda a formatação do começo da seleção e arma o pincel."""
        inicio, _fim = self._aba.espelho.intervalo()
        atributos = rico.atributos_em(self._aba.documento, inicio)
        if atributos is None:
            self._aba.estado.emit("Não há trecho de onde copiar a formatação.")
            return
        self._pincel = atributos
        self._pincel_fixo = False
        self._pincel_armado_em = self._aba._relogio()
        folha = self._aba.editor.viewport()
        if folha is not None:
            folha.setCursor(Qt.CursorShape.PointingHandCursor)
        self._aba.fita.marcar({"pincel_de_formatacao": True})
        self._aba.estado.emit("Pincel armado: selecione o trecho que recebe a formatação (Esc desarma).")

    def colar_formato(self) -> None:
        """`Ctrl+Shift+V`: pinta a seleção com a formatação guardada, sem desarmar o pincel fixo."""
        if self._pincel is None:
            self._aba.estado.emit("Não há formatação copiada: use o pincel ou Ctrl+Shift+C antes.")
            return
        inicio, fim = self._aba.espelho.intervalo()
        comeco, final = rico.intervalo_de_paragrafo(self._aba.documento, inicio, fim)
        inteiros = fim > inicio and (comeco, final) == (inicio, fim)
        self._aba.espelho.rotulo_corrente = "Pincel de formatação"
        try:
            self._aba.espelho.aplicar(rico.pintar(self._aba.documento, inicio, fim, self._pincel, paragrafo=inteiros))
        finally:
            self._aba.espelho.rotulo_corrente = ""
        if not self._pincel_fixo:
            self._desarmar_pincel()

    def _desarmar_pincel(self) -> None:
        self._pincel = None
        self._pincel_fixo = False
        folha = self._aba.editor.viewport()
        if folha is not None:
            folha.unsetCursor()
        self._aba.fita.marcar({"pincel_de_formatacao": False})

    def sair_com_esc(self) -> bool:
        """`Esc` desarma o pincel, e depois sai do modo foco (S-653, S-658). Devolve se fez algo."""
        if self._pincel is not None:
            self._desarmar_pincel()
            self._aba.estado.emit("Pincel desarmado.")
            return True
        if self._aba.vista.modo_foco:
            self._aba.vista.alternar_modo_foco()
            return True
        return False

    # ------------------------------------------------------ três ferramentas de correção (S-659)

    def mover_paragrafo(self, passo: int) -> None:
        inicio, _fim = self._aba.espelho.intervalo()
        novo, onde = rico.mover_paragrafo(self._aba.documento, inicio, passo)
        if novo is self._aba.documento:
            self._aba.estado.emit("Não há parágrafo " + ("acima" if passo < 0 else "abaixo") + " para trocar de lugar.")
            return
        self._aba.espelho.aplicar(novo, selecao=(onde, onde))

    def codigo_unicode(self) -> None:
        """`Alt+X`: o código antes do cursor vira o caractere, e o caractere vira o código."""
        inicio, _fim = self._aba.espelho.intervalo()
        troca = codigo_unicode(self._aba.documento.para_texto()[:inicio])
        if troca is None:
            return
        apagar, escrever = troca
        depois = inicio - apagar + len(escrever)
        self._aba.espelho.aplicar(rico.editar(self._aba.documento, inicio - apagar, inicio, escrever), selecao=(depois, depois))

    # -------------------------------------------------------------- corrigir pelo léxico (S-657)

    def proxima_fora_do_lexico(self) -> None:
        """`F7`: vai à próxima palavra marcada depois do cursor, e a seleciona. Liga a conferência se preciso."""
        if not self.conferindo_lexico:
            self.marcar_fora_do_lexico()
        if not self._fora_do_lexico:
            self._aba.estado.emit("Nenhuma palavra fora do léxico nesta folha.")
            return
        _inicio, fim = self._aba.espelho.intervalo()
        seguinte = next(((i, f) for i, f in self._fora_do_lexico if i >= fim), self._fora_do_lexico[0])
        self._aba.espelho.mostrar_intervalo(*seguinte)

    def proxima_a_revisar(self) -> None:
        """`Shift+F7`: vai à próxima palavra marcada `revisar` depois do cursor, e a seleciona (S-718).

        **Pela marcação, e não pelo documento cru:** antes de gravar, a palavra que se acabou de corrigir ainda é
        `w` e `ite`, em duas corridas `revisar`, e o gesto parava nos pedaços. A tinta na tela continua até gravar.
        """
        marcas = rico.intervalos_a_revisar(correcao.com_procedencia_humana(self._aba.documento))
        if not marcas:
            self._aba.estado.emit(strings.NADA_A_REVISAR)
            return
        _inicio, fim = self._aba.espelho.intervalo()
        self._aba.espelho.mostrar_intervalo(*next(((i, f) for i, f in marcas if i >= fim), marcas[0]))

    def _lexico_da_folha(self) -> frozenset[str]:
        """O léxico do programa mais o do livro (o caderno), em caixa baixa."""
        from chess_diagram_ocr.text import dicionario

        livro = self._aba.caderno.aberto.lexico() if self._aba.caderno.aberto is not None else frozenset()
        return dicionario.carregar() | livro

    def sugestoes_no_menu(self, menu: QMenu, ponto: QPoint) -> None:
        """Sobre uma palavra marcada: até cinco sugestões, acrescentar ao léxico do livro, ignorar (S-657)."""
        from chess_diagram_ocr.text import sugestao

        posicao = self._aba.espelho.mapa.deslocamento(self._aba.editor.cursorForPosition(ponto).position())
        achada = next(((i, f) for i, f in self._fora_do_lexico if i <= posicao <= f), None)
        if achada is None:
            return
        inicio, fim = achada
        palavra = self._aba.documento.para_texto()[inicio:fim]
        primeira = menu.actions()[0] if menu.actions() else None
        try:
            lexico = self._lexico_da_folha()
        except OSError:
            lexico = frozenset()
        for sugerida in sugestao.sugestoes(palavra, lexico):
            acao = QAction(sugerida, menu)
            acao.triggered.connect(lambda _m=False, s=sugerida, a=inicio, b=fim: self._aceitar_sugestao(a, b, s))
            menu.insertAction(primeira, acao)
        for rotulo, alvo in (
            (f"Acrescentar «{palavra}» ao léxico do livro", lambda: self._acrescentar_ao_lexico(palavra)),
            (f"Ignorar «{palavra}» nesta folha", lambda: self._ignorar_na_folha(palavra)),
        ):
            acao = QAction(rotulo, menu)
            acao.triggered.connect(lambda _m=False, f=alvo: f())
            menu.insertAction(primeira, acao)
        if primeira is not None:
            menu.insertSeparator(primeira)

    def _aceitar_sugestao(self, inicio: int, fim: int, nova: str) -> None:
        """A troca pelo clique: um passo de desfazer, e uma correção, porque o bloco fica (S-245)."""
        self._aba.espelho.rotulo_corrente = "Sugestão do léxico"
        try:
            self._aba.espelho.aplicar(rico.substituir_intervalo(self._aba.documento, inicio, fim, nova), selecao=(inicio + len(nova),) * 2)
        finally:
            self._aba.espelho.rotulo_corrente = ""
        self._aba.vista.contar_correcoes()

    def _acrescentar_ao_lexico(self, palavra: str) -> None:
        if self._aba.caderno.aberto is None or not self._aba.caderno.aberto.acrescentar_ao_lexico(palavra):
            self._aba.estado.emit("Sem caderno de livro aberto, não há léxico do livro onde acrescentar.")
            return
        self._aba.estado.emit(f"«{palavra}» entrou no léxico deste livro: deixa de ser marcada nas folhas dele.")
        self.conferir_lexico(avisar=False)

    def _ignorar_na_folha(self, palavra: str) -> None:
        self.ignoradas.add(palavra.lower())
        self.conferir_lexico(avisar=False)


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
            self._painel.espelho.mostrar_intervalo(achada.inicio, achada.fim)

    def substituir_todos(self) -> None:
        """Troca **todas** as achadas de uma vez, e diz quantas foram.

        Uma só chamada, e não uma por ocorrência: a substituição inteira entra na pilha como um
        passo, e `Ctrl+Z` reverte a troca toda -- e não troca a troca.
        """
        if not self._achadas:
            self._painel.estado.emit("Não há ocorrência para substituir.")
            return
        trocadas = self._painel.correcao.aplicar_substituicao(self._achadas, self.campo_novo.text())
        self._painel.estado.emit(f"{trocadas} ocorrência(s) substituída(s).")
        self.procurar()
