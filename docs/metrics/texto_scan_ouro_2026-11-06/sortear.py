"""Escreve `assets/texto_prosa/scan_ouro.json` (S-703): 30 folhas de 10 livros escaneados, antes de qualquer transcrição.

**Nenhum leitor roda aqui.** A produção sai das fontes e da resolução (`prata.estrato_de_producao`); o conteúdo da folha, do texto da camada
de terceiro que o PDF já traz, pelo classificador da régua; o livro sem camada só passa pela contagem de linhas em `leitor.segmentar`, que é
geometria. O teste do manifesto confere que este módulo não importa nem glifo, nem Tesseract, nem fusão.

**A ordem é a do sorteio, e o resto é regra escrita antes:**

1. Os dois livros do século XIX que o item nomeia entram primeiro, e no dev: os dois foram vistos pelas S-743 e S-721.
2. Teste: `COTAS_DO_TESTE`, por produção, entre os livros **não vistos**, na ordem `sha256(semente:identidade)`.
3. Dev: `COTAS_DO_DEV`, entre os que sobraram, vistos ou não, na mesma ordem.
4. Um livro por grupo (série ou autor), e no máximo `POR_LINGUA` por língua. Com 2 não sobrava `clearscan` para o dev: só há eng, deu e spa nele. As cinco línguas `problemas` confere.
5. O livro que não dá as folhas cede a vaga ao seguinte. As folhas vêm na ordem `sha256(identidade + folha)`.

**O livro sem camada não entra no sorteio**, porque sem ela o conteúdo da folha não se sabe antes de ler. Fora o que o item obriga, é um
recuo com custo: ver `SPEC_TEXTO_PRECISO.md`.

Uso: sortear.py <saida.json>. Raiz com `PDF/`: `CVOFF_RAIZ`. Só identidades saem daqui, e o texto da camada não é gravado nem impresso.
"""

from __future__ import annotations

import hashlib
import os
import statistics
import sys
from pathlib import Path

import fitz

from chess_diagram_ocr.text import ouro, prata, regua_prosa, scan_ouro
from chess_diagram_ocr.text.caderno import identidade_de

AQUI = Path(__file__).resolve().parent
RAIZ = Path(os.environ.get("CVOFF_RAIZ") or AQUI.parents[2])

SEMENTE = "s703-2026-11-06"
CONGELADO_EM = "2026-11-06"
COTAS_DO_TESTE = {prata.ATE_150: 2, prata.DE_300: 1, prata.CLEARSCAN: 2}
COTAS_DO_DEV = {prata.ATE_150: 1, prata.DE_300: 1, prata.CLEARSCAN: 1}
POR_LINGUA = 3
FOLHAS_POR_LIVRO = 3
LINHAS_MINIMAS_SEM_CAMADA = 15
CHARS_DE_LIVRO_COM_CAMADA = 200
"""Mediana de caracteres da camada por folha, nas folhas de perfil: abaixo disso, o livro não tem camada que diga o conteúdo."""

BACHMANN = "cc97a2f1"
NEUMANN = "05a0e10f"
OBRIGATORIOS = (BACHMANN, NEUMANN)

