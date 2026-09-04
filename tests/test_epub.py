"""O EPUB 3 do estudo e do texto (S-542).

**O que se trava é o pacote, não a prosa.** Um EPUB que o leitor recusa é o que acontece quando o
`mimetype` sai comprimido, quando um XHTML tem um `&` solto, ou quando o manifesto aponta uma imagem
que ninguém gravou -- e nenhum dos três aparece ao abrir o zip à mão. Os testes conferem os três com
a `zipfile` e o `ElementTree` diretamente, e **também** por `epub.verificar`, para o verificador ser
provado contra defeitos fabricados e não só contra o que o módulo escreve certo.
"""

from __future__ import annotations

import io
import posixpath
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import chess

from chess_diagram_ocr import epub, estudo_paragrafos
from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo
from chess_diagram_ocr.text import rico
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from tests.ambiente_de_teste import pasta_temporaria

ITALIANA = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"
XHTML = f"{{{epub.XHTML_NS}}}"
OPF = f"{{{epub.OPF_NS}}}"
DC = f"{{{epub.DC_NS}}}"


def _estudo(*, pede_diagrama: bool = False) -> Estudo:
    e = Estudo.de_posicao(
        PosicaoDeEstudo(placement=ITALIANA, vez="b", lance=4, ancora=Ancora(documento="C:/livros/Secrets.pdf", pagina=142, diagrama=1))
    )
    bc5 = e.jogo.add_variation(chess.Move.from_uci("f8c5"))
    bc5.nags.add(5)
    bc5.comment = "a italiana & <isto>" + (" [%D]" if pede_diagrama else "")
    bc5.add_variation(chess.Move.from_uci("e1g1"))
    bc5.add_variation(chess.Move.from_uci("c2c3")).comment = "a outra"
    return e


def _pagina(*blocos: object) -> PaginaLida:
    return PaginaLida(documento="livro.pdf", pagina=57, colunas=(Coluna(indice=0, blocos=tuple(blocos)),))  # type: ignore[arg-type]


def _texto(conteudo: str) -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas([LinhaLida(conteudo, (0.0, 0.0, 100.0, 9.0), 1.0, "camada")])  # type: ignore[arg-type]


def _documento(*, com_placement: bool = True) -> rico.DocumentoRico:
    """Uma folha com título, duas linhas, um diagrama lido e um só com a marca."""
    doc = rico.de_pagina(
        _pagina(
            _texto("Um título"),
            _texto("Uma frase com <isto> & aquilo.\nSegunda linha."),
            BlocoDeDiagrama(indice=1, bbox=(0.0, 0.0, 9.0, 9.0), placement="8/8/8/8/8/8/8/K6k" if com_placement else ""),
            BlocoDeDiagrama(indice=2, bbox=(0.0, 0.0, 9.0, 9.0)),
            _texto("Outra frase."),
        )
    )
    doc = rico.aplicar_estilo(doc, 0, 3, rico.ESTILO_TITULO)
    doc = rico.alternar(doc, 10, 13, "negrito")
    return rico.aplicar(doc, 14, 19, italico=True, cor="nota")


def _membros(dados: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(dados)) as zip_:
        return {info.filename: zip_.read(info.filename) for info in zip_.infolist()}


def _capitulos(dados: bytes) -> list[ET.Element]:
    return [ET.fromstring(c) for n, c in sorted(_membros(dados).items()) if n.startswith(f"{epub.PASTA}/") and n.endswith(".xhtml") and not n.endswith(epub.NAV)]


def _livro_do_estudo(**argumentos: object) -> bytes:
    livro = epub.Livro(metadados=epub.Metadados().resolvidos(), css=epub.folha_de_estilo())
    capitulo, _ = epub.capitulo_do_estudo(_estudo(**argumentos), 1, livro.imagens)  # type: ignore[arg-type]
    livro.capitulos.append(capitulo)
    return epub.empacotar(livro)


