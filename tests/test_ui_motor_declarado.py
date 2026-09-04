"""As opções do motor e o que o painel dele mostra, sem abrir janela (S-529/S-536).

O que se afirma aqui é o que decide, e não o que desenha: até quanto cada opção pode ir **nesta
máquina**, o que é recusado e com que frase, o que uma mudança faz com o processo aberto, quanto
da barra é das brancas e como uma linha de MultiPV se numera.

A régua de cada teste é o motivo da decisão, e não o valor: `teto_de` não é "8192" -- é "metade
da memória, arredondada para baixo à potência de dois", e é isso que o teste pergunta.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.engine import Evaluation, fracao_de_vantagem
from chess_diagram_ocr.settings import EngineSettings
from chess_diagram_ocr.ui import motor_declarado as md
from chess_diagram_ocr.ui import tokens


class TetosTests(unittest.TestCase):
    """O teto sai dos números da máquina, e o teste os passa à mão."""

    def test_hash_e_metade_da_memoria_arredondada_a_potencia_de_dois(self) -> None:
        """**Metade e não tudo**: o resto da máquina existe, e uma tabela que force o sistema a
        usar disco é mais lenta que uma tabela pequena. Potência de dois porque é o que o
        Stockfish reparte de fato -- pedir 3000 MB gasta 2048 e joga fora 952."""
        self.assertEqual(8192, md.teto_de(md.HASH, memoria_mb=32_000, nucleos=8))
        self.assertEqual(2048, md.teto_de(md.HASH, memoria_mb=8_000, nucleos=8))

    def test_sem_memoria_conhecida_o_teto_cai_no_piso_e_nao_no_infinito(self) -> None:
        """`memoria_da_maquina_mb` devolve zero quando o sistema não diz, e um teto de zero
        deixaria o campo sem faixa nenhuma -- que é pior que um teto conservador."""
        self.assertEqual(16, md.teto_de(md.HASH, memoria_mb=0, nucleos=4))

    def test_threads_e_o_numero_de_nucleos(self) -> None:
        """Não `núcleos - 1`: quem analisa uma partida inteira quer a máquina toda, e a janela
        continua respondendo porque a análise não roda na linha de eventos."""
        self.assertEqual(12, md.teto_de(md.THREADS, memoria_mb=32_000, nucleos=12))
        self.assertEqual(1, md.teto_de(md.THREADS, memoria_mb=32_000, nucleos=0))

    def test_multipv_e_o_tempo_nao_dependem_da_maquina(self) -> None:
        """Os dois são limites de **leitura** e não de recurso: dez linhas já são ruído, e um
        minuto por posição faz a análise contínua deixar de acompanhar quem navega."""
        self.assertEqual(10, md.teto_de(md.MULTIPV, memoria_mb=1, nucleos=1))
        self.assertEqual(60_000, md.teto_de(md.MOVETIME, memoria_mb=1, nucleos=1))

    def test_opcao_desconhecida_levanta(self) -> None:
        with self.assertRaises(KeyError):
            md.teto_de("skill_level", memoria_mb=8_000, nucleos=8)


class ValidacaoTests(unittest.TestCase):
    """A frase diz o intervalo, e não "inválido"."""

    def test_abaixo_do_piso_a_frase_traz_o_minimo(self) -> None:
        frase = md.validar(md.HASH, 8, memoria_mb=32_000, nucleos=8)
        self.assertIn("16", frase)
        self.assertIn("MB", frase)

    def test_acima_do_teto_a_frase_traz_o_teto_desta_maquina(self) -> None:
        """Quem digitou 64 núcleos numa máquina de 8 precisa **ver** o 8."""
        frase = md.validar(md.THREADS, 64, memoria_mb=32_000, nucleos=8)
        self.assertIn("8", frase)

    def test_o_que_nao_e_numero_e_recusado_pelo_nome_do_campo(self) -> None:
        self.assertIn("Núcleos", md.validar(md.THREADS, "muitos", memoria_mb=32_000, nucleos=8))

    def test_o_valor_dentro_da_faixa_passa(self) -> None:
        for chave, valor in ((md.HASH, 512), (md.THREADS, 4), (md.MULTIPV, 5), (md.MOVETIME, 1500)):
            with self.subTest(chave=chave):
                self.assertEqual("", md.validar(chave, valor, memoria_mb=32_000, nucleos=8))

    def test_caminho_vazio_e_a_resposta_certa_e_nao_um_erro(self) -> None:
        """Vazio é "procure sozinho" (S-33), que é o caso da máquina com o Stockfish no PATH."""
        self.assertEqual("", md.validar_caminho(""))
        self.assertEqual("", md.validar_pasta_de_tablebase("   "))

    def test_caminho_que_nao_existe_diz_o_caminho(self) -> None:
        frase = md.validar_caminho("Z:/nao/existe/stockfish.exe")
        self.assertIn("stockfish.exe", frase)

    def test_pasta_no_lugar_do_binario_e_binario_no_lugar_da_pasta(self) -> None:
        """Os dois erros mais comuns de quem cola um caminho, e cada um tem a sua frase."""
        pasta = __file__.rsplit("test_ui_motor_declarado.py", 1)[0]
        self.assertIn("pasta", md.validar_caminho(pasta))
        self.assertIn("arquivo", md.validar_pasta_de_tablebase(__file__))

    def test_aspas_em_volta_nao_inventam_um_caminho_inexistente(self) -> None:
        """É o que o Windows põe em "Copiar como caminho", e é o caminho que se cola."""
        self.assertEqual("", md.validar_caminho(f'"{__file__}"'))


class PlanoTests(unittest.TestCase):
    """O que separa `setoption` de derrubar o processo (S-536)."""

    def test_nada_mudou_e_nada_acontece(self) -> None:
        antes = EngineSettings(path="a.exe", hash_mb=256, threads=4)
        plano = md.plano_de_aplicacao(antes, antes)
        self.assertFalse(plano.mudou)
        self.assertFalse(plano.trocar_processo)
        self.assertIn("não mudaram", plano.frase())

    def test_hash_e_threads_vao_por_setoption_no_processo_aberto(self) -> None:
        """**É o item inteiro**: `setoption name Hash value 512` é uma linha no `stdin`, e o
        Stockfish realoca a tabela sozinho. Fechar e reabrir custaria os 100 a 300 ms de
        inicialização e perderia a análise em curso."""
        plano = md.plano_de_aplicacao(
            EngineSettings(path="a.exe", hash_mb=128, threads=1),
            EngineSettings(path="a.exe", hash_mb=512, threads=4),
        )
        self.assertFalse(plano.trocar_processo)
        self.assertEqual({"Hash": 512, "Threads": 4}, plano.do_processo)
        self.assertIn("sem derrubar o processo", plano.frase())

    def test_multipv_e_tempo_nao_tocam_o_processo(self) -> None:
        """Os dois entram em cada análise, e é por isso que mudá-los vale na resposta seguinte."""
        plano = md.plano_de_aplicacao(
            EngineSettings(path="a.exe"), EngineSettings(path="a.exe", multipv=5, movetime_ms=2000)
        )
        self.assertFalse(plano.trocar_processo)
        self.assertEqual({}, plano.do_processo)
        self.assertEqual({md.MULTIPV: 5, md.MOVETIME: 2000}, plano.por_analise)

    def test_a_pasta_de_tablebases_e_opcao_do_processo(self) -> None:
        """`SyzygyPath` é opção UCI: apontá-la faz o próprio motor dar avaliação exata (S-538)."""
        plano = md.plano_de_aplicacao(
            EngineSettings(path="a.exe"), EngineSettings(path="a.exe", syzygy_path="D:/syzygy")
        )
        self.assertFalse(plano.trocar_processo)
        self.assertEqual({"SyzygyPath": "D:/syzygy"}, plano.do_processo)

    def test_trocar_o_binario_derruba_e_sobe_outro(self) -> None:
        """O processo aberto **é** o motor antigo: a única forma de falar com outro é abrir outro."""
        plano = md.plano_de_aplicacao(
            EngineSettings(path="a.exe", hash_mb=128), EngineSettings(path="b.exe", hash_mb=512)
        )
        self.assertTrue(plano.trocar_processo)
        self.assertEqual({}, plano.do_processo, "o motor que vai morrer não se configura")
        self.assertIn("processo anterior foi encerrado", plano.frase())

    def test_o_mesmo_caminho_escrito_diferente_nao_e_troca(self) -> None:
        """Sem isto, abrir o diálogo e confirmar sem mexer em nada derrubaria o motor -- e o
        caminho volta com aspas e barra invertida de todo "Copiar como caminho" do Windows."""
        plano = md.plano_de_aplicacao(
            EngineSettings(path="C:/Program Files/x/stockfish.exe"),
            EngineSettings(path='"C:\\Program Files\\x\\stockfish.exe" '),
        )
        self.assertFalse(plano.trocar_processo)
        self.assertFalse(plano.mudou)


class BarraTests(unittest.TestCase):
    """A barra de avaliação: altura, cor e o que o mate faz (S-529)."""

    def test_a_curva_e_a_de_engine_e_nao_uma_segunda(self) -> None:
        """Uma segunda curva daria uma barra que discorda do número escrito ao lado dela."""
        for cp in (-800, -100, 0, 35, 250, 900):
            with self.subTest(cp=cp):
                esperado = Evaluation(score_cp=cp, mate_in=None, best_move=None).advantage_fraction()
                self.assertEqual(esperado, fracao_de_vantagem(cp, None))

    def test_a_posicao_equilibrada_reparte_a_barra_ao_meio(self) -> None:
        self.assertEqual(100, md.altura_de_brancas(fracao_de_vantagem(0, None), 200))

    def test_a_vantagem_das_brancas_cresce_a_faixa_de_baixo(self) -> None:
        """Brancas embaixo é a convenção do Lichess e da ChessBase, e ela casa com o tabuleiro
        ao lado -- uma barra invertida faria o olho ter de traduzir."""
        mais = md.altura_de_brancas(fracao_de_vantagem(200, None), 200)
        menos = md.altura_de_brancas(fracao_de_vantagem(-200, None), 200)
        self.assertGreater(mais, 100)
        self.assertLess(menos, 100)
        self.assertEqual(200, mais + menos, "a curva é simétrica em torno do zero")

    def test_a_escala_nao_e_linear_e_a_diferenca_e_medida(self) -> None:
        """De 0 a +1,00 a barra anda mais do que de +5,00 a +10,00, e é a razão de ela existir:
        a segunda faixa não muda a partida."""
        do_zero_a_um = md.altura_de_brancas(fracao_de_vantagem(100, None), 200) - 100
        de_cinco_a_dez = md.altura_de_brancas(fracao_de_vantagem(1000, None), 200) - md.altura_de_brancas(
            fracao_de_vantagem(500, None), 200
        )
        self.assertGreater(do_zero_a_um, de_cinco_a_dez)

    def test_o_mate_enche_a_barra_e_pinta_a_faixa_de_quem_mateia(self) -> None:
        """**Cor própria e não barra cheia**: a barra cheia já quer dizer +8. O que separa "está
        ganho" de "acaba em três lances" é a cor, e é o que o Lichess faz."""
        self.assertEqual(200, md.altura_de_brancas(fracao_de_vantagem(None, 3), 200))
        self.assertEqual(md.PAPEL_DE_MATE, md.papel_do_lado(brancas=True, mate_em=3))
        self.assertEqual(md.PAPEL_DE_PRETAS, md.papel_do_lado(brancas=False, mate_em=3))
        self.assertEqual(md.PAPEL_DE_MATE, md.papel_do_lado(brancas=False, mate_em=-2))

    def test_sem_mate_cada_lado_fica_com_a_cor_dele(self) -> None:
        self.assertEqual(md.PAPEL_DE_BRANCAS, md.papel_do_lado(brancas=True, mate_em=None))
        self.assertEqual(md.PAPEL_DE_PRETAS, md.papel_do_lado(brancas=False, mate_em=None))

    def test_as_cores_da_barra_sao_a_tinta_das_pecas_e_nao_do_tema(self) -> None:
        """Uma faixa "das brancas" que escurecesse junto com a janela deixaria de dizer isso --
        é o mesmo argumento que `tokens.GLIFO_CLARO` já carrega para a peça desenhada."""
        self.assertEqual(tokens.GLIFO_CLARO, md.PAPEL_DE_BRANCAS)
        self.assertEqual(tokens.GLIFO_ESCURO, md.PAPEL_DE_PRETAS)

    def test_barra_sem_altura_nao_desenha_faixa(self) -> None:
        self.assertEqual(0, md.altura_de_brancas(1.0, 0))


