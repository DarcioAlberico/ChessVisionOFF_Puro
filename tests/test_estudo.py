"""O estudo como dado: árvore, âncora, caminho, vez e sala (S-268/S-269/S-270/S-272/S-278/S-279).

O que estes testes travam é o que a aba não conseguia afirmar sem abrir janela -- e por isso quase
nunca afirmava. Três deles são regressões de defeito medido, e cada um está nomeado no docstring:

- **o estudo abria com a vez errada** e sem direito a roque, porque o painel recebia o campo de
  peças e o chamava de FEN (S-269);
- **trocar de diagrama apagava a análise** do anterior, sem pergunta e sem desfazer (S-270);
- **escrever um comentário apagaria as setas** do lance, porque as duas coisas moram no mesmo campo
  do PGN (S-268).
"""

from __future__ import annotations

import unittest

import chess
import chess.pgn

from chess_diagram_ocr.estudo import (
    Ancora,
    Estudo,
    PosicaoDeEstudo,
    Sala,
    alternar_nag,
    caminho_de,
    colar,
    com_texto,
    comandos_do_comentario,
    no_em,
    roque_provavel,
    setas_de,
    simbolo_de_nag,
    texto_do_comentario,
    trocar_seta,
)

ITALIANA = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"
ROQUEADAS = "r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R1BQ1RK1"


def _ancora(pagina: int = 142, diagrama: int = 1) -> Ancora:
    return Ancora(documento="C:/livros/Secrets.pdf", pagina=pagina, diagrama=diagrama)


def _com_variantes() -> Estudo:
    """Um estudo com variante e **subvariante** -- que é a palavra do pedido e o que o plugin
    de referência não faz (profundidade 1)."""
    e = Estudo.de_posicao(PosicaoDeEstudo(ancora=_ancora()))
    e4 = e.jogo.add_variation(chess.Move.from_uci("e2e4"))
    e5 = e4.add_variation(chess.Move.from_uci("e7e5"))
    c5 = e4.add_variation(chess.Move.from_uci("c7c5"))
    nf3 = c5.add_variation(chess.Move.from_uci("g1f3"))
    nf3.nags.add(1)
    nc3 = c5.add_variation(chess.Move.from_uci("b1c3"))
    nc3.comment = "o ataque grande-prix"
    e5.add_variation(chess.Move.from_uci("g1f3"))
    return e


class ComentarioTests(unittest.TestCase):
    """O comentário do PGN carrega os comandos da máquina misturados ao texto da pessoa."""

    BRUTO = "[%csl Rd4][%cal Gf3g5] roque curto [%eval 0.35,18]"

    def test_o_texto_sai_sem_os_comandos(self) -> None:
        """Medido com `python-chess` 1.11.2: `arrows()` e `eval()` leem os comandos e **não** os
        tiram de `node.comment`. Mostrar isso numa caixa de comentário é mostrar o encanamento."""
        self.assertEqual(texto_do_comentario(self.BRUTO), "roque curto")

    def test_os_comandos_saem_na_ordem_em_que_estao(self) -> None:
        self.assertEqual(comandos_do_comentario(self.BRUTO), ("[%csl Rd4]", "[%cal Gf3g5]", "[%eval 0.35,18]"))

    def test_editar_o_texto_nao_apaga_as_setas(self) -> None:
        """O defeito de uma linha que este módulo existe para impedir: `no.comment = novo` apaga a
        seta e a avaliação do lance, em silêncio."""
        novo = com_texto(self.BRUTO, "melhor era Bb5")
        self.assertEqual(texto_do_comentario(novo), "melhor era Bb5")
        self.assertEqual(comandos_do_comentario(novo), comandos_do_comentario(self.BRUTO))

    def test_comentario_sem_comando_continua_sendo_so_o_texto(self) -> None:
        self.assertEqual(com_texto("", "uma frase"), "uma frase")


