"""Cada diagrama do PDF digital com o seu nó do PGN (S-587, S-588).

As páginas são dicionários na forma do `page.get_text("dict")` do PyMuPDF, com as caixas que o
Harikrishna tem: imagem de 270 pt e a legenda «Position after: ...» logo abaixo. Os dois defeitos
que a medição achou estão travados aqui: a legenda cuja imagem faltou pegava a imagem da legenda
de cima, e a imagem do pé da página era lida na página da legenda.
"""

from __future__ import annotations

import unittest

import chess
import chess.pgn

from chess_diagram_ocr import livro_com_pgn as lp
from chess_diagram_ocr.pgn_do_livro import IndiceDoLivro, fluxo_tolerante

PGN = (
    '[Event "Chapter 1"]\n[Site "Game 1"]\n\n'
    "1.e4 e6 2.d4 d5 3.Nc3 c5 (3...a6 4.Nf3) 4.exd5 exd5 5.dxc5 *\n\n"
    '[Event "Chapter 2"]\n[Site "Game 1"]\n\n'
    "1.e4 e6 2.d4 d5 3.Nc3 Nc6 4.Nf3 *\n"
)


def _indice() -> IndiceDoLivro:
    fluxo = fluxo_tolerante(PGN)
    partidas = []
    while (jogo := chess.pgn.read_game(fluxo)) is not None:
        partidas.append(jogo)
    return IndiceDoLivro(partidas)


def _campo(*lances: str) -> str:
    tabuleiro = chess.Board()
    for lance in lances:
        tabuleiro.push_san(lance)
    return tabuleiro.board_fen()


def _imagem(topo: float) -> dict:
    return {"type": 1, "bbox": (171.0, topo, 441.0, topo + 270.0)}


def _legenda(topo: float, lance: str) -> dict:
    return {
        "type": 0,
        "bbox": (30.0, topo, 160.0, topo + 13.0),
        "lines": [{"bbox": (30.0, topo, 160.0, topo + 13.0), "spans": [{"text": f"Position after: {lance}"}]}],
    }


def _pagina(*blocos: dict) -> dict:
    return {"blocks": list(blocos)}


SUMARIO = [[1, "Chapter 1 – Odd 3rd moves", 1], [1, "Chapter 2 – 3...Nc6", 3]]


class PareamentoTests(unittest.TestCase):
    def test_a_imagem_com_a_legenda_logo_abaixo(self) -> None:
        diagramas, sobra = lp.diagramas_da_pagina(_pagina(_imagem(30), _legenda(316, "5.dxc5")), 1)
        self.assertEqual([("5.dxc5", (171.0, 30.0, 441.0, 300.0))], [(d.legenda, d.caixa) for d in diagramas])
        self.assertIsNone(sobra)

    def test_a_legenda_sem_imagem_nao_pega_a_da_outra(self) -> None:
        """A página 21 do Harikrishna: uma imagem e quatro legendas; as três de baixo faltaram."""
        pagina = _pagina(_imagem(30), _legenda(316, "8.Be2"), _legenda(452, "11.Ne5"), _legenda(587, "15.Bg5!"))
        diagramas, _ = lp.diagramas_da_pagina(pagina, 21)
        self.assertEqual([True, False, False], [d.caixa is not None for d in diagramas])

    def test_a_imagem_do_pe_da_pagina_e_da_legenda_que_abre_a_seguinte(self) -> None:
        """Páginas 26 e 27: a imagem fica no pé de uma, a legenda no alto da outra -- e a imagem
        continua sendo da página 26, que é onde ela é lida."""
        _, sobra = lp.diagramas_da_pagina(_pagina(_imagem(30), _legenda(315, "19.c3"), _imagem(477)), 26)
        self.assertIsNotNone(sobra)
        diagramas, _ = lp.diagramas_da_pagina(_pagina(_legenda(32, "14.Ba3"), _legenda(167, "18.Nc4")), 27, sobra_da_anterior=sobra)
        self.assertEqual((26, 27, sobra), (diagramas[0].pagina, diagramas[0].pagina_da_legenda, diagramas[0].caixa))
        self.assertIsNone(diagramas[1].caixa)

    def test_imagem_sem_legenda_abaixo_fica_para_a_pagina_seguinte(self) -> None:
        """Se a seguinte não a reclamar, `casar_livro` a devolve como diagrama sem legenda desta
        página (`test_sem_legenda_a_posicao_lida_acha_o_no`)."""
        texto = {"type": 0, "lines": [{"bbox": (30.0, 400.0, 500.0, 413.0), "spans": [{"text": "8...Bb4! White"}]}]}
        diagramas, sobra = lp.diagramas_da_pagina(_pagina(_imagem(30), texto), 5)
        self.assertEqual(([], (171.0, 30.0, 441.0, 300.0)), (diagramas, sobra))

    def test_imagem_sem_legenda_entre_duas_com_legenda_e_diagrama(self) -> None:
        pagina = _pagina(_imagem(30), _imagem(320), _legenda(600, "5.dxc5"))
        diagramas, _ = lp.diagramas_da_pagina(pagina, 5)
        self.assertEqual([("", 30.0), ("5.dxc5", 320.0)], [(d.legenda, d.caixa[1]) for d in diagramas if d.caixa])


