"""O que uma variante dobrada esconde, e o que ela não pode esconder (S-516).

Puro, sem janela: a decisão inteira do dobrar é *quais trechos somem*. Desenhar o `(…)` é do
widget, e está em `tests/test_qt_painel_de_estudo.py`.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.estudo import Estudo
from chess_diagram_ocr.ui import estudo_dobra, estudo_lista

PGN = (
    '[Event "?"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 (3... Nf6 4. O-O Nxe4 5. d4 '
    "(5. Re1 Nd6 6. Nxe5 Be7) 5... Nd6 6. Bxc6 dxc6) 4. Ba4 Nf6 *\n"
)


def _estudo() -> Estudo:
    novo = Estudo.de_pgn(PGN, documento="livro.pdf")
    assert novo is not None
    return novo


class VariantesTests(unittest.TestCase):
    """Achar os `( ... )` da lista, e saber o que há dentro de cada um."""

    def setUp(self) -> None:
        self.trechos = estudo_lista.trechos(_estudo())
        self.achadas = estudo_dobra.variantes(self.trechos)

    def test_acha_a_variante_e_a_subvariante(self) -> None:
        self.assertEqual(2, len(self.achadas))

    def test_a_chave_e_o_caminho_do_primeiro_lance(self) -> None:
        """**Caminho e não índice**: promover ou apagar variante reordena as irmãs, e uma dobra
        guardada por índice mudaria de dona no gesto seguinte (a armadilha da S-268)."""
        for variante in self.achadas:
            with self.subTest(abre=variante.abre):
                primeiro = next(
                    t for t in self.trechos[variante.abre + 1 :] if t.caminho is not None
                )
                self.assertEqual(primeiro.caminho, variante.chave)

    def test_a_de_fora_contem_os_caminhos_da_de_dentro(self) -> None:
        """É o que responde "o corrente está aqui?" sem percorrer a lista de novo."""
        interna, externa = sorted(self.achadas, key=lambda v: v.fecha - v.abre)
        self.assertTrue(interna.caminhos < externa.caminhos)

    def test_os_parenteses_delimitam_a_variante(self) -> None:
        for variante in self.achadas:
            with self.subTest(abre=variante.abre):
                self.assertEqual(estudo_lista.ABRE, self.trechos[variante.abre].papel)
                self.assertEqual(estudo_lista.FECHA, self.trechos[variante.fecha].papel)

    def test_lista_sem_variante_nao_acha_nada(self) -> None:
        so_principal = Estudo.de_pgn('[Event "?"]\n\n1. e4 e5 *\n', documento="livro.pdf")
        assert so_principal is not None
        self.assertEqual((), estudo_dobra.variantes(estudo_lista.trechos(so_principal)))


class EscondidosTests(unittest.TestCase):
    """O que some, e o que **não** pode sumir."""

    def setUp(self) -> None:
        self.trechos = estudo_lista.trechos(_estudo())
        self.achadas = estudo_dobra.variantes(self.trechos)
        self.externa = max(self.achadas, key=lambda v: v.fecha - v.abre)
        self.interna = min(self.achadas, key=lambda v: v.fecha - v.abre)

    def test_sem_dobra_nada_some(self) -> None:
        self.assertEqual(frozenset(), estudo_dobra.escondidos(self.trechos, ()))

    def test_dobrar_esconde_o_miolo_e_deixa_os_parenteses(self) -> None:
        """Uma variante que sumisse inteira não diria que existe, e desdobrá-la não teria onde
        acontecer."""
        ocultos = estudo_dobra.escondidos(self.trechos, [self.externa.chave])
        self.assertNotIn(self.externa.abre, ocultos)
        self.assertNotIn(self.externa.fecha, ocultos)
        self.assertIn(self.externa.abre + 1, ocultos)

    def test_dobrar_a_de_fora_leva_a_de_dentro_junto(self) -> None:
        ocultos = estudo_dobra.escondidos(self.trechos, [self.externa.chave])
        self.assertIn(self.interna.abre, ocultos)
        self.assertIn(self.interna.fecha, ocultos)

    def test_a_dobra_que_contem_o_corrente_nao_e_aplicada(self) -> None:
        """**O item que impede a lista de perder a pessoa.** Uma dobra que engolisse o nó em que
        se está deixaria o tabuleiro mostrando uma posição que a lista não tem."""
        dentro = next(iter(sorted(self.externa.caminhos)))
        ocultos = estudo_dobra.escondidos(self.trechos, [self.externa.chave], dentro)
        self.assertEqual(frozenset(), ocultos)

    def test_a_dobra_de_fora_cai_e_a_de_dentro_continua(self) -> None:
        """Ela é ignorada uma a uma, e não em bloco: estar dentro da externa não abre a interna."""
        so_da_externa = sorted(self.externa.caminhos - self.interna.caminhos)[0]
        ocultos = estudo_dobra.escondidos(
            self.trechos, [self.externa.chave, self.interna.chave], so_da_externa
        )
        self.assertIn(self.interna.abre + 1, ocultos, "a subvariante deixou de estar dobrada")
        self.assertNotIn(self.externa.abre + 1, ocultos, "a de fora escondeu o corrente")

    def test_a_dobra_continua_declarada_quando_nao_e_aplicada(self) -> None:
        """Sair dali com a seta devolve o que a pessoa pediu, sem ela pedir de novo -- e é por
        isso que `escondidos` não mexe na lista de dobradas."""
        dentro = next(iter(sorted(self.externa.caminhos)))
        dobradas = [self.externa.chave]
        estudo_dobra.escondidos(self.trechos, dobradas, dentro)
        self.assertEqual(frozenset(), estudo_dobra.escondidos(self.trechos, dobradas, ()) & frozenset())
        self.assertIn(self.externa.abre + 1, estudo_dobra.escondidos(self.trechos, dobradas, ()))

    def test_caminho_que_nao_existe_mais_nao_dobra_nada(self) -> None:
        """Degradação certa para estado de vista: a dobra some com o lance que a nomeava."""
        self.assertEqual(frozenset(), estudo_dobra.escondidos(self.trechos, [(9, 9, 9)]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