class CaminhoTests(unittest.TestCase):
    def test_o_caminho_e_derivado_e_resolve_de_volta(self) -> None:
        e = _com_variantes()
        for caminho in ((), (0,), (0, 0), (0, 1), (0, 1, 0), (0, 1, 1)):
            with self.subTest(caminho=caminho):
                no = no_em(e.jogo, caminho)
                self.assertIsNotNone(no)
                self.assertEqual(caminho_de(no), caminho)

    def test_caminho_que_nao_existe_devolve_none_em_vez_de_levantar(self) -> None:
        """`None` é resposta legítima: um caminho guardado antes de apagar uma variante aponta para
        o vazio, e a resposta certa ali é voltar para a raiz."""
        e = _com_variantes()
        self.assertIsNone(no_em(e.jogo, (0, 9)))
        self.assertIsNone(no_em(e.jogo, (5,)))

    def test_promover_muda_os_indices_e_o_caminho_acompanha(self) -> None:
        """**A armadilha do item.** Um caminho guardado antes da promoção aponta para outro lance
        depois dela; por isso quem opera trabalha com o nó e recalcula o caminho no fim."""
        e = _com_variantes()
        c5 = no_em(e.jogo, (0, 1))
        antes = caminho_de(c5)
        c5.parent.promote_to_main(c5)
        self.assertEqual(antes, (0, 1))
        self.assertEqual(caminho_de(c5), (0, 0))
        self.assertIsNot(no_em(e.jogo, antes), c5)

    def test_ir_para_caminho_morto_volta_para_a_raiz(self) -> None:
        e = _com_variantes()
        self.assertFalse(e.ir_para((0, 7)))
        self.assertIs(e.no, e.jogo)


class PosicaoTests(unittest.TestCase):
    """A vez e o roque que o livro diz -- e que a aba jogava fora na porta de entrada (S-269)."""

    def test_a_vez_do_diagrama_chega_ao_estudo(self) -> None:
        """Era o defeito: `board_from_fen` completava o campo de peças com `w - - 0 1`, e toda a
        Fase 3 do projeto existe para responder de quem é a vez."""
        posicao = PosicaoDeEstudo(placement=ROQUEADAS, vez="b")
        self.assertFalse(chess.Board(posicao.fen()).turn)

    def test_o_roque_e_concedido_so_com_rei_e_torre_em_casa(self) -> None:
        self.assertEqual(roque_provavel(ITALIANA), "KQkq")
        self.assertEqual(roque_provavel(ROQUEADAS), "-")
        # Torre de h1 fora de casa: sobra o roque grande das brancas.
        sem_h1 = ITALIANA.replace("RNBQK2R", "RNBQK1R1")
        self.assertEqual(roque_provavel(sem_h1), "Qkq")

    def test_o_roque_deduzido_deixa_a_procedencia_escrita(self) -> None:
        """`CastlingSource: inferred` é o header que `pdf_to_pgn` já usa para a mesma dedução."""
        deduzido = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA))
        explicito = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA, roque="-"))
        self.assertEqual(deduzido.jogo.headers.get("CastlingSource"), "inferred")
        self.assertNotIn("CastlingSource", explicito.jogo.headers)

    def test_o_numero_do_lance_da_galeria_numera_o_estudo(self) -> None:
        """Sem ele um estudo da posição do lance 23 numeraria a partir de 1, e os números não
        bateriam com a página impressa ao lado."""
        posicao = PosicaoDeEstudo(placement=ROQUEADAS, vez="b", lance=23)
        self.assertEqual(chess.Board(posicao.fen()).fullmove_number, 23)

    def test_uma_fen_inteira_e_respeitada_inteira(self) -> None:
        """Quem digitou uma FEN à mão quer aquela FEN: sobrescrever a vez dela seria o mesmo
        defeito, do outro lado."""
        fen = f"{ROQUEADAS} b - - 4 21"
        self.assertEqual(PosicaoDeEstudo(placement=fen, vez="w").fen(), fen)

    def test_o_tabuleiro_abre_do_lado_de_quem_joga(self) -> None:
        self.assertTrue(Estudo.de_posicao(PosicaoDeEstudo(placement=ROQUEADAS, vez="b")).invertido)
        self.assertFalse(Estudo.de_posicao(PosicaoDeEstudo(placement=ROQUEADAS, vez="w")).invertido)

    def test_placement_impossivel_nao_e_valido(self) -> None:
        self.assertFalse(PosicaoDeEstudo(placement="isto-nao-e-uma-posicao").valida())


