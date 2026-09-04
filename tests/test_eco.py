"""A tabela ECO embutida e as duas classificações (S-534).

O que se afirma aqui é o que a tabela **promete**: que ela é a classificação padrão de A00 a E99,
que a linha canônica de cada código é legal, que o código mais profundo vence, e que os dois
caminhos -- por posição e por ordem de lances -- concordam quando não há transposição e divergem
exatamente onde a documentação diz que divergem.

O custo entra como teste porque ele é o critério de aceite do item: a classificação sem header
roda dez milhões de vezes na passada do índice, e um `push_san` por lance ali seriam horas.
"""

from __future__ import annotations

import time
import unittest

import chess

from chess_diagram_ocr import eco


class TabelaTests(unittest.TestCase):
    """A tabela é dado, e dado errado não dá erro -- ele responde outra coisa."""

    def test_a_tabela_cobre_as_cinco_letras_de_a00_a_e99(self) -> None:
        """Uma tabela com buracos classifica a partida no código anterior, sem dizer que faltou."""
        codigos = {abertura.codigo for abertura in eco.tabela()}
        self.assertEqual(500, len(codigos), "a classificação padrão tem 500 códigos")
        for letra in "ABCDE":
            for numero in range(100):
                with self.subTest(codigo=f"{letra}{numero:02d}"):
                    self.assertIn(f"{letra}{numero:02d}", codigos)

    def test_toda_linha_da_tabela_e_legal_desde_a_posicao_inicial(self) -> None:
        """Um lance ilegal numa linha não levanta: `classificar` para ali e o código some.

        `_por_posicao` reproduz cada linha uma vez e usa `push_san`, que **levanta** -- então um
        erro de digitação na tabela quebraria o programa em vez de dar código errado. Aqui ele é
        achado com o nome da linha, e não com um traceback dentro de um `refresh`.
        """
        quebradas: list[str] = []
        for abertura in eco.tabela():
            tabuleiro = chess.Board()
            for lance in abertura.lances:
                try:
                    tabuleiro.push_san(lance)
                except ValueError:
                    quebradas.append(f"{abertura.codigo} {abertura.nome}: {lance}")
                    break
        self.assertEqual([], quebradas)

    def test_todo_codigo_tem_nome_e_nenhum_nome_e_vazio(self) -> None:
        for abertura in eco.tabela():
            with self.subTest(codigo=abertura.codigo):
                self.assertTrue(abertura.nome.strip())
                self.assertTrue(abertura.lances, "linha sem lance nenhum não define código")

    def test_o_nome_do_codigo_e_o_da_primeira_linha_dele(self) -> None:
        """A00 tem catorze linhas e um nome. Se fosse a última, `1.g3` renomearia a família."""
        self.assertEqual("Uncommon Opening", eco.nome("A00"))
        self.assertEqual("Sicilian, Najdorf", eco.nome("B90"))
        self.assertEqual("", eco.nome("Z99"), "código que a tabela não tem não ganha nome inventado")


