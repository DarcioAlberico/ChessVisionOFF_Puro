"""Maiúscula ou minúscula, decidido pela **altura** e não pela forma (S-211).

**O problema é do pré-processamento, e não do modelo.** `ClassificadorDeGlifo._entrada` faz
`cv2.resize(recorte, (32, 32))` em todo glifo, e oito letras do alfabeto latino têm maiúscula e
minúscula com a **mesma forma**, mudando só o tamanho:

    c C   o O   s S   u U   v V   w W   x X   z Z

Depois do resize as duas são a mesma imagem. O modelo não erra por ser fraco: ele erra porque a
informação que decide foi apagada antes de ele ver o recorte.

## O tamanho da coisa, medido

Em 13 páginas de 3 livros de camada **editorada** (Dvoretsky 2025, Capablanca pt-br, Fischer
pt-br), 212 linhas casadas contra a camada, 617 substituições:

    ♔->K, ♖->R, ♕->Q          192    não é erro: o glifo acerta a figurina, a camada usa ASCII
    caixa alta (S->s, V->v…)  ~241    <- isto
    caractere espúrio           ~96
    0->o                          3

E duas medições fecham o caso:

- **a classe certa está em rank 2 em 237 de 237 casos.** Não "quase sempre": todos. O modelo diz
  `S` com 0,96 e `s` com 0,03, sempre nessa ordem. Não há o que aprender -- há o que **escolher**;
- **a altura separa.** Minúscula mede 1,00 da mediana de altura da linha; maiúscula, 1,41.

E o ganho ponta a ponta, medido em 11 páginas de 4 livros pelo caminho de produção
(`docs/metrics/texto_caixa_alta.json`):

    CER 0,1434 -> 0,1114   (-22,3%)   11 páginas melhoram, nenhuma piora, sem custo de tempo

É o maior ganho medido deste subpacote, e é o único dos três interruptores da página que entra
**ligado** -- o modo bloco da S-188 e o separador da S-186 foram medidos e não pagam.

**O caminho da faixa de legenda não usa isto.** A correção mora em `text/leitor.py`, e não em
`GlyphRecognizer.read`: os números publicados da legenda continuam descrevendo o que roda lá.

## Por que o critério é a mediana da linha, e não a escala da página

`boxes.escala_de_texto` é medida por massa de tinta e cai perto da **altura de maiúscula** -- é a
mesma razão pela qual `unir_pingos` usa a mediana das caixas presentes em vez da escala. Aqui a
régua tem de ser a **x-height**, e a mediana das alturas de uma linha de prosa é dominada por
minúscula, que é o que a torna uma boa aproximação dela.

**Por linha, e nunca pela página.** Um título em corpo maior tem x-height maior, e comparar as
letras dele com a mediana da página os promoveria todos a maiúscula.

## O que este módulo não faz

Não decide `l` contra `1`, nem `0` contra `o`: essas trocam **entre alfabetos**, e altura não as
separa (`l` e `1` têm a mesma altura). Elas são da S-209.

## A régua que a mediana não dava (S-731)

Nas 27 folhas dos 5 livros aprovados do ouro-dev, depois de tudo acima, a família caixa ainda tinha 59
palavras, e **o modelo estava certo em quase todas**: em `White`->`white`, o `W` vinha com 0,99 e era a
régua de altura que o derrubava. A mediana das alturas só é a altura-de-x em linha de prosa. Em linha
com notação, dígito e maiúscula, ela sobe para a altura de maiúscula (`h/mediana` de 1,00 a 1,19 num `W`
de verdade), e na linha toda em maiúscula ela **é** a altura de maiúscula: `DEFEsA`.

Medindo contra as letras que não têm haste nem acento, e que o modelo não confunde (`LETRAS_DE_X`):

    maiúscula ambígua certa, 139    p1 1,32    mediana 1,50    p99 1,58
    minúscula ambígua certa, 4.992  p1 0,94    mediana 1,00    p99 1,06

**O vão vai de 1,06 a 1,32**, e o corte de 1,25 continua no meio dele. Sobram dois casos sem letra de x
na linha: a toda em maiúscula, que se mede pelas altas seguras (`RAZAO_ALTA_X`), e a linha de um só
sinal (`W`, `W?`), que se mede pela escala da folha.

**Versalete é outro problema, e é da palavra.** `'UNUSUAL SQUARES'` em versalete tem altura de letra de
x, e nenhuma régua de altura o separa: a palavra toda é que diz (`coerente`).

## A cedilha e o P, que também são tamanho (S-731, S-735)

`ç` era lido `C`: o modelo diz `c` a 0,6 e `ç` a 0,3, e a cedilha estica a caixa, que então passa do
corte. Descida da caixa abaixo da linha de base, em alturas-de-x:

    ç (certo ou lido C/c), 61     0,38 a 0,50
    C certo, 69                  -0,04 a 0,06
    c certo, 797                  0,00 a 0,05

`P` era lido `p` em *Minhas 60* (Calibri, 11 casos, `P` em rank 2 a 0,08): esticados, são o mesmo
desenho, e quem os separa é a descida do `p`, que o `P` não tem.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

AMBIGUAS = "cosuvwxz"
"""As letras cuja maiúscula e minúscula têm a mesma forma, mudando só o tamanho.

