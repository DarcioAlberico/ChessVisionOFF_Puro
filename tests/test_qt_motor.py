"""O painel do motor na janela: barra, linhas, opções e a partida inteira (S-529/S-536/S-537/S-538).

**O que é decisão já foi afirmado sem janela** -- `tests/test_ui_motor_declarado.py`,
`tests/test_ui_analise_da_partida.py` e `tests/test_tablebase.py`. Aqui mede-se o que só existe
depois de o Qt desenhar, e são cinco coisas que quebram caladas:

1. **A barra pinta diferente para +2,00 e −2,00**, e o teste conta pixels: uma barra que não muda
   de altura é uma barra que não diz nada, e sob `offscreen` não há fonte -- mede-se fundo, nunca
   glifo (`tests/qt_app.py`).
2. **O clique numa linha do MultiPV chega à árvore.** O sinal é ligado na montagem, e trocar o
   método depois do `connect` não troca quem o sinal chama: o teste emite o sinal e afirma o
   **efeito** na árvore.
3. **Trocar `Hash` não derruba o processo, e trocar o caminho derruba.** É a promessa inteira da
   S-536, e é a diferença que um `setoption` faz -- afirmada contra o objeto do `python-chess`.
4. **A análise da partida cancela, e não deixa thread viva.** Um `QThread` destruído rodando
   derruba o processo inteiro, e leva os testes seguintes junto.
5. **Sem motor, nada disso aparece** -- é o contrato da S-33, e ele continua valendo.
"""

from __future__ import annotations

import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

import chess
from ambiente_de_teste import pasta_temporaria
from fake_uci_engine import ENGINE_NAME
from qt_app import MOTIVO, TEM_PYQT, aplicacao, cor_em, descartar, pixels_diferentes, renderizar
from test_engine import _launcher

from chess_diagram_ocr import tablebase
from chess_diagram_ocr.engine import EngineAnalyzer, Evaluation
from chess_diagram_ocr.settings import EngineSettings
from chess_diagram_ocr.ui import analise_da_partida as declarada
from chess_diagram_ocr.ui import motor_declarado, tokens

if TEM_PYQT:
    from PyQt6.QtGui import QFontMetrics

    from chess_diagram_ocr.qt import analise_da_partida as qt_analise
    from chess_diagram_ocr.qt import motor as qt_motor
    from chess_diagram_ocr.qt import painel_de_estudo as qt_estudo
    from chess_diagram_ocr.qt import preferencias as qt_preferencias
    from chess_diagram_ocr.qt import tema


ALTURA = 200


def _girar(app: Any, condicao: Any, limite_s: float = 20.0) -> bool:
    """Roda a linha de eventos até a condição valer. Devolve se ela valeu antes do limite."""
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        app.processEvents()
        if condicao():
            return True
        time.sleep(0.005)
    return False


