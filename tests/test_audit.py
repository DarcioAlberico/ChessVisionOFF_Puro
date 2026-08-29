from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

# `gravar_imagem` e nao `write_image`: a `Fixture.add` abaixo ja tem um parametro com esse
# nome, e o import sombreado dava `TypeError: 'bool' object is not callable`.
from chess_diagram_ocr.atomic_io import write_image as gravar_imagem
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
from chess_diagram_ocr.cli import audit as cli_audit
from chess_diagram_ocr.cli import train as cli_train
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
            gravar_imagem(self.samples / name, img)
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
            gravar_imagem(fx.samples / "orfa.png", _board_image(99))

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
            gravar_imagem(fx.samples / "orfa.png", _board_image(77))
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

            gravar_imagem(fx.samples / "orfa.png", _board_image(78))
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
        """A FEN é trabalho humano e a imagem é reextraível: apagar a linha inverteria o valor.

        A linha que **fica** não é enfeite: desde a S-321 esta função recusa esvaziar o CSV
        inteiro, porque "faltam todas" não é poda, é um clone sem `data/samples/`. Poda parcial
        é o que ela serve, e é o que este teste mede.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("fica.png", LEGAL)
            fx.add("sumiu.png", LEGAL_OTHER, write_image=False)
            fx.write()
            quarentena = Path(tmp) / "quarantine.csv"

            drop_missing_labels(fx.csv, audit_dataset(fx.csv, fx.samples), quarentena)

            texto = quarentena.read_text(encoding="utf-8")
            self.assertIn("sumiu.png", texto)
            self.assertIn(LEGAL_OTHER, texto)
            self.assertIn("imagem ausente", texto)

    def test_faltando_todas_as_imagens_a_poda_recusa(self) -> None:
        """S-321: num clone novo, `--drop-missing` reduzia o `labels.csv` a um cabeçalho.

        `data/labels.csv` vem versionado com 4.454 linhas e `data/samples/` vem com um
        `.gitkeep`; as imagens são 3,9 GB e ficam fora do git. O `cvoff-train` imprimia
        "conserto: cvoff-audit --drop-missing", e seguir a instrução destruía o único dado que o
        repositório de fato entrega -- sem destravar nada, porque os rótulos utilizáveis
        continuavam zero. Havia backup, o que salvava o arquivo e não a confiança.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("uma.png", LEGAL, write_image=False)
            fx.add("outra.png", LEGAL_OTHER, write_image=False)
            fx.write()
            antes = fx.csv.read_text(encoding="utf-8")

            with self.assertRaises(ValueError) as erro:
                drop_missing_labels(fx.csv, audit_dataset(fx.csv, fx.samples), Path(tmp) / "q.csv")

            self.assertIn("data/samples/", str(erro.exception))
            self.assertEqual(fx.csv.read_text(encoding="utf-8"), antes, "o CSV não foi tocado")

    def test_o_conserto_impresso_muda_quando_faltam_todas(self) -> None:
        """A outra metade: a violação **não pode** mandar rodar o comando que ela recusa."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("uma.png", LEGAL, write_image=False)
            fx.write()

            violacoes = audit_dataset(fx.csv, fx.samples).violations()

            self.assertTrue(any("não vêm no repositório" in linha for linha in violacoes), violacoes)
            self.assertFalse(
                any("conserto: cvoff-audit --drop-missing" in linha for linha in violacoes),
                violacoes,
            )

    def test_the_two_actions_together_leave_the_same_set_of_names(self) -> None:
        """O critério de aceite da S-63, escrito como teste."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.add("sumiu.png", LEGAL_OTHER, write_image=False)
            fx.write()
            gravar_imagem(fx.samples / "orfa.png", _board_image(79))

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


