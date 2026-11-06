"""Ajusta o calibrador da S-760 e mede a marca da S-761, sem rodar motor: tudo sai dos JSONL de `coletar.py`.

    ajustar.py <pasta dos jsonl> [--saida relatorio.json]

O **pedaço reservado** ajusta; as folhas do manifesto (`ouro_dev`, `prata`) validam; e, para não depender de um corte só, cada livro é
também medido com um calibrador que não o viu (`deixa um livro de fora`). Corte e coeficientes saem do pedaço reservado, e nunca do que valida.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rotular  # noqa: E402

from chess_diagram_ocr.text import calibracao, fusao, ouro, regua_prosa  # noqa: E402
from chess_diagram_ocr.text import confianca_palavra as cp

FRACAO = 0.05
CORTE_DA_FOLHA_DE_REFERENCIA_RUIM = 0.10
"""A folha em que a própria referência não bate (ordem de coluna, OCR de terceiro): `CER > 10%` na prosa pelo oráculo, ou, no ouro, pela
fusão. O relatório publica com e sem ela: tirar a folha ruim do placar sem dizer seria ajustar a régua."""


def _tokens(linhas: list[list[dict[str, Any]]]) -> list[list[fusao.Token]]:
    return [
        [fusao.Token(t["texto"], t["origem"], t["do_glifo"], t["confianca"], t["do_leitor"]) for t in linha]
        for linha in linhas
    ]


def amostras(registros: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Por folha: a matriz de atributos, o rótulo, e o que falta à conta (palavras sem rótulo e palavras perdidas)."""
    saida = []
    for r in registros:
        existe = fusao.existe_do_livro(r["lingua"])
        linhas = _tokens(r["tokens"])
        valores = [[cp.atributos(t, existe=existe) for t in linha] for linha in linhas]
        rotulados, sem_rotulo = rotular.tokens_rotulados(r)
        rotulo = rotular.rotular_linhas(r["ref"], [ln["texto"] for ln in r["linhas"]], r["lingua"])
        x, y = [], []
        for _token, errada, _prosa, n, k in rotulados:
            x.append(valores[n][k])
            y.append(errada)
        p = r["placar"]["fusao|tip"]
        o = r["placar"].get("tess_oraculo|tip")
        saida.append({
            "id": r["identidade"], "folha": r["folha"], "lingua": r["lingua"],
            "x": np.array(x, dtype=np.float64).reshape(-1, len(cp.NOMES)), "y": np.array(y, dtype=bool),
            "palavras": sum(len(ln) for ln in linhas), "sem_rotulo": sem_rotulo, "perdidas": rotulo["perdidas"],
            "cer": p["erros"]["prosa"] / max(1, p["total"]["prosa"]),
            "oraculo": None if o is None else o["erros"]["prosa"] / max(1, o["total"]["prosa"]),
            "ref_ruim": (o["erros"]["prosa"] / max(1, o["total"]["prosa"]) if o else p["erros"]["prosa"] / max(1, p["total"]["prosa"])) > CORTE_DA_FOLHA_DE_REFERENCIA_RUIM,
            "regra": r["regra"],
        })
    return saida


def ajustar(x: np.ndarray, y: np.ndarray, *, l2: float = 1.0, iteracoes: int = 30, colunas: Sequence[int] | None = None) -> np.ndarray:
    """Logística por Newton, com L2 em tudo menos o viés. `colunas` restringe o conjunto: as outras ficam em zero."""
    usadas = list(range(x.shape[1])) if colunas is None else list(colunas)
    z = x[:, usadas]
    pesos = np.zeros(z.shape[1])
    lambda_ = np.full(z.shape[1], l2)
    lambda_[0] = 1e-6
    for _ in range(iteracoes):
        p = 1.0 / (1.0 + np.exp(-np.clip(z @ pesos, -30, 30)))
        s = np.clip(p * (1 - p), 1e-6, None)
        grad = z.T @ (p - y) + lambda_ * pesos
        hess = (z * s[:, None]).T @ z + np.diag(lambda_)
        passo = np.linalg.solve(hess, grad)
        pesos = pesos - passo
        if np.abs(passo).max() < 1e-6:
            break
    cheio = np.zeros(x.shape[1])
    cheio[usadas] = pesos
    return cheio


def prob(x: np.ndarray, pesos: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x @ pesos, -30, 30)))


