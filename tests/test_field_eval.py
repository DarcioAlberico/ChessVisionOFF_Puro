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
    FieldReport,
    _accumulate,
    bbox_iou,
    evaluate_field,
    evaluate_page,
    field_set_identity,
    load_field_set,
    save_field_set,
)
from chess_diagram_ocr.labels import DatasetEntry, pages_with_training_samples
from chess_diagram_ocr.service import RecognitionOptions, RecognizedDiagram

LEGAL = "4k3/8/8/8/8/8/8/4K3"
VAZIO = "8/8/8/8/8/8/8/8"  # fatalmente ilegal: sem reis


def lido(
    bbox: tuple[float, float, float, float],
    *,
    conf: float = 0.95,
    placement: str = LEGAL,
    reparadas: tuple[int, ...] = (),
) -> RecognizedDiagram:
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
        changed_squares=list(reparadas),
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


class ExatidaoDeCampoTests(unittest.TestCase):
    """S-96: a taxa de exportação mede confiança; a exatidão de campo mede correção.

    Uma leitura **confiantemente errada** passa o gate e entra na taxa de exportação como
    acerto. Foi essa cegueira que a 7.7 encontrou como "uma catraca que só desce" e atribuiu à
    distribuição bimodal da confiança -- a explicação está um nível abaixo, e é que uma métrica
    de confiança não pode medir correção.
    """

    OUTRA = "4k3/8/8/8/8/8/8/3QK3"

    def _pagina(self, *placements: str) -> FieldPage:
        return FieldPage(
            pdf="a.pdf",
            page=1,
            reviewed=True,
            diagrams=tuple(
                AnnotatedDiagram(bbox=(i * 200.0, 0.0, i * 200.0 + 100.0, 100.0), placement=p)
                for i, p in enumerate(placements)
            ),
        )

    def _leituras(self, *pares: tuple[str, float]) -> list:
        return [
            lido((i * 200.0, 0.0, i * 200.0 + 100.0, 100.0), placement=p, conf=c)
            for i, (p, c) in enumerate(pares)
        ]

    def test_exportado_e_errado_e_categoria_propria(self) -> None:
        """O dano é de outra natureza: entra no PGN e no dataset **como verdade**."""
        r = evaluate_page(self._pagina(LEGAL), self._leituras((self.OUTRA, 0.99)), accept_threshold=0.8)

        self.assertEqual(r.exported, 1, "passou o gate")
        self.assertEqual((r.comparable, r.exact), (1, 0))
        self.assertEqual((r.exported_comparable, r.exported_exact, r.exported_wrong), (1, 0, 1))
        self.assertAlmostEqual(r.field_exact, 0.0)
        self.assertEqual(len(r.wrong), 1)
        self.assertIn("exportado e errado", r.wrong[0])
        self.assertIn(self.OUTRA, r.wrong[0], "o relatório mostra o que foi lido")
        self.assertIn(LEGAL, r.wrong[0], "e a referência ao lado")

    def test_a_taxa_de_exportacao_nao_distingue_o_errado(self) -> None:
        """O ponto do item: as duas páginas exportam 1,000, e uma delas está errada."""
        certa = evaluate_page(self._pagina(LEGAL), self._leituras((LEGAL, 0.99)), accept_threshold=0.8)
        errada = evaluate_page(self._pagina(LEGAL), self._leituras((self.OUTRA, 0.99)), accept_threshold=0.8)

        self.assertAlmostEqual(certa.export_rate, errada.export_rate, msg="a métrica antiga é cega")
        self.assertAlmostEqual(certa.field_exact, 1.0)
        self.assertAlmostEqual(errada.field_exact, 0.0)

    def test_o_barrado_nao_entra_na_exatidao_de_campo(self) -> None:
        """Errar e ser barrado é o sistema funcionando: vai para o `.review.pgn`."""
        r = evaluate_page(self._pagina(LEGAL), self._leituras((self.OUTRA, 0.40)), accept_threshold=0.8)

        self.assertEqual(r.exported, 0)
        self.assertEqual((r.comparable, r.exact), (1, 0), "conta na exatidão condicional")
        self.assertEqual(r.exported_comparable, 0, "e não na de campo")
        self.assertEqual(r.wrong, [])

    def test_exportado_sem_referencia_nao_conta_nem_como_acerto_nem_como_erro(self) -> None:
        """Não medido é uma terceira coisa, e hoje é a mais comum."""
        r = evaluate_page(self._pagina(""), self._leituras((LEGAL, 0.99)), accept_threshold=0.8)

        self.assertEqual(r.exported, 1)
        self.assertEqual((r.comparable, r.exported_comparable), (0, 0))
        self.assertAlmostEqual(r.field_exact, 0.0, msg="sem denominador, a taxa é 0 e não 1")
        self.assertFalse(r.has_enough_comparable)

    def test_a_exatidao_de_campo_separa_do_condicional(self) -> None:
        """Um exportado errado e um barrado errado: as duas taxas respondem coisas diferentes."""
        r = evaluate_page(
            self._pagina(LEGAL, LEGAL),
            self._leituras((self.OUTRA, 0.99), (self.OUTRA, 0.40)),
            accept_threshold=0.8,
        )

        self.assertEqual((r.comparable, r.exact), (2, 0))
        self.assertAlmostEqual(r.conditional_exact, 0.0)
        self.assertEqual(r.exported_comparable, 1, "só o que passou o gate")
        self.assertAlmostEqual(r.field_exact, 0.0)
        self.assertEqual(r.exported_wrong, 1)

    def test_sem_conferivel_bastante_o_numero_e_recusado(self) -> None:
        """Um 1,000 sobre n=1 tem a mesma aparência de um 1,000 sobre n=300."""
        r = evaluate_page(self._pagina(LEGAL, "", "", ""), self._leituras(*[(LEGAL, 0.99)] * 4), accept_threshold=0.8)

        self.assertEqual((r.comparable, r.annotated), (1, 4))
        self.assertAlmostEqual(r.comparable_share, 0.25)
        self.assertFalse(r.has_enough_comparable)
        self.assertIn("exatidão não medida", r.summary())
        self.assertIn("1 de 4", r.summary())

    def test_com_conferivel_bastante_o_numero_sai(self) -> None:
        r = evaluate_page(self._pagina(LEGAL, LEGAL), self._leituras(*[(LEGAL, 0.99)] * 2), accept_threshold=0.8)

        self.assertTrue(r.has_enough_comparable)
        self.assertAlmostEqual(r.field_exact, 1.0)
        self.assertIn("exatidão de campo 1.000", r.summary())
        self.assertIn("n=2", r.summary(), "o `n` sai junto, sempre")

    def test_o_json_sai_cru_mesmo_quando_o_texto_recusa(self) -> None:
        """Quem refaz a conta precisa dos números; quem lê o relatório precisa da ressalva."""
        r = evaluate_page(self._pagina(LEGAL, "", "", ""), self._leituras(*[(LEGAL, 0.99)] * 4), accept_threshold=0.8)
        dados = r.as_dict()

        self.assertEqual(dados["comparable"], 1)
        self.assertEqual(dados["exact"], 1)
        self.assertEqual(dados["annotated"], 4)
        self.assertAlmostEqual(dados["comparable_share"], 0.25)
        self.assertFalse(dados["enough_comparable"])

    def test_os_novos_contadores_somam_entre_paginas(self) -> None:
        """`_accumulate` esquecer um campo é o defeito clássico deste dataclass."""
        uma = evaluate_page(self._pagina(LEGAL), self._leituras((self.OUTRA, 0.99)), accept_threshold=0.8)
        outra = evaluate_page(self._pagina(LEGAL), self._leituras((LEGAL, 0.99)), accept_threshold=0.8)

        total = FieldReport()
        for parcela in (uma, outra):
            _accumulate(total, parcela)

        self.assertEqual((total.exported_comparable, total.exported_exact, total.exported_wrong), (2, 1, 1))
        self.assertAlmostEqual(total.field_exact, 0.5)
        self.assertEqual(len(total.wrong), 1)


