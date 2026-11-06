"""A decisão da Revisão no `.pgn` já exportado (pendência da Fase 4, `docs/ROADMAP.md`)."""

from __future__ import annotations

import io
import unittest
from collections import Counter
from pathlib import Path

import chess
import chess.pgn
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import pgn_revisado
from chess_diagram_ocr.gallery import lichess_analysis_url
from chess_diagram_ocr.pdf_to_pgn import DiagramPosition, build_pgn_text
from chess_diagram_ocr.review_queue import ReviewItem, ReviewQueue
from chess_diagram_ocr.semantics import SideToMove

LIDA = "r3k3/8/8/8/8/8/8/4K3"
CERTA = "q3k3/8/8/8/8/8/8/4K3"
OUTRA = "4k3/8/8/8/8/8/8/R3K3"


def _posicao(pagina: int, diagrama: int, fen: str = LIDA) -> DiagramPosition:
    return DiagramPosition(
        page_index=pagina,
        diagram_index=diagrama,
        fen=fen,
        confidence=0.7,
        min_confidence=0.41,
        side_to_move=SideToMove(color=chess.WHITE, source="default", reason="assumido"),
    )


def _pgn(*posicoes: DiagramPosition, fonte: str = "livro.pdf", links: bool = False) -> str:
    return build_pgn_text(posicoes, source_name=fonte, lichess_links=links) + "\n"


def _item(pagina: int, diagrama: int, fen: str = CERTA, *, status: str = "done", lado: str = "w", pdf: str = "C:/x/livro.pdf") -> ReviewItem:
    return ReviewItem(
        pdf_path=pdf,
        page_index=pagina,
        diagram_index=diagrama,
        board_image="p.png",
        fen=fen,
        side_to_move=lado,
        min_confidence=0.4,
        mean_entropy=0.1,
        priority=1.0,
        reasons=(),
        status=status,  # type: ignore[arg-type]
    )


def _decisoes(*itens: ReviewItem) -> dict[pgn_revisado.Chave, pgn_revisado.Decisao]:
    return pgn_revisado.decisoes_da_fila(ReviewQueue(source_pdf="livro.pdf", items=list(itens)))


def _jogos(texto: str) -> list[chess.pgn.Game]:
    jogos = []
    fluxo = io.StringIO(texto)
    while (jogo := chess.pgn.read_game(fluxo)) is not None:
        jogos.append(jogo)
    return jogos


class DecisoesDaFilaTests(unittest.TestCase):
    def test_so_o_que_a_pessoa_fechou_e_decisao(self) -> None:
        decisoes = _decisoes(_item(0, 1), _item(1, 1, status="pending"), _item(2, 1, status="skipped"))
        self.assertEqual(list(decisoes), [("livro.pdf", 1, 1)])

    def test_fen_completa_e_campo_de_pecas_dao_a_mesma_decisao(self) -> None:
        """A varredura guarda a FEN completa, e o editor pode devolver só o campo de peças."""
        completa = _decisoes(_item(0, 1, f"{CERTA} b - - 0 1", lado="b"))[("livro.pdf", 1, 1)]
        so_pecas = _decisoes(_item(0, 1, CERTA, lado="b"))[("livro.pdf", 1, 1)]
        self.assertEqual(completa, so_pecas)


