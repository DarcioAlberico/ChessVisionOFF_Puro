"""O negrito vem da camada de texto, e nunca da imagem (S-211).

**A metade que funciona, e a metade que foi medida e recusada.** Negrito é atributo de forma, e há
dois lugares de onde tirá-lo: o nome da fonte na camada de texto do PDF, que é **metadado** e não
erra, e a espessura do traço na imagem, que é palpite. Este módulo faz só o primeiro.

## Por que a imagem ficou de fora, com número

Medido em 2026-08-24 sobre 940 palavras rotuladas pela camada, em 3 livros:

    medida                 melhor acerto    chutar "normal" sempre
    espessura do traço            82,2%              82,7%
    densidade de tinta            85,6%              82,7%

A espessura **não passa do acaso**. A densidade passa um pouco, e a acurácia engana com 17% de
positivos -- a curva de verdade é esta:

    corte    cobertura   precisão
    0,410      81,0%       46,8%
    0,448      54,0%       58,3%
    0,474      29,4%       63,2%     melhor F1 = 0,60

**Metade do que fosse marcado sairia errado.** Subir de 220 para 400 dpi não muda (86,6% contra
85,6%): o problema não é resolução, é que a densidade depende mais do limiar de binarização e do
corpo da fonte do que do peso. A régua deste projeto para aplicar em lote é 99,29% (S-213).

> **Um erro de método que vale ficar escrito.** A primeira medição normalizou a espessura pela
> **mediana da linha**, e isso apaga o sinal justamente quando a linha inteira é negrito -- que é o
> caso comum: título, lance principal. Normalizar pela linha só faria sentido se o negrito fosse
> sempre parcial dentro dela.

## A cobertura é irregular, e o desconhecido é dito

Dos 42 livros do acervo: **13 têm negrito na camada**, 16 têm camada sem nenhum negrito, e 10 não
têm camada. Por isso `negrito` é `bool | None` e não `bool`: `None` é **"não se sabe"**, e é
diferente de `False`. Um livro cuja camada não registra peso nenhum não pode declarar que nada ali
é negrito -- ele não sabe.

## A unidade era a linha, e deixou de ser (2026-08-28)

A `PaginaLida` não tinha unidade menor que a `LinhaLida`, então uma linha meio em negrito era
decidida pela **maioria** da largura dela: onde o negrito é a linha inteira -- título, variante
principal -- o resultado é exato, e onde ele é um lance no meio da prosa era grosso.

**Medido, o "grosso" era quase metade.** Em 8 folhas de cada um dos 45 PDFs do acervo, das 969
linhas com peso na camada **428 (44,2%) misturam peso dentro de si**: 281 somem (cobrem menos de
60% e a linha sai normal) e 147 incham (a linha toda sai em negrito por causa da maioria). A S-429
desceu a régua ao caractere -- `linhas_de_negrito` mais `camada.trechos` --, e a `LinhaLida` passou
a carregar os intervalos em `negrito_em`.

O campo de linha **continua o que era**, com a mesma maioria de 60%: quem o lê -- `BlocoDeTexto`,
`paragrafos.cortar`, `documento.estado_do_negrito` -- não mudou uma linha, e onde não há intervalo
é ele que desenha. Ver "A régua desceu ao caractere" em `text/camada.py`.

## O peso também corta parágrafo (2026-08-25)

**Ler o peso certo não basta: ele tem de sobreviver à montagem do bloco.** `BlocoDeTexto.de_linhas`
só declara o negrito do bloco quando **todas** as linhas concordam, e por boa razão -- ver o
comentário lá. Mas isso torna o corte de parágrafo parte desta régua: um parágrafo que junta prosa
e lance sai `negrito=None`, e a aba passa a dizer *"o livro não informa"* numa página em que o
livro informa cada lance.

Na folha 51 do `Dvoretsky` era o que acontecia em **cinco dos oito** parágrafos de texto: lá a
prosa e a notação se alternam com entrelinhamento constante, e nem o recuo nem o salto de
`text/paragrafos.py` veem o corte. A quarta regra de lá -- *o peso mudou* -- é o conserto, e a
população em que ela vale é a mesma deste módulo: onde `negrito` é `None`, ela fica inerte.

Medido em 2026-08-25 sobre 96 folhas dos 12 livros que registram peso: **94 dos 1.557 blocos de
texto (6,0%) misturavam peso dentro de si**, e todos eram parágrafo grudado.

## A máquina saiu daqui (2026-08-25)

`spans → cobertura → marcar` era geometria genérica escrita dentro do módulo do negrito, e a S-236
já tinha registrado que o itálico da camada precisava dela. Ela agora mora em `text/camada.py`, e
este módulo é o que sobrou: **o nome de fonte e o bit que denunciam peso**, mais a delegação. Os
nomes públicos continuam os mesmos, e quem os importa não muda uma linha.
"""

