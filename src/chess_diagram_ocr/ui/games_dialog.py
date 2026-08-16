"""A lista de partidas candidatas, e a escolha (S-86).

**Por que uma lista, e não um automático melhor.** Medido no acervo em 2026-08-15: dos 373
diagramas cuja posição aparece em mais de uma partida, o desempate automático resolve 23 pela
legenda -- e **350 continuam sem saída**. Neles a base sabe a resposta e nenhuma regra sabe
qual das candidatas é: um final de rei e peão aparece em centenas de partidas, e só quem tem o
livro na mão pode dizer qual delas o autor citou.

**A janela é só widget.** Filtrar, escolher, espalhar aos vizinhos e decidir o que pode ser
sobrescrito são decisões do `GalleryModel`, que se testa sem abrir um Tk. O que mora aqui é a
`Treeview`, o campo de filtro e o vaivém entre os dois -- é a mesma divisão que organizou a
Fase 6, e ela existe porque foi na lógica, não na janela, que os defeitos apareceram.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from chess_diagram_ocr.games_db import PositionHit, agrees_with_caption
from chess_diagram_ocr.pdf_text import fold

from .gallery_model import GalleryModel

__all__ = ["GamesDialog"]

COLUNAS = (
    ("date", "Data", 90),
    ("white", "Brancas", 170),
    ("black", "Pretas", 170),
    ("event", "Evento", 190),
    ("result", "Resultado", 80),
    ("move", "Lance", 55),
    ("side", "Vez", 45),
)
"""As colunas, e a ordem delas é a da pergunta que a pessoa faz: *que partida é esta?* -- data
e jogadores primeiro, e o lance por último, que é consequência da escolha e não critério dela."""

NEIGHBOUR_RADIUS = 3
"""Quantos diagramas de cada lado o "aplicar aos vizinhos" alcança.

