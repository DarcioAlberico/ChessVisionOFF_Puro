"""Livros em DjVu: viram PDF uma vez, e o resto do programa nem fica sabendo.

**Por que converter, em vez de ler o DjVu direto.** Render, detecção, camada de texto, `OpenPdf`
e a exportação falam `fitz.Document`, e o MuPDF não abre DjVu. Uma segunda implementação de cada
um desses seria um segundo programa. Então `pdf_io._open_document` pede aqui o caminho de um PDF
guardado em `DJVU_CONVERTIDOS_DIR`, e **quem chamou continua com o caminho do `.djvu` na mão**: é
ele que entra na sessão, nos rótulos, na Galeria e no nome do PGN.

A pasta é descartável: apagada, o livro é convertido de novo na próxima abertura.

**O que `Document.to_pdf` entrega, e os quatro acertos que ele pede.** Medido em 253 livros reais:

1. **A camada de texto dele perde o cirílico.** Ele escreve em Helvetica/WinAnsi, e cada letra
   fora do Latin-1 vira `?`. Um programa que lê a camada confiaria nesse lixo, então o texto dele
   sai da página e `_escrever_camada` escreve o de `Page.text_layer()`. Ela usa um só alfabeto por
   página, porque a fonte embutida do PDF é de 8 bits. O índice do livro sofre do mesmo defeito, e
   sai do PDF: nada neste programa o lê.

2. **O DPI do cabeçalho nem sempre é verdade.** 1.413 x 2.259 px declarados a 72 DPI dão uma
   página de 31 polegadas; 1.310 x 2.158 px a 600 DPI dão 3,6. Como o programa rasteriza por DPI,
   a primeira viraria uma folha de quase 7.000 px, e a segunda encolheria para 791 px e perderia as casas
   do diagrama. Ver `fator_de_escala`.

3. **`INCL` fora de UTF-8 deixa a página sem dicionário.** Seis dos livros têm o nome do
   dicionário JB2 em cp1251. A biblioteca ignora esse `INCL`, e a página falha com "stream requires
   shared dict". `paginas_soltas` remonta cada página com o dicionário dentro dela, achado pelo nome
   (`djvu_bzz`).

4. **Uma página ruim derruba o livro inteiro, ou some em silêncio.** Depende do erro. Em três
   livros a página recusada faz o `to_pdf` falhar no livro todo, e num deles é a página 2 de 423.
   Em outro ele não reclama e devolve a página sem imagem nenhuma, igual a uma folha em branco de
   verdade. Nos dois casos a página sai com `AVISO_DE_PAGINA_ILEGIVEL` escrito nela: quem abre vê o
   que faltou, e as outras continuam disponíveis.

**Os padrões da exportação também são escolha.** Sem `dpi=0` ela sairia a 150 DPI, abaixo dos 220
em que a detecção foi calibrada. `adaptive` e `ccitt_g4` são o que mantém o disco razoável: um livro
de 178 páginas em tons de cinza ficou em 92 MB, contra 389 MB em JPEG puro.
"""

from __future__ import annotations

import hashlib
import logging
import re
import struct
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from chess_diagram_ocr.atomic_io import atomic_write_bytes
from chess_diagram_ocr.config import DJVU_CONVERTIDOS_DIR
from chess_diagram_ocr.djvu_bzz import decodificar

logger = logging.getLogger(__name__)

__all__ = [
    "EXTENSOES_DE_LIVRO",
    "FILTRO_DE_LIVROS",
    "e_djvu",
    "fator_de_escala",
    "ja_convertido",
    "livros_em",
    "paginas_soltas",
    "pdf_legivel",
]

EXTENSOES_DJVU = (".djvu", ".djv")
EXTENSOES_DE_LIVRO = (".pdf", *EXTENSOES_DJVU)

FILTRO_DE_LIVROS = "Livros (*.pdf *.djvu *.djv);;PDF (*.pdf);;DjVu (*.djvu *.djv);;Todos (*.*)"
"""O filtro dos diálogos que abrem livro. O primeiro é o padrão: quem abre não precisa escolher."""

VERSAO_DA_CONVERSAO = 1
"""Entra na chave do arquivo guardado: mudar a conversão aqui invalida o que já foi convertido."""

_EXPORTACAO: dict[str, Any] = {"dpi": 0, "adaptive": True, "ccitt_g4": True, "jpeg_quality": 90}

