"""Compila `docs/metrics/texto_g3_20261106.json` a partir das contagens de `varredura.py`. Só agregados, sem texto de livro.

    python apurar.py <pasta dos .jsonl> <camada.jsonl> <relidas.json> <saída.json>

O que este script não calcula, e vem como constante: a conferência visual dos mosaicos, que quem mediu fez folha a folha.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

CONFERENCIA_DAS_136 = {
    "só diagrama, com o tabuleiro desenhado em fonte na camada": 119,
    "diagramas com duas linhas de teste (Seirawan 200), não conferida palavra a palavra": 1,
    "grade de anotação com números (Schiller 274 a 287): perda parcial real, sem aviso": 13,
    "sumário com pontilhado (Euwe 4, Polgar 3), não conferida palavra a palavra": 2,
    "folha de rosto (Seirawan 2), não conferida palavra a palavra": 1,
}
CONFERENCIA_DO_RUIDO = {
    "capa, contracapa ou contracapa em negativo": 7,
    "só diagrama, com a hachura lida como letra (La casa del Ajedrez)": 26,
    "prosa real, com a coluna pontilhada lida como letra (Yusupov, Build Up Your Chess)": 9,
}


def main(pasta: str, camada: str, relidas: str, saida: str) -> None:
    regs = [json.loads(linha) for f in Path(pasta).glob("*.jsonl") for linha in f.open(encoding="utf-8")]
    ok = [r for r in regs if "erro" not in r]
    remedidas = [json.loads(linha) for linha in Path(camada).open(encoding="utf-8")]
    voltaram = json.loads(Path(relidas).read_bytes())
    seg = sorted(r["segundos"] for r in regs)
    suspeitas = [d for d in remedidas if d["montada"] >= 50 and d["lidos"] < 0.6 * d["montada"]]
    assert len(suspeitas) == sum(CONFERENCIA_DAS_136.values())
    ruido = [r for r in ok if r["lidos"] > 6000 and not r["avisos"]]
    assert len(ruido) == sum(CONFERENCIA_DO_RUIDO.values())
    relatorio = {
        "item": "G3 e a varredura do G101: toda folha do acervo pelo glifo e pela guarda da S-710",
        "quando": "2026-11-06",
        "codigo": {
            "varredura": "095496e5",
            "conserto_das_excecoes": "87d60bca",
            "ressalva": "só as 11 folhas da exceção foram relidas depois do conserto. As outras não mudam: só elas produziam a caixa vazia.",
        },
        "comando": "docs/metrics/texto_g3_2026-11-06/varredura.py, motor glifo a 220 dpi, 5 processos",
        "acervo": {
            "arquivos": len({r["livro"] for r in regs}),
            "folhas": len(regs),
            "ressalva": "PDF/ tem livros duplicados: a contagem é de arquivos, e a mesma folha pode valer duas vezes.",
        },
        "veredito": {
            "G3": 0,
            "o_que_G3_promete": "perda total sem aviso, a promessa da S-710. Perda parcial e ruído estão abaixo, e não entram no número.",
            "ouro_dev_teste_prata": "0 em todos, em texto_prosa_portoes_20261106.json",
            "G101_continua_reprovado": "pela perda de leiaute no ouro-teste, +1,79 p.p. [+0,74; +3,05] contra teto de +0,3",
        },
        "excecoes": {
            "na_varredura": sum("erro" in r for r in regs),
            "causa": "text/poeira.py cortava a letra toda fora do alcance e devolvia caixa sem altura; cv2.resize derrubava a folha",
            "relidas_com_o_conserto": len(voltaram),
            "ainda_com_erro": sum("erro" in d for d in voltaram),
            "das_relidas_com_mais_de_6000_lidos": sum(d.get("lidos", 0) > 6000 for d in voltaram),
        },
        "avisos": {
            "por_codigo": dict(Counter(a for r in ok for a in r["avisos"]).most_common()),
            "folhas_com_aviso": sum(bool(r["avisos"]) for r in ok),
        },
        "perda_total_sem_aviso": {
            "com_camada": {
                "criterio": "camada com ao menos 50 caracteres, menos de 5% lidos, sem aviso",
                "folhas": sum(r["camada_chars"] >= 50 and r["lidos"] < 0.05 * r["camada_chars"] and not r["avisos"] for r in ok),
            },
            "sem_camada": {
                "criterio": "menos de 50 caracteres na camada, menos de 600 lidos, sem aviso; régua independente da guarda: componentes de altura de letra a 110 dpi, fora de componente grande",
                "folhas_examinadas": sum(r["camada_chars"] < 50 and r["lidos"] < 600 and not r["avisos"] for r in ok),
                "com_100_letras_e_menos_da_metade_lida": 73,
                "o_que_sao": "todas do Reinfeld em espanhol, com cerca de 82 lidos: seis diagramas sem moldura, cujas peças a régua conta como letra. Duas vistas.",
            },
        },
        "perda_parcial_sem_aviso": {
            "suspeitas_pela_camada_crua": len(remedidas),
            "criterio_cru": "camada com ao menos 50 caracteres, menos de 60% lidos, sem aviso",
            "suspeitas_pela_camada_montada": len(suspeitas),
            "conferencia_visual_das_montadas": CONFERENCIA_DAS_136,
            "ressalva": "a camada montada ainda conta o tabuleiro em fonte destes livros, por isso as 119. Folha que lê mais de 60% e perde o resto não entra nesta conta.",
        },
        "ruido_sem_aviso": {
            "criterio": "mais de 6.000 caracteres lidos, sem aviso; uma folha cheia de prosa tem de 2.500 a 4.000",
            "folhas": len(ruido),
            "maior_leitura": max(r["lidos"] for r in ruido),
            "conferencia_visual": CONFERENCIA_DO_RUIDO,
            "ressalva": "a guarda só trata sinal solto como ruído em folha com moldura (S-711). Nas 9 de prosa, o texto fica afogado em 15 mil a 78 mil caracteres, e a tela não avisa.",
        },
        "criterio_da_s710_nao_refeito": "a varredura não gravou a densidade de cada folha, então a regra do corte de 0,5 segue valendo pela amostra de 812 folhas já publicada.",
        "segundos_por_folha": {
            "media": round(statistics.mean(seg), 2),
            "p50": seg[len(seg) // 2],
            "p95": seg[int(len(seg) * 0.95)],
            "p99": seg[int(len(seg) * 0.99)],
            "max": seg[-1],
            "ressalva": "cinco processos disputando a máquina, e a página inteira do acervo: não é o G4.",
        },
    }
    Path(saida).write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main(*sys.argv[1:5])
