"""A sala de estudo dirigida pela janela (S-270/S-272/S-274/S-275/S-277/S-279).

O que está aqui é o que **só quebra com widget**: o clique na lista chegar ao nó certo, o comentário
ser gravado no lance em que foi escrito, a seta do botão direito ir para o nó corrente, e -- o item
que motivou a fase -- **trocar de diagrama devolver a análise do anterior**, que antes era descartada
sem pergunta por `_set_board_state`.

O que não precisa de janela está em `test_estudo.py`, `test_estudo_lista.py` e
`test_estudo_arquivo.py`. A regra é a da S-137: o que dá para afirmar sem abrir janela não abre.
"""

from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

import chess
import numpy as np
from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr import estudo as estudo_mod
from chess_diagram_ocr import estudo_arquivo
from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.engine import Evaluation
from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo, caminho_de
from chess_diagram_ocr.games_cache import CachedPosition
from chess_diagram_ocr.games_db import PositionHit
from chess_diagram_ocr.ui import (
    abas,
    atalhos,
    comandos,
    estudo_lista,
    legenda,
    paleta_de_comandos,
    rolagem,
    study_panel,
)
from chess_diagram_ocr.ui.board_widget import PieceImages
from chess_diagram_ocr.ui.study_panel import StudyPanel, posicao_do_painel

RAIZ = Path(__file__).resolve().parents[1]

ITALIANA = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"
ROQUEADAS = "r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R1BQ1RK1"
LIVRO = "C:/livros/Secrets.pdf"


class _PainelFalso:
    """Os quatro atributos que `posicao_do_painel` usa do `ResultPanel` (S-269)."""

    def __init__(self, placement: str, lado: str, chave: tuple[str, int] | None, indice: int = 0) -> None:
        self.fen_var = tk.StringVar(master=raiz_do_processo(), value=placement)
        self.side_edits = [lado]
        self.selected_index = indice
        self.page_key = chave


class PosicaoDoPainelTests(unittest.TestCase):
    """O que a janela entrega à sala. Era `lambda: result_panel.fen_var.get()`, e aquilo não é
    uma FEN: é o campo de peças."""

    @classmethod
    def setUpClass(cls) -> None:
        raiz_do_processo()

    def test_a_vez_e_a_ancora_chegam_juntas(self) -> None:
        posicao = posicao_do_painel(_PainelFalso(ROQUEADAS, "b", (LIVRO, 142)), lambda _p, _d: 23)
        self.assertEqual(posicao.vez, "b")
        self.assertEqual(posicao.lance, 23)
        self.assertEqual(posicao.ancora, Ancora(documento=LIVRO, pagina=142, diagrama=0))
        self.assertFalse(chess.Board(posicao.fen()).turn)

    def test_sem_pagina_o_estudo_nasce_avulso(self) -> None:
        """Item da fila e amostra do dataset não têm par (documento, página): a anotação seria de
        um diagrama que ninguém sabe qual é."""
        posicao = posicao_do_painel(_PainelFalso(ROQUEADAS, "w", None))
        self.assertFalse(posicao.ancora.valida)

    def test_sem_painel_nao_ha_posicao(self) -> None:
        self.assertIsNone(posicao_do_painel(None))

    def test_campo_vazio_nao_vira_estudo(self) -> None:
        self.assertIsNone(posicao_do_painel(_PainelFalso("", "w", (LIVRO, 1))))


