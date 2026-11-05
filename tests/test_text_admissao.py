"""A admissão sem motor (S-702): cada critério reprova o que deve, e só isso.

Os casos vêm dos livros que ensinaram cada regra: o Dvoretsky desenha o tabuleiro em `Chess-Merida`
dentro do diagrama e não pode sair; o *Kemeri* é scan com camada invisível e um carimbo visível; o
*Gaprindashvili* e o AAGAARD têm produtor de OCR; o *Chess Evolution* desenha a imagem de fundo
**antes** do texto. Os PDFs do acervo não estão na CI, então a lógica se testa pelos trechos e a
extração por PDFs gerados aqui.
"""

from __future__ import annotations

import unittest

import fitz

from chess_diagram_ocr.text import admissao as ad

MERIDA = "Chess-Merida"


def fileira(x0: float, y: float, n: int, *, largura: float = 10.0, vao: float = 0.0, fonte: str = MERIDA) -> ad.Trecho:
    """`n` caracteres de 10 pt de altura, encostados (vão `vao`), com a base em `y`."""
    caixas = tuple((x0 + i * (largura + vao), y - 10, x0 + i * (largura + vao) + largura, y) for i in range(n))
    return ad.Trecho(fonte=fonte, texto="x" * n, bbox=(caixas[0][0], y - 10, caixas[-1][2], y), caixas=caixas)


PROSA = ad.Trecho(fonte="Times-Roman", texto="The king walks to the centre.", bbox=(50, 500, 300, 512))
DIAGRAMA = (60.0, 190.0, 260.0, 390.0)


class FileiraTests(unittest.TestCase):
    def test_oito_encostados_sao_uma_fileira_de_oito(self) -> None:
        self.assertEqual(8, ad.maior_fileira(fileira(0, 100, 8).caixas))

    def test_figurina_solta_e_um(self) -> None:
        self.assertEqual(1, ad.maior_fileira(fileira(0, 100, 1).caixas))

    def test_vao_de_meia_altura_parte_a_fileira(self) -> None:
        self.assertEqual(1, ad.maior_fileira(fileira(0, 100, 8, vao=6).caixas))
        self.assertEqual(8, ad.maior_fileira(fileira(0, 100, 8, vao=4).caixas))

    def test_linhas_diferentes_nao_se_somam(self) -> None:
        caixas = fileira(0, 100, 4).caixas + fileira(0, 130, 4).caixas
        self.assertEqual(4, ad.maior_fileira(caixas))


