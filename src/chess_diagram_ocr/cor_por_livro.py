"""Calibrador de cor por livro: contorno × preenchido, medido na tinta e não no softmax (C5).

**O erro dominante do campo é cor.** Das 27 casas erradas nos 114 diagramas do conjunto de
campo, 10 são a mesma peça na outra cor -- 4 delas `q→Q` no Koblenz a 0,71–1,00
(`docs/OCR_UI_ANALISE_C2.md` §3.1). Com confiança assim o softmax não tem o que dizer: nenhuma
temperatura, TTA ou protótipo no embedding move uma casa a 1,00 (§9.1). O que distingue uma
dama preta de uma branca no papel é **quanto de tinta há dentro do glifo** -- as pretas são
preenchidas, as brancas são contorno --, e isso se mede na imagem, fora do modelo.

**A medida.** A média de cinza do centro da casa (os 40 % centrais, onde a peça está): uma
peça preenchida deixa o centro escuro, um contorno o deixa claro. Medido nos recortes do
campo antes de este módulo entrar (`scratchpad/colour_probe.py` do ciclo 2): no Koblenz as
pretas ficam entre 81 e 154 (mediana 108) e as brancas entre 148 e 219 (mediana 185); as
cinco casas de cor erradas do livro caem do lado certo (140, 137, 107, 128 → pretas; 171 →
branca). No Burgess, pretas ≤ 48 e brancas ≥ 137, e o `e5` errado mede 48. No Niemeijer e no
Stefaniu as duas distribuições se sobrepõem, e as casas erradas caem na sobreposição -- ali o
calibrador **se abstém**, que é o que um instrumento sem resolução deve fazer.

**Por livro, porque a impressão é do livro.** O limiar entre contorno e preenchido depende da
fonte, da tinta e do scan -- 145 no Koblenz, 90 no Burgess. As amostras vêm dos diagramas
**corrigidos** daquele livro (o perfil do livro, `caissa.ocr.book_profile`, mantido pelo
fechamento de ciclo, C6): sem perfil, o calibrador cala, e é o fechamento do ciclo -- rotular
uma dúzia de diagramas do livro e fechar -- que o faz falar. O próprio tabuleiro não é amostra
de si: uma peça por lado e por cor de casa nunca chega ao mínimo, e onde chegava (os peões) a
régua errou (Stefaniu p100, `b2 P→p`).

**Quando fala.** Só quando o par `(X, x)` domina a casa -- a dúvida é *só* de cor -- e o valor
medido está fora da zona em que as duas cores se misturam nas amostras. A troca é registrada
como reparo com evidência externa: a confiança da casa continua a da matriz (não se mente
sobre ela), e o gate julga as outras casas (`RecognizedDiagram.gate_confidence`), como no
lance seguinte (C11).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

from .config import PIECE_CLASSES

if TYPE_CHECKING:
    from .inference import BoardPrediction
    from .orientation import OrientedPrediction

VERSAO_DA_MEDIDA = "centro40-v3"
"""Identidade da medida: amostras de outra versão não se comparam com esta. A v3 guarda as
amostras **por tipo de peça e cor da casa** (ver `CalibradorDeCor` e `chave_da_amostra`)."""

TIPOS = "KQRBNP"
"""Os tipos de peça, como letras maiúsculas: a primeira metade da chave das amostras."""


def casa_clara(casa: int) -> bool:
    """Em ordem de leitura (0 = a8): a8 é clara, e a paridade alterna."""
    return (casa // 8 + casa % 8) % 2 == 0


def chave_da_amostra(tipo: str, casa: int) -> str:
    """`"Qc"` para uma dama numa casa clara, `"Qe"` numa escura.

    A casa escura de um livro hachurado escurece o centro de qualquer peça que está nela: um
    peão branco em b2 medido contra peões brancos de casas claras sai "preto". Medido no
    Stefaniu p100 antes desta chave: a régua do próprio tabuleiro pediu `b2 P→p` (só a guarda
    de legalidade a segurou). A peça na casa da mesma cor é a única régua da peça.
    """
    return f"{tipo.upper()}{'c' if casa_clara(casa) else 'e'}"

FRACAO_CENTRAL = 0.40
"""Lado do quadrado central medido, como fração do lado da casa."""

PAR_DOMINA = 0.90
"""`P(X) + P(x)` a partir do qual a dúvida da casa é só de cor."""

MINIMO_POR_COR = 5
"""Amostras do tipo, por cor, abaixo das quais o calibrador não decide nada.

