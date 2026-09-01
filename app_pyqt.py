"""Ponto de entrada da janela do produto, em PyQt6 (S-500/S-505/S-506).

    uv sync
    uv run python app_pyqt.py

**É a janela do produto desde o corte do Tk** (S-506). O `app_tkinter.py` que dividia este papel
foi apagado no mesmo dia em que a paridade fechou, e com ele os 28 módulos de `ui/` acoplados ao
toolkit; o PyQt6 deixou de ser o extra `qt` e virou dependência de base. O porquê de cada metade
está em `chess_diagram_ocr/qt/__init__.py`.

O arquivo é fino de propósito, e é a mesma regra da S-31 que decidia o tamanho do arquivo de
entrada anterior: o que dá para testar mora no pacote. O que sobra aqui é o que só o processo pode
fazer -- ler os argumentos, ligar o log, montar a `QApplication` e o auto-teste que responde, numa
instalação nova, se o projeto funciona nesta máquina.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import multiprocessing as mp
import os
import sys
from pathlib import Path

from chess_diagram_ocr.config import (
    DEFAULT_MODEL_PATH,
    DEFAULT_PDF_DIR,
    PROJECT_ROOT,
    find_default_pdf_path,
)
from chess_diagram_ocr.logging_setup import configure_logging, default_log_file
from chess_diagram_ocr.ui import pele

logger = logging.getLogger(__name__)

FALTA_O_PYQT = (
    "A janela precisa do PyQt6, que é dependência do projeto e não está neste ambiente.\n"
    "Instale com:\n"
    "    uv sync\n"
    "ou, num venv gerenciado à mão:\n"
    "    pip install \"PyQt6>=6.6\""
)
"""A mensagem que falta quando a biblioteca falta.

Em pt-BR e com o comando escrito, porque o `ModuleNotFoundError: No module named 'PyQt6'` que
apareceria no lugar dela é verdadeiro e inútil: ele nomeia o módulo e não diz o que rodar.

**O comando mudou no corte do Tk (S-506), e a frase ficou mentindo.** Enquanto o Qt era o segundo
frontend ele era o extra `qt`, e esta mensagem mandava `uv sync --extra qt`. O extra saiu do
`pyproject.toml` quando o PyQt6 virou dependência de base -- e pedir um extra que o projeto não
declara não instala coisa nenhuma. A frase continuou dizendo o contrário por um mês, com um teste
afirmando o texto errado: uma guarda fixando a instrução quebrada é pior que guarda nenhuma."""

CODIGO_SEM_QT = 6
"""Distinto dos outros códigos de saída (1 falha, 2 PDF, 3 checkpoint, 4 treino, 5 pele): "o Qt
não montou" é uma resposta própria, e colapsá-la em 1 esconderia a única causa que se conserta com
um comando.

