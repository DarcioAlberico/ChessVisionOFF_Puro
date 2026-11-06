"""Quanto vale cada palavra da linha fundida: a confiança calibrada por domínio (S-760).

**Com ~99% de palavras certas, uma confiança constante já cumpre "ECE baixo".** Por isso a régua aqui são duas: o `ece_por_faixa`, em que
toda faixa vale o mesmo, e a curva risco-cobertura, que diz quanto erro sobra aceitando sem revisão as N% de cima. A S-189 respondia com
`max`/`min` de duas confianças de escalas diferentes: a do glifo calibrada, e a do TSV do Tesseract, crua. Na linha fundida ela nem chegava a
rodar: a linha carregava a confiança do glifo, pintada sobre o texto de outro motor.

**O calibrador é uma regressão logística sobre o que o token já traz**: quem o escreveu, a confiança de quem o escreveu, se o outro leitor
discordou e o quanto, se a palavra existe na língua do livro, e a forma dela. O resto da linha e da folha foi medido, e não paga. **Nenhum texto de livro
entra nos coeficientes**, e `docs/metrics/texto_confianca_2026-11-06/ajustar.py` os refaz a partir do pedaço reservado do dev: a Fase 105 não
vai começar (D8), e o roadmap prevê esse recuo.

**Dois domínios, os dois estratos da fusão:** `digital` para a regra v5, `scan` para a v3. O erro não se distribui igual: no scan a
discordância é a regra, e os mesmos pesos marcariam a folha inteira. **O domínio `scan` foi ajustado contra OCR de terceiro**, porque o
scan-ouro ainda não tem verdade (S-703): ele ordena, e a probabilidade dele é uma estimativa contra aquela referência. Quem precisar da
verdade de scan espera a D3.

**Só a prosa é calibrada.** A referência da notação é a camada, que escreve o lance num formato que a tinta não tem (protocolo, seção 2): um
rótulo de erro ali mediria a referência. O token de notação fica com a confiança de quem o escreveu.

**Sem importar a régua**: `regua_prosa` é o instrumento, e o calibrador é parte do medido. `test_text_confianca_palavra.py` trava o grafo.

O interruptor é `LIGADO`. Desligado, a linha fundida volta à confiança de antes: a do glifo na linha, e a de quem escreveu em cada palavra.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import replace

from . import fusao as _fusao

LIGADO = True
"""O interruptor da S-760. Só `motor="fusao"` passa por aqui, e ele não é o padrão: ligar não muda o que `auto` ou `glifo` leem."""

DIGITAL = "digital"
SCAN = "scan"
DOMINIOS = (DIGITAL, SCAN)

NOMES = (
    "vies",
    "conf_logit",
    "conf_ausente",
    "origem_glifo",
    "discorda",
    "sem_par",
    "distancia",
    "leitor_discorda",
    "fora_do_lexico",
    "forma_estranha",
    "curta",
    "caixa_alta",
    "notacao",
    "sem_letra",
)
"""Os atributos, na ordem dos coeficientes. Um teste confere que `atributos` devolve um por nome."""

COEFICIENTES: dict[str, tuple[float, ...]] = {
    DIGITAL: (-3.5396, -0.6555, 0.0, 1.0943, 3.0895, 1.4138, -0.1, 0.9825, 0.7778, -0.9045, 0.1246, 2.5618, -4.686, -3.0661),
    SCAN: (-2.4287, -0.6452, 0.0, 2.0667, 0.8073, 1.6402, 0.9532, 0.1015, 1.1198, -1.9036, 0.5945, 2.7009, -4.7205, -3.986),
}
"""Saída de `ajustar.py`, sobre o pedaço reservado. Mudar um número à mão é mudar a calibração sem medir."""

_NU = ".,;:!?()[]{}'\"’‘“”«»…"
_FORMA_ESTRANHA = re.compile(r"\d|[^\w\-'’]")
_MISTA = re.compile(r"[a-zà-ÿ][A-ZÀ-Þ]")
_CHAO = 1e-4


def dominio_da_regra(regra: str) -> str:
    """O domínio é o estrato que a fusão já decidiu: v3 é scan, e o resto é digital."""
    return SCAN if regra == _fusao.V3 else DIGITAL


def _distancia(a: str, b: str) -> float:
    return _fusao._distancia(a, b)  # noqa: SLF001


def _logit(valor: float) -> float:
    return math.log((valor + 0.01) / (1.01 - valor))


def _discorda(token: _fusao.Token) -> bool:
    return bool(token.do_glifo) and token.do_glifo != token.texto


def atributos(
    token: _fusao.Token,
    *,
    existe: Callable[[str], bool],
) -> tuple[float, ...]:
    """Um número por nome de `NOMES`. Só o que a fusão sabe na hora: nenhum atributo olha referência."""
    texto = token.texto
    nu = texto.strip(_NU)
    letras = sum(c.isalpha() for c in nu)
    classe = _fusao.classe_do_token(texto)
    conf = token.confianca
    return (
        1.0,
        0.0 if conf is None else _logit(max(0.0, min(1.0, float(conf)))),
        1.0 if conf is None else 0.0,
        1.0 if token.origem == "glifo" else 0.0,
        1.0 if _discorda(token) else 0.0,
        1.0 if not token.do_glifo else 0.0,
        _distancia(token.do_glifo, texto) if token.do_glifo else 0.0,
        1.0 if token.do_leitor and token.do_leitor != texto else 0.0,
        0.0 if existe(texto) else 1.0,
        1.0 if _FORMA_ESTRANHA.search(nu) or _MISTA.search(nu) else 0.0,
        1.0 if 0 < letras <= 2 else 0.0,
        1.0 if letras >= 3 and nu.isupper() else 0.0,
        1.0 if classe == _fusao.NOTACAO else 0.0,
        1.0 if classe == _fusao.OUTRO else 0.0,
    )


def erro_de(valores: Sequence[float], dominio: str) -> float:
    """A probabilidade de a palavra estar errada, dados os atributos."""
    pesos = COEFICIENTES[dominio]
    z = sum(p * v for p, v in zip(pesos, valores, strict=True))
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def erros_da_folha(linhas: Sequence[Sequence[_fusao.Token]], *, existe: Callable[[str], bool], dominio: str) -> list[list[float]]:
    """A probabilidade de erro de cada token. É o que a marca da S-761 compara ao corte."""
    return [[erro_de(atributos(t, existe=existe), dominio) for t in linha] for linha in linhas]


def calibrar_folha(
    linhas: Sequence[Sequence[_fusao.Token]], *, existe: Callable[[str], bool], dominio: str
) -> tuple[list[list[_fusao.Token]], list[list[float]]]:
    """Os tokens com a confiança calibrada na prosa, e a probabilidade de erro de todos.

    **O token de notação não muda**: ver o cabeçalho. Texto nenhum muda: esta função só toca em `confianca`.
    """
    erros = erros_da_folha(linhas, existe=existe, dominio=dominio)
    saida: list[list[_fusao.Token]] = []
    for linha, da_linha in zip(linhas, erros, strict=True):
        saida.append(
            [
                t if _fusao.classe_do_token(t.texto) == _fusao.NOTACAO else replace(t, confianca=max(_CHAO, 1.0 - p))
                for t, p in zip(linha, da_linha, strict=True)
            ]
        )
    return saida, erros


def confianca_da_linha(tokens: Sequence[_fusao.Token], reserva: float) -> float:
    """A linha vale a palavra de prosa mais fraca dela. Sem prosa, `reserva`: a confiança de antes, a do glifo."""
    prosa = [t.confianca for t in tokens if t.confianca is not None and _fusao.classe_do_token(t.texto) != _fusao.NOTACAO]
    return min(prosa) if prosa else reserva


__all__ = [
    "COEFICIENTES",
    "DIGITAL",
    "DOMINIOS",
    "LIGADO",
    "NOMES",
    "SCAN",
    "atributos",
    "calibrar_folha",
    "confianca_da_linha",
    "dominio_da_regra",
    "erro_de",
    "erros_da_folha",
]
