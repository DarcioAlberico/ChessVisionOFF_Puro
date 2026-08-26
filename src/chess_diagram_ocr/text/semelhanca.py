"""Aplicar a todos os semelhantes: o critério é a imagem, e não o caractere lido (S-213).

**O problema é o custo da repetição.** Corrigir um `e` lido como `c` e ter de repetir a correção
nos outros 300 é o que faz uma página custar horas. A S-212 diz *o que* olhar; este módulo diz
*o que mais* a mesma correção alcança.

## A decisão principal do item é o critério, e ela é contraintuitiva

Casar **pelo caractere lido** é o caminho óbvio e está errado: procurar "todos os `c`" acharia os
300 `c` que são `e` e, junto com eles, **todos os `c` legítimos** da página -- e o lote os
estragaria. O que os separa não é o que o modelo respondeu, é a forma. Por isso o alvo é o
descritor da S-202 (`dedupe.descritor`, 24x24 em [0,1]) e a régua é a distância RMS entre imagens.

E a busca é **entre classes**, ao contrário da `dedupe.agrupar`, que compara dentro da classe. Ali
o assunto é vazamento entre treino e teste, e duas imagens de leituras diferentes não são irmãs;
aqui o assunto é justamente o glifo que **saiu** da classe certa.

## A segunda condição, e o que ela compra

`dedupe.agrupar` também é medida com "a mesma leitura" ao lado do limiar. Aqui ela entra como
`mesma_leitura=`, e o que ela compra é **poder afrouxar o limiar sem perder precisão**: ela
descarta o par que a forma aproximou mas que o modelo leu de dois jeitos -- que é homóglifo ou
erro de rótulo, e assunto de `conflitos.py`, não de lote.

Ela não é o critério; é uma trava sobre ele. Ligada sozinha, sem a distância, ela vira "todos os
`c`" -- o caminho recusado no parágrafo acima.

## A consequência de projeto é de interface, e é onde o item termina

Nenhum limiar deste módulo chega a 100%. **Um em cada ~145 boxes de um lote sairia errado**
(a precisão medida no projeto de origem no limiar frouxo), e por isso *aplicar em silêncio está
fora de questão*. O resultado vai para uma **pré-visualização** com os recortes à vista, e a lista
sai **ordenada por distância crescente** -- o duvidoso fica no fim, que é onde o olho deve parar.

Isso não é conselho de uso: é o tipo. `aplicar` só aceita uma `Previsao`, e `Previsao` só sai de
`previsualizar`. Um lote sem pré-visualização **não é expressável**, e `test_o_lote_exige_previsualizacao`
afirma que a função pura recusa até quando alguém monta a estrutura à mão.

## O rigor é escolha de cobertura, e não de risco

`estrito`, `normal` e `amplo` movem o limiar. **Os três são medidos, e a tabela vai junto** --
`docs/metrics/texto_semelhanca.json` --, porque o que muda entre eles é quantos boxes o lote
alcança, e não o quanto ele erra. Se a precisão de um deles cair abaixo de `PISO_DE_PRECISAO`, o
item entrega a pré-visualização e não o lote; é o critério de aceite, e `avaliar` é quem responde.

**Os limiares são desta base, e não do projeto de origem.** Lá a tabela é 0,20 e 0,30 numa métrica
que não veio junto; aqui a mesma faixa casaria a classe inteira -- é a lição que
`dedupe.LIMIAR_PADRAO` registra por extenso, e repeti-la de cabeça seria repetir o erro.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .dedupe import LADO_DESCRITOR, descritor

logger = logging.getLogger(__name__)

Rigor = Literal["estrito", "normal", "amplo"]
RIGORES: tuple[Rigor, ...] = ("estrito", "normal", "amplo")

LIMIAR_POR_RIGOR: dict[Rigor, float] = {
    "estrito": 0.14,
    "normal": 0.22,
    "amplo": 0.30,
}
"""Distância RMS em [0,1] de cada rigor. **Medidos nesta base**, em 3.000 recortes de 299 classes
de `training_data/` (semente 0), par a par completo -- 4,5 milhões de pares. A tabela inteira está
em `docs/metrics/texto_semelhanca.json`; o que decidiu os três números é isto:

    limiar |  imagem só          |  imagem + mesma leitura
           |  precisão cobertura |  precisão cobertura
     0,10  |  0,9999   0,1124    |  1,0000   0,1124
     0,14  |  0,9986   0,2180    |  1,0000   0,2180     <- estrito
     0,18  |  0,9930   0,3055    |  0,9994   0,3055
     0,22  |  0,9828   0,3829    |  0,9991   0,3829     <- normal
     0,26  |  0,9569   0,4788    |  0,9983   0,4787
     0,30  |  0,8276   0,5683    |  0,9971   0,5682     <- amplo
     0,35  |  0,6983   0,6563    |  0,9968   0,6562
     0,40  |  0,4540   0,7445    |  0,9969   0,7444

