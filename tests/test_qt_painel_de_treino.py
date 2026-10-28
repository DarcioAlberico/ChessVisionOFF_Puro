"""A tela de treino e o placar da sala (S-539/S-540/S-541).

**O que é decisão já foi afirmado sem janela** -- `tests/test_taticas.py`,
`tests/test_revisao_espacada.py` e `tests/test_ui_treino_declarado.py`. Aqui mede-se o que só
existe depois de o Qt desenhar, e são quatro coisas que quebram caladas:

1. **O tabuleiro nasce virado para quem resolve**, e o lance errado é desfeito na tela. O segundo
   é o defeito que a S-290 deixou passar: o modelo do widget joga sobre a própria cópia, e sem
   redesenhar a pessoa fica olhando uma posição que o exercício não tem.
2. **A comparação com o motor volta por sinal**, e o veredicto chega antes dela. É a razão de a
   frase do rodapé ser escrita duas vezes.
3. **A janela grava o baralho ao fechar**, e espera a thread do motor antes de morrer -- um
   `QThread` destruído rodando derruba o processo e leva os testes seguintes junto.
4. **O placar do livro sobrevive a desligar o treino**, que é o item inteiro da S-541.
"""

from __future__ import annotations

import time
import unittest
from datetime import date, timedelta
from typing import Any

import chess
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar
from test_engine import _launcher

from chess_diagram_ocr import placar as placar_mod
from chess_diagram_ocr import revisao_arquivo, revisao_espacada, taticas, taticas_arquivo
from chess_diagram_ocr.engine import EngineAnalyzer

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import painel_de_estudo as qt_estudo
    from chess_diagram_ocr.qt import painel_de_treino as qt_treino

HOJE = date(2026, 9, 4)
LIVRO = "C:/PDF/Reinfeld 1001.pdf"


def _girar(app: Any, condicao: Any, limite_s: float = 20.0) -> bool:
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        app.processEvents()
        if condicao():
            return True
        time.sleep(0.005)
    return False


