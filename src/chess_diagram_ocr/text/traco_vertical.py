"""Traço vertical contra ponto, decidido pela **geometria da caixa** (S-730).

Irmão de `caixa_alta`, `marca_fina` e `traco`, e pelo mesmo motivo de fundo: o recorte que o
classificador recebe é o bbox apertado, esticado para 32x32. O `l` de uma fonte sem serifa é um
retângulo cheio, e esticado é a mesma imagem que o ponto: `will` saía `wi..`, e `I` saía `.`.

## Medido antes de escrever a regra

Nas 27 folhas dos 5 livros aprovados do ouro-dev, nenhuma classe certa estava longe, mas ela também
não estava sempre logo atrás do erro:

    ref -> lido   n     rank da classe certa     altura / altura-de-x     largura / altura
    l -> .       149    2: 62   6: 87            1,03 a 1,32              0,12
    I -> .        13    5: 13                    1,03 a 1,32              0,12 a 0,19
    .  certo    1095    --                       0,15 a 0,28              0,80 a 1,25

**O vão é de quase quatro vezes, e o rank não decide.** Onde o `.` não vence, vence o `—`, e o `l`
cai para o sexto lugar, atrás de quatro traços: quem olha só o rank 2 acha 62 dos 149. É decisão de
geometria sobre a caixa, e a ordem entre `l`, `I` e `1` dentro do modelo não diz nada, porque depois
do resize os três são a mesma mancha. Quem os separa é o contexto.

## A regra irmã: a marca baixa lida como traço

Em *Minhas 60* (Calibri), a vírgula é uma barra inclinada, e o modelo responde `/` a 0,999 (a classe
`,` nem aparece entre as oito primeiras): `entanto,` saía `entantol`, porque depois o `italico` troca
o `/` por `l`. Toda a informação está na caixa:

    ref -> lido   n     altura / altura-de-x     descida / altura
    , -> l / /    20    0,48 a 0,53              0,56 a 0,58
    , certo      191    0,35 a 0,56              > 0,20
    / e l certos  --    >= 1,00                  ~0

Esta é a única decisão do subpacote que aceita uma classe que o modelo não pôs no topo, e é pelo que
ela olha: um traço que tem meia altura de letra e desce abaixo da linha de base não é traço nenhum.

## O que este módulo não faz

Não decide `l` contra `1` em caixa que o modelo **já leu** como `l` ou `1`: isso é do dicionário
(S-508). E não mexe em caixa alta que o modelo leu como `i`, `!`, `:`, `;`, `(` ou `/`: todas têm a
mesma geometria, e nenhuma é erro de marca fina.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from . import caixa_alta as _caixa_alta
from .palavras_curtas import conhecida_ou_curta

LIGADO = True
"""A reversão da S-730. Desligada, o módulo devolve a entrada intacta."""

MARCAS = ".,'`-–—_"
"""As classes que nunca têm caixa alta e estreita: o que o modelo diz quando o traço é esticado."""

TRACOS_DE_VIRGULA = "/l1I|"
"""O que o modelo responde para a vírgula que é uma barra inclinada."""

ALTURA_MINIMA = 0.85
"""Acima de tantas alturas-de-x, a caixa estreita é traço de verdade.

