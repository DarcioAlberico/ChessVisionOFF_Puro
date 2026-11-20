"""Quantos erros repetidos somem depois da primeira correção (S-766), num livro do dev. Sem rodar motor: refaz a fusão pelo que `coletar.py` gravou.

    repetidos.py <pasta dos jsonl> <arquivo.jsonl>... [--saida relatorio.json]

**O dono é simulado, e a simulação é generosa só no que ele faria:** as folhas passam em ordem; a primeira vez que um par `lido -> certo` aparece, ele corrige, e o que ele
escreveu vai ao léxico do livro se o léxico não o conhece. Dois caminhos, medidos à parte:

- **a troca em todas as folhas**: a ocorrência seguinte do mesmo `lido` some, se a referência diz que era erro; se era certa, é a **colateral**, que a prévia mostra e o dono desmarca;
- **o léxico do livro nos árbitros**: a fusão refeita nas folhas seguintes com as palavras ensinadas até ali, contra a mesma fusão sem elas. Fora do `ler_pagina`, e por isso sem a montagem: o que
  se compara é uma fusão com a outra, na mesma ordem de linhas.

O texto de livro não sai daqui: o relatório só tem contagens.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rotular  # noqa: E402

from chess_diagram_ocr.text import arbitro, correcao_no_livro, fusao  # noqa: E402
from chess_diagram_ocr.text import regua_prosa as regua


def _norm(token: str, lingua: str) -> str:
    return regua.normalizar(token, regua.TIP, lingua).strip()


def pares_de_erro(ref: str, linhas: list[str], lingua: str) -> list[tuple[str, str]]:
    """Os pares `(lido, certo)` de troca um a um em que `lido` é prosa. É o que uma correção de palavra faz."""
    tokens_ref = ref.split()
    tokens_hip = [t for ln in linhas for t in ln.split()]
    a = [_norm(t, lingua) for t in tokens_ref]
    b = [_norm(t, lingua) for t in tokens_hip]
    saida = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "replace" and i2 - i1 == j2 - j1:
            saida.extend(
                (tokens_hip[j1 + k], tokens_ref[i1 + k]) for k in range(i2 - i1) if regua.classe_do_token(tokens_hip[j1 + k], lingua) == regua.PROSA
            )
    return saida


def fusao_refeita(r: dict[str, Any], palavras: frozenset[str]) -> list[str]:
    existe = fusao.existe_do_livro(r["lingua"], palavras)
    linhas = []
    for e in r["entrada"]:
        if e["t"] is None:
            linhas.append([fusao.Token(t, "glifo", t, c) for t, c in zip(e["g"].split(), e["c_g"], strict=True)])
        else:
            linhas.append(fusao.fundir(e["g"], e["t"], existe=existe, confiancas_do_leitor=e["c_t"], confiancas_do_glifo=e["c_g"], regra=r["regra"] or fusao.V5, guarda_prosa_sem_par=True))
    linhas = arbitro.arbitrar(linhas, existe=existe, posicoes=(), lingua=r["lingua"])
    return [fusao.texto_fundido(ln) for ln in linhas]


def erradas(ref: str, linhas: list[str], lingua: str) -> int:
    rotulo = rotular.rotular_linhas(ref, linhas, lingua)
    return sum(sum(x) for x in rotulo["errada"])


def livro(registros: list[dict[str, Any]]) -> dict[str, Any]:
    registros = sorted((r for r in registros if r["tokens"]), key=lambda r: r["folha"])
    lingua = registros[0]["lingua"]
    existe = fusao.existe_do_livro(lingua)
    primeira_de: dict[str, str] = {}
    ensinadas: set[str] = set()
    conta: Counter[str] = Counter()
    pares_vistos: Counter[tuple[str, str]] = Counter()
    sem_arbitro = com_arbitro = folhas_que_mudam = 0
    for r in registros:
        finais = [ln["texto"] for ln in r["linhas"]]
        erros = pares_de_erro(r["ref"], finais, lingua)
        conta["erradas"] += erradas(r["ref"], finais, lingua)
        base = fusao_refeita(r, frozenset())
        ouvindo = fusao_refeita(r, frozenset(ensinadas))
        sem_arbitro += erradas(r["ref"], base, lingua)
        com_arbitro += erradas(r["ref"], ouvindo, lingua)
        folhas_que_mudam += base != ouvindo
        de_erro = Counter(lido for lido, _ in erros)
        for lido, certo in erros:
            conta["pares"] += 1
            pares_vistos[(lido, certo)] += 1
            if primeira_de.get(lido) == certo:
                conta["repetidos_que_a_troca_tira"] += 1
            elif lido in primeira_de:
                conta["mesmo_lido_outro_certo"] += 1
            else:
                primeira_de[lido] = certo
                conta["primeiras_correcoes"] += 1
                nova = correcao_no_livro.palavra_do_livro(certo)
                if nova and not existe(nova):
                    ensinadas.add(nova)
        for token in (t for ln in finais for t in ln.split()):
            if token in primeira_de and de_erro[token] <= 0:
                conta["colaterais_que_a_previa_mostra"] += 1
            elif token in primeira_de:
                de_erro[token] -= 1
    repetidos = sorted(pares_vistos.values(), reverse=True)
    return {
        "folhas": len(registros), "lingua": lingua,
        "palavras_erradas": conta["erradas"], "pares_de_troca_um_a_um": conta["pares"], "primeiras_correcoes": conta["primeiras_correcoes"],
        "repetidos_que_a_troca_tira": conta["repetidos_que_a_troca_tira"], "mesmo_lido_outro_certo": conta["mesmo_lido_outro_certo"],
        "colaterais_que_a_previa_mostra": conta["colaterais_que_a_previa_mostra"],
        "maiores_repeticoes": repetidos[:5],
        "palavras_ensinadas": len(ensinadas),
        "erradas_na_fusao_refeita_sem_as_palavras": sem_arbitro, "erradas_na_fusao_refeita_com_as_palavras": com_arbitro, "folhas_em_que_o_lexico_do_livro_muda_o_texto": folhas_que_mudam,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("arquivos", nargs="+")
    ap.add_argument("--saida", default="")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    relatorio = {}
    for nome in args.arquivos:
        registros = rotular.ler(Path(args.pasta) / f"{nome}.jsonl")
        por_livro: dict[str, list[dict[str, Any]]] = {}
        for r in registros:
            por_livro.setdefault(r["identidade"], []).append(r)
        for identidade, dele in por_livro.items():
            relatorio[f"{nome}:{identidade}"] = livro(dele)
    texto = json.dumps(relatorio, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.saida:
        Path(args.saida).write_bytes(texto.encode("utf-8"))
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
