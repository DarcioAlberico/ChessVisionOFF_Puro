"""O que a aba Dataset **mostra**, sem toolkit nenhum (S-23/S-118/S-149/S-503).

As oito colunas, o tamanho da página, as escolhas dos filtros, a linha que uma amostra vira na
tabela e os dois textos de estatística. Tudo cálculo sobre `DatasetRow`, que já é puro --
`dataset_browser.py` decide o que é legalidade, o que é duplicata e o que cada filtro deixa
passar, e nada disso é reescrito nem aqui nem no widget.

**Por que isto virou um módulo.** `ui/dataset_panel.py` importa `tkinter` na primeira linha do
corpo -- `DatasetPanel` herda de `ttk.Frame` --, e o texto que ele monta é a parte da aba que mais
custa reescrever certo: a linha da tabela publica `Brancas` e não `w` (S-169), a coluna de FEN
alinha por ser monoespaçada (S-149), e o painel de estatística é uma tabela alinhada por espaço em
que qualquer diferença de formatação desmonta a coluna.

**O caso é o mesmo da fita, e a divergência aqui seria pior.** Duas cópias do
`f"{count / total:.2%}"` não quebram: elas só passam a discordar no dia em que alguém arredondar
diferente, e o sintoma é uma janela dizendo que a classe `p` é 12,3% do dataset e a outra dizendo
12%. Nenhuma das duas pode ser conferida contra a outra, porque as duas são "a estatística do
dataset".

**O que ficou de fora, e a fronteira é essa.** A preguiça da S-116 -- reler o `labels.csv` só
quando a aba aparece -- continua em cada frontend, porque o sinal de "a aba apareceu" é de
toolkit: no Tk é o `<Map>` que o `ttk.Notebook` dispara, no Qt é o `showEvent`. O *estado* que ela
usa (`_stale`) é uma bandeira, e uma bandeira não precisa de módulo.

`ui/dataset_panel.py` reexportava tudo o que está aqui, e saiu no corte do Tk (S-506). Quem
consome agora é `qt/painel_do_dataset.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..dataset_browser import (
    DatasetRow,
    class_distribution,
    imbalance_alerts,
    source_distribution,
    split_distribution,
)
from . import formato, strings, tabela

__all__ = [
    "COLUNAS",
    "LEGALITY_CHOICES",
    "PAGE_SIZE",
    "SPLIT_CHOICES",
    "TODOS",
    "celulas",
    "frase_de_pagina",
    "linha_de_estatisticas",
    "paginas",
    "texto_de_estatisticas",
]

TODOS = "(todos)"
"""O primeiro valor de "Livro", e o que quer dizer "não filtre por este eixo".

Um literal e não `""` porque ele **aparece na lista**: uma linha em branco no alto de um
`combobox` de trinta livros é indistinguível de um livro sem nome."""

LEGALITY_CHOICES: tuple[str, ...] = ("(todas)", "legal", "lado-a-jogar", "ilegal", "sintaxe")
SPLIT_CHOICES: tuple[str, ...] = (TODOS, "train", "val", "test")

COLUNAS: tuple[tabela.Coluna, ...] = (
    tabela.Coluna("arquivo", "Arquivo", 210),
    tabela.Coluna("fen", "FEN", 330, elastica=True),
    tabela.Coluna("lado", "Lado", 45),
    tabela.Coluna("legalidade", "Legalidade", 95),
    tabela.Coluna("split", strings.CONJUNTO, 55),
    tabela.Coluna("origem", "Livro", 150),
    tabela.Coluna("página", "Pag.", 50, numerica=True),
    tabela.Coluna("criado", "Criado em", 130),
)
"""As oito colunas, cada uma dizendo o que é (S-153).

Eram três dicionários paralelos -- `COLUMNS`, `HEADINGS`, `WIDTHS` --, e paralelo é o problema:
nada ligava a largura ao título, nada dizia que "Pag." é número, e a nona coluna entraria em três
lugares ou em dois."""

PAGE_SIZE = 200
"""Linhas por página da tabela.

**A premissa que criou isto está medida e é falsa** (S-118). A justificativa era "3.195 linhas de
uma vez travam o `Treeview` do Tk", e o `ARCHITECTURE.md` a repetia. Medido com `Treeview` real e
as mesmas 8 colunas: inserir **3.936 linhas custa 53 ms**, e limpar a tabela custa 6 ms. O que
custava era o `load_rows` que vinha antes -- 689 ms --, e esse é assunto da S-116.

