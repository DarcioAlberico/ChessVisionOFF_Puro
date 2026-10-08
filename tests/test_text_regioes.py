"""A região horizontal, e o parágrafo de largura inteira que apagava a calha (S-507).

**O teste que dá nome a este arquivo é `test_o_bloco_de_largura_inteira_nao_apaga_a_calha`.** A
S-190 tolera **uma** linha na calha, e esse número está medido; um parágrafo de abertura tem
quatro. Com a régua de folha, a página de duas colunas com um bloco desses em cima sai como
**uma** coluna, e a leitura intercala as duas colunas linha a linha.

Os fixtures são os mesmos de `test_text_colunas.py`, e de propósito: o que muda aqui não é a
geometria da calha, é até onde ela vale. Nada aqui precisa de imagem.
"""

from __future__ import annotations

import unittest

from test_text_colunas import (  # type: ignore[import-not-found]
    ALTURA_DA_LETRA,
    DIREITA,
    ESQUERDA,
    LARGURA_DA_LETRA,
    PASSO_X,
    PASSO_Y,
    POR_LINHA,
    duas_colunas,
    uma_coluna,
)

from chess_diagram_ocr.config import DEFAULT_PDF_DIR
from chess_diagram_ocr.text import regioes as regioes_mod
from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.colunas import LINHAS_NA_CALHA, detectar_colunas
from chess_diagram_ocr.text.regioes import (
    BANDAS_NA_REGIAO,
    BORDA_MAX,
    VAO_DE_BORDA,
    Regiao,
    atribuir_regiao,
    colunas_da_folha,
    detectar_regioes,
)

LARGURA_INTEIRA = 2 * POR_LINHA + 1
"""Caixas numa linha que vai de margem a margem, cobrindo a calha."""


def _linha_larga(y: int) -> list[Caixa]:
    """Uma linha que atravessa a folha inteira, como a de um parágrafo de abertura."""
    return [
        Caixa(ESQUERDA + i * PASSO_X, y, ESQUERDA + i * PASSO_X + LARGURA_DA_LETRA, y + ALTURA_DA_LETRA)
        for i in range(LARGURA_INTEIRA)
    ]


def _bloco_largo(y0: int, linhas: int) -> list[Caixa]:
    return [c for i in range(linhas) for c in _linha_larga(y0 + i * PASSO_Y)]


def com_bloco_no_topo(linhas_do_bloco: int = 4, linhas_de_coluna: int = 30) -> list[Caixa]:
    """A folha da queixa: um parágrafo de largura inteira em cima de duas colunas."""
    bloco = _bloco_largo(20, linhas_do_bloco)
    abaixo = 20 + linhas_do_bloco * PASSO_Y + PASSO_Y
    colunas = [
        c
        for i in range(linhas_de_coluna)
        for c in (
            *_linha_de(ESQUERDA, abaixo + i * PASSO_Y),
            *_linha_de(DIREITA, abaixo + i * PASSO_Y),
        )
    ]
    return [*bloco, *colunas]


def _linha_de(x0: int, y: int, quantas: int = POR_LINHA) -> list[Caixa]:
    return [
        Caixa(x0 + i * PASSO_X, y, x0 + i * PASSO_X + LARGURA_DA_LETRA, y + ALTURA_DA_LETRA)
        for i in range(quantas)
    ]


class FolhaHomogeneaTests(unittest.TestCase):
    """**A folha inteira é tentada primeiro**, e é isso que preserva o que a S-190 mediu."""

    def test_duas_colunas_saem_numa_regiao_so(self) -> None:
        regioes = detectar_regioes(duas_colunas())
        self.assertEqual(1, len(regioes), f"a folha foi partida à toa: {regioes}")
        self.assertEqual(tuple(detectar_colunas(duas_colunas())), regioes[0].colunas)

    def test_coluna_unica_nao_ganha_coluna_nenhuma(self) -> None:
        """O controle. A busca por região olha **toda** janela de bandas, e é aí que ela poderia
        inventar calha onde a régua de folha não inventa."""
        regioes = detectar_regioes(uma_coluna())
        self.assertEqual([1], sorted({len(r.colunas) for r in regioes}), f"inventou coluna: {regioes}")

    def test_sem_caixa_nenhuma_nao_ha_regiao(self) -> None:
        self.assertEqual([], detectar_regioes([]))


