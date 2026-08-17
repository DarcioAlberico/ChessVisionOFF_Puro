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

__all__ = [
    "ALTURA_MINIMA_DO_CONTEUDO",
    "CHROME_HORIZONTAL",
    "CHROME_VERTICAL",
    "PISO_MEDIDO",
    "piso_da_janela",
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

**A altura de 800 não cabe num notebook de 1366×768, e isso é o item pela metade.** Ela é o que
o conteúdo precisa hoje *sem rolagem*; quem fecha a lacuna é a segunda metade da S-150 -- as
abas rolando verticalmente --, que não foi entregue. Sem ela, num 1366×768 a janela pede mais
altura do que a tela tem. Está registrado assim de propósito: um piso menor devolveria o botão
cortado em silêncio, que é o defeito original.
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
