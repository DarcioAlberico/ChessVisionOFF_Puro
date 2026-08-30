"""Que livros a varredura vai percorrer -- a pergunta que o botão passou a fazer antes de varrer.

**O que existia.** "Varrer o livro" só sabia varrer *o livro aberto*: sem PDF na tela o botão
recusava, e com um PDF na tela ele varria aquele e mais nenhum. Quem quisesse os outros 33 do
acervo tinha uma saída só, o `cvoff-scan --all`, que é linha de comando -- e quem trabalha na
janela não abre um terminal para pedir a mesma varredura que o botão do lado já faz.

**O que a pergunta acrescenta.** Três escopos, e o custo de cada um dito antes do clique:

* **este livro** -- o que o botão sempre fez, e continua sendo o padrão quando há PDF aberto;
* **escolher em disco** -- um ou vários `.pdf` de qualquer pasta, inclusive de fora do acervo;
* **a pasta padrão inteira** -- os `.pdf` de `PDF/`, em ordem de nome.

**Por que o "pular os já completos" só vale para mais de um livro.** Pedir *este* livro é um
pedido explícito -- depois de treinar um modelo novo é exatamente o que se quer refazer, e um
botão que respondesse "pulei, já estava completo" seria um botão quebrado. Pedir *a pasta* é
outra frase: é "varra o que falta", que é como o `cvoff-scan --all` já se comporta desde a
S-121. A regra sai daqui em uma linha (`skip_complete`) e é o worker quem a aplica, porque ler
34 índices do disco é trabalho de thread e não do laço do Tk (S-116).

O diálogo é só widget: quem decide o que fazer com a lista é o `GalleryPanel`.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, ttk

from chess_diagram_ocr.config import DEFAULT_PDF_DIR

from . import espaco, estilos, strings, tokens

__all__ = [
    "ABERTO",
    "ESCOLHER",
    "PASTA",
    "ScanScope",
    "ScanScopeDialog",
    "ask_scan_scope",
    "books_in_folder",
]

ABERTO = "aberto"
ESCOLHER = "escolher"
PASTA = "pasta"


@dataclass(frozen=True)
class ScanScope:
    """Os livros escolhidos, e de que pergunta eles vieram."""

    kind: str
    books: tuple[Path, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.books

    @property
    def skip_complete(self) -> bool:
        """Pular o livro cujo índice já está completo?

        Mais de um livro é "varra o que falta"; um livro é "varra este". Ver o cabeçalho do
        módulo -- é a única regra deste arquivo, e ela é de negócio, não de tela.
        """
        return len(self.books) > 1


def books_in_folder(directory: Path = DEFAULT_PDF_DIR) -> list[Path]:
    """Os `.pdf` da pasta, em ordem de nome. Pasta que não existe é lista vazia, e não erro.

    Ordenado pelo mesmo motivo do `cvoff-scan`: a varredura de um acervo é interrompida e
    retomada, e uma ordem estável faz "continuar de onde parou" significar alguma coisa.
    """
    pasta = Path(directory)
    if not pasta.is_dir():
        return []
    return sorted(caminho for caminho in pasta.glob("*.pdf") if caminho.is_file())


class ScanScopeDialog(tk.Toplevel):
    """Pergunta o escopo. Devolve pelo atributo `scope` depois do `wait_window`.

    `choose` existe para o teste, pela mesma razão do `campos.linha_de_caminho`: o
    `filedialog` do sistema não se dirige de um roteiro, e o que se quer afirmar é que a
    escolha vira lista de livros -- não que o Tk sabe abrir a caixa de abrir arquivo.
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        open_book: Path | None = None,
        folder: Path = DEFAULT_PDF_DIR,
        choose: Callable[[], Sequence[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._open_book = open_book
        self._folder = Path(folder)
        self._choose = choose
        self._da_pasta = books_in_folder(self._folder)
        self.scope: ScanScope | None = None
        """`None` enquanto ninguém confirmou -- e depois de fechar no X, também."""

        self.title(strings.VARRER_LIVRO)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())

        # O padrão é o que o botão sempre fez. Sem PDF aberto ele não existe, e aí o padrão é
        # a pasta -- que é a razão de o diálogo poder ser aberto sem livro nenhum na tela.
        self.kind_var = tk.StringVar(value=ABERTO if open_book is not None else PASTA)
        self._build()

    # ------------------------------------------------------------------------ construção

    def _build(self) -> None:
        corpo = ttk.Frame(self, padding=espaco.moldura())
        corpo.pack(fill=tk.BOTH, expand=True)

        ttk.Label(corpo, text="Varrer quais livros?").pack(anchor=tk.W)

        nome_aberto = self._open_book.name if self._open_book is not None else "nenhum PDF aberto"
        self.radio_aberto = ttk.Radiobutton(
            corpo,
            text=f"Este livro — {nome_aberto}",
            value=ABERTO,
            variable=self.kind_var,
            state=tk.NORMAL if self._open_book is not None else tk.DISABLED,
        )
        self.radio_aberto.pack(anchor=tk.W, pady=(espaco.folga(), 0))

        self.radio_escolher = ttk.Radiobutton(
            corpo,
            text="Escolher livro(s) em disco…",
            value=ESCOLHER,
            variable=self.kind_var,
        )
        self.radio_escolher.pack(anchor=tk.W, pady=(espaco.linha(), 0))

        self.radio_pasta = ttk.Radiobutton(
            corpo,
            text=f"Todos os livros da pasta padrão — {len(self._da_pasta)} livro(s)",
            value=PASTA,
            variable=self.kind_var,
            state=tk.NORMAL if self._da_pasta else tk.DISABLED,
        )
        self.radio_pasta.pack(anchor=tk.W, pady=(espaco.linha(), 0))

        # O caminho da pasta e a regra do "pula os completos" ficam na tela, e não num tooltip:
        # são as duas coisas que decidem se o clique custa minutos ou horas.
        secundario = tokens.cor(tokens.TEXTO_SECUNDARIO)
        # 22 e recuo e nao vao: ele alinha este rotulo sob o **texto** do `Checkbutton` de
        # cima, entao depende da largura do indicador, e nao da escala de folga (S-447).
        ttk.Label(corpo, text=str(self._folder), foreground=secundario).pack(anchor=tk.W, padx=(22, 0))
        ttk.Label(
            corpo,
            text=(
                "Com mais de um livro, os que já têm índice completo são pulados —\n"
                "varrer de novo custa a leitura inteira e não acrescenta diagrama."
            ),
            foreground=secundario,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(espaco.folga(), 0))

        rodape = ttk.Frame(corpo)
        rodape.pack(fill=tk.X, pady=(espaco.moldura(), 0))
        self.btn_ok = ttk.Button(rodape, text="Varrer", command=self.confirm, style=estilos.estilo_de_botao(estilos.NEUTRO))
        self.btn_ok.pack(side=tk.RIGHT)
        ttk.Button(
            rodape,
            text="Cancelar",
            command=self.cancel,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.RIGHT, padx=espaco.linha())

        self.bind("<Return>", lambda _evento: self.confirm())
        self.bind("<Escape>", lambda _evento: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.btn_ok.focus_set()

    # ------------------------------------------------------------------------ decisão

    def _escolher_em_disco(self) -> list[Path]:
        if self._choose is not None:
            escolhidos = self._choose()
        else:  # pragma: no cover - diálogo do sistema
            inicial = self._open_book.parent if self._open_book is not None else self._folder
            escolhidos = filedialog.askopenfilenames(
                parent=self,
                title="Livros a varrer",
                filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
                initialdir=str(inicial),
            )
        return [Path(caminho) for caminho in escolhidos or ()]

    def confirm(self) -> None:
        """Fecha com a escolha feita -- exceto se o seletor de arquivos foi cancelado.

        Cancelar a caixa de abrir arquivo é "escolhi errado", e não "desisti de varrer": o
        diálogo continua aberto para a pessoa marcar outro escopo, que é o que ela ia querer
        fazer de qualquer jeito.
        """
        tipo = self.kind_var.get()
        if tipo == ABERTO:
            livros = [self._open_book] if self._open_book is not None else []
        elif tipo == ESCOLHER:
            livros = self._escolher_em_disco()
            if not livros:
                return
        else:
            livros = list(self._da_pasta)

        self.scope = ScanScope(kind=tipo, books=tuple(livros))
        self.destroy()

    def cancel(self) -> None:
        self.scope = None
        self.destroy()


def ask_scan_scope(
    parent: tk.Misc,
    *,
    open_book: Path | None = None,
    folder: Path = DEFAULT_PDF_DIR,
    choose: Callable[[], Sequence[str]] | None = None,
) -> ScanScope | None:
    """Abre o diálogo modal e devolve o escopo, ou `None` se a pessoa desistiu."""
    dialogo = ScanScopeDialog(parent, open_book=open_book, folder=folder, choose=choose)
    dialogo.grab_set()
    dialogo.wait_window()
    return dialogo.scope
