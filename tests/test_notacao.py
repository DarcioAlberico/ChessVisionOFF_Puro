"""Fatiar: onde acaba a prosa e começa o lance (S-208, parcial).

Os testes que carregam este arquivo são os do que **não** deve acontecer, porque é neles que o
custo é caro: prosa tratada como lance vira erro no PGN, e um número de ano juntado vira data
errada. Cada uma das duas guardas aqui saiu de uma regressão medida.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from chess_diagram_ocr.text import notacao as nt


class LanceTests(unittest.TestCase):
    def test_as_formas_de_lance_casam(self) -> None:
        for lance in ("e4", "Nf3", "♘f3", "Bxf6", "exd5", "0-0", "O-O-O", "Qh5+",
                      "R1e2", "Nbd2", "a8=Q", "gxf1=♕", "cxd5!?", "♗xh7+", "dxc2!"):
            with self.subTest(lance=lance):
                self.assertTrue(nt.LANCE.match(lance))

    def test_a_captura_sem_nada_antes_do_x_nao_e_lance(self) -> None:
        """Em SAN toda captura tem algo antes do `x`. Frouxidão aqui vira prosa tratada como lance."""
        for token in ("xf6", "x", "f6x", "xd5+"):
            with self.subTest(token=token):
                self.assertFalse(nt.LANCE.match(token))

    def test_prosa_nao_e_lance(self) -> None:
        for palavra in ("the", "and", "see", "Black", "Mecking", "an", "he"):
            with self.subTest(palavra=palavra):
                self.assertFalse(nt.LANCE.match(palavra))

    def test_o_numero_sozinho_nao_e_lance(self) -> None:
        self.assertFalse(nt.LANCE.match("15"))
        self.assertTrue(nt.e_numero_de_lance("15"))
        self.assertTrue(nt.e_numero_de_lance("15."))
        self.assertTrue(nt.e_numero_de_lance("15..."))


class FatiarTests(unittest.TestCase):
    def _tipos(self, linha: str) -> list[tuple[str, list[str]]]:
        tokens = linha.split()
        return [(f.tipo, tokens[f.inicio : f.fim]) for f in nt.fatiar(tokens)]

    def test_a_sequencia_de_lances_vira_uma_fatia(self) -> None:
        fatias = self._tipos("most probably, 19...♖g8 20 ♕h5+ ♕xh5 21 ♘xh5.")
        self.assertEqual([t for t, _ in fatias], ["prosa", "lance"])

    def test_a_prosa_pura_nunca_vira_lance(self) -> None:
        for linha in ("The rook is needed to protect d1.",
                      "In 1968 he lost to me because of the weakness",
                      "A year later he readily conceded all the dark squares"):
            with self.subTest(linha=linha[:24]):
                self.assertEqual({t for t, _ in self._tipos(linha)}, {"prosa"})

    def test_o_composto_vale_por_dois(self) -> None:
        """`19...♖g8` é número **e** lance no mesmo token, e é como o livro imprime as pretas."""
        self.assertEqual(nt.peso_de_notacao("19...♖g8"), 2)
        self.assertEqual([t for t, _ in self._tipos("simple 19...♕xf4! and")], ["prosa", "lance", "prosa"])

    def test_dois_numeros_sem_lance_nao_sao_notacao(self) -> None:
        """`capítulo 3 4 do livro` -- a guarda que nasceu do primeiro falso positivo."""
        self.assertEqual({t for t, _ in self._tipos("a resposta esta no capitulo 3 4 do livro")}, {"prosa"})

    def test_um_lance_solto_na_prosa_nao_abre_fatia(self) -> None:
        """`e4` sozinho é uma casa citada no texto; notação de verdade vem em sequência."""
        self.assertEqual({t for t, _ in self._tipos("the square e4 is weak here")}, {"prosa"})

    def test_lista_vazia_devolve_vazio(self) -> None:
        self.assertEqual(nt.fatiar([]), [])


class JuntarTests(unittest.TestCase):
    """O número de lance partido em dois -- o que a geometria não separa."""

    def test_o_numero_partido_e_juntado(self) -> None:
        self.assertEqual(
            nt.juntar_numero_de_lance("inaccuracy 1 5 0-0?! really"),
            "inaccuracy 15 0-0?! really",
        )

    def test_o_composto_com_o_numero_partido_tambem(self) -> None:
        """`1` + `9...♕xf4!` -- a forma mais comum, e a que escapou da primeira versão."""
        self.assertEqual(
            nt.juntar_numero_de_lance("simple 1 9...♕xf4!"), "simple 19...♕xf4!"
        )

    def test_o_ano_na_prosa_nao_e_tocado(self) -> None:
        """**É o teste que importa.** Fora da notação, dois números seguidos são legítimos."""
        for linha in ("In 1968 he lost to me", "a resposta esta no capitulo 3 4 do livro",
                      "sao 2 5 paginas de prosa sem lance nenhum"):
            with self.subTest(linha=linha[:22]):
                self.assertEqual(nt.juntar_numero_de_lance(linha), linha)

    def test_duas_numeracoes_legitimas_nao_sao_fundidas(self) -> None:
        """`15 2 f3 xg5` virava `152`: a divisão acontece **dentro** do número, e o pedaço da
        esquerda é um dígito só. A guarda nasceu desta regressão."""
        self.assertEqual(nt.juntar_numero_de_lance("15 2 f3 xg5 h7"), "15 2 f3 xg5 h7")

    def test_o_numero_longo_demais_nao_e_juntado(self) -> None:
        self.assertEqual(nt.juntar_numero_de_lance("999 9 Nf3 e5"), "999 9 Nf3 e5")

    def test_a_linha_de_um_token_sai_intacta(self) -> None:
        self.assertEqual(nt.juntar_numero_de_lance("15"), "15")

    def test_a_linha_vazia_sai_intacta(self) -> None:
        self.assertEqual(nt.juntar_numero_de_lance(""), "")

    def test_o_espacamento_do_resto_da_linha_e_preservado(self) -> None:
        """A junção mexe só onde junta: o resto sai token a token como entrou."""
        original = "Thus we see that in the event of 1 6 ♘f4 Black is"
        self.assertEqual(
            nt.juntar_numero_de_lance(original),
            "Thus we see that in the event of 16 ♘f4 Black is",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

class LinhaDeNotacaoTests(unittest.TestCase):
    """A régua de "este trecho é linha de lances?", e o que a S-249 mediu nela."""

    def test_a_maioria_decide_e_um_lance_solto_nao(self) -> None:
        self.assertTrue(nt.e_linha_de_notacao("1.e4 e5 2.Nf3 Nc6"))
        self.assertFalse(nt.e_linha_de_notacao("Ivkov—Dueckstein 1967"))
        self.assertFalse(
            nt.e_linha_de_notacao("White has a strong attack after the natural 19.Qh5 here"),
            "prosa que cita um lance não é linha de lances",
        )

    def test_pontuacao_solta_nao_vota(self) -> None:
        """O que a medição da S-249 trocou: `!` e `.` separados do lance não contam para nenhum lado.

        Sem isto, `28 . . . b6 ! !` são sete tokens com dois de notação -- uma linha de lances
        inteira em minoria de si mesma.
        """
        self.assertTrue(nt.e_linha_de_notacao("28 . . . b6 ! !"))
        self.assertTrue(nt.e_linha_de_notacao("2 1 . . . . e2 :"))
        # E ela não passa a dizer "sim" para o que não tem lance nenhum.
        self.assertFalse(nt.e_linha_de_notacao(". . . ! !"))
        self.assertFalse(nt.e_linha_de_notacao(""))

    def test_o_piso_de_dois_continua_valendo(self) -> None:
        """Um token de notação sozinho não faz linha de lances, por mais curto que seja o trecho."""
        self.assertFalse(nt.e_linha_de_notacao("Diagrama 45"))
        self.assertFalse(nt.e_linha_de_notacao("e4"))


class ReferenciaDeNotacaoTests(unittest.TestCase):
    """O conjunto rotulado à mão da S-249 está no disco, e o relatório sai dele."""

    RAIZ = Path(__file__).resolve().parents[1]
    REFERENCIA = RAIZ / "docs" / "metrics" / "texto_notacao_referencia.jsonl"
    RELATORIO = RAIZ / "docs" / "metrics" / "texto_notacao_estilo.json"
    ROTULOS = ("lance", "prosa", "misto", "ilegivel")

    def blocos(self) -> list[dict]:
        bruto = self.REFERENCIA.read_text(encoding="utf-8")
        return [json.loads(linha) for linha in bruto.splitlines() if linha.strip()]

    def test_a_referencia_esta_versionada_com_o_texto_de_cada_bloco(self) -> None:
        blocos = self.blocos()
        self.assertTrue(blocos, "a referência da S-249 sumiu do disco")
        for bloco in blocos:
            self.assertIn(bloco["rotulo"], self.ROTULOS)
            self.assertIn("livro", bloco)
            self.assertIn("folha", bloco)
            # O texto fica no arquivo para que o rótulo possa ser conferido -- ou contestado --
            # sem `PDF/`, que não é versionado.
            self.assertTrue(bloco["texto"].strip())

    def test_o_relatorio_bate_com_a_referencia_no_disco(self) -> None:
        blocos = self.blocos()
        relatorio = json.loads(self.RELATORIO.read_text(encoding="utf-8"))
        amostra = relatorio["amostra"]
        self.assertEqual(len(blocos), amostra["blocos"])
        for rotulo in self.ROTULOS:
            self.assertEqual(
                sum(1 for b in blocos if b["rotulo"] == rotulo),
                amostra["por_rotulo"].get(rotulo, 0),
                rotulo,
            )
        self.assertEqual(
            sum(1 for b in blocos if b["rotulo"] in ("lance", "prosa")), amostra["julgaveis"]
        )

    def test_a_regua_em_uso_reproduz_a_precisao_publicada(self) -> None:
        """O número do relatório é recontável a partir do conjunto, com a régua de hoje.

        É a guarda que impede a régua de mudar sem a medição mudar junto: quem mexer em
        `e_linha_de_notacao` e não remedir vê este teste vermelho.
        """
        blocos = [b for b in self.blocos() if b["rotulo"] in ("lance", "prosa")]
        vp = fp = fn = 0
        for bloco in blocos:
            nosso = nt.e_linha_de_notacao(bloco["texto"])
            if bloco["rotulo"] == "lance" and nosso:
                vp += 1
            elif bloco["rotulo"] == "lance":
                fn += 1
            elif nosso:
                fp += 1
        relatorio = json.loads(self.RELATORIO.read_text(encoding="utf-8"))
        publicado = next(
            c
            for c in relatorio["candidatos"]
            if c["maioria"] == 0.5 and c["regra"].startswith("pontuação não vota")
        )
        self.assertEqual(publicado["verdadeiros_positivos"], vp)
        self.assertEqual(publicado["falsos_positivos"], fp)
        self.assertEqual(publicado["falsos_negativos"], fn)
        self.assertEqual(publicado["precisao"], round(vp / (vp + fp), 4))
        self.assertEqual(publicado["recall"], round(vp / (vp + fn), 4))
