"""O piso da janela, e a janela que o respeita (S-150); e o arranjo lembrado (S-156).

O cálculo é puro e afirmado contra a soma declarada; a ligação com o `Tk` é afirmada com uma
janela de verdade, porque a função podia existir e `root.minsize()` continuar não sendo
chamado -- que é exatamente o estado anterior.

A S-156 entra no mesmo arquivo porque é a mesma pergunta com outro escopo: **onde a janela cabe**.
O piso responde "quão pequena ela pode ficar"; a geometria lembrada responde "onde ela pode
estar" -- e as duas são desmentidas pela mesma coisa, uma tela que mudou desde ontem.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui import geometria
from chess_diagram_ocr.ui.geometria import (
    ALTURA_MINIMA_DO_CONTEUDO,
    CHROME_HORIZONTAL,
    CHROME_VERTICAL,
    PISO_MEDIDO,
    piso_da_janela,
)


class PisoTests(unittest.TestCase):
    def test_com_os_paineis_de_hoje_vence_a_medicao(self) -> None:
        """A soma dá (1000, 716) e é otimista -- 1100×760 já cortava a fila de salvar."""
        self.assertEqual(piso_da_janela(420, 520), PISO_MEDIDO)
        self.assertLess(420 + 520 + CHROME_HORIZONTAL, PISO_MEDIDO[0])
        self.assertLess(ALTURA_MINIMA_DO_CONTEUDO + CHROME_VERTICAL, PISO_MEDIDO[1])

    def test_o_piso_acompanha_o_painel_que_cresce_acima_da_medicao(self) -> None:
        """A medição é piso, não teto: um painel maior empurra o número para cima."""
        largura, _ = piso_da_janela(900, 900)
        self.assertEqual(largura, 900 + 900 + CHROME_HORIZONTAL)
        self.assertGreater(largura, PISO_MEDIDO[0])

    def test_o_piso_cobre_as_resolucoes_em_que_o_defeito_foi_fotografado(self) -> None:
        """1100×760 cortava a fila de salvar; 940×620 sumia com o botão "Remover"."""
        largura, altura = piso_da_janela(420, 520)
        for cortada in ((1100, 760), (940, 620)):
            with self.subTest(tamanho=cortada):
                self.assertTrue(
                    cortada[0] < largura or cortada[1] < altura,
                    f"{cortada} continuaria permitida pelo piso {(largura, altura)}",
                )

    def test_a_largura_cabe_num_notebook_de_1366_e_a_altura_nao(self) -> None:
        """O item pela metade, travado como teste em vez de escondido.

        A largura cabe. A altura **não**: 800 contra 768. É o que o conteúdo precisa hoje *sem
        rolagem*, e quem fecha a lacuna é a segunda metade da S-150 -- as abas rolando --, que
        não foi entregue. Baixar o piso para caber devolveria o botão cortado em silêncio, que
        é o defeito original; o teste registra a dívida no lugar disso.

        Quando a rolagem entrar, este teste muda junto: a altura passa a poder ser menor.
        """
        largura, altura = piso_da_janela(420, 520)
        self.assertLessEqual(largura, 1366)
        self.assertGreater(altura, 768, "se isto passar a caber, a rolagem da S-150 chegou")


class GeometriaLembradaTests(unittest.TestCase):
    """A janela restaurada, e os dois modos de ela abrir onde não há tela (S-156).

    Os dois vêm de trocar de máquina ou de monitor entre uma sessão e a seguinte, e nenhum dos
    dois gera erro: a janela simplesmente não aparece, e o programa parece não ter aberto.
    """

    UM_MONITOR = ((0, 0, 1920, 1080),)
    DOIS_MONITORES = ((0, 0, 1920, 1080), (1920, 0, 5360, 1440))

    def test_a_leitura_e_a_escrita_fecham(self) -> None:
        for texto in ("1700x980+120+40", "800x600+0+0", "1700x980-1690+0", "1024x768+100-50"):
            with self.subTest(texto=texto):
                lida = geometria.geometria_de_texto(texto)
                assert lida is not None
                self.assertEqual(str(lida), texto)

    def test_o_que_nao_e_geometria_e_recusado_em_vez_de_adivinhado(self) -> None:
        """Um estado corrompido que virasse `0x0+0+0` abriria uma janela invisível, e o usuário
        não teria como saber que o culpado é um arquivo."""
        for lixo in ("", "1700x980", "axb+0+0", "0x980+0+0", "1700x0+0+0", "1700 x 980 + 0 + 0"):
            with self.subTest(lixo=lixo):
                self.assertIsNone(geometria.geometria_de_texto(lixo))

    def test_a_janela_dentro_de_um_monitor_e_deixada_em_paz(self) -> None:
        self.assertEqual(geometria.geometria_a_aplicar("1700x980+100+50", self.UM_MONITOR), "1700x980+100+50")

    def test_o_monitor_que_desapareceu(self) -> None:
        """A janela estava em `+2560+0`; a tela do escritório ficou no escritório."""
        alvo = geometria.geometria_a_aplicar("1700x980+2560+0", self.UM_MONITOR)
        assert alvo is not None
        corrigida = geometria.geometria_de_texto(alvo)
        assert corrigida is not None
        self.assertTrue(geometria.visivel_em(corrigida, self.UM_MONITOR))
        self.assertEqual((corrigida.largura, corrigida.altura), (1700, 980), "o tamanho não precisava mudar")

    def test_o_mesmo_ponto_continua_valendo_com_o_segundo_monitor_ligado(self) -> None:
        """O controle do teste acima: com a tela de volta, a geometria não é mexida."""
        self.assertEqual(geometria.geometria_a_aplicar("1700x980+2560+0", self.DOIS_MONITORES), "1700x980+2560+0")

    def test_cabe_em_parte_e_encolhido_ate_o_monitor(self) -> None:
        """Trocar por um notebook: a janela guardada é maior que a tela que existe agora."""
        alvo = geometria.geometria_a_aplicar("2600x1500+3000+0", ((0, 0, 1366, 768),))
        assert alvo is not None
        corrigida = geometria.geometria_de_texto(alvo)
        assert corrigida is not None
        self.assertEqual(corrigida.largura, 1366)
        self.assertEqual(corrigida.altura, geometria.PISO_MEDIDO[1], "o piso da S-150 vence a tela")
        self.assertEqual((corrigida.x, corrigida.y), (0, 0))

    def test_uma_borda_de_fora_de_proposito_e_arranjo_legitimo(self) -> None:
        """Recusar isto seria a interface desfazendo uma escolha deliberada."""
        self.assertEqual(geometria.geometria_a_aplicar("1700x980-200+40", self.UM_MONITOR), "1700x980-200+40")

    def test_sem_monitores_a_janela_nao_e_movida(self) -> None:
        """Não saber onde estão as telas não é razão para mover a janela de ninguém."""
        self.assertEqual(geometria.geometria_a_aplicar("1700x980+9000+0", ()), "1700x980+9000+0")

    def test_o_minimo_visivel_e_nos_dois_eixos_e_nao_em_area(self) -> None:
        """Uma janela que cruza 2.000 px de largura e 3 px de altura tem 6.000 px² e é invisível."""
        fatia = geometria.Geometria(largura=2000, altura=980, x=0, y=1077)
        self.assertFalse(geometria.visivel_em(fatia, self.UM_MONITOR))

    def test_a_janela_minimizada_nao_e_gravada(self) -> None:
        """O Tk devolve `1x1+-32000+-32000` no Windows, e gravar isso perde o arranjo bom."""
        self.assertEqual(geometria.geometria_gravavel("1x1+-32000+-32000"), "")
        self.assertEqual(geometria.geometria_gravavel("lixo"), "")
        self.assertEqual(geometria.geometria_gravavel("1700x980+0+0"), "1700x980+0+0")

    def test_a_fracao_do_divisor_nunca_esconde_um_painel(self) -> None:
        """`sash_place` fora dos limites deixa um painel com zero pixel -- e a alça colada na
        borda, de onde nenhum gesto de mouse a traz de volta."""
        self.assertAlmostEqual(geometria.fracao_de_divisor(700, 1700), 700 / 1700, places=9)
        self.assertEqual(geometria.fracao_de_divisor(0, 1700), 0.15)
        self.assertEqual(geometria.fracao_de_divisor(1700, 1700), 0.85)

    def test_sem_largura_a_fracao_cai_no_padrao(self) -> None:
        """É o que acontece antes do primeiro layout, e 42% é o arranjo da primeira execução."""
        self.assertEqual(geometria.fracao_de_divisor(0, 0), geometria.FRACAO_PADRAO_DO_DIVISOR)


if __name__ == "__main__":
    unittest.main()
