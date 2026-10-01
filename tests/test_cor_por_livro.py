"""Calibrador de cor por livro (C5 do ciclo 2 OCR/UI).

O que se trava: a medida separa contorno de preenchido; o calibrador só fala com amostras das
duas cores e fora da zona em que elas se misturam; a troca só acontece quando o par `(X, x)`
domina a casa; o tabuleiro sozinho responde com as casas em que o modelo não hesitou; uma
troca que tornasse a posição ilegal é descartada; e as casas medidas são as que o modelo viu
(a 180° e do ponto de vista das pretas).
"""

from __future__ import annotations

import unittest

import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.config import PIECE_TO_IDX
from chess_diagram_ocr.cor_por_livro import (
    CalibradorDeCor,
    apply_colour,
    casa_clara,
    cells_as_read,
    chave_da_amostra,
    medir,
    trocas_de_cor,
)
from chess_diagram_ocr.fen_utils import labels_from_fen, square_name
from chess_diagram_ocr.inference import prediction_from_probs
from chess_diagram_ocr.orientation import OrientedPrediction


def square_index(name: str) -> int:
    return next(index for index in range(64) if square_name(index) == name)


def cell(center: int, background: int = 235, size: int = 100) -> np.ndarray:
    """Uma casa sintética: fundo uniforme com um quadrado central de outro tom."""
    img = np.full((size, size, 3), background, dtype=np.uint8)
    a, b = int(size * 0.3), int(size * 0.7)
    img[a:b, a:b] = center
    return img


def board_from_placement(placement: str, *, white_center: int = 185, black_center: int = 100,
                         overrides: dict[str, int] | None = None) -> np.ndarray:
    """Um tabuleiro 800×800 em que cada peça branca é um contorno claro e cada preta um bloco
    escuro, com um pouco de variação por casa (a tinta de um livro não é uniforme) e, em
    `overrides`, o tom de casas escolhidas."""
    labels = labels_from_fen(placement)
    board = np.full((800, 800, 3), 235, dtype=np.uint8)
    for index, classe in enumerate(labels):
        row, col = divmod(index, 8)
        piece = _piece_name(classe)
        if piece == "empty":
            continue
        tone = (white_center if piece.isupper() else black_center) + (index % 7) - 3
        tone = (overrides or {}).get(square_name(index), tone)
        board[row * 100:(row + 1) * 100, col * 100:(col + 1) * 100] = cell(tone)
    return board


def _piece_name(classe: int) -> str:
    from chess_diagram_ocr.config import PIECE_CLASSES

    return PIECE_CLASSES[classe]


class MedidaTests(unittest.TestCase):
    def test_a_chave_e_a_peca_na_cor_da_casa(self) -> None:
        """Stefaniu p100 b2: um peão branco numa casa escura hachurada não se compara com os
        peões brancos das casas claras -- a chave carrega a cor da casa."""
        self.assertTrue(casa_clara(0))  # a8
        self.assertFalse(casa_clara(square_index("b2")))
        self.assertEqual(chave_da_amostra("q", square_index("d6")), "Qe")
        self.assertEqual(chave_da_amostra("P", square_index("a2")), "Pc")

    def test_a_medida_e_o_centro_e_nao_o_fundo(self) -> None:
        self.assertAlmostEqual(medir(cell(100)), 100.0)
        self.assertAlmostEqual(medir(cell(185)), 185.0)
        self.assertLess(medir(cell(100, background=250)), medir(cell(185, background=120)))


