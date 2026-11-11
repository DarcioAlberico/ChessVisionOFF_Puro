"""O executor do Tesseract, testado sem o binário: saídas gravadas e processo falso (S-720)."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
import pytest
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.text import leitor_de_linha, tesseract

CABECALHO = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
"""Saída gravada do Tesseract 5.5 em `tsv`, com o cabeçalho que ele sempre escreve."""


def tsv(*palavras: tuple[int, str, float]) -> str:
    linhas = [CABECALHO]
    for pagina, texto, conf in palavras:
        linhas.append(f"1\t{pagina}\t0\t0\t0\t0\t0\t0\t100\t30\t-1\t\n")
        linhas.append(f"5\t{pagina}\t1\t1\t1\t1\t10\t5\t40\t20\t{conf}\t{texto}\n")
    return "".join(linhas)


class TsvTests(unittest.TestCase):
    def test_so_o_nivel_cinco_e_palavra_e_a_confianca_vira_fracao(self) -> None:
        palavras = tesseract.palavras_do_tsv(tsv((1, "White", 96.5), (1, "wins", 50.0)))
        self.assertEqual([p.texto for p in palavras], ["White", "wins"])
        self.assertAlmostEqual(palavras[0].confianca, 0.965)
        self.assertEqual(palavras[0].caixa, (10, 5, 50, 25))

    def test_linha_truncada_e_palavra_vazia_nao_derrubam(self) -> None:
        texto = CABECALHO + "5\t1\t1\t1\t1\t1\t10\t5\n" + "5\t1\t1\t1\t1\t1\t10\t5\t40\t20\t90\t \n"
        self.assertEqual(tesseract.palavras_do_tsv(texto), [])

    def test_confianca_negativa_vira_zero(self) -> None:
        self.assertEqual(tesseract.palavras_do_tsv(tsv((1, "x", -1.0)))[0].confianca, 0.0)


class ResolverBinarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.binario = self.pasta / ("tesseract.exe" if os.name == "nt" else "tesseract")
        self.binario.write_bytes(b"")

    def test_o_declarado_absoluto_vale(self) -> None:
        achado = tesseract.resolver_binario({"TESSERACT_CMD": str(self.binario), "PATH": ""}, instalado_em=())
        self.assertEqual(achado, self.binario)

    def test_o_declarado_relativo_nao_vale(self) -> None:
        self.assertIsNone(tesseract.resolver_binario({"TESSERACT_CMD": "tesseract.exe", "PATH": ""}, instalado_em=()))

    def test_o_diretorio_corrente_no_path_nao_vale(self) -> None:
        """Com nome nu o Windows procura primeiro na pasta corrente: é o que esta guarda evita."""
        atual = Path.cwd()
        os.chdir(self.pasta)
        self.addCleanup(os.chdir, atual)
        self.assertIsNone(tesseract.resolver_binario({"PATH": os.pathsep.join(["", ".", "./"])}, instalado_em=()))

    def test_o_path_absoluto_vale(self) -> None:
        self.assertEqual(tesseract.resolver_binario({"PATH": str(self.pasta)}, instalado_em=()), self.binario)

    def test_o_bundle_vence_o_resto(self) -> None:
        pasta = self.pasta / "tesseract"
        pasta.mkdir()
        dentro = pasta / self.binario.name
        dentro.write_bytes(b"")
        achado = tesseract.resolver_binario({"PATH": str(self.pasta)}, congelado_em=self.pasta, instalado_em=())
        self.assertEqual(achado, dentro)

    def test_sem_nada_e_none(self) -> None:
        self.assertIsNone(tesseract.resolver_binario({"PATH": ""}, instalado_em=()))


class VersaoTests(unittest.TestCase):
    def test_a_saida_real_de_version(self) -> None:
        self.assertEqual(tesseract.versao_de("tesseract v5.5.0.20241111\n leptonica-1.85.0\n"), "5.5.0.20241111")
        self.assertEqual(tesseract.versao_de("tesseract 4.1.1\n"), "4.1.1")
        self.assertEqual(tesseract.versao_de("outro programa"), "")

    def test_so_a_faixa_medida_passa(self) -> None:
        self.assertTrue(tesseract.versao_medida("5.5.0"))
        self.assertFalse(tesseract.versao_medida("4.1.1"))
        self.assertFalse(tesseract.versao_medida(""))

    def test_binario_de_outra_versao_nao_e_motor(self) -> None:
        falso = FabricaDeProcesso(saida=b"tesseract 4.1.1\n")
        original = subprocess.Popen
        subprocess.Popen = falso  # type: ignore[misc,assignment]
        self.addCleanup(setattr, subprocess, "Popen", original)
        motor = tesseract.examinar(Path("C:/x/tesseract.exe"))
        self.assertFalse(motor.disponivel)
        self.assertIn("4.1.1", motor.motivo)


class ProcessoFalso:
    returncode = 0

    def __init__(self, saida: bytes = b"", erro: bytes = b"", codigo: int = 0, estoura: bool = False) -> None:
        self._saida, self._erro, self.returncode, self._estoura = saida, erro, codigo, estoura
        self._handle = 0
        self.morto = False
        self.entrada: bytes | None = None

    def communicate(self, entrada: bytes | None = None, timeout: float | None = None) -> tuple[bytes, bytes]:
        self.entrada = entrada
        if self._estoura and not self.morto:
            raise subprocess.TimeoutExpired("tesseract", timeout or 0)
        return (self._saida, self._erro)

    def kill(self) -> None:
        self.morto = True


class FabricaDeProcesso:
    def __init__(self, **opcoes: Any) -> None:
        self.opcoes = opcoes
        self.comando: list[str] = []
        self.kwargs: dict[str, Any] = {}
        self.processo = ProcessoFalso(**opcoes)

    def __call__(self, comando: list[str], **kwargs: Any) -> ProcessoFalso:
        self.comando, self.kwargs = comando, kwargs
        return self.processo


MOTOR = tesseract.Motor(binario=Path("C:/x/tesseract.exe"), tessdata=Path("C:/acentuação/tessdata"), versao="5.5.0")


class RodarTests(unittest.TestCase):
    def _rodar(self, fabrica: FabricaDeProcesso) -> str:
        return tesseract.rodar(MOTOR, b"img", lingua="por", dpi=220, psm=7, timeout=5, popen=fabrica)

    def test_a_imagem_vai_pelo_stdin_e_nenhum_caminho_vai_na_linha(self) -> None:
        fabrica = FabricaDeProcesso(saida=b"ok")
        self.assertEqual(self._rodar(fabrica), "ok")
        self.assertEqual(fabrica.processo.entrada, b"img")
        self.assertEqual(fabrica.comando[1:3], ["stdin", "stdout"])
        self.assertIn("220", fabrica.comando)

    def test_o_tessdata_do_executor_sobrescreve_o_do_ambiente(self) -> None:
        ambiente = tesseract.ambiente_do_processo(MOTOR, {"TESSDATA_PREFIX": "C:/outra", "PATH": ""})
        self.assertEqual(ambiente["TESSDATA_PREFIX"], str(MOTOR.tessdata))
        self.assertEqual(ambiente["OMP_THREAD_LIMIT"], "1")

    def test_os_tres_canos_sao_explicitos_e_nao_ha_console(self) -> None:
        fabrica = FabricaDeProcesso(saida=b"")
        self._rodar(fabrica)
        for cano in ("stdin", "stdout", "stderr"):
            self.assertEqual(fabrica.kwargs[cano], subprocess.PIPE)
        if os.name == "nt":
            self.assertEqual(fabrica.kwargs["creationflags"], 0x08000000)

    def test_erro_do_processo_vira_falha_e_nao_texto_vazio(self) -> None:
        with self.assertRaisesRegex(tesseract.FalhaDoTesseract, "Failed loading language"):
            self._rodar(FabricaDeProcesso(erro=b"Failed loading language 'xxx'\n", codigo=1))

    def test_timeout_mata_o_processo(self) -> None:
        fabrica = FabricaDeProcesso(estoura=True)
        with self.assertRaisesRegex(tesseract.FalhaDoTesseract, "interrompido"):
            self._rodar(fabrica)
        self.assertTrue(fabrica.processo.morto)

    def test_binario_que_nao_abre_vira_falha(self) -> None:
        def nao_abre(*_a: Any, **_k: Any) -> Any:
            raise OSError("acesso negado")

        with self.assertRaisesRegex(tesseract.FalhaDoTesseract, "acesso negado"):
            tesseract.rodar(MOTOR, b"", lingua="eng", dpi=220, psm=7, timeout=5, popen=nao_abre)

    def test_sem_motor_vira_falha_com_o_motivo(self) -> None:
        with self.assertRaisesRegex(tesseract.FalhaDoTesseract, "não achado"):
            tesseract.rodar(tesseract.Motor(motivo="não achado"), b"", lingua="eng", dpi=220, psm=7, timeout=5)


class LerLinhasTests(unittest.TestCase):
    def test_cada_pagina_do_tiff_volta_ao_recorte_dela(self) -> None:
        recorte = np.full((20, 80), 255, dtype=np.uint8)
        vazio = np.zeros((0, 0), dtype=np.uint8)
        pedidos: list[bytes] = []

        def falso(_motor: object, imagem: bytes, **_k: object) -> str:
            pedidos.append(imagem)
            return tsv((1, "um", 90.0), (3, "tres", 80.0))

        lidas = tesseract.ler_linhas([recorte, vazio, recorte, recorte], motor=MOTOR, rodar_tesseract=falso)
        # O recorte vazio não foi lido (`None`, S-853); o terceiro foi, e veio vazio (`""`).
        self.assertEqual([None if li is None else li.texto for li in lidas], ["um", None, "", "tres"])
        assert lidas[3] is not None
        self.assertEqual(lidas[3].confiancas, (0.8,))
        self.assertEqual(len(pedidos), 1, "um processo por folha")
        self.assertTrue(pedidos[0][:2] in (b"II", b"MM"), "um TIFF")

    def test_o_tiff_tem_uma_pagina_por_recorte(self) -> None:
        from io import BytesIO

        from PIL import Image

        recortes = [np.full((20, 80 + i), 255, dtype=np.uint8) for i in range(3)]
        tiff = Image.open(BytesIO(tesseract._tiff_de(recortes)))  # noqa: SLF001
        self.assertEqual(tiff.n_frames, 3)
        m = tesseract.MARGEM_DO_RECORTE
        self.assertEqual(tiff.size, (80 + 2 * m, 20 + 2 * m))

    def test_nenhum_recorte_nao_abre_processo(self) -> None:
        def nao_pode(*_a: object, **_k: object) -> str:
            raise AssertionError("abriu processo")

        self.assertEqual(tesseract.ler_linhas([np.zeros((0, 0))], motor=MOTOR, rodar_tesseract=nao_pode), [None])

    def test_a_palavra_com_espaco_dentro_nao_desloca_as_confiancas(self) -> None:
        """U+2009 dentro de uma palavra do TSV: `split()` a parte em duas, e a confiança é uma por token (S-853)."""
        recorte = np.full((20, 80), 255, dtype=np.uint8)

        def falso(*_a: object, **_k: object) -> str:
            return tsv((1, "white knight", 90.0), (1, "wins", 20.0))

        [lida] = tesseract.ler_linhas([recorte], motor=MOTOR, rodar_tesseract=falso)
        assert lida is not None
        self.assertEqual(lida.texto.split(), ["white", "knight", "wins"])
        self.assertEqual(lida.confiancas, (0.9, 0.9, 0.2))

    def test_folha_acima_do_teto_nao_vai_ao_processo(self) -> None:
        def nao_pode(*_a: object, **_k: object) -> str:
            raise AssertionError("abriu processo")

        with self.assertRaisesRegex(tesseract.FalhaDoTesseract, "MP"):
            tesseract.ler_folha(np.zeros((8000, 8000), dtype=np.uint8), motor=MOTOR, rodar_tesseract=nao_pode)


class ContratoDoLeitorTests(unittest.TestCase):
    """`None` é "não leu"; `""` é "leu vazio". A ausência do motor nunca levanta."""

    def test_sem_motor_nao_levanta_e_diz_o_motivo(self) -> None:
        leitor = leitor_de_linha.LeitorTesseract(tesseract.Motor(motivo="não há Tesseract"))
        leitura = leitor.ler_linhas([np.zeros((9, 9), dtype=np.uint8)], lingua="eng", dpi=220)
        self.assertEqual(leitura.linhas, (None,))
        self.assertEqual(leitura.falha, "não há Tesseract")
        self.assertEqual(leitor.ler_folha(np.zeros((9, 9), dtype=np.uint8), lingua="eng", dpi=220), ([], "não há Tesseract"))

    def test_falha_do_processo_vira_none_com_a_frase(self) -> None:
        motor = tesseract.Motor(binario=Path("C:/nao/existe/tesseract.exe"), versao="5.5.0")
        leitura = leitor_de_linha.LeitorTesseract(motor).ler_linhas(
            [np.full((9, 9), 255, dtype=np.uint8)], lingua="eng", dpi=220
        )
        self.assertEqual(leitura.linhas, (None,))
        self.assertTrue(leitura.falha)


@pytest.mark.requer_tesseract
@pytest.mark.skipif(not tesseract.achar_motor().disponivel, reason="sem o binário do Tesseract")
class IntegracaoTests(unittest.TestCase):
    """Só onde há o binário: o CI pula, e a máquina do dono confere o contrato de ponta a ponta."""

    def _recorte(self, texto: str) -> np.ndarray:
        import cv2

        imagem = np.full((60, 620), 255, dtype=np.uint8)
        cv2.putText(imagem, texto, (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.1, 0, 2, cv2.LINE_AA)
        return imagem

    def test_tessdata_em_caminho_acentuado_le_de_verdade(self) -> None:
        """Esta máquina é UTF-8, e por isso **não** reproduz o defeito de uma cp1252: ver a spec da S-720."""
        import shutil
        from dataclasses import replace

        real = tesseract.achar_motor()
        assert real.tessdata is not None
        pasta = pasta_temporaria(self) / "ação çãé" / "tessdata"
        pasta.mkdir(parents=True)
        shutil.copy(real.tessdata / "eng.traineddata", pasta)
        lidas = tesseract.ler_linhas([self._recorte("White wins")], lingua="eng", motor=replace(real, tessdata=pasta))
        self.assertEqual(lidas[0].texto, "White wins")

    def test_le_linhas_de_verdade_com_um_processo_so(self) -> None:
        lidas = tesseract.ler_linhas([self._recorte("White wins"), self._recorte("the knight")], lingua="eng")
        self.assertEqual(lidas[0].texto, "White wins")
        self.assertEqual(lidas[1].texto, "the knight")



class AjustesDaS721Tests(unittest.TestCase):
    """Os três ajustes que a S-720 adiou, atrás de constante, e o `rus+eng` da S-729."""

    def _comando(self, **opcoes: object) -> list[str]:
        vistos: list[list[str]] = []

        class Processo:
            returncode = 0
            _handle = 0

            def communicate(self, *_a: object, **_k: object) -> tuple[bytes, bytes]:
                return (b"", b"")

        def popen(comando: list[str], **_k: object) -> Processo:
            vistos.append(comando)
            return Processo()

        motor = tesseract.Motor(binario=Path("C:/t/tesseract.exe"), tessdata=None, versao="5.5")
        with mock.patch.object(tesseract, "_no_trabalho"):
            tesseract.rodar(motor, b"x", dpi=220, psm=7, timeout=1.0, popen=popen, **opcoes)  # type: ignore[arg-type]
        return vistos[0]

    def test_o_russo_vai_com_o_ingles_ao_lado(self) -> None:
        self.assertIn("rus+eng", self._comando(lingua="rus"))
        with mock.patch.object(tesseract, "RUS_COM_ENG", False):
            self.assertNotIn("rus+eng", self._comando(lingua="rus"))
        self.assertIn("deu", self._comando(lingua="deu"))

    def test_as_opcoes_e_o_formato_chegam_ao_comando(self) -> None:
        comando = self._comando(lingua="eng", opcoes=("-c", "lstm_choice_mode=2"), formato="hocr")
        self.assertEqual("hocr", comando[-1])
        self.assertIn("lstm_choice_mode=2", comando)

    def test_as_palavras_do_usuario_so_entram_com_lista(self) -> None:
        self.assertNotIn("--user-words", self._comando(lingua="eng"))
        with mock.patch.object(tesseract, "PALAVRAS_DO_USUARIO", Path("C:/t/nomes.txt")):
            self.assertIn("--user-words", self._comando(lingua="eng"))

    def test_a_altura_x_mede_a_faixa_mais_cheia(self) -> None:
        linha = np.full((40, 200), 255, dtype=np.uint8)
        linha[10:24, 10:190] = 0  # corpo da letra, 14 px
        linha[4:10, 20:30] = 0  # ascendente, pouca tinta
        self.assertEqual(14.0, tesseract.altura_x(linha))

    def test_a_escala_leva_a_altura_x_ao_alvo_e_fora_dela_nao_mexe(self) -> None:
        linha = np.full((40, 200), 255, dtype=np.uint8)
        linha[10:20, 10:190] = 0
        self.assertAlmostEqual(20.0, tesseract.altura_x(tesseract.escalado(linha)) or 0, delta=2)
        no_alvo = np.full((60, 200), 255, dtype=np.uint8)
        no_alvo[10:35, 10:190] = 0
        self.assertIs(no_alvo, tesseract.escalado(no_alvo))


if __name__ == "__main__":
    unittest.main()
