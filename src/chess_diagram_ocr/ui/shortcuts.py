"""Atalhos de teclado do ciclo corrigir → salvar → próximo (S-20/S-31).

**A guarda é o item, não o `bind`.** Os atalhos ficam ligados na janela inteira
(`bind_all`), porque o usuário pode estar com o foco em qualquer widget quando aperta
`←`. Mas `←` dentro do campo de FEN pertence ao campo -- move o cursor --, e `Del` dentro
dele apaga um caractere. Sem a guarda, digitar uma FEN à mão trocaria de diagrama a cada
seta e apagaria a peça selecionada a cada `Delete`.

**Ceder é por tecla, e não pelo widget inteiro.** A guarda cedia **qualquer** sequência a um
campo de texto, e o preço estava medido: de tudo o que `ATALHOS` liga, um `Entry` usa três
teclas -- `←`, `→` e `Del`, as mesmas três que o parágrafo acima justifica. Todas as demais,
`Ctrl+S` à frente, ficavam inertes lá dentro sem aviso nenhum: digitar uma FEN e apertar
`Ctrl+S` não salvava. O inventário de quem engole o quê está em `tests/test_shortcuts.py`, para
o número não voltar a ser uma lembrança. O achado está escrito em
`docs/SPEC_APARENCIA.md`, na S-223, que o encontrou ao dar `Ctrl+Enter` ao `aplicar_fen` e não
o consertou porque mexer aqui muda o comportamento de todas elas.

**Quem diz o que o campo usa é o Tk, por escrito.** `bind Entry <Control-Key>` é `# nothing`
nas cinco classes: o Tk declarando que `Control`+<o que ele não nomeou> não é do campo. E
`bind Entry <Prior>` é `# nothing` também, enquanto `bind Text <Prior>` é
`tk::TextScrollPages` -- que é por que a lista é **por classe** e não uma só.

Que a regra viva num módulo próprio é o que a torna verificável: `keys_of_widget` responde
quais teclas são de uma classe de widget, sem abrir janela nenhuma.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from tkinter import ttk

TEXT_ENTRY_WIDGETS: tuple[type, ...] = (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, ttk.Spinbox)
"""As classes em que **alguma** tecla é do widget, e não do app.

