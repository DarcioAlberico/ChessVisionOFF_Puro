"""O que o sistema precisa saber antes de a janela existir: DPI e ícone, no Qt (S-501).

**O item é o mesmo da S-148, e metade dele o Qt já resolve.** Aquele item registrou duas
ausências: o processo não declarava consciência de DPI -- e num monitor a 125% o Windows
ampliava o bitmap inteiro, borrando o texto, as coordenadas do tabuleiro e a página do PDF --,
e a janela abria com a pena genérica do Tk.

O Qt 6 declara a consciência de DPI **por conta própria**, na criação da `QApplication`: ele é
sempre *per-monitor DPI aware* e não existe mais como desligar isso. O `SetProcessDpiAwareness`
que `ui/plataforma.py` chama com `ctypes` não tem contraparte aqui, e chamá-lo assim mesmo seria
pior que inútil -- a chamada precisa vir antes da primeira janela, e depois dela o Windows
devolve `E_ACCESSDENIED`. **A ausência dessa função é o item, e não um esquecimento.**

O que sobra deste lado, então, é o que o Qt **não** faz sozinho:

1. *O ícone.* `QApplication` não adota `assets/cvoff.ico` por estar no disco. Sem
   `setWindowIcon` a barra de tarefas, o Alt-Tab e o atalho mostram o ícone genérico -- o mesmo
   defeito da S-148, com outro desenho.
2. *A escala de arredondamento.* Em 125% e 150% o Qt precisa saber o que fazer com a fração; o
   padrão dele arredonda, e o que a janela quer é a densidade real. Ver `PoliticaDeEscala`.

**O gerador do `.ico` continua sendo o de `ui/plataforma.py`**, e é de propósito: ele compõe o
cavalo sobre a esteira com o Pillow, não toca `tkinter` numa linha, e é o arquivo em disco que o
`packaging/cvoff.spec` consome. Dois geradores dariam dois ícones para a mesma barra de tarefas.

**Nada aqui derruba a janela.** É o contrato da S-53 e o do módulo irmão: toda chamada de sistema
é tolerante, e o que falhou vira uma linha de log.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QWidget

from chess_diagram_ocr.ui.plataforma import CAMINHO_DO_ICONE, DPI_DE_REFERENCIA

logger = logging.getLogger(__name__)

__all__ = [
    "CAMINHO_DO_ICONE",
    "DPI_DE_REFERENCIA",
    "ID_NA_BARRA_DE_TAREFAS",
    "Preparo",
    "aplicar_icone",
    "identificar_na_barra_de_tarefas",
    "monitores",
    "politica_de_escala",
    "preparar_janela",
]

ID_NA_BARRA_DE_TAREFAS = "DarcioAlberico.ChessVisionOFF.Puro"
"""O `AppUserModelID` do Windows, e sem ele o ícone da barra de tarefas não é o da janela.

**O defeito que isto conserta é específico do Windows e não tem sintoma em lugar nenhum.** Um
processo Python que não declara identidade própria é agrupado sob o `python.exe` que o lançou: a
barra de tarefas mostra o ícone do **interpretador**, mesmo com `setWindowIcon` aplicado e
funcionando -- a janela tem o cavalo, e o botão na barra tem a serpente. `ui/plataforma.py` não
precisava disto porque o `iconbitmap(default=...)` do Tk faz a mesma coisa por dentro.

Formato `Empresa.Produto.SubProduto`, que é o que a documentação da Microsoft pede."""


@dataclass(frozen=True)
class Preparo:
    """O que de fato deu certo. Existe para o teste poder afirmar cada parte separadamente.

    Uma função que só faz efeito colateral e devolve `None` é indistinguível de uma que não fez
    nada -- e "não fez nada" é justamente o estado anterior a este item. É o `Preparo` da S-148,
    com os campos que fazem sentido deste lado.
    """

    dpi: float
    escala: float
    icone: Path | None
    identificado: bool

    @property
    def percentual(self) -> int:
        """O DPI dito como o Windows o mostra: 100, 125, 150."""
        return round(100 * self.dpi / DPI_DE_REFERENCIA)


def politica_de_escala() -> None:
    """Diz ao Qt o que fazer com a fração de 125% e 150%. **Chame antes da `QApplication`.**

    Depois dela a política já foi lida, e a chamada não tem efeito -- é a mesma pré-condição de
    `consciencia_de_dpi`, e pela mesma razão: quem decide densidade decide antes de haver janela.

    `PassThrough` é o que preserva a fração. O padrão do Qt 6 (`Round`) transforma 125% em 100%
    e devolve exatamente o borrão que a S-148 mediu, por outro caminho: a janela é desenhada para
    uma densidade e esticada para outra. Num programa cujo trabalho é conferir glifo impresso,
    isso é dano funcional e não estético.

    Não levanta: uma variável de ambiente já posta por quem roda ganha desta, e é o que permite
    diagnosticar um problema de escala sem editar código.
    """
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")


def identificar_na_barra_de_tarefas(identificador: str = ID_NA_BARRA_DE_TAREFAS) -> bool:
    """Declara ao Windows que este processo é um produto, e não um `python.exe`.

    Devolve se conseguiu. Fora do Windows, sem `ctypes.windll` ou com a chamada recusada,
    devolve `False` e segue -- o ícone da barra fica sendo o do interpretador, que é como ele
    estava antes deste item.

    **Chame antes da primeira janela.** Depois dela o Windows já agrupou o botão da barra de
    tarefas, e a mudança só vale para a próxima execução.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(identificador)
        return True
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.info("Sem identidade na barra de tarefas (%s): o ícone dela será o do Python.", exc)
        return False


