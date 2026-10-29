"""O caderno do livro no EPUB/DOCX da suíte: as folhas corrigidas, num formato que a suíte lê (R7).

**O defeito.** Há três guardas de texto de livro inteiro: o caderno (S-610), onde a aba Texto
corrige folha a folha; a aba **Revisão de texto** (SOL-11), que grava no IR da suíte; e *Exportar o
livro para EPUB…/DOCX…*, que escreve desse IR. A tarde de correção feita na aba Texto não chegava
ao EPUB: a suíte relia o livro e escrevia a leitura dela, como se o caderno não existisse.

**O que vai.** Só as folhas em que uma pessoa mexeu (`Caderno.corrigidas`: editadas e conferidas).
A folha só lida é o motor deste programa, e trocar a leitura da suíte pela de outro motor não é
correção -- é escolher motor, e quem escolhe o motor da exportação é a suíte.

**Por que dado neutro, e não o IR.** O tronco não importa `caissa` (num checkout a suíte é um
repositório vizinho, de outro Python), e a suíte não importa este pacote. O que atravessa é uma
lista de dicionários de tipos simples -- o formato de `caissa.export.page_texts.PageText`, versão
`FORMATO` --, montada aqui sem toolkit e testável sem a suíte. Quem a converte em `Paragraph` e
`Heading`, e decide onde os diagramas da página ficam, é a suíte.

O formato, por folha::

    {"format": 1, "page_index": 11, "state": "conferida", "saved_at": "2026-10-28T10:00:00",
     "paragraphs": [
        {"kind": "text", "style": "heading", "alignment": "center",
         "runs": [{"text": "Capítulo 3", "bold": true}]},
        {"kind": "diagram", "fen": "8/8/8/8/8/8/8/8", "alignment": "center"},
     ]}

`style` é `"heading"`, `"notation"`, `"caption"` ou `""` (prosa); `alignment` é `"left"`,
`"center"`, `"right"`, `"justify"` ou `""` (o da folha). A cor de autor, o realce e o corpo não
vão: o IR os teria, mas o caderno os usa para marcar trabalho, e o livro publicado não é o lugar.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .caderno import Caderno, EstadoDaFolha
from .rico import (
    ALINHAMENTO_CENTRO,
    ALINHAMENTO_DIREITA,
    ALINHAMENTO_ESQUERDA,
    ALINHAMENTO_JUSTIFICADO,
    ESTILO_LEGENDA,
    ESTILO_NOTACAO,
    ESTILO_TITULO,
    Corrida,
    DocumentoRico,
    alinhamento_efetivo,
)

__all__ = ["folhas_para_a_suite"]

FORMATO = 1
"""A versão do formato que `caissa.export.page_texts` lê. Muda junto com a de lá, nunca sozinha."""

_ESTILO: dict[str, str] = {ESTILO_TITULO: "heading", ESTILO_NOTACAO: "notation", ESTILO_LEGENDA: "caption"}
_ALINHAMENTO: dict[str, str] = {
    ALINHAMENTO_ESQUERDA: "left",
    ALINHAMENTO_CENTRO: "center",
    ALINHAMENTO_DIREITA: "right",
    ALINHAMENTO_JUSTIFICADO: "justify",
}
_ENFASES = ("bold", "italic", "underline", "strike")


def _enfase(corrida: Corrida) -> dict[str, bool]:
    a = corrida.atributos
    valores = (a.negrito, a.italico, a.sublinhado, a.tachado)
    return {nome: True for nome, ligado in zip(_ENFASES, valores, strict=True) if ligado}


def _paragrafo_de_texto(pedacos: list[tuple[Corrida, str]]) -> dict[str, Any] | None:
    """Um parágrafo a partir dos pedaços de corrida dele, ou `None` se ele é só branco."""
    if not "".join(texto for _, texto in pedacos).strip():
        return None
    primeira = next(c for c, texto in pedacos if texto.strip())
    runs: list[dict[str, Any]] = []
    for corrida, texto in pedacos:
        enfase = _enfase(corrida)
        if runs and {k: v for k, v in runs[-1].items() if k != "text"} == enfase:
            runs[-1]["text"] += texto  # a mesma ênfase partida em duas corridas é um trecho só
        else:
            runs.append({"text": texto, **enfase})
    runs[0]["text"] = runs[0]["text"].lstrip()
    runs[-1]["text"] = runs[-1]["text"].rstrip()
    return {
        "kind": "text",
        "style": _ESTILO.get(primeira.atributos.estilo, ""),
        "alignment": _ALINHAMENTO.get(primeira.atributos.alinhamento, ""),
        "runs": [r for r in runs if r["text"]],
    }


def paragrafos_da_folha(doc: DocumentoRico) -> list[dict[str, Any]]:
    """Os parágrafos da folha, na ordem da tela, com os diagramas no lugar em que estão. Pura.

    Cada quebra de linha fecha um parágrafo -- é o que o `Enter` faz no editor --, e o separador
    entre dois blocos da página também. Linha em branco não vira parágrafo vazio. O estilo e o
    alinhamento do parágrafo são os da primeira corrida com texto dele: os dois são atributos de
    parágrafo (`ATRIBUTOS_DE_PARAGRAFO`), e o editor os aplica ao parágrafo inteiro.
    """
    saida: list[dict[str, Any]] = []
    pedacos: list[tuple[Corrida, str]] = []

    def fechar() -> None:
        paragrafo = _paragrafo_de_texto(pedacos)
        if paragrafo is not None:
            saida.append(paragrafo)
        pedacos.clear()

    for corrida in doc.corridas:
        if corrida.e_diagrama:
            fechar()
            placement = str(getattr(doc.bloco_de(corrida), "placement", "") or "")
            saida.append(
                {
                    "kind": "diagram",
                    "fen": placement,
                    "alignment": _ALINHAMENTO.get(alinhamento_efetivo(corrida), ""),
                }
            )
            continue
        linhas = corrida.texto.split("\n")
        for i, linha in enumerate(linhas):
            if i:
                fechar()
            if linha:
                pedacos.append((corrida, linha))
    fechar()
    return saida


def folha_para_a_suite(doc: DocumentoRico, estado: EstadoDaFolha) -> dict[str, Any]:
    """A folha no formato da suíte. `estado` é a linha do índice dela (`Caderno.estado`)."""
    return {
        "format": FORMATO,
        "page_index": int(estado.pagina),
        "state": estado.estado,
        "saved_at": estado.gravada_em,
        "paragraphs": paragrafos_da_folha(doc),
    }


def folhas_para_a_suite(cad: Caderno, paginas: Iterable[int] | None = None) -> list[dict[str, Any]]:
    """As folhas **corrigidas** do caderno (0-based em `paginas`; `None` = o livro), no formato da suíte.

    A folha cujo arquivo não abre fica de fora com o aviso que `Caderno.folha` já dá: a suíte
    escreve a leitura dela, e é o mesmo que acontecia antes de o caderno ir ao EPUB.
    """
    pedidas = None if paginas is None else {int(p) for p in paginas}
    saida: list[dict[str, Any]] = []
    for estado in cad.corrigidas():
        if pedidas is not None and estado.pagina not in pedidas:
            continue
        doc = cad.folha(estado.pagina)
        if doc is not None:
            saida.append(folha_para_a_suite(doc, estado))
    return saida
