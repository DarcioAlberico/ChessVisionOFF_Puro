"""A tabela do segundo frontend, montada das mesmas `Coluna` (S-153/S-501).

**A declaração não é reescrita.** `ui/tabela.py` diz o que cada coluna é -- chave, título,
largura, se é número, se estica -- e daí saem o alinhamento, a largura mínima e a resposta a "esta
tabela precisa rolar para o lado?". Quatro funções puras, afirmadas sem abrir janela desde a
S-153. Este módulo as chama; o que ele escreve é o `QTreeWidget` e nada mais.

**Metade do defeito da S-153 o Qt não tem, e a outra metade ele tem igual.**

A barra horizontal ausente era um defeito do Tk: o `ttk.Treeview` encolhe as colunas até
`minwidth` (20 px de fábrica) antes de admitir que não cabe, então oito colunas em 940 px viravam
oito colunas de 20 px e a barra **nunca aparecia**. O `QTreeWidget` põe a barra sozinho quando a
soma das seções passa da vista -- desde que as seções não encolham, que é o que
`ResizeMode.Interactive` garante e o que este módulo declara.

O que **não** vem de graça é a largura mínima por coluna: o `QHeaderView` tem um
`minimumSectionSize` único para a tabela inteira, e não um por seção. Sem isso, arrastar o
separador de "Motivo" até 5 px é possível, e o texto que diz o que conferir volta a ser o que não
se pode ler. Ver `_LimiteDeSecao`.

**E o alinhamento vale pela mesma razão de lá:** `1623.8` e `40` alinhados à esquerda só se
comparam lendo os dígitos um a um, e numa fila ordenada por prioridade comparar por magnitude é a
leitura inteira.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem, QWidget

from chess_diagram_ocr.ui.tabela import (
    ANCORA_NUMERO,
    Coluna,
    ancora,
    largura_minima,
    largura_total,
    precisa_de_barra_horizontal,
)

logger = logging.getLogger(__name__)

__all__ = [
    "Coluna",
    "TabelaQt",
    "alinhamento",
    "largura_total",
    "montar",
    "precisa_de_barra_horizontal",
]

_ALINHAMENTO: dict[str, Qt.AlignmentFlag] = {
    ANCORA_NUMERO: Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
}
"""`âncora do Tk -> alinhamento do Qt`. Só o número diverge do padrão; o texto já encosta à
esquerda em ambos, e declará-lo seria escrever o padrão duas vezes."""


def alinhamento(coluna: Coluna) -> Qt.AlignmentFlag:
    """Para que lado o conteúdo desta coluna encosta, na linguagem do Qt.

    A decisão continua sendo de `ui/tabela.ancora`: aqui só se traduz `"e"`/`"w"` para a flag.
    Perguntar `coluna.numerica` direto seria a mesma resposta por um caminho paralelo, e o
    caminho paralelo é o que diverge quando alguém acrescenta um terceiro tipo de coluna.
    """
    return _ALINHAMENTO.get(
        ancora(coluna), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )


class _LimiteDeSecao(QObject):
    """Impede que uma seção seja arrastada abaixo da largura mínima da coluna dela.

    **O `QHeaderView` só tem um mínimo para a tabela inteira** (`minimumSectionSize`), e as
    colunas desta tabela não têm o mesmo mínimo: `largura_minima` dá a largura cheia para as
    colunas normais e um terço para a elástica -- porque é a elástica que devolve espaço às
    outras quando a janela aperta, e é ela que a linha de detalhe cobre por baixo.

    Sem isto, arrastar o separador de "Motivo" até 5 px é possível, e o texto que diz o que
    conferir volta a ser o que não se pode ler -- que é o defeito fotografado na S-153, chegando
    pela mão em vez de pelo layout.

    Nasce filho do cabeçalho para não ser coletado, como todo ouvinte deste pacote.
    """

    def __init__(self, cabecalho: QHeaderView, minimos: Sequence[int]) -> None:
        super().__init__(cabecalho)
        self._cabecalho = cabecalho
        self._minimos = list(minimos)
        self._ajustando = False
        cabecalho.sectionResized.connect(self._conferir)

    def _conferir(self, indice: int, _antes: int, depois: int) -> None:
        # A guarda é contra a recursão: `resizeSection` emite `sectionResized` de novo, e sem ela
        # a primeira correção dispara a segunda para sempre.
        if self._ajustando or not 0 <= indice < len(self._minimos):
            return
        minimo = self._minimos[indice]
        if depois >= minimo:
            return
        self._ajustando = True
        try:
            self._cabecalho.resizeSection(indice, minimo)
        finally:
            self._ajustando = False


class _Linha(QTreeWidgetItem):
    """Uma linha que sabe comparar-se pela coluna em que a tabela está ordenada.

    O `QTreeWidgetItem` compara **texto**, e numa coluna de Elo isso põe `900` depois de `2882`
    e o travessão de "sem Elo" no meio dos números. `Coluna.numerica` já diz quais colunas são
    número -- é a mesma declaração que decide o alinhamento --, e aqui ela decide a ordem.

    A célula sem número (`—`, ou vazia) vai para o **fim** nos dois sentidos, e não para o
    começo: ela não é um valor pequeno, é a ausência de valor, e uma ordenação por Elo que
    começasse pelas partidas sem Elo responderia a pergunta errada.
    """

    def __init__(self, valores: Sequence[str], colunas: Sequence[Coluna]) -> None:
        super().__init__(list(valores))
        self._numericas = {indice for indice, coluna in enumerate(colunas) if coluna.numerica}

    def __lt__(self, outro: object) -> bool:
        arvore = self.treeWidget()
        cabecalho = arvore.header() if arvore is not None else None
        coluna = arvore.sortColumn() if arvore is not None else 0
        if not isinstance(outro, QTreeWidgetItem) or coluna not in self._numericas:
            return bool(super().__lt__(outro))  # type: ignore[operator]
        meu, dele = _numero(self.text(coluna)), _numero(outro.text(coluna))
        if meu is not None and dele is not None:
            return meu < dele
        if meu is None and dele is None:
            return False
        # Sem valor vai para o **fim** nos dois sentidos, e é por isso que o sentido é lido aqui:
        # o Qt aplica o mesmo `<` nos dois e inverte o resultado ao ordenar decrescente, então
        # uma resposta só poria as células vazias na frente em metade dos cliques.
        com_valor_primeiro = meu is not None
        crescente = cabecalho is None or cabecalho.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
        return com_valor_primeiro if crescente else not com_valor_primeiro


def _numero(texto: str) -> float | None:
    try:
        return float(texto.replace(",", ".").split()[0])
    except (ValueError, IndexError):
        return None


class TabelaQt(QTreeWidget):
    """Um `QTreeWidget` configurado pelas `Coluna` que recebeu. Guarda a declaração.

    Guardar as colunas é o que permite `preencher` alinhar cada célula sem que o ponto de
    chamada repita o alinhamento -- que é como a coluna numérica volta a nascer à esquerda em
    metade dos lugares.
    """

    def __init__(
        self, colunas: Iterable[Coluna], parent: QWidget | None = None, *, ordenavel: bool = False
    ) -> None:
        """`ordenavel` liga o clique no cabeçalho, e ele **não** é o padrão.

        É o gesto de toda sessão de quem usa uma base -- clicar em "Elo" para achar a partida mais
        forte da lista --, e é por isso que a busca da S-533 o liga. Mas ele não serve a toda
        tabela deste programa: a fila de livros (S-546) tem uma ordem própria, que é a de
        execução, e reordená-la faria a linha que está sendo lida saltar de lugar enquanto a barra
        anda. Uma tabela que se reordena sozinha durante a operação é pior que uma que não ordena.
        """
        super().__init__(parent)
        self.colunas: tuple[Coluna, ...] = tuple(colunas)
        self.ordenavel = ordenavel
        self.setColumnCount(len(self.colunas))
        self.setHeaderLabels([coluna.titulo for coluna in self.colunas])
        # `show="headings"` do Tk: sem a coluna-árvore de recuo, que esta tabela não usa.
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)

        # `header()` e `headerItem()` são `Optional` nos stubs do PyQt, e nunca são `None` num
        # `QTreeWidget` construído. Sair cedo em vez de afirmar o contrário é o que mantém a
        # tabela montável mesmo num Qt que responda diferente -- ela sai sem alinhamento e sem
        # limite de seção, que é pior que o certo e melhor que uma janela que não abre.
        cabecalho = self.header()
        titulos = self.headerItem()
        if cabecalho is None or titulos is None:  # pragma: no cover - o Qt sempre os dá
            logger.warning("A tabela montou sem cabeçalho: as colunas ficam no padrão do Qt.")
            return

        # **Sem esticar a última**, que é o padrão do Qt e é o errado aqui: quem estica é a coluna
        # que `Coluna.elastica` declara -- a FEN no Dataset, o Motivo na Revisão --, e ela nem
        # sempre é a última. Deixar o padrão faria a última coluna comer a folga que era da
        # elástica, e a barra horizontal deixaria de aparecer quando ela devia.
        cabecalho.setStretchLastSection(False)
        if ordenavel:
            cabecalho.setSectionsClickable(True)
            self.setSortingEnabled(True)
        for indice, coluna in enumerate(self.colunas):
            modo = QHeaderView.ResizeMode.Stretch if coluna.elastica else QHeaderView.ResizeMode.Interactive
            cabecalho.setSectionResizeMode(indice, modo)
            if not coluna.elastica:
                cabecalho.resizeSection(indice, coluna.largura)
            titulos.setTextAlignment(indice, alinhamento(coluna))

        self._limite = _LimiteDeSecao(cabecalho, [largura_minima(c) for c in self.colunas])

    def preencher(self, linhas: Iterable[Sequence[object]]) -> None:
        """Troca o conteúdo inteiro, com cada célula no alinhamento da coluna dela.

        Linha com número de células diferente do de colunas **levanta**: uma linha curta que
        fosse aceita apareceria com as últimas colunas em branco, e quem olhasse concluiria que
        o dado está faltando quando o que houve foi a chamada errada.

        **Cada célula sai com o próprio texto como dica**, e é o que resolve a coluna estreita:
        dois livros de nome longo que só diferem no fim ficam visualmente idênticos com as
        reticências do Qt, e a fila da S-546 os mostra lado a lado dizendo que um deles falhou.
        O texto inteiro na dica é a leitura que a largura não cabe -- e custa uma atribuição por
        célula, contra a alternativa de medir a largura de cada uma para decidir.
        """
        # Com a ordenação ligada, o Qt reordena a cada `addTopLevelItem` -- inserir N linhas fica
        # quadrático, e a ordem de chegada (que é o desempate) se perde. Desligar durante o
        # preenchimento e religar é o que a própria documentação do Qt manda fazer.
        ordenando = self.isSortingEnabled()
        self.setSortingEnabled(False)
        self.clear()
        itens: list[QTreeWidgetItem] = []
        for linha in linhas:
            valores = [str(valor) for valor in linha]
            if len(valores) != len(self.colunas):
                raise ValueError(
                    f"a linha tem {len(valores)} célula(s) e a tabela tem {len(self.colunas)} coluna(s): "
                    f"{valores!r}"
                )
            item = _Linha(valores, self.colunas)
            # A posição de chegada viaja com a linha: com a ordenação ligada, a posição na tela
            # deixa de ser a posição na lista de quem preencheu, e `indexOfTopLevelItem` passaria
            # a devolver a linha errada -- abrindo outra partida, em silêncio. Ver `posicao_de`.
            item.setData(0, Qt.ItemDataRole.UserRole, len(itens))
            for indice, coluna in enumerate(self.colunas):
                item.setTextAlignment(indice, alinhamento(coluna))
                item.setToolTip(indice, valores[indice])
            itens.append(item)
        self.addTopLevelItems(itens)
        self.setSortingEnabled(ordenando)

    def posicao_de(self, item: QTreeWidgetItem | None) -> int:
        """Em que posição da lista que `preencher` recebeu esta linha estava, ou `-1`.

        **Não é `indexOfTopLevelItem`**, e a diferença aparece com a ordenação ligada: ali a
        posição na tela é a da ordenação escolhida, e quem tem uma lista de objetos ao lado da
        tabela precisa da posição original -- senão o duplo clique abre a partida da linha que
        calhou de estar naquela altura antes de a pessoa clicar no cabeçalho.
        """
        if item is None:
            return -1
        guardada = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(guardada, int):
            return guardada
        return self.indexOfTopLevelItem(item)

    def posicao_selecionada(self) -> int:
        """A posição original da linha marcada, ou `-1`. Ver `posicao_de`."""
        return self.posicao_de(self.currentItem())

    def precisa_rolar(self) -> bool:
        """Se a tabela não cabe na largura que ela tem agora.

        É `ui/tabela.precisa_de_barra_horizontal` perguntada sobre a largura de verdade. O Qt põe
        a barra sozinho; isto existe para o teste poder afirmar *que ela é necessária* na largura
        do piso da S-150, que é o critério de aceite -- e não para decidir coisa alguma.
        """
        vista = self.viewport()
        return precisa_de_barra_horizontal(self.colunas, vista.width() if vista else self.width())


def montar(pai: QWidget, colunas: Iterable[Coluna], *, ordenavel: bool = False) -> TabelaQt:
    """Cria a tabela e a devolve. O par de `ui/tabela.montar`, com a mesma assinatura de ideia.

    Não empacota: em Qt quem posiciona é o leiaute de quem chama, e um `addWidget` escondido
    aqui dentro tiraria do painel a decisão de onde a tabela fica -- que é justamente o que o
    `pack(fill=BOTH, expand=True)` de lá faz e que o outro frontend não tem como evitar.
    """
    return TabelaQt(colunas, pai, ordenavel=ordenavel)
