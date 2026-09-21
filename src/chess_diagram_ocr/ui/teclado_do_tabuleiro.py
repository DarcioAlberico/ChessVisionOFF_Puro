"""O que cada tecla faz no tabuleiro editável (OCR_UI ciclo 2, passo C8). Sem toolkit.

Corrigir uma casa pelo teclado custava zero teclas: o tabuleiro não recebia foco nem tecla, e
só o recorte andava por setas. A régua do passo é **três teclas por casa**, e a tabela abaixo
é o que a cumpre em duas:

* **`Tab` / `Shift+Tab`** vão à próxima / anterior casa **duvidosa** (as âmbar da leitura, ou as
  incertas; sem nenhuma, as ocupadas) -- a casa que a pessoa ia conferir de qualquer modo.
  **Depois da última, o `Tab` sai do tabuleiro** (e o `Shift+Tab`, antes da primeira): a lista
  não dá a volta. Entrar pelo teclado já seleciona a primeira (a última, entrando de trás).
* **Setas** andam uma casa, como no recorte ao lado.
* **`k q r b n p`** põem a peça **preta** na casa selecionada; com `Shift`, a **branca**.
  `Delete`/`Backspace` esvaziam; `Espaço`/`Enter` aplicam o pincel da paleta, quando há um.

A letra é a peça e não a coluna: `b` é o bispo, nunca a coluna b -- endereçar casa por
`letra+número` daria ao `b` dois papéis e a régua de três teclas ao `Enter` de desempate.
Quem quer uma casa longe usa `Tab` (as duvidosas) ou o clique; as setas ficam para o ajuste.

**As setas são atalhos globais da janela** (`ui/atalhos.py`: `←`/`→` = diagrama anterior /
próximo), e a guarda de atalhos vê a tecla **antes** do widget em foco -- um `keyPressEvent`
que tratasse a seta nunca a receberia. A suíte inteira do tronco foi quem mostrou isso: o
teste do widget sozinho passava, e passava a falhar depois de qualquer teste que tivesse
ligado a guarda. A saída é a da S-244, o ceder tipado: enquanto tem o foco, o tabuleiro
**toma para si** as ações que as setas pedem (`ACOES_DAS_SETAS`), e o ir ao diagrama vizinho
fica com os botões do painel e com o foco fora do tabuleiro -- a mesma regra que dá `←` ao
campo de texto em foco.

**O `Tab` que dava a volta era uma armadilha de teclado** (WCAG 2.1.2): com uma posição na
tela o tabuleiro consumia todo `Tab` e todo `Shift+Tab`, e `Ctrl+Tab` também caía aqui -- quem
não usa o mouse não saía dele nunca. A auditoria `teclado` não o via porque mede a cadeia pelo
`focusNextPrevChild` da **janela**, não pela tecla entregue ao widget. Por isso a lista das
duvidosas é percorrida **uma vez** e o foco segue para o controle seguinte; é o padrão de
widget composto (a grade da ARIA): `Tab` entra e sai, o que anda por dentro são as setas -- com
a concessão do passo, que o `Tab` por dentro visite as duvidosas antes de sair.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "ACAO_DE_APAGAR", "ACOES_DAS_SETAS", "ANDAR", "APAGAR", "APLICAR", "Acao", "DUVIDOSA", "PECA", "PECAS",
    "acao_da_tecla", "proxima_duvidosa",
]

# Os tipos de ação, como nomes e não como texto de tela: `tests/test_strings.py` varre os
# literais dos módulos de `ui/` à procura de português sem acento, e "peca" só escapa como o
# nome minúsculo de uma constante MAIÚSCULA (a regra da S-230).
ANDAR = "andar"
DUVIDOSA = "duvidosa"
PECA = "peca"
APAGAR = "apagar"
APLICAR = "aplicar"

PECAS = "kqrbnp"
"""As letras de peça, minúsculas = pretas; `Shift` as torna brancas (maiúsculas)."""

ACOES_DAS_SETAS: dict[str, int] = {"diagrama_anterior": -1, "proximo_diagrama": 1}
"""Ação global da tabela de atalhos -> passo no tabuleiro, para as setas que a guarda de
atalhos entregaria à janela (`←` e `→`). `↑`/`↓` não têm atalho global e chegam ao widget."""

ACAO_DE_APAGAR = "apagar_casa"
"""`Delete` também é global (`apagar_casa`, que a janela manda ao tabuleiro do Resultado); o
tabuleiro em foco a atende ele mesmo, e é o mesmo gesto sem depender de qual janela a ligou."""


@dataclass(frozen=True)
class Acao:
    """O que a tecla pede: `tipo` em {`ANDAR`, `DUVIDOSA`, `PECA`, `APAGAR`, `APLICAR`}."""

    tipo: str
    passo: int = 0
    simbolo: str = ""


def acao_da_tecla(tecla: str, *, shift: bool = False) -> Acao | None:
    """A ação de uma tecla nomeada (`"Left"`, `"Tab"`, `"k"`, `"Delete"`…), ou `None`."""
    setas = {"Left": -1, "Right": 1, "Up": -8, "Down": 8}
    if tecla in setas:
        return Acao(ANDAR, passo=setas[tecla])
    if tecla in ("Tab", "Backtab"):
        return Acao(DUVIDOSA, passo=-1 if (shift or tecla == "Backtab") else 1)
    if tecla in ("Delete", "Backspace"):
        return Acao(APAGAR)
    if tecla in ("Space", "Return", "Enter"):
        return Acao(APLICAR)
    baixa = tecla.lower()
    if len(baixa) == 1 and baixa in PECAS:
        return Acao(PECA, simbolo=baixa.upper() if shift else baixa)
    return None


def proxima_duvidosa(
    duvidosas: Sequence[int], atual: int | None, passo: int, *, dar_a_volta: bool = True
) -> int | None:
    """A duvidosa seguinte (`passo=1`) ou anterior (`-1`) a `atual`; `None` sem duvidosas.

    **A ordem é a da lista, não a do tabuleiro**: quem a monta põe primeiro a casa que mais
    merece o olho (a de menor margem, a de menor confiança), e o primeiro `Tab` vai a ela --
    é o que faz a correção caber em duas teclas. `atual=None` ou fora da lista começa na
    primeira (ou na última, andando para trás).

    Com `dar_a_volta=False` a lista **acaba**: depois da última (ou antes da primeira) devolve
    `None`, e é assim que o `Tab` do tabuleiro sabe que é hora de sair para o controle seguinte.
    """
    lista: list[int] = []
    for casa in duvidosas:
        c = int(casa)
        if 0 <= c < 64 and c not in lista:
            lista.append(c)
    if not lista:
        return None
    if atual is None or atual not in lista:
        return lista[0] if passo > 0 else lista[-1]
    indice = lista.index(atual) + (1 if passo > 0 else -1)
    if dar_a_volta:
        return lista[indice % len(lista)]
    return lista[indice] if 0 <= indice < len(lista) else None
