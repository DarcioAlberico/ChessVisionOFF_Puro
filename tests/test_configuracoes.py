"""`ui/configuracoes.py` e `qt/dialogo_de_configuracoes.py`: a janela *Configurações…*.

A metade pura cobra o contrato da tabela contra `settings.Settings` -- todo campo declarado
existe, todo campo do dataclass tem lugar declarado --, e é o que impede uma preferência nova
de nascer sem controle. A metade Qt cobra que a janela leia e devolva um `Settings` fiel, que
*Restaurar padrões* volte à fábrica e que *Salvar* entregue o que está na tela a quem grava.
"""

from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr import settings as preferencias
from chess_diagram_ocr.ui import configuracoes
from chess_diagram_ocr.ui.pedido_de_treino import pedido_de_treino

if TEM_PYQT:
    from chess_diagram_ocr.qt.dialogo_de_configuracoes import DialogoDeConfiguracoes


class TabelaTests(unittest.TestCase):
    """A declaração e o dataclass dizem a mesma coisa."""

    def test_todo_campo_declarado_existe_em_settings(self) -> None:
        padrao = preferencias.Settings()
        for campo in configuracoes.CAMPOS:
            with self.subTest(campo=campo.chave):
                configuracoes.ler(padrao, campo)  # AttributeError se a tabela mentir

    def test_todo_campo_de_settings_tem_lugar_declarado(self) -> None:
        declarados = {campo.chave for campo in configuracoes.CAMPOS} | set(configuracoes.FORA_DA_JANELA)
        existentes = {
            f"{secao.name}.{campo.name}"
            for secao in dataclasses.fields(preferencias.Settings)
            for campo in dataclasses.fields(getattr(preferencias.Settings(), secao.name))
        }
        self.assertEqual(existentes - declarados, set(), "preferência sem lugar na janela")
        self.assertEqual(declarados - existentes, set(), "declaração sem campo no dataclass")

    def test_toda_secao_dos_campos_tem_aba(self) -> None:
        abas = {secao for secao, _titulo in configuracoes.ABAS} | {"local_reader"}
        for campo in configuracoes.CAMPOS:
            self.assertIn(campo.secao, abas, campo.chave)

    def test_trocar_devolve_um_settings_novo_e_nao_toca_no_antigo(self) -> None:
        antigo = preferencias.Settings()
        novo = configuracoes.trocar(antigo, {"training.epochs": 30, "ocr.languages": ("pt",)})
        self.assertEqual(novo.training.epochs, 30)
        self.assertEqual(novo.ocr.languages, ("pt",))
        self.assertEqual(antigo.training.epochs, 8)
        self.assertEqual(novo.engine, antigo.engine)


