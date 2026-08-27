from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

from chess_diagram_ocr.checkpoint import (
    CHECKPOINT_FORMAT,
    MOTIVO_MAX,
    check_compatible,
    checkpoint_fingerprint,
    checkpoint_identity,
    describe_checkpoint,
    git_commit,
    git_worktree_dirty,
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


class AtomicWriteTests(unittest.TestCase):
    """S-57: o `.pt` é o quarto arquivo que não pode ficar pela metade.

    O `atomic_io` protegia estado da app, fila de revisão e `labels.csv` desde a S-25, e não
    o checkpoint -- que é o maior dos quatro, o mais demorado de escrever, e o único cuja
    escrita acontece numa thread de fundo enquanto outra pode estar lendo o mesmo caminho.
    """

    def test_uma_escrita_interrompida_preserva_o_checkpoint_anterior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.pt"
            save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata(best_epoch=1))
            intacto = path.read_bytes()

            with patch("chess_diagram_ocr.checkpoint.torch.save", side_effect=OSError("disco cheio")):
                with self.assertRaises(OSError):
                    save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata(best_epoch=2))

            self.assertEqual(path.read_bytes(), intacto)
            self.assertEqual(load_checkpoint(path).metadata["best_epoch"], 1)

    def test_nao_sobra_temporario_ao_lado_do_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.pt"
            save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata())
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["m.pt"])


class RevisaoDoCodigoTests(unittest.TestCase):
    """S-324: o commit sozinho mente numa árvore suja.

    O caso é medido: em 2026-08-22 quatro relatórios de campo foram gravados, e um commit
    posterior mudou a detecção o bastante para levar o recall de uma página de 0,800 para
    1,000. Nada nos arquivos mudou, e a guarda da S-100 não pega -- ela compara o
    **conjunto**, e mudança de código não move `pages` nem `annotated`.
    """

    def test_sem_git_o_commit_sai_vazio_e_a_arvore_nao_se_diz_suja(self) -> None:
        """Um `.exe` congelado não tem `.git`. "Não sei" é a resposta, e quem lê a vê no
        commit vazio -- dizer `dirty: true` ali seria inventar um defeito."""
        with patch("chess_diagram_ocr.checkpoint._git", return_value=None):
            self.assertEqual(git_commit(), "")
            self.assertFalse(git_worktree_dirty())

    def test_a_arvore_limpa_e_a_suja_se_distinguem(self) -> None:
        with patch("chess_diagram_ocr.checkpoint._git", return_value="") as limpo:
            self.assertFalse(git_worktree_dirty())
            limpo.assert_called_once()

        with patch("chess_diagram_ocr.checkpoint._git", return_value=" M src/x.py\n"):
            self.assertTrue(git_worktree_dirty())


