"""A saída da S-700: os números de 2026-10-30 pela régua do pacote, sem rodar motor nenhum.

Repontua os JSONL brutos de 2026-10-30 (`hip` e `ref` gravados; têm texto de livro, e por isso ficam fora do
repositório, nos dados locais da skill) com `text/regua_prosa.py` de dois jeitos:

  --prototipo   com o classificador do protótipo (`banco.classe_do_token`) injetado: prova o alinhamento e o
                placar novos contra o relatório, até a 4ª casa, e a normalização onde não há linha vazia;
  --normalizacao-antiga   com a normalização do protótipo, que não era idempotente: `a-

b` só se juntava na
                segunda passada. É o que sobra de diferença nos conjuntos com linha lida vazia (degradado, prata);
  (padrão)      com o classificador consertado da S-701: a diferença é o efeito dele, e sai por motor e conjunto.

Sem texto de livro na saída: `--saida` grava só números, e os tokens que mudaram de classe vão para a tela.

Uso: reproduzir_regua.py <pasta dos JSONL> [--prototipo] [--normalizacao-antiga] [--saida x.json] [--tokens]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "texto_prosa_2026-10-30"))
sys.stdout.reconfigure(encoding="utf-8")

import banco  # noqa: E402

from chess_diagram_ocr.text import regua_prosa as regua  # noqa: E402

CONJUNTOS = {
    "ouro_dev_completo": "ouro_completo.jsonl",
    "ouro_dev_sem_folha_perdida": "ouro_sem_perdida.jsonl",
    "ouro_dev_6_livros_leiaute_limpo": "ouro_6livros.jsonl",
    "ouro_dev_estrato_misto": "misto.jsonl",
    "degradado_medio_mesmas_folhas": "degradado.jsonl",
    "prata_todas": "prata.jsonl",
    "prata_admitida": "prata_admitida.jsonl",
}


def _linha(placares: list[regua.Placar], livros: list[str]) -> dict:
    ponto, baixo, alto = regua.ic95([p.erros["prosa"] for p in placares], [p.total["prosa"] for p in placares], livros)
    soma = regua.Placar()
    for p in placares:
        soma.somar(p)
    return {
        "cer_prosa": ponto, "ic95": (baixo, alto), "wer_prosa": soma.wer_prosa(), "cer_notacao": soma.cer("notacao"),
        "cer_outro": soma.cer("outro"), "cer_espaco": soma.cer("espaco"), "insercoes": soma.insercoes,
        "fig_revocacao": soma.fig_tp / max(1, soma.fig_ref), "fig_precisao": soma.fig_tp / max(1, soma.fig_hip),
        "caracteres_prosa": soma.total["prosa"], "palavras_prosa": soma.wer_n,
    }


def repontuar(caminho: Path, *, prototipo: bool, normalizacao_antiga: bool = False) -> dict[str, dict]:
    registros = [json.loads(lin) for lin in caminho.open(encoding="utf-8")]
    motores = list(registros[0]["hip"])
    saida = {}
    for motor in motores:
        for modo in regua.MODOS:
            placares = []
            for r in registros:
                if normalizacao_antiga:
                    ref = banco.normalizar(r["ref"], tipografia=modo == regua.TIP, lang=r["lang"])
                    hip = banco.normalizar(r["hip"][motor], tipografia=modo == regua.TIP, lang=r["lang"])
                else:
                    ref = regua.normalizar(r["ref"], modo, r["lang"])
                    hip = regua.normalizar(r["hip"][motor], modo, r["lang"])
                placares.append(regua.pontuar(ref, hip, r["lang"], classificar=banco.classe_do_token if prototipo else None))
            saida[f"{motor}|{modo}"] = _linha(placares, [r["livro"] for r in registros])
    return saida


def tokens_que_mudaram(caminho: Path) -> Counter:
    mudaram: Counter = Counter()
    for lin in caminho.open(encoding="utf-8"):
        r = json.loads(lin)
        for token in regua.normalizar(r["ref"], regua.TIP, r["lang"]).split():
            antes, depois = banco.classe_do_token(token), regua.classe_do_token(token, r["lang"])
            if antes != depois:
                mudaram[f"{antes}->{depois}"] += 1
                mudaram[f"{antes}->{depois} {token}"] += 1
    return mudaram


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dados")
    ap.add_argument("--prototipo", action="store_true")
    ap.add_argument("--normalizacao-antiga", action="store_true", help="a do protótipo: prova que o que sobra é a idempotência")
    ap.add_argument("--saida")
    ap.add_argument("--tokens", action="store_true")
    ap.add_argument("--conjunto", action="append")
    args = ap.parse_args()
    publicado = json.loads((AQUI.parent / "texto_prosa_20261030.json").read_text(encoding="utf-8"))["conjuntos"]
    resultado = {"classificador": "prototipo" if args.prototipo else regua.VERSAO_CLASSIFICADOR, "conjuntos": {}}
    for nome, arquivo in CONJUNTOS.items():
        if args.conjunto and nome not in args.conjunto:
            continue
        medido = repontuar(Path(args.dados) / arquivo, prototipo=args.prototipo, normalizacao_antiga=args.normalizacao_antiga)
        tabela = {}
        for chave, linha in medido.items():
            motor, modo = chave.split("|")
            antigo = publicado[nome]["motores"].get(motor, {}).get(modo)
            if antigo is None:
                continue
            campos = {"cer_prosa": "cer_prosa", "wer_prosa": "wer_prosa_sdi", "cer_notacao": "cer_notacao", "cer_espaco": "cer_espaco",
                      "fig_revocacao": "figurina_revocacao", "fig_precisao": "figurina_precisao"}
            difs = {c: round(linha[c] - antigo[d], 6) for c, d in campos.items()}
            difs["insercoes"] = 0.0 if linha["insercoes"] == antigo["insercoes"] else 1.0
            maior = max((abs(v) for v in difs.values()), default=0.0)
            tabela[chave] = {"novo": round(linha["cer_prosa"], 5), "publicado": antigo["cer_prosa"], "maior_diferenca": maior,
                             "ic95_novo": [round(v, 5) for v in linha["ic95"]], "ic95_publicado": antigo.get("ic95_prosa_dois_niveis"),
                             "wer_novo": round(linha["wer_prosa"], 5), "wer_publicado": antigo["wer_prosa_sdi"]}
        resultado["conjuntos"][nome] = tabela
        # O publicado tem 4 casas: até 0,00005 é o arredondamento dele. Além disso, um pouco de folga de ponto flutuante.
        fora = {k: v for k, v in tabela.items() if v["maior_diferenca"] > 0.0000501}
        print(f"{nome}: {len(tabela)} linhas, {len(fora)} com diferença na 4ª casa")
        for k, v in sorted(fora.items(), key=lambda x: -x[1]["maior_diferenca"])[:40 if args.prototipo else 8]:
            print(f"   {k:22s} CER {v['publicado']:.5f} -> {v['novo']:.5f}  WER {v['wer_publicado']} -> {v['wer_novo']}  maior {v['maior_diferenca']:.5f}")
        if args.tokens:
            mudaram = tokens_que_mudaram(Path(args.dados) / arquivo)
            print("   ", {k: v for k, v in mudaram.items() if " " not in k})
            print("   ", [(k.split(" ", 1)[1], v) for k, v in mudaram.most_common(60) if " " in k])
    if args.saida:
        Path(args.saida).write_bytes((json.dumps(resultado, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
