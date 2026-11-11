"""O que as alternativas do Tesseract acrescentam ao dígito forçado (S-729): `lstm_choice_mode=2`, que só sai no hOCR.

    alternativas.py <ouro|prata> [limite_segundos]

Para cada palavra com forma de lance que a gramática não aceita, e que o mapa de homóglifos não resolve, pergunta se trocar
**um** caractere por uma das alternativas dá um lance aceito. Só contagens saem daqui.
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter

from chess_diagram_ocr.cli.texto_prosa import _achar_livros, _pastas_padrao, folhas_do_conjunto
from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text import arbitro, leitor, notacao, tesseract
from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

_PALAVRA = re.compile(r"<span class='ocrx_word'[^>]*>(.*?)(?=<span class='ocrx_word'|</span>\s*</span>\s*</p>|\Z)", re.S)
_ESCOLHAS = re.compile(r"id='lstm_choices_[^']*'>(.*?)</span></span>|id='lstm_choices_[^']*'>(.*?)</span>\s*</span>", re.S)
_ESCOLHA = re.compile(r"title='x_confs ([\d.]+)'>([^<]*)</span>")


def palavras_do_hocr(hocr: str) -> list[list[list[tuple[str, float]]]]:
    """Por palavra, por posição, `(caractere, confiança)`, a primeira sendo a lida."""
    saida = []
    for bloco in hocr.split("class='ocrx_word'")[1:]:
        posicoes = []
        for grupo in bloco.split("id='lstm_choices_")[1:]:
            opcoes = [(c, float(n)) for n, c in _ESCOLHA.findall(grupo)]
            # O espaço que o LSTM põe antes da palavra é uma posição como outra no hOCR, e não é letra.
            if opcoes and opcoes[0][0].strip():
                posicoes.append(opcoes)
        saida.append(posicoes)
    return saida


def main() -> int:
    conjunto = sys.argv[1]
    limite = float(sys.argv[2]) if len(sys.argv) > 2 else 150.0
    folhas = folhas_do_conjunto(conjunto, "dev" if conjunto == "ouro" else "")
    achados = _achar_livros(folhas, _pastas_padrao(__import__("os").environ.get("CVOFF_RAIZ", "")))
    rec = build_glyph_recognizer()
    motor = tesseract.achar_motor()
    conta = Counter()
    exemplos = Counter()
    t0 = time.perf_counter()
    for f in folhas:
        if time.perf_counter() - t0 > limite:
            print("parou pelo limite", conta["folhas"])
            break
        pdf = str(achados[f.identidade])
        imagem = render_pdf_page(pdf, f.folha - 1, 220)
        escala = 220 / 72
        from chess_diagram_ocr.detection.hybrid import detect_diagrams_in_pdf_page

        ret = [tuple(v * escala for v in c.bbox_pdf) for c in detect_diagrams_in_pdf_page(pdf, f.folha - 1, imagem)]
        cruas, _ = leitor.linhas_do_glifo(imagem, ret, reconhecedor=rec, dpi=220)
        recortes = [leitor._recorte_de_linha(imagem, c.caixa, escala) for c in cruas if notacao.e_linha_de_notacao(c.texto)]  # noqa: SLF001
        recortes = [r for r in recortes if r.size]
        if not recortes:
            continue
        conta["folhas"] += 1
        hocr = tesseract.rodar(
            motor, tesseract._tiff_de(recortes), lingua=f.lingua, dpi=220, psm=7, timeout=60.0,  # noqa: SLF001
            opcoes=("-c", "lstm_choice_mode=2"), formato="hocr",
        )
        for posicoes in palavras_do_hocr(hocr):
            lida = "".join(p[0][0] for p in posicoes)
            conta["palavras"] += 1
            if arbitro.e_estrita(lida) or not re.search(r"[a-h]", lida) or not re.search(r"[0-9]|^[A-Z][a-h]", lida) or len(lida) > 9:
                continue
            conta["com_forma_de_lance_e_invalidas"] += 1
            novo, forma = arbitro.forcado(lida)
            if forma and arbitro.e_estrita(novo):
                conta["resolvidas_pelo_mapa"] += 1
                continue
            achou = False
            for i, opcoes in enumerate(posicoes):
                for c, _conf in opcoes[1:]:
                    tentativa = lida[:i] + c + lida[i + 1 :]
                    if c.strip() and arbitro.e_estrita(tentativa):
                        achou = True
                        # O que a S-729 pede é o dígito. A letra de peça trocada (`Hb4` -> `Bb4` ou `Kb4`) é a figurina, que é do glifo.
                        if c.isdigit():
                            conta["das_quais_trocam_um_digito"] += 1
                            exemplos[(lida, tentativa)] += 1
                        break
                if achou:
                    break
            conta["resolvidas_so_pelas_alternativas" if achou else "sem_resolver"] += 1
    print(dict(conta))
    print(exemplos.most_common(25))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