class BlocoDeLarguraInteiraTests(unittest.TestCase):
    """O item. Quatro linhas cobrindo a calha, e a folha inteira virava uma coluna."""

    def test_a_regua_de_folha_perde_a_calha(self) -> None:
        """A premissa da S-507, travada: sem região, esta folha é de **uma** coluna."""
        self.assertEqual(1, len(detectar_colunas(com_bloco_no_topo())))

    def test_o_bloco_de_largura_inteira_nao_apaga_a_calha(self) -> None:
        regioes = detectar_regioes(com_bloco_no_topo())
        self.assertEqual(2, len(regioes), f"esperava topo + colunas, veio {regioes}")
        self.assertTrue(regioes[0].transversal, "o bloco de abertura não é coluna de nada")
        self.assertEqual(2, len(regioes[1].colunas), "a região de baixo é de duas colunas")

    def test_a_regiao_de_baixo_acha_a_mesma_calha_da_folha_sem_o_bloco(self) -> None:
        """A calha não muda de lugar por causa do que está acima dela."""
        sozinhas = detectar_regioes(duas_colunas())[0].colunas
        com_bloco = detectar_regioes(com_bloco_no_topo())[1].colunas
        self.assertEqual(len(sozinhas), len(com_bloco))
        for (a1, a2), (b1, b2) in zip(sozinhas, com_bloco, strict=True):
            self.assertLessEqual(abs(a1 - b1), PASSO_X, f"{sozinhas} contra {com_bloco}")
            self.assertLessEqual(abs(a2 - b2), PASSO_X, f"{sozinhas} contra {com_bloco}")

    def test_o_bloco_no_pe_da_folha_tambem_vira_regiao(self) -> None:
        """Nota de rodapé de largura inteira: mesma história, do outro lado."""
        colunas = duas_colunas()
        base = max(c.y2 for c in colunas)
        caixas = [*colunas, *_bloco_largo(base + PASSO_Y, 4)]
        regioes = detectar_regioes(caixas)
        self.assertEqual(2, len(regioes))
        self.assertEqual(2, len(regioes[0].colunas))
        self.assertTrue(regioes[1].transversal)

    def test_a_linha_tolerada_no_meio_vira_regiao_de_uma_coluna(self) -> None:
        """**A banda que cruza a calha não pode ser partida na calha.**

        Ela cabe na tolerância da S-190 e sobreviveria dentro da região colunar -- e aí o motor
        de glifo, que atribui caractere a coluna, cortaria a linha em duas metades.
        """
        caixas = duas_colunas(30)
        meio = 120 + 15 * PASSO_Y
        caixas = [c for c in caixas if c.y1 != meio]
        caixas.extend(_linha_larga(meio))
        regioes = detectar_regioes(caixas)
        self.assertEqual(3, len(regioes), f"esperava colunas / linha larga / colunas: {regioes}")
        self.assertTrue(regioes[1].transversal)
        self.assertTrue(regioes[1].topo <= meio <= regioes[1].base)
        self.assertEqual([2, 2], [len(regioes[0].colunas), len(regioes[2].colunas)])


CURTAS = (5, 4, 17, 6, 3)
"""Comprimentos, em caixas, das linhas de uma coluna de solução («1.♗h3!», «(1 point)»): a mediana
fica em 5 de 17 da coluna, bem abaixo do `PREENCHIMENTO_DA_COLUNA`."""

CALHA_ESTREITA = 30
"""A calha da página de soluções, em px: duas letras. A dos fixtures de `test_text_colunas` tem
110 px, e nela um fólio de uma caixa não fecha nada -- na página real (11 pt) ele fecha."""

DIREITA_ESTREITA = ESQUERDA + POR_LINHA * PASSO_X + CALHA_ESTREITA
MEIO = ESQUERDA + POR_LINHA * PASSO_X + CALHA_ESTREITA // 2
"""O meio da calha estreita."""


