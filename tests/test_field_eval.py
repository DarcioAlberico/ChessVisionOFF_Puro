"""Avaliação sobre páginas reais (S-41).

Nenhum teste aqui depende de `PDF/`: o conjunto real não é versionado, e a lógica que
importa -- casar anotação com leitura, contar falso positivo, recusar rascunho -- é
aritmética sobre estruturas. O único teste que toca o conjunto real pula quando ele não
existe, no mesmo padrão de `data/samples/`.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from chess_diagram_ocr.fen_utils import check_position
from chess_diagram_ocr.field_eval import (
    AnnotatedDiagram,
    FieldPage,
    bbox_iou,
    evaluate_field,
    evaluate_page,
    load_field_set,
    save_field_set,
)
from chess_diagram_ocr.service import RecognitionOptions, RecognizedDiagram

LEGAL = "4k3/8/8/8/8/8/8/4K3"
VAZIO = "8/8/8/8/8/8/8/8"  # fatalmente ilegal: sem reis


def lido(bbox: tuple[float, float, float, float], *, conf: float = 0.95, placement: str = LEGAL) -> RecognizedDiagram:
    """`RecognizedDiagram` de verdade, não um duplo.

    Objeto real pelo mesmo motivo do `oriented_for` em `test_pdf_to_pgn`: se a forma mudar,
    estes testes quebram em vez de continuarem passando sobre um contrato que não existe.
    """
    return RecognizedDiagram(
        index=0,
        board_rgb=np.zeros((8, 8, 3), dtype=np.uint8),
        placement=placement,
        min_confidence=conf,
        bbox_pdf=bbox,
        legality=check_position(f"{placement} w - - 0 1"),
    )


class IouTests(unittest.TestCase):
    def test_caixas_identicas_dao_um(self) -> None:
        self.assertAlmostEqual(bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)

    def test_caixas_disjuntas_dao_zero(self) -> None:
        self.assertEqual(bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)), 0.0)

    def test_caixas_que_so_se_tocam_dao_zero(self) -> None:
        self.assertEqual(bbox_iou((0, 0, 10, 10), (10, 0, 20, 10)), 0.0)

    def test_metade_sobreposta(self) -> None:
        # Interseção 50, união 150.
        self.assertAlmostEqual(bbox_iou((0, 0, 10, 10), (5, 0, 15, 10)), 50 / 150)


class FormatTests(unittest.TestCase):
    def test_ida_e_volta_preserva_tudo(self) -> None:
        pagina = FieldPage(
            pdf="livro.pdf",
            page=40,
            diagrams=(
                AnnotatedDiagram(bbox=(1.0, 2.0, 3.0, 4.0), placement=LEGAL, side_to_move="b", note="x"),
                AnnotatedDiagram(bbox=(5.0, 6.0, 7.0, 8.0)),
            ),
            reviewed=True,
            regime="scan-puro",
            note="conferida",
        )
        self.assertEqual(FieldPage.from_dict(pagina.to_dict()), pagina)

    def test_grava_e_le_ordenado_por_livro_e_pagina(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "field.jsonl"
            save_field_set(
                caminho,
                [FieldPage(pdf="b.pdf", page=1), FieldPage(pdf="a.pdf", page=9), FieldPage(pdf="a.pdf", page=2)],
            )
            lidas = load_field_set(caminho)
            self.assertEqual([(p.pdf, p.page) for p in lidas], [("a.pdf", 2), ("a.pdf", 9), ("b.pdf", 1)])

    def test_pagina_sem_diagrama_sobrevive_a_ida_e_volta(self) -> None:
        """`diagrams: []` é um dado -- é o que mede falso positivo --, não uma lacuna."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "field.jsonl"
            save_field_set(caminho, [FieldPage(pdf="a.pdf", page=1, reviewed=True, regime="sem-diagrama")])
            lida = load_field_set(caminho)[0]
            self.assertEqual(lida.diagrams, ())
            self.assertTrue(lida.reviewed)

    def test_linha_invalida_diz_qual_e(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "field.jsonl"
            caminho.write_text('{"pdf": "a.pdf", "page": 1}\nnao é json\n', encoding="utf-8")
            with self.assertRaises(ValueError) as capturado:
                load_field_set(caminho)
            self.assertIn(":2:", str(capturado.exception))

    def test_conjunto_inexistente_e_lista_vazia_e_nao_erro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_field_set(Path(tmp) / "nao-existe.jsonl"), [])