def corte_da_fracao(p: np.ndarray, fracao: float = FRACAO) -> float:
    """O menor `p` que ainda fica dentro da fração, no conjunto que ajusta."""
    if p.size == 0:
        return 1.0
    ordem = np.sort(p)[::-1]
    return float(ordem[max(0, int(p.size * fracao) - 1)])


def marcar_por_corte(folhas: Sequence[dict[str, Any]], pesos: np.ndarray, corte: float) -> list[tuple[int, int, int, int]]:
    """Por folha: `(capturadas, erradas, marcadas, palavras)`, com o corte global."""
    return [
        (int(((p := prob(f["x"], pesos)) >= corte)[f["y"]].sum()), int(f["y"].sum()), int((p >= corte).sum()), int(f["y"].size))
        for f in folhas
    ]


def marcar_por_folha(folhas: Sequence[dict[str, Any]], pesos: np.ndarray, fracao: float = FRACAO) -> list[tuple[int, int, int, int]]:
    """A marca da S-718: as mais suspeitas de cada folha, até o teto dela, arredondando para baixo."""
    saida = []
    for f in folhas:
        p = prob(f["x"], pesos)
        teto = int(f["y"].size * fracao)
        ordem = np.argsort(-p, kind="stable")[:teto]
        saida.append((int(f["y"][ordem].sum()), int(f["y"].sum()), teto, int(f["y"].size)))
    return saida


def placar(contas: Sequence[tuple[int, int, int, int]], folhas: Sequence[dict[str, Any]]) -> dict[str, Any]:
    cap = [c[0] for c in contas]
    err = [c[1] for c in contas]
    mar = [c[2] for c in contas]
    pal = [c[3] for c in contas]
    livros = [f["id"] for f in folhas]
    ponto, baixo, alto = regua_prosa.ic95(cap, err, livros)
    _, fb, fa = regua_prosa.ic95(mar, pal, livros)
    return {
        "folhas": len(folhas), "livros": len(set(livros)), "palavras": sum(pal), "erradas": sum(err), "capturadas": sum(cap), "marcadas": sum(mar),
        "captura": round(float(ponto), 4), "captura_ic95": [round(float(baixo), 4), round(float(alto), 4)],
        "fracao_marcada": round(sum(mar) / max(1, sum(pal)), 4), "fracao_ic95": [round(float(fb), 4), round(float(fa), 4)],
        "palavras_perdidas_que_marca_nenhuma_alcanca": sum(f["perdidas"] for f in folhas),
    }


def fracao_travada(folhas: Sequence[dict[str, Any]], pesos: np.ndarray, fracoes: Sequence[float] = (0.01, 0.02, 0.03, 0.05, 0.1, 0.2)) -> list[dict[str, Any]]:
    """A curva captura × fração marcada, **com o corte tirado do próprio conjunto**: é a G5 da S-718, com a fração travada, e mede só o ranque."""
    x, _ = juntar(folhas)
    p = prob(x, pesos)
    saida = []
    for fracao in fracoes:
        m = placar(marcar_por_corte(folhas, pesos, corte_da_fracao(p, fracao)), folhas)
        saida.append({"fracao_pedida": fracao, "fracao_marcada": m["fracao_marcada"], "captura": m["captura"], "captura_ic95": m["captura_ic95"]})
    return saida


def risco_cobertura(p_certa: np.ndarray, y: np.ndarray) -> list[dict[str, float]]:
    """Aceitando sem revisão as N% de maior confiança, quanto erro fica nelas: a curva que uma confiança constante não passa."""
    ordem = np.argsort(-p_certa, kind="stable")
    erros = np.cumsum(y[ordem])
    saida = []
    for cobertura in (0.5, 0.8, 0.9, 0.95, 0.98, 0.99, 1.0):
        n = max(1, int(round(cobertura * y.size)))
        saida.append({"cobertura": cobertura, "erro_restante": round(float(erros[n - 1] / n), 5), "erros_aceitos": int(erros[n - 1])})
    return saida


