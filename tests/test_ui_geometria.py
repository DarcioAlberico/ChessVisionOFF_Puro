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
    FRACAO_PADRAO_DO_DIVISOR,
    PISO_MEDIDO,
    divisor_da_primeira_abertura,
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
        """Trocar por um notebook: a janela guardada é maior que a tela que existe agora.

        **A tela vence o piso** (S-552, terceira rodada). Até esta rodada a altura saía em 800 --
        o `PISO_MEDIDO` -- contra os 768 do notebook, e a janela recuperada nascia 32 px mais alta
        que o monitor em que ela acabara de ser posta. Um piso maior que a tela não é piso.
        """
        alvo = geometria.geometria_a_aplicar("2600x1500+3000+0", ((0, 0, 1366, 768),))
        assert alvo is not None
        corrigida = geometria.geometria_de_texto(alvo)
        assert corrigida is not None
        self.assertEqual((corrigida.largura, corrigida.altura), (1366, 768))
        self.assertEqual((corrigida.x, corrigida.y), (0, 0))

    def test_a_janela_recuperada_nunca_nasce_maior_que_a_tela(self) -> None:
        """**O bloqueio 3 do crítico, com o caso dele.** `geometria_a_aplicar` devolvia 1180x800
        para uma tela de 1024x768: mais larga e mais alta que o monitor, e centrada -- ou seja,
        sem barra de título ao alcance para arrastá-la de volta.

        Vale para o piso de fábrica e para o que a janela do Qt passa: quem manda é a tela.
        """
        pisos = (geometria.PISO_MEDIDO, piso_da_janela(500, 440, com_a_medicao=False), (4000, 3000))
        for tela in ((0, 0, 1024, 768), (0, 0, 1366, 768), (0, 0, 1280, 720)):
            for piso in pisos:
                with self.subTest(tela=tela, piso=piso):
                    alvo = geometria.geometria_a_aplicar("1400x950+2100+120", (tela,), piso=piso)
                    assert alvo is not None
                    lida = geometria.geometria_de_texto(alvo)
                    assert lida is not None
                    self.assertLessEqual(lida.largura, tela[2] - tela[0])
                    self.assertLessEqual(lida.altura, tela[3] - tela[1])
                    self.assertTrue(geometria.visivel_em(lida, (tela,)))

    def test_a_janela_que_cabe_em_parte_e_grampeada_sem_sair_do_lugar(self) -> None:
        """**A variante que o teste acima não alcançava** (S-552, quarta rodada).

        Ele só exercita geometrias com a **posição** fora da tela, e a correção da terceira rodada
        entrou depois do curto-circuito de `visivel_em`: uma janela guardada que *aparece* na tela
        nova era devolvida como veio, por maior que fosse.
        `geometria_a_aplicar('1920x1080+0+0', [(0, 0, 1024, 768)])` respondia **1920x1080** -- 896
        px mais larga que o monitor --, que é exatamente o "cabe em parte" nomeado no docstring da
        função: baixar a resolução, ou desdocar o notebook sem mudar a janela de lugar.

        O grampo é só para baixo, e desde a quinta rodada a janela que ele encolheu é **empurrada
        para dentro**: os dois primeiros casos já estavam no canto e não se mexem, e o terceiro
        perde os 40 px de `x` porque na largura grampeada eles ficariam fora -- ver
        `test_a_janela_grampeada_nao_fica_com_meia_janela_fora_da_tela`.
        """
        for tela, guardada, esperada in (
            ((0, 0, 1024, 768), "1920x1080+0+0", "1024x768+0+0"),
            ((0, 0, 1366, 768), "1920x1080+0+0", "1366x768+0+0"),
            ((0, 0, 1280, 1024), "1400x950+40+30", "1280x950+0+30"),
            ((0, 0, 1024, 768), "800x600+100+50", "800x600+100+50"),
        ):
            with self.subTest(tela=tela, guardada=guardada):
                self.assertEqual(esperada, geometria.geometria_a_aplicar(guardada, (tela,)))

    def test_a_janela_grampeada_nao_fica_com_meia_janela_fora_da_tela(self) -> None:
        """**O achado da quinta rodada**: o grampo encolhia e não reposicionava.

        `geometria_a_aplicar('1920x1080-500+0', [(0, 0, 1024, 768)])` devolvia `1024x768-500+0` --
        do tamanho exato da tela, com 500 px dela fora dela, e `visivel_em` aprovando porque os 524
        px restantes bastam. O empurrão é o menor que põe a janela inteira dentro, e **o eixo que
        não foi grampeado guarda a posição**: no segundo caso só a altura estoura e `x` fica nos 40;
        no terceiro só a largura, e `y` fica nos 50. Grampeado, um eixo passa a ter a medida exata
        da tela e não sobra onde pôr a janela senão no canto -- é o primeiro caso.
        """
        for tela, guardada, esperada in (
            ((0, 0, 1024, 768), "1920x1080-500+0", "1024x768+0+0"),
            ((0, 0, 1600, 1200), "1400x1400+40+30", "1400x1200+40+0"),
            ((0, 0, 1024, 768), "1400x700+900+50", "1024x700+0+50"),
        ):
            with self.subTest(guardada=guardada):
                alvo = geometria.geometria_a_aplicar(guardada, (tela,))
                self.assertEqual(esperada, alvo)
                lida = geometria.geometria_de_texto(alvo or "")
                assert lida is not None
                x0, y0, x1, y1 = lida.retangulo
                self.assertTrue(
                    tela[0] <= x0 and tela[1] <= y0 and x1 <= tela[2] and y1 <= tela[3],
                    f"{alvo} ainda cruza a borda de {tela}",
                )

    def test_a_janela_que_coube_nao_e_empurrada(self) -> None:
        """O empurrão é **só** da que o grampo encolheu, e é o que o separa de desfazer arranjo.

        Uma janela que cabe e que alguém deixou com uma borda para fora continua onde estava --
        é a decisão de `VISIVEL_MINIMO`, e ela não mudou nesta rodada.
        """
        self.assertEqual("900x700-200+40", geometria.geometria_a_aplicar("900x700-200+40", ((0, 0, 1920, 1080),)))
        self.assertEqual("900x700+1800+40", geometria.geometria_a_aplicar("900x700+1800+40", ((0, 0, 1920, 1080),)))

    def test_a_janela_deitada_sobre_dois_monitores_nao_e_encolhida(self) -> None:
        """O grampo é contra a **área de trabalho inteira**, e não contra um monitor: encolher ao
        maior deles desfaria um arranjo que alguém escolheu com a janela nas duas telas."""
        dois = ((0, 0, 1920, 1080), (1920, 0, 3840, 1080))
        self.assertEqual("2400x1000+700+40", geometria.geometria_a_aplicar("2400x1000+700+40", dois))
        self.assertEqual(
            "1920x1000+0+40",
            geometria.geometria_a_aplicar("2400x1000+700+40", dois[:1]),
            "desligado o segundo monitor, a janela passa a ter de caber no que sobrou",
        )

    def test_sem_a_medicao_o_piso_e_so_a_soma_das_partes(self) -> None:
        """As duas metades de `piso_da_janela`, separadas porque a janela do Qt rola (S-552).

        `piso_da_janela` continua devolvendo o maior dos dois -- é a decisão da S-150 e ela não
        mudou. O que mudou é que existe como pedir só a soma, e é isso que `qt/janela.py` passa.
        """
        soma = piso_da_janela(500, 440, com_a_medicao=False)
        self.assertEqual(soma, (500 + 440 + CHROME_HORIZONTAL, ALTURA_MINIMA_DO_CONTEUDO + CHROME_VERTICAL))
        self.assertLess(soma[0], PISO_MEDIDO[0])
        self.assertLess(soma[1], PISO_MEDIDO[1])
        self.assertEqual(piso_da_janela(500, 440), PISO_MEDIDO)
        # O maior é por componente: a largura somada de 1860 passa o medido, a altura não.
        self.assertEqual(piso_da_janela(900, 900)[0], piso_da_janela(900, 900, com_a_medicao=False)[0])
        self.assertEqual(piso_da_janela(900, 900)[1], PISO_MEDIDO[1])

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


