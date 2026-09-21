"""O painel de Resultado do Qt: o que ele acrescentou ao que a janela já fazia (S-503).

**O que estes testes cobrem, e o que não.** A gravação é de `tests/test_qt_gravacao.py`, a edição
do tabuleiro é de `tests/test_qt_tabuleiro_editavel.py`, e as decisões que o painel chama --
`DiagramEditorModel`, `Historico`, `explain_position`, `board_edit` -- são puras e afirmadas nos
testes delas. Repetir qualquer uma aqui mediria o mesmo código duas vezes.

O que só existe deste lado é o que o porte **acrescentou** à janela: aplicar a FEN digitada,
desfazer e refazer por diagrama, trocar o lado a jogar, o estado vazio e a navegação. E, acima de
tudo, o que amarra os cinco: `_atualizar_tudo`, o único lugar que repõe o que depende do estado --
no Tk isso eram `update_views`, `update_legality` e `sync_side_widgets` separados, esquecidos um
de cada vez.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.config import PIECE_CLASSES
from chess_diagram_ocr.service import RecognizedDiagram
from chess_diagram_ocr.ui import atalhos, board_edit, comandos, strings

if TEM_PYQT:
    from chess_diagram_ocr.qt import decisoes_de_diagrama
    from chess_diagram_ocr.qt.painel_de_resultado import (
        MENSAGEM_VAZIA,
        MOTIVO_SEM_DIAGRAMA,
        PainelDeResultado,
        _girar_180,
    )

LEGAL = "4k3/8/8/8/8/8/8/4K3"
OUTRA = "8/8/8/4k3/8/8/8/4K3"


def diagrama(placement: str = LEGAL, *, indice: int = 0, probs: np.ndarray | None = None) -> RecognizedDiagram:
    return RecognizedDiagram(
        index=indice,
        board_rgb=np.full((64, 64, 3), 200, np.uint8),
        placement=placement,
        min_confidence=0.93,
        square_confidences=[0.99] * 64,
        side_to_move="w",
        probs=probs,
    )


def probs_que_hesitam_em(casa: int) -> np.ndarray:
    """(64, 13) certa de «vazia» em tudo, menos na casa dada: 0,60 dama branca × 0,35 dama preta."""
    probs = np.zeros((64, len(PIECE_CLASSES)))
    probs[:, PIECE_CLASSES.index("empty")] = 1.0
    probs[casa] = 0.0
    probs[casa, PIECE_CLASSES.index("Q")] = 0.6
    probs[casa, PIECE_CLASSES.index("q")] = 0.35
    probs[casa, PIECE_CLASSES.index("empty")] = 0.05
    return probs


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PainelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.painel = PainelDeResultado(mock.MagicMock(), csv_de_rotulos=pasta_temporaria(self) / "l.csv")
        self.addCleanup(self.painel.deleteLater)
        self.recados: list[str] = []
        self.painel.estado.connect(self.recados.append)

    def carregar(self, *placements: str) -> None:
        itens = [diagrama(p, indice=i) for i, p in enumerate(placements or (LEGAL,))]
        self.painel.carregar_pagina(itens, chave="livro.pdf", pagina=0)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class EstadoVazioTests(PainelTests):
    """O item da S-170: sem ele, "Salvar" grava a posição inicial como leitura de uma página."""

    def test_o_painel_vazio_diz_o_que_fazer(self) -> None:
        self.assertEqual(self.painel.legalidade.text(), MENSAGEM_VAZIA)
        self.assertEqual(self.painel.campo_fen.text(), "")

    def test_as_acoes_que_nao_tem_o_que_fazer_ficam_cinzas(self) -> None:
        for botao in (
            self.painel.btn_salvar,
            self.painel.btn_salvar_todos,
            self.painel.btn_limpar,
            self.painel.btn_aplicar,
            self.painel.copiar,
        ):
            with self.subTest(botao=botao.text()):
                self.assertFalse(botao.isEnabled())

    def test_o_botao_cinza_diz_por_que(self) -> None:
        """A regra da S-165, que achou treze botões cinzas e mudos."""
        self.assertIn("Não há diagrama", self.painel.btn_salvar.toolTip())

    def test_o_tabuleiro_vazio_nao_e_a_posicao_inicial(self) -> None:
        """**É o defeito inteiro da S-170.** O padrão do tabuleiro é a posição inicial, e um
        painel que a mostrasse pareceria um diagrama reconhecido."""
        self.assertEqual(self.painel.tabuleiro.posicao(), board_edit.EMPTY_PLACEMENT)

    def test_carregar_e_limpar_volta_ao_vazio(self) -> None:
        self.carregar(LEGAL)
        self.assertTrue(self.painel.btn_salvar.isEnabled())
        self.painel.limpar()
        self.assertFalse(self.painel.btn_salvar.isEnabled())
        self.assertEqual(self.painel.legalidade.text(), MENSAGEM_VAZIA)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class NavegacaoTests(PainelTests):
    """A lista, o seletor e as duas setas -- e o que eles fazem com a pilha de desfazer."""

    def test_andar_para_nas_pontas(self) -> None:
        """Quem aperta `→` no último diagrama quer o último: voltar ao primeiro faz a pessoa
        perder onde estava numa página de nove."""
        self.carregar(LEGAL, OUTRA)
        self.painel.andar(-1)
        self.assertEqual(self.painel.lista.currentRow(), 0)
        self.painel.andar(1)
        self.painel.andar(1)
        self.assertEqual(self.painel.lista.currentRow(), 1)

    def test_as_setas_apagam_nas_pontas(self) -> None:
        self.carregar(LEGAL, OUTRA)
        self.assertFalse(self.painel.anterior.isEnabled())
        self.assertTrue(self.painel.proximo.isEnabled())
        self.painel.andar(1)
        self.assertTrue(self.painel.anterior.isEnabled())
        self.assertFalse(self.painel.proximo.isEnabled())

    def test_o_seletor_acompanha_e_manda(self) -> None:
        self.carregar(LEGAL, OUTRA)
        self.painel.andar(1)
        self.assertEqual(self.painel.seletor.value(), 2)
        self.painel.seletor.setValue(1)
        self.assertEqual(self.painel.lista.currentRow(), 0)

    def test_trocar_de_diagrama_zera_a_pilha(self) -> None:
        """**A pilha é por diagrama** (S-229): `Ctrl+Z` depois de andar tem de devolver a posição
        anterior *deste* diagrama, e não a correção do vizinho."""
        self.carregar(LEGAL, OUTRA)
        self.painel._tabuleiro_mudou(board_edit.set_piece(LEGAL, 27, "Q"))
        self.assertTrue(self.painel.historico.pode_desfazer)
        self.painel.andar(1)
        self.assertFalse(self.painel.historico.pode_desfazer)

    def test_a_selecao_e_anunciada_para_a_janela(self) -> None:
        """É por este sinal que o visor destaca a caixa do diagrama em edição."""
        vistos: list[int] = []
        self.painel.selecionou.connect(vistos.append)
        self.carregar(LEGAL, OUTRA)
        self.painel.andar(1)
        self.assertEqual(vistos, [0, 1])


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FenTests(PainelTests):
    """A quarta origem de uma correção (S-229): a FEN digitada."""

    def test_aplicar_a_fen_digitada_muda_o_tabuleiro(self) -> None:
        self.carregar(LEGAL)
        corrigida = board_edit.set_piece(LEGAL, 27, "Q")
        self.painel.campo_fen.setText(corrigida)
        self.painel.aplicar_fen()
        self.assertEqual(self.painel.tabuleiro.posicao(), corrigida)
        self.assertEqual(self.painel.modelo.fen_at(0), corrigida)

    def test_a_fen_invalida_avisa_e_nao_muda_nada(self) -> None:
        """Aceitar um campo malformado daria 64 casas inventadas, e quem digitou não saberia
        que o que está na tela não é o que escreveu."""
        self.carregar(LEGAL)
        self.painel.campo_fen.setText("isto não é uma FEN")
        self.painel.aplicar_fen()
        self.assertEqual(self.painel.tabuleiro.posicao(), LEGAL)
        self.assertIn("não descreve um tabuleiro", self.recados[-1])

    def test_a_fen_aplicada_entra_na_pilha(self) -> None:
        self.carregar(LEGAL)
        self.painel.campo_fen.setText(board_edit.set_piece(LEGAL, 27, "Q"))
        self.painel.aplicar_fen()
        self.assertTrue(self.painel.historico.pode_desfazer)

    def test_a_edicao_no_tabuleiro_reescreve_o_campo(self) -> None:
        """O campo de texto segue funcionando: as duas metades mostram a mesma posição."""
        self.carregar(LEGAL)
        corrigida = board_edit.set_piece(LEGAL, 27, "Q")
        self.painel._tabuleiro_mudou(corrigida)
        self.assertIn(corrigida, self.painel.campo_fen.text())

    def test_a_tecla_de_aplicar_e_a_da_tabela(self) -> None:
        """`Ctrl+Enter` é declarada no próprio campo, que é o mecanismo da S-117: quem declara
        a sequência fica com ela, e a guarda de foco cede."""
        esperada = atalhos.por_acao["aplicar_fen"]
        acoes = [a.shortcut().toString() for a in self.painel.campo_fen.actions()]
        self.assertIn("Ctrl+Return", acoes)
        self.assertEqual(esperada.rotulo, "Ctrl+Enter")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LadoELegalidadeTests(PainelTests):
    """O painel de legalidade da S-21, e a vez que muda a resposta dele (S-17)."""

    def test_a_legalidade_e_o_material_aparecem(self) -> None:
        self.carregar(LEGAL)
        self.assertIn("legal", self.painel.legalidade.text().lower())
        self.assertIn("K", self.painel.material.text())

    def test_a_posicao_ilegal_acende_as_casas(self) -> None:
        self.carregar(LEGAL)
        self.painel._tabuleiro_mudou(board_edit.set_piece(LEGAL, 0, "K"))
        self.assertTrue(self.painel.tabuleiro.casas_marcadas()["problematicas"])
        self.assertNotIn("legal.", self.painel.legalidade.text().lower().replace("ilegal", ""))

    def test_trocar_a_vez_muda_a_legalidade_sem_mexer_em_peca(self) -> None:
        """O "xeque invertido" da S-17: a posição em que o lado a jogar é o problema."""
        self.carregar(LEGAL)
        antes = self.painel.tabuleiro.posicao()
        for botao in self.painel._lados.buttons():
            if botao.property("lado") == "b":
                botao.setChecked(True)
                self.painel._trocou_o_lado()
        self.assertEqual(self.painel.modelo.side_at(0), "b")
        self.assertEqual(self.painel.tabuleiro.posicao(), antes, "trocar a vez mexeu numa peça")

    def test_o_radio_reflete_o_lado_do_modelo(self) -> None:
        self.carregar(LEGAL)
        marcado = [b for b in self.painel._lados.buttons() if b.isChecked()]
        self.assertEqual([str(b.property("lado")) for b in marcado], ["w"])


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class HistoricoTests(PainelTests):
    """Desfazer e refazer, e as duas razões diferentes de estarem cinzas (S-165/S-229)."""

    def test_desfazer_devolve_a_posicao_anterior(self) -> None:
        self.carregar(LEGAL)
        corrigida = board_edit.set_piece(LEGAL, 27, "Q")
        self.painel._tabuleiro_mudou(corrigida)
        self.painel.desfazer()
        self.assertEqual(self.painel.modelo.fen_at(0), LEGAL)

    def test_refazer_repoe_o_que_o_desfazer_tirou(self) -> None:
        self.carregar(LEGAL)
        corrigida = board_edit.set_piece(LEGAL, 27, "Q")
        self.painel._tabuleiro_mudou(corrigida)
        self.painel.desfazer()
        self.painel.refazer()
        self.assertEqual(self.painel.modelo.fen_at(0), corrigida)

    def test_desfazer_com_a_pilha_vazia_diz_por_que(self) -> None:
        self.carregar(LEGAL)
        self.painel.desfazer()
        self.assertIn("mudança anterior", self.recados[-1])

    def test_as_duas_razoes_de_estar_cinza_sao_ditas_diferentes(self) -> None:
        """Sem diagrama não há posição nenhuma; com diagrama e pilha vazia, não há mudança
        anterior **neste** diagrama -- e quem olha precisa saber qual é a sua."""
        sem_diagrama = self.painel.btn_desfazer.toolTip()
        self.carregar(LEGAL)
        pilha_vazia = self.painel.btn_desfazer.toolTip()
        self.assertNotEqual(sem_diagrama, pilha_vazia)
        self.assertIn("diagrama", sem_diagrama)
        self.assertIn("mudança anterior", pilha_vazia)

    def test_limpar_o_tabuleiro_e_desfazivel(self) -> None:
        self.carregar(LEGAL)
        self.painel.limpar_tabuleiro()
        self.assertEqual(self.painel.modelo.fen_at(0), board_edit.EMPTY_PLACEMENT)
        self.painel.desfazer()
        self.assertEqual(self.painel.modelo.fen_at(0), LEGAL)

    def _trocar_o_lado(self, lado: str) -> None:
        for botao in self.painel._lados.buttons():
            if botao.property("lado") == lado:
                botao.setChecked(True)
                self.painel._trocou_o_lado()

    def test_trocar_o_lado_entra_na_pilha_e_desfazer_devolve(self) -> None:
        """OCR_UI C2, A7 (análise §6.5): a troca de vez era a única das sete origens de mudança
        fora do `Ctrl+Z`. Agora o estado da pilha é `(placement, side)`."""
        self.carregar(LEGAL)
        self._trocar_o_lado("b")
        self.assertEqual(self.painel.modelo.side_at(0), "b")
        self.assertTrue(self.painel.btn_desfazer.isEnabled(), "trocar o lado não acendeu o desfazer")
        self.painel.desfazer()
        self.assertEqual(self.painel.modelo.side_at(0), "w", "o desfazer não devolveu o lado")
        self.assertEqual(self.painel.modelo.fen_at(0), LEGAL, "o desfazer mexeu numa peça")
        self.painel.refazer()
        self.assertEqual(self.painel.modelo.side_at(0), "b")

    def test_desfazer_devolve_peca_e_lado_na_ordem_em_que_mudaram(self) -> None:
        self.carregar(LEGAL)
        corrigida = board_edit.set_piece(LEGAL, 27, "Q")
        self.painel._tabuleiro_mudou(corrigida)
        self._trocar_o_lado("b")
        self.painel.desfazer()
        self.assertEqual((self.painel.modelo.fen_at(0), self.painel.modelo.side_at(0)), (corrigida, "w"))
        self.painel.desfazer()
        self.assertEqual((self.painel.modelo.fen_at(0), self.painel.modelo.side_at(0)), (LEGAL, "w"))

    @pytest.mark.xfail(strict=True, reason="o comportamento antigo (A7): desfazer não devolvia o lado")
    def test_sabotagem_desfazer_nao_devolvia_o_lado(self) -> None:
        self.carregar(LEGAL)
        self._trocar_o_lado("b")
        self.painel.desfazer()
        self.assertEqual(self.painel.modelo.side_at(0), "b")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TecladoEBotoesTests(PainelTests):
    """O que o painel declara para si, e de onde vêm os rótulos."""

    def test_o_painel_declara_as_acoes_que_atende(self) -> None:
        """O mecanismo da S-244: `atalhos.destino` consulta a cadeia antes do comando global,
        e é isto que faz `Ctrl+S` gravar quando o foco está aqui."""
        for acao in self.painel.acoes_proprias():
            with self.subTest(acao=acao):
                self.assertIsNotNone(self.painel.atender(acao), f"{acao} é declarada e não atende")

    def test_conferir_dono_aprova_a_declaracao(self) -> None:
        """A trava de `atalhos.conferir_dono`, que é quem cobra a declaração na montagem."""
        atalhos.conferir_dono(self.painel, "o painel de resultado do Qt")

    def test_toda_acao_declarada_esta_na_tabela(self) -> None:
        for acao in self.painel.acoes_proprias():
            with self.subTest(acao=acao):
                self.assertIn(acao, atalhos.por_acao)

    def test_o_rotulo_dos_botoes_vem_do_catalogo(self) -> None:
        """A fronteira da S-324: este painel não escreve texto de interface."""
        for botao, acao in (
            (self.painel.btn_salvar, "salvar"),
            (self.painel.btn_salvar_todos, "salvar_todos"),
            (self.painel.btn_desfazer, "desfazer"),
            (self.painel.btn_refazer, "refazer"),
            (self.painel.btn_limpar, "limpar_tabuleiro"),
            (self.painel.btn_aplicar, "aplicar_fen"),
        ):
            with self.subTest(acao=acao):
                self.assertEqual(botao.text(), comandos.rotulo_de_botao(acao))

    def test_a_barra_de_acoes_quebra_em_vez_de_cortar(self) -> None:
        """Cinco botões numa coluna de 360 px não cabem numa linha, e o `QHBoxLayout` responderia
        com uma largura mínima maior que o painel -- o divisor deixaria de poder ser arrastado."""
        from chess_diagram_ocr.qt.barra import BarraFluida

        barras = self.painel.findChildren(BarraFluida)
        # Duas desde C1/X5: a das ações e a dos estados com ação (que nasce vazia à vista).
        self.assertEqual(len(barras), 2)
        acoes = next(b for b in barras if self.painel.btn_salvar in b.findChildren(type(self.painel.btn_salvar)))
        self.assertGreater(acoes.linhas_em(200), 1)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class SalvarTodosTests(PainelTests):
    """A gravação da página inteira, que conta o que deu certo (S-318)."""

    def setUp(self) -> None:
        super().setUp()
        self.gravados: list[int] = []
        self.painel.salvou.connect(self.gravados.append)
        self.painel._servico.save_sample.return_value = Path("amostra.png")

    def test_salvar_todos_grava_cada_diagrama(self) -> None:
        self.carregar(LEGAL, OUTRA)
        self.painel.salvar_todos()
        self.assertEqual(self.gravados, [0, 1])
        self.assertIn("Salvos 2 de 2", self.recados[-1])

    def test_um_que_falha_nao_para_os_outros(self) -> None:
        """Parar no primeiro erro deixaria metade da página gravada sem dizer quantos."""
        self.carregar(LEGAL, OUTRA)
        self.painel._servico.save_sample.side_effect = [OSError("disco cheio"), Path("b.png")]
        with self.assertLogs("chess_diagram_ocr.qt.painel_de_resultado", level="ERROR"):
            self.painel.salvar_todos()
        self.assertEqual(self.gravados, [1])
        self.assertIn("Salvos 1 de 2", self.recados[-1])

    def test_salvar_todos_sem_diagrama_avisa(self) -> None:
        self.painel.salvar_todos()
        self.assertIn("leia uma página", self.recados[-1])


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PaletaTests(PainelTests):
    """A paleta e o tabuleiro, ligados (S-65).

    O que a paleta faz sozinha é de `tests/test_qt_paleta_de_pecas.py`. O que se afirma aqui é a
    **fiação**: escolher na paleta arma o pincel do tabuleiro, e um clique numa casa deposita a
    peça. Afirmar o efeito e não a chamada é o que a S-522 pede -- trocar o método depois do
    `connect` não troca quem o sinal chama, e um teste com `mock` continuaria verde com o fio
    cortado.
    """

    def test_escolher_na_paleta_arma_o_pincel_do_tabuleiro(self) -> None:
        self.carregar()
        self.painel.paleta._botoes["Q"].click()
        self.assertEqual("Q", self.painel.tabuleiro.modelo.brush)

    def test_largar_na_paleta_desarma_o_pincel_do_tabuleiro(self) -> None:
        """O outro sentido do mesmo fio: sem ele o clique ficaria pintando para sempre."""
        self.carregar()
        self.painel.paleta._botoes["Q"].click()
        self.painel.paleta._botoes["Q"].click()
        self.assertIsNone(self.painel.tabuleiro.modelo.brush)

    def test_a_frase_do_pincel_chega_a_barra_de_status(self) -> None:
        self.carregar()
        self.painel.paleta._botoes["Q"].click()
        self.assertIn(board_edit.PIECE_NAMES_PT["Q"], self.recados[-1])

    def test_a_paleta_fica_ao_lado_do_tabuleiro_e_alinhada_por_cima(self) -> None:
        """A forma pedida: coluna à direita do desenho, e não fileira embaixo dele. Sem o
        alinhamento por cima o layout centraria os catorze botões na altura do tabuleiro."""
        self.painel.resize(400, 880)
        # Mostrar é o que faz o Qt calcular a geometria dos filhos: `activate()` na camada de
        # cima não desce até o layout do grupo, e as duas posições sairiam zeradas. Sob
        # `offscreen` nada aparece na tela, e o `hide` devolve o painel ao estado em que estava.
        self.painel.show()
        self.addCleanup(self.painel.hide)
        self.app.processEvents()
        tabuleiro, paleta = self.painel.tabuleiro, self.painel.paleta
        self.assertGreaterEqual(paleta.x(), tabuleiro.x() + tabuleiro.width())
        self.assertEqual(paleta.y(), tabuleiro.y())

    def test_sem_diagrama_a_paleta_fica_cinza(self) -> None:
        """O painel vazio desenha um tabuleiro sem peças, e pintar nele produziria a tela que a
        S-170 escolheu não deixar acontecer: um diagrama na cara de quem não abriu nenhum."""
        self.assertFalse(self.painel.paleta._botoes["Q"].isEnabled())
        self.assertEqual(MOTIVO_SEM_DIAGRAMA, self.painel.paleta._botoes["Q"].toolTip())
        self.carregar()
        self.assertTrue(self.painel.paleta._botoes["Q"].isEnabled())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class RecorteTests(PainelTests):
    """O recorte ao lado do tabuleiro e a sincronia entre os dois (OCR_UI passo 13, U1).

    O que o recorte faz sozinho é de `tests/test_qt_painel_de_recorte.py`; a regra é de
    `tests/test_ui_recorte_do_diagrama.py`. Aqui é a **fiação**: o clique no recorte chega ao
    tabuleiro como gesto inteiro, o ponteiro e a seleção se espelham, a tinta é a mesma nos dois, e
    o fio que o portão `percurso --sabotar sem_sincronia` corta corta de fato.
    """

    def test_o_recorte_mostra_o_diagrama_e_some_com_ele(self) -> None:
        self.assertFalse(self.painel.recorte.tem_recorte())
        self.carregar()
        self.assertTrue(self.painel.recorte.tem_recorte())
        self.painel.limpar()
        self.assertFalse(self.painel.recorte.tem_recorte())

    def test_o_clique_no_recorte_seleciona_a_casa_no_tabuleiro(self) -> None:
        self.carregar()
        self.painel.recorte.casa_clicada.emit(60)  # e1, o rei branco
        self.assertEqual(self.painel.tabuleiro.selecionada(), 60)
        self.assertEqual(self.painel.recorte.selecionada(), 60, "e a seleção volta espelhada")

    def test_o_clique_no_recorte_com_pincel_pinta(self) -> None:
        """O gesto inteiro, e não só a seleção: com a peça na mão, a casa do recorte recebe a peça
        -- é o que faz o recorte valer um clique, e o que o portão do passo 13 conta."""
        self.carregar()
        self.painel.paleta._botoes["Q"].click()
        self.painel.recorte.casa_clicada.emit(27)
        self.assertEqual(board_edit.piece_at(self.painel.modelo.fen_at(0), 27), "Q")

    def test_sem_sincronia_o_clique_no_recorte_nao_chega_ao_tabuleiro(self) -> None:
        """A sabotagem do portão, e a prova de que ela corta o que diz cortar."""
        self.carregar()
        self.painel.ligar_recorte(False)
        self.painel.recorte.casa_clicada.emit(60)
        self.assertIsNone(self.painel.tabuleiro.selecionada())
        self.painel.ligar_recorte(True)
        self.painel.recorte.casa_clicada.emit(60)
        self.assertEqual(self.painel.tabuleiro.selecionada(), 60)

    def test_o_ponteiro_se_espelha_nos_dois_sentidos(self) -> None:
        self.carregar()
        self.painel.tabuleiro.casa_apontada.emit(9)
        self.assertEqual(self.painel.recorte.apontada(), 9)
        self.painel.recorte.casa_apontada.emit(18)
        self.assertEqual(self.painel.tabuleiro.apontada(), 18)
        self.painel.recorte.casa_apontada.emit(None)
        self.assertIsNone(self.painel.tabuleiro.apontada())

    def test_a_tinta_por_margem_vai_ao_tabuleiro_e_ao_recorte(self) -> None:
        """Uma casa em que o modelo hesitou (0,60 × 0,35) fica âmbar nos dois; uma casa apenas
        pouco confiante pela régua antiga não entra -- a tinta é por margem quando há matriz."""
        itens = [diagrama(LEGAL, probs=probs_que_hesitam_em(12))]
        self.painel.carregar_pagina(itens, chave="livro.pdf", pagina=0)
        self.assertEqual(self.painel.tabuleiro.casas_incertas(), (12,))
        self.assertEqual(self.painel.recorte.casas_marcadas()["hesitacao"], (12,))
        self.assertTrue(self.painel.tabuleiro.dica_da_casa(12).startswith("e7 · dama branca 0,600"))

    def test_sem_matriz_vale_a_regua_antiga(self) -> None:
        item = diagrama(LEGAL)
        item.uncertain_squares = [5]
        self.painel.carregar_pagina([item], chave="livro.pdf", pagina=0)
        self.assertEqual(self.painel.tabuleiro.casas_incertas(), (5,))

    def test_a_caixa_esconder_incerteza_nasce_desmarcada_e_e_o_inverso_do_estado(self) -> None:
        self.assertFalse(self.painel.heatmap.isChecked())
        self.assertTrue(self.painel.mostrar_incerteza)
        self.assertTrue(self.painel.tabuleiro._heatmap)
        self.painel.mostrar_incerteza = False
        self.assertTrue(self.painel.heatmap.isChecked())
        self.assertFalse(self.painel.tabuleiro._heatmap)

    def test_o_painel_avisa_que_mudou_a_cada_edicao(self) -> None:
        """É o sinal que a janela usa para recarimbar a caixa da página como «corrigido»."""
        mudou: list[int] = []
        self.painel.mudou.connect(lambda: mudou.append(1))
        self.carregar()
        antes = len(mudou)
        self.painel.paleta._botoes["Q"].click()
        self.painel.recorte.casa_clicada.emit(27)
        self.assertGreater(len(mudou), antes)
        self.assertEqual(self.painel.modelo.hand_edited_indices(), frozenset({0}))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


def diagrama_com_estados(**campos: object) -> RecognizedDiagram:
    """Um diagrama lido com os sinais que o serviço calcula e a tela não dizia (C1/X5)."""
    item = diagrama(LEGAL)
    for nome, valor in campos.items():
        setattr(item, nome, valor)
    return item


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class EstadosComAcaoTests(PainelTests):
    """Os três estados com ação (OCR_UI C2, C1/X5; análise §7.5).

    O serviço já calculava `changed_squares`, `orientation_ambiguous` e `side_conflicting`; a tela
    mostrava só o rótulo do terceiro, sem nada a fazer. Cada um vira um botão que só existe com o
    diagrama que o tem -- e a sabotagem, no fim, é o diagrama sem os campos: a tela volta ao
    genérico e o teste que espera os botões reprova.
    """

    def _abrir(self, item: RecognizedDiagram) -> None:
        self.painel.carregar_pagina([item], chave="livro.pdf", pagina=0)

    def test_sem_os_sinais_nenhum_botao_de_estado_aparece(self) -> None:
        self._abrir(diagrama(LEGAL))
        for botao in (self.painel.btn_reparadas, self.painel.btn_orientacao, self.painel.btn_lado):
            with self.subTest(botao=botao.text()):
                self.assertFalse(botao.isVisibleTo(self.painel))

    def test_reparado_em_n_casas_aparece_com_as_casas_e_o_botao_as_pinta(self) -> None:
        self._abrir(diagrama_com_estados(changed_squares=[27, 36]))
        self.assertTrue(self.painel.btn_reparadas.isVisibleTo(self.painel))
        # Os índices são em ordem de leitura (a8 = 0), como `square_name` os lê: 27 = d5, 36 = e4.
        self.assertIn("Reparado em 2 casas: d5, e4", self.painel.detalhes.text())
        self.assertEqual(self.painel.btn_reparadas.text(), strings.REPARADAS_MOSTRAR)
        self.assertNotIn(27, self.painel.tabuleiro.casas_marcadas()["corrigidas"])
        self.painel.btn_reparadas.click()
        marcadas = self.painel.tabuleiro.casas_marcadas()
        self.assertEqual(marcadas["corrigidas"], (27, 36), "as casas reparadas não foram pintadas")
        self.assertEqual(marcadas["selecionada"], (27,), "a primeira reparada não foi selecionada")
        self.assertEqual(self.painel.btn_reparadas.text(), strings.REPARADAS_ESCONDER)
        self.painel.btn_reparadas.click()
        self.assertEqual(self.painel.tabuleiro.casas_marcadas()["corrigidas"], ())

    def test_a_pintura_das_reparadas_nao_confunde_a_correcao_humana(self) -> None:
        self._abrir(diagrama_com_estados(changed_squares=[27]))
        self.painel.btn_reparadas.click()
        self.painel._tabuleiro_mudou(board_edit.set_piece(LEGAL, 0, "Q"))
        self.assertEqual(self.painel.tabuleiro.casas_marcadas()["corrigidas"], (0, 27))
        self.painel.desfazer()
        self.assertEqual(self.painel.tabuleiro.casas_marcadas()["corrigidas"], (27,))

    def test_orientacao_ambigua_aparece_com_o_motivo_e_compara_as_duas(self) -> None:
        self._abrir(diagrama_com_estados(orientation_ambiguous=True, orientation_reason="margem 0,02"))
        self.assertTrue(self.painel.btn_orientacao.isVisibleTo(self.painel))
        self.assertIn("Orientação ambígua: margem 0,02", self.painel.detalhes.text())
        self.assertEqual(self.painel.btn_orientacao.text(), strings.ORIENTACAO_COMPARAR)
        self.painel.btn_orientacao.click()
        self.assertEqual(self.painel.modelo.fen_at(0), _girar_180(LEGAL))
        self.assertEqual(self.painel.btn_orientacao.text(), strings.ORIENTACAO_VOLTAR)
        self.painel.btn_orientacao.click()
        self.assertEqual(self.painel.modelo.fen_at(0), LEGAL, "girar duas vezes não devolveu a original")
        self.painel.btn_orientacao.click()
        self.painel.desfazer()
        self.assertEqual(self.painel.modelo.fen_at(0), LEGAL, "a comparação não é desfazível")

    def test_girar_180_e_a_ordem_inversa_das_casas(self) -> None:
        self.assertEqual(_girar_180("K7/8/8/8/8/8/8/7k"), "k7/8/8/8/8/8/8/7K", "a8 vai parar em h1")
        self.assertEqual(_girar_180("8/8/8/3K4/8/8/8/8"), "8/8/8/8/4K3/8/8/8", "d5 vai parar em e4")
        self.assertEqual(_girar_180("ruim"), "ruim", "colocação malformada volta como veio")

    def test_o_conflito_de_lado_ganha_a_acao_de_trocar(self) -> None:
        item = diagrama_com_estados(side_conflicting=True, side_to_move_reason="a legenda diz «pretas jogam»")
        self._abrir(item)
        self.assertIn(strings.SIDE_SOURCE_CONFLICT, self.painel.detalhes.text(), "o rótulo que já existia")
        self.assertTrue(self.painel.btn_lado.isVisibleTo(self.painel))
        self.assertEqual(self.painel.btn_lado.text(), strings.trocar_o_lado_para("b"))
        self.assertIn("legenda diz", self.painel.btn_lado.toolTip())
        self.painel.btn_lado.click()
        self.assertEqual(self.painel.modelo.side_at(0), "b")
        self.assertFalse(item.side_conflicting, "decidido por um humano, não há mais duas fontes")
        self.assertFalse(self.painel.btn_lado.isVisibleTo(self.painel), "o conflito resolvido some")
        self.painel.desfazer()
        self.assertEqual(self.painel.modelo.side_at(0), "w")

    def test_os_estados_somem_com_o_diagrama(self) -> None:
        self._abrir(diagrama_com_estados(changed_squares=[1], orientation_ambiguous=True, side_conflicting=True))
        self.painel.limpar()
        for botao in (self.painel.btn_reparadas, self.painel.btn_orientacao, self.painel.btn_lado):
            self.assertFalse(botao.isVisibleTo(self.painel))

    @pytest.mark.xfail(strict=True, reason="sabotagem (C1/X5): sem os campos a tela volta ao genérico")
    def test_sabotagem_sem_os_campos_os_estados_nao_aparecem(self) -> None:
        self._abrir(diagrama(LEGAL))
        self.assertTrue(self.painel.btn_reparadas.isVisibleTo(self.painel))
        self.assertTrue(self.painel.btn_orientacao.isVisibleTo(self.painel))
        self.assertTrue(self.painel.btn_lado.isVisibleTo(self.painel))


class _DecisaoFalsa:
    """O `DiagramDecision` da suíte, como o contrato §1.1 o descreve."""

    def __init__(self, **campos: object) -> None:
        self.campos = campos


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DecisaoDeDiagramaTests(PainelTests):
    """A correção gravada chega ao livro (OCR_UI C2, A3; análise §6.2).

    `_gravar_alvo` com sucesso chama `caissa.ocr.diagram_decisions.record` com o retângulo em
    **pontos** e a FEN inteira. O módulo da suíte é resolvido por chamada em
    `qt/decisoes_de_diagrama._contrato`, e é ele que o teste troca por um falso.
    """

    def setUp(self) -> None:
        super().setUp()
        self.gravadas: list[tuple[Path, _DecisaoFalsa]] = []

        def record(pdf: Path, decisao: _DecisaoFalsa) -> Path:
            self.gravadas.append((pdf, decisao))
            return Path("labeling/diagramas/livro.json")

        self.contrato = mock.patch.object(
            decisoes_de_diagrama, "_contrato", return_value=(_DecisaoFalsa, record)
        )
        self.contrato.start()
        self.addCleanup(self.contrato.stop)
        self.painel._servico.save_sample.return_value = "amostra.png"

    def test_gravar_a_amostra_registra_a_decisao_em_pontos(self) -> None:
        item = diagrama(LEGAL)
        item.bbox_pdf = (72.0, 100.0, 272.0, 300.0)
        self.painel.carregar_pagina([item], chave="C:/livros/livro.pdf", pagina=16)
        self.painel._tabuleiro_mudou(board_edit.set_piece(LEGAL, 27, "Q"))
        self.painel.salvar_atual()
        self.assertEqual(len(self.gravadas), 1, "a decisão não foi registrada")
        pdf, decisao = self.gravadas[0]
        self.assertEqual(pdf, Path("C:/livros/livro.pdf"))
        self.assertEqual(decisao.campos["page_index"], 16)
        self.assertEqual(decisao.campos["rect"], (72.0, 100.0, 272.0, 300.0))
        self.assertTrue(str(decisao.campos["fen"]).startswith(board_edit.set_piece(LEGAL, 27, "Q") + " w "))
        self.assertEqual(decisao.campos["side"], "w")
        self.assertEqual(decisao.campos["source"], "janela")
        self.assertRegex(str(decisao.campos["decided_at"]), r"^\d{4}-\d{2}-\d{2}T")

    def test_o_lado_gravado_e_o_da_decisao(self) -> None:
        item = diagrama(LEGAL)
        item.bbox_pdf = (0.0, 0.0, 10.0, 10.0)
        self.painel.carregar_pagina([item], chave="livro.pdf", pagina=0)
        for botao in self.painel._lados.buttons():
            if botao.property("lado") == "b":
                botao.setChecked(True)
                self.painel._trocou_o_lado()
        self.painel.salvar_atual()
        self.assertEqual(self.gravadas[0][1].campos["side"], "b")
        self.assertIn(" b ", str(self.gravadas[0][1].campos["fen"]))

    def test_sem_retangulo_na_pagina_nao_ha_decisao(self) -> None:
        """Item da fila, amostra do dataset, recorte: sem `bbox_pdf` nem `quad` não há com que a
        importação casar a decisão, e registrá-la seria inventar um lugar."""
        self.painel.carregar_pagina([diagrama(LEGAL)], chave="livro.pdf", pagina=0)
        self.painel.salvar_atual()
        self.assertEqual(self.gravadas, [])

    def test_sem_procedencia_de_pagina_nao_ha_decisao(self) -> None:
        item = diagrama(LEGAL)
        item.bbox_pdf = (0.0, 0.0, 10.0, 10.0)
        self.painel.carregar_avulsos([item])
        self.painel.salvar_atual()
        self.assertEqual(self.gravadas, [])

    def test_a_gravacao_que_falha_nao_registra_decisao(self) -> None:
        item = diagrama(LEGAL)
        item.bbox_pdf = (0.0, 0.0, 10.0, 10.0)
        self.painel.carregar_pagina([item], chave="livro.pdf", pagina=0)
        self.painel._servico.save_sample.side_effect = OSError("disco cheio")
        with mock.patch("chess_diagram_ocr.qt.painel_de_resultado.QMessageBox.critical"):
            self.painel.salvar_atual()
        self.assertEqual(self.gravadas, [], "decisão registrada sobre uma amostra que não entrou")

    def test_sem_a_suite_a_amostra_grava_e_a_decisao_fica_no_log(self) -> None:
        self.contrato.stop()
        with mock.patch.dict("sys.modules", {"caissa": None, "caissa.ocr": None, "caissa.ocr.diagram_decisions": None}):
            item = diagrama(LEGAL)
            item.bbox_pdf = (0.0, 0.0, 10.0, 10.0)
            self.painel.carregar_pagina([item], chave="livro.pdf", pagina=0)
            with self.assertLogs("chess_diagram_ocr.qt.decisoes_de_diagrama", level="INFO") as capturado:
                self.painel.salvar_atual()
        self.contrato.start()
        self.assertTrue(self.painel._servico.save_sample.called, "a amostra deixou de ser gravada")
        self.assertIn("suíte", "\n".join(capturado.output))

    def test_o_quad_em_pixels_vira_pontos_pelo_dpi_do_render(self) -> None:
        item = mock.Mock(bbox_pdf=None, quad=[[220.0, 440.0], [660.0, 440.0], [660.0, 880.0], [220.0, 880.0]])
        self.assertEqual(decisoes_de_diagrama.retangulo_em_pontos(item, 220), (72.0, 144.0, 216.0, 288.0))
        self.assertEqual(decisoes_de_diagrama.retangulo_em_pontos(mock.Mock(bbox_pdf=None, quad=None), 220), None)

    @pytest.mark.xfail(strict=True, reason="sabotagem (A3): gravar sem registrar a decisão")
    def test_sabotagem_gravar_sem_o_gancho_nao_registra(self) -> None:
        item = diagrama(LEGAL)
        item.bbox_pdf = (0.0, 0.0, 10.0, 10.0)
        self.painel.carregar_pagina([item], chave="livro.pdf", pagina=0)
        with mock.patch.object(self.painel, "_registrar_decisao"):
            self.painel.salvar_atual()
        self.assertEqual(len(self.gravadas), 1)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PontoDeVistaDasPretasTests(PainelTests):
    """OCR_UI ciclo 2, passo C10: impresso do ponto de vista das pretas, o tabuleiro **e o
    recorte** viram juntos -- a posição continua canônica, só a vista gira.

    A casa canônica `i` está impressa em `63 - i`, como na leitura de cabeça para baixo; com o
    recorte virando só pela rotação, a tinta e o clique no recorte caíam na casa espelhada.
    """

    def test_o_tabuleiro_e_o_recorte_viram_juntos_e_a_posicao_fica_canonica(self) -> None:
        item = diagrama(LEGAL, probs=probs_que_hesitam_em(12))   # e7, na ordem de leitura
        item.black_point_of_view = True
        item.rotation = 0
        self.painel.carregar_pagina([item], chave="livro.pdf", pagina=0)
        self.assertTrue(self.painel.tabuleiro.virado, "tabuleiro na vista do impresso")
        self.assertTrue(self.painel.recorte._virado, "recorte na mesma vista")
        self.assertEqual(self.painel.tabuleiro.posicao(), LEGAL, "a posição continua canônica")
        # A tinta é canônica nos dois; é o `virado` que a leva à casa impressa.
        from chess_diagram_ocr.ui import recorte_do_diagrama as regra

        x0, y0, _x1, _y1 = regra.retangulo_da_casa(12, 80.0, 80.0, virado=True)
        self.assertEqual((x0, y0), (30.0, 60.0), "e7 canônica está impressa onde d2 estaria")
        self.assertIn(12, self.painel.tabuleiro._incertas, "a dúvida fica na casa canônica")

    def test_de_pe_e_das_brancas_nada_vira(self) -> None:
        item = diagrama(LEGAL)
        item.black_point_of_view = False
        self.painel.carregar_pagina([item], chave="livro.pdf", pagina=0)
        self.assertFalse(self.painel.tabuleiro.virado)
        self.assertFalse(self.painel.recorte._virado)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class SegundaOpiniaoTests(PainelTests):
    """OCR_UI ciclo 2, passo C3: a segunda opinião volta à janela, com ação."""

    class _Leitor:
        name = "leitor de outra família"

        def __init__(self, placement: str) -> None:
            self.placement = placement
            self.lidos = 0

        def predict(self, image_rgb) -> str:
            self.lidos += 1
            return self.placement

    def _esperar(self, condicao, ate_ms: int = 4000) -> None:
        from PyQt6.QtTest import QTest

        for _ in range(ate_ms // 10):
            QTest.qWait(10)
            if condicao():
                return

    def test_as_casas_em_disputa_ficam_marcadas_e_a_posicao_e_adotada(self) -> None:
        self.carregar(LEGAL)
        leitor = self._Leitor(OUTRA)   # discorda em e8/e5: o rei preto mudou de casa
        with mock.patch.object(self.painel, "leitor_da_segunda_opiniao", return_value=leitor):
            self.painel.segunda_opiniao()
            self._esperar(lambda: self.painel._segunda_em_curso is None)
        self.assertEqual(leitor.lidos, 1)
        disputadas = self.painel.tabuleiro.casas_marcadas()["disputadas"]
        self.assertEqual(disputadas, (4, 28))   # e8 e e5 na ordem de leitura
        self.assertEqual(self.painel.modelo.fen_at(0), OUTRA, "a leitura do segundo é adotada")
        self.assertIn("discorda em 2 casa(s)", self.recados[-1])
        # A procedência da amostra diz de onde a posição veio.
        self.assertEqual(self.painel.modelo.label_route(0, OUTRA), "segunda-opiniao")
        # Ctrl+Z devolve a leitura do primeiro.
        self.painel.desfazer()
        self.assertEqual(self.painel.modelo.fen_at(0), LEGAL)

    def test_sem_leitor_configurado_o_botao_some_e_o_comando_diz_por_que(self) -> None:
        self.carregar(LEGAL)
        with mock.patch.object(self.painel, "_segunda_opiniao_configurada", return_value=False):
            self.painel._atualizar_tudo()
            self.assertFalse(self.painel.btn_segunda.isVisible())
        with mock.patch.object(self.painel, "leitor_da_segunda_opiniao", return_value=None):
            self.painel.segunda_opiniao()
        self.assertTrue(self.recados and "Segunda opinião" in self.recados[-1], self.recados)

    def test_a_copia_do_primeiro_nao_marca_nada(self) -> None:
        """O que o portão `second_opinion_gate --sabotar copia` mede, visto da janela."""
        self.carregar(LEGAL)
        with mock.patch.object(self.painel, "leitor_da_segunda_opiniao", return_value=self._Leitor(LEGAL)):
            self.painel.segunda_opiniao()
            self._esperar(lambda: self.painel._segunda_em_curso is None)
        self.assertEqual(self.painel.tabuleiro.casas_marcadas()["disputadas"], ())
        self.assertIn("64 casas batem", self.recados[-1])