class LimitesDeclaradosTests(unittest.TestCase):
    """A auditoria barra em vez de relatar (S-102).

    `cvoff-audit` saía com código **0** com o teto da S-63 estourado em 11,0% e um rótulo cujo
    PNG sumiu -- *"descartado em silêncio no treino"*, nas palavras do próprio relatório. Nada
    no fluxo a consultava antes de treinar.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture = Fixture(self.tmp.name)

    def _relatorio(self) -> object:
        self.fixture.write()
        return audit_dataset(self.fixture.csv, self.fixture.samples)

    def test_dataset_limpo_nao_tem_violacao(self) -> None:
        self.fixture.add("a.png", LEGAL)
        self.fixture.add("b.png", LEGAL_OTHER)
        self.assertEqual(self._relatorio().violations(), [])

    def test_ilegal_fatal_e_violacao_e_a_mensagem_diz_o_conserto(self) -> None:
        self.fixture.add("a.png", LEGAL)
        self.fixture.add("ruim.png", FATAL_NO_KINGS)
        violacoes = self._relatorio().violations()

        self.assertEqual(len(violacoes), 1)
        self.assertIn("--quarantine", violacoes[0], "uma violação sem conserto ao lado é um beco")

    def test_png_ausente_e_violacao(self) -> None:
        """O caso do dataset de hoje, e o que ele custa: o treino descarta a linha em silêncio."""
        self.fixture.add("a.png", LEGAL)
        self.fixture.add("sumiu.png", LEGAL_OTHER, write_image=False)
        violacoes = self._relatorio().violations()

        self.assertEqual(len(violacoes), 1)
        self.assertIn("--drop-missing", violacoes[0])

    def test_redundancia_acima_do_teto_e_violacao(self) -> None:
        imagem = _board_image(3)
        for nome in ("a.png", "b.png"):
            self.fixture.add(nome, LEGAL, image=imagem)
        violacoes = self._relatorio().violations()

        self.assertEqual(len(violacoes), 1)
        self.assertIn(f"{DUPLICATE_SHARE_CEILING:.0%}", violacoes[0])
        self.assertIn("suba o teto explicitamente", violacoes[0], "o teto não é sagrado; o silêncio é que não serve")

    def test_amostra_sem_split_nao_e_violacao(self) -> None:
        """Quem atribui split é o `cvoff-train`, e ele o faz na linha seguinte (S-56).
        Barrar aqui seria barrar o conserto."""
        self.fixture.add("a.png", LEGAL)
        self.assertEqual(self._relatorio().violations(), [])

    def test_ilegal_confirmada_a_mao_nao_e_violacao(self) -> None:
        """`illegal_ok` é decisão humana registrada (S-70), não defeito -- e o livro desenha
        assim: capítulo de estrutura de peões não tem rei."""
        self.fixture.add("a.png", LEGAL)
        self.fixture.add("estrutura.png", FATAL_NO_KINGS)
        self.fixture.write(illegal_ok={"estrutura.png": ILLEGAL_OK})
        relatorio = audit_dataset(self.fixture.csv, self.fixture.samples)

        self.assertEqual(relatorio.violations(), [])

    def test_a_saida_estrita_e_1_e_a_normal_e_0(self) -> None:
        """**O critério de aceite.** Sem `--strict` o comando é usado para olhar, e quebrar o
        código de saída de quem olha trocaria um problema por outro."""
        self.fixture.add("a.png", LEGAL)
        self.fixture.add("sumiu.png", LEGAL_OTHER, write_image=False)
        self.fixture.write()

        comum = ["--csv", str(self.fixture.csv), "--samples", str(self.fixture.samples), "--skip-duplicates"]
        self.assertEqual(cli_audit.main([*comum, "--strict"]), 1)
        self.assertEqual(cli_audit.main(comum), 0)

    def test_o_rotulo_de_modelo_no_teste_de_caractere_reprova_o_estrito(self) -> None:
        """A S-201 no portão: a base de caractere não é do `labels.csv`, e quem responde "esta
        base pode publicar um número?" é este comando.

        O relatório vem de `cvoff-texto-train --so-split`, porque o split de caractere **não
        existe em disco** -- ele é função pura da semente e é refeito a cada corrida.
        """
        import json

        self.fixture.add("a.png", LEGAL)
        self.fixture.add("b.png", LEGAL_OTHER)
        self.fixture.write()
        vazamento = Path(self.fixture.csv).parent / "texto_vazamento.json"
        vazamento.write_text(
            json.dumps(
                {
                    "grupos_em_dois_lados": 0,
                    "livros_em_dois_lados": 0,
                    "procedencia_por_lado": {"teste": {"humano": 90, "modelo": 10}},
                    "registro_de_procedencia": "100 recorte(s) registrado(s)",
                    "desconhecida_no_teste_permitida": False,
                }
            ),
            encoding="utf-8",
        )

        comum = [
            "--csv", str(self.fixture.csv),
            "--samples", str(self.fixture.samples),
            "--skip-duplicates",
            "--vazamento-de-texto", str(vazamento),
        ]
        self.assertEqual(cli_audit.main([*comum, "--strict"]), 1)
        # Sem `--strict` continua saindo 0, pela mesma regra do teste acima: quem olha, olha.
        self.assertEqual(cli_audit.main(comum), 0)

    def test_estrito_sobre_dataset_limpo_sai_0(self) -> None:
        self.fixture.add("a.png", LEGAL)
        self.fixture.add("b.png", LEGAL_OTHER)
        self.fixture.write()

        codigo = cli_audit.main(
            ["--csv", str(self.fixture.csv), "--samples", str(self.fixture.samples), "--strict", "--skip-duplicates"]
        )
        self.assertEqual(codigo, 0)


class TreinoRecusaDatasetReprovadoTests(unittest.TestCase):
    """`cvoff-train` pergunta à auditoria antes de montar o dataset (S-102)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture = Fixture(self.tmp.name)
        self.fixture.add("a.png", LEGAL)
        self.fixture.add("sumiu.png", LEGAL_OTHER, write_image=False)
        self.fixture.write()

    def _args(self, **extra: object) -> argparse.Namespace:
        base = {
            "csv": self.fixture.csv,
            "samples": self.fixture.samples,
            "force": False,
        }
        base.update(extra)
        return argparse.Namespace(**base)

    def test_recusa_com_codigo_proprio_e_diz_o_conserto(self) -> None:
        self.assertEqual(cli_train._audit_gate(self._args()), 2)

    def test_force_passa_por_cima(self) -> None:
        """Quem sabe o que está fazendo continua podendo treinar -- foi assim que o dataset
        chegou até aqui."""
        self.assertIsNone(cli_train._audit_gate(self._args(force=True)))

    def test_dataset_ausente_nao_e_reprovacao(self) -> None:
        """Num clone limpo o `labels.csv` pode nem existir, e quem reclama disso com mensagem
        melhor é o próprio `train_model`."""
        ausente = Path(self.tmp.name) / "nao_existe.csv"
        self.assertIsNone(cli_train._audit_gate(self._args(csv=ausente)))

    def test_dataset_limpo_libera(self) -> None:
        pasta = Path(self.tmp.name) / "limpo"
        pasta.mkdir()
        limpo = Fixture(str(pasta))
        limpo.add("a.png", LEGAL)
        limpo.add("b.png", LEGAL_OTHER)
        limpo.write()
        self.assertIsNone(cli_train._audit_gate(self._args(csv=limpo.csv, samples=limpo.samples)))