class _Sala(unittest.TestCase):
    """Um painel de verdade num frame próprio -- destruir frame é seguro, destruir raiz não é."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.host = tk.Frame(self.root)
        self.addCleanup(self.host.destroy)
        self.proxima: PosicaoDeEstudo | None = None
        self.pedidos: list[int] = []
        self.paginas: list[tuple[str, int]] = []
        self.impressa = ""
        self.abre_pagina = True
        self.bases: tuple[Path, ...] = ()
        self.para_o_texto: list[str] = []
        self.aceita_texto = True
        self.motor = self._motor()
        self.painel = StudyPanel(
            self.host,
            piece_images=PieceImages(BUNDLE_ROOT / "assets" / "piece_images"),
            posicao=lambda: self.proxima,
            initial_dir=Path(self.tmp.name),
            pasta_de_estudos=Path(self.tmp.name),
            analyzer=self.motor,
            recorte=self._recorte,
            linha_impressa=lambda ancora: self.impressa,
            abrir_pagina=self._abrir_pagina,
            bases_de_partidas=lambda: self.bases,
            para_o_texto=self._levar_para_o_texto,
        )
        self.painel.pack()
        self.root.update_idletasks()

    def _no_diagrama(self, diagrama: int, placement: str = ITALIANA, vez: str = "b") -> None:
        self.proxima = PosicaoDeEstudo(
            placement=placement,
            vez=vez,
            lance=4,
            ancora=Ancora(documento=LIVRO, pagina=142, diagrama=diagrama),
        )
        self.painel.sync_with_ocr(force=True)

    def _jogar(self, *ucis: str) -> None:
        for uci in ucis:
            self.painel.push_move(chess.Move.from_uci(uci))

    def _texto_da_lista(self) -> str:
        return self.painel.moves_text.get("1.0", "end-1c")

    def _motor(self):  # noqa: ANN202 - EngineAnalyzer | None
        """Sem motor por padrão: é o caso da máquina que não tem Stockfish, que é a da suíte."""
        return None

    def _recorte(self, ancora: Ancora):  # noqa: ANN202 - np.ndarray | None
        """Conta quantas vezes o recorte foi **pedido**: é como o teste afirma que ele não é
        reamostrado a cada lance."""
        self.pedidos.append(ancora.diagrama)
        return np.full((80, 80, 3), 200, dtype=np.uint8)

    def _levar_para_o_texto(self, linha: str) -> bool:
        if not self.aceita_texto:
            return False
        self.para_o_texto.append(linha)
        return True

    def _abrir_pagina(self, ancora: Ancora) -> bool:
        if not self.abre_pagina:
            return False
        self.paginas.append((ancora.documento, ancora.pagina))
        return True


class TrocarDeDiagramaTests(_Sala):
    def test_voltar_ao_diagrama_devolve_a_analise(self) -> None:
        """**A regressão do item.** `_set_board_state` fazia `self.game = self._new_game(board)` --
        a árvore inteira no lixo, sem pergunta, sem aviso e sem desfazer."""
        self.painel.sala.documento = LIVRO
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self._no_diagrama(1, placement=ROQUEADAS)
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 0)
        self._no_diagrama(0)
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 2)

    def test_o_estudo_abre_com_a_vez_do_diagrama(self) -> None:
        self._no_diagrama(0, vez="b")
        self.assertFalse(self.painel.estudo.tabuleiro.turn)
        self.assertTrue(self.painel.board_widget.flipped)

    def test_o_roque_do_diagrama_e_um_lance_possivel(self) -> None:
        """Antes, `board_from_fen` cravava `w - - 0 1` e o roque era recusado como ilegal."""
        self._no_diagrama(0, vez="w")
        self.assertIn(chess.Move.from_uci("e1g1"), self.painel.estudo.tabuleiro.legal_moves)

    def test_a_chave_do_estudo_aberto_e_a_do_diagrama(self) -> None:
        self._no_diagrama(2)
        self.assertEqual(
            self.painel.chave_do_estudo_aberto,
            Ancora(documento=LIVRO, pagina=142, diagrama=2).chave(),
        )

    def test_o_estudo_do_livro_vai_para_o_disco_e_volta(self) -> None:
        self.painel.abrir_livro(LIVRO)
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.assertTrue(self.painel.tem_trabalho_por_gravar())
        self.assertIsNotNone(self.painel.salvar_agora())
        self.assertFalse(self.painel.tem_trabalho_por_gravar())

        self.painel.sala = type(self.painel.sala)()
        self.painel.abrir_livro(LIVRO)
        self.assertEqual(len(self.painel.sala), 1)


class ListaDeLancesTests(_Sala):
    def test_a_lista_mostra_a_variante_e_a_subvariante(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self.painel.undo_move()
        self._jogar("c2c3")
        texto = self._texto_da_lista()
        self.assertIn("Bc5", texto)
        self.assertIn("O-O", texto)
        self.assertIn("c3", texto)

    def test_clicar_num_lance_leva_ao_no(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        alvo = caminho_de(self.painel.estudo.no.parent)
        indice = estudo_lista.trecho_do_caminho(self.painel._trechos, alvo)
        self.painel._clique_na_lista(indice, None)
        self.assertEqual(self.painel.estudo.caminho(), alvo)

    def test_a_raiz_e_clicavel_e_volta_a_posicao_do_diagrama(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self.painel._clique_na_lista(0, None)
        self.assertEqual(self.painel.estudo.caminho(), ())

    def test_o_lance_corrente_fica_marcado(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.assertTrue(self.painel.moves_text.tag_ranges("corrente"))

    def test_promover_variante_nao_troca_o_destino_dos_cliques(self) -> None:
        """Promover reordena as irmãs: um caminho guardado na tag apontaria para o outro lance."""
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self.painel.undo_move()
        self._jogar("c2c3")
        c3 = self.painel.estudo.no
        self.painel.promover_a_principal()
        indice = estudo_lista.trecho_do_caminho(self.painel._trechos, caminho_de(c3))
        self.painel._clique_na_lista(indice, None)
        self.assertIs(self.painel.estudo.no, c3)

    def test_lance_igual_ao_que_ja_estava_segue_a_linha(self) -> None:
        """O único acerto de peso que a aba já tinha, e que a Fase 44 preserva."""
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.painel.undo_move()
        self._jogar("f8c5")
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 1)


class VarianteTests(_Sala):
    def _com_variante(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self.painel.undo_move()
        self._jogar("c2c3")

    def test_promover_a_principal_troca_as_duas_linhas(self) -> None:
        self._com_variante()
        self.painel.promover_a_principal()
        principal = [no.move for no in self.painel.estudo.raiz.mainline()]
        self.assertEqual(principal[1], chess.Move.from_uci("c2c3"))

    def test_apagar_variante_folha_nao_pergunta_e_volta_ao_pai(self) -> None:
        self._com_variante()
        pai = self.painel.estudo.no.parent
        self.painel.apagar_variante()
        self.assertIs(self.painel.estudo.no, pai)
        self.assertEqual(len(pai.variations), 1)

    def test_apagar_continuacao_mantem_o_lance(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self.painel.undo_move()
        no = self.painel.estudo.no
        self.painel.apagar_continuacao()
        self.assertIs(self.painel.estudo.no, no)
        self.assertEqual(no.variations, [])

    def test_a_raiz_nao_e_variante_nem_se_apaga(self) -> None:
        self._no_diagrama(0)
        self.painel.promover_a_principal()
        self.painel.apagar_variante()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 0)

    def test_fim_da_linha_segue_a_principal_a_partir_daqui(self) -> None:
        self._com_variante()
        self.painel.go_to_start_of_line()
        self.painel.go_to_end_of_line()
        self.assertEqual(self.painel.estudo.tabuleiro.fen(), self.painel.estudo.raiz.end().board().fen())


class DesfazerTests(_Sala):
    """O `Ctrl+Z` da sala é o da janela, e não uma terceira pilha (S-243/S-275)."""

    def test_a_sala_e_um_desfazivel_de_verdade(self) -> None:
        from chess_diagram_ocr.ui.desfazivel import Desfazivel

        self.assertIsInstance(self.painel, Desfazivel)

    def test_o_contador_de_edicao_so_cresce(self) -> None:
        self._no_diagrama(0)
        antes = self.painel.edicao
        self._jogar("f8c5")
        self.assertGreater(self.painel.edicao, antes)

    def test_desfazer_devolve_a_variante_apagada_com_a_anotacao(self) -> None:
        """A pilha guarda o **PGN** do estudo: comentário e seta voltam junto com os lances.

        E o `patch` aqui não é conveniência: apagar um lance **anotado** pergunta antes (S-275), e
        um teste que abrisse a caixa de verdade travaria a suíte esperando um clique. A pergunta em
        si é afirmada em `PerguntaAntesDeApagarTests`.
        """
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self.painel.on_arrow(0, 63, "green")
        self.painel.comentario_text.insert("1.0", "o roque")
        self.painel.gravar_comentario()
        with mock.patch.object(study_panel.messagebox, "askyesno", return_value=True):
            self.painel.apagar_variante()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 1)

        self.painel.desfazer()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 2)
        volta = self.painel.estudo.raiz.end()
        self.assertIn("o roque", volta.comment)
        self.assertIn("%cal", volta.comment)

    def test_refazer_tira_de_novo(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self.painel.apagar_variante()  # folha sem anotação: não pergunta
        self.painel.desfazer()
        self.painel.refazer()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 1)

    def test_desfazer_sem_nada_a_desfazer_avisa_e_nao_quebra(self) -> None:
        self._no_diagrama(0)
        self.painel.desfazer()
        self.assertIn("desfazer", self.painel.status_var.get())

    def test_trocar_de_diagrama_recomeca_a_pilha(self) -> None:
        """Um `Ctrl+Z` que atravessasse a troca de mesa desfaria um lance que não está na tela."""
        self.painel.sala.documento = LIVRO
        self._no_diagrama(0)
        self._jogar("f8c5")
        self._no_diagrama(1, placement=ROQUEADAS)
        self.painel.desfazer()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 0)

    def test_o_foco_dentro_da_sala_e_reconhecido(self) -> None:
        self.assertTrue(self.painel.contem(self.painel.moves_text))
        self.assertTrue(self.painel.contem(self.painel.comentario_text))
        self.assertFalse(self.painel.contem(self.host))


class PerguntaAntesDeApagarTests(_Sala):
    """Apagar pergunta **quando há o que perder**, e só aí (regra 7 da SPEC_ESTUDO)."""

    def test_apagar_um_lance_solto_nao_pergunta(self) -> None:
        """É o desfazer de um clique errado: perguntar ali seria atrito, não proteção."""
        self._no_diagrama(0)
        self._jogar("f8c5")
        with mock.patch.object(study_panel.messagebox, "askyesno") as caixa:
            self.painel.apagar_variante()
        caixa.assert_not_called()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 0)

    def test_apagar_lance_anotado_pergunta(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.painel.comentario_text.insert("1.0", "o lance da italiana")
        self.painel.gravar_comentario()
        with mock.patch.object(study_panel.messagebox, "askyesno", return_value=False) as caixa:
            self.painel.apagar_variante()
        caixa.assert_called_once()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 1)

    def test_apagar_subarvore_de_dois_lances_pergunta(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self.painel.undo_move()
        with mock.patch.object(study_panel.messagebox, "askyesno", return_value=False) as caixa:
            self.painel.apagar_variante()
        caixa.assert_called_once()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 2)

    def test_trocar_de_posicao_num_estudo_avulso_pergunta(self) -> None:
        """Estudo com âncora fica guardado na sala e volta; o avulso não tem para onde ir."""
        self.proxima = PosicaoDeEstudo(placement=ITALIANA, vez="w")
        self.painel.load_from_recognized()
        self._jogar("e1g1")
        with mock.patch.object(study_panel.messagebox, "askyesno", return_value=False) as caixa:
            self.painel.load_initial_position()
        caixa.assert_called_once()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 1)

    def test_trocar_a_vez_pergunta_mesmo_com_ancora(self) -> None:
        """A única ação da aba que **descarta** um estudo ancorado: trocar a vez muda a raiz, e a
        árvore antiga deixa de valer sobre a posição nova."""
        self.painel.sala.documento = LIVRO
        self._no_diagrama(0)
        self._jogar("f8c5")
        with mock.patch.object(study_panel.messagebox, "askyesno", return_value=False) as caixa:
            self.painel.toggle_turn()
        caixa.assert_called_once()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 1)

        with mock.patch.object(study_panel.messagebox, "askyesno", return_value=True):
            self.painel.toggle_turn()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 0)
        self.assertEqual(len(self.painel.sala), 0)

    def test_trocar_a_vez_num_estudo_vazio_nao_pergunta(self) -> None:
        self._no_diagrama(0)
        with mock.patch.object(study_panel.messagebox, "askyesno") as caixa:
            self.painel.toggle_turn()
        caixa.assert_not_called()

    def test_trocar_de_diagrama_ancorado_nao_pergunta_nada(self) -> None:
        """**O item da S-270 visto de fora**: o que era descarte silencioso virou troca de mesa."""
        self.painel.sala.documento = LIVRO
        self._no_diagrama(0)
        self._jogar("f8c5")
        with mock.patch.object(study_panel.messagebox, "askyesno") as caixa:
            self._no_diagrama(1, placement=ROQUEADAS)
        caixa.assert_not_called()


class DivisorTests(_Sala):
    def test_o_divisor_volta_onde_estava(self) -> None:
        self.host.pack()
        self.painel.update_idletasks()
        self.painel.divisor.configure(width=400, height=300)
        self.painel.update_idletasks()
        self.painel.posicionar_divisor(0.7)
        self.painel.update_idletasks()
        self.assertGreater(self.painel.fracao_do_divisor, 0.0)

    def test_fracao_zero_deixa_o_peso_decidir(self) -> None:
        """`0.0` é "nunca guardado", e aí quem decide é o `weight` do `PanedWindow`."""
        antes = self.painel.divisor.sashpos(0)
        self.painel.posicionar_divisor(0.0)
        self.assertEqual(self.painel.divisor.sashpos(0), antes)


class AnotacaoTests(_Sala):
    def test_o_comentario_e_gravado_no_lance_em_que_foi_escrito(self) -> None:
        """Navegar troca o nó corrente antes de a caixa perder o foco: gravar no corrente poria o
        comentário de um lance em outro."""
        self._no_diagrama(0)
        self._jogar("f8c5")
        bc5 = self.painel.estudo.no
        self.painel.comentario_text.insert("1.0", "o lance da italiana")
        self._jogar("e1g1")
        self.assertIn("o lance da italiana", bc5.comment)
        self.assertNotIn("o lance da italiana", self.painel.estudo.no.comment or "")

    def test_navegar_troca_o_comentario_mostrado(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.painel.comentario_text.insert("1.0", "primeiro")
        self._jogar("e1g1")
        self.assertEqual(self.painel.comentario_text.get("1.0", "end-1c"), "")
        self.painel.undo_move()
        self.assertEqual(self.painel.comentario_text.get("1.0", "end-1c"), "primeiro")

    def test_escrever_comentario_preserva_as_setas(self) -> None:
        """O defeito de uma linha: `no.comment = novo` apaga as setas, que moram no mesmo campo."""
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.painel.on_arrow(0, 63, "green")
        self.painel.comentario_text.insert("1.0", "vale a pena")
        self.painel.gravar_comentario()
        no = self.painel.estudo.no
        self.assertIn("%cal", no.comment)
        self.assertIn("vale a pena", no.comment)

    def test_a_seta_do_botao_direito_vai_para_o_no_e_o_mesmo_gesto_apaga(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.painel.on_arrow(0, 63, "red")
        self.assertEqual(len(self.painel.board_widget.model.arrows), 1)
        self.painel.on_arrow(0, 63, "red")
        self.assertEqual(self.painel.board_widget.model.arrows, ())

    def test_navegar_troca_as_setas_na_tela(self) -> None:
        """Elas são do lance, e não do tabuleiro."""
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.painel.on_arrow(0, 63, "green")
        self._jogar("e1g1")
        self.assertEqual(self.painel.board_widget.model.arrows, ())
        self.painel.undo_move()
        self.assertEqual(len(self.painel.board_widget.model.arrows), 1)

    def test_o_simbolo_entra_e_sai_pelo_mesmo_gesto(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.painel.alternar_nag(5)
        self.assertEqual(self.painel.estudo.no.nags, {5})
        self.assertEqual(self.painel.simbolo_var.get(), "!?")
        self.painel.alternar_nag(5)
        self.assertEqual(self.painel.estudo.no.nags, set())
        self.assertEqual(self.painel.simbolo_var.get(), "")

    def test_o_simbolo_de_posicao_soma_ao_do_lance(self) -> None:
        """`13.♗g5!? ⩲` é como o livro escreve: um julgamento do lance e um da posição."""
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.painel.alternar_nag(5)
        self.painel.alternar_nag(16)
        self.assertEqual(self.painel.estudo.no.nags, {5, 16})
        self.assertEqual(self.painel.simbolo_var.get(), "!? ±")

    def test_o_comentario_da_raiz_sai_antes_do_primeiro_lance(self) -> None:
        """O comentário da posição do diagrama é o comentário do exercício, e o PGN o escreve
        antes do primeiro lance -- que é onde quem abrir o arquivo no ChessBase vai procurá-lo."""
        self._no_diagrama(0)
        self.painel.comentario_text.insert("1.0", "exercicio 12 da pagina 143")
        self.painel.gravar_comentario()
        self._jogar("f8c5")
        pgn = self.painel.pgn_payload()
        self.assertLess(pgn.index("exercicio 12"), pgn.index("Bc5"))

    def test_diagrama_sem_posicao_valida_avisa_no_rodape_e_nao_abre_caixa(self) -> None:
        """Pré-condição de uma frase vai para o rodapé, e não para um modal (S-164)."""
        self.proxima = None
        with mock.patch.object(study_panel.messagebox, "showerror") as caixa:
            self.painel.load_from_recognized()
        caixa.assert_not_called()
        self.assertIn("Não há diagrama", self.painel.status_var.get())

    def test_a_posicao_do_diagrama_nao_recebe_simbolo_de_lance(self) -> None:
        self._no_diagrama(0)
        self.painel.alternar_nag(5)
        self.assertEqual(self.painel.estudo.raiz.nags, set())


class NomeDaAbaTests(unittest.TestCase):
    """O rename, e a tradução sem a qual ele seria um defeito silencioso (S-272)."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.host = tk.Frame(self.root)
        self.addCleanup(self.host.destroy)
        self.abas = tk.ttk.Notebook(self.host) if hasattr(tk, "ttk") else None

    def test_a_aba_se_chama_estudo_e_esta_entre_resultado_e_revisao(self) -> None:
        self.assertEqual(abas.ESTUDO, "Estudo")
        self.assertEqual(abas.DO_DIAGRAMA[:3], (abas.RESULTADO, abas.ESTUDO, abas.REVISAO))
        self.assertEqual(len(abas.ABAS), 7)

    def test_o_rotulo_guardado_como_analise_encontra_a_aba_de_hoje(self) -> None:
        """Sem isto a sessão seguinte cairia na primeira aba **em silêncio**, que é o pior jeito
        de esse defeito acontecer."""
        self.assertEqual(abas.nome_atual("Análise"), abas.ESTUDO)
        self.assertEqual(abas.nome_atual("Análise (3)"), abas.ESTUDO)

    def test_nome_que_nunca_foi_renomeado_passa_igual(self) -> None:
        self.assertEqual(abas.nome_atual("Revisão (129)"), abas.REVISAO)
        self.assertEqual(abas.nome_atual("Aba que não existe"), "Aba que não existe")

    def test_a_selecao_por_rotulo_antigo_acha_a_aba_nova(self) -> None:
        from tkinter import ttk

        caderno = ttk.Notebook(self.host)
        for nome in abas.ABAS:
            caderno.add(ttk.Frame(caderno), text=nome)
        self.assertTrue(rolagem.selecionar_aba(caderno, "Análise"))
        self.assertEqual(abas.nome_base(caderno.tab(caderno.select(), "text")), abas.ESTUDO)

    def test_rotulo_desconhecido_continua_sem_efeito(self) -> None:
        from tkinter import ttk

        caderno = ttk.Notebook(self.host)
        for nome in abas.ABAS:
            caderno.add(ttk.Frame(caderno), text=nome)
        self.assertFalse(rolagem.selecionar_aba(caderno, "Aba que não existe"))


