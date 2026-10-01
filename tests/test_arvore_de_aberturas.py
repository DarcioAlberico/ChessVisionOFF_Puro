"""A árvore de aberturas: o que a passada grava, o que a consulta responde, e os quatro estados (S-535).

O que a tabela **mostra** está em `tests/test_ui_arvore_de_aberturas.py`; a janela, em
`tests/test_qt_arvore_de_aberturas.py`. Aqui é o arquivo: a chave, a soma, a profundidade e o que
a árvore se recusa a responder.
"""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

import chess

from chess_diagram_ocr import arvore_de_aberturas as arv

CABECALHO = (
    '[Event "Teste"]\n[Date "{data}"]\n[White "{branco}"]\n[Black "{preto}"]\n'
    '[Result "{resultado}"]\n[WhiteElo "{welo}"]\n[BlackElo "{belo}"]\n\n'
)


def partida(
    lances: str,
    *,
    data: str = "2020.01.01",
    resultado: str = "1-0",
    welo: str = "2600",
    belo: str = "2400",
    branco: str = "A, A",
    preto: str = "B, B",
) -> str:
    return (
        CABECALHO.format(data=data, branco=branco, preto=preto, resultado=resultado, welo=welo, belo=belo)
        + lances
        + "\n\n"
    )


class ChaveTests(unittest.TestCase):
    """A chave é a colocação **e a vez**, e ela não pode depender do processo."""

    def test_a_vez_faz_parte_da_chave(self) -> None:
        """Sem a vez, a mesma colocação com brancas e com pretas a jogar somaria os dois nós -- e
        os lances legais de um são ilegais no outro."""
        colocacao = chess.Board().board_fen()
        self.assertNotEqual(arv.chave_da_posicao(colocacao, "w"), arv.chave_da_posicao(colocacao, "b"))

    def test_a_chave_nao_e_o_hash_do_python(self) -> None:
        """O `hash()` é aleatorizado por processo desde a 3.3, e uma árvore gravada hoje não seria
        consultável amanhã -- em silêncio, respondendo "nenhum lance". O valor é fixo e escrito
        aqui: se ele mudar, todo arquivo gravado antes deixa de responder."""
        self.assertEqual(115_815_009_994_539_115, arv.chave_da_posicao("8/8/8/8/8/8/8/8", "w"))
        self.assertEqual(
            arv.chave_da_posicao("8/8/8/8/8/8/8/8", "w"), arv.chave_da_posicao("8/8/8/8/8/8/8/8", "w")
        )


