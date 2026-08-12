"""A aba de análise: tabuleiro de estudo, árvore de variantes e PGN (S-31).

**Por que sai do `app_tkinter.py`.** São ~330 linhas que não têm nada a ver com OCR: uma
árvore `chess.pgn`, navegação por variantes e escrita de arquivo. Ficavam misturadas com o
reconhecimento porque tudo morava na mesma classe, e o único vínculo real entre as duas
coisas é uma string -- a FEN do diagrama selecionado.

**Esse vínculo é de mão única, e de propósito.** O painel *lê* a FEN do OCR quando o
usuário pede (ou quando "Seguir OCR selecionado" está ligado) e nunca escreve de volta.
Analisar uma posição não é corrigi-la: um lance jogado aqui muda o tabuleiro de estudo, e
propagá-lo para o reconhecimento sobrescreveria o que o usuário está tentando conferir.

**A árvore mora no painel, o widget é o mesmo dos dois lados.** `InteractiveBoard` em modo
`play` (S-20) desenha e valida o lance; quem guarda a linha, as variantes e o nó atual é
esta classe. Antes da S-20 havia duas implementações de tabuleiro no mesmo arquivo e só uma
era interativa.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import chess
import chess.pgn

from chess_diagram_ocr.engine import EngineAnalyzer, Evaluation
from chess_diagram_ocr.fen_utils import board_from_fen, is_valid_fen

from .board_widget import InteractiveBoard, PieceImages

logger = logging.getLogger(__name__)


class StudyPanel(ttk.Frame):
    """Tabuleiro de estudo com árvore de variantes, sincronizável com o OCR."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        piece_images: PieceImages,
        current_fen: Callable[[], str],
        initial_dir: Path,
        analyzer: EngineAnalyzer | None = None,
    ) -> None:
        super().__init__(parent, padding=6)
        self._current_fen = current_fen
        """De onde vem a FEN do diagrama selecionado. Só é chamada quando o usuário pede."""

        self._initial_dir = initial_dir
        self._analyzer = analyzer
        """O motor, se houver um. `None` esconde a seção inteira em vez de deixá-la
        cinza: a S-33 pede que sem Stockfish o app funcione normalmente (S-33)."""

        self._analysing = False

        self.board = chess.Board()
        self.game = chess.pgn.Game()
        self.game.setup(self.board.copy(stack=False))
        self.current_node: chess.pgn.GameNode = self.game

        self.origin_var = tk.StringVar(value="Base: posição inicial")
        self.status_var = tk.StringVar(value="")
        self.fen_var = tk.StringVar(value=self.board.fen())
        self.variation_var = tk.StringVar(value="")
        self.follow_ocr_var = tk.BooleanVar(value=True)
        self.flipped_var = tk.BooleanVar(value=False)
        self.engine_var = tk.StringVar(value="")
        self.engine_line_var = tk.StringVar(value="")

        self._build(piece_images)
        self.refresh()
        self.set_status("Clique em uma peça para estudar.")

    # ------------------------------------------------------------------------------ layout

    def _build(self, piece_images: PieceImages) -> None:
        top_row = ttk.Frame(self)
        top_row.pack(fill=tk.X, padx=4, pady=(0, 4))
        ttk.Button(top_row, text="Carregar OCR atual", command=self.load_from_recognized).pack(side=tk.LEFT)
        ttk.Button(top_row, text="Posição inicial", command=self.load_initial_position).pack(side=tk.LEFT, padx=6)
        ttk.Button(top_row, text="Virar board", command=self.flip_board).pack(side=tk.LEFT, padx=6)
        ttk.Button(top_row, text="Trocar vez", command=self.toggle_turn).pack(side=tk.LEFT, padx=6)
        ttk.Button(top_row, text="Salvar PGN", command=self.save_pgn).pack(side=tk.LEFT, padx=6)

        action_row = ttk.Frame(self)
        action_row.pack(fill=tk.X, padx=4, pady=(0, 6))
        ttk.Button(action_row, text="|<", width=4, command=self.go_to_start_of_line).pack(side=tk.LEFT)
        ttk.Button(action_row, text="<", width=4, command=self.undo_move).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(action_row, text=">", width=4, command=self.redo_move).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(action_row, text=">|", width=4, command=self.go_to_end_of_line).pack(side=tk.LEFT, padx=(6, 6))
        ttk.Button(action_row, text="Aplicar FEN", command=self.apply_fen).pack(side=tk.LEFT, padx=6)
        ttk.Button(action_row, text="Copiar FEN", command=self.copy_fen).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(
            action_row,
            text="Seguir OCR selecionado",
            variable=self.follow_ocr_var,
            command=self.on_follow_ocr_toggle,
        ).pack(side=tk.RIGHT)

        variation_row = ttk.Frame(self)
        variation_row.pack(fill=tk.X, padx=4, pady=(0, 6))
        ttk.Label(variation_row, text="Continuações").pack(side=tk.LEFT)
        self.variation_combo = ttk.Combobox(
            variation_row, textvariable=self.variation_var, state="readonly", width=46
        )
        self.variation_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.variation_combo.bind("<<ComboboxSelected>>", lambda _event: self.set_status("Continuação selecionada."))
        ttk.Button(variation_row, text="Entrar", command=self.redo_move).pack(side=tk.LEFT)

        ttk.Label(self, textvariable=self.origin_var).pack(anchor="w", padx=6)
        ttk.Label(self, textvariable=self.status_var, wraplength=620).pack(anchor="w", padx=6, pady=(0, 6))

        ttk.Label(self, text="FEN do estudo").pack(anchor="w", padx=6)
        entry = ttk.Entry(self, textvariable=self.fen_var)
        entry.pack(fill=tk.X, padx=6, pady=(0, 6))
        entry.bind("<Return>", lambda _event: self.apply_fen())

        self.board_widget = InteractiveBoard(
            self,
            mode="play",
            on_move=self.push_move,
            on_status=self.set_status,
            promotion_chooser=self.choose_promotion,
            piece_images=piece_images,
        )
        self.board_widget.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        canvas = self.board_widget.canvas
        canvas.bind("<Left>", lambda _event: self.undo_move())
        canvas.bind("<Right>", lambda _event: self.redo_move())
        canvas.bind("<Home>", lambda _event: self.go_to_start_of_line())
        canvas.bind("<End>", lambda _event: self.go_to_end_of_line())

        move_box = ttk.LabelFrame(self, text="Linha de estudo")
        move_box.pack(fill=tk.BOTH, expand=False, padx=6, pady=(0, 2))
        self.moves_text = tk.Text(move_box, height=5, wrap="word", font=("Consolas", 10), state=tk.DISABLED)
        self.moves_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self._build_engine_section()

    def _build_engine_section(self) -> None:
        """A seção do motor. Sem binário, ela simplesmente não existe (S-33)."""
        if self._analyzer is None:
            return

        caixa = ttk.LabelFrame(self, text=f"Motor ({self._analyzer.path.name})")
        caixa.pack(fill=tk.X, padx=6, pady=(4, 6))

        linha = ttk.Frame(caixa)
        linha.pack(fill=tk.X, padx=6, pady=(6, 0))
        self.btn_analyse = ttk.Button(linha, text="Analisar posição", command=self.analyse)
        self.btn_analyse.pack(side=tk.LEFT)
        ttk.Label(linha, textvariable=self.engine_var).pack(side=tk.LEFT, padx=(10, 0))

        # Barra de vantagem: 0 = pretas ganhando, 100 = brancas. A escala e logistica, e a
        # conversao mora em `Evaluation.advantage_fraction`.
        self.advantage = ttk.Progressbar(caixa, maximum=100.0, value=50.0)
        self.advantage.pack(fill=tk.X, padx=6, pady=(6, 0))
        ttk.Label(caixa, textvariable=self.engine_line_var, wraplength=600, foreground="#555555").pack(
            anchor="w", padx=6, pady=(4, 6)
        )

    # ------------------------------------------------------------------------------ motor

    @property
    def has_engine(self) -> bool:
        return self._analyzer is not None

    def analyse(self) -> None:
        """Avalia a posição atual numa thread, para a interface não travar (S-33)."""
        if self._analyzer is None or self._analysing:
            return

        self._analysing = True
        self.btn_analyse.configure(state=tk.DISABLED)
        self.engine_var.set("Analisando...")
        posicao = self.board.copy(stack=False)
        threading.Thread(target=self._analyse_worker, args=(posicao,), daemon=True).start()

    def _analyse_worker(self, board: chess.Board) -> None:
        assert self._analyzer is not None
        try:
            avaliacao = self._analyzer.analyse(board)
            self.after(0, partial(self._show_evaluation, avaliacao))
        except Exception as exc:
            logger.warning("Falha na análise: %s", exc)
            self.after(0, partial(self._show_engine_error, str(exc)))
        finally:
            self.after(0, self._finish_analysis)

    def _show_evaluation(self, avaliacao: Evaluation) -> None:
        self.engine_var.set(avaliacao.summary())
        self.advantage.configure(value=avaliacao.advantage_fraction() * 100.0)
        self.engine_line_var.set(
            ("Linha: " + " ".join(avaliacao.pv_san)) if avaliacao.pv_san else "Sem lance legal nesta posição."
        )

    def _show_engine_error(self, mensagem: str) -> None:
        self.engine_var.set("O motor não respondeu.")
        self.engine_line_var.set(mensagem)

    def _finish_analysis(self) -> None:
        self._analysing = False
        self.btn_analyse.configure(state=tk.NORMAL)

    # ------------------------------------------------------------------------------ estado

    def set_status(self, text: str = "") -> None:
        turno = "brancas" if self.board.turn else "pretas"
        self.status_var.set(f"{text} | vez: {turno}" if text else f"Vez: {turno}")

    def _new_game(self, board: chess.Board) -> chess.pgn.Game:
        game = chess.pgn.Game()
        game.headers["Event"] = "ChessVisionOFF Study"
        game.headers["Site"] = "Local"
        game.headers["Result"] = "*"
        game.setup(board.copy(stack=False))
        return game

    def _variation_labels(self) -> list[str]:
        board = self.board.copy(stack=False)
        return [f"{idx}. {board.san(child.move)}" for idx, child in enumerate(self.current_node.variations, start=1)]

    def _update_variation_selector(self) -> None:
        labels = self._variation_labels()
        if not labels:
            self.variation_combo.configure(values=(), state="disabled")
            self.variation_var.set("")
            return
        self.variation_combo.configure(values=labels, state="readonly")
        if self.variation_var.get() not in labels:
            self.variation_var.set(labels[0])
        self.variation_combo.current(labels.index(self.variation_var.get()))

    def _selected_variation_index(self) -> int:
        labels = self._variation_labels()
        if not labels:
            return 0
        valor = self.variation_var.get()
        return labels.index(valor) if valor in labels else 0

    def _update_moves_text(self) -> None:
        exporter = chess.pgn.StringExporter(headers=False, variations=True, comments=True)
        texto = self.game.accept(exporter).strip() or "Sem lances."
        self.moves_text.configure(state=tk.NORMAL)
        self.moves_text.delete("1.0", tk.END)
        self.moves_text.insert("1.0", texto)
        self.moves_text.configure(state=tk.DISABLED)

    def refresh(self) -> None:
        self.board = self.current_node.board()
        self.fen_var.set(self.board.fen())
        self._update_moves_text()
        self._update_variation_selector()
        self.board_widget.set_position(self.board.fen())
        self.board_widget.set_last_move(self.current_node.move)

    def _set_board_state(self, board: chess.Board, origin: str, status: str) -> None:
        self.game = self._new_game(board)
        self.current_node = self.game
        self.board = self.current_node.board()
        self.origin_var.set(origin)
        self.refresh()
        self.set_status(status)

    def _load_position(self, fen: str, origin: str, status: str) -> None:
        if not fen:
            messagebox.showwarning("Aviso", "Não ha FEN para carregar no tabuleiro de análise.")
            return
        if not is_valid_fen(fen):
            messagebox.showerror("Erro", "A FEN informada para análise e inválida.")
            return
        self._set_board_state(board_from_fen(fen), origin=origin, status=status)

    # ------------------------------------------------------------------- vínculo com o OCR

    def sync_with_ocr(self, force: bool = False) -> None:
        """Traz a FEN do diagrama selecionado, se o usuário quiser esse acoplamento.

        Silenciosa quando não há FEN válida: é chamada a cada edição de casa no painel de
        resultado, e um `messagebox` de "FEN inválida" no meio de uma correção seria pior
        que não sincronizar.
        """
        if not force and not self.follow_ocr_var.get():
            return
        fen = self._current_fen().strip()
        if not fen or not is_valid_fen(fen):
            return
        self._load_position(fen, origin="Base: OCR selecionado", status="Tabuleiro sincronizado com o OCR.")

    def on_follow_ocr_toggle(self) -> None:
        if self.follow_ocr_var.get():
            self.sync_with_ocr(force=True)
        else:
            self.set_status("Sincronismo com OCR desativado.")

    def load_from_recognized(self) -> None:
        self._load_position(
            self._current_fen().strip(),
            origin="Base: OCR selecionado",
            status="Posição reconhecida carregada no tabuleiro.",
        )

    # ------------------------------------------------------------------------------- ações

    def load_initial_position(self) -> None:
        self.follow_ocr_var.set(False)
        self._set_board_state(chess.Board(), "Base: posição inicial", "Tabuleiro reiniciado na posição inicial.")

    def apply_fen(self) -> None:
        self.follow_ocr_var.set(False)
        self._load_position(
            self.fen_var.get().strip(),
            origin="Base: FEN manual",
            status="FEN aplicada no tabuleiro de análise.",
        )

    def copy_fen(self) -> None:
        janela = self.winfo_toplevel()
        janela.clipboard_clear()
        janela.clipboard_append(self.board.fen())
        self.set_status("FEN do estudo copiada.")

    def flip_board(self) -> None:
        self.flipped_var.set(not self.flipped_var.get())
        self.board_widget.set_flipped(self.flipped_var.get())

    def toggle_turn(self) -> None:
        board = self.board.copy(stack=False)
        board.turn = not board.turn
        self.follow_ocr_var.set(False)
        self._set_board_state(board, "Base: lado a jogar ajustado", "Lado a jogar invertido.")

    def undo_move(self) -> None:
        if self.current_node.parent is None:
            self.set_status("Não ha lances para desfazer.")
            return
        self.current_node = self.current_node.parent
        self.refresh()
        self.set_status("Último lance desfeito.")

    def redo_move(self) -> None:
        if not self.current_node.variations:
            self.set_status("Não ha lances para refazer.")
            return
        idx = max(0, min(self._selected_variation_index(), len(self.current_node.variations) - 1))
        self.current_node = self.current_node.variations[idx]
        self.refresh()
        self.set_status("Lance refeito.")

    def go_to_start_of_line(self) -> None:
        if self.current_node.parent is None:
            self.set_status("Já esta no inicio da linha.")
            return
        while self.current_node.parent is not None:
            self.current_node = self.current_node.parent
        self.refresh()
        self.set_status("Voltou para o inicio da linha.")

    def go_to_end_of_line(self) -> None:
        if not self.current_node.variations:
            self.set_status("Já esta no fim da linha.")
            return
        # A variante escolhida no seletor vale para o primeiro passo; dali em diante segue a
        # linha principal, que e a leitura usual de "ir para o fim".
        primeiro = True
        while self.current_node.variations:
            idx = self._selected_variation_index() if primeiro else 0
            idx = max(0, min(idx, len(self.current_node.variations) - 1))
            self.current_node = self.current_node.variations[idx]
            primeiro = False
        self.refresh()
        self.set_status("Avancou para o fim da linha.")

    def push_move(self, move: chess.Move) -> None:
        san = self.board.san(move)
        existente = next((child for child in self.current_node.variations if child.move == move), None)
        self.current_node = existente if existente is not None else self.current_node.add_variation(move)
        self.refresh()
        self.set_status(f"{san} | {'Variante seguida.' if existente is not None else 'Lance salvo.'}")

    def choose_promotion(self) -> int | None:
        janela = self.winfo_toplevel()
        escolha: dict[str, int | None] = {"piece_type": None}
        dlg = tk.Toplevel(janela)
        dlg.title("Promoção")
        dlg.resizable(False, False)
        dlg.transient(janela)
        dlg.grab_set()

        wrap = ttk.Frame(dlg, padding=12)
        wrap.pack(fill=tk.BOTH, expand=True)
        ttk.Label(wrap, text="Escolha a peça para promoção").pack(anchor="w", pady=(0, 8))

        def _select(piece_type: int) -> None:
            escolha["piece_type"] = piece_type
            dlg.destroy()

        for rotulo, tipo in (("Dama", chess.QUEEN), ("Torre", chess.ROOK), ("Bispo", chess.BISHOP), ("Cavalo", chess.KNIGHT)):
            # `partial` e não `lambda ...=tipo`: aqui ha laco, então a captura por valor e
            # obrigatoria -- e o `partial` a expressa sem enganar o verificador de tipos.
            ttk.Button(wrap, text=rotulo, command=partial(_select, tipo)).pack(fill=tk.X, pady=2)

        ttk.Button(wrap, text="Cancelar", command=dlg.destroy).pack(fill=tk.X, pady=(8, 0))
        janela.wait_window(dlg)
        return escolha["piece_type"]

    # --------------------------------------------------------------------------------- PGN

    def pgn_payload(self) -> str:
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        return self.game.accept(exporter).strip()

    def write_pgn(self, path: Path, append: bool) -> None:
        payload = self.pgn_payload()
        if append and path.exists() and path.stat().st_size > 0:
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n\n")
                handle.write(payload)
                handle.write("\n")
            return
        path.write_text(payload + "\n", encoding="utf-8")

    def save_pgn(self) -> None:
        filename = filedialog.asksaveasfilename(
            title="Salvar estudo em PGN",
            defaultextension=".pgn",
            filetypes=[("PGN", "*.pgn"), ("Todos", "*.*")],
            initialdir=str(self._initial_dir),
        )
        if not filename:
            return

        path = Path(filename)
        append = False
        if path.exists():
            # Três respostas, não duas: acrescentar é o caso comum (um arquivo por livro),
            # e oferecer só "sobrescrever ou cancelar" faria perder análise já salva.
            resposta = messagebox.askyesnocancel(
                "PGN existente",
                "O arquivo já existe.\n\nSim: acrescentar esta análise ao final.\n"
                "Não: sobrescrever o arquivo.\nCancelar: abortar o salvamento.",
            )
            if resposta is None:
                return
            append = bool(resposta)

        try:
            self.write_pgn(path, append=append)
            self.set_status(f"Análise acrescentada em {path.name}." if append else f"PGN salvo em {path.name}.")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao salvar PGN:\n{exc}")
