"""A decisão de orientação, separada da inferência (S-48).

**Por que isto é um módulo e não um `if`.** A cascata de orientação já mudou uma vez, e vai
mudar de novo. A S-13 supôs que a legalidade decidiria; a medição mostrou que ela só decide
em 16% dos casos, e que a confiança -- que acerta 320 de 320 em leitura boa -- vira ruído
quando a leitura é ruim. Cada uma dessas descobertas exigia editar uma função de 112 linhas
que também fazia a inferência, o que significa que medir uma regra isolada custava recortar
código à mão.

Aqui a cascata é uma tupla de objetos. Cada regra responde a uma pergunta e cala quando não
sabe; a **ordem** é a decisão, e `explain()` diz o que cada uma disse sobre um diagrama
específico. Medir uma regra sozinha contra o conjunto de campo passa a ser trocar a tupla.

A tabela que justifica a ordem, medida no split de teste (320 tabuleiros):

| sinal              | acerta | erra | empata |
|--------------------|--------|------|--------|
| legalidade         |     52 |    0 |    268 |
| `min_confidence`   |    320 |    0 |      0 |
| peões nas filas    |    264 |    9 |     47 |
| reis nas filas     |    267 |   37 |     16 |

O prior de **reis** que a S-13 sugeria erra 37 vezes em 320 e ficou fora -- e continua fora,
o que é informação e não omissão.

A tabela acima, porém, só descreve leitura boa. Medido depois no `1937 Kemeri.pdf`, a
confiança **para de decidir** quando a leitura é ruim: em duas páginas cuja leitura de pé era
claramente correta, as duas orientações saíram com confiança ~0,04 e margens de 0,001 e 0,019
-- ruído, e seguir a margem girava o diagrama errado. O prior de peões, que olha a estrutura
da posição e não a aparência das peças, continuava informativo nos mesmos casos (+3,8 contra
-4,2). É por isso que ele vem **depois** da margem e não antes: ele é a regra do regime de
leitura ruim, e no regime bom a confiança é melhor que ele.

**O que isto não resolve:** diagrama impresso do ponto de vista das pretas. Ali as peças
estão desenhadas para cima e o que muda é o mapeamento casa→índice, não os pixels; girar a
imagem estragaria a leitura. O sinal que resolveria são as coordenadas das bordas, e é o que
`CoordinateRule` lê. Ver a ressalva dela sobre a medição da S-45.
"""

from __future__ import annotations

from collections.abc import Callable

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .config import ORIENTATION_DECISIVE_MARGIN, ORIENTATION_PAWN_PRIOR_MARGIN
from .fen_utils import pawn_direction_score

if TYPE_CHECKING:  # pragma: no cover - só para o verificador de tipos
    from .inference import BoardPrediction

__all__ = [
    "BoardCoordinates",
    "ConfidenceMarginRule",
    "CoordinateRule",
    "OrientationEvidence",
    "OrientationPolicy",
    "OrientationRule",
    "OrientationVerdict",
    "OrientedPrediction",
    "PawnPriorRule",
    "SingleLegalRule",
    "TightMarginFallback",
]


@dataclass(frozen=True, eq=False)
class OrientedPrediction:
    """Leitura de um diagrama junto com a orientação escolhida para ela (S-13).

    Mora aqui, e não em `inference`, porque é o **resultado da decisão** e não o resultado da
    inferência. `inference` reexporta o nome para não quebrar os chamadores.
    """

    prediction: BoardPrediction
    rotation: int
    """0 ou 180 graus, aplicado à imagem antes de reconhecer."""

    margin: float
    """`min_confidence` da orientação escolhida menos a da descartada.

    Sempre ≥ 0 quando a escolha foi por confiança. É a medida de quão folgada foi."""

    ambiguous: bool
    """A escolha foi apertada, ou os dois sinais discordaram: vale olho humano."""

    reason: str
    """Por que esta orientação venceu, em pt-BR, para a UI e o arquivo de revisão."""

    alternative: BoardPrediction | None = None
    """A leitura descartada. `None` quando a orientação foi imposta, não escolhida."""

    black_point_of_view: bool = False
    """O diagrama está impresso do ponto de vista das pretas (passo C10 do ciclo 2).

    As peças estão de pé e a fila 1 fica em cima: `rotation` continua 0 -- girar a imagem
    poria as peças de cabeça para baixo -- e o que girou foi o **mapeamento** casa→índice
    da `prediction`, que já sai canônica (a8 no canto superior esquerdo do tabuleiro real).
    A tela desenha o tabuleiro virado para bater com o recorte; a FEN gravada é a posição."""


