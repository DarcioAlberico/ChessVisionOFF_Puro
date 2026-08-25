"""A barra de menus da janela, declarada como dado (S-161).

**O que havia antes: nada.** `grep -rn "tk.Menu" src/ app_tkinter.py` devolvia vazio. Os ~70
comandos da janela eram botões permanentemente visíveis, e isso produz três consequências juntas:
as barras ocupavam 20% da altura (S-151), a ação rara competia com a frequente pelo mesmo olhar, e
**o que não era botão não existia** — não havia "Abrir recente", nem "Abrir o log", nem a lista dos
dez atalhos, que depois da S-150 deixou de ser conveniência (num notebook, `Ctrl+S` era o único
caminho para salvar).

**Declarado como dado, e é isso que o torna verificável.** `MENUS` é uma tupla de tuplas: nenhum
`tkinter` até `montar`. Um teste percorre a declaração e afirma que todo comando com atalho mostra
o acelerador, sem abrir janela -- e `montar` recusa uma declaração cujo comando ninguém amarrou, em
vez de desenhar um item de menu que não faz nada.

**O que o menu não é.** Ele não substitui botão: dá casa ao comando raro e ao que não cabia em
barra nenhuma. O botão de salvar continua na tela porque salvar é o gesto do minuto a minuto; o
"Abrir o log" nunca teve botão e nem devia ter.

**O rótulo saiu daqui na S-219, e a fronteira é essa.** Este módulo decide *onde na barra de
menus*; `ui/comandos.py` decide *o que o comando é* -- como ele se chama, a que grupo pertence,
com que ênfase se desenha. `MENUS` referencia o catálogo em vez de repetir o texto, e `montar`
ganhou a trava no sentido que faltava: item cujo `acao` ninguém registrou levanta, como já
levantava o item que ninguém amarrou a uma função.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from . import atalhos, pele

# Apelidado: neste módulo `comandos` já é o nome do mapa `acao -> função` que `montar` recebe, e
# duas coisas com o mesmo nome no mesmo arquivo é como se lê o errado. `strings` saiu junto: o
# único uso dele aqui era o rótulo de "Varrer o livro", que agora mora no catálogo.
from . import comandos as catalogo

logger = logging.getLogger(__name__)

__all__ = [
    "APARENCIA",
    "MENUS",
    "Item",
    "Menu",
    "acoes_declaradas",
    "acoes_fora_do_catalogo",
    "comandos_faltando",
    "montar",
]

COMANDO = "COMANDO"
INTERRUPTOR = "INTERRUPTOR"
"""Item com marca de ligado/desligado -- os dois de visualização que o `AppState` já guarda."""

SEPARADOR = "SEPARADOR"
RECENTES = "RECENTES"
"""Submenu montado na hora, com os livros que o `AppState` lembra (S-156)."""

APARENCIA = "APARENCIA"
"""Submenu de `radiobutton`, um por pele registrada em `ui/pele.py` (S-221).

