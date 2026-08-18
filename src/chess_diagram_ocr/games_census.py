"""Quantos diagramas a base identifica, e **por que regra** (S-89).

**Por que ele existe.** A tabela que abriu este trabalho -- 1.268 posições em partida única,
141 preenchidas por desempate cego, 232 confirmadas e vazias -- foi escrita à mão, num script
de scratchpad, porque não havia instrumento. É a mesma cegueira que a S-82 encontrou na
detecção: sem contagem, "melhorou" é opinião, e uma regressão na regra de preenchimento não
tem como aparecer.

**O que ele conta que os outros não contam.** `cvoff-games` já relata quantos diagramas casam;
isso mede *alcance*. Este mede **procedência**: dos que casaram, quantos a base identificou
sozinha, quantos a legenda desempatou, quantos ficaram com o palpite da data e quantos uma
pessoa escolheu. São perguntas diferentes, e a segunda é a que diz se dá para confiar no
arquivo que vai virar PGN.

**A coluna que importa é "a revisar".** São os diagramas preenchidos por `filled_rule="date"` --
o desempate que discorda da legenda 72,3% das vezes onde há legenda para conferir. Eles têm
procedência gravada com cara de dado conferido, e a única forma de encontrá-los é esta.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .gallery import GalleryAnnotations
from .games_cache import PositionCache, PositionStore

__all__ = ["BUCKETS", "BookCensus", "bucket_for", "census_book", "census_total"]

BUCKETS: tuple[tuple[str, int], ...] = (
    ("1", 1),
    ("2", 2),
    ("3-5", 5),
    ("6-20", 20),
    ("21-100", 100),
    (">100", 0),
)
"""As faixas de quantas partidas contêm a posição, e o teto de cada uma (0 = sem teto).

Não são quantis: o corte em 5 é o `max_games` que decide se o preenchimento automático
acontece, e o corte em 1 é a diferença entre "não há escolha a fazer" e "há". As faixas existem
para responder *quanto trabalho humano sobra*, e por isso seguem as fronteiras das regras."""


def bucket_for(count: int) -> str:
    for nome, teto in BUCKETS:
        if teto and count <= teto:
            return nome
    return BUCKETS[-1][0]


def inferred_rule(annotation: Any, count: int) -> str:
    """A regra de um preenchimento gravado **antes** de a regra ser gravada (S-89).

    **Isto é inferência, e está declarada como tal** -- o mesmo desenho do `_recover_provenance`
    da S-72, e pela mesma necessidade: o acervo inteiro foi preenchido pela varredura de
    2026-08-13, e sem inferir nada o censo relata 1.413 diagramas "de regra desconhecida" e
    zero a revisar. Zero por ignorância não é zero.

    **E ela é dedutível, não chutada.** O código daquela varredura preenchia se, e só se, a
    posição estivesse em até `max_games` partidas, escolhendo sempre a primeira da lista
    ordenada por data. Então, sabendo quantas partidas contêm a posição:

    - uma partida só -> não houve escolha a fazer: `unique`;
    - duas ou mais -> a escolha foi o desempate por data: `date`, e é o que precisa de revisão.

    Quem tem regra gravada não passa por aqui: a marca real sempre vence a inferida.
    """
    if getattr(annotation, "filled_rule", ""):
        return str(annotation.filled_rule)
    if not getattr(annotation, "filled_from", ""):
        return ""
    return "unique" if count <= 1 else "date"


@dataclass
class BookCensus:
    """O placar de um livro: alcance, distribuição e procedência."""

    book: str = ""
    diagrams: int = 0
    matched: int = 0

    buckets: dict[str, int] = field(default_factory=dict)
    """Quantos diagramas por faixa de candidatas."""

    by_rule: dict[str, int] = field(default_factory=dict)
    """Quantos diagramas preenchidos por cada regra -- ver `DiagramAnnotation.filled_rule`.

    `sem marca` são os gravados antes da S-91, cuja regra ninguém registrou. Eles não são
    "confiáveis por omissão": são **desconhecidos**, e a diferença importa."""

    chosen: int = 0
    """Diagramas em que uma pessoa escolheu a partida (S-86). O trabalho já feito."""

    to_review: int = 0
    """Preenchidos pelo desempate por data. **A fila de trabalho que este censo existe para
    produzir** -- e a que some conforme a S-86 for usada."""

    pending: int = 0
    """Ambíguos que ninguém resolveu: nem a legenda, nem uma pessoa. O que a lista alcança."""

    inferred: int = 0
    """Quantos dos números acima vieram de `inferred_rule` e não de marca gravada.

    Aparece no relatório porque um total que mistura o medido com o deduzido sem dizer qual é
    qual é o tipo de número que a S-80 foi reprovada por produzir."""

    @property
    def ambiguous(self) -> int:
        return sum(quantos for faixa, quantos in self.buckets.items() if faixa != "1")

    def merge(self, outro: BookCensus) -> None:
        self.diagrams += outro.diagrams
        self.matched += outro.matched
        self.chosen += outro.chosen
        self.to_review += outro.to_review
        self.pending += outro.pending
        self.inferred += outro.inferred
        for faixa, quantos in outro.buckets.items():
            self.buckets[faixa] = self.buckets.get(faixa, 0) + quantos
        for regra, quantos in outro.by_rule.items():
            self.by_rule[regra] = self.by_rule.get(regra, 0) + quantos


def census_book(
    book: str,
    entries: Sequence[Any],
    cache: PositionCache | PositionStore,
    annotations: GalleryAnnotations,
    *,
    max_games: int = 5,
) -> BookCensus:
    """Conta um livro. Não abre a base e não muda nada -- é instrumento, não ferramenta.

    Lê as três fontes que já existem: o índice da Galeria diz quais diagramas há, o cache diz o
    que a base respondeu sobre cada posição, e as anotações dizem o que foi feito com isso.
    """
    placar = BookCensus(book=book, diagrams=len(entries))
    for entrada in entries:
        guardada = cache.get(getattr(entrada, "placement", ""))
        if not guardada.count:
            continue
        placar.matched += 1
        faixa = bucket_for(guardada.count)
        placar.buckets[faixa] = placar.buckets.get(faixa, 0) + 1

        anotacao = annotations.get(*entrada.key)
        if anotacao.filled_from or anotacao.chosen_game:
            regra = inferred_rule(anotacao, guardada.count) or "sem marca"
            placar.by_rule[regra] = placar.by_rule.get(regra, 0) + 1
            if not anotacao.filled_rule and regra != "sem marca":
                placar.inferred += 1
            if regra == "human":
                placar.chosen += 1
            elif regra == "date":
                placar.to_review += 1

        if guardada.count > 1 and not anotacao.chosen_game and anotacao.filled_rule != "caption":
            # Ambíguo e sem resposta humana nem da legenda. Acima do teto ele nem preencheu;
            # abaixo, preencheu por palpite. Nos dois casos é a lista da S-86 que resolve.
            placar.pending += 1
    return placar


def census_total(placares: Iterable[BookCensus]) -> BookCensus:
    total = BookCensus(book="total")
    for placar in placares:
        total.merge(placar)
    return total
