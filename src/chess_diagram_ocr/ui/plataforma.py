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
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import BUNDLE_ROOT
from . import tokens

logger = logging.getLogger(__name__)

__all__ = [
    "CAMINHO_DO_ICONE",
    "DPI_DE_REFERENCIA",
    "PONTOS_POR_POLEGADA",
    "TAMANHOS_DO_ICONE",
    "Preparo",
    "compor_icone",
    "consciencia_de_dpi",
    "escala_de_tk",
    "gravar_icone",
    "monitores",
    "preparar_janela",
]

PONTOS_POR_POLEGADA = 72.0
"""A unidade de `tk scaling`: quantos pixels o Tk desenha para cada ponto tipográfico.

Não é 96. `tk scaling` é pixels **por ponto**, e ponto é 1/72 de polegada por definição
tipográfica — o 96 é o DPI que o Windows finge quando o processo não declara consciência, e
confundir os dois é o erro que faz a fonte sair 33% menor do que se pediu."""

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


def escala_de_tk(dpi: float) -> float:
    """O valor de `tk scaling` para um DPI: pixels por ponto (S-148).

    Função pura, e é o ponto: a conversão é afirmável em 96, 120 e 144 sem abrir janela nem
    ter um monitor de cada densidade à mão.

    96 DPI (100%) dá 1,333; 120 (125%) dá 1,667; 144 (150%) dá 2,0. Um DPI não positivo — que é
    o que um `winfo_fpixels` sem janela mapeada devolve — cai na referência, porque escala zero
    faria o Tk desenhar fonte de altura zero.
    """
    if dpi <= 0:
        dpi = DPI_DE_REFERENCIA
    return dpi / PONTOS_POR_POLEGADA


@dataclass(frozen=True)
class Preparo:
    """O que de fato deu certo. Existe para o teste poder afirmar cada parte separadamente.

    Uma função que só faz efeito colateral e devolve `None` é indistinguível de uma que não fez
    nada — e "não fez nada" é justamente o estado anterior a este item.
    """

    consciencia_de_dpi: bool
    dpi: float
    escala: float
    icone: Path | None

    @property
    def percentual(self) -> int:
        """O DPI dito como o Windows o mostra: 100, 125, 150."""
        return round(100 * self.dpi / DPI_DE_REFERENCIA)