class BarraDeAvaliacaoTests(unittest.TestCase):
    """A barra vertical, medida em pixel (S-529)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def barra(self) -> Any:
        widget = qt_motor.BarraDeAvaliacao()
        self.addCleanup(descartar, widget)
        widget.resize(motor_declarado.LARGURA_DA_BARRA, ALTURA)
        widget.show()
        self.app.processEvents()
        return widget

    def test_mais_dois_e_menos_dois_desenham_diferente(self) -> None:
        """**O critério de aceite em pixel.** Uma barra que responde igual às duas vantagens é um
        widget que ocupa 18 px e não informa nada."""
        widget = self.barra()
        widget.definir(200, None, "+2,00")
        mais = renderizar(widget)
        widget.definir(-200, None, "-2,00")
        menos = renderizar(widget)
        self.assertGreater(pixels_diferentes(mais, menos), 1000)

    def test_no_meio_da_barra_a_cor_diz_de_quem_e_a_posicao(self) -> None:
        """Brancas embaixo: com +2,00 a faixa branca passa do meio, e com −2,00 não chega lá."""
        widget = self.barra()
        widget.definir(200, None, "+2,00")
        claro = cor_em(renderizar(widget), 3, ALTURA // 2)
        widget.definir(-200, None, "-2,00")
        escuro = cor_em(renderizar(widget), 3, ALTURA // 2)
        self.assertEqual(tema.cor_atual(tokens.GLIFO_CLARO), claro)
        self.assertEqual(tema.cor_atual(tokens.GLIFO_ESCURO), escuro)

    def test_a_posicao_equilibrada_reparte_ao_meio(self) -> None:
        widget = self.barra()
        widget.definir(0, None, "0,00")
        self.assertEqual(ALTURA // 2, widget.altura_de_brancas())

    def test_mate_das_brancas_e_mate_das_pretas_desenham_diferente(self) -> None:
        """**O bloqueio da primeira rodada, medido em pixel.** Com o âmbar na faixa, `M3` e `-M3`
        saíam idênticos -- 0 pixel de diferença --, porque a barra de mate está cheia por
        construção e "a faixa de quem mateia" é a barra inteira. Agora a faixa é a cor do lado."""
        widget = self.barra()
        widget.definir(None, 3, "M3")
        brancas = renderizar(widget)
        widget.definir(None, -3, "-M3")
        pretas = renderizar(widget)
        self.assertGreater(
            pixels_diferentes(brancas, pretas),
            motor_declarado.LARGURA_DA_BARRA * ALTURA // 2,
            "M3 e -M3 têm de trocar a barra inteira de cor",
        )
        self.assertEqual(tema.cor_atual(tokens.GLIFO_CLARO), cor_em(brancas, 12, ALTURA // 2))
        self.assertEqual(tema.cor_atual(tokens.GLIFO_ESCURO), cor_em(pretas, 12, ALTURA // 2))

    def test_o_mate_troca_o_fio_por_ambar_e_o_ganho_grande_nao(self) -> None:
        """O que separa "está ganho" de "acaba em três lances" continua sendo a cor -- mudou onde
        ela é pintada. `+20,00` e `M3` enchem a barra igual e diferem no fio."""
        widget = self.barra()
        widget.definir(2000, None, "+20,00")
        ganho = renderizar(widget)
        widget.definir(None, 3, "M3")
        mate = renderizar(widget)
        self.assertEqual(tema.cor_atual(tokens.ATENCAO), cor_em(mate, 0, ALTURA // 2))
        self.assertEqual(tema.cor_atual(tokens.ATENCAO), cor_em(mate, 1, ALTURA // 2), "o fio tem 2 px")
        self.assertNotEqual(tema.cor_atual(tokens.ATENCAO), cor_em(ganho, 0, ALTURA // 2))
        self.assertGreater(pixels_diferentes(ganho, mate), 0)

    def test_o_fio_da_barra_muda_com_a_pele_para_nao_sumir_no_escuro(self) -> None:
        """Na pele Foco o fio `MOLDURA` dava 1,04:1 contra o fundo e a barra sumia. O teste mede o
        pixel do fio nos dois cromos, e não a constante."""
        widget = self.barra()
        widget.definir(0, None, "")
        claro = cor_em(renderizar(widget), 0, ALTURA // 2)
        self.assertEqual(tema.cor_atual(tokens.MOLDURA), claro)
        anterior = tema.cromo_escuro_em_vigor()
        tema.aplicar_tema(None, cromo_escuro=True)
        self.addCleanup(tema.aplicar_tema, None, cromo_escuro=anterior)
        escuro = cor_em(renderizar(widget), 0, ALTURA // 2)
        self.assertEqual(tema.cor_atual(tokens.GLIFO_CLARO), escuro)

    def test_a_barra_espelha_com_o_tabuleiro_virado(self) -> None:
        """O Lichess espelha a barra junto com o tabuleiro: quem virou está olhando do lado das
        pretas, e uma barra teimosa obriga o olho a traduzir duas vezes."""
        virado = {"sim": False}
        widget = qt_motor.BarraDeAvaliacao(virado=lambda: virado["sim"])
        self.addCleanup(descartar, widget)
        widget.resize(motor_declarado.LARGURA_DA_BARRA, ALTURA)
        widget.show()
        self.app.processEvents()
        widget.definir(200, None, "+2,00")
        de_pe = renderizar(widget)
        virado["sim"] = True
        widget.update()
        espelhada = renderizar(widget)
        self.assertEqual(tema.cor_atual(tokens.GLIFO_CLARO), cor_em(de_pe, 12, ALTURA - 5))
        self.assertEqual(tema.cor_atual(tokens.GLIFO_CLARO), cor_em(espelhada, 12, 5))
        self.assertGreater(pixels_diferentes(de_pe, espelhada), 1000)

    def test_o_rotulo_que_nao_cabe_nao_e_escrito_cortado(self) -> None:
        """**O outro bloqueio**: `-12,34` precisava de 30 px numa barra de 18 e saía como `12`, que
        é outra avaliação igualmente plausível. A barra passou a 26 e o rótulo perdeu o sinal; o
        que ainda não couber **não é desenhado**, e é isto que o pixel afirma -- a barra com um
        rótulo grande demais fica idêntica à barra sem rótulo nenhum.

        (Sob `offscreen` não há fonte de verdade, então a régua aqui é a decisão e não o glifo: a
        medida em Consolas está na spec.)
        """
        widget = self.barra()
        self.assertEqual(26, motor_declarado.LARGURA_DA_BARRA)
        self.assertIsNone(widget._fonte_que_cabe("+123.456,78"), "nem no menor corpo cabe")
        widget.definir(200, None, "")
        sem_rotulo = renderizar(widget)
        widget.definir(200, None, "+123.456,78")
        com_rotulo = renderizar(widget)
        self.assertEqual(0, pixels_diferentes(sem_rotulo, com_rotulo))
        fonte = widget._fonte_que_cabe("M3")
        if fonte is not None:
            self.assertLessEqual(
                QFontMetrics(fonte).horizontalAdvance("M3"), motor_declarado.LARGURA_DA_BARRA - 2
            )

    def test_a_barra_limpa_volta_ao_meio(self) -> None:
        widget = self.barra()
        widget.definir(500, None, "+5,00")
        widget.limpar()
        self.assertEqual(ALTURA // 2, widget.altura_de_brancas())


class LinhasDoMotorTests(unittest.TestCase):
    """A lista MultiPV: ela é redesenhada a cada ~900 ms e não pode perder o lugar (S-529)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)
        self.lista = qt_motor.LinhasDoMotor()
        self.addCleanup(descartar, self.lista)
        self.lista.resize(200, 60)
        self.lista.show()
        self.app.processEvents()

    def _linhas(self, quantas: int = 10, desvio: int = 0) -> Any:
        return motor_declarado.linhas_do_motor(
            [
                Evaluation(score_cp=100 - 7 * i + desvio, mate_in=None, best_move=None,
                           pv_san=("e4", "e5", "Nf3", "Nc6"), depth=20)
                for i in range(quantas)
            ],
            numero_do_lance=12,
            brancas_jogam=True,
        )

    def test_a_rolagem_sobrevive_a_resposta_seguinte(self) -> None:
        """Com `MultiPV 10` a lista voltava ao topo a cada resposta do motor: quem tinha rolado até
        a nona linha para clicar nela não conseguia -- ela saía debaixo do cursor."""
        self.lista.mostrar(self._linhas())
        self.app.processEvents()
        barra = self.lista.verticalScrollBar()
        self.assertGreater(barra.maximum(), 0, "dez linhas em 60 px têm de rolar")
        barra.setValue(barra.maximum())
        antes = barra.value()
        self.lista.mostrar(self._linhas(desvio=1))
        self.app.processEvents()
        self.assertEqual(antes, self.lista.verticalScrollBar().value())

    def test_a_selecao_sobrevive_a_resposta_seguinte(self) -> None:
        """`setHtml` troca o documento inteiro e apaga a seleção: quem selecionava uma linha para
        copiá-la perdia a seleção antes de chegar ao `Ctrl+C`."""
        self.lista.mostrar(self._linhas(3))
        self.app.processEvents()
        cursor = self.lista.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(8, cursor.MoveMode.KeepAnchor)
        self.lista.setTextCursor(cursor)
        self.assertTrue(self.lista.textCursor().selectedText())
        self.lista.mostrar(self._linhas(3, desvio=1))
        self.app.processEvents()
        # As **pontas** da seleção, e não o texto: a resposta seguinte muda o número que está
        # selecionado, e é justamente por isso que ela redesenhou.
        depois = self.lista.textCursor()
        self.assertEqual((0, 8), (depois.selectionStart(), depois.selectionEnd()))

    def test_resposta_igual_nao_redesenha_a_lista(self) -> None:
        """A defesa que mais paga: numa posição parada -- que é onde alguém lê a lista com calma --
        a resposta seguinte é literalmente a mesma, e aí não há redesenho nenhum a sobreviver."""
        self.lista.mostrar(self._linhas(3))
        self.app.processEvents()
        antes = renderizar(self.lista)
        documento = self.lista.document()
        self.lista.mostrar(self._linhas(3))
        self.app.processEvents()
        self.assertIs(documento, self.lista.document())
        self.assertEqual(0, pixels_diferentes(antes, renderizar(self.lista)))


