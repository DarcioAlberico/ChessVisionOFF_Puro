"""Um eixo, um significado: a cor como linguagem, e não como decoração (S-158).

**O achado que nenhuma auditoria de arquivo acharia.** Duas paletas, cada uma impecavelmente
documentada no seu módulo, dizendo coisas diferentes com a mesma cor a 30 cm de distância na
mesma janela:

| cor | na página | no tabuleiro |
|---|---|---|
| azul | `#4da3ff` — localizado, **ainda não lido** | `#3d7dd4` — casa **reescrita** pelo decodificador |
| violeta | `#9b7bff` — a base reconheceu: **não precisa de você** | `#8e44ad` — as duas leituras **discordam**: olhe |

Medido: os dois azuis distavam **3,6° de matiz**. O olho aprende cor antes de rótulo — violeta na
página queria dizer "pule" e violeta no tabuleiro queria dizer "pare".

**O teste não lista os pares: ele os gera.** `tokens.SIGNIFICADO` diz em que superfície cada
papel é desenhado, e daí sai quem compete com quem. Uma marcação nova declara o que significa e
descobre na hora se a matiz que escolheu já quer dizer outra coisa — que é a única forma de esta
regra sobreviver ao próximo item que acrescentar uma cor.

**E o contraste passou a ser gerado do mesmo jeito (S-257).** Este arquivo media *um* papel
contra *duas* casas — o `CORRIGIDO`, que era o que a S-158 tinha acabado de consertar. Um teste
que afirma o conserto não é um teste que afirma a regra, e a diferença deixou três contornos
invisíveis em metade do tabuleiro passarem em verde desde a S-158. A varredura agora sai de
`SIGNIFICADO` × `tokens.CASAS_DO_TABULEIRO`: todas as marcações, todos os fundos.
"""

from __future__ import annotations

import itertools
import unittest

from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.tokens import (
    PAGINA,
    RESERVA,
    SATURACAO_NEUTRA,
    SEPARACAO_MINIMA_DE_MATIZ,
    SIGNIFICADO,
    TABULEIRO,
    distancia_de_matiz,
    matiz,
    saturacao,
)


class InstrumentoTests(unittest.TestCase):
    """A régua antes da medição. Um `distancia_de_matiz` errado reprovaria a paleta inteira."""

    def test_as_ancoras_de_matiz(self) -> None:
        self.assertAlmostEqual(matiz("#ff0000"), 0.0, places=3)
        self.assertAlmostEqual(matiz("#00ff00"), 120.0, places=3)
        self.assertAlmostEqual(matiz("#0000ff"), 240.0, places=3)

    def test_a_distancia_e_circular(self) -> None:
        """350° e 10° distam 20, e não 340 -- a matiz é um círculo, não uma régua."""
        self.assertAlmostEqual(distancia_de_matiz("#ff0000", "#00ff00"), 120.0, places=3)
        self.assertAlmostEqual(distancia_de_matiz("#ff0080", "#ff8000"), 60.0, delta=0.5)

    def test_a_distancia_e_simetrica_e_nunca_passa_de_180(self) -> None:
        for a, b in itertools.combinations(RESERVA.values(), 2):
            with self.subTest(par=(a, b)):
                self.assertAlmostEqual(distancia_de_matiz(a, b), distancia_de_matiz(b, a), places=9)
                self.assertLessEqual(distancia_de_matiz(a, b), 180.0)

    def test_cinza_nao_tem_matiz_a_disputar(self) -> None:
        for cinza in ("#000000", "#808080", "#ffffff"):
            with self.subTest(cinza=cinza):
                self.assertEqual(saturacao(cinza), 0.0)

    def test_uma_cor_saturada_tem_saturacao_alta(self) -> None:
        """O controle: se `saturacao` devolvesse zero sempre, toda a regra ficaria isenta."""
        self.assertGreater(saturacao(RESERVA[tokens.A_FAZER]), SATURACAO_NEUTRA)


class EixoDeclaradoTests(unittest.TestCase):
    """A tabela existe, cobre o que a janela desenha, e cada papel diz uma coisa só."""

    def test_toda_marcacao_declara_superficie_e_significado(self) -> None:
        marcacoes = {
            tokens.A_FAZER,
            tokens.LIDO,
            tokens.PRONTO,
            tokens.DISPENSADO,
            tokens.TRACEJADO,
            tokens.CORRIGIDO,
            tokens.DIVERGENTE,
            tokens.PROBLEMA,
            tokens.ALVO,
            tokens.CONTORNO_DE_SELECAO,
        }
        self.assertEqual(marcacoes, set(SIGNIFICADO), "uma marcação sem significado declarado")

    def test_as_superficies_declaradas_sao_as_duas_que_existem(self) -> None:
        self.assertEqual({PAGINA, TABULEIRO}, {superficie for superficie, _ in SIGNIFICADO.values()})

    def test_nenhum_significado_se_repete(self) -> None:
        """Dois papéis dizendo a mesma frase seriam um papel só, e a paleta teria uma cor sobrando."""
        frases = [frase for _, frase in SIGNIFICADO.values()]
        self.assertEqual(len(frases), len(set(frases)))

    def test_todo_papel_declarado_tem_cor(self) -> None:
        self.assertTrue(set(SIGNIFICADO) <= set(RESERVA))


