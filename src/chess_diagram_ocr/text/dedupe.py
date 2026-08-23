"""A quase-duplicata: o mesmo glifo da mesma fonte, que difere num pixel de antialiasing (S-202).

**O que ela é, e por que o hash não a pega.** Em PDF digital o mesmo `e` da mesma fonte sai byte
a byte igual — e `dataset.varrer` fecha esse caso com SHA-256, que nesta base achou 70,7% de
cópia. O que escapa é o `e` que passou por uma rasterização com meio pixel de deslocamento: para
o olho é a mesma imagem, para o hash é outra. Se uma cai no treino e a irmã no teste, o modelo
mede a própria memória — e o número sai inflado sem que nada avise.

**Ela nunca apaga nada, e isso é da spec.** A precisão do critério não passa de ~99,3% nem no
projeto de origem, e o que sobra são homóglifos de verdade (`0`×`o`, `9`×`g`, `1`×`i`, `P`×`p`)
em que as duas imagens *são* quase iguais. Consequência: a quase-duplicata **alimenta o split**,
agrupando prováveis irmãs para caírem do mesmo lado, e alimenta a revisão. Ela não é uma poda.
`agrupar` devolve grupos; a contagem de amostras de cada classe não muda.

**Só compara dentro da classe, e isso não é atalho — é o critério.** A S-202 exige "a mesma
leitura" junto do limiar. Duas imagens quase iguais com leituras diferentes não são irmãs: são
homóglifo ou erro de rótulo, e quem trata disso é `conflitos.py`. Restringir à classe também é o
que torna a passada exata viável: o par a par completo sobre 178 mil imagens seria 1,6·10¹⁰
comparações, e por classe são 4,4·10⁸ — que cabem em `matmul` por blocos, sem aproximação.

**O lado 24 vem de lá, e a aritmética confere.** 32² = 1024 contra 24² = 576: exatamente os 78%
de memória a mais que a spec de origem cita, sem ganho de precisão medido. Ele fica.

**O limiar 0,20 de lá NÃO fica, e recusá-lo é o que a regra do projeto manda.** Ele foi medido
noutra métrica, que não veio junto. Nesta base, com distância RMS em [0, 1], 0,20 casa 12% a 24%
de *todos* os pares de uma classe — juntaria a classe inteira num grupo só. O que foi medido aqui
(2026-08-23, três classes, pares amostrados e olhados um a um):

    d < 0,03   a mesma renderização; diferem em antialiasing e contraste
    d ~ 0,05   mesma forma, peso visivelmente diferente
    d > 0,08   o mesmo caractere em fontes diferentes -- amostra legítima, não irmã

E a régua que decide, medida contra o modelo de 2026-08-23: **19% do conjunto de teste tinha uma
imagem de treino a menos de 0,01**, e a acurácia nessa faixa é 0,9994 contra 0,9925 na faixa de
0,08 a 0,12. Excluir do teste tudo com vizinho abaixo de 0,03 leva a acurácia de 0,9928 para
0,9906. **É esse o tamanho do vazamento** — pequeno, mas medido, e não mais suposto.

**A proporção e a altura entram por fora, e nesta base só às vezes.** O critério de origem as
exige porque um `.` e um `O` preenchem o mesmo quadrado depois do redimensionamento. Aqui a
comparação é dentro da classe, então esse caso não aparece; o que elas ainda separam é um `a`
pequeno de um `a` grande da mesma classe. Só que **58% dos recortes chegaram em 32x32 da
origem**, e para eles a altura é o valor que a normalização impôs, não o do glifo. Então a
guarda só vale quando **os dois** recortes do par trazem tamanho nativo — ver `RAZAO_MAXIMA`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

LADO_DESCRITOR = 24
"""Lado do descritor. **Não é 32, e o motivo está medido no projeto de origem**: 32 não muda a
precisão e custa 1024/576 = 78% mais memória. Ver o cabeçalho."""

LIMIAR_PADRAO = 0.03
"""Distância RMS em [0, 1] abaixo da qual duas imagens da mesma classe são irmãs.

**Medido nesta base, e não herdado.** O 0,20 da spec de origem é de outra métrica e aqui casaria
a classe inteira. Ver o cabeçalho para as três faixas que foram olhadas e para a régua de
vazamento que fixou o valor."""

RAZAO_MAXIMA = 1.25
"""Quanto a altura nativa de duas irmãs pode diferir. Só se aplica quando **as duas** a têm.

