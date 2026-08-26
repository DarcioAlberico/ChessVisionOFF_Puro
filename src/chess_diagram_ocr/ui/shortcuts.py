"""Atalhos de teclado do ciclo corrigir → salvar → próximo (S-20/S-31).

**A guarda é o item, não o `bind`.** Os atalhos ficam ligados na janela inteira
(`bind_all`), porque o usuário pode estar com o foco em qualquer widget quando aperta
`←`. Mas `←` dentro do campo de FEN pertence ao campo -- move o cursor --, e `Del` dentro
dele apaga um caractere. Sem a guarda, digitar uma FEN à mão trocaria de diagrama a cada
seta e apagaria a peça selecionada a cada `Delete`.

**E a guarda cede a tecla, não o teclado** (S-294). Até aquele item ela perguntava só *"é campo de
texto?"* e, se fosse, cedia **os dezoito** atalhos da janela -- inclusive `Ctrl+S`, `Ctrl+N` e
`Ctrl+P`, que campo de texto nenhum usa e que ali simplesmente morriam. `←` é do campo; `Ctrl+S`
não é de campo nenhum.

Que a regra viva num módulo próprio é o que a torna verificável: `cede_a_tecla` responde sim ou não
sobre um par (classe de widget, tecla), sem abrir janela nenhuma.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from tkinter import ttk

from . import atalhos

TEXT_ENTRY_WIDGETS: tuple[type, ...] = (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, ttk.Spinbox)
"""Widgets em que as teclas de navegação são do widget, não do app.

`ttk.Spinbox` está aqui por causa do seletor "Selecionado": as setas dentro dele já
incrementam o número, e deixar o atalho passar mudaria o diagrama duas vezes por tecla."""

MULTILINHA: tuple[type, ...] = (tk.Text,)
"""Os que rolam. `PgUp`/`PgDn` são deles; num campo de uma linha essas teclas não fazem nada."""

ACOES_DO_CAMPO: frozenset[str] = frozenset(
    {
        "diagrama_anterior",   # <-
        "proximo_diagrama",    # ->
        "primeira_pagina",     # Home
        "ultima_pagina",       # End
        "apagar_casa",         # Del
        "desfazer",            # Ctrl+Z
        "refazer",             # Ctrl+Y
    }
)
"""As ações da janela cujas teclas **qualquer** campo de texto de fato usa (S-294).

Navegação, edição e o desfazer do próprio widget: cada uma tem comportamento de fábrica dentro do
campo, e deixar o atalho da janela passar por cima o quebraria -- digitar uma FEN trocaria de
diagrama a cada seta, que é o defeito que a guarda existe para impedir desde a S-20.

**Declaradas por ação, e não por sequência.** A regra deste projeto é que só `ui/atalhos.py`
escreve tecla (`test_ui_legenda.test_so_a_tabela_escreve_sequencia_de_tecla`), e ela é a regra
certa: remapear `desfazer` lá e esquecer aqui deixaria a guarda cedendo uma tecla que não é mais a
do desfazer. Aqui se diz o **significado**; a tecla sai da tabela."""

ACOES_SO_DO_MULTILINHA: frozenset[str] = frozenset({"pagina_anterior", "proxima_pagina"})
"""`PgUp`/`PgDn` são cedidas só a quem rola.

Num `Entry` de uma linha -- o campo de FEN -- elas não fazem coisa nenhuma, e cedê-las ali era
desligar "página anterior/seguinte" em troca de nada."""

TECLAS_DE_EDICAO: frozenset[str] = frozenset({"<Up>", "<Down>", "<BackSpace>"})
"""As teclas de edição que **não são atalho de janela nenhum**, e por isso não têm ação a citar.

