"""As palavras curtas que o léxico não tem de propósito, para quem precisa delas (S-732, S-735).

`lexico.MIN_TAMANHO` é 4, e tem de ser: `Kf`, `Nc` e `Re` são notação, e estavam no léxico bruto antes
dessa régua. O preço é que `the`, `of`, `não` e `são` também ficam de fora, e duas decisões da Fase 103
precisam deles: partir `ofthe` (S-732) e trocar o acento de `näo` (S-735).

**A lista é fechada, escrita à mão e de palavra funcional**: artigo, preposição, conjunção, pronome e os
verbos mais comuns, nas línguas do acervo. Quem a consulta usa o léxico para a palavra longa e esta lista
só para a curta: ela nunca é somada ao dicionário de `corrigir`, cuja guarda de `MIN_TAMANHO` continua
valendo. E quem a consulta é decisão de **palavra**, não de lance: `Be2` tem dígito, e nenhuma delas o
olha; `be` sozinho é palavra.
"""

from __future__ import annotations

from .lexico import MIN_TAMANHO, PONTUACAO_DE_BORDA

_INGLES = """a i an as at be by do go he if in is it me my no of on or so to up us we
all and any are but can did for get had has her him his how its let may nor not now off old one our
out own put say see she the too two use was way who why yes yet you"""

_PORTUGUES = """a e o à é ao as às da de do em há já lá me na no nu os se si só te tu um
aos até bem bom boa com das dos ela ele era foi fez lhe mal mas mão meu não nem nos nós num por pão que
são sem ser seu sob sua tal tão ter teu tem têm uma vai vão ver vez dá dão pôr rei vós"""

_ESPANHOL = """a e o y al de el en es ha la le lo me mi ni no se si su te tu un ya
con del era fue las les los más mis muy por que sin son sus una"""

_FRANCES = """a à y au ce de du en et il je la le ma me ne on ou où sa se si un
aux ces des est les mes mon nos ont par pas que qui ses son sur une"""

_ALEMAO = """am an da du er es im in ja wo zu
auf aus bei das dem den der des die ein hat ist mit nun oft sie und von vor war wie zum zur"""

CURTAS = frozenset(p for grupo in (_INGLES, _PORTUGUES, _ESPANHOL, _FRANCES, _ALEMAO) for p in grupo.split())
"""Em `casefold`. Toda palavra daqui tem menos de `lexico.MIN_TAMANHO` letras (`test_palavras_curtas`)."""


def conhecida_ou_curta(palavra: str, lexico: frozenset[str]) -> bool:
    """A palavra está no léxico, ou é curta e está nesta lista? Sem pontuação nas pontas."""
    limpa = palavra.strip(PONTUACAO_DE_BORDA).casefold()
    if not limpa:
        return False
    return limpa in lexico or (len(limpa) < MIN_TAMANHO and limpa in CURTAS)


__all__ = ["CURTAS", "conhecida_ou_curta"]
