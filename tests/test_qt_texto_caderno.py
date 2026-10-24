"""A aba Texto com o caderno do livro: trocar de folha guarda, voltar abre, sem pergunta (S-611, S-612).

Os critérios de aceite da Fase 91 que são da fiação, e não do módulo puro (`test_texto_caderno.py`).
**Toda caixa de pergunta reprova** -- é o `conftest` que a faz falhar --, e é justamente o que se
afirma: ler outra folha, trocar de livro e fechar deixaram de perguntar "descarta as alterações?",
porque não há mais o que descartar. A leitura corre na hora (`_TarefaNaHora`), com o motor trocado
por uma função que diz qual folha leu.
"""

from __future__ import annotations

import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import caderno, rascunho, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QMessageBox
    from test_qt_janela import _JanelaComLivro

    from chess_diagram_ocr.qt import dialogos, painel_de_texto, tema
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto
    from chess_diagram_ocr.ui import strings
else:  # pragma: no cover - sem o PyQt6 as classes pulam, mas precisam de uma base para existir
    _JanelaComLivro = unittest.TestCase


def _pagina(livro: str, folha: int, texto: str) -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas([LinhaLida(texto, (0.0, 0.0, 100.0, 9.0), 0.5, "glifo")])  # type: ignore[arg-type]
    return PaginaLida(documento=livro, pagina=folha, colunas=(Coluna(indice=0, blocos=(bloco,)),))


class _Sinal:
    def __init__(self) -> None:
        self._alvos: list[Callable[..., object]] = []

    def connect(self, alvo: Callable[..., object]) -> None:
        self._alvos.append(alvo)

    def emit(self, *argumentos: object) -> None:
        for alvo in self._alvos:
            alvo(*argumentos)


class _TarefaNaHora:
    """A `Tarefa` sem thread: o trabalho roda no `start`, e os sinais saem na hora."""

    rodando = False
    """Verdade enquanto um trabalho roda: é como o teste sabe que algo foi feito "na thread"."""

    def __init__(self, trabalho: Callable[[], object], parent: object = None, nome: str = "tarefa") -> None:
        self._trabalho = trabalho
        self.pronto, self.falhou, self.finished = _Sinal(), _Sinal(), _Sinal()

    def start(self) -> None:
        try:
            _TarefaNaHora.rodando = True
            try:
                resultado = self._trabalho()
            finally:
                _TarefaNaHora.rodando = False
        except Exception as erro:  # noqa: BLE001 - o teste quer ver a falha pelo sinal, como na thread
            self.falhou.emit(str(erro), erro)
        else:
            self.pronto.emit(resultado)
        self.finished.emit()


class _Respondendo:
    def __init__(self, botao: object) -> None:
        self._tela = mock.patch.object(dialogos, "ha_quem_responda", return_value=True)
        self._caixa = mock.patch.object(QMessageBox, "question", return_value=botao)

    def __enter__(self) -> mock.MagicMock:
        self._tela.start()
        return self._caixa.start()

    def __exit__(self, *_: object) -> None:
        self._caixa.stop()
        self._tela.stop()


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class _Aba(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.pasta = pasta_temporaria(self)
        self.livro = self.pasta / "livros" / "Nunn.pdf"
        self.livro.parent.mkdir()
        self.livro.write_bytes(b"%PDF-1.7\n" + b"conteudo do livro " * 100)
        self.cadernos = self.pasta / "cadernos"
        self.painel = self.novo_painel()
        self.recados: list[str] = []
        self.painel.estado.connect(self.recados.append)
        self.lidas: list[int] = []
        for alvo, falso in (("Tarefa", _TarefaNaHora), ("_ler", self.motor_de_mentira)):
            remendo = mock.patch.object(painel_de_texto, alvo, falso)
            remendo.start()
            self.addCleanup(remendo.stop)
        self.painel.definir_livro(self.livro, pagina=0, paginas=20)

    def novo_painel(self) -> PainelDeTexto:
        painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=self.pasta / "rascunhos", pasta_de_cadernos=self.cadernos)
        self.addCleanup(descartar, painel)
        self.addCleanup(painel.fechar_caderno)
        painel.resize(700, 500)
        painel.show()
        self.app.processEvents()
        return painel

    def motor_de_mentira(self, caminho: Path, indice: int, **_: object) -> PaginaLida:
        self.lidas.append(indice)
        return _pagina(str(caminho), indice, f"texto lido da folha {indice + 1}")

    def ler(self, folha: int) -> None:
        self.painel.campo_de_folha.setValue(folha)
        self.painel.ler()

    def digitar_no_fim(self, texto: str) -> None:
        self.painel.editor.setFocus()
        cursor = self.painel.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.painel.editor.setTextCursor(cursor)
        QTest.keyClicks(self.painel.editor, texto)

    @property
    def cad(self) -> caderno.Caderno:
        aberto = self.painel.caderno_aberto
        assert aberto is not None
        return aberto

    def no_caderno(self, folha: int) -> str:
        doc = self.cad.folha(folha - 1)
        return "" if doc is None else doc.para_texto()