class ClassificarTests(unittest.TestCase):
    """Por posição: a que a sala usa, e a que reconhece transposição."""

    def _tabuleiro(self, *sans: str) -> chess.Board:
        tabuleiro = chess.Board()
        for san in sans:
            tabuleiro.push_san(san)
        return tabuleiro

    def test_o_codigo_mais_profundo_vence(self) -> None:
        """A Najdorf passa por B20, B27, B50, B54, B56 e para em B90: o que vale é a linha mais
        longa que a partida alcançou, e não a primeira nem a última posição casada."""
        najdorf = ("e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6")
        abertura = eco.classificar(najdorf)
        assert abertura is not None
        self.assertEqual("B90", abertura.codigo)

    def test_a_transposicao_chega_ao_mesmo_codigo(self) -> None:
        """`1.Nf3 d5 2.d4 Nf6 3.c4 e6` é a mesma **posição** de `1.d4 Nf6 2.c4 e6 3.Nf3`.

        É a razão de haver duas classificações: quem casa por posição vê a igualdade, e quem casa
        por ordem de lances não vê -- e a sala, que abre uma partida por vez, pode pagar a primeira.
        """
        direta = eco.classificar(("d4", "Nf6", "c4", "e6", "Nf3"))
        transposta = eco.classificar(("Nf3", "Nf6", "c4", "e6", "d4"))
        assert direta is not None and transposta is not None
        self.assertEqual("E10", direta.codigo)
        self.assertEqual(direta.codigo, transposta.codigo)

    def test_a_ordem_dos_lances_nao_ve_a_transposicao(self) -> None:
        """O outro lado da moeda, medido em vez de suposto: é o que o índice aceita perder.

        Pela ordem, `1.Nf3 Nf6` para em A05 -- a árvore não tem `2.c4` abaixo dele --, e a mesma
        partida classificada por posição chega a E10. É o preço de ~5 µs contra ~1 ms."""
        direta = eco.classificar_lances(["d4", "Nf6", "c4", "e6", "Nf3"])
        transposta = eco.classificar_lances(["Nf3", "Nf6", "c4", "e6", "d4"])
        assert direta is not None and transposta is not None
        self.assertEqual("E10", direta.codigo)
        self.assertEqual("A05", transposta.codigo)

    def test_toda_primeira_jogada_legal_tem_codigo(self) -> None:
        """As vinte estão na tabela, e as catorze menos jogadas em A00 -- é a classificação padrão.

        O teste existe porque a consequência não é óbvia: **nenhuma** partida que comece na posição
        inicial sai sem código, e um `None` de `classificar` significa sempre outra coisa (a posição
        montada de um `[FEN]`), que é o que o teste abaixo afirma.
        """
        tabuleiro = chess.Board()
        for lance in tabuleiro.legal_moves:
            san = tabuleiro.san(lance)
            with self.subTest(lance=san):
                self.assertIsNotNone(eco.classificar((san,)), f"{san} sem código")
                self.assertIsNotNone(eco.classificar_lances([san]), f"{san} sem código pela ordem")

    def test_sem_lance_nenhum_nao_ha_abertura(self) -> None:
        """`None` e não "A00": dizer um código sobre o que a tabela não conhece é o número
        enganoso que a S-135 tirou deste projeto."""
        self.assertIsNone(eco.classificar(()))
        self.assertIsNone(eco.classificar_lances([]))
        self.assertIsNone(eco.classificar(("Qz9",)), "primeiro lance ilegal não classifica nada")

    def test_um_lance_ilegal_encerra_a_leitura_em_vez_de_derrubar(self) -> None:
        """A base tem 10,5 milhões de partidas, e algumas trazem notação que o `python-chess`
        recusa (S-85). Perder o resto da partida é melhor que perder a passada."""
        abertura = eco.classificar(("e4", "c5", "Nf3", "Qz9", "d4"))
        assert abertura is not None
        self.assertEqual("B27", abertura.codigo)

    def test_o_tabuleiro_e_a_sequencia_dao_o_mesmo_codigo(self) -> None:
        """A sala passa um `chess.Board`; o teste da tabela passa a sequência. Um caminho que
        divergisse do outro faria a frase sob o tabuleiro discordar do índice."""
        lances = ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6")
        pela_sequencia = eco.classificar(lances)
        pelo_tabuleiro = eco.classificar(self._tabuleiro(*lances))
        assert pela_sequencia is not None and pelo_tabuleiro is not None
        self.assertEqual(pela_sequencia.codigo, pelo_tabuleiro.codigo)

    def test_o_tabuleiro_montado_de_uma_fen_nao_inventa_abertura(self) -> None:
        """Um estudo de final montado de uma FEN não tem abertura: a pilha de lances é vazia e a
        posição não está na tabela. É o caso da `Endgame_Study_Database` inteira."""
        tabuleiro = chess.Board("8/8/8/8/8/8/4K3/4k3 w - - 0 1")
        self.assertIsNone(eco.classificar(tabuleiro))
        self.assertEqual("", eco.frase_do_tabuleiro(tabuleiro))


