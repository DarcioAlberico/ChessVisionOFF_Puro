"""O estudo em parágrafos de livro (S-542/S-543).

**O que se trava é a paginação**, e não o texto do lance -- esse vem de `ui/estudo_lista.trechos`,
conferido contra o `chess.pgn` em `test_estudo_lista`. Aqui a pergunta é onde a linha corta, o que
recua, e onde o `[%D]` põe o diagrama. O EPUB e o DOCX leem esta lista; um erro aqui sai duas vezes.
"""

from __future__ import annotations

import unittest

import chess

from chess_diagram_ocr import estudo_paragrafos, estudo_saida
from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo

ITALIANA = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"


def _estudo(*, comentario_da_raiz: str = "", pede_diagrama: bool = False) -> Estudo:
    e = Estudo.de_posicao(
        PosicaoDeEstudo(
            placement=ITALIANA, vez="b", lance=4, ancora=Ancora(documento="C:/livros/Secrets.pdf", pagina=142, diagrama=1)
        )
    )
    e.jogo.comment = comentario_da_raiz
    bc5 = e.jogo.add_variation(chess.Move.from_uci("f8c5"))
    bc5.nags.add(5)
    bc5.comment = "a italiana" + (" [%D]" if pede_diagrama else "")
    o_o = bc5.add_variation(chess.Move.from_uci("e1g1"))
    c3 = bc5.add_variation(chess.Move.from_uci("c2c3"))
    c3.comment = "a outra"
    d6 = c3.add_variation(chess.Move.from_uci("d7d6"))
    d6.add_variation(chess.Move.from_uci("d2d4"))
    d6.add_variation(chess.Move.from_uci("d2d3"))
    o_o.add_variation(chess.Move.from_uci("d7d6"))
    return e


def _tipos(estudo: Estudo) -> list[str]:
    return [p.tipo for p in estudo_paragrafos.paragrafos(estudo)]


def _textos(estudo: Estudo, tipo: str) -> list[str]:
    return [p.texto for p in estudo_paragrafos.paragrafos(estudo) if p.tipo == tipo]


class OrdemTests(unittest.TestCase):
    def test_o_livro_comeca_pelo_titulo_e_pelo_diagrama(self) -> None:
        tipos = _tipos(_estudo())
        self.assertEqual(tipos[:2], [estudo_paragrafos.TITULO, estudo_paragrafos.DIAGRAMA])

    def test_o_titulo_e_o_mesmo_de_estudo_saida(self) -> None:
        """Dois títulos para o mesmo estudo seria o EPUB discordando do `.md`."""
        e = _estudo()
        self.assertEqual(estudo_paragrafos.titulo_do_estudo(e), estudo_saida.para_documento(e).corridas[0].texto.strip())

    def test_o_diagrama_da_raiz_e_o_numero_1_e_segue_a_orientacao_do_estudo(self) -> None:
        e = _estudo()
        diagrama = estudo_paragrafos.paragrafos(e)[1]
        self.assertEqual(diagrama.numero, 1)
        self.assertEqual(diagrama.fen, e.raiz.board().fen())
        self.assertEqual(diagrama.virado, e.invertido)

    def test_o_comentario_da_raiz_e_paragrafo_proprio_antes_da_linha(self) -> None:
        tipos = _tipos(_estudo(comentario_da_raiz="uma nota da posição"))
        self.assertEqual(tipos[2], estudo_paragrafos.COMENTARIO_DO_ESTUDO)
        self.assertEqual(_textos(_estudo(comentario_da_raiz="uma nota da posição"), estudo_paragrafos.COMENTARIO_DO_ESTUDO)[0], "uma nota da posição")


