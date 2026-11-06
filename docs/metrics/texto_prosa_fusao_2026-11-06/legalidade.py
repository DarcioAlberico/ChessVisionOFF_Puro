"""G1(c) e o alcance da legalidade (S-729): quantas sequências fecham legais a partir da FEN do diagrama, e quantos lances isso alcança.

    legalidade.py <ouro|prata> <fens.jsonl> <saida.json>

A FEN é a do classificador de peças de produção, gravada por `fens.py`. **Esta conta não usa a jogada do árbitro:** usa
`notacao.fatiar` e `notacao.validar`, para o juiz não ser o mesmo que o julgado. Uma sequência é a primeira fatia de lances em ordem de
leitura depois do diagrama; ela fecha se todos os lances dela forem legais, com o lado lido no diagrama ou com o outro.

Roda com `PYTHONPATH=<worktree>/src`, `CVOFF_RAIZ` no checkout com os PDF. O texto de livro não sai daqui: só contagens.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import chess

from chess_diagram_ocr.cli.texto_prosa import _achar_livros, _pastas_padrao, folhas_do_conjunto
from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text import arbitro, leitor, notacao
from chess_diagram_ocr.text.leitor import ler_pagina
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama
from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

LETRAS = {
    "eng": {},
    "por": dict(zip("RDTC", "KQRN", strict=True)),
    "spa": dict(zip("RDTAC", "KQRBN", strict=True)),
    "deu": dict(zip("DTLS", "QRBN", strict=True)),
    "fra": dict(zip("RDTFC", "KQRBN", strict=True)),
    "nld": dict(zip("DTLP", "QRBN", strict=True)),
}


def em_ingles(token: str, lingua: str) -> str:
    m = re.match(r"^([(\[]?(?:\d{1,3}(?:\.{1,3}|\))\s*)?)(.*)$", token)
    prefixo, resto = m.group(1), m.group(2)
    if resto[:1] in LETRAS.get(lingua, {}):
        resto = LETRAS[lingua][resto[0]] + resto[1:]
    return prefixo + resto


def juntar_figurina(tokens: list[str]) -> list[str]:
    """`♘ f6+` é um lance: o glifo põe espaço depois da figurina no *Minhas 60*."""
    saida: list[str] = []
    for t in tokens:
        if saida and re.fullmatch(r"(?:\d{1,3}\.{1,3})?[♔-♟]", saida[-1]):
            saida[-1] += t
        else:
            saida.append(t)
    return saida


def medir(pagina, posicoes: list[chess.Board | None], lingua: str) -> dict[str, int]:
    """Por diagrama da folha, em ordem de leitura, a primeira fatia de lances depois dele."""
    c = {"diagramas_com_fen": 0, "sequencias": 0, "fecham": 0, "lances_na_sequencia": 0, "lances_jogados": 0, "lances_na_folha": 0}
    tokens: list[str] = []
    marcos: list[tuple[int, int]] = []
    for elemento in pagina.blocos:
        if isinstance(elemento, BlocoDeDiagrama):
            marcos.append((len(tokens), elemento.indice))
        else:
            for linha in getattr(elemento, "linhas", ()):
                tokens.extend(juntar_figurina(linha.texto.split()))
    fatias = notacao.fatiar(tokens, minimo=1)
    c["lances_na_folha"] = sum(1 for f in fatias if f.e_lance for t in tokens[f.inicio : f.fim] if not notacao.e_numero_de_lance(t))
    for onde, indice in marcos:
        tabuleiro = posicoes[indice] if indice < len(posicoes) else None
        if tabuleiro is None:
            continue
        c["diagramas_com_fen"] += 1
        fatia = next((f for f in fatias if f.inicio >= onde and f.e_lance), None)
        if fatia is None:
            continue
        lances = [em_ingles(t, lingua) for t in tokens[fatia.inicio : fatia.fim]]
        total = sum(1 for t in lances if not notacao.e_numero_de_lance(t))
        melhor = None
        for vez in (tabuleiro.turn, not tabuleiro.turn):
            t = tabuleiro.copy(stack=False)
            t.turn = vez
            if not t.is_valid():
                continue
            # O número impresso não é conferido aqui: a FEN do diagrama não sabe em que lance está.
            t.fullmove_number = 1
            sem_numero = [re.sub(r"^[(\[]?\d{1,3}(?:\.{1,3}|\))", "", x) for x in lances if not notacao.e_numero_de_lance(x)]
            r = notacao.validar([x for x in sem_numero if x], t)
            if melhor is None or len(r.lances) > len(melhor.lances):
                melhor = r
        c["sequencias"] += 1
        c["lances_na_sequencia"] += total
        if melhor is not None:
            c["lances_jogados"] += len(melhor.lances)
            c["fecham"] += int(melhor.fechou and len(melhor.lances) > 0)
    return c


def somar(a: dict[str, int], b: dict[str, int]) -> None:
    for k, v in b.items():
        a[k] = a.get(k, 0) + v


def main() -> int:
    conjunto, arq_fens, saida = sys.argv[1:4]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raiz = Path(sys.argv[4]) if len(sys.argv) > 4 else (Path(os.environ["CVOFF_RAIZ"]) if os.environ.get("CVOFF_RAIZ") else None)
    fens = {(r["identidade"], r["folha"]): r["diagramas"] for r in map(json.loads, open(arq_fens, encoding="utf-8"))}
    folhas = folhas_do_conjunto(conjunto, "dev" if conjunto == "ouro" else "")
    achados = _achar_livros(folhas, _pastas_padrao(str(raiz) if raiz else ""))
    rec = build_glyph_recognizer()
    variantes = {"glifo": {}, "fusao_sem_arbitro": {}, "fusao_gramatica": {}, "fusao_com_legalidade": {}}
    trocas = 0
    for f in folhas:
        pdf = str(achados[f.identidade])
        imagem = render_pdf_page(pdf, f.folha - 1, 220)
        diagramas = fens.get((f.identidade, f.folha), [])
        comum = {"reconhecedor": rec, "imagem_rgb": imagem, "dpi": 220, "lingua": f.lingua}
        # A ordem dos diagramas é a do detector nos dois caminhos: `recognize_page` e `ler_pagina` usam a mesma lista.
        tabuleiros: list[chess.Board | None] = []
        for d in diagramas:
            try:
                t = chess.Board(f"{d['placement']} {'w' if d['brancas'] else 'b'} - - 0 1")
                tabuleiros.append(t)
            except ValueError:
                tabuleiros.append(None)

        def posicao(n: int) -> chess.Board | None:
            return tabuleiros[n] if n < len(tabuleiros) else None

        for nome, motor, gramatica, com_fen in (
            ("glifo", "glifo", False, False),
            ("fusao_sem_arbitro", "fusao", False, False),
            ("fusao_gramatica", "fusao", True, False),
            ("fusao_com_legalidade", "fusao", True, True),
        ):
            arbitro.GRAMATICA = gramatica
            relato = arbitro.Relato()
            real = leitor._arbitro.arbitrar  # noqa: SLF001

            def com_relato(fund, relato_do_chamador=None, r=relato, **kw):
                kw.pop("relato", None)
                return real(fund, relato=r, **kw)

            leitor._arbitro.arbitrar = com_relato  # noqa: SLF001
            pagina = ler_pagina(pdf, f.folha - 1, motor=motor, posicao_do_diagrama=posicao if com_fen else None, **comum)
            leitor._arbitro.arbitrar = real  # noqa: SLF001
            c = medir(pagina, tabuleiros, f.lingua)
            c["trocas_pela_legalidade"] = relato.pela_legalidade
            c["lances_alcancados_pelo_arbitro"] = relato.lances_alcancados
            somar(variantes[nome], c)
        print(f.identidade[:8], f.folha, len(diagramas), flush=True)
    Path(saida).write_bytes((json.dumps({"conjunto": conjunto, "variantes": variantes}, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    for nome, c in variantes.items():
        print(nome, c)
    return trocas


if __name__ == "__main__":
    raise SystemExit(main())
