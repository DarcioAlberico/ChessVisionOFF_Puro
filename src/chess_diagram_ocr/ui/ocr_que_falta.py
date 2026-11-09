"""O OCR de legenda que foi pedido e não subiu, dito na janela (S-884).

**O defeito.** O `.exe` não leva o `onnxruntime` (`packaging/cvoff.spec`), o padrão de `ocr.engine`
é `rapidocr`, e `ocr.build_recognizer` responde ao `ImportError` com uma linha de log que manda
rodar `uv sync --extra ocr` -- o que ninguém faz num executável. O serviço nascia sem leitor de
legenda e a janela abria como se ele estivesse lá: o OCR faltava em silêncio, justamente nos livros
sem camada de texto, onde a legenda é a única pista do lado a jogar.

**Por que aqui, e não em `ocr.py`.** `ocr` e `settings` estão no fecho de medição dos relatórios
de campo (S-218); mexer neles por causa de uma frase de janela obrigaria a remedir os quatro. E o
fecho já devolve tudo o que a pergunta precisa: o serviço diz se há `caption_reader`, a
configuração diz o que foi pedido, e `ocr.KNOWN_ENGINES` diz o que existe. A frase é decisão de
interface, e mora com as outras.

**No executável a resposta é outra, e ela é sabida** -- é o mesmo raciocínio do `tsoj_reader`
(S-387). Um motor de terceiro (`rapidocr`, `easyocr`, `tesseract`) pedido e ausente no `.exe` não
é defeito a procurar: é decisão de empacotamento, e o que a pessoa pode fazer ali é escolher o
`glifo`, que é de casa e vai no bundle. Se a D8 da solidez puser o `onnxruntime` no bundle, o
`rapidocr` passa a subir e esta frase deixa de aparecer para ele -- nada aqui precisa mudar.
"""

from __future__ import annotations

import sys
from typing import Protocol

from ..ocr import KNOWN_ENGINES, MOTOR_DE_CASA
from ..settings import OcrSettings
from . import estado_do_rodape

__all__ = ["ABERTURA", "ServicoComLeitor", "frase", "frase_de_abertura"]


class ServicoComLeitor(Protocol):
    """O que `frase_de_abertura` pergunta ao `OcrService`, e nada mais."""

    @property
    def caption_reader(self) -> object: ...


ABERTURA = "Abra um livro em PDF para começar."
"""O que o rodapé diz quando a janela abre e não falta nada."""


def frase(ocr: OcrSettings, *, leitor_pronto: bool, congelado: bool) -> str:
    """Por que o OCR de legenda pedido não está de pé, em pt-BR. Vazio quando não falta nada.

    `congelado` é o `sys.frozen` do PyInstaller: ele decide se a saída é instalar o extra ou
    trocar de motor.
    """
    if not ocr.enabled or leitor_pronto:
        return ""
    motor = ocr.engine.strip().lower()
    if motor not in KNOWN_ENGINES:
        return (
            f"O OCR de legenda pede o motor {ocr.engine!r}, que não existe; os conhecidos são "
            f"{', '.join(KNOWN_ENGINES)}. A leitura segue sem OCR de legenda."
        )
    if motor == MOTOR_DE_CASA:
        return ocr.glyph_disabled_reason() or (
            f"O OCR de legenda com o motor {motor} não subiu, e o log diz por quê. "
            "A leitura segue sem OCR de legenda."
        )
    if congelado:
        return (
            f"O OCR de legenda com o motor {motor} não está disponível na versão empacotada: o "
            "executável não leva os motores de terceiro (o rapidocr depende do onnxruntime). "
            f"Escolha o motor {MOTOR_DE_CASA} em data/settings.json (`ocr.engine`) ou use a "
            "instalação de desenvolvimento. A leitura segue sem OCR de legenda."
        )
    return (
        f"O OCR de legenda com o motor {motor} não subiu: o extra não está instalado ou o motor "
        "não iniciou, e o log diz qual. Instale com `uv sync --extra ocr`. "
        "A leitura segue sem OCR de legenda."
    )


def frase_de_abertura(servico: ServicoComLeitor, ocr: OcrSettings, *, congelado: bool | None = None) -> tuple[str, str]:
    """`(frase, severidade)` do rodapé ao abrir a janela: a falta do OCR quando há uma, ou `ABERTURA`.

    **O serviço só é interrogado quando o OCR foi pedido**: desligado é o padrão (S-42), e os
    serviços falsos dos testes de janela não têm `caption_reader` a responder.
    """
    if congelado is None:
        congelado = bool(getattr(sys, "frozen", False))
    if ocr.enabled:
        falta = frase(ocr, leitor_pronto=servico.caption_reader is not None, congelado=congelado)
        if falta:
            return falta, estado_do_rodape.AVISO
    return ABERTURA, estado_do_rodape.INFORMACAO