def colunas_de_solucao(linhas: int = 30, y0: int = 120) -> list[Caixa]:
    """Duas colunas de linha curta com a calha estreita, como as páginas «Solutions» do Yusupov."""
    caixas: list[Caixa] = []
    for i in range(linhas):
        y = y0 + i * PASSO_Y
        caixas.extend(_linha_de(ESQUERDA, y, CURTAS[i % len(CURTAS)]))
        caixas.extend(_linha_de(DIREITA_ESTREITA, y, CURTAS[(i + 2) % len(CURTAS)]))
    return caixas


def _titulo(y: int) -> list[Caixa]:
    """Um título centralizado: seis caixas em volta do meio da folha, cobrindo a calha."""
    return _linha_de(MEIO - 3 * PASSO_X, y, 6)


def _folio(y: int) -> list[Caixa]:
    """O número de página, duas caixas que fecham a calha estreita (sobra menos que o piso)."""
    return _linha_de(MEIO - PASSO_X + 2, y, 2)


def pagina_de_solucoes(vao: int = 3, linhas: int = 30) -> list[Caixa]:
    """A folha da queixa (S-523): título e fólio na calha, `vao` passos afastados do corpo de
    linhas curtas."""
    corpo = colunas_de_solucao(linhas)
    ultima = 120 + (linhas - 1) * PASSO_Y
    return [*_titulo(120 - vao * PASSO_Y), *corpo, *_folio(ultima + vao * PASSO_Y)]


