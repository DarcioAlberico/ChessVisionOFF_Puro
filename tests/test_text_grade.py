"""A grade de exercícios, e a direção que só o número impresso diz (S-216).

**O par de fixtures é o item.** Uma página de prosa densa em duas colunas e uma folha de
exercícios esparsa: as duas têm duas colunas, as duas têm as linhas das duas colunas pareadas no
mesmo `y`, e elas se leem em ordens diferentes. O que as separa é o vão que atravessa a página, e
é isso que `test_a_prosa_densa_nao_e_grade` e `test_a_grade_esparsa_e_grade` travam.

**O que estes testes deliberadamente não travam é a direção.** Ela não sai da geometria: o
`Schiller` e o `Karpov` têm grades indistinguíveis numeradas ao contrário uma da outra, e por isso
`sequencia_de_leitura` não adivinha -- recebe `arranjo` de fora. `DirecaoTests` prova que o número
impresso responde onde a geometria não responde.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.colunas import detectar_colunas
from chess_diagram_ocr.text.grade import (
    CORRIDA_MINIMA,
    FRACAO_DE_VAO,
    VAO_DE_FILEIRA,
    corrida_de_exercicio,
    cortes_de_fileira,
    direcao_pela_numeracao,
    fracao_de_vao,
    parece_grade,
    vaos_entre_bandas,
)
from chess_diagram_ocr.text.pagina import sequencia_de_leitura
from tests.test_text_colunas import (
    ALTURA_DA_LETRA,
    DIREITA,
    ESQUERDA,
    PASSO_Y,
    _linha_de_caixas,
    duas_colunas,
)

POR_CELULA = 8
"""Caixas por linha de legenda. 8 x 18 = 144 px de célula, contra os 276 px de calha que sobram."""

FILEIRAS = 3
LINHAS_POR_CELULA = 2
ALTURA_DA_FILEIRA = 300
"""Passo entre fileiras. O vão que sobra é 246 px, contra os 14 px entre as duas linhas da célula.

