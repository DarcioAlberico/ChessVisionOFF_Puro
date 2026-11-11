"""O que `atomic_io` promete a quem grava, conferido pelo comportamento (S-873).

`tests/test_atomic_writes.py` é a guarda de arquitetura -- ninguém grava fora deste módulo -- e
`tests/test_image_io.py` cobre o caminho não-ASCII das imagens. O mutator da S-803 achou o que
nenhum dos dois conferia: quantas vezes a troca insiste e quanto espera, a frase inteira que a
pessoa lê quando o arquivo está preso, o nome do temporário, o JSON gravado, e a leitura do
tabuleiro em RGB. As frases são conferidas inteiras porque são o que chega à tela.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import IO
from unittest import mock

import numpy as np

import chess_diagram_ocr.atomic_io as io_mod
from chess_diagram_ocr.atomic_io import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_stream,
    read_board_image,
    write_image,
)


class TrocaPresaTests(unittest.TestCase):
    """O `os.replace` que o Windows recusa enquanto outro programa segura o arquivo (S-373)."""

    def setUp(self) -> None:
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.alvo = Path(pasta.name) / "labels.csv"
        self.alvo.write_bytes(b"antigo\n")

    def test_insiste_cinco_vezes_e_espera_cada_vez_mais_entre_elas(self) -> None:
        """Quatro esperas crescentes entre cinco tentativas, e nenhuma depois da última: o
        antivírus solta em milissegundos, e esperar depois de desistir só atrasa o recado."""
        with (
            mock.patch.object(io_mod.os, "replace", side_effect=PermissionError(5, "Acesso negado")) as troca,
            mock.patch.object(io_mod.time, "sleep") as dormir,
            self.assertRaises(PermissionError),
        ):
            atomic_write_bytes(self.alvo, b"novo\n")

        self.assertEqual(troca.call_count, 5)
        self.assertEqual([chamada.args[0] for chamada in dormir.call_args_list], [0.08, 0.16, 0.24, 0.32])

    def test_a_frase_inteira_que_a_pessoa_le(self) -> None:
        with (
            mock.patch.object(io_mod.os, "replace", side_effect=PermissionError(5, "Acesso negado")),
            mock.patch.object(io_mod.time, "sleep"),
            mock.patch.object(io_mod, "ESPERA_ENTRE_TROCAS", 0.07),
            self.assertRaises(PermissionError) as capturado,
        ):
            atomic_write_bytes(self.alvo, b"novo\n")

        self.assertEqual(
            str(capturado.exception),
            f"Não foi possível gravar {self.alvo}: o sistema recusou substituir o arquivo por 0.7 s seguidos. "
            "No Windows isso quer dizer que ele está aberto em outro programa -- o Excel e o Bloco de Notas "
            "seguram o arquivo enquanto a janela estiver aberta. Feche-o e repita a operação; o arquivo "
            "anterior continua intacto e nada foi gravado pela metade. Detalhe do sistema: [Errno 5] Acesso negado",
        )
        self.assertEqual(self.alvo.read_bytes(), b"antigo\n")


class TemporarioVizinhoTests(unittest.TestCase):
    def setUp(self) -> None:
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def test_o_temporario_e_oculto_e_termina_em_tmp(self) -> None:
        """Enquanto grava, o vizinho é `.<nome>.<sorteio>.tmp`: oculto, reconhecível como
        temporário, e fora de qualquer `*.csv` ou `*.json` que alguém varra na pasta."""
        vistos: list[str] = []

        def escrever(fluxo: IO[bytes]) -> None:
            vistos.extend(p.name for p in self.pasta.iterdir())
            fluxo.write(b"x")

        atomic_write_stream(self.pasta / "labels.csv", escrever)

        self.assertEqual(len(vistos), 1, vistos)
        self.assertRegex(vistos[0], r"^\.labels\.csv\.[^.]+\.tmp$")

    def test_cria_as_pastas_que_faltam(self) -> None:
        destino = self.pasta / "a" / "b" / "estado.json"
        atomic_write_bytes(destino, b"{}")
        self.assertEqual(destino.read_bytes(), b"{}")

    def test_o_erro_do_gravador_chega_inteiro_mesmo_sem_o_temporario(self) -> None:
        """Uma biblioteca que apaga o próprio arquivo antes de cair não pode trocar o erro dela
        por um `FileNotFoundError` do nosso lado: o erro que a pessoa vê é o que aconteceu."""

        def apaga_e_cai(fluxo: IO[bytes]) -> None:
            fluxo.close()
            Path(fluxo.name).unlink()
            raise RuntimeError("o exportador caiu")

        with self.assertRaisesRegex(RuntimeError, "^o exportador caiu$"):
            atomic_write_stream(self.pasta / "m.onnx", apaga_e_cai)
        self.assertEqual(list(self.pasta.iterdir()), [])


class JsonTests(unittest.TestCase):
    def test_utf8_legivel_indentado_e_com_quebra_no_fim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "estado.json"
            atomic_write_json(destino, {"livro": "Peões"})
            self.assertEqual(destino.read_bytes(), '{\n  "livro": "Peões"\n}\n'.encode())


def _imagem() -> np.ndarray:
    imagem = np.zeros((8, 8, 3), dtype=np.uint8)
    imagem[..., 0] = 255  # azul em BGR
    return imagem


class ImagemTests(unittest.TestCase):
    def setUp(self) -> None:
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def test_duas_imagens_na_mesma_pasta_nova(self) -> None:
        primeira = write_image(self.pasta / "livro" / "p1" / "d0.png", _imagem())
        segunda = write_image(self.pasta / "livro" / "p1" / "d1.png", _imagem())
        self.assertEqual(sorted(p.name for p in primeira.parent.iterdir()), ["d0.png", "d1.png"])
        self.assertEqual(segunda, self.pasta / "livro" / "p1" / "d1.png")

    def test_as_frases_de_quando_a_imagem_nao_grava(self) -> None:
        destino = self.pasta / "d0.png"
        with self.assertRaises(OSError) as sem_codec:
            write_image(self.pasta / "d0.xyz", _imagem())
        self.assertEqual(
            str(sem_codec.exception), f"O OpenCV não sabe codificar '.xyz' para gravar {self.pasta / 'd0.xyz'}."
        )

        with mock.patch("cv2.imencode", return_value=(False, None)), self.assertRaises(OSError) as recusada:
            write_image(destino, _imagem())
        self.assertEqual(str(recusada.exception), f"O OpenCV não conseguiu codificar a imagem de {destino}.")

        with (
            mock.patch.object(io_mod, "atomic_write_bytes", side_effect=OSError("disco cheio")),
            self.assertRaises(OSError) as disco,
        ):
            write_image(destino, _imagem())
        self.assertEqual(
            str(disco.exception),
            f"Não foi possível gravar {destino}: disco cheio. Verifique espaço em disco e permissão de escrita.",
        )

    def test_o_tabuleiro_volta_em_rgb(self) -> None:
        destino = write_image(self.pasta / "d0.png", _imagem())
        lido = read_board_image(destino)
        assert lido is not None
        self.assertEqual(lido[0, 0].tolist(), [0, 0, 255])

    def test_o_tabuleiro_que_nao_esta_la_ou_nao_decodifica_e_none(self) -> None:
        estragado = self.pasta / "estragado.png"
        estragado.write_bytes(b"isto nao e um png")
        self.assertIsNone(read_board_image(self.pasta / "sumiu.png"))
        self.assertIsNone(read_board_image(estragado))


if __name__ == "__main__":
    unittest.main()
