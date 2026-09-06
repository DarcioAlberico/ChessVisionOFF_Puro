"""O estudo e o texto em DOCX, escritos como OOXML mínimo com `zipfile` (S-543).

**Por que OOXML à mão, e não `python-docx`.** O `.venv` do projeto não tem `python-docx`, e o item
não o instala: um extra `[docx]` seria a exportação que "não está disponível" na máquina de quem
edita -- o mesmo argumento de `epub.py`. Um `.docx` é um zip com seis partes obrigatórias
(`[Content_Types].xml`, `_rels/.rels`, `word/document.xml`, `word/styles.xml`,
`word/_rels/document.xml.rels` e, quando há imagem, `word/media/`), e este módulo escreve as seis com
a biblioteca padrão. O que se perde é o que não se usa: tabelas, cabeçalhos, revisão.

**O diagrama vai em par: PNG e SVG.** O `a:blip` aponta o PNG de `diagrama_png.py` -- é o que todo
leitor de `.docx` desenha, do LibreOffice ao celular. Na extensão `asvg:svgBlip` vai o SVG de
`diagrama_svg.py`, que o Word de 2016 em diante prefere e imprime como vetor. É exatamente o par que
o próprio Word grava quando alguém cola um SVG nele; um DOCX só com SVG abre em branco fora do Word
novo, e um só com PNG serrilha no papel. Para o diagrama do texto **sem posição lida**, o PNG é o
recorte injetado por quem chama (`imagens=`), sem SVG; sem nem isso, sai a marca `[Diagrama N]`,
que **nunca desaparece** (regra da S-250).

**Os parágrafos são os de `estudo_paragrafos.py`**, a mesma lista que o EPUB lê: título, diagrama,
comentário, lance e variante. Os estilos nomeados no Word são esses -- `heading 1`/`heading 2`,
`Lance` (negrito), `Variante` (itálico, recuado), `Comentário`, `Legenda` -- e quem abrir o arquivo
pode retocá-los na galeria de estilos em vez de caçar parágrafo por parágrafo. Para o texto do livro,
a formatação
inline (negrito, itálico, sublinhado, tachado, cor, realce, corpo) vem de `Atributos`, e a cor e o
corpo chegam **resolvidos de fora** (`cores=`, `corpos=`), pelos mesmos mapas de `exportacao.Html`:
nenhum hexadecimal é escrito aqui (regra 3 da SPEC_EDITOR).

**O que faz um `.docx` ser um documento e não uma tira de parágrafos**: o campo `TOC` na primeira
página, que o Word e o LibreOffice preenchem com os títulos; o cabeçalho com o título do livro; e o
rodapé com o campo `PAGE`, porque um livro de novecentas páginas sem número de página não se
consulta. Cada um é uma parte a mais no zip (`word/header1.xml`, `word/footer1.xml`) e uma
referência no `sectPr` -- e `word/settings.xml` com `updateFields`, que é o que faz o Word
oferecer-se para montar o índice ao abrir.

`verificar` é a conferência que se faz sem Word: zip, XML bem formado em toda parte, todo tipo de
conteúdo declarado, toda relação apontando um membro do zip, todo `r:embed` do documento com a sua
relação. O teste a roda sobre o que este módulo escreve.
"""

from __future__ import annotations

import datetime as _dt
import html as _html
import io
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from chess_diagram_ocr import diagrama_png, diagrama_svg, estudo_paragrafos
from chess_diagram_ocr.atomic_io import atomic_write_bytes
from chess_diagram_ocr.epub import PRODUTOR, Metadados
from chess_diagram_ocr.estudo import Estudo
from chess_diagram_ocr.text import documento as _documento
from chess_diagram_ocr.text import exportacao, rico

__all__ = [
    "ESTILOS",
    "LARGURA_PADRAO_CM",
    "SUBTITULO",
    "TITULO",
    "Documento",
    "Metadados",
    "Relatorio",
    "exportar_estudo_docx",
    "exportar_estudos_docx",
    "exportar_texto_docx",
    "exportar_textos_docx",
    "verificar",
]

LARGURA_PADRAO_CM = 7.6
"""O lado do diagrama na página, em centímetros. É o `18em` do EPUB a 12 pt: metade da coluna A4."""

EMU_POR_CM = 360000
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
NS_ASVG = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS_CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_DCTERMS = "http://purl.org/dc/terms/"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

REL_OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
REL_CORE = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
REL_APP = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"
REL_STYLES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
REL_SETTINGS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings"
REL_HEADER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
REL_FOOTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
URI_SVG = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"

RID_ESTILOS = "rId1"
RID_CONFIGURACAO = "rId2"
RID_CABECALHO = "rId3"
RID_RODAPE = "rId4"
"""As quatro relações fixas do documento. As imagens entram depois delas, em `_media`."""

