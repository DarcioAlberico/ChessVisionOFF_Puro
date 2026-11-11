"""Caracterização de `evaluate_page` (S-835): o relatório de fixtures sai igual byte a byte.

Gravado com o `evaluate_page` de antes da partição; a partição não pode mudar uma vírgula. Para
regravar (só quando um número muda **de propósito**): `python tests/test_field_eval_caracterizacao.py --gravar`.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

from chess_diagram_ocr.fen_utils import check_position
from chess_diagram_ocr.field_eval import AnnotatedDiagram, FieldPage, FieldReport, _accumulate, evaluate_page
from chess_diagram_ocr.service import RecognizedDiagram

ESPERADO = Path(__file__).parent / "fixtures" / "field_eval_caracterizacao.json"

LEGAL = "4k3/8/8/8/8/8/8/4K3"
VAZIO = "8/8/8/8/8/8/8/8"
MATE2 = "6k1/5ppp/3q4/4R3/8/8/5PPP/6K1"


def _lido(bbox, *, conf=0.95, placement=LEGAL, **campos) -> RecognizedDiagram:
    lido = RecognizedDiagram(
        index=0,
        board_rgb=np.zeros((8, 8, 3), dtype=np.uint8),
        placement=placement,
        min_confidence=conf,
        bbox_pdf=bbox,
        legality=check_position(f"{placement} w - - 0 1"),
    )
    for nome, valor in campos.items():
        setattr(lido, nome, valor)
    return lido


def _paginas() -> list[tuple[FieldPage, list[RecognizedDiagram], int]]:
    """Uma página por ramo de `evaluate_page`, e algumas que combinam ramos."""
    caixa = (0.0, 0.0, 10.0, 10.0)
    outra = (100.0, 100.0, 110.0, 110.0)

    def pagina(n, *anotados, regime=""):
        return FieldPage(pdf="a.pdf", page=n, reviewed=True, regime=regime,
                         diagrams=tuple(AnnotatedDiagram(bbox=b, placement=p) for b, p in anotados))

    confs = [0.99] * 63 + [0.30]
    return [
        (pagina(1, (caixa, LEGAL)), [_lido(caixa)], 0),
        (pagina(2), [_lido(caixa)], 0),
        (pagina(3, (caixa, LEGAL)), [], 0),
        (pagina(4, (caixa, LEGAL)), [_lido(caixa, placement=VAZIO)], 0),
        (pagina(5, (caixa, LEGAL)), [_lido(caixa, conf=0.4, changed_squares=[3, 9])], 0),
        (pagina(6, (caixa, LEGAL)), [_lido(caixa, conf=0.30, square_confidences=confs, colour_repairs=[63],
                                           changed_squares=[63], colour_reason="trocada")], 0),
        (pagina(7, (caixa, LEGAL), (outra, "")), [_lido(caixa, next_move_replays=True), _lido(outra)], 2),
        (pagina(8, (caixa, LEGAL)), [_lido(caixa, conf=0.2, next_move_replays=False, next_move_repairs=[5],
                                           square_confidences=[0.99] * 5 + [0.2] + [0.99] * 58)], 0),
        (pagina(9, (caixa, LEGAL)), [_lido(caixa, next_move_replays=False,
                                           next_move_reason="o lance impresso '1.e4' replica com 2 trocas "
                                                            "diferentes: nenhuma foi adotada",
                                           next_move_ambiguous=True)], 0),
        (pagina(10, (caixa, MATE2)), [_lido(caixa, placement=MATE2, side_to_move="b", stipulation="#2",
                                            stipulation_closes=True)], 0),
        (pagina(11, (caixa, LEGAL)), [_lido(caixa, placement=MATE2, side_to_move="b", stipulation="#2",
                                            stipulation_closes=True)], 0),
        (pagina(12, (caixa, MATE2)), [_lido(caixa, placement="6k1/5ppp/3Q4/4R3/8/8/5PPP/6K1", side_to_move="b",
                                            stipulation="#2", stipulation_closes=False,
                                            stipulation_reason="Mate em 2 fecha com trocas diferentes: "
                                                               "nenhuma foi adotada",
                                            stipulation_ambiguous=True)], 0),
        (pagina(13, (caixa, MATE2)), [_lido(caixa, placement=MATE2, side_to_move="b", stipulation="#2",
                                            stipulation_closes=False, stipulation_repairs=[19])], 1),
        (pagina(14, (caixa, MATE2), regime="fonte"), [_lido(caixa, placement=MATE2, stipulation="#3",
                                                            stipulation_closes=None)], 0),
        (pagina(15, (caixa, LEGAL)), [_lido(caixa, placement="4k3/8/8/8/8/8/8/4KQ2")], 1),
        (pagina(16, (caixa, LEGAL), (outra, LEGAL)), [_lido((80, 80, 180, 180))], 0),
    ]


def relatorio_das_fixtures() -> str:
    total = FieldReport()
    paginas = []
    for pagina, lidos, amostras in _paginas():
        parcela = evaluate_page(pagina, lidos, accept_threshold=0.8, training_samples=amostras,
                                stipulation_engine=lambda: None)
        paginas.append({
            "relatorio": parcela.as_dict(),
            "misses": parcela.misses,
            "wrong": parcela.wrong,
            "diagrams": parcela.diagrams,
            "contaminated_pages": parcela.contaminated_pages,
        })
        _accumulate(total, parcela)
    return json.dumps({"paginas": paginas, "total": total.as_dict()}, ensure_ascii=False, indent=1,
                      sort_keys=True) + "\n"


class CaracterizacaoDeEvaluatePageTests(unittest.TestCase):
    def test_o_relatorio_das_fixtures_sai_igual_byte_a_byte(self) -> None:
        self.assertEqual(relatorio_das_fixtures(), ESPERADO.read_bytes().decode("utf-8"))


if __name__ == "__main__":
    if "--gravar" in sys.argv:
        ESPERADO.write_bytes(relatorio_das_fixtures().encode("utf-8"))
        print(f"gravado {ESPERADO}")
    else:
        unittest.main()
