"""Aba "Dataset": listar, filtrar, recorrigir e remover amostras (S-23).

Toda a lógica de dados está em `dataset_browser`, que é testável; aqui fica só a tabela, os
filtros e os botões. A separação não é estética: os 100 rótulos ilegais que a Fase 1 mediu
precisam poder ser corrigidos **pela UI**, e isso é o critério de aceite da S-23 -- se a
regra de "o que é ilegal" morasse no widget, não haveria como testá-la.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from ..audit import find_duplicate_groups
from ..dataset_browser import (
    DatasetRow,
    class_distribution,
    delete_rows,
    filter_rows,
    imbalance_alerts,
    load_rows,
    quarantine_rows,
    source_distribution,
    split_distribution,
)

logger = logging.getLogger(__name__)

LEGALITY_CHOICES = ("(todas)", "legal", "lado-a-jogar", "ilegal", "sintaxe")
SPLIT_CHOICES = ("(todos)", "train", "val", "test")


class DatasetPanel(ttk.Frame):
    """Tabela paginada do `labels.csv` com filtros, estatísticas e ações."""

    COLUMNS = ("arquivo", "fen", "lado", "legalidade", "split", "origem", "pagina", "criado")
    HEADINGS = {
        "arquivo": "Arquivo",
        "fen": "FEN",
        "lado": "Lado",
        "legalidade": "Legalidade",
        "split": "Split",
        "origem": "Livro",
        "pagina": "Pag.",
        "criado": "Criado em",
    }
    WIDTHS = {
        "arquivo": 210,
        "fen": 330,
        "lado": 45,
        "legalidade": 95,
        "split": 55,
        "origem": 150,
        "pagina": 50,
        "criado": 130,
    }

    PAGE_SIZE = 200
    """Linhas por página da tabela. 3.195 linhas de uma vez travam o Treeview do Tk."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        paths: Callable[[], tuple[Path, Path, Path]],
        on_edit: Callable[[DatasetRow], None],
        on_recheck: Callable[[DatasetRow], str] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, padding=6)
        self._paths = paths
        self._on_edit = on_edit
        self._on_recheck = on_recheck
        self._on_status = on_status or (lambda _text: None)

        self.rows: list[DatasetRow] = []
        self.visible: list[DatasetRow] = []
        self._duplicate_groups: list[list[str]] = []
        self._page = 0

        self.query_var = tk.StringVar(value="")
        self.legality_var = tk.StringVar(value=LEGALITY_CHOICES[0])
        self.split_var = tk.StringVar(value=SPLIT_CHOICES[0])
        self.source_var = tk.StringVar(value="(todos)")
        self.duplicates_var = tk.BooleanVar(value=False)
        self.missing_var = tk.BooleanVar(value=False)
        self.page_var = tk.StringVar(value="")
        self.stats_var = tk.StringVar(value="")

        self._build_ui()

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="Recarregar", command=self.reload).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Detectar duplicatas", command=self.detect_duplicates).pack(side=tk.LEFT, padx=6)
        ttk.Button(toolbar, text="Estatísticas", command=self.show_statistics).pack(side=tk.LEFT)

        filters = ttk.LabelFrame(self, text="Filtros")
        filters.pack(fill=tk.X, pady=(6, 6))
        line = ttk.Frame(filters)
        line.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(line, text="Busca").pack(side=tk.LEFT)
        entry = ttk.Entry(line, textvariable=self.query_var, width=26)
        entry.pack(side=tk.LEFT, padx=(4, 10))
        entry.bind("<Return>", lambda _event: self.apply_filters())
        ttk.Label(line, text="Legalidade").pack(side=tk.LEFT)
        ttk.Combobox(line, textvariable=self.legality_var, values=LEGALITY_CHOICES, state="readonly", width=13).pack(
            side=tk.LEFT, padx=(4, 10)
        )
        ttk.Label(line, text="Split").pack(side=tk.LEFT)
        ttk.Combobox(line, textvariable=self.split_var, values=SPLIT_CHOICES, state="readonly", width=8).pack(
            side=tk.LEFT, padx=(4, 10)
        )

        line2 = ttk.Frame(filters)
        line2.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Label(line2, text="Livro").pack(side=tk.LEFT)
        self.source_combo = ttk.Combobox(line2, textvariable=self.source_var, values=("(todos)",), state="readonly", width=32)
        self.source_combo.pack(side=tk.LEFT, padx=(4, 10))
        ttk.Checkbutton(line2, text="Só duplicatas", variable=self.duplicates_var).pack(side=tk.LEFT)
        ttk.Checkbutton(line2, text="Imagem ausente", variable=self.missing_var).pack(side=tk.LEFT, padx=8)
        ttk.Button(line2, text="Aplicar", command=self.apply_filters).pack(side=tk.LEFT, padx=8)
        ttk.Button(line2, text="Limpar", command=self.clear_filters).pack(side=tk.LEFT)

        table_wrap = ttk.Frame(self)
        table_wrap.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(table_wrap, columns=self.COLUMNS, show="headings", selectmode="extended", height=14)
        for column in self.COLUMNS:
            self.tree.heading(column, text=self.HEADINGS[column])
            self.tree.column(column, width=self.WIDTHS[column], anchor="w", stretch=(column == "fen"))
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(table_wrap, orient=tk.VERTICAL, command=self.tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _event: self.edit_selected())

        pager = ttk.Frame(self)
        pager.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(pager, text="<", width=3, command=lambda: self.change_page(-1)).pack(side=tk.LEFT)
        ttk.Label(pager, textvariable=self.page_var).pack(side=tk.LEFT, padx=6)
        ttk.Button(pager, text=">", width=3, command=lambda: self.change_page(1)).pack(side=tk.LEFT)

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(actions, text="Abrir no editor", command=self.edit_selected).pack(side=tk.LEFT)
        ttk.Button(actions, text="Conferir com o modelo", command=self.recheck_selected).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="Quarentena", command=self.quarantine_selected).pack(side=tk.LEFT)
        ttk.Button(actions, text="Remover", command=self.remove_selected).pack(side=tk.LEFT, padx=6)

        ttk.Label(self, textvariable=self.stats_var, wraplength=780, justify=tk.LEFT).pack(anchor="w", pady=(6, 0))

    # -------------------------------------------------------------------- dados

    def reload(self) -> None:
        csv_path, samples_dir, splits_path = self._paths()
        try:
            self.rows = load_rows(csv_path, samples_dir, splits_path=splits_path, duplicate_groups=self._duplicate_groups)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Dataset", f"Não foi possível ler o dataset:\n{exc}")
            return

        livros = sorted({row.source_pdf for row in self.rows if row.source_pdf})
        self.source_combo.configure(values=("(todos)", *livros))
        self.apply_filters()
        self._on_status(f"Dataset carregado: {len(self.rows)} amostras.")

    def apply_filters(self) -> None:
        legality = self.legality_var.get()
        split = self.split_var.get()
        source = self.source_var.get()
        self.visible = filter_rows(
            self.rows,
            query=self.query_var.get(),
            legality=None if legality == LEGALITY_CHOICES[0] else legality,  # type: ignore[arg-type]
            split=None if split == SPLIT_CHOICES[0] else split,  # type: ignore[arg-type]
            source_pdf=None if source == "(todos)" else source,
            only_duplicates=bool(self.duplicates_var.get()),
            only_missing_image=bool(self.missing_var.get()),
        )
        self._page = 0
        self._render_page()
        self._update_stats()

    def clear_filters(self) -> None:
        self.query_var.set("")
        self.legality_var.set(LEGALITY_CHOICES[0])
        self.split_var.set(SPLIT_CHOICES[0])
        self.source_var.set("(todos)")
        self.duplicates_var.set(False)
        self.missing_var.set(False)
        self.apply_filters()

    def change_page(self, delta: int) -> None:
        pages = max(1, (len(self.visible) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._page = max(0, min(pages - 1, self._page + delta))
        self._render_page()

    def _render_page(self) -> None:
        self.tree.delete(*self.tree.get_children())
        start = self._page * self.PAGE_SIZE
        chunk = self.visible[start : start + self.PAGE_SIZE]
        for row in chunk:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    row.filename,
                    row.fen,
                    row.side_to_move or "—",
                    row.legality + (" (dup)" if row.is_duplicate else ""),
                    row.split or "—",
                    row.source_pdf or "—",
                    row.source_page or "—",
                    row.created_at or "—",
                ),
            )
        pages = max(1, (len(self.visible) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page_var.set(f"página {self._page + 1}/{pages} — {len(self.visible)} de {len(self.rows)} amostras")

    def _update_stats(self) -> None:
        if not self.rows:
            self.stats_var.set("")
            return
        por_legalidade = {
            estado: sum(1 for row in self.rows if row.legality == estado)
            for estado in ("legal", "lado-a-jogar", "ilegal", "sintaxe")
        }
        splits = split_distribution(self.rows)
        partes = [
            "legalidade: " + ", ".join(f"{estado} {contagem}" for estado, contagem in por_legalidade.items() if contagem),
            "splits: " + ", ".join(f"{nome} {contagem}" for nome, contagem in sorted(splits.items())),
        ]
        faltando = sum(1 for row in self.rows if not row.image_exists)
        if faltando:
            partes.append(f"{faltando} sem imagem no disco")
        self.stats_var.set(" | ".join(partes))

    # ------------------------------------------------------------------- ações

    def selected_rows(self) -> list[DatasetRow]:
        start = self._page * self.PAGE_SIZE
        chunk = self.visible[start : start + self.PAGE_SIZE]
        return [chunk[self.tree.index(item)] for item in self.tree.selection() if self.tree.index(item) < len(chunk)]

    def edit_selected(self) -> None:
        rows = self.selected_rows()
        if not rows:
            self._on_status("Selecione uma amostra.")
            return
        self._on_edit(rows[0])

    def recheck_selected(self) -> None:
        """Roda o modelo na amostra e compara com o rótulo -- acha rótulo humano errado."""
        if self._on_recheck is None:
            return
        rows = self.selected_rows()
        if not rows:
            self._on_status("Selecione uma amostra.")
            return
        try:
            resultado = self._on_recheck(rows[0])
        except Exception as exc:  # noqa: BLE001 - falha de modelo vira mensagem, nao crash
            messagebox.showerror("Conferir com o modelo", f"Não foi possível conferir:\n{exc}")
            return
        messagebox.showinfo("Conferir com o modelo", resultado)

    def quarantine_selected(self) -> None:
        rows = self.selected_rows()
        if not rows:
            self._on_status("Selecione ao menos uma amostra.")
            return
        csv_path, _samples_dir, _splits = self._paths()
        quarantine_path = csv_path.with_name("quarantine.csv")
        if not messagebox.askyesno(
            "Quarentena",
            f"Mover {len(rows)} amostra(s) para {quarantine_path.name}?\n\nElas saem do treino e continuam recuperáveis.",
        ):
            return
        moved = quarantine_rows(csv_path, [row.filename for row in rows], quarantine_path)
        self._on_status(f"{moved} amostra(s) movidas para quarentena.")
        self.reload()

    def remove_selected(self) -> None:
        rows = self.selected_rows()
        if not rows:
            self._on_status("Selecione ao menos uma amostra.")
            return
        answer = messagebox.askyesnocancel(
            "Remover amostras",
            f"Remover {len(rows)} amostra(s) do labels.csv?\n\n"
            "Sim: remove a linha e apaga o PNG.\n"
            "Não: remove só a linha, preservando o PNG.\n"
            "Cancelar: não faz nada.",
        )
        if answer is None:
            return
        csv_path, samples_dir, _splits = self._paths()
        removed = delete_rows(
            csv_path,
            [row.filename for row in rows],
            samples_dir=samples_dir,
            delete_images=bool(answer),
        )
        self._on_status(f"{removed} amostra(s) removidas.")
        self.reload()

    def detect_duplicates(self) -> None:
        """Roda o hash perceptual em segundo plano: são 3.195 imagens de 800×800."""
        if not self.rows:
            self.reload()
        csv_path, samples_dir, _splits = self._paths()
        self._on_status("Procurando duplicatas... isto lê todas as imagens do dataset.")
        labels = [(row.filename, row.fen) for row in self.rows if row.image_exists]

        def _worker() -> None:
            try:
                groups = find_duplicate_groups(samples_dir, labels)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao detectar duplicatas.")
                detalhe = str(exc)
                self.after(0, lambda: messagebox.showerror("Duplicatas", f"Falha na detecção:\n{detalhe}"))
                return
            self.after(0, lambda: self._apply_duplicates(groups))

        threading.Thread(target=_worker, daemon=True).start()
        logger.debug("Detecção de duplicatas disparada sobre %s", csv_path)

    def _apply_duplicates(self, groups: list[list[str]]) -> None:
        self._duplicate_groups = groups
        redundantes = sum(len(group) - 1 for group in groups)
        self._on_status(f"{len(groups)} grupos de duplicatas, {redundantes} amostras redundantes.")
        self.reload()

    def show_statistics(self) -> None:
        if not self.rows:
            self.reload()
        if not self.rows:
            return

        classes = class_distribution(self.rows)
        linhas = ["Casas por classe:"]
        total = sum(classes.values()) or 1
        for name, count in classes.most_common():
            linhas.append(f"  {name:>6}: {count:>7} ({count / total:.2%})")
        linhas.append("")
        linhas.append("Amostras por split: " + ", ".join(f"{k} {v}" for k, v in sorted(split_distribution(self.rows).items())))
        linhas.append("")
        linhas.append("Amostras por livro:")
        for name, count in source_distribution(self.rows).most_common(10):
            linhas.append(f"  {name}: {count}")
        alertas = imbalance_alerts(classes)
        if alertas:
            linhas.append("")
            linhas.append("Alertas:")
            linhas.extend(f"  {texto}" for texto in alertas)

        window = tk.Toplevel(self)
        window.title("Estatísticas do dataset")
        window.geometry("560x520")
        text = tk.Text(window, wrap="none", font=("Consolas", 10))
        text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        text.insert("1.0", "\n".join(linhas))
        text.configure(state=tk.DISABLED)