TIPOS_DE_CONTEUDO: Mapping[str, str] = {
    "rels": "application/vnd.openxmlformats-package.relationships+xml",
    "xml": "application/xml",
    "png": "image/png",
    "svg": "image/svg+xml",
}
TIPO_DO_DOCUMENTO = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
TIPO_DOS_ESTILOS = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
TIPO_DA_CONFIGURACAO = "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"
TIPO_DO_CABECALHO = "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
TIPO_DO_RODAPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
TIPO_DO_NUCLEO = "application/vnd.openxmlformats-package.core-properties+xml"
TIPO_DO_APLICATIVO = "application/vnd.openxmlformats-officedocument.extended-properties+xml"

CAMPO_DE_SUMARIO = ' TOC \\o "1-3" \\h \\z \\u '
"""O campo que vira o índice do Word. `\\o "1-3"` recolhe os três primeiros níveis de título, `\\h`
faz cada linha um vínculo, `\\z` esconde o número de página na visão web e `\\u` usa o nível de
estrutura do estilo. O texto que vai no lugar do resultado é a instrução de atualizar (F9) -- o
Word só numera as páginas quando pagina, e ninguém aqui pagina."""

TITULO = "Heading1"
SUBTITULO = "Heading2"
LANCE = "Lance"
VARIANTE = "Variante"
VARIANTE_2 = "Variante2"
COMENTARIO = "Comentario"
LEGENDA = "Legenda"
DIAGRAMA = "Diagrama"
MARCA = "Marca"

NOME_DO_TITULO = "heading 1"
NOME_DO_SUBTITULO = "heading 2"
"""**O nome do estilo, e não o `styleId`, é o que faz um parágrafo virar título.**

O `w:name` de um estilo interno do Word é sempre o nome inglês da especificação -- `heading 1` --, e
é o Word que o mostra localizado ("Título 1") na galeria de estilos. Quem lê o arquivo casa esse
nome: o Calibre casa `heading\\s+(\\d+)$` sobre ele e só então escreve `<h1>`; o painel de navegação
do Word e o `TOC` fazem o mesmo. Na primeira rodada o estilo se chamava `Título`, com acento e sem o
número -- não casava nada, e o Calibre relatava *"Auto generated TOC with 0 entries"* sobre um
documento com 2.618 títulos. `outlineLvl` sozinho não resolve: ele é o nível na estrutura, não o
papel do estilo."""

ESTILOS: Mapping[str, tuple[str, str, str]] = {
    "Normal": ("Normal", "", '<w:sz w:val="22"/>'),
    TITULO: (
        NOME_DO_TITULO,
        '<w:keepNext/><w:spacing w:before="360" w:after="160"/><w:outlineLvl w:val="0"/>',
        '<w:b/><w:sz w:val="32"/>',
    ),
    SUBTITULO: (
        NOME_DO_SUBTITULO,
        '<w:keepNext/><w:spacing w:before="280" w:after="120"/><w:outlineLvl w:val="1"/>',
        '<w:b/><w:sz w:val="26"/>',
    ),
    LANCE: ("Lance", '<w:spacing w:after="120"/>', "<w:b/>"),
    VARIANTE: ("Variante", '<w:ind w:left="720"/><w:spacing w:after="120"/>', "<w:i/>"),
    VARIANTE_2: ("Variante 2", '<w:ind w:left="1440"/><w:spacing w:after="120"/>', "<w:i/>"),
    COMENTARIO: ("Comentário", '<w:spacing w:after="120"/>', ""),
    LEGENDA: ("Legenda", '<w:jc w:val="center"/><w:spacing w:after="240"/>', '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="16"/>'),
    DIAGRAMA: ("Diagrama", '<w:keepNext/><w:jc w:val="center"/><w:spacing w:before="120" w:after="60"/>', ""),
    MARCA: ("Marca de diagrama", '<w:jc w:val="center"/><w:spacing w:before="120" w:after="120"/>', ""),
}
"""`id -> (nome visível, pPr, rPr)`. **São os mesmos cinco papéis do CSS do EPUB**, mais os dois de
figura: `p.lance` é `Lance`, `p.variante` é `Variante`, `p.variante.nivel-2` é `Variante 2`."""

ALINHAMENTOS: Mapping[str, str] = {
    rico.ALINHAMENTO_ESQUERDA: "left",
    rico.ALINHAMENTO_CENTRO: "center",
    rico.ALINHAMENTO_DIREITA: "right",
    rico.ALINHAMENTO_JUSTIFICADO: "both",
}

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
_PONTOS = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*pt\s*$")


@dataclass(frozen=True)
class Relatorio:
    """O que a exportação escreveu, contado (S-254 vale aqui também)."""

    caminho: Path
    tamanho: int
    paragrafos: int
    diagramas: int
    png: int = 0
    svg: int = 0
    so_marca: int = 0
    avisos: tuple[str, ...] = ()

    def resumo(self) -> str:
        """Uma linha em pt-BR para a barra de estado."""
        partes = [f"{self.paragrafos} parágrafo(s)", f"{self.diagramas} diagrama(s)"]
        if self.png:
            partes.append(f"{self.png} em PNG")
        if self.svg:
            partes.append(f"{self.svg} também em SVG")
        if self.so_marca:
            partes.append(f"{self.so_marca} só com a marca")
        return f"{self.caminho} ({self.tamanho // 1024} KB): " + ", ".join(partes)