No meio do vão de 0,28 (o ponto mais alto) a 1,03 (o traço mais baixo); nos dois lados o número é
da altura-de-x de `caixa_alta.x_height_da_linha`, e não da mediana da linha."""

PROPORCAO_MAXIMA = 0.35
"""Largura sobre altura. O traço mede 0,12 a 0,19, e o ponto, 0,80 a 1,25."""

VIRGULA_ALTURA_MAXIMA = 0.65
"""Acima disso a barra inclinada é `/` de verdade: a vírgula vai a 0,56, e `/` e `l` começam em 1,0."""

VIRGULA_DESCIDA_MINIMA = 0.35
"""Fração da altura da caixa abaixo da linha de base. A vírgula passa de 0,5 quando é a barra."""

ARQUIVOS = "abcdefgh"


def e_traco_alto(altura: float, largura: float, xh: float) -> bool:
    """Esta caixa é um traço vertical, pela altura e pela proporção? `False` sem altura-de-x."""
    if xh <= 0 or altura <= 0:
        return False
    return altura / xh >= ALTURA_MINIMA and largura / altura <= PROPORCAO_MAXIMA


def e_virgula_de_barra(altura: float, descida: float, xh: float) -> bool:
    """Esta caixa, lida como traço, é a vírgula? Meia altura de letra e abaixo da linha de base."""
    if xh <= 0 or altura <= 0:
        return False
    return altura / xh <= VIRGULA_ALTURA_MAXIMA and descida / altura >= VIRGULA_DESCIDA_MINIMA


def _e_notacao_perto(palavra: Sequence[str], k: int) -> bool:
    """O traço está num número ou num lance? `11.`, `1.`, `Rf1`, `♖f1`: aí ele é `1`.

    Dígito de um dos lados basta. Sem dígito, só o lance que termina na casa da coluna: figurina ou
    letra de peça, depois a coluna, e o traço no fim. `of.` não é lance, e `Rf.` é.
    """
    vizinhos = [palavra[j] for j in (k - 1, k + 1) if 0 <= j < len(palavra)]
    if any(c and c[-1].isdigit() for c in vizinhos):
        return True
    if k != len(palavra) - 1 or k < 2:
        return False
    return palavra[k - 1] in ARQUIVOS and (
        palavra[k - 2] in "♔♕♖♗♘♙♚♛♜♝♞♟KQRBNDTCSLF" or palavra[k - 2] in "xX:"
    )


def escolher_letra(palavra: Sequence[str], k: int, lexico: frozenset[str]) -> str:
    """`l`, `I` ou `1` para o traço na posição `k` da palavra, pelo contexto.

    **O modelo não opina**: depois do resize os três são a mesma mancha. Sozinho na palavra, é o
    pronome `I`; entre maiúsculas, é `I`; no começo da palavra, o léxico separa `look` de `Informant`
    (`In` é curta demais para o léxico, então a regra é só sobre o que ele conhece); no resto, é `l`,
    que é onde um traço cai na prosa.
    """
    if _e_notacao_perto(palavra, k) and not conhecida_ou_curta("".join(palavra), lexico):
        return "1"
    letras = [c for j, c in enumerate(palavra) if j != k and c and c[0].isalpha()]
    if not letras:
        return "I"
    if k + 1 < len(palavra) and palavra[k + 1] and palavra[k + 1][0] in "'’":
        return "I"
    vizinhas = [palavra[j] for j in (k - 1, k + 1) if 0 <= j < len(palavra) and palavra[j] and palavra[j][0].isalpha()]
    if vizinhas and all(c.isupper() for c in vizinhas) and len(letras) >= 2:
        return "I"
    if k == 0 or not (palavra[k - 1] and palavra[k - 1][0].isalpha()):
        resto = "".join(palavra[k + 1 :]).split("-")[0]
        pre = "".join(palavra[:k])
        if not conhecida_ou_curta(f"{pre}l{resto}", lexico) and conhecida_ou_curta(f"{pre}i{resto}", lexico):
            return "I"
    return _l_ou_i(palavra, k, lexico)


def _l_ou_i(palavra: Sequence[str], k: int, lexico: frozenset[str]) -> str:
    """`l`, salvo se só o `i` faz palavra: em scan o pingo se perde, e `fixed` saía `f.xed`."""
    antes, depois = "".join(palavra[:k]), "".join(palavra[k + 1 :])
    if not conhecida_ou_curta(f"{antes}l{depois}", lexico) and conhecida_ou_curta(f"{antes}i{depois}", lexico):
        return "i"
    return "l"


def corrigir(
    lidos: Sequence[tuple[str, float]],
    probs: np.ndarray,
    caixas: Sequence[object],
    idx_to_char: dict[int, str],
    lexico: frozenset[str] = frozenset(),
    *,
    escala: float | None = None,
) -> list[tuple[str, float]]:
    """Devolve à caixa alta e estreita a letra que ela é, e à barra baixa a vírgula que ela é.

    A confiança devolvida é a da classe escolhida: trocar o caractere e manter a do palpite recusado
    diria que o programa tem certeza de algo sobre o que acabou de mudar de ideia.
    """
    saida = list(lidos)
    if not LIGADO or not lidos or len(lidos) != len(caixas):
        return saida

    from .dicionario import palavras

    de_char = {c: i for i, c in idx_to_char.items() if len(c) == 1}
    alturas = [float(c.altura) for c in caixas]  # type: ignore[attr-defined]
    xh = _caixa_alta.x_height_da_linha(alturas, [c for c, _ in lidos], escala=escala)
    base = float(np.median([c.y2 for c in caixas]))  # type: ignore[attr-defined]

    def por(k: int, novo: str) -> None:
        indice = de_char.get(novo)
        saida[k] = (novo, float(probs[k, indice]) if indice is not None and k < probs.shape[0] else 0.0)

    for inicio, fim in palavras(caixas, lidos):  # type: ignore[arg-type]
        palavra = [c for c, _ in saida[inicio:fim]]
        altos: list[int] = []
        for k in range(inicio, fim):
            char = saida[k][0]
            caixa = caixas[k]
            if char in TRACOS_DE_VIRGULA:
                descida = float(caixa.y2) - base  # type: ignore[attr-defined]
                if "," in de_char and e_virgula_de_barra(alturas[k], descida, xh):
                    por(k, ",")
                    palavra[k - inicio] = ","
            elif char in MARCAS and e_traco_alto(alturas[k], float(caixa.largura), xh):  # type: ignore[attr-defined]
                altos.append(k)
        # Primeiro todos viram `l`, para o contexto de cada um ser a palavra e não a mancha ao lado:
        # em `ca.cu.ate` e `wi..`, a vizinha de um traço é outro traço.
        for k in altos:
            palavra[k - inicio] = "l"
        for k in altos:
            novo = escolher_letra(palavra, k - inicio, lexico)
            por(k, novo)
            palavra[k - inicio] = novo
        _pronome_no_comeco(palavra, inicio, por, lexico)
    return saida


def _pronome_no_comeco(palavra: list[str], inicio: int, por: Callable[[int, str], None], lexico: frozenset[str]) -> None:
    """`lf` e `ln` que o modelo leu como `l`, e que só existem com `I` (S-730). `Hertan`: `If`->`lf`.

    Sem mexer na palavra que existe com `l`, e o léxico aqui não vale para a resposta longa: `like` não é
    `Iike`, porque `like` existe; `Iike` não existiria.
    """
    if len(palavra) < 2 or palavra[0] not in ("l", "1") or not all(len(c) == 1 and c.islower() for c in palavra[1:]):
        return
    resto = "".join(palavra[1:])
    if not conhecida_ou_curta(f"l{resto}", lexico) and conhecida_ou_curta(f"i{resto}", lexico):
        por(inicio, "I")


__all__ = [
    "ALTURA_MINIMA",
    "LIGADO",
    "MARCAS",
    "PROPORCAO_MAXIMA",
    "TRACOS_DE_VIRGULA",
    "VIRGULA_ALTURA_MAXIMA",
    "VIRGULA_DESCIDA_MINIMA",
    "corrigir",
    "e_traco_alto",
    "e_virgula_de_barra",
    "escolher_letra",
]
