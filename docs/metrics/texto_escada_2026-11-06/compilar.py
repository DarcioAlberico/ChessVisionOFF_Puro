"""Compila `docs/metrics/texto_escada_2026-11-06.json` (S-745), a escada de linhas de base, a partir dos JSONL, que ficam fora do repositório.

    compilar.py <esc_dev.jsonl> <esc_prata.jsonl> <saida.json>

Os JSONL saem de `ngramas.py`, com OMP_NUM_THREADS=3, QT_QPA_PLATFORM=offscreen, CVOFF_RAIZ no checkout com PDF/ e PYTHONPATH=<worktree>/src, em
pedaços abaixo de três minutos, pelo mesmo --dados. Os três ajustes da S-721 **não se remedem**: saem de `texto_prosa_fusao_2026-11-06.json`.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from chess_diagram_ocr.text import regua_prosa as regua

AQUI = Path(__file__).resolve().parent
TIP = regua.TIP
PROSA = regua.PROSA
VARIANTES = ("tess_hocr", "tess", "ng_05", "ng_10", "ng_20", "lex", "teto")
POR_RECUO = "pulado por recuo"


def ler(caminho: str) -> list[dict]:
    with open(caminho, encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo]


def _coluna(registros: list[dict], motor: str) -> tuple[list[float], list[float]]:
    placares = [r["placar"][f"{motor}|{TIP}"] for r in registros]
    return [p["erros"][PROSA] for p in placares], [p["total"][PROSA] for p in placares]


def cer(registros: list[dict], motor: str) -> float:
    erros, totais = _coluna(registros, motor)
    return round(100 * sum(erros) / max(1, sum(totais)), 3)


def par(registros: list[dict], a: str, b: str) -> dict[str, object]:
    ponto, baixo, alto = regua.diferenca_pareada(*_coluna(registros, a), *_coluna(registros, b), [r["identidade"] for r in registros])
    ea, _ = _coluna(registros, a)
    eb, _ = _coluna(registros, b)
    return {
        "delta_prosa_pp": round(100 * ponto, 3),
        "ic95_prosa_pp": [round(100 * baixo, 3), round(100 * alto, 3)],
        "folhas_melhores": sum(x < y for x, y in zip(ea, eb, strict=True)),
        "folhas_piores": sum(x > y for x, y in zip(ea, eb, strict=True)),
    }


def trocas(registros: list[dict], motor: str) -> dict[str, int]:
    """Palavra a palavra contra a base, só nas folhas em que o número de palavras não mudou: o que a variante trocou, e o que a referência diz da troca."""
    conta = {"trocas": 0, "para_palavra_da_referencia": 0, "estragou_palavra_da_referencia": 0}
    for r in registros:
        base, nova = r["hip"]["tess_hocr"].split(), r["hip"][motor].split()
        if len(base) != len(nova):
            continue
        referencia = set(r["ref"].split())
        for antes, depois in zip(base, nova, strict=True):
            if antes != depois:
                conta["trocas"] += 1
                conta["para_palavra_da_referencia"] += depois in referencia
                conta["estragou_palavra_da_referencia"] += antes in referencia and depois not in referencia
    return conta


def bloco(registros: list[dict], *, uso: str = "") -> dict[str, object]:
    razoes = [r["tempo"]["tess_hocr"] / max(1e-6, r["tempo"]["tess"]) for r in registros]
    saida: dict[str, object] = {
        "folhas": len(registros),
        "livros": len({r["identidade"] for r in registros}),
        "cer_prosa_pct": {m: cer(registros, m) for m in VARIANTES},
        "pares": {
            "hOCR - TSV, a primeira escolha": par(registros, "tess_hocr", "tess"),
            **{f"{m} - tess_hocr": par(registros, m, "tess_hocr") for m in ("ng_05", "ng_10", "ng_20", "lex", "teto")},
        },
        "palavras": sum(len(r["hip"]["tess_hocr"].split()) for r in registros),
        "trocas": {m: trocas(registros, m) for m in ("ng_05", "ng_10", "ng_20", "lex", "teto")},
        "segundos_tess": round(statistics.fmean(r["tempo"]["tess"] for r in registros), 2),
        "segundos_tess_hocr": round(statistics.fmean(r["tempo"]["tess_hocr"] for r in registros), 2),
        "razao_mediana_hocr_sobre_tsv": round(statistics.median(razoes), 2),
    }
    if uso:
        saida["uso"] = uso
    return saida


def _do_relatorio_da_fusao() -> dict:
    return json.loads((AQUI.parent / "texto_prosa_fusao_2026-11-06.json").read_text(encoding="utf-8"))


def main(dev: str, prata: str, saida: str) -> None:
    de_dev, de_prata = ler(dev), ler(prata)
    fusao = _do_relatorio_da_fusao()
    ablacao = fusao["ablacao"]
    codigo = de_dev[0]["codigo"]
    ng_dev, ng_prata = bloco(de_dev), bloco(de_prata, uso="ordenação")
    cer_fusao_dev = fusao["conjuntos"]["ouro_dev"]["motores"]["fusao"]["tip"]
    def ajuste(chave: str) -> dict:
        return {c: ablacao[c].get(chave) for c in ("ouro_dev", "prata", "prata_admitida") if c in ablacao}
    relatorio = {
        "item": "S-745: a escada de linhas de base, antes de qualquer modelo da casa",
        "medido_em": "2026-11-06",
        "pergunta": "Qual o melhor leitor de linha que não exige modelo da casa? É contra ele que a S-755 compara.",
        "melhor_degrau": {
            "nome": "a fusão de 2026-11-06 (motor=fusao) sobre o Tesseract 5.5 com tessdata fast, sem nenhum ajuste do degrau 0",
            "por_que": "nenhum dos quatro itens do degrau 0 paga, e os degraus 1, 2 e 3 foram pulados por recuo. A S-755 compara contra ele, até a D2 ou a D7 mudarem isto.",
            "ouro_dev_cer_prosa_pct": round(100 * cer_fusao_dev["cer_prosa"], 3),
            "ouro_dev_ic95_pct": [round(100 * v, 3) for v in cer_fusao_dev["ic95_prosa_dois_niveis"]],
            "scan_ouro_dev": "sem número: não há verdade humana (S-703, decisão D3)",
            "fonte": "docs/metrics/texto_prosa_fusao_2026-11-06.json",
        },
        "escada": [
            {"degrau": "0a", "o_que": "--user-words com os nomes", "estado": "medido e recusado pela S-721", "ouro_dev": ajuste("uw"),
             "leitura": "1 de 316 linhas muda, para pior; no spa o processo termina com erro, com a lista toda", "scan_ouro_dev": "sem número"},
            {"degrau": "0b", "o_que": "load_system_dawg=0 na notação", "estado": "medido e recusado pela S-721", "ouro_dev": ajuste("dic"),
             "leitura": "0 de 120 linhas mudam: o LSTM não lê essa variável em tempo de execução", "scan_ouro_dev": "sem número"},
            {"degrau": "0c", "o_que": "escala pela altura-x", "estado": "medido e recusado pela S-721", "ouro_dev": ajuste("esc"),
             "leitura": "diferença dentro do ruído nos dois conjuntos", "scan_ouro_dev": "sem número"},
            {"degrau": "0d", "o_que": "n-gramas de caractere por língua desempatando lstm_choice_mode=2", "estado": "medido e recusado aqui",
             "ouro_dev": ng_dev["pares"], "prata_ordenacao": ng_prata["pares"], "scan_ouro_dev": "sem número",
             "leitura": "o ponto piora nos dois conjuntos, em toda margem, com o IC tocando o zero: 7 folhas piores contra 1 no dev, 18 contra 2 na prata. Das 32 trocas do dev com margem de 1 nat, nenhuma leva a palavra da referência e 11 estragam uma certa (nome próprio). O custo não é o que recusa: é o ganho, porque até o oráculo só tira 0,046 p.p. no dev."},
            {"degrau": "1", "o_que": "tessdata_best (S-741)", "estado": POR_RECUO, "por_que": "D2, download não autorizado: fica o fast (seção 7 do roadmap)"},
            {"degrau": "2", "o_que": "ajuste fino do Tesseract (tesstrain + S-746)", "estado": POR_RECUO, "por_que": "D2 e D7, downloads não autorizados; a S-746 só serve a este degrau e fica de fora"},
            {"degrau": "3", "o_que": "PP-OCR latino em ONNX", "estado": POR_RECUO, "por_que": "D7, download não autorizado"},
        ],
        "ngramas": {
            "regra": "palavra de letras, de 3 letras ou mais, fora do léxico da língua: troca pela alternativa (confiança >= 5%, até 2 posições) cujo trigrama ganha pela margem",
            "modelo": "trigramas de caractere, suavização 0,5, contados nos tipos de lexico.da_lingua",
            "variantes": {"ng_05": "margem 0,5 nat", "ng_10": "1 nat", "ng_20": "2 nats", "lex": "o controle: a alternativa que é palavra do léxico", "teto": "o oráculo: a alternativa que está na referência"},
            "ouro_dev": ng_dev,
            "prata": ng_prata,
            "custo_do_processo": {
                "pergunta": "A S-729 recusou as alternativas por pagar um processo a mais por folha, sem dizer quanto. Quanto é?",
                "resposta": f"{ng_dev['segundos_tess_hocr']} s por folha no dev e {ng_prata['segundos_tess_hocr']} s na prata, se for um processo a mais; +15% se o hOCR substituir o TSV, e aí a primeira escolha do hOCR ainda perde {ng_dev['pares']['hOCR - TSV, a primeira escolha']['delta_prosa_pp']} p.p. no dev. Sob contenção: não julga o G4.",
                "veredito": "o custo sozinho não o tornaria inviável. Quem o recusa é o ganho.",
            },
        },
        "codigo": {k: codigo.get(k) for k in ("pacote", "commit", "src_sujo", "modelo_sha256", "tesseract", "tessdata_sha256")},
        "ressalvas": [
            "O ouro_dev é dev contaminado, e a regra foi escrita sem olhar o teste, que não foi aberto. O scan-ouro não tem número: sem verdade, M3 e M4 não existem.",
            "prata só ordena: a referência é OCR de terceiro. No Kmoch ela erra 30% a 42% da prosa, e o ganho de n-gramas ali pode ser concordar com o erro dela.",
            "Tempo sob contenção (duas outras medições na máquina): só a razão entre os dois tempos, folha a folha, fala de alguma coisa, e não julga o G4.",
            "Os três ajustes da S-721 não foram remedidos, a pedido: os números são os dela.",
        ],
    }
    Path(saida).write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    for nome, b in (("ouro_dev", ng_dev), ("prata (ordenação)", ng_prata)):
        print(nome, b["folhas"], "folhas", b["cer_prosa_pct"])
        for chave, valor in b["pares"].items():
            print(" ", chave, valor)
        print("  segundos", b["segundos_tess"], b["segundos_tess_hocr"], "razão mediana", b["razao_mediana_hocr_sobre_tsv"])
    print("fusão", relatorio["melhor_degrau"])
    for chave in ("uw", "dic", "esc"):
        print(chave, ajuste(chave))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main(*sys.argv[1:4])