class PacoteTests(unittest.TestCase):
    def test_o_mimetype_e_o_primeiro_membro_e_vai_armazenado(self) -> None:
        """É a regra que deixa o leitor reconhecer o arquivo lendo os primeiros bytes."""
        dados = _livro_do_estudo()
        with zipfile.ZipFile(io.BytesIO(dados)) as zip_:
            primeiro = zip_.infolist()[0]
        self.assertEqual(primeiro.filename, "mimetype")
        self.assertEqual(primeiro.compress_type, zipfile.ZIP_STORED)
        self.assertEqual(_membros(dados)["mimetype"], b"application/epub+zip")
        self.assertEqual(dados[30:38], b"mimetype")

    def test_todo_xml_do_pacote_e_bem_formado(self) -> None:
        for nome, conteudo in _membros(_livro_do_estudo()).items():
            if Path(nome).suffix in (".xhtml", ".opf", ".xml", ".svg"):
                with self.subTest(arquivo=nome):
                    ET.fromstring(conteudo)

    def test_toda_referencia_do_manifesto_existe_no_zip(self) -> None:
        membros = _membros(_livro_do_estudo(pede_diagrama=True))
        opf = ET.fromstring(membros[f"{epub.PASTA}/{epub.OPF}"])
        hrefs = [item.get("href", "") for item in opf.iter(f"{OPF}item")]
        self.assertGreaterEqual(len(hrefs), 5)
        for href in hrefs:
            self.assertIn(posixpath.join(epub.PASTA, href), membros)

    def test_o_container_aponta_o_opf_e_o_opf_tem_os_dc_obrigatorios(self) -> None:
        membros = _membros(_livro_do_estudo())
        container = ET.fromstring(membros["META-INF/container.xml"])
        rootfile = container.find(f".//{{{epub.CONTAINER_NS}}}rootfile")
        assert rootfile is not None
        self.assertIn(rootfile.get("full-path"), membros)
        opf = ET.fromstring(membros[rootfile.get("full-path", "")])
        for nome in ("identifier", "title", "language"):
            self.assertIsNotNone(opf.find(f".//{DC}{nome}"), nome)
        self.assertIsNotNone(opf.find(f".//{OPF}meta[@property='dcterms:modified']"))
        self.assertEqual(opf.get("version"), "3.0")

    def test_a_espinha_lista_os_capitulos_na_ordem_e_o_nav_os_nomeia(self) -> None:
        pasta = pasta_temporaria(self)
        relatorio = epub.exportar_estudos_epub([_estudo(), _estudo()], pasta / "dois.epub", epub.Metadados(titulo="Dois"))
        membros = _membros(relatorio.caminho.read_bytes())
        opf = ET.fromstring(membros[f"{epub.PASTA}/{epub.OPF}"])
        self.assertEqual([r.get("idref") for r in opf.iter(f"{OPF}itemref")], ["estudo_001", "estudo_002"])
        nav = ET.fromstring(membros[f"{epub.PASTA}/{epub.NAV}"])
        self.assertEqual(len(list(nav.iter(f"{XHTML}li"))), 2)
        self.assertEqual(relatorio.capitulos, 2)

    def test_verificar_aprova_o_que_o_modulo_escreve(self) -> None:
        self.assertEqual(epub.verificar(_livro_do_estudo(pede_diagrama=True)), [])


class VerificadorTests(unittest.TestCase):
    """O verificador provado contra defeito fabricado, para não ser uma guarda vácua."""

    def _quebrado(self, *, mimetype_comprimido: bool = False, sem_imagem: bool = False, xml_ruim: bool = False) -> bytes:
        membros = _membros(_livro_do_estudo())
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zip_:
            for nome, conteudo in membros.items():
                if nome == "mimetype":
                    tipo = zipfile.ZIP_DEFLATED if mimetype_comprimido else zipfile.ZIP_STORED
                    zip_.writestr(zipfile.ZipInfo(nome), conteudo, compress_type=tipo)
                    continue
                if sem_imagem and nome.endswith(".svg"):
                    continue
                if xml_ruim and nome.endswith("estudo_001.xhtml"):
                    conteudo = conteudo.replace(b"</section>", b"")
                zip_.writestr(nome, conteudo, compress_type=zipfile.ZIP_DEFLATED)
        return buffer.getvalue()

    def test_pega_o_mimetype_comprimido(self) -> None:
        self.assertTrue(any("comprimido" in p for p in epub.verificar(self._quebrado(mimetype_comprimido=True))))

    def test_pega_a_imagem_que_o_manifesto_promete_e_o_zip_nao_tem(self) -> None:
        self.assertTrue(any("não está no zip" in p for p in epub.verificar(self._quebrado(sem_imagem=True))))

    def test_pega_o_xhtml_mal_formado(self) -> None:
        self.assertTrue(any("mal formado" in p for p in epub.verificar(self._quebrado(xml_ruim=True))))

    def test_o_que_nao_e_zip_e_dito_em_portugues(self) -> None:
        self.assertEqual(len(epub.verificar(b"isto nao e um zip")), 1)