class CoresDeSetaTests(unittest.TestCase):
    def test_as_duas_tabelas_de_cor_dizem_a_mesma_coisa(self) -> None:
        """`board_widget` não importa o estudo -- ele desenha um tabuleiro, e um tabuleiro não sabe
        o que é uma partida anotada. A duplicata é deliberada, e quem a afirma é este teste."""
        from chess_diagram_ocr.estudo import CORES_DE_SETA
        from chess_diagram_ocr.ui.board_render import PAPEL_DE_SETA
        from chess_diagram_ocr.ui.board_widget import CORES_DE_SETA as DO_WIDGET

        self.assertEqual(set(CORES_DE_SETA), set(DO_WIDGET))
        self.assertEqual(set(CORES_DE_SETA), set(PAPEL_DE_SETA))

    def test_o_modificador_escolhe_a_cor_como_no_lichess(self) -> None:
        from chess_diagram_ocr.ui.board_widget import cor_de_seta

        self.assertEqual(cor_de_seta(0), "green")
        self.assertEqual(cor_de_seta(0x0001), "red")
        self.assertEqual(cor_de_seta(0x0004), "yellow")
        self.assertEqual(cor_de_seta(0x20000), "blue")


class ModuloTests(unittest.TestCase):
    def test_o_painel_expoe_o_que_a_janela_usa(self) -> None:
        for nome in ("sync_with_ocr", "abrir_livro", "salvar_agora", "chave_do_estudo_aberto"):
            self.assertTrue(hasattr(StudyPanel, nome), nome)
        self.assertTrue(callable(study_panel.posicao_do_painel))


