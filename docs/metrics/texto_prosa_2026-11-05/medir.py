"""Mede a primeira entrega da prosa (S-710, S-715 a S-718, S-720) com a régua de 2026-10-30.

A régua é a mesma, importada de `texto_prosa_2026-10-30/banco.py`: referência pela montagem da camada,
prosa separada da notação token a token, IC95 de dois níveis. Os motores agora rodam **dentro** do
`ler_pagina`, e não por fora dele como os protótipos.

Uso (com o `.venv` do projeto, `PYTHONPATH=<arvore>/src` e `CVOFF_RAIZ` no checkout com `PDF/`):

  medir.py folhas <relatorio.json> <conjunto> <saida.jsonl>   lê glifo, camada na prosa e fusão, folha a folha
  medir.py perdidas <saida.jsonl>                             as sete folhas perdidas, pela guarda e pela reserva
  medir.py varrer <saida.jsonl> [--por-livro N]               a guarda em todos os livros, por tipo de folha
  medir.py caminho_da_camada <saida.jsonl>                    a folha acusada em camada na prosa, com a reserva
  medir.py resumir <saida.json> <entrada.jsonl>...            compila o relatório, sem texto de livro nenhum

A saída dos três primeiros **tem texto de livro comercial**: mande-a para fora do repositório. Só o
`resumir` escreve dentro dele, e o que ele escreve são números e identidades.
"""
from __future__ import annotations

import argparse
import difflib
import glob
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "texto_prosa_2026-10-30"))
sys.stdout.reconfigure(encoding="utf-8")

import banco  # noqa: E402
import resumo  # noqa: E402

RAIZ = Path(os.environ.get("CVOFF_RAIZ") or Path(__file__).resolve().parents[3])
MODELO = RAIZ / "models" / "char_classifier.pt"
DPI = 220


def _leitura():
    from chess_diagram_ocr.text.leitor import ler_pagina
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

    return ler_pagina, build_glyph_recognizer(str(MODELO))


def _marcadas(pagina) -> tuple[list[str], list[str]]:
    """(os tokens da folha, os marcados), na ordem do texto. A marca vem por intervalo em cada linha."""
    tokens, marcados = [], []
    for linha in banco.linhas_da_pagina(pagina):
        posicao = 0
        for token in linha.texto.split():
            inicio = linha.texto.index(token, posicao)
            posicao = inicio + len(token)
            tokens.append(token)
            if any(a < posicao and inicio < b for a, b in getattr(linha, "revisar_em", ())):
                marcados.append(token)
    return tokens, marcados


def _erradas(ref: str, tokens: list[str]) -> set[int]:
    """Os índices de `tokens` que não casam com a referência. Só prosa conta como erro de palavra (G5)."""
    casador = difflib.SequenceMatcher(None, ref.split(), tokens, autojunk=False)
    certas: set[int] = set()
    for bloco in casador.get_matching_blocks():
        certas.update(range(bloco.b, bloco.b + bloco.size))
    return {i for i, t in enumerate(tokens) if i not in certas and banco.classe_do_token(t) == "prosa"}


def _captura(ref: str, pagina) -> dict:
    tokens, _ = _marcadas(pagina)
    erradas = _erradas(ref, tokens)
    indice_marcados: set[int] = set()
    posicao = 0
    for linha in banco.linhas_da_pagina(pagina):
        p = 0
        for token in linha.texto.split():
            inicio = linha.texto.index(token, p)
            p = inicio + len(token)
            if any(a < p and inicio < b for a, b in getattr(linha, "revisar_em", ())):
                indice_marcados.add(posicao)
            posicao += 1
    return {"palavras": len(tokens), "marcadas": len(indice_marcados), "erradas": len(erradas),
            "capturadas": len(erradas & indice_marcados)}


def _preservacao(glifo: list[str], fundida: list[str]) -> tuple[int, int]:
    """Quantos tokens com figurina do glifo chegam idênticos ao texto fundido (G1, sem referência)."""
    figurinas = [t for ln in glifo for t in ln.split() if re.search(r"[♔-♟]", t)]
    restam = Counter(t for ln in fundida for t in ln.split())
    ok = 0
    for token in figurinas:
        if restam[token] > 0:
            restam[token] -= 1
            ok += 1
    return ok, len(figurinas)


