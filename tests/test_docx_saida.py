"""O DOCX do estudo e do texto, escrito como OOXML mínimo (S-543).

**O que se trava é o que o Word recusa em silêncio.** Um `.docx` sem tipo de conteúdo para uma
parte, com um `r:embed` sem relação ou com um `&` solto no `document.xml` abre como "conteúdo
ilegível" -- e nada disso aparece ao listar o zip. Os testes conferem as três coisas com a `zipfile`
e o `ElementTree` diretamente, e provam `docx_saida.verificar` contra defeitos fabricados.
"""

from __future__ import annotations

import io
import re
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import chess

from chess_diagram_ocr import docx_saida
from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo
from chess_diagram_ocr.text import rico
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from tests.ambiente_de_teste import pasta_temporaria

ITALIANA = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"
W = f"{{{docx_saida.NS_W}}}"
R = f"{{{docx_saida.NS_R}}}"
A = f"{{{docx_saida.NS_A}}}"
ASVG = f"{{{docx_saida.NS_ASVG}}}"


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
    doc = rico.aplicar(doc, 14, 19, italico=True, sublinhado=True, cor="nota", realce="destaque")
    return rico.aplicar_corpo(doc, 20, 25, 2)


def _membros(dados: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(dados)) as zip_:
        return {info.filename: zip_.read(info.filename) for info in zip_.infolist()}


def _estudo_em_bytes(**argumentos: object) -> bytes:
    """Em memória: `Documento` é a mesma montagem de `exportar_estudo_docx`, sem o disco."""
    doc = docx_saida.Documento()
    docx_saida._estudo(doc, _estudo(**argumentos), 1, docx_saida.LARGURA_PADRAO_CM)  # type: ignore[arg-type]
    return doc.empacotar()


def _paragrafos(dados: bytes) -> list[tuple[str, str]]:
    """`(estilo, texto)` de cada `<w:p>` do documento."""
    corpo = ET.fromstring(_membros(dados)["word/document.xml"]).find(f"{W}body")
    assert corpo is not None
    saida = []
    for p in corpo.iter(f"{W}p"):
        estilo = p.find(f"{W}pPr/{W}pStyle")
        saida.append((estilo.get(f"{W}val", "") if estilo is not None else "", "".join(t.text or "" for t in p.iter(f"{W}t"))))
    return saida


class PacoteTests(unittest.TestCase):
    def test_as_partes_obrigatorias_estao_no_zip(self) -> None:
        membros = _membros(_estudo_em_bytes())
        for parte in ("[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml", "word/_rels/document.xml.rels"):
            self.assertIn(parte, membros)

    def test_todo_xml_e_bem_formado(self) -> None:
        for nome, conteudo in _membros(_estudo_em_bytes()).items():
            if nome.endswith((".xml", ".rels", ".svg")):
                with self.subTest(arquivo=nome):
                    ET.fromstring(conteudo)

    def test_a_raiz_aponta_o_documento_e_toda_parte_tem_tipo_de_conteudo(self) -> None:
        membros = _membros(_estudo_em_bytes())
        rels = ET.fromstring(membros["_rels/.rels"])
        alvos = {r.get("Target") for r in rels.iter(f"{{{docx_saida.NS_REL}}}Relationship")}
        self.assertIn("word/document.xml", alvos)
        tipos = ET.fromstring(membros["[Content_Types].xml"])
        padroes = {d.get("Extension") for d in tipos.iter(f"{{{docx_saida.NS_CT}}}Default")}
        sobrescritos = {o.get("PartName") for o in tipos.iter(f"{{{docx_saida.NS_CT}}}Override")}
        self.assertIn("/word/document.xml", sobrescritos)
        self.assertTrue({"rels", "xml", "png", "svg"} <= padroes, padroes)

    def test_todo_r_embed_tem_relacao_e_toda_relacao_tem_parte(self) -> None:
        membros = _membros(_estudo_em_bytes(pede_diagrama=True))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(membros["word/_rels/document.xml.rels"]).iter(f"{{{docx_saida.NS_REL}}}Relationship")}
        embeds = [e.get(f"{R}embed") for e in ET.fromstring(membros["word/document.xml"]).iter() if e.get(f"{R}embed")]
        self.assertEqual(len(embeds), 4)  # dois diagramas, PNG e SVG cada
        for embed in embeds:
            self.assertIn(f"word/{rels[embed]}", membros)

    def test_verificar_aprova_o_que_o_modulo_escreve(self) -> None:
        self.assertEqual(docx_saida.verificar(_estudo_em_bytes(pede_diagrama=True)), [])


