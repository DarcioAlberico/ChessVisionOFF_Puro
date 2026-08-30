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
from ambiente_de_teste import pasta_temporaria_da_classe

from chess_diagram_ocr.engine import (
    ENV_ENGINE_PATH,
    EngineAnalyzer,
    Evaluation,
    find_engine,
)

MOTOR_FALSO = Path(__file__).resolve().parent / "fake_uci_engine.py"


def _curto(caminho: Path | str) -> str:
    """O caminho 8.3 do Windows, que e **ASCII por construcao**.

    **Por que a S-434 nao bastou.** Ela grava o `.bat` na code page OEM porque o `cmd.exe` le
    arquivo de lote pela code page do console. Isso acerta quando as duas coincidem, e a CI
    mostrou o outro lado: no job `caminho-com-acento` o checkout mora em `acentuado-aeiouc` com
    acentos, e os sete testes desta classe morreram com `EngineTerminatedError`. Gravar numa code
    page e apostar em qual o console vai usar para ler -- a aposta muda de maquina, e as duas
    pontas do erro dao o mesmo sintoma.

    **A saida e nao ter o que decodificar.** O nome curto de um diretorio acentuado e algo como
    `ACENTU~1`: sem acento, igual em qualquer code page. O `.bat` passa a ser ASCII e a pergunta
    "em que code page isto sera lido?" deixa de existir.

    Onde o 8.3 esta desligado (`NtfsDisable8dot3NameCreation`) a API devolve o caminho longo, o
    `write_text` em `ascii` levanta e o chamador volta para a OEM da S-434 -- pior, mas nunca
    pior do que era.
    """
    texto = str(caminho)
    if os.name != "nt":
        return texto
    import ctypes
    from ctypes import wintypes

    obter = ctypes.windll.kernel32.GetShortPathNameW  # type: ignore[attr-defined]
    obter.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    obter.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(1024)
    quantos = obter(texto, buffer, 1024)
    return buffer.value if 0 < quantos < 1024 else texto


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
        conteudo = f'@echo off\n"{_curto(sys.executable)}" "{_curto(MOTOR_FALSO)}" %*\n'
        try:
            caminho.write_text(conteudo, encoding="ascii")
        except UnicodeEncodeError:
            # Sem nome 8.3 no volume: volta ao comportamento da S-434, que acerta quando a
            # code page do console e a OEM e levanta -- em vez de gravar lixo -- quando nao cabe.
            caminho.write_text(conteudo, encoding="oem")
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
        """"+327,00" não diz nada; "M3" diz exatamente o que está acontecendo."""
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
