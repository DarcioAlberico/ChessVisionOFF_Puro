"""O box que engoliu duas linhas, e o fragmento que veio junto (S-198).

Dois defeitos com a mesma cara. O primeiro é do projeto de origem: o descendente de um `g` encosta
na linha de baixo e um caractere some -- o conserto valeu +0,3 de F1. O segundo foi **medido aqui
na S-185**: a faixa dilatada da `ocr_caption` encosta na linha de cima, e os fragmentos de
descendente que entram custam 8 pontos de CER (0,14 -> 0,22).
"""

from __future__ import annotations

import json
import unittest
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.duas_linhas import (
    ALTURA_SUSPEITA,
    GANHO_MINIMO,
    descartar_fragmentos,
    e_fragmento,
    partir,
    separar,
    vale,
)

RAIZ = Path(__file__).resolve().parents[1]

ESCALA = 20


def _duas_linhas_coladas() -> tuple[np.ndarray, Caixa]:
    """Duas faixas de tinta com um vale entre elas: o `g` que encostou na linha de baixo."""
    imagem = np.zeros((120, 60), dtype=np.uint8)
    cv2.rectangle(imagem, (5, 10), (55, 45), 255, -1)  # a linha de cima
    cv2.line(imagem, (28, 45), (32, 62), 255, 3)  # o descendente que liga as duas
    cv2.rectangle(imagem, (5, 62), (55, 100), 255, -1)  # a linha de baixo
    return imagem, Caixa(5, 10, 55, 100)


def _arbitro(inteiro: float, partido: float) -> object:
    def julgar(caixas: Sequence[Caixa]) -> float:
        return partido if len(caixas) > 1 else inteiro

    return julgar


class ValeTests(unittest.TestCase):
    def test_o_vale_sai_entre_as_duas_linhas(self) -> None:
        imagem, caixa = _duas_linhas_coladas()
        corte = vale(imagem, caixa)
        assert corte is not None
        self.assertGreater(corte, 45)
        self.assertLess(corte, 62)

    def test_o_minimo_colado_na_borda_nao_e_vale(self) -> None:
        """Ele é o fim do próprio glifo, e cortar ali produz um pedaço vazio."""
        imagem = np.zeros((60, 40), dtype=np.uint8)
        cv2.rectangle(imagem, (5, 5), (35, 55), 255, -1)
        caixa = Caixa(5, 0, 35, 60)
        corte = vale(imagem, caixa)
        if corte is not None:
            self.assertGreater(corte, caixa.y1 + 5)
            self.assertLess(corte, caixa.y2 - 5)

    def test_sem_vale_devolve_none(self) -> None:
        """O descendente preenche a faixa: quem corta é a fronteira da banda, não o perfil."""
        cheia = np.full((60, 40), 255, dtype=np.uint8)
        self.assertIsNone(vale(cheia, Caixa(0, 0, 40, 60)))

    def test_recorte_curto_demais_nao_tem_perfil(self) -> None:
        self.assertIsNone(vale(np.zeros((2, 2), dtype=np.uint8), Caixa(0, 0, 2, 2)))


class PartirTests(unittest.TestCase):
    """**A geometria propõe, o classificador dispõe** -- a mesma regra da S-197."""

    def setUp(self) -> None:
        self.caixa = Caixa(5, 10, 55, 100)

    def test_sem_arbitro_nao_corta(self) -> None:
        """Cortar sem confirmação custou 2,3 pontos de F1 no projeto de origem."""
        self.assertEqual([self.caixa], partir(self.caixa, 55))

    def test_o_arbitro_que_recusa_deixa_a_caixa_inteira(self) -> None:
        self.assertEqual([self.caixa], partir(self.caixa, 55, arbitro=_arbitro(inteiro=0.9, partido=0.5)))

    def test_o_ganho_precisa_superar_a_margem(self) -> None:
        """**Na dúvida, não cortar**: cortar um glifo bom troca um caractere certo por dois
        errados. E a régua é uma probabilidade, então ela não atravessa uma calibração."""
        raspando = _arbitro(inteiro=0.80, partido=0.80 + GANHO_MINIMO / 2)
        self.assertEqual([self.caixa], partir(self.caixa, 55, arbitro=raspando))

        folgado = _arbitro(inteiro=0.80, partido=0.95)
        self.assertEqual(2, len(partir(self.caixa, 55, arbitro=folgado)))

    def test_os_dois_pedacos_cobrem_a_caixa_inteira(self) -> None:
        de_cima, de_baixo = partir(self.caixa, 55, arbitro=_arbitro(inteiro=0.5, partido=0.95))
        self.assertEqual((self.caixa.y1, 55), (de_cima.y1, de_cima.y2))
        self.assertEqual((55, self.caixa.y2), (de_baixo.y1, de_baixo.y2))
        self.assertEqual((self.caixa.x1, self.caixa.x2), (de_cima.x1, de_cima.x2))

    def test_corte_fora_da_caixa_e_ignorado(self) -> None:
        for corte in (self.caixa.y1, self.caixa.y2, self.caixa.y1 - 5, self.caixa.y2 + 5):
            with self.subTest(corte=corte):
                self.assertEqual([self.caixa], partir(self.caixa, corte, arbitro=_arbitro(0.1, 0.99)))


