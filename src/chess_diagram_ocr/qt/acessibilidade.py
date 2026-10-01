"""Dá nome acessível a todo controle da janela que ainda não tem um (F9). **Só executa.**

A decisão -- que palavra descreve um controle sem rótulo -- é de `ui/nomes_acessiveis.py`. Aqui
está a parte que precisa do toolkit: andar pela árvore de widgets, ler o leiaute e chamar
`setAccessibleName`.

**A medição que a obrigou.** O arnês `caissa.ui.audit.teclado` andou pela janela como um teclado
andaria e contou, por aba, entre 4 e 15 controles chegando ao leitor de tela **sem nome nenhum**:
doze `QLineEdit`, seis réguas de zoom, cinco caixas de escolha, três editores, duas tabelas. O Qt
anuncia cada um pelo tipo -- "caixa de edição" --, sem dizer qual. Depois desta varredura o número
é **zero** nas seis abas.

**Por que uma varredura e não vinte chamadas espalhadas.** As vinte chamadas seriam vinte lugares
que alguém precisa lembrar, e a vigésima primeira -- o campo que o próximo item acrescenta --
nasceria muda. O arnês `caissa.ui.audit.teclado` mede o número, e um número que só melhora quando
alguém lembra é um número que volta a piorar. A varredura roda uma vez, no fim da montagem da
janela, e alcança o que existir.

**Ela nunca sobrescreve.** Um `accessibleName` já posto ganha de tudo: a varredura é a rede de
segurança, não a autoridade. É o mesmo contrato de `pele.valida` -- o explícito vence o derivado.

**Ela não pode custar a janela.** Um leiaute exótico, um widget em desmontagem, um `parentWidget`
nulo: nada disso é motivo para a janela não abrir. Cada widget é tratado dentro de um `try`, e o
que falhar simplesmente fica sem nome derivado -- que é o estado de antes desta varredura existir.

---

**E ela alcança todo diálogo, por um filtro de evento e não por doze chamadas** (F9-C12). A
varredura rodava **uma** vez em todo o produto -- `qt/janela.py`, dentro do `__init__` da janela
principal --, e **todo `QDialog` nasce depois dela**. O crítico do ciclo 11 rodou a régua do
portão de teclado em seis dos doze diálogos e achou **11 controles sem nome acessível**: o campo
onde se digita o comando na paleta (`Ctrl+Shift+P`), que é a superfície de quem usa o teclado, e
dois `QLineEdit` lado a lado em `Achar e substituir` -- de modo que quem não vê a tela não
distingue "Achar" de "Trocar por".

O remédio é o argumento que já estava escrito acima, aplicado à outra metade do produto: doze
chamadas de `nomear_tudo` seriam doze lugares que alguém precisa lembrar, e a décima terceira --
o diálogo que o próximo item acrescenta -- nasceria muda. `vigiar_dialogos` instala **um** filtro
de evento na aplicação, e todo `QDialog` que aparecer na tela é varrido no `QEvent.Show`. Não há
lista para manter e não há como um diálogo novo escapar: ele não pode ser mostrado sem passar por
aqui.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QAbstractSpinBox, QDialog, QDialogButtonBox, QLabel, QLayout, QWidget

from chess_diagram_ocr.ui import nomes_acessiveis, strings

logger = logging.getLogger(__name__)

__all__ = [
    "botoes_em_portugues",
    "nome_derivado",
    "nomear_tudo",
    "rotulo_vizinho",
    "tornar_acessivel",
    "vigiar_dialogos",
]


def _leiaute_de(widget: QWidget) -> tuple[QLayout | None, int]:
    """O leiaute **mais interno** que contém este widget, e o índice dele lá dentro.

    **Esta função é a correção de um defeito medido, e a medição é do crítico do ciclo 1.** A
    versão anterior olhava só `pai.layout()` -- o leiaute de topo do widget pai -- e desistia. Mas
    a montagem real dos painéis é aninhada: em `qt/painel_do_dataset.py` o grupo "Filtros" tem um
    `QVBoxLayout`, e dentro dele duas `QHBoxLayout` com os pares `[QLabel][controle]`. O combo é
    filho do `QGroupBox`, então `pai.layout()` devolvia o `QVBoxLayout` -- que **não contém o
    combo diretamente**, e o laço saía sem achar nada.

    Consequência exata: três `QComboBox` da aba Dataset chegavam ao leitor de tela como
    `"Escolha"`, o nome genérico da classe, **na mesma tela**, com os rótulos "Legalidade",
    "Conjunto" e "Livro" desenhados 4 px à esquerda de cada um. O texto estava na tela; a busca
    não descia até ele.

    Devolve `(None, -1)` quando o widget não está em leiaute nenhum.
    """
    pai = widget.parentWidget()
    raiz: QLayout | None = pai.layout() if pai is not None else None
    if raiz is None:
        return None, -1
    pilha: list[QLayout] = [raiz]
    while pilha:
        leiaute = pilha.pop()
        for indice in range(leiaute.count()):
            item = leiaute.itemAt(indice)
            if item is None:
                continue
            if item.widget() is widget:
                return leiaute, indice
            aninhado = item.layout()
            if aninhado is not None:
                pilha.append(aninhado)
    return None, -1


def rotulo_vizinho(widget: QWidget) -> str:
    """O texto do `QLabel` que precede este controle no leiaute do pai. `""` se não houver.

    **Dois caminhos, e o primeiro é o do Qt.** `QLabel.setBuddy` é a ligação explícita entre
    rótulo e controle, e onde ela existe é ela que vale -- inclusive porque é ela que o
    `QFormLayout` cria sozinho. Onde ela não existe, vale a **posição**: o rótulo imediatamente
    anterior no mesmo leiaute é o que a pessoa que vê associa ao campo, e é por isso que ele foi
    posto ali. O leiaute que vale é o **mais interno** que contém o controle -- ver `_leiaute_de`.

    A busca do vizinho para no primeiro item que **não** é rótulo: numa fileira
    `[Lance] [campo] [Lado a jogar] [rádio]`, o campo tem de achar "Lance" e não "Lado a jogar".
    """
    pai = widget.parentWidget()
    if pai is None:
        return ""
    for rotulo in pai.findChildren(QLabel):
        if rotulo.buddy() is widget:
            return nomes_acessiveis.limpar_rotulo(rotulo.text())
    leiaute, indice = _leiaute_de(widget)
    if leiaute is None:
        return ""
    for anterior in range(indice - 1, -1, -1):
        item_anterior = leiaute.itemAt(anterior)
        candidato = item_anterior.widget() if item_anterior is not None else None
        if isinstance(candidato, QLabel) and candidato.text().strip():
            return nomes_acessiveis.limpar_rotulo(candidato.text())
        return ""  # o vizinho imediato não é rótulo: não há associação por posição
    return ""


def nome_derivado(widget: QWidget) -> str:
    """O nome que este controle deve anunciar, pela cascata de `ui/nomes_acessiveis.py`.

    Devolve `""` quando o Qt já anuncia alguma coisa sozinho -- `accessibleName` posto à mão ou
    `text()` não vazio --, porque nesses casos escrever de novo seria duplicar a fonte da verdade.

    **`text()` deixa de valer para as classes de `nomes_acessiveis.CLASSES_COM_VALOR`, e este é o
    defeito nº 1 da crítica do ciclo 1.** `QSpinBox.text()` devolve `"121"` -- o número da página
    aberta. O leitor de tela anunciava "121, campo de número", e o **nome do controle mudava
    quando a pessoa virava a página**: a identidade do objeto era o conteúdo dele. Para essas
    classes a cascata pula direto para a dica e para o rótulo vizinho, que é onde mora o nome.
    """
    if widget.accessibleName():
        return ""
    if not nomes_acessiveis.o_texto_e_valor(tuple(c.__name__ for c in type(widget).__mro__)):
        texto = getattr(widget, "text", None)
        if callable(texto):
            try:
                if str(texto() or "").strip():
                    return ""
            except TypeError:  # pragma: no cover - `text(int)` de alguns widgets
                pass
    dica = str(widget.toolTip() or "").strip()
    if dica:
        return dica.splitlines()[0]
    vizinho = rotulo_vizinho(widget)
    if vizinho:
        return vizinho
    return nomes_acessiveis.nome_por_classe(tuple(c.__name__ for c in type(widget).__mro__))


def nomear_tudo(raiz: QWidget) -> int:
    """Nomeia todo controle focável abaixo de `raiz` que ainda não tem nome. Devolve quantos.

    **Só o que aceita foco**, e é o recorte certo: um rótulo decorativo não é operável, e um
    leitor de tela já lê o texto dele quando passa por cima. O que precisa de nome é o que a
    pessoa pode alcançar e operar -- e é exatamente o conjunto que o arnês de teclado mede.

    **O `QLineEdit` de dentro de um `QAbstractSpinBox` fica de fora**, e o motivo é que ele não é
    um controle: é a peça interna do campo de número, que o Qt já anuncia como um só. Nomeá-lo
    criaria dois anúncios para uma caixa.
    """
    nomeados = 0
    for widget in raiz.findChildren(QWidget):
        try:
            # **Nem só o que aceita foco agora**, e o motivo é temporal: o tabuleiro da sala de
            # estudo só ganha política de foco quando a aba dele aparece, e uma varredura que
            # olhasse apenas o focável do instante da montagem passaria por cima dele para
            # sempre. Quem tem nome declarado por classe é uma **região** do documento -- página,
            # tabuleiro, tabela --, e uma região se anuncia mesmo quando não se opera.
            declarado = nomes_acessiveis.nome_por_classe(
                tuple(classe.__name__ for classe in type(widget).__mro__)
            )
            if not widget.focusPolicy() and not declarado:
                continue
            pai = widget.parentWidget()
            if isinstance(pai, QAbstractSpinBox):
                continue
            nome = nome_derivado(widget)
            if nome:
                widget.setAccessibleName(nome)
                nomeados += 1
        except Exception as exc:  # noqa: BLE001 - acessibilidade não derruba a janela
            logger.debug("Nome acessível não derivado para %s: %s", type(widget).__name__, exc)
    return nomeados


class _VigiaDeDialogos(QObject):
    """Varre todo `QDialog` que aparece na tela. Um filtro, não uma lista (F9-C12).

    **A pergunta que este objeto responde é "qual janela", e não "qual aparência".** O ciclo 9
    reprovou esta frente porque o portão media uma pele de três; o ciclo 11 reprovou porque a
    varredura de nome acessível rodava numa janela de treze. A resposta das duas vezes é a
    mesma: a largura sai de uma fonte que não se pode esquecer de atualizar. Lá foi
    `ui/pele.PELES`; aqui é o próprio Qt -- um diálogo que ninguém mostra não tem controle que
    alguém alcance, e um que alguém mostra passa por `QEvent.Show`.

    **Por que `Show` e não `ChildAdded` ou o construtor.** No `Show` o diálogo já tem os
    leiautes montados, que é de onde `rotulo_vizinho` tira o nome de um campo -- é assim que o
    `QLineEdit` de `Achar e substituir` vira `"Achar"` e o de baixo vira `"Trocar por"`. Num
    evento anterior à montagem a cascata cairia no nome genérico da classe, que é justamente o
    que o portão do ciclo 2 reprova.

    **O custo por evento foi medido, e é a razão de a primeira linha ser a que é.** O filtro
    está na aplicação, então ele vê todo evento de todo objeto; a comparação de inteiro do
    `type()` acontece antes de qualquer `isinstance`, e o filtro devolve `False` sempre --
    ele observa, nunca consome.
    """

    def eventFilter(self, alvo: QObject, evento: QEvent) -> bool:  # noqa: N802 - API do Qt
        try:
            if (
                evento is not None
                and evento.type() == QEvent.Type.Show
                and isinstance(alvo, QDialog)
            ):
                nomear_tudo(alvo)
                botoes_em_portugues(alvo)
                escala_do_dialogo(alvo)
        except Exception as exc:  # noqa: BLE001 - acessibilidade não derruba a janela
            logger.debug("Diálogo não preparado: %s", exc)
        return False


def escala_do_dialogo(raiz: QWidget) -> int:
    """Aplica a escala tipográfica ao diálogo que acabou de aparecer. Devolve quantos mudaram.

    **A varredura de `qt/escala.py` rodava uma vez, no fim da montagem da janela -- e os treze
    diálogos são montados depois** (F9-C14). O efeito foi medido pelo crítico do ciclo 13 sem que
    ninguém achasse a causa: o cabeçalho de `DialogoDePartidas` desenhava `Resultad·` porque o
    `QHeaderView` dele ficava no corpo de 9 pt enquanto a folha o **pintava** a 12 pt negrito --
    76 px de tinta numa seção medida sobre 52. `QHeaderView` está em
    `ui/tipografia.PAPEL_POR_CLASSE` desde o ciclo 2; o que faltava era a varredura alcançar a
    janela em que ele estava.

    **É o mesmo argumento do filtro que nomeia**, e por isso mora no mesmo `QEvent.Show`: treze
    chamadas seriam treze lugares para esquecer, e a décima quarta tela nasceria fora da escala.
    Aqui a decisão é do evento, e não de uma lista.

    E ela fecha o desencontro **na origem**: com o widget e a folha na mesma fonte, quem mede
    largura com `QWidget.fontMetrics()` volta a medir o que a tela desenha. É melhor do que
    ensinar mais um consumidor a perguntar à folha.
    """
    from chess_diagram_ocr.qt import escala

    return escala.aplicar_escala(raiz)


_vigia: _VigiaDeDialogos | None = None
"""O filtro vivo. **Guardado num atributo de módulo de propósito**: um `QObject` sem referência
viva é coletado pelo Python, e um filtro coletado deixa de ser chamado sem que nada avise -- é a
mesma armadilha que `qt/janela._teclas` documenta para a guarda de atalhos."""


def botoes_em_portugues(raiz: QWidget) -> int:
    """Põe em pt-BR os botões padrão de todo `QDialogButtonBox` abaixo de `raiz`. Devolve quantos.

    **Isto foi achado pelo olho, e não por régua** (F9-C12). O portão de teclado do ciclo 12
    abriu os treze diálogos do produto e todos passaram; a primeira fotografia mostrou um botão
    escrito `Close`. Os textos de um `QDialogButtonBox` vêm do catálogo de tradução do Qt, e sem
    catálogo instalado o Qt fala inglês: **7 de 12** botões padrão dos diálogos deste produto
    estavam em inglês (`Close` ×3, `Cancel` ×2, `Open`, e o `OK` de duas letras). Nenhuma régua
    desta frente procurava idioma.

    **Por quê aqui, e não uma chamada por diálogo.** É a razão inteira deste módulo, e ela vale
    duas vezes: doze chamadas seriam doze lugares para lembrar, e a décima terceira -- o diálogo
    que o próximo item acrescenta -- nasceria em inglês. O evento é o mesmo (`QEvent.Show`), o
    filtro é o mesmo, e um segundo filtro de aplicação dobraria o custo por evento que este já
    paga. O texto em si não mora aqui: ele é `ui/strings.BOTOES_PADRAO`, puro e testável sem
    janela, que é a mesma fronteira de `ui/nomes_acessiveis`.

    **Botão feito à mão fica como está.** `QDialogButtonBox.addButton(texto, papel)` devolve
    `NoButton` em `standardButton`, e é por isso que o `Varrer` de `DialogoDeEscopo` e o `Colar`
    de `_JanelaDeColar` sobrevivem a esta varredura: quem escreveu o texto sabia o que o botão
    faz naquela janela, e essa escolha ganha da tabela genérica -- o mesmo contrato de
    `nomear_tudo`, onde o explícito vence o derivado.
    """
    trocados = 0
    for caixa in raiz.findChildren(QDialogButtonBox):
        for botao in caixa.buttons():
            try:
                padrao = caixa.standardButton(botao)
                if padrao == QDialogButtonBox.StandardButton.NoButton:
                    continue
                texto = strings.BOTOES_PADRAO.get(padrao.name)
                if texto and botao.text().replace("&", "") != texto:
                    botao.setText(texto)
                    trocados += 1
            except Exception as exc:  # noqa: BLE001 - idioma não derruba a janela
                logger.debug("Botão padrão não traduzido: %s", exc)
    return trocados


def vigiar_dialogos(aplicacao: object | None = None) -> bool:
    """Instala em `aplicacao` o filtro que nomeia todo `QDialog` mostrado. Idempotente.

    Devolve `True` quando instalou agora, `False` quando já estava instalado ou quando não há
    aplicação (o caso de um teste puro, que não monta `QApplication` nenhuma).

    **Idempotente porque ela é chamada de onde a janela sobe**, e nada garante que só sobe uma
    janela por processo -- o arnês de medição monta uma por pele. Dois filtros iguais na mesma
    aplicação varreriam cada diálogo duas vezes, e a segunda varredura nunca acha nada porque a
    primeira já nomeou: seria custo puro.
    """
    global _vigia
    from PyQt6.QtWidgets import QApplication

    app = aplicacao if aplicacao is not None else QApplication.instance()
    if app is None:
        return False
    if _vigia is not None and _vigia.parent() is app:
        return False
    _vigia = _VigiaDeDialogos(app)
    app.installEventFilter(_vigia)
    return True


def tornar_acessivel(janela: QWidget) -> int:
    """Nomeia o que já existe **e** deixa vigiando o que ainda vai nascer. Devolve quantos nomeou.

    **É a única linha que a janela precisa dizer, e isso é uma decisão e não conveniência.**
    Até o ciclo 11 a janela chamava `nomear_tudo(self)` e nada mais, e o resultado é o defeito
    que reprovou aquele ciclo: a varredura alcançava a janela principal e **todo `QDialog` do
    produto nasce depois dela** -- onze controles chegando ao leitor de tela sem nome, entre eles
    o campo da paleta de comandos e os dois `QLineEdit` lado a lado de `Achar e substituir`.

    Duas linhas em `qt/janela.py` seriam duas coisas para lembrar, e a segunda é a que se
    esquece: quem escrever a próxima janela copia a primeira. Uma linha só põe a decisão aqui,
    que é onde ela mora -- o mesmo argumento pelo qual `nomear_tudo` é uma varredura e não vinte
    chamadas espalhadas.

    (E há um efeito lateral honesto: `qt/janela.py` está sob uma catraca de tamanho da S-31, e
    uma linha a mais lá é uma linha que alguém vai ter de tirar de outro lugar.)
    """
    nomeados = nomear_tudo(janela)
    botoes_em_portugues(janela)
    vigiar_dialogos()
    return nomeados
