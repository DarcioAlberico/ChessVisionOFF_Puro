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

## E a volta (R7 de volta, 2026-10-29)

As regiões que alguém **editou** na Revisão de texto da suíte voltam ao caderno, no mesmo formato
(`caissa.export.reviewed_pages`). A regra é do dono do projeto:

- a folha **sem correção no caderno** (só lida, ou sem caderno) recebe o texto da suíte, e fica
  `editada` -- a leitura do motor que estava nela vai para `anterior`;
- a folha **corrigida nos dois lados** fica como o caderno a tem, e a versão da suíte vai para
  `anterior`, onde «Voltar à versão anterior» a alcança. A correção feita aqui não é desfeita por
  uma feita lá.

A folha que volta precisa de origem (`Caderno.gravar` não grava folha sem página): é a da folha que
o caderno já tem quando ela tem tantos diagramas quanto as marcas da suíte -- e aí as miniaturas
continuam recortadas da página --, e senão uma página feita só dos diagramas da suíte, com a
posição de cada um.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from . import correcao
from .caderno import EDITADA, GRAVADA, IGUAL, LIDA, Caderno, EstadoDaFolha
from .pagina import BlocoDeDiagrama, Coluna, PaginaLida
from .rico import (
    ALINHAMENTO_CENTRO,
    ALINHAMENTO_DIREITA,
    ALINHAMENTO_ESQUERDA,
    ALINHAMENTO_JUSTIFICADO,
    DIAGRAMA,
    ESTILO_LEGENDA,
    ESTILO_NOTACAO,
    ESTILO_TITULO,
    SEPARADOR,
    Atributos,
    Corrida,
    DocumentoRico,
    alinhamento_efetivo,
    fundir,
)

__all__ = ["Volta", "folha_da_suite", "folhas_para_a_suite", "trazer_da_suite"]

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


# ------------------------------------------------------------------------------------- a volta

_ESTILO_DE_VOLTA: dict[str, str] = {nome: estilo for estilo, nome in _ESTILO.items()}
_ALINHAMENTO_DE_VOLTA: dict[str, str] = {nome: alinhamento for alinhamento, nome in _ALINHAMENTO.items()}


def _origem_para(paragrafos: list[Mapping[str, Any]], origem: PaginaLida | None, *, livro: str, pagina: int) -> PaginaLida:
    """A origem da folha que volta: a que o caderno já tem, se os diagramas batem; senão a da suíte."""
    marcas = [p for p in paragrafos if p.get("kind") == "diagram"]
    if origem is not None and len(origem.diagramas) == len(marcas):
        return origem
    blocos = tuple(
        BlocoDeDiagrama(indice=k, procedencia="humano", placement=str(marca.get("fen", "")).split(" ")[0])
        for k, marca in enumerate(marcas)
    )
    return PaginaLida(documento=livro, pagina=pagina, colunas=(Coluna(indice=0, blocos=blocos),))


def folha_da_suite(dados: Mapping[str, Any], *, origem: PaginaLida | None = None, livro: str = "") -> DocumentoRico:
    """Uma folha no formato da suíte, de volta a documento do caderno. O inverso de `folha_para_a_suite`.

    O texto é `humano` -- uma pessoa o escreveu na revisão -- e cada parágrafo é separado do seguinte
    como o leitor separa os blocos. A marca de cada diagrama aponta para o diagrama da origem na
    mesma ordem. `ValueError` para um formato que este programa não conhece.
    """
    versao = dados.get("format", FORMATO)
    if versao != FORMATO:
        raise ValueError(f"formato de folha da suíte desconhecido: {versao!r}")
    pagina = int(dados["page_index"])
    paragrafos = list(dados.get("paragraphs", ()))
    base = _origem_para(paragrafos, origem, livro=livro, pagina=pagina)
    diagramas = [i for i, bloco in enumerate(base.blocos) if isinstance(bloco, BlocoDeDiagrama)]
    corridas: list[Corrida] = []
    proximo = 0
    for paragrafo in paragrafos:
        if paragrafo.get("kind") == "diagram":
            if proximo >= len(diagramas):  # pragma: no cover - `_origem_para` garante as marcas
                continue
            indice = diagramas[proximo]
            proximo += 1
            pedaco = [Corrida(texto=base.blocos[indice].texto, bloco=indice, tipo=DIAGRAMA)]
        else:
            estilo = _ESTILO_DE_VOLTA.get(str(paragrafo.get("style", "")), "")
            alinhamento = _ALINHAMENTO_DE_VOLTA.get(str(paragrafo.get("alignment", "")), "")
            pedaco = [
                Corrida(
                    texto=str(trecho.get("text", "")),
                    atributos=Atributos(
                        negrito=bool(trecho.get("bold")),
                        italico=bool(trecho.get("italic")),
                        sublinhado=bool(trecho.get("underline")),
                        tachado=bool(trecho.get("strike")),
                        estilo=estilo,
                        alinhamento=alinhamento,
                    ),
                    procedencia="humano",
                )
                for trecho in paragrafo.get("runs", ())
                if trecho.get("text")
            ]
            if not pedaco:
                continue
        if corridas:
            corridas.append(Corrida(texto="\n\n", tipo=SEPARADOR))
        corridas.extend(pedaco)
    return DocumentoRico(corridas=fundir(corridas), origem=base)


