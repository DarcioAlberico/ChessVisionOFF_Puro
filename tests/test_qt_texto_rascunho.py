"""O rascunho automático da aba Texto do Qt, e a procedência da mão ao gravar (S-255, S-239).

**Uma sessão de correção é a coisa mais cara desta aba.** Ler a folha custa de 1 s a 40 s; corrigir
à mão custa a tarde de alguém -- e é a única coisa da aba que não sai de graça de uma releitura. O
porte para o Qt deixou os dois recursos para trás: o texto digitado vivia só na memória até alguém
apertar Salvar, e o `.cvtxt` gravado dizia `glifo` sobre o que uma pessoa tinha acabado de corrigir.

A chave estável e a poda são de `text/rascunho.py`; a marcação é de `text/correcao.py`. Aqui se
afirmam as regras da aba: grava por **inatividade**, só quando há o que gravar, na abertura
**oferece** sem aplicar, e gravar carimba e apaga o rascunho.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import arquivo, rascunho, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

if TEM_PYQT:
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QFileDialog, QMessageBox

    from chess_diagram_ocr.qt import dialogos, tema
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto


def _pagina(livro: str = "livro.pdf", folha: int = 0, texto: str = "uma folha lida") -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas([LinhaLida(texto, (0.0, 0.0, 100.0, 9.0), 0.5, "glifo")])  # type: ignore[arg-type]
    return PaginaLida(documento=livro, pagina=folha, colunas=(Coluna(indice=0, blocos=(bloco,)),))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class _Aba(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.pasta = pasta_temporaria(self)
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=self.pasta)
        self.addCleanup(descartar, self.painel)
        self.painel.resize(700, 500)
        self.painel.show()
        self.app.processEvents()
        self.recados: list[str] = []
        self.painel.estado.connect(self.recados.append)

    def digitar_no_fim(self, texto: str) -> None:
        self.painel.editor.setFocus()
        cursor = self.painel.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.painel.editor.setTextCursor(cursor)
        QTest.keyClicks(self.painel.editor, texto)

    def chegou(self, pagina: PaginaLida, *, resposta: bool | None = None) -> None:
        """A folha lida volta da thread -- é onde a oferta do rascunho acontece."""
        if resposta is None:
            self.painel._leitura_terminou((pagina, None))
            return
        with _Respondendo(QMessageBox.StandardButton.Yes if resposta else QMessageBox.StandardButton.No):
            self.painel._leitura_terminou((pagina, None))


class _Respondendo:
    """Uma tela que responde à caixa de pergunta -- sob `offscreen` ninguém responderia."""

    def __init__(self, botao: object) -> None:
        self._tela = mock.patch.object(dialogos, "ha_quem_responda", return_value=True)
        self._caixa = mock.patch.object(QMessageBox, "question", return_value=botao)

    def __enter__(self) -> mock.MagicMock:
        self._tela.start()
        return self._caixa.start()

    def __exit__(self, *_: object) -> None:
        self._caixa.stop()
        self._tela.stop()


class GravaPorInatividadeTests(_Aba):
    def test_grava_so_se_houver_o_que_gravar(self) -> None:
        """Duas regras num teste porque elas são a mesma decisão: **quando** gravar."""
        self.painel.mostrar_pagina(_pagina())
        self.assertIsNone(self.painel.gravar_rascunho(), "gravou com a aba limpa")
        self.digitar_no_fim(" corrigido a mao")
        self.assertTrue(self.painel.tem_alteracoes)
        destino = self.painel.gravar_rascunho()
        self.assertIsNotNone(destino)
        self.assertIn("corrigido", arquivo.carregar(destino).para_texto())  # type: ignore[arg-type]

    def test_a_tecla_reagenda_em_vez_de_gravar_na_hora(self) -> None:
        """Por inatividade, e não por relógio: um relógio fixo grava no meio da digitação."""
        self.painel.mostrar_pagina(_pagina())
        self.assertFalse(self.painel._rascunho.isActive(), "a folha recém-lida não tem o que gravar")
        self.digitar_no_fim("a")
        self.assertTrue(self.painel._rascunho.isActive(), "a tecla não agendou nada")
        self.assertTrue(self.painel._rascunho.isSingleShot())
        self.assertEqual(self.painel._rascunho.interval(), int(rascunho.ESPERA_SEGUNDOS * 1000))
        self.assertIsNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta), "gravou antes da pausa")

    def test_a_ferramenta_tambem_reagenda(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
        self.painel.editor.setTextCursor(cursor)
        self.painel.negrito()
        self.assertTrue(self.painel._rascunho.isActive())

    def test_o_relogio_que_dispara_grava(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.digitar_no_fim(" trabalho")
        self.painel._rascunho.timeout.emit()
        achado = rascunho.achar("livro.pdf", 0, pasta=self.pasta)
        self.assertIsNotNone(achado)
        self.assertFalse(self.painel._rascunho.isActive())

    def test_documento_sem_folha_de_origem_nao_vira_rascunho(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("texto solto"))
        self.digitar_no_fim(" mais")
        self.assertIsNone(self.painel.gravar_rascunho())
        self.assertEqual(list(self.pasta.glob("*")), [])

    def test_fechar_grava_o_rascunho_antes_de_perguntar(self) -> None:
        """O relógio pode não ter disparado: fechar é o momento para o qual ele existe."""
        self.painel.mostrar_pagina(_pagina())
        self.digitar_no_fim(" trabalho nao salvo")
        with _Respondendo(QMessageBox.StandardButton.Yes):
            self.assertTrue(self.painel.confirmar_fechamento())
        self.assertIsNotNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))

    def test_sem_tela_o_fechamento_tambem_deixa_o_rascunho(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.digitar_no_fim(" trabalho nao salvo")
        with self.assertLogs("chess_diagram_ocr.qt.painel_de_texto", level="WARNING"):
            self.assertTrue(self.painel.confirmar_fechamento())
        self.assertIsNotNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))


class ListarTests(unittest.TestCase):
    """`rascunho.listar`: os rascunhos de um livro, por folha, sem abri-los (item 18)."""

    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)

    def test_lista_por_folha_e_so_do_livro(self) -> None:
        rascunho.gravar(rico.de_pagina(_pagina(folha=4)), pasta=self.pasta)
        rascunho.gravar(rico.de_pagina(_pagina(folha=1)), pasta=self.pasta)
        rascunho.gravar(rico.de_pagina(_pagina(livro="outro.pdf", folha=0)), pasta=self.pasta)
        achados = rascunho.listar("livro.pdf", pasta=self.pasta)
        self.assertEqual([r.folha for r in achados], [1, 4])
        self.assertEqual([r.folha for r in rascunho.listar("outro.pdf", pasta=self.pasta)], [0])
        self.assertEqual(rascunho.listar("ninguem.pdf", pasta=self.pasta), [])
        self.assertEqual(rascunho.listar("livro.pdf", pasta=self.pasta / "nao-existe"), [])

    def test_a_poda_vale_tambem_quando_a_impressao_comeca_por_f(self) -> None:
        """`rsplit("_f")` partia a chave na impressão: um livro em dezesseis nunca era podado."""
        self.assertEqual(rascunho._nome_e_impressao("livro_f1_f36a81cc42"), ("livro", "f36a81cc42"))
        self.assertEqual(rascunho._nome_e_impressao("meu_f_livro_f1_0a1b2c3d4e"), ("meu_f_livro", "0a1b2c3d4e"))
        for folha in range(10):
            rascunho.gravar(rico.de_pagina(_pagina(folha=folha)), pasta=self.pasta)
        self.assertEqual(len(rascunho.listar("livro.pdf", pasta=self.pasta)), rascunho.TETO_POR_DOCUMENTO)


class AnuncioNaAberturaTests(_Aba):
    """Ao trocar de livro, a aba diz quantos rascunhos dele há por recuperar (item 18)."""

    def test_o_livro_com_rascunhos_e_anunciado_uma_vez(self) -> None:
        livro = self.pasta / "livro.pdf"
        rascunho.gravar(rico.de_pagina(_pagina(livro=str(livro), folha=2)), pasta=self.pasta)
        rascunho.gravar(rico.de_pagina(_pagina(livro=str(livro), folha=0)), pasta=self.pasta)
        self.painel.definir_livro(livro, pagina=0)
        self.assertEqual(self.recados[-1], "2 rascunho(s) deste livro por recuperar (folha 1, 3): leia a folha e a aba oferece.")
        self.painel.definir_livro(livro, pagina=5)  # a virada de página não repete o anúncio
        self.assertEqual(len(self.recados), 1)

    def test_sem_rascunho_nada_e_dito(self) -> None:
        self.painel.definir_livro(self.pasta / "livro.pdf", pagina=0)
        self.assertEqual(self.recados, [])


class ReabrirOfereceTests(_Aba):
    def setUp(self) -> None:
        super().setUp()
        rascunho.gravar(rico.de_pagina(_pagina(texto="versão do rascunho")), pasta=self.pasta)

    def test_reabrir_oferece_e_nao_aplica(self) -> None:
        """**Oferece**: sobrescrever o que a pessoa acabou de ler com um rascunho de ontem é o
        contrário do que ela quer."""
        with _Respondendo(QMessageBox.StandardButton.No) as pergunta:
            self.painel._leitura_terminou((_pagina(texto="versão recém-lida"), None))
        pergunta.assert_called_once()
        self.assertIn("Há um rascunho não salvo desta folha", pergunta.call_args.args[2])
        self.assertIn("recém-lida", self.painel.texto())
        self.assertFalse(self.painel.tem_alteracoes)

    def test_aceitar_a_oferta_traz_o_rascunho(self) -> None:
        folha = np.full((40, 40, 3), 200, np.uint8)
        with _Respondendo(QMessageBox.StandardButton.Yes):
            self.painel._leitura_terminou((_pagina(texto="versão recém-lida"), folha))
        self.assertIn("rascunho", self.painel.texto())
        self.assertIs(self.painel._pagina_rgb, folha, "a folha recém-lida serve ao rascunho da mesma folha")
        self.assertIn("recuperado", self.recados[-1])

    def test_recusar_nao_apaga(self) -> None:
        self.chegou(_pagina(), resposta=False)
        self.assertIsNotNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))

    def test_recuperar_apaga(self) -> None:
        """Recuperado é trabalho que chegou a um lugar melhor -- a tela."""
        self.chegou(_pagina(), resposta=True)
        self.assertIsNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))

    def test_o_recuperado_continua_sendo_trabalho_por_gravar(self) -> None:
        """A outra metade da linha acima (S-308): o segundo travamento não pode perder tudo."""
        self.chegou(_pagina(), resposta=True)
        self.assertTrue(self.painel.tem_alteracoes, "recuperar apagou o arquivo e deu o texto por gravado")
        self.assertTrue(self.painel._rascunho.isActive(), "e desligou o rascunho automático")
        self.assertIsNotNone(self.painel.gravar_rascunho())
        self.assertIsNotNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))

    def test_sem_tela_o_rascunho_fica_e_a_leitura_vale(self) -> None:
        with self.assertLogs("chess_diagram_ocr.qt.painel_de_texto", level="WARNING"):
            self.chegou(_pagina(texto="versão recém-lida"))
        self.assertIn("recém-lida", self.painel.texto())
        self.assertIsNotNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))

    def test_outra_folha_nao_e_oferecida(self) -> None:
        with _Respondendo(QMessageBox.StandardButton.Yes) as pergunta:
            self.painel._leitura_terminou((_pagina(folha=3), None))
        pergunta.assert_not_called()


class GravarCarimbaAMaoTests(_Aba):
    """O que a mão corrigiu sai do arquivo como `humano`, e deixa de ser pintado como palpite (S-239)."""

    def salvar(self, nome: str = "salvo.cvtxt") -> Path:
        destino = self.pasta / nome
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")):
            self.painel.salvar_documento_como()
        return destino

    def test_salvar_a_folha_vazia_recusa_no_rodape_sem_abrir_dialogo(self) -> None:
        """O porte gravava um `.cvtxt` vazio e dizia «Texto gravado» (item 19)."""
        with mock.patch.object(QFileDialog, "getSaveFileName") as dialogo:
            self.painel.salvar_documento_como()
            self.painel.salvar_documento()
        dialogo.assert_not_called()
        self.assertEqual(self.recados[-1], "Não há texto nesta aba para salvar: leia uma folha ou abra um arquivo.")
        self.assertEqual(list(self.pasta.glob("*.cvtxt")), [])

    def test_salvar_apaga_o_rascunho(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.digitar_no_fim(" corrigido")
        self.painel.gravar_rascunho()
        self.assertIsNotNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))
        destino = self.salvar()
        self.assertTrue(destino.exists())
        self.assertIsNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))
        self.assertFalse(self.painel._rascunho.isActive())

    def test_o_arquivo_e_a_tela_dizem_humano_onde_a_mao_passou(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.assertEqual({c.procedencia for c in self.painel.documento.corridas}, {"glifo"})
        self.digitar_no_fim(" corrigido")
        destino = self.salvar()
        gravado = arquivo.carregar(destino)
        self.assertEqual({c.procedencia for c in gravado.corridas if c.texto.strip()}, {"humano"})
        self.assertEqual(self.painel.documento, gravado, "o que se grava é o que fica na tela")
        self.assertFalse(self.painel.tem_alteracoes)
        self.assertIn("1 correção(ões)", self.recados[-1])

    def test_sem_correcao_o_documento_fica_como_esta(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        antes = self.painel.documento
        self.salvar()
        self.assertIs(self.painel.documento, antes)
        self.assertNotIn("correção", self.recados[-1])

    def test_a_marcacao_nao_entra_na_pilha_de_desfazer(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.digitar_no_fim(" corrigido")
        self.salvar()
        self.painel.desfazer()
        self.assertEqual(self.painel.texto(), "uma folha lida", "o Ctrl+Z desfaz a palavra, e não a procedência")
        self.assertFalse(self.painel.pode_desfazer)

    def test_o_rascunho_tambem_sai_carimbado(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.digitar_no_fim(" corrigido")
        destino = self.painel.gravar_rascunho()
        assert destino is not None
        self.assertEqual({c.procedencia for c in arquivo.carregar(destino).corridas}, {"humano"})

    def test_gravar_tira_a_tinta_de_conferir_do_que_a_mao_corrigiu(self) -> None:
        """A faixa vai junto com a procedência: a cor da letra é a faixa, e ela tem de concordar."""
        self.painel.mostrar_pagina(_pagina())
        self.assertEqual({c.faixa for c in self.painel.documento.corridas}, {"conferir"})
        self.digitar_no_fim(" corrigido")
        self.salvar()
        self.assertEqual({c.faixa for c in self.painel.documento.corridas}, {"tranquilo"})

    def test_a_exportacao_leva_a_procedencia_e_nao_toca_na_tela(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.digitar_no_fim(" corrigido")
        destino = self.pasta / "folha.html"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")):
            self.painel.exportar_html()
        tarefa = self.painel._tarefa
        self.assertIsNotNone(tarefa)
        self.assertTrue(tarefa.wait(10_000))  # type: ignore[union-attr]
        self.app.processEvents()
        self.assertNotIn("faixa-conferir", destino.read_text(encoding="utf-8"), "o corrigido saiu como palpite")
        self.assertTrue(self.painel.tem_alteracoes, "exportar não é gravar")
        # O trecho lido continua "conferir" na tela; o digitado nasce "tranquilo" por ser da mão.
        self.assertIn("conferir", {c.faixa for c in self.painel.documento.corridas}, "e não toca na tela")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
