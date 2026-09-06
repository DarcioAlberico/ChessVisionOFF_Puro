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
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.service import RecognizedDiagram
from chess_diagram_ocr.ui import atalhos, barra_do_resultado, board_edit, comandos

if TEM_PYQT:
    from chess_diagram_ocr.qt.painel_de_resultado import MENSAGEM_VAZIA, PainelDeResultado

LEGAL = "4k3/8/8/8/8/8/8/4K3"
OUTRA = "8/8/8/4k3/8/8/8/4K3"


def diagrama(placement: str = LEGAL, *, indice: int = 0) -> RecognizedDiagram:
    return RecognizedDiagram(
        index=indice,
        board_rgb=np.full((64, 64, 3), 200, np.uint8),
        placement=placement,
        min_confidence=0.93,
        square_confidences=[0.99] * 64,
        side_to_move="w",
    )


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

    def test_a_fen_reescrita_pelo_tabuleiro_mostra_o_comeco(self) -> None:
        """A mesma guarda da sala (S-552, quinta rodada): `setText` põe o cursor no fim e o campo
        estreito rola até lá, mostrando o meio da FEN como se fosse a posição inteira.

        **O painel é mostrado, e sem isso a guarda é vácua**: um `QLineEdit` que nunca foi criado
        não rola, então `cursorPositionAt` responde 0 com o defeito de pé. É a mesma armadilha de
        `tests/qt_app.py` -- medir o silêncio do Qt em vez do comportamento.
        """
        from PyQt6.QtCore import QPoint, Qt

        self.painel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.painel.resize(600, 500)
        self.painel.show()
        self.app.processEvents()
        self.carregar(LEGAL)
        self.painel.campo_fen.setFixedWidth(90)
        self.app.processEvents()
        self.painel._tabuleiro_mudou(board_edit.set_piece(LEGAL, 27, "Q"))
        self.app.processEvents()
        # **O desenho é onde o `QLineEdit` resolve o deslocamento horizontal.** Sem pintar, o
        # `hscroll` dele fica em zero e a guarda passa com o defeito de pé -- de novo o silêncio
        # do Qt no lugar do comportamento.
        self.painel.campo_fen.grab()
        meio = self.painel.campo_fen.height() // 2
        self.assertEqual(
            0,
            self.painel.campo_fen.cursorPositionAt(QPoint(1, meio)),
            "o campo rolou para a direita e o começo da FEN saiu da tela",
        )

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
        """A fronteira da S-324: este painel não escreve texto de interface.

        **Dois rótulos por ação desde a fila** (S-528, terceira barra): o botão com texto mostra o
        curto (`Salvar`) e o item do "Mais" mostra o longo (`Salvar a posição`), que é o do menu.
        Quem escolhe é `com_texto` na tabela, e é essa escolha que se afirma aqui -- os dois textos
        continuam vindo do catálogo, e nenhum deles é escrito neste painel.
        """
        for nome in ("salvar", "salvar_todos", "desfazer", "refazer", "limpar_tabuleiro", "aplicar_fen"):
            registro = barra_do_resultado.acao(nome)
            esperado = comandos.rotulo_de_botao(nome) if registro.com_texto else comandos.rotulo(nome)
            with self.subTest(acao=nome):
                self.assertEqual(esperado, self.painel.barra.acoes[nome].text())

    def test_a_S_233_fecha_e_os_tres_rotulos_curtos_existem(self) -> None:
        """`ui/comandos.py` registrava que "Aplicar FEN", "Salvar posição reconhecida" e "Salvar
        todos" eram comandos da janela cujos rótulos o painel escrevia **à mão** -- e por isso os
        três não declaravam `rotulo_curto`, "que seria uma promessa que ninguém cumpre". Com a fila
        quem os escreve é o catálogo, e a promessa passou a ter quem a cumpra."""
        for nome in ("salvar", "salvar_todos", "aplicar_fen"):
            with self.subTest(acao=nome):
                curto = comandos.rotulo_de_botao(nome)
                self.assertTrue(curto)
                self.assertNotEqual(comandos.rotulo(nome), curto, "o rótulo curto não encurtou nada")

    def test_a_fila_enfileira_em_vez_de_quebrar(self) -> None:
        """**É o que mudou.** A `BarraFluida` da S-151 resolvia "esconder botão sem avisar"
        empilhando fileiras: cinco botões de texto numa coluna de 360 px viravam três linhas, e a
        aba que abre primeiro gastava isso em cromo. A fila resolve o mesmo sem gastar altura --
        continua sendo **uma** linha em qualquer largura, e o que não cabe está no "Mais".

        A propriedade afirmada é a da S-151, e ela não mudou: **nenhuma ação é descartada**.
        """
        for largura in (1200, 700, 494, 300, 160):
            self.painel.barra.resize(largura, self.painel.barra.height())
            self.app.processEvents()
            with self.subTest(largura=largura):
                self.assertEqual(1, self.painel.barra.linhas)
                declaradas = {registro.acao for registro in barra_do_resultado.ACOES}
                mostradas = set(self.painel.barra.na_fila()) | set(self.painel.barra.no_mais())
                self.assertEqual(declaradas, mostradas, "uma ação sumiu da fila e do menu")

    def test_o_mapa_de_incerteza_e_um_item_marcavel_do_mais(self) -> None:
        """Preferência e não gesto: liga-se uma vez e esquece-se, e eram ~180 px permanentes de
        `QCheckBox` com texto numa coluna de 494. É a régua de "marcar diagramas" no livro."""
        self.assertIn(barra_do_resultado.MAPA_DE_INCERTEZA, self.painel.barra.no_mais())
        self.assertTrue(self.painel.heatmap.isCheckable())
        self.assertTrue(self.painel.heatmap.isChecked(), "a tinta de dúvida nasce ligada")
        self.painel.heatmap.setChecked(False)
        self.app.processEvents()
        self.assertFalse(self.painel.tabuleiro._heatmap, "a tinta continuou ligada no tabuleiro")

    def test_o_seletor_diz_de_quantos_e_anda_com_as_setas(self) -> None:
        """Era um `QLabel` "Selecionado" e um campo sem total: para saber quantos diagramas a
        página tinha era preciso contar a lista acima."""
        self.carregar(LEGAL, OUTRA)
        self.assertEqual(barra_do_resultado.sufixo_de_diagramas(2), self.painel.seletor.suffix())
        self.assertIn(self.painel.seletor, self.painel.barra.findChildren(type(self.painel.seletor)))


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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
