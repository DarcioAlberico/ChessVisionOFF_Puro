"""A comparação entre duas leituras e o leitor local que a alimenta (S-66)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from chess_diagram_ocr.labels import NET_REMOTO, OCR_ACEITO, SEGUNDA_OPINIAO, label_route
from chess_diagram_ocr.second_opinion import (
    COLLAPSE_DISPUTED,
    SecondOpinion,
    compare,
    disputed_squares,
)
from chess_diagram_ocr.settings import LocalReaderSettings, Settings
from chess_diagram_ocr.tsoj_reader import (
    TsojDiagramReader,
    TsojUnavailableError,
    build_local_provider,
)

VAZIO = "8/8/8/8/8/8/8/8"
UM_REI = "8/8/8/8/8/8/8/K7"
DOIS_REIS = "7k/8/8/8/8/8/8/K7"


class TestDisputedSquares(unittest.TestCase):
    def test_leituras_iguais_nao_tem_casa_em_disputa(self) -> None:
        self.assertEqual(disputed_squares(DOIS_REIS, DOIS_REIS), ())

    def test_indice_em_ordem_de_leitura(self) -> None:
        # a1 e o indice 56 (0 = a8), e h8 e o 7.
        self.assertEqual(disputed_squares(VAZIO, UM_REI), (56,))
        self.assertEqual(disputed_squares(UM_REI, DOIS_REIS), (7,))

    def test_aceita_fen_completa_dos_dois_lados(self) -> None:
        """O leitor externo devolve ` w - - 0 1` grudado; normalizar e papel desta funcao."""
        self.assertEqual(disputed_squares(f"{UM_REI} w - - 0 1", UM_REI), ())
        self.assertEqual(disputed_squares(UM_REI, f"{DOIS_REIS} b - - 3 9"), (7,))

    def test_cor_diferente_na_mesma_casa_conta_como_disputa(self) -> None:
        """Foi o erro mais comum do modelo local no Niemeijer: dama branca lida como preta."""
        self.assertEqual(disputed_squares("Q7/8/8/8/8/8/8/8", "q7/8/8/8/8/8/8/8"), (0,))

    def test_fen_com_filas_de_menos_e_recusada(self) -> None:
        with self.assertRaises(ValueError):
            disputed_squares(VAZIO, "8/8/8")


class TestSecondOpinion(unittest.TestCase):
    def test_concordancia_total(self) -> None:
        parecer = compare(DOIS_REIS, DOIS_REIS, reader="leitor")
        self.assertEqual(parecer.disputed, ())
        self.assertEqual(parecer.agreement, 1.0)
        self.assertFalse(parecer.collapsed)
        self.assertIn("64 casas batem", parecer.describe())

    def test_guarda_as_duas_leituras_separadas(self) -> None:
        """A leitura de base nao pode ser perdida: e o que o modelo principal produziu."""
        parecer = compare(UM_REI, f"{DOIS_REIS} w - - 0 1", reader="leitor")
        self.assertEqual(parecer.baseline, UM_REI)
        self.assertEqual(parecer.placement, DOIS_REIS)

    def test_poucas_casas_sao_nomeadas(self) -> None:
        parecer = compare(UM_REI, DOIS_REIS, reader="leitor")
        self.assertEqual(parecer.disputed_names, ("h8",))
        self.assertIn("h8", parecer.describe())
        self.assertIn("Confira só elas", parecer.describe())

    def test_desabamento_nao_lista_as_casas(self) -> None:
        """Uma lista de 41 casas nao e informacao, e ruido -- ver COLLAPSE_DISPUTED."""
        muitas = tuple(range(COLLAPSE_DISPUTED + 1))
        parecer = SecondOpinion(placement=VAZIO, baseline=VAZIO, reader="leitor", disputed=muitas)
        self.assertTrue(parecer.collapsed)
        self.assertIn("posição inteira", parecer.describe())
        self.assertNotIn("a8", parecer.describe())

    def test_limiar_de_desabamento_e_exclusivo(self) -> None:
        no_limite = SecondOpinion(VAZIO, VAZIO, "leitor", tuple(range(COLLAPSE_DISPUTED)))
        self.assertFalse(no_limite.collapsed)

    def test_agreement_conta_sobre_64(self) -> None:
        parecer = SecondOpinion(VAZIO, VAZIO, "leitor", (0, 1, 2, 3))
        self.assertAlmostEqual(parecer.agreement, 60 / 64)


class TestLabelRoute(unittest.TestCase):
    def test_segunda_opiniao_tem_valor_proprio(self) -> None:
        self.assertEqual(label_route(from_second_opinion=True), SEGUNDA_OPINIAO)

    def test_net_remoto_vence_a_segunda_opiniao(self) -> None:
        """Se a imagem chegou a sair da maquina, e isso que a linha precisa registrar."""
        self.assertEqual(label_route(from_net=True, from_second_opinion=True), NET_REMOTO)

    def test_sem_declaracao_a_regra_antiga_continua(self) -> None:
        self.assertEqual(label_route(read_placement=VAZIO, saved_placement=VAZIO), OCR_ACEITO)


class TestLocalReaderSettings(unittest.TestCase):
    def test_padrao_nao_usa_nada(self) -> None:
        configuracao = LocalReaderSettings()
        self.assertFalse(configuracao.is_usable)
        self.assertIsNone(build_local_provider(configuracao))

    def test_ligado_sem_caminho_nao_e_usavel(self) -> None:
        self.assertFalse(LocalReaderSettings(enabled=True).is_usable)

    def test_caminho_sem_ligar_nao_e_usavel(self) -> None:
        self.assertFalse(LocalReaderSettings(path="/algum/clone").is_usable)

    def test_motivo_distingue_nao_configurado_de_desligado(self) -> None:
        self.assertIn("não configurada", LocalReaderSettings().disabled_reason())
        desligado = LocalReaderSettings(path="/clone").disabled_reason()
        self.assertIn("desligada", desligado)
        self.assertIn("/clone", desligado)
        self.assertEqual(LocalReaderSettings(enabled=True, path="/clone").disabled_reason(), "")

    def test_sobrevive_a_ida_e_volta_pelo_json(self) -> None:
        original = Settings(local_reader=LocalReaderSettings(enabled=True, path="/clone"))
        self.assertEqual(Settings.from_dict(original.to_dict()), original)

    def test_secao_ausente_cai_no_padrao_desligado(self) -> None:
        self.assertFalse(Settings.from_dict({}).local_reader.is_usable)


class TestTsojReader(unittest.TestCase):
    def test_caminho_sem_clone_explica_o_que_falta(self) -> None:
        leitor = TsojDiagramReader(Path(__file__).parent / "nao-existe")
        with self.assertRaises(TsojUnavailableError) as capturado:
            leitor.predict(np.zeros((32, 32, 3), dtype=np.uint8))
        self.assertIn("download_models.sh", str(capturado.exception))

    def test_clone_sem_pesos_diz_isso_e_nao_outra_coisa(self) -> None:
        with mock.patch.object(Path, "is_file", return_value=True), mock.patch.object(Path, "is_dir", return_value=False):
            leitor = TsojDiagramReader(Path("/clone"))
            with self.assertRaises(TsojUnavailableError) as capturado:
                leitor.predict(np.zeros((32, 32, 3), dtype=np.uint8))
        self.assertIn("os pesos não foram", str(capturado.exception))

    def test_imagem_que_nao_e_rgb_e_recusada_antes_de_carregar_peso(self) -> None:
        """A checagem vem antes do import: 232,8 MiB nao devem ser lidos para depois recusar."""
        leitor = TsojDiagramReader(Path("/clone"))
        with self.assertRaises(ValueError):
            leitor.predict(np.zeros((32, 32), dtype=np.uint8))

    def test_nao_importa_o_leitor_ao_importar_este_projeto(self) -> None:
        """O adaptador e preguicoso: importar `tsoj_reader` nao pode puxar torch de terceiro."""
        self.assertNotIn("chess_diagram_to_fen", sys.modules)


if __name__ == "__main__":
    unittest.main()