@dataclass(frozen=True)
class BoardCoordinates:
    """As coordenadas impressas na borda do diagrama, quando alguém as tiver lido (S-45).

    `ranks_top_to_bottom` é o que a coluna da esquerda diz, de cima para baixo:
    `(8, 7, 6, 5, 4, 3, 2, 1)` é ponto de vista das brancas, `(1, 2, ..., 8)` é das pretas.

    A S-45 foi medida em 2026-08-09 e adiada: coordenadas legíveis na camada de texto em 52
    de 380 diagramas (13,7%), das quais 48 do `Polgar`, que já lê a 1,000 -- e dos 49
    conclusivos, 49 apontam ponto de vista das brancas e nenhum das pretas. Desde o passo C10
    do ciclo 2 (2026-09-20) `pdf_text.board_coordinates_for` **produz** o dado a partir das
    palavras curtas em volta do retângulo do diagrama, e `files_left_to_right` entrou porque
    a linha `h..a` embaixo do tabuleiro diz o mesmo que a coluna `1..8` -- e um livro pode
    imprimir só uma das duas.
    """

    ranks_top_to_bottom: tuple[int, ...]
    files_left_to_right: tuple[str, ...] = ()
    """A linha de letras embaixo (ou em cima) do tabuleiro, da esquerda para a direita."""

    @property
    def white_point_of_view(self) -> bool | None:
        """`True`/`False` quando a leitura é conclusiva, `None` quando ela não diz nada.

        As filas decidem quando existem; senão as colunas. Quando as duas existem e
        discordam (um diagrama espelhado, ou uma leitura errada), a resposta é `None`: a
        regra cala em vez de escolher.
        """
        by_ranks = self._direction(self.ranks_top_to_bottom, reverse_is_white=True)
        by_files = self._direction(self.files_left_to_right, reverse_is_white=False)
        if by_ranks is not None and by_files is not None and by_ranks != by_files:
            return None
        return by_ranks if by_ranks is not None else by_files

    @staticmethod
    def _direction(run: tuple, *, reverse_is_white: bool) -> bool | None:
        if len(run) < 2:
            return None
        ordered = list(run)
        if ordered == sorted(ordered, reverse=True):
            return reverse_is_white
        if ordered == sorted(ordered):
            return not reverse_is_white
        return None


@dataclass(frozen=True)
class OrientationEvidence:
    """Tudo o que as regras podem olhar, e nada além disso.

    As regras não recebem o modelo, o dispositivo nem a imagem: recebem as duas leituras
    já feitas. É o que permite exercitá-las com `BoardPrediction` sintético e sem torch.
    """

    upright: BoardPrediction
    flipped: BoardPrediction
    coordinates: BoardCoordinates | None = None

    @property
    def margin(self) -> float:
        """`min_confidence` de pé menos a de cabeça para baixo. Positivo favorece de pé."""
        return self.upright.min_confidence - self.flipped.min_confidence

    @property
    def legal_upright(self) -> bool:
        return not self.upright.position.is_fatal

    @property
    def legal_flipped(self) -> bool:
        return not self.flipped.position.is_fatal

    @property
    def pawn_gap(self) -> float | None:
        """Quanto o prior de peões prefere a leitura de pé. `None` se ele não se aplica."""
        score_upright = pawn_direction_score(self.upright.class_indices)
        score_flipped = pawn_direction_score(self.flipped.class_indices)
        if score_upright is None and score_flipped is None:
            return None
        # Uma leitura sem peão de alguma cor não pontua; tratá-la como 0 é justo, porque o
        # outro lado é que está afirmando algo sobre a estrutura.
        return (score_upright or 0.0) - (score_flipped or 0.0)


@dataclass(frozen=True)
class OrientationVerdict:
    """O que uma regra respondeu.

    A spec da S-48 desenhava isto como `tuple[bool, str]`. Um terceiro campo entrou porque
    `ambiguous` é **por regra** e a tupla o perderia: uma legalidade que discorda da confiança
    é ambígua por definição, uma margem decisiva não é, e o desempate final é ambíguo sempre.
    Derivá-lo fora da regra exigiria que a política soubesse qual regra decidiu -- que é
    exatamente o acoplamento que este item desfaz.
    """

    upright: bool
    reason: str
    ambiguous: bool = False
    black_point_of_view: bool = False
    """As coordenadas dizem ponto de vista das pretas (passo C10): a leitura de pé é a
    certa e o que gira é o mapeamento das casas, não a imagem."""