Quais teclas é o que `WIDGET_KEYS` diz, e a resposta muda de uma para a outra."""


CURSOR: frozenset[str] = frozenset({"<Left>", "<Right>", "<Home>", "<End>", "<Control-Left>", "<Control-Right>"})
"""Onde está o cursor. `←` e `→` são duas das três que a S-20 mediu."""

SELECAO: frozenset[str] = frozenset(
    {
        "<Shift-Left>",
        "<Shift-Right>",
        "<Shift-Home>",
        "<Shift-End>",
        "<Control-Shift-Left>",
        "<Control-Shift-Right>",
        "<Control-a>",
        "<Control-Lock-A>",
        "<Control-slash>",
        "<Control-backslash>",
    }
)
r"""O que está selecionado. `Ctrl+A` e `Ctrl+/` são `<<SelectAll>>`; `Ctrl+\` é `<<SelectNone>>`."""

EDICAO: frozenset[str] = frozenset({"<Delete>", "<BackSpace>", "<Control-d>", "<Control-h>", "<Control-k>"})
"""O que apaga caractere. `Del` é a terceira tecla da S-20; as de `Control` são a herança emacs
que o Tk mantém em todos os campos -- `Ctrl+K` apaga da posição até o fim."""

TRANSFERENCIA: frozenset[str] = frozenset(
    {
        "<Control-c>",
        "<Control-v>",
        "<Control-x>",
        "<Control-Lock-C>",
        "<Control-Lock-V>",
        "<Control-Lock-X>",
        "<Control-Insert>",
        "<Shift-Insert>",
        "<Shift-Delete>",
    }
)
"""Copiar, colar e recortar -- nas duas grafias que o Tk liga para cada um, e com as variantes
de Caps Lock que ele acrescenta sozinho."""

FIELD_KEYS: frozenset[str] = CURSOR | SELECAO | EDICAO | TRANSFERENCIA
"""As teclas que **todo** campo de texto usa, medidas nas cinco classes de `TEXT_ENTRY_WIDGETS`."""

TEXT_BOX_KEYS: frozenset[str] = frozenset(
    {
        # a caixa tem linhas: o cursor sobe, desce, e `Enter` insere uma
        "<Up>",
        "<Down>",
        "<Shift-Up>",
        "<Shift-Down>",
        "<Control-Up>",
        "<Control-Down>",
        "<Control-Shift-Up>",
        "<Control-Shift-Down>",
        "<Return>",
        "<Insert>",
        # e tem páginas: `PgUp` rola o texto, o que num campo de uma linha não existe
        "<Prior>",
        "<Next>",
        "<Shift-Prior>",
        "<Shift-Next>",
        "<Control-Prior>",
        "<Control-Next>",
        "<Control-Home>",
        "<Control-End>",
        "<Control-Shift-Home>",
        "<Control-Shift-End>",
        # desfazer é do `tk.Text` e de mais nenhum dos cinco
        "<Control-z>",
        "<Control-y>",
        "<Control-Lock-Z>",
        "<Control-Lock-Y>",
        # e a tabulação, que o Tk escreve de cinco formas -- `Ctrl+I` entre elas
        "<Tab>",
        "<Shift-Tab>",
        "<Control-Tab>",
        "<Control-Shift-Tab>",
        "<Control-i>",
    }
)
r"""O que **só** o `tk.Text` usa, além de `FIELD_KEYS`.

`PgUp`/`PgDn` são o exemplo de por que a lista é por classe e não uma só: no `tk.Text` elas
rolam o texto (`tk::TextScrollPages`), e num `Entry` o Tk as liga a `# nothing` -- de propósito,
para o `<Key>` genérico não inserir caractere. Cedê-las num `Entry` seria tirar do programa a
virada de página em troca de tecla nenhuma.

`<Control-i>` é `tk::TextInsert %W \t`: dentro de uma caixa de texto, a tecla universal de
itálico já é a de tabulação. Está declarada aqui porque é verdade -- e é o que faz um futuro
atalho de itálico falhar no teste em vez de falhar na mão de quem escreve."""

SPINBOX_KEYS: frozenset[str] = frozenset({"<Up>", "<Down>"})
"""`<<Increment>>` e `<<Decrement>>` do seletor "Selecionado".

É por causa **destas** que o `ttk.Spinbox` entrou na lista da S-20, e não por `←`/`→`: ali as
setas horizontais movem o cursor do texto, como em qualquer campo."""

COMBOBOX_KEYS: frozenset[str] = frozenset({"<Down>", "<Escape>"})
"""`↓` abre a lista (`ttk::combobox::Post`) e `Esc` a fecha."""


WIDGET_KEYS: tuple[tuple[type, frozenset[str]], ...] = (
    (tk.Text, FIELD_KEYS | TEXT_BOX_KEYS),
    (ttk.Combobox, FIELD_KEYS | COMBOBOX_KEYS),
    (ttk.Spinbox, FIELD_KEYS | SPINBOX_KEYS),
    (tk.Entry, FIELD_KEYS),
)
"""Classe de widget → as teclas que são dela. **A ordem é parte da regra**: vale a primeira que
casa.

