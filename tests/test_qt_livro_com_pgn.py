"""O PGN do livro ligado à janela (S-590, S-592).

Um PDF de verdade, montado aqui com o PyMuPDF: duas páginas, cada uma com a imagem de um tabuleiro
e a legenda «Position after: ...» logo abaixo, e um sumário com o capítulo. Os painéis são falsos
que anotam o que receberam -- o que se afirma é o fio, e não o desenho do Resultado.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import chess
import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr import livro_com_pgn as lp

if TEM_PYQT:
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QWidget

    from chess_diagram_ocr.qt.livro_com_pgn import LivroComPgn

PGN = (
    '[Event "Chapter 1"]\n[Site "Game 1"]\n\n'
    "1.e4 e6 2.d4 d5 3.Nc3 c5 4.exd5 exd5 5.dxc5 *\n"
)
CAIXA = (171.0, 30.0, 441.0, 300.0)


def _campo(*lances: str) -> str:
    tabuleiro = chess.Board()
    for lance in lances:
        tabuleiro.push_san(lance)
    return tabuleiro.board_fen()


DEPOIS_DE_C5 = _campo("e4", "e6", "d4", "d5", "Nc3", "c5")
DEPOIS_DE_DXC5 = _campo("e4", "e6", "d4", "d5", "Nc3", "c5", "exd5", "exd5", "dxc5")
DEPOIS_DE_EXD5 = _campo("e4", "e6", "d4", "d5", "Nc3", "c5", "exd5")


def _pdf(caminho: Path) -> Path:
    import fitz

    from chess_diagram_ocr.desenho_de_diagrama import png_do_diagrama

    documento = fitz.open()
    for lance, campo in (("3...c5?!", DEPOIS_DE_C5), ("5.dxc5", DEPOIS_DE_DXC5)):
        pagina = documento.new_page(width=612, height=792)
        pagina.insert_image(fitz.Rect(*CAIXA), stream=png_do_diagrama(campo, lado_px=270))
        pagina.insert_text((30, 326), f"Position after: {lance}", fontsize=11)
        if lance == "3...c5?!":
            pagina.insert_text((30, 600), "Position after: 4.exd5", fontsize=11)  # a imagem que o PDF perdeu
    documento.set_toc([[1, "Chapter 1 – Odd 3rd moves", 1]])
    documento.save(caminho)
    documento.close()
    return caminho


class _Painel:
    def __init__(self) -> None:
        self.adotados: list[tuple[int, str, str, str]] = []
        self.modelo = SimpleNamespace(items=[], clamped_index=lambda: 0)

    def adotar_do_livro(self, indice: int, item: object, placement: str, lado: str, nota: str) -> bool:
        self.adotados.append((indice, placement, lado, nota))
        return True


class _Revisao:
    def __init__(self) -> None:
        self.recebidos: list = []

    def acrescentar(self, itens: list) -> int:
        novos = [i for i in itens if (i.page_index, i.diagram_index) not in {(r.page_index, r.diagram_index) for r in self.recebidos}]
        self.recebidos.extend(novos)
        return len(novos)


def _item(placement: str) -> SimpleNamespace:
    return SimpleNamespace(
        placement=placement, bbox_pdf=CAIXA, board_rgb=np.zeros((32, 32, 3), dtype=np.uint8), min_confidence=0.9
    )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LivroComPgnTests(unittest.TestCase):
    def setUp(self) -> None:
        aplicacao()
        self.pasta = pasta_temporaria(self)
        self.pdf = _pdf(self.pasta / "livro.pdf")
        self.pgn = self.pasta / "livro.pgn"
        self.pgn.write_text(PGN, encoding="utf-8")
        trava = mock.patch.object(lp, "ARQUIVO_DAS_ASSOCIACOES", self.pasta / "livros_com_pgn.json")
        trava.start()
        self.addCleanup(trava.stop)
        self.janela = QWidget()
        self.addCleanup(descartar, self.janela)
        self.painel, self.revisao = _Painel(), _Revisao()
        self.texto = mock.Mock()
        self.estudo = mock.Mock()
        self.galeria = mock.Mock()
        self.ditos: list[str] = []
        self.atuais: list = []
        self.livro = LivroComPgn(
            self.janela,
            dizer=self.ditos.append,
            pdf_atual=lambda: self.pdf,
            itens_atuais=lambda: self.atuais,
            painel=self.painel,
            revisao=self.revisao,
            texto=self.texto,
            estudo=self.estudo,
            galeria=self.galeria,
            focar=lambda _p: None,
            ir_para_pagina=lambda _p: None,
        )

    def _com_pgn(self, pagina: int = 0, itens: list | None = None) -> None:
        self.assertTrue(lp.associar(self.pdf, self.pgn))
        self.livro.aplicar(pagina, itens or [])  # a primeira pergunta pelo livro dispara a leitura do índice
        for _ in range(300):
            if self.livro.indice is not None:
                break
            QTest.qWait(10)
        self.assertIsNotNone(self.livro.indice, "o índice do PGN não chegou")

    def test_a_associacao_e_lembrada_pelo_conteudo_do_pdf(self) -> None:
        lp.associar(self.pdf, self.pgn)
        copia = self.pasta / "copia.pdf"
        copia.write_bytes(self.pdf.read_bytes())
        self.assertEqual(self.pgn.resolve(), lp.pgn_associado(copia))
        self.assertTrue(lp.esquecer(copia))
        self.assertIsNone(lp.pgn_associado(self.pdf))

    def test_a_pagina_lida_adota_a_posicao_e_o_lado_do_livro(self) -> None:
        self._com_pgn()
        uma_casa = DEPOIS_DE_C5.replace("rnbqkbnr", "rbbqkbnr")
        self.livro.aplicar(0, [_item(uma_casa)])
        ((indice, campo, lado, nota),) = self.painel.adotados
        self.assertEqual((0, DEPOIS_DE_C5, "w"), (indice, campo, lado))
        self.assertIn("3...c5", nota)
        self.assertIn("corrigiu 1 casa", nota)
        self.texto.definir_posicoes.assert_called_with(0, [DEPOIS_DE_C5])

    def test_a_discordancia_vai_a_revisao_uma_vez_e_nao_e_adotada(self) -> None:
        self._com_pgn()
        errado = chess.Board().board_fen()
        self.livro.aplicar(1, [_item(errado)])
        self.livro.aplicar(1, [_item(errado)])
        self.assertEqual([], self.painel.adotados)
        (item,) = self.revisao.recebidos
        self.assertEqual((1, 1), (item.page_index, item.diagram_index))
        self.assertEqual(DEPOIS_DE_DXC5, item.fen.split()[0])
        self.assertIn("PGN do livro discorda", item.reasons[0])

    def test_a_pagina_lida_antes_do_indice_recebe_o_livro_quando_ele_chega(self) -> None:
        # A primeira página lida é a que dispara a leitura do PGN, e o índice chega depois dela --
        # com a tela, às vezes, já em outra folha. Vale a página dos itens, e não a da tela.
        self.atuais = [_item(DEPOIS_DE_DXC5)]
        self._com_pgn(1, self.atuais)
        ((indice, campo, lado, _nota),) = self.painel.adotados
        self.assertEqual((0, DEPOIS_DE_DXC5, "b"), (indice, campo, lado))
        self.texto.definir_posicoes.assert_called_with(1, [DEPOIS_DE_DXC5])

    def test_o_indice_atrasado_nao_vai_a_itens_que_ja_sairam_da_tela(self) -> None:
        self._com_pgn(1, [_item(DEPOIS_DE_DXC5)])  # `self.atuais` é outra lista: a página mudou
        self.assertEqual([], self.painel.adotados)

    def test_o_livro_aberto_ja_comeca_a_ler_o_pgn_e_o_livro_inteiro(self) -> None:
        lp.associar(self.pdf, self.pgn)
        self.livro.livro_aberto()
        for _ in range(300):
            if self.livro.indice is not None:
                break
            QTest.qWait(10)
        (faltando,) = [d for d in self.livro.do_livro if d.estado == lp.FALTANDO]
        self.assertEqual((1, "4.exd5", DEPOIS_DE_EXD5), (faltando.pagina, faltando.legenda, faltando.fen.split()[0]))
        self.assertIn("1 diagrama(s) do livro faltam no PDF", self.ditos[-1])

    def test_por_na_folha_manda_a_aba_texto_os_que_faltam_naquela_folha(self) -> None:
        self._com_pgn()
        self.texto.folha_atual.return_value = (0, 2)
        self.texto.inserir_diagramas_do_livro.return_value = 1
        self.livro.por_na_folha()
        self.texto.inserir_diagramas_do_livro.assert_called_once_with(0, [("4.exd5", DEPOIS_DE_EXD5)])
        self.texto.folha_atual.return_value = (1, 2)
        self.livro.por_na_folha()
        self.assertEqual(1, self.texto.inserir_diagramas_do_livro.call_count, "na folha 2 nada falta")
        self.assertIn("folha 2", self.ditos[-1])

    def test_o_duplo_clique_no_inserido_abre_a_arvore_do_autor(self) -> None:
        self._com_pgn()
        self.livro._estudar_o_inserido(0, DEPOIS_DE_EXD5)
        jogo, caminho = self.estudo.abrir_no_livro.call_args.args
        from chess_diagram_ocr.estudo import no_em

        self.assertEqual(DEPOIS_DE_EXD5, no_em(jogo, caminho).board().board_fen())

    def test_a_galeria_do_livro_recebe_os_que_conferem(self) -> None:
        from chess_diagram_ocr.gallery_scan import GalleryEntry

        self._com_pgn()
        entradas = [GalleryEntry(0, 0, DEPOIS_DE_C5), GalleryEntry(1, 0, chess.Board().board_fen())]
        self.galeria.model = SimpleNamespace(pdf_path=self.pdf, is_empty=False, index=SimpleNamespace(entries=entradas))
        self.livro.preencher_a_galeria()
        (casamentos,), opcoes = self.galeria.preencher_de_fora.call_args
        self.assertEqual([(0, 0)], [c.key for c in casamentos])
        self.assertEqual(1, opcoes["discordam"])

    def test_a_galeria_de_outro_livro_nao_e_preenchida(self) -> None:
        self._com_pgn()
        self.galeria.model = SimpleNamespace(pdf_path=self.pasta / "outro.pdf", is_empty=False, index=SimpleNamespace(entries=[]))
        self.livro.preencher_a_galeria()
        self.galeria.preencher_de_fora.assert_not_called()
        self.assertIn("varra-o antes", self.ditos[-1])

    def test_sem_pgn_nada_muda(self) -> None:
        self.livro.aplicar(0, [_item(DEPOIS_DE_C5)])
        self.assertEqual([], self.painel.adotados)
        self.texto.definir_posicoes.assert_not_called()

    def test_estudar_abre_a_partida_inteira_no_no_do_diagrama(self) -> None:
        self._com_pgn()
        self.livro.aplicar(0, [_item(DEPOIS_DE_C5)])
        self.painel.modelo.items = [object()]
        self.livro.estudar_na_arvore()
        jogo, caminho = self.estudo.abrir_no_livro.call_args.args
        self.assertEqual("1", jogo.headers["Diagram"])
        from chess_diagram_ocr.estudo import no_em

        no = no_em(jogo, caminho)
        assert no is not None
        self.assertEqual(DEPOIS_DE_C5, no.board().board_fen())
        self.assertEqual("dxc5", jogo.end().san(), "a partida vai inteira, e não só até o diagrama")


if __name__ == "__main__":
    unittest.main()
