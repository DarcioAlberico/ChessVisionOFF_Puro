"""Em que dispositivo cada um dos dois modelos torch está, e o que a janela diz quando não há um.

O defeito que isto evita é o da S-30 em dobro: a escolha de dispositivo acontece em dois lugares
independentes (`inference.load_model` e `text.modelo._escolher_device`), e nenhum deles avisa
quando cai na CPU por o torch ser `+cpu`. Com dois modelos, eles podem até discordar entre si.

A cola é afirmável sem abrir janela, como o resto de `ui/` que não importa `tkinter`.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from chess_diagram_ocr.text import modelo
from chess_diagram_ocr.ui import dispositivos
from chess_diagram_ocr.ui import estado_do_rodape as rodape


@dataclass
class ServicoFalso:
    """O que `dispositivos_da_janela` de fato usa do `OcrService`, e nada mais."""

    device: str | None = None
    device_label: str = "cpu (torch 2.4.1)"


@dataclass
class OcrFalso:
    """`OcrSettings` reduzido à pergunta que importa aqui."""

    motivo: str = ""

    def glyph_disabled_reason(self) -> str:
        return self.motivo


class ClassificadorFalso:
    def __init__(self, device: str) -> None:
        self.device = device


class CacheDoClassificadorTests(unittest.TestCase):
    """A leitura do cache: ela responde, e **não** carrega 2,6 MB de pesos para responder."""

    def setUp(self) -> None:
        self.original = dict(modelo._CACHE)
        modelo._CACHE.clear()
        self.addCleanup(lambda: (modelo._CACHE.clear(), modelo._CACHE.update(self.original)))

    def test_sem_classificador_carregado_a_janela_nao_inventa_um_dispositivo(self) -> None:
        self.assertIsNone(modelo.dispositivo_em_uso())
        self.assertIsNone(dispositivos.descricao_do_classificador_de_caracteres())

    def test_o_dispositivo_sai_do_cache_sem_tocar_no_disco(self) -> None:
        """Se carregasse para responder, abrir a janela custaria os pesos mesmo sem OCR ligado."""

        def nao_deve_carregar(*_args: object, **_kwargs: object) -> None:  # pragma: no cover
            raise AssertionError("perguntar o dispositivo não pode carregar o modelo")

        original = modelo.carregar_classificador
        modelo.carregar_classificador = nao_deve_carregar  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(modelo, "carregar_classificador", original))

        modelo._CACHE[("a", "b", "cpu", 0, 0)] = ClassificadorFalso("cpu")  # type: ignore[assignment]
        self.assertEqual(modelo.dispositivo_em_uso(), "cpu")

    def test_o_retreino_no_meio_da_sessao_vale_mais_que_o_modelo_velho(self) -> None:
        """O cache guarda uma entrada por par de arquivos; a nova entra ao lado da velha."""
        modelo._CACHE[("a", "b", "cpu", 0, 0)] = ClassificadorFalso("cpu")  # type: ignore[assignment]
        modelo._CACHE[("a", "b", "cuda", 1, 0)] = ClassificadorFalso("cuda")  # type: ignore[assignment]
        self.assertEqual(modelo.dispositivo_em_uso(), "cuda")


class ZonaDoRodapeTests(unittest.TestCase):
    """Os três estados do classificador de caracteres, e os dois do de peças."""

    def setUp(self) -> None:
        self.original = dict(modelo._CACHE)
        modelo._CACHE.clear()
        self.addCleanup(lambda: (modelo._CACHE.clear(), modelo._CACHE.update(self.original)))

    def test_pesos_ausentes_e_motor_outro_nao_sao_ditos_com_a_mesma_palavra(self) -> None:
        """Mandar procurar um arquivo que já está na pasta é o defeito que a distinção evita."""
        sem_pesos = dispositivos.dispositivos_da_janela(
            ServicoFalso(), OcrFalso("Os pesos não estão em models/char_classifier.pt.")
        )
        desligado = dispositivos.dispositivos_da_janela(ServicoFalso(), OcrFalso(""))

        self.assertEqual(sem_pesos.ausencia, rodape.SEM_PESOS)
        self.assertEqual(desligado.ausencia, rodape.DESLIGADO)
        self.assertIn("models/char_classifier.pt", sem_pesos.motivo)
        self.assertEqual(desligado.motivo, "")

    def test_o_modelo_de_pecas_so_e_dito_depois_da_primeira_leitura(self) -> None:
        """`device` é `None` até alguém reconhecer alguma coisa, e supor "cpu" ali seria a S-30."""
        antes = dispositivos.dispositivos_da_janela(ServicoFalso(device=None), OcrFalso(""))
        depois = dispositivos.dispositivos_da_janela(
            ServicoFalso(device="cuda", device_label="cuda:0 (placa)"), OcrFalso("")
        )

        self.assertIsNone(antes.pecas)
        self.assertEqual(depois.pecas, "cuda:0 (placa)")
        self.assertIn(rodape.SEM_MODELO, rodape.descricao_dos_dispositivos(antes.pecas, None)[0])


if __name__ == "__main__":
    unittest.main()
