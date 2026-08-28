"""A régua da ordem de leitura, e o guarda que impede a referência de mentir (S-194).

**O teste que dá nome a este arquivo é `test_a_referencia_com_blocos_fora_de_ordem_e_recusada`.**
Na primeira execução, o `tau` médio deu 0,0965 e o pior caso 0,53 -- como se estivéssemos lendo
páginas quase ao contrário. A investigação mostrou o oposto: no `400 Quebra-cabeças ..._hq` a
camada de texto emite o rodapé, depois a metade de baixo e **só então o topo**. Nossa ordem estava
certa; a referência é que não era ordem de leitura.

Com o guarda, o `tau` médio caiu para 0,0096.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from chess_diagram_ocr.cli import texto_ordem as ordem


class KendallTests(unittest.TestCase):
    def test_a_ordem_identica_da_zero(self) -> None:
        self.assertEqual(0.0, ordem.kendall_tau([0, 1, 2, 3, 4]))

    def test_a_ordem_invertida_da_um(self) -> None:
        self.assertEqual(1.0, ordem.kendall_tau([4, 3, 2, 1, 0]))

    def test_uma_troca_local_pesa_pouco_e_o_embaralhado_pesa_muito(self) -> None:
        """**É o par que importa, e não a posição.**

        Uma página com 40 linhas e uma troca local não é o mesmo defeito que uma com as duas
        colunas intercaladas, e uma régua de "acertou tudo" trataria as duas igual.
        """
        uma_troca = [0, 1, 3, 2, 4, 5, 6, 7, 8, 9]
        colunas_intercaladas = [0, 5, 1, 6, 2, 7, 3, 8, 4, 9]
        self.assertLess(ordem.kendall_tau(uma_troca), 0.05)
        self.assertGreater(ordem.kendall_tau(colunas_intercaladas), 0.15)

    def test_sequencia_curta_demais_nao_tem_par(self) -> None:
        self.assertEqual(0.0, ordem.kendall_tau([]))
        self.assertEqual(0.0, ordem.kendall_tau([3]))


class DescidasTests(unittest.TestCase):
    def test_uma_coluna_bem_emitida_nao_desce(self) -> None:
        self.assertEqual(0, ordem.descidas([100.0, 130.0, 160.0, 190.0]))

    def test_duas_colunas_descem_uma_vez(self) -> None:
        """Ao passar do fim da primeira coluna para o topo da segunda."""
        self.assertEqual(1, ordem.descidas([100.0, 130.0, 160.0, 100.0, 130.0]))

    def test_a_folga_absorve_o_rasgo_da_linha_justificada(self) -> None:
        """Duas caixas da mesma linha diferem um pixel no topo, e isso não é descer."""
        self.assertEqual(0, ordem.descidas([100.0, 99.0, 130.0]))

    def test_o_bloco_fora_de_ordem_desce_mais_de_uma_vez(self) -> None:
        """O caso do `400 Quebra-cabeças`: rodapé, metade de baixo, topo."""
        self.assertEqual(2, ordem.descidas([797.0, 309.0, 400.0, 630.0, 88.0, 112.0]))


class ReferenciaTests(unittest.TestCase):
    """O guarda: uma coluna desce zero vezes, duas descem uma. Mais que isso é bloco fora de ordem."""

    def _pagina(self, *, colunas: int, descidas: int) -> ordem.Pagina:
        return ordem.Pagina(pdf="x", pagina=1, linhas=20, tau=0.5, colunas=colunas, descidas_da_referencia=descidas)

    def test_a_referencia_de_uma_coluna_em_ordem_e_confiavel(self) -> None:
        self.assertTrue(self._pagina(colunas=1, descidas=0).referencia_confiavel)

    def test_a_referencia_de_duas_colunas_pode_descer_uma_vez(self) -> None:
        self.assertTrue(self._pagina(colunas=2, descidas=1).referencia_confiavel)

    def test_a_referencia_com_blocos_fora_de_ordem_e_recusada(self) -> None:
        """**Ali o `tau` mede a referência, e não a nossa ordenação.**

        Sem este guarda o número publicado seria 0,0965 quando o real é 0,0096 -- e a conclusão
        seria "a ordenação está ruim" quando ela está certa.
        """
        self.assertFalse(self._pagina(colunas=1, descidas=2).referencia_confiavel)
        self.assertFalse(self._pagina(colunas=2, descidas=3).referencia_confiavel)


class MedirPaginaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def _pdf(self, linhas: list[tuple[str, float, float]]) -> Path:
        doc = fitz.open()
        page = doc.new_page(width=595.0, height=842.0)
        for texto, x, y in linhas:
            page.insert_text((x, y), texto, fontsize=11)
        caminho = self.raiz / "livro.pdf"
        doc.save(caminho)
        doc.close()
        return caminho

    def test_a_pagina_de_coluna_unica_bem_emitida_sai_em_ordem(self) -> None:
        caminho = self._pdf([(f"linha numero {i}", 60.0, 100.0 + i * 20) for i in range(10)])
        with fitz.open(caminho) as doc:
            resultado = ordem.medir_pagina(doc[0])
        assert resultado is not None
        self.assertEqual(0.0, resultado.tau)
        self.assertTrue(resultado.referencia_confiavel)

    def test_a_pagina_curta_demais_nao_e_medida(self) -> None:
        """Rosto, folha de guarda e página com uma linha solta não têm ordem a medir."""
        caminho = self._pdf([("titulo", 60.0, 100.0)])
        with fitz.open(caminho) as doc:
            self.assertIsNone(ordem.medir_pagina(doc[0]))

    def test_o_relatorio_traz_o_livro_sem_camada_de_texto(self) -> None:
        doc = fitz.open()
        doc.new_page(width=595.0, height=842.0)
        caminho = self.raiz / "scan.pdf"
        doc.save(caminho)
        doc.close()
        relatorio = ordem.medir([caminho], por_livro=3)
        self.assertEqual(["scan.pdf"], relatorio["livros_sem_referencia"])
        self.assertIsNone(relatorio["tau_medio"])

    def test_o_relatorio_conta_as_referencias_suspeitas_em_vez_de_descarta_las_calado(self) -> None:
        # Blocos fora de ordem: o PyMuPDF preserva a ordem de inserção nos spans.
        linhas = [(f"rodape {i}", 60.0, 700.0 + i * 15) for i in range(4)]
        linhas += [(f"topo {i}", 60.0, 100.0 + i * 20) for i in range(6)]
        caminho = self._pdf(linhas)
        relatorio = ordem.medir([caminho], por_livro=3)
        self.assertIn("paginas_com_referencia_suspeita", relatorio)


class ComandoTests(unittest.TestCase):
    def test_sem_pdf_nenhum_nao_derruba(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertEqual(0, ordem.main(["--pdf-dir", tmp, "--saida", str(Path(tmp) / "s.json")]))

    def test_o_baseline_que_nao_existe_falha(self) -> None:
        with TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            doc = fitz.open()
            page = doc.new_page(width=595.0, height=842.0)
            for i in range(10):
                page.insert_text((60.0, 100.0 + i * 20), f"linha {i}", fontsize=11)
            doc.save(raiz / "livro.pdf")
            doc.close()
            codigo = ordem.main(
                ["--pdf-dir", tmp, "--saida", str(raiz / "s.json"), "--baseline", str(raiz / "nao.json")]
            )
            # Caminho apontado que não existe é a classe 2 da S-126, e não a 1 (S-378).
            self.assertEqual(2, codigo)

    def test_o_baseline_falha_quando_a_ordem_piora(self) -> None:
        """Regressão de ordem é regressão — mesma trava do `cvoff-census --fail-on-loss`."""
        import json

        with TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            doc = fitz.open()
            page = doc.new_page(width=595.0, height=842.0)
            for i in range(10):
                page.insert_text((60.0, 100.0 + i * 20), f"linha {i}", fontsize=11)
            doc.save(raiz / "livro.pdf")
            doc.close()

            baseline = raiz / "base.json"
            baseline.write_text(json.dumps({"tau_medio": 0.0}), encoding="utf-8")
            saida = str(raiz / "s.json")
            self.assertEqual(0, ordem.main(["--pdf-dir", tmp, "--saida", saida, "--baseline", str(baseline)]))

            # Um baseline melhor que o possível: a saída de hoje passa a ser "pior".
            baseline.write_text(json.dumps({"tau_medio": -1.0}), encoding="utf-8")
            self.assertEqual(1, ordem.main(["--pdf-dir", tmp, "--saida", saida, "--baseline", str(baseline)]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