class VerificadorTests(unittest.TestCase):
    def _quebrado(self, *, sem_relacao: bool = False, sem_tipo: bool = False, xml_ruim: bool = False) -> bytes:
        membros = _membros(_estudo_em_bytes())
        if sem_relacao:
            alvo = f'Id="{docx_saida.RID_ESTILOS[:-1]}5"'.encode()  # a primeira relação de imagem
            membros["word/_rels/document.xml.rels"] = membros["word/_rels/document.xml.rels"].replace(alvo, b'Id="rId99"')
        if sem_tipo:
            membros["[Content_Types].xml"] = membros["[Content_Types].xml"].replace(b'<Default Extension="png" ContentType="image/png"/>', b"")
        if xml_ruim:
            membros["word/document.xml"] = membros["word/document.xml"].replace(b"</w:body>", b"")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zip_:
            for nome, conteudo in membros.items():
                zip_.writestr(nome, conteudo)
        return buffer.getvalue()

    def test_pega_o_embed_sem_relacao(self) -> None:
        self.assertTrue(any("sem relação" in p for p in docx_saida.verificar(self._quebrado(sem_relacao=True))))

    def test_pega_a_parte_sem_tipo_de_conteudo(self) -> None:
        self.assertTrue(any("sem tipo de conteúdo" in p for p in docx_saida.verificar(self._quebrado(sem_tipo=True))))

    def test_pega_o_xml_mal_formado(self) -> None:
        self.assertTrue(any("mal formado" in p for p in docx_saida.verificar(self._quebrado(xml_ruim=True))))


class EstilosTests(unittest.TestCase):
    def test_os_estilos_de_livro_existem_com_o_traco_que_o_nome_promete(self) -> None:
        """Lance em negrito, Variante em itálico e recuada: quem abre o arquivo retoca na galeria
        de estilos, não parágrafo a parágrafo."""
        estilos = {s.get(f"{W}styleId"): s for s in ET.fromstring(_membros(_estudo_em_bytes())["word/styles.xml"]).iter(f"{W}style")}
        for identificador in ("Normal", docx_saida.TITULO, docx_saida.LANCE, docx_saida.VARIANTE, docx_saida.COMENTARIO, docx_saida.LEGENDA):
            self.assertIn(identificador, estilos)
        self.assertIsNotNone(estilos[docx_saida.LANCE].find(f"{W}rPr/{W}b"))
        self.assertIsNotNone(estilos[docx_saida.VARIANTE].find(f"{W}rPr/{W}i"))
        self.assertIsNotNone(estilos[docx_saida.VARIANTE].find(f"{W}pPr/{W}ind"))
        self.assertIsNotNone(estilos[docx_saida.TITULO].find(f"{W}pPr/{W}outlineLvl"))

    def test_os_nomes_visiveis_tem_acento(self) -> None:
        nomes = {s.find(f"{W}name").get(f"{W}val") for s in ET.fromstring(_membros(_estudo_em_bytes())["word/styles.xml"]).iter(f"{W}style")}  # type: ignore[union-attr]
        self.assertIn("Comentário", nomes)
        self.assertIn("Variante 2", nomes)
        self.assertIn(docx_saida.NOME_DO_TITULO, nomes)


