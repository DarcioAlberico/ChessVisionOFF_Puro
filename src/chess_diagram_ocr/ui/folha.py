"""A folha de base do `ttk`: o acabamento dos widgets que o tema deixou vazios (S-441, S-442).

**O que havia antes.** O projeto inteiro tinha cinco `style.configure`, os cinco em `ui/theme.py`,
e eles cobriam fonte de tabela, fonte de título, altura de linha e a faixa de abas de *uma* pele.
Nenhum tocava a folga de widget nenhum, e a faixa de abas da pele clássica desenhava o rótulo
encostado na borda dos dois lados.

**Por que uma folha e não um `padding=` por sítio.** São 14 caixas de seleção, 8 botões de opção e
uma faixa de abas em três peles. Um `padding=` por sítio é a mesma aposta que a S-153 perdeu com a
altura de linha das duas tabelas: o primeiro que alguém esquecer fica no valor de fábrica, e
ninguém avisa. Redefinir a classe faz o acabamento valer por construção -- é o argumento de
`ESTILO_DE_TITULO`, aplicado ao resto da janela.

**O acabamento é da janela, e não da pele** (S-443). A folha é aplicada dentro de
`theme.registrar_estilos`, que roda para toda pele e todo tema. `Discreta.TNotebook` continua sendo
da pele "Foco", e o que ela mantém de próprio é `borderwidth=0` -- que é peso, não folga.

---

**A medição que reduziu este módulo à metade do que a spec pedia.**

A `SPEC_ACABAMENTO.md` abre dizendo que `padding` de um `ttk.Button` resolve para `1 1`. **Está
errado, e o erro é de bancada:** aquele número foi lido com o tema `vista`, que é o que responde
antes de `apply_theme` rodar. Sob os temas que o programa de fato usa a resposta é outra:

    classe            bootstrap-light / bootstrap-dark
    TButton           '10 4'          <- já vem folgado
    TMenubutton       '10 4 6 4'      <- já vem folgado
    TEntry            '5'             <- já vem folgado
    TCombobox         '5 6 7 4'       <- já vem folgado
    TNotebook.Tab     ''              <- vazio
    TCheckbutton      ''              <- vazio, e `indicatormargin` também
    TRadiobutton      ''              <- vazio, e `indicatormargin` também
    TSpinbox          ''              <- vazio, ao lado de um `TEntry` que tem 5
    TLabelframe       ''              <- vazio

**O `ttkbootstrap` cobre o que ele tematiza, e deixa vazio exatamente o que a fotografia mostrou
quebrado.** A aba sem folga e o indicador colado no rótulo não são "o Tk de 2009": são os dois
widgets que a biblioteca não desenha. Escrever a folha sobre os quatro primeiros foi medido e
**piorou** -- com `padding=(6, 2)` o botão de fita encolhe de 58 para 50 px de largura, porque 6 é
menos que os 10 que o tema já dava.

Daí a fronteira deste módulo: **a folha cobre quem o tema deixou vazio, e não encosta em quem ele
já resolveu.** Um dia em que o `ttkbootstrap` passe a tematizar a aba, esta folha vira uma linha a
menos -- e o teste que compara as três peles é quem vai avisar.

**Três coisas que a spec pedia e que não entram, e a ausência é decisão.**

**1 · `TFrame` não entra, e o número é grande.** Medido na janela montada: **117 `ttk.Frame`,
aninhados até 8 níveis**. Um `padding` de classe não se aplica ao ramo -- ele se aplica a *cada*
moldura do ramo, e no mais fundo isso são `8 x 10 x 2 = 160 px` de cada eixo, comidos por dentro.
`ttk.Frame` neste programa é caixa de arrumação, não superfície; quem quer moldura pede `padding=`
no sítio, como `left_frame` já faz.

**2 · `TSeparator` e `TScale` não têm folga a dar.** Nenhum dos dois desenha `padding`: o vão que
eles precisam é entre eles e o vizinho, e isso é `pady=` de quem empacota -- é a S-447, não esta.

**3 · `TButton` fica como está.** Ver a medição acima. E há um segundo motivo, que valeria mesmo se
o tema não o cobrisse: `padding=(10, 6)` custa **+51 px** nas duas barras do painel de PDF e faz o
`barra_livro` saltar de 98 para 138 px, quebrando em mais linhas porque cada botão fica 18 px mais
largo. Botão que muda de linha é controle que muda de lugar, e a regra 2 desta spec proíbe isso na
pele clássica.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from . import pele, tipografia

logger = logging.getLogger(__name__)

__all__ = [
    "CLASSES",
    "COM_INDICADOR",
    "RECHEIO",
    "aplicar",
    "recheio",
    "vao_do_indicador",
]

RECHEIO: dict[str, tuple[str, str]] = {
    "TNotebook.Tab": (tipografia.FOLGA_DE_MOLDURA, tipografia.FOLGA_DE_LINHA),
    "TCheckbutton": (tipografia.FOLGA_MINIMA, tipografia.FOLGA_MINIMA),
    "TRadiobutton": (tipografia.FOLGA_MINIMA, tipografia.FOLGA_MINIMA),
    "TSpinbox": (tipografia.FOLGA_DE_LINHA, tipografia.FOLGA_MINIMA),
    "TLabelframe": (tipografia.FOLGA, tipografia.FOLGA_DE_LINHA),
}
"""`classe ttk -> (papel de folga horizontal, papel de folga vertical)`.