def folhas(relatorio: str, conjunto: str, saida: str) -> None:
    from chess_diagram_ocr.pdf_io import render_pdf_page
    from chess_diagram_ocr.text import leitor_de_linha, tesseract

    ler, rec = _leitura()
    c = json.load(open(relatorio, encoding="utf-8"))["conjuntos"][conjunto]
    leitor = leitor_de_linha.LeitorTesseract()
    aquecido = False
    with open(saida, "w", encoding="utf-8") as f:
        for livro, info in c["por_livro"].items():
            pdf = str(RAIZ / "PDF" / livro)
            lang = info["lingua"]
            for folha in info["folhas"]:
                idx = folha - 1
                img = render_pdf_page(pdf, idx, DPI)
                if not aquecido:
                    ler(pdf, idx, motor="glifo", reconhecedor=rec, imagem_rgb=img, dpi=DPI, reserva=False)
                    aquecido = True
                ref_pag = ler(pdf, idx, motor="camada", imagem_rgb=img, dpi=DPI)
                t0 = time.perf_counter()
                gl = ler(pdf, idx, motor="glifo", reconhecedor=rec, imagem_rgb=img, dpi=DPI, reserva=False)
                t1 = time.perf_counter()
                cp = ler(pdf, idx, motor="camada_prosa", reconhecedor=rec, imagem_rgb=img, dpi=DPI, reserva=False)
                t2 = time.perf_counter()
                fu = ler(pdf, idx, motor="fusao", reconhecedor=rec, imagem_rgb=img, dpi=DPI, lingua=lang, reserva=False)
                t3 = time.perf_counter()
                diagramas = [d.bbox for d in ref_pag.diagramas] + [d.bbox for d in gl.diagramas]
                ref_l = [ln for ln in banco.linhas_da_pagina(ref_pag) if not banco.cruza_diagrama(ln.bbox, diagramas)]
                ref = banco.texto_de([ln.texto for ln in ref_l])
                gl_l = banco.linhas_da_pagina(gl)
                recortes = [banco.recortar(img, ln.bbox, DPI) for ln in gl_l]
                t4 = time.perf_counter()
                por_processo = [banco.tess_linha(r, lang, 1.0, dpi_declarado=DPI)[0] for r in recortes]
                t5 = time.perf_counter()
                leitura = leitor.ler_linhas(recortes, lingua=lang, dpi=DPI)
                t6 = time.perf_counter()
                por_folha = ["" if li is None else li.texto for li in leitura.linhas]
                hip = {
                    "glifo": banco.texto_de([ln.texto for ln in gl_l]),
                    "camada_prosa": banco.texto_de([ln.texto for ln in banco.linhas_da_pagina(cp)]),
                    "fusao": banco.texto_de([ln.texto for ln in banco.linhas_da_pagina(fu)]),
                    "tess": banco.texto_de(por_folha),
                }
                placar = {}
                for tip in (True, False):
                    r = banco.normalizar(ref, tipografia=tip, lang=lang)
                    for k, v in hip.items():
                        p = banco.pontuar(r, banco.normalizar(v, tipografia=tip, lang=lang))
                        placar[f"{k}|{'tip' if tip else 'cru'}"] = banco.placar_dict(p)
                reg = {
                    "conjunto": conjunto, "livro": livro, "lang": lang, "pagina": idx, "ref": ref, "hip": hip,
                    "placar": placar,
                    "tempo": {"glifo": t1 - t0, "camada_prosa": t2 - t1, "fusao": t3 - t2,
                              "tess_por_processo": t5 - t4, "tess_por_folha": t6 - t5},
                    "executor": {"linhas": len(recortes), "diferentes": sum(a != b for a, b in zip(por_processo, por_folha, strict=True))},
                    "preservacao": {
                        "camada_prosa": _preservacao([ln.texto for ln in gl_l], [ln.texto for ln in banco.linhas_da_pagina(cp)]),
                        "fusao": _preservacao([ln.texto for ln in gl_l], [ln.texto for ln in banco.linhas_da_pagina(fu)]),
                    },
                    "captura": {"fusao": _captura(ref, fu), "camada_prosa": _captura(ref, cp)},
                    "avisos": {"glifo": [a.codigo for a in gl.avisos], "camada_prosa": [a.codigo for a in cp.avisos],
                               "fusao": [a.codigo for a in fu.avisos]},
                }
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                f.flush()
                print(livro[:28], folha, *(f"{k}={placar[k + '|tip']['erros']['prosa'] / max(1, placar[k + '|tip']['total']['prosa']):.4f}" for k in hip),
                      f"exec_dif={reg['executor']['diferentes']}", flush=True)
    assert tesseract.achar_motor().disponivel


