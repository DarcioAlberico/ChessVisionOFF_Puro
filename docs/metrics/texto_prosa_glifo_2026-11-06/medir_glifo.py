"""Mede a Fase 103 (S-730 a S-735): o glifo com cada conserto ligado sozinho, e todos, no ouro-dev.

A régua é a de `texto_prosa_2026-10-30/banco.py`; o ouro-dev são os 5 livros aprovados na auditoria da S-702
(`assets/texto_prosa/ouro.json`), 27 folhas. Só o motor `glifo`: o que muda aqui é o glifo, e nenhuma variante
chama o Tesseract. As variantes leem a mesma folha no mesmo processo, trocando as constantes, depois de uma
leitura de aquecimento.

Uso (com o `.venv` do projeto, `PYTHONPATH=<arvore>/src` e `CVOFF_RAIZ` no checkout com `PDF/`):

  medir_glifo.py rodar <saida.jsonl> [--livro TRECHO]     texto de livro comercial: fora do repositório
  medir_glifo.py compilar <saida.json> <entrada.jsonl>... números e identidades, e nada de texto

`hoje` é tudo desligado, e `tudo` é o padrão: a comparação pareada é sempre contra `hoje`.

**O IC95 depende da ordem dos livros.** O bootstrap de dois níveis de `resumo.py` agrupa pela primeira aparição
e sorteia com semente fixa, então a mesma folha em outra ordem dá outro intervalo, com o ponto igual. `compilar`
ordena as folhas sempre por `ORDEM_NO_IC` (Dvoretsky, Hertan, Minhas 60, 400 Quebra-cabeças, Seirawan), e o
relatório a grava. Comparar IC de relatórios só vale com a mesma ordem.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "texto_prosa_2026-10-30"))
sys.stdout.reconfigure(encoding="utf-8")

import banco  # noqa: E402
import resumo  # noqa: E402

RAIZ = Path(os.environ.get("CVOFF_RAIZ") or AQUI.parents[2])
DPI = 220
ITENS = {
    "S-730": ["traco_vertical.LIGADO"],
    "S-731": ["caixa_alta.XH_COERENTE", "caixa_alta.PALAVRA_COERENTE", "caixa_alta.P_PELA_DESCIDA"],
    "S-732": ["fronteira.LIGADO", "fronteira.JUNTAR_PARTIDAS", "colados.POR_LEXICO"],
    "S-733": ["ligadura.LIGADO"],
    "S-734": ["marca_fina.ASPAS_PELA_GEOMETRIA"],
    "S-735": ["caixa_alta.CEDILHA_PELA_DESCIDA", "caixa_alta.SEGUNDO_CORTE", "acento.LIGADO"],
}
TODAS = [c for lista in ITENS.values() for c in lista]
LIVROS = {
    "603581c988ea2bd6": ("Dvoretsky - Dvoretsky's Endgame Manual (2025).pdf", "eng", "Dvoretsky"),
    "18d93bd07b7a826c": ("📚Hertan Charles. Forcing Chess Moves.pdf", "eng", "Hertan"),
    "69343a5746264fae": ("Xadrez Vitorioso - Finais - Yasser Seirawan.pdf", "por", "Seirawan"),
    "a728e2c7e968913c": ("Minhas 60 partidas memoráveis Bobby Fischer pt-br algébrico.pdf", "por", "Minhas 60"),
    "7a548a47f20f5f1f": ("400 Quebra-cabeças de Estratégia de Xadrez.pdf", "por", "400 Quebra-cabeças"),
}
ROTULO = {nome: rotulo for nome, _, rotulo in LIVROS.values()}
ORDEM_NO_IC = ("Dvoretsky", "Hertan", "Minhas 60", "400 Quebra-cabeças", "Seirawan")
ROTULO_ANTIGO = {"Melhores Finais de Capablanca - Irving Chernev pt-br - Copia.pdf": "Capablanca (reprovado)",
                 "📚Chess Evolution 2013 №045-096.pdf": "Chess Evolution (reprovado)"}


def _folhas_do_dev() -> list[tuple[str, str, str, list[int]]]:
    """(identidade, arquivo, língua, folhas em base 1), lidos do manifesto: só o split `dev`."""
    ouro = json.loads((AQUI.parents[2] / "assets" / "texto_prosa" / "ouro.json").read_text(encoding="utf-8"))
    saida = []
    for identidade, (arquivo, lingua, _) in LIVROS.items():
        assert any(x["identidade"] == identidade and x["split"] == "dev" for x in ouro["livros"]), identidade
        folhas = [f["folha"] for f in ouro["folhas"] if f["identidade"] == identidade and f["split"] == "dev"]
        saida.append((identidade, arquivo, lingua, folhas))
    return saida


def _com(desligadas: list[str]):
    antes = []
    for chave in desligadas:
        mod, nome = chave.rsplit(".", 1)
        m = importlib.import_module("chess_diagram_ocr.text." + mod)
        antes.append((m, nome, getattr(m, nome)))
        setattr(m, nome, False)
    return antes


def rodar(saida: str, trecho: str) -> None:
    from chess_diagram_ocr.pdf_io import render_pdf_page
    from chess_diagram_ocr.text.leitor import ler_pagina
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

    variantes: dict[str, list[str]] = {"hoje": TODAS, "tudo": []}
    for item, constantes in ITENS.items():
        variantes[item] = [c for c in TODAS if c not in constantes]
    rec = build_glyph_recognizer()
    aquecido = False
    # **Retoma**: uma folha já gravada não se lê de novo, e a saída pode ser costurada em pedaços.
    feitas = set()
    if os.path.exists(saida):
        feitas = {(r["livro"], r["folha"]) for r in map(json.loads, open(saida, encoding="utf-8"))}
    with open(saida, "a", encoding="utf-8") as f:
        for identidade, arquivo, lingua, folhas in _folhas_do_dev():
            if trecho and trecho not in arquivo:
                continue
            pdf = str(RAIZ / "PDF" / arquivo)
            for folha in folhas:
                if (arquivo, folha) in feitas:
                    continue
                img = render_pdf_page(pdf, folha - 1, DPI)
                if not aquecido:
                    ler_pagina(pdf, folha - 1, motor="glifo", reconhecedor=rec, imagem_rgb=img, dpi=DPI)
                    aquecido = True
                camada = ler_pagina(pdf, folha - 1, motor="camada", imagem_rgb=img, dpi=DPI)
                hip = {}
                diagramas = [d.bbox for d in camada.diagramas]
                for nome, desligadas in variantes.items():
                    antes = _com(desligadas)
                    lida = ler_pagina(pdf, folha - 1, motor="glifo", reconhecedor=rec, imagem_rgb=img, dpi=DPI)
                    for m, n, v in antes:
                        setattr(m, n, v)
                    hip[nome] = banco.texto_de([ln.texto for ln in banco.linhas_da_pagina(lida)])
                    if nome == "hoje":
                        diagramas += [d.bbox for d in lida.diagramas]
                linhas = [x for x in banco.linhas_da_pagina(camada) if not banco.cruza_diagrama(x.bbox, diagramas)]
                ref = banco.texto_de([x.texto for x in linhas])
                reg = {"identidade": identidade, "livro": arquivo, "lang": lingua, "folha": folha, "ref": ref, "hip": hip, "placar": {}}
                for tip in (True, False):
                    r = banco.normalizar(ref, tipografia=tip, lang=lingua)
                    for nome, texto in hip.items():
                        p = banco.pontuar(r, banco.normalizar(texto, tipografia=tip, lang=lingua))
                        reg["placar"][f"{nome}|{'tip' if tip else 'cru'}"] = banco.placar_dict(p)
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                f.flush()
                print(ROTULO[arquivo], folha, flush=True)


def _taxa(regs, m, tip, classe):
    pl = [r["placar"][f"{m}|{tip}"] for r in regs]
    e = [p["erros"][classe] for p in pl]
    t = [p["total"][classe] for p in pl]
    c, lo, hi = resumo.ic95(e, t, [r["livro"] for r in regs])
    return {"cer": round(c, 5), "ic95": [round(lo, 5), round(hi, 5)], "erros": sum(e), "total": sum(t)}


def _familias(regs, m, tip):
    fam: Counter = Counter()
    por: dict = defaultdict(Counter)
    for r in regs:
        for k, v in r["placar"][f"{m}|{tip}"]["trocas"].items():
            ref, _, hip = k.partition(" -> ")
            if re.search(r"[A-Za-zÀ-ÿ]", ref) is None:
                continue
            nome = resumo.familia(ref, hip)
            fam[nome] += v
            por[nome][ROTULO.get(r["livro"], ROTULO_ANTIGO.get(r["livro"], r["livro"]))] += v
    return {k: {"palavras": v, "por_livro": dict(por[k])} for k, v in fam.most_common()}


def _par(regs, m, tip, classe):
    a = [r["placar"][f"{m}|{tip}"] for r in regs]
    b = [r["placar"][f"hoje|{tip}"] for r in regs]
    d, lo, hi = resumo.diferenca_pareada(
        [p["erros"][classe] for p in a], [p["total"][classe] for p in a],
        [p["erros"][classe] for p in b], [p["total"][classe] for p in b], [r["livro"] for r in regs],
    )
    return {"pp": round(100 * d, 3), "ic95": [round(100 * lo, 3), round(100 * hi, 3)],
            "melhores": sum(x["erros"][classe] < y["erros"][classe] for x, y in zip(a, b, strict=True)),
            "piores": sum(x["erros"][classe] > y["erros"][classe] for x, y in zip(a, b, strict=True))}


def _figurina(regs, m):
    f = {k: sum(r["placar"][f"{m}|tip"]["fig"][k] for r in regs) for k in ("ref", "hip", "tp")}
    return {"revocacao": round(f["tp"] / max(1, f["ref"]), 4), "precisao": round(f["tp"] / max(1, f["hip"]), 4), **f}


def _wer(regs, m, tip):
    w = {k: sum(r["placar"][f"{m}|{tip}"]["wer"][k] for r in regs) for k in "sdin"}
    return round((w["s"] + w["d"] + w["i"]) / max(1, w["n"]), 5)


def _bloco(regs, motores):
    saida = {"folhas": len(regs), "livros": sorted({ROTULO.get(r["livro"], ROTULO_ANTIGO.get(r["livro"], r["livro"])) for r in regs}), "motores": {}}
    for m in motores:
        saida["motores"][m] = {
            "prosa_tip": _taxa(regs, m, "tip", "prosa"), "prosa_cru": _taxa(regs, m, "cru", "prosa"),
            "wer_tip": _wer(regs, m, "tip"), "wer_cru": _wer(regs, m, "cru"),
            "notacao_tip": _taxa(regs, m, "tip", "notacao"), "espaco_tip": _taxa(regs, m, "tip", "espaco"),
            "insercoes_tip": sum(r["placar"][f"{m}|tip"]["insercoes"] for r in regs),
            "figurina": _figurina(regs, m),
            "familias_tip": _familias(regs, m, "tip"), "familias_cru": _familias(regs, m, "cru"),
        }
        if m != "hoje":
            saida["motores"][m]["pareado_contra_hoje"] = {
                "prosa_tip": _par(regs, m, "tip", "prosa"), "prosa_cru": _par(regs, m, "cru", "prosa"),
                "g1b_notacao_tip": _par(regs, m, "tip", "notacao"),
            }
    return saida


def _por_livro(regs, motores):
    grupos = defaultdict(list)
    for r in regs:
        grupos[ROTULO.get(r["livro"], r["livro"])].append(r)
    return {k: {m: _taxa(v, m, "tip", "prosa") | {"wer": _wer(v, m, "tip")} for m in motores} for k, v in grupos.items()}


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def compilar(saida: str, entradas: list[str], extras: str) -> None:
    regs = [json.loads(x) for e in entradas for x in open(e, encoding="utf-8")]
    regs.sort(key=lambda r: (ORDEM_NO_IC.index(ROTULO[r["livro"]]), r["folha"]))
    motores = list(regs[0]["hip"].keys())
    arvore = AQUI.parents[2]
    git = lambda *a: subprocess.run(["git", "-C", str(arvore), *a], capture_output=True, text=True).stdout.strip()  # noqa: E731
    rel = {
        "pergunta": "Quanto cada conserto da Fase 103 tira de cada família de erro do glifo, sem piorar a notação?",
        "split": "dev contaminado: 5 livros aprovados na auditoria da S-702. Nenhum número aqui decide portão; o G103 abre o teste e é rodado depois.",
        "reprovados_fora": "Chess Evolution e Capablanca (citados nas Saídas do roadmap) foram reprovados na auditoria da S-702 e não entram no ouro-dev; ficam em `reprovados_na_auditoria`, só como conferência.",
        "commit_medido": git("rev-parse", "HEAD"),
        "src_sujo": bool(git("status", "--porcelain", "--", "src")),
        "modelo_sha256": _sha(RAIZ / "models" / "char_classifier.pt"),
        "dpi": DPI,
        "ordem_dos_livros_no_ic": list(ORDEM_NO_IC),
        "regua": "texto_prosa_2026-10-30/banco.py; sha256 " + _sha(AQUI.parent / "texto_prosa_2026-10-30" / "banco.py")[:16],
        "motores": {"hoje": "tudo desligado: reproduz o texto de a2937260 byte a byte, folha a folha", "tudo": "o padrão", **{k: "só as constantes deste item: " + ", ".join(v) for k, v in ITENS.items()}},
        "tempo": "não publicado: três trilhas na máquina; G4 se mede depois com a máquina parada",
        "ouro_dev": _bloco(regs, motores),
        "por_livro": _por_livro(regs, motores),
    }
    if extras:
        rel.update(json.loads(Path(extras).read_text(encoding="utf-8")))
    Path(saida).write_bytes((json.dumps(rel, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("rodar")
    a.add_argument("saida")
    a.add_argument("--livro", default="")
    c = sub.add_parser("compilar")
    c.add_argument("saida")
    c.add_argument("entradas", nargs="+")
    c.add_argument("--extras", default="", help="JSON com os blocos medidos à parte")
    args = ap.parse_args()
    if args.cmd == "rodar":
        rodar(args.saida, args.livro)
    else:
        compilar(args.saida, args.entradas, args.extras)


if __name__ == "__main__":
    main()
