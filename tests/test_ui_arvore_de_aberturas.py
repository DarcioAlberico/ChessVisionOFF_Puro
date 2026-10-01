"""O que a árvore de aberturas mostra, em que ordem, e o que ela recusa afirmar (S-535).

Decisão pura: nenhuma janela e nenhum SQLite. O arquivo está em
`tests/test_arvore_de_aberturas.py`; a fiação, em `tests/test_qt_arvore_de_aberturas.py`.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass

import chess

from chess_diagram_ocr.arvore_de_aberturas import ACHOU, FUNDO_DEMAIS, SEM_ARVORE, SEM_PARTIDA
from chess_diagram_ocr.ui import arvore_de_aberturas as arvore_ui
from chess_diagram_ocr.ui import indice_da_base as indice_ui
from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.busca_de_partidas import problemas
from chess_diagram_ocr.ui.tabela import Coluna


@dataclass(frozen=True)
class RamoFalso:
    """Os doze atributos que `ui/arvore_de_aberturas.Ramo` declara, montados à mão.

    É o `Protocol` cumprindo o que ele promete: afirmar que uma percentagem sai com travessão não
    pode exigir uma passada sobre um `.pgn`.
    """

    lance: str
    partidas: int
    brancas: int = 0
    empates: int = 0
    pretas: int = 0
    soma_elo: int = 0
    com_elo: int = 0
    soma_ano: int = 0
    com_ano: int = 0
    ano_min: int = 0
    ano_max: int = 0

    @property
    def decididas(self) -> int:
        return self.brancas + self.empates + self.pretas


@dataclass(frozen=True)
class RespostaFalsa:
    estado: str
    ramos: tuple[RamoFalso, ...] = ()
    profundidade: int = 20
    ply: int = 0

    @property
    def partidas(self) -> int:
        return sum(ramo.partidas for ramo in self.ramos)


def _linhas(*ramos: RamoFalso, tabuleiro: chess.Board | None = None) -> tuple[arvore_ui.Linha, ...]:
    return arvore_ui.linhas(RespostaFalsa(ACHOU, ramos), tabuleiro if tabuleiro is not None else chess.Board())


def _celula(linha: arvore_ui.Linha, chave: str) -> str:
    return linha.celulas[[coluna.chave for coluna in arvore_ui.COLUNAS].index(chave)]


class ColunasTests(unittest.TestCase):
    def test_sao_seis_e_a_abertura_e_a_elastica(self) -> None:
        """A abertura é o único campo sem comprimento previsível -- é a regra de `ui/tabela.Coluna`."""
        self.assertEqual(6, len(arvore_ui.COLUNAS))
        elasticas = [coluna.chave for coluna in arvore_ui.COLUNAS if coluna.elastica]
        self.assertEqual(["abertura"], elasticas)

    def test_as_colunas_de_numero_sao_partidas_elo_e_ano(self) -> None:
        """Número alinha à direita e ordena por magnitude (S-153). "Lance" e "Abertura" são texto,
        e a coluna do resultado é uma barra desenhada."""
        numericas = [coluna.chave for coluna in arvore_ui.COLUNAS if coluna.numerica]
        self.assertEqual(["partidas", "elo", "ano"], numericas)

    def test_toda_coluna_tem_titulo_e_a_declaracao_e_valida(self) -> None:
        for coluna in arvore_ui.COLUNAS:
            with self.subTest(coluna=coluna.chave):
                self.assertTrue(coluna.titulo.strip())
                self.assertIsInstance(coluna, Coluna)


class OrdemTests(unittest.TestCase):
    def test_a_ordem_e_por_numero_de_partidas_como_no_ChessBase(self) -> None:
        """E **não** por percentagem de vitória: ordenar por percentagem põe no topo o lance jogado
        uma vez que ganhou uma vez, e a pergunta de quem abre a árvore é o que se joga aqui."""
        linhas = _linhas(
            RamoFalso("d4", 10, brancas=3, empates=3, pretas=4),
            RamoFalso("e4", 30, brancas=10, empates=10, pretas=10),
            RamoFalso("c4", 20, brancas=20),
        )
        self.assertEqual(["e4", "c4", "d4"], [linha.lance for linha in linhas])

    def test_empate_de_frequencia_desempata_pelo_SAN(self) -> None:
        """Duas execuções da mesma posição têm de sair na mesma ordem: sem desempate, a ordem seria
        a que o SQLite devolveu."""
        linhas = _linhas(RamoFalso("e4", 5), RamoFalso("c4", 5), RamoFalso("d4", 5))
        self.assertEqual(["c4", "d4", "e4"], [linha.lance for linha in linhas])

    def test_a_fatia_do_no_entra_na_celula_do_numero(self) -> None:
        """São duas percentagens diferentes na mesma tabela -- frequência e resultado --, e a de
        frequência mora na coluna do número que ela divide."""
        linhas = _linhas(RamoFalso("e4", 30), RamoFalso("d4", 10))
        self.assertEqual("30 · 75%", _celula(linhas[0], "partidas"))

    def test_o_numero_sai_sem_separador_de_milhar(self) -> None:
        """`8.609` seria lido como 8,609 pela ordenação numérica da tabela (`qt/tabela._numero`)."""
        (linha,) = _linhas(RamoFalso("e4", 8609))
        self.assertTrue(_celula(linha, "partidas").startswith("8609"))


class PercentagemTests(unittest.TestCase):
    def test_abaixo_do_minimo_a_percentagem_nao_aparece(self) -> None:
        """`100% das brancas` sobre uma partida parece uma medida e é uma amostra de um -- a forma
        de número enganoso da S-135. O número de partidas continua lá."""
        (linha,) = _linhas(RamoFalso("e4", 4, brancas=4))
        self.assertEqual("—", _celula(linha, "resultado"))
        self.assertEqual((0.0, 0.0, 0.0), linha.fracoes)
        self.assertEqual("4 · 100%", _celula(linha, "partidas"))

    def test_no_minimo_ela_aparece(self) -> None:
        (linha,) = _linhas(RamoFalso("e4", 5, brancas=3, empates=1, pretas=1))
        self.assertEqual(arvore_ui.MINIMO_PARA_PERCENTUAL, 5)
        self.assertEqual("60% · 20% · 20%", _celula(linha, "resultado"))
        self.assertEqual((0.6, 0.2, 0.2), linha.fracoes)

    def test_as_tres_somam_cem_mesmo_com_arredondamento_ruim(self) -> None:
        """Três `round()` independentes somam 99 ou 101 numa linha em cada três, e uma barra que
        soma 101% faz a pessoa parar de confiar na tabela. O empate leva o resto."""
        for brancas, empates, pretas in ((1, 1, 1), (2, 3, 2), (5, 1, 1), (10, 10, 9)):
            with self.subTest(resultado=(brancas, empates, pretas)):
                (linha,) = _linhas(RamoFalso("e4", 99, brancas=brancas * 3, empates=empates * 3, pretas=pretas * 3))
                self.assertEqual(100, sum(round(f * 100) for f in linha.fracoes))

    def test_a_partida_sem_resultado_nao_entra_no_denominador(self) -> None:
        """`*` não é empate: quatro decididas de dez dão 50/25/25, e não 20/10/10."""
        (linha,) = _linhas(RamoFalso("e4", 10, brancas=4, empates=2, pretas=2))
        self.assertEqual("50% · 25% · 25%", _celula(linha, "resultado"))


class EloEAnoTests(unittest.TestCase):
    def test_sem_Elo_a_celula_e_travessao_e_nao_zero(self) -> None:
        """`0` numa coluna de Elo é lido como um Elo, e a base não diz que aquele jogador tem zero
        -- ela não diz nada (a decisão de `ui/lista_de_partidas.linha`)."""
        (linha,) = _linhas(RamoFalso("e4", 9, com_elo=0, soma_elo=0))
        self.assertEqual("—", _celula(linha, "elo"))

    def test_o_Elo_e_a_media_de_quem_tem_Elo(self) -> None:
        (linha,) = _linhas(RamoFalso("e4", 9, com_elo=2, soma_elo=2500 + 2600))
        self.assertEqual("2550", _celula(linha, "elo"))

    def test_o_ano_traz_a_media_e_a_faixa(self) -> None:
        """A média diz quando a linha foi jogada; a faixa diz se ela é antiga ou de ano passado --
        e duas linhas com a mesma média podem ser essas duas coisas."""
        (linha,) = _linhas(RamoFalso("e4", 4, com_ano=2, soma_ano=1990 + 2020, ano_min=1990, ano_max=2020))
        self.assertEqual("2005 (1990–2020)", _celula(linha, "ano"))

    def test_um_ano_so_sai_sem_a_faixa(self) -> None:
        (linha,) = _linhas(RamoFalso("e4", 1, com_ano=1, soma_ano=2020, ano_min=2020, ano_max=2020))
        self.assertEqual("2020", _celula(linha, "ano"))

    def test_sem_data_a_celula_e_travessao(self) -> None:
        (linha,) = _linhas(RamoFalso("e4", 4))
        self.assertEqual("—", _celula(linha, "ano"))

    def test_o_primeiro_token_das_celulas_numericas_e_o_numero(self) -> None:
        """É o que a ordenação da tabela lê (`qt/tabela._numero` faz `split()[0]`), e é por isso que
        o milhar sai sem ponto e a faixa vem depois da média."""
        (linha,) = _linhas(
            RamoFalso("e4", 1234, brancas=600, empates=300, pretas=334, com_elo=1, soma_elo=2500,
                      com_ano=2, soma_ano=1990 + 2020, ano_min=1990, ano_max=2020)
        )
        for chave, esperado in (("partidas", 1234.0), ("elo", 2500.0), ("ano", 2005.0)):
            with self.subTest(coluna=chave):
                self.assertEqual(esperado, float(_celula(linha, chave).split()[0]))


class AberturaTests(unittest.TestCase):
    def test_a_coluna_traz_o_nome_da_linha_e_nao_o_do_codigo(self) -> None:
        """`frase_da_abertura` dá o nome da **linha** (S-534); `nome(codigo)` diria `Ruy Lopez` em
        nove códigos diferentes."""
        tabuleiro = chess.Board()
        for san in ("e4", "e5", "Nf3", "Nc6", "Bb5"):
            tabuleiro.push_san(san)
        (linha,) = _linhas(RamoFalso("Nf6", 40), tabuleiro=tabuleiro)
        self.assertIn("Berlin", _celula(linha, "abertura"))

    def test_fora_do_livro_a_coluna_fica_vazia_e_nao_com_travessao(self) -> None:
        """Uma posição fora do livro não é um dado faltando: é o fim do livro.

        O tabuleiro vem de uma FEN **sem pilha de lances** de propósito: com a pilha,
        `eco.classificar` anda para trás até achar uma posição conhecida, e nas aberturas ela sempre
        acha -- a posição inicial é A00. É a posição colada que pode não ter classificação nenhuma.
        """
        tabuleiro = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 30")
        (linha,) = _linhas(RamoFalso("Ra8+", 3), tabuleiro=tabuleiro)
        self.assertEqual("", _celula(linha, "abertura"))

    def test_o_tabuleiro_volta_como_estava(self) -> None:
        """`_abertura` empilha e desempilha para achar o nome; se ela deixasse o lance na pilha, a
        segunda linha seria calculada de outra posição."""
        tabuleiro = chess.Board()
        antes = tabuleiro.fen()
        _linhas(RamoFalso("e4", 3), RamoFalso("d4", 2), tabuleiro=tabuleiro)
        self.assertEqual(antes, tabuleiro.fen())


class LegalidadeTests(unittest.TestCase):
    def test_o_lance_ilegal_na_posicao_nao_vira_linha(self) -> None:
        """A chave é um resumo de 64 bits, e duas posições podem colidir (~2×10⁻⁵ na gigabase
        inteira). A colisão vira lance faltando, e não estatística de outra posição em silêncio."""
        linhas = _linhas(RamoFalso("e4", 10), RamoFalso("Qxh7", 99))
        self.assertEqual(["e4"], [linha.lance for linha in linhas])

    def test_o_resumo_diz_quantos_sobraram_quando_algum_caiu(self) -> None:
        resposta = RespostaFalsa(ACHOU, (RamoFalso("e4", 10), RamoFalso("Qxh7", 99)))
        linhas = arvore_ui.linhas(resposta, chess.Board())
        self.assertIn("1 de 2 lance(s)", arvore_ui.resumo(resposta, len(linhas)))

    def test_sem_descarte_o_resumo_nao_diz_de_quantos(self) -> None:
        """"17 de 17 lances" toda vez ensina a ignorar a frase, e é justamente nela que a diferença
        precisa aparecer."""
        resposta = RespostaFalsa(ACHOU, (RamoFalso("e4", 10),))
        self.assertIn("1 lance(s)", arvore_ui.resumo(resposta, 1))
        self.assertNotIn("de 1 lance", arvore_ui.resumo(resposta, 1))


class EstadosTests(unittest.TestCase):
    def test_os_quatro_estados_dizem_coisas_diferentes(self) -> None:
        frases = {
            estado: arvore_ui.resumo(RespostaFalsa(estado, (RamoFalso("e4", 9),), ply=40))
            for estado in (SEM_ARVORE, FUNDO_DEMAIS, SEM_PARTIDA, ACHOU)
        }
        self.assertEqual(4, len(set(frases.values())), f"dois estados dizem a mesma coisa: {frases}")

    def test_sem_arvore_a_frase_traz_o_comando_que_a_constroi(self) -> None:
        self.assertIn("cvoff-games --build-tree", arvore_ui.resumo(RespostaFalsa(SEM_ARVORE)))

    def test_fundo_demais_diz_ate_onde_a_arvore_vai_e_onde_a_posicao_esta(self) -> None:
        """Sem os dois números a frase seria "não sei", e a pessoa não teria como saber se falta
        um lance ou vinte."""
        frase = arvore_ui.resumo(RespostaFalsa(FUNDO_DEMAIS, profundidade=20, ply=40))
        self.assertIn("lance 10", frase)
        self.assertIn("21", frase)

    def test_so_a_falta_de_arvore_e_aviso(self) -> None:
        """Ela é a única das quatro que a pessoa pode resolver. Pintar "nenhuma partida" de vermelho
        ensinaria a ler resposta como defeito."""
        self.assertTrue(arvore_ui.e_aviso(RespostaFalsa(SEM_ARVORE)))
        for estado in (FUNDO_DEMAIS, SEM_PARTIDA, ACHOU):
            with self.subTest(estado=estado):
                self.assertFalse(arvore_ui.e_aviso(RespostaFalsa(estado)))

    def test_o_estado_que_nao_achou_nao_produz_linha(self) -> None:
        for estado in (SEM_ARVORE, FUNDO_DEMAIS, SEM_PARTIDA):
            with self.subTest(estado=estado):
                self.assertEqual((), arvore_ui.linhas(RespostaFalsa(estado, (RamoFalso("e4", 9),)), chess.Board()))


class BarraTests(unittest.TestCase):
    def test_as_tres_cores_sao_as_das_pecas_e_o_cinza_neutro(self) -> None:
        """Um par novo de cores para "brancas" e "pretas" seria a segunda declaração da mesma
        ideia, e a que ninguém lembraria de trocar junto."""
        self.assertEqual((tokens.GLIFO_CLARO, tokens.DISPENSADO, tokens.GLIFO_ESCURO), arvore_ui.CORES_DA_BARRA)

    def test_as_luminancias_saem_ordenadas_nas_duas_peles(self) -> None:
        """Brancas mais clara que empate, empate mais claro que pretas -- senão a barra diz o
        contrário do que a coluna promete. É por isso que `TEXTO_SECUNDARIO` foi recusado."""
        for escuro in (False, True):
            with self.subTest(cromo_escuro=escuro):
                claras = [tokens._luminancia(tokens.cor(papel, None, cromo_escuro=escuro)) for papel in arvore_ui.CORES_DA_BARRA]
                self.assertEqual(sorted(claras, reverse=True), claras, f"a ordem das luminâncias: {claras}")

    def test_a_tinta_de_cada_segmento_passa_no_piso_de_contraste(self) -> None:
        """O número escrito dentro do segmento é texto, e o piso dele é `AA_TEXTO` (S-146)."""
        for escuro in (False, True):
            for fundo, tinta in zip(arvore_ui.CORES_DA_BARRA, arvore_ui.TINTAS_DA_BARRA, strict=True):
                with self.subTest(fundo=fundo, cromo_escuro=escuro):
                    razao = tokens.razao_de_contraste(
                        tokens.cor(tinta, None, cromo_escuro=escuro), tokens.cor(fundo, None, cromo_escuro=escuro)
                    )
                    self.assertGreaterEqual(razao, tokens.AA_TEXTO, f"{tinta} sobre {fundo}: {razao:.2f}")


class PerdaAoFecharTests(unittest.TestCase):
    def test_a_arvore_perde_e_o_indice_nao(self) -> None:
        """As duas respostas são opostas porque as duas operações são opostas: o índice é uma
        transação por arquivo e retoma; cada linha da árvore é uma **soma**, e a passada
        interrompida é descartada inteira.

        Elas são afirmadas juntas de propósito: o valor do aviso da S-112 está em ele ser exato
        dos dois lados -- "perde" sobre o que retoma treina a pessoa a ignorá-lo quando for verdade.
        """
        self.assertTrue(arvore_ui.perde_trabalho_ao_fechar())
        self.assertFalse(indice_ui.perde_trabalho_ao_fechar())


class BuscaDaPosicaoTests(unittest.TestCase):
    def test_o_ECO_e_o_que_estreita_a_busca(self) -> None:
        """A posição não tem árvore no índice (S-533): sozinha ela não escolhe nada, e o formulário
        recusaria a busca. O ECO da própria posição é a única coisa que se sabe sem ler partida."""
        filtro = arvore_ui.busca_da_posicao("colocacao-qualquer", "B90")
        self.assertEqual(("B90", "B90", "colocacao-qualquer"), (filtro.eco_de, filtro.eco_ate, filtro.posicao))
        self.assertEqual((), problemas(filtro))

    def test_sem_ECO_o_formulario_recusa_e_diz_o_que_falta(self) -> None:
        filtro = arvore_ui.busca_da_posicao("colocacao-qualquer", "")
        self.assertTrue(problemas(filtro))


class ConstrucaoTests(unittest.TestCase):
    @dataclass(frozen=True)
    class PassadaFalsa:
        partidas: int = 0
        ramos: int = 0
        profundidade: int = 20
        segundos: float = 0.0
        bytes_no_disco: int = 0
        cancelada: bool = False

    def test_a_frase_da_barra_conta_pedacos_e_partidas(self) -> None:
        frase = arvore_ui.frase_da_construcao(3, 10, 1234567)
        self.assertIn("3 de 10", frase)
        self.assertIn("1.234.567", frase)

    def test_antes_do_primeiro_pedaco_a_frase_nao_inventa_total(self) -> None:
        self.assertNotIn("0 de 0", arvore_ui.frase_da_construcao(0, 0, 0))

    def test_a_frase_de_fim_traz_o_que_a_passada_custou(self) -> None:
        frase = arvore_ui.frase_do_fim(self.PassadaFalsa(partidas=10_355_488, ramos=1_000, segundos=1800, bytes_no_disco=2_000_000_000))
        self.assertIn("10.355.488", frase)
        self.assertIn("30 min", frase)
        self.assertIn("2000 MB", frase)

    def test_cancelada_a_frase_diz_que_nada_ficou(self) -> None:
        """Esconder isso faria a pessoa procurar um arquivo que não existe."""
        self.assertIn("nada foi gravado", arvore_ui.frase_do_fim(self.PassadaFalsa(cancelada=True)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
