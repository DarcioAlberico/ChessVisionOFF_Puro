"""Cliente do serviço externo de correção de FEN — o botão "Corrigir Net".

**O que é.** Um serviço de terceiro que recebe a imagem do tabuleiro e devolve uma FEN.
Serve como segunda opinião quando o modelo local erra.

**Por que mora aqui e não no `app_tkinter.py`.** Ele estava embutido na janela, e com ele
os quatro modos de falha que um cliente HTTP tem: erro de rede, HTTP de erro, corpo que não
é JSON e JSON sem o campo esperado. Nenhum deles tinha teste, porque testá-los exigia abrir
uma janela. Aqui cada um é um caso, e as mensagens em pt-BR que a interface mostra são
verificáveis.

**Quem decide *se* a requisição parte não é este módulo.** Aqui mora o *como*. A decisão é
do `settings.py` (habilitado? qual endpoint?) e da interface (o usuário consentiu?). Essa
separação é o que permite ao teste da S-32 provar que, sem configuração, nenhuma requisição
existe: não há caminho que construa um provedor.

**`RemoteFenProvider` é protocolo, não classe base.** A S-32 pede que outros serviços -- ou
um segundo modelo local -- possam entrar como segunda opinião. Um `Protocol` deixa isso
aberto sem obrigar ninguém a herdar de um cliente HTTP para não ser um.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from typing import Protocol, runtime_checkable

import cv2
import numpy as np

from .settings import RemoteFenSettings

logger = logging.getLogger(__name__)

KNOWN_PUBLIC_ENDPOINT = "https://helpman.komtera.lt/predict"
"""O endereço que estava fixo no código até a S-32. Continua documentado porque quem já
usava o recurso precisa saber o que escrever para tê-lo de volta -- mas agora é o usuário
quem o declara, e nada aqui o usa como padrão."""

DEFAULT_TIMEOUT = 30.0


@runtime_checkable
class RemoteFenProvider(Protocol):
    """Uma segunda opinião sobre a FEN de um tabuleiro (S-32).

    Não presume HTTP: um segundo modelo local satisfaz a mesma interface, e é justamente
    esse o uso que alimentaria o sinal de concordância da S-12.
    """

    @property
    def name(self) -> str:
        """Como o provedor aparece na barra de status e no log."""

    def predict(self, image_rgb: np.ndarray) -> str:
        """A FEN lida, ou `RuntimeError` com o motivo em pt-BR."""


class HttpFenProvider:
    """Provedor que fala com um serviço HTTP que aceita `multipart/form-data`."""

    def __init__(self, url: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        if not url.strip():
            # Falhar aqui, e nao na hora do envio: um provedor sem destino nao deveria
            # chegar a existir, e deixa-lo existir e o que faria a UI oferecer o botao.
            raise ValueError("Provedor remoto exige um endpoint declarado.")
        self.url = url.strip()
        self.timeout = timeout

    @property
    def name(self) -> str:
        return self.url

    def predict(self, image_rgb: np.ndarray) -> str:
        return predict_fen_via_net(image_rgb, url=self.url, timeout=self.timeout)


def build_provider(settings: RemoteFenSettings) -> RemoteFenProvider | None:
    """O provedor que a configuração autoriza, ou `None` -- e `None` significa não enviar.

    É o único caminho para um provedor existir. Sem ele não há como uma requisição partir
    por engano, que é exatamente o que o critério de aceite da S-32 exige poder provar.
    """
    if not settings.is_usable:
        return None
    return HttpFenProvider(settings.endpoint, timeout=settings.timeout)


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
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Envia o tabuleiro ao serviço externo e devolve a FEN que ele responder.

    **Esta chamada envia a imagem para fora da máquina.** Quem decide se ela pode partir é
    a configuração e a interface (S-32); aqui a decisão já foi tomada, e por isso `url` é
    obrigatória -- não há para onde enviar por padrão.
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
