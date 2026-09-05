"""A análise da partida inteira, sem motor e sem janela (S-537).

Três coisas se afirmam aqui, e nenhuma delas precisa do Stockfish: **onde estão os cortes** de
`?!`/`?`/`??` (em expectativa de vitória desde a segunda rodada), **como a perda é medida** e
**onde o gráfico põe cada ply**.

O que este arquivo deliberadamente não mede é o laço do motor: ele é fiação, roda numa `QThread` e
está em `tests/test_qt_motor.py`.
"""

from __future__ import annotations

import io
import unittest

import chess.pgn

from chess_diagram_ocr.engine import fracao_de_vantagem
from chess_diagram_ocr.ui import analise_da_partida as ap


def _jogo(movetext: str) -> chess.pgn.Game:
    lido = chess.pgn.read_game(io.StringIO(movetext))
    assert lido is not None
    return lido


class CortesTests(unittest.TestCase):
    """8, 15 e 25 pontos percentuais de expectativa de vitória perdidos (S-537, 2ª rodada)."""

    def test_os_tres_cortes_sao_8_15_e_25_pontos_de_expectativa(self) -> None:
        """**A escala é a chance de ganhar, e não o peão.** Em 256 lances de três partidas de
        torneio, a tabela em centipeões discorda do Lichess em 14 juízos e esta em 4 -- porque
        meio peão perdido no equilíbrio muda a partida e o mesmo meio peão com nove de vantagem
        não muda nada."""
        self.assertEqual("", ap.classificar(7.9))
        self.assertEqual(ap.IMPRECISAO, ap.classificar(8))
        self.assertEqual(ap.IMPRECISAO, ap.classificar(14.9))
        self.assertEqual(ap.ERRO, ap.classificar(15))
        self.assertEqual(ap.ERRO, ap.classificar(24.9))
        self.assertEqual(ap.ERRO_GRAVE, ap.classificar(25))
        self.assertEqual(ap.ERRO_GRAVE, ap.classificar(100))

    def test_a_expectativa_e_a_curva_da_barra_e_nao_uma_segunda(self) -> None:
        """Uma segunda logística aqui daria um juízo discordando do desenho ao lado dele -- é o
        defeito que a S-529 registra para a curva da barra."""
        self.assertAlmostEqual(50.0, ap.expectativa(0))
        self.assertAlmostEqual(100 * fracao_de_vantagem(300, None), ap.expectativa(300))
        self.assertGreater(ap.expectativa(100) - ap.expectativa(0), ap.expectativa(900) - ap.expectativa(800))

    def test_a_maioria_dos_lances_nao_recebe_simbolo(self) -> None:
        """A marca só vale enquanto for rara: uma partida em que metade dos lances é `?!` não diz
        nada sobre a partida. Medido: 29 lances marcados em 256."""
        self.assertEqual("", ap.classificar(0))
        self.assertEqual("", ap.classificar(5))

    def test_a_partida_do_critico_sai_como_o_lichess_nos_dois_lances_que_ele_nomeou(self) -> None:
        """`9...O-O` (0,46 -> 2,94) saía `?` e o Lichess dá `??`; `27...Kh7` (+3,04 -> +3,86) saía
        `?!` e o Lichess não marca nada. Os dois números são da partida ALG-ch Women 2012."""
        self.assertEqual(ap.ERRO_GRAVE, ap.julgar(46, 294, brancas_jogaram=False)[1])
        self.assertEqual("", ap.julgar(304, 386, brancas_jogaram=False)[1])

    def test_cada_juizo_vira_o_NAG_do_padrao_PGN(self) -> None:
        """**É o que faz a análise sobreviver ao arquivo**: `$4` é lido por qualquer programa de
        xadrez, e a lista de lances já o desenha. Uma marca só de tela morreria ao fechar."""
        self.assertEqual({ap.IMPRECISAO: 6, ap.ERRO: 2, ap.ERRO_GRAVE: 4}, ap.NAG_DE_JUIZO)


