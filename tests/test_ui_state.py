from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

from chess_diagram_ocr.atomic_io import atomic_write_json, atomic_write_text
from chess_diagram_ocr.ui.state import (
    MAX_PDF_HISTORY,
    STATE_VERSION,
    AppState,
    load_state,
    save_state,
    state_from_dict,
)


class AtomicWriteTests(unittest.TestCase):
    """S-25: nunca existe um estado intermediário truncado no caminho de destino."""

    def test_failed_write_leaves_previous_content_intact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "estado.json"
            atomic_write_text(path, "conteudo original")

            # Objeto nao serializavel: a falha acontece *durante* a escrita, que e
            # exatamente a janela em que `write_text` deixaria o arquivo com 0 byte.
            with self.assertRaises(TypeError):
                atomic_write_json(path, {"impossivel": object()})

            self.assertEqual(path.read_text(encoding="utf-8"), "conteudo original")

    def test_no_temporary_file_survives_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "estado.json"
            with self.assertRaises(TypeError):
                atomic_write_json(path, {"impossivel": object()})
            self.assertEqual(list(Path(tmpdir).iterdir()), [])

    def test_write_creates_missing_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sub" / "dir" / "estado.json"
            atomic_write_json(path, {"a": 1})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1})


class StateRoundTripTests(unittest.TestCase):
    def test_saves_and_loads_every_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "app.json"
            state = AppState(
                last_pdf="C:/PDF/livro.pdf",
                last_page=41,
                pdf_zoom=1.25,
                board_zoom=1.1,
                pdf_history={"C:/PDF/livro.pdf": 41},
                show_heatmap=False,
                review_queue_path="data/review_queue.json",
            )
            save_state(path, state)
            restored = load_state(path)

            self.assertEqual(restored.last_pdf, state.last_pdf)
            self.assertEqual(restored.last_page, 41)
            self.assertAlmostEqual(restored.pdf_zoom, 1.25)
            self.assertAlmostEqual(restored.board_zoom, 1.1)
            self.assertFalse(restored.show_heatmap)
            self.assertEqual(restored.review_queue_path, "data/review_queue.json")

    def test_saved_state_declares_its_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "app.json"
            save_state(path, AppState())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], STATE_VERSION)


class StateMigrationTests(unittest.TestCase):
    """O formato que existe em disco hoje não tem `version` -- e precisa continuar abrindo."""

    def test_reads_version_1_without_the_version_field(self) -> None:
        antigo = {
            "last_pdf": "C:/PDF/livro.pdf",
            "last_page": 12,
            "pdf_zoom": 0.9,
            "pdf_history": {"C:/PDF/livro.pdf": 12},
        }
        state = state_from_dict(antigo)
        self.assertEqual(state.last_pdf, "C:/PDF/livro.pdf")
        self.assertEqual(state.last_page, 12)
        self.assertAlmostEqual(state.pdf_zoom, 0.9)
        self.assertEqual(state.pdf_history, {"C:/PDF/livro.pdf": 12})
        # Campos novos assumem o padrao, e nao lixo.
        self.assertTrue(state.show_heatmap)

    def test_refuses_state_written_by_a_newer_version(self) -> None:
        with self.assertRaises(ValueError):
            state_from_dict({"version": STATE_VERSION + 1})


class InvalidStateTests(unittest.TestCase):
    """Estado inválido gera aviso no log, não silêncio -- é o que a S-25 exige."""

    def test_corrupted_json_warns_and_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "app.json"
            path.write_text("{isto nao e json", encoding="utf-8")

            with self.assertLogs("chess_diagram_ocr.ui.state", level=logging.WARNING) as captured:
                state = load_state(path)

            self.assertEqual(state, AppState())
            self.assertTrue(any("descartado" in line for line in captured.output))

    def test_truncated_file_warns(self) -> None:
        """O arquivo de 0 byte que a escrita não atômica produzia."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "app.json"
            path.write_text("", encoding="utf-8")
            with self.assertLogs("chess_diagram_ocr.ui.state", level=logging.WARNING):
                self.assertEqual(load_state(path), AppState())

    def test_json_that_is_not_an_object_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "app.json"
            path.write_text("[1, 2, 3]", encoding="utf-8")
            with self.assertLogs("chess_diagram_ocr.ui.state", level=logging.WARNING):
                self.assertEqual(load_state(path), AppState())

    def test_missing_file_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(load_state(Path(tmpdir) / "nao-existe.json"), AppState())

    def test_field_of_wrong_type_falls_back_without_losing_the_rest(self) -> None:
        state = state_from_dict({"last_pdf": "livro.pdf", "last_page": "quarenta", "pdf_zoom": None})
        self.assertEqual(state.last_pdf, "livro.pdf")
        self.assertEqual(state.last_page, 0)
        self.assertAlmostEqual(state.pdf_zoom, AppState().pdf_zoom)

    def test_zoom_out_of_range_is_clamped(self) -> None:
        self.assertAlmostEqual(state_from_dict({"pdf_zoom": 99.0}).pdf_zoom, 2.0)
        self.assertAlmostEqual(state_from_dict({"pdf_zoom": 0.0}).pdf_zoom, 0.25)


class PdfHistoryTests(unittest.TestCase):
    def test_remembers_page_per_pdf(self) -> None:
        state = AppState()
        pdf = Path("livro.pdf")
        state.remember_page(pdf, 17)
        self.assertEqual(state.page_for(pdf), 17)
        self.assertEqual(state.page_for(Path("outro.pdf")), 0)

    def test_history_is_bounded(self) -> None:
        state = AppState()
        for index in range(MAX_PDF_HISTORY + 10):
            state.remember_page(Path(f"livro_{index}.pdf"), index)
        self.assertEqual(len(state.pdf_history), MAX_PDF_HISTORY)
        # O mais antigo saiu; o mais recente ficou.
        self.assertEqual(state.page_for(Path(f"livro_{MAX_PDF_HISTORY + 9}.pdf")), MAX_PDF_HISTORY + 9)
        self.assertEqual(state.page_for(Path("livro_0.pdf")), 0)


if __name__ == "__main__":
    unittest.main()