class TrocarDeFolhaGuardaTests(_Aba):
    def test_ler_a_folha_seguinte_guarda_a_correcao_sem_caixa(self) -> None:
        self.ler(1)
        self.digitar_no_fim(" corrigida")
        self.ler(2)  # antes de qualquer relógio, e a caixa de pergunta reprovaria
        self.assertIn("corrigida", self.no_caderno(1))
        self.assertIn("folha 2", self.painel.documento.para_texto())

    def test_a_leitura_vai_ao_caderno_na_hora(self) -> None:
        self.ler(3)
        estado = self.cad.estado(2)
        assert estado is not None
        self.assertEqual((estado.estado, estado.correcoes), (caderno.LIDA, 0))
        self.assertIn("folha 3", self.cad.lida(2).para_texto())  # type: ignore[union-attr]

    def test_trocar_de_livro_guarda_a_folha(self) -> None:
        self.ler(1)
        self.digitar_no_fim(" corrigida")
        primeiro = self.cad
        outro = self.pasta / "livros" / "outro.pdf"
        outro.write_bytes(b"%PDF-1.7\n outro livro")
        self.painel.definir_livro(outro, pagina=0)
        self.assertIsNot(self.painel.caderno_aberto, primeiro)
        self.assertIn("corrigida", primeiro.folha(0).para_texto())  # type: ignore[union-attr]

    def test_fechar_guarda_sem_perguntar_e_solta_a_trava(self) -> None:
        self.ler(1)
        self.digitar_no_fim(" corrigida")
        pasta = self.cad.pasta
        self.assertTrue(self.painel.confirmar_fechamento())
        self.assertFalse((pasta / "caderno.lock").exists())
        self.assertIn("corrigida", arquivo_de(pasta, 1))

    def test_apagar_tudo_e_sair_nao_apaga_a_folha_do_caderno(self) -> None:
        self.ler(3)
        self.painel.editor.setFocus()
        self.painel.editor.selectAll()
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Delete)
        self.assertEqual(self.painel.documento.para_texto().strip(), "")
        self.ler(4)
        self.assertIn("folha 3", self.no_caderno(3), "a versão vazia sobrescreveu a folha")

    def test_abrir_outro_arquivo_guarda_antes_sem_perguntar(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        self.ler(1)
        self.digitar_no_fim(" corrigida")
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=("", "")):
            self.painel.abrir_documento()
        self.assertIn("corrigida", self.no_caderno(1))


