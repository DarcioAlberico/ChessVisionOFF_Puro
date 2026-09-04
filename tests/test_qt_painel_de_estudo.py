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
from chess_diagram_ocr.ui import comandos, estudo_lista, sala_declarada

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

    def test_a_sincronia_com_o_ocr_e_tabelada(self) -> None:
        """As quatro respostas de `decidir_sincronia`, e o que cada uma protege (S-512).

        **A linha que mais importa é a última.** Sem ela, religar o fio que o porte cortou
        devolveria a sincronia e criaria outro defeito: o sinal do painel de resultado dispara a
        cada casa corrigida, e `_abrir` zera a pilha de desfazer da sala.
        """
        decidir = sala_declarada.decidir_sincronia
        sincronia = sala_declarada.Sincronia
        aberta = Ancora(documento="livro.pdf", pagina=3, diagrama=1)
        no_livro = PosicaoDeEstudo(ancora=aberta)
        outra = PosicaoDeEstudo(ancora=Ancora(documento="livro.pdf", pagina=3, diagrama=2))

        casos = (
            ("outro diagrama", aberta, outra, False, sincronia.TROCA),
            ("mesmo diagrama, estudo vazio", aberta, no_livro, True, sincronia.ATUALIZA),
            ("mesmo diagrama, já analisado", aberta, no_livro, False, sincronia.NADA),
            ("posição sem âncora", aberta, PosicaoDeEstudo(), True, sincronia.NADA),
            ("posição inválida", aberta, PosicaoDeEstudo(placement="lixo", ancora=outra.ancora), True, sincronia.NADA),
            ("sala em posição avulsa", Ancora(), no_livro, True, sincronia.TROCA),
        )
        for nome, ancora, posicao, vazio, esperada in casos:
            with self.subTest(caso=nome):
                self.assertIs(esperada, decidir(ancora, posicao, vazio=vazio))

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
        self.assertEqual(len([f for f in vistos if "Sem motor UCI instalado" in f]), 3)

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


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class UltimoLanceNaSalaTests(unittest.TestCase):
    """A marca do último lance sai do **nó**, e não de estado guardado no widget (S-509).

    `BoardModel.last_move` e `last_move_squares()` eram puros, testados e **nunca recebiam valor**:
    `mostrar_tabuleiro` fazia `copy(stack=False)`, que descarta a pilha de onde eles sairiam. Quem
    tem a aresta que chegou ao nó corrente é a sala, e ela passa por argumento.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)
        self.painel = qt_estudo.PainelDeEstudo(pasta_inicial=self.pasta, pasta_de_estudos=self.pasta)
        self.addCleanup(descartar, self.painel)

    def casas(self) -> frozenset[int]:
        return self.painel.tabuleiro.modelo.last_move_squares()

    def test_a_raiz_nao_marca_casa_nenhuma(self) -> None:
        """A posição do diagrama não veio de lance nenhum -- marcar ali seria inventar uma jogada."""
        self.assertEqual(frozenset(), self.casas())

    def test_jogar_marca_as_duas_casas_do_lance(self) -> None:
        self.painel.push_move(chess.Move.from_uci("e2e4"))
        self.assertEqual(2, len(self.casas()))

    def test_voltar_para_a_raiz_apaga_a_marca(self) -> None:
        """**É o caso que um `_ultimo_lance` guardado no widget erraria.**"""
        self.painel.push_move(chess.Move.from_uci("e2e4"))
        self.painel.undo_move()
        self.assertEqual(frozenset(), self.casas())

    def test_navegar_troca_a_marca_junto_com_o_no(self) -> None:
        self.painel.push_move(chess.Move.from_uci("e2e4"))
        depois_de_e4 = self.casas()
        self.painel.push_move(chess.Move.from_uci("e7e5"))
        self.assertNotEqual(depois_de_e4, self.casas(), "a marca ficou no lance anterior")
        self.painel.undo_move()
        self.assertEqual(depois_de_e4, self.casas(), "voltar não repôs a marca do nó")

    def test_desfazer_nao_deixa_a_marca_de_um_lance_que_saiu_da_arvore(self) -> None:
        """**O caso que uma marca guardada no widget erraria calado.**

        `_aplicar_pgn` recarrega o estudo do PGN e reaplica o caminho -- que pode não existir mais,
        e aí `ir_para` cai na raiz, como o método documenta. A marca sai do nó, então ela cai
        junto; guardada no widget, ela continuaria pintando e7-e5 sobre uma árvore que já não tem
        aquele lance.
        """
        self.painel.push_move(chess.Move.from_uci("e2e4"))
        self.painel.push_move(chess.Move.from_uci("e7e5"))
        self.painel.desfazer()
        self.assertIsNone(self.painel.estudo.no.move, "o desfazer não caiu na raiz como documentado")
        self.assertEqual(frozenset(), self.casas())

    def test_a_marca_e_sempre_a_do_no_corrente(self) -> None:
        """O invariante, afirmado depois de cada gesto que troca de nó."""
        from chess_diagram_ocr.fen_utils import reading_index_from_square

        def esperada() -> frozenset[int]:
            lance = self.painel.estudo.no.move
            if lance is None:
                return frozenset()
            return frozenset(
                {reading_index_from_square(lance.from_square), reading_index_from_square(lance.to_square)}
            )

        for gesto in (
            lambda: self.painel.push_move(chess.Move.from_uci("e2e4")),
            lambda: self.painel.push_move(chess.Move.from_uci("e7e5")),
            self.painel.undo_move,
            self.painel.go_to_end_of_line,
            self.painel.go_to_start_of_line,
        ):
            gesto()
            with self.subTest(no=self.painel.estudo.no.move):
                self.assertEqual(esperada(), self.casas())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class SincroniaComOOcrTests(unittest.TestCase):
    """A caixa "Seguir OCR selecionado" volta a seguir, e sem levar a pilha junto (S-512).

    **A ligação existia no Tk e caiu no porte**: `result_panel` chamava `on_sync_study` em três
    pontos, `app_tkinter.py:1537` o repassava, e a janela do Qt nunca ligou o fio. A caixa nasce
    marcada, então o que a aba prometia de fábrica é o que ela não fazia.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)
        self.posicao: PosicaoDeEstudo | None = None
        self.painel = qt_estudo.PainelDeEstudo(
            pasta_inicial=self.pasta,
            pasta_de_estudos=self.pasta,
            posicao=lambda: self.posicao,
        )
        self.addCleanup(descartar, self.painel)

    def diagrama(self, numero: int, *, placement: str = chess.STARTING_BOARD_FEN) -> PosicaoDeEstudo:
        return PosicaoDeEstudo(
            placement=placement,
            ancora=Ancora(documento=str(self.pasta / "livro.pdf"), pagina=3, diagrama=numero),
        )

    def test_seguir_troca_de_mesa_quando_o_diagrama_muda(self) -> None:
        self.posicao = self.diagrama(1)
        self.painel.sync_with_ocr()
        self.assertEqual(1, self.painel.estudo.ancora.diagrama)

        self.posicao = self.diagrama(2)
        self.painel.sync_with_ocr()
        self.assertEqual(2, self.painel.estudo.ancora.diagrama)

    def test_a_caixa_desmarcada_nao_segue(self) -> None:
        self.painel.seguir_ocr.setChecked(False)
        self.posicao = self.diagrama(1)
        self.painel.sync_with_ocr()
        self.assertFalse(self.painel.estudo.ancora.valida)

    def test_corrigir_uma_casa_do_diagrama_aberto_nao_zera_o_desfazer(self) -> None:
        """**A regressão que religar o fio cru teria criado.**

        O sinal do painel de resultado dispara a cada casa corrigida, e `_abrir` zera a pilha. Quem
        estivesse analisando aquele mesmo diagrama perderia o `Ctrl+Z` a cada tecla -- e `edicao` é
        o contador que `ui/desfazivel.py` lê para decidir de quem é a tecla.
        """
        self.posicao = self.diagrama(1)
        self.painel.sync_with_ocr()
        self.painel.push_move(chess.Move.from_uci("e2e4"))
        edicao = self.painel.edicao
        no = self.painel.estudo.no

        # A mesma âncora, com uma casa corrigida: é o que a aba Resultado emite a cada edição.
        self.posicao = self.diagrama(1, placement="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBN1")
        self.painel.sync_with_ocr()

        self.assertEqual(edicao, self.painel.edicao, "a sincronia contou como edição")
        self.assertIs(no, self.painel.estudo.no, "a sincronia moveu o lance corrente")
        self.painel.desfazer()
        self.assertEqual(0, self.painel.estudo.contagem_de_lances(), "a pilha de desfazer foi zerada")

    def test_corrigir_uma_casa_do_diagrama_vazio_chega_ao_tabuleiro(self) -> None:
        """Antes do primeiro lance não há o que perder, e a correção **tem** de chegar."""
        self.posicao = self.diagrama(1)
        self.painel.sync_with_ocr()
        antes = self.painel.estudo.tabuleiro.board_fen()

        corrigido = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBN1"
        self.posicao = self.diagrama(1, placement=corrigido)
        self.painel.sync_with_ocr()

        self.assertNotEqual(antes, self.painel.estudo.tabuleiro.board_fen())
        self.assertEqual(corrigido, self.painel.estudo.tabuleiro.board_fen())

    def test_a_atualizacao_silenciosa_nao_fala_no_rodape(self) -> None:
        """Uma frase por casa corrigida enterraria a de quem está corrigindo."""
        self.posicao = self.diagrama(1)
        self.painel.sync_with_ocr()
        ditas: list[str] = []
        self.painel.estado.connect(ditas.append)
        self.posicao = self.diagrama(1, placement="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBN1")
        self.painel.sync_with_ocr()
        self.assertEqual([], [f for f in ditas if "diagrama selecionado" in f])

    def test_posicao_sem_ancora_nao_recomeca_o_estudo_avulso(self) -> None:
        """Item de fila e amostra do dataset não têm par no livro: a âncora não nomeia mesa.

        Seguir uma delas recomeçaria o estudo em curso a cada atualização. O caminho para
        estudá-las continua sendo "Carregar OCR atual", que é explícito.
        """
        self.painel.push_move(chess.Move.from_uci("e2e4"))
        self.posicao = PosicaoDeEstudo()
        self.painel.sync_with_ocr()
        self.assertEqual(1, self.painel.estudo.contagem_de_lances())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ListaDeLancesTests(unittest.TestCase):
    """A lista que se lê: recuo que aparece e quebra que não parte lance (S-514/S-515).

    **Os dois defeitos eram do mecanismo do Qt, e nenhum deles quebrava teste.** `ui/estudo_lista.py`
    continua travado contra o `StringExporter` e não foi tocado; o que mudou é como o painel desenha
    os `Trecho` que ela devolve.
    """

    PGN = (
        '[Event "?"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 (3... Nf6 4. O-O Nxe4 5. d4 '
        "(5. Re1 Nd6 6. Nxe5 Be7) 5... Nd6 6. Bxc6 dxc6) 4. Ba4 Nf6 5. O-O Be7 *\n"
    )

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)
        self.painel = qt_estudo.PainelDeEstudo(pasta_inicial=self.pasta, pasta_de_estudos=self.pasta)
        self.addCleanup(descartar, self.painel)
        from chess_diagram_ocr.estudo import Estudo

        novo = Estudo.de_pgn(self.PGN, documento="livro.pdf")
        assert novo is not None
        self.painel.estudo = novo
        self.painel.refresh()

    def margens(self) -> list[float]:
        documento = self.painel.lista.document()
        bloco = documento.begin()
        vistas: list[float] = []
        while bloco.isValid():
            if bloco.text().strip():
                vistas.append(bloco.blockFormat().leftMargin())
            bloco = bloco.next()
        return vistas

    def test_a_variante_recua_e_a_subvariante_recua_mais(self) -> None:
        """**A regressão do item.** O recuo era `margin-left` num `<span>`, e o `QTextDocument`
        descarta margem em elemento inline: todos os blocos saíam com `leftMargin == 0.0`.
        """
        margens = self.margens()
        passo = float(sala_declarada.RECUO_POR_NIVEL)
        self.assertIn(0.0, margens, "a linha principal deixou de estar na margem zero")
        self.assertIn(passo, margens, "a variante não recuou um nível")
        self.assertIn(2 * passo, margens, "a subvariante não recuou dois níveis")

    def test_o_recuo_satura_e_a_numeracao_nao(self) -> None:
        """`NIVEL_MAXIMO_DE_RECUO` é do módulo puro, e o desenho o respeita."""
        teto = estudo_lista.NIVEL_MAXIMO_DE_RECUO * sala_declarada.RECUO_POR_NIVEL
        self.assertLessEqual(max(self.margens()), float(teto))

    def _quebras(self, largura: int) -> list[str]:
        """Os caracteres imediatamente **antes** de cada quebra visual, naquela largura.

        **Num documento à parte, e não no do widget.** `QTextEdit` refaz a largura do documento a
        partir do próprio viewport a cada leiaute, então um `setTextWidth` no documento dele é
        sobrescrito: o que se mediria seria a geometria de um widget que nunca foi mostrado (aqui,
        linhas de 72 px pedindo 240). O HTML é o mesmo -- é o que o painel gerou --, e é dele que a
        quebra depende.
        """
        from PyQt6.QtGui import QTextDocument

        documento = QTextDocument()
        documento.setDefaultFont(self.painel.lista.font())
        documento.setHtml(self.painel.lista.toHtml())
        documento.setTextWidth(largura)
        documento.documentLayout().documentSize()  # força o leiaute
        antes: list[str] = []
        bloco = documento.begin()
        while bloco.isValid():
            leiaute, texto = bloco.layout(), bloco.text()
            for i in range(1, leiaute.lineCount()):
                inicio = leiaute.lineAt(i).textStart()
                if 0 < inicio <= len(texto):
                    antes.append(texto[inicio - 1])
            bloco = bloco.next()
        return antes

    def test_a_quebra_so_acontece_em_espaco_que_pode_quebrar(self) -> None:
        """**Um critério cobre os dois da spec.**

        Se toda quebra cai depois de um espaço comum, então nenhum token de SAN foi partido ao
        meio *e* nenhum `&nbsp;` -- o que gruda `12.` em `Ba4` e `(` no primeiro lance da variante
        -- foi quebrado. Medido antes do item, num documento de 240 px:
        `1. Nf3 Nc6 2. Nf3 N` / `c6 3. Nf3 Nc6 4. Nf`.
        """
        for largura in (240, 320, 480, 900):
            with self.subTest(largura=largura):
                partidos = [c for c in self._quebras(largura) if c != " "]
                self.assertEqual(
                    [],
                    partidos,
                    f"quebra fora de espaço quebrável em {largura} px: {partidos!r}",
                )

    def test_a_varredura_de_quebra_acha_alguma(self) -> None:
        """Sem isto, um leiaute que não quebrasse faria o teste acima passar sobre lista vazia."""
        self.assertGreater(len(self._quebras(240)), 0, "nada quebrou a 240 px -- suspeito")

    def test_a_lista_continua_batendo_com_o_string_exporter(self) -> None:
        """A trava da S-273 não é tocada por este item: o desenho mudou, o PGN não."""
        import chess.pgn

        exportador = chess.pgn.StringExporter(headers=False, variations=True, comments=True)
        esperado = self.painel.estudo.jogo.accept(exportador)
        obtido = estudo_lista.texto_de(estudo_lista.trechos(self.painel.estudo))
        self.assertEqual(esperado.split(), obtido.split())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DobraDasVariantesTests(unittest.TestCase):
    """Dobrar é **vista**: esconde na tela e não toca a árvore (S-516)."""

    PGN = ListaDeLancesTests.PGN

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)
        self.painel = qt_estudo.PainelDeEstudo(pasta_inicial=self.pasta, pasta_de_estudos=self.pasta)
        self.addCleanup(descartar, self.painel)
        from chess_diagram_ocr.estudo import Estudo

        novo = Estudo.de_pgn(self.PGN, documento="livro.pdf")
        assert novo is not None
        self.painel.estudo = novo
        self.painel.refresh()

    def visivel(self) -> str:
        return self.painel.lista.toPlainText()

    def test_dobrar_esconde_o_miolo_e_deixa_a_reticencia(self) -> None:
        self.assertIn("Nxe4", self.visivel())
        self.painel.alternar_dobra()
        self.assertNotIn("Nxe4", self.visivel(), "o miolo da variante continuou na tela")
        self.assertIn("(", self.visivel(), "o parêntese sumiu junto -- não há onde desdobrar")
        self.assertIn("…", self.visivel(), "a variante dobrada não diz que existe")

    def test_desdobrar_devolve_tudo(self) -> None:
        antes = self.visivel()
        self.painel.alternar_dobra()
        self.painel.alternar_dobra()
        self.assertEqual(antes, self.visivel())

    def test_dobrar_nao_toca_a_arvore_nem_a_pilha(self) -> None:
        """`Ctrl+Z` não enxerga a dobra, e `edicao` -- que decide de quem é a tecla -- não sobe."""
        pgn, edicao = self.painel.pgn_payload(), self.painel.edicao
        self.painel.alternar_dobra()
        self.assertEqual(pgn, self.painel.pgn_payload())
        self.assertEqual(edicao, self.painel.edicao)

    def test_navegar_para_dentro_de_uma_dobra_a_abre(self) -> None:
        """**O lance corrente nunca se esconde.** A dobra continua declarada e volta a valer
        quando a navegação sai dali -- ver `ui/estudo_dobra`."""
        self.painel.alternar_dobra()
        self.assertNotIn("Nxe4", self.visivel())

        dentro = next(
            t.caminho
            for t in self.painel._trechos
            if t.papel == estudo_lista.LANCE and t.texto.startswith("Nxe4")
        )
        self.assertTrue(self.painel.estudo.ir_para(dentro))
        self.painel.refresh()
        self.assertIn("Nxe4", self.visivel(), "a lista escondeu o lance corrente")

        self.painel.go_to_start_of_line()
        self.assertNotIn("Nxe4", self.visivel(), "a dobra não voltou a valer ao sair dali")

    def test_o_botao_fica_cinza_sem_variante(self) -> None:
        """Como o do recorte na S-347: alternar sobre o que não existe troca o texto por nada."""
        from chess_diagram_ocr.estudo import Estudo

        so_principal = Estudo.de_pgn('[Event "?"]\n\n1. e4 e5 *\n', documento="livro.pdf")
        assert so_principal is not None
        self.painel.estudo = so_principal
        self.painel.refresh()
        self.assertFalse(self.painel.btn_dobra.isEnabled())
        self.assertEqual(comandos.rotulo_de_botao("dobrar_variantes"), self.painel.btn_dobra.text())

    def test_o_rotulo_do_botao_diz_o_que_esta_na_tela(self) -> None:
        self.painel.alternar_dobra()
        self.assertEqual(comandos.rotulo_alternado("dobrar_variantes"), self.painel.btn_dobra.text())
        self.painel.alternar_dobra()
        self.assertEqual(comandos.rotulo_de_botao("dobrar_variantes"), self.painel.btn_dobra.text())

    def test_o_clique_no_parentese_dobra_uma_so(self) -> None:
        """O `(` é o controle, e não um glifo novo ao lado dele -- ver `_trecho_em_html`."""
        from PyQt6.QtCore import QUrl

        interna = min(self.painel._variantes, key=lambda v: v.fecha - v.abre)
        self.painel._clique_na_lista(QUrl(f"dobra:{interna.abre}"))
        self.assertNotIn("Nxe5", self.visivel(), "a subvariante não dobrou")
        self.assertIn("Nxe4", self.visivel(), "a de fora dobrou junto")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ArranjoTests(unittest.TestCase):
    """Onde as coisas ficam (S-517/S-518/S-519).

    **O `ROADMAP_ACABAMENTO` adiou este item por escrito** -- *"as quatro fileiras de botão do
    Estudo são problema de arranjo, não de acabamento… merecem um plano próprio"* -- e a medição
    que ele deixou é a que estes testes fixam: 28 botões em quatro fileiras, 130 px de 800 a 900 de
    largura e 155 px de 620 a 760.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def sala(self, **kwargs: object) -> qt_estudo.PainelDeEstudo:
        montada = qt_estudo.PainelDeEstudo(
            pasta_inicial=self.pasta, pasta_de_estudos=self.pasta, **kwargs  # type: ignore[arg-type]
        )
        self.addCleanup(descartar, montada)
        return montada

    def _barras_do_topo(self, painel: qt_estudo.PainelDeEstudo) -> list[object]:
        from chess_diagram_ocr.qt.barra import BarraFluida

        fora = painel.layout()
        assert fora is not None
        return [
            item.widget()
            for i in range(fora.count())
            if isinstance(item := fora.itemAt(i), object)
            and isinstance(item.widget(), BarraFluida)
        ]

    def test_o_topo_tem_uma_fila_e_nenhuma_barra_fluida(self) -> None:
        """Eram três `BarraFluida` (S-517) que a 715 px quebravam em cinco fileiras e 154 px; desde a
        S-527 o topo é a `BarraDaSala`, que é uma fila por construção."""
        painel = self.sala()
        self.assertEqual([], self._barras_do_topo(painel))
        self.assertEqual(1, painel.barra.linhas)
        fora = painel.layout()
        assert fora is not None
        self.assertIs(painel.barra, fora.itemAt(0).widget())  # type: ignore[union-attr]

    def test_a_navegacao_saiu_do_topo_e_esta_sob_o_tabuleiro(self) -> None:
        """Os quatro de navegação eram os **menores alvos do painel**, encostados na cirurgia de
        árvore. São o único grupo cuja frequência justifica estar ao lado do tabuleiro."""
        from PyQt6.QtWidgets import QPushButton

        painel = self.sala()
        navegacao = {"inicio_da_linha", "lance_anterior", "proximo_lance", "fim_da_linha"}

        def acoes(dentro: object) -> set[str]:
            return {
                str(b.property("acao"))
                for b in dentro.findChildren(QPushButton)  # type: ignore[union-attr]
                if b.property("acao")
            }

        self.assertEqual(set(), set(painel.barra.acoes) & navegacao, "a navegação continua no topo")
        self.assertTrue(
            navegacao <= acoes(painel.tabuleiro.parent()),
            "a navegação não foi para junto do tabuleiro",
        )

    def test_a_faixa_diz_o_lance_corrente_e_a_vez(self) -> None:
        """As duas informações não tinham lugar: o lance só existia como fundo amarelo no meio da
        lista, e a vez só como sufixo da frase do rodapé."""
        painel = self.sala()
        self.assertIn("posição", painel.lbl_lance.text())
        self.assertIn("brancas", painel.lbl_vez.text())

        painel.push_move(chess.Move.from_uci("e2e4"))
        self.assertEqual("1. e4", painel.lbl_lance.text())
        self.assertIn("pretas", painel.lbl_vez.text())

        painel.push_move(chess.Move.from_uci("e7e5"))
        self.assertEqual("e5", painel.lbl_lance.text(), "o lance das pretas não repete o número")

    def test_o_catalogo_nao_mudou_de_dono(self) -> None:
        """Rearranjar não é tirar comando: o critério da S-280 vale para todo movimento de botão."""
        self.assertEqual(comandos.acoes_fora_do_catalogo(sala_declarada.COMANDOS_DA_ABA), [])
        painel = self.sala()
        for acao, metodo in sala_declarada.COMANDOS_DA_ABA.items():
            with self.subTest(acao=acao):
                self.assertTrue(callable(getattr(painel, metodo, None)))

    def test_o_tabuleiro_da_sala_passa_do_teto_fixo_numa_janela_grande(self) -> None:
        """**O item da S-518.** `MAX_DO_TABULEIRO` é herança do canvas de tamanho fixo do Tk."""
        from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro

        painel = self.sala()
        painel.tabuleiro.resize(900, 900)
        self.assertGreater(painel.tabuleiro.geometria().size, qt_tabuleiro.MAX_DO_TABULEIRO)

    def test_o_tabuleiro_do_resultado_nao_muda(self) -> None:
        """A fração é da sala. Na aba Resultado o tabuleiro divide a coluna com a lista de casas."""
        from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro

        outro = qt_tabuleiro.TabuleiroQt()
        self.addCleanup(descartar, outro)
        outro.resize(900, 900)
        self.assertEqual(float(qt_tabuleiro.MAX_DO_TABULEIRO), outro.geometria().size)

    def test_a_fracao_guardada_manda_e_o_zero_e_o_padrao(self) -> None:
        painel = self.sala()
        painel.tabuleiro.resize(900, 900)
        painel.definir_fracao_do_tabuleiro(0.5)
        self.assertEqual(0.5, painel.fracao_do_tabuleiro)
        meio = painel.tabuleiro.geometria().size

        painel.definir_fracao_do_tabuleiro(0.0)
        self.assertEqual(sala_declarada.FRACAO_PADRAO_DO_TABULEIRO, painel.fracao_do_tabuleiro)
        self.assertGreater(painel.tabuleiro.geometria().size, meio)

    def test_o_divisor_vertical_tem_duas_partes_sem_motor(self) -> None:
        """Sem binário a seção do motor não existe (S-33), e o divisor não reserva altura para ela."""
        self.assertEqual(2, self.sala().divisor_vertical.count())

    def test_a_fracao_do_divisor_vertical_vai_e_volta(self) -> None:
        painel = self.sala()
        painel.resize(1000, 700)
        painel.show()
        self.app.processEvents()
        painel.posicionar_divisor_vertical(0.4)
        self.assertAlmostEqual(0.4, painel.fracao_do_divisor_vertical, places=1)
