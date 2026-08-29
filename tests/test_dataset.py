from __future__ import annotations

import tempfile
import unittest
import unittest.mock
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from chess_diagram_ocr.atomic_io import read_image, write_image
from chess_diagram_ocr.config import BOARD_SIZE
from chess_diagram_ocr.dataset import (
    BoardFenDataset,
    DatasetEntry,
    append_training_sample,
    migrate_labels_csv,
)
from chess_diagram_ocr.labels import ILLEGAL_OK, LabelStore

LEGAL = "4k3/8/8/8/8/8/8/4K3"
FATAL = "4n3/8/8/4B2n/8/8/8/8"  # sem reis
TURN_FLIP = "R3k3/8/8/8/8/8/8/4K3"  # legal apenas com pretas a jogar


def _write_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = ["filename,fen"] + [f"{name},{fen}" for name, fen in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_board(directory: Path, name: str, size: int = BOARD_SIZE) -> None:
    write_image(directory / name, np.full((size, size, 3), 200, dtype=np.uint8))


class MalformedCsvTests(unittest.TestCase):
    """Regressao: uma celula FEN vazia derrubava todo o carregamento do dataset."""

    def test_empty_fen_cell_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "a.png")
            _write_board(samples, "b.png")
            _write_csv(root / "labels.csv", [("a.png", LEGAL), ("b.png", "")])

            dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset.entries), 1)
            self.assertEqual(dataset.entries[0].filename, "a.png")

    def test_missing_columns_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "labels.csv").write_text("arquivo,posicao\na.png,x\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                BoardFenDataset(root / "labels.csv", root)

    def test_absent_csv_yields_empty_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = BoardFenDataset(Path(tmp) / "ausente.csv", Path(tmp))
            self.assertEqual(len(dataset), 0)

    def test_missing_image_warns_and_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_csv(root / "labels.csv", [("ausente.png", LEGAL)])

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset.entries), 0)
            self.assertTrue(any("imagem ausente" in str(w.message) for w in caught))


