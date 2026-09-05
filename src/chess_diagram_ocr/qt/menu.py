"""A barra de menus do segundo frontend, da mesma declaração (S-161/S-501).

**`MENUS` não é reescrita, e é o item.** `ui/menu.py` declara os 7 menus e os 152 itens como
*dado* -- uma tupla de tuplas -- e é isso que torna a declaração verificável sem abrir janela.
Este módulo percorre a mesma tupla e monta um `QMenuBar`. Uma segunda declaração divergiria no
primeiro comando acrescentado, e o sintoma seria uma janela com um item que a outra não tem.

Para isto valer, `ui/menu.py` passou a importar `tkinter` **dentro** de `montar` e das quatro
funções que desenham. O docstring de lá já dizia, desde a S-161, que não há "nenhum `tkinter` até
`montar`"; o import de topo fazia daquilo meia verdade, e a S-501 a tornou literal.

**O rótulo continua vindo de `ui/comandos.py`.** É a fronteira que a S-324 fixou: `ui/menu.py`
decide *onde na barra*, o catálogo decide *o que o comando é*. Este módulo não escreve texto de
interface numa linha -- e o teste cobra isso.

---

**O acelerador é mostrado e não ligado, e essa é a única decisão não óbvia daqui.**

O caminho natural do Qt seria `acao.setShortcut(...)`: a `QAction` passa a mostrar `Ctrl+S` na
linha do menu **e** a responder à tecla. A segunda metade é o problema. Quem responde por tecla
neste frontend é `qt/atalhos.GuardaDeAtalhos`, e ela existe porque a S-20 e a S-294 exigem três
respostas que a `QAction` não tem: *trate*, *ceda ao campo em foco*, *ceda a quem declarou a tecla
para si*. Uma `QAction` com atalho ativo dispararia `←` com o cursor dentro do campo de FEN --
que é literalmente o defeito que a guarda existe para impedir.

`ShortcutContext.WidgetShortcut` numa ação que vive num menu fechado é o que resolve: o Qt
**desenha** o acelerador na linha e só o dispararia se o próprio menu tivesse o foco, o que não
acontece com o menu fechado. O texto aparece, a tecla continua sendo da guarda, e não há dois
donos para a mesma sequência.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtWidgets import QMenu, QMenuBar, QWidget

from chess_diagram_ocr.qt.atalhos import sequencia_qt
from chess_diagram_ocr.ui import atalhos, conjuntos, pele
from chess_diagram_ocr.ui import comandos as catalogo
from chess_diagram_ocr.ui import menu as declaracao

logger = logging.getLogger(__name__)

__all__ = ["BarraDeMenus", "montar"]


@dataclass
class BarraDeMenus:
    """A barra montada, mais o índice do que dá para mexer depois.

    **O índice é o que substitui o `BooleanVar`/`StringVar` do Tk.** Lá a marca de um interruptor
    mora numa variável do Tcl que o painel também segura, e o menu se atualiza sozinho quando ela
    muda. O Qt não tem esse laço: a marca é estado da `QAction`. Guardá-las por ação é o que
    permite ao painel dizer `barra.marcar("modo_bloco", ligado=True)` sem procurar o item na
    árvore de menus -- que é o que faria cada painel conhecer a estrutura da barra.
    """

    barra: QMenuBar
    acoes: dict[str, QAction] = field(default_factory=dict)
    grupos: dict[str, QActionGroup] = field(default_factory=dict)

    def marcar(self, acao: str, *, ligado: bool) -> None:
        """Põe ou tira a marca de um interruptor. Ignora ação que não é interruptor.

        Ignorar em vez de levantar porque quem chama é o painel ao **refletir** estado -- e um
        painel que reflete o estado de um comando que deixou de ter marca não pode derrubar a
        janela por causa disso. Quem levanta é `montar`, na montagem, que é onde o erro é do
        programa e não do momento.
        """
        item = self.acoes.get(acao)
        if item is not None and item.isCheckable():
            item.setChecked(ligado)

    def escolher(self, acao: str, valor: str) -> None:
        """Marca o valor em vigor num submenu de escolha (pele, densidade, conjunto de peças).

        Silencioso para valor desconhecido, pela razão de `marcar`: uma pele removida do registro
        deixaria o submenu sem marca, que é melhor que uma janela que não abre.
        """
        grupo = self.grupos.get(acao)
        if grupo is None:
            return
        for item in grupo.actions():
            item.setChecked(item.data() == valor)

    def escolhido(self, acao: str) -> str:
        """O valor marcado naquele submenu, ou `""`.

        **É o que substitui o `StringVar` do Tk, e é a razão de o comando continuar sem
        argumento.** Lá o radiobutton escrevia numa variável e o comando a lia; aqui a marca é
        estado da `QAction`, e quem a lê é este método. Passar o valor pelo comando obrigaria a
        tabela de comandos a ter duas assinaturas -- e ela é a mesma que o menu, a paleta e os
        atalhos consomem, os três chamando sem argumento nenhum.
        """
        grupo = self.grupos.get(acao)
        marcada = grupo.checkedAction() if grupo is not None else None
        return str(marcada.data()) if marcada is not None and marcada.data() is not None else ""


def _acao(
    pai: QMenu,
    item: declaracao.Item,
    comandos: Mapping[str, Callable[[], object]],
) -> QAction:
    """Uma linha de comando ou de interruptor. O rótulo vem do catálogo, a tecla vem da tabela."""
    acao = QAction(catalogo.rotulo(item.acao), pai)
    # `atalho_de` responde pela tabela da janela **e** pela da sala (S-527): o acelerador é só
    # mostrado (contexto de widget, abaixo), então uma tecla que só vale na sala não é ligada aqui
    # uma segunda vez -- quem a liga é a `QAction` da barra da sala.
    atalho = atalhos.atalho_de(item.acao)
    if atalho is not None:
        try:
            acao.setShortcut(QKeySequence(sequencia_qt(atalho.sequencia)))
            # Mostrado e não ligado -- ver o cabeçalho. Quem responde por tecla é a guarda.
            acao.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        except ValueError as exc:
            # Uma tecla que não traduz não pode custar a **linha do menu**: o comando continua
            # clicável, e o que se perde é o texto do acelerador. É a disciplina de `folha.aplicar`.
            logger.warning("Acelerador de %s não mostrado (%s).", item.acao, exc)

    funcao = comandos[item.acao]
    if item.tipo == declaracao.INTERRUPTOR:
        acao.setCheckable(True)
        # `triggered` e não `toggled`: `toggled` também dispara quando `marcar` reflete estado
        # vindo do painel, e aí o comando rodaria em resposta ao próprio efeito dele -- um laço
        # que no Tk não existe porque lá a variável e o comando são coisas separadas.
        acao.triggered.connect(lambda _marcado=False, f=funcao: f())
    else:
        acao.triggered.connect(lambda _checado=False, f=funcao: f())
    return acao


def _valores_de(tipo: str) -> Sequence[object]:
    """O registro que aquele submenu de escolha lista. Um por eixo de aparência.

    **Os três saem de um registro e não de uma lista escrita aqui**, e é a razão de `ui/pele.py` e
    `ui/conjuntos.py` existirem: acrescentar uma pele é acrescentar uma linha lá, e o menu a
    desenha sem que ninguém venha aqui.
    """
    if tipo == declaracao.APARENCIA:
        return pele.PELES
    if tipo == declaracao.CONJUNTO:
        return conjuntos.CONJUNTOS
    return pele.DENSIDADES


def _submenu_de_escolha(
    pai: QMenu,
    item: declaracao.Item,
    valores: Sequence[object],
    ao_escolher: Callable[[], object],
) -> tuple[QMenu, QActionGroup]:
    """O submenu de pele, de densidade ou de peças: um item marcável por valor, exclusivos.

    **Um montador para os três eixos**, e não um por eixo -- é a razão de `ui/menu.py`, e ela não
    muda de toolkit: peles, densidades e conjuntos são a mesma linha de menu com outra lista atrás.

    O valor fica no `data()` da ação e não no rótulo, porque `pele.Pele` separa `nome` de
    `rotulo` desde a S-166: o primeiro é chave e o segundo é texto de interface.
    """
    submenu = QMenu(catalogo.rotulo(item.acao), pai)
    grupo = QActionGroup(submenu)
    grupo.setExclusive(True)
    for valor in valores:
        if isinstance(valor, (pele.Pele, conjuntos.Conjunto)):
            nome, rotulo = valor.nome, valor.rotulo
        else:
            nome = str(valor)
            rotulo = pele.rotulo_de_densidade(nome)
        escolha = QAction(rotulo, submenu)
        escolha.setCheckable(True)
        escolha.setData(nome)
        escolha.triggered.connect(lambda _checado=False, f=ao_escolher: f())
        grupo.addAction(escolha)
        submenu.addAction(escolha)
    return submenu, grupo


def _submenu_recentes(
    pai: QMenu,
    item: declaracao.Item,
    recentes: Callable[[], Sequence[tuple[str, Callable[[], None]]]],
) -> QMenu:
    """Os livros recentes, refeitos **a cada abertura** do menu (S-156).

    `aboutToShow` é o `postcommand` do Tk, e a razão é a mesma: a lista de livros muda a cada PDF
    aberto, e um submenu montado uma vez mostraria o acervo de quando a janela subiu.
    """
    submenu = QMenu(catalogo.rotulo(item.acao), pai)
    submenu.aboutToShow.connect(lambda: _preencher_recentes(submenu, recentes))
    return submenu


def _preencher_recentes(
    submenu: QMenu, recentes: Callable[[], Sequence[tuple[str, Callable[[], None]]]]
) -> None:
    """Refaz o submenu. Sem livro nenhum, uma linha desabilitada que diz isso.

    A linha desabilitada não é enfeite: um submenu vazio no Qt é um retângulo de dois pixels, e
    quem o abre conclui que o menu está quebrado em vez de concluir que não abriu livro nenhum.
    """
    submenu.clear()
    try:
        itens = list(recentes())
    except Exception:  # noqa: BLE001 - ler o estado não pode derrubar o menu
        logger.exception("Não foi possível montar a lista de livros recentes.")
        itens = []
    if not itens:
        vazio = submenu.addAction("(nenhum livro aberto ainda)")
        if vazio is not None:
            vazio.setEnabled(False)
        return
    for rotulo, abrir in itens:
        acao = submenu.addAction(rotulo)
        if acao is not None:
            acao.triggered.connect(lambda _checado=False, f=abrir: f())


def montar(
    janela: QWidget,
    comandos: Mapping[str, Callable[[], object]],
    *,
    recentes: Callable[[], Sequence[tuple[str, Callable[[], None]]]] = list,
) -> BarraDeMenus:
    """Constrói a barra e a pendura na janela. Devolve a barra e o índice das ações.

    Levanta `KeyError` quando um item declarado não tem comando, e quando um item está fora do
    catálogo: **é a mesma trava de `ui/menu.montar`, e ela é o motivo de o menu ser confiável.**
    Um menu que desenha uma linha inerte é pior que um menu sem ela -- a pessoa conclui que a
    função existe e está quebrada.

    **Sem `interruptores` e sem `escolhas`**, ao contrário do outro `montar`, e a ausência é
    decisão. Lá eles são obrigatórios porque a marca mora num `BooleanVar`/`StringVar` que o menu
    precisa receber para desenhar; aqui a marca é estado da `QAction`, e quem a define depois é
    `BarraDeMenus.marcar` / `.escolher`. Exigi-los na montagem obrigaria a inventar um tipo novo
    só para carregar um `bool` até aqui.
    """
    if fora := declaracao.acoes_fora_do_catalogo():
        raise KeyError(f"item de menu fora do catálogo de comandos: {', '.join(fora)}")
    if faltando := declaracao.comandos_faltando(comandos):
        raise KeyError(f"item de menu sem comando: {', '.join(faltando)}")

    barra = QMenuBar(janela)
    montada = BarraDeMenus(barra)
    for declarado in declaracao.MENUS:
        menu = QMenu(declarado.titulo, barra)
        for item in declarado.itens:
            if item.tipo == declaracao.SEPARADOR:
                menu.addSeparator()
            elif item.tipo == declaracao.RECENTES:
                menu.addMenu(_submenu_recentes(menu, item, recentes))
            elif item.tipo in declaracao.TIPOS_DE_ESCOLHA:
                submenu, grupo = _submenu_de_escolha(
                    menu, item, _valores_de(item.tipo), comandos[item.acao]
                )
                menu.addMenu(submenu)
                montada.grupos[item.acao] = grupo
            else:
                acao = _acao(menu, item, comandos)
                menu.addAction(acao)
                montada.acoes[item.acao] = acao
        barra.addMenu(menu)

    # `setMenuBar` só existe em `QMainWindow`; num `QWidget` a barra é apenas filha e o leiaute
    # a posiciona. Aceitar os dois é o que permite ao teste montar a barra sem uma janela
    # principal inteira -- e à janela real usar o caminho nativo.
    definir = getattr(janela, "setMenuBar", None)
    if callable(definir):
        definir(barra)
    return montada