class VoltarAbreOCadernoTests(_Aba):
    def test_voltar_a_folha_abre_o_que_foi_feito_sem_motor(self) -> None:
        self.ler(3)
        self.digitar_no_fim(" corrigida")
        self.ler(4)
        self.lidas.clear()
        self.painel.campo_de_folha.setValue(3)
        self.assertEqual(self.painel.botao_de_ler.text(), strings.ABRIR_FOLHA_DO_CADERNO)
        self.painel.ler()
        self.assertEqual(self.lidas, [], "voltar à folha chamou o motor")
        self.assertIn("corrigida", self.painel.documento.para_texto())
        self.assertFalse(self.painel.tem_alteracoes)
        rodape = self.painel.status.text()
        self.assertIn("Folha 3 do caderno", rodape)
        self.assertIn("1 correção", rodape)

    def test_a_folha_sem_caderno_diz_ler(self) -> None:
        self.ler(3)
        self.painel.campo_de_folha.setValue(5)
        self.assertNotEqual(self.painel.botao_de_ler.text(), strings.ABRIR_FOLHA_DO_CADERNO)

    def test_motor_trocado_sem_correcao_le_de_novo_sem_perguntar(self) -> None:
        self.ler(3)
        self.painel._motor = "glifo"
        self.lidas.clear()
        self.ler(3)
        self.assertEqual(self.lidas, [2])
        self.assertEqual(self.cad.estado(2).motor, "glifo")  # type: ignore[union-attr]

    def test_ler_de_novo_com_correcoes_pergunta_uma_vez(self) -> None:
        self.ler(3)
        self.digitar_no_fim(" corrigida")
        with _Respondendo(QMessageBox.StandardButton.No) as caixa:
            self.painel.ler_de_novo()
        caixa.assert_called_once()
        self.assertIn("1 correção", caixa.call_args.args[2])
        self.assertIn("corrigida", self.painel.documento.para_texto(), "recusado, algo mudou")
        with _Respondendo(QMessageBox.StandardButton.Yes):
            self.painel.ler_de_novo()
        self.assertNotIn("corrigida", self.painel.documento.para_texto())
        self.assertIn("corrigida", self.cad.anterior(2).para_texto())  # type: ignore[union-attr]
        self.assertTrue(self.painel.voltar_a_anterior())
        self.assertIn("corrigida", self.painel.documento.para_texto())


class RenderizarAoFundoTests(_Aba):
    """A folha aberta do caderno é rasterizada numa `Tarefa`, e não na thread da janela (S-612)."""

    def test_abrir_do_caderno_rasteriza_dentro_de_uma_tarefa(self) -> None:
        import numpy as np

        self.ler(3)
        self.ler(4)
        chamadas: list[tuple[int, bool]] = []

        def renderizar(_caminho: Path, indice: int, *, dpi: int) -> np.ndarray:
            chamadas.append((indice, _TarefaNaHora.rodando))
            return np.full((400, 400, 3), 200, np.uint8)

        with mock.patch.object(painel_de_texto, "_renderizar", renderizar):
            self.ler(3)
        self.assertEqual(chamadas, [(2, True)], "a folha foi rasterizada fora da tarefa, ou duas vezes")
        self.assertIsNotNone(self.painel._pagina_rgb)

    def test_a_folha_que_chega_depois_de_outra_e_jogada_fora(self) -> None:
        import numpy as np

        self.ler(3)
        self.painel._folha_pedida_ao_fundo = 5
        self.painel._folha_chegou((2, 72, np.zeros((10, 10, 3), np.uint8)))
        self.assertIsNone(self.painel._pagina_rgb)


class DescartarTests(_Aba):
    def test_descartar_mostra_a_leitura_e_ctrl_z_traz_as_correcoes(self) -> None:
        self.ler(2)
        self.digitar_no_fim(" corrigida")
        self.painel._guardar_a_folha()
        lida_antes = self.cad.caminho(1, tipo="lida").read_bytes()
        with _Respondendo(QMessageBox.StandardButton.Yes):
            self.assertTrue(self.painel.descartar_correcoes())
        self.assertEqual(self.painel.documento.para_texto().strip(), "texto lido da folha 2")
        self.assertEqual(self.painel._correcoes, 0)
        self.assertIn("corrigida", self.cad.anterior(1).para_texto())  # type: ignore[union-attr]
        self.painel.desfazer()
        self.assertIn("corrigida", self.painel.documento.para_texto())
        self.painel._guardar_a_folha()
        self.assertEqual(self.cad.caminho(1, tipo="lida").read_bytes(), lida_antes, "a leitura guardada mudou")

    def test_marcar_conferida_muda_o_indice_sem_redesenhar(self) -> None:
        self.ler(2)
        documento = self.painel.editor.document()
        self.assertTrue(self.painel.marcar_conferida())
        self.assertEqual(self.cad.estado(1).estado, caderno.CONFERIDA)  # type: ignore[union-attr]
        self.assertIs(self.painel.editor.document(), documento)