class PerdaTests(unittest.TestCase):
    """A perda é do ponto de vista de quem jogou, e nunca negativa."""

    def test_a_perda_das_brancas_e_a_avaliacao_caindo(self) -> None:
        self.assertEqual(150, ap.perda_do_lance(100, -50, brancas_jogaram=True))

    def test_a_perda_das_pretas_e_a_avaliacao_subindo(self) -> None:
        """Os dois números são do ponto de vista das brancas -- é como `Evaluation` os normaliza."""
        self.assertEqual(150, ap.perda_do_lance(-100, 50, brancas_jogaram=False))

    def test_o_lance_que_melhora_nao_vira_ganho(self) -> None:
        """Não é um lance "ganho": é o motor tendo mudado de ideia com mais um ply. Registrar isso
        encheria a partida de `!` que ninguém jogou."""
        self.assertEqual(0, ap.perda_do_lance(0, 300, brancas_jogaram=True))

    def test_o_teto_apaga_a_diferenca_quando_os_dois_lados_estouram(self) -> None:
        """De +18 para +12 as duas viram +10 e a perda é zero: acima de dez peões a diferença
        entre duas avaliações não é informação sobre o lance."""
        antes = ap.avaliacao_em_centipeoes(1800, None)
        depois = ap.avaliacao_em_centipeoes(1200, None)
        self.assertEqual(ap.TETO_DE_AVALIACAO, antes)
        self.assertEqual(0, ap.perda_do_lance(antes, depois, brancas_jogaram=True))

    def test_a_posicao_ja_ganha_nao_recebe_juizo_e_ja_nao_precisa_de_regra(self) -> None:
        """**O caso que criou a regra da "posição decidida", e que a escala nova resolve sozinha**:
        +18 -> +9 clampa em 1000 -> 900 e saía como "erro" numa posição em que qualquer lance
        ganha. Em expectativa de vitória isso custa 0,24 ponto, e nem chega perto do corte."""
        perda, juizo = ap.julgar(
            ap.avaliacao_em_centipeoes(1800, None),
            ap.avaliacao_em_centipeoes(900, None),
            brancas_jogaram=True,
        )
        self.assertEqual(100, perda, "a perda continua sendo medida e mostrada")
        self.assertEqual("", juizo)
        self.assertLess(ap.perda_de_expectativa(1000, 900, brancas_jogaram=True), 1.0)

    def test_a_posicao_ja_perdida_tambem_nao_recebe_juizo(self) -> None:
        """**O outro lado da regra que sumiu, e o defeito que o crítico achou.** `POSICAO_DECIDIDA`
        media `min` do ponto de vista de quem jogou: ela protegia quem estava ganhando e deixava
        quem estava perdido levar `erro grave` por cair de -6 para -10. Em expectativa isso custa
        2,75 pontos, para os dois lados, e não há regra nenhuma a acertar."""
        _perda, juizo = ap.julgar(600, 1000, brancas_jogaram=False)
        self.assertEqual("", juizo)
        _perda, juizo = ap.julgar(-600, -1000, brancas_jogaram=True)
        self.assertEqual("", juizo)

    def test_cair_de_ganho_para_apenas_melhor_continua_sendo_erro(self) -> None:
        """Quem sai de +6 e para em +2 jogou fora a partida ganha: 21 pontos de chance."""
        _perda, juizo = ap.julgar(600, 200, brancas_jogaram=True)
        self.assertEqual(ap.ERRO, juizo)

    def test_a_regra_da_decisao_vale_para_as_pretas_com_o_sinal_trocado(self) -> None:
        _perda, juizo = ap.julgar(-1800, -900, brancas_jogaram=False)
        self.assertEqual("", juizo)

    def test_o_mate_em_3_e_o_mate_em_30_valem_a_mesma_coisa(self) -> None:
        """Os dois são "acabou". Dar-lhes valores diferentes faria trocar um mate em 3 por um em 5
        aparecer como erro grave, e não é."""
        self.assertEqual(
            ap.avaliacao_em_centipeoes(None, 3), ap.avaliacao_em_centipeoes(None, 30)
        )
        self.assertEqual(-ap.TETO_DE_AVALIACAO, ap.avaliacao_em_centipeoes(None, -2))

    def test_posicao_sem_avaliacao_vale_zero(self) -> None:
        self.assertEqual(0, ap.avaliacao_em_centipeoes(None, None))