class CheckpointIdentityTests(unittest.TestCase):
    """S-57: retomar uma exportação depois de treinar não pode misturar dois modelos."""

    def test_regravar_o_mesmo_caminho_muda_a_identidade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.pt"
            save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata(best_epoch=1))
            antes = checkpoint_identity(path)

            # `st_mtime_ns` pode empatar em duas escritas seguidas; o tamanho muda porque os
            # metadados mudam, e é justamente por isso que a identidade usa os dois.
            save_checkpoint(
                path,
                PieceClassifier().state_dict(),
                metadata=_metadata(best_epoch=2, split_hash="outro-split-bem-mais-longo"),
            )

            self.assertNotEqual(checkpoint_identity(path), antes)

    def test_arquivo_ausente_devolve_identidade_vazia(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(checkpoint_identity(Path(tmp) / "nao-existe.pt"), "")


class DescricaoDoCheckpointTests(unittest.TestCase):
    """S-324: um relatório tem de poder dizer **de que modelo** ele é.

    O defeito que isto fecha tem data. Em 2026-08-22 quatro modelos foram medidos sobre as
    mesmas 66 páginas e os quatro JSON de `docs/metrics/` só se distinguiam pelo nome do
    arquivo -- a tabela comparativa dependia de quem gravou ter lembrado o que rodou.
    """

    def test_a_descricao_traz_o_treino_que_produziu_o_arquivo(self) -> None:
        """`best_metric`/`best_epoch` já eram gravados dentro do `.pt` desde a Fase 5. O que
        faltava era alguém lê-los para fora."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.pt"
            save_checkpoint(
                path,
                PieceClassifier().state_dict(),
                metadata=_metadata(best_metric_name="val_board_exact_acc", git_commit="abc1234"),
                temperature=1.25,
            )

            descricao = describe_checkpoint(path)

            self.assertEqual(descricao.best_epoch, 3)
            self.assertAlmostEqual(descricao.best_metric or 0.0, 0.95)
            self.assertEqual(descricao.best_metric_name, "val_board_exact_acc")
            self.assertEqual(descricao.arch_version, ArchConfig().version)
            self.assertEqual(descricao.train_commit, "abc1234")
            self.assertAlmostEqual(descricao.temperature, 1.25)
            self.assertEqual(descricao.unreadable, "")
            self.assertGreater(descricao.size_bytes, 0)

    def test_dois_modelos_no_mesmo_caminho_tem_impressoes_diferentes(self) -> None:
        """**O caso que paga o item.** O treino reescreve sempre o mesmo `.pt`, então o
        caminho é igual nos quatro relatórios e não distingue nada. O conteúdo distingue.

        Metadados **idênticos** de propósito: assim a única diferença entre os dois arquivos
        são os pesos, e o que o teste afirma é que a impressão vê o modelo -- e não o rótulo
        que veio junto com ele."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "piece_classifier.pt"

            torch.manual_seed(1)
            save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata())
            primeiro = describe_checkpoint(path)

            torch.manual_seed(2)
            save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata())
            segundo = describe_checkpoint(path)

            self.assertEqual(primeiro.path, segundo.path)
            self.assertEqual(primeiro.best_epoch, segundo.best_epoch)
            self.assertNotEqual(primeiro.sha256, segundo.sha256)

    def test_o_mesmo_conteudo_em_dois_caminhos_tem_a_mesma_impressao(self) -> None:
        """O outro lado da mesma moeda: renomear um checkpoint não o torna outro modelo."""
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "m.pt"
            save_checkpoint(original, PieceClassifier().state_dict(), metadata=_metadata())
            copia = Path(tmp) / "outro-nome.pt"
            copia.write_bytes(original.read_bytes())

            self.assertEqual(checkpoint_fingerprint(original), checkpoint_fingerprint(copia))
            self.assertNotEqual(describe_checkpoint(original).path, describe_checkpoint(copia).path)

    def test_um_pt_ilegivel_nao_derruba_o_relatorio_e_diz_por_que(self) -> None:
        """Meia identidade vale mais que nenhuma: a impressão e o tamanho ainda identificam o
        arquivo, e o motivo fica escrito no JSON em vez de virar traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nao-e-um-checkpoint.pt"
            path.write_bytes(b"isto nao e um arquivo do torch")

            descricao = describe_checkpoint(path)

            self.assertNotEqual(descricao.sha256, "")
            self.assertGreater(descricao.size_bytes, 0)
            self.assertNotEqual(descricao.unreadable, "")
            self.assertIsNone(descricao.best_metric)
            self.assertIn("unreadable", descricao.as_dict())

    def test_arquivo_ausente_devolve_o_caminho_pedido_e_um_motivo_estavel(self) -> None:
        """A mensagem do sistema vem traduzida pelo locale e carrega o caminho absoluto --
        dois motivos para o mesmo relatório sair diferente em duas máquinas, num campo que
        existe justamente para comparar relatórios."""
        with tempfile.TemporaryDirectory() as tmp:
            descricao = describe_checkpoint(Path(tmp) / "nao-existe.pt")

            self.assertEqual(descricao.unreadable, "arquivo não encontrado")
            self.assertEqual(descricao.sha256, "")
            self.assertEqual(descricao.size_bytes, 0)
            self.assertTrue(descricao.path.endswith("nao-existe.pt"))

    def test_um_checkpoint_pre_fase_5_nao_inventa_metrica(self) -> None:
        """`piece_classifier_baseline.pt` não tem metadados, e continua carregando. Aqui isso
        vira `best_metric = None` -- que é "não sei", e não um número plausível."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legado.pt"
            torch.save(PieceClassifier().state_dict(), path)

            descricao = describe_checkpoint(path)

            self.assertEqual(descricao.unreadable, "")
            self.assertNotEqual(descricao.sha256, "")
            self.assertIsNone(descricao.best_metric)
            self.assertIsNone(descricao.best_epoch)
            self.assertEqual(descricao.arch_version, "")

    def test_um_metadado_torto_tambem_vira_motivo_e_nao_traceback(self) -> None:
        """A promessa é "nunca levanta", e ela vale para o que está **dentro** do `.pt`
        também: um `best_epoch` que não é número não pode derrubar a medição de campo depois
        de ela ter gasto minutos de inferência."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "torto.pt"
            torch.save(
                {"model_state": {"w": torch.zeros(2)}, "metadata": {"best_epoch": "doze"}},
                path,
            )

            descricao = describe_checkpoint(path)

            self.assertNotEqual(descricao.sha256, "")
            self.assertIsNone(descricao.best_epoch)
            self.assertIn("ValueError", descricao.unreadable)

    def test_o_motivo_nao_carrega_um_traceback_inteiro(self) -> None:
        """Estes JSON são versionados; um `except` do `torch` inteiro num campo de texto é
        diff sem informação."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nao-e-um-checkpoint.pt"
            path.write_bytes(b"lixo" * 4096)

            self.assertLessEqual(len(describe_checkpoint(path).unreadable), MOTIVO_MAX)

    def test_o_json_tem_as_mesmas_chaves_com_e_sem_o_arquivo(self) -> None:
        """O uso é comparar quatro arquivos campo a campo; uma chave que some num deles vira
        ruído na comparação. `unreadable` é a exceção, e só aparece quando há o que dizer."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.pt"
            save_checkpoint(path, PieceClassifier().state_dict(), metadata=_metadata())

            presente = describe_checkpoint(path).as_dict()
            ausente = describe_checkpoint(Path(tmp) / "sumiu.pt").as_dict()

            self.assertEqual(set(ausente) - set(presente), {"unreadable"})
            self.assertEqual(set(presente) - set(ausente), set())


if __name__ == "__main__":
    unittest.main()
