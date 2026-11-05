"""A prosa da camada, nos livros em que a camada é a tinta (S-716).

**A recusa antiga era sobre notação, e não sobre prosa.** `leitor.py` não usa a camada como motor porque
ela não representa figurina. Na prosa de um livro nascido digital ela **é** o que o editor escreveu, e é a
referência do ouro. Rotear a prosa para ela e a notação para o glifo leva o erro de prosa a perto de zero,
sem Tesseract, sem instalador e sem custo de tempo.

**Quem decide se a folha serve é `admissao.py`**, sem motor nenhum. O perfil de livro do critério (a) --
30 folhas, só `get_texttrace` -- é calculado uma vez por documento aberto e fica em memória.

**(a)-(d) não bastam, e a auditoria da S-702 mostrou por quê.** Cinco de 27 livros admitidos têm camada que
não é a tinta. Na prosa, o defeito é a ligadura que perde letra: no *Chess Evolution 2013* o glifo `ft` da
*MyriadPro* está mapeado para `f`, e `after` sai `afer`. O que entrega a ligadura é a largura: aquele `f`
mede 0,523 do corpo, e os outros `f` da mesma fonte, 0,292. A palavra suspeita fica com o glifo. O mesmo
destino tem a palavra escrita em fonte de figurina, cujo código não é letra nenhuma.

**A ligadura mapeada direito não é suspeita, e a diferença está no caractere seguinte.** O `fi` do mesmo
livro mede os mesmos 0,523, mas a camada o escreve como `f` seguido de um `i` de largura **zero**: as duas
letras estão lá. Sem essa exceção, `first` ia ao glifo, que lê `frst`: o conserto criava o defeito.
"""

from __future__ import annotations

import statistics
import unicodedata
from collections import OrderedDict, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from . import admissao

Retangulo = tuple[float, float, float, float]

FOLGA_VERTICAL = 0.15
"""A caixa da linha do glifo crescida 15% na altura: ela é apertada à tinta, e a da camada, à fonte."""

LARGURA_DE_LIGADURA = 1.4
"""Uma letra mais larga que isto vezes a mediana dela, na mesma fonte e na mesma folha, é ligadura."""

MINIMO_PARA_A_MEDIANA = 3
"""Com menos ocorrências da letra na folha não há mediana, e a palavra não é acusada."""

VAO_DE_PALAVRA = 0.1
"""Em corpos da fonte. Um vão maior que isto entre duas letras é espaço que o PDF não escreveu: o do
*Chess Evolution* mede 1,76 pt em corpo 13, ou 0,135, e o par de letras mais largo fica abaixo de 0,05."""

_FAIXA_DE_BUSCA = 4
"""Pontos de altura de cada balde: a palavra só procura os caracteres da faixa dela."""

_PERFIS_EM_MEMORIA = 16


@dataclass(frozen=True)
class PalavraDaCamada:
    """Uma palavra da camada. `bloqueada` é a que não pode ser usada: ligadura, ou fonte de figurina."""

    texto: str
    bbox: Retangulo
    bloqueada: bool = False


def sem_ligadura(texto: str) -> str:
    """`ﬁ` vira `fi`. Só as formas de apresentação latinas: NFKC no texto inteiro mudaria `½` e `…`."""
    return "".join(unicodedata.normalize("NFKC", c) if "ﬀ" <= c <= "ﬆ" else c for c in texto)


@dataclass(frozen=True)
class _Caractere:
    """Um caractere do `get_texttrace`, com o que a palavra precisa saber dele."""

    letra: str
    x0: float
    y0: float
    x1: float
    y1: float
    corpo: float
    suspeito: bool