class BandaIsoladaNaBordaTests(unittest.TestCase):
    """O item S-523. Título e fólio cruzam a calha -- duas bandas, e a folha tolera uma --, e o
    corpo de linhas curtas não passa no preenchimento da busca por região."""

    def test_a_regua_de_folha_perde_a_calha(self) -> None:
        """A premissa, travada: pela régua da S-190 esta folha é de **uma** coluna."""
        self.assertEqual(1, len(detectar_colunas(pagina_de_solucoes())))

    def test_o_titulo_e_o_folio_isolados_nao_apagam_a_calha(self) -> None:
        regioes = detectar_regioes(pagina_de_solucoes())
        self.assertEqual([1, 2, 1], [len(r.colunas) for r in regioes], f"veio {regioes}")
        self.assertTrue(regioes[0].transversal and regioes[2].transversal)
        self.assertLessEqual(regioes[0].base, 120, "o título é a região do topo")

    def test_o_corpo_acha_a_mesma_calha_da_folha_sem_as_bordas(self) -> None:
        sozinhas = detectar_regioes(colunas_de_solucao())[0].colunas
        com_bordas = detectar_regioes(pagina_de_solucoes())[1].colunas
        self.assertEqual(len(sozinhas), len(com_bordas))
        for (a1, a2), (b1, b2) in zip(sozinhas, com_bordas, strict=True):
            self.assertLessEqual(abs(a1 - b1), PASSO_X, f"{sozinhas} contra {com_bordas}")
            self.assertLessEqual(abs(a2 - b2), PASSO_X, f"{sozinhas} contra {com_bordas}")

    def test_a_banda_colada_ao_corpo_nao_e_borda(self) -> None:
        """Título a um passo do corpo: não está isolado, e a folha segue o caminho de sempre --
        que aqui é a busca por região, e ela reprova a coluna de linha curta no preenchimento.

        **É o limite desta régua, registrado e não escondido**: o preenchimento é o passo 3 do
        plano. O que o teste trava é que a borda não é inventada onde não há vão.
        """
        regioes = detectar_regioes(pagina_de_solucoes(vao=1))
        self.assertEqual([1], sorted({len(r.colunas) for r in regioes}), f"inventou borda: {regioes}")

    def test_onde_a_folha_inteira_acha_calha_nada_muda(self) -> None:
        """Só o título, tolerado pela S-190: uma região, duas colunas, como antes do item."""
        caixas = [*_titulo(120 - 3 * PASSO_Y), *duas_colunas()]
        regioes = detectar_regioes(caixas)
        self.assertEqual(1, len(regioes), f"a borda não devia entrar aqui: {regioes}")
        self.assertEqual(len(detectar_colunas(duas_colunas())), len(regioes[0].colunas))

    def test_a_coluna_unica_com_titulo_e_folio_continua_de_uma_coluna(self) -> None:
        """O controle: o corpo sem as bordas é tentado com a régua de folha, e ela não inventa
        calha numa coluna única."""
        corpo = uma_coluna()
        ultima = max(c.y1 for c in corpo)
        caixas = [*_titulo(120 - 3 * PASSO_Y), *corpo, *_folio(ultima + 3 * PASSO_Y)]
        regioes = detectar_regioes(caixas)
        self.assertEqual([1], sorted({len(r.colunas) for r in regioes}), f"inventou coluna: {regioes}")

    def test_uma_banda_so_na_calha_e_a_tolerancia_da_folha_e_nao_a_borda(self) -> None:
        """Só o fólio: a S-190 tolera uma banda, a folha inteira acha a calha, uma região."""
        corpo = colunas_de_solucao()
        regioes = detectar_regioes([*corpo, *_folio(120 + 32 * PASSO_Y)])
        self.assertEqual([2], [len(r.colunas) for r in regioes], f"veio {regioes}")

    def test_as_duas_bandas_podem_estar_na_mesma_borda(self) -> None:
        """Título e subtítulo no topo, isolados um do outro e do corpo; e o espelho na base."""
        corpo = colunas_de_solucao()
        topo = [*_titulo(120 - 6 * PASSO_Y), *_titulo(120 - 3 * PASSO_Y), *corpo]
        self.assertEqual([1, 2], [len(r.colunas) for r in detectar_regioes(topo)])
        ultima = 120 + 29 * PASSO_Y
        base = [*corpo, *_folio(ultima + 3 * PASSO_Y), *_titulo(ultima + 6 * PASSO_Y)]
        self.assertEqual([2, 1], [len(r.colunas) for r in detectar_regioes(base)])

    def test_cada_borda_cede_no_maximo_duas_bandas(self) -> None:
        corpo = colunas_de_solucao()
        topo = 120
        tres = [*_titulo(topo - 9 * PASSO_Y), *_titulo(topo - 6 * PASSO_Y), *_titulo(topo - 3 * PASSO_Y)]
        grupos = regioes_mod.bandas([*tres, *corpo])
        a, b = regioes_mod._bandas_isoladas_nas_bordas(grupos)
        self.assertEqual((BORDA_MAX, len(grupos)), (a, b))

    def test_o_vao_e_medido_em_passos_do_corpo(self) -> None:
        """Um título a `VAO_DE_BORDA` passos exatos é borda; um pouco menos, não."""
        corpo = colunas_de_solucao()
        grupos = regioes_mod.bandas([*_titulo(120 - int(VAO_DE_BORDA * PASSO_Y)), *corpo])
        self.assertEqual(1, regioes_mod._bandas_isoladas_nas_bordas(grupos)[0])
        grupos = regioes_mod.bandas([*_titulo(120 - int(VAO_DE_BORDA * PASSO_Y) + 2), *corpo])
        self.assertEqual(0, regioes_mod._bandas_isoladas_nas_bordas(grupos)[0])