# ------------------------------------------------------------------------------ o documento


class Documento:
    """O `.docx` em construção: parágrafos, imagens e relações, até `empacotar`."""

    def __init__(self, metadados: Metadados | None = None) -> None:
        self.metadados = (metadados or Metadados()).resolvidos()
        self.corpo: list[str] = []
        self.media: dict[str, bytes] = {}
        self.relacoes: list[tuple[str, str, str]] = [
            (RID_ESTILOS, REL_STYLES, "styles.xml"),
            (RID_CONFIGURACAO, REL_SETTINGS, "settings.xml"),
            (RID_CABECALHO, REL_HEADER, "header1.xml"),
            (RID_RODAPE, REL_FOOTER, "footer1.xml"),
        ]
        self.paragrafos = 0
        self.figuras = 0

    # ------------------------------------------------------------------ parágrafos

    def sumario(self) -> None:
        """O campo `TOC` como primeira página do documento, com quebra depois.

        **É um campo, e não uma lista escrita à mão**: uma lista de títulos com números de página
        que ninguém recalcula mente na segunda edição. O Word (e o LibreOffice) preenche o campo com
        `F9`, e quem converte o arquivo lê os títulos direto do estilo.
        """
        self.corpo.append(f'<w:p><w:pPr><w:pStyle w:val="{TITULO}"/></w:pPr>{run("Sumário")}</w:p>')
        self.corpo.append(
            "<w:p>"
            '<w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve">{_html.escape(CAMPO_DE_SUMARIO, quote=False)}</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f"{run('Índice vazio: clique nele e tecle F9 para o Word montá-lo.')}"
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
            "</w:p>"
        )
        self.paragrafos += 2
        self.quebra_de_pagina()

    def paragrafo(self, estilo: str, runs: Sequence[str], *, alinhamento: str = "") -> None:
        """Um `<w:p>` com estilo e os `<w:r>` já escritos. Vazio não sai."""
        if not runs:
            return
        propriedades = []
        if estilo and estilo != "Normal":
            propriedades.append(f'<w:pStyle w:val="{_atributo(estilo)}"/>')
        if alinhamento in ALINHAMENTOS:
            propriedades.append(f'<w:jc w:val="{ALINHAMENTOS[alinhamento]}"/>')
        ppr = f"<w:pPr>{''.join(propriedades)}</w:pPr>" if propriedades else ""
        self.corpo.append(f"<w:p>{ppr}{''.join(runs)}</w:p>")
        self.paragrafos += 1

    def texto(self, estilo: str, texto: str, *, alinhamento: str = "") -> None:
        self.paragrafo(estilo, [run(texto)], alinhamento=alinhamento)

    def quebra_de_pagina(self) -> None:
        self.corpo.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    # ------------------------------------------------------------------ figuras

    def figura(
        self,
        nome: str,
        png: bytes,
        *,
        svg: bytes | None = None,
        alt: str = "",
        largura_cm: float = LARGURA_PADRAO_CM,
        legenda: str = "",
    ) -> None:
        """O diagrama como `wp:inline`: o PNG no `a:blip`, o SVG na extensão, quando houver."""
        self.figuras += 1
        rid_png = self._media(f"{nome}.png", png)
        extensao = ""
        if svg:
            rid_svg = self._media(f"{nome}.svg", svg)
            extensao = (
                f'<a:extLst><a:ext uri="{URI_SVG}"><asvg:svgBlip r:embed="{rid_svg}"/></a:ext></a:extLst>'
            )
        lado = int(round(largura_cm * EMU_POR_CM))
        numero = self.figuras
        desenho = (
            "<w:r><w:drawing>"
            '<wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{lado}" cy="{lado}"/>'
            f'<wp:docPr id="{numero}" name="Diagrama {numero}" descr="{_atributo(alt)}"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            "<a:graphic>"
            f'<a:graphicData uri="{NS_PIC}">'
            "<pic:pic>"
            f'<pic:nvPicPr><pic:cNvPr id="{numero}" name="{_atributo(nome)}.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid_png}">{extensao}</a:blip><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{lado}" cy="{lado}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            "</pic:pic>"
            "</a:graphicData>"
            "</a:graphic>"
            "</wp:inline>"
            "</w:drawing></w:r>"
        )
        self.paragrafo(DIAGRAMA, [desenho])
        if legenda:
            self.texto(LEGENDA, legenda)

    def _media(self, nome: str, dados: bytes) -> str:
        self.media[nome] = bytes(dados)
        rid = f"rId{len(self.relacoes) + 1}"
        self.relacoes.append((rid, REL_IMAGE, f"media/{nome}"))
        return rid

    # ------------------------------------------------------------------ o pacote

    def empacotar(self) -> bytes:
        """O `.docx` inteiro, em memória."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_:
            zip_.writestr("[Content_Types].xml", _tipos_de_conteudo(self.media))
            zip_.writestr("_rels/.rels", _rels_da_raiz())
            zip_.writestr("docProps/core.xml", _nucleo(self.metadados))
            zip_.writestr("docProps/app.xml", _aplicativo())
            zip_.writestr("word/document.xml", _documento_xml(self.corpo))
            zip_.writestr("word/styles.xml", _estilos_xml())
            zip_.writestr("word/settings.xml", _configuracao())
            zip_.writestr("word/header1.xml", _cabecalho(self.metadados))
            zip_.writestr("word/footer1.xml", _rodape())
            zip_.writestr("word/_rels/document.xml.rels", _rels(self.relacoes))
            for nome, dados in self.media.items():
                zip_.writestr(f"word/media/{nome}", dados)
        return buffer.getvalue()

    def escrever(self, caminho: Path) -> Relatorio:
        """Grava atomicamente e conta. Cancelar no meio não deixa um `.docx` pela metade."""
        dados = self.empacotar()
        atomic_write_bytes(Path(caminho), dados)
        png = sum(1 for nome in self.media if nome.endswith(".png"))
        svg = sum(1 for nome in self.media if nome.endswith(".svg"))
        return Relatorio(
            caminho=Path(caminho), tamanho=len(dados), paragrafos=self.paragrafos, diagramas=self.figuras, png=png, svg=svg
        )


def run(
    texto: str,
    *,
    negrito: bool = False,
    italico: bool = False,
    sublinhado: bool = False,
    tachado: bool = False,
    cor: str = "",
    realce: str = "",
    meios_pontos: int = 0,
    monoespaco: bool = False,
    pontilhado: bool = False,
) -> str:
    """Um `<w:r>`. `cor` e `realce` são hexadecimais **já resolvidos**; vazio não escreve nada."""
    propriedades: list[str] = []
    if monoespaco:
        propriedades.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>')
    if negrito:
        propriedades.append("<w:b/>")
    if italico:
        propriedades.append("<w:i/>")
    if tachado:
        propriedades.append("<w:strike/>")
    cor_hex = _hex(cor)
    if cor_hex:
        propriedades.append(f'<w:color w:val="{cor_hex}"/>')
    if meios_pontos > 0:
        propriedades.append(f'<w:sz w:val="{meios_pontos}"/>')
    realce_hex = _hex(realce)
    if realce_hex:
        propriedades.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{realce_hex}"/>')
    if sublinhado:
        propriedades.append('<w:u w:val="single"/>')
    elif pontilhado:
        propriedades.append('<w:u w:val="dotted"/>')
    rpr = f"<w:rPr>{''.join(propriedades)}</w:rPr>" if propriedades else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{_html.escape(texto, quote=False)}</w:t></w:r>'


# ------------------------------------------------------------------------------ o estudo


def exportar_estudo_docx(
    estudo: Estudo,
    caminho: Path,
    metadados: Metadados | None = None,
    *,
    largura_cm: float = LARGURA_PADRAO_CM,
    com_fen: bool = False,
) -> Relatorio:
    """Um estudo, um documento. O título do arquivo é o do estudo quando ninguém deu outro."""
    dados = metadados or Metadados(titulo=estudo_paragrafos.titulo_do_estudo(estudo))
    return exportar_estudos_docx([estudo], caminho, dados, largura_cm=largura_cm, com_fen=com_fen)


def exportar_estudos_docx(
    estudos: Sequence[Estudo],
    caminho: Path,
    metadados: Metadados | None = None,
    *,
    largura_cm: float = LARGURA_PADRAO_CM,
    com_fen: bool = False,
) -> Relatorio:
    """Vários estudos num documento, um título de nível 1 cada e quebra de página entre eles.

    **O índice só entra quando há mais de um estudo**: um sumário de uma linha é uma página a mais
    para dizer o que a primeira já diz.
    """
    doc = Documento(metadados)
    if len(estudos) > 1:
        doc.sumario()
    for indice, estudo in enumerate(estudos, start=1):
        if indice > 1:
            doc.quebra_de_pagina()
        _estudo(doc, estudo, indice, largura_cm, com_fen=com_fen)
    return doc.escrever(caminho)


def _estudo(doc: Documento, estudo: Estudo, indice: int, largura_cm: float, *, com_fen: bool = False) -> None:
    for paragrafo in estudo_paragrafos.paragrafos(estudo):
        tipo = paragrafo.tipo
        if tipo == estudo_paragrafos.TITULO:
            doc.texto(TITULO, paragrafo.texto)
        elif tipo == estudo_paragrafos.DIAGRAMA:
            nome = f"estudo_{indice:03d}_diagrama_{paragrafo.numero:02d}"
            alt = diagrama_svg.descricao_da_posicao(paragrafo.fen, marca=f"Diagrama {paragrafo.numero}")
            png = diagrama_png.png_da_posicao(paragrafo.fen, virado=paragrafo.virado)
            svg = _svg_de_arquivo(paragrafo.fen, virado=paragrafo.virado, largura_cm=largura_cm, titulo=alt)
            doc.figura(
                nome,
                png,
                svg=svg,
                alt=alt,
                largura_cm=largura_cm,
                legenda=f"FEN: {paragrafo.fen}" if com_fen else "",
            )
        elif tipo == estudo_paragrafos.COMENTARIO_DO_ESTUDO:
            doc.texto(COMENTARIO, paragrafo.texto)
        elif tipo == estudo_paragrafos.VARIANTE:
            doc.texto(VARIANTE_2 if paragrafo.nivel >= 2 else VARIANTE, paragrafo.texto)
        else:
            doc.texto(LANCE, paragrafo.texto)


# ------------------------------------------------------------------------------ o texto


def exportar_texto_docx(
    documento: rico.DocumentoRico,
    caminho: Path,
    metadados: Metadados | None = None,
    *,
    imagens: Mapping[int, bytes] | None = None,
    cores: Mapping[str, str] | None = None,
    corpos: Mapping[str, str] | None = None,
    largura_cm: float = LARGURA_PADRAO_CM,
) -> Relatorio:
    """Uma folha do livro. `imagens` é `bloco -> PNG` para o diagrama sem posição lida."""
    dados = metadados or Metadados(titulo=_titulo_do_texto(documento))
    return exportar_textos_docx(
        [documento], caminho, dados, imagens=imagens, cores=cores, corpos=corpos, largura_cm=largura_cm
    )


def exportar_textos_docx(
    documentos: Sequence[rico.DocumentoRico],
    caminho: Path,
    metadados: Metadados | None = None,
    *,
    imagens: Mapping[int, bytes] | None = None,
    cores: Mapping[str, str] | None = None,
    corpos: Mapping[str, str] | None = None,
    largura_cm: float = LARGURA_PADRAO_CM,
) -> Relatorio:
    """Várias folhas, na ordem em que vieram, com quebra de página entre elas.

    `cores` e `corpos` são os mapas de `exportacao.Html` (`cor-nota -> #hex`, `corpo-mais-2 -> 13pt`):
    vêm de `ui/tokens` e de `ui/tipografia`, porque este módulo não conhece um hexadecimal.
    """
    doc = Documento(metadados)
    if len(documentos) > 1:
        doc.sumario()
    formatador = _Runs(dict(cores or {}), dict(corpos or {}))
    so_marca = 0
    for indice, documento in enumerate(documentos, start=1):
        if indice > 1:
            doc.quebra_de_pagina()
        so_marca += _texto(doc, documento, indice, formatador, imagens or {}, largura_cm)
    relatorio = doc.escrever(caminho)
    avisos = (f"{so_marca} diagrama(s) sem posição lida nem imagem: só a marca",) if so_marca else ()
    return Relatorio(
        caminho=relatorio.caminho,
        tamanho=relatorio.tamanho,
        paragrafos=relatorio.paragrafos,
        diagramas=relatorio.diagramas + so_marca,
        png=relatorio.png,
        svg=relatorio.svg,
        so_marca=so_marca,
        avisos=avisos,
    )


class _Runs:
    """`Corrida -> <w:r>`, com a cor e o corpo resolvidos pelos mapas que vieram de fora."""

    def __init__(self, cores: Mapping[str, str], corpos: Mapping[str, str]) -> None:
        self.cores = cores
        self.corpos = corpos

    def run(self, corrida: rico.Corrida, texto: str) -> str:
        atributos = corrida.atributos
        meios_pontos = 0
        if atributos.corpo:
            meios_pontos = _meios_pontos(self.corpos.get(exportacao.classe_de_corpo(atributos.corpo), ""))
        return run(
            texto,
            negrito=atributos.negrito,
            italico=atributos.italico or atributos.estilo == rico.ESTILO_LEGENDA,
            sublinhado=atributos.sublinhado,
            tachado=atributos.tachado,
            cor=self.cores.get(f"cor-{atributos.cor}", "") if atributos.cor else "",
            realce=self.cores.get(f"realce-{atributos.realce}", "") if atributos.realce else "",
            meios_pontos=meios_pontos,
            monoespaco=atributos.estilo == rico.ESTILO_NOTACAO,
            pontilhado=atributos.fora_do_modelo or corrida.faixa != _documento.TRANQUILO,
        )


def _texto(
    doc: Documento,
    documento: rico.DocumentoRico,
    indice: int,
    formatador: _Runs,
    injetadas: Mapping[int, bytes],
    largura_cm: float,
) -> int:
    """Os parágrafos de uma folha: corte em cada quebra de linha, e as figuras. Devolve `so_marca`."""
    so_marca = 0
    inicio = len(doc.corpo)
    montador = _Paragrafo(doc)
    for corrida in documento.corridas:
        if corrida.e_diagrama:
            montador.fechar()
            so_marca += _diagrama_do_texto(doc, documento, corrida, indice, injetadas, largura_cm)
            continue
        for numero, pedaco in enumerate(corrida.texto.split("\n")):
            if numero:
                montador.fechar()
            if pedaco:
                montador.pedaco(corrida, formatador.run(corrida, pedaco), pedaco)
    montador.fechar()
    if not montador.teve_titulo:
        doc.corpo.insert(inicio, _paragrafo_de_titulo(_titulo_do_texto(documento)))
        doc.paragrafos += 1
    return so_marca


def _paragrafo_de_titulo(texto: str) -> str:
    return f'<w:p><w:pPr><w:pStyle w:val="{TITULO}"/></w:pPr>{run(texto)}</w:p>'


class _Paragrafo:
    """Acumula os runs e fecha o `<w:p>` quando a quebra chega.

    **O primeiro título da folha é `Heading1` e os seguintes são `Heading2`**, como no EPUB: um
    documento que começa no segundo nível não tem primeiro, e é o painel de navegação do Word e o
    campo `TOC` que leem essa hierarquia.
    """

    def __init__(self, doc: Documento) -> None:
        self.doc = doc
        self.runs: list[str] = []
        self.texto: list[str] = []
        self.titulo = False
        self.alinhamento = ""
        self.teve_titulo = False

    def pedaco(self, corrida: rico.Corrida, marcado: str, puro: str) -> None:
        if not self.runs:
            self.alinhamento = corrida.atributos.alinhamento
        self.runs.append(marcado)
        self.texto.append(puro)
        self.titulo = self.titulo or corrida.atributos.estilo == rico.ESTILO_TITULO

    def fechar(self) -> None:
        if "".join(self.texto).strip():
            estilo = "Normal"
            if self.titulo:
                estilo = SUBTITULO if self.teve_titulo else TITULO
                self.teve_titulo = True
            self.doc.paragrafo(estilo, self.runs, alinhamento=self.alinhamento)
        self.runs, self.texto, self.titulo, self.alinhamento = [], [], False, ""


def _diagrama_do_texto(
    doc: Documento,
    documento: rico.DocumentoRico,
    corrida: rico.Corrida,
    indice: int,
    injetadas: Mapping[int, bytes],
    largura_cm: float,
) -> int:
    bloco = documento.bloco_de(corrida)
    placement = str(getattr(bloco, "placement", "") or "")
    marca = corrida.texto
    nome = f"folha_{indice:03d}_bloco_{max(corrida.bloco, 0):03d}"
    if placement:
        alt = diagrama_svg.descricao_da_posicao(placement, marca=marca)
        png = diagrama_png.png_da_posicao(placement)
        svg = _svg_de_arquivo(placement, largura_cm=largura_cm, titulo=alt)
        doc.figura(nome, png, svg=svg, alt=alt, largura_cm=largura_cm)
        return 0
    png_injetado = injetadas.get(corrida.bloco)
    if png_injetado:
        doc.figura(nome, png_injetado, alt=marca, largura_cm=largura_cm)
        return 0
    doc.texto(MARCA, marca)
    return 1


def _svg_de_arquivo(fen: str, *, virado: bool = False, largura_cm: float, titulo: str = "") -> bytes:
    """O SVG **como parte do pacote**, e não como elemento de um XHTML.

    Duas diferenças, as duas do lado de fora do desenho: a declaração `<?xml?>` na frente, que é o
    que um `.svg` autônomo leva e o que o Word espera achar; e o tamanho em `cm` em vez de `em` --
    `width="18em"` num arquivo solto não tem corpo de texto a que se referir, e o Word resolve `em`
    como um palpite ou como zero. O tamanho que vale continua sendo o `wp:extent` em EMU; o do
    arquivo é o que os outros programas leem.
    """
    return diagrama_svg.svg_da_posicao(
        fen, virado=virado, largura_em=largura_cm, unidade="cm", declaracao=True, titulo=titulo
    ).encode("utf-8")


def _titulo_do_texto(documento: rico.DocumentoRico) -> str:
    pagina = documento.origem
    if pagina is None:
        return "Texto do ChessVisionOFF"
    origem = Path(pagina.documento or "texto").name
    return f"{origem} — folha {pagina.pagina + 1}"


# ------------------------------------------------------------------------------ as partes


def _tipos_de_conteudo(media: Mapping[str, bytes]) -> str:
    extensoes = {"rels", "xml"} | {_extensao(nome) for nome in media}
    padroes = "".join(
        f'<Default Extension="{ext}" ContentType="{TIPOS_DE_CONTEUDO.get(ext, "application/octet-stream")}"/>'
        for ext in sorted(extensoes)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Types xmlns="{NS_CT}">{padroes}'
        f'<Override PartName="/word/document.xml" ContentType="{TIPO_DO_DOCUMENTO}"/>'
        f'<Override PartName="/word/styles.xml" ContentType="{TIPO_DOS_ESTILOS}"/>'
        f'<Override PartName="/word/settings.xml" ContentType="{TIPO_DA_CONFIGURACAO}"/>'
        f'<Override PartName="/word/header1.xml" ContentType="{TIPO_DO_CABECALHO}"/>'
        f'<Override PartName="/word/footer1.xml" ContentType="{TIPO_DO_RODAPE}"/>'
        f'<Override PartName="/docProps/core.xml" ContentType="{TIPO_DO_NUCLEO}"/>'
        f'<Override PartName="/docProps/app.xml" ContentType="{TIPO_DO_APLICATIVO}"/>'
        "</Types>"
    )


def _configuracao() -> str:
    """`word/settings.xml`. **`updateFields` é o que faz o Word oferecer-se para montar o índice**
    ao abrir o arquivo -- sem ele o campo `TOC` fica com o texto de reserva até alguém teclar F9."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:settings xmlns:w="{NS_W}"><w:updateFields w:val="true"/>'
        '<w:defaultTabStop w:val="708"/><w:compat/></w:settings>'
    )