class SumarioTests(unittest.TestCase):
    def test_o_capitulo_pelo_titulo_e_por_palavra_inteira(self) -> None:
        inicios = lp.capitulos_do_sumario(
            [[1, "Introduction", 8], [1, "Chapter 1 – Odd", 11], [1, "Chapter 10 – Be7", 314]],
            ["Chapter Introduction", "Chapter 1", "Chapter 10"],
        )
        self.assertEqual([(8, "Chapter Introduction"), (11, "Chapter 1"), (314, "Chapter 10")], inicios)
        self.assertEqual("Chapter 1", lp.capitulo_da_pagina(200, inicios))
        self.assertEqual("", lp.capitulo_da_pagina(3, inicios))


class CasarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.indice = _indice()

    def _casar(self, paginas: list[dict], leituras: dict[int, str] | None = None) -> list[lp.DiagramaDoLivro]:
        ler = None if leituras is None else (lambda d: leituras.get(d.pagina, ""))
        return lp.casar_livro(enumerate(paginas, start=1), self.indice, sumario=SUMARIO, ler=ler)

    def test_a_legenda_da_a_fen_e_o_lado_a_jogar(self) -> None:
        (d,) = self._casar([_pagina(_imagem(30), _legenda(316, "5.dxc5"))])
        self.assertEqual(lp.SEM_LEITURA, d.estado)
        self.assertEqual(_campo("e4", "e6", "d4", "d5", "Nc3", "c5", "exd5", "exd5", "dxc5"), d.fen.split()[0])
        self.assertEqual("b", d.fen.split()[1])

    def test_o_capitulo_separa_a_mesma_jogada_de_dois_capitulos(self) -> None:
        paginas = [_pagina(), _pagina(), _pagina(_imagem(30), _legenda(316, "3.Nc3"))]
        (d,) = self._casar(paginas)
        self.assertEqual("Chapter 2", self.indice.nos[d.no].capitulo)

    def test_estados_pela_leitura(self) -> None:
        certo = _campo("e4", "e6", "d4", "d5", "Nc3", "c5", "exd5", "exd5", "dxc5")
        uma_casa = certo.replace("rnbqkbnr", "rbbqkbnr")
        paginas = [_pagina(_imagem(30), _legenda(316, "5.dxc5"))] * 3
        self.assertEqual(lp.CONFERE, self._casar(paginas[:1], {1: certo})[0].estado)
        corrigido = self._casar(paginas[:1], {1: uma_casa})[0]
        self.assertEqual((lp.CORRIGIDO, (1,)), (corrigido.estado, corrigido.casas))
        self.assertEqual(lp.DISCORDA, self._casar(paginas[:1], {1: chess.Board().board_fen()})[0].estado)

    def test_a_leitura_escolhe_o_candidato_mais_perto_e_nao_o_primeiro(self) -> None:
        """«3.Nc3» tem dois nós no capítulo 1? Não -- mas «4.Nf3» só na variante; e a mesma jogada em
        duas linhas é o caso do Harikrishna: com o modelo errando uma casa, a ordem pegava o nó de
        outra partida a 15 casas."""
        dois = IndiceDoLivro(
            [
                chess.pgn.read_game(fluxo_tolerante('[Event "C"]\n\n1.e4 e5 2.Nf3 *\n')),
                chess.pgn.read_game(fluxo_tolerante('[Event "C"]\n\n1.d4 d5 2.Nf3 *\n')),
            ]
        )
        segundo = _campo("d4", "d5", "Nf3").replace("rnbqkbnr", "rbbqkbnr")
        (d,) = lp.casar_livro([(1, _pagina(_imagem(30), _legenda(316, "2.Nf3")))], dois, ler=lambda _d: segundo)
        self.assertEqual((lp.CORRIGIDO, 1), (d.estado, dois.nos[d.no].partida))

    def test_a_legenda_sem_imagem_e_faltando_com_a_fen_do_pgn(self) -> None:
        pagina = _pagina(_imagem(30), _legenda(316, "3...c5"), _legenda(452, "4.exd5"))
        diagramas = self._casar([pagina])
        self.assertEqual([lp.SEM_LEITURA, lp.FALTANDO], [d.estado for d in diagramas])
        self.assertEqual(_campo("e4", "e6", "d4", "d5", "Nc3", "c5", "exd5"), diagramas[1].fen.split()[0])

    def test_sem_legenda_a_posicao_lida_acha_o_no(self) -> None:
        lido = _campo("e4", "e6", "d4", "d5", "Nc3", "a6")
        (d,) = self._casar([_pagina(_imagem(30))], {1: lido})
        self.assertEqual((lp.CONFERE, "3...a6"), (d.estado, self.indice.nos[d.no].rotulo))

    def test_sem_no_fica_com_o_reconhecimento(self) -> None:
        (d,) = self._casar([_pagina(_imagem(30), _legenda(316, "40.Qh7"))])
        self.assertEqual(lp.SEM_NO, d.estado)
        self.assertEqual("", d.fen)

    def test_contagem(self) -> None:
        diagramas = self._casar([_pagina(_imagem(30), _legenda(316, "3...c5"), _legenda(452, "4.exd5"))])
        self.assertEqual({lp.SEM_LEITURA: 1, lp.FALTANDO: 1}, lp.contagem(diagramas))

    def test_a_linha_de_legenda_diz_o_lance(self) -> None:
        self.assertEqual("5.dxc5", lp.legenda_da_linha("Position after: 5.dxc5"))
        self.assertEqual("12...Nf6", lp.legenda_da_linha("Posição após 12...Nf6"))
        self.assertEqual("", lp.legenda_da_linha("White is better after 5.dxc5"))


