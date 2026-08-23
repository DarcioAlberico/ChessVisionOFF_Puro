"""Texto impresso em negativo — branco sobre tarja preta ou colorida (S-195).

Livro de xadrez põe o cabeçalho da partida numa tarja: *"J.Bolbochan – L.Pachman"* em branco
sobre um retângulo preto. A binarização deixa a tinta em branco, então a tarja inteira vira um
borrão, `findContours` com `RETR_EXTERNAL` devolve **um** box e os vinte caracteres de dentro
somem. Medido no projeto de origem, na página 33 do Yusupov: 6 tarjas, 6 boxes, **zero
caracteres**. No *Chess Evolution 1* são 264 páginas com tarja em quase toda partida.

## Três decisões, e cada uma tem cicatriz

**1. A polaridade é do box, não da página.** Inverter a página inteira seria mais simples e está
descartado: o usuário confere o box contra a página impressa, e mexer no que ele vê para
consertar o que o modelo lê troca um problema de leitura por um de revisão.

**2. A faixa é aparada antes de ser lida.** Acima da tarja há uma tira decorativa hachurada,
clara o bastante para virar tinta na inversão; ela encosta no topo das letras e funde meia linha
num componente só -- medido, uma tarja de 20 caracteres devolvia 88 componentes, dois deles com
metade da tarja cada. Linha de retângulo cheio tem ~100% de tinta, linha de tira hachurada tem
55%-75%:

    0.27 0.54 ... 0.74 | 0.98 1.00 0.99 0.97 | 0.86 ... 0.90 | 0.99 0.99 | 0.24
    \\___ tira hachurada _/ \\__ borda da tarja _/ \\_ o texto _/ \\_ borda _/

**Não aparar é a resposta certa quando não há borda cheia**, e não uma desistência: é a tarja de
tom fraco, em que a binarização marca 60%-87% e nenhuma linha chega ao piso. Quando a apara era
condição de aceite, a tarja *"6...♘bd7"* do Kasparov -- cinza, legível, nove caracteres -- era
recusada, e o texto ficava perdido do mesmo jeito de antes.

**3. O que decide não é o formato da faixa, é o que tem dentro.** Uma faixa cheia pode ser tarja,
foto, logotipo ou barra de rodapé. Inverte-se e conta-se quantos componentes têm tamanho de
caractere **em relação à altura da própria faixa** -- a régua está dentro dela, e não na mediana
da página, que não é confiável para medir glifo (medido: 4 px numa página contra 18 px na
seguinte).

## O caso perigoso é a palavra sublinhada, e não a foto

O sublinhado gruda as letras num componente cheio e largo, e os *vazados* do `n` e do `a` viram
"glifos" plausíveis. Aceitá-la **substituiria por lixo um texto que o caminho normal já lia
certo**. Quem a recusa são duas medidas juntas, e nenhuma sozinha:

    tarja de verdade      proporção 5,34 - 13,70    altura 2,57 - 28,50 escalas
    palavra sublinhada    proporção 3,00 -  4,72    altura 0,41 -  1,21

## O limite conhecido, registrado e não corrigido

Com o glifo medido contra a altura da faixa, a razão cai a cada linha a mais. A tarja de duas
linhas do Kasparov (715x112, letras de ~35 px) passa em 0,31, raspando no piso de 0,30, e uma de
três linhas não passaria. A correção óbvia -- deduzir a altura da linha agrupando os próprios
componentes -- é também a que aceitaria a palavra sublinhada, cujos vazados se agrupam tão bem
quanto letras.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from .boxes import Caixa

PREENCHIMENTO = 0.55
"""Fração de tinta acima da qual a caixa é bloco cheio, e não traço de glifo.

Medido, a tarja com o texto já carvado fica em 0,73-0,86 no Yusupov e em 0,66-0,88 no Kasparov; o
limiar fica abaixo das duas faixas de propósito, porque tarja de tom fraco perde tinta na
binarização. **Sozinho ele não separa nada** -- palavra em negrito com sublinhado chega a 0,68."""

RAZAO = 4.0
"""A tarja é bem mais larga que alta. Ver a tabela do cabeçalho.

