"""Uma raiz Tk para o **processo** inteiro, criada uma vez e nunca destruída.

**O que isto corrige, e por que o sintoma aparecia longe da causa.**

Cada módulo de teste que precisa de janela criava a sua raiz. A primeira rodada de correções
já tinha reduzido isso de "uma por teste" para "uma por módulo" (ver o histórico de
`test_result_panel` e de `test_gallery_panel`), porque no Windows **reinicializar o Tcl depois
de destruir a última raiz não é confiável**: as raízes seguintes caem em `Can't find a usable
init.tcl`. O efeito visível era um módulo inteiro *pulando*, e uma suíte verde escondendo
testes que não rodaram.

Uma raiz por módulo não bastou, e o que sobrou é pior porque **não pula, quebra**. Com dois
módulos vivos ao mesmo tempo há dois interpretadores Tcl, e `tkinter._default_root` continua
sendo o **primeiro**. Uma `ImageTk.PhotoImage` criada sem `master` nasce nesse primeiro
interpretador; o widget que vai exibi-la vive no segundo. O Tk recusa com

    _tkinter.TclError: image "pyimage145" doesn't exist

com a imagem viva e referenciada, o que faz a mensagem parecer um problema de garbage
collection e não de interpretador. Foi assim que **20 testes do `test_result_panel` falharam
na CI** passando na máquina de desenvolvimento: aqui o `test_board_palette` costumava pular
(a própria raiz dele falhava), e um módulo que pula não deixa uma segunda raiz viva para
atrapalhar o vizinho.

**A regra, então:** nenhum teste chama `tk.Tk()`. Quem precisa de janela chama `raiz()` e
pendura os widgets num `tk.Frame` próprio, destruído no `addCleanup` -- destruir *frame* é
seguro, destruir *raiz* é que não é.
"""

from __future__ import annotations

import tkinter as tk
import unittest

_RAIZ: tk.Tk | None = None


def raiz() -> tk.Tk:
    """A raiz compartilhada. Levanta `SkipTest` numa máquina sem display."""
    global _RAIZ
    if _RAIZ is None:
        try:
            _RAIZ = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - máquina sem display
            raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
        _RAIZ.withdraw()
    return _RAIZ