class EstudoTests(unittest.TestCase):
    def test_cada_paragrafo_do_estudo_sai_com_o_estilo_do_seu_tipo(self) -> None:
        paragrafos = _paragrafos(_estudo_em_bytes())
        estilos = [e for e, _ in paragrafos]
        self.assertEqual(estilos[0], docx_saida.TITULO)
        self.assertIn(docx_saida.DIAGRAMA, estilos)
        self.assertNotIn(docx_saida.LEGENDA, estilos)  # a FEN só sai com `com_fen`
        self.assertTrue(any(e == docx_saida.LANCE and "4...Bc5" in t for e, t in paragrafos), paragrafos)
        self.assertTrue(any(e == docx_saida.COMENTARIO and t == "a italiana & <isto>" for e, t in paragrafos), paragrafos)
        self.assertTrue(any(e == docx_saida.VARIANTE and t.startswith("5.c3") for e, t in paragrafos), paragrafos)

    def test_o_diagrama_leva_png_no_blip_e_svg_na_extensao(self) -> None:
        """O par que o próprio Word grava: o PNG é o que todo leitor mostra, o SVG é o que o Word
        novo prefere. Um DOCX só com SVG abre em branco fora dele."""
        membros = _membros(_estudo_em_bytes())
        documento = ET.fromstring(membros["word/document.xml"])
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(membros["word/_rels/document.xml.rels"]).iter(f"{{{docx_saida.NS_REL}}}Relationship")}
        blips = list(documento.iter(f"{A}blip"))
        self.assertEqual(len(blips), 1)
        png = membros[f"word/{rels[blips[0].get(f'{R}embed', '')]}"]
        self.assertTrue(png.startswith(b"\x89PNG"))
        svgs = list(documento.iter(f"{ASVG}svgBlip"))
        self.assertEqual(len(svgs), 1)
        svg = membros[f"word/{rels[svgs[0].get(f'{R}embed', '')]}"]
        self.assertEqual(ET.fromstring(svg).tag, "{http://www.w3.org/2000/svg}svg")

    def test_o_diagrama_mede_o_que_se_pediu(self) -> None:
        pasta = pasta_temporaria(self)
        dados = docx_saida.exportar_estudo_docx(_estudo(), pasta / "e.docx", largura_cm=5.0).caminho.read_bytes()
        extent = ET.fromstring(_membros(dados)["word/document.xml"]).find(f".//{{{docx_saida.NS_WP}}}extent")
        assert extent is not None
        self.assertEqual(extent.get("cx"), str(5 * docx_saida.EMU_POR_CM))
        self.assertEqual(extent.get("cx"), extent.get("cy"))

    def test_o_relatorio_conta_e_o_titulo_do_arquivo_e_o_do_estudo(self) -> None:
        pasta = pasta_temporaria(self)
        relatorio = docx_saida.exportar_estudo_docx(_estudo(pede_diagrama=True), pasta / "e.docx")
        membros = _membros(relatorio.caminho.read_bytes())
        self.assertEqual((relatorio.diagramas, relatorio.png, relatorio.svg, relatorio.so_marca), (2, 2, 2, 0))
        self.assertEqual(relatorio.tamanho, relatorio.caminho.stat().st_size)
        self.assertIn("Secrets.pdf", membros["docProps/core.xml"].decode("utf-8"))
        self.assertIn("2 diagrama(s)", relatorio.resumo())

    def test_varios_estudos_tem_uma_quebra_de_pagina_entre_cada_dois(self) -> None:
        pasta = pasta_temporaria(self)
        dados = docx_saida.exportar_estudos_docx([_estudo(), _estudo(), _estudo()], pasta / "tres.docx").caminho.read_bytes()
        quebras = [b for b in ET.fromstring(_membros(dados)["word/document.xml"]).iter(f"{W}br") if b.get(f"{W}type") == "page"]
        self.assertEqual(len(quebras), 3)  # uma depois do sumário, duas entre os três estudos
        self.assertEqual(sum(1 for e, _ in _paragrafos(dados) if e == docx_saida.TITULO), 4)  # e o do sumário


