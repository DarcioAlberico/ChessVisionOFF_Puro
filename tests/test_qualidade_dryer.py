"""O dryer e a catraca de pares de funções duplicadas (S-802)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools" / "qualidade"))

import dryer  # noqa: E402

CONTAR = '''
def contar_{n}(itens, limite=3):
    """Quantos itens passam do limite, e quais."""
    {a} = 0
    {b} = []
    for {c} in itens:
        if {c} > limite and {c} % 2 == 0:
            {a} = {a} + 1
            {b}.append({c} * 10)
        elif {c} < -limite:
            {b}.append(-{c})
    if not {b}:
        return None
    return {a}, sorted({b}), "pronto"
'''

MESMO_ESQUELETO = '''
def montar(pasta, nomes):
    """O mesmo esqueleto do de cima: def, for, if, elif, if not, return."""
    caminhos = {}
    for nome in nomes:
        if nome.endswith(".py") or nome.startswith("_"):
            caminhos[nome] = pasta / nome
            print("achado", nome, file=sys.stderr)
        elif nome in caminhos.keys():
            raise ValueError(f"repetido: {nome!r}")
    if not caminhos:
        raise FileNotFoundError(str(pasta))
    return list(caminhos.values())[::-1]
'''


def _funcoes(fonte: str) -> list[dryer.Funcao]:
    return dryer.funcoes_do_arquivo(fonte, "src/m.py")


class SemelhancaTests(unittest.TestCase):
    def test_duas_funcoes_iguais_a_menos_dos_nomes_dao_1(self) -> None:
        a, b = _funcoes(CONTAR.format(n=1, a="total", b="vistos", c="x") + CONTAR.format(n=2, a="k", b="lst", c="v"))
        self.assertGreaterEqual(a.tokens, dryer.MIN_TOKENS)
        self.assertEqual(dryer.semelhanca(a, b), 1.0)
        self.assertEqual(
            [(p.a.nome, p.b.nome, p.semelhanca) for p in dryer.pares([a, b])], [("contar_1", "contar_2", 1.0)]
        )

    def test_mesmo_esqueleto_com_corpo_diferente_fica_abaixo_de_0_6(self) -> None:
        a, b = _funcoes(CONTAR.format(n=1, a="total", b="vistos", c="x") + MESMO_ESQUELETO)
        self.assertLess(dryer.semelhanca(a, b), 0.6)
        self.assertEqual(dryer.pares([a, b]), [])

    def test_funcao_curta_nao_entra(self) -> None:
        self.assertEqual(_funcoes("def f(x):\n    return x + 1\n"), [])

    def test_a_de_fora_e_a_de_dentro_nao_sao_um_par(self) -> None:
        interna = CONTAR.format(n=1, a="total", b="vistos", c="x").replace("\n", "\n    ")
        funcoes = _funcoes(f"def fora(itens):{interna}\n    return contar_1(itens)\n")
        self.assertEqual(sorted(f.nome for f in funcoes), ["fora", "fora.contar_1"])
        self.assertEqual(dryer.pares(funcoes), [])

    def test_metodo_sai_com_o_nome_da_classe(self) -> None:
        metodo = CONTAR.format(n=1, a="total", b="vistos", c="x").replace("(itens", "(self, itens")
        (funcao,) = _funcoes("class C:" + metodo.replace("\n", "\n    "))
        self.assertEqual(funcao.chave, "src/m.py::C.contar_1")

    def test_f_string_vira_uma_string_so(self) -> None:
        """No 3.12+ o `tokenize` abre a f-string em pedaços; a régua tem de dar o mesmo no 3.10."""
        self.assertEqual(dryer.tokens_por_linha('x = f"a{b + 1}c{d!r}"\n'), [(1, "N"), (1, "="), (1, "S")])


class CatracaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raiz = pasta_temporaria(self)
        (self.raiz / "src").mkdir()
        self.registro = self.raiz / "dryer.json"
        self._escreve("a.py", CONTAR.format(n=1, a="total", b="vistos", c="x") + MESMO_ESQUELETO)
        self.assertEqual(self._roda("--gravar"), 0)

    def _escreve(self, nome: str, fonte: str) -> None:
        (self.raiz / "src" / nome).write_bytes(fonte.encode())

    def _roda(self, *extra: str) -> int:
        return dryer.main(["--raiz", str(self.raiz), "--registro", str(self.registro), "--mostrar", "0", *extra])

    def _registrado(self) -> dict[str, object]:
        dados: dict[str, object] = json.loads(self.registro.read_text(encoding="utf-8"))
        return dados

    def test_o_estado_registrado_passa(self) -> None:
        self.assertEqual(self._roda(), 0)

    def test_a_copia_acrescentada_reprova_e_gravar_a_recusa(self) -> None:
        self._escreve("b.py", CONTAR.format(n=9, a="soma", b="lista", c="item"))
        self.assertEqual(self._roda(), 1)
        antes = self.registro.read_bytes()
        self.assertEqual(self._roda("--gravar"), 1)
        self.assertEqual(self.registro.read_bytes(), antes)

    def test_par_aceito_leva_a_razao_e_ela_sobrevive_a_regravacao(self) -> None:
        self._escreve("b.py", CONTAR.format(n=9, a="soma", b="lista", c="item"))
        self.assertEqual(self._roda("--gravar", "--aceitar", "duas leituras do mesmo formato"), 0)
        self.assertEqual(self._roda(), 0)
        self.assertEqual(self._roda("--gravar"), 0)
        pares = self._registrado()["pares"]
        assert isinstance(pares, list)
        self.assertEqual(
            [(par["a"], par["b"], par["proposito"]) for par in pares],
            [("src/a.py::contar_1", "src/b.py::contar_9", "duas leituras do mesmo formato")],
        )

    def test_par_que_some_reprova_ate_regravar_e_o_teto_desce(self) -> None:
        self._escreve("b.py", CONTAR.format(n=9, a="soma", b="lista", c="item"))
        self.assertEqual(self._roda("--gravar", "--aceitar", "por ora"), 0)
        (self.raiz / "src" / "b.py").unlink()
        self.assertEqual(self._roda(), 1)
        self.assertEqual(self._roda("--gravar"), 0)
        self.assertEqual((self._registrado()["total"], self._roda()), (0, 0))


class CatracaDoRepositorioTests(unittest.TestCase):
    """O `src/` de hoje contra `docs/metrics/dryer.json`."""

    def test_nenhum_par_novo_e_nenhum_par_sumido(self) -> None:
        registrado = json.loads(dryer.REGISTRO.read_text(encoding="utf-8"))
        novos, sumidos = dryer.comparar(registrado, dryer.pares(dryer.funcoes_da_arvore(RAIZ)))
        self.assertEqual(
            ([dryer._descreve(p) for p in novos], sumidos),
            ([], []),
            "Par novo: desfaça a cópia, ou registre com `python tools/qualidade/dryer.py --gravar "
            '--aceitar "razão"`. Par sumido: `python tools/qualidade/dryer.py --gravar` baixa o teto.',
        )


if __name__ == "__main__":
    unittest.main()
