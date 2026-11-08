"""O crapper e a catraca de CRAP por função (S-801)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
import unittest.mock
from pathlib import Path

from ambiente_de_teste import pasta_temporaria

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools" / "qualidade"))

import crapper  # noqa: E402

TEM_RADON = importlib.util.find_spec("radon") is not None

COMPLEXIDADE_12 = (
    "def doze(x):\n" + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(11)) + "    return -1\n"
)
"""Onze `if` e um caminho reto: complexidade ciclomática 12."""


def _bloco(funcao: str, cc: int, linha: int = 1, fim: int = 10, arquivo: str = "src/m.py") -> crapper.Bloco:
    return crapper.Bloco(arquivo, funcao, linha, fim, cc)


class FormulaTests(unittest.TestCase):
    def test_funcao_sem_teste_vale_cc_ao_quadrado_mais_cc(self) -> None:
        medidas = crapper.medir([_bloco("doze", 12)], {})
        self.assertEqual([(m.funcao, m.cobertura, m.crap) for m in medidas], [("doze", 0.0, 156.0)])

    def test_funcao_toda_coberta_vale_o_proprio_cc(self) -> None:
        linhas = crapper.Linhas(frozenset(range(1, 11)), frozenset())
        (medida,) = crapper.medir([_bloco("doze", 12)], {"src/m.py": linhas})
        self.assertEqual((medida.cobertura, medida.crap), (1.0, 12.0))

    def test_a_cobertura_e_a_das_linhas_da_funcao_e_nao_a_do_arquivo(self) -> None:
        # Linhas 1-4 da função rodaram, 5-8 não; 20-30 são de outra função e não contam.
        linhas = crapper.Linhas(frozenset([1, 2, 3, 4, *range(20, 31)]), frozenset([5, 6, 7, 8]))
        (medida,) = crapper.medir([_bloco("f", 4, 1, 8)], {"src/m.py": linhas})
        self.assertEqual(medida.cobertura, 0.5)
        self.assertEqual(medida.crap, 4 * 4 * 0.5**3 + 4)

    def test_o_json_do_coverage_entra_com_barra_normal(self) -> None:
        dados = {"files": {"src\\pacote\\m.py": {"executed_lines": [1], "missing_lines": [2]}}}
        self.assertEqual(list(crapper.ler_cobertura(dados)), ["src/pacote/m.py"])


@unittest.skipUnless(TEM_RADON, "radon não instalado (extra `dev`)")
class RadonTests(unittest.TestCase):
    def test_funcao_sintetica_de_complexidade_12_sem_teste_da_156(self) -> None:
        raiz = pasta_temporaria(self)
        (raiz / "src").mkdir()
        (raiz / "src" / "m.py").write_bytes(COMPLEXIDADE_12.encode())
        blocos = crapper.blocos_do_radon(raiz)
        self.assertEqual([(b.arquivo, b.funcao, b.cc) for b in blocos], [("src/m.py", "doze", 12)])
        self.assertEqual(crapper.medir(blocos, {})[0].crap, 156.0)

    def test_metodo_e_closure_saem_com_nome_qualificado(self) -> None:
        raiz = pasta_temporaria(self)
        (raiz / "src").mkdir()
        fonte = (
            "class C:\n    def m(self):\n        def dentro():\n            return 1\n        return dentro\n"
            "class D:\n    class E:\n        def m(self):\n            return 2\n"
        )
        (raiz / "src" / "m.py").write_bytes(fonte.encode())
        nomes = sorted(b.funcao for b in crapper.blocos_do_radon(raiz))
        self.assertEqual(nomes, ["C.m", "C.m.dentro", "D.E.m"])


class CatracaTests(unittest.TestCase):
    """A catraca compara pelo nome, e reprova o que sobe."""

    def setUp(self) -> None:
        cobertura = {"src/m.py": crapper.Linhas(frozenset(range(1, 200)), frozenset())}
        self.base = crapper.medir([_bloco("velha", 11, 1, 5), _bloco("pior", 40, 6, 9)], {})
        self.base += crapper.medir([_bloco("coberta", 5, 10, 20)], cobertura)
        self.registrado = crapper.registro(self.base, {})

    def test_o_estado_registrado_passa(self) -> None:
        self.assertEqual(crapper.comparar(self.registrado, self.base), [])

    def test_funcao_nova_acima_de_30_reprova_e_removida_passa(self) -> None:
        nova = crapper.medir([_bloco("doze", 12, 30, 40)], {})
        falhas = crapper.comparar(self.registrado, self.base + nova)
        self.assertEqual(len(falhas), 2, falhas)
        self.assertIn("funções com CRAP >= 10: 3, e o registro permite 2", falhas)
        self.assertTrue(falhas[1].startswith("src/m.py:30 doze: CRAP 156"), falhas)
        self.assertEqual(crapper.comparar(self.registrado, self.base), [])

    def test_a_linha_que_anda_nao_conta_como_funcao_nova(self) -> None:
        andou = crapper.medir([_bloco("velha", 11, 101, 105), _bloco("pior", 40, 106, 109)], {})
        self.assertEqual(crapper.comparar(self.registrado, andou), [])

    def test_trocar_uma_funcao_acima_do_limiar_por_outra_reprova_se_a_nova_passa_do_teto(self) -> None:
        trocada = crapper.medir([_bloco("velha", 11, 1, 5), _bloco("outra", 40, 6, 9)], {})
        self.assertEqual(len(crapper.comparar(self.registrado, trocada)), 1)

    def test_gravar_recusa_a_regressao(self) -> None:
        pasta = pasta_temporaria(self)
        registro = pasta / "crap.json"
        registro.write_bytes(json.dumps({**self.registrado, "funcoes_acima_do_limiar": 0, "funcoes": []}).encode())
        cobertura = pasta / "coverage.json"
        cobertura.write_bytes(json.dumps({"meta": {}, "files": {}}).encode())
        antes = registro.read_bytes()
        with unittest.mock.patch.object(crapper, "blocos_do_radon", return_value=[_bloco("doze", 12)]):
            codigo = crapper.main(["--cobertura", str(cobertura), "--registro", str(registro), "--gravar"])
        self.assertEqual((codigo, registro.read_bytes()), (1, antes))


COBERTURA_GRAVADA = Path(os.environ.get("CVOFF_COBERTURA", RAIZ / "coverage.json"))


@unittest.skipUnless(
    TEM_RADON and COBERTURA_GRAVADA.exists(), "sem radon ou sem coverage.json: rode `coverage run -m pytest`"
)
class CatracaDoRepositorioTests(unittest.TestCase):
    """O `src/` de hoje contra `docs/metrics/crap.json`, quando há uma cobertura medida."""

    def test_nenhuma_funcao_sobe_alem_do_registrado(self) -> None:
        dados = json.loads(COBERTURA_GRAVADA.read_text(encoding="utf-8"))
        medidas = crapper.medir(crapper.blocos_do_radon(RAIZ), crapper.ler_cobertura(dados))
        registrado = json.loads(crapper.REGISTRO.read_text(encoding="utf-8"))
        self.assertEqual(crapper.comparar(registrado, medidas), [])


if __name__ == "__main__":
    unittest.main()
