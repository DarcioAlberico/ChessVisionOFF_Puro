"""A pilha de desfazer guarda o que quem chama disser que é o estado (S-229; OCR_UI C2, A7).

Era uma pilha de `str`, e o painel de Resultado punha só o `placement`: trocar o lado a jogar não
entrava, e `Ctrl+Z` depois de um clique no rádio errado devolvia a peça de trás em vez do lado de
trás (análise §6.5). Agora o estado é qualquer valor comparável por `==` -- o painel põe
`(placement, side)`, a sala de estudo continua pondo o PGN como texto.
"""

from __future__ import annotations

import unittest

import pytest

from chess_diagram_ocr.ui.historico import TETO, Historico

A = "4k3/8/8/8/8/8/8/4K3"
B = "8/8/8/4k3/8/8/8/4K3"


class PilhaDeTextoTests(unittest.TestCase):
    """O contrato de antes continua valendo para quem guarda texto (a sala de estudo)."""

    def test_registrar_desfazer_refazer(self) -> None:
        pilha: Historico[str] = Historico(A)
        self.assertTrue(pilha.registrar(B))
        self.assertEqual(pilha.desfazer(), A)
        self.assertEqual(pilha.refazer(), B)
        self.assertIsNone(pilha.refazer())

    def test_a_posicao_que_nao_mudou_nao_entra(self) -> None:
        pilha: Historico[str] = Historico(A)
        self.assertFalse(pilha.registrar(A))
        self.assertFalse(pilha.pode_desfazer)

    def test_o_teto_descarta_o_mais_antigo(self) -> None:
        pilha: Historico[str] = Historico("0", teto=3)
        for i in range(1, 6):
            pilha.registrar(str(i))
        self.assertEqual(pilha.profundidade, 3)
        self.assertEqual([pilha.desfazer() for _ in range(3)], ["4", "3", "2"])
        self.assertIsNone(pilha.desfazer())

    def test_o_teto_padrao_e_o_declarado(self) -> None:
        self.assertEqual(TETO, 100)
        with self.assertRaises(ValueError):
            Historico("", teto=0)


class PilhaDeEstadosTests(unittest.TestCase):
    """O estado do painel de Resultado: `(placement, side)` (A7)."""

    def test_trocar_so_o_lado_entra_na_pilha_e_volta(self) -> None:
        pilha: Historico[tuple[str, str]] = Historico((A, "w"))
        self.assertTrue(pilha.registrar((A, "b")), "o lado mudou: é um estado novo")
        self.assertEqual(pilha.desfazer(), (A, "w"))
        self.assertEqual(pilha.refazer(), (A, "b"))

    def test_a_igualdade_e_da_tupla_inteira(self) -> None:
        pilha: Historico[tuple[str, str]] = Historico((A, "w"))
        self.assertFalse(pilha.registrar((A, "w")))
        self.assertTrue(pilha.registrar((B, "w")))
        self.assertTrue(pilha.registrar((B, "b")))
        self.assertEqual(pilha.profundidade, 2)

    def test_zerar_recomeca_no_estado_dado(self) -> None:
        pilha: Historico[tuple[str, str]] = Historico((A, "w"))
        pilha.registrar((B, "b"))
        pilha.zerar((A, "b"))
        self.assertEqual(pilha.atual, (A, "b"))
        self.assertFalse(pilha.pode_desfazer)
        self.assertFalse(pilha.pode_refazer)

    def test_o_valor_nao_e_coagido_a_texto(self) -> None:
        """A sabotagem de A7 seria o `str()` de antes: a tupla viraria `"('...', 'w')"` e o
        `desfazer` devolveria um texto que nenhum tabuleiro entende."""
        pilha: Historico[tuple[str, str]] = Historico((A, "w"))
        pilha.registrar((B, "b"))
        anterior = pilha.desfazer()
        self.assertIsInstance(anterior, tuple)
        self.assertEqual(anterior, (A, "w"))


@pytest.mark.xfail(strict=True, reason="o comportamento antigo (A7): o lado não entrava na pilha")
def test_sabotagem_trocar_o_lado_nao_entrava_na_pilha() -> None:
    """O teste invertido: com a pilha só de `placement`, trocar o lado não registrava nada."""
    pilha: Historico[tuple[str, str]] = Historico((A, "w"))
    pilha.registrar((A, "b"))
    assert not pilha.pode_desfazer


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
