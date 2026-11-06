"""A folha-canário por língua (S-763): sorteia, grava o manifesto, e mede o que ela vê. Só identidades e números saem daqui.

    canario.py sortear <medidas.jsonl>      escreve assets/texto_prosa/canario.json, a partir das folhas do ouro-dev já lidas pela fusão
    canario.py validar                      relê duas vezes (o falso alarme de uma mesma versão) e com o glifo (a regressão de mentira)

**Sorteio por `sha256("S-763:identidade:folha")`, entre as folhas de prosa do dev de cada língua.** O dev só tem `eng` e `por`: o ouro-teste, que tem as outras, não abre aqui. O scan não tem canário: a verdade
dele é a S-703, e a camada de terceiro mediria a referência. **É "canário de camada, não humano"**, e o manifesto o diz.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
MINIMO_DE_PROSA = 1000


def sortear(medidas: str) -> int:
    from chess_diagram_ocr.text import monitor_prosa

    registros = [json.loads(ln) for ln in Path(medidas).read_text(encoding="utf-8").splitlines()]
    escolhidas = {}
    for r in sorted(registros, key=lambda r: hashlib.sha256(f"S-763:{r['identidade']}:{r['folha']}".encode()).hexdigest()):
        p = r["placar"]["fusao|tip"]
        if r["lingua"] not in escolhidas and p["total"]["prosa"] >= MINIMO_DE_PROSA:
            escolhidas[r["lingua"]] = {
                "identidade": r["identidade"], "folha": r["folha"], "lingua": r["lingua"], "motor": "fusao",
                "cer_de_base": round(p["erros"]["prosa"] / p["total"]["prosa"], 6),
            }
    manifesto = {
        "rotulo": monitor_prosa.ROTULO_DO_CANARIO,
        "nota": "A referência é a camada do próprio livro digital admitido, porque a humana depende da S-703 e da D3. Ver a spec da S-763. Só o dev: eng e por.",
        "folhas": [escolhidas[k] for k in sorted(escolhidas)],
    }
    (RAIZ / "assets" / "texto_prosa" / monitor_prosa.CANARIO).write_bytes((json.dumps(manifesto, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(manifesto)
    return 0


def validar() -> int:
    from chess_diagram_ocr.cli import texto_prosa

    saidas = {}
    for nome, motor in (("primeira", ""), ("segunda", ""), ("regressao_de_mentira", "glifo")):
        saidas[nome] = texto_prosa.conferir_o_canario(motor=motor)
    print(json.dumps(saidas, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(sortear(sys.argv[2]) if sys.argv[1] == "sortear" else validar())
