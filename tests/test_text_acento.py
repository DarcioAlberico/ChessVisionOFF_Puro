"""S-735: o acento trocado, a cedilha e o segundo corte de caixa.

Decisão com caixas sintéticas, que roda no CI sem modelo nem livro. Cada família tem o caso que reproduz o
defeito com a constante desligada: teste que passa com o conserto revertido não guarda nada.
"""

from __future__ import annotations

import unittest
from unittest import mock

from glifo_sintetico import C2I, DE_X, I2C, _lidos, _linha, _matriz, _texto

from chess_diagram_ocr.text import acento, caixa_alta
from chess_diagram_ocr.text.boxes import Caixa


class AcentoTests(unittest.TestCase):
    """S-735: `não` saía `näo`, e a classe que vencia é a de 15 amostras."""

    def _ler(self, palavra: str, segundos: dict[int, str], lexico: frozenset[str]) -> str:
        chars, caixas = _linha([(c, 12, 20) for c in palavra])
        return _texto(acento.corrigir(_lidos(chars), _matriz(chars, segundos), caixas, I2C, lexico))

    def test_til_contra_trema(self) -> None:
        self.assertEqual(self._ler("näo", {1: "ã"}, frozenset({"nada"})), "não")
        self.assertEqual(self._ler("entäo", {3: "ã"}, frozenset({"então"})), "então")

    def test_o_defeito_volta_com_a_constante_desligada(self) -> None:
        with mock.patch.object(acento, "LIGADO", False):
            self.assertEqual(self._ler("entäo", {3: "ã"}, frozenset({"então"})), "entäo")

    def test_circunflexo_contra_agudo(self) -> None:
        self.assertEqual(self._ler("trés", {2: "ê"}, frozenset({"três"})), "três")

    def test_o_alemao_fica(self) -> None:
        self.assertEqual(self._ler("Spätes", {2: "ã"}, frozenset({"outra"})), "Spätes")
        self.assertEqual(self._ler("Bäume", {1: "ã"}, frozenset({"bäume", "bãume"})), "Bäume")

    def test_nao_tira_nem_poe_tinta(self) -> None:
        """`façanha` virava `facanha` no dicionário. Letra sem acento não entra."""
        self.assertEqual(self._ler("facanha", {2: "ç"}, frozenset({"façanha"})), "facanha")
        self.assertEqual(self._ler("päo", {1: "a"}, frozenset({"pao"})), "päo")

    def test_sem_a_opcao_do_modelo_nao_troca(self) -> None:
        self.assertEqual(self._ler("entäo", {}, frozenset({"então"})), "entäo")

    def test_o_sufixo_portugues_sem_lexico(self) -> None:
        self.assertEqual(self._ler("moderaçäo", {7: "ã"}, frozenset({"outra"})), "moderação")
        self.assertEqual(self._ler("moderaçäos", {7: "ã"}, frozenset({"outra"})), "moderaçäos")
        self.assertEqual(self._ler("näo-sovi", {1: "ã"}, frozenset({"outra"})), "não-sovi")
        self.assertEqual(self._ler("äo", {0: "ã"}, frozenset({"outra"})), "äo", "`äo` sozinho não é sufixo")

    def test_a_confianca_e_da_classe_escolhida(self) -> None:
        chars, caixas = _linha([(c, 12, 20) for c in "entäo"])
        lidos = acento.corrigir(_lidos(chars), _matriz(chars, {3: "ã"}), caixas, I2C, frozenset({"então"}))
        self.assertAlmostEqual(lidos[3][1], 0.3, places=5)


class DescidaTests(unittest.TestCase):
    """A cedilha desce, e o `P` não."""

    def _ultima(self, char: str, caixa: Caixa, segundo: str | None = None) -> str:
        chars, caixas = _linha(DE_X)
        chars, caixas = [*chars, char], [*caixas, caixa]
        probs = _matriz(chars, {len(chars) - 1: segundo} if segundo else None)
        return caixa_alta.decidir(probs, [c.altura for c in caixas], I2C, caixas=caixas)[-1][0]

    def test_a_cedilha(self) -> None:
        cedilha = Caixa(60, 80, 72, 109)
        self.assertEqual(self._ultima("c", cedilha, "ç"), "ç")
        with mock.patch.object(caixa_alta, "CEDILHA_PELA_DESCIDA", False):
            self.assertEqual(self._ultima("c", cedilha, "ç"), "C", "a cedilha estica a caixa, e ela passa do corte")

    def test_c_sem_descida_fica(self) -> None:
        self.assertEqual(self._ultima("C", Caixa(60, 72, 76, 100), "ç"), "C")
        self.assertEqual(self._ultima("c", Caixa(60, 80, 72, 101), "ç"), "c")

    def test_cedilha_fora_das_opcoes_do_modelo_nao_entra(self) -> None:
        self.assertEqual(self._ultima("c", Caixa(60, 80, 72, 109)), "C")

    def test_o_p_sem_descida_e_maiusculo(self) -> None:
        self.assertEqual(self._ultima("p", Caixa(60, 72, 74, 100)), "P")
        with mock.patch.object(caixa_alta, "P_PELA_DESCIDA", False):
            self.assertEqual(self._ultima("p", Caixa(60, 72, 74, 100)), "p")

    def test_o_p_que_desce_fica(self) -> None:
        self.assertEqual(self._ultima("p", Caixa(60, 80, 74, 107)), "p")


