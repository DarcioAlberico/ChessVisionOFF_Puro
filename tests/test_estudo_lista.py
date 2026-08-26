"""A lista de lances conferida contra o `StringExporter` (S-273).

**A trava é o teste, e é ele que torna o item seguro.** A numeração de variante é a parte que todo
visualizador de PGN erra: o primeiro lance de uma variante imprime o número (com `...` se for das
pretas); dentro dela as pretas não imprimem nada -- **exceto** depois de comentário ou de
subvariante, onde voltam a imprimir `N...`. O plugin que serviu de referência resolve isso com
quatro condicionais aninhadas e ainda assim só cobre profundidade 1.

O `chess.pgn.StringExporter` acerta há anos. Enquanto `texto_de(trechos(e))` for igual ao que ele
produz, não estamos adivinhando -- é a mesma trava que a S-235 usou para o `para_texto()` do
documento rico.
"""

from __future__ import annotations

import unittest

import chess
import chess.pgn

from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo, caminho_de, no_em, trocar_seta
from chess_diagram_ocr.ui import estudo_lista

ITALIANA = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"


def _movetext(jogo: chess.pgn.Game) -> str:
    """O movetext que o `chess.pgn` escreveria. **Um exportador por chamada**: ele acumula."""
    visitante = chess.pgn.StringExporter(headers=False, variations=True, comments=True, columns=None)
    return " ".join(str(jogo.accept(visitante)).split())


def _linha(estudo: Estudo, *lances: str) -> chess.pgn.GameNode:
    no: chess.pgn.GameNode = estudo.jogo
    for uci in lances:
        no = no.add_variation(chess.Move.from_uci(uci))
    return no