class ContaminacaoPorTreinoTests(unittest.TestCase):
    """S-97: o conjunto de campo herdou uma versão menor do problema que veio corrigir.

    A Fase 7 nasceu de *"não é o modelo que está ruim, é o conjunto de teste que não
    representa a entrada"*. Mas nada impedia que uma página do conjunto de campo fosse também
    uma página de que há amostra em `train` -- e medido em 2026-08-16 são 7 de 39 diagramas
    (17,9%), todos exportando.

    Isto **não** diz que o checkpoint em uso viu a página: diz que o próximo treinado sobre
    estes splits verá. É armadilha que fecha no próximo retreino.
    """

    def _pagina(self, quantos: int = 2) -> FieldPage:
        return FieldPage(
            pdf="a.pdf",
            page=80,
            reviewed=True,
            diagrams=tuple(
                AnnotatedDiagram(bbox=(i * 200.0, 0.0, i * 200.0 + 100.0, 100.0)) for i in range(quantos)
            ),
        )

    def _leituras(self, quantos: int = 2, *, conf: float = 0.99) -> list:
        return [
            lido((i * 200.0, 0.0, i * 200.0 + 100.0, 100.0), conf=conf) for i in range(quantos)
        ]

    def test_pagina_com_amostra_de_treino_e_marcada(self) -> None:
        r = evaluate_page(self._pagina(), self._leituras(), training_samples=3)

        self.assertEqual(r.contaminated, 2, "os dois diagramas da página contam")
        self.assertEqual(len(r.contaminated_pages), 1)
        self.assertIn("3 amostra(s) de treino", r.contaminated_pages[0])

    def test_pagina_sem_amostra_nao_e_marcada(self) -> None:
        r = evaluate_page(self._pagina(), self._leituras(), training_samples=0)

        self.assertEqual(r.contaminated, 0)
        self.assertEqual(r.contaminated_pages, [])
        self.assertAlmostEqual(r.clean_export_rate, r.export_rate, msg="sem contaminação, as duas coincidem")

    def test_a_taxa_limpa_tira_a_pagina_contaminada_das_duas_pontas(self) -> None:
        """Do numerador e do denominador: o que sai dali não conta como sucesso nem como falha."""
        suja = evaluate_page(self._pagina(2), self._leituras(2), training_samples=1)
        limpa = evaluate_page(
            FieldPage(pdf="b.pdf", page=9, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 100, 100)),)),
            [lido((0, 0, 100, 100), conf=0.2)],
            accept_threshold=0.8,
        )

        total = FieldReport()
        for parcela in (suja, limpa):
            _accumulate(total, parcela)

        self.assertEqual((total.annotated, total.exported), (3, 2))
        self.assertAlmostEqual(total.export_rate, 2 / 3)
        self.assertEqual((total.contaminated, total.contaminated_exported), (2, 2))
        self.assertEqual(total.clean_annotated, 1)
        self.assertAlmostEqual(total.clean_export_rate, 0.0, msg="o único diagrama limpo foi barrado")

    def test_pagina_sem_diagrama_nao_e_contaminada(self) -> None:
        """Ela mede falso positivo, e não há diagrama anotado para o modelo ter aprendido."""
        r = evaluate_page(FieldPage(pdf="a.pdf", page=1, reviewed=True), [lido((0, 0, 10, 10))], training_samples=5)

        self.assertEqual(r.contaminated, 0)
        self.assertEqual(r.contaminated_pages, [])

    def test_o_resumo_declara_a_contaminacao(self) -> None:
        r = evaluate_page(self._pagina(), self._leituras(), training_samples=1)
        self.assertIn("contaminados", r.summary())
        self.assertIn("limpa", r.summary())

    def test_o_json_traz_as_duas_taxas(self) -> None:
        dados = evaluate_page(self._pagina(), self._leituras(), training_samples=1).as_dict()

        self.assertEqual(dados["contaminated"], 2)
        self.assertEqual(dados["clean_annotated"], 0)
        self.assertIn("clean_export_rate", dados)