O preço está registrado: uma tarja mais curta que 4:1 -- um rótulo colorido de uma palavra só --
não é vista. Abaixo dessa proporção ela é indistinguível de uma palavra em negrito com sublinhado,
e essa palavra o caminho normal já lê certo."""

ALTURA_MINIMA = 8
"""Altura mínima em pixels. Abaixo disto não cabe caractere legível nem a 150 dpi."""

ALTURA_TARJA = 2.0
"""A tarja tem de ser mais alta que isto, em escalas de caractere. Ver a tabela do cabeçalho.

**A mediana falha num lugar conhecido, e quem cobre é a proporção.** Numa página de sumário, com
centenas de pontos de preenchimento, ela desce a 8 px enquanto a letra mede 22 -- e o fragmento
*"ening"* de um título em negrito chega a 2,75 escalas. Ele é recusado por ter proporção 3,09."""

SOLIDO = 0.90
"""Tinta de uma linha (ou coluna) da borda do retângulo cheio."""

MAX_APARA = 0.40
"""Quanto a apara pode comer de cada eixo. Passando disto ela não está achando a borda de um
retângulo, está comendo o miolo -- e o eixo volta inteiro, para a decisão ficar com o conteúdo."""

ALTURA_GLIFO = (0.30, 0.95)
"""Altura de um glifo em frações da altura da faixa.

