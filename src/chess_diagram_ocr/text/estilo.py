"""O estilo da palavra pela imagem: o conjunto rotulado, o classificador e o portão (Fase 96, S-661 a S-663).

**A pergunta é a mesma de `text/negrito.py`, com outra ferramenta.** Lá a geometria do traço foi
medida em 20.156 palavras de 14 livros e recusada: a melhor precisão utilizável era 0,839, e apertar
o corte não comprava precisão. A Fase 96 (`docs/ROADMAP_MESA_DE_TEXTO.md`) reabre a pergunta com uma
rede pequena e o mesmo tipo de portão -- se não passar, a recusa volta com o número novo.

## O rótulo é metadado, e só vem da folha tipográfica

A palavra é rotulada pelo **nome da fonte ou o bit** do span da camada (`negrito._span_e_negrito`,
`italico._span_e_italico`), e só em folha cuja camada é a tipografia de quem editou o livro
(`camada.camada_tipografica`): a camada de um scan é o palpite de outro OCR, e treinar nela seria
aprender o erro dele. A palavra que mistura estilo dentro de si fica fora -- ela não tem uma classe.

## O livro é a unidade da divisão, e a identidade é pelo conteúdo

O acervo tem o mesmo livro em dois arquivos (`_hq`, `- Copia`), e a identidade da S-610 -- o resumo
do primeiro MiB -- não os junta: os bytes são outros. Aqui a identidade é o **texto**: as sequências
de cinco palavras de uma amostra de folhas, e dois arquivos que dividem mais de `PARENTESCO` delas são
o mesmo livro. Sem isso o mesmo livro cai no treino e no teste, e a medida fora do livro mente.

## O que este módulo não faz

Não lê PDF nem treina: as funções aqui são puras (ou só tocam `numpy`), e quem coleta e quem treina
são `cli/texto_estilo_conjunto.py` e `cli/texto_estilo_classificador.py`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

CLASSES: tuple[str, ...] = ("normal", "negrito", "italico", "negrito-italico")
"""As quatro classes da S-661, na ordem dos índices da rede."""

ALTURA = 32
LARGURA_MAXIMA = 192
"""A entrada da rede: a palavra em altura fixa, e a largura até o teto -- a palavra mais larga é
**cortada** à direita, e não espremida, porque espremer muda a espessura aparente do traço, que é
exatamente o que a rede tem de ler."""

PARENTESCO = 0.3
"""A partir de que fração de sequências de cinco palavras em comum dois arquivos são o mesmo livro.
Duas edições do mesmo texto dividem quase tudo; dois livros diferentes, quase nada (notação de
abertura repetida é o que sobra, e ela não chega a um décimo)."""

PARTICOES: dict[str, float] = {"treino": 0.7, "validacao": 0.1, "teste": 0.2}

REGUA_DE_APLICAR = 0.9929
"""Precisão por classe para aplicar sem perguntar: a régua de lote do projeto (S-213)."""

REGUA_DE_SUGERIR = 0.95
COBERTURA_DE_SUGERIR = 0.50
"""Precisão por classe e cobertura para sugerir (R4): uma sugestão errada a cada vinte, que a
pessoa recusa com um clique, e ao menos metade do estilo de verdade sugerido. Números de produto, e
quem os escolhe é o dono (R4); estes são os propostos."""

_PALAVRA_UTIL = re.compile(r"[^\W_]")


def rotulo(negrito: bool, italico: bool) -> str:
    """A classe de uma palavra pelos dois bits. Pura."""
    return CLASSES[int(negrito) + 2 * int(italico)]


@dataclass(frozen=True)
class PalavraDeCamada:
    """Uma palavra da camada: o texto, a caixa em pontos e a classe, ou `None` quando mistura."""

    texto: str
    bbox: tuple[float, float, float, float]
    classe: str | None


def palavras_de_caracteres(
    caracteres: Iterable[tuple[str, tuple[float, float, float, float], bool, bool]],
) -> list[PalavraDeCamada]:
    """Junta os caracteres de **uma linha** em palavras, pelo espaço. Pura.

    Cada caractere é `(letra, bbox, negrito, itálico)`. A palavra que tem caractere de dois estilos
    sai com `classe=None` -- quem coleta a joga fora --, e a que não tem letra nem algarismo (`--`,
    `!?`) nem entra: ela não tem traço bastante para se ler peso nela.
    """
    palavras: list[PalavraDeCamada] = []
    atual: list[tuple[str, tuple[float, float, float, float], bool, bool]] = []

    def fechar() -> None:
        if not atual:
            return
        texto = "".join(c[0] for c in atual)
        if len(texto) >= 2 and _PALAVRA_UTIL.search(texto):
            estilos = {(c[2], c[3]) for c in atual}
            classe = rotulo(*next(iter(estilos))) if len(estilos) == 1 else None
            caixa = (
                min(c[1][0] for c in atual),
                min(c[1][1] for c in atual),
                max(c[1][2] for c in atual),
                max(c[1][3] for c in atual),
            )
            palavras.append(PalavraDeCamada(texto, caixa, classe))
        atual.clear()

    for caractere in caracteres:
        if caractere[0].isspace():
            fechar()
        else:
            atual.append(caractere)
    fechar()
    return palavras


# --------------------------------------------------------------------------- a identidade do livro


def sequencias(texto: str, n: int = 5) -> frozenset[str]:
    """As sequências de `n` palavras do texto, em minúsculas e sem pontuação. Pura."""
    palavras = re.findall(r"[^\W_]+", texto.casefold())
    return frozenset(" ".join(palavras[i : i + n]) for i in range(max(0, len(palavras) - n + 1)))


def parentesco(a: frozenset[str], b: frozenset[str]) -> float:
    """A fração do menor conjunto que o outro também tem. Pura.

    Do menor, e não Jaccard: a amostra de folhas de um arquivo de 300 folhas e a de um de 150 do
    mesmo livro não caem nas mesmas folhas, e o que importa é se o que um tem o outro também tem.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def identidades(textos: Mapping[str, frozenset[str]], *, corte: float = PARENTESCO) -> dict[str, str]:
    """`arquivo -> identidade do livro`, juntando os arquivos aparentados. Pura.

    A identidade é um resumo do nome do primeiro arquivo do grupo em ordem alfabética: estável entre
    corridas enquanto o acervo não muda, e curta o bastante para o manifesto.
    """
    nomes = sorted(textos)
    pai = {nome: nome for nome in nomes}

    def raiz(nome: str) -> str:
        while pai[nome] != nome:
            pai[nome] = pai[pai[nome]]
            nome = pai[nome]
        return nome

    for i, a in enumerate(nomes):
        for b in nomes[i + 1 :]:
            if parentesco(textos[a], textos[b]) > corte:
                ra, rb = raiz(a), raiz(b)
                if ra != rb:
                    pai[max(ra, rb)] = min(ra, rb)
    return {nome: hashlib.sha1(raiz(nome).encode("utf-8")).hexdigest()[:12] for nome in nomes}


