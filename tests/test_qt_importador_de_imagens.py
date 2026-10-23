"""A janela *Importar imagens* (`qt/importador_de_imagens.py`) e o botão dela na aba Dataset.

A decisão é de `importacao_de_imagens.py` e está afirmada em `tests/test_importacao_de_imagens.py`.
Aqui ficam as três coisas que só a janela tem: a leitura que volta de outra thread e só vale se o
item ainda for o da tela, a conferência que grava com a rota certa (`ocr-aceito` sem mexer,
`ocr-corrigido` mexendo) e anda para o próximo, e o lote que corre fora da thread da janela.

O modelo é um leitor de mentira: carregar o `.pt` não é o que se testa, e ele não existe no CI.
"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar
from test_importacao_de_imagens import FINAL, INICIAL, diagrama, gravar_png, pasta_do_sigil

from chess_diagram_ocr import importacao_de_imagens as imp
from chess_diagram_ocr.importacao_de_imagens import IMPORTADO_COM_FEN
from chess_diagram_ocr.labels import OCR_ACEITO, OCR_CORRIGIDO
from chess_diagram_ocr.ui.busy import BusyRegistry

if TEM_PYQT:
    from chess_diagram_ocr.qt import importador_de_imagens as qt_imp
    from chess_diagram_ocr.qt import painel_do_dataset as qt_dataset


def linhas_do_csv(caminho: Path) -> list[dict[str, str]]:
    if not caminho.exists():
        return []
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ConferenciaTests(unittest.TestCase):
    def setUp(self) -> None:
        aplicacao()
        self.dados = pasta_temporaria(self)
        self.csv = self.dados / "labels.csv"
        self.janela = qt_imp.JanelaDeImportacao(
            caminhos=lambda: (self.csv, self.dados / "samples", self.dados / "splits.csv"),
            modelo=lambda: Path("nao-existe.pt"),
            leitor=lambda _tabuleiro: FINAL,
            diretorio_dos_lotes=self.dados / "importacao",
        )
        self.addCleanup(descartar, self.janela)

    def abrir(self, pasta: Path, origem: str) -> None:
        self.janela.combo_origem.setCurrentIndex([chave for chave, _ in qt_imp.ORIGENS].index(origem))
        self.assertTrue(self.janela.abrir_pasta(pasta))
        self.janela.aguardar()

    def test_sem_fen_a_proposta_e_a_leitura_e_salvar_sem_mexer_e_ocr_aceito(self) -> None:
        raiz = pasta_temporaria(self) / "soltas"
        gravar_png(raiz / "1.png", diagrama(margem=0))
        gravar_png(raiz / "2.png", diagrama(margem=0))
        self.abrir(raiz, imp.SEM_FEN)

        self.assertEqual(self.janela.tabuleiro.posicao(), FINAL)
        self.assertEqual(self.janela.lbl_posicao.text(), "1 de 2")
        self.assertTrue(self.janela.salvar())

        linhas = linhas_do_csv(self.csv)
        self.assertEqual([linha["corrected_by"] for linha in linhas], [OCR_ACEITO])
        self.assertEqual(linhas[0]["source_pdf"], "soltas: soltas")
        self.assertEqual(self.janela.item_atual().imagem, "2.png", "salvar anda para a próxima")
        self.assertEqual(self.janela.lbl_posicao.text(), "1 de 1")

    def test_mexer_no_tabuleiro_antes_de_salvar_e_ocr_corrigido(self) -> None:
        raiz = pasta_temporaria(self) / "soltas"
        gravar_png(raiz / "1.png", diagrama(margem=0))
        self.abrir(raiz, imp.SEM_FEN)
        self.janela.campo_fen.setText(f"{INICIAL} b - - 0 1")
        self.janela._fen_digitada()

        self.assertTrue(self.janela.salvar())

        (linha,) = linhas_do_csv(self.csv)
        self.assertEqual((linha["fen"], linha["corrected_by"]), (f"{INICIAL} b - - 0 1", OCR_CORRIGIDO))
        self.assertEqual(self.janela.lbl_item.text(), "Nada para conferir neste filtro.")

    def test_pular_descartar_e_o_andamento_sobrevive_a_reabrir(self) -> None:
        raiz = pasta_temporaria(self) / "soltas"
        for nome in ("1", "2", "3"):
            gravar_png(raiz / f"{nome}.png", diagrama(margem=0))
        self.abrir(raiz, imp.SEM_FEN)
        self.janela.pular()
        self.janela.aguardar()
        self.janela.descartar()
        self.janela.aguardar()

        self.assertEqual(self.janela.item_atual().imagem, "3.png")
        self.assertEqual(linhas_do_csv(self.csv), [])

        self.abrir(raiz, imp.SEM_FEN)
        contagem = self.janela.lote.contagem()
        self.assertEqual((contagem[imp.PULADO], contagem[imp.DESCARTADO], contagem[imp.PENDENTE]), (1, 1, 1))

    def test_resposta_de_leitura_de_outro_item_e_ignorada(self) -> None:
        raiz = pasta_temporaria(self) / "soltas"
        gravar_png(raiz / "1.png", diagrama(margem=0))
        gravar_png(raiz / "2.png", diagrama(margem=0))
        self.abrir(raiz, imp.SEM_FEN)
        recorte = self.janela._recorte_atual

        self.janela._chegou_leitura(1, recorte, imp.RECORTE_INTEIRA, INICIAL)

        self.assertEqual(self.janela.tabuleiro.posicao(), FINAL)
        self.assertEqual(self.janela.lote.itens[1].fen_do_modelo, "")

    def test_com_fen_o_lote_grava_os_confirmados_e_a_conferencia_abre_nos_avisos(self) -> None:
        busy = BusyRegistry()
        self.janela._busy = busy
        self.abrir(pasta_do_sigil(self), imp.COM_FEN)
        self.assertEqual(self.janela.filtro(), "aviso", "o relatório já trouxe dois avisos")

        self.assertTrue(self.janela.importar_confirmados())
        self.assertEqual([op.name for op in busy.running()], ["importação de imagens"], "o lote aparece no rodapé")
        self.janela.aguardar()
        self.assertFalse(busy.is_busy, "e sai dele quando acaba")

        self.assertEqual(self.janela.ultimo_resultado["salvos"], 2)
        self.assertEqual({linha["corrected_by"] for linha in linhas_do_csv(self.csv)}, {IMPORTADO_COM_FEN})
        self.assertEqual(self.janela.filtro(), "aviso")
        self.assertEqual(len(self.janela._fila), 3)
        # Na conferência a proposta é a FEN do relatório, e o modelo fica ao lado.
        self.assertEqual(self.janela.tabuleiro.posicao(), INICIAL)
        self.assertIn("34 casas diferentes", self.janela.lbl_leituras.text())
        self.janela.usar_modelo()
        self.assertEqual(self.janela.tabuleiro.posicao(), FINAL)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class BotaoDoDatasetTests(unittest.TestCase):
    def test_o_botao_abre_uma_janela_so_e_fechar_marca_o_dataset_para_reler(self) -> None:
        aplicacao()
        dados = pasta_temporaria(self)
        painel = qt_dataset.PainelDoDataset(
            caminhos=lambda: (dados / "labels.csv", dados / "samples", dados / "splits.csv"),
            em_processo=False,
        )
        self.addCleanup(descartar, painel)

        janela = painel.importar_imagens()
        self.assertIs(painel.importar_imagens(), janela)
        self.assertEqual(janela._diretorio, dados / "importacao")

        painel._stale = False
        janela.amostras_gravadas.emit(3)
        self.assertTrue(painel._stale)
        janela.close()
        self.assertIsNone(painel.importador)


if __name__ == "__main__":
    unittest.main()