class SalvamentoAutomaticoTests(_Aba):
    def test_espera_a_mudanca_e_o_cursor_parados(self) -> None:
        agora = [100.0]
        self.painel._relogio = lambda: agora[0]
        self.ler(1)
        self.digitar_no_fim(" corrigida")
        self.assertEqual(self.painel._rascunho.interval(), int(caderno.ESPERA_DA_MUDANCA * 1000))
        self.painel._cursor_em = agora[0] = 102.6  # a mudança parou há 2,6 s, o cursor acabou de mexer
        self.painel._rascunho.timeout.emit()
        self.assertNotIn("corrigida", self.no_caderno(1), "gravou com o cursor andando")
        self.assertTrue(self.painel._rascunho.isActive(), "o relógio não voltou a contar")
        agora[0] = 104.2
        self.painel._rascunho.timeout.emit()
        self.assertIn("corrigida", self.no_caderno(1))
        self.assertNotIn("por gravar", self.painel.status.text())


class RascunhosDeAntesTests(_Aba):
    def test_o_rascunho_de_antes_entra_no_caderno_e_sai_da_pasta(self) -> None:
        self.painel.fechar_caderno()
        doc = rico.de_pagina(_pagina(str(self.livro), 4, "corrigida no rascunho"))
        rascunho.gravar(doc, pasta=self.pasta / "rascunhos")
        outro = self.novo_painel()
        outro.definir_livro(self.livro, pagina=0)
        aberto = outro.caderno_aberto
        assert aberto is not None
        self.assertIn("corrigida no rascunho", aberto.folha(4).para_texto())  # type: ignore[union-attr]
        self.assertIsNone(rascunho.achar(self.livro, 4, pasta=self.pasta / "rascunhos"))


class OutraJanelaTests(_Aba):
    def test_o_caderno_travado_por_outra_janela_abre_so_para_leitura(self) -> None:
        import os

        pasta = self.cad.pasta
        self.painel.fechar_caderno()
        (pasta / "caderno.lock").write_text(str(os.getppid()), encoding="utf-8")
        outro = self.novo_painel()
        recados: list[str] = []
        outro.estado.connect(recados.append)
        outro.definir_livro(self.livro, pagina=0)
        self.assertTrue(outro.caderno_aberto.somente_leitura)  # type: ignore[union-attr]
        self.assertTrue(any("só para leitura" in r for r in recados))


class IndiceTests(_Aba):
    """S-613: as folhas do caderno numa lista, do `indice.json`, e o clique abre a folha."""

    def preparar(self) -> None:
        self.ler(2)
        self.digitar_no_fim(" corrigida")
        self.ler(5)
        self.painel.alternar_indice()

    def test_o_indice_lista_as_folhas_sem_abrir_os_arquivos(self) -> None:
        self.preparar()
        self.assertTrue(self.painel.indice.isVisible())
        self.assertEqual(self.painel.indice.paginas(), (1, 4))
        with mock.patch.object(caderno.arquivo, "carregar", side_effect=AssertionError("o índice abriu um .cvtxt")):
            self.painel._mostrar_indice()
        self.assertIn("corrigida", self.painel.indice.item(0).text())  # type: ignore[union-attr]

    def test_o_clique_abre_a_folha_do_caderno(self) -> None:
        self.preparar()
        self.lidas.clear()
        self.painel.indice.itemClicked.emit(self.painel.indice.item(0))
        self.assertEqual(self.lidas, [], "o clique chamou o motor")
        self.assertIn("corrigida", self.painel.documento.para_texto())

    def test_marcar_conferida_pelo_comando_muda_a_linha_e_o_rodape(self) -> None:
        self.preparar()
        documento = self.painel.editor.document()
        self.painel.executar("marcar_folha_conferida")
        self.assertTrue(self.painel.indice.item(1).text().startswith("√ Folha 5"))  # type: ignore[union-attr]
        self.assertIn("1 de 20 folhas conferidas", self.painel.status.text())
        self.assertIs(self.painel.editor.document(), documento, "marcar redesenhou a folha")

    def test_a_tecla_e_a_do_plano(self) -> None:
        from chess_diagram_ocr.ui import atalhos

        self.assertEqual(atalhos.TECLAS_DO_EDITOR["marcar_folha_conferida"], "<Control-Shift-Return>")


