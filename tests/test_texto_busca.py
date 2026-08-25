"""Achar e substituir no documento, sem widget nenhum (S-245).

O que estes testes travam é a metade cara do item: a **contagem** que a lista de confirmação mostra
tem de ser a mesma que a troca executa, e o atributo do trecho tem de atravessar a troca. Uma
substituição em massa que perdesse o negrito -- ou o `bloco`, que é o que liga a correção à S-239 --
seria trabalho apagado em silêncio sobre um texto que alguém passou a tarde corrigindo.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text import busca, correcao, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida


def _pagina(*textos: str) -> PaginaLida:
    blocos = [
        BlocoDeTexto.de_linhas([LinhaLida(t, (0.0, i * 10.0, 100.0, i * 10.0 + 9.0), 1.0, "camada")])
        for i, t in enumerate(textos)
    ]
    return PaginaLida(documento="livro.pdf", pagina=0, colunas=(Coluna(indice=0, blocos=tuple(blocos)),))


class AcharTests(unittest.TestCase):
    def test_achar_percorre_o_documento_sem_widget(self) -> None:
        """O critério de aceite: a mesma função responde com a janela fechada."""
        doc = rico.de_texto("1.Nf3 e depois 2.Nf3 outra vez")
        achadas = busca.achar(doc, "Nf3")
        self.assertEqual([(o.inicio, o.texto) for o in achadas], [(2, "Nf3"), (17, "Nf3")])

    def test_a_agulha_vazia_nao_acha_nada(self) -> None:
        """Uma busca sem termo casaria com toda posição, e acenderia a lista inteira da troca."""
        self.assertEqual(busca.achar(rico.de_texto("qualquer coisa"), ""), ())

    def test_a_figurina_casa_com_a_letra_quando_ligado(self) -> None:
        doc = rico.de_texto("1.Nf3 e 2.♘d4")
        com = [o.texto for o in busca.achar(doc, "N", casar_figurina=True)]
        sem = [o.texto for o in busca.achar(doc, "N", casar_figurina=False)]
        self.assertEqual(com, ["N", "♘"])
        self.assertEqual(sem, ["N"])

    def test_procurar_a_figurina_acha_a_letra(self) -> None:
        """O caminho contrário, que é o mesmo interruptor: quem copia um `♘` da página e o procura
        quer os dois."""
        doc = rico.de_texto("1.Nf3 e 2.♘d4")
        achadas = [o.texto for o in busca.achar(doc, "♘", casar_figurina=True)]
        self.assertEqual(achadas, ["N", "♘"])

    def test_o_contexto_traz_o_que_esta_em_volta(self) -> None:
        """A lista da confirmação é o que impede a troca errada, e ela se lê pelo contexto."""
        doc = rico.de_texto("uma frase comprida com a palavra alvo no meio dela, e mais texto")
        (achada,) = busca.achar(doc, "alvo")
        self.assertIn("palavra alvo no meio", achada.contexto)

    def test_a_ocorrencia_sabe_de_que_bloco_saiu(self) -> None:
        """Sem o bloco, a troca deixa de ser correção **daquele** bloco para a S-239."""
        doc = rico.de_pagina(_pagina("primeiro bloco", "segundo com alvo"))
        (achada,) = busca.achar(doc, "alvo")
        self.assertEqual(achada.bloco, 1)


class SubstituirTests(unittest.TestCase):
    def test_a_contagem_bate_com_as_trocas(self) -> None:
        """O critério de aceite: o número que a lista mostra é o número de trocas feitas."""
        doc = rico.de_texto("a, b, c, d")
        achadas = busca.achar(doc, ",")
        novo, feitas = busca.substituir_todas(doc, ",", ";")
        self.assertEqual(len(achadas), feitas)
        self.assertEqual(novo.para_texto(), "a; b; c; d")

    def test_o_desmarcado_nao_e_trocado(self) -> None:
        doc = rico.de_texto("a, b, c")
        novo, feitas = busca.substituir_todas(doc, ",", ";", fora=[0])
        self.assertEqual(feitas, 1)
        self.assertEqual(novo.para_texto(), "a, b; c")

    def test_a_troca_preserva_o_atributo(self) -> None:
        """Trocar uma palavra em negrito devolve a palavra nova **em negrito**."""
        doc = rico.alternar(rico.de_texto("o bispo e o rei"), 2, 7, "negrito")
        novo, _ = busca.substituir_todas(doc, "bispo", "cavalo")
        negrito = [c.texto for c in novo.corridas if c.atributos.negrito]
        self.assertEqual(negrito, ["cavalo"])

    def test_a_troca_preserva_o_bloco_e_vira_correcao(self) -> None:
        """Cada troca vira uma `Correcao` da S-239 -- **derivada**, e não gravada ao lado.

        O que a substituição precisa preservar para isso acontecer é o `bloco`: com ele,
        `text/correcao.py` compara o que está na tela com o que o motor leu e o par aparece no
        relatório com a contagem, que é o que a S-213 consome.
        """
        doc = rico.de_pagina(_pagina("Black,s move"))
        novo, feitas = busca.substituir_todas(doc, ",", "'")
        self.assertEqual(feitas, 1)
        achadas = correcao.correcoes(novo)
        self.assertEqual([(c.antes, c.depois, c.bloco) for c in achadas], [(",", "'", 0)])

    def test_a_troca_de_tras_para_frente_nao_desloca_as_seguintes(self) -> None:
        """Aplicar na ordem direta escreveria a segunda ocorrência no lugar errado assim que a
        primeira mudasse de tamanho -- é a mesma razão de `text/leitor.py` aplicar assim."""
        doc = rico.de_texto("x x x")
        novo, _ = busca.substituir_todas(doc, "x", "abcdef")
        self.assertEqual(novo.para_texto(), "abcdef abcdef abcdef")

    def test_trocar_por_nada_apaga_o_trecho(self) -> None:
        doc = rico.de_texto("com  espaco duplo")
        novo, feitas = busca.substituir_todas(doc, "  ", " ")
        self.assertEqual(feitas, 1)
        self.assertEqual(novo.para_texto(), "com espaco duplo")

    def test_a_marca_do_diagrama_atravessa_a_troca(self) -> None:
        """A busca não edita a estrutura do texto: `[Diagrama N]` não é palavra a trocar.

        Ela pode até casar com a agulha -- procurar `a` acha o `a` de "Diagrama" --, e mesmo assim
        a corrida de marca sai inteira do outro lado: quem a apagasse perderia o diagrama na
        exportação seguinte (`text/documento.py`).
        """
        doc = rico.DocumentoRico(
            corridas=(
                rico.Corrida(texto="antes ", bloco=0),
                rico.Corrida(texto="[Diagrama 1]", tipo=rico.DIAGRAMA, bloco=1),
                rico.Corrida(texto=" depois", bloco=2),
            )
        )
        novo = busca.substituir(doc, busca.achar(doc, "a"), "@")
        self.assertIn("[Diagrama 1]", novo.para_texto())


class RecusaTests(unittest.TestCase):
    def test_a_expressao_regular_nao_e_interpretada(self) -> None:
        """`regex` fica **fora** por decisão (ver o cabeçalho do módulo), então `.` é um ponto."""
        doc = rico.de_texto("a.b acb")
        achadas = [o.inicio for o in busca.achar(doc, "a.b")]
        self.assertEqual(achadas, [0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
