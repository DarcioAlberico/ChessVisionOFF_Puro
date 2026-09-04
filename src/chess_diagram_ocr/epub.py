"""O estudo e o texto em EPUB 3, com um SVG por diagrama (S-542).

**Por que um empacotador próprio, e não uma biblioteca.** Um EPUB é um zip com quatro regras: o
`mimetype` vem primeiro e **sem compressão**, `META-INF/container.xml` aponta o pacote, o
`content.opf` lista todo arquivo e a ordem de leitura, e todo documento é XML bem formado. A
`zipfile` da biblioteca padrão cumpre as quatro em sessenta linhas; uma dependência nova por isso
seria o extra `[epub]` que ninguém instala e a exportação que "não está disponível" na máquina do
editor -- que é exatamente quem este item serve.

**O que decide o conteúdo não mora aqui.** A paginação do estudo -- onde a linha corta, o que é
variante, onde o autor pediu diagrama -- é `estudo_paragrafos.py`, a mesma lista que o DOCX lê. O
desenho do diagrama é `diagrama_svg.py`. A formatação inline do texto do livro (negrito, itálico,
cor de autor, faixa de confiança) é a de `text/exportacao.Html`, corrida por corrida, e a folha de
estilo do EPUB **é a mesma lista de regras** do `.html` da Fase 39: a classe `cor-nota` quer dizer
a mesma coisa nos dois arquivos porque é o mesmo código que a escreve. O que este módulo acrescenta
é o que o `.html` não tem: parágrafos `<p>` no lugar de `<br>`, um capítulo por estudo ou por
folha, e a imagem em arquivo separado no `manifest`, que é como um leitor de EPUB a encontra.

## O diagrama no texto do livro

| o que a corrida de diagrama tem | o que sai |
|---|---|
| `BlocoDeDiagrama.placement` lido | um `.svg` em `imagens/`, e `<img alt="[Diagrama N]">` |
| placement vazio e um PNG injetado (`imagens=`) | o `.png` em `imagens/`, mesmo `<img>` |
| nem um nem outro | a marca `[Diagrama N]` num parágrafo, como no `.txt` |

**A marca nunca desaparece** (regra da S-250): ela é o `alt` da imagem, e é o parágrafo quando não
há imagem. O relatório conta os três casos, porque "não havia diagrama" e "havia e saiu só a marca"
são coisas diferentes para quem vai imprimir.

`verificar` é a conferência que o `epubcheck` faria se estivesse na máquina: mimetype primeiro e
armazenado, container que aponta um OPF existente, todo XML bem formado, toda referência do
manifesto presente no zip, todo `idref` da espinha no manifesto. O teste a roda sobre o que este
módulo escreve; quem chamar pode rodá-la sobre o que quiser.
"""

from __future__ import annotations

import datetime as _dt
import html as _html
import io
import posixpath
import uuid
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from chess_diagram_ocr import diagrama_svg, estudo_paragrafos
from chess_diagram_ocr.atomic_io import atomic_write_bytes
from chess_diagram_ocr.estudo import Estudo
from chess_diagram_ocr.text import exportacao, rico

__all__ = [
    "CSS",
    "MIMETYPE",
    "PASTA",
    "PASTA_DE_IMAGENS",
    "Capitulo",
    "Livro",
    "Metadados",
    "Relatorio",
    "capitulo_do_estudo",
    "capitulo_do_texto",
    "empacotar",
    "escrever",
    "exportar_estudo_epub",
    "exportar_estudos_epub",
    "exportar_texto_epub",
    "exportar_textos_epub",
    "folha_de_estilo",
    "verificar",
]

MIMETYPE = "application/epub+zip"
PASTA = "OEBPS"
PASTA_DE_IMAGENS = "imagens"
CSS = "estilo.css"
OPF = "content.opf"
NAV = "nav.xhtml"

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"

