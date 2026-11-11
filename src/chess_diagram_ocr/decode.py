"""Decodificação de um tabuleiro sujeita às regras do xadrez (S-11).

O argmax por casa decide 64 vezes de forma independente, então nada impede que o
resultado tenha dois reis brancos ou um peão na oitava fila. Nos PDFs medidos isso não é
teórico: em fonte figurina alemã, K e Q se confundem sistematicamente e o resultado sai
sem rei branco.

A informação para corrigir já está na matriz de probabilidades -- o argmax é que a joga
fora. Aqui a decodificação vira uma busca: qual é a atribuição de **maior probabilidade**
entre as que respeitam as regras? Como o argmax é o ótimo irrestrito, a resposta é sempre
"o argmax com o menor número de trocas mais baratas possível".

As restrições são todas verificáveis sem saber o lado a jogar -- que o diagrama de livro
não carrega. Xeque não entra aqui por isso (ver `fen_utils`, S-05).

**Duas regras a mais (C11 do ciclo 2 OCR/UI, `docs/OCR_UI_ANALISE_C2.md` §3.9).** Reis
adjacentes é violação absoluta -- nenhuma posição legal os tem -- e nunca estava aqui. E dois
bispos do mesmo lado em casas da mesma cor não são violação por si (uma promoção explica), mas
consomem um peão ausente **do mesmo modo que o excesso de promoção já modela**: o lado começa
com um bispo em cada cor, logo cada bispo a mais numa cor veio de um peão. Com oito peões no
tabuleiro, dois bispos brancos em casas claras são impossíveis, e é esse o caso da dúvida do
Stefaniu f1. As duas ficam em `DecodeRules`, com `CLASSIC_RULES` para medir sem elas.

**O rei que falta só é reparado onde a rede vê rei.** Diagrama de esquema ou de marcas pode não ter
rei nenhum, e a busca punha um na casa menos contrariada, com probabilidade quase zero: uma casa
vazia e limpa virava rei. Ver `MIN_KING_PROBABILITY`. Sem indício, a falta fica declarada em
`remaining_kinds`, e os outros reparos continuam.
"""

from __future__ import annotations

import heapq
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import Enum

import numpy as np

from .config import PIECE_CLASSES, PIECE_TO_IDX
from .fen_utils import fen_from_class_indices

_EPS = 1e-12


class TipoDeViolacao(Enum):
    """Que regra uma leitura viola (S-835). A frase vai para a tela; quem decide confere o tipo."""

    REI_FALTANDO = "rei_faltando"
    REIS_DEMAIS = "reis_demais"
    PEAO_NA_BORDA = "peao_na_borda"
    PEOES_DEMAIS = "peoes_demais"
    PECAS_DEMAIS = "pecas_demais"
    PROMOVIDAS_DEMAIS = "promovidas_demais"
    REIS_SE_TOCAM = "reis_se_tocam"

EMPTY = PIECE_TO_IDX["empty"]
WHITE_KING = PIECE_TO_IDX["K"]
BLACK_KING = PIECE_TO_IDX["k"]
WHITE_PAWN = PIECE_TO_IDX["P"]
BLACK_PAWN = PIECE_TO_IDX["p"]

WHITE_CLASSES = frozenset(PIECE_TO_IDX[name] for name in "PNBRQK")
BLACK_CLASSES = frozenset(PIECE_TO_IDX[name] for name in "pnbrqk")

# Índices em ordem de leitura: 0..7 é a oitava fila, 56..63 é a primeira. Peão em nenhuma
# das duas -- na oitava teria promovido, na primeira não teria como ter chegado.
BACKRANK_SQUARES: tuple[int, ...] = tuple(range(8)) + tuple(range(56, 64))

MAX_PAWNS = 8
MAX_PIECES = 16

# Quantas peças de cada tipo o lado começa tendo. O que passa disso só pode ter vindo de
# promoção, e cada promoção consome um peão.
_INITIAL_COUNT = {"N": 2, "B": 2, "R": 2, "Q": 1}