class _MotorLento:
    """Um analisador que demora de propósito, para o Cancelar ter o que cancelar."""

    def __init__(self, espera_s: float = 0.05) -> None:
        self.espera_s = espera_s
        self.chamadas = 0

    def analyse(self, board: chess.Board, **_opcoes: Any) -> Evaluation:
        self.chamadas += 1
        time.sleep(self.espera_s)
        return Evaluation(score_cp=10 * self.chamadas, mate_in=None, best_move=None, depth=8)


class AnaliseDaPartidaTests(unittest.TestCase):
    """A passada pela partida inteira: progresso, cancelamento e o que fica gravado (S-537)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def _jogo(self, lances: int = 30) -> Any:
        import chess.pgn

        jogo = chess.pgn.Game()
        no = jogo
        tabuleiro = chess.Board()
        for _ in range(lances):
            lance = next(iter(tabuleiro.legal_moves))
            no = no.add_variation(lance)
            tabuleiro.push(lance)
        return jogo

    def test_o_cancelar_para_em_menos_de_um_segundo_e_meio(self) -> None:
        """**E não deixa `QThread` viva**: um `QThread` destruído rodando derruba o processo e
        leva os testes seguintes junto, com uma mensagem que não nomeia quem fez isso."""
        rodada = qt_analise.AnalisadorDaPartida(analisador=_MotorLento(0.05))
        self.addCleanup(rodada.deleteLater)
        self.assertTrue(rodada.iniciar(self._jogo(30), profundidade=8))
        self.assertTrue(_girar(self.app, lambda: len(rodada.resultado) or rodada.ocupado, 2.0))
        inicio = time.monotonic()
        rodada.cancelar()
        parou = rodada.esperar(1500)
        gasto = time.monotonic() - inicio
        self.app.processEvents()
        self.assertTrue(parou, "a rodada não parou em 1,5 s")
        self.assertLess(gasto, 1.5)
        self.assertFalse(rodada.ocupado)

    def test_o_que_ja_foi_avaliado_fica(self) -> None:
        """Cancelar não desfaz os vinte primeiros lances, do mesmo modo que cancelar o índice da
        base não apaga os arquivos já lidos."""
        rodada = qt_analise.AnalisadorDaPartida(analisador=_MotorLento(0.01))
        self.addCleanup(rodada.deleteLater)
        rodada.iniciar(self._jogo(40), profundidade=8)
        _girar(self.app, lambda: False, 0.25)
        rodada.cancelar()
        rodada.esperar(1500)
        self.assertTrue(_girar(self.app, lambda: not rodada.ocupado, 2.0))
        self.assertTrue(rodada.cancelada)
        self.assertLess(len(rodada.resultado), 40, "cancelou e mesmo assim avaliou tudo")

    def test_o_progresso_chega_por_sinal_uma_vez_por_posicao(self) -> None:
        rodada = qt_analise.AnalisadorDaPartida(analisador=_MotorLento(0.0))
        self.addCleanup(rodada.deleteLater)
        vistos: list[tuple[int, int, str]] = []
        rodada.progresso.connect(lambda feito, total, san: vistos.append((feito, total, san)))
        rodada.iniciar(self._jogo(6), profundidade=8)
        self.assertTrue(_girar(self.app, lambda: not rodada.ocupado, 5.0))
        self.assertEqual(7, len(vistos), "n+1 posições: a de partida também é avaliada")
        # **Contando a partir de 1, e sobre o número de lances.** A tela dizia `lance 0 de 62`
        # numa partida de 61 lances: o índice da posição estava sendo mostrado como número de
        # lance, e a primeira posição (a de partida) virava "lance 0".
        self.assertEqual((1, 6), vistos[0][:2])
        self.assertTrue(vistos[0][2], "a frase nomeia o lance que está sendo avaliado")
        self.assertIn("lance 1 de 6", declarada.frase_de_progresso(*vistos[0]))
        self.assertIn("lance 6 de 6", declarada.frase_de_progresso(*vistos[-1]))

    def test_partida_sem_lance_nao_comeca_rodada(self) -> None:
        import chess.pgn

        rodada = qt_analise.AnalisadorDaPartida(analisador=_MotorLento(0.0))
        self.addCleanup(rodada.deleteLater)
        self.assertFalse(rodada.iniciar(chess.pgn.Game(), profundidade=8))

    def test_o_grafico_desenha_a_curva_e_o_clique_devolve_o_lance(self) -> None:
        grafico = qt_analise.GraficoDaPartida()
        self.addCleanup(descartar, grafico)
        grafico.resize(300, qt_analise.ALTURA_DO_GRAFICO)
        grafico.show()
        self.app.processEvents()
        vazio = renderizar(grafico)
        grafico.definir(
            [
                declarada.Avaliado(ply=i + 1, numero=i // 2 + 1, brancas=i % 2 == 0, san="Nf3",
                                   centipeoes=cp, mate_em=None, perda=0, juizo="")
                for i, cp in enumerate((20, -40, 300, -600, 120))
            ]
        )
        self.app.processEvents()
        self.assertGreater(pixels_diferentes(vazio, renderizar(grafico)), 500)
        escolhidos: list[int] = []
        grafico.escolhido.connect(escolhidos.append)
        grafico.escolhido.emit(declarada.indice_no_x(299, 5, 300))
        self.assertEqual([4], escolhidos)

    def _grafico(self) -> Any:
        grafico = qt_analise.GraficoDaPartida()
        self.addCleanup(descartar, grafico)
        grafico.resize(300, qt_analise.ALTURA_DO_GRAFICO)
        grafico.show()
        grafico.definir(
            [
                declarada.Avaliado(ply=i + 1, numero=i // 2 + 1, brancas=i % 2 == 0, san="Nf3",
                                   centipeoes=cp, mate_em=None, perda=0, juizo="")
                for i, cp in enumerate((20, -40, 300, -600, 120))
            ]
        )
        self.app.processEvents()
        return grafico

    def test_o_grafico_marca_o_lance_corrente(self) -> None:
        """Sem a marca, o gráfico e o tabuleiro deixam de conversar depois do primeiro clique:
        ele continua mostrando a partida inteira sem dizer onde aquele tabuleiro está nela."""
        grafico = self._grafico()
        sem_marca = renderizar(grafico)
        grafico.marcar(3)
        self.app.processEvents()
        self.assertEqual(2, grafico.corrente())
        self.assertGreater(pixels_diferentes(sem_marca, renderizar(grafico)), 100)
        grafico.marcar(999)
        self.app.processEvents()
        self.assertEqual(-1, grafico.corrente(), "ply fora da partida apaga a marca")
        self.assertEqual(0, pixels_diferentes(sem_marca, renderizar(grafico)))

    def test_a_dica_do_grafico_diz_o_ply_e_a_avaliacao_sob_o_ponteiro(self) -> None:
        """O gráfico só tinha forma. Quem para o ponteiro num vale quer saber qual lance e quanto,
        e achar isso obrigava a clicar -- movendo o tabuleiro -- ou a procurar na lista ao lado."""
        grafico = self._grafico()
        frase = grafico.frase_em(299)
        self.assertIn("ply 5", frase)
        self.assertIn("Nf3", frase)
        self.assertIn("1,20", frase)
        sem_dados = qt_analise.GraficoDaPartida()
        self.addCleanup(descartar, sem_dados)
        self.assertEqual(sem_dados.DICA, sem_dados.frase_em(10))

    def test_o_teto_por_posicao_acompanha_a_profundidade_pedida(self) -> None:
        """A profundidade 30 do diálogo não existia: com 3 s fixos, 41 de 46 posições paravam no
        teto e a média alcançada era 23,5 -- pedir 30 custava o mesmo que pedir 24."""
        self.assertEqual(declarada.TETO_POR_LANCE_MS, declarada.teto_por_lance_ms(16))
        self.assertGreater(declarada.teto_por_lance_ms(20), declarada.teto_por_lance_ms(16))
        self.assertEqual(declarada.TETO_MAXIMO_POR_LANCE_MS, declarada.teto_por_lance_ms(30))
        self.assertLessEqual(declarada.teto_por_lance_ms(30), declarada.TETO_MAXIMO_POR_LANCE_MS)

    def test_o_relatorio_conta_as_posicoes_que_pararam_no_teto(self) -> None:
        """O teto não pode ser eliminado -- um meio-jogo travado a 30 plies passa de meio minuto em
        qualquer máquina --, então o que sobra tem de estar escrito no relatório."""
        cheios = [
            declarada.Avaliado(ply=1, numero=1, brancas=True, san="e4", centipeoes=10,
                               mate_em=None, perda=0, juizo="", profundidade=30)
        ]
        curtos = [
            *cheios,
            declarada.Avaliado(ply=2, numero=1, brancas=False, san="e5", centipeoes=10,
                               mate_em=None, perda=0, juizo="", profundidade=22),
        ]
        self.assertEqual("", declarada.frase_de_truncamento(cheios, 30))
        aviso = declarada.frase_de_truncamento(curtos, 30)
        self.assertIn("1 posição(ões)", aviso)
        self.assertIn("22", aviso)
        self.assertNotIn("teto de tempo", declarada.resumo(curtos), "o aviso é da medição, não da partida")
        janela = qt_analise.JanelaDaAnalise(None, curtos, ir_para=lambda _ply: None, profundidade=30)
        self.addCleanup(descartar, janela)
        self.assertEqual(aviso, janela.lbl_truncadas.text())
        limpa = qt_analise.JanelaDaAnalise(None, cheios, ir_para=lambda _ply: None, profundidade=30)
        self.addCleanup(descartar, limpa)
        self.assertEqual("", limpa.lbl_truncadas.text())

    def test_o_resumo_traz_precisao_e_perda_media(self) -> None:
        """Nenhum dos dois números aparecia, e são os que a ChessBase e o Lichess põem no topo: a
        contagem de erros diz quantas vezes alguém tropeçou, o ACPL diz o quanto."""
        lances = [
            declarada.Avaliado(ply=1, numero=1, brancas=True, san="e4", centipeoes=0,
                               mate_em=None, perda=20, juizo="", perda_de_chance=3.0),
            declarada.Avaliado(ply=2, numero=1, brancas=False, san="e5", centipeoes=0,
                               mate_em=None, perda=400, juizo=declarada.ERRO_GRAVE, perda_de_chance=40.0),
        ]
        frase = declarada.resumo(lances)
        self.assertIn("perda média 20 centipeões", frase)
        self.assertIn("perda média 400 centipeões", frase)
        self.assertEqual(20, declarada.perda_media(lances, brancas=True))
        self.assertGreater(declarada.precisao(lances, brancas=True), declarada.precisao(lances, brancas=False))

    def test_a_posicao_ja_matada_nao_ganha_eval_no_arquivo(self) -> None:
        """`[%eval #1]` estava sendo gravado na posição em que o mate **já aconteceu**: o UCI
        responde `mate 0` ali e a normalização para `±1` -- que a barra precisa -- virava um "mate
        em um" falso no PGN. O Lichess simplesmente não grava avaliação na posição final."""
        vivo = declarada.Avaliado(ply=1, numero=1, brancas=True, san="e4", centipeoes=10,
                                  mate_em=None, perda=0, juizo="")
        matado = declarada.Avaliado(ply=2, numero=1, brancas=False, san="Qh4#", centipeoes=-1000,
                                    mate_em=-1, perda=0, juizo="", acabou=True)
        self.assertTrue(declarada.grava_avaliacao(vivo))
        self.assertFalse(declarada.grava_avaliacao(matado))

    def test_o_laco_marca_a_posicao_final_de_uma_partida_que_acaba_em_mate(self) -> None:
        """O `acabou` sai do tabuleiro e não do motor: é `generate_legal_moves` vazio."""
        import chess.pgn

        jogo = chess.pgn.read_game(__import__("io").StringIO("1. f3 e5 2. g4 Qh4# 0-1"))
        rodada = qt_analise.AnalisadorDaPartida(analisador=_MotorLento(0.0))
        self.addCleanup(rodada.deleteLater)
        pronto: list[Any] = []
        rodada.terminou.connect(pronto.append)
        rodada.iniciar(jogo, profundidade=8)
        self.assertTrue(_girar(self.app, lambda: bool(pronto), 5.0))
        avaliados = pronto[0]
        self.assertEqual(4, len(avaliados))
        self.assertFalse(any(lance.acabou for lance in avaliados[:-1]))
        self.assertTrue(avaliados[-1].acabou, "depois de Qh4# não há lance legal")


