"""O piso da janela, calculado do que os painéis pedem (S-150).

**O defeito.** `app_tkinter.py` pedia 1700×980 e **nada** definia um piso: `root.minsize()`
nunca era chamado. Os `minsize` do `PanedWindow` (420 + 520) não impedem a janela de encolher
-- eles só disputam a posição do divisor.

Fotografado em 1100×760 com a aba Resultado aberta, a fila de ações do rodapé -- "Aplicar
FEN", "Salvar posição reconhecida", "Salvar todos", "Corrigir Net", "2ª opinião" -- é cortada
ao meio pela borda inferior, e não há rolagem que a alcance. Em 940×620, com o Dataset, somem
"Aplicar", "Limpar" e o botão **"Remover"**.

O programa continua funcionando -- `Ctrl+S` salva --, e é isso que torna o defeito difícil de
ver: ele não gera erro, gera um usuário que não sabe que existe um botão.

**O piso sai da soma e não do olho.** Um número redondo escolhido a olho envelhece junto com
os painéis; este acompanha, porque é calculado dos mesmos `minsize` que o `PanedWindow` usa.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "ALTURA_MINIMA_DO_CONTEUDO",
    "CHROME_HORIZONTAL",
    "CHROME_VERTICAL",
    "FRACAO_PADRAO_DO_DIVISOR",
    "PISO_MEDIDO",
    "VISIVEL_MINIMO",
    "Geometria",
    "fracao_de_divisor",
    "fracao_do_documento",
    "geometria_corrigida",
    "geometria_de_texto",
    "piso_da_janela",
    "visivel_em",
]

CHROME_HORIZONTAL = 60
"""Bordas, `padding` dos painéis e a alça do divisor -- o que não é conteúdo, na horizontal."""

CHROME_VERTICAL = 96
"""Abas do `Notebook`, barra de status e a moldura da janela."""

ALTURA_MINIMA_DO_CONTEUDO = 620
"""Altura em que a aba mais alta ainda mostra o tabuleiro e a fila de ações.

Vem do painel de Resultado, que é o mais alto dos seis: tabuleiro (520 de `min_size`) mais a
linha de FEN, a de legalidade e a fila de botões.
"""

PISO_MEDIDO = (1180, 800)
"""O piso que a avaliação da interface obteve **dirigindo a janela**, e não somando.