class PaginasComTreinoTests(unittest.TestCase):
    """`labels.pages_with_training_samples`: quem responde de onde vem a marca (S-97)."""

    def _entrada(self, nome: str, **campos: str) -> DatasetEntry:
        base = {"filename": nome, "fen": f"{LEGAL} w - - 0 1", "source_pdf": "a.pdf", "source_page": "81"}
        base.update(campos)
        return DatasetEntry(**base)  # type: ignore[arg-type]

    def test_converte_a_pagina_para_base_0(self) -> None:
        """O CSV grava a página que o usuário vê (base 1); o conjunto de campo conta de 0."""
        achado = pages_with_training_samples([self._entrada("x.png")], {"x.png": "train"})
        self.assertEqual(achado, {("a.pdf", 80): 1})

    def test_conta_quantas_amostras_por_pagina(self) -> None:
        entradas = [self._entrada("x.png"), self._entrada("y.png"), self._entrada("z.png", source_page="99")]
        splits = {"x.png": "train", "y.png": "train", "z.png": "train"}

        self.assertEqual(pages_with_training_samples(entradas, splits), {("a.pdf", 80): 2, ("a.pdf", 98): 1})

    def test_so_conta_train(self) -> None:
        """Amostra em `val`/`test` na mesma página é outro assunto: o modelo não aprende dela."""
        entradas = [self._entrada("x.png"), self._entrada("y.png")]

        self.assertEqual(pages_with_training_samples(entradas, {"x.png": "val", "y.png": "test"}), {})

    def test_amostra_sem_procedencia_e_ignorada(self) -> None:
        """84,1% do acervo. O alcance do alerta é o das amostras que declaram de onde vieram."""
        entradas = [self._entrada("x.png", source_pdf=""), self._entrada("y.png", source_page="")]

        self.assertEqual(pages_with_training_samples(entradas, {"x.png": "train", "y.png": "train"}), {})

    def test_o_20_ponto_0_herdado_do_pandas_ainda_e_lido(self) -> None:
        achado = pages_with_training_samples([self._entrada("x.png", source_page="20.0")], {"x.png": "train"})
        self.assertEqual(achado, {("a.pdf", 19): 1})


