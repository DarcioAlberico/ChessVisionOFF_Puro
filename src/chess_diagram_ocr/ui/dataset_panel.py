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
    page_after_change,
    quarantine_rows,
    source_distribution,
    split_distribution,
)
from . import espaco, estilos, formato, strings, tabela, texto, theme, tipografia
from .busy import BusyRegistry, BusyToken
from .tooltip import Tooltip

logger = logging.getLogger(__name__)

LEGALITY_CHOICES = ("(todas)", "legal", "lado-a-jogar", "ilegal", "sintaxe")
SPLIT_CHOICES = ("(todos)", "train", "val", "test")


class DatasetPanel(ttk.Frame):
    """Tabela paginada do `labels.csv` com filtros, estatísticas e ações."""

    COLUNAS = (
        tabela.Coluna("arquivo", "Arquivo", 210),
        tabela.Coluna("fen", "FEN", 330, elastica=True),
        tabela.Coluna("lado", "Lado", 45),
        tabela.Coluna("legalidade", "Legalidade", 95),
        tabela.Coluna("split", strings.CONJUNTO, 55),
        tabela.Coluna("origem", "Livro", 150),
        tabela.Coluna("página", "Pag.", 50, numerica=True),
        tabela.Coluna("criado", "Criado em", 130),
    )
    """As oito colunas, cada uma dizendo o que é (S-153).

    Eram três dicionários paralelos -- `COLUMNS`, `HEADINGS`, `WIDTHS` --, e paralelo é o
    problema: nada ligava a largura ao título, nada dizia que "Pag." é número, e a nona coluna
    entraria em três lugares ou em dois."""

    COLUMNS = tuple(coluna.chave for coluna in COLUNAS)

    PAGE_SIZE = 200
    """Linhas por página da tabela.

    **A premissa que criou isto está medida e é falsa** (S-118). A justificativa era "3.195
    linhas de uma vez travam o `Treeview` do Tk", e o `ARCHITECTURE.md` a repetia. Medido nesta
    máquina com `Treeview` real e as mesmas 8 colunas: inserir **3.936 linhas custa 53 ms**, e
    limpar a tabela custa 6 ms. O que custava era o `load_rows` que vinha antes -- 689 ms --, e
    esse é assunto da S-116.

    **A paginação fica, e tirá-la é uma segunda decisão.** Ela não é gratuita: cobra o lugar de
    quem está conferindo rótulo a rótulo, e é isso que a S-118 conserta preservando página e
    seleção. Mas 53 ms é o número de hoje com 3.936 linhas, e o `labels.csv` é o arquivo que o
    projeto existe para fazer crescer -- a decisão de remover a paginação precisa da medição
    refeita quando ele dobrar, não da premissa de 2026-07 nem desta."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        paths: Callable[[], tuple[Path, Path, Path]],
        on_edit: Callable[[DatasetRow], None],
        on_recheck: Callable[[DatasetRow], str] | None = None,
        on_status: Callable[[str], None] | None = None,
        busy: BusyRegistry | None = None,
    ) -> None:
        super().__init__(parent, padding=espaco.linha())
        self._paths = paths
        self._on_edit = on_edit
        self._on_recheck = on_recheck
        self._on_status = on_status or (lambda _text: None)

        self.rows: list[DatasetRow] = []
        self.visible: list[DatasetRow] = []
        self._duplicate_groups: list[list[str]] = []
        self._page = 0
        self._busy_registry = busy
        """Onde a detecção de duplicatas se declara como operação longa (S-112)."""
        self._busy_token: BusyToken | None = None

        self._stale = True
        """Alguém gravou no `labels.csv` desde a última leitura desta aba (S-116).

        Começa **verdadeiro**: a aba nasce sem linha nenhuma, e a primeira vez que ela aparecer
        tem de ler. É o mesmo estado de "mudou desde que eu li"."""

        self.query_var = tk.StringVar(value="")
        self.legality_var = tk.StringVar(value=LEGALITY_CHOICES[0])
        self.split_var = tk.StringVar(value=SPLIT_CHOICES[0])
        self.source_var = tk.StringVar(value="(todos)")
        self.duplicates_var = tk.BooleanVar(value=False)
        self.missing_var = tk.BooleanVar(value=False)
        self.page_var = tk.StringVar(value="")
        self.stats_var = tk.StringVar(value="")

        self._build_ui()
        # O `ttk.Notebook` mapeia e desmapeia o quadro de cada aba ao trocar de aba: e este o
        # evento que diz "a pessoa esta olhando o dataset agora" (S-116).
        self.bind("<Map>", self._on_map)

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="Recarregar", command=self.reload, style=estilos.estilo_de_botao(estilos.NEUTRO)).pack(side=tk.LEFT)
        # Guardado em atributo porque ele precisa **ficar cinza** enquanto a detecção roda
        # (S-314): era criado inline e não havia como desabilitá-lo.
        self.btn_duplicatas = ttk.Button(
            toolbar,
            text="Detectar duplicatas",
            command=self.detect_duplicates,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        )
        self.btn_duplicatas.pack(side=tk.LEFT, padx=espaco.linha())
        Tooltip(self.btn_duplicatas).set_text(
            "Compara todas as imagens do dataset por hash perceptual. Fica cinza enquanto uma "
            "detecção está em andamento -- são 3.195 imagens de 800×800, e duas passadas ao "
            "mesmo tempo leem o disco duas vezes para dar a mesma resposta."
        )
        ttk.Button(
            toolbar,
            text="Estatísticas",
            command=self.show_statistics,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.LEFT)

        filters = ttk.LabelFrame(self, text="Filtros")
        filters.pack(fill=tk.X, pady=(espaco.linha(), espaco.linha()))
        line = ttk.Frame(filters)
        line.pack(fill=tk.X, padx=espaco.linha(), pady=espaco.linha())
        ttk.Label(line, text="Busca").pack(side=tk.LEFT)
        entry = ttk.Entry(line, textvariable=self.query_var, width=26)
        entry.pack(side=tk.LEFT, padx=(espaco.linha(), espaco.folga()))
        entry.bind("<Return>", lambda _event: self.apply_filters())
        ttk.Label(line, text="Legalidade").pack(side=tk.LEFT)
        ttk.Combobox(line, textvariable=self.legality_var, values=LEGALITY_CHOICES, state="readonly", width=13).pack(
            side=tk.LEFT, padx=(espaco.linha(), espaco.folga())
        )
        ttk.Label(line, text=strings.CONJUNTO).pack(side=tk.LEFT)
        ttk.Combobox(line, textvariable=self.split_var, values=SPLIT_CHOICES, state="readonly", width=8).pack(
            side=tk.LEFT, padx=(espaco.linha(), espaco.folga())
        )

        line2 = ttk.Frame(filters)
        line2.pack(fill=tk.X, padx=espaco.linha(), pady=(0, espaco.linha()))
        ttk.Label(line2, text="Livro").pack(side=tk.LEFT)
        self.source_combo = ttk.Combobox(line2, textvariable=self.source_var, values=("(todos)",), state="readonly", width=32)
        self.source_combo.pack(side=tk.LEFT, padx=(espaco.linha(), espaco.folga()))
        ttk.Checkbutton(line2, text="Só duplicatas", variable=self.duplicates_var).pack(side=tk.LEFT)
        ttk.Checkbutton(line2, text="Imagem ausente", variable=self.missing_var).pack(side=tk.LEFT, padx=espaco.folga())
        ttk.Button(
            line2,
            text="Aplicar",
            command=self.apply_filters,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.LEFT, padx=espaco.folga())
        ttk.Button(line2, text="Limpar", command=self.clear_filters, style=estilos.estilo_de_botao(estilos.NEUTRO)).pack(side=tk.LEFT)

        # Corpo em monoespaçada (S-149): a coluna de FEN é a razão, e `ttk` não tem fonte por
        # coluna -- mas esta tabela é dado de ponta a ponta (arquivo, FEN, livro, data), e é
        # nela que duas linhas precisam alinhar para serem comparadas.
        self.tree = tabela.montar(
            self,
            self.COLUNAS,
            selectmode="extended",
            height=14,
            style=theme.ESTILO_DE_TABELA_DE_DADOS,
        )
        self.tree.bind("<Double-1>", lambda _event: self.edit_selected())

        pager = ttk.Frame(self)
        pager.pack(fill=tk.X, pady=(espaco.linha(), 0))
        ttk.Button(
            pager,
            text="<",
            width=3,
            command=lambda: self.change_page(-1),
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.LEFT)
        ttk.Label(pager, textvariable=self.page_var).pack(side=tk.LEFT, padx=espaco.linha())
        ttk.Button(
            pager,
            text=">",
            width=3,
            command=lambda: self.change_page(1),
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.LEFT)

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, pady=(espaco.linha(), 0))
        ttk.Button(
            actions,
            text="Abrir no editor",
            command=self.edit_selected,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text="Conferir com o modelo",
            command=self.recheck_selected,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.LEFT, padx=espaco.linha())
        ttk.Button(actions, text="Quarentena", command=self.quarantine_selected, style=estilos.estilo_de_botao(estilos.DESTRUTIVO)).pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text="Remover",
            command=self.remove_selected,
            style=estilos.estilo_de_botao(estilos.DESTRUTIVO),
        ).pack(side=tk.LEFT, padx=espaco.linha())

        texto.acompanhar(ttk.Label(
            self,
            textvariable=self.stats_var,
            justify=tk.LEFT,
        )).pack(anchor="w", pady=(espaco.linha(), 0))

    # -------------------------------------------------------------------- dados

    def contagem_de_amostras(self) -> int | None:
        """Quantas linhas o `labels.csv` tem, **sem carregar o dataset** (S-162).

        A contagem vai para o rótulo da aba, e ela não pode custar o que custa abrir a aba: a
        S-116 mediu `load_rows` em **689 ms** sobre 3.936 linhas e tornou esta aba preguiçosa
        justamente por isso. Contar linhas do arquivo é leitura sequencial e milissegundos -- e
        responde a pergunta que o rótulo faz ("quanto tem lá dentro?") sem desfazer aquele item.

        `None` quando o arquivo não existe: a aba nunca foi usada, e "(0)" ali seria afirmar que o
        dataset está vazio quando o que se sabe é que ele não foi encontrado.
        """
        csv_path, _amostras, _splits = self._paths()
        try:
            with Path(csv_path).open("r", encoding="utf-8", errors="replace") as arquivo:
                linhas = sum(1 for _ in arquivo)
        except OSError:
            return None
        # Menos o cabeçalho; um arquivo só com ele é dataset vazio, e não -1 amostras.
        return max(0, linhas - 1)

    def reload(self) -> None:
        """Relê o dataset -- **ou anota que ele mudou, se esta aba não está na tela** (S-116).

        `load_rows` custa **689 ms** medidos sobre o `labels.csv` de 3.936 linhas, e o caminho
        que mais chamava isto era o `Ctrl+S`: gravar uma amostra avisava a aba Dataset, que
        relia o arquivo inteiro na thread do Tk **mesmo nunca tendo sido aberta**. O laço mais
        interno do projeto -- corrigir, salvar, seta, corrigir -- pagava quase um segundo de
        janela travada por amostra, e o custo cresce com o arquivo que o projeto existe para
        fazer crescer.

        **A preguiça mora aqui, e não em quem avisa.** Quem grava uma amostra não tem como
        saber se esta aba está visível, e não deveria: espalhar `if aba_visivel` pelos
        chamadores poria a mesma decisão em cinco lugares. O `<Map>` do próprio painel -- que o
        `ttk.Notebook` dispara ao trocar de aba -- é o sinal, e ele chega sem que ninguém o
        mande.
        """
        if not self.winfo_ismapped():
            self._stale = True
            return
        self._reload_now()

    def _on_map(self, _event: object = None) -> None:
        """A aba apareceu. Se alguém gravou enquanto ela estava escondida, é agora que se paga."""
        if self._stale:
            self._reload_now()

    def _reload_now(self) -> None:
        self._stale = False
        # O lugar de quem estava conferindo, guardado antes da recarga (S-118). Por
        # `filename` e nao por indice: a linha corrigida pode ter mudado de posicao no filtro,
        # e um indice apontaria para a vizinha dela.
        selecionadas = {row.filename for row in self.selected_rows()}
        csv_path, samples_dir, splits_path = self._paths()
        try:
            self.rows = load_rows(csv_path, samples_dir, splits_path=splits_path, duplicate_groups=self._duplicate_groups)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Dataset", f"Não foi possível ler o dataset:\n{exc}")
            return

        livros = sorted({row.source_pdf for row in self.rows if row.source_pdf})
        self.source_combo.configure(values=("(todos)", *livros))
        self.apply_filters(keep_position=True)
        self._select_filenames(selecionadas)
        self._on_status(f"Dataset carregado: {len(self.rows)} amostras.")

    def _select_filenames(self, filenames: set[str]) -> None:
        """Reseleciona, na página desenhada agora, as linhas que estavam selecionadas antes.

        Só o que está na página: uma linha que saiu dela pela mudança de filtro não tem item
        de `Treeview` para selecionar, e persegui-la mudando de página seria adivinhar.
        """
        if not filenames:
            return
        inicio = self._page * self.PAGE_SIZE
        chunk = self.visible[inicio : inicio + self.PAGE_SIZE]
        itens = self.tree.get_children()
        alvos = [itens[i] for i, row in enumerate(chunk) if row.filename in filenames and i < len(itens)]
        if alvos:
            self.tree.selection_set(alvos)
            self.tree.see(alvos[0])

    def apply_filters(self, *, keep_position: bool = False) -> None:
        """Refiltra e redesenha. `keep_position` é para quem **não** mudou o filtro (S-118).

        Trocar um filtro é pedir outra lista, e ali voltar à primeira página é o certo. Salvar
        uma amostra não é: a lista é a mesma, e devolver a tabela ao começo perde o lugar de
        quem estava conferindo rótulo a rótulo.
        """
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
        self._page = page_after_change(self._page, len(self.visible), self.PAGE_SIZE) if keep_position else 0
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
                    # "Brancas" e não `w` (S-169): o código é do CSV, e publicá-lo obriga quem
                    # lê a saber que `w` quer dizer brancas -- em inglês, numa janela pt-BR.
                    formato.lado_a_jogar(row.side_to_move),
                    row.legality + (" (dup)" if row.is_duplicate else ""),
                    formato.texto_ou_ausente(row.split),
                    formato.texto_ou_ausente(row.source_pdf),
                    formato.texto_ou_ausente(row.source_page),
                    formato.texto_ou_ausente(row.created_at),
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
        except Exception as exc:  # noqa: BLE001 - falha de modelo vira mensagem, não crash
            messagebox.showerror("Conferir com o modelo", f"Não foi possível conferir:\n{exc}")
            return
        # O resultado da conferência é uma linha, e ela vai para o rodapé (S-164): a caixa era
        # modal por não haver outro lugar, e conferir amostra a amostra é gesto de repetição --
        # exatamente onde um clique obrigatório por resposta custa mais.
        self._on_status(resultado)

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
            # A pergunta **nomeia** o que vai sumir (S-170): contar não é conferir, e o que
            # está prestes a ser apagado é rótulo corrigido à mão. Ver `strings.frase_de_remocao`.
            strings.frase_de_remocao([row.filename for row in rows], arquivo=self._paths()[0].name) + "\n\n"
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
        """Roda o hash perceptual em segundo plano: são 3.195 imagens de 800×800.

        **Um clique de cada vez (S-314).** Não havia guarda nenhuma: o segundo clique
        sobrescrevia `self._busy_token` com uma chave nova, e a do primeiro ficava registrada
        para sempre -- `_release_busy` só solta a que está no atributo. `BusyRegistry.running()`
        não filtra por `loses_work`, então a chave vazada entra na pergunta de fechamento **de
        toda sessão seguinte**: a janela passa a avisar que há uma operação em andamento que
        terminou há horas, que é exatamente o que essa pergunta existe para não fazer.

        **O botão cinza e não uma bandeira.** Uma bandeira sozinha deixa o botão vivo e joga a
        resposta numa frase de rodapé que se perde; o botão cinza é a mesma resposta e não
        depende de a pessoa estar olhando -- e é o molde que a própria janela já usa na Galeria
        e na fila de revisão. A frase fica como rede para quem chegar pela paleta de comandos em
        vez do botão.
        """
        if self._busy_token is not None:
            self._on_status("A detecção de duplicatas já está em andamento.")
            return
        if not self.rows:
            self.reload()
        csv_path, samples_dir, _splits = self._paths()
        self._on_status("Procurando duplicatas... isto lê todas as imagens do dataset.")
        labels = [(row.filename, row.fen) for row in self.rows if row.image_exists]

        if self._busy_registry is not None:
            self._busy_token = self._busy_registry.register(
                "detecção de duplicatas",
                # Derivada: o hash perceptual não grava nada, e refazer recomputa a mesma
                # resposta a partir das mesmas imagens. Não é cancelável porque
                # `find_duplicate_groups` não tem por onde -- e inventar um `Event` que ninguém
                # consulta seria oferecer um botão que não para nada.
                loses_work=False,
                detail=f"{len(labels)} imagem(ns)",
            )
        self.btn_duplicatas.configure(state=tk.DISABLED)

        def _worker() -> None:
            try:
                groups = find_duplicate_groups(samples_dir, labels)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao detectar duplicatas.")
                detalhe = str(exc)
                self.after(0, lambda: messagebox.showerror("Duplicatas", f"Falha na detecção:\n{detalhe}"))
                return
            finally:
                self.after(0, self._release_busy)
            self.after(0, lambda: self._apply_duplicates(groups))

        threading.Thread(target=_worker, daemon=True).start()
        logger.debug("Detecção de duplicatas disparada sobre %s", csv_path)

    def _release_busy(self) -> None:
        # No `finally` do worker, e não depois de `_apply_duplicates`: o caminho de exceção abre
        # um modal e retorna, e reabilitar depois dele deixaria o botão cinza para sempre --
        # trocar um travamento por outro (S-314).
        if self._busy_token is not None:
            self._busy_token.release()
            self._busy_token = None
        try:
            self.btn_duplicatas.configure(state=tk.NORMAL)
        except tk.TclError:  # pragma: no cover - painel destruído antes de a thread voltar
            pass

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
        window.bind("<Escape>", lambda _evento: window.destroy())  # S-395
        # `wrap="none"` mais monoespaçada: as estatísticas são colunas alinhadas por espaço, e
        # em proporcional elas deixam de ser colunas (S-149).
        text = tk.Text(window, wrap="none", font=theme.fonte_atual(tipografia.DADO))
        text.pack(fill=tk.BOTH, expand=True, padx=espaco.folga(), pady=espaco.folga())
        text.insert("1.0", "\n".join(linhas))
        text.configure(state=tk.DISABLED)
