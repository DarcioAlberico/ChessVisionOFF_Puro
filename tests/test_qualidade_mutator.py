"""O mutator: o mutante que a suíte deixa passar, e o fonte que volta byte a byte (S-803)."""

from __future__ import annotations

import ast
import json
import sys
import unittest
from collections.abc import Sequence
from pathlib import Path

from ambiente_de_teste import pasta_temporaria

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools" / "qualidade"))

import mutator  # noqa: E402

SOMA = b'"""Brinquedo."""\n\n\ndef soma(a, b):\n    # comentario que o ast.unparse perderia\n    return a + b\n'


class BrinquedoTests(unittest.TestCase):
    """O critério da spec, rodando pytest de verdade num diretório temporário."""

    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.alvo = self.pasta / "soma.py"
        self.alvo.write_bytes(SOMA)
        self.teste = self.pasta / "test_soma.py"

    def _mutar(self, conferencia: str) -> mutator.Resultado:
        self.teste.write_bytes(f"from soma import soma\n\n\ndef test_soma():\n    assert {conferencia}\n".encode())
        return mutator.mutar(self.alvo, [self.teste], mutator.rodar_pytest(self.pasta, timeout=120))

    def test_conferir_so_zero_mais_zero_deixa_o_menos_viver(self) -> None:
        resultado = self._mutar("soma(0, 0) == 0")
        self.assertEqual((resultado.mutantes, resultado.mortos), (2, 1))
        self.assertEqual(resultado.sobreviventes, [mutator.Sobrevivente(6, "bin", "return a + b")])

    def test_conferir_dois_mais_tres_mata_o_menos(self) -> None:
        resultado = self._mutar("soma(2, 3) == 5")
        self.assertEqual((resultado.mutantes, resultado.mortos, resultado.sobreviventes), (2, 2, []))
        self.assertEqual(resultado.escore, 1.0)

    def test_o_fonte_volta_byte_a_byte_e_a_copia_some(self) -> None:
        self._mutar("soma(0, 0) == 0")
        self.assertEqual(self.alvo.read_bytes(), SOMA)
        self.assertFalse(mutator.copia_de(self.alvo).exists())

    def test_suite_que_ja_reprova_nao_e_medida(self) -> None:
        with self.assertRaises(RuntimeError):
            self._mutar("soma(2, 3) == 6")
        self.assertEqual(self.alvo.read_bytes(), SOMA)


class RestauracaoTests(unittest.TestCase):
    """Ctrl+C, `taskkill /F` e o `.pyc` que mantinha o mutante vivo."""

    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.alvo = self.pasta / "soma.py"
        self.alvo.write_bytes(SOMA)
        self.chamadas: list[bytes] = []

    def _rodar(self, interromper_na: int | None = None) -> mutator.Rodar:
        def rodar(testes: Sequence[Path]) -> bool:
            self.chamadas.append(self.alvo.read_bytes())
            if len(self.chamadas) == interromper_na:
                raise KeyboardInterrupt
            return True

        return rodar

    def test_ctrl_c_no_meio_restaura_o_fonte(self) -> None:
        with self.assertRaises(KeyboardInterrupt):
            mutator.mutar(self.alvo, [self.alvo], self._rodar(interromper_na=2))
        self.assertNotEqual(self.chamadas[1], SOMA, "a interrupção veio com o mutante gravado")
        self.assertEqual(self.alvo.read_bytes(), SOMA)
        self.assertFalse(mutator.copia_de(self.alvo).exists())

    def test_a_copia_existe_antes_da_primeira_mutacao(self) -> None:
        copias: list[bytes] = []

        def rodar(testes: Sequence[Path]) -> bool:
            if self.alvo.read_bytes() != SOMA:
                copias.append(mutator.copia_de(self.alvo).read_bytes())
            return True

        mutator.mutar(self.alvo, [self.alvo], rodar)
        self.assertEqual(copias, [SOMA, SOMA])

    def test_a_partida_seguinte_restaura_o_que_um_processo_morto_deixou(self) -> None:
        """O `taskkill /F` não roda `finally`: fica o mutante no lugar e a cópia ao lado."""
        mutator.copia_de(self.alvo).write_bytes(SOMA)
        self.alvo.write_bytes(SOMA.replace(b"a + b", b"a - b"))
        mutator.mutar(self.alvo, [self.alvo], self._rodar())
        self.assertEqual(self.chamadas[0], SOMA, "a linha de base mediu o mutante que ficou")
        self.assertEqual(self.alvo.read_bytes(), SOMA)
        self.assertFalse(mutator.copia_de(self.alvo).exists())

    def test_o_pyc_do_modulo_some_e_o_dos_outros_fica(self) -> None:
        cache = self.pasta / "__pycache__"
        cache.mkdir()
        (cache / "soma.cpython-310.pyc").write_bytes(b"velho")
        (cache / "outro.cpython-310.pyc").write_bytes(b"outro")
        vistos: list[bool] = []

        def rodar(testes: Sequence[Path]) -> bool:
            vistos.append((cache / "soma.cpython-310.pyc").exists())
            return True

        mutator.mutar(self.alvo, [self.alvo], rodar)
        self.assertEqual(vistos, [False, False, False])
        self.assertEqual(sorted(p.name for p in cache.iterdir()), ["outro.cpython-310.pyc"])

    def test_o_filho_nao_escreve_bytecode(self) -> None:
        self.assertEqual(mutator.ambiente(self.pasta)["PYTHONDONTWRITEBYTECODE"], "1")


