"""A ordem em que a página se lê, com o diagrama dentro dela (S-193).

**O defeito que estes testes travam é invisível.** Ordem de leitura não muda a FEN, não muda a
legenda e não aparece na tela — só aparece quando alguém exporta um livro e lê. Sem régua, uma
regressão de ordem passa meses despercebida, que foi o que aconteceu no projeto de origem: numa
página real do Kasparov, 9 saltos entre colunas onde o correto é 1.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text.boxes import Caixa, excluir_diagramas
from chess_diagram_ocr.text.pagina import Diagrama, sequencia_de_leitura
from tests.test_text_colunas import (
    ALTURA_DA_LETRA,
    DIREITA,
    ESQUERDA,
    PASSO_X,
    PASSO_Y,
    POR_LINHA,
    _linha_de_caixas,
)


def pagina_de_duas_colunas(linhas: int = 30) -> tuple[list[Caixa], list[Caixa], list[Caixa]]:
    """`(todas, da_esquerda, da_direita)`, com a ordem correta dentro de cada coluna."""
    esquerda: list[Caixa] = []
    direita: list[Caixa] = []
    for i in range(linhas):
        y = 120 + i * PASSO_Y
        esquerda.extend(_linha_de_caixas(ESQUERDA, y))
        direita.extend(_linha_de_caixas(DIREITA, y))
    # Embaralhadas na entrada: a ordem de saída não pode depender da de entrada.
    todas = [c for par in zip(esquerda, direita, strict=True) for c in par]
    return todas, esquerda, direita


class ColunaTests(unittest.TestCase):
    def test_a_pagina_de_duas_colunas_sai_coluna_a_coluna(self) -> None:
        """Antes, agrupava tudo por linha ignorando colunas: linha 1 da esquerda, linha 1 da
        direita, linha 2 da esquerda... e o texto saía embaralhado."""
        todas, esquerda, direita = pagina_de_duas_colunas()
        self.assertEqual([*esquerda, *direita], sequencia_de_leitura(todas))

    def test_a_ordem_nao_depende_da_ordem_de_entrada(self) -> None:
        todas, esquerda, direita = pagina_de_duas_colunas()
        esperado = [*esquerda, *direita]
        self.assertEqual(esperado, sequencia_de_leitura(list(reversed(todas))))

    def test_a_pagina_de_coluna_unica_sai_linha_a_linha(self) -> None:
        linhas = [_linha_de_caixas(ESQUERDA, 120 + i * PASSO_Y, quantas=30) for i in range(20)]
        esperado = [c for linha in linhas for c in linha]
        self.assertEqual(esperado, sequencia_de_leitura([c for linha in linhas for c in linha]))

    def test_pagina_vazia(self) -> None:
        self.assertEqual([], sequencia_de_leitura([]))


class TransversalTests(unittest.TestCase):
    """Título e diagrama largo não podem ser jogados numa coluna: são separador horizontal."""

    def test_o_titulo_que_atravessa_separa_o_que_esta_acima_do_que_esta_abaixo(self) -> None:
        todas, esquerda, direita = pagina_de_duas_colunas(linhas=6)
        meio = 120 + 3 * PASSO_Y - 8
        titulo = Caixa(ESQUERDA, meio, DIREITA + 200, meio + 24)

        ordem = sequencia_de_leitura([*todas, titulo])
        posicao = ordem.index(titulo)

        acima = ordem[:posicao]
        abaixo = ordem[posicao + 1 :]
        self.assertTrue(all(c.y1 < meio for c in acima if isinstance(c, Caixa)))
        self.assertTrue(all(c.y1 > meio for c in abaixo if isinstance(c, Caixa)))
        # E de cada lado do título a leitura continua sendo coluna a coluna.
        self.assertEqual([c for c in esquerda if c.y1 < meio], [c for c in acima if c.x1 < DIREITA])


class DiagramaTests(unittest.TestCase):
    def test_o_diagrama_entra_na_ordem_da_coluna(self) -> None:
        """O diagrama entre o parágrafo 3 e o 4 tem de sair entre o 3 e o 4.

        **O fixture passa por `excluir_diagramas` primeiro**, e não é detalhe de conveniência: na
        página real não há texto *debaixo* do tabuleiro, e um fixture que o mantém mede uma
        situação que não existe. É também o que prova o par exclusão/reinserção sobre o mesmo
        retângulo -- o mesmo `bbox` sai de um lado e volta do outro.

        `margem=0` porque o fixture tem linhas a cada 34 px e a margem de produção (1,4 escala)
        comeria a linha vizinha. A margem em si é medida em `test_text_boxes.py`.
        """
        todas, esquerda, direita = pagina_de_duas_colunas(linhas=8)
        # A largura cobre a coluna inteira, inclusive a última caixa da linha: com `POR_LINHA - 1`
        # o centro dela cai fora do retângulo, ela sobrevive à exclusão e fica **dentro** da faixa
        # vertical do diagrama. Um tabuleiro que cobre 15 das 16 letras da linha não existe.
        largura_da_coluna = POR_LINHA * PASSO_X
        topo = 120 + 4 * PASSO_Y
        bbox = (float(ESQUERDA), float(topo), float(ESQUERDA + largura_da_coluna), float(topo + 3 * PASSO_Y))
        diagrama = Diagrama(bbox=bbox, indice=0)

        sobraram = excluir_diagramas(todas, [bbox], escala=ALTURA_DA_LETRA, margem=0.0)
        self.assertLess(len(sobraram), len(todas), "a exclusão não tirou nada; o fixture não cobre texto")

        ordem = sequencia_de_leitura(sobraram, [diagrama])
        posicao = ordem.index(diagrama)

        da_esquerda = [c for c in ordem[:posicao] if isinstance(c, Caixa) and c.x1 < DIREITA]
        depois = [c for c in ordem[posicao + 1 :] if isinstance(c, Caixa)]
        self.assertTrue(da_esquerda, "o diagrama saiu antes de tudo")
        self.assertTrue(all(c.y1 < topo for c in da_esquerda), "o diagrama saiu tarde demais")
        self.assertTrue(any(c in direita for c in depois), "a coluna da direita sumiu")

    def test_o_diagrama_largo_e_da_pagina_e_nao_da_coluna(self) -> None:
        """O diagrama centrado que atravessa as duas colunas sai entre a linha de cima e a de
        baixo, e **não** no fim da página."""
        todas, _, _ = pagina_de_duas_colunas(linhas=8)
        topo = 120 + 4 * PASSO_Y
        largo = Diagrama(bbox=(ESQUERDA, topo, DIREITA + 200, topo + 2 * PASSO_Y), indice=0)

        ordem = sequencia_de_leitura(todas, [largo])
        posicao = ordem.index(largo)
        self.assertGreater(posicao, 0)
        self.assertLess(posicao, len(ordem) - 1, "o diagrama largo foi para o fim da página")

    def test_o_diagrama_nao_entra_na_projecao_da_calha(self) -> None:
        """**Um diagrama largo encostado na calha a apagaria**, e seria a letra do cabeçalho um
        nível acima. A calha é achada sobre as caixas de caractere, e só."""
        todas, esquerda, direita = pagina_de_duas_colunas(linhas=8)
        topo = 120 + 4 * PASSO_Y
        largo = Diagrama(bbox=(ESQUERDA, topo, DIREITA + 200, topo + 2 * PASSO_Y), indice=0)

        ordem = sequencia_de_leitura(todas, [largo])
        acima = [c for c in ordem[: ordem.index(largo)] if isinstance(c, Caixa)]
        # A parte de cima continua saindo coluna a coluna: esquerda inteira, depois direita.
        da_esquerda_acima = [c for c in esquerda if c.y1 < topo]
        self.assertEqual(da_esquerda_acima, acima[: len(da_esquerda_acima)])

    def test_a_exclusao_e_a_reinsercao_usam_o_mesmo_bbox(self) -> None:
        """Duas verdades sobre onde o diagrama está produziriam um buraco ou um objeto duplicado.

        `boxes.excluir_diagramas` recebe o retângulo e a sequência de leitura o reinsere; os dois
        vêm do mesmo `bbox` que a S-12 carrega em cada candidato.
        """
        bbox = (100.0, 200.0, 400.0, 500.0)
        diagrama = Diagrama(bbox=bbox, indice=3)
        caixa = diagrama.caixa
        self.assertEqual((100, 200, 400, 500), (caixa.x1, caixa.y1, caixa.x2, caixa.y2))
        self.assertEqual(bbox, diagrama.bbox)

    def test_o_indice_do_candidato_sobrevive(self) -> None:
        """É por ele que o chamador reencontra a FEN do diagrama que acabou de posicionar."""
        ordem = sequencia_de_leitura([Caixa(0, 0, 10, 20)], [Diagrama(bbox=(0.0, 40.0, 100.0, 140.0), indice=7)])
        diagramas = [e for e in ordem if isinstance(e, Diagrama)]
        self.assertEqual([7], [d.indice for d in diagramas])

    def test_pagina_so_de_diagramas(self) -> None:
        """Sem caixa de caractere não há calha a detectar, e a ordem é a geométrica."""
        de_cima = Diagrama(bbox=(0.0, 0.0, 100.0, 100.0), indice=0)
        de_baixo = Diagrama(bbox=(0.0, 200.0, 100.0, 300.0), indice=1)
        self.assertEqual([de_cima, de_baixo], sequencia_de_leitura([], [de_baixo, de_cima]))


class ArranjoDeGradeTests(unittest.TestCase):
    """O diagrama dentro de uma grade lida em fileiras (S-216).

    A separação grade/prosa e a direção estão em `test_text_grade.py`; o que se trava aqui é o que
    é **desta** camada: o diagrama continua sendo um objeto da célula quando a página se lê
    atravessando as colunas.
    """

    def test_o_diagrama_entra_na_fileira_da_celula_dele(self) -> None:
        """O tabuleiro da célula do meio sai **na fileira do meio**, e não na de cima.

        **O elemento entra pelo topo dele, e é o que os três livros de grade do acervo pedem.**
        Nos três -- `Karpov`, `Schiller` e `Burgess` -- a legenda vem *acima* do tabuleiro, então
        o topo do tabuleiro cai depois da legenda dele e antes do corte seguinte. Casar pelo
        centro o empurraria uma fileira adiante em todos eles.

        O limite conhecido: numa diagramação com a legenda *abaixo* do tabuleiro, o corte cairia
        no meio do tabuleiro e o topo o deixaria na fileira anterior. Nenhum livro deste acervo
        diagrama assim, e por isso a regra não foi escrita para um caso que ninguém pôde medir.
        """
        from tests.test_text_grade import ALTURA_DA_FILEIRA, TOPO, grade_de_exercicios
        from tests.test_text_grade import ESQUERDA as X_ESQ

        todas, celulas = grade_de_exercicios()
        topo_do_quadro = float(TOPO + ALTURA_DA_FILEIRA + 2 * PASSO_Y + 26)  # logo abaixo da legenda
        quadro = Diagrama(bbox=(float(X_ESQ), topo_do_quadro, float(X_ESQ + 140), topo_do_quadro + 220), indice=4)

        ordem = sequencia_de_leitura(todas, [quadro], arranjo="grade")

        esperado = [*celulas[0], *celulas[1], *celulas[2], quadro, *celulas[3], *celulas[4], *celulas[5]]
        self.assertEqual(esperado, ordem)

    def test_o_diagrama_nao_apaga_o_vao_que_parte_a_fileira(self) -> None:
        """**Mesmo motivo da calha, no outro eixo.** O diagrama *preenche* o vão entre fileiras;
        deixá-lo entrar na projeção apagaria todos os cortes e a grade voltaria a sair coluna a
        coluna. Os cortes saem das caixas de caractere, e só."""
        from tests.test_text_grade import ALTURA_DA_FILEIRA, TOPO, grade_de_exercicios
        from tests.test_text_grade import ESQUERDA as X_ESQ

        todas, celulas = grade_de_exercicios()
        quadros = [
            Diagrama(
                bbox=(float(X_ESQ), float(TOPO + f * ALTURA_DA_FILEIRA + 40), float(X_ESQ + 140),
                      float(TOPO + f * ALTURA_DA_FILEIRA + 280)),
                indice=f,
            )
            for f in range(2)
        ]
        sem = sequencia_de_leitura(todas, arranjo="grade")
        com = [e for e in sequencia_de_leitura(todas, quadros, arranjo="grade") if isinstance(e, Caixa)]
        self.assertEqual(sem, com, "os diagramas mudaram a ordem das legendas")

    def test_o_arranjo_de_prosa_e_o_padrao_tambem_com_diagrama(self) -> None:
        todas, _, _ = pagina_de_duas_colunas(linhas=8)
        largo = Diagrama(bbox=(ESQUERDA, 120.0, DIREITA + 200, 200.0), indice=0)
        self.assertEqual(
            sequencia_de_leitura(todas, [largo]),
            sequencia_de_leitura(todas, [largo], arranjo="prosa"),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
