"""As anotações por diagrama da galeria e o que elas mudam no PGN (S-67)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import chess

from chess_diagram_ocr.gallery import (
    DiagramAnnotation,
    GalleryAnnotations,
    annotations_path_for,
    lichess_analysis_url,
    load_annotations,
    save_annotations,
)
from chess_diagram_ocr.pdf_to_pgn import DiagramPosition, build_pgn_text
from chess_diagram_ocr.semantics import SideToMove

PLACEMENT = "4k3/8/8/8/8/8/8/4K3"


def _posicao(page: int = 0, diagram: int = 0, side: SideToMove | None = None) -> DiagramPosition:
    return DiagramPosition(
        page_index=page,
        diagram_index=diagram,
        fen=PLACEMENT,
        confidence=0.99,
        min_confidence=0.98,
        is_legal=True,
        is_fatal=False,
        side_to_move=side,
    )


class AnotacaoTests(unittest.TestCase):
    def test_vazia_e_vazia(self) -> None:
        self.assertTrue(DiagramAnnotation().is_empty)
        self.assertFalse(DiagramAnnotation(move_number=3).is_empty)
        self.assertFalse(DiagramAnnotation(lichess_link=False).is_empty)
        self.assertFalse(DiagramAnnotation(headers={"White": "Tal"}).is_empty)

    def test_lichess_false_nao_e_o_mesmo_que_ausente(self) -> None:
        """Tri-estado: `False` é uma decisão, `None` é "siga o padrão da exportação"."""
        self.assertIsNone(DiagramAnnotation().lichess_link)
        self.assertIs(DiagramAnnotation(lichess_link=False).lichess_link, False)
        self.assertIn("lichess_link", DiagramAnnotation(lichess_link=False).to_dict())
        self.assertNotIn("lichess_link", DiagramAnnotation().to_dict())

    def test_lance_zero_ou_negativo_vira_ausencia(self) -> None:
        self.assertIsNone(DiagramAnnotation.from_dict({"move_number": 0}).move_number)
        self.assertIsNone(DiagramAnnotation.from_dict({"move_number": -4}).move_number)
        self.assertIsNone(DiagramAnnotation.from_dict({"move_number": "seis"}).move_number)
        self.assertEqual(DiagramAnnotation.from_dict({"move_number": "24"}).move_number, 24)

    def test_lado_so_aceita_w_ou_b(self) -> None:
        self.assertEqual(DiagramAnnotation.from_dict({"side_to_move": "B"}).side_to_move, "b")
        self.assertEqual(DiagramAnnotation.from_dict({"side_to_move": "white"}).side_to_move, "w")
        self.assertIsNone(DiagramAnnotation.from_dict({"side_to_move": "x"}).side_to_move)

    def test_headers_reservados_sao_recusados(self) -> None:
        """`[FEN]` digitada à mão criaria um PGN cujo header contradiz o próprio diagrama."""
        anotacao = DiagramAnnotation.from_dict({"headers": {"FEN": "lixo", "SetUp": "0", "White": "Tal"}})
        self.assertEqual(anotacao.headers, {"White": "Tal"})

    def test_header_vazio_some(self) -> None:
        self.assertEqual(DiagramAnnotation.from_dict({"headers": {"White": "   "}}).headers, {})


class ConjuntoTests(unittest.TestCase):
    def test_get_devolve_vazia_e_nunca_none(self) -> None:
        self.assertTrue(GalleryAnnotations().get(3, 1).is_empty)

    def test_gravar_vazia_apaga_a_chave(self) -> None:
        """Limpar os campos tem de significar "volte ao padrão", não "declarei nada"."""
        conjunto = GalleryAnnotations()
        conjunto.set(0, 0, DiagramAnnotation(move_number=5))
        self.assertIn((0, 0), conjunto.entries)
        conjunto.set(0, 0, DiagramAnnotation())
        self.assertNotIn((0, 0), conjunto.entries)

    def test_update_preserva_os_outros_campos(self) -> None:
        conjunto = GalleryAnnotations()
        conjunto.update(1, 2, move_number=9)
        conjunto.update(1, 2, lichess_link=False)
        anotacao = conjunto.get(1, 2)
        self.assertEqual(anotacao.move_number, 9)
        self.assertIs(anotacao.lichess_link, False)

    def test_ida_e_volta_pelo_json(self) -> None:
        conjunto = GalleryAnnotations(source_name="livro.pdf")
        conjunto.set(4, 1, DiagramAnnotation(move_number=17, side_to_move="b", headers={"White": "Tal"}))
        voltou = GalleryAnnotations.from_dict(conjunto.to_dict())
        self.assertEqual(voltou.get(4, 1), conjunto.get(4, 1))

    def test_chave_do_json_e_pagina_ponto_diagrama(self) -> None:
        conjunto = GalleryAnnotations()
        conjunto.set(7, 2, DiagramAnnotation(move_number=1))
        self.assertIn("7.2", conjunto.to_dict()["diagrams"])

    def test_chave_estragada_e_ignorada_sem_derrubar_o_resto(self) -> None:
        dados = {"diagrams": {"lixo": {"move_number": 3}, "2.0": {"move_number": 8}}}
        conjunto = GalleryAnnotations.from_dict(dados)
        self.assertEqual(conjunto.get(2, 0).move_number, 8)
        self.assertEqual(len(conjunto.entries), 1)


class ArquivoTests(unittest.TestCase):
    def test_ausente_devolve_conjunto_vazio(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            conjunto = load_annotations(Path("livro.pdf"), directory=Path(pasta))
        self.assertEqual(conjunto.entries, {})
        self.assertEqual(conjunto.source_name, "livro.pdf")

    def test_corrompido_nao_derruba_a_exportacao(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = annotations_path_for(Path("livro.pdf"), directory=Path(pasta))
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text("{ isto nao e json", encoding="utf-8")
            conjunto = load_annotations(Path("livro.pdf"), directory=Path(pasta))
        self.assertEqual(conjunto.entries, {})

    def test_grava_e_le_de_volta(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            conjunto = GalleryAnnotations(source_name="livro.pdf")
            conjunto.set(0, 1, DiagramAnnotation(move_number=12, lichess_link=False))
            caminho = save_annotations(Path("/qualquer/livro.pdf"), conjunto, directory=Path(pasta))
            self.assertTrue(caminho.exists())
            gravado = json.loads(caminho.read_text(encoding="utf-8"))
            self.assertEqual(gravado["version"], 1)
            voltou = load_annotations(Path("/qualquer/livro.pdf"), directory=Path(pasta))
        self.assertEqual(voltou.get(0, 1).move_number, 12)
        self.assertIs(voltou.get(0, 1).lichess_link, False)

    def test_nome_do_arquivo_segue_o_stem_como_o_pgn(self) -> None:
        caminho = annotations_path_for(Path("/livros/1937 Kemeri.pdf"), directory=Path("/g"))
        self.assertEqual(caminho.name, "1937 Kemeri.json")


class LichessTests(unittest.TestCase):
    def test_url_troca_espaco_por_underscore(self) -> None:
        url = lichess_analysis_url("8/8/8/8/8/8/8/K6k w - - 0 1")
        self.assertEqual(url, "https://lichess.org/analysis/8/8/8/8/8/8/8/K6k_w_-_-_0_1")

    def test_nao_acessa_a_rede(self) -> None:
        """Montar é offline; abrir é que manda a posição para fora (ver o docstring)."""
        import urllib.request
        from unittest import mock

        with mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("saiu para a rede")):
            lichess_analysis_url(f"{PLACEMENT} w - - 0 1")


class ExportacaoTests(unittest.TestCase):
    """O que a anotação muda no PGN. É aqui que a galeria justifica existir."""

    def _pgn(self, **kwargs) -> str:
        return build_pgn_text([_posicao()], source_name="livro.pdf", **kwargs)

    def test_sem_anotacao_o_pgn_nao_muda(self) -> None:
        self.assertIn(f'[FEN "{PLACEMENT} w - - 0 1"]', self._pgn())

    def test_lance_entra_na_fen(self) -> None:
        pgn = self._pgn(annotations={(0, 0): DiagramAnnotation(move_number=24)})
        self.assertIn(f'[FEN "{PLACEMENT} w - - 0 24"]', pgn)

    def test_vez_declarada_vence_a_deduzida(self) -> None:
        """É a razão de a galeria existir: corrigir o palpite da S-17, não reforçá-lo."""
        posicao = _posicao(side=SideToMove(color=chess.WHITE, source="legality"))
        pgn = build_pgn_text(
            [posicao],
            source_name="livro.pdf",
            annotations={(0, 0): DiagramAnnotation(side_to_move="b")},
        )
        self.assertIn(f'[FEN "{PLACEMENT} b - - 0 1"]', pgn)
        self.assertIn('[SideToMove "pretas"]', pgn)
        self.assertIn('[SideToMoveSource "manual"]', pgn)

    def test_header_da_pessoa_vence_o_inferido(self) -> None:
        pgn = self._pgn(annotations={(0, 0): DiagramAnnotation(headers={"White": "Tal", "Site": "Riga"})})
        self.assertIn('[White "Tal"]', pgn)
        self.assertIn('[Site "Riga"]', pgn)
        self.assertNotIn('[Site "Local"]', pgn)

    def test_link_por_diagrama_vence_o_padrao_da_exportacao(self) -> None:
        """O pedido original: uns diagramas precisam do link e outros não."""
        sem = self._pgn(annotations={(0, 0): DiagramAnnotation(lichess_link=False)}, lichess_links=True)
        self.assertNotIn("lichess.org", sem)

        com = self._pgn(annotations={(0, 0): DiagramAnnotation(lichess_link=True)}, lichess_links=False)
        self.assertIn("https://lichess.org/analysis/", com)

    def test_sem_declaracao_o_diagrama_segue_o_padrao(self) -> None:
        self.assertNotIn("lichess.org", self._pgn(lichess_links=False))
        self.assertIn("lichess.org", self._pgn(lichess_links=True))

    def test_o_link_carrega_a_fen_ja_anotada(self) -> None:
        """Link com a FEN antiga mandaria para o lichess uma posição que o PGN não tem."""
        pgn = self._pgn(annotations={(0, 0): DiagramAnnotation(move_number=24, lichess_link=True)})
        self.assertIn(lichess_analysis_url(f"{PLACEMENT} w - - 0 24"), pgn)

    def test_anotacao_de_outro_diagrama_nao_vaza(self) -> None:
        pgn = build_pgn_text(
            [_posicao(diagram=0), _posicao(diagram=1)],
            source_name="livro.pdf",
            annotations={(0, 1): DiagramAnnotation(move_number=30)},
        )
        self.assertIn("0 30", pgn)
        self.assertIn("0 1", pgn)


if __name__ == "__main__":
    unittest.main()
