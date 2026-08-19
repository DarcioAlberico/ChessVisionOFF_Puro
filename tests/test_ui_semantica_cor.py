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


class ContrasteDasMarcacoesTests(unittest.TestCase):
    """Trocar de matiz não pode custar legibilidade — e aqui ela **melhorou**."""

    def test_as_marcacoes_do_tabuleiro_contrastam_com_as_duas_casas(self) -> None:
        """O contorno tem de ser visto na casa clara **e** na escura: metade do tabuleiro é cada.

        O azul antigo dava 1,31:1 sobre a casa escura -- desenhado e invisível em metade das
        casas, que é o mesmo defeito da S-146 num lugar que ninguém tinha medido.
        """
        self.assertLess(
            tokens.razao_de_contraste("#3d7dd4", RESERVA[tokens.CASA_ESCURA]), 2.0, "o valor antigo, para o registro"
        )
        for casa in (tokens.CASA_CLARA, tokens.CASA_ESCURA):
            with self.subTest(casa=casa):
                razao = tokens.razao_de_contraste(RESERVA[tokens.CORRIGIDO], RESERVA[casa])
                self.assertGreaterEqual(razao, tokens.AA_GRAFICO, f"CORRIGIDO sobre {casa}: {razao:.2f}:1")

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