def consciencia_de_dpi() -> bool:
    """Declara ao Windows que este processo desenha na densidade real do monitor.

    Devolve se conseguiu. Fora do Windows, sem `ctypes.windll` ou com a chamada recusada,
    devolve `False` e segue — a janela abre borrada, que é como ela abria antes deste item.

    **Chame antes de `tk.Tk()`.** Depois da primeira janela o Windows já classificou o processo
    e devolve `E_ACCESSDENIED`; a chamada continua sem levantar, e continua sem efeito.

    Dois caminhos, do mais específico para o mais antigo: `shcore.SetProcessDpiAwareness(2)` é
    por monitor e existe desde o 8.1; `user32.SetProcessDPIAware()` é do sistema inteiro e
    existe desde o Vista. Num monitor só, os dois dão o mesmo resultado; em dois monitores de
    densidades diferentes, só o primeiro reescala ao arrastar a janela de um para o outro.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            return True
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
            return True
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.info("Sem consciência de DPI (%s): a janela abre na escala do sistema.", exc)
        return False


def monitores(root: tk.Misc | None = None) -> list[tuple[int, int, int, int]]:
    """Os retângulos `(x0, y0, x1, y1)` dos monitores, o principal primeiro (S-156).

    **Por que isto existe.** A geometria guardada da janela é em coordenada de área de trabalho,
    e a área de trabalho muda entre sessões: desconectar a tela do escritório move a janela para
    `+2560+0`, onde não há mais tela nenhuma. Restaurá-la ali abre uma janela invisível, sem
    erro nenhum a que se agarrar — o programa parece não ter aberto.

    No Windows, `EnumDisplayMonitors` dá a lista de verdade. Fora dele, e em qualquer falha, a
    reserva é **um** retângulo com a tela que o Tk conhece: pior que a lista completa e melhor
    que nada, porque ainda pega o caso comum de a janela estar fora da única tela que existe.

    Devolve lista vazia quando nem o Tk responde, e `geometria_corrigida` trata isso como "não
    sei onde estão as telas" — que não é razão para mover a janela de ninguém.
    """
    if sys.platform == "win32":
        achados = _monitores_do_windows()
        if achados:
            return achados
    if root is None:
        return []
    try:
        return [(0, 0, int(root.winfo_screenwidth()), int(root.winfo_screenheight()))]
    except Exception:  # noqa: BLE001 - duplo de teste ou Tk sem tela
        return []


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


def _aplicar_icone(root: tk.Misc) -> Path | None:
    """Põe o ícone na janela. `None` quando não deu — e a janela abre com a pena do Tk.

    `iconbitmap` é o caminho do Windows e o único que alcança a barra de tarefas e o Alt-Tab;
    `iconphoto` é o portátil e vale para o resto. Tentar os dois, nesta ordem, é o que faz o
    item valer nos dois lugares sem um `if` de plataforma decidindo aparência.
    """
    if not CAMINHO_DO_ICONE.is_file():
        logger.info("Ícone não encontrado em %s: a janela abre com o padrão do Tk.", CAMINHO_DO_ICONE)
        return None
    try:
        root.iconbitmap(default=str(CAMINHO_DO_ICONE))  # type: ignore[attr-defined]
        return CAMINHO_DO_ICONE
    except Exception:  # noqa: BLE001 - `iconbitmap` com `default` é só do Windows
        pass
    try:
        from PIL import Image, ImageTk

        with Image.open(CAMINHO_DO_ICONE) as imagem:
            foto = ImageTk.PhotoImage(imagem.convert("RGBA"), master=root)
        root.iconphoto(True, foto)  # type: ignore[attr-defined]
        # Sem esta referência o Tk descarta a imagem no próximo ciclo e o ícone some.
        root._cvoff_icone = foto  # type: ignore[attr-defined]
        return CAMINHO_DO_ICONE
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.info("Ícone não aplicado (%s).", exc)
        return None


def _dpi_da_janela(root: tk.Misc) -> float:
    """Quantos pixels o Tk conta numa polegada desta janela. Referência quando não sabe."""
    try:
        return float(root.winfo_fpixels("1i"))
    except Exception:  # noqa: BLE001 - duplo de teste, janela não mapeada, Tk exótico
        return DPI_DE_REFERENCIA


def preparar_janela(root: tk.Misc) -> Preparo:
    """DPI e ícone, antes de qualquer widget (S-148). Nunca levanta.

    Chamável com um duplo de `root` que levante em toda chamada: o teste faz exatamente isso,
    porque a garantia que importa aqui não é o efeito e sim a **ausência de propagação** — este
    é o primeiro código a rodar na abertura da janela, e uma exceção aqui é uma janela que não
    abre em vez de uma janela sem ícone.
    """
    consciente = consciencia_de_dpi()
    dpi = _dpi_da_janela(root)
    escala = escala_de_tk(dpi)
    try:
        root.tk.call("tk", "scaling", escala)
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.info("Escala do Tk não aplicada (%s).", exc)
    preparo = Preparo(consciencia_de_dpi=consciente, dpi=dpi, escala=escala, icone=_aplicar_icone(root))
    logger.info(
        "Janela preparada: DPI %.0f (%d%%), escala %.3f, consciência de DPI %s, ícone %s.",
        preparo.dpi,
        preparo.percentual,
        preparo.escala,
        "sim" if preparo.consciencia_de_dpi else "não",
        preparo.icone.name if preparo.icone else "padrão do Tk",
    )
    return preparo
