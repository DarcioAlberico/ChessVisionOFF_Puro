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
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from . import atalhos, strings

logger = logging.getLogger(__name__)

__all__ = ["MENUS", "Item", "Menu", "acoes_declaradas", "comandos_faltando", "montar"]

COMANDO = "COMANDO"
INTERRUPTOR = "INTERRUPTOR"
"""Item com marca de ligado/desligado -- os dois de visualização que o `AppState` já guarda."""

SEPARADOR = "SEPARADOR"
RECENTES = "RECENTES"
"""Submenu montado na hora, com os livros que o `AppState` lembra (S-156)."""


@dataclass(frozen=True)
class Item:
    """Uma linha de menu. `acao` é o nome do comando, não a função (ver `ui/atalhos.py`)."""

    rotulo: str = ""
    acao: str = ""
    tipo: str = COMANDO


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
            Item("Abrir PDF…", "abrir_pdf"),
            Item("Abrir recente", "abrir_recente", RECENTES),
            Item("Abrir no leitor do sistema", "abrir_no_leitor"),
            _sep(),
            Item("Exportar o livro para PGN…", "exportar_pgn"),
            _sep(),
            Item("Sair", "sair"),
        ),
    ),
    Menu(
        "Editar",
        (
            Item("Aplicar a FEN digitada", "aplicar_fen"),
            Item("Apagar a peça da casa selecionada", "apagar_casa"),
            _sep(),
            Item("Salvar a posição", "salvar"),
            Item("Salvar todas as posições da página", "salvar_todos"),
            _sep(),
            Item("Diagrama anterior", "diagrama_anterior"),
            Item("Próximo diagrama", "proximo_diagrama"),
            Item("Próximo item da fila de revisão", "proximo_da_fila"),
        ),
    ),
    Menu(
        "Ver",
        (
            Item("Página anterior", "pagina_anterior"),
            Item("Próxima página", "proxima_pagina"),
            _sep(),
            Item("Ajustar à largura", "ajustar_largura"),
            Item("Ajustar à página", "ajustar_pagina"),
            _sep(),
            Item("Marcar os diagramas na página", "marcar_diagramas", INTERRUPTOR),
            Item("A roda do mouse vira a página", "roda_vira_pagina", INTERRUPTOR),
        ),
    ),
    Menu(
        "Ferramentas",
        (
            Item("Ler esta página", "ler_pagina"),
            Item("Ler o melhor diagrama da página", "ler_melhor"),
            Item("Selecionar área para ler", "selecionar_area"),
            _sep(),
            # Um comando, e não dois: a varredura do livro alimenta a Galeria **e** a fila de
            # revisão na mesma passada (S-119). Enquanto eram duas passadas, "Varrer a fila de
            # revisão" era um segundo item aqui, com o mesmo custo do primeiro.
            Item(strings.VARRER_LIVRO, "varrer_livro"),
            _sep(),
            Item("Recarregar o modelo", "recarregar_modelo"),
            Item("Treinar o modelo", "treinar"),
        ),
    ),
    Menu(
        "Ajuda",
        (
            Item("Atalhos de teclado", "legenda_de_atalhos"),
            Item("Abrir o arquivo de log", "abrir_log"),
            _sep(),
            Item("Sobre o ChessVisionOFF", "sobre"),
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
    exigidos = {item.acao for menu in MENUS for item in menu.itens if item.tipo in (COMANDO, INTERRUPTOR)}
    return sorted(exigidos - set(comandos))


def montar(
    root: tk.Misc,
    comandos: Mapping[str, Callable[[], None]],
    *,
    interruptores: Mapping[str, tk.BooleanVar] | None = None,
    recentes: Callable[[], Sequence[tuple[str, Callable[[], None]]]] = list,
) -> tk.Menu:
    """Constrói a barra e a pendura na janela. Devolve a barra montada.

    Levanta `KeyError` quando um item declarado não tem comando: um menu que desenha uma linha
    inerte é pior que um menu sem ela -- a pessoa conclui que a função existe e está quebrada.
    É a mesma disciplina de `tokens.cor` e de `estilos.estilo_de_botao`.

    `recentes` é chamado **na hora de abrir** o menu Arquivo, e não aqui: a lista de livros muda a
    cada PDF aberto, e um submenu montado uma vez mostraria o acervo de quando a janela subiu.
    """
    if faltando := comandos_faltando(comandos):
        raise KeyError(f"item de menu sem comando: {', '.join(faltando)}")

    marcas = interruptores or {}
    barra = tk.Menu(root)
    for declarado in MENUS:
        menu = tk.Menu(barra, tearoff=False)
        for item in declarado.itens:
            _acrescentar(menu, item, comandos, marcas, recentes)
        barra.add_cascade(label=declarado.titulo, menu=menu)
    root.configure(menu=barra)  # type: ignore[call-arg]
    return barra


def _acrescentar(
    menu: tk.Menu,
    item: Item,
    comandos: Mapping[str, Callable[[], None]],
    marcas: Mapping[str, tk.BooleanVar],
    recentes: Callable[[], Sequence[tuple[str, Callable[[], None]]]],
) -> None:
    if item.tipo == SEPARADOR:
        menu.add_separator()
        return
    if item.tipo == RECENTES:
        menu.add_cascade(label=item.rotulo, menu=_submenu_recentes(menu, recentes))
        return
    if item.tipo == INTERRUPTOR and item.acao in marcas:
        menu.add_checkbutton(label=item.rotulo, variable=marcas[item.acao], command=comandos[item.acao])
        return
    # `accelerator` só **mostra** a tecla; quem a liga é `bind_shortcuts`, e é de propósito: o
    # `bind` da S-20 tem a guarda de foco (`←` dentro do campo de FEN é do campo), e o
    # acelerador do Tk não tem guarda nenhuma. Duas ligações da mesma tecla disparariam duas vezes.
    menu.add_command(label=item.rotulo, command=comandos[item.acao], accelerator=atalhos.acelerador(item.acao))


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
