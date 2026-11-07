"""A folha que saiu vazia avisa: a densidade de leitura (S-710).

**O sintoma é o pior que este subsistema tem, porque não tem sintoma.** Medido em 2026-10-30, 5 de 67
folhas -- *Chess Evolution* 903 e 1210, *Kmoch* 31, 69 e 106 -- saíam com um bloco só (`h`, `.`), sem
log nem exceção: uma região escura na borda da folha faz a segmentação ver um caractere do tamanho da
página. Quem lê o livro não tem como saber que faltam 40 linhas.

**A primeira guarda foi reprovada por medição, e o motivo é o que decide esta.** "Tinta coberta pelas
caixas de linha ≥ 95%" dá **1,000** na folha perdida -- a caixa única e degenerada cobre a folha
inteira -- e 0,942 em folhas boas. "Altura da maior linha ÷ mediana" também falha (47,9 numa folha
normal). O que separa, nas 95 folhas dos quatro conjuntos, é a **densidade de leitura**: caracteres
lidos ÷ componentes de tinta fora dos diagramas. Folhas normais, 0,903 a 1,285; as perdidas, 0,001 a
0,007.

## O que ela promete, e o que não

**Perda total, e só.** A densidade não vê perda parcial: no degradado, três folhas do *Capablanca*
saem com 35-39% dos caracteres e densidade 0,97-1,16 -- o texto ruim tem tanta letra quanto o bom. Por
isso o aviso se chama `folha_nao_lida`, e a perda parcial tem sinal próprio: linhas de texto estimadas
pela projeção horizontal contra linhas lidas e, quando há camada, caracteres lidos contra caracteres
dela.

**Componente conta só com altura de letra**, 8 a 60 px a 220 dpi: a arte da capa virava centenas de
componentes sem letra nenhuma, e o *Dvoretsky* dava 0,284 na capa. **Folha com pouca tinta é classe à
parte** (capa, branco, só diagrama), e não avisa: nela não há o que ler, e avisar ensinaria a ignorar
o selo.

**O diagrama é mais largo que o retângulo dele.** As coordenadas e o número do exercício ficam em volta,
têm altura de letra, e o glifo os descarta de propósito (`sem_rotulos_de_eixo`). Na *Polgar 5334*, com
seis diagramas por folha, isso dava densidade de 0,33 a 0,48 em 16 de 25 folhas, sem nada perdido, e a
reserva trocava o texto certo por outro pior. A máscara cresce uma casa de cada lado. E **a leitura que
bate com a camada não é perda**: quem leu ao menos 60% do que a camada tem não perdeu a folha.

**Ela olha para os dois lados.** O ruído fora da moldura não é perda, e não se chama `folha_nao_lida`: é a folha que leu
muito mais do que tem, e o aviso é `leitura_com_ruido` (`Medida.afogada`). Ele não chama a reserva nem muda o texto, porque
o texto certo pode estar no meio: nas 9 folhas de prosa do *Yusupov*, ele fica afogado em 15 mil a 78 mil sinais.

O cálculo é sobre a binária de Otsu da imagem da folha, e não a de `binarize`: o limiar global é o que
a medição usou, e o resultado não depende da segmentação que esta guarda existe para vigiar.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

CORTE_DA_DENSIDADE = 0.5
"""Abaixo disto a folha não foi lida. Folhas normais ficam acima de 0,9; as perdidas, abaixo de 0,01."""

MINIMO_DE_COMPONENTES = 100
"""Abaixo disto a folha não tem texto a perder: capa, branco, só diagrama. Duas linhas de prosa.

Era 40, e as capas do *1000 Chess Problems* e do *A Matter of Endgame* (47 e 43 componentes) avisavam."""

MINIMO_COM_CAMADA = 40
"""O mesmo mínimo, quando a camada confirma que a folha tem texto. **O número sozinho não separa os dois
casos**: a folha 814 do *Chess Evolution 2013* tem três linhas, 68 componentes, e o glifo lê `h`. As duas capas
não têm camada nenhuma, e essa folha tem."""

CAMADA_QUE_CONFIRMA = 20
"""Caracteres na camada para ela valer de testemunha: uma palavra solta na capa não confirma folha de texto."""

DPI_DA_REGUA = 220
ALTURA_MINIMA = 8
ALTURA_MAXIMA = 60
AREA_MINIMA = 6
"""Área e altura da letra a `DPI_DA_REGUA`; escalam com o DPI da folha."""

FOLGA = 8

CORTE_DAS_LINHAS = 0.5
MINIMO_DE_LINHAS = 10
"""Perda parcial por linhas: lidas abaixo de metade das estimadas, numa folha com ao menos dez."""

CORTE_DA_CAMADA = 0.6
MINIMO_DA_CAMADA = 200
"""Perda parcial por camada: lidos abaixo de 60% dos caracteres dela, se ela tiver ao menos 200."""

RUIDO_POR_TOKEN = 1.3
MINIMO_DE_RUIDO = 40
"""Caracteres por token e caracteres na folha para o que saiu ser sinal solto, e não leitura (S-711).

