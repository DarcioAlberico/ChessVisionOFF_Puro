"""Os atalhos de teclado, **declarados uma vez** (S-161/S-165).

**O defeito que isto fecha.** Os atalhos existiam como um dicionário literal dentro de
`app_tkinter._bind_shortcuts`: sequência do Tk → função. Nada mais no programa sabia deles.
Consequência, medida com a janela aberta: **nenhum dos dez aparece na interface** — não há menu,
não há legenda, e o tooltip de um botão não diz que existe tecla para aquilo. Depois da S-150 isso
deixou de ser conveniência: num notebook de 1366×768 o `Ctrl+S` era o único caminho para salvar, e
ele não estava escrito em lugar nenhum.

**Uma tabela, três clientes.** `bind_shortcuts` liga, o menu mostra o acelerador e a legenda da
S-165 lista. Se fossem duas listas elas divergiriam -- é exatamente o que aconteceu com os rótulos
de procedência antes da S-04, e o que a S-134 documenta sobre índices que ninguém verifica.

**Eram dez, e não onze.** A avaliação escreveu "onze atalhos" e listou dez (`←`, `→`, `Ctrl+S`,
`Ctrl+Shift+S`, `Ctrl+R`, `Del`, `Ctrl+N`, `PgUp`, `PgDn`, `Ctrl+0`); `_bind_shortcuts` ligava dez.
Ficou corrigido aqui e o teste conta, porque um número que ninguém consegue reproduzir é o
mecanismo da S-135.

**São onze desde a S-223**, e o décimo primeiro é `Ctrl+Enter`. Ele não entrou por simetria: a
fila de ações da pele "Foco" só admite comando que tenha tecla, e `aplicar_fen` é o gesto que
**fecha** o ciclo corrigir → salvar sem ter uma. Quem digita uma FEN à mão estava obrigado a largar
o teclado para aplicá-la, com as mãos já dentro do campo -- que é a mesma situação de notebook que
a S-150 mediu para o `Ctrl+S`.

**A ação é um nome, e não uma função.** Cada linha aponta para um identificador (`"salvar"`), e
quem tem os widgets é que diz o que aquele nome faz. É o que permite a este módulo -- e ao
`ui/menu.py`, que consome os mesmos nomes -- não importar `tkinter` nem conhecer painel nenhum.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

__all__ = ["ATALHOS", "Atalho", "acelerador", "ligacoes", "por_acao"]


@dataclass(frozen=True)
class Atalho:
    """Uma tecla, o que ela faz, e como ela se escreve para ser lida."""

    sequencia: str
    """A sequência do Tk, como `bind_all` a quer: `"<Control-s>"`."""

    rotulo: str
    """Como a pessoa lê: `"Ctrl+S"`. Declarado e não derivado -- `<Prior>` vira "Page Up", e
    nenhuma regra de tradução acerta isso sem uma tabela de exceções do tamanho desta."""

    acao: str
    """O nome do comando. Quem tem os widgets amarra o nome à função."""

    descricao: str
    """O que ele faz, em pt-BR, como a legenda e o menu vão dizer."""


ATALHOS: tuple[Atalho, ...] = (
    Atalho("<Left>", "←", "diagrama_anterior", "Diagrama anterior desta página"),
    Atalho("<Right>", "→", "proximo_diagrama", "Próximo diagrama desta página"),
    # Antes de salvar porque é o que vem antes no gesto: aplica-se a FEN digitada e **então**
    # se grava. A guarda de foco de `ui/shortcuts.py` cede a tecla a qualquer campo de texto, e
    # é dentro do campo de FEN que esta faz sentido -- por isso o campo declara a mesma sequência
    # para si (S-117), e a tabela continua sendo a única declaração dela.
    Atalho("<Control-Return>", "Ctrl+Enter", "aplicar_fen", "Aplicar ao tabuleiro a FEN digitada"),
    Atalho("<Control-s>", "Ctrl+S", "salvar", "Salvar a posição do diagrama selecionado"),
    Atalho("<Control-S>", "Ctrl+Shift+S", "salvar_todos", "Salvar todos os diagramas lidos da página"),
    Atalho("<Control-r>", "Ctrl+R", "ler_pagina", "Ler esta página de novo (OCR de todos os diagramas)"),
    Atalho("<Delete>", "Del", "apagar_casa", "Apagar a peça da casa selecionada no tabuleiro"),
    # Depois do apagar porque é o que vem depois no gesto: erra-se a casa e desfaz-se. As duas
    # teclas são as do sistema, e a escolha é de reconhecimento e não de gosto -- `Ctrl+Z` num
    # editor que fizesse outra coisa seria a pior surpresa possível num programa de correção.
    Atalho("<Control-z>", "Ctrl+Z", "desfazer", "Desfazer a última mudança no tabuleiro"),
    Atalho("<Control-y>", "Ctrl+Y", "refazer", "Refazer a mudança que o desfazer tirou"),
    Atalho("<Control-n>", "Ctrl+N", "proximo_da_fila", "Abrir o próximo item pendente da fila de revisão"),
    Atalho("<Prior>", "Page Up", "pagina_anterior", "Página anterior do livro"),
    Atalho("<Next>", "Page Down", "proxima_pagina", "Próxima página do livro"),
    Atalho("<Control-0>", "Ctrl+0", "ajustar_largura", "Ajustar a página à largura do visualizador"),
)
"""Os treze atalhos do ciclo corrigir → salvar → próximo (S-20/S-70/S-223/S-229).

A ordem é a do gesto, e não a alfabética: navegar entre diagramas, aplicar a FEN, salvar, reler,
corrigir casa, desfazer, puxar da fila, virar página, enquadrar. É a mesma ordem em que a legenda
os mostra.

**Os dois últimos são da S-229**, e eles fecham um buraco que a tabela tornava visível: dez das
onze teclas agiam sobre o diagrama, e nenhuma o devolvia ao estado anterior."""


por_acao: dict[str, Atalho] = {atalho.acao: atalho for atalho in ATALHOS}
"""Índice por nome de comando. É por aqui que o menu descobre o acelerador de um item."""


def acelerador(acao: str) -> str:
    """O rótulo da tecla daquele comando, ou `""` quando ele não tem uma.

    Devolve vazio em vez de levantar: a maioria dos itens de menu **não** tem atalho, e essa é a
    resposta certa para eles -- ao contrário de `tokens.cor`, onde não haver cor é um defeito.
    """
    atalho = por_acao.get(acao)
    return atalho.rotulo if atalho is not None else ""


def ligacoes(comandos: Mapping[str, Callable[[], None]]) -> dict[str, Callable[[], None]]:
    """O mapa `sequência → função` que `bind_shortcuts` consome, montado da tabela.

    Levanta `KeyError` nomeando os comandos que faltam. Um atalho declarado e não ligado é uma
    tecla que não faz nada e que a legenda promete -- pior que não tê-lo, porque a pessoa conclui
    que apertou errado.
    """
    faltando = sorted(atalho.acao for atalho in ATALHOS if atalho.acao not in comandos)
    if faltando:
        raise KeyError(f"atalho declarado sem comando: {', '.join(faltando)}")
    return {atalho.sequencia: comandos[atalho.acao] for atalho in ATALHOS}
