"""A régua da estrutura de colunas, anotada à mão (S-524).

**O teste que dá nome a este arquivo é `test_o_baseline_reprova_a_pagina_que_acertava_e_passou_a_errar`.**
A régua da S-194 é cega onde a camada é zigue-zague, e foi assim que as páginas de soluções do
Yusupov saíram intercaladas sem nenhum número vermelho. Aqui a referência é a diagramação, anotada,
e o portão é por página: uma média esconderia a troca de uma página certa por outra.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from chess_diagram_ocr.cli import texto_colunas as colunas


def _pdf(raiz: Path, nome: str, paginas: list[list[tuple[str, float, float]]]) -> Path:
    doc = fitz.open()
    for linhas in paginas:
        page = doc.new_page(width=595.0, height=842.0)
        for texto, x, y in linhas:
            page.insert_text((x, y), texto, fontsize=11)
    caminho = raiz / nome
    doc.save(caminho)
    doc.close()
    return caminho


def _duas_colunas() -> list[tuple[str, float, float]]:
    return [(f"esquerda {i}", 60.0, 100.0 + i * 20) for i in range(20)] + [
        (f"direita {i}", 330.0, 100.0 + i * 20) for i in range(20)
    ]


def _uma_coluna() -> list[tuple[str, float, float]]:
    return [(f"uma linha comprida de prosa, a de numero {i}", 60.0, 100.0 + i * 20) for i in range(20)]


def _anotadas(raiz: Path, paginas: list[dict[str, object]]) -> Path:
    caminho = raiz / "anotadas.json"
    caminho.write_text(json.dumps({"esquema": 1, "paginas": paginas}), encoding="utf-8")
    return caminho


class MedirTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)
        _pdf(self.raiz, "livro.pdf", [_duas_colunas(), _uma_coluna(), []])

    def test_a_camada_acha_a_estrutura_anotada(self) -> None:
        anotadas = [
            colunas.Anotada("livro.pdf", 1, 2, "prosa"),
            colunas.Anotada("livro.pdf", 2, 1, "coluna_unica"),
        ]
        relatorio = colunas.medir(anotadas, pdf_dir=self.raiz, motor="camada")
        self.assertEqual(2, relatorio["acertos"])
        self.assertEqual({"prosa": {"paginas": 1, "acertos": 1}, "coluna_unica": {"paginas": 1, "acertos": 1}},
                         relatorio["por_grupo"])

    def test_a_pagina_errada_sai_com_o_que_foi_achado(self) -> None:
        relatorio = colunas.medir([colunas.Anotada("livro.pdf", 1, 1, "x")], pdf_dir=self.raiz, motor="camada")
        [pagina] = relatorio["paginas"]
        self.assertFalse(pagina["acerto"])
        self.assertEqual((1, 2), (pagina["esperado"], pagina["achado"]))

    def test_a_pagina_sem_camada_nao_e_erro_nem_acerto(self) -> None:
        relatorio = colunas.medir([colunas.Anotada("livro.pdf", 3, 1, "x")], pdf_dir=self.raiz, motor="camada")
        self.assertIsNone(relatorio["paginas"][0]["acerto"])
        self.assertEqual(0, relatorio["paginas_medidas"])
        self.assertEqual(["livro.pdf p.3: sem camada"], relatorio["sem_medida"])

    def test_o_livro_que_nao_esta_no_checkout_e_dito(self) -> None:
        relatorio = colunas.medir([colunas.Anotada("outro.pdf", 1, 2, "x")], pdf_dir=self.raiz, motor="camada")
        self.assertEqual(["outro.pdf p.1"], relatorio["nao_encontradas"])
        self.assertEqual([], relatorio["paginas"])

    def test_o_glifo_segmenta_a_imagem_e_acha_as_duas_colunas(self) -> None:
        """O motor da aba: caixas de caractere na imagem renderizada, sem modelo nenhum."""
        relatorio = colunas.medir([colunas.Anotada("livro.pdf", 1, 2, "prosa")], pdf_dir=self.raiz, motor="glifo")
        self.assertEqual(1, relatorio["acertos"], relatorio["paginas"])


class RegressoesTests(unittest.TestCase):
    def test_so_a_pagina_que_acertava_e_errou_conta(self) -> None:
        antes = {"paginas": [
            {"pdf": "a.pdf", "pagina": 1, "acerto": True},
            {"pdf": "a.pdf", "pagina": 2, "acerto": False},
        ]}
        agora = {"paginas": [
            {"pdf": "a.pdf", "pagina": 1, "grupo": "g", "esperado": 2, "achado": 1, "acerto": False},
            {"pdf": "a.pdf", "pagina": 2, "grupo": "g", "esperado": 2, "achado": 1, "acerto": False},
            {"pdf": "a.pdf", "pagina": 3, "grupo": "g", "esperado": 2, "achado": 1, "acerto": False},
        ]}
        self.assertEqual(["a.pdf p.1 (g): esperava 2, achou 1"], colunas.regressoes(agora, antes))

    def test_a_pagina_sem_medida_nao_e_regressao(self) -> None:
        antes = {"paginas": [{"pdf": "a.pdf", "pagina": 1, "acerto": True}]}
        agora = {"paginas": [{"pdf": "a.pdf", "pagina": 1, "grupo": "g", "esperado": 2, "achado": None, "acerto": None}]}
        self.assertEqual([], colunas.regressoes(agora, antes))


class ComandoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)
        _pdf(self.raiz, "livro.pdf", [_duas_colunas(), _uma_coluna()])
        self.anotadas = _anotadas(self.raiz, [
            {"pdf": "livro.pdf", "pagina": 1, "colunas": 2, "grupo": "prosa"},
            {"pdf": "livro.pdf", "pagina": 2, "colunas": 1, "grupo": "coluna_unica"},
        ])

    def _main(self, *extra: str) -> int:
        return colunas.main([
            "--anotadas", str(self.anotadas), "--pdf-dir", str(self.raiz), "--saida", str(self.raiz / "s.json"),
            *extra,
        ])

    def test_mede_e_grava_o_relatorio(self) -> None:
        self.assertEqual(0, self._main())
        relatorio = json.loads((self.raiz / "s.json").read_text(encoding="utf-8"))
        self.assertEqual(("camada", 2, 2), (relatorio["motor"], relatorio["acertos"], relatorio["paginas_medidas"]))

    def test_o_baseline_que_nao_existe_falha_antes_de_medir(self) -> None:
        self.assertEqual(2, self._main("--baseline", str(self.raiz / "nao.json")))
        self.assertFalse((self.raiz / "s.json").exists())

    def test_o_baseline_de_outro_motor_e_recusado(self) -> None:
        base = self.raiz / "base.json"
        base.write_text(json.dumps({"motor": "glifo", "paginas": []}), encoding="utf-8")
        self.assertEqual(2, self._main("--baseline", str(base)))

    def test_o_baseline_reprova_a_pagina_que_acertava_e_passou_a_errar(self) -> None:
        base = self.raiz / "base.json"
        self.assertEqual(0, self._main("--saida", str(base)))
        self.assertEqual(0, self._main("--baseline", str(base)), "a mesma medição não regride")
        # A anotação muda: a página 2 passa a "esperar" duas colunas, e a medição de hoje a erra.
        anotadas = json.loads(self.anotadas.read_text(encoding="utf-8"))
        anotadas["paginas"][1]["colunas"] = 2
        self.anotadas.write_text(json.dumps(anotadas), encoding="utf-8")
        self.assertEqual(1, self._main("--baseline", str(base)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
