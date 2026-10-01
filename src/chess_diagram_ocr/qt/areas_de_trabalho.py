"""As áreas de trabalho: a faixa de abas com a aba `Livro` e as do acervo (OCR_UI passo 17, tarefa 3).

**Uma área de trabalho é onde se trabalha**: um dos quatro modos do painel principal (Resultado,
Estudo, Revisão, Texto -- `ui/abas.MODOS`) ou uma das abas do acervo (Dataset, Galeria e as duas
da suíte -- `ui/abas.DO_ACERVO`). A aba `Livro` não é uma área: é a casa dos quatro modos.

**Este widget é o único que sabe onde cada área mora.** A janela fala por nome (`mostrar_area`)
ou por painel (`mostrar`), e pergunta o que está à frente (`area_atual`) -- e nem a janela, nem
os testes, nem os portões da suíte precisam saber se aquele nome é uma aba ou um modo. É o que
deixou o estado guardar o mesmo nome de sempre (`Revisão`, e não `Livro`) e os portões varrerem
"cada painel à frente uma vez" com um só laço (`areas`).

A ordem de `areas()` é a que as oito abas tinham antes do passo (S-162): os modos, e depois o
acervo. Nada saiu; quatro mudaram de casa.
"""

from __future__ import annotations

from collections.abc import Mapping

from PyQt6.QtWidgets import QTabWidget, QWidget

from chess_diagram_ocr.qt.painel_principal import PainelPrincipal
from chess_diagram_ocr.ui import abas

__all__ = ["AreasDeTrabalho"]


class AreasDeTrabalho(QTabWidget):
    """A faixa de abas da janela, com a `Livro` montada e à frente."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # **"Abas" não nomeia nada** (F9-C2): é o eco do papel `PageTabList`, e um leitor de tela
        # já anuncia o papel logo em seguida. O que a pessoa precisa saber é o que este conjunto
        # de abas **é** dentro da janela -- o lado do trabalho, ao lado do lado do livro.
        self.setAccessibleName("Áreas de trabalho")
        self.principal = PainelPrincipal(self)
        self.addTab(self.principal, abas.LIVRO)

    # -------------------------------------------------------------------------------- perguntas

    def indice_da_aba(self, nome: str) -> int | None:
        """Onde está a aba com aquele nome. `None` para a que não existe (ou é um modo).

        Pelo **nome** e não pelo índice, porque índice não sobrevive a reordenar as abas -- e a
        S-162 é, literalmente, reordená-las. Compara com `nome_base` porque o rótulo na tela leva
        a contagem junto: `"Galeria (129)"` guardado não casaria com `"Galeria (54)"`.
        """
        base = abas.nome_base(nome)
        for indice in range(self.count()):
            if abas.nome_base(self.tabText(indice)) == base:
                return indice
        return None

    def area_atual(self) -> QWidget | None:
        """O painel à frente: o modo, quando a aba à frente é a `Livro`; a aba, senão."""
        atual = self.currentWidget()
        if atual is self.principal:
            return self.principal.painel_atual()
        return atual

    def nome_da_area_atual(self) -> str:
        """O nome que o estado guarda: o modo (`Revisão`) quando a `Livro` está à frente.

        É o nome que toda sessão anterior ao passo 17 já guardava, e é o que `mostrar_area` sabe
        reabrir no lugar certo -- o mesmo lugar, com outra casa.
        """
        if self.currentWidget() is self.principal:
            return self.principal.modo_atual()
        return abas.nome_base(self.tabText(self.currentIndex()))

    def areas(self) -> list[str]:
        """Os nomes de tudo o que `mostrar_area` alcança: os modos, depois as abas do acervo."""
        nomes = self.principal.modos()
        for indice in range(self.count()):
            if self.widget(indice) is not self.principal:
                nomes.append(abas.nome_base(self.tabText(indice)))
        return nomes

    # ----------------------------------------------------------------------------------- gestos

    def mostrar_area(self, nome: str) -> bool:
        """Traz para a frente a área daquele nome -- aba **ou modo**. Devolve se achou."""
        base = abas.nome_base(nome)
        if abas.e_modo(base):
            self.setCurrentWidget(self.principal)
            self.principal.definir_modo(base)
            return True
        indice = self.indice_da_aba(base)
        if indice is None:
            return False
        self.setCurrentIndex(indice)
        return True

    def mostrar(self, painel: QWidget) -> None:
        """Traz para a frente o painel que acabou de receber alguma coisa, seja modo ou aba."""
        modo = self.principal.modo_de(painel)
        if modo is not None:
            self.mostrar_area(modo)
            return
        indice = self.indexOf(painel)
        if indice >= 0:
            self.setCurrentIndex(indice)

    def definir_contagens(self, contagens: Mapping[str, int | None]) -> None:
        """Quanto trabalho cada área carrega, no rótulo dela -- aba ou botão de modo, a mesma
        regra pura de `ui/abas.rotulo`."""
        for indice in range(self.count()):
            nome = abas.nome_base(self.tabText(indice))
            if nome in contagens:
                self.setTabText(indice, abas.rotulo(nome, contagens[nome]))
        for nome in self.principal.modos():
            if nome in contagens:
                self.principal.definir_contagem(nome, contagens[nome])
