"""A sala no disco: um PGN por livro, uma partida por diagrama (S-271).

Nenhum dos 20 campos do `AppState` era do estudo, e a única saída era um `filedialog` que dependia
de alguém lembrar. Fechar o programa levava a análise da tarde junto.

O que estes testes travam é o contrato do arquivo, e ele tem uma consequência que não é interna:
**o arquivo é PGN de verdade.** Ele abre no ChessBase e no Scid como base de partidas, com
`SourcePDF`, `Page` e `Diagram` dizendo de onde cada estudo veio. Um contêiner nosso não teria uma
vantagem sequer sobre isso.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from typing import TextIO
from unittest import mock

import chess
import chess.pgn

from chess_diagram_ocr import estudo_arquivo
from chess_diagram_ocr.arquivo_do_dono import GravacaoRecusada, Ilegivel, Leitura, Lida, gravavel
from chess_diagram_ocr.estudo import Ancora, PosicaoDeEstudo, Sala

ITALIANA = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"


def _gravar(sala: Sala, *, pasta: Path) -> Path | None:
    """Grava como a sala grava: sobre a leitura do livro dela, que aqui nunca existiu antes."""
    return estudo_arquivo.gravar(Lida(sala, estudo_arquivo.caminho_de(sala.documento, pasta=pasta)))


def _sala_com(livro: str, *diagramas: int) -> Sala:
    sala = Sala(livro)
    for diagrama in diagramas:
        estudo = sala.abrir(
            PosicaoDeEstudo(
                placement=ITALIANA,
                vez="b",
                lance=4,
                ancora=Ancora(documento=livro, pagina=142, diagrama=diagrama),
            )
        )
        no = estudo.jogo.add_variation(chess.Move.from_uci("f8c5"))
        no.nags.add(5)
        no.comment = f"a italiana, diagrama {diagrama}"
        no.add_variation(chess.Move.from_uci("e1g1"))
        sala.guardar(estudo)
    return sala


class ArquivoDaSalaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)
        self.livro = str(self.pasta / "Secrets.pdf")

    def _sala(self, *diagramas: int) -> Sala:
        return _sala_com(self.livro, *diagramas)

    def test_a_sala_volta_do_disco_com_tudo(self) -> None:
        _gravar(self._sala(0, 1, 2), pasta=self.pasta)
        volta = estudo_arquivo.carregar(self.livro, pasta=self.pasta).valor
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
        caminho = _gravar(self._sala(0, 1), pasta=self.pasta)
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

    def test_a_sala_e_o_rascunho_nomeiam_o_livro_do_mesmo_jeito(self) -> None:
        """O nome do arquivo é contrato com o disco: mudar uma vírgula dele perde as salas e os
        rascunhos já gravados. Nome legível do `stem`, e dez hexadecimais do sha1 do caminho
        resolvido, sem `normcase` (S-864: a regra mora em `ui/livros.nome_e_impressao`)."""
        import hashlib

        from chess_diagram_ocr.text import rascunho

        livro = self.pasta / "sub" / ".." / "Meu Livro (2ª ed.).pdf"
        impressao = hashlib.sha1(str(livro.resolve()).encode("utf-8")).hexdigest()[:10]
        self.assertEqual(f"Meu_Livro_2_ed.__{impressao}", estudo_arquivo.chave_de(livro))
        self.assertEqual(f"Meu_Livro_2_ed.__f8_{impressao}", rascunho.chave_de(livro, 7))
        sem = hashlib.sha1(str(Path("sem-documento").resolve()).encode("utf-8")).hexdigest()[:10]
        self.assertEqual(f"sem-documento_{sem}", estudo_arquivo.chave_de(""))
        self.assertEqual(f"sem-documento_f1_{sem}", rascunho.chave_de("", 0))

    def test_o_nome_do_arquivo_e_legivel_por_quem_abrir_a_pasta(self) -> None:
        self.assertTrue(estudo_arquivo.chave_de(self.livro).startswith("Secrets_"))

    def test_livro_sem_sala_carrega_vazio_em_vez_de_levantar(self) -> None:
        """Ausência é o caso normal: quase todo livro do acervo nunca foi estudado."""
        sala = estudo_arquivo.carregar(self.livro, pasta=self.pasta).valor
        self.assertEqual(len(sala), 0)
        self.assertEqual(sala.documento, self.livro)

    def test_sala_sem_documento_nao_grava(self) -> None:
        """Gravá-la num nome inventado criaria um arquivo que ninguém acha de volta."""
        self.assertIsNone(_gravar(Sala(), pasta=self.pasta))

    def test_sala_que_esvaziou_apaga_o_arquivo(self) -> None:
        """Um PGN de zero partidas faria a próxima abertura carregar nada, e a pessoa concluir que
        a gravação não funciona."""
        caminho = _gravar(self._sala(0), pasta=self.pasta)
        self.assertTrue(caminho.exists())
        self.assertIsNone(_gravar(Sala(self.livro), pasta=self.pasta))
        self.assertFalse(caminho.exists())

    def test_a_gravacao_e_atomica(self) -> None:
        """`atomic_write_text`: o que está no disco é trabalho humano, e um arquivo truncado por
        cima do anterior seria pior que gravação nenhuma."""
        _gravar(self._sala(0), pasta=self.pasta)
        antes = estudo_arquivo.caminho_de(self.livro, pasta=self.pasta).read_text(encoding="utf-8")
        _gravar(self._sala(0, 1), pasta=self.pasta)
        depois = estudo_arquivo.caminho_de(self.livro, pasta=self.pasta).read_text(encoding="utf-8")
        self.assertGreater(len(depois), len(antes))
        self.assertEqual(list(self.pasta.glob("*.tmp*")), [])

    def test_partida_sem_ancora_no_arquivo_e_descartada_sem_derrubar_as_outras(self) -> None:
        """PGN de fora pode ter sido colado ali à mão. Uma partida que não é de diagrama nenhum não
        entra na sala, e as 49 restantes continuam valendo."""
        caminho = _gravar(self._sala(0, 1), pasta=self.pasta)
        caminho.write_text(
            caminho.read_text(encoding="utf-8") + '\n\n[Event "avulsa"]\n[Result "*"]\n\n1. e4 e5 *\n',
            encoding="utf-8",
        )
        self.assertEqual(len(estudo_arquivo.carregar(self.livro, pasta=self.pasta).valor), 2)


class PartidaQueNaoLeTests(unittest.TestCase):
    """A partida da sala que não lê sobrevive à gravação (S-814).

    O arquivo da sala é trabalho de tardes, e a gravação o reescreve inteiro a cada edição: o que a
    leitura deixa de fora, a gravação apaga. Antes, deixava de fora a partida sem âncora, a que tinha
    um lance ilegal (cortada ali, em silêncio) e, se o `read_game` levantasse, todas as seguintes.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)
        self.livro = str(self.pasta / "Secrets.pdf")
        self.caminho = estudo_arquivo.caminho_de(self.livro, pasta=self.pasta)

    def _sala(self, quantos: int) -> Sala:
        return _sala_com(self.livro, *range(quantos))

    def _acrescentar(self, bloco: str) -> None:
        self.caminho.write_text(self.caminho.read_text(encoding="utf-8") + "\n" + bloco, encoding="utf-8")

    def _editar_e_gravar(self, leitura: Leitura[Sala] | None = None) -> str:
        """Carrega, mexe no primeiro estudo como a sala mexe, e grava: devolve o arquivo gravado."""
        if leitura is None:
            leitura = estudo_arquivo.carregar(self.livro, pasta=self.pasta)
        self.assertIsInstance(leitura, Lida)
        sala = leitura.valor
        primeiro = sala.estudos()[0]
        primeiro.jogo.comment = "editado hoje"
        sala.guardar(primeiro)
        estudo_arquivo.gravar(gravavel(leitura))
        return self.caminho.read_text(encoding="utf-8")

    def test_estudo_sem_ancora_sobrevive_a_gravacao(self) -> None:
        _gravar(self._sala(2), pasta=self.pasta)
        avulsa = '[Event "avulsa"]\n[Page "catorze"]\n[Diagram "1"]\n[Result "*"]\n\n1. e4 e5 {minha nota} *'
        self._acrescentar(avulsa + "\n")
        self.assertEqual(2, len(estudo_arquivo.carregar(self.livro, pasta=self.pasta).valor))
        gravado = self._editar_e_gravar()
        self.assertIn("editado hoje", gravado)
        self.assertIn(avulsa, gravado, "a partida sem âncora volta byte a byte igual")

    def test_lance_ilegal_nao_trunca_a_partida_na_regravacao(self) -> None:
        """O `read_game` não levanta: manda o lance ilegal para `errors` e corta a partida ali."""
        _gravar(self._sala(2), pasta=self.pasta)
        quebrada = (
            '[Event "x"]\n[SourcePDF "Secrets.pdf"]\n[Page "200"]\n[Diagram "1"]\n[Result "*"]\n\n'
            "1. e4 e5 2. Ke3 Nf6 {a análise depois do erro} 3. d4 *"
        )
        self._acrescentar(quebrada + "\n")
        gravado = self._editar_e_gravar()
        self.assertIn(quebrada, gravado, "a partida inteira, com o que vem depois do lance ilegal")

    def test_read_game_que_levanta_na_segunda_nao_derruba_as_seguintes(self) -> None:
        _gravar(self._sala(5), pasta=self.pasta)
        original = self.caminho.read_text(encoding="utf-8")
        segunda = self._sala(5).estudos()[1].para_pgn()
        self.assertIn(segunda, original)
        ler_de_verdade = chess.pgn.read_game
        chamadas = [0]

        def read_game(fluxo: TextIO) -> chess.pgn.Game | None:
            jogo = ler_de_verdade(fluxo)
            chamadas[0] += 1
            if chamadas[0] == 2:
                raise RuntimeError("visitante quebrou")
            return jogo

        with mock.patch.object(chess.pgn, "read_game", read_game):
            leitura = estudo_arquivo.carregar(self.livro, pasta=self.pasta)
        self.assertIsInstance(leitura, Lida)
        self.assertEqual(4, len(leitura.valor), "quatro carregadas")
        gravado = self._editar_e_gravar(leitura)
        partidas = []
        fluxo = io.StringIO(gravado)
        while (jogo := chess.pgn.read_game(fluxo)) is not None:
            partidas.append(jogo)
        self.assertEqual(5, len(partidas), "cinco gravadas")
        self.assertIn(segunda, gravado, "a que não leu volta igual")

    def test_leitura_que_nao_avanca_trava_a_sala(self) -> None:
        """Se o `read_game` levanta sem consumir nada, o resto do arquivo não tem como ser lido: a
        sala fica com o que leu, e a gravação fica travada (S-812) -- e o laço não roda para sempre."""
        _gravar(self._sala(3), pasta=self.pasta)
        original = self.caminho.read_bytes()

        def read_game(_fluxo: TextIO) -> chess.pgn.Game | None:
            raise RuntimeError("não leio nada")

        with mock.patch.object(chess.pgn, "read_game", read_game):
            leitura = estudo_arquivo.carregar(self.livro, pasta=self.pasta)
        self.assertIsInstance(leitura, Ilegivel)
        with self.assertRaises(GravacaoRecusada):
            estudo_arquivo.gravar(gravavel(leitura))
        self.assertEqual(original, self.caminho.read_bytes())