CATALOGO: dict[str, tuple[str, str]] = {
    # identidade: (língua, grupo). A lista dos escaneados do acervo; o que não está aqui não é candidato. Os digitais e a duplicata
    # de ebook (`calibre`, `pdfTeX`) ficam de fora, e os do ouro saem por `no_ouro`.
    "cc97a2f1": ("deu", "bachmann"), "05a0e10f": ("fra", "neumann"),
    "d611aba2": ("deu", "kemeri"), "93cc211e": ("eng", "aagaard"), "1033806d": ("eng", "aagaard"), "d28c7920": ("eng", "aagaard"),
    "0da3a0e8": ("deu", "brinckmann"), "3766d329": ("deu", "dufresne"), "0f88889e": ("deu", "estrin"),
    "ee6312cc": ("deu", "euwe"), "e16d97fe": ("deu", "euwe"), "76499e36": ("eng", "gallagher"), "1582c67e": ("eng", "gaprindashvili"),
    "1f13e292": ("deu", "gunderam"), "f83536bf": ("deu", "gutmayer"), "9f14b753": ("eng", "karpov"), "e0dcb169": ("eng", "karpov"),
    "9267efd2": ("nld", "kmoch"), "a9c024a3": ("spa", "koblenz"), "9013f3b8": ("spa", "yusupov"), "3dd812dd": ("eng", "yusupov"),
    "82e4b117": ("spa", "dobonov"), "694a1500": ("ron", "levenfis"), "8f259b04": ("eng", "flores"), "19b846c4": ("nld", "mieses"),
    "8cfb2b02": ("nld", "niemeijer"), "ed341925": ("eng", "pachman"), "e003408e": ("eng", "pachman"), "1d793f97": ("eng", "pachman"),
    "b49aec67": ("deu", "polugajewski"), "b77d3e1e": ("spa", "reinfeld"), "55dea76e": ("eng", "schiller"), "43beb378": ("eng", "secrets"),
    "21812291": ("eng", "stean"), "1198b562": ("ron", "stefaniu"), "e6e0be55": ("eng", "anand"), "c671c356": ("rus", "pilavov"),
    "8167f3d5": ("eng", "burgess"), "c22d5e70": ("eng", "nunn"), "65d6c32a": ("eng", "nunn"), "d057d44f": ("eng", "silman"),
    "8f3a3ee7": ("rus", "boleslavsky"), "5f01ea01": ("eng", "vladimirov"),
}

VISTOS_FORA_DA_PRATA = {"cc97a2f1", "f83536bf", "c671c356"}
"""Lidos pelas regras fora da prata: as folhas das S-743 e S-744, e as oito do russo da S-721. Os da prata saem do manifesto dela."""


def perfil(doc: fitz.Document) -> tuple[list[str], int, int]:
    """As fontes, a resolução mediana e a mediana de caracteres da camada, nas folhas de perfil. É o `perfil_de_producao` da S-705."""
    n = doc.page_count
    fontes, dpis, chars = set(), [], []
    for i in range(int(n * 0.1), int(n * 0.9), max(1, int(n * 0.8 / 12))):
        pagina = doc[i]
        fontes.update(f[3] for f in pagina.get_fonts())
        chars.append(len(pagina.get_text()))
        for imagem in pagina.get_image_info():
            x0, _, x1, _ = imagem["bbox"]
            if x1 - x0 > 0.5 * pagina.rect.width:
                dpis.append(imagem["width"] / ((x1 - x0) / 72))
    return sorted(fontes), int(statistics.median(dpis)) if dpis else 0, int(statistics.median(chars)) if chars else 0


def folhas_pela_camada(doc: fitz.Document, identidade: str, lingua: str) -> dict[str, list[int]]:
    """As primeiras folhas de cada conteúdo, na ordem do sorteio. Basta o dobro do que um livro pode dar."""
    achadas: dict[str, list[int]] = {ouro.PROSA: [], ouro.MISTO: []}
    for folha in ouro.ordem_das_folhas(identidade, doc.page_count):
        if all(len(v) >= 2 for v in achadas.values()):
            break
        estrato = ouro.estrato_do_texto(doc[folha - 1].get_text(), lambda token: regua_prosa.classe_do_token(token, lingua))
        if estrato is not None and len(achadas[estrato]) < 2:
            achadas[estrato].append(folha)
    return achadas