Cinco e não três, medido: com quatro cavalos brancos de amostra (183–189) um cavalo branco a
171 foi trocado por preto no Koblenz -- o extremo de quatro amostras não é o extremo da
impressão. Nas 22 amostras corrigidas do livro, deixando uma de fora de cada vez: com 6, 9 ou
12 diagramas o livro ainda não junta cinco damas de cada cor e não troca nada; com 22, troca
oito casas -- as oito certas, todas damas `Q→q` -- e as casas de cor erradas caem de 21
para 13 (`caissa.ocr.closing`, medido no ciclo 2)."""

MARGEM = 10.0
"""Níveis de cinza além do **extremo** das amostras da outra cor para a cor ser dita: preta
só abaixo da branca mais escura menos isto, branca só acima da preta mais clara mais isto.

Extremos e não quantis, e é medido: com `[p95 das pretas, p5 das brancas]` a régua trocava
um rei branco que media exatamente o p5 dos reis brancos (Koblenz p51 g1, 153) e um peão
branco no p5 dos peões (p47 b2) -- 5 % das brancas estão ali por definição. Dez níveis é a
metade da diferença entre as sete damas `Q→q` do Koblenz e a dama branca mais escura do
livro (27 a 52 níveis abaixo dela): todas continuam trocadas, e nenhuma torre, rei, cavalo
ou peão branco no rabo da distribuição é trocado."""


def medir(cell_rgb: np.ndarray) -> float:
    """A média de cinza dos 40 % centrais da casa, em 0–255. Escuro = preenchido."""
    gray = cv2.cvtColor(cell_rgb, cv2.COLOR_RGB2GRAY) if cell_rgb.ndim == 3 else cell_rgb
    h, w = gray.shape[:2]
    y0 = int(round(h * (0.5 - FRACAO_CENTRAL / 2)))
    y1 = int(round(h * (0.5 + FRACAO_CENTRAL / 2)))
    x0 = int(round(w * (0.5 - FRACAO_CENTRAL / 2)))
    x1 = int(round(w * (0.5 + FRACAO_CENTRAL / 2)))
    centro = gray[y0:max(y1, y0 + 1), x0:max(x1, x0 + 1)]
    return float(centro.mean())


def _aparadas(valores: Sequence[float]) -> list[float]:
    """As amostras sem a mais clara e a mais escura, quando há pelo menos `MINIMO_POR_COR`.

    Uma amostra de cada cor pode ser de outra impressão -- no Koblenz as damas pretas de casa
    clara medem 117–142 e uma, hachurada (p. 46–48), 218. Tolerar **uma** por lado é o que
    deixa as outras falarem sem abrir a porta a uma segunda: com duas fora, a cor não separa.
    """
    ordenados = sorted(float(v) for v in valores)
    if len(ordenados) >= MINIMO_POR_COR:
        return ordenados[1:-1]
    return ordenados


@dataclass(frozen=True)
class Veredito:
    """O que o calibrador disse de uma casa."""

    cor: str | None
    """`"w"`, `"b"` ou `None` (abstido)."""

    valor: float
    zona: tuple[float, float]
    """`(branca mais escura − margem, preta mais clara + margem)` das amostras usadas: abaixo
    do primeiro é preta, acima do segundo é branca, entre os dois (ou nos dois) ninguém diz."""

    amostras: tuple[int, int]
    """Quantas amostras (brancas, pretas) decidiram."""


Amostras = dict[str, list[float]]
"""`chave_da_amostra` (`"Qc"`, `"Qe"`) → medidas das casas daquela peça naquela cor de casa."""


def _juntar(*grupos: Mapping[str, Sequence[float]]) -> Amostras:
    saida: Amostras = {}
    for grupo in grupos:
        for tipo, valores in grupo.items():
            saida.setdefault(tipo, []).extend(float(v) for v in valores)
    return saida


def _todas(grupo: Mapping[str, Sequence[float]]) -> list[float]:
    return [float(v) for valores in grupo.values() for v in valores]


@dataclass
class CalibradorDeCor:
    """As amostras de um livro, por tipo de peça, e a decisão que elas sustentam.

    **Por tipo, porque a tinta do centro é da peça.** Um cavalo branco tem a crina escura no
    meio da casa e uma torre preta tem as ameias claras: medido nas 22 amostras corrigidas do
    Koblenz, a régua de todas as peças juntas trocava certo as damas (`Q→q` ×4, o erro do
    campo) e errado uma torre (`a8`, 166 contra a zona 145–150) e um cavalo (`f7`, 159 contra
    164–185). Comparar dama com damas e cavalo com cavalos é o que tira essas duas.
    """

    brancas: Amostras = field(default_factory=dict)
    pretas: Amostras = field(default_factory=dict)
    diagramas: int = 0
    """Quantos diagramas corrigidos deram as amostras."""

    medida: str = VERSAO_DA_MEDIDA

    def vazio(self) -> bool:
        return not _todas(self.brancas) and not _todas(self.pretas)

    def decidir(self, valor: float, *, tipo: str) -> Veredito:
        """A cor que `valor` indica para uma peça da chave `tipo` (`chave_da_amostra`), ou abstenção.

        Decide só com `MINIMO_POR_COR` amostras **da mesma chave** (mesma peça, mesma cor de
        casa) em cada cor, só com as duas cores separadas (aparada uma amostra de cada lado,
        `_aparadas`), e só além dos extremos da outra cor com `MARGEM` de folga e dentro do que
        a própria cor mostra: preta abaixo da branca mais escura e não acima das pretas
        aparadas, branca o espelho. Um valor que satisfaz os dois (as cores não se tocam e ele
        cai no vão) ou nenhum é abstenção. Outra peça, ou a mesma noutra cor de casa, não é a
        régua desta, e uma régua que não separa não é régua.
        """
        tipo = tipo[0].upper() + tipo[1:] if len(tipo) > 1 else tipo.upper()
        brancas = list(self.brancas.get(tipo, ()))
        pretas = list(self.pretas.get(tipo, ()))
        amostras = (len(brancas), len(pretas))
        if len(brancas) < MINIMO_POR_COR or len(pretas) < MINIMO_POR_COR:
            return Veredito(None, valor, (float("nan"), float("nan")), amostras)
        pretas_aparadas = _aparadas(pretas)
        brancas_aparadas = _aparadas(brancas)
        if max(pretas_aparadas) >= min(brancas_aparadas):
            # As duas cores se misturam nesta chave (as torres do Koblenz: pretas 136–224
            # contra brancas 167–210, um livro que muda de impressão entre capítulos): a régua
            # não separa, e não fala. Medido: sem esta guarda, uma torre branca a 151 era
            # trocada por preta -- estava abaixo da branca mais escura, e dentro das pretas.
            return Veredito(None, valor, (min(brancas_aparadas), max(pretas_aparadas)), amostras)
        piso_das_brancas = min(brancas) - MARGEM
        teto_das_pretas = max(pretas) + MARGEM
        zona = (piso_das_brancas, teto_das_pretas)
        # Preta: abaixo da branca mais escura (todas, sem aparar: um extremo a mais só torna a
        # régua mais tímida) com margem **e** não acima das pretas aparadas com margem;
        # branca, o espelho. Um valor que satisfaz os dois lados (as cores não se tocam e ele
        # cai no vão) ou nenhum é abstenção.
        escura = valor < piso_das_brancas and valor <= max(pretas_aparadas) + MARGEM
        clara = valor > teto_das_pretas and valor >= min(brancas_aparadas) - MARGEM
        if escura and not clara:
            return Veredito("b", valor, zona, amostras)
        if clara and not escura:
            return Veredito("w", valor, zona, amostras)
        return Veredito(None, valor, zona, amostras)

    def as_dict(self) -> dict[str, Any]:
        return {"medida": self.medida, "diagramas": self.diagramas,
                "brancas": {tipo: [round(v, 2) for v in valores] for tipo, valores in sorted(self.brancas.items())},
                "pretas": {tipo: [round(v, 2) for v in valores] for tipo, valores in sorted(self.pretas.items())}}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> CalibradorDeCor | None:
        if not data:
            return None
        medida = str(data.get("medida", VERSAO_DA_MEDIDA))
        if medida != VERSAO_DA_MEDIDA:
            return None
        brancas = data.get("brancas", {})
        pretas = data.get("pretas", {})
        if not isinstance(brancas, Mapping) or not isinstance(pretas, Mapping):
            return None
        return cls(brancas={str(k): [float(v) for v in vals] for k, vals in brancas.items()},
                   pretas={str(k): [float(v) for v in vals] for k, vals in pretas.items()},
                   diagramas=int(data.get("diagramas", 0)), medida=medida)


def amostras_do_tabuleiro(cells: Sequence[np.ndarray], placement_labels: Sequence[int]) -> tuple[Amostras, Amostras]:
    """`(brancas, pretas)` por chave, medidas nas casas ocupadas de um tabuleiro **rotulado**."""
    brancas: Amostras = {}
    pretas: Amostras = {}
    for casa, (cell, classe) in enumerate(zip(cells, placement_labels, strict=True)):
        nome = PIECE_CLASSES[int(classe)]
        if nome == "empty":
            continue
        (brancas if nome.isupper() else pretas).setdefault(chave_da_amostra(nome, casa), []).append(medir(cell))
    return brancas, pretas


@dataclass(frozen=True)
class TrocaDeCor:
    casa: int
    de: int
    para: int
    veredito: Veredito


def _gemea(classe: int) -> int | None:
    nome = PIECE_CLASSES[int(classe)]
    if nome == "empty":
        return None
    return PIECE_CLASSES.index(nome.swapcase())


def trocas_de_cor(
    probs: np.ndarray,
    class_indices: Sequence[int],
    cells: Sequence[np.ndarray],
    calibrador: CalibradorDeCor | None,
    *,
    medir_casa: Callable[[np.ndarray], float] = medir,
) -> list[TrocaDeCor]:
    """As casas em que a tinta contradiz a cor lida, com o par `(X, x)` dominando.

    Sem `calibrador` (livro sem perfil) não há troca: o tabuleiro não é amostra de si.
    """
    probs = np.asarray(probs, dtype=np.float64)
    if calibrador is None or calibrador.vazio():
        return []
    if probs.shape != (64, len(PIECE_CLASSES)) or len(cells) != 64:
        return []
    trocas: list[TrocaDeCor] = []
    for casa, classe in enumerate(class_indices):
        gemea = _gemea(classe)
        if gemea is None:
            continue
        if probs[casa, classe] + probs[casa, gemea] < PAR_DOMINA:
            continue
        nome = PIECE_CLASSES[int(classe)]
        cor_lida = "w" if nome.isupper() else "b"
        veredito = calibrador.decidir(medir_casa(cells[casa]), tipo=chave_da_amostra(nome, casa))
        if veredito.cor is not None and veredito.cor != cor_lida:
            trocas.append(TrocaDeCor(casa, int(classe), gemea, veredito))
    return trocas


def cells_as_read(board_rgb: np.ndarray, oriented: OrientedPrediction) -> list[np.ndarray]:
    """As 64 casas do recorte na ordem em que `oriented.prediction` as numera.

    A leitura a 180° foi feita sobre a imagem girada; no ponto de vista das pretas a matriz
    foi invertida (a casa `i` é a célula `63 - i`). As casas medidas têm de ser as que o
    modelo viu, ou a cor seria julgada na célula errada.
    """
    from .board_detection import split_board_into_cells

    board = cv2.rotate(board_rgb, cv2.ROTATE_180) if oriented.rotation == 180 else board_rgb
    cells = split_board_into_cells(board)
    if getattr(oriented, "black_point_of_view", False):
        cells = cells[::-1]
    return cells


def apply_colour(
    prediction: BoardPrediction,
    board_rgb: np.ndarray,
    oriented: OrientedPrediction,
    calibrador: CalibradorDeCor | None,
) -> tuple[BoardPrediction, list[TrocaDeCor], str]:
    """A leitura com as cores que a tinta contradiz trocadas (C5), e o motivo em pt-BR.

    Sem calibrador (livro sem perfil) devolve a leitura como está. Uma troca que tornasse a
    posição fatalmente ilegal quando a lida não era é descartada inteira: o calibrador não
    sabe de reis, e o decodificador já falou. `prediction_with_squares` acumula as trocas em
    `decode.changed_squares` e mantém a matriz.
    """
    from .fen_utils import check_position
    from .inference import prediction_with_squares

    if calibrador is None or calibrador.vazio():
        return prediction, [], ""
    cells = cells_as_read(board_rgb, oriented)
    trocas = trocas_de_cor(prediction.probs, prediction.class_indices, cells, calibrador)
    if not trocas:
        return prediction, [], ""
    trocada = prediction_with_squares(prediction, [(t.casa, t.de, t.para) for t in trocas])
    if check_position(trocada.fen_board).is_fatal and not prediction.position.is_fatal:
        descricao = ", ".join(f"{_nome(t.casa)} {PIECE_CLASSES[t.de]}→{PIECE_CLASSES[t.para]}" for t in trocas)
        return prediction, [], f"a tinta contradiz a cor em {descricao}, mas a troca tornaria a posição ilegal: não aplicada"
    descricao = ", ".join(
        f"{_nome(t.casa)} {PIECE_CLASSES[t.de]}→{PIECE_CLASSES[t.para]} ({t.veredito.valor:.0f} fora de "
        f"{t.veredito.zona[0]:.0f}–{t.veredito.zona[1]:.0f}, {t.veredito.amostras[0]}+{t.veredito.amostras[1]} amostras)"
        for t in trocas)
    return trocada, trocas, f"cor pela tinta (perfil do livro, {calibrador.diagramas} diagramas): {descricao}"


def _nome(casa: int) -> str:
    return f"{'abcdefgh'[casa % 8]}{8 - casa // 8}"


def calibrador_do_livro(pdf_source: Any) -> CalibradorDeCor | None:
    """O calibrador gravado no perfil do livro deste PDF, quando a suíte está importável.

    O perfil mora na suíte (`caissa.ocr.book_profile`, ao lado da cifra do livro); o tronco
    não o escreve, só o lê -- e num checkout sem a suíte devolve `None`, e o tabuleiro
    responde sozinho. A mesma guarda que `decisoes_de_diagrama` usa para gravar a decisão.
    """
    try:
        from caissa.ocr.book_profile import colour_for_pdf
    except ImportError:
        return None
    try:
        return CalibradorDeCor.from_dict(colour_for_pdf(pdf_source))
    except Exception:  # noqa: BLE001 - um perfil ilegível não pode derrubar a leitura
        return None
