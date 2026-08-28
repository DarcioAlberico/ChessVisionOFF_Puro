from __future__ import annotations

import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from chess_diagram_ocr.config import PIECE_CLASSES
from chess_diagram_ocr.dataset import BoardGroupedSampler, DatasetEntry, board_groups
from chess_diagram_ocr.labels import DatasetEntry as LabelEntry
from chess_diagram_ocr.training import (
    build_train_transform,
    class_weights_for,
    evaluate_validation,
    labels_hash,
    resolve_num_workers,
    set_seed,
)

LEGAL = "4k3/8/8/8/8/8/8/4K3"
PAWNS = "4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3"


def _index_map(boards: int) -> list[tuple[int, int]]:
    return [(board, square) for board in range(boards) for square in range(64)]


class BoardGroupsTests(unittest.TestCase):
    def test_groups_all_squares_of_each_board(self) -> None:
        groups = board_groups(_index_map(5))
        self.assertEqual(len(groups), 5)
        self.assertTrue(all(len(group) == 64 for group in groups))

    def test_returns_wrapper_positions_not_dataset_indices(self) -> None:
        """Com um `Subset` no meio, devolver indices do dataset apontaria para outras casas."""
        index_map = _index_map(3)
        subset = list(range(64, 192))  # tabuleiros 1 e 2
        groups = board_groups(index_map, subset)

        self.assertEqual(len(groups), 2)
        self.assertEqual(sorted(position for group in groups for position in group), list(range(128)))
        self.assertEqual(groups[0], list(range(64)))

    def test_groups_come_out_in_board_order(self) -> None:
        groups = board_groups(_index_map(4))
        self.assertEqual([group[0] for group in groups], [0, 64, 128, 192])