def particionar(contas: Mapping[str, Mapping[str, int]], alvo: Mapping[str, float] = PARTICOES) -> dict[str, str]:
    """`identidade -> partição`, com cada livro inteiro numa partição só. Pura.

    `contas` é `identidade -> classe -> palavras`. Guloso e determinístico: os livros em ordem de
    identidade, cada um para a partição que mais se aproxima do alvo **em cada classe** -- o itálico
    mora em poucos livros, e uma divisão que olhasse só o total podia deixar o teste sem itálico, e o
    portão sem o que medir.
    """
    totais = {c: sum(conta.get(c, 0) for conta in contas.values()) for c in CLASSES}
    tem = {p: dict.fromkeys(CLASSES, 0) for p in alvo}
    saida: dict[str, str] = {}
    for identidade in sorted(contas, key=lambda i: (-sum(contas[i].values()), i)):
        conta = contas[identidade]

        def custo(particao: str, conta: Mapping[str, int] = conta) -> float:
            erro = 0.0
            for p, fracao in alvo.items():
                for c in CLASSES:
                    if not totais[c]:
                        continue
                    depois = tem[p][c] + (conta.get(c, 0) if p == particao else 0)
                    erro += (depois / totais[c] - fracao) ** 2
            return erro

        escolhida = min(alvo, key=lambda p: (custo(p), list(alvo).index(p)))
        saida[identidade] = escolhida
        for c in CLASSES:
            tem[escolhida][c] += conta.get(c, 0)
    return saida


# --------------------------------------------------------------------------------- a imagem


def normalizar(cinza: np.ndarray) -> tuple[np.ndarray, int]:
    """A palavra em `ALTURA` de altura, cortada ou completada a `LARGURA_MAXIMA` com papel. Pura.

    Devolve a imagem `uint8` (tinta escura, papel claro, como a folha) e a largura útil antes do
    papel acrescentado.
    """
    import cv2

    altura, largura = cinza.shape[:2]
    if altura == 0 or largura == 0:
        return np.full((ALTURA, LARGURA_MAXIMA), 255, np.uint8), 0
    nova = max(1, round(largura * ALTURA / altura))
    redimensionada = cv2.resize(cinza, (nova, ALTURA), interpolation=cv2.INTER_AREA)
    util = min(nova, LARGURA_MAXIMA)
    saida = np.full((ALTURA, LARGURA_MAXIMA), 255, np.uint8)
    saida[:, :util] = redimensionada[:, :util]
    return saida, util