def _pares_da_mesma_superficie() -> list[tuple[str, str]]:
    """Os pares que competem pelo mesmo olhar. **Gerados**, e não listados à mão."""
    return [
        (a, b)
        for a, b in itertools.combinations(sorted(SIGNIFICADO), 2)
        if SIGNIFICADO[a][0] == SIGNIFICADO[b][0]
    ]


class SeparacaoTests(unittest.TestCase):
    """A regra: duas marcações da mesma superfície não compartilham matiz."""

    def test_a_geracao_de_pares_nao_esta_vazia(self) -> None:
        """O controle. Uma varredura sobre lista vazia passa sempre e não mede nada."""
        pares = _pares_da_mesma_superficie()
        self.assertGreaterEqual(len(pares), 12)
        self.assertIn(("A_FAZER", "PRONTO"), pares)
        self.assertNotIn(("A_FAZER", "CORRIGIDO"), pares, "página e tabuleiro não são a mesma superfície")

    def test_nenhum_par_da_mesma_superficie_compartilha_matiz(self) -> None:
        muito_perto = []
        for a, b in _pares_da_mesma_superficie():
            if saturacao(RESERVA[a]) < SATURACAO_NEUTRA or saturacao(RESERVA[b]) < SATURACAO_NEUTRA:
                continue  # cinza não tem matiz a disputar -- ver SATURACAO_NEUTRA
            separacao = distancia_de_matiz(RESERVA[a], RESERVA[b])
            if separacao < SEPARACAO_MINIMA_DE_MATIZ:
                muito_perto.append(f"{a} x {b} ({SIGNIFICADO[a][0]}): {separacao:.1f}°")
        self.assertEqual([], muito_perto, f"marcações a menos de {SEPARACAO_MINIMA_DE_MATIZ}° na mesma superfície")

    def test_o_verde_da_selecao_deixou_de_ser_o_verde_de_pronto(self) -> None:
        """O par que a regra encontrou sozinha, e que a spec não tinha listado.

        `TRACEJADO` (`#00ff88`, 152°) e `PRONTO` (`#00c07a`, 158°) distavam **6°** e são
        desenhados na **mesma** superfície: o retângulo verde que você acabou de arrastar e a
        caixa verde que diz "este já foi feito".
        """
        self.assertGreaterEqual(
            distancia_de_matiz(RESERVA[tokens.TRACEJADO], RESERVA[tokens.PRONTO]),
            SEPARACAO_MINIMA_DE_MATIZ,
        )
        self.assertLess(distancia_de_matiz("#00ff88", "#00c07a"), 10.0, "o par antigo, para o registro")


class ParesDaSpecTests(unittest.TestCase):
    """Os dois pares que a avaliação nomeou, agora com número dos dois lados."""

    def test_o_azul_da_pagina_e_o_do_tabuleiro_se_separaram(self) -> None:
        """3,6° era a distância entre "ainda não lido" e "esta casa foi reescrita"."""
        self.assertLess(distancia_de_matiz("#4da3ff", "#3d7dd4"), 5.0, "o par antigo, para o registro")
        self.assertGreaterEqual(
            distancia_de_matiz(RESERVA[tokens.A_FAZER], RESERVA[tokens.CORRIGIDO]),
            SEPARACAO_MINIMA_DE_MATIZ,
        )

    def test_o_violeta_de_pule_deixou_de_ser_o_violeta_de_pare(self) -> None:
        """`DISPENSADO` recuou para cinza: "não precisa de você" não deve competir por atenção."""
        self.assertLess(saturacao(RESERVA[tokens.DISPENSADO]), SATURACAO_NEUTRA)
        self.assertGreater(saturacao(RESERVA[tokens.DIVERGENTE]), SATURACAO_NEUTRA)

    def test_a_procedencia_da_vizinha_deixou_de_ser_o_azul_da_casa_reescrita(self) -> None:
        """Era `CORRIGIDO_TEXTO`, "o mesmo azul como texto" -- e nunca foi o mesmo significado."""
        self.assertIn("VIZINHA_TEXTO", tokens.PAPEIS)
        self.assertNotIn("CORRIGIDO_TEXTO", tokens.PAPEIS)