class PageMetricTests(unittest.TestCase):
    def test_tudo_certo_da_exportacao_cheia(self) -> None:
        pagina = FieldPage(
            pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),)
        )
        r = evaluate_page(pagina, [lido((0, 0, 10, 10))])

        self.assertEqual((r.matched, r.false_positives), (1, 0))
        self.assertAlmostEqual(r.detection_recall, 1.0)
        self.assertAlmostEqual(r.export_rate, 1.0)

    def test_diagrama_nao_detectado_conta_como_perdido(self) -> None:
        pagina = FieldPage(pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),))
        r = evaluate_page(pagina, [])

        self.assertEqual(r.matched, 0)
        self.assertAlmostEqual(r.detection_recall, 0.0)
        self.assertAlmostEqual(r.export_rate, 0.0)
        self.assertIn("não detectado", r.misses[0])

    def test_pagina_sem_diagrama_mede_falso_positivo(self) -> None:
        """É a métrica que não existia: sem estas páginas, inventar diagrama sai de graça."""
        r = evaluate_page(FieldPage(pdf="a.pdf", page=1, reviewed=True), [lido((0, 0, 10, 10))])

        self.assertEqual((r.annotated, r.detected, r.false_positives), (0, 1, 1))
        self.assertEqual(r.pages_without_diagram, 1)

    def test_detectado_mas_ilegal_nao_e_exportado(self) -> None:
        pagina = FieldPage(pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),))
        r = evaluate_page(pagina, [lido((0, 0, 10, 10), placement=VAZIO)])

        self.assertEqual((r.matched, r.legal, r.exported), (1, 0, 0))
        self.assertIn("ilegal", r.misses[0])

    def test_detectado_e_legal_mas_abaixo_do_gate_nao_e_exportado(self) -> None:
        pagina = FieldPage(pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),))
        r = evaluate_page(pagina, [lido((0, 0, 10, 10), conf=0.4)], accept_threshold=0.8)

        self.assertEqual((r.matched, r.legal, r.above_gate, r.exported), (1, 1, 0, 0))
        self.assertIn("confiança 0.400", r.misses[0])

    def test_recorte_deslocado_ainda_casa(self) -> None:
        """O que se mede é achou ou não achou; a qualidade do recorte é a `min_confidence`."""
        pagina = FieldPage(pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 100, 100)),))
        r = evaluate_page(pagina, [lido((5, 5, 105, 105))])
        self.assertEqual(r.matched, 1)

    def test_recorte_muito_fora_nao_casa_e_conta_dos_dois_lados(self) -> None:
        pagina = FieldPage(pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 100, 100)),))
        r = evaluate_page(pagina, [lido((80, 80, 180, 180))])

        self.assertEqual((r.matched, r.false_positives), (0, 1))
        self.assertAlmostEqual(r.detection_recall, 0.0)
        self.assertAlmostEqual(r.detection_precision, 0.0)

    def test_uma_leitura_nao_casa_com_duas_anotacoes(self) -> None:
        """Guloso pelo melhor IoU: a leitura fica com quem ela cobre melhor, e só com essa."""
        pagina = FieldPage(
            pdf="a.pdf",
            page=1,
            reviewed=True,
            diagrams=(AnnotatedDiagram(bbox=(0, 0, 100, 100)), AnnotatedDiagram(bbox=(10, 10, 110, 110))),
        )
        r = evaluate_page(pagina, [lido((0, 0, 100, 100))])

        self.assertEqual(r.matched, 1)
        self.assertEqual(r.false_positives, 0)

    def test_a_posicao_so_conta_quando_a_anotacao_a_traz(self) -> None:
        com = FieldPage(
            pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10), placement=LEGAL),)
        )
        sem = FieldPage(pdf="a.pdf", page=2, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),))

        self.assertEqual(evaluate_page(com, [lido((0, 0, 10, 10))]).comparable, 1)
        self.assertEqual(evaluate_page(sem, [lido((0, 0, 10, 10))]).comparable, 0)

    def test_leitura_sem_bbox_nao_casa_com_nada(self) -> None:
        """Caminho antigo do serviço, antes de a S-41 devolver o bbox: nao pode casar por sorte."""
        sem_bbox = lido((0, 0, 10, 10))
        sem_bbox.bbox_pdf = None
        pagina = FieldPage(pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),))

        r = evaluate_page(pagina, [sem_bbox])
        self.assertEqual((r.matched, r.false_positives), (0, 1))


class _FakeService:
    """Devolve leituras fixas por página, sem abrir PDF nenhum."""

    def __init__(self, por_pagina: dict[int, list[RecognizedDiagram]]) -> None:
        self.por_pagina = por_pagina
        self.paginas_lidas: list[int] = []

    def recognize_page(self, _source: object, page_index: int, *_args: object, **_kwargs: object):
        self.paginas_lidas.append(page_index)
        return self.por_pagina.get(page_index, [])