MIN_KING_PROBABILITY = 0.01
"""Abaixo disto a busca não cria rei na casa, seja qual for a regra que ela está reparando."""


@dataclass(frozen=True)
class DecodeRules:
    """Quais regras além das da S-11 o decodificador aplica (C11).

    `bishop_colors`: bispos de um lado em casas da mesma cor contam como promovidos na
    conta de peões ausentes. `adjacent_kings`: reis que se tocam são uma violação.
    `min_king_probability`: a menor probabilidade com que uma casa pode virar rei; zero é o
    decodificador que sempre punha o rei que faltava.
    """

    bishop_colors: bool = True
    adjacent_kings: bool = True
    min_king_probability: float = MIN_KING_PROBABILITY


DEFAULT_RULES = DecodeRules()
CLASSIC_RULES = DecodeRules(bishop_colors=False, adjacent_kings=False, min_king_probability=0.0)
"""O decodificador de antes do C11 -- a sabotagem do `lab_gate --rules classic`."""


@dataclass(frozen=True)
class DecodeResult:
    class_indices: list[int]
    fen_board: str

    log_prob: float
    """Log-probabilidade da atribuição escolhida. Sempre ≤ a do argmax."""

    changed_squares: list[tuple[int, int, int]]
    """(casa, classe do argmax, classe final) para cada troca feita."""

    constraints_satisfied: bool
    """False quando a busca esgotou o limite sem achar atribuição legal."""

    remaining_kinds: tuple[TipoDeViolacao, ...] = ()
    """O que continuou violado, quando `constraints_satisfied` é False (S-835).

    Havia ao lado uma frase em pt-BR por violação, `remaining_problems`, "para a tela" -- e
    nenhuma tela a lia: a S-835 tirou dela a última decisão, e o mutator da S-873 achou as frases
    trocáveis por vazio sem nada notar. Saiu. A frase que a pessoa lê sobre a posição é a de
    `fen_utils.check_position` e a do painel de `ui/legality`."""

    @property
    def changed_square_count(self) -> int:
        return len(self.changed_squares)

    @property
    def only_king_missing(self) -> bool:
        """O único defeito é o rei que nenhuma casa sustenta: a leitura pode estar certa."""
        return bool(self.remaining_kinds) and all(k is TipoDeViolacao.REI_FALTANDO for k in self.remaining_kinds)


@dataclass(frozen=True)
class _Violation:
    """Uma regra violada e o conjunto de reparos capaz de resolvê-la.

    `squares` são as casas que uma solução obrigatoriamente precisa alterar (ou, no caso
    de rei faltando, as casas candidatas a virar rei). Ramificar sobre elas é completo:
    nenhuma atribuição legal fica fora do espaço de busca, salvo as que criam um rei sem
    indício. Vazio quer dizer que nenhuma troca resolve: o rei falta e nenhuma casa o sustenta.
    """

    tipo: TipoDeViolacao
    squares: tuple[int, ...]
    targets: tuple[int, ...] | None
    """Classes-alvo fixas. `None` significa "qualquer outra classe plausível da casa"."""


def _color_counts(state: tuple[int, ...]) -> Counter[int]:
    return Counter(state)


def _promotion_excess(counts: Counter[int], upper: bool) -> int:
    """Peças a mais do que o início da partida -- cada uma consumiu um peão."""
    excess = 0
    for name, initial in _INITIAL_COUNT.items():
        symbol = name if upper else name.lower()
        excess += max(0, counts[PIECE_TO_IDX[symbol]] - initial)
    return excess


def _square_is_light(square: int) -> bool:
    """Em ordem de leitura (0 = a8): a8 é clara, e a paridade alterna."""
    row, col = divmod(square, 8)
    return (row + col) % 2 == 0


