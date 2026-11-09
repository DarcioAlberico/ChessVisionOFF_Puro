from __future__ import annotations

import dataclasses
import json
import logging
import tempfile
import threading
import types
import typing
import unittest
from pathlib import Path
from unittest.mock import patch

import chess
import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.config import ReadingOrder
from chess_diagram_ocr.detection import DiagramCandidate
from chess_diagram_ocr.export_checkpoint import (
    CheckpointWriter,
    ScanParams,
    _params_diff,
    load_partial,
    partial_path_for,
    position_from_dict,
    position_to_dict,
)
from chess_diagram_ocr.gallery import DiagramAnnotation, GalleryAnnotations, load_annotations, save_annotations
from chess_diagram_ocr.inference import OrientedPrediction, prediction_from_probs
from chess_diagram_ocr.pdf_text import DiagramContext
from chess_diagram_ocr.pdf_to_pgn import DiagramPosition, save_pdf_positions_to_pgn, scan_pdf_positions
from chess_diagram_ocr.semantics import SideToMove

KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"


def params(**overrides) -> ScanParams:
    base = {
        "source_name": "livro.pdf",
        "model_path": "models/piece_classifier.pt",
        "dpi": 220,
        "max_boards_per_page": 8,
        "orientation": "auto",
        "reading_order": "column",
        "read_text": True,
        "start_page": 0,
        "end_page": None,
    }
    base.update(overrides)
    return ScanParams(**base)


def position(page: int = 0, diagram: int = 1) -> DiagramPosition:
    return DiagramPosition(
        page_index=page,
        diagram_index=diagram,
        fen=KINGS_ONLY,
        confidence=0.97,
        min_confidence=0.91,
        is_legal=True,
        is_fatal=False,
        problems=("nenhum",),
        rotation=180,
        orientation_ambiguous=True,
        orientation_reason="margem apertada",
        side_to_move=SideToMove(color=chess.BLACK, source="text", reason="legenda", conflicting=True),
        context=DiagramContext(
            caption="5\nMorphy-De Riviere",
            side_to_move=chess.BLACK,
            side_to_move_evidence="pretas jogam",
            exercise_number=5,
            players=("Morphy", "De Riviere"),
            event="Paris",
            year=1858,
        ),
        detection_source="embedded",
        duplicate_of=(3, 2),
    )


class SerializationTests(unittest.TestCase):
    """Se a serialização perder um campo, retomar produz um PGN diferente do inteiro."""

    def test_round_trip_preserves_every_field(self) -> None:
        original = position()
        restored = position_from_dict(position_to_dict(original))
        self.assertEqual(restored, original)

    def test_round_trip_of_a_bare_position(self) -> None:
        bare = DiagramPosition(page_index=2, diagram_index=1, fen=KINGS_ONLY, confidence=0.5)
        self.assertEqual(position_from_dict(position_to_dict(bare)), bare)

    def test_side_to_move_color_survives(self) -> None:
        restored = position_from_dict(position_to_dict(position()))
        assert restored.side_to_move is not None
        self.assertEqual(restored.side_to_move.color, chess.BLACK)
        self.assertTrue(restored.side_to_move.conflicting)


def _valor_diferente(tipo: object, padrao: object, nome: str) -> object:
    """Um valor do tipo anotado que não é o padrão do campo -- gerado da anotação, não escrito.

    É o que deixa um campo acrescentado depois entrar no teste sozinho (S-819): ninguém
    precisa lembrar de escrever um exemplo para ele, assim como ninguém lembrou de escrever
    a chave dele na serialização.
    """
    origem, args = typing.get_origin(tipo), typing.get_args(tipo)
    if origem in (typing.Union, types.UnionType):
        return _valor_diferente(next(a for a in args if a is not type(None)), padrao, nome)
    if origem is typing.Literal:
        return next(a for a in args if a != padrao)
    if origem is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return (_valor_diferente(args[0], None, nome),)
        return tuple(_valor_diferente(a, None, nome) for a in args)
    if isinstance(tipo, type) and dataclasses.is_dataclass(tipo):
        return _exemplar(tipo)
    if tipo is bool:
        return not padrao if isinstance(padrao, bool) else True
    if tipo is int:
        return 7
    if tipo is float:
        return 0.25
    if tipo is str:
        return f"<{nome}>"
    raise AssertionError(f"{nome}: tipo sem gerador no teste: {tipo!r}")


