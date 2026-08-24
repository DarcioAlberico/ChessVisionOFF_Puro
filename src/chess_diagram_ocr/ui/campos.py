"""Campo de caminho e campo de número: o erro que aparece ao digitar (S-168).

**Dois defeitos, e nos dois o erro chegava tarde.**

*Os três caminhos.* `Modelo (.pt)`, `CSV labels` e `Pasta samples` eram `ttk.Entry` de texto
livre — **sem botão "Procurar…"** e sem verificação de existência, num programa que usa
`filedialog` em cinco outros lugares. Um caractere errado no caminho do modelo não aparecia ali:
aparecia como falha na hora do OCR, minutos depois, com uma mensagem sobre outra coisa.

*O `Learning rate`.* Era um `ttk.Entry` ligado a um `DoubleVar`. Uma letra digitada faz o
`get()` levantar `TclError` **na hora de treinar** — não na hora de digitar. O erro sai do campo
errado, no momento errado, e o traço aponta para o treino.

**O princípio é um só: o campo sabe o que aceita, e diz na hora.** As duas decisões —
o caminho existe? o texto é um número na faixa? — são funções puras, e o widget só as mostra.

**O que este módulo não faz:** impedir de digitar. Um campo que recusa tecla é pior que um que
avisa: colar um caminho de rede que ainda vai montar, ou digitar `0.` antes de `0.001`, são
gestos legítimos que a validação por tecla quebra. Aqui o campo **aceita e informa**.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, ttk

from . import theme, tipografia, tokens

__all__ = [
    "ARQUIVO",
    "PASTA",
    "Diagnostico",
    "diagnosticar_caminho",
    "linha_de_caminho",
    "linha_de_numero",
    "numero_na_faixa",
]

ARQUIVO = "arquivo"
PASTA = "pasta"
"""O que se espera encontrar no caminho. Decide o diálogo e a mensagem, e nada mais."""


@dataclass(frozen=True)
class Diagnostico:
    """O que há para dizer sobre o valor de um campo, agora.

    `ok=True` com mensagem vazia é o caso normal e silencioso -- um campo certo não precisa de
    rótulo confirmando que está certo, e enchê-lo de "✓ ok" gasta a atenção que os errados
    precisam.
    """

    ok: bool
    mensagem: str = ""

    def __bool__(self) -> bool:
        return self.ok


def diagnosticar_caminho(texto: str, *, tipo: str = ARQUIVO, existe: Callable[[Path], bool] | None = None) -> Diagnostico:
    """O caminho serve? Pura -- `existe` é injetável, e é o que a torna testável sem disco.

    Três respostas, e as três importam por motivos diferentes: **vazio** é configuração
    incompleta, e o programa ainda nem tentou; **não existe** é o erro que hoje só aparece na
    hora do OCR; e **é do outro tipo** é o engano frequente de apontar a pasta de amostras para
    o CSV, que produz uma falha de leitura ilegível.
    """
    limpo = str(texto).strip()
    if not limpo:
        return Diagnostico(False, "não configurado")

    caminho = Path(limpo)
    if existe is None:
        def existe(alvo: Path) -> bool:
            return alvo.exists()

    if not existe(caminho):
        return Diagnostico(False, "não existe neste caminho")
    if tipo == PASTA and caminho.is_file():
        return Diagnostico(False, "é um arquivo, e aqui se espera uma pasta")
    if tipo == ARQUIVO and caminho.is_dir():
        return Diagnostico(False, "é uma pasta, e aqui se espera um arquivo")
    return Diagnostico(True)


def numero_na_faixa(texto: str, *, minimo: float, maximo: float) -> Diagnostico:
    """O texto é um número dentro da faixa? Pura, e é o que o `DoubleVar` não sabia responder.

    O `DoubleVar` só tem dois estados -- devolve um `float` ou levanta --, e levanta **onde é
    lido**. Uma letra digitada no `Learning rate` virava `TclError` dentro de `train_model`, com
    o traço apontando para o treino.
    """
    limpo = str(texto).strip().replace(",", ".")
    if not limpo:
        return Diagnostico(False, "não preenchido")
    try:
        valor = float(limpo)
    except ValueError:
        return Diagnostico(False, "não é um número")
    if not minimo <= valor <= maximo:
        return Diagnostico(False, f"fora da faixa ({minimo:g} a {maximo:g})")
    return Diagnostico(True)


# ------------------------------------------------------------------------------ os widgets


def _linha(pai: tk.Misc, rotulo: str, largura_do_rotulo: int) -> ttk.Frame:
    linha = ttk.Frame(pai)
    linha.pack(fill=tk.X, padx=8, pady=4)
    ttk.Label(linha, text=rotulo, width=largura_do_rotulo).pack(side=tk.LEFT)
    return linha


def _aviso(linha: ttk.Frame) -> ttk.Label:
    aviso = ttk.Label(linha, text="", foreground=tokens.RESERVA[tokens.PROBLEMA_TEXTO])
    aviso.pack(side=tk.RIGHT, padx=(8, 0))
    return aviso


def _vigiar(var: tk.Variable, aviso: ttk.Label, diagnostico: Callable[[str], Diagnostico]) -> None:
    """Liga o rótulo de aviso ao valor, agora e a cada mudança."""

    def atualizar(*_args: object) -> None:
        try:
            aviso.configure(text=diagnostico(str(var.get())).mensagem)
        except tk.TclError:  # pragma: no cover - rótulo destruído antes do evento
            pass

    var.trace_add("write", atualizar)
    atualizar()


def linha_de_caminho(
    pai: tk.Misc,
    rotulo: str,
    var: tk.Variable,
    *,
    tipo: str = ARQUIVO,
    largura_do_rotulo: int = 16,
    escolher: Callable[[], str] | None = None,
) -> ttk.Frame:
    """Rótulo, campo em monoespaçada, botão "Procurar…" e o aviso do que está errado (S-168).

    `escolher` existe para o teste: por padrão abre o `filedialog` do sistema, que não se pode
    dirigir de um roteiro. Injetá-lo é o que permite afirmar que o botão **grava na variável** o
    que o diálogo devolveu, sem abrir diálogo nenhum.
    """
    linha = _linha(pai, rotulo, largura_do_rotulo)
    aviso = _aviso(linha)

    def procurar() -> None:
        atual = str(var.get()).strip()
        if escolher is not None:
            escolhido = escolher()
        elif tipo == PASTA:  # pragma: no cover - diálogo do sistema
            escolhido = filedialog.askdirectory(initialdir=atual or ".", title=rotulo)
        else:  # pragma: no cover - diálogo do sistema
            escolhido = filedialog.askopenfilename(initialdir=str(Path(atual).parent) if atual else ".", title=rotulo)
        # Cancelar devolve string vazia, e apagar o caminho de quem desistiu de trocá-lo seria
        # transformar um "deixa pra lá" numa configuração perdida.
        if escolhido:
            var.set(escolhido)

    ttk.Button(linha, text="Procurar…", command=procurar).pack(side=tk.RIGHT)
    ttk.Entry(linha, textvariable=var, font=theme.fonte_atual(tipografia.DADO)).pack(
        side=tk.LEFT, fill=tk.X, expand=True
    )
    _vigiar(var, aviso, lambda texto: diagnosticar_caminho(texto, tipo=tipo))
    return linha


def linha_de_numero(
    pai: tk.Misc,
    rotulo: str,
    var: tk.Variable,
    *,
    minimo: float,
    maximo: float,
    largura_do_rotulo: int = 16,
) -> ttk.Frame:
    """Rótulo, campo e o aviso de "não é um número" **enquanto se digita** (S-168)."""
    linha = _linha(pai, rotulo, largura_do_rotulo)
    aviso = _aviso(linha)
    ttk.Entry(linha, textvariable=var, font=theme.fonte_atual(tipografia.DADO)).pack(
        side=tk.LEFT, fill=tk.X, expand=True
    )
    _vigiar(var, aviso, lambda texto: numero_na_faixa(texto, minimo=minimo, maximo=maximo))
    return linha