class DecidirTests(unittest.TestCase):
    def test_prosa_visivel_entra(self) -> None:
        self.assertTrue(ad.decidir([PROSA], []).admitida)

    def test_produtor_de_ocr_reprova_por_d(self) -> None:
        a = ad.decidir([PROSA], [], produtor="Adobe Acrobat 9.0 Paper Capture Plug-in")
        self.assertEqual(ad.PRODUTOR, a.criterio)

    def test_fonte_de_ocr_reprova_por_d(self) -> None:
        trecho = ad.Trecho(fonte="GlyphLessFont", texto="texto", bbox=(50, 500, 100, 512))
        self.assertEqual(ad.FONTE, ad.decidir([trecho], []).criterio)

    def test_livro_de_scan_reprova_todas_as_folhas(self) -> None:
        a = ad.decidir([PROSA], [], perfil=ad.PerfilDoLivro(com_texto=30, invisiveis=29))
        self.assertEqual(ad.LIVRO_DE_SCAN, a.criterio)

    def test_texto_invisivel_fora_do_diagrama_reprova_por_a(self) -> None:
        trecho = ad.Trecho(fonte="Times-Roman", texto="oculto", bbox=(50, 500, 100, 512), invisivel=True)
        self.assertEqual(ad.INVISIVEL, ad.decidir([PROSA, trecho], []).criterio)

    def test_imagem_desenhada_depois_do_texto_reprova_por_a(self) -> None:
        self.assertEqual(ad.COBERTO, ad.decidir([PROSA], [], imagem_cobre_texto=True).criterio)

    def test_lixo_de_figurina_reprova_por_c(self) -> None:
        trecho = ad.Trecho(fonte="Times-Roman", texto="16.l:l'.xe3", bbox=(50, 500, 100, 512))
        self.assertEqual(ad.LIXO, ad.decidir([PROSA, trecho], []).criterio)

    def test_uso_privado_em_fonte_de_texto_reprova_e_em_fonte_de_figurina_nao(self) -> None:
        texto = ad.Trecho(fonte="Times-Roman", texto="xe5", bbox=(50, 500, 100, 512))
        figurina = ad.Trecho(fonte="FigurineSymbolT1", texto="xe5", bbox=(50, 500, 100, 512))
        self.assertEqual(ad.LIXO, ad.decidir([PROSA, texto], []).criterio)
        self.assertTrue(ad.decidir([PROSA, figurina], []).admitida)

    def test_tabuleiro_em_fonte_dentro_do_diagrama_nao_reprova(self) -> None:
        """O Dvoretsky: 64 trechos em `Chess-Merida` por diagrama, e o livro inteiro é ouro."""
        tabuleiro = [fileira(70, 210 + 22 * i, 8, largura=22) for i in range(8)]
        a = ad.decidir([PROSA, *tabuleiro], [DIAGRAMA])
        self.assertTrue(a.admitida)
        self.assertEqual(8, a.fonte_de_diagrama_dentro)

    def test_sem_retangulo_o_mesmo_tabuleiro_reprova_por_b(self) -> None:
        """A falsificação do (b): apagados os retângulos, ele dispara -- ou a guarda é vácua."""
        tabuleiro = [fileira(70, 210 + 22 * i, 8, largura=22) for i in range(8)]
        a = ad.decidir([PROSA, *tabuleiro], [])
        self.assertEqual(ad.FILEIRA_FORA, a.criterio)
        self.assertEqual(8, a.maior_fileira_fora)

    def test_figurina_solta_em_fonte_de_diagrama_fora_do_diagrama_nao_reprova(self) -> None:
        figurina = fileira(120, 600, 1)
        self.assertTrue(ad.decidir([PROSA, figurina], [DIAGRAMA]).admitida)

    def test_cinco_encostados_ainda_nao_sao_fileira(self) -> None:
        self.assertTrue(ad.decidir([PROSA, fileira(120, 600, ad.FILEIRA - 1)], []).admitida)
        self.assertEqual(ad.FILEIRA_FORA, ad.decidir([PROSA, fileira(120, 600, ad.FILEIRA)], []).criterio)

    def test_folha_so_de_diagrama_e_sem_texto(self) -> None:
        self.assertEqual(ad.SEM_TEXTO, ad.decidir([fileira(70, 210, 8, largura=22)], [DIAGRAMA]).criterio)
        self.assertEqual(ad.SEM_TEXTO, ad.decidir([], []).criterio)


class PerfilTests(unittest.TestCase):
    def test_mais_da_metade_invisivel_e_scan(self) -> None:
        self.assertTrue(ad.PerfilDoLivro(30, 29).de_scan)
        self.assertTrue(ad.PerfilDoLivro(29, 15).de_scan)

    def test_metade_ou_menos_nao_e_scan(self) -> None:
        self.assertFalse(ad.PerfilDoLivro(30, 15).de_scan)
        self.assertFalse(ad.PerfilDoLivro(29, 0).de_scan)
        self.assertFalse(ad.PerfilDoLivro(0, 0).de_scan)

    def test_folhas_do_perfil_sao_trinta_igualmente_espacadas(self) -> None:
        folhas = ad.folhas_do_perfil(816)
        self.assertEqual(30, len(folhas))
        self.assertEqual((0, 815), (folhas[0], folhas[-1]))
        self.assertEqual(list(range(5)), ad.folhas_do_perfil(5))
        self.assertEqual([], ad.folhas_do_perfil(0))


def _pagina_com_texto(doc: fitz.Document, *, invisivel: bool = False) -> fitz.Page:
    pagina = doc.new_page(width=400, height=600)
    pagina.insert_text((50, 100), "The king walks to the centre.", fontsize=11, render_mode=3 if invisivel else 0)
    return pagina


def _imagem_cheia(pagina: fitz.Page) -> None:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 60), False)
    pix.clear_with(200)
    pagina.insert_image(pagina.rect, pixmap=pix)