class ExportarCadernoTests(_Aba):
    """S-614: o caderno inteiro sai num arquivo, as folhas em ordem, e o relatório diz o que falta."""

    def test_o_md_tem_as_folhas_em_ordem_e_lista_as_que_faltam(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        self.ler(5)
        self.ler(2)
        self.digitar_no_fim(" corrigida")
        destino = self.pasta / "saida" / "caderno.md"
        destino.parent.mkdir()
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "Markdown (*.md)")):
            self.painel.exportar_caderno()
        texto = destino.read_text(encoding="utf-8")
        self.assertLess(texto.index("# Folha 2"), texto.index("# Folha 5"))
        self.assertEqual(texto.count("# Folha "), 2)
        self.assertIn("corrigida", texto, "a folha da tela não entrou como estava")
        self.assertTrue(any("faltam as folhas 1, 3-4, 6-20" in r for r in self.recados), self.recados[-3:])


class PdfPesquisavelDoCadernoTests(_Aba):
    def test_o_livro_sai_com_a_camada_das_folhas_do_caderno(self) -> None:
        import fitz
        from PyQt6.QtWidgets import QFileDialog

        livro = self.pasta / "livros" / "verdadeiro.pdf"
        documento = fitz.open()
        for _ in range(4):
            documento.new_page(width=300, height=200)
        documento.save(str(livro))
        documento.close()
        self.painel.definir_livro(livro, pagina=0, paginas=4)
        self.ler(2)
        self.digitar_no_fim(" corrigida")
        destino = self.pasta / "saida" / "caderno.pdf"
        destino.parent.mkdir()
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "PDF pesquisável (*.pdf)")):
            self.painel.exportar_caderno()
        saida = fitz.open(destino)
        try:
            self.assertEqual(saida.page_count, 4, "o livro saiu sem as folhas que o caderno não tem")
            self.assertIn("corrigida", saida[1].get_text())
            self.assertEqual(saida[0].get_text().strip(), "")
        finally:
            saida.close()
        self.assertIn("do caderno", self.recados[-1])


def _tres_blocos(livro: str, folha: int) -> PaginaLida:
    """Uma folha de três parágrafos com `bbox` conhecidos, em pontos."""
    blocos = tuple(
        BlocoDeTexto.de_linhas([LinhaLida(texto, caixa, 0.9, "glifo")])  # type: ignore[arg-type]
        for texto, caixa in (
            ("primeiro bloco", (10.0, 10.0, 90.0, 30.0)),
            ("segundo bloco", (10.0, 40.0, 120.0, 70.0)),
            ("terceiro bloco", (10.0, 80.0, 60.0, 95.0)),
        )
    )
    return PaginaLida(documento=livro, pagina=folha, colunas=(Coluna(indice=0, blocos=blocos),))


class MesaAcompanhaTests(_Aba):
    """S-644: com a mesa armada, virar a página guarda a folha que sai e abre a que entra."""

    def test_virar_para_folha_sem_caderno_mostra_ler_e_nao_le(self) -> None:
        self.ler(3)
        self.digitar_no_fim(" corrigida")
        self.painel.definir_mesa(True)
        self.lidas.clear()
        self.painel.definir_livro(self.livro, pagina=12)
        self.assertEqual(self.lidas, [], "virar a página leu a folha")
        self.assertEqual(self.painel.documento.para_texto(), "")
        self.assertEqual(self.painel.vazio.botao.text(), strings.ler_a_folha(13))  # type: ignore[union-attr]
        self.assertIn("corrigida", self.no_caderno(3), "a folha que saiu não foi ao caderno")
        self.painel.ler()  # o botão do vazio
        self.assertEqual(self.lidas, [12])

    def test_virar_para_folha_do_caderno_abre_o_texto_dela(self) -> None:
        self.ler(3)
        self.digitar_no_fim(" corrigida")
        self.ler(5)
        self.painel.definir_mesa(True)
        self.lidas.clear()
        self.painel.definir_livro(self.livro, pagina=2)
        self.assertEqual(self.lidas, [])
        self.assertIn("corrigida", self.painel.documento.para_texto())

    def test_sem_a_mesa_virar_a_pagina_nao_troca_a_folha(self) -> None:
        self.ler(3)
        self.painel.definir_livro(self.livro, pagina=12)
        self.assertIn("folha 3", self.painel.documento.para_texto())


