"""O que o Windows precisa saber antes de a janela existir: DPI e ícone (S-148).

**Duas ausências que decidem a primeira impressão antes de qualquer widget.**

*DPI.* Nada no projeto chamava `SetProcessDpiAwareness`. Num monitor a 125% ou 150% — o padrão
de fábrica de quase todo notebook novo — o Windows trata o processo como legado, desenha a
janela a 96 DPI e **amplia o bitmap inteiro** para o tamanho da tela. O texto, as coordenadas
do tabuleiro e a página do PDF ficam borrados. Num programa cujo trabalho é conferir glifo
impresso, borrão é dano funcional e não estético.

*Ícone.* `iconphoto` nunca era chamado e `packaging/cvoff.spec` trazia `icon=None`. Barra de
tarefas, Alt-Tab, atalho e `.exe` mostravam a pena genérica do Tk — o desenho que diz "isto é um
script Python", que é a única coisa que o produto não é.

**Nada aqui derruba a janela.** É o mesmo contrato do `ui/theme.py` desde a S-53: aparência não
derruba ferramenta. Toda chamada de sistema deste módulo é tolerante, e o que falhou vira uma
linha de log — não uma exceção que impede o programa de abrir num Windows diferente do desta
máquina, num Linux, ou num `ctypes` sem `windll`.

**A ordem importa, e é por isso que são duas funções.** `SetProcessDpiAwareness` só vale se
chamada **antes** de o processo criar a primeira janela; depois disso o Windows já decidiu como
tratar o processo e devolve `E_ACCESSDENIED`. Daí `consciencia_de_dpi()` ser chamável sozinha,
antes de `tk.Tk()`, e `preparar_janela(root)` cuidar do que precisa de janela pronta.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import BUNDLE_ROOT
from . import tokens

logger = logging.getLogger(__name__)

__all__ = [
    "CAMINHO_DO_ICONE",
    "DPI_DE_REFERENCIA",
    "gravar_icone",
]

DPI_DE_REFERENCIA = 96.0
"""O DPI de um monitor a 100%. Serve de referência para o log dizer "150%", e não para a conta."""

TAMANHOS_DO_ICONE = (16, 24, 32, 48, 64, 128, 256)
"""Os tamanhos que vão dentro do `.ico`.

Windows escolhe um deles por contexto: 16 na barra de título e na lista de tarefas pequena, 32
no Alt-Tab, 48 no Explorer em ícones médios, 256 em ícones extra-grandes. Um `.ico` com só um
tamanho faz o Windows reamostrar, e reamostragem de 256 para 16 vira borrão — que é o mesmo
defeito de DPI, num lugar menor."""

CAMINHO_DO_ICONE = BUNDLE_ROOT / "assets" / "cvoff.ico"
"""O ícone do produto, dentro do bundle.

`BUNDLE_ROOT` e não `PROJECT_ROOT`: ícone é recurso do programa, como as imagens de peça, e não
dado do usuário. A distinção é a mesma da S-55 e é ela que faz reinstalar não apagar rótulo."""

_PECA_DO_ICONE = "wn"
"""O cavalo branco. É a peça que se reconhece a 16 px de silhueta, sem cor e sem detalhe —
torre e bispo viram retângulo, e rei e dama viram a mesma cruz borrada."""


def _monitores_do_windows() -> list[tuple[int, int, int, int]]:
    """`EnumDisplayMonitors`, com o principal (o que contém a origem) na frente."""
    try:
        import ctypes
        from ctypes import wintypes

        achados: list[tuple[int, int, int, int]] = []
        ponteiro_de_rect = ctypes.POINTER(wintypes.RECT)

        def visitar(_monitor: int, _dc: int, retangulo: Any, _dados: int) -> int:
            caixa = retangulo.contents
            achados.append((int(caixa.left), int(caixa.top), int(caixa.right), int(caixa.bottom)))
            return 1

        prototipo = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ponteiro_de_rect, ctypes.c_double
        )
        ctypes.windll.user32.EnumDisplayMonitors(0, 0, prototipo(visitar), 0)
        # O principal é o que contém a origem (0,0) -- é a definição do Windows, e é ele que
        # `geometria_corrigida` usa para reposicionar a janela perdida.
        achados.sort(key=lambda caixa: (caixa[0], caixa[1]) != (0, 0))
        return achados
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.info("Monitores não enumerados (%s): usando a tela que o Tk conhece.", exc)
        return []


def compor_icone(tamanho: int):  # -> PIL.Image.Image
    """O ícone do produto num tamanho: o cavalo de `assets/piece_images/` sobre a esteira.

    **Composto, e não recortado de uma captura.** A peça vem transparente com contorno escuro;
    sobre fundo claro do Explorer ela some. A esteira da S-147 (`SUPERFICIE_TABULEIRO`) dá o
    contraste, e usá-la aqui é o que faz o ícone e a janela serem visivelmente o mesmo produto.

    A moldura é o mesmo anel de 2 px do tabuleiro, proporcional ao tamanho — sem ela, o ícone
    encosta na borda e a 16 px vira um quadrado escuro.
    """
    from PIL import Image

    anel = max(1, round(tamanho / 16))
    imagem = Image.new("RGBA", (tamanho, tamanho), tokens.RESERVA[tokens.MOLDURA])
    interno = max(1, tamanho - 2 * anel)
    imagem.paste(Image.new("RGBA", (interno, interno), tokens.RESERVA[tokens.SUPERFICIE_TABULEIRO]), (anel, anel))

    # A peça ocupa a área interna com uma folga de um anel de cada lado: cheia demais e a
    # silhueta encosta na moldura, pequena demais e a 16 px sobra fundo e falta cavalo. A
    # proporção original é preservada -- o cavalo é mais alto que largo, e esticá-lo até o
    # quadrado é o tipo de detalhe que só se vê depois de o ícone estar na barra de tarefas.
    peca = Image.open(BUNDLE_ROOT / "assets" / "piece_images" / f"{_PECA_DO_ICONE}.png").convert("RGBA")
    peca = peca.crop(peca.getbbox() or (0, 0, peca.width, peca.height))
    cabe = max(1, tamanho - 4 * anel)
    fator = min(cabe / peca.width, cabe / peca.height)
    largura, altura = max(1, round(peca.width * fator)), max(1, round(peca.height * fator))
    peca = peca.resize((largura, altura), Image.Resampling.LANCZOS)
    imagem.paste(peca, ((tamanho - peca.width) // 2, (tamanho - peca.height) // 2), peca)
    return imagem


def gravar_icone(destino: Path = CAMINHO_DO_ICONE, tamanhos: tuple[int, ...] = TAMANHOS_DO_ICONE) -> Path:
    """Escreve o `.ico` com todos os tamanhos. É o gerador, e o teste o roda em memória.

    O arquivo é versionado porque o `.spec` do PyInstaller precisa dele **em disco** na hora do
    build, e um build que gerasse o próprio ícone dependeria de o Pillow estar no ambiente de
    empacotamento. O teste garante que o arquivo em disco e este gerador não divergiram.
    """
    maior = compor_icone(max(tamanhos))
    destino.parent.mkdir(parents=True, exist_ok=True)
    maior.save(destino, format="ICO", sizes=[(lado, lado) for lado in sorted(tamanhos)])
    return destino