É a proporção real: o vão de fileira é a altura de um tabuleiro, e o entrelinha é entrelinha."""

TOPO = 100


def _celula(coluna_x: int, y: int) -> list[Caixa]:
    """Uma célula da grade: a linha do número e a linha da legenda, na ordem em que se leem."""
    return [
        *_linha_de_caixas(coluna_x, y, quantas=POR_CELULA),
        *_linha_de_caixas(coluna_x, y + PASSO_Y, quantas=POR_CELULA),
    ]


def grade_de_exercicios() -> tuple[list[Caixa], list[list[Caixa]]]:
    """`(todas, células)`, com as células em ordem **de fileira**: (0,0), (0,1), (1,0), (1,1)...

    É a diagramação do `Karpov` e do `Burgess`: 3 fileiras de 2 células, cada célula com um
    tabuleiro em cima (que não está aqui -- ele é o vão) e duas linhas de legenda embaixo.
    """
    celulas: list[list[Caixa]] = []
    for fileira in range(FILEIRAS):
        y = TOPO + fileira * ALTURA_DA_FILEIRA
        celulas.append(_celula(ESQUERDA, y))
        celulas.append(_celula(DIREITA, y))
    # Embaralhadas na entrada: a ordem de saída não pode depender da ordem de entrada.
    todas = [c for celula in reversed(celulas) for c in celula]
    return todas, celulas


def numeros_da_grade(celulas: list[list[Caixa]], *, por_fileira: bool) -> list[tuple[int, Caixa]]:
    """O número impresso em cada célula, na caixa em que ele está.

    `por_fileira=True` é o `Karpov` (1 2 / 3 4 / 5 6); `False` é o `Schiller` (1 4 / 2 5 / 3 6).
    """
    numerados: list[tuple[int, Caixa]] = []
    for indice, celula in enumerate(celulas):
        fileira, coluna = divmod(indice, 2)
        numero = 1 + (fileira * 2 + coluna if por_fileira else coluna * FILEIRAS + fileira)
        numerados.append((numero, celula[0]))
    return numerados


class SeparacaoTests(unittest.TestCase):
    """A metade do problema que a geometria resolve: grade não é prosa."""

    def test_a_prosa_densa_nao_e_grade(self) -> None:
        caixas = duas_colunas(linhas=30)
        self.assertEqual([], cortes_de_fileira(caixas))
        self.assertFalse(parece_grade(caixas, colunas=detectar_colunas(caixas)))
        self.assertAlmostEqual(0.0, fracao_de_vao(caixas))

    def test_a_grade_esparsa_e_grade(self) -> None:
        todas, _ = grade_de_exercicios()
        self.assertTrue(parece_grade(todas, colunas=detectar_colunas(todas)))
        self.assertEqual(FILEIRAS - 1, len(cortes_de_fileira(todas)))
        self.assertGreater(fracao_de_vao(todas), FRACAO_DE_VAO)

    def test_o_entrelinha_da_celula_nao_parte_a_fileira(self) -> None:
        """**O corte é entre fileiras, e não entre as duas linhas da legenda.** Sem isto a célula
        de duas linhas sairia partida e a legenda apareceria em dois pedaços."""
        todas, celulas = grade_de_exercicios()
        cortes = cortes_de_fileira(todas)
        for celula in celulas:
            topo = min(c.y1 for c in celula)
            fundo = max(c.y2 for c in celula)
            self.assertFalse(
                any(topo < corte < fundo for corte in cortes),
                "um corte caiu dentro de uma célula",
            )

    def test_a_pagina_de_uma_coluna_nunca_e_grade(self) -> None:
        """Com uma coluna, fileira e linha são a mesma coisa: a pergunta não tem conteúdo."""
        todas, _ = grade_de_exercicios()
        self.assertFalse(parece_grade(todas, colunas=[(0, 900)]))

    def test_o_vao_e_medido_entre_bandas_e_nao_dentro_delas(self) -> None:
        todas, _ = grade_de_exercicios()
        vaos = [topo - fundo for fundo, topo in vaos_entre_bandas(todas)]
        entrelinhas = [v for v in vaos if v < VAO_DE_FILEIRA * ALTURA_DA_LETRA]
        de_fileira = [v for v in vaos if v >= VAO_DE_FILEIRA * ALTURA_DA_LETRA]
        self.assertEqual(FILEIRAS, len(entrelinhas), "uma entrelinha por célula empilhada")
        self.assertEqual(FILEIRAS - 1, len(de_fileira))
        # E os dois montes não se tocam: é o que faz o limiar não ser delicado.
        self.assertGreater(min(de_fileira), 10 * max(entrelinhas))

    def test_a_mesma_grade_em_caixa_de_linha_da_o_mesmo_veredito(self) -> None:
        """**A régua vale para os dois alimentadores.** A camada de texto entrega uma caixa por
        linha; a segmentação da S-185 entrega uma por caractere. O limiar é em alturas medianas,
        e é por isso que ele atravessa a diferença."""
        todas, celulas = grade_de_exercicios()
        por_linha = [
            Caixa(min(c.x1 for c in linha), linha[0].y1, max(c.x2 for c in linha), linha[0].y2)
            for celula in celulas
            for linha in (celula[:POR_CELULA], celula[POR_CELULA:])
        ]
        self.assertTrue(parece_grade(por_linha, colunas=detectar_colunas(por_linha)))
        self.assertEqual(len(cortes_de_fileira(todas)), len(cortes_de_fileira(por_linha)))


class OrdemTests(unittest.TestCase):
    def test_a_grade_sai_celula_a_celula_atravessando_as_colunas(self) -> None:
        """O defeito da S-193 nesta página: ela lia a coluna da esquerda inteira primeiro."""
        todas, celulas = grade_de_exercicios()
        esperado = [c for celula in celulas for c in celula]
        self.assertEqual(esperado, sequencia_de_leitura(todas, arranjo="grade"))

    def test_o_padrao_continua_sendo_prosa(self) -> None:
        """`arranjo` não tem detecção automática, e o padrão é o lado seguro do erro."""
        todas, celulas = grade_de_exercicios()
        coluna_a_coluna = [c for i in (0, 2, 4, 1, 3, 5) for c in celulas[i]]
        self.assertEqual(coluna_a_coluna, sequencia_de_leitura(todas))
        self.assertEqual(sequencia_de_leitura(todas), sequencia_de_leitura(todas, arranjo="prosa"))

    def test_pedir_grade_numa_pagina_de_prosa_nao_muda_nada(self) -> None:
        """**A segurança é estrutural, e não só o padrão.** Prosa não tem vão de fileira, então
        não há onde partir: mesmo um chamador que erre o `arranjo` recebe a leitura de prosa.

        Medido também fora do fixture: nas páginas de prosa densa do acervo o `tau` sob
        `arranjo="grade"` é idêntico ao de `arranjo="prosa"`, até a última casa."""
        caixas = duas_colunas(linhas=30)
        self.assertEqual(sequencia_de_leitura(caixas), sequencia_de_leitura(caixas, arranjo="grade"))


class DirecaoTests(unittest.TestCase):
    """A metade que a geometria **não** resolve, e que só o número impresso resolve."""

    def test_as_duas_grades_sao_geometricamente_iguais(self) -> None:
        """O teste que justifica o parâmetro `arranjo` existir.

        A mesma página, numerada das duas maneiras, é a mesma página para toda régua geométrica
        deste módulo. Se algum dia uma delas as distinguir, este teste falha e a S-216 muda.
        """
        todas, celulas = grade_de_exercicios()
        colunas = detectar_colunas(todas)
        self.assertTrue(parece_grade(todas, colunas=colunas))
        self.assertNotEqual(
            direcao_pela_numeracao(numeros_da_grade(celulas, por_fileira=True), colunas=colunas),
            direcao_pela_numeracao(numeros_da_grade(celulas, por_fileira=False), colunas=colunas),
            "a mesma geometria tem de admitir as duas direções",
        )

    def test_a_numeracao_atravessando_as_colunas_pede_grade(self) -> None:
        """`1 2 / 3 4 / 5 6` -- a diagramação do `Karpov` e do `Burgess`."""
        todas, celulas = grade_de_exercicios()
        colunas = detectar_colunas(todas)
        self.assertEqual(
            "grade", direcao_pela_numeracao(numeros_da_grade(celulas, por_fileira=True), colunas=colunas)
        )

    def test_a_numeracao_descendo_a_coluna_pede_prosa(self) -> None:
        """`1 4 / 2 5 / 3 6` -- a diagramação do `Schiller`, que a S-193 já lê certo."""
        todas, celulas = grade_de_exercicios()
        colunas = detectar_colunas(todas)
        self.assertEqual(
            "prosa", direcao_pela_numeracao(numeros_da_grade(celulas, por_fileira=False), colunas=colunas)
        )

    def test_a_direcao_calibrada_ordena_cada_grade_na_ordem_dos_numeros(self) -> None:
        """O item inteiro, de ponta a ponta: o número decide o `arranjo`, e o `arranjo` ordena."""
        todas, celulas = grade_de_exercicios()
        colunas = detectar_colunas(todas)
        for por_fileira in (True, False):
            numerados = numeros_da_grade(celulas, por_fileira=por_fileira)
            arranjo = direcao_pela_numeracao(numerados, colunas=colunas)
            assert arranjo is not None
            ordem = sequencia_de_leitura(todas, colunas=colunas, arranjo=arranjo)
            saiu = [numero for numero, caixa in sorted(numerados, key=lambda a: ordem.index(a[1]))]
            self.assertEqual(sorted(saiu), saiu, f"grade {por_fileira=} saiu fora da numeração")

    def test_a_corrida_precisa_dobrar_a_esquina(self) -> None:
        """Três números não decidem: numa grade 2x3 eles crescem para baixo **e** para o lado."""
        self.assertEqual(4, CORRIDA_MINIMA)
        _, celulas = grade_de_exercicios()
        tres = numeros_da_grade(celulas, por_fileira=True)[:3]
        self.assertEqual([], corrida_de_exercicio(tres))

    def test_numero_que_nao_e_exercicio_nao_entra_na_corrida(self) -> None:
        """Ano de partida e número de página também são inteiros. O que identifica exercício é a
        numeração seguir sem buraco."""
        _, celulas = grade_de_exercicios()
        numerados = numeros_da_grade(celulas, por_fileira=True)
        com_ruido = [*numerados, (1931, celulas[0][1]), (1994, celulas[1][1])]
        self.assertEqual(
            [n for n, _ in numerados], [n for n, _ in corrida_de_exercicio(com_ruido)]
        )

    def test_a_pagina_sem_numeracao_nao_opina(self) -> None:
        """`None` é "esta página não responde", e o chamador continua em prosa."""
        todas, _ = grade_de_exercicios()
        self.assertIsNone(direcao_pela_numeracao([], colunas=detectar_colunas(todas)))

    def test_a_pagina_de_uma_coluna_nao_opina(self) -> None:
        _, celulas = grade_de_exercicios()
        numerados = numeros_da_grade(celulas, por_fileira=True)
        self.assertIsNone(direcao_pela_numeracao(numerados, colunas=[(0, 900)]))


class LimiarTests(unittest.TestCase):
    """Os dois números medidos, e o que acontece se alguém os trocar por "qualquer vão"."""

    def test_qualquer_vao_transformaria_prosa_em_grade(self) -> None:
        """**É o defeito que `FRACAO_DE_VAO` existe para impedir.** Sem o piso, o entrelinha de
        uma página de prosa abre fileira em cada linha e a página sai lida linha a linha --
        exatamente a leitura que a S-193 corrigiu."""
        caixas = duas_colunas(linhas=30)
        self.assertNotEqual([], cortes_de_fileira(caixas, vao_minimo=1))
        self.assertGreater(fracao_de_vao(caixas, vao_minimo=1), FRACAO_DE_VAO)
        self.assertEqual([], cortes_de_fileira(caixas))

    def test_o_limiar_esta_entre_as_duas_populacoes_medidas(self) -> None:
        """0,30 fica 2,0x acima da maior prosa densa do acervo (0,153) e 2,1x abaixo da menor
        grade (0,634). Ver o cabeçalho de `FRACAO_DE_VAO`."""
        self.assertLess(0.153, FRACAO_DE_VAO)
        self.assertLess(FRACAO_DE_VAO, 0.634)

    def test_uma_figura_no_meio_da_prosa_nao_faz_grade(self) -> None:
        """O caso que o piso existe para recusar: prosa densa com **um** vão largo no meio.

        Medido no acervo, a página do `Yusupov` com figura larga dá 0,15 -- vão largo de verdade,
        e ainda assim metade do limiar."""
        de_cima = [c for i in range(14) for c in (*_linha_de_caixas(ESQUERDA, 100 + i * PASSO_Y),
                                                  *_linha_de_caixas(DIREITA, 100 + i * PASSO_Y))]
        base = 100 + 14 * PASSO_Y + 8 * ALTURA_DA_LETRA
        de_baixo = [c for i in range(14) for c in (*_linha_de_caixas(ESQUERDA, base + i * PASSO_Y),
                                                   *_linha_de_caixas(DIREITA, base + i * PASSO_Y))]
        pagina = [*de_cima, *de_baixo]
        self.assertEqual(1, len(cortes_de_fileira(pagina)), "o fixture tem de ter um vão largo")
        self.assertFalse(parece_grade(pagina, colunas=detectar_colunas(pagina)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