class BoardGroupedSamplerTests(unittest.TestCase):
    def test_yields_every_index_exactly_once(self) -> None:
        sampler = BoardGroupedSampler(board_groups(_index_map(10)), seed=1)
        drawn = list(sampler)
        self.assertEqual(len(drawn), 640)
        self.assertEqual(sorted(drawn), list(range(640)))
        self.assertEqual(len(sampler), 640)

    def test_a_chunk_touches_a_bounded_number_of_boards(self) -> None:
        """E a propriedade que faz o cache com teto funcionar (S-26)."""
        sampler = BoardGroupedSampler(board_groups(_index_map(200)), seed=1, boards_per_chunk=8)
        drawn = list(sampler)
        for start in range(0, len(drawn), 8 * 64):
            janela = drawn[start : start + 8 * 64]
            self.assertLessEqual(len({index // 64 for index in janela}), 8)

    def test_a_chunk_still_mixes_several_boards_in_one_batch(self) -> None:
        """Um lote de 2 tabuleiros deixaria o BatchNorm com a estatistica de 2 posicoes."""
        sampler = BoardGroupedSampler(board_groups(_index_map(200)), seed=1, boards_per_chunk=32)
        primeiro_lote = list(sampler)[:128]
        self.assertGreater(len({index // 64 for index in primeiro_lote}), 8)

    def test_shuffle_off_is_plain_board_order(self) -> None:
        sampler = BoardGroupedSampler(board_groups(_index_map(3)), shuffle=False)
        self.assertEqual(list(sampler), list(range(192)))

    def test_same_seed_gives_the_same_epoch_sequence(self) -> None:
        a = list(BoardGroupedSampler(board_groups(_index_map(20)), seed=7))
        b = list(BoardGroupedSampler(board_groups(_index_map(20)), seed=7))
        self.assertEqual(a, b)

    def test_consecutive_epochs_differ(self) -> None:
        sampler = BoardGroupedSampler(board_groups(_index_map(20)), seed=7)
        self.assertNotEqual(list(sampler), list(sampler))

    def test_set_epoch_makes_a_given_epoch_reproducible(self) -> None:
        first = BoardGroupedSampler(board_groups(_index_map(20)), seed=7)
        first.set_epoch(3)
        second = BoardGroupedSampler(board_groups(_index_map(20)), seed=7)
        second.set_epoch(3)
        self.assertEqual(list(first), list(second))


class ClassWeightTests(unittest.TestCase):
    def test_none_means_no_weighting(self) -> None:
        self.assertIsNone(class_weights_for([DatasetEntry("a.png", LEGAL)], "none"))

    def test_balanced_gives_rare_classes_more_weight_than_empty(self) -> None:
        weights = class_weights_for([DatasetEntry("a.png", LEGAL)], "balanced")
        assert weights is not None
        empty = weights[PIECE_CLASSES.index("empty")]
        king = weights[PIECE_CLASSES.index("K")]
        self.assertGreater(king, empty)

    def test_absent_class_gets_zero_not_infinity(self) -> None:
        weights = class_weights_for([DatasetEntry("a.png", LEGAL)], "balanced")
        assert weights is not None
        self.assertEqual(float(weights[PIECE_CLASSES.index("Q")]), 0.0)
        self.assertTrue(torch.isfinite(weights).all())

    def test_weights_track_the_observed_frequency(self) -> None:
        weights = class_weights_for([DatasetEntry("a.png", PAWNS)], "balanced")
        assert weights is not None
        # 8 peoes brancos contra 1 rei branco: o rei pesa 8x mais.
        ratio = float(weights[PIECE_CLASSES.index("K")] / weights[PIECE_CLASSES.index("P")])
        self.assertAlmostEqual(ratio, 8.0, places=4)

    def test_empty_entry_list_falls_back_to_no_weighting(self) -> None:
        self.assertIsNone(class_weights_for([], "balanced"))


class NumWorkersTests(unittest.TestCase):
    def test_none_resolves_to_half_the_cpus_capped_at_four(self) -> None:
        self.assertEqual(resolve_num_workers(None), min(4, (os.cpu_count() or 2) // 2))

    def test_explicit_zero_is_respected(self) -> None:
        """O padrao da biblioteca e 0 porque o Streamlit nao tem guarda de `__main__`."""
        self.assertEqual(resolve_num_workers(0), 0)

    def test_negative_is_clamped(self) -> None:
        self.assertEqual(resolve_num_workers(-3), 0)


class _CountingDataset(torch.utils.data.Dataset):
    """Casas cujo rotulo e conhecido, para conferir a acuracia exata por tabuleiro."""

    def __init__(self, labels: list[int]) -> None:
        self.labels = labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        return torch.zeros(1, 64, 64), self.labels[idx]


class _FixedModel(nn.Module):
    """Devolve os logits que lhe forem dados, na ordem em que as casas chegam."""

    def __init__(self, logits: torch.Tensor) -> None:
        super().__init__()
        self.logits = logits
        self.cursor = 0

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        chunk = self.logits[self.cursor : self.cursor + x.shape[0]]
        self.cursor += x.shape[0]
        return chunk


class EvaluateValidationTests(unittest.TestCase):
    def _run(self, labels: list[int], predictions: list[int]):
        logits = torch.zeros(len(labels), len(PIECE_CLASSES))
        logits[torch.arange(len(labels)), torch.tensor(predictions)] = 10.0
        loader = DataLoader(_CountingDataset(labels), batch_size=32, shuffle=False)
        return evaluate_validation(_FixedModel(logits), loader, "cpu", nn.CrossEntropyLoss())

    def test_perfect_prediction_scores_one_everywhere(self) -> None:
        labels = [0] * 128
        metrics = self._run(labels, labels)
        self.assertAlmostEqual(metrics.square_accuracy, 1.0)
        self.assertAlmostEqual(metrics.board_exact_accuracy, 1.0)

    def test_one_wrong_square_costs_the_whole_board(self) -> None:
        """A diferenca entre as duas metricas e o ponto inteiro da S-27."""
        labels = [0] * 128
        predictions = list(labels)
        predictions[5] = 1
        metrics = self._run(labels, predictions)

        self.assertAlmostEqual(metrics.square_accuracy, 127 / 128)
        self.assertAlmostEqual(metrics.board_exact_accuracy, 0.5)  # 1 de 2 tabuleiros

    def test_per_class_recall_is_nan_for_absent_classes(self) -> None:
        metrics = self._run([0] * 64, [0] * 64)
        self.assertAlmostEqual(metrics.per_class_recall["empty"], 1.0)
        self.assertNotEqual(metrics.per_class_recall["Q"], metrics.per_class_recall["Q"])  # NaN

    def test_a_validation_set_that_is_not_whole_boards_is_rejected(self) -> None:
        """Sintoma detectavel de alguem ter ligado shuffle no loader de validacao."""
        with self.assertRaises(ValueError) as caught:
            self._run([0] * 100, [0] * 100)
        self.assertIn("64", str(caught.exception))


class SeedTests(unittest.TestCase):
    def test_seeding_makes_the_augmentation_pipeline_reproducible(self) -> None:
        transform = build_train_transform()
        image = torch.rand(1, 64, 64)

        set_seed(123)
        first = transform(image)
        set_seed(123)
        second = transform(image)
        self.assertTrue(torch.equal(first, second))

    def test_different_seeds_produce_different_augmentation(self) -> None:
        transform = build_train_transform()
        image = torch.rand(1, 64, 64)

        set_seed(1)
        first = transform(image)
        set_seed(2)
        second = transform(image)
        self.assertFalse(torch.equal(first, second))

    def test_the_augmentation_pipeline_is_picklable(self) -> None:
        """Era uma lambda: com num_workers > 0 no Windows isso quebraria em `spawn`."""
        import pickle

        self.assertIsNotNone(pickle.loads(pickle.dumps(build_train_transform())))


class CacheSizeSplitTests(unittest.TestCase):
    def test_workers_divide_the_cache_budget(self) -> None:
        """O teto da S-26 e sobre o treino inteiro, e o cache e por processo."""
        with patch("chess_diagram_ocr.training.load_splits", return_value={}), \
             patch("chess_diagram_ocr.training.BoardFenDataset") as fake:
            fake.side_effect = ValueError("parar antes de treinar")
            from chess_diagram_ocr.training import train_model

            with self.assertRaises(ValueError):
                train_model(
                    csv_path=__file__,  # type: ignore[arg-type]
                    samples_dir=__file__,  # type: ignore[arg-type]
                    model_path=__file__,  # type: ignore[arg-type]
                    cache_size=256,
                    num_workers=3,
                )
            self.assertEqual(fake.call_args.kwargs["cache_size"], 64)


class SplitAssignmentTests(unittest.TestCase):
    """S-56: a amostra que você salva tem de chegar ao treino.

    O defeito: `splits.ensure_splits` existia e nada em produção a chamava. Amostra nova
    ficava sem split, `BoardFenDataset` a descartava, e o ciclo corrigir → salvar → treinar
    não fechava. Eram 45 amostras fora do treino, em silêncio, justamente as únicas com
    procedência preenchida.
    """

    def _dataset(self, root: Path, nomes: list[str], *, registrados: dict[str, str] | None = None) -> tuple[Path, Path, Path]:
        import cv2
        import numpy as np

        from chess_diagram_ocr.splits import save_splits

        samples = root / "samples"
        samples.mkdir(parents=True)
        rng = np.random.default_rng(0)
        linhas = ["filename,fen"]
        for nome in nomes:
            cv2.imwrite(str(samples / nome), rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))
            linhas.append(f"{nome},{LEGAL}")

        csv_path = root / "labels.csv"
        csv_path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        splits_path = root / "splits.csv"
        if registrados is not None:
            save_splits(splits_path, registrados)  # type: ignore[arg-type]
        return csv_path, samples, splits_path

    def test_amostra_nova_recebe_split_e_passa_a_ser_vista_pelo_treino(self) -> None:
        import tempfile

        from chess_diagram_ocr.dataset import BoardFenDataset
        from chess_diagram_ocr.training import resolve_splits

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path, samples, splits_path = self._dataset(
                root, ["velha.png", "nova.png"], registrados={"velha.png": "train"}
            )

            antes = BoardFenDataset(csv_path, samples, cache_size=0, splits={"velha.png": "train"}, split="train")
            self.assertEqual(len(antes.entries), 1)
            self.assertEqual(antes.skipped_without_split, ["nova.png"], "o descarte precisa ser registrado")

            mapa = resolve_splits(csv_path, samples, splits_path)
            self.assertIn("nova.png", mapa)

            visiveis = sum(
                len(BoardFenDataset(csv_path, samples, cache_size=0, splits=mapa, split=s).entries)
                for s in ("train", "val", "test")
            )
            self.assertEqual(visiveis, 2, "a amostra nova continua invisível a todos os splits")

    def test_o_split_de_uma_amostra_ja_registrada_nunca_muda(self) -> None:
        """A garantia da S-07: atribuir split a uma nova não pode mover as antigas."""
        import tempfile

        from chess_diagram_ocr.splits import load_splits
        from chess_diagram_ocr.training import resolve_splits

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registrados = {"a.png": "test", "b.png": "val", "c.png": "train"}
            csv_path, samples, splits_path = self._dataset(
                root, [*registrados, "nova.png"], registrados=registrados
            )

            mapa = resolve_splits(csv_path, samples, splits_path)

            for nome, split in registrados.items():
                self.assertEqual(mapa[nome], split)
            gravado = load_splits(splits_path)
            self.assertEqual({n: gravado[n] for n in registrados}, registrados)

    def test_assign_new_false_le_e_nao_escreve(self) -> None:
        import tempfile

        from chess_diagram_ocr.training import resolve_splits

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path, samples, splits_path = self._dataset(
                root, ["velha.png", "nova.png"], registrados={"velha.png": "train"}
            )
            antes = splits_path.read_bytes()

            mapa = resolve_splits(csv_path, samples, splits_path, assign_new=False)

            self.assertNotIn("nova.png", mapa)
            self.assertEqual(splits_path.read_bytes(), antes)

    def test_amostra_identica_a_uma_ja_registrada_herda_o_split_dela(self) -> None:
        """Membros de um mesmo diagrama não podem cair em splits diferentes (S-07).

        A imagem é copiada byte a byte com o mesmo rótulo, que é o caso 1 dos grupos de
        duplicata: a mesma amostra salva duas vezes.
        """
        import shutil
        import tempfile

        from chess_diagram_ocr.training import resolve_splits

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path, samples, splits_path = self._dataset(root, ["original.png"], registrados={"original.png": "test"})
            shutil.copy(samples / "original.png", samples / "zcopia.png")
            with csv_path.open("a", encoding="utf-8") as arquivo:
                arquivo.write(f"zcopia.png,{LEGAL}\n")

            mapa = resolve_splits(csv_path, samples, splits_path)

            self.assertEqual(mapa["zcopia.png"], "test", "a cópia caiu em outro split que a original")

    def test_a_deduplicacao_so_le_as_imagens_que_importam(self) -> None:
        """`duplicate_groups_touching` existe pelo custo: o completo lê ~6 GB a cada treino."""
        import tempfile

        import cv2
        import numpy as np

        from chess_diagram_ocr.atomic_io import read_image
        from chess_diagram_ocr.audit import duplicate_groups_touching

        OUTRO = "8/8/8/8/8/8/8/K1k5"
        with tempfile.TemporaryDirectory() as tmp:
            samples = Path(tmp)
            rng = np.random.default_rng(1)
            for nome in ("a.png", "b.png", "nova.png"):
                cv2.imwrite(str(samples / nome), rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))

            lidas: list[str] = []

            def _espiao(caminho: Path | str, *args: object, **kwargs: object):
                lidas.append(Path(caminho).name)
                return read_image(caminho, *args, **kwargs)

            labels = [("a.png", OUTRO), ("b.png", OUTRO), ("nova.png", LEGAL)]
            with patch("chess_diagram_ocr.audit.read_image", side_effect=_espiao):
                duplicate_groups_touching(samples, labels, ["nova.png"])

            self.assertEqual(lidas, ["nova.png"], f"leu imagens de rótulo que nenhuma amostra nova tem: {lidas}")

    def test_o_treino_atribui_split_em_vez_de_so_ler(self) -> None:
        """Regressão do defeito exato: `train_model` chamava `load_splits`, que só lê.

        A varredura é sobre o texto do módulo em vez de sobre o comportamento porque o
        defeito era **a chamada errada**, não um resultado errado: `load_splits` funciona
        perfeitamente, ela só não faz o que este caminho precisa. Um teste de comportamento
        passaria a verde de novo se alguém trocasse de volta e o dataset de teste já tivesse
        todos os splits registrados -- que é a situação de qualquer fixture.

        A S-47 moveu a montagem do dataset de `train_model` para `Trainer.prepare`, e a
        varredura foi junto. `train_model` é hoje uma função fina sobre `Trainer.fit()`;
        quem resolve o split é `prepare`, e é o corpo dela que precisa continuar chamando
        `resolve_splits`.
        """
        import chess_diagram_ocr.training as training

        fonte = Path(training.__file__).read_text(encoding="utf-8")
        corpo = fonte.split("    def prepare(self) -> None:", 1)[1].split("    def resume(", 1)[0]
        self.assertIn("resolve_splits(", corpo)
        self.assertNotIn(
            "load_splits(",
            corpo,
            "`Trainer.prepare` voltou a só ler o arquivo de splits; amostra nova fica fora do treino (S-56).",
        )


def _tiny_dataset(root: Path, boards: int = 6) -> tuple[Path, Path, Path]:
    """Dataset sintético mínimo: `boards` tabuleiros, os dois últimos em `val`.

    Módulo, e não método, porque a S-47 trouxe um segundo grupo de testes que precisa dele
    -- o que exercita `Trainer` etapa a etapa.
    """
    import cv2
    import numpy as np

    from chess_diagram_ocr.splits import save_splits

    samples = root / "samples"
    samples.mkdir()
    linhas = ["filename,fen"]
    splits = {}
    rng = np.random.default_rng(0)
    for index in range(boards):
        name = f"b{index}.png"
        cv2.imwrite(str(samples / name), rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))
        linhas.append(f"{name},{LEGAL}")
        splits[name] = "train" if index < boards - 2 else "val"

    csv_path = root / "labels.csv"
    csv_path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    splits_path = root / "splits.csv"
    save_splits(splits_path, splits)  # type: ignore[arg-type]
    return csv_path, samples, splits_path


class ReproducibilityTests(unittest.TestCase):
    """O criterio de aceite da S-27: mesma semente e mesmo dataset -> metricas identicas.

    Dataset sintetico minusculo de proposito. O que se testa aqui e determinismo do
    caminho de treino -- semente, ordem do amostrador, aumento de dados, inicializacao --,
    e isso nao precisa de 2.569 tabuleiros para falhar quando esta quebrado.
    """

    _tiny_dataset = staticmethod(_tiny_dataset)

    def _train(self, root: Path, name: str, seed: int = 7):
        from chess_diagram_ocr.training import train_model

        csv_path, samples, splits_path = self._tiny_dataset(root / name)
        return train_model(
            csv_path=csv_path,
            samples_dir=samples,
            model_path=root / name / "m.pt",
            epochs=2,
            batch_size=64,
            splits_path=splits_path,
            fresh=True,
            seed=seed,
            num_workers=0,
            patience=0,
        )

    def test_cancelar_antes_da_primeira_epoca_nao_toca_no_checkpoint(self) -> None:
        """S-60: até aqui o treino não tinha cancelamento, e parar exigia fechar a janela.

        Fechar a janela matava a thread daemon a qualquer instante -- inclusive no meio do
        `torch.save`, que era a outra metade do defeito da S-57.
        """
        import tempfile
        import threading

        from chess_diagram_ocr.training import train_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cancelado").mkdir()
            csv_path, samples, splits_path = self._tiny_dataset(root / "cancelado")
            model_path = root / "cancelado" / "m.pt"

            cancel = threading.Event()
            cancel.set()
            run = train_model(
                csv_path=csv_path,
                samples_dir=samples,
                model_path=model_path,
                epochs=5,
                batch_size=64,
                splits_path=splits_path,
                fresh=True,
                num_workers=0,
                patience=0,
                cancel_event=cancel,
            )

            self.assertTrue(run.cancelled)
            self.assertEqual(run.history, [])
            self.assertFalse(model_path.exists(), "um treino cancelado antes da 1ª época gravou checkpoint")

    def test_cancelar_no_meio_preserva_o_melhor_checkpoint_ja_gravado(self) -> None:
        import tempfile
        import threading

        from chess_diagram_ocr.checkpoint import load_checkpoint
        from chess_diagram_ocr.training import train_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meio").mkdir()
            csv_path, samples, splits_path = self._tiny_dataset(root / "meio")
            model_path = root / "meio" / "m.pt"

            cancel = threading.Event()

            def _pede_parada_apos_a_primeira(_row: dict) -> None:
                cancel.set()

            run = train_model(
                csv_path=csv_path,
                samples_dir=samples,
                model_path=model_path,
                epochs=5,
                batch_size=64,
                splits_path=splits_path,
                fresh=True,
                num_workers=0,
                patience=0,
                cancel_event=cancel,
                progress_cb=_pede_parada_apos_a_primeira,
            )

            self.assertTrue(run.cancelled)
            self.assertEqual(len(run.history), 1, "a época em curso tem de terminar, não ser abortada no meio")
            self.assertTrue(model_path.exists())
            # O checkpoint continua carregável: cancelar não pode deixar `.pt` pela metade.
            self.assertEqual(load_checkpoint(model_path).metadata["best_epoch"], run.best_epoch)

    def test_um_treino_normal_nao_se_diz_cancelado(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "normal").mkdir()
            run = self._train(Path(tmp), "normal")
            self.assertFalse(run.cancelled)

    def test_two_runs_with_the_same_seed_agree_to_the_last_digit(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            (root / "b").mkdir()
            first = self._train(root, "a")
            second = self._train(root, "b")

            self.assertEqual(len(first.history), len(second.history))
            for a, b in zip(first.history, second.history, strict=True):
                for key in ("train_loss", "train_square_acc", "val_loss", "val_board_exact_acc"):
                    with self.subTest(epoch=a["epoch"], metric=key):
                        self.assertEqual(a[key], b[key])
            self.assertEqual(first.temperature, second.temperature)

    def test_a_different_seed_changes_the_run(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            (root / "b").mkdir()
            first = self._train(root, "a", seed=1)
            second = self._train(root, "b", seed=2)
            self.assertNotEqual(first.history[0]["train_loss"], second.history[0]["train_loss"])

    def test_checkpoint_records_what_is_needed_to_reproduce_it(self) -> None:
        import tempfile

        from chess_diagram_ocr.checkpoint import load_checkpoint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            run = self._train(root, "a")

            checkpoint = load_checkpoint(root / "a" / "m.pt")
            self.assertFalse(checkpoint.is_legacy)
            self.assertEqual(checkpoint.metadata["seed"], 7)
            self.assertEqual(checkpoint.arch_version, "cnn-gray-64-linear")
            self.assertTrue(checkpoint.metadata["split_hash"])
            self.assertEqual(checkpoint.metadata["dataset_size"], 4)
            self.assertEqual(checkpoint.metadata["best_epoch"], run.best_epoch)

    def test_resume_keeps_the_best_metric_instead_of_restarting_it(self) -> None:
        """A pendencia aberta desde a Fase 1: retomar sobrescrevia o melhor checkpoint.

        `best_val_loss` recomecava em infinito e a primeira epoca da retomada gravava por
        cima mesmo sendo pior -- foi o que aconteceu ao treinar o baseline.
        """
        import tempfile

        from chess_diagram_ocr.checkpoint import load_checkpoint
        from chess_diagram_ocr.training import train_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            self._train(root, "a")

            csv_path, samples, splits_path = (root / "a" / "labels.csv", root / "a" / "samples", root / "a" / "splits.csv")
            antes = load_checkpoint(root / "a" / "m.pt").best_metric
            retomado = train_model(
                csv_path=csv_path,
                samples_dir=samples,
                model_path=root / "a" / "m.pt",
                epochs=1,
                batch_size=64,
                splits_path=splits_path,
                fresh=False,
                seed=7,
                num_workers=0,
                patience=0,
            )
            self.assertGreaterEqual(retomado.best_metric, antes or 0.0)

    def test_a_legacy_checkpoint_can_be_resumed(self) -> None:
        """Regressao do relato do usuario: a UI ficou sem como treinar.

        Recusar checkpoint sem metadados bloqueava quem tinha `piece_classifier.pt`
        gravado antes da Fase 5 -- ou seja, todo mundo que ja usava o projeto.
        """
        import tempfile

        import torch as _torch

        from chess_diagram_ocr.model import PieceClassifier
        from chess_diagram_ocr.training import train_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            csv_path, samples, splits_path = self._tiny_dataset(root / "a")

            legacy = root / "a" / "m.pt"
            _torch.save({"model_state": PieceClassifier().state_dict()}, legacy)

            run = train_model(
                csv_path=csv_path,
                samples_dir=samples,
                model_path=legacy,
                epochs=1,
                batch_size=64,
                splits_path=splits_path,
                fresh=False,
                num_workers=0,
                patience=0,
            )
            self.assertEqual(len(run.history), 1)

    def test_resuming_a_legacy_checkpoint_measures_it_before_overwriting(self) -> None:
        """A pendencia da Fase 1, agora fechada tambem para checkpoint sem metadados.

        Um checkpoint antigo nao diz que metrica atingiu. Supor 0 faz a primeira epoca
        gravar por cima mesmo sendo pior -- que e exatamente o que quase perdeu o
        baseline. A resposta e medir o modelo carregado na validacao atual.
        """
        import tempfile
        from unittest.mock import patch as _patch

        import torch as _torch

        from chess_diagram_ocr.model import PieceClassifier
        from chess_diagram_ocr.training import train_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            csv_path, samples, splits_path = self._tiny_dataset(root / "a")
            legacy = root / "a" / "m.pt"
            _torch.save({"model_state": PieceClassifier().state_dict()}, legacy)

            real = __import__("chess_diagram_ocr.training", fromlist=["evaluate_validation"]).evaluate_validation
            chamadas = []

            def spy(*args, **kwargs):
                resultado = real(*args, **kwargs)
                chamadas.append(resultado.board_exact_accuracy)
                return resultado

            with _patch("chess_diagram_ocr.training.evaluate_validation", side_effect=spy):
                train_model(
                    csv_path=csv_path,
                    samples_dir=samples,
                    model_path=legacy,
                    epochs=1,
                    batch_size=64,
                    splits_path=splits_path,
                    fresh=False,
                    num_workers=0,
                    patience=0,
                )

            # Uma medicao do incumbente antes da epoca 1, mais a da propria epoca 1.
            self.assertEqual(len(chamadas), 2)

    def test_resuming_a_different_architecture_fails_loudly(self) -> None:
        import tempfile

        from chess_diagram_ocr.model import ArchConfig
        from chess_diagram_ocr.training import train_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            self._train(root, "a")

            with self.assertRaises(ValueError) as caught:
                train_model(
                    csv_path=root / "a" / "labels.csv",
                    samples_dir=root / "a" / "samples",
                    model_path=root / "a" / "m.pt",
                    epochs=1,
                    splits_path=root / "a" / "splits.csv",
                    fresh=False,
                    arch=ArchConfig(image_size=32),
                    num_workers=0,
                )
            self.assertIn("cnn-gray-32-linear", str(caught.exception))


class BestEpochPolicyTests(unittest.TestCase):
    """A consequência concreta da S-47: a política de melhor época sem dataset e sem GPU.

    Cada teste aqui cobre uma decisão que antes só podia ser exercitada rodando um treino
    inteiro -- e o primeiro deles é o defeito histórico que sobreviveu duas fases porque
    ninguém conseguia perguntar à política sem treinar.
    """

    def test_retomar_nao_deixa_uma_epoca_pior_gravar_por_cima(self) -> None:
        """O defeito da Fase 1, agora em três linhas.

        Retomar zerava o controle em infinito e a primeira época gravava por cima mesmo
        sendo pior. O incumbente do checkpoint é o que impede isso.
        """
        from chess_diagram_ocr.training import BestEpochPolicy

        policy = BestEpochPolicy("val_board_exact_acc", 0.9906, best_epoch=12)
        self.assertFalse(policy.accepts(0.9800))
        self.assertFalse(policy.observe(0.9800, epoch=1))
        self.assertEqual(policy.best_epoch, 12, "a melhor época retomada foi perdida")
        self.assertEqual(policy.best_metric, 0.9906)

    def test_treino_do_zero_grava_na_primeira_epoca_sem_clausula_especial(self) -> None:
        from chess_diagram_ocr.training import BestEpochPolicy

        policy = BestEpochPolicy("val_board_exact_acc", float("-inf"))
        self.assertTrue(policy.observe(0.0, epoch=1), "com incumbente -inf, qualquer métrica grava")
        self.assertEqual(policy.best_epoch, 1)

    def test_empatar_nao_regrava(self) -> None:
        """Regravar sem ganho é reescrever 8,7 MB e correr o risco da S-57 de graça."""
        from chess_diagram_ocr.training import BestEpochPolicy

        policy = BestEpochPolicy("val_board_exact_acc", 0.5)
        self.assertFalse(policy.accepts(0.5))
        self.assertTrue(policy.accepts(0.5 + 1e-12))

    def test_parada_antecipada_conta_epocas_sem_melhora(self) -> None:
        from chess_diagram_ocr.training import BestEpochPolicy

        policy = BestEpochPolicy("val_board_exact_acc", 0.5, patience=2)
        policy.observe(0.4, epoch=1)
        self.assertFalse(policy.should_stop())
        policy.observe(0.3, epoch=2)
        self.assertTrue(policy.should_stop())

        policy.observe(0.9, epoch=3)
        self.assertFalse(policy.should_stop(), "uma época melhor tem de zerar o contador")

    def test_paciencia_zero_desliga_a_parada_antecipada(self) -> None:
        from chess_diagram_ocr.training import BestEpochPolicy

        policy = BestEpochPolicy("val_board_exact_acc", 0.5, patience=0)
        for epoch in range(1, 50):
            policy.observe(0.1, epoch=epoch)
        self.assertFalse(policy.should_stop())

    def test_menos_infinito_nao_vai_para_os_metadados(self) -> None:
        """`epochs=0` ou cancelamento antes da 1ª época: gravar `-inf` seria um número falso."""
        from chess_diagram_ocr.training import BestEpochPolicy

        self.assertEqual(BestEpochPolicy("m", float("-inf")).settled_metric, 0.0)
        self.assertEqual(BestEpochPolicy("m", 0.42).settled_metric, 0.42)


class TrainingPlanTests(unittest.TestCase):
    """Os 18 parâmetros passam a ser conferidos uma vez, na construção do plano."""

    def test_val_ratio_fora_da_faixa_e_recusado_na_construcao(self) -> None:
        from chess_diagram_ocr.training import DataPlan

        for ruim in (0.0, 1.0, -0.1, 1.5):
            with self.subTest(val_ratio=ruim), self.assertRaises(ValueError):
                DataPlan(csv_path=Path("a.csv"), samples_dir=Path("s"), val_ratio=ruim)

    def test_hiperparametros_impossiveis_sao_recusados(self) -> None:
        from chess_diagram_ocr.training import OptimPlan

        with self.assertRaises(ValueError):
            OptimPlan(batch_size=0)
        with self.assertRaises(ValueError):
            OptimPlan(lr=0.0)
        with self.assertRaises(ValueError):
            OptimPlan(epochs=-1)

    def test_o_plano_e_imutavel(self) -> None:
        """Um plano que muda no meio do treino faria os metadados descreverem outro treino."""
        import dataclasses

        from chess_diagram_ocr.training import OptimPlan

        with self.assertRaises(dataclasses.FrozenInstanceError):
            OptimPlan().epochs = 99  # type: ignore[misc]


class TrainerStageTests(unittest.TestCase):
    """`prepare → resume → run_epoch → finish` chamáveis uma a uma, e fiéis ao `fit()`."""

    def _plan(self, root: Path, name: str, *, epochs: int = 2, seed: int = 7):
        from chess_diagram_ocr.training import DataPlan, OptimPlan, OutputPlan, TrainingPlan

        (root / name).mkdir()
        csv_path, samples, splits_path = _tiny_dataset(root / name)
        return TrainingPlan(
            data=DataPlan(csv_path=csv_path, samples_dir=samples, splits_path=splits_path, num_workers=0),
            output=OutputPlan(model_path=root / name / "m.pt", fresh=True),
            optim=OptimPlan(epochs=epochs, batch_size=64, patience=0, seed=seed),
        )

    def test_rodar_as_etapas_a_mao_da_o_mesmo_que_fit(self) -> None:
        """O critério de aceite da S-47: a decomposição não pode mudar resultado.

        Duas execuções com a mesma semente, uma por `fit()` e outra chamando as etapas na
        mão, têm de concordar até o último dígito.
        """
        import tempfile

        from chess_diagram_ocr.training import Trainer

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            de_uma_vez = Trainer(self._plan(root, "fit")).fit()

            passo_a_passo = Trainer(self._plan(root, "passos"))
            passo_a_passo.prepare()
            passo_a_passo.resume()
            passo_a_passo.run_epoch(1)
            passo_a_passo.run_epoch(2)
            manual = passo_a_passo.finish()

            self.assertEqual(len(de_uma_vez.history), len(manual.history))
            for a, b in zip(de_uma_vez.history, manual.history, strict=True):
                for key in ("train_loss", "train_square_acc", "val_loss", "val_board_exact_acc", "is_best"):
                    with self.subTest(epoch=a["epoch"], metric=key):
                        self.assertEqual(a[key], b[key])
            self.assertEqual(de_uma_vez.temperature, manual.temperature)
            self.assertEqual(de_uma_vez.best_epoch, manual.best_epoch)

    def test_run_epoch_antes_de_prepare_diz_o_que_falta(self) -> None:
        import tempfile

        from chess_diagram_ocr.training import Trainer

        with tempfile.TemporaryDirectory() as tmp:
            trainer = Trainer(self._plan(Path(tmp), "cru"))
            with self.assertRaises(RuntimeError) as caught:
                trainer.run_epoch(1)
            self.assertIn("prepare()", str(caught.exception))

    def test_resume_devolve_o_checkpoint_em_vez_de_o_esconder(self) -> None:
        """"De onde vieram estes pesos" é a pergunta que toda retomada levanta."""
        import tempfile

        from chess_diagram_ocr.training import Trainer

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plano = self._plan(root, "a", epochs=1)
            Trainer(plano).fit()

            import dataclasses

            retomada = dataclasses.replace(plano, output=dataclasses.replace(plano.output, fresh=False))
            trainer = Trainer(retomada)
            trainer.prepare()
            checkpoint = trainer.resume()

            self.assertIsNotNone(checkpoint)
            assert checkpoint is not None
            self.assertEqual(checkpoint.arch_version, "cnn-gray-64-linear")
            self.assertEqual(trainer.policy.best_metric, checkpoint.best_metric)

    def test_validate_sem_conjunto_de_validacao_diz_por_que(self) -> None:
        import tempfile

        from chess_diagram_ocr.training import Trainer

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plano = self._plan(root, "sem_val")
            trainer = Trainer(plano)
            trainer.prepare()
            trainer.val_loader = None
            with self.assertRaises(ValueError):
                trainer.validate()


class ChunkCoverageTests(unittest.TestCase):
    def test_every_board_appears_the_expected_number_of_times(self) -> None:
        sampler = BoardGroupedSampler(board_groups(_index_map(50)), seed=3, boards_per_chunk=16)
        counts = Counter(index // 64 for index in sampler)
        self.assertEqual(set(counts.values()), {64})
        self.assertEqual(len(counts), 50)


if __name__ == "__main__":
    unittest.main()


class EmpateEntreEpocasTests(unittest.TestCase):
    """`--keep-ties` grava a época empatada ao lado, para que a decisão tenha número (S-104).

    A métrica que decide tem granularidade de **um tabuleiro** -- 1/306 = 0,00327 no `val` da
    Fase 5 --, então empate é comum: em `docs/metrics/phase5_training.json` o máximo é atingido
    por duas épocas em **3 de 3** execuções, e em **2 delas** a época gravada tem `val_loss`
    maior que a da outra empatada.

    O `>` estrito do `accepts` **não** é defeito: é decisão escrita, e a razão dela está no
    docstring -- regravar sem ganho é reescrever 8,7 MB e correr o risco da S-57 de graça. O
    que faltava era medir se a de menor `val_loss` exporta mais em página real, e é isso que
    esta flag permite. Ela existe para o experimento, não para o uso normal.
    """

    def _plan(self, root: Path, name: str, *, keep_ties: bool, epochs: int = 2):
        from chess_diagram_ocr.training import DataPlan, OptimPlan, OutputPlan, TrainingPlan

        (root / name).mkdir()
        csv_path, samples, splits_path = _tiny_dataset(root / name)
        return TrainingPlan(
            data=DataPlan(csv_path=csv_path, samples_dir=samples, splits_path=splits_path, num_workers=0),
            output=OutputPlan(model_path=root / name / "m.pt", fresh=True, keep_ties=keep_ties, calibrate=False),
            optim=OptimPlan(epochs=epochs, batch_size=64, patience=0, seed=7),
        )

    def _empata_a_proxima(self, trainer) -> None:  # noqa: ANN001
        """Força a próxima época a empatar com a melhor, sem depender do acaso do dataset.

        Devolver a **mesma** `board_exact_accuracy` da melhor é o que define empate para a
        política; o `loss` vai menor de propósito, porque é justamente esse o caso que o item
        quer medir -- a época empatada que tem `val_loss` melhor e não é gravada.
        """
        from chess_diagram_ocr.training import ValidationMetrics

        igual = trainer.policy.best_metric
        trainer.validate = lambda: ValidationMetrics(  # type: ignore[method-assign]
            loss=0.0001,
            square_accuracy=1.0,
            board_exact_accuracy=igual,
            per_class_recall={},
            logits=torch.zeros(1, 13),
            targets=torch.zeros(1, dtype=torch.long),
        )

    def _treina_com_empate(self, root: Path, name: str, *, keep_ties: bool):
        from chess_diagram_ocr.training import Trainer

        trainer = Trainer(self._plan(root, name, keep_ties=keep_ties))
        trainer.prepare()
        trainer.resume()
        trainer.run_epoch(1)
        self._empata_a_proxima(trainer)
        linha = trainer.run_epoch(2)
        return trainer, linha

    def test_a_epoca_empatada_e_gravada_ao_lado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            trainer, linha = self._treina_com_empate(raiz, "com", keep_ties=True)

            self.assertFalse(linha["is_best"], "empatar continua não regravando o principal")
            self.assertEqual(trainer.run.best_epoch, 1, "o checkpoint principal é o da política")
            self.assertTrue((raiz / "com" / "m.tie-e2.pt").exists())
            self.assertTrue((raiz / "com" / "m.pt").exists(), "e o principal continua lá")

    def test_sem_a_flag_o_empate_nao_deixa_arquivo(self) -> None:
        """O padrão é o comportamento de sempre: a flag existe para um experimento."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self._treina_com_empate(raiz, "sem", keep_ties=False)

            self.assertEqual(list((raiz / "sem").glob("*.tie-*.pt")), [])

    def test_o_arquivo_do_empate_diz_com_quem_empatou(self) -> None:
        """Um `.tie-*.pt` copiado para outro nome seria indistinguível de um checkpoint que a
        política escolheu -- e o experimento inteiro depende de saber qual é qual."""
        from chess_diagram_ocr.checkpoint import load_checkpoint

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self._treina_com_empate(raiz, "marca", keep_ties=True)

            metadados = load_checkpoint(raiz / "marca" / "m.tie-e2.pt").metadata
            self.assertEqual(metadados["tie_with_best_epoch"], 1)
            self.assertEqual(metadados["best_epoch"], 2)
            self.assertEqual(metadados["metrics"]["val_loss"], 0.0001, "a loss menor, que é o ponto")

    def test_perder_nao_conta_como_empate(self) -> None:
        """A guarda que separa "empatou" de "piorou": só a igualdade exata grava ao lado."""
        from chess_diagram_ocr.training import Trainer, ValidationMetrics

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            trainer = Trainer(self._plan(raiz, "pior", keep_ties=True))
            trainer.prepare()
            trainer.resume()
            trainer.run_epoch(1)
            pior = trainer.policy.best_metric - 0.5
            trainer.validate = lambda: ValidationMetrics(  # type: ignore[method-assign]
                loss=0.0001,
                square_accuracy=0.5,
                board_exact_accuracy=pior,
                per_class_recall={},
                logits=torch.zeros(1, 13),
                targets=torch.zeros(1, dtype=torch.long),
            )
            trainer.run_epoch(2)

            self.assertEqual(list((raiz / "pior").glob("*.tie-*.pt")), [])


class MetadadosQueReproduzemTests(unittest.TestCase):
    """O checkpoint guarda o que reproduz o número (S-105).

    Os metadados traziam `arch_version`, `seed`, `class_weights`, `augment_version`,
    `split_hash`, `dataset_size`, `git_commit`, `best_metric` e a calibração. **Ausentes:**
    taxa de aprendizado, tamanho de lote, número de épocas pedido, otimizador, e qualquer
    identidade do **conteúdo** dos rótulos.

    `cvoff-train --lr 1e-4` e `cvoff-train --lr 1e-3` produziam dois arquivos indistinguíveis,
    e há 17 checkpoints em `models/` e nove treinos comparados no `EXPERIMENTS_FASE7.md`.

    A S-107 encontrou a consequência: a única forma de saber que o candidato histórico
    `s40_mhsp_16ep.pt` rodou **8** épocas e não 16 foi ler `metadata["metrics"]
    ["total_epochs"]`, que existe por acaso. O nome do arquivo dizia outra coisa.
    """

    def _entradas(self, pares: list[tuple[str, str]]) -> list[LabelEntry]:
        return [LabelEntry(filename=nome, fen=fen) for nome, fen in pares]

    def test_a_ordem_das_linhas_nao_muda_o_hash(self) -> None:
        """A pergunta é "estes rótulos são os mesmos?", e a ordem no arquivo não é parte da
        resposta -- ela muda a cada reescrita do `LabelStore`."""
        pares = [("a.png", "4k3/8/8/8/8/8/8/4K3"), ("b.png", "8/8/8/8/8/8/8/4K2k")]
        self.assertEqual(
            labels_hash(self._entradas(pares)),
            labels_hash(self._entradas(list(reversed(pares)))),
        )

    def test_corrigir_uma_fen_muda_o_hash(self) -> None:
        """**O caso que o `split_hash` não vê.** Corrigir um rótulo não muda a partição."""
        antes = self._entradas([("a.png", "4k3/8/8/8/8/8/8/4K3")])
        depois = self._entradas([("a.png", "4k3/8/8/8/8/8/4P3/4K3")])
        self.assertNotEqual(labels_hash(antes), labels_hash(depois))

    def test_amostra_nova_muda_o_hash(self) -> None:
        """As 468 amostras de correção humana da S-107 entraram sem que o `split_hash` mudasse."""
        antes = self._entradas([("a.png", "4k3/8/8/8/8/8/8/4K3")])
        depois = self._entradas([("a.png", "4k3/8/8/8/8/8/8/4K3"), ("b.png", "8/8/8/8/8/8/8/4K2k")])
        self.assertNotEqual(labels_hash(antes), labels_hash(depois))

    def test_conjunto_vazio_tem_hash_e_nao_erro(self) -> None:
        self.assertTrue(labels_hash([]))

    def test_dois_treinos_que_diferem_so_no_lr_sao_distinguiveis(self) -> None:
        """**O critério de aceite.** Dois arquivos indistinguíveis pelos metadados são dois
        arquivos que ninguém consegue comparar depois."""
        from chess_diagram_ocr.checkpoint import load_checkpoint
        from chess_diagram_ocr.training import Trainer

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            caminhos = []
            for nome, lr in (("baixo", 1e-4), ("alto", 1e-3)):
                plano = self._plano(raiz, nome, lr=lr)
                Trainer(plano).fit()
                caminhos.append(load_checkpoint(plano.output.model_path).metadata)

            self.assertNotEqual(caminhos[0]["lr"], caminhos[1]["lr"])
            self.assertEqual(caminhos[0]["lr"], 1e-4)

    def test_o_checkpoint_declara_lote_epocas_e_otimizador(self) -> None:
        from chess_diagram_ocr.checkpoint import load_checkpoint
        from chess_diagram_ocr.training import Trainer

        with tempfile.TemporaryDirectory() as tmp:
            plano = self._plano(Path(tmp), "meta", lr=1e-3)
            Trainer(plano).fit()
            metadados = load_checkpoint(plano.output.model_path).metadata

            self.assertEqual(metadados["batch_size"], 64)
            self.assertEqual(metadados["epochs_requested"], 2, "o pedido, e não o que rodou")
            self.assertEqual(metadados["patience"], 0)
            self.assertEqual(metadados["optimizer"], "adam")
            self.assertTrue(metadados["labels_hash"])

    def test_o_labels_hash_do_checkpoint_e_o_do_split_de_treino(self) -> None:
        """Só o `train`: `val` e `test` mudarem não altera o que o modelo aprendeu, e incluí-los
        faria o hash mudar por motivo que não é sobre este checkpoint."""
        from chess_diagram_ocr.checkpoint import load_checkpoint
        from chess_diagram_ocr.training import Trainer

        with tempfile.TemporaryDirectory() as tmp:
            plano = self._plano(Path(tmp), "treino", lr=1e-3)
            trainer = Trainer(plano)
            trainer.fit()

            gravado = load_checkpoint(plano.output.model_path).metadata["labels_hash"]
            self.assertEqual(gravado, trainer.metadata_base["labels_hash"])

    def _plano(self, root: Path, name: str, *, lr: float):
        from chess_diagram_ocr.training import DataPlan, OptimPlan, OutputPlan, TrainingPlan

        (root / name).mkdir()
        csv_path, samples, splits_path = _tiny_dataset(root / name)
        return TrainingPlan(
            data=DataPlan(csv_path=csv_path, samples_dir=samples, splits_path=splits_path, num_workers=0),
            output=OutputPlan(model_path=root / name / "m.pt", fresh=True, calibrate=False),
            optim=OptimPlan(epochs=2, batch_size=64, patience=0, seed=7, lr=lr),
        )


class IncumbenteDaRetomadaTests(unittest.TestCase):
    """O número que a primeira época da retomada precisa superar (S-370, S-371).

    A pergunta é sempre a mesma -- *o valor gravado no checkpoint é comparável com o que este
    treino vai medir?* --, e havia duas formas de responder "sim" errado: comparar métricas
    de nomes diferentes, e chamar de "mesmo split" dois vazios.
    """

    def _checkpoint(self, **metadados: object):
        from chess_diagram_ocr.checkpoint import Checkpoint

        base = {
            "best_metric": 0.99,
            "best_epoch": 7,
            "best_metric_name": "val_board_exact_acc",
            "split_hash": "1a2b3c4d",
        }
        return Checkpoint(state={}, path=Path("m.pt"), metadata={**base, **metadados})

    def _resolver(self, checkpoint, **kwargs):  # noqa: ANN001
        from chess_diagram_ocr.training import _resolve_best_metric

        argumentos = {
            "model": nn.Identity(),
            "val_loader": None,
            "device": "cpu",
            "criterion": nn.Identity(),
            "split_hash": "1a2b3c4d",
            "metric_name": "val_board_exact_acc",
        }
        argumentos.update(kwargs)
        return _resolve_best_metric(checkpoint, **argumentos)  # type: ignore[arg-type]

    def test_mesmo_split_e_mesma_metrica_reaproveitam_o_numero(self) -> None:
        """O caso que a S-27 abriu, e que continua valendo: nada aqui o estreita."""
        self.assertEqual(self._resolver(self._checkpoint()), (0.99, 7))

    def test_metrica_de_outro_nome_nao_serve_de_incumbente(self) -> None:
        """`-train_loss` contra acurácia por tabuleiro não é comparação, é acidente (S-370)."""
        with self.assertLogs("chess_diagram_ocr.training", level="WARNING") as registro:
            resultado = self._resolver(self._checkpoint(best_metric_name="train_loss", best_metric=-0.42))
        self.assertEqual(resultado, (float("-inf"), 0))
        self.assertIn("train_loss", "\n".join(registro.output))

    def test_split_vazio_dos_dois_lados_nao_e_o_mesmo_split(self) -> None:
        """Sem arquivo de splits, `""` == `""` dizia "mesma partição" sobre dois sorteios (S-371)."""
        with self.assertLogs("chess_diagram_ocr.training", level="WARNING") as registro:
            resultado = self._resolver(self._checkpoint(split_hash=""), split_hash="")
        self.assertEqual(resultado, (float("-inf"), 0))
        self.assertIn("outro split", "\n".join(registro.output))

    def test_checkpoint_sem_nome_de_metrica_tambem_nao_serve(self) -> None:
        """Um `.pt` anterior à S-105 grava `best_metric` e não diz de quê."""
        resultado = self._resolver(self._checkpoint(best_metric_name=None))
        self.assertEqual(resultado, (float("-inf"), 0))

    def test_o_motivo_diz_as_duas_causas_quando_as_duas_valem(self) -> None:
        """Dizer só a primeira faria o log mentir por omissão na retomada em que as duas valem."""
        from chess_diagram_ocr.training import _motivo_para_medir

        motivo = _motivo_para_medir(
            0.5, mesmo_split=False, mesma_metrica=False,
            nome_gravado="train_loss", metric_name="val_board_exact_acc",
        )
        self.assertIn("outro split", motivo)
        self.assertIn("train_loss", motivo)


class UnidadeDoLoteNosMetadadosTests(unittest.TestCase):
    """O checkpoint declara o lote que **governou** o treino (S-372).

    `batch_size` é do amostrador por janela da S-26; `boards_per_batch` é da cabeça por
    tabuleiro da S-62b. Cada regime ignora o número do outro, e só o primeiro ia gravado --
    então dois treinos com `boards_per_batch` 4 e 8 saíam com metadados idênticos, que é o
    que a S-105 existiu para acabar.
    """

    def _metadados(self, *, head: str, boards_per_batch: int = 4):
        from chess_diagram_ocr.model import ArchConfig
        from chess_diagram_ocr.training import OptimPlan, _optim_metadata

        return _optim_metadata(
            OptimPlan(batch_size=128, boards_per_batch=boards_per_batch),
            ArchConfig(head=head),  # type: ignore[arg-type]
        )

    def test_os_dois_numeros_vao_gravados(self) -> None:
        metadados = self._metadados(head="linear")
        self.assertEqual(metadados["batch_size"], 128)
        self.assertEqual(metadados["boards_per_batch"], 4)

    def test_a_unidade_diz_qual_dos_dois_valeu(self) -> None:
        self.assertEqual(self._metadados(head="linear")["batch_unit"], "square")
        self.assertEqual(self._metadados(head="board")["batch_unit"], "board")

    def test_dois_treinos_da_cabeca_por_tabuleiro_sao_distinguiveis(self) -> None:
        """O critério de aceite: era este o par que saía idêntico."""
        quatro = self._metadados(head="board", boards_per_batch=4)
        oito = self._metadados(head="board", boards_per_batch=8)
        self.assertNotEqual(quatro, oito)


class ProbabilidadeDasGenericasTests(unittest.TestCase):
    """`jitter` e `affine` são probabilidades, e agora a pipeline as lê (S-376)."""

    def _tipos(self, **kwargs: float) -> list[str]:
        from chess_diagram_ocr.augment import AugmentConfig

        return [type(etapa).__name__ for etapa in build_train_transform(AugmentConfig(**kwargs)).transforms]

    def test_o_padrao_monta_a_pipeline_de_sempre(self) -> None:
        """**O treino do padrão tem de sair idêntico**: `RandomApply` sorteia mesmo com `p=1`."""
        self.assertEqual(self._tipos(), ["RandomApply", "ColorJitter", "RandomAffine", "Lambda"])

    def test_jitter_zero_tira_o_jitter_da_lista(self) -> None:
        self.assertEqual(self._tipos(jitter=0.0), ["RandomApply", "RandomAffine", "Lambda"])

    def test_affine_zero_tira_o_afim_da_lista(self) -> None:
        self.assertEqual(self._tipos(affine=0.0), ["RandomApply", "ColorJitter", "Lambda"])

    def test_probabilidade_intermediaria_envolve_em_random_apply(self) -> None:
        self.assertEqual(self._tipos(jitter=0.5), ["RandomApply", "RandomApply", "RandomAffine", "Lambda"])
