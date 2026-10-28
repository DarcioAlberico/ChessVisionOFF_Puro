"""A fila de livros na janela (S-546): thread, sinais, cancelamento e tabela.

A decisão -- transição, frase, resumo -- é de `ui/fila_de_livros.py` e já é afirmada em
`tests/test_ui_fila_de_livros.py`; a varredura em si, em `tests/test_batch.py`. O que só existe
aqui é o que atravessa a fronteira de thread e o que o diálogo liga.

**A varredura é de mentira, e é o ponto.** Uma de verdade exigiria PDF, o `.pt` e minutos por
livro -- e o que este módulo tem para provar é a fiação: que o aviso da thread de trabalho vira
sinal, que cancelar responde em menos de um segundo e meio, e que nenhuma thread sobrevive ao
teste. `VarreduraDeLivros(executor=...)` é a costura que permite afirmar isso em milissegundos.
"""

from __future__ import annotations

import threading
import time
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.batch import STATUS_FAILED, STATUS_OK, STATUS_SKIPPED, BatchReport, BookResult
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.fila_de_livros import CANCELADO, FALHOU, PRONTO, PULADO

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt.fila_de_livros import POR_MIL, DialogoDaFila, VarreduraDeLivros

A = Path("PDF/a.pdf")
B = Path("PDF/b.pdf")
C = Path("PDF/c.pdf")