class CatalogoDaSalaTests(unittest.TestCase):
    """A aba deixou de ser invisível para o resto do programa (S-280).

    Medido antes da fase: 13 botões e **zero** comandos no catálogo -- logo zero na paleta da
    S-231, zero itens de menu, e nenhuma das três peles capaz de desenhar um controle dela.
    """

    def test_toda_acao_da_sala_esta_no_catalogo(self) -> None:
        self.assertEqual([], comandos.acoes_fora_do_catalogo(study_panel.COMANDOS_DA_ABA))

    def test_o_grupo_estudo_e_exatamente_a_tabela_da_aba(self) -> None:
        """Nos dois sentidos: comando do grupo que a aba não implementa é botão inerte, e método
        da aba fora do grupo é o comando que nenhuma pele desenha."""
        self.assertEqual(
            {registro.acao for registro in comandos.do_grupo(comandos.ESTUDO)},
            set(study_panel.COMANDOS_DA_ABA),
        )

    def test_o_grupo_tem_rotulo_legivel(self) -> None:
        """`"ESTUDO"` não é texto de interface, e a fita da S-227 põe o grupo num cabeçalho."""
        self.assertEqual(comandos.rotulo_do_grupo(comandos.ESTUDO), "Estudo")

    def test_todo_metodo_declarado_existe_no_painel(self) -> None:
        """A promessa vazia que `atalhos.conferir_dono` proíbe, aplicada à tabela de comandos."""
        for acao, metodo in sorted(study_panel.COMANDOS_DA_ABA.items()):
            with self.subTest(acao=acao):
                self.assertTrue(callable(getattr(StudyPanel, metodo, None)), metodo)

    def test_a_paleta_de_comandos_lista_e_executa_cada_um(self) -> None:
        """A paleta lista o catálogo inteiro; o que ela **não** executa é o que ninguém amarrou --
        e a sala amarra os vinte e quatro pela tabela."""
        amarrados = dict.fromkeys(study_panel.COMANDOS_DA_ABA, object())
        inertes = [
            entrada.acao
            for entrada in paleta_de_comandos.inventario(amarrados)
            if entrada.acao in study_panel.COMANDOS_DA_ABA and not entrada.habilitado
        ]
        self.assertEqual([], inertes)


class TeclasDaSalaTests(unittest.TestCase):
    """As quatro teclas saíram do canvas e entraram na tabela da S-161 (S-281)."""

    def test_as_setas_e_as_pontas_tem_destino_na_sala(self) -> None:
        """`na_sala` é irmão de `no_editor`: a mesma tecla, destino conforme o foco (S-244)."""
        for acao in sorted(study_panel.ACOES_PROPRIAS):
            with self.subTest(acao=acao):
                self.assertTrue(atalhos.por_acao[acao].na_sala, acao)

    def test_home_e_end_entraram_na_tabela_e_tem_comando_global(self) -> None:
        """Aqui não entra tecla sem comando global -- e a resposta que faltava desde a S-70 é
        que `Page Up`/`Page Down` viram uma página e nada levava à primeira ou à última."""
        self.assertEqual(atalhos.acao_de("<Home>"), "primeira_pagina")
        self.assertEqual(atalhos.acao_de("<End>"), "ultima_pagina")
        self.assertEqual([], comandos.acoes_fora_do_catalogo(["primeira_pagina", "ultima_pagina"]))

    def test_a_legenda_conta_os_dois_destinos(self) -> None:
        for acao in ("diagrama_anterior", "primeira_pagina"):
            with self.subTest(acao=acao):
                atalho = atalhos.por_acao[acao]
                linha = legenda._descricao(atalho)
                self.assertIn(atalho.descricao, linha)
                self.assertIn(atalho.na_sala, linha)
                self.assertIn("Na sala de estudo", linha)

    def test_o_canvas_do_tabuleiro_nao_declara_mais_tecla_nenhuma(self) -> None:
        """O `bind` que `shortcuts.owns_key` cita pelo nome. O conserto de lá tornou a colisão
        inofensiva; este é o conserto de não a ter."""
        fonte = (RAIZ / "src" / "chess_diagram_ocr" / "ui" / "study_panel.py").read_text(encoding="utf-8")
        for tecla in ("<Left>", "<Right>", "<Home>", "<End>"):
            with self.subTest(tecla=tecla):
                self.assertNotIn(f'canvas.bind("{tecla}"', fonte)