ALTURA_MINIMA_POL = 6.0
ALTURA_MAXIMA_POL = 13.0
"""A faixa em que o DPI do cabeçalho é aceito. Do 5º ao 95º percentil do acervo: de 6,3 a 11,8."""

ALTURA_PRESUMIDA_POL = 9.0
"""A altura de quem caiu fora da faixa: o miolo do acervo vai de 7,7 a 9,1 polegadas."""

AVISO_DE_PAGINA_ILEGIVEL = "Esta página do DjVu não pôde ser lida."

_FORMAS_DE_PAGINA = (b"DJVU", b"BM44", b"PM44")
_BLOCO_DE_TEXTO = re.compile(rb"(?s)\bBT\b.*?\bET\b\s*")

_LATIM = (0, "cp1252")
_CIRILICO = (2, "koi8_u")
"""`(encoding do PyMuPDF, código de 8 bits)`. O 2 é `fitz.TEXT_ENCODING_CYRILLIC`, em número para
este módulo não importar o `fitz` só para listar uma constante. **É KOI8-U, e não cp1251**: com o
código errado o `В` vira `б` na leitura, sem erro nenhum."""

_conversao = threading.Lock()
"""Uma conversão por vez. Sem ela, a abertura e uma varredura do mesmo livro fariam o trabalho
duas vezes, cada uma pagando até minutos de CPU."""


def e_djvu(caminho: str | Path) -> bool:
    return Path(str(caminho)).suffix.lower() in EXTENSOES_DJVU


def livros_em(pasta: str | Path, *, recursivo: bool = False) -> list[Path]:
    """Os PDFs e DjVus da pasta, em ordem de nome. Pela extensão em minúscula: há `.Djvu` no acervo."""
    base = Path(pasta)
    candidatos = base.rglob("*") if recursivo else base.glob("*")
    return sorted(p for p in candidatos if p.suffix.lower() in EXTENSOES_DE_LIVRO and p.is_file())


def _guardado(origem: Path, pasta: Path) -> Path:
    """Onde mora o PDF deste DjVu. Trocar o arquivo muda o tamanho ou a data, e com eles o nome."""
    dados = origem.stat()
    chave = f"{origem.resolve()}|{dados.st_size}|{dados.st_mtime_ns}|{VERSAO_DA_CONVERSAO}"
    resumo = hashlib.sha256(chave.encode("utf-8", "surrogatepass")).hexdigest()[:16]
    legivel = "".join(c if c.isascii() and c.isalnum() else "_" for c in origem.stem)[:40]
    return pasta / f"{legivel}-{resumo}.pdf"


def ja_convertido(origem: str | Path, *, pasta: Path | None = None) -> bool:
    """Se abrir este livro é imediato. Arquivo que não existe responde que sim: a falha é da abertura."""
    caminho = Path(origem)
    if not caminho.is_file():
        return True
    return _guardado(caminho, pasta or DJVU_CONVERTIDOS_DIR).is_file()


def pdf_legivel(fonte: str | Path, *, pasta: Path | None = None) -> str:
    """O caminho que o `fitz` consegue abrir. Quem não é DjVu volta como veio, sem tocar no disco.

    `ValueError` para DjVu que não dá para ler, pela mesma razão da senha em `pdf_io`: é o que o
    `cli_errors` traduz em frase, e o que o painel já apanha.
    """
    if not e_djvu(fonte):
        return str(fonte)
    origem = Path(fonte)
    destino = _guardado(origem, pasta or DJVU_CONVERTIDOS_DIR)
    if destino.is_file():
        return str(destino)
    with _conversao:
        if not destino.is_file():  # outra thread pode ter convertido enquanto esta esperava
            _converter(origem, destino)
    return str(destino)


def _converter(origem: Path, destino: Path) -> None:
    livro = _exportar(origem)
    try:
        payload = livro.tobytes(garbage=1, deflate=True)
    finally:
        livro.close()
    try:
        atomic_write_bytes(destino, payload)
    except PermissionError:
        # O Windows recusa substituir arquivo aberto: outro processo acabou de convertê-lo e já o
        # está lendo. O conteúdo é o mesmo, e este é só um trabalho repetido.
        if not destino.is_file():
            raise