class ConstruirTests(unittest.TestCase):
    """A passada sobre um PGN pequeno, com o mesmo código que lê a gigabase."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.arvore = self.raiz / "arvore.sqlite"

    def _construir(self, texto: str, **extras: object) -> arv.Construcao:
        self.base.write_text(texto, encoding="utf-8")
        return arv.construir(self.base, self.arvore, workers=1, **extras)  # type: ignore[arg-type]

    def _raiz(self) -> arv.Arvore:
        return arv.consultar(chess.Board().board_fen(), "w", ply=0, path=self.arvore)

    def test_cada_lance_da_posicao_vira_um_ramo_com_a_contagem(self) -> None:
        texto = partida("1. e4 e5 2. Nf3") * 3 + partida("1. d4 d5") * 2
        self._construir(texto)
        resposta = self._raiz()
        self.assertEqual(arv.ACHOU, resposta.estado)
        self.assertEqual({"e4": 3, "d4": 2}, {ramo.lance: ramo.partidas for ramo in resposta.ramos})
        self.assertEqual(5, resposta.partidas)

    def test_os_tres_resultados_sao_contados_e_o_asterisco_nao_e_nenhum(self) -> None:
        """`*` é partida sem resultado, e somá-la a empate inventaria meio ponto. `partidas`
        conta as cinco; `decididas`, as quatro que terminaram."""
        texto = (
            partida("1. e4", resultado="1-0")
            + partida("1. e4", resultado="1-0")
            + partida("1. e4", resultado="1/2-1/2")
            + partida("1. e4", resultado="0-1")
            + partida("1. e4", resultado="*")
        )
        self._construir(texto)
        (ramo,) = self._raiz().ramos
        self.assertEqual((5, 2, 1, 1), (ramo.partidas, ramo.brancas, ramo.empates, ramo.pretas))
        self.assertEqual(4, ramo.decididas)

    def test_o_elo_e_a_media_dos_dois_e_so_de_quem_tem_os_dois(self) -> None:
        """A média dos dois jogadores, e não o menor: a coluna responde "quem joga este lance?".
        Partida sem um dos Elos fica fora do denominador -- ver `_elo_medio`."""
        texto = (
            partida("1. e4", welo="2600", belo="2400")
            + partida("1. e4", welo="2700", belo="2500")
            + partida("1. e4", welo="", belo="2500")
        )
        self._construir(texto)
        (ramo,) = self._raiz().ramos
        self.assertEqual((2500 + 2600, 2), (ramo.soma_elo, ramo.com_elo))

    def test_o_ano_traz_media_e_faixa_e_a_partida_sem_data_fica_de_fora(self) -> None:
        texto = (
            partida("1. e4", data="1990.05.05")
            + partida("1. e4", data="2020.01.01")
            + partida("1. e4", data="????.??.??")
        )
        self._construir(texto)
        (ramo,) = self._raiz().ramos
        self.assertEqual((3, 2, 1990 + 2020, 1990, 2020), (ramo.partidas, ramo.com_ano, ramo.soma_ano, ramo.ano_min, ramo.ano_max))

    def test_o_ano_fora_da_faixa_do_formulario_nao_entra(self) -> None:
        """Medido na gigabase inteira: sem esta guarda a coluna Ano da raiz saía `2005 (2–2026)`.

        A base tem partidas com `[Date "0002.??.??"]`, e um `2` na ponta de uma faixa de anos é um
        número que ninguém mediu. A régua é a que o formulário de busca já declara
        (`ui/busca_de_partidas.ANO_MINIMO`), e não uma segunda escrita aqui.
        """
        texto = partida("1. e4", data="0002.01.01") + partida("1. e4", data="2020.01.01")
        self._construir(texto)
        (ramo,) = self._raiz().ramos
        self.assertEqual((2, 1, 2020, 2020), (ramo.partidas, ramo.com_ano, ramo.ano_min, ramo.ano_max))

    def test_o_Elo_acima_do_teto_nao_entra(self) -> None:
        """`ELO_MAXIMO` é 4000, acima de qualquer rating publicado -- a mesma régua do formulário."""
        texto = partida("1. e4", welo="27000", belo="2500") + partida("1. e4", welo="2600", belo="2400")
        self._construir(texto)
        (ramo,) = self._raiz().ramos
        self.assertEqual((1, 2500), (ramo.com_elo, ramo.soma_elo))

    def test_a_partida_montada_de_uma_FEN_nao_entra(self) -> None:
        """Uma composição não tem abertura: os lances dela não saem da posição inicial, e contá-los
        na árvore poria a solução de um estudo entre as continuações de `1.e4`."""
        montada = (
            '[Event "Estudo"]\n[Result "1-0"]\n[FEN "8/8/8/8/8/8/6k1/R5K1 w - - 0 1"]\n\n1. Ra2+ 1-0\n\n'
        )
        self._construir(partida("1. e4") + montada)
        (ramo,) = self._raiz().ramos
        self.assertEqual(1, ramo.partidas)

    def test_o_lance_desconhecido_encerra_a_partida(self) -> None:
        """`--` é lance nulo para o `python-chess`: a posição fica igual e só a vez troca, e dois
        deles voltam à posição de partida. Medido na gigabase: 7 partidas de 27.395 contavam duas
        vezes na raiz por causa disso."""
        self._construir(partida("1. e4 e5 2. -- -- 3. Nf3"))
        raiz = self._raiz()
        self.assertEqual(1, raiz.partidas, "a partida contou duas vezes na raiz")
        depois = chess.Board()
        for san in ("e4", "e5"):
            depois.push_san(san)
        seguinte = arv.consultar(depois.board_fen(), "w", ply=2, path=self.arvore)
        self.assertEqual(arv.SEM_PARTIDA, seguinte.estado, "o replay seguiu depois do lance nulo")

    def test_a_variante_do_movetext_nao_vira_linha_principal(self) -> None:
        """Sem tirar os parênteses, `1. e4 (1. d4 d5) e5` seria lido como `e4 d4 d5 e5`, e o replay
        sairia da linha no primeiro parêntese -- é a medição de `games_db._sem_variantes`."""
        self._construir(partida("1. e4 (1. d4 d5) 1... e5 2. Nf3"))
        self.assertEqual({"e4"}, {ramo.lance for ramo in self._raiz().ramos})

    def test_a_profundidade_corta_a_partida_e_fica_gravada(self) -> None:
        self._construir(partida("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"), profundidade=4)
        self.assertEqual("4", arv.resumo_do_arquivo(self.arvore)["profundidade"])
        tabuleiro = chess.Board()
        for san in ("e4", "e5", "Nf3", "Nc6"):
            tabuleiro.push_san(san)
        # O quarto meio-lance foi gravado; o quinto (`Bb5`) nao, porque a posicao dele e o ply 4.
        self.assertEqual(
            arv.FUNDO_DEMAIS, arv.consultar(tabuleiro.board_fen(), "w", ply=4, path=self.arvore).estado
        )

    def test_a_posicao_alem_da_profundidade_nao_e_nenhuma_partida(self) -> None:
        """É a distinção da S-135 que `estudo_partidas` já escreveu em quatro estados: dizer
        "nenhum lance foi jogado daqui" sobre o que ninguém indexou é um número enganoso."""
        self._construir(partida("1. e4 e5"), profundidade=2)
        resposta = arv.consultar(chess.Board().board_fen(), "w", ply=40, path=self.arvore)
        self.assertEqual(arv.FUNDO_DEMAIS, resposta.estado)
        self.assertEqual(2, resposta.profundidade)

    def test_a_posicao_dentro_da_profundidade_e_sem_partida_e_sem_partida(self) -> None:
        self._construir(partida("1. e4 e5"))
        tabuleiro = chess.Board()
        tabuleiro.push_san("h4")
        resposta = arv.consultar(tabuleiro.board_fen(), "b", ply=1, path=self.arvore)
        self.assertEqual(arv.SEM_PARTIDA, resposta.estado)

    def test_sem_arquivo_a_resposta_e_sem_arvore(self) -> None:
        resposta = arv.consultar(chess.Board().board_fen(), "w", ply=0, path=self.raiz / "nao_existe.sqlite")
        self.assertEqual(arv.SEM_ARVORE, resposta.estado)

    def test_uma_arvore_de_outra_base_e_recusada(self) -> None:
        """As contagens de uma base não valem para outra -- a mesma guarda de `games_cache`, e pelo
        mesmo motivo: uma percentagem de outra base parece uma percentagem."""
        self._construir(partida("1. e4"))
        outra = self.raiz / "outra.pgn"
        outra.write_text(partida("1. d4"), encoding="utf-8")
        resposta = arv.consultar(
            chess.Board().board_fen(), "w", ply=0, path=self.arvore, bases=[self.base, outra]
        )
        self.assertEqual(arv.SEM_ARVORE, resposta.estado)
        self.assertEqual(arv.ACHOU, arv.consultar(chess.Board().board_fen(), "w", ply=0, path=self.arvore, bases=[self.base]).estado)

    def test_um_formato_anterior_e_recusado(self) -> None:
        self._construir(partida("1. e4"))
        with sqlite3.connect(self.arvore) as conexao:
            conexao.execute("UPDATE meta SET value = '0' WHERE key = 'version'")
        self.assertEqual(arv.SEM_ARVORE, self._raiz().estado)

    def test_a_passada_cancelada_nao_grava_nada(self) -> None:
        """Meia árvore daria percentagem sobre a metade que se leu, e ela pareceria certa: é a
        regra de `games_cache.PositionStore.update`, aqui de novo."""
        cancelar = threading.Event()
        cancelar.set()
        resultado = self._construir(partida("1. e4"), cancel=cancelar)
        self.assertTrue(resultado.cancelada)
        self.assertEqual(0, resultado.ramos)
        self.assertFalse(self.arvore.exists(), "a árvore cancelada foi gravada")

    def test_a_profundidade_zero_e_recusada_na_porta(self) -> None:
        self.base.write_text(partida("1. e4"), encoding="utf-8")
        with self.assertRaises(ValueError):
            arv.construir(self.base, self.arvore, profundidade=0, workers=1)

    def test_o_progresso_conta_pedacos_e_partidas(self) -> None:
        vistos: list[tuple[int, int, int]] = []
        self._construir(partida("1. e4") * 3, progress=lambda *aviso: vistos.append(aviso))
        self.assertTrue(vistos, "a passada não avisou nada")
        self.assertEqual((1, 1, 3), vistos[-1])

    def test_o_resumo_do_arquivo_diz_o_que_ele_e_sem_abri_lo_para_escrita(self) -> None:
        self._construir(partida("1. e4 e5") * 2)
        resumo = arv.resumo_do_arquivo(self.arvore)
        self.assertEqual(str(arv.TREE_VERSION), resumo["version"])
        self.assertEqual("2", resumo["partidas"])
        self.assertGreater(int(resumo["ramos"]), 0)
        self.assertEqual({}, arv.resumo_do_arquivo(self.raiz / "nao_existe.sqlite"))


class VariosProcessosTests(unittest.TestCase):
    """A passada repartida responde o mesmo que a sequencial. É o que a fusão dos parciais faz."""

    def test_o_pedaco_sem_data_nao_zera_a_faixa_de_anos(self) -> None:
        """`min(0, 1902)` é 0, e zero quer dizer "esta linha não tem partida com data".

        **Visto na gigabase inteira**: o ramo `6.d3` da Ruy Lopez fechada saía `2015 (0–2026)`,
        porque um dos dez pedaços não tinha nenhuma partida datada naquele nó e contribuía com
        `ano_min = 0`. A fusão tem de tomar o menor **entre os que existem** -- ver `_MENOR_ANO`.
        """
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            base = raiz / "base.pgn"
            # Datadas na primeira metade do arquivo, sem data na segunda: `chunk_bounds` corta no
            # meio, entao os dois pedacos veem o mesmo `1.e4` com respostas diferentes sobre o ano.
            base.write_text(
                "".join(partida("1. e4 e5", data="1990.01.01") for _ in range(40))
                + "".join(partida("1. e4 e5", data="????.??.??") for _ in range(40)),
                encoding="utf-8",
            )
            alvo = raiz / "arvore.sqlite"
            arv.construir(base, alvo, workers=2)
            (ramo,) = arv.consultar(chess.Board().board_fen(), "w", ply=0, path=alvo).ramos
            self.assertEqual((80, 40, 1990, 1990), (ramo.partidas, ramo.com_ano, ramo.ano_min, ramo.ano_max))

    def test_dois_processos_somam_o_mesmo_que_um(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            base = raiz / "base.pgn"
            base.write_text(
                "".join(partida("1. e4 e5 2. Nf3", data=f"20{10 + i:02d}.01.01") for i in range(40))
                + "".join(partida("1. d4 d5", resultado="0-1") for _ in range(20)),
                encoding="utf-8",
            )
            um, dois = raiz / "um.sqlite", raiz / "dois.sqlite"
            arv.construir(base, um, workers=1)
            arv.construir(base, dois, workers=2)
            colocacao = chess.Board().board_fen()
            sequencial = arv.consultar(colocacao, "w", ply=0, path=um)
            repartida = arv.consultar(colocacao, "w", ply=0, path=dois)
            self.assertEqual(sorted(sequencial.ramos, key=lambda r: r.lance), sorted(repartida.ramos, key=lambda r: r.lance))
            self.assertEqual(60, repartida.partidas)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