class FocoDaSalaTests(_Sala):
    def test_a_aba_declara_e_atende_as_quatro(self) -> None:
        """A promessa vazia que a S-244 proíbe: declarar e não atender **come** a tecla."""
        atalhos.conferir_dono(self.painel, "StudyPanel")

    def test_a_seta_e_da_caixa_de_comentario_enquanto_o_cursor_esta_nela(self) -> None:
        """Sem esta pergunta, escrever um comentário moveria o estudo a cada seta.

        O foco entra por `focus_get` trocado, e não por foco de verdade: a raiz da suíte é
        `withdraw`n (ver `tests/tk_root.py`), e foco em janela escondida é o tipo de coisa que
        responde diferente em cada gerenciador de janelas.
        """
        with mock.patch.object(self.painel, "focus_get", return_value=self.painel.comentario_text):
            self.assertEqual(self.painel.acoes_proprias(), frozenset())

    def test_fora_dela_a_aba_atende_as_quatro(self) -> None:
        with mock.patch.object(self.painel, "focus_get", return_value=self.painel.board_widget.canvas):
            self.assertEqual(self.painel.acoes_proprias(), study_panel.ACOES_PROPRIAS)

    def test_as_quatro_acoes_andam_pelo_estudo(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self.painel.atender("diagrama_anterior")()
        self.assertEqual(self.painel.estudo.caminho(), (0,))
        self.painel.atender("proximo_diagrama")()
        self.assertEqual(self.painel.estudo.caminho(), (0, 0))
        self.painel.atender("primeira_pagina")()
        self.assertEqual(self.painel.estudo.caminho(), ())
        self.painel.atender("ultima_pagina")()
        self.assertEqual(self.painel.estudo.caminho(), (0, 0))


class RecorteTests(_Sala):
    """A miniatura do diagrama ao lado do tabuleiro (S-282)."""

    def test_sem_ancora_nao_ha_recorte_nem_espaco_reservado(self) -> None:
        self.painel.alternar_recorte()
        self.assertFalse(self.painel.recorte_label.winfo_ismapped())

    def test_o_recorte_e_o_do_diagrama_ancora(self) -> None:
        self._no_diagrama(1)
        self.painel.alternar_recorte()
        self.root.update()
        self.assertTrue(self.painel.recorte_var.get())
        self.assertEqual(self.pedidos, [1])

    def test_a_imagem_nao_e_refeita_a_cada_lance(self) -> None:
        """Navegar redesenha o tabuleiro dezenas de vezes por minuto; reamostrar o recorte junto
        seria trabalho por nada."""
        self._no_diagrama(1)
        self.painel.alternar_recorte()
        self._jogar("f8c5", "e1g1")
        self.painel.undo_move()
        self.assertEqual(self.pedidos, [1])

    def test_trocar_de_diagrama_troca_o_recorte(self) -> None:
        self._no_diagrama(1)
        self.painel.alternar_recorte()
        self._no_diagrama(2, placement=ROQUEADAS)
        self.assertEqual(self.pedidos, [1, 2])

    def test_o_clique_amplia_no_tamanho_em_que_o_modelo_leu(self) -> None:
        """A miniatura diz *que* diagrama é; conferir **uma casa** pede o recorte inteiro."""
        self._no_diagrama(1)
        self.painel.alternar_recorte()
        self.painel.ampliar_recorte()
        janelas = [f for f in self.painel.winfo_children() if isinstance(f, tk.Toplevel)]
        self.assertEqual(len(janelas), 1)
        self.addCleanup(janelas[0].destroy)
        self.assertIn("diagrama 2", janelas[0].title())

    def test_sem_recorte_o_clique_diz_isso_e_nao_abre_janela(self) -> None:
        self.painel.ampliar_recorte()
        self.assertIn("ampliar", self.painel.status_var.get())
        self.assertEqual([f for f in self.painel.winfo_children() if isinstance(f, tk.Toplevel)], [])

    def test_o_botao_troca_de_texto_em_vez_de_virar_checkbutton(self) -> None:
        """Um `Checkbutton` não é comando: o estado dele viveria só na barra, e o mesmo comando
        pela paleta da S-231 não teria onde ler o valor de antes (S-280).

        **Com âncora**, porque é ela que dá recorte: sem uma, o botão fica cinza e o rótulo não
        troca -- ele descreveria uma miniatura que não existe (S-347).
        """
        self._no_diagrama(0)
        botao, _ = self.painel._alternaveis["mostrar_diagrama"]
        self.assertEqual(str(botao.cget("text")), comandos.rotulo_de_botao("mostrar_diagrama"))
        self.painel.alternar_recorte()
        self.assertEqual(str(botao.cget("text")), comandos.rotulo_alternado("mostrar_diagrama"))

    def test_sem_ancora_o_botao_fica_cinza_e_o_rotulo_nao_troca(self) -> None:
        """A dica promete "fica cinza quando o estudo não veio de um diagrama do livro" desde a
        S-282, e ele nunca ficava: o clique trocava o rótulo sem nada ter aparecido (S-347)."""
        botao, _ = self.painel._alternaveis["mostrar_diagrama"]
        self.painel.refresh()

        self.assertEqual(str(botao.cget("state")), "disabled")

        self.painel.alternar_recorte()

        self.assertEqual(str(botao.cget("text")), comandos.rotulo_de_botao("mostrar_diagrama"))
        self.assertIn("não veio de um diagrama", self.painel.status_var.get())


class LinhaDoLivroTests(_Sala):
    """A linha impressa vira variante -- e é o que fecha a S-208 (S-283)."""

    def test_a_linha_impressa_entra_na_arvore(self) -> None:
        self.impressa = "4.♘g5 d5 5.exd5"
        self._no_diagrama(0, vez="w")
        self.painel.jogar_a_linha_do_livro()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 3)
        self.assertIn("3 lance(s)", self.painel.status_var.get())

    def test_a_procedencia_da_linha_fica_escrita_no_pgn(self) -> None:
        """O que a pessoa jogou e o que o livro imprimiu não podem ficar indistinguíveis."""
        self.impressa = "4.♘g5 d5"
        self._no_diagrama(0, vez="w")
        self.painel.jogar_a_linha_do_livro()
        self.assertIn("linha impressa no livro", self.painel.pgn_payload())

    def test_a_linha_que_nao_fecha_para_e_diz_onde(self) -> None:
        """Contrato da S-15: propõe, marca, não reescreve calado."""
        self.impressa = "4.♘g5 d5 5.exd6"
        self._no_diagrama(0, vez="w")
        self.painel.jogar_a_linha_do_livro()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 2)
        self.assertIn("5.exd6", self.painel.status_var.get())
        self.assertIn("não é legal", self.painel.status_var.get())

    def test_a_marca_vai_no_ramo_do_livro_e_nao_no_que_a_pessoa_jogou(self) -> None:
        """S-312: a marca era posta no **primeiro filho** do nó corrente, e não no da linha lida.

        Os dois coincidem quando o nó corrente não tinha continuação -- que é o caso dos quatro
        testes acima, e é por isso que nenhum deles pegava o defeito. Quem já tinha jogado um
        lance a partir do diagrama recebia "linha impressa no livro" no **seu** lance, e o PGN
        saía atribuindo ao livro o que a pessoa jogou.

        `assertIn("linha impressa no livro", pgn)` sozinho não prova nada aqui: a frase está no
        PGN nos dois casos. O que decide é **em qual ramo** ela está.
        """
        self.impressa = "4.♘g5 d5"
        self._no_diagrama(0, vez="w")
        self._jogar("d2d4")
        self.painel.go_to_start_of_line()

        self.painel.jogar_a_linha_do_livro()

        ramos = {no.move.uci(): (no.starting_comment or "") for no in self.painel.estudo.jogo.variations}
        self.assertIn("linha impressa no livro", ramos["f3g5"])
        self.assertEqual(ramos["d2d4"], "", "o lance de quem estuda ficou marcado como do livro")

    def test_sem_folha_lida_a_aba_diz_o_que_fazer(self) -> None:
        self.impressa = ""
        self._no_diagrama(0, vez="w")
        self.painel.jogar_a_linha_do_livro()
        self.assertIn("aba Texto", self.painel.status_var.get())
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 0)

    def test_estudo_avulso_nao_tem_linha_impressa(self) -> None:
        self.proxima = PosicaoDeEstudo(placement=ITALIANA, vez="w")
        self.painel.load_from_recognized()
        self.painel.jogar_a_linha_do_livro()
        self.assertIn("não veio de um diagrama", self.painel.status_var.get())

    def test_a_linha_entra_a_partir_do_no_corrente(self) -> None:
        """Quem aperta o botão depois de andar três lances quer a continuação **dali**."""
        self.impressa = "5.exd5"
        self._no_diagrama(0, vez="w")
        self._jogar("f3g5", "d7d5")
        self.painel.jogar_a_linha_do_livro()
        self.assertEqual([no.san() for no in self.painel.estudo.raiz.mainline()], ["Ng5", "d5", "exd5"])


class VoltarAoLivroTests(_Sala):
    def test_o_comando_leva_a_pagina_da_ancora(self) -> None:
        self._no_diagrama(3)
        self.painel.ir_para_a_pagina()
        self.assertEqual(self.paginas, [(LIVRO, 142)])

    def test_sem_ancora_ele_diz_por_que_nao(self) -> None:
        self.proxima = PosicaoDeEstudo(placement=ITALIANA, vez="w")
        self.painel.load_from_recognized()
        self.painel.ir_para_a_pagina()
        self.assertEqual(self.paginas, [])
        self.assertIn("não veio de um diagrama", self.painel.status_var.get())

    def test_livro_que_saiu_do_lugar_diz_no_rodape_e_nao_levanta(self) -> None:
        self.abre_pagina = False
        self._no_diagrama(0)
        self.painel.ir_para_a_pagina()
        self.assertIn("Não foi possível abrir", self.painel.status_var.get())


class _MotorFalso:
    """O que o painel usa de um `EngineAnalyzer`: o caminho e `analyse_multi`."""

    def __init__(self, avaliacoes: list[Evaluation]) -> None:
        self.path = Path("engines/motor-de-mentira.exe")
        self._avaliacoes = avaliacoes
        self.pedidos = 0

    def analyse_multi(self, board, *, count=3, movetime_ms=None):  # noqa: ANN001, ANN202, ARG002
        self.pedidos += 1
        return list(self._avaliacoes)


def _avaliacao(cp: int, pv: tuple[str, ...], profundidade: int = 18) -> Evaluation:
    return Evaluation(
        score_cp=cp,
        mate_in=None,
        best_move=None,
        best_move_san=pv[0] if pv else "",
        pv_san=pv,
        depth=profundidade,
    )


