"""S-731: a régua de altura pelas letras de x, a palavra coerente, e o `P` pela descida.

Decisão com caixas sintéticas, que roda no CI sem modelo nem livro. Cada família tem o caso que reproduz o
defeito com a constante desligada: teste que passa com o conserto revertido não guarda nada.
"""

from __future__ import annotations

import unittest
from unittest import mock

from glifo_sintetico import DE_X, I2C, _lidos, _linha, _matriz, _texto

from chess_diagram_ocr.text import caixa_alta
from chess_diagram_ocr.text.palavras_curtas import CURTAS, conhecida_ou_curta


class ReguaDeAlturaTests(unittest.TestCase):
    """S-731: a mediana da linha sobe com notação e maiúscula, e derruba o `W`."""

    def _decidir(self, desenho: list[tuple[str, int, int]], escala: float | None = None) -> str:
        chars, caixas = _linha(desenho)
        lidos = caixa_alta.decidir(_matriz(chars), [c.altura for c in caixas], I2C, caixas=caixas, escala=escala)
        return _texto(lidos)

    # O `W` numa linha cheia de lance: a mediana das alturas é a da maiúscula.
    LANCES = [("W", 24, 28), ("h", 12, 28), ("1", 8, 28), ("2", 8, 28), ("3", 8, 28), ("4", 8, 28), ("a", 12, 20), ("e", 12, 20)]

    def test_o_w_na_linha_de_notacao(self) -> None:
        self.assertEqual(self._decidir(self.LANCES), "Wh1234ae")

    def test_o_defeito_volta_com_a_mediana(self) -> None:
        with mock.patch.object(caixa_alta, "XH_COERENTE", False):
            self.assertEqual(self._decidir(self.LANCES), "wh1234ae")

    def test_a_linha_toda_em_maiuscula(self) -> None:
        self.assertEqual(self._decidir([(c, 16, 28) for c in "DEFESA"]), "DEFESA")
        with mock.patch.object(caixa_alta, "XH_COERENTE", False):
            self.assertEqual(self._decidir([(c, 16, 28) for c in "DEFESA"]), "DEFEsA")

    def test_com_letras_de_x_a_regua_e_delas(self) -> None:
        """Haste muito alta não muda a altura-de-x: pela razão das altas, este `C` cairia para `c`."""
        desenho = [*DE_X, ("h", 12, 40), ("d", 12, 40), ("b", 12, 40), ("C", 16, 28)]
        self.assertEqual(self._decidir(desenho), "aenhdbC")

    def test_a_minuscula_sem_letra_de_x_fica_minuscula(self) -> None:
        """`Bc4 Nc5`: nenhum `a`, `e`, `m`, `n`, `r`, e o `c` tem 0,7 da altura das altas."""
        self.assertEqual(self._decidir([("B", 16, 28), ("c", 12, 20), ("4", 10, 28)]), "Bc4")

    def test_a_linha_de_um_sinal_usa_a_escala_da_folha(self) -> None:
        self.assertEqual(self._decidir([("W", 24, 28)], escala=28.0), "W")
        self.assertEqual(self._decidir([("w", 16, 20)], escala=28.0), "w")
        self.assertEqual(self._decidir([("W", 24, 28)]), "w", "sem escala, o que sobra é a mediana da própria caixa")