PERDIDAS = [("*Evolution 2013*", 902, "eng"), ("*Evolution 2013*", 1209, "eng"), ("Kmoch*", 30, "nld"), ("Kmoch*", 68, "nld"),
            ("Kmoch*", 105, "nld"), ("*Evolution 2013*", 813, "eng"), ("*Evolution 2013*", 1395, "eng")]


def perdidas(saida: str) -> None:
    """As cinco folhas de 2026-10-30 e as duas que o crítico achou. Devolve o CER da reserva e as linhas achadas."""
    from chess_diagram_ocr.pdf_io import render_pdf_page

    ler, rec = _leitura()
    with open(saida, "w", encoding="utf-8") as f:
        for padrao, idx, lang in PERDIDAS:
            pdf = glob.glob(str(RAIZ / "PDF" / padrao))[0]
            img = render_pdf_page(pdf, idx, DPI)
            ref_pag = ler(pdf, idx, motor="camada", imagem_rgb=img, dpi=DPI)
            sem = ler(pdf, idx, motor="glifo", reconhecedor=rec, imagem_rgb=img, dpi=DPI, reserva=False)
            com = ler(pdf, idx, motor="glifo", reconhecedor=rec, imagem_rgb=img, dpi=DPI, lingua=lang, reserva=True)
            ref_l = banco.linhas_da_pagina(ref_pag)
            ref = banco.texto_de([ln.texto for ln in ref_l])
            r = banco.normalizar(ref, tipografia=True, lang=lang)
            p = banco.pontuar(r, banco.normalizar(com.texto(com_marcas=False), tipografia=True, lang=lang))
            reg = {"livro": os.path.basename(pdf), "pagina": idx, "lang": lang,
                   "avisos_sem_reserva": [(a.codigo, a.dado) for a in sem.avisos],
                   "avisos_com_reserva": [a.codigo for a in com.avisos],
                   "cer_prosa": p.erros["prosa"] / max(1, p.total["prosa"]),
                   "linhas_camada": len(ref_l), "linhas_reserva": len(banco.linhas_da_pagina(com)),
                   "linhas_sem_reserva": len(banco.linhas_da_pagina(sem))}
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
            f.flush()
            print(reg["livro"][:26], idx + 1, reg["avisos_com_reserva"], f"cer={reg['cer_prosa']:.3f}",
                  f"linhas {reg['linhas_sem_reserva']}->{reg['linhas_reserva']} (camada {reg['linhas_camada']})", flush=True)