def folhas_pela_tinta(pdf: Path, doc: fitz.Document, identidade: str) -> list[int]:
    """O livro sem camada: as primeiras folhas com linhas de texto bastantes. Geometria, sem classificador nenhum."""
    from chess_diagram_ocr.pdf_io import render_pdf_page
    from chess_diagram_ocr.text import transcricao_scan

    achadas = []
    for folha in ouro.ordem_das_folhas(identidade, doc.page_count):
        imagem = render_pdf_page(str(pdf), folha - 1, 220)
        if len(transcricao_scan.linhas_da_folha(imagem, (), dpi=220)) >= LINHAS_MINIMAS_SEM_CAMADA:
            achadas.append(folha)
        if len(achadas) == FOLHAS_POR_LIVRO:
            break
    return achadas


def main(saida: str) -> None:
    no_ouro = {livro.identidade for livro in ouro.carregar().livros}
    da_prata = {livro.identidade for livro in prata.carregar().livros}
    candidatos: dict[str, dict] = {}
    for pdf in sorted((RAIZ / "PDF").glob("*.pdf")):
        identidade = identidade_de(pdf)
        chave = identidade[:8] if identidade else ""
        if chave not in CATALOGO or identidade in no_ouro:
            continue
        lingua, grupo = CATALOGO[chave]
        with fitz.open(pdf) as doc:
            fontes, dpi, chars = perfil(doc)
        producao = prata.estrato_de_producao(fontes, dpi)
        if producao is None:
            print(f"# {chave}: resolução intermediária, fora dos três estratos")
            continue
        candidatos[identidade] = {
            "pdf": pdf, "chave": chave, "lingua": lingua, "grupo": grupo, "producao": producao, "dpi": dpi, "chars": chars,
            "visto": identidade in da_prata or chave in VISTOS_FORA_DA_PRATA,
        }
    grupos: set[str] = set()
    linguas: dict[str, int] = {}
    escolhidos: list[tuple[dict, str, dict[str, list[int]]]] = []

    def cabe(c: dict) -> bool:
        return c["grupo"] not in grupos and linguas.get(c["lingua"], 0) < POR_LINGUA

    def tomar(c: dict, split: str, folhas: dict[str, list[int]]) -> None:
        grupos.add(c["grupo"])
        linguas[c["lingua"]] = linguas.get(c["lingua"], 0) + 1
        escolhidos.append((c, split, folhas))

    def folhas_do(identidade: str, c: dict) -> dict[str, list[int]] | None:
        if c["chars"] < CHARS_DE_LIVRO_COM_CAMADA:
            return None
        with fitz.open(c["pdf"]) as doc:
            achadas = folhas_pela_camada(doc, identidade, c["lingua"])
        m, p = len(achadas[ouro.MISTO]), len(achadas[ouro.PROSA])
        return achadas if m >= 1 and p >= 1 and m + p >= FOLHAS_POR_LIVRO else None

    for chave in OBRIGATORIOS:
        identidade = next(i for i, c in candidatos.items() if c["chave"] == chave)
        c = candidatos[identidade]
        if c["chars"] < CHARS_DE_LIVRO_COM_CAMADA:
            with fitz.open(c["pdf"]) as doc:
                tomar(c, scan_ouro.DEV, {scan_ouro.A_CONFERIR: folhas_pela_tinta(c["pdf"], doc, identidade)})
        else:
            achadas = folhas_do(identidade, c)
            assert achadas is not None, chave
            tomar(c, scan_ouro.DEV, achadas)

    fila = ouro.ordem_dos_livros(candidatos, SEMENTE)
    cedidos = []
    for split, cotas, so_nao_vistos in ((scan_ouro.TESTE, COTAS_DO_TESTE, True), (scan_ouro.DEV, COTAS_DO_DEV, False)):
        for producao, cota in cotas.items():
            tomados = 0
            for identidade in fila:
                c = candidatos[identidade]
                if tomados == cota:
                    break
                if c["producao"] != producao or (so_nao_vistos and c["visto"]) or not cabe(c):
                    continue
                achadas = folhas_do(identidade, c)
                if achadas is None:
                    cedidos.append(c["chave"])
                    continue
                tomar(c, split, achadas)
                tomados += 1
            assert tomados == cota, (split, producao, tomados, cota)

    livros, folhas = [], []
    alocacao = {}
    for c, _split, achadas in escolhidos:
        if scan_ouro.A_CONFERIR in achadas:
            continue
        p = len(achadas[ouro.PROSA])
        alocacao[c["chave"]] = [1, 2] if p >= 2 else [2, 1]
    for c, _split, achadas in escolhidos:
        if sum(m for m, _ in alocacao.values()) >= scan_ouro.FOLHAS_MINIMAS // 2:
            break
        if alocacao.get(c["chave"], [2, 1])[0] == 1 and len(achadas[ouro.MISTO]) >= 2:
            alocacao[c["chave"]] = [2, 1]
    for c, split, achadas in escolhidos:
        identidade = next(i for i, x in candidatos.items() if x is c)
        livros.append(scan_ouro.LivroDoScanOuro(
            identidade, split, c["lingua"], c["producao"], c["dpi"], c["grupo"], c["visto"], c["chave"] in OBRIGATORIOS,
        ))
        if scan_ouro.A_CONFERIR in achadas:
            pares = [(f, scan_ouro.A_CONFERIR) for f in achadas[scan_ouro.A_CONFERIR]]
        else:
            m, p = alocacao[c["chave"]]
            pares = [(f, ouro.MISTO) for f in achadas[ouro.MISTO][:m]] + [(f, ouro.PROSA) for f in achadas[ouro.PROSA][:p]]
        with fitz.open(c["pdf"]) as doc:
            for folha, conteudo in sorted(pares):
                folhas.append(scan_ouro.FolhaDoScanOuro(
                    identidade, folha, c["lingua"], c["producao"], conteudo, split, False, scan_ouro.sha_da_folha(doc, folha - 1),
                ))
    duplas: set[tuple[str, int]] = set()
    for producao in prata.ESTRATOS:
        for split in scan_ouro.SPLITS:
            desta = [f for f in folhas if f.producao == producao and f.split == split]
            desta.sort(key=lambda f: hashlib.sha256(f"dupla:{f.identidade}{f.folha}".encode()).hexdigest())
            duplas.add((desta[0].identidade, desta[0].folha))
    folhas = [
        scan_ouro.FolhaDoScanOuro(f.identidade, f.folha, f.lingua, f.producao, f.conteudo, f.split, (f.identidade, f.folha) in duplas, f.sha_folha)
        for f in folhas
    ]
    manifesto = scan_ouro.ScanOuro(
        scan_ouro.VERSAO, CONGELADO_EM, None, tuple(livros), tuple(folhas),
        {
            "semente": SEMENTE,
            "livros": "sha256(semente:identidade), por produção; livro visto não vai ao teste",
            "folhas": "sha256(identidade + folha), base 1, fora os 8% iniciais e finais",
            "conteudo": "ouro.estrato_do_texto sobre a camada de terceiro, com regua_prosa.classe_do_token; sem camada, a_conferir",
            "duplas": "sha256('dupla:' + identidade + folha), a primeira de cada produção em cada split",
            "cotas": {"teste": COTAS_DO_TESTE, "dev": COTAS_DO_DEV, "por_lingua": POR_LINGUA, "folhas_por_livro": FOLHAS_POR_LIVRO},
            "candidatos": len(candidatos),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16],
        },
    )
    erros = scan_ouro.problemas(manifesto)
    assert not erros, erros
    scan_ouro.gravar(manifesto, saida)
    print(f"# {len(candidatos)} candidatos; cederam a vaga: {sorted(set(cedidos))}")
    for livro in livros:
        print(f"{livro.identidade[:8]} {livro.split:5} {livro.lingua} {livro.producao:9} visto={livro.visto}")
    print({c: sum(f.conteudo == c for f in folhas) for c in scan_ouro.CONTEUDOS}, len(folhas), "folhas,", len(duplas), "duplas")


if __name__ == "__main__":
    main(sys.argv[1])
