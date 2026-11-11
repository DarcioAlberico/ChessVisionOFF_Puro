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
                show_diagram_boxes=False,
                review_queue_path="data/review_queue.json",
            )
            save_state(path, state)
            restored = load_state(path)

            self.assertEqual(restored.last_pdf, state.last_pdf)
            self.assertEqual(restored.last_page, 41)
            self.assertAlmostEqual(restored.pdf_zoom, 1.25)
            self.assertAlmostEqual(restored.board_zoom, 1.1)
            self.assertFalse(restored.show_heatmap)
            self.assertFalse(restored.show_diagram_boxes)
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
        self.assertTrue(state.show_diagram_boxes)

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

    def test_o_historico_lido_e_aparado_ao_teto(self) -> None:
        """S-828: o teto valia para `remember_page` e não para a leitura; 500 entradas seguiam 500."""
        state = state_from_dict({"pdf_history": {str(i): i for i in range(80)}})
        self.assertEqual(len(state.pdf_history), MAX_PDF_HISTORY)
        # A ordem do arquivo é a de uso (`recentes`): ficam as últimas, que são as mais recentes.
        self.assertEqual(list(state.pdf_history), [str(i) for i in range(80 - MAX_PDF_HISTORY, 80)])


class LeituraPorTabelaTests(unittest.TestCase):
    """S-828: todo campo do `AppState` é lido, e o de tipo errado cai no padrão do próprio `AppState`."""

    def test_todo_campo_faz_ida_e_volta(self) -> None:
        import dataclasses

        from chess_diagram_ocr.ui import viewport

        padrao = AppState()
        self.assertNotEqual(padrao.pdf_enquadramento, viewport.ENQUADRAMENTO_PAGINA)
        mudado = AppState(
            **{
                campo.name: _outro_valor(getattr(padrao, campo.name))
                for campo in dataclasses.fields(AppState)
                if campo.name != "pdf_enquadramento"
            },
            pdf_enquadramento=viewport.ENQUADRAMENTO_PAGINA,
        )
        relido = state_from_dict(mudado.to_dict())
        for campo in dataclasses.fields(AppState):
            with self.subTest(campo.name):
                self.assertEqual(getattr(relido, campo.name), getattr(mudado, campo.name))
                self.assertNotEqual(getattr(relido, campo.name), getattr(padrao, campo.name), "o campo não foi lido")

    def test_todo_campo_de_tipo_errado_cai_no_padrao(self) -> None:
        import dataclasses

        padrao = AppState()
        estragado: dict[str, object] = {campo.name: object() for campo in dataclasses.fields(AppState)}
        estragado.update(last_page=True, texto_zoom=False, pdf_zoom=True, texto_glifos_recentes="abc")
        relido = state_from_dict(estragado)
        self.assertEqual(relido, padrao)


def _outro_valor(valor: object) -> object:
    """Um valor do mesmo tipo e diferente do padrão, dentro das faixas que a leitura grampeia."""
    if isinstance(valor, bool):
        return not valor
    if isinstance(valor, int):
        return valor + 3
    if isinstance(valor, float):
        return 0.5 if valor != 0.5 else 0.6
    if isinstance(valor, str):
        return valor + "x"
    if isinstance(valor, dict):
        return {"C:/PDF/livro.pdf": 7}
    if isinstance(valor, list):
        return ["♔", "♘"]
    raise AssertionError(f"tipo sem valor de teste: {type(valor).__name__}")


class ArranjoDaJanelaTests(unittest.TestCase):
    """Os três campos que faltavam: geometria, divisor e aba (S-156).

    O estado lembrava o PDF, a página, os dois zooms e três interruptores — cada um com o
    porquê escrito ao lado. Não lembrava o **arranjo da janela**, que é o que o usuário
    reconstrói primeiro ao voltar: o tamanho, onde ele deixou o divisor, e em que aba estava.
    """

    def test_os_tres_campos_fazem_ida_e_volta(self) -> None:
        state = AppState(window_geometry="1700x980+120+40", sash_fraction=0.63, active_tab="Resultado")
        de_volta = state_from_dict(state.to_dict())
        self.assertEqual(de_volta.window_geometry, "1700x980+120+40")
        self.assertAlmostEqual(de_volta.sash_fraction, 0.63, places=6)
        self.assertEqual(de_volta.active_tab, "Resultado")

    def test_os_padroes_dizem_nunca_guardado(self) -> None:
        """"Não guardado" e "guardado no padrão" são estados diferentes: o divisor em 42% que o
        usuário escolheu tem de sobreviver a alguém mudar o padrão."""
        state = AppState()
        self.assertEqual(state.window_geometry, "")
        self.assertEqual(state.sash_fraction, 0.0)
        self.assertEqual(state.active_tab, "")

    def test_um_estado_antigo_sem_os_tres_campos_continua_valendo(self) -> None:
        """O formato em disco hoje não os tem, e ler um deles não pode custar os outros nove."""
        antigo = {"version": STATE_VERSION, "last_pdf": "livro.pdf", "pdf_zoom": 1.2}
        state = state_from_dict(antigo)
        self.assertEqual(state.last_pdf, "livro.pdf")
        self.assertAlmostEqual(state.pdf_zoom, 1.2, places=6)
        self.assertEqual(state.window_geometry, "")

    def test_campo_de_tipo_errado_cai_no_padrao_sem_derrubar_a_leitura(self) -> None:
        state = state_from_dict(
            {
                "version": STATE_VERSION,
                "last_pdf": "livro.pdf",
                "window_geometry": 1700,
                "sash_fraction": "meio",
                "active_tab": ["Resultado"],
            }
        )
        self.assertEqual(state.last_pdf, "livro.pdf", "um campo estragado custou o resto")
        self.assertEqual((state.window_geometry, state.sash_fraction, state.active_tab), ("", 0.0, ""))

    def test_a_fracao_do_divisor_e_grampeada_na_leitura(self) -> None:
        """Um valor absurdo em disco não pode virar um painel de largura negativa na tela."""
        for bruto, esperado in ((-3.0, 0.0), (7.5, 1.0), (0.5, 0.5)):
            with self.subTest(bruto=bruto):
                state = state_from_dict({"version": STATE_VERSION, "sash_fraction": bruto})
                self.assertAlmostEqual(state.sash_fraction, esperado, places=6)

    def test_a_aba_e_guardada_por_rotulo_e_nao_por_indice(self) -> None:
        """Índice não sobrevive a reordenar as abas -- e a S-162 é, literalmente, reordená-las."""
        self.assertIsInstance(AppState().active_tab, str)
        self.assertEqual(state_from_dict({"version": STATE_VERSION, "active_tab": 3}).active_tab, "")


if __name__ == "__main__":
    unittest.main()
