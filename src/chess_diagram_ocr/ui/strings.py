"""Vocabulário compartilhado da interface (S-04).

**O que entra aqui, e o que não.** Não é um catálogo de todas as strings: um dicionário com
duzentas constantes usadas uma vez cada troca um literal legível por uma indireção, e piora
o código de layout sem nada em troca. Entra o que **duas telas precisam dizer igual** ou o
que tem significado além do texto.

**Por que isso importa, medido.** Os rótulos de procedência do lado a jogar existiam em dois
lugares -- `ui/result_panel.py` e o Streamlit (hoje `examples/streamlit_demo.py`) -- e já
tinham divergido: o Tkinter
dizia "deduzido da posicao" e o Streamlit "deduzido da legalidade da posicao"; "assumido"
contra "assumido (o PDF nao diz)". É o mesmo mecanismo da S-31 aplicado a texto -- duas
implementações do mesmo conceito, e a segunda seguindo por conta própria.

**A acentuação é a outra metade.** A Fase 0 deixou as strings sem acento ("posicao",
"Configuracao") porque centralizá-las dependia da decomposição do Tkinter, que só veio na
6.2. `WORDS_REQUIRING_ACCENTS` é a lista que o teste usa para impedir que voltem.
"""

from __future__ import annotations

SIDE_SOURCE_LABELS: dict[str, str] = {
    "text": "declarado no texto do PDF",
    "ocr": "lido por OCR da legenda",
    "text-page-scope": "declarado no cabeçalho da página",
    "ocr-page-scope": "lido por OCR do cabeçalho da página",
    "legality": "deduzido da legalidade da posição",
    "default": "assumido (o PDF não diz)",
    "manual": "definido por você",
    "queue": "vindo da fila de revisão",
}
"""De onde saiu o lado a jogar (S-16/S-17/S-19).

Aparece ao lado do rádio "Brancas/Pretas" nas duas telas e no header
`[SideToMoveSource]` do PGN. "Pretas jogam" lido de uma legenda e "pretas jogam" assumido
pelo padrão têm o mesmo texto e valores completamente diferentes para quem vai conferir --
é essa diferença que o rótulo carrega, e por isso ele não pode variar entre as telas."""

SIDE_SOURCE_CONFLICT = "texto e posição discordam — confira"
"""A discordância da S-17 tem rótulo próprio porque não é uma procedência: é o aviso de que
duas fontes se contradizem e uma delas está errada."""

DETECTION_SOURCE_LABELS: dict[str, str] = {
    "embedded": "imagem embutida no PDF",
    "contour": "contorno detectado na página",
    "hybrid": "imagem embutida, alinhada pelo contorno",
}
"""Como o diagrama foi localizado (S-12). Vale para auditar o dataset por fonte."""

ORIENTATION_LABELS: dict[str, str] = {
    "auto": "Automática",
    "0": "0 graus",
    "180": "180 graus",
}
"""Tri-estado da S-13, no lugar do checkbox que valia para a página inteira."""


def side_source_label(source: str, *, conflicting: bool = False) -> str:
    """Rótulo de procedência do lado a jogar, ou `""` quando não há o que dizer."""
    if conflicting:
        return SIDE_SOURCE_CONFLICT
    return SIDE_SOURCE_LABELS.get(source, "")


def detection_source_label(source: str) -> str:
    """Rótulo da fonte de detecção. Devolve o valor cru se for um que não conhecemos."""
    return DETECTION_SOURCE_LABELS.get(source, source)


WORDS_REQUIRING_ACCENTS: tuple[str, ...] = (
    "analise",
    "apos",
    "area",
    "automatica",
    "cabeca",
    "codigo",
    "conclusao",
    "conclusoes",
    "confianca",
    "configuracao",
    "configuracoes",
    "continuacao",
    "continuacoes",
    "correcao",
    "correcoes",
    "decisao",
    "decisoes",
    "deteccao",
    "disponivel",
    "epoca",
    "execucao",
    "execucoes",
    "exportacao",
    "exportacoes",
    "indisponivel",
    "informacao",
    "informacoes",
    "invalida",
    "invalido",
    "maximo",
    "media",
    "memoria",
    "metricas",
    "minimo",
    "nao",
    "numero",
    "opcao",
    "opcoes",
    "orientacao",
    "orientacoes",
    "padrao",
    "padroes",
    "pagina",
    "peca",
    "plausivel",
    "plausiveis",
    "posicao",
    "posicoes",
    "possivel",
    "promocao",
    "proximo",
    "revisao",
    "revisoes",
    "sao",
    "selecao",
    "selecoes",
    "tambem",
    "ultimo",
    "usuario",
    "versao",
    "voce",
)
"""Palavras que, sem acento, estão erradas em pt-BR.

Serve ao teste que impede a regressão da pendência 0.7. É uma lista de raízes: o teste
compara ignorando plural e gênero, para que "posicoes" e "invalidos" também sejam pegos."""