class MotorTests(_Sala):
    """A análise contínua e os candidatos (S-285/S-286), sem abrir processo nenhum."""

    def _motor(self):  # noqa: ANN202
        return _MotorFalso([_avaliacao(35, ("Bc5", "O-O")), _avaliacao(10, ("Nf6", "d3"))])

    def test_a_resposta_atrasada_da_posicao_anterior_e_descartada(self) -> None:
        """**A regressão do item.** A thread guardava a posição e o `after(0, ...)` não a conferia:
        trocar de diagrama durante uma análise escrevia a avaliação da posição anterior sobre a
        nova -- e com a sala isso passou a ser um clique."""
        self._no_diagrama(0)
        velha = self.painel._geracao
        no = self.painel.estudo.no
        self._jogar("f8c5")
        self.painel._show_evaluation(velha, no, [_avaliacao(999, ("Qh5",))])
        self.assertEqual(self.painel.engine_var.get(), "")
        self.assertEqual(self.painel._candidatos, [])

    def test_a_avaliacao_fica_no_lance_e_volta_pelo_pgn(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.painel._show_evaluation(self.painel._geracao, self.painel.estudo.no, self.motor._avaliacoes)
        self.assertIn("%eval", self.painel.pgn_payload())
        volta = Estudo.de_pgn(self.painel.pgn_payload())
        self.assertIsNotNone(volta.jogo.variations[0].eval())

    def test_a_avaliacao_nao_entra_na_pilha_de_desfazer(self) -> None:
        """Um número que o motor escreveu sozinho não é edição de quem estuda."""
        self._no_diagrama(0)
        self._jogar("f8c5")
        antes = self.painel.edicao
        self.painel._show_evaluation(self.painel._geracao, self.painel.estudo.no, self.motor._avaliacoes)
        self.assertEqual(self.painel.edicao, antes)

    def test_a_avaliacao_sozinha_nao_cria_estudo_na_sala(self) -> None:
        """Navegar com o motor ligado não pode encher a sala de posições sem análise humana."""
        self.painel.sala.documento = LIVRO
        self._no_diagrama(0)
        self.painel._show_evaluation(self.painel._geracao, self.painel.estudo.no, self.motor._avaliacoes)
        self.assertEqual(len(self.painel.sala), 0)

    def test_os_candidatos_aparecem_em_ordem(self) -> None:
        self._no_diagrama(0)
        self.painel._show_evaluation(self.painel._geracao, self.painel.estudo.no, self.motor._avaliacoes)
        linhas = self.painel.engine_line_var.get().splitlines()
        self.assertEqual(len(linhas), 2)
        self.assertTrue(linhas[0].startswith("1."))
        self.assertIn("Bc5", linhas[0])

    def test_a_linha_do_motor_vira_variante_com_a_procedencia(self) -> None:
        """O que a máquina sugeriu e o que a pessoa jogou não podem ficar indistinguíveis (S-286)."""
        self._no_diagrama(0)
        self.painel._show_evaluation(self.painel._geracao, self.painel.estudo.no, self.motor._avaliacoes)
        self.painel.variante_do_motor()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 2)
        self.assertIn("motor-de-mentira", self.painel.pgn_payload())

    def test_sem_resposta_do_motor_ele_diz_isso_em_vez_de_inventar(self) -> None:
        self._no_diagrama(0)
        self.painel.variante_do_motor()
        self.assertIn("ainda não respondeu", self.painel.status_var.get())

    def _analise_sincrona(self):  # noqa: ANN202
        """A análise **sem thread**, para o teste poder afirmar o resultado dela (S-413).

        `analyse` sobe uma thread de verdade -- o motor é de mentira, a thread não -- e ela volta
        por `after(0, ...)`. Num teste isso não funciona e ainda vaza: o Tk recusa a chamada de
        outra thread enquanto a principal não está **dentro** do laço (`RuntimeError: main thread
        is not in main loop`), e a thread morre com esse erro depois que o `tearDown` já destruiu
        o painel -- então o rastro aparece no teste seguinte. Era o defeito que o
        `sem_thread_vazada` do `conftest` passou a acusar.

        Rodar o alvo na hora troca a corrida por uma ordem: o `after(0, ...)` sai da thread
        principal, que é onde ele é legal, e o `update` abaixo o executa.
        """

        class Imediata:
            def __init__(self, *, target, args=(), daemon=False, **_):  # noqa: ANN001, ANN003, ARG002
                self._alvo, self._args = target, args

            def start(self) -> None:
                self._alvo(*self._args)

        return mock.patch.object(study_panel.threading, "Thread", Imediata)

    def test_a_analise_continua_alterna_e_o_botao_conta(self) -> None:
        self._no_diagrama(0)
        with self._analise_sincrona():
            self.painel.alternar_analise_continua()
            self.assertTrue(self.painel.continua_var.get())
            botao, _ = self.painel._alternaveis["analise_continua"]
            self.assertEqual(str(botao.cget("text")), comandos.rotulo_alternado("analise_continua"))

            self.painel.alternar_analise_continua()
            self.assertFalse(self.painel.continua_var.get())
            self.assertEqual(self.painel.engine_var.get(), "")

            # **O `update` fica aqui dentro, e depois de desligar.** Ele executa os `after(0, ...)`
            # que o trabalho enfileirou -- e é o que impede que eles rodem num teste seguinte,
            # sobre um painel destruído. Com a análise contínua **ligada** ele não poderia rodar:
            # `_finish_analysis` pede a próxima, que com a thread síncrona seria a mesma chamada
            # de novo, para sempre.
            self.root.update()


class SemMotorTests(_Sala):
    """Sem binário a seção não existe -- e os comandos dizem por quê em vez de ficarem cinzas."""

    def test_a_secao_do_motor_nao_e_montada(self) -> None:
        self.assertFalse(self.painel.has_engine)
        self.assertFalse(hasattr(self.painel, "btn_analyse"))

    def test_os_comandos_do_motor_dizem_o_que_falta(self) -> None:
        for metodo in (self.painel.analyse, self.painel.alternar_analise_continua, self.painel.variante_do_motor):
            with self.subTest(metodo=metodo.__name__):
                metodo()
                self.assertIn("Sem motor UCI", self.painel.status_var.get())


class PartidasDaPosicaoTests(_Sala):
    """A base do usuário perguntada do tabuleiro (S-287)."""

    def test_sem_base_a_aba_diz_onde_por_os_pgn(self) -> None:
        self._no_diagrama(0)
        self.painel.partidas_da_posicao()
        self.assertIn("pgn_database/", self.painel.status_var.get())

    def test_com_partidas_a_janela_lista_o_que_a_base_guardou(self) -> None:
        guardada = CachedPosition(
            count=2,
            games=(
                PositionHit(move_number=12, side_to_move="w", headers={"White": "Capablanca", "Black": "Alekhine"}),
                PositionHit(move_number=14, side_to_move="b", headers={"White": "Tal", "Black": "Botvinnik"}),
            ),
        )
        self._no_diagrama(0)
        self.painel._loja = _LojaDeMentira({self.painel.estudo.tabuleiro.board_fen(): guardada})
        self.bases = (Path("pgn_database/gigabase.pgn"),)
        self.painel.partidas_da_posicao()
        janela = next(
            filho for filho in self.painel.winfo_children() if isinstance(filho, study_panel._JanelaDePartidas)
        )
        self.addCleanup(janela.destroy)
        self.root.update()
        self.assertEqual(len(janela.linhas()), 2)
        self.assertIn("Capablanca", janela.linhas()[0])

    def test_posicao_nao_perguntada_nao_abre_janela(self) -> None:
        self._no_diagrama(0)
        self.painel._loja = _LojaDeMentira({})
        self.bases = (Path("pgn_database/gigabase.pgn"),)
        self.painel.partidas_da_posicao()
        self.assertIn("cvoff-games", self.painel.status_var.get())
        self.assertEqual([f for f in self.painel.winfo_children() if isinstance(f, tk.Toplevel)], [])


class _LojaDeMentira:
    def __init__(self, guardadas: dict) -> None:
        self.guardadas = guardadas

    def missing(self, targets) -> set[str]:  # noqa: ANN001
        return {alvo for alvo in targets if alvo not in self.guardadas}

    def get(self, placement: str) -> CachedPosition:
        return self.guardadas.get(placement, CachedPosition())


class ColarEAbrirTests(_Sala):
    """A entrada da sala: colar e abrir (S-288)."""

    def _colar(self, texto: str) -> None:
        self.painel._aceitar_colado(texto)

    def test_uma_fen_colada_vira_o_estudo_aberto(self) -> None:
        self._colar(f"{ROQUEADAS} b - - 4 21")
        self.assertEqual(self.painel.estudo.tabuleiro.board_fen(), ROQUEADAS)
        self.assertFalse(self.painel.estudo.tabuleiro.turn)

    def test_um_pgn_colado_vira_a_arvore(self) -> None:
        self._colar("1. e4 e5 2. Nf3 Nc6 *")
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 4)

    def test_pgn_com_lance_que_nao_fecha_diz_qual_e_nao_descarta_o_aberto(self) -> None:
        """Critério de aceite do item: o que estava na mesa continua lá."""
        self._no_diagrama(0)
        self._jogar("f8c5")
        self._colar("1. e4 e5 2. Qh8 *")
        self.assertIn("Qh8", self.painel.status_var.get())
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 1)

    def test_colar_sobre_um_estudo_avulso_com_lances_pergunta_antes(self) -> None:
        self.proxima = PosicaoDeEstudo(placement=ITALIANA, vez="w")
        self.painel.load_from_recognized()
        self._jogar("e1g1")
        with mock.patch.object(study_panel.messagebox, "askyesno", return_value=False) as caixa:
            self._colar("1. e4 e5 *")
        caixa.assert_called_once()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 1)

    def test_colar_recomeca_a_pilha_de_desfazer(self) -> None:
        """`Ctrl+Z` que atravessasse a troca desfaria um lance que não está na tela."""
        self._no_diagrama(0)
        self._jogar("f8c5")
        self._colar("1. e4 e5 *")
        self.painel.desfazer()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 2)

    def test_um_pgn_de_uma_partida_abre_como_estudo(self) -> None:
        arquivo = Path(self.tmp.name) / "uma.pgn"
        arquivo.write_text("1. e4 e5 2. Nf3 *\n", encoding="utf-8")
        with mock.patch.object(study_panel.filedialog, "askopenfilename", return_value=str(arquivo)):
            self.painel.abrir_pgn()
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 3)

    def test_a_colecao_do_livro_volta_para_a_sala(self) -> None:
        """**O caminho de volta de quem editou a coleção no ChessBase**: as partidas trazem
        `SourcePDF`, `Page` e `Diagram`, e por isso elas sabem em que mesa sentar."""
        self.painel.sala.documento = LIVRO
        for diagrama in (0, 1):
            self._no_diagrama(diagrama)
            self._jogar("f8c5")
        arquivo = Path(self.tmp.name) / "colecao.pgn"
        arquivo.write_text(estudo_arquivo.para_pgn(self.painel.sala) + "\n", encoding="utf-8")
        self.painel.sala = type(self.painel.sala)(LIVRO)

        with mock.patch.object(study_panel.filedialog, "askopenfilename", return_value=str(arquivo)):
            self.painel.abrir_pgn()
        self.assertEqual(len(self.painel.sala), 2)
        self.assertIn("entraram na sala", self.painel.status_var.get())

    def test_um_pgn_de_muitas_partidas_de_fora_abre_a_lista(self) -> None:
        arquivo = Path(self.tmp.name) / "base.pgn"
        arquivo.write_text(
            '[White "Capablanca"]\n[Black "Alekhine"]\n[Date "1927.??.??"]\n\n1. d4 d5 *\n\n'
            '[White "Tal"]\n[Black "Botvinnik"]\n\n1. e4 c5 *\n',
            encoding="utf-8",
        )
        with mock.patch.object(study_panel.filedialog, "askopenfilename", return_value=str(arquivo)):
            self.painel.abrir_pgn()
        janela = next(
            f for f in self.painel.winfo_children() if isinstance(f, study_panel._JanelaDeColecao)
        )
        self.addCleanup(janela.destroy)
        self.root.update()
        self.assertEqual(len(janela.linhas()), 2)
        self.assertIn("Capablanca", janela.linhas()[0])
        self.assertIn("1927", janela.linhas()[0])

    def test_escolher_da_lista_abre_a_partida(self) -> None:
        escolhido, _ = estudo_mod.colar("1. e4 c5 2. Nf3 *")
        self.painel._escolher_da_colecao(escolhido)
        self.assertEqual(self.painel.estudo.contagem_de_lances(), 3)

    def test_arquivo_sem_partida_legivel_diz_isso(self) -> None:
        arquivo = Path(self.tmp.name) / "vazio.pgn"
        arquivo.write_text("isto não é um PGN\n", encoding="utf-8")
        with mock.patch.object(study_panel.filedialog, "askopenfilename", return_value=str(arquivo)):
            self.painel.abrir_pgn()
        self.assertIn("não tem nenhuma partida legível", self.painel.status_var.get())