Elas nunca chegam à guarda hoje -- nada as liga com `bind_all` --, e estão aqui para o dia em que
alguma delas virar atalho: o campo de texto continua sendo o dono, e a lista já diz isso."""


def _sequencias(acoes: frozenset[str]) -> frozenset[str]:
    """As sequências daquelas ações, pela tabela. Ação sem tecla é ignorada, e não levanta.

    Ignorar em vez de levantar porque isto roda na **importação** do módulo: uma ação que perdesse
    a tecla derrubaria a janela inteira por causa de uma linha desta lista, e o que ela merece é
    deixar de ser cedida."""
    return frozenset(
        atalho.sequencia for acao in acoes if (atalho := atalhos.por_acao.get(acao)) is not None
    )


CEDIDAS_A_TODO_CAMPO: frozenset[str] = _sequencias(ACOES_DO_CAMPO) | TECLAS_DE_EDICAO
CEDIDAS_SO_AO_MULTILINHA: frozenset[str] = _sequencias(ACOES_SO_DO_MULTILINHA)


def ignores_widget(widget: object) -> bool:
    """Este widget é um campo de texto? Ver `cede_a_tecla`, que é quem decide o que ceder.

    **Sozinha ela não decide mais nada**, e o motivo é a S-294: ceder *todas* as teclas a um campo
    de texto desligava nove atalhos que campo de texto nenhum usa.
    """
    return isinstance(widget, TEXT_ENTRY_WIDGETS)


def cede_a_tecla(widget: object, sequence: str) -> bool:
    """A guarda deve ceder **esta tecla** a este widget? (S-294)

    ## O defeito que isto conserta, e ele estava registrado

    Até aqui a guarda perguntava só *"é campo de texto?"* e, se fosse, cedia **os dezoito** atalhos
    da janela. O docstring dela justificava três -- `←`, `→` e `Del` --, e a `SPEC_APARENCIA` da
    S-223 anotou o resto por escrito: *"a mesma guarda cede os onze atalhos dentro de qualquer
    `Entry`, inclusive `Ctrl+S`, `Ctrl+R` e `Ctrl+N`, que campo de texto nenhum usa. Digitar uma FEN
    e apertar `Ctrl+S` não salva hoje, e ninguém registrou isso."*

    O sintoma é exatamente esse: com o cursor no campo de FEN, `Ctrl+S` não salvava, `Ctrl+N` não
    ia para o próximo da fila, `Ctrl+P` não abria a paleta e `PgDn` não virava a página. Nenhuma
    delas faz coisa alguma dentro de um `Entry` -- então a tecla simplesmente morria.

    ## A pergunta certa é sobre a tecla, e não sobre o widget

    `←` dentro de um campo pertence ao campo; `Ctrl+S` não pertence a campo nenhum. A régua passou
    a ser a lista do que o widget **de fato usa** (`CEDIDAS_A_TODO_CAMPO`), mais as duas de rolagem
    que só quem rola usa (`CEDIDAS_SO_AO_MULTILINHA`).

    ## O que **não** muda, e é o que mantém a S-117 e a S-267 de pé

    Uma tecla que o widget declarou para si continua sendo dele -- quem responde por isso é
    `owns_key`, e ela roda depois desta. É por ali que `Ctrl+R` continua "alinhar à direita" dentro
    do editor, e `Ctrl+Enter` continua sendo do campo de FEN: as duas são declaradas no widget, e
    nenhuma depende mais do cobertor.

    `sequence=""` cede, como antes. Quem chama `guard` sem dizer que tecla ligou não dá a esta
    função como responder, e o lado seguro é o comportamento anterior.
    """
    if not ignores_widget(widget):
        return False
    if not sequence:
        return True
    if sequence in CEDIDAS_A_TODO_CAMPO:
        return True
    return sequence in CEDIDAS_SO_AO_MULTILINHA and isinstance(widget, MULTILINHA)


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

    Cede em **dois** casos: a tecla é do campo de texto em foco (`cede_a_tecla`, S-294), ou o
    widget já declarou binding próprio para aquela sequência (`owns_key`, S-117). `sequence=""`
    desliga a segunda pergunta e faz a primeira ceder tudo, que é o comportamento anterior --
    existe para quem chama `guard` sem saber qual tecla ligou.
    """

    def _wrapped(event: tk.Event) -> str | None:
        alvo = getattr(event, "widget", None)
        # **Antes de ceder, pergunta se o painel em foco declarou esta ação para si** (S-244).
        # A guarda abaixo é de 2026-08 e vale: `←` dentro de um campo pertence ao campo. Mas ela
        # cedia *tudo*, e o efeito era que `Ctrl+S` com o cursor no editor de texto não salvava
        # nada -- nem a posição (a guarda cedeu) nem o texto (ninguém ligou). Quem declara é o
        # painel, em `acoes_proprias`; quem confere que a declaração é cumprida é
        # `atalhos.conferir_dono`, na montagem.
        acao = atalhos.acao_de(sequence) if sequence else ""
        if acao:
            proprio = atalhos.destino(acao, alvo, {})
            if proprio is not None:
                proprio()
                return "break"
        if cede_a_tecla(alvo, sequence):
            return None
        if sequence and owns_key(alvo, sequence):
            return None
        handler()
        return "break"

    return _wrapped


def bind_shortcuts(root: tk.Misc, bindings: Mapping[str, Callable[[], None]]) -> None:
    """Liga os atalhos na janela inteira, cada um sob a guarda de foco."""
    for sequence, handler in bindings.items():
        root.bind_all(sequence, guard(handler, sequence))
