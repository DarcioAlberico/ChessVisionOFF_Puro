"""Compila `docs/metrics/texto_prosa_s712.json`, sem texto de livro nenhum.

Os JSONL vêm de fora do repositório, porque têm texto de livro: `rodar.py` nas folhas do `portao_*`, `medir.py folhas`
nos conjuntos, `medir.py perdidas`, `medir.py varrer`, e `censo_de_linhas.py`. `<pasta>` guarda os dois lados:

  compilar.py <saida.json> <pasta> <commit de antes> <commit de depois> <estilo.json>

Na pasta, com `T` em `antes` e `depois`: `ce_T`, `nv_T`, `ouro_T`, `prata_T` .jsonl; e mais:

- `prata_gigantes.jsonl` e `nv_gigantes.jsonl`: com `duas_linhas.PARTIR_LINHA_ALTA` desligada;
- `censo_antes`, `censo_gigantes`, `censo_depois` .jsonl: `censo_de_linhas.py`, com `--sem-particao` no segundo;
- `ouro_altas_antes.json`, `ouro_altas.json`, `ouro_altas_so_gigantes.json`: `censo_de_linhas.py --ouro`;
- `auditoria.json`: `auditoria_das_caixas.py`;
- `equivalencia_da_tinta.json`: `equivalencia_da_tinta.py`;
- `perdidas`, `amostra_ce`, `varrer` .jsonl: `medir.py`.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "texto_prosa_2026-11-05"))

import medir  # noqa: E402

CONFERIDO = (
    "as 47 caixas que tocam a camada ou em que o Tesseract le palavra de 3 letras, e o mosaico das 264 de tamanho de letra: 19 fios sao as "
    "barras do codigo de barras de uma contracapa; 7 sao a faixa do Chess Evolution, com o titulo dela; a caixa do Nunn 326 e a moldura de "
    "uma tabela, unica a sair da folha, e as letras de dentro ficam; o resto e capa, contracapa, foto, anuncio, ornamento e um tabuleiro "
    "que o detector nao viu. Duas eram letra: o n e o u do titulo da capa do Estrin, classe mancha, devolvidas por TINTA_DE_MANCHA 0,9"
)


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
        "as_que_pioraram": [[k[0], k[1], erros(antes[k]), erros(depois[k])] for k in sorted(antes) if erros(depois[k]) > erros(antes[k])],
    }


def _ligaduras_perdidas(caminho: Path) -> dict:
    """`afer` e `lef` na camada, sem o `t` que a tinta tem: o Tesseract acerta a palavra, e a régua conta erro."""
    regs = _registros(caminho)
    achadas = sum(len(re.findall(r"\b(?:afer|lef)\b", r["ref"], re.IGNORECASE)) for r in regs)
    return {
        "ocorrencias_na_referencia": achadas,
        "erros_de_prosa_do_tesseract": sum(r["placar"]["tess|tip"]["erros"]["prosa"] for r in regs),
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
            "ligaduras_perdidas_na_camada": _ligaduras_perdidas(pasta / "nv_depois.jsonl"),
            "cer_de_prosa_por_motor": {
                lado: {motor: medir._taxa(_registros(pasta / f"nv_{lado}.jsonl"), motor) for motor in ("glifo", "fusao", "tess")}
                for lado in ("antes", "depois")
            },
        },
        "conjuntos": {
            nome: {"antes": ant["conjuntos"][nome], "depois": dep["conjuntos"][nome]} for nome in dep["conjuntos"]
        },
        "ouro_dev_folha_a_folha": {
            "glifo": _folha_a_folha(pasta / "ouro_antes.jsonl", pasta / "ouro_depois.jsonl", "glifo"),
            "camada_prosa": _folha_a_folha(pasta / "ouro_antes.jsonl", pasta / "ouro_depois.jsonl", "camada_prosa"),
            "texto_do_glifo": _textos_iguais(pasta / "ouro_antes.jsonl", pasta / "ouro_depois.jsonl", "glifo"),
        },
        "prata_folha_a_folha": {
            motor: _folha_a_folha(pasta / "prata_antes.jsonl", pasta / "prata_depois.jsonl", motor) for motor in ("glifo", "fusao", "tess")
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
        "particao_sozinha_nos_chess_evolution": {
            "nota": "as 40 não vistas; é aqui que a partição muda folha de livro digital",
            "tess": _folha_a_folha(pasta / "nv_gigantes.jsonl", pasta / "nv_depois.jsonl", "tess"),
            "glifo": _folha_a_folha(pasta / "nv_gigantes.jsonl", pasta / "nv_depois.jsonl", "glifo"),
            "tess_cer": {
                "sem": medir._taxa(_registros(pasta / "nv_gigantes.jsonl"), "tess"),
                "com": medir._taxa(_registros(pasta / "nv_depois.jsonl"), "tess"),
            },
        },
        "folhas_perdidas": dep.get("folhas_perdidas"),
        "amostra_chess_evolution": dep.get("amostra_chess_evolution"),
        "varredura_da_guarda": dep.get("varredura_da_guarda"),
        "censo_de_linhas_altas": {
            "antes": _censo(pasta / "censo_antes.jsonl"),
            "so_gigantes": _censo(pasta / "censo_gigantes.jsonl"),
            "depois": _censo(pasta / "censo_depois.jsonl"),
            "ouro_dev_antes": json.loads((pasta / "ouro_altas_antes.json").read_text(encoding="utf-8")),
            "ouro_dev_depois": json.loads((pasta / "ouro_altas.json").read_text(encoding="utf-8")),
            "ouro_dev_so_gigantes": json.loads((pasta / "ouro_altas_so_gigantes.json").read_text(encoding="utf-8")),
        },
        "auditoria_das_caixas": json.loads((pasta / "auditoria.json").read_text(encoding="utf-8")),
        "auditoria_conferida_a_vista": CONFERIDO,
        "mudanca_depois_de_medir": {
            "commit": "0d950439",
            **json.loads((pasta / "equivalencia_da_tinta.json").read_text(encoding="utf-8")),
        },
        "estilo": json.loads(Path(estilo).read_text(encoding="utf-8"))["total"],
    }
    Path(saida).write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main(*sys.argv[1:6])