class ReparoSeparadoDoGateTests(unittest.TestCase):
    """"Casas reparadas" separado em exportadas e barradas (S-132).

    Enquanto era um número só ao lado da taxa de exportação, ele sugeria que o reparo estava
    ajudando a exportar. A parcela "ajudou" é **zero por aritmética**: uma casa reparada carrega
    a confiança da segunda opção, que não passa de 0,5, contra um gate de 0,80. Ver
    `decode.decode_constrained` e `tests/test_decode.py::ReparoNaoPassaNoGateTests`.

    Aqui a confiança é montada à mão, então o teste consegue exercitar o ramo "reparado e
    exportado" que o pipeline real não produz -- e é isso que faz dele um teste da **separação**
    e não uma repetição da prova algébrica.
    """

    def _pagina(self) -> FieldPage:
        return FieldPage(pdf="a.pdf", page=1, reviewed=True, diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)),))

    def test_sem_reparo_os_tres_numeros_sao_zero(self) -> None:
        r = evaluate_page(self._pagina(), [lido((0, 0, 10, 10))])

        self.assertEqual((r.repaired_squares, r.repaired_diagrams), (0, 0))
        self.assertEqual((r.repaired_exported, r.repaired_blocked), (0, 0))

    def test_o_reparado_que_o_gate_barra_conta_como_barrado(self) -> None:
        """O caso real: confiança abaixo do gate porque houve reparo."""
        r = evaluate_page(self._pagina(), [lido((0, 0, 10, 10), conf=0.45, reparadas=(12, 13))])

        self.assertEqual(r.repaired_squares, 2)
        self.assertEqual(r.repaired_diagrams, 1)
        self.assertEqual((r.repaired_exported, r.repaired_blocked), (0, 1))
        self.assertEqual(r.exported, 0)

    def test_a_separacao_e_pelo_gate_e_nao_por_suposicao(self) -> None:
        """Se um dia o gate mudar, o número acompanha em vez de continuar dizendo zero."""
        r = evaluate_page(self._pagina(), [lido((0, 0, 10, 10), conf=0.95, reparadas=(12,))])

        self.assertEqual((r.repaired_exported, r.repaired_blocked), (1, 0))
        self.assertEqual(r.exported, 1)

    def test_as_parcelas_somam_o_total_casado(self) -> None:
        pagina = FieldPage(
            pdf="a.pdf",
            page=1,
            reviewed=True,
            diagrams=(AnnotatedDiagram(bbox=(0, 0, 10, 10)), AnnotatedDiagram(bbox=(20, 20, 30, 30))),
        )
        r = evaluate_page(
            pagina,
            [lido((0, 0, 10, 10), conf=0.45, reparadas=(1,)), lido((20, 20, 30, 30), conf=0.95, reparadas=(2,))],
        )

        self.assertEqual(r.repaired_exported + r.repaired_blocked, 2)
        self.assertEqual(r.repaired_diagrams, 2)

    def test_o_falso_positivo_conta_no_total_e_nao_na_separacao(self) -> None:
        """`repaired_squares` mede o trabalho do decodificador, inclusive no que não é diagrama.

        `repaired_exported`/`blocked` medem o destino de um diagrama **anotado**, então o falso
        positivo fica de fora dos dois -- ele não tinha para onde ir.
        """
        r = evaluate_page(FieldPage(pdf="a.pdf", page=1, reviewed=True), [lido((0, 0, 10, 10), reparadas=(5,))])

        self.assertEqual(r.repaired_squares, 1)
        self.assertEqual(r.repaired_diagrams, 1)
        self.assertEqual((r.repaired_exported, r.repaired_blocked), (0, 0))
        self.assertEqual(r.false_positives, 1)


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


