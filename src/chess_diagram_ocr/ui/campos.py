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

from . import espaco, estilos, theme, tipografia, tokens

__all__ = [
    "ARQUIVO",
    "CAMINHO",
    "LARGURA_DE_CAMPO",
    "NUMERO",
    "PASTA",
    "TEXTO",
    "Diagnostico",
    "diagnosticar_caminho",
    "largura_de_rotulo",
    "linha_de_caminho",
    "linha_de_giro",
    "linha_de_numero",
    "numero_na_faixa",
]

ARQUIVO = "arquivo"
PASTA = "pasta"
"""O que se espera encontrar no caminho. Decide o diálogo e a mensagem, e nada mais."""

NUMERO = "numero"
TEXTO = "texto"
CAMINHO = "caminho"
"""A **classe de dado** do campo, e é ela que decide a largura (S-448).

O defeito que isto fecha estava na aba Configuração e é mensurável: o campo mais largo do painel
(≈590 px) era o que guardava o valor mais curto (`0.001`), porque `linha_de_numero` pedia
`expand=True` e comia toda a sobra; ao lado dele, "Épocas" (`8`) e "Tamanho do lote" (`128`) tinham
≈100 px porque eram `ttk.Spinbox(width=12)`. A largura não dizia nada sobre o dado que o campo
espera -- e largura é a primeira dica que um formulário dá.
"""

LARGURA_DE_CAMPO: dict[str, int] = {NUMERO: 12, TEXTO: 28, CAMINHO: 0}
"""Largura em **caracteres** por classe. `0` quer dizer "ocupa a sobra da linha".

Cresce com a classe -- número < texto < caminho --, que é a ordem em que o dado cresce. O caminho
é o único que expande, e ele é o único cujo conteúdo não tem tamanho previsível: `C:\\Users\\...`
não cabe em número nenhum que se escolha aqui."""


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


def largura_de_rotulo(*rotulos: str) -> int:
    """Quantos caracteres a coluna de rótulo precisa para não cortar nenhum deles. Pura.

    **O defeito que isto fecha corta letra na tela.** `largura_do_rotulo` era `16` cravado, e
    "Taxa de aprendizado" tem **19** caracteres: o Tk desenhava `Taxa de aprendizad` e o resto
    sumia dentro do campo ao lado. Não era caso de borda -- era o rótulo mais longo do único
    formulário do programa.

    Quem chama passa **todos** os rótulos do formulário de uma vez, e é isso que faz a segunda
    metade do critério valer por construção: se todos recebem a mesma coluna, todos os campos
    começam na mesma coluna.

    O piso de 1 existe porque `ttk.Label(width=0)` não reserva coluna nenhuma, e um formulário sem
    rótulo nenhum é chamada errada, não formulário estreito.
    """
    return max((len(rotulo) for rotulo in rotulos), default=1) or 1


def _linha(pai: tk.Misc, rotulo: str, largura_do_rotulo: int) -> ttk.Frame:
    linha = ttk.Frame(pai)
    linha.pack(fill=tk.X, padx=espaco.folga(), pady=espaco.linha())
    ttk.Label(linha, text=rotulo, width=largura_do_rotulo).pack(side=tk.LEFT)
    return linha


def _aviso(linha: ttk.Frame) -> ttk.Label:
    aviso = theme.pintar(ttk.Label(linha, text=""), "foreground", tokens.PROBLEMA_TEXTO)
    aviso.pack(side=tk.RIGHT, padx=(espaco.folga(), 0))
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

    ttk.Button(linha, text="Procurar…", command=procurar, style=estilos.estilo_de_botao(estilos.NEUTRO)).pack(side=tk.RIGHT)
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
    # **Sem `expand=True`, e é o item** (S-448). Expandindo, este campo ficava com ≈590 px para
    # guardar `0.001` -- o mais largo do painel para o valor mais curto dele. E a fonte é a de
    # corpo e não a `DADO`: os vizinhos de número são `ttk.Spinbox`, que desenham na fonte de
    # corpo, e dois números do mesmo formulário em fontes diferentes é o que a fotografia mostrou.
    ttk.Entry(linha, textvariable=var, width=LARGURA_DE_CAMPO[NUMERO]).pack(side=tk.LEFT)
    _vigiar(var, aviso, lambda texto: numero_na_faixa(texto, minimo=minimo, maximo=maximo))
    return linha


def linha_de_giro(
    pai: tk.Misc,
    rotulo: str,
    var: tk.Variable,
    *,
    minimo: float,
    maximo: float,
    passo: float,
    largura_do_rotulo: int = 16,
) -> ttk.Frame:
    """Rótulo e `ttk.Spinbox`, na mesma coluna e na mesma largura de `linha_de_numero` (S-448).

    **Era o `_spin_row` do `app_tkinter`**, e ser uma segunda implementação da mesma linha era o
    defeito: ela cravava `width=16` no rótulo e `width=12` no campo por conta própria, então
    mudar a coluna de rótulo num lugar não mudava no outro. É o mesmo argumento de
    `theme.altura_de_linha_atual` sobre as duas tabelas (S-153) -- duas cópias erram a mesma
    coisa em momentos diferentes.
    """
    linha = _linha(pai, rotulo, largura_do_rotulo)
    ttk.Spinbox(
        linha,
        from_=minimo,
        to=maximo,
        increment=passo,
        textvariable=var,
        width=LARGURA_DE_CAMPO[NUMERO],
    ).pack(side=tk.LEFT)
    return linha
