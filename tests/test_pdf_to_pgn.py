from __future__ import annotations

import tempfile
import threading
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import chess
import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.detection import DiagramCandidate
from chess_diagram_ocr.inference import OrientedPrediction, prediction_from_probs
from chess_diagram_ocr.pdf_text import DiagramContext
from chess_diagram_ocr.pdf_to_pgn import (
    DiagramPosition,
    build_pgn_text,
    classify_position,
    mark_duplicates,
    partition_positions,
    save_pdf_positions_to_pgn,
    scan_pdf_positions,
    write_gated_pgn,
)
from chess_diagram_ocr.semantics import SideToMove

EMPTY_BOARD = "8/8/8/8/8/8/8/8"
KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"
KINGS_D1_D3 = "8/8/8/8/8/3k4/8/3K4"

# Pretas em xeque. O export assume "brancas jogam", então a FEN completa fica ilegal --
# mas o tabuleiro está perfeito: é o palpite de lado a jogar que está errado (S-17).
BLACK_IN_CHECK = "4k3/8/8/8/8/8/8/4KR2"


def oriented_for(fen: str, confidence: float, *, rotation: int = 0, ambiguous: bool = False):
    """`OrientedPrediction` real, como `predict_with_orientation` devolveria.

    Objeto de verdade em vez de duplo: se a S-13 mudar de forma, estes testes quebram em vez
    de continuarem passando sobre um contrato que nao existe mais.
    """
    return OrientedPrediction(
        prediction=prediction_for(fen, confidence),
        rotation=rotation,
        margin=0.0 if ambiguous else 0.5,
        ambiguous=ambiguous,
        reason="teste",
    )


def candidate_for(board_rgb: np.ndarray, index: int = 0) -> DiagramCandidate:
    """`DiagramCandidate` real, como o detector híbrido da S-12 devolveria."""
    top = 100.0 * index
    return DiagramCandidate(
        board_rgb=board_rgb,
        bbox_pdf=(10.0, top, 90.0, top + 80.0),
        source="embedded",
        detector_score=0.9,
        native_size=(320, 320),
    )


def prediction_for(fen: str, confidence: float):
    """`BoardPrediction` real para uma FEN, com todas as casas na mesma confiança.

    Usar o objeto de verdade em vez de um duplo garante que a S-10 continue conectada
    ponta a ponta: se `predict_board` mudar de forma, estes testes quebram.
    """
    return prediction_from_probs(probs_for_fen(fen, confidence))