RAIZ = Path(__file__).resolve().parents[1]

RELATORIOS_CORRENTES = {
    "field_20260822_s99.json": "a régua da S-99 fechada: a produção sobre as 66 páginas",
    "controle_20260822.json": "o controle da S-107, regravado sobre o conjunto de hoje",
    "mhsp_20260822.json": "o candidato da S-107, regravado no mesmo conjunto",
    "s108_20260822.json": "o tratamento da S-108, medido pela primeira vez com régua que separa",
}
"""Os relatórios de campo que os documentos citam **como correntes** (S-100).

O conjunto passou de 15 páginas/38 diagramas para 17/39 em 2026-08-15, e todas as medições
anteriores são do conjunto antigo. As tabelas que reprovaram S-38b, S-40, S-62a e S-62b
comparam variantes sobre 38 diagramas -- uma variante medida hoje entra nelas sem ser
comparável, e a diferença de 0,019 na taxa de exportação é da ordem das que decidiram
aqueles vereditos.

**Um relatório entra nesta lista quando um documento o apresenta como o número de agora.** Os
de `docs/metrics/field_20260809*.json` e `field_20260811*.json` ficam de fora de propósito:
eles são o registro histórico da Fase 7, e o cabeçalho do `EXPERIMENTS_FASE7.md` declara o
conjunto deles.

Quando a S-99 crescer o conjunto para 60 páginas, esta suíte falha em bloco -- e é o ponto:
cada linha aqui tem de ser remedida ou sair da lista, e a decisão passa a ser explícita.

**Foi o que aconteceu em 2026-08-22.** O conjunto passou de 17/40 para 65/112 e as quatro
linhas de 2026-08-16 caíram juntas. Os quatro modelos foram remedidos sobre o conjunto novo --
`producao_20260816.json` sai da lista porque `field_20260822_s99.json` é a produção sobre o
conjunto de hoje, e `s108_20260822.json` entra porque a decisão da Fase 15 passou a depender
dele. Os de 2026-08-16 viram registro histórico: eles declaram `"pages": 19` e é assim que se
confere.

**E aconteceu de novo em 2026-08-23, dentro do mesmo commit que fechou a S-99.** Os quatro
relatórios de 22/08 declaravam `63/110`; o `field_set.jsonl` daquele commit tem `65/112`, porque
duas páginas do Yusupov foram anotadas depois de a medição rodar. Ninguém percebeu na hora --
a mensagem do commit repete `63/110` cinco vezes -- e foi esta guarda que pegou, que é para o
que ela existe. O conjunto foi para `66/115` com a `p14` do Yusupov, que estava por anotar, e
os quatro foram remedidos sobre ele com o mesmo código.

O que se moveu foi denominador e **detecção**: o recall caiu de 0,9364 para 0,9217 e a precisão
de 0,9904 para 0,9725, e as duas quedas são o mesmo caso -- a `p14`, em que o caminho de imagem
embutida devolve fragmento de scan em vez de diagrama, acha um dos três diagramas e inventa uma
caixa. As FENs dos três foram transcritas depois, e aí `comparable` foi de 93 para 94 e `exact`
subiu 1 nas quatro colunas: dos três, só o 1-11 é casado, e os quatro modelos o leem certo.
Está na S-99 da `SPEC_FASE14.md`.

**Repare no que esta guarda não pega.** Ela compara identidade -- `pages` e `annotated` -- e
transcrever uma FEN não mexe em nenhum dos dois. Os relatórios ficaram materialmente velhos
(`comparable` e `exact` mudaram) com a suíte verde. Quem acrescentar FEN, ou mexer no código
de detecção, tem de remedir por conta própria."""


