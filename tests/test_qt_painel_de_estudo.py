"""A sala de estudo do segundo frontend (S-268 a S-290, S-503).

**O que estes testes cobrem, e o que não.** A árvore, a âncora, a numeração de variante, a pilha
de desfazer, o motor e os três formatos de saída são puros e já são afirmados sem janela --
`tests/test_estudo*.py`, `tests/test_ui_estudo_lista.py`, `tests/test_engine.py`. A tabela de
comandos e as seis medidas são de `ui/sala_declarada.py`. Nada disso é remedido aqui.

O que só existe deste lado são as cinco coisas em que o Qt difere do Tk e que quebram calado:

1. **A tabela `comando -> método` tem de bater com os métodos que existem.** É o critério da
   S-280 aplicado ao segundo frontend: um método com outro nome deixa o comando no menu sem fazer
   nada, e nada acusa.
2. **`setChecked` dispara sinal**, e `refresh` marca botões: sem a guarda `_montando`, redesenhar
   a tela ligaria o treino ou o recorte sozinho.
3. **Virar o tabuleiro não pode subir `edicao`** (S-346): é `edicao` que diz a `ui/desfazivel.py`
   qual painel recebe o `Ctrl+Z`, e virar o tabuleiro sequestrava a tecla.
4. **A resposta atrasada do motor é descartada pela geração** (S-285), e a geração cresce em
   `refresh` -- o único ponto por onde toda mudança de nó passa.
5. **O relógio de gravação não pode ser reiniciado pela escrita da máquina** (S-345): com a
   análise contínua ligada, a sala nunca era gravada.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import chess
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.estudo import Ancora, PosicaoDeEstudo
from chess_diagram_ocr.ui import comandos, sala_declarada, strings

if TEM_PYQT:
    from chess_diagram_ocr.qt import painel_de_estudo as qt_estudo


class DeclaracaoTests(unittest.TestCase):
    """A decisão é a mesma dos dois lados, e nenhum dos dois a reescreve."""

    def test_a_tabela_nao_declara_comando_fora_do_catalogo(self) -> None:
        """O critério de aceite da S-280, e ele não mudou de dono."""
        self.assertEqual(comandos.acoes_fora_do_catalogo(sala_declarada.COMANDOS_DA_ABA), [])

    def test_a_cor_da_seta_e_a_ordem_do_lichess(self) -> None:
        cor = sala_declarada.cor_de_seta_por_modificador
        self.assertEqual(cor(shift=False, alt=False, ctrl=False), "green")
        self.assertEqual(cor(shift=True, alt=False, ctrl=False), "red")
        self.assertEqual(cor(shift=False, alt=True, ctrl=False), "blue")
        self.assertEqual(cor(shift=False, alt=False, ctrl=True), "yellow")
        # Shift ganha de todos: a prioridade é a ordem, e não a soma.
        self.assertEqual(cor(shift=True, alt=True, ctrl=True), "red")

    def test_o_modulo_puro_nao_carrega_tkinter(self) -> None:
        import ast

        arvore = ast.parse(Path(sala_declarada.__file__).read_text(encoding="utf-8"))
        nomes = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
        nomes |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
        self.assertNotIn("tkinter", nomes)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class SalaTests(unittest.TestCase):
    """A sala montada, sem motor e sem livro."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def sala(self, **kwargs: object) -> qt_estudo.PainelDeEstudo:
        montada = qt_estudo.PainelDeEstudo(
            pasta_inicial=self.pasta, pasta_de_estudos=self.pasta, **kwargs  # type: ignore[arg-type]
        )
        self.addCleanup(descartar, montada)
        montada.resize(1000, 700)
        montada.show()
        self.app.processEvents()
        return montada

    def test_todo_comando_do_catalogo_tem_metodo_neste_painel(self) -> None:
        """**O critério da S-280 aplicado ao segundo frontend.** Um método com outro nome deixa o
        comando no menu, na paleta e nas três peles -- sem fazer nada, e sem nada acusar."""
        painel = self.sala()
        faltando = [
            f"{acao} -> {metodo}"
            for acao, metodo in sala_declarada.COMANDOS_DA_ABA.items()
            if not callable(getattr(painel, metodo, None))
        ]
        self.assertEqual(faltando, [])

    def test_o_campo_da_fen_mostra_o_comeco_e_nao_o_fim_num_painel_estreito(self) -> None:
        """A FEN visivel comeca em `rnbqkbnr`, e nao em `qkbnr` (F9-C6, achado nas capturas).

        **Este defeito foi achado olhando, e nenhuma medida de layout o pegava.** A 1280x800 o
        campo da FEN da aba Estudo aparecia como `qkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq
        - 0 1`: `QLineEdit.setText` deixa o cursor no fim, o campo rola para o fim, e as tres
        primeiras casas somem **sem reticencia e sem nenhum sinal**. Nao ha rotulo espremido nem
        controle fora da janela -- so texto rolado --, entao as varreduras de sobreposicao, de
        colapso e de rotulo cortado passavam todas. Quem le a FEN na tela copia uma FEN invalida.

        **A regua e o pixel, e nao o cursor.** `cursorPositionAt` responde qual caractere esta
        desenhado numa coordenada da tela: pedir o caractere da **borda esquerda de dentro** do
        campo e perguntar "o que o usuario ve primeiro?". Afirmar so `cursorPosition() == 0`
        mediria a intencao; isto mede o desenho.
        """
        from PyQt6.QtCore import QPoint

        painel = self.sala()
        painel.resize(560, 700)
        self.app.processEvents()
        campo = painel.campo_fen
        fen = campo.text()
        self.assertTrue(fen.startswith("rnbqkbnr"), f"a FEN inicial mudou: {fen!r}")
        self.assertGreater(
            campo.fontMetrics().horizontalAdvance(fen),
            campo.width(),
            "o campo coube inteiro: neste tamanho o teste nao prova nada -- estreite-o mais",
        )
        dentro = QPoint(4, campo.height() // 2)
        self.assertEqual(
            0,
            campo.cursorPositionAt(dentro),
            "o campo esta desenhando o FIM da FEN: o comeco, que identifica a posicao, saiu da "
            f"vista sem reticencia nenhuma -- ve-se {fen[campo.cursorPositionAt(dentro):][:12]!r}",
        )

    def test_a_fen_que_nao_cabe_desenha_a_reticencia_em_toda_largura(self) -> None:
        """**A ponta direita nao pode sumir em silencio** (F9-C7, §4.5).

        O teste acima monta o caso cortado -- ele **assegura** que o campo e' estreito demais --
        e verifica so de que lado o corte cai. Enquanto a ponta direita sumisse sem sinal, ele
        nao tinha como reprovar: e' o mesmo feitio de portao cego que fechou este ciclo, um
        instrumento que mede metade da pergunta que ele mesmo escreveu.

        O crítico mediu a outra metade em quatro larguras: **3 a 33 caracteres perdidos, sem
        reticencia e sem sinal**, a 1366, 1280 e 1024. E o prefixo e' o caso perigoso --
        `rnbqkbnr/.../RNBQ` **parece** uma FEN completa, enquanto o sufixo que se via antes do
        ciclo 6 (`...RNBQKBNR w KQkq - 0 1`) nao parecia.

        A regua e' o `grab()`: conta **tinta** na faixa da marca, e nao o estado interno do
        widget. Um campo que ligasse a marca sem desenha-la passaria numa asserção sobre
        `textMargins()`, e essa e' exatamente a forma de cegueira deste ciclo.
        """
        larguras = (720, 560, 460, 380)
        painel = self.sala()
        for largura in larguras:
            with self.subTest(largura=largura):
                painel.resize(largura, 700)
                self.app.processEvents()
                campo = painel.campo_fen
                campo.setText("r1bq1rk1/pp2ppbp/2np1np1/2p5/2P1P3/2NP1NP1/PP2BP1P/R1BQ1RK1 w - - 12 129")
                campo.setCursorPosition(0)
                self.app.processEvents()
                if not campo.texto_cortado():
                    self.assertEqual(0, campo.textMargins().right(), "marca acesa sem corte")
                    continue
                faixa = campo.textMargins().right()
                self.assertGreater(faixa, 0, "a FEN foi cortada e nenhuma faixa foi reservada")
                imagem = campo.grab().toImage()
                fundo = imagem.pixel(imagem.width() - 1, 1)
                tinta = sum(
                    1
                    for x in range(imagem.width() - faixa, imagem.width())
                    for y in range(imagem.height())
                    if imagem.pixel(x, y) != fundo
                )
                self.assertGreater(
                    tinta,
                    0,
                    "a faixa da marca esta reservada e VAZIA: a FEN continua sumindo em silencio",
                )

    def test_a_fen_que_cabe_nao_ganha_marca_nenhuma(self) -> None:
        """O outro lado: um aviso permanente e ruido, e ruido permanente se aprende a nao ver."""
        painel = self.sala()
        painel.resize(900, 700)
        self.app.processEvents()
        campo = painel.campo_fen
        campo.setText("8/8/8/4k3/8/4K3/8/8 w - - 0 1")
        self.app.processEvents()
        self.assertFalse(campo.texto_cortado())
        self.assertEqual(0, campo.textMargins().right(), "marca acesa com a FEN inteira na tela")

    def test_o_texto_do_campo_da_fen_nunca_e_elidido(self) -> None:
        """A marca e' **desenho**; o `text()` continua inteiro, porque o campo e' editavel.

        Elidir o `text()` de um campo editavel corromperia o que `apply_fen` le -- e a FEN
        elidida seria gravada como se fosse a posicao. E' a razao de a reticencia ser pintada e
        nao escrita.
        """
        fen = "r1bq1rk1/pp2ppbp/2np1np1/2p5/2P1P3/2NP1NP1/PP2BP1P/R1BQ1RK1 w - - 12 129"
        painel = self.sala()
        painel.resize(380, 700)
        self.app.processEvents()
        painel.campo_fen.setText(fen)
        self.app.processEvents()
        self.assertTrue(painel.campo_fen.texto_cortado())
        self.assertEqual(fen, painel.campo_fen.text())
        self.assertNotIn("\u2026", painel.campo_fen.text())

    def test_o_campo_da_fen_continua_mostrando_o_comeco_depois_de_um_lance(self) -> None:
        """`refresh()` reescreve a FEN, e era o `setText` dele que rolava o campo para o fim."""
        from PyQt6.QtCore import QPoint

        painel = self.sala()
        painel.resize(560, 700)
        painel.push_move(chess.Move.from_uci("e2e4"))
        self.app.processEvents()
        campo = painel.campo_fen
        dentro = QPoint(4, campo.height() // 2)
        self.assertEqual(0, campo.cursorPositionAt(dentro), campo.text())

    def test_jogar_um_lance_entra_na_arvore_e_na_lista(self) -> None:
        painel = self.sala()
        painel.push_move(chess.Move.from_uci("e2e4"))
        self.assertEqual(painel.estudo.contagem_de_lances(), 1)
        self.assertIn("e4", painel.lista.toPlainText())

    def test_o_lance_igual_segue_e_o_diferente_ramifica(self) -> None:
        """É o comportamento do ChessBase, e era o único acerto de peso que a aba já tinha."""
        painel = self.sala()
        painel.push_move(chess.Move.from_uci("e2e4"))
        painel.undo_move()
        painel.push_move(chess.Move.from_uci("e2e4"))
        self.assertEqual(len(painel.estudo.raiz.variations), 1, "seguiu em vez de duplicar")
        painel.undo_move()
        painel.push_move(chess.Move.from_uci("d2d4"))
        self.assertEqual(len(painel.estudo.raiz.variations), 2, "o diferente ramificou")

    def test_navegar_anda_e_diz_quando_nao_ha_para_onde(self) -> None:
        painel = self.sala()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.undo_move()
        painel.go_to_start_of_line()
        self.assertTrue(any("Não ha lances para desfazer" in frase for frase in vistos))
        self.assertTrue(any("Já esta no inicio da linha" in frase for frase in vistos))

    def test_o_comentario_vai_no_no_em_que_foi_escrito(self) -> None:
        """Navegar troca o nó corrente antes de a caixa perder o foco, e gravar no corrente poria
        o comentário de um lance em outro."""
        painel = self.sala()
        painel.push_move(chess.Move.from_uci("e2e4"))
        no_do_e4 = painel.estudo.no
        painel.comentario.setPlainText("boa ideia")
        painel.push_move(chess.Move.from_uci("e7e5"))
        self.assertIn("boa ideia", no_do_e4.comment)
        self.assertNotIn("boa ideia", painel.estudo.no.comment or "")

    def test_o_comentario_nao_apaga_as_setas_do_mesmo_lance(self) -> None:
        """Setas e avaliação moram no mesmo campo do PGN: `no.comment = novo` as apagaria (S-268)."""
        painel = self.sala()
        painel.push_move(chess.Move.from_uci("e2e4"))
        painel.on_arrow(52, 36, "red")
        painel.comentario.setPlainText("uma nota")
        painel.gravar_comentario()
        self.assertIn("uma nota", painel.estudo.no.comment)
        self.assertIn("%cal", painel.estudo.no.comment)

    def test_o_simbolo_alterna_e_aparece_ao_lado(self) -> None:
        painel = self.sala()
        painel.push_move(chess.Move.from_uci("e2e4"))
        painel.alternar_nag(1)
        self.assertEqual(sorted(painel.estudo.no.nags), [1])
        self.assertTrue(painel.lbl_simbolo.text())
        painel.alternar_nag(1)
        self.assertEqual(sorted(painel.estudo.no.nags), [])

    def test_a_raiz_nao_recebe_simbolo(self) -> None:
        painel = self.sala()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.alternar_nag(1)
        self.assertTrue(any("não recebe símbolo" in frase for frase in vistos))

    def test_virar_o_tabuleiro_nao_conta_como_edicao(self) -> None:
        """**É `edicao` que diz a `ui/desfazivel.py` qual painel recebe o `Ctrl+Z`** (S-346).

        A orientação é vista, e não árvore: `para_pgn` não muda com ela. Com `edicao` subindo,
        virar o tabuleiro sequestrava a tecla -- ela vinha para a sala e não desfazia nada,
        enquanto a edição real de quem estava no editor ao lado ficava lá, sem quem a desfizesse.
        """
        painel = self.sala()
        painel.push_move(chess.Move.from_uci("e2e4"))
        antes = painel.edicao
        painel.flip_board()
        self.assertTrue(painel.estudo.invertido)
        self.assertEqual(painel.edicao, antes)
        self.assertTrue(painel.tem_trabalho_por_gravar(), "e continua sujando a sala")

    def test_desfazer_recarrega_o_pgn_e_volta_ao_lance(self) -> None:
        painel = self.sala()
        painel.push_move(chess.Move.from_uci("e2e4"))
        painel.push_move(chess.Move.from_uci("e7e5"))
        painel.desfazer()
        self.assertEqual(painel.estudo.contagem_de_lances(), 1)
        painel.refazer()
        self.assertEqual(painel.estudo.contagem_de_lances(), 2)

    def test_desfazer_sem_nada_vira_frase(self) -> None:
        painel = self.sala()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.desfazer()
        self.assertTrue(any("Não há nada para desfazer" in frase for frase in vistos))

    def test_redesenhar_nao_liga_o_treino_nem_o_recorte(self) -> None:
        """`setChecked` dispara sinal, e `refresh` mexe em botões marcáveis."""
        painel = self.sala()
        painel.refresh()
        self.assertFalse(painel.btn_treino.isChecked())
        self.assertFalse(painel.btn_recorte.isChecked())

    def test_o_recorte_fica_cinza_sem_ancora(self) -> None:
        """A dica dele promete "fica cinza quando o estudo não veio de um diagrama do livro"
        desde a S-282, e ele nunca ficava (S-347)."""
        painel = self.sala()
        self.assertFalse(painel.btn_recorte.isEnabled())
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.alternar_recorte()
        self.assertFalse(painel.btn_recorte.isChecked(), "não liga o que não tem o que mostrar")
        self.assertTrue(any("não veio de um diagrama do livro" in frase for frase in vistos))

    def test_o_treino_esconde_a_continuacao_e_nao_muda_a_arvore(self) -> None:
        """"A linha some, e o tabuleiro cobra o lance" -- e errar não cria variante (S-290)."""
        painel = self.sala()
        painel.push_move(chess.Move.from_uci("e2e4"))
        painel.push_move(chess.Move.from_uci("e7e5"))
        painel.go_to_start_of_line()
        painel.alternar_treino()
        self.assertNotIn("e4", painel.lista.toPlainText(), "a continuação sumiu da tela")

        antes = painel.estudo.para_pgn()
        painel.push_move(chess.Move.from_uci("d2d4"))
        self.assertEqual(painel.estudo.para_pgn(), antes, "errar não criou variante")
        self.assertIn("errado", painel.lbl_placar.text())

        painel.push_move(chess.Move.from_uci("e2e4"))
        self.assertIn("certo", painel.lbl_placar.text())
        self.assertEqual(painel.estudo.no.san(), "e4", "acertar anda na linha")

    def test_a_fen_invalida_nao_troca_o_estudo(self) -> None:
        from PyQt6.QtWidgets import QMessageBox

        painel = self.sala()
        painel.push_move(chess.Move.from_uci("e2e4"))
        vistas: list[str] = []
        original = QMessageBox.critical
        QMessageBox.critical = staticmethod(lambda *args, **kwargs: vistas.append(args[1]))  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(QMessageBox, "critical", original))
        painel.campo_fen.setText("isto não é uma FEN")
        painel.apply_fen()
        self.assertEqual(vistas, ["FEN inválida"])
        self.assertEqual(painel.estudo.contagem_de_lances(), 1, "a árvore ficou como estava")

    def test_a_geracao_cresce_a_cada_mudanca_de_no(self) -> None:
        """É ela que descarta a resposta atrasada do motor, e ela cresce em `refresh` -- o único
        ponto por onde toda mudança de nó passa (S-285)."""
        painel = self.sala()
        antes = painel._geracao
        painel.push_move(chess.Move.from_uci("e2e4"))
        painel.undo_move()
        self.assertGreater(painel._geracao, antes + 1)

    def test_sem_motor_a_secao_nao_existe_e_os_comandos_dizem_isso(self) -> None:
        """Sem binário, a seção inteira não aparece -- em vez de aparecer cinza (S-33)."""
        painel = self.sala()
        self.assertFalse(painel.has_engine)
        self.assertIsNone(painel.btn_continua)
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.analyse()
        painel.alternar_analise_continua()
        painel.variante_do_motor()
        # **A frase saiu do literal e foi para o catálogo** (F9-C16): ela mandava "ponha o
        # Stockfish em engines/ e reabra", que era uma receita que não resolvia -- nada em `src/`
        # procurava o binário. Afirmar contra `strings.SEM_MOTOR_STATUS` é mais forte que afirmar
        # contra uma cópia do texto: um dia em que o catálogo mudar e o painel não, isto cai.
        self.assertEqual(len([f for f in vistos if strings.SEM_MOTOR_STATUS in f]), 3)

    def test_a_escrita_da_maquina_nao_adia_a_gravacao(self) -> None:
        """**Com a análise contínua ligada, a sala nunca era gravada** (S-345): o motor escreve a
        cada ~800 ms, e cada escrita reagendando fazia o prazo de inatividade nunca vencer."""
        painel = self.sala()
        painel._marcar_sujo()
        self.assertTrue(painel._relogio_de_gravacao.isActive())
        restante = painel._relogio_de_gravacao.remainingTime()
        painel._marcar_sujo(historico=False, da_maquina=True)
        self.assertLessEqual(
            painel._relogio_de_gravacao.remainingTime(), restante, "a máquina empurrou o relógio"
        )

    def test_a_sala_grava_no_disco_quando_ha_livro(self) -> None:
        painel = self.sala()
        # `abrir_livro` primeiro: é ele que dá documento à sala, e `salvar_agora` recusa gravar
        # uma sala sem livro -- não há nome de arquivo para ela.
        painel.abrir_livro("livro.pdf")
        painel._abrir(
            PosicaoDeEstudo(ancora=Ancora(documento="livro.pdf", pagina=3, diagrama=0)),
            origem="Base: teste",
            status="aberto",
        )
        painel.push_move(chess.Move.from_uci("e2e4"))
        caminho = painel.salvar_agora()
        self.assertIsNotNone(caminho)
        assert caminho is not None
        self.assertTrue(caminho.exists())
        self.assertFalse(painel.tem_trabalho_por_gravar())

    def test_reabrir_por_chave_volta_a_mesa(self) -> None:
        """Voltar ao livro sem voltar ao diagrama devolveria a pessoa à porta da sala (S-347)."""
        painel = self.sala()
        painel.abrir_livro("livro.pdf")
        ancora = Ancora(documento="livro.pdf", pagina=7, diagrama=1)
        painel._abrir(PosicaoDeEstudo(ancora=ancora), origem="Base: teste", status="aberto")
        painel.push_move(chess.Move.from_uci("d2d4"))
        chave = painel.chave_do_estudo_aberto
        painel.load_initial_position()
        self.assertTrue(painel.reabrir_por_chave(chave))
        self.assertEqual(painel.estudo.contagem_de_lances(), 1)
        self.assertFalse(painel.reabrir_por_chave("nao-existe"))

    def test_o_tab_sai_do_comentario_e_grava_sem_escrever_tabulacao(self) -> None:
        """Com a tecla de verdade: o `Tab` na caixa do comentário leva o foco adiante (e sair grava
        o comentário no lance), em vez de escrever uma tabulação e prender quem anda pelo teclado
        (portão `teclado` da suíte, crítico da fase 5, ciclo 4). A sabotagem é a caixa guardando o
        `Tab`, como antes: o foco fica, e o texto ganha a tabulação."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication

        painel = self.sala()
        painel.push_move(chess.Move.from_uci("e2e4"))
        painel.activateWindow()
        painel.comentario.setFocus(Qt.FocusReason.TabFocusReason)
        self.app.processEvents()
        painel.comentario.setPlainText("uma nota")
        QTest.keyClick(painel.comentario, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertIsNot(QApplication.focusWidget(), painel.comentario)
        self.assertNotIn("\t", painel.comentario.toPlainText())
        self.assertIn("uma nota", painel.estudo.no.comment)
        painel.comentario.setTabChangesFocus(False)
        painel.comentario.setFocus(Qt.FocusReason.TabFocusReason)
        self.app.processEvents()
        QTest.keyClick(painel.comentario, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), painel.comentario)
        self.assertIn("\t", painel.comentario.toPlainText())

    def test_a_lista_de_lances_e_uma_parada_do_tab_nos_dois_sentidos(self) -> None:
        """Com a tecla de verdade, numa partida de 40 lances: o `Shift+Tab` do comentário passa
        pela lista e sai dela na tecla seguinte, e o `Tab` sai dela de uma vez (portão `teclado`
        da suíte, crítico da fase 5, ciclo 4). A sabotagem é a lista andando de âncora em âncora
        pelo teclado, como antes: o `Shift+Tab` não sai mais dela."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication

        painel = self.sala()
        tabuleiro = chess.Board()
        for _ in range(40):
            lance = sorted(tabuleiro.legal_moves, key=lambda m: m.uci())[0]
            painel.push_move(lance)
            tabuleiro.push(lance)
        painel.activateWindow()

        def na_lista_de_volta() -> int:
            painel.comentario.setFocus(Qt.FocusReason.TabFocusReason)
            self.app.processEvents()
            vezes = 0
            for _ in range(200):
                QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Backtab,
                               Qt.KeyboardModifier.ShiftModifier)
                self.app.processEvents()
                if QApplication.focusWidget() is painel.lista:
                    vezes += 1
                elif vezes:
                    break
            return vezes

        self.assertEqual(na_lista_de_volta(), 1)
        painel.lista.setFocus(Qt.FocusReason.TabFocusReason)
        self.app.processEvents()
        QTest.keyClick(painel.lista, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertIsNot(QApplication.focusWidget(), painel.lista)
        painel.lista.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.assertGreater(na_lista_de_volta(), 60)

    def test_com_o_cursor_num_campo_a_sala_cede_a_tecla(self) -> None:
        """A sala tem o campo de FEN, a lista e a caixa de anotação: ali `←` é do texto (S-323)."""
        from PyQt6.QtWidgets import QApplication

        painel = self.sala()
        painel.activateWindow()
        painel.campo_fen.setFocus()
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), painel.campo_fen, "o foco não foi para o campo")
        self.assertEqual(painel.acoes_proprias(), frozenset())

    def test_as_quatro_acoes_da_aba_sao_de_navegacao_de_lance(self) -> None:
        """`←` é "diagrama anterior" na janela e "lance anterior" aqui dentro."""
        painel = self.sala()
        # `==` e não `is`: um método ligado é criado a cada acesso, então `is` compararia dois
        # objetos diferentes que envolvem a mesma função e o mesmo painel.
        self.assertEqual(painel.atender("diagrama_anterior"), painel.undo_move)
        self.assertEqual(painel.atender("ultima_pagina"), painel.go_to_end_of_line)
        self.assertIsNone(painel.atender("salvar"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
