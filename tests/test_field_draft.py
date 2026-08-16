"""A anotação de página do conjunto de campo, sem janela (S-77).

O que se verifica aqui é o que erra em silêncio: acrescentar duas vezes o mesmo diagrama,
gravar página não revisada, e a página anotada de novo virar duas linhas no arquivo -- e
`evaluate_field` contaria a página duas vezes, com pesos diferentes.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chess_diagram_ocr.field_eval import FieldPage, load_field_set, upsert_page
from chess_diagram_ocr.ui.field_draft import REGIMES, FieldDraft

CAIXA_A = (100.0, 100.0, 200.0, 200.0)
CAIXA_B = (300.0, 100.0, 400.0, 200.0)


class RascunhoTests(unittest.TestCase):
    def _rascunho(self) -> FieldDraft:
        rascunho = FieldDraft(pdf_name="livro.pdf", page=80, regime="scan-puro")
        rascunho.reset_from([(CAIXA_A, "4k3/8/8/8/8/8/8/4K3", True)])
        return rascunho

    def test_comeca_do_que_o_detector_achou(self) -> None:
        rascunho = self._rascunho()
        self.assertEqual(len(rascunho.diagrams), 1)
        self.assertEqual(rascunho.diagrams[0].bbox, CAIXA_A)
        self.assertEqual(rascunho.diagrams[0].placement, "4k3/8/8/8/8/8/8/4K3")

    def test_acrescentar_o_que_faltou_e_o_que_mede_recall(self) -> None:
        rascunho = self._rascunho()
        self.assertTrue(rascunho.add(CAIXA_B))
        self.assertEqual(len(rascunho.diagrams), 2)

    def test_nao_acrescenta_duas_vezes_o_mesmo_diagrama(self) -> None:
        """Sobreposição alta é a mesma caixa -- e duas anotações dela fariam o recall cair."""
        rascunho = self._rascunho()
        quase_igual = (105.0, 105.0, 205.0, 205.0)
        self.assertFalse(rascunho.add(quase_igual))
        self.assertEqual(len(rascunho.diagrams), 1)

    def test_a_ordem_e_a_da_leitura_da_pagina(self) -> None:
        rascunho = FieldDraft(pdf_name="livro.pdf", page=80)
        rascunho.add((300.0, 400.0, 400.0, 500.0))
        rascunho.add((100.0, 100.0, 200.0, 200.0))
        self.assertEqual(rascunho.diagrams[0].bbox[1], 100.0, "o de cima vem primeiro")

    def test_remover_tira_o_falso_positivo(self) -> None:
        rascunho = self._rascunho()
        self.assertTrue(rascunho.remove(0))
        self.assertTrue(rascunho.is_empty)
        self.assertFalse(rascunho.remove(0), "índice inexistente não levanta")

    def test_acha_o_item_pela_caixa_da_tela(self) -> None:
        rascunho = self._rascunho()
        self.assertEqual(rascunho.index_at((102.0, 101.0, 199.0, 198.0)), 0)
        self.assertIsNone(rascunho.index_at(CAIXA_B))

    def test_a_pagina_gravada_sai_revisada(self) -> None:
        """É o ponto do módulo: `reviewed=True` só existe onde houve gesto humano."""
        pagina = self._rascunho().to_page()
        self.assertTrue(pagina.reviewed)
        self.assertEqual(pagina.regime, "scan-puro")
        self.assertEqual(pagina.page, 80)

    def test_pagina_vazia_declara_o_regime_sozinha(self) -> None:
        """Página sem diagrama é dado obrigatório (S-41): é ela que mede falso positivo."""
        pagina = FieldDraft(pdf_name="livro.pdf", page=12).to_page()
        self.assertEqual(pagina.regime, "sem-diagrama")
        self.assertEqual(pagina.diagrams, ())
        self.assertTrue(pagina.reviewed)

    def test_retomar_uma_pagina_ja_anotada(self) -> None:
        original = self._rascunho().to_page()
        retomada = FieldDraft.from_page(original)
        self.assertEqual(retomada.regime, "scan-puro")
        self.assertEqual(len(retomada.diagrams), 1)
        retomada.add(CAIXA_B)
        self.assertEqual(len(original.diagrams), 1, "a original não pode mudar junto")

    def test_a_descricao_conta_o_que_esta_na_lista(self) -> None:
        self.assertIn("1 diagrama", self._rascunho().describe())
        self.assertEqual(FieldDraft().describe(), "página sem diagrama")

    def test_os_regimes_sao_os_da_s41(self) -> None:
        self.assertIn("scan-hachurado", REGIMES)
        self.assertIn("sem-diagrama", REGIMES)


class VerdadeDeReferenciaTests(unittest.TestCase):
    """S-95: a colocação que vira verdade é a **conferida**, nunca a lida pelo modelo.

    Até aqui `app_tkinter._field_draft` montava a anotação com `items[i].placement` -- a
    leitura do modelo -- em vez de `fen_edits[i]`, que é o que a pessoa corrigiu. O efeito era
    circular e invisível: `evaluate_field` comparava o modelo com a própria saída e reportava
    `conditional_exact = 1,000`. A única FEN que o conjunto chegou a ter era a leitura de uma
    **capa** de livro, sem rei branco e com 9 torres pretas.
    """

    LEGAL = "4k3/8/8/8/8/8/8/4K3"
    A_CAPA_DO_YUSUPOV = "4r2R/7Q/6R1/3rrrr1/1R1rrrR1/6Pq/2k1r1Q1/3b2q1"

    def test_a_leitura_nao_conferida_nao_vira_verdade(self) -> None:
        rascunho = FieldDraft(pdf_name="livro.pdf", page=80)
        rascunho.reset_from([(CAIXA_A, self.LEGAL, False)])
        self.assertEqual(rascunho.diagrams[0].placement, "")
        self.assertEqual(rascunho.diagrams[0].bbox, CAIXA_A, "a caixa continua sendo anotação válida")

    def test_a_correcao_humana_e_o_que_fica(self) -> None:
        """O par que hoje falhava em silêncio: leitura e correção diferentes entre si."""
        lido = "4k3/8/8/8/8/8/8/3QK3"
        corrigido = "4k3/8/8/8/8/8/8/4K3"
        rascunho = FieldDraft(pdf_name="livro.pdf", page=80)
        rascunho.reset_from([(CAIXA_A, corrigido, True)])
        self.assertEqual(rascunho.diagrams[0].placement, corrigido)
        self.assertNotEqual(rascunho.diagrams[0].placement, lido)

    def test_posicao_fatalmente_ilegal_nao_entra_nem_conferida(self) -> None:
        """A capa do Yusupov: `NO_WHITE_KING`. Um clique errado não pode fixá-la como alvo."""
        rascunho = FieldDraft(pdf_name="livro.pdf", page=0)
        rascunho.reset_from([(CAIXA_A, self.A_CAPA_DO_YUSUPOV, True)])
        self.assertEqual(rascunho.diagrams[0].placement, "")

    def test_notacao_invalida_nao_entra(self) -> None:
        rascunho = FieldDraft(pdf_name="livro.pdf", page=0)
        rascunho.reset_from([(CAIXA_A, "isto não é uma FEN", True)])
        self.assertEqual(rascunho.diagrams[0].placement, "")

    def test_ilegal_por_turno_continua_entrando(self) -> None:
        """A S-05 separou fatal de ilegal-por-turno para que guardas pudessem escolher uma.

        O livro desenha final parcial e estrutura de peões; recusar tudo que é ilegal barraria
        exatamente o material difícil que o conjunto de campo existe para medir.
        """
        torre_dando_xeque = "R3k3/8/8/8/8/8/8/4K3"
        rascunho = FieldDraft(pdf_name="livro.pdf", page=80)
        rascunho.reset_from([(CAIXA_A, torre_dando_xeque, True)])
        self.assertEqual(rascunho.diagrams[0].placement, torre_dando_xeque)

    def test_o_diagrama_que_o_detector_achou_e_ninguem_abriu_fica_sem_fen(self) -> None:
        """O caso comum: varrer a página e anotar sem abrir diagrama nenhum."""
        rascunho = FieldDraft(pdf_name="livro.pdf", page=80, regime="scan-puro")
        rascunho.reset_from([(CAIXA_A, self.LEGAL, False), (CAIXA_B, self.LEGAL, False)])
        pagina = rascunho.to_page()
        self.assertTrue(pagina.reviewed, "a caixa foi conferida por gente")
        self.assertEqual([d.placement for d in pagina.diagrams], ["", ""])

    def test_conferir_um_diagrama_de_dois_grava_so_o_conferido(self) -> None:
        rascunho = FieldDraft(pdf_name="livro.pdf", page=80)
        rascunho.reset_from([(CAIXA_A, self.LEGAL, True), (CAIXA_B, self.LEGAL, False)])
        self.assertEqual([d.placement for d in rascunho.diagrams], [self.LEGAL, ""])


class GravacaoTests(unittest.TestCase):
    def test_anotar_a_mesma_pagina_de_novo_substitui_a_linha(self) -> None:
        """Duas linhas do mesmo par fariam `evaluate_field` contar a página duas vezes."""
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "field_set.jsonl"
            rascunho = FieldDraft(pdf_name="livro.pdf", page=80, regime="scan-puro")
            rascunho.add(CAIXA_A)
            self.assertEqual(upsert_page(caminho, rascunho.to_page()), 1)

            rascunho.add(CAIXA_B)
            total = upsert_page(caminho, rascunho.to_page())

            paginas = load_field_set(caminho)
            self.assertEqual(len(paginas), 1, "uma linha por (livro, página)")
            self.assertEqual(len(paginas[0].diagrams), 2)
            self.assertEqual(total, 1)

    def test_conta_so_as_revisadas(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "field_set.jsonl"
            upsert_page(caminho, FieldPage(pdf="livro.pdf", page=1, reviewed=False))
            total = upsert_page(caminho, FieldDraft(pdf_name="livro.pdf", page=2).to_page())
            self.assertEqual(total, 1, "o rascunho não revisado não conta para o alvo")

    def test_paginas_de_livros_diferentes_convivem(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "field_set.jsonl"
            upsert_page(caminho, FieldDraft(pdf_name="a.pdf", page=1).to_page())
            upsert_page(caminho, FieldDraft(pdf_name="b.pdf", page=1).to_page())
            self.assertEqual(len(load_field_set(caminho)), 2)


if __name__ == "__main__":
    unittest.main()