class ConjuntoVigenteTests(unittest.TestCase):
    """Um relatório antigo citado como corrente faz a suíte falhar (S-100)."""

    def _hoje(self) -> dict[str, int]:
        conjunto = RAIZ / "data" / "field_set.jsonl"
        if not conjunto.exists():
            raise unittest.SkipTest("sem data/field_set.jsonl: o conjunto real não é versionado em todo clone")
        return field_set_identity(load_field_set(conjunto))

    def test_a_identidade_conta_so_o_que_foi_revisado(self) -> None:
        """Rascunho não é verdade de referência, e `evaluate_field` o pula -- então ele também
        não entra na identidade, senão dois conjuntos com o mesmo número de revisadas
        pareceriam diferentes por causa de rascunhos que ninguém mediu."""
        paginas = [
            FieldPage(pdf="a.pdf", page=1, diagrams=(AnnotatedDiagram(bbox=(0, 0, 1, 1)),), reviewed=True),
            FieldPage(pdf="b.pdf", page=2, diagrams=(AnnotatedDiagram(bbox=(0, 0, 1, 1)),), reviewed=False),
        ]
        self.assertEqual(field_set_identity(paginas), {"pages": 1, "annotated": 1})

    def test_pagina_sem_diagrama_conta_como_pagina(self) -> None:
        """"Esta página não tem diagrama" é uma afirmação, e é ela que mede falso positivo."""
        paginas = [FieldPage(pdf="a.pdf", page=1, diagrams=(), reviewed=True)]
        self.assertEqual(field_set_identity(paginas), {"pages": 1, "annotated": 0})

    def test_todo_relatorio_corrente_mediu_o_conjunto_de_hoje(self) -> None:
        """**O critério de aceite.** Sem isto, um número de 38 diagramas e um de 39 entram na
        mesma tabela sem nada avisar -- e foi assim que quatro itens de spec foram julgados."""
        hoje = self._hoje()
        divergentes = []
        for nome, por_que in sorted(RELATORIOS_CORRENTES.items()):
            caminho = RAIZ / "docs" / "metrics" / nome
            if not caminho.exists():
                divergentes.append(f"{nome}: citado como corrente ({por_que}) e não existe")
                continue
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            medido = {"pages": dados.get("pages"), "annotated": dados.get("annotated")}
            if medido != hoje:
                divergentes.append(f"{nome}: mediu {medido}, e o conjunto de hoje é {hoje}")

        self.assertEqual(
            divergentes,
            [],
            "Relatório citado como corrente medido sobre outro conjunto. Ou remeça-o com "
            "`cvoff-field --json`, ou tire-o de RELATORIOS_CORRENTES e diga no documento que "
            "ele é histórico.",
        )

    def test_um_relatorio_de_conjunto_antigo_e_pego(self) -> None:
        """A guarda demonstrada sobre um caso sintético, para o teste acima não ser vacuamente
        verdadeiro no dia em que a lista ficar vazia."""
        hoje = self._hoje()
        antigo = {"pages": hoje["pages"] - 2, "annotated": hoje["annotated"] - 1}
        self.assertNotEqual(antigo, hoje)

    def test_os_relatorios_historicos_declaram_o_conjunto_deles(self) -> None:
        """O que torna o cabeçalho do EXPERIMENTS_FASE7 verificável em vez de uma promessa:
        todo relatório da Fase 7 diz `15 / 38` no próprio arquivo."""
        historicos = sorted((RAIZ / "docs" / "metrics").glob("field_202608[01]*.json"))
        if not historicos:
            raise unittest.SkipTest("sem relatórios históricos neste clone")
        for caminho in historicos:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            with self.subTest(relatorio=caminho.name):
                self.assertIn("pages", dados, "sem a identidade, o relatório não é auditável")
                self.assertIn("annotated", dados)
