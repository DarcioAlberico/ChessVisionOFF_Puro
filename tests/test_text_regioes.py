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

from chess_diagram_ocr.text import regioes as regioes_mod
from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.colunas import LINHAS_NA_CALHA, detectar_colunas
from chess_diagram_ocr.text.regioes import (
    BANDAS_NA_REGIAO,
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