class HeaderEFraseTests(unittest.TestCase):
    """O header vence, e a frase é a mesma nos dois lugares que a mostram."""

    def test_a_sublinha_do_codigo_e_cortada(self) -> None:
        """Algumas bases escrevem `C47d`; a unidade da classificação são os três caracteres."""
        self.assertEqual("C47", eco.codigo_do_header("C47d"))
        self.assertEqual("B90", eco.codigo_do_header(" b90 "))
        self.assertEqual("", eco.codigo_do_header("?"))
        self.assertEqual("", eco.codigo_do_header(""))

    def test_o_header_vence_a_tabela(self) -> None:
        """É a classificação que quem publicou a partida escolheu, e a tabela embutida pode
        discordar dela numa transposição rara."""
        tabuleiro = chess.Board()
        for san in ("e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"):
            tabuleiro.push_san(san)
        self.assertEqual("ECO B90 · Sicilian, Najdorf", eco.frase_do_tabuleiro(tabuleiro))
        self.assertEqual("ECO B33 · Sicilian, Sveshnikov", eco.frase_do_tabuleiro(tabuleiro, "B33"))

    def test_a_frase_traz_o_codigo_antes_do_nome(self) -> None:
        """O código é o que se compara e o que se procura; o nome é a legenda dele."""
        self.assertEqual("ECO B33 · Sicilian, Sveshnikov", eco.frase("B33"))
        self.assertEqual("", eco.frase(""))
        self.assertEqual("", eco.frase("Z99"), "o que não é código ECO não vira frase")
        self.assertEqual(eco.SEPARADOR, " · ", "o separador do projeto, e não uma vírgula")


class MovetextTests(unittest.TestCase):
    """A tokenização barata que o índice paga: uma expressão regular, e nenhum tabuleiro."""

    def test_numeros_resultado_e_nags_ficam_de_fora(self) -> None:
        texto = "1. e4 c5 2. Nf3 $14 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 1-0"
        self.assertEqual(
            ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"],
            eco.lances_do_movetext(texto),
        )

    def test_o_lance_do_comentario_nao_conta(self) -> None:
        """`{Better was Bf4}` tem um `Bf4` que não foi jogado: contá-lo classificaria a partida
        por um lance que não está nela."""
        self.assertEqual(["e4", "e5", "Nf3"], eco.lances_do_movetext("1. e4 e5 {Better was Bf4} 2. Nf3"))

    def test_o_meio_lance_das_pretas_com_reticencias_e_lido(self) -> None:
        """`4... Nf6` é como a base escreve o lance das pretas depois de um comentário."""
        self.assertEqual(["Nf6", "Nc3"], eco.lances_do_movetext("4... Nf6 5. Nc3"))

    def test_o_empate_com_barras_nao_vira_lance(self) -> None:
        self.assertEqual(["e4", "e5"], eco.lances_do_movetext("1. e4 e5 1/2-1/2"))

    def test_o_roque_e_lance(self) -> None:
        lances = eco.lances_do_movetext("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7")
        self.assertIn("O-O", lances)

    def test_a_leitura_para_no_maximo_pedido(self) -> None:
        """`LANCES_EXAMINADOS` é o teto: a linha mais longa da tabela tem 26 meios-lances, e cada
        token a mais é custo sem resposta em dez milhões de partidas."""
        texto = " ".join(f"{n}. e4 e5" for n in range(1, 40))
        self.assertEqual(eco.LANCES_EXAMINADOS, len(eco.lances_do_movetext(texto)))
        self.assertEqual(3, len(eco.lances_do_movetext(texto, maximo=3)))


