"""Junta o que os outros scripts desta pasta mediram em `docs/metrics/texto_confianca_2026-11-06.json`. Só números e identidades.

    compilar.py <pasta dos pedaços> <saída.json>

Os pedaços: `calibrador.json` (ajustar.py), `monitor.json` (monitor.py), `repetidos.json` (repetidos.py), `alternativas.json` (alternativas.py), `canario.json` (canario.py validar).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from chess_diagram_ocr.text import regua_prosa, tesseract

RAIZ = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(RAIZ), *args], capture_output=True, text=True, check=False).stdout.strip()


def main() -> int:
    pasta, saida = Path(sys.argv[1]), Path(sys.argv[2])

    def pedaco(nome: str) -> Any:
        return json.loads((pasta / f"{nome}.json").read_text(encoding="utf-8"))

    motor = tesseract.achar_motor()
    relatorio = {
        "item": "S-760, S-761, S-763, S-766",
        "medido_em": "2026-11-06",
        "pergunta": "A confiança por palavra se calibra por domínio? A marca paga a atenção de quem revisa? Algum sinal sem referência acusa a folha ruim? Corrigir uma vez corrige o livro?",
        "codigo": {
            "commit_da_base": _git("merge-base", "HEAD", "main") or _git("rev-parse", "HEAD"),
            "tesseract": motor.versao,
            "tessdata_sha256": {k: hashlib.sha256((motor.tessdata / f"{k}.traineddata").read_bytes()).hexdigest()[:16] for k in ("eng", "por")} if motor.tessdata else {},
            "regua": regua_prosa.VERSAO_CLASSIFICADOR,
        },
        "regua": "palavra de prosa da régua, normalização tip, contra a camada montada; o split teste não foi aberto",
        "ressalvas": [
            "Tudo é dev contaminado: quem julga a G5 é o portão, no ouro-teste, que este item não abriu.",
            "O ouro-dev tem só 20 palavras erradas depois da S-721: o IC é largo, e a medida que não foi vista pelo ajuste é a que deixa um livro de fora.",
            "No domínio scan, a referência é OCR de terceiro: a prata ordena, e a probabilidade de lá é contra aquela referência. O ajuste tira a folha em que o oráculo erra mais de 10%; a validação publica com e sem.",
            "Parte do erro do dígito é ruído de rótulo: legenda e título lidos certo que a referência tira, por cruzarem o diagrama (`OLAFSSON`, `Short-Speelman`) contam como erro, e nenhuma marca os separa.",
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
