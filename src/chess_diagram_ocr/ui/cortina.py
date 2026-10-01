# Origem: Editor_Diagramas_de_Xadrez/src/chess_pdf_editor/widgets.py
#         (`SelectablePageWidget.set_curtain_pixmap`, `curtain_fraction`, `curtain_split_x`,
#          `_near_curtain`, `_curtain_fraction_at`, `curtain_band`, `_paint_curtain`,
#          `_paint_curtain_labels`).
# Absorvido em 2026-09-07. Alterações: a geometria saiu do widget e virou um valor congelado --
#         lá a fração, o grampeamento, a alça e a caixa de cada rótulo eram atributos e métodos
#         de um `QLabel`, e afirmá-los exigia montar a página inteira. Aqui a única coisa que o
#         Qt ainda responde é a **medida do texto**, que é do toolkit por natureza e entra como
#         argumento (ver `rotulos`).
"""A cortina de comparação: onde está a divisa entre o antes e o depois (F9).

**O que a cortina é, e por que ela foi o que se decidiu preservar.** Substituir um diagrama num
livro é uma edição destrutiva sobre uma página que a pessoa não escreveu. A pergunta que ela faz
o tempo todo -- *"ficou melhor ou pior do que estava?"* -- não se responde com duas miniaturas
lado a lado, porque o que importa é o **encaixe**: se o tabuleiro novo cobre exatamente o antigo,
se a folga comeu a legenda, se a coordenada `a`--`h` do livro sobrou emoldurando o desenho novo.
Uma divisa arrastável sobre a **mesma** página responde isso num gesto, porque põe os dois estados
no mesmo lugar da tela em vez de em dois lugares.

É o mesmo instrumento que um comparador de imagens de referência usa, e o que o faz funcionar são
três detalhes que este módulo guarda:

1. **a divisa vai de ponta a ponta**, para poder ser agarrada na altura em que o olho já está;
2. **a alça e os rótulos são ancorados no que está visível**, e não no bitmap -- uma página de
   livro é muito mais alta que o visor, e uma alça no meio do bitmap passa a vida inteira fora
   da tela;
3. **os dois lados são nomeados**. Uma linha sozinha não informa a direção: sem o par
   `antes`/`depois` a pessoa não sabe qual metade é a original, e passa a arrastar até as pontas
   para descobrir.

**Por que a fração, e não a posição em pixel.** A página é re-rasterizada a cada zoom e a cada
virada; guardar pixel faria a divisa saltar para outro ponto do papel a cada mudança de escala.
A fração é a mesma coisa em qualquer zoom, e é o que se guarda entre uma página e a seguinte.

Sem toolkit aqui, como em `ui/tokens.py` e `ui/page_overlay.py`: a divisa, a faixa, a alça e as
caixas dos rótulos são retângulos de `float`, e é isso que permite afirmar o comportamento de
arrastar sem abrir janela. Quem os pinta é `qt/pagina_selecionavel.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

__all__ = [
    "ANTES",
    "DEPOIS",
    "FOLGA_DO_ROTULO",
    "FRACAO_INICIAL",
    "LARGURA_MINIMA_PARA_ROTULOS",
    "MEIA_ALCA",
    "TOLERANCIA_DE_CLIQUE",
    "Cortina",
    "Faixa",
    "Rotulo",
]

FRACAO_INICIAL = 0.5
"""A divisa nasce no meio. Meio porque é o único ponto que não afirma nada sobre a página: um
padrão de 0,25 ou 0,75 sugeriria que um dos dois lados é o assunto, e ele não é."""

MEIA_ALCA = 7.0
"""Metade da largura da alça, em pixel de tela. A alça mede o dobro disto de largura e o
quádruplo de altura -- proporção de pega vertical, que é a direção em que ela **não** anda."""

TOLERANCIA_DE_CLIQUE = 12.0
"""A que distância da divisa um clique ainda a agarra.

