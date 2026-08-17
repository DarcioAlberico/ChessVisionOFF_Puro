from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.audit import (
    DUPLICATE_HASH_SIZE,
    DUPLICATE_SHARE_CEILING,
    apply_side_to_move_fixes,
    audit_dataset,
    backup_csv,
    dedupe_summary,
    dhash,
    drop_missing_labels,
    find_duplicate_groups,
    hamming_distance,
    orphans_dir_for,
    prune_orphan_images,
    quarantine_fatal_labels,
    read_label_rows,
    remove_duplicate_labels,
    write_dedupe_summary,
)
from chess_diagram_ocr.labels import ILLEGAL_OK

LEGAL = "4k3/8/8/8/8/8/8/4K3"
LEGAL_OTHER = "4k3/8/8/8/8/8/4P3/4K3"
FATAL_NO_KINGS = "4n3/8/8/4B2n/8/8/8/8"
FATAL_TWO_WHITE_KINGS = "4k3/8/8/8/8/8/8/3KK3"
TURN_FLIP = "R3k3/8/8/8/8/8/8/4K3"  # pretas em xeque: legal apenas com "b"


def _board_image(seed: int, size: int = 128) -> np.ndarray:
    """Imagem sintetica deterministica, com estrutura suficiente para o dHash."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8)


class Fixture:
    def __init__(self, tmp: str) -> None:
        self.root = Path(tmp)
        self.samples = self.root / "samples"
        self.samples.mkdir()
        self.csv = self.root / "labels.csv"
        self.rows: list[tuple[str, str]] = []

    def add(self, name: str, fen: str, *, image: np.ndarray | None = None, write_image: bool = True) -> None:
        if write_image:
            img = image if image is not None else _board_image(len(self.rows) + 1)
            cv2.imwrite(str(self.samples / name), img)
        self.rows.append((name, fen))

    def write(self, *, illegal_ok: dict[str, str] | None = None) -> None:
        """Sem `illegal_ok`, escreve o esquema mínimo -- que é o que quase todo teste quer."""
        marcas = illegal_ok or {}
        if not marcas:
            lines = ["filename,fen"] + [f"{name},{fen}" for name, fen in self.rows]
        else:
            lines = ["filename,fen,illegal_ok"] + [
                f"{name},{fen},{marcas.get(name, '')}" for name, fen in self.rows
            ]
        self.csv.write_text("\n".join(lines) + "\n", encoding="utf-8")


class HashTests(unittest.TestCase):
    def test_default_hash_size_is_not_eight(self) -> None:
        # Um dHash 8x8 alinha com a grade 8x8 do tabuleiro e captura o padrao xadrezado
        # em vez das pecas. Regressao explicita: ver comentario em audit.DUPLICATE_HASH_SIZE.
        self.assertNotEqual(DUPLICATE_HASH_SIZE, 8)
        self.assertEqual(DUPLICATE_HASH_SIZE, 16)

    def test_identical_images_hash_equal(self) -> None:
        image = _board_image(7)
        self.assertEqual(dhash(image), dhash(image.copy()))

    def test_different_images_hash_far_apart(self) -> None:
        self.assertGreater(hamming_distance(dhash(_board_image(1)), dhash(_board_image(2))), 10)

    def test_hamming_distance_basics(self) -> None:
        self.assertEqual(hamming_distance(0b1011, 0b1011), 0)
        self.assertEqual(hamming_distance(0b1011, 0b1000), 2)


class AuditReportTests(unittest.TestCase):
    def test_classifies_each_kind_of_problem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.add("sem_reis.png", FATAL_NO_KINGS)
            fx.add("dois_reis.png", FATAL_TWO_WHITE_KINGS)
            fx.add("turno.png", TURN_FLIP)
            fx.add("ausente.png", LEGAL, write_image=False)
            fx.add("vazia.png", "")
            fx.write()

            report = audit_dataset(fx.csv, fx.samples)

            self.assertEqual(report.total_rows, 6)
            self.assertEqual(len(report.of_kind("fatal")), 2)
            self.assertEqual(len(report.of_kind("lado-a-jogar")), 1)
            self.assertEqual(len(report.of_kind("imagem-ausente")), 1)
            self.assertEqual(len(report.of_kind("sintaxe")), 1)

    def test_suggests_side_to_move_correction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("turno.png", TURN_FLIP)
            fx.write()

            issue = audit_dataset(fx.csv, fx.samples).of_kind("lado-a-jogar")[0]

            self.assertIsNotNone(issue.suggested_fen)
            self.assertIn(" b ", str(issue.suggested_fen))

    def test_counts_orphan_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.write()
            cv2.imwrite(str(fx.samples / "orfa.png"), _board_image(99))

            report = audit_dataset(fx.csv, fx.samples)

            self.assertEqual(report.orphan_images, ["orfa.png"])

    def test_class_distribution_counts_squares(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.write()

            report = audit_dataset(fx.csv, fx.samples)

            self.assertEqual(report.class_counts["K"], 1)
            self.assertEqual(report.class_counts["k"], 1)
            self.assertEqual(report.class_counts["empty"], 62)

    def test_missing_csv_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                audit_dataset(Path(tmp) / "nao_existe.csv", Path(tmp))


class DuplicateDetectionTests(unittest.TestCase):
    def test_same_image_same_label_is_a_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            shared = _board_image(11)
            fx.add("a.png", LEGAL, image=shared)
            fx.add("b.png", LEGAL, image=shared)
            fx.write()

            groups = find_duplicate_groups(fx.samples, fx.rows)

            self.assertEqual(groups, [["a.png", "b.png"]])

    def test_same_image_different_label_is_not_a_group(self) -> None:
        # Conflito de anotacao: remover as cegas descartaria a etiqueta correta.
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            shared = _board_image(12)
            fx.add("a.png", LEGAL, image=shared)
            fx.add("b.png", LEGAL_OTHER, image=shared)
            fx.write()

            self.assertEqual(find_duplicate_groups(fx.samples, fx.rows), [])

    def test_different_images_same_label_is_not_a_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("a.png", LEGAL, image=_board_image(21))
            fx.add("b.png", LEGAL, image=_board_image(22))
            fx.write()

            self.assertEqual(find_duplicate_groups(fx.samples, fx.rows), [])


class MutationTests(unittest.TestCase):
    def test_backup_preserves_original_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.write()
            original = fx.csv.read_bytes()

            backup = backup_csv(fx.csv)

            self.assertTrue(backup.exists())
            self.assertEqual(backup.read_bytes(), original)

    def test_apply_side_to_move_fixes_rewrites_only_the_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("turno.png", TURN_FLIP)
            fx.add("ok.png", LEGAL)
            fx.write()
            report = audit_dataset(fx.csv, fx.samples)

            applied = apply_side_to_move_fixes(fx.csv, report)

            self.assertEqual(applied, 1)
            after = audit_dataset(fx.csv, fx.samples)
            self.assertEqual(after.of_kind("lado-a-jogar"), [])
            # A colocacao das pecas nao mudou.
            content = fx.csv.read_text(encoding="utf-8")
            self.assertIn(TURN_FLIP, content)

    def test_quarantine_moves_fatal_rows_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.add("ruim.png", FATAL_NO_KINGS)
            fx.write()
            report = audit_dataset(fx.csv, fx.samples)
            quarantine = Path(tmp) / "quarantine.csv"

            moved = quarantine_fatal_labels(fx.csv, report, quarantine)

            self.assertEqual(moved, 1)
            self.assertTrue(quarantine.exists())
            self.assertIn("ruim.png", quarantine.read_text(encoding="utf-8"))
            self.assertNotIn("ruim.png", fx.csv.read_text(encoding="utf-8"))
            self.assertIn("ok.png", fx.csv.read_text(encoding="utf-8"))

    def test_quarantine_records_the_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ruim.png", FATAL_TWO_WHITE_KINGS)
            fx.write()
            report = audit_dataset(fx.csv, fx.samples)
            quarantine = Path(tmp) / "quarantine.csv"

            quarantine_fatal_labels(fx.csv, report, quarantine)

            self.assertIn("mais de um rei", quarantine.read_text(encoding="utf-8"))

    def test_quarantine_leaves_the_confirmed_illegal_rows_alone(self) -> None:
        """O `--fix` não pode desfazer o "sim" que a interface pediu.

        Sem isto, salvar um diagrama de estrutura seria salvar num arquivo de onde o comando
        seguinte o tira -- e o "sim" viraria uma pergunta sem consequência.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("estrutura.png", FATAL_NO_KINGS)
            fx.add("erro.png", FATAL_TWO_WHITE_KINGS)
            fx.write(illegal_ok={"estrutura.png": ILLEGAL_OK})
            report = audit_dataset(fx.csv, fx.samples)
            quarantine = Path(tmp) / "quarantine.csv"

            self.assertEqual([issue.filename for issue in report.of_kind("fatal")], ["erro.png"])
            self.assertEqual([issue.filename for issue in report.deliberate_illegal], ["estrutura.png"])
            # E ela conta como utilizavel, porque o treino de fato a usa.
            self.assertEqual(report.valid_rows, 1)

            self.assertEqual(quarantine_fatal_labels(fx.csv, report, quarantine), 1)
            self.assertIn("estrutura.png", fx.csv.read_text(encoding="utf-8"))
            self.assertNotIn("estrutura.png", quarantine.read_text(encoding="utf-8"))

    def test_dedupe_keeps_first_of_each_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            shared = _board_image(31)
            fx.add("a.png", LEGAL, image=shared)
            fx.add("b.png", LEGAL, image=shared)
            fx.write()
            report = audit_dataset(fx.csv, fx.samples)

            removed = remove_duplicate_labels(fx.csv, report)

            self.assertEqual(removed, 1)
            content = fx.csv.read_text(encoding="utf-8")
            self.assertIn("a.png", content)
            self.assertNotIn("b.png", content)