def _exportar(origem: Path) -> Any:
    """O `fitz.Document` pronto: páginas na escala certa, e só a camada de texto escrita aqui."""
    try:
        import djvu_rs
    except ImportError as exc:  # pragma: no cover - dependência declarada no pyproject
        raise ValueError(
            f"Não dá para abrir {origem.name}: falta a biblioteca djvu-rs neste ambiente (rode `uv sync`)."
        ) from exc
    import fitz

    dados = origem.read_bytes()
    ilegiveis: list[int] = []
    try:
        inteiro = djvu_rs.Document.from_bytes(dados)
        if _tem_incl_ilegivel(dados):
            livro, fontes, ilegiveis = _exportar_por_pagina(dados)
        else:
            try:
                livro = fitz.open("pdf", inteiro.to_pdf(**_EXPORTACAO))
                livro.set_toc([])
                fontes = [inteiro.page(indice) for indice in range(inteiro.page_count())]
            except djvu_rs.ExportError as exc:
                logger.info("%s: a exportação inteira falhou (%s); indo página por página.", origem.name, exc)
                livro, fontes, ilegiveis = _exportar_por_pagina(dados)
    except djvu_rs.Error as exc:
        raise ValueError(
            f"Não dá para ler {origem.name}: o arquivo parece incompleto ou danificado ({exc})."
        ) from exc

    ilegiveis = [
        indice
        for indice, (pagina, fonte) in enumerate(zip(livro, fontes, strict=True))
        if indice in ilegiveis or (not pagina.get_images() and _nao_renderiza(fonte))
    ]
    if len(ilegiveis) == len(fontes):
        livro.close()
        raise ValueError(f"Não dá para ler {origem.name}: nenhuma das páginas pôde ser decodificada.")
    for pagina, fonte in zip(livro, fontes, strict=True):
        _acertar_pagina(livro, pagina, fonte)
    for indice in ilegiveis:
        pagina = livro[indice]
        pagina.insert_text((pagina.rect.width * 0.1, pagina.rect.height / 2), AVISO_DE_PAGINA_ILEGIVEL, fontsize=12)
    if ilegiveis:
        logger.warning("%s: páginas em branco, ilegíveis no DjVu: %s", origem.name, [i + 1 for i in ilegiveis])
    return livro


def _nao_renderiza(fonte: Any) -> bool:
    """Separa a página que a exportação perdeu da folha em branco de verdade: as duas vêm sem imagem."""
    import djvu_rs

    try:
        fonte.render(dpi=25)
    except djvu_rs.Error:
        return True
    return False


def _exportar_por_pagina(dados: bytes) -> tuple[Any, list[Any], list[int]]:
    """O livro uma página de cada vez: `(documento, fontes, índices das que saíram em branco)`."""
    import djvu_rs
    import fitz

    livro = fitz.open()
    fontes = []
    ilegiveis = []
    for indice, pagina in enumerate(paginas_soltas(dados)):
        solta = djvu_rs.Document.from_bytes(pagina)
        fonte = solta.page(0)
        fontes.append(fonte)
        try:
            parte = fitz.open("pdf", solta.to_pdf(**_EXPORTACAO))
        except djvu_rs.Error as exc:
            logger.info("Página %d não decodifica: %s", indice + 1, exc)
            livro.new_page(width=fonte.width * 72 / fonte.dpi, height=fonte.height * 72 / fonte.dpi)
            ilegiveis.append(indice)
            continue
        livro.insert_pdf(parte)
        parte.close()
    return livro, fontes, ilegiveis


def fator_de_escala(altura_pt: float) -> float:
    """Por quanto multiplicar a página para ela ter o tamanho de uma página de livro.

    1.0 enquanto o DPI do cabeçalho der uma altura plausível. Fora disso ele não informa nada, e a
    página passa a ter a altura presumida. Os pixels são os mesmos: só muda o tamanho declarado.
    """
    polegadas = altura_pt / 72.0
    if ALTURA_MINIMA_POL <= polegadas <= ALTURA_MAXIMA_POL:
        return 1.0
    return ALTURA_PRESUMIDA_POL / polegadas