class _VarreduraFalsa:
    """Uma `run_batch` de mentira: N páginas por livro, cada uma custando `passo` segundos.

    Ela cumpre o contrato inteiro de `batch.run_batch` -- os três avisos, a ordem deles e o
    `cancel_event` conferido antes de cada livro e entre páginas --, porque é justamente esse
    contrato que a fiação do outro lado consome.
    """

    def __init__(self, *, paginas: int = 4, passo: float = 0.0, pulados: Sequence[str] = (), quebra: str = "") -> None:
        self.paginas = paginas
        self.passo = passo
        self.pulados = set(pulados)
        self.quebra = quebra
        self.opcoes: Any = None
        self.sessoes: list[Any] = []

    def __call__(
        self,
        livros: Sequence[Path],
        destino: Path,
        *,
        options: Any = None,
        on_book_start: Any = None,
        on_book_done: Any = None,
        on_page: Any = None,
        session_factory: Any = None,
        cancel_event: threading.Event | None = None,
    ) -> BatchReport:
        self.opcoes = options
        relatorio = BatchReport(started_at="teste")
        for indice, pdf in enumerate(livros, start=1):
            if cancel_event is not None and cancel_event.is_set():
                break
            if on_book_start is not None:
                on_book_start(pdf, indice, len(livros))
            if session_factory is not None:
                self.sessoes.append(session_factory(destino))
            if pdf.name == self.quebra:
                raise RuntimeError("a varredura inteira caiu")
            if pdf.name in self.pulados:
                resultado = BookResult(pdf=pdf, status=STATUS_SKIPPED, output=destino / f"{pdf.stem}.pgn")
            else:
                cancelado = False
                for pagina in range(1, self.paginas + 1):
                    if cancel_event is not None and cancel_event.is_set():
                        cancelado = True
                        break
                    if self.passo:
                        time.sleep(self.passo)
                    if on_page is not None:
                        on_page(pdf, pagina, self.paginas, pagina * 2)
                resultado = BookResult(
                    pdf=pdf,
                    status="cancelado" if cancelado else STATUS_OK,
                    pages=self.paginas,
                    accepted=3,
                    needs_review=1,
                    rejected=2,
                    elapsed_s=1.5,
                )
            relatorio.books.append(resultado)
            if on_book_done is not None:
                on_book_done(resultado)
        return relatorio


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class VarreduraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.varredura = VarreduraDeLivros(executor=_VarreduraFalsa())
        # LIFO: primeiro espera a thread, depois destroi o objeto -- um QThread destruido rodando
        # derruba o processo.
        self.addCleanup(descartar, self.varredura)
        self.addCleanup(self.varredura.esperar, 10_000)

    def _esperar(self, varredura: Any = None, ate_ms: int = 10_000) -> None:
        alvo = varredura or self.varredura
        for _ in range(ate_ms // 20):
            QTest.qWait(20)
            if not alvo.ocupado:
                return

    def test_cada_livro_termina_com_o_resultado_ao_lado_do_nome(self) -> None:
        self.varredura.acrescentar([A, B])
        self.assertTrue(self.varredura.iniciar(Path("PGN")))
        self._esperar()
        for livro in self.varredura.fila:
            self.assertEqual(livro.estado, PRONTO)
            self.assertEqual(livro.diagramas, 6, "aceitos + revisão + ilegais")
            self.assertEqual(livro.exportados, 3)
            self.assertEqual(livro.ilegais, 2)
        self.assertIsNotNone(self.varredura.relatorio)

    def test_o_progresso_por_pagina_chega_por_sinal(self) -> None:
        """O `on_page` roda na thread de trabalho; o que a barra recebe já veio pela fila de
        eventos, e a fração do conjunto termina em um."""
        fracoes: list[float] = []
        self.varredura.mudou.connect(lambda: fracoes.append(self.varredura.fila.fracao))
        self.varredura.acrescentar([A, B])
        self.varredura.iniciar(Path("PGN"))
        self._esperar()
        self.assertEqual(fracoes[-1], 1.0)
        self.assertIn(0.5, fracoes, "o primeiro livro pronto é metade da fila")

    def test_o_livro_pulado_nao_vira_pronto(self) -> None:
        """Ele não foi lido agora: dizer "pronto" seria afirmar uma leitura que não houve."""
        self.varredura._executor = _VarreduraFalsa(pulados=["b.pdf"])
        self.varredura.acrescentar([A, B])
        self.varredura.iniciar(Path("PGN"))
        self._esperar()
        self.assertEqual([livro.estado for livro in self.varredura.fila], [PRONTO, PULADO])

    def test_nao_comeca_duas_rodadas_ao_mesmo_tempo(self) -> None:
        """Duas escreveriam no mesmo PGN e disputariam os mesmos núcleos."""
        self.varredura._executor = _VarreduraFalsa(paginas=20, passo=0.01)
        self.varredura.acrescentar([A, B])
        self.assertTrue(self.varredura.iniciar(Path("PGN")))
        self.assertFalse(self.varredura.iniciar(Path("PGN")))
        self.varredura.cancelar()
        self._esperar()

    def test_sem_pendente_nao_ha_o_que_comecar(self) -> None:
        self.assertFalse(self.varredura.iniciar(Path("PGN")))

    def test_cancelar_para_em_menos_de_um_segundo_e_meio(self) -> None:
        """E o que já ficou pronto fica: o critério do item."""
        self.varredura._executor = _VarreduraFalsa(paginas=200, passo=0.005)
        self.varredura.acrescentar([A, B, C])
        self.varredura.iniciar(Path("PGN"))
        QTest.qWait(100)
        inicio = time.perf_counter()
        self.varredura.cancelar()
        self._esperar()
        self.assertLess(time.perf_counter() - inicio, 1.5)
        estados = [livro.estado for livro in self.varredura.fila]
        self.assertEqual(estados[0], CANCELADO, "o livro em curso volta cancelado, com o que leu")
        self.assertEqual(estados[1:], [CANCELADO, CANCELADO], "os que nunca começaram")

    def test_a_falha_da_varredura_inteira_vira_sinal_e_nao_excecao(self) -> None:
        falhas: list[str] = []
        self.varredura._executor = _VarreduraFalsa(quebra="a.pdf")
        self.varredura.falhou.connect(lambda mensagem, _exc: falhas.append(mensagem))
        self.varredura.acrescentar([A])
        with self.assertLogs("chess_diagram_ocr.qt", level="WARNING"):
            self.varredura.iniciar(Path("PGN"))
            self._esperar()
        self.assertEqual(len(falhas), 1)
        self.assertIsNone(self.varredura.relatorio)

    def test_registra_no_busy_enquanto_roda_e_solta_no_fim(self) -> None:
        """Fechar a janela no meio pergunta; e a fila não perde trabalho, porque cada livro
        pronto já tem o PGN no disco e o livro em curso tem o parcial da S-24."""
        registro = BusyRegistry()
        varredura = VarreduraDeLivros(busy=registro, executor=_VarreduraFalsa(paginas=40, passo=0.005))
        self.addCleanup(descartar, varredura)
        self.addCleanup(varredura.esperar, 10_000)
        varredura.acrescentar([A])
        varredura.iniciar(Path("PGN"))
        self.assertTrue(registro.is_busy)
        (operacao,) = registro.running()
        self.assertFalse(operacao.loses_work)
        self.assertTrue(operacao.cancellable)
        self._esperar(varredura)
        self.assertFalse(registro.is_busy)

    def test_nenhuma_thread_sobrevive_a_rodada(self) -> None:
        """Um `QThread` vivo quando o objeto Python morre derruba o processo -- e a mensagem
        (`QThread: Destroyed while thread is still running`) não nomeia quem fez isso."""
        terminou: list[bool] = []
        self.varredura.acrescentar([A, B])
        self.varredura.iniciar(Path("PGN"))
        tarefa = self.varredura._tarefa
        self.assertIsNotNone(tarefa)
        tarefa.finished.connect(lambda: terminou.append(True))
        self._esperar()
        self.assertEqual(terminou, [True], "a Tarefa saiu do run() antes de a rodada acabar")
        self.assertIsNone(self.varredura._tarefa, "e a varredura largou a referência")
        self.assertFalse(self.varredura.ocupado)
        with self.assertRaises(RuntimeError):
            # O `deleteLater` ja foi processado pela linha de eventos do `_esperar`: nao sobrou
            # nem o objeto C++, quanto mais a thread.
            tarefa.isRunning()

    def test_o_modelo_do_servico_e_emprestado_um_livro_de_cada_vez(self) -> None:
        """Segurar o lock da S-31 pela fila inteira deixaria a janela sem reconhecer a página
        aberta durante horas."""
        emprestimos: list[Path] = []

        class _Servico:
            def model_session(self, caminho: Path) -> Any:
                emprestimos.append(caminho)
                return None

        falsa = _VarreduraFalsa()
        varredura = VarreduraDeLivros(servico=_Servico(), executor=falsa)
        self.addCleanup(descartar, varredura)
        self.addCleanup(varredura.esperar, 10_000)
        varredura.acrescentar([A, B])
        varredura.iniciar(Path("PGN"))
        self._esperar(varredura)
        self.assertEqual(len(emprestimos), 2, "um por livro, e não um pela fila")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DialogoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        # A pasta de saida e temporaria porque o dialogo grava os relatorios da S-548 nela: um
        # `Path("PGN")` relativo escreveria na arvore de quem roda a suite.
        self.saida = pasta_temporaria(self, prefixo="cvoff-fila-") / "PGN"

    def _montar(self, **kwargs: Any) -> Any:
        varredura = VarreduraDeLivros(executor=kwargs.pop("executor", _VarreduraFalsa()))
        dialogo = DialogoDaFila(None, varredura=varredura, destino=self.saida, **kwargs)
        varredura.setParent(dialogo)
        self.addCleanup(descartar, dialogo)
        self.addCleanup(varredura.esperar, 10_000)
        return dialogo

    def _esperar(self, dialogo: Any, ate_ms: int = 10_000) -> None:
        for _ in range(ate_ms // 20):
            QTest.qWait(20)
            if not dialogo.varredura.ocupado:
                return

    def test_a_fila_vazia_diz_o_que_fazer_e_nao_deixa_comecar(self) -> None:
        dialogo = self._montar()
        self.assertIn("acrescente livros", dialogo.resumo.text())
        self.assertFalse(dialogo.botao_comecar.isEnabled())
        self.assertFalse(dialogo.botao_cancelar.isEnabled())

    def test_acrescentar_livro_liga_o_botao_e_desenha_a_linha(self) -> None:
        dialogo = self._montar()
        dialogo.varredura.acrescentar([A, B])
        self.assertEqual(dialogo.tabela.topLevelItemCount(), 2)
        self.assertEqual(dialogo.tabela.topLevelItem(0).text(0), "a.pdf")
        self.assertEqual(dialogo.tabela.topLevelItem(0).text(1), "na fila")
        self.assertTrue(dialogo.botao_comecar.isEnabled())

    def test_as_duas_barras_andam_e_terminam_cheias(self) -> None:
        """A do conjunto responde "quanto falta"; a do livro responde "isto ainda anda?" -- e num
        livro de milhares de páginas só a segunda se mexe por dezenas de minutos."""
        dialogo = self._montar()
        dialogo.varredura.acrescentar([A, B])
        vistos: list[tuple[int, int]] = []
        dialogo.varredura.mudou.connect(
            lambda: vistos.append((dialogo.barra_do_livro.value(), dialogo.barra_do_conjunto.value()))
        )
        self.assertTrue(dialogo.comecar())
        self._esperar(dialogo)
        self.assertEqual(dialogo.barra_do_conjunto.value(), POR_MIL)
        self.assertTrue(any(0 < livro < POR_MIL for livro, _conjunto in vistos), "a barra do livro andou")

    def test_a_tabela_publica_o_resultado_ao_lado_do_nome(self) -> None:
        dialogo = self._montar()
        dialogo.varredura.acrescentar([A])
        dialogo.comecar()
        self._esperar(dialogo)
        linha = dialogo.tabela.topLevelItem(0)
        self.assertEqual([linha.text(coluna) for coluna in (2, 3, 4)], ["6", "3", "2"])
        self.assertIn("1 livro(s) lido(s)", dialogo.resumo.text())

    def test_o_botao_cancelar_para_a_fila(self) -> None:
        dialogo = self._montar(executor=_VarreduraFalsa(paginas=200, passo=0.005))
        dialogo.varredura.acrescentar([A, B])
        dialogo.comecar()
        QTest.qWait(100)
        self.assertTrue(dialogo.botao_cancelar.isEnabled())
        dialogo.botao_cancelar.click()
        self._esperar(dialogo)
        self.assertEqual(dialogo.varredura.fila[1].estado, CANCELADO)
        self.assertFalse(dialogo.botao_cancelar.isEnabled())

    def test_a_falha_vai_para_o_resumo_e_nao_para_uma_caixa(self) -> None:
        """Uma caixa modal em cima de uma operação que alguém deixou rodando é o que a S-164
        tirou da exportação; o `conftest` reprova a caixa de verdade, então ela nem apareceria."""
        dialogo = self._montar(executor=_VarreduraFalsa(quebra="a.pdf"))
        dialogo.varredura.acrescentar([A])
        with self.assertLogs("chess_diagram_ocr.qt", level="WARNING"):
            dialogo.comecar()
            self._esperar(dialogo)
        self.assertIn("A fila parou", dialogo.resumo.text())

    def test_o_livro_que_falhou_aparece_pelo_nome_no_resumo(self) -> None:
        class _UmFalha(_VarreduraFalsa):
            def __call__(self, livros: Sequence[Path], destino: Path, **kwargs: Any) -> BatchReport:
                relatorio = BatchReport(started_at="teste")
                for indice, pdf in enumerate(livros, start=1):
                    kwargs["on_book_start"](pdf, indice, len(livros))
                    resultado = BookResult(pdf=pdf, status=STATUS_FAILED, error="ValueError: senha")
                    relatorio.books.append(resultado)
                    kwargs["on_book_done"](resultado)
                return relatorio

        dialogo = self._montar(executor=_UmFalha())
        dialogo.varredura.acrescentar([A])
        dialogo.comecar()
        self._esperar(dialogo)
        self.assertEqual(dialogo.varredura.fila[0].estado, FALHOU)
        self.assertIn("falhou: a.pdf — ValueError: senha", dialogo.resumo.text())

    def test_o_relatorio_de_qualidade_sai_um_por_livro_ao_fim_da_fila(self) -> None:
        """S-548: a fila diz "120 diagramas, 0 exportados" na tela; o JSON ao lado do PGN guarda
        isso com a procedência, que é o que permite comparar duas varreduras."""
        import json

        dialogo = self._montar()
        dialogo.varredura.acrescentar([A, B])
        dialogo.comecar()
        self._esperar(dialogo)
        self.assertEqual(len(dialogo.gravados), 2)
        conteudo = json.loads(dialogo.gravados[0].read_text(encoding="utf-8"))
        self.assertEqual(conteudo["book"], "a.pdf")
        self.assertEqual(conteudo["diagrams"], 6)
        self.assertEqual(conteudo["exported"], 3)
        self.assertIn("dpi", conteudo["provenance"])
        self.assertIn(str(self.saida), dialogo.resumo.text())

    def test_a_fila_pode_varrer_sem_deixar_relatorio(self) -> None:
        """Quem varre para conferir uma coisa só não quer cinquenta JSON ao lado dos PGN."""
        dialogo = self._montar(relatorios=False)
        dialogo.varredura.acrescentar([A])
        dialogo.comecar()
        self._esperar(dialogo)
        self.assertEqual(dialogo.gravados, [])
        self.assertNotIn("Relatório de qualidade", dialogo.resumo.text())

    def test_fechar_o_dialogo_nao_para_a_fila(self) -> None:
        """Uma varredura de horas é o que se deixa rodando enquanto se faz outra coisa (S-164):
        quem para a fila é Cancelar, e fechar só guarda a tela. E por isso o diálogo **não** é
        `WA_DeleteOnClose` -- destruí-lo com a thread dentro derrubaria o processo."""
        dialogo = self._montar(executor=_VarreduraFalsa(paginas=200, passo=0.005))
        dialogo.varredura.acrescentar([A, B])
        dialogo.comecar()
        QTest.qWait(60)
        self.assertFalse(dialogo.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose))
        dialogo.close()
        self.assertTrue(dialogo.varredura.ocupado, "fechar guarda a tela e não para a varredura")
        dialogo.varredura.cancelar()
        self._esperar(dialogo)
        self.assertFalse(dialogo.varredura.ocupado)

    def test_a_tabela_traz_as_colunas_declaradas(self) -> None:
        dialogo = self._montar()
        self.assertEqual(
            [coluna.chave for coluna in dialogo.tabela.colunas],
            ["livro", "situacao", "diagramas", "exportados", "ilegais", "tempo"],
        )


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TirarDaFilaTests(unittest.TestCase):
    """Acrescentar era irreversível (S-546, r2): uma pasta entra com todos os PDFs dela (S-34)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.saida = pasta_temporaria(self, prefixo="cvoff-fila-") / "PGN"

    def _montar(self, **kwargs: Any) -> Any:
        varredura = VarreduraDeLivros(executor=kwargs.pop("executor", _VarreduraFalsa()))
        dialogo = DialogoDaFila(None, varredura=varredura, destino=self.saida, **kwargs)
        varredura.setParent(dialogo)
        self.addCleanup(descartar, dialogo)
        self.addCleanup(varredura.esperar, 10_000)
        return dialogo

    def test_o_botao_tira_a_linha_marcada_e_a_tabela_encolhe(self) -> None:
        dialogo = self._montar()
        dialogo.varredura.acrescentar([A, B, C])
        dialogo.tabela.setCurrentItem(dialogo.tabela.topLevelItem(1))

        self.assertEqual([B], dialogo.tirar_selecionado())

        self.assertEqual(2, dialogo.tabela.topLevelItemCount())
        self.assertEqual([A, C], [livro.pdf for livro in dialogo.varredura.fila])

    def test_sem_nada_marcado_nada_sai(self) -> None:
        dialogo = self._montar()
        dialogo.varredura.acrescentar([A, B])
        dialogo.tabela.setCurrentItem(None)
        self.assertEqual([], dialogo.tirar_selecionado())
        self.assertEqual(2, len(dialogo.varredura.fila))

    def test_o_botao_nasce_desligado_e_liga_com_a_fila(self) -> None:
        dialogo = self._montar()
        self.assertFalse(dialogo.botao_tirar.isEnabled())
        dialogo.varredura.acrescentar([A])
        self.assertTrue(dialogo.botao_tirar.isEnabled())

    def test_com_a_varredura_em_curso_a_remocao_e_recusada(self) -> None:
        """A thread guarda a posição de cada livro como número: tirar uma linha faria o resultado
        do seguinte chegar na linha de outro, e em silêncio."""
        dialogo = self._montar(executor=_VarreduraFalsa(paginas=4, passo=0.05))
        dialogo.varredura.acrescentar([A, B, C])
        self.assertTrue(dialogo.comecar())
        try:
            self.assertFalse(dialogo.botao_tirar.isEnabled())
            self.assertEqual([], dialogo.varredura.remover([2]))
        finally:
            dialogo.varredura.cancelar()
            self.assertTrue(dialogo.varredura.esperar(10_000))
        self.assertEqual(3, len(dialogo.varredura.fila))
