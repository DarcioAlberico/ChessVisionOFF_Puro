"""Cache de reconhecimento por pagina (navegar sem perder o OCR)."""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui.page_results import (
    DEFAULT_MAX_CACHED_PAGES,
    PageOcrParams,
    PageResults,
    PageResultsCache,
    PageSwitch,
    decide_page_switch,
    page_index_from_origin,
)

DOC = "livro.pdf"
PARAMS = PageOcrParams(dpi=220, max_boards=12, orientation="auto", model_path="m.pt")


def _results(page: int, count: int = 3, *, params: PageOcrParams = PARAMS, hand: bool = False) -> PageResults:
    itens = [{"index": i, "fen_pred": f"p{page}d{i}"} for i in range(count)]
    if hand and itens:
        itens[0]["edited_by_hand"] = True
    return PageResults(
        page_index=page,
        params=params,
        items=itens,
        fen_edits=[f"p{page}d{i}" for i in range(count)],
        side_edits=["w"] * count,
    )


class PageResultsTests(unittest.TestCase):
    def test_mismatched_list_lengths_are_rejected(self) -> None:
        """Listas paralelas de tamanhos diferentes corrompem a selecao em silencio."""
        with self.assertRaises(ValueError):
            PageResults(page_index=1, params=PARAMS, items=[{}, {}], fen_edits=["a"], side_edits=["w", "b"])

    def test_hand_edits_are_detected_from_either_marker(self) -> None:
        self.assertFalse(_results(1).has_hand_edits)
        self.assertTrue(_results(1, hand=True).has_hand_edits)

        pelo_lado = _results(1)
        pelo_lado.items[1]["side_to_move_source"] = "manual"
        self.assertTrue(pelo_lado.has_hand_edits)

    def test_selected_index_is_clamped_to_the_available_diagrams(self) -> None:
        guardado = _results(1, count=3)
        guardado.selected_index = 9
        self.assertEqual(guardado.clamped_index(), 2)
        guardado.selected_index = -4
        self.assertEqual(guardado.clamped_index(), 0)

    def test_empty_results_clamp_to_zero(self) -> None:
        vazio = PageResults(page_index=1, params=PARAMS)
        vazio.selected_index = 5
        self.assertEqual(vazio.clamped_index(), 0)


class RoundTripTests(unittest.TestCase):
    def test_a_stored_page_comes_back(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(17))

        de_volta = cache.get(DOC, 17, PARAMS)
        self.assertIsNotNone(de_volta)
        assert de_volta is not None
        self.assertEqual(de_volta.count, 3)
        self.assertEqual(de_volta.fen_edits[1], "p17d1")

    def test_a_page_that_was_never_recognised_returns_none(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(17))
        self.assertIsNone(cache.get(DOC, 18, PARAMS))

    def test_pages_of_other_documents_do_not_collide(self) -> None:
        """A pagina 17 de um livro nao pode devolver os diagramas da 17 de outro."""
        cache = PageResultsCache()
        cache.put("a.pdf", _results(17))
        self.assertIsNone(cache.get("b.pdf", 17, PARAMS))

    def test_edits_made_after_storing_are_visible_because_lists_are_shared(self) -> None:
        """E o ponto do desenho: nao existe um passo de "salvar" que possa ser esquecido."""
        cache = PageResultsCache()
        guardado = _results(17)
        cache.put(DOC, guardado)

        guardado.fen_edits[0] = "corrigido a mao"
        de_volta = cache.get(DOC, 17, PARAMS)
        assert de_volta is not None
        self.assertEqual(de_volta.fen_edits[0], "corrigido a mao")

    def test_storing_the_same_page_twice_replaces_it(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(17, count=3))
        cache.put(DOC, _results(17, count=5))

        de_volta = cache.get(DOC, 17, PARAMS)
        assert de_volta is not None
        self.assertEqual(de_volta.count, 5)
        self.assertEqual(len(cache), 1)


