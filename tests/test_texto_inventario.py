"""O manifesto da base de caractere, e as três regras que ele não pode quebrar (S-200).

A mais cara das três vem de um acidente do projeto de origem: `cv2.imread` devolve `None` em
caminho não-ASCII no Windows, indistinguível de "arquivo corrompido", e a primeira versão da
migração de lá apagou PNGs válidos por causa disso. Aqui a leitura é `open()` + `imdecode`, e o
inventário **não escreve nada** dentro da pasta que inventaria.
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np

from chess_diagram_ocr.cli import texto_inventario as inv
from chess_diagram_ocr.text import procedencia as pr


def _png(caminho: Path, altura: int = 32, largura: int = 32, valor: int = 128) -> None:
    ok, buffer = cv2.imencode(".png", np.full((altura, largura), valor, dtype=np.uint8))
    assert ok
    caminho.write_bytes(buffer.tobytes())


class BaseDeMentira:
    """Uma base pequena e com defeito de propósito: classe vazia, PNG ilegível, pasta estranha."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz
        (raiz / "lower_a").mkdir(parents=True)
        _png(raiz / "lower_a" / "aaaa1111.png", 32, 32, 10)
        _png(raiz / "lower_a" / "aaaa2222.png", 26, 35, 20)
        _png(raiz / "lower_a" / "aaaa3333.png", 32, 32, 10)  # mesma imagem da primeira

        (raiz / "digit_1").mkdir()
        _png(raiz / "digit_1" / "bbbb1111.png")
        (raiz / "digit_1" / "quebrado.png").write_bytes(b"nao sou um png")

        (raiz / "lower_z").mkdir()  # classe vazia: a `lower_ä` do projeto de origem
        (raiz / "pasta_solta").mkdir()
        _png(raiz / "pasta_solta" / "cccc1111.png")


class ManifestoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name) / "base"
        BaseDeMentira(self.raiz)

    def test_o_inventario_nao_escreve_na_pasta(self) -> None:
        """Um inventário que mexe no que inventaria é a primeira peça de uma migração acidental."""
        antes = {
            caminho.relative_to(self.raiz).as_posix(): caminho.stat().st_mtime_ns
            for caminho in sorted(self.raiz.rglob("*"))
        }

        inv.inventariar(self.raiz, minimo=3)

        depois = {
            caminho.relative_to(self.raiz).as_posix(): caminho.stat().st_mtime_ns
            for caminho in sorted(self.raiz.rglob("*"))
        }
        self.assertEqual(antes, depois)

    def test_classe_vazia_vira_achado_nomeado(self) -> None:
        """Uma classe vazia entre 314 linhas iguais é uma classe vazia que ninguém vê."""
        manifesto = inv.inventariar(self.raiz, minimo=3)
        self.assertEqual(["lower_z"], manifesto["achados"]["classes_vazias"])

    def test_a_pasta_que_nao_decodifica_nao_vira_classe_calada(self) -> None:
        manifesto = inv.inventariar(self.raiz, minimo=3)
        self.assertIn("pasta_solta", manifesto["achados"]["pastas_que_nao_decodificam"])

    def test_a_classe_abaixo_do_minimo_e_nomeada_com_a_contagem(self) -> None:
        manifesto = inv.inventariar(self.raiz, minimo=3)
        abaixo = {a["pasta"]: a["recortes"] for a in manifesto["achados"]["classes_abaixo_do_minimo"]}
        self.assertEqual({"digit_1": 1, "pasta_solta": 1}, abaixo)

    def test_png_ilegivel_e_contado_e_nao_derruba(self) -> None:
        """Contado e nomeado, e o comando termina com sucesso. Nada é apagado nem movido."""
        manifesto = inv.inventariar(self.raiz, minimo=3)
        self.assertEqual(1, manifesto["achados"]["pngs_ilegiveis"])
        self.assertIn("digit_1/quebrado.png", manifesto["pngs_ilegiveis"])
        self.assertTrue((self.raiz / "digit_1" / "quebrado.png").exists())

    def test_a_copia_exata_nao_conta_como_imagem_distinta(self) -> None:
        manifesto = inv.inventariar(self.raiz, minimo=3)
        por_classe = {c["pasta"]: c for c in manifesto["por_classe"]}
        self.assertEqual(3, por_classe["lower_a"]["recortes"])
        self.assertEqual(2, por_classe["lower_a"]["imagens_distintas"])
        self.assertEqual({"32x32": 2, "26x35": 1}, por_classe["lower_a"]["dimensoes"])

    def test_a_leitura_usa_imdecode_e_nao_imread(self) -> None:
        """É lei neste projeto, e vem de PNGs válidos apagados no projeto de origem.

        A varredura é do **código**, via `ast`, e não do texto do arquivo: o cabeçalho cita
        `cv2.imread` e `cv2.imwrite` justamente para explicar por que eles não podem ser usados,
        e um `assertNotIn` sobre o arquivo inteiro proibiria explicar a regra.
        """
        arvore = ast.parse(Path(inv.__file__).read_text(encoding="utf-8"))
        chamados = {
            no.attr
            for no in ast.walk(arvore)
            if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name) and no.value.id == "cv2"
        }
        self.assertNotIn("imread", chamados)
        self.assertNotIn("imwrite", chamados)
        self.assertIn("cv2_imdecode_cinza", Path(inv.__file__).read_text(encoding="utf-8"))


class ProcedenciaNoManifestoTests(unittest.TestCase):
    """A S-201 entra aqui mesmo valendo `desconhecida` para tudo -- e é essa a informação."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name) / "base"
        BaseDeMentira(self.raiz)

    def test_sem_registro_toda_amostra_e_desconhecida(self) -> None:
        manifesto = inv.inventariar(self.raiz, minimo=3)
        self.assertEqual(0, manifesto["procedencia"][pr.HUMANO])
        self.assertEqual(5, manifesto["procedencia"][pr.DESCONHECIDA])
        self.assertTrue(manifesto["registro_de_procedencia"].startswith("sem registro"))

    def test_o_registro_no_disco_aparece_por_classe(self) -> None:
        csv = Path(self.tmp.name) / "proc.csv"
        csv.write_text(
            "uuid,livro,pagina,procedencia,rotulado_em\n"
            "aaaa1111,Yusupov,12,humano,2026-02-16\n"
            "aaaa2222,Yusupov,13,modelo,2026-02-16\n",
            encoding="utf-8",
        )
        manifesto = inv.inventariar(self.raiz, minimo=3, registro=pr.ler(csv))

        self.assertEqual(1, manifesto["procedencia"][pr.HUMANO])
        self.assertEqual(1, manifesto["procedencia"][pr.MODELO])
        por_classe = {c["pasta"]: c for c in manifesto["por_classe"]}
        self.assertEqual(1, por_classe["lower_a"]["procedencia"][pr.HUMANO])

    def test_o_manifesto_e_json_e_traz_o_total_e_a_contagem_por_classe(self) -> None:
        manifesto = inv.inventariar(self.raiz, minimo=3)
        redondo = json.loads(json.dumps(manifesto, ensure_ascii=False))
        self.assertEqual(5, redondo["recortes"])
        self.assertEqual(4, redondo["pastas"])
        self.assertEqual(4, len(redondo["por_classe"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
