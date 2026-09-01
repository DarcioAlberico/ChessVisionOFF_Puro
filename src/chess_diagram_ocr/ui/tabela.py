"""As colunas de uma tabela: o que cada uma é, e o que isso decide (S-153).

**O defeito.** Os dois `Treeview` do projeto tinham barra **vertical** e nenhuma horizontal, e
todas as colunas com `anchor="w"`. As consequências foram fotografadas, não supostas:

- no Dataset, em 940 de largura, **6 das 8 colunas** eram inalcançáveis; em 1700, quatro delas;
- na Revisão, a coluna **"Motivo"** aparecia truncada em **todas** as 129 linhas. Motivo é a
  razão de a fila existir — "ilegal: mais de um rei da mesma cor; peças brancas demais; o
  lado…" —, e o texto que diz o que conferir era o texto que não se podia ler;
- e `1623.8`, `40`, `1` e `0.082` alinhados à esquerda não se comparam por magnitude, que é a
  única leitura que uma coluna de prioridade tem.

**Uma coluna sabe o que é, e o resto sai daí.** Alinhamento, largura mínima e se a tabela
precisa de barra horizontal são consequências de a coluna ser número ou texto, e de quanto ela
declarou precisar. Declarar isso uma vez por coluna é o que faz as duas tabelas concordarem sem
que nenhuma das duas copie a regra da outra.

**A decisão é pura; `montar` só executa.** `ancora`, `largura_minima`, `largura_total` e
`precisa_de_barra_horizontal` não tocam widget nenhum e são afirmáveis sem abrir janela. O
módulo importa `tkinter` por causa de `montar`, que é a montagem das duas barras — e ela mora
aqui, e não em cada painel, porque os dois painéis erravam a **mesma** coisa.

**A barra horizontal não é o item inteiro.** Rolar para o lado é um gesto caro numa lista longa
— perde-se a coluna de referência. Por isso a fila de Revisão ganha também a **linha de
detalhe**: a tabela dá a visão geral e o rodapé dá o motivo inteiro do item selecionado, e
nenhuma das duas precisa escolher entre as duas coisas.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # só para as anotações; ver a nota de `montar` sobre o import tardio
    pass

__all__ = [
    "ANCORA_NUMERO",
    "ANCORA_TEXTO",
    "Coluna",
    "ancora",
    "largura_minima",
    "largura_total",
    "precisa_de_barra_horizontal",
]

ANCORA_NUMERO: Literal["e"] = "e"
"""Números alinham à **direita**: é o que põe unidade sobre unidade e dezena sobre dezena.

`1623.8` e `40` alinhados à esquerda só se comparam lendo os dígitos um a um. Numa fila
ordenada por prioridade, comparar por magnitude é a leitura inteira.

O tipo é `Literal` porque o `ttk.Treeview.column` só aceita os nove pontos cardeais: um
`anchor` escrito errado é `TclError` em execução, e aqui ele é erro de tipo antes disso."""

ANCORA_TEXTO: Literal["w"] = "w"
"""Texto alinha à esquerda, porque é onde a linha começa."""


@dataclass(frozen=True)
class Coluna:
    """Uma coluna de tabela: o que ela mostra, quanto pede, e o que ela é.

    `elastica` é a que absorve a folga quando a janela é maior que a soma — a FEN no Dataset, o
    Motivo na Revisão. É sempre a coluna cujo conteúdo não tem tamanho previsível.
    """

    chave: str
    titulo: str
    largura: int
    numerica: bool = False
    elastica: bool = False

    def __post_init__(self) -> None:
        if self.largura <= 0:
            raise ValueError(f"coluna {self.chave!r}: largura precisa ser positiva, veio {self.largura}")
        if self.numerica and self.elastica:
            raise ValueError(
                f"coluna {self.chave!r}: número não estica. Coluna elástica é a de conteúdo sem "
                "tamanho previsível (FEN, motivo); número tem largura conhecida."
            )


def ancora(coluna: Coluna) -> Literal["e", "w"]:
    """Para que lado o conteúdo desta coluna encosta."""
    return ANCORA_NUMERO if coluna.numerica else ANCORA_TEXTO


def largura_minima(coluna: Coluna) -> int:
    """Abaixo de quanto a coluna não encolhe. **É o que faz a barra horizontal funcionar.**

    Não é detalhe: o `ttk.Treeview` encolhe as colunas até `minwidth` (20 px de fábrica) antes
    de admitir que não cabe. Com o padrão, oito colunas espremidas em 940 px viram oito colunas
    de 20 px e a barra horizontal **nunca aparece** — que é exatamente o estado fotografado, com
    as colunas "inalcançáveis" na verdade presentes e ilegíveis.

    A elástica é a exceção: ela pode encolher até um piso menor, porque é ela que devolve espaço
    às outras quando a janela aperta, e porque é a que a linha de detalhe cobre por baixo.
    """
    return max(1, coluna.largura // 3) if coluna.elastica else coluna.largura


def largura_total(colunas: Iterable[Coluna]) -> int:
    """A soma das larguras mínimas: a largura abaixo da qual a tabela precisa rolar."""
    return sum(largura_minima(coluna) for coluna in colunas)


def precisa_de_barra_horizontal(colunas: Iterable[Coluna], largura_disponivel: int) -> bool:
    """Se a tabela não cabe na largura dada.

    O critério de aceite da S-153 é "toda coluna é alcançável em qualquer largura permitida pelo
    piso", e o teste o afirma passando a largura do piso da S-150 aqui: se der `True`, o painel
    **precisa** declarar `xscrollcommand` — e é isso que o teste vai conferir no widget.
    """
    return largura_total(colunas) > int(largura_disponivel)