**Montado do registro, e não listado à mão** -- é o mesmo princípio de `RECENTES`, com uma
diferença: o acervo muda enquanto o programa roda e por isso o submenu de livros se refaz a cada
abertura; o registro de peles é fixo na importação. O que varia aqui é a **marca**, e disso quem
cuida é o `StringVar`."""


@dataclass(frozen=True)
class Item:
    """Uma linha de menu: **qual** comando e de que tipo. O que ele *é* mora em `ui/comandos.py`.

    O rótulo saiu daqui na S-219. Ele continua legível como `item.rotulo` -- agora derivado do
    catálogo, e não guardado -- porque o menu escrevia o texto que `ui/pdf_panel.py` escrevia de
    novo, com outra redação, e nada comparava os dois.
    """

    acao: str = ""
    tipo: str = COMANDO

    @property
    def rotulo(self) -> str:
        """O texto da linha, tirado do catálogo. Vazio no separador, que não tem comando."""
        return catalogo.rotulo(self.acao) if self.acao else ""


@dataclass(frozen=True)
class Menu:
    titulo: str
    itens: tuple[Item, ...] = field(default_factory=tuple)


def _sep() -> Item:
    return Item(tipo=SEPARADOR)


MENUS: tuple[Menu, ...] = (
    Menu(
        "Arquivo",
        (
            Item("abrir_pdf"),
            Item("abrir_recente", RECENTES),
            Item("abrir_no_leitor"),
            _sep(),
            Item("exportar_pgn"),
            Item("cancelar_exportacao"),
            _sep(),
            Item("sair"),
        ),
    ),
    Menu(
        "Editar",
        (
            # Os três da S-229 abrem o menu, que é onde todo editor os põe -- e é onde quem
            # procura por eles olha primeiro, antes de saber que existe `Ctrl+Z` aqui.
            Item("desfazer"),
            Item("refazer"),
            _sep(),
            Item("aplicar_fen"),
            Item("apagar_casa"),
            Item("limpar_tabuleiro"),
            _sep(),
            Item("salvar"),
            Item("salvar_todos"),
            _sep(),
            Item("diagrama_anterior"),
            Item("proximo_diagrama"),
            Item("proximo_da_fila"),
        ),
    ),
    Menu(
        "Ver",
        (
            Item("pagina_anterior"),
            Item("proxima_pagina"),
            _sep(),
            Item("zoom_menos"),
            Item("zoom_mais"),
            Item("ajustar_largura"),
            Item("ajustar_pagina"),
            _sep(),
            Item("marcar_diagramas", INTERRUPTOR),
            # Ao lado do interruptor que liga a marcação, e não em Ferramentas: os dois falam
            # do mesmo objeto -- os retângulos sobre a página --, e a diferença entre eles é
            # "todos" contra "este" (S-177).
            Item("tirar_caixa"),
            Item("devolver_caixas"),
            _sep(),
            Item("roda_vira_pagina", INTERRUPTOR),
            _sep(),
            Item("aparencia", APARENCIA),
        ),
    ),
    Menu(
        "Ferramentas",
        (
            Item("ler_pagina"),
            Item("ler_melhor"),
            Item("selecionar_area"),
            _sep(),
            # Um comando, e não dois: a varredura do livro alimenta a Galeria **e** a fila de
            # revisão na mesma passada (S-119). Enquanto eram duas passadas, "Varrer a fila de
            # revisão" era um segundo item aqui, com o mesmo custo do primeiro.
            Item("varrer_livro"),
            _sep(),
            Item("recarregar_modelo"),
            Item("treinar"),
        ),
    ),
    Menu(
        "Ajuda",
        (
            Item("legenda_de_atalhos"),
            Item("abrir_log"),
            _sep(),
            Item("sobre"),
        ),
    ),
)
"""A barra inteira, como dado.

**Cinco menus, e o critério de cada um é uma pergunta.** Arquivo: que documento. Editar: o que
muda no diagrama aberto. Ver: como a página aparece. Ferramentas: o que roda sobre o livro. Ajuda:
o que o programa sabe sobre si.