class PdfToPgnTests(unittest.TestCase):
    def test_build_pgn_text_creates_one_game_per_position(self) -> None:
        positions = [
            DiagramPosition(page_index=0, diagram_index=1, fen=EMPTY_BOARD, confidence=0.91),
            DiagramPosition(page_index=2, diagram_index=2, fen=KINGS_ONLY, confidence=0.83),
        ]

        payload = build_pgn_text(positions, source_name="book.pdf")

        self.assertIn('[SourcePDF "book.pdf"]', payload)
        self.assertIn('[Page "1"]', payload)
        self.assertIn('[Diagram "1"]', payload)
        self.assertIn('[OCRConfidence "0.910"]', payload)
        self.assertIn('[Round "3.2"]', payload)
        self.assertEqual(payload.count("[SetUp \"1\"]"), 2)
        self.assertEqual(payload.count("[Result \"*\"]"), 2)

    def test_headers_record_the_reading_order(self) -> None:
        """S-14: `[Diagram "2"]` só é conferível se o PGN disser como a página foi numerada."""
        positions = [DiagramPosition(page_index=0, diagram_index=2, fen=KINGS_ONLY, confidence=0.9)]

        self.assertIn('[ReadingOrder "column"]', build_pgn_text(positions, source_name="book.pdf"))
        self.assertIn(
            '[ReadingOrder "row"]',
            build_pgn_text(positions, source_name="book.pdf", reading_order="row"),
        )

    def test_headers_omit_unmeasured_fields(self) -> None:
        """Posição montada à mão não afirma legalidade nem confiança mínima."""
        payload = build_pgn_text(
            [DiagramPosition(page_index=0, diagram_index=1, fen=KINGS_ONLY, confidence=0.91)],
            source_name="book.pdf",
        )

        self.assertNotIn("OCRMinConfidence", payload)
        self.assertNotIn("OCRLegality", payload)

    def test_headers_carry_min_confidence_and_legality(self) -> None:
        positions = [
            DiagramPosition(
                page_index=0,
                diagram_index=1,
                fen=EMPTY_BOARD,
                confidence=0.97,
                min_confidence=0.42,
                is_legal=False,
                is_fatal=True,
                problems=("tabuleiro vazio",),
            ),
            DiagramPosition(
                page_index=0,
                diagram_index=2,
                fen=KINGS_ONLY,
                confidence=0.99,
                min_confidence=0.95,
                is_legal=True,
                is_fatal=False,
            ),
        ]

        payload = build_pgn_text(positions, source_name="book.pdf")

        self.assertIn('[OCRMinConfidence "0.420"]', payload)
        self.assertIn('[OCRLegality "ilegal"]', payload)
        self.assertIn('[OCRProblems "tabuleiro vazio"]', payload)
        self.assertIn('[OCRMinConfidence "0.950"]', payload)
        self.assertIn('[OCRLegality "legal"]', payload)
        # Posicao legal nao carrega lista de problemas vazia.
        self.assertEqual(payload.count("OCRProblems"), 1)

    def test_side_to_move_case_is_not_labelled_illegal(self) -> None:
        """Tabuleiro bom, palpite de lado a jogar ruim: o PGN precisa dizer qual dos dois."""
        payload = build_pgn_text(
            [
                DiagramPosition(
                    page_index=0,
                    diagram_index=1,
                    fen=BLACK_IN_CHECK,
                    confidence=0.99,
                    min_confidence=0.98,
                    is_legal=False,
                    is_fatal=False,
                    problems=("o lado que não joga está em xeque",),
                )
            ],
            source_name="book.pdf",
        )

        self.assertIn('[OCRLegality "lado-a-jogar"]', payload)
        self.assertNotIn('"ilegal"', payload)

    def test_headers_record_the_orientation_used(self) -> None:
        """S-13: sem isso não há como saber depois se a leitura foi feita de pé ou girada."""
        for rotation in (0, 180):
            with self.subTest(rotation=rotation):
                payload = build_pgn_text(
                    [
                        DiagramPosition(
                            page_index=0,
                            diagram_index=1,
                            fen=KINGS_ONLY,
                            confidence=0.99,
                            rotation=rotation,
                        )
                    ],
                    source_name="book.pdf",
                )

                self.assertIn(f'[OCRRotation "{rotation}"]', payload)

    @patch("chess_diagram_ocr.pdf_to_pgn._page_contexts")
    @patch("chess_diagram_ocr.pdf_to_pgn.predict_with_orientation")
    @patch("chess_diagram_ocr.pdf_to_pgn._detect_page_diagrams")
    @patch("chess_diagram_ocr.pdf_to_pgn._render_pdf_page")
    @patch("chess_diagram_ocr.pdf_to_pgn.load_model")
    @patch("chess_diagram_ocr.pdf_to_pgn._get_pdf_page_count")
    def test_o_leitor_de_legenda_chega_ate_a_leitura_de_contexto(
        self,
        mock_get_pdf_page_count,
        mock_load_model,
        mock_render_pdf_page,
        mock_detect,
        mock_predict,
        mock_contexts,
    ) -> None:
        """A S-43 só vale se o leitor atravessar as quatro camadas até `contexts_for_page`.

        É uma passagem de parâmetro, e é exatamente o tipo de fio que se rompe em silêncio:
        o pipeline continua funcionando sem OCR, e ninguém nota que ele parou de chegar.
        """
        mock_get_pdf_page_count.return_value = 1
        mock_load_model.return_value = ("model", "cpu")
        mock_render_pdf_page.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        mock_detect.return_value = [candidate_for(np.zeros((800, 800, 3), dtype=np.uint8), 0)]
        mock_contexts.return_value = [DiagramContext()]
        mock_predict.return_value = oriented_for(KINGS_ONLY, 0.9)

        sentinela = object()
        scan_pdf_positions(Path("sample.pdf"), caption_reader=sentinela)

        self.assertIs(mock_contexts.call_args.args[3], sentinela)

    @patch("chess_diagram_ocr.pdf_to_pgn._page_contexts")
    @patch("chess_diagram_ocr.pdf_to_pgn.predict_with_orientation")
    @patch("chess_diagram_ocr.pdf_to_pgn._detect_page_diagrams")
    @patch("chess_diagram_ocr.pdf_to_pgn._render_pdf_page")
    @patch("chess_diagram_ocr.pdf_to_pgn.load_model")
    @patch("chess_diagram_ocr.pdf_to_pgn._get_pdf_page_count")
    def test_scan_pdf_positions_walks_all_pages(
        self,
        mock_get_pdf_page_count,
        mock_load_model,
        mock_render_pdf_page,
        mock_detect,
        mock_predict,
        mock_contexts,
    ) -> None:
        mock_get_pdf_page_count.return_value = 3
        mock_load_model.return_value = ("model", "cpu")
        mock_render_pdf_page.side_effect = [
            np.zeros((10, 10, 3), dtype=np.uint8),
            np.zeros((10, 10, 3), dtype=np.uint8),
            np.zeros((10, 10, 3), dtype=np.uint8),
        ]
        board_rgb = np.zeros((800, 800, 3), dtype=np.uint8)
        mock_detect.side_effect = [
            [candidate_for(board_rgb, 0), candidate_for(board_rgb, 1)],
            [],
            [candidate_for(board_rgb, 0)],
        ]
        mock_contexts.side_effect = [[DiagramContext(), DiagramContext()], [], [DiagramContext()]]
        mock_predict.side_effect = [
            oriented_for(EMPTY_BOARD, 0.90),
            oriented_for(KINGS_ONLY, 0.80, rotation=180),
            oriented_for(KINGS_D1_D3, 0.70),
        ]

        positions = scan_pdf_positions(Path("sample.pdf"))

        self.assertEqual(
            [(p.page_index, p.diagram_index, p.fen) for p in positions],
            [(0, 1, EMPTY_BOARD), (0, 2, KINGS_ONLY), (2, 1, KINGS_D1_D3)],
        )
        for position, expected_confidence in zip(positions, (0.90, 0.80, 0.70), strict=True):
            self.assertAlmostEqual(position.confidence, expected_confidence, places=6)
            # Todas as casas com a mesma confianca: minimo e media coincidem.
            self.assertAlmostEqual(position.min_confidence, expected_confidence, places=6)

        # A legalidade acompanha a posicao, e nao um valor fixo: tabuleiro vazio e ilegal.
        self.assertEqual([p.is_legal for p in positions], [False, True, True])
        # E `is_fatal` chega junto: sem ele o gate nao distingue erro de leitura de palpite
        # errado de lado a jogar.
        self.assertEqual([p.is_fatal for p in positions], [True, False, False])
        self.assertIn("tabuleiro vazio", positions[0].problems)
        self.assertEqual(positions[1].problems, ())

        self.assertEqual(mock_render_pdf_page.call_count, 3)
        self.assertEqual(mock_detect.call_count, 3)
        self.assertTrue(all(call.kwargs.get("reading_order") == "column" for call in mock_detect.call_args_list))
        self.assertEqual(mock_predict.call_count, 3)

    @patch("chess_diagram_ocr.pdf_to_pgn._page_contexts")
    @patch("chess_diagram_ocr.pdf_to_pgn.predict_with_orientation")
    @patch("chess_diagram_ocr.pdf_to_pgn._detect_page_diagrams")
    @patch("chess_diagram_ocr.pdf_to_pgn._render_pdf_page")
    @patch("chess_diagram_ocr.pdf_to_pgn.load_model")
    @patch("chess_diagram_ocr.pdf_to_pgn._get_pdf_page_count")
    def test_com_model_session_a_varredura_nao_carrega_o_proprio_modelo(
        self,
        mock_get_pdf_page_count,
        mock_load_model,
        mock_render_pdf_page,
        mock_detect,
        mock_predict,
        mock_contexts,
    ) -> None:
        """S-57: a exportação e a fila rodavam fora do lock, e o treino reescreve o mesmo `.pt`.

        O emprestado tem de ser **usado**, não só aceito: se a varredura ainda chamasse
        `load_model`, o lock do serviço não cobriria nada e a corrida continuaria de pé.
        """
        mock_get_pdf_page_count.return_value = 1
        mock_render_pdf_page.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        board_rgb = np.zeros((800, 800, 3), dtype=np.uint8)
        mock_detect.return_value = [candidate_for(board_rgb, 0)]
        mock_contexts.return_value = [DiagramContext()]
        mock_predict.return_value = oriented_for(KINGS_ONLY, 0.9)

        entrou = threading.Event()
        saiu = threading.Event()

        @contextmanager
        def _emprestimo():
            entrou.set()
            try:
                yield ("modelo-do-servico", "cpu")
            finally:
                saiu.set()

        positions = scan_pdf_positions(Path("sample.pdf"), model_session=_emprestimo())

        self.assertEqual(len(positions), 1)
        mock_load_model.assert_not_called()
        self.assertTrue(entrou.is_set(), "a sessão emprestada não foi usada")
        self.assertTrue(saiu.is_set(), "o lock não foi devolvido ao fim da varredura")
        self.assertEqual(mock_predict.call_args.args[1], "modelo-do-servico")

    def test_so_o_servico_e_os_clis_carregam_o_modelo(self) -> None:
        """Regressão da S-57: `load_model` fora destes módulos é uma varredura sem lock.

        Varre a árvore em vez de testar comportamento porque o defeito era **onde** a carga
        acontecia, não o que ela devolvia: uma nova chamada em `review_queue.py` ou em
        `batch.py` passaria em qualquer teste de resultado e reabriria a corrida.
        """
        import chess_diagram_ocr

        raiz = Path(chess_diagram_ocr.__file__).parent
        permitidos = {"inference.py", "service.py", "evaluation.py"}
        culpados = [
            caminho.relative_to(raiz).as_posix()
            for caminho in sorted(raiz.rglob("*.py"))
            if caminho.name not in permitidos
            and caminho.parent.name != "cli"
            and "load_model(" in caminho.read_text(encoding="utf-8")
        ]
        # `pdf_to_pgn` fica na lista com uma chamada só, dentro de `_own_model_session`, que
        # é o caminho declarado dos CLIs. Qualquer outra é o defeito voltando.
        self.assertEqual(culpados, ["pdf_to_pgn.py"])
        fonte = (raiz / "pdf_to_pgn.py").read_text(encoding="utf-8")
        self.assertEqual(fonte.count("load_model("), 1)

    @patch("chess_diagram_ocr.pdf_to_pgn._page_contexts")
    @patch("chess_diagram_ocr.pdf_to_pgn.predict_with_orientation")
    @patch("chess_diagram_ocr.pdf_to_pgn._detect_page_diagrams")
    @patch("chess_diagram_ocr.pdf_to_pgn._render_pdf_page")
    @patch("chess_diagram_ocr.pdf_to_pgn.load_model")
    @patch("chess_diagram_ocr.pdf_to_pgn._get_pdf_page_count")
    def test_scan_pdf_positions_reports_progress(
        self,
        mock_get_pdf_page_count,
        mock_load_model,
        mock_render_pdf_page,
        mock_detect,
        mock_predict,
        mock_contexts,
    ) -> None:
        mock_get_pdf_page_count.return_value = 2
        mock_load_model.return_value = ("model", "cpu")
        mock_render_pdf_page.side_effect = [
            np.zeros((10, 10, 3), dtype=np.uint8),
            np.zeros((10, 10, 3), dtype=np.uint8),
        ]
        board_rgb = np.zeros((800, 800, 3), dtype=np.uint8)
        mock_detect.side_effect = [
            [candidate_for(board_rgb)],
            [],
        ]
        mock_contexts.side_effect = [[DiagramContext()], []]
        mock_predict.return_value = oriented_for(EMPTY_BOARD, 0.9)
        progress_calls: list[tuple[int, int, int, int]] = []

        scan_pdf_positions(
            Path("sample.pdf"),
            progress_callback=lambda page_index, total_pages, page_boards, total_positions: progress_calls.append(
                (page_index, total_pages, page_boards, total_positions)
            ),
        )

        self.assertEqual(progress_calls, [(0, 2, 1, 1), (1, 2, 0, 1)])

    @patch("chess_diagram_ocr.pdf_to_pgn.scan_pdf_positions")
    def test_save_pdf_positions_to_pgn_writes_output_file(self, mock_scan_pdf_positions) -> None:
        mock_scan_pdf_positions.return_value = [
            DiagramPosition(page_index=0, diagram_index=1, fen=KINGS_ONLY, confidence=0.95)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.pgn"
            report = save_pdf_positions_to_pgn(
                pdf_source=Path("PDF") / "book.pdf",
                output_path=output_path,
            )

            self.assertEqual(len(report.accepted), 1)
            self.assertTrue(output_path.exists())
            payload = output_path.read_text(encoding="utf-8")
            self.assertIn('[SourcePDF "book.pdf"]', payload)
            self.assertIn(f'[FEN "{KINGS_ONLY} w - - 0 1"]', payload)


class EnrichedHeaderTests(unittest.TestCase):
    """S-18: o que a S-16 extraiu tem de chegar ao PGN, e o que ela não extraiu não."""

    def position_with_context(self) -> DiagramPosition:
        return DiagramPosition(
            page_index=19,
            diagram_index=1,
            fen=KINGS_ONLY,
            confidence=0.99,
            min_confidence=0.97,
            is_legal=True,
            is_fatal=False,
            side_to_move=SideToMove(color=chess.BLACK, source="text", reason="texto do PDF"),
            context=DiagramContext(
                caption="5\nMorphy-De Riviere\nParis, 1858",
                side_to_move=chess.BLACK,
                exercise_number=5,
                players=("Morphy", "De Riviere"),
                event="Paris",
                year=1858,
            ),
            detection_source="embedded",
        )

    def test_metadados_da_legenda_preenchem_os_headers(self) -> None:
        payload = build_pgn_text([self.position_with_context()], source_name="book.pdf")

        self.assertIn('[Event "Paris"]', payload)
        self.assertIn('[White "Morphy"]', payload)
        self.assertIn('[Black "De Riviere"]', payload)
        self.assertIn('[Date "1858.??.??"]', payload)
        self.assertIn('[ExerciseNumber "5"]', payload)
        self.assertIn('[DetectionSource "embedded"]', payload)
        self.assertIn("Morphy-De Riviere", payload)

    def test_lado_a_jogar_vai_para_a_fen_e_a_procedencia_para_o_header(self) -> None:
        payload = build_pgn_text([self.position_with_context()], source_name="book.pdf")

        self.assertIn(f'[FEN "{KINGS_ONLY} b - - 0 1"]', payload)
        self.assertIn('[SideToMoveSource "text"]', payload)
        self.assertIn('[SideToMove "pretas"]', payload)

    def position_read_by_ocr(self, source: str = "ocr") -> DiagramPosition:
        """O mesmo diagrama, mas com a legenda lida por um motor e não pelo arquivo (S-43)."""
        return DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=KINGS_ONLY,
            confidence=0.99,
            min_confidence=0.97,
            is_legal=True,
            is_fatal=False,
            side_to_move=SideToMove(color=chess.BLACK, source=source, reason="OCR"),
            context=DiagramContext(
                caption="31: Jogada das pretas",
                side_to_move=chess.BLACK,
                side_to_move_origin="ocr" if source == "ocr" else "ocr-page-scope",
                side_to_move_confidence=0.62,
            ),
        )

    def test_lado_lido_por_ocr_nao_se_disfarca_de_camada_de_texto(self) -> None:
        payload = build_pgn_text([self.position_read_by_ocr()], source_name="book.pdf")

        self.assertIn('[SideToMoveSource "ocr"]', payload)
        self.assertIn('[SideToMoveConfidence "0.620"]', payload)

    def test_escopo_de_pagina_por_ocr_tem_procedencia_propria(self) -> None:
        """Um cabeçalho que vale para a página inteira não é a legenda deste diagrama."""
        payload = build_pgn_text([self.position_read_by_ocr("ocr-page-scope")], source_name="book.pdf")

        self.assertIn('[SideToMoveSource "ocr-page-scope"]', payload)

    def test_confianca_so_aparece_quando_quem_decidiu_foi_o_ocr(self) -> None:
        """Escrever a confiança de uma leitura que a legalidade derrubou seria mentir.

        A cascata da S-17 pode descartar uma declaração de OCR de 0,62 e decidir pela
        posição. O header diria que a resposta gravada vale 0,62, e ela não veio de lá.
        """
        derrubada = replace(
            self.position_read_by_ocr(),
            side_to_move=SideToMove(color=chess.WHITE, source="legality", reason="xeque", conflicting=True),
        )

        payload = build_pgn_text([derrubada], source_name="book.pdf")

        self.assertIn('[SideToMoveSource "legality"]', payload)
        self.assertNotIn("SideToMoveConfidence", payload)

    def test_camada_de_texto_nao_ganha_header_de_confianca(self) -> None:
        """1,0 em todo jogo de um livro com camada de texto ensina a ignorar o header."""
        payload = build_pgn_text([self.position_with_context()], source_name="book.pdf")

        self.assertNotIn("SideToMoveConfidence", payload)

    def test_sem_legenda_os_padroes_continuam(self) -> None:
        payload = build_pgn_text(
            [DiagramPosition(page_index=0, diagram_index=1, fen=KINGS_ONLY, confidence=0.9)],
            source_name="book.pdf",
            event_name="ChessVisionOFF PDF OCR",
        )

        self.assertIn('[Event "ChessVisionOFF PDF OCR"]', payload)
        self.assertIn('[White "?"]', payload)
        self.assertNotIn("ExerciseNumber", payload)
        self.assertNotIn("SideToMoveSource", payload)
        self.assertNotIn("Caption", payload)

    def test_lado_assumido_e_declarado_como_assumido(self) -> None:
        """O padrão continua sendo brancas -- a diferença é o PGN dizer que foi assumido."""
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=KINGS_ONLY,
            confidence=0.9,
            side_to_move=SideToMove(color=chess.WHITE, source="default", reason="nada diz"),
        )

        payload = build_pgn_text([position], source_name="book.pdf")

        self.assertIn(f'[FEN "{KINGS_ONLY} w - - 0 1"]', payload)
        self.assertIn('[SideToMoveSource "default"]', payload)

    def test_roque_inferido_e_declarado_como_inferido(self) -> None:
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen="r3k2r/8/8/8/8/8/8/R3K2R",
            confidence=0.9,
            side_to_move=SideToMove(color=chess.WHITE, source="default"),
        )

        payload = build_pgn_text([position], source_name="book.pdf")

        self.assertIn('[FEN "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"]', payload)
        self.assertIn('[CastlingSource "inferred"]', payload)

    def test_legenda_com_aspas_nao_quebra_o_header(self) -> None:
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=KINGS_ONLY,
            confidence=0.9,
            context=DiagramContext(caption='Ele disse "xeque"\nsegunda linha'),
        )

        payload = build_pgn_text([position], source_name="book.pdf")

        self.assertIn("[Caption \"Ele disse 'xeque' / segunda linha\"]", payload)


