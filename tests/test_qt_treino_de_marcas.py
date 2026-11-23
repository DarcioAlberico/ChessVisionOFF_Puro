"""A janela do modelo de marcas (`qt/treino_de_marcas.py`): congelar, treinar, medir e instalar a pedido.

Um dataset de quatro tabuleiros sintéticos, uma época em CPU: o que se afirma é o caminho -- o teste
congelado ganha a anotação nova, o modelo novo vai para a pasta de experimentos sem tocar no instalado,
a medição põe os leitores na tabela, e instalar guarda o anterior e avisa quem o tinha carregado. O
número que o modelo tira aqui não interessa: quatro tabuleiros não ensinam marca a ninguém.
"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr import teste_de_marcas as tm
from chess_diagram_ocr.atomic_io import write_image

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.janela import JanelaPrincipal

if TEM_PYQT:
    from PyQt6.QtWidgets import QMessageBox

    from chess_diagram_ocr.qt import treino_de_marcas as tdm

FEN = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class JanelaDoModeloDeMarcasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.samples = self.pasta / "samples"
        self.samples.mkdir()
        self.csv = self.pasta / "labels.csv"
        self.splits = self.pasta / "splits.csv"
        tabuleiro = np.full((800, 800, 3), 235, dtype=np.uint8)
        for fila in range(8):
            for coluna in range(8):
                if (fila + coluna) % 2:
                    tabuleiro[fila * 100 : (fila + 1) * 100, coluna * 100 : (coluna + 1) * 100] = 170
        particoes = {"t1.png": "train", "t2.png": "train", "v1.png": "val", "anotada.png": "test"}
        with self.csv.open("w", encoding="utf-8", newline="") as rotulos, self.splits.open(
            "w", encoding="utf-8", newline=""
        ) as divisao:
            escritor, partes = csv.writer(rotulos), csv.writer(divisao)
            escritor.writerow(["filename", "fen"])
            partes.writerow(["filename", "split"])
            for nome, particao in particoes.items():
                write_image(self.samples / nome, tabuleiro)
                escritor.writerow([nome, FEN])
                partes.writerow([nome, particao])
        self.anotacoes = self.pasta / "marcas" / "anotacoes.json"
        mc.ArquivoDeMarcas(self.anotacoes).gravar("k", mc.MarcasDoDiagrama(casas={"c6": mc.X}), amostra="anotada.png")
        self.teste = self.pasta / "marcas" / "teste_congelado.json"
        self.instalado = self.pasta / "models" / "marcas.pt"
        self.janela = tdm.JanelaDoModeloDeMarcas(
            caminhos=lambda: (self.csv, self.samples, self.splits),
            anotacoes=self.anotacoes,
            teste=self.teste,
            modelo_instalado=lambda: self.instalado,
            experimentos=self.pasta / "experimentos",
            amostras_de_alarme=5,
            workers=0,
            tabuleiros_val=None,
        )
        self.addCleanup(descartar, self.janela)
        self.janela.spin_epocas.setValue(1)

    def treinar(self) -> tdm.RodadaDoTreino:
        self.janela.treinar()
        self.assertTrue(self.janela.rodando)
        self.assertFalse(self.janela.btn_treinar.isEnabled(), "dois treinos ao mesmo tempo não")
        self.janela.esperar(120)
        self.app.processEvents()
        self.assertFalse(self.janela.rodando)
        rodada = self.janela.rodada
        assert rodada is not None
        return rodada

    def test_abrir_mostra_o_que_esta_instalado_e_o_teste(self) -> None:
        self.janela.abrir()
        self.assertIn("Nenhum modelo de marcas instalado", self.janela.lbl_situacao.text())
        self.assertIn("Teste congelado: 0 diagrama(s)", self.janela.lbl_situacao.text())

    def test_treinar_congela_treina_fora_do_instalado_e_mede(self) -> None:
        rodada = self.treinar()
        self.assertEqual(rodada.congeladas, 1, rodada.mensagem)
        self.assertEqual([c.amostra for c in tm.ler_teste(self.teste)], ["anotada.png"])
        assert rodada.caminho is not None
        self.assertEqual(rodada.caminho.parent, self.pasta / "experimentos")
        self.assertTrue(rodada.caminho.exists())
        self.assertFalse(self.instalado.exists(), "treinar não instala")
        self.assertEqual(self.janela.tabela.rowCount(), 2, "sem instalado, o novo e o detector")
        self.assertTrue(self.janela.btn_instalar.isEnabled())
        self.assertIn("Teste congelado: 1 diagrama(s)", self.janela.lbl_situacao.text())

    def test_instalar_avisa_e_o_segundo_treino_mede_contra_o_instalado(self) -> None:
        self.treinar()
        instalados: list[str] = []
        self.janela.instalado.connect(instalados.append)
        # A medição em 4 tabuleiros pode dar qualquer coisa: a pergunta, se vier, é respondida "sim".
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.janela.instalar()
        self.assertTrue(self.instalado.exists())
        self.assertEqual(instalados, [str(self.instalado)])
        self.assertFalse(self.janela.btn_instalar.isEnabled())

        self.treinar()
        self.assertEqual(self.janela.tabela.rowCount(), 3, "o novo, o instalado e o detector")

    def test_o_modelo_que_perde_pergunta_antes_e_o_nao_nao_instala(self) -> None:
        self.treinar()
        with mock.patch.object(tdm.md, "em_que_perde", return_value=["aponta 9 diagramas, contra 1"]), mock.patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ) as pergunta:
            self.janela.instalar()
        pergunta.assert_called_once()
        self.assertFalse(self.instalado.exists())

    def test_sem_anotacao_nenhuma_nao_treina(self) -> None:
        self.anotacoes.unlink()
        rodada = self.treinar()
        self.assertIsNone(rodada.caminho)
        self.assertIn("vazio", rodada.mensagem)
        self.assertFalse(self.janela.btn_instalar.isEnabled())

    def test_fechar_esconde_e_o_treino_segue(self) -> None:
        self.janela.abrir()
        self.janela.reject()
        self.assertTrue(self.janela.isHidden())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ComandoTests(unittest.TestCase):
    def test_o_comando_esta_no_catalogo_e_no_menu(self) -> None:
        from chess_diagram_ocr.ui import comandos, menu

        self.assertEqual(comandos.comando("treinar_marcas").rotulo, "Treinar o modelo de marcas…")
        self.assertIn("treinar_marcas", {item.acao for secao in menu.MENUS for item in secao.itens})

    def test_o_comando_abre_a_mesma_janela_e_instalar_esquece_o_modelo_das_leituras(self) -> None:
        from PyQt6.QtWidgets import QWidget

        from chess_diagram_ocr.qt import montagem_da_janela

        class Principal(QWidget):
            """O que `abrir_o_modelo_de_marcas` usa da janela principal, e nada mais."""

            def __init__(self) -> None:
                super().__init__()
                self.busy = None
                self.texto = mock.MagicMock()
                self.dataset = mock.MagicMock()

            def _caminhos_do_dataset(self) -> tuple[Path, Path, Path]:
                return Path("labels.csv"), Path("samples"), Path("splits.csv")

        aplicacao()
        principal = Principal()
        self.addCleanup(descartar, principal)
        janela = cast("JanelaPrincipal", principal)
        with mock.patch.object(tdm.JanelaDoModeloDeMarcas, "abrir") as abrir:
            dialogo = montagem_da_janela.abrir_o_modelo_de_marcas(janela)
            self.assertIs(montagem_da_janela.abrir_o_modelo_de_marcas(janela), dialogo, "a segunda vez reabre a mesma")
        self.assertEqual(abrir.call_count, 2)
        dialogo.instalado.emit("marcas.pt")
        principal.texto.leitor_de_marcas.esquecer.assert_called_once()
        principal.dataset.importador.esquecer_modelo_de_marcas.assert_called_once()


if __name__ == "__main__":
    unittest.main()