**Oito, e a lista é fechada por inspeção do alfabeto, não por medição.** `k` e `y` quase entram --
a minúscula tem haste que sobe ou desce, e isso muda a forma o bastante para o modelo. As oito
daqui não têm nenhuma diferença de desenho em fonte de texto comum."""

XH_COERENTE = True
"""A reversão da régua de letras de x (S-731). Desligada, volta a mediana da linha inteira."""

LETRAS_DE_X = "aemnr"
"""Sem haste, sem descida, sem acento, e com a maiúscula de outro desenho: o modelo não as confunde."""

MIN_LETRAS_DE_X = 2
"""Com menos que isto na linha, a altura delas é ruído de uma caixa só."""

ALTAS_SEGURAS = "ABDEFGHKLMNPRTbdfhkl0123456789"
"""Altura de maiúscula ou de haste, e a forma não muda com a caixa de ninguém."""

RAZAO_ALTA_X = 1.40
"""Altura de maiúscula sobre altura-de-x, para a linha sem letra de x. Dos livros dev: Arial 1,38,
Calibri 1,38, Times 1,47, Cambria 1,45. Só precisa cair longe do corte: minúscula ambígua fica em 0,65 a
0,75 da alta segura, e maiúscula, em 1,00 a 1,17, com o corte em 0,89."""

PALAVRA_COERENTE = True
"""A reversão de `coerente` (S-731)."""

MINUSCULAS_QUE_ABSOLVEM = 2
"""Quantas minúsculas depois da ambígua dizem que ela é maiúscula de verdade: `ChessCafe`, `McClure`.

`IvanchUk` e `teU` têm uma ou nenhuma, e é esse o erro que a regra desfaz. Foi o crítico da Fase 103 quem
achou o outro lado, fora do dev."""

PREFIXOS_DE_NOME = ("Mc", "Mac")
"""A maiúscula no meio que é do nome, mesmo curta: `McCoy` passaria pela regra acima, `McOy` não."""

MIN_LETRAS_DO_S_FINAL = 5
"""Abaixo disto, o `s` final não sobe: `GMs` é plural de sigla, com 19 ocorrências num livro só."""

MIN_MAIUSCULAS_DA_PALAVRA = 2
"""Quantas maiúsculas de desenho próprio bastam para dizer que a palavra é toda em maiúscula."""

CEDILHA_PELA_DESCIDA = True
"""A reversão da cedilha (S-735)."""

DESCIDA_DA_CEDILHA = 0.25
"""Em alturas-de-x abaixo da linha de base. `C` e `c` vão até 0,06, e `ç` começa em 0,38."""

PISO_DA_CEDILHA = 0.01
"""A classe `ç` tem de estar entre as opções do modelo: `ç` tem 93 amostras, e ele a vê."""

P_PELA_DESCIDA = True
"""A reversão do `P` (S-731)."""

DESCIDA_DO_P = 0.10
"""Fração da altura da caixa. O `p` lido errado que era `P` fica em 0,00; o `p` de verdade passa de 0,2."""

SEGUNDO_CORTE = True
"""A reversão do corte da família acentuada (S-735)."""

AMBIGUAS_ACENTUADAS = "íóõöúćčšž"
"""As acentuadas de mesma forma. `á ã ä å è é` mudam de desenho; `ý` tem a haste, como `y`."""

CORTE_ACENTUADA = 1.65
"""A minúscula acentuada mede até 1,46 com o acento dentro do bbox, e a maiúscula, cerca de 1,85.

**As classes de cima quase não têm amostra**, e é por isso que ela é regra de geometria: `Õ` 1, `Ú` 1,
`Ó` 3, `Ć` 3, `Č` 3, `ö` 3, `ž` 2, `Ž` 1, `Ö` 5, `š` 7, `Š` 9 em `training_data/`. O que o modelo
responde nessas classes é ruído, e nenhum número aqui fala do modelo."""

CORTE_DE_CAIXA = 1.25
"""Acima de tantas x-heights, a caixa é alta. Medido em 1.026 casos: separa 99,4%.

