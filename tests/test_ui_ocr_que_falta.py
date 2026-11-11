"""O OCR de legenda pedido e que não subiu é dito na janela, com a frase do lugar em que ela roda (S-884).

**O defeito.** O `.exe` exclui o `onnxruntime` (`packaging/cvoff.spec`), o padrão de `ocr.engine` é
`rapidocr`, e a resposta ao `ImportError` era só uma linha de log mandando rodar
`uv sync --extra ocr` -- o que ninguém faz num executável. A janela abria como se o OCR estivesse lá.

**O teste da spec é o primeiro desta classe** e passa pelo caminho do produto: preferências, serviço
montado por elas com o import falhando de verdade, e a frase que a janela põe no rodapé ao abrir.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.settings import OcrSettings, Settings
from chess_diagram_ocr.ui import estado_do_rodape, ocr_que_falta

LIGADO = OcrSettings(enabled=True, engine="rapidocr")


def _sem_rapidocr() -> mock._patch[dict[str, object]]:
    """`None` em `sys.modules` faz o `import` levantar `ImportError`: é o `.exe` sem o onnxruntime."""
    return mock.patch.dict(sys.modules, {"rapidocr_onnxruntime": None})


class NoExecutavelTests(unittest.TestCase):
    def test_congelado_e_sem_o_motor_a_frase_e_a_do_bundle(self) -> None:
        """A spec: `sys.frozen` simulado, o import falhando, e a frase é a da versão empacotada."""
        from chess_diagram_ocr.qt import preferencias

        with _sem_rapidocr(), mock.patch.object(sys, "frozen", True, create=True):
            servico = preferencias.servico_das_preferencias(Settings(ocr=LIGADO))
            frase, severidade = ocr_que_falta.frase_de_abertura(servico, LIGADO)

        self.assertIsNone(servico.caption_reader)
        self.assertIn("versão empacotada", frase)
        self.assertIn("glifo", frase, "a frase diz o que dá para fazer dentro do executável")
        self.assertNotIn("uv sync", frase, "no executável não há `uv` a rodar")
        self.assertEqual(estado_do_rodape.AVISO, severidade)

    def test_no_checkout_a_frase_manda_instalar_o_extra(self) -> None:
        """Fora do `.exe` a resposta continua sendo o extra, e ela também chega à janela."""
        from chess_diagram_ocr.qt import preferencias

        with _sem_rapidocr(), mock.patch.object(sys, "frozen", False, create=True):
            servico = preferencias.servico_das_preferencias(Settings(ocr=LIGADO))
            frase, _ = ocr_que_falta.frase_de_abertura(servico, LIGADO)

        self.assertIn("uv sync --extra ocr", frase)
        self.assertNotIn("versão empacotada", frase)


class FraseTests(unittest.TestCase):
    """A decisão pura: quando há o que dizer, e o quê."""

    def test_ocr_desligado_nao_tem_o_que_dizer(self) -> None:
        """Desligado é o padrão (S-42), e não é falta de nada."""
        self.assertEqual("", ocr_que_falta.frase(OcrSettings(), leitor_pronto=False, congelado=True))

    def test_leitor_pronto_nao_tem_o_que_dizer(self) -> None:
        self.assertEqual("", ocr_que_falta.frase(LIGADO, leitor_pronto=True, congelado=True))

    def test_motor_desconhecido_e_nomeado_com_os_que_existem(self) -> None:
        frase = ocr_que_falta.frase(OcrSettings(enabled=True, engine="abbyy"), leitor_pronto=False, congelado=True)
        self.assertIn("'abbyy'", frase)
        self.assertIn("rapidocr", frase)
        self.assertNotIn("versão empacotada", frase, "o motor não existe em lugar nenhum, não só no .exe")

    def test_o_glifo_diz_o_motivo_que_a_configuracao_sabe(self) -> None:
        """O `glifo` é de casa e vai no executável; o que falta a ele são os pesos (S-182)."""
        ocr = OcrSettings(enabled=True, engine="glifo", glyph_model=str(Path("nao-existe") / "char.pt"))
        motivo = ocr.glyph_disabled_reason()
        self.assertTrue(motivo)
        self.assertEqual(motivo, ocr_que_falta.frase(ocr, leitor_pronto=False, congelado=True))


class AberturaTests(unittest.TestCase):
    def test_sem_falta_a_abertura_e_a_frase_de_sempre(self) -> None:
        """O serviço não é interrogado quando o OCR está desligado: o falso da janela não tem leitor."""
        frase, severidade = ocr_que_falta.frase_de_abertura(object(), OcrSettings(), congelado=True)
        self.assertEqual("Abra um livro em PDF para começar.", frase)
        self.assertEqual(estado_do_rodape.INFORMACAO, severidade)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class NaJanelaTests(unittest.TestCase):
    """O que a pessoa vê: a frase no rodapé da janela que acabou de abrir, sem livro."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def test_o_exe_sem_o_motor_diz_no_rodape_por_que_nao_ha_ocr(self) -> None:
        from chess_diagram_ocr.qt import janela as janela_mod

        with (
            _sem_rapidocr(),
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch.object(janela_mod, "load_settings", return_value=Settings(ocr=LIGADO)),
        ):
            montada = janela_mod.JanelaPrincipal(
                motor=None,
                csv_de_rotulos=self.pasta / "labels.csv",
                pasta_de_estudos=self.pasta,
                pasta_da_galeria=self.pasta,
                caminho_do_cache=self.pasta / "posicoes.sqlite",
                caminho_do_estado=self.pasta / "janela.json",
            )
        self.addCleanup(descartar, montada)
        self.assertIn("versão empacotada", montada.rodape.mensagem())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
