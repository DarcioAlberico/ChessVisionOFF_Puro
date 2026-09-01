"""Ponto de entrada da janela em PyQt6 (S-500/S-505).

    uv sync
    uv run python app_pyqt.py

**Ainda não substitui o `app_tkinter.py`, e a diferença agora é só de decisão.** As sete abas
estão montadas e ligadas, e esta janela escreve: corrige, grava amostra, regrava linha do
dataset, treina e exporta. O que falta é o **corte**, que é do dono -- enquanto ele não vem, as
duas janelas abrem o mesmo `service.py` e a de Tk continua sendo a do produto. O porquê de cada
metade está em `chess_diagram_ocr/qt/__init__.py`.

O arquivo é fino de propósito, e é a mesma regra da S-31 que decidiu o tamanho do
`app_tkinter.py`: o que dá para testar mora no pacote. O que sobra aqui é o que só o processo
pode fazer -- ler os argumentos, ligar o log, montar a `QApplication` e o auto-teste que
responde, numa instalação nova, se esta metade do projeto funciona nesta máquina.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import multiprocessing as mp
import os
import sys
from pathlib import Path

from chess_diagram_ocr.config import DEFAULT_MODEL_PATH, DEFAULT_PDF_DIR, find_default_pdf_path
from chess_diagram_ocr.logging_setup import configure_logging, default_log_file

logger = logging.getLogger(__name__)

FALTA_O_PYQT = (
    "A versão de teste precisa do PyQt6, que é um extra do projeto e não vem no ambiente padrão.\n"
    "Instale com:\n"
    "    uv sync --extra qt\n"
    "ou, num venv gerenciado à mão:\n"
    "    pip install \"PyQt6>=6.6\""
)
"""A mensagem que falta quando a biblioteca falta.