class FaixaImpressaTests(_Aba):
    """S-643: a faixa acima do editor com o recorte impresso do bloco sob o cursor."""

    def setUp(self) -> None:
        super().setUp()
        import numpy as np

        self.folha = (np.arange(400 * 400 * 3, dtype=np.uint32) % 251).astype(np.uint8).reshape(400, 400, 3)
        self.painel.mostrar_pagina(_tres_blocos(str(self.livro), 0), folha_rgb=self.folha, dpi=72)

    def por_o_cursor_no(self, bloco: int) -> None:
        deslocamento = rico.deslocamento_do_bloco(self.painel.documento, bloco)
        assert deslocamento is not None
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(deslocamento + 2))
        self.painel.editor.setTextCursor(cursor)

    def test_o_cursor_no_segundo_bloco_mostra_o_recorte_dele(self) -> None:
        import numpy as np

        from chess_diagram_ocr.qt.painel_de_texto import _recorte_da_folha

        self.painel.definir_mesa(True)
        self.por_o_cursor_no(1)
        self.assertFalse(self.painel.faixa_impressa.isHidden())
        esperado = _recorte_da_folha(self.folha, self.painel.documento.origem.blocos[1], dpi=72)  # type: ignore[union-attr]
        self.assertTrue(np.array_equal(self.painel.recorte_na_faixa, esperado))
        self.por_o_cursor_no(2)
        self.assertEqual(self.painel.recorte_na_faixa.shape[:2], (15, 50))  # type: ignore[union-attr]

    def test_fora_da_mesa_ou_sem_folha_a_faixa_some(self) -> None:
        self.por_o_cursor_no(1)
        self.assertTrue(self.painel.faixa_impressa.isHidden(), "a faixa apareceu fora da mesa")
        self.painel.definir_mesa(True)
        self.painel.abrir(rico.DocumentoRico())
        self.painel.definir_mesa(True)
        self.assertTrue(self.painel.faixa_impressa.isHidden())


class ApontarTests(_Aba):
    """S-642, etapa 1: o bloco sob o cursor ganha contorno na folha; o clique na folha leva o cursor."""

    def setUp(self) -> None:
        super().setUp()
        self.painel.definir_livro(self.livro, pagina=0)
        self.painel.mostrar_pagina(_tres_blocos(str(self.livro), 0))
        self.avisados: list[object] = []
        self.painel.bloco_destacado.connect(self.avisados.append)
        self.painel.definir_mesa(True)

    def cursor_em(self, deslocamento: int) -> None:
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(deslocamento))
        self.painel.editor.setTextCursor(cursor)

    def test_o_cursor_em_cada_bloco_contorna_o_bbox_dele(self) -> None:
        blocos = self.painel.documento.origem.blocos  # type: ignore[union-attr]
        for indice in range(3):
            comeco = rico.deslocamento_do_bloco(self.painel.documento, indice)
            assert comeco is not None
            self.cursor_em(comeco + 1)
            self.assertEqual(self.avisados[-1], tuple(blocos[indice].bbox))

    def test_o_clique_no_centro_de_cada_bloco_poe_o_cursor_no_comeco_dele(self) -> None:
        for indice, bloco in enumerate(self.painel.documento.origem.blocos):  # type: ignore[union-attr]
            x0, y0, x1, y1 = bloco.bbox
            self.assertTrue(self.painel.ir_ao_ponto((x0 + x1) / 2, (y0 + y1) / 2))
            posicao = self.painel._mapa.deslocamento(self.painel.editor.textCursor().position())
            self.assertEqual(posicao, rico.deslocamento_do_bloco(self.painel.documento, indice))
        self.assertFalse(self.painel.ir_ao_ponto(250.0, 250.0), "o clique fora de todo bloco moveu o cursor")

    def test_sem_origem_nada_e_contornado_e_nada_levanta(self) -> None:
        self.painel.abrir(rico.DocumentoRico())
        self.painel._avisar_bloco()
        self.assertIsNone(self.avisados[-1])
        self.assertFalse(self.painel.ir_ao_ponto(20.0, 20.0))

    def test_fora_da_mesa_o_contorno_some(self) -> None:
        self.cursor_em(1)
        self.assertIsNotNone(self.avisados[-1])
        self.painel.definir_mesa(False)
        self.assertIsNone(self.avisados[-1])