def _acertar_pagina(livro: Any, pagina: Any, fonte: Any) -> None:
    """Tira o texto da exportação, corrige a escala e escreve a camada de texto certa."""
    import fitz

    xrefs = pagina.get_contents()
    conteudo = pagina.read_contents()
    novo = _BLOCO_DE_TEXTO.sub(b"", conteudo)
    fator = fator_de_escala(pagina.rect.height)
    if fator != 1.0:
        largura, altura = pagina.rect.width * fator, pagina.rect.height * fator
        novo = f"q {fator:.6f} 0 0 {fator:.6f} 0 0 cm\n".encode("ascii") + novo + b"\nQ\n"
        pagina.set_mediabox(fitz.Rect(0, 0, largura, altura))
    if novo != conteudo and xrefs:  # a página em branco de `_exportar_por_pagina` não tem fluxo
        livro.update_stream(xrefs[0], novo)
        if len(xrefs) > 1:  # pragma: no cover - a exportação grava um fluxo só por página
            pagina.set_contents(xrefs[0])
    _escrever_camada(pagina, fonte)


def _palavras(zona: Any, linha: Any = None) -> Iterator[tuple[Any, Any, str]]:
    """`(retângulo da palavra, retângulo da linha, texto)`, nas folhas da árvore de zonas."""
    if zona["kind"] == "Line":
        linha = zona["rect"]
    if zona["kind"] != "Word" and zona["children"]:
        for filha in zona["children"]:
            yield from _palavras(filha, linha)
    elif zona["text"].strip():
        yield zona["rect"], linha or zona["rect"], zona["text"].strip()


def _escrever_camada(pagina: Any, fonte: Any) -> None:
    """A camada de `Page.text_layer()`, invisível, palavra por palavra.

    **O corpo e a linha de base vêm da linha, e não da palavra.** A caixa de uma palavra sem
    maiúscula começa mais embaixo que a da vizinha que tem; com a caixa de cada uma, palavras da mesma
    linha sairiam em bases diferentes, e o `get_text` as separaria em linhas.
    """
    import djvu_rs
    import fitz

    try:
        camada = fonte.text_layer()
    except djvu_rs.Error as exc:
        logger.info("Camada de texto ilegível, a página fica sem ela: %s", exc)
        return
    if not camada or not camada["text"].strip():
        return
    tem_cirilico = any("Ѐ" <= letra <= "ӿ" for letra in camada["text"])
    encoding, codigo = _CIRILICO if tem_cirilico else _LATIM
    escala = pagina.rect.width / fonte.width
    desenho = pagina.new_shape()
    escritas = 0
    for zona in camada["zones"]:
        for palavra, linha, texto in _palavras(zona):
            # O PyMuPDF escreve em fonte simples o `ord` de cada letra como o byte do PDF, e troca
            # por um ponto o que passa de 255. Por isso o texto vai como "letras" do byte certo.
            bytes_da_palavra = texto.encode(codigo, "ignore").decode("latin-1")
            if not bytes_da_palavra:
                continue
            corpo = max(linha["height"] * escala * 0.8, 1.0)
            base = (linha["y"] + linha["height"]) * escala - corpo * 0.2
            desenho.insert_text(
                fitz.Point(palavra["x"] * escala, base),
                bytes_da_palavra,
                fontsize=corpo,
                fontname="helv",
                encoding=encoding,
                render_mode=3,
            )
            escritas += 1
    if escritas:
        desenho.commit()


# ---------------------------------------------------------------- o INCL que a biblioteca ignora


def _pedacos(dados: bytes, inicio: int, fim: int) -> Iterator[tuple[int, bytes, int]]:
    """`(posição, id, tamanho)` de cada pedaço IFF. Pedaço que passa do fim encerra a varredura."""
    posicao = inicio
    fim = min(fim, len(dados))  # o tamanho vem do próprio arquivo, e num arquivo cortado ele mente
    while posicao + 8 <= fim:
        tamanho = struct.unpack(">I", dados[posicao + 4 : posicao + 8])[0]
        if posicao + 8 + tamanho > fim:
            return
        yield posicao, dados[posicao : posicao + 4], tamanho
        posicao += 8 + tamanho + (tamanho & 1)


def _componentes(dados: bytes) -> Iterator[tuple[bytes, list[tuple[bytes, bytes]]]]:
    """`(forma, [(id, conteúdo)])` de cada componente de um DjVu de várias páginas, na ordem do DIRM."""
    posicoes: list[int] = []
    for posicao, identificador, _tamanho in _pedacos(dados, 16, len(dados)):
        if identificador == b"DIRM":
            quantos = struct.unpack(">H", dados[posicao + 9 : posicao + 11])[0]
            posicoes = list(struct.unpack(f">{quantos}I", dados[posicao + 11 : posicao + 11 + 4 * quantos]))
            break
    for posicao in posicoes:
        if posicao + 12 > len(dados):  # arquivo cortado: o DIRM promete o que não chegou
            continue
        tamanho = struct.unpack(">I", dados[posicao + 4 : posicao + 8])[0]
        pedacos = [
            (identificador, dados[inicio + 8 : inicio + 8 + bytes_])
            for inicio, identificador, bytes_ in _pedacos(dados, posicao + 12, posicao + 8 + tamanho)
        ]
        yield dados[posicao + 8 : posicao + 12], pedacos


