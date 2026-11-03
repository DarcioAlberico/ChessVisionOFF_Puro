"""O livro como lote do dataset: a pasta com o PDF digital e o PGN dele (S-593).

O PDF é montado aqui: três páginas com a imagem de um tabuleiro e a legenda abaixo. A terceira
repete na outra linha do capítulo a mesma jogada da segunda («3.Nc3» depois de 1.e4 e de 1.d4) --
é o caso em que a legenda sozinha não decide, e a leitura do modelo escolhe.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

import chess
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import importacao_de_imagens as imp

PGN = (
    '[Event "Chapter 1"]\n[Site "Game 1"]\n\n\n'  # a linha em branco a mais do Harikrishna (S-585)
    "1.e4 e6 2.d4 d5 3.Nc3 *\n\n"
    '[Event "Chapter 1"]\n[Site "Game 2"]\n\n'
    "1.d4 d5 2.c4 e6 3.Nc3 *\n"
)


def _campo(*lances: str) -> str:
    tabuleiro = chess.Board()
    for lance in lances:
        tabuleiro.push_san(lance)
    return tabuleiro.board_fen()


FRANCESA = _campo("e4", "e6", "d4", "d5", "Nc3")
GAMBITO = _campo("d4", "d5", "c4", "e6", "Nc3")


def _pasta_do_livro(pasta: Path) -> Path:
    import fitz

    from chess_diagram_ocr.desenho_de_diagrama import png_do_diagrama

    livro = pasta / "livro"
    livro.mkdir()
    documento = fitz.open()
    for lance, campo in (("2.d4", _campo("e4", "e6", "d4")), ("3.Nc3", FRANCESA), ("3.Nc3", GAMBITO)):
        pagina = documento.new_page(width=612, height=792)
        pagina.insert_image(fitz.Rect(171, 30, 441, 300), stream=png_do_diagrama(campo, lado_px=270))
        pagina.insert_text((30, 326), f"Position after: {lance}", fontsize=11)
    documento.set_toc([[1, "Chapter 1 – A francesa", 1]])
    documento.save(livro / "📚Autor. Livro.pdf")
    documento.close()
    (livro / "Autor. Livro.pgn").write_text(PGN, encoding="utf-8")
    return livro


class LoteDoLivroTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.livro = _pasta_do_livro(self.pasta)
        self.lotes = self.pasta / "lotes"
        self.lote, self.arquivo = imp.abrir_lote(self.livro, imp.COM_PGN, diretorio=self.lotes)

    def test_cada_diagrama_com_a_fen_a_pagina_e_a_imagem_do_livro(self) -> None:
        self.assertEqual(3, len(self.lote))
        primeiro = self.lote.itens[0]
        self.assertEqual(("Autor. Livro", 1, 1, "b"), (primeiro.livro, primeiro.indice, primeiro.pagina, primeiro.lado))
        self.assertEqual(_campo("e4", "e6", "d4"), imp.campo_de_pecas(primeiro.fen_da_fonte))
        imagem = imp.ler_imagem(self.lote.caminho_da_imagem(primeiro))
        self.assertEqual(3, imagem.shape[2])
        self.assertTrue(str(self.lote.caminho_da_imagem(primeiro)).startswith(str(self.lotes)), "a imagem não vai para a pasta do livro")

    def test_a_legenda_ambigua_leva_os_candidatos_e_a_leitura_escolhe(self) -> None:
        segundo, terceiro = self.lote.itens[1], self.lote.itens[2]
        self.assertEqual({FRANCESA, GAMBITO}, {imp.campo_de_pecas(f) for f in terceiro.candidatos})
        lido = imp.com_a_leitura(terceiro, GAMBITO, imp.RECORTE_DETECTADO)
        self.assertEqual(GAMBITO, imp.campo_de_pecas(lido.fen_da_fonte))
        self.assertTrue(imp.concorda(lido))
        self.assertEqual(segundo.candidatos, terceiro.candidatos)

    def test_sem_candidatos_a_leitura_nao_troca_a_fonte(self) -> None:
        primeiro = self.lote.itens[0]
        lido = imp.com_a_leitura(primeiro, chess.Board().board_fen(), imp.RECORTE_DETECTADO)
        self.assertEqual(primeiro.fen_da_fonte, lido.fen_da_fonte)
        self.assertFalse(imp.concorda(lido))

    def test_reabrir_guarda_o_candidato_que_a_leitura_escolheu(self) -> None:
        self.lote.itens[2] = imp.com_a_leitura(self.lote.itens[2], GAMBITO, imp.RECORTE_DETECTADO)
        self.lote.salvar(self.arquivo)
        reaberto, _ = imp.abrir_lote(self.livro, imp.COM_PGN, diretorio=self.lotes)
        self.assertEqual(GAMBITO, imp.campo_de_pecas(reaberto.itens[2].fen_da_fonte))
        self.assertEqual(GAMBITO, reaberto.itens[2].fen_do_modelo)

    def test_a_amostra_registra_o_livro_e_a_pagina(self) -> None:
        import csv

        import numpy as np

        csv_path, samples = self.pasta / "labels.csv", self.pasta / "samples"
        item = self.lote.itens[1]
        self.lote.itens[1] = replace(item, fen_do_modelo=imp.campo_de_pecas(item.fen_da_fonte))
        imp.gravar_item(
            self.lote, 1, np.zeros((256, 256, 3), dtype=np.uint8), item.fen_da_fonte,
            lado=item.lado, recorte=imp.RECORTE_DETECTADO, csv_path=csv_path, samples_dir=samples,
            corrected_by=imp.IMPORTADO_COM_FEN, diretorio=self.lotes,
        )
        with csv_path.open(encoding="utf-8") as arquivo:
            (linha,) = list(csv.DictReader(arquivo))
        self.assertEqual(("Autor. Livro", "2", "2"), (linha["source_pdf"], linha["source_page"], linha["source_diagram"]))

    def test_pasta_sem_o_par_e_recusada(self) -> None:
        vazia = self.pasta / "vazia"
        vazia.mkdir()
        with self.assertRaises(FileNotFoundError):
            imp.abrir_lote(vazia, imp.COM_PGN, diretorio=self.lotes)


if __name__ == "__main__":
    unittest.main()
