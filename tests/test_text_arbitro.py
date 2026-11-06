"""O árbitro de notação: gramática, continuidade e legalidade (S-729), e o dígito de estilo antigo (S-743)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest import mock

import chess

from chess_diagram_ocr.text import arbitro, fusao


def nao_existe(_token: str) -> bool:
    return False


def existe_das(token: str) -> bool:
    return token.strip(".,;:!?").casefold() in {"das", "and", "tel"}


def do_leitor(*textos: str) -> list[fusao.Token]:
    return [fusao.Token(t, "outro", "", None, t) for t in textos]


def arbitrada(*textos: str, existe=nao_existe, **opcoes) -> list[str]:  # type: ignore[no-untyped-def]
    (linha,) = arbitro.arbitrar([do_leitor(*textos)], existe=existe, **opcoes)
    return [t.texto for t in linha]


class GramaticaTests(unittest.TestCase):
    def test_o_que_e_lance_e_o_que_nao_e(self) -> None:
        for token in ("Dh5", "Sg1-f3", "1...e5", "e4", "P4R", "C3AR", "17.Kxf3+", "♘f3", "...♖xh4?", "O-O", "Lb4t,"):
            with self.subTest(token=token):
                self.assertTrue(arbitro.e_estrita(token))
        for token in ("Dhs", "ABR", "8h6", "the", "Sgl-f3", "e4x"):
            with self.subTest(token=token):
                self.assertFalse(arbitro.e_estrita(token))

    def test_a_notacao_longa_nao_precisa_de_contexto(self) -> None:
        """No *Bachmann*: `Tgı-g2`, `Sbı-cg`, `Tdy-f7`, `Seö-f3`. Duas casas com traço entre elas não são outra coisa."""
        for lido, certo in (("Tgı-g2", "Tg1-g2"), ("Sbı-cg", "Sb1-c3"), ("h2-hg", "h2-h3"), ("Tdy-f7", "Td7-f7"), ("Seö—f3", "Se5—f3"), ("Sf3xeb", "Sf3xe6")):
            with self.subTest(lido=lido):
                self.assertEqual([certo], arbitrada(lido))

    def test_o_numero_colado_vem_junto(self) -> None:
        self.assertEqual(["10.Dh5"], arbitrada("Io.Dhs"))
        self.assertEqual(["11.f2-f3"], arbitrada("ıı.f2-f3"))
        self.assertEqual(["1.d2-d4"], arbitrada("I.d2-d4"))

    def test_o_numero_solto_com_i_sem_ponto_e_sempre_numero(self) -> None:
        # `ı` não é letra de nenhuma das línguas do acervo fora do turco, e não há livro em turco.
        self.assertEqual(["Aus", "dem", "10.", "Gang"], arbitrada("Aus", "dem", "ıo.", "Gang"))

    def test_o_numero_solto_sem_lance_adiante_fica(self) -> None:
        self.assertEqual(["Jahr", "Io.", "Gang"], arbitrada("Jahr", "Io.", "Gang"))

    def test_abreviatura_antes_de_lance_nao_vira_numero(self) -> None:
        """`A. B. Keres`, com lance adiante: `B.` só é `8.` com `7.` ou `9.` por perto."""
        self.assertEqual(["B.", "Sg1-f3"], arbitrada("B.", "Sg1-f3"))
        self.assertEqual(["7.", "e4", "8.", "Sg1-f3"], arbitrada("7.", "e4", "B.", "Sg1-f3"))

    def test_a_curta_precisa_de_vizinho_de_notacao(self) -> None:
        self.assertEqual(["12.", "Dh5"], arbitrada("12.", "Dhs"))
        self.assertEqual(["viu", "Dhs", "ontem"], arbitrada("viu", "Dhs", "ontem"))

    def test_a_palavra_que_existe_so_cai_entre_dois_lances(self) -> None:
        self.assertEqual(["viu", "Das", "ontem"], arbitrada("viu", "Das", "ontem", existe=existe_das))
        self.assertEqual(["12.", "e4", "Da5", "13.", "e5"], arbitrada("12.", "e4", "Das", "13.", "e5", existe=existe_das))

    def test_o_peao_so_entre_lances(self) -> None:
        self.assertEqual(["1.", "e4", "e5", "2.", "f4"], arbitrada("1.", "e4", "es", "2.", "f4"))
        self.assertEqual(["vem", "es", "aqui"], arbitrada("vem", "es", "aqui"))

    def test_a_descritiva_das_linguas_latinas(self) -> None:
        """`R1D` -> `RID` e `P5C` -> `PSC`, a saída da S-729."""
        self.assertEqual(["1.", "R1D", "P5C", "2."], arbitrada("1.", "RID", "PSC", "2."))

    def test_o_interruptor_de_digito_e_a_constante_da_s743(self) -> None:
        with mock.patch.object(arbitro, "DIGITO_FORCADO", False):
            self.assertEqual(["Tgı-g2"], arbitrada("Tgı-g2"))

    def test_o_interruptor_do_arbitro_devolve_as_regras_de_forma(self) -> None:
        with mock.patch.object(arbitro, "GRAMATICA", False):
            self.assertEqual(["Tgı-g2"], arbitrada("Tgı-g2"))

    def test_o_cirilico_so_sob_a_gramatica(self) -> None:
        self.assertEqual(["10.", "Bxe4"], arbitrada("10.", "Вхе4"))
        self.assertEqual(["Этот", "Вхе", "ход"], arbitrada("Этот", "Вхе", "ход"))


class OutraLeituraTests(unittest.TestCase):
    def linha(self, texto: str, do_glifo: str) -> list[str]:
        (saida,) = arbitro.arbitrar([[fusao.Token(texto, "outro", do_glifo, None, texto)]], existe=nao_existe)
        return [t.texto for t in saida]

    def test_a_outra_e_lance_e_esta_nao(self) -> None:
        self.assertEqual(["A3R"], self.linha("ABR", "A3R"))

    def test_o_digito_forcado_vem_antes_da_outra_leitura(self) -> None:
        # `Tel,` é `Te1,`: o glifo leu `Tc1`, e no scan a letra do Tesseract é a melhor das duas.
        (saida,) = arbitro.arbitrar(
            [[fusao.Token("12.", "outro", "12.", None, "12."), fusao.Token("Tel,", "outro", "Tc1", None, "Tel,")]], existe=nao_existe
        )
        self.assertEqual(["12.", "Te1,"], [t.texto for t in saida])

    def test_leituras_que_nao_sao_da_mesma_tinta_nao_trocam(self) -> None:
        self.assertEqual(["ins"], self.linha("ins", "h8"))
        self.assertEqual(["Dro-"], self.linha("Dro-", "Df6"))

    def test_figurina_nunca_e_trocada_por_letra(self) -> None:
        (saida,) = arbitro.arbitrar([[fusao.Token("♖g", "glifo", "♖g", None, "Bg4")]], existe=nao_existe)
        self.assertEqual(["♖g"], [t.texto for t in saida])

    def test_o_numero_que_faltava_vem_e_a_figurina_fica(self) -> None:
        (saida,) = arbitro.arbitrar([[fusao.Token(".♖g6!", "glifo", ".♖g6!", None, "1.2g6!")]], existe=nao_existe)
        self.assertEqual(["1.♖g6!"], [t.texto for t in saida])

    def test_o_numero_partido_pelo_glifo_nao_duplica(self) -> None:
        tokens = [fusao.Token("1", "glifo", "1"), fusao.Token("1", "glifo", "1"), fusao.Token("...♖xh4?", "glifo", "...♖xh4?", None, "11...2xh4?")]
        (saida,) = arbitro.arbitrar([tokens], existe=nao_existe)
        self.assertEqual(["11...♖xh4?"], [t.texto for t in saida])

    def test_os_dois_pedacos_nao_viram_tres(self) -> None:
        tokens = [fusao.Token("Db6x", "outro", "Db6xb2", None, "Db6x"), fusao.Token("b2", "outro", "", None, "b2")]
        (saida,) = arbitro.arbitrar([tokens], existe=nao_existe)
        self.assertEqual(["Db6x", "b2"], [t.texto for t in saida])


class ContinuidadeTests(unittest.TestCase):
    def test_o_numero_que_continua_vence_a_regra_de_forma(self) -> None:
        tokens = [fusao.Token("26.♘f3", "glifo", "26.♘f3"), fusao.Token("21.♖f3", "glifo", "21.♖f3", None, "27.Hf3"), fusao.Token("28.♘e5", "glifo", "28.♘e5")]
        (saida,) = arbitro.arbitrar([tokens], existe=nao_existe)
        self.assertEqual("27.♖f3", saida[1].texto)

    def test_sem_vizinho_que_diga_fica_o_que_estava(self) -> None:
        (saida,) = arbitro.arbitrar([[fusao.Token("21.♖f3", "glifo", "21.♖f3", None, "27.Hf3")]], existe=nao_existe)
        self.assertEqual("21.♖f3", saida[0].texto)

    def test_a_linha_seguinte_conta(self) -> None:
        l1 = [fusao.Token("26.♘f3", "glifo", "26.♘f3")]
        l2 = [fusao.Token("21.♖f3", "glifo", "21.♖f3", None, "27.Hf3")]
        (_a, b) = arbitro.arbitrar([l1, l2], existe=nao_existe)
        self.assertEqual("27.♖f3", b[0].texto)


class LegalidadeTests(unittest.TestCase):
    def _posicoes(self, fen: str) -> list[tuple[int, chess.Board]]:
        return [(0, chess.Board(fen))]

    def test_a_leitura_legal_vence_a_ilegal(self) -> None:
        relato = arbitro.Relato()
        # Na posição inicial, `Nf3` é legal e `Bf3` não. O Tesseract leu certo, e o glifo trocou a figurina.
        tokens = [fusao.Token("♗f3", "glifo", "♗f3", None, "Nf3")]
        (saida,) = arbitro.arbitrar([tokens], existe=nao_existe, posicoes=[(0, chess.Board())], relato=relato)
        self.assertEqual("Nf3", saida[0].texto)
        self.assertEqual((1, 1), (relato.pela_legalidade, relato.lances_alcancados))

    def test_sem_leitura_legal_nada_se_fabrica(self) -> None:
        tokens = [fusao.Token("♗f3", "glifo", "♗f3", None, "Bf3")]
        (saida,) = arbitro.arbitrar([tokens], existe=nao_existe, posicoes=[(0, chess.Board())])
        self.assertEqual("♗f3", saida[0].texto)

    def test_o_lado_lido_errado_nao_derruba_a_sequencia(self) -> None:
        relato = arbitro.Relato()
        tabuleiro = chess.Board()
        tabuleiro.turn = chess.BLACK
        arbitro.arbitrar([do_leitor("Nf3", "Nc6")], existe=nao_existe, posicoes=[(0, tabuleiro)], relato=relato)
        self.assertEqual(2, relato.lances_alcancados)

    def test_a_letra_da_lingua_do_livro_e_o_figura_solta(self) -> None:
        relato = arbitro.Relato()
        arbitro.arbitrar([do_leitor("Sf3")], existe=nao_existe, posicoes=[(0, chess.Board())], lingua="deu", relato=relato)
        self.assertEqual(1, relato.lances_alcancados)
        relato = arbitro.Relato()
        arbitro.arbitrar([[fusao.Token("♘", "glifo", "♘"), fusao.Token("f3", "glifo", "f3")]], existe=nao_existe, posicoes=[(0, chess.Board())], relato=relato)
        self.assertEqual(1, relato.lances_alcancados)

    def test_a_notacao_longa_e_jogada(self) -> None:
        relato = arbitro.Relato()
        arbitro.arbitrar([do_leitor("Sg1—f3", "Sb8><c6")], existe=nao_existe, posicoes=[(0, chess.Board())], lingua="deu", relato=relato)
        self.assertEqual(2, relato.lances_alcancados)

    def test_a_prosa_encerra_o_trecho(self) -> None:
        relato = arbitro.Relato()
        arbitro.arbitrar([do_leitor("e4", "porque", "e5")], existe=nao_existe, posicoes=[(0, chess.Board())], relato=relato)
        self.assertEqual(1, relato.lances_alcancados)

    def test_o_interruptor_da_legalidade(self) -> None:
        relato = arbitro.Relato()
        with mock.patch.object(arbitro, "LEGALIDADE", False):
            arbitro.arbitrar([do_leitor("e4")], existe=nao_existe, posicoes=[(0, chess.Board())], relato=relato)
        self.assertEqual(0, relato.lances_alcancados)


class FronteiraTests(unittest.TestCase):
    def test_o_arbitro_nao_importa_a_regua(self) -> None:
        arvore = ast.parse(Path(arbitro.__file__).read_text(encoding="utf-8"))
        nomes = {a.name for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom) for a in no.names}
        self.assertFalse({"regua_prosa", "relatorio_prosa", "bancada_prosa"} & nomes)
        self.assertIn("fusao", nomes)


if __name__ == "__main__":
    unittest.main()