class VisorDestacaTests(unittest.TestCase):
    """O visualizador desenha o contorno pelo DPI e pelo zoom, e diz o clique em pontos (S-642)."""

    @unittest.skipUnless(TEM_PYQT, MOTIVO)
    def test_pontos_viram_pixel_e_o_clique_volta_a_pontos(self) -> None:
        import numpy as np

        from chess_diagram_ocr.qt.visor import VisorDePagina

        aplicacao()
        visor = VisorDePagina()
        self.addCleanup(descartar, visor)
        visor.mostrar_pagina(np.full((300, 300, 3), 250, np.uint8), dpi=144)
        visor.definir_zoom(1.0)
        visor.definir_destaque((10.0, 20.0, 40.0, 50.0))
        retangulo = visor.retangulo_do_destaque()
        assert retangulo is not None
        self.assertEqual((retangulo.x(), retangulo.y(), retangulo.width(), retangulo.height()), (20, 40, 60, 60))
        pontos: list[tuple[float, float]] = []
        visor.ponto_clicado.connect(lambda x, y: pontos.append((x, y)))
        visor.clicar_em(60.0, 100.0)
        self.assertEqual(pontos, [(30.0, 50.0)])
        visor.definir_destaque(None)
        self.assertIsNone(visor.retangulo_do_destaque())


def _com_diagramas(livro: str, folha: int, quantos: int = 3) -> PaginaLida:
    from chess_diagram_ocr.text.pagina import BlocoDeDiagrama

    blocos: list[object] = []
    for indice in range(quantos):
        blocos.append(BlocoDeTexto.de_linhas([LinhaLida(f"texto {indice}", (0.0, 0.0, 9.0, 9.0), 0.9, "glifo")]))  # type: ignore[arg-type]
        blocos.append(BlocoDeDiagrama(indice=indice, bbox=(10.0, 10.0 + 60 * indice, 60.0, 60.0 + 60 * indice)))
    return PaginaLida(documento=livro, pagina=folha, colunas=(Coluna(indice=0, blocos=tuple(blocos)),))  # type: ignore[arg-type]


