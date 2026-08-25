"""`cvoff-texto-transcrever` — a janela que transcreve as 123 faixas de referência (S-183).

    cvoff-texto-placar --exportar data/faixas_para_transcrever   # os PNGs, uma vez
    cvoff-texto-transcrever                                      # e então isto

**Por que uma janela, e não um editor de texto.** A transcrição é o portão da Fase 25: 123
faixas, e a medição recusa cada uma que ainda esteja com `conferido: false`. Feita à mão, ela
custa abrir o `.jsonl`, achar a linha certa, abrir o PNG de mesmo número noutra janela, digitar
com aspas escapadas e trocar a marca -- 123 vezes, sem nada que conte quanto falta. Aqui a
imagem e o campo estão lado a lado, `Ctrl+Enter` marca e pula para a próxima pendente, e o
arquivo é gravado na forma exata que o `cvoff-texto-placar` lê.

**O que esta janela deliberadamente não tem: um botão de preencher com OCR.** A referência da
S-183 tem de vir da página impressa. Vinda de um motor, a tabela mediria o motor contra ele
mesmo -- e as três colunas que ela compara (camada, RapidOCR, glifo) deixariam de significar o
que dizem. O único texto pré-preenchido é o que o `--semear` tirou da **camada de texto** do
PDF, e ele vem marcado: enquanto ninguém mudar uma letra, a faixa aparece como `circular`, e é
assim que ela sai na tabela.

O que é do modelo -- navegar, editar, avisar, gravar -- mora em `text/transcricao.py` e é
testado sem abrir Tk. O que sobra aqui é o que só a janela faz.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT
from ..logging_setup import configure_logging
from ..text.transcricao import Item, ReferenciaMudouNoDisco, SessaoDeTranscricao, so_scan
from . import EXIT_BAD_INPUT, EXIT_OK, cli_errors

logger = logging.getLogger(__name__)

REFERENCIA_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_faixa_referencia.jsonl"
PNGS_PADRAO = PROJECT_ROOT / "data" / "faixas_para_transcrever"

ZOOM_MIN = 0.15
ZOOM_MAX = 6.0
ZOOM_PASSO = 1.15


class JanelaDeTranscricao:
    """A janela: a imagem à esquerda, o campo à direita, e o teclado no meio."""

    def __init__(self, root: Any, sessao: SessaoDeTranscricao) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._tk = tk
        self.root = root
        self.sessao = sessao
        self._foto: Any = None
        """A referência viva do `PhotoImage`. Sem ela o Tk coleta a imagem e o canvas fica
        branco -- é a pegadinha clássica, e ela some em silêncio."""
        self._zoom = 1.0
        self._ajustar = True
        self._imagem_atual: Any = None
        self._largura_canvas = 0

        titulo = "Transcrever as faixas de referência · S-183"
        root.title(f"{titulo} — só as de scan" if sessao.filtrada else titulo)
        root.geometry("1440x900")
        root.minsize(900, 600)

        topo = ttk.Frame(root, padding=(10, 8))
        topo.pack(side=tk.TOP, fill=tk.X)
        self.var_progresso = tk.StringVar()
        ttk.Label(topo, textvariable=self.var_progresso, font=("TkDefaultFont", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(topo, text="Próxima pendente  (Ctrl+P)", command=self.ir_para_pendente).pack(side=tk.RIGHT)
        ttk.Button(topo, text="Gravar  (Ctrl+S)", command=self.gravar).pack(side=tk.RIGHT, padx=(0, 6))

        self.corpo = corpo = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        corpo.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        moldura = ttk.Frame(corpo)
        self.canvas = tk.Canvas(moldura, background="#2b2b2b", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        corpo.add(moldura, weight=3)

        painel = ttk.Frame(corpo, padding=(12, 10))
        corpo.add(painel, weight=2)

        self.var_rotulo = tk.StringVar()
        ttk.Label(painel, textvariable=self.var_rotulo, wraplength=420, justify=tk.LEFT).pack(anchor="w")

        self.var_semente = tk.StringVar()
        ttk.Label(
            painel, textvariable=self.var_semente, wraplength=420, justify=tk.LEFT, foreground="#7a7a7a"
        ).pack(anchor="w", pady=(6, 8))

        ttk.Label(painel, text="O que está impresso nesta faixa:").pack(anchor="w")
        # `expand=False`: o campo de uma legenda tem duas ou três linhas, e deixá-lo crescer
        # empurraria a imagem -- que é o que se está lendo -- para um terço da janela.
        self.campo = tk.Text(painel, height=8, wrap=tk.WORD, font=("TkDefaultFont", 12), undo=True)
        self.campo.pack(fill=tk.X, expand=False, pady=(4, 8))

        linha = ttk.Frame(painel)
        linha.pack(fill=tk.X)
        self.var_conferido = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            linha, text="conferido contra a página", variable=self.var_conferido, command=self._marcar
        ).pack(side=tk.LEFT)
        self.botao_semente = ttk.Button(linha, text="restaurar semente", command=self.restaurar_semente)
        self.botao_semente.pack(side=tk.RIGHT)

        navegacao = ttk.Frame(painel)
        navegacao.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(navegacao, text="◀ anterior", command=self.anterior).pack(side=tk.LEFT)
        ttk.Button(navegacao, text="próxima ▶", command=self.proximo).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            navegacao, text="marcar e seguir  (Ctrl+Enter)", command=self.marcar_e_seguir
        ).pack(side=tk.RIGHT)

        self.var_status = tk.StringVar(value="Nada gravado ainda nesta sessão.")
        ttk.Label(root, textvariable=self.var_status, padding=(10, 6), anchor="w").pack(side=tk.BOTTOM, fill=tk.X)

        for sequencia, acao in (
            ("<Control-s>", lambda _e: self.gravar()),
            ("<Control-S>", lambda _e: self.gravar()),
            ("<Control-p>", lambda _e: self.ir_para_pendente()),
            ("<Control-P>", lambda _e: self.ir_para_pendente()),
            ("<Control-Return>", lambda _e: self.marcar_e_seguir()),
            ("<Alt-Right>", lambda _e: self.proximo()),
            ("<Alt-Left>", lambda _e: self.anterior()),
            ("<Prior>", lambda _e: self.anterior()),
            ("<Next>", lambda _e: self.proximo()),
        ):
            root.bind_all(sequencia, _engolindo(acao))

        self.canvas.bind("<MouseWheel>", self._roda)
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<Double-Button-1>", lambda _e: self._ajustar_a_janela())
        self.canvas.bind("<Configure>", self._redimensionou)
        root.protocol("WM_DELETE_WINDOW", self.fechar)

        root.after(50, self._posicionar_divisor)

        # Onde o trabalho parou já é a posição inicial da sessão -- a primeira pendente da vista.
        self._mostrar()

    # ------------------------------------------------------------------ o que a janela mostra

    def _mostrar(self) -> None:
        item = self.sessao.atual
        self.campo.delete("1.0", self._tk.END)
        self.campo.insert("1.0", item.faixa.texto)
        self.campo.edit_reset()
        self.var_conferido.set(item.faixa.conferido)
        self.var_rotulo.set(item.rotulo)

        if item.faixa.semeado_de:
            igual = "  (ainda intocada — a coluna `camada` fica circular)" if item.faixa.intocada else ""
            self.var_semente.set(f"semente da camada de texto:{igual}\n{item.faixa.texto_semente or '(vazia)'}")
            self.botao_semente.state(["!disabled"])
        else:
            self.var_semente.set("sem semente: scan puro, e é por isso que esta faixa decide a fase.")
            self.botao_semente.state(["disabled"])

        self._atualizar_progresso()
        self._carregar_imagem(item)
        self.campo.focus_set()

    def _posicionar_divisor(self) -> None:
        """Cinco oitavos da largura para a imagem, e o resto para o formulário.

        O `weight` do `PanedWindow` só reparte o que a janela **ganha** ao ser redimensionada;
        a posição inicial do divisor vem do tamanho que os widgets pedem, e o formulário pede
        largura demais. Sem isto a imagem abre em pouco mais de um terço da janela, que é a
        parte que se está lendo.

        **E ele se reagenda enquanto a janela não estiver no ar.** Antes do primeiro mapeamento
        o Tk responde `1` a `winfo_width`, e um divisor colocado em 62% de 1 pixel colapsa o
        lado da imagem a zero -- que foi exatamente o que aconteceu na primeira versão disto.
        """
        try:
            largura = self.corpo.winfo_width()
            if largura < 200:
                self.root.after(50, self._posicionar_divisor)
                return
            self.corpo.sashpos(0, int(largura * 0.625))
        except self._tk.TclError:  # pragma: no cover - janela fechada antes de o `after` correr
            return
        self._desenhar()

    def _atualizar_progresso(self) -> None:
        s = self.sessao
        circulares = f" · {s.circulares} circular(es)" if s.circulares else ""
        if s.filtrada:
            # Com filtro, o placar que interessa é o da vista -- mas o do arquivo continua ao
            # lado: é o arquivo que se grava, e é sobre ele que o `cvoff-texto-placar` mede.
            self.var_progresso.set(
                f"faixa {s.indice + 1}   ·   scan: {s.conferidas_visiveis} de {s.total_visivel} "
                f"conferidas, {s.total_visivel - s.conferidas_visiveis} pendentes   ·   "
                f"no arquivo: {s.conferidas} de {s.total}{circulares}"
            )
            return
        self.var_progresso.set(
            f"faixa {s.indice + 1} de {s.total}   ·   {s.conferidas} conferidas, "
            f"{s.total - s.conferidas} pendentes{circulares}"
        )

    def _carregar_imagem(self, item: Item) -> None:
        self.canvas.delete("all")
        self._imagem_atual = None
        if item.imagem is None or not item.imagem.exists():
            self.canvas.create_text(
                20, 20, anchor="nw", fill="#dddddd", width=600,
                text=(
                    "O PNG desta faixa não está na pasta.\n\n"
                    "Rode `cvoff-texto-placar --exportar data/faixas_para_transcrever` para "
                    "gerar as 123 imagens -- é a mesma banda que os motores leem."
                ),
            )
            return
        from PIL import Image  # noqa: PLC0415 - import tardio: a janela abre sem ele até aqui

        self._imagem_atual = Image.open(item.imagem)
        self._imagem_atual.load()
        self._ajustar = True
        self._desenhar()

    def _desenhar(self) -> None:
        if self._imagem_atual is None:
            return
        from PIL import Image, ImageTk  # noqa: PLC0415 - idem

        largura_canvas = max(self.canvas.winfo_width(), 1)
        altura_canvas = max(self.canvas.winfo_height(), 1)
        if self._ajustar:
            self._zoom = min(
                largura_canvas / self._imagem_atual.width,
                altura_canvas / self._imagem_atual.height,
            )
            self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom))

        largura = max(1, int(self._imagem_atual.width * self._zoom))
        altura = max(1, int(self._imagem_atual.height * self._zoom))
        redimensionada = self._imagem_atual.resize((largura, altura), resample=Image.Resampling.LANCZOS)
        self._foto = ImageTk.PhotoImage(redimensionada)
        self.canvas.delete("all")
        self.canvas.create_image(largura_canvas // 2, altura_canvas // 2, image=self._foto, anchor="center")
        self.canvas.configure(scrollregion=(0, 0, largura, altura))

    def _redimensionou(self, evento: Any) -> None:
        # Só redesenha quando a largura mudou de fato: o `<Configure>` do Tk dispara também por
        # movimento da janela, e redesenhar uma imagem de 1,4 MP a cada evento trava o arrasto.
        if evento.width != self._largura_canvas:
            self._largura_canvas = evento.width
            self._desenhar()

    def _roda(self, evento: Any) -> None:
        self._ajustar = False
        fator = ZOOM_PASSO if evento.delta > 0 else 1 / ZOOM_PASSO
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom * fator))
        self._desenhar()

    def _ajustar_a_janela(self) -> None:
        self._ajustar = True
        self._desenhar()

    # ------------------------------------------------------------------ o que a janela grava

    def _coletar(self) -> None:
        """Passa o que está nos widgets para o modelo. Chamado antes de sair da faixa."""
        self.sessao.editar(
            texto=self.campo.get("1.0", self._tk.END),
            conferido=bool(self.var_conferido.get()),
        )

    def _marcar(self) -> None:
        self._coletar()
        self._atualizar_progresso()

    def gravar(self) -> bool:
        from tkinter import messagebox  # noqa: PLC0415 - import tardio: só quem grava precisa

        self._coletar()
        try:
            self.sessao.salvar()
        except ReferenciaMudouNoDisco as exc:
            messagebox.showerror("A referência mudou no disco", str(exc))
            self.var_status.set("NÃO gravado: o arquivo mudou no disco desde que esta janela abriu.")
            return False
        except OSError as exc:
            messagebox.showerror("Não foi possível gravar", str(exc))
            self.var_status.set(f"NÃO gravado: {exc}")
            return False
        s = self.sessao
        self.var_status.set(
            f"Gravado em {s.referencia}: {s.conferidas} de {s.total} conferidas. " + " ".join(s.avisos())
        )
        self._atualizar_progresso()
        return True

    def _sair_da_faixa(self) -> None:
        """Recolhe o que foi digitado e grava, se alguma coisa mudou.

        Gravar a cada troca de faixa, e não só no fim: quem transcreve 123 imagens não deveria
        perder a sessão inteira porque a janela fechou sozinha na centésima.
        """
        self._coletar()
        if self.sessao.sujo:
            self.gravar()

    def proximo(self) -> None:
        self._sair_da_faixa()
        if self.sessao.proximo():
            self._mostrar()

    def anterior(self) -> None:
        self._sair_da_faixa()
        if self.sessao.anterior():
            self._mostrar()

    def ir_para_pendente(self) -> None:
        self._sair_da_faixa()
        if self.sessao.proxima_pendente():
            self._mostrar()
        else:
            self.var_status.set(self._recado_de_fim())

    def marcar_e_seguir(self) -> None:
        self.var_conferido.set(True)
        self._sair_da_faixa()
        seguiu = self.sessao.proxima_pendente()
        self._mostrar()
        if not seguiu:
            self.var_status.set(self._recado_de_fim())

    def _recado_de_fim(self) -> str:
        s = self.sessao
        if s.filtrada:
            return (
                f"Não sobrou pendente entre as {s.total_visivel} de scan. No arquivo ainda "
                f"faltam {s.total - s.conferidas} -- reabra sem `--so-scan` para elas."
            )
        return f"As {s.total} estão conferidas. Rode `cvoff-texto-placar` para a tabela da S-183."

    def restaurar_semente(self) -> None:
        if self.sessao.restaurar_semente():
            item = self.sessao.atual
            self.campo.delete("1.0", self._tk.END)
            self.campo.insert("1.0", item.faixa.texto)

    def fechar(self) -> None:
        from tkinter import messagebox  # noqa: PLC0415 - idem

        self._coletar()
        if self.sessao.sujo and not self.gravar():
            if not messagebox.askokcancel("Fechar sem gravar?", "O que você digitou não foi para o disco."):
                return
        self.root.destroy()


def _engolindo(acao: Any) -> Any:
    """Devolve `"break"` para o Tk não repassar o atalho ao `Text` que está com o foco."""

    def tratador(evento: Any) -> str:
        acao(evento)
        return "break"

    return tratador


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cvoff-texto-transcrever",
        description="Janela para transcrever as faixas de referência da S-183, com o PNG ao lado.",
        epilog=(
            "A referencia tem de vir da pagina impressa: esta janela nao tem, e nao vai ter, um "
            "botao de preencher com OCR. Exporte os PNGs antes com "
            "`cvoff-texto-placar --exportar`."
        ),
    )
    parser.add_argument("--referencia", type=Path, default=REFERENCIA_PADRAO)
    parser.add_argument("--pngs", type=Path, default=PNGS_PADRAO, help="A pasta do `--exportar`.")
    parser.add_argument(
        "--so-scan",
        action="store_true",
        help=(
            "Navega so pelas faixas de livro sem camada de texto -- as que decidem a fase. As "
            "outras continuam no arquivo e continuam sendo gravadas; o filtro e da navegacao."
        ),
    )
    return parser.parse_args(argv)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()

    if not args.referencia.exists():
        logger.error(
            "%s não existe. Semeie primeiro com `cvoff-texto-placar --semear`.", args.referencia
        )
        return EXIT_BAD_INPUT

    sessao = SessaoDeTranscricao.carregar(
        args.referencia, args.pngs, filtro=so_scan if args.so_scan else None
    )
    if not sessao.total:
        logger.warning("%s está vazio: não há faixa para transcrever.", args.referencia)
        return EXIT_OK
    if args.so_scan and not sessao.total_visivel:
        # Sair em vez de abrir uma janela vazia: sem faixa de scan não há o que fazer aqui, e
        # uma janela em branco não diz por quê.
        logger.warning(
            "Nenhuma das %d faixas de %s é de livro sem camada de texto. "
            "Rode sem `--so-scan`.", sessao.total, args.referencia,
        )
        return EXIT_OK
    if args.so_scan:
        logger.info(
            "Só as de scan: %d faixas, %d ainda pendentes. As outras %d continuam no arquivo.",
            sessao.total_visivel,
            sessao.total_visivel - sessao.conferidas_visiveis,
            sessao.total - sessao.total_visivel,
        )
    sem_png = sum(1 for item in sessao.itens if item.imagem is None)
    if sem_png:
        logger.warning(
            "%d de %d faixas não têm PNG em %s. Rode `cvoff-texto-placar --exportar %s`.",
            sem_png, sessao.total, args.pngs, args.pngs,
        )

    import tkinter as tk  # noqa: PLC0415 - import tardio: o módulo importa sem display

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        # Sem display não é defeito do programa: é um ambiente onde esta janela não abre, e o
        # `.jsonl` continua editável à mão.
        logger.error("Não foi possível abrir a janela (%s). Este comando precisa de uma sessão gráfica.", exc)
        return EXIT_BAD_INPUT

    try:
        from ..ui.theme import apply_theme  # noqa: PLC0415 - idem

        apply_theme(root)
    except Exception:  # noqa: BLE001 - aparência nunca é motivo de a ferramenta não abrir (S-53)
        logger.debug("Tema não aplicado; seguindo com o ttk puro.", exc_info=True)

    JanelaDeTranscricao(root, sessao)
    root.mainloop()

    logger.info(
        "%d de %d faixas conferidas em %s.", sessao.conferidas, sessao.total, args.referencia
    )
    for aviso in sessao.avisos():
        logger.warning("%s", aviso)
    return EXIT_OK


__all__ = ["JanelaDeTranscricao", "main", "parse_args"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