class MarcacaoContraTextoTests(unittest.TestCase):
    """A regra da S-146 aplicada de novo, e desta vez pelo outro lado (S-257).

    Lá o achado foi uma **marcação** que reprovava como texto (`PRONTO` sobre branco, 2,38:1) e
    a saída foi `PRONTO_TEXTO`. Aqui é o inverso: dois papéis de **texto** que a janela também
    usava como contorno de casa. `#c0392b` é um vermelho legível sobre o cinza da janela e uma
    borda invisível sobre `#b58863` -- e enquanto os dois usos tinham um nome só, corrigir um
    quebrava o outro.
    """

    PARES = (("PROBLEMA", "PROBLEMA_TEXTO"), ("DIVERGENTE", "DIVERGENTE_TEXTO"))

    def test_os_dois_significados_tem_dois_papeis(self) -> None:
        for marcacao, texto in self.PARES:
            with self.subTest(papel=marcacao):
                self.assertIn(marcacao, tokens.PAPEIS)
                self.assertIn(texto, tokens.PAPEIS)

    def test_a_marcacao_esta_no_eixo_e_o_texto_nao(self) -> None:
        """`SIGNIFICADO` é a tabela de quem compete pelo mesmo olhar **numa superfície**. Texto
        de rótulo não é desenhado sobre página nem sobre tabuleiro, e entrar ali faria a regra
        dos 40° cobrar separação de matiz entre coisas que nunca aparecem juntas."""
        for marcacao, texto in self.PARES:
            with self.subTest(papel=marcacao):
                self.assertEqual(TABULEIRO, SIGNIFICADO[marcacao][0])
                self.assertNotIn(texto, SIGNIFICADO)

    def test_cada_um_passa_o_piso_do_lugar_em_que_e_desenhado(self) -> None:
        """E os pisos são outros em cada caso -- 3,0 de elemento gráfico, 4,5 de texto."""
        for marcacao, texto in self.PARES:
            with self.subTest(papel=marcacao):
                for casa in tokens.CASAS_DO_TABULEIRO:
                    razao = tokens.razao_de_contraste(RESERVA[marcacao], RESERVA[casa])
                    self.assertGreaterEqual(razao, tokens.AA_GRAFICO, f"{marcacao} sobre {casa}")
                razao = tokens.razao_de_contraste(RESERVA[texto], RESERVA[tokens.SUPERFICIE_PADRAO])
                self.assertGreaterEqual(razao, tokens.AA_TEXTO, f"{texto} sobre a janela")

    def test_um_valor_so_nao_cumpria_os_dois_pisos(self) -> None:
        """**O critério de aceite da separação.** Se o valor de texto passasse também como
        marcação, dois papéis seriam luxo -- e a S-145 chama isso de defeito, não de virtude."""
        for marcacao, texto in self.PARES:
            with self.subTest(papel=marcacao):
                razao = tokens.razao_de_contraste(RESERVA[texto], RESERVA[tokens.CASA_ESCURA])
                self.assertLess(razao, tokens.AA_GRAFICO, f"{texto} serviria de marcação: {razao:.2f}:1")
                self.assertNotEqual(RESERVA[marcacao], RESERVA[texto])

    def test_o_texto_nao_mudou_de_pixel(self) -> None:
        """Separar os nomes é o item; repintar o rodapé não é. Os dois valores de texto são os
        que os três painéis já desenhavam antes da S-257."""
        self.assertEqual("#c0392b", RESERVA[tokens.PROBLEMA_TEXTO])
        self.assertEqual("#8e44ad", RESERVA[tokens.DIVERGENTE_TEXTO])


MARCACOES_DO_TABULEIRO = tuple(
    sorted(papel for papel, (superficie, _) in SIGNIFICADO.items() if superficie == TABULEIRO)
)
"""Geradas de `SIGNIFICADO`, e não listadas: uma marcação nova é medida sem ninguém lembrar."""

REPROVAS_ANTERIORES_A_S257 = {
    "ALVO sobre CASA_ESCURA": 1.53,
    "DIVERGENTE sobre CASA_ESCURA": 1.86,
    "PROBLEMA sobre CASA_ESCURA": 1.73,
    "ALVO sobre CASA_ULTIMO_LANCE": 2.99,
}
"""Os valores de antes, guardados para que a correção seja verificável e não afirmada.

As três primeiras foram medidas em 2026-08-24 e registradas como exceção declarada enquanto o
item não existia. A quarta ninguém tinha medido: o amarelo do último lance é o terceiro fundo
do tabuleiro, e nenhuma lista de pares o citava -- ver `tokens.CASAS_DO_TABULEIRO`."""


