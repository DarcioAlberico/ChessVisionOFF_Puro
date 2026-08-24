"""O aumento de dados dirigido ao glifo, e a transformação que **não** pode entrar (S-204).

O módulo de peças tem oito degradações e a mais barata delas é o espelhamento horizontal — lá
válido, porque um cavalo espelhado continua sendo um cavalo. Aqui um `b` espelhado é um `d`, e é
por isso que este módulo existe em vez de reusar aquele.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text import aumento


def _lote(n: int = 32, valor: int = 90) -> np.ndarray:
    """Papel claro com um traço escuro no meio: dá para ver se alguma coisa mexeu nele."""
    imagem = np.full((32, 32), 230, np.uint8)
    imagem[8:24, 14:18] = valor
    return np.tile(imagem.reshape(1, -1), (n, 1))


class ConfigTests(unittest.TestCase):
    def test_o_desligado_devolve_o_lote_como_veio(self) -> None:
        lote = _lote()
        saida = aumento.aplicar(lote, np.random.default_rng(0), aumento.DESLIGADO)
        np.testing.assert_array_equal(lote, saida)

    def test_a_versao_separa_os_dois_regimes(self) -> None:
        """As letras sozinhas empatam `leve` e `forte`: eles ligam as mesmas sete degradações.

        Uma identidade que empata dois regimes é pior que nenhuma — ela faz a tabela da grade
        dizer que comparou dois braços iguais.
        """
        self.assertNotEqual(aumento.LEVE.versao, aumento.FORTE.versao)
        self.assertEqual("tex0", aumento.DESLIGADO.versao)

    def test_o_nome_errado_levanta_em_vez_de_cair_no_padrao(self) -> None:
        with self.assertRaises(ValueError):
            aumento.de_nome("medio")

    def test_os_tres_nomes_da_grade_existem(self) -> None:
        for nome in ("desligado", "leve", "forte"):
            with self.subTest(nome=nome):
                self.assertIsInstance(aumento.de_nome(nome), aumento.Config)


class AplicarTests(unittest.TestCase):
    def test_o_lote_original_nao_e_tocado(self) -> None:
        """`X` é a base inteira em RAM: degradar no lugar apagaria o disco dentro da memória."""
        lote = _lote()
        copia = lote.copy()
        aumento.aplicar(lote, np.random.default_rng(0), aumento.FORTE)
        np.testing.assert_array_equal(copia, lote)

    def test_parte_do_lote_passa_intacta(self) -> None:
        """O modelo precisa ver a imagem limpa: é o que a inferência lhe dá na maioria das páginas."""
        lote = _lote(n=200)
        saida = aumento.aplicar(lote, np.random.default_rng(1), aumento.LEVE)
        mudaram = (saida != lote).any(axis=1).sum()
        self.assertGreater(mudaram, 0)
        self.assertLess(mudaram, 200)

    def test_a_saida_continua_sendo_tinta_escura_sobre_papel_claro(self) -> None:
        """A polaridade é a do disco, e o classificador foi treinado nela (`modelo._entrada`)."""
        saida = aumento.aplicar(_lote(n=64), np.random.default_rng(2), aumento.FORTE)
        for recorte in saida.reshape(-1, 32, 32):
            with self.subTest():
                self.assertGreater(recorte.mean(), 128, "o papel tem de continuar mais claro que a tinta")

    def test_a_forma_e_o_tipo_sobrevivem(self) -> None:
        lote = _lote(n=16)
        saida = aumento.aplicar(lote, np.random.default_rng(3), aumento.FORTE)
        self.assertEqual(lote.shape, saida.shape)
        self.assertEqual(np.uint8, saida.dtype)

    def test_lote_vazio_nao_derruba(self) -> None:
        vazio = np.empty((0, 1024), np.uint8)
        np.testing.assert_array_equal(vazio, aumento.aplicar(vazio, np.random.default_rng(0), aumento.LEVE))

    def test_a_mesma_semente_da_o_mesmo_aumento(self) -> None:
        lote = _lote(n=64)
        um = aumento.aplicar(lote, np.random.default_rng(7), aumento.LEVE)
        outro = aumento.aplicar(lote, np.random.default_rng(7), aumento.LEVE)
        np.testing.assert_array_equal(um, outro)


class EspelhoTests(unittest.TestCase):
    """**A transformação que não entra**, e o teste existe para que ela não volte por engano."""

    def test_nenhuma_degradacao_espelha_o_recorte(self) -> None:
        """Um `b` espelhado é um `d`, e os pares que ele confundiria são os da S-202.

        A prova é assimétrica de propósito: um traço fora do centro tem de continuar do mesmo
        lado depois de mil aumentos.
        """
        imagem = np.full((32, 32), 230, np.uint8)
        imagem[4:28, 4:10] = 20  # tinta encostada na **esquerda**
        lote = np.tile(imagem.reshape(1, -1), (500, 1))

        saida = aumento.aplicar(lote, np.random.default_rng(11), aumento.FORTE).reshape(-1, 32, 32)

        esquerda = saida[:, :, :16].astype(np.int32).sum(axis=(1, 2))
        direita = saida[:, :, 16:].astype(np.int32).sum(axis=(1, 2))
        self.assertTrue(
            bool((esquerda < direita).all()),
            "algum recorte saiu com a tinta do lado errado: alguma degradação está espelhando",
        )

    def test_o_modulo_nao_chama_flip_nem_transpose(self) -> None:
        """A varredura é do código, via `ast`: o cabeçalho cita o espelhamento para proibi-lo."""
        import ast
        from pathlib import Path

        arvore = ast.parse(Path(aumento.__file__).read_text(encoding="utf-8"))
        chamados = {no.attr for no in ast.walk(arvore) if isinstance(no, ast.Attribute)}
        for proibida in ("flip", "fliplr", "flipud", "transpose", "rot90"):
            with self.subTest(proibida=proibida):
                self.assertNotIn(proibida, chamados)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