class TextoTests(unittest.TestCase):
    def _exportar(self, doc: rico.DocumentoRico, **argumentos: object) -> tuple[docx_saida.Relatorio, dict[str, bytes]]:
        pasta = pasta_temporaria(self)
        relatorio = docx_saida.exportar_texto_docx(doc, pasta / "folha.docx", **argumentos)  # type: ignore[arg-type]
        return relatorio, _membros(relatorio.caminho.read_bytes())

    def test_a_quebra_de_linha_corta_o_paragrafo_e_o_titulo_vira_Titulo(self) -> None:
        _, membros = self._exportar(_documento())
        paragrafos = _paragrafos(_membros_para_bytes(membros))
        textos = [t for _, t in paragrafos]
        self.assertIn("Uma frase com <isto> & aquilo.", textos)
        self.assertIn("Segunda linha.", textos)
        self.assertEqual(paragrafos[0], (docx_saida.TITULO, "Um título"))

    def test_a_formatacao_inline_chega_ao_run_com_a_cor_e_o_corpo_resolvidos_de_fora(self) -> None:
        """Nenhum hexadecimal é escrito no módulo: o que `cores` e `corpos` não trouxerem não sai."""
        _, membros = self._exportar(_documento(), cores={"cor-nota": "#aa0000", "realce-destaque": "#ffff00"}, corpos={"corpo-mais-2": "13pt"})
        documento = membros["word/document.xml"].decode("utf-8")
        self.assertIn("<w:b/>", documento)
        self.assertIn("<w:i/>", documento)
        self.assertIn('<w:u w:val="single"/>', documento)
        self.assertIn('<w:color w:val="AA0000"/>', documento)
        self.assertIn('w:fill="FFFF00"', documento)
        self.assertIn('<w:sz w:val="26"/>', documento)
        self.assertIn("&lt;isto&gt; &amp; aquilo.", documento)
        _, sem_mapas = self._exportar(_documento())
        self.assertNotIn("<w:color", sem_mapas["word/document.xml"].decode("utf-8"))

    def test_o_diagrama_lido_vira_par_png_svg_e_o_sem_nada_vira_a_marca(self) -> None:
        relatorio, membros = self._exportar(_documento())
        self.assertEqual((relatorio.diagramas, relatorio.png, relatorio.svg, relatorio.so_marca), (2, 1, 1, 1))
        self.assertEqual(len(relatorio.avisos), 1)
        self.assertIn((docx_saida.MARCA, "[Diagrama 3]"), _paragrafos(_membros_para_bytes(membros)))
        self.assertIn("word/media/folha_001_bloco_002.svg", membros)

    def test_o_png_injetado_entra_sem_svg(self) -> None:
        png = b"\x89PNG\r\n\x1a\nfalso"
        relatorio, membros = self._exportar(_documento(com_placement=False), imagens={2: png})
        self.assertEqual((relatorio.png, relatorio.svg, relatorio.so_marca), (1, 0, 1))
        self.assertEqual(membros["word/media/folha_001_bloco_002.png"], png)
        self.assertEqual(docx_saida.verificar(_membros_para_bytes(membros)), [])


