"""As sugestões do léxico para uma palavra marcada, ordenadas pelo que o OCR erra (S-657).

**O léxico confere e não troca** (S-209): a sugestão só entra pelo clique da pessoa. O que este
módulo decide é a **ordem**, e ela é a única coisa que importa num menu de cinco: `p/ayer` tem de
oferecer `player` primeiro, e não `payer`, embora as duas estejam a uma troca de distância.

## A distância tem os pesos do OCR, e cada peso tem a página que o mediu

Uma distância de edição comum diz que `l`->`/` custa o mesmo que `l`->`q`. Para quem corrige OCR
não custa: a primeira é a confusão que o classificador de glifo faz em linha itálica, a segunda
quase nunca acontece. `TROCAS_DE_OCR` é a tabela, explícita, e uma troca dela custa
`PESO_DE_OCR` em vez de 1.

**Não é `text/semelhanca.py`**: aquele compara recortes de glifo pela imagem (S-213), e o documento
não carrega os recortes. Aqui só há a palavra lida e o léxico.

## Os candidatos são gerados, e não procurados

Medir a distância contra as ~200 mil palavras do léxico a cada clique seria segundo de espera. O
caminho é o de Norvig: gerar as variantes a uma edição (e as de OCR a duas) e ficar com as que o
léxico conhece. São algumas centenas de consultas a um `frozenset`, e o menu abre na hora.
"""

from __future__ import annotations

from collections.abc import Collection

__all__ = [
    "MAXIMO",
    "PESO_DE_OCR",
    "TROCAS_DE_OCR",
    "distancia",
    "sugestoes",
]

TROCAS_DE_OCR: tuple[tuple[str, str, str], ...] = (
    ("l", "/", "a barra no lugar do l em linha itálica (`text/italico.py`, S-211)"),
    ("rn", "m", "o par colado que vira uma letra (`text/colados.py`)"),
    ("tu", "m", "a barra do t encosta no u (`study`->`smdy`, a memória «tu fundido vira m»)"),
    ("c", "e", "o olho do e fechado pela binarização"),
    ("I", "l", "as hastes iguais na fonte sem serifa"),
    ("l", "1", "a haste e o um (`text/numeros.py`)"),
    ("I", "1", "a haste e o um, na caixa alta"),
    ("O", "0", "o círculo e o zero"),
    ("o", "0", "o círculo e o zero, na caixa baixa"),
)
"""As confusões que o OCR deste projeto faz, cada uma com onde ela foi vista. Valem nos dois sentidos."""

PESO_DE_OCR = 0.3
"""Quanto custa uma troca da tabela, contra 1 de uma edição comum. Abaixo de meio: duas trocas de
OCR ainda ficam à frente de uma edição qualquer, que é o que o caso `rn`+`l` pede."""

MAXIMO = 5
"""Quantas sugestões o menu mostra: as que cabem numa olhada sem rolagem."""

_LETRAS = "abcdefghijklmnopqrstuvwxyzáàâãéêíóôõúüçñš"


def _trocas_de_ocr(palavra: str) -> set[str]:
    """As palavras a uma troca de OCR de distância, nos dois sentidos da tabela."""
    saida: set[str] = set()
    for a, b, _onde in TROCAS_DE_OCR:
        for de, para in ((a, b), (b, a)):
            inicio = palavra.find(de)
            while inicio >= 0:
                saida.add(palavra[:inicio] + para + palavra[inicio + len(de) :])
                inicio = palavra.find(de, inicio + 1)
    return saida


def _uma_edicao(palavra: str) -> set[str]:
    """Apagar, trocar de lugar, trocar e inserir uma letra -- a vizinhança de Norvig."""
    pedacos = [(palavra[:i], palavra[i:]) for i in range(len(palavra) + 1)]
    apagadas = {e + d[1:] for e, d in pedacos if d}
    transpostas = {e + d[1] + d[0] + d[2:] for e, d in pedacos if len(d) > 1}
    trocadas = {e + c + d[1:] for e, d in pedacos if d for c in _LETRAS}
    inseridas = {e + c + d for e, d in pedacos for c in _LETRAS}
    return apagadas | transpostas | trocadas | inseridas


def distancia(origem: str, destino: str) -> float:
    """A distância de edição com os pesos de OCR. Pura, e simétrica como a tabela."""
    pares = {(a, b) for a, b, _ in TROCAS_DE_OCR} | {(b, a) for a, b, _ in TROCAS_DE_OCR}
    linhas, colunas = len(origem), len(destino)
    custo = [[0.0] * (colunas + 1) for _ in range(linhas + 1)]
    for i in range(linhas + 1):
        custo[i][0] = float(i)
    for j in range(colunas + 1):
        custo[0][j] = float(j)
    for i in range(1, linhas + 1):
        for j in range(1, colunas + 1):
            igual = origem[i - 1] == destino[j - 1]
            melhor = min(
                custo[i - 1][j] + 1,
                custo[i][j - 1] + 1,
                custo[i - 1][j - 1] + (0.0 if igual else (PESO_DE_OCR if (origem[i - 1], destino[j - 1]) in pares else 1.0)),
            )
            # As trocas de duas letras por uma (`rn`->`m`) e de uma por duas.
            for a, b in pares:
                if len(a) > 1 and i >= len(a) and origem[i - len(a) : i] == a and destino[j - len(b) : j] == b and j >= len(b):
                    melhor = min(melhor, custo[i - len(a)][j - len(b)] + PESO_DE_OCR)
            custo[i][j] = melhor
    return custo[linhas][colunas]


def sugestoes(palavra: str, lexico: Collection[str], *, maximo: int = MAXIMO) -> tuple[str, ...]:
    """Até `maximo` palavras do léxico perto daquela, da mais perto à mais longe. Vazio sem nenhuma.

    A caixa da palavra lida é mantida na sugestão: `P/ayer` sugere `Player`. O léxico é consultado
    em caixa baixa, como `dicionario.desconhecidas` o consulta.
    """
    if not palavra:
        return ()
    baixa = palavra.lower()
    perto = _trocas_de_ocr(palavra) | {t.lower() for t in _trocas_de_ocr(palavra)}
    segunda = {s for p in list(perto) for s in _trocas_de_ocr(p)}
    candidatas = perto | segunda | _uma_edicao(baixa)
    conhecidas = {c for c in candidatas if c.lower() in lexico and c.lower() != baixa}
    unicas: dict[str, str] = {}
    for candidata in conhecidas:
        unicas.setdefault(candidata.lower(), candidata)
    ordenadas = sorted(unicas.values(), key=lambda c: (distancia(baixa, c.lower()), c.lower()))
    return tuple(_na_caixa_de(palavra, c) for c in ordenadas[:maximo])


def _na_caixa_de(original: str, sugestao: str) -> str:
    if original.isupper() and len(original) > 1:
        return sugestao.upper()
    if original[:1].isupper():
        return sugestao[:1].upper() + sugestao[1:].lower()
    return sugestao.lower()