from __future__ import annotations

import re

from . import camada

FONTE_NEGRITO = re.compile(r"bold|black|heavy|semib|demi", re.I)
"""O nome da fonte que denuncia peso. `Times-Bold`, `Calibri-Black`, `Helvetica-SemiBold`.

Vale junto com o bit `2**4` de `flags`, que o PyMuPDF preenche a partir do descritor da fonte --
os dois porque nenhum dos dois sozinho pega tudo: há PDF com o nome sem o bit, e vice-versa."""

BIT_DE_NEGRITO = 2**4
"""O bit de negrito em `span["flags"]` do `get_text("dict")`."""

COBERTURA_MINIMA = camada.COBERTURA_MINIMA
"""Fração da largura da linha que precisa estar em negrito para a linha inteira contar como tal.

Maioria, e não qualquer sobreposição: uma linha de prosa com **um** lance em negrito no meio não é
uma linha em negrito, e marcá-la assim seria pior que não marcar. Ver a limitação declarada no
cabeçalho. **O número mora em `text/camada.py`**, porque a régua é a mesma para o itálico."""

PAGINAS_DE_AMOSTRA = camada.PAGINAS_DE_AMOSTRA
"""Quantas páginas se olham para decidir se o **documento** registra negrito.

A pergunta não é da página: uma página de prosa sem nenhum negrito num livro que o registra é um
`False` legítimo, e num livro que não o registra é um `None`. Quem separa as duas é o documento, e
por isso a amostra é dele."""


Retangulo = camada.Retangulo


def _span_e_negrito(span: dict) -> bool:
    """O nome da fonte **ou** o bit. Ver `FONTE_NEGRITO`."""
    return bool(FONTE_NEGRITO.search(str(span.get("font", "")))) or bool(
        int(span.get("flags", 0)) & BIT_DE_NEGRITO
    )


def spans_de_negrito(page: object) -> list[Retangulo]:
    """Os retângulos em negrito da página, em **pontos do PDF**. Vazio quando não há nenhum."""
    return camada.spans_com(page, _span_e_negrito)


def linhas_de_negrito(page: object) -> list[camada.LinhaDeCamada]:
    """As linhas da camada com o peso marcado **caractere a caractere** (S-429).

    O irmão fino de `spans_de_negrito`: aquele serve à régua de maioria da linha, este serve aos
    intervalos que a `LinhaLida` carrega em `negrito_em`. Ver "A régua desceu ao caractere" em
    `text/camada.py`, com o número que a mediu."""
    return camada.linhas_com(page, _span_e_negrito)


def documento_registra_negrito(doc: object, *, amostra: int = PAGINAS_DE_AMOSTRA) -> bool:
    """Este documento registra peso de fonte em algum lugar? Ver `text/camada.py`."""
    return camada.documento_registra(doc, _span_e_negrito, amostra=amostra, marca="negrito")


cobertura = camada.cobertura
"""A geometria da cobertura, que hoje mora em `text/camada.py`. Ver "A máquina saiu daqui"."""

marcar = camada.marcar
"""A decisão por linha, que hoje mora em `text/camada.py`. Ver "A máquina saiu daqui"."""


__all__ = [
    "BIT_DE_NEGRITO",
    "COBERTURA_MINIMA",
    "FONTE_NEGRITO",
    "PAGINAS_DE_AMOSTRA",
    "cobertura",
    "documento_registra_negrito",
    "linhas_de_negrito",
    "marcar",
    "spans_de_negrito",
]
