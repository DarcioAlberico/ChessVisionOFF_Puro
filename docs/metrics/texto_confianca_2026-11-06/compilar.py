"""Junta o que os outros scripts desta pasta mediram em `docs/metrics/texto_confianca_2026-11-06.json`. Só números e identidades.

    compilar.py <pasta dos pedaços> <saída.json>

Os pedaços: `calibrador.json` (ajustar.py), `monitor.json` (monitor.py), `repetidos.json` (repetidos.py), `alternativas.json` (alternativas.py), `canario.json` (canario.py validar).
A pasta dos pedaços tem de ter os JSONL ao lado, em `..`: **o `codigo` do relatório sai do que cada folha gravou ao ser lida**, e não do `HEAD` de quem compila. A primeira versão gravava o merge-base com a `main`,
que nem continha o calibrador, e só `eng` e `por` num relatório com scan de dez livros.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from chess_diagram_ocr.text import regua_prosa

COLETA = ("ouro_dev", "reservado_ouro", "prata", "reservado_prata", "livro_603581", "livro_69343a")
PRODUTO = ("produto_ouro_dev", "produto_prata")


def codigo_de(pasta: Path, nomes: tuple[str, ...]) -> dict[str, Any]:
    """O que as folhas destes JSONL gravaram. Mais de um commit ou de um modelo aparece, e não some numa escolha."""
    commits: set[str] = set()
    modelos: set[str] = set()
    versoes: set[str] = set()
    tessdata: dict[str, str] = {}
    sujo = False
    folhas = 0
    for nome in nomes:
        with (pasta / f"{nome}.jsonl").open(encoding="utf-8") as arquivo:
            for linha in arquivo:
                c = json.loads(linha)["codigo"]
                folhas += 1
                commits.add(c["commit"])
                modelos.add(c["modelo_sha256"])
                versoes.add(c["tesseract"])
                tessdata.update(c["tessdata_sha256"])
                sujo = sujo or bool(c["src_sujo"])
    return {
        "folhas": folhas, "commit": sorted(commits), "src_sujo": sujo, "modelo_sha256": sorted(modelos), "tesseract": sorted(versoes),
        "tessdata_sha256": dict(sorted(tessdata.items())),
    }


def main() -> int:
    pasta, saida = Path(sys.argv[1]), Path(sys.argv[2])

    def pedaco(nome: str) -> Any:
        return json.loads((pasta / f"{nome}.json").read_text(encoding="utf-8"))

    relatorio = {
        "item": "S-760, S-761, S-763, S-766",
        "medido_em": "2026-11-06",
        "pergunta": "A confiança por palavra se calibra por domínio? A marca paga a atenção de quem revisa? Algum sinal sem referência acusa a folha ruim? Corrigir uma vez corrige o livro?",
        "codigo": {
            "regua": regua_prosa.VERSAO_CLASSIFICADOR,
            "coleta_que_ajustou": codigo_de(pasta.parent, COLETA),
            "marca_no_produto": codigo_de(pasta.parent, PRODUTO),
        },
        "regua": "palavra de prosa da régua, normalização tip, contra a camada montada; o split teste não foi aberto",
        "ressalvas": [
            "Tudo é dev contaminado: quem julga a G5 é o portão, no ouro-teste, que este item não abriu.",
            "O ouro-dev tem só 19 palavras erradas depois da S-721: o IC é largo, e a medida que não foi vista pelo ajuste é a que deixa um livro de fora.",
            "No domínio scan, a referência é OCR de terceiro: a prata ordena, e a probabilidade de lá é contra aquela referência. O ajuste tira a folha em que o oráculo erra mais de 10%; a validação publica com e sem.",
            "Parte do erro do digital é ruído de rótulo: legenda e título lidos certo que a referência tira, por cruzarem o diagrama (`OLAFSSON`, `Short-Speelman`) contam como erro, e nenhuma marca os separa.",
            "O livro c22d5e70, da prata, é da série de um livro do teste (S-750): é medido, e nunca ajusta.",
            "Tempos sob contenção: três trilhas na máquina. Nenhum número de tempo é veredito aqui.",
        ],
        "s760_s761_calibrador_e_marca": pedaco("calibrador"),
        "s760_alternativas_do_lstm": {
            "medida": pedaco("alternativas"),
            "custo": "0,88 a 1,34 s por folha como processo a mais, ou +15% substituindo o TSV, da S-745 e da S-729: não foi remedido sob contenção",
            "veredito": "não pagam, e ficam de fora: nenhuma diferença sai do IC",
        },
        "s763_monitor": {
            "regra": "ver o cabeçalho de texto_confianca_2026-11-06/monitor.py: escrita antes de olhar o número",
            "sinais_por_dominio": pedaco("monitor"),
            "canario": pedaco("canario"),
        },
        "s766_repetidos": pedaco("repetidos"),
    }
    saida.write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