class LegalityFilterTests(unittest.TestCase):
    def test_fatal_labels_are_skipped_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            for name in ("ok.png", "ruim.png"):
                _write_board(samples, name)
            _write_csv(root / "labels.csv", [("ok.png", LEGAL), ("ruim.png", FATAL)])

            dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset.entries), 1)
            self.assertEqual(len(dataset.skipped_illegal), 1)
            self.assertEqual(dataset.skipped_illegal[0][0], "ruim.png")

    def test_confirmed_illegal_labels_survive_the_filter(self) -> None:
        """A estrutura de peões que uma pessoa confirmou treina; a ilegal sem marca, não.

        As duas linhas violam a mesma regra (nenhum rei). O que as separa é só a coluna, e é
        essa separação que faz a confirmação da interface significar alguma coisa.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            for name in ("estrutura.png", "erro.png"):
                _write_board(samples, name)
            (root / "labels.csv").write_text(
                "filename,fen,illegal_ok\n"
                f"estrutura.png,{FATAL},{ILLEGAL_OK}\n"
                f"erro.png,{FATAL},\n",
                encoding="utf-8",
            )

            dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual([entry.filename for entry in dataset.entries], ["estrutura.png"])
            self.assertEqual(dataset.kept_illegal, ["estrutura.png"])
            self.assertEqual([name for name, _ in dataset.skipped_illegal], ["erro.png"])

    def test_skip_illegal_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "ruim.png")
            _write_csv(root / "labels.csv", [("ruim.png", FATAL)])

            dataset = BoardFenDataset(root / "labels.csv", samples, skip_illegal=False)

            self.assertEqual(len(dataset.entries), 1)

    def test_turn_flip_labels_are_kept(self) -> None:
        # As pecas estao certas; so o turno assumido esta errado. Descartar perderia
        # uma amostra perfeitamente boa para o treino.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "turno.png")
            _write_csv(root / "labels.csv", [("turno.png", TURN_FLIP)])

            dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset.entries), 1)
            self.assertEqual(dataset.skipped_illegal, [])


class SplitFilterTests(unittest.TestCase):
    def test_only_requested_split_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            for name in ("a.png", "b.png", "c.png"):
                _write_board(samples, name)
            _write_csv(root / "labels.csv", [("a.png", LEGAL), ("b.png", LEGAL), ("c.png", LEGAL)])
            splits = {"a.png": "train", "b.png": "val", "c.png": "test"}

            train = BoardFenDataset(root / "labels.csv", samples, split="train", splits=splits)  # type: ignore[arg-type]
            test = BoardFenDataset(root / "labels.csv", samples, split="test", splits=splits)  # type: ignore[arg-type]

            self.assertEqual([e.filename for e in train.entries], ["a.png"])
            self.assertEqual([e.filename for e in test.entries], ["c.png"])

    def test_sample_without_recorded_split_is_excluded(self) -> None:
        # Amostra nova nao pode entrar no conjunto de teste por acidente.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            for name in ("a.png", "nova.png"):
                _write_board(samples, name)
            _write_csv(root / "labels.csv", [("a.png", LEGAL), ("nova.png", LEGAL)])

            test = BoardFenDataset(
                root / "labels.csv", samples, split="test", splits={"a.png": "test"}  # type: ignore[arg-type]
            )

            self.assertEqual([e.filename for e in test.entries], ["a.png"])

    def test_split_without_map_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "a.png")
            _write_csv(root / "labels.csv", [("a.png", LEGAL)])

            with self.assertRaises(ValueError):
                BoardFenDataset(root / "labels.csv", samples, split="train")


class ItemShapeTests(unittest.TestCase):
    def test_each_board_yields_64_squares(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "a.png")
            _write_csv(root / "labels.csv", [("a.png", LEGAL)])

            dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset), 64)
            tensor, label = dataset[0]
            self.assertEqual(tuple(tensor.shape), (1, 64, 64))
            self.assertIsInstance(label, int)

    def test_king_squares_carry_the_right_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "a.png")
            _write_csv(root / "labels.csv", [("a.png", LEGAL)])
            dataset = BoardFenDataset(root / "labels.csv", samples)

            # LEGAL = "4k3/8/.../4K3": indice 4 e o rei preto (e8), 60 o branco (e1).
            self.assertEqual(dataset[4][1], 12)  # 'k'
            self.assertEqual(dataset[60][1], 6)  # 'K'


class AppendSampleTests(unittest.TestCase):
    def test_appending_writes_image_and_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            path = append_training_sample(board, LEGAL, root / "labels.csv", root / "samples")

            self.assertTrue(path.exists())
            self.assertIn(path.name, (root / "labels.csv").read_text(encoding="utf-8"))

    def test_a_imagem_que_nao_gravou_nao_vira_linha_no_csv(self) -> None:
        """S-111: a gravação da imagem falha em silêncio, e quem chamava seguia adiante.

        Disco cheio, pasta em rede fora do ar, antivírus segurando o arquivo: gravava-se a
        linha apontando para um PNG inexistente. O prejuízo é o trabalho humano daquela
        correção, e ele só aparece semanas depois, na linha da auditoria "rótulos cujo PNG
        sumiu -- descartados em silêncio no treino".
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            with unittest.mock.patch.object(Path, "write_bytes", side_effect=OSError("disco cheio")):
                with self.assertRaises(OSError) as ctx:
                    append_training_sample(board, LEGAL, root / "labels.csv", root / "samples")

            self.assertIn("Não foi possível gravar", str(ctx.exception))
            self.assertFalse((root / "labels.csv").exists())

    def test_a_imagem_que_nao_codificou_nao_vira_linha_no_csv(self) -> None:
        """A outra metade: o `imencode` recusa e devolve `False` em vez de levantar."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            with unittest.mock.patch("cv2.imencode", return_value=(False, None)):
                with self.assertRaises(OSError) as ctx:
                    append_training_sample(board, LEGAL, root / "labels.csv", root / "samples")

            self.assertIn("não conseguiu codificar", str(ctx.exception))
            self.assertFalse((root / "labels.csv").exists())

    def test_a_falha_de_gravacao_nao_acrescenta_a_um_csv_que_ja_existe(self) -> None:
        """O caso que importa de verdade: o CSV tem 3.936 linhas e não pode ganhar uma órfã."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)
            append_training_sample(board, LEGAL, root / "labels.csv", root / "samples")
            antes = (root / "labels.csv").read_text(encoding="utf-8")

            with unittest.mock.patch.object(Path, "write_bytes", side_effect=OSError("disco cheio")):
                with self.assertRaises(OSError):
                    append_training_sample(board, LEGAL, root / "labels.csv", root / "samples")

            self.assertEqual((root / "labels.csv").read_text(encoding="utf-8"), antes)

    def test_fatal_position_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            with self.assertRaises(ValueError) as ctx:
                append_training_sample(board, FATAL, root / "labels.csv", root / "samples")

            self.assertIn("ilegal", str(ctx.exception).lower())
            self.assertFalse((root / "labels.csv").exists())

    def test_fatal_position_can_be_forced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            path = append_training_sample(
                board, FATAL, root / "labels.csv", root / "samples", allow_illegal=True
            )

            self.assertTrue(path.exists())

    def test_forced_illegal_row_carries_the_mark(self) -> None:
        """Sem a marca, o treino descartaria a amostra e o `--fix` a tiraria do arquivo."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            append_training_sample(
                board, FATAL, root / "labels.csv", root / "samples", allow_illegal=True
            )

            entry = LabelStore(root / "labels.csv").read()[0]
            self.assertEqual(entry.illegal_ok, ILLEGAL_OK)
            self.assertTrue(entry.illegal_accepted)

    def test_legal_row_saved_with_the_bypass_is_not_marked(self) -> None:
        """`allow_illegal` não é o que marca: marcar é a posição ser de fato ilegal.

        Um chamador que passe `allow_illegal=True` por precaução sobre um tabuleiro normal não
        pode acabar dispensando aquela linha da checagem de legalidade para sempre.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            append_training_sample(
                board, LEGAL, root / "labels.csv", root / "samples", allow_illegal=True
            )

            self.assertEqual(LabelStore(root / "labels.csv").read()[0].illegal_ok, "")

    def test_unparseable_fen_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            with self.assertRaises(ValueError):
                append_training_sample(board, "isto nao e uma fen", root / "labels.csv", root / "samples")

    def test_board_is_resized_to_canonical_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((200, 200, 3), 128, dtype=np.uint8)

            path = append_training_sample(board, LEGAL, root / "labels.csv", root / "samples")

            written = read_image(path)
            self.assertEqual(written.shape[:2], (BOARD_SIZE, BOARD_SIZE))