class _Sala(unittest.TestCase):
    """A sala montada com o motor falso -- a base dos três grupos abaixo."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.launcher = _launcher(type(self))
        self.addCleanup(self.app.processEvents)

    def motor(self, **kwargs: Any) -> EngineAnalyzer:
        analisador = EngineAnalyzer(self.launcher, movetime_ms=100, **kwargs)
        self.addCleanup(analisador.close)
        return analisador

    def sala(self, analisador: EngineAnalyzer | None) -> Any:
        painel = qt_estudo.PainelDeEstudo(
            pasta_inicial=self.pasta,
            pasta_de_estudos=self.pasta,
            analyzer=analisador,
            caminho_das_preferencias=self.pasta / "settings.json",
        )
        self.addCleanup(descartar, painel)
        painel.resize(1000, 760)
        painel.show()
        self.app.processEvents()
        return painel

    def analisar(self, painel: Any) -> None:
        painel.analyse()
        self.assertTrue(_girar(self.app, lambda: not painel._analysing and painel._candidatos))


class PainelComMotorTests(_Sala):
    """O que aparece com motor, e o que não aparece sem ele (S-33/S-529)."""

    def test_sem_motor_nao_ha_barra_nem_secao(self) -> None:
        painel = self.sala(None)
        self.assertIsNone(painel.vantagem)
        self.assertEqual(2, painel.divisor_vertical.count())
        self.assertNotIn("analise_continua", painel.barra.acoes)

    def test_com_motor_a_barra_fica_ao_lado_do_tabuleiro(self) -> None:
        """Ao lado, e não sob a caixa de comentário: ela tem de ser lida com o rabo do olho
        enquanto se olha o tabuleiro."""
        painel = self.sala(self.motor())
        self.assertIsNotNone(painel.vantagem)
        self.assertEqual(3, painel.divisor_vertical.count())
        alto = painel.vantagem.mapTo(painel, painel.vantagem.rect().topLeft())
        do_tabuleiro = painel.tabuleiro.mapTo(painel, painel.tabuleiro.rect().topLeft())
        self.assertLess(alto.x(), do_tabuleiro.x(), "a barra fica à esquerda do tabuleiro")
        self.assertLess(abs(alto.y() - do_tabuleiro.y()), 8, "e na mesma altura dele")

    def test_a_analise_enche_barra_linhas_e_desempenho(self) -> None:
        painel = self.sala(self.motor(multipv=3))
        self.analisar(painel)
        self.assertEqual(3, len(painel.lbl_linha_do_motor.texto_das_linhas()))
        self.assertIn("1. ", painel.lbl_linha_do_motor.texto_das_linhas()[0])
        self.assertIn("profundidade 12", painel.lbl_desempenho.text())
        self.assertIn("N/s", painel.lbl_desempenho.text())
        self.assertNotEqual(0.5, painel.vantagem.fracao)

    def test_o_clique_numa_linha_do_multipv_poe_a_variante_na_arvore(self) -> None:
        """**O sinal é ligado na montagem**, e trocar o método depois do `connect` não troca quem
        ele chama: o teste emite o sinal e afirma o efeito na árvore (S-529)."""
        painel = self.sala(self.motor(multipv=3))
        self.analisar(painel)
        segunda = painel._candidatos[1].pv_san[0]
        painel.lbl_linha_do_motor.escolhida.emit(2)
        self.app.processEvents()
        filhos = [painel.estudo.raiz.board().san(no.move) for no in painel.estudo.raiz.variations]
        self.assertIn(segunda, filhos)

    def test_a_linha_inserida_leva_a_procedencia_no_pgn(self) -> None:
        """O que a máquina sugeriu e o que a pessoa jogou não podem ficar indistinguíveis."""
        painel = self.sala(self.motor(multipv=3))
        self.analisar(painel)
        painel.inserir_linha_do_motor(1)
        primeiro = painel.estudo.raiz.variations[0]
        self.assertIn("motor", primeiro.starting_comment.casefold() + self.launcher.name.casefold())

    def test_o_lance_corrente_nao_se_move_ao_inserir(self) -> None:
        """Quem clica na linha 1 quase sempre quer clicar na 2 em seguida, e as duas ficam lado a
        lado sob a mesma posição -- que é a comparação da S-286."""
        painel = self.sala(self.motor(multipv=3))
        self.analisar(painel)
        antes = painel.estudo.no
        painel.inserir_linha_do_motor(1)
        self.assertIs(antes, painel.estudo.no)

    def test_a_barra_da_sala_espelha_quando_o_tabuleiro_e_virado(self) -> None:
        """A barra sabia espelhar desde a S-529 e **a sala não lhe dizia nada**: `virado` chegava
        `None`, e quem virava o tabuleiro para estudar do lado das pretas ficava com uma barra
        teimosa ao lado dele -- o olho traduzindo duas vezes, que é o defeito que o item nomeia.

        Mede-se o pixel do painel, e não o parâmetro: a barra pergunta a orientação no `paintEvent`
        dela, e uma fiação que passasse a resposta errada passaria igual num teste de assinatura.
        """
        painel = self.sala(self.motor())
        self.analisar(painel)
        self.assertFalse(painel.vantagem.invertida())
        de_pe = renderizar(painel.vantagem)
        painel.flip_board()
        self.app.processEvents()
        self.assertTrue(painel.vantagem.invertida(), "a barra não pergunta ao estudo da sala")
        self.assertGreater(pixels_diferentes(de_pe, renderizar(painel.vantagem)), 100)

    def test_o_titulo_da_secao_traz_o_nome_que_o_motor_diz(self) -> None:
        """`Motor (stockfish.exe)` não distingue dois Stockfish de versões diferentes nem um
        binário renomeado, e o UCI responde `id name` na abertura -- é esse nome que todo programa
        de xadrez mostra.

        **O nome chega depois da montagem**, e é isso que a segunda metade afirma: o processo só
        sobe na primeira análise (S-33), então na hora de desenhar a seção só há o nome do arquivo.
        """
        painel = self.sala(self.motor())
        self.assertEqual(f"Motor ({self.launcher.name})", painel.caixa_do_motor.title())
        self.analisar(painel)
        self.assertEqual(f"Motor ({ENGINE_NAME})", painel.caixa_do_motor.title())

    def test_pedir_uma_linha_que_o_motor_nao_deu_vira_frase(self) -> None:
        painel = self.sala(self.motor(multipv=1))
        self.analisar(painel)
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.inserir_linha_do_motor(3)
        self.assertTrue(any("ainda não respondeu" in frase for frase in vistos))


class OpcoesDoMotorTests(_Sala):
    """As opções aplicadas sem reiniciar (S-536)."""

    def _aplicar(self, painel: Any, antes: EngineSettings, depois: EngineSettings) -> Any:
        vivo = painel.aplicar_opcoes_do_motor(antes, depois)
        self.assertTrue(_girar(self.app, lambda: not vivo.ocupado, 20.0))
        return vivo

    def test_trocar_hash_nao_derruba_o_processo(self) -> None:
        """**A promessa inteira do item**: `setoption name Hash value 512` é uma linha no `stdin`,
        e o processo que estava pensando continua o mesmo."""
        analisador = self.motor(hash_mb=128)
        painel = self.sala(analisador)
        self.analisar(painel)
        antes_do_processo = analisador._engine
        self.assertIsNotNone(antes_do_processo)
        self._aplicar(
            painel,
            EngineSettings(path=str(self.launcher), hash_mb=128),
            EngineSettings(path=str(self.launcher), hash_mb=512),
        )
        self.assertIs(antes_do_processo, analisador._engine, "o processo foi derrubado")
        self.assertEqual(512, analisador.opcoes["Hash"])

    def test_trocar_o_caminho_derruba_e_sobe_outro(self) -> None:
        analisador = self.motor()
        painel = self.sala(analisador)
        self.analisar(painel)
        antes_do_processo = analisador._engine
        outro = _launcher(type(self))
        self._aplicar(
            painel,
            EngineSettings(path=str(self.launcher)),
            EngineSettings(path=str(outro)),
        )
        self.assertIsNot(antes_do_processo, analisador._engine, "o processo não foi trocado")
        self.assertIsNotNone(analisador._engine, "o motor novo não subiu")
        self.assertEqual(outro, analisador.path)

    def test_a_troca_roda_fora_da_linha_de_eventos(self) -> None:
        """**A janela não pode congelar**: fechar um motor que está pensando espera ele responder,
        e o `close()` mais o `popen_uci` do seguinte custam centenas de milissegundos."""
        analisador = self.motor()
        painel = self.sala(analisador)
        vivo = painel.aplicar_opcoes_do_motor(
            EngineSettings(path=str(self.launcher)),
            EngineSettings(path=str(_launcher(type(self)))),
        )
        self.assertTrue(vivo.ocupado, "a troca aconteceu na linha de eventos")
        self.assertTrue(_girar(self.app, lambda: not vivo.ocupado, 20.0))

    def test_multipv_vale_na_analise_seguinte_sem_tocar_o_processo(self) -> None:
        analisador = self.motor(multipv=3)
        painel = self.sala(analisador)
        self.analisar(painel)
        do_processo = analisador._engine
        self._aplicar(
            painel,
            EngineSettings(path=str(self.launcher), multipv=3),
            EngineSettings(path=str(self.launcher), multipv=1),
        )
        self.assertIs(do_processo, analisador._engine)
        self.assertEqual(1, analisador.multipv)
        self.analisar(painel)
        self.assertEqual(1, len(painel._candidatos))

    def test_um_caminho_sem_motor_apaga_a_secao_em_vez_de_deixa_la_cinza(self) -> None:
        """É a S-33 aplicada à troca: apontar para um binário que não existe é ficar sem motor."""
        analisador = self.motor()
        painel = self.sala(analisador)
        self._aplicar(
            painel,
            EngineSettings(path=str(self.launcher)),
            EngineSettings(path=str(self.pasta / "nao-existe.exe")),
        )
        self.assertFalse(painel.has_engine)
        self.assertTrue(painel.caixa_do_motor.isHidden())
        self.assertIsNone(painel.analisador)

    def test_uma_sala_sem_motor_ganha_a_secao_e_a_barra_sem_reiniciar(self) -> None:
        """O caso que mais importa: a máquina em que a procura automática não achou nada, e a
        pessoa informa o caminho. Sem isto, a preferência só valeria na abertura seguinte."""
        painel = self.sala(None)
        self.assertNotIn("analise_continua", painel.barra.acoes)
        self._aplicar(painel, EngineSettings(), EngineSettings(path=str(self.launcher)))
        self.assertTrue(painel.has_engine)
        self.assertIn("analise_continua", painel.barra.acoes)
        self.assertEqual(3, painel.divisor_vertical.count())
        self.addCleanup(lambda: painel.analisador and painel.analisador.close())

    def test_as_preferencias_ficam_gravadas_para_a_proxima_sessao(self) -> None:
        from chess_diagram_ocr.settings import load_settings

        painel = self.sala(self.motor())
        self._aplicar(
            painel,
            EngineSettings(path=str(self.launcher)),
            EngineSettings(path=str(self.launcher), hash_mb=256, multipv=4),
        )
        gravado = load_settings(self.pasta / "settings.json").engine
        self.assertEqual(256, gravado.hash_mb)
        self.assertEqual(4, gravado.multipv)


class DialogoDoMotorTests(unittest.TestCase):
    """O formulário: tetos desta máquina e recusa com frase (S-536)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def dialogo(self, **kwargs: Any) -> Any:
        janela = qt_preferencias.DialogoDoMotor(memoria_mb=32_000, nucleos=8, **kwargs)
        self.addCleanup(descartar, janela)
        return janela

    def test_cada_campo_nasce_com_a_faixa_desta_maquina(self) -> None:
        janela = self.dialogo()
        self.assertEqual(8192, janela.campos[motor_declarado.HASH].maximum())
        self.assertEqual(8, janela.campos[motor_declarado.THREADS].maximum())
        self.assertEqual(16, janela.campos[motor_declarado.HASH].minimum())

    def test_o_que_esta_gravado_aparece_nos_campos(self) -> None:
        janela = self.dialogo(opcoes=EngineSettings(path="x.exe", hash_mb=512, threads=4, multipv=5))
        self.assertEqual("x.exe", janela.campo_caminho.text())
        self.assertEqual(512, janela.campos[motor_declarado.HASH].value())
        self.assertEqual(5, janela.campos[motor_declarado.MULTIPV].value())

    def test_um_caminho_que_nao_existe_e_recusado_com_frase_na_propria_janela(self) -> None:
        """Uma segunda caixa para dizer "o caminho não existe" custaria dois cliques para corrigir
        um caractere. A frase fica ao lado do campo, que é onde a correção acontece."""
        janela = self.dialogo()
        janela.campo_caminho.setText("Z:/nao/existe/stockfish.exe")
        self.assertIn("stockfish.exe", janela.erro())
        janela._confirmar()
        self.assertIn("stockfish.exe", janela.lbl_erro.text())
        self.assertFalse(janela.result())

    def test_o_caminho_vazio_passa_porque_e_procure_sozinho(self) -> None:
        janela = self.dialogo()
        self.assertEqual("", janela.erro())

    def test_a_janela_diz_os_numeros_da_maquina(self) -> None:
        janela = self.dialogo()
        self.assertIn("8", janela.lbl_maquina.text())
        self.assertIn("32000", janela.lbl_maquina.text())

    def test_os_numeros_da_maquina_sao_lidos_de_verdade(self) -> None:
        """A memória é zero quando o sistema não diz, e o teto cai no piso -- nunca levanta."""
        self.assertGreaterEqual(qt_preferencias.nucleos_da_maquina(), 1)
        self.assertGreaterEqual(qt_preferencias.memoria_da_maquina_mb(), 0)


