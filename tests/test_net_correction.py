"""Cliente do "Corrigir Net" (S-31/S-32).

Os quatro modos de falha de um cliente HTTP moravam dentro da janela do Tkinter, onde
testá-los exigia abrir uma janela -- então nenhum deles tinha teste. As mensagens em pt-BR
que a interface mostra ao usuário são o contrato aqui, e é isso que se verifica.

Nenhum teste toca a rede: o *opener* do módulo é substituído. Ele é um objeto próprio desde
a S-59 -- `urllib.request.urlopen` segue redirect por padrão, e seguir um manda a imagem do
tabuleiro para um host que o consentimento da S-32 nunca nomeou. Substituir o alvo errado faz
estes testes saírem para a rede de verdade em vez de falharem, e é o que
`test_o_envio_nao_passa_por_urlopen` trava.
"""

from __future__ import annotations

import io
import unittest
import urllib.error
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

import cv2
import numpy as np

from chess_diagram_ocr import net_correction
from chess_diagram_ocr.net_correction import (
    encode_multipart_png,
    parse_net_response,
    predict_fen_via_net,
)

FEN = "8/8/8/8/8/8/8/K6k"
ENDPOINT = "https://exemplo.invalido/predict"


def _board() -> np.ndarray:
    return np.random.default_rng(0).integers(0, 256, (64, 64, 3), dtype=np.uint8)


@contextmanager
def _responding(payload: str) -> Any:
    class _Response:
        def read(self) -> bytes:
            return payload.encode("utf-8")

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    with mock.patch.object(net_correction._OPENER, "open", return_value=_Response()) as chamada:
        yield chamada


class EncodeTests(unittest.TestCase):
    def test_the_body_carries_a_readable_png_of_the_board(self) -> None:
        board = _board()
        body, content_type = encode_multipart_png(board)

        self.assertIn("multipart/form-data; boundary=", content_type)
        inicio = body.index(b"\r\n\r\n") + 4
        fim = body.rindex(b"\r\n--")
        decodificada = cv2.imdecode(np.frombuffer(body[inicio:fim], dtype=np.uint8), cv2.IMREAD_COLOR)

        self.assertIsNotNone(decodificada)
        # A imagem vai em RGB e o PNG e gravado em BGR: converter de volta tem de reproduzir
        # o original. Trocar os canais aqui entregaria pecas brancas como pretas.
        np.testing.assert_array_equal(cv2.cvtColor(decodificada, cv2.COLOR_BGR2RGB), board)

    def test_the_boundary_in_the_header_is_the_one_used_in_the_body(self) -> None:
        body, content_type = encode_multipart_png(_board())
        boundary = content_type.split("boundary=")[1]
        self.assertTrue(body.startswith(f"--{boundary}\r\n".encode("ascii")))
        self.assertTrue(body.endswith(f"--{boundary}--\r\n".encode("ascii")))

    def test_an_empty_image_is_refused_before_any_request(self) -> None:
        with self.assertRaises(ValueError):
            encode_multipart_png(np.zeros((0, 0, 3), dtype=np.uint8))


class ParseTests(unittest.TestCase):
    def test_a_well_formed_response_yields_the_fen(self) -> None:
        self.assertEqual(parse_net_response(f'{{"results": [{{"fen": "{FEN}"}}]}}'), FEN)

    def test_a_body_that_is_not_json_says_so(self) -> None:
        with self.assertRaises(RuntimeError) as capturado:
            parse_net_response("<html>502 Bad Gateway</html>")
        self.assertIn("JSON", str(capturado.exception))

    def test_the_api_message_wins_over_a_generic_one(self) -> None:
        """Quando o serviço explica a recusa, repetir a explicação vale mais que ocultá-la."""
        with self.assertRaises(RuntimeError) as capturado:
            parse_net_response('{"message": "cota diaria excedida"}')
        self.assertIn("cota diaria excedida", str(capturado.exception))

    def test_an_empty_results_list_is_a_failure_not_an_empty_fen(self) -> None:
        with self.assertRaises(RuntimeError):
            parse_net_response('{"results": []}')

    def test_a_result_without_a_fen_is_a_failure(self) -> None:
        with self.assertRaises(RuntimeError) as capturado:
            parse_net_response('{"results": [{"fen": "   "}]}')
        self.assertIn("vazia", str(capturado.exception))


