"""Onde a linha quebra, e por que um número cravado sempre está errado (S-152).

**As duas falhas eram a mesma, em telas diferentes.** Doze `wraplength` de 220 a 780 px num
painel cuja largura real vai de 420 (o `minsize`) a ~1.180 (divisor à direita): com o painel
estreito o texto era **cortado** — o de procedência da Galeria, com `wraplength=220`, truncado
no meio da palavra ("Whit", "Jam", "antiga") —, e com o painel largo ele **quebrava cedo**,
deixando quatro linhas curtas onde caberia uma.

A varredura por literal é a metade que impede a regressão: sem ela o décimo terceiro número
entra exatamente como os doze entraram, um de cada vez e cada um justificável sozinho.
"""

from __future__ import annotations

import re
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from tk_root import raiz

from chess_diagram_ocr.ui import texto
from chess_diagram_ocr.ui.texto import (
    FOLGA_LATERAL,
    MEDIDA_EM_CARACTERES,
    PISO_DE_QUEBRA,
    acompanhar,
    largura_de_quebra,
    largura_media_do_caractere,
)

RAIZ = Path(__file__).resolve().parents[1]
LITERAL = re.compile(r"wraplength=\d")


class LarguraDeQuebraTests(unittest.TestCase):
    """Os três regimes, sem Tk. É o que faz o critério de aceite caber num `assertEqual`."""

    LARGURA_DO_CARACTERE = 7.0
    """Uma média plausível para Segoe UI 9. O teto vira 90 x 7 = 630 px."""

    def _quebra(self, largura_do_pai: int) -> int:
        return largura_de_quebra(largura_do_pai, self.LARGURA_DO_CARACTERE)

    def test_painel_confortavel_usa_a_largura_disponivel(self) -> None:
        """O regime do meio: o texto ocupa o painel, e não um número escolhido em 2026-07."""
        self.assertEqual(self._quebra(500), 500 - FOLGA_LATERAL)

    def test_painel_largo_para_no_teto_de_leitura(self) -> None:
        """Linha longa demais é ruim de ler mesmo quando cabe: o olho perde a linha seguinte."""
        teto = round(self.LARGURA_DO_CARACTERE * MEDIDA_EM_CARACTERES)
        self.assertEqual(self._quebra(1180), teto)
        self.assertEqual(self._quebra(3000), teto, "o teto não é teto se ele cresce com a janela")

    def test_painel_estreito_ou_nao_medido_cai_no_piso(self) -> None:
        """Antes de a janela ser mapeada `winfo_width` devolve 1: sem piso, uma palavra por
        linha em todo rótulo, arrumando-se no primeiro `<Configure>` -- um piscar por abertura."""
        for largura in (0, 1, 100, PISO_DE_QUEBRA):
            with self.subTest(largura=largura):
                self.assertEqual(self._quebra(largura), PISO_DE_QUEBRA)

    def test_a_quebra_nunca_passa_da_largura_do_pai(self) -> None:
        """O defeito do texto cortado, dito como propriedade: acima do piso, nada transborda."""
        for largura in range(PISO_DE_QUEBRA + FOLGA_LATERAL, 1400, 37):
            with self.subTest(largura=largura):
                self.assertLessEqual(self._quebra(largura), largura)

    def test_a_quebra_cresce_com_o_painel_ate_o_teto(self) -> None:
        """Monotônica: arrastar o divisor para a direita nunca estreita o texto."""
        larguras = [self._quebra(pai) for pai in (300, 500, 700, 900, 1180)]
        self.assertEqual(larguras, sorted(larguras))

    def test_o_teto_acompanha_a_fonte(self) -> None:
        """A medida é em caracteres e não em pixels: quem aumenta a fonte do Windows ganha
        linha mais larga, e continua com as mesmas 90 colunas de leitura."""
        estreita = largura_de_quebra(3000, 6.0)
        larga = largura_de_quebra(3000, 9.0)
        self.assertLess(estreita, larga)
        self.assertEqual(larga / estreita, 1.5)