class SegundoCorteTests(unittest.TestCase):
    """S-735: a minúscula acentuada tem o acento dentro da caixa, e não pode virar `Ó`."""

    def _ultima(self, char: str, altura: int) -> str:
        chars, caixas = _linha([*DE_X, (char, 12, altura)])
        return caixa_alta.decidir(_matriz(chars), [c.altura for c in caixas], I2C, caixas=caixas)[-1][0]

    def test_o_palpite_maiusculo_baixo_vira_minuscula(self) -> None:
        self.assertEqual(self._ultima("Õ", 29), "õ", "1,45 x-height, abaixo do segundo corte")
        self.assertEqual(self._ultima("Ó", 29), "ó")

    def test_a_maiuscula_de_verdade_fica(self) -> None:
        self.assertEqual(self._ultima("Õ", 37), "Õ", "1,85 x-height")

    def test_a_minuscula_mais_alta_do_dev_nao_sobe(self) -> None:
        """`após`->`apÓs`, com corte de 1,5: a minúscula acentuada vai a 1,53 no dev, e a margem é para 1,65."""
        self.assertEqual(self._ultima("ó", 31), "ó", "1,55")
        self.assertEqual(self._ultima("ú", 32), "ú", "1,60")

    def test_o_corte_de_1_25_inventaria_o_oo(self) -> None:
        """A régua de quem não tem acento: minúscula acentuada a 1,45 não pode virar maiúscula."""
        self.assertEqual(self._ultima("õ", 29), "õ")

    def test_o_defeito_volta_com_a_constante_desligada(self) -> None:
        with mock.patch.object(caixa_alta, "SEGUNDO_CORTE", False):
            self.assertEqual(self._ultima("Õ", 29), "Õ")


class LimiaresDaDescidaTests(unittest.TestCase):
    def _ultima(self, char: str, caixa: Caixa, probs: dict[str, float] | None = None) -> str:
        chars, caixas = _linha(DE_X)
        chars, caixas = [*chars, char], [*caixas, caixa]
        m = _matriz(chars)
        for c, p in (probs or {}).items():
            m[-1, C2I[c]] = p
        return caixa_alta.decidir(m, [c.altura for c in caixas], I2C, caixas=caixas)[-1][0]

    def test_a_descida_da_cedilha(self) -> None:
        self.assertEqual(self._ultima("c", Caixa(60, 80, 72, 104), {"ç": 0.3}), "c", "0,20: fica")
        self.assertEqual(self._ultima("c", Caixa(60, 80, 72, 107), {"ç": 0.3}), "ç", "0,35")

    def test_o_piso_da_cedilha(self) -> None:
        self.assertEqual(self._ultima("c", Caixa(60, 80, 72, 109), {"ç": 0.012}), "ç")
        self.assertEqual(self._ultima("c", Caixa(60, 80, 72, 109), {"ç": 0.008}), "C", "abaixo do piso, o modelo não a viu")

    def test_a_descida_do_p(self) -> None:
        self.assertEqual(self._ultima("p", Caixa(60, 74, 74, 102)), "P", "0,07 da caixa")
        self.assertEqual(self._ultima("p", Caixa(60, 75, 74, 103)), "p", "0,11 da caixa")

    def test_toda_acentuada_tem_o_segundo_corte(self) -> None:
        for baixa in "íóõöúćčšž":
            alta = baixa.upper()
            self.assertEqual(self._ultima(alta, Caixa(60, 71, 72, 100)), baixa, alta)


class LimiaresDoAcentoTests(unittest.TestCase):
    def _ler(self, palavra: str, alternativas: dict[int, list[tuple[str, float]]], lexico: frozenset[str]) -> str:
        chars, caixas = _linha([(c, 12, 20) for c in palavra])
        m = _matriz(chars)
        for k, lista in alternativas.items():
            for c, p in lista:
                m[k, C2I[c]] = p
        return _texto(acento.corrigir(_lidos(chars), m, caixas, I2C, lexico))

    def test_o_terceiro_do_modelo_entra(self) -> None:
        lido = self._ler("trés", {2: [("e", 0.2), ("ê", 0.1)]}, frozenset({"três"}))
        self.assertEqual(lido, "três")

    def test_o_quarto_nao_entra(self) -> None:
        lido = self._ler("trés", {2: [("e", 0.2), ("a", 0.15), ("ê", 0.1)]}, frozenset({"três"}))
        self.assertEqual(lido, "trés")

    def test_o_piso(self) -> None:
        self.assertEqual(self._ler("trés", {2: [("ê", 0.0012)]}, frozenset({"três"})), "três")
        self.assertEqual(self._ler("trés", {2: [("ê", 0.0008)]}, frozenset({"três"})), "trés")

    def test_duas_trocas_sim_e_tres_nao(self) -> None:
        duas = {1: [("ã", 0.3)], 3: [("ê", 0.3)]}
        self.assertEqual(self._ler("cäbé", duas, frozenset({"cãbê"})), "cãbê")
        tres = {1: [("ã", 0.3)], 3: [("ê", 0.3)], 4: [("ê", 0.3)]}
        self.assertEqual(self._ler("cäbéé", tres, frozenset({"cãbêê"})), "cäbéé")


if __name__ == "__main__":
    unittest.main()
