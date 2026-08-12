"""A S-62 de ponta a ponta: a cabeça por tabuleiro (b) e o treino com coordenadas (a).

A forma dos canais está em `test_model.py`; aqui o que se exercita é o **treino**, que é
onde os dois degraus tocam o `DataLoader`, o aumento e o checkpoint.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
import torch

from chess_diagram_ocr.config import BOARD_SIZE, PIECE_CLASSES
from chess_diagram_ocr.dataset import BoardFenDataset, BoardUnitDataset
from chess_diagram_ocr.inference import load_model, predict_board
from chess_diagram_ocr.model import SQUARES_PER_BOARD, ArchConfig, build_model
from chess_diagram_ocr.training import ImageChannelsOnly, train_model

LEGAL = "4k3/8/8/8/8/8/8/4K3"
OUTRA = "4k3/8/8/8/8/8/4P3/4K3"
BOARD_ARCH = ArchConfig(head="board")


def _fixture(root: Path, boards: int = 4) -> tuple[Path, Path]:
    samples = root / "samples"
    samples.mkdir(exist_ok=True)
    linhas = ["filename,fen"]
    rng = np.random.default_rng(7)
    for i in range(boards):
        nome = f"b{i}.png"
        cv2.imwrite(str(samples / nome), rng.integers(0, 256, (BOARD_SIZE, BOARD_SIZE, 3), dtype=np.uint8))
        linhas.append(f"{nome},{LEGAL if i % 2 == 0 else OUTRA}")
    csv = root / "labels.csv"
    csv.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return csv, samples


class ForwardContractTests(unittest.TestCase):
    def test_version_names_the_head(self) -> None:
        self.assertEqual(BOARD_ARCH.version, "cnn-gray-64-board")
        self.assertEqual(ArchConfig.from_version("cnn-gray-64-board"), BOARD_ARCH)

    def test_accepts_boards_and_returns_flat_logits(self) -> None:
        model = build_model(BOARD_ARCH, pretrained=False).eval()
        entrada = torch.zeros(3, SQUARES_PER_BOARD, 1, 64, 64)
        with torch.no_grad():
            saida = model(entrada)
        self.assertEqual(tuple(saida.shape), (3 * SQUARES_PER_BOARD, len(PIECE_CLASSES)))

    def test_accepts_the_flat_batch_the_pipeline_already_builds(self) -> None:
        """`board_probabilities` e `evaluation` montam (N, C, S, S). Tem de continuar valendo."""
        model = build_model(BOARD_ARCH, pretrained=False).eval()
        plano = torch.rand(2 * SQUARES_PER_BOARD, 1, 64, 64)
        with torch.no_grad():
            por_lote = model(plano)
            por_tabuleiro = model(plano.reshape(2, SQUARES_PER_BOARD, 1, 64, 64))
        self.assertTrue(torch.equal(por_lote, por_tabuleiro))

    def test_rejects_a_batch_that_is_not_whole_boards(self) -> None:
        # Adivinhar produziria uma leitura errada sem erro nenhum -- o pior resultado possivel.
        model = build_model(BOARD_ARCH, pretrained=False).eval()
        with self.assertRaises(ValueError) as ctx:
            model(torch.zeros(100, 1, 64, 64))
        self.assertIn("64", str(ctx.exception))

    def test_a_square_sees_the_other_sixty_three(self) -> None:
        """Se a saída de uma casa não mudar quando outra muda, a cabeça não está misturando nada."""
        torch.manual_seed(0)
        model = build_model(BOARD_ARCH, pretrained=False).eval()
        a = torch.rand(1, SQUARES_PER_BOARD, 1, 64, 64)
        b = a.clone()
        b[0, 40] = torch.rand(1, 64, 64)
        with torch.no_grad():
            self.assertFalse(torch.allclose(model(a)[0], model(b)[0], atol=1e-6))

    def test_only_over_the_cnn_trunk(self) -> None:
        with self.assertRaises(ValueError):
            build_model(ArchConfig(backbone="mobilenet_v3_small", head="board"), pretrained=False)

    def test_composes_with_the_coordinate_channels(self) -> None:
        arch = ArchConfig(head="board", coords=True)
        self.assertEqual(arch.version, "cnn-gray-64-board-coords")
        model = build_model(arch, pretrained=False).eval()
        with torch.no_grad():
            saida = model(torch.zeros(1, SQUARES_PER_BOARD, arch.in_channels, 64, 64))
        self.assertEqual(tuple(saida.shape), (SQUARES_PER_BOARD, len(PIECE_CLASSES)))


class BoardUnitDatasetTests(unittest.TestCase):
    def test_item_is_a_whole_board(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv, samples = _fixture(Path(tmp))
            base = BoardFenDataset(csv, samples, arch=BOARD_ARCH)
            unidades = BoardUnitDataset(base)

            x, y = unidades[0]
            self.assertEqual(len(unidades), len(base.entries))
            self.assertEqual(tuple(x.shape), (SQUARES_PER_BOARD, 1, 64, 64))
            self.assertEqual(tuple(y.shape), (SQUARES_PER_BOARD,))

    def test_cells_are_the_same_the_per_square_dataset_produces(self) -> None:
        """A garantia que faz o treino por tabuleiro ver o que a inferência monta."""
        with tempfile.TemporaryDirectory() as tmp:
            csv, samples = _fixture(Path(tmp))
            base = BoardFenDataset(csv, samples, arch=BOARD_ARCH)
            x, y = BoardUnitDataset(base)[1]

            for square in range(SQUARES_PER_BOARD):
                esperado_x, esperado_y = base[1 * 64 + square]
                self.assertTrue(torch.equal(x[square], esperado_x), f"casa {square}")
                self.assertEqual(int(y[square]), esperado_y)

    def test_board_indices_restrict_what_it_exposes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv, samples = _fixture(Path(tmp))
            base = BoardFenDataset(csv, samples, arch=BOARD_ARCH)
            unidades = BoardUnitDataset(base, board_indices=[2, 3])

            self.assertEqual(len(unidades), 2)
            self.assertEqual([e.filename for e in unidades.entries], ["b2.png", "b3.png"])

    def test_augmentation_is_drawn_per_square(self) -> None:
        """Aplicar o Compose ao bloco sortearia um parâmetro só para as 64 casas."""
        vistas: list[int] = []

        def transform(x: torch.Tensor) -> torch.Tensor:
            vistas.append(x.shape[0])
            return x

        with tempfile.TemporaryDirectory() as tmp:
            csv, samples = _fixture(Path(tmp))
            base = BoardFenDataset(csv, samples, arch=BOARD_ARCH)
            BoardUnitDataset(base, transform=transform)[0]

        self.assertEqual(len(vistas), SQUARES_PER_BOARD)
        self.assertTrue(all(canais == 1 for canais in vistas), "o transform tem de ver uma casa por vez")


class EndToEndTests(unittest.TestCase):
    def test_one_epoch_produces_a_checkpoint_the_pipeline_can_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv, samples = _fixture(root, boards=6)
            destino = root / "board_head.pt"

            run = train_model(
                csv_path=csv,
                samples_dir=samples,
                model_path=destino,
                epochs=1,
                arch=BOARD_ARCH,
                boards_per_batch=2,
                num_workers=0,
                calibrate=False,
                fresh=True,
            )

            self.assertEqual(len(run.history), 1)
            self.assertEqual(run.metadata["arch_version"], "cnn-gray-64-board")
            self.assertTrue(destino.exists())

            model, device = load_model(destino)
            tabuleiro = np.full((BOARD_SIZE, BOARD_SIZE, 3), 180, dtype=np.uint8)
            prediction = predict_board(tabuleiro, model, device)
            self.assertEqual(len(prediction.class_indices), SQUARES_PER_BOARD)

    def test_a_board_head_checkpoint_does_not_load_as_a_linear_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv, samples = _fixture(root, boards=4)
            destino = root / "board_head.pt"
            train_model(
                csv_path=csv,
                samples_dir=samples,
                model_path=destino,
                epochs=1,
                arch=BOARD_ARCH,
                boards_per_batch=2,
                num_workers=0,
                calibrate=False,
                fresh=True,
            )

            with self.assertRaises(RuntimeError):
                load_model(destino, arch=ArchConfig())


class CoordinateTrainingTests(unittest.TestCase):
    """S-62a no laço de treino, que é onde ela quebrou primeiro."""

    def test_the_augmentation_never_sees_the_coordinate_channels(self) -> None:
        """Regressão do defeito que travou o primeiro treino com `--coords`.

        O `ColorJitter` recusa 4 canais, e recusar foi sorte: um aumento que os aceitasse
        teria treinado, e a coordenada transladada pelo `RandomAffine` viraria um modelo pior
        sem nenhuma mensagem. Ver `training.ImageChannelsOnly`.
        """
        vistos: list[int] = []

        def inner(x: torch.Tensor) -> torch.Tensor:
            vistos.append(x.shape[-3])
            return x

        protegido = ImageChannelsOnly(inner, image_channels=1)
        entrada = torch.rand(4, 64, 64)
        entrada[1:] = 0.5  # planos de coordenada, constantes

        saida = protegido(entrada)

        self.assertEqual(vistos, [1])
        self.assertEqual(tuple(saida.shape), (4, 64, 64))
        self.assertTrue(torch.equal(saida[1:], entrada[1:]), "a coordenada tem de sair intacta")

    def test_it_is_transparent_without_coordinate_channels(self) -> None:
        protegido = ImageChannelsOnly(lambda x: x * 2, image_channels=1)
        entrada = torch.ones(1, 8, 8)
        self.assertTrue(torch.equal(protegido(entrada), entrada * 2))

    def test_it_survives_pickling(self) -> None:
        # `num_workers > 0` no Windows usa spawn: a pipeline inteira e pickleada por worker.
        import pickle

        from chess_diagram_ocr.training import build_train_transform

        pickle.dumps(ImageChannelsOnly(build_train_transform(), image_channels=1))

    def test_one_epoch_with_coords_produces_a_readable_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv, samples = _fixture(root, boards=4)
            destino = root / "coords.pt"

            run = train_model(
                csv_path=csv,
                samples_dir=samples,
                model_path=destino,
                epochs=1,
                arch=ArchConfig(coords=True),
                num_workers=0,
                calibrate=False,
                fresh=True,
            )

            self.assertEqual(run.metadata["arch_version"], "cnn-gray-64-linear-coords")
            model, device = load_model(destino)
            tabuleiro = np.full((BOARD_SIZE, BOARD_SIZE, 3), 180, dtype=np.uint8)
            self.assertEqual(len(predict_board(tabuleiro, model, device).class_indices), SQUARES_PER_BOARD)


if __name__ == "__main__":
    unittest.main()