class PalavraCoerenteTests(unittest.TestCase):
    """S-731: `FcM`, e o versalete, em que altura nenhuma separa."""

    def _coerente(self, palavra: str) -> str:
        chars, caixas = _linha([(c, 12, 20) for c in palavra])
        return _texto(caixa_alta.coerente(_lidos(chars), _matriz(chars), caixas, I2C))

    def test_a_palavra_em_maiuscula_nao_ganha_minuscula(self) -> None:
        self.assertEqual(self._coerente("uNusuAL"), "UNUSUAL")
        self.assertEqual(self._coerente("FcM"), "FCM")
        self.assertEqual(self._coerente("ANTlPoslTloNAL"), "ANTIPOSITIONAL")

    def test_o_defeito_volta_com_a_constante_desligada(self) -> None:
        with mock.patch.object(caixa_alta, "PALAVRA_COERENTE", False):
            self.assertEqual(self._coerente("uNusuAL"), "uNusuAL")

    def test_palavra_comum_fica(self) -> None:
        for palavra in ("Black", "White", "Los", "os"):
            self.assertEqual(self._coerente(palavra), palavra)

    def test_a_ambigua_depois_de_minuscula_desce(self) -> None:
        self.assertEqual(self._coerente("IvanchUk"), "Ivanchuk")
        self.assertEqual(self._coerente("teU"), "teu")
        self.assertEqual(self._coerente("McDonald"), "McDonald", "o `D` tem desenho próprio")

    def test_a_maiuscula_do_nome_fica(self) -> None:
        """O que o crítico achou fora do dev: Hertan, Yusupov."""
        for palavra in ("ChessCafe", "McClure", "McCutcheon", "McCoy", "McOy", "MacOs", "'McCoy"):
            self.assertEqual(self._coerente(palavra), palavra)

    def test_a_forma_minuscula_existe_e_nao_absolve(self) -> None:
        """`soViéticos`, `SacrifiCio`: o léxico sem nomes separa de `ChessCafe`, que não existe em minúscula."""
        lexico = frozenset({"soviéticos", "sacrificio", "siguiente"})
        for lido, certo in (("soViéticos", "soviéticos"), ("SacrifiCio", "Sacrificio"), ("sigUiente", "siguiente")):
            chars, caixas = _linha([(c, 12, 20) for c in lido])
            saida = caixa_alta.coerente(_lidos(chars), _matriz(chars), caixas, I2C, lexico)
            self.assertEqual(_texto(saida), certo)
        chars, caixas = _linha([(c, 12, 20) for c in "ChessCafe"])
        self.assertEqual(_texto(caixa_alta.coerente(_lidos(chars), _matriz(chars), caixas, I2C, lexico)), "ChessCafe")

    def test_mc_nao_depende_do_lexico(self) -> None:
        chars, caixas = _linha([(c, 12, 20) for c in "McClure"])
        lido = caixa_alta.coerente(_lidos(chars), _matriz(chars), caixas, I2C, frozenset({"mcclure"}))
        self.assertEqual(_texto(lido), "McClure")

    def test_uma_so_minuscula_depois_nao_absolve(self) -> None:
        self.assertEqual(self._coerente("toUr"), "tour")

    def test_o_plural_de_sigla_fica(self) -> None:
        """`GMs`, 19 ocorrências num livro."""
        self.assertEqual(self._coerente("GMs"), "GMs")
        self.assertEqual(self._coerente("FIDEs"), "FIDES", "a partir de 5 letras, é a palavra em maiúscula")

    def test_uma_maiuscula_so_nao_faz_a_palavra(self) -> None:
        for palavra in ("Dos", "You", "Now", "Bus"):
            self.assertEqual(self._coerente(palavra), palavra)

    def test_a_captura_seguida_de_casa_e_minuscula(self) -> None:
        self.assertEqual(self._coerente("QXf7"), "Qxf7")
        self.assertEqual(self._coerente("TXPTR"), "TXPTR", "descritiva")
        self.assertEqual(self._coerente("TEXas"), "TEXas", "sem a casa inteira depois, não é captura")

    def test_a_captura_com_a_casa_numa_caixa_so(self) -> None:
        """`Qxf7` chega com `f7` numa classe só, e o crítico achou `5.QXf7` e `NXa2` no Aagaard."""
        chars, caixas = _linha([("Q", 16, 28), ("X", 14, 28), ("f7", 18, 28)])
        self.assertEqual(_texto(caixa_alta.coerente(_lidos(chars), _matriz(chars), caixas, I2C)), "Qxf7")
        chars, caixas = _linha([("N", 16, 28), ("X", 14, 28), ("a2", 18, 28)])
        self.assertEqual(_texto(caixa_alta.coerente(_lidos(chars), _matriz(chars), caixas, I2C)), "Nxa2")

    def test_a_coluna_maiuscula_diante_do_digito_desce(self) -> None:
        self.assertEqual(self._coerente("KC5"), "Kc5")
        self.assertEqual(self._coerente("C2"), "c2")
        self.assertEqual(self._coerente("SC7"), "Sc7")
        self.assertEqual(self._coerente("C3A"), "C3A", "descritiva")
        self.assertEqual(self._coerente("Cc3"), "Cc3")
        self.assertEqual(self._coerente("aC5"), "aC5", "letra minúscula antes: não sabemos o que é")

    def test_codigo_eco_e_rotulo_nao_sao_casa(self) -> None:
        """Reprovação do crítico: `C3)` em *Secrets*, e `[C42]` no *Chess Evolution 2014*."""
        for palavra in ("C42", "[C42]", "C65", "C3)", "(C3)"):
            self.assertEqual(self._coerente(palavra), palavra)

    def test_o_eco_em_minuscula_volta(self) -> None:
        """`[c18]`: `c` com dois dígitos não é casa nenhuma."""
        self.assertEqual(self._coerente("[c18]"), "[C18]")
        self.assertEqual(self._coerente("c18"), "C18")
        self.assertEqual(self._coerente("c1"), "c1", "um dígito é casa")
        self.assertEqual(self._coerente("Rc1"), "Rc1")
        self.assertEqual(self._coerente("c3)"), "c3)", "rótulo em minúscula fica como está")

    def test_lance_fica(self) -> None:
        """Lance tem dígito, e `KxR` é captura: o `x` só sobe a partir de quatro letras."""
        for palavra in ("Nc3", "RxN3", "KxR", "QxB"):
            self.assertEqual(self._coerente(palavra), palavra)
        self.assertEqual(self._coerente("EXPRESs"), "EXPRESS")