class LerPgnSemCarregarTudoTests(unittest.TestCase):
    """`estudos_de_pgn` lê de um fluxo, e o teto de partidas é de quem chama (S-307).

    **O defeito.** `abrir_pgn` fazia `caminho.read_text()` na thread do Tk, e `pgn_database/` --
    a pasta que este projeto manda usar -- tem arquivos de 8,6 GB e 10,3 GB. Medido: 5,2 MB de
    PGN custam 18,8 s e 220 MB de pico, o que dá ~3,5 min de janela congelada num arquivo de
    62 MB. Nos de gigabytes o `read_text` levanta `MemoryError`, que **não** é `OSError` e por
    isso escapava da guarda e subia para o laço de eventos.

    **O teto é argumento, e não constante.** Este mesmo laço lê o arquivo da sala em `carregar`:
    um limite global truncaria em silêncio a sala de quem tem mais estudos que o teto -- perda
    de análise humana, que é o oposto do que o item quer.
    """

    def _pgn(self, quantas: int) -> str:
        return "\n\n".join(f'[Event "Partida {i}"]\n\n1. e4 e5 *' for i in range(quantas))

    def test_le_de_um_fluxo_aberto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "colecao.pgn"
            caminho.write_text(self._pgn(3), encoding="utf-8")

            with caminho.open(encoding="utf-8") as fluxo:
                achados = estudo_arquivo.estudos_de_pgn(fluxo, onde=caminho.name)

            self.assertEqual(len(achados), 3)

    def test_o_texto_continua_valendo(self) -> None:
        """A assinatura ganhou um caso; ela não pode ter perdido o que já servia."""
        self.assertEqual(len(estudo_arquivo.estudos_de_pgn(self._pgn(2))), 2)

    def test_o_teto_para_a_leitura_onde_foi_pedido(self) -> None:
        self.assertEqual(len(estudo_arquivo.estudos_de_pgn(self._pgn(10), limite=4)), 4)

    def test_sem_teto_le_tudo(self) -> None:
        """O padrão é "sem limite", e é ele que protege a sala de ser truncada."""
        self.assertEqual(len(estudo_arquivo.estudos_de_pgn(self._pgn(10))), 10)

    def test_a_sala_e_lida_sem_teto(self) -> None:
        """`carregar` não pode passar limite nenhum: a sala é trabalho humano acumulado.

        É o risco que fez o teto virar argumento em vez de constante -- e é este teste que o
        trava, porque um `LIMITE` global lá dentro passaria em todos os outros quatro.
        """
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            livro = str(pasta / "Livro.pdf")
            sala = Sala(livro)
            for diagrama in range(6):
                estudo = sala.abrir(
                    PosicaoDeEstudo(
                        placement="rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R",
                        vez="b",
                        lance=4,
                        ancora=Ancora(documento=livro, pagina=142, diagrama=diagrama),
                    )
                )
                estudo.jogo.add_variation(chess.Move.from_uci("f8c5")).comment = f"nota {diagrama}"
                sala.guardar(estudo)
            _gravar(sala, pasta=pasta)

            self.assertEqual(len(estudo_arquivo.carregar(livro, pasta=pasta).valor), 6)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