def caminho_da_camada(saida: str) -> None:
    """O caminho `camada_na_folha` com a reserva, forçado: depois da S-711, quase nenhuma folha real chega nele.

    O glifo é trocado por uma linha só, e o resto roda de verdade, com o Tesseract. O que se afirma é que a
    notação da camada sai intacta e que o `afer` da ligadura vira `after`.
    """
    from unittest import mock

    import fitz

    from chess_diagram_ocr.pdf_io import render_pdf_page
    from chess_diagram_ocr.text import boxes, camada_prosa, leitor

    ler, rec = _leitura()
    cru = leitor._Cru(texto="h", caixa=boxes.Caixa(0, 0, 40, 40), confianca=0.1, procedencia="glifo")  # noqa: SLF001
    with open(saida, "w", encoding="utf-8") as f:
        for padrao in ("*Evolution 2013*", "*Evolution 2014*"):
            pdf = glob.glob(str(RAIZ / "PDF" / padrao))[0]
            with fitz.open(pdf) as doc:
                n = doc.page_count
            for i in range(int(n * 0.1), int(n * 0.9), int(n * 0.8 / 13)):
                img = render_pdf_page(pdf, i, DPI)
                with mock.patch.object(leitor, "linhas_do_glifo", return_value=([cru], [])):
                    pag = ler(pdf, i, motor="camada_prosa", reconhecedor=rec, imagem_rgb=img, dpi=DPI, reserva=True)
                # As palavras da camada já partidas no vão: contra a montagem crua, o que a partição separou
                # contaria como lance perdido.
                with fitz.open(pdf) as doc:
                    t_base = [p.texto for p in camada_prosa.palavras_da_folha(doc[i])]
                t_pag = pag.texto(com_marcas=False).split()
                nota = [x for x in t_base if banco.classe_do_token(x) == "notacao"]
                restam = Counter(t_pag)
                ok = sum(1 for x in nota if restam[x] > 0 and not restam.subtract([x]))
                reg = {"caminho": True, "livro": os.path.basename(pdf), "pagina": i, "avisos": [a.codigo for a in pag.avisos],
                       "notacao": [ok, len(nota)], "afer": [t_base.count("afer"), t_pag.count("afer")],
                       "palavras": [len(t_base), len(t_pag)]}
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                f.flush()
                print(reg["livro"][:24], i + 1, reg["avisos"], reg["notacao"], reg["afer"], reg["palavras"], flush=True)


def _tipo(indice: int, n: int, camada: str, diagramas: int, componentes: int, linhas: list[str]) -> str:
    """O tipo da folha, pelo que ela tem, sem olhar o texto lido: é contra ele que a guarda se mede.

    **O só-diagrama vem pela camada, e não pela tinta.** A primeira versão perguntava `componentes < 40`, e as
    folhas da *Polgar*, com seis diagramas e as coordenadas em volta, saíam `prosa`: a tabela por tipo escondia
    justamente o falso alarme que ela existe para mostrar.
    """
    if componentes < 5:
        return "branco"
    if indice < 4 and componentes < 400:
        return "capa"
    if diagramas:
        letras = sum(len(t) for t in camada.split() if banco.classe_do_token(t) == "prosa")
        if letras < 200 and (camada.strip() or componentes < 300):
            return "so_diagrama"
    fim_em_numero = sum(bool(re.search(r"\d\s*$", ln)) for ln in camada.splitlines())
    if camada and len(camada.splitlines()) >= 12 and fim_em_numero > 0.7 * len(camada.splitlines()):
        return "indice"
    if not camada.strip():
        return "sem_camada"
    tokens = camada.split()
    prosa = sum(len(t) for t in tokens if banco.classe_do_token(t) == "prosa")
    total = max(1, sum(len(t) for t in tokens))
    return "prosa" if prosa / total >= 0.55 else ("misto" if prosa / total >= 0.2 else "so_notacao")


def varrer(saida: str, por_livro: int, padrao: str = "*.pdf") -> None:
    """A guarda em folhas igualmente espaçadas de cada livro do acervo, sem a reserva."""
    import fitz

    from chess_diagram_ocr.pdf_io import render_pdf_page
    from chess_diagram_ocr.text import guarda_de_leitura

    ler, rec = _leitura()
    vistos = set()
    with open(saida, "w", encoding="utf-8") as f:
        for pdf in sorted(glob.glob(str(RAIZ / "PDF" / padrao))):
            chave = hashlib.sha256(Path(pdf).read_bytes()[:1 << 20]).hexdigest()[:16]
            if chave in vistos:
                continue
            vistos.add(chave)
            with fitz.open(pdf) as doc:
                n = doc.page_count
                textos = {}
                indices = sorted({int(i * (n - 1) / max(1, por_livro - 1)) for i in range(por_livro)})
                for i in indices:
                    textos[i] = doc[i].get_text()
            for i in indices:
                try:
                    img = render_pdf_page(pdf, i, DPI)
                    t0 = time.perf_counter()
                    pag = ler(pdf, i, motor="glifo", reconhecedor=rec, imagem_rgb=img, dpi=DPI, reserva=False)
                    tempo = time.perf_counter() - t0
                except Exception as exc:  # noqa: BLE001 - uma folha ruim não derruba a varredura
                    print("falhou", os.path.basename(pdf)[:30], i, exc, flush=True)
                    continue
                s = DPI / 72
                linhas = banco.linhas_da_pagina(pag)
                medida = guarda_de_leitura.medir(
                    img, [[v * s for v in d.bbox] for d in pag.diagramas],
                    lidos=sum(len("".join(ln.texto.split())) for ln in linhas), linhas_lidas=len(linhas), dpi=DPI,
                )
                reg = {"livro": chave, "n": n, "pagina": i, "tipo": _tipo(i, n, textos[i], len(pag.diagramas), medida.componentes, [ln.texto for ln in linhas]),
                       "densidade": medida.densidade, "componentes": medida.componentes, "lidos": medida.lidos,
                       "linhas": medida.linhas_lidas, "estimadas": medida.linhas_estimadas, "camada": len("".join(textos[i].split())),
                       "avisos": [a.codigo for a in pag.avisos], "segundos": tempo, "nome": os.path.basename(pdf)}
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                f.flush()
            print("livro", os.path.basename(pdf)[:40], n, flush=True)


