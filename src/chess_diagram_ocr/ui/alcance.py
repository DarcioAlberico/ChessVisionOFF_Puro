"""O inventário de alcance: nenhuma pele esconde um comando (S-233).

**É o risco central da SPEC_APARENCIA, e ele não é técnico:** três peles convidam a resolver
rápido só numa delas. Um comando novo entra na fita porque foi lá que quem o escreveu estava
trabalhando, some da "Foco" e da clássica, e ninguém descobre até alguém que usa a pele errada
precisar dele. A regra 2 -- *pele é apresentação, nunca conjunto menor* -- não vale nada sem uma
máquina que a cobre, e esta é a máquina.

## "Alcançável" tem três formas, e só duas contam

1. **um controle na tela daquela pele** -- as barras do PDF na clássica, a fila na "Foco", a fita
   na "Fita", e a linha de conjunto de campo, que é de todas;
2. **um item de `menu.MENUS`**, que é a mesma declaração para as três peles;
3. uma entrada da **paleta de comandos** (S-231) -- que, por construção, cobre o catálogo inteiro.

**A terceira não conta, e é a decisão que faz este módulo medir alguma coisa.** A paleta percorre
`comandos.CATALOGO`: incluí-la faria `alcancaveis(pele) == catálogo` ser verdade por definição, e
o teste passaria para sempre sem olhar para nada. A paleta é atalho para quem sabe o nome; o mapa
de quem procura é o menu.

## Reflexão sobre a declaração, e não varredura de widget

Nada aqui abre janela. Cada forma tem um dono que já declara o que desenha -- `fila.acoes_da_fila`,
`fita.acoes_da_fita`, `menu.acoes_declaradas`, `comandos.NAS_BARRAS_DO_PDF` e
`comandos.NA_LINHA_DE_CAMPO` --, e é isso que torna o inventário barato o bastante para rodar em
toda execução da suíte em vez de virar uma conferência manual que ninguém faz.

**O preço disso é uma declaração que pode mentir**, e ela tem guarda própria: as barras do PDF são
montadas à mão em `pdf_panel._montar_barras`, e `test_ui_alcance` varre aquela função por `ast`
para afirmar que a lista declarada é exatamente a que o código desenha.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from . import comandos, fila, fita, menu, pele

__all__ = [
    "alcancaveis",
    "na_tela",
    "no_menu",
    "perdidos",
    "relato",
]


def no_menu() -> set[str]:
    """A forma 2: os comandos que a barra de menus alcança.

    **É a mesma para as três peles**, e é isso que faz a barra de menus ser a rede de segurança da
    regra 2: `menu.MENUS` é uma declaração só, e nenhuma montagem de cromo a filtra.
    """
    return set(menu.acoes_declaradas())


def na_tela(cromo: str) -> set[str]:
    """A forma 1: os comandos que aquela montagem de cromo põe na tela.

    Levanta `KeyError` para montagem que não existe, como `tokens.cor`: um nome escrito errado que
    caísse na clássica devolveria um inventário plausível para a pele errada -- e um inventário
    que erra a pele é pior que nenhum, porque ele passa em verde.

    **A linha de conjunto de campo entra em todas**, e não é exceção arbitrária: `remontar_cromo`
    a refaz em toda troca, e a S-77 a pôs junto da página exibida de propósito. São os três
    comandos que o menu **não** tem, e por isso a única forma 1 que hoje decide alguma coisa.
    """
    if cromo == pele.CROMO_CLASSICO:
        controles: Iterable[str] = comandos.NAS_BARRAS_DO_PDF
    elif cromo == pele.CROMO_FOCO:
        # As duas barras do PDF existem e **não são empacotadas** nesta pele (S-223): o painel
        # mantém um contrato só, e o que a pele decide é o que aparece. Quem aparece é a fila.
        controles = fila.acoes_da_fila()
    elif cromo == pele.CROMO_FITA:
        controles = fita.acoes_da_fita()
    else:
        raise KeyError(f"montagem de cromo desconhecida: {cromo!r}. As válidas estão em ui/pele.py.")
    return set(controles) | set(comandos.NA_LINHA_DE_CAMPO)


def alcancaveis(
    nome_da_pele: str,
    *,
    tela: Callable[[str], set[str]] = na_tela,
    barra_de_menus: Callable[[], set[str]] = no_menu,
) -> set[str]:
    """Os comandos que aquela pele alcança pelas formas 1 e 2. **Nunca pela paleta.**

    Os dois parâmetros existem para o teste poder simular a perda -- "e se a fita deixasse cair um
    comando que só ela desenha?" -- sem editar o programa para descobrir se a guarda funciona. É a
    mesma razão de `tipografia.escala` receber o `base` em vez de ler o Tk.
    """
    return tela(pele.registrada(nome_da_pele).montar_cromo) | barra_de_menus()


def perdidos(
    *,
    catalogo: Iterable[str] | None = None,
    tela: Callable[[str], set[str]] = na_tela,
    barra_de_menus: Callable[[], set[str]] = no_menu,
) -> dict[str, list[str]]:
    """`pele → comandos que ela não alcança`, só para as peles que perderam algum.

    Dicionário vazio é o estado correto, e é o que a suíte cobra. Devolver o **que** faltou, e não
    um booleano, é metade do valor: "a fita esconde um comando" manda alguém procurar entre
    quarenta e um; "a fita esconde `tirar_caixa`" manda alguém consertar.
    """
    todos = set(catalogo) if catalogo is not None else {registro.acao for registro in comandos.CATALOGO}
    faltas = {
        registro.nome: sorted(todos - alcancaveis(registro.nome, tela=tela, barra_de_menus=barra_de_menus))
        for registro in pele.PELES
    }
    return {nome: faltando for nome, faltando in faltas.items() if faltando}


def relato(faltas: dict[str, list[str]]) -> str:
    """A mensagem de falha, que **nomeia** a pele e os comandos. Vazia quando não há falta.

    O critério de aceite do item pede isto por escrito, e a razão está na forma do defeito que ele
    persegue: quem esconde um comando sem querer está trabalhando noutra pele, e uma mensagem que
    não diz qual pele perdeu o quê manda essa pessoa abrir as três à mão.
    """
    if not faltas:
        return ""
    linhas = [f"{nome}: {', '.join(faltando)}" for nome, faltando in sorted(faltas.items())]
    return "pele que não alcança comando do catálogo -- " + "; ".join(linhas)