Três porque é o tamanho de um trecho analisado -- um capítulo mostra a mesma partida em quatro
ou cinco diagramas seguidos. Um raio grande transformaria um acerto em espalhamento, que é
exatamente o que a S-76 custou caro para aprender."""


class GamesDialog(tk.Toplevel):
    """Mostra as candidatas do diagrama atual e aplica a que a pessoa escolher."""

    def __init__(self, parent: tk.Misc, *, model: GalleryModel, on_applied: Callable[[str], None]) -> None:
        super().__init__(parent)
        self._model = model
        self._on_applied = on_applied
        self._todas: tuple[PositionHit, ...] = ()
        self._visiveis: list[PositionHit] = []
        self._por_nome: set[str] = set()
        """As que vieram da busca por nome (S-87), para a lista dizer de onde cada uma veio."""

        self.title("Partidas da base")
        self.transient(parent.winfo_toplevel())
        self.geometry("900x420")

        self.filter_var = tk.StringVar(value="")
        self.count_var = tk.StringVar(value="")
        self._build()
        self.reload()

    # ------------------------------------------------------------------------ construção

    def _build(self) -> None:
        topo = ttk.Frame(self, padding=(8, 8, 8, 4))
        topo.pack(fill=tk.X)
        ttk.Label(topo, text="filtro").pack(side=tk.LEFT)
        campo = ttk.Entry(topo, textvariable=self.filter_var, width=30)
        campo.pack(side=tk.LEFT, padx=6)
        campo.focus_set()
        # A cada tecla, e nao no Return: com 32 candidatas o filtro e para *reduzir enquanto se
        # olha*, e exigir confirmacao a cada tentativa faria a pessoa digitar o nome inteiro.
        self.filter_var.trace_add("write", lambda *_: self._repopulate())
        ttk.Label(topo, textvariable=self.count_var, foreground="#666666").pack(side=tk.RIGHT)

        corpo = ttk.Frame(self, padding=(8, 0))
        corpo.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(corpo, columns=[c[0] for c in COLUNAS], show="headings", selectmode="browse")
        for chave, titulo, largura in COLUNAS:
            self.tree.heading(chave, text=titulo)
            self.tree.column(chave, width=largura, anchor=tk.W, stretch=chave in ("white", "black", "event"))
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        barra = ttk.Scrollbar(corpo, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra.set)
        barra.pack(side=tk.LEFT, fill=tk.Y)
        self.tree.bind("<Double-1>", lambda _e: self.apply_selected())
        self.tree.bind("<Return>", lambda _e: self.apply_selected())

        # A escolhida em negrito, a confirmada pela legenda em verde, a que os vizinhos tambem
        # tem em azul: as tres informacoes que decidem o clique, e nenhuma delas cabe numa
        # coluna sem virar mais uma coluna.
        self.tree.tag_configure("escolhida", font=("TkDefaultFont", 9, "bold"))
        self.tree.tag_configure("legenda", foreground="#2e7d32")
        self.tree.tag_configure("vizinha", foreground="#1565c0")
        self.tree.tag_configure("porNome", foreground="#6a1b9a")

        rodape = ttk.Frame(self, padding=8)
        rodape.pack(fill=tk.X)
        ttk.Button(rodape, text="Aplicar", command=self.apply_selected).pack(side=tk.LEFT)
        self.btn_by_name = ttk.Button(rodape, text="Procurar por nome", command=self.search_by_name)
        self.btn_by_name.pack(side=tk.LEFT, padx=6)
        self.btn_neighbours = ttk.Button(
            rodape, text="Aplicar aos vizinhos...", command=self.apply_to_neighbours, state=tk.DISABLED
        )
        self.btn_neighbours.pack(side=tk.LEFT, padx=6)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_neighbour_button())

    # ------------------------------------------------------------------------ conteúdo

    def reload(self) -> None:
        self._todas, total = self._model.current_candidates()
        guardadas = len(self._todas)
        # "32 de 147" e obrigatorio, nao decorativo: sem ele a pessoa escolhe achando que viu
        # tudo, e a partida certa pode estar entre as 115 que a varredura nao guardou.
        self.count_var.set(
            f"{guardadas} de {total} partida(s)" if total > guardadas else f"{total} partida(s)"
        )
        self._repopulate()

    def _repopulate(self) -> None:
        alvo = fold(self.filter_var.get())
        self._visiveis = [hit for hit in self._todas if not alvo or alvo in fold(_texto_busca(hit))]
        escolhida = self._model.current_annotation.chosen_game
        par = self._model.current_caption_pair()
        vizinhas = self._model.neighbour_game_keys(radius=NEIGHBOUR_RADIUS)

        self.tree.delete(*self.tree.get_children())
        for indice, hit in enumerate(self._visiveis):
            etiquetas = []
            if escolhida and hit.key == escolhida:
                etiquetas.append("escolhida")
            elif par is not None and agrees_with_caption(hit, par):
                etiquetas.append("legenda")
            elif hit.key in self._por_nome:
                etiquetas.append("porNome")
            elif hit.key in vizinhas:
                etiquetas.append("vizinha")
            self.tree.insert("", tk.END, iid=str(indice), values=_linha(hit), tags=tuple(etiquetas))
        if self._visiveis:
            self.tree.selection_set("0")
        self._update_neighbour_button()

    def _selected(self) -> PositionHit | None:
        selecao = self.tree.selection()
        if not selecao:
            return None
        return self._visiveis[int(selecao[0])]

    def _update_neighbour_button(self) -> None:
        escolhida = self._selected()
        vizinhos = [] if escolhida is None else self._model.neighbours_with_game(escolhida, radius=NEIGHBOUR_RADIUS)
        self.btn_neighbours.configure(
            state=tk.NORMAL if vizinhos else tk.DISABLED,
            text=f"Aplicar aos vizinhos ({len(vizinhos)})..." if vizinhos else "Aplicar aos vizinhos...",
        )

    # ------------------------------------------------------------------------ a escolha

    def apply_selected(self) -> None:
        escolhida = self._selected()
        if escolhida is None:
            return
        conflitos = self._model.conflicts_with(escolhida)
        sobrescrever = False
        if conflitos:
            # A base nunca sobrescreve (S-72); uma pessoa escolhendo pode -- mas o que *ela*
            # digitou nao some calado. O que veio da base e trocado nos dois casos.
            sobrescrever = messagebox.askyesno(
                "Partidas da base",
                "Esta partida discorda do que você digitou em:\n\n"
                f"  {', '.join(_rotulo(campo) for campo in conflitos)}\n\n"
                "Substituir pelo que a partida escolhida diz?\n"
                "Responder Não aplica o resto e deixa esses campos como estão.",
                parent=self,
            )
        campos = self._model.choose_game(escolhida, overwrite=sobrescrever)
        self._on_applied(
            f"Partida escolhida: {escolhida.label} -- {len(campos)} campo(s) preenchido(s)."
            if campos
            else f"Partida escolhida: {escolhida.label}. Nada a preencher; a escolha ficou registrada."
        )
        self._repopulate()

    def search_by_name(self) -> None:
        """Pergunta à base pelos nomes da legenda e junta o que ela achar à lista (S-87).

        **Junta, não substitui.** A lista do cache é o que a varredura mediu sobre a posição; a
        busca por nome alcança o que ela não podia guardar -- a partida cortada pelo teto de 32,
        e a que a posição não casou. Trocar uma pela outra perderia a metade que já estava
        certa.
        """
        if self._model.current_caption_pair() is None:
            messagebox.showinfo(
                "Partidas da base",
                "A legenda deste diagrama não nomeia os dois jogadores, então não há por onde "
                "procurar por nome.",
                parent=self,
            )
            return
        achadas = self._model.search_games_by_name()
        conhecidas = {hit.key for hit in self._todas}
        novas = tuple(hit for hit in achadas if hit.key not in conhecidas)
        self._por_nome.update(hit.key for hit in achadas)
        if not achadas:
            messagebox.showinfo(
                "Partidas da base",
                "A busca por nome não achou partida com esta posição.\n\n"
                "Se o índice ainda não foi construído:  cvoff-games --build-index",
                parent=self,
            )
            return
        self._todas = (*self._todas, *novas)
        sem_posicao = sum(1 for hit in novas if not hit.verified)
        aviso = f", {sem_posicao} sem a posição (só headers)" if sem_posicao else ""
        self.count_var.set(f"{len(self._todas)} partida(s), {len(novas)} pela busca por nome{aviso}")
        self._repopulate()

    def apply_to_neighbours(self) -> None:
        escolhida = self._selected()
        if escolhida is None:
            return
        vizinhos = self._model.neighbours_with_game(escolhida, radius=NEIGHBOUR_RADIUS)
        if not vizinhos:
            return
        if not messagebox.askyesno(
            "Partidas da base",
            f"Aplicar {escolhida.label} a {len(vizinhos)} diagrama(s) vizinho(s)?\n\n"
            "Só entram os que têm esta partida entre as candidatas deles, e cada um recebe o "
            "lance dele -- é a mesma partida em outro momento.",
            parent=self,
        ):
            return
        tocados = self._model.apply_game_to_neighbours(escolhida, radius=NEIGHBOUR_RADIUS)
        self._on_applied(f"{escolhida.label}: aplicada a {tocados} diagrama(s) vizinho(s).")


def _texto_busca(hit: PositionHit) -> str:
    """O que o filtro varre: os nomes, o evento e o ano -- que é como se procura uma partida."""
    return " ".join(hit.headers.get(campo, "") for campo in ("White", "Black", "Event", "Site", "Date"))


def _linha(hit: PositionHit) -> tuple[str, ...]:
    return (
        hit.headers.get("Date", ""),
        hit.headers.get("White", ""),
        hit.headers.get("Black", ""),
        hit.headers.get("Event", ""),
        hit.headers.get("Result", ""),
        # Travessão e não "0": a partida não diz em que lance esta posição acontece, porque
        # ela não contém esta posição. Um número ali seria lido como resposta.
        str(hit.move_number) if hit.verified else "—",
        ("brancas" if hit.side_to_move == "w" else "pretas") if hit.verified else "—",
    )


def _rotulo(campo: str) -> str:
    """Nome de campo como a pessoa o vê na tela, e não como o arquivo o guarda."""
    return {"move_number": "Lance", "side_to_move": "Vez"}.get(campo, campo.removeprefix("header:"))
