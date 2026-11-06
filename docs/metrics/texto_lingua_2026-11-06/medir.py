"""Mede a língua do livro e o léxico por língua (S-723, S-728), com a régua de 2026-10-30.

Uso (com o `.venv` do projeto, `PYTHONPATH=<arvore>/src`, `CVOFF_RAIZ` no checkout com `PDF/` e a saída fora do repositório):

  medir.py glifo <saida.jsonl>                         o texto do glifo no ouro-dev, por sha, para comparar duas árvores
  medir.py comparar <a.jsonl> <b.jsonl>                quantas folhas do ouro-dev diferem entre as duas corridas
  medir.py deteccao <saida.jsonl> [--orcamento S]      as primeiras folhas lidas de cada livro deduplicado de `PDF/`
  medir.py fusao <saida.jsonl> [--orcamento S]         a fusão do ouro-dev, com o léxico de antes e com o da língua
  medir.py resumir <saida.json> <deteccao.jsonl> [--fusao F] [--glifo-iguais N --glifo-folhas M]

`--orcamento` para a corrida depois de tantos segundos, sem perder nada: rodar de novo continua de onde parou. **A saída
dos comandos de leitura tem texto de livro comercial** (na fusão): mande-a para fora do repositório. Só o `resumir` escreve
dentro dele, e o que ele escreve são contagens e identidades.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "texto_prosa_2026-10-30"))
sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(os.environ.get("CVOFF_RAIZ") or Path(__file__).resolve().parents[3])
MODELO = RAIZ / "models" / "char_classifier.pt"
RELATORIO = Path(__file__).resolve().parent.parent / "texto_prosa_20261030.json"
TABELA = Path(__file__).resolve().parent / "linguas_declaradas.json"
DPI = 220
FOLHAS = 10
TENTATIVAS = 40
"""Quantas folhas do começo do livro, no máximo, para achar as dez lidas com texto."""


def _reconhecedor():
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

    return build_glyph_recognizer(str(MODELO))


def _folhas_do_ouro():
    conjunto = json.loads(RELATORIO.read_text(encoding="utf-8"))["conjuntos"]["ouro_dev_completo"]["por_livro"]
    for livro, info in conjunto.items():
        for folha in info["folhas"]:
            yield livro, info["lingua"], folha - 1


def _ja_lidas(saida: Path) -> list[dict]:
    if not saida.exists():
        return []
    return [json.loads(linha) for linha in saida.read_text(encoding="utf-8").splitlines() if linha.strip()]


def glifo(saida: Path) -> None:
    from chess_diagram_ocr.text.leitor import ler_pagina

    reconhecedor = _reconhecedor()
    primeiro = next(_folhas_do_ouro())
    ler_pagina(RAIZ / "PDF" / primeiro[0], primeiro[2], dpi=DPI, motor="glifo", reconhecedor=reconhecedor)  # o aquecimento
    with saida.open("w", encoding="utf-8", newline="\n") as fluxo:
        for livro, _lingua, folha in _folhas_do_ouro():
            texto = ler_pagina(RAIZ / "PDF" / livro, folha, dpi=DPI, motor="glifo", reconhecedor=reconhecedor).texto()
            fluxo.write(json.dumps({"livro": livro, "folha": folha, "sha": hashlib.sha256(texto.encode()).hexdigest(), "n": len(texto)}) + "\n")
    print("gravado", saida)


def comparar(a: Path, b: Path) -> None:
    x = {(r["livro"], r["folha"]): r["sha"] for r in _ja_lidas(a)}
    y = {(r["livro"], r["folha"]): r["sha"] for r in _ja_lidas(b)}
    assert x.keys() == y.keys() and x, "as duas corridas não leram as mesmas folhas"
    diferentes = sorted(chave for chave in x if x[chave] != y[chave])
    print(f"{len(x)} folhas, {len(diferentes)} diferentes", diferentes)


def _tabela() -> dict:
    return json.loads(TABELA.read_text(encoding="utf-8"))["livros"]


def deteccao(saida: Path, orcamento: float) -> None:
    """As dez primeiras folhas **com texto** de cada livro, em duas fontes: o que o glifo lê, e a camada do PDF."""
    import fitz

    from chess_diagram_ocr.text import lingua
    from chess_diagram_ocr.text.leitor import ler_pagina

    feitos = {r["livro"] for r in _ja_lidas(saida)}
    tabela = _tabela()
    inicio = time.monotonic()
    reconhecedor = None
    for livro, declarada in tabela.items():
        if livro in feitos:
            continue
        if time.monotonic() - inicio > orcamento:
            print("orçamento gasto; rode de novo para continuar")
            return
        if reconhecedor is None:
            reconhecedor = _reconhecedor()
        caminho = RAIZ / "PDF" / livro
        doc = fitz.open(caminho)
        total = doc.page_count
        do_glifo = lingua.LinguaDoLivro()
        da_camada = lingua.LinguaDoLivro()
        decidiu_em = {"glifo": None, "camada": None}
        lidas = 0
        for indice in range(min(total, TENTATIVAS)):
            if len(do_glifo.folhas) >= FOLHAS:
                break
            lidas += 1
            camada = doc[indice].get_text()
            da_camada = da_camada.com_folha(indice, camada)
            do_glifo = do_glifo.com_folha(indice, ler_pagina(caminho, indice, dpi=DPI, motor="glifo", reconhecedor=reconhecedor).texto())
            if decidiu_em["glifo"] is None and do_glifo.detectada == declarada:
                decidiu_em["glifo"] = lidas
            if decidiu_em["camada"] is None and da_camada.detectada == declarada:
                decidiu_em["camada"] = lidas
        doc.close()
        registro = {
            "livro": livro,
            "declarada": declarada,
            "folhas_abertas": lidas,
            "glifo": do_glifo.para_json(),
            "camada": da_camada.para_json(),
            "decidiu_em": decidiu_em,
        }
        with saida.open("a", encoding="utf-8", newline="\n") as fluxo:
            fluxo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        print(f"{declarada} glifo={do_glifo.detectada or '-'} camada={da_camada.detectada or '-'} {livro[:60]}", flush=True)
    print("fim")


def fusao(saida: Path, orcamento: float) -> None:
    """A fusão no ouro-dev: `antes` é o léxico de sempre, `depois` é o da língua, as duas com o `tessdata` da língua do livro."""
    import banco

    from chess_diagram_ocr.text import fusao as modulo
    from chess_diagram_ocr.text.leitor import ler_pagina

    feitas = {(r["livro"], r["folha"]) for r in _ja_lidas(saida)}
    reconhecedor = None
    inicio = time.monotonic()
    for livro, lingua_do_livro, folha in _folhas_do_ouro():
        if (livro, folha) in feitas:
            continue
        if time.monotonic() - inicio > orcamento:
            print("orçamento gasto; rode de novo para continuar")
            return
        if reconhecedor is None:
            reconhecedor = _reconhecedor()
            primeiro = next(_folhas_do_ouro())
            ler_pagina(RAIZ / "PDF" / primeiro[0], primeiro[2], dpi=DPI, motor="glifo", reconhecedor=reconhecedor)
        caminho = RAIZ / "PDF" / livro
        referencia = ler_pagina(caminho, folha, dpi=DPI, motor="camada")
        registro = {"livro": livro, "folha": folha, "lingua": lingua_do_livro, "ref": banco.texto_da_pagina(referencia) if hasattr(banco, "texto_da_pagina") else referencia.texto()}
        for nome, ligado in (("antes", False), ("depois", True)):
            modulo.LEXICO_POR_LINGUA = ligado
            registro[nome] = ler_pagina(caminho, folha, dpi=DPI, motor="fusao", lingua=lingua_do_livro, reconhecedor=reconhecedor).texto()
        with saida.open("a", encoding="utf-8", newline="\n") as fluxo:
            fluxo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    print("fim")


def resumir_fusao(entrada: Path) -> dict:
    import banco

    linhas = _ja_lidas(entrada)
    por_variante: dict[str, Counter] = {"antes": Counter(), "depois": Counter()}
    trocas: Counter = Counter()
    iguais = 0
    for r in linhas:
        iguais += r["antes"] == r["depois"]
        for nome in por_variante:
            placar = banco.pontuar(r["ref"], r[nome], normalizacao="tip", lingua=r["lingua"][:2]) if False else banco.placar(r["ref"], r[nome], "tip")
            por_variante[nome]["erros"] += placar["prosa"]["erros"]
            por_variante[nome]["caracteres"] += placar["prosa"]["n"]
    return {
        "folhas": len(linhas),
        "folhas_com_texto_igual": iguais,
        "cer_de_prosa_tip": {k: round(v["erros"] / max(1, v["caracteres"]), 5) for k, v in por_variante.items()},
        "trocas": trocas.most_common(0),
    }


def resumir(saida: Path, entrada: Path, args: argparse.Namespace) -> None:
    from chess_diagram_ocr.text import lingua

    linhas = _ja_lidas(entrada)
    livros = []
    for r in linhas:
        glifo_ = lingua.LinguaDoLivro.de_json(r["glifo"])
        camada = lingua.LinguaDoLivro.de_json(r["camada"])
        combinada = lingua.detectar_em(glifo_, camada)
        livros.append(
            {
                "livro": r["livro"],
                "declarada": r["declarada"],
                "folhas_abertas": r["folhas_abertas"],
                "decidiu_em": r["decidiu_em"],
                "glifo": {"detectada": glifo_.detectada, "folhas": len(glifo_.folhas), **glifo_.contagem.para_json()},
                "camada": {"detectada": camada.detectada, "folhas": len(camada.folhas), **camada.contagem.para_json()},
                "produto": combinada,
            }
        )
    acertos = {
        nome: sum(1 for livro in livros if chave(livro) == livro["declarada"])
        for nome, chave in (
            ("glifo", lambda x: x["glifo"]["detectada"]),
            ("camada", lambda x: x["camada"]["detectada"]),
            ("produto", lambda x: x["produto"]),
        )
    }
    relatorio = {
        "item": "S-723 e S-728 · a língua do livro e o léxico por língua",
        "medido_em": time.strftime("%Y-%m-%d"),
        "conjunto": "PDF/ deduplicado: uma cópia de cada livro, língua declarada à mão em linguas_declaradas.json",
        "folhas": f"as primeiras {FOLHAS} folhas com texto de cada livro, abrindo no máximo {TENTATIVAS}",
        "perfil_sha": lingua.sha_do_perfil(),
        "livros_medidos": len(livros),
        "acertos": acertos,
        "por_lingua_declarada": dict(Counter(livro["declarada"] for livro in livros)),
        "erros": [
            {"livro": x["livro"], "declarada": x["declarada"], "produto": x["produto"], "glifo": x["glifo"]["detectada"], "camada": x["camada"]["detectada"]}
            for x in livros
            if x["produto"] != x["declarada"]
        ],
        "livros": livros,
    }
    if args.fusao:
        relatorio["fusao_no_ouro_dev"] = resumir_fusao(Path(args.fusao))
    if args.glifo_folhas:
        relatorio["glifo_no_ouro_dev"] = {"folhas": args.glifo_folhas, "iguais_a_base": args.glifo_iguais, "base": args.base}
    saida.write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(acertos, "de", len(livros))
    for erro in relatorio["erros"]:
        print(erro)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comando", choices=("glifo", "comparar", "deteccao", "fusao", "resumir"))
    parser.add_argument("arquivos", nargs="+", type=Path)
    parser.add_argument("--orcamento", type=float, default=150.0)
    parser.add_argument("--fusao")
    parser.add_argument("--glifo-iguais", type=int, default=0)
    parser.add_argument("--glifo-folhas", type=int, default=0)
    parser.add_argument("--base", default="")
    args = parser.parse_args()
    if args.comando == "glifo":
        glifo(args.arquivos[0])
    elif args.comando == "comparar":
        comparar(args.arquivos[0], args.arquivos[1])
    elif args.comando == "deteccao":
        deteccao(args.arquivos[0], args.orcamento)
    elif args.comando == "fusao":
        fusao(args.arquivos[0], args.orcamento)
    else:
        resumir(args.arquivos[0], args.arquivos[1], args)


if __name__ == "__main__":
    main()
