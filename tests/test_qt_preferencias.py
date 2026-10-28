"""O serviço e o motor que a janela monta a partir das preferências (S-523).

**Sem `QApplication`, e é o item.** As duas funções são a leitura de `data/settings.json` virando os
dois objetos que o pipeline e a sala de estudo recebem prontos; nada aqui precisa de widget. O que
a janela faz com eles -- passar o motor à sala, fechá-lo ao fechar -- está em
`tests/test_qt_janela.py`, que é onde a fiação se mede.

**Nenhum processo é aberto.** `EngineAnalyzer` só abre o binário na primeira análise, e o motor
falso de `tests/fake_uci_engine.py` serve aqui apenas como um caminho que existe no disco.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from chess_diagram_ocr.qt import preferencias
from chess_diagram_ocr.settings import EngineSettings, OcrSettings, Settings

MOTOR_FALSO = Path(__file__).resolve().parent / "fake_uci_engine.py"


class MotorDasPreferenciasTests(unittest.TestCase):
    def test_o_caminho_das_preferencias_vira_motor_sem_abrir_processo(self) -> None:
        """É o único caminho que alcança um binário fora do `PATH` e dos diretórios conhecidos."""
        prefs = Settings(engine=EngineSettings(path=str(MOTOR_FALSO), movetime_ms=250, threads=2))
        motor = preferencias.motor_das_preferencias(prefs, env={})
        assert motor is not None
        self.assertEqual(MOTOR_FALSO, motor.path)
        self.assertEqual(250, motor.movetime_ms)
        # `name` responde o nome do arquivo enquanto o processo não existe: é o que afirma que
        # montar o motor não o abriu.
        self.assertEqual(MOTOR_FALSO.name, motor.name)

    def test_caminho_informado_que_nao_existe_nao_cai_no_path_em_silencio(self) -> None:
        """Quem informou um caminho quer aquele binário; cair no do `PATH` esconderia o erro."""
        prefs = Settings(engine=EngineSettings(path=str(MOTOR_FALSO.with_name("nao-existe.exe"))))
        self.assertIsNone(preferencias.motor_das_preferencias(prefs, env={}))

    def test_sem_caminho_a_procura_e_a_de_find_engine(self) -> None:
        """Caminho vazio é "procure sozinho", e não achar é o caso normal (S-33)."""
        with mock.patch.object(preferencias, "find_engine", return_value=None) as procura:
            self.assertIsNone(preferencias.motor_das_preferencias(Settings(), env={}))
        procura.assert_called_once_with(None, env={})


class ServicoDasPreferenciasTests(unittest.TestCase):
    def test_ocr_desligado_e_o_pipeline_de_sempre(self) -> None:
        """`None` é o padrão do serviço, e o padrão das preferências não liga o OCR de legenda."""
        self.assertIsNone(preferencias.servico_das_preferencias(Settings()).caption_reader)

    def test_o_leitor_que_as_preferencias_autorizam_chega_ao_servico(self) -> None:
        """Quem lê a configuração é a interface; o pipeline recebe pronto o que ela autorizou (S-43)."""
        leitor = object()
        prefs = Settings(ocr=OcrSettings(enabled=True))
        with mock.patch.object(preferencias, "caption_reader_from_settings", return_value=leitor) as monta:
            servico = preferencias.servico_das_preferencias(prefs)
        monta.assert_called_once_with(prefs.ocr)
        self.assertIs(leitor, servico.caption_reader)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
