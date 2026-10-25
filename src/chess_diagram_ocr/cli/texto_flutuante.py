"""`cvoff-texto-flutuante` -- o portão da S-624: o texto ao lado do diagrama não estraga o editor?

    cvoff-texto-flutuante --pdf-dir PDF --folha "Kemeri.pdf:53" ... --json docs/metrics/texto_flutuante.json

**A pergunta não é se fica bonito, e sim se o editor continua dizendo a verdade.** A figura que
flutua muda o leiaute do `QTextDocument`, e o editor da aba Texto vive de traduzir posição do Qt
em deslocamento do documento (`_Mapa`) e de ler a tela de volta (a guarda S-603). Uma figura que
pusesse um caractere a mais no texto cru, ou um bloco que o desenho não conhece, faria a digitação
ao lado dela cair no lugar errado -- e é exatamente onde a pessoa vai digitar, porque é onde a
legenda e o primeiro lance estão.

## O que cada folha passa

Cada folha é lida pelo motor, aberta no painel com a folha rasterizada (sem ela não há miniatura),
com os diagramas à esquerda e o texto ao lado, e conferida em cinco coisas:

1. **flutua** -- a primeira linha depois de cada figura começa à direita dela: o texto contorna;
2. **paridade** -- a guarda S-603 inteira (`tests/paridade_do_texto.divergencias`) vazia;
3. **mapa** -- de cada deslocamento do documento à posição do Qt e de volta, o mesmo deslocamento;
4. **seleção** -- uma seleção que atravessa a figura volta como o mesmo trecho do documento;
5. **digitação** -- uma letra digitada no começo da linha ao lado da figura entra no documento
   onde o cursor estava, a guarda continua vazia, e `Ctrl+Z` devolve a folha de antes.

**A mesma folha também é conferida com o desenho de hoje** (a figura numa linha só para ela). É o
controle: lá o item 1 tem de reprovar -- senão a conta de "flutua" não mede nada -- e os outros
quatro têm de passar, senão o defeito é de antes e não da figura que flutua.

**A guarda é a da suíte, e não uma cópia.** Ela mora em `tests/`, e este comando a importa de lá:
uma segunda guarda escrita para a medição seria uma segunda opinião sobre o que é "a tela concorda".
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from ..config import DEFAULT_PDF_DIR
from ..logging_setup import configure_logging
from . import add_verbose, cli_errors

logger = logging.getLogger(__name__)

DPI = 150
"""A resolução da leitura e da folha rasterizada. A da aba (`PainelDeTexto(dpi=...)`) é a da janela,
e aqui só precisa ligar o `bbox` aos pixels -- 150 basta para a miniatura e lê depressa."""

FOLGA_DO_CONTORNO = 0.8
"""Quanto da largura da figura a linha seguinte tem de pular para contar como "ao lado". Menos que 1
porque o Qt mede a linha da margem do quadro, e a figura tem a margem dela."""


@dataclass
class Conferencia:
    """O que uma folha deu, numa das duas vistas."""

    figuras: int = 0
    flutuam: int = 0
    divergencias: list[str] = field(default_factory=list)
    mapa: list[str] = field(default_factory=list)
    selecao: list[str] = field(default_factory=list)
    digitacao: list[str] = field(default_factory=list)

    @property
    def editor_certo(self) -> bool:
        return not (self.divergencias or self.mapa or self.selecao or self.digitacao)

    def como_dado(self) -> dict[str, Any]:
        return {
            "figuras": self.figuras,
            "flutuam": self.flutuam,
            "editor_certo": self.editor_certo,
            "divergencias": self.divergencias[:5],
            "mapa": self.mapa[:5],
            "selecao": self.selecao[:5],
            "digitacao": self.digitacao[:5],
        }


def folha_do_argumento(texto: str) -> tuple[str, int]:
    """`"Livro.pdf:53"` -> `("Livro.pdf", 52)`: a folha é contada de 1, como a pessoa a vê. Pura."""
    nome, _, numero = texto.rpartition(":")
    if not nome or not numero.isdigit() or int(numero) < 1:
        raise ValueError(f"folha {texto!r}: o formato é Livro.pdf:N, com N a partir de 1")
    return nome, int(numero) - 1


def _guarda():  # noqa: ANN202 - a função da suíte, importada de tests/
    raiz = Path(__file__).resolve().parents[3] / "tests"
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))
    from paridade_do_texto import divergencias  # type: ignore[import-not-found]

    return divergencias


def _figuras(painel: Any) -> list[int]:
    """Os números de bloco do Qt que trazem uma miniatura."""
    from ..qt.painel_de_texto import OBJETO

    documento = painel.editor.document()
    achados = []
    bloco = documento.begin()
    while bloco.isValid():
        if OBJETO in bloco.text():
            achados.append(bloco.blockNumber())
        bloco = bloco.next()
    return achados


def conferir(painel: Any) -> Conferencia:
    """As cinco conferências na folha que está no painel, na vista que ele tem agora."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    divergencias = _guarda()
    QApplication.processEvents()
    saida = Conferencia(divergencias=list(divergencias(painel)))
    documento = painel.editor.document()
    texto = painel.documento.para_texto()

    for k in range(len(texto) + 1):
        if painel._mapa.deslocamento(painel._mapa.posicao(k)) != k:
            saida.mapa.append(f"deslocamento {k} volta como {painel._mapa.deslocamento(painel._mapa.posicao(k))}")

    for numero in _figuras(painel):
        saida.figuras += 1
        figura = documento.findBlockByNumber(numero)
        seguinte = figura.next()
        if not seguinte.isValid():
            continue
        largura = max(
            (f.charFormat().toImageFormat().width() for f in _fragmentos(figura) if f.charFormat().isImageFormat()),
            default=0.0,
        )
        layout = seguinte.layout()
        if layout is not None and layout.lineCount() and largura:
            recuo = layout.position().x() + layout.lineAt(0).x() - (figura.layout().position().x() if figura.layout() else 0.0)
            if recuo >= FOLGA_DO_CONTORNO * largura:
                saida.flutuam += 1

        # A seleção que atravessa a figura: de três letras antes dela a três depois.
        marca = painel._mapa.deslocamento(seguinte.position())
        inicio, fim = max(0, marca - 3), min(len(texto), marca + 3)
        cursor = QTextCursor(documento)
        cursor.setPosition(painel._mapa.posicao(inicio))
        cursor.setPosition(painel._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        painel.editor.setTextCursor(cursor)
        if painel._selecao_atual() != (inicio, fim):
            saida.selecao.append(f"figura do bloco {numero}: ({inicio}, {fim}) voltou {painel._selecao_atual()}")

        # A letra digitada ao lado da figura, no começo da linha da marca.
        antes = painel.documento.para_texto()
        cursor = QTextCursor(documento)
        cursor.setPosition(seguinte.position())
        painel.editor.setTextCursor(cursor)
        painel.editor.setFocus()
        onde = painel._mapa.deslocamento(seguinte.position())
        QTest.keyClick(painel.editor, Qt.Key.Key_X)  # type: ignore[call-overload]  # o stub declara keyClick com `self`
        QApplication.processEvents()
        depois = painel.documento.para_texto()
        if depois != antes[:onde] + "x" + antes[onde:]:
            saida.digitacao.append(f"figura do bloco {numero}: a letra não entrou no deslocamento {onde}")
        saida.digitacao.extend(f"depois de digitar: {erro}" for erro in divergencias(painel)[:3])
        painel.desfazer()
        QApplication.processEvents()
        if painel.documento.para_texto() != antes:
            saida.digitacao.append(f"figura do bloco {numero}: desfazer não devolveu a folha")
        documento = painel.editor.document()  # o desfazer redesenha num documento novo
    return saida


def _fragmentos(bloco: Any) -> list[Any]:
    achados = []
    iterador = bloco.begin()
    while not iterador.atEnd():
        achados.append(iterador.fragment())
        iterador += 1
    return achados


def medir(pdf_dir: Path, folhas: list[tuple[str, int]], *, motor: str) -> list[dict[str, Any]]:
    """Lê cada folha e a confere com o texto ao lado e com o desenho de hoje."""
    from ..pdf_io import render_pdf_page
    from ..qt import tema
    from ..qt.painel_de_texto import PainelDeTexto
    from ..text.leitor import ler_pagina
    from ..ui.texto_declarado import DIAGRAMAS_A_ESQUERDA

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # a medição não abre janela na mesa de ninguém
    from PyQt6.QtWidgets import QApplication

    existente = QApplication.instance()
    app = existente if isinstance(existente, QApplication) else QApplication(sys.argv[:1])
    tema.aplicar_tema(app)
    rascunhos = Path(tempfile.mkdtemp(prefix="cvoff-flutuante-"))  # a digitação de teste não vai a data/rascunhos
    resultados = []
    for nome, folha in folhas:
        pdf = pdf_dir / nome
        pagina = ler_pagina(pdf, folha, dpi=DPI, motor=motor)  # type: ignore[arg-type]
        rgb = render_pdf_page(pdf, folha, dpi=DPI)
        painel = PainelDeTexto(dpi=DPI, pasta_de_rascunhos=rascunhos)
        painel.resize(900, 1100)
        painel.show()
        painel.definir_diagramas(DIAGRAMAS_A_ESQUERDA)
        painel.mostrar_pagina(pagina, folha_rgb=rgb, dpi=DPI)
        painel.definir_texto_ao_lado(False)
        controle = conferir(painel)
        painel.definir_texto_ao_lado(True)
        ao_lado = conferir(painel)
        painel.close()
        painel.deleteLater()
        app.processEvents()
        resultados.append(
            {
                "livro": nome,
                "folha": folha + 1,
                "diagramas_lidos": len(pagina.diagramas),
                "ao_lado": ao_lado.como_dado(),
                "controle": controle.como_dado(),
            }
        )
        logger.info("%s folha %d: ao lado %s, controle %s", nome, folha + 1, ao_lado.como_dado(), controle.como_dado())
    return resultados


def veredito(resultados: list[dict[str, Any]]) -> dict[str, Any]:
    """Passa quando, em toda folha, o editor está certo nas duas vistas, toda figura flutua com o texto
    ao lado e nenhuma flutua no controle. Pura."""
    figuras = sum(r["ao_lado"]["figuras"] for r in resultados)
    reprovadas = [
        f"{r['livro']}:{r['folha']}"
        for r in resultados
        if not (r["ao_lado"]["editor_certo"] and r["controle"]["editor_certo"])
        or r["ao_lado"]["flutuam"] != r["ao_lado"]["figuras"]
        or r["controle"]["flutuam"]
    ]
    return {
        "folhas": len(resultados),
        "figuras": figuras,
        "flutuam": sum(r["ao_lado"]["flutuam"] for r in resultados),
        "flutuam_no_controle": sum(r["controle"]["flutuam"] for r in resultados),
        "folhas_reprovadas": reprovadas,
        "passa": bool(resultados) and figuras > 0 and not reprovadas,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Pasta dos livros (padrao: PDF/).")
    parser.add_argument("--folha", action="append", default=[], help="Livro.pdf:N (a folha contada de 1). Repita.")
    parser.add_argument("--motor", default="auto", help="O motor de leitura (padrao: auto).")
    parser.add_argument("--json", type=Path, help="Grava o relatorio neste caminho.")
    add_verbose(parser)
    return parser


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)
    from ..checkpoint import git_commit, git_worktree_dirty

    folhas = [folha_do_argumento(texto) for texto in args.folha]
    if not folhas:
        print("Nenhuma folha: passe --folha Livro.pdf:N, uma por folha.")
        return 0
    resultados = medir(Path(args.pdf_dir), folhas, motor=args.motor)
    final = veredito(resultados)
    relatorio = {
        "item": "S-624 · o portão do diagrama à esquerda com o texto ao lado",
        "medido_em": date.today().isoformat(),
        "codigo": {"commit": git_commit(), "arvore_suja": git_worktree_dirty()},
        "protocolo": "cada folha lida, aberta no painel com a folha rasterizada e os diagramas à esquerda, e conferida com o texto ao lado e com o desenho de hoje (o controle)",
        "motor": args.motor,
        "dpi": DPI,
        "veredito": final,
        "folhas": resultados,
    }
    print(f"{final['folhas']} folha(s), {final['figuras']} figura(s): {final['flutuam']} flutuam ao lado, "
          f"{final['flutuam_no_controle']} no controle.")
    for nome in final["folhas_reprovadas"]:
        print(f"  reprovada: {nome}")
    print("PASSA" if final["passa"] else "NAO PASSA")
    if args.json:
        atomic_write_text(args.json, json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
        print(f"Relatorio em {args.json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
