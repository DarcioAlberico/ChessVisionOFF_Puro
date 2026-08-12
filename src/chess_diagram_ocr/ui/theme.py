"""O tema da janela (S-53, parte (a)).

`ttkbootstrap` é a única mudança de interface que a Fase 10 faz, e a razão é que ela é a
única que não fecha porta nenhuma: **mesma API de widget**, `ttk.Treeview` intacto, e todo o
código de painel continua igual. Custo de um dia, risco quase nulo.

`CustomTkinter` ficou de fora por um motivo objetivo e não estético: não tem equivalente
decente de `Treeview`, então a aba Dataset continuaria em `ttk` e a tela ficaria com dois
visuais. O porte para Qt fica adiado por **gatilho**, e os dois gatilhos estão registrados
no `ARCHITECTURE.md` -- não aqui, porque quem os procura não vai procurar num módulo de tema.

**A degradação é o contrato.** Se `ttkbootstrap` não estiver instalado, a janela abre em
`ttk` puro exatamente como antes, e o log diz isso uma vez. Um checkout sem o extra, um
bundle que não o incluiu ou um tema com nome errado não podem impedir o app de abrir --
tema é aparência, e aparência não derruba ferramenta.
"""

from __future__ import annotations

import logging
import os
import tkinter as tk

logger = logging.getLogger(__name__)

__all__ = ["DEFAULT_THEME", "apply_theme", "available_themes"]

DEFAULT_THEME = "bootstrap-light"
"""Claro, alto contraste e sóbrio.

A escolha não é gosto: o produto é ler diagrama impresso em papel branco e comparar com o
que o modelo leu. Um tema escuro põe o tabuleiro claro do `InteractiveBoard` e a página
renderizada do PDF sobre fundo preto, e o olho passa a corrigir contraste em vez de
posição. `CVOFF_TTK_THEME` troca para quem discordar -- `available_themes()` lista os 30.

É um nome da era 2.0 de propósito. Os nomes antigos (`litera`, `flatly`, ...) ainda
resolvem, mas cada abertura da janela emitiria um `DeprecationWarning`, e a biblioteca diz
que eles saem na 3.0.
"""

THEME_ENV = "CVOFF_TTK_THEME"


def available_themes() -> list[str]:
    """Nomes de tema que este ambiente aceita. Vazio quando `ttkbootstrap` não está lá."""
    try:
        import ttkbootstrap as tb
    except ImportError:
        return []
    return sorted(tb.Style().theme_names())


def apply_theme(root: tk.Misc, theme: str | None = None) -> str:
    """Aplica o tema e devolve o que de fato ficou valendo.

    Devolve o nome do tema `ttkbootstrap` em uso, ou `"ttk"` quando a biblioteca não está
    instalada. Nunca levanta: chamar isto não pode ser o motivo de a janela não abrir.
    """
    escolhido = theme or os.environ.get(THEME_ENV) or DEFAULT_THEME

    try:
        import ttkbootstrap as tb
    except ImportError:
        logger.info(
            "ttkbootstrap não está instalado: a janela abre no tema padrão do ttk. "
            "`uv sync` traz a biblioteca; nada mais muda (S-53)."
        )
        return "ttk"

    # `tb.Style` nao recebe `master`: ele se prende ao root **padrao** do Tk. Dai `root` ser
    # parametro obrigatorio desta funcao mesmo sem ser repassado -- ele documenta a
    # pre-condicao real, que e existir uma janela antes de haver tema.
    if root is None:  # pragma: no cover - guarda de chamador, não de ambiente
        raise ValueError("apply_theme precisa da janela já criada: o tema se prende ao root do Tk.")

    try:
        style = tb.Style(theme=escolhido)
    except (tk.TclError, ValueError, KeyError, AttributeError) as exc:
        logger.warning(
            "Tema %r recusado (%s). Voltando para %r. Temas disponíveis: %s",
            escolhido,
            exc,
            DEFAULT_THEME,
            ", ".join(available_themes()) or "nenhum",
        )
        try:
            style = tb.Style(theme=DEFAULT_THEME)
        except Exception:  # noqa: BLE001 - aparência não derruba a ferramenta
            logger.warning("Nem o tema padrão foi aceito: seguindo com o ttk puro.")
            return "ttk"

    nome = str(getattr(style.theme, "name", escolhido))
    logger.info("Tema da interface: %s (ttkbootstrap).", nome)
    return nome