class _TabelaDeMentira:
    """A mesma de `tests/test_tablebase.py`: `.rtbw` de verdade não cabe numa suíte."""

    def __init__(self, wdl: int, dtz: int | None = None) -> None:
        self._wdl = wdl
        self._dtz = dtz

    def get_wdl(self, _board: chess.Board) -> int:
        return self._wdl

    def get_dtz(self, _board: chess.Board) -> int | None:
        return self._dtz

    def close(self) -> None:
        return None


class TablebaseNaSalaTests(_Sala):
    """O resultado exato chegando à tela em vez da estimativa (S-538)."""

    FINAL = "8/8/8/8/8/8/4K1k1/4R3 b - - 0 1"
    """Rei e torre contra rei, pretas a jogar: três peças, e com lance legal -- uma posição
    de mate deixaria o motor sem variante nenhuma e mediria outra coisa."""

    def _com_tabela(self, wdl: int, dtz: int | None = None) -> Any:
        painel = self.sala(self.motor())
        painel._finais = tablebase.Finais(self.pasta, tabela=_TabelaDeMentira(wdl, dtz))
        painel.estudo.tabuleiro.set_fen(self.FINAL)
        painel.campo_fen.setText(self.FINAL)
        painel.apply_fen()
        self.app.processEvents()
        return painel

    def test_a_tabela_vence_a_estimativa_do_motor(self) -> None:
        """O motor diz `+0,35` numa posição que ou é ganha ou é tábua -- não existe `+0,35` ali."""
        painel = self._com_tabela(-2, 12)
        self.analisar(painel)
        self.assertIn("Tabela de finais", painel.lbl_motor.text())
        self.assertIn("derrota das pretas", painel.lbl_motor.text())

    def test_tabuas_poem_a_barra_no_meio(self) -> None:
        """Uma tabela dizendo "tábuas" com a barra em +3,45 é a tela discordando de si mesma."""
        painel = self._com_tabela(0)
        self.analisar(painel)
        self.assertIn("Tábuas", painel.lbl_motor.text())
        self.assertEqual(0.5, painel.vantagem.fracao)

    def test_sem_pasta_nada_muda(self) -> None:
        """O contrato do item: sem tablebase configurada, a sala é a de sempre."""
        painel = self.sala(self.motor())
        painel.estudo.tabuleiro.set_fen(self.FINAL)
        self.analisar(painel)
        self.assertNotIn("Tabela de finais", painel.lbl_motor.text())
        self.assertNotIn("Tábuas", painel.lbl_motor.text())

    def test_as_linhas_do_motor_continuam_sendo_as_do_motor(self) -> None:
        """A tabela diz o **resultado**, não a variante: ela substitui uma parte da tela e não a
        seção inteira."""
        painel = self._com_tabela(2, 5)
        self.analisar(painel)
        self.assertTrue(painel.lbl_linha_do_motor.texto_das_linhas())