**Os outros cinco ficaram sem dono no corte do Tk e voltaram aqui** (S-506): quem media o pipeline
-- torch, checkpoint, treino, peles -- era o `--selftest` do arquivo de entrada que o corte apagou,
e por um mês o `QUICKSTART.md` documentou códigos que nada mais podia devolver. Ver `selftest`."""


def tem_pyqt() -> bool:
    return importlib.util.find_spec("PyQt6") is not None


def selftest(pdf: Path | None = None, page_index: int = 0) -> int:
    """Abre um livro, monta a janela e reconhece uma página, sem mostrar nada. `0` se funciona.

    Existe por causa do bundle da S-55. Um `.exe` sem console não tem como dizer "aqui funciona":
    se ele abrir e o torch estiver faltando, o sintoma é uma janela que some. Um auto-teste que
    grava no log responde à única pergunta que interessa numa máquina limpa -- *esta instalação lê
    um diagrama?* -- em vez de deixar a pessoa descobrir isso ao perder uma correção.

    **Ele mede o caminho inteiro de novo, e é uma dívida do corte do Tk que se paga aqui (S-506).**
    Enquanto havia duas janelas, esta metade media só o que era dela -- *o Qt sobe? a janela monta?
    a página desenha?* -- e delegava o pipeline ao `app_tkinter.py --selftest`, "que já tem dono".
    O corte apagou aquele dono e ninguém notou: os códigos 1, 3, 4 e 5 continuaram documentados no
    `QUICKSTART.md` e no README, e nada mais podia devolvê-los.

    Os códigos, na ordem em que ele os descobre:

        6  o PyQt6 não está instalado, ou a janela não montou
        2  não há PDF, ou o que há não abre
        3  não há checkpoint, ou ele existe e não carrega
        1  a página não foi reconhecida
        4  a leitura funciona e o caminho de TREINO não montou
        5  alguma pele registrada não monta o cromo

    **A ordem responde duas perguntas diferentes, e a da instalação vem primeiro** (Fase 18): se o
    checkpoint não carrega, isso é verdade sobre a instalação e não depende de qual PDF a pessoa
    escolheu. Só depois vem "e este arquivo dá para abrir?".

    Roda com a plataforma `offscreen`: um auto-teste que exige servidor gráfico não roda na CI, e
    um auto-teste que não roda na CI é uma promessa.
    """
    if not tem_pyqt():
        logger.error("Auto-teste: %s", FALTA_O_PYQT)
        return CODIGO_SEM_QT

    caminho = pdf or find_default_pdf_path()
    if caminho is None:
        logger.error(
            "Auto-teste sem PDF: ponha um arquivo em %s (ao lado do executável) e rode de novo.",
            DEFAULT_PDF_DIR,
        )
        return 2

    from chess_diagram_ocr.board_detection import NoBoardDetectedError
    from chess_diagram_ocr.cli import message_for
    from chess_diagram_ocr.config import DEFAULT_MAX_BOARDS, DEFAULT_ORIENTATION_MODE
    from chess_diagram_ocr.logging_setup import onde_esta_o_rastro
    from chess_diagram_ocr.pdf_io import get_pdf_page_count
    from chess_diagram_ocr.service import OcrService, RecognitionOptions

    modelo = Path(DEFAULT_MODEL_PATH)
    if not modelo.exists():
        logger.error("Auto-teste sem checkpoint em %s: o programa abre, mas não lê nada.", modelo)
        return 3

    logger.info("Auto-teste: %s, página %d.", Path(caminho).name, page_index)
    servico = OcrService(model_path=modelo)

    # Passo próprio porque **classificar exige saber onde falhou**: dentro do `except` do
    # reconhecimento, um checkpoint truncado saía com 1 -- "o programa falhou" -- e um traceback
    # em inglês, quando quem falhou foi um arquivo que a pessoa consegue trocar.
    try:
        with servico.model_session(modelo):
            pass
    except Exception as exc:  # noqa: BLE001 - o que o torch levanta aqui não tem tipo próprio
        logger.exception("Auto-teste: o checkpoint não pôde ser lido.")
        logger.error(
            "Auto-teste: o checkpoint em %s existe mas não pôde ser lido (%s). Ele pode estar "
            "truncado, ter vindo pela metade, ou ser de outra arquitetura -- ver `arch_version`. %s",
            modelo,
            message_for(exc),
            onde_esta_o_rastro(),
        )
        return 3

    try:
        get_pdf_page_count(caminho)
    except Exception as exc:  # noqa: BLE001 - o `pymupdf` levanta a sua própria família aqui
        logger.exception("Auto-teste: o PDF não pôde ser aberto.")
        logger.error(
            "Auto-teste: não foi possível abrir %s (%s).", Path(caminho).name, message_for(exc)
        )
        return 2

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from chess_diagram_ocr.qt.janela import JanelaPrincipal

    aplicacao = QApplication.instance() or QApplication([])
    try:
        janela = JanelaPrincipal(servico=servico)
        janela.abrir_pdf(Path(caminho))
        # **Ir à página pedida, e não à que o estado lembra** (S-506): desde que a janela restaura
        # o livro e a página da sessão anterior, abrir o livro não deixa mais o auto-teste na
        # página 0 -- e `--page 80` mediria outra folha sem dizer nada.
        janela.pdf.ir_para_pagina(page_index)
        # O visualizador é do painel de PDF desde a S-505, quando a janela virou coordenadora das
        # abas em vez de ser ela própria o visualizador.
        pagina = janela.pdf.page_rgb
        if pagina is None:
            logger.error("Auto-teste: a janela montou, mas a página %d não renderizou.", page_index)
            return 2
        peles_quebradas = janela.provar_as_peles()
    except Exception:
        logger.exception("Auto-teste: a janela do Qt não montou.")
        return CODIGO_SEM_QT
    finally:
        del aplicacao

    try:
        itens = servico.recognize_page(
            Path(caminho),
            page_index,
            options=RecognitionOptions(
                max_boards=DEFAULT_MAX_BOARDS, orientation=DEFAULT_ORIENTATION_MODE
            ),
        )
    except NoBoardDetectedError:
        # **Página sem diagrama não é instalação quebrada, e é o caso comum** (S-506). O
        # reconhecimento levanta quando não acha tabuleiro nenhum, e a página 0 de quase todo livro
        # é rosto ou sumário: um auto-teste que saísse com 1 ali mandaria a pessoa procurar um
        # defeito que não existe -- e é por isso que o README ensinava a passar `--page 80`.
        # O que se afirma neste ponto é o caminho, e ele rodou inteiro para poder dizer "nenhum".
        itens = []
        logger.info("Auto-teste: nenhum diagrama na página %d (o caminho rodou inteiro).", page_index)
    except Exception:
        logger.exception("Auto-teste falhou ao reconhecer a página.")
        return 1

    for indice, item in enumerate(itens, start=1):
        logger.info(
            "  diagrama %d: %s | conf min %.3f | %s",
            indice,
            item.placement,
            item.min_confidence,
            "legal" if item.is_legal else "ilegal",
        )
    logger.info("Auto-teste concluído: %d diagrama(s) reconhecido(s).", len(itens))

    # O bundle da S-55 promete leitor **e** treinador, e ler não prova treinar: o caminho de treino
    # usa `torchvision.transforms.v2`, que nada importa estaticamente e que um bundle incompleto
    # derruba só quando a pessoa clica "Treinar modelo" -- depois de ter corrigido dezenas de
    # diagramas. Montar a pipeline de aumento custa milissegundos e responde a pergunta agora.
    try:
        from chess_diagram_ocr.training import build_train_transform, train_model  # noqa: F401

        build_train_transform()
    except Exception:
        logger.exception("Auto-teste: a leitura funciona, mas o caminho de TREINO não montou.")
        return 4
    logger.info("Auto-teste: o caminho de treino também montou (leitor + treinador).")

    # **O segundo modelo torch do programa não entra no bundle**, e ausente não é falha: a decisão
    # e o porquê estão em `packaging/cvoff.spec`. O auto-teste diz em qual dos dois estados a
    # instalação está, sem mexer no código de saída (S-182).
    from chess_diagram_ocr.settings import Settings

    logger.info(
        "Auto-teste: classificador de caracteres -- %s",
        Settings().ocr.glyph_disabled_reason() or f"presente em {PROJECT_ROOT / 'models'}.",
    )

    # **"As três peles abrem" volta a ser afirmação verificada** (S-234). Ela é medida lá em cima,
    # com a janela ainda viva, e cobrada aqui: montar o cromo é o único passo que passa pela tabela
    # de comandos inteira, e é onde uma pele nova quebra sem que nenhum teste de painel note.
    if peles_quebradas:
        logger.error("Auto-teste: cromo de pele que não montou -- %s", "; ".join(peles_quebradas))
        return 5
    logger.info("Auto-teste: as %d peles registradas montam o cromo.", len(pele.PELES))

    # Zero diagrama não é falha: há páginas de prosa. O que se afirma aqui é que o caminho inteiro
    # -- Qt, janela, render, torch, decodificação, treino e cromo -- rodou sem estourar.
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
            # O livro da sessão anterior, e só na falta dele o primeiro da pasta (S-25).
            janela.abrir_livro_da_sessao()
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