**Maior que o desenho de propósito**, e é a mesma razão da tolerância das alças da seleção:
a linha tem 3 px, e acertar 3 px com o ponteiro é sorte, não gesto. Doze é o que a origem usou e
o que sobrevive ao teste do dedo trêmulo sem invadir a página inteira."""

LARGURA_MINIMA_PARA_ROTULOS = 220.0
"""Abaixo desta largura de página os dois rótulos não cabem sem cobrir o que se está comparando.

Some-se: duas caixas de ~60 px, mais 8 px de vão de cada lado da divisa, mais o que sobra de
página para o olho. Numa miniatura estreita a divisa continua funcionando e sem legenda -- o que
não pode acontecer é a legenda tapar o diagrama, que é o objeto da comparação."""

FOLGA_DO_ROTULO = 8.0
"""Vão entre a divisa e a caixa do rótulo, e distância do topo da faixa visível."""

ANTES = "antes"
DEPOIS = "depois"
"""As duas palavras, em caixa baixa.

**Não estão em `ui/strings.py`** porque não são frase de interface e sim rótulo desenhado dentro
de um `paintEvent`, medido em pixel e comparado com a largura da página -- o critério de lá é
"texto que nomeia um comando", e nenhum destes dois nomeia coisa alguma. Ficam aqui, ao lado da
regra que decide se cabem."""


@dataclass(frozen=True)
class Faixa:
    """A parte da página que está de fato à vista, em pixel de tela.

    Existe como tipo, e não como quatro argumentos soltos, porque ela é a âncora de **tudo** o
    que se desenha por cima da cortina -- alça e rótulos --, e passá-la inteira é o que impede
    que um deles seja ancorado no bitmap por engano.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def meio_y(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def vazia(self) -> bool:
        return not (self.x1 > self.x0 and self.y1 > self.y0)


@dataclass(frozen=True)
class Rotulo:
    """Um dos dois nomes e a caixa em que ele é desenhado."""

    texto: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class Cortina:
    """A divisa sobre uma página de `largura` × `altura`, em `fracao` da largura.

    Congelada, e cada ajuste devolve outra: é um valor, não um estado. O widget guarda a
    instância em vigor e a troca; o que ele **não** faz é guardar `_fracao` solta e recalcular a
    posição em três lugares, que é como a origem tinha e é o que faz a alça e a linha
    discordarem no dia em que uma das contas mudar.
    """

    largura: float = 0.0
    altura: float = 0.0
    fracao: float = FRACAO_INICIAL

    # ------------------------------------------------------------------------------ a divisa

    @property
    def posicao(self) -> float:
        """Onde a divisa está, em pixel do widget."""
        return self.largura * self.fracao

    def com_fracao(self, fracao: float) -> Cortina:
        """A mesma cortina noutra fração, **grampeada** em `[0, 1]`.

        Grampear e não recusar: o valor chega de um arrasto, e o arrasto passa da borda o tempo
        todo -- quem arrasta para fora da janela está pedindo "tudo de um lado", e é isso que ele
        recebe. Recusar deixaria a divisa parada a 3 px da ponta, o que se lê como travamento.
        """
        return replace(self, fracao=min(1.0, max(0.0, float(fracao))))

    def com_pagina(self, largura: float, altura: float) -> Cortina:
        """A mesma fração noutra página. É o que a troca de zoom e a virada de página chamam.

        **A fração sobrevive e a posição não**, e é o argumento inteiro de a cortina ser guardada
        em fração: quem comparava o pé da página continua comparando o pé da página depois de um
        zoom, em vez de ver a divisa saltar para o meio do papel.
        """
        return replace(self, largura=max(0.0, float(largura)), altura=max(0.0, float(altura)))

    def fracao_em(self, x: float) -> float:
        """A fração que corresponde àquele `x` de tela. Página sem largura devolve a atual."""
        if self.largura <= 0:
            return self.fracao
        return min(1.0, max(0.0, float(x) / self.largura))

    def perto(self, x: float, *, tolerancia: float = TOLERANCIA_DE_CLIQUE) -> bool:
        """Um clique naquele `x` agarra a divisa?

        **Só o eixo horizontal conta**, e é decisão: a linha cruza a página inteira justamente
        para poder ser agarrada na altura em que a pessoa já está olhando. Exigir também
        proximidade vertical faria a alça ser o único ponto de pega, e a alça é um *anúncio* de
        que a linha se arrasta -- não o alvo.
        """
        return abs(float(x) - self.posicao) <= tolerancia

    # ------------------------------------------------------------------------------ o desenho

    def revelado(self) -> tuple[float, float, float, float]:
        """O recorte em que o "depois" é pintado: da divisa até a borda direita.

        **O depois fica à direita, e o bitmap de baixo continua sendo o original.** Isso importa
        para um caso específico: cortina desligada é a página original, sem nenhum caminho de
        código a mais. Se o "depois" fosse o fundo, desligar a cortina exigiria repintar -- e o
        instante entre uma coisa e outra mostraria o resultado onde se prometeu o original.
        """
        return (self.posicao, 0.0, max(self.posicao, self.largura), self.altura)

    def divisa(self, *, espessura: float = 3.0) -> tuple[float, float, float, float]:
        """O retângulo da própria linha, de ponta a ponta da página."""
        return (self.posicao - espessura / 2.0, 0.0, self.posicao + espessura / 2.0, self.altura)

    def faixa_visivel(self, visivel: Faixa | None) -> Faixa:
        """A faixa em que alça e rótulos se ancoram. Sem visor, a página inteira.

        Fora de um visor -- um `grab()` num widget nunca exibido, que é o caso do teste e da
        captura de tela -- `visibleRegion()` do Qt devolve região vazia. Cair na página inteira ali
        é o que faz a captura mostrar a alça em vez de um retângulo que o widget acha que está
        fora da tela.
        """
        if visivel is None or visivel.vazia:
            return Faixa(0.0, 0.0, self.largura, self.altura)
        return visivel

    def alca(self, visivel: Faixa | None = None, *, meia: float = MEIA_ALCA) -> tuple[float, float, float, float]:
        """A pega, centrada na altura do que está à vista.

        Sem ela a linha não se anuncia como arrastável -- e uma linha clara sobre uma página
        clara é indistinguível de um artefato de rasterização.
        """
        faixa = self.faixa_visivel(visivel)
        centro = faixa.meio_y
        return (self.posicao - meia, centro - meia * 2.0, self.posicao + meia, centro + meia * 2.0)

    def rotulos(
        self,
        larguras_do_texto: tuple[float, float],
        altura_do_texto: float,
        visivel: Faixa | None = None,
        *,
        recheio: float = 5.0,
    ) -> tuple[Rotulo, ...]:
        """As caixas de `antes` e `depois`, ou vazio quando não cabem.

        `larguras_do_texto` é `(largura de "antes", largura de "depois")` **medida pelo toolkit** --
        é a única coisa daqui que depende de fonte, e ela entra como argumento em vez de o módulo
        importar `QFontMetricsF`. É a mesma fronteira de `ui/tipografia.py`: a escala é pura, e
        quem sabe medir letra é quem tem a janela.

        Um rótulo que não caberia inteiro na página **não é desenhado**, e o outro continua. Meio
        rótulo cortado pela borda é pior que nenhum: ele diz "antes" mostrando "ant".
        """
        if self.largura < LARGURA_MINIMA_PARA_ROTULOS:
            return ()
        faixa = self.faixa_visivel(visivel)
        topo = faixa.y0 + FOLGA_DO_ROTULO
        altura_da_caixa = altura_do_texto + recheio
        saida: list[Rotulo] = []
        for texto, largura_do_texto, a_esquerda in (
            (ANTES, larguras_do_texto[0], True),
            (DEPOIS, larguras_do_texto[1], False),
        ):
            largura_da_caixa = largura_do_texto + recheio * 2.0
            x0 = (
                self.posicao - FOLGA_DO_ROTULO - largura_da_caixa
                if a_esquerda
                else self.posicao + FOLGA_DO_ROTULO
            )
            if x0 < 0.0 or x0 + largura_da_caixa > self.largura:
                continue
            saida.append(Rotulo(texto, x0, topo, x0 + largura_da_caixa, topo + altura_da_caixa))
        return tuple(saida)