class CustoTests(unittest.TestCase):
    """O orçamento da S-534: a classificação sem header roda uma vez por partida indexada."""

    LANCES = ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "Be3", "e5"]
    TETO_POR_PARTIDA_MS = 0.05
    """Cinquenta microssegundos por partida. Medido em 2026-09-04: ~5 µs por
    `classificar_lances`, e ~1 ms por `classificar` -- **duzentas vezes mais**. O teto é dez vezes
    o medido, para a guarda não virar medidor de máquina ocupada; o que ela impede é a árvore de
    prefixos ser trocada por um replay, que é o que custaria +1 ms × 10 milhões = quase três horas
    sobre os nove minutos da gigabase.
    """

    def test_a_classificacao_por_lance_custa_microssegundos(self) -> None:
        eco._arvore()  # a árvore é montada uma vez; o que se mede é a consulta
        inicio = time.perf_counter()
        for _ in range(2000):
            eco.classificar_lances(self.LANCES)
        por_partida = (time.perf_counter() - inicio) * 1000 / 2000
        self.assertLess(por_partida, self.TETO_POR_PARTIDA_MS, f"{por_partida:.4f} ms por partida")

    def test_a_classificacao_por_posicao_custa_muito_mais_e_e_por_isso_que_ha_duas(self) -> None:
        """Sem este número, "há duas classificações" parece redundância em vez de decisão."""
        eco._por_posicao()
        inicio = time.perf_counter()
        for _ in range(200):
            eco.classificar(self.LANCES)
        por_posicao = (time.perf_counter() - inicio) * 1000 / 200
        inicio = time.perf_counter()
        for _ in range(200):
            eco.classificar_lances(self.LANCES)
        por_lance = (time.perf_counter() - inicio) * 1000 / 200
        self.assertGreater(por_posicao, 10 * por_lance, "as duas custam o mesmo: uma delas sobra")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TransposicaoTests(unittest.TestCase):
    """A promessa que a primeira rodada não cumpriu: a mesma posição, o mesmo código (S-534, r2).

    O crítico mediu `1.Nf3 d5 2.d4 Nf6 3.c4` dando **D02** e `1.d4 d5 2.c4 Nf6 3.Nf3` dando
    **D06** -- mesmas peças, mesma vez, mesmos roques. A causa não era a posição final: era a
    regra. `classificar` guardava a linha **mais longa da tabela** entre todas as que a partida
    tocou, e cada caminho tinha passado por uma intermediária diferente. Pela posição final os
    dois caem no mesmo lugar, que é o que a classificação padrão faz.
    """

    PARES = {
        "gambito da dama pela Reti": ("Nf3 d5 d4 Nf6 c4", "d4 d5 c4 Nf6 Nf3"),
        "índia da dama": ("Nf3 Nf6 c4 e6 d4 b6", "d4 Nf6 c4 e6 Nf3 b6"),
        "índia do rei pela inglesa": ("c4 Nf6 Nc3 g6 d4 Bg7 e4 d6", "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6"),
        "siciliana pela Reti": ("Nf3 c5 e4", "e4 c5 Nf3"),
        "inglesa que vira gambito da dama": ("c4 e6 d4 d5", "d4 d5 c4 e6"),
        "Nimzo pela Reti": ("Nf3 Nf6 c4 e6 Nc3 Bb4 d4", "d4 Nf6 c4 e6 Nc3 Bb4 Nf3"),
    }

    def test_a_mesma_posicao_por_dois_caminhos_recebe_o_mesmo_codigo(self) -> None:
        for rotulo, (um, outro) in self.PARES.items():
            with self.subTest(par=rotulo):
                a, b = chess.Board(), chess.Board()
                for lance in um.split():
                    a.push_san(lance)
                for lance in outro.split():
                    b.push_san(lance)
                self.assertEqual(
                    (a.board_fen(), a.turn, a.castling_rights),
                    (b.board_fen(), b.turn, b.castling_rights),
                    "o par do teste não chega à mesma posição, e não prova nada",
                )
                primeiro, segundo = eco.classificar(um.split()), eco.classificar(outro.split())
                self.assertIsNotNone(primeiro)
                self.assertIsNotNone(segundo)
                assert primeiro is not None and segundo is not None
                self.assertEqual(primeiro.codigo, segundo.codigo)

    def test_a_classificacao_e_da_posicao_mais_tardia_e_nao_da_linha_mais_longa(self) -> None:
        """A regra em uma frase, sobre um caso em que as duas discordam.

        `1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Bg5 e6 7.f4` passa pela Najdorf (B90,
        dez meios-lances na tabela) e chega à B96 (catorze). A regra da linha mais longa daria
        B96 aqui e daria a errada no dia em que a partida voltasse para uma linha curta -- a
        regra da posição mais tardia dá B96 **porque é onde a partida está**.
        """
        lances = "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Bg5 e6 f4".split()
        achada = eco.classificar(lances)
        assert achada is not None
        self.assertEqual("B96", achada.codigo)

    def test_a_linha_mais_longa_da_tabela_e_alcancavel(self) -> None:
        """`LANCES_EXAMINADOS` era 24 e a linha mais longa tem 28: C99 nunca casava.

        As 52 partidas C99 da amostra de 2026-09-04 erraram **todas**, e não por falta de linha:
        por um teto que cortava a leitura antes dela. Um teto abaixo da tabela é uma tabela menor
        do que ela diz ser.
        """
        mais_longa = max(eco.tabela(), key=lambda abertura: abertura.profundidade)
        self.assertLessEqual(mais_longa.profundidade, eco.LANCES_EXAMINADOS)
        for codigo in ("C98", "C99", "D68", "D69", "D89"):
            with self.subTest(codigo=codigo):
                linha = next(a for a in eco.tabela() if a.codigo == codigo)
                achada = eco.classificar(linha.lances)
                assert achada is not None
                self.assertEqual(codigo, achada.codigo)


