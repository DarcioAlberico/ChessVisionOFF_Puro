"""`cvoff-eval` diz sobre que partição o número vale (S-103).

`grep split_hash` em `src/` devolvia quatro ocorrências, **todas em `training.py`**: escrito ao
salvar, lido só para decidir se a métrica gravada num checkpoint retomado ainda vale.
`evaluate_split` carregava o `splits.csv` e o checkpoint e não comparava nada.

A S-07 inteira existe para tornar impossível medir num conjunto que o modelo já viu, e o dado
que fecha essa porta estava gravado no arquivo desde a Fase 5, ao alcance de um `if`.

**Aviso e não recusa**, e a distinção é deliberada: comparar um checkpoint antigo é legítimo --
é assim que os números do `BASELINE.md` continuam verificáveis --, e recusar impediria a
própria auditoria histórica. O número sai com a ressalva ao lado, no texto e no JSON.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import torch

from chess_diagram_ocr.checkpoint import save_checkpoint
from chess_diagram_ocr.evaluation import EvaluationReport, split_caveat
from chess_diagram_ocr.splits import splits_hash

PARTICAO = {"a.png": "train", "b.png": "val", "c.png": "test"}
OUTRA_PARTICAO = {"a.png": "val", "b.png": "train", "c.png": "test"}


class RessalvaDeParticaoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)

    def _checkpoint(self, nome: str, metadata: dict[str, object] | None) -> Path:
        caminho = self.raiz / nome
        if metadata is None:
            # O formato anterior a Fase 5: os pesos soltos, sem envelope de metadados.
            torch.save({"peso": torch.zeros(1)}, caminho)
            return caminho
        save_checkpoint(caminho, {"peso": torch.zeros(1)}, metadata=metadata)
        return caminho

    def test_mesma_particao_nao_tem_o_que_ressalvar(self) -> None:
        modelo = self._checkpoint("igual.pt", {"split_hash": splits_hash(PARTICAO)})
        self.assertEqual(split_caveat(modelo, PARTICAO), "")

    def test_outra_particao_diz_os_dois_hashes(self) -> None:
        """Sem os dois números a ressalva seria uma acusação sem prova: quem for conferir
        precisa saber qual `splits.csv` reproduz o checkpoint."""
        modelo = self._checkpoint("outra.pt", {"split_hash": splits_hash(OUTRA_PARTICAO)})
        ressalva = split_caveat(modelo, PARTICAO)

        self.assertIn(splits_hash(OUTRA_PARTICAO), ressalva)
        self.assertIn(splits_hash(PARTICAO), ressalva)
        self.assertIn("outra partição", ressalva)

    def test_split_hash_vazio_e_contaminacao_e_a_palavra_e_essa(self) -> None:
        """`--no-splits` sorteia a validação a cada execução: não existe conjunto reservado, e
        parte do que se está medindo esteve no treino. "Pode estar" seria eufemismo."""
        modelo = self._checkpoint("sem_splits.pt", {"split_hash": "", "arch_version": "cnn-gray-64-linear"})
        ressalva = split_caveat(modelo, PARTICAO)

        self.assertIn("contaminado", ressalva)
        self.assertIn("--no-splits", ressalva)

    def test_checkpoint_legado_diz_que_nao_e_auditavel(self) -> None:
        """`piece_classifier_baseline.pt` é a única forma de reproduzir o BASELINE.md, e por
        isso continua carregando -- mas o número que ele produz não é auditável."""
        modelo = self._checkpoint("legado.pt", None)
        ressalva = split_caveat(modelo, PARTICAO)

        self.assertIn("legado", ressalva)
        self.assertIn("não é auditável", ressalva)

    def test_checkpoint_ausente_nao_inventa_ressalva(self) -> None:
        """Quem falha com mensagem boa sobre arquivo que não existe é o `load_model`, e ele
        roda antes daqui. Uma segunda mensagem pior no meio do relatório só atrapalha."""
        self.assertEqual(split_caveat(self.raiz / "nunca_existiu.pt", PARTICAO), "")

    def test_sem_particao_carregada_nao_ha_com_que_comparar(self) -> None:
        modelo = self._checkpoint("igual.pt", {"split_hash": splits_hash(PARTICAO)})
        self.assertEqual(split_caveat(modelo, {}), "")

    def test_a_ressalva_sai_no_json(self) -> None:
        """**É a metade que impede a contaminação de virar baseline.** Um número copiado do
        JSON para um documento sem a ressalva junto é exatamente como isso acontece."""
        relatorio = EvaluationReport(split="test", model_path=Path("m.pt"), device="cpu")
        relatorio.split_caveat = "o checkpoint foi treinado sobre outra partição"

        self.assertEqual(relatorio.as_dict()["split_caveat"], "o checkpoint foi treinado sobre outra partição")

    def test_sem_ressalva_o_campo_sai_vazio_e_nao_ausente(self) -> None:
        """Chave ausente obrigaria quem lê o JSON a distinguir "não havia ressalva" de "esta
        medição é de antes da S-103" -- e as duas coisas são diferentes."""
        relatorio = EvaluationReport(split="test", model_path=Path("m.pt"), device="cpu")
        self.assertEqual(relatorio.as_dict()["split_caveat"], "")


if __name__ == "__main__":
    unittest.main()