def _taxa(regs: list[dict], motor: str, campo: str = "prosa", tip: str = "tip") -> dict:
    erros = [r["placar"][f"{motor}|{tip}"]["erros"].get(campo, 0) for r in regs]
    totais = [r["placar"][f"{motor}|{tip}"]["total"].get(campo, 0) for r in regs]
    livros = [r["livro"] for r in regs]
    ponto, baixo, alto = resumo.ic95(erros, totais, livros)
    return {"cer": round(float(ponto), 5), "ic95": [round(float(baixo), 5), round(float(alto), 5)]}


def _wer(regs: list[dict], motor: str) -> float:
    w = [r["placar"][f"{motor}|tip"]["wer"] for r in regs]
    return round(sum(x["s"] + x["d"] + x["i"] for x in w) / max(1, sum(x["n"] for x in w)), 5)


def _par(regs: list[dict], a: str, b: str, campo: str = "prosa") -> dict:
    d, baixo, alto = resumo.diferenca_pareada(
        *[[r["placar"][f"{m}|tip"][k].get(campo, 0) for r in regs] for m in (a, b) for k in ("erros", "total")],
        [r["livro"] for r in regs],
    )
    return {"delta_pp": round(float(d) * 100, 3), "ic95_pp": [round(float(baixo) * 100, 3), round(float(alto) * 100, 3)]}


def _figurina(regs: list[dict], motor: str) -> dict:
    f = [r["placar"][f"{motor}|tip"]["fig"] for r in regs]
    tp, ref, hip = sum(x["tp"] for x in f), sum(x["ref"] for x in f), sum(x["hip"] for x in f)
    return {"revocacao": round(tp / max(1, ref), 4), "precisao": round(tp / max(1, hip), 4)}


def _p95(valores) -> float:
    ordenados = sorted(valores)
    return round(ordenados[min(len(ordenados) - 1, int(len(ordenados) * 0.95))], 3) if ordenados else 0.0


