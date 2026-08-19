"""PNG sob nome que a code page ANSI não representa.

O acervo tem um livro russo, e a varredura dele morria sempre no mesmo lugar:

    O OpenCV não conseguiu gravar
    data/review_cache/_Болеславский_И_Избранные_партии/p00006_d1.png.
    Verifique espaço em disco, permissão de escrita e se a pasta existe.

As três coisas que a mensagem mandava conferir estavam em ordem -- a pasta, inclusive, tinha
acabado de ser criada pela mesma função duas linhas acima. O que falhava era outra coisa:
`cv2.imwrite` recebe o caminho como `std::string` e o repassa ao `fopen` estreito do CRT, que
o converte pela code page ANSI do processo (cp1252 numa máquina brasileira). Cirílico não
existe em cp1252, o `fopen` falha, o `imwrite` devolve `False`. O `mkdir` do Python não sofria
disso porque a `pathlib` usa a API wide do Windows.

`cv2.imread` sofre da mesma conversão, com um agravante: devolve `None`, o mesmo valor que
significa "arquivo não existe". A miniatura teria voltado em branco, sem erro nenhum na tela.

Estes testes passariam sozinhos no Linux, onde a locale é UTF-8 e o `imwrite` nunca teve o
problema. É de propósito -- eles guardam o comportamento, não o defeito.

A guarda da S-111 (`write_image` confere o retorno em vez de seguir adiante) continua aqui,
agora sobre as duas falhas que restaram: a codificação recusada e a escrita que não foi ao
disco. Foi ela que transformou este defeito num diálogo de erro em vez de um PNG faltando.
"""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

import numpy as np

from chess_diagram_ocr.atomic_io import read_image, write_image

CIRILICO = "_Болеславский_И_Избранные_партии"
"""O nome exato que quebrava, tirado de `data/review_cache/`."""

NOMES_DIFICEIS = (
    CIRILICO,
    "Δοκιμή",  # grego, também fora da cp1252
    "棋譜",  # japonês, fora de qualquer code page de byte único ocidental
    "400 Quebra-cabeças de Estratégia",  # esse sempre funcionou: cabe na cp1252
)


def _tabuleiro() -> np.ndarray:
    imagem = np.zeros((16, 16, 3), dtype=np.uint8)
    imagem[4:12, 4:12] = (30, 90, 200)  # algo assimétrico, para o round-trip provar conteúdo
    return imagem


class CaminhoForaDaCodePageTests(unittest.TestCase):
    def test_grava_e_le_de_volta_sob_nome_cirilico(self) -> None:
        original = _tabuleiro()
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / CIRILICO / "p00006_d1.png"

            gravado = write_image(destino, original)

            self.assertTrue(gravado.exists())
            self.assertGreater(gravado.stat().st_size, 0)
            np.testing.assert_array_equal(read_image(gravado), original)

    def test_todos_os_alfabetos_que_o_acervo_alcanca(self) -> None:
        original = _tabuleiro()
        for nome in NOMES_DIFICEIS:
            with self.subTest(nome=nome), tempfile.TemporaryDirectory() as tmp:
                destino = Path(tmp) / nome / "p00001_d0.png"
                write_image(destino, original)
                np.testing.assert_array_equal(read_image(destino), original)

    def test_a_pasta_e_criada_quando_nao_existe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / CIRILICO / "sub" / "p00001_d0.png"
            write_image(destino, _tabuleiro())
            self.assertTrue(destino.parent.is_dir())


class LeituraTests(unittest.TestCase):
    """`read_image` devolve `None` onde o `imread` devolvia -- os sete pontos de chamada
    mantiveram o tratamento que já tinham."""

    def test_arquivo_que_nao_existe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_image(Path(tmp) / "nao_existe.png"))

    def test_arquivo_vazio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vazio = Path(tmp) / "vazio.png"
            vazio.touch()
            self.assertIsNone(read_image(vazio))

    def test_arquivo_que_nao_e_imagem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lixo = Path(tmp) / "lixo.png"
            lixo.write_bytes(b"isto aqui e um CSV, nao um PNG\n")
            self.assertIsNone(read_image(lixo))

    def test_diretorio_no_lugar_do_arquivo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_image(Path(tmp)))

    def test_aceita_caminho_em_texto(self) -> None:
        """`app_tkinter._ocr_local` passa o `str` que o diálogo de arquivo devolveu."""
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / CIRILICO / "escolhido.png"
            write_image(destino, _tabuleiro())
            self.assertIsNotNone(read_image(str(destino)))

    def test_devolve_sempre_tres_canais(self) -> None:
        """Paridade com o `IMREAD_COLOR` que era o padrão do `imread`: quem chama faz
        `cvtColor(..., COLOR_BGR2RGB)` na sequência e um PNG em escala de cinza quebraria."""
        with tempfile.TemporaryDirectory() as tmp:
            import cv2

            cinza = Path(tmp) / "cinza.png"
            _, buffer = cv2.imencode(".png", np.full((16, 16), 128, dtype=np.uint8))
            cinza.write_bytes(buffer.tobytes())

            lido = read_image(cinza)
            self.assertIsNotNone(lido)
            self.assertEqual(lido.shape, (16, 16, 3))


class EscritaTests(unittest.TestCase):
    def test_extensao_sem_codec_levanta_oserror(self) -> None:
        """O `imencode` levanta `cv2.error` aqui; quem chama trata `OSError`."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(OSError) as ctx:
                write_image(Path(tmp) / "board.xyz", _tabuleiro())
            self.assertIn("codificar", str(ctx.exception))

    def test_falha_de_disco_levanta_com_o_caminho_na_mensagem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / CIRILICO / "p00006_d1.png"
            with unittest.mock.patch.object(Path, "write_bytes", side_effect=OSError("disco cheio")):
                with self.assertRaises(OSError) as ctx:
                    write_image(destino, _tabuleiro())

            mensagem = str(ctx.exception)
            self.assertIn("p00006_d1.png", mensagem)
            self.assertIn("disco cheio", mensagem)


if __name__ == "__main__":
    unittest.main()
