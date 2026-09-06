"""Camada de serviço (S-31): o pipeline de OCR exercitado sem nenhuma interface.

O critério de aceite da S-31 diz "`OcrService` testável sem Tk", e é literalmente o que
este arquivo verifica: nenhum `import tkinter`, nenhum `streamlit`, nenhuma janela. Era
justamente por estar preso dentro de `ChessOcrTkApp` que o pipeline não tinha teste nenhum
-- e foi assim que o Streamlit pôde divergir dele sem nada acusar.
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import fitz
import numpy as np
import torch
import torch.nn as nn
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import service as modulo_do_servico
from chess_diagram_ocr.board_detection import NoBoardDetectedError
from chess_diagram_ocr.config import BOARD_SIZE, PIECE_CLASSES, PIECE_TO_IDX
from chess_diagram_ocr.detection import DiagramCandidate
from chess_diagram_ocr.model import ArchConfig
from chess_diagram_ocr.service import (
    OcrService,
    RecheckReport,
    RecognitionOptions,
    RecognitionOrigin,
    RecognizedDiagram,
    refine_board_from_quad,
)

# Rei preto em a8 em xeque pela dama branca em a7, rei branco em h1. A posição só é legal
# com as pretas a jogar -- é o caso que a S-17 usa para deduzir a vez sem texto nenhum, e
# o mesmo que denunciava o `w` fixo do Streamlit como ilegal.
PRETAS_A_JOGAR = "k7/Q7/8/8/8/8/8/7K"


def _class_indices(placement: str) -> list[int]:
    """As 64 classes na ordem de leitura a8..h1 a partir do campo de peças da FEN."""
    indices: list[int] = []
    for row in placement.split("/"):
        for char in row:
            if char.isdigit():
                indices.extend([PIECE_TO_IDX["empty"]] * int(char))
            else:
                indices.append(PIECE_TO_IDX[char])
    return indices


class _ScriptedModel(nn.Module):
    """Responde uma classe escolhida por posição no lote.

    O lote que `board_probabilities` monta é exatamente as 64 casas em ordem de leitura,
    então ditar a resposta por índice dá controle total sobre a FEN lida -- sem precisar
    de um `.pt` nem de pesos que acertem coisa alguma.
    """

    def __init__(self, placement: str = PRETAS_A_JOGAR, logit: float = 8.0) -> None:
        super().__init__()
        self.arch = ArchConfig()
        self.temperature = 1.0
        self.indices = _class_indices(placement)
        self.logit = logit
        self.forward_calls = 0

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        self.forward_calls += 1
        logits = torch.zeros(x.shape[0], len(PIECE_CLASSES))
        for row in range(x.shape[0]):
            logits[row, self.indices[row % 64]] = self.logit
        return logits


def _service(placement: str = PRETAS_A_JOGAR) -> tuple[OcrService, _ScriptedModel]:
    model = _ScriptedModel(placement)
    loads = {"count": 0}

    def loader(path: Path) -> tuple[nn.Module, str]:
        loads["count"] += 1
        return model, "cpu"

    service = OcrService(model_path=Path("inexistente.pt"), loader=loader)
    service.load_count = loads  # type: ignore[attr-defined]
    return service, model


def _board_image() -> np.ndarray:
    """Um tabuleiro 8×8 de verdade, com moldura, no tamanho que o pipeline usa.

    **Era ruído aleatório (S-160), e o nome era mentira.** Passava porque `detect_boards`
    achava dois "tabuleiros" no ruído -- um deles com alongamento 2,81, uma mancha torta cuja
    caixa alinhada aos eixos saía quadrada. Corrigida a régua do aspecto, o ruído passou a
    devolver zero, que é a resposta certa, e o teste de recorte deste arquivo caiu junto.

    Trocar por um tabuleiro desenhado é o conserto, e não afrouxar a guarda: o modelo aqui é
    ditado, então a imagem nunca precisou ser ruído -- ela só precisa ser detectável, que é
    justamente o que o nome dela sempre prometeu.
    """
    casa = BOARD_SIZE // 8
    imagem = np.full((BOARD_SIZE, BOARD_SIZE, 3), 235, dtype=np.uint8)
    for linha in range(8):
        for coluna in range(8):
            if (linha + coluna) % 2:
                imagem[linha * casa : (linha + 1) * casa, coluna * casa : (coluna + 1) * casa] = 60
    imagem[:3, :] = imagem[-3:, :] = imagem[:, :3] = imagem[:, -3:] = 0
    return imagem


def _upright() -> RecognitionOptions:
    """Orientação fixa em 0°: `auto` faria duas leituras e o modelo ditado é simétrico."""
    return RecognitionOptions(orientation="0", max_boards=4)


class OriginTests(unittest.TestCase):
    """A origem era f-string montada em três lugares e interpretada em dois."""

    def test_page_origin_round_trips(self) -> None:
        origin = RecognitionOrigin.for_page("livro.pdf", 16)
        self.assertEqual(origin.as_text(), "pdf:livro.pdf:page:16")
        self.assertEqual(RecognitionOrigin.parse(origin.as_text()), origin)

    def test_image_origin_round_trips(self) -> None:
        origin = RecognitionOrigin.for_image("foto.png")
        self.assertEqual(origin.as_text(), "local-image:foto.png")
        self.assertEqual(RecognitionOrigin.parse(origin.as_text()), origin)

    def test_crop_origin_keeps_the_page_and_is_not_a_whole_page(self) -> None:
        origin = RecognitionOrigin.for_crop("livro.pdf", 16, (10, 20, 300, 400))
        self.assertEqual(origin.as_text(), "pdf:livro.pdf:page:16:crop=(10,20)-(300,400)")

        lido = RecognitionOrigin.parse(origin.as_text())
        self.assertEqual(lido.page_index, 16)
        self.assertEqual(lido.kind, "crop")
        self.assertFalse(lido.is_whole_page)

    def test_only_a_whole_page_may_go_to_the_page_cache(self) -> None:
        self.assertTrue(RecognitionOrigin.for_page("livro.pdf", 3).is_whole_page)
        self.assertFalse(RecognitionOrigin.for_image("foto.png").is_whole_page)

    def test_page_zero_is_a_real_page_and_not_a_falsy_miss(self) -> None:
        """`if pagina:` em vez de `is None` quebraria a primeira página do livro."""
        lido = RecognitionOrigin.parse("pdf:livro.pdf:page:0")
        self.assertEqual(lido.page_index, 0)
        self.assertTrue(lido.is_whole_page)

    def test_a_pdf_name_containing_the_marker_does_not_confuse_the_parser(self) -> None:
        """O marcador que vale é o último; o nome do arquivo não interfere."""
        self.assertEqual(RecognitionOrigin.parse("pdf:my:page:book.pdf:page:42").page_index, 42)

    def test_an_origin_without_a_page_marker_is_not_a_page_result(self) -> None:
        self.assertFalse(RecognitionOrigin.parse("pdf:livro.pdf").is_whole_page)

    def test_unparseable_origin_degrades_to_image_instead_of_raising(self) -> None:
        """Procedência estranha ainda vale gravada; exceção no meio de um salvamento, não."""
        lido = RecognitionOrigin.parse("pdf:livro.pdf:page:dezesseis")
        self.assertEqual(lido.kind, "image")
        self.assertFalse(lido.is_whole_page)

    def test_sample_page_is_one_based_like_the_number_the_user_sees(self) -> None:
        campos = RecognitionOrigin.for_page("livro.pdf", 16).sample_fields()
        self.assertEqual(campos, {"source_pdf": "livro.pdf", "source_page": 17})

    def test_local_image_has_no_page_to_record(self) -> None:
        campos = RecognitionOrigin.for_image("foto.png").sample_fields()
        self.assertEqual(campos["source_page"], "")

    def test_o_livro_vai_pelo_nome_e_nao_pelo_caminho_da_maquina(self) -> None:
        """**72 linhas do `labels.csv` traziam o caminho inteiro** (S-19/S-506).

        `document` e a chave de cache da janela e precisa ser o caminho -- dois livros de mesmo
        nome em pastas diferentes sao dois livros. O CSV quer o nome, e o diz por escrito em
        `saved_diagrams_by_page` e em `SavedSample.source_pdf`. Quem os concilia e este metodo,
        que e o unico ponto onde a origem vira coluna.

        O efeito de gravar o caminho e silencioso duas vezes: o diagrama nao volta marcado de
        verde ao reabrir a pagina, e a contagem por livro ve o mesmo livro duas vezes.
        """
        caminho = "C:" + chr(92) + "Chess" + chr(92) + "PDF" + chr(92) + "livro.pdf"
        self.assertEqual(
            RecognitionOrigin.for_page(caminho, 16).sample_fields(),
            {"source_pdf": "livro.pdf", "source_page": 17},
        )
        self.assertEqual(
            RecognitionOrigin.for_page("/home/alguem/PDF/livro.pdf", 0).sample_fields()["source_pdf"],
            "livro.pdf",
        )

    def test_uma_origem_sem_documento_nao_inventa_nome(self) -> None:
        """`Path("").name` e `""`, e o vazio tem de atravessar: linha sem procedencia e ignorada
        por `saved_diagrams_by_page`, e um nome inventado entraria no indice."""
        self.assertEqual(RecognitionOrigin(kind="pdf", document="").sample_fields()["source_pdf"], "")


class RecognizeTests(unittest.TestCase):
    def test_a_detected_board_becomes_a_diagram_with_the_prediction_kept(self) -> None:
        service, _ = _service()
        boards = [(_board_image(), None)]

        diagramas = service.recognize_image(_board_image(), options=_upright(), boards=boards)

        self.assertEqual(len(diagramas), 1)
        self.assertEqual(diagramas[0].placement, PRETAS_A_JOGAR)
        # A matriz por casa sobrevive ate a UI: e o insumo do heatmap da S-21, e era
        # exatamente o que o dicionario do Streamlit descartava.
        self.assertIsNotNone(diagramas[0].probs)
        assert diagramas[0].probs is not None
        self.assertEqual(diagramas[0].probs.shape, (64, len(PIECE_CLASSES)))
        self.assertEqual(len(diagramas[0].square_confidences), 64)

    def test_legality_is_composed_with_the_inferred_side_not_a_fixed_white(self) -> None:
        """O defeito que o Streamlit tinha: `w` fixo tornava esta posição ilegal."""
        service, _ = _service()

        diagrama = service.recognize_image(
            _board_image(), options=_upright(), boards=[(_board_image(), None)]
        )[0]

        self.assertEqual(diagrama.side_to_move, "b")
        self.assertEqual(diagrama.side_to_move_source, "legality")
        self.assertTrue(diagrama.is_legal)

    def test_every_diagram_carries_its_own_index(self) -> None:
        service, _ = _service()
        boards = [(_board_image(), None) for _ in range(3)]

        diagramas = service.recognize_image(_board_image(), options=_upright(), boards=boards)

        self.assertEqual([d.index for d in diagramas], [0, 1, 2])

    def test_nothing_detected_raises_instead_of_returning_an_empty_page(self) -> None:
        """E levanta a classe **nomeada** (S-125), para quem chama poder testar o tipo.

        Era `ValueError`, e a janela separava "página sem diagrama" de "o OCR quebrou"
        procurando a mensagem dentro do texto da exceção."""
        service, _ = _service()
        with self.assertRaises(NoBoardDetectedError):
            service.recognize_image(_board_image(), options=_upright(), boards=[])

    def test_fallback_treats_the_whole_image_as_the_board(self) -> None:
        """Quem selecionou a área com o mouse já disse onde está o diagrama."""
        service, _ = _service()
        options = RecognitionOptions(orientation="0", fallback_to_full_image=True)

        diagramas = service.recognize_image(_board_image(), options=options, boards=[])

        self.assertEqual(len(diagramas), 1)
        self.assertIsNone(diagramas[0].quad)

    def test_region_clamps_to_the_page_instead_of_slicing_out_of_bounds(self) -> None:
        """Retângulo maior que a página vira a página inteira, não uma fatia vazia."""
        service, _ = _service()
        page = _board_image()

        recortado = service.recognize_region(page, (-50, -50, 10_000, 10_000), options=_upright())
        inteiro = service.recognize_image(page, options=_upright())

        self.assertEqual(len(recortado), len(inteiro))
        self.assertGreaterEqual(len(recortado), 1)


class ModelLifecycleTests(unittest.TestCase):
    def test_the_model_is_loaded_once_and_reused(self) -> None:
        service, _ = _service()
        for _ in range(3):
            service.recognize_image(_board_image(), options=_upright(), boards=[(_board_image(), None)])

        self.assertEqual(service.load_count["count"], 1)  # type: ignore[attr-defined]

    def test_invalidating_forces_the_next_read_to_load_again(self) -> None:
        service, _ = _service()
        service.load()
        service.invalidate_model()
        service.load()

        self.assertEqual(service.load_count["count"], 2)  # type: ignore[attr-defined]

    def test_device_label_says_so_when_no_model_is_loaded_yet(self) -> None:
        service, _ = _service()
        self.assertIn("nenhum modelo", service.device_label)

    def test_reload_waits_for_a_recognition_in_flight(self) -> None:
        """A corrida que a S-31 nomeia: o treino zerava o modelo durante um OCR.

        Sem o lock, `invalidate_model` retornaria de imediato -- é isso que o tempo
        registrado aqui distingue, e não a simples ausência de erro.
        """
        service, _ = _service()
        dentro = threading.Event()
        pode_sair = threading.Event()
        invalidou = threading.Event()

        def segurando() -> None:
            with service.model_session():
                dentro.set()
                pode_sair.wait(timeout=5)

        ocr = threading.Thread(target=segurando, daemon=True)
        ocr.start()
        self.assertTrue(dentro.wait(timeout=5))

        def invalidando() -> None:
            service.invalidate_model()
            invalidou.set()

        treino = threading.Thread(target=invalidando, daemon=True)
        treino.start()

        # Enquanto a sessao esta aberta, a invalidacao nao passa.
        self.assertFalse(invalidou.wait(timeout=0.3))
        pode_sair.set()
        self.assertTrue(invalidou.wait(timeout=5))
        ocr.join(timeout=5)


class DiagramTests(unittest.TestCase):
    def _diagram(self) -> RecognizedDiagram:
        service, _ = _service()
        return service.recognize_image(
            _board_image(), options=_upright(), boards=[(_board_image(), None)]
        )[0]

    def test_changing_the_side_marks_it_manual_and_clears_the_conflict(self) -> None:
        diagrama = self._diagram()
        diagrama.side_conflicting = True

        diagrama.set_side_to_move("w")

        self.assertEqual(diagrama.side_to_move, "w")
        self.assertEqual(diagrama.side_to_move_source, "manual")
        self.assertFalse(diagrama.side_conflicting)

    def test_legality_follows_the_side_because_turning_it_can_fix_the_position(self) -> None:
        """Trocar a vez resolve o "xeque invertido" sem mexer em nenhuma peça (S-17)."""
        diagrama = self._diagram()
        self.assertTrue(diagrama.is_legal)

        diagrama.set_side_to_move("w")
        diagrama.resolve_legality()

        self.assertFalse(diagrama.is_legal)

    def test_legality_can_be_recomputed_from_a_hand_edited_placement(self) -> None:
        diagrama = self._diagram()
        diagrama.resolve_legality("8/8/8/8/8/8/8/8")

        self.assertFalse(diagrama.is_legal)
        self.assertTrue(diagrama.is_fatal)

    def test_context_fields_are_empty_without_a_pdf_caption(self) -> None:
        diagrama = self._diagram()
        self.assertIsNone(diagrama.exercise_number)
        self.assertEqual(diagrama.caption, "")


class SaveSampleTests(unittest.TestCase):
    def test_the_sample_records_where_it_came_from(self) -> None:
        service, _ = _service()
        diagrama = service.recognize_image(
            _board_image(), options=_upright(), boards=[(_board_image(), None)]
        )[0]

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            csv_path = raiz / "labels.csv"
            service.save_sample(
                diagrama,
                PRETAS_A_JOGAR,
                csv_path=csv_path,
                samples_dir=raiz / "samples",
                origin=RecognitionOrigin.for_page("livro.pdf", 16),
            )

            linhas = csv_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(linhas), 2)
        self.assertIn("livro.pdf", linhas[1])
        # Pagina 1-based e o diagrama 1-based, como aparecem na interface.
        self.assertIn("17", linhas[1])
        self.assertIn(",b,", f",{linhas[1]},")

    def test_saving_without_an_origin_leaves_the_fields_empty_instead_of_guessing(self) -> None:
        service, _ = _service()
        diagrama = service.recognize_image(
            _board_image(), options=_upright(), boards=[(_board_image(), None)]
        )[0]

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            csv_path = raiz / "labels.csv"
            service.save_sample(
                diagrama, PRETAS_A_JOGAR, csv_path=csv_path, samples_dir=raiz / "samples"
            )
            cabecalho, linha = csv_path.read_text(encoding="utf-8").splitlines()

        colunas = dict(zip(cabecalho.split(","), linha.split(","), strict=False))
        self.assertEqual(colunas["source_pdf"], "")
        self.assertEqual(colunas["source_page"], "")


class RefineTests(unittest.TestCase):
    def test_without_a_quad_the_image_is_only_resized(self) -> None:
        board, quad = refine_board_from_quad(_board_image(), None)
        self.assertEqual(board.shape, (BOARD_SIZE, BOARD_SIZE, 3))
        self.assertIsNone(quad)

    def test_a_quad_outside_the_image_does_not_crash(self) -> None:
        quad = np.array([[-10, -10], [-5, -10], [-5, -5], [-10, -5]], dtype=np.float32)
        board, _ = refine_board_from_quad(_board_image(), quad)
        self.assertEqual(board.shape, (BOARD_SIZE, BOARD_SIZE, 3))


class NoUiDependencyTests(unittest.TestCase):
    """O critério de aceite da S-31, verificável em vez de prometido."""

    def test_the_service_module_imports_no_ui_toolkit(self) -> None:
        fonte = (
            Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "service.py"
        ).read_text(encoding="utf-8")

        for proibido in ("import tkinter", "import streamlit", "from tkinter", "from PIL"):
            with self.subTest(importacao=proibido):
                self.assertNotIn(proibido, fonte)


if __name__ == "__main__":
    unittest.main()


class RecheckTests(unittest.TestCase):
    """Comparar o que o modelo lê com o rótulo gravado (S-23).

    Morava dentro da janela do Tkinter, onde a única forma de conferir o relatório era
    abrir a aba Dataset e olhar. O que importa aqui é o texto que o usuário lê.
    """

    def _report(self, rotulo: str, lido: str = PRETAS_A_JOGAR) -> RecheckReport:
        service, _ = _service(lido)
        return service.recheck_label(_board_image(), rotulo)

    def test_a_matching_label_reports_full_agreement(self) -> None:
        relatorio = self._report(PRETAS_A_JOGAR)
        self.assertTrue(relatorio.agrees)
        self.assertIn("todas as 64 casas", relatorio.describe("amostra.png"))

    def test_a_differing_label_lists_the_squares_with_both_readings(self) -> None:
        # Mesma posicao, mas com a dama branca em a6 em vez de a7.
        relatorio = self._report("k7/8/Q7/8/8/8/8/7K")

        self.assertFalse(relatorio.agrees)
        texto = relatorio.describe("amostra.png")
        self.assertIn("Divergem em 2 casa(s)", texto)
        self.assertIn("a7:", texto)
        self.assertIn("a6:", texto)

    def test_an_empty_square_is_named_instead_of_shown_blank(self) -> None:
        """"rotulo  | modelo Q" nao diria o que estava lá; "vazia" diz."""
        self.assertIn("vazia", self._report("k7/8/Q7/8/8/8/8/7K").describe("amostra.png"))

    def test_a_wildly_different_label_is_counted_not_listed_in_full(self) -> None:
        """Discordar de 40 casas não pede lista: pede olho humano, e a contagem já diz isso."""
        texto = self._report("8/8/8/8/8/8/8/8").describe("amostra.png", max_squares=1)
        self.assertIn("... e outras", texto)

    def test_the_report_names_the_sample_and_both_readings(self) -> None:
        texto = self._report(PRETAS_A_JOGAR).describe("board_123.png")
        self.assertIn("board_123.png", texto)
        self.assertIn(f"Rotulo:  {PRETAS_A_JOGAR}", texto)
        self.assertIn(f"Modelo:  {PRETAS_A_JOGAR}", texto)


class PaginaComCandidatosProntosTests(unittest.TestCase):
    """`recognize_page` aceita a lista que quem chamou já detectou (S-501).

    **O defeito medido**: o visualizador roda o detector para desenhar os retângulos sobre a
    página, e mandar ler a mesma página rodava tudo de novo. O log de uma sessão de verdade
    mostra as mesmas linhas de "Aparado pela moldura" duas vezes por página -- uma por marcar,
    outra por ler.

    **E o que o parâmetro corrige é maior que o tempo.** Que o retângulo "3" da tela e o
    diagrama 3 da lista sejam o mesmo objeto valia por o detector ser determinístico e receber
    a mesma entrada; passando a lista adiante, passa a valer por construção.
    """

    CAIXA = (60.0, 60.0, 260.0, 260.0)

    def _pdf(self) -> Path:
        """Uma página com o tabuleiro como imagem embutida -- o caminho da S-12."""
        imagem = _board_image()
        pixmap = fitz.Pixmap(fitz.csRGB, BOARD_SIZE, BOARD_SIZE, imagem.tobytes(), False)
        documento = fitz.open()
        pagina = documento.new_page(width=400, height=500)
        pagina.insert_image(fitz.Rect(*self.CAIXA), pixmap=pixmap)
        alvo = pasta_temporaria(self) / "livro.pdf"
        documento.save(str(alvo))
        documento.close()
        return alvo

    def _candidato(self) -> DiagramCandidate:
        return DiagramCandidate(
            board_rgb=_board_image(),
            bbox_pdf=self.CAIXA,
            source="embedded",
            detector_score=1.0,
            native_size=(BOARD_SIZE, BOARD_SIZE),
        )

    def test_com_a_lista_pronta_o_detector_nao_roda_de_novo(self) -> None:
        service, _ = _service()

        def _nao_devia_rodar(*_args: object, **_kwargs: object) -> list[DiagramCandidate]:
            raise AssertionError("o detector rodou de novo com a lista pronta na mão")

        with mock.patch.object(modulo_do_servico, "detect_diagrams_in_pdf_page", _nao_devia_rodar):
            lidos = service.recognize_page(
                self._pdf(), 0, options=_upright(), candidates=[self._candidato()]
            )

        self.assertEqual(1, len(lidos))
        self.assertEqual(PRETAS_A_JOGAR, lidos[0].placement)

    def test_a_procedencia_e_o_lugar_vem_da_lista_recebida(self) -> None:
        """Não basta não redetectar: o que a lista carrega tem de chegar ao diagrama lido.

        `bbox_pdf` é o que casa a leitura com a anotação de campo (S-41) e `detection_source` é
        o que permite auditar o dataset por fonte (S-12) -- se o parâmetro os perdesse, o ganho
        de tempo sairia caro.
        """
        service, _ = _service()

        lidos = service.recognize_page(
            self._pdf(), 0, options=_upright(), candidates=[self._candidato()]
        )

        self.assertEqual(self.CAIXA, lidos[0].bbox_pdf)
        self.assertEqual("embedded", lidos[0].detection_source)

    def test_sem_a_lista_o_caminho_e_o_de_sempre(self) -> None:
        """O padrão continua sendo detectar aqui dentro -- é o que a exportação usa."""
        service, _ = _service()

        lidos = service.recognize_page(self._pdf(), 0, options=_upright())

        self.assertEqual(1, len(lidos))
        self.assertEqual("embedded", lidos[0].detection_source)

    def test_uma_lista_vazia_e_pagina_sem_diagrama_e_nao_pedido_para_detectar(self) -> None:
        """`[]` e `None` são respostas diferentes: uma diz "não há", a outra "não sei".

        Colapsá-las faria a página de prosa que o visualizador já examinou ser reexaminada a
        cada leitura -- e é a página mais comum de um livro.
        """
        service, _ = _service()

        with self.assertRaises(NoBoardDetectedError):
            service.recognize_page(self._pdf(), 0, options=_upright(), candidates=[])