class HygieneTests(unittest.TestCase):
    """S-63: as duas ações que a auditoria só relatava, e o teto de redundância."""

    def test_prune_orphans_moves_instead_of_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("usada.png", LEGAL)
            fx.write()
            cv2.imwrite(str(fx.samples / "orfa.png"), _board_image(77))
            report = audit_dataset(fx.csv, fx.samples)
            self.assertEqual(report.orphan_images, ["orfa.png"])

            movidos = prune_orphan_images(report)

            self.assertEqual(len(movidos), 1)
            self.assertTrue(movidos[0].exists(), "o orfao tem de continuar existindo em outro lugar")
            self.assertFalse((fx.samples / "orfa.png").exists())
            self.assertTrue((fx.samples / "usada.png").exists())
            self.assertEqual(movidos[0].parent.parent, orphans_dir_for(fx.samples))

    def test_prune_orphans_does_not_overwrite_a_previous_prune(self) -> None:
        # Dois arquivos com o mesmo nome sao dois trabalhos diferentes; o segundo nao pode
        # apagar o primeiro so porque a poda de hoje repetiu um nome de ontem.
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.write()
            destino = orphans_dir_for(fx.samples) / "anterior"
            destino.mkdir(parents=True)
            (destino / "orfa.png").write_bytes(b"conteudo antigo")

            cv2.imwrite(str(fx.samples / "orfa.png"), _board_image(78))
            report = audit_dataset(fx.csv, fx.samples)
            movidos = prune_orphan_images(report, orphans_dir=destino.parent / "hoje")

            self.assertEqual(len(movidos), 1)
            self.assertEqual((destino / "orfa.png").read_bytes(), b"conteudo antigo")

    def test_drop_missing_moves_only_the_rows_without_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("existe.png", LEGAL)
            fx.add("sumiu.png", LEGAL_OTHER, write_image=False)
            fx.write()
            report = audit_dataset(fx.csv, fx.samples)
            quarentena = Path(tmp) / "quarantine.csv"

            dropped = drop_missing_labels(fx.csv, report, quarentena)

            self.assertEqual(dropped, 1)
            content = fx.csv.read_text(encoding="utf-8")
            self.assertIn("existe.png", content)
            self.assertNotIn("sumiu.png", content)

    def test_drop_missing_preserves_the_fen_in_quarantine(self) -> None:
        """A FEN é trabalho humano e a imagem é reextraível: apagar a linha inverteria o valor."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("sumiu.png", LEGAL_OTHER, write_image=False)
            fx.write()
            quarentena = Path(tmp) / "quarantine.csv"

            drop_missing_labels(fx.csv, audit_dataset(fx.csv, fx.samples), quarentena)

            texto = quarentena.read_text(encoding="utf-8")
            self.assertIn("sumiu.png", texto)
            self.assertIn(LEGAL_OTHER, texto)
            self.assertIn("imagem ausente", texto)

    def test_the_two_actions_together_leave_the_same_set_of_names(self) -> None:
        """O critério de aceite da S-63, escrito como teste."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.add("sumiu.png", LEGAL_OTHER, write_image=False)
            fx.write()
            cv2.imwrite(str(fx.samples / "orfa.png"), _board_image(79))

            report = audit_dataset(fx.csv, fx.samples)
            drop_missing_labels(fx.csv, report, Path(tmp) / "quarantine.csv")
            prune_orphan_images(audit_dataset(fx.csv, fx.samples, check_duplicates=False))

            depois = audit_dataset(fx.csv, fx.samples)
            self.assertEqual(depois.orphan_images, [])
            self.assertEqual(depois.of_kind("imagem-ausente"), [])
            no_disco = {path.name for path in fx.samples.glob("*.png")}
            no_csv = {name for name, _fen in read_label_rows(fx.csv)}
            self.assertEqual(no_disco, no_csv)
            self.assertEqual(no_disco, {"ok.png"})

    def test_duplicate_share_flags_growth_above_the_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            shared = _board_image(31)
            fx.add("a.png", LEGAL, image=shared)
            fx.add("b.png", LEGAL, image=shared)
            fx.write()

            report = audit_dataset(fx.csv, fx.samples)

            # 1 redundante em 2 utilizaveis = 50%, muito acima do teto.
            self.assertEqual(report.duplicate_count, 1)
            self.assertAlmostEqual(report.duplicate_share, 0.5)
            self.assertTrue(report.duplicates_above_ceiling)

    def test_duplicate_share_is_zero_without_labels(self) -> None:
        # Um CSV sem rotulo utilizavel nao tem excesso de redundancia: tem outro problema.
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.write()
            report = audit_dataset(fx.csv, fx.samples)

            self.assertEqual(report.duplicate_share, 0.0)
            self.assertFalse(report.duplicates_above_ceiling)

    def test_ceiling_is_above_todays_measured_share(self) -> None:
        # O teto e uma guarda contra crescimento, nao uma reprovacao do estado de hoje:
        # 248 redundantes em 3.454 rotulos sao 7,2%.
        self.assertGreater(DUPLICATE_SHARE_CEILING, 248 / 3454)