O piso deixa passar a pontuação (o ponto de "J.Bolbochan" tem 0,07 e entra por `MIN_RUIDO`); o
teto recusa o que atravessa a tarja de borda a borda."""

LARGURA_GLIFO = 1.5
"""Largura máxima de um glifo, em alturas da faixa. Mais largo é fusão de letras coladas: não
conta para a **decisão**, mas continua virando caixa -- quem as separa é a S-186."""

MIN_GLIFOS = 3
"""Quantos glifos de tamanho plausível fazem uma faixa ser texto."""

MIN_RUIDO = 0.06
"""Abaixo disto, em frações da altura da faixa, o componente é respingo do papel dentro da tarja e
não vira caixa. O ponto final e a vírgula ficam acima."""


def positivar(recorte: np.ndarray) -> np.ndarray:
    """O recorte com a tinta escura sobre fundo claro, **como o modelo o viu no treino**.

    Mora num lugar só pelo mesmo motivo que `vertical.endireitar`: para ninguém ter de lembrar do
    sinal. Ver a nota sobre polaridade em `modelo.ClassificadorDeGlifo._entrada`.
    """
    return 255 - recorte


def _preenchimento(binaria: np.ndarray, caixa: Caixa) -> float:
    recorte = caixa.recortar(binaria)
    return float((recorte > 0).mean()) if recorte.size else 0.0


def candidatos(binaria: np.ndarray, caixas: Sequence[Caixa], *, escala: int) -> list[Caixa]:
    """Caixas cheias, largas e mais altas que um caractere -- **só geometria**.

    Nada aqui afirma que a caixa é tarja: quem afirma é `ler_faixa`, depois de olhar o que há
    dentro. Ver "O que decide não é o formato da faixa" no cabeçalho.
    """
    piso = max(ALTURA_MINIMA, int(ALTURA_TARJA * escala))
    return [
        caixa
        for caixa in caixas
        if caixa.altura >= piso
        and caixa.largura >= caixa.altura * RAZAO
        and _preenchimento(binaria, caixa) >= PREENCHIMENTO
    ]


def _apara(perfil: np.ndarray) -> tuple[int, int]:
    """`(início, fim)` do miolo cheio. **Eixo sem borda cheia volta inteiro** -- ver o cabeçalho."""
    inicio, fim = 0, len(perfil)
    while inicio < fim and perfil[inicio] < SOLIDO:
        inicio += 1
    while fim > inicio and perfil[fim - 1] < SOLIDO:
        fim -= 1
    if inicio >= fim or (inicio + len(perfil) - fim) > MAX_APARA * len(perfil):
        return 0, len(perfil)
    return inicio, fim


def faixa_solida(binaria: np.ndarray, caixa: Caixa) -> Caixa | None:
    """A caixa encolhida até o retângulo cheio, ou `None` para caixa vazia.

    **Parar na primeira linha cheia é o que impede a apara de comer o miolo**: as linhas do meio
    da tarja são as que o texto carvou, e são justamente as que não passam de `SOLIDO`.
    """
    regiao = caixa.recortar(binaria) > 0
    if regiao.size == 0:
        return None

    y0, y1 = _apara(regiao.mean(axis=1))
    x0, x1 = _apara(regiao[y0:y1].mean(axis=0))
    if y1 <= y0 or x1 <= x0:
        return None
    return Caixa(caixa.x1 + x0, caixa.y1 + y0, caixa.x1 + x1, caixa.y1 + y1)


def glifos_da_faixa(cinza: np.ndarray, faixa: Caixa) -> list[Caixa]:
    """As caixas de caractere de dentro da faixa, em coordenadas da página.

    A faixa é invertida e rebinarizada com o limiar dela: dentro da tarja o papel some da conta e
    sobram duas populações, e o Otsu local separa as duas onde o global não separava nada.
    """
    recorte = faixa.recortar(cinza)
    if recorte.size == 0:
        return []

    invertido = positivar(recorte)
    _, binaria = cv2.threshold(invertido, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    piso = MIN_RUIDO * faixa.altura
    saida = []
    for contorno in contornos:
        x, y, largura, altura = cv2.boundingRect(contorno)
        if altura < piso or largura <= 0:
            continue
        saida.append(Caixa(faixa.x1 + x, faixa.y1 + y, faixa.x1 + x + largura, faixa.y1 + y + altura))
    return saida


def parece_texto(glifos: Sequence[Caixa], faixa: Caixa) -> bool:
    """A faixa invertida tem cara de texto? **A régua está dentro dela** -- ver o cabeçalho."""
    piso, teto = (f * faixa.altura for f in ALTURA_GLIFO)
    largura_maxima = LARGURA_GLIFO * faixa.altura
    plausiveis = sum(1 for g in glifos if piso <= g.altura <= teto and g.largura <= largura_maxima)
    return plausiveis >= MIN_GLIFOS


def ler_faixa(cinza: np.ndarray, faixa: Caixa) -> list[Caixa] | None:
    """Os caracteres da tarja, ou `None` quando ela não é tarja de texto.

    `None` é caminho normal, e não erro: uma foto, um logotipo e uma barra de rodapé passam pela
    geometria de `candidatos` e param aqui.
    """
    glifos = glifos_da_faixa(cinza, faixa)
    return glifos if parece_texto(glifos, faixa) else None


def substituir_tarjas(
    cinza: np.ndarray,
    binaria: np.ndarray,
    caixas: Sequence[Caixa],
    *,
    escala: int,
) -> tuple[list[Caixa], list[Caixa]]:
    """`(caixas com as tarjas trocadas pelos caracteres, as faixas aceitas)`.

    A saída é **ordenada por `(y1, x1)`, e isso não é cortesia**: no projeto de origem, devolver
    as caixas novas no fim da lista fazia o merge vertical casar uma letra da tarja lá em cima com
    um box lá embaixo, a caixa resultante atravessava a página e passava a absorver tudo que
    cruzasse a coluna dela. Medido: os 1.889 boxes de uma página saíram do merge como **27**.
    """
    faixas: list[Caixa] = []
    trocadas: dict[int, list[Caixa]] = {}

    for candidata in candidatos(binaria, caixas, escala=escala):
        faixa = faixa_solida(binaria, candidata)
        if faixa is None:
            continue
        glifos = ler_faixa(cinza, faixa)
        if glifos is None:
            continue
        faixas.append(faixa)
        trocadas[id(candidata)] = glifos

    saida: list[Caixa] = []
    for caixa in caixas:
        saida.extend(trocadas.get(id(caixa), [caixa]))
    saida.sort(key=lambda c: (c.y1, c.x1))
    return saida, faixas


__all__ = [
    "ALTURA_GLIFO",
    "ALTURA_MINIMA",
    "ALTURA_TARJA",
    "LARGURA_GLIFO",
    "MAX_APARA",
    "MIN_GLIFOS",
    "MIN_RUIDO",
    "PREENCHIMENTO",
    "RAZAO",
    "SOLIDO",
    "candidatos",
    "faixa_solida",
    "glifos_da_faixa",
    "ler_faixa",
    "parece_texto",
    "positivar",
    "substituir_tarjas",
]