**Só vale na folha com moldura.** Tirar a moldura abre o que estava dentro dela, e isso pode ser mancha de
contracapa ou texto que o glifo despedaça. Medido em 117 folhas com moldura de 10 livros: as que dão ruído vão de
1,02 a 1,29, e a seguinte já é 1,39. Fora da moldura esse número é uma tabela de torneio, e não ruído. A fração de
palavras existentes não serve aqui: nos livros holandeses ela fica em 2% com o texto lido."""

CORTE_DO_EXCESSO = 4.0
MINIMO_DO_EXCESSO = 500
"""Sinais lidos por letra impressa, e sinais na folha, para o que saiu estar afogado em ruído.

**Densidade, e não contagem:** folha de letra miúda lê mais de 6.000 sinais certos. Medido em 2026-11-07 no acervo
inteiro (`docs/metrics/texto_g3_20261106.json`): na amostra de 1.448 folhas, a mediana é 1,13 e o p95 é 1,49. Abaixo do
corte ainda há prosa de verdade (*Simple Chess* 117 e 127, 3,06 e 3,18; *Bachmann* 121, 3,17), e a seguinte que dispara
é a capa do *Chess Structures*, 4,85. Das 84 folhas que disparam, vistas uma a uma, nenhuma tem leitura boa: 56 de
diagramas ou tabela com a hachura lida como letra, 18 de capa ou arte, e 10 de prosa real no meio do ruído.

