"""Cliente do serviço externo de correção de FEN — o botão "Corrigir Net".

**O que é.** Um serviço de terceiro que recebe a imagem do tabuleiro e devolve uma FEN.
Serve como segunda opinião quando o modelo local erra.

**Por que mora aqui e não no `app_tkinter.py`.** Ele estava embutido na janela, e com ele
os quatro modos de falha que um cliente HTTP tem: erro de rede, HTTP de erro, corpo que não
é JSON e JSON sem o campo esperado. Nenhum deles tinha teste, porque testá-los exigia abrir
uma janela. Aqui cada um é um caso, e as mensagens em pt-BR que a interface mostra são
verificáveis.

**O que ainda não é (S-32).** O endpoint continua fixo e o recurso continua ligado por
padrão. Torná-lo opt-in, configurável e com aviso explícito de que a imagem sai da máquina
é o item 6.3 -- e é ele quem deve decidir *se* a requisição parte, não este módulo, que
sabe apenas *como* fazê-la.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_NET_CORRECT_URL = "https://helpman.komtera.lt/predict"
"""Serviço de terceiro, sem contrato. Pode sair do ar; nunca é dependência do fluxo."""

DEFAULT_TIMEOUT = 30.0


def encode_multipart_png(image_rgb: np.ndarray, *, field: str = "file", filename: str = "board.png") -> tuple[bytes, str]:
    """Codifica a imagem como `multipart/form-data`, devolvendo `(corpo, content-type)`."""
    if image_rgb.size == 0:
        raise ValueError("Imagem vazia.")

    ok, buffer = cv2.imencode(".png", cv2.cvtColor(image_rgb.astype(np.uint8), cv2.COLOR_RGB2BGR))
    if not ok:
        raise ValueError("Nao foi possivel codificar a imagem do tabuleiro em PNG.")

    boundary = f"----ChessVisionBoundary{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("ascii"),
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode("ascii"),
            b"Content-Type: image/png\r\n\r\n",
            buffer.tobytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("ascii"),
        ]
    )
    return body, f"multipart/form-data; boundary={boundary}"


def parse_net_response(payload: str) -> str:
    """Extrai a FEN da resposta, ou levanta `RuntimeError` com o motivo em pt-BR.

    Separada da requisição de propósito: os três jeitos de a resposta não servir -- não é
    JSON, não traz `results`, traz `results` com FEN vazia -- são o que de fato acontece com
    um serviço sem contrato, e são testáveis sem rede.
    """
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Resposta da API nao esta em JSON.") from exc

    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(results, list) or not results:
        message = parsed.get("message") if isinstance(parsed, dict) else ""
        raise RuntimeError(str(message or "API nao retornou resultados."))

    primeiro = results[0]
    fen = str(primeiro.get("fen", "")).strip() if isinstance(primeiro, dict) else ""
    if not fen:
        raise RuntimeError("API retornou FEN vazia.")
    return fen


def predict_fen_via_net(
    image_rgb: np.ndarray,
    *,
    url: str = DEFAULT_NET_CORRECT_URL,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Envia o tabuleiro ao serviço externo e devolve a FEN que ele responder.

    **Esta chamada envia a imagem para fora da máquina.** Quem decide se ela pode partir é
    a interface (S-32); aqui a decisão já foi tomada.
    """
    body, content_type = encode_multipart_png(image_rgb)
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": content_type, "Accept": "application/json"},
        method="POST",
    )

    logger.info("Enviando tabuleiro para correcao externa em %s.", url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL vem da config
            payload = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detalhes = exc.read().decode("utf-8", errors="replace").strip() or f"HTTP {exc.code}"
        raise RuntimeError(detalhes) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Erro de rede: {exc.reason}") from exc

    return parse_net_response(payload)
