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

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from chess_diagram_ocr.ui import plataforma, tokens
from chess_diagram_ocr.ui.plataforma import (
    CAMINHO_DO_ICONE,
    DPI_DE_REFERENCIA,
    TAMANHOS_DO_ICONE,
    compor_icone,
    consciencia_de_dpi,
    escala_de_tk,
    preparar_janela,
)

PROJETO = Path(__file__).resolve().parents[1]


class EscalaTests(unittest.TestCase):
    """A conversão de DPI para `tk scaling`. Pura, e por isso afirmável nas três densidades."""

    def test_as_tres_densidades_de_fabrica(self) -> None:
        """96 é 100%, 120 é 125%, 144 é 150% — os três padrões que um notebook novo traz."""
        self.assertAlmostEqual(escala_de_tk(96), 96 / 72, places=6)
        self.assertAlmostEqual(escala_de_tk(120), 120 / 72, places=6)
        self.assertAlmostEqual(escala_de_tk(144), 2.0, places=6)

    def test_a_escala_nao_e_dpi_sobre_96(self) -> None:
        """O erro clássico do item: `tk scaling` é pixels por **ponto**, e ponto é 1/72.

        Dividir por 96 daria 1,0 a 100% e a fonte sairia 25% menor do que o pedido em toda a
        janela — um defeito que parece "o tema mudou" e não "a conta está errada".
        """
        self.assertNotAlmostEqual(escala_de_tk(96), 1.0, places=3)
        self.assertAlmostEqual(escala_de_tk(96), 1.3333, places=4)

    def test_a_escala_e_monotonica(self) -> None:
        valores = [escala_de_tk(dpi) for dpi in (96, 120, 144, 192)]
        self.assertEqual(valores, sorted(valores))
        self.assertEqual(len(set(valores)), len(valores))

    def test_um_dpi_impossivel_cai_na_referencia(self) -> None:
        """`winfo_fpixels` numa janela não mapeada devolve 0, e escala 0 é fonte de altura 0."""
        for ruim in (0.0, -1.0):
            with self.subTest(dpi=ruim):
                self.assertAlmostEqual(escala_de_tk(ruim), escala_de_tk(DPI_DE_REFERENCIA), places=9)


class RaizQueLevanta:
    """Um duplo de `root` em que **toda** chamada levanta. O pior caso, e o teste central."""

    def __init__(self) -> None:
        self.tk = self

    def __getattr__(self, nome: str):
        def qualquer(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError(f"este root recusa {nome}")

        return qualquer

    def call(self, *_args: object) -> None:
        raise RuntimeError("este root recusa tk.call")


class ToleranciaTests(unittest.TestCase):
    """Aparência não derruba ferramenta — o contrato do `ui/theme.py` desde a S-53."""

    def test_um_root_que_recusa_tudo_nao_propaga_nada(self) -> None:
        preparo = preparar_janela(RaizQueLevanta())  # type: ignore[arg-type]
        self.assertAlmostEqual(preparo.dpi, DPI_DE_REFERENCIA, places=6)
        self.assertAlmostEqual(preparo.escala, escala_de_tk(DPI_DE_REFERENCIA), places=6)
        self.assertIsNone(preparo.icone)

    def test_a_consciencia_de_dpi_nao_levanta_sem_windll(self) -> None:
        """Num Linux, num macOS ou num Python sem `ctypes.windll`, devolve `False` e segue."""
        with patch.object(sys, "platform", "linux"):
            self.assertFalse(consciencia_de_dpi())

    def test_a_consciencia_de_dpi_tolera_a_chamada_recusada(self) -> None:
        """O Windows recusa quando o processo já criou janela, e recusar não é falhar."""
        import ctypes

        class WindllQuebrado:
            def __getattr__(self, nome: str):
                raise OSError(f"sem {nome} neste sistema")

        with patch.object(sys, "platform", "win32"), patch.object(ctypes, "windll", WindllQuebrado(), create=True):
            self.assertFalse(consciencia_de_dpi())

    def test_o_icone_ausente_nao_impede_a_janela(self) -> None:
        with patch.object(plataforma, "CAMINHO_DO_ICONE", PROJETO / "assets" / "nao-existe.ico"):
            preparo = preparar_janela(RaizQueLevanta())  # type: ignore[arg-type]
        self.assertIsNone(preparo.icone)


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


class ChamadaNaAberturaTests(unittest.TestCase):
    """A ordem: consciência de DPI **antes** de `tk.Tk()`, e o preparo logo depois.

    Depois da primeira janela o Windows já classificou o processo, e a chamada passa a existir
    sem fazer nada. É o modo de falha mais caro deste item, porque não deixa rastro: o código
    está lá, o log diz "sim", e a tela continua borrada.
    """

    def test_o_app_pede_dpi_antes_de_criar_a_janela(self) -> None:
        texto = (PROJETO / "app_tkinter.py").read_text(encoding="utf-8")
        pedido = texto.index("plataforma.consciencia_de_dpi()")
        criacao = texto.index("root = tk.Tk()")
        preparo = texto.index("plataforma.preparar_janela(root)")
        self.assertLess(pedido, criacao, "a consciência de DPI é pedida depois da janela: não tem efeito")
        self.assertLess(criacao, preparo, "`preparar_janela` precisa da janela já criada")


if __name__ == "__main__":
    unittest.main()
