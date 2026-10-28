"""O que se pergunta à base, o que é pergunta malfeita, e a frase que conta a resposta (S-533).

Tudo afirmável sem abrir janela nem sqlite: é o lado puro da busca. O que o índice faz com o
`Filtro` está em `tests/test_games_index.py`; o que a janela faz com ele, em
`tests/test_qt_busca_de_partidas.py`.
"""

from __future__ import annotations

import unittest
from dataclasses import fields

from chess_diagram_ocr.ui import busca_de_partidas as busca
from chess_diagram_ocr.ui.tabela import Coluna


class Achado:
    """Um `games_index.Achado` de mentira -- os oito atributos que `linha` lê, e nada mais.

    De mentira de propósito: importar o de lá amarraria o teste do módulo puro ao sqlite, e é
    justamente o que o `Protocol` do módulo existe para evitar.
    """

    def __init__(self, **campos: object) -> None:
        padrao = {
            "brancas": "Carlsen, Magnus",
            "elo_brancas": 2882,
            "pretas": "Anand, Viswanathan",
            "elo_pretas": 2785,
            "resultado": "1-0",
            "evento": "Tata Steel Masters",
            "data": "2019.01.26",
            "eco": "B90",
        }
        self.__dict__.update({**padrao, **campos})


class CamposTests(unittest.TestCase):
    """`de_campos` é a porta do formulário: entra texto, sai `Filtro`."""

    def test_o_numero_escrito_vira_inteiro_e_o_texto_e_aparado(self) -> None:
        filtro = busca.de_campos(brancas="  Carlsen ", ano_de="2015", ano_ate="2020", elo_minimo="2700")
        self.assertEqual("Carlsen", filtro.brancas)
        self.assertEqual((2015, 2020, 2700), (filtro.ano_de, filtro.ano_ate, filtro.elo_minimo))

    def test_campo_vazio_e_zero_e_campo_malfeito_e_outra_coisa(self) -> None:
        """**As duas não são a mesma**: em branco é um filtro que não existe, e `dois mil` é um
        filtro que a pessoa quis e errou. Sem os dois valores, o erro seria engolido e a busca
        sairia sem o filtro que se pediu."""
        self.assertEqual(0, busca.de_campos().ano_de)
        self.assertEqual(busca.NAO_E_NUMERO, busca.de_campos(ano_de="dois mil").ano_de)
        self.assertEqual(busca.NAO_E_NUMERO, busca.de_campos(elo_minimo="2 700").elo_minimo)

    def test_nada_e_consertado_calado(self) -> None:
        """`2O19` com um "ó" no lugar do zero não vira 2019: consertar calado faria a busca
        responder outra pergunta."""
        self.assertEqual(busca.NAO_E_NUMERO, busca.de_campos(ano_de="2O19").ano_de)
        self.assertEqual("b9", busca.de_campos(eco_de=" b9 ").eco_de)

    def test_o_formulario_em_branco_e_um_filtro_vazio(self) -> None:
        self.assertTrue(busca.de_campos().vazio)
        self.assertFalse(busca.de_campos(brancas="Carlsen").vazio)

    def test_todo_campo_do_filtro_tem_entrada_no_formulario(self) -> None:
        """Um campo de `Filtro` que `de_campos` não preenche é um filtro que a janela não alcança
        -- e que o índice consulta com o valor de fábrica, em silêncio."""
        vindos = busca.de_campos(
            brancas="a",
            pretas="b",
            qualquer_cor=False,
            evento="c",
            ano_de="2000",
            ano_ate="2001",
            elo_minimo="2500",
            resultado="1-0",
            eco_de="A00",
            eco_ate="B99",
            posicao="8/8/8/8/8/8/8/8",
        )
        padrao = busca.Filtro()
        iguais = [campo.name for campo in fields(busca.Filtro) if getattr(vindos, campo.name) == getattr(padrao, campo.name)]
        self.assertEqual([], iguais, "campo do filtro que o formulário não preenche")