def calibracao_de(p_certa: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    linhas = calibracao.curva_de_confianca(list(map(float, p_certa)), list(map(bool, ~y)), faixas=10)
    ponderado, por_faixa = calibracao.ece_da_curva(linhas)
    return {"ece": round(ponderado, 5), "ece_por_faixa": round(por_faixa, 5), "curva": [f.como_dicionario() for f in linhas]}


def juntar(folhas: Sequence[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    return np.vstack([f["x"] for f in folhas]), np.concatenate([f["y"] for f in folhas])


def deixa_um_livro_de_fora(folhas: Sequence[dict[str, Any]], *, colunas: Sequence[int] | None = None) -> dict[str, Any]:
    """Cada livro medido por um calibrador e um corte que não o viram. O livro da exclusão da S-750 é medido, e nunca ajusta."""
    excluidos = ouro.carregar_exclusao().identidades
    por_livro = defaultdict(list)
    for f in folhas:
        por_livro[f["id"]].append(f)
    contas, ordem = [], []
    contas_do_teto: list[tuple[int, int, int, int]] = []
    ps, ys = [], []
    for livro, dele in por_livro.items():
        outros = [f for f in folhas if f["id"] != livro and f["id"] not in excluidos]
        x, y = juntar(outros)
        pesos = ajustar(x, y, colunas=colunas)
        corte = corte_da_fracao(prob(x, pesos))
        contas.extend(marcar_por_corte(dele, pesos, corte))
        contas_do_teto.extend(marcar_por_folha(dele, pesos))
        ordem.extend(dele)
        xd, yd = juntar(dele)
        ps.append(1 - prob(xd, pesos))
        ys.append(yd)
    p, y = np.concatenate(ps), np.concatenate(ys)
    return {"marca": placar(contas, ordem), "marca_por_teto_de_folha": placar(contas_do_teto, ordem), **calibracao_de(p, y), "risco_cobertura": risco_cobertura(p, y)}


def dos_dados(pasta: Path, *nomes: str) -> list[dict[str, Any]]:
    return amostras([r for nome in nomes for r in rotular.ler(pasta / f"{nome}.jsonl") if r["tokens"]])


def marca_s718(folhas: Sequence[dict[str, Any]], registros: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """O ranque por folha da S-718 **refeito sobre os tokens**, com o mesmo rótulo. Os `revisar_em` gravados já são os da S-761, com a S-760 ligada."""
    contas = []
    for r in registros:
        marcadas = fusao.marcar(_tokens(r["tokens"]), existe=fusao.existe_do_livro(r["lingua"]))
        rotulados, _ = rotular.tokens_rotulados(r)
        contas.append((
            sum(1 for _t, errada, _p, n, k in rotulados if errada and k in marcadas[n]),
            sum(1 for _t, errada, _p, _n, _k in rotulados if errada),
            sum(1 for _t, _e, _p, n, k in rotulados if k in marcadas[n]),
            len(rotulados),
        ))
    return placar(contas, folhas)


def marca_gravada(folhas: Sequence[dict[str, Any]], registros: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """A marca que `ler_pagina` escreveu, lida em `revisar_em`: é o que o produto mostra."""
    contas = []
    for r in registros:
        rotulo = rotular.rotular_linhas(r["ref"], [ln["texto"] for ln in r["linhas"]], r["lingua"])
        marcadas = capturadas = palavras = 0
        erradas = sum(sum(x) for x in rotulo["errada"])
        for ln, erro in zip(r["linhas"], rotulo["errada"], strict=True):
            posicao = 0
            for k, token in enumerate(ln["texto"].split()):
                inicio = ln["texto"].index(token, posicao)
                posicao = inicio + len(token)
                palavras += 1
                if any(a < posicao and inicio < b for a, b in ln["revisar_em"]):
                    marcadas += 1
                    capturadas += erro[k]
        contas.append((capturadas, erradas, marcadas, palavras))
    return placar(contas, folhas)


def comparacao(pasta: Path, ajuste: str, valida: str, uniao: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """O que havia antes, e a armadilha: a confiança de quem escreveu, a marca da S-718 e uma constante, no mesmo conjunto."""
    registros = [r for nome in (ajuste, valida) for r in rotular.ler(pasta / f"{nome}.jsonl") if r["tokens"]]
    chaves = {(f["id"], f["folha"]) for f in uniao}
    registros = [r for r in registros if (r["identidade"], r["folha"]) in chaves]
    por_chave = {(f["id"], f["folha"]): f for f in uniao}
    folhas = [por_chave[(r["identidade"], r["folha"])] for r in registros]
    conf, certo = [], []
    for r in registros:
        for token, errada, _prosa, _n, _k in rotular.tokens_rotulados(r)[0]:
            if token["confianca"] is not None:
                conf.append(float(token["confianca"]))
                certo.append(errada)
    c, y = np.array(conf), np.array(certo, dtype=bool)
    constante = np.full(y.size, 1 - float(y.mean()))
    return {
        "marca_s718": marca_s718(folhas, registros),
        "confianca_de_quem_escreveu": {**calibracao_de(c, y), "risco_cobertura": risco_cobertura(c, y)},
        "constante": {**calibracao_de(constante, y), "risco_cobertura": risco_cobertura(constante, y)},
    }


def do_produto(pasta: Path, anterior: str, produto: str) -> dict[str, Any]:
    """A marca que `ler_pagina` escreveu, relida em `revisar_em`, e a prova de que o calibrador não mexeu no texto."""
    antes = {(r["identidade"], r["folha"]): r["hip"]["fusao"] for r in rotular.ler(pasta / f"{anterior}.jsonl")}
    registros = rotular.ler(pasta / f"{produto}.jsonl")
    folhas = [{"id": r["identidade"], "perdidas": rotular.rotular_linhas(r["ref"], [ln["texto"] for ln in r["linhas"]], r["lingua"])["perdidas"]} for r in registros]
    return {
        "folhas_com_texto_diferente_de_antes": sum(antes[(r["identidade"], r["folha"])] != r["hip"]["fusao"] for r in registros),
        "folhas_comparadas": len(registros),
        **marca_gravada(folhas, registros),
    }


def bloco_do_dominio(pasta: Path, ajuste: str, valida: str) -> tuple[dict[str, Any], np.ndarray, float]:
    no_ajuste = dos_dados(pasta, ajuste)
    if ajuste == "reservado_prata":
        no_ajuste = [f for f in no_ajuste if not f["ref_ruim"]]
    na_validacao = dos_dados(pasta, valida)
    x, y = juntar(no_ajuste)
    pesos = ajustar(x, y)
    corte = corte_da_fracao(prob(x, pesos))
    xv, yv = juntar(na_validacao)
    limpas = [f for f in na_validacao if not f["ref_ruim"]]
    registros = [r for r in rotular.ler(pasta / f"{valida}.jsonl") if r["tokens"]]
    uniao = no_ajuste + na_validacao
    bloco = {
        "ajuste": {
            "conjunto": ajuste, "folhas": len(no_ajuste), "livros": len({f["id"] for f in no_ajuste}), "identidades": sorted({f["id"] for f in no_ajuste}),
            "palavras": int(y.size), "erradas": int(y.sum()),
        },
        "pesos": dict(zip(cp.NOMES, [round(float(v), 4) for v in pesos], strict=True)),
        "corte_de_revisar": round(corte, 5),
        "validacao": {
            "conjunto": valida,
            "calibracao": calibracao_de(1 - prob(xv, pesos), yv),
            "risco_cobertura": risco_cobertura(1 - prob(xv, pesos), yv),
            "marca_de_hoje_s718": marca_s718(na_validacao, registros),
            "marca_por_corte": placar(marcar_por_corte(na_validacao, pesos, corte), na_validacao),
            "marca_por_teto_de_folha": placar(marcar_por_folha(na_validacao, pesos), na_validacao),
            "captura_com_a_fracao_travada": fracao_travada(na_validacao, pesos),
            "marca_por_corte_sem_folha_de_referencia_ruim": placar(marcar_por_corte(limpas, pesos, corte), limpas) if limpas else None,
        },
        "deixa_um_livro_de_fora": deixa_um_livro_de_fora(uniao),
        "linha_de_comparacao": comparacao(pasta, ajuste, valida, uniao),
    }
    return bloco, pesos, corte


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("--saida", default="")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pasta = Path(args.pasta)
    relatorio: dict[str, Any] = {}
    for dominio, ajuste, valida in ((cp.DIGITAL, "reservado_ouro", "ouro_dev"), (cp.SCAN, "reservado_prata", "prata")):
        if not (pasta / f"{ajuste}.jsonl").is_file():
            continue
        bloco, pesos, corte = bloco_do_dominio(pasta, ajuste, valida)
        if (pasta / f"produto_{valida}.jsonl").is_file():
            bloco["validacao"]["marca_no_produto"] = do_produto(pasta, valida, f"produto_{valida}")
        relatorio[dominio] = bloco
        print(dominio, "pesos =", tuple(round(float(v), 4) for v in pesos), "corte =", round(corte, 5))
    if args.saida:
        Path(args.saida).write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    else:
        print(json.dumps(relatorio, ensure_ascii=False, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
