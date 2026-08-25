"""Onde está cada caractere, e o que não é caractere (S-185).

Duas decisões carregam este módulo, e as duas foram compradas com medição no projeto de origem.

## 1. A escala do caractere é medida por massa de tinta, não pela mediana das alturas

A mediana simples não serve, e a página do quadro de pontuação do *Chess Evolution 1* mostra por
quê: o painel de meio-tom põe 22 mil pontos de 1-3 px na conta e a mediana desce para **1**. Todo
limiar relativo do pipeline desaba junto -- com mediana 1, a régua de bloco joga fora tudo acima
de 4 px, isto é, o texto.

A mediana **ponderada pela área de tinta** é estável porque o ponto de trama tem ~4 px de tinta e
uma letra tem ~200. Medido em 6 páginas:

    ponderada    31   39   43   37   36   58
    simples       1    1    8    4    7    4

E ela é sobre **componentes conexos**, não sobre contornos externos: naquela população o diagrama
é *um* componente com dezenas de milhares de pixels de tinta, e a ponderação aterrissaria nele.
Daí a exclusão de bloco, que é regra do domínio: **caractere não ocupa 1% de uma página.**

**O limite da régua, medido aqui em 2026-08-22 e não herdado.** A ponderação funciona porque o
texto pesa mais que a trama, e não porque seja imune a ela. Numa página sintética de 300x420 com
6.228 px de tinta de texto e um painel de meio-tom de 120x200:

    passo da trama   componentes   tinta da trama   mediana simples   ponderada
          4              1.516            1.517            1             17
          3              2.666            2.681            1             17
          2              5.877            6.055            1              5   <- paridade

Na paridade a ponderada cai de 17 para 5. Não é defeito a consertar neste módulo: é a fronteira
dele, e quem a atravessa é a S-196, que **apaga** a trama antes de medir em vez de sobreviver a
ela. `tests/test_text_boxes.py` trava as duas pontas -- a que aguenta e a que degrada.

## 2. A peneira do caractere é área, não altura

**Cortar por altura derruba o ponto final.** A primeira versão de lá cortava a 0,30 da escala e o
livro saía sem pontuação nenhuma: `5.♔xf2` virava `5♔d2`, `G.Levenfish` virava `G Levenfish`.
Medido nas páginas 10 e 11 do Yusupov, com a área normalizada pela escala ao quadrado:

    respingo da régua decorativa   0,0021 - 0,0031
    ponto final                    0,0129 - 0,0514
    hífen e travessão              0,0073 - 0,0882
    letra minúscula                0,1570 - 0,3315

O limiar cai no vão entre a primeira faixa e a segunda, com folga dos dois lados: ~1,6x acima do
maior respingo e ~1,5x abaixo do menor traço legítimo.

## O diagrama sai antes, e com margem

Os rótulos das casas (`a`-`h` embaixo, `8`-`1` ao lado) moram **fora** da borda do tabuleiro que
o detector devolve. Sem margem eles entram no texto como linhas de um caractere -- medido lá,
oito linhas contendo só "8", "7", "6"...
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

FRACAO_MAXIMA_DE_CARACTERE = 0.01
"""Fração da página que a caixa de um componente pode ocupar e ele ainda contar como caractere
ao medir a escala. Um `M` a 300 dpi ocupa ~0,05% de uma página A5; um tabuleiro ocupa 6%, e uma
trama soldada numa malha só, 20%."""

MIN_AREA_GLIFO = 0.005
"""Área mínima de um contorno para ele ser caractere, em escalas de caractere ao quadrado.
Ver a tabela no cabeçalho -- **é área, e não altura**."""

PROPORCAO_MAXIMA = 6.0
"""Largura sobre altura. Acima disto é filete, moldura ou sublinhado, não glifo. Não veio de
tabela: é o piso grosseiro que separa traço de linha decorativa, e a S-199 é quem trata moldura
de tabela como tabela em vez de descartá-la."""

MARGEM_DIAGRAMA = 1.4
"""Quanto o retângulo do tabuleiro cresce antes de o que está dentro dele ser excluído, em
alturas de caractere. Ver "O diagrama sai antes" no cabeçalho."""


@dataclass(frozen=True)
class Caixa:
    """Um contorno aceito como caractere, em pixels da imagem que foi passada.

    `angulo` são graus **anti-horários do texto impresso**, a convenção do PDF: 0 normal, 90 o
    texto sobe, 270 o texto desce. Fica aqui desde já, e sempre 0 por enquanto, porque quem o
    preenche é a S-197 e mudar a forma do dado depois obrigaria a mexer em tudo que o consome.
    """

    x1: int
    y1: int
    x2: int
    y2: int
    angulo: int = 0

    @property
    def largura(self) -> int:
        return self.x2 - self.x1

    @property
    def altura(self) -> int:
        return self.y2 - self.y1

    @property
    def area_da_caixa(self) -> int:
        return self.largura * self.altura

    def recortar(self, imagem: np.ndarray) -> np.ndarray:
        return imagem[self.y1 : self.y2, self.x1 : self.x2]


def escala_de_texto(img_bin: np.ndarray) -> int:
    """Altura de caractere da página, medida por **massa de tinta**. `0` quando não há tinta.

    Ver a seção 1 do cabeçalho para o porquê de não ser a mediana simples.
    """
    if img_bin.size == 0:
        return 0
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(img_bin, connectivity=8)
    if n <= 1:
        return 0

    caixas = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64) * stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
    de_texto = caixas <= img_bin.size * FRACAO_MAXIMA_DE_CARACTERE
    if not de_texto.any():
        # Nenhum componente tem tamanho de caractere -- página só de bloco. Medir com todos é
        # pior que não medir: sem isto a função devolveria 0 e todo limiar relativo cairia.
        de_texto = np.ones(len(caixas), bool)

    alturas = stats[1:, cv2.CC_STAT_HEIGHT][de_texto]
    areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)[de_texto]
    ordem = np.argsort(alturas)
    acumulado = np.cumsum(areas[ordem])
    if acumulado[-1] <= 0:
        return 0
    return int(alturas[ordem][np.searchsorted(acumulado, acumulado[-1] / 2)])


def caixas_de_caractere(
    img_bin: np.ndarray,
    *,
    escala: int | None = None,
    min_area: float = MIN_AREA_GLIFO,
    proporcao_maxima: float = PROPORCAO_MAXIMA,
) -> list[Caixa]:
    """Os contornos externos que passam pela peneira de área e de proporção.

    `escala=None` mede com `escala_de_texto`. Passá-la explicitamente é o caminho de quem lê uma
    faixa pequena dentro de uma página: **a régua tem de ser a da página**, e não a da faixa --
    uma faixa com três letras não tem população para medir escala nenhuma.
    """
    if img_bin.size == 0:
        return []
    if escala is None:
        escala = escala_de_texto(img_bin)
    if escala <= 0:
        return []

    piso = min_area * escala * escala
    contornos, _ = cv2.findContours(img_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    aceitas: list[Caixa] = []
    for contorno in contornos:
        x, y, largura, altura = cv2.boundingRect(contorno)
        if largura <= 0 or altura <= 0:
            continue
        if largura * altura < piso:
            continue
        if largura / altura > proporcao_maxima:
            continue
        aceitas.append(Caixa(x, y, x + largura, y + altura))
    return aceitas


CAIXA_CURTA = 0.65
"""Abaixo desta fração da escala, a caixa não tem altura de letra: é pingo, acento ou pontuação."""

SOBREPOSICAO_MINIMA = 0.55
"""Quanto da largura da caixa curta precisa estar sobre a base para elas serem o mesmo glifo.

