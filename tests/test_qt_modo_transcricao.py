"""A fiação do modo transcrição (S-703): o efeito na tela e no arquivo, e nunca "o método foi chamado". Sem PDF nem motor: `abrir_folha` é trocado."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import ouro, prata, scan_ouro
from chess_diagram_ocr.text import transcricao_scan as ts
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt.modo_transcricao import ModoTranscricao
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto
    from chess_diagram_ocr.ui import comandos, fita_do_texto, menu, strings, texto_declarado
    from chess_diagram_ocr.ui.state import AppState, state_from_dict

_SHA_FOLHA = "b" * 16
_CAIXAS = ((10.0, 10.0, 200.0, 30.0), (10.0, 50.0, 200.0, 70.0))
_ID = "aaaaaaaaaaaaaaaa"


def _aberta(*_a, **_k) -> ts.FolhaAberta:
    return ts.FolhaAberta(np.full((100, 300, 3), 200, np.uint8), _CAIXAS, ("camada um", "camada dois"), "a" * 16, _SHA_FOLHA)


def _manifesto() -> scan_ouro.ScanOuro:
    folhas = (
        scan_ouro.FolhaDoScanOuro(_ID, 1, "eng", prata.ATE_150, ouro.MISTO, scan_ouro.DEV, True, _SHA_FOLHA),
        scan_ouro.FolhaDoScanOuro(_ID, 2, "eng", prata.ATE_150, ouro.PROSA, scan_ouro.DEV, False, _SHA_FOLHA),
    )
    return scan_ouro.ScanOuro(scan_ouro.VERSAO, "2026-11-06", None, (scan_ouro.LivroDoScanOuro(_ID, scan_ouro.DEV, "eng", prata.ATE_150),), folhas)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ModoTests(unittest.TestCase):
    def setUp(self) -> None:
        aplicacao()
        self.pasta = pasta_temporaria(self)
        self.backup = pasta_temporaria(self)
        self.hora = [100.0]
        patcher = mock.patch.object(ts, "abrir_folha", side_effect=_aberta)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.modo = ModoTranscricao(manifesto=_manifesto(), escolher_pasta=lambda _p, _t: "", agora=lambda: self.hora[0])
        self.addCleanup(descartar, self.modo)
        self.modo._achados = {_ID: Path("x.pdf")}  # noqa: SLF001
        ts.declarar_backup(self.pasta, self.backup)
        self.modo.definir_pasta(self.pasta)

    def _digitar(self, *textos: str) -> None:
        for linha, texto in zip(self.modo.linhas, textos, strict=False):
            linha.campo.setText(texto)
            linha.campo.textEdited.emit(texto)

    def _dados(self, passada: int) -> list[dict]:
        linhas = ts.caminho_da_passada(self.pasta, passada).read_text(encoding="utf-8").splitlines()
        return [json.loads(x) for x in linhas]

    def test_a_folha_abre_com_uma_faixa_ao_lado_de_cada_linha_e_vazia(self) -> None:
        self.assertTrue(self.modo.abrir(_ID, 1))
        self.assertEqual(2, len(self.modo.linhas))
        for linha in self.modo.linhas:
            self.assertFalse(linha.faixa.pixmap().isNull())
            self.assertEqual("", linha.campo.text())

    def test_a_partida_da_camada_enche_os_campos(self) -> None:
        self.modo.escolha_de_partida.setCurrentIndex(self.modo.escolha_de_partida.findData(ts.CAMADA))
        self.modo.abrir(_ID, 1)
        self.assertEqual(["camada um", "camada dois"], [x.campo.text() for x in self.modo.linhas])
        self._digitar("corrigida um")
        self.modo.concluir()
        self.assertEqual("camada", self._dados(1)[-1]["partida"])

    def test_concluir_grava_a_procedencia_e_os_shas(self) -> None:
        self.modo.abrir(_ID, 1)
        self._digitar("primeira", "segunda")
        self.modo.botao_de_concluir.click()
        dados = self._dados(1)[-1]
        self.assertEqual(["primeira", "segunda"], dados["linhas"])
        self.assertEqual("transcricao:1", dados["procedencia"])
        self.assertEqual(("a" * 16, _SHA_FOLHA), (dados["sha_imagem"], dados["sha_folha"]))
        self.assertTrue(dados["completa"])

    def test_a_segunda_passada_nao_abre_a_primeira(self) -> None:
        self.modo.abrir(_ID, 1)
        self._digitar("digitada na primeira", "outra")
        self.modo.concluir()
        self.modo.escolha_de_passada.setCurrentIndex(self.modo.escolha_de_passada.findData(2))
        self.assertEqual([], self.modo.linhas, "a troca de passada tira da tela o que estava digitado")
        self.modo.abrir(_ID, 1)
        self.assertEqual(["", ""], [x.campo.text() for x in self.modo.linhas])
        self.assertEqual([ts.VAZIO], [self.modo.escolha_de_partida.itemData(i) for i in range(self.modo.escolha_de_partida.count())])

    def test_voltar_a_primeira_reabre_o_dela(self) -> None:
        self.modo.abrir(_ID, 1)
        self._digitar("digitada", "")
        self.modo.concluir()
        self.modo.escolha_de_passada.setCurrentIndex(self.modo.escolha_de_passada.findData(2))
        self.modo.escolha_de_passada.setCurrentIndex(self.modo.escolha_de_passada.findData(1))
        self.modo.abrir(_ID, 1)
        self.assertEqual("digitada", self.modo.linhas[0].campo.text())

    def test_a_segunda_passada_so_lista_as_duplas(self) -> None:
        self.modo.escolha_de_passada.setCurrentIndex(self.modo.escolha_de_passada.findData(2))
        self.assertEqual(1, self.modo.escolha_de_folha.count())
        self.assertFalse(self.modo.abrir(_ID, 2))
        self.assertEqual(strings.TRANSCRICAO_FORA_DA_PASSADA, self.modo.frase.text())

    def test_trocar_de_folha_guarda_o_rascunho_sem_concluir(self) -> None:
        self.modo.abrir(_ID, 1)
        self._digitar("pela metade")
        self.modo.abrir(_ID, 2)
        dados = self._dados(1)[-1]
        self.assertEqual("pela metade", dados["linhas"][0])
        self.assertFalse(dados["completa"])
        self.modo.abrir(_ID, 1)
        self.assertEqual("pela metade", self.modo.linhas[0].campo.text())

    def test_sem_backup_trocar_de_folha_nao_apaga_o_digitado(self) -> None:
        self.modo.definir_pasta(pasta_temporaria(self))
        self.modo.abrir(_ID, 1)
        self._digitar("horas de trabalho")
        self.assertFalse(self.modo.abrir(_ID, 2))
        self.assertEqual("horas de trabalho", self.modo.linhas[0].campo.text())
        self.assertEqual(1, self.modo._folha.folha)  # noqa: SLF001
        self.assertIn("não foi gravado", self.modo.frase.text())

    def test_com_disco_cheio_a_frase_nao_diz_em_dia(self) -> None:
        self.modo.abrir(_ID, 1)
        self._digitar("horas de trabalho")
        with mock.patch.object(ts.os, "fsync", side_effect=OSError(28, "disco cheio")):
            self.assertFalse(self.modo.abrir(_ID, 2))
        self.assertEqual("horas de trabalho", self.modo.linhas[0].campo.text())
        self.assertIn("disco cheio", self.modo.frase.text())
        self.assertNotIn(strings.TRANSCRICAO_BACKUPS["em_dia"], self.modo.frase.text())
        self.assertTrue(self.modo.guardar(), "o disco voltou, e o digitado ainda está lá para gravar")
        self.assertEqual("horas de trabalho", self._dados(1)[-1]["linhas"][0])

    def test_a_caixa_de_folha_nao_mente_quando_a_troca_e_recusada(self) -> None:
        self.modo.definir_pasta(pasta_temporaria(self))
        self.modo.abrir(_ID, 1)
        self._digitar("x")
        self.modo.escolha_de_folha.setCurrentIndex(1)
        self.modo._trocar_folha(1)  # noqa: SLF001
        self.assertEqual((_ID, 1), self.modo.escolha_de_folha.currentData())

    def test_trocar_de_passada_sem_gravar_nao_apaga(self) -> None:
        self.modo.definir_pasta(pasta_temporaria(self))
        self.modo.abrir(_ID, 1)
        self._digitar("primeira passada")
        self.modo.escolha_de_passada.setCurrentIndex(self.modo.escolha_de_passada.findData(2))
        self.assertEqual(1, self.modo.passada)
        self.assertEqual("primeira passada", self.modo.linhas[0].campo.text())

    def test_arquivo_com_linha_cortada_abre_e_avisa(self) -> None:
        self.modo.abrir(_ID, 1)
        self._digitar("inteira")
        self.modo.concluir()
        with ts.caminho_da_passada(self.pasta, 1).open("ab") as arquivo:
            arquivo.write(b'{"identidade": "cortad')
        self.assertTrue(self.modo.definir_pasta(self.pasta))
        self.assertTrue(self.modo.abrir(_ID, 1))
        self.assertEqual("inteira", self.modo.linhas[0].campo.text())
        self.assertIn("cortadas", self.modo.frase.text())

    def test_folha_vazia_nao_se_conclui(self) -> None:
        self.modo.abrir(_ID, 1)
        self.modo.concluir()
        self.assertEqual(strings.TRANSCRICAO_FOLHA_VAZIA, self.modo.frase.text())
        self.assertFalse(ts.caminho_da_passada(self.pasta, 1).exists())

    def test_concluir_mantem_a_folha_na_caixa(self) -> None:
        self.modo._encher_folhas()  # noqa: SLF001
        self.modo.escolha_de_folha.setCurrentIndex(1)
        self.modo.abrir(_ID, 2)
        self._digitar("x")
        self.modo.concluir()
        self.assertEqual((_ID, 2), self.modo.escolha_de_folha.currentData())

    def test_sair_do_modo_guarda(self) -> None:
        self.modo.abrir(_ID, 1)
        self._digitar("antes de sair")
        self.modo.desativar()
        self.assertEqual("antes de sair", self._dados(1)[-1]["linhas"][0])

    def test_o_relogio_grava_o_tempo_da_folha(self) -> None:
        self.modo.abrir(_ID, 1)
        self.hora[0] += 90.0
        self._digitar("x")
        self.hora[0] += 30.0
        self.modo.concluir()
        self.assertEqual(120.0, self._dados(1)[-1]["segundos"])
        self.modo._tique()  # noqa: SLF001
        self.assertRegex(self.modo.mostrador.text(), r"^00:0\d:\d\d$")

    def test_reabrir_soma_ao_tempo_que_ja_havia(self) -> None:
        self.modo.abrir(_ID, 1)
        self.hora[0] += 60.0
        self._digitar("x")
        self.modo.concluir()
        self.modo.abrir(_ID, 1)
        self.hora[0] += 60.0
        self._digitar("xy")
        self.modo.concluir()
        self.assertEqual(120.0, self._dados(1)[-1]["segundos"])

    def test_o_custo_aparece_com_duas_folhas(self) -> None:
        for folha in (1, 2):
            self.modo.abrir(_ID, folha)
            self.hora[0] += 600.0 if folha == 1 else 300.0
            self._digitar("x")
            self.modo.concluir()
        self.assertIn("em 2 folhas", self.modo.custo.text())

    def test_sem_backup_a_frase_diz_e_o_processo_sobrevive(self) -> None:
        outra = pasta_temporaria(self)
        self.modo.definir_pasta(outra)
        self.modo.abrir(_ID, 1)
        self._digitar("x")
        self.modo.concluir()
        self.assertIn("backup", self.modo.frase.text().lower())
        self.assertFalse(ts.caminho_da_passada(outra, 1).exists())

    def test_pasta_no_repositorio_e_recusada_na_frase(self) -> None:
        raiz = Path(__file__).resolve().parents[1]
        self.assertFalse(self.modo.definir_pasta(raiz / "data"))
        self.assertIn("repositório", self.modo.frase.text())
        self.assertIsNone(self.modo.caderno)

    def test_outra_copia_do_livro_nao_abre(self) -> None:
        with mock.patch.object(ts, "abrir_folha", return_value=ts.FolhaAberta(np.zeros((9, 9, 3), np.uint8), (), (), "a" * 16, "c" * 16)):
            self.assertFalse(self.modo.abrir(_ID, 1))
        self.assertEqual(strings.TRANSCRICAO_OUTRA_COPIA, self.modo.frase.text())

    def test_enter_vai_a_linha_seguinte(self) -> None:
        self.modo.show()
        self.modo.activateWindow()
        aplicacao().processEvents()
        self.modo.abrir(_ID, 1)
        self.modo.linhas[0].campo.setFocus()
        aplicacao().processEvents()
        if not self.modo.linhas[0].campo.hasFocus():
            self.skipTest("sem foco nesta plataforma")
        QTest.keyClick(self.modo.linhas[0].campo, Qt.Key.Key_Return)
        self.assertTrue(self.modo.linhas[1].campo.hasFocus())

    def test_linha_a_mais_e_figurina(self) -> None:
        self.modo.show()
        self.modo.activateWindow()
        aplicacao().processEvents()
        self.modo.abrir(_ID, 1)
        self.modo.linhas[0].campo.setFocus()
        aplicacao().processEvents()
        if not self.modo.linhas[0].campo.hasFocus():
            self.skipTest("sem foco nesta plataforma")
        self.modo.botao_de_linha.click()
        self.assertEqual(3, len(self.modo.linhas))
        self.assertTrue(self.modo.linhas[1].campo.hasFocus())
        self.assertTrue(self.modo.linhas[1].faixa.pixmap().isNull())
        self.modo._escrever("♘")  # noqa: SLF001
        self.assertEqual("♘", self.modo.linhas[1].campo.text())

    def test_o_botao_de_pasta_usa_quem_escolhe(self) -> None:
        escolhas = [str(self.pasta)]
        self.modo._escolher_pasta = lambda _p, _t: escolhas[0]  # noqa: SLF001
        ouvidas: list[str] = []
        self.modo.pasta_mudou.connect(ouvidas.append)
        self.modo.botao_de_pasta.click()
        self.assertEqual([str(self.pasta)], ouvidas)
        novo = pasta_temporaria(self)
        escolhas[0] = str(novo)
        self.modo.botao_de_backup.click()
        self.assertEqual(novo.resolve(), ts.backup_declarado(self.pasta))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class NoPainelTests(unittest.TestCase):
    def setUp(self) -> None:
        aplicacao()
        self.painel = PainelDeTexto()
        self.addCleanup(descartar, self.painel)

    def test_o_editor_sai_de_cena_e_o_texto_do_motor_nao_chega(self) -> None:
        bloco = BlocoDeTexto.de_linhas([LinhaLida("lido pelo glifo", (0.0, 0.0, 100.0, 9.0), 0.5, "glifo")])  # type: ignore[arg-type]
        self.painel.mostrar_pagina(PaginaLida(pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),)))
        self.assertIn("lido pelo glifo", self.painel.editor.toPlainText())
        self.painel.show()
        self.painel.alternar_transcricao()
        self.assertTrue(self.painel.em_transcricao)
        self.assertFalse(self.painel.editor.isVisible())
        self.assertTrue(self.painel.transcricao.isVisible())
        self.assertNotIn("lido pelo glifo", " ".join(x.campo.text() for x in self.painel.transcricao.linhas))
        self.painel.alternar_transcricao()
        self.assertFalse(self.painel.em_transcricao)
        self.assertTrue(self.painel.editor.isVisible())
        self.assertIn("lido pelo glifo", self.painel.editor.toPlainText())

    def test_o_botao_voltar_devolve_o_editor(self) -> None:
        self.painel.show()
        self.painel.alternar_transcricao()
        self.painel.transcricao.botao_de_fechar.click()
        self.assertFalse(self.painel.em_transcricao)
        self.assertTrue(self.painel.editor.isVisible())

    def test_sem_gravar_o_modo_nao_sai_e_a_frase_fica(self) -> None:
        self.painel.show()
        self.painel.alternar_transcricao()
        modo = self.painel.transcricao
        modo.manifesto = _manifesto()
        modo._achados = {_ID: Path("x.pdf")}  # noqa: SLF001
        modo.definir_pasta(pasta_temporaria(self))
        modo._encher_folhas()  # noqa: SLF001
        with mock.patch.object(ts, "abrir_folha", side_effect=_aberta):
            modo.abrir(_ID, 1)
        modo.linhas[0].campo.setText("x")
        modo.linhas[0].campo.textEdited.emit("x")
        self.painel.alternar_transcricao()
        self.assertTrue(self.painel.em_transcricao)
        self.assertFalse(self.painel.editor.isVisible())
        self.assertIn("não foi gravado", modo.frase.text())
        self.assertEqual("x", modo.linhas[0].campo.text())

    def test_a_pasta_sobrevive_a_sessao(self) -> None:
        pasta = pasta_temporaria(self)
        estado = AppState()
        estado.texto_transcricao_pasta = str(pasta)
        self.painel.aplicar_estado(estado)
        self.painel.alternar_transcricao()
        self.assertEqual(pasta, self.painel.transcricao.pasta)
        outra = pasta_temporaria(self)
        self.painel.transcricao._escolher_pasta = lambda _p, _t: str(outra)  # noqa: SLF001
        self.painel.transcricao.botao_de_pasta.click()
        nova = AppState()
        self.painel.anotar_estado(nova)
        self.assertEqual(str(outra), nova.texto_transcricao_pasta)
        self.assertEqual(str(outra), state_from_dict(nova.to_dict()).texto_transcricao_pasta)

    def test_o_comando_esta_na_fita_no_menu_e_tem_dono(self) -> None:
        self.assertIn("modo_transcricao", {c.acao for c in comandos.CATALOGO})
        self.assertEqual("alternar_transcricao", texto_declarado.COMANDOS_DA_ABA["modo_transcricao"])
        self.assertTrue(callable(getattr(self.painel, texto_declarado.COMANDOS_DA_ABA["modo_transcricao"])))
        self.assertIn("modo_transcricao", {a for aba in fita_do_texto.ABAS for g in aba.grupos for a in g.itens})
        self.assertIn("modo_transcricao", {i.acao for m in menu.MENUS for i in m.itens})


if __name__ == "__main__":
    unittest.main()