A soma dos painéis mais o *chrome* dá `(1000, 716)`, e ela é otimista: fotografada em
**1100×760** -- que a soma permitiria -- a fila de ações do Resultado ("Aplicar FEN", "Salvar
posição reconhecida", "Salvar todos", "Corrigir Net", "2ª opinião") sai cortada ao meio pela
borda inferior. O `minsize` dos painéis do `PanedWindow` mede o que o **divisor** aceita, não o
que o conteúdo precisa.

Então o piso é o **maior dos dois**: a soma continua valendo porque acompanha um painel que
cresça, e a medição continua valendo porque ela viu a janela.

**A altura de 800 não cabe num notebook de 1366×768, e por isso o piso sozinho nunca foi o
item.** Ela é o que o conteúdo precisa *sem rolagem*; quem fecha a lacuna é a segunda metade da
S-150, `ui/rolagem.py` -- Resultado, Configuração e Galeria rolam verticalmente, e o teste de
`tests/test_ui_rolagem.py` dirige a janela a 1366×768 para perguntar se o último botão da fila
de salvar chega ao viewport.

O piso continua sendo o que é: um piso menor devolveria o botão cortado em silêncio nas abas que
**não** rolam, e um piso maior travaria a janela acima de telas que existem. As duas metades
juntas é que dão a garantia inteira -- abaixo do piso a janela não vai, e acima dele nada fica
inalcançável.
"""


def piso_da_janela(
    largura_esquerda: int,
    largura_direita: int,
    *,
    chrome_horizontal: int = CHROME_HORIZONTAL,
    chrome_vertical: int = CHROME_VERTICAL,
    altura_do_conteudo: int = ALTURA_MINIMA_DO_CONTEUDO,
) -> tuple[int, int]:
    """`(largura, altura)` mínimas da janela, dados os `minsize` dos dois painéis.

    Função pura, e é o ponto: o piso é afirmável por teste contra a soma declarada, sem abrir
    janela. Se alguém aumentar o `minsize` de um painel, o piso acompanha -- e é isso que um
    número cravado não faz.
    """
    somado = (largura_esquerda + largura_direita + chrome_horizontal, altura_do_conteudo + chrome_vertical)
    return (max(somado[0], PISO_MEDIDO[0]), max(somado[1], PISO_MEDIDO[1]))


def fracao_do_documento(
    altura_da_janela: int,
    *,
    altura_do_cromo: int,
    chrome_vertical: int = CHROME_VERTICAL,
) -> float:
    """Que fração da altura da janela sobra para o documento. Pura (S-232).

    `altura_do_cromo` é o que a faixa de cromo da pele gasta -- a fita ou a fila --, e
    `chrome_vertical` é o resto, que sempre esteve lá: abas, barra de status e moldura.

    **Existe para que "o painel do PDF fica com >= 60% da altura" seja uma conta e não uma
    fotografia.** É a mesma escolha de `fita.altura_da_fita`: um orçamento medido no widget
    montado só falha depois de a janela já estar errada, e numa largura que o teste por acaso
    escolheu.

    **O que ela não modela**, e fica dito para que ninguém a leia como mais do que é: as duas
    barras do próprio painel de PDF e a linha de conjunto de campo entram por `chrome_vertical`,
    que é uma estimativa e não uma soma item a item. A fração devolvida é um **teto**.
    """
    if altura_da_janela <= 0:
        return 0.0
    return max(0.0, (altura_da_janela - chrome_vertical - altura_do_cromo) / altura_da_janela)


# ------------------------------------------------------- a janela lembrada entre execuções (S-156)

FRACAO_PADRAO_DO_DIVISOR = 0.42
"""Onde o divisor fica quando não há nada guardado.

Era o número cravado em `_set_initial_sashes`, aplicado **toda** abertura: quem trabalha com o
PDF grande arrastava o divisor toda sessão e o perdia toda sessão. Agora ele é o padrão da
primeira execução, e não a decisão de todas elas."""

VISIVEL_MINIMO = 80
"""Quantos pixels da janela precisam cair dentro de algum monitor para a geometria valer.

Não é zero e não é a janela inteira. **Zero** aceitaria uma janela inteiramente fora da tela --
o caso do monitor que foi desconectado, em que a janela some sem erro nenhum e o programa
parece não ter aberto. **A janela inteira** recusaria o arranjo legítimo de quem deixa uma
borda para fora de propósito. 80 px é mais que a barra de título e menos que qualquer arranjo
deliberado: sobra para agarrar e arrastar de volta."""

_GEOMETRIA = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")
"""O formato do Tk: `LARGURAxALTURA+X+Y`, com `-` para coordenada negativa (monitor à esquerda)."""


@dataclass(frozen=True)
class Geometria:
    """Tamanho e posição de uma janela, no formato que o Tk fala."""

    largura: int
    altura: int
    x: int
    y: int

    def __str__(self) -> str:
        return f"{self.largura}x{self.altura}{self.x:+d}{self.y:+d}"

    @property
    def retangulo(self) -> tuple[int, int, int, int]:
        """`(x0, y0, x1, y1)`, que é como os monitores também são descritos."""
        return (self.x, self.y, self.x + self.largura, self.y + self.altura)


def geometria_de_texto(texto: str) -> Geometria | None:
    """Lê uma geometria do Tk. `None` para qualquer coisa que não seja uma.

    Recusar em vez de adivinhar: um estado corrompido que virasse `0x0+0+0` abriria uma janela
    invisível, e o usuário não teria como saber que o culpado é um arquivo de estado.
    """
    casou = _GEOMETRIA.match(str(texto).strip())
    if casou is None:
        return None
    largura, altura, x, y = (int(grupo) for grupo in casou.groups())
    return Geometria(largura, altura, x, y) if largura > 0 and altura > 0 else None


def visivel_em(geometria: Geometria, monitores: Sequence[tuple[int, int, int, int]], *, minimo: int = VISIVEL_MINIMO) -> bool:
    """Se a janela tem pelo menos `minimo` px de sobreposição com **algum** monitor, nos dois eixos.

    Nos dois eixos, e não em área: uma janela que cruza 2.000 px de largura e 3 px de altura de
    um monitor tem 6.000 px² de sobreposição e é, na prática, invisível.
    """
    jx0, jy0, jx1, jy1 = geometria.retangulo
    for mx0, my0, mx1, my1 in monitores:
        if min(jx1, mx1) - max(jx0, mx0) >= minimo and min(jy1, my1) - max(jy0, my0) >= minimo:
            return True
    return False


def geometria_corrigida(
    geometria: Geometria,
    monitores: Sequence[tuple[int, int, int, int]],
    *,
    piso: tuple[int, int] = PISO_MEDIDO,
    minimo: int = VISIVEL_MINIMO,
) -> Geometria:
    """A geometria a aplicar de verdade: a guardada, ou uma centrada no monitor principal.

    **Os dois casos que este item existe para tratar**, e os dois vêm de trocar de máquina ou de
    monitor entre uma sessão e a seguinte:

    - *o monitor desapareceu*: a janela estava em `+2560+0` e agora só há um monitor de 1920 —
      restaurar a geometria abriria a janela fora da tela, sem erro nenhum a que se agarrar;
    - *cabe em parte*: o monitor novo é menor, e a janela guardada é maior que ele.

    A correção é conservadora: mantém o tamanho quando ele cabe, encolhe até o monitor quando
    não cabe (respeitando o piso da S-150) e centraliza. Sem lista de monitores, devolve a
    geometria como veio — não saber onde estão as telas não é razão para mover a janela.
    """
    if not monitores:
        return geometria
    if visivel_em(geometria, monitores, minimo=minimo):
        return geometria

    mx0, my0, mx1, my1 = monitores[0]
    largura = max(piso[0], min(geometria.largura, mx1 - mx0))
    altura = max(piso[1], min(geometria.altura, my1 - my0))
    return Geometria(largura, altura, mx0 + max(0, (mx1 - mx0 - largura) // 2), my0 + max(0, (my1 - my0 - altura) // 2))


def geometria_a_aplicar(
    guardada: str,
    monitores: Sequence[tuple[int, int, int, int]],
    *,
    piso: tuple[int, int] = PISO_MEDIDO,
) -> str | None:
    """O texto de geometria a passar ao Tk, ou `None` para "deixe a janela como está".

    Junta as três decisões da restauração num lugar só — ler, validar contra os monitores de
    agora, e devolver texto —, e é o que faz a janela ter **uma** linha sobre isto em vez de
    doze. `None` cobre os dois casos em que não há o que restaurar: nunca foi guardada, e o que
    foi guardado não é uma geometria.
    """
    lida = geometria_de_texto(guardada)
    if lida is None:
        return None
    return str(geometria_corrigida(lida, monitores, piso=piso))


def geometria_gravavel(atual: str) -> str:
    """A geometria a guardar, ou `""` quando a de agora não vale a pena.

    **Janela minimizada não conta.** O Tk devolve `1x1+-32000+-32000` para uma janela
    minimizada no Windows, e gravar isso faria a sessão seguinte abrir uma janela de 1 px fora
    da tela. Devolver vazio preserva o arranjo bom que já estava guardado, em vez de trocá-lo
    por um que a restauração teria de recusar.
    """
    lida = geometria_de_texto(atual)
    return atual if lida is not None and lida.largura > 1 and lida.altura > 1 else ""


def fracao_de_divisor(posicao: int, largura: int) -> float:
    """Onde o divisor está, como fração da largura. Grampeada para nunca esconder um painel.

    Os limites não são estéticos: o `PanedWindow` aceita `sash_place` fora deles e o painel do
    outro lado fica com zero pixel de largura -- estado do qual não há gesto de mouse que
    devolva, porque a alça do divisor fica colada na borda da janela.
    """
    if largura <= 0:
        return FRACAO_PADRAO_DO_DIVISOR
    return max(0.15, min(0.85, posicao / largura))
