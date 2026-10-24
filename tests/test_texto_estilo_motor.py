"""`cvoff-texto-estilo-motor`: a conta que diz se o estilo da camada chega ao documento (S-660).

A leitura de verdade precisa dos PDFs e do classificador de glifo, que não vêm no repositório; o
que se afirma aqui é a régua -- o casamento dos textos, a contagem de chegou e de a mais, e o
protocolo das folhas --, com documentos montados à mão.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.cli import texto_estilo_motor as medida
from chess_diagram_ocr.text import rico


def _doc(*trechos: tuple[str, dict]) -> rico.DocumentoRico:
    return rico.DocumentoRico(corridas=tuple(rico.Corrida(texto, rico.Atributos(**attrs)) for texto, attrs in trechos))


class ContaTests(unittest.TestCase):
    def test_o_negrito_que_chegou_conta(self) -> None:
        ref = _doc(("1.e4 ", {"negrito": True}), ("e o resto", {}))
        contas = medida.comparar(ref, ref)
        self.assertEqual(contas["negrito_declarado"], 4, "espaço não conta")
        self.assertEqual(contas["negrito_chegou"], 4)
        self.assertEqual(medida.perdas(contas)["negrito"], 0.0)

    def test_o_negrito_que_sumiu_e_perda(self) -> None:
        ref = _doc(("1.e4 ", {"negrito": True}), ("e o resto", {}))
        sem = _doc(("1.e4 e o resto", {}))
        self.assertEqual(medida.perdas(medida.comparar(ref, sem))["negrito"], 1.0)

    def test_o_estilo_a_mais_e_contado_a_parte(self) -> None:
        ref = _doc(("texto em pe", {}))
        inclinado = _doc(("texto em pe", {"italico": True}))
        contas = medida.comparar(ref, inclinado)
        self.assertEqual(contas["italico_a_mais"], 9)
        self.assertIsNone(medida.perdas(contas)["italico"], "não há itálico declarado para perder")

    def test_o_titulo_conta_como_negrito_porque_a_tela_o_pinta_assim(self) -> None:
        ref = _doc(("Capitulo", {"negrito": True}))
        titulo = _doc(("Capitulo", {"estilo": rico.ESTILO_TITULO}))
        self.assertEqual(medida.comparar(ref, titulo)["negrito_chegou"], 8)

    def test_o_texto_do_glifo_que_erra_letra_e_casado_pelo_resto(self) -> None:
        """O glifo lê `p/ayer` onde a camada tem `player`: os outros cinco casam e contam."""
        ref = _doc(("player", {"italico": True}))
        lido = _doc(("p/ayer", {"italico": True}))
        contas = medida.comparar(ref, lido)
        self.assertEqual(contas["casados"], 5)
        self.assertEqual(contas["italico_chegou"], 5)


class ProtocoloTests(unittest.TestCase):
    def test_folhas_espacadas_longe_da_capa_e_do_fim(self) -> None:
        self.assertEqual(medida.folhas_de(100, 4), [20, 40, 60, 80])
        self.assertEqual(medida.folhas_de(3, 4), [1, 2])
        self.assertEqual(medida.folhas_de(0, 4), [])

    def test_o_total_soma_as_contagens_e_refaz_a_perda(self) -> None:
        """A linha de cada livro traz `perda` e `folhas`; o total soma contagem, e não dicionário."""
        livro = {"negrito_declarado": 10, "negrito_chegou": 5, "folhas": 4, "perda": {"negrito": 0.5, "italico": None}}
        outro = {"negrito_declarado": 10, "negrito_chegou": 10, "folhas": 4, "perda": {"negrito": 0.0, "italico": None}}
        total = medida.total_por_motor({"a.pdf": {"glifo": livro}, "b.pdf": {"glifo": outro}}, ("glifo",))
        self.assertEqual(total["glifo"]["negrito_declarado"], 20)
        self.assertEqual(total["glifo"]["folhas"], 8)
        self.assertEqual(total["glifo"]["perda"]["negrito"], 0.25)

    def test_so_o_livro_que_perde_mais_que_o_limiar_e_nomeado(self) -> None:
        por_livro = {
            "a.pdf": {"glifo": {"perda": {"negrito": 0.5, "italico": None}}},
            "b.pdf": {"glifo": {"perda": {"negrito": 0.005, "italico": 0.0}}},
        }
        self.assertEqual(
            medida.livros_com_perda(por_livro),
            [{"livro": "a.pdf", "motor": "glifo", "estilo": "negrito", "perda": 0.5}],
        )


if __name__ == "__main__":
    unittest.main()