class ExportarEstudoTests(_Sala):
    """As três saídas da Fase 39 alimentadas pelo estudo (S-289)."""

    def _exportar(self, extensao: str) -> Path:
        destino = Path(self.tmp.name) / f"saida{extensao}"
        with mock.patch.object(study_panel.filedialog, "asksaveasfilename", return_value=str(destino)):
            getattr(self.painel, f"exportar_estudo_{extensao.lstrip('.')}")()
        return destino

    def test_o_markdown_traz_o_titulo_a_fen_e_a_linha(self) -> None:
        self._no_diagrama(1)
        self._jogar("f8c5", "e1g1")
        destino = self._exportar(".md")
        conteudo = destino.read_text(encoding="utf-8")
        self.assertIn("Secrets.pdf", conteudo)
        self.assertIn("FEN: ", conteudo)
        self.assertIn("4... Bc5", conteudo)

    def test_o_recorte_e_gravado_ao_lado_e_o_markdown_o_aponta(self) -> None:
        """**O primeiro cliente de `recortes=`**, que existe em `exportar` desde a S-250 e nunca
        teve quem o usasse."""
        self._no_diagrama(1)
        self._jogar("f8c5")
        destino = self._exportar(".md")
        imagem = destino.parent / "diagramas" / f"{destino.stem}.png"
        self.assertTrue(imagem.exists())
        self.assertIn(f"diagramas/{imagem.name}", destino.read_text(encoding="utf-8"))

    def test_os_tres_formatos_gravam(self) -> None:
        self._no_diagrama(1)
        self._jogar("f8c5")
        for extensao in (".md", ".html", ".rtf"):
            with self.subTest(formato=extensao):
                destino = self._exportar(extensao)
                self.assertGreater(destino.stat().st_size, 0)

    def test_o_rodape_conta_o_que_foi_gravado(self) -> None:
        self._no_diagrama(1)
        self._jogar("f8c5")
        self._exportar(".md")
        self.assertIn("saida.md", self.painel.status_var.get())

    def test_o_nome_sugerido_traz_livro_pagina_e_diagrama(self) -> None:
        self._no_diagrama(1)
        self.assertEqual(self.painel._nome_sugerido(), "Secrets_p143_d2")

    def test_estudo_avulso_sugere_um_nome_generico(self) -> None:
        self.assertEqual(self.painel._nome_sugerido(), "estudo")

    def test_cancelar_o_dialogo_nao_grava_nada(self) -> None:
        self._no_diagrama(1)
        with mock.patch.object(study_panel.filedialog, "asksaveasfilename", return_value=""):
            self.painel.exportar_estudo_md()
        self.assertEqual(list(Path(self.tmp.name).glob("*.md")), [])


