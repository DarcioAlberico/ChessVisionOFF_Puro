"""A aba **Rotulagem**: a bancada de rotulagem e treino por livro da suíte, dentro desta janela.

**O painel não mora aqui.** Ele é `caissa.ui.views.rotulagem.PainelDeRotulagem`, da suíte
(`Suite_de_Edicao_de_Xadrez`), escrito contra o mesmo PyQt6 e com a mesma regra deste
pacote -- o toolkit pinta, as decisões ficam em módulos sem toolkit (`caissa.ocr.labeling`,
`caissa.ocr.training`). O que este arquivo faz é o que só o tronco pode fazer: dizer se a suíte
está ao alcance e, se estiver, dar o painel à janela.

**Por que a importação é guardada.** Num checkout do tronco a suíte é um repositório vizinho e
não um pacote instalado -- e ela exige Python 3.11, que o `.venv` deste repositório não é. No
bundle (`Suite_de_Edicao_de_Xadrez/packaging/caissa.spec`) os dois pacotes moram no mesmo
arquivo compilado e a aba existe sempre. Sem a suíte a janela sobe com as seis abas de antes,
e o motivo fica no log -- nunca uma janela que não abre por causa de uma aba.
"""

from __future__ import annotations

import getpass
import logging

from PyQt6.QtWidgets import QWidget

__all__ = ["comandos", "disponivel", "montar"]

logger = logging.getLogger(__name__)


def disponivel() -> bool:
    """Se a suíte está importável daqui -- é o que decide se a sétima aba existe."""
    try:
        import caissa.ui.views.rotulagem  # noqa: F401 - só a pergunta "existe?"
    except Exception:  # noqa: BLE001 - ImportError, SyntaxError num Python antigo, tudo é "não"
        return False
    return True


def montar(parent: QWidget) -> QWidget | None:
    """O painel da suíte, ou `None` com o motivo no log."""
    try:
        from caissa.ui.views.rotulagem import PainelDeRotulagem
    except Exception as exc:  # noqa: BLE001 - ver o cabeçalho
        logger.info("aba Rotulagem ausente: a suíte não está ao alcance (%s).", exc)
        return None
    try:
        revisor = getpass.getuser()
    except Exception:  # noqa: BLE001 - sem usuário do sistema, o projeto pede o nome depois
        revisor = ""
    try:
        return PainelDeRotulagem(parent, revisor=revisor)
    except Exception:
        logger.exception("a aba Rotulagem não pôde ser montada; a janela segue sem ela.")
        return None


def comandos() -> dict[str, str]:
    """A tabela ``comando -> método`` que a aba declara (passo C8), ou ``{}`` sem a suíte.

    O molde é `ui/sala_declarada.COMANDOS_DA_ABA`: a janela gera as ligações a partir dela, e o
    comando chega ao menu, à paleta e às teclas sem uma segunda declaração. Os nomes estão no
    catálogo (`ui/comandos.py`) sempre -- com ou sem a suíte, para o menu ser o mesmo -- e sem a
    aba o dono é a frase de ausência.
    """
    try:
        from caissa.ui.views.declarados import COMANDOS_DA_ROTULAGEM
    except Exception:  # noqa: BLE001 - sem a suíte não há aba, e o catálogo continua o mesmo
        return {}
    return dict(COMANDOS_DA_ROTULAGEM)
