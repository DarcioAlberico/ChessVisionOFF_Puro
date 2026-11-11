"""S-726: o modo bloco como variante da bancada, pareado contra a fusão, e a fusão sem Tesseract.

Porta 2 do cabeçalho de `text/bancada_prosa.py`. `_ler_pelo_leitor` não passa `modo_bloco`, e `modo_bloco=True` com um reconhecedor
sem leitor de linha é **silenciosamente** o glifo puro (`linhas_do_glifo` só constrói o RapidOCR quando `reconhecedor is None`):
por isso o reconhecedor do bloco é construído aqui, uma vez, com o mesmo `leitor_de_linha_padrao()` que a janela usaria.

**Só roda no commit medido (689132d6):** a S-726 tirou o parâmetro e `leitor_de_linha_padrao`. Fica porque é o que reproduz o número:

    git worktree add <fora> 689132d6
    PYTHONPATH=<fora>/src python medir_bloco.py --conjunto ouro --split dev --motor glifo,fusao,glifo_bloco,fusao_sem_tess --dados <fora do repo>/dev.jsonl
    PYTHONPATH=<fora>/src python medir_bloco.py --conjunto prata --motor glifo,fusao,glifo_bloco,fusao_sem_tess --dados <fora do repo>/prata.jsonl
    cvoff-texto-prosa --compilar <saída> --bloco ouro_dev=dev.jsonl --bloco prata=prata.jsonl --pares fusao-glifo_bloco,glifo-glifo_bloco,fusao_sem_tess-glifo
"""

from __future__ import annotations

import sys

from chess_diagram_ocr.cli import texto_prosa
from chess_diagram_ocr.text import bancada_prosa, leitor_de_linha, tesseract
from chess_diagram_ocr.text import regua_prosa as regua
from chess_diagram_ocr.text.leitor import leitor_de_linha_padrao, ler_pagina
from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

_com_rapid = None


def _reconhecedor_do_bloco():
    global _com_rapid
    if _com_rapid is None:
        rapid = leitor_de_linha_padrao()
        if rapid is None:
            raise SystemExit("sem RapidOCR não há modo bloco para medir")
        _com_rapid = build_glyph_recognizer(leitor_de_linha=rapid)
    return _com_rapid


def glifo_bloco(folha: bancada_prosa.FolhaEmMedida) -> str:
    pagina = ler_pagina(
        folha.pdf, folha.indice, motor="glifo", reconhecedor=_reconhecedor_do_bloco(), imagem_rgb=folha.imagem, dpi=folha.dpi,
        lingua=folha.lingua, reserva=folha.reserva, modo_bloco=True,
    )
    return regua.texto_das_linhas(ln.texto for ln in regua.linhas_da_pagina(pagina))


def fusao_sem_tess(folha: bancada_prosa.FolhaEmMedida) -> str:
    """A máquina sem Tesseract: o mesmo `motor="fusao"`, com o leitor que diz "não achei"."""
    ausente = leitor_de_linha.LeitorTesseract(tesseract.Motor(motivo="O Tesseract não foi encontrado nesta máquina."))
    pagina = ler_pagina(
        folha.pdf, folha.indice, motor="fusao", reconhecedor=folha.reconhecedor, imagem_rgb=folha.imagem, dpi=folha.dpi,
        lingua=folha.lingua, reserva=True, leitor_de_linha=ausente,
    )
    assert any(a.codigo for a in pagina.avisos), "sem Tesseract a folha tem de avisar"
    return regua.texto_das_linhas(ln.texto for ln in regua.linhas_da_pagina(pagina))


bancada_prosa.registrar_motor("glifo_bloco", glifo_bloco)
bancada_prosa.registrar_motor("fusao_sem_tess", fusao_sem_tess)

if __name__ == "__main__":
    raise SystemExit(texto_prosa.main(sys.argv[1:]))