@dataclass(frozen=True)
class Volta:
    """O que `trazer_da_suite` fez, folha a folha (0-based)."""

    trazidas: tuple[int, ...] = ()
    """Folhas sem correção no caderno que receberam o texto da suíte."""
    guardadas: tuple[int, ...] = ()
    """Folhas corrigidas nos dois lados: o caderno ficou, a da suíte foi para `anterior`."""
    iguais: tuple[int, ...] = ()
    """Folhas em que a suíte diz o mesmo que o caderno: nada a fazer."""
    recusadas: tuple[int, ...] = ()
    """Folhas que o caderno não gravou (somente leitura, ou o disco recusou)."""

    def frase(self) -> str:
        """O resumo para o rodapé, folhas contadas de 1."""
        if not (self.trazidas or self.guardadas or self.iguais or self.recusadas):
            return "Nenhuma folha foi editada na Revisão de texto da suíte."
        partes = []
        if self.trazidas:
            partes.append(f"{len(self.trazidas)} folha(s) trazida(s) da revisão ({_lista(self.trazidas)})")
        if self.guardadas:
            partes.append(
                f"{len(self.guardadas)} já corrigida(s) aqui, com a da revisão em «anterior» ({_lista(self.guardadas)})"
            )
        if self.iguais:
            partes.append(f"{len(self.iguais)} igual(is) ao caderno")
        if self.recusadas:
            partes.append(f"{len(self.recusadas)} não gravada(s) ({_lista(self.recusadas)})")
        return "; ".join(partes) + "."


def _lista(paginas: tuple[int, ...]) -> str:
    return ", ".join(str(p + 1) for p in paginas)


def trazer_da_suite(cad: Caderno, folhas: Iterable[Mapping[str, Any]], *, livro: str = "") -> Volta:
    """Põe no caderno as folhas editadas na Revisão de texto, pela regra do dono (ver o cabeçalho)."""
    trazidas: list[int] = []
    guardadas: list[int] = []
    iguais: list[int] = []
    recusadas: list[int] = []
    for dados in folhas:
        pagina = int(dados["page_index"])
        estado = cad.estado(pagina)
        atual = cad.folha(pagina) if estado is not None else None
        doc = folha_da_suite(dados, origem=atual.origem if atual is not None else None, livro=livro)
        if atual is not None and atual.corridas == doc.corridas:
            iguais.append(pagina)
            continue
        try:
            if estado is not None and estado.estado != LIDA:
                feito = cad.guardar_anterior(doc)
                (guardadas if feito == GRAVADA else recusadas).append(pagina)
                continue
            cad.visitar(pagina)  # a leitura do motor que estava nela vai para `anterior`
            feito = cad.gravar(doc, estado=EDITADA, correcoes=max(1, len(correcao.correcoes(doc))))
        except OSError:
            recusadas.append(pagina)
            continue
        if feito == GRAVADA:
            trazidas.append(pagina)
        elif feito == IGUAL:
            iguais.append(pagina)
        else:
            recusadas.append(pagina)
    return Volta(tuple(trazidas), tuple(guardadas), tuple(iguais), tuple(recusadas))