O ponto final vem **ao lado** da letra e não sobre ela, e é isso que o separa do pingo do `i`."""

VAO_MAXIMO_DO_PINGO = 0.40
"""Vão vertical máximo entre o pingo e a base, em escalas de caractere.

**É o guarda contra o merge atravessar a linha de texto**, e ele tem cicatriz no projeto de
origem (F3.11). Entre linhas o vão é de ~1 escala; dentro do glifo é uma fração dela."""

HASTE_ESTREITA = 2.0
"""Quantas vezes mais alta que larga uma base precisa ser para valer a correção de itálico.

**Só um traço carrega pingo.** `i` e `j` são haste (medido: 6 x 17 px numa página a 220 dpi); `a`
e `e` são largos e o que pousa sobre eles é acento, não pingo. Restringir a correção à haste é o
que a mantém longe do resto -- e do ponto final, cuja base costuma ser letra larga."""


def _inclinacao_da_haste(binaria: np.ndarray | None, base: Caixa) -> float:
    """A inclinação `dx/dy` da base, ou `0.0` quando não há imagem ou não é haste.

    Zero é "não corrige", e é o caminho normal: sem `binaria` (a maioria dos chamadores) e em
    qualquer base que não seja estreita, o deslocamento some e `unir_pingos` decide como sempre.
    """
    if binaria is None or base.altura < HASTE_ESTREITA * base.largura:
        return 0.0
    from .italico import inclinacao_do_box

    return inclinacao_do_box(binaria, base) or 0.0


def unir_pingos(
    caixas: list[Caixa], *, escala: int, binaria: np.ndarray | None = None
) -> list[Caixa]:
    """Devolve o pingo do `i`, o acento e o ponto do `!` ao glifo a que pertencem.

    **Sem isto a régua de área da S-185 fica pior que a régua de altura que ela substituiu**, e a
    medição de 2026-08-22 mostrou exatamente isso: com o pingo solto, `Defensive` sai
    `Defens1.ve` -- o pingo vira um ponto final, e o CER da faixa subiu de 0,21 para 0,35.

    Não é argumento para voltar à altura: a régua de altura acertava aqui **por descartar o
    pingo**, e o preço dela era descartar junto o ponto final de verdade (`G.Levenfish` virava
    `G Levenfish`). A régua certa é área, e o que faltava era esta função.

    O que **não** é unido, e cada um por um motivo:

    - o ponto final e a vírgula, que vêm **ao lado** e não sobre a letra (`SOBREPOSICAO_MINIMA`);
    - qualquer coisa a mais de `VAO_MAXIMO_DO_PINGO` de distância, que é o guarda contra o merge
      atravessar a linha de texto -- entre linhas o vão é de ~1 escala;
    - dois pontos e ponto e vírgula, que não têm base alta com que se unir.

    ## `binaria` conserta o pingo do itálico, e nada mais

    **A régua de sobreposição é horizontal e o itálico é uma inclinação: falta o eixo.** Em
    itálico o pingo do `i` pousa à *direita* da haste, e a régua que separa ponto final de pingo
    -- "o ponto final vem ao lado e não sobre a letra" -- o classifica como ponto final. Medido:
    `tecnica` sai `tecnl'ca`, `Fischer` sai `Fl'scher`, e o `i` **não** é recuperável depois,
    porque o classificador nunca o vê inteiro (na haste ele responde `/` com 0,915).

    Com `binaria`, o x do pingo é projetado para onde ele estaria se o glifo fosse reto --
    `inclinacao × vão` -- antes de medir a sobreposição. **O deslocamento é proporcional ao vão, e
    é isso que protege a pontuação**: o ponto final está na altura da letra, o vão dele é ~0, e o
    x dele não se move. Medido na página do `Fischer`: pingo em 0,500 de sobreposição contra o
    mínimo de 0,55, deslocamento de 0,6 px, e o par passa a unir.

    Sem `binaria` nada disso acontece, e é o padrão de todos os chamadores que não são a página.
    """
    if not caixas:
        return caixas

    # **A régua é a mediana das caixas presentes, e não a escala da página.** A escala é medida
    # por massa de tinta e cai perto da altura de maiúscula -- 30 px na página do `AAGAARD`. A
    # haste de um `i` minúsculo tem 18. Com `0,65 x 30 = 19,5` a própria haste conta como curta,
    # não sobra base com que unir, e o merge nunca dispara: medido em 2026-08-22, foi exatamente
    # este erro que deixou `Defensive` sair `Defens1.ve` mesmo com a função ligada.
    alturas = sorted(c.altura for c in caixas)
    mediana = alturas[len(alturas) // 2] or 1
    piso_de_letra = CAIXA_CURTA * mediana
    vao_maximo = VAO_MAXIMO_DO_PINGO * mediana

    bases = [c for c in caixas if c.altura >= piso_de_letra]
    if not bases:
        return list(caixas)

    def sobreposicao(curta: Caixa, base: Caixa, *, deslocamento: float = 0.0) -> float:
        comum = min(curta.x2 + deslocamento, base.x2) - max(curta.x1 + deslocamento, base.x1)
        return comum / curta.largura if curta.largura else 0.0

    # Uma medição por base, e não uma por par: a haste não muda de inclinação entre os pingos que
    # se oferecem a ela, e medi-la no laço de dentro custaria um recorte de imagem por par.
    inclinacoes: dict[int, float] = {}

    absorvido: dict[int, Caixa] = {}
    for indice, caixa in enumerate(caixas):
        if caixa.altura >= piso_de_letra:
            continue
        melhor: int | None = None
        melhor_vao = vao_maximo
        for outro, base in enumerate(caixas):
            if base.altura < piso_de_letra:
                continue
            if outro not in inclinacoes:
                inclinacoes[outro] = _inclinacao_da_haste(binaria, base)
            # **Só o pingo acima da haste é projetado**, e o sinal é o do itálico: o topo pende à
            # direita, então o pingo volta para a esquerda pelo tanto que a inclinação o levou.
            deslocamento = (
                -inclinacoes[outro] * (base.y1 - caixa.y2) if caixa.y2 <= base.y1 else 0.0
            )
            if sobreposicao(caixa, base, deslocamento=deslocamento) < SOBREPOSICAO_MINIMA:
                continue
            # Acima da base (pingo, acento) ou abaixo dela (o ponto do `!` e do `?`).
            vao = base.y1 - caixa.y2 if caixa.y2 <= base.y1 else caixa.y1 - base.y2
            if 0 <= vao <= melhor_vao:
                melhor, melhor_vao = outro, vao
        if melhor is not None:
            absorvido[indice] = caixas[melhor]

    # **A ordem de entrada é preservada.** Quem ordena é `linhas.ordem_em_faixa`, e devolver uma
    # ordem diferente aqui esconderia um defeito dele atrás de um daqui.
    uniao: dict[int, Caixa] = {}
    for indice, base in absorvido.items():
        chave = caixas.index(base)
        atual = uniao.get(chave, base)
        pingo = caixas[indice]
        uniao[chave] = Caixa(
            min(atual.x1, pingo.x1),
            min(atual.y1, pingo.y1),
            max(atual.x2, pingo.x2),
            max(atual.y2, pingo.y2),
            atual.angulo,
        )

    return [uniao.get(i, caixa) for i, caixa in enumerate(caixas) if i not in absorvido]


def excluir_diagramas(
    caixas: list[Caixa],
    diagramas: list[tuple[float, float, float, float]],
    *,
    escala: int,
    margem: float = MARGEM_DIAGRAMA,
) -> list[Caixa]:
    """Tira do texto o que está dentro de um diagrama, **com margem**.

    A margem é o item: sem ela os rótulos das casas viram linhas de um caractere. Ver o
    cabeçalho. Os retângulos vêm em pixels da mesma imagem das caixas.
    """
    if not diagramas:
        return caixas

    folga = escala * margem
    inflados = [(x0 - folga, y0 - folga, x1 + folga, y1 + folga) for x0, y0, x1, y1 in diagramas]

    def dentro(caixa: Caixa) -> bool:
        centro_x = (caixa.x1 + caixa.x2) / 2.0
        centro_y = (caixa.y1 + caixa.y2) / 2.0
        return any(x0 <= centro_x <= x1 and y0 <= centro_y <= y1 for x0, y0, x1, y1 in inflados)

    return [caixa for caixa in caixas if not dentro(caixa)]


__all__ = [
    "CAIXA_CURTA",
    "FRACAO_MAXIMA_DE_CARACTERE",
    "MARGEM_DIAGRAMA",
    "MIN_AREA_GLIFO",
    "PROPORCAO_MAXIMA",
    "SOBREPOSICAO_MINIMA",
    "VAO_MAXIMO_DO_PINGO",
    "Caixa",
    "caixas_de_caractere",
    "escala_de_texto",
    "excluir_diagramas",
    "unir_pingos",
]
