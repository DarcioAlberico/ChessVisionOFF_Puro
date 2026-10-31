"""Admissão de folha ao ouro, sem rodar OCR nenhum: a camada só é referência quando é a tinta (S-702).

**A pergunta é sobre o PDF, não sobre um leitor.** A primeira regra proposta ("o Tesseract nas caixas
da camada erra ≤ 2%") foi reprovada porque dependia do motor avaliado e das caixas: no *Koblenz* p. 14
esse oráculo errava 19% e o Tesseract nas caixas do glifo 2,8%. Aqui só se olham o produtor, as
fontes, o modo de renderização, a ordem de desenho e a geometria dos trechos -- nada que um motor
melhor ou pior mude.

Os quatro critérios, na ordem em que reprovam:

- **(d) o PDF não é produção de OCR.** Produtor `Paper Capture`, `Image Conversion`, `FineReader`,
  `OmniPage`, `Omniscan`, `Google`, ABBYY, ou fontes `GlyphLessFont`, `HiddenHorzOCR`, `Fd\\d+`. O
  ClearScan **parece** digital -- o glifo é vetorizado --, mas o Unicode dele veio de um OCR.
- **(a) o texto é visível e é a tinta.** Nenhum trecho fora dos diagramas em modo de renderização 3 ou
  opacidade 0; nenhuma imagem de página inteira desenhada **depois** de algum texto (a de fundo,
  desenhada antes, como no *Chess Evolution*, não reprova); e o **livro** não é scan com camada
  invisível. Esta última é decidida por livro, num perfil de 30 folhas igualmente espaçadas: se mais
  da metade das que têm texto têm texto invisível, o livro inteiro sai. É o que recusa a folha de
  carimbo do *Kemeri* -- texto visível sobre o scan. A primeira redação decidia isso por folha
  ("menos de 200 caracteres sobre imagem de página inteira") e recusava ao menos 120 folhas de
  solução dos *Chess Evolution*.
- **(c) sem lixo de figurina.** Nenhum caractere de uso privado em fonte de **texto** (em fonte de
  figurina ele é a figurina) e nenhum dos padrões que a camada de terceiro deixa (`l:l'`, `'ii'`,
  `.tg`).
- **(b) nenhuma fileira de tabuleiro fora dos diagramas.** Seis ou mais caracteres em fonte de
  diagrama, na mesma linha de base, cada um encostado no anterior (vão menor que meia altura), fora
  dos retângulos de diagrama crescidos de uma casa. O desenho do tabuleiro em fonte **dentro** do
  retângulo (o Dvoretsky tem 64 trechos por diagrama em `Chess-Merida`) sai da referência e não
  reprova; um caractere solto nessa fonte fora do diagrama é figurina. A primeira redação ("nenhum
  trecho em fonte de diagrama") derrubava o Dvoretsky inteiro. A fonte de diagrama é reconhecida
  **pelo nome**: a do Seirawan (`TTE…`, embutida sem nome) não é, e ali só o retângulo protege.

A auditoria visual de 20 linhas por livro, que a S-702 também exige, é de gente ou de um agente que
não seja o executor, e não mora aqui.

Este módulo lê `page.get_texttrace()` e `page.get_bboxlog()` por conta própria, e não pelo
`pdf_text.py`: aquele está no digest da S-218, e mexer nele invalidaria os quatro relatórios de campo.
O PyMuPDF é importado dentro das funções, como no resto de `text/`. Os retângulos de diagrama
entram de fora: a S-716 tem os do glifo, e o sorteio da S-702 os pega da montagem da camada.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

VERSAO = 1
"""Sobe quando um critério muda: o manifesto do ouro grava a versão com que admitiu cada folha."""

FOLHAS_DE_PERFIL = 30
FILEIRA = 6
"""Caracteres encostados de fonte de diagrama, na mesma linha de base, que fazem uma fileira de
tabuleiro. Uma figurina é um; um lance com figurina e captura, dois ou três."""

FRACAO_DE_IMAGEM_CHEIA = 0.6
"""Uma imagem cobre a folha quando a área dela passa disto da área da página."""

PRODUTOR_DE_OCR = re.compile(r"paper capture|image conversion|finereader|omnipage|omniscan|google|abbyy", re.I)
FONTE_DE_OCR = re.compile(r"glyphlessfont|hiddenhorzocr|^fd\d+", re.I)
FONTE_DE_DIAGRAMA = re.compile(r"merida|diagram|alpha|leipzig|kingdom|chess-?berlin|usualchess|linares", re.I)
"""O protótipo listava também `skaknew-diagram`, `diagramtt` e `chessalpha`, que `diagram` e `alpha` já
cobrem: saíram para cada alternativa que fica ter um teste que a pegue sozinha."""
FONTE_DE_FIGURINA = re.compile(r"figurine|merida|skak|chess|alpha|leipzig|segoe ui symbol|ms gothic", re.I)
LIXO_DE_FIGURINA = re.compile(r"l:l'|'ii'|\.tg")
"""O ponto de `.tg` é literal: sem ele, `Stuttgart` e `outgoing` seriam lixo."""
USO_PRIVADO = re.compile("[-]")

PRODUTOR = "d:produtor"
FONTE = "d:fonte"
LIVRO_DE_SCAN = "a:livro_de_scan"
INVISIVEL = "a:invisivel"
COBERTO = "a:coberto_por_imagem"
LIXO = "c:lixo"
FILEIRA_FORA = "b:fileira_fora"
SEM_TEXTO = "sem_texto"
CRITERIOS = (PRODUTOR, LIVRO_DE_SCAN, FONTE, INVISIVEL, LIXO, FILEIRA_FORA, COBERTO, SEM_TEXTO)
"""Por que uma folha não entra, na ordem em que se decide. `sem_texto` não é defeito do PDF: é capa,
branco ou folha só de diagrama, onde não há prosa a medir."""

Retangulo = tuple[float, float, float, float]


@dataclass(frozen=True)
class Trecho:
    """Um trecho do `get_texttrace`, só com o que a admissão olha."""

    fonte: str
    texto: str
    bbox: Retangulo
    caixas: tuple[Retangulo, ...] = ()
    """As caixas de cada caractere imprimível, para achar a fileira."""
    invisivel: bool = False


@dataclass(frozen=True)
class PerfilDoLivro:
    """O critério (a) de livro: quantas folhas do perfil têm texto, e quantas têm texto invisível."""

    com_texto: int
    invisiveis: int

    @property
    def de_scan(self) -> bool:
        return self.com_texto > 0 and self.invisiveis > self.com_texto / 2


@dataclass(frozen=True)
class Admissao:
    """O veredito de uma folha. `criterio` é `None` quando ela entra."""

    criterio: str | None
    trechos_fora: int = 0
    """Trechos com texto fora dos retângulos de diagrama."""
    fonte_de_diagrama_dentro: int = 0
    maior_fileira_fora: int = 0

    @property
    def admitida(self) -> bool:
        return self.criterio is None


def maior_fileira(caixas: Iterable[Retangulo]) -> int:
    """A maior sequência de caracteres na mesma linha de base, cada um encostado no anterior.

    Duas caixas estão na mesma linha quando a base delas difere menos de um quarto da altura; estão
    encostadas quando o vão entre elas é menor que meia altura. É assim que uma linha do tabuleiro
    desenhado em fonte se distingue de uma figurina solta no meio de um lance.
    """
    melhor = 0
    linhas: list[list[tuple[float, float, float, float]]] = []
    for x0, y0, x1, y1 in sorted(caixas, key=lambda c: c[3]):
        altura = max(y1 - y0, 1e-3)
        if linhas and abs(y1 - linhas[-1][-1][3]) < altura / 4:
            linhas[-1].append((x0, x1, altura, y1))
        else:
            linhas.append([(x0, x1, altura, y1)])
    for linha in linhas:
        linha.sort()
        corrida, fim = 0, None
        for x0, x1, altura, _ in linha:
            corrida = corrida + 1 if fim is not None and x0 - fim < altura / 2 else 1
            fim = x1
            melhor = max(melhor, corrida)
    return melhor


def folga_de(retangulo: Retangulo) -> float:
    """Uma casa do tabuleiro: um oitavo da largura do retângulo de diagrama, para cada lado."""
    return (retangulo[2] - retangulo[0]) / 8


def dentro_de_algum(bbox: Retangulo, retangulos: Sequence[Retangulo]) -> bool:
    """O centro do trecho cai em algum dos retângulos de diagrama, crescido de uma casa (`folga_de`)?"""
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    for x0, y0, x1, y1 in retangulos:
        folga = folga_de((x0, y0, x1, y1))
        if x0 - folga <= cx <= x1 + folga and y0 - folga <= cy <= y1 + folga:
            return True
    return False


def decidir(
    trechos: Sequence[Trecho],
    retangulos: Sequence[Retangulo],
    *,
    produtor: str = "",
    perfil: PerfilDoLivro | None = None,
    imagem_cobre_texto: bool = False,
) -> Admissao:
    """A admissão de uma folha a partir do que já foi extraído dela. Pura: é o que os testes exercitam."""
    criterio: str | None = None
    if PRODUTOR_DE_OCR.search(produtor or ""):
        criterio = PRODUTOR
    elif perfil is not None and perfil.de_scan:
        criterio = LIVRO_DE_SCAN
    fora = dentro_diagrama = 0
    caixas_de_diagrama: list[Retangulo] = []
    for trecho in trechos:
        if not trecho.texto.strip():
            continue
        e_de_diagrama = bool(FONTE_DE_DIAGRAMA.search(trecho.fonte))
        if dentro_de_algum(trecho.bbox, retangulos):
            dentro_diagrama += e_de_diagrama
            continue
        fora += 1
        if e_de_diagrama:
            caixas_de_diagrama.extend(trecho.caixas)
        if criterio is None and FONTE_DE_OCR.search(trecho.fonte):
            criterio = FONTE
        if criterio is None and trecho.invisivel:
            criterio = INVISIVEL
        if criterio is None and (
            LIXO_DE_FIGURINA.search(trecho.texto)
            or (USO_PRIVADO.search(trecho.texto) and not FONTE_DE_FIGURINA.search(trecho.fonte))
        ):
            criterio = LIXO
    fileira = maior_fileira(caixas_de_diagrama)
    if criterio is None and fileira >= FILEIRA:
        criterio = FILEIRA_FORA
    if criterio is None and imagem_cobre_texto and fora:
        criterio = COBERTO
    if criterio is None and fora == 0:
        criterio = SEM_TEXTO
    return Admissao(criterio, trechos_fora=fora, fonte_de_diagrama_dentro=dentro_diagrama, maior_fileira_fora=fileira)


def trechos_da_folha(pagina: Any) -> list[Trecho]:
    """Os trechos de texto de uma `fitz.Page`, pelo `get_texttrace`."""
    trechos = []
    for bruto in pagina.get_texttrace():
        chars = bruto.get("chars", ())
        texto = "".join(chr(c[0]) for c in chars if c[0] > 0)
        trechos.append(
            Trecho(
                fonte=bruto.get("font", "") or "",
                texto=texto,
                bbox=tuple(bruto.get("bbox", (0, 0, 0, 0))),
                caixas=tuple(tuple(c[3]) for c in chars if c[0] > 32),
                invisivel=bruto.get("type", 0) == 3 or bruto.get("opacity", 1) == 0,
            )
        )
    return trechos


def imagem_cobre_texto(pagina: Any) -> bool:
    """Alguma imagem de página inteira é desenhada **depois** de algum texto?"""
    import fitz

    area = pagina.rect.width * pagina.rect.height
    texto_antes = False
    for tipo, ret in pagina.get_bboxlog():
        if "text" in tipo:
            texto_antes = True
        elif "image" in tipo and texto_antes:
            r = fitz.Rect(ret)
            if r.width * r.height > FRACAO_DE_IMAGEM_CHEIA * area:
                return True
    return False


def tem_texto_invisivel(pagina: Any) -> tuple[bool, bool]:
    """(a folha tem texto, a folha tem texto invisível) -- sem olhar diagrama: é o perfil do livro."""
    texto = False
    for trecho in trechos_da_folha(pagina):
        if not trecho.texto.strip():
            continue
        texto = True
        if trecho.invisivel:
            return True, True
    return texto, False


def folhas_do_perfil(n_folhas: int) -> list[int]:
    """As 30 folhas igualmente espaçadas, fixas pelo número de páginas (índice 0)."""
    if n_folhas <= 0:
        return []
    return sorted({round(i * (n_folhas - 1) / (FOLHAS_DE_PERFIL - 1)) for i in range(FOLHAS_DE_PERFIL)})


def perfil_do_livro(documento: Any) -> PerfilDoLivro:
    """O perfil de uma `fitz.Document`. Calcula-se uma vez por documento aberto."""
    com_texto = invisiveis = 0
    for indice in folhas_do_perfil(documento.page_count):
        texto, invisivel = tem_texto_invisivel(documento[indice])
        com_texto += texto
        invisiveis += invisivel
    return PerfilDoLivro(com_texto, invisiveis)


def produtor_de(documento: Any) -> str:
    return ((documento.metadata or {}).get("producer") or "").strip()


def admitir_folha(
    pagina: Any,
    retangulos: Sequence[Retangulo],
    *,
    produtor: str = "",
    perfil: PerfilDoLivro | None = None,
) -> Admissao:
    """A admissão de uma `fitz.Page`, com os retângulos de diagrama em pontos do PDF."""
    return decidir(
        trechos_da_folha(pagina),
        retangulos,
        produtor=produtor,
        perfil=perfil,
        imagem_cobre_texto=imagem_cobre_texto(pagina),
    )