class ParameterMismatchTests(unittest.TestCase):
    """Decisao da S-24: retomar com parametros diferentes nao e retomar."""

    def test_a_different_dpi_invalidates_the_stored_crop(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(17))
        outro_dpi = PageOcrParams(dpi=300, max_boards=12, orientation="auto", model_path="m.pt")
        self.assertIsNone(cache.get(DOC, 17, outro_dpi))

    def test_a_different_model_invalidates_the_stored_reading(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(17))
        outro_modelo = PageOcrParams(dpi=220, max_boards=12, orientation="auto", model_path="outro.pt")
        self.assertIsNone(cache.get(DOC, 17, outro_modelo))

    def test_an_invalidated_entry_is_dropped_not_kept_around(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(17))
        cache.get(DOC, 17, PageOcrParams(dpi=300, max_boards=12, orientation="auto", model_path="m.pt"))
        self.assertEqual(len(cache), 0)

    def test_the_log_says_what_changed(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(17))
        outro = PageOcrParams(dpi=300, max_boards=12, orientation="180", model_path="m.pt")
        with self.assertLogs("chess_diagram_ocr.ui.page_results", level="INFO") as capturado:
            cache.get(DOC, 17, outro)
        texto = "\n".join(capturado.output)
        self.assertIn("DPI", texto)
        self.assertIn("orienta", texto)

    def test_describe_difference_is_empty_for_identical_params(self) -> None:
        self.assertEqual(PARAMS.describe_difference(PARAMS), "")


class EvictionTests(unittest.TestCase):
    """Cada item carrega um recorte de 1,83 MiB: sem teto, navegar vaza memoria (S-26)."""

    def test_the_cache_never_exceeds_its_limit(self) -> None:
        cache = PageResultsCache(max_pages=3)
        for page in range(10):
            cache.put(DOC, _results(page))
            self.assertLessEqual(len(cache), 3)

    def test_the_least_recently_used_page_is_the_one_evicted(self) -> None:
        cache = PageResultsCache(max_pages=2)
        cache.put(DOC, _results(1))
        cache.put(DOC, _results(2))
        cache.get(DOC, 1, PARAMS)  # renova a pagina 1
        cache.put(DOC, _results(3))

        self.assertIsNotNone(cache.get(DOC, 1, PARAMS))
        self.assertIsNone(cache.get(DOC, 2, PARAMS))
        self.assertIsNotNone(cache.get(DOC, 3, PARAMS))

    def test_evicting_hand_corrected_work_is_warned_not_silent(self) -> None:
        """Perder leitura do modelo custa rodar o OCR; perder correcao custa o trabalho."""
        cache = PageResultsCache(max_pages=1)
        cache.put(DOC, _results(1, hand=True))
        with self.assertLogs("chess_diagram_ocr.ui.page_results", level="WARNING") as capturado:
            cache.put(DOC, _results(2))
        self.assertIn("mao", "\n".join(capturado.output))

    def test_evicting_untouched_results_is_quiet(self) -> None:
        cache = PageResultsCache(max_pages=1)
        cache.put(DOC, _results(1))
        with self.assertNoLogs("chess_diagram_ocr.ui.page_results", level="WARNING"):
            cache.put(DOC, _results(2))

    def test_a_limit_below_one_is_clamped(self) -> None:
        self.assertEqual(PageResultsCache(max_pages=0).max_pages, 1)

    def test_the_default_limit_bounds_memory_to_a_few_hundred_megabytes(self) -> None:
        # 9 diagramas x 1,83 MiB por pagina: o teto tem de manter isso na casa das centenas
        # de MiB, nao dos gigabytes.
        self.assertLessEqual(DEFAULT_MAX_CACHED_PAGES * 9 * 1.83, 300)