class ProblemasTests(unittest.TestCase):
    """Pergunta malfeita é recusada com a frase que diz qual campo, e todas de uma vez."""

    def test_o_filtro_completo_nao_tem_problema(self) -> None:
        self.assertEqual((), busca.problemas(busca.de_campos(brancas="Carlsen", ano_de="2019")))

    def test_sem_filtro_que_estreite_a_busca_e_recusada(self) -> None:
        """**Medida e não zelo.** Sem cláusula com árvore no índice, a consulta varre a tabela
        inteira e ordena dez milhões de linhas para responder "as cem mais recentes da base" --
        que não é resposta a pergunta nenhuma."""
        for filtro in (busca.de_campos(), busca.de_campos(resultado="1-0"), busca.de_campos(posicao="8/8/8/8/8/8/8/8")):
            with self.subTest(filtro=filtro):
                problemas = busca.problemas(filtro)
                self.assertTrue(problemas)
                self.assertIn("estreite", problemas[0])

    def test_cada_campo_com_arvore_basta_sozinho(self) -> None:
        """O outro lado: nenhum dos cinco pode exigir companhia, senão a régua vira "preencha tudo"."""
        for campo, valor in (
            ("brancas", "Carlsen"),
            ("pretas", "Anand"),
            ("evento", "Tata"),
            ("ano_de", "2019"),
            ("ano_ate", "2019"),
            ("elo_minimo", "2700"),
            ("eco_de", "B90"),
            ("eco_ate", "B99"),
        ):
            with self.subTest(campo=campo):
                self.assertEqual((), busca.problemas(busca.de_campos(**{campo: valor})))

    def test_o_ano_fora_da_faixa_e_o_ano_invertido_sao_acusados(self) -> None:
        self.assertTrue(busca.problemas(busca.de_campos(ano_de="19")))
        self.assertTrue(busca.problemas(busca.de_campos(ano_ate="20190")))
        invertido = busca.problemas(busca.de_campos(ano_de="2020", ano_ate="2015"))
        self.assertTrue(any("depois do final" in frase for frase in invertido))

    def test_o_eco_que_nao_e_codigo_e_a_faixa_invertida_sao_acusados(self) -> None:
        self.assertTrue(any("A00 a E99" in frase for frase in busca.problemas(busca.de_campos(eco_de="Z9"))))
        invertido = busca.problemas(busca.de_campos(eco_de="C00", eco_ate="B99"))
        self.assertTrue(any("depois do final" in frase for frase in invertido))

    def test_o_resultado_que_o_pgn_nao_escreve_e_acusado(self) -> None:
        """A lista da janela só oferece os quatro; um `Filtro` montado à mão pode trazer outro, e
        `result = 'vitoria'` casaria zero linhas em silêncio."""
        problemas = busca.problemas(busca.Filtro(brancas="Carlsen", resultado="vitória"))
        self.assertTrue(any("resultado de PGN" in frase for frase in problemas))

    def test_os_problemas_vem_todos_de_uma_vez(self) -> None:
        """Corrigir um erro por vez num formulário de dez campos é dez viagens."""
        problemas = busca.problemas(busca.de_campos(ano_de="dois mil", elo_minimo="9999", eco_de="Z9"))
        self.assertEqual(3, len(problemas), problemas)


class ColunasTests(unittest.TestCase):
    """As oito colunas, e o travessão da célula sem valor."""

    def test_as_oito_colunas_na_ordem_da_pergunta(self) -> None:
        self.assertEqual(
            ["Brancas", "Elo", "Pretas", "Elo", "Resultado", "Evento", "Data", "ECO"],
            [coluna.titulo for coluna in busca.COLUNAS],
        )
        for coluna in busca.COLUNAS:
            self.assertIsInstance(coluna, Coluna)

    def test_o_elo_e_numerico_e_o_evento_estica(self) -> None:
        """Elo alinha à direita pela régua da S-153; o evento é o único sem comprimento previsível."""
        numericas = {coluna.chave for coluna in busca.COLUNAS if coluna.numerica}
        self.assertEqual({"elo_brancas", "elo_pretas"}, numericas)
        self.assertEqual({"evento"}, {coluna.chave for coluna in busca.COLUNAS if coluna.elastica})

    def test_a_linha_tem_uma_celula_por_coluna(self) -> None:
        celulas = busca.linha(Achado())
        self.assertEqual(len(busca.COLUNAS), len(celulas))
        self.assertEqual("Carlsen, Magnus", celulas[0])
        self.assertEqual("2882", celulas[1])
        self.assertEqual("B90", celulas[-1])

    def test_a_celula_sem_valor_e_travessao_e_nao_zero(self) -> None:
        """`0` numa coluna de Elo é lido como um Elo, e a base não diz que aquele jogador tem
        zero -- ela não diz nada. É a decisão de `ui/lista_de_partidas.linha`."""
        celulas = busca.linha(Achado(elo_brancas=0, elo_pretas=0, data="", eco="", evento=""))
        self.assertEqual("—", celulas[1])
        self.assertEqual("—", celulas[3])
        self.assertEqual("—", celulas[5])
        self.assertEqual("—", celulas[6])
        self.assertEqual("—", celulas[7])