def _padrao(campo: dataclasses.Field) -> object:
    if campo.default is not dataclasses.MISSING:
        return campo.default
    if campo.default_factory is not dataclasses.MISSING:
        return campo.default_factory()
    return None


def _exemplar(cls: type) -> object:
    """Uma instância de `cls` com **todo** campo fora do padrão."""
    dicas = typing.get_type_hints(cls)
    return cls(**{
        campo.name: _valor_diferente(dicas[campo.name], _padrao(campo), campo.name)
        for campo in dataclasses.fields(cls)
    })


def _ida_e_volta_pelo_arquivo(original: DiagramPosition) -> DiagramPosition:
    """O caminho de quem cancela e retoma: grava o parcial e lê de volta."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "livro.partial.jsonl"
        CheckpointWriter(path, params(), every=1).record_page(original.page_index, [original])
        partial = load_partial(path, params())
    assert partial is not None
    [restored] = partial.positions
    return restored


class EveryFieldSurvivesResumeTests(unittest.TestCase):
    """S-819: a retomada não perde campo nenhum, nem os que vierem depois.

    A lista de campos da serialização estava escrita à mão e a dataclass cresceu sem ela: a
    página lida antes da interrupção saía sem `[Stipulation]` nem `[OCRStipulation]`, e como
    `gate_confidence` sobrevivia, uma posição aceita por reparo de estipulação saía sem dizer
    que foi reparada.
    """

    BASE = DiagramPosition(page_index=0, diagram_index=1, fen=KINGS_ONLY, confidence=0.5)

    def test_cada_campo_da_posicao_sobrevive(self) -> None:
        dicas = typing.get_type_hints(DiagramPosition)
        for campo in dataclasses.fields(DiagramPosition):
            with self.subTest(campo=campo.name):
                valor = _valor_diferente(dicas[campo.name], _padrao(campo), campo.name)
                original = dataclasses.replace(self.BASE, **{campo.name: valor})
                self.assertEqual(getattr(_ida_e_volta_pelo_arquivo(original), campo.name), valor)

    def test_cada_campo_do_contexto_sobrevive(self) -> None:
        dicas = typing.get_type_hints(DiagramContext)
        for campo in dataclasses.fields(DiagramContext):
            with self.subTest(campo=campo.name):
                valor = _valor_diferente(dicas[campo.name], _padrao(campo), campo.name)
                original = dataclasses.replace(self.BASE, context=DiagramContext(**{campo.name: valor}))
                restored = _ida_e_volta_pelo_arquivo(original)
                assert restored.context is not None
                self.assertEqual(getattr(restored.context, campo.name), valor)

    def test_posicao_com_tudo_preenchido_volta_igual(self) -> None:
        original = _exemplar(DiagramPosition)
        assert isinstance(original, DiagramPosition)
        self.assertEqual(_ida_e_volta_pelo_arquivo(original), original)

    def test_chave_desconhecida_e_recusada(self) -> None:
        """Ler em silêncio uma chave que a dataclass não tem é perder campo do outro lado."""
        cru = position_to_dict(self.BASE)
        cru["campo_do_futuro"] = 1
        with self.assertRaises(ValueError) as erro:
            position_from_dict(cru)
        self.assertIn("campo_do_futuro", str(erro.exception))

    def test_parcial_da_versao_anterior_retoma_com_aviso(self) -> None:
        """O parcial v1 não tinha os campos novos: retoma, com eles no padrão, e avisa."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            cabecalho = {"kind": "header", "version": 1, "params": params().to_dict()}
            pagina_v1 = {
                "kind": "page",
                "page_index": 0,
                "positions": [{
                    "page_index": 0, "diagram_index": 1, "fen": KINGS_ONLY, "confidence": 0.97,
                    "side_to_move": {"color": False, "source": "text", "reason": "", "conflicting": False},
                    "context": {"caption": "5", "side_to_move": False, "players": ["A", "B"]},
                    "duplicate_of": [3, 2], "gate_confidence": 0.8,
                }],
            }
            path.write_bytes(
                (json.dumps(cabecalho) + "\n" + json.dumps(pagina_v1) + "\n").encode("utf-8")
            )
            with self.assertLogs("chess_diagram_ocr.export_checkpoint", level=logging.WARNING) as captured:
                partial = load_partial(path, params())
            assert partial is not None
            [restored] = partial.positions
            self.assertEqual(restored.duplicate_of, (3, 2))
            self.assertEqual(restored.stipulation, "")
            assert restored.context is not None
            self.assertEqual(restored.context.players, ("A", "B"))
            self.assertTrue(any("versão anterior" in line for line in captured.output))


