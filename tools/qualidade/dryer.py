"""dryer: pares de funções quase iguais em `src/`, e a catraca sobre eles (S-802).

Cada função com `MIN_TOKENS` tokens ou mais vira uma sequência normalizada -- nome vira `N`, número
`0`, string `S`; palavra-chave e operador ficam --, e dois pares se medem pelo Jaccard dos
conjuntos de `GRAMAS`-gramas. Normalizar nomes e literais é o que pega a cópia com renomeação.

**Uso.**

    python tools/qualidade/dryer.py                  # compara com docs/metrics/dryer.json
    python tools/qualidade/dryer.py --gravar         # registra (recusa par novo)
    python tools/qualidade/dryer.py --gravar --aceitar "razão"   # aceita os novos, com a razão

A catraca guarda os pares com semelhança >= `LIMIAR`. Par novo reprova; par que some também
reprova, até alguém regravar -- é assim que o teto desce e não volta a subir. Um par pode ser
declarado semelhante de propósito: o campo `proposito` do par no JSON traz a razão, e o
`--gravar` a preserva.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import keyword
import math
import sys
import time
import tokenize
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
REGISTRO = RAIZ / "docs" / "metrics" / "dryer.json"

LIMIAR = 0.8
GRAMAS = 5
MIN_TOKENS = 60

_PALAVRAS = frozenset(keyword.kwlist)
_FSTRING_INICIO = getattr(tokenize, "FSTRING_START", -1)
_FSTRING_FIM = getattr(tokenize, "FSTRING_END", -1)


@dataclass(frozen=True)
class Funcao:
    arquivo: str
    nome: str
    linha: int
    fim: int
    tokens: int
    gramas: frozenset[tuple[str, ...]]

    @property
    def chave(self) -> str:
        return f"{self.arquivo}::{self.nome}"


@dataclass(frozen=True)
class Par:
    a: Funcao
    b: Funcao
    semelhanca: float

    @property
    def chave(self) -> tuple[str, str]:
        return (self.a.chave, self.b.chave)


def tokens_por_linha(fonte: str) -> list[tuple[int, str]]:
    """Os tokens normalizados do arquivo, cada um com a linha onde começa.

    A f-string vira um `S` só, como qualquer string: do 3.12 em diante o `tokenize` a abre em
    pedaços com os nomes de dentro, e sem isto a mesma função mediria diferente no 3.10 e no 3.13.
    """
    saida: list[tuple[int, str]] = []
    dentro_de_fstring = 0
    for token in tokenize.generate_tokens(io.StringIO(fonte).readline):
        if token.type == _FSTRING_INICIO:
            if not dentro_de_fstring:
                saida.append((token.start[0], "S"))
            dentro_de_fstring += 1
        elif token.type == _FSTRING_FIM:
            dentro_de_fstring -= 1
        elif dentro_de_fstring:
            continue
        elif token.type == tokenize.NAME:
            saida.append((token.start[0], token.string if token.string in _PALAVRAS else "N"))
        elif token.type == tokenize.NUMBER:
            saida.append((token.start[0], "0"))
        elif token.type == tokenize.STRING:
            saida.append((token.start[0], "S"))
        elif token.type == tokenize.OP:
            saida.append((token.start[0], token.string))
    return saida


def _definicoes(arvore: ast.Module) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Toda função do módulo com o nome qualificado (`Classe.metodo`, `funcao.interna`)."""
    achadas: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []

    def anda(no: ast.AST, prefixo: str) -> None:
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)):
                achadas.append((prefixo + filho.name, filho))
                anda(filho, f"{prefixo}{filho.name}.")
            elif isinstance(filho, ast.ClassDef):
                anda(filho, f"{prefixo}{filho.name}.")
            else:
                anda(filho, prefixo)

    anda(arvore, "")
    return achadas


def funcoes_do_arquivo(fonte: str, arquivo: str) -> list[Funcao]:
    lidos = tokens_por_linha(fonte)
    linhas = [linha for linha, _ in lidos]
    saida = []
    for nome, no in _definicoes(ast.parse(fonte)):
        fim = no.end_lineno or no.lineno
        sequencia = [t for _, t in lidos[bisect_left(linhas, no.lineno) : bisect_right(linhas, fim)]]
        if len(sequencia) < MIN_TOKENS:
            continue
        gramas = frozenset(tuple(sequencia[i : i + GRAMAS]) for i in range(len(sequencia) - GRAMAS + 1))
        saida.append(Funcao(arquivo, nome, no.lineno, fim, len(sequencia), gramas))
    return saida


def funcoes_da_arvore(raiz: Path, pastas: Sequence[str] = ("src",)) -> list[Funcao]:
    saida = []
    for pasta in pastas:
        for caminho in sorted((raiz / pasta).rglob("*.py")):
            saida += funcoes_do_arquivo(caminho.read_text(encoding="utf-8"), caminho.relative_to(raiz).as_posix())
    return saida


def semelhanca(a: Funcao, b: Funcao) -> float:
    comuns = len(a.gramas & b.gramas)
    return comuns / (len(a.gramas) + len(b.gramas) - comuns)


def _aninhadas(a: Funcao, b: Funcao) -> bool:
    """Uma dentro da outra: a de fora contém a de dentro, e isso não é cópia."""
    return a.arquivo == b.arquivo and (a.linha <= b.linha <= a.fim or b.linha <= a.linha <= b.fim)


