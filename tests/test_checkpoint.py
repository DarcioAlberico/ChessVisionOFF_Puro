from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import torch

from chess_diagram_ocr.checkpoint import (
    CHECKPOINT_FORMAT,
    check_compatible,
    load_checkpoint,
    load_state_dict,
    save_checkpoint,
)
from chess_diagram_ocr.config import PIECE_CLASSES
from chess_diagram_ocr.model import ArchConfig, PieceClassifier


def _metadata(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "arch_version": ArchConfig().version,
        "class_names": list(PIECE_CLASSES),
        "seed": 42,
        "split_hash": "abc123",
        "dataset_size": 2569,
        "best_metric": 0.95,
        "best_epoch": 3,
    }
    base.update(overrides)
    return base


class RoundTripTests(unittest.TestCase):
    def test_metadata_survives_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.pt"
            save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata(), temperature=1.42)

            checkpoint = load_checkpoint(path)
            self.assertFalse(checkpoint.is_legacy)
            self.assertEqual(checkpoint.arch_version, ArchConfig().version)
            self.assertEqual(checkpoint.class_names, list(PIECE_CLASSES))
            self.assertEqual(checkpoint.metadata["seed"], 42)
            self.assertEqual(checkpoint.metadata["split_hash"], "abc123")
            self.assertEqual(checkpoint.metadata["checkpoint_format"], CHECKPOINT_FORMAT)
            self.assertAlmostEqual(checkpoint.temperature, 1.42)
            self.assertAlmostEqual(checkpoint.best_metric or 0.0, 0.95)

    def test_weights_reload_into_the_same_architecture_strictly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.pt"
            original = PieceClassifier()
            save_checkpoint(path, original.state_dict(), metadata=_metadata())

            restored = PieceClassifier()
            restored.load_state_dict(load_checkpoint(path).state, strict=True)
            for a, b in zip(original.state_dict().values(), restored.state_dict().values(), strict=True):
                self.assertTrue(torch.equal(a, b))


class LegacyFormatTests(unittest.TestCase):
    """Checkpoints pre-Fase 5 continuam carregando: sem isso o BASELINE.md fica inverificavel."""

    def test_bare_state_dict_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.pt"
            torch.save(PieceClassifier().state_dict(), path)

            checkpoint = load_checkpoint(path)
            self.assertTrue(checkpoint.is_legacy)
            self.assertEqual(checkpoint.temperature, 1.0)
            self.assertEqual(checkpoint.arch_version, "")

    def test_model_state_without_metadata_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.pt"
            torch.save({"model_state": PieceClassifier().state_dict()}, path)

            checkpoint = load_checkpoint(path)
            self.assertTrue(checkpoint.is_legacy)
            self.assertEqual(checkpoint.temperature, 1.0)

    def test_load_state_dict_shim_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.pt"
            torch.save({"model_state": PieceClassifier().state_dict()}, path)
            self.assertIn("features.0.weight", load_state_dict(path, map_location="cpu"))

    def test_rejects_a_checkpoint_that_is_not_a_dict_of_weights(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.pt"
            torch.save(torch.zeros(3), path)
            with self.assertRaises(ValueError):
                load_checkpoint(path)

    def test_rejects_non_positive_temperature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.pt"
            torch.save({"model_state": PieceClassifier().state_dict(), "temperature": 0.0}, path)
            with self.assertRaises(ValueError):
                load_checkpoint(path)


class CompatibilityTests(unittest.TestCase):
    def test_matching_architecture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.pt"
            save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata())
            check_compatible(load_checkpoint(path), ArchConfig().version)

    def test_different_architecture_is_rejected_by_name(self) -> None:
        """A mensagem tem de nomear as duas arquiteturas.

        O torch tambem recusaria sob strict=True, mas com uma lista de tensores faltando
        -- e "size mismatch for classifier.1.weight" nao diz a ninguem que o problema e
        ter trocado 64x64 por 48x48.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.pt"
            save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata())

            outra = ArchConfig(image_size=48)
            with self.assertRaises(ValueError) as caught:
                check_compatible(load_checkpoint(path), outra.version)
            self.assertIn(ArchConfig().version, str(caught.exception))
            self.assertIn(outra.version, str(caught.exception))

    def test_legacy_checkpoint_is_not_rejected_on_metadata_alone(self) -> None:
        """Recusar checkpoint antigo bloqueava todo mundo sem comprar seguranca.

        A garantia contra retomar de outra arquitetura e o `strict=True`, nao o metadado:
        no espaco de `ArchConfig`, cada fator muda nome ou formato de algum tensor. Este
        teste trava a regressao de voltar a recusar por falta de metadados.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.pt"
            torch.save({"model_state": PieceClassifier().state_dict()}, path)

            checkpoint = load_checkpoint(path)
            self.assertTrue(checkpoint.is_legacy)
            check_compatible(checkpoint, ArchConfig().version)  # nao levanta
            PieceClassifier().load_state_dict(checkpoint.state, strict=True)

    def test_strict_load_is_what_catches_a_legacy_checkpoint_of_another_architecture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.pt"
            torch.save({"model_state": PieceClassifier(ArchConfig(image_size=32)).state_dict()}, path)

            checkpoint = load_checkpoint(path)
            check_compatible(checkpoint, ArchConfig().version)  # metadado nao sabe...
            with self.assertRaises(RuntimeError):  # ...mas os pesos sabem
                PieceClassifier().load_state_dict(checkpoint.state, strict=True)

    def test_different_class_list_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.pt"
            save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata(class_names=["a", "b"]))
            with self.assertRaises(ValueError):
                check_compatible(load_checkpoint(path), ArchConfig().version)


if __name__ == "__main__":
    unittest.main()
