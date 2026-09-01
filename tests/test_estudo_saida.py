"""O estudo virado documento, e o que cada formato faz com ele (S-289).

**O que estes testes travam não é o `.md`.** É a fronteira: o estudo vira `DocumentoRico`, e daí em
diante quem decide o que acontece com negrito, título e diagrama é `text/exportacao.py` -- o módulo
que existe porque *"quatro exportadores escritos separadamente dariam quatro respostas, e três
estariam erradas em silêncio"*. Um teste que afirmasse o texto do Markdown estaria testando aquele
módulo pela segunda vez; o que se afirma aqui é a conversão.
"""

from __future__ import annotations

import unittest

import chess

from chess_diagram_ocr import estudo_saida
from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo, trocar_seta
from chess_diagram_ocr.text import exportacao, rico

ITALIANA = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"


def _estudo(*, ancora: Ancora = Ancora()) -> Estudo:
    e = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA, vez="b", lance=4, ancora=ancora))
    bc5 = e.jogo.add_variation(chess.Move.from_uci("f8c5"))
    bc5.nags.add(5)
    bc5.comment = "a italiana"
    bc5.add_variation(chess.Move.from_uci("e1g1"))
    bc5.add_variation(chess.Move.from_uci("c2c3"))
    return e


def _do_livro() -> Ancora:
    return Ancora(documento="C:/livros/Secrets.pdf", pagina=142, diagrama=1)


class NotacaoTests(unittest.TestCase):
    def test_a_linha_sai_como_o_livro_a_imprime(self) -> None:
        """**É o `texto` do trecho, e não o `pgn`.** O arquivo PGN escreve `$5` e `{ a italiana }`;
        um parágrafo que alguém vai ler escreve `!?` e a frase solta."""
        linha = estudo_saida.notacao_do_estudo(_estudo())
        self.assertIn("4... Bc5", linha)
        self.assertIn("!?", linha)
        self.assertNotIn("$5", linha)
        self.assertIn("a italiana", linha)
        self.assertNotIn("{", linha)

    def test_a_variante_vai_junto_com_os_parenteses(self) -> None:
        self.assertIn("( 5. c3 )", estudo_saida.notacao_do_estudo(_estudo()))

    def test_a_raiz_e_o_resultado_ficam_de_fora(self) -> None:
        """`posição do diagrama` é item de navegação da aba, e `*` é do arquivo -- nenhum dos dois é
        o que o livro imprime na linha."""
        linha = estudo_saida.notacao_do_estudo(_estudo())
        self.assertNotIn("posição", linha)
        self.assertNotIn("*", linha)

    def test_estudo_sem_lance_devolve_linha_vazia(self) -> None:
        vazio = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA))
        self.assertEqual(estudo_saida.notacao_do_estudo(vazio), "")


class DocumentoTests(unittest.TestCase):
    def test_o_documento_tem_titulo_diagrama_fen_e_notacao(self) -> None:
        doc = estudo_saida.para_documento(_estudo(ancora=_do_livro()))
        estilos = [c.atributos.estilo for c in doc.corridas]
        self.assertIn(rico.ESTILO_TITULO, estilos)
        self.assertIn(rico.ESTILO_NOTACAO, estilos)
        self.assertEqual(len(doc.diagramas), 1)
        self.assertIn("Secrets.pdf", doc.para_texto())
        self.assertIn("FEN: ", doc.para_texto())

    def test_a_marca_do_diagrama_nunca_desaparece(self) -> None:
        """A regra que a S-250 escreveu para os quatro formatos: *"um diagrama desenhado sem marca
        correspondente seria invisível para o texto"*."""
        doc = estudo_saida.para_documento(_estudo(ancora=_do_livro()))
        self.assertEqual(doc.diagramas[0].texto, "[Diagrama 1]")
        self.assertEqual(doc.diagramas[0].bloco, estudo_saida.BLOCO_DO_DIAGRAMA)

    def test_estudo_avulso_diz_que_e_avulso_no_titulo(self) -> None:
        self.assertIn("Estudo avulso", estudo_saida.para_documento(_estudo()).para_texto())

    def test_o_comentario_da_raiz_entra_como_prosa(self) -> None:
        e = _estudo(ancora=_do_livro())
        e.jogo.comment = "exercício 12 da página 143"
        doc = estudo_saida.para_documento(e)
        self.assertIn("exercício 12", doc.para_texto())

    def test_as_setas_nao_vazam_como_encanamento(self) -> None:
        """`[%cal Gf3g5]` é comando de PGN, e nenhum formato tem como desenhar uma seta."""
        e = _estudo(ancora=_do_livro())
        trocar_seta(e.jogo, chess.F3, chess.G5)
        self.assertNotIn("%cal", estudo_saida.para_documento(e).para_texto())


