"""OCR da faixa de legenda (S-43).

O teste que carrega o item é `test_legenda_por_ocr_produz_o_mesmo_contexto_da_camada`: a
mesma legenda, lida pelos dois caminhos, tem de sair no mesmo `DiagramContext`. É o que
prova que o OCR entra pela porta da S-16 -- agrupamento por coluna, `dominant_placement`,
tiers, filtro de prosa -- e não por uma paralela que reimplementaria tudo com outros bugs.
"""

from __future__ import annotations

import unittest

import chess
import fitz
import numpy as np
from test_ocr import FakeRecognizer

from chess_diagram_ocr.ocr import TextBox
from chess_diagram_ocr.ocr_caption import (
    CaptionReader,
    build_caption_reader,
    caption_reader_from_settings,
)
from chess_diagram_ocr.pdf_text import (
    NearbyLine,
    TextLine,
    context_from_lines,
    contexts_for_page,
    page_scope_declaration,
)
from chess_diagram_ocr.settings import OcrSettings

PAGE_WIDTH, PAGE_HEIGHT = 595.0, 842.0

BBOX = (100.0, 300.0, 400.0, 600.0)
"""Um diagrama de 300×300 pt no meio da página. Com `radius_pt=60` a faixa lida vai de
(40, 240) a (460, 660) -- 420 pt de altura, dos quais o diagrama ocupa o miolo."""

ACIMA = (0.20, 0.02, 0.50, 0.10)
"""Retângulo relativo à faixa que cai **acima** do diagrama: y 248-282 pt, a 18 pt dele."""

ABAIXO = (0.20, 0.90, 0.50, 0.98)
"""O espelho: y 618-651 pt, também a 18 pt do diagrama."""


def blank_page() -> fitz.Document:
    """Página sem uma linha de texto -- os 7 livros do acervo que não têm camada."""
    doc = fitz.open()
    doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    return doc


def page_with(lines: list[tuple[str, float, float]]) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    for text, x, y in lines:
        page.insert_text((x, y), text, fontsize=11)
    return doc


class RelativeRecognizer(FakeRecognizer):
    """`FakeRecognizer` cujas caixas vêm em fração da imagem, resolvidas na leitura.

    Fração e não pixel porque o recorte é renderizado a 300 DPI a partir de um retângulo em
    pontos: fixar pixel no teste amarraria a asserção ao DPI, que é justamente o parâmetro
    que a S-43 pode querer mexer depois.
    """

    def read(self, image_rgb: np.ndarray, *, allowlist: str = "") -> list[TextBox]:
        relativas = super().read(image_rgb, allowlist=allowlist)
        altura, largura = image_rgb.shape[:2]
        return [
            TextBox(
                text=box.text,
                bbox=(
                    box.bbox[0] * largura,
                    box.bbox[1] * altura,
                    box.bbox[2] * largura,
                    box.bbox[3] * altura,
                ),
                confidence=box.confidence,
            )
            for box in relativas
        ]


def reader(*calls: list[tuple[str, tuple[float, float, float, float], float]]) -> CaptionReader:
    recognizer = RelativeRecognizer(
        *[[TextBox(text=t, bbox=r, confidence=c) for t, r, c in chamada] for chamada in calls]
    )
    return CaptionReader(recognizer)