class CorteTests(unittest.TestCase):
    def test_o_comentario_da_linha_principal_corta_a_linha(self) -> None:
        tipos = _tipos(_estudo())
        indice = tipos.index(estudo_paragrafos.COMENTARIO_DO_ESTUDO)
        self.assertEqual(tipos[indice - 1], estudo_paragrafos.LANCE)
        self.assertEqual(_textos(_estudo(), estudo_paragrafos.COMENTARIO_DO_ESTUDO), ["a italiana"])

    def test_a_linha_que_continua_traz_o_numero_de_novo(self) -> None:
        lances = _textos(_estudo(), estudo_paragrafos.LANCE)
        self.assertIn("4...Bc5", lances[0])
        self.assertTrue(any(lance.startswith("5.O-O") for lance in lances), lances)

    def test_a_variante_de_primeiro_nivel_e_paragrafo_recuado_sem_parenteses(self) -> None:
        variantes = [p for p in estudo_paragrafos.paragrafos(_estudo()) if p.tipo == estudo_paragrafos.VARIANTE]
        self.assertEqual(len(variantes), 1)
        (c3,) = variantes
        self.assertEqual(c3.nivel, 1)
        self.assertTrue(c3.texto.startswith("5.c3"), c3.texto)
        self.assertNotIn(")", c3.texto.split("(")[0])

    def test_o_comentario_da_variante_fica_dentro_dela(self) -> None:
        c3 = next(v for v in estudo_paragrafos.paragrafos(_estudo()) if v.texto.startswith("5.c3"))
        self.assertIn("a outra", c3.texto)
        self.assertEqual(_textos(_estudo(), estudo_paragrafos.COMENTARIO_DO_ESTUDO), ["a italiana"])

    def test_a_subvariante_fica_entre_parenteses_dentro_da_variante(self) -> None:
        """Recuar quatro níveis empurra a linha para fora da tela do leitor."""
        c3 = next(v for v in estudo_paragrafos.paragrafos(_estudo()) if v.texto.startswith("5.c3"))
        self.assertIn("(6.d3)", c3.texto)
        self.assertNotIn("(", c3.texto.split("(")[0].strip()[-1:])

    def test_nenhum_paragrafo_tem_espaco_duplo_nem_sobra_nas_pontas(self) -> None:
        for p in estudo_paragrafos.paragrafos(_estudo()):
            if p.texto:
                self.assertEqual(p.texto, " ".join(p.texto.split()))


class DiagramaPedidoTests(unittest.TestCase):
    def test_o_comando_D_pede_um_diagrama_depois_do_comentario(self) -> None:
        e = _estudo(pede_diagrama=True)
        paragrafos = estudo_paragrafos.paragrafos(e)
        tipos = [p.tipo for p in paragrafos]
        indice = tipos.index(estudo_paragrafos.COMENTARIO_DO_ESTUDO)
        self.assertEqual(tipos[indice + 1], estudo_paragrafos.DIAGRAMA)
        self.assertEqual(paragrafos[indice + 1].numero, 2)
        self.assertEqual(paragrafos[indice + 1].fen, e.jogo.variations[0].board().fen())

    def test_o_comando_nao_vaza_como_texto(self) -> None:
        for p in estudo_paragrafos.paragrafos(_estudo(pede_diagrama=True)):
            self.assertNotIn("%D", p.texto)

    def test_sem_o_comando_so_ha_o_diagrama_da_raiz(self) -> None:
        self.assertEqual(_tipos(_estudo()).count(estudo_paragrafos.DIAGRAMA), 1)


class ResultadoTests(unittest.TestCase):
    def test_o_asterisco_nao_sai_e_o_resultado_sai(self) -> None:
        e = _estudo()
        self.assertFalse(any("*" in p.texto for p in estudo_paragrafos.paragrafos(e)))
        e.jogo.headers["Result"] = "1-0"
        lances = _textos(e, estudo_paragrafos.LANCE)
        self.assertTrue(lances[-1].endswith("1-0"), lances)

    def test_estudo_sem_lance_tem_titulo_e_diagrama_e_nada_mais(self) -> None:
        vazio = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA))
        self.assertEqual(_tipos(vazio), [estudo_paragrafos.TITULO, estudo_paragrafos.DIAGRAMA])
        self.assertEqual(estudo_paragrafos.titulo_do_estudo(vazio), "Estudo avulso")


RETI = """[Event "Ceske Slovo"]
[Date "1921.??.??"]
[White "Réti, R."]
[Black "?"]
[SetUp "1"]
[FEN "7K/8/k1P5/7p/8/8/8/8 w - - 0 1"]

1. Kg7 $1 {a diagonal do rei} (1. c7 $2 Kb7 $17 {as pretas ganham} (1... Kb6 2. Kg7)) 1... h4 $6 2. Kf6 $14 *
"""
"""O estudo de Réti de 1921, com NAG na linha, NAG na variante, comentário e subvariante -- os
quatro lugares em que o espaço do widget aparecia. Ver `TipografiaTests`."""