def _bloco(regs: list[dict]) -> dict:
    motores = ("glifo", "camada_prosa", "fusao", "tess")
    fusao = [r["captura"]["fusao"] for r in regs]
    pres_cp = [r["preservacao"]["camada_prosa"] for r in regs]
    pres_fu = [r["preservacao"]["fusao"] for r in regs]
    return {
        "folhas": len(regs),
        "livros": len({r["livro"] for r in regs}),
        "prosa": {m: _taxa(regs, m) for m in motores},
        "notacao": {m: _taxa(regs, m, "notacao") for m in motores},
        "wer": {m: _wer(regs, m) for m in motores},
        "figurina": {m: _figurina(regs, m) for m in ("glifo", "camada_prosa", "fusao")},
        "pares": {
            "fusao-tess_prosa": _par(regs, "fusao", "tess"),
            "fusao-glifo_notacao": _par(regs, "fusao", "glifo", "notacao"),
            "camada_prosa-glifo_notacao": _par(regs, "camada_prosa", "glifo", "notacao"),
        },
        "preservacao_de_figurina": {
            "camada_prosa": round(sum(a for a, _ in pres_cp) / max(1, sum(b for _, b in pres_cp)), 4),
            "fusao": round(sum(a for a, _ in pres_fu) / max(1, sum(b for _, b in pres_fu)), 4),
        },
        "g5_provisoria_fusao": {
            "fracao_marcada": round(sum(c["marcadas"] for c in fusao) / max(1, sum(c["palavras"] for c in fusao)), 4),
            "captura": round(sum(c["capturadas"] for c in fusao) / max(1, sum(c["erradas"] for c in fusao)), 4),
            "palavras_erradas": sum(c["erradas"] for c in fusao),
        },
        "segundos_por_folha": {k: round(sum(r["tempo"][k] for r in regs) / max(1, len(regs)), 3) for k in regs[0]["tempo"]},
        "segundos_por_folha_p95": {k: _p95(r["tempo"][k] for r in regs) for k in regs[0]["tempo"]},
        "executor": {"linhas": sum(r["executor"]["linhas"] for r in regs), "diferentes_do_processo_por_linha": sum(r["executor"]["diferentes"] for r in regs)},
        "avisos": dict(Counter(a for r in regs for m in r["avisos"].values() for a in m)),
    }


def _reprovados() -> set[str]:
    """Os reprovados pela auditoria visual da S-702, pela TSV dela: o manifesto do ouro não é aberto aqui."""
    caminho = Path(__file__).resolve().parent.parent / "texto_ouro_2026-10-30" / "reprovados_auditoria.tsv"
    return {ln.split("\t")[0] for ln in caminho.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")}


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16] if caminho.is_file() else ""


def _procedencia(commit_medido: str = "") -> dict:
    """Com que código, modelo e Tesseract isto foi medido. Sem caminho absoluto: o relatório é público.

    `commit_medido` é o da árvore que **leu** as folhas: `resumir` costuma rodar depois, de outro commit, e
    gravar o de agora declararia um código que não mediu nada.
    """
    import subprocess

    from chess_diagram_ocr.text import tesseract

    raiz = Path(__file__).resolve().parents[3]
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, text=True).stdout.strip()

    motor = tesseract.achar_motor()
    tessdata = {
        lingua: _sha(motor.tessdata / f"{lingua}.traineddata") if motor.tessdata else "" for lingua in tesseract.LINGUAS
    }
    return {
        "commit": commit_medido or git("rev-parse", "HEAD"),
        "arvore_suja_em_src": bool(git("status", "--porcelain", "--", "src")),
        "modelo_sha256": _sha(MODELO),
        "tesseract": motor.versao,
        "tessdata_sha256": tessdata,
        "regua_sha256": _sha(Path(banco.__file__)),
        "nota": "tempos sob contenção: outras medições rodavam na máquina, e o G4 não se julga por eles",
    }


