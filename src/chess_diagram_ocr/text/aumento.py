"""O aumento de dados dirigido ao glifo de livro (S-204).

**Este módulo existe porque o de peças não serve, e o motivo é de domínio e não de código.**
`augment.py` tem oito degradações e a mais barata delas é o **espelhamento horizontal** -- lá ele
é válido, e o docstring de lá explica por quê: o classificador decide *casa → peça*, e um cavalo
espelhado continua sendo um cavalo.

**Aqui ele é a pior coisa que se pode fazer.** Um `b` espelhado é um `d`. Um `p` espelhado é um
`q`. Um `(` espelhado é um `)`. Espelhar caractere não aumenta o dataset: ele ensina o modelo a
confundir pares que a base separa, e os pares que ele confundiria são exatamente os que a S-202
já mostrou serem os mais caros -- `digit_1`×`lower_l`, `lower_v`×`upper_V`, `digit_0`×`lower_o`.

Pela mesma razão não entram: giro de 180°, transposição, e qualquer troca de eixo. O que entra é
o que um **scanner e uma gráfica** fazem com a mesma letra.

## As sete que entram, e o que cada uma imita

| degradação | o que ela imita no acervo |
|---|---|
| `giro` | a página torta no scanner -- graus, não dezenas de graus |
| `deslocamento` | a caixa de segmentação que não centra o glifo (S-185) |
| `escala` | corpo de fonte diferente, e a mesma letra em duas resoluções |
| `espessura` | tinta gorda contra tinta fina: `bold`, papel absorvente, digitalização escura |
| `granulacao` | o ruído de scan, que a S-196 já mede na página inteira |
| `borrao` | livro de 1870 digitalizado a 200 DPI |
| `contraste` | página amarelada, e a binarização que a S-184 escolhe pelo resultado |

**Nenhuma delas muda a identidade do caractere**, e é esse o único critério: um aumento válido é
aquele cuja saída um humano rotularia com a mesma classe.

## Como isto entra no treino, e o que ele custa

O aumento acontece **no lote**, sobre o `uint8` de 32x32 que a varredura já tem em RAM, e só no
treino -- validação e teste veem a imagem como ela está no disco. Medido nesta base: ~1,4 s por
época a mais sobre os 143 mil recortes, contra os ~65 s que a época já custa.

**E ele é uma opção, não um padrão.** A Fase 5 deste projeto mediu que o aumento genérico não
ajudou para peças, e a S-204 mediu que os pesos de classe não ajudaram para caractere. Ligar sem
medir seria a terceira vez que alguém supõe. Quem decide é a grade -- `cvoff-texto-variantes`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .modelo import LADO

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    """Quanto de cada degradação. `0.0` desliga a degradação; `probabilidade` desliga o conjunto.

    Os valores são **faixas**, e não valores fixos: `giro=3.0` quer dizer "até 3 graus para cada
    lado, sorteado". Um aumento que aplica sempre a mesma coisa vira uma normalização, e o modelo
    aprende a desfazê-la em vez de a ignorar.
    """

    probabilidade: float = 0.8
    """Chance de um recorte do lote receber **alguma** degradação. O resto passa intacto.

    Não é 1,0 de propósito: o modelo precisa ver a imagem limpa também, que é o que a inferência
    vai lhe dar na maior parte das páginas."""

    giro: float = 3.0
    deslocamento: float = 1.5
    escala: float = 0.06
    espessura: float = 0.25
    granulacao: float = 0.25
    borrao: float = 0.20
    contraste: float = 0.30

    @property
    def versao(self) -> str:
        """Identidade do regime, para o metadado do checkpoint.

        Sem isto, "o modelo A é melhor que o B" pode estar comparando dois regimes de aumento --
        a mesma armadilha que a S-27 fechou para arquitetura e semente.
        """
        ativos = "".join(
            letra
            for letra, valor in (
                ("g", self.giro),
                ("d", self.deslocamento),
                ("e", self.escala),
                ("t", self.espessura),
                ("r", self.granulacao),
                ("b", self.borrao),
                ("c", self.contraste),
            )
            if valor > 0.0
        )
        if not ativos or self.probabilidade <= 0:
            return "tex0"
        # A probabilidade e o giro entram porque **as letras sozinhas não separam os regimes**:
        # `LEVE` e `FORTE` ligam as mesmas sete, e a única diferença é a intensidade. Uma
        # identidade que empata dois regimes é pior que nenhuma -- ela faz a tabela da grade
        # dizer que comparou dois braços iguais.
        return f"tex{ativos}-p{int(round(self.probabilidade * 100))}-g{self.giro:g}"


DESLIGADO = Config(probabilidade=0.0)
"""O controle da grade: nenhum recorte é tocado."""

LEVE = Config()
"""O que o acervo pede: torto de poucos graus, tinta de espessura variável, um pouco de ruído."""

FORTE = Config(
    probabilidade=1.0, giro=6.0, deslocamento=2.5, escala=0.12, espessura=0.5,
    granulacao=0.5, borrao=0.4, contraste=0.5,
)
"""O outro extremo da grade. Existe para a tabela ter os dois lados do joelho, e não porque
alguém ache que mais é melhor."""


def _matriz(aleatorio: np.random.Generator, config: Config, lado: int) -> np.ndarray:
    """A afim de um recorte: giro pequeno, escala e deslocamento, em volta do centro."""
    import cv2

    graus = float(aleatorio.uniform(-config.giro, config.giro)) if config.giro > 0 else 0.0
    escala = 1.0 + float(aleatorio.uniform(-config.escala, config.escala)) if config.escala > 0 else 1.0
    matriz = cv2.getRotationMatrix2D((lado / 2 - 0.5, lado / 2 - 0.5), graus, escala)
    if config.deslocamento > 0:
        matriz[0, 2] += float(aleatorio.uniform(-config.deslocamento, config.deslocamento))
        matriz[1, 2] += float(aleatorio.uniform(-config.deslocamento, config.deslocamento))
    return matriz


def _um(recorte: np.ndarray, aleatorio: np.random.Generator, config: Config) -> np.ndarray:
    """Um recorte 32x32 degradado. **A polaridade é a do disco: tinta escura sobre papel claro.**"""
    import cv2

    saida = recorte
    if config.giro > 0 or config.escala > 0 or config.deslocamento > 0:
        # `BORDER_REPLICATE` e não `BORDER_CONSTANT`: uma borda preta inventada vira tinta, e o
        # modelo aprenderia a ler a moldura em vez do glifo.
        saida = cv2.warpAffine(
            saida,
            _matriz(aleatorio, config, saida.shape[0]),
            (saida.shape[1], saida.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

    if config.espessura > 0 and aleatorio.random() < config.espessura:
        # Erodir engorda a tinta escura; dilatar afina. Os dois com núcleo 2x2, que é o menor
        # que muda alguma coisa em 32x32 -- 3x3 apaga letra fina inteira.
        nucleo = np.ones((2, 2), np.uint8)
        saida = cv2.erode(saida, nucleo) if aleatorio.random() < 0.5 else cv2.dilate(saida, nucleo)

    if config.borrao > 0 and aleatorio.random() < config.borrao:
        saida = cv2.GaussianBlur(saida, (3, 3), float(aleatorio.uniform(0.4, 1.0)))

    if config.contraste > 0 and aleatorio.random() < config.contraste:
        ganho = 1.0 + float(aleatorio.uniform(-config.contraste, config.contraste))
        desvio = float(aleatorio.uniform(-25, 25))
        saida = cv2.convertScaleAbs(saida, alpha=ganho, beta=desvio)

    if config.granulacao > 0 and aleatorio.random() < config.granulacao:
        ruido = aleatorio.normal(0.0, 255 * 0.05, saida.shape)
        saida = np.clip(saida.astype(np.float32) + ruido, 0, 255).astype(np.uint8)

    return saida


def aplicar(
    lote: np.ndarray, aleatorio: np.random.Generator, config: Config, *, lado: int = LADO
) -> np.ndarray:
    """`(n, lado*lado) uint8` degradado, **cópia**. `probabilidade` 0 devolve o lote como veio.

    Devolve cópia porque o lote vem de uma fatia de `X`, que é a base inteira em RAM: degradar no
    lugar apagaria o disco dentro da memória, e a época seguinte veria o estrago acumulado.
    """
    if config.probabilidade <= 0.0 or lote.size == 0:
        return lote

    saida = lote.copy()
    escolhidos = np.flatnonzero(aleatorio.random(lote.shape[0]) < config.probabilidade)
    for i in escolhidos:
        recorte = saida[i].reshape(lado, lado)
        saida[i] = _um(recorte, aleatorio, config).reshape(-1)
    return saida


def de_nome(nome: str) -> Config:
    """`"desligado"`, `"leve"` ou `"forte"` -> a configuração. Nome fora disso levanta.

    Levanta em vez de cair no padrão: um nome errado que vire "leve" em silêncio faria a linha da
    grade dizer uma coisa e medir outra.
    """
    tabela = {"desligado": DESLIGADO, "leve": LEVE, "forte": FORTE}
    if nome not in tabela:
        raise ValueError(f"regime de aumento desconhecido: {nome!r}. Use {', '.join(tabela)}.")
    return tabela[nome]


__all__ = ["DESLIGADO", "FORTE", "LEVE", "Config", "aplicar", "de_nome"]