class LabelSchemaTests(unittest.TestCase):
    """S-19: as colunas novas entram sem quebrar os 3.195 rótulos que já existem."""

    def test_csv_antigo_carrega_com_campos_vazios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "a.png")
            _write_csv(root / "labels.csv", [("a.png", LEGAL)])

            dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset.entries), 1)
            self.assertEqual(dataset.entries[0].side_to_move, "")
            self.assertEqual(dataset.entries[0].source_pdf, "")

    def test_csv_novo_carrega_com_os_campos_preenchidos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "a.png")
            (root / "labels.csv").write_text(
                "filename,fen,side_to_move,source_pdf,source_page,source_diagram,"
                "detection_source,created_at,corrected_by\n"
                f"a.png,{LEGAL},b,livro.pdf,20,1,embedded,2026-07-26T00:00:00Z,\n",
                encoding="utf-8",
            )

            entry = BoardFenDataset(root / "labels.csv", samples).entries[0]

            self.assertEqual(entry.side_to_move, "b")
            self.assertEqual(entry.source_pdf, "livro.pdf")
            self.assertEqual(entry.source_page, "20")
            self.assertEqual(entry.detection_source, "embedded")
            self.assertEqual(entry.corrected_by, "")

    def test_lado_a_jogar_da_fen_vale_quando_a_coluna_esta_vazia(self) -> None:
        self.assertEqual(DatasetEntry(filename="a.png", fen=f"{LEGAL} b - - 0 1").resolved_side_to_move, "b")
        self.assertEqual(DatasetEntry(filename="a.png", fen=LEGAL).resolved_side_to_move, "")

    def test_gravacao_registra_lado_a_jogar_e_origem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            append_training_sample(
                board,
                LEGAL,
                root / "labels.csv",
                root / "samples",
                side_to_move="b",
                source_pdf="livro.pdf",
                source_page=20,
                source_diagram=2,
                detection_source="contour",
            )

            frame = pd.read_csv(root / "labels.csv")
            self.assertEqual(frame.loc[0, "side_to_move"], "b")
            self.assertEqual(frame.loc[0, "source_pdf"], "livro.pdf")
            self.assertEqual(frame.loc[0, "source_page"], 20)
            self.assertEqual(frame.loc[0, "detection_source"], "contour")
            # A coluna e a FEN sao gravadas juntas: nao pode haver duas verdades no arquivo.
            self.assertEqual(str(frame.loc[0, "fen"]).split()[1], "b")

    def test_gravar_no_csv_antigo_preserva_as_linhas_existentes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "labels.csv", [("antiga.png", LEGAL)])
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            append_training_sample(board, LEGAL, root / "labels.csv", root / "samples", side_to_move="b")

            frame = pd.read_csv(root / "labels.csv")
            self.assertEqual(len(frame), 2)
            self.assertEqual(frame.loc[0, "filename"], "antiga.png")
            self.assertEqual(list(frame.columns)[:3], ["filename", "fen", "side_to_move"])


