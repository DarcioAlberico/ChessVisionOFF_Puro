"""Fonte de diagrama e rótulo de eixo numa regra só (S-836).

Havia duas regras de "esta fonte desenha tabuleiro" que discordavam: a de `pdf_text`, que tira da
legenda a linha que é o próprio tabuleiro, e a da `text/admissao`, que recusa a folha com uma fileira
de tabuleiro fora do diagrama. `Leipzig` era diagrama para uma e texto para a outra; `Schachfiguren`
e `XadrezFont`, o contrário. A tabela abaixo é conferida **pelo que cada consumidor faz**, e não pela
expressão que ele usa por dentro.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import varredura

from chess_diagram_ocr.pdf_text import _is_diagram_font_row
from chess_diagram_ocr.text import admissao

NOMES = (
    "ChessMerida",
    "ABCDEF+ChessMerida",
    "Chess-Merida",
    "Chess Merida Regular",
    "SkakNew-Diagram",
    "ChessAlpha",
    "UsualChess",
    "Leipzig",
    "Kingdom",
    "Linares",
    "Alpha",
    "Echecs",
    "Ajedrez",
    "Schachfiguren",
    "XadrezFont",
    "DiagramTT",
    "SkakNew-Figurine",
    "SkakNew-Figurine-Bold",
    "FigurineSymbol-T1-Regular",
    "TimesNewRomanPSMT",
    "Minion-Regular",
)


def _pdf_text_le_como_diagrama(nome: str) -> bool:
    """A linha "Steinitz" só cai da legenda se a fonte dela for de diagrama."""
    return _is_diagram_font_row("Steinitz", [nome])


def _admissao_le_como_diagrama(nome: str) -> bool:
    """Oito caracteres encostados, fora de qualquer diagrama, só recusam a folha em fonte de diagrama."""
    caixas = tuple((10.0 * i, 0.0, 10.0 * i + 9.5, 10.0) for i in range(8))
    trecho = admissao.Trecho(fonte=nome, texto="abcdefgh", bbox=(0.0, 0.0, 80.0, 10.0), caixas=caixas)
    return admissao.decidir([trecho], []).criterio == admissao.FILEIRA_FORA


class UmaRegraSoTests(unittest.TestCase):
    def test_os_dois_consumidores_concordam(self) -> None:
        discordam = [
            (nome, _pdf_text_le_como_diagrama(nome), _admissao_le_como_diagrama(nome))
            for nome in NOMES
            if _pdf_text_le_como_diagrama(nome) != _admissao_le_como_diagrama(nome)
        ]
        self.assertEqual(discordam, [], "(fonte, pdf_text, admissao)")

    def test_figurina_nao_e_diagrama(self) -> None:
        for nome in ("SkakNew-Figurine", "SkakNew-Figurine-Bold", "FigurineSymbol-T1-Regular"):
            with self.subTest(nome=nome):
                self.assertFalse(_pdf_text_le_como_diagrama(nome))

    def test_ninguem_importa_nome_privado_de_pdf_text(self) -> None:
        raiz = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr"
        privados = []
        for arquivo in varredura.fontes(raiz, recursivo=True, piso=300):
            if arquivo.name == "pdf_text.py":
                continue
            for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
                if isinstance(no, ast.ImportFrom) and (no.module or "").endswith("pdf_text"):
                    privados += [f"{arquivo.relative_to(raiz)}: {a.name}" for a in no.names if a.name.startswith("_")]
        self.assertEqual(privados, [])


if __name__ == "__main__":
    unittest.main()