class ExtracaoTests(unittest.TestCase):
    """O que se lê de um PDF de verdade, gerado aqui."""

    def test_texto_visivel_e_invisivel(self) -> None:
        doc = fitz.open()
        self.addCleanup(doc.close)
        visivel = ad.trechos_da_folha(_pagina_com_texto(doc))
        invisivel = ad.trechos_da_folha(_pagina_com_texto(doc, invisivel=True))
        self.assertTrue(visivel and not any(t.invisivel for t in visivel))
        self.assertTrue(invisivel and all(t.invisivel for t in invisivel))
        self.assertEqual((True, True), ad.tem_texto_invisivel(doc[1]))
        self.assertEqual((False, False), ad.tem_texto_invisivel(doc.new_page()))

    def test_imagem_de_fundo_antes_do_texto_nao_cobre_e_depois_cobre(self) -> None:
        doc = fitz.open()
        self.addCleanup(doc.close)
        primeira = doc.new_page(width=400, height=600)
        _imagem_cheia(primeira)
        primeira.insert_text((50, 100), "Solution 12", fontsize=11)
        _imagem_cheia(_pagina_com_texto(doc))
        fundo, carimbo = doc[0], doc[1]  # a página nova invalida o objeto da anterior
        self.assertFalse(ad.imagem_cobre_texto(fundo))
        self.assertTrue(ad.imagem_cobre_texto(carimbo))
        self.assertTrue(ad.admitir_folha(fundo, []).admitida)
        self.assertEqual(ad.COBERTO, ad.admitir_folha(carimbo, []).criterio)

    def test_livro_de_scan_pelo_perfil(self) -> None:
        scan, digital = fitz.open(), fitz.open()
        self.addCleanup(scan.close)
        self.addCleanup(digital.close)
        for _ in range(40):
            _pagina_com_texto(scan, invisivel=True)
            _pagina_com_texto(digital)
        self.assertTrue(ad.perfil_do_livro(scan).de_scan)
        self.assertFalse(ad.perfil_do_livro(digital).de_scan)
        self.assertEqual(ad.LIVRO_DE_SCAN, ad.admitir_folha(scan[3], [], perfil=ad.perfil_do_livro(scan)).criterio)

    def test_produtor_vem_dos_metadados(self) -> None:
        doc = fitz.open()
        self.addCleanup(doc.close)
        _pagina_com_texto(doc)
        doc.set_metadata({"producer": "ABBYY FineReader 15"})
        self.assertEqual(ad.PRODUTOR, ad.admitir_folha(doc[0], [], produtor=ad.produtor_de(doc)).criterio)


