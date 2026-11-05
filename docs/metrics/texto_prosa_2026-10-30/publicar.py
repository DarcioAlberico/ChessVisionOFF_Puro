"""Compila os JSONL do banco no relatório de docs/metrics (caminhos relativos).

É o compilador do relatório de 2026-10-30 (terceira régua, depois da rodada 4 do crítico). Os
nomes de entrada (ouro_*.jsonl, misto, degradado, prata*, guardados em `dados/2026-10-30/` da skill) e as ressalvas são daquela
medição; para um relatório novo, copie e
ajuste -- e prefira o `cvoff-texto-prosa` da S-706 quando ele existir.

Uso: publicar.py <destino.json> [pasta_dos_jsonl]
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from resumo import diferenca_pareada, familia, linha_de_motor  # noqa: E402

# o checkout que tem PDF/ e models/: CVOFF_RAIZ, ou o repositório onde este script mora
RAIZ = os.environ.get("CVOFF_RAIZ") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
AQUI = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
TESS = os.path.dirname(os.environ.get("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"))


def sha(caminho):
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def git(*a):
    return subprocess.run(["git", "-C", RAIZ, *a], capture_output=True, text=True).stdout.strip()


def carregar(n):
    return [json.loads(lin) for lin in open(os.path.join(AQUI, n), encoding="utf-8")]


def r4(x):
    return round(float(x), 4)


def resumir(regs, pares=()):
    motores = list(regs[0]["hip"].keys())
    out = {"folhas": len(regs), "livros": sorted({r["livro"] for r in regs}),
           "caracteres_de_prosa": sum(r["placar"]["glifo|tip"]["total"]["prosa"] for r in regs),
           "palavras_de_prosa": sum(r["placar"]["glifo|tip"]["wer"]["n"] for r in regs),
           "caracteres_de_notacao": sum(r["placar"]["glifo|tip"]["total"]["notacao"] for r in regs),
           "linhas_da_camada_fora_por_cruzar_diagrama": sum(r["n_linhas"].get("ref_no_diagrama", 0) for r in regs),
           "segundos_por_folha": {k: round(float(np.mean([r["tempo"][k] for r in regs])), 2) for k in regs[0]["tempo"]},
           "motores": {}, "pares": {}, "por_livro": {}}
    for norm in ("tip", "cru"):
        for m in motores:
            x = linha_de_motor(regs, m, norm)
            out["motores"].setdefault(m, {})[norm] = {
                "cer_prosa": r4(x["cer_prosa"]), "ic95_prosa_dois_niveis": [r4(x["ic95"][0]), r4(x["ic95"][1])],
                "wer_prosa_sdi": r4(x["wer_prosa"]), "wer_partes": x["wer_partes"],
                "cer_notacao": r4(x["cer_notacao"]), "cer_espaco": r4(x["cer_espaco"]), "insercoes": x["insercoes"],
                "figurina_revocacao": r4(x["fig_revocacao"]), "figurina_precisao": r4(x["fig_precisao"])}
    livros = [r["livro"] for r in regs]
    for a, b in pares:
        if a not in motores or b not in motores:
            continue
        for classe in ("prosa", "notacao"):
            Pa = [r["placar"][f"{a}|tip"] for r in regs]
            Pb = [r["placar"][f"{b}|tip"] for r in regs]
            d, lo, hi = diferenca_pareada([p["erros"][classe] for p in Pa], [p["total"][classe] for p in Pa],
                                          [p["erros"][classe] for p in Pb], [p["total"][classe] for p in Pb], livros)
            out["pares"][f"{a} - {b} ({classe})"] = {
                "pp": round(100 * d, 2), "ic95_pp": [round(100 * lo, 2), round(100 * hi, 2)],
                "folhas_melhores": sum(pa["erros"][classe] < pb["erros"][classe] for pa, pb in zip(Pa, Pb, strict=False)),
                "folhas_piores": sum(pa["erros"][classe] > pb["erros"][classe] for pa, pb in zip(Pa, Pb, strict=False))}
    porl = defaultdict(list)
    for r in regs:
        porl[r["livro"]].append(r)
    pres = [r["preservacao_v5"] for r in regs if "preservacao_v5" in r]
    if pres:
        out["preservacao_de_figurina_do_glifo_na_fusao_v5"] = {
            "preservadas": sum(a for a, _ in pres), "do_glifo": sum(b for _, b in pres),
            "fracao": r4(sum(a for a, _ in pres) / max(1, sum(b for _, b in pres)))}
    for lin, rs in porl.items():
        out["por_livro"][lin] = {"lingua": rs[0]["lang"], "folhas": [r["pagina"] + 1 for r in rs], **{
            m: r4(sum(r["placar"][f"{m}|tip"]["erros"]["prosa"] for r in rs)
                  / max(1, sum(r["placar"][f"{m}|tip"]["total"]["prosa"] for r in rs))) for m in motores}}
    return out


def taxonomia(regs, motor):
    fam = Counter()
    ex = defaultdict(Counter)
    orig = defaultdict(Counter)
    for r in regs:
        for k, v in r["placar"][f"{motor}|tip"]["trocas"].items():
            ref, _, hip = k.partition(" -> ")
            if re.search(r"[A-Za-zÀ-ÿ]", ref) is None:
                continue
            f = familia(ref, hip)
            fam[f] += v
            ex[f][k] += v
            orig[f][r["livro"]] += v
    tot = sum(fam.values())
    por_livro = Counter()
    for f in fam:
        por_livro.update(orig[f])
    # "livros" sem corte: a fração de uma família num grupo de livros (89,6% de acento no RapidOCR, nos
    # livros em português) sai daqui e de "por_livro", e não de uma conta feita por fora
    return {"palavras_erradas": tot, "por_livro": dict(por_livro.most_common()), "familias": [
        {"familia": f, "n": v, "fracao": round(v / max(1, tot), 3), "exemplos": [e for e, _ in ex[f].most_common(5)],
         "livros": dict(orig[f].most_common())} for f, v in fam.most_common()]}


def guarda():
    """Densidade de leitura (caracteres lidos / componentes de tinta fora dos diagramas), S-710."""
    import csv
    linhas = list(csv.DictReader(open(os.path.join(AQUI, "cobertura.tsv"), encoding="utf-8"), delimiter="\t"))

    def perdida(r):
        return int(r["linhas_glifo"]) <= 2 and int(r["linhas_camada"]) >= 10

    out = {"sinal": "B_densidade = caracteres lidos pelo glifo / componentes de tinta (>= 6 px, >= 4 px de altura) "
                    "fora dos diagramas; A (cobertura das caixas) e C (caixa degenerada) medidos e reprovados",
           "por_conjunto": {}, "perdidas": []}
    for conj in sorted({r["conjunto"] for r in linhas}):
        v = sorted(float(r["B_densidade"]) for r in linhas if r["conjunto"] == conj and not perdida(r))
        a = [float(r["A_cobertura"]) for r in linhas if r["conjunto"] == conj and not perdida(r)]
        c = [float(r["C_degenerada"]) for r in linhas if r["conjunto"] == conj and not perdida(r)]
        out["por_conjunto"][conj] = {"folhas_legiveis": len(v), "densidade_min": v[0], "densidade_max": v[-1],
                                     "cobertura_min": min(a), "degenerada_max": max(c)}
    out["perdidas"] = [{"livro": r["livro"], "folha": int(r["folha"]), "densidade": float(r["B_densidade"]),
                        "cobertura": float(r["A_cobertura"])} for r in linhas if perdida(r)]
    return out


def admissao():
    """Taxa de admissão por livro (S-716/S-702), sem OCR nenhum: 30 folhas sorteadas por livro e, quando
    existe `admissao_livro_inteiro.tsv`, a recusa medida em todas as folhas dos livros que estão nele."""
    import csv
    from collections import Counter

    def ler(nome):
        caminho = os.path.join(AQUI, nome)
        if not os.path.exists(caminho):
            return None
        por = defaultdict(list)
        for r in csv.DictReader(open(caminho, encoding="utf-8"), delimiter="\t"):
            por[r["livro"]].append(r)
        out = {}
        for livro, rs in por.items():
            out[livro] = {"folhas": len(rs), "admitidas": sum(int(r["admitida"]) for r in rs),
                          "folhas_com_trecho_fora_do_diagrama": sum(int(r["trechos"]) > 0 for r in rs),
                          "motivos": dict(Counter(r["motivo"] for r in rs if r["motivo"] != "-"))}
            if rs[0].get("perfil_com_texto"):
                out[livro]["perfil_de_30_folhas"] = {"com_texto": int(rs[0]["perfil_com_texto"]),
                                                     "com_texto_invisivel": int(rs[0]["perfil_invisivel"])}
        return out

    amostra = ler("admissao.tsv")
    if amostra is None:
        return None
    return {"metodo": "admissao.py: criterios (a)-(d) da S-702, sem OCR; 30 folhas sorteadas por livro, semente "
                      "sha256('20261030:' + nome do arquivo) por livro -- a amostra nao depende da ordem nem dos "
                      "outros livros da corrida; (a) inclui o livro de scan (mais da metade das 30 folhas de perfil "
                      "com texto invisivel); (b) e fileira de 6+ caracteres de fonte de diagrama encostados, fora "
                      "dos retangulos",
            "por_livro": amostra,
            "livro_inteiro": ler("admissao_livro_inteiro.tsv")}


def main():
    ouro = carregar("ouro_completo.jsonl")
    ouro_ok = carregar("ouro_sem_perdida.jsonl")
    misto = carregar("misto.jsonl")
    degr = carregar("degradado.jsonl")
    prata = carregar("prata.jsonl")
    prata_adm = carregar("prata_admitida.jsonl")
    PARES = [("fusao_v5", "glifo"), ("fusao_v5", "tess"), ("fusao_v5", "fusao"), ("fusao_v5", "fusao_v4"),
             ("tess", "tess_oraculo"), ("tess", "glifo"), ("tess_pagina", "tess"), ("tess_pagina", "tess_oraculo")]
    rel = {
        "item": "Fase 100 (linha de base) -- docs/ROADMAP_TEXTO_PRECISO.md",
        "medido_em": "2026-10-30",
        "medicao": "quarta medicao (rodada 9: hipotese e referencia montadas como o produto -- cabecalho e rodape so quando nenhuma linha de coluna os cobre; a montagem anterior duplicava o cabecalho) com a terceira regua (rodada 4: lance com reticencia, simbolo Informator, fileira de coordenadas em fonte, descritiva, cirilico, captura com X e : passam a notacao/outro) sobre a segunda medicao (rodada 1: linhas da camada que cruzam diagrama fora da "
                   "referencia; separador entre tokens de prosa e prosa; WER (S+D+I)/N; IC95 em dois niveis; "
                   "oraculo em linhas visuais justas a tinta; degradado nas MESMAS folhas do ouro; fusao_v4)",
        "pergunta": "Quanto o OCR de texto erra na PROSA (texto que nao e lance nem avaliacao), por motor, e onde?",
        "commit": git("rev-parse", "HEAD"),
        "arvore_suja_em": [lin[3:] for lin in git("status", "--porcelain").splitlines() if lin[3:].startswith("src/")],
        "modelo": "models/char_classifier.pt",
        "modelo_sha256": sha(os.path.join(RAIZ, "models", "char_classifier.pt")),
        "tesseract": subprocess.run([os.path.join(TESS, "tesseract.exe"), "--version"], capture_output=True,
                                    text=True).stdout.splitlines()[0],
        "tessdata": {"variante": "fast", **{lin: sha(os.path.join(TESS, "tessdata", f"{lin}.traineddata"))[:16]
                                           for lin in ("eng", "por", "deu", "spa", "nld", "fra")}},
        "rapidocr": "rapidocr_onnxruntime, ch_PP-OCRv4_rec_infer.onnx, so reconhecimento (use_det=False)",
        "dpi": 220,
        "scripts_sha256": {n: sha(os.path.join(os.path.dirname(os.path.abspath(__file__)), n))[:16] for n in
                           sorted(f for f in os.listdir(os.path.dirname(os.path.abspath(__file__))) if f.endswith(".py"))},
        "scripts_onde": "~/.claude/skills/ocr-texto-preciso/scripts/; a migracao do roadmap os leva ao repositorio "
                        "em docs/metrics/texto_prosa_2026-10-30/ e o sha identifica a versao",
        "split": "TODOS os livros digitais aqui sao DEV e dev contaminado: a regua, a taxonomia e as regras de fusao "
                 "foram desenhadas olhando para eles. Nenhum numero deste relatorio decide portao.",
        "referencia": "camada de texto montada por text.leitor.ler_pagina(motor='camada'), sem as linhas que cruzam "
                      "retangulo de diagrama; ouro = livros nascidos digitais",
        "motores": {
            "glifo": "producao: ler_pagina(motor='glifo') com todos os padroes",
            "tess": "Tesseract --psm 7 em cada caixa de linha que o GLIFO achou (mesmo leiaute)",
            "rapid": "RapidOCR so-reconhecimento nas mesmas caixas (sem acento: modelo chines+ingles)",
            "fusao": "por linha: notacao de QUALQUER lado -> glifo; prosa -> Tesseract",
            "fusao_rapid": "idem com RapidOCR",
            "fusao_v2": "glifo so onde ELE ve figurina (com o numero de lance do Tesseract); resto do Tesseract",
            "fusao_v3": "fusao_v2 + veto: se o Tesseract leu ali palavra so de letras, a palavra vence a figurina",
            "fusao_v4": "fusao (notacao de qualquer lado -> glifo) + o veto de palavra so-de-letras da v3",
            "fusao_v5": "v4 com veto so por palavra que existe (lexico + palavras funcionais curtas de 6 linguas) e numero de lance do Tesseract so quando o glifo o partiu: a regra recomendada para comecar a S-721",
            "tess_pagina": "Tesseract na PAGINA inteira com o leiaute dele (psm 3), diagramas pintados de branco",
            "tess_oraculo": "Tesseract nas linhas VISUAIS da camada: cada linha da camada apertada a tinta, e juntada so a IMEDIATAMENTE anterior quando esta a direita dela a menos de uma altura"},
        "normalizacoes": {
            "tip": "NFC; aspas/travessoes/ligaduras para ASCII; figurina -> letra da lingua; hifen de quebra juntado",
            "cru": "NFC; hifen de quebra juntado; nada mais"},
        "classes_de_token": "notacao = figurina; lance SAN, longo ou com reticencia; numero de lance; avaliacao, "
                            "inclusive simbolo Informator como a fonte o codifica; resultado; roque; letra de peca "
                            "solta; descritiva (P-K4, TXPTR); peca em cirilico; captura com x, X, : e o sinal de "
                            "multiplicacao; prosa = token com letra que nao e notacao (o separador entre dois tokens "
                            "de prosa e prosa); outro = sem letra, ou so letras acentuadas de fonte de diagrama",
        "estatistica": "IC95 por bootstrap em dois niveis (livros com reposicao, folhas com reposicao dentro do "
                       "livro), 2000 reamostras, semente 7; pares = diferenca pareada nas mesmas folhas",
        "conjuntos": {
            "ouro_dev_completo": resumir(ouro, PARES),
            "ouro_dev_sem_folha_perdida": {**resumir(ouro_ok, PARES), "filtro": "filtrar.py --sem-folha-perdida"},
            "ouro_dev_6_livros_leiaute_limpo": {**resumir(carregar("ouro_6livros.jsonl"), PARES),
                                                "filtro": "sem folha perdida e sem o Chess Evolution (linha intercalada)"},
            "ouro_dev_estrato_misto": {**resumir(misto, PARES), "o_que_e": "folhas com 20-55% de prosa: partida comentada"},
            "degradado_medio_mesmas_folhas": {**resumir(degr, PARES), "o_que_e": (
                "as MESMAS folhas do ouro, perfil 'medio' (~110 dpi efetivos) -- sem calibracao contra scan real")},
            "prata_todas": {**resumir(prata, PARES), "o_que_e": "scans reais; referencia = OCR de terceiro; so ordena"},
            "prata_admitida": {**resumir(prata_adm, PARES), "filtro": "filtrar.py --oraculo-max 0.10",
                               "o_que_e": "so ordena motores; a regra de admissao por oraculo foi reprovada para "
                                          "o ouro (S-702) e aqui so limpa o pior desalinhamento"},
        },
        "folhas_perdidas_em_silencio": [
            {"livro": r["livro"], "folha": r["pagina"] + 1, "linhas_da_camada": r["n_linhas"]["ref"],
             "linhas_do_glifo": r["n_linhas"]["glifo"],
             "cer_prosa_glifo": r4(r["placar"]["glifo|tip"]["erros"]["prosa"] / max(1, r["placar"]["glifo|tip"]["total"]["prosa"])),
             "cer_prosa_tess_oraculo": r4(r["placar"]["tess_oraculo|tip"]["erros"]["prosa"] / max(1, r["placar"]["tess_oraculo|tip"]["total"]["prosa"]))}
            for r in ouro + misto + prata if r["n_linhas"]["glifo"] <= 2 and r["n_linhas"]["ref"] >= 10],
        "taxonomia": {"glifo_ouro": taxonomia(ouro_ok, "glifo"), "tess_ouro": taxonomia(ouro_ok, "tess"),
                      "fusao_v5_ouro": taxonomia(ouro_ok, "fusao_v5"), "rapid_ouro": taxonomia(ouro_ok, "rapid"),
                      "glifo_prata": taxonomia(prata_adm, "glifo"), "fusao_v5_prata": taxonomia(prata_adm, "fusao_v5")},
        "tamanho_de_amostra": {
            "metodo": "amostra.py: reamostra livros e folhas do dev (tess_oraculo, CER ~0,16%, o nivel do alvo) e "
                      "mede a meia-largura superior do IC95 de dois niveis do conjunto simulado (60 simulacoes)",
            "tabela": open(os.path.join(AQUI, "amostra_oraculo.txt"), encoding="utf-8").read().splitlines(),
            "tabela_no_nivel_da_fusao": open(os.path.join(AQUI, "amostra_fusao.txt"), encoding="utf-8").read().splitlines(),
            "poder_pareado_oraculo_contra_tess": open(os.path.join(AQUI, "poder_oraculo_tess.txt"),
                                                      encoding="utf-8").read().splitlines()},
        "guarda_de_leitura_incompleta": guarda(),
        "admissao_s716": admissao(),
        "rejeitado_do_ouro": {
            "livro": "Gaprindashvili, Paata - Imagination in Chess (2005)",
            "motivo": "a camada NAO e a tinta: notacao em lixo de OCR ('l:l'.xe3') sob figurinas impressas; "
                      "Tesseract nas caixas da propria camada erra 45-57% (primeira medicao)"},
        "experimentos_avulsos": {
            "ablacao_glifo_7_folhas_cer_prosa": {
                "producao": 0.0422, "sem_caixa_alta": 0.083, "sem_dicionario": 0.0452, "sem_empilhados": 0.0445,
                "sem_marca_fina": 0.0436, "sem_traco": 0.0433, "colados_nunca": 0.0432, "sem_italico": 0.0429,
                "sem_numeros": 0.0422, "sem_juntar_lance": 0.0422,
                "nota": "medida na primeira regua (antes da rodada 1); vale como ordenacao entre variantes"},
            "tesseract_recorte_ampliado_2x": {
                "limpo_8_folhas": {"1x": 0.0457, "2x": 0.0464}, "degradado_medio_6_folhas": {"1x": 0.18, "2x": 0.1703},
                "leitura": "nao paga a 220 dpi; diferencas dentro do ruido"}},
        "ressalvas": [
            "todos os livros sao dev contaminado (ver 'split'); o ouro-teste da S-702 ainda nao existe",
            "CER de notacao desta regua nao e nota da notacao: a camada escreve o lance em formato que a tinta nao tem",
            "a prata so ordena motores: a referencia escreve figurina como lixo e a regua a conta como prosa",
            "o perfil degradado nao foi calibrado contra scan real; serve de estresse, nao de alvo",
            "tempos com 10 threads de Tesseract, RapidOCR e glifo na mesma CPU; nao e orcamento de producao",
        ],
    }
    reproducao = os.path.join(AQUI, "reproducao_main.json")
    if os.path.exists(reproducao):
        rel["reproduzido_na_main"] = json.load(open(reproducao, encoding="utf-8"))
    destino = sys.argv[1]
    with open(destino, "wb") as f:
        f.write((json.dumps(rel, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print("gravado", destino)


if __name__ == "__main__":
    main()
