"""Os parâmetros da varredura e o acumulador da fila, sem toolkit nenhum (S-116/S-119/S-503).

Duas decisões, e as duas eram puras dentro de `ui/review_panel.py`:

1. **`PedidoDeVarredura`** -- o que a janela tem configurado quando alguém manda varrer: livro,
   modelo, rótulos, DPI, ordem de leitura, faixa de páginas e o gate de aceitação. É um
   `dataclass` congelado e sempre foi; o que ele nunca teve foi um endereço fora do Tk.
2. **`AcumuladorDaFila`** -- o `ReviewQueueBuilder` construído **tarde**, na primeira alimentação.
   Isto é a S-116 virada forma: o construtor roda na thread da janela, junto com o clique, e ler
   3.936 linhas de `labels.csv` ali é o defeito que ela mediu. `feed` já roda na thread da
   varredura, e é lá que o disco pode ser tocado.

**Por que elas mudaram de arquivo.** `ui/review_panel.py` importa `tkinter` na primeira linha do
corpo -- `ReviewPanel` herda de `ttk.Frame` --, e o segundo frontend precisa exatamente destas
duas coisas e de widget nenhum. Copiá-las daria duas respostas para "quando o `labels.csv` é
lido", e a errada não falha: ela só torna o clique lento numa das duas janelas, que é o defeito
mais fácil de não atribuir a ninguém.

**O que ficou de fora, e a fronteira é essa.** O *sumidouro* -- quem recebe cada diagrama da
varredura e avisa o painel do progresso -- continua em cada frontend, porque o aviso é a única
parte dele que é de toolkit e é a parte que não pode errar: no Tk é `panel.after(0, ...)` e no Qt
é um sinal, e os dois existem pela mesma razão -- **tocar num widget da thread da varredura
derruba o programa**. Um sumidouro compartilhado teria de esconder essa diferença atrás de uma
função, e a função esconderia justamente o que quem lê precisa ver.

`ui/review_panel.py` reexportava o `ScanRequest`, e saiu no corte do Tk (S-506). Quem consome
agora é `qt/painel_de_revisao.py` e `qt/janela.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import ACCEPT_MIN_CONFIDENCE, DEFAULT_MAX_BOARDS, DEFAULT_READING_ORDER, OrientationMode, ReadingOrder
from ..pdf_to_pgn import ScannedDiagram
from ..review_queue import ReviewQueue, ReviewQueueBuilder, rare_classes_from_labels

__all__ = ["AcumuladorDaFila", "PedidoDeVarredura", "ScanRequest"]


@dataclass(frozen=True)
class PedidoDeVarredura:
    """Os parâmetros da varredura, como a janela principal os tem configurados."""

    pdf_path: Path
    model_path: Path
    labels_csv: Path
    dpi: int = 220
    max_boards_per_page: int = DEFAULT_MAX_BOARDS
    orientation: OrientationMode = "auto"
    reading_order: ReadingOrder = DEFAULT_READING_ORDER
    start_page: int = 0
    end_page: int | None = None
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE


ScanRequest = PedidoDeVarredura
"""O nome antigo, que `app_tkinter.py` e a Galeria passam adiante. Um `alias` e não uma segunda
classe: `isinstance` tem de responder a mesma coisa nos dois lados enquanto os dois existirem."""


class AcumuladorDaFila:
    """O `ReviewQueueBuilder` da varredura, construído na primeira alimentação e não antes.

    **O adiamento é o item, e ele tem medida.** `rare_classes_from_labels` lê o `labels.csv`
    inteiro; o construtor do sumidouro roda na thread da janela, junto com o clique. Ler 3.936
    linhas de CSV para desenhar um botão cinza foi o defeito da S-116, e a cura é esta: o primeiro
    `feed` já está na thread da varredura, e é lá que o disco é tocado.

    **`pronta()` devolve `None` quando nada foi alimentado**, e a distinção não é zelo: uma
    varredura retomada que não achou página nova (S-120) alimentaria zero diagramas, e uma fila
    vazia entregue por cima da existente apagaria o trabalho da sessão anterior. "Nada lido, nada
    entregue" é a regra, e ela mora aqui para os dois frontends não a escreverem cada um do seu
    jeito.
    """

    def __init__(self, pedido: PedidoDeVarredura, *, cache_dir: Path) -> None:
        self._pedido = pedido
        self._cache_dir = Path(cache_dir)
        self._construtor: ReviewQueueBuilder | None = None

    def feed(self, scanned: ScannedDiagram) -> None:
        """Um diagrama lido pela varredura. **Roda na thread dela**, e é onde o disco é tocado."""
        if self._construtor is None:
            self._construtor = ReviewQueueBuilder(
                self._pedido.pdf_path,
                cache_dir=self._cache_dir,
                rare_classes=rare_classes_from_labels(self._pedido.labels_csv),
                accept_threshold=self._pedido.accept_threshold,
            )
        self._construtor.feed(scanned)

    def vazio(self) -> bool:
        """Se nada foi alimentado. Ver `pronta`."""
        return self._construtor is None

    def paginas(self) -> frozenset[int]:
        """As páginas que a passada de fato visitou.

        Elas viajam junto da fila porque é o que impede a fusão de encurtá-la: a varredura do
        livro retoma de onde parou (S-120), e sem dizer quais páginas ela viu, `merge_queues`
        reduziria a fila às páginas novas.
        """
        return frozenset() if self._construtor is None else frozenset(self._construtor.pages)

    def pronta(self) -> ReviewQueue | None:
        """A fila montada, ou `None` quando nada foi alimentado."""
        return None if self._construtor is None else self._construtor.finish()