def _nome_ilegivel(nome: bytes) -> bool:
    try:
        nome.split(b"\0")[0].decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _tem_incl_ilegivel(dados: bytes) -> bool:
    if dados[12:16] != b"DJVM":
        return False
    return any(
        identificador == b"INCL" and _nome_ilegivel(conteudo)
        for _forma, pedacos in _componentes(dados)
        for identificador, conteudo in pedacos
    )


def _pedaco(identificador: bytes, conteudo: bytes) -> bytes:
    enchimento = b"\0" if len(conteudo) & 1 else b""
    return identificador + struct.pack(">I", len(conteudo)) + conteudo + enchimento


def _nomes_do_dirm(dados: bytes) -> list[bytes]:
    """O nome de cada componente, na ordem do `DIRM`. Em bytes: é em cp1251 que eles dão problema."""
    for posicao, identificador, tamanho in _pedacos(dados, 16, len(dados)):
        if identificador != b"DIRM":
            continue
        quantos = struct.unpack(">H", dados[posicao + 9 : posicao + 11])[0]
        metadados = decodificar(dados[posicao + 11 + 4 * quantos : posicao + 8 + tamanho])
        bandeiras = metadados[3 * quantos : 4 * quantos]
        campos = iter(metadados[4 * quantos :].split(b"\0"))
        nomes = []
        for bandeira in bandeiras:
            nomes.append(next(campos))
            # Depois do id podem vir o nome de arquivo e o título, cada um com o seu bit.
            for bit in (0x80, 0x40):
                if bandeira & bit:
                    next(campos)
        return nomes
    return []


def paginas_soltas(dados: bytes) -> list[bytes]:
    """Cada página como um DjVu de uma página só, com o dicionário no lugar do `INCL`.

    **O dicionário sai pelo nome, lido do `DIRM`.** A ordem do arquivo parecia bastar, e bastava em
    quase todos, mas num livro editado os dicionários estão fora de ordem e a contagem ainda bate:
    o dicionário errado decodifica sem erro e troca letras em silêncio.

    `INCL` que não leva a dicionário nenhum é anotação compartilhada, que este programa não usa, e
    some da página. Se ele fosse de um dicionário perdido, o JB2 recusa, e a página sai como
    ilegível. Dicionário que herda de outro é recusado: embuti-lo sozinho perderia o que ele herda.

    Um DjVu de uma página só já é o que esta função devolve.
    """
    if dados[12:16] != b"DJVM":
        return [dados]
    componentes = list(_componentes(dados))
    citam = any(identificador == b"INCL" for _forma, pedacos in componentes for identificador, _ in pedacos)
    nomes = _nomes_do_dirm(dados) if citam else [b""] * len(componentes)
    dicionarios: dict[bytes, bytes] = {}
    paginas: list[list[tuple[bytes, bytes]]] = []
    for nome, (forma, pedacos) in zip(nomes, componentes, strict=True):
        if forma == b"DJVI":
            djbz = [conteudo for identificador, conteudo in pedacos if identificador == b"Djbz"]
            if djbz and any(identificador == b"INCL" for identificador, _ in pedacos):
                raise ValueError("este DjVu tem dicionário que herda de outro, e isso não dá para embutir")
            if djbz:
                dicionarios[nome] = djbz[0]
        elif forma in _FORMAS_DE_PAGINA:
            paginas.append(pedacos)
    soltas = []
    for pedacos in paginas:
        corpo = bytearray(b"DJVU")
        for identificador, conteudo in pedacos:
            if identificador != b"INCL":
                corpo += _pedaco(identificador, conteudo)
            elif conteudo.split(b"\0")[0] in dicionarios:
                corpo += _pedaco(b"Djbz", dicionarios[conteudo.split(b"\0")[0]])
        soltas.append(b"AT&TFORM" + struct.pack(">I", len(corpo)) + bytes(corpo))
    return soltas