class FieldRunTests(unittest.TestCase):
    def test_pagina_nao_revisada_e_pulada(self) -> None:
        """Medir contra o proprio rascunho daria recall 1,0 e nao significaria nada."""
        servico = _FakeService({1: [lido((0, 0, 10, 10))], 2: [lido((0, 0, 10, 10))]})
        paginas = [
            FieldPage(pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),)),
            FieldPage(pdf="a.pdf", page=2, reviewed=False, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),)),
        ]

        r = evaluate_field(paginas, options=RecognitionOptions(), service=servico)  # type: ignore[arg-type]

        self.assertEqual(servico.paginas_lidas, [1])
        self.assertEqual(r.pages, 1)
        self.assertEqual(r.annotated, 1)

    def test_pagina_que_falha_ao_ser_lida_vira_zero_detectados(self) -> None:
        """Uma pagina quebrada e um resultado; derrubar o relatorio inteiro nao e."""

        class _Quebrado(_FakeService):
            def recognize_page(self, *_args: object, **_kwargs: object):
                raise RuntimeError("Nenhum tabuleiro foi detectado")

        paginas = [FieldPage(pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),))]
        r = evaluate_field(paginas, options=RecognitionOptions(), service=_Quebrado({}))  # type: ignore[arg-type]

        self.assertEqual((r.pages, r.detected, r.exported), (1, 0, 0))

    def test_o_relatorio_separa_por_regime_e_por_livro(self) -> None:
        servico = _FakeService({1: [lido((0, 0, 10, 10))], 2: []})
        paginas = [
            FieldPage(pdf="a.pdf", page=1, reviewed=True, regime="facil", diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),)),
            FieldPage(pdf="b.pdf", page=2, reviewed=True, regime="dificil", diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),)),
        ]

        r = evaluate_field(paginas, options=RecognitionOptions(), service=servico)  # type: ignore[arg-type]

        self.assertAlmostEqual(r.export_rate, 0.5)
        self.assertAlmostEqual(r.per_regime["facil"].export_rate, 1.0)
        self.assertAlmostEqual(r.per_regime["dificil"].export_rate, 0.0)
        self.assertAlmostEqual(r.per_book["a.pdf"].export_rate, 1.0)
        self.assertAlmostEqual(r.per_book["b.pdf"].export_rate, 0.0)

    def test_o_json_do_relatorio_tem_as_quatro_metricas(self) -> None:
        servico = _FakeService({1: [lido((0, 0, 10, 10))]})
        paginas = [FieldPage(pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),))]

        dados = evaluate_field(paginas, options=RecognitionOptions(), service=servico).as_dict()  # type: ignore[arg-type]

        for chave in ("detection_recall", "detection_precision", "export_rate", "conditional_exact"):
            self.assertIn(chave, dados)
        json.dumps(dados)  # serializa


class RealFieldSetTests(unittest.TestCase):
    """O conjunto versionado é texto e cabe no git; medir contra ele precisa dos PDFs."""

    CAMINHO = Path(__file__).resolve().parents[1] / "data" / "field_set.jsonl"

    def setUp(self) -> None:
        if not self.CAMINHO.exists():
            self.skipTest("data/field_set.jsonl não existe neste clone.")

    def test_o_conjunto_versionado_carrega(self) -> None:
        paginas = load_field_set(self.CAMINHO)
        self.assertGreater(len(paginas), 0)

    def test_toda_pagina_do_conjunto_versionado_esta_revisada(self) -> None:
        """Rascunho commitado por engano viraria verdade de referência sem passar por olho."""
        nao_revisadas = [f"{p.pdf} p{p.page}" for p in load_field_set(self.CAMINHO) if not p.reviewed]
        self.assertEqual(nao_revisadas, [])

    def test_o_conjunto_tem_pagina_sem_diagrama(self) -> None:
        """Sem elas o falso positivo não é medido, e inventar diagrama sai de graça."""
        paginas = load_field_set(self.CAMINHO)
        self.assertTrue(any(not p.diagrams for p in paginas))

    def test_as_caixas_sao_plausiveis(self) -> None:
        """Diagrama de xadrez é quadrado; caixa muito fora disso é anotação errada."""
        for pagina in load_field_set(self.CAMINHO):
            for indice, diagrama in enumerate(pagina.diagrams):
                x0, y0, x1, y1 = diagrama.bbox
                with self.subTest(pdf=pagina.pdf, page=pagina.page, diagram=indice):
                    self.assertGreater(x1, x0)
                    self.assertGreater(y1, y0)
                    self.assertAlmostEqual((x1 - x0) / (y1 - y0), 1.0, delta=0.25)


if __name__ == "__main__":
    unittest.main()
