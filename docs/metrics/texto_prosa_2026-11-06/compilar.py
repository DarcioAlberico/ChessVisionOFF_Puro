"""Compila `docs/metrics/texto_prosa_s712.json`, sem texto de livro nenhum.

Os JSONL vêm de fora do repositório, porque têm texto de livro: `rodar.py` nas folhas do `portao_*`, `medir.py folhas`
nos conjuntos, `medir.py perdidas`, `medir.py varrer`, e `censo_de_linhas.py`. `<pasta>` guarda os dois lados:

  compilar.py <saida.json> <pasta> <commit de antes> <commit de depois> <estilo.json>

Na pasta, com `T` em `antes` e `depois`: `ce_T`, `nv_T`, `ouro_T`, `prata_T` .jsonl, e `prata_gigantes`, `censo_antes`,
`censo_gigantes`, `censo_depois`, `perdidas`, `amostra_ce`, `varrer` .jsonl. `auditoria.json` é a conta das caixas que saíram.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "texto_prosa_2026-11-05"))

import medir  # noqa: E402


def _resumo(pasta: Path, nomes: list[str], commit: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        saida = Path(tmp) / "r.json"
        medir.resumir(str(saida), [str(pasta / f"{n}.jsonl") for n in nomes], commit)
        return json.loads(saida.read_text(encoding="utf-8"))


def _registros(caminho: Path) -> list[dict]:
    return [json.loads(ln) for ln in open(caminho, encoding="utf-8")]


def _censo(caminho: Path) -> dict:
    regs = _registros(caminho)
    linhas = sum(r["linhas"] for r in regs)
    altas = sum(len(r["altas"]) for r in regs)
    return {
        "folhas": len(regs),
        "livros": len({r["nome"] for r in regs}),
        "linhas": linhas,
        "altas": altas,
        "fracao": round(altas / max(1, linhas), 4),
        "altas_na_primeira_folha_do_livro": sum(len(r["altas"]) for r in regs if r["pagina"] == 0),
    }


def _textos_iguais(a: Path, b: Path, motor: str) -> dict:
    chave = lambda r: (r["livro"], r["pagina"])  # noqa: E731
    antes = {chave(r): r for r in _registros(a)}
    depois = {chave(r): r for r in _registros(b)}
    return {
        "folhas": len(antes),
        "texto_igual": sum(antes[k]["hip"][motor] == depois[k]["hip"][motor] for k in antes),
    }


def _folha_a_folha(a: Path, b: Path, motor: str) -> dict:
    chave = lambda r: (r["livro"], r["pagina"])  # noqa: E731
    antes = {chave(r): r for r in _registros(a)}
    depois = {chave(r): r for r in _registros(b)}
    erros = lambda r: r["placar"][f"{motor}|tip"]["erros"]["prosa"]  # noqa: E731
    return {
        "melhoraram": sum(erros(depois[k]) < erros(antes[k]) for k in antes),
        "pioraram": sum(erros(depois[k]) > erros(antes[k]) for k in antes),
        "iguais": sum(erros(depois[k]) == erros(antes[k]) for k in antes),
    }


def main(saida: str, pasta_: str, antes: str, depois: str, estilo: str) -> None:
    pasta = Path(pasta_)
    dep = _resumo(pasta, ["ouro_depois", "prata_depois", "perdidas", "amostra_ce", "varrer"], depois)
    ant = _resumo(pasta, ["ouro_antes", "prata_antes"], antes)
    relatorio: dict = {
        "item": "S-712",
        "regua": "texto_prosa_2026-10-30/banco.py",
        "dpi": medir.DPI,
        "medido_com": dep["medido_com"],
        "commit_de_antes": antes,
        "portao_nas_folhas_vistas": {
            "nota": "as 24 folhas do portão da S-711: foram olhadas para achar o conserto, e não julgam nada",
            "antes": _resumo(pasta, ["ce_antes"], antes)["portao_da_s711"],
            "depois": _resumo(pasta, ["ce_depois"], depois)["portao_da_s711"],
        },
        "portao_nas_folhas_nao_vistas": {
            "nota": "40 folhas de prosa, 20 por livro, fora das 24 e das duas fixtures; é o que a Saída pede",
            "antes": _resumo(pasta, ["nv_antes"], antes)["portao_da_s711"],
            "depois": _resumo(pasta, ["nv_depois"], depois)["portao_da_s711"],
            "tess_folha_a_folha": _folha_a_folha(pasta / "nv_antes.jsonl", pasta / "nv_depois.jsonl", "tess"),
            "glifo_folha_a_folha": _folha_a_folha(pasta / "nv_antes.jsonl", pasta / "nv_depois.jsonl", "glifo"),
        },
        "conjuntos": {
            nome: {"antes": ant["conjuntos"][nome], "depois": dep["conjuntos"][nome]} for nome in dep["conjuntos"]
        },
        "ouro_dev_folha_a_folha": {
            "glifo": _folha_a_folha(pasta / "ouro_antes.jsonl", pasta / "ouro_depois.jsonl", "glifo"),
            "camada_prosa": _folha_a_folha(pasta / "ouro_antes.jsonl", pasta / "ouro_depois.jsonl", "camada_prosa"),
            "texto_do_glifo": _textos_iguais(pasta / "ouro_antes.jsonl", pasta / "ouro_depois.jsonl", "glifo"),
        },
        "particao_sozinha_na_prata": {
            "nota": "gigantes ligado nos dois lados; só a partição pela projeção muda",
            "glifo": _folha_a_folha(pasta / "prata_gigantes.jsonl", pasta / "prata_depois.jsonl", "glifo"),
            "tess": _folha_a_folha(pasta / "prata_gigantes.jsonl", pasta / "prata_depois.jsonl", "tess"),
            "tess_cer": {
                "sem": medir._taxa(_registros(pasta / "prata_gigantes.jsonl"), "tess"),
                "com": medir._taxa(_registros(pasta / "prata_depois.jsonl"), "tess"),
            },
        },
        "folhas_perdidas": dep.get("folhas_perdidas"),
        "amostra_chess_evolution": dep.get("amostra_chess_evolution"),
        "varredura_da_guarda": dep.get("varredura_da_guarda"),
        "censo_de_linhas_altas": {
            "antes": _censo(pasta / "censo_antes.jsonl"),
            "so_gigantes": _censo(pasta / "censo_gigantes.jsonl"),
            "depois": _censo(pasta / "censo_depois.jsonl"),
            "ouro_dev_depois": json.loads((pasta / "ouro_altas.json").read_text(encoding="utf-8")),
            "ouro_dev_so_gigantes": json.loads((pasta / "ouro_altas_so_gigantes.json").read_text(encoding="utf-8")),
        },
        "auditoria_das_caixas": json.loads((pasta / "auditoria.json").read_text(encoding="utf-8")),
        "estilo": json.loads(Path(estilo).read_text(encoding="utf-8"))["total"],
    }
    Path(saida).write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main(*sys.argv[1:6])