class PgnTests(unittest.TestCase):
    def test_o_pgn_do_estudo_volta_com_a_arvore_inteira(self) -> None:
        e = _com_variantes()
        volta = Estudo.de_pgn(e.para_pgn(), documento=e.ancora.documento)
        self.assertIsNotNone(volta)
        # Dois exportadores, e não um: `StringExporter` acumula linhas entre chamadas, e reusá-lo
        # compara a primeira partida com a primeira **mais** a segunda.
        def movetext(jogo: chess.pgn.Game) -> str:
            visitante = chess.pgn.StringExporter(headers=False, variations=True, comments=True, columns=None)
            return str(jogo.accept(visitante))

        self.assertEqual(movetext(volta.jogo), movetext(e.jogo))

    def test_a_ancora_vai_e_volta_pelos_headers(self) -> None:
        """Os headers são os de `pdf_to_pgn.py`: `Page` e `Diagram` **1-based** no arquivo, e
        0-based na `Ancora`. As duas convenções existem, e a conversão fica num lugar só."""
        e = Estudo.de_posicao(PosicaoDeEstudo(placement=ROQUEADAS, ancora=_ancora(pagina=142, diagrama=1)))
        self.assertEqual(e.jogo.headers["Page"], "143")
        self.assertEqual(e.jogo.headers["Diagram"], "2")
        self.assertEqual(e.jogo.headers["Round"], "143.2")
        volta = Estudo.de_pgn(e.para_pgn(), documento=e.ancora.documento)
        self.assertEqual(volta.ancora, e.ancora)

    def test_a_orientacao_sobrevive_ao_arquivo(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo(ancora=_ancora()))
        e.invertido = True
        self.assertTrue(Estudo.de_pgn(e.para_pgn()).invertido)

    def test_pgn_ilegivel_devolve_none_em_vez_de_levantar(self) -> None:
        self.assertIsNone(Estudo.de_pgn(""))

    def test_o_anotador_diz_de_onde_o_arquivo_saiu(self) -> None:
        """Num PGN aberto no ChessBase é ele que distingue o que saiu daqui do que veio de fora."""
        e = Estudo.de_posicao(PosicaoDeEstudo(ancora=_ancora()))
        self.assertEqual(e.jogo.headers["Annotator"], "ChessVisionOFF")


class VazioTests(unittest.TestCase):
    """A régua que decide o que a sala guarda: um livro tem ~1.500 diagramas."""

    def test_estudo_sem_lance_e_sem_anotacao_e_vazio(self) -> None:
        self.assertTrue(Estudo.de_posicao(PosicaoDeEstudo(ancora=_ancora())).vazio())

    def test_um_lance_basta_para_deixar_de_ser_vazio(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo(ancora=_ancora()))
        e.jogo.add_variation(chess.Move.from_uci("e2e4"))
        self.assertFalse(e.vazio())

    def test_so_um_comentario_na_raiz_ja_e_trabalho(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo(ancora=_ancora()))
        e.jogo.comment = "posição do exercício 12"
        self.assertFalse(e.vazio())

    def test_a_contagem_de_lances_inclui_as_variantes(self) -> None:
        self.assertEqual(_com_variantes().contagem_de_lances(), 6)


