"""O caderno no formato que a suíte lê para o EPUB/DOCX do livro (R7). Puro, sem a suíte.

O que se afirma é o contrato com `caissa.export.page_texts`: só as folhas corrigidas vão, um
parágrafo por quebra de linha, o estilo e o alinhamento do parágrafo, a ênfase por trecho, e o
diagrama no lugar em que a folha o tem.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.text import caderno, caderno_na_suite, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida


def _pagina(livro: str, folha: int, texto: str) -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas([LinhaLida(texto, (0.0, 0.0, 100.0, 9.0), 0.5, "glifo")])  # type: ignore[arg-type]
    return PaginaLida(documento=livro, pagina=folha, colunas=(Coluna(indice=0, blocos=(bloco,)),))


def _doc(*corridas: rico.Corrida, origem: PaginaLida | None = None) -> rico.DocumentoRico:
    return rico.DocumentoRico(corridas=corridas, origem=origem)


def _c(texto: str, **atributos: object) -> rico.Corrida:
    return rico.Corrida(texto, atributos=rico.Atributos(**atributos))  # type: ignore[arg-type]


class ParagrafosTests(unittest.TestCase):
    def test_cada_quebra_fecha_um_paragrafo_e_a_linha_em_branco_nao_vira_paragrafo(self) -> None:
        paragrafos = caderno_na_suite.paragrafos_da_folha(_doc(_c("um\n\ndois\n")))
        self.assertEqual([p["runs"][0]["text"] for p in paragrafos], ["um", "dois"])

    def test_a_enfase_vai_por_trecho_e_a_mesma_enfase_partida_e_um_trecho(self) -> None:
        doc = _doc(_c("normal "), _c("forte", negrito=True), _c(" e ", negrito=True), _c("inclinado", italico=True))
        (paragrafo,) = caderno_na_suite.paragrafos_da_folha(doc)
        self.assertEqual(
            paragrafo["runs"],
            [{"text": "normal "}, {"text": "forte e ", "bold": True}, {"text": "inclinado", "italic": True}],
        )

    def test_estilo_e_alinhamento_sao_do_paragrafo(self) -> None:
        doc = _doc(_c("Capítulo 3\n", estilo=rico.ESTILO_TITULO, alinhamento=rico.ALINHAMENTO_CENTRO), _c("1.e4 e5", estilo=rico.ESTILO_NOTACAO))
        titulo, lance = caderno_na_suite.paragrafos_da_folha(doc)
        self.assertEqual((titulo["style"], titulo["alignment"]), ("heading", "center"))
        self.assertEqual((lance["style"], lance["alignment"]), ("notation", ""))

    def test_o_diagrama_fica_entre_os_paragrafos_com_o_alinhamento_efetivo(self) -> None:
        marca = rico.Corrida("[diagrama 1]", tipo=rico.DIAGRAMA)
        paragrafos = caderno_na_suite.paragrafos_da_folha(_doc(_c("antes\n"), marca, _c("depois")))
        self.assertEqual([p["kind"] for p in paragrafos], ["text", "diagram", "text"])
        self.assertEqual(paragrafos[1], {"kind": "diagram", "fen": "", "alignment": "center"})

    def test_o_branco_das_pontas_do_paragrafo_sai(self) -> None:
        (paragrafo,) = caderno_na_suite.paragrafos_da_folha(_doc(_c("  meio  ")))
        self.assertEqual(paragrafo["runs"], [{"text": "meio"}])


class FolhasTests(unittest.TestCase):
    def setUp(self) -> None:
        raiz = pasta_temporaria(self)
        self.livro = raiz / "Nunn.pdf"
        self.livro.write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 64)
        aberto = caderno.abrir(self.livro, pasta=raiz / "cadernos")
        assert aberto is not None
        self.addCleanup(aberto.fechar)
        self.caderno = aberto

    def _gravar(self, folha: int, texto: str, *, correcoes: int) -> None:
        doc = rico.de_pagina(_pagina(str(self.livro), folha, texto))
        self.assertEqual(self.caderno.gravar(doc, correcoes=correcoes), caderno.GRAVADA)

    def test_so_as_folhas_corrigidas_vao_e_em_ordem(self) -> None:
        self._gravar(4, "corrigida depois", correcoes=2)
        self._gravar(1, "só lida", correcoes=0)
        self._gravar(2, "corrigida antes", correcoes=1)
        folhas = caderno_na_suite.folhas_para_a_suite(self.caderno)
        self.assertEqual([f["page_index"] for f in folhas], [2, 4])
        self.assertEqual(folhas[0]["paragraphs"][0]["runs"], [{"text": "corrigida antes"}])
        self.assertEqual((folhas[0]["format"], folhas[0]["state"]), (caderno_na_suite.FORMATO, caderno.EDITADA))
        self.assertTrue(folhas[0]["saved_at"])

    def test_a_conferida_vai_mesmo_sem_correcao(self) -> None:
        self._gravar(3, "conferida", correcoes=0)
        self.caderno.marcar(3, caderno.CONFERIDA)
        self.assertEqual([f["state"] for f in caderno_na_suite.folhas_para_a_suite(self.caderno)], [caderno.CONFERIDA])

    def test_o_intervalo_pedido_corta_as_folhas(self) -> None:
        self._gravar(2, "dois", correcoes=1)
        self._gravar(9, "nove", correcoes=1)
        self.assertEqual([f["page_index"] for f in caderno_na_suite.folhas_para_a_suite(self.caderno, (9, 10))], [9])

    def test_folha_que_nao_abre_fica_de_fora(self) -> None:
        self._gravar(2, "dois", correcoes=1)
        Path(self.caderno.caminho(2)).write_text("isto não é cvtxt", encoding="utf-8")
        self.caderno._ultimos.clear()
        self.assertEqual(caderno_na_suite.folhas_para_a_suite(self.caderno), [])


if __name__ == "__main__":
    unittest.main()