class RequestTests(unittest.TestCase):
    def test_the_fen_comes_back_from_a_successful_call(self) -> None:
        with _responding(f'{{"results": [{{"fen": "{FEN}"}}]}}') as chamada:
            self.assertEqual(predict_fen_via_net(_board(), url=ENDPOINT), FEN)

        pedido = chamada.call_args.args[0]
        self.assertEqual(pedido.full_url, ENDPOINT)
        self.assertEqual(pedido.method, "POST")

    def test_the_destination_is_always_the_one_that_was_asked_for(self) -> None:
        """A S-32 exige endpoint declarado; o cliente nao tem destino proprio."""
        with _responding(f'{{"results": [{{"fen": "{FEN}"}}]}}') as chamada:
            predict_fen_via_net(_board(), url="http://localhost:9999/predict")
        self.assertEqual(chamada.call_args.args[0].full_url, "http://localhost:9999/predict")

    def test_a_network_error_becomes_a_message_in_portuguese(self) -> None:
        erro = urllib.error.URLError("getaddrinfo failed")
        with mock.patch.object(net_correction._OPENER, "open", side_effect=erro):
            with self.assertRaises(RuntimeError) as capturado:
                predict_fen_via_net(_board(), url=ENDPOINT)
        self.assertIn("Erro de rede", str(capturado.exception))

    def test_an_http_error_reports_the_body_the_server_sent(self) -> None:
        erro = urllib.error.HTTPError(
            ENDPOINT, 413, "Payload Too Large", {}, io.BytesIO(b"imagem grande demais")  # type: ignore[arg-type]
        )
        with mock.patch.object(net_correction._OPENER, "open", side_effect=erro):
            with self.assertRaises(RuntimeError) as capturado:
                predict_fen_via_net(_board(), url=ENDPOINT)
        self.assertIn("imagem grande demais", str(capturado.exception))

    def test_an_http_error_with_an_empty_body_falls_back_to_the_status(self) -> None:
        erro = urllib.error.HTTPError(ENDPOINT, 500, "Server Error", {}, io.BytesIO(b""))  # type: ignore[arg-type]
        with mock.patch.object(net_correction._OPENER, "open", side_effect=erro):
            with self.assertRaises(RuntimeError) as capturado:
                predict_fen_via_net(_board(), url=ENDPOINT)
        self.assertIn("HTTP 500", str(capturado.exception))

    def test_the_timeout_is_passed_through_instead_of_being_left_to_the_default(self) -> None:
        """Sem timeout, um serviço de terceiro fora do ar congela a thread para sempre."""
        with _responding(f'{{"results": [{{"fen": "{FEN}"}}]}}') as chamada:
            predict_fen_via_net(_board(), url=ENDPOINT, timeout=7)
        self.assertEqual(chamada.call_args.kwargs["timeout"], 7)

    def test_o_envio_nao_passa_por_urlopen(self) -> None:
        """S-59: `urlopen` segue redirect, e seguir um fura o consentimento da S-32.

        Este teste é sobre os **testes** tanto quanto sobre o código. Enquanto eles
        substituíam `urllib.request.urlopen`, trocar o caminho de envio não os fazia falhar:
        fazia-os sair para a rede de verdade. Foi o que aconteceu ao introduzir o opener, e é
        a razão de a garantia estar escrita aqui em vez de só no docstring.
        """
        fonte = Path(net_correction.__file__).read_text(encoding="utf-8")
        corpo = fonte.split("def predict_fen_via_net(", 1)[1]
        self.assertIn("_OPENER.open(", corpo)
        self.assertNotIn("urlopen(", corpo)

    def test_nenhuma_requisicao_sai_com_o_opener_substituido(self) -> None:
        """A rede está de fato desligada nestes testes -- não só por convenção."""
        with mock.patch.object(net_correction._OPENER, "open", side_effect=AssertionError("saiu para a rede")):
            with self.assertRaises(AssertionError):
                predict_fen_via_net(_board(), url=ENDPOINT)


if __name__ == "__main__":
    unittest.main()