class DiagramasNaTelaTests(_Aba):
    """Fase 92 na tela: a preferência redesenha sem gravar, e alinhar todos é um passo de desfazer."""

    def alinhamentos_desenhados(self) -> list[Qt.AlignmentFlag]:
        documento = self.painel.editor.document()
        bloco = documento.begin()
        achados = []
        while bloco.isValid():
            iterador = bloco.begin()
            while not iterador.atEnd():
                if iterador.fragment().charFormat().isImageFormat():
                    achados.append(bloco.blockFormat().alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask)
                    break
                iterador += 1
            bloco = bloco.next()
        return achados

    def test_tres_diagramas_ao_centro_e_a_preferencia_os_leva_a_esquerda_sem_gravar(self) -> None:
        from paridade_do_texto import divergencias

        import numpy as np

        folha = np.full((400, 400, 3), 210, np.uint8)  # 72 dpi: os três bbox cabem nela
        self.painel.mostrar_pagina(_com_diagramas(str(self.livro), 0), folha_rgb=folha, dpi=72)
        centro = Qt.AlignmentFlag.AlignHCenter
        esquerda = Qt.AlignmentFlag.AlignLeft
        self.assertEqual(self.alinhamentos_desenhados(), [centro] * 3)
        self.painel.definir_diagramas("esquerda")
        self.assertEqual(self.alinhamentos_desenhados(), [esquerda] * 3)
        self.assertFalse(self.painel.tem_alteracoes, "a preferência tornou a folha por gravar")
        self.assertEqual(divergencias(self.painel), [])

    def test_a_preferencia_vale_para_a_guarda_de_paridade(self) -> None:
        from paridade_do_texto import divergencias

        self.painel.mostrar_pagina(_com_diagramas(str(self.livro), 0))
        self.painel.definir_diagramas("esquerda")
        self.assertEqual(divergencias(self.painel), [])
        self.assertFalse(self.painel.tem_alteracoes)

    def test_alinhar_os_da_folha_e_um_passo_de_desfazer(self) -> None:
        self.painel.mostrar_pagina(_com_diagramas(str(self.livro), 0))
        self.painel.diagramas_da_folha_a_esquerda()
        self.assertEqual([c.atributos.alinhamento for c in self.painel.documento.diagramas], ["esquerda"] * 3)
        self.painel.desfazer()
        self.assertEqual([c.atributos.alinhamento for c in self.painel.documento.diagramas], [""] * 3)

    def test_grande_com_zoom_mais_dois(self) -> None:
        from chess_diagram_ocr.qt import tema as qt_tema

        self.painel.mostrar_pagina(_com_diagramas(str(self.livro), 0))
        self.painel.definir_tamanho_da_miniatura("grande")
        self.painel.aplicar_zoom(2, avisar=False)
        corpo_do_sistema = qt_tema.fonte_base()[0]
        corpo_da_vista = self.painel._base[0]  # type: ignore[index]
        self.assertEqual(self.painel._largura_da_miniatura(), round(320 * corpo_da_vista / corpo_do_sistema))
        self.assertFalse(self.painel.tem_alteracoes, "o tamanho tornou a folha por gravar")

    def test_alinhar_o_caderno_inteiro_conta_antes_e_guarda_a_anterior_de_cada_folha(self) -> None:
        from chess_diagram_ocr.text import arquivo

        for folha in (1, 4):
            doc = rico.de_pagina(_com_diagramas(str(self.livro), folha, quantos=2))
            self.cad.gravar(doc)
        self.ler(9)  # uma folha sem diagrama, na tela
        with _Respondendo(QMessageBox.StandardButton.Yes) as caixa:
            mudadas = self.painel.alinhar_diagramas_do_caderno("esquerda")
        self.assertIn("4 diagrama(s) de 2 folha(s)", caixa.call_args.args[2])
        self.assertEqual(mudadas, 2)
        for folha in (1, 4):
            depois = arquivo.carregar(self.cad.caminho(folha))
            self.assertEqual({c.atributos.alinhamento for c in depois.diagramas}, {"esquerda"})
            self.assertTrue(self.cad.caminho(folha, tipo="anterior").exists(), f"a folha {folha + 1} ficou sem anterior")

    def test_o_indice_tem_o_menu_do_caderno(self) -> None:
        rotulos = [acao.text() for acao in self.painel.indice.menu().actions()]
        self.assertEqual(len(rotulos), 3)
        self.assertTrue(all("diagramas do caderno" in r.lower() for r in rotulos))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class JanelaTests(_JanelaComLivro):
    def test_a_janela_abre_o_caderno_do_livro_aberto(self) -> None:
        """A janela liga o caderno, na pasta que a suíte dá a este teste (`conftest`)."""
        janela = self.janela()
        aberto = janela.texto.caderno_aberto
        self.assertIsNotNone(aberto)
        self.assertEqual(aberto.pasta.parent, caderno.PASTA_PADRAO)  # type: ignore[union-attr]
        self.assertFalse(aberto.somente_leitura)  # type: ignore[union-attr]


def arquivo_de(pasta: Path, folha: int) -> str:
    from chess_diagram_ocr.text import arquivo

    return arquivo.carregar(pasta / f"folha-{folha:04d}{arquivo.EXTENSAO}").para_texto()


if __name__ == "__main__":
    unittest.main()