class ResumoTests(unittest.TestCase):
    """A frase sob a tabela: quantas há, **e de que pergunta elas são**."""

    def test_a_frase_do_item(self) -> None:
        filtro = busca.de_campos(brancas="Carlsen", ano_de="2015", ano_ate="2020", eco_de="B90")
        self.assertEqual("1.234 partidas · Carlsen · 2015–2020 · B90", busca.resumo(filtro, 1234))

    def test_o_singular_e_o_zero_tem_frase_propria(self) -> None:
        filtro = busca.de_campos(brancas="Carlsen")
        self.assertEqual("1 partida · Carlsen", busca.resumo(filtro, 1))
        self.assertEqual("Nenhuma partida · Carlsen", busca.resumo(filtro, 0))

    def test_a_contagem_no_teto_diz_mais_de(self) -> None:
        """Contar todas as partidas de `1.e4` custa segundos para dizer um número que ninguém lê
        até o fim; "mais de 100.000" é a informação inteira."""
        frase = busca.resumo(busca.de_campos(eco_de="B00"), 100_000, teto=True)
        self.assertTrue(frase.startswith("mais de 100.000 partidas"), frase)

    def test_a_pagina_aparece_so_quando_ela_nao_e_a_resposta_toda(self) -> None:
        filtro = busca.de_campos(brancas="Carlsen")
        self.assertEqual("1–100 de 1.234 partidas · Carlsen", busca.resumo(filtro, 1234, mostrados=100))
        self.assertEqual("101–200 de 1.234 partidas · Carlsen", busca.resumo(filtro, 1234, mostrados=100, desde=100))
        self.assertEqual("40 partidas · Carlsen", busca.resumo(filtro, 40, mostrados=40))

    def test_os_dois_jogadores_e_a_cor_exigida(self) -> None:
        dois = busca.de_campos(brancas="Carlsen", pretas="Anand")
        self.assertIn("Carlsen × Anand", busca.resumo(dois, 5))
        com_cor = busca.de_campos(brancas="Carlsen", pretas="Anand", qualquer_cor=False)
        self.assertIn("Carlsen de brancas × Anand de pretas", busca.resumo(com_cor, 5))
        so_pretas = busca.de_campos(pretas="Anand", qualquer_cor=False)
        self.assertIn("Anand de pretas", busca.resumo(so_pretas, 5))

    def test_o_resumo_repete_o_que_a_pessoa_digitou_e_nao_a_forma_dobrada(self) -> None:
        """Quem escreveu `Carlsen` não pode ler `carlsen` de volta: quem dobra é o índice."""
        self.assertIn("Carlsen, Magnus", busca.resumo(busca.de_campos(brancas="Carlsen, Magnus"), 3))

    def test_cada_filtro_preenchido_aparece_na_frase(self) -> None:
        """Uma contagem sem a pergunta ao lado parece defeito da base quando é um ano digitado
        errado -- e o formulário pode já estar apagado para a busca seguinte."""
        filtro = busca.de_campos(
            brancas="Carlsen",
            evento="Tata Steel",
            ano_de="2019",
            ano_ate="2019",
            elo_minimo="2700",
            resultado="1-0",
            eco_de="B90",
            posicao="8/8/8/8/8/8/8/8",
        )
        frase = busca.resumo(filtro, 12, examinadas=2000)
        for pedaco in ("12 partidas", "Carlsen", "Tata Steel", "2019", "Elo ≥ 2700", "1-0", "B90", "posição"):
            with self.subTest(pedaco=pedaco):
                self.assertIn(pedaco, frase)
        self.assertIn("2.000 candidatas lidas", frase)

    def test_a_faixa_de_um_ano_e_de_um_codigo_nao_vira_intervalo(self) -> None:
        self.assertEqual("1 partida · X · 2019", busca.resumo(busca.de_campos(ano_de="2019", ano_ate="2019", brancas="X"), 1))
        self.assertIn("desde 2019", busca.resumo(busca.de_campos(ano_de="2019"), 1))
        self.assertIn("até 2019", busca.resumo(busca.de_campos(ano_ate="2019"), 1))
        self.assertIn("B90", busca.resumo(busca.de_campos(eco_de="B90", eco_ate="B90"), 1))
        self.assertIn("B90–B99", busca.resumo(busca.de_campos(eco_de="b90", eco_ate="B99"), 1))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