class LinesAroundTests(unittest.TestCase):
    def test_caixa_do_motor_volta_em_pontos_do_pdf(self) -> None:
        doc = blank_page()
        try:
            lines = reader([("Steinitz - Bird", ACIMA, 0.91)]).lines_around(doc[0], BBOX)
        finally:
            doc.close()

        self.assertEqual(len(lines), 1)
        x0, y0, x1, y1 = lines[0].bbox
        # A faixa vai de (40, 240) a (460, 660): 420 x 420 pt. Tolerancia de meio ponto
        # porque `get_pixmap` alinha o clip a pixel inteiro.
        self.assertAlmostEqual(x0, 40.0 + 0.20 * 420.0, delta=0.5)
        self.assertAlmostEqual(y0, 240.0 + 0.02 * 420.0, delta=0.5)
        self.assertAlmostEqual(x1, 40.0 + 0.50 * 420.0, delta=0.5)
        self.assertAlmostEqual(y1, 240.0 + 0.10 * 420.0, delta=0.5)

    def test_a_linha_sai_marcada_como_ocr_e_com_a_confianca_do_motor(self) -> None:
        doc = blank_page()
        try:
            lines = reader([("White to move", ACIMA, 0.62)]).lines_around(doc[0], BBOX)
        finally:
            doc.close()

        self.assertEqual(lines[0].origin, "ocr")
        self.assertAlmostEqual(lines[0].confidence, 0.62)

    def test_o_diagrama_e_apagado_antes_de_o_motor_ver_a_imagem(self) -> None:
        """A armadilha nº 3 da S-16 resolvida por construção: o tabuleiro não vira texto."""
        doc = blank_page()
        page = doc[0]
        # Um retangulo preto onde o diagrama esta -- a coisa mais parecida com um bloco de
        # texto que se pode desenhar, e o que um tabuleiro de verdade produz.
        page.draw_rect(fitz.Rect(*BBOX), color=(0, 0, 0), fill=(0, 0, 0))

        leitor = reader([])
        try:
            leitor.lines_around(page, BBOX)
        finally:
            doc.close()

        recebida = leitor._recognizer.seen[0]  # type: ignore[attr-defined]
        altura, largura = recebida.shape[:2]
        centro = recebida[altura // 2, largura // 2]
        self.assertTrue((centro == 255).all(), f"centro da faixa deveria estar apagado, veio {centro}")

    def test_faixa_degenerada_nao_chega_ao_motor(self) -> None:
        doc = blank_page()
        leitor = reader([("qualquer", ACIMA, 0.9)])
        try:
            fora = (-500.0, -500.0, -499.0, -499.0)
            self.assertEqual(leitor.lines_around(doc[0], fora), [])
        finally:
            doc.close()
        self.assertEqual(leitor._recognizer.seen, [])  # type: ignore[attr-defined]

    def test_falha_do_motor_no_meio_da_varredura_nao_derruba_a_pagina(self) -> None:
        class Quebrado:
            @property
            def name(self) -> str:
                return "quebrado"

            def read(self, image_rgb: np.ndarray, *, allowlist: str = "") -> list[TextBox]:
                raise RuntimeError("onnxruntime session collapsed")

        doc = blank_page()
        try:
            with self.assertLogs("chess_diagram_ocr.ocr_caption", level="WARNING"):
                self.assertEqual(CaptionReader(Quebrado()).lines_around(doc[0], BBOX), [])
        finally:
            doc.close()


class GroupingTests(unittest.TestCase):
    def test_legenda_de_tres_linhas_e_um_grupo_so(self) -> None:
        """O `Schiller`: `5` / `Morphy-De Riviere` / `Paris, 1858`.

        A S-16 mediu por que isto importa -- linha a linha, o número da legenda de baixo cai
        mais perto do diagrama de cima, e a página inteira sai deslocada de um exercício.
        """
        doc = blank_page()
        try:
            lines = reader(
                [
                    ("5", (0.20, 0.010, 0.24, 0.035), 0.95),
                    ("Morphy-De Riviere", (0.20, 0.040, 0.55, 0.065), 0.93),
                    ("Paris, 1858", (0.20, 0.070, 0.45, 0.095), 0.90),
                ]
            ).lines_around(doc[0], BBOX)
        finally:
            doc.close()

        self.assertEqual(len({line.group_id for line in lines}), 1)
        self.assertEqual({line.block_words for line in lines}, {5})

    def test_colunas_vizinhas_nao_viram_o_mesmo_grupo(self) -> None:
        """O `Karpov`: duas legendas na mesma altura, uma por coluna da página."""
        doc = blank_page()
        try:
            lines = reader(
                [
                    ("№79. Steinitz - Bird", (0.05, 0.02, 0.30, 0.05), 0.9),
                    ("№80. Steinitz - Mortimer", (0.55, 0.02, 0.95, 0.05), 0.9),
                ]
            ).lines_around(doc[0], BBOX)
        finally:
            doc.close()

        self.assertEqual(len({line.group_id for line in lines}), 2)


class ContextIntegrationTests(unittest.TestCase):
    """O item inteiro: as linhas do OCR entrando pela porta da S-16."""

    def test_legenda_por_ocr_produz_o_mesmo_contexto_da_camada(self) -> None:
        por_texto = page_with([("11: Brancas jogam", 124.0, 280.0)])
        por_ocr = blank_page()
        try:
            esperado = contexts_for_page(por_texto[0], [BBOX])[0]
            obtido = contexts_for_page(
                por_ocr[0],
                [BBOX],
                caption_reader=reader([("11: Brancas jogam", ACIMA, 0.88)]),
            )[0]
        finally:
            por_texto.close()
            por_ocr.close()

        self.assertEqual(obtido.side_to_move, esperado.side_to_move)
        self.assertEqual(obtido.exercise_number, esperado.exercise_number)
        self.assertEqual(obtido.caption, esperado.caption)
        # O que muda e so a procedencia, que e exatamente o que a S-43 acrescenta.
        self.assertEqual(esperado.side_to_move_origin, "text")
        self.assertEqual(obtido.side_to_move_origin, "ocr")
        self.assertAlmostEqual(obtido.side_to_move_confidence, 0.88)

    def test_legenda_abaixo_do_diagrama_tambem_e_lida(self) -> None:
        doc = blank_page()
        try:
            contexts = contexts_for_page(
                doc[0],
                [BBOX],
                caption_reader=reader([("31: Jogada das pretas **", ABAIXO, 0.85)]),
            )
        finally:
            doc.close()

        self.assertEqual(contexts[0].side_to_move, chess.BLACK)
        self.assertEqual(contexts[0].exercise_number, 31)

    def test_onde_a_camada_de_texto_respondeu_o_ocr_nao_roda(self) -> None:
        """A economia que a S-61 torna obrigatória, e a decisão por diagrama, não por livro."""
        doc = page_with([("11: Brancas jogam", 124.0, 280.0)])
        leitor = reader([("nunca deveria ser lido", ACIMA, 0.99)])
        try:
            contexts = contexts_for_page(doc[0], [BBOX], caption_reader=leitor)
        finally:
            doc.close()

        self.assertEqual(leitor._recognizer.seen, [])  # type: ignore[attr-defined]
        self.assertEqual(contexts[0].side_to_move_origin, "text")

    def test_a_decisao_e_por_diagrama_e_nao_por_livro(self) -> None:
        """Os 5 livros de OCR parcial: a camada responde por um diagrama e cala no outro.

        Decidir por livro deixaria metade das páginas do `Gaprindashvili` sem legenda, ou
        pagaria OCR na outra metade sem precisar. Aqui a mesma página tem as duas fontes, e
        cada diagrama sai com a procedência de quem de fato o respondeu.
        """
        doc = page_with([("11: Brancas jogam", 124.0, 280.0), ("comentário", 124.0, 290.0)])
        alto = (100.0, 300.0, 400.0, 450.0)
        baixo = (100.0, 470.0, 400.0, 620.0)
        try:
            contexts = contexts_for_page(
                doc[0],
                [alto, baixo],
                caption_reader=reader([("31: Jogada das pretas", (0.20, 0.02, 0.60, 0.08), 0.55)]),
            )
        finally:
            doc.close()

        self.assertEqual((contexts[0].side_to_move, contexts[0].side_to_move_origin), (chess.WHITE, "text"))
        self.assertEqual((contexts[1].side_to_move, contexts[1].side_to_move_origin), (chess.BLACK, "ocr"))

    def test_camada_de_texto_vence_o_ocr_no_mesmo_escalao(self) -> None:
        """O desempate, testado onde ele é alcançável -- e ele é raro por construção.

        `contexts_for_page` só roda o OCR onde a camada calou, então as duas fontes quase
        nunca disputam o mesmo escalão do mesmo diagrama: para isso, uma linha de OCR gerada
        pela vizinhança de um diagrama precisa cair também na de outro que já tinha texto. O
        desempate existe para esse caso, e é aqui -- em `context_from_lines`, que recebe o
        balde pronto -- que ele se exercita sem contorcer a geometria da página.
        """
        bucket = [
            NearbyLine(
                line=TextLine(text="11: Brancas jogam", bbox=(120.0, 270.0, 300.0, 285.0), block_words=3),
                distance=15.0,
                placement="above",
            ),
            NearbyLine(
                line=TextLine(
                    text="Pretas jogam",
                    bbox=(120.0, 250.0, 300.0, 265.0),
                    block_words=2,
                    group_id=9,
                    origin="ocr",
                    confidence=0.55,
                ),
                distance=35.0,
                placement="above",
            ),
        ]
        context = context_from_lines(bucket)

        self.assertEqual(context.side_to_move, chess.WHITE)
        self.assertEqual(context.side_to_move_origin, "text")
        self.assertEqual(context.side_to_move_confidence, 1.0)

    def test_duas_leituras_de_ocr_em_conflito_continuam_sem_resposta(self) -> None:
        """Sem camada de texto não há desempate, e inventar um seria pior que calar."""
        bucket = [
            NearbyLine(
                line=TextLine(text="Brancas jogam", bbox=(120.0, 270.0, 300.0, 285.0), block_words=2, origin="ocr"),
                distance=15.0,
                placement="above",
            ),
            NearbyLine(
                line=TextLine(
                    text="Pretas jogam",
                    bbox=(120.0, 250.0, 300.0, 265.0),
                    block_words=2,
                    group_id=9,
                    origin="ocr",
                ),
                distance=35.0,
                placement="above",
            ),
        ]
        context = context_from_lines(bucket)

        self.assertIsNone(context.side_to_move)
        self.assertIsNone(context.side_to_move_origin)


class PageScopeTests(unittest.TestCase):
    """`LAS BLANCAS JUEGAN PRIMERO`: a faixa que `MARGIN_BAND` jogava fora."""

    TOPO = (0.10, 0.20, 0.80, 0.70)
    """Dentro da faixa de margem renderizada -- 7% de 842 pt = 58,9 pt de altura."""

    def test_declaracao_de_escopo_na_camada_de_texto(self) -> None:
        doc = page_with([("2.1 White to Move #2", 150.0, 30.0)])
        try:
            scope = page_scope_declaration(doc[0])
        finally:
            doc.close()

        self.assertIsNotNone(scope)
        assert scope is not None
        self.assertEqual(scope.color, chess.WHITE)
        self.assertEqual(scope.origin, "text-page-scope")

    def test_declaracao_de_escopo_por_ocr(self) -> None:
        doc = blank_page()
        try:
            scope = page_scope_declaration(
                doc[0],
                caption_reader=reader([("LAS BLANCAS JUEGAN PRIMERO", self.TOPO, 0.83)]),
            )
        finally:
            doc.close()

        self.assertIsNotNone(scope)
        assert scope is not None
        self.assertEqual(scope.color, chess.WHITE)
        self.assertEqual(scope.origin, "ocr-page-scope")
        self.assertAlmostEqual(scope.confidence, 0.83)

    def test_numero_de_pagina_na_margem_nao_e_declaracao(self) -> None:
        doc = blank_page()
        try:
            self.assertIsNone(
                page_scope_declaration(doc[0], caption_reader=reader([("142", self.TOPO, 0.99)]))
            )
        finally:
            doc.close()

    def test_topo_e_rodape_declarando_lados_opostos_nao_decidem(self) -> None:
        doc = page_with([("White to Move", 150.0, 30.0), ("Black to Move", 150.0, 820.0)])
        try:
            self.assertIsNone(page_scope_declaration(doc[0]))
        finally:
            doc.close()

    def test_escopo_de_pagina_preenche_o_diagrama_que_a_legenda_calou(self) -> None:
        doc = page_with([("LAS BLANCAS JUEGAN PRIMERO", 120.0, 30.0)])
        try:
            contexts = contexts_for_page(doc[0], [BBOX])
        finally:
            doc.close()

        self.assertEqual(contexts[0].side_to_move, chess.WHITE)
        self.assertEqual(contexts[0].side_to_move_origin, "text-page-scope")

    def test_a_legenda_do_diagrama_tem_precedencia_sobre_o_escopo(self) -> None:
        """O cuidado do item: um livro que declara nos dois lugares não muda de resposta."""
        doc = page_with(
            [("LAS BLANCAS JUEGAN PRIMERO", 120.0, 30.0), ("31: Jogada das pretas", 124.0, 280.0)]
        )
        try:
            contexts = contexts_for_page(doc[0], [BBOX])
        finally:
            doc.close()

        self.assertEqual(contexts[0].side_to_move, chess.BLACK)
        self.assertEqual(contexts[0].side_to_move_origin, "text")


class BuildTests(unittest.TestCase):
    def test_sem_motor_nao_ha_leitor(self) -> None:
        self.assertIsNone(build_caption_reader(None))

    def test_configuracao_desligada_nao_produz_leitor(self) -> None:
        """O caminho padrão do projeto, e o mais curto de escrever."""
        self.assertIsNone(caption_reader_from_settings(OcrSettings()))

    def test_com_motor_ha_leitor(self) -> None:
        leitor = build_caption_reader(FakeRecognizer())
        self.assertIsNotNone(leitor)
        assert leitor is not None
        self.assertEqual(leitor.name, "fake")


if __name__ == "__main__":
    unittest.main()