class AlternativasTests(unittest.TestCase):
    """Cada alternativa das listas reprova por si: cada caso casa **uma** alternativa só, e a que some do
    regex faz o caso dela falhar."""

    def test_cada_produtor_de_ocr(self) -> None:
        for produtor in ("Adobe Acrobat 9.0 Paper Capture Plug-in", "Adobe Acrobat Pro 11 Image Conversion Plug-in",
                         "FineReader Engine 12", "OmniPage CSDK 21", "Omniscan 3", "Google Books",
                         "ABBYY Recognition Server"):
            with self.subTest(produtor=produtor):
                self.assertEqual(ad.PRODUTOR, ad.decidir([PROSA], [], produtor=produtor).criterio)
        for produtor in ("Adobe InDesign 16.0 (Windows)", "calibre 3.48.0", "pdfTeX-1.40.21", "PDFill PDF Editor 15.0"):
            with self.subTest(produtor=produtor):
                self.assertTrue(ad.decidir([PROSA], [], produtor=produtor).admitida)

    def test_cada_fonte_de_ocr(self) -> None:
        for fonte in ("GlyphLessFont", "HiddenHorzOCR", "Fd12", "fd3"):
            with self.subTest(fonte=fonte):
                trecho = ad.Trecho(fonte=fonte, texto="texto", bbox=(50, 500, 100, 512))
                self.assertEqual(ad.FONTE, ad.decidir([trecho], []).criterio)
        for fonte in ("Fdx", "Fedra", "Times-Roman"):
            with self.subTest(fonte=fonte):
                self.assertTrue(ad.decidir([ad.Trecho(fonte=fonte, texto="texto", bbox=(50, 500, 100, 512))], []).admitida)

    def test_cada_lixo_de_figurina(self) -> None:
        for lixo in ("16.l:l'.xe3", "'ii'xa4", "21.tg5"):
            with self.subTest(lixo=lixo):
                trecho = ad.Trecho(fonte="Times-Roman", texto=lixo, bbox=(50, 500, 100, 512))
                self.assertEqual(ad.LIXO, ad.decidir([PROSA, trecho], []).criterio)

    def test_cada_fonte_de_diagrama_faz_fileira(self) -> None:
        for fonte in ("Chess-Merida", "DiagramTTFritz", "ChessAlpha2", "Leipzig", "ChessKingdom", "Chess-Berlin",
                      "ChessBerlin", "UsualChess", "Linares"):
            with self.subTest(fonte=fonte):
                self.assertEqual(ad.FILEIRA_FORA, ad.decidir([PROSA, fileira(120, 600, 8, fonte=fonte)], []).criterio)
        self.assertTrue(ad.decidir([PROSA, fileira(120, 600, 8, fonte="Times-Roman")], []).admitida)

    def test_uso_privado_em_cada_fonte_de_figurina_e_figurina(self) -> None:
        for fonte in ("FigurineSymbolT1", "Merida", "SkakNew", "ChessText", "Alpha", "Leipzig", "Segoe UI Symbol",
                      "MS Gothic"):
            with self.subTest(fonte=fonte):
                trecho = ad.Trecho(fonte=fonte, texto="\ue051xe5", bbox=(50, 500, 100, 512))
                self.assertTrue(ad.decidir([PROSA, trecho], []).admitida)

    def test_toda_a_faixa_de_uso_privado_em_fonte_de_texto(self) -> None:
        """Os casos reais: U+E300 a U+E305 numa fonte de editora, U+F0B1 no ± do Chess Evolution."""
        for caractere in ("\ue000", "\ue300", "\uf0b1", "\uf8ff"):
            with self.subTest(codigo=f"U+{ord(caractere):04X}"):
                trecho = ad.Trecho(fonte="Times-Roman", texto=f"19.a4{caractere}", bbox=(50, 500, 100, 512))
                self.assertEqual(ad.LIXO, ad.decidir([PROSA, trecho], []).criterio)
        fora = ad.Trecho(fonte="Times-Roman", texto="\uf900", bbox=(50, 500, 100, 512))  # logo depois da faixa
        self.assertTrue(ad.decidir([PROSA, fora], []).admitida)

    def test_o_ponto_de_tg_e_literal(self) -> None:
        for palavra in ("Stuttgart", "outgoing"):
            with self.subTest(palavra=palavra):
                trecho = ad.Trecho(fonte="Times-Roman", texto=palavra, bbox=(50, 500, 100, 512))
                self.assertTrue(ad.decidir([PROSA, trecho], []).admitida)

    def test_trecho_so_de_espaco_nao_conta_como_texto(self) -> None:
        branco = ad.Trecho(fonte="Times-Roman", texto="   ", bbox=(50, 500, 100, 512))
        self.assertEqual(ad.SEM_TEXTO, ad.decidir([branco], []).criterio)

    def test_a_fileira_e_de_seis(self) -> None:
        self.assertEqual(6, ad.FILEIRA)
        self.assertTrue(ad.decidir([PROSA, fileira(120, 600, 5)], []).admitida)
        self.assertEqual(ad.FILEIRA_FORA, ad.decidir([PROSA, fileira(120, 600, 6)], []).criterio)

    def test_a_linha_de_base_tolera_um_quarto_da_altura(self) -> None:
        """Oito caracteres de 10 pt, a base alternando: 2 pt cabe em um quarto (mesma linha, fileira de 8);
        3 e 6 pt não cabem (duas linhas de 4 com vão de uma letra, fileira de 1)."""
        def alternando(desvio: float) -> list[ad.Retangulo]:
            return [(10.0 * i, 90 + desvio * (i % 2), 10.0 * i + 10, 100 + desvio * (i % 2)) for i in range(8)]

        self.assertEqual(8, ad.maior_fileira(alternando(2)))
        self.assertEqual(1, ad.maior_fileira(alternando(3)))  # passa de um quarto (2,5), não de um terço
        self.assertEqual(1, ad.maior_fileira(alternando(6)))

    def test_texto_invisivel_dentro_do_diagrama_nao_reprova(self) -> None:
        """Desvio declarado da spec: o que está dentro do retângulo sai da referência de qualquer jeito."""
        oculto = ad.Trecho(fonte="Times-Roman", texto="FEN oculta", bbox=(100, 250, 200, 262), invisivel=True)
        self.assertTrue(ad.decidir([PROSA, oculto], [DIAGRAMA]).admitida)
        self.assertEqual(ad.INVISIVEL, ad.decidir([PROSA, oculto], []).criterio)


