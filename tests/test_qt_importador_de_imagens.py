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
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar
from test_importacao_de_imagens import FINAL, INICIAL, diagrama, gravar_png, pasta_do_sigil

from chess_diagram_ocr import importacao_de_imagens as imp
from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr.importacao_de_imagens import IMPORTADO_COM_FEN
from chess_diagram_ocr.labels import OCR_ACEITO, OCR_CORRIGIDO
from chess_diagram_ocr.ui.busy import BusyRegistry

if TEM_PYQT:
    from chess_diagram_ocr.qt import importador_de_imagens as qt_imp
    from chess_diagram_ocr.qt import painel_do_dataset as qt_dataset


C5 = 26
"""A casa da estrela desenhada em `com_estrela`."""

E6 = 20
"""A casa do rei preto em `FINAL`, que é o que o leitor de mentira lê: uma casa com peça."""


def linhas_do_csv(caminho: Path) -> list[dict[str, str]]:
    if not caminho.exists():
        return []
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MarcasNaConferenciaTests(unittest.TestCase):
    """As marcas na conferência: gravam sozinhas, ficam fora do dataset de peças e se reencontram."""

    def setUp(self) -> None:
        aplicacao()
        self.dados = pasta_temporaria(self)
        self.csv = self.dados / "labels.csv"
        self.arquivo = self.dados / "marcas" / "anotacoes.json"
        self.janela = self.nova_janela()
        self.raiz = pasta_temporaria(self) / "soltas"
        gravar_png(self.raiz / "1.png", diagrama(margem=0))
        gravar_png(self.raiz / "2.png", diagrama(margem=0, casa=31))  # outro conteúdo: outra chave

    def nova_janela(self) -> qt_imp.JanelaDeImportacao:
        janela = qt_imp.JanelaDeImportacao(
            caminhos=lambda: (self.csv, self.dados / "samples", self.dados / "splits.csv"),
            modelo=lambda: Path("nao-existe.pt"),
            leitor=lambda _tabuleiro: FINAL,
            diretorio_dos_lotes=self.dados / "importacao",
            arquivo_de_marcas=self.arquivo,
        )
        self.addCleanup(descartar, janela)
        return janela

    def abrir(self, janela: qt_imp.JanelaDeImportacao, pasta: Path) -> None:
        janela.combo_origem.setCurrentIndex([chave for chave, _ in qt_imp.ORIGENS].index(imp.SEM_FEN))
        self.assertTrue(janela.abrir_pasta(pasta))
        janela.aguardar()

    def clicar_casa(self, janela: qt_imp.JanelaDeImportacao, indice: int) -> None:
        from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        tabuleiro = janela.tabuleiro
        linha, coluna = tabuleiro.modelo.display_from_index(indice)
        x0, y0, x1, y1 = tabuleiro.geometria().rect(linha, coluna)
        ponto = QPointF(QPoint(int((x0 + x1) / 2), int((y0 + y1) / 2)))
        botao = Qt.MouseButton.LeftButton
        for tipo, metodo in (
            (QEvent.Type.MouseButtonPress, tabuleiro.mousePressEvent),
            (QEvent.Type.MouseButtonRelease, tabuleiro.mouseReleaseEvent),
        ):
            metodo(QMouseEvent(tipo, ponto, botao, botao, Qt.KeyboardModifier.NoModifier))

    def anotar(self, janela: qt_imp.JanelaDeImportacao, tipo: str, indice: int) -> None:
        janela.paleta_de_marcas.escolher(tipo)
        self.clicar_casa(janela, indice)

    def test_a_anotacao_grava_na_hora_com_o_nome_da_imagem(self) -> None:
        self.abrir(self.janela, self.raiz)
        self.anotar(self.janela, mc.ESTRELA_PRETA, 0)

        relido = mc.ArquivoDeMarcas(self.arquivo)
        chave = mc.chave_da_imagem(self.raiz / "1.png")
        self.assertEqual(relido.marcas_de(chave).casas, {"a8": mc.ESTRELA_PRETA})
        entrada = relido.entrada(chave)
        assert entrada is not None
        self.assertTrue(entrada["imagem"].endswith("1.png"))
        self.assertEqual(entrada["recorte"], self.janela._recorte_usado)
        self.assertIn("estrela preta em a8", self.janela.lbl_marcas.text())
        self.assertEqual(linhas_do_csv(self.csv), [], "anotar não grava no dataset")

    def test_a_marca_nao_entra_na_fen_gravada_e_o_salvar_liga_a_amostra(self) -> None:
        self.abrir(self.janela, self.raiz)
        chave = mc.chave_da_imagem(self.raiz / "1.png")
        self.anotar(self.janela, mc.BOLINHA_BRANCA, 0)
        campo = self.janela.tabuleiro.posicao()

        self.assertTrue(self.janela.salvar())

        (linha,) = linhas_do_csv(self.csv)
        self.assertEqual(linha["fen"].split()[0], campo)
        self.assertNotIn(mc.BOLINHA_BRANCA, str(linha))
        entrada = mc.ArquivoDeMarcas(self.arquivo).entrada(chave)
        assert entrada is not None
        self.assertEqual(Path(entrada["amostra"]).suffix, ".png")
        self.assertTrue((self.dados / "samples" / entrada["amostra"]).is_file())

    def test_a_marca_troca_com_a_imagem_e_volta_ao_voltar(self) -> None:
        self.abrir(self.janela, self.raiz)
        self.anotar(self.janela, mc.X, 0)
        self.janela.andar(1)
        self.janela.aguardar()
        self.assertTrue(self.janela.tabuleiro.marcas().vazia)
        self.assertEqual(self.janela.lbl_marcas.text(), "")

        self.janela.andar(-1)
        self.janela.aguardar()
        self.assertEqual(self.janela.tabuleiro.marcas().casas, {"a8": mc.X})

    def test_a_marca_sobrevive_a_outra_janela_e_acha_a_mesma_imagem_em_outra_pasta(self) -> None:
        self.abrir(self.janela, self.raiz)
        self.anotar(self.janela, mc.ESTRELA_BRANCA, 0)

        outra_pasta = pasta_temporaria(self) / "copia"
        outra_pasta.mkdir()
        (outra_pasta / "qualquer.png").write_bytes((self.raiz / "1.png").read_bytes())
        outra = self.nova_janela()
        self.abrir(outra, outra_pasta)

        self.assertEqual(outra.tabuleiro.marcas().casas, {"a8": mc.ESTRELA_BRANCA})

    def test_a_leitura_do_modelo_nao_devolve_peca_a_casa_marcada(self) -> None:
        self.abrir(self.janela, self.raiz)
        self.assertEqual(self.janela.tabuleiro.modelo.squares()[E6], "k", "o leitor de mentira põe um rei em e6")
        self.anotar(self.janela, mc.ESTRELA_PRETA, E6)

        outra = self.nova_janela()
        self.abrir(outra, self.raiz)

        self.assertEqual(outra.tabuleiro.marcas().casas, {"e6": mc.ESTRELA_PRETA})
        self.assertEqual(outra.tabuleiro.modelo.squares()[E6], "", "o modelo lê peça, mas a casa está marcada")

    def test_item_ja_salvo_pode_ser_anotado_e_liga_a_amostra_dele(self) -> None:
        self.abrir(self.janela, self.raiz)
        self.assertTrue(self.janela.salvar())
        amostra = self.janela.lote.itens[0].amostra
        self.janela.combo_filtro.setCurrentIndex([chave for chave, _ in qt_imp.FILTROS].index("todas"))
        self.janela.aguardar()
        self.janela.andar(-1)
        self.janela.aguardar()
        self.assertEqual(self.janela.item_atual().status, imp.SALVO)
        self.assertTrue(self.janela.paleta_de_marcas._botoes[mc.X].isEnabled())

        self.anotar(self.janela, mc.X, 0)

        entrada = mc.ArquivoDeMarcas(self.arquivo).entrada(mc.chave_da_imagem(self.raiz / "1.png"))
        assert entrada is not None
        self.assertEqual(entrada["amostra"], amostra)
        self.assertEqual(len(linhas_do_csv(self.csv)), 1, "anotar não regrava a amostra")

    def test_o_recorte_mostra_as_marcas_por_cima(self) -> None:
        self.abrir(self.janela, self.raiz)
        antes = self.janela.img_recorte.pixmap().toImage()
        self.anotar(self.janela, mc.ESTRELA_PRETA, 36)
        self.assertNotEqual(antes, self.janela.img_recorte.pixmap().toImage())
        self.clicar_casa(self.janela, 36)
        self.assertEqual(antes, self.janela.img_recorte.pixmap().toImage(), "tirar a marca devolve o recorte")

    def com_estrela(self) -> Path:
        """Uma pasta em que o detector vê uma estrela em c5 na primeira imagem, e nada na segunda.

        O detector é uma resposta fixa aqui: o que ele acha é de `tests/test_detector_de_marcas.py`, e
        o que se afirma nesta classe é o caminho da sugestão até a tela e o arquivo.
        """
        raiz = pasta_temporaria(self) / "com-estrela"
        gravar_png(raiz / "1.png", diagrama(margem=0))
        gravar_png(raiz / "2.png", diagrama(margem=0, casa=31))
        referencia, _ = imp.recortar(imp.ler_imagem(raiz / "1.png"))

        def sugerir(tabuleiro: np.ndarray) -> mc.MarcasDoDiagrama:
            casas = {"c5": mc.ESTRELA_PRETA} if np.array_equal(tabuleiro, referencia) else {}
            return mc.MarcasDoDiagrama(casas=casas)

        remendo = mock.patch.object(qt_imp.detector_de_marcas, "sugerir_marcas", sugerir)
        remendo.start()
        self.addCleanup(remendo.stop)
        return raiz

    def test_a_sugestao_aparece_e_nao_e_anotacao_ate_aceitar(self) -> None:
        raiz = self.com_estrela()
        self.abrir(self.janela, raiz)

        self.assertEqual(self.janela.tabuleiro.sugestao_pendente(), {"c5": mc.ESTRELA_PRETA})
        self.assertIn("estrela preta em c5", self.janela.lbl_sugestao.text())
        self.assertFalse(self.janela.btn_sugestao.isHidden())
        self.assertTrue(self.janela.tabuleiro.marcas().vazia, "sugerir não é anotar")
        self.assertFalse(self.arquivo.exists(), "sugerir não grava nada")

        self.janela.aceitar_sugestao()

        self.assertEqual(self.janela.tabuleiro.marcas().casas, {"c5": mc.ESTRELA_PRETA})
        self.assertEqual(self.janela.tabuleiro.sugestao_pendente(), {})
        self.assertEqual(self.janela.lbl_sugestao.text(), "")
        self.assertTrue(self.janela.btn_sugestao.isHidden())
        relido = mc.ArquivoDeMarcas(self.arquivo)
        self.assertEqual(relido.marcas_de(mc.chave_da_imagem(raiz / "1.png")).casas, {"c5": mc.ESTRELA_PRETA})

    def test_a_sugestao_nao_muda_a_posicao_ate_aceitar(self) -> None:
        raiz = self.com_estrela()
        leituras = {"com-peca": "8/8/8/2P5/8/8/8/8"}
        self.janela._leitor = lambda _tabuleiro: leituras["com-peca"]
        self.abrir(self.janela, raiz)
        self.assertEqual(self.janela.tabuleiro.modelo.squares()[C5], "P", "o modelo leu a estrela como peão")
        self.assertEqual(self.janela.tabuleiro.sugestao_pendente(), {"c5": mc.ESTRELA_PRETA})

        self.janela.aceitar_sugestao()

        self.assertEqual(self.janela.tabuleiro.modelo.squares()[C5], "", "aceitar segue a opção de esvaziar")

    def test_a_sugestao_troca_com_a_imagem(self) -> None:
        self.abrir(self.janela, self.com_estrela())
        self.janela.andar(1)
        self.janela.aguardar()
        self.assertEqual(self.janela.tabuleiro.sugestao_pendente(), {})
        self.assertEqual(self.janela.lbl_sugestao.text(), "")

        self.janela.andar(-1)
        self.janela.aguardar()
        self.assertEqual(self.janela.tabuleiro.sugestao_pendente(), {"c5": mc.ESTRELA_PRETA})

    def test_sugestao_de_outra_imagem_e_ignorada(self) -> None:
        self.abrir(self.janela, self.raiz)
        self.janela._chegou_sugestao(1, {"a1": mc.X})
        self.assertEqual(self.janela.tabuleiro.sugestao_pendente(), {})

    def test_anotacao_a_mao_tem_precedencia_sobre_a_sugestao(self) -> None:
        self.abrir(self.janela, self.com_estrela())
        self.anotar(self.janela, mc.X, C5)
        self.assertEqual(self.janela.tabuleiro.sugestao_pendente(), {}, "a casa já foi resolvida à mão")
        self.janela.aceitar_sugestao()
        self.assertEqual(self.janela.tabuleiro.marcas().casas, {"c5": mc.X})

    def test_sem_arquivo_de_marcas_aceitar_nao_faz_nada(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text("{ estragado", encoding="utf-8")
        janela = self.nova_janela()
        self.abrir(janela, self.com_estrela())
        janela.aceitar_sugestao()
        self.assertTrue(janela.tabuleiro.marcas().vazia)
        self.assertEqual(self.arquivo.read_text(encoding="utf-8"), "{ estragado")

    def test_so_uma_das_paletas_tem_algo_na_mao(self) -> None:
        self.abrir(self.janela, self.raiz)
        self.janela.paleta.escolher("Q")
        self.janela.paleta_de_marcas.escolher(mc.X)
        self.assertIsNone(self.janela.paleta.escolhido)
        self.assertIsNone(self.janela.tabuleiro.modelo.brush)
        self.assertEqual(self.janela.tabuleiro.ferramenta(), mc.X)

        self.janela.paleta.escolher("Q")
        self.assertIsNone(self.janela.paleta_de_marcas.escolhido)
        self.assertIsNone(self.janela.tabuleiro.ferramenta())
        self.assertEqual(self.janela.tabuleiro.modelo.brush, "Q")

    def test_a_opcao_de_esvaziar_chega_ao_tabuleiro(self) -> None:
        self.abrir(self.janela, self.raiz)
        campo = self.janela.tabuleiro.posicao()
        self.janela.chk_esvaziar.setChecked(False)
        self.anotar(self.janela, mc.X, E6)
        self.assertEqual(self.janela.tabuleiro.posicao(), campo)

    def test_marcar_esvazia_a_casa_e_a_fen_da_tela_acompanha(self) -> None:
        self.abrir(self.janela, self.raiz)
        self.anotar(self.janela, mc.X, E6)
        self.assertEqual(self.janela.tabuleiro.posicao(), "8/8/8/8/8/4K3/8/8")
        self.assertTrue(self.janela.campo_fen.text().startswith("8/8/8/8/8/4K3/8/8 "))

    def test_sem_item_a_paleta_fica_apagada(self) -> None:
        self.assertFalse(self.janela.paleta_de_marcas._botoes[mc.X].isEnabled())

    def test_arquivo_estragado_desliga_a_paleta_e_nao_e_tocado(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text("{ estragado", encoding="utf-8")
        janela = self.nova_janela()
        self.abrir(janela, self.raiz)

        self.assertFalse(janela.paleta_de_marcas._botoes[mc.X].isEnabled())
        self.assertIn("ilegível", janela.paleta_de_marcas._botoes[mc.X].toolTip())
        self.assertTrue(janela.salvar(), "a conferência de peças continua")
        self.assertEqual(self.arquivo.read_text(encoding="utf-8"), "{ estragado")

    def test_arquivo_que_estraga_com_a_janela_aberta_vira_aviso(self) -> None:
        self.abrir(self.janela, self.raiz)
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text("{ estragou", encoding="utf-8")

        self.anotar(self.janela, mc.X, 0)

        self.assertIn("não foram gravadas", self.janela.lbl_aviso.text())
        self.assertEqual(self.arquivo.read_text(encoding="utf-8"), "{ estragou")


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
