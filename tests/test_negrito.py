"""O negrito vem da camada, e nunca da imagem (S-211).

O teste que carrega este arquivo é o do **desconhecido**: um livro cuja camada não registra peso
não pode declarar que nada ali é negrito. `None` e `False` são respostas diferentes, e confundi-las
seria afirmar o que ninguém mediu.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text import negrito as ng

LINHA = (10.0, 100.0, 110.0, 112.0)


class FonteTests(unittest.TestCase):
    def test_o_nome_da_fonte_denuncia_o_peso(self) -> None:
        for nome in ("Times-Bold", "Calibri-Black", "Helvetica-SemiBold", "Arial-Heavy", "X-Demi"):
            with self.subTest(nome=nome):
                self.assertTrue(ng._span_e_negrito({"font": nome}))

    def test_a_fonte_normal_nao(self) -> None:
        for nome in ("TimesNewRomanPSMT", "Calibri", "Chess-Merida", "SemFigNormal"):
            with self.subTest(nome=nome):
                self.assertFalse(ng._span_e_negrito({"font": nome}))

    def test_o_bit_vale_sem_o_nome(self) -> None:
        """Há PDF com o bit e sem o nome, e vice-versa -- por isso os dois."""
        self.assertTrue(ng._span_e_negrito({"font": "Calibri", "flags": ng.BIT_DE_NEGRITO}))


class CoberturaTests(unittest.TestCase):
    def test_a_linha_inteira_coberta(self) -> None:
        self.assertAlmostEqual(ng.cobertura(LINHA, [(10, 100, 110, 112)]), 1.0)

    def test_a_fracao_e_de_largura(self) -> None:
        self.assertAlmostEqual(ng.cobertura(LINHA, [(10, 100, 40, 112)]), 0.30)

    def test_dois_spans_sobrepostos_nao_contam_duas_vezes(self) -> None:
        """Sem a união, uma linha poderia cobrir mais que 100% de si mesma."""
        self.assertAlmostEqual(ng.cobertura(LINHA, [(10, 100, 60, 112), (40, 100, 80, 112)]), 0.70)

    def test_dois_spans_separados_somam(self) -> None:
        self.assertAlmostEqual(ng.cobertura(LINHA, [(10, 100, 30, 112), (90, 100, 110, 112)]), 0.40)

    def test_o_span_de_outra_linha_nao_conta(self) -> None:
        self.assertAlmostEqual(ng.cobertura(LINHA, [(10, 200, 110, 212)]), 0.0)

    def test_linha_sem_largura_nao_estoura(self) -> None:
        self.assertAlmostEqual(ng.cobertura((10.0, 100.0, 10.0, 112.0), [(0, 90, 200, 120)]), 0.0)


class MarcarTests(unittest.TestCase):
    def test_o_documento_que_nao_registra_devolve_desconhecido(self) -> None:
        """**É o teste principal.** `False` ali seria afirmar que nada é negrito."""
        self.assertEqual(ng.marcar([LINHA], [(10, 100, 110, 112)], registra=False), [None])

    def test_o_documento_que_registra_responde_sim_ou_nao(self) -> None:
        self.assertEqual(ng.marcar([LINHA], [(10, 100, 110, 112)], registra=True), [True])
        self.assertEqual(ng.marcar([LINHA], [], registra=True), [False])

    def test_a_maioria_decide_a_linha(self) -> None:
        """Uma linha de prosa com **um** lance em negrito não é uma linha em negrito."""
        self.assertEqual(ng.marcar([LINHA], [(10, 100, 40, 112)], registra=True), [False])
        self.assertEqual(ng.marcar([LINHA], [(10, 100, 90, 112)], registra=True), [True])

    def test_sem_linha_nenhuma_devolve_vazio(self) -> None:
        self.assertEqual(ng.marcar([], [], registra=True), [])


class ModeloTests(unittest.TestCase):
    """O que o `PaginaLida` faz com o peso: herança pelo bloco, e ida-e-volta."""

    def _linha(self, texto: str, peso: bool | None):
        from chess_diagram_ocr.text.pagina import LinhaLida

        return LinhaLida(texto, (0.0, 0.0, 10.0, 10.0), 1.0, "camada", peso)

    def test_o_bloco_so_e_negrito_se_todas_as_linhas_forem(self) -> None:
        from chess_diagram_ocr.text.pagina import BlocoDeTexto

        casos = (
            ((True, True), True),
            ((False, False), False),
            ((True, False), None),
            ((True, None), None),
            ((None, None), None),
        )
        for pesos, esperado in casos:
            with self.subTest(pesos=pesos):
                linhas = [self._linha(f"l{i}", p) for i, p in enumerate(pesos)]
                self.assertIs(BlocoDeTexto.de_linhas(linhas).negrito, esperado)

    def test_o_peso_sobrevive_a_ida_e_volta(self) -> None:
        import json

        from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, PaginaLida

        pagina = PaginaLida(
            colunas=(Coluna(blocos=(BlocoDeTexto.de_linhas([self._linha("x", True)]),)),)
        )
        volta = PaginaLida.de_json(json.loads(json.dumps(pagina.para_json())))
        self.assertEqual(volta, pagina)

    def test_o_arquivo_antigo_sem_o_campo_vira_desconhecido(self) -> None:
        """Campo ausente é exatamente o que um arquivo gravado antes dele sabe: nada."""
        from chess_diagram_ocr.text.pagina import LinhaLida

        linha = LinhaLida.de_json(
            {"texto": "x", "bbox": [0, 0, 1, 1], "confianca": 1.0, "procedencia": "camada"}
        )
        self.assertIsNone(linha.negrito)

    def test_um_negrito_que_nao_e_booleano_recusa(self) -> None:
        from chess_diagram_ocr.text.pagina import LinhaLida, PaginaInvalida

        with self.assertRaises(PaginaInvalida):
            LinhaLida.de_json(
                {"texto": "x", "bbox": [0, 0, 1, 1], "confianca": 1.0,
                 "procedencia": "camada", "negrito": "sim"}
            )

    def test_o_editor_desenha_desconhecido_como_normal(self) -> None:
        """A tela tem dois estados, não três -- e "não se sabe" cai no lado seguro."""
        from chess_diagram_ocr.text import documento
        from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, PaginaLida

        for peso, esperado in ((True, True), (False, False), (None, False)):
            with self.subTest(peso=peso):
                bloco = BlocoDeTexto.de_linhas([self._linha("x", peso)])
                pagina = PaginaLida(colunas=(Coluna(blocos=(bloco,)),))
                segmento = next(iter(documento.segmentos(pagina)))
                self.assertIs(segmento.negrito, esperado)


class EstadoNaTelaTests(unittest.TestCase):
    """"Nada em negrito" e "o livro não informa" não podem parecer a mesma coisa.

    O segundo caso é a **maioria** -- 28 dos 41 livros do acervo --, e sem a frase quem abre um
    deles conclui que a função está quebrada. Foi o que aconteceu com o `A Matter of Endgame
    Technique`, cuja camada escreve o livro inteiro numa fonte só.
    """

    def _pagina(self, *pesos: bool | None):
        from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

        blocos = tuple(
            BlocoDeTexto.de_linhas(
                [LinhaLida(f"l{i}", (0.0, 0.0, 10.0, 10.0), 1.0, "glifo", p)]
            )
            for i, p in enumerate(pesos)
        )
        return PaginaLida(colunas=(Coluna(blocos=blocos),))

    def test_o_livro_que_nao_informa_diz_isso(self) -> None:
        from chess_diagram_ocr.text import documento

        self.assertEqual(
            documento.estado_do_negrito(self._pagina(None, None)), "negrito: o livro não informa"
        )

    def test_o_livro_que_informa_e_nao_tem_negrito_diz_outra_coisa(self) -> None:
        from chess_diagram_ocr.text import documento

        self.assertEqual(documento.estado_do_negrito(self._pagina(False, False)), "nada em negrito")

    def test_o_que_tem_negrito_conta(self) -> None:
        from chess_diagram_ocr.text import documento

        self.assertEqual(documento.estado_do_negrito(self._pagina(True, False, True)), "2 em negrito")

    def test_a_pagina_vazia_nao_estoura(self) -> None:
        from chess_diagram_ocr.text import documento
        from chess_diagram_ocr.text.pagina import PaginaLida

        self.assertEqual(
            documento.estado_do_negrito(PaginaLida()), "negrito: o livro não informa"
        )

    def test_a_frase_entra_no_resumo_da_aba(self) -> None:
        from chess_diagram_ocr.text import documento

        self.assertIn("o livro não informa", documento.resumo(self._pagina(None)))
        self.assertIn("1 em negrito", documento.resumo(self._pagina(True)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
