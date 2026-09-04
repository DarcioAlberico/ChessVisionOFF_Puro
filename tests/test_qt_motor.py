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
from pathlib import Path
from typing import Any

import chess
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, cor_em, descartar, pixels_diferentes, renderizar
from test_engine import _launcher

from chess_diagram_ocr import tablebase
from chess_diagram_ocr.engine import EngineAnalyzer, Evaluation
from chess_diagram_ocr.settings import EngineSettings
from chess_diagram_ocr.ui import analise_da_partida as declarada
from chess_diagram_ocr.ui import motor_declarado, tokens

if TEM_PYQT:
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

    def test_o_mate_pinta_a_faixa_de_quem_mateia_em_cor_propria(self) -> None:
        """**Cor e não altura**: a barra cheia já quer dizer +8, e o que separa "está ganho" de
        "acaba em três lances" é a cor (S-529)."""
        widget = self.barra()
        widget.definir(2000, None, "+20,00")
        ganho = cor_em(renderizar(widget), 3, ALTURA - 5)
        widget.definir(None, 3, "M3")
        mate = cor_em(renderizar(widget), 3, ALTURA - 5)
        self.assertEqual(tema.cor_atual(tokens.GLIFO_CLARO), ganho)
        self.assertEqual(tema.cor_atual(tokens.ATENCAO), mate)
        self.assertNotEqual(ganho, mate)

    def test_o_mate_das_pretas_pinta_a_faixa_de_cima(self) -> None:
        widget = self.barra()
        widget.definir(None, -2, "-M2")
        self.assertEqual(tema.cor_atual(tokens.ATENCAO), cor_em(renderizar(widget), 3, 5))

    def test_a_barra_limpa_volta_ao_meio(self) -> None:
        widget = self.barra()
        widget.definir(500, None, "+5,00")
        widget.limpar()
        self.assertEqual(ALTURA // 2, widget.altura_de_brancas())


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
        self.assertEqual("", vistos[0][2], "a posição de partida não veio de lance nenhum")

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