def _caracteres(pagina: Any) -> list[_Caractere]:
    """Todos os caracteres da folha que não são espaço, com a marca de quais não são o que dizem ser."""
    medidas: defaultdict[tuple[str, int], list[float]] = defaultdict(list)
    trechos = pagina.get_texttrace()
    for trecho in trechos:
        corpo = max(float(trecho.get("size", 0) or 0), 1e-3)
        for caractere in trecho.get("chars", ()):
            if caractere[0] > 32 and caractere[3][2] - caractere[3][0] > 1e-3:
                x0, _, x1, _ = caractere[3]
                medidas[(trecho.get("font", ""), caractere[0])].append((x1 - x0) / corpo)
    medianas = {k: statistics.median(v) for k, v in medidas.items() if len(v) >= MINIMO_PARA_A_MEDIANA}

    saida: list[_Caractere] = []
    for trecho in trechos:
        fonte = trecho.get("font", "") or ""
        corpo = max(float(trecho.get("size", 0) or 0), 1e-3)
        de_figurina = bool(admissao.FONTE_DE_FIGURINA.search(fonte) or admissao.FONTE_DE_DIAGRAMA.search(fonte))
        caracteres = trecho.get("chars", ())
        for posicao, caractere in enumerate(caracteres):
            codigo = caractere[0]
            if codigo <= 32:
                continue
            x0, y0, x1, y1 = caractere[3]
            mediana = medianas.get((fonte, codigo))
            seguinte = caracteres[posicao + 1] if posicao + 1 < len(caracteres) else None
            ligada = seguinte is not None and seguinte[3][2] - seguinte[3][0] <= 1e-3
            larga = mediana is not None and not ligada and (x1 - x0) / corpo > LARGURA_DE_LIGADURA * mediana
            # Na fonte de figurina só é suspeito o que não é figurina escrita em Unicode: o *Hertan* usa
            # `♕` de verdade, e esse código diz o que é.
            codigo_cego = de_figurina and not 0x2654 <= codigo <= 0x265F and not chr(codigo).isdigit()
            privado = bool(admissao.USO_PRIVADO.search(chr(codigo)))
            saida.append(
                _Caractere(chr(codigo), float(x0), float(y0), float(x1), float(y1), corpo, larga or codigo_cego or privado)
            )
    return saida