**Nenhum pixel aqui, e é o item.** Todo número sai de `tipografia.FOLGAS`, o que faz a folha
acompanhar a fonte do sistema e encolher na densidade compacta sem uma segunda tabela para manter
-- que é o mesmo movimento que a S-149 fez com o tamanho de fonte e a S-232 com o espaço do cromo.

`TNotebook.Tab` é `(FOLGA_DE_MOLDURA, FOLGA_DE_LINHA)` porque isso resolve para `(14, 6)` na base
de referência, que é **exatamente** o valor que a S-226 mediu e aprovou para a faixa da pele
"Foco". A folha não inventa a folga da aba: ela generaliza a que já passou por revisão e a entrega
às três peles.

`TSpinbox` leva folga horizontal porque o vizinho dele na aba Configuração é um `TEntry`, que o
tema já dá com 5 -- dois campos de número lado a lado com recheio diferente é a inconsistência que
esta folha existe para não deixar acontecer.
"""

CLASSES: tuple[str, ...] = tuple(RECHEIO)
"""As classes que a folha alcança. Existe para o teste afirmar cobertura, como `PAPEIS_DE_FOLGA`."""

COM_INDICADOR: tuple[str, ...] = ("TCheckbutton", "TRadiobutton")
"""Quem desenha indicador à esquerda do rótulo, e por isso precisa do vão da S-442."""


def recheio(
    classe: str,
    *,
    base: int = tipografia.BASE_DE_REFERENCIA,
    densidade: str = pele.CONFORTAVEL,
) -> tuple[int, int]:
    """O `padding` `(horizontal, vertical)` daquela classe, em pixel. Pura: não toca `Style`.

    Levanta `KeyError` para classe fora da folha, e não devolve `(0, 0)`: uma classe escrita errada
    que caísse em zero desenharia o widget de fábrica e ninguém saberia dizer se aquilo era a folha
    ou a ausência dela. É a disciplina de `estilos.estilo_de_botao` e de `tokens.cor`.
    """
    if classe not in RECHEIO:
        raise KeyError(f"classe fora da folha de base: {classe!r}. As cobertas estão em CLASSES.")
    horizontal, vertical = RECHEIO[classe]
    return (
        tipografia.folga(horizontal, base=base, densidade=densidade),
        tipografia.folga(vertical, base=base, densidade=densidade),
    )


def vao_do_indicador(
    *,
    base: int = tipografia.BASE_DE_REFERENCIA,
    densidade: str = pele.CONFORTAVEL,
) -> int:
    """O vão entre o indicador e o rótulo de uma caixa de seleção, em pixel (S-442). Pura.

    Zero nos outros três lados: o vão que faltava é **entre** indicador e rótulo, e o espaço em
    volta do conjunto já é o `padding` da classe. Somar os dois lugares daria um controle que
    afasta o rótulo do indicador e a caixa inteira do vizinho, que é o dobro do pedido.

    O piso de `tipografia.folga` é 1 e vale aqui: dois vizinhos colados viram um controle só para o
    olho, e a densidade compacta existe para caber, não para fundir.
    """
    return tipografia.folga(tipografia.FOLGA_DE_LINHA, base=base, densidade=densidade)


def aplicar(
    style: ttk.Style,
    *,
    base: int = tipografia.BASE_DE_REFERENCIA,
    densidade: str = pele.CONFORTAVEL,
) -> None:
    """Escreve a folha no `Style`. Nunca levanta -- acabamento não derruba ferramenta.

    **Um `try` por classe, e não um em volta de tudo.** É a mesma razão pela qual
    `registrar_estilos` separa a tipografia da altura de linha: um tema que recuse `padding` num
    `TSpinbox` não pode levar junto a folga da faixa de abas. Cada classe que falhar sai no log com
    o nome, e as outras ficam de pé.
    """
    for classe in CLASSES:
        try:
            style.configure(classe, padding=recheio(classe, base=base, densidade=densidade))
        except tk.TclError as exc:  # pragma: no cover - tema que recusa `padding` naquela classe
            logger.info("Folha de base não aplicada em %s (%s).", classe, exc)

    # Bloco próprio porque o item é outro (S-442) e porque `indicatormargin` é a única opção desta
    # folha que não existe em todo tema `ttk` -- no `classic` ela não é lida. Um tema sem ela não
    # pode custar o `padding` das classes acima.
    vao = vao_do_indicador(base=base, densidade=densidade)
    for classe in COM_INDICADOR:
        try:
            style.configure(classe, indicatormargin=(0, 0, vao, 0))
        except tk.TclError as exc:  # pragma: no cover - tema sem `indicatormargin`
            logger.info("Vão do indicador não aplicado em %s (%s).", classe, exc)