class PercursoTests(unittest.TestCase):
    """A linha principal virada FENs: `n+1` posições para `n` lances."""

    def test_sao_n_mais_um_porque_a_posicao_de_partida_tambem_e_avaliada(self) -> None:
        """A perda de um lance é a diferença entre antes e depois, e a "depois" de um lance é a
        "antes" do seguinte -- analisar par a par pediria `2n` buscas para a mesma resposta."""
        fens, passos = ap.percurso(_jogo("1. e4 e5 2. Nf3 *"))
        self.assertEqual(3, len(passos))
        self.assertEqual(4, len(fens))

    def test_cada_passo_traz_o_numero_a_cor_e_o_san(self) -> None:
        _fens, passos = ap.percurso(_jogo("1. e4 e5 2. Nf3 *"))
        self.assertEqual([(1, True, "e4"), (1, False, "e5"), (2, True, "Nf3")],
                         [(p.numero, p.brancas, p.san) for p in passos])

    def test_so_a_linha_principal_entra(self) -> None:
        """As variantes são o que quem estuda escreveu **sobre** a partida; analisá-las junto
        multiplicaria o tempo por um número que ninguém pediu."""
        _fens, passos = ap.percurso(_jogo("1. e4 (1. d4 d5 2. c4) e5 *"))
        self.assertEqual(["e4", "e5"], [p.san for p in passos])

    def test_partida_sem_lance_nao_tem_percurso(self) -> None:
        fens, passos = ap.percurso(_jogo("*"))
        self.assertEqual(1, len(fens))
        self.assertEqual((), passos)


def _avaliado(
    ply: int,
    cp: int,
    perda: int = 0,
    mate: int | None = None,
    *,
    chance: float | None = None,
    profundidade: int = 0,
    acabou: bool = False,
) -> ap.Avaliado:
    """Um `Avaliado` para o teste. `chance` é a perda de expectativa; sem ela, a do peão.

    Sem `chance`, o lance é tratado como se tivesse saído **do equilíbrio** e perdido `perda`
    centipeões: é a conversão que a própria `perda_de_expectativa` faz, e não uma segunda régua.
    """
    pontos = (
        ap.perda_de_expectativa(0, -int(perda), brancas_jogaram=True) if chance is None else float(chance)
    )
    return ap.Avaliado(
        ply=ply,
        numero=(ply + 1) // 2,
        brancas=ply % 2 == 1,
        san="Nf3",
        centipeoes=cp,
        mate_em=mate,
        perda=perda,
        juizo=ap.classificar(pontos),
        perda_de_chance=pontos,
        profundidade=profundidade,
        acabou=acabou,
    )


