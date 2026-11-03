"""A classificação ECO das aberturas, embutida no pacote (S-534).

**Por que ela mora aqui e não vem de fora.** O `python-chess` não traz a tabela ECO, e a base de
partidas nem sempre traz o header `[ECO]` -- a `LumbrasGigaBase` traz em 99,99% das partidas, uma
base exportada de um servidor costuma não trazer nenhum. A sala de estudo quer dizer *"ECO: B33
Sicilian, Sveshnikov"* sob o tabuleiro em qualquer dos dois casos, e a busca (S-533) quer filtrar
por código também no segundo. A tabela é o dado que falta, e ela é pequena: **500 códigos** (A00 a
E99), cada um com a linha canônica que o define, ~30 KB de texto.

**Código sempre, nome em inglês.** O produto é pt-BR, mas o nome de uma abertura é consagrado como
está nos livros e no ChessBase -- *Sicilian, Najdorf*, *Queen's Gambit Declined*, *Ruy Lopez* --, e
traduzir "Nimzo-Indian" inventaria vocabulário que nenhum enxadrista usa. O código é o que se
filtra e o que se compara; o nome é a legenda dele.

**Duas classificações, e a diferença é o custo.**

- `classificar(tabuleiro_ou_lances)` casa **por posição**: cada linha da tabela é reproduzida uma
  vez e guardada pela FEN sem contadores, e a partida é percorrida lance a lance procurando a
  posição mais profunda que a tabela conhece. Transposição vale: `1.Nf3 d5 2.d4 Nf6 3.c4 e6` é a
  mesma posição de `1.d4 Nf6 2.c4 e6 3.Nf3`, e recebe o mesmo E10. Custa um `push_san` por lance
  -- **~1 ms por partida**, o preço certo para *uma* partida na sala.
- `classificar_lances(sans)` casa **pela ordem dos lances**, numa árvore de prefixos sem tabuleiro
  nenhum: **~5 µs por partida**. É o que o índice (`games_index`) usa nas partidas sem header,
  porque o orçamento da S-534 é *"< +30% no tempo de indexar"* e o replay custaria +1 ms × 10
  milhões de partidas = quase três horas sobre os nove minutos da gigabase. Ele perde a
  transposição -- e a sala, ao abrir a partida, reclassifica por posição, então o que aparece
  sob o tabuleiro é sempre a leitura completa.

**O código mais profundo vence.** `1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6` passa por B20,
B27, B50, B54, B56 e para em **B90**: o que se guarda é a linha mais longa da tabela que a partida
alcançou, e não a primeira nem a última posição casada.

**E `None` quando a tabela não alcança nada** -- e não "A00": dizer um código sobre o que a tabela
não conhece seria um número enganoso, que é o defeito que este projeto já cometeu e corrigiu
(S-135). Uma partida que comece na posição inicial **sempre** recebe algum código: as vinte
primeiras jogadas legais têm linha (as catorze menos jogadas todas em A00), e é assim na
classificação padrão. Quem devolve `None` é a posição de onde não se chegou por lance nenhum -- o
estudo montado de um `[FEN]`, que é a `Endgame_Study_Database` inteira, e a raiz de um estudo
aberto de um diagrama de livro.

A tabela é a **classificação padrão** (a do Informador, a que todo programa e toda base usam),
escrita a partir dela; as sublinhas de um código (`B90a`, `B90b`) que algumas bases acrescentam são
cortadas para o código de três caracteres, que é a unidade da classificação.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import chess

__all__ = [
    "Abertura",
    "LANCES_EXAMINADOS",
    "SEPARADOR",
    "classificar",
    "classificar_lances",
    "codigo_do_header",
    "frase",
    "frase_da_abertura",
    "frase_do_tabuleiro",
    "lances_do_movetext",
    "nome",
    "tabela",
]

LANCES_EXAMINADOS = 30
"""Quantos meios-lances da partida a classificação percorre.

**Eram 24, e 24 era menos que a tabela.** A linha mais longa tem **28** meios-lances (D69) e há
outras três com 24 ou mais (D89 com 26, C99 com 25, C98 e D68 com 24) -- o teto cortava a leitura
antes de elas poderem casar, e **C99 era inalcançável**: as 52 partidas C99 da amostra de 2026-09-04
erraram todas, todas as 52. Trinta cobrem a linha mais longa com folga de duas, e o custo é só o de
uma partida que fica em livro até o décimo quinto lance -- que são poucas.

Depois do fim da linha mais longa não há resposta a comprar: cada `push_san` a mais seria custo
puro. O teto é da tabela, e não da partida."""

_RE_NUMERO = re.compile(r"^\d+\.(\.\.)?")
_RE_CODIGO = re.compile(r"^([A-E])(\d\d)")
_RE_COMENTARIO = re.compile(r"\{[^}]*\}")
_RE_LANCE = re.compile(r"(?<![\w/])([a-hKQRBNO][a-hKQRBNOx1-8=+#\-]{1,6})(?![\w/])")
"""Um lance em SAN no meio do movetext cru: começa por peça, coluna ou `O`, e é palavra inteira.