TIPOS_DE_MIDIA: Mapping[str, str] = {
    ".xhtml": "application/xhtml+xml",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@dataclass(frozen=True)
class Metadados:
    """O que vai em `dc:` no pacote. Vazio em `identificador` e `modificado` quer dizer "gere"."""

    titulo: str = "Estudos do ChessVisionOFF"
    autor: str = "ChessVisionOFF"
    idioma: str = "pt-BR"
    identificador: str = ""
    modificado: str = ""

    def resolvidos(self) -> Metadados:
        """Com o `urn:uuid` e a data que o EPUB 3 exige, quando ninguém os deu."""
        identificador = self.identificador or f"urn:uuid:{uuid.uuid4()}"
        modificado = self.modificado or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return replace(self, identificador=identificador, modificado=modificado)


@dataclass(frozen=True)
class Capitulo:
    """Um documento XHTML da espinha. `corpo` é o que vai dentro de `<section>`."""

    id: str
    titulo: str
    corpo: str

    @property
    def arquivo(self) -> str:
        return f"{self.id}.xhtml"


@dataclass
class Livro:
    """Tudo o que `empacotar` precisa, e nada do que ele não precisa."""

    metadados: Metadados
    capitulos: list[Capitulo] = field(default_factory=list)
    imagens: dict[str, bytes] = field(default_factory=dict)
    """`nome.svg`/`nome.png` -> bytes; vai para `OEBPS/imagens/`."""

    css: str = ""


@dataclass(frozen=True)
class Relatorio:
    """O que a exportação escreveu, contado (S-254 vale aqui também)."""

    caminho: Path
    tamanho: int
    capitulos: int
    diagramas: int
    svg: int = 0
    png: int = 0
    so_marca: int = 0
    """Diagramas que saíram só como `[Diagrama N]`: sem posição lida e sem imagem injetada."""

    avisos: tuple[str, ...] = ()

    def resumo(self) -> str:
        """Uma linha em pt-BR para a barra de estado."""
        partes = [f"{self.capitulos} capítulo(s)", f"{self.diagramas} diagrama(s)"]
        if self.svg:
            partes.append(f"{self.svg} em SVG")
        if self.png:
            partes.append(f"{self.png} em PNG")
        if self.so_marca:
            partes.append(f"{self.so_marca} só com a marca")
        return f"{self.caminho} ({self.tamanho // 1024} KB): " + ", ".join(partes)


# ------------------------------------------------------------------------------ o estudo


def exportar_estudo_epub(
    estudo: Estudo,
    caminho: Path,
    metadados: Metadados | None = None,
    *,
    largura_em: float = diagrama_svg.LARGURA_PADRAO_EM,
) -> Relatorio:
    """Um estudo, um capítulo. O título do livro é o do estudo quando ninguém deu outro."""
    dados = metadados or Metadados(titulo=estudo_paragrafos.titulo_do_estudo(estudo))
    return exportar_estudos_epub([estudo], caminho, dados, largura_em=largura_em)


def exportar_estudos_epub(
    estudos: Sequence[Estudo],
    caminho: Path,
    metadados: Metadados | None = None,
    *,
    largura_em: float = diagrama_svg.LARGURA_PADRAO_EM,
) -> Relatorio:
    """Vários estudos -- a sala inteira, ou um PGN -- como um livro de um capítulo por estudo."""
    livro = Livro(metadados=(metadados or Metadados()).resolvidos(), css=folha_de_estilo())
    diagramas = 0
    for indice, estudo in enumerate(estudos, start=1):
        capitulo, quantos = capitulo_do_estudo(estudo, indice, livro.imagens, largura_em=largura_em)
        livro.capitulos.append(capitulo)
        diagramas += quantos
    dados = empacotar(livro)
    escrever(caminho, dados)
    return Relatorio(
        caminho=Path(caminho),
        tamanho=len(dados),
        capitulos=len(livro.capitulos),
        diagramas=diagramas,
        svg=diagramas,
    )


def capitulo_do_estudo(
    estudo: Estudo,
    indice: int,
    imagens: dict[str, bytes],
    *,
    largura_em: float = diagrama_svg.LARGURA_PADRAO_EM,
) -> tuple[Capitulo, int]:
    """O capítulo daquele estudo. **Os SVGs entram em `imagens`**, com nome único por capítulo."""
    partes: list[str] = []
    diagramas = 0
    titulo = estudo_paragrafos.titulo_do_estudo(estudo)
    for paragrafo in estudo_paragrafos.paragrafos(estudo):
        tipo = paragrafo.tipo
        if tipo == estudo_paragrafos.TITULO:
            partes.append(f"<h1>{_html.escape(paragrafo.texto)}</h1>")
        elif tipo == estudo_paragrafos.DIAGRAMA:
            diagramas += 1
            nome = f"estudo_{indice:03d}_diagrama_{paragrafo.numero:02d}.svg"
            imagens[nome] = diagrama_svg.svg_da_posicao(
                paragrafo.fen, virado=paragrafo.virado, largura_em=largura_em
            ).encode("utf-8")
            partes.append(_figura(nome, f"Diagrama {paragrafo.numero}", legenda=f"FEN: {paragrafo.fen}"))
        elif tipo == estudo_paragrafos.COMENTARIO_DO_ESTUDO:
            partes.append(f'<p class="comentario">{_html.escape(paragrafo.texto)}</p>')
        elif tipo == estudo_paragrafos.VARIANTE:
            partes.append(f'<p class="variante nivel-{paragrafo.nivel}">{_html.escape(paragrafo.texto)}</p>')
        else:
            partes.append(f'<p class="lance">{_html.escape(paragrafo.texto)}</p>')
    return Capitulo(id=f"estudo_{indice:03d}", titulo=titulo, corpo="\n".join(partes)), diagramas


def _figura(nome: str, alt: str, *, legenda: str = "") -> str:
    figcaption = f"<figcaption>{_html.escape(legenda)}</figcaption>" if legenda else ""
    return (
        f'<figure class="diagrama"><img src="{PASTA_DE_IMAGENS}/{nome}" alt="{_html.escape(alt, quote=True)}"/>'
        f"{figcaption}</figure>"
    )


# ------------------------------------------------------------------------------ o texto


def exportar_texto_epub(
    documento: rico.DocumentoRico,
    caminho: Path,
    metadados: Metadados | None = None,
    *,
    imagens: Mapping[int, bytes] | None = None,
    cores: Mapping[str, str] | None = None,
    corpos: Mapping[str, str] | None = None,
    largura_em: float = diagrama_svg.LARGURA_PADRAO_EM,
) -> Relatorio:
    """Uma folha do livro, um capítulo. `imagens` é `bloco -> PNG` para o diagrama sem posição lida."""
    dados = metadados or Metadados(titulo=_titulo_do_texto(documento))
    return exportar_textos_epub(
        [documento], caminho, dados, imagens=imagens, cores=cores, corpos=corpos, largura_em=largura_em
    )


def exportar_textos_epub(
    documentos: Sequence[rico.DocumentoRico],
    caminho: Path,
    metadados: Metadados | None = None,
    *,
    imagens: Mapping[int, bytes] | None = None,
    cores: Mapping[str, str] | None = None,
    corpos: Mapping[str, str] | None = None,
    largura_em: float = diagrama_svg.LARGURA_PADRAO_EM,
) -> Relatorio:
    """Várias folhas, um capítulo cada -- na ordem em que vieram, que é a ordem do livro.

    `cores` e `corpos` são os mesmos mapas de `exportacao.Html`: vêm de fora, de `ui/tokens` e de
    `ui/tipografia`, porque este módulo não conhece um hexadecimal (regra 3 da SPEC_EDITOR).
    """
    formato = exportacao.Html(cores=dict(cores or {}), corpos=dict(corpos or {}))
    livro = Livro(metadados=(metadados or Metadados()).resolvidos(), css=folha_de_estilo(formato))
    total = _Contagem()
    for indice, documento in enumerate(documentos, start=1):
        capitulo, contagem = capitulo_do_texto(
            documento, indice, livro.imagens, formato=formato, injetadas=imagens or {}, largura_em=largura_em
        )
        livro.capitulos.append(capitulo)
        total.somar(contagem)
    dados = empacotar(livro)
    escrever(caminho, dados)
    avisos = (f"{total.so_marca} diagrama(s) sem posição lida nem imagem: só a marca",) if total.so_marca else ()
    return Relatorio(
        caminho=Path(caminho),
        tamanho=len(dados),
        capitulos=len(livro.capitulos),
        diagramas=total.diagramas,
        svg=total.svg,
        png=total.png,
        so_marca=total.so_marca,
        avisos=avisos,
    )


@dataclass
class _Contagem:
    diagramas: int = 0
    svg: int = 0
    png: int = 0
    so_marca: int = 0

    def somar(self, outra: _Contagem) -> None:
        self.diagramas += outra.diagramas
        self.svg += outra.svg
        self.png += outra.png
        self.so_marca += outra.so_marca


def capitulo_do_texto(
    documento: rico.DocumentoRico,
    indice: int,
    imagens: dict[str, bytes],
    *,
    formato: exportacao.Html | None = None,
    injetadas: Mapping[int, bytes] | None = None,
    largura_em: float = diagrama_svg.LARGURA_PADRAO_EM,
) -> tuple[Capitulo, _Contagem]:
    """O capítulo de uma folha: parágrafos `<p>` cortados em cada quebra de linha, e as figuras.

    **A formatação inline é a de `exportacao.Html.corrida`**, e não uma cópia: negrito, itálico,
    sublinhado, tachado, cor, realce, faixa e corpo saem com as mesmas classes que o `.html` já
    escreve. O que este módulo faz a mais é cortar em parágrafos -- o `.html` escreve `<br>`, e um
    leitor de EPUB reflui parágrafo, não quebra de linha.
    """
    html = formato or exportacao.Html()
    injetadas = injetadas or {}
    contagem = _Contagem()
    partes: list[str] = []
    montador = _Paragrafos(partes)

    for corrida in documento.corridas:
        if corrida.e_diagrama:
            montador.fechar()
            contagem.diagramas += 1
            partes.append(_diagrama_do_texto(documento, corrida, indice, imagens, injetadas, contagem, largura_em))
            continue
        for numero, pedaco in enumerate(corrida.texto.split("\n")):
            if numero:
                montador.fechar()
            if not pedaco:
                continue
            e_titulo = corrida.atributos.estilo == rico.ESTILO_TITULO
            atributos = replace(corrida.atributos, estilo="") if e_titulo else corrida.atributos
            montador.pedaco(html.corrida(replace(corrida, texto=pedaco, atributos=atributos)), pedaco, e_titulo)
    montador.fechar()

    titulo = _titulo_do_texto(documento)
    if not partes or not partes[0].startswith("<h"):
        partes.insert(0, f"<h1>{_html.escape(titulo)}</h1>")
    return Capitulo(id=f"folha_{indice:03d}", titulo=titulo, corpo="\n".join(partes)), contagem


class _Paragrafos:
    """Acumula os pedaços inline e fecha o `<p>` (ou o `<h2>`) quando a quebra chega."""

    def __init__(self, saida: list[str]) -> None:
        self.saida = saida
        self.inline: list[str] = []
        self.texto: list[str] = []
        self.titulo = False

    def pedaco(self, marcado: str, puro: str, titulo: bool) -> None:
        self.inline.append(marcado)
        self.texto.append(puro)
        self.titulo = self.titulo or titulo

    def fechar(self) -> None:
        if "".join(self.texto).strip():
            conteudo = "".join(self.inline)
            self.saida.append(f"<h2>{conteudo}</h2>" if self.titulo else f"<p>{conteudo}</p>")
        self.inline, self.texto, self.titulo = [], [], False


def _diagrama_do_texto(
    documento: rico.DocumentoRico,
    corrida: rico.Corrida,
    indice: int,
    imagens: dict[str, bytes],
    injetadas: Mapping[int, bytes],
    contagem: _Contagem,
    largura_em: float,
) -> str:
    bloco = documento.bloco_de(corrida)
    placement = str(getattr(bloco, "placement", "") or "")
    marca = corrida.texto
    base = f"folha_{indice:03d}_bloco_{max(corrida.bloco, 0):03d}"
    if placement:
        nome = f"{base}.svg"
        imagens[nome] = diagrama_svg.svg_da_posicao(placement, largura_em=largura_em, titulo=marca).encode("utf-8")
        contagem.svg += 1
        return _figura(nome, marca)
    png = injetadas.get(corrida.bloco)
    if png:
        nome = f"{base}.png"
        imagens[nome] = bytes(png)
        contagem.png += 1
        return _figura(nome, marca)
    contagem.so_marca += 1
    return f'<p class="marca">{_html.escape(marca)}</p>'


def _titulo_do_texto(documento: rico.DocumentoRico) -> str:
    pagina = documento.origem
    if pagina is None:
        return "Texto do ChessVisionOFF"
    origem = Path(pagina.documento or "texto").name
    return f"{origem} — folha {pagina.pagina + 1}"


# ------------------------------------------------------------------------------ a folha de estilo


def folha_de_estilo(formato: exportacao.Html | None = None, *, largura_em: float = diagrama_svg.LARGURA_PADRAO_EM) -> str:
    """O CSS do livro: as regras de `exportacao.Html` mais o que o EPUB tem e o `.html` não.

    `p.lance` em negrito e `p.variante` em itálico recuado são a tipografia de livro de xadrez, e
    são **os mesmos três estilos** que o DOCX nomeia ("Lance", "Variante", "Comentário") -- os dois
    formatos leem a mesma lista de parágrafos e a vestem do mesmo jeito.
    """
    html = formato or exportacao.Html()
    regras = [
        f"body {{ font-family: {html.fontes}; line-height: 1.4; }}",
        "h1 { font-size: 1.4em; margin: 1em 0 0.5em; }",
        "h2 { font-size: 1.2em; margin: 1em 0 0.5em; }",
        "p { margin: 0 0 0.6em; }",
        "p.lance { font-weight: bold; }",
        "p.variante { font-style: italic; margin-left: 1.5em; }",
        "p.variante.nivel-2 { margin-left: 3em; }",
        "p.comentario { }",
        "p.marca { text-align: center; color: inherit; }",
        "figure.diagrama { margin: 1em auto; text-align: center; page-break-inside: avoid; }",
        f"figure.diagrama img {{ width: {largura_em:g}em; max-width: 100%; height: auto; }}",
        "figure.diagrama figcaption { font-size: 0.75em; font-family: monospace; }",
    ]
    regras.extend(f".{nome} {{ {propriedade}: {valor}; }}" for nome, propriedade, valor in html.regras_de_css())
    return "\n".join(regras) + "\n"


# ------------------------------------------------------------------------------ o pacote


def empacotar(livro: Livro) -> bytes:
    """O EPUB inteiro, em memória. **O `mimetype` é o primeiro membro e vai armazenado**: é a regra
    que permite a um leitor reconhecer o arquivo lendo os primeiros bytes, sem descomprimir nada."""
    dados = livro.metadados.resolvidos()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_:
        zip_.writestr(zipfile.ZipInfo("mimetype"), MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zip_.writestr("META-INF/container.xml", _container(), compress_type=zipfile.ZIP_DEFLATED)
        zip_.writestr(f"{PASTA}/{OPF}", _opf(livro, dados), compress_type=zipfile.ZIP_DEFLATED)
        zip_.writestr(f"{PASTA}/{NAV}", _nav(livro, dados), compress_type=zipfile.ZIP_DEFLATED)
        zip_.writestr(f"{PASTA}/{CSS}", livro.css or folha_de_estilo(), compress_type=zipfile.ZIP_DEFLATED)
        for capitulo in livro.capitulos:
            zip_.writestr(f"{PASTA}/{capitulo.arquivo}", _xhtml(capitulo, dados), compress_type=zipfile.ZIP_DEFLATED)
        for nome, conteudo in livro.imagens.items():
            zip_.writestr(f"{PASTA}/{PASTA_DE_IMAGENS}/{nome}", conteudo, compress_type=zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def escrever(caminho: Path, dados: bytes) -> Path:
    """Grava atomicamente: cancelar no meio não deixa um EPUB pela metade no disco."""
    atomic_write_bytes(Path(caminho), dados)
    return Path(caminho)


def _container() -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<container version="1.0" xmlns="{CONTAINER_NS}">\n'
        "  <rootfiles>\n"
        f'    <rootfile full-path="{PASTA}/{OPF}" media-type="application/oebps-package+xml"/>\n'
        "  </rootfiles>\n"
        "</container>\n"
    )


def _opf(livro: Livro, dados: Metadados) -> str:
    itens = [
        f'    <item id="nav" href="{NAV}" media-type="application/xhtml+xml" properties="nav"/>',
        f'    <item id="css" href="{CSS}" media-type="text/css"/>',
    ]
    itens.extend(
        f'    <item id="{capitulo.id}" href="{capitulo.arquivo}" media-type="application/xhtml+xml"/>'
        for capitulo in livro.capitulos
    )
    for numero, nome in enumerate(livro.imagens, start=1):
        tipo = TIPOS_DE_MIDIA.get(Path(nome).suffix.lower(), "application/octet-stream")
        itens.append(f'    <item id="img{numero:04d}" href="{PASTA_DE_IMAGENS}/{_atributo(nome)}" media-type="{tipo}"/>')
    espinha = "\n".join(f'    <itemref idref="{capitulo.id}"/>' for capitulo in livro.capitulos)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<package xmlns="{OPF_NS}" version="3.0" unique-identifier="pub-id" xml:lang="{_atributo(dados.idioma)}">\n'
        f'  <metadata xmlns:dc="{DC_NS}">\n'
        f'    <dc:identifier id="pub-id">{_html.escape(dados.identificador)}</dc:identifier>\n'
        f"    <dc:title>{_html.escape(dados.titulo)}</dc:title>\n"
        f"    <dc:creator>{_html.escape(dados.autor)}</dc:creator>\n"
        f"    <dc:language>{_html.escape(dados.idioma)}</dc:language>\n"
        f'    <meta property="dcterms:modified">{_html.escape(dados.modificado)}</meta>\n'
        "  </metadata>\n"
        "  <manifest>\n" + "\n".join(itens) + "\n  </manifest>\n"
        "  <spine>\n" + espinha + "\n  </spine>\n"
        "</package>\n"
    )


def _nav(livro: Livro, dados: Metadados) -> str:
    entradas = "\n".join(
        f'      <li><a href="{capitulo.arquivo}">{_html.escape(capitulo.titulo)}</a></li>' for capitulo in livro.capitulos
    )
    corpo = (
        f'<nav epub:type="toc" id="toc">\n    <h1>{_html.escape(dados.titulo)}</h1>\n    <ol>\n{entradas}\n    </ol>\n  </nav>'
    )
    return _documento_xhtml(dados.titulo, corpo, dados.idioma)


def _xhtml(capitulo: Capitulo, dados: Metadados) -> str:
    corpo = f'<section epub:type="chapter" id="{capitulo.id}">\n{capitulo.corpo}\n  </section>'
    return _documento_xhtml(capitulo.titulo, corpo, dados.idioma)


def _documento_xhtml(titulo: str, corpo: str, idioma: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        f'<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_NS}" xml:lang="{_atributo(idioma)}" lang="{_atributo(idioma)}">\n'
        "<head>\n"
        '  <meta charset="utf-8"/>\n'
        f"  <title>{_html.escape(titulo)}</title>\n"
        f'  <link rel="stylesheet" type="text/css" href="{CSS}"/>\n'
        "</head>\n"
        "<body>\n"
        f"  {corpo}\n"
        "</body>\n"
        "</html>\n"
    )


def _atributo(texto: str) -> str:
    return _html.escape(str(texto), quote=True)


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
        membros = zip_.infolist()
        nomes = {info.filename for info in membros}
        if not membros or membros[0].filename != "mimetype":
            problemas.append("o primeiro membro do zip não é `mimetype`")
        else:
            if membros[0].compress_type != zipfile.ZIP_STORED:
                problemas.append("`mimetype` está comprimido")
            if zip_.read("mimetype") != MIMETYPE.encode("ascii"):
                problemas.append("`mimetype` não diz application/epub+zip")
        for info in membros:
            if Path(info.filename).suffix.lower() in (".xhtml", ".opf", ".xml", ".svg", ".ncx"):
                try:
                    ET.fromstring(zip_.read(info.filename))
                except ET.ParseError as erro:
                    problemas.append(f"{info.filename}: XML mal formado ({erro})")
        opf = _caminho_do_opf(zip_, nomes, problemas)
        if opf:
            problemas.extend(_conferir_opf(zip_, nomes, opf))
    return problemas


def _caminho_do_opf(zip_: zipfile.ZipFile, nomes: set[str], problemas: list[str]) -> str:
    if "META-INF/container.xml" not in nomes:
        problemas.append("falta META-INF/container.xml")
        return ""
    try:
        raiz = ET.fromstring(zip_.read("META-INF/container.xml"))
    except ET.ParseError:
        return ""
    rootfile = raiz.find(f".//{{{CONTAINER_NS}}}rootfile")
    caminho = rootfile.get("full-path", "") if rootfile is not None else ""
    if not caminho or caminho not in nomes:
        problemas.append(f"o container aponta um OPF que não está no zip: {caminho!r}")
        return ""
    return caminho


def _conferir_opf(zip_: zipfile.ZipFile, nomes: set[str], opf: str) -> list[str]:
    problemas: list[str] = []
    try:
        raiz = ET.fromstring(zip_.read(opf))
    except ET.ParseError:
        return problemas
    pasta = posixpath.dirname(opf)
    ids: set[str] = set()
    com_nav = False
    for item in raiz.iter(f"{{{OPF_NS}}}item"):
        ids.add(item.get("id", ""))
        com_nav = com_nav or "nav" in item.get("properties", "").split()
        alvo = posixpath.normpath(posixpath.join(pasta, item.get("href", ""))) if pasta else item.get("href", "")
        if alvo not in nomes:
            problemas.append(f"o manifesto aponta {alvo!r}, que não está no zip")
    if not com_nav:
        problemas.append("nenhum item do manifesto tem properties=\"nav\"")
    for ref in raiz.iter(f"{{{OPF_NS}}}itemref"):
        if ref.get("idref", "") not in ids:
            problemas.append(f"a espinha aponta idref={ref.get('idref')!r}, que não está no manifesto")
    for obrigatorio in ("identifier", "title", "language"):
        if raiz.find(f".//{{{DC_NS}}}{obrigatorio}") is None:
            problemas.append(f"falta dc:{obrigatorio} nos metadados")
    if raiz.find(f".//{{{OPF_NS}}}meta[@property='dcterms:modified']") is None:
        problemas.append("falta dcterms:modified nos metadados")
    return problemas