O que **não** entrou: os campos de configuração (são estado, não comando), as anotações do conjunto
de campo (pertencem à página exibida e a S-77 as põe junto dela de propósito) e os botões de
navegação da Galeria (são de dentro de uma aba). Um menu que listasse os 70 controles não seria um
mapa da janela -- seria a mesma pilha de botões noutra vertical."""


def acoes_declaradas() -> list[str]:
    """Todo nome de comando que a barra usa, em ordem de declaração."""
    return [item.acao for menu in MENUS for item in menu.itens if item.tipo != SEPARADOR]


def comandos_faltando(comandos: Mapping[str, object]) -> list[str]:
    """Os comandos declarados que ninguém amarrou. Vazio é o estado correto.

    O submenu de recentes fica de fora: ele não tem função própria -- quem o preenche é o
    `recentes` de `montar`, e cada livro vira uma função na hora de abrir o menu.
    """
    exigidos = {item.acao for menu in MENUS for item in menu.itens if item.tipo in (COMANDO, INTERRUPTOR, APARENCIA)}
    return sorted(exigidos - set(comandos))


def acoes_fora_do_catalogo() -> list[str]:
    """Os itens declarados que `ui/comandos.py` não conhece. Vazio é o estado correto.

    O sentido que faltava. `comandos_faltando` pega o item que ninguém amarrou a uma função;
    este pega o item que ninguém declarou como comando -- o que, depois da S-219, é o que faria
    uma pele desenhar uma linha sem rótulo, ou nenhuma linha.
    """
    return catalogo.acoes_fora_do_catalogo(acoes_declaradas())


def montar(
    root: tk.Misc,
    comandos: Mapping[str, Callable[[], None]],
    *,
    interruptores: Mapping[str, tk.BooleanVar] | None = None,
    recentes: Callable[[], Sequence[tuple[str, Callable[[], None]]]] = list,
    escolhas: Mapping[str, tk.StringVar] | None = None,
) -> tk.Menu:
    """Constrói a barra e a pendura na janela. Devolve a barra montada.

    Levanta `KeyError` quando um item declarado não tem comando: um menu que desenha uma linha
    inerte é pior que um menu sem ela -- a pessoa conclui que a função existe e está quebrada.
    É a mesma disciplina de `tokens.cor` e de `estilos.estilo_de_botao`.

    `recentes` é chamado **na hora de abrir** o menu Arquivo, e não aqui: a lista de livros muda a
    cada PDF aberto, e um submenu montado uma vez mostraria o acervo de quando a janela subiu.

    `escolhas` traz o `StringVar` de cada item de `APARENCIA`, e a falta dele **levanta** pela
    mesma razão que a falta de comando: um submenu de `radiobutton` sem variável desenha três
    opções em que nenhuma aparece marcada, e a pessoa conclui que a escolha não pegou.
    """
    if fora := acoes_fora_do_catalogo():
        raise KeyError(f"item de menu fora do catálogo de comandos: {', '.join(fora)}")
    if faltando := comandos_faltando(comandos):
        raise KeyError(f"item de menu sem comando: {', '.join(faltando)}")
    variaveis = escolhas or {}
    if sem_variavel := sorted(
        item.acao
        for declarado in MENUS
        for item in declarado.itens
        if item.tipo == APARENCIA and item.acao not in variaveis
    ):
        raise KeyError(f"item de aparência sem variável de escolha: {', '.join(sem_variavel)}")

    marcas = interruptores or {}
    barra = tk.Menu(root)
    for declarado in MENUS:
        menu = tk.Menu(barra, tearoff=False)
        for item in declarado.itens:
            _acrescentar(menu, item, comandos, marcas, recentes, variaveis)
        barra.add_cascade(label=declarado.titulo, menu=menu)
    root.configure(menu=barra)  # type: ignore[call-arg]
    return barra


def _acrescentar(
    menu: tk.Menu,
    item: Item,
    comandos: Mapping[str, Callable[[], None]],
    marcas: Mapping[str, tk.BooleanVar],
    recentes: Callable[[], Sequence[tuple[str, Callable[[], None]]]],
    variaveis: Mapping[str, tk.StringVar],
) -> None:
    if item.tipo == SEPARADOR:
        menu.add_separator()
        return
    if item.tipo == RECENTES:
        menu.add_cascade(label=item.rotulo, menu=_submenu_recentes(menu, recentes))
        return
    if item.tipo == APARENCIA:
        submenu = _submenu_de_peles(menu, variaveis[item.acao], comandos[item.acao])
        menu.add_cascade(label=item.rotulo, menu=submenu)
        return
    if item.tipo == INTERRUPTOR and item.acao in marcas:
        menu.add_checkbutton(label=item.rotulo, variable=marcas[item.acao], command=comandos[item.acao])
        return
    # `accelerator` só **mostra** a tecla; quem a liga é `bind_shortcuts`, e é de propósito: o
    # `bind` da S-20 tem a guarda de foco (`←` dentro do campo de FEN é do campo), e o
    # acelerador do Tk não tem guarda nenhuma. Duas ligações da mesma tecla disparariam duas vezes.
    menu.add_command(label=item.rotulo, command=comandos[item.acao], accelerator=atalhos.acelerador(item.acao))


def _submenu_de_peles(pai: tk.Menu, escolha: tk.StringVar, ao_escolher: Callable[[], None]) -> tk.Menu:
    """Um `radiobutton` por pele registrada, na ordem de `pele.PELES` (S-221).

    O `value` é o nome que vai para o disco e o `label` é o que a pessoa lê -- separados porque
    o primeiro é chave e o segundo é texto de interface, e a S-166 já fixou que os dois não são
    a mesma coisa.
    """
    submenu = tk.Menu(pai, tearoff=False)
    for registro in pele.PELES:
        submenu.add_radiobutton(label=registro.rotulo, value=registro.nome, variable=escolha, command=ao_escolher)
    return submenu


def _submenu_recentes(pai: tk.Menu, recentes: Callable[[], Sequence[tuple[str, Callable[[], None]]]]) -> tk.Menu:
    submenu = tk.Menu(pai, tearoff=False, postcommand=lambda: _preencher_recentes(submenu, recentes))
    return submenu


def _preencher_recentes(
    submenu: tk.Menu, recentes: Callable[[], Sequence[tuple[str, Callable[[], None]]]]
) -> None:
    """Refaz o submenu a cada abertura. Sem livro nenhum, uma linha desabilitada que diz isso."""
    submenu.delete(0, tk.END)
    try:
        itens = list(recentes())
    except Exception:  # pragma: no cover - ler o estado não pode derrubar o menu
        logger.exception("Não foi possível montar a lista de livros recentes.")
        itens = []
    if not itens:
        submenu.add_command(label="(nenhum livro aberto ainda)", state=tk.DISABLED)
        return
    for rotulo, abrir in itens:
        submenu.add_command(label=rotulo, command=abrir)
