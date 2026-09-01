"""A partida candidata como linha de tabela: colunas, filtro e o travessão (S-86/S-503).

`COLUNAS`, `NEIGHBOUR_RADIUS`, `texto_busca`, `linha` e `rotulo`. Cálculo puro sobre
`PositionHit`, e eram privados dentro de `ui/games_dialog.py` -- que importa `tkinter` na primeira
linha do corpo, porque `GamesDialog` herda de `tk.Toplevel`.

**O travessão é a razão de isto ser compartilhado.** Numa candidata não verificada, a coluna
"Lance" mostra `—` e não `0`: a partida não diz em que lance a posição acontece **porque ela não
contém a posição**, e um número ali seria lido como resposta. Uma segunda cópia da montagem de
linha é uma cópia dessa decisão, e o dia em que uma das duas escrever `0` é o dia em que uma das
janelas passa a afirmar uma coisa que ninguém mediu.

`ui/games_dialog.py` reexportava tudo o que está aqui, com os nomes privados de antes, e saiu no
corte do Tk (S-506). Quem consome agora é `qt/dialogos.py`.
"""

from __future__ import annotations

from ..games_db import PositionHit

__all__ = ["COLUNAS", "NEIGHBOUR_RADIUS", "linha", "rotulo", "texto_busca"]

COLUNAS: tuple[tuple[str, str, int], ...] = (
    ("date", "Data", 90),
    ("white", "Brancas", 170),
    ("black", "Pretas", 170),
    ("event", "Evento", 190),
    ("result", "Resultado", 80),
    ("move", "Lance", 55),
    ("side", "Vez", 45),
)
"""As colunas, e a ordem delas é a da pergunta que a pessoa faz: *que partida é esta?* -- data e
jogadores primeiro, e o lance por último, que é consequência da escolha e não critério dela."""

NEIGHBOUR_RADIUS = 3
"""Quantos diagramas de cada lado o "aplicar aos vizinhos" alcança.

Três porque é o tamanho de um trecho analisado -- um capítulo mostra a mesma partida em quatro ou
cinco diagramas seguidos. Um raio grande transformaria um acerto em espalhamento, que é exatamente
o que a S-76 custou caro para aprender."""


def texto_busca(hit: PositionHit) -> str:
    """O que o filtro varre: os nomes, o evento e o ano -- que é como se procura uma partida."""
    return " ".join(hit.headers.get(campo, "") for campo in ("White", "Black", "Event", "Site", "Date"))


def linha(hit: PositionHit) -> tuple[str, ...]:
    """A candidata como linha, uma célula por coluna de `COLUNAS`."""
    return (
        hit.headers.get("Date", ""),
        hit.headers.get("White", ""),
        hit.headers.get("Black", ""),
        hit.headers.get("Event", ""),
        hit.headers.get("Result", ""),
        # Travessão e não "0": a partida não diz em que lance esta posição acontece, porque ela
        # não contém esta posição. Um número ali seria lido como resposta.
        str(hit.move_number) if hit.verified else "—",
        ("brancas" if hit.side_to_move == "w" else "pretas") if hit.verified else "—",
    )


def rotulo(campo: str) -> str:
    """Nome de campo como a pessoa o vê na tela, e não como o arquivo o guarda."""
    return {"move_number": "Lance", "side_to_move": "Vez"}.get(campo, campo.removeprefix("header:"))