def _membros_para_bytes(membros: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_:
        for nome, conteudo in membros.items():
            zip_.writestr(nome, conteudo)
    return buffer.getvalue()


class MiudezasTests(unittest.TestCase):
    def test_run_escapa_o_que_o_xml_nao_aceita(self) -> None:
        self.assertIn("&lt;a&gt; &amp; b", docx_saida.run("<a> & b"))
        self.assertNotIn("<w:rPr>", docx_saida.run("puro"))

    def test_o_corpo_em_pontos_vira_meio_ponto_e_o_resto_nao_vira_nada(self) -> None:
        self.assertEqual(docx_saida._meios_pontos("13pt"), 26)
        self.assertEqual(docx_saida._meios_pontos("13,5pt"), 27)
        self.assertEqual(docx_saida._meios_pontos("1.2em"), 0)
        self.assertEqual(docx_saida._meios_pontos(""), 0)

    def test_so_hexadecimal_de_seis_digitos_vira_cor(self) -> None:
        self.assertEqual(docx_saida._hex("#aa0000"), "AA0000")
        self.assertEqual(docx_saida._hex("red"), "")

    def test_nenhuma_cor_e_escrita_no_modulo(self) -> None:
        fonte = Path(docx_saida.__file__).read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{6}\b", fonte), [])


class EstruturaDoWordTests(unittest.TestCase):
    """O que faz um `.docx` ser um documento e não uma tira de parágrafos."""

    def setUp(self) -> None:
        pasta = pasta_temporaria(self)
        self.dados = docx_saida.exportar_estudos_docx([_estudo(), _estudo()], pasta / "dois.docx").caminho.read_bytes()
        self.membros = _membros(self.dados)

    def test_o_titulo_e_o_estilo_interno_de_titulo_do_Word(self) -> None:
        """**O nome do estilo, e não o `styleId`, é o que faz um parágrafo virar título.** O Calibre
        casa `heading\\s+(\\d+)$` sobre o `w:name`; com `Título` ele relatava *"Auto generated TOC
        with 0 entries"* sobre um documento com 2.618 títulos."""
        estilos = {s.get(f"{W}styleId"): s for s in ET.fromstring(self.membros["word/styles.xml"]).iter(f"{W}style")}
        for identificador, esperado in ((docx_saida.TITULO, "heading 1"), (docx_saida.SUBTITULO, "heading 2")):
            self.assertIn(identificador, estilos)
            nome = estilos[identificador].find(f"{W}name")
            assert nome is not None
            self.assertEqual(nome.get(f"{W}val"), esperado)
            self.assertRegex(esperado, r"^heading\s+\d+$")
            self.assertIsNotNone(estilos[identificador].find(f"{W}pPr/{W}outlineLvl"))

    def test_o_documento_abre_com_o_campo_de_sumario(self) -> None:
        documento = self.membros["word/document.xml"].decode("utf-8")
        self.assertIn('TOC \\o "1-3"', documento)
        self.assertIn('w:fldCharType="begin"', documento)
        self.assertIn('w:fldCharType="end"', documento)
        configuracao = self.membros["word/settings.xml"].decode("utf-8")
        self.assertIn('<w:updateFields w:val="true"/>', configuracao)

    def test_ha_cabecalho_rodape_e_numero_de_pagina(self) -> None:
        """Um livro de novecentas páginas sem número de página não se consulta."""
        for parte in ("word/header1.xml", "word/footer1.xml"):
            self.assertIn(parte, self.membros)
        self.assertIn(" PAGE ", self.membros["word/footer1.xml"].decode("utf-8"))
        secao = ET.fromstring(self.membros["word/document.xml"]).find(f".//{W}sectPr")
        assert secao is not None
        # A ordem é imposta pelo esquema: as referências abrem o `sectPr`, ou o Word recusa.
        self.assertEqual([e.tag for e in secao][:2], [f"{W}headerReference", f"{W}footerReference"])
        relacoes = {
            r.get("Id"): r.get("Target")
            for r in ET.fromstring(self.membros["word/_rels/document.xml.rels"]).iter(f"{{{docx_saida.NS_REL}}}Relationship")
        }
        self.assertEqual(relacoes[docx_saida.RID_CABECALHO], "header1.xml")
        self.assertEqual(relacoes[docx_saida.RID_RODAPE], "footer1.xml")

    def test_as_partes_novas_tem_tipo_de_conteudo_declarado(self) -> None:
        self.assertEqual(docx_saida.verificar(self.dados), [])
        tipos = ET.fromstring(self.membros["[Content_Types].xml"])
        sobrescritos = {o.get("PartName") for o in tipos.iter(f"{{{docx_saida.NS_CT}}}Override")}
        for parte in ("/word/settings.xml", "/word/header1.xml", "/word/footer1.xml", "/docProps/app.xml"):
            self.assertIn(parte, sobrescritos)

    def test_o_programa_nao_assina_o_documento_como_autor(self) -> None:
        nucleo = self.membros["docProps/core.xml"].decode("utf-8")
        self.assertNotIn("<dc:creator>", nucleo)
        self.assertIn(f"<cp:lastModifiedBy>{docx_saida.PRODUTOR}</cp:lastModifiedBy>", nucleo)


class SvgEmbutidoTests(unittest.TestCase):
    def test_o_svg_do_pacote_e_um_arquivo_e_mede_em_centimetros(self) -> None:
        """Dentro do `.docx` o SVG é uma parte solta: leva declaração `<?xml?>`, e `18em` não tem
        corpo de texto a que se referir."""
        membros = _membros(_estudo_em_bytes())
        (nome,) = [n for n in membros if n.endswith(".svg")]
        texto = membros[nome].decode("utf-8")
        self.assertTrue(texto.startswith("<?xml "), texto[:40])
        raiz = ET.fromstring(texto)
        self.assertEqual(raiz.get("width"), f"{docx_saida.LARGURA_PADRAO_CM:g}cm")

    def test_o_desenho_descreve_a_posicao_no_descr(self) -> None:
        documento = ET.fromstring(_membros(_estudo_em_bytes())["word/document.xml"])
        propriedades = documento.find(f".//{{{docx_saida.NS_WP}}}docPr")
        assert propriedades is not None
        self.assertIn("FEN: ", propriedades.get("descr") or "")


class LegendaOpcionalTests(unittest.TestCase):
    def test_a_fen_nao_sai_sob_o_diagrama_por_padrao(self) -> None:
        pasta = pasta_temporaria(self)
        sem = docx_saida.exportar_estudo_docx(_estudo(), pasta / "sem.docx")
        com = docx_saida.exportar_estudo_docx(_estudo(), pasta / "com.docx", com_fen=True)
        estilos_sem = [e for e, _ in _paragrafos(sem.caminho.read_bytes())]
        paragrafos_com = _paragrafos(com.caminho.read_bytes())
        self.assertNotIn(docx_saida.LEGENDA, estilos_sem)
        self.assertTrue(any(e == docx_saida.LEGENDA and t.startswith("FEN: ") for e, t in paragrafos_com), paragrafos_com)


if __name__ == "__main__":
    unittest.main()