class ModelIdentityTests(unittest.TestCase):
    """S-57: "os mesmos parâmetros" inclui o mesmo **arquivo** de modelo, não o mesmo caminho.

    O treino reescreve sempre `models/piece_classifier.pt`. Exportar metade de um livro,
    cancelar, treinar e retomar juntava metade de um PGN lido por um modelo com metade lida
    por outro -- e o docstring do módulo prometia justamente que outro modelo descartava o
    parcial. Ele comparava o caminho.
    """

    def test_mesmo_caminho_e_arquivo_diferente_recusa_o_parcial(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            antigos = params(model_identity="8786991-111")
            writer = CheckpointWriter(path, antigos, every=1)
            writer.record_page(0, [position(0, 1)])
            writer.flush()

            depois_do_treino = params(model_identity="8787400-222")
            self.assertIsNone(load_partial(path, depois_do_treino))
            self.assertIsNotNone(load_partial(path, antigos))

    def test_um_parcial_anterior_a_s57_continua_sendo_retomado(self) -> None:
        """Recusá-lo por não registrar algo que ninguém lhe perguntou jogaria fora trabalho."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            writer = CheckpointWriter(path, params(model_identity=""), every=1)
            writer.record_page(0, [position(0, 1)])
            writer.flush()

            retomado = load_partial(path, params(model_identity="8787400-222"))
            self.assertIsNotNone(retomado)

    def test_a_mensagem_diz_que_o_arquivo_do_modelo_mudou(self) -> None:
        antigos = params(model_identity="a")
        novos = params(model_identity="b")
        self.assertIn("o arquivo do modelo mudou", _params_diff(antigos, novos))

    def test_dpi_diferente_continua_recusando_como_antes(self) -> None:
        self.assertFalse(params(dpi=220).is_compatible_with(params(dpi=300)))


class PartialFileTests(unittest.TestCase):
    def test_writer_and_loader_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            writer = CheckpointWriter(path, params(), every=1)
            writer.record_page(0, [position(0, 1)])
            writer.record_page(1, [position(1, 1), position(1, 2)])

            partial = load_partial(path, params())
            assert partial is not None
            self.assertEqual(len(partial.positions), 3)
            self.assertEqual(partial.last_page_done, 1)
            self.assertEqual(partial.resume_from, 2)

    def test_pages_are_buffered_until_the_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            writer = CheckpointWriter(path, params(), every=5)
            for page in range(3):
                writer.record_page(page, [position(page, 1)])
            self.assertFalse(path.exists())

            writer.flush()
            partial = load_partial(path, params())
            assert partial is not None
            self.assertEqual(partial.last_page_done, 2)

    def test_different_parameters_invalidate_the_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            writer = CheckpointWriter(path, params(dpi=220), every=1)
            writer.record_page(0, [position()])

            with self.assertLogs("chess_diagram_ocr.export_checkpoint", level=logging.WARNING) as captured:
                self.assertIsNone(load_partial(path, params(dpi=300)))
            self.assertTrue(any("outros parâmetros" in line for line in captured.output))

    def test_torn_last_line_keeps_the_pages_before_it(self) -> None:
        """Queda de energia no meio da escrita: a última linha não parseia, o resto vale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            writer = CheckpointWriter(path, params(), every=1)
            writer.record_page(0, [position(0, 1)])
            writer.record_page(1, [position(1, 1)])
            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"kind": "page", "page_index": 2, "positi')

            with self.assertLogs("chess_diagram_ocr.export_checkpoint", level=logging.WARNING):
                partial = load_partial(path, params())
            assert partial is not None
            self.assertEqual(partial.last_page_done, 1)
            self.assertEqual(len(partial.positions), 2)

    def test_parcial_rasgado_no_meio_de_um_acento_retoma_da_pagina_anterior(self) -> None:
        """A queda no meio do `á` (dois bytes) rasga só a última linha, e não o arquivo (S-905).

        Antes, o arquivo inteiro era decodificado antes do laço que descarta a linha rasgada: o
        `UnicodeDecodeError` jogava fora as páginas boas, e a exportação recomeçava do zero.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            writer = CheckpointWriter(path, params(), every=1)
            writer.record_page(0, [position(0, 1)])
            writer.record_page(1, [position(1, 1)])
            with path.open("ab") as handle:
                handle.write(b'{"kind": "page", "page_index": 2, "legenda": "an' + "á".encode()[:1])

            with self.assertLogs("chess_diagram_ocr.export_checkpoint", level=logging.WARNING):
                partial = load_partial(path, params())
            assert partial is not None
            self.assertEqual(1, partial.last_page_done)
            self.assertEqual(2, partial.resume_from)

    def test_missing_file_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(load_partial(Path(tmpdir) / "nao-existe.jsonl", params()))

    def test_resumed_writer_appends_instead_of_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            CheckpointWriter(path, params(), every=1).record_page(0, [position(0, 1)])

            continuacao = CheckpointWriter(path, params(), every=1, resumed=True)
            continuacao.record_page(1, [position(1, 1)])

            partial = load_partial(path, params())
            assert partial is not None
            self.assertEqual([p.page_index for p in partial.positions], [0, 1])

    def test_partial_path_sits_next_to_the_pgn(self) -> None:
        self.assertEqual(partial_path_for(Path("PGN/livro.pgn")), Path("PGN/livro.partial.jsonl"))


def oriented(fen: str, confidence: float = 0.99) -> OrientedPrediction:
    return OrientedPrediction(
        prediction=prediction_from_probs(probs_for_fen(fen, confidence)),
        rotation=0,
        margin=0.5,
        ambiguous=False,
        reason="teste",
    )


def candidate() -> DiagramCandidate:
    return DiagramCandidate(
        board_rgb=np.zeros((800, 800, 3), dtype=np.uint8),
        bbox_pdf=(10.0, 10.0, 90.0, 90.0),
        source="embedded",
        detector_score=0.9,
        native_size=(320, 320),
    )


class CancelAndResumeTests(unittest.TestCase):
    """S-24: cancelar preserva o parcial, e retomar produz o mesmo PGN da execução inteira."""

    def setUp(self) -> None:
        self.page_count = 6
        self.patches = [
            patch("chess_diagram_ocr.pdf_to_pgn._get_pdf_page_count", return_value=self.page_count),
            patch("chess_diagram_ocr.pdf_to_pgn.load_model", return_value=("model", "cpu")),
            patch(
                "chess_diagram_ocr.pdf_to_pgn._render_pdf_page",
                side_effect=lambda *a, **k: np.zeros((10, 10, 3), dtype=np.uint8),
            ),
            patch("chess_diagram_ocr.pdf_to_pgn._detect_page_diagrams", side_effect=lambda *a, **k: [candidate()]),
            patch("chess_diagram_ocr.pdf_to_pgn._page_contexts", side_effect=lambda *a, **k: [DiagramContext()]),
            patch("chess_diagram_ocr.pdf_to_pgn.predict_with_orientation", side_effect=lambda *a, **k: oriented(KINGS_ONLY)),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in self.patches])

    def test_cancel_stops_between_pages(self) -> None:
        cancel = threading.Event()
        visited: list[int] = []

        def _progress(page_index: int, total: int, boards: int, positions: int) -> None:
            visited.append(page_index)
            if len(visited) == 2:
                cancel.set()

        positions = scan_pdf_positions(
            Path("livro.pdf"),
            cancel_event=cancel,
            progress_callback=_progress,
        )

        # Parou logo apos a segunda pagina, e nao no fim das seis.
        self.assertEqual(visited, [0, 1])
        self.assertEqual(len(positions), 2)

    def test_cancel_already_set_reads_nothing(self) -> None:
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(scan_pdf_positions(Path("livro.pdf"), cancel_event=cancel), [])

    def test_resume_produces_the_same_pgn_as_an_uninterrupted_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            inteiro = Path(tmpdir) / "inteiro.pgn"
            report_inteiro = save_pdf_positions_to_pgn(pdf_source=Path("livro.pdf"), output_path=inteiro)
            self.assertFalse(report_inteiro.cancelled)
            self.assertIsNone(report_inteiro.resumed_from_page)
            # Terminar apaga o parcial: ele existe para atravessar a interrupcao, nao para
            # virar um segundo formato de saida.
            self.assertFalse(partial_path_for(inteiro).exists())

            interrompido = Path(tmpdir) / "retomado.pgn"
            cancel = threading.Event()
            paginas: list[int] = []

            def _progress(page_index: int, total: int, boards: int, positions: int) -> None:
                paginas.append(page_index)
                if len(paginas) == 3:
                    cancel.set()

            parcial = save_pdf_positions_to_pgn(
                pdf_source=Path("livro.pdf"),
                output_path=interrompido,
                cancel_event=cancel,
                checkpoint_every=1,
                progress_callback=_progress,
            )
            self.assertTrue(parcial.cancelled)
            self.assertEqual(parcial.partial_path, partial_path_for(interrompido))
            self.assertTrue(parcial.partial_path.exists())
            self.assertEqual(len(parcial.accepted), 3)

            retomado = save_pdf_positions_to_pgn(pdf_source=Path("livro.pdf"), output_path=interrompido)
            self.assertFalse(retomado.cancelled)
            self.assertEqual(retomado.resumed_from_page, 3)
            self.assertEqual(len(retomado.accepted), len(report_inteiro.accepted))
            # O header `[ProvenanceFile]` (A11) leva o nome do sidecar, que segue o nome do PGN:
            # os dois arquivos têm nomes diferentes de propósito, e é o único header que difere.
            self.assertEqual(
                interrompido.read_text(encoding="utf-8").replace("retomado.proveniencia", "X"),
                inteiro.read_text(encoding="utf-8").replace("inteiro.proveniencia", "X"),
            )
            self.assertFalse(partial_path_for(interrompido).exists())

    def test_resume_disabled_starts_over(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            saida = Path(tmpdir) / "livro.pgn"
            cancel = threading.Event()
            cancel.set()
            save_pdf_positions_to_pgn(pdf_source=Path("livro.pdf"), output_path=saida, cancel_event=cancel)

            report = save_pdf_positions_to_pgn(pdf_source=Path("livro.pdf"), output_path=saida, resume=False)
            self.assertIsNone(report.resumed_from_page)
            self.assertEqual(len(report.accepted), self.page_count)

    def test_galeria_de_outro_livro_de_mesmo_nome_nao_entra_no_pgn(self) -> None:
        """S-878: `b/Livro.pdf` exporta sem as anotações de `a/Livro.pdf`, e sem falhar o lote."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            livro_a, livro_b, galeria = raiz / "a" / "Livro.pdf", raiz / "b" / "Livro.pdf", raiz / "gallery"
            for livro in (livro_a, livro_b):
                livro.parent.mkdir()
                livro.write_bytes(b"%PDF-1.4\n")
            do_a = GalleryAnnotations()
            do_a.set(0, 1, DiagramAnnotation(headers={"White": "Karpov"}))
            save_annotations(livro_a, do_a, directory=galeria)

            def _da_pasta(pdf: Path, *, reading_order: ReadingOrder) -> GalleryAnnotations:
                return load_annotations(pdf, directory=galeria, reading_order=reading_order)

            with patch("chess_diagram_ocr.pdf_to_pgn.load_annotations", _da_pasta):
                for livro in (livro_a, livro_b):
                    save_pdf_positions_to_pgn(pdf_source=livro, output_path=raiz / f"{livro.parent.name}.pgn")

            self.assertIn('[White "Karpov"]', (raiz / "a.pgn").read_text(encoding="utf-8"))
            self.assertNotIn("Karpov", (raiz / "b.pgn").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
