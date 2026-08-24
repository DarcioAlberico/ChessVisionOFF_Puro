"""O que a aba de texto mostra, testado **sem abrir janela** (S-211).

É a regra da Fase 6: o que dá para testar não mora na janela. `ui/texto_panel.py` é widget, thread
e `after`; tudo que ele *decide* está em `text/documento.py`, e é aqui que se afirma.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text import documento
from chess_diagram_ocr.text.pagina import (
    BlocoDeDiagrama,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaLida,
    de_diagramas,
)


def _texto(conteudo: str, confianca: float = 1.0, procedencia: str = "camada") -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas(
        [LinhaLida(conteudo, (0.0, 0.0, 10.0, 10.0), confianca, procedencia)]  # type: ignore[arg-type]
    )


class FaixaDeConfiancaTests(unittest.TestCase):
    def test_abaixo_do_corte_da_s42_e_adivinhacao(self) -> None:
        self.assertEqual(documento.faixa_de_confianca(0.1, "glifo"), documento.REVISAR)

    def test_o_corte_de_baixo_e_o_mesmo_do_resto_do_programa(self) -> None:
        """Um segundo corte para "isto é palpite?" faria a aba discordar do resto (S-42)."""
        from chess_diagram_ocr.ocr import MIN_CONFIDENCE

        self.assertEqual(documento.corte_de_revisar(), MIN_CONFIDENCE)
        self.assertEqual(
            documento.faixa_de_confianca(MIN_CONFIDENCE - 0.001, "glifo"), documento.REVISAR
        )
        self.assertNotEqual(documento.faixa_de_confianca(MIN_CONFIDENCE, "glifo"), documento.REVISAR)

    def test_no_meio_pede_conferencia(self) -> None:
        self.assertEqual(documento.faixa_de_confianca(0.5, "glifo"), documento.CONFERIR)

    def test_leitura_certa_nao_pede_nada(self) -> None:
        self.assertEqual(documento.faixa_de_confianca(0.99, "glifo"), documento.TRANQUILO)

    def test_a_camada_de_texto_nunca_pede_revisao(self) -> None:
        """Não é leitura, é registro. Sem isto um arquivo com `confianca: 0` pintaria tudo."""
        self.assertEqual(documento.faixa_de_confianca(0.0, "camada"), documento.TRANQUILO)

    def test_a_correcao_humana_nunca_pede_revisao(self) -> None:
        self.assertEqual(documento.faixa_de_confianca(0.0, "humano"), documento.TRANQUILO)

    def test_toda_faixa_devolvida_esta_declarada(self) -> None:
        for confianca in (0.0, 0.29, 0.3, 0.74, 0.75, 1.0):
            for procedencia in ("camada", "glifo", "rapidocr", "humano"):
                with self.subTest(confianca=confianca, procedencia=procedencia):
                    self.assertIn(
                        documento.faixa_de_confianca(confianca, procedencia), documento.FAIXAS
                    )


class SegmentosTests(unittest.TestCase):
    def test_o_editor_nao_abre_com_linha_em_branco_no_topo(self) -> None:
        """Um editor que abre com uma linha vazia faz todo mundo apertar Backspace antes de começar."""
        pagina = PaginaLida(colunas=(Coluna(blocos=(_texto("primeiro"), _texto("segundo"))),))
        segmentos = list(documento.segmentos(pagina))
        self.assertNotEqual(segmentos[0].tipo, "separador")
        self.assertNotEqual(segmentos[-1].tipo, "separador")

    def test_ha_exatamente_um_separador_entre_blocos(self) -> None:
        pagina = PaginaLida(
            colunas=(Coluna(blocos=(_texto("a"), _texto("b"), _texto("c"))),)
        )
        segmentos = list(documento.segmentos(pagina))
        self.assertEqual([s.tipo for s in segmentos],
                         ["texto", "separador", "texto", "separador", "texto"])

    def test_o_diagrama_vira_um_segmento_proprio_no_lugar_dele(self) -> None:
        pagina = PaginaLida(
            colunas=(Coluna(blocos=(_texto("antes"), BlocoDeDiagrama(indice=0), _texto("depois"))),)
        )
        tipos = [s.tipo for s in documento.segmentos(pagina) if s.tipo != "separador"]
        self.assertEqual(tipos, ["texto", "diagrama", "texto"])

    def test_um_bloco_sem_texto_nao_vira_segmento(self) -> None:
        """Senão ele apareceria como uma linha em branco a mais, sem nada que a explique."""
        pagina = PaginaLida(colunas=(Coluna(blocos=(_texto("tem"), _texto(""))),))
        self.assertEqual(len(list(documento.segmentos(pagina))), 1)

    def test_a_faixa_do_segmento_vem_do_bloco(self) -> None:
        pagina = PaginaLida(colunas=(Coluna(blocos=(_texto("chute", 0.1, "glifo"),)),))
        self.assertEqual(list(documento.segmentos(pagina))[0].faixa, documento.REVISAR)

    def test_os_diagramas_visiveis_saem_na_ordem_do_texto(self) -> None:
        pagina = de_diagramas([(0.0, 0.0, 1.0, 1.0)] * 3)
        visiveis = documento.diagramas_visiveis(list(documento.segmentos(pagina)))
        self.assertEqual([d.indice for d in visiveis], [0, 1, 2])


class ArquivoTests(unittest.TestCase):
    def test_o_arquivo_diz_de_onde_o_texto_veio(self) -> None:
        pagina = PaginaLida(documento="Livro.pdf", pagina=40, numero_impresso=38,
                            colunas=(Coluna(blocos=(_texto("o corpo"),)),))
        saida = documento.texto_para_arquivo(pagina)
        self.assertTrue(saida.startswith("# Livro.pdf — folha 41, página impressa 38"))
        self.assertIn("o corpo", saida)

    def test_a_folha_e_1_based_e_o_indice_e_0_based(self) -> None:
        """O mesmo par que a S-14 confundiu entre o "diagrama 2" da tela e o do PGN."""
        pagina = PaginaLida(documento="L.pdf", pagina=0, colunas=(Coluna(blocos=(_texto("x"),)),))
        self.assertIn("folha 1", documento.texto_para_arquivo(pagina))

    def test_sem_numero_impresso_a_frase_nao_mente(self) -> None:
        pagina = PaginaLida(documento="L.pdf", pagina=5, colunas=(Coluna(blocos=(_texto("x"),)),))
        self.assertNotIn("página impressa", documento.texto_para_arquivo(pagina))

    def test_o_arquivo_termina_com_quebra(self) -> None:
        pagina = PaginaLida(documento="L.pdf", colunas=(Coluna(blocos=(_texto("x"),)),))
        self.assertTrue(documento.texto_para_arquivo(pagina).endswith("\n"))

    def test_o_diagrama_vai_para_o_arquivo_como_marca(self) -> None:
        """A imagem morre com o widget; a marca é o que sobrevive a salvar, copiar e colar."""
        pagina = PaginaLida(colunas=(Coluna(blocos=(_texto("antes"), BlocoDeDiagrama(indice=2)),),))
        self.assertIn("[Diagrama 3]", documento.texto_para_arquivo(pagina, com_cabecalho=False))

    def test_uma_pagina_vazia_nao_produz_arquivo_com_lixo(self) -> None:
        self.assertEqual(documento.texto_para_arquivo(PaginaLida(), com_cabecalho=False), "")


class ResumoTests(unittest.TestCase):
    def test_o_resumo_conta_o_que_pede_olho(self) -> None:
        pagina = PaginaLida(
            colunas=(Coluna(blocos=(_texto("bom", 1.0, "camada"),
                                    _texto("chute", 0.1, "glifo"),
                                    _texto("meio", 0.5, "glifo"))),)
        )
        resumo = documento.resumo(pagina)
        self.assertIn("2 pedem conferência", resumo)
        self.assertIn("1 adivinhados", resumo)

    def test_uma_pagina_toda_certa_nao_pede_conferencia_nenhuma(self) -> None:
        pagina = PaginaLida(colunas=(Coluna(blocos=(_texto("bom", 1.0, "camada"),)),))
        self.assertNotIn("pedem conferência", documento.resumo(pagina))

    def test_o_resumo_diz_a_procedencia(self) -> None:
        pagina = PaginaLida(colunas=(Coluna(blocos=(_texto("da camada", 1.0, "camada"),)),))
        self.assertIn("1 camada", documento.resumo(pagina))

    def test_a_contagem_por_faixa_cobre_todos_os_blocos(self) -> None:
        pagina = PaginaLida(
            colunas=(Coluna(blocos=(_texto("a", 0.1, "glifo"), _texto("b", 0.5, "glifo"),
                                    _texto("c", 1.0, "camada"))),)
        )
        contagem = documento.contagem_por_faixa(pagina)
        self.assertEqual(sum(contagem.values()), len(pagina.blocos))
        self.assertEqual(contagem[documento.REVISAR], 1)
        self.assertEqual(contagem[documento.CONFERIR], 1)
        self.assertEqual(contagem[documento.TRANQUILO], 1)

    def test_o_resumo_de_uma_pagina_vazia_nao_estoura(self) -> None:
        self.assertIsInstance(documento.resumo(PaginaLida()), str)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