O `1,25` é folga para arredondamento de rasterização entre páginas do mesmo livro; acima disso
são tamanhos de corpo diferentes, que é outra renderização e não uma irmã."""

BLOCO = 512
"""Linhas por bloco na matriz de distâncias. 512 x 12.000 x 4 bytes = 24 MB por bloco."""


@dataclass(frozen=True)
class Resumo:
    """O que `agrupar` achou. Vai para `docs/metrics/texto_dedupe_*.json`."""

    grupos_antes: int
    grupos_depois: int
    fundidos: int
    maior_grupo: int
    limiar: float

    @property
    def reducao(self) -> float:
        """Fração dos grupos exatos que a quase-duplicata absorveu."""
        return 0.0 if not self.grupos_antes else self.fundidos / self.grupos_antes


def descritor(X: np.ndarray, lado_origem: int = 32, lado: int = LADO_DESCRITOR) -> np.ndarray:
    """`(n, lado*lado)` em [0, 1], a partir dos recortes achatados de `dataset.Varredura.X`."""
    import cv2

    if X.size == 0:
        return np.empty((0, lado * lado), np.float32)
    saida = np.empty((X.shape[0], lado * lado), np.float32)
    for i in range(X.shape[0]):
        quadro = X[i].reshape(lado_origem, lado_origem)
        saida[i] = cv2.resize(quadro, (lado, lado), interpolation=cv2.INTER_AREA).reshape(-1)
    return saida / 255.0


class _Uniao:
    """União-busca sobre índices. Pequeno de propósito: é o único uso, e é literal."""

    def __init__(self, n: int) -> None:
        self._pai = np.arange(n)

    def raiz(self, i: int) -> int:
        pai = self._pai
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = int(pai[i])
        return i

    def unir(self, a: int, b: int) -> bool:
        ra, rb = self.raiz(a), self.raiz(b)
        if ra == rb:
            return False
        self._pai[max(ra, rb)] = min(ra, rb)
        return True


def _pares_proximos(
    D: np.ndarray, limiar: float, alturas: np.ndarray | None
) -> list[tuple[int, int]]:
    """Os pares `(i, j)`, `i < j`, com distância RMS abaixo do limiar.

    A distância é `sqrt(mean((a-b)^2))` sobre o descritor em [0, 1] -- a mesma escala em que o
    limiar foi medido. Sai por `matmul`, que é o que torna o par a par exato viável.
    """
    n = D.shape[0]
    if n < 2:
        return []
    quadrados = (D * D).sum(1)
    dimensao = D.shape[1]
    achados: list[tuple[int, int]] = []
    corte2 = (limiar**2) * dimensao
    for inicio in range(0, n, BLOCO):
        fim = min(inicio + BLOCO, n)
        dist2 = quadrados[inicio:fim, None] + quadrados[None, :] - 2.0 * (D[inicio:fim] @ D.T)
        # só o triângulo superior: o par (i, j) com i >= j já foi visto ou é a diagonal
        linhas, colunas = np.nonzero(dist2 <= corte2)
        linhas = linhas + inicio
        manter = linhas < colunas
        for i, j in zip(linhas[manter], colunas[manter], strict=True):
            if alturas is not None:
                ai, aj = alturas[i], alturas[j]
                if ai > 0 and aj > 0:
                    maior, menor = (ai, aj) if ai >= aj else (aj, ai)
                    if maior > menor * RAZAO_MAXIMA:
                        continue
            achados.append((int(i), int(j)))
    return achados


def agrupar(
    X: np.ndarray,
    y: np.ndarray,
    grupos: np.ndarray,
    *,
    dims: np.ndarray | None = None,
    limiar: float = LIMIAR_PADRAO,
    lado_origem: int = 32,
) -> tuple[np.ndarray, Resumo]:
    """Funde os grupos de cópia exata cujas imagens são quase iguais **dentro da mesma classe**.

    Devolve `(grupos, resumo)`. Os grupos novos são **mais grossos** que os de entrada: nenhuma
    imagem muda de classe, nenhuma sai da base, e a contagem de amostras de cada classe é a
    mesma -- é o que `test_a_quase_duplicata_nao_remove_amostra` trava.

    Compara **um representante por grupo exato**, e não todos os recortes: as cópias exatas já
    são idênticas, e compará-las de novo multiplicaria o custo pelo fator 3,4 de duplicação desta
    base sem mudar nenhuma resposta.
    """
    if not (X.shape[0] == y.shape[0] == grupos.shape[0]):
        raise ValueError("X, y e grupos têm de ter o mesmo número de linhas.")

    _, primeiros = np.unique(grupos, return_index=True)
    primeiros = np.sort(primeiros)
    grupo_do_representante = grupos[primeiros]
    uniao = _Uniao(primeiros.size)
    posicao_do_grupo = {int(g): i for i, g in enumerate(grupo_do_representante)}

    fundidos = 0
    for classe in np.unique(y[primeiros]):
        locais = np.flatnonzero(y[primeiros] == classe)
        if locais.size < 2:
            continue
        linhas = primeiros[locais]
        D = descritor(X[linhas], lado_origem=lado_origem)
        alturas = None
        if dims is not None and dims.size:
            alturas = dims[linhas][:, 0].astype(np.int32)
        for a, b in _pares_proximos(D, limiar, alturas):
            if uniao.unir(int(locais[a]), int(locais[b])):
                fundidos += 1

    raizes = np.array([uniao.raiz(i) for i in range(primeiros.size)])
    _, compacto = np.unique(raizes, return_inverse=True)
    novo_do_grupo = {g: int(compacto[i]) for g, i in posicao_do_grupo.items()}
    saida = np.fromiter((novo_do_grupo[int(g)] for g in grupos), dtype=np.int32, count=grupos.size)

    _, contagens = np.unique(saida, return_counts=True)
    resumo = Resumo(
        grupos_antes=int(primeiros.size),
        grupos_depois=int(np.unique(saida).size),
        fundidos=fundidos,
        maior_grupo=int(contagens.max()) if contagens.size else 0,
        limiar=limiar,
    )
    logger.info(
        "Quase-duplicata: %d grupos exatos -> %d grupos, %d fusões, maior grupo %d recortes.",
        resumo.grupos_antes,
        resumo.grupos_depois,
        resumo.fundidos,
        resumo.maior_grupo,
    )
    return saida, resumo


__all__ = [
    "BLOCO",
    "LADO_DESCRITOR",
    "LIMIAR_PADRAO",
    "RAZAO_MAXIMA",
    "Resumo",
    "agrupar",
    "descritor",
]