class DeduplicationTests(unittest.TestCase):
    """S-18: repetição é comum e legítima, então o padrão é anotar e não remover."""

    def positions(self) -> list[DiagramPosition]:
        return [
            DiagramPosition(page_index=0, diagram_index=1, fen=KINGS_ONLY, confidence=0.99, min_confidence=0.99),
            DiagramPosition(page_index=4, diagram_index=2, fen=KINGS_D1_D3, confidence=0.99, min_confidence=0.99),
            # Mesma colocacao de pecas da primeira: o diagrama reimpresso na solucao.
            DiagramPosition(page_index=9, diagram_index=1, fen=KINGS_ONLY, confidence=0.99, min_confidence=0.99),
        ]

    def test_repeticao_aponta_para_a_primeira_ocorrencia(self) -> None:
        marked = mark_duplicates(self.positions())

        self.assertEqual([p.duplicate_of for p in marked], [None, None, (1, 1)])

    def test_lado_a_jogar_diferente_ainda_e_a_mesma_posicao_impressa(self) -> None:
        marked = mark_duplicates(
            [
                DiagramPosition(page_index=0, diagram_index=1, fen=f"{KINGS_ONLY} w - - 0 1", confidence=0.9),
                DiagramPosition(page_index=1, diagram_index=1, fen=f"{KINGS_ONLY} b - - 0 1", confidence=0.9),
            ]
        )

        self.assertEqual(marked[1].duplicate_of, (1, 1))

    def test_sem_dedupe_a_repeticao_sai_no_pgn_anotada(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_gated_pgn(self.positions(), Path(tmpdir) / "book.pgn", source_name="book.pdf")

            payload = report.output_path.read_text(encoding="utf-8")
            self.assertEqual(payload.count("[FEN "), 3)
            self.assertIn('[DuplicateOf "1.1"]', payload)
            self.assertEqual(report.duplicates, [])

    def test_com_dedupe_a_repeticao_sai_do_arquivo_mas_nao_do_relatorio(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_gated_pgn(
                self.positions(),
                Path(tmpdir) / "book.pgn",
                source_name="book.pdf",
                pages_scanned=10,
                dedupe=True,
            )

            payload = report.output_path.read_text(encoding="utf-8")
            self.assertEqual(payload.count("[FEN "), 2)
            self.assertEqual([p.page_number for p in report.duplicates], [10])
            self.assertEqual(report.total, 3)
            self.assertIn("1 duplicados", report.summary())


class ExportGateTests(unittest.TestCase):
    """S-15: o PGN principal sai limpo e nada desaparece em silencio."""

    def positions(self) -> list[DiagramPosition]:
        return [
            # Legal e confiante -> PGN principal.
            DiagramPosition(
                page_index=0,
                diagram_index=1,
                fen=KINGS_ONLY,
                confidence=0.99,
                min_confidence=0.97,
                is_legal=True,
                is_fatal=False,
            ),
            # Legal, mas com uma casa insegura -> revisao.
            DiagramPosition(
                page_index=1,
                diagram_index=1,
                fen=KINGS_D1_D3,
                confidence=0.98,
                min_confidence=0.42,
                is_legal=True,
                is_fatal=False,
            ),
            # Ilegal -> rejeitada, fora do PGN principal.
            DiagramPosition(
                page_index=2,
                diagram_index=1,
                fen=EMPTY_BOARD,
                confidence=0.99,
                min_confidence=0.99,
                is_legal=False,
                is_fatal=True,
                problems=("tabuleiro vazio",),
            ),
        ]

    def test_classification_of_each_bucket(self) -> None:
        accepted, needs_review, rejected = partition_positions(self.positions())

        self.assertEqual([p.page_index for p in accepted], [0])
        self.assertEqual([p.page_index for p, _ in needs_review], [1])
        self.assertEqual([p.page_index for p, _ in rejected], [2])
        self.assertIn("0.420", needs_review[0][1])
        self.assertIn("tabuleiro vazio", rejected[0][1])

    def test_side_to_move_goes_to_review_and_not_to_the_bin(self) -> None:
        """O caso medido no 1937 Kemeri: 3 de 12 diagramas caem aqui.

        Rejeitar seria perder leitura boa; aceitar em silencio afirmaria um lado a jogar
        que ninguem verificou. Revisao com o motivo escrito e a unica resposta honesta.
        """
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=BLACK_IN_CHECK,
            confidence=0.99,
            min_confidence=0.98,
            is_legal=False,
            is_fatal=False,
            problems=("o lado que não joga está em xeque",),
        )

        verdict, reason = classify_position(position)

        self.assertEqual(verdict, "needs_review")
        self.assertIn("lado a jogar", reason)

    def test_texto_e_posicao_em_desacordo_vao_para_revisao(self) -> None:
        """S-17: a posição venceu e o que sai é legal, mas uma das duas fontes está errada."""
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=KINGS_ONLY,
            confidence=0.99,
            min_confidence=0.98,
            is_legal=True,
            is_fatal=False,
            side_to_move=SideToMove(
                color=chess.BLACK,
                source="legality",
                reason="o texto do PDF dizia o contrário",
                conflicting=True,
            ),
        )

        verdict, reason = classify_position(position)

        self.assertEqual(verdict, "needs_review")
        self.assertIn("discordam", reason)

    def test_lado_a_jogar_resolvido_pela_legalidade_e_aceito(self) -> None:
        """O gancho da Fase 2: o xeque invertido que ia para revisão agora passa direto.

        A posição continua a mesma; o que mudou é que alguém respondeu de quem era a vez,
        e com a resposta certa ela é legal. Mandar isso para revisão seria pedir ao usuário
        que confirmasse uma dedução que a regra do xadrez já garante.
        """
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=BLACK_IN_CHECK,
            confidence=0.99,
            min_confidence=0.98,
            is_legal=True,
            is_fatal=False,
            side_to_move=SideToMove(color=chess.BLACK, source="legality"),
        )

        self.assertEqual(classify_position(position), ("accepted", ""))

    def test_ambiguous_orientation_outranks_a_low_confidence_square(self) -> None:
        """Uma casa insegura custa uma correção; diagrama girado custa o diagrama inteiro.

        Então quando os dois problemas coexistem, o motivo que chega ao usuário é a
        orientação -- é o que ele precisa conferir primeiro.
        """
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=KINGS_ONLY,
            confidence=0.99,
            min_confidence=0.10,
            is_legal=True,
            is_fatal=False,
            rotation=180,
            orientation_ambiguous=True,
            orientation_reason="margem apertada (0.004) entre as duas orientações",
        )

        verdict, reason = classify_position(position)

        self.assertEqual(verdict, "needs_review")
        self.assertIn("orientação incerta", reason)
        self.assertIn("margem apertada", reason)

    def test_confident_board_with_settled_orientation_is_accepted(self) -> None:
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=KINGS_ONLY,
            confidence=0.99,
            min_confidence=0.98,
            is_legal=True,
            is_fatal=False,
            rotation=180,
            orientation_ambiguous=False,
            orientation_reason="maior confiança mínima (margem 0.900)",
        )

        # Ter girado nao e defeito: o diagrama do livro e que estava de cabeca para baixo.
        self.assertEqual(classify_position(position), ("accepted", ""))

    def test_unmeasured_position_is_not_condemned(self) -> None:
        """Sem `is_legal`/`min_confidence` medidos, nao ha o que alegar contra a posicao."""
        verdict, reason = classify_position(
            DiagramPosition(page_index=0, diagram_index=1, fen=KINGS_ONLY, confidence=0.5)
        )

        self.assertEqual(verdict, "accepted")
        self.assertEqual(reason, "")

    def test_threshold_zero_accepts_every_legal_position(self) -> None:
        accepted, needs_review, rejected = partition_positions(self.positions(), accept_threshold=0.0)

        self.assertEqual(len(accepted), 2)
        self.assertEqual(needs_review, [])
        # Ilegal continua ilegal: o limiar de confianca nao tem nada a dizer sobre regras.
        self.assertEqual(len(rejected), 1)

    def test_main_pgn_excludes_everything_that_needs_a_human(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "book.pgn"
            report = write_gated_pgn(self.positions(), output_path, source_name="book.pdf", pages_scanned=3)

            main_payload = output_path.read_text(encoding="utf-8")
            self.assertEqual(main_payload.count("[FEN "), 1)
            self.assertIn(KINGS_ONLY, main_payload)
            self.assertNotIn(EMPTY_BOARD, main_payload)
            self.assertNotIn("Review", main_payload)

            self.assertEqual(report.review_path, Path(tmpdir) / "book.review.pgn")
            review_payload = report.review_path.read_text(encoding="utf-8")
            self.assertEqual(review_payload.count("[FEN "), 2)
            # O motivo acompanha cada posicao separada -- sem ele o usuario adivinha.
            self.assertIn('[Review "confiança mínima 0.420 < 0.80"]', review_payload)
            self.assertIn('[Review "ilegal: tabuleiro vazio"]', review_payload)
            self.assertEqual(report.summary(), "1 aceitos, 1 para revisão, 1 rejeitados em 3 páginas")

    def test_review_file_is_not_created_when_nothing_needs_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "book.pgn"
            report = write_gated_pgn(self.positions()[:1], output_path, source_name="book.pdf", pages_scanned=1)

            self.assertIsNone(report.review_path)
            self.assertFalse((Path(tmpdir) / "book.review.pgn").exists())

    def test_review_items_keep_pdf_order(self) -> None:
        positions = list(reversed(self.positions()))
        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_gated_pgn(positions, Path(tmpdir) / "book.pgn", source_name="book.pdf")

            self.assertEqual([p.page_index for p, _ in report.review_items], [1, 2])

    def test_every_position_lands_in_exactly_one_bucket(self) -> None:
        positions = self.positions()
        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_gated_pgn(positions, Path(tmpdir) / "book.pgn", source_name="book.pdf")

            self.assertEqual(report.total, len(positions))

    def test_gate_runs_on_real_predictions_end_to_end(self) -> None:
        """Ponte com a S-10: a confianca que o gate le e a que `predict_board` produz."""
        prediction = prediction_for(KINGS_ONLY, 0.55)
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=prediction.fen_board,
            confidence=prediction.mean_confidence,
            min_confidence=prediction.min_confidence,
            is_legal=prediction.position.is_legal,
            problems=prediction.position.problems,
        )

        verdict, reason = classify_position(position)

        self.assertEqual(verdict, "needs_review")
        self.assertIn("0.550", reason)


if __name__ == "__main__":
    unittest.main()