class IntegerColumnTests(unittest.TestCase):
    """S-58: `source_page` e `source_diagram` são inteiros em texto, e continuam sendo.

    O defeito: `pd.read_csv` sem `dtype` tipava a coluna como `float64` porque 98,6% das
    células estão vazias, e `20` voltava `20.0`. Como a gravação relê o arquivo inteiro
    antes de acrescentar uma linha, cada amostra nova reescrevia as antigas nesse formato --
    o `labels.csv` acabou com os dois, e um diff de uma linha virava um diff de milhares.
    """

    def _uma_amostra(self, root: Path, **campos: object) -> None:
        board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)
        append_training_sample(board, LEGAL, root / "labels.csv", root / "samples", **campos)  # type: ignore[arg-type]

    def test_pagina_e_diagrama_sao_gravados_como_inteiro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._uma_amostra(root, source_pdf="livro.pdf", source_page=20, source_diagram=1)

            linhas = (root / "labels.csv").read_text(encoding="utf-8").splitlines()
            self.assertIn(",20,1,", linhas[1])
            self.assertNotIn("20.0", linhas[1])

    def test_uma_amostra_nova_nao_reescreve_as_linhas_antigas(self) -> None:
        """O critério de aceite da S-58: gravar produz um diff de exatamente uma linha."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._uma_amostra(root, source_pdf="livro.pdf", source_page=20, source_diagram=1)
            antes = (root / "labels.csv").read_text(encoding="utf-8").splitlines()

            self._uma_amostra(root, source_pdf="livro.pdf", source_page=21, source_diagram=2)
            depois = (root / "labels.csv").read_text(encoding="utf-8").splitlines()

            self.assertEqual(len(depois), len(antes) + 1)
            self.assertEqual(depois[: len(antes)], antes, "linhas antigas foram reescritas")

    def test_um_csv_com_o_formato_antigo_converge_na_proxima_gravacao(self) -> None:
        """Normalizar na escrita dispensa comando de migração: o arquivo se conserta sozinho."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "labels.csv").write_text(
                "filename,fen,side_to_move,source_pdf,source_page,source_diagram,"
                "detection_source,created_at,corrected_by\n"
                f"antiga.png,{LEGAL} w - - 0 1,w,livro.pdf,20.0,1.0,contour,2026-01-01T00:00:00Z,\n",
                encoding="utf-8",
            )

            self._uma_amostra(root, source_pdf="livro.pdf", source_page=21, source_diagram=2)

            frame = pd.read_csv(root / "labels.csv", dtype=str, keep_default_na=False)
            self.assertEqual(list(frame["source_page"]), ["20", "21"])
            self.assertEqual(list(frame["source_diagram"]), ["1", "2"])

    def test_celula_vazia_continua_vazia_e_nao_vira_nan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._uma_amostra(root)  # sem nenhum campo de origem

            texto = (root / "labels.csv").read_text(encoding="utf-8")
            self.assertNotIn("nan", texto.lower())
            entrada = BoardFenDataset(root / "labels.csv", root / "samples", cache_size=0).entries
            self.assertEqual(entrada[0].source_page, "")
            self.assertEqual(entrada[0].source_diagram, "")

    def test_valor_que_nao_e_numero_passa_intacto(self) -> None:
        """Não é papel da normalização decidir que um valor inesperado é lixo."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "labels.csv").write_text(
                "filename,fen,side_to_move,source_pdf,source_page,source_diagram,"
                "detection_source,created_at,corrected_by\n"
                f"antiga.png,{LEGAL} w - - 0 1,w,livro.pdf,xii,capa,contour,2026-01-01T00:00:00Z,\n",
                encoding="utf-8",
            )

            self._uma_amostra(root, source_page=3)

            frame = pd.read_csv(root / "labels.csv", dtype=str, keep_default_na=False)
            self.assertEqual(list(frame["source_page"]), ["xii", "3"])
            self.assertEqual(list(frame["source_diagram"]), ["capa", ""])


class MigrateLabelsTests(unittest.TestCase):
    def test_migracao_deduz_lado_a_jogar_pela_legalidade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "labels.csv", [("a.png", TURN_FLIP), ("b.png", LEGAL)])

            counters = migrate_labels_csv(root / "labels.csv")

            frame = pd.read_csv(root / "labels.csv").fillna("")
            self.assertEqual(list(frame["side_to_move"]), ["b", ""])
            self.assertEqual(counters["inferido"], 1)
            self.assertEqual(counters["sem_resposta"], 1)

    def test_migracao_nao_inventa_brancas_para_quem_nao_responde(self) -> None:
        """Gravar `w` aqui repetiria o erro que a S-19 existe para corrigir."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "labels.csv", [("a.png", LEGAL)])

            migrate_labels_csv(root / "labels.csv")

            frame = pd.read_csv(root / "labels.csv").fillna("")
            self.assertEqual(frame.loc[0, "side_to_move"], "")

    def test_migracao_respeita_lado_ja_declarado_na_fen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "labels.csv", [("a.png", f"{LEGAL} b - - 0 1")])

            counters = migrate_labels_csv(root / "labels.csv")

            self.assertEqual(pd.read_csv(root / "labels.csv").loc[0, "side_to_move"], "b")
            self.assertEqual(counters["ja_tinha"], 1)

    def test_migracao_grava_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "labels.csv", [("a.png", LEGAL)])

            migrate_labels_csv(root / "labels.csv")

            self.assertTrue(list(root.glob("labels.csv.bak-*")))

    def test_migracao_e_idempotente(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "labels.csv", [("a.png", TURN_FLIP)])

            migrate_labels_csv(root / "labels.csv", backup=False)
            primeira = (root / "labels.csv").read_text(encoding="utf-8")
            migrate_labels_csv(root / "labels.csv", backup=False)

            self.assertEqual(primeira, (root / "labels.csv").read_text(encoding="utf-8"))

    def test_csv_sem_as_colunas_obrigatorias_e_recusado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "labels.csv").write_text("filename\na.png\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                migrate_labels_csv(root / "labels.csv", backup=False)


if __name__ == "__main__":
    unittest.main()