**A segunda condição é o que faz os três caberem, e o número é mais forte do que o do projeto de
origem.** Lá ela valia 0,4 ponto de precisão; aqui, no limiar de 0,30, ela leva a precisão de
**82,76% para 99,71%** -- e a cobertura fica igual até a quarta casa (0,5683 contra 0,5682). Isto
é, ela remove quase só os pares errados. Em 0,40, onde a imagem sozinha desaba para 45%, ela ainda
segura 99,69% com 74,4% de cobertura -- e é por isso que `amplo` parou em 0,30 e não em 0,40: **o
teto de 0,30 é escolha, e não limite da régua**. Além dele o lote passa a depender inteiramente da
trava, e um rigor cuja precisão vem toda de uma condição secundária é um rigor que não se explica
para quem vai olhar a pré-visualização. Com ela ligada -- o padrão de `semelhantes` -- os três
rigores ficam acima do `PISO_DE_PRECISAO`; **desligada, só o `estrito` fica**, e é isso que
`Placar.entrega_lote` responde por rigor em vez de por módulo.

**Os limiares são desta base, e não do projeto de origem.** Lá a tabela é 0,20 e 0,30 numa métrica
que não veio junto, com 64,6% de cobertura; aqui, no limiar mais próximo, a precisão bate e a
cobertura é **metade** -- a amostra de lá eram 9 páginas de um livro, e esta são 299 classes do
acervo inteiro, onde os pares da mesma classe são muito mais heterogêneos. Herdar o número de lá
teria produzido uma tabela que descreve outro material, que é a lição que `dedupe.LIMIAR_PADRAO`
registra por extenso.