class TipografiaTests(unittest.TestCase):
    """A linha impressa, caractere a caractere.

    **O que este arquivo trava e nenhum outro trava.** `estudo_lista.trechos` é tokenizador de lista
    clicável: ele termina todo trecho em espaço para dois itens não se encostarem na tela, e a linha
    crua sai `1. Kg7 ! a diagonal do rei ( 1. c7 ? Kb7 ∓ ... )`. Um livro imprime `1.Kg7!` e
    `(1.c7? Kb7∓ ...)`. Os dois formatos leem esta lista, então a cola é decidida uma vez -- e é aqui
    que se afirma que ela é a do livro, com a string inteira e não por `assertIn`.
    """

    def _linhas(self) -> list[tuple[str, str]]:
        return [(p.tipo, p.texto) for p in estudo_paragrafos.paragrafos(Estudo.de_pgn(RETI))]

    def test_a_linha_de_um_estudo_conhecido_sai_como_o_livro_a_imprime(self) -> None:
        self.assertEqual(
            self._linhas(),
            [
                (estudo_paragrafos.TITULO, "Réti, R., Ceske Slovo, 1921"),
                (estudo_paragrafos.DIAGRAMA, ""),
                (estudo_paragrafos.LANCE, "1.Kg7!"),
                (estudo_paragrafos.COMENTARIO_DO_ESTUDO, "a diagonal do rei"),
                (estudo_paragrafos.VARIANTE, "1.c7? Kb7∓ as pretas ganham (1...Kb6 2.Kg7)"),
                (estudo_paragrafos.LANCE, "1...h4?! 2.Kf6⩲"),
            ],
        )

    def test_nenhum_espaco_do_widget_sobrevive(self) -> None:
        """As quatro formas que o tokenizador produz e que nenhum livro imprime."""
        for _, texto in self._linhas():
            for folga in (" !", " ?", " ⩲", " ∓", "( ", " )"):
                self.assertNotIn(folga, texto, texto)
            self.assertNotRegex(texto, r"\d+\.\s")
            self.assertNotRegex(texto, r"\d+\.\.\.\s")


class TituloTests(unittest.TestCase):
    """Trezentas entradas escritas `Estudo avulso` não são um sumário."""

    def test_sem_ancora_o_titulo_e_o_cabecalho_da_partida(self) -> None:
        self.assertEqual(estudo_paragrafos.titulo_do_estudo(Estudo.de_pgn(RETI)), "Réti, R., Ceske Slovo, 1921")

    def test_a_data_incompleta_do_pgn_entra_pelo_que_ela_tem(self) -> None:
        """`1921.??.??` é o ano de uma composição; `????.??.??` não é data nenhuma."""
        self.assertIn("1921", estudo_paragrafos.titulo_do_estudo(Estudo.de_pgn(RETI)))
        sem_data = Estudo.de_pgn(RETI.replace('[Date "1921.??.??"]', '[Date "????.??.??"]'))
        self.assertEqual(estudo_paragrafos.titulo_do_estudo(sem_data), "Réti, R., Ceske Slovo")

    def test_os_dois_jogadores_saem_separados(self) -> None:
        dois = Estudo.de_pgn(RETI.replace('[Black "?"]', '[Black "Alekhine, A."]'))
        self.assertEqual(estudo_paragrafos.titulo_do_estudo(dois), "Réti, R. × Alekhine, A., Ceske Slovo, 1921")

    def test_sem_jogador_nenhum_o_estudo_e_avulso(self) -> None:
        """`Estudo.de_posicao` grava `Event = "ChessVisionOFF Estudo"` em toda posição criada aqui
        dentro: um livro intitulado com o nome do próprio programa é o mesmo erro que o `dc:creator`
        da primeira rodada."""
        vazio = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA))
        self.assertEqual(estudo_paragrafos.titulo_do_estudo(vazio), "Estudo avulso")

    def test_a_ancora_do_livro_continua_ganhando_do_cabecalho(self) -> None:
        e = Estudo.de_pgn(RETI)
        e.ancora = Ancora(documento="C:/livros/Secrets.pdf", pagina=142, diagrama=1)
        self.assertEqual(estudo_paragrafos.titulo_do_estudo(e), e.ancora.rotulo())


class MarcaDeDiagramaTests(unittest.TestCase):
    def test_o_campo_de_profundidade_do_motor_nao_pede_diagrama(self) -> None:
        """`[%Depth 20]` é o que o Fritz grava ao anotar com motor. Casando por prefixo (`"[%D"`),
        um livro anotado por máquina ganhava um diagrama em cada lance analisado."""
        e = _estudo()
        e.jogo.variations[0].comment = "avaliado [%Depth 20] [%eval 0.31]"
        self.assertEqual(_tipos(e).count(estudo_paragrafos.DIAGRAMA), 1)
        self.assertEqual(estudo_paragrafos.MARCA_DE_DIAGRAMA, "[%D]")

    def test_o_pedido_de_diagrama_inteiro_continua_valendo(self) -> None:
        self.assertEqual(_tipos(_estudo(pede_diagrama=True)).count(estudo_paragrafos.DIAGRAMA), 2)


if __name__ == "__main__":
    unittest.main()
