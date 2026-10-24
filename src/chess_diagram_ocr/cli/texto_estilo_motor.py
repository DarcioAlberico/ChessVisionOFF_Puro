"""`cvoff-texto-estilo-motor` -- quanto do negrito e do itálico da camada chega ao documento, por motor (S-660).

    cvoff-texto-estilo-motor --pdf-dir PDF --folhas 4 --json docs/metrics/texto_estilo_por_motor.json

**A pergunta que este comando responde vem antes de qualquer modelo.** O dono do projeto pediu
"o reconhecimento de textos em negrito, itálico e normal", e o código diz que parte disso já
existe: o negrito da camada do PDF vale nos dois motores ("o peso não tem segunda fonte",
`text/leitor.py`), e o itálico por caractere só no motor `camada`, porque no glifo quem responde é
o pendor da imagem (S-211/S-429). Não havia **número** de quanto disso a pessoa vê -- e se, nos
livros que declaram peso, a resposta já for "chega", treinar um classificador seria resolver o
problema errado.

## A referência é o motor `camada`, e é por isso que a medida é honesta

Para cada folha, a camada lida pelo motor `camada` é a referência: é o estilo que o PDF **declara**,
descido ao caractere pela S-429 (e a fidelidade dela ao PDF é a medição daquele item,
`docs/metrics/texto_estilo_fino.json`). Os outros motores leem a mesma folha, cada um com o seu
texto -- o glifo erra letra --, então os dois textos são **casados** por `difflib` e só os
caracteres casados entram na conta. Para cada um se pergunta: o estilo que a referência tem chegou?
e o estilo que a referência não tem apareceu?

"Negrito na tela" é o que o desenho pinta: o atributo `negrito` **ou** o estilo de título, que
`qt/texto_formato.formato_de` desenha em negrito. É a mesma regra dos dois lados.

## O que ele não mede

O desenho: que o documento e a tela concordam é a guarda S-603, e ela roda na suíte. E as folhas
sem camada: lá não há referência, e é exatamente a população da Fase 96, que este relatório decide
se abre.
"""

from __future__ import annotations

import argparse
import difflib
import json
import logging
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from ..config import DEFAULT_PDF_DIR
from ..logging_setup import configure_logging
from ..text import rico
from . import add_dpi_argument, add_verbose, cli_errors

logger = logging.getLogger(__name__)

REFERENCIA = "camada"
"""O motor cuja leitura é a verdade do estilo. Ver o cabeçalho."""

MOTORES_MEDIDOS: tuple[str, ...] = ("auto", "glifo")

LIMIAR_DE_PERDA = 0.01
"""A partir de quanto o relatório **nomeia** o livro: mais de 1% do estilo declarado não chegou.

Abaixo disso a diferença é ruído de casamento -- um caractere do glifo casado com o vizinho errado
do lado da referência --, e listar o livro mandaria procurar defeito onde não há."""


def estilo_por_caractere(doc: rico.DocumentoRico) -> tuple[list[bool], list[bool]]:
    """`(negrito, itálico)` de cada caractere de `doc.para_texto()`, como a tela os pinta. Puro."""
    negrito: list[bool] = []
    italico: list[bool] = []
    for corrida in doc.corridas:
        atributos = corrida.atributos
        pesado = atributos.negrito or atributos.estilo == rico.ESTILO_TITULO
        negrito.extend([pesado] * len(corrida.texto))
        italico.extend([atributos.italico] * len(corrida.texto))
    return negrito, italico


def casados(referencia: str, outro: str) -> list[tuple[int, int]]:
    """Os pares `(i, j)` de caracteres iguais que `difflib` casa entre os dois textos. Puro.

    `autojunk=False`: numa página o espaço é o caractere mais comum, e a heurística de lixo do
    `difflib` o jogaria fora -- e com ele o casamento de linha inteira de notação.
    """
    pares: list[tuple[int, int]] = []
    for bloco in difflib.SequenceMatcher(None, referencia, outro, autojunk=False).get_matching_blocks():
        pares.extend((bloco.a + k, bloco.b + k) for k in range(bloco.size) if not referencia[bloco.a + k].isspace())
    return pares


def comparar(referencia: rico.DocumentoRico, outro: rico.DocumentoRico) -> dict[str, int]:
    """A contagem de uma folha: quanto estilo a referência tem, quanto chegou, quanto sobrou. Puro."""
    ref_negrito, ref_italico = estilo_por_caractere(referencia)
    out_negrito, out_italico = estilo_por_caractere(outro)
    contas = dict.fromkeys(
        (
            "casados",
            "negrito_declarado",
            "negrito_chegou",
            "negrito_a_mais",
            "italico_declarado",
            "italico_chegou",
            "italico_a_mais",
        ),
        0,
    )
    for i, j in casados(referencia.para_texto(), outro.para_texto()):
        contas["casados"] += 1
        for nome, ref, out in (("negrito", ref_negrito, out_negrito), ("italico", ref_italico, out_italico)):
            if ref[i]:
                contas[f"{nome}_declarado"] += 1
                contas[f"{nome}_chegou"] += int(out[j])
            elif out[j]:
                contas[f"{nome}_a_mais"] += 1
    return contas