class QuadroDeLarguraInteiraTests(unittest.TestCase):
    """O item S-525. O quadro «Scoring» tem cinco bandas cruzando a calha; a borda cede duas. Já
    achado (`text/quadros.py`), ele entra aqui como intervalo de `y`, vira região de uma coluna, e
    a folha é cortada em volta dele."""

    def _quadro(self, y0: int, linhas: int = 5) -> tuple[tuple[int, int], list[Caixa]]:
        """Linhas centradas que cobrem a calha estreita inteira, como as do «Scoring»."""
        caixas = [c for i in range(linhas) for c in _linha_de(ESQUERDA + 40, y0 + i * PASSO_Y, 17)]
        return (y0 - 5, y0 + linhas * PASSO_Y), caixas

    def test_o_quadro_no_pe_da_folha_vira_regiao_e_as_solucoes_acham_a_calha(self) -> None:
        corpo = colunas_de_solucao()
        ultima = 120 + 29 * PASSO_Y
        quadro, dentro = self._quadro(ultima + 3 * PASSO_Y)
        caixas = [*_titulo(120 - 3 * PASSO_Y), *corpo, *dentro, *_folio(quadro[1] + 3 * PASSO_Y)]
        self.assertEqual([1], sorted({len(r.colunas) for r in detectar_regioes(caixas)}), "sem o quadro, a premissa")
        regioes = detectar_regioes(caixas, quadros=[quadro])
        self.assertEqual([1, 2, 1], [len(r.colunas) for r in regioes], f"veio {regioes}")
        self.assertTrue(regioes[2].topo <= quadro[0] + 5 <= regioes[2].base, "o quadro está na região do pé")

    def test_o_quadro_no_meio_corta_a_folha_em_dois_trechos(self) -> None:
        cima = colunas_de_solucao(14)
        quadro, dentro = self._quadro(120 + 14 * PASSO_Y + 2 * PASSO_Y, linhas=3)
        baixo = colunas_de_solucao(14, y0=quadro[1] + 2 * PASSO_Y)
        regioes = detectar_regioes([*cima, *dentro, *baixo], quadros=[quadro])
        self.assertEqual([2, 1, 2], [len(r.colunas) for r in regioes], f"veio {regioes}")

    def test_o_trecho_curto_abaixo_do_quadro_e_de_uma_coluna(self) -> None:
        """Duas linhas largas e o fólio sob o quadro: poucas bandas para decidir calha nenhuma."""
        corpo = colunas_de_solucao()
        ultima = 120 + 29 * PASSO_Y
        quadro, dentro = self._quadro(ultima + 3 * PASSO_Y)
        y = quadro[1] + 2 * PASSO_Y
        # Duas linhas que deixam o mesmo vão alinhado -- em três bandas isso é "calha".
        rodape = [c for i in range(2) for c in (*_linha_de(ESQUERDA, y + i * PASSO_Y, 7), *_linha_de(ESQUERDA + 11 * PASSO_X, y + i * PASSO_Y, 7))]
        caixas = [*corpo, *dentro, *rodape, *_folio(y + 4 * PASSO_Y)]
        regioes = detectar_regioes(caixas, quadros=[quadro])
        self.assertEqual([2, 1], [len(r.colunas) for r in regioes], f"veio {regioes}")

    def test_sem_quadro_nenhum_nada_muda(self) -> None:
        caixas = pagina_de_solucoes()
        self.assertEqual(detectar_regioes(caixas), detectar_regioes(caixas, quadros=[]))

    def test_o_quadro_fora_de_toda_banda_nao_faz_nada(self) -> None:
        caixas = pagina_de_solucoes()
        self.assertEqual(detectar_regioes(caixas), detectar_regioes(caixas, quadros=[(5000, 6000)]))


LIVRO = DEFAULT_PDF_DIR / "📚Yusupov Artur. Build Up Your Chess (all volumes).pdf"