class TextoIgualAoExportadorTests(unittest.TestCase):
    def _conferir(self, estudo: Estudo) -> None:
        obtido = " ".join(estudo_lista.texto_de(estudo_lista.trechos(estudo)).split())
        self.assertEqual(obtido, _movetext(estudo.jogo))

    def test_linha_simples(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo())
        _linha(e, "e2e4", "e7e5", "g1f3", "b8c6")
        self._conferir(e)

    def test_variante_das_brancas(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        e4.parent.add_variation(chess.Move.from_uci("d2d4"))
        _linha_de(e4, "e7e5", "g1f3")
        self._conferir(e)

    def test_variante_das_pretas_imprime_reticencia(self) -> None:
        """`1... c5` -- o caso em que o número volta a aparecer porque a variante começa nas pretas."""
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        _linha_de(e4, "e7e5", "g1f3")
        _linha_de(e4, "c7c5", "g1f3")
        self.assertIn("1... c5", estudo_lista.texto_de(estudo_lista.trechos(e)))
        self._conferir(e)

    def test_subvariante_de_terceiro_nivel(self) -> None:
        """A palavra do pedido. O plugin de referência para na profundidade 1; `chess.pgn` não."""
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        c5 = _linha_de(e4, "c7c5")
        nf3 = _linha_de(c5, "g1f3")
        _linha_de(nf3, "d7d6")
        _linha_de(nf3, "b8c6", "d2d4")
        _linha_de(c5, "b1c3")
        _linha_de(e4, "e7e5")
        self._conferir(e)

    def test_comentario_no_meio_da_linha_faz_o_numero_voltar(self) -> None:
        """Depois de um comentário as pretas reimprimem `N...`. É a regra que se erra sozinho."""
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        e4.comment = "o lance mais jogado do mundo"
        _linha_de(e4, "e7e5")
        self.assertIn("1... e5", estudo_lista.texto_de(estudo_lista.trechos(e)))
        self._conferir(e)

    def test_nag_entra_no_texto_como_o_pgn_o_escreve(self) -> None:
        """A lista desenha `!` e o PGN grava `$1`. As duas coisas convivem por causa de `token`."""
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        e4.nags.add(5)
        e4.nags.add(16)
        trechos = estudo_lista.trechos(e)
        simbolos = [t.texto.strip() for t in trechos if t.papel == estudo_lista.NAG]
        self.assertEqual(simbolos, ["!?", "±"])
        self._conferir(e)

    def test_diagrama_com_pretas_a_jogar_e_numero_do_livro(self) -> None:
        """O caso normal desta aba: a posição não é o começo de uma partida."""
        e = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA, vez="b", lance=4))
        bc5 = _linha(e, "f8c5")
        _linha_de(bc5, "e1g1", "e8g8")
        _linha_de(bc5, "c2c3")
        self.assertIn("4... Bc5", estudo_lista.texto_de(estudo_lista.trechos(e)))
        self._conferir(e)

    def test_comentario_com_chave_nao_quebra_o_pgn(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        e4.comment = "isto } fecharia o comentário"
        self._conferir(e)


def _linha_de(no: chess.pgn.GameNode, *lances: str) -> chess.pgn.GameNode:
    for uci in lances:
        no = no.add_variation(chess.Move.from_uci(uci))
    return no


class TrechoTests(unittest.TestCase):
    def test_estudo_sem_lance_tem_so_a_raiz_e_o_resultado(self) -> None:
        trechos = estudo_lista.trechos(Estudo.de_posicao(PosicaoDeEstudo()))
        self.assertEqual([t.papel for t in trechos], [estudo_lista.RAIZ, estudo_lista.RESULTADO])

    def test_a_raiz_diz_se_o_estudo_veio_do_livro(self) -> None:
        """"posição do diagrama" e "posição inicial" são duas coisas, e quem estuda sabe qual é."""
        do_livro = Estudo.de_posicao(
            PosicaoDeEstudo(ancora=Ancora(documento="a.pdf", pagina=3, diagrama=0))
        )
        avulso = Estudo.de_posicao(PosicaoDeEstudo())
        self.assertIn("diagrama", estudo_lista.trechos(do_livro)[0].texto)
        self.assertIn("inicial", estudo_lista.trechos(avulso)[0].texto)

    def test_todo_lance_tem_caminho_que_resolve_no_no(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        _linha_de(e4, "e7e5", "g1f3")
        _linha_de(e4, "c7c5", "b1c3")
        for trecho in estudo_lista.trechos(e):
            if trecho.papel != estudo_lista.LANCE:
                continue
            with self.subTest(lance=trecho.texto.strip()):
                no = no_em(e.jogo, trecho.caminho)
                self.assertIsNotNone(no)
                self.assertEqual(caminho_de(no), trecho.caminho)

    def test_a_subvariante_ganha_nivel_dois(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        # A **ordem de inserção decide qual é a linha principal**: o primeiro filho é a linha, os
        # demais são variantes. Por isso `e5` entra antes de `c5`.
        _linha_de(e4, "e7e5")
        c5 = _linha_de(e4, "c7c5")
        nf3 = _linha_de(c5, "g1f3")
        _linha_de(nf3, "d7d6")
        _linha_de(nf3, "b8c6")
        niveis = {t.texto.strip(): t.nivel for t in estudo_lista.trechos(e) if t.papel == estudo_lista.LANCE}
        self.assertEqual(niveis["e4"], 0)
        self.assertEqual(niveis["e5"], 0)
        self.assertEqual(niveis["c5"], 1)
        self.assertEqual(niveis["Nc6"], 2)

    def test_o_recuo_satura_e_a_numeracao_nao(self) -> None:
        """Um recuo que cresce sem limite empurra a linha para fora da janela; o número, não."""
        fundo = estudo_lista.Trecho("Nf3 ", estudo_lista.LANCE, (), nivel=9)
        self.assertEqual(fundo.recuo, estudo_lista.NIVEL_MAXIMO_DE_RECUO)
        self.assertEqual(fundo.nivel, 9)

    def test_o_comentario_de_setas_nao_aparece_na_lista_mas_esta_no_pgn(self) -> None:
        """`{ [%cal Gf3g5] }` é encanamento: ele existe no arquivo e não tem o que mostrar."""
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        trocar_seta(e4, chess.F3, chess.G5)
        comentarios = [t for t in estudo_lista.trechos(e) if t.papel == estudo_lista.COMENTARIO]
        self.assertEqual(len(comentarios), 1)
        self.assertEqual(comentarios[0].texto, "")
        self.assertIn("%cal", comentarios[0].pgn)

    def test_o_indice_do_lance_corrente_e_achavel(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        c5 = _linha_de(e4, "c7c5")
        trechos = estudo_lista.trechos(e)
        indice = estudo_lista.trecho_do_caminho(trechos, caminho_de(c5))
        self.assertGreaterEqual(indice, 0)
        self.assertEqual(trechos[indice].texto.strip(), "c5")

class CorteDoTreinoTests(unittest.TestCase):
    """A lista cortada no lance corrente, que é o que faz o treino ser treino (S-290)."""

    def _com_linha(self) -> Estudo:
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        e5 = _linha_de(e4, "e7e5")
        _linha_de(e5, "g1f3", "b8c6")
        _linha_de(e4, "c7c5")
        return e

    def test_o_que_vem_depois_do_lance_corrente_some(self) -> None:
        e = self._com_linha()
        trechos = estudo_lista.trechos(e)
        cortado = estudo_lista.ate(trechos, (0, 0))
        texto = estudo_lista.texto_de(cortado)
        self.assertIn("e5", texto)
        self.assertNotIn("Nf3", texto)
        self.assertNotIn("Nc6", texto)

    def test_corta_e_nao_filtra_para_nao_deixar_parentese_orfao(self) -> None:
        """Um `(` cujo conteúdo sumiu é pior que a linha inteira à mostra."""
        e = self._com_linha()
        cortado = estudo_lista.ate(estudo_lista.trechos(e), (0, 0))
        texto = estudo_lista.texto_de(cortado)
        self.assertEqual(texto.count("("), texto.count(")"))

    def test_na_raiz_so_a_raiz_aparece(self) -> None:
        cortado = estudo_lista.ate(estudo_lista.trechos(self._com_linha()), ())
        self.assertEqual([t.papel for t in cortado], [estudo_lista.RAIZ])

    def test_caminho_que_nao_esta_na_lista_devolve_so_a_raiz(self) -> None:
        cortado = estudo_lista.ate(estudo_lista.trechos(self._com_linha()), (9, 9))
        self.assertEqual([t.papel for t in cortado], [estudo_lista.RAIZ])

    def test_o_simbolo_e_o_comentario_do_lance_corrente_ficam(self) -> None:
        """Eles são **do** lance que se acabou de jogar, e não da continuação."""
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        e4.nags.add(1)
        e4.comment = "o lance mais jogado"
        _linha_de(e4, "e7e5")
        cortado = estudo_lista.ate(estudo_lista.trechos(e), (0,))
        texto = estudo_lista.texto_de(cortado)
        self.assertIn("$1", texto)
        self.assertIn("o lance mais jogado", texto)
        self.assertNotIn("e5", texto)


class PontuacaoTests(unittest.TestCase):
    def test_pontuacao_nao_leva_a_lugar_nenhum(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = _linha(e, "e2e4")
        _linha_de(e4, "e7e5")
        _linha_de(e4, "c7c5")
        for trecho in estudo_lista.trechos(e):
            if trecho.papel in (estudo_lista.ABRE, estudo_lista.FECHA, estudo_lista.RESULTADO):
                self.assertIsNone(trecho.caminho)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
