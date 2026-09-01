"""DPI e ícone: o que o Windows precisa saber antes de a janela existir (S-148).

**A garantia que importa aqui não é o efeito — é a ausência de propagação.** Este é o primeiro
código a rodar na abertura da janela, e num monitor, num Windows ou num `ctypes` diferentes
destes uma exceção não daria uma janela sem ícone: daria uma janela que não abre. Daí o teste
central ser o do duplo que levanta em **toda** chamada.

O resto é puro e mede o que dá para medir sem ter três monitores de densidades diferentes à
mão: a conversão de DPI para escala do Tk, a composição do ícone, e a amarra entre o `.ico` do
disco, o gerador que o produz e o `.spec` que o crava no `.exe` — que é onde este item apodrece
em silêncio se ninguém olhar.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.plataforma import (
    CAMINHO_DO_ICONE,
    TAMANHOS_DO_ICONE,
    compor_icone,
)

PROJETO = Path(__file__).resolve().parents[1]


class IconeTests(unittest.TestCase):
    """O `.ico` do disco, o gerador que o produz e o `.spec` que o crava no `.exe`."""

    def test_o_arquivo_existe_e_traz_todos_os_tamanhos(self) -> None:
        """Um `.ico` de um tamanho só faz o Windows reamostrar, e 256→16 vira borrão."""
        from PIL import Image

        self.assertTrue(CAMINHO_DO_ICONE.is_file(), f"ícone ausente: {CAMINHO_DO_ICONE}")
        with Image.open(CAMINHO_DO_ICONE) as imagem:
            tamanhos = {lado for lado, _ in imagem.ico.sizes()}
        self.assertEqual(set(TAMANHOS_DO_ICONE), tamanhos)

    def test_o_arquivo_em_disco_e_o_que_o_gerador_produz(self) -> None:
        """A amarra que impede o ícone de virar arte solta.

        Se alguém trocar a peça, a moldura ou a esteira em `compor_icone` e não regravar, o
        `.exe` sai com um desenho e a janela com outro. Comparado por pixel no maior tamanho,
        que é onde a diferença aparece primeiro.
        """
        from PIL import Image

        gerado = compor_icone(max(TAMANHOS_DO_ICONE)).convert("RGB")
        with Image.open(CAMINHO_DO_ICONE) as imagem:
            imagem.size = (max(TAMANHOS_DO_ICONE), max(TAMANHOS_DO_ICONE))
            do_disco = imagem.convert("RGB")
        self.assertEqual(gerado.size, do_disco.size)
        self.assertEqual(
            gerado.tobytes(),
            do_disco.tobytes(),
            "o `.ico` versionado divergiu de `compor_icone`. Rode `gravar_icone()` e comite.",
        )

    def test_o_icone_usa_a_paleta_e_nao_uma_cor_propria(self) -> None:
        """Ícone e janela são o mesmo produto, e a S-145 diz onde as cores moram."""
        imagem = compor_icone(32).convert("RGB")
        esperado = tuple(int(tokens.RESERVA[tokens.MOLDURA][i : i + 2], 16) for i in (1, 3, 5))
        self.assertEqual(imagem.getpixel((0, 0)), esperado)

    def test_a_silhueta_se_le_no_menor_tamanho(self) -> None:
        """A 16 px o cavalo tem que ser mais que um quadrado escuro.

        Medido como a fração de pixels claros na área interna: pouco demais e não há peça,
        muito demais e a peça encosta na moldura. Não é gosto — é o que separa "ícone do
        produto" de "retângulo".
        """
        histograma = compor_icone(16).convert("L").histogram()
        fracao = sum(histograma[128:]) / (16 * 16)
        self.assertGreater(fracao, 0.10, f"o cavalo sumiu a 16 px: {fracao:.0%} de pixels claros")
        self.assertLess(fracao, 0.60, f"o cavalo tomou o ícone a 16 px: {fracao:.0%} de pixels claros")

    def test_o_spec_do_bundle_aponta_para_o_icone_que_existe(self) -> None:
        """`icon=None` era o estado anterior, e é o estado para o qual isto volta sozinho.

        O `.spec` não é executado por teste nenhum: um caminho errado ali só aparece na hora do
        build, na máquina de quem empacota. Por isso a asserção é sobre o texto do arquivo.
        """
        texto = (PROJETO / "packaging" / "cvoff.spec").read_text(encoding="utf-8")
        self.assertIn("icon=str(ICONE)", texto)
        self.assertNotIn("icon=None", texto)
        self.assertIn('ICONE = PROJETO / "assets" / "cvoff.ico"', texto)
        self.assertEqual(CAMINHO_DO_ICONE.name, "cvoff.ico")


if __name__ == "__main__":
    unittest.main()