def _exercicio(diagrama: int = 0, *, lances: tuple[str, ...] = ("Qxf7#",)) -> taticas.Exercicio:
    """O mate do pastor, que é o exercício mais curto que existe."""
    return taticas.Exercicio(
        fen="r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 1",
        lances=lances,
        procedencia=taticas.Procedencia(
            livro=LIVRO, pagina=62, diagrama=diagrama, numero=214, folha_impressa=63
        ),
        desfecho=taticas.MATE,
    )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class JanelaDeTreinoTests(unittest.TestCase):
    """A fila do dia, um exercício por vez."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def janela(self, **kwargs: Any) -> Any:
        kwargs.setdefault("exercicios", [_exercicio()])
        kwargs.setdefault("hoje", HOJE)
        montada = qt_treino.JanelaDeTreino(None, **kwargs)
        self.addCleanup(descartar, montada)
        return montada

    def test_a_agenda_abre_com_o_exercicio_e_a_procedencia(self) -> None:
        janela = self.janela()
        self.assertEqual(1, janela.agenda.quantos)
        self.assertIsNotNone(janela.exercicio)
        self.assertIn("exercício 214", janela.lbl_procedencia.text())
        self.assertIn("Brancas jogam", janela.lbl_vez.text())
        self.assertFalse(janela.tabuleiro.isHidden(), "com exercício aberto o tabuleiro está lá")

    def test_o_tabuleiro_nasce_virado_para_quem_resolve(self) -> None:
        """Resolver de cabeça para baixo é outro exercício."""
        das_brancas = self.janela()
        self.assertFalse(das_brancas.tabuleiro.virado)
        pretas = taticas.Exercicio(
            fen="r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR b KQkq - 0 1",
            lances=("Nd4",),
            procedencia=taticas.Procedencia(livro=LIVRO, pagina=1, diagrama=0, numero=1),
        )
        self.assertTrue(self.janela(exercicios=[pretas]).tabuleiro.virado)

    def test_acertar_fecha_o_exercicio_e_agenda_como_bom(self) -> None:
        janela = self.janela()
        janela.jogar(chess.Move.from_uci("f3f7"))
        self.assertTrue(janela.tentativa.terminou)
        self.assertIn("Solução", janela.lbl_recado.text())
        estado = janela.baralho[_exercicio().chave]
        self.assertEqual(revisao_espacada.BOM, estado.historico[-1].nota)

    def test_errar_nao_anda_a_linha_e_desfaz_o_lance_na_tela(self) -> None:
        """**O defeito que a S-290 deixou passar**: sem redesenhar, a pessoa fica olhando uma
        posição que o exercício não tem, e o lance seguinte parte dela."""
        janela = self.janela()
        # `Nh3` e não `Nf3`: a dama está em f3, e `chess.Board.san` **não** recusa lance ilegal
        # quando há peça na casa de origem -- ela devolve "Nf3" e o exercício seguiria sobre uma
        # posição impossível. É por isso que `jogar` confere a legalidade antes de qualquer coisa.
        janela.jogar(chess.Move.from_uci("g1h3"))
        self.assertEqual("Qxf7#", janela.tentativa.esperado)
        self.assertEqual(1, janela.tentativa.erros)
        self.assertEqual(janela.exercicio.fen, janela.tabuleiro.modelo.board.fen())

    def test_o_lance_ilegal_nao_derruba_o_processo(self) -> None:
        """`chess.Board.san` levanta para lance ilegal sem peça na origem, e uma exceção num slot
        do Qt mata o processo sem mensagem. O widget só emite lance legal -- e mesmo assim."""
        janela = self.janela()
        janela.jogar(chess.Move.from_uci("a1a8"))
        self.assertEqual(0, janela.tentativa.erros)
        self.assertEqual("Qxf7#", janela.tentativa.esperado)

    def test_acertar_depois_de_errar_agenda_como_dificil(self) -> None:
        janela = self.janela()
        janela.jogar(chess.Move.from_uci("g1h3"))
        janela.jogar(chess.Move.from_uci("f3f7"))
        estado = janela.baralho[_exercicio().chave]
        self.assertEqual(revisao_espacada.DIFICIL, estado.historico[-1].nota)

    def test_ver_a_solucao_conta_como_nao_sabido(self) -> None:
        """Ver a resposta é não saber a resposta, e a agenda trata os dois igual."""
        janela = self.janela()
        janela.revelar()
        estado = janela.baralho[_exercicio().chave]
        self.assertEqual(revisao_espacada.DE_NOVO, estado.historico[-1].nota)
        self.assertIn("Qxf7#", janela.lbl_recado.text())
        self.assertFalse(janela.btn_facil.isEnabled(), "não se marca fácil o que não se soube")

    def test_o_facil_so_existe_depois_de_acertar_e_estica_o_intervalo(self) -> None:
        """O programa nunca dá esta nota sozinho: ela é um julgamento sobre a própria memória."""
        janela = self.janela()
        self.assertFalse(janela.btn_facil.isEnabled())
        janela.jogar(chess.Move.from_uci("f3f7"))
        self.assertTrue(janela.btn_facil.isEnabled())
        bom = janela.baralho[_exercicio().chave].vencimento
        janela.marcar_facil()
        self.assertGreater(janela.baralho[_exercicio().chave].vencimento, bom)

    def test_a_resposta_do_adversario_e_jogada_sozinha(self) -> None:
        """Pedir que a pessoa jogue os dois lados transformaria a combinação numa digitação."""
        longo = taticas.Exercicio(
            fen="r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 1",
            lances=("Bxf7+", "Ke7", "Qd5"),
            procedencia=taticas.Procedencia(livro=LIVRO, pagina=1, diagrama=0, numero=1),
        )
        janela = self.janela(exercicios=[longo])
        janela.jogar(chess.Move.from_uci("c4f7"))
        self.assertEqual("Qd5", janela.tentativa.esperado)
        # O tabuleiro já andou os **dois** meios-lances: o da pessoa e a resposta do gabarito.
        self.assertEqual(2, janela.tabuleiro.modelo.board.fullmove_number)
        self.assertTrue(janela.tabuleiro.modelo.board.turn, "a vez voltou para quem resolve")

    def test_a_fila_acaba_com_resumo_da_sessao_e_sem_tabuleiro(self) -> None:
        """**Três defeitos numa tela só, medidos em 2026-09-04** (S-540, r2): a agenda continuava
        anunciando "Hoje você tem 3 para revisar" ao lado de "Fila concluída"; não havia resumo
        nenhum de meia hora de sessão; e o tabuleiro ficava na última posição jogada, que já não é
        pergunta."""
        janela = self.janela()
        janela.jogar(chess.Move.from_uci("f3f7"))
        janela._proximo()
        self.assertIsNone(janela.exercicio)
        self.assertIn("concluída", janela.lbl_vazio.text())
        self.assertIn("1 exercício(s)", janela.lbl_vazio.text())
        self.assertIn("1 de 1", janela.lbl_vazio.text(), "o placar da sessão entra no resumo")
        self.assertEqual("", janela.lbl_agenda.text(), "a agenda de meia hora atrás se apaga")
        self.assertTrue(janela.tabuleiro.isHidden(), "não há posição a olhar")
        self.assertTrue(janela.btn_proximo.isHidden(), "três botões cinza não são assunto")
        self.assertFalse(janela.btn_proximo.isEnabled())

    def test_fechar_grava_o_baralho(self) -> None:
        caminho = self.pasta / "revisao.json"
        janela = self.janela(gravar=lambda baralho: revisao_arquivo.gravar(baralho, caminho=caminho))
        janela.jogar(chess.Move.from_uci("f3f7"))
        janela.reject()
        self.app.processEvents()
        self.assertEqual([_exercicio().chave], list(revisao_arquivo.carregar(caminho=caminho)))

    def test_um_item_ja_revisto_hoje_nao_volta_na_fila_de_hoje(self) -> None:
        """**E a fila vazia diz quando o material volta, sem desenhar tabuleiro** (S-540, r2). A
        tela mostrava 64 casas vazias em 60% da janela e a mesma frase de "nenhum exercício
        extraído" -- que manda extrair o que já está extraído."""
        vencimento = revisao_espacada.estado_inicial(_exercicio().chave, revisao_espacada.BOM, hoje=HOJE)
        janela = self.janela(baralho={vencimento.chave: vencimento})
        self.assertTrue(janela.agenda.vazia)
        frase = janela.lbl_vazio.text()
        self.assertIn("Nada vence hoje", frase)
        self.assertIn("/2026", frase, "a data do próximo vencimento")
        self.assertIn("1 exercício(s)", frase, "e o tamanho da coleção que já existe")
        self.assertNotIn("extraia", frase.lower())
        self.assertTrue(janela.tabuleiro.isHidden())

    def test_o_placar_conta_na_janela_e_no_livro(self) -> None:
        placar = placar_mod.Placar()
        janela = self.janela(placar=placar)
        janela.jogar(chess.Move.from_uci("g1h3"))
        janela.jogar(chess.Move.from_uci("f3f7"))
        self.assertEqual(2, placar.sessao.total)
        self.assertEqual(1, placar.do_livro(LIVRO).certos)
        self.assertIn("sessão: 1 de 2", janela.lbl_placar.text())

    def test_o_placar_da_janela_de_treino_vai_para_o_disco(self) -> None:
        """**O defeito 3 da segunda rodada, e ele era total** (S-541, r2). `done()` gravava só o
        baralho de revisão; o placar vivia num objeto na memória e `placar.json` **nunca era
        criado**. A spec afirmava "sobrevive a desligar ✅" sobre um arquivo que não existia."""
        caminho = self.pasta / "placar.json"
        placar = placar_mod.carregar(caminho=caminho)
        janela = self.janela(placar=placar)
        self.assertFalse(caminho.exists())
        janela.jogar(chess.Move.from_uci("f3f7"))
        self.assertTrue(caminho.exists(), "uma gravação por lance, como na sala (S-541)")
        self.assertEqual(1, placar_mod.carregar(caminho=caminho).do_livro(LIVRO).certos)

    def test_placar_sem_origem_nao_grava_na_arvore_do_programa(self) -> None:
        """`Placar()` de teste, ou de quem colou uma posição à mão, não veio do disco -- e
        `placar.gravar` cairia em `CAMINHO_PADRAO`, que é `data/placar.json` da instalação."""
        placar = placar_mod.Placar()
        self.assertIsNone(placar.origem)
        janela = self.janela(placar=placar)
        janela.jogar(chess.Move.from_uci("f3f7"))
        self.assertEqual(1, placar.sessao.total, "conta na memória")

    def test_o_enter_nao_revela_a_solucao_nem_reprova_o_exercicio(self) -> None:
        """**O defeito 4 da segunda rodada** (S-541, r2). `btn_solucao` era o primeiro botão criado
        e virava o botão padrão do diálogo; nenhum widget recebia foco na abertura. `Enter` então
        revelava o gabarito e reprovava o exercício -- estabilidade 0,4872, volta amanhã -- sem que
        ninguém tivesse jogado nada."""
        janela = self.janela()
        janela.show()
        janela.activateWindow()
        self.app.processEvents()
        self.assertTrue(janela.tabuleiro.hasFocus(), "o foco nasce onde se joga")
        for botao in (janela.btn_solucao, janela.btn_facil, janela.btn_proximo):
            self.assertFalse(botao.autoDefault(), f"{botao.text()} não é o botão padrão")
        QTest.keyClick(janela, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertFalse(janela.tentativa.revelou, "o Enter não desiste do exercício")
        self.assertEqual({}, janela.baralho, "e não agenda nada")
        self.assertEqual("", janela.lbl_recado.text())

    def test_a_tecla_de_avanco_passa_ao_seguinte_depois_de_o_exercicio_fechar(self) -> None:
        """**A sessão inteira pelo teclado**, que é como o Chessable e o Anki funcionam: não havia
        `QShortcut`, `keyPressEvent` nem `setFocus` nesta janela."""
        janela = self.janela(exercicios=[_exercicio(0), _exercicio(1)])
        janela.show()
        self.app.processEvents()
        primeiro = janela.exercicio
        janela.jogar(chess.Move.from_uci("f3f7"))
        QTest.keyClick(janela, Qt.Key.Key_Space)
        self.app.processEvents()
        self.assertIsNotNone(janela.exercicio)
        self.assertNotEqual(primeiro.chave, janela.exercicio.chave)

    def test_a_tecla_de_avanco_nao_pula_exercicio_em_aberto(self) -> None:
        """Um `Enter` distraído no meio de uma combinação pularia o item sem resposta, e a agenda
        o contaria como visto."""
        janela = self.janela(exercicios=[_exercicio(0), _exercicio(1)])
        janela.show()
        self.app.processEvents()
        primeiro = janela.exercicio
        janela.avancar()
        self.assertEqual(primeiro.chave, janela.exercicio.chave)

    def test_o_tabuleiro_do_treino_ocupa_a_coluna_e_nao_560_px(self) -> None:
        """**O defeito 5 da segunda rodada** (S-539, r2). Sem `definir_fracao`, o tabuleiro ficava
        preso no `MAX_DO_TABULEIRO` de 560 px em toda janela e em toda pele -- 15% da área a
        1400×950, com 861 px de vazio na coluna direita. A sala de estudo já chamava `definir_fracao`
        pela mesma razão (S-518), e a janela cujo assunto é olhar para uma posição não chamava."""
        from chess_diagram_ocr.qt.tabuleiro import MAX_DO_TABULEIRO

        janela = self.janela()
        janela.resize(1400, 950)
        janela.show()
        self.app.processEvents()
        lado = janela.tabuleiro.geometria().size
        self.assertGreater(lado, MAX_DO_TABULEIRO, "o teto do canvas do Tk deixou de valer aqui")

    def test_o_lance_errado_fica_marcado_no_tabuleiro(self) -> None:
        """**O erro não tinha sinal nenhum na tela** (S-541, r2): a peça voltava sozinha para a
        casa de origem, e quem move rápido joga o mesmo lance de novo achando que soltou fora da
        casa. A seta vermelha é o mecanismo que a S-279 já tem."""
        janela = self.janela()
        janela.jogar(chess.Move.from_uci("g1h3"))
        setas = list(janela.tabuleiro.modelo.arrows)
        self.assertEqual(1, len(setas))
        self.assertEqual(qt_treino.COR_DO_ERRO, setas[0][2])
        janela.jogar(chess.Move.from_uci("f3f7"))
        self.assertEqual((), janela.tabuleiro.modelo.arrows, "o acerto limpa a marca")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PerdaDoLanceTests(unittest.TestCase):
    """A comparação com o motor, contra um processo UCI de verdade (o de mentira)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = _launcher(cls)

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def test_sem_motor_o_pedido_e_recusado_e_nada_fica_pendurado(self) -> None:
        """A frase de "certo ou errado" já chegou; o número é o que não existe sem motor."""
        medidor = qt_treino.PerdaDoLance(analisador=None)
        self.assertFalse(medidor.pedir(chess.Board(), chess.Move.from_uci("e2e4"), "x"))
        self.assertFalse(medidor.ocupado)

    def test_a_perda_volta_por_sinal_e_a_avaliacao_de_antes_e_reusada(self) -> None:
        """**Errar três vezes não custa seis buscas**: a posição antes do lance é a mesma."""
        respostas: list[tuple[Any, int]] = []
        with EngineAnalyzer(self.launcher, movetime_ms=50) as motor:
            medidor = qt_treino.PerdaDoLance(analisador=motor)
            medidor.pronta.connect(lambda ficha, perda: respostas.append((ficha, perda)))
            self.assertTrue(medidor.pedir(chess.Board(), chess.Move.from_uci("e2e4"), "um"))
            self.assertTrue(_girar(self.app, lambda: bool(respostas)))
            self.assertEqual("um", respostas[0][0])
            self.assertGreaterEqual(respostas[0][1], 0)
            guardadas = len(medidor._antes)
            self.assertTrue(medidor.pedir(chess.Board(), chess.Move.from_uci("d2d4"), "dois"))
            self.assertTrue(_girar(self.app, lambda: len(respostas) > 1))
            self.assertEqual(guardadas, len(medidor._antes), "a posição de antes foi reavaliada")
            self.assertTrue(medidor.esperar(3000))

    def test_um_segundo_pedido_durante_o_primeiro_e_recusado(self) -> None:
        """Quem erra três lances em dois segundos quer a nota do último, não três atrasadas."""
        with EngineAnalyzer(self.launcher, movetime_ms=50) as motor:
            medidor = qt_treino.PerdaDoLance(analisador=motor)
            self.assertTrue(medidor.pedir(chess.Board(), chess.Move.from_uci("e2e4"), "um"))
            self.assertFalse(medidor.pedir(chess.Board(), chess.Move.from_uci("d2d4"), "dois"))
            self.assertTrue(medidor.esperar(5000))
            self.app.processEvents()


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TreinoNaSalaTests(unittest.TestCase):
    """O que a S-541 mudou na sala de estudo."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = _launcher(cls)

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def sala(self, **kwargs: Any) -> Any:
        kwargs.setdefault("pasta_de_treino", self.pasta)
        montada = qt_estudo.PainelDeEstudo(
            pasta_inicial=self.pasta, pasta_de_estudos=self.pasta, **kwargs
        )
        self.addCleanup(descartar, montada)
        return montada

    def _com_linha(self, painel: Any, *, livro: str = "") -> None:
        if livro:
            painel.abrir_livro(livro)
        painel.push_move(chess.Move.from_uci("e2e4"))
        painel.push_move(chess.Move.from_uci("e7e5"))
        painel.go_to_start_of_line()

    def test_o_placar_do_livro_sobrevive_a_desligar_o_treino(self) -> None:
        """**O item inteiro da S-541**: desligar o treino é o gesto declarado para guardar um lance
        que se quis jogar, e ele apagava a tarde toda."""
        painel = self.sala()
        self._com_linha(painel, livro=LIVRO)
        painel.alternar_treino()
        painel.push_move(chess.Move.from_uci("e2e4"))
        painel.alternar_treino()
        painel.alternar_treino()
        self.assertEqual(0, painel.placar.sessao.total, "a sessão zera")
        self.assertEqual(1, painel.placar.total.total, "o livro não zera")

    def test_o_placar_esta_no_disco_depois_do_lance(self) -> None:
        """Uma gravação por lance: o arquivo tem alguns bytes, e o que se perde numa queda é a
        sessão que ninguém vai repetir."""
        painel = self.sala()
        self._com_linha(painel, livro=LIVRO)
        painel.alternar_treino()
        painel.push_move(chess.Move.from_uci("e2e4"))
        lido = placar_mod.carregar(caminho=self.pasta / "placar.json")
        self.assertEqual(1, lido.total.total)

    def test_sem_motor_a_frase_do_erro_nao_promete_numero(self) -> None:
        painel = self.sala()
        self._com_linha(painel)
        painel.alternar_treino()
        painel.push_move(chess.Move.from_uci("d2d4"))
        self.assertIn("não é o lance da linha", painel.lbl_status.text())
        self.assertNotIn("perde", painel.lbl_status.text())
        self.assertEqual(1, painel.placar.sessao.errados)

    def test_com_motor_a_frase_e_escrita_duas_vezes(self) -> None:
        """O veredicto chega na hora; o preço chega quando o motor termina."""
        with EngineAnalyzer(self.launcher, movetime_ms=50) as motor:
            painel = self.sala(analyzer=motor)
            self._com_linha(painel)
            painel.alternar_treino()
            painel.push_move(chess.Move.from_uci("d2d4"))
            self.assertIn("perguntando ao motor", painel.lbl_status.text())
            self.assertTrue(_girar(self.app, lambda: painel.placar.sessao.total > 0))
            self.assertIn("d4", painel.lbl_status.text())
            self.assertTrue(painel._medidor_da_perda().esperar(5000))
            self.app.processEvents()

    def test_o_lance_da_linha_e_certo_e_anda(self) -> None:
        painel = self.sala()
        self._com_linha(painel)
        painel.alternar_treino()
        painel.push_move(chess.Move.from_uci("e2e4"))
        self.assertEqual("e4", painel.estudo.no.san())
        self.assertEqual(1, painel.placar.sessao.certos)

    def test_o_fim_da_linha_nao_cobra_lance(self) -> None:
        painel = self.sala()
        self._com_linha(painel)
        painel.go_to_end_of_line()
        painel.alternar_treino()
        painel.push_move(chess.Move.from_uci("d2d4"))
        self.assertIn("Fim da linha", painel.lbl_status.text())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TaticasNaSalaTests(unittest.TestCase):
    """Os dois comandos novos da barra (S-539/S-540)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def sala(self, **kwargs: Any) -> Any:
        kwargs.setdefault("pasta_de_treino", self.pasta)
        montada = qt_estudo.PainelDeEstudo(
            pasta_inicial=self.pasta, pasta_de_estudos=self.pasta, **kwargs
        )
        self.addCleanup(descartar, montada)
        return montada

    def test_extrair_sem_livro_aberto_recusa_com_frase(self) -> None:
        painel = self.sala()
        self.assertIsNone(painel.extrair_taticas())
        self.assertIn("Abra um livro", painel.lbl_status.text())

    def test_a_agenda_sem_exercicio_nao_abre_janela_vazia(self) -> None:
        """Uma tela de treino vazia não diz o que fazer; a frase diz, e nomeia o comando."""
        painel = self.sala()
        self.assertIsNone(painel.treinar_a_agenda())
        self.assertIn("Táticas do livro", painel.lbl_status.text())

    def test_a_agenda_abre_com_o_que_a_extracao_gravou(self) -> None:
        taticas_arquivo.gravar(LIVRO, [_exercicio()], pasta=self.pasta / "taticas")
        painel = self.sala()
        janela = painel.treinar_a_agenda()
        self.assertIsNotNone(janela)
        self.addCleanup(descartar, janela)
        self.assertEqual(1, janela.agenda.quantos)
        janela.reject()
        self.app.processEvents()
        self.assertTrue((self.pasta / "revisao.json").exists(), "fechar gravou o baralho")

    def test_o_que_venceu_amanha_nao_esta_na_fila_de_hoje(self) -> None:
        """A ponte entre os dois arquivos: a agenda lê o baralho que a sessão anterior gravou."""
        taticas_arquivo.gravar(LIVRO, [_exercicio()], pasta=self.pasta / "taticas")
        estado = revisao_espacada.estado_inicial(
            _exercicio().chave, revisao_espacada.FACIL, hoje=date.today() + timedelta(days=1)
        )
        revisao_arquivo.gravar({estado.chave: estado}, caminho=self.pasta / "revisao.json")
        painel = self.sala()
        janela = painel.treinar_a_agenda()
        self.addCleanup(descartar, janela)
        self.assertTrue(janela.agenda.vazia)

    def test_o_placar_da_sessao_de_treino_nasce_na_pasta_de_treino(self) -> None:
        """**A ponta a ponta do defeito 3** (S-541, r2): a sala carrega `placar.json` da pasta de
        treino e passa o objeto para a janela; sem `Placar.origem` a janela não tinha como saber
        que pasta é essa, e o arquivo nunca era criado."""
        taticas_arquivo.gravar(LIVRO, [_exercicio()], pasta=self.pasta / "taticas")
        painel = self.sala()
        janela = painel.treinar_a_agenda()
        self.addCleanup(descartar, janela)
        janela.jogar(chess.Move.from_uci("f3f7"))
        alvo = self.pasta / "placar.json"
        self.assertTrue(alvo.exists())
        self.assertEqual(1, placar_mod.carregar(caminho=alvo).do_livro(LIVRO).certos)

    def test_os_dois_comandos_tem_metodo_e_botao_no_mais(self) -> None:
        from chess_diagram_ocr.ui import barra_da_sala

        painel = self.sala()
        for acao in ("taticas_do_livro", "treinar_agenda"):
            with self.subTest(acao=acao):
                registro = barra_da_sala.acao(acao)
                self.assertEqual(barra_da_sala.TREINO, registro.grupo)
                self.assertFalse(registro.principal, "os dois moram no Mais")
                self.assertTrue(callable(getattr(painel, registro.metodo, None)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
