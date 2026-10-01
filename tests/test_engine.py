"""Motor de análise opcional (S-33).

O critério de aceite tem dois lados, e os dois são verificáveis:

1. **Sem motor instalado, o app funciona normalmente e o recurso fica oculto.** É o que
   `find_engine` devolvendo `None` garante, e é o caso desta máquina.
2. **Com motor, a avaliação aparece em menos de 2 s e não bloqueia a interface.** Aqui um
   motor UCI de mentira (`fake_uci_engine.py`) exercita o caminho inteiro: processo aberto,
   conversa em UCI, pontuação normalizada, linha em SAN.

O motor falso não joga xadrez. Ele existe porque `SimpleEngine.popen_uci` precisa de um
processo de verdade, e porque a máquina de desenvolvimento não tem Stockfish -- exigi-lo
para rodar a suíte contradiria a própria ideia de recurso opcional.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

import chess
import chess.engine
from ambiente_de_teste import pasta_temporaria_da_classe

from chess_diagram_ocr.engine import (
    ENV_ENGINE_PATH,
    TETO_DE_CENTIPEOES,
    EngineAnalyzer,
    Evaluation,
    MotorNaoRespondeu,
    _avaliacao_de,
    find_engine,
)

MOTOR_FALSO = Path(__file__).resolve().parent / "fake_uci_engine.py"


def _launcher(caso: type[unittest.TestCase]) -> Path:
    """Um script que o `popen_uci` consiga executar: o `.py` sozinho não é executável.

    No Windows sai um `.bat`, no resto um `.sh`. Não é frescura de portabilidade -- é o que
    permite ao mesmo teste rodar aqui e na CI.

    **O `.bat` vai na code page OEM, e não em UTF-8 (S-434).** O `cmd.exe` lê arquivo de lote
    pela code page do console -- `cp850` numa máquina brasileira de fábrica --, e não por UTF-8.
    Com `encoding="utf-8"` o acento de `sys.executable` (num Python gerenciado pelo `uv` o
    interpretador mora dentro do perfil do usuário) virava mojibake dentro do `.bat`, e os oito
    testes desta classe morriam com `EngineTerminatedError: engine process died unexpectedly`,
    precedido de um "O sistema não pode encontrar o caminho especificado" que o `python-chess`
    nem consegue decodificar para o log. A CI roda sob caminho ASCII e nunca pôde ver isso.

    Fica um limite, e ele é do `cmd.exe` e não daqui: caminho com caractere fora da code page
    OEM -- cirílico, que é o caso do acervo e o que quebrou na S-111 -- não cabe num `.bat` de
    jeito nenhum, e ali o `encode` **levanta** em vez de gravar lixo, que é a falha certa. Se
    isso aparecer, o caminho é fugir do `cmd`: `popen_uci` aceita **lista** de argumentos, e
    `[sys.executable, str(MOTOR_FALSO)]` dispensa o arquivo de lote inteiro.
    """
    diretorio = pasta_temporaria_da_classe(caso, prefixo="cvoff-engine-")
    if os.name == "nt":
        caminho = diretorio / "motor.bat"
        # Os caminhos vao pelo AMBIENTE, e nao dentro do .bat (S-434, e o que faltava).
        #
        # A S-434 gravava o .bat na code page OEM porque o cmd.exe le arquivo de lote pela
        # code page do console. Isso acerta quando as duas coincidem e erra quando nao -- e o
        # runner da CI e o outro lado: sete testes desta classe morriam com
        # EngineTerminatedError sob `acentuado-aeiouc`. Gravar numa code page e apostar em qual
        # sera usada na leitura, e as duas pontas do erro dao o mesmo sintoma.
        #
        # Nome curto 8.3 tambem nao serve: o volume da CI tem a criacao de nome curto
        # desligada, e ali o GetShortPathName devolve o caminho longo de volta.
        #
        # Variavel de ambiente no Windows e UTF-16 e nao passa por code page nenhuma. O .bat
        # fica ASCII puro -- `%CVOFF_PY%` sao oito caracteres ASCII --, o cmd.exe expande na
        # hora, e a pergunta 'em que code page isto sera lido?' deixa de existir.
        os.environ["CVOFF_PY"] = str(sys.executable)
        os.environ["CVOFF_MOTOR"] = str(MOTOR_FALSO)
        caminho.write_text('@echo off\n"%CVOFF_PY%" "%CVOFF_MOTOR%" %*\n', encoding="ascii")
    else:
        caminho = diretorio / "motor.sh"
        caminho.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{MOTOR_FALSO}" "$@"\n', encoding="utf-8")
        caminho.chmod(0o755)
    return caminho


class FindEngineTests(unittest.TestCase):
    def test_no_engine_is_a_normal_answer_and_not_an_error(self) -> None:
        """É o caso desta máquina, e o app precisa abrir assim mesmo (S-33)."""
        self.assertIsNone(find_engine("caminho/que/nao/existe", env={}))

    def test_an_explicit_path_that_exists_is_used(self) -> None:
        self.assertEqual(find_engine(MOTOR_FALSO, env={}), MOTOR_FALSO)

    def test_an_explicit_path_that_is_wrong_does_not_silently_fall_back(self) -> None:
        """Cair no motor do PATH esconderia o erro de digitação de quem informou o caminho."""
        self.assertIsNone(find_engine("nao-existe.exe", env={"PATH": os.environ.get("PATH", "")}))

    def test_the_environment_variable_is_honoured(self) -> None:
        self.assertEqual(find_engine(env={ENV_ENGINE_PATH: str(MOTOR_FALSO)}), MOTOR_FALSO)


class EvaluationTests(unittest.TestCase):
    """A apresentação da avaliação, sem processo nenhum envolvido."""

    def test_a_positive_score_reads_as_a_white_advantage(self) -> None:
        self.assertEqual(Evaluation(score_cp=135, mate_in=None, best_move=None).display(), "+1,35")

    def test_a_negative_score_keeps_the_sign(self) -> None:
        self.assertEqual(Evaluation(score_cp=-40, mate_in=None, best_move=None).display(), "-0,40")

    def test_a_mate_is_not_shown_as_a_huge_number_of_pawns(self) -> None:
        """ "+327,00" não diz nada; "M3" diz exatamente o que está acontecendo."""
        self.assertEqual(Evaluation(score_cp=None, mate_in=3, best_move=None).display(), "M3")
        self.assertEqual(Evaluation(score_cp=None, mate_in=-2, best_move=None).display(), "-M2")

    def test_an_even_position_puts_the_bar_in_the_middle(self) -> None:
        self.assertAlmostEqual(Evaluation(score_cp=0, mate_in=None, best_move=None).advantage_fraction(), 0.5)

    def test_the_bar_saturates_instead_of_growing_forever(self) -> None:
        """A diferença entre +8 e +12 não muda nada; uma barra linear gastaria a tela nisso."""
        oito = Evaluation(score_cp=800, mate_in=None, best_move=None).advantage_fraction()
        doze = Evaluation(score_cp=1200, mate_in=None, best_move=None).advantage_fraction()
        self.assertGreater(oito, 0.9)
        self.assertLess(doze - oito, 0.05)

    def test_a_mate_pins_the_bar_to_the_end(self) -> None:
        self.assertEqual(Evaluation(score_cp=None, mate_in=1, best_move=None).advantage_fraction(), 1.0)
        self.assertEqual(Evaluation(score_cp=None, mate_in=-1, best_move=None).advantage_fraction(), 0.0)

    def test_the_summary_leads_with_the_evaluation(self) -> None:
        resumo = Evaluation(score_cp=35, mate_in=None, best_move=None, best_move_san="e4", depth=12).summary()
        self.assertTrue(resumo.startswith("Avaliação: +0,35"))
        self.assertIn("e4", resumo)
        self.assertIn("12", resumo)


class AnalyzerTests(unittest.TestCase):
    """O caminho completo, contra um processo UCI de verdade."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = _launcher(cls)

    def test_the_analysis_answers_well_under_the_two_second_criterion(self) -> None:
        with EngineAnalyzer(self.launcher, movetime_ms=100) as motor:
            inicio = time.monotonic()
            avaliacao = motor.analyse(chess.Board())
            decorrido = time.monotonic() - inicio

        self.assertLess(decorrido, 2.0, "A S-33 exige avaliação em menos de 2 s.")
        self.assertEqual(avaliacao.depth, 12)
        self.assertTrue(avaliacao.best_move_san)

    def test_the_score_is_normalised_to_the_white_point_of_view(self) -> None:
        """O UCI responde relativo a quem joga; a barra precisa de um lado só.

        O motor falso responde sempre `+35` para quem está no lance. Com as pretas a jogar,
        isso é **desvantagem** das brancas, e é isso que a avaliação tem de mostrar.
        """
        board = chess.Board()
        board.push_san("e4")

        with EngineAnalyzer(self.launcher, movetime_ms=100) as motor:
            brancas = motor.analyse(chess.Board())
            pretas = motor.analyse(board)

        self.assertGreater(brancas.score_cp or 0, 0)
        self.assertLess(pretas.score_cp or 0, 0)

    def test_the_principal_variation_comes_back_in_algebraic_notation(self) -> None:
        """`e2e4` é do protocolo; quem lê o tabuleiro lê `e4`."""
        with EngineAnalyzer(self.launcher, movetime_ms=100) as motor:
            avaliacao = motor.analyse(chess.Board())
        self.assertTrue(avaliacao.pv_san)
        self.assertNotIn("2", avaliacao.pv_san[0])

    def test_a_position_with_no_legal_move_is_an_answer_and_not_a_crash(self) -> None:
        """Mate é resposta legítima: o motor não tem o que sugerir, e isso não é erro."""
        mate = chess.Board("7k/5KQ1/8/8/8/8/8/8 b - - 0 1")
        self.assertTrue(mate.is_checkmate())

        with EngineAnalyzer(self.launcher, movetime_ms=100) as motor:
            avaliacao = motor.analyse(mate)

        self.assertEqual(avaliacao.best_move_san, "")

    def test_o_mate_ja_dado_aponta_para_quem_o_deu(self) -> None:
        """**`mate 0` não carrega sinal, e isso valia o vencedor errado** (S-537).

        O UCI responde `score mate 0` na posição em que quem está no lance está mateado, e tanto
        `Mate(0)` quanto `MateGiven` respondem `0` a `.mate()`. Sem normalizar, a posição final de
        toda partida ganha valia `-M0`: a barra ia para o lado do perdedor, e a análise da partida
        inteira marcava o lance de mate como **erro grave** de quem deu o mate -- foi assim que
        `7. Nd5#` apareceu com `??` na fotografia da defesa de Legall.
        """
        brancas_mateiam = chess.Board("7k/5KQ1/8/8/8/8/8/8 b - - 0 1")
        pretas_mateiam = chess.Board("8/8/8/8/8/5k2/6q1/7K w - - 0 1")
        self.assertTrue(brancas_mateiam.is_checkmate() and pretas_mateiam.is_checkmate())

        with EngineAnalyzer(self.launcher, movetime_ms=100) as motor:
            de_brancas = motor.analyse(brancas_mateiam)
            de_pretas = motor.analyse(pretas_mateiam)

        self.assertGreater(de_brancas.mate_in or 0, 0, "o mate das brancas não pode valer negativo")
        self.assertLess(de_pretas.mate_in or 0, 0)
        self.assertEqual(1.0, de_brancas.advantage_fraction())
        self.assertEqual(0.0, de_pretas.advantage_fraction())

    def test_o_score_de_tablebase_do_uci_vira_resultado_e_nao_duzentos_peoes(self) -> None:
        """**Medido com Syzygy de verdade nesta máquina** (S-538, segunda rodada).

        Com `SyzygyPath` apontado, o Stockfish imprime a vitória por tabela como `cp 20000 - ply`
        (`UCI::value`) -- e num KBNvK o painel mostrava `+200,00` e o arquivo recebia
        `[%eval 200.0]`. Duzentos peões não é uma avaliação: é a tabela dizendo o placar, e é assim
        que ela tem de aparecer.
        """
        board = chess.Board("8/8/8/4k3/8/8/8/2BNK3 w - - 0 1")
        ganho = _avaliacao_de(board, {"score": chess.engine.PovScore(chess.engine.Cp(19_980), chess.WHITE)})
        self.assertEqual(1, ganho.tabela)
        self.assertEqual("1-0", ganho.display())
        self.assertEqual(TETO_DE_CENTIPEOES, ganho.score_cp)
        # A barra vai ao teto de dez peões e não a 1,0 exato: é o mesmo número que uma partida
        # decidida já vale, e é o que faz o gráfico e o `[%eval]` do arquivo continuarem coerentes.
        self.assertGreater(ganho.advantage_fraction(), 0.99)

        perdido = _avaliacao_de(board, {"score": chess.engine.PovScore(chess.engine.Cp(-19_980), chess.WHITE)})
        self.assertEqual("0-1", perdido.display())
        self.assertEqual(-TETO_DE_CENTIPEOES, perdido.score_cp)

        normal = _avaliacao_de(board, {"score": chess.engine.PovScore(chess.engine.Cp(229), chess.WHITE)})
        self.assertIsNone(normal.tabela, "uma avaliação de verdade continua sendo um número")
        self.assertEqual("+2,29", normal.display())

    def test_um_binario_que_nao_fala_uci_levanta_a_frase_em_pt_br(self) -> None:
        """A janela mostrava a palavra `TimeoutError` -- o nome de uma classe do Python, em inglês.

        `TimeoutError()` tem `str()` **vazio**, então `cli.message_for` caía no nome do tipo. Com
        uma classe própria carregando a frase, a mensagem chega inteira à janela. Aqui o binário
        morre em vez de calar (é mais rápido que os dez segundos do `popen_uci`), e o caminho de
        tradução é o mesmo.
        """
        from chess_diagram_ocr.cli import message_for

        vazio = pasta_temporaria_da_classe(type(self), prefixo="cvoff-engine-") / "nao_e_motor.bat"
        vazio.write_bytes(b"@echo off\r\nexit /b 1\r\n" if os.name == "nt" else b"#!/bin/sh\nexit 1\n")
        if os.name != "nt":
            vazio.chmod(0o755)
        motor = EngineAnalyzer(vazio)
        with self.assertRaises(MotorNaoRespondeu) as capturado:
            motor.start()
        frase = message_for(capturado.exception)
        self.assertIn("UCI", frase)
        self.assertIn("sem motor", frase)
        self.assertNotIn("Timeout", frase)
        self.assertNotIn("EngineTerminated", frase)

    def test_the_process_is_reused_between_analyses(self) -> None:
        """Reabrir o motor a cada posição custaria ~100–300 ms só de inicialização."""
        with EngineAnalyzer(self.launcher, movetime_ms=100) as motor:
            motor.analyse(chess.Board())
            primeiro = motor._engine
            motor.analyse(chess.Board())
            self.assertIs(motor._engine, primeiro)

    def test_closing_twice_is_harmless(self) -> None:
        motor = EngineAnalyzer(self.launcher, movetime_ms=100)
        motor.start()
        motor.close()
        motor.close()

    def test_the_engine_reports_the_name_it_announced(self) -> None:
        with EngineAnalyzer(self.launcher, movetime_ms=100) as motor:
            self.assertIn("FakeEngine", motor.name)


if __name__ == "__main__":
    unittest.main()
