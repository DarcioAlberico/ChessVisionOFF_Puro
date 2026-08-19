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
from tkinter import ttk

from . import tipografia, tokens

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_THEME",
    "apply_theme",
    "available_themes",
    "cor_atual",
    "estilo_atual",
    "fonte_atual",
    "fonte_base",
]

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
    # Depois do tema, e dentro desta função de propósito (S-149): estilo declarado antes é
    # sobrescrito pelo tema, e deixar a ordem a cargo do chamador é o tipo de dependência
    # invisível que produz "funciona aqui e não lá". Aplicar o tema é aplicá-lo inteiro.
    registrar_estilos()
    return nome


# ------------------------------------------------------------------ a ponte com os tokens


def estilo_atual() -> ttk.Style | None:
    """O `Style` que a janela está usando agora, ou `None` se não houver janela.

    Existe porque `ui/tokens.py` não importa `tkinter` — é o que permite afirmar a paleta
    inteira sem abrir janela — e alguém precisa levar o `Style` até lá. Este módulo já é o que
    sabe de tema, então a ponte mora aqui e não num painel.

    `ttk.Style()` se prende ao root **padrão** do Tk; sem root ele levanta, e um painel que
    pergunta a cor antes de existir janela é erro de ordem, não de tema.
    """
    try:
        return ttk.Style()
    except (tk.TclError, RuntimeError):  # pragma: no cover - sem root: cai na reserva
        return None


def cor_atual(papel: str) -> str:
    """Um papel da S-145 resolvido contra o tema em uso (S-147).

    É o que os painéis chamam. Sem janela, sem `ttkbootstrap` ou com um `Style` que não
    responde, devolve a reserva clara — o mesmo contrato de degradação do resto do módulo.

    Papel desconhecido **levanta**, e isso é de propósito: a tolerância aqui é a tema ausente,
    não a papel escrito errado (ver `tokens.cor`).
    """
    return tokens.cor(papel, estilo_atual())


FAMILIA_DE_RESERVA = ("Segoe UI", "Consolas")
"""Família proporcional e monoespaçada de quando o Tk não responde.

São as duas que a janela já usava cravadas, e ficam aqui como **último** recurso: o caminho
normal é perguntar à `TkDefaultFont` e à `TkFixedFont`, que é o que faz a escala acompanhar a
configuração de fonte do Windows em vez de ignorá-la."""


def fonte_base() -> tuple[int, str, str]:
    """`(tamanho, família proporcional, família monoespaçada)` do sistema (S-149).

    Lidas da `TkDefaultFont` e da `TkFixedFont`, que é o que o Tk expõe da configuração do
    sistema. **É daqui que a escala inteira deriva**: quem aumenta a fonte do Windows aumenta a
    do programa, e uma escala de números fixos ignoraria isso.

    O tamanho vem negativo quando o Tk o expressa em pixels em vez de pontos; o sinal some
    porque a escala só precisa da magnitude, e um `-9` cravado num `font=` desenha do mesmo
    tamanho que `9` em quase toda tela.
    """
    tamanho, proporcional, monoespacada = 9, *FAMILIA_DE_RESERVA
    try:
        from tkinter import font as tkfont

        padrao = tkfont.nametofont("TkDefaultFont")
        tamanho = abs(int(padrao.cget("size"))) or tamanho
        proporcional = str(padrao.cget("family") or proporcional)
        do_tk = str(tkfont.nametofont("TkFixedFont").cget("family") or monoespacada)
        monoespacada = tipografia.familia_monoespacada(tkfont.families(), do_tk)
    except Exception as exc:  # noqa: BLE001 - sem root, sem Tk ou fonte exótica: a reserva serve
        logger.debug("Fonte do sistema não lida (%s): usando %s.", exc, FAMILIA_DE_RESERVA)
    return tamanho, proporcional, monoespacada


def fonte_atual(papel: str, *, negrito: bool = False) -> tuple[str, int] | tuple[str, int, str]:
    """Um papel da S-149 resolvido contra a fonte do sistema. É o que os painéis chamam.

    Como `cor_atual`: tolerante a ambiente, intolerante a papel escrito errado.
    """
    tamanho, proporcional, monoespacada = fonte_base()
    return tipografia.fonte(papel, base=tamanho, familia=proporcional, mono=monoespacada, negrito=negrito)


ESTILO_DE_TABELA_DE_DADOS = "Dado.Treeview"
"""Nome do estilo de `Treeview` cujo corpo é monoespaçado. Pedido por quem quer, e são poucos."""

ESTILO_DE_TITULO = "TLabelframe.Label"
"""O rótulo de `LabelFrame`, **sem** prefixo: todo `LabelFrame` desta janela é título de grupo.

Um estilo nomeado exigiria `style=` nos 20 e poucos grupos da janela, e o primeiro que alguém
esquecesse voltaria ao corpo sem nada avisar. Redefinir o padrão faz a escala valer por
construção -- e se um dia existir um `LabelFrame` que não seja título, ele é que pede o
prefixo."""


def registrar_estilos() -> None:
    """Declara no `Style` os papéis que só um estilo nomeado alcança (S-149). Nunca levanta.

    **Por que dois deles não cabem num `font=` de widget.**

    `ttk.Treeview` aplica a fonte à tabela inteira: não existe fonte por coluna. A coluna que
    pede monoespaçada é a de FEN, e a do Dataset é uma tabela de **dados** de ponta a ponta --
    arquivo, FEN, livro, data. Aplicar ao corpo inteiro é a leitura certa desse painel; a fila
    de Revisão, cuja coluna larga é prosa ("Motivo"), fica de fora de propósito.

    `LabelFrame` desenha o próprio rótulo por um sub-estilo, e um `font=` no construtor do
    widget não o alcança.

    Chamada pelo próprio `apply_theme`, no fim: estilo declarado antes do tema é sobrescrito
    por ele. Pública porque o teste a chama direto, e porque trocar de tema em execução — o que
    `CVOFF_TTK_THEME` permite entre execuções e um menu de preferências vai permitir dentro de
    uma — precisa reaplicá-la.
    """
    style = estilo_atual()
    if style is None:  # pragma: no cover - sem root não há estilo a registrar
        return
    try:
        style.configure(ESTILO_DE_TABELA_DE_DADOS, font=fonte_atual(tipografia.DADO))
        style.configure(ESTILO_DE_TITULO, font=fonte_atual(tipografia.TITULO))
    except tk.TclError as exc:  # pragma: no cover - Style exótico: a janela abre sem a escala
        logger.info("Estilos de tipografia não registrados (%s).", exc)
