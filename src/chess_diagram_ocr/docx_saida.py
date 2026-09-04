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
comentário, lance e variante. Os estilos nomeados no Word são esses -- `Título`, `Lance` (negrito),
`Variante` (itálico, recuado), `Comentário`, `Legenda` -- e quem abrir o arquivo pode retocá-los na
galeria de estilos em vez de caçar parágrafo por parágrafo. Para o texto do livro, a formatação
inline (negrito, itálico, sublinhado, tachado, cor, realce, corpo) vem de `Atributos`, e a cor e o
corpo chegam **resolvidos de fora** (`cores=`, `corpos=`), pelos mesmos mapas de `exportacao.Html`:
nenhum hexadecimal é escrito aqui (regra 3 da SPEC_EDITOR).

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
from chess_diagram_ocr.epub import Metadados
from chess_diagram_ocr.estudo import Estudo
from chess_diagram_ocr.text import documento as _documento
from chess_diagram_ocr.text import exportacao, rico

__all__ = [
    "ESTILOS",
    "LARGURA_PADRAO_CM",
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
REL_STYLES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
URI_SVG = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"

TIPOS_DE_CONTEUDO: Mapping[str, str] = {
    "rels": "application/vnd.openxmlformats-package.relationships+xml",
    "xml": "application/xml",
    "png": "image/png",
    "svg": "image/svg+xml",
}
TIPO_DO_DOCUMENTO = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
TIPO_DOS_ESTILOS = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
TIPO_DO_NUCLEO = "application/vnd.openxmlformats-package.core-properties+xml"

TITULO = "Titulo"
LANCE = "Lance"
VARIANTE = "Variante"
VARIANTE_2 = "Variante2"
COMENTARIO = "Comentario"
LEGENDA = "Legenda"
DIAGRAMA = "Diagrama"
MARCA = "Marca"

ESTILOS: Mapping[str, tuple[str, str, str]] = {
    "Normal": ("Normal", "", '<w:sz w:val="22"/>'),
    TITULO: (
        "Título",
        '<w:keepNext/><w:spacing w:before="360" w:after="160"/><w:outlineLvl w:val="0"/>',
        '<w:b/><w:sz w:val="32"/>',
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
        self.relacoes: list[tuple[str, str, str]] = [("rId1", REL_STYLES, "styles.xml")]
        self.paragrafos = 0
        self.figuras = 0

    # ------------------------------------------------------------------ parágrafos

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
            zip_.writestr("word/document.xml", _documento_xml(self.corpo))
            zip_.writestr("word/styles.xml", _estilos_xml())
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
) -> Relatorio:
    """Um estudo, um documento. O título do arquivo é o do estudo quando ninguém deu outro."""
    dados = metadados or Metadados(titulo=estudo_paragrafos.titulo_do_estudo(estudo))
    return exportar_estudos_docx([estudo], caminho, dados, largura_cm=largura_cm)


def exportar_estudos_docx(
    estudos: Sequence[Estudo],
    caminho: Path,
    metadados: Metadados | None = None,
    *,
    largura_cm: float = LARGURA_PADRAO_CM,
) -> Relatorio:
    """Vários estudos num documento, um título de nível 1 cada e quebra de página entre eles."""
    doc = Documento(metadados)
    for indice, estudo in enumerate(estudos, start=1):
        if indice > 1:
            doc.quebra_de_pagina()
        _estudo(doc, estudo, indice, largura_cm)
    return doc.escrever(caminho)


def _estudo(doc: Documento, estudo: Estudo, indice: int, largura_cm: float) -> None:
    for paragrafo in estudo_paragrafos.paragrafos(estudo):
        tipo = paragrafo.tipo
        if tipo == estudo_paragrafos.TITULO:
            doc.texto(TITULO, paragrafo.texto)
        elif tipo == estudo_paragrafos.DIAGRAMA:
            nome = f"estudo_{indice:03d}_diagrama_{paragrafo.numero:02d}"
            png = diagrama_png.png_da_posicao(paragrafo.fen, virado=paragrafo.virado)
            svg = diagrama_svg.svg_da_posicao(paragrafo.fen, virado=paragrafo.virado).encode("utf-8")
            doc.figura(
                nome, png, svg=svg, alt=f"Diagrama {paragrafo.numero}", largura_cm=largura_cm, legenda=f"FEN: {paragrafo.fen}"
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
    """Acumula os runs e fecha o `<w:p>` quando a quebra chega. Título vira `Título`."""

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
            self.doc.paragrafo(TITULO if self.titulo else "Normal", self.runs, alinhamento=self.alinhamento)
            self.teve_titulo = self.teve_titulo or self.titulo
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
        png = diagrama_png.png_da_posicao(placement)
        svg = diagrama_svg.svg_da_posicao(placement, titulo=marca).encode("utf-8")
        doc.figura(nome, png, svg=svg, alt=marca, largura_cm=largura_cm)
        return 0
    png_injetado = injetadas.get(corrida.bloco)
    if png_injetado:
        doc.figura(nome, png_injetado, alt=marca, largura_cm=largura_cm)
        return 0
    doc.texto(MARCA, marca)
    return 1


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
        f'<Override PartName="/docProps/core.xml" ContentType="{TIPO_DO_NUCLEO}"/>'
        "</Types>"
    )


def _rels_da_raiz() -> str:
    return _rels([("rId1", REL_OFFICE, "word/document.xml"), ("rId2", REL_CORE, "docProps/core.xml")])


def _rels(relacoes: Sequence[tuple[str, str, str]]) -> str:
    itens = "".join(
        f'<Relationship Id="{rid}" Type="{tipo}" Target="{_atributo(alvo)}"/>' for rid, tipo, alvo in relacoes
    )
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{NS_REL}">{itens}</Relationships>'


def _nucleo(dados: Metadados) -> str:
    agora = dados.modificado or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<cp:coreProperties xmlns:cp="{NS_CP}" xmlns:dc="{NS_DC}" xmlns:dcterms="{NS_DCTERMS}" xmlns:xsi="{NS_XSI}">'
        f"<dc:title>{_html.escape(dados.titulo)}</dc:title>"
        f"<dc:creator>{_html.escape(dados.autor)}</dc:creator>"
        f"<dc:language>{_html.escape(dados.idioma)}</dc:language>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{_html.escape(agora)}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{_html.escape(agora)}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def _documento_xml(corpo: Sequence[str]) -> str:
    secao = (
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
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
        estilos.append(
            f'<w:style w:type="paragraph" w:styleId="{identificador}"{padrao}>'
            f'<w:name w:val="{_atributo(nome)}"/>{base}<w:qFormat/>'
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