class SemLiteralTests(unittest.TestCase):
    """A varredura. É a irmã da que a S-145 fez com as cores e a S-149 com as fontes."""

    LIVRES = {"texto.py"}
    """`texto.py` **é** a decisão, e é o único isento.

    `tooltip.py` não precisa de isenção e o caso dele vale ser dito: ele declara
    `wraplength: int = 360` como **parâmetro**, não como argumento cravado numa chamada. A dica
    é uma janela flutuante, sem pai cuja largura seguir -- a largura dela é escolhida, e quem a
    escolhe é quem cria o tooltip. É por isso que o padrão da varredura procura `wraplength=`
    seguido de dígito, e não a palavra solta."""

    def test_nenhum_painel_crava_wraplength(self) -> None:
        infratores = []
        arquivos = [*sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")), RAIZ / "app_tkinter.py"]
        for arquivo in arquivos:
            if arquivo.name in self.LIVRES:
                continue
            for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
                if LITERAL.search(linha):
                    infratores.append(f"{arquivo.name}:{numero}: {linha.strip()[:70]}")
        self.assertEqual([], infratores, "`wraplength` cravado num painel. Use `texto.acompanhar`.")

    def test_a_varredura_enxerga_o_que_deveria(self) -> None:
        """O controle: o padrão pega o que ela veio pegar, e ignora o que não é o defeito.

        Sem ele o teste acima passaria vazio por um `re` errado, que é a forma mais silenciosa
        de uma varredura deixar de varrer.
        """
        self.assertTrue(LITERAL.search('ttk.Label(pai, text="x", wraplength=220).pack()'))
        self.assertTrue(LITERAL.search("        ttk.Label(self, textvariable=v, wraplength=780)"))
        self.assertIsNone(LITERAL.search("    def __init__(self, w: tk.Misc, *, wraplength: int = 360) -> None:"))
        self.assertIsNone(LITERAL.search("            wraplength=self.wraplength,"))

    def test_os_painies_que_tinham_os_doze_agora_chamam_o_auxiliar(self) -> None:
        """O outro sentido: a varredura passaria vazia se alguém apagasse os rótulos."""
        esperados = {
            "app_tkinter.py": 2,
            "dataset_panel.py": 1,
            "gallery_panel.py": 1,
            # Dois: o painel de legalidade e a frase do estado vazio, que a S-170 acrescentou --
            # ela é a mais longa da aba e nasceu acompanhando a largura, e não com um número.
            "result_panel.py": 2,
            # Três: os dois que já existiam mais a linha de detalhe do motivo, que a S-153
            # acrescentou -- e que nasceu acompanhando a largura em vez de com um número.
            "review_panel.py": 3,
            "study_panel.py": 2,
            "training_dialog.py": 2,
        }
        contados = {}
        for nome in esperados:
            caminho = RAIZ / nome if nome == "app_tkinter.py" else RAIZ / "src" / "chess_diagram_ocr" / "ui" / nome
            contados[nome] = caminho.read_text(encoding="utf-8").count("texto.acompanhar(")
        self.assertEqual(esperados, contados, "um rótulo multi-linha deixou de acompanhar a largura")


class AcompanharTests(unittest.TestCase):
    """A metade que liga: o rótulo de fato reflui quando o pai muda de largura."""

    def setUp(self) -> None:
        self.janela = tk.Toplevel(raiz())
        self.janela.geometry("900x300")
        self.addCleanup(self.janela.destroy)
        self.pai = ttk.Frame(self.janela)
        self.pai.pack(fill=tk.BOTH, expand=True)

    def _rotulo_que_acompanha(self) -> ttk.Label:
        rotulo = acompanhar(ttk.Label(self.pai, text="a posição é ilegal porque " * 12))
        rotulo.pack(anchor="w")
        self.janela.update()
        return rotulo

    def test_o_rotulo_nasce_com_quebra_derivada_e_nao_com_zero(self) -> None:
        rotulo = self._rotulo_que_acompanha()
        self.assertGreaterEqual(int(rotulo.cget("wraplength")), PISO_DE_QUEBRA)

    def test_estreitar_a_janela_estreita_a_quebra(self) -> None:
        """O gesto real: arrastar o divisor. É o que os doze números cravados ignoravam."""
        rotulo = self._rotulo_que_acompanha()
        largo = int(rotulo.cget("wraplength"))

        self.janela.geometry("500x300")
        self.janela.update()
        estreito = int(rotulo.cget("wraplength"))

        self.assertLess(estreito, largo, f"a quebra ficou em {estreito} nas duas larguras")
        self.assertLessEqual(estreito, self.pai.winfo_width(), "o texto quebraria além do painel")

    def test_alargar_de_volta_devolve_a_quebra(self) -> None:
        """Sem isto o rótulo encolheria uma vez e nunca mais voltaria a usar o painel inteiro."""
        rotulo = self._rotulo_que_acompanha()
        self.janela.geometry("400x300")
        self.janela.update()
        estreito = int(rotulo.cget("wraplength"))

        self.janela.geometry("1000x300")
        self.janela.update()
        self.assertGreater(int(rotulo.cget("wraplength")), estreito)

    def test_a_largura_do_caractere_sai_da_fonte_de_verdade(self) -> None:
        """Se ela viesse de uma constante, o teto em caracteres seria um pixel com outro nome."""
        rotulo = ttk.Label(self.pai, text="x")
        medida = largura_media_do_caractere(rotulo)
        self.assertGreater(medida, 3.0)
        self.assertLess(medida, 20.0)

    def test_um_rotulo_destruido_nao_derruba_o_evento(self) -> None:
        """O `<Configure>` do pai chega depois de o filho morrer -- é rotina ao trocar de aba."""
        rotulo = self._rotulo_que_acompanha()
        rotulo.destroy()
        self.janela.geometry("600x300")
        self.janela.update()  # sem exceção: é a asserção

    def test_a_medida_cai_na_reserva_quando_a_fonte_nao_responde(self) -> None:
        class SemFonte:
            def cget(self, _opcao: str) -> str:
                raise tk.TclError("widget sem fonte")

        self.assertGreater(largura_media_do_caractere(SemFonte()), 0)  # type: ignore[arg-type]


class ModuloTests(unittest.TestCase):
    def test_o_teto_e_uma_medida_de_leitura_e_nao_um_pixel(self) -> None:
        """45 a 90 caracteres é o intervalo confortável; abaixo de 45 o teto seria decoração."""
        self.assertGreaterEqual(texto.MEDIDA_EM_CARACTERES, 45)
        self.assertLessEqual(texto.MEDIDA_EM_CARACTERES, 90)


if __name__ == "__main__":
    unittest.main()