Os números (`12.`), os resultados (`1-0`, `1/2-1/2`), os NAGs (`$14`) e os `!?` ficam de fora
porque não começam por esses caracteres ou porque o caractere seguinte é de palavra. É a
tokenização barata que o índice pode pagar: uma expressão regular sobre duas linhas de texto, e
não um tabuleiro."""

SEPARADOR = " · "
"""O que separa o código do nome na frase da sala: `ECO B33 · Sicilian, Sveshnikov`."""


@dataclass(frozen=True)
class Abertura:
    """Um código ECO com a legenda dele e a linha que o define."""

    codigo: str
    nome: str
    lances: tuple[str, ...]
    """A linha canônica, em SAN, sem os números dos lances."""

    @property
    def profundidade(self) -> int:
        return len(self.lances)

    def __str__(self) -> str:
        return f"{self.codigo} {self.nome}"


_TABELA = """
A00|Uncommon Opening|1.b4
A00|Uncommon Opening|1.g4
A00|Uncommon Opening|1.Nc3
A00|Uncommon Opening|1.a3
A00|Uncommon Opening|1.f3
A00|Uncommon Opening|1.h4
A00|Uncommon Opening|1.e3
A00|Uncommon Opening|1.d3
A00|Uncommon Opening|1.c3
A00|Uncommon Opening|1.Nh3
A00|Uncommon Opening|1.Na3
A00|Uncommon Opening|1.h3
A00|Uncommon Opening|1.a4
A00|Uncommon Opening|1.g3
A01|Nimzovich-Larsen Attack|1.b3
A02|Bird's Opening|1.f4
A03|Bird's Opening|1.f4 d5
A04|Reti Opening|1.Nf3
A05|Reti Opening|1.Nf3 Nf6
A06|Reti Opening|1.Nf3 d5
A07|King's Indian Attack|1.Nf3 d5 2.g3
A08|King's Indian Attack|1.Nf3 d5 2.g3 c5 3.Bg2
A09|Reti Opening|1.Nf3 d5 2.c4
A10|English|1.c4
A11|English, Caro-Kann Defensive System|1.c4 c6
A12|English with b3|1.c4 c6 2.Nf3 d5 3.b3
A13|English|1.c4 e6
A14|English|1.c4 e6 2.Nf3 d5 3.g3 Nf6 4.Bg2 Be7 5.O-O
A15|English|1.c4 Nf6
A16|English|1.c4 Nf6 2.Nc3
A17|English|1.c4 Nf6 2.Nc3 e6
A18|English, Mikenas-Carls|1.c4 Nf6 2.Nc3 e6 3.e4
A19|English, Mikenas-Carls, Sicilian Variation|1.c4 Nf6 2.Nc3 e6 3.e4 c5
A20|English|1.c4 e5
A21|English|1.c4 e5 2.Nc3
A22|English|1.c4 e5 2.Nc3 Nf6
A23|English, Bremen System, Keres Variation|1.c4 e5 2.Nc3 Nf6 3.g3 c6
A24|English, Bremen System with ...g6|1.c4 e5 2.Nc3 Nf6 3.g3 g6
A25|English|1.c4 e5 2.Nc3 Nc6
A26|English|1.c4 e5 2.Nc3 Nc6 3.g3 g6 4.Bg2 Bg7 5.d3 d6
A27|English, Three Knights System|1.c4 e5 2.Nc3 Nc6 3.Nf3
A28|English|1.c4 e5 2.Nc3 Nc6 3.Nf3 Nf6
A29|English, Four Knights, Kingside Fianchetto|1.c4 e5 2.Nc3 Nc6 3.Nf3 Nf6 4.g3
A30|English, Symmetrical|1.c4 c5
A31|English, Symmetrical, Benoni Formation|1.c4 c5 2.Nf3 Nf6 3.d4
A32|English, Symmetrical Variation|1.c4 c5 2.Nf3 Nf6 3.d4 cxd4 4.Nxd4 e6
A33|English, Symmetrical|1.c4 c5 2.Nf3 Nf6 3.d4 cxd4 4.Nxd4 e6 5.Nc3 Nc6
A34|English, Symmetrical|1.c4 c5 2.Nc3
A35|English, Symmetrical|1.c4 c5 2.Nc3 Nc6
A36|English|1.c4 c5 2.Nc3 Nc6 3.g3
A37|English, Symmetrical|1.c4 c5 2.Nc3 Nc6 3.g3 g6 4.Bg2 Bg7 5.Nf3
A38|English, Symmetrical|1.c4 c5 2.Nc3 Nc6 3.g3 g6 4.Bg2 Bg7 5.Nf3 Nf6
A39|English, Symmetrical, Main line with d4|1.c4 c5 2.Nc3 Nc6 3.g3 g6 4.Bg2 Bg7 5.Nf3 Nf6 6.O-O O-O 7.d4
A40|Queen's Pawn Game|1.d4
A41|Queen's Pawn Game (with ...d6)|1.d4 d6
A42|Modern Defense, Averbakh System|1.d4 d6 2.c4 g6 3.Nc3 Bg7 4.e4
A43|Old Benoni|1.d4 c5
A44|Old Benoni Defense|1.d4 c5 2.d5 e5
A45|Queen's Pawn Game|1.d4 Nf6
A46|Queen's Pawn Game|1.d4 Nf6 2.Nf3
A47|Queen's Indian|1.d4 Nf6 2.Nf3 b6
A48|King's Indian|1.d4 Nf6 2.Nf3 g6
A49|King's Indian, Fianchetto without c4|1.d4 Nf6 2.Nf3 g6 3.g3
A50|Queen's Pawn Game|1.d4 Nf6 2.c4
A51|Budapest Gambit|1.d4 Nf6 2.c4 e5
A52|Budapest Gambit|1.d4 Nf6 2.c4 e5 3.dxe5 Ng4
A53|Old Indian|1.d4 Nf6 2.c4 d6
A54|Old Indian, Ukrainian Variation, 4.Nf3|1.d4 Nf6 2.c4 d6 3.Nc3 e5 4.Nf3
A55|Old Indian, Main line|1.d4 Nf6 2.c4 d6 3.Nc3 e5 4.Nf3 Nbd7 5.e4
A56|Benoni Defense|1.d4 Nf6 2.c4 c5
A57|Benko Gambit|1.d4 Nf6 2.c4 c5 3.d5 b5
A58|Benko Gambit|1.d4 Nf6 2.c4 c5 3.d5 b5 4.cxb5 a6 5.bxa6
A59|Benko Gambit|1.d4 Nf6 2.c4 c5 3.d5 b5 4.cxb5 a6 5.bxa6 Bxa6 6.Nc3 d6 7.e4
A60|Benoni Defense|1.d4 Nf6 2.c4 c5 3.d5 e6
A61|Benoni|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.Nf3 g6
A62|Benoni, Fianchetto Variation|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.Nf3 g6 7.g3 Bg7 8.Bg2 O-O
A63|Benoni, Fianchetto, 9...Nbd7|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.Nf3 g6 7.g3 Bg7 8.Bg2 O-O 9.O-O Nbd7
A64|Benoni, Fianchetto, 11...Re8|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.Nf3 g6 7.g3 Bg7 8.Bg2 O-O 9.O-O Nbd7 10.Nd2 a6 11.a4 Re8
A65|Benoni, 6.e4|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4
A66|Benoni|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.f4
A67|Benoni, Taimanov Variation|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.f4 Bg7 8.Bb5+
A68|Benoni, Four Pawns Attack|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.f4 Bg7 8.Nf3 O-O
A69|Benoni, Four Pawns Attack, Main line|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.f4 Bg7 8.Nf3 O-O 9.Be2 Re8
A70|Benoni, Classical with 7.Nf3|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3
A71|Benoni, Classical, 8.Bg5|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3 Bg7 8.Bg5
A72|Benoni, Classical without 9.O-O|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3 Bg7 8.Be2 O-O
A73|Benoni, Classical, 9.O-O|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3 Bg7 8.Be2 O-O 9.O-O
A74|Benoni, Classical, 9...a6, 10.a4|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3 Bg7 8.Be2 O-O 9.O-O a6 10.a4
A75|Benoni, Classical with ...a6 and 10...Bg4|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3 Bg7 8.Be2 O-O 9.O-O a6 10.a4 Bg4
A76|Benoni, Classical, 9...Re8|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3 Bg7 8.Be2 O-O 9.O-O Re8
A77|Benoni, Classical, 9...Re8, 10.Nd2|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3 Bg7 8.Be2 O-O 9.O-O Re8 10.Nd2
A78|Benoni, Classical with ...Re8 and ...Na6|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3 Bg7 8.Be2 O-O 9.O-O Re8 10.Nd2 Na6
A79|Benoni, Classical, 11.f3|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3 Bg7 8.Be2 O-O 9.O-O Re8 10.Nd2 Na6 11.f3
A80|Dutch|1.d4 f5
A81|Dutch|1.d4 f5 2.g3
A82|Dutch, Staunton Gambit|1.d4 f5 2.e4
A83|Dutch, Staunton Gambit|1.d4 f5 2.e4 fxe4 3.Nc3 Nf6 4.Bg5
A84|Dutch|1.d4 f5 2.c4
A85|Dutch, with c4 & Nc3|1.d4 f5 2.c4 Nf6 3.Nc3
A86|Dutch|1.d4 f5 2.c4 Nf6 3.g3
A87|Dutch, Leningrad, Main Variation|1.d4 f5 2.c4 Nf6 3.g3 g6 4.Bg2 Bg7 5.Nf3
A88|Dutch, Leningrad, Main Variation with c6|1.d4 f5 2.c4 Nf6 3.g3 g6 4.Bg2 Bg7 5.Nf3 O-O 6.O-O d6 7.Nc3 c6
A89|Dutch, Leningrad, Main Variation with Nc6|1.d4 f5 2.c4 Nf6 3.g3 g6 4.Bg2 Bg7 5.Nf3 O-O 6.O-O d6 7.Nc3 Nc6
A90|Dutch|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2
A91|Dutch Defense|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2 Be7
A92|Dutch|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2 Be7 5.Nf3 O-O
A93|Dutch, Stonewall, Botvinnik Variation|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2 Be7 5.Nf3 O-O 6.O-O d5 7.b3
A94|Dutch, Stonewall with Ba3|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2 Be7 5.Nf3 O-O 6.O-O d5 7.b3 c6 8.Ba3
A95|Dutch, Stonewall|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2 Be7 5.Nf3 O-O 6.O-O d5 7.Nc3 c6
A96|Dutch, Classical Variation|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2 Be7 5.Nf3 O-O 6.O-O d6
A97|Dutch, Ilyin-Genevsky|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2 Be7 5.Nf3 O-O 6.O-O d6 7.Nc3 Qe8
A98|Dutch, Ilyin-Genevsky Variation with Qc2|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2 Be7 5.Nf3 O-O 6.O-O d6 7.Nc3 Qe8 8.Qc2
A99|Dutch, Ilyin-Genevsky Variation with b3|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2 Be7 5.Nf3 O-O 6.O-O d6 7.Nc3 Qe8 8.b3
B00|Uncommon King's Pawn Opening|1.e4
B00|Nimzovich Defense|1.e4 Nc6
B00|Owen Defense|1.e4 b6
B00|St. George Defense|1.e4 a6
B01|Scandinavian|1.e4 d5
B02|Alekhine's Defense|1.e4 Nf6
B03|Alekhine's Defense|1.e4 Nf6 2.e5 Nd5 3.d4
B04|Alekhine's Defense, Modern|1.e4 Nf6 2.e5 Nd5 3.d4 d6 4.Nf3
B05|Alekhine's Defense, Modern|1.e4 Nf6 2.e5 Nd5 3.d4 d6 4.Nf3 Bg4
B06|Robatsch (Modern) Defense|1.e4 g6
B07|Pirc|1.e4 d6 2.d4 Nf6
B08|Pirc, Classical|1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Nf3
B09|Pirc, Austrian Attack|1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.f4
B10|Caro-Kann|1.e4 c6
B11|Caro-Kann, Two Knights, 3...Bg4|1.e4 c6 2.Nc3 d5 3.Nf3 Bg4
B12|Caro-Kann Defense|1.e4 c6 2.d4
B13|Caro-Kann, Exchange|1.e4 c6 2.d4 d5 3.exd5 cxd5
B14|Caro-Kann, Panov-Botvinnik Attack|1.e4 c6 2.d4 d5 3.exd5 cxd5 4.c4 Nf6 5.Nc3 e6
B15|Caro-Kann|1.e4 c6 2.d4 d5 3.Nc3
B16|Caro-Kann, Bronstein-Larsen Variation|1.e4 c6 2.d4 d5 3.Nc3 dxe4 4.Nxe4 Nf6 5.Nxf6+ gxf6
B17|Caro-Kann, Steinitz Variation|1.e4 c6 2.d4 d5 3.Nc3 dxe4 4.Nxe4 Nd7
B18|Caro-Kann, Classical|1.e4 c6 2.d4 d5 3.Nc3 dxe4 4.Nxe4 Bf5
B19|Caro-Kann, Classical|1.e4 c6 2.d4 d5 3.Nc3 dxe4 4.Nxe4 Bf5 5.Ng3 Bg6 6.h4 h6 7.Nf3 Nd7
B20|Sicilian|1.e4 c5
B21|Sicilian, Grand Prix Attack|1.e4 c5 2.f4
B21|Sicilian, Smith-Morra Gambit|1.e4 c5 2.d4
B22|Sicilian, Alapin|1.e4 c5 2.c3
B23|Sicilian, Closed|1.e4 c5 2.Nc3
B24|Sicilian, Closed|1.e4 c5 2.Nc3 Nc6 3.g3
B25|Sicilian, Closed|1.e4 c5 2.Nc3 Nc6 3.g3 g6 4.Bg2 Bg7 5.d3 d6
B26|Sicilian, Closed, 6.Be3|1.e4 c5 2.Nc3 Nc6 3.g3 g6 4.Bg2 Bg7 5.d3 d6 6.Be3
B27|Sicilian|1.e4 c5 2.Nf3
B28|Sicilian, O'Kelly Variation|1.e4 c5 2.Nf3 a6
B29|Sicilian, Nimzovich-Rubinstein|1.e4 c5 2.Nf3 Nf6
B30|Sicilian|1.e4 c5 2.Nf3 Nc6
B31|Sicilian, Rossolimo Variation|1.e4 c5 2.Nf3 Nc6 3.Bb5 g6
B32|Sicilian|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 e5
B33|Sicilian, Sveshnikov|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e5
B34|Sicilian, Accelerated Fianchetto, Exchange Variation|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 g6 5.Nxc6
B35|Sicilian, Accelerated Fianchetto, Modern Variation with Bc4|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 g6 5.Nc3 Bg7 6.Be3 Nf6 7.Bc4
B36|Sicilian, Accelerated Fianchetto, Maroczy Bind|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 g6 5.c4
B37|Sicilian, Accelerated Fianchetto, Maroczy Bind, 5...Bg7|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 g6 5.c4 Bg7
B38|Sicilian, Accelerated Fianchetto, Maroczy Bind, 6.Be3|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 g6 5.c4 Bg7 6.Be3
B39|Sicilian, Accelerated Fianchetto, Breyer Variation|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 g6 5.c4 Bg7 6.Be3 Nf6 7.Nc3 Ng4
B40|Sicilian|1.e4 c5 2.Nf3 e6
B41|Sicilian, Kan|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 a6
B42|Sicilian, Kan, 5.Bd3|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 a6 5.Bd3
B43|Sicilian, Kan, 5.Nc3|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 a6 5.Nc3
B44|Sicilian|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 Nc6
B45|Sicilian, Taimanov|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 Nc6 5.Nc3
B46|Sicilian, Taimanov Variation|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 Nc6 5.Nc3 a6
B47|Sicilian, Taimanov (Bastrikov) Variation|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 Nc6 5.Nc3 Qc7
B48|Sicilian, Taimanov Variation|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 Nc6 5.Nc3 Qc7 6.Be3
B49|Sicilian, Taimanov Variation|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 Nc6 5.Nc3 Qc7 6.Be3 a6 7.Be2
B50|Sicilian|1.e4 c5 2.Nf3 d6
B51|Sicilian, Canal-Sokolsky (Rossolimo) Attack|1.e4 c5 2.Nf3 d6 3.Bb5+
B52|Sicilian, Canal-Sokolsky Attack, 3...Bd7|1.e4 c5 2.Nf3 d6 3.Bb5+ Bd7
B53|Sicilian|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Qxd4
B54|Sicilian|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4
B55|Sicilian, Prins Variation, Venice Attack|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.f3 e5 6.Bb5+
B56|Sicilian|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3
B57|Sicilian, Sozin|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bc4
B58|Sicilian, Classical|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Be2
B59|Sicilian, Boleslavsky Variation, 7.Nb3|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Be2 e5 7.Nb3
B60|Sicilian, Richter-Rauzer|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bg5
B61|Sicilian, Richter-Rauzer, Larsen Variation, 7.Qd2|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bg5 Bd7 7.Qd2
B62|Sicilian, Richter-Rauzer|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bg5 e6
B63|Sicilian, Richter-Rauzer Attack|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bg5 e6 7.Qd2
B64|Sicilian, Richter-Rauzer Attack|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bg5 e6 7.Qd2 Be7 8.O-O-O O-O 9.f4
B65|Sicilian, Richter-Rauzer Attack, 7...Be7 Defense, 9...Nxd4|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bg5 e6 7.Qd2 Be7 8.O-O-O O-O 9.f4 Nxd4 10.Qxd4
B66|Sicilian, Richter-Rauzer Attack, 7...a6|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bg5 e6 7.Qd2 a6
B67|Sicilian, Richter-Rauzer Attack, 7...a6 Defense, 8...Bd7|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bg5 e6 7.Qd2 a6 8.O-O-O Bd7
B68|Sicilian, Richter-Rauzer Attack, 7...a6 Defense, 9...Be7|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bg5 e6 7.Qd2 a6 8.O-O-O Bd7 9.f4 Be7
B69|Sicilian, Richter-Rauzer Attack, 7...a6 Defense, 11.Bxf6|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6 6.Bg5 e6 7.Qd2 a6 8.O-O-O Bd7 9.f4 Be7 10.Nf3 b5 11.Bxf6
B70|Sicilian, Dragon Variation|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6
B71|Sicilian, Dragon, Levenfish Variation|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6 6.f4
B72|Sicilian, Dragon|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6 6.Be3
B73|Sicilian, Dragon, Classical|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6 6.Be3 Bg7 7.Be2 Nc6 8.O-O
B74|Sicilian, Dragon, Classical|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6 6.Be3 Bg7 7.Be2 Nc6 8.O-O O-O 9.Nb3
B75|Sicilian, Dragon, Yugoslav Attack|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6 6.Be3 Bg7 7.f3
B76|Sicilian, Dragon, Yugoslav Attack|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6 6.Be3 Bg7 7.f3 O-O
B77|Sicilian, Dragon, Yugoslav Attack|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6 6.Be3 Bg7 7.f3 O-O 8.Qd2 Nc6 9.Bc4
B78|Sicilian, Dragon, Yugoslav Attack, 10.castle long|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6 6.Be3 Bg7 7.f3 O-O 8.Qd2 Nc6 9.Bc4 Bd7 10.O-O-O
B79|Sicilian, Dragon, Yugoslav Attack, 12.h4|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6 6.Be3 Bg7 7.f3 O-O 8.Qd2 Nc6 9.Bc4 Bd7 10.O-O-O Qa5 11.Bb3 Rfc8 12.h4
B80|Sicilian, Scheveningen|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6
B81|Sicilian, Scheveningen, Keres Attack|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6 6.g4
B82|Sicilian, Scheveningen|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6 6.f4
B83|Sicilian|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6 6.Be2
B84|Sicilian, Scheveningen|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6 6.Be2 a6
B85|Sicilian, Scheveningen, Classical|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6 6.Be2 a6 7.O-O Qc7 8.f4 Nc6
B86|Sicilian, Fischer-Sozin Attack|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6 6.Bc4
B87|Sicilian, Fischer-Sozin with ...a6 and ...b5|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6 6.Bc4 a6 7.Bb3 b5
B88|Sicilian, Fischer-Sozin Attack|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6 6.Bc4 Nc6
B89|Sicilian|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6 6.Bc4 Nc6 7.Be3
B90|Sicilian, Najdorf|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6
B91|Sicilian, Najdorf, Zagreb (Fianchetto) Variation|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.g3
B92|Sicilian, Najdorf, Opocensky Variation|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Be2
B93|Sicilian, Najdorf, 6.f4|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.f4
B94|Sicilian, Najdorf, 6.Bg5|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Bg5 Nbd7
B95|Sicilian, Najdorf, 6...e6|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Bg5 e6
B96|Sicilian, Najdorf|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Bg5 e6 7.f4
B97|Sicilian, Najdorf, Poisoned Pawn|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Bg5 e6 7.f4 Qb6
B98|Sicilian, Najdorf|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Bg5 e6 7.f4 Be7
B99|Sicilian, Najdorf, 7...Be7 Main line|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Bg5 e6 7.f4 Be7 8.Qf3 Qc7 9.O-O-O Nbd7
C00|French Defense|1.e4 e6
C01|French, Exchange|1.e4 e6 2.d4 d5 3.exd5
C02|French, Advance|1.e4 e6 2.d4 d5 3.e5
C03|French, Tarrasch|1.e4 e6 2.d4 d5 3.Nd2
C04|French, Tarrasch, Guimard Main line|1.e4 e6 2.d4 d5 3.Nd2 Nc6 4.Ngf3 Nf6
C05|French, Tarrasch|1.e4 e6 2.d4 d5 3.Nd2 Nf6
C06|French, Tarrasch|1.e4 e6 2.d4 d5 3.Nd2 Nf6 4.e5 Nfd7 5.Bd3 c5 6.c3 Nc6 7.Ne2 cxd4 8.cxd4
C07|French, Tarrasch|1.e4 e6 2.d4 d5 3.Nd2 c5
C08|French, Tarrasch, Open, 4.exd5 exd5|1.e4 e6 2.d4 d5 3.Nd2 c5 4.exd5 exd5
C09|French, Tarrasch, Open Variation, Main line|1.e4 e6 2.d4 d5 3.Nd2 c5 4.exd5 exd5 5.Ngf3 Nc6
C10|French|1.e4 e6 2.d4 d5 3.Nc3
C11|French|1.e4 e6 2.d4 d5 3.Nc3 Nf6
C12|French, MacCutcheon|1.e4 e6 2.d4 d5 3.Nc3 Nf6 4.Bg5 Bb4
C13|French|1.e4 e6 2.d4 d5 3.Nc3 Nf6 4.Bg5 Be7
C14|French, Classical|1.e4 e6 2.d4 d5 3.Nc3 Nf6 4.Bg5 Be7 5.e5 Nfd7 6.Bxe7 Qxe7
C15|French, Winawer|1.e4 e6 2.d4 d5 3.Nc3 Bb4
C16|French, Winawer|1.e4 e6 2.d4 d5 3.Nc3 Bb4 4.e5
C17|French, Winawer, Advance|1.e4 e6 2.d4 d5 3.Nc3 Bb4 4.e5 c5
C18|French, Winawer|1.e4 e6 2.d4 d5 3.Nc3 Bb4 4.e5 c5 5.a3 Bxc3+ 6.bxc3
C19|French, Winawer, Advance|1.e4 e6 2.d4 d5 3.Nc3 Bb4 4.e5 c5 5.a3 Bxc3+ 6.bxc3 Ne7
C20|King's Pawn Game|1.e4 e5
C21|Center Game|1.e4 e5 2.d4 exd4
C22|Center Game|1.e4 e5 2.d4 exd4 3.Qxd4 Nc6
C23|Bishop's Opening|1.e4 e5 2.Bc4
C24|Bishop's Opening|1.e4 e5 2.Bc4 Nf6
C25|Vienna|1.e4 e5 2.Nc3
C26|Vienna|1.e4 e5 2.Nc3 Nf6
C27|Vienna Game|1.e4 e5 2.Nc3 Nf6 3.Bc4 Nxe4
C28|Vienna Game|1.e4 e5 2.Nc3 Nf6 3.Bc4 Nc6
C29|Vienna Gambit|1.e4 e5 2.Nc3 Nf6 3.f4 d5
C30|King's Gambit|1.e4 e5 2.f4
C31|King's Gambit Declined, Falkbeer Counter Gambit|1.e4 e5 2.f4 d5
C32|King's Gambit Declined, Falkbeer Counter Gambit|1.e4 e5 2.f4 d5 3.exd5 e4 4.d3 Nf6
C33|King's Gambit Accepted|1.e4 e5 2.f4 exf4
C34|King's Gambit Accepted|1.e4 e5 2.f4 exf4 3.Nf3
C35|King's Gambit Accepted, Cunningham|1.e4 e5 2.f4 exf4 3.Nf3 Be7
C36|King's Gambit Accepted, Abbazia Defense|1.e4 e5 2.f4 exf4 3.Nf3 d5
C37|King's Gambit Accepted|1.e4 e5 2.f4 exf4 3.Nf3 g5 4.Nc3
C37|King's Gambit Accepted, Muzio Gambit|1.e4 e5 2.f4 exf4 3.Nf3 g5 4.Bc4 g4 5.O-O
C38|King's Gambit Accepted|1.e4 e5 2.f4 exf4 3.Nf3 g5 4.Bc4 Bg7
C39|King's Gambit Accepted|1.e4 e5 2.f4 exf4 3.Nf3 g5 4.h4
C40|King's Knight Opening|1.e4 e5 2.Nf3
C41|Philidor Defense|1.e4 e5 2.Nf3 d6
C42|Petrov Defense|1.e4 e5 2.Nf3 Nf6
C43|Petrov, Modern Attack|1.e4 e5 2.Nf3 Nf6 3.d4
C44|King's Pawn Game|1.e4 e5 2.Nf3 Nc6
C45|Scotch Game|1.e4 e5 2.Nf3 Nc6 3.d4 exd4 4.Nxd4
C46|Three Knights|1.e4 e5 2.Nf3 Nc6 3.Nc3
C47|Four Knights|1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6
C48|Four Knights|1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Bb5
C49|Four Knights|1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Bb5 Bb4
C50|Giuoco Piano|1.e4 e5 2.Nf3 Nc6 3.Bc4
C51|Evans Gambit|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.b4
C52|Evans Gambit|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.b4 Bxb4 5.c3 Ba5
C53|Giuoco Piano|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3
C54|Giuoco Piano|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6 5.d4 exd4 6.cxd4
C55|Two Knights Defense|1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6
C56|Two Knights|1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.d4 exd4 5.O-O Nxe4
C57|Two Knights|1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5
C58|Two Knights|1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Na5
C59|Two Knights|1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Na5 6.Bb5+ c6 7.dxc6 bxc6 8.Be2 h6
C60|Ruy Lopez|1.e4 e5 2.Nf3 Nc6 3.Bb5
C61|Ruy Lopez, Bird's Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 Nd4
C62|Ruy Lopez, Old Steinitz Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 d6
C63|Ruy Lopez, Schliemann Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 f5
C64|Ruy Lopez, Classical|1.e4 e5 2.Nf3 Nc6 3.Bb5 Bc5
C65|Ruy Lopez, Berlin Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6
C66|Ruy Lopez|1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6 4.O-O d6
C67|Ruy Lopez|1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6 4.O-O Nxe4
C68|Ruy Lopez, Exchange|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Bxc6
C69|Ruy Lopez, Exchange, Gligoric Variation|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Bxc6 dxc6 5.O-O f6
C70|Ruy Lopez|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4
C71|Ruy Lopez|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 d6
C72|Ruy Lopez, Modern Steinitz Defense, 5.O-O|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 d6 5.O-O
C73|Ruy Lopez, Modern Steinitz Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 d6 5.Bxc6+ bxc6 6.d4
C74|Ruy Lopez, Modern Steinitz Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 d6 5.c3
C75|Ruy Lopez, Modern Steinitz Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 d6 5.c3 Bd7 6.d4 Nge7
C76|Ruy Lopez, Modern Steinitz Defense, Fianchetto Variation|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 d6 5.c3 Bd7 6.d4 g6
C77|Ruy Lopez|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6
C78|Ruy Lopez|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O
C79|Ruy Lopez, Steinitz Defense Deferred|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O d6
C80|Ruy Lopez, Open|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Nxe4
C81|Ruy Lopez, Open, Howell Attack|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Nxe4 6.d4 b5 7.Bb3 d5 8.dxe5 Be6 9.Qe2
C82|Ruy Lopez, Open|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Nxe4 6.d4 b5 7.Bb3 d5 8.dxe5 Be6 9.c3
C83|Ruy Lopez, Open, Classical Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Nxe4 6.d4 b5 7.Bb3 d5 8.dxe5 Be6 9.c3 Be7
C84|Ruy Lopez, Closed|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7
C85|Ruy Lopez, Exchange Variation Doubly Deferred|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Bxc6 dxc6
C86|Ruy Lopez, Worrall Attack|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Qe2
C87|Ruy Lopez|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 d6
C88|Ruy Lopez|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3
C89|Ruy Lopez, Marshall|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 O-O 8.c3 d5
C90|Ruy Lopez, Closed|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3
C91|Ruy Lopez, Closed|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.d4
C92|Ruy Lopez, Closed|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3
C93|Ruy Lopez, Closed, Smyslov Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3 h6
C94|Ruy Lopez, Closed, Breyer Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3 Nb8
C95|Ruy Lopez, Closed, Breyer|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3 Nb8 10.d4
C96|Ruy Lopez, Closed|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3 Na5 10.Bc2
C97|Ruy Lopez, Closed, Chigorin|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3 Na5 10.Bc2 c5 11.d4 Qc7
C98|Ruy Lopez, Closed, Chigorin|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3 Na5 10.Bc2 c5 11.d4 Qc7 12.Nbd2 Nc6
C99|Ruy Lopez, Closed, Chigorin, 12...cxd4|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3 Na5 10.Bc2 c5 11.d4 Qc7 12.Nbd2 cxd4 13.cxd4
D00|Queen's Pawn Game|1.d4 d5
D01|Richter-Veresov Attack|1.d4 d5 2.Nc3 Nf6 3.Bg5
D02|Queen's Pawn Game|1.d4 d5 2.Nf3
D03|Torre Attack (Tartakower Variation)|1.d4 d5 2.Nf3 Nf6 3.Bg5
D04|Queen's Pawn Game|1.d4 d5 2.Nf3 Nf6 3.e3
D05|Queen's Pawn Game, Colle System|1.d4 d5 2.Nf3 Nf6 3.e3 e6
D06|Queen's Gambit|1.d4 d5 2.c4
D07|Queen's Gambit Declined, Chigorin Defense|1.d4 d5 2.c4 Nc6
D08|Queen's Gambit Declined, Albin Counter Gambit|1.d4 d5 2.c4 e5
D09|Queen's Gambit Declined, Albin Counter Gambit, 5.g3|1.d4 d5 2.c4 e5 3.dxe5 d4 4.Nf3 Nc6 5.g3
D10|Queen's Gambit Declined Slav|1.d4 d5 2.c4 c6
D11|Queen's Gambit Declined Slav|1.d4 d5 2.c4 c6 3.Nf3
D12|Queen's Gambit Declined Slav|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.e3 Bf5
D13|Queen's Gambit Declined Slav, Exchange Variation|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.cxd5 cxd5
D14|Queen's Gambit Declined Slav, Exchange Variation|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.cxd5 cxd5 5.Nc3 Nc6 6.Bf4 Bf5
D15|Queen's Gambit Declined Slav|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.Nc3
D16|Queen's Gambit Declined Slav Accepted, Alapin Variation|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.Nc3 dxc4 5.a4
D17|Queen's Gambit Declined Slav|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.Nc3 dxc4 5.a4 Bf5
D18|Queen's Gambit Declined Slav, Dutch|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.Nc3 dxc4 5.a4 Bf5 6.e3
D19|Queen's Gambit Declined Slav, Dutch|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.Nc3 dxc4 5.a4 Bf5 6.e3 e6 7.Bxc4 Bb4 8.O-O
D20|Queen's Gambit Accepted|1.d4 d5 2.c4 dxc4
D21|Queen's Gambit Accepted, 3.Nf3|1.d4 d5 2.c4 dxc4 3.Nf3
D22|Queen's Gambit Accepted, Alekhine Defense|1.d4 d5 2.c4 dxc4 3.Nf3 a6
D23|Queen's Gambit Accepted|1.d4 d5 2.c4 dxc4 3.Nf3 Nf6
D24|Queen's Gambit Accepted, 4.Nc3|1.d4 d5 2.c4 dxc4 3.Nf3 Nf6 4.Nc3
D25|Queen's Gambit Accepted, 4.e3|1.d4 d5 2.c4 dxc4 3.Nf3 Nf6 4.e3
D26|Queen's Gambit Accepted|1.d4 d5 2.c4 dxc4 3.Nf3 Nf6 4.e3 e6
D27|Queen's Gambit Accepted, Classical|1.d4 d5 2.c4 dxc4 3.Nf3 Nf6 4.e3 e6 5.Bxc4 c5 6.O-O a6
D28|Queen's Gambit Accepted, Classical|1.d4 d5 2.c4 dxc4 3.Nf3 Nf6 4.e3 e6 5.Bxc4 c5 6.O-O a6 7.Qe2
D29|Queen's Gambit Accepted, Classical|1.d4 d5 2.c4 dxc4 3.Nf3 Nf6 4.e3 e6 5.Bxc4 c5 6.O-O a6 7.Qe2 b5 8.Bb3 Bb7
D30|Queen's Gambit Declined|1.d4 d5 2.c4 e6
D31|Queen's Gambit Declined|1.d4 d5 2.c4 e6 3.Nc3
D32|Queen's Gambit Declined, Tarrasch|1.d4 d5 2.c4 e6 3.Nc3 c5
D33|Queen's Gambit Declined, Tarrasch|1.d4 d5 2.c4 e6 3.Nc3 c5 4.cxd5 exd5 5.Nf3 Nc6 6.g3
D34|Queen's Gambit Declined, Tarrasch|1.d4 d5 2.c4 e6 3.Nc3 c5 4.cxd5 exd5 5.Nf3 Nc6 6.g3 Nf6 7.Bg2 Be7
D35|Queen's Gambit Declined|1.d4 d5 2.c4 e6 3.Nc3 Nf6
D36|Queen's Gambit Declined, Exchange, Positional line, 6.Qc2|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.cxd5 exd5 5.Bg5 c6 6.Qc2
D37|Queen's Gambit Declined|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3
D38|Queen's Gambit Declined, Ragozin Variation|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 Bb4
D39|Queen's Gambit Declined, Ragozin, Vienna Variation|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 Bb4 5.Bg5 dxc4
D40|Queen's Gambit Declined, Semi-Tarrasch|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c5
D41|Queen's Gambit Declined, Semi-Tarrasch, 5.cxd5|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c5 5.cxd5
D42|Queen's Gambit Declined, Semi-Tarrasch, 7.Bd3|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c5 5.cxd5 Nxd5 6.e3 Nc6 7.Bd3
D43|Queen's Gambit Declined Semi-Slav|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c6
D44|Queen's Gambit Declined Semi-Slav, 5.Bg5 dxc4|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c6 5.Bg5 dxc4
D45|Queen's Gambit Declined Semi-Slav, 5.e3|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c6 5.e3
D46|Queen's Gambit Declined Semi-Slav, 6.Bd3|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c6 5.e3 Nbd7 6.Bd3
D47|Queen's Gambit Declined Semi-Slav, 7.Bc4|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c6 5.e3 Nbd7 6.Bd3 dxc4 7.Bxc4
D48|Queen's Gambit Declined Semi-Slav, Meran|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c6 5.e3 Nbd7 6.Bd3 dxc4 7.Bxc4 b5 8.Bd3 a6
D49|Queen's Gambit Declined Semi-Slav, Meran|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c6 5.e3 Nbd7 6.Bd3 dxc4 7.Bxc4 b5 8.Bd3 a6 9.e4 c5 10.e5 cxd4 11.Nxb5
D50|Queen's Gambit Declined|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5
D51|Queen's Gambit Declined|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Nbd7
D52|Queen's Gambit Declined, Cambridge Springs|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Nbd7 5.e3 c6 6.Nf3 Qa5
D53|Queen's Gambit Declined|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7
D54|Queen's Gambit Declined, Anti-neo-Orthodox Variation|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Rc1
D55|Queen's Gambit Declined|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3
D56|Queen's Gambit Declined, Lasker Defense|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 h6 7.Bh4 Ne4
D57|Queen's Gambit Declined, Lasker Defense, Main line|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 h6 7.Bh4 Ne4 8.Bxe7 Qxe7 9.cxd5 Nxc3 10.bxc3
D58|Queen's Gambit Declined, Tartakower (Makagonov-Bondarevsky) System|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 h6 7.Bh4 b6
D59|Queen's Gambit Declined, Tartakower|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 h6 7.Bh4 b6 8.cxd5 Nxd5
D60|Queen's Gambit Declined, Orthodox Defense|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 Nbd7
D61|Queen's Gambit Declined, Orthodox, Rubinstein Attack|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 Nbd7 7.Qc2
D62|Queen's Gambit Declined, Orthodox, Rubinstein Attack|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 Nbd7 7.Qc2 c5 8.cxd5
D63|Queen's Gambit Declined, Orthodox Defense|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 Nbd7 7.Rc1
D64|Queen's Gambit Declined, Orthodox, Rubinstein Attack|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 Nbd7 7.Rc1 c6 8.Qc2
D65|Queen's Gambit Declined, Orthodox, Rubinstein Attack, Main line|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 Nbd7 7.Rc1 c6 8.Qc2 a6 9.cxd5
D66|Queen's Gambit Declined, Orthodox Defense, Bd3 line|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 Nbd7 7.Rc1 c6 8.Bd3
D67|Queen's Gambit Declined, Orthodox Defense, Bd3 line, Capablanca freeing maneuver|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 Nbd7 7.Rc1 c6 8.Bd3 dxc4 9.Bxc4 Nd5
D68|Queen's Gambit Declined, Orthodox Defense, Classical|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 Nbd7 7.Rc1 c6 8.Bd3 dxc4 9.Bxc4 Nd5 10.Bxe7 Qxe7 11.O-O Nxc3 12.Rxc3 e5
D69|Queen's Gambit Declined, Orthodox Defense, Classical, 13.dxe5|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3 O-O 6.Nf3 Nbd7 7.Rc1 c6 8.Bd3 dxc4 9.Bxc4 Nd5 10.Bxe7 Qxe7 11.O-O Nxc3 12.Rxc3 e5 13.dxe5 Nxe5 14.Nxe5 Qxe5
D70|Neo-Grunfeld Defense|1.d4 Nf6 2.c4 g6 3.g3 d5
D70|Neo-Grunfeld Defense|1.d4 Nf6 2.c4 g6 3.f3 d5
D71|Neo-Grunfeld|1.d4 Nf6 2.c4 g6 3.g3 d5 4.Bg2
D72|Neo-Grunfeld, 5.cxd5|1.d4 Nf6 2.c4 g6 3.g3 d5 4.Bg2 Bg7 5.cxd5 Nxd5 6.e4
D73|Neo-Grunfeld, 5.Nf3|1.d4 Nf6 2.c4 g6 3.g3 d5 4.Bg2 Bg7 5.Nf3
D74|Neo-Grunfeld, 6.cxd5 Nxd5 7.O-O|1.d4 Nf6 2.c4 g6 3.g3 d5 4.Bg2 Bg7 5.Nf3 O-O 6.cxd5 Nxd5 7.O-O
D75|Neo-Grunfeld, 6.cxd5 Nxd5 7.O-O c5 8.Nc3|1.d4 Nf6 2.c4 g6 3.g3 d5 4.Bg2 Bg7 5.Nf3 O-O 6.cxd5 Nxd5 7.O-O c5 8.Nc3
D76|Neo-Grunfeld, 6.cxd5 Nxd5 7.O-O Nb6|1.d4 Nf6 2.c4 g6 3.g3 d5 4.Bg2 Bg7 5.Nf3 O-O 6.cxd5 Nxd5 7.O-O Nb6
D77|Neo-Grunfeld, 6.O-O|1.d4 Nf6 2.c4 g6 3.g3 d5 4.Bg2 Bg7 5.Nf3 O-O 6.O-O
D78|Neo-Grunfeld, 6.O-O c6|1.d4 Nf6 2.c4 g6 3.g3 d5 4.Bg2 Bg7 5.Nf3 O-O 6.O-O c6
D79|Neo-Grunfeld, 6.O-O, Main line|1.d4 Nf6 2.c4 g6 3.g3 d5 4.Bg2 Bg7 5.Nf3 O-O 6.O-O c6 7.cxd5 cxd5
D80|Grunfeld|1.d4 Nf6 2.c4 g6 3.Nc3 d5
D81|Grunfeld, Russian Variation|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Qb3
D82|Grunfeld, 4.Bf4|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Bf4
D83|Grunfeld, Grunfeld Gambit|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Bf4 Bg7 5.e3 O-O
D84|Grunfeld, Grunfeld Gambit Accepted|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Bf4 Bg7 5.e3 O-O 6.cxd5 Nxd5 7.Nxd5 Qxd5 8.Bxc7
D85|Grunfeld|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.cxd5 Nxd5
D86|Grunfeld, Exchange|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.cxd5 Nxd5 5.e4 Nxc3 6.bxc3 Bg7 7.Bc4
D87|Grunfeld, Exchange|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.cxd5 Nxd5 5.e4 Nxc3 6.bxc3 Bg7 7.Bc4 O-O 8.Ne2 c5
D88|Grunfeld, Spassky Variation, Main line, 10...cxd4, 11.cxd4|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.cxd5 Nxd5 5.e4 Nxc3 6.bxc3 Bg7 7.Bc4 O-O 8.Ne2 c5 9.O-O Nc6 10.Be3 cxd4 11.cxd4
D89|Grunfeld, Exchange, Spassky Variation, Main line|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.cxd5 Nxd5 5.e4 Nxc3 6.bxc3 Bg7 7.Bc4 O-O 8.Ne2 c5 9.O-O Nc6 10.Be3 cxd4 11.cxd4 Bg4 12.f3 Na5 13.Bd3 Be6
D90|Grunfeld, Three Knights Variation|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3
D91|Grunfeld, 5.Bg5|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3 Bg7 5.Bg5
D92|Grunfeld, 5.Bf4|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3 Bg7 5.Bf4
D93|Grunfeld, with Bf4 & e3|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3 Bg7 5.Bf4 O-O 6.e3
D94|Grunfeld|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3 Bg7 5.e3
D95|Grunfeld|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3 Bg7 5.e3 O-O 6.Qb3
D96|Grunfeld, Russian Variation|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3 Bg7 5.Qb3
D97|Grunfeld, Russian|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3 Bg7 5.Qb3 dxc4 6.Qxc4 O-O 7.e4
D98|Grunfeld, Russian|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3 Bg7 5.Qb3 dxc4 6.Qxc4 O-O 7.e4 Bg4
D99|Grunfeld Defense, Smyslov|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3 Bg7 5.Qb3 dxc4 6.Qxc4 O-O 7.e4 Bg4 8.Be3 Nfd7
E00|Queen's Pawn Game|1.d4 Nf6 2.c4 e6
E01|Catalan, Closed|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2
E02|Catalan, Open, 5.Qa4|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 dxc4 5.Qa4+
E03|Catalan, Open|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 dxc4 5.Qa4+ Nbd7 6.Qxc4
E04|Catalan, Open, 5.Nf3|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 dxc4 5.Nf3
E05|Catalan, Open, Classical line|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 dxc4 5.Nf3 Be7
E06|Catalan, Closed, 5.Nf3|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 Be7 5.Nf3
E07|Catalan, Closed|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 Be7 5.Nf3 O-O 6.O-O Nbd7
E08|Catalan, Closed|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 Be7 5.Nf3 O-O 6.O-O Nbd7 7.Qc2
E09|Catalan, Closed|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 Be7 5.Nf3 O-O 6.O-O Nbd7 7.Qc2 c6 8.Nbd2
E10|Queen's Pawn Game|1.d4 Nf6 2.c4 e6 3.Nf3
E11|Bogo-Indian Defense|1.d4 Nf6 2.c4 e6 3.Nf3 Bb4+
E12|Queen's Indian|1.d4 Nf6 2.c4 e6 3.Nf3 b6
E13|Queen's Indian, 4.Nc3, Main line|1.d4 Nf6 2.c4 e6 3.Nf3 b6 4.Nc3 Bb7 5.Bg5 h6 6.Bh4 Bb4
E14|Queen's Indian|1.d4 Nf6 2.c4 e6 3.Nf3 b6 4.e3
E15|Queen's Indian|1.d4 Nf6 2.c4 e6 3.Nf3 b6 4.g3
E16|Queen's Indian, Capablanca Variation|1.d4 Nf6 2.c4 e6 3.Nf3 b6 4.g3 Bb7 5.Bg2 Bb4+
E17|Queen's Indian|1.d4 Nf6 2.c4 e6 3.Nf3 b6 4.g3 Bb7 5.Bg2 Be7
E18|Queen's Indian, Old Main line, 7.Nc3|1.d4 Nf6 2.c4 e6 3.Nf3 b6 4.g3 Bb7 5.Bg2 Be7 6.O-O O-O 7.Nc3
E19|Queen's Indian, Old Main line, 9.Qxc3|1.d4 Nf6 2.c4 e6 3.Nf3 b6 4.g3 Bb7 5.Bg2 Be7 6.O-O O-O 7.Nc3 Ne4 8.Qc2 Nxc3 9.Qxc3
E20|Nimzo-Indian|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4
E21|Nimzo-Indian, Three Knights|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Nf3
E22|Nimzo-Indian, Spielmann Variation|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qb3
E23|Nimzo-Indian, Spielmann|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qb3 c5 5.dxc5 Nc6
E24|Nimzo-Indian, Samisch|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.a3 Bxc3+ 5.bxc3
E25|Nimzo-Indian, Samisch|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.a3 Bxc3+ 5.bxc3 c5 6.f3 d5 7.cxd5
E26|Nimzo-Indian, Samisch|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.a3 Bxc3+ 5.bxc3 c5 6.e3
E27|Nimzo-Indian, Samisch Variation|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.a3 Bxc3+ 5.bxc3 O-O
E28|Nimzo-Indian, Samisch Variation|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.a3 Bxc3+ 5.bxc3 O-O 6.e3
E29|Nimzo-Indian, Samisch|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.a3 Bxc3+ 5.bxc3 O-O 6.e3 Nc6 7.Bd3
E30|Nimzo-Indian, Leningrad|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Bg5
E31|Nimzo-Indian, Leningrad, Main line|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Bg5 h6 5.Bh4 c5 6.d5 d6
E32|Nimzo-Indian, Classical|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qc2
E33|Nimzo-Indian, Classical|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qc2 Nc6
E34|Nimzo-Indian, Classical, Noa Variation|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qc2 d5
E35|Nimzo-Indian, Classical, Noa Variation, 5.cxd5 exd5|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qc2 d5 5.cxd5 exd5
E36|Nimzo-Indian, Classical|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qc2 d5 5.a3
E37|Nimzo-Indian, Classical|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qc2 d5 5.a3 Bxc3+ 6.Qxc3 Ne4 7.Qc2
E38|Nimzo-Indian, Classical, 4...c5|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qc2 c5
E39|Nimzo-Indian, Classical, Pirc Variation|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qc2 c5 5.dxc5 O-O
E40|Nimzo-Indian, 4.e3|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3
E41|Nimzo-Indian|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 c5
E42|Nimzo-Indian, 4.e3 c5, 5.Ne2 (Rubinstein)|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 c5 5.Ne2
E43|Nimzo-Indian, Fischer Variation|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 b6
E44|Nimzo-Indian, Fischer Variation, 5.Ne2|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 b6 5.Ne2
E45|Nimzo-Indian, 4.e3, Bronstein (Byrne) Variation|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 b6 5.Ne2 Ba6
E46|Nimzo-Indian|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O
E47|Nimzo-Indian, 4.e3 O-O 5.Bd3|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Bd3
E48|Nimzo-Indian, 4.e3 O-O 5.Bd3 d5|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Bd3 d5
E49|Nimzo-Indian, 4.e3, Botvinnik System|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Bd3 d5 6.a3 Bxc3+ 7.bxc3
E50|Nimzo-Indian, 4.e3 O-O 5.Nf3, without ...d5|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Nf3
E51|Nimzo-Indian, 4.e3|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Nf3 d5
E52|Nimzo-Indian, 4.e3, Main line with ...b6|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Nf3 d5 6.Bd3 b6
E53|Nimzo-Indian, 4.e3|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Nf3 d5 6.Bd3 c5
E54|Nimzo-Indian, 4.e3, Gligoric System with 7...dxc4|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Nf3 d5 6.Bd3 c5 7.O-O dxc4 8.Bxc4
E55|Nimzo-Indian, 4.e3, Gligoric System, Bronstein Variation|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Nf3 d5 6.Bd3 c5 7.O-O dxc4 8.Bxc4 Nbd7
E56|Nimzo-Indian, 4.e3, Main line with 7...Nc6|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Nf3 d5 6.Bd3 c5 7.O-O Nc6
E57|Nimzo-Indian, 4.e3, Main line with 8...dxc4 and 9...cxd4|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Nf3 d5 6.Bd3 c5 7.O-O Nc6 8.a3 dxc4 9.Bxc4 cxd4
E58|Nimzo-Indian, 4.e3, Main line with 8...Bxc3|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Nf3 d5 6.Bd3 c5 7.O-O Nc6 8.a3 Bxc3 9.bxc3
E59|Nimzo-Indian, 4.e3, Main line|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.e3 O-O 5.Nf3 d5 6.Bd3 c5 7.O-O Nc6 8.a3 Bxc3 9.bxc3 dxc4 10.Bxc4
E60|King's Indian Defense|1.d4 Nf6 2.c4 g6
E61|King's Indian|1.d4 Nf6 2.c4 g6 3.Nc3
E62|King's Indian, Fianchetto|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.g3
E63|King's Indian, Fianchetto, Panno Variation|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.g3 O-O 6.Bg2 Nc6 7.O-O a6
E64|King's Indian, Fianchetto, Yugoslav System|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.g3 O-O 6.Bg2 c5
E65|King's Indian, Fianchetto, Yugoslav, 7.O-O|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.g3 O-O 6.Bg2 c5 7.O-O
E66|King's Indian, Fianchetto, Yugoslav Panno|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.g3 O-O 6.Bg2 c5 7.O-O Nc6 8.d5
E67|King's Indian, Fianchetto|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.g3 O-O 6.Bg2 Nbd7
E68|King's Indian, Fianchetto, Classical Variation, 8.e4|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.g3 O-O 6.Bg2 Nbd7 7.O-O e5 8.e4
E69|King's Indian, Fianchetto, Classical Main line|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.g3 O-O 6.Bg2 Nbd7 7.O-O e5 8.e4 c6 9.h3
E70|King's Indian|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4
E71|King's Indian, Makagonov System (5.h3)|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.h3
E72|King's Indian|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.g3
E73|King's Indian|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Be2
E74|King's Indian, Averbakh, 6...c5|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Be2 O-O 6.Bg5 c5
E75|King's Indian, Averbakh, Main line|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Be2 O-O 6.Bg5 c5 7.d5 e6
E76|King's Indian, Four Pawns Attack|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f4
E77|King's Indian, Four Pawns Attack|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f4 O-O 6.Be2
E78|King's Indian, Four Pawns Attack, with Be2 and Nf3|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f4 O-O 6.Be2 c5 7.Nf3
E79|King's Indian, Four Pawns Attack, Main line|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f4 O-O 6.Be2 c5 7.Nf3 cxd4 8.Nxd4 Nc6 9.Be3
E80|King's Indian, Samisch Variation|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f3
E81|King's Indian, Samisch|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f3 O-O
E82|King's Indian, Samisch, double Fianchetto Variation|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f3 O-O 6.Be3 b6
E83|King's Indian, Samisch|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f3 O-O 6.Be3 Nc6
E84|King's Indian, Samisch, Panno Main line|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f3 O-O 6.Be3 Nc6 7.Nge2 a6 8.Qd2 Rb8
E85|King's Indian, Samisch, Orthodox Variation|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f3 O-O 6.Be3 e5
E86|King's Indian, Samisch, Orthodox, 7.Nge2 c6|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f3 O-O 6.Be3 e5 7.Nge2 c6
E87|King's Indian, Samisch, Orthodox|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f3 O-O 6.Be3 e5 7.d5
E88|King's Indian, Samisch, Orthodox, 7.d5 c6|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f3 O-O 6.Be3 e5 7.d5 c6
E89|King's Indian, Samisch, Orthodox Main line|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.f3 O-O 6.Be3 e5 7.d5 c6 8.Nge2 cxd5
E90|King's Indian|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3
E91|King's Indian|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2
E92|King's Indian|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5
E93|King's Indian, Petrosian System, Main line|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.d5 Nbd7
E94|King's Indian, Orthodox|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O
E95|King's Indian, Orthodox, 7...Nbd7, 8.Re1|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Nbd7 8.Re1
E96|King's Indian, Orthodox, 7...Nbd7, Main line|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Nbd7 8.Re1 c6 9.Bf1 a5
E97|King's Indian, Orthodox, Aronin-Taimanov Variation|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Nc6
E98|King's Indian, Orthodox, Aronin-Taimanov, 9.Ne1|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Nc6 8.d5 Ne7 9.Ne1
E99|King's Indian, Orthodox, Aronin-Taimanov, Main line|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Nc6 8.d5 Ne7 9.Ne1 Nd7 10.f3 f5
"""


_TABELA_EXTRA = """
A04|Reti, Dutch Invitation|1.Nf3 f5
A05|Reti, King's Indian Attack|1.Nf3 Nf6 2.g3
A06|Reti, Nimzo-Larsen Attack|1.Nf3 d5 2.b3
A06|Reti, Nimzo-Larsen Attack with ...Nf6|1.Nf3 d5 2.b3 Nf6 3.Bb2
A06|Reti, Tennison Gambit|1.Nf3 d5 2.e4
A07|King's Indian Attack, Yugoslav Variation|1.Nf3 d5 2.g3 Nf6 3.Bg2
A07|King's Indian Attack with ...c6|1.Nf3 d5 2.g3 c6
A07|King's Indian Attack, Keres Variation|1.Nf3 d5 2.g3 Bg4
A08|King's Indian Attack against the Sicilian|1.e4 c5 2.Nf3 e6 3.g3
A08|King's Indian Attack, Sicilian with ...Nc6|1.e4 c5 2.Nf3 Nc6 3.g3
A08|King's Indian Attack, Sicilian with ...d6|1.e4 c5 2.Nf3 d6 3.g3
A08|King's Indian Attack against the French|1.e4 e6 2.d3 d5 3.Nd2 c5 4.Ngf3 Nc6 5.g3
A08|King's Indian Attack, French with ...Nf6|1.e4 e6 2.d3 d5 3.Nd2 Nf6 4.Ngf3 c5 5.g3
A10|English, Anglo-Dutch Defense|1.c4 f5 2.Nf3
A11|English, Caro-Kann Defensive System|1.c4 c6 2.Nf3 d5
A11|English, Caro-Kann Defensive System with 3.e3|1.c4 c6 2.Nf3 d5 3.e3
A11|English, Caro-Kann Defensive System with 3.g3|1.c4 c6 2.Nf3 d5 3.g3
A12|English with b3, Bogoljubow Variation|1.c4 c6 2.Nf3 d5 3.b3 Nf6 4.Bb2
A13|English, Agincourt Defense|1.c4 e6 2.Nf3 d5
A13|English, Agincourt Defense with 3.b3|1.c4 e6 2.Nf3 d5 3.b3
A13|English, Agincourt Defense with 3.e3|1.c4 e6 2.Nf3 d5 3.e3
A13|English, Neo-Catalan|1.c4 e6 2.Nf3 d5 3.g3
A13|English, Neo-Catalan with Bg2|1.c4 e6 2.Nf3 d5 3.g3 Nf6 4.Bg2
A14|English, Neo-Catalan Declined, Nimzo-Larsen|1.c4 e6 2.Nf3 Nf6 3.b3 d5 4.Bb2
A16|English, Anglo-Indian Defense|1.c4 Nf6 2.Nf3
A20|English Opening, King's English with e3|1.c4 e5 2.e3
A22|English, King's English, Two Knights with e3|1.c4 e5 2.Nc3 Nf6 3.e3
A25|English, Closed System with e3|1.c4 e5 2.Nc3 Nc6 3.e3
A25|English, Closed System with Nf3 and e3|1.c4 e5 2.Nc3 Nc6 3.Nf3 e4 4.Ng5
A26|English, Botvinnik System|1.c4 e5 2.Nc3 Nc6 3.g3 g6 4.Bg2 Bg7 5.e3
A28|English, Four Knights, Nimzowitsch|1.c4 e5 2.Nc3 Nc6 3.Nf3 Nf6 4.e3
A29|English, Four Knights, Kingside Fianchetto with ...Bb4|1.c4 e5 2.Nc3 Nc6 3.Nf3 Nf6 4.g3 Bb4
A30|English, Symmetrical, Hedgehog|1.c4 c5 2.Nf3 Nf6 3.g3 b6
A33|English, Symmetrical, Geller Variation|1.c4 c5 2.Nf3 Nf6 3.d4 cxd4 4.Nxd4 e6 5.Nc3 Nc6 6.g3
A34|English, Symmetrical, Rubinstein System|1.c4 c5 2.Nc3 Nf6 3.g3 d5 4.cxd5 Nxd5
A34|English, Symmetrical, Three Knights with ...d5|1.c4 c5 2.Nc3 Nf6 3.Nf3 d5 4.cxd5 Nxd5
A35|English, Symmetrical, Four Knights|1.c4 c5 2.Nc3 Nc6 3.Nf3 Nf6
A40|Queen's Pawn, Modern Defense|1.d4 g6
A41|Wade Defense|1.d4 d6 2.Nf3 Bg4
A45|Trompowsky Attack, 2...e6|1.d4 Nf6 2.Bg5 e6
A45|Queen's Pawn, Torre Attack|1.d4 Nf6 2.Nf3 e6 3.Bg5
A46|Queen's Pawn, Torre Attack with 3.Bg5|1.d4 Nf6 2.Nf3 e6 3.Bf4
A46|Queen's Pawn, London System|1.d4 Nf6 2.Nf3 e6 3.e3
A48|King's Indian, London System|1.d4 Nf6 2.Nf3 g6 3.Bf4
A48|King's Indian, Torre Attack|1.d4 Nf6 2.Nf3 g6 3.Bg5
A48|King's Indian, Barry Attack|1.d4 Nf6 2.Nf3 g6 3.Nc3 d5 4.Bf4
A53|Old Indian Defense, 3.Nf3|1.d4 Nf6 2.c4 d6 3.Nf3
A56|Benoni Defense, Czech Benoni|1.d4 Nf6 2.c4 c5 3.d5 e5
A57|Benko Gambit, Declined|1.d4 Nf6 2.c4 c5 3.d5 b5 4.Nf3
A60|Benoni Defense, Modern with 4.Nc3|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5
A70|Benoni, Classical with 7.Nf3 and ...Bg7|1.d4 Nf6 2.c4 c5 3.d5 e6 4.Nc3 exd5 5.cxd5 d6 6.e4 g6 7.Nf3 Bg7
A80|Dutch Defense, 2.Nf3|1.d4 f5 2.Nf3
A80|Dutch Defense, Hopton Attack|1.d4 f5 2.Bg5
A81|Dutch Defense, Leningrad without c4|1.d4 f5 2.g3 Nf6 3.Bg2 g6
A84|Dutch Defense, 3.Nc3|1.d4 f5 2.c4 e6 3.Nc3
A85|Dutch, with c4 and Nc3, ...Bb4|1.d4 f5 2.c4 Nf6 3.Nc3 e6 4.Nf3
A87|Dutch, Leningrad, Main Variation with Nc3|1.d4 f5 2.c4 Nf6 3.g3 g6 4.Bg2 Bg7 5.Nc3
A90|Dutch Defense, Stonewall with Nf3|1.d4 f5 2.c4 Nf6 3.g3 e6 4.Bg2 d5 5.Nf3
A06|Reti, Nimzo-Larsen Attack with ...e6|1.Nf3 d5 2.b3 Nf6 3.Bb2 e6
A87|Dutch, Leningrad, Main Variation with 5.Nc3|1.d4 f5 2.c4 Nf6 3.g3 g6 4.Bg2 Bg7 5.Nc3 d6 6.Nf3
B01|Scandinavian, Modern Variation|1.e4 d5 2.exd5 Nf6
B01|Scandinavian, Mieses-Kotroc|1.e4 d5 2.exd5 Qxd5 3.Nc3
B06|Modern Defense with 2.d4 Bg7|1.e4 g6 2.d4 Bg7
B06|Modern Defense, Three Pawns Attack|1.e4 g6 2.d4 Bg7 3.f4
B06|Modern Defense, Standard Line|1.e4 g6 2.d4 Bg7 3.Nc3 d6
B06|Modern Defense, 3.Nf3|1.e4 g6 2.d4 Bg7 3.Nf3 d6
B06|Modern Defense, Three Pawns Attack with Nf3|1.e4 g6 2.d4 Bg7 3.f4 d6 4.Nf3
B07|Pirc Defense, 150 Attack|1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Be3
B07|Pirc Defense, 150 Attack with Qd2|1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Be3 Bg7 5.Qd2
B07|Pirc Defense, Byrne Variation|1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Bg5
B08|Pirc, Classical with ...Bg7|1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Nf3 Bg7
B08|Pirc, Classical, 5.Be2|1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Nf3 Bg7 5.Be2
B08|Pirc, Classical, 5.Be3|1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Nf3 Bg7 5.Be3
B08|Pirc, Classical, 5.h3|1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Nf3 Bg7 5.h3
B12|Caro-Kann, Advance Variation|1.e4 c6 2.d4 d5 3.e5
B12|Caro-Kann, Advance, Short Variation|1.e4 c6 2.d4 d5 3.e5 Bf5 4.Nf3
B14|Caro-Kann, Panov Attack with 5.Nf3|1.e4 c6 2.d4 d5 3.exd5 cxd5 4.c4 Nf6 5.Nf3
B14|Caro-Kann, Panov Attack, Gruenfeld Defense|1.e4 c6 2.d4 d5 3.exd5 cxd5 4.c4 Nf6 5.Nc3 g6
B21|Sicilian, Grand Prix Attack with 2.f4|1.e4 c5 2.f4 Nc6 3.Nf3
B21|Sicilian, McDonnell Attack with ...d5|1.e4 c5 2.f4 d5
B21|Sicilian, McDonnell Attack with ...g6|1.e4 c5 2.f4 g6
B21|Sicilian, Smith-Morra Gambit Accepted|1.e4 c5 2.d4 cxd4 3.c3 dxc3 4.Nxc3
B22|Sicilian, Alapin with 2...e6|1.e4 c5 2.Nf3 e6 3.c3
B22|Sicilian, Alapin with 2...Nc6|1.e4 c5 2.Nf3 Nc6 3.c3
B22|Sicilian, Alapin, 2...e6 3.c3 d5|1.e4 c5 2.Nf3 e6 3.c3 d5 4.exd5 Qxd5 5.d4
B22|Sicilian, Alapin, 2...d5|1.e4 c5 2.c3 d5 3.exd5 Qxd5 4.d4
B22|Sicilian, Alapin, 2...Nf6|1.e4 c5 2.c3 Nf6 3.e5 Nd5 4.d4
B23|Sicilian, Closed, Grand Prix Attack|1.e4 c5 2.Nc3 Nc6 3.f4
B23|Sicilian, Grand Prix Attack, Nf3 and Nc3|1.e4 c5 2.f4 Nc6 3.Nf3 g6 4.Nc3
B23|Sicilian, Closed, 2...e6|1.e4 c5 2.Nc3 e6
B23|Sicilian, Closed, 2...d6|1.e4 c5 2.Nc3 d6
B24|Sicilian, Closed, Fianchetto with Nf3|1.e4 c5 2.Nc3 Nc6 3.g3 g6 4.Bg2 Bg7 5.Nf3
B27|Sicilian, Hyperaccelerated Dragon|1.e4 c5 2.Nf3 g6
B29|Sicilian, Nimzowitsch-Rubinstein|1.e4 c5 2.Nf3 Nf6 3.e5 Nd5 4.Nc3
B30|Sicilian, Old Sicilian with 3.Nc3|1.e4 c5 2.Nf3 Nc6 3.Nc3
B30|Sicilian, Rossolimo Variation|1.e4 c5 2.Nf3 Nc6 3.Bb5
B30|Sicilian, Rossolimo, 3...e6|1.e4 c5 2.Nf3 Nc6 3.Bb5 e6
B30|Sicilian, Closed with Nf3 and ...g6|1.e4 c5 2.Nf3 Nc6 3.Nc3 g6
B30|Sicilian, Closed with Nf3 and ...e6|1.e4 c5 2.Nf3 Nc6 3.Nc3 e6
B31|Sicilian, Rossolimo, Fianchetto with 4.O-O|1.e4 c5 2.Nf3 Nc6 3.Bb5 g6 4.O-O
B32|Sicilian, Loewenthal Variation|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 e5 5.Nb5
B32|Sicilian, Kalashnikov Variation|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 e5 5.Nb5 d6
B33|Sicilian, Sveshnikov with 5...e6|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e6 6.Ndb5
B33|Sicilian, Sveshnikov, Chelyabinsk|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 e5 6.Ndb5 d6
B34|Sicilian, Accelerated Dragon, 5.Nc3|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 g6 5.Nc3
B34|Sicilian, Accelerated Dragon, 5.Nc3 Bg7|1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 g6 5.Nc3 Bg7
B40|Sicilian, French Variation with 3.d4|1.e4 c5 2.Nf3 e6 3.d4
B40|Sicilian, Pin Variation|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Bb4
B44|Sicilian, Taimanov with 5.Nb5|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 Nc6 5.Nb5
B45|Sicilian, Taimanov, Four Knights|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 Nc6 5.Nc3 Nf6
B47|Sicilian, Taimanov with 5...a6|1.e4 c5 2.Nf3 e6 3.d4 cxd4 4.Nxd4 Nc6 5.Nc3 a6 6.Be2 Qc7
B50|Sicilian, 2...d6 with 3.c3|1.e4 c5 2.Nf3 d6 3.c3 Nf6 4.h3
B51|Sicilian, Moscow Variation with 3...Nc6|1.e4 c5 2.Nf3 d6 3.Bb5+ Nc6
B52|Sicilian, Moscow, 4.Bxd7+|1.e4 c5 2.Nf3 d6 3.Bb5+ Bd7 4.Bxd7+
B54|Sicilian, Prins Variation|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.f3
B56|Sicilian, Classical with 5...Nc6|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 Nc6
B70|Sicilian, Dragon with 6.g3|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 g6 6.g3
B90|Sicilian, Najdorf, English Attack|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Be3
B90|Sicilian, Najdorf, 6.h3|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.h3
B90|Sicilian, Najdorf, 6.Bc4|1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Bc4
C00|French Defense, King's Indian Attack|1.e4 e6 2.d3
C00|French Defense, Two Knights|1.e4 e6 2.Nf3 d5 3.Nc3
C00|French Defense, Advance without d4|1.e4 e6 2.d3 d5 3.Nd2
C01|French Defense, Exchange Variation|1.e4 e6 2.d4 d5 3.exd5 exd5
C01|French, Exchange with 3.Nc3 Nf6|1.e4 e6 2.d4 d5 3.Nc3 Nf6 4.exd5 exd5
C01|French, Exchange with 3.Nc3 Bb4|1.e4 e6 2.d4 d5 3.Nc3 Bb4 4.exd5 exd5
C02|French, Advance, Milner-Barry|1.e4 e6 2.d4 d5 3.e5 c5 4.c3 Nc6 5.Nf3
C02|French, Advance, Euwe Variation|1.e4 e6 2.d4 d5 3.e5 c5 4.c3 Nc6 5.Nf3 Bd7
C10|French, Rubinstein Variation|1.e4 e6 2.d4 d5 3.Nc3 dxe4 4.Nxe4
C11|French, Classical with 4.e5|1.e4 e6 2.d4 d5 3.Nc3 Nf6 4.e5
C11|French, Steinitz Variation|1.e4 e6 2.d4 d5 3.Nc3 Nf6 4.e5 Nfd7 5.f4
C25|Vienna Game, 2...Nc6|1.e4 e5 2.Nc3 Nc6
C26|Vienna Game, Falkbeer with 3.g3|1.e4 e5 2.Nc3 Nf6 3.g3
C41|Philidor Defense, 3.d4|1.e4 e5 2.Nf3 d6 3.d4
C41|Philidor Defense, Exchange|1.e4 e5 2.Nf3 d6 3.d4 exd4 4.Nxd4
C41|Philidor Defense, Nimzowitsch|1.e4 e5 2.Nf3 d6 3.d4 Nf6 4.Nc3
C41|Philidor Defense, Hanham Variation|1.e4 e5 2.Nf3 d6 3.d4 Nf6 4.Nc3 Nbd7
C42|Petrov, Classical Attack|1.e4 e5 2.Nf3 Nf6 3.Nxe5 d6 4.Nf3 Nxe4 5.d4
C44|Scotch Game, Ponziani Opening|1.e4 e5 2.Nf3 Nc6 3.c3
C44|Scotch Gambit|1.e4 e5 2.Nf3 Nc6 3.d4 exd4 4.Bc4
C44|Scotch Game, Goering Gambit|1.e4 e5 2.Nf3 Nc6 3.d4 exd4 4.c3
C45|Scotch, Mieses Variation|1.e4 e5 2.Nf3 Nc6 3.d4 exd4 4.Nxd4 Nf6 5.Nxc6
C46|Four Knights, Italian Variation|1.e4 e5 2.Nf3 Nc6 3.Nc3 Bc5
C47|Four Knights, Scotch Variation|1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.d4
C50|Italian Game, Giuoco Piano|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5
C50|Italian Game, Giuoco Pianissimo|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.d3
C50|Italian Game, Four Knights|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.Nc3
C50|Italian Game, Hungarian Defense|1.e4 e5 2.Nf3 Nc6 3.Bc4 Be7
C50|Italian Game, Blackburne Shilling Gambit|1.e4 e5 2.Nf3 Nc6 3.Bc4 Nd4
C50|Italian Game, Rousseau Gambit|1.e4 e5 2.Nf3 Nc6 3.Bc4 f5
C50|Italian Game, Giuoco Pianissimo with 4.O-O|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.O-O
C53|Giuoco Piano, Close Variation|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Qe7
C54|Giuoco Piano, Main Line|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6
C54|Giuoco Pianissimo, Modern Main Line|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6 5.d3
C54|Giuoco Piano, Evans Gambit Declined transposition|1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6 5.b4
C55|Two Knights Defense, Modern Bishop's Opening|1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.d3
C55|Two Knights Defense, Giuoco Piano transposition|1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.O-O
C55|Two Knights Defense, Max Lange Attack|1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.d4 exd4 5.O-O Bc5
C60|Ruy Lopez, Cozio Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 Nge7
C60|Ruy Lopez, Bird Defense transposition|1.e4 e5 2.Nf3 Nc6 3.Bb5 g6
C65|Ruy Lopez, Berlin Defense, 4.d3|1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6 4.d3
C65|Ruy Lopez, Berlin Defense, 4.O-O Bc5|1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6 4.O-O Bc5
C67|Ruy Lopez, Berlin Defense, Open Variation|1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6 4.O-O Nxe4 5.d4
C67|Ruy Lopez, Berlin Defense, Rio de Janeiro|1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6 4.O-O Nxe4 5.d4 Nd6 6.Bxc6 dxc6 7.dxe5 Nf5 8.Qxd8+ Kxd8
C68|Ruy Lopez, Exchange Variation, 5.O-O|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Bxc6 dxc6 5.O-O
C68|Ruy Lopez, Exchange Variation, 5.Nc3|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Bxc6 dxc6 5.Nc3
C77|Ruy Lopez, Anderssen Variation|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.d3
C77|Ruy Lopez, Morphy Defense, Wormald Attack|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.Qe2
C78|Ruy Lopez, Moeller Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Bc5
C78|Ruy Lopez, Archangel Defense|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O b5 6.Bb3 Bb7
C84|Ruy Lopez, Closed Defense with 6.d3|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.d3
C88|Ruy Lopez, Closed, Anti-Marshall|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 O-O 8.a4
C99|Ruy Lopez, Chigorin, 12...c5 13.d4 Qc7 14.Nbd2 cxd4|1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3 Na5 10.Bc2 c5 11.d4 Qc7 12.Nbd2 cxd4 13.cxd4
D00|Queen's Pawn Game, Levitsky Attack|1.d4 d5 2.Bg5
D00|Queen's Pawn Game, Blackmar-Diemer|1.d4 d5 2.e4
D00|Queen's Pawn Game, Colle transposition|1.d4 d5 2.e3
D02|Queen's Pawn Game, London System|1.d4 d5 2.Nf3 Nf6 3.Bf4
D02|Queen's Pawn Game, Symmetrical with ...g6|1.d4 Nf6 2.Nf3 g6 3.g3 Bg7 4.Bg2 d5
D04|Colle System|1.d4 d5 2.Nf3 Nf6 3.e3 e6 4.Bd3
D06|Queen's Gambit, Marshall Defense|1.d4 d5 2.c4 Nf6
D06|Queen's Gambit, Marshall Defense with 3.Nf3|1.d4 d5 2.c4 Nf6 3.Nf3
D06|Queen's Gambit, Marshall Defense with 3.cxd5|1.d4 d5 2.c4 Nf6 3.cxd5 Nxd5
D10|Slav Defense, Exchange with 3.cxd5|1.d4 d5 2.c4 c6 3.cxd5 cxd5
D11|Slav Defense, 3.Nf3 Nf6|1.d4 d5 2.c4 c6 3.Nf3 Nf6
D11|Slav Defense, Breyer Variation|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.e3
D11|Slav Defense, Modern with 4.g3|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.g3
D11|Slav Defense, 4.Qc2|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.Qc2
D15|Slav Defense, Chameleon with 4...a6|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.Nc3 a6
D15|Slav Defense, Schlechter with 4...g6|1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.Nc3 g6
D20|Queen's Gambit Accepted, 3.e4|1.d4 d5 2.c4 dxc4 3.e4
D20|Queen's Gambit Accepted, 3.e3|1.d4 d5 2.c4 dxc4 3.e3
D30|Queen's Gambit Declined, 3.Nf3|1.d4 d5 2.c4 e6 3.Nf3
D30|Queen's Gambit Declined, 3.Nf3 Nf6|1.d4 d5 2.c4 e6 3.Nf3 Nf6
D30|Queen's Gambit Declined, 4.Bg5|1.d4 d5 2.c4 e6 3.Nf3 Nf6 4.Bg5
D30|Queen's Gambit Declined, 4.e3|1.d4 d5 2.c4 e6 3.Nf3 Nf6 4.e3
D30|Queen's Gambit Declined, 4.Bf4|1.d4 d5 2.c4 e6 3.Nf3 Nf6 4.Bf4
D30|Semi-Slav, 3.Nf3 c6|1.d4 d5 2.c4 e6 3.Nf3 c6
D31|Queen's Gambit Declined, Semi-Slav with 3.Nc3|1.d4 d5 2.c4 e6 3.Nc3 c6
D31|Queen's Gambit Declined, Alatortsev Variation|1.d4 d5 2.c4 e6 3.Nc3 Be7
D31|Queen's Gambit Declined, Ragozin transposition|1.d4 d5 2.c4 e6 3.Nc3 Bb4
D31|Semi-Slav, Noteboom Variation|1.d4 d5 2.c4 e6 3.Nc3 c6 4.Nf3 dxc4
D35|Queen's Gambit Declined, Exchange Variation|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.cxd5 exd5
D35|Queen's Gambit Declined, Exchange with 5.Bg5|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.cxd5 exd5 5.Bg5
D36|Queen's Gambit Declined, Exchange, positional line|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.cxd5 exd5 5.Bg5 c6 6.e3
D36|Queen's Gambit Declined, Exchange with 6.Qc2|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.cxd5 exd5 5.Bg5 Be7 6.Qc2
D37|Queen's Gambit Declined, 5.Bf4|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 Be7 5.Bf4
D37|Queen's Gambit Declined, 5.e3|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 Be7 5.e3
D43|Semi-Slav Defense, Anti-Moscow|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c6 5.Bg5 h6 6.Bh4
D45|Semi-Slav Defense, Stoltz Variation|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c6 5.e3 Nbd7 6.Qc2
D46|Semi-Slav Defense, Main Line with ...Bd6|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 c6 5.e3 Bd6 6.Bd3
D50|Queen's Gambit Declined, 4.Bg5 c6|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 c6
D53|Queen's Gambit Declined, 4.Bg5 Be7 5.Nf3|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.Nf3
D53|Queen's Gambit Declined, 4.Bg5 Be7 5.e3|1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Bg5 Be7 5.e3
D70|Neo-Gruenfeld Defense with 3.Nf3|1.d4 Nf6 2.c4 g6 3.Nf3 d5 4.g3
D85|Gruenfeld, Exchange Variation with Nf3|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.cxd5 Nxd5 5.e4 Nxc3 6.bxc3 Bg7 7.Nf3
D94|Gruenfeld, Smyslov Defense|1.d4 Nf6 2.c4 g6 3.Nc3 d5 4.Nf3 Bg7 5.e3 O-O
E00|Catalan Opening, Closed|1.d4 Nf6 2.c4 e6 3.g3
E01|Catalan Opening, Closed with ...Be7|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 Be7
E05|Catalan, Open, Classical Line|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 Be7 5.Nf3 O-O 6.O-O dxc4
E05|Catalan, Open, Classical with 7.Qc2|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 Be7 5.Nf3 O-O 6.O-O dxc4 7.Qc2
E05|Catalan, Open, Classical with 7.Ne5|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 Be7 5.Nf3 O-O 6.O-O dxc4 7.Ne5
E06|Catalan, Closed, 5.Nf3 O-O 6.O-O|1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 Be7 5.Nf3 O-O 6.O-O
E10|Queen's Pawn Game, Blumenfeld Gambit|1.d4 Nf6 2.c4 e6 3.Nf3 c5 4.d5 b5
E11|Bogo-Indian Defense, 4.Bd2|1.d4 Nf6 2.c4 e6 3.Nf3 Bb4+ 4.Bd2
E11|Bogo-Indian Defense, 4.Nbd2|1.d4 Nf6 2.c4 e6 3.Nf3 Bb4+ 4.Nbd2
E12|Queen's Indian, 4.a3|1.d4 Nf6 2.c4 e6 3.Nf3 b6 4.a3
E12|Queen's Indian, 4.Nc3 Bb7|1.d4 Nf6 2.c4 e6 3.Nf3 b6 4.Nc3 Bb7
E15|Queen's Indian, Nimzowitsch Variation|1.d4 Nf6 2.c4 e6 3.Nf3 b6 4.g3 Ba6
E20|Nimzo-Indian Defense, Kmoch Variation|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.f3
E32|Nimzo-Indian, Classical, 4...O-O|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qc2 O-O
E32|Nimzo-Indian, Classical, 4...b6|1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 4.Qc2 b6
E60|King's Indian Defense, 3.Nf3|1.d4 Nf6 2.c4 g6 3.Nf3
E60|King's Indian Defense, 3.Nf3 Bg7|1.d4 Nf6 2.c4 g6 3.Nf3 Bg7
E60|King's Indian Defense, Fianchetto without Nc3|1.d4 Nf6 2.c4 g6 3.g3
E61|King's Indian Defense, 3.Nc3 Bg7|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7
E61|King's Indian Defense, Three Knights|1.d4 Nf6 2.c4 g6 3.Nf3 Bg7 4.Nc3
E61|King's Indian Defense, 4...d6|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6
E61|King's Indian Defense, Smyslov System|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.Bg5
E61|King's Indian Defense, 5.e3|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.e3
E61|King's Indian Defense, 5.Bf4|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.Nf3 d6 5.Bf4
E61|King's Indian Defense, Fianchetto with Nc3|1.d4 Nf6 2.c4 g6 3.g3 Bg7 4.Nc3
E62|King's Indian, Fianchetto Variation, 5.Bg2|1.d4 Nf6 2.c4 g6 3.Nf3 Bg7 4.g3 d6 5.Bg2
E62|King's Indian, Fianchetto, 6.O-O|1.d4 Nf6 2.c4 g6 3.Nf3 Bg7 4.g3 O-O 5.Bg2 d6 6.O-O
E62|King's Indian, Fianchetto with ...c6|1.d4 Nf6 2.c4 g6 3.Nf3 Bg7 4.g3 O-O 5.Bg2 d6 6.O-O c6 7.Nc3
E62|King's Indian, Fianchetto with ...Nc6|1.d4 Nf6 2.c4 g6 3.Nf3 Bg7 4.g3 O-O 5.Bg2 d6 6.O-O Nc6 7.Nc3
E70|King's Indian Defense, 4.e4 d6|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6
E73|King's Indian, Averbakh System|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Be2 O-O 6.Bg5
E76|King's Indian, Four Pawns Attack, Benoni transposition|1.d4 Nf6 2.c4 c5 3.d5 g6 4.Nc3 Bg7 5.e4 d6 6.f4
E90|King's Indian, Makogonov Variation|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.h3
E90|King's Indian, Benoni transposition with h3|1.d4 Nf6 2.c4 c5 3.d5 g6 4.Nc3 Bg7 5.e4 d6 6.h3
E91|King's Indian, Benoni transposition with Be2|1.d4 Nf6 2.c4 c5 3.d5 g6 4.Nc3 Bg7 5.e4 d6 6.Nf3 O-O 7.Be2
E92|King's Indian, Petrosian System|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.d5
E94|King's Indian, Orthodox, 7...Nbd7|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Nbd7
E94|King's Indian, Orthodox, 7...exd4|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O exd4
E94|King's Indian, Orthodox, 7...c6|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O c6
E94|King's Indian, Orthodox, 7...Na6|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Na6
E97|King's Indian, Mar del Plata|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Nc6 8.d5 Ne7
E99|King's Indian, Orthodox, Classical, 10.Nd3|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Nc6 8.d5 Ne7 9.Ne1 Nd7 10.Nd3 f5
B30|Sicilian, Four Knights Variation|1.e4 c5 2.Nf3 Nc6 3.Nc3 Nf6
A34|English, Symmetrical, Rubinstein with 2.g3|1.c4 c5 2.g3 Nf6 3.Bg2 d5 4.cxd5 Nxd5
C18|French, Winawer, Advance, Poisoned Pawn|1.e4 e6 2.d4 d5 3.Nc3 Bb4 4.e5 c5 5.a3 Bxc3+ 6.bxc3 Ne7 7.Qg4
C18|French, Winawer, Advance, 7.Nf3|1.e4 e6 2.d4 d5 3.Nc3 Bb4 4.e5 c5 5.a3 Bxc3+ 6.bxc3 Ne7 7.Nf3
C18|French, Winawer, Advance, 7.h4|1.e4 e6 2.d4 d5 3.Nc3 Bb4 4.e5 c5 5.a3 Bxc3+ 6.bxc3 Ne7 7.h4
C18|French, Winawer, Advance, 7.a4|1.e4 e6 2.d4 d5 3.Nc3 Bb4 4.e5 c5 5.a3 Bxc3+ 6.bxc3 Ne7 7.a4
A68|Benoni, Four Pawns Attack, King's Indian move order|1.d4 Nf6 2.c4 c5 3.d5 g6 4.Nc3 Bg7 5.e4 d6 6.f4 O-O 7.Nf3 e6
E99|King's Indian, Orthodox, Classical, 10.Be3|1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Nc6 8.d5 Ne7 9.Ne1 Nd7 10.Be3 f5
"""
"""As linhas que a segunda rodada da S-534 acrescentou, e cada uma nasceu de uma medição.

