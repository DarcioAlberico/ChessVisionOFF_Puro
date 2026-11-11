"""Os limites de relógio da suíte escalam com o ambiente, e as esperas reprovam no estouro (S-872)."""

from __future__ import annotations

import ast
import os
import time
import unittest
from pathlib import Path
from unittest import mock

import tempo_da_suite
from qt_app import MOTIVO, TEM_PYQT, aplicacao, esperar_ate

TESTES = Path(__file__).resolve().parent


class FatorTests(unittest.TestCase):
    def test_sem_variavel_e_sem_cobertura_o_fator_e_um(self) -> None:
        with mock.patch.dict(os.environ, {tempo_da_suite.VARIAVEL: ""}), mock.patch.object(
            tempo_da_suite, "sob_cobertura", return_value=False
        ):
            self.assertEqual(tempo_da_suite.fator(), 1.0)
            self.assertEqual(tempo_da_suite.limite(1.5), 1.5)

    def test_sob_cobertura_o_fator_e_tres(self) -> None:
        with mock.patch.dict(os.environ, {tempo_da_suite.VARIAVEL: ""}), mock.patch.object(
            tempo_da_suite, "sob_cobertura", return_value=True
        ):
            self.assertEqual(tempo_da_suite.limite(1.5), 4.5)
            self.assertEqual(tempo_da_suite.limite_ms(1500), 4500)

    def test_a_variavel_vence_a_cobertura_e_aceita_virgula(self) -> None:
        with mock.patch.dict(os.environ, {tempo_da_suite.VARIAVEL: "2,5"}), mock.patch.object(
            tempo_da_suite, "sob_cobertura", return_value=True
        ):
            self.assertEqual(tempo_da_suite.limite(2.0), 5.0)

    def test_fator_que_nao_e_positivo_levanta_em_vez_de_ser_ignorado(self) -> None:
        for texto in ("0", "-1", "rapido"):
            with self.subTest(texto=texto), mock.patch.dict(os.environ, {tempo_da_suite.VARIAVEL: texto}):
                with self.assertRaises(ValueError):
                    tempo_da_suite.fator()


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class EsperarAteTests(unittest.TestCase):
    def setUp(self) -> None:
        aplicacao()

    def test_volta_assim_que_a_condicao_vale(self) -> None:
        prazo = time.monotonic() + 0.05
        inicio = time.monotonic()
        esperar_ate(lambda: time.monotonic() >= prazo, limite_s=5)
        self.assertLess(time.monotonic() - inicio, tempo_da_suite.limite(2.0))

    def test_o_estouro_reprova_dizendo_o_que_nao_aconteceu(self) -> None:
        """As esperas copiadas nos testes voltavam caladas; a asserção seguinte dizia outra coisa."""
        with mock.patch.dict(os.environ, {tempo_da_suite.VARIAVEL: "1"}):
            with self.assertRaises(AssertionError) as erro:
                esperar_ate(lambda: False, limite_s=0.1, o_que="o fim da varredura")
        self.assertIn("o fim da varredura não aconteceu em 0.1 s", str(erro.exception))


class NenhumaEsperaCaladaTests(unittest.TestCase):
    """Uma função de espera nos testes reprova no estouro, ou chama quem reprova (S-872)."""

    def test_toda_espera_dos_testes_reprova_no_estouro(self) -> None:
        caladas = []
        for caminho in sorted(TESTES.glob("*.py")):
            arvore = ast.parse(caminho.read_bytes().decode("utf-8"))
            for no in ast.walk(arvore):
                if not isinstance(no, ast.FunctionDef) or not no.name.lstrip("_").startswith("esperar"):
                    continue
                if no.name == "esperar_ate" and caminho.name == "qt_app.py":
                    continue
                corpo = ast.unparse(no)
                if not any(marca in corpo for marca in ("esperar_ate", "assert", "raise", "fail(")):
                    caladas.append(f"{caminho.name}:{no.lineno} {no.name}")
        self.assertEqual([], caladas, "espera que volta calada no estouro: use `qt_app.esperar_ate`")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