**Nenhum deles é o `dedupe.LIMIAR_PADRAO` (0,03), e a primeira versão deste módulo usava-o.** Ele
é o limiar da *quase-duplicata* -- a mesma renderização com meio pixel de deslocamento -- e medido
aqui ele entrega 100% de precisão com **6% de cobertura**: um lote que quase nunca alcança nada.
Os dois assuntos usam a mesma régua e não o mesmo corte.
"""

PISO_DE_PRECISAO = 0.99
"""Abaixo disto o rigor entrega pré-visualização e **não** lote. É o critério de aceite do item."""

BLOCO = 512
"""Linhas por bloco na matriz de distâncias, como em `dedupe.BLOCO`."""


@dataclass(frozen=True)
class Semelhante:
    """Um candidato do lote: onde ele está, o quanto se parece, e o que o modelo leu nele."""

    indice: int
    distancia: float
    leitura: str = ""

    @property
    def duvidoso(self) -> bool:
        """Passou do rigor `estrito`. É o que a tela marca para o olho parar.

        O corte não é uma fração arbitrária do limiar corrente: é o **rigor de baixo**, que é o
        único que a medição aprova mesmo com a segunda condição desligada. Um candidato além dele
        depende da trava para estar certo, e é exatamente isso que a marca quer dizer."""
        return self.distancia > LIMIAR_POR_RIGOR["estrito"]


def limiar_de(rigor: Rigor | float) -> float:
    """O número do rigor, ou o próprio número quando alguém passa um.

    Aceitar o float é o que permite a `cvoff-texto-semelhanca` varrer a tabela sem inventar três
    nomes novos por linha medida.
    """
    if isinstance(rigor, str):
        if rigor not in LIMIAR_POR_RIGOR:
            raise ValueError(f"rigor desconhecido: {rigor!r}. Conhecidos: {', '.join(RIGORES)}")
        return LIMIAR_POR_RIGOR[rigor]
    return float(rigor)


def distancias(alvo: np.ndarray, candidatos: np.ndarray) -> np.ndarray:
    """RMS entre o descritor do alvo e o de cada candidato, em [0, 1].

    A mesma métrica de `dedupe._pares_proximos`, e é o que torna as duas tabelas comparáveis: um
    limiar deste módulo quer dizer, pixel por pixel, o mesmo que um limiar de lá.
    """
    if candidatos.size == 0:
        return np.empty(0, np.float32)
    alvo = np.asarray(alvo, np.float32).reshape(1, -1)
    candidatos = np.asarray(candidatos, np.float32)
    if alvo.shape[1] != candidatos.shape[1]:
        raise ValueError(
            f"descritores de tamanhos diferentes: alvo {alvo.shape[1]}, candidatos {candidatos.shape[1]}"
        )
    saida = np.empty(candidatos.shape[0], np.float32)
    for inicio in range(0, candidatos.shape[0], BLOCO):
        fatia = candidatos[inicio : inicio + BLOCO]
        saida[inicio : inicio + BLOCO] = np.sqrt(((fatia - alvo) ** 2).mean(axis=1))
    return saida


def semelhantes(
    alvo: np.ndarray,
    candidatos: np.ndarray,
    *,
    rigor: Rigor | float = "normal",
    leituras: Sequence[str] = (),
    leitura_do_alvo: str = "",
    mesma_leitura: bool = True,
) -> list[Semelhante]:
    """Os candidatos parecidos com o alvo, **ordenados por distância crescente**.

    `alvo` e `candidatos` são descritores (`dedupe.descritor`), e não recortes crus: quem já os
    tem não paga o `resize` outra vez, e quem não os tem chama `descritores_de`.

    `mesma_leitura` liga a segunda condição -- ver o cabeçalho. Ela só tem efeito quando há
    `leituras` **e** `leitura_do_alvo`: sem uma das duas não há o que comparar, e filtrar por uma
    string vazia esvaziaria o lote em silêncio, que é o pior jeito de uma trava falhar.

    A ordem crescente é critério de aceite e não gosto: a pré-visualização põe o duvidoso no fim,
    que é onde o olho deve parar de confiar.
    """
    corte = limiar_de(rigor)
    todas = distancias(alvo, candidatos)
    dentro = np.flatnonzero(todas <= corte)

    filtrando = mesma_leitura and bool(leitura_do_alvo) and len(leituras) > 0
    achados = [
        Semelhante(int(i), float(todas[i]), leituras[i] if i < len(leituras) else "")
        for i in dentro
        if not filtrando or (i < len(leituras) and leituras[i] == leitura_do_alvo)
    ]
    return sorted(achados, key=lambda s: (s.distancia, s.indice))


def descritores_de(recortes: np.ndarray, *, lado_origem: int = 32) -> np.ndarray:
    """`dedupe.descritor` com o nome que este módulo usa. Existe para não haver dois `resize`."""
    return descritor(np.asarray(recortes), lado_origem=lado_origem, lado=LADO_DESCRITOR)


# --------------------------------------------------------------------------------------
# A previsualizacao, e por que ela nao e um conselho
# --------------------------------------------------------------------------------------


class SemPrevisualizacao(RuntimeError):
    """Alguém tentou aplicar um lote que ninguém olhou. Ver `aplicar`."""


@dataclass(frozen=True)
class Previsao:
    """O que o lote faria, com os recortes à vista e nada aplicado.

    **Só `previsualizar` a produz**, e é isso que torna "lote sem pré-visualização" inexpressável
    em vez de desaconselhado. Montá-la à mão é possível em Python -- tudo é --, e por isso
    `aplicar` ainda confere `olhada`: a trava do tipo pega o descuido, e a do valor pega a
    esperteza.
    """

    alvo: int
    para: str
    """O caractere que a correção humana pôs no lugar. É o que o lote propaga."""

    candidatos: tuple[Semelhante, ...]
    rigor: Rigor | float
    olhada: bool = False
    """Alguém viu esta lista na tela. `previsualizar` a devolve `False`; `confirmar` a vira."""

    @property
    def quantos(self) -> int:
        return len(self.candidatos)

    @property
    def pior_distancia(self) -> float:
        """A do último da lista -- ela sai ordenada, e o duvidoso fica no fim."""
        return self.candidatos[-1].distancia if self.candidatos else 0.0

    def confirmar(self) -> Previsao:
        """A mesma previsão, marcada como olhada. É o gesto que a tela faz por quem olhou."""
        return Previsao(self.alvo, self.para, self.candidatos, self.rigor, olhada=True)


def previsualizar(
    alvo: int,
    para: str,
    candidatos: Sequence[Semelhante],
    *,
    rigor: Rigor | float = "normal",
) -> Previsao:
    """A lista que a tela mostra. **Não aplica nada**, e é o ponto.

    Reordena por distância mesmo quando `semelhantes` já ordenou: a lista pode ter passado por um
    filtro de quem chama, e a ordem é critério de aceite -- garanti-la aqui custa um `sorted` e
    tira a garantia de depender de todo mundo lembrar.
    """
    em_ordem = tuple(sorted(candidatos, key=lambda s: (s.distancia, s.indice)))
    return Previsao(alvo=int(alvo), para=str(para), candidatos=em_ordem, rigor=rigor)


def aplicar(previsao: Previsao, escolhidos: Iterable[int] | None = None) -> dict[int, str]:
    """`{índice: caractere}` para quem vai gravar. Levanta se ninguém olhou a lista.

    `escolhidos` é o subconjunto que a pessoa deixou marcado; `None` é "todos os da previsão".
    Um índice fora da previsão é **recusado**, e não ignorado: aplicar a um box que não estava na
    lista olhada é a mesma coisa que aplicar sem lista.

    Este módulo não escreve em lugar nenhum -- devolve o que mudar. Quem grava é o editor, e quem
    transforma isso em amostra de treino é a S-214, que tem a etapa humana no meio.
    """
    if not previsao.olhada:
        raise SemPrevisualizacao(
            "o lote não foi pré-visualizado. Um em cada ~145 boxes sairia errado, e por isso "
            "aplicar em silêncio está fora de questão (S-213)."
        )
    disponiveis = {s.indice for s in previsao.candidatos}
    alvos = disponiveis if escolhidos is None else {int(i) for i in escolhidos}
    fora = sorted(alvos - disponiveis)
    if fora:
        raise SemPrevisualizacao(f"índices fora da pré-visualização: {fora}")
    return dict.fromkeys(sorted(alvos), previsao.para)


# --------------------------------------------------------------------------------------
# A medicao, que e o que decide se o rigor entrega lote ou so previsualizacao
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Placar:
    """Precisão e cobertura de um critério, sobre todos os pares de uma amostra rotulada."""

    limiar: float
    mesma_leitura: bool
    pares_casados: int
    pares_certos: int
    pares_da_mesma_classe: int
    amostras: int

    @property
    def precisao(self) -> float:
        """Dos pares que o critério juntou, quantos são de fato o mesmo caractere."""
        return 0.0 if not self.pares_casados else self.pares_certos / self.pares_casados

    @property
    def cobertura(self) -> float:
        """Dos pares que **são** o mesmo caractere, quantos o critério alcançou."""
        return 0.0 if not self.pares_da_mesma_classe else self.pares_certos / self.pares_da_mesma_classe

    @property
    def entrega_lote(self) -> bool:
        """Acima do piso o rigor entrega lote; abaixo, só a pré-visualização (critério de aceite)."""
        return self.precisao >= PISO_DE_PRECISAO

    @property
    def um_errado_a_cada(self) -> float:
        """`1/(1-precisão)`: a unidade em que a consequência de interface se lê."""
        erro = 1.0 - self.precisao
        return float("inf") if erro <= 0 else 1.0 / erro

    def para_json(self) -> dict[str, object]:
        return {
            "limiar": round(self.limiar, 4),
            "mesma_leitura": self.mesma_leitura,
            "amostras": self.amostras,
            "pares_casados": self.pares_casados,
            "pares_certos": self.pares_certos,
            "pares_da_mesma_classe": self.pares_da_mesma_classe,
            "precisao": round(self.precisao, 6),
            "cobertura": round(self.cobertura, 6),
            "um_errado_a_cada": round(self.um_errado_a_cada, 1) if self.pares_casados else None,
            "entrega_lote": self.entrega_lote,
        }


def avaliar(
    D: np.ndarray,
    y: np.ndarray,
    *,
    limiar: float,
    leituras: np.ndarray | None = None,
) -> Placar:
    """O critério medido sobre **todos os pares** da amostra. `leituras=None` desliga a 2ª condição.

    `y` é a verdade (a pasta de onde o recorte veio) e `leituras` é o que o **modelo** respondeu --
    as duas são coisas diferentes, e confundi-las mediria o critério contra ele mesmo. A segunda
    condição filtra por `leituras`; o acerto é julgado por `y`.

    Par a par completo, em blocos: uma amostra de alguns milhares cabe, e uma base inteira não --
    quem chama é que decide o tamanho. Ver `cvoff-texto-semelhanca`.
    """
    D = np.asarray(D, np.float32)
    y = np.asarray(y)
    n = D.shape[0]
    if n != y.shape[0]:
        raise ValueError(f"D tem {n} linhas e y tem {y.shape[0]}.")

    casados = certos = 0
    mesma_classe = 0
    # **Pela identidade do `matmul`, e nao pela diferenca elemento a elemento.** Um
    # `fatia[:, None, :] - D[None, :, :]` monta um cubo de (bloco, n, 576) floats -- com n=4.000
    # sao 4,7 GB para uma amostra que cabe em 9 MB. E a mesma conta de `dedupe._pares_proximos`,
    # e e o que torna o par a par exato viavel.
    quadrados = (D * D).sum(1)
    corte2 = (float(limiar) ** 2) * D.shape[1]
    for inicio in range(0, n, BLOCO):
        fim = min(inicio + BLOCO, n)
        linhas = np.arange(inicio, fim)
        dist2 = quadrados[inicio:fim, None] + quadrados[None, :] - 2.0 * (D[inicio:fim] @ D.T)
        # So o triangulo superior: o par (i, j) nao pode contar duas vezes, e i == j nao e par.
        acima = linhas[:, None] < np.arange(n)[None, :]
        igual = y[linhas][:, None] == y[None, :]
        mesma_classe += int((acima & igual).sum())

        perto = (dist2 <= corte2) & acima
        if leituras is not None:
            perto &= leituras[linhas][:, None] == leituras[None, :]
        casados += int(perto.sum())
        certos += int((perto & igual).sum())

    return Placar(
        limiar=float(limiar),
        mesma_leitura=leituras is not None,
        pares_casados=casados,
        pares_certos=certos,
        pares_da_mesma_classe=mesma_classe,
        amostras=n,
    )


def tabela(placares: Mapping[str, Placar]) -> list[str]:
    """A tabela do rigor, para a tela e para o documento. Ver "O rigor é escolha de cobertura"."""
    linhas = ["critério                 limiar   precisão   cobertura   lote?"]
    for nome, placar in placares.items():
        marca = "sim" if placar.entrega_lote else "NÃO"
        linhas.append(
            f"  {nome:<22s} {placar.limiar:6.3f}   {placar.precisao:7.2%}    {placar.cobertura:7.2%}   {marca}"
        )
    return linhas