class SalaTests(unittest.TestCase):
    """Trocar de diagrama é ir para a outra mesa, e não recomeçar (S-270)."""

    def test_voltar_ao_diagrama_devolve_a_analise(self) -> None:
        """**A regressão do item.** Antes, `sync_with_ocr` chamava `_set_board_state`, que fazia
        `self.game = self._new_game(board)` -- a árvore inteira no lixo, sem pergunta."""
        sala = Sala("C:/livros/Secrets.pdf")
        um = PosicaoDeEstudo(placement=ITALIANA, ancora=_ancora(diagrama=0))
        dois = PosicaoDeEstudo(placement=ROQUEADAS, ancora=_ancora(diagrama=1))

        estudo = sala.abrir(um)
        estudo.jogo.add_variation(chess.Move.from_uci("e1g1"))
        sala.guardar(estudo)

        sala.guardar(sala.abrir(dois))
        de_volta = sala.abrir(um)
        self.assertEqual(de_volta.contagem_de_lances(), 1)

    def test_estudo_sem_lance_nao_ocupa_lugar_na_sala(self) -> None:
        sala = Sala("C:/livros/Secrets.pdf")
        sala.guardar(sala.abrir(PosicaoDeEstudo(placement=ITALIANA, ancora=_ancora())))
        self.assertEqual(len(sala), 0)

    def test_apagar_o_ultimo_lance_tira_o_estudo_da_sala(self) -> None:
        """Os dois lados de `guardar`: senão o arquivo do livro acumula partidas de zero lance."""
        sala = Sala("C:/livros/Secrets.pdf")
        estudo = sala.abrir(PosicaoDeEstudo(placement=ITALIANA, ancora=_ancora()))
        no = estudo.jogo.add_variation(chess.Move.from_uci("e1g1"))
        self.assertTrue(sala.guardar(estudo))
        estudo.jogo.remove_variation(no)
        self.assertFalse(sala.guardar(estudo))
        self.assertEqual(len(sala), 0)

    def test_a_chave_e_a_ancora_e_nao_a_fen(self) -> None:
        """Duas páginas com o mesmo diagrama são dois estudos."""
        sala = Sala("C:/livros/Secrets.pdf")
        for pagina in (10, 20):
            estudo = sala.abrir(PosicaoDeEstudo(placement=ITALIANA, ancora=_ancora(pagina=pagina)))
            estudo.jogo.add_variation(chess.Move.from_uci("e1g1"))
            sala.guardar(estudo)
        self.assertEqual(len(sala), 2)

    def test_fen_sem_ancora_abre_estudo_avulso_e_nao_entra_na_colecao(self) -> None:
        """Guardá-lo num nome inventado criaria trabalho que ninguém acha de volta -- é a mesma
        decisão de `text/rascunho.gravar` para documento sem folha de origem."""
        sala = Sala("C:/livros/Secrets.pdf")
        estudo = sala.abrir(PosicaoDeEstudo(placement=ITALIANA))
        estudo.jogo.add_variation(chess.Move.from_uci("e1g1"))
        self.assertFalse(sala.guardar(estudo))
        self.assertEqual(len(sala), 0)

    def test_os_estudos_saem_na_ordem_em_que_se_le_o_livro(self) -> None:
        sala = Sala("C:/livros/Secrets.pdf")
        for pagina, diagrama in ((20, 1), (10, 2), (20, 0)):
            estudo = sala.abrir(
                PosicaoDeEstudo(placement=ITALIANA, ancora=_ancora(pagina=pagina, diagrama=diagrama))
            )
            estudo.jogo.add_variation(chess.Move.from_uci("e1g1"))
            sala.guardar(estudo)
        self.assertEqual(
            [(e.ancora.pagina, e.ancora.diagrama) for e in sala.estudos()], [(10, 2), (20, 0), (20, 1)]
        )


