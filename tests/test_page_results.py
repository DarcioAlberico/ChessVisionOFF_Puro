"""Cache de reconhecimento por pagina (navegar sem perder o OCR)."""

from __future__ import annotations

import unittest

import numpy as np
import pytest

from chess_diagram_ocr.service import RecognizedDiagram
from chess_diagram_ocr.ui.page_results import (
    DEFAULT_MAX_CACHED_PAGES,
    PageOcrParams,
    PageResults,
    PageResultsCache,
    PageSwitch,
    decide_page_switch,
    paginas_editadas,
)

DOC = "livro.pdf"
PARAMS = PageOcrParams(dpi=220, max_boards=12, orientation="auto", model_path="m.pt")


def _diagram(placement: str) -> RecognizedDiagram:
    """Um diagrama minimo. O cache nao le nada dele alem dos marcadores de edicao."""
    return RecognizedDiagram.from_label(np.zeros((8, 8, 3), dtype=np.uint8), placement)


def _results(page: int, count: int = 3, *, params: PageOcrParams = PARAMS, hand: bool = False) -> PageResults:
    itens = [_diagram(f"p{page}d{i}") for i in range(count)]
    if hand and itens:
        itens[0].edited_by_hand = True
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
            PageResults(page_index=1, params=PARAMS, items=[_diagram("a"), _diagram("b")], fen_edits=["a"], side_edits=["w", "b"])

    def test_hand_edits_are_detected_from_either_marker(self) -> None:
        self.assertFalse(_results(1).has_hand_edits)
        self.assertTrue(_results(1, hand=True).has_hand_edits)

        pelo_lado = _results(1)
        pelo_lado.items[1].side_to_move_source = "manual"
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

    def test_a_page_with_hand_edits_survives_the_limit(self) -> None:
        """OCR_UI C2, A7: a 9.a pagina lida nao expulsa a 1.a com a correcao dentro. Quem sai e a
        leitura do modelo mais antiga sem edicao -- a 2.a -- e a 1.a continua no cache."""
        cache = PageResultsCache(max_pages=DEFAULT_MAX_CACHED_PAGES)
        cache.put(DOC, _results(1, hand=True))
        for page in range(2, 10):
            cache.put(DOC, _results(page))
        self.assertLessEqual(len(cache), DEFAULT_MAX_CACHED_PAGES)
        self.assertIsNotNone(cache.get(DOC, 1, PARAMS), "a pagina corrigida a mao saiu do cache")
        self.assertIsNone(cache.get(DOC, 2, PARAMS), "a leitura sem edicao mais antiga e a que sai")
        self.assertEqual(cache.pages_with_hand_edits(DOC), [1])

    @pytest.mark.xfail(strict=True, reason="o comportamento antigo (A7): a LRU expulsava a pagina editada")
    def test_sabotagem_the_oldest_page_is_evicted_even_with_hand_edits(self) -> None:
        cache = PageResultsCache(max_pages=DEFAULT_MAX_CACHED_PAGES)
        cache.put(DOC, _results(1, hand=True))
        for page in range(2, 10):
            cache.put(DOC, _results(page))
        self.assertIsNone(cache.get(DOC, 1, PARAMS))

    def test_when_every_page_is_hand_edited_none_is_evicted_and_it_is_logged(self) -> None:
        """Perder leitura do modelo custa rodar o OCR; perder correcao custa o trabalho. Se toda
        pagina guardada tem correcao, o cache passa do teto -- e diz isso no log."""
        cache = PageResultsCache(max_pages=1)
        cache.put(DOC, _results(1, hand=True))
        with self.assertLogs("chess_diagram_ocr.ui.page_results", level="WARNING") as capturado:
            cache.put(DOC, _results(2, hand=True))
        self.assertIn("teto", "\n".join(capturado.output))
        self.assertEqual(len(cache), 2)
        self.assertEqual(cache.pages_with_hand_edits(), [1, 2])

    def test_the_page_just_stored_is_never_the_one_evicted(self) -> None:
        """E a pagina de que a pessoa acabou de sair: descarta-la faria a volta custar um OCR."""
        cache = PageResultsCache(max_pages=1)
        cache.put(DOC, _results(1, hand=True))
        cache.put(DOC, _results(2))
        self.assertIsNotNone(cache.get(DOC, 2, PARAMS))
        self.assertIsNotNone(cache.get(DOC, 1, PARAMS))

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


class PaginasEditadasTests(unittest.TestCase):
    """O que a janela pergunta antes de fechar e antes de trocar de livro (A7)."""

    class _Modelo:
        def __init__(self, page_key: tuple[str, int] | None, edits: bool) -> None:
            self.page_key = page_key
            self.has_hand_edits = edits
            self.has_unsaved_hand_edits = edits  # a pergunta é sobre o que não foi gravado

    def test_junta_o_cache_e_a_pagina_que_esta_no_editor(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(3, hand=True))
        cache.put(DOC, _results(4))
        editor = self._Modelo((DOC, 7), True)
        self.assertEqual(paginas_editadas(cache, editor), [3, 7])

    def test_o_editor_sem_edicao_ou_sem_pagina_nao_conta(self) -> None:
        cache = PageResultsCache()
        self.assertEqual(paginas_editadas(cache, self._Modelo((DOC, 7), False)), [])
        self.assertEqual(paginas_editadas(cache, self._Modelo(None, True)), [])

    def test_uma_correcao_gravada_nao_conta(self) -> None:
        """Crítico (fase 1, ciclo 1): a página com correção **gravada** não se perde ao fechar."""
        cache = PageResultsCache()
        gravada = _results(3, hand=True)
        for item, fen, side in zip(gravada.items, gravada.fen_edits, gravada.side_edits, strict=False):
            item.saved_placement, item.saved_side = fen, side
        cache.put(DOC, gravada)
        cache.put(DOC, _results(4, hand=True))
        self.assertEqual(paginas_editadas(cache, self._Modelo(None, False)), [4])
        gravada.fen_edits[0] = "8/8/8/8/8/8/8/K6k"  # editada de novo depois de gravar
        self.assertEqual(paginas_editadas(cache, self._Modelo(None, False)), [3, 4])

    def test_filtra_pelo_livro(self) -> None:
        cache = PageResultsCache()
        cache.put(DOC, _results(3, hand=True))
        cache.put("outro.pdf", _results(5, hand=True))
        editor = self._Modelo(("outro.pdf", 9), True)
        self.assertEqual(paginas_editadas(cache, editor, DOC), [3])
        self.assertEqual(paginas_editadas(cache, editor, "outro.pdf"), [5, 9])
        self.assertEqual(paginas_editadas(cache, editor), [3, 5, 9])


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


# `OriginParsingTests` mudou de casa junto com a funcao: a interpretacao da origem virou
# `service.RecognitionOrigin` na S-31, e os casos estao em `tests/test_service.py`.


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