if __name__ == "__main__":
    unittest.main()


class DedupeSummaryTests(unittest.TestCase):
    """O que o `--dedupe` tirou de cada split, gravado antes de tirar (S-101).

    **O alarme original deste item era falso, e o registro é o que sobra dele.** A primeira
    leitura foi que o dedupe encolheria `val`/`test` "sem consultar o split" e quebraria a
    comparabilidade. A primeira metade é verdade; a segunda não -- `splits.group_keys` mapeia
    cada membro para `sorted(group)[0]`, exatamente o nome que `find_duplicate_groups` mantém,
    então toda linha que sai é cópia de um representante que fica **no mesmo split**.

    O que muda é a contagem, e é ela que faz um número medido depois deixar de ser comparável,
    por denominador, com um medido antes.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture = Fixture(self.tmp.name)
        imagem = _board_image(7)
        for nome in ("a.png", "b.png", "c.png"):
            self.fixture.add(nome, LEGAL, image=imagem)
        self.fixture.add("d.png", LEGAL_OTHER)
        self.fixture.write()

        self.splits = Path(self.tmp.name) / "splits.csv"
        self.splits.write_text(
            "filename,split\na.png,test\nb.png,test\nc.png,test\nd.png,train\n", encoding="utf-8"
        )
        self.report = audit_dataset(self.fixture.csv, self.fixture.samples)

    def test_o_resumo_diz_quanto_cada_split_encolhe(self) -> None:
        resumo = dedupe_summary(self.report, self.splits)

        self.assertEqual(resumo["removed"], 2, "b e c são cópias de a")
        self.assertEqual(resumo["by_split"]["test"], {"antes": 3, "removidos": 2, "depois": 1})
        self.assertEqual(resumo["by_split"]["train"], {"antes": 1, "removidos": 0, "depois": 1})

    def test_o_representante_fica_no_mesmo_split_das_copias(self) -> None:
        """**O número que refuta o alarme original.** Zero grupos atravessam split, e não é
        sorte: é a S-07 funcionando. Fica no arquivo para que a próxima limpeza mostre se
        isso deixou de ser verdade."""
        self.assertEqual(dedupe_summary(self.report, self.splits)["groups_across_splits"], 0)

    def test_grupo_que_atravessa_split_aparece_no_resumo(self) -> None:
        """Se a garantia da S-07 quebrar, o resumo é onde isso fica visível."""
        self.splits.write_text(
            "filename,split\na.png,test\nb.png,train\nc.png,test\nd.png,train\n", encoding="utf-8"
        )
        self.assertEqual(dedupe_summary(self.report, self.splits)["groups_across_splits"], 1)

    def test_linha_sem_split_nao_some_da_conta(self) -> None:
        self.splits.write_text("filename,split\na.png,test\nd.png,train\n", encoding="utf-8")
        resumo = dedupe_summary(self.report, self.splits)
        self.assertEqual(resumo["by_split"]["(sem split)"]["removidos"], 2)

    def test_o_resumo_vai_para_o_disco_com_a_data_no_nome(self) -> None:
        """Em `docs/metrics/`, com o resto do que é número publicado: é o denominador que
        explica por que duas medições da mesma coisa não batem."""
        destino = Path(self.tmp.name) / "metrics"
        caminho = write_dedupe_summary(dedupe_summary(self.report, self.splits), destino, stamp="20260816_2200")

        self.assertEqual(caminho.name, "dedupe_20260816_2200.json")
        gravado = json.loads(caminho.read_text(encoding="utf-8"))
        self.assertEqual(gravado["removed"], 2)
        self.assertEqual(gravado["by_split"]["test"]["depois"], 1)

    def test_o_resumo_e_de_antes_e_confere_com_o_que_saiu(self) -> None:
        """O critério de aceite: a contagem por split bate com o que o `--dedupe` removeu."""
        resumo = dedupe_summary(self.report, self.splits)
        removidos = remove_duplicate_labels(self.fixture.csv, self.report)

        self.assertEqual(removidos, resumo["removed"])
        soma = sum(parcial["removidos"] for parcial in resumo["by_split"].values())
        self.assertEqual(soma, removidos)
