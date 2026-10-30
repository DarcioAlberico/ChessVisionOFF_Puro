"""Admissão de folha ao ouro e à S-716 (prosa da camada), sem rodar OCR nenhum.

Critérios (roadmap, S-702), por folha:
  (d) o PDF não é produção de OCR: produtor e fontes;
  (a) todo trecho de texto FORA dos diagramas é visível (tipo != 3 no texttrace, opacidade > 0) e não
      está COBERTO por imagem de página inteira -- coberto quer dizer desenhada DEPOIS do texto, pela
      ordem do `get_bboxlog`; imagem de fundo desenhada antes (o Chess Evolution) não reprova. E o LIVRO
      não é scan com camada invisível: se mais da metade das folhas de perfil (30, igualmente espaçadas,
      fixas pelo número de páginas) que têm texto têm texto invisível, o livro inteiro sai. É isto que
      recusa a folha de carimbo do Kemeri -- texto visível sobre o scan. A primeira redação usava "menos
      de 200 caracteres sobre imagem de página inteira" por folha, e recusava folhas de solução do
      Chess Evolution (rodada 10);
  (b) nenhuma FILEIRA de tabuleiro em fonte de diagrama fora dos retângulos de diagrama (crescidos de
      uma casa): 6 ou mais caracteres de fonte de diagrama na mesma linha de base, encostados (vão menor
      que meia altura). Um caractere solto nessa fonte é figurina -- notação, vai ao glifo e não reprova.
      Texto em fonte de diagrama DENTRO do retângulo é o desenho do tabuleiro: sai da referência e não
      reprova a folha (a primeira redação reprovava, e derrubava todo o Dvoretsky -- rodada 10);
  (c) nenhum lixo de figurina conhecido (`l:l'`, `'ii'`, `.tg`) e nenhum caractere de uso privado em
      fonte de TEXTO fora dos diagramas (uso privado em fonte de figurina é a figurina, e é notação).

Cada livro tem a sua semente (sha256 de "20261030:" + nome do arquivo): a amostra de um livro não
depende de que outros livros estão na mesma corrida, nem da ordem deles.

Uso: admissao.py [--sem-retangulos] <saida.tsv> <n_folhas_por_livro | todas | INI-FIM> <pdf> [<pdf> ...]
  --sem-retangulos  ignora os diagramas achados -- prova de que o (b) dispara (falsificação)
"""
import hashlib
import os
import random
import re
import sys

RAIZ = os.environ.get("CVOFF_RAIZ", r"C:\Python-Chess2\ChessVisionOFF_Puro")
SEMENTE = "20261030"
PRODUTOR_OCR = re.compile(r"paper capture|image conversion|finereader|omnipage|omniscan|google|abbyy", re.I)
FONTE_OCR = re.compile(r"glyphlessfont|hiddenhorzocr|^fd\d+", re.I)
FONTE_DIAGRAMA = re.compile(r"merida|diagram|alpha|leipzig|kingdom|chess-?berlin|skaknew-diagram|"
                            r"diagramtt|usualchess|chessalpha|linares", re.I)
LIXO = re.compile(r"l:l'|'ii'|\.tg")
USO_PRIVADO = re.compile("[\ue000-\uf8ff]")
FONTE_FIGURINA = re.compile(r"figurine|merida|skak|chess|alpha|leipzig|segoe ui symbol|ms gothic", re.I)
FILEIRA = 6       # caracteres encostados de fonte de diagrama que fazem uma fileira de tabuleiro
FOLHAS_DE_PERFIL = 30


def dentro(b, rets, folga):
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return any(r[0] - folga[i] <= cx <= r[2] + folga[i] and r[1] - folga[i] <= cy <= r[3] + folga[i]
               for i, r in enumerate(rets))


def maior_fileira(caixas) -> int:
    """Maior sequência de caracteres na mesma linha de base, cada um encostado no anterior."""
    melhor = 0
    linhas: list[list] = []
    for x0, y0, x1, y1 in sorted(caixas, key=lambda c: c[3]):
        h = max(y1 - y0, 1e-3)
        if linhas and abs(y1 - linhas[-1][-1][3]) < h / 4:
            linhas[-1].append((x0, x1, h, y1))
        else:
            linhas.append([(x0, x1, h, y1)])
    for cs in linhas:
        cs.sort()
        corrida, fim = 0, None
        for x0, x1, h, _ in cs:
            corrida = corrida + 1 if fim is not None and x0 - fim < h / 2 else 1
            fim = x1
            melhor = max(melhor, corrida)
    return melhor


def tem_invisivel(pg) -> tuple[bool, bool]:
    """(tem texto, tem texto invisível) -- sem olhar diagrama: serve ao perfil do livro."""
    texto = invisivel = False
    for tr in pg.get_texttrace():
        if not "".join(chr(c[0]) for c in tr.get("chars", ()) if c[0] > 0).strip():
            continue
        texto = True
        if tr.get("type", 0) == 3 or tr.get("opacity", 1) == 0:
            invisivel = True
            break
    return texto, invisivel