class PalavrasCurtasTests(unittest.TestCase):
    def test_toda_palavra_e_curta_e_em_minuscula(self) -> None:
        self.assertTrue(all(len(p) < 4 and p == p.casefold() for p in CURTAS))

    def test_a_consulta(self) -> None:
        self.assertTrue(conhecida_ou_curta("The,", frozenset()))
        self.assertTrue(conhecida_ou_curta("first", frozenset({"first"})))
        self.assertFalse(conhecida_ou_curta("first", frozenset()))
        self.assertFalse(conhecida_ou_curta("...", frozenset({"..."})))


class LimiaresDaAlturaTests(unittest.TestCase):
    """A régua presa dos dois lados: o caso em que cada fonte da altura-de-x dá uma resposta diferente."""

    def _decidir(self, desenho: list[tuple[str, int, int]]) -> str:
        chars, caixas = _linha(desenho)
        return _texto(caixa_alta.decidir(_matriz(chars), [c.altura for c in caixas], I2C, caixas=caixas))

    # haste alta demais: pela razão das altas o `C` cairia, e pelas letras de x fica
    ALTAS = [("h", 12, 40), ("d", 12, 40), ("b", 12, 40), ("C", 16, 28)]

    def test_toda_letra_de_x_conta(self) -> None:
        for letras in ("ae", "mn", "nr", "am"):
            desenho = [(c, 12, 20) for c in letras]
            self.assertEqual(self._decidir(desenho + self.ALTAS), letras + "hdbC", letras)

    def test_duas_letras_de_x_bastam(self) -> None:
        self.assertEqual(self._decidir([("a", 12, 20), ("e", 12, 20), *self.ALTAS]), "aehdbC")

    def test_uma_letra_de_x_e_ruido(self) -> None:
        """Um fragmento de 12 px lido `a` não vira a régua: `c` de 20 seria 1,67 dele."""
        self.assertEqual(self._decidir([("a", 8, 12), ("h", 12, 28), ("d", 12, 28), ("c", 12, 20)]), "ahdc")

    def test_cada_alta_segura_mede_a_linha(self) -> None:
        for alta in "ABDEFGHKLMNPRTbdfhkl0123456789":  # literal: iterar a constante faria a guarda vácua
            lido = self._decidir([("C", 16, 28), (alta, 10, 28), (alta, 10, 28)])
            self.assertEqual(lido, f"C{alta}{alta}", alta)

    def test_cada_letra_de_x_mede_a_linha(self) -> None:
        for letra in "aemnr":  # literal, pelo mesmo motivo
            lido = self._decidir([(letra, 12, 20), (letra, 12, 20), ("h", 12, 40), ("d", 12, 40), ("b", 12, 40), ("C", 16, 28)])
            self.assertEqual(lido, f"{letra}{letra}hdbC", letra)

    def test_toda_alta_segura_conta(self) -> None:
        """Sem letra de x e só com dígito: a mediana, que sobra sem as altas, derrubaria o `C`."""
        self.assertEqual(self._decidir([("C", 16, 28), ("4", 10, 28), ("6", 10, 28)]), "C46")
        self.assertEqual(self._decidir([("C", 16, 28), ("T", 10, 28), ("k", 10, 28)]), "CTk")


class LimiaresDaPalavraTests(unittest.TestCase):
    def _coerente(self, palavra: str) -> str:
        chars, caixas = _linha([(c, 12, 20) for c in palavra])
        return _texto(caixa_alta.coerente(_lidos(chars), _matriz(chars), caixas, I2C))

    def test_duas_minusculas_absolvem_e_tres_nao_sao_preciso(self) -> None:
        self.assertEqual(self._coerente("ChesCar"), "ChesCar")

    def test_o_s_final_de_quatro_letras_fica(self) -> None:
        self.assertEqual(self._coerente("FIDs"), "FIDs")

    def test_duas_maiusculas_de_desenho_proprio_bastam(self) -> None:
        self.assertEqual(self._coerente("FcM"), "FCM")
        self.assertEqual(self._coerente("DoR"), "DOR")


if __name__ == "__main__":
    unittest.main()