def degradar(cinza: np.ndarray, aleatorio: np.random.Generator) -> np.ndarray:
    """As quatro degradações da S-661, cada uma com metade de chance, sobre o recorte **antes** de normalizar.

    Imitam o scan, que é a população-alvo: reamostrar a metade da resolução e voltar (o livro
    digitalizado a 150 dpi), desfoque leve, ruído de pontos e binarização com limiar sorteado. Nenhuma
    engrossa nem afina o traço de propósito -- a `espessura` de `text/aumento.py` fica de fora,
    porque ela muda justamente o rótulo.
    """
    import cv2

    img: np.ndarray = cinza.astype(np.uint8)
    altura, largura = img.shape[:2]
    if aleatorio.random() < 0.5 and altura >= 4 and largura >= 4:
        pequena = cv2.resize(img, (max(1, largura // 2), max(1, altura // 2)), interpolation=cv2.INTER_AREA)
        img = cv2.resize(pequena, (largura, altura), interpolation=cv2.INTER_LINEAR)
    if aleatorio.random() < 0.5:
        sigma = float(aleatorio.uniform(0.3, 0.9))
        img = cv2.GaussianBlur(img, (0, 0), sigma)
    if aleatorio.random() < 0.5:
        pontos = aleatorio.random(img.shape) < float(aleatorio.uniform(0.002, 0.01))
        img = img.copy()
        img[pontos] = np.where(aleatorio.random(int(pontos.sum())) < 0.5, 0, 255).astype(np.uint8)
    if aleatorio.random() < 0.5:
        limiar = int(aleatorio.integers(100, 190))
        img = np.where(img < limiar, 0, 255).astype(np.uint8)
    return img


# ------------------------------------------------------------------------------- as réguas


def chutar_pela_altura(alturas_treino: Sequence[float], classes_treino: Sequence[str], alturas: Sequence[float]) -> list[str]:
    """O controle da S-663: `negrito` acima de um corte de altura aprendido no treino, `normal` abaixo. Pura.

    É a régua que a geometria não tinha feito na primeira vez e que custou o primeiro resultado: se o
    classificador não vencer isto, aprendeu o tamanho, e não o peso.
    """
    pares = sorted(zip(alturas_treino, classes_treino, strict=True))
    melhor, corte = -1, float("inf")
    candidatos = sorted({a for a, _ in pares})
    for limite in [*candidatos, float("inf")]:
        acertos = sum(1 for a, c in pares if (c == "negrito") == (a >= limite))
        if acertos > melhor:
            melhor, corte = acertos, limite
    return ["negrito" if a >= corte else "normal" for a in alturas]


def acerto(previsto: Sequence[str], verdade: Sequence[str]) -> float:
    """A fração de acertos. Pura."""
    if not verdade:
        return 0.0
    return sum(1 for p, v in zip(previsto, verdade, strict=True) if p == v) / len(verdade)


@dataclass(frozen=True)
class Regua:
    """O que uma classe dá sob um corte de confiança: quantas marcadas, quantas certas, quantas havia."""

    marcadas: int
    certas: int
    havia: int

    @property
    def precisao(self) -> float | None:
        return None if not self.marcadas else self.certas / self.marcadas

    @property
    def cobertura(self) -> float | None:
        return None if not self.havia else self.certas / self.havia


def regua(probabilidades: np.ndarray, verdade: np.ndarray, classe: int, corte: float) -> Regua:
    """A classe marcada quando ela é a mais provável **e** passa do corte. Pura."""
    escolhida = probabilidades.argmax(axis=1)
    marcada = (escolhida == classe) & (probabilidades[:, classe] >= corte)
    return Regua(int(marcada.sum()), int((marcada & (verdade == classe)).sum()), int((verdade == classe).sum()))


def corte_para(probabilidades: np.ndarray, verdade: np.ndarray, classe: int, precisao: float) -> float | None:
    """O menor corte em que a classe chega à `precisao` na validação, ou `None` se nenhum chega. Pura.

    O menor, porque é o que dá mais cobertura; e escolhido na **validação**, que também é fora do
    livro, para o teste não ajudar a escolher o corte que ele vai julgar.
    """
    candidatos = sorted(set(np.round(probabilidades[:, classe], 4).tolist()))
    for corte in candidatos:
        medida = regua(probabilidades, verdade, classe, corte)
        if medida.marcadas >= 5 and medida.precisao is not None and medida.precisao >= precisao:
            return float(corte)
    return None


__all__ = [
    "ALTURA",
    "CLASSES",
    "COBERTURA_DE_SUGERIR",
    "LARGURA_MAXIMA",
    "PARENTESCO",
    "PARTICOES",
    "PalavraDeCamada",
    "REGUA_DE_APLICAR",
    "REGUA_DE_SUGERIR",
    "Regua",
    "acerto",
    "chutar_pela_altura",
    "corte_para",
    "degradar",
    "identidades",
    "normalizar",
    "palavras_de_caracteres",
    "parentesco",
    "particionar",
    "regua",
    "rotulo",
    "sequencias",
]