class CalibradorTests(unittest.TestCase):
    def test_sem_amostras_de_uma_cor_o_calibrador_se_abstem(self) -> None:
        calibrador = CalibradorDeCor(brancas={"Qe": [180.0, 190.0, 185.0, 182.0, 184.0, 186.0]},
                                     pretas={"Qe": [100.0, 110.0, 105.0, 102.0]})
        self.assertIsNone(calibrador.decidir(120.0, tipo="Qe").cor, "quatro pretas não bastam")

    def test_decide_alem_dos_extremos_com_margem_e_se_abstem_no_vao(self) -> None:
        calibrador = CalibradorDeCor(brancas={"Qe": [170.0, 180.0, 185.0, 190.0, 200.0, 195.0]},
                                     pretas={"Qe": [90.0, 100.0, 110.0, 120.0, 150.0, 130.0]})
        # Preta: abaixo de 170 − 10 e não acima das pretas aparadas (130) + 10; branca: acima
        # de 150 + 10 e não abaixo das brancas aparadas (180) − 10. No vão, ninguém diz.
        self.assertEqual(calibrador.decidir(80.0, tipo="Qe").cor, "b")
        self.assertEqual(calibrador.decidir(135.0, tipo="Qe").cor, "b")
        self.assertIsNone(calibrador.decidir(155.0, tipo="Qe").cor, "abaixo das brancas, mas acima do que as pretas mostram")
        self.assertEqual(calibrador.decidir(210.0, tipo="qe").cor, "w")
        self.assertEqual(calibrador.decidir(175.0, tipo="Qe").cor, "w")
        self.assertIsNone(calibrador.decidir(165.0, tipo="Qe").cor, "acima das pretas, mas abaixo do que as brancas mostram")
        self.assertEqual(calibrador.decidir(165.0, tipo="Qe").zona, (160.0, 160.0))
        self.assertIsNone(calibrador.decidir(80.0, tipo="Qc").cor, "a dama da casa clara é outra régua")

    def test_a_branca_mais_escura_e_o_piso_e_nao_um_quantil(self) -> None:
        """Koblenz p51 g1: um rei branco que mede o p5 dos reis brancos não é um rei preto."""
        calibrador = CalibradorDeCor(
            brancas={"Ke": [146.0, 153.0, 156.0, 158.0, 159.0, 159.0, 166.0, 167.0, 168.0, 170.0, 171.0]},
            pretas={"Ke": [115.0, 117.0, 119.0, 120.0, 124.0, 125.0, 127.0, 128.0, 135.0, 140.0, 144.0]})
        self.assertIsNone(calibrador.decidir(153.0, tipo="Ke").cor)
        self.assertIsNone(calibrador.decidir(140.0, tipo="Ke").cor, "seis abaixo da branca mais escura: menos que a margem")
        self.assertEqual(calibrador.decidir(125.0, tipo="Ke").cor, "b")
        self.assertEqual(calibrador.decidir(60.0, tipo="Ke").cor, "b", "mais escuro que toda preta continua preto")

    def test_outra_peca_nao_e_regua_desta(self) -> None:
        """Medido no Koblenz: a régua de todas as peças juntas trocava um cavalo branco (a
        crina escura) e uma torre preta (as ameias claras). Só o mesmo tipo decide."""
        calibrador = CalibradorDeCor(brancas={"Qe": [170.0, 180.0, 185.0, 190.0, 200.0, 195.0]},
                                     pretas={"Qe": [90.0, 100.0, 110.0, 120.0, 150.0, 130.0]})
        self.assertIsNone(calibrador.decidir(80.0, tipo="Ne").cor)

    def test_distribuicoes_sobrepostas_nao_sao_regua(self) -> None:
        """Niemeijer/Stefaniu, e as torres do Koblenz: pretas 136–224, brancas 167–210 -- a
        régua não separa e não fala, nem nos extremos (uma torre branca a 151 estava abaixo
        da branca mais escura e dentro das pretas, e era trocada)."""
        calibrador = CalibradorDeCor(brancas={"Rc": [167.0, 182.0, 183.0, 190.0, 197.0, 201.0, 204.0, 205.0, 210.0]},
                                     pretas={"Rc": [136.0, 155.0, 166.0, 180.0, 215.0, 216.0, 224.0]})
        for valor in (90.0, 130.0, 151.0, 200.0, 240.0):
            self.assertIsNone(calibrador.decidir(valor, tipo="Rc").cor, valor)

    def test_uma_amostra_de_outra_impressao_nao_cala_as_outras(self) -> None:
        """Koblenz, damas de casa clara: quatro pretas a 117–142 e uma hachurada a 218; brancas
        176–211. Pelos extremos as cores se tocariam (218 > 176) e as duas damas `Q→q` de
        p30/p50 ficariam sem régua; aparada uma de cada lado, separam -- e 127 é preta.
        Duas fora (218 e 200) já não: a régua não separa."""
        calibrador = CalibradorDeCor(brancas={"Qc": [176.0, 180.0, 185.0, 190.0, 195.0, 200.0, 205.0, 211.0]},
                                     pretas={"Qc": [117.0, 125.0, 138.0, 142.0, 218.0]})
        self.assertEqual(calibrador.decidir(127.0, tipo="Qc").cor, "b")
        self.assertIsNone(calibrador.decidir(160.0, tipo="Qc").cor, "acima das pretas aparadas + margem (152): não é preta plausível")
        self.assertIsNone(calibrador.decidir(200.0, tipo="Qc").cor, "acima da preta mais clara + margem? não: 218 + 10")
        duas_fora = CalibradorDeCor(brancas={"Qc": [176.0, 180.0, 185.0, 190.0, 195.0, 200.0, 205.0, 211.0]},
                                    pretas={"Qc": [117.0, 125.0, 138.0, 142.0, 200.0, 218.0]})
        self.assertIsNone(duas_fora.decidir(127.0, tipo="Qc").cor)

    def test_serializa_e_recusa_outra_medida(self) -> None:
        calibrador = CalibradorDeCor(brancas={"Qc": [1.0]}, pretas={"Qc": [2.0]}, diagramas=3)
        again = CalibradorDeCor.from_dict(calibrador.as_dict())
        self.assertEqual((again.brancas, again.pretas, again.diagramas), ({"Qc": [1.0]}, {"Qc": [2.0]}, 3))
        self.assertIsNone(CalibradorDeCor.from_dict({"medida": "outra", "brancas": {"Qc": [1.0]}, "pretas": {"Qc": [2.0]}}))
        self.assertIsNone(CalibradorDeCor.from_dict({"medida": "centro40-v1", "brancas": [1.0], "pretas": [2.0]}))
        self.assertIsNone(CalibradorDeCor.from_dict(None))


