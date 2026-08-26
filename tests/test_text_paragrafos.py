"""Onde um parágrafo termina e outro começa (S-192).

**A margem é por coluna, e o teste que trava isso é o que dá valor ao arquivo.** A mediana das
esquerdas de uma página de duas colunas não é margem nenhuma -- metade das linhas começa em 122 e
metade em 893. Com ela, ou a coluna da direita inteira parece recuada (cada linha vira um
parágrafo), ou a da esquerda perde todos os recuos que tem.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from chess_diagram_ocr.text.paragrafos import (
    QUANTIL_DA_MARGEM,
    RECUO_DE_PARAGRAFO,
    SALTO_DE_PARAGRAFO,
    Linha,
    cortar,
    metricas_por_coluna,
)

ALTURA = 20
PASSO = 30
MARGEM_ESQUERDA = 122
MARGEM_DIREITA = 893


def corrida(quantas: int, *, coluna: int = 0, margem: int = MARGEM_ESQUERDA, topo: int = 100) -> list[Linha]:
    """Linhas seguidas, todas na margem: um parágrafo só."""
    return [
        Linha(topo=topo + i * PASSO, esquerda=margem, altura=ALTURA, texto=f"linha {i}", coluna=coluna)
        for i in range(quantas)
    ]


class RecuoTests(unittest.TestCase):
    def test_o_recuo_abre_paragrafo(self) -> None:
        linhas = corrida(3)
        linhas.append(Linha(topo=100 + 3 * PASSO, esquerda=MARGEM_ESQUERDA + 40, altura=ALTURA, texto="novo"))
        linhas.extend(corrida(2, topo=100 + 4 * PASSO))
        paragrafos = cortar(linhas)
        self.assertEqual(2, len(paragrafos))
        self.assertTrue(paragrafos[1].texto.startswith("novo"))

    def test_um_recuo_pequeno_demais_nao_abre(self) -> None:
        """A justificação move a esquerda alguns pixels; recuo de parágrafo é outra escala."""
        linhas = corrida(3)
        pequeno = int(ALTURA * RECUO_DE_PARAGRAFO) - 2
        linhas.append(Linha(topo=100 + 3 * PASSO, esquerda=MARGEM_ESQUERDA + pequeno, altura=ALTURA, texto="x"))
        self.assertEqual(1, len(cortar(linhas)))


class SaltoTests(unittest.TestCase):
    def test_o_salto_vertical_abre_paragrafo(self) -> None:
        """A notação em negrito entre parágrafos usa espaço em branco, e não recuo."""
        linhas = corrida(3)
        salto = int(ALTURA * (1 + SALTO_DE_PARAGRAFO)) + 4
        linhas.append(
            Linha(topo=linhas[-1].topo + salto, esquerda=MARGEM_ESQUERDA, altura=ALTURA, texto="depois do salto")
        )
        paragrafos = cortar(linhas)
        self.assertEqual(2, len(paragrafos))
        self.assertEqual("depois do salto", paragrafos[1].texto)

    def test_o_espacamento_normal_nao_abre(self) -> None:
        self.assertEqual(1, len(cortar(corrida(6))))


class PesoTests(unittest.TestCase):
    """A quarta regra, e a folha 51 do Dvoretsky que a mediu.

    **Naquela página nem o recuo nem o salto veem o corte.** A prosa e a notação em negrito se
    alternam num entrelinhamento constante, e o que as separa é só o peso da fonte. Sem esta
    regra, cinco dos oito parágrafos de texto da folha saíam grudados -- e o bloco grudado sai
    `negrito=None`, que é a aba dizendo "o livro não informa" numa página em que ele informa.
    """

    def _folha(self) -> list[Linha]:
        """Prosa, lance em negrito, prosa: sem recuo e sem salto, como no Dvoretsky."""
        pesos = [False, False, False, True, False, False]
        return [
            Linha(
                topo=100 + i * PASSO,
                esquerda=MARGEM_ESQUERDA,
                altura=ALTURA,
                texto=f"linha {i}",
                negrito=peso,
            )
            for i, peso in enumerate(pesos)
        ]

    def test_a_mudanca_de_peso_abre_paragrafo(self) -> None:
        paragrafos = cortar(self._folha())
        self.assertEqual(3, len(paragrafos))
        self.assertEqual("linha 3", paragrafos[1].texto)

    def test_sem_o_peso_a_mesma_folha_sai_grudada(self) -> None:
        """O fixture só vale se as outras três regras estiverem mesmo cegas a este corte."""
        sem_peso = [
            Linha(topo=ln.topo, esquerda=ln.esquerda, altura=ln.altura, texto=ln.texto)
            for ln in self._folha()
        ]
        self.assertEqual(1, len(cortar(sem_peso)), "o fixture ganhou recuo ou salto; refazê-lo")

    def test_o_desconhecido_nao_abre_paragrafo(self) -> None:
        """**`None` de um lado é "não se sabe"**, e não se abre parágrafo sobre o que não se sabe.

        É o caminho dos 26 livros do acervo cuja camada não registra peso: toda linha é `None`, e
        a regra fica inerte.
        """
        linhas = self._folha()
        meio = linhas[3]
        linhas[3] = Linha(topo=meio.topo, esquerda=meio.esquerda, altura=meio.altura, texto=meio.texto)
        self.assertEqual(1, len(cortar(linhas)))

    def test_o_peso_igual_nao_abre_paragrafo(self) -> None:
        linhas = [
            Linha(topo=100 + i * PASSO, esquerda=MARGEM_ESQUERDA, altura=ALTURA, texto=f"l{i}", negrito=True)
            for i in range(4)
        ]
        self.assertEqual(1, len(cortar(linhas)))


class ColunaTests(unittest.TestCase):
    """S-192 e a lição da F61."""

    def test_a_margem_e_por_coluna(self) -> None:
        """**Com a mediana da página, a coluna da direita inteira vira um parágrafo por linha.**

        É o defeito medido no projeto de origem: metade das linhas começa em 122 e metade em 893,
        e a mediana cai num dos dois.
        """
        linhas = [*corrida(5, coluna=0, margem=MARGEM_ESQUERDA), *corrida(5, coluna=1, margem=MARGEM_DIREITA)]
        metricas = metricas_por_coluna(linhas)
        self.assertEqual(MARGEM_ESQUERDA, metricas[0][0])
        self.assertEqual(MARGEM_DIREITA, metricas[1][0])

        paragrafos = cortar(linhas)
        self.assertEqual(2, len(paragrafos), "a coluna da direita se despedaçou")
        self.assertEqual([0, 1], [p.coluna for p in paragrafos])

    def test_a_troca_de_coluna_abre_paragrafo_mesmo_sem_recuo_e_sem_salto(self) -> None:
        """**No fim da coluna o salto vertical é negativo**: a leitura volta ao topo da página.

        Nem o recuo nem o salto veem esse corte, e é por isso que a terceira regra existe.
        """
        esquerda = corrida(4, coluna=0, margem=MARGEM_ESQUERDA, topo=600)
        direita = corrida(4, coluna=1, margem=MARGEM_DIREITA, topo=100)
        self.assertLess(direita[0].topo, esquerda[-1].topo, "o fixture não tem salto negativo")
        self.assertEqual(2, len(cortar([*esquerda, *direita])))

    def test_o_recuo_da_coluna_da_direita_e_visto(self) -> None:
        """O outro lado da mesma moeda: com a mediana da página, ele **some**."""
        linhas = [*corrida(4, coluna=0), *corrida(3, coluna=1, margem=MARGEM_DIREITA)]
        linhas.append(
            Linha(topo=100 + 3 * PASSO, esquerda=MARGEM_DIREITA + 40, altura=ALTURA, texto="recuado", coluna=1)
        )
        paragrafos = cortar(linhas)
        self.assertEqual(3, len(paragrafos))
        self.assertEqual("recuado", paragrafos[-1].texto)


class MetricasTests(unittest.TestCase):
    def test_a_metrica_da_pagina_vence_a_do_trecho(self) -> None:
        """**A mediana de cinco linhas entre dois diagramas não diz onde fica a margem.**

        Passar as métricas de fora é o que permite cortar um trecho sem ele reinventar a margem.
        """
        pagina = corrida(20, margem=MARGEM_ESQUERDA)
        recuo = MARGEM_ESQUERDA + 40
        # Dois parágrafos de duas linhas, entre dois diagramas: recuo, margem, recuo, margem.
        trecho = [
            Linha(topo=500, esquerda=recuo, altura=ALTURA, texto="a"),
            Linha(topo=530, esquerda=MARGEM_ESQUERDA, altura=ALTURA, texto="b"),
            Linha(topo=560, esquerda=recuo, altura=ALTURA, texto="c"),
            Linha(topo=590, esquerda=MARGEM_ESQUERDA, altura=ALTURA, texto="d"),
        ]

        # **Sozinho, o trecho erra**: com quatro linhas metade recuadas, a mediana das esquerdas
        # cai no recuo, e aí nenhuma linha parece recuada -- os dois parágrafos viram um.
        self.assertEqual(1, len(cortar(trecho)), "o trecho sozinho deixou de errar; refazer o fixture")

        # Com a métrica da página, o recuo volta a ser recuo.
        metricas = metricas_por_coluna(pagina)
        self.assertEqual(MARGEM_ESQUERDA, metricas[0][0])
        self.assertEqual(["a b", "c d"], [p.texto for p in cortar(trecho, metricas)])

    def test_sem_linha_nenhuma(self) -> None:
        self.assertEqual([], cortar([]))
        self.assertEqual({}, metricas_por_coluna([]))

    def test_o_texto_do_paragrafo_junta_as_linhas_com_espaco(self) -> None:
        paragrafos = cortar(corrida(3))
        self.assertEqual("linha 0 linha 1 linha 2", paragrafos[0].texto)
        self.assertEqual(3, len(paragrafos[0].linhas))



class QuantilDaMargemTests(unittest.TestCase):
    """A margem sai de um quantil declarado, e a S-257 mediu qual (`docs/metrics/`)."""

    def test_a_margem_sai_do_quantil_declarado(self) -> None:
        """`quantil=` escolhe a posição na lista ordenada das esquerdas, e o padrão é a mediana."""
        linhas = [
            Linha(topo=i * PASSO, esquerda=MARGEM_ESQUERDA + salto, altura=ALTURA, texto="x")
            for i, salto in enumerate((0, 0, 40, 40, 40))
        ]
        # Três das cinco linhas estão no recuo: a mediana cai nele, o décimo não.
        self.assertEqual(MARGEM_ESQUERDA + 40, metricas_por_coluna(linhas)[0][0])
        self.assertEqual(MARGEM_ESQUERDA, metricas_por_coluna(linhas, quantil=0.10)[0][0])
        self.assertEqual(QUANTIL_DA_MARGEM, 0.5, "o padrão é a mediana -- ver a S-257")

    def test_a_coluna_de_recuo_frequente_perde_a_margem_na_mediana(self) -> None:
        """O defeito que originou a S-257 existe, e o teste o guarda em vez de escondê-lo.

        Ele **não** é o critério de aceite do item: a medição contra referência disse que consertá-lo
        pelo quantil não paga (dois acertos em 323). O que este teste trava é que o fenômeno é real,
        para que quem mexer na régua saiba o que está mexendo.
        """
        linhas = [
            Linha(topo=i * PASSO, esquerda=MARGEM_ESQUERDA + salto, altura=ALTURA, texto=f"l{i}")
            for i, salto in enumerate((40, 0, 40, 0, 40, 0, 40))
        ]
        # Quatro das sete no recuo: com a mediana, nenhuma linha parece recuada e tudo vira um só.
        self.assertEqual(1, len(cortar(linhas)))
        # Com o quantil baixo, os quatro parágrafos aparecem.
        metricas = metricas_por_coluna(linhas, quantil=0.10)
        self.assertEqual(4, len(cortar(linhas, metricas)))

    def test_a_altura_nao_segue_o_quantil(self) -> None:
        """A altura continua sendo a mediana: ela mede o corpo da fonte, que é simétrico."""
        linhas = [
            Linha(topo=i * PASSO, esquerda=MARGEM_ESQUERDA, altura=altura, texto="x")
            for i, altura in enumerate((10, 20, 20, 20, 60))
        ]
        self.assertEqual(20, metricas_por_coluna(linhas, quantil=0.10)[0][1])
        self.assertEqual(20, metricas_por_coluna(linhas)[0][1])


class ReferenciaDeParagrafoTests(unittest.TestCase):
    """O conjunto que a S-257 mediu está no disco, e os números do relatório saem dele."""

    RAIZ = Path(__file__).resolve().parents[1]
    REFERENCIA = RAIZ / "docs" / "metrics" / "texto_paragrafo_referencia.jsonl"
    RELATORIO = RAIZ / "docs" / "metrics" / "texto_paragrafo_referencia.json"

    def registros(self) -> list[dict]:
        bruto = self.REFERENCIA.read_text(encoding="utf-8")
        return [json.loads(linha) for linha in bruto.splitlines() if linha.strip()]

    def test_a_referencia_esta_versionada_com_livro_folha_e_marca(self) -> None:
        registros = self.registros()
        self.assertTrue(registros, "a referência da S-257 sumiu do disco")
        for registro in registros:
            self.assertIn("livro", registro)
            self.assertIn("folha", registro)
            for linha in registro["linhas"]:
                self.assertIn("texto", linha)
                self.assertEqual(4, len(linha["bbox"]))
                # `None` é "esta coluna não é justificada, não se sabe" -- e ele é declarado.
                self.assertIn(linha["comeca"], (True, False, None))

    def test_o_relatorio_bate_com_a_referencia_no_disco(self) -> None:
        """S-135 aplicada a estes dois arquivos: o número publicado é contável no conjunto."""
        registros = self.registros()
        relatorio = json.loads(self.RELATORIO.read_text(encoding="utf-8"))
        self.assertEqual(len(registros), relatorio["folhas"])
        self.assertEqual(
            sum(1 for r in registros for x in r["linhas"] if x["comeca"] is not None),
            relatorio["linhas_com_referencia"],
        )
        self.assertEqual(
            sum(1 for r in registros for x in r["linhas"] if x["comeca"] is True),
            relatorio["paragrafos_na_referencia"],
        )
        self.assertEqual("docs/metrics/texto_paragrafo_referencia.jsonl", relatorio["referencia"])

    def test_o_relatorio_traz_os_dois_candidatos_e_o_que_ficou(self) -> None:
        """Sem os dois lados no relatório, "não há vão" é afirmação sem conta."""
        relatorio = json.loads(self.RELATORIO.read_text(encoding="utf-8"))
        quantis = [c["quantil"] for c in relatorio["candidatos"]]
        self.assertIn(QUANTIL_DA_MARGEM, quantis, "o valor em uso não foi medido")
        self.assertIn(0.10, quantis, "o candidato que a S-257 recusou saiu do relatório")
        for candidato in relatorio["candidatos"]:
            for chave in ("precisao", "recall", "f1", "blocos"):
                self.assertIn(chave, candidato)

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