**A paginação fica, e tirá-la é uma segunda decisão.** Ela não é gratuita: cobra o lugar de quem
está conferindo rótulo a rótulo, e é isso que a S-118 conserta preservando página e seleção. Mas
53 ms é o número de hoje com 3.936 linhas, e o `labels.csv` é o arquivo que o projeto existe para
fazer crescer -- a decisão de remover a paginação precisa da medição refeita quando ele dobrar,
não da premissa de 2026-07 nem desta."""


def celulas(row: DatasetRow) -> tuple[object, ...]:
    """A linha da tabela, uma célula por coluna de `COLUNAS`.

    **"Brancas" e não `w`** (S-169): o código é do CSV, e publicá-lo obriga quem lê a saber que
    `w` quer dizer brancas -- em inglês, numa janela pt-BR. O `(dup)` cola na legalidade porque
    duplicata não é um estado de legalidade e não merece uma nona coluna que fica vazia em 99%
    das linhas.
    """
    return (
        row.filename,
        row.fen,
        formato.lado_a_jogar(row.side_to_move),
        row.legality + (" (dup)" if row.is_duplicate else ""),
        formato.texto_ou_ausente(row.split),
        formato.texto_ou_ausente(row.source_pdf),
        formato.texto_ou_ausente(row.source_page),
        formato.texto_ou_ausente(row.created_at),
    )


def paginas(visiveis: int, *, tamanho: int = PAGE_SIZE) -> int:
    """Quantas páginas a lista filtrada tem. **Nunca zero**: uma lista vazia é a página 1 de 1."""
    return max(1, (visiveis + tamanho - 1) // tamanho)


def frase_de_pagina(pagina: int, visiveis: int, total: int, *, tamanho: int = PAGE_SIZE) -> str:
    """`página 2/4 — 380 de 3936 amostras`. Os dois números respondem perguntas diferentes.

    "380 de 3936" é o filtro, e "2/4" é onde se está dentro dele. Sem o primeiro, filtrar até
    sobrar nada é indistinguível de a aba não ter carregado.
    """
    return f"página {pagina + 1}/{paginas(visiveis, tamanho=tamanho)} — {visiveis} de {total} amostras"


def linha_de_estatisticas(linhas: Sequence[DatasetRow]) -> str:
    """A linha única sob a tabela: legalidade, splits e quantas imagens faltam no disco.

    Vazia quando não há amostra -- a aba ainda não leu, e um `legalidade: ` sem número afirmaria
    que o dataset está vazio quando o que se sabe é que ele não foi lido.
    """
    if not linhas:
        return ""
    por_legalidade = {
        estado: sum(1 for row in linhas if row.legality == estado)
        for estado in ("legal", "lado-a-jogar", "ilegal", "sintaxe")
    }
    splits = split_distribution(linhas)
    partes = [
        "legalidade: " + ", ".join(f"{estado} {contagem}" for estado, contagem in por_legalidade.items() if contagem),
        "splits: " + ", ".join(f"{nome} {contagem}" for nome, contagem in sorted(splits.items())),
    ]
    faltando = sum(1 for row in linhas if not row.image_exists)
    if faltando:
        partes.append(f"{faltando} sem imagem no disco")
    return " | ".join(partes)


def texto_de_estatisticas(linhas: Sequence[DatasetRow]) -> str:
    """O corpo da janela de estatísticas: classes, splits, livros e alertas de desequilíbrio.

    **É tabela alinhada por espaço**, e é por isso que quem a mostra tem de usar monoespaçada e
    não quebrar linha (S-149): `{name:>6}` e `{count:>7}` só viram coluna numa fonte em que todo
    caractere tem a mesma largura.
    """
    classes = class_distribution(linhas)
    total = sum(classes.values()) or 1
    saida = ["Casas por classe:"]
    saida += [f"  {name:>6}: {count:>7} ({count / total:.2%})" for name, count in classes.most_common()]
    saida += ["", "Amostras por split: " + ", ".join(f"{k} {v}" for k, v in sorted(split_distribution(linhas).items()))]
    saida += ["", "Amostras por livro:"]
    saida += [f"  {name}: {count}" for name, count in source_distribution(linhas).most_common(10)]
    if alertas := imbalance_alerts(classes):
        saida += ["", "Alertas:"]
        saida += [f"  {texto}" for texto in alertas]
    return "\n".join(saida)