def _caixa_fora(lado: str, largura: float, d: float) -> ad.Retangulo:
    """Uma caixa de 2 x 2 com o centro a `d` pt de fora do lado `lado` de um tabuleiro quadrado em (0, 0)."""
    meio = largura / 2
    centro = {"direita": (largura + d, meio), "esquerda": (-d, meio), "baixo": (meio, largura + d), "cima": (meio, -d)}
    cx, cy = centro[lado]
    return (cx - 1, cy - 1, cx + 1, cy + 1)


class FolgaTests(unittest.TestCase):
    RETANGULO = [(0.0, 0.0, 80.0, 80.0)]
    """Um tabuleiro de 80 pt: a folga é um oitavo da largura, 10 pt, de cada lado."""

    LADOS = {  # a caixa de um trecho de 4 x 4 com o centro a `d` pt de fora de cada lado
        "direita": lambda d: (78 + d, 38, 82 + d, 42),
        "esquerda": lambda d: (-2 - d, 38, 2 - d, 42),
        "baixo": lambda d: (38, 78 + d, 42, 82 + d),
        "cima": lambda d: (38, -2 - d, 42, 2 - d),
    }

    def test_o_retangulo_cresce_uma_casa_dos_quatro_lados(self) -> None:
        """O rótulo da coordenada e a moldura encostados no tabuleiro ainda são do diagrama."""
        for lado, caixa in self.LADOS.items():
            with self.subTest(lado=lado):
                self.assertTrue(ad.dentro_de_algum(caixa(6), self.RETANGULO))
                self.assertFalse(ad.dentro_de_algum(caixa(14), self.RETANGULO))

    def test_a_folga_e_um_oitavo_da_largura_rente_a_fronteira(self) -> None:
        """A meio ponto da fronteira, de cada lado e em dois tamanhos de tabuleiro: 80 pt (folga 10) e
        160 pt (folga 20). Um sexto ou um décimo da largura erraria pelo menos um destes casos."""
        self.assertEqual(8, round(80 / ad.folga_de((0.0, 0.0, 80.0, 80.0))))
        for largura in (80.0, 160.0):
            retangulo = [(0.0, 0.0, largura, largura)]
            folga = largura / 8
            for lado in ("direita", "esquerda", "baixo", "cima"):
                with self.subTest(largura=largura, lado=lado):
                    self.assertTrue(ad.dentro_de_algum(_caixa_fora(lado, largura, folga - 0.5), retangulo))
                    self.assertFalse(ad.dentro_de_algum(_caixa_fora(lado, largura, folga + 0.5), retangulo))

    def test_a_folga_e_da_largura_de_cada_retangulo(self) -> None:
        """Num retângulo de 80 x 120, a casa é 10 pt também na vertical (a largura, não a altura); numa
        folha com tabuleiros de 80 e de 160 pt, cada um cresce a sua casa, e não a do outro."""
        alto = [(0.0, 0.0, 80.0, 120.0)]
        self.assertTrue(ad.dentro_de_algum((39, 128.5, 41, 130.5), alto))  # 9,5 abaixo
        self.assertFalse(ad.dentro_de_algum((39, 129.5, 41, 131.5), alto))  # 10,5 abaixo
        largo = [(0.0, 0.0, 120.0, 80.0)]  # a casa é 15 pt: a largura, e não a menor dimensão
        self.assertTrue(ad.dentro_de_algum((59, 93.5, 61, 95.5), largo))  # 14,5 abaixo
        self.assertFalse(ad.dentro_de_algum((59, 94.5, 61, 96.5), largo))  # 15,5 abaixo
        dois = [(0.0, 0.0, 80.0, 80.0), (200.0, 0.0, 360.0, 160.0)]
        self.assertFalse(ad.dentro_de_algum((89.5, 39, 91.5, 41), dois))  # 10,5 à direita do pequeno
        self.assertTrue(ad.dentro_de_algum((378.5, 79, 380.5, 81), dois))  # 19,5 à direita do grande
        self.assertFalse(ad.dentro_de_algum((379.5, 79, 381.5, 81), dois))  # 20,5 à direita do grande

    def test_cada_um_dos_diagramas_da_folha(self) -> None:
        """O Dvoretsky tem dois diagramas por folha: o tabuleiro em fonte e a moldura do segundo e do
        terceiro também são de diagrama. Sem os retângulos, a mesma folha reprova por (b)."""
        retangulos = [(0.0, 0.0, 80.0, 80.0), (200.0, 300.0, 280.0, 380.0), (0.0, 500.0, 80.0, 580.0)]
        for x0, y0, x1, _ in retangulos:
            with self.subTest(retangulo=(x0, y0)):
                tabuleiro = [fileira(x0 + 2, y0 + 12 + 9 * i, 8, largura=9) for i in range(8)]
                moldura = ad.Trecho(fonte="", texto="\uf021\uf022", bbox=(x0 + 10, y0 - 7, x1 - 10, y0 - 5))
                self.assertTrue(ad.decidir([PROSA, *tabuleiro, moldura], retangulos).admitida)
                self.assertEqual(ad.FILEIRA_FORA, ad.decidir([PROSA, *tabuleiro], []).criterio)
        self.assertTrue(ad.dentro_de_algum((236, 336, 244, 344), retangulos))
        self.assertTrue(ad.dentro_de_algum((36, 536, 44, 544), retangulos))

    def test_a_moldura_em_uso_privado_na_folga_nao_reprova(self) -> None:
        """Um livro do teste desenha a moldura do tabuleiro numa fonte sem nome, em U+F021 a U+F02F, nos
        quatro lados do diagrama: na folga, ela é do diagrama; um pouco mais longe, seria lixo (c)."""
        for lado, caixa in self.LADOS.items():
            with self.subTest(lado=lado):
                perto = ad.Trecho(fonte="", texto="\uf021\uf022", bbox=caixa(6))
                longe = ad.Trecho(fonte="", texto="\uf021\uf022", bbox=caixa(14))
                self.assertTrue(ad.decidir([PROSA, perto], self.RETANGULO).admitida)
                self.assertEqual(ad.LIXO, ad.decidir([PROSA, longe], self.RETANGULO).criterio)