class LinhasTests(unittest.TestCase):
    """As linhas do MultiPV, numeradas a partir do lance corrente (S-529)."""

    def _avaliacao(self, cp: int, *lances: str) -> Evaluation:
        return Evaluation(score_cp=cp, mate_in=None, best_move=None, pv_san=lances, depth=18)

    def test_a_variante_sai_numerada_a_partir_do_lance_corrente(self) -> None:
        """Sem o número, comparar a linha do motor com a linha da lista de lances obriga a contar
        nos dedos onde ela começa."""
        self.assertEqual(
            "12. Ba4 Nf6 13. O-O", md.variante_numerada(("Ba4", "Nf6", "O-O"), numero=12, brancas=True)
        )

    def test_com_as_pretas_a_jogar_a_reticencia_aparece_uma_vez(self) -> None:
        self.assertEqual(
            "12... Nf6 13. Nc3 Bb4", md.variante_numerada(("Nf6", "Nc3", "Bb4"), numero=12, brancas=False)
        )

    def test_cada_linha_leva_indice_avaliacao_e_profundidade(self) -> None:
        linhas = md.linhas_do_motor(
            [self._avaliacao(35, "e4", "e5"), self._avaliacao(20, "d4", "d5")],
            numero_do_lance=1,
            brancas_jogam=True,
        )
        self.assertEqual((1, 2), tuple(linha.indice for linha in linhas))
        self.assertEqual("+0,35", linhas[0].display)
        self.assertEqual(18, linhas[0].profundidade)
        self.assertEqual("+0,35  1. e4 e5", linhas[0].texto())

    def test_a_linha_sem_lance_nenhum_nao_vira_linha(self) -> None:
        """Mate ou afogamento: um número apontando para variante nenhuma seria pior que nada."""
        self.assertEqual((), md.linhas_do_motor([self._avaliacao(0)]))
        self.assertEqual((), md.linhas_do_motor(None))


class DesempenhoTests(unittest.TestCase):
    """Profundidade e nós por segundo, que é o que diz se dá para confiar (S-529)."""

    def test_a_frase_traz_os_tres_numeros_em_pt_br(self) -> None:
        frase = md.frase_de_desempenho(profundidade=22, nos=3_100_000, nos_por_segundo=1_400_000)
        self.assertIn("profundidade 22", frase)
        self.assertIn("1,4 MN/s", frase)
        self.assertIn("3,1 M nós", frase)

    def test_o_que_o_motor_nao_relatou_nao_aparece(self) -> None:
        """Zero é "o motor não disse", e alguns só dizem no fim da busca -- um "0 N/s" na tela
        seria a interface afirmando o que ela não sabe."""
        self.assertEqual("profundidade 12", md.frase_de_desempenho(profundidade=12, nos=0, nos_por_segundo=0))
        self.assertEqual("", md.frase_de_desempenho(profundidade=0, nos=0, nos_por_segundo=0))

    def test_o_numero_curto_usa_virgula_decimal(self) -> None:
        self.assertEqual("1,4 M", md.numero_curto(1_400_000))
        self.assertEqual("820 k", md.numero_curto(820_000))
        self.assertEqual("999", md.numero_curto(999))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