@unittest.skipUnless(LIVRO.exists(), f"{LIVRO.name} não está neste checkout (PDF/ fica fora do git)")
class PaginaDeSolucoesDoYusupovTests(unittest.TestCase):
    """A página da queixa, lida do livro de verdade, pelas linhas da camada de texto -- o caminho
    da régua da S-194, que não precisa de modelo. Pula sem o acervo, como `test_falso_positivo_vence`."""

    def test_a_pagina_1917_sai_em_duas_colunas_entre_o_titulo_e_o_folio(self) -> None:
        import fitz

        from chess_diagram_ocr.cli.texto_ordem import _linhas_da_camada
        from chess_diagram_ocr.text.leitor import calha_de_linhas

        with fitz.open(LIVRO) as doc:
            linhas = _linhas_da_camada(doc[1916])
        caixas = [Caixa(int(b[0]), int(b[1]), int(b[2]), int(b[3])) for _, b in linhas]
        regioes = detectar_regioes(caixas, calha_minima=calha_de_linhas(caixas))
        self.assertEqual([1, 2, 1], [len(r.colunas) for r in regioes], f"veio {regioes}")

    def test_a_pagina_1021_com_o_quadro_scoring_sai_em_duas_colunas(self) -> None:
        """S-525: a imagem do quadro é achada na camada e as soluções em cima dele acham a calha."""
        import fitz

        from chess_diagram_ocr.cli.texto_ordem import _linhas_da_camada
        from chess_diagram_ocr.text.leitor import calha_de_linhas
        from chess_diagram_ocr.text.quadros import quadros_da_camada

        with fitz.open(LIVRO) as doc:
            page = doc[1020]
            linhas = _linhas_da_camada(page)
            quadros = [(int(y0), int(y1)) for y0, y1 in quadros_da_camada(page)]
        # Dois quadros: a imagem decorativa do cabeçalho (com o título e o número do capítulo
        # dentro) e o «Scoring», em 452-557 pt. O do cabeçalho é transversal de qualquer jeito.
        self.assertTrue(any(440 <= y0 <= 460 for y0, _ in quadros), f"esperava o quadro Scoring, veio {quadros}")
        caixas = [Caixa(int(b[0]), int(b[1]), int(b[2]), int(b[3])) for _, b in linhas]
        sem = detectar_regioes(caixas, calha_minima=calha_de_linhas(caixas))
        self.assertEqual([1], sorted({len(r.colunas) for r in sem}), "sem o quadro a folha era de uma coluna")
        com = detectar_regioes(caixas, calha_minima=calha_de_linhas(caixas), quadros=quadros)
        self.assertEqual(2, max(len(r.colunas) for r in com), f"veio {com}")


class ColunaVaziaTests(unittest.TestCase):
    """A guarda de `PREENCHIMENTO_DA_COLUNA`, e a folha que a obrigou a existir.

    Reproduz a folha 74 do `Melhores Finais de Capablanca`: prosa de **coluna única** com uma
    lista de lances no meio. A margem direita das linhas curtas de prosa alinha com o começo da
    coluna dos lances das pretas, e ali há calha por doze bandas seguidas -- a região que sai dali
    põe todos os lances das brancas antes de todos os das pretas.
    """

    def _lista_de_lances(self, fileiras: int = 15) -> list[Caixa]:
        """Prosa de largura inteira em cima, e no meio a lista: prosa curta e dois campos estreitos.

        O vão entre o fim da prosa curta e o campo da direita é a "calha" que não é calha: ele
        existe porque a prosa acaba ali, e não porque haja duas colunas. O bloco de largura inteira
        em cima é o que faz a régua de folha desistir, deixando a busca por região sozinha.
        """
        caixas = list(_bloco_largo(20, 4))
        y0 = 20 + 5 * PASSO_Y
        for i in range(fileiras):
            y = y0 + i * PASSO_Y
            if i % 3 == 2:  # prosa, da margem esquerda até um pouco antes do campo da direita
                caixas.extend(_linha_de(ESQUERDA, y, POR_LINHA + 3))
                continue
            # lance das brancas, no meio da faixa da esquerda; das pretas, no começo da direita
            caixas.extend(_linha_de(ESQUERDA + 6 * PASSO_X, y, 4))
            caixas.extend(_linha_de(DIREITA, y, 4))
        return caixas

    def test_a_folha_e_de_uma_coluna_para_a_regua_de_folha(self) -> None:
        """A premissa: sem região, esta folha não tem coluna nenhuma a achar."""
        self.assertEqual(1, len(detectar_colunas(self._lista_de_lances())))

    def test_a_coluna_vazia_demais_nao_vira_regiao(self) -> None:
        regioes = detectar_regioes(self._lista_de_lances())
        self.assertEqual([1], sorted({len(r.colunas) for r in regioes}), f"inventou coluna: {regioes}")

    def test_sem_a_guarda_a_folha_seria_partida(self) -> None:
        """O outro lado do par. Sem ele, o teste acima passaria por qualquer motivo -- inclusive
        por a folha não ter calha nenhuma, que não é o caso."""
        caixas = self._lista_de_lances()
        original = regioes_mod.PREENCHIMENTO_DA_COLUNA
        regioes_mod.PREENCHIMENTO_DA_COLUNA = 0.0
        self.addCleanup(setattr, regioes_mod, "PREENCHIMENTO_DA_COLUNA", original)
        self.assertEqual(2, max(len(r.colunas) for r in detectar_regioes(caixas)))

    def test_a_prosa_de_duas_colunas_passa_pela_guarda(self) -> None:
        """A guarda não pode barrar a folha do item: ali as duas colunas são justificadas."""
        regioes = detectar_regioes(com_bloco_no_topo())
        self.assertEqual(2, max(len(r.colunas) for r in regioes))