**O mínimo tira as legendas:** abaixo dele a densidade alta pode ser leitura certa. As folhas de diagrama do *Karpov* e do
*Dufresne* passam do corte com 130 a 330 sinais legítimos, porque a régua conta pouca letra em volta dos tabuleiros."""


def parece_ruido(tokens: Sequence[str]) -> bool:
    """O que saiu da folha é sinal solto: `RUIDO_POR_TOKEN`, numa quantidade que não é número de folha."""
    caracteres = sum(len(t) for t in tokens)
    return caracteres >= MINIMO_DE_RUIDO and caracteres / max(1, len(tokens)) <= RUIDO_POR_TOKEN


@dataclass(frozen=True)
class Medida:
    """O que a guarda viu numa folha. Os três números vão ao relatório da régua."""

    componentes: int
    lidos: int
    linhas_estimadas: int
    linhas_lidas: int
    caracteres_da_camada: int = 0
    ruido: bool = False
    """A folha tem moldura, e o que saiu de dentro dela é sinal solto. Ver `RUIDO_POR_TOKEN`."""

    @property
    def densidade(self) -> float:
        return self.lidos / max(1, self.componentes)

    @property
    def tem_texto(self) -> bool:
        return self.componentes >= MINIMO_DE_COMPONENTES or (
            self.componentes >= MINIMO_COM_CAMADA and self.caracteres_da_camada >= CAMADA_QUE_CONFIRMA
        )

    @property
    def bate_com_a_camada(self) -> bool:
        """Leu ao menos o que a camada pede para não ser perda parcial. Sem camada, não responde."""
        return (
            self.caracteres_da_camada >= CAMADA_QUE_CONFIRMA
            and self.lidos >= CORTE_DA_CAMADA * self.caracteres_da_camada
        )

    @property
    def nao_lida(self) -> bool:
        # **O ruído não se absolve pela contagem.** Bater em número com a camada não diz nada de sinal solto: no
        # *Niemeijer*, índice 4, saem 3.101 caracteres em 2.789 tokens contra uma camada de 1.624, e a conta passava.
        perdida = self.tem_texto and self.densidade < CORTE_DA_DENSIDADE and not self.bate_com_a_camada
        return self.ruido or perdida

    @property
    def parcial(self) -> bool:
        """Leu, mas menos do que a folha tem. **Nunca junto com `nao_lida`**: é a mesma folha duas vezes."""
        if not self.tem_texto or self.nao_lida:
            return False
        if self.linhas_estimadas >= MINIMO_DE_LINHAS and self.linhas_lidas < CORTE_DAS_LINHAS * self.linhas_estimadas:
            return True
        return (
            self.caracteres_da_camada >= MINIMO_DA_CAMADA
            and self.lidos < CORTE_DA_CAMADA * self.caracteres_da_camada
        )

    @property
    def afogada(self) -> bool:
        """Leu muito mais do que a folha tem. **Nunca junto dos outros dois**, e o texto certo pode estar no meio."""
        return (
            not self.nao_lida
            and not self.parcial
            and self.lidos >= MINIMO_DO_EXCESSO
            and self.densidade >= CORTE_DO_EXCESSO
        )


def linhas_pela_projecao(tinta: np.ndarray, dpi: int = DPI_DA_REGUA) -> int:
    """Quantas faixas de tinta a projeção horizontal acha: uma estimativa de linhas, para **baixo**.

    Em duas colunas desalinhadas as linhas das duas se fundem numa faixa. É o lado seguro: a estimativa
    baixa não dispara aviso, e o sinal existe para a folha em que quase nada foi lido.
    """
    if tinta.size == 0:
        return 0
    projecao = (tinta > 0).sum(axis=1)
    minimo = max(3, int(round(0.01 * tinta.shape[1])))
    fatias = projecao >= minimo
    entradas = np.flatnonzero(fatias[1:] & ~fatias[:-1]) + 1
    saidas = np.flatnonzero(~fatias[1:] & fatias[:-1]) + 1
    inicios = entradas.tolist() if not fatias[0] else [0, *entradas.tolist()]
    fins = saidas.tolist() if not fatias[-1] else [*saidas.tolist(), len(fatias)]
    altura_minima = ALTURA_MINIMA * dpi / DPI_DA_REGUA
    return sum(1 for a, b in zip(inicios, fins, strict=False) if b - a >= altura_minima)


def medir(
    imagem_rgb: np.ndarray,
    diagramas: Sequence[Sequence[float]],
    *,
    lidos: int,
    linhas_lidas: int,
    dpi: int = DPI_DA_REGUA,
    caracteres_da_camada: int = 0,
    ruido: bool = False,
) -> Medida:
    """A medida de uma folha, com os retângulos de diagrama em **pixels** da imagem."""
    import cv2

    cinza = cv2.cvtColor(imagem_rgb, cv2.COLOR_RGB2GRAY) if imagem_rgb.ndim == 3 else imagem_rgb
    _, binaria = cv2.threshold(np.ascontiguousarray(cinza), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    altura, largura = binaria.shape[:2]
    for x0, y0, x1, y1 in diagramas:
        folga = max(FOLGA, int((x1 - x0) / 8))  # uma casa: a moldura, as coordenadas e o número
        ex0, ey0 = max(0, int(x0) - folga), max(0, int(y0) - folga)
        ex1, ey1 = min(largura, int(x1) + folga), min(altura, int(y1) + folga)
        if ex1 > ex0 and ey1 > ey0:
            binaria[ey0:ey1, ex0:ex1] = 0
    fator = dpi / DPI_DA_REGUA
    _, _, estatisticas, _ = cv2.connectedComponentsWithStats(binaria, connectivity=8)
    alturas = estatisticas[1:, cv2.CC_STAT_HEIGHT]
    areas = estatisticas[1:, cv2.CC_STAT_AREA]
    de_letra = (
        (alturas >= ALTURA_MINIMA * fator)
        & (alturas <= ALTURA_MAXIMA * fator)
        & (areas >= AREA_MINIMA * fator * fator)
    )
    return Medida(
        componentes=int(de_letra.sum()),
        lidos=int(lidos),
        linhas_estimadas=linhas_pela_projecao(binaria, dpi),
        linhas_lidas=int(linhas_lidas),
        caracteres_da_camada=int(caracteres_da_camada),
        ruido=ruido,
    )


__all__ = [
    "ALTURA_MAXIMA",
    "ALTURA_MINIMA",
    "AREA_MINIMA",
    "CAMADA_QUE_CONFIRMA",
    "CORTE_DAS_LINHAS",
    "CORTE_DA_CAMADA",
    "CORTE_DA_DENSIDADE",
    "CORTE_DO_EXCESSO",
    "DPI_DA_REGUA",
    "FOLGA",
    "MINIMO_COM_CAMADA",
    "MINIMO_DA_CAMADA",
    "MINIMO_DE_COMPONENTES",
    "MINIMO_DE_LINHAS",
    "MINIMO_DO_EXCESSO",
    "Medida",
    "linhas_pela_projecao",
    "medir",
]
