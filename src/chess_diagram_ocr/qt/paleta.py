"""A paleta de comandos do segundo frontend: um campo, uma lista filtrada, Enter executa (S-503).

**A ordem do resultado não é reescrita.** `ui/filtro_de_comandos.py` diz quem entra na lista e em
que ordem -- o casamento por subsequência, o vão que separa "apertado" de "espalhado", o grupo por
trecho, a linha cinza que desce só no empate --, e essa é a metade que custou a medir. Este módulo
chama `inventario` e `filtrar`; o que ele escreve é o diálogo e nada mais.

**Duas coisas o Qt dá de graça e o Tk teve de amarrar.**

1. *Esc fecha.* É `QDialog.reject`, e do outro lado é um `bind` explícito em dois widgets.
2. *A lista rola até a seleção.* `setCurrentItem` já traz a linha à vista; lá é `see(alvo)`, e
   esquecê-lo faz a seta andar por linhas que não se vê andar.

**Uma o Qt não dá, e ela é a mesma dos dois lados: as setas moram no campo.** Quem tem o foco é o
campo -- senão não se digita --, e uma lista sem foco não recebe seta nenhuma. Do lado do Tk isso
é `campo.bind("<Down>")`; aqui é um `QObject` de filtro sobre o campo, e não `keyPressEvent` do
diálogo: o `QLineEdit` **ignora** `Up`/`Down` e o evento subiria sozinho até o diálogo, o que
funcionaria hoje e pararia de funcionar no dia em que o campo virasse um `QComboBox` editável --
que trata as duas teclas e não as deixa subir. Ver `_SetasNoCampo`.

**A linha cinza é por item e não por tag.** O `ttk.Treeview` pinta por tag (`TAG_DESABILITADO`), e
o Qt não tem tag: a cor vai em cada célula da linha, na montagem. É a mesma diferença que
`qt/tabela.py` registra no alinhamento, e o efeito de esquecê-la é o mesmo -- o comando
indisponível com a aparência do disponível, que é a metade do critério de aceite da S-231 que diz
*"cinza e com o motivo, e não some"*.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.tabela import TabelaQt
from chess_diagram_ocr.ui import espaco, tipografia, tokens
from chess_diagram_ocr.ui.filtro_de_comandos import (
    ALTURA_EM_LINHAS,
    COLUNAS,
    TITULO,
    Entrada,
    filtrar,
    inventario,
)

__all__ = ["RODAPE", "JanelaDaPaleta", "abrir"]

RODAPE = "Enter executa · ↑ ↓ navegam · Esc fecha"
"""O mesmo texto do outro frontend. Ele não é decoração: a paleta é a única janela do programa
cujo gesto inteiro é teclado, e sem a linha ninguém descobre que a seta anda."""


class _SetasNoCampo(QObject):
    """Faz `Up`/`Down`/`Enter` do campo andarem na lista em vez de irem para o campo.

    **Filtro sobre o campo, e não `keyPressEvent` do diálogo.** Hoje as duas formas funcionam: o
    `QLineEdit` ignora as setas verticais e o evento sobe sozinho. A diferença aparece no dia em
    que o campo virar um `QComboBox` editável -- que trata `Up`/`Down` como "item anterior" e não
    as deixa subir --, e o sintoma seria a seta parando de navegar sem ninguém ter tocado na
    paleta. Amarrar onde a versão do Tk amarra é o que faz as duas quebrarem juntas, quando
    quebrarem.

    Nasce filho do campo para não ser coletado, como todo ouvinte deste pacote.
    """

    def __init__(self, campo: QLineEdit, paleta: JanelaDaPaleta) -> None:
        super().__init__(campo)
        self._paleta = paleta
        campo.installEventFilter(self)

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if a1 is None or a1.type() != QEvent.Type.KeyPress or not isinstance(a1, QKeyEvent):
            return False
        tecla = a1.key()
        if tecla == Qt.Key.Key_Down:
            self._paleta.mover(1)
        elif tecla == Qt.Key.Key_Up:
            self._paleta.mover(-1)
        elif tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._paleta.executar()
        else:
            return False
        # Comer o evento é o `"break"` do outro lado: sem isto o `Enter` chegaria ao diálogo, que
        # o trata como o botão padrão e fecharia a paleta **depois** de `executar` ter decidido
        # não fechar -- que é exatamente o caso da linha cinza.
        return True


class JanelaDaPaleta(QDialog):
    """Um campo em cima, a lista embaixo, e o teclado inteiro no campo.

    A janela guarda `_visiveis` -- o que `filtrar` devolveu na última digitação -- em vez de reler
    a lista de widgets. É a mesma razão de `qt/legenda.py`: a linha da tela é texto formatado
    (`Entrada.no_texto` cola o motivo no rótulo), e voltar dela para a entrada exigiria desfazer a
    formatação, que é a forma de a seleção apontar para o comando errado no dia em que o formato
    mudar.
    """

    def __init__(
        self,
        pai: QWidget | None,
        amarrados: Mapping[str, Callable[[], object]],
        *,
        motivos: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(pai)
        self.setWindowTitle(TITULO)

        self._amarrados = dict(amarrados)
        self._entradas = inventario(amarrados, motivos=motivos)
        self._visiveis: tuple[Entrada, ...] = ()

        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.folga())

        self.campo = QLineEdit(self)
        self.campo.setPlaceholderText("Digite para achar um comando")
        fora.addWidget(self.campo)

        # `TabelaQt` e não um `QTreeWidget` à mão: a largura mínima por seção e a coluna que
        # estica são as regras da S-153, e escrevê-las de novo aqui é como o projeto chegou a
        # duas tabelas com o mesmo defeito.
        self.lista = TabelaQt(COLUNAS, self)
        self.lista.setSelectionMode(TabelaQt.SelectionMode.SingleSelection)
        fora.addWidget(self.lista, 1)

        rodape = QLabel(RODAPE, self)
        rodape.setFont(tema.fonte_atual(tipografia.AUXILIAR))
        tema.pintar(rodape, "color", tokens.TEXTO_SECUNDARIO)
        fora.addWidget(rodape)

        self.campo.textChanged.connect(self._refiltrar)
        self.lista.itemDoubleClicked.connect(lambda *_: self.executar())
        self._setas = _SetasNoCampo(self.campo, self)

        self._refiltrar()
        self.campo.setFocus()
        self.resize(
            sum(coluna.largura for coluna in COLUNAS) + 2 * espaco.moldura(),
            self._altura_pedida(),
        )

    def _altura_pedida(self) -> int:
        """A altura que mostra `ALTURA_EM_LINHAS` sem rolar, mais o campo e o rodapé.

        O outro frontend pede as linhas ao `Treeview` (`height=` conta linhas) e deixa o Tk medir
        o resto; aqui a conta é explícita porque o `QTreeWidget` dimensiona em pixels. O número de
        linhas continua vindo da mesma constante -- é a decisão, e ela é de lá.
        """
        linha = tema.altura_de_linha_atual()
        return (ALTURA_EM_LINHAS + 1) * linha + 3 * espaco.folga() + 4 * espaco.moldura()

    # ------------------------------------------------------------------------ o que o teste lê

    def visiveis(self) -> tuple[Entrada, ...]:
        """As entradas desenhadas agora, na ordem em que estão na lista."""
        return self._visiveis

    def selecionada(self) -> Entrada | None:
        """A entrada sob a seleção, ou `None` quando a consulta não achou nada."""
        indice = self.lista.indexOfTopLevelItem(self.lista.currentItem())
        if indice < 0 or indice >= len(self._visiveis):
            return None
        return self._visiveis[indice]

    def digitar(self, consulta: str) -> None:
        """Escreve no campo como quem digita. O `textChanged` refiltra, e é o mesmo caminho."""
        self.campo.setText(consulta)

    # ---------------------------------------------------------------------------- a mecânica

    def _refiltrar(self, *_argumentos: object) -> None:
        self._visiveis = filtrar(self.campo.text(), self._entradas)
        self.lista.preencher(
            (entrada.no_texto, entrada.tecla, entrada.grupo) for entrada in self._visiveis
        )
        cinza = QBrush(QColor(tema.cor_atual(tokens.TEXTO_SECUNDARIO)))
        for posicao, entrada in enumerate(self._visiveis):
            if entrada.habilitado:
                continue
            item = self.lista.topLevelItem(posicao)
            if item is None:  # pragma: no cover - acabou de ser inserido
                continue
            for coluna in range(len(COLUNAS)):
                item.setForeground(coluna, cinza)
        self._selecionar(0)

    def _selecionar(self, indice: int) -> None:
        total = self.lista.topLevelItemCount()
        if not total:
            return
        alvo = self.lista.topLevelItem(max(0, min(indice, total - 1)))
        if alvo is None:  # pragma: no cover - o índice acabou de ser limitado
            return
        # `setCurrentItem` já rola até a linha; é o `see(alvo)` que o outro lado chama à mão.
        self.lista.setCurrentItem(alvo)

    def mover(self, passo: int) -> None:
        """Anda uma linha. Não dá a volta na ponta.

        Uma lista circular faz a última linha aparecer onde a primeira deveria estar, e numa lista
        que rola isso é indistinguível de não ter andado.
        """
        atual = self.lista.indexOfTopLevelItem(self.lista.currentItem())
        self._selecionar(max(atual, 0) + passo)

    def executar(self) -> None:
        """Roda o comando selecionado, se ele estiver vivo. Linha cinza não faz nada e não fecha."""
        entrada = self.selecionada()
        if entrada is None or not entrada.habilitado:
            return
        funcao = self._amarrados[entrada.acao]
        # Fecha **antes** de executar: metade destes comandos abre uma caixa de diálogo, e uma
        # paleta que continuasse por cima dela seria a janela pedindo duas respostas ao mesmo
        # tempo. É a mesma ordem do menu, que se recolhe antes de o comando rodar.
        self.accept()
        funcao()

    def fechar(self) -> None:
        """Sai sem executar nada. O mesmo que a tecla `Esc`, que o `QDialog` já trata."""
        self.reject()


def abrir(
    pai: QWidget,
    amarrados: Mapping[str, Callable[[], object]],
    *,
    motivos: Mapping[str, str] | None = None,
) -> JanelaDaPaleta:
    """Abre a paleta. Uma por vez: reabrir traz a que já está aberta para a frente.

    Mesma regra da legenda (S-165), e aqui ela vale mais: a tecla que abre é a mesma que se aperta
    quando nada parece ter acontecido, e sem isto o segundo `Ctrl+Shift+P` empilharia uma paleta
    sobre a outra com duas consultas diferentes.

    **Reabrir não recarrega o inventário**, e é de propósito: a paleta que já está aberta guarda a
    consulta digitada, e trocá-la por uma vazia seria a tecla de trazer para a frente apagando o
    que a pessoa acabou de escrever.
    """
    for filho in pai.findChildren(JanelaDaPaleta):
        filho.show()
        filho.raise_()
        filho.activateWindow()
        filho.campo.setFocus()
        return filho
    janela = JanelaDaPaleta(pai, amarrados, motivos=motivos)
    janela.show()
    return janela
