"""O cache da leitura de linha: chave, despejo, disco cheio, e a régua fora dele (S-725)."""

from __future__ import annotations

import errno
import json
import os
import re
import time
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.text import bancada_prosa, cache_texto, leitor_de_linha, tesseract
from chess_diagram_ocr.text.cache_texto import CacheDeLeitura, chave_de
from chess_diagram_ocr.text.tesseract import LinhaDoTesseract

RAIZ = Path(__file__).resolve().parents[1]


def _recortes(semente: int = 1, n: int = 2) -> list[np.ndarray]:
    gerador = np.random.default_rng(semente)
    return [gerador.integers(0, 255, (20, 80), dtype=np.uint8) for _ in range(n)]


class _ComMotor(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.tessdata = self.pasta / "tessdata"
        self.tessdata.mkdir()
        for lingua in ("eng", "por", "rus"):
            (self.tessdata / f"{lingua}.traineddata").write_bytes(lingua.encode() * 100)
        self.motor = tesseract.Motor(binario=self.pasta / "tesseract.exe", tessdata=self.tessdata, versao="5.5.0")

    def chave(self, **campos: Any) -> cache_texto.ChaveDaLeitura:
        pedido: dict[str, Any] = {"motor": self.motor, "lingua": "eng", "dpi": 220, "psm": 7}
        recortes = campos.pop("recortes", None) or _recortes()
        pedido.update(campos)
        return chave_de(recortes, **pedido)


class AChaveTests(_ComMotor):
    """Trocar o que muda a leitura invalida a entrada. É a verificação do item."""

    def test_a_mesma_leitura_da_a_mesma_chave(self) -> None:
        self.assertEqual(self.chave().nome, self.chave().nome)

    def test_cada_componente_muda_a_chave(self) -> None:
        base = self.chave().nome
        casos: dict[str, dict[str, Any]] = {
            "recorte": {"recortes": _recortes(semente=2)},
            "língua": {"lingua": "por"},
            "psm": {"psm": 6},
            "dpi": {"dpi": 300},
            "modelo": {"modelo": "abc"},
            "opções": {"opcoes": ("-c", "load_system_dawg=0")},
            "versão do Tesseract": {"motor": tesseract.Motor(self.motor.binario, self.tessdata, "5.6.0")},
        }
        for nome, campos in casos.items():
            with self.subTest(nome):
                self.assertNotEqual(self.chave(**campos).nome, base)

    def test_a_ordem_dos_recortes_muda_a_chave(self) -> None:
        um, dois = _recortes()
        self.assertNotEqual(self.chave(recortes=[um, dois]).nome, self.chave(recortes=[dois, um]).nome)

    def test_a_forma_do_recorte_muda_a_chave(self) -> None:
        cheio = np.zeros((20, 80), dtype=np.uint8)
        self.assertNotEqual(self.chave(recortes=[cheio]).nome, self.chave(recortes=[cheio.reshape(40, 40)]).nome)

    def test_trocar_o_tessdata_invalida(self) -> None:
        antes = self.chave().nome
        alvo = self.tessdata / "eng.traineddata"
        alvo.write_bytes(b"outro modelo" * 100)
        os.utime(alvo, ns=(time.time_ns(), time.time_ns() + 1000))
        self.assertNotEqual(self.chave().nome, antes)

    def test_o_russo_depende_dos_dois_tessdata(self) -> None:
        """`rus` vai ao processo como `rus+eng` (S-729): trocar o `eng` muda a leitura do russo."""
        antes = self.chave(lingua="rus").nome
        alvo = self.tessdata / "eng.traineddata"
        alvo.write_bytes(b"outro modelo" * 100)
        os.utime(alvo, ns=(time.time_ns(), time.time_ns() + 1000))
        self.assertNotEqual(self.chave(lingua="rus").nome, antes)

    def test_a_versao_do_executor_e_o_preprocessamento_invalidam(self) -> None:
        base = self.chave().nome
        with mock.patch.object(tesseract, "VERSAO_DO_EXECUTOR", tesseract.VERSAO_DO_EXECUTOR + 1):
            self.assertNotEqual(self.chave().nome, base)
        with mock.patch.object(tesseract, "MARGEM_DO_RECORTE", tesseract.MARGEM_DO_RECORTE + 1):
            self.assertNotEqual(self.chave().nome, base)
        with mock.patch.object(tesseract, "ESCALA_PELA_ALTURA_X", not tesseract.ESCALA_PELA_ALTURA_X):
            self.assertNotEqual(self.chave().nome, base)

    def test_a_entrada_de_outra_chave_nao_responde(self) -> None:
        cache = CacheDeLeitura(self.pasta / "c")
        cache.gravar(self.chave(), [LinhaDoTesseract("a")])
        self.assertIsNone(cache.ler(self.chave(lingua="por")))


class OCacheTests(_ComMotor):
    def setUp(self) -> None:
        super().setUp()
        self.cache = CacheDeLeitura(self.pasta / "cache")

    def test_ida_e_volta_igual(self) -> None:
        linhas = [LinhaDoTesseract("the white", (0.97, 0.31)), LinhaDoTesseract("")]
        self.cache.gravar(self.chave(), linhas)
        self.assertEqual(self.cache.ler(self.chave()), linhas)

    def test_sem_entrada_e_falta(self) -> None:
        self.assertIsNone(self.cache.ler(self.chave()))

    def test_entrada_estragada_e_falta_e_sai_da_pasta(self) -> None:
        chave = self.chave()
        self.cache.gravar(chave, [LinhaDoTesseract("a")])
        caminho = next((self.pasta / "cache").glob("??/*.json"))
        caminho.write_text("{ isto não é json", encoding="utf-8")
        self.assertIsNone(self.cache.ler(chave))
        self.assertFalse(caminho.exists())

    def test_a_gravacao_nao_deixa_temporario(self) -> None:
        self.cache.gravar(self.chave(), [LinhaDoTesseract("a")])
        arquivos = [p for p in (self.pasta / "cache").rglob("*") if p.is_file()]
        self.assertEqual(len(arquivos), 1)
        self.assertEqual(arquivos[0].suffix, ".json")

    def test_a_gravacao_passa_pelo_atomic_io(self) -> None:
        with mock.patch.object(cache_texto, "atomic_write_text") as gravar:
            self.cache.gravar(self.chave(), [LinhaDoTesseract("a")])
        gravar.assert_called_once()

    def test_disco_cheio_vira_frase_e_nao_excecao(self) -> None:
        with mock.patch.object(cache_texto, "atomic_write_text", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            frase = self.cache.gravar(self.chave(), [LinhaDoTesseract("a")])
        self.assertIn("disco está cheio", frase)
        self.assertIn("não se perdeu", frase)

    def test_limpar_apaga_as_entradas_e_so_elas(self) -> None:
        self.cache.gravar(self.chave(), [LinhaDoTesseract("a")])
        self.cache.gravar(self.chave(lingua="por"), [LinhaDoTesseract("b")])
        alheio = self.pasta / "cache" / "nao_e_do_cache.txt"
        alheio.write_text("fica", encoding="utf-8")
        quantas, tamanho = self.cache.limpar()
        self.assertEqual(quantas, 2)
        self.assertGreater(tamanho, 0)
        self.assertEqual(self.cache.tamanho(), 0)
        self.assertTrue(alheio.exists())
        self.assertEqual(self.cache.limpar(), (0, 0))

    def test_limpar_sem_pasta_nao_levanta(self) -> None:
        self.assertEqual(CacheDeLeitura(self.pasta / "nao_existe").limpar(), (0, 0))


class ODespejoTests(_ComMotor):
    def _lote(self, n: int) -> list[LinhaDoTesseract]:
        return [LinhaDoTesseract(f"linha {n} " + "x" * 2000)]

    def _envelhecer(self, chave: cache_texto.ChaveDaLeitura, cache: CacheDeLeitura, segundos: int) -> None:
        caminho = cache._caminho(chave)  # noqa: SLF001
        agora = time.time() - segundos
        os.utime(caminho, (agora, agora))

    def test_o_teto_e_cumprido_e_sai_quem_foi_usado_ha_mais_tempo(self) -> None:
        cache = CacheDeLeitura(self.pasta / "c", teto_mb=9_000 / (1024 * 1024))
        chaves = [self.chave(recortes=_recortes(semente=n)) for n in range(4)]
        for n, chave in enumerate(chaves[:3]):
            cache.gravar(chave, self._lote(n))
            self._envelhecer(chave, cache, 1000 - n)
        # A mais antiga é lida agora: é ela que deixa de ser a primeira a sair. LRU, e não FIFO.
        self.assertIsNotNone(cache.ler(chaves[0]))
        cache.gravar(chaves[3], self._lote(3))
        self.assertLessEqual(cache.tamanho(), cache.teto)
        self.assertIsNotNone(cache.ler(chaves[0]), "a usada agora fica")
        self.assertIsNone(cache.ler(chaves[1]), "a usada há mais tempo sai")
        self.assertIsNotNone(cache.ler(chaves[3]), "a recém-gravada fica")

    def test_a_conta_sobrevive_a_um_programa_novo(self) -> None:
        """A primeira gravação de um processo mede a pasta, e não começa do zero."""
        teto = 5_000 / (1024 * 1024)
        primeiro = CacheDeLeitura(self.pasta / "c", teto_mb=1)
        for n in range(4):
            primeiro.gravar(self.chave(recortes=_recortes(semente=n)), self._lote(n))
        segundo = CacheDeLeitura(self.pasta / "c", teto_mb=teto)
        segundo.gravar(self.chave(recortes=_recortes(semente=9)), self._lote(9))
        self.assertLessEqual(segundo.tamanho(), segundo.teto)

    def test_despejar_com_arquivo_preso_nao_levanta(self) -> None:
        cache = CacheDeLeitura(self.pasta / "c", teto_mb=1_000 / (1024 * 1024))
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("preso")):
            self.assertEqual(cache.gravar(self.chave(), self._lote(1)), "")


class _Rodar:
    """Conta os processos: é o que diz se a leitura veio do cache."""

    def __init__(self) -> None:
        self.vezes = 0

    def __call__(self, recortes: Sequence[np.ndarray], **_: Any) -> list[LinhaDoTesseract]:
        self.vezes += 1
        return [LinhaDoTesseract(f"linha {k}", (0.9, 0.8)) for k in range(len(recortes))]


class OLeitorTests(_ComMotor):
    def setUp(self) -> None:
        super().setUp()
        self.rodar = _Rodar()
        trocado = mock.patch.object(tesseract, "ler_linhas", self.rodar)
        trocado.start()
        self.addCleanup(trocado.stop)
        self.cache = CacheDeLeitura(self.pasta / "c")

    def test_a_segunda_leitura_nao_abre_processo_e_devolve_o_mesmo(self) -> None:
        leitor = leitor_de_linha.LeitorTesseract(self.motor, cache=self.cache)
        primeira = leitor.ler_linhas(_recortes(), lingua="eng", dpi=220)
        segunda = leitor.ler_linhas(_recortes(), lingua="eng", dpi=220)
        self.assertEqual(self.rodar.vezes, 1)
        self.assertEqual(primeira.linhas, segunda.linhas)
        self.assertEqual(primeira.falha, "")

    def test_sem_cache_toda_leitura_abre_processo(self) -> None:
        leitor = leitor_de_linha.LeitorTesseract(self.motor)
        leitor.ler_linhas(_recortes(), lingua="eng", dpi=220)
        leitor.ler_linhas(_recortes(), lingua="eng", dpi=220)
        self.assertEqual(self.rodar.vezes, 2)

    def test_a_outra_lingua_le_de_novo(self) -> None:
        leitor = leitor_de_linha.LeitorTesseract(self.motor, cache=self.cache)
        leitor.ler_linhas(_recortes(), lingua="eng", dpi=220)
        leitor.ler_linhas(_recortes(), lingua="por", dpi=220)
        self.assertEqual(self.rodar.vezes, 2)

    def test_o_que_falhou_nao_vai_ao_cache(self) -> None:
        leitor = leitor_de_linha.LeitorTesseract(self.motor, cache=self.cache)
        with mock.patch.object(tesseract, "ler_linhas", side_effect=tesseract.FalhaDoTesseract("travou")):
            falha = leitor.ler_linhas(_recortes(), lingua="eng", dpi=220)
        self.assertEqual(falha.falha, "travou")
        self.assertEqual(self.cache.tamanho(), 0)

    def test_disco_cheio_devolve_a_leitura_com_o_aviso(self) -> None:
        leitor = leitor_de_linha.LeitorTesseract(self.motor, cache=self.cache)
        with mock.patch.object(cache_texto, "atomic_write_text", side_effect=OSError(errno.ENOSPC, "cheio")):
            lida = leitor.ler_linhas(_recortes(), lingua="eng", dpi=220)
        self.assertEqual(lida.falha, "")
        self.assertEqual([li.texto for li in lida.linhas if li is not None], ["linha 0", "linha 1"])
        self.assertIn("disco está cheio", lida.aviso)

    def test_sem_tessdata_conhecido_nao_ha_cache(self) -> None:
        """Binário do `PATH` sem a pasta ao lado: quem escolhe os pesos é o `TESSDATA_PREFIX`, que a chave não vê."""
        sem_pasta = tesseract.Motor(binario=self.motor.binario, tessdata=None, versao="5.5.0")
        leitor = leitor_de_linha.LeitorTesseract(sem_pasta, cache=self.cache)
        with mock.patch.dict(os.environ, {"TESSDATA_PREFIX": "pesos_um"}):
            leitor.ler_linhas(_recortes(), lingua="eng", dpi=220)
        with mock.patch.dict(os.environ, {"TESSDATA_PREFIX": "pesos_dois"}):
            lida = leitor.ler_linhas(_recortes(), lingua="eng", dpi=220)
        self.assertEqual(self.rodar.vezes, 2, "a segunda leitura respondeu com os pesos da primeira")
        self.assertEqual(self.cache.tamanho(), 0)
        self.assertEqual(lida.aviso, "")

    def test_motor_ausente_nao_toca_no_cache(self) -> None:
        leitor = leitor_de_linha.LeitorTesseract(tesseract.Motor(motivo="sem"), cache=self.cache)
        self.assertEqual(leitor.ler_linhas(_recortes(), lingua="eng", dpi=220).falha, "sem")
        self.assertEqual(self.cache.tamanho(), 0)


class AReguaFicaDeForaTests(unittest.TestCase):
    """**Uma medição que responde do disco mede a leitura de outro dia.**"""

    def test_o_leitor_nasce_sem_cache(self) -> None:
        self.assertIsNone(leitor_de_linha.LeitorTesseract()._cache)  # noqa: SLF001
        self.assertIsNone(leitor_de_linha.leitor_padrao()._cache)  # type: ignore[attr-defined]  # noqa: SLF001

    def test_a_bancada_nao_liga(self) -> None:
        folha = mock.Mock(leitor_de_linha=None)
        self.assertIsNone(bancada_prosa._leitor_da_folha(folha)._cache)  # noqa: SLF001

    def test_so_a_janela_liga(self) -> None:
        """A varredura do pacote: quem cita `cache_texto` é o leitor, que recebe, e a aba, que liga."""
        pacote = RAIZ / "src" / "chess_diagram_ocr"
        quem = {
            str(p.relative_to(pacote)).replace("\\", "/")
            for p in pacote.rglob("*.py")
            if p.name != "cache_texto.py" and re.search(r"\bcache_texto\b", p.read_text(encoding="utf-8"))
        }
        self.assertEqual(quem, {"qt/painel_de_texto.py", "text/leitor_de_linha.py"})

    def test_data_cache_texto_nao_vai_ao_git(self) -> None:
        self.assertIn("data/cache_texto/", (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines())


class OLoteTests(unittest.TestCase):
    """Um processo por folha é o que a S-720 entrega, e a leitura por linha fica como reserva atrás de constante."""

    MOTOR = tesseract.Motor(binario=Path("tesseract.exe"), versao="5.5.0")

    def _tsv(self, *por_pagina: str) -> str:
        cabecalho = "level\tpage\tblock\tpar\tline\tword\tleft\ttop\twidth\theight\tconf\ttext\n"
        return cabecalho + "".join(f"5\t{k}\t1\t1\t1\t1\t0\t0\t9\t9\t90\t{t}\n" for k, t in enumerate(por_pagina, start=1))

    def test_o_lote_abre_um_processo_com_um_tiff_de_varias_paginas(self) -> None:
        from io import BytesIO

        from PIL import Image

        chamadas: list[tuple[bytes, int]] = []

        def rodar(_motor: object, imagem: bytes, *, psm: int, **_: Any) -> str:
            chamadas.append((imagem, psm))
            return self._tsv("a", "b", "c")

        lidas = tesseract.ler_linhas(_recortes(n=3), motor=self.MOTOR, rodar_tesseract=rodar)
        self.assertEqual([li.texto for li in lidas], ["a", "b", "c"])
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0][1], tesseract.PSM_DA_LINHA)
        self.assertEqual(Image.open(BytesIO(chamadas[0][0])).n_frames, 3)

    def test_a_reserva_abre_um_processo_por_linha(self) -> None:
        textos = iter("abc")

        def rodar(_motor: object, _imagem: bytes, **_: Any) -> str:
            return self._tsv(next(textos))

        with mock.patch.object(tesseract, "LOTE_POR_FOLHA", False):
            lidas = tesseract.ler_linhas(_recortes(n=3), motor=self.MOTOR, rodar_tesseract=rodar)
        self.assertEqual([li.texto for li in lidas], ["a", "b", "c"])
        self.assertEqual([li.palavras[0].pagina for li in lidas], [1, 1, 1])

    def test_a_reserva_mantem_o_recorte_vazio_no_lugar(self) -> None:
        textos = iter("ab")
        vazio = np.zeros((0, 0), dtype=np.uint8)

        def rodar(_motor: object, _imagem: bytes, **_: Any) -> str:
            return self._tsv(next(textos))

        um, dois = _recortes()
        with mock.patch.object(tesseract, "LOTE_POR_FOLHA", False):
            lidas = tesseract.ler_linhas([um, vazio, dois], motor=self.MOTOR, rodar_tesseract=rodar)
        self.assertEqual([li.texto for li in lidas], ["a", "", "b"])


class OAvisoDeCacheTests(unittest.TestCase):
    def test_o_aviso_de_cache_nao_vai_ao_arquivo(self) -> None:
        """É da sessão: uma folha inteira não pode passar a dizer, para sempre, que o disco esteve cheio um dia."""
        from chess_diagram_ocr.text import pagina

        lida = pagina.PaginaLida(avisos=(pagina.Aviso(pagina.CACHE_NAO_GRAVADO, "cheio"),))
        dados = json.loads(json.dumps(lida.para_json()))
        self.assertEqual(dados["esquema"], 1)
        self.assertNotIn("avisos", dados)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
