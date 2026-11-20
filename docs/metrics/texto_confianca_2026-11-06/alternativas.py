"""As alternativas do `lstm_choice_mode=2` pagam na confiança da S-760? O calibrador com e sem elas, cada livro medido por um calibrador que não o viu.

    alternativas.py <pasta dos jsonl> [--saida relatorio.json]

Três atributos a mais por palavra, do hOCR das mesmas linhas: a menor confiança da primeira escolha, a menor margem para a segunda, e "não achei a palavra no hOCR". O resto é `ajustar.py`, tal e qual.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ajustar  # noqa: E402
import rotular  # noqa: E402

from chess_diagram_ocr.text import confianca_palavra as cp  # noqa: E402
from chess_diagram_ocr.text import fusao


def amostras(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    saida = []
    for r in registros:
        if not r["tokens"]:
            continue
        existe = fusao.existe_do_livro(r["lingua"])
        linhas = ajustar._tokens(r["tokens"])  # noqa: SLF001
        alternativas = r.get("alternativas") or []
        mapa: dict[tuple[int, int], dict[str, Any]] = {}
        for n, linha in enumerate(r["tokens"]):
            dela = list(alternativas[n]) if n < len(alternativas) else []
            posicao = 0
            for k, token in enumerate(linha):
                if token["do_leitor"]:
                    for q in range(posicao, len(dela)):
                        if dela[q]["t"] == token["do_leitor"]:
                            mapa[(n, k)] = dela[q]
                            posicao = q + 1
                            break
        rotulados, _ = rotular.tokens_rotulados(r)
        x, y = [], []
        for _token, errada, _prosa, n, k in rotulados:
            a = mapa.get((n, k))
            extra = [0.0, 0.0, 1.0] if a is None else [a["topo"], a["margem"], 0.0]
            x.append([*cp.atributos(linhas[n][k], existe=existe), *extra])
            y.append(errada)
        o = r["placar"].get("tess_oraculo|tip") or r["placar"]["fusao|tip"]
        saida.append({
            "id": r["identidade"], "folha": r["folha"], "x": np.array(x, dtype=np.float64).reshape(-1, len(cp.NOMES) + 3), "y": np.array(y, dtype=bool),
            "perdidas": 0, "ref_ruim": o["erros"]["prosa"] / max(1, o["total"]["prosa"]) > ajustar.CORTE_DA_FOLHA_DE_REFERENCIA_RUIM,
        })
    return saida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("--saida", default="")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    n = len(cp.NOMES)
    relatorio = {}
    for dominio, nomes in ((cp.DIGITAL, ("reservado_ouro", "ouro_dev")), (cp.SCAN, ("reservado_prata", "prata"))):
        folhas = amostras([r for nome in nomes for r in rotular.ler(Path(args.pasta) / f"{nome}.jsonl")])
        if dominio == cp.SCAN:
            folhas = [f for f in folhas if not f["ref_ruim"]]
        bloco = {}
        for rotulo, colunas in (("sem_alternativas", list(range(n))), ("com_alternativas", list(range(n + 3)))):
            medida = ajustar.deixa_um_livro_de_fora(folhas, colunas=colunas)
            m = medida["marca"]
            bloco[rotulo] = {"captura": m["captura"], "captura_ic95": m["captura_ic95"], "fracao_marcada": m["fracao_marcada"], "ece": medida["ece"], "ece_por_faixa": medida["ece_por_faixa"]}
        relatorio[dominio] = bloco
    texto = json.dumps(relatorio, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.saida:
        Path(args.saida).write_bytes(texto.encode("utf-8"))
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