class PontosTests(unittest.TestCase):
    FONTE = '''
"""Docstring do módulo."""
LIMITE: int = 3


def f(x: "Tipo", ys: list[int]) -> "Volta":
    """Docstring que não se muta."""
    nome: "Anotada" = "texto"
    if x < 1 and not ys:
        return True
    return x * 2 + LIMITE, nome
'''

    def test_cada_operador_aparece_e_docstring_e_anotacao_ficam_de_fora(self) -> None:
        arvore = ast.parse(self.FONTE)
        achados = [(p.linha, p.operador) for p in mutator.pontos(arvore)]
        self.assertEqual(
            achados,
            [
                (8, "str"),
                (9, "bool"),
                (9, "cmp"),
                (9, "not"),
                (9, "int"),
                (10, "ret"),
                (10, "boolc"),
                (11, "ret"),
                (11, "bin"),
                (11, "bin"),
                (11, "int"),
            ],
        )

    def test_cada_mutante_muda_so_o_seu_ponto(self) -> None:
        arvore = ast.parse(self.FONTE)
        original = ast.unparse(arvore)
        trocas = {}
        for ponto in mutator.pontos(arvore):
            novo = mutator.mutante(arvore, ponto)
            self.assertNotEqual(novo.strip(), original)
            ast.parse(novo)
            trocas.setdefault(ponto.operador, novo)
        self.assertIn("x <= 1", trocas["cmp"])
        self.assertIn("x < 1 or not ys", trocas["bool"])
        self.assertIn("if x < 1 and ys:", trocas["not"])
        self.assertIn("return False", trocas["boolc"])
        self.assertIn("nome: 'Anotada' = ''", trocas["str"])
        self.assertIn("x < 2", trocas["int"])
        self.assertEqual(ast.unparse(arvore), original, "a árvore original não pode mudar")

    def test_limite_amostra_em_ordem_de_linha(self) -> None:
        arvore = ast.parse(self.FONTE)
        todos = mutator.pontos(arvore)
        amostra = mutator.pontos(arvore, limite=4)
        self.assertEqual(len(amostra), 4)
        self.assertEqual(amostra, sorted(amostra, key=lambda p: (p.linha, p.indice)))
        self.assertTrue(set(amostra) <= set(todos))


class TestesQueImportamTests(unittest.TestCase):
    def test_todo_jeito_de_importar_conta_e_o_vizinho_nao(self) -> None:
        pasta = pasta_temporaria(self)
        arquivos = {
            "test_a.py": "import pacote.ui.legality\n",
            "test_b.py": "from pacote.ui.legality import x\n",
            "test_c.py": "from pacote.ui import legality as leg\n",
            "test_d.py": "def t():\n    from pacote.ui import outro, legality\n",
            "test_e.py": "from pacote.ui import legality_extra\nimport pacote.ui\n",
            "test_f.py": "from pacote import ui\n",
            "test_legality.py": "from pacote.ui.legality import y\n",
            "ajudante.py": "import pacote.ui.legality\n",
        }
        for nome, fonte in arquivos.items():
            (pasta / nome).write_bytes(fonte.encode())
        achados = [p.name for p in mutator.testes_que_importam("pacote.ui.legality", pasta)]
        # O homônimo primeiro: com `pytest -x`, o mutante que morre nele não paga os outros.
        self.assertEqual(achados, ["test_legality.py", "test_a.py", "test_b.py", "test_c.py", "test_d.py"])

    def test_nome_do_modulo_sai_do_caminho(self) -> None:
        src = RAIZ / "src"
        self.assertEqual(
            mutator.nome_do_modulo(src / "chess_diagram_ocr" / "ui" / "legality.py", src),
            "chess_diagram_ocr.ui.legality",
        )


class RegistroTests(unittest.TestCase):
    def test_o_escore_registrado_so_sobe(self) -> None:
        registro = pasta_temporaria(self) / "mutacao.json"
        bom = mutator.Resultado("src/m.py", ["test_m.py"], mutantes=10, mortos=8)
        self.assertIsNone(mutator.gravar(bom, 10, registro, forcar=False))
        pior = mutator.Resultado("src/m.py", ["test_m.py"], mutantes=10, mortos=5)
        self.assertIsNotNone(mutator.gravar(pior, 10, registro, forcar=False))
        self.assertEqual(json.loads(registro.read_text(encoding="utf-8"))["modulos"]["src/m.py"]["escore"], 0.8)
        self.assertIsNone(mutator.gravar(pior, 10, registro, forcar=True))


if __name__ == "__main__":
    unittest.main()