class ParaOTextoTests(_Sala):
    """O inverso exato da S-283: a variante vira parágrafo (S-289)."""

    def test_a_linha_vai_para_a_aba_de_texto(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1")
        self.painel.levar_para_o_texto()
        self.assertEqual(len(self.para_o_texto), 1)
        self.assertIn("4... Bc5", self.para_o_texto[0])
        self.assertIn("5. O-O", self.para_o_texto[0])

    def test_estudo_sem_lance_nao_manda_nada(self) -> None:
        self._no_diagrama(0)
        self.painel.levar_para_o_texto()
        self.assertEqual(self.para_o_texto, [])
        self.assertIn("Não há lance", self.painel.status_var.get())

    def test_aba_que_nao_recebe_e_dita_no_rodape(self) -> None:
        self.aceita_texto = False
        self._no_diagrama(0)
        self._jogar("f8c5")
        self.painel.levar_para_o_texto()
        self.assertIn("não está pronta", self.painel.status_var.get())


class TreinoTests(_Sala):
    """Adivinhar o lance: a linha some e o tabuleiro cobra (S-290)."""

    def _com_linha(self) -> None:
        self._no_diagrama(0)
        self._jogar("f8c5", "e1g1", "e8g8")
        self.painel.go_to_start_of_line()
        self.painel.alternar_treino()

    def test_a_linha_some_da_lista(self) -> None:
        self._com_linha()
        texto = self._texto_da_lista()
        self.assertNotIn("Bc5", texto)
        self.assertNotIn("O-O", texto)

    def test_o_lance_certo_avanca_e_conta(self) -> None:
        self._com_linha()
        self._jogar("f8c5")
        self.assertEqual(self.painel.estudo.caminho(), (0,))
        self.assertIn("certo", self.painel.status_var.get())
        self.assertIn("1 certo", self.painel.placar_var.get())

    def test_o_lance_errado_nao_cria_variante(self) -> None:
        """**O critério de aceite do item**: o modo não altera a árvore."""
        self._com_linha()
        antes = self.painel.estudo.contagem_de_lances()
        self._jogar("b8c6")
        self.assertEqual(self.painel.estudo.contagem_de_lances(), antes)
        self.assertEqual(self.painel.estudo.caminho(), ())
        self.assertIn("não é o lance da linha", self.painel.status_var.get())
        self.assertIn("1 errado", self.painel.placar_var.get())

    def test_o_erro_diz_como_guardar_o_lance(self) -> None:
        """"a menos que se peça" -- e o pedido é desligar o treino, dito na própria frase."""
        self._com_linha()
        self._jogar("b8c6")
        self.assertIn("Desligue o treino", self.painel.status_var.get())

    def test_o_placar_fica_fora_do_arquivo(self) -> None:
        """Desempenho de quem estuda não é anotação da partida."""
        self._com_linha()
        self._jogar("f8c5")
        self._jogar("d7d5")
        self.assertNotIn("certo", self.painel.pgn_payload())
        self.assertNotIn("errado", self.painel.pgn_payload())

    def test_o_fim_da_linha_diz_que_acabou(self) -> None:
        self._com_linha()
        for uci in ("f8c5", "e1g1", "e8g8"):
            self._jogar(uci)
        self._jogar("d7d5")
        self.assertIn("Fim da linha", self.painel.status_var.get())

    def test_desligar_o_treino_devolve_a_linha_e_zera_o_placar(self) -> None:
        self._com_linha()
        self._jogar("b8c6")
        self.painel.alternar_treino()
        self.assertIn("Bc5", self._texto_da_lista())
        self.assertEqual(self.painel.placar_var.get(), "")

    def test_com_o_treino_desligado_o_lance_diferente_volta_a_criar_variante(self) -> None:
        self._com_linha()
        self.painel.alternar_treino()
        antes = self.painel.estudo.contagem_de_lances()
        self._jogar("b8c6")
        self.assertEqual(self.painel.estudo.contagem_de_lances(), antes + 1)

    def test_o_botao_troca_de_texto(self) -> None:
        botao, _ = self.painel._alternaveis["modo_treino"]
        self.assertEqual(str(botao.cget("text")), comandos.rotulo_de_botao("modo_treino"))
        self.painel.alternar_treino()
        self.assertEqual(str(botao.cget("text")), comandos.rotulo_alternado("modo_treino"))


class ComentarioNaoConfirmadoTests(_Sala):
    """O comentário digitado e não confirmado sobrevive ao fechamento (S-302).

    **O defeito.** O texto da caixa só entra no nó quando ela perde o foco: os onze chamadores
    de `gravar_comentario` são todos de navegação e de exportação. `salvar_agora` -- que é o
    que `app_tkinter._on_close` chama ao fechar a janela, e o que a inatividade agenda -- saía
    em `if not self._sujo` sem olhar a caixa. Quem escrevia uma nota e fechava o programa com o
    cursor ainda dentro dela perdia a nota, e nada avisava: o `tem_trabalho_por_gravar` que
    alimenta o aviso de fechamento também lê `_sujo`, então ele dizia que não havia trabalho.

    **A ordem é o item.** `gravar_comentario` tem de vir *antes* do teste de `_sujo`, porque é
    ela quem liga `_sujo`.
    """

    def _com_um_lance(self) -> None:
        self._no_diagrama(1)
        self._jogar("f8c5")
        self.painel.salvar_agora()

    def test_o_comentario_digitado_e_nao_confirmado_e_gravado(self) -> None:
        self._com_um_lance()
        self.painel.comentario_text.insert("1.0", "o centro fecha e a coluna abre")

        self.painel.salvar_agora()

        self.assertIn("o centro fecha e a coluna abre", self.painel.estudo.no.comment or "")

    def test_o_texto_so_na_tela_e_invisivel_ao_aviso_de_fechamento(self) -> None:
        """A metade que explica por que nada avisava.

        `tem_trabalho_por_gravar` -- o `loses_work` do `BusyRegistry` aplicado à sala -- também
        lê `_sujo`. Com a nota apenas na caixa, ele responde "nada a gravar", e o fechamento não
        pergunta. Ou seja: o programa não só perdia a nota, ele afirmava que não havia nada a
        perder. Por isso a correção tem de estar em `salvar_agora`, e não numa pergunta a mais
        no fechamento.

        `_sujo = False` à mão é a sala recém-gravada: a gravação de verdade precisaria de um
        livro aberto, que não é o que este teste mede.
        """
        self._com_um_lance()
        self.painel._sujo = False

        self.painel.comentario_text.insert("1.0", "ainda por confirmar")
        self.assertFalse(self.painel.tem_trabalho_por_gravar())

        self.painel.salvar_agora()

        self.assertIn("ainda por confirmar", self.painel.estudo.no.comment or "")
        self.assertTrue(self.painel.tem_trabalho_por_gravar())

    def test_sala_limpa_e_sem_comentario_novo_nao_grava(self) -> None:
        """A correção não pode fazer toda inatividade regravar o arquivo: `gravar_comentario`
        sai cedo quando o texto é o mesmo, e `salvar_agora` continua devolvendo `None`."""
        self._com_um_lance()

        self.assertIsNone(self.painel.salvar_agora())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class GravacaoPorInatividadeTests(_Sala):
    """A escrita do motor não adia a gravação da sala (S-345).

    Com a análise contínua ligada, o motor grava `[%eval ...]` a cada ~800 ms, e cada escrita
    cancelava e reagendava o prazo de inatividade: ele nunca vencia, e a sala **nunca chegava ao
    disco** enquanto o motor estivesse ligado.
    """

    def test_a_avaliacao_do_motor_nao_empurra_o_relogio(self) -> None:
        self._no_diagrama(0)
        self.painel._marcar_sujo()
        agendada = self.painel._gravacao_agendada
        self.assertIsNotNone(agendada, "uma edição de gente marca a gravação")

        self.painel._marcar_sujo(historico=False, da_maquina=True)

        self.assertIs(self.painel._gravacao_agendada, agendada, "o motor reagendou o prazo")

    def test_a_edicao_de_gente_continua_empurrando(self) -> None:
        self._no_diagrama(0)
        self.painel._marcar_sujo()
        agendada = self.painel._gravacao_agendada

        self.painel._marcar_sujo()

        self.assertIsNotNone(self.painel._gravacao_agendada)
        self.assertNotEqual(self.painel._gravacao_agendada, agendada)

    def test_sem_nada_marcado_a_maquina_marca(self) -> None:
        """Senão a avaliação de um estudo que ninguém mais tocar não chegaria ao disco."""
        self._no_diagrama(0)
        self.painel.salvar_agora()
        self.assertIsNone(self.painel._gravacao_agendada)

        self.painel._marcar_sujo(historico=False, da_maquina=True)

        self.assertIsNotNone(self.painel._gravacao_agendada)


class VirarTabuleiroTests(_Sala):
    """Virar o tabuleiro é vista, e não edição (S-346)."""

    def test_virar_nao_conta_como_edicao(self) -> None:
        """`_edicao` é o que diz a `ui/desfazivel.py` qual painel recebe o `Ctrl+Z`: virar o
        tabuleiro sequestrava a tecla e não desfazia nada."""
        self._no_diagrama(0)
        antes = self.painel.edicao
        orientacao = self.painel.estudo.invertido

        self.painel.flip_board()

        self.assertEqual(self.painel.edicao, antes)
        self.assertNotEqual(self.painel.estudo.invertido, orientacao)

    def test_virar_continua_marcando_a_sala_como_suja(self) -> None:
        """`invertido` é gravado com o estudo: a orientação sobrevive a fechar a janela."""
        self._no_diagrama(0)
        self.painel.salvar_agora()

        self.painel.flip_board()

        self.assertTrue(self.painel._sujo)
        self.assertIsNotNone(self.painel._gravacao_agendada, "gesto de gente empurra o relógio")


class PgnAtomicoTests(_Sala):
    """Sobrescrever o PGN de um estudo não pode truncar o que estava lá (S-346)."""

    def test_sobrescrever_passa_pela_escrita_atomica(self) -> None:
        from chess_diagram_ocr import atomic_io

        self._no_diagrama(0)
        destino = Path(self.tmp.name) / "estudo.pgn"
        destino.write_text("PGN de outro dia\n", encoding="utf-8")
        chamadas: list[Path] = []
        original = atomic_io.atomic_write_text

        def espiao(caminho, payload, **kwargs):  # noqa: ANN001, ANN202
            chamadas.append(Path(caminho))
            return original(caminho, payload, **kwargs)

        atomic_io.atomic_write_text = espiao  # type: ignore[assignment]
        self.addCleanup(setattr, atomic_io, "atomic_write_text", original)

        self.painel.write_pgn(destino, append=False)

        self.assertEqual(chamadas, [destino])
        self.assertNotIn("outro dia", destino.read_text(encoding="utf-8"))

    def test_acrescentar_continua_acrescentando(self) -> None:
        """O `append` nunca trunca: o risco dele é outro, e está escrito no docstring."""
        self._no_diagrama(0)
        destino = Path(self.tmp.name) / "colecao.pgn"
        destino.write_text('[Event "de ontem"]\n\n*\n', encoding="utf-8")

        self.painel.write_pgn(destino, append=True)

        self.assertIn("de ontem", destino.read_text(encoding="utf-8"))


class ReabrirAMesaTests(_Sala):
    """`estudo_aberto` era gravado no estado e nunca lido (S-347)."""

    def test_reabrir_por_chave_volta_ao_estudo_daquele_diagrama(self) -> None:
        self._no_diagrama(1)
        self._jogar("f8c5")  # um lance de verdade: estudo vazio não fica guardado na sala
        chave = self.painel.chave_do_estudo_aberto
        self.assertTrue(chave)
        self._no_diagrama(0)
        self.assertNotEqual(self.painel.chave_do_estudo_aberto, chave)

        self.assertTrue(self.painel.reabrir_por_chave(chave))

        self.assertEqual(self.painel.chave_do_estudo_aberto, chave)

    def test_chave_que_nao_existe_mais_nao_levanta(self) -> None:
        """Livro revarrido, diagrama com outro número: voltar à porta da sala é a degradação certa."""
        self._no_diagrama(0)
        self.assertFalse(self.painel.reabrir_por_chave("nao_existe_p9_d9"))
        self.assertFalse(self.painel.reabrir_por_chave(""))