class CortesTests(unittest.TestCase):
    """As regiões ladrilham a folha: nada fica fora, nada fica em duas."""

    def test_os_cortes_nao_deixam_buraco_nem_sobreposicao(self) -> None:
        regioes = detectar_regioes(com_bloco_no_topo())
        for antes, depois in zip(regioes, regioes[1:], strict=False):
            self.assertEqual(antes.base + 1, depois.topo, f"{antes} e {depois}")

    def test_toda_caixa_cai_em_alguma_regiao(self) -> None:
        caixas = com_bloco_no_topo()
        regioes = detectar_regioes(caixas)
        for caixa in caixas:
            indice = atribuir_regiao(caixa, regioes)
            self.assertTrue(
                regioes[indice].topo <= caixa.y1 <= regioes[indice].base,
                f"{caixa} caiu em {regioes[indice]}",
            )

    def test_a_caixa_entra_pelo_topo_dela(self) -> None:
        """A mesma convenção da fileira da S-216: um diagrama é mais alto que o corte seguinte."""
        regioes = [Regiao(0, 100, ((0, 50),)), Regiao(101, 400, ((0, 20), (30, 50)))]
        alta = Caixa(0, 90, 50, 300)
        self.assertEqual(0, atribuir_regiao(alta, regioes))

    def test_sem_regiao_nenhuma_a_caixa_vai_para_a_primeira(self) -> None:
        self.assertEqual(0, atribuir_regiao(Caixa(0, 0, 10, 10), []))

    def test_a_caixa_abaixo_de_tudo_vai_para_a_ultima_regiao(self) -> None:
        """O diagrama não entrou na conta que cortou a folha, e pode passar da base."""
        regioes = detectar_regioes(com_bloco_no_topo())
        fundo = Caixa(ESQUERDA, regioes[-1].base + 500, DIREITA, regioes[-1].base + 900)
        self.assertEqual(len(regioes) - 1, atribuir_regiao(fundo, regioes))


class ColunasDaFolhaTests(unittest.TestCase):
    def test_responde_pela_regiao_mais_dividida(self) -> None:
        self.assertEqual(2, len(colunas_da_folha(detectar_regioes(com_bloco_no_topo()))))

    def test_sem_regiao_nenhuma_nao_ha_coluna(self) -> None:
        self.assertEqual([], colunas_da_folha([]))


class PisoDeBandasTests(unittest.TestCase):
    """`BANDAS_NA_REGIAO` é o mesmo `LINHAS_PARA_TOLERAR`, e o motivo é o mesmo.

    A janela é de 12 bandas e **uma delas pode ser a linha tolerada** por `LINHAS_NA_CALHA` -- é o
    que a tolerância quer dizer. O piso efetivo de bandas colunares é, portanto, 11.
    """

    COLUNARES_NO_PISO = BANDAS_NA_REGIAO - LINHAS_NA_CALHA

    def test_um_punhado_de_linhas_nao_vira_regiao_colunar(self) -> None:
        """Abaixo do piso, a folha fica inteira -- que é o lado seguro do erro."""
        caixas = com_bloco_no_topo(linhas_do_bloco=4, linhas_de_coluna=self.COLUNARES_NO_PISO - 1)
        regioes = detectar_regioes(caixas)
        self.assertEqual([1], sorted({len(r.colunas) for r in regioes}), f"{regioes}")

    def test_no_piso_a_regiao_colunar_aparece(self) -> None:
        """O outro lado do par, e é ele que prova que o piso é um limiar e não um acidente."""
        caixas = com_bloco_no_topo(linhas_do_bloco=4, linhas_de_coluna=self.COLUNARES_NO_PISO)
        self.assertEqual(2, max(len(r.colunas) for r in detectar_regioes(caixas)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
