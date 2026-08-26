"""A sala no disco: um PGN por livro, uma partida por diagrama (S-271).

Nenhum dos 20 campos do `AppState` era do estudo, e a única saída era um `filedialog` que dependia
de alguém lembrar. Fechar o programa levava a análise da tarde junto.

O que estes testes travam é o contrato do arquivo, e ele tem uma consequência que não é interna:
**o arquivo é PGN de verdade.** Ele abre no ChessBase e no Scid como base de partidas, com
`SourcePDF`, `Page` e `Diagram` dizendo de onde cada estudo veio. Um contêiner nosso não teria uma
vantagem sequer sobre isso.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import chess
import chess.pgn

from chess_diagram_ocr import estudo_arquivo
from chess_diagram_ocr.estudo import Ancora, PosicaoDeEstudo, Sala

ITALIANA = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"


class ArquivoDaSalaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)
        self.livro = str(self.pasta / "Secrets.pdf")

    def _sala(self, *diagramas: int) -> Sala:
        sala = Sala(self.livro)
        for diagrama in diagramas:
            estudo = sala.abrir(
                PosicaoDeEstudo(
                    placement=ITALIANA,
                    vez="b",
                    lance=4,
                    ancora=Ancora(documento=self.livro, pagina=142, diagrama=diagrama),
                )
            )
            no = estudo.jogo.add_variation(chess.Move.from_uci("f8c5"))
            no.nags.add(5)
            no.comment = f"a italiana, diagrama {diagrama}"
            no.add_variation(chess.Move.from_uci("e1g1"))
            sala.guardar(estudo)
        return sala

    def test_a_sala_volta_do_disco_com_tudo(self) -> None:
        estudo_arquivo.gravar(self._sala(0, 1, 2), pasta=self.pasta)
        volta = estudo_arquivo.carregar(self.livro, pasta=self.pasta)
        self.assertEqual(len(volta), 3)
        primeiro = volta.estudos()[0]
        self.assertEqual(primeiro.ancora.pagina, 142)
        self.assertEqual(primeiro.ancora.diagrama, 0)
        self.assertEqual(primeiro.contagem_de_lances(), 2)
        no = primeiro.jogo.variations[0]
        self.assertEqual(no.nags, {5})
        self.assertIn("a italiana", no.comment)
        self.assertTrue(primeiro.invertido)

    def test_o_arquivo_e_um_pgn_de_muitas_partidas(self) -> None:
        """É o que o ChessBase e o Scid chamam de base -- e é por isso que o formato não é nosso."""
        caminho = estudo_arquivo.gravar(self._sala(0, 1), pasta=self.pasta)
        self.assertEqual(caminho.suffix, ".pgn")
        with caminho.open(encoding="utf-8") as arquivo:
            partidas = []
            while (jogo := chess.pgn.read_game(arquivo)) is not None:
                partidas.append(jogo)
        self.assertEqual(len(partidas), 2)
        self.assertEqual([p.headers["Diagram"] for p in partidas], ["1", "2"])
        self.assertEqual(partidas[0].headers["SourcePDF"], "Secrets.pdf")
        self.assertEqual(partidas[0].headers["Annotator"], "ChessVisionOFF")
        self.assertEqual([], partidas[0].errors)

    def test_dois_livros_de_mesmo_nome_nao_se_misturam(self) -> None:
        """Chave pelo caminho **resolvido**, como `ui/state._history_key` e `text/rascunho`."""
        um = str(self.pasta / "a" / "Secrets.pdf")
        dois = str(self.pasta / "b" / "Secrets.pdf")
        self.assertNotEqual(estudo_arquivo.chave_de(um), estudo_arquivo.chave_de(dois))
        self.assertNotEqual(
            estudo_arquivo.caminho_de(um, pasta=self.pasta), estudo_arquivo.caminho_de(dois, pasta=self.pasta)
        )

    def test_o_nome_do_arquivo_e_legivel_por_quem_abrir_a_pasta(self) -> None:
        self.assertTrue(estudo_arquivo.chave_de(self.livro).startswith("Secrets_"))

    def test_livro_sem_sala_carrega_vazio_em_vez_de_levantar(self) -> None:
        """Ausência é o caso normal: quase todo livro do acervo nunca foi estudado."""
        sala = estudo_arquivo.carregar(self.livro, pasta=self.pasta)
        self.assertEqual(len(sala), 0)
        self.assertEqual(sala.documento, self.livro)

    def test_sala_sem_documento_nao_grava(self) -> None:
        """Gravá-la num nome inventado criaria um arquivo que ninguém acha de volta."""
        self.assertIsNone(estudo_arquivo.gravar(Sala(), pasta=self.pasta))

    def test_sala_que_esvaziou_apaga_o_arquivo(self) -> None:
        """Um PGN de zero partidas faria a próxima abertura carregar nada, e a pessoa concluir que
        a gravação não funciona."""
        caminho = estudo_arquivo.gravar(self._sala(0), pasta=self.pasta)
        self.assertTrue(caminho.exists())
        self.assertIsNone(estudo_arquivo.gravar(Sala(self.livro), pasta=self.pasta))
        self.assertFalse(caminho.exists())

    def test_a_gravacao_e_atomica(self) -> None:
        """`atomic_write_text`: o que está no disco é trabalho humano, e um arquivo truncado por
        cima do anterior seria pior que gravação nenhuma."""
        estudo_arquivo.gravar(self._sala(0), pasta=self.pasta)
        antes = estudo_arquivo.caminho_de(self.livro, pasta=self.pasta).read_text(encoding="utf-8")
        estudo_arquivo.gravar(self._sala(0, 1), pasta=self.pasta)
        depois = estudo_arquivo.caminho_de(self.livro, pasta=self.pasta).read_text(encoding="utf-8")
        self.assertGreater(len(depois), len(antes))
        self.assertEqual(list(self.pasta.glob("*.tmp*")), [])

    def test_partida_sem_ancora_no_arquivo_e_descartada_sem_derrubar_as_outras(self) -> None:
        """PGN de fora pode ter sido colado ali à mão. Uma partida que não é de diagrama nenhum não
        entra na sala, e as 49 restantes continuam valendo."""
        caminho = estudo_arquivo.gravar(self._sala(0, 1), pasta=self.pasta)
        caminho.write_text(
            caminho.read_text(encoding="utf-8") + '\n\n[Event "avulsa"]\n[Result "*"]\n\n1. e4 e5 *\n',
            encoding="utf-8",
        )
        self.assertEqual(len(estudo_arquivo.carregar(self.livro, pasta=self.pasta)), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
