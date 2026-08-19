"""Qual base de partidas usar -- a pergunta que as duas buscas passaram a fazer antes de abrir 19 GB.

**O que existia.** As duas buscas da Galeria chamavam `database_paths()` e pronto: *todos* os
`.pgn` de `pgn_database/`, sempre, sem dizer quais nem quanto. Foi a decisão certa da S-93 --
a partida procurada costuma estar justamente no arquivo que ficava de fora --, mas ela tirou da
pessoa a única escolha que a passada de meia hora por gigabase tem: **contra o que perguntar**.

**O que a pergunta acrescenta.** A lista dos `.pgn` com o tamanho de cada um, todos marcados
(o comportamento de sempre), mais um botão para trazer um `.pgn` de fora da pasta. Desmarcar
uma base de 10 GB é a diferença entre uma busca de minutos e uma de horas.

**A parte que não é cosmética: o cache.** O cache de posições (`games_cache`) vale para *um
conjunto de bases* -- a contagem de partidas de uma posição muda quando um `.pgn` entra, e é a
contagem que autoriza preencher um header (S-74). Por isso a guarda descarta tudo quando o
conjunto muda. Duas consequências, e este módulo cuida das duas:

* **cada conjunto tem o seu arquivo de cache** (`store_path_for`). Sem isso, experimentar uma
  base sozinha apagaria as respostas do acervo inteiro, e voltar apagaria as da experiência --
  ~56 min medidos de cada lado, por um clique reversível;
* **o custo é dito antes do clique** (`cache_note`), lido sem abrir o cache para escrita: quem
  pergunta o que perderia não pode descobrir perdendo.

**O índice por nome não segue a escolha, e não precisa seguir.** O `games_index` grava *em que
arquivo* cada partida mora, e o número é a posição na lista de bases (ver `database_paths`);
com um subconjunto, os offsets dele apontariam para o arquivo errado. Ele já se defende
sozinho -- `lookup_pair` confere o fingerprint e devolve vazio quando não bate --, então o
efeito de escolher um subconjunto é o atalho da lista de candidatas ficar mudo, e não responder
errado. As duas buscas continuam inteiras: elas leem os `.pgn`, não o índice.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import filedialog, ttk

from chess_diagram_ocr.games_cache import (
    DEFAULT_STORE_PATH,
    database_fingerprint,
    same_database,
    stored_summary,
)
from chess_diagram_ocr.games_db import DEFAULT_DATABASE_DIR, database_paths

from . import texto, tokens
from .tooltip import Tooltip

__all__ = [
    "DatabaseDialog",
    "ask_databases",
    "cache_note",
    "describe_size",
    "store_path_for",
]


def describe_size(caminho: Path) -> str:
    """O tamanho do arquivo como quem vai esperar por ele o lê: `8,6 GB`, `62 MB`."""
    try:
        bytes_ = caminho.stat().st_size
    except OSError:
        return "ausente"
    if bytes_ >= 1_000_000_000:
        return f"{bytes_ / 1e9:.1f} GB".replace(".", ",")
    if bytes_ >= 1_000_000:
        return f"{bytes_ / 1e6:.0f} MB"
    return f"{bytes_ / 1e3:.0f} kB"


def _mesmo_conjunto(um: Sequence[Path], outro: Sequence[Path]) -> bool:
    return sorted(caminho.name.lower() for caminho in um) == sorted(caminho.name.lower() for caminho in outro)


def store_path_for(
    bases: Sequence[Path],
    *,
    default_bases: Sequence[Path] | None = None,
    default_path: Path = DEFAULT_STORE_PATH,
) -> Path:
    """Onde mora o cache **deste** conjunto de bases.

    A pasta inteira continua no arquivo de sempre -- é o conjunto que o `cvoff-games` usa, e
    mudar o caminho dele deixaria a linha de comando e a janela com dois caches que não se
    enxergam. Qualquer outro conjunto ganha um arquivo vizinho, nomeado pelos arquivos que o
    compõem.

    **O nome sai dos nomes, e não do fingerprint.** Tamanho entra na guarda de dentro do cache
    (é ela que descarta quando um `.pgn` cresce); se entrasse também no caminho, um arquivo que
    crescesse viraria um cache novo e abandonaria o anterior no disco sem ninguém para apagá-lo.
    """
    padrao = list(default_bases) if default_bases is not None else database_paths()
    alvo = Path(default_path)
    if not bases or _mesmo_conjunto(bases, padrao):
        return alvo
    # Um nome legível vale mais que um hash: quem abrir `data/` precisa saber o que apagar.
    marca = "-".join(sorted(Path(base).stem[:12].replace(" ", "_") for base in bases))
    return alvo.with_name(f"{alvo.stem}__{marca[:60]}{alvo.suffix}")


def cache_note(bases: Sequence[Path], *, store_path: Path | None = None) -> str:
    """O que o cache deste conjunto tem hoje, e o que a próxima busca fará com ele.

    Lê o cache **em modo leitura** (`stored_summary`): abrir pela porta normal já descartaria o
    que esta frase existe para avisar que vai ser descartado.
    """
    if not bases:
        return "Nenhuma base marcada: as buscas não têm onde procurar."
    caminho = store_path if store_path is not None else store_path_for(bases)
    marca, linhas = stored_summary(caminho)
    if not linhas:
        return "Sem respostas guardadas para este conjunto: a primeira busca por posição lê os arquivos inteiros."
    if same_database(marca, database_fingerprint(bases)):
        return f"{linhas} posição(ões) já respondidas continuam valendo — a busca só pergunta o que faltar."
    return (
        f"As {linhas} posição(ões) guardadas foram respondidas por outro conjunto de arquivos e "
        "serão descartadas na próxima busca por posição: a contagem de uma base não vale para outra."
    )


class DatabaseDialog(tk.Toplevel):
    """A lista de `.pgn` com caixas de marcar. Devolve pelo atributo `chosen` após `wait_window`.

    `choose` e `note` existem para o teste: o `filedialog` do sistema não se dirige de um
    roteiro, e a frase do cache depende de um arquivo SQLite que um teste de widget não deveria
    ter de montar.
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        selected: Sequence[Path] | None = None,
        folder: Path = DEFAULT_DATABASE_DIR,
        choose: Callable[[], Sequence[str]] | None = None,
        note: Callable[[Sequence[Path]], str] = cache_note,
    ) -> None:
        super().__init__(parent)
        self._folder = Path(folder)
        self._choose = choose
        self._note = note
        self.chosen: tuple[Path, ...] | None = None
        """`None` enquanto ninguém confirmou -- e depois de cancelar, também."""

        # A pasta primeiro, e o que veio de fora depois: a ordem da pasta é a identidade que o
        # indice por nome usa (ver `database_paths`), e embaralhá-la aqui confundiria a leitura.
        da_pasta = database_paths(self._folder)
        marcados = list(selected) if selected is not None else list(da_pasta)
        de_fora = [caminho for caminho in marcados if not any(_mesmo(caminho, outro) for outro in da_pasta)]
        self._bases: list[Path] = [*da_pasta, *de_fora]
        self._marcas: dict[str, tk.BooleanVar] = {
            str(base): tk.BooleanVar(value=any(_mesmo(base, escolhido) for escolhido in marcados))
            for base in self._bases
        }

        self.title("Base de partidas")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.note_var = tk.StringVar(value="")
        self.total_var = tk.StringVar(value="")
        self._build()
        self._atualizar()

    # ------------------------------------------------------------------------ construção

    def _build(self) -> None:
        corpo = ttk.Frame(self, padding=12)
        corpo.pack(fill=tk.BOTH, expand=True)
        ttk.Label(corpo, text="Procurar em quais bases?").pack(anchor=tk.W)

        self.lista = ttk.Frame(corpo)
        self.lista.pack(anchor=tk.W, pady=(8, 0))
        self._desenhar_lista()

        secundario = tokens.cor(tokens.TEXTO_SECUNDARIO)
        ttk.Label(corpo, text=str(self._folder), foreground=secundario).pack(anchor=tk.W, pady=(6, 0))

        botoes = ttk.Frame(corpo)
        botoes.pack(anchor=tk.W, pady=(8, 0))
        ttk.Button(botoes, text="Marcar todas", command=lambda: self._marcar(True)).pack(side=tk.LEFT)
        ttk.Button(botoes, text="Desmarcar todas", command=lambda: self._marcar(False)).pack(side=tk.LEFT, padx=6)
        ttk.Button(botoes, text="Adicionar .pgn de outra pasta…", command=self.add_from_disk).pack(side=tk.LEFT)

        ttk.Label(corpo, textvariable=self.total_var, foreground=secundario).pack(anchor=tk.W, pady=(10, 0))
        # A frase do cache é o que decide entre "clico agora" e "hoje não": ela diz se a busca
        # custa minutos ou se descarta ~56 min de respostas já pagas.
        texto.acompanhar(
            ttk.Label(corpo, textvariable=self.note_var, foreground=secundario, justify=tk.LEFT)
        ).pack(anchor=tk.W, pady=(4, 0))

        rodape = ttk.Frame(corpo)
        rodape.pack(fill=tk.X, pady=(14, 0))
        self.btn_ok = ttk.Button(rodape, text="Procurar", command=self.confirm)
        self.btn_ok.pack(side=tk.RIGHT)
        Tooltip(
            self.btn_ok,
            "Fica cinza enquanto nenhuma base estiver marcada:\n"
            "a busca precisa de pelo menos um .pgn para ter onde procurar.",
        )
        ttk.Button(rodape, text="Cancelar", command=self.cancel).pack(side=tk.RIGHT, padx=6)

        self.bind("<Return>", lambda _evento: self.confirm())
        self.bind("<Escape>", lambda _evento: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.btn_ok.focus_set()

    def _desenhar_lista(self) -> None:
        for filho in self.lista.winfo_children():
            filho.destroy()
        for base in self._bases:
            linha = ttk.Frame(self.lista)
            linha.pack(anchor=tk.W, fill=tk.X)
            ttk.Checkbutton(
                linha, text=base.name, variable=self._marcas[str(base)], command=self._atualizar
            ).pack(side=tk.LEFT)
            ttk.Label(linha, text=f"  {describe_size(base)}", foreground=tokens.cor(tokens.TEXTO_SECUNDARIO)).pack(
                side=tk.LEFT
            )

    # ------------------------------------------------------------------------ decisão

    @property
    def selection(self) -> tuple[Path, ...]:
        return tuple(base for base in self._bases if self._marcas[str(base)].get())

    def _marcar(self, valor: bool) -> None:
        for marca in self._marcas.values():
            marca.set(valor)
        self._atualizar()

    def _atualizar(self) -> None:
        escolhidas = self.selection
        bytes_ = 0
        for base in escolhidas:
            try:
                bytes_ += base.stat().st_size
            except OSError:
                pass
        total = f"{bytes_ / 1e9:.1f} GB".replace(".", ",")
        self.total_var.set(f"{len(escolhidas)} base(s) marcada(s), {total} no total.")
        self.note_var.set(self._note(escolhidas))
        self.btn_ok.configure(state=tk.NORMAL if escolhidas else tk.DISABLED)

    def add_from_disk(self) -> None:
        """Traz `.pgn` de fora da pasta padrão, já marcados. Repetir um que já está na lista é nada."""
        if self._choose is not None:
            escolhidos = self._choose()
        else:  # pragma: no cover - diálogo do sistema
            escolhidos = filedialog.askopenfilenames(
                parent=self,
                title="Bases de partidas",
                filetypes=[("PGN", "*.pgn"), ("Todos", "*.*")],
                initialdir=str(self._folder),
            )
        for bruto in escolhidos or ():
            caminho = Path(bruto)
            ja = next((base for base in self._bases if _mesmo(base, caminho)), None)
            if ja is not None:
                self._marcas[str(ja)].set(True)
                continue
            self._bases.append(caminho)
            self._marcas[str(caminho)] = tk.BooleanVar(value=True)
        self._desenhar_lista()
        self._atualizar()

    def confirm(self) -> None:
        escolhidas = self.selection
        if not escolhidas:
            # O botão já está cinza; o `<Return>` chegaria aqui de qualquer jeito.
            return
        self.chosen = escolhidas
        self.destroy()

    def cancel(self) -> None:
        self.chosen = None
        self.destroy()


def _mesmo(um: Path, outro: Path) -> bool:
    """O mesmo `.pgn`, apesar da grafia do caminho. Sem `resolve`: 19 GB não mudam de lugar,
    e o que interessa aqui é não listar o mesmo arquivo duas vezes."""
    try:
        return um.resolve() == outro.resolve()
    except OSError:  # pragma: no cover - caminho que o sistema recusa resolver
        return str(um).lower() == str(outro).lower()


def ask_databases(
    parent: tk.Misc,
    *,
    selected: Sequence[Path] | None = None,
    folder: Path = DEFAULT_DATABASE_DIR,
    choose: Callable[[], Sequence[str]] | None = None,
    note: Callable[[Sequence[Path]], str] = cache_note,
) -> tuple[Path, ...] | None:
    """Abre o diálogo modal e devolve as bases marcadas, ou `None` se a pessoa desistiu."""
    dialogo = DatabaseDialog(parent, selected=selected, folder=folder, choose=choose, note=note)
    dialogo.grab_set()
    dialogo.wait_window()
    return dialogo.chosen