class CapituloDoEstudoTests(unittest.TestCase):
    def test_o_capitulo_tem_titulo_figura_lance_comentario_e_variante(self) -> None:
        (capitulo,) = _capitulos(_livro_do_estudo())
        corpo = ET.tostring(capitulo, encoding="unicode")
        self.assertIn("Secrets.pdf", capitulo.find(f".//{XHTML}h1").text or "")  # type: ignore[union-attr]
        self.assertEqual(len(list(capitulo.iter(f"{XHTML}figure"))), 1)
        classes = {p.get("class") for p in capitulo.iter(f"{XHTML}p")}
        self.assertIn("lance", classes)
        self.assertIn("comentario", classes)
        self.assertIn("variante nivel-1", classes)
        self.assertIn("a italiana &amp; &lt;isto&gt;", corpo)

    def test_o_D_vira_uma_segunda_figura_com_o_seu_svg(self) -> None:
        dados = _livro_do_estudo(pede_diagrama=True)
        (capitulo,) = _capitulos(dados)
        figuras = list(capitulo.iter(f"{XHTML}img"))
        self.assertEqual([f.get("alt") for f in figuras], ["Diagrama 1", "Diagrama 2"])
        membros = _membros(dados)
        for figura in figuras:
            svg = membros[posixpath.join(epub.PASTA, figura.get("src", ""))]
            self.assertEqual(ET.fromstring(svg).tag, "{http://www.w3.org/2000/svg}svg")

    def test_a_figura_leva_a_fen_na_legenda(self) -> None:
        (capitulo,) = _capitulos(_livro_do_estudo())
        legenda = capitulo.find(f".//{XHTML}figcaption")
        assert legenda is not None
        self.assertTrue((legenda.text or "").startswith("FEN: " + ITALIANA))

    def test_o_relatorio_conta_os_diagramas_e_o_titulo_do_livro_e_o_do_estudo(self) -> None:
        pasta = pasta_temporaria(self)
        relatorio = epub.exportar_estudo_epub(_estudo(pede_diagrama=True), pasta / "um.epub")
        membros = _membros(relatorio.caminho.read_bytes())
        self.assertEqual((relatorio.capitulos, relatorio.diagramas, relatorio.svg), (1, 2, 2))
        self.assertEqual(relatorio.tamanho, relatorio.caminho.stat().st_size)
        titulo = ET.fromstring(membros[f"{epub.PASTA}/{epub.OPF}"]).find(f".//{DC}title")
        self.assertEqual(titulo.text, estudo_paragrafos.titulo_do_estudo(_estudo()))  # type: ignore[union-attr]
        self.assertIn("2 diagrama(s)", relatorio.resumo())