def _bishop_promotion_excess(state: tuple[int, ...], upper: bool) -> int:
    """Bispos promovidos que a cor das casas denuncia, além dos que a contagem já denuncia.

    O lado começa com um bispo claro e um escuro: `max(0, claros − 1) + max(0, escuros − 1)`
    é o mínimo de bispos promovidos, sempre ≥ `max(0, bispos − 2)` (que `_promotion_excess`
    já conta). Devolve só a diferença, para não contar duas vezes.
    """
    bishop = PIECE_TO_IDX["B" if upper else "b"]
    light = sum(1 for square in range(64) if state[square] == bishop and _square_is_light(square))
    dark = sum(1 for square in range(64) if state[square] == bishop and not _square_is_light(square))
    by_colour = max(0, light - 1) + max(0, dark - 1)
    by_count = max(0, light + dark - 2)
    return by_colour - by_count


def _adjacent_kings(state: tuple[int, ...]) -> tuple[int, ...]:
    """As casas dos dois reis quando se tocam (distância de Chebyshev ≤ 1), senão vazio."""
    whites = [square for square in range(64) if state[square] == WHITE_KING]
    blacks = [square for square in range(64) if state[square] == BLACK_KING]
    touching: list[int] = []
    for white in whites:
        for black in blacks:
            if abs(white // 8 - black // 8) <= 1 and abs(white % 8 - black % 8) <= 1:
                touching.extend((white, black))
    return tuple(sorted(set(touching)))


def _king_without_evidence(square: int, target: int, probs: np.ndarray, rules: DecodeRules) -> bool:
    return target in (WHITE_KING, BLACK_KING) and probs[square, target] < rules.min_king_probability


def _find_violations(state: tuple[int, ...], probs: np.ndarray, rules: DecodeRules = DEFAULT_RULES) -> list[_Violation]:
    counts = _color_counts(state)
    violations: list[_Violation] = []

    for king in (WHITE_KING, BLACK_KING):
        total = counts[king]
        if total == 0:
            violations.append(
                _Violation(
                    TipoDeViolacao.REI_FALTANDO,
                    tuple(square for square in range(64) if not _king_without_evidence(square, king, probs, rules)),
                    (king,),
                )
            )
        elif total > 1:
            violations.append(
                _Violation(TipoDeViolacao.REIS_DEMAIS, tuple(square for square in range(64) if state[square] == king), None)
            )

    on_backrank = tuple(square for square in BACKRANK_SQUARES if state[square] in (WHITE_PAWN, BLACK_PAWN))
    if on_backrank:
        violations.append(_Violation(TipoDeViolacao.PEAO_NA_BORDA, on_backrank, None))

    for pawn in (WHITE_PAWN, BLACK_PAWN):
        if counts[pawn] > MAX_PAWNS:
            violations.append(
                _Violation(TipoDeViolacao.PEOES_DEMAIS, tuple(square for square in range(64) if state[square] == pawn), None)
            )

    for classes, upper in ((WHITE_CLASSES, True), (BLACK_CLASSES, False)):
        squares = tuple(square for square in range(64) if state[square] in classes)
        if len(squares) > MAX_PIECES:
            violations.append(_Violation(TipoDeViolacao.PECAS_DEMAIS, squares, None))
            continue

        pawn = WHITE_PAWN if upper else BLACK_PAWN
        promoted = _promotion_excess(counts, upper)
        if rules.bishop_colors:
            promoted += _bishop_promotion_excess(state, upper)
        if counts[pawn] + promoted > MAX_PAWNS:
            violations.append(_Violation(TipoDeViolacao.PROMOVIDAS_DEMAIS, squares, None))

    if rules.adjacent_kings:
        touching = _adjacent_kings(state)
        if touching:
            violations.append(_Violation(TipoDeViolacao.REIS_SE_TOCAM, touching, None))

    return violations


def _alternatives(
    square: int,
    current: int,
    logp: np.ndarray,
    limit: int,
) -> tuple[int, ...]:
    """Classes plausíveis para substituir a atual, da mais provável para a menos.

    Restringir às `limit` melhores é o que mantém a busca barata. `empty` entra sempre:
    é o reparo certo quando a casa é ruído da moldura ou da legenda, e nem por isso o
    modelo lhe dá probabilidade alta.
    """
    order = [int(index) for index in np.argsort(logp[square])[::-1] if int(index) != current]
    chosen = order[:limit]
    if EMPTY != current and EMPTY not in chosen:
        chosen.append(EMPTY)
    return tuple(chosen)


def _candidates(
    state: tuple[int, ...],
    violation: _Violation,
    logp: np.ndarray,
    alternatives_per_square: int,
    probs: np.ndarray,
    rules: DecodeRules,
) -> Iterator[tuple[int, int]]:
    for square in violation.squares:
        current = state[square]
        targets = (
            tuple(target for target in violation.targets if target != current)
            if violation.targets is not None
            else _alternatives(square, current, logp, alternatives_per_square)
        )
        for target in targets:
            if not _king_without_evidence(square, target, probs, rules):
                yield square, target


def _build_result(
    state: tuple[int, ...],
    base: tuple[int, ...],
    logp: np.ndarray,
    *,
    satisfied: bool,
    violations: Sequence[_Violation] = (),
) -> DecodeResult:
    changed = [(square, base[square], state[square]) for square in range(64) if state[square] != base[square]]
    log_prob = float(sum(logp[square, state[square]] for square in range(64)))
    return DecodeResult(
        class_indices=list(state),
        fen_board=fen_from_class_indices(state),
        log_prob=log_prob,
        changed_squares=changed,
        constraints_satisfied=satisfied,
        remaining_kinds=tuple(v.tipo for v in violations),
    )


MAX_EXPANSOES = 600
"""Quantos estados a busca retira da fila num tabuleiro só, e o único teto que ela tem (S-834).

**O relógio decidia, e não pode.** A S-358 pôs um prazo de 0,5 s de `time.monotonic` por cima das
5.000 expansões, porque um tabuleiro ilegal gastava todas elas (3,4 s medidos, duas vezes por
diagrama no modo `auto`). Com o prazo, a mesma matriz de probabilidades saía em FEN diferente numa
máquina carregada, em rodadas paralelas ou na primeira chamada lenta do processo: o modelo `mhsp`
deu 28 e 27 casas reparadas sobre o mesmo código, conforme a carga. O teto agora é de expansões, e
só de expansões, e por isso a leitura é função da matriz e de nada mais.

**600, medidos nesta máquina em 2026-11-09.** O pior caso conhecido é o da S-358 -- rei branco
como argmax nas 64 casas --, que ramifica em ~200 sucessores por expansão: 400 expansões levam
0,32 s, 500 levam 0,40 s, 600 levam ~0,5 s e 700 já 0,67 s. Um tabuleiro real custa cerca de um
sétimo disso por expansão (as 228 leituras do conjunto de campo com o `mhsp`, a 0° e a 180°: 5.000
expansões em até 0,6 s). No conjunto de campo, com 600, o modelo de produção sai idêntico ao
relatório arquivado, e o `mhsp` sai com 27 casas reparadas em vez de 28: a do `Euwe Band 1-2` cujo
reparo precisava de mais de 600 expansões e que o relógio só concedia com a máquina ociosa.
"""


def decode_constrained(
    probs: np.ndarray,
    *,
    max_changes: int = 6,
    max_expansions: int = MAX_EXPANSOES,
    alternatives_per_square: int = 4,
    rules: DecodeRules = DEFAULT_RULES,
) -> DecodeResult:
    """Atribuição de maior probabilidade que respeita as regras verificáveis do xadrez.

    Busca de custo uniforme sobre trocas: o custo de uma atribuição é a perda de
    log-probabilidade em relação ao argmax, que é sempre ≥ 0 e **não depende do caminho**
    -- o que torna a primeira solução retirada da fila a de maior probabilidade dentro do
    espaço considerado.

    `max_changes` limita quantas casas podem ser reescritas. É uma trava de segurança: se
    a leitura estiver muito errada, reparar 20 casas produziria uma posição legal e
    inventada, pior que admitir a falha. Nesse caso volta o melhor estado parcial com
    `constraints_satisfied=False`.

    **Uma posição reparada aqui nunca é exportada, e isso é aritmética e não tendência (S-132).**

    Uma casa reparada recebeu, por definição, uma classe que **não** era o argmax. A confiança
    reportada para ela é a dessa classe (`inference.prediction_from_probs` troca as confianças
    pelas das classes efetivamente escolhidas, que é o desenho certo — a confiança relatada tem
    de ser a verdade sobre o que foi escolhido). Essa probabilidade é no máximo a segunda maior
    da casa, e a segunda maior **não pode passar de 0,5**: se passasse, a maior também
    passaria, e as duas somariam mais que 1.

    `min_confidence` é o mínimo sobre as 64 casas. Logo, um diagrama com pelo menos uma casa
    reparada tem `min_confidence ≤ 0,5`, e o gate de exportação é
    `ACCEPT_MIN_CONFIDENCE = 0,80`. **Nenhum diagrama reparado passa**, hoje nem com outro
    modelo — o teto de 0,5 não depende de quão bem o classificador vai.

    Não é defeito, é propriedade. Mas ela muda a leitura de duas métricas que o projeto publica
    lado a lado: `cvoff-field` mostra "casas reparadas" ao lado da taxa de exportação, e o
    reparo — uma das entregas centrais da Fase 2 — **não contribui com um único diagrama
    exportado**. Por isso o relatório separa `repaired_exported` de `repaired_blocked` desde a
    S-132: somados, os dois números sugeriam que o reparo estava ajudando a exportar.

    Se um dia se quiser que o reparo chegue ao PGN, a mudança é no **gate** e não aqui — um
    gate que olhasse a confiança das casas *não* reparadas, ou um limiar próprio para posição
    reparada. Mexer no decodificador para elevar a confiança da casa consertada seria mentir
    sobre o que ele sabe.
    """
    probs = np.asarray(probs, dtype=np.float64)
    expected = (64, len(PIECE_CLASSES))
    if probs.shape != expected:
        raise ValueError(f"Esperada matriz {expected}, recebida {probs.shape}.")

    logp = np.log(np.clip(probs, _EPS, None))
    base: tuple[int, ...] = tuple(int(index) for index in probs.argmax(axis=1))

    if not _find_violations(base, probs, rules):
        return _build_result(base, base, logp, satisfied=True)

    heap: list[tuple[float, int, tuple[int, ...]]] = [(0.0, 0, base)]
    visited: set[tuple[int, ...]] = {base}
    counter = 0
    expansions = 0

    best_state = base
    best_key = (len(_find_violations(base, probs, rules)), 0.0)

    while heap and expansions < max_expansions:
        cost, _, state = heapq.heappop(heap)
        expansions += 1

        violations = _find_violations(state, probs, rules)
        if not violations:
            return _build_result(state, base, logp, satisfied=True)
        # Só sobrou o que nenhuma troca resolve. A fila sai em ordem de custo, então este é o
        # melhor estado possível, e seguir buscando só gastaria o tempo da S-358.
        repairable = [violation for violation in violations if violation.squares]
        if not repairable:
            return _build_result(state, base, logp, satisfied=False, violations=violations)

        key = (len(violations), cost)
        if key < best_key:
            best_key = key
            best_state = state

        changes = sum(1 for square in range(64) if state[square] != base[square])
        if changes >= max_changes:
            continue

        # Ramificar sobre a violação mais restrita primeiro reduz o fator de ramificação
        # sem perder completude: qualquer solução precisa reparar todas elas.
        violation = min(repairable, key=lambda item: len(item.squares))

        for square, target in _candidates(state, violation, logp, alternatives_per_square, probs, rules):
            successor = state[:square] + (target,) + state[square + 1 :]
            if successor in visited:
                continue
            visited.add(successor)
            counter += 1
            delta = float(logp[square, state[square]] - logp[square, target])
            heapq.heappush(heap, (cost + delta, counter, successor))

    return _build_result(best_state, base, logp, satisfied=False, violations=_find_violations(best_state, probs, rules))