class _PaginaFalsa:
    """O mínimo de `fitz.Page` que a extração lê, para os campos que um PDF gerado não produz."""

    class _Ret:
        width, height = 400.0, 600.0

    rect = _Ret()

    def __init__(self, traco: dict) -> None:
        self._traco = traco

    def get_texttrace(self) -> list[dict]:
        return [self._traco]

    def get_bboxlog(self) -> list:
        return []


def _traco(**kw: object) -> dict:
    chars = [(ord(c), 0, (50 + 6 * i, 512), (50 + 6 * i, 500, 56 + 6 * i, 512)) for i, c in enumerate("oculto")]
    return {"font": "Times-Roman", "chars": chars, "bbox": (50, 500, 86, 512), "type": 0, "opacity": 1.0, **kw}


class InvisivelTests(unittest.TestCase):
    def test_opacidade_zero_e_invisivel(self) -> None:
        self.assertFalse(ad.trechos_da_folha(_PaginaFalsa(_traco()))[0].invisivel)
        self.assertTrue(ad.trechos_da_folha(_PaginaFalsa(_traco(opacity=0)))[0].invisivel)
        self.assertEqual(ad.INVISIVEL, ad.admitir_folha(_PaginaFalsa(_traco(opacity=0)), []).criterio)

    def test_modo_tres_e_invisivel(self) -> None:
        self.assertEqual(ad.INVISIVEL, ad.admitir_folha(_PaginaFalsa(_traco(type=3)), []).criterio)


class ImagemCheiaTests(unittest.TestCase):
    def test_so_imagem_de_mais_de_sessenta_por_cento_cobre(self) -> None:
        self.assertEqual(0.6, ad.FRACAO_DE_IMAGEM_CHEIA)
        doc = fitz.open()
        self.addCleanup(doc.close)
        for altura in (300, 420):  # 50% e 70% de uma folha de 400 x 600
            pagina = _pagina_com_texto(doc)
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 30), False)
            pix.clear_with(200)
            pagina.insert_image(fitz.Rect(0, 0, 400, altura), pixmap=pix, keep_proportion=False)
        self.assertFalse(ad.imagem_cobre_texto(doc[0]))
        self.assertTrue(ad.imagem_cobre_texto(doc[1]))


if __name__ == "__main__":
    unittest.main()
