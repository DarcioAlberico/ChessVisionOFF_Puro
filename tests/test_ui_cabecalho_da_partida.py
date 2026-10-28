"""O cabeçalho da partida como dado: os nove campos, a frase e o que a edição grava (S-530).

**O que se afirma sem janela.** Que o formulário cobre o que o ChessBase mostra; que um campo
esvaziado grava o vazio **daquele** campo em vez de sumir com uma etiqueta obrigatória -- que é o
que faria o PGN exportado ser inválido --; que a frase esconde o que o próprio programa escreveu e
mostra o que veio do livro; e que "Gravar" sem tocar em nada não muda nada, que é o que mantém o
`Ctrl+Z` da sala honesto. O widget que executa isto está em `tests/test_qt_painel_de_estudo.py`.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import chess.pgn

from chess_diagram_ocr.estudo import EVENTO, LOCAL, Ancora, Estudo, PosicaoDeEstudo
from chess_diagram_ocr.games_db import _KEPT_HEADERS
from chess_diagram_ocr.ui import cabecalho_da_partida as cabecalho
from chess_diagram_ocr.ui import icones

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"

PARTIDA = {
    "White": "Capablanca, José Raúl",
    "WhiteElo": "2720",
    "Black": "Alekhine, Alexander",
    "BlackElo": "2690",
    "Event": "Kemeri",
    "Site": "Kemeri LAT",
    "Date": "1937.06.24",
    "Round": "12",
    "Result": "1-0",
}


def _estudo_de_diagrama() -> Estudo:
    """Um estudo como a sala o cria a partir de um diagrama do livro."""
    return Estudo.de_posicao(
        PosicaoDeEstudo(
            placement=INICIAL,
            vez="w",
            ancora=Ancora(documento="1937 Kemeri.pdf", pagina=20, diagrama=0),
        )
    )


class CamposTests(unittest.TestCase):
    """Quais são os nove, e por que não são os oito do índice."""

    def test_os_nove_campos_e_a_ordem_deles(self) -> None:
        """A ordem é a de quem copia a legenda de um livro: quem contra quem, onde, quando, como
        terminou -- e não a alfabética."""
        self.assertEqual(
            [
                "White",
                "WhiteElo",
                "Black",
                "BlackElo",
                "Event",
                "Site",
                "Date",
                "Round",
                "Result",
            ],
            [campo.chave for campo in cabecalho.CAMPOS],
        )

    def test_todo_campo_tem_rotulo_e_chaves_unicas(self) -> None:
        chaves = [campo.chave for campo in cabecalho.CAMPOS]
        self.assertEqual(len(chaves), len(set(chaves)))
        for campo in cabecalho.CAMPOS:
            with self.subTest(campo=campo.chave):
                self.assertTrue(campo.rotulo.strip())

    def test_o_formulario_acrescenta_o_elo_e_deixa_o_eco_de_fora(self) -> None:
        """`_KEPT_HEADERS` é o que o **índice** guarda por partida, e Elo não é chave de busca
        ali; na sala ele é metade da pergunta "que partida é esta?". `ECO` vai no sentido
        contrário: é deduzido da posição (S-534) e já aparece na faixa sob o tabuleiro."""
        do_formulario = {campo.chave for campo in cabecalho.CAMPOS}
        self.assertEqual({"WhiteElo", "BlackElo"}, do_formulario - set(_KEPT_HEADERS))
        self.assertEqual({"ECO"}, set(_KEPT_HEADERS) - do_formulario)

    def test_so_o_resultado_tem_lista_fechada(self) -> None:
        """`1:0`, `1-0 ` e `1–0` com travessão são o que se digita sem querer, e cada um faz o PGN
        ser recusado. Nome de jogador e de torneio não têm forma fechada nenhuma."""
        com_escolhas = [campo.chave for campo in cabecalho.CAMPOS if campo.escolhas]
        self.assertEqual(["Result"], com_escolhas)
        self.assertEqual(cabecalho.RESULTADOS, cabecalho.campo("Result").escolhas)
        self.assertEqual("*", cabecalho.RESULTADOS[0], "o em andamento é o de fábrica")

    def test_so_os_dois_elo_ficam_na_mesma_linha(self) -> None:
        estreitos = [campo.chave for campo in cabecalho.CAMPOS if campo.estreito]
        self.assertEqual(["WhiteElo", "BlackElo"], estreitos)

    def test_campo_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            cabecalho.campo("ECO")

    def test_o_traco_do_lapis_existe(self) -> None:
        """Ele não entra por `ui/comandos.py`: editar o cabeçalho ainda não é comando do catálogo,
        e um traço com a chave de um comando inexistente seria arte órfã."""
        self.assertIsNotNone(icones.tracos_de(cabecalho.ICONE))
        self.assertIn(cabecalho.ICONE, icones.ICONES_DA_SALA)


class VazioTests(unittest.TestCase):
    """Vazio é o valor de fábrica do padrão, e não a ausência da chave."""

    def test_as_sete_obrigatorias_sao_o_seven_tag_roster(self) -> None:
        """A régua é o próprio `chess.pgn`: um jogo recém-criado traz exatamente estas sete."""
        self.assertEqual(set(chess.pgn.Game().headers), set(cabecalho.OBRIGATORIOS))

    def test_o_vazio_de_cada_campo_e_o_do_formato(self) -> None:
        self.assertEqual("?", cabecalho.valor_vazio("White"))
        self.assertEqual("????.??.??", cabecalho.valor_vazio("Date"))
        self.assertEqual("*", cabecalho.valor_vazio("Result"))
        self.assertEqual("", cabecalho.valor_vazio("WhiteElo"), "Elo não é obrigatório: some")

    def test_esvaziar_uma_obrigatoria_nao_tira_a_chave_do_jogo(self) -> None:
        """**O PGN sem uma das sete é inválido.** `del jogo.headers["White"]` tira a chave, e é o
        que "apagar o campo" faria se o vazio fosse `""`."""
        jogo = chess.pgn.Game()
        jogo.headers["White"] = "Capablanca"
        mudou = cabecalho.mudancas(jogo.headers, {**PARTIDA, "White": "  "})
        self.assertEqual("?", mudou["White"])
        jogo.headers["White"] = mudou["White"]
        self.assertIn("White", jogo.headers)

    def test_o_placeholder_nao_vai_para_o_campo_do_formulario(self) -> None:
        """Um formulário que abre com sete interrogações obriga a apagar cada uma antes de
        escrever, e quem não apagar grava `?Capablanca`."""
        valores = cabecalho.valores_para_o_formulario(chess.pgn.Game().headers)
        self.assertEqual({""}, set(valores.values()))

    def test_gravar_sem_tocar_em_nada_nao_muda_nada(self) -> None:
        """`_marcar_sujo` empilha o PGN inteiro: um passo de desfazer que não desfaz coisa alguma
        é o defeito que a S-275 evitou na árvore."""
        for headers in (chess.pgn.Game().headers, _estudo_de_diagrama().jogo.headers, dict(PARTIDA)):
            with self.subTest(headers=dict(headers)):
                lidos = cabecalho.valores_para_o_formulario(headers)
                self.assertEqual({}, cabecalho.mudancas(headers, lidos))

    def test_o_que_o_proprio_programa_escreve_aparece_no_formulario(self) -> None:
        """Escondê-lo aqui faria "Gravar" sem tocar em nada **apagar** o header que o resto do
        projeto escreve -- `mudancas` veria `""` e gravaria `?`."""
        valores = cabecalho.valores_para_o_formulario(_estudo_de_diagrama().jogo.headers)
        self.assertEqual(EVENTO, valores["Event"])
        self.assertEqual(LOCAL, valores["Site"])


class FraseTests(unittest.TestCase):
    """As duas linhas que a sala escreve acima do tabuleiro."""

    def test_a_partida_inteira_em_duas_linhas(self) -> None:
        primeira, segunda = cabecalho.linhas(PARTIDA)
        self.assertEqual(
            f"Capablanca, José Raúl (2720){cabecalho.TRAVESSAO}Alekhine, Alexander (2690)"
            f"{cabecalho.SEPARADOR}1-0",
            primeira,
        )
        self.assertEqual("Kemeri · Kemeri LAT · 24/06/1937 · rodada 12", segunda)

    def test_sem_jogador_nenhum_a_primeira_linha_diz_o_que_falta(self) -> None:
        """Uma faixa em branco acima do tabuleiro é espaço que ninguém sabe que é editável."""
        primeira, segunda = cabecalho.linhas(chess.pgn.Game().headers)
        self.assertEqual(cabecalho.SEM_JOGADORES, primeira)
        self.assertEqual("", segunda)

    def test_o_elo_sozinho_e_o_nome_sozinho_valem(self) -> None:
        primeira, _ = cabecalho.linhas({"White": "Capablanca", "BlackElo": "2690"})
        self.assertEqual(f"Capablanca{cabecalho.TRAVESSAO}2690", primeira)

    def test_o_estudo_de_um_diagrama_nao_anuncia_o_programa(self) -> None:
        """`ChessVisionOFF Estudo · Local · rodada 21.1` é o programa se apresentando, e não o
        torneio: acima do tabuleiro é ruído com cara de dado."""
        primeira, segunda = cabecalho.linhas(_estudo_de_diagrama().jogo.headers)
        self.assertEqual(cabecalho.SEM_JOGADORES, primeira)
        self.assertEqual("", segunda)

    def test_a_rodada_que_e_coordenada_do_livro_nao_e_rodada(self) -> None:
        """`Round = "{página}.{diagrama}"` é a convenção do `pdf_to_pgn`; `rodada 21.1` num livro
        de torneio parece a vigésima primeira rodada, e o livro tem catorze."""
        coordenada = {"Round": "21.1", "Page": "21", "Diagram": "1"}
        self.assertEqual("", cabecalho.linhas(coordenada)[1])
        self.assertEqual("rodada 21.1", cabecalho.linhas({**coordenada, "Page": "3"})[1])

    def test_a_data_parcial_do_pgn_vira_o_que_da_para_ler(self) -> None:
        """A maior parte do acervo só tem o ano -- é o que os livros de torneio imprimem."""
        self.assertEqual("24/06/1937", cabecalho.data_legivel("1937.06.24"))
        self.assertEqual("06/1937", cabecalho.data_legivel("1937.06.??"))
        self.assertEqual("1937", cabecalho.data_legivel("1937.??.??"))
        self.assertEqual("", cabecalho.data_legivel("????.??.??"))
        self.assertEqual("", cabecalho.data_legivel(None))

    def test_uma_data_escrita_a_mao_volta_como_veio(self) -> None:
        """Comê-la seria pior que mostrá-la: é informação que alguém digitou."""
        self.assertEqual("verão de 1937", cabecalho.data_legivel("verão de 1937"))


class GravacaoTests(unittest.TestCase):
    """O que a edição escreve, e o que ela deixa em paz."""

    def test_so_o_que_mudou_volta(self) -> None:
        antes = dict(PARTIDA)
        depois = {**PARTIDA, "Round": "13"}
        self.assertEqual({"Round": "13"}, cabecalho.mudancas(antes, depois))

    def test_o_texto_e_aparado(self) -> None:
        mudou = cabecalho.mudancas(PARTIDA, {**PARTIDA, "White": "  Capablanca  "})
        self.assertEqual({"White": "Capablanca"}, mudou)

    def test_o_formulario_incompleto_esvazia_o_que_ele_nao_traz(self) -> None:
        """`mudancas` compara os **nove**, e não os que vieram: o diálogo sempre manda todos, e um
        que mandasse menos estaria dizendo que o resto foi apagado. É o contrato, e ele fica
        afirmado para que ninguém o use como leitura parcial."""
        mudou = cabecalho.mudancas(PARTIDA, {"White": "Capablanca"})
        self.assertEqual("Capablanca", mudou["White"])
        self.assertEqual("?", mudou["Black"])
        self.assertEqual("*", mudou["Result"])

    def test_o_elo_apagado_some_e_o_nome_apagado_vira_interrogacao(self) -> None:
        mudou = cabecalho.mudancas(PARTIDA, {**PARTIDA, "WhiteElo": "", "Black": ""})
        self.assertEqual({"WhiteElo": "", "Black": "?"}, mudou)

    def test_o_que_e_gravado_sobrevive_ao_pgn(self) -> None:
        """A ida e a volta pelo formato: é por `Estudo.para_pgn` que o `Ctrl+Z` da sala passa."""
        estudo = _estudo_de_diagrama()
        for chave, valor in cabecalho.mudancas(estudo.jogo.headers, PARTIDA).items():
            estudo.jogo.headers[chave] = valor
        relido = Estudo.de_pgn(estudo.para_pgn())
        assert relido is not None
        self.assertEqual(cabecalho.linhas(PARTIDA), cabecalho.linhas(relido.jogo.headers))


class PurezaTests(unittest.TestCase):
    def test_o_modulo_nao_importa_toolkit(self) -> None:
        arvore = ast.parse(Path(cabecalho.__file__).read_text(encoding="utf-8"))
        nomes = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
        nomes |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
        self.assertEqual(set(), nomes & {"PyQt6", "tkinter"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