class NomeDaLinhaTests(unittest.TestCase):
    """O nome mostrado é o da linha, e não o da família (S-534, r2).

    `nome(codigo)` é a legenda da família e ela **repete**: *Ruy Lopez* nomeia nove códigos,
    *English* treze, *Sicilian* doze. Sob um tabuleiro que está na Berlim aberta, dizer
    `ECO C67 · Ruy Lopez` é dizer o que já se via.
    """

    def _tabuleiro(self, *sans: str) -> chess.Board:
        tabuleiro = chess.Board()
        for san in sans:
            tabuleiro.push_san(san)
        return tabuleiro

    def test_a_frase_da_sala_traz_o_nome_da_linha_casada(self) -> None:
        berlim = self._tabuleiro("e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6", "O-O", "Nxe4", "d4")
        frase = eco.frase_do_tabuleiro(berlim)
        self.assertTrue(frase.startswith("ECO C67"), frase)
        self.assertIn("Berlin", frase)
        self.assertNotEqual(frase, eco.frase("C67"), "a legenda da família não distingue o C67")

    def test_com_header_que_concorda_a_legenda_e_a_da_linha(self) -> None:
        berlim = self._tabuleiro("e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6", "O-O", "Nxe4", "d4")
        self.assertEqual(eco.frase_do_tabuleiro(berlim), eco.frase_do_tabuleiro(berlim, "C67"))

    def test_com_header_que_discorda_o_codigo_e_do_header_e_a_legenda_e_da_familia(self) -> None:
        """Afirmar o nome de uma linha que a partida não percorreu é pior que a legenda genérica."""
        berlim = self._tabuleiro("e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6", "O-O", "Nxe4", "d4")
        self.assertEqual("ECO C65" + eco.SEPARADOR + eco.nome("C65"), eco.frase_do_tabuleiro(berlim, "C65"))

    def test_sem_posicao_conhecida_o_header_ainda_responde(self) -> None:
        montado = chess.Board("8/8/8/8/8/5k2/6p1/6K1 w - - 0 1")
        self.assertEqual(eco.frase("B90"), eco.frase_do_tabuleiro(montado, "B90"))
        self.assertEqual("", eco.frase_do_tabuleiro(montado))

    def test_a_frase_da_abertura_poe_o_codigo_antes_do_nome(self) -> None:
        abertura = eco.Abertura("Z99", "Nome Inventado", ("e4",))
        self.assertEqual("ECO Z99 · Nome Inventado", eco.frase_da_abertura(abertura))
