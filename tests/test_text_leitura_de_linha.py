"""Ler a linha em vez do caractere, e a confiança que sai da concordância (S-188/S-189).

O ganho prometido é o maior do plano — 72,8% para 91,2% no acervo do projeto de origem —, e o
mecanismo é o alinhamento: `Bib1i0g[aPhY` vira `Bibliography`. **Nenhum desses erros é decidível
olhando um glifo de cada vez.**
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.leitura_de_linha import (
    MARCA,
    alinhar,
    ancora,
    confianca_por_concordancia,
    em_bloco,
)


class LeitorFalso:
    """Devolve o texto que lhe mandarem. O motor de verdade é escolha do dono do projeto (S-42)."""

    name = "falso"

    def __init__(self, texto: str, confianca: float = 0.8) -> None:
        self.texto, self.confianca = texto, confianca
        self.chamadas = 0

    def read(self, imagem: np.ndarray, **_: object) -> list[object]:  # noqa: ARG002
        self.chamadas += 1
        if not self.texto:
            return []
        return [type("TextBox", (), {"text": self.texto, "confidence": self.confianca})()]


class AncoraTests(unittest.TestCase):
    def test_o_box_vazio_vira_marca_e_nao_string_vazia(self) -> None:
        """`"".join` com um vazio encurta a string, e **tudo depois dela anda uma casa**."""
        texto, mapa = ancora([("a", 0.9), ("", 0.1), ("b", 0.9)])
        self.assertEqual(f"a{MARCA}b", texto)
        self.assertEqual([0, 1, 2], mapa)

    def test_a_ligadura_ocupa_duas_posicoes_e_continua_sendo_um_box(self) -> None:
        """**A primeira coisa que quebrou aqui.** `fi` é uma caixa e dois caracteres."""
        texto, mapa = ancora([("B", 0.9), ("fi", 0.8), ("m", 0.9)])
        self.assertEqual("Bfim", texto)
        self.assertEqual([0, 1, 1, 2], mapa)


class AlinhamentoTests(unittest.TestCase):
    def test_o_exemplo_do_item_sai_certo(self) -> None:
        pedacos = alinhar("Bib1i0g[aPhY", "Bibliography")
        self.assertEqual(list("Bibliography"), pedacos)

    def test_o_box_vazio_nao_desloca_o_alinhamento(self) -> None:
        """O critério de aceite da S-188, direto: uma leitura vazia no meio da linha."""
        pedacos = alinhar(f"ab{MARCA}cd", "abXcd")
        self.assertEqual(["a", "b", "X", "c", "d"], pedacos)

    def test_a_string_maior_que_os_boxes_descarta_o_excedente(self) -> None:
        """Quem conta boxes é a segmentação: o alinhamento não inventa caixa nova."""
        pedacos = alinhar("abc", "abcdef")
        self.assertEqual(3, len(pedacos))
        self.assertEqual("abcdef", "".join(pedacos))

    def test_o_bloco_vazio_deixa_todos_os_boxes_vazios(self) -> None:
        self.assertEqual(["", "", ""], alinhar("abc", ""))

    def test_ancora_vazia_devolve_lista_vazia(self) -> None:
        self.assertEqual([], alinhar("", "abc"))


class ConfiancaTests(unittest.TestCase):
    """A S-189 em duas linhas: concordam vale a maior, divergem vale a menor."""

    def test_concordancia_vale_a_maior_e_divergencia_a_menor(self) -> None:
        self.assertEqual(0.9, confianca_por_concordancia(0.4, 0.9, concordam=True))
        self.assertEqual(0.4, confianca_por_concordancia(0.4, 0.9, concordam=False))

    def test_a_divergencia_nao_vira_media(self) -> None:
        """Uma média esconderia o box em que as duas fontes discordam — e é lá que o erro está."""
        self.assertNotEqual(0.65, confianca_por_concordancia(0.4, 0.9, concordam=False))


class EmBlocoTests(unittest.TestCase):
    LINHA = (Caixa(0, 0, 10, 20), Caixa(10, 0, 20, 20), Caixa(20, 0, 30, 20))
    LIDOS = (("B", 0.7), ("1", 0.4), ("b", 0.6))

    def _cinza(self) -> np.ndarray:
        return np.full((20, 30), 200, np.uint8)

    def test_sem_leitor_a_leitura_por_caractere_sai_intacta(self) -> None:
        """A mesma regra da S-186 e da S-197: sem o segundo opinante, não mexer."""
        saida = em_bloco(self._cinza(), self.LINHA, self.LIDOS, None)
        self.assertEqual(["B", "1", "b"], [item.caractere for item in saida])
        self.assertEqual([0.7, 0.4, 0.6], [item.confianca for item in saida])

    def test_o_bloco_corrige_o_caractere_que_o_glifo_errou(self) -> None:
        leitor = LeitorFalso("Bib")
        saida = em_bloco(self._cinza(), self.LINHA, self.LIDOS, leitor)
        self.assertEqual(["B", "i", "b"], [item.caractere for item in saida])

    def test_o_box_que_divergiu_fica_com_a_confianca_menor(self) -> None:
        saida = em_bloco(self._cinza(), self.LINHA, self.LIDOS, LeitorFalso("Bib", confianca=0.95))
        divergente = next(item for item in saida if not item.concordam)
        concordante = next(item for item in saida if item.concordam)
        self.assertEqual(0.4, divergente.confianca)
        self.assertEqual(0.95, concordante.confianca)

    def test_a_linha_girada_cai_no_modo_por_caractere(self) -> None:
        """A faixa deixa de ser um retângulo em pé, e endireitá-la é problema da S-197."""
        girada = (Caixa(0, 0, 10, 20, 90), Caixa(10, 0, 20, 20, 90), Caixa(20, 0, 30, 20, 90))
        leitor = LeitorFalso("Bib")
        saida = em_bloco(self._cinza(), girada, self.LIDOS, leitor)
        self.assertEqual(["B", "1", "b"], [item.caractere for item in saida])
        self.assertEqual(0, leitor.chamadas, "o leitor de linha não devia nem ter sido chamado")

    def test_o_leitor_que_nao_le_nada_nao_apaga_a_leitura_por_caractere(self) -> None:
        saida = em_bloco(self._cinza(), self.LINHA, self.LIDOS, LeitorFalso(""))
        self.assertEqual(["B", "1", "b"], [item.caractere for item in saida])

    def test_o_leitor_que_levanta_nao_derruba_a_linha(self) -> None:
        """Motor de terceiro: a leitura por caractere é o que sempre existiu, e ela sobrevive."""

        class Explode:
            name = "explode"

            def read(self, *_args: object, **_kwargs: object) -> list[object]:
                raise RuntimeError("o onnx morreu")

        saida = em_bloco(self._cinza(), self.LINHA, self.LIDOS, Explode())
        self.assertEqual(["B", "1", "b"], [item.caractere for item in saida])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
