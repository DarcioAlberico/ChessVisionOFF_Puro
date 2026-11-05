"""Folhas de conferência da auditoria visual da S-702: 20 linhas por livro, a tinta ao lado da camada.

Para cada livro do dev e do teste do manifesto, sorteia 20 linhas da referência (a montagem da
camada por `ler_pagina(motor="camada")`, sem as linhas que cruzam diagrama, como a régua faz) entre
as folhas do manifesto, na ordem `sha256(identidade + folha + ":" + linha)`. Cada linha vira um
recorte da página a 200 dpi com o texto da camada desenhado embaixo, em duas folhas de 10 linhas,
e um `.json` com o texto exato e o código de cada caractere fora do ASCII -- a imagem sozinha não
distingue um hífen de um traço.

**A saída tem texto de livro comercial e vai para fora do repositório.** Quem confere não é quem
sorteou: gente, ou um agente que só recebe as folhas e a regra de divergência.

Uso: auditoria.py <ouro.json> <pasta_de_saida> [identidade ...]  (sem identidades: todos os livros)
"""
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import fitz
import matplotlib
from PIL import Image, ImageDraw, ImageFont

from chess_diagram_ocr.text import ouro
from chess_diagram_ocr.text.leitor import ler_pagina

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "texto_prosa_2026-10-30"))
import banco  # noqa: E402

# o checkout que tem PDF/ e PDF Digitais/: CVOFF_RAIZ, ou o repositório onde este script mora
RAIZ = os.environ.get("CVOFF_RAIZ") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LINHAS = 20
POR_FOLHA_DE_CONFERENCIA = 10
FONTE = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf", "DejaVuSans.ttf")
DPI = 200
LARGURA = 1500


def linhas_do_livro(identidade, pdf, folhas):
    candidatas = []
    for folha in folhas:
        pagina = ler_pagina(pdf, folha - 1, motor="camada")
        diagramas = [d.bbox for d in pagina.diagramas]
        for k, ln in enumerate(banco.linhas_da_pagina(pagina)):
            texto = (ln.texto or "").strip()
            if len(texto) >= 12 and not banco.cruza_diagrama(ln.bbox, diagramas):
                chave = hashlib.sha256(f"{identidade}{folha}:{k}".encode()).hexdigest()
                candidatas.append((chave, folha, k, tuple(ln.bbox), texto))
    return sorted(candidatas)[:LINHAS]


def um_livro(args):
    identidade, split, pdf, folhas, saida = args
    doc = fitz.open(pdf)
    fonte = ImageFont.truetype(FONTE, 26)
    escolhidas = linhas_do_livro(identidade, pdf, folhas)
    registro = []
    for parte in range(0, len(escolhidas), POR_FOLHA_DE_CONFERENCIA):
        linhas = []
        for numero, (_, folha, k, bbox, texto) in enumerate(escolhidas[parte:parte + POR_FOLHA_DE_CONFERENCIA], parte + 1):
            r = fitz.Rect(bbox) + (-3, -3, 3, 3)
            pix = doc[folha - 1].get_pixmap(dpi=DPI, clip=r & doc[folha - 1].rect)
            recorte = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            if recorte.width > LARGURA:
                recorte = recorte.resize((LARGURA, max(1, recorte.height * LARGURA // recorte.width)))
            linhas.append((numero, recorte, texto))
            registro.append({"n": numero, "folha": folha, "linha": k, "texto": texto,
                             "fora_do_ascii": [f"{c} U+{ord(c):04X}" for c in sorted(set(texto)) if ord(c) > 126]})
        altura = sum(rc.height + 80 for _, rc, _ in linhas) + 20
        folha_img = Image.new("RGB", (LARGURA + 80, altura), "white")
        d = ImageDraw.Draw(folha_img)
        y = 10
        for numero, recorte, texto in linhas:
            d.text((5, y), f"{numero:2d}", fill="red", font=fonte)
            folha_img.paste(recorte, (60, y))
            y += recorte.height + 6
            d.text((60, y), texto, fill=(0, 0, 160), font=fonte)
            y += 56
            d.line((0, y + 6, LARGURA + 80, y + 6), fill=(200, 200, 200))
            y += 18
        folha_img.save(os.path.join(saida, f"{split}_{identidade}_{parte // POR_FOLHA_DE_CONFERENCIA + 1}.png"))
    with open(os.path.join(saida, f"{split}_{identidade}.json"), "wb") as f:
        f.write(json.dumps(registro, ensure_ascii=False, indent=1).encode())
    return identidade, len(escolhidas)


def main(manifesto, saida, *so):
    m = ouro.carregar(manifesto)
    os.makedirs(saida, exist_ok=True)
    livros = [x for x in m.livros if x.split in (ouro.DEV, ouro.TESTE) and (not so or x.identidade in so)]
    caminho = ouro.localizar([x.identidade for x in livros], [os.path.join(RAIZ, "PDF"), os.path.join(RAIZ, "PDF Digitais")])
    faltam = sorted({x.identidade for x in livros} - set(caminho))
    assert not faltam, f"livros do manifesto que não se acham: {faltam}"
    tarefas = [(x.identidade, x.split, str(caminho[x.identidade]),
                sorted(f.folha for f in m.folhas if f.identidade == x.identidade), saida) for x in livros]
    with ProcessPoolExecutor(8) as ex:
        for identidade, n in ex.map(um_livro, tarefas):
            print(identidade, n, "linhas")


if __name__ == "__main__":
    main(*sys.argv[1:])
