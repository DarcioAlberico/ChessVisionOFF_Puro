"""A mesa de texto: o PDF à esquerda e o editor à direita, na própria janela (S-640/S-645).

O pedido foi "quando clicar no botão Texto, uma janela com o PDF à esquerda e o editor à direita".
A janela já tinha os dois, na ordem contrária e com a aba espremida na coluna estreita. Estes testes
cobram a troca de lados ao entrar no Texto, a volta ao sair, o interruptor do menu, o limiar de
largura decidido só ao entrar, que a página e o zoom do visualizador sobrevivem, e que cada
disposição lembra a sua alça.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT

from chess_diagram_ocr.ui import abas, mesa
from chess_diagram_ocr.ui.state import AppState, load_state, save_state

if TEM_PYQT:
    from test_qt_janela import _JanelaComLivro

    from chess_diagram_ocr.qt.janela import JanelaPrincipal
else:  # pragma: no cover - sem o PyQt6 as classes pulam, mas precisam de uma base para existir
    _JanelaComLivro = unittest.TestCase


class DecisaoTests(unittest.TestCase):
    def test_com_o_texto_a_frente_a_mesa_vale(self) -> None:
        self.assertTrue(mesa.vale_a_mesa("", texto_a_frente=True, largura=1400))
        self.assertFalse(mesa.vale_a_mesa("", texto_a_frente=False, largura=1400))

    def test_sempre_vale_fora_do_texto(self) -> None:
        self.assertTrue(mesa.vale_a_mesa(mesa.MESA_SEMPRE, texto_a_frente=False, largura=1400))
        self.assertFalse(mesa.vale_a_mesa(mesa.MESA_SEMPRE, texto_a_frente=False, largura=mesa.LARGURA_MINIMA - 1))
        self.assertTrue(mesa.ligada(mesa.MESA_SEMPRE) and mesa.sempre(mesa.MESA_SEMPRE))
        self.assertFalse(mesa.sempre(""))

    def test_desligada_nunca_vale(self) -> None:
        self.assertFalse(mesa.vale_a_mesa(mesa.MESA_NUNCA, texto_a_frente=True, largura=1400))

    def test_abaixo_da_largura_minima_nao_vale(self) -> None:
        self.assertFalse(mesa.vale_a_mesa("", texto_a_frente=True, largura=mesa.LARGURA_MINIMA - 1))
        self.assertTrue(mesa.vale_a_mesa("", texto_a_frente=True, largura=mesa.LARGURA_MINIMA))

    def test_preferencia_desconhecida_vale_como_o_padrao(self) -> None:
        self.assertTrue(mesa.ligada("de outra versão"))
        self.assertTrue(mesa.ligada(""), "nunca escolhida é ligada")
        self.assertFalse(mesa.ligada(mesa.MESA_NUNCA))

    def test_a_fracao_guardada_ou_a_de_fabrica(self) -> None:
        self.assertEqual(mesa.fracao_da_mesa(0.0), mesa.FRACAO_PADRAO)
        self.assertEqual(mesa.fracao_da_mesa(1.0), mesa.FRACAO_PADRAO)
        self.assertEqual(mesa.fracao_da_mesa(0.3), 0.3)


class EstadoTests(unittest.TestCase):
    def test_os_diagramas_e_a_miniatura_vao_e_voltam_do_arquivo(self) -> None:
        from ambiente_de_teste import pasta_temporaria

        caminho = pasta_temporaria(self) / "estado.json"
        save_state(caminho, AppState(texto_diagramas="esquerda", texto_miniatura="grande"))
        lido = load_state(caminho)
        self.assertEqual((lido.texto_diagramas, lido.texto_miniatura), ("esquerda", "grande"))

    def test_a_preferencia_e_a_alca_vao_e_voltam_do_arquivo(self) -> None:
        from ambiente_de_teste import pasta_temporaria

        caminho = pasta_temporaria(self) / "estado.json"
        save_state(caminho, AppState(texto_mesa=mesa.MESA_NUNCA, mesa_fraction=0.4))
        lido = load_state(caminho)
        self.assertEqual((lido.texto_mesa, lido.mesa_fraction), (mesa.MESA_NUNCA, 0.4))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DisposicaoTests(_JanelaComLivro):
    def montar(self, preferencia: str = "", *, largura: int = 1400) -> JanelaPrincipal:
        janela = self.janela()
        janela._estado.texto_mesa = preferencia
        janela.resize(largura, 900)
        janela.show()
        self.app.processEvents()
        return janela

    def ir_para(self, janela: JanelaPrincipal, area: str) -> None:
        janela.abas.mostrar_area(area)
        self.app.processEvents()

    def fracao_da_esquerda(self, janela: JanelaPrincipal) -> float:
        tamanhos = janela.divisor.sizes()
        return tamanhos[0] / sum(tamanhos)

    def test_entrar_no_texto_poe_o_pdf_a_esquerda(self) -> None:
        janela = self.montar()
        self.ir_para(janela, abas.TEXTO)
        self.assertTrue(janela.mesa.armada)
        self.assertIs(janela.divisor.widget(0), janela.lado_do_livro)
        self.assertIs(janela.divisor.widget(1), janela.abas)
        # A fração de fábrica, ou o mínimo do visualizador quando ela não cabe: o divisor respeita
        # o piso de cada lado, e a 1400 px os 45% ficam abaixo do do lado do livro.
        total = sum(janela.divisor.sizes())
        piso = janela.lado_do_livro.minimumSizeHint().width()
        esperado = max(total * mesa.FRACAO_PADRAO, piso)
        self.assertLessEqual(abs(janela.divisor.sizes()[0] - esperado), 20)

    def test_sair_do_texto_devolve_a_disposicao_e_a_alca(self) -> None:
        janela = self.montar()
        antes = self.fracao_da_esquerda(janela)
        self.ir_para(janela, abas.TEXTO)
        self.ir_para(janela, abas.RESULTADO)
        self.assertFalse(janela.mesa.armada)
        self.assertIs(janela.divisor.widget(0), janela.abas)
        self.assertAlmostEqual(self.fracao_da_esquerda(janela), antes, delta=0.02)

    def test_a_pagina_e_o_zoom_do_visualizador_sobrevivem(self) -> None:
        janela = self.montar()
        janela.pdf.ir_para_pagina(2)
        janela.pdf.aplicar_zoom(1.5)
        self.app.processEvents()
        pagina, zoom = janela.pdf.page_index, janela.pdf.zoom
        self.ir_para(janela, abas.TEXTO)
        self.assertEqual((janela.pdf.page_index, janela.pdf.zoom), (pagina, zoom))
        self.ir_para(janela, abas.RESULTADO)
        self.assertEqual((janela.pdf.page_index, janela.pdf.zoom), (pagina, zoom))

    def test_desligada_deixa_como_era(self) -> None:
        janela = self.montar(mesa.MESA_NUNCA)
        self.ir_para(janela, abas.TEXTO)
        self.assertFalse(janela.mesa.armada)
        self.assertIs(janela.divisor.widget(0), janela.abas)

    def test_mesa_sempre_arma_em_qualquer_area_e_marca_os_dois_interruptores(self) -> None:
        janela = self.montar()
        self.ir_para(janela, abas.RESULTADO)
        self.assertFalse(janela.mesa.armada)
        janela._comandos()["mesa_sempre"]()
        self.assertTrue(janela.mesa.armada, "a mesa sempre não armou fora do Texto")
        self.assertEqual(janela._estado.texto_mesa, mesa.MESA_SEMPRE)
        self.assertTrue(janela.menu.acoes["mesa_sempre"].isChecked())
        self.assertTrue(janela.menu.acoes["mesa_de_texto"].isChecked())
        janela._comandos()["mesa_de_texto"]()  # desligar a mesa desliga as duas posições
        self.assertFalse(janela.mesa.armada)
        self.assertFalse(janela.menu.acoes["mesa_sempre"].isChecked())
        self.assertFalse(janela.menu.acoes["mesa_de_texto"].isChecked())

    def test_o_interruptor_do_menu_desarma_e_rearma(self) -> None:
        janela = self.montar()
        self.ir_para(janela, abas.TEXTO)
        janela._comandos()["mesa_de_texto"]()
        self.assertFalse(janela.mesa.armada, "desligar com o Texto à frente devolve a disposição de antes")
        self.assertEqual(janela._estado.texto_mesa, mesa.MESA_NUNCA)
        self.assertFalse(janela.menu.acoes["mesa_de_texto"].isChecked(), "o menu mostra o que vale")
        janela._comandos()["mesa_de_texto"]()
        self.assertTrue(janela.mesa.armada)
        self.assertTrue(janela.menu.acoes["mesa_de_texto"].isChecked())

    def test_janela_estreita_nao_arma_a_mesa(self) -> None:
        janela = self.montar(largura=mesa.LARGURA_MINIMA - 1)
        self.ir_para(janela, abas.TEXTO)
        if janela.width() < mesa.LARGURA_MINIMA:  # o piso da janela pode alargá-la sozinho
            self.assertFalse(janela.mesa.armada)

    def test_estreitar_a_janela_com_a_mesa_armada_nao_troca_os_lados(self) -> None:
        """O limiar é decidido ao entrar na área, e não a cada redimensionamento (S-645)."""
        janela = self.montar()
        self.ir_para(janela, abas.TEXTO)
        janela.resize(mesa.LARGURA_MINIMA - 50, 900)
        self.app.processEvents()
        self.assertTrue(janela.mesa.armada)

    def test_a_aba_texto_sabe_que_a_mesa_armou(self) -> None:
        """S-643/S-644: a janela avisa o painel, que passa a acompanhar a página."""
        janela = self.montar()
        self.assertFalse(janela.texto._na_mesa)
        self.ir_para(janela, abas.TEXTO)
        self.assertTrue(janela.texto._na_mesa)
        janela.pdf.ir_para_pagina(2)
        self.app.processEvents()
        self.assertEqual(janela.texto._folha_por_ler, 2, "virar a página com a mesa não levou a aba junto")
        self.ir_para(janela, abas.RESULTADO)
        self.assertFalse(janela.texto._na_mesa)

    def test_cada_disposicao_lembra_a_sua_alca(self) -> None:
        """A alça da mesa grava sempre; a de fora, só se alguém a escolheu (S-552).

        Aqui ninguém arrastou a de fora: ela é a repartição de fábrica, e gravá-la a faria valer
        como escolha na sessão seguinte. O que a mesa não pode fazer é escrever a dela por cima.
        """
        janela = self.montar()
        self.ir_para(janela, abas.TEXTO)
        total = sum(janela.divisor.sizes())
        janela.divisor.setSizes([int(total * 0.6), total - int(total * 0.6)])
        self.app.processEvents()
        janela._anotar_arranjo()
        self.assertAlmostEqual(janela._estado.mesa_fraction, 0.6, delta=0.03)
        self.assertFalse(janela._estado.sash_fraction, "a fábrica de fora da mesa virou escolha")
        self.ir_para(janela, abas.RESULTADO)
        self.ir_para(janela, abas.TEXTO)
        self.assertAlmostEqual(self.fracao_da_esquerda(janela), 0.6, delta=0.03)

    def test_a_alca_escolhida_fora_da_mesa_sobrevive_a_ela(self) -> None:
        janela = self.montar()
        janela._alca_movida_a_mao(0, 1)  # o que o `splitterMoved` do gesto chama
        antes = self.fracao_da_esquerda(janela)
        self.ir_para(janela, abas.TEXTO)
        total = sum(janela.divisor.sizes())
        janela.divisor.setSizes([int(total * 0.6), total - int(total * 0.6)])
        janela._alca_movida_a_mao(0, 1)  # na mesa: é a alça do PDF, e não decide a do trabalho
        self.app.processEvents()
        janela._anotar_arranjo()
        self.assertAlmostEqual(janela._estado.mesa_fraction, 0.6, delta=0.03)
        self.assertAlmostEqual(janela._estado.sash_fraction, antes, delta=0.03, msg="a alça de fora da mesa não foi apagada")


if __name__ == "__main__":
    unittest.main()