#: O Koblenz p30: a dama de d6 é preta, lida branca a 1,00; o resto certo.
TRUTH = "r4rk1/1p3ppp/p2q4/3p4/3P4/2N2N2/PP3PPP/R2Q1RK1"
MISREAD = "r4rk1/1p3ppp/p2Q4/3p4/3P4/2N2N2/PP3PPP/R2Q1RK1"
#: As damas do livro, corrigidas noutras páginas: a régua que decide d6.
LIVRO = CalibradorDeCor(brancas={"Qe": [178.0, 182.0, 185.0, 190.0, 180.0, 188.0]},
                        pretas={"Qe": [98.0, 102.0, 105.0, 110.0, 100.0, 108.0]}, diagramas=6)


def _misread() -> tuple[np.ndarray, list[int]]:
    probs = probs_for_fen(MISREAD, confidence=0.995)
    d6 = square_index("d6")
    probs[d6] = 0.0
    probs[d6, PIECE_TO_IDX["Q"]] = 0.996  # a confiança alta do campo
    probs[d6, PIECE_TO_IDX["q"]] = 0.004
    return probs, [int(i) for i in probs.argmax(axis=1)]


class TrocasTests(unittest.TestCase):
    def test_o_livro_troca_a_cor_que_a_tinta_contradiz(self) -> None:
        """A dama de d6 lida branca a 0,996: as damas corrigidas do livro dizem preta."""
        probs, lidos = _misread()
        board = board_from_placement(TRUTH, overrides={"d6": 92})
        from chess_diagram_ocr.board_detection import split_board_into_cells

        trocas = trocas_de_cor(probs, lidos, split_board_into_cells(board), LIVRO)
        self.assertEqual([(t.casa, t.de, t.para) for t in trocas],
                         [(square_index("d6"), PIECE_TO_IDX["Q"], PIECE_TO_IDX["q"])])
        self.assertEqual(trocas[0].veredito.cor, "b")
        self.assertEqual(trocas_de_cor(probs, lidos, split_board_into_cells(board), None), [],
                         "sem o livro, uma dama de cada cor no tabuleiro não é amostra")

    def test_sem_perfil_do_livro_nada_e_trocado(self) -> None:
        """O tabuleiro não é amostra de si: sem o perfil (C6) o calibrador cala."""
        probs, lidos = _misread()
        board = board_from_placement(TRUTH, overrides={"d6": 92})
        from chess_diagram_ocr.board_detection import split_board_into_cells

        self.assertEqual(trocas_de_cor(probs, lidos, split_board_into_cells(board), None), [])
        self.assertEqual(trocas_de_cor(probs, lidos, split_board_into_cells(board), CalibradorDeCor()), [])

    def test_so_o_par_de_cores_dominando_a_casa_e_julgado(self) -> None:
        probs, lidos = _misread()
        d6 = square_index("d6")
        probs[d6] = 0.0
        probs[d6, PIECE_TO_IDX["Q"]] = 0.60
        probs[d6, PIECE_TO_IDX["K"]] = 0.35  # a dúvida é de peça, não de cor
        probs[d6, PIECE_TO_IDX["q"]] = 0.05
        board = board_from_placement(TRUTH)
        from chess_diagram_ocr.board_detection import split_board_into_cells

        self.assertEqual(trocas_de_cor(probs, lidos, split_board_into_cells(board), LIVRO), [])

    def test_a_amostra_do_livro_decide_e_so_a_da_mesma_chave(self) -> None:
        """Final com poucas peças: só o perfil do livro dá as amostras, e só as da chave certa."""
        truth = "8/8/3q4/8/8/8/5K2/7k"
        misread = "8/8/3Q4/8/8/8/5K2/7k"
        probs = probs_for_fen(misread, confidence=0.995)
        d6 = square_index("d6")
        probs[d6] = 0.0
        probs[d6, PIECE_TO_IDX["Q"]] = 0.9
        probs[d6, PIECE_TO_IDX["q"]] = 0.1
        lidos = [int(i) for i in probs.argmax(axis=1)]
        board = board_from_placement(truth)
        from chess_diagram_ocr.board_detection import split_board_into_cells

        cells = split_board_into_cells(board)
        self.assertEqual(trocas_de_cor(probs, lidos, cells, None), [], "sem perfil não decide")
        livro = LIVRO
        trocas = trocas_de_cor(probs, lidos, cells, livro)
        self.assertEqual([t.casa for t in trocas], [d6])
        outra = CalibradorDeCor(brancas={"Ne": LIVRO.brancas["Qe"]}, pretas={"Ne": LIVRO.pretas["Qe"]})
        self.assertEqual(trocas_de_cor(probs, lidos, cells, outra), [], "cavalos não são régua de damas")

    def test_apply_colour_troca_e_registra_e_recusa_a_posicao_ilegal(self) -> None:
        probs, _ = _misread()
        prediction = prediction_from_probs(probs, constrained=False)
        board = board_from_placement(TRUTH, overrides={"d6": 92})
        oriented = OrientedPrediction(prediction=prediction, rotation=0, margin=1.0, ambiguous=False, reason="")
        trocada, trocas, motivo = apply_colour(prediction, board, oriented, LIVRO)
        self.assertEqual(trocada.fen_board, TRUTH)
        self.assertEqual([t.casa for t in trocas], [square_index("d6")])
        self.assertIn("cor pela tinta", motivo)
        self.assertEqual(trocada.decode.changed_squares, [(square_index("d6"), PIECE_TO_IDX["Q"], PIECE_TO_IDX["q"])])

        # A troca que tornaria a posição ilegal (dois reis pretos) é descartada inteira.
        misread = "r4rk1/1p3ppp/p2q4/3p4/3P4/2N2N2/PP3PPP/R2Q1RK1"  # certo…
        truth_like = "r4rk1/1p3ppp/p2q4/3p4/3P4/2N2N2/PP3PPP/R2Q1Rk1"  # …mas a tinta diz rei preto em g1
        probs2 = probs_for_fen(misread, confidence=0.995)
        g1 = square_index("g1")
        probs2[g1] = 0.0
        probs2[g1, PIECE_TO_IDX["K"]] = 0.95
        probs2[g1, PIECE_TO_IDX["k"]] = 0.05
        prediction2 = prediction_from_probs(probs2, constrained=False)
        board2 = board_from_placement(truth_like, overrides={"g1": 92})
        oriented2 = OrientedPrediction(prediction=prediction2, rotation=0, margin=1.0, ambiguous=False, reason="")
        reis = CalibradorDeCor(brancas={"Kc": LIVRO.brancas["Qe"], "Ke": LIVRO.brancas["Qe"]},
                               pretas={"Kc": LIVRO.pretas["Qe"], "Ke": LIVRO.pretas["Qe"]})
        same, nothing, motivo2 = apply_colour(prediction2, board2, oriented2, reis)
        self.assertIs(same, prediction2)
        self.assertEqual(nothing, [])
        self.assertIn("ilegal", motivo2)


class OrientacaoTests(unittest.TestCase):
    def test_as_casas_medidas_sao_as_que_o_modelo_viu(self) -> None:
        board = np.zeros((800, 800, 3), dtype=np.uint8)
        board[0:100, 0:100] = 255  # a8 branca, o resto preto
        prediction = prediction_from_probs(probs_for_fen("8/8/8/8/8/8/8/8"), constrained=False)
        upright = OrientedPrediction(prediction=prediction, rotation=0, margin=1.0, ambiguous=False, reason="")
        self.assertEqual(cells_as_read(board, upright)[0].mean(), 255.0)
        rotated = OrientedPrediction(prediction=prediction, rotation=180, margin=1.0, ambiguous=False, reason="")
        self.assertEqual(cells_as_read(board, rotated)[63].mean(), 255.0)
        black_pov = OrientedPrediction(prediction=prediction, rotation=0, margin=1.0, ambiguous=False,
                                       reason="", black_point_of_view=True)
        self.assertEqual(cells_as_read(board, black_pov)[63].mean(), 255.0)


if __name__ == "__main__":
    unittest.main()