def resumir(saida: str, entradas: list[str], commit_medido: str = "", commit_medido_do_caminho: str = "") -> None:
    from chess_diagram_ocr.text.caderno import identidade_de

    reprovados = _reprovados()
    conjuntos: dict[str, list[dict]] = defaultdict(list)
    relatorio: dict = {
        "item": "S-710, S-715, S-716, S-717, S-718, S-720",
        "regua": "texto_prosa_2026-10-30/banco.py",
        "dpi": DPI,
        "medido_com": _procedencia(commit_medido),
    }
    for entrada in entradas:
        regs = [json.loads(ln) for ln in open(entrada, encoding="utf-8")]
        if not regs:
            continue
        if "caminho" in regs[0]:
            relatorio["caminho_da_camada_com_reserva"] = {
                "medido_em": commit_medido_do_caminho,
                "nota": "forçado: depois da S-711 nenhuma folha do ouro e da prata chega neste caminho",
                "folhas": len(regs),
                "tokens_de_notacao_da_camada": sum(r["notacao"][1] for r in regs),
                "intactos": sum(r["notacao"][0] for r in regs),
                "afer_na_camada": sum(r["afer"][0] for r in regs),
                "afer_na_saida": sum(r["afer"][1] for r in regs),
                "palavras_na_camada": sum(r["palavras"][0] for r in regs),
                "palavras_na_saida": sum(r["palavras"][1] for r in regs),
            }
        elif "tipo" in regs[0] and all("Chess Evolution" in r["nome"] for r in regs):
            por_livro: dict[str, list[dict]] = defaultdict(list)
            for r in regs:
                por_livro[r["nome"][:21].lstrip("📚")].append(r)
            relatorio["amostra_chess_evolution"] = {
                livro: {"folhas": len(v), "folha_nao_lida": sum("folha_nao_lida" in r["avisos"] for r in v)}
                for livro, v in sorted(por_livro.items())
            }
        elif "tipo" in regs[0]:
            por_tipo: dict[str, list[dict]] = defaultdict(list)
            for r in regs:
                por_tipo[r["tipo"]].append(r)
            relatorio["varredura_da_guarda"] = {
                "folhas": len(regs),
                "livros": len({r["livro"] for r in regs}),
                "por_tipo": {
                    t: {
                        "folhas": len(v),
                        "folha_nao_lida": sum("folha_nao_lida" in r["avisos"] for r in v),
                        "leitura_parcial": sum("leitura_parcial" in r["avisos"] for r in v),
                        "densidade_min": round(min(r["densidade"] for r in v), 3),
                        "densidade_p05": round(sorted(r["densidade"] for r in v)[len(v) // 20], 3),
                    }
                    for t, v in sorted(por_tipo.items())
                },
                "folhas_com_camada_abaixo_de_0_7": sum(r["densidade"] < 0.7 and r["camada"] >= 200 and not r["avisos"] for r in regs),
                "densidade_das_avisadas": sorted(round(r["densidade"], 3) for r in regs if "folha_nao_lida" in r["avisos"]),
                "segundos_por_folha_p95": _p95(r["segundos"] for r in regs),
            }
        elif "cer_prosa" in regs[0]:
            relatorio["folhas_perdidas"] = [
                {"livro": r["livro"][:12], "folha": r["pagina"] + 1, "densidade": (r["avisos_sem_reserva"] or [[None, None]])[0][1],
                 "avisos": r["avisos_com_reserva"], "cer_prosa_glifo": round(r["cer_prosa"], 4),
                 "linhas": {"lidas": r["linhas_reserva"], "camada": r["linhas_camada"]}}
                for r in regs
            ]
        else:
            for r in regs:
                conjuntos[r["conjunto"]].append(r)
    relatorio["conjuntos"] = {}
    for nome, regs in conjuntos.items():
        relatorio["conjuntos"][nome] = _bloco(regs)
        aprovados = [r for r in regs if identidade_de(RAIZ / "PDF" / r["livro"]) not in reprovados]
        if aprovados and len(aprovados) != len(regs):
            relatorio["conjuntos"][nome + "_aprovados_na_auditoria"] = _bloco(aprovados)
    Path(saida).write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="modo", required=True)
    a = sub.add_parser("folhas")
    a.add_argument("relatorio")
    a.add_argument("conjunto")
    a.add_argument("saida")
    a = sub.add_parser("perdidas")
    a.add_argument("saida")
    a = sub.add_parser("caminho_da_camada")
    a.add_argument("saida")
    a = sub.add_parser("varrer")
    a.add_argument("saida")
    a.add_argument("--por-livro", type=int, default=12)
    a.add_argument("--padrao", default="*.pdf", help="quais livros de PDF/, por glob")
    a = sub.add_parser("resumir")
    a.add_argument("saida")
    a.add_argument("entradas", nargs="+")
    a.add_argument("--commit", default="", help="o commit da árvore que leu as folhas")
    a.add_argument("--commit-do-caminho", default="", help="idem, para a medida do caminho da camada")
    args = ap.parse_args()
    if args.modo == "folhas":
        folhas(args.relatorio, args.conjunto, args.saida)
    elif args.modo == "perdidas":
        perdidas(args.saida)
    elif args.modo == "caminho_da_camada":
        caminho_da_camada(args.saida)
    elif args.modo == "varrer":
        varrer(args.saida, args.por_livro, args.padrao)
    else:
        resumir(args.saida, args.entradas, args.commit, args.commit_do_caminho)


if __name__ == "__main__":
    main()