`ttk.Combobox` e `ttk.Spinbox` herdam de `ttk.Entry`, que herda de `tk.Entry`. Pôr `tk.Entry`
em qualquer lugar que não o fim daria a resposta do pai aos três filhos, e `↑` deixaria de
incrementar o seletor."""


def keys_of_widget(widget: object) -> frozenset[str]:
    """As teclas que pertencem àquele widget -- vazio para quem não é campo de texto."""
    for classe, teclas in WIDGET_KEYS:
        if isinstance(widget, classe):
            return teclas
    return frozenset()


def ignores_widget(widget: object) -> bool:
    """Se o widget é um campo de texto -- isto é, se **alguma** tecla pertence a ele.

    Continua respondendo sobre a classe e não sobre a tecla. Quem cruza as duas perguntas é
    `uses_key`; esta segue existindo porque "é campo de texto" é a única resposta possível
    quando não se sabe qual tecla foi -- o `guard` sem sequência."""
    return isinstance(widget, TEXT_ENTRY_WIDGETS)


def uses_key(widget: object, sequence: str) -> bool:
    """Se **aquela** tecla, dentro daquele widget, é do widget.

    É esta a pergunta que a guarda faz. `ignores_widget` sozinho respondia sim para `Ctrl+S`
    dentro de um `Entry`, e o Tk diz o contrário: lá `Control`+qualquer coisa é `# nothing`."""
    return sequence in keys_of_widget(widget)


def owns_key(widget: object, sequence: str) -> bool:
    """Se aquele widget já declarou um `bind` próprio para aquela sequência (S-117).

    **O defeito que isto conserta.** `ui/study_panel.py` liga `<Left>`/`<Right>` no canvas do
    tabuleiro de estudo a `undo_move`/`redo_move`, e esses handlers devolvem `None`. O
    `bind_all` daqui liga as mesmas teclas ao editor. Sem esta pergunta, os **dois** disparam:
    analisar uma posição com as setas na aba Análise movia, invisivelmente, o cursor do editor
    em outra aba -- e o que o `Ctrl+S` seguinte gravava deixava de ser o diagrama que a pessoa
    achava que estava selecionado.

    A alternativa mais barata era `undo_move`/`redo_move` devolverem `"break"`. Ela resolve
    este caso e não o próximo: a regra "quem declarou a tecla fica com ela" vale para todo
    atalho que vier depois, e é por isso que ela mora aqui e não lá.

    **É por esta porta que um campo de texto fica com uma tecla que `uses_key` não lhe dá.** O
    campo de FEN liga `Ctrl+Enter` a si mesmo, lendo a sequência de `ui/atalhos.py`: uma
    declaração, duas ligações. `uses_key` diz não -- o Tk não usa `Ctrl+Enter` num `Entry` --,
    e é `owns_key` que responde sim.

    `widget.bind(seq)` sem callback **consulta** em vez de ligar, e devolve string vazia quando
    não há binding. Um widget destruído ou de outra biblioteca levanta, e aí a resposta é não:
    não ceder é o comportamento anterior, que é o certo diante de dúvida.
    """
    consulta = getattr(widget, "bind", None)
    if consulta is None:
        return False
    try:
        return bool(str(consulta(sequence)).strip())
    except Exception:  # noqa: BLE001 - widget destruido, ou que nao implementa `bind`
        return False


def guard(handler: Callable[[], None], sequence: str = "") -> Callable[[tk.Event], str | None]:
    """Envolve o handler com a guarda de foco.

    Devolve `"break"` quando trata a tecla, para o Tk não a repassar adiante, e `None`
    quando cede -- que é o que faz o `Entry` continuar recebendo a seta normalmente.

    Cede em **dois** casos: aquela tecla é do widget em foco (`uses_key`), ou ele já declarou
    binding próprio para ela (`owns_key`, S-117). Nos dois a pergunta é sobre a **sequência**, e
    é isso que faz `Ctrl+S` salvar com o cursor dentro do campo de FEN, o que ele não fazia.

    `sequence=""` desliga as duas perguntas e cai na guarda anterior -- campo de texto leva
    tudo. Sem saber qual tecla foi não há como separar `←` de `Ctrl+S`, e a resposta segura para
    quem está digitando é essa. `bind_shortcuts` sempre passa a sequência; o padrão existe para
    quem chama `guard` sem ela.
    """

    def _wrapped(event: tk.Event) -> str | None:
        alvo = getattr(event, "widget", None)
        if not sequence:
            if ignores_widget(alvo):
                return None
        elif uses_key(alvo, sequence) or owns_key(alvo, sequence):
            return None
        handler()
        return "break"

    return _wrapped


def bind_shortcuts(root: tk.Misc, bindings: Mapping[str, Callable[[], None]]) -> None:
    """Liga os atalhos na janela inteira, cada um sob a guarda de foco."""
    for sequence, handler in bindings.items():
        root.bind_all(sequence, guard(handler, sequence))
