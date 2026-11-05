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


class _ComCaderno(unittest.TestCase):
    """A base: um caderno de verdade numa pasta temporária. Sem teste próprio."""

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


class FolhasTests(_ComCaderno):
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


def _da_suite(folha: int, *paragrafos: dict[str, object]) -> dict[str, object]:
    return {"format": 1, "page_index": folha, "state": "editada", "saved_at": "2026-10-29T09:00:00",
            "paragraphs": list(paragrafos)}


def _texto(texto: str, **campos: object) -> dict[str, object]:
    return {"kind": "text", "runs": [{"text": texto}], **campos}


FEN = "8/8/8/4k3/8/8/4K3/8 w - - 0 1"


class FolhaDaSuiteTests(unittest.TestCase):
    """O inverso de `folha_para_a_suite` (R7 de volta)."""

    def test_ida_e_volta_dao_o_mesmo_texto_e_os_mesmos_atributos(self) -> None:
        doc = _doc(
            _c("Capítulo 3", estilo=rico.ESTILO_TITULO, alinhamento=rico.ALINHAMENTO_CENTRO),
            rico.Corrida("\n\n", tipo=rico.SEPARADOR),
            _c("normal "), _c("forte", negrito=True), _c(" e "), _c("riscado", tachado=True),
            rico.Corrida("\n\n", tipo=rico.SEPARADOR),
            _c("1.e4 e5", estilo=rico.ESTILO_NOTACAO),
        )
        estado = caderno.EstadoDaFolha(pagina=3, estado=caderno.EDITADA)
        volta = caderno_na_suite.folha_da_suite(caderno_na_suite.folha_para_a_suite(doc, estado), livro="Nunn.pdf")
        self.assertEqual(volta.para_texto(), doc.para_texto())
        self.assertEqual(
            [(c.texto, c.atributos) for c in volta.corridas if c.tipo == rico.TEXTO],
            [(c.texto, c.atributos) for c in doc.corridas if c.tipo == rico.TEXTO],
        )
        self.assertEqual({c.procedencia for c in volta.corridas if c.tipo == rico.TEXTO}, {"humano"})
        self.assertEqual((volta.origem.pagina, volta.origem.documento), (3, "Nunn.pdf"))  # type: ignore[union-attr]

    def test_sem_origem_que_sirva_a_marca_aponta_para_um_diagrama_com_a_posicao_da_suite(self) -> None:
        volta = caderno_na_suite.folha_da_suite(
            _da_suite(0, _texto("antes"), {"kind": "diagram", "fen": FEN}, _texto("depois")),
            origem=_pagina("Nunn.pdf", 0, "sem diagrama nenhum"),
        )
        marca = next(c for c in volta.corridas if c.e_diagrama)
        bloco = volta.bloco_de(marca)
        self.assertEqual((marca.texto, getattr(bloco, "placement", None)), ("[Diagrama 1]", FEN.split(" ")[0]))
        self.assertEqual(volta.para_texto(), "antes\n\n[Diagrama 1]\n\ndepois")

    def test_com_tantos_diagramas_quanto_marcas_a_origem_do_caderno_fica(self) -> None:
        from chess_diagram_ocr.text.pagina import BlocoDeDiagrama

        origem = PaginaLida(documento="Nunn.pdf", pagina=0, colunas=(Coluna(indice=0, blocos=(
            BlocoDeDiagrama(indice=0, bbox=(10.0, 10.0, 90.0, 90.0)),)),))
        volta = caderno_na_suite.folha_da_suite(_da_suite(0, {"kind": "diagram", "fen": FEN}), origem=origem)
        self.assertIs(volta.origem, origem, "a miniatura continua recortada da página")

    def test_formato_desconhecido_e_recusado(self) -> None:
        with self.assertRaises(ValueError):
            caderno_na_suite.folha_da_suite({"format": 2, "page_index": 0})