class GaleriaTests(unittest.TestCase):
    """O livro como base de partidas da Galeria (S-594): só a posição exata confirma."""

    def setUp(self) -> None:
        self.indice = _indice()
        pagina = _pagina(_imagem(30), _legenda(316, "3...c5"), _legenda(452, "4.exd5"))
        self.diagramas = lp.casar_livro([(1, pagina)], self.indice, sumario=SUMARIO)

    def _entrada(self, placement: str, pagina: int = 0) -> object:
        from chess_diagram_ocr.gallery_scan import GalleryEntry

        return GalleryEntry(page_index=pagina, diagram_index=0, placement=placement)

    def test_a_posicao_exata_vira_casamento_com_lance_lado_e_cabecalhos(self) -> None:
        certo = _campo("e4", "e6", "d4", "d5", "Nc3", "c5")
        (casamento,), discordam = lp.casamentos_da_galeria([self._entrada(certo)], self.diagramas, self.indice)
        self.assertEqual(0, discordam)
        self.assertEqual(((0, 0), 4, "w"), (casamento.key, casamento.move_number, casamento.side_to_move))
        self.assertEqual({"Event": "Chapter 1", "Site": "Game 1"}, casamento.headers)
        self.assertTrue(casamento.caption_confirmed)
        self.assertIn("3...c5", casamento.game_label)

    def test_a_leitura_errada_nao_confirma_e_e_contada(self) -> None:
        uma_casa = _campo("e4", "e6", "d4", "d5", "Nc3", "c5").replace("rnbqkbnr", "rbbqkbnr")
        self.assertEqual(([], 1), lp.casamentos_da_galeria([self._entrada(uma_casa)], self.diagramas, self.indice))

    def test_pagina_sem_diagrama_do_livro_nao_conta_como_discordancia(self) -> None:
        self.assertEqual(([], 0), lp.casamentos_da_galeria([self._entrada("8/8/8/8/8/8/8/8", 5)], self.diagramas, self.indice))

    def test_o_que_falta_no_pdf_nao_casa_com_a_galeria(self) -> None:
        """A legenda sem imagem não tem o que a Galeria varreu: o diagrama dela não existe no PDF."""
        faltando = _campo("e4", "e6", "d4", "d5", "Nc3", "c5", "exd5")
        self.assertEqual(([], 1), lp.casamentos_da_galeria([self._entrada(faltando)], self.diagramas, self.indice))

    def test_pagina_sem_legenda_casa_pela_posicao_de_uma_partida(self) -> None:
        """A abertura de capítulo e o livro sem legenda (S-597): a posição de uma partida só traz os cabeçalhos dela."""
        so_do_primeiro = _campo("e4", "e6", "d4", "d5", "Nc3", "c5", "exd5", "exd5")
        (casamento,), discordam = lp.casamentos_da_galeria([self._entrada(so_do_primeiro, 5)], self.diagramas, self.indice)
        self.assertEqual(0, discordam)
        self.assertEqual(((5, 0), 5, "w", 1), (casamento.key, casamento.move_number, casamento.side_to_move, casamento.games_matched))
        self.assertEqual({"Event": "Chapter 1", "Site": "Game 1"}, casamento.headers)
        self.assertFalse(casamento.caption_confirmed)

    def test_a_posicao_de_varias_partidas_nao_escolhe_cabecalho(self) -> None:
        das_duas = _campo("e4", "e6", "d4", "d5", "Nc3")
        (casamento,), _ = lp.casamentos_da_galeria([self._entrada(das_duas, 5)], self.diagramas, self.indice)
        self.assertEqual((3, "b", 2, {}), (casamento.move_number, casamento.side_to_move, casamento.games_matched, casamento.headers))
        self.assertIn("2 partidas", casamento.game_label)

    def test_onde_ha_legenda_a_posicao_de_outro_canto_nao_casa(self) -> None:
        """Na página com legenda, a leitura que não é candidato é erro, ainda que exista noutra página do livro."""
        de_outro_canto = _campo("e4", "e6", "d4", "d5", "Nc3", "Nc6", "Nf3")
        self.assertEqual(([], 1), lp.casamentos_da_galeria([self._entrada(de_outro_canto)], self.diagramas, self.indice))


if __name__ == "__main__":
    unittest.main()