def palavras_da_folha(pagina: Any) -> list[PalavraDaCamada]:
    """As palavras da camada desta folha, em pontos, partidas onde a tinta tem vão.

    **O PDF não precisa escrever o espaço, e o `get_text("words")` só parte onde ele está escrito.** No
    *Chess Evolution* o espaço é um salto de posição: 1,76 pt entre duas letras, sem caractere nenhum, e
    saía um token de 52 letras colado. A palavra cuja lista de caracteres não fecha com o texto dela fica
    como veio, com a marca do que foi achado.
    """
    caracteres = _caracteres(pagina)
    por_faixa: defaultdict[int, list[_Caractere]] = defaultdict(list)
    for c in caracteres:
        por_faixa[int((c.y0 + c.y1) / 2) // _FAIXA_DE_BUSCA].append(c)

    palavras: list[PalavraDaCamada] = []
    for x0, y0, x1, y1, texto, *_ in pagina.get_text("words"):
        dentro = sorted(
            (
                c
                for faixa in range(int(y0) // _FAIXA_DE_BUSCA, int(y1) // _FAIXA_DE_BUSCA + 1)
                for c in por_faixa.get(faixa, ())
                if x0 <= (c.x0 + c.x1) / 2 <= x1 and y0 <= (c.y0 + c.y1) / 2 <= y1
            ),
            key=lambda c: c.x0,
        )
        pedacos: list[list[_Caractere]] = []
        for c in dentro:
            # **O maior fim já visto, e não o do caractere anterior**: a ligadura mapeada direito tem um
            # segundo caractere de largura zero, e medir dele partia `Aerofl|ot` e `Newslett|er`.
            if pedacos and c.x0 - max(d.x1 for d in pedacos[-1]) <= VAO_DE_PALAVRA * c.corpo:
                pedacos[-1].append(c)
            else:
                pedacos.append([c])
        if len(pedacos) > 1 and "".join(c.letra for c in dentro) == "".join(texto.split()):
            for pedaco in pedacos:
                palavras.append(
                    PalavraDaCamada(
                        sem_ligadura("".join(c.letra for c in pedaco)),
                        (pedaco[0].x0, min(c.y0 for c in pedaco), pedaco[-1].x1, max(c.y1 for c in pedaco)),
                        any(c.suspeito for c in pedaco),
                    )
                )
            continue
        bloqueada = any(c.suspeito for c in dentro)
        # A camada separa token com espaço fino dentro da "palavra" (`(2546)\u2009—\u2009Macedo,M`). O
        # roteador parte por espaço de qualquer tipo; quem parte aqui é para a marca ir com cada pedaço.
        for pedaco_de_texto in sem_ligadura(texto).split():
            palavras.append(PalavraDaCamada(pedaco_de_texto, (float(x0), float(y0), float(x1), float(y1)), bloqueada))
    return palavras


def caracteres_fora(pagina: Any, retangulos: Sequence[Retangulo]) -> int:
    """Quantos caracteres a camada tem fora dos diagramas: o segundo sinal de perda parcial (S-710)."""
    return sum(
        len("".join(palavra[4].split()))
        for palavra in pagina.get_text("words")
        if not admissao.dentro_de_algum(tuple(palavra[:4]), retangulos)
    )


def por_linha(
    caixas: Sequence[Retangulo],
    palavras: Sequence[PalavraDaCamada],
) -> tuple[list[list[PalavraDaCamada]], list[PalavraDaCamada]]:
    """Cada palavra na linha do glifo que contém o centro dela, em ordem de x; e as que não caíram em nenhuma.

    A caixa cresce 15% na vertical. Quando duas linhas a contêm, vale a de centro mais próximo: a palavra
    entra numa só, e não aparece duas vezes.
    """
    linhas: list[list[PalavraDaCamada]] = [[] for _ in caixas]
    fora: list[PalavraDaCamada] = []
    for palavra in palavras:
        cx = (palavra.bbox[0] + palavra.bbox[2]) / 2
        cy = (palavra.bbox[1] + palavra.bbox[3]) / 2
        melhor, distancia = -1, float("inf")
        for n, (x0, y0, x1, y1) in enumerate(caixas):
            folga = (y1 - y0) * FOLGA_VERTICAL
            if x0 <= cx <= x1 and y0 - folga <= cy <= y1 + folga and abs(cy - (y0 + y1) / 2) < distancia:
                melhor, distancia = n, abs(cy - (y0 + y1) / 2)
        if melhor < 0:
            fora.append(palavra)
        else:
            linhas[melhor].append(palavra)
    for linha in linhas:
        linha.sort(key=lambda p: p.bbox[0])
    return linhas, fora


_perfis: OrderedDict[tuple[str, int], admissao.PerfilDoLivro] = OrderedDict()


def perfil_em_memoria(documento: Any) -> admissao.PerfilDoLivro:
    """O perfil do livro, uma vez por documento: ~30 `get_texttrace` não cabem em toda folha lida."""
    chave = (str(getattr(documento, "name", "") or id(documento)), int(documento.page_count))
    if chave in _perfis:
        _perfis.move_to_end(chave)
        return _perfis[chave]
    perfil = admissao.perfil_do_livro(documento)
    _perfis[chave] = perfil
    while len(_perfis) > _PERFIS_EM_MEMORIA:
        _perfis.popitem(last=False)
    return perfil


MOTIVOS_DA_RECUSA: dict[str, str] = {
    admissao.PRODUTOR: "o PDF saiu de um programa de OCR",
    admissao.FONTE: "as fontes são as de um programa de OCR",
    admissao.LIVRO_DE_SCAN: "o livro é um scan com camada invisível",
    admissao.INVISIVEL: "a camada desta folha é invisível",
    admissao.COBERTO: "uma imagem cobre a camada nesta folha",
    admissao.LIXO: "a camada tem código de fonte no lugar de figurina",
    admissao.FILEIRA_FORA: "a camada desenha um tabuleiro em fonte fora do diagrama",
}
"""A frase de cada critério da admissão, para o selo: quem lê a folha não sabe o que é `d:produtor`."""


def admitir(documento: Any, indice: int, retangulos: Sequence[Retangulo]) -> admissao.Admissao:
    """A folha `indice` entra? Retângulos de diagrama em pontos."""
    return admissao.admitir_folha(
        documento[indice],
        retangulos,
        produtor=admissao.produtor_de(documento),
        perfil=perfil_em_memoria(documento),
    )


__all__ = [
    "FOLGA_VERTICAL",
    "LARGURA_DE_LIGADURA",
    "MINIMO_PARA_A_MEDIANA",
    "MOTIVOS_DA_RECUSA",
    "VAO_DE_PALAVRA",
    "PalavraDaCamada",
    "admitir",
    "caracteres_fora",
    "palavras_da_folha",
    "perfil_em_memoria",
    "por_linha",
    "sem_ligadura",
]