def perfil_do_livro(doc) -> tuple[int, int]:
    """(folhas de perfil com texto, folhas de perfil com texto invisível)."""
    n = doc.page_count
    perfil = sorted({round(i * (n - 1) / (FOLHAS_DE_PERFIL - 1)) for i in range(FOLHAS_DE_PERFIL)})
    com_texto = invisiveis = 0
    for i in perfil:
        texto, invisivel = tem_invisivel(doc[i])
        com_texto += texto
        invisiveis += invisivel
    return com_texto, invisiveis


def livro_de_scan(doc) -> bool:
    com_texto, invisiveis = perfil_do_livro(doc)
    return com_texto > 0 and invisiveis > com_texto / 2


def avaliar(pdf, doc, idx, produtor, scan, sem_retangulos=False):
    import fitz

    from chess_diagram_ocr.text.leitor import ler_pagina

    pg = doc[idx]
    motivo = "d:produtor" if PRODUTOR_OCR.search(produtor) else ("a:livro_de_scan" if scan else "")
    area = pg.rect.width * pg.rect.height
    texto_antes = img_cheia = False  # imagem de página inteira desenhada DEPOIS de algum texto
    for tipo, ret in pg.get_bboxlog():
        if "text" in tipo:
            texto_antes = True
        elif "image" in tipo and fitz.Rect(ret).width * fitz.Rect(ret).height > 0.6 * area:
            img_cheia = img_cheia or texto_antes
    rets = []
    if not sem_retangulos:
        try:
            rets = [d.bbox for d in ler_pagina(pdf, idx, motor="camada").diagramas]
        except Exception:  # noqa: BLE001 -- folha que o leitor recusa fica sem retângulo
            rets = []
    folga = [(r[2] - r[0]) / 8 for r in rets]
    n_tr = dentro_diag = 0
    caixas_diagrama = []
    for tr in pg.get_texttrace():
        fonte = tr.get("font", "") or ""
        texto = "".join(chr(c[0]) for c in tr.get("chars", ()) if c[0] > 0)
        if not texto.strip():
            continue
        if dentro(tr.get("bbox", (0, 0, 0, 0)), rets, folga):
            dentro_diag += bool(FONTE_DIAGRAMA.search(fonte))
            continue
        n_tr += 1
        if FONTE_DIAGRAMA.search(fonte):
            caixas_diagrama.extend(c[3] for c in tr.get("chars", ()) if c[0] > 32)
        if not motivo and FONTE_OCR.search(fonte):
            motivo = "d:fonte"
        if not motivo and (tr.get("type", 0) == 3 or tr.get("opacity", 1) == 0):
            motivo = "a:invisivel"
        if not motivo and (LIXO.search(texto) or (USO_PRIVADO.search(texto) and not FONTE_FIGURINA.search(fonte))):
            motivo = "c:lixo"
    fileira = maior_fileira(caixas_diagrama)
    if not motivo and fileira >= FILEIRA:
        motivo = "b:fileira_fora"
    if not motivo and img_cheia and n_tr:
        motivo = "a:coberto_por_imagem"
    if not motivo and n_tr == 0:
        motivo = "sem_texto"
    return motivo, n_tr, dentro_diag, fileira


def main(argv):
    import fitz

    sem_retangulos = "--sem-retangulos" in argv
    argv = [a for a in argv if a != "--sem-retangulos"]
    sai, n, *pdfs = argv
    with open(sai, "w", encoding="utf-8") as f:
        f.write("livro\tfolha\tadmitida\tmotivo\ttrechos\tfonte_diagrama_dentro\tmaior_fileira_fora\t"
                "perfil_com_texto\tperfil_invisivel\n")
        for nome in pdfs:
            pdf = nome if os.path.isabs(nome) else os.path.join(RAIZ, "PDF", nome)
            base = os.path.basename(pdf)
            doc = fitz.open(pdf)
            produtor = (doc.metadata or {}).get("producer", "") or ""
            com_texto, invisiveis = perfil_do_livro(doc)
            scan = com_texto > 0 and invisiveis > com_texto / 2
            rnd = random.Random(int(hashlib.sha256(f"{SEMENTE}:{base}".encode()).hexdigest()[:16], 16))
            if n == "todas":
                folhas = range(doc.page_count)
            elif "-" in n:  # faixa de folhas, base 1, inclusiva: para dividir o livro inteiro em processos
                ini, fim = (int(x) for x in n.split("-"))
                folhas = range(ini - 1, min(fim, doc.page_count))
            else:
                folhas = rnd.sample(range(doc.page_count), min(int(n), doc.page_count))
            for idx in sorted(folhas):
                motivo, n_tr, dentro_diag, fileira = avaliar(pdf, doc, idx, produtor, scan, sem_retangulos)
                f.write(f"{base[:40]}\t{idx + 1}\t{int(not motivo)}\t{motivo or '-'}\t{n_tr}\t{dentro_diag}\t{fileira}"
                        f"\t{com_texto}\t{invisiveis}\n")
                f.flush()


if __name__ == "__main__":
    main(sys.argv[1:])