class GraficoTests(unittest.TestCase):
    """Onde cada ply cai, e o que o clique acerta (S-537)."""

    def test_o_primeiro_e_o_ultimo_ply_encostam_nas_bordas(self) -> None:
        pontos = ap.pontos_do_grafico([_avaliado(1, 0), _avaliado(2, 0), _avaliado(3, 0)], 100, 50)
        self.assertEqual(0, pontos[0][0])
        self.assertEqual(99, pontos[-1][0])

    def test_brancas_para_cima_e_pretas_para_baixo(self) -> None:
        """É o sentido da barra lateral virado 90°; trocá-lo entre os dois desenhos da mesma tela
        seria o defeito que a S-158 registra para cor."""
        (_x, y_branco), (_x2, y_meio), (_x3, y_preto) = ap.pontos_do_grafico(
            [_avaliado(1, 800), _avaliado(2, 0), _avaliado(3, -800)], 30, 101
        )
        self.assertLess(y_branco, y_meio)
        self.assertLess(y_meio, y_preto)
        self.assertEqual(ap.y_do_meio(101), y_meio + 1 - 1)

    def test_a_escala_vertical_e_a_mesma_curva_nao_linear_da_barra(self) -> None:
        """**Cem centipeões valem mais perto do zero do que perto do fim**, e é a razão de a curva
        existir: um gráfico linear achataria contra a linha do meio justamente a faixa em que a
        partida se decide, e gastaria a altura com a faixa em que ela já acabou."""
        def y(cp: int) -> int:
            return ap.pontos_do_grafico([_avaliado(1, cp)], 10, 201)[0][1]

        perto_do_zero = y(0) - y(100)
        perto_do_fim = y(900) - y(1000)
        self.assertGreater(perto_do_zero, 20)
        self.assertLess(perto_do_fim, 3)

    def test_sem_lance_ou_sem_geometria_nao_ha_pontos(self) -> None:
        self.assertEqual((), ap.pontos_do_grafico([], 100, 50))
        self.assertEqual((), ap.pontos_do_grafico([_avaliado(1, 0)], 0, 50))

    def test_o_clique_no_vale_leva_ao_lance_do_vale(self) -> None:
        """É o gesto inteiro do item: o gráfico existe para achar onde a partida virou."""
        self.assertEqual(0, ap.indice_no_x(0, 5, 101))
        self.assertEqual(2, ap.indice_no_x(50, 5, 101))
        self.assertEqual(4, ap.indice_no_x(100, 5, 101))

    def test_o_clique_fora_da_faixa_cai_na_ponta_mais_proxima(self) -> None:
        """Meio pixel antes do começo não pode ser "nenhum lance"."""
        self.assertEqual(0, ap.indice_no_x(-20, 5, 101))
        self.assertEqual(4, ap.indice_no_x(500, 5, 101))


class ResumoTests(unittest.TestCase):
    """A frase que abre o relatório."""

    def test_a_contagem_e_por_cor(self) -> None:
        """A pergunta é sobre a **própria** partida: um total somado com o do adversário não
        responde "quantos erros eu cometi"."""
        frase = ap.resumo([_avaliado(1, 0, 120), _avaliado(2, 0, 400), _avaliado(3, 0, 60)])
        self.assertIn("3 lance(s) analisados", frase)
        self.assertIn("Brancas: 1 imprecisão, 1 erro", frase)
        self.assertIn("Pretas: 1 erro grave", frase)

    def test_a_contagem_concorda_em_numero(self) -> None:
        """`2 imprecisão` saiu na primeira fotografia. Um `s` colado no fim não serve a nenhuma
        das três formas: imprecisão/imprecisões, erro/erros, erro grave/erros graves."""
        frase = ap.resumo([_avaliado(1, 0, 60), _avaliado(3, 0, 60), _avaliado(5, 0, 400)])
        self.assertIn("2 imprecisões", frase)
        self.assertIn("1 erro grave", frase)
        self.assertEqual("erros graves", ap.rotulo_de_juizo(ap.ERRO_GRAVE, 3))
        self.assertEqual("erro", ap.rotulo_de_juizo(ap.ERRO, 1))
        self.assertEqual("", ap.rotulo_de_juizo("", 2))

    def test_partida_limpa_diz_que_esta_limpa(self) -> None:
        self.assertIn("Brancas: sem erro", ap.resumo([_avaliado(1, 0, 10)]))

    def test_sem_lance_nenhum_a_frase_nao_promete_analise(self) -> None:
        self.assertIn("Não há lance", ap.resumo([]))

    def test_a_frase_final_conta_os_simbolos_escritos(self) -> None:
        """Dizer só "análise concluída" esconderia que ela **editou** a árvore."""
        self.assertIn("12 lance(s) avaliados, 3 com símbolo", ap.frase_final(12, 3, cancelado=False))

    def test_cancelar_nao_joga_fora_o_que_ja_foi_medido(self) -> None:
        frase = ap.frase_final(7, 1, cancelado=True)
        self.assertIn("cancelada", frase)
        self.assertIn("7 lance(s) já avaliados ficam gravados", frase)

    def test_o_progresso_traz_o_lance_para_a_espera_ter_conteudo(self) -> None:
        self.assertIn("Bd3", ap.frase_de_progresso(12, 40, "Bd3"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