def pares(funcoes: Sequence[Funcao], limiar: float = LIMIAR) -> list[Par]:
    """Os pares com semelhança >= `limiar`, do mais parecido ao menos.

    Comparar todos com todos são milhões de interseções. O filtro de prefixo escolhe os
    candidatos sem perder par nenhum: com os gramas de cada função em ordem do mais raro ao mais
    comum, dois conjuntos de Jaccard >= `limiar` têm de dividir ao menos um grama entre os
    `n - ceil(limiar * n) + 1` primeiros de cada um. Só os que dividem são medidos.
    """
    frequencia: Counter[tuple[str, ...]] = Counter()
    for funcao in funcoes:
        frequencia.update(funcao.gramas)
    indice: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for i, funcao in enumerate(funcoes):
        ordem = sorted(funcao.gramas, key=lambda g: (frequencia[g], g))
        for grama in ordem[: len(ordem) - math.ceil(limiar * len(ordem)) + 1]:
            indice[grama].append(i)
    candidatos = {(i, j) for donos in indice.values() for x, i in enumerate(donos) for j in donos[x + 1 :]}
    achados = []
    for i, j in candidatos:
        a, b = funcoes[i], funcoes[j]
        if _aninhadas(a, b):
            continue
        valor = semelhanca(a, b)
        if valor >= limiar:
            primeiro, segundo = sorted((a, b), key=lambda f: (f.arquivo, f.linha))
            achados.append(Par(primeiro, segundo, valor))
    achados.sort(key=lambda p: (-p.semelhanca, p.chave))
    return achados


def registro(achados: Sequence[Par], anterior: dict[str, object] | None, aceitar: str | None) -> dict[str, object]:
    """O JSON da catraca. Preserva o `proposito` de quem já o tinha; os novos levam `aceitar`."""
    propositos: dict[tuple[str, str], str | None] = {}
    if anterior is not None:
        propositos = {(par["a"], par["b"]): par.get("proposito") for par in _pares_registrados(anterior)}
    linhas = []
    for par in achados:
        entrada: dict[str, object] = {
            "a": par.a.chave,
            "linha_a": par.a.linha,
            "b": par.b.chave,
            "linha_b": par.b.linha,
            "semelhanca": round(par.semelhanca, 3),
        }
        proposito = propositos[par.chave] if par.chave in propositos else aceitar
        if proposito:
            entrada["proposito"] = proposito
        linhas.append(entrada)
    return {"limiar": LIMIAR, "gramas": GRAMAS, "min_tokens": MIN_TOKENS, "total": len(linhas), "pares": linhas}


def _pares_registrados(registrado: dict[str, object]) -> list[dict[str, str]]:
    lista = registrado["pares"]
    assert isinstance(lista, list)
    return lista


def comparar(registrado: dict[str, object], achados: Sequence[Par]) -> tuple[list[Par], list[str]]:
    """Os pares novos, que reprovam, e as chaves registradas que sumiram, que pedem regravar."""
    conhecidos = {(par["a"], par["b"]) for par in _pares_registrados(registrado)}
    agora = {par.chave for par in achados}
    novos = [par for par in achados if par.chave not in conhecidos]
    sumidos = sorted(f"{a}  <->  {b}" for a, b in conhecidos - agora)
    return novos, sumidos


def _descreve(par: Par) -> str:
    return f"{par.semelhanca:.2f} {par.a.arquivo}:{par.a.linha} {par.a.nome}  <->  {par.b.arquivo}:{par.b.linha} {par.b.nome}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registro", type=Path, default=REGISTRO)
    parser.add_argument("--raiz", type=Path, default=RAIZ)
    parser.add_argument("--gravar", action="store_true", help="grava os pares de hoje no registro")
    parser.add_argument("--aceitar", metavar="RAZAO", help="com --gravar, aceita os pares novos com esta razão")
    parser.add_argument("--mostrar", type=int, default=20)
    args = parser.parse_args(argv)

    inicio = time.perf_counter()
    funcoes = funcoes_da_arvore(args.raiz)
    achados = pares(funcoes)
    print(
        f"{len(funcoes)} funções com {MIN_TOKENS}+ tokens, {len(achados)} pares >= {LIMIAR:g} "
        f"({time.perf_counter() - inicio:.1f} s)"
    )
    for par in achados[: args.mostrar]:
        print(" ", _descreve(par))

    anterior = json.loads(args.registro.read_text(encoding="utf-8")) if args.registro.exists() else None
    novos, sumidos = comparar(anterior, achados) if anterior is not None else ([], [])
    for par in novos:
        print("PAR NOVO:", _descreve(par), file=sys.stderr)
    for chave in sumidos:
        print("PAR QUE SUMIU (regrave para baixar o teto):", chave, file=sys.stderr)
    if args.gravar:
        if novos and not args.aceitar:
            print('Nada gravado: há par novo. Desfaça a cópia, ou --aceitar "razão".', file=sys.stderr)
            return 1
        texto = json.dumps(registro(achados, anterior, args.aceitar), ensure_ascii=False, indent=1) + "\n"
        args.registro.write_bytes(texto.encode("utf-8"))
        print(f"gravado {args.registro}")
        return 0
    return 1 if novos or sumidos else 0


if __name__ == "__main__":
    sys.exit(main())