class TrazerDaSuiteTests(_ComCaderno):
    """A regra do dono: sem correção aqui, entra; corrigida dos dois lados, o caderno vence."""

    def trazer(self, *folhas: dict[str, object]) -> caderno_na_suite.Volta:
        return caderno_na_suite.trazer_da_suite(self.caderno, folhas, livro=str(self.livro))

    def test_a_folha_so_lida_recebe_a_revisao_e_a_leitura_vai_para_anterior(self) -> None:
        self._gravar(1, "lida pelo motor", correcoes=0)
        volta = self.trazer(_da_suite(1, _texto("corrigida na revisão")))
        self.assertEqual(volta.trazidas, (1,))
        self.assertEqual(self.caderno.folha(1).para_texto(), "corrigida na revisão")  # type: ignore[union-attr]
        self.assertEqual(self.caderno.estado(1).estado, caderno.EDITADA)  # type: ignore[union-attr]
        self.assertEqual(self.caderno.anterior(1).para_texto(), "lida pelo motor")  # type: ignore[union-attr]
        self.assertIn(1, [f["page_index"] for f in caderno_na_suite.folhas_para_a_suite(self.caderno)],
                      "a folha trazida vai de novo ao livro, como corrigida")

    def test_a_folha_sem_caderno_entra(self) -> None:
        volta = self.trazer(_da_suite(7, _texto("só a revisão leu")))
        self.assertEqual(volta.trazidas, (7,))
        self.assertEqual(self.caderno.folha(7).para_texto(), "só a revisão leu")  # type: ignore[union-attr]

    def test_corrigida_dos_dois_lados_o_caderno_vence_e_a_revisao_vai_para_anterior(self) -> None:
        self._gravar(2, "corrigida aqui", correcoes=1)
        volta = self.trazer(_da_suite(2, _texto("corrigida lá")))
        self.assertEqual((volta.guardadas, volta.trazidas), ((2,), ()))
        self.caderno._ultimos.clear()
        self.assertEqual(self.caderno.folha(2).para_texto(), "corrigida aqui")  # type: ignore[union-attr]
        self.assertEqual(self.caderno.anterior(2).para_texto(), "corrigida lá")  # type: ignore[union-attr]
        self.assertEqual(self.caderno.estado(2).estado, caderno.EDITADA)  # type: ignore[union-attr]

    def test_a_conferida_tambem_vence(self) -> None:
        self._gravar(3, "conferida aqui", correcoes=0)
        self.caderno.marcar(3, caderno.CONFERIDA)
        volta = self.trazer(_da_suite(3, _texto("outra coisa")))
        self.assertEqual(volta.guardadas, (3,))
        self.assertEqual(self.caderno.estado(3).estado, caderno.CONFERIDA)  # type: ignore[union-attr]

    def test_o_que_ja_e_igual_nao_mexe_em_nada(self) -> None:
        self.trazer(_da_suite(4, _texto("uma vez")))
        anterior = self.caderno.caminho(4, tipo="anterior")
        self.assertEqual(self.trazer(_da_suite(4, _texto("uma vez"))).iguais, (4,))
        self.assertFalse(anterior.exists(), "a segunda vez não gira a folha para anterior")

    def test_somente_leitura_recusa_e_diz(self) -> None:
        self._gravar(5, "lida", correcoes=0)
        self.caderno.somente_leitura = True
        volta = self.trazer(_da_suite(5, _texto("da revisão")))
        self.assertEqual(volta.recusadas, (5,))
        self.assertIn("não gravada(s) (6)", volta.frase())

    def test_a_frase_conta_as_folhas_de_um(self) -> None:
        self._gravar(2, "aqui", correcoes=1)
        volta = self.trazer(_da_suite(0, _texto("a")), _da_suite(2, _texto("b")))
        self.assertEqual(volta.frase(), "1 folha(s) trazida(s) da revisão (1); 1 já corrigida(s) aqui, com a da revisão em «anterior» (3).")
        self.assertEqual(caderno_na_suite.Volta().frase(), "Nenhuma folha foi editada na Revisão de texto da suíte.")


if __name__ == "__main__":
    unittest.main()
