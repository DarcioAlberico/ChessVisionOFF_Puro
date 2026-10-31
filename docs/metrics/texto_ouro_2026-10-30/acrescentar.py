"""O livro que chega depois do congelamento entra **a mais** no ouro-teste (S-702, a terceira língua).

Sorteia as folhas dele com a mesma regra e a mesma admissão do `sortear.py`, acrescenta com
`ouro.acrescentar_ao_teste` -- que não mexe em nenhum livro do teste nem em folha nenhuma, marca os
irmãos de série da reserva `fora_do_treino` e tira a pendência de língua quando ela se cumpre -- e
confere que o manifesto continua valendo.

**A elegibilidade é a dos candidatos do sorteio**, e a parte que se mede é medida aqui:

- o livro não está no manifesto, nem no acervo `PDF/` (o programa já o leu; o *Chess Evolution 2014*,
  da série de um livro dev, mora lá);
- não tem a diagramação de um livro dev de 2026-10-30: mesmo produtor e famílias de fonte com
  Jaccard ≥ `PARENTESCO` (a regra reproduz, sem divergência, os 11 livros da D6 que o inventário
  separou por diagramação);
- dá `2 * POR_ESTRATO` folhas admitidas.

A parte que não se mede é **declarada**: `--serie=<identidade>` do livro do manifesto da mesma série,
ou `--serie=nenhuma`. A série não se detecta sozinha -- o *Chess Evolution 2013* do acervo foi
regravado por outro programa e não se parece com o 2014 em produtor nem em fonte. Série de livro dev
não entra, e série que já tem livro no teste também não. Conteúdo de livro dev (o original de uma
tradução, como o do *400 Quebra-cabeças*) se declara com a identidade do livro dev em `--serie`.

**Antes do commit**, o livro passa pela auditoria visual como os outros:
`auditoria.py <ouro.json> <pasta> <identidade>`, conferida por quem não sorteou. Reprovado, ele não entra.

Uso: acrescentar.py <ouro.json> <pdf> <lingua> <origem: pdf|ebook> --serie=<identidade|nenhuma> [--data=AAAA-MM-DD]
  --data: a data de entrada gravada em `entrou_em` (hoje, se omitida); com a mesma data, o acréscimo se
  reproduz byte a byte
  <lingua>: código de três letras do Tesseract, um de `ouro.LINGUAS` (eng, por, spa, deu, nld, fra, ron, rus)
Raiz com `PDF/`: `CVOFF_RAIZ`, ou o repositório onde este script mora.
"""
import datetime
import json
import os
import re
import sys

import fitz

from chess_diagram_ocr.text import admissao, ouro
from chess_diagram_ocr.text.caderno import identidade_de

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sortear  # noqa: E402

PARENTESCO = 0.8


def familias_de_fonte(doc):
    """As famílias de fonte das folhas de perfil, sem o prefixo de subconjunto e sem o estilo."""
    familias = set()
    for indice in admissao.folhas_do_perfil(doc.page_count):
        for fonte in doc[indice].get_fonts():
            nome = re.split(r"[-,]", re.sub(r"^[A-Z]{6}\+", "", fonte[3] or ""))[0].lower()
            if nome:
                familias.add(nome)
    return familias


def livros_dev(pdf_dir):
    """Os sete livros dev de 2026-10-30, {identidade: caminho} -- os reprovados depois também."""
    rel = json.load(open(sortear.RELATORIO, encoding="utf-8"))
    caminhos = [os.path.join(pdf_dir, a) for a in rel["conjuntos"]["ouro_dev_completo"]["por_livro"]]
    return {identidade_de(c): c for c in caminhos}


def diagramacao_de_livro_dev(doc, dev):
    """O livro dev cuja diagramação este tem, ou `None`."""
    produtor, familias = admissao.produtor_de(doc), familias_de_fonte(doc)
    for identidade, caminho in dev.items():
        dev_doc = fitz.open(caminho)
        outras = familias_de_fonte(dev_doc)
        if produtor and produtor == admissao.produtor_de(dev_doc) and outras:
            if len(familias & outras) / len(familias | outras) >= PARENTESCO:
                return identidade
    return None


def main(manifesto, pdf, lingua, origem, *opcoes):
    estranhas = [op for op in opcoes if not op.startswith(("--serie=", "--data="))]
    if estranhas:
        raise SystemExit(f"opções desconhecidas: {estranhas} (as que existem: --serie=..., --data=AAAA-MM-DD)")
    valor = dict(op[2:].split("=", 1) for op in opcoes)
    if "serie" not in valor:
        raise SystemExit("declare a série: --serie=<identidade do livro irmão> ou --serie=nenhuma")
    serie = valor["serie"]
    hoje = datetime.date.today()
    try:
        dia = datetime.date.fromisoformat(valor.get("data") or hoje.isoformat())
    except ValueError as erro:
        raise SystemExit(f"--data={valor.get('data')}: não é uma data AAAA-MM-DD") from erro
    if dia > hoje:
        raise SystemExit(f"--data={dia}: data futura; o livro entra no dia em que é acrescentado")
    data = dia.isoformat()
    if lingua not in ouro.LINGUAS:
        raise SystemExit(f"língua {lingua!r} fora de {ouro.LINGUAS}")
    if origem not in ouro.ORIGENS:
        raise SystemExit(f"origem {origem!r} fora de {ouro.ORIGENS}")
    m = ouro.carregar(manifesto)
    pdf_dir = os.path.join(sortear.RAIZ, "PDF")
    identidade = identidade_de(pdf)
    assert identidade, f"não consegui ler {pdf}"
    if identidade in ouro.localizar([identidade], [pdf_dir]):
        raise SystemExit(f"{identidade} está no acervo PDF/: o programa já o leu, e ele não é livro novo")
    dev = livros_dev(pdf_dir)
    vista = diagramacao_de_livro_dev(fitz.open(pdf), dev)
    if vista:
        raise SystemExit(f"{identidade} tem a diagramação do livro dev {vista}")
    grupo = ""
    if serie != "nenhuma":
        irmao = next((x for x in m.livros if x.identidade == serie), None)
        if irmao is None:
            raise SystemExit(f"--serie={serie}: o manifesto não tem esse livro")
        if serie in dev or irmao.grupo in dev or irmao.diagramacao == "vista":
            raise SystemExit(f"--serie={serie} é livro dev ou do grupo de um: a série dele não serve de teste")
        grupo = irmao.grupo or irmao.identidade
    _, folhas, recusadas = sortear.folhas_do_livro((identidade, pdf))
    livro = ouro.LivroDoOuro(identidade, ouro.TESTE, lingua, origem, "nova", grupo)
    try:
        novo = ouro.acrescentar_ao_teste(m, livro, folhas, entrou_em=data,
                                         folhas_minimas=2 * sortear.POR_ESTRATO)
    except ValueError as erro:
        raise SystemExit(f"{erro} (folhas recusadas: {recusadas})") from erro
    assert all(x in novo.livros or x.split == ouro.RESERVA for x in m.livros)
    assert novo.folhas[: len(m.folhas)] == m.folhas
    erros = ouro.problemas(novo)
    assert not erros, erros
    ouro.gravar(novo, manifesto)
    print(f"{identidade} entrou no teste em {data} com {len(folhas)} folhas; "
          f"pendências: {list(novo.pendencias) or 'nenhuma'}")
    print(f"agora a auditoria: auditoria.py {manifesto} <pasta fora do repositório> {identidade}")


if __name__ == "__main__":
    main(*sys.argv[1:])