class ReescreverTests(unittest.TestCase):
    def test_troca_so_o_jogo_decidido_e_o_resto_sai_igual(self) -> None:
        texto = _pgn(_posicao(0, 1), _posicao(0, 2, OUTRA), _posicao(1, 1, OUTRA))
        feita = pgn_revisado.reescrever(texto, _decisoes(_item(0, 2, CERTA)))
        self.assertEqual(feita.trocados, (("livro.pdf", 1, 2),))
        jogos = _jogos(feita.texto)
        self.assertEqual([j.headers["FEN"].split()[0] for j in jogos], [LIDA, CERTA, OUTRA])
        self.assertEqual(jogos[1].headers["ReviewedFrom"].split()[0], OUTRA)
        self.assertNotIn("ReviewedFrom", jogos[0].headers)
        # o que não foi tocado é o texto de antes, linha por linha
        antes = texto.splitlines()
        depois = feita.texto.splitlines()
        removidas = Counter(antes) - Counter(depois)
        acrescentadas = Counter(depois) - Counter(antes)
        self.assertEqual(removidas.total(), 1, "só a linha da FEN do jogo decidido sai")
        self.assertEqual(acrescentadas.total(), 2, "a FEN nova e o ReviewedFrom")

    def test_mudar_so_o_lado_conta_como_mudanca_e_acompanha_os_cabecalhos(self) -> None:
        texto = _pgn(_posicao(0, 1))
        feita = pgn_revisado.reescrever(texto, _decisoes(_item(0, 1, LIDA, lado="b")))
        jogo = _jogos(feita.texto)[0]
        self.assertEqual(jogo.headers["FEN"].split()[:2], [LIDA, "b"])
        self.assertEqual(jogo.headers["SideToMoveSource"], "manual")
        self.assertEqual(jogo.headers["SideToMove"], SideToMove(chess.BLACK, "manual", "").label)

    def test_a_mesma_posicao_nao_muda_nem_um_byte(self) -> None:
        texto = _pgn(_posicao(0, 1))
        feita = pgn_revisado.reescrever(texto, _decisoes(_item(0, 1, LIDA)))
        self.assertEqual(feita.iguais, (("livro.pdf", 1, 1),))
        self.assertEqual(feita.trocados, ())
        self.assertEqual(feita.texto, texto)

    def test_outro_livro_nao_e_tocado(self) -> None:
        texto = _pgn(_posicao(0, 1), fonte="outro.pdf")
        feita = pgn_revisado.reescrever(texto, _decisoes(_item(0, 1)))
        self.assertEqual(feita.trocados, ())
        self.assertEqual(feita.texto, texto)

    def test_o_numero_do_lance_declarado_fica(self) -> None:
        texto = _pgn(_posicao(0, 1)).replace(f'{LIDA} w q - 0 1"]', f'{LIDA} w q - 0 17"]')
        feita = pgn_revisado.reescrever(texto, _decisoes(_item(0, 1)))
        self.assertEqual(_jogos(feita.texto)[0].headers["FEN"].split()[5], "17")

    def test_numerado_em_outra_ordem_fica_de_fora(self) -> None:
        """`[Diagram "2"]` só significa algo junto com a ordem: era reescrever o diagrama vizinho."""
        texto = _pgn(_posicao(0, 1)).replace('[ReadingOrder "column"]', '[ReadingOrder "row"]')
        self.assertIn('[ReadingOrder "row"]', texto)
        feita = pgn_revisado.reescrever(texto, _decisoes(_item(0, 1)))
        self.assertEqual(feita.outra_ordem, (("livro.pdf", 1, 1),))
        self.assertEqual(feita.texto, texto)

    def test_o_link_do_lichess_acompanha_a_fen(self) -> None:
        texto = _pgn(_posicao(0, 1), links=True)
        antes = _jogos(texto)[0].headers["FEN"]
        self.assertIn(lichess_analysis_url(antes), texto)
        feita = pgn_revisado.reescrever(texto, _decisoes(_item(0, 1)))
        jogo = _jogos(feita.texto)[0]
        self.assertNotIn(lichess_analysis_url(antes), feita.texto)
        self.assertEqual(jogo.comment.strip(), lichess_analysis_url(jogo.headers["FEN"]))

    def test_crlf_e_preservado(self) -> None:
        """A exportação grava por `write_text`, então no Windows o arquivo é CRLF."""
        texto = _pgn(_posicao(0, 1)).replace("\n", "\r\n")
        feita = pgn_revisado.reescrever(texto, _decisoes(_item(0, 1)))
        self.assertEqual(feita.texto.count("\n"), feita.texto.count("\r\n"))
        self.assertEqual(_jogos(feita.texto)[0].headers["FEN"].split()[0], CERTA)

    def test_corrigir_de_novo_guarda_a_primeira_leitura(self) -> None:
        primeira = pgn_revisado.reescrever(_pgn(_posicao(0, 1)), _decisoes(_item(0, 1, CERTA)))
        segunda = pgn_revisado.reescrever(primeira.texto, _decisoes(_item(0, 1, OUTRA)))
        jogo = _jogos(segunda.texto)[0]
        self.assertEqual(jogo.headers["FEN"].split()[0], OUTRA)
        self.assertEqual(jogo.headers["ReviewedFrom"].split()[0], LIDA)

    def test_comentario_e_lance_que_a_pessoa_escreveu_ficam(self) -> None:
        texto = _pgn(_posicao(0, 1)).rstrip().removesuffix("*") + "{ meu comentário } *\n"
        feita = pgn_revisado.reescrever(texto, _decisoes(_item(0, 1)))
        self.assertIn("{ meu comentário }", feita.texto)


class GravarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta: Path = pasta_temporaria(self)
        self.pgn = self.pasta / "livro.pgn"
        self.revisao = self.pasta / "livro.review.pgn"

    def test_grava_com_copia_e_a_copia_e_o_arquivo_anterior(self) -> None:
        original = _pgn(_posicao(0, 1)).encode()
        self.pgn.write_bytes(original)
        plano = pgn_revisado.planejar(self.pgn, _decisoes(_item(0, 1)))
        self.assertEqual(plano.trocados, 1)
        self.assertEqual(self.pgn.read_bytes(), original, "planejar não grava")

        copias = pgn_revisado.gravar(plano)
        self.assertEqual(len(copias), 1)
        self.assertTrue(copias[0].name.startswith("livro.pgn.bak-"))
        self.assertEqual(copias[0].read_bytes(), original)
        self.assertEqual(_jogos(self.pgn.read_text(encoding="utf-8"))[0].headers["FEN"].split()[0], CERTA)
        self.assertEqual(list(self.pasta.glob("*.tmp")), [], "o temporário não fica")

    def test_o_par_de_revisao_e_lido_junto_e_so_o_que_muda_e_gravado(self) -> None:
        """O item da fila costuma estar no `.review.pgn`, que é onde o gate põe o que duvida."""
        self.pgn.write_bytes(_pgn(_posicao(0, 1)).encode())
        self.revisao.write_bytes(_pgn(_posicao(4, 1)).encode())
        antes = self.pgn.read_bytes()
        plano = pgn_revisado.planejar(self.pgn, _decisoes(_item(4, 1)))
        self.assertEqual([a.caminho.name for a in plano.a_gravar], ["livro.review.pgn"])
        copias = pgn_revisado.gravar(plano)
        self.assertEqual([c.name.split(".bak-")[0] for c in copias], ["livro.review.pgn"])
        self.assertEqual(self.pgn.read_bytes(), antes)
        self.assertIn(CERTA, self.revisao.read_text(encoding="utf-8"))

    def test_escolher_o_de_revisao_acha_o_principal(self) -> None:
        self.pgn.write_bytes(_pgn(_posicao(0, 1)).encode())
        self.revisao.write_bytes(_pgn(_posicao(4, 1)).encode())
        plano = pgn_revisado.planejar(self.revisao, _decisoes(_item(0, 1)))
        self.assertEqual([a.caminho.name for a in plano.a_gravar], ["livro.pgn"])

    def test_duas_copias_no_mesmo_segundo_nao_se_apagam(self) -> None:
        self.pgn.write_bytes(b"um")
        primeira = pgn_revisado.copia_de_seguranca(self.pgn)
        self.pgn.write_bytes(b"dois")
        segunda = pgn_revisado.copia_de_seguranca(self.pgn)
        self.assertNotEqual(primeira, segunda)
        self.assertEqual(primeira.read_bytes(), b"um")
        self.assertEqual(segunda.read_bytes(), b"dois")

    def test_a_frase_diz_o_que_ficou_de_fora(self) -> None:
        self.pgn.write_bytes(_pgn(_posicao(0, 1)).encode())
        plano = pgn_revisado.planejar(self.pgn, _decisoes(_item(0, 1), _item(9, 1)))
        self.assertIn("1 diagrama(s)", plano.pergunta())
        self.assertIn("livro.pgn", plano.pergunta())
        self.assertIn("1 não está(ão) neste arquivo", plano.pergunta())
        vazio = pgn_revisado.planejar(self.pgn, _decisoes(_item(9, 1)))
        self.assertEqual(vazio.trocados, 0)
        self.assertIn("Nada a reescrever", vazio.frase_sem_trocas())


if __name__ == "__main__":
    unittest.main()