class OrientationRule(Protocol):
    """Uma pergunta sobre a orientação. Cala quando não sabe responder.

    `name` é propriedade só de leitura de propósito: as regras são `dataclass(frozen=True)`,
    e um membro de protocolo declarado como atributo mutável as recusaria -- uma regra com
    estado seria uma regra cujo resultado depende de quantas vezes foi chamada.
    """

    @property
    def name(self) -> str:
        """Como a regra aparece em `explain()` e no painel de diagnóstico."""
        ...

    def decide(self, ev: OrientationEvidence) -> OrientationVerdict | None:
        """O veredito da regra, ou `None` quando ela não tem o que dizer sobre este diagrama."""
        ...


@dataclass(frozen=True)
class CoordinateRule:
    """As coordenadas da borda, quando alguém as leu (S-45).

    Primeira da cascata porque, quando responde, **responde**: as coordenadas são a única
    evidência direta do ponto de vista, e não um prior sobre a posição. Hoje ela cala em
    100% dos diagramas, porque nada produz `BoardCoordinates` -- ver a ressalva do tipo.
    """

    name: str = "coordenadas"

    def decide(self, ev: OrientationEvidence) -> OrientationVerdict | None:
        if ev.coordinates is None:
            return None
        white_pov = ev.coordinates.white_point_of_view
        if white_pov is None:
            return None
        # Ponto de vista das pretas não é "de cabeça para baixo": as peças estão de pé, a
        # leitura de pé é a certa, e o que gira é a FEN (passo C10). `upright=True` para a
        # política escolher `ev.upright`; `black_point_of_view` para ela girar o mapeamento.
        return OrientationVerdict(
            upright=True,
            reason="coordenadas da borda" + ("" if white_pov else " (ponto de vista das pretas)"),
            black_point_of_view=not white_pov,
        )


@dataclass(frozen=True)
class SingleLegalRule:
    """Uma orientação ilegal e a outra não → a legal.

    Primeira das regras medidas porque, quando decide, **nunca errou** em 320 tabuleiros -- e
    uma leitura ilegal é pior que uma de confiança baixa. Ela cala nos 84% em que as duas são
    legais, o que é o motivo de a S-13 ter se enganado ao supô-la dominante: girar 180° manda
    peão branco da fila `r` para a `9-r`, e 2..7 vira 7..2, o que continua legal.
    """

    name: str = "legalidade"

    def decide(self, ev: OrientationEvidence) -> OrientationVerdict | None:
        if ev.legal_upright == ev.legal_flipped:
            return None
        upright = ev.legal_upright
        return OrientationVerdict(
            upright=upright,
            reason="única orientação legal",
            # Discordância entre sinais nunca apareceu na medição, mas se aparecer é
            # exatamente o que "ambíguo" quer dizer -- e não algo para resolver em silêncio.
            ambiguous=(ev.margin > 0) != upright,
        )


@dataclass(frozen=True)
class ConfidenceMarginRule:
    """Margem de confiança mínima ≥ `decisive_margin` → a mais confiante.

    Acerta 320 de 320 quando a leitura é boa. O limiar existe porque abaixo dele a margem
    deixa de ser sinal -- ver o caso do `Kemeri` no docstring do módulo.
    """

    decisive_margin: float = ORIENTATION_DECISIVE_MARGIN
    name: str = "margem de confiança"

    def decide(self, ev: OrientationEvidence) -> OrientationVerdict | None:
        margin = ev.margin
        if abs(margin) < self.decisive_margin:
            return None
        return OrientationVerdict(upright=margin > 0, reason=f"maior confiança mínima (margem {abs(margin):.3f})")


@dataclass(frozen=True)
class PawnPriorRule:
    """A estrutura de peões, para o regime em que a confiança empatou baixo.

    Erra 9 vezes em 320 no regime bom, o que é pior que a margem -- por isso vem depois dela.
    No regime ruim é a única coisa que ainda sabe algo, porque olha a posição e não a
    aparência das peças.
    """

    pawn_prior_margin: float = ORIENTATION_PAWN_PRIOR_MARGIN
    name: str = "prior de peões"

    def decide(self, ev: OrientationEvidence) -> OrientationVerdict | None:
        gap = ev.pawn_gap
        if gap is None or abs(gap) < self.pawn_prior_margin:
            return None
        return OrientationVerdict(
            upright=gap > 0,
            reason=f"peões apontam a orientação (vantagem {abs(gap):.1f} filas, confiança empatada)",
        )