class ColarTests(unittest.TestCase):
    """Um campo só para FEN e PGN, e quem decide qual é o dado (S-288)."""

    def test_uma_fen_colada_abre_como_posicao(self) -> None:
        estudo, motivo = colar(f"{ITALIANA} b KQkq - 4 4")
        self.assertEqual(motivo, "")
        self.assertFalse(estudo.tabuleiro.turn)
        self.assertEqual(estudo.tabuleiro.fullmove_number, 4)

    def test_um_campo_de_pecas_sozinho_tambem_abre(self) -> None:
        """É o que o OCR desta casa produz, e ele tem sete barras e não oito -- a régua do plugin
        de referência (`includes('/')`) acertaria aqui e erraria noutros lugares."""
        estudo, motivo = colar(ITALIANA)
        self.assertEqual(motivo, "")
        self.assertEqual(estudo.tabuleiro.board_fen(), ITALIANA)

    def test_um_pgn_colado_abre_como_partida(self) -> None:
        estudo, motivo = colar("1. e4 e5 2. Nf3 Nc6 3. Bc4 *")
        self.assertEqual(motivo, "")
        self.assertEqual(estudo.contagem_de_lances(), 5)

    def test_um_pgn_com_headers_traz_a_ancora_de_volta(self) -> None:
        """O caminho de volta de quem editou a coleção do livro no ChessBase."""
        original = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA, ancora=_ancora()))
        original.jogo.add_variation(chess.Move.from_uci("e1g1"))
        estudo, motivo = colar(original.para_pgn(), ancora=_ancora())
        self.assertEqual(motivo, "")
        self.assertEqual(estudo.ancora, _ancora())

    def test_lance_ilegal_no_pgn_diz_qual_foi(self) -> None:
        """`"PGN inválido"` mandaria a pessoa procurar o defeito num texto que ela acabou de colar."""
        estudo, motivo = colar("1. e4 e5 2. Qh8 *")
        self.assertIsNone(estudo)
        self.assertIn("Qh8", motivo)

    def test_texto_que_nao_e_nem_um_nem_outro_diz_isso(self) -> None:
        estudo, motivo = colar("isto aqui não é xadrez nenhum")
        self.assertIsNone(estudo)
        self.assertIn("não é uma FEN nem um PGN", motivo)

    def test_nada_colado_nao_levanta(self) -> None:
        estudo, motivo = colar("   ")
        self.assertIsNone(estudo)
        self.assertTrue(motivo)


class NagTests(unittest.TestCase):
    """Julgar o lance e julgar a posição são duas frases, e somam (S-278)."""

    def test_o_mesmo_simbolo_de_novo_desliga(self) -> None:
        self.assertEqual(alternar_nag({1}, 1), set())

    def test_nag_de_lance_troca_e_nag_de_posicao_soma(self) -> None:
        self.assertEqual(alternar_nag({1}, 2), {2})
        self.assertEqual(alternar_nag({1}, 16), {1, 16})
        self.assertEqual(alternar_nag({1, 16}, 14), {1, 14})

    def test_nag_desconhecido_aparece_como_o_pgn_o_escreveria(self) -> None:
        self.assertEqual(simbolo_de_nag(1), "!")
        self.assertEqual(simbolo_de_nag(140), "$140")


class SetaTests(unittest.TestCase):
    """Seta e casa marcada moram no PGN, em `[%cal]`/`[%csl]` (S-279)."""

    def test_o_mesmo_gesto_desenha_e_apaga(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA))
        no = e.jogo.add_variation(chess.Move.from_uci("e1g1"))
        trocar_seta(no, chess.F3, chess.G5)
        self.assertEqual(len(setas_de(no)), 1)
        trocar_seta(no, chess.F3, chess.G5)
        self.assertEqual(setas_de(no), [])

    def test_a_seta_sobrevive_a_ida_e_volta_pelo_pgn(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA, ancora=_ancora()))
        no = e.jogo.add_variation(chess.Move.from_uci("e1g1"))
        trocar_seta(no, chess.F3, chess.G5, "red")
        trocar_seta(no, chess.D4, chess.D4, "blue")
        volta = Estudo.de_pgn(e.para_pgn())
        setas = {(s.tail, s.head, s.color) for s in setas_de(volta.jogo.variations[0])}
        self.assertEqual(setas, {(chess.F3, chess.G5, "red"), (chess.D4, chess.D4, "blue")})

    def test_desenhar_seta_nao_mexe_no_texto_do_comentario(self) -> None:
        e = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA))
        no = e.jogo.add_variation(chess.Move.from_uci("e1g1"))
        no.comment = "abriga o rei"
        trocar_seta(no, chess.F3, chess.G5)
        self.assertEqual(texto_do_comentario(no.comment), "abriga o rei")

    def test_comentario_com_cal_malformado_nao_derruba_o_estudo(self) -> None:
        """PGN de fora traz de tudo, e uma seta ilegível não pode impedir a posição de aparecer."""
        e = Estudo.de_posicao(PosicaoDeEstudo(placement=ITALIANA))
        no = e.jogo.add_variation(chess.Move.from_uci("e1g1"))
        no.comment = "[%cal Gzz9zz9] nota"
        self.assertEqual(setas_de(no), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