def somar(partes: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Soma as contagens, e só elas: a linha de um livro traz também `perda`, que é derivada. Puro."""
    total: dict[str, int] = {}
    for parte in partes:
        for chave, valor in parte.items():
            if isinstance(valor, int) and not isinstance(valor, bool):
                total[chave] = total.get(chave, 0) + valor
    return total


def total_por_motor(por_livro: dict[str, Any], motores: Sequence[str]) -> dict[str, Any]:
    """As contagens do acervo inteiro por motor, com a perda de cada estilo. Puro."""
    totais = {motor: somar(dados[motor] for dados in por_livro.values()) for motor in motores}
    return {motor: {**totais[motor], "perda": perdas(totais[motor])} for motor in motores}


def perdas(contas: dict[str, int]) -> dict[str, float | None]:
    """A fração do estilo declarado que **não** chegou. `None` quando o livro não declara aquele estilo."""
    saida: dict[str, float | None] = {}
    for nome in ("negrito", "italico"):
        declarado = contas.get(f"{nome}_declarado", 0)
        saida[nome] = None if not declarado else round(1 - contas.get(f"{nome}_chegou", 0) / declarado, 4)
    return saida


def folhas_de(total: int, quantas: int) -> list[int]:
    """`quantas` folhas espaçadas pelo livro, longe da capa e do fim -- o protocolo da S-429. Puro."""
    if total <= 0:
        return []
    return sorted({min(total - 1, round(total * k / (quantas + 1))) for k in range(1, quantas + 1)})


def _ler(pdf: Path, folha: int, motor: str, dpi: int) -> rico.DocumentoRico:
    from ..text.leitor import ler_pagina

    return rico.de_pagina(ler_pagina(pdf, folha, dpi=dpi, motor=motor))  # type: ignore[arg-type]


def medir(pdfs: Sequence[Path], *, folhas: int, dpi: int, motores: Sequence[str]) -> dict[str, Any]:
    """Lê cada folha do protocolo com a referência e com cada motor, e conta. Livro sem estilo declarado sai."""
    from ..pdf_io import opened

    por_livro: dict[str, Any] = {}
    for pdf in pdfs:
        try:
            with opened(pdf) as documento:
                total = documento.page_count
        except Exception as erro:  # noqa: BLE001 - um PDF ilegível não derruba a medição do acervo
            logger.warning("Nao abriu %s: %s", pdf.name, erro)
            continue
        contas: dict[str, list[dict[str, int]]] = {motor: [] for motor in motores}
        for folha in folhas_de(total, folhas):
            referencia = _ler(pdf, folha, REFERENCIA, dpi)
            negrito, italico = estilo_por_caractere(referencia)
            if not any(negrito) and not any(italico):
                continue
            for motor in motores:
                contas[motor].append(comparar(referencia, _ler(pdf, folha, motor, dpi)))
        if not any(contas[motor] for motor in motores):
            continue
        por_livro[pdf.name] = {
            motor: {**somar(contas[motor]), "folhas": len(contas[motor]), "perda": perdas(somar(contas[motor]))}
            for motor in motores
        }
        logger.info("%s: %s", pdf.name, {m: por_livro[pdf.name][m]["perda"] for m in motores})
    return por_livro


def livros_com_perda(por_livro: dict[str, Any], limiar: float = LIMIAR_DE_PERDA) -> list[dict[str, Any]]:
    """Os livros em que algum motor perde mais que `limiar` de algum estilo declarado. Puro."""
    achados = []
    for livro, motores in sorted(por_livro.items()):
        for motor, dados in motores.items():
            for estilo, perda in dados["perda"].items():
                if perda is not None and perda > limiar:
                    achados.append({"livro": livro, "motor": motor, "estilo": estilo, "perda": perda})
    return achados


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Pasta dos livros (padrao: PDF/).")
    parser.add_argument("--folhas", type=int, default=4, help="Folhas por livro, espacadas (padrao: 4).")
    parser.add_argument("--livros", type=int, default=0, help="Limita a quantos livros (0: todos).")
    add_dpi_argument(parser)
    parser.add_argument("--json", type=Path, help="Grava o relatorio neste caminho.")
    add_verbose(parser)
    return parser


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)
    from ..checkpoint import git_commit, git_worktree_dirty
    from ..text.leitor import _ha_classificador

    pdfs = sorted(Path(args.pdf_dir).glob("*.pdf"))
    if args.livros:
        pdfs = pdfs[: args.livros]
    if not pdfs:
        print(f"Nenhum PDF em {args.pdf_dir}.")
        return 0
    if not _ha_classificador():
        print("Sem o classificador de glifo (models/char_classifier.pt): o glifo e o auto leriam pela camada, e a medida nao diria nada.")
        return 0

    por_livro = medir(pdfs, folhas=args.folhas, dpi=args.dpi, motores=MOTORES_MEDIDOS)
    relatorio = {
        "item": "S-660 · o estilo da camada chega ao documento em cada motor?",
        "medido_em": date.today().isoformat(),
        "codigo": {"commit": git_commit(), "arvore_suja": git_worktree_dirty()},
        "protocolo": f"{args.folhas} folhas espacadas de cada um dos {len(pdfs)} PDFs; livros sem estilo declarado nas folhas lidas ficam fora",
        "referencia": REFERENCIA,
        "livros_medidos": len(por_livro),
        "total": total_por_motor(por_livro, MOTORES_MEDIDOS),
        "livros_com_perda": livros_com_perda(por_livro),
        "por_livro": por_livro,
    }
    print(f"{len(por_livro)} livro(s) com estilo declarado nas folhas lidas.")
    for motor in MOTORES_MEDIDOS:
        print(f"  {motor}: perda {relatorio['total'][motor]['perda']}")
    for achado in relatorio["livros_com_perda"]:
        print(f"  {achado['livro']} [{achado['motor']}] {achado['estilo']}: {achado['perda']:.1%} nao chegou")
    if args.json:
        atomic_write_text(args.json, json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
        print(f"Relatorio em {args.json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
