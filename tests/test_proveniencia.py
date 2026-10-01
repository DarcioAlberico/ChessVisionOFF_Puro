"""O sidecar de proveniência do PGN (A11 do ciclo 2 OCR/UI).

O que se trava: o PGN aponta para o sidecar e a chave é a do `[Diagram]`; o sidecar carrega o
que o header não cabe (retângulo, hash do recorte, confiança por casa, reparos, decisão
humana, modelo, perfil); um item exportado e relido volta inteiro; e a sabotagem -- chave por
FEN -- faz dois diagramas iguais em páginas diferentes colidir, e a colisão é acusada.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import chess

from chess_diagram_ocr.gallery import DiagramAnnotation
from chess_diagram_ocr.pdf_to_pgn import DiagramPosition, write_gated_pgn
from chess_diagram_ocr.proveniencia import (
    Cabecalho,
    ColisaoDeProveniencia,
    chave,
    read_sidecar,
    sidecar_path,
    write_sidecar,
)
from chess_diagram_ocr.semantics import SideToMove

FEN = "6k1/5ppp/3q4/4R3/8/8/5PPP/6K1"


def _position(page: int, index: int, *, fen: str = FEN, min_confidence: float = 0.97) -> DiagramPosition:
    return DiagramPosition(
        page_index=page, diagram_index=index, fen=fen, confidence=0.99, min_confidence=min_confidence,
        is_legal=True, is_fatal=False, rotation=0,
        side_to_move=SideToMove(color=chess.BLACK, source="move-number", reason="23..."),
        detection_source="contour", bbox_pdf=(10.0 + page, 20.0, 110.0 + page, 120.0),
        image_hash="ab" * 32, square_confidences=tuple([0.99] * 63 + [min_confidence]),
        repairs=(("d6", "Q", "q"),), colour_repairs=("d6",), next_move="23...♛xe5",
        next_move_repairs=(), gate_confidence=None if min_confidence < 0.8 else 0.99,
    )


class SidecarTests(unittest.TestCase):
    def test_the_pgn_points_at_the_sidecar_and_the_sidecar_carries_what_the_header_cannot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            saida = Path(tmpdir) / "livro.pgn"
            positions = [_position(3, 1), _position(3, 2, min_confidence=0.40), _position(7, 1)]
            annotations = {(3, 1): DiagramAnnotation(move_number=23, side_to_move="b",
                                                     headers={"White": "Alguém"})}
            report = write_gated_pgn(
                positions, saida, source_name="livro.pdf", annotations=annotations,
                provenance=Cabecalho(source_name="livro.pdf", source_hash="ff" * 32,
                                     model_identity="123-456", profile={"closures": 2}, dpi=220),
            )
            self.assertEqual(report.provenance_path, sidecar_path(saida))
            self.assertTrue(report.provenance_path.exists())

            pgn = saida.read_text(encoding="utf-8")
            self.assertIn('[ProvenanceFile "livro.proveniencia.jsonl"]', pgn)
            self.assertIn('[ProvenanceKey "p3:d1"]', pgn)
            self.assertIn('[ProvenanceKey "p7:d1"]', pgn)
            review = report.review_path.read_text(encoding="utf-8")
            self.assertIn('[ProvenanceKey "p3:d2"]', review)
            self.assertIn('[ProvenanceFile "livro.proveniencia.jsonl"]', review)

            header, records = read_sidecar(report.provenance_path)
            self.assertEqual(header["source_hash"], "ff" * 32)
            self.assertEqual(header["model_identity"], "123-456")
            self.assertEqual(header["profile"], {"closures": 2})
            self.assertEqual(header["accept_threshold"], 0.8)
            self.assertEqual(set(records), {"p3:d1", "p3:d2", "p7:d1"})
            linha = records["p3:d1"]
            self.assertEqual(linha["rect"], [13.0, 20.0, 113.0, 120.0])
            self.assertEqual(linha["image_hash"], "ab" * 32)
            self.assertEqual(len(linha["square_confidences"]), 64)
            self.assertEqual(linha["repairs"], [["d6", "Q", "q"]])
            self.assertEqual(linha["colour_repairs"], ["d6"])
            self.assertEqual(linha["next_move"], "23...♛xe5")
            self.assertEqual(linha["verdict"], "accepted")
            self.assertEqual(linha["human"]["headers"], {"White": "Alguém"})
            self.assertEqual(linha["side"], {"color": "b", "source": "move-number", "reason": "23...",
                                             "conflicting": False})
            self.assertEqual(records["p3:d2"]["verdict"], "needs_review")
            self.assertIn("0.400", records["p3:d2"]["reason"])
            self.assertIsNone(records["p7:d1"]["human"])

    def test_without_a_header_no_sidecar_and_no_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            saida = Path(tmpdir) / "livro.pgn"
            report = write_gated_pgn([_position(3, 1)], saida, source_name="livro.pdf")
            self.assertIsNone(report.provenance_path)
            self.assertFalse(sidecar_path(saida).exists())
            self.assertNotIn("Provenance", saida.read_text(encoding="utf-8"))

    def test_a_synthetic_item_survives_export_and_reimport(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            saida = Path(tmpdir) / "livro.pgn"
            position = _position(12, 2)
            write_sidecar([(position, "accepted", "")], saida,
                          cabecalho=Cabecalho(source_name="livro.pdf"))
            _, records = read_sidecar(sidecar_path(saida))
            back = records[chave(12, 2)]
            self.assertEqual(back["placement"], FEN)
            self.assertEqual(back["fen"], position.full_fen)
            self.assertEqual(back["page_index"], 12)
            self.assertEqual(back["diagram_index"], 2)
            self.assertEqual(tuple(back["rect"]), position.bbox_pdf)
            self.assertEqual(back["square_confidences"], [round(c, 4) for c in position.square_confidences])
            self.assertEqual([tuple(r) for r in back["repairs"]], list(position.repairs))

    def test_the_same_fen_on_two_pages_is_two_records_and_a_fen_key_collides(self) -> None:
        """A sabotagem do passo: a chave por FEN funde dois diagramas -- e é acusada."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saida = Path(tmpdir) / "livro.pgn"
            positions = [(_position(3, 1), "accepted", ""), (_position(9, 1), "accepted", "")]
            write_sidecar(positions, saida, cabecalho=Cabecalho(source_name="livro.pdf"))
            _, records = read_sidecar(sidecar_path(saida))
            self.assertEqual(len(records), 2, "a mesma posição em duas páginas são dois diagramas")
            with self.assertRaises(ColisaoDeProveniencia) as caught:
                write_sidecar(positions, saida, cabecalho=Cabecalho(source_name="livro.pdf"),
                              key_of=lambda position: position.fen)
            self.assertIn("página 3", str(caught.exception))
            self.assertIn("página 9", str(caught.exception))

    def test_reading_a_sidecar_with_a_repeated_key_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            arquivo = Path(tmpdir) / "x.proveniencia.jsonl"
            linhas = [json.dumps({"kind": "header", "version": 1}),
                      json.dumps({"kind": "diagram", "key": "p1:d1", "page_index": 1, "diagram_index": 1}),
                      json.dumps({"kind": "diagram", "key": "p1:d1", "page_index": 2, "diagram_index": 1})]
            arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
            with self.assertRaises(ColisaoDeProveniencia):
                read_sidecar(arquivo)


if __name__ == "__main__":
    unittest.main()