@dataclass(frozen=True)
class TightMarginFallback:
    """O desempate quando nenhuma regra soube. Nunca cala, e sempre marca `ambiguous`.

    Escolher a de maior confiança aqui não é uma decisão sobre a orientação: é a menos ruim
    das duas, dita em voz alta. Quem lê `ambiguous=True` sabe que vale olho humano.
    """

    name: str = "desempate"

    def decide(self, ev: OrientationEvidence) -> OrientationVerdict | None:
        margin = ev.margin
        tem_peoes = ev.pawn_gap is not None
        return OrientationVerdict(
            upright=margin >= 0,
            reason=(
                f"margem apertada ({abs(margin):.3f}) e peões não decidem"
                if tem_peoes
                else f"margem apertada ({abs(margin):.3f}) e sem peões dos dois lados"
            ),
            ambiguous=True,
        )


class OrientationPolicy:
    """Cascata ordenada de regras. A ordem é a decisão, e ela é medível regra a regra.

    `DEFAULT` reproduz exatamente a cascata que `predict_with_orientation` tinha embutida,
    mais `CoordinateRule` na frente -- que hoje cala sempre, porque nada produz o dado dela.
    """

    DEFAULT: tuple[OrientationRule, ...] = (
        CoordinateRule(),
        SingleLegalRule(),
        ConfidenceMarginRule(),
        PawnPriorRule(),
        TightMarginFallback(),
    )

    def __init__(self, rules: tuple[OrientationRule, ...] | None = None) -> None:
        self.rules = self.DEFAULT if rules is None else rules
        if not self.rules:
            raise ValueError("Uma política de orientação precisa de pelo menos uma regra.")

    def decide(self, ev: OrientationEvidence) -> tuple[OrientationRule, OrientationVerdict]:
        """A primeira regra que não cala, e o que ela disse."""
        for rule in self.rules:
            verdict = rule.decide(ev)
            if verdict is not None:
                return rule, verdict
        raise ValueError(
            "Nenhuma regra decidiu a orientação. A última regra da cascata tem de ser um "
            "desempate que nunca cala -- ver TightMarginFallback."
        )

    def resolve(
        self,
        ev: OrientationEvidence,
        *,
        turn: Callable[[BoardPrediction], BoardPrediction] | None = None,
    ) -> OrientedPrediction:
        """A leitura escolhida, com a orientação, a margem e o motivo em pt-BR.

        `turn` é quem sabe girar o **mapeamento** de uma leitura (as 64 casas espelhadas
        pelo centro, a FEN vista do outro lado) sem tocar nos pixels; a política o chama
        quando as coordenadas dizem ponto de vista das pretas (passo C10). Sem `turn`, a
        leitura de pé sai como está e o veredito registra o ponto de vista mesmo assim.
        """
        _rule, verdict = self.decide(ev)
        chosen, discarded = (ev.upright, ev.flipped) if verdict.upright else (ev.flipped, ev.upright)
        if verdict.black_point_of_view and turn is not None:
            chosen = turn(chosen)
        return OrientedPrediction(
            prediction=chosen,
            rotation=0 if verdict.upright else 180,
            margin=abs(ev.margin),
            ambiguous=verdict.ambiguous,
            reason=verdict.reason,
            alternative=discarded,
            black_point_of_view=verdict.black_point_of_view,
        )

    def explain(self, ev: OrientationEvidence) -> list[tuple[str, str | None]]:
        """O que **cada** regra disse, na ordem, inclusive as que calaram.

        Para o painel de diagnóstico e para medir uma regra isolada contra o conjunto de
        campo da S-41: `None` é "calou", e o texto é o motivo que ela daria se decidisse.
        Ao contrário de `resolve`, não para na primeira que responde.
        """
        return [(rule.name, verdict.reason if (verdict := rule.decide(ev)) else None) for rule in self.rules]


DEFAULT_POLICY = OrientationPolicy()
"""A cascata em produção. Instanciada uma vez porque as regras não têm estado."""