def aplicar_icone(aplicacao: QApplication | None = None) -> Path | None:
    """Põe o ícone do produto na aplicação. `None` quando não deu.

    **Na aplicação e não na janela**, e a diferença importa: `QApplication.setWindowIcon` vale
    para toda janela do processo, inclusive os diálogos. Pô-lo em cada janela deixaria o
    primeiro diálogo que alguém esquecesse com o ícone genérico -- é o argumento de
    `theme.ESTILO_DE_TITULO`, aplicado a outro recurso.
    """
    if not CAMINHO_DO_ICONE.is_file():
        logger.info("Ícone não encontrado em %s: a janela abre com o padrão do Qt.", CAMINHO_DO_ICONE)
        return None
    alvo = aplicacao or QApplication.instance()
    if not isinstance(alvo, QApplication):  # pragma: no cover - erro de ordem
        logger.info("Sem QApplication: o ícone não foi aplicado.")
        return None
    try:
        icone = QIcon(str(CAMINHO_DO_ICONE))
        if icone.isNull():
            # `QIcon` de um arquivo ilegível **não levanta**: ele devolve um ícone vazio, e a
            # janela abre com o padrão sem uma linha a que se agarrar. É por isso que a
            # pergunta é feita aqui em vez de se confiar na ausência de exceção.
            logger.info("Ícone em %s não foi lido pelo Qt: a janela abre com o padrão.", CAMINHO_DO_ICONE)
            return None
        alvo.setWindowIcon(icone)
        return CAMINHO_DO_ICONE
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.info("Ícone não aplicado (%s).", exc)
        return None


def _dpi_da_janela(janela: QWidget | None) -> float:
    """Quantos pixels o Qt conta numa polegada desta tela. A referência quando não sabe."""
    try:
        tela = janela.screen() if janela is not None else None
        if tela is None:
            aplicacao = QApplication.instance()
            tela = aplicacao.primaryScreen() if isinstance(aplicacao, QApplication) else None
        return float(tela.logicalDotsPerInch()) if tela is not None else DPI_DE_REFERENCIA
    except Exception:  # noqa: BLE001 - duplo de teste, janela sem tela, Qt exótico
        return DPI_DE_REFERENCIA


def preparar_janela(janela: QWidget | None = None) -> Preparo:
    """Ícone e identidade, com a janela já criada (S-148/S-501). Nunca levanta.

    Chamável com um duplo que levante em toda chamada: o teste faz exatamente isso, porque a
    garantia que importa aqui não é o efeito e sim a **ausência de propagação** -- este é o
    primeiro código a rodar na abertura da janela, e uma exceção aqui é uma janela que não abre
    em vez de uma janela sem ícone.

    **Não declara consciência de DPI**, e a ausência está explicada no cabeçalho: o Qt 6 já a
    declarou ao construir a `QApplication`, e a fração é decidida por `politica_de_escala`, que
    roda antes dela.
    """
    dpi = _dpi_da_janela(janela)
    preparo = Preparo(
        dpi=dpi,
        escala=dpi / DPI_DE_REFERENCIA,
        icone=aplicar_icone(),
        identificado=identificar_na_barra_de_tarefas(),
    )
    logger.info(
        "Janela preparada: DPI %.0f (%d%%), escala %.3f, ícone %s, identidade na barra %s.",
        preparo.dpi,
        preparo.percentual,
        preparo.escala,
        preparo.icone.name if preparo.icone else "padrão do Qt",
        "sim" if preparo.identificado else "não",
    )
    return preparo


def monitores() -> tuple[tuple[int, int, int, int], ...]:
    """Os retângulos das telas, no formato que `ui/geometria.py` cobra: `(x0, y0, x1, y1)`.

    **É a metade que faltava da restauração de geometria (S-156).** `geometria_corrigida` decide
    se a janela guardada ainda cabe nas telas de hoje, e a lista de telas é a única parte daquela
    decisão que conhece toolkit -- do lado do Tk ela era `ui/plataforma.monitores`.

    **Área útil e não a física** (`availableGeometry`): a barra de tarefas ocupa parte da tela, e
    uma janela restaurada por baixo dela abre com a barra de título fora do alcance do mouse.

    **A principal vem primeiro**, porque é ela que `geometria_corrigida` usa para centralizar a
    janela que não cabe em lugar nenhum -- e `screens()` não promete ordem.

    Vazio quando não há `QApplication`, ou quando o Qt recusa a pergunta. `geometria_corrigida`
    já trata o vazio como "não sei onde estão as telas", que é a resposta certa: não saber não é
    razão para mover a janela de lugar.
    """
    aplicacao = QApplication.instance()
    if not isinstance(aplicacao, QApplication):
        return ()
    try:
        principal = aplicacao.primaryScreen()
        telas = [principal, *(t for t in aplicacao.screens() if t is not principal)] if principal else list(aplicacao.screens())
        return tuple(
            (area.x(), area.y(), area.x() + area.width(), area.y() + area.height())
            for area in (tela.availableGeometry() for tela in telas if tela is not None)
        )
    except Exception as exc:  # noqa: BLE001 - Qt sem tela, duplo de teste, offscreen exótico
        logger.info("Telas não enumeradas (%s): a geometria guardada é aplicada como veio.", exc)
        return ()