def _cabecalho(dados: Metadados) -> str:
    """`word/header1.xml`: o título do livro, à direita, como todo livro impresso traz."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:hdr xmlns:w="{NS_W}" xmlns:r="{NS_R}">'
        f'<w:p><w:pPr><w:jc w:val="right"/></w:pPr>{run(dados.titulo, meios_pontos=18)}</w:p>'
        "</w:hdr>"
    )


def _rodape() -> str:
    """`word/footer1.xml`: o número da página, centrado, como campo `PAGE`.

    Campo e não texto: um número escrito à mão fica errado no primeiro parágrafo que alguém
    acrescentar. Sem ele, um `.docx` de 2.618 estudos imprime 900 páginas sem numeração nenhuma.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:ftr xmlns:w="{NS_W}" xmlns:r="{NS_R}">'
        '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f"{run('1')}"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        "</w:p></w:ftr>"
    )


def _aplicativo() -> str:
    """`docProps/app.xml`: quem **fabricou** o arquivo. O autor é de quem publica, e está no núcleo."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        f"<Application>{_html.escape(PRODUTOR)}</Application></Properties>"
    )


def _rels_da_raiz() -> str:
    return _rels(
        [
            ("rId1", REL_OFFICE, "word/document.xml"),
            ("rId2", REL_CORE, "docProps/core.xml"),
            ("rId3", REL_APP, "docProps/app.xml"),
        ]
    )


def _rels(relacoes: Sequence[tuple[str, str, str]]) -> str:
    itens = "".join(
        f'<Relationship Id="{rid}" Type="{tipo}" Target="{_atributo(alvo)}"/>' for rid, tipo, alvo in relacoes
    )
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{NS_REL}">{itens}</Relationships>'


def _nucleo(dados: Metadados) -> str:
    """`docProps/core.xml`. **`dc:creator` só sai quando há autor**, e o programa vai em
    `cp:lastModifiedBy`: um arquivo cujo autor é o nome do exportador atribui a obra a quem não a
    escreveu, e é o Word que mostra esse campo em "Propriedades" e nas colunas do Explorador."""
    agora = dados.modificado or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    autoria = f"<dc:creator>{_html.escape(dados.autor)}</dc:creator>" if dados.autor else ""
    editora = f"<cp:category>{_html.escape(dados.editora)}</cp:category>" if dados.editora else ""
    direitos = f"<dc:description>{_html.escape(dados.direitos)}</dc:description>" if dados.direitos else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<cp:coreProperties xmlns:cp="{NS_CP}" xmlns:dc="{NS_DC}" xmlns:dcterms="{NS_DCTERMS}" xmlns:xsi="{NS_XSI}">'
        f"<dc:title>{_html.escape(dados.titulo)}</dc:title>"
        f"{autoria}{direitos}"
        f"<dc:language>{_html.escape(dados.idioma)}</dc:language>"
        f"<cp:lastModifiedBy>{_html.escape(PRODUTOR)}</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{_html.escape(agora)}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{_html.escape(agora)}</dcterms:modified>'
        f"{editora}"
        "</cp:coreProperties>"
    )


def _documento_xml(corpo: Sequence[str]) -> str:
    """O corpo e a seção. **As referências de cabeçalho e rodapé abrem o `sectPr`**: a ordem dos
    filhos é imposta pelo esquema, e um `headerReference` depois do `pgSz` faz o Word recusar o
    arquivo como ilegível."""
    secao = (
        "<w:sectPr>"
        f'<w:headerReference w:type="default" r:id="{RID_CABECALHO}"/>'
        f'<w:footerReference w:type="default" r:id="{RID_RODAPE}"/>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{NS_W}" xmlns:r="{NS_R}" xmlns:wp="{NS_WP}" xmlns:a="{NS_A}" xmlns:pic="{NS_PIC}" xmlns:asvg="{NS_ASVG}">'
        f"<w:body>{''.join(corpo)}{secao}</w:body></w:document>"
    )


def _estilos_xml() -> str:
    estilos = []
    for identificador, (nome, ppr, rpr) in ESTILOS.items():
        padrao = ' w:default="1"' if identificador == "Normal" else ""
        base = "" if identificador == "Normal" else '<w:basedOn w:val="Normal"/>'
        # Depois de um título vem texto, e não outro título -- e a prioridade é a que o Word usa
        # nos seus próprios cabeçalhos, para o estilo aparecer no começo da galeria.
        cabecalho = '<w:next w:val="Normal"/><w:uiPriority w:val="9"/>' if identificador in (TITULO, SUBTITULO) else ""
        estilos.append(
            f'<w:style w:type="paragraph" w:styleId="{identificador}"{padrao}>'
            f'<w:name w:val="{_atributo(nome)}"/>{base}{cabecalho}<w:qFormat/>'
            f"{f'<w:pPr>{ppr}</w:pPr>' if ppr else ''}{f'<w:rPr>{rpr}</w:rPr>' if rpr else ''}"
            "</w:style>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{NS_W}"><w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="22"/><w:lang w:val="pt-BR"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
        f"{''.join(estilos)}</w:styles>"
    )


def _atributo(texto: str) -> str:
    return _html.escape(str(texto), quote=True)


def _extensao(nome: str) -> str:
    """`"_rels/.rels" -> "rels"`: `Path.suffix` acha que `.rels` é um arquivo oculto sem extensão."""
    base = posixpath.basename(nome)
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""


def _hex(cor: str) -> str:
    casou = _HEX.match(str(cor or "").strip())
    return casou.group(1).upper() if casou else ""


def _meios_pontos(tamanho: str) -> int:
    """`"13pt" -> 26`. O que não é em pontos não vira `w:sz`: melhor o corpo do estilo que um chute."""
    casou = _PONTOS.match(str(tamanho or ""))
    return int(round(float(casou.group(1).replace(",", ".")) * 2)) if casou else 0


# ------------------------------------------------------------------------------ a conferência


def verificar(dados: bytes | Path) -> list[str]:
    """Os defeitos do pacote, em pt-BR. Vazio é "passou". Ver o cabeçalho."""
    conteudo = Path(dados).read_bytes() if isinstance(dados, Path) else dados
    problemas: list[str] = []
    try:
        zip_ = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as erro:
        return [f"não é um zip: {erro}"]
    with zip_:
        nomes = {info.filename for info in zip_.infolist()}
        for nome in sorted(nomes):
            if Path(nome).suffix.lower() in (".xml", ".rels", ".svg"):
                try:
                    ET.fromstring(zip_.read(nome))
                except ET.ParseError as erro:
                    problemas.append(f"{nome}: XML mal formado ({erro})")
        problemas.extend(_conferir_tipos(zip_, nomes))
        for nome in sorted(nomes):
            if nome.endswith(".rels"):
                problemas.extend(_conferir_rels(zip_, nomes, nome))
        problemas.extend(_conferir_documento(zip_, nomes))
    return problemas


def _conferir_tipos(zip_: zipfile.ZipFile, nomes: set[str]) -> list[str]:
    if "[Content_Types].xml" not in nomes:
        return ["falta [Content_Types].xml"]
    try:
        raiz = ET.fromstring(zip_.read("[Content_Types].xml"))
    except ET.ParseError:
        return []
    padroes = {e.get("Extension", "").lower() for e in raiz.iter(f"{{{NS_CT}}}Default")}
    sobrescritos = {e.get("PartName", "") for e in raiz.iter(f"{{{NS_CT}}}Override")}
    problemas = [
        f"{nome}: sem tipo de conteúdo declarado"
        for nome in sorted(nomes)
        if nome != "[Content_Types].xml"
        and f"/{nome}" not in sobrescritos
        and _extensao(nome) not in padroes
    ]
    problemas.extend(f"o Override aponta {parte!r}, que não está no zip" for parte in sorted(sobrescritos) if parte.lstrip("/") not in nomes)
    return problemas


def _conferir_rels(zip_: zipfile.ZipFile, nomes: set[str], rels: str) -> list[str]:
    try:
        raiz = ET.fromstring(zip_.read(rels))
    except ET.ParseError:
        return []
    dono = posixpath.dirname(posixpath.dirname(rels))
    problemas = []
    for relacao in raiz.iter(f"{{{NS_REL}}}Relationship"):
        if relacao.get("TargetMode") == "External":
            continue
        alvo = relacao.get("Target", "")
        resolvido = posixpath.normpath(posixpath.join(dono, alvo)) if dono else posixpath.normpath(alvo)
        if resolvido.lstrip("/") not in nomes:
            problemas.append(f"{rels}: a relação {relacao.get('Id')!r} aponta {alvo!r}, que não está no zip")
    return problemas


def _conferir_documento(zip_: zipfile.ZipFile, nomes: set[str]) -> list[str]:
    if "word/document.xml" not in nomes:
        return ["falta word/document.xml"]
    ids: set[str] = set()
    if "word/_rels/document.xml.rels" in nomes:
        try:
            for relacao in ET.fromstring(zip_.read("word/_rels/document.xml.rels")).iter(f"{{{NS_REL}}}Relationship"):
                ids.add(relacao.get("Id", ""))
        except ET.ParseError:
            pass
    try:
        raiz = ET.fromstring(zip_.read("word/document.xml"))
    except ET.ParseError:
        return []
    problemas = []
    for elemento in raiz.iter():
        embed = elemento.get(f"{{{NS_R}}}embed")
        if embed is not None and embed not in ids:
            problemas.append(f"word/document.xml: r:embed={embed!r} sem relação em document.xml.rels")
    if raiz.find(f"{{{NS_W}}}body") is None:
        problemas.append("word/document.xml: sem <w:body>")
    return problemas
