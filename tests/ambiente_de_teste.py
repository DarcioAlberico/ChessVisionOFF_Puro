"""O que um teste desta suíte precisa criar, e o que ele tem de devolver (S-415).

**O que estava acontecendo.** Cada rodada da suíte abandonava mais de cem diretórios em `%TEMP%`
-- `tempfile.mkdtemp()` sem `rmtree` em 24 lugares -- e pendurava 99 painéis na mesma raiz Tk,
nenhum destruído. Nada disso quebra um teste: quebra a **máquina de quem roda a suíte**, aos
poucos, e nunca aparece num relatório vermelho. É a mesma classe do `tests/tk_root.py`: uma regra
que só existia escrita, e por isso valia enquanto alguém lembrava.

**As duas funções aqui são a regra em forma executável**, e `tests/test_disciplina_da_suite.py` é
quem cobra que elas sejam usadas: `mkdtemp` só mora aqui, e widget de teste não pendura na raiz.
"""

from __future__ import annotations

import shutil
import tempfile
import tkinter as tk
import unittest
from pathlib import Path


def pasta_temporaria(caso: unittest.TestCase, *, prefixo: str = "cvoff-teste-") -> Path:
    """Uma pasta temporária que morre com o teste que a pediu.

    `ignore_errors=True` porque no Windows um arquivo ainda aberto -- um `.pt` sendo lido, um log
    com handler vivo -- impede a remoção, e falhar a limpeza reprovaria um teste que passou. Ver
    o mesmo raciocínio em `tests/test_logging_setup.py`.
    """
    pasta = Path(tempfile.mkdtemp(prefix=prefixo))
    caso.addCleanup(shutil.rmtree, pasta, True)
    return pasta


def pasta_temporaria_da_classe(caso: type[unittest.TestCase], *, prefixo: str = "cvoff-teste-") -> Path:
    """A mesma coisa para o que nasce no `setUpClass`, que não tem instância para limpar.

    `addClassCleanup` é o par de `addCleanup` do lado da classe, e existe desde o Python 3.8. Sem
    ele, um artefato criado uma vez por classe -- o lançador do motor de mentira, por exemplo --
    ficaria em `%TEMP%` para sempre, que é exatamente o que a S-415 mediu.
    """
    pasta = Path(tempfile.mkdtemp(prefix=prefixo))
    caso.addClassCleanup(shutil.rmtree, pasta, True)
    return pasta


def quadro(caso: unittest.TestCase, raiz: tk.Misc) -> tk.Frame:
    """Um `Frame` próprio, destruído no fim do teste -- e é ele que hospeda os widgets.

    **Pendurar na raiz é o defeito** (S-415): a raiz é do processo inteiro (`tests/tk_root.py`) e
    sobrevive a todos os módulos, então um painel criado nela vive até o fim da suíte. Noventa e
    nove `TextoPanel` vivos ao mesmo tempo não é só memória: cada um tem `after` agendado, ligações
    de tecla e um `Text` com `edit_separator` -- e o `bind_all` de um alcança o evento do outro.

    Destruir **quadro** é seguro; destruir raiz é que não é, e o porquê está no `tk_root`.
    """
    filho = tk.Frame(raiz)
    caso.addCleanup(filho.destroy)
    return filho