class ExportacaoTests(unittest.TestCase):
    """A fronteira funcionando: quem decide o formato é `text/exportacao.py`, e ele aceita isto."""

    def test_o_markdown_sai_com_titulo_e_notacao(self) -> None:
        doc = estudo_saida.para_documento(_estudo(ancora=_do_livro()))
        relatorio = exportacao.exportar(doc, exportacao.formato_de(".md"))
        self.assertIn("# Secrets.pdf", relatorio.conteudo)
        self.assertIn("4... Bc5", relatorio.conteudo)
        self.assertEqual(relatorio.diagramas, 1)

    def test_sem_recorte_o_relatorio_conta_que_faltou(self) -> None:
        """A diferença entre "não havia diagrama" e "havia e não veio" -- e ela vai para o rodapé."""
        doc = estudo_saida.para_documento(_estudo(ancora=_do_livro()))
        relatorio = exportacao.exportar(doc, exportacao.formato_de(".md"))
        self.assertEqual(relatorio.sem_recorte, 1)

    def test_com_recorte_o_markdown_aponta_para_a_imagem(self) -> None:
        from pathlib import Path

        doc = estudo_saida.para_documento(_estudo(ancora=_do_livro()))
        relatorio = exportacao.exportar(
            doc,
            exportacao.formato_de(".md"),
            recortes={estudo_saida.BLOCO_DO_DIAGRAMA: Path("diagramas/Secrets_p143_d2.png")},
        )
        self.assertIn("![[Diagrama 1]](diagramas/Secrets_p143_d2.png)", relatorio.conteudo)
        self.assertEqual(relatorio.sem_recorte, 0)

    def test_os_tres_formatos_aceitam_o_documento_do_estudo(self) -> None:
        doc = estudo_saida.para_documento(_estudo(ancora=_do_livro()))
        for extensao in (".md", ".html", ".rtf"):
            with self.subTest(formato=extensao):
                relatorio = exportacao.exportar(doc, exportacao.formato_de(extensao))
                self.assertTrue(relatorio.conteudo.strip())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ComentarioDaRaizTests(unittest.TestCase):
    """O comentário da raiz sai **uma** vez em cada formato (S-347).

    Ele saía duas: como parágrafo próprio, logo abaixo da FEN, e outra vez grudado no primeiro
    lance -- "uma nota da raiz 1. e4" --, porque `notacao_do_estudo` não filtrava o comentário de
    caminho vazio. A nota da raiz é sobre a **posição**; a linha é a dos lances.
    """

    def _com_nota(self) -> Estudo:
        estudo = Estudo.de_posicao(PosicaoDeEstudo())
        estudo.raiz.comment = "uma nota da raiz"
        estudo.raiz.add_variation(chess.Move.from_uci("e2e4"))
        return estudo

    def test_a_nota_da_raiz_sai_uma_vez_so(self) -> None:
        texto = estudo_saida.para_documento(self._com_nota()).para_texto()
        self.assertEqual(texto.count("uma nota da raiz"), 1)

    def test_a_linha_continua_trazendo_o_comentario_dos_lances(self) -> None:
        """A guarda é só do comentário da raiz: o do lance é parte da linha."""
        estudo = self._com_nota()
        estudo.raiz.variations[0].comment = "boa jogada"

        linha = estudo_saida.notacao_do_estudo(estudo)

        self.assertIn("boa jogada", linha)
        self.assertNotIn("uma nota da raiz", linha)


class ContagemDaSubarvoreTests(unittest.TestCase):
    """A confirmação de apagar conta a **subárvore**, e não a linha principal (S-347).

    `len(list(no.mainline())) + 1` percorre só a continuação principal, e a busca por anotação
    olhava um nível: uma variante com sublinhas anotadas anunciava "isto apaga 2 lance(s)" e
    apagava dezoito, com os comentários todos. Quem lê "2 lances" clica em Sim.
    """

    def _arvore(self):  # noqa: ANN202 - GameNode
        estudo = Estudo.de_posicao(PosicaoDeEstudo())
        e4 = estudo.raiz.add_variation(chess.Move.from_uci("e2e4"))
        e5 = e4.add_variation(chess.Move.from_uci("e7e5"))
        e5.add_variation(chess.Move.from_uci("g1f3"))
        sub = e4.add_variation(chess.Move.from_uci("c7c5"))
        sub.comment = "a siciliana"
        return e4

    def test_conta_os_lances_de_todas_as_linhas(self) -> None:
        from chess_diagram_ocr.qt.painel_de_estudo import _tamanho_da_subarvore

        lances, anotado = _tamanho_da_subarvore([self._arvore()])

        self.assertEqual(lances, 4, "e4 e as duas linhas embaixo dele: e5, Nf3 e c5")
        self.assertTrue(anotado, "a anotação está na subvariante, e não no primeiro nível")

    def test_lance_solto_continua_sendo_um(self) -> None:
        """A caixa só aparece quando há o que perder: um lance sem nada embaixo não pergunta."""
        from chess_diagram_ocr.qt.painel_de_estudo import _tamanho_da_subarvore

        estudo = Estudo.de_posicao(PosicaoDeEstudo())
        solto = estudo.raiz.add_variation(chess.Move.from_uci("e2e4"))

        self.assertEqual(_tamanho_da_subarvore([solto]), (1, False))