class SepararTests(unittest.TestCase):
    def test_a_caixa_de_duas_linhas_e_partida(self) -> None:
        imagem, caixa = _duas_linhas_coladas()
        outra = Caixa(5, 105, 25, 118)
        saida = separar(imagem, [caixa, outra], escala=ESCALA, arbitro=_arbitro(inteiro=0.4, partido=0.95))
        self.assertEqual(3, len(saida))
        self.assertIn(outra, saida)

    def test_a_caixa_de_altura_normal_nao_e_tocada(self) -> None:
        imagem, _ = _duas_linhas_coladas()
        normal = Caixa(5, 10, 25, 10 + ESCALA)
        self.assertLess(normal.altura, ALTURA_SUSPEITA * ESCALA, "o fixture não é de altura normal")
        self.assertEqual([normal], separar(imagem, [normal], escala=ESCALA, arbitro=_arbitro(0.1, 0.99)))

    def test_sem_vale_a_fronteira_da_banda_decide(self) -> None:
        """Quando o descendente preenche a faixa, o corte vem de quem já sabe onde a linha acaba."""
        cheia = np.full((120, 60), 255, dtype=np.uint8)
        caixa = Caixa(0, 0, 60, 100)
        sem_fronteira = separar(cheia, [caixa], escala=ESCALA, arbitro=_arbitro(0.4, 0.95))
        self.assertEqual([caixa], sem_fronteira)

        com_fronteira = separar(
            cheia, [caixa], escala=ESCALA, arbitro=_arbitro(0.4, 0.95), fronteira={id(caixa): 50}
        )
        self.assertEqual(2, len(com_fronteira))

    def test_escala_zero_nao_mexe_em_nada(self) -> None:
        imagem, caixa = _duas_linhas_coladas()
        self.assertEqual([caixa], separar(imagem, [caixa], escala=0))


class FragmentoTests(unittest.TestCase):
    """O achado da S-185: a faixa dilatada encosta na linha de cima e custa 8 pontos de CER."""

    def test_a_linha_de_fragmentos_e_reconhecida(self) -> None:
        fragmentos = [Caixa(i * 20, 0, i * 20 + 10, 4) for i in range(4)]
        self.assertTrue(e_fragmento(fragmentos, escala=ESCALA))

    def test_a_linha_de_texto_com_um_ponto_nao_e_fragmento(self) -> None:
        """Uma linha com um `.` e cinco letras não é fragmento; uma com quatro pedaços de 4 px é."""
        linha = [Caixa(i * 20, 0, i * 20 + 12, ESCALA) for i in range(5)]
        linha.append(Caixa(120, ESCALA - 4, 125, ESCALA))
        self.assertFalse(e_fragmento(linha, escala=ESCALA))

    def test_linha_vazia_e_escala_zero_nao_levantam(self) -> None:
        self.assertFalse(e_fragmento([], escala=ESCALA))
        self.assertFalse(e_fragmento([Caixa(0, 0, 4, 4)], escala=0))

    def test_descartar_tira_so_as_linhas_de_fragmento(self) -> None:
        boa = [Caixa(i * 20, 30, i * 20 + 12, 30 + ESCALA) for i in range(5)]
        ruim = [Caixa(i * 20, 0, i * 20 + 10, 4) for i in range(4)]
        self.assertEqual([boa], descartar_fragmentos([ruim, boa], escala=ESCALA))


class LimiarEcalibracaoTests(unittest.TestCase):
    """**A régua é uma probabilidade, e por isso ela não atravessa uma calibração.**

    `GANHO_MINIMO` compara a confiança dos dois pedaços contra a do inteiro. Confiança é uma
    escala que a temperatura move -- foi o achado da F69 no projeto de origem --, então um
    retreino que mude a temperatura muda o significado do limiar sem tocar no número.

    O que este teste faz é o que a S-198 pede: **falhar** quando o relatório do ganho descreve
    outro modelo. Ele não adivinha o limiar novo; ele obriga alguém a remedir.
    """

    RELATORIO = RAIZ / "docs" / "metrics" / "texto_duas_linhas.json"
    METADADO = RAIZ / "models" / "char_meta.json"

    def _relatorio(self) -> dict:
        if not self.RELATORIO.exists():
            self.skipTest("o ganho ainda não foi medido: rode `cvoff-texto-duas-linhas`")
        return json.loads(self.RELATORIO.read_text(encoding="utf-8"))

    def test_o_ganho_medido_descreve_o_modelo_que_esta_publicado(self) -> None:
        relatorio = self._relatorio()
        if not self.METADADO.exists():  # pragma: no cover - clone sem o metadado
            self.skipTest("sem models/char_meta.json")
        publicado = json.loads(self.METADADO.read_text(encoding="utf-8"))

        self.assertAlmostEqual(
            relatorio["modelo"]["temperatura"],
            publicado["temperatura"],
            places=4,
            msg="A temperatura do modelo publicado mudou desde que o ganho foi medido. O limiar "
            "do corte é uma probabilidade: remeça com `cvoff-texto-duas-linhas`.",
        )
        self.assertEqual(
            relatorio["modelo"]["modelo_sha256"],
            publicado["modelo_sha256"],
            "O relatório do ganho foi medido com outros pesos.",
        )

    def test_o_limiar_gravado_no_relatorio_e_o_que_o_codigo_usa(self) -> None:
        """Mudar `GANHO_MINIMO` sem remedir deixaria o número descrevendo outro corte."""
        relatorio = self._relatorio()
        self.assertAlmostEqual(relatorio["limiares"]["ganho_minimo"], GANHO_MINIMO, places=6)
        self.assertAlmostEqual(relatorio["limiares"]["altura_suspeita"], ALTURA_SUSPEITA, places=6)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