class PageSwitchDecisionTests(unittest.TestCase):
    def test_stored_results_are_restored(self) -> None:
        self.assertIs(
            decide_page_switch(stored=_results(17), current_is_page_result=True),
            PageSwitch.RESTORE,
        )

    def test_results_of_another_page_are_cleared(self) -> None:
        """O sintoma relatado: "Selecionado" apontando para diagramas de outra pagina."""
        self.assertIs(
            decide_page_switch(stored=None, current_is_page_result=True),
            PageSwitch.CLEAR,
        )

    def test_a_dataset_sample_in_the_editor_survives_page_navigation(self) -> None:
        """Amostra do dataset ou item da fila nao tem a ver com a pagina exibida.

        Limpa-la porque "esta pagina nao tem reconhecimento" apagaria o trabalho do
        usuario por um motivo que nao e dele.
        """
        self.assertIs(
            decide_page_switch(stored=None, current_is_page_result=False),
            PageSwitch.KEEP,
        )

    def test_stored_results_win_even_over_unrelated_editor_content(self) -> None:
        self.assertIs(
            decide_page_switch(stored=_results(17), current_is_page_result=False),
            PageSwitch.RESTORE,
        )


class OriginParsingTests(unittest.TestCase):
    """Quais origens de OCR contam como "resultado desta pagina"."""

    def test_a_full_page_ocr_is_a_page_result(self) -> None:
        self.assertEqual(page_index_from_origin("pdf:livro.pdf:page:17"), 17)

    def test_page_zero_is_a_valid_page_not_a_falsy_miss(self) -> None:
        """`if pagina:` em vez de `if pagina is None:` quebraria a primeira pagina."""
        self.assertEqual(page_index_from_origin("pdf:livro.pdf:page:0"), 0)

    def test_an_area_crop_is_not_a_page_result(self) -> None:
        origem = "pdf:livro.pdf:page:17:crop=(10,20)-(300,400)"
        self.assertIsNone(page_index_from_origin(origem))

    def test_a_local_image_is_not_a_page_result(self) -> None:
        self.assertIsNone(page_index_from_origin("local-image:foto.png"))

    def test_a_pdf_name_containing_page_does_not_confuse_the_parser(self) -> None:
        """`rsplit` pega o ultimo `:page:`, entao o nome do arquivo nao interfere."""
        self.assertEqual(page_index_from_origin("pdf:my:page:book.pdf:page:42"), 42)

    def test_a_malformed_page_number_returns_none_instead_of_raising(self) -> None:
        self.assertIsNone(page_index_from_origin("pdf:livro.pdf:page:abc"))

    def test_an_origin_without_a_page_marker_returns_none(self) -> None:
        self.assertIsNone(page_index_from_origin("pdf:livro.pdf"))


class DiscardTests(unittest.TestCase):
    def test_discarding_one_page_leaves_the_others(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(1))
        cache.put(DOC, _results(2))
        cache.discard(DOC, 1)

        self.assertIsNone(cache.get(DOC, 1, PARAMS))
        self.assertIsNotNone(cache.get(DOC, 2, PARAMS))

    def test_discarding_a_document_leaves_the_other_document(self) -> None:
        cache = PageResultsCache()
        cache.put("a.pdf", _results(1))
        cache.put("b.pdf", _results(1))
        cache.discard_document("a.pdf")

        self.assertIsNone(cache.get("a.pdf", 1, PARAMS))
        self.assertIsNotNone(cache.get("b.pdf", 1, PARAMS))

    def test_discarding_a_missing_page_is_not_an_error(self) -> None:
        PageResultsCache().discard(DOC, 99)

    def test_clear_empties_everything(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(1))
        cache.clear()
        self.assertEqual(len(cache), 0)

    def test_membership_and_listing_reflect_eviction_order(self) -> None:
        cache = PageResultsCache(max_pages=3)
        for page in (5, 6, 7):
            cache.put(DOC, _results(page))
        self.assertIn((DOC, 5), cache)
        self.assertEqual(cache.cached_pages, [(DOC, 5), (DOC, 6), (DOC, 7)])


if __name__ == "__main__":
    unittest.main()
