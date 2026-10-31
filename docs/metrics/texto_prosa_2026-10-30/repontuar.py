"""Recalcula o placar de um JSONL do banco a partir dos textos gravados (sem rodar motor)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import banco  # noqa: E402

ent, sai = sys.argv[1], sys.argv[2]
with open(sai, "w", encoding="utf-8") as f:
    for linha in open(ent, encoding="utf-8"):
        r = json.loads(linha)
        for tip in (True, False):
            ref = banco.normalizar(r["ref"], tipografia=tip, lang=r["lang"])
            for k, v in r["hip"].items():
                p = banco.pontuar(ref, banco.normalizar(v, tipografia=tip, lang=r["lang"]))
                r["placar"][f"{k}|{'tip' if tip else 'cru'}"] = banco.placar_dict(p)
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