**Por que uma segunda tabela e não linhas costuradas na primeira.** A de cima é a classificação
padrão escrita por código -- uma linha canônica por código, na ordem A00…E99 --, e ela continua
sendo isso. Esta é outra coisa: o **erro medido**. Cada linha aqui responde a uma confusão contada
contra o header `[ECO]` de 20.000 partidas da gigabase (`scratchpad/eco_medir.py`), e a diferença
entre as duas listas é a diferença entre *o que a classificação é* e *onde ela falhava*.

**As três formas de falha que estas linhas consertam**, e nenhuma delas era "a tabela está errada":

1. **A porta de transposição que faltava.** `1.Nf3 d5 2.c4 e6` chega à mesma posição de
   `1.c4 e6 2.Nf3 d5`, e a tabela só tinha `A13 = 1.c4 e6` -- dois meios-lances, cedo demais para
   a partida ainda estar nela. Eram 149 erros de A13 em 178 partidas.
2. **O ponto de bifurcação sem linha.** `C54` era só a linha principal com 11 meios-lances; a
   partida que jogasse `4...Nf6 5.d3` caía para `C53` porque não havia nada entre os dois. 102
   erros em 103 partidas.
3. **A abertura que a tabela alcançava por um caminho só.** `B33` existia como a Sveshnikov de
   16 meios-lances; a mesma abertura por `5...e6 6.Ndb5` não tinha linha, e 95 partidas de 398
   caíam em `B30`.