class ContrasteDasMarcacoesTests(unittest.TestCase):
    """Trocar de matiz não pode custar legibilidade — e aqui ela **melhorou**."""

    def test_toda_marcacao_do_tabuleiro_contrasta_com_as_tres_casas(self) -> None:
        """O contorno tem de ser visto em **qualquer** casa: cada uma é um terço do tabuleiro.

        A varredura é sobre `SIGNIFICADO` × `CASAS_DO_TABULEIRO`, e é essa a diferença para o
        que havia aqui antes. A versão da S-158 media **um** papel (`CORRIGIDO`) contra **duas**
        casas, e a paleta passava em verde com três contornos invisíveis em metade do tabuleiro:
        o teste media o que a S-158 tinha acabado de consertar, não a regra.
        """
        reprovas = []
        for papel in MARCACOES_DO_TABULEIRO:
            for casa in tokens.CASAS_DO_TABULEIRO:
                razao = tokens.razao_de_contraste(RESERVA[papel], RESERVA[casa])
                if razao < tokens.AA_GRAFICO:
                    reprovas.append(f"{papel} sobre {casa}: {razao:.2f}:1")
        self.assertEqual([], reprovas, f"marcação de tabuleiro abaixo de {tokens.AA_GRAFICO}:1")

    def test_os_valores_antigos_reprovavam_de_verdade(self) -> None:
        """O controle do teste acima. Sem ele, um `AA_GRAFICO` frouxo passaria despercebido."""
        antigos = {"ALVO": "#3f7f4c", "DIVERGENTE": "#8e44ad", "PROBLEMA": "#c0392b", "CORRIGIDO": "#3d7dd4"}
        for par, esperado in REPROVAS_ANTERIORES_A_S257.items():
            papel, casa = par.split(" sobre ")
            with self.subTest(par=par):
                razao = tokens.razao_de_contraste(antigos[papel], RESERVA[casa])
                self.assertAlmostEqual(razao, esperado, places=2)
                self.assertLess(razao, tokens.AA_GRAFICO)
        self.assertLess(
            tokens.razao_de_contraste(antigos["CORRIGIDO"], RESERVA[tokens.CASA_ESCURA]),
            2.0,
            "o azul que a S-158 tirou, para o registro",
        )

    def test_a_correcao_foi_de_luminosidade_e_nao_de_matiz(self) -> None:
        """**Por que o conserto não podia ser o da S-158.** Lá o defeito era matiz e a saída foi
        trocar de faixa; aqui a matiz de cada um já estava a 40° de todas as outras da mesma
        superfície, e o que reprovava era brilho. Trocar matiz teria trocado o significado."""
        antigos = {"ALVO": "#3f7f4c", "DIVERGENTE": "#8e44ad", "PROBLEMA": "#c0392b"}
        for papel, antigo in antigos.items():
            with self.subTest(papel=papel):
                self.assertLess(distancia_de_matiz(RESERVA[papel], antigo), 1.0, "a matiz mudou")
                self.assertGreater(saturacao(RESERVA[papel]), SATURACAO_NEUTRA, "virou cinza")

    def test_nenhuma_cor_clara_serve_as_duas_casas(self) -> None:
        """**A conta que fecha o item, e ela explica por que as cinco marcações são escuras.**

        Para passar 3,0:1 sobre a casa escura por cima, uma cor precisaria de luminância ≥ 0,95;
        sobre a casa clara, ≥ 2,24 -- que não existe, porque o branco puro é 1,0. Não há cor
        clara que sirva às duas: a única saída para uma marcação medida contra o tabuleiro
        inteiro é descer, e é por isso que descer não foi preguiça."""
        for casa, piso in ((tokens.CASA_CLARA, 2.2), (tokens.CASA_ESCURA, 0.9)):
            with self.subTest(casa=casa):
                fundo = tokens._luminancia(RESERVA[casa])
                necessaria = tokens.AA_GRAFICO * (fundo + 0.05) - 0.05
                self.assertGreater(necessaria, piso, "haveria cor clara servindo a esta casa")
        self.assertLess(
            tokens.razao_de_contraste("#ffffff", RESERVA[tokens.CASA_CLARA]),
            tokens.AA_GRAFICO,
            "nem o branco puro passa sobre a casa clara pelo lado de cima",
        )

    def test_as_marcacoes_da_pagina_continuam_passando_o_piso_grafico(self) -> None:
        pagina = RESERVA[tokens.SUPERFICIE_PAGINA]
        for papel, (superficie, _) in SIGNIFICADO.items():
            if superficie != PAGINA:
                continue
            with self.subTest(papel=papel):
                razao = tokens.razao_de_contraste(RESERVA[papel], pagina)
                self.assertGreaterEqual(razao, tokens.AA_GRAFICO, f"{papel} sobre a página: {razao:.2f}:1")


if __name__ == "__main__":
    unittest.main()