class CapituloDoTextoTests(unittest.TestCase):
    def _exportar(self, doc: rico.DocumentoRico, **argumentos: object) -> tuple[epub.Relatorio, dict[str, bytes]]:
        pasta = pasta_temporaria(self)
        relatorio = epub.exportar_texto_epub(doc, pasta / "folha.epub", **argumentos)  # type: ignore[arg-type]
        return relatorio, _membros(relatorio.caminho.read_bytes())

    def test_a_quebra_de_linha_vira_paragrafo_e_nao_br(self) -> None:
        """Um leitor de EPUB reflui parágrafo, não quebra de linha."""
        _, membros = self._exportar(_documento())
        (capitulo,) = [ET.fromstring(c) for n, c in membros.items() if n.endswith("folha_001.xhtml")]
        textos = ["".join(p.itertext()) for p in capitulo.iter(f"{XHTML}p") if p.get("class") != "marca"]
        self.assertIn("Uma frase com <isto> & aquilo.", textos)
        self.assertIn("Segunda linha.", textos)
        self.assertEqual(list(capitulo.iter(f"{XHTML}br")), [])

    def test_a_formatacao_inline_e_a_do_html_da_fase_39_e_a_folha_traz_a_regra(self) -> None:
        _, membros = self._exportar(_documento(), cores={"cor-nota": "#aa0000"})
        xhtml = membros[f"{epub.PASTA}/folha_001.xhtml"].decode("utf-8")
        self.assertIn("<strong>", xhtml)
        self.assertIn('class="cor-nota"', xhtml)
        css = membros[f"{epub.PASTA}/{epub.CSS}"].decode("utf-8")
        self.assertIn(".cor-nota { color: #aa0000; }", css)
        self.assertIn(".fora-do-modelo", css)

    def test_o_titulo_do_documento_abre_o_capitulo_e_sem_ele_entra_o_nome_da_folha(self) -> None:
        """Um capítulo começa por um título: o do documento quando a folha tem um, o da folha
        (`livro.pdf — folha 58`) quando não tem -- é o que o índice do leitor mostra."""
        _, membros = self._exportar(_documento())
        capitulo = ET.fromstring(membros[f"{epub.PASTA}/folha_001.xhtml"])
        secao = capitulo.find(f".//{XHTML}section")
        assert secao is not None
        self.assertEqual(secao[0].tag, f"{XHTML}h2")
        self.assertEqual("".join(secao[0].itertext()), "Um título")
        self.assertIsNone(capitulo.find(f".//{XHTML}h1"))
        _, sem_titulo = self._exportar(rico.de_pagina(_pagina(_texto("Só prosa."))))
        capitulo = ET.fromstring(sem_titulo[f"{epub.PASTA}/folha_001.xhtml"])
        self.assertIn("livro.pdf — folha 58", capitulo.find(f".//{XHTML}h1").text or "")  # type: ignore[union-attr]

    def test_o_diagrama_lido_vira_svg_e_o_sem_nada_vira_a_marca(self) -> None:
        """**A marca nunca desaparece** (S-250): é o `alt` da imagem, e é o parágrafo quando não há
        imagem. E o relatório distingue os dois, porque "não havia" e "havia e saiu só a marca" são
        coisas diferentes para quem vai imprimir."""
        relatorio, membros = self._exportar(_documento())
        xhtml = membros[f"{epub.PASTA}/folha_001.xhtml"].decode("utf-8")
        self.assertIn('alt="[Diagrama 2]"', xhtml)
        self.assertIn('<p class="marca">[Diagrama 3]</p>', xhtml)
        self.assertEqual((relatorio.diagramas, relatorio.svg, relatorio.png, relatorio.so_marca), (2, 1, 0, 1))
        self.assertEqual(len(relatorio.avisos), 1)
        self.assertTrue(any(n.endswith("folha_001_bloco_002.svg") for n in membros))

    def test_o_png_injetado_entra_no_lugar_do_svg_que_nao_ha(self) -> None:
        png = b"\x89PNG\r\n\x1a\nfalso"
        relatorio, membros = self._exportar(_documento(com_placement=False), imagens={2: png})
        self.assertEqual((relatorio.svg, relatorio.png, relatorio.so_marca), (0, 1, 1))
        self.assertEqual(membros[f"{epub.PASTA}/{epub.PASTA_DE_IMAGENS}/folha_001_bloco_002.png"], png)
        opf = membros[f"{epub.PASTA}/{epub.OPF}"].decode("utf-8")
        self.assertIn('media-type="image/png"', opf)
        self.assertEqual(epub.verificar(_membros_para_bytes(membros)), [])


def _membros_para_bytes(membros: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_:
        zip_.writestr(zipfile.ZipInfo("mimetype"), membros["mimetype"], compress_type=zipfile.ZIP_STORED)
        for nome, conteudo in membros.items():
            if nome != "mimetype":
                zip_.writestr(nome, conteudo, compress_type=zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


class MetadadosTests(unittest.TestCase):
    def test_sem_identificador_gera_um_urn_uuid_e_uma_data_no_formato_do_epub(self) -> None:
        dados = epub.Metadados().resolvidos()
        self.assertTrue(dados.identificador.startswith("urn:uuid:"))
        self.assertRegex(dados.modificado, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_o_que_veio_de_fora_fica(self) -> None:
        dados = epub.Metadados(titulo="Livro", autor="Eu", identificador="isbn:1", modificado="2026-09-04T00:00:00Z").resolvidos()
        self.assertEqual((dados.identificador, dados.modificado), ("isbn:1", "2026-09-04T00:00:00Z"))
        pasta = pasta_temporaria(self)
        relatorio = epub.exportar_estudo_epub(_estudo(), pasta / "m.epub", dados)
        opf = _membros(relatorio.caminho.read_bytes())[f"{epub.PASTA}/{epub.OPF}"].decode("utf-8")
        self.assertIn("<dc:title>Livro</dc:title>", opf)
        self.assertIn("<dc:creator>Eu</dc:creator>", opf)


class FolhaDeEstiloTests(unittest.TestCase):
    def test_os_tres_estilos_de_livro_estao_na_folha(self) -> None:
        """São os mesmos que o DOCX nomeia: Lance em negrito, Variante em itálico recuado."""
        css = epub.folha_de_estilo()
        self.assertIn("p.lance { font-weight: bold; }", css)
        self.assertIn("p.variante { font-style: italic; margin-left: 1.5em; }", css)
        self.assertIn("figure.diagrama img { width: 18em;", css)


if __name__ == "__main__":
    unittest.main()