Em pt-BR e com o comando escrito, porque o `ModuleNotFoundError: No module named 'PyQt6'` que
apareceria no lugar dela é verdadeiro e inútil: ele nomeia o módulo e não diz que existe um
extra declarado no `pyproject.toml` exatamente para isso."""

CODIGO_SEM_QT = 6
"""Distinto dos códigos do auto-teste do produto (1 falha, 2 PDF, 3 checkpoint, 4 treino,
5 pele): "o Qt não montou" é uma quinta resposta, e colapsá-la em 1 esconderia a única causa
que se conserta com um comando."""


def tem_pyqt() -> bool:
    return importlib.util.find_spec("PyQt6") is not None


def selftest(
    pdf: Path | None = None, page_index: int = 0, *, caminho_do_cache: Path | None = None
) -> int:
    """Monta a janela sem mostrar, abre um livro e marca uma página. `0` se funciona.

    `caminho_do_cache` é para a **suíte**, e `None` é o produto: abrir um livro abre o cache de
    posições, e sem esta porta o teste que exercita o auto-teste cria o
    `data/games_positions.sqlite` no checkout de quem o roda. É a guarda da S-415 que cobra, e a
    lista de escrita legítima dela existe para o que não tem porta -- este tem.

    **Mede o que só esta metade tem.** O pipeline (torch, detecção, decodificação) já é medido
    por `app_tkinter.py --selftest`, e repeti-lo aqui responderia de novo uma pergunta que já
    tem dono. O que falta responder é se o Qt sobe nesta máquina, se a janela monta e se ela
    consegue renderizar e marcar uma página -- que é a parte que um `.zip` numa máquina limpa
    quebra sem dizer nada.

    Roda com a plataforma `offscreen`: um auto-teste que exige servidor gráfico não roda na CI,
    e um auto-teste que não roda na CI é uma promessa.
    """
    if not tem_pyqt():
        logger.error("Auto-teste: %s", FALTA_O_PYQT)
        return CODIGO_SEM_QT

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from chess_diagram_ocr.detection import detect_diagrams_in_pdf_page
    from chess_diagram_ocr.qt.janela import JanelaPrincipal

    caminho = pdf or find_default_pdf_path()
    if caminho is None:
        logger.error("Auto-teste sem PDF: ponha um arquivo em %s e rode de novo.", DEFAULT_PDF_DIR)
        return 2

    aplicacao = QApplication.instance() or QApplication([])
    try:
        janela = JanelaPrincipal(caminho_do_cache=caminho_do_cache)
        janela.abrir_pdf(Path(caminho))
        # O visualizador é do painel de PDF desde a S-505, quando a janela virou coordenadora
        # das sete abas em vez de ser ela própria o visualizador.
        pagina = janela.pdf.page_rgb
        if pagina is None:
            logger.error("Auto-teste: a janela montou, mas a página %d não renderizou.", page_index)
            return 2
        candidatos = detect_diagrams_in_pdf_page(Path(caminho), page_index, pagina)
    except Exception:
        logger.exception("Auto-teste: a janela do Qt não montou.")
        return CODIGO_SEM_QT
    finally:
        del aplicacao

    logger.info(
        "Auto-teste (PyQt): %s, página %d — %d diagrama(s) marcado(s). O checkpoint em %s %s.",
        Path(caminho).name,
        page_index,
        len(candidatos),
        DEFAULT_MODEL_PATH,
        "existe" if Path(DEFAULT_MODEL_PATH).exists() else "NÃO existe, e sem ele a leitura não roda",
    )
    # Zero diagrama não é falha: há páginas de prosa. O que se afirma aqui é que o caminho
    # inteiro -- Qt, janela, render, detecção -- rodou sem estourar.
    return 0


def main() -> None:
    # A mesma guarda do `app_tkinter.py`: num bundle congelado, `spawn` reexecuta o próprio
    # executável para criar cada filho, e sem isto cada filho abriria outra janela. Fora do
    # bundle é uma chamada sem efeito.
    mp.freeze_support()

    parser = argparse.ArgumentParser(description="Versão de teste da interface, em PyQt6.")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="monta a janela sem mostrar, abre um PDF e sai. Para conferir uma instalação nova.",
    )
    parser.add_argument("--pdf", type=Path, default=None, help="livro a abrir; sem isto, o primeiro de PDF/.")
    parser.add_argument("--page", type=int, default=0, help="página do auto-teste (base 0).")
    args = parser.parse_args()

    configure_logging(log_file=default_log_file())
    if args.selftest:
        raise SystemExit(selftest(args.pdf, args.page))

    if not tem_pyqt():
        # `print` **e** log: quem roda num terminal precisa ler agora, e quem roda por atalho
        # precisa que fique escrito. É a mesma razão da S-127.
        print(FALTA_O_PYQT, file=sys.stderr)
        logger.error("A janela em Qt não abriu: %s", FALTA_O_PYQT)
        raise SystemExit(CODIGO_SEM_QT)

    # **Antes da `QApplication`, e é a única coisa que tem de ser aqui** (S-501). A política de
    # arredondamento de escala é lida na construção dela; depois disso a chamada não tem efeito, e
    # em 125% o Qt arredonda para 100% e desenha a janela esticada -- o borrão da S-148 por outro
    # caminho. É a mesma pré-condição que `plataforma.consciencia_de_dpi` tem do lado do Tk.
    from chess_diagram_ocr.qt.plataforma import politica_de_escala

    politica_de_escala()

    from PyQt6.QtWidgets import QApplication

    from chess_diagram_ocr.qt.janela import JanelaPrincipal

    logger.info("Iniciando a janela em Qt (PyQt6).")
    try:
        aplicacao = QApplication(sys.argv)
        janela = JanelaPrincipal()
        # **Mostrar antes de abrir o livro.** O "ajustar à página" mede a área visível, e antes
        # do `show()` ela ainda é a do tamanho pedido e não a que o gerenciador de janelas deu:
        # o livro nasceria enquadrado para uma janela que não é esta.
        janela.show()
        if args.pdf is not None:
            janela.abrir_pdf(args.pdf)
        else:
            janela.abrir_livro_padrao()
        raise SystemExit(aplicacao.exec())
    except SystemExit:
        raise
    except Exception:
        # Sem isto uma exceção aqui sobe para o `sys.excepthook` e escreve em `stderr`, que num
        # processo sem console não vai a lugar nenhum: o arquivo de log existiria e a única
        # falha que ninguém consegue diagnosticar continuaria fora dele (S-127).
        logger.exception("A janela de teste não abriu.")
        raise


if __name__ == "__main__":
    main()