class TreinoTests(unittest.TestCase):
    """As seções novas viajam pelo arquivo e o pedido de treino as lê."""

    def test_round_trip_e_padroes_de_fabrica(self) -> None:
        caminho = pasta_temporaria(self) / "settings.json"
        gravado = configuracoes.trocar(
            preferencias.Settings(),
            {"training.epochs": 25, "training.ocr_iterations": 4000, "recognition.dpi": 300},
        )
        preferencias.save_settings(caminho, gravado)
        lido = preferencias.load_settings(caminho, env={})
        self.assertEqual(lido.training.epochs, 25)
        self.assertEqual(lido.training.ocr_iterations, 4000)
        self.assertEqual(lido.recognition.dpi, 300)
        # Um arquivo antigo, sem as seções, treina como sempre treinou.
        caminho.write_text(json.dumps({"version": 1, "engine": {"threads": 2}}), encoding="utf-8")
        antigo = preferencias.load_settings(caminho, env={})
        self.assertEqual(antigo.training, preferencias.TrainingSettings())
        self.assertEqual(antigo.recognition, preferencias.RecognitionSettings())
        self.assertEqual(antigo.engine.threads, 2)

    def test_valores_absurdos_caem_na_faixa(self) -> None:
        treino = preferencias.TrainingSettings.from_dict({"epochs": 0, "ocr_negatives": -5})
        self.assertEqual((treino.epochs, treino.ocr_negatives), (1, 0))
        rec = preferencias.RecognitionSettings.from_dict({"dpi": "muito", "max_boards": 999})
        self.assertEqual((rec.dpi, rec.max_boards), (220, 64))

    def test_o_pedido_de_treino_le_o_arquivo(self) -> None:
        caminho = pasta_temporaria(self) / "settings.json"
        preferencias.save_settings(
            caminho, configuracoes.trocar(preferencias.Settings(), {"training.epochs": 3, "training.lr": 0.01})
        )
        original = preferencias.DEFAULT_SETTINGS_PATH
        preferencias.DEFAULT_SETTINGS_PATH = caminho
        try:
            pedido = pedido_de_treino(Path("l.csv"), Path("s"), None, model_path=Path("m.pt"))
            # C4: sem checkpoint legível o regime é o genérico, e o pedido o carrega.
            self.assertEqual(pedido.augment, "aug0")
        finally:
            preferencias.DEFAULT_SETTINGS_PATH = original
        self.assertEqual((pedido.epochs, pedido.lr, pedido.batch_size), (3, 0.01, 16))

    def test_dpi_e_max_boards_releem_quando_o_arquivo_muda(self) -> None:
        caminho = pasta_temporaria(self) / "settings.json"
        preferencias.save_settings(caminho, configuracoes.trocar(preferencias.Settings(), {"recognition.dpi": 150}))
        self.assertEqual(configuracoes.reconhecimento(caminho).dpi, 150)
        preferencias.save_settings(caminho, configuracoes.trocar(preferencias.Settings(), {"recognition.dpi": 400}))
        self.assertEqual(configuracoes.reconhecimento(caminho).dpi, 400)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DialogoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()

    def test_um_controle_nomeado_por_campo_e_uma_aba_por_secao(self) -> None:
        dialogo = DialogoDeConfiguracoes()
        try:
            self.assertEqual(dialogo.abas.count(), len(configuracoes.ABAS))
            for campo in configuracoes.CAMPOS:
                controle = dialogo._controles[campo.chave]
                self.assertEqual(controle.accessibleName(), campo.rotulo, campo.chave)
        finally:
            descartar(dialogo)

    def test_le_e_devolve_o_mesmo_settings(self) -> None:
        entrada = configuracoes.trocar(
            preferencias.Settings(),
            {
                "training.epochs": 12,
                "training.lr": 0.0005,
                "ocr.enabled": True,
                "ocr.engine": "tesseract",
                "ocr.languages": ("pt", "ru"),
                "engine.path": "C:/motores/stockfish.exe",
                "remote_fen.endpoint": "https://exemplo.test/predict",
            },
        )
        dialogo = DialogoDeConfiguracoes(configuracao=entrada)
        try:
            self.assertEqual(dialogo.valores(), entrada)
        finally:
            descartar(dialogo)

    def test_restaurar_padroes_volta_a_fabrica_e_salvar_entrega_a_tela(self) -> None:
        entrada = configuracoes.trocar(preferencias.Settings(), {"training.epochs": 40})
        recebido: list[preferencias.Settings] = []
        dialogo = DialogoDeConfiguracoes(configuracao=entrada, ao_salvar=recebido.append)
        try:
            dialogo.btn_padroes.click()
            self.assertEqual(dialogo.valores().training.epochs, 8)
            dialogo._controles["training.epochs"].setValue(21)
            dialogo.btn_salvar.click()
            self.assertEqual([s.training.epochs for s in recebido], [21])
        finally:
            descartar(dialogo)

    def test_cancelar_nao_grava(self) -> None:
        recebido: list[preferencias.Settings] = []
        dialogo = DialogoDeConfiguracoes(ao_salvar=recebido.append)
        try:
            dialogo._controles["training.epochs"].setValue(99)
            dialogo.btn_cancelar.click()
            self.assertEqual(recebido, [])
        finally:
            descartar(dialogo)


if __name__ == "__main__":
    unittest.main()


class RegimeDeAumentoTests(unittest.TestCase):
    """C4 do ciclo 2: a janela retreina no regime que produziu o checkpoint de produção."""

    def test_o_pedido_le_o_regime_do_checkpoint(self) -> None:
        import tempfile

        import torch

        from chess_diagram_ocr.augment import AugmentConfig, from_letters
        from chess_diagram_ocr.checkpoint import save_checkpoint

        with tempfile.TemporaryDirectory() as tmp:
            modelo = Path(tmp) / "m.pt"
            save_checkpoint(modelo, {"w": torch.zeros(1)}, metadata={"augment_version": "augmhsp"})
            original = preferencias.DEFAULT_SETTINGS_PATH
            preferencias.DEFAULT_SETTINGS_PATH = Path(tmp) / "settings.json"
            try:
                pedido = pedido_de_treino(Path("l.csv"), Path("s"), None, model_path=modelo)
            finally:
                preferencias.DEFAULT_SETTINGS_PATH = original
            self.assertEqual(pedido.augment, "augmhsp")
            self.assertEqual(from_letters(pedido.augment), AugmentConfig(hflip=0.5, hatch=0.30, speckle=0.25, paper=0.30))
