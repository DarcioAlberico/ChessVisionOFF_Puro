"""Os sinais do monitor sem referência, contra o CER por folha, por domínio (S-763). Sem rodar motor: tudo sai dos JSONL de `coletar.py`.

    monitor.py <pasta dos jsonl> [--saida relatorio.json]

**A regra foi escrita antes de olhar o número.** Um sinal vira alarme se, no domínio: (1) a correlação de postos com o CER de prosa da saída, por
folha, for ≥ 0,5 em módulo e o limite do IC95 (livro, folha) não passar de 0,2; e (2) com o corte tirado do pedaço reservado, no máximo 1 em 3 alarmes for falso
nas folhas do manifesto. "Folha ruim" é CER de prosa ≥ 1% no digital e ≥ 5% no scan: acima do teto de M1 (0,60%) e de M3 (2,0%), onde a folha pede olho.

**Referência de terceiro no scan**: a prata só ordena, e é o que há até a S-703 ter verdade. A folha em que o próprio oráculo erra mais de 10% sai: lá o CER mede a referência.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ajustar  # noqa: E402
import rotular  # noqa: E402

from chess_diagram_ocr.text import confianca_palavra as cp  # noqa: E402
from chess_diagram_ocr.text import fusao, monitor_prosa

FOLHA_RUIM = {cp.DIGITAL: 0.01, cp.SCAN: 0.05}
MINIMO_DE_PROSA = 200
"""Folha com menos caracteres de prosa não tem CER que se compare: um erro só dá 0,5%."""
REAMOSTRAS = 2000
SEMENTE = 7


def linhas_de_tokens(r: dict[str, Any]) -> list[list[fusao.Token]]:
    return ajustar._tokens(r["tokens"])  # noqa: SLF001


def sinais_da_folha(r: dict[str, Any]) -> dict[str, float]:
    existe = fusao.existe_do_livro(r["lingua"])
    linhas = linhas_de_tokens(r)
    dominio = cp.dominio_da_regra(r["regra"])
    g = r["guarda"] or {}
    return {
        "discordancia": 1.0 - monitor_prosa.concordancia(linhas),
        "densidade": abs(1.0 - float(g.get("densidade", 1.0))),
        "erro_estimado": monitor_prosa.erro_estimado(linhas, existe=existe, dominio=dominio),
        "marcadas": monitor_prosa.fracao_acima_do_corte(linhas, existe=existe, dominio=dominio),
    }


def amostra(pasta: Path, *nomes: str) -> list[dict[str, Any]]:
    saida = []
    for nome in nomes:
        for r in rotular.ler(pasta / f"{nome}.jsonl"):
            if not r["tokens"]:
                continue
            p = r["placar"]["fusao|tip"]
            if p["total"]["prosa"] < MINIMO_DE_PROSA:
                continue
            o = r["placar"].get("tess_oraculo|tip")
            if o is not None and o["erros"]["prosa"] / max(1, o["total"]["prosa"]) > 0.10:
                continue
            saida.append({"id": r["identidade"], "folha": r["folha"], "cer": p["erros"]["prosa"] / p["total"]["prosa"], "conjunto": nome, **sinais_da_folha(r)})
    return saida


def _postos(v: np.ndarray) -> np.ndarray:
    ordem = v.argsort(kind="stable")
    postos = np.empty_like(ordem, dtype=np.float64)
    postos[ordem] = np.arange(v.size)
    for valor in np.unique(v):
        iguais = v == valor
        postos[iguais] = postos[iguais].mean()
    return postos


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return float("nan")
    return float(np.corrcoef(_postos(a), _postos(b))[0, 1])


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def ic_de_correlacao(folhas: Sequence[dict[str, Any]], sinal: str, medida: Callable[[np.ndarray, np.ndarray], float]) -> list[float]:
    """IC95 em dois níveis, como o da régua: sorteia livros, depois folhas dentro de cada um."""
    gerador = np.random.default_rng(SEMENTE)
    por_livro: dict[str, list[int]] = {}
    for i, f in enumerate(folhas):
        por_livro.setdefault(f["id"], []).append(i)
    livros = sorted(por_livro)
    s = np.array([f[sinal] for f in folhas])
    c = np.array([f["cer"] for f in folhas])
    valores = []
    for _ in range(REAMOSTRAS):
        indices: list[int] = []
        for livro in gerador.choice(len(livros), len(livros)):
            dele = por_livro[livros[int(livro)]]
            indices.extend(gerador.choice(dele, len(dele)).tolist())
        valor = medida(s[indices], c[indices])
        if not np.isnan(valor):
            valores.append(valor)
    return [round(float(np.percentile(valores, 2.5)), 3), round(float(np.percentile(valores, 97.5)), 3)] if valores else [float("nan")] * 2


def corte_do_sinal(folhas: Sequence[dict[str, Any]], sinal: str, ruim: float) -> float:
    """O corte que melhor separa as folhas ruins no pedaço reservado (Youden). Sem folha ruim lá, o p95."""
    s = np.array([f[sinal] for f in folhas])
    y = np.array([f["cer"] >= ruim for f in folhas])
    if not y.any() or y.all():
        return float(np.percentile(s, 95))
    melhor, valor = float("inf"), -1.0
    for candidato in np.unique(s):
        alarme = s >= candidato
        j = alarme[y].mean() - alarme[~y].mean()
        if j > valor:
            melhor, valor = float(candidato), float(j)
    return melhor


def alarme_de(folhas: Sequence[dict[str, Any]], sinal: str, corte: float, ruim: float) -> dict[str, Any]:
    s = np.array([f[sinal] for f in folhas])
    y = np.array([f["cer"] >= ruim for f in folhas])
    alarme = s >= corte
    return {
        "folhas": len(folhas), "ruins": int(y.sum()), "alarmes": int(alarme.sum()), "alarmes_falsos": int((alarme & ~y).sum()),
        "taxa_de_falso_alarme": round(float((alarme & ~y).sum() / max(1, alarme.sum())), 3),
        "alarme_em_folha_boa": round(float(alarme[~y].mean()), 3) if (~y).any() else None,
        "revocacao": round(float(alarme[y].mean()), 3) if y.any() else None,
    }


def bloco(pasta: Path, dominio: str, reservado: str, manifesto: str) -> dict[str, Any]:
    ajuste = amostra(pasta, reservado)
    valida = amostra(pasta, manifesto)
    tudo = ajuste + valida
    ruim = FOLHA_RUIM[dominio]
    saida: dict[str, Any] = {
        "folhas": {"reservado": len(ajuste), "manifesto": len(valida), "livros": len({f["id"] for f in tudo}), "ruins": sum(f["cer"] >= ruim for f in tudo)},
        "folha_ruim_a_partir_de": ruim,
        "sinais": {},
    }
    for sinal in ("discordancia", "densidade", "erro_estimado", "marcadas"):
        s, c = np.array([f[sinal] for f in tudo]), np.array([f["cer"] for f in tudo])
        rho = spearman(s, c)
        ic = ic_de_correlacao(tudo, sinal, spearman)
        por_livro = {f["id"]: None for f in tudo}
        for livro in por_livro:
            dele = [f for f in tudo if f["id"] == livro]
            por_livro[livro] = spearman(np.array([f[sinal] for f in dele]), np.array([f["cer"] for f in dele]))
        corte = corte_do_sinal(ajuste, sinal, ruim)
        no_manifesto = alarme_de(valida, sinal, corte, ruim)
        vira = abs(rho) >= 0.5 and (ic[0] >= 0.2 or ic[1] <= -0.2) and no_manifesto["taxa_de_falso_alarme"] <= 1 / 3 and no_manifesto["alarmes"] > 0
        saida["sinais"][sinal] = {
            "spearman": round(rho, 3), "spearman_ic95": ic, "pearson": round(pearson(s, c), 3),
            "spearman_mediana_dentro_do_livro": round(float(np.nanmedian(list(por_livro.values()))), 3),
            "corte_do_reservado": round(corte, 5), "alarme_no_manifesto": no_manifesto, "vira_alarme": bool(vira),
        }
    return saida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("--saida", default="")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pasta = Path(args.pasta)
    relatorio = {
        cp.DIGITAL: bloco(pasta, cp.DIGITAL, "reservado_ouro", "ouro_dev"),
        cp.SCAN: bloco(pasta, cp.SCAN, "reservado_prata", "prata"),
    }
    texto = json.dumps(relatorio, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.saida:
        Path(args.saida).write_bytes(texto.encode("utf-8"))
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
