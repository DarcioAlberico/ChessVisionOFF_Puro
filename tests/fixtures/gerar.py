"""Gera as páginas de teste versionadas em `tests/fixtures/` (S-09).

    uv run python tests/fixtures/gerar.py

**Por que sintéticas, e não recortes do acervo.** A S-09 admitia as duas -- *"páginas PDF
pequenas construídas para teste (ou recortes com licença clara)"* -- e as duas razões de
escolher a primeira são fortes:

- **Peso.** Um tabuleiro de `data/samples/` é um PNG 800×800 de ~900 KB. Doze deles são 11 MB,
  contra o teto de 2 MB que a própria S-09 fixou. As páginas daqui são cor chapada e comprimem
  para poucos KB.
- **Licença.** `data/samples/`, `data/gallery/` e `data/review_cache/` estão fora do git porque
  descrevem o conteúdo de livros protegidos (ver `.gitignore` e a tabela de persistência do
  `ARCHITECTURE.md`). Versionar recortes deles seria distribuir o que o repositório existe para
  não distribuir.

**O que estas páginas cobrem, e o que elas não cobrem.** Elas são desenho geométrico: quadrados
alternados, borda, peças como glifos de alto contraste. Isso é o bastante para o **detector** e
para a **ordem de leitura**, que trabalham em geometria e contraste e é o que aqui se guarda.
Não é bastante para acurácia do modelo: o domínio é outro, e um número medido sobre isto não
descreveria o produto. Ver `test_fixtures.py` para onde essa fronteira está escrita.

O gerador é versionado junto com o que ele gera **para que o fixture seja reprodutível**: um
PNG no repositório sem a receita ao lado é um dado que ninguém pode conferir nem refazer.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

AQUI = Path(__file__).resolve().parent

PAGINA = (1400, 1000)
"""Altura e largura da página, em pixels. É a ordem de grandeza de uma página a 220 dpi
recortada, e a mesma que os testes de página em branco de `test_board_detection.py` usam."""

FUNDO = 255
CLARA, ESCURA = 235, 120
"""As duas cores da grade. O contraste entre elas é o sinal que `sem-contraste-de-casa`
procura (S-131); afastá-las mais tornaria o fixture mais fácil do que uma página impressa, e
aproximá-las o faria testar o limiar em vez do detector."""

BORDA = 3


def desenhar_tabuleiro(lado: int, placement: str) -> np.ndarray:
    """Um tabuleiro de `lado` px com as peças de `placement`, em tons de cinza sobre RGB.

    As peças são disco (claro) e disco com anel (escuro) -- não são imagens de peça, e não
    precisam ser: o que se testa aqui é achar o tabuleiro e cortá-lo em 64, e para isso a peça
    só precisa ocupar a casa de forma reconhecível por olho e por média de pixel.
    """
    casa = lado // 8
    imagem = np.full((lado, lado, 3), FUNDO, dtype=np.uint8)
    for linha in range(8):
        for coluna in range(8):
            cor = CLARA if (linha + coluna) % 2 == 0 else ESCURA
            y0, x0 = linha * casa, coluna * casa
            imagem[y0 : y0 + casa, x0 : x0 + casa] = cor

    for linha, fileira in enumerate(placement.split("/")):
        coluna = 0
        for caractere in fileira:
            if caractere.isdigit():
                coluna += int(caractere)
                continue
            centro = (coluna * casa + casa // 2, linha * casa + casa // 2)
            branca = caractere.isupper()
            cv2.circle(imagem, centro, casa // 3, (250, 250, 250) if branca else (20, 20, 20), -1)
            cv2.circle(imagem, centro, casa // 3, (20, 20, 20), 2)
            coluna += 1

    cv2.rectangle(imagem, (0, 0), (lado - 1, lado - 1), (0, 0, 0), BORDA)
    return imagem


def montar_pagina(tabuleiros: list[tuple[str, tuple[int, int, int]]]) -> np.ndarray:
    """Cola os tabuleiros numa página branca. Cada um é `(placement, (x, y, lado))`."""
    pagina = np.full((*PAGINA, 3), FUNDO, dtype=np.uint8)
    for placement, (x, y, lado) in tabuleiros:
        pagina[y : y + lado, x : x + lado] = desenhar_tabuleiro(lado, placement)
    return pagina


INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
FINAL = "8/8/4k3/8/8/4K3/8/8"
MEIO = "r3qr1k/pp3pbp/2pn4/7Q/3pP3/2NB3P/PPP3P1/R4RK1"
ESPARSO = "8/5k2/8/8/3Q4/8/2K5/8"

PAGINAS: dict[str, list[tuple[str, tuple[int, int, int]]]] = {
    # Um diagrama só, grande e centrado: o caso mínimo do detector.
    "um_diagrama": [(MEIO, (250, 400, 500))],
    # Dois por linha e dois por coluna: e o que separa `row` de `column` na ordem de leitura
    # (S-14). Os quatro tem lados diferentes de proposito -- pagina real nao tem diagrama do
    # mesmo tamanho, e um fixture que tivesse esconderia um prior de tamanho quebrado.
    "quatro_diagramas": [
        (INICIAL, (80, 120, 380)),
        (FINAL, (560, 140, 340)),
        (MEIO, (80, 700, 360)),
        (ESPARSO, (560, 720, 320)),
    ],
    # Um tabuleiro quase vazio: o caso em que o contraste medio da pagina cai e o detector
    # ainda tem de achar a grade.
    "diagrama_esparso": [(ESPARSO, (300, 500, 420))],
}


def main() -> int:
    esperado: dict[str, list[dict[str, object]]] = {}
    for nome, tabuleiros in PAGINAS.items():
        pagina = montar_pagina(tabuleiros)
        destino = AQUI / f"{nome}.png"
        cv2.imwrite(str(destino), cv2.cvtColor(pagina, cv2.COLOR_RGB2BGR))
        esperado[nome] = [
            {"placement": placement, "x": x, "y": y, "lado": lado}
            for placement, (x, y, lado) in tabuleiros
        ]
        print(f"{destino.name}: {destino.stat().st_size / 1024:.1f} KB, {len(tabuleiros)} diagrama(s)")

    manifesto = AQUI / "esperado.json"
    manifesto.write_text(
        json.dumps({"paginas": esperado}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{manifesto.name} gravado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