**A amostra dos dois lados é muito desigual, e o número acima esconde isso**: são 1.001 minúsculas
contra 25 maiúsculas, porque prosa é quase toda minúscula. O que está bem medido é que minúscula
fica em 1,00; o corte alto o bastante para não rebaixar maiúscula legítima está medido em 25
casos, e é aí que este número pode estar errado. Ver `docs/metrics/texto_caixa_alta.json`."""


def x_height(alturas: Sequence[int]) -> float:
    """A x-height da linha, aproximada pela **mediana** das alturas de box. `0.0` sem boxes.

    Mediana e não média: uma linha com dois parênteses altos e uma vírgula baixa move a média e
    não move a mediana. É a mesma escolha de `unir_pingos`, e pelo mesmo motivo.
    """
    if not alturas:
        return 0.0
    return float(np.median(np.asarray(alturas, dtype=np.float64)))


def x_height_da_linha(
    alturas: Sequence[float], chars: Sequence[str], *, escala: float | None = None
) -> float:
    """A altura-de-x pelas letras que a medem (S-731). `x_height` quando a régua está desligada.

    Na ordem: a mediana das letras de x; sem elas, a das altas seguras dividida pela razão de sempre;
    sem nenhuma das duas, a escala da folha, que cai perto da altura de maiúscula; e, sem escala, a
    mediana da linha.
    """
    if not XH_COERENTE:
        return x_height(alturas)  # type: ignore[arg-type]
    pares = list(zip(alturas, chars, strict=False))
    de_x = [h for h, c in pares if c in LETRAS_DE_X]
    if len(de_x) >= MIN_LETRAS_DE_X:
        return float(np.median(de_x))
    altas = [h for h, c in pares if c in ALTAS_SEGURAS]
    if altas:
        return float(np.median(altas)) / RAZAO_ALTA_X
    if escala:
        return float(escala) / RAZAO_ALTA_X
    return x_height(alturas)  # type: ignore[arg-type]


def pares_de_caixa(idx_to_char: dict[int, str]) -> dict[int, int]:
    """`{índice de classe: índice da mesma letra na outra caixa}`, só para as ambíguas.

    Só entra o par **completo**: uma classe cuja contraparte não existe no modelo fica de fora, e
    não vira meia-regra. Classes de ligadura (`fi`, `Bl`) nunca entram -- elas têm mais de um
    caractere, e a altura de uma ligadura não diz nada sobre a caixa dela.
    """
    de_char = {c: i for i, c in idx_to_char.items() if len(c) == 1}
    pares: dict[int, int] = {}
    for letra in AMBIGUAS:
        baixa, alta = de_char.get(letra), de_char.get(letra.upper())
        if baixa is None or alta is None:
            continue
        pares[baixa] = alta
        pares[alta] = baixa
    return pares


def caixa_pela_altura(altura: float, xh: float, *, corte: float | None = None) -> bool:
    """Este box é caixa alta? `False` quando não há x-height -- ver `decidir`.

    **`corte=None` lê `CORTE_DE_CAIXA` na hora da chamada, e isso é o item.** Escrever
    `corte: float = CORTE_DE_CAIXA` na assinatura amarra o valor no momento em que o módulo é
    importado: quem depois muda a constante -- uma varredura de limiar, um teste -- muda um número
    que ninguém mais lê, e a varredura sai com todas as linhas iguais. Foi exatamente o que
    aconteceu na primeira medição deste item, e o defeito só apareceu porque sete cortes
    diferentes deram o mesmo CER até o quarto decimal.
    """
    if xh <= 0:
        return False
    return altura / xh >= (CORTE_DE_CAIXA if corte is None else corte)


def decidir(
    probs: np.ndarray,
    alturas: Sequence[int],
    idx_to_char: dict[int, str],
    *,
    corte: float | None = None,
    pares: dict[int, int] | None = None,
    caixas: Sequence[object] | None = None,
    escala: float | None = None,
) -> list[tuple[str, float]]:
    """`(caractere, confiança)` por box, com a caixa das ambíguas decidida pela altura.

    **Restringe o decodificador, e não a saída.** Onde a altura contradiz o argmax, a escolha passa
    para a outra classe do par e a confiança devolvida é a **dela** -- que é o que a torna honesta:
    trocar o caractere e manter os 0,96 do palpite recusado diria que o programa tem certeza de
    algo que ele acabou de mudar de ideia sobre. É a mesma decisão de `GlyphRecognizer`, que tira
    as colunas proibidas da matriz **antes** do argmax; o critério aqui é por box, e não por faixa.

    O que ela **não** faz: mexer em box que não é letra ambígua, e mexer em linha sem x-height.
    Fora as ambíguas, o resultado é `argmax` puro -- byte a byte o que o classificador daria.

    `caixas` e `escala` são da S-731: sem elas, a régua é a das letras de x da linha, e a cedilha, o
    `P` e o segundo corte, que olham a linha de base, não decidem.
    """
    if probs.size == 0:
        return []
    if pares is None:
        pares = pares_de_caixa(idx_to_char)
    argmax = [idx_to_char[int(probs[k].argmax())] for k in range(probs.shape[0])]
    xh = x_height_da_linha(alturas, argmax, escala=escala)
    base = None
    if caixas:
        base = float(np.median([c.y2 for c in caixas]))  # type: ignore[attr-defined]
    de_char = {c: i for i, c in idx_to_char.items() if len(c) == 1}
    acentuadas = _pares_acentuados(de_char) if SEGUNDO_CORTE else {}

    saida: list[tuple[str, float]] = []
    for linha in range(probs.shape[0]):
        escolhido = int(probs[linha].argmax())
        outro = pares.get(escolhido)
        if outro is not None and linha < len(alturas):
            alta = caixa_pela_altura(float(alturas[linha]), xh, corte=corte)
            desejado = outro if idx_to_char[escolhido].isupper() != alta else escolhido
            escolhido = desejado
        elif escolhido in acentuadas and linha < len(alturas):
            alta = caixa_pela_altura(float(alturas[linha]), xh, corte=CORTE_ACENTUADA)
            escolhido = acentuadas[escolhido] if idx_to_char[escolhido].isupper() != alta else escolhido
        if base is not None and linha < len(caixas or ()) and linha < len(alturas):
            descida = float(caixas[linha].y2) - base  # type: ignore[index,union-attr,attr-defined]
            escolhido = _pela_descida(escolhido, descida, float(alturas[linha]), xh, probs[linha], idx_to_char, de_char)
        saida.append((idx_to_char[escolhido], float(probs[linha, escolhido])))
    return saida


def _pares_acentuados(de_char: dict[str, int]) -> dict[int, int]:
    """Os pares completos de `AMBIGUAS_ACENTUADAS`. Como em `pares_de_caixa`, meia-regra não entra."""
    pares: dict[int, int] = {}
    for letra in AMBIGUAS_ACENTUADAS:
        baixa, alta = de_char.get(letra), de_char.get(letra.upper())
        if baixa is not None and alta is not None:
            pares[baixa] = alta
            pares[alta] = baixa
    return pares


def _pela_descida(
    escolhido: int,
    descida: float,
    altura: float,
    xh: float,
    probs: np.ndarray,
    idx_to_char: dict[int, str],
    de_char: dict[str, int],
) -> int:
    """A cedilha desce, e o `P` não: as duas decisões que só a linha de base toma."""
    char = idx_to_char[escolhido]
    if xh <= 0:
        return escolhido
    if CEDILHA_PELA_DESCIDA and char in "cC" and descida / xh >= DESCIDA_DA_CEDILHA:
        cedilha = de_char.get("ç")
        if cedilha is not None and float(probs[cedilha]) >= PISO_DA_CEDILHA:
            return cedilha
    if P_PELA_DESCIDA and char == "p" and altura > 0 and altura / xh >= CORTE_DE_CAIXA:
        maiuscula = de_char.get("P")
        if maiuscula is not None and descida / altura < DESCIDA_DO_P:
            return maiuscula
    return escolhido


def coerente(
    lidos: Sequence[tuple[str, float]],
    probs: np.ndarray,
    caixas: Sequence[object],
    idx_to_char: dict[int, str],
) -> list[tuple[str, float]]:
    """A palavra toda em maiúscula não ganha minúscula no meio (S-731). `DEFEsA`, `FcM`, `uNusuAL`.

    Olha as letras de desenho próprio da palavra: se há ao menos `MIN_MAIUSCULAS_DA_PALAVRA` maiúsculas e
    nenhuma minúscula, as ambíguas, o `p` e o `l` sobem. É o que resolve o **versalete**, em que a altura
    não separa nada, e é por isso que esta regra não olha altura.

    **Só palavra de letras.** Com dígito ou figurina ela é lance, e `Nc3` não é palavra em maiúscula. E
    `x` entre duas peças é captura: `KxR` e `QxB` são notação, então o `x` só sobe em palavra de quatro
    letras ou mais.

    **E o lance que a régua de altura estragou volta**, em `_lance_em_minuscula`: em scan, as letras de x
    comidas fazem `c` e `x` passarem do corte.
    """
    saida = list(lidos)
    if not PALAVRA_COERENTE or not lidos or len(lidos) != len(caixas):
        return saida

    from .dicionario import palavras

    de_char = {c: i for i, c in idx_to_char.items() if len(c) == 1}
    sobem = {c: c.upper() for c in AMBIGUAS + "p"}
    sobem["l"] = "I"

    def por(k: int, novo: str) -> None:
        indice = de_char.get(novo)
        if indice is not None and k < probs.shape[0]:
            saida[k] = (novo, float(probs[k, indice]))

    for inicio, fim in palavras(caixas, lidos):  # type: ignore[arg-type]
        # Antes de olhar ligadura: `Qxf7` chega com `f7` numa caixa só.
        _lance_em_minuscula(saida, inicio, fim, por)
        trecho = [c for c, _ in saida[inicio:fim]]
        if any(len(c) != 1 for c in trecho):
            continue
        tem_lance = any(c.isdigit() or ord(c) >= 0x2654 for c in trecho)
        for k in range(inicio + 1, fim):
            # A ambígua depois de minúscula, em palavra sem dígito: `IvanchUk`, `teU`.
            if saida[k][0] in AMBIGUAS.upper() and saida[k - 1][0].islower() and not tem_lance:
                depois = trecho[k + 1 - inicio : k + 1 - inicio + MINUSCULAS_QUE_ABSOLVEM]
                absolvida = len(depois) == MINUSCULAS_QUE_ABSOLVEM and all(c.islower() for c in depois)
                if not absolvida and not "".join(trecho[: k - inicio]).lstrip("'\"(").startswith(PREFIXOS_DE_NOME):
                    por(k, saida[k][0].lower())
        trecho = [c for c, _ in saida[inicio:fim]]
        if tem_lance:
            continue
        letras = [c for c in trecho if c.isalpha()]
        proprias = [c for c in letras if c.casefold() not in sobem and c != "I"]
        if len(letras) < 3 or any(c.islower() for c in proprias):
            continue
        if sum(c.isupper() for c in proprias) < MIN_MAIUSCULAS_DA_PALAVRA:
            continue
        ultima_letra = max(k for k in range(inicio, fim) if saida[k][0].isalpha())
        for k in range(inicio, fim):
            char = saida[k][0]
            if char not in sobem or (char == "x" and len(letras) < 4):
                continue
            if char == "s" and k == ultima_letra and len(letras) < MIN_LETRAS_DO_S_FINAL:
                continue
            por(k, sobem[char])
    return saida


def _lance_em_minuscula(
    saida: list[tuple[str, float]], inicio: int, fim: int, por: Callable[[int, str], None]
) -> None:
    """`QXf7`->`Qxf7`, `NXa2`->`Nxa2`, e a coluna `KC5`->`Kc5`, `C2`->`c2`: maiúscula aí não é lance de ninguém.

    A coluna exige o dígito de casa e nenhuma letra depois dele: `C3A` é descritiva, e `Cc3` tem o `c` certo. O
    `X` exige a casa inteira depois, numa caixa (`f7`) ou em duas: `TEXas` e `TXPTR` ficam.
    """
    for k in range(inicio, fim):
        char = saida[k][0]
        proximos = [c for c, _ in saida[k + 1 : min(fim, k + 3)]]
        if char == "X" and k > inicio and proximos and proximos[0][:1] in tuple("abcdefgh"):
            if len(proximos[0]) == 2 or (len(proximos) == 2 and proximos[1][:1] in tuple("12345678")):
                por(k, "x")
        elif char == "C" and proximos and proximos[0] in tuple("12345678"):
            depois_e_letra = len(proximos) == 2 and proximos[1][:1].isalpha()
            antes = saida[k - 1][0][-1:] if k > inicio else ""
            if not depois_e_letra and (not antes or not antes.isalpha() or antes in "KQRBNDTCSLFP"):
                por(k, "c")


__all__ = [
    "AMBIGUAS",
    "AMBIGUAS_ACENTUADAS",
    "CEDILHA_PELA_DESCIDA",
    "CORTE_ACENTUADA",
    "CORTE_DE_CAIXA",
    "LETRAS_DE_X",
    "PALAVRA_COERENTE",
    "P_PELA_DESCIDA",
    "SEGUNDO_CORTE",
    "XH_COERENTE",
    "caixa_pela_altura",
    "coerente",
    "decidir",
    "pares_de_caixa",
    "x_height",
    "x_height_da_linha",
]