class DivisorDaPrimeiraAberturaTests(unittest.TestCase):
    """Onde a alça nasce quando não há nada guardado (S-552, segunda rodada).

    **Por que a fração sozinha deixou de bastar.** O piso de 720 px do lado esquerdo fazia dois
    trabalhos: segurava a janela (o defeito que a S-552 fechou) e, de graça, dava 720 px à aba de
    trabalho numa janela de 1400 em vez dos 586 que 42% dariam. Baixado o piso, a segunda garantia
    caiu junto -- medido, o tabuleiro da sala foi de 488 para 392 px.
    """

    PREFERIDAS = {"preferida_esquerda": 720, "preferida_direita": 520}

    def test_a_janela_larga_da_a_fracao_porque_ela_ja_passa_do_preferido(self) -> None:
        """A 1920 px, 42% são 806 -- mais que os 720 que a aba pede. O preferido é piso, não teto:
        quem tem tela grande continua vendo o livro grande."""
        self.assertEqual(806, divisor_da_primeira_abertura(1920, **self.PREFERIDAS))

    def test_a_janela_media_da_o_preferido_porque_a_fracao_fica_abaixo(self) -> None:
        """**É o caso que quebrou.** A 1400 px, 42% são 588 e a aba pede 720."""
        self.assertEqual(720, divisor_da_primeira_abertura(1400, **self.PREFERIDAS))

    def test_na_tela_minima_quem_cede_e_a_esquerda(self) -> None:
        """Os dois preferidos somam 1240 e não cabem em 1024: o direito leva o que pede, e o
        esquerdo fica com o resto. É a página do livro, e é ela que não se lê espremida."""
        self.assertEqual(504, divisor_da_primeira_abertura(1024, **self.PREFERIDAS))

    def test_numa_largura_menor_que_os_dois_preferidos_ninguem_fica_com_zero(self) -> None:
        """Um lado com zero pixel é o estado do qual não há gesto de mouse que devolva -- a mesma
        razão dos limites de `fracao_de_divisor`."""
        # A partir de 2: numa largura de 1 px não há como dar um pixel a cada lado.
        for largura in (2, 100, 400, 519, 520, 521):
            with self.subTest(largura=largura):
                esquerda = divisor_da_primeira_abertura(largura, **self.PREFERIDAS)
                self.assertGreaterEqual(esquerda, 1)
                self.assertGreaterEqual(largura - esquerda, 1)

    def test_sem_geometria_ainda_a_resposta_e_zero(self) -> None:
        """Antes do primeiro `show` o `QSplitter` não tem largura, e repartir zero poria a alça
        num lugar que a janela nunca pediu."""
        self.assertEqual(0, divisor_da_primeira_abertura(0, **self.PREFERIDAS))
        self.assertEqual(0, divisor_da_primeira_abertura(-40, **self.PREFERIDAS))

    def test_a_fracao_padrao_e_a_da_S_156(self) -> None:
        """Nenhum número novo: quem não passa fração recebe a que o item de lembrar a janela já
        declarou."""
        self.assertEqual(
            divisor_da_primeira_abertura(1920, fracao=FRACAO_PADRAO_DO_DIVISOR, **self.PREFERIDAS),
            divisor_da_primeira_abertura(1920, **self.PREFERIDAS),
        )


if __name__ == "__main__":
    unittest.main()