**Os nomes daqui são o da linha, e não o da família** -- é o dado que `frase_da_abertura` mostra
sob o tabuleiro. `Ruy Lopez` é o nome de nove códigos e não distingue nenhum; *Berlin Defense,
Open Variation* distingue o C67 de todos eles.
"""


def _lances_de(texto: str) -> tuple[str, ...]:
    """`1.e4 c5 2.Nf3` -> `("e4", "c5", "Nf3")`. Os números vão embora; os lances ficam."""
    lances = []
    for token in texto.split():
        lance = _RE_NUMERO.sub("", token)
        if lance:
            lances.append(lance)
    return tuple(lances)


@lru_cache(maxsize=1)
def tabela() -> tuple[Abertura, ...]:
    """As linhas da tabela, na ordem em que estão escritas. Lida uma vez.

    As de `_TABELA_EXTRA` vêm depois, e a ordem importa em dois lugares: `_nomes` fica com o nome
    da **primeira** linha de cada código (a legenda da família, que é a da tabela padrão), e
    `_por_posicao`/`_arvore` desempatam pela primeira escrita quando duas linhas chegam à mesma
    posição pelo mesmo número de lances.
    """
    aberturas = []
    for texto in (_TABELA, _TABELA_EXTRA):
        for linha in texto.strip().splitlines():
            codigo, nome_, lances = linha.split("|")
            aberturas.append(Abertura(codigo, nome_, _lances_de(lances)))
    return tuple(aberturas)


@lru_cache(maxsize=1)
def _nomes() -> dict[str, str]:
    """`código -> nome`: o da **primeira** linha do código, que é a canônica."""
    nomes: dict[str, str] = {}
    for abertura in tabela():
        nomes.setdefault(abertura.codigo, abertura.nome)
    return nomes


def _chave(tabuleiro: chess.Board) -> str:
    """A FEN sem os dois contadores: a posição, e não o momento em que se chegou a ela."""
    return " ".join(tabuleiro.fen().split()[:4])


@lru_cache(maxsize=1)
def _por_posicao() -> dict[str, Abertura]:
    """`FEN sem contadores -> abertura`, reproduzindo cada linha uma vez. É o que dá a transposição.

    Quando duas linhas chegam à mesma posição -- acontece nas variantes de um mesmo código, e
    entre códigos vizinhos --, fica a **mais profunda**, e em empate a primeira escrita.
    """
    posicoes: dict[str, Abertura] = {}
    for abertura in tabela():
        tabuleiro = chess.Board()
        for lance in abertura.lances:
            tabuleiro.push_san(lance)
        chave = _chave(tabuleiro)
        anterior = posicoes.get(chave)
        if anterior is None or abertura.profundidade > anterior.profundidade:
            posicoes[chave] = abertura
    return posicoes


@lru_cache(maxsize=1)
def _arvore() -> dict[str, Any]:
    """A árvore de prefixos dos lances: `{lance: {..., "": Abertura}}`. Sem tabuleiro nenhum."""
    raiz: dict[str, Any] = {}
    for abertura in tabela():
        no = raiz
        for lance in abertura.lances:
            no = no.setdefault(lance, {})
        # Em empate de posicao fica a primeira escrita, como em `_por_posicao`.
        no.setdefault("", abertura)
    return raiz


def _a_ultima(candidatas: Iterable[Abertura]) -> Abertura | None:
    """A **última** casada, e não a de linha mais longa: ver `classificar`."""
    melhor: Abertura | None = None
    for abertura in candidatas:
        melhor = abertura
    return melhor


def classificar(tabuleiro_ou_lances: chess.Board | Iterable[str]) -> Abertura | None:
    """O código ECO da **posição final** que a tabela ainda conhece. `None` se nenhuma conhece.

    Aceita um `chess.Board` -- é a pilha de lances dele que é percorrida, então um tabuleiro
    montado de uma FEN e sem lances é conferido só na posição em que está -- ou uma sequência de
    SAN a partir da posição inicial. Um lance ilegal encerra a leitura no que já se viu, em vez
    de derrubar quem perguntou: a base tem partidas que o `python-chess` recusa (S-85).

    **A partida é classificada pela posição mais tardia que a tabela conhece, andando para trás
    a partir da última** -- e não pela linha mais longa da tabela entre as que ela tocou. A
    diferença é a transposição, e a primeira rodada da S-534 a prometeu sem entregá-la:
    `1.Nf3 d5 2.d4 Nf6 3.c4` e `1.d4 d5 2.c4 Nf6 3.Nf3` chegam à **mesma posição** -- mesmas
    peças, mesma vez, mesmos roques -- e davam D02 e D06. Não porque a posição final não casasse:
    porque cada caminho tinha passado por uma linha intermediária diferente, e era a linha mais
    longa entre as **intermediárias** que vencia. Pela posição final os dois dão o mesmo código,
    que é o que "a transposição vale" quer dizer -- e é também a regra da classificação padrão:
    o código de uma partida é o da última posição dela que está no livro de aberturas.

    **O alcance disto é o da tabela, e não mais que ele.** Dois caminhos que chegam a uma posição
    que a tabela **não** conhece continuam andando para trás cada um pelo seu, e podem parar em
    pontos diferentes: foi o que aconteceu com `1.Nf3 d5 2.d4 Nf6 3.c4`, cuja posição final não
    tinha linha nenhuma. A resposta ali não é uma regra melhor -- é a linha que faltava.
    """
    posicoes = _por_posicao()
    achadas: list[Abertura] = []
    if isinstance(tabuleiro_ou_lances, chess.Board):
        atual = tabuleiro_ou_lances.root()
        lances = list(tabuleiro_ou_lances.move_stack)[:LANCES_EXAMINADOS]
        abertura = posicoes.get(_chave(atual))
        if abertura is not None:
            achadas.append(abertura)
        for lance in lances:
            atual.push(lance)
            abertura = posicoes.get(_chave(atual))
            if abertura is not None:
                achadas.append(abertura)
        return _a_ultima(achadas)

    atual = chess.Board()
    for indice, san in enumerate(tabuleiro_ou_lances):
        if indice >= LANCES_EXAMINADOS:
            break
        try:
            atual.push_san(san)
        except ValueError:
            break
        abertura = posicoes.get(_chave(atual))
        if abertura is not None:
            achadas.append(abertura)
    return _a_ultima(achadas)


def classificar_lances(sans: Sequence[str]) -> Abertura | None:
    """O código mais profundo **pela ordem dos lances**, sem tabuleiro: microssegundos.

    É o caminho do índice (S-534): a transposição fica de fora, e a sala a recupera em
    `classificar` quando abre a partida. O primeiro lance que a árvore não conhece encerra a
    leitura no que já se viu.
    """
    no = _arvore()
    achada: Abertura | None = no.get("")
    for san in sans[:LANCES_EXAMINADOS]:
        proximo = no.get(san.rstrip("!?"))
        if proximo is None:
            break
        no = proximo
        if "" in no:
            achada = no[""]
    return achada


def codigo_do_header(valor: str) -> str:
    """`C47d` -> `C47`; `B90` -> `B90`; qualquer outra coisa -> `""`.

    Algumas bases acrescentam uma letra de sublinha ao código; a unidade da classificação são
    os três caracteres, e é neles que a busca filtra e a tabela nomeia.
    """
    casado = _RE_CODIGO.match(str(valor).strip().upper())
    return "" if casado is None else casado.group(1) + casado.group(2)


def nome(codigo: str) -> str:
    """A legenda do código, ou `""` para um código que a tabela não tem."""
    return _nomes().get(codigo_do_header(codigo), "")


def frase(codigo: str) -> str:
    """`ECO B33 · Sicilian, Sveshnikov` -- o que a sala mostra sob o tabuleiro. Vazio sem código.

    O código vem antes do nome porque é o que se compara e o que se procura; o nome é a legenda
    dele, e um código sem nome na tabela sai sozinho em vez de sair com uma legenda inventada.
    """
    limpo = codigo_do_header(codigo)
    if not limpo:
        return ""
    legenda = nome(limpo)
    return f"ECO {limpo}{SEPARADOR}{legenda}" if legenda else f"ECO {limpo}"


def frase_da_abertura(abertura: Abertura) -> str:
    """`ECO C67 · Ruy Lopez, Berlin Defense, Open Variation` -- o nome da **linha**.

    O par de `frase`, e a diferença entre os dois é a diferença entre ter a partida e ter só o
    código. `nome(codigo)` é a legenda da **família**, e ela repete: *Ruy Lopez* é o nome de nove
    códigos, *English* de treze, *Sicilian* de doze -- dizer `ECO C67 · Ruy Lopez` sob um
    tabuleiro que está na Berlim aberta é dizer o que já se via. Quando a posição foi
    classificada, sabe-se **qual linha** casou, e é o nome dela que distingue.
    """
    return f"ECO {abertura.codigo}{SEPARADOR}{abertura.nome}"


def frase_do_tabuleiro(tabuleiro: chess.Board, codigo_do_header_da_partida: str = "") -> str:
    """A frase para a partida na sala: o header `[ECO]` decide o código, a posição dá o nome.

    **O header continua vencendo o código**, pela mesma razão que no índice: é a classificação que
    quem publicou a partida escolheu, e a tabela embutida pode discordar dela numa transposição
    rara. O que mudou na segunda rodada da S-534 é o **nome**: a posição é classificada de todo
    jeito, e quando ela concorda com o header a legenda passa a ser a da linha casada
    (`frase_da_abertura`) em vez da legenda genérica da família. Discordando, o código é o do
    header e a legenda volta a ser a da família -- afirmar o nome de uma linha que a partida não
    percorreu seria pior que a legenda genérica. Ver `frase_da_abertura`.

    Sem header -- a partida veio de um servidor, ou foi digitada na sala -- vale a posição, e é aí
    que a transposição paga. Vazio quando nem um nem outro dizem nada.
    """
    do_header = codigo_do_header(codigo_do_header_da_partida)
    abertura = classificar(tabuleiro)
    if abertura is not None and (not do_header or abertura.codigo == do_header):
        return frase_da_abertura(abertura)
    return frase(do_header)


def lances_do_movetext(texto: str, maximo: int = LANCES_EXAMINADOS) -> list[str]:
    """Os primeiros `maximo` lances em SAN de um movetext cru, sem tabuleiro nenhum.

    É a entrada de `classificar_lances` no índice: o texto é a primeira linha (ou as duas
    primeiras) do movetext, com números, comentários e resultado ainda dentro. Os comentários
    saem primeiro porque `{Better was Bf4}` tem um `Bf4` que não foi jogado.
    """
    return _RE_LANCE.findall(_RE_COMENTARIO.sub(" ", texto))[:maximo]
