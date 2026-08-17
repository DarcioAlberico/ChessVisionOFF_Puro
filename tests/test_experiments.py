"""A grade da S-29 lê a partição e não a escreve (S-106).

`cli/experiment.py` carrega `load_splits(args.splits)` **uma vez, antes** da grade, e passa
esse dicionário congelado a `run_variant`. Dentro dele, `train_model` era chamado sem
`assign_splits=False`, e o padrão é `True`.

Efeito: a **primeira** variante atribuía split às amostras que estavam sem, reescrevendo o
`splits.csv`; as seguintes treinavam sobre a partição nova; e a avaliação de todas usava o
mapa velho. Com **357 amostras sem split** no dataset de hoje, isto não é hipótese -- é o que
teria acontecido na próxima execução da grade.

Uma grade que muda a partição no meio compara variantes contra conjuntos diferentes, que é
exatamente o que ela existe para não fazer.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.cli import experiment as cli_experiment
from chess_diagram_ocr.experiments import Variant, run_variant
from chess_diagram_ocr.model import ArchConfig
from chess_diagram_ocr.splits import load_splits, save_splits

LEGAL = "4k3/8/8/8/8/8/8/4K3"


def _dataset(root: Path, *, boards: int = 6, sem_split: int = 0) -> tuple[Path, Path, Path]:
    """Dataset mínimo. `sem_split` deixa os N últimos fora do `splits.csv`, de propósito."""
    samples = root / "samples"
    samples.mkdir(parents=True)
    linhas = ["filename,fen"]
    splits: dict[str, str] = {}
    rng = np.random.default_rng(0)
    for index in range(boards):
        nome = f"b{index}.png"
        cv2.imwrite(str(samples / nome), rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))
        linhas.append(f"{nome},{LEGAL}")
        if index < boards - sem_split:
            splits[nome] = "train" if index < boards - sem_split - 2 else "val"

    csv_path = root / "labels.csv"
    csv_path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    splits_path = root / "splits.csv"
    save_splits(splits_path, splits)  # type: ignore[arg-type]
    return csv_path, samples, splits_path


class GradeNaoReatribuiSplitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)

    def _roda(self, csv_path: Path, samples: Path, splits_path: Path) -> None:
        run_variant(
            Variant(name="ref", factor="referencia", arch=ArchConfig()),
            csv_path=csv_path,
            samples_dir=samples,
            splits_path=splits_path,
            splits=load_splits(splits_path),
            workdir=self.raiz / "work",
            epochs=1,
            seed=7,
            batch_size=64,
            num_workers=0,
        )

    def test_uma_variante_nao_altera_o_splits_csv(self) -> None:
        """**O critério de aceite.** Com amostra sem split, o padrão de `assign_splits` daria
        um split a ela -- e a variante seguinte treinaria sobre outra partição."""
        csv_path, samples, splits_path = _dataset(self.raiz, boards=6, sem_split=2)
        antes = splits_path.read_bytes()

        self._roda(csv_path, samples, splits_path)

        self.assertEqual(splits_path.read_bytes(), antes)

    def test_duas_variantes_veem_a_mesma_particao(self) -> None:
        """A garantia de que a grade compara: o mapa da primeira é o mapa da última."""
        csv_path, samples, splits_path = _dataset(self.raiz, boards=6, sem_split=2)
        primeira = load_splits(splits_path)

        self._roda(csv_path, samples, splits_path)
        self._roda(csv_path, samples, splits_path)

        self.assertEqual(load_splits(splits_path), primeira)

    def test_sem_amostra_solta_o_arquivo_tambem_fica_intacto(self) -> None:
        """A guarda vale também no caso feliz: ler não escreve, mesmo sem nada a atribuir."""
        csv_path, samples, splits_path = _dataset(self.raiz, boards=6, sem_split=0)
        antes = splits_path.read_bytes()

        self._roda(csv_path, samples, splits_path)

        self.assertEqual(splits_path.read_bytes(), antes)


class GradeRecusaComecarTests(unittest.TestCase):
    """A recusa é **antes** de começar: descobrir isso depois de sete treinos custa horas."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)

    def _args(self, csv_path: Path, samples: Path, splits_path: Path) -> list[str]:
        return [
            "--csv", str(csv_path),
            "--samples", str(samples),
            "--splits", str(splits_path),
            "--workdir", str(self.raiz / "work"),
            "--epochs", "1",
            "--only", "referencia",
        ]

    def test_amostra_sem_split_recusa_e_diz_o_que_fazer(self) -> None:
        csv_path, samples, splits_path = _dataset(self.raiz, boards=6, sem_split=2)

        codigo = cli_experiment.main(self._args(csv_path, samples, splits_path))

        self.assertEqual(codigo, 1, "a grade não atribui split, então ela não pode começar assim")

    def test_splits_ausente_continua_recusando_por_outro_motivo(self) -> None:
        """A guarda anterior a esta continua de pé, e a mensagem dela é outra."""
        csv_path, samples, _splits = _dataset(self.raiz, boards=6)
        vazio = self.raiz / "nao_existe.csv"

        self.assertEqual(cli_experiment.main(self._args(csv_path, samples, vazio)), 1)


if __name__ == "__main__":
    unittest.main()