class PartidaAnalisadaNaSalaTests(_Sala):
    """A passada inteira gravando na árvore (S-537)."""

    def test_a_analise_grava_a_avaliacao_e_o_simbolo_em_cada_lance(self) -> None:
        """**O símbolo é NAG e não cor de tela**: `$4` vai para o PGN e é lido por qualquer
        programa de xadrez. Uma marca só de tela morreria ao fechar a sala."""
        painel = self.sala(self.motor())
        for uci in ("e2e4", "e7e5", "g1f3", "b8c6"):
            painel.push_move(chess.Move.from_uci(uci))
        avaliados = [
            declarada.Avaliado(ply=1, numero=1, brancas=True, san="e4", centipeoes=30,
                               mate_em=None, perda=0, juizo=""),
            declarada.Avaliado(ply=2, numero=1, brancas=False, san="e5", centipeoes=-400,
                               mate_em=None, perda=430, juizo=declarada.ERRO_GRAVE),
        ]
        janela = painel._chegou_a_analise_da_partida(avaliados)
        if janela is not None:
            self.addCleanup(descartar, janela)
        primeiro = painel.estudo.raiz.variations[0]
        segundo = primeiro.variations[0]
        self.assertIn("%eval", primeiro.comment)
        self.assertIn(declarada.NAG_DE_JUIZO[declarada.ERRO_GRAVE], segundo.nags)
        self.assertEqual(set(), set(primeiro.nags), "lance limpo não recebe símbolo")
        self.assertIn("??", painel.lista.toPlainText())

    def test_a_posicao_ja_matada_nao_leva_eval_para_o_pgn(self) -> None:
        """`[%eval #-1]` saía gravado na posição em que o mate **já aconteceu**: o UCI responde
        `score mate 0` ali, e a normalização para `±1` -- que a barra precisa -- vira um "mate em
        um" falso num campo que outros programas leem. O Lichess não grava avaliação na final.

        A decisão existia (`grava_avaliacao`) e a sala não a chamava, então o defeito continuava
        saindo no arquivo. O teste lê o PGN gravado, que é onde o número falso ia parar.
        """
        painel = self.sala(self.motor())
        for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):
            painel.push_move(chess.Move.from_uci(uci))
        avaliados = [
            declarada.Avaliado(ply=1, numero=1, brancas=True, san="f3", centipeoes=-40,
                               mate_em=None, perda=40, juizo=""),
            declarada.Avaliado(ply=2, numero=1, brancas=False, san="e5", centipeoes=-30,
                               mate_em=None, perda=0, juizo=""),
            declarada.Avaliado(ply=3, numero=2, brancas=True, san="g4", centipeoes=-1000,
                               mate_em=None, perda=970, juizo=declarada.ERRO_GRAVE),
            declarada.Avaliado(ply=4, numero=2, brancas=False, san="Qh4#", centipeoes=-1000,
                               mate_em=-1, perda=0, juizo="", acabou=True),
        ]
        janela = painel._chegou_a_analise_da_partida(avaliados)
        if janela is not None:
            self.addCleanup(descartar, janela)
        mate = painel.estudo.raiz.variations[0].variations[0].variations[0].variations[0]
        self.assertEqual("Qh4#", mate.san())
        self.assertNotIn("%eval", mate.comment)
        self.assertEqual(3, painel.pgn_payload().count("%eval"), "os outros três continuam")

        # **O que se pula é a avaliação, e não o nó.** A posição que acaba a partida também pode
        # ser um afogamento, e afogar no lugar de matar é justamente o `??` que esta passada existe
        # para achar: o símbolo continua sendo escrito no lance que a acabou.
        afogou = [*avaliados[:-1], replace(avaliados[-1], juizo=declarada.ERRO_GRAVE)]
        self.assertEqual(2, painel._marcar_os_lances(afogou))
        self.assertIn(declarada.NAG_DE_JUIZO[declarada.ERRO_GRAVE], mate.nags)
        self.assertNotIn("%eval", mate.comment)

    def test_o_relatorio_leva_ao_lance_do_erro(self) -> None:
        painel = self.sala(self.motor())
        for uci in ("e2e4", "e7e5", "g1f3"):
            painel.push_move(chess.Move.from_uci(uci))
        painel.ir_para_o_ply(0)
        self.assertIs(painel.estudo.raiz, painel.estudo.no)
        painel.ir_para_o_ply(2)
        self.assertEqual("e5", painel.estudo.no.san())

    def test_sem_lance_a_analise_da_partida_diz_isso(self) -> None:
        painel = self.sala(self.motor())
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        self.assertIsNone(painel.analisar_partida())
        self.assertTrue(any("Não há lance" in frase for frase in vistos))

    def test_sem_motor_a_analise_da_partida_nao_comeca(self) -> None:
        painel = self.sala(None)
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        self.assertIsNone(painel.analisar_partida())
        self.assertTrue(any("Sem motor UCI" in frase for frase in vistos))


class SemPyQtTests(unittest.TestCase):
    def test_o_pyqt_esta_instalado(self) -> None:
        if not TEM_PYQT:  # pragma: no cover - só num `.venv` antigo
            self.skipTest(MOTIVO)
        self.assertTrue(Path(qt_motor.__file__).exists())
        self.assertTrue(isinstance(threading.current_thread(), threading.Thread))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
