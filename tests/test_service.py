"""Camada de serviço (S-31): o pipeline de OCR exercitado sem nenhuma interface.

O critério de aceite da S-31 diz "`OcrService` testável sem Tk", e é literalmente o que
este arquivo verifica: nenhum `import tkinter`, nenhum `streamlit`, nenhuma janela. Era
justamente por estar preso dentro de `ChessOcrTkApp` que o pipeline não tinha teste nenhum
-- e foi assim que o Streamlit pôde divergir dele sem nada acusar.
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from chess_diagram_ocr.config import BOARD_SIZE, PIECE_CLASSES, PIECE_TO_IDX
from chess_diagram_ocr.model import ArchConfig
from chess_diagram_ocr.service import (
    OcrService,
    RecognitionOptions,
    RecognitionOrigin,
    RecognizedDiagram,
    refine_board_from_quad,
)

# Rei preto em a8 em xeque pela dama branca em a7, rei branco em h1. A posição só é legal
# com as pretas a jogar -- é o caso que a S-17 usa para deduzir a vez sem texto nenhum, e
# o mesmo que denunciava o `w` fixo do Streamlit como ilegal.
PRETAS_A_JOGAR = "k7/Q7/8/8/8/8/8/7K"


def _class_indices(placement: str) -> list[int]:
    """As 64 classes na ordem de leitura a8..h1 a partir do campo de peças da FEN."""
    indices: list[int] = []
    for row in placement.split("/"):
        for char in row:
            if char.isdigit():
                indices.extend([PIECE_TO_IDX["empty"]] * int(char))
            else:
                indices.append(PIECE_TO_IDX[char])
    return indices


class _ScriptedModel(nn.Module):
    """Responde uma classe escolhida por posição no lote.

    O lote que `board_probabilities` monta é exatamente as 64 casas em ordem de leitura,
    então ditar a resposta por índice dá controle total sobre a FEN lida -- sem precisar
    de um `.pt` nem de pesos que acertem coisa alguma.
    """

    def __init__(self, placement: str = PRETAS_A_JOGAR, logit: float = 8.0) -> None:
        super().__init__()
        self.arch = ArchConfig()
        self.temperature = 1.0
        self.indices = _class_indices(placement)
        self.logit = logit
        self.forward_calls = 0

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        self.forward_calls += 1
        logits = torch.zeros(x.shape[0], len(PIECE_CLASSES))
        for row in range(x.shape[0]):
            logits[row, self.indices[row % 64]] = self.logit
        return logits


def _service(placement: str = PRETAS_A_JOGAR) -> tuple[OcrService, _ScriptedModel]:
    model = _ScriptedModel(placement)
    loads = {"count": 0}

    def loader(path: Path) -> tuple[nn.Module, str]:
        loads["count"] += 1
        return model, "cpu"

    service = OcrService(model_path=Path("inexistente.pt"), loader=loader)
    service.load_count = loads  # type: ignore[attr-defined]
    return service, model


def _board_image() -> np.ndarray:
    return np.random.default_rng(0).integers(0, 256, (BOARD_SIZE, BOARD_SIZE, 3), dtype=np.uint8)


def _upright() -> RecognitionOptions:
    """Orientação fixa em 0°: `auto` faria duas leituras e o modelo ditado é simétrico."""
    return RecognitionOptions(orientation="0", max_boards=4)


class OriginTests(unittest.TestCase):
    """A origem era f-string montada em três lugares e interpretada em dois."""

    def test_page_origin_round_trips(self) -> None:
        origin = RecognitionOrigin.for_page("livro.pdf", 16)
        self.assertEqual(origin.as_text(), "pdf:livro.pdf:page:16")
        self.assertEqual(RecognitionOrigin.parse(origin.as_text()), origin)

    def test_image_origin_round_trips(self) -> None:
        origin = RecognitionOrigin.for_image("foto.png")
        self.assertEqual(origin.as_text(), "local-image:foto.png")
        self.assertEqual(RecognitionOrigin.parse(origin.as_text()), origin)

    def test_crop_origin_keeps_the_page_and_is_not_a_whole_page(self) -> None:
        origin = RecognitionOrigin.for_crop("livro.pdf", 16, (10, 20, 300, 400))
        self.assertEqual(origin.as_text(), "pdf:livro.pdf:page:16:crop=(10,20)-(300,400)")

        lido = RecognitionOrigin.parse(origin.as_text())
        self.assertEqual(lido.page_index, 16)
        self.assertEqual(lido.kind, "crop")
        self.assertFalse(lido.is_whole_page)

    def test_only_a_whole_page_may_go_to_the_page_cache(self) -> None:
        self.assertTrue(RecognitionOrigin.for_page("livro.pdf", 3).is_whole_page)
        self.assertFalse(RecognitionOrigin.for_image("foto.png").is_whole_page)

    def test_page_zero_is_a_real_page_and_not_a_falsy_miss(self) -> None:
        """`if pagina:` em vez de `is None` quebraria a primeira página do livro."""
        lido = RecognitionOrigin.parse("pdf:livro.pdf:page:0")
        self.assertEqual(lido.page_index, 0)
        self.assertTrue(lido.is_whole_page)

    def test_a_pdf_name_containing_the_marker_does_not_confuse_the_parser(self) -> None:
        """O marcador que vale é o último; o nome do arquivo não interfere."""
        self.assertEqual(RecognitionOrigin.parse("pdf:my:page:book.pdf:page:42").page_index, 42)

    def test_an_origin_without_a_page_marker_is_not_a_page_result(self) -> None:
        self.assertFalse(RecognitionOrigin.parse("pdf:livro.pdf").is_whole_page)

    def test_unparseable_origin_degrades_to_image_instead_of_raising(self) -> None:
        """Procedência estranha ainda vale gravada; exceção no meio de um salvamento, não."""
        lido = RecognitionOrigin.parse("pdf:livro.pdf:page:dezesseis")
        self.assertEqual(lido.kind, "image")
        self.assertFalse(lido.is_whole_page)

    def test_sample_page_is_one_based_like_the_number_the_user_sees(self) -> None:
        campos = RecognitionOrigin.for_page("livro.pdf", 16).sample_fields()
        self.assertEqual(campos, {"source_pdf": "livro.pdf", "source_page": 17})

    def test_local_image_has_no_page_to_record(self) -> None:
        campos = RecognitionOrigin.for_image("foto.png").sample_fields()
        self.assertEqual(campos["source_page"], "")


class RecognizeTests(unittest.TestCase):
    def test_a_detected_board_becomes_a_diagram_with_the_prediction_kept(self) -> None:
        service, _ = _service()
        boards = [(_board_image(), None)]

        diagramas = service.recognize_image(_board_image(), options=_upright(), boards=boards)

        self.assertEqual(len(diagramas), 1)
        self.assertEqual(diagramas[0].placement, PRETAS_A_JOGAR)
        # A matriz por casa sobrevive ate a UI: e o insumo do heatmap da S-21, e era
        # exatamente o que o dicionario do Streamlit descartava.
        self.assertIsNotNone(diagramas[0].probs)
        assert diagramas[0].probs is not None
        self.assertEqual(diagramas[0].probs.shape, (64, len(PIECE_CLASSES)))
        self.assertEqual(len(diagramas[0].square_confidences), 64)

    def test_legality_is_composed_with_the_inferred_side_not_a_fixed_white(self) -> None:
        """O defeito que o Streamlit tinha: `w` fixo tornava esta posição ilegal."""
        service, _ = _service()

        diagrama = service.recognize_image(
            _board_image(), options=_upright(), boards=[(_board_image(), None)]
        )[0]

        self.assertEqual(diagrama.side_to_move, "b")
        self.assertEqual(diagrama.side_to_move_source, "legality")
        self.assertTrue(diagrama.is_legal)

    def test_every_diagram_carries_its_own_index(self) -> None:
        service, _ = _service()
        boards = [(_board_image(), None) for _ in range(3)]

        diagramas = service.recognize_image(_board_image(), options=_upright(), boards=boards)

        self.assertEqual([d.index for d in diagramas], [0, 1, 2])

    def test_nothing_detected_raises_instead_of_returning_an_empty_page(self) -> None:
        service, _ = _service()
        with self.assertRaises(ValueError):
            service.recognize_image(_board_image(), options=_upright(), boards=[])

    def test_fallback_treats_the_whole_image_as_the_board(self) -> None:
        """Quem selecionou a área com o mouse já disse onde está o diagrama."""
        service, _ = _service()
        options = RecognitionOptions(orientation="0", fallback_to_full_image=True)

        diagramas = service.recognize_image(_board_image(), options=options, boards=[])

        self.assertEqual(len(diagramas), 1)
        self.assertIsNone(diagramas[0].quad)

    def test_region_clamps_to_the_page_instead_of_slicing_out_of_bounds(self) -> None:
        """Retângulo maior que a página vira a página inteira, não uma fatia vazia."""
        service, _ = _service()
        page = _board_image()

        recortado = service.recognize_region(page, (-50, -50, 10_000, 10_000), options=_upright())
        inteiro = service.recognize_image(page, options=_upright())

        self.assertEqual(len(recortado), len(inteiro))
        self.assertGreaterEqual(len(recortado), 1)


class ModelLifecycleTests(unittest.TestCase):
    def test_the_model_is_loaded_once_and_reused(self) -> None:
        service, _ = _service()
        for _ in range(3):
            service.recognize_image(_board_image(), options=_upright(), boards=[(_board_image(), None)])

        self.assertEqual(service.load_count["count"], 1)  # type: ignore[attr-defined]

    def test_invalidating_forces_the_next_read_to_load_again(self) -> None:
        service, _ = _service()
        service.load()
        service.invalidate_model()
        service.load()

        self.assertEqual(service.load_count["count"], 2)  # type: ignore[attr-defined]

    def test_device_label_says_so_when_no_model_is_loaded_yet(self) -> None:
        service, _ = _service()
        self.assertIn("nenhum modelo", service.device_label)

    def test_reload_waits_for_a_recognition_in_flight(self) -> None:
        """A corrida que a S-31 nomeia: o treino zerava o modelo durante um OCR.

        Sem o lock, `invalidate_model` retornaria de imediato -- é isso que o tempo
        registrado aqui distingue, e não a simples ausência de erro.
        """
        service, _ = _service()
        dentro = threading.Event()
        pode_sair = threading.Event()
        invalidou = threading.Event()

        def segurando() -> None:
            with service.model_session():
                dentro.set()
                pode_sair.wait(timeout=5)

        ocr = threading.Thread(target=segurando, daemon=True)
        ocr.start()
        self.assertTrue(dentro.wait(timeout=5))

        def invalidando() -> None:
            service.invalidate_model()
            invalidou.set()

        treino = threading.Thread(target=invalidando, daemon=True)
        treino.start()

        # Enquanto a sessao esta aberta, a invalidacao nao passa.
        self.assertFalse(invalidou.wait(timeout=0.3))
        pode_sair.set()
        self.assertTrue(invalidou.wait(timeout=5))
        ocr.join(timeout=5)


class DiagramTests(unittest.TestCase):
    def _diagram(self) -> RecognizedDiagram:
        service, _ = _service()
        return service.recognize_image(
            _board_image(), options=_upright(), boards=[(_board_image(), None)]
        )[0]

    def test_changing_the_side_marks_it_manual_and_clears_the_conflict(self) -> None:
        diagrama = self._diagram()
        diagrama.side_conflicting = True

        diagrama.set_side_to_move("w")

        self.assertEqual(diagrama.side_to_move, "w")
        self.assertEqual(diagrama.side_to_move_source, "manual")
        self.assertFalse(diagrama.side_conflicting)

    def test_legality_follows_the_side_because_turning_it_can_fix_the_position(self) -> None:
        """Trocar a vez resolve o "xeque invertido" sem mexer em nenhuma peça (S-17)."""
        diagrama = self._diagram()
        self.assertTrue(diagrama.is_legal)

        diagrama.set_side_to_move("w")
        diagrama.resolve_legality()

        self.assertFalse(diagrama.is_legal)

    def test_legality_can_be_recomputed_from_a_hand_edited_placement(self) -> None:
        diagrama = self._diagram()
        diagrama.resolve_legality("8/8/8/8/8/8/8/8")

        self.assertFalse(diagrama.is_legal)
        self.assertTrue(diagrama.is_fatal)

    def test_context_fields_are_empty_without_a_pdf_caption(self) -> None:
        diagrama = self._diagram()
        self.assertIsNone(diagrama.exercise_number)
        self.assertEqual(diagrama.caption, "")


class SaveSampleTests(unittest.TestCase):
    def test_the_sample_records_where_it_came_from(self) -> None:
        service, _ = _service()
        diagrama = service.recognize_image(
            _board_image(), options=_upright(), boards=[(_board_image(), None)]
        )[0]

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            csv_path = raiz / "labels.csv"
            service.save_sample(
                diagrama,
                PRETAS_A_JOGAR,
                csv_path=csv_path,
                samples_dir=raiz / "samples",
                origin=RecognitionOrigin.for_page("livro.pdf", 16),
            )

            linhas = csv_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(linhas), 2)
        self.assertIn("livro.pdf", linhas[1])
        # Pagina 1-based e o diagrama 1-based, como aparecem na interface.
        self.assertIn("17", linhas[1])
        self.assertIn(",b,", f",{linhas[1]},")

    def test_saving_without_an_origin_leaves_the_fields_empty_instead_of_guessing(self) -> None:
        service, _ = _service()
        diagrama = service.recognize_image(
            _board_image(), options=_upright(), boards=[(_board_image(), None)]
        )[0]

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            csv_path = raiz / "labels.csv"
            service.save_sample(
                diagrama, PRETAS_A_JOGAR, csv_path=csv_path, samples_dir=raiz / "samples"
            )
            cabecalho, linha = csv_path.read_text(encoding="utf-8").splitlines()

        colunas = dict(zip(cabecalho.split(","), linha.split(","), strict=False))
        self.assertEqual(colunas["source_pdf"], "")
        self.assertEqual(colunas["source_page"], "")


class RefineTests(unittest.TestCase):
    def test_without_a_quad_the_image_is_only_resized(self) -> None:
        board, quad = refine_board_from_quad(_board_image(), None)
        self.assertEqual(board.shape, (BOARD_SIZE, BOARD_SIZE, 3))
        self.assertIsNone(quad)

    def test_a_quad_outside_the_image_does_not_crash(self) -> None:
        quad = np.array([[-10, -10], [-5, -10], [-5, -5], [-10, -5]], dtype=np.float32)
        board, _ = refine_board_from_quad(_board_image(), quad)
        self.assertEqual(board.shape, (BOARD_SIZE, BOARD_SIZE, 3))


class NoUiDependencyTests(unittest.TestCase):
    """O critério de aceite da S-31, verificável em vez de prometido."""

    def test_the_service_module_imports_no_ui_toolkit(self) -> None:
        fonte = (
            Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "service.py"
        ).read_text(encoding="utf-8")

        for proibido in ("import tkinter", "import streamlit", "from tkinter", "from PIL"):
            with self.subTest(importacao=proibido):
                self.assertNotIn(proibido, fonte)


if __name__ == "__main__":
    unittest.main()
