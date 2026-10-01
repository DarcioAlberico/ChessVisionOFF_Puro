"""A aba **Revisão de texto**: a janela de revisão dos spans duvidosos da suíte (SOL-11).

**O painel não mora aqui.** Ele é `caissa.ui.views.revisao_de_texto.PainelDeRevisaoDeTexto`,
da suíte (`Suite_de_Edicao_de_Xadrez`, OCR_UI_ROADMAP passo 14), escrito contra o mesmo PyQt6
e com a mesma regra deste pacote -- o toolkit pinta, as decisões ficam em módulos sem toolkit
(`caissa.ocr.review`). O que este arquivo faz é o que só o tronco pode fazer: dizer se a suíte
está ao alcance e, se estiver, dar o painel à janela -- o mesmo desenho de
`qt/painel_de_rotulagem.py`, e pela mesma razão.

**Por que uma aba e não um modo da Revisão.** A aba *Revisão* deste pacote é a fila de
**diagramas** (S-22): posição lida, confiança mínima, motivo. A revisão de **texto** é outra
fila -- regiões de OCR com leitura, alternativas e três ações que gravam texto no IR -- e
outra unidade de trabalho (o livro importado, não o diagrama clicado). Pôr as duas na mesma
aba seria um interruptor de modo que a S-162 já mediu como o pior lugar para esconder trabalho.
"""

from __future__ import annotations

import getpass
import logging

from PyQt6.QtWidgets import QWidget

__all__ = ["comandos", "disponivel", "montar"]

logger = logging.getLogger(__name__)


def disponivel() -> bool:
    """Se a suíte está importável daqui -- é o que decide se a aba existe."""
    try:
        import caissa.ui.views.revisao_de_texto  # noqa: F401 - só a pergunta "existe?"
    except Exception:  # noqa: BLE001 - ImportError, SyntaxError num Python antigo, tudo é "não"
        return False
    return True


def montar(parent: QWidget) -> QWidget | None:
    """O painel da suíte, ou `None` com o motivo no log."""
    try:
        from caissa.ui.views.revisao_de_texto import PainelDeRevisaoDeTexto
    except Exception as exc:  # noqa: BLE001 - ver o cabeçalho
        logger.info("aba Revisão de texto ausente: a suíte não está ao alcance (%s).", exc)
        return None
    try:
        revisor = getpass.getuser()
    except Exception:  # noqa: BLE001 - sem usuário do sistema, a trilha fica sem nome
        revisor = ""
    try:
        return PainelDeRevisaoDeTexto(parent, revisor=revisor)
    except Exception:
        logger.exception("a aba Revisão de texto não pôde ser montada; a janela segue sem ela.")
        return None


def comandos() -> dict[str, str]:
    """A tabela ``comando -> método`` que a aba declara (passo C8), ou ``{}`` sem a suíte.

    O molde é `ui/sala_declarada.COMANDOS_DA_ABA`: a janela gera as ligações a partir dela, e o
    comando chega ao menu, à paleta e às teclas sem uma segunda declaração. Os nomes estão no
    catálogo (`ui/comandos.py`) sempre -- com ou sem a suíte, para o menu ser o mesmo -- e sem a
    aba o dono é a frase de ausência.
    """
    try:
        from caissa.ui.views.declarados import COMANDOS_DA_REVISAO_DE_TEXTO
    except Exception:  # noqa: BLE001 - sem a suíte não há aba, e o catálogo continua o mesmo
        return {}
    return dict(COMANDOS_DA_REVISAO_DE_TEXTO)
