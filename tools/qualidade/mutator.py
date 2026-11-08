"""mutator: quanto do que a suíte cobre ela de fato verifica (S-803).

Uma mutação por vez, por AST, no fonte do módulo; para cada uma rodam **os arquivos de teste que
importam o módulo** (não só o homônimo), e o mutante que passa é um sobrevivente: a linha que a
suíte executa sem conferir. Os operadores:

    cmp      troca de comparação (`<` por `<=`, `==` por `!=`, `in` por `not in`, ...)
    bin      troca aritmética (`+` por `-`, `*` por `/`, ...)
    bool     `and` por `or` e vice-versa
    not      `not x` vira `x`
    int      constante inteira + 1
    boolc    `True` por `False` e vice-versa
    ret      `return X` vira `return None`
    str      constante `str` vira `""`

Só se muta o que está dentro de função, e nunca docstring nem anotação.

**O fonte volta byte a byte.** Antes da primeira mutação o original é copiado para
`<modulo>.py.mutator-orig`; um `finally` o restaura na saída normal e no Ctrl+C, e a partida
seguinte restaura a cópia que um processo morto sem `finally` (`taskkill /F`) deixou. Os filhos
rodam com `PYTHONDONTWRITEBYTECODE=1`, e o `.pyc` do módulo é apagado a cada mutação e na
restauração: o `.pyc` é validado por mtime em segundos e tamanho, e a troca de `+` por `-` não
muda o tamanho.

**Uso** (não roda no CI; roda à mão, e o escore registrado só sobe):

    python tools/qualidade/mutator.py src/chess_diagram_ocr/splits.py --limite 50 --gravar
"""

from __future__ import annotations

import argparse
import ast
import copy
import datetime
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SRC = RAIZ / "src"
TESTES = RAIZ / "tests"
REGISTRO = RAIZ / "docs" / "metrics" / "mutacao.json"
SUFIXO_DA_COPIA = ".mutator-orig"

_CMP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}
_BIN: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.FloorDiv,
}

Rodar = Callable[[Sequence[Path]], bool]
"""Roda os arquivos de teste e diz se todos passaram."""


@dataclass(frozen=True)
class Ponto:
    operador: str
    linha: int
    indice: int
    """Posição do nó em `ast.walk` da árvore: a cópia da árvore tem o mesmo nó no mesmo índice."""


@dataclass(frozen=True)
class Sobrevivente:
    linha: int
    operador: str
    trecho: str


@dataclass
class Resultado:
    modulo: str
    testes: list[str]
    mutantes: int = 0
    mortos: int = 0
    sobreviventes: list[Sobrevivente] = field(default_factory=list)

    @property
    def escore(self) -> float:
        return self.mortos / self.mutantes if self.mutantes else 0.0


def _operador(no: ast.AST) -> str | None:
    if isinstance(no, ast.Compare) and type(no.ops[0]) in _CMP:
        return "cmp"
    if isinstance(no, ast.BinOp) and type(no.op) in _BIN:
        return "bin"
    if isinstance(no, ast.BoolOp):
        return "bool"
    if isinstance(no, ast.UnaryOp) and isinstance(no.op, ast.Not):
        return "not"
    if isinstance(no, ast.Constant):
        if isinstance(no.value, bool):
            return "boolc"
        if type(no.value) is int:
            return "int"
        if isinstance(no.value, str) and no.value:
            return "str"
    if isinstance(no, ast.Return) and no.value is not None:
        if not (isinstance(no.value, ast.Constant) and no.value.value is None):
            return "ret"
    return None


def _intocaveis(arvore: ast.AST) -> set[int]:
    """`id` dos nós que não se mutam: docstrings e tudo o que está dentro de uma anotação."""
    fora: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            corpo = no.body
            if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant):
                fora.add(id(corpo[0].value))
        anotacoes: list[ast.AST | None] = []
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            anotacoes.append(no.returns)
        if isinstance(no, ast.arg):
            anotacoes.append(no.annotation)
        if isinstance(no, ast.AnnAssign):
            anotacoes.append(no.annotation)
        for anotacao in anotacoes:
            if anotacao is not None:
                fora.update(id(dentro) for dentro in ast.walk(anotacao))
    return fora


def pontos(arvore: ast.AST, limite: int | None = None) -> list[Ponto]:
    """Os pontos de mutação dentro de funções, em ordem de linha; com `limite`, uma amostra regular."""
    dentro_de_funcao: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for filho in no.body:
                dentro_de_funcao.update(id(n) for n in ast.walk(filho))
    fora = _intocaveis(arvore)
    achados = []
    for indice, no in enumerate(ast.walk(arvore)):
        if id(no) not in dentro_de_funcao or id(no) in fora:
            continue
        operador = _operador(no)
        if operador is not None:
            achados.append(Ponto(operador, getattr(no, "lineno", 0), indice))
    achados.sort(key=lambda p: (p.linha, p.indice))
    if limite is not None and len(achados) > limite:
        passo = len(achados) / limite
        achados = [achados[int(i * passo)] for i in range(limite)]
    return achados


def mutante(arvore: ast.AST, ponto: Ponto) -> str:
    """O fonte com uma mutação só, a do `ponto`."""
    copia = copy.deepcopy(arvore)
    alvo = next(no for indice, no in enumerate(ast.walk(copia)) if indice == ponto.indice)
    if isinstance(alvo, ast.Compare):
        alvo.ops = [_CMP[type(alvo.ops[0])](), *alvo.ops[1:]]
    elif isinstance(alvo, ast.BinOp):
        alvo.op = _BIN[type(alvo.op)]()
    elif isinstance(alvo, ast.BoolOp):
        alvo.op = ast.Or() if isinstance(alvo.op, ast.And) else ast.And()
    elif isinstance(alvo, ast.UnaryOp):
        _substituir(copia, alvo, alvo.operand)
    elif isinstance(alvo, ast.Constant) and isinstance(alvo.value, bool):
        alvo.value = not alvo.value
    elif isinstance(alvo, ast.Constant) and isinstance(alvo.value, int):
        alvo.value = alvo.value + 1
    elif isinstance(alvo, ast.Constant):
        alvo.value = ""
    elif isinstance(alvo, ast.Return):
        alvo.value = ast.Constant(None)
    return ast.unparse(ast.fix_missing_locations(copia)) + "\n"


def _substituir(arvore: ast.AST, velho: ast.AST, novo: ast.AST) -> None:
    for pai in ast.walk(arvore):
        for nome, valor in ast.iter_fields(pai):
            if valor is velho:
                setattr(pai, nome, novo)
                return
            if isinstance(valor, list) and any(item is velho for item in valor):
                valor[[item is velho for item in valor].index(True)] = novo
                return


def nome_do_modulo(caminho: Path, src: Path = SRC) -> str:
    partes = caminho.resolve().relative_to(src.resolve()).with_suffix("").parts
    return ".".join(partes[:-1] if partes[-1] == "__init__" else partes)


def _importa(arvore: ast.AST, modulo: str) -> bool:
    pai, _, folha = modulo.rpartition(".")
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import) and any(a.name == modulo or a.name.startswith(modulo + ".") for a in no.names):
            return True
        if isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            if no.module == modulo or no.module.startswith(modulo + "."):
                return True
            if no.module == pai and any(a.name == folha for a in no.names):
                return True
    return False


def testes_que_importam(modulo: str, pasta: Path = TESTES) -> list[Path]:
    """Os `test_*.py` que importam o módulo, de qualquer jeito que se escreva o import.

    O homônimo (`test_<modulo>.py`) vem primeiro: é onde a maior parte dos mutantes morre, e com
    o `pytest -x` o mutante morto ali não paga os outros arquivos.
    """
    homonimo = f"test_{modulo.rpartition('.')[2]}.py"
    achados = [
        caminho
        for caminho in sorted(pasta.rglob("test_*.py"))
        if _importa(ast.parse(caminho.read_text(encoding="utf-8")), modulo)
    ]
    return sorted(achados, key=lambda caminho: caminho.name != homonimo)


def copia_de(alvo: Path) -> Path:
    return alvo.with_name(alvo.name + SUFIXO_DA_COPIA)


def apagar_pyc(alvo: Path) -> None:
    for pyc in (alvo.parent / "__pycache__").glob(f"{alvo.stem}.*.pyc"):
        pyc.unlink(missing_ok=True)


def restaurar_pendente(alvo: Path) -> bool:
    """Devolve ao módulo a cópia que uma rodada morta deixou. True se havia uma."""
    copia = copia_de(alvo)
    if not copia.exists():
        return False
    alvo.write_bytes(copia.read_bytes())
    copia.unlink()
    apagar_pyc(alvo)
    return True


def ambiente(raiz: Path) -> dict[str, str]:
    anterior = os.environ.get("PYTHONPATH", "")
    caminho = str(raiz / "src") + (os.pathsep + anterior if anterior else "")
    return {
        **os.environ,
        "PYTHONPATH": caminho,
        "PYTHONDONTWRITEBYTECODE": "1",
        "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "offscreen"),
    }


def rodar_pytest(raiz: Path, timeout: float = 600.0) -> Rodar:
    """`pytest -x` nos arquivos, num processo novo. Estourar o tempo conta como reprovar."""

    def rodar(testes: Sequence[Path]) -> bool:
        comando = [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *map(str, testes)]
        try:
            saida = subprocess.run(
                comando,
                cwd=raiz,
                env=ambiente(raiz),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False
        return saida.returncode == 0

    return rodar


def mutar(
    alvo: Path,
    testes: Sequence[Path],
    rodar: Rodar,
    *,
    limite: int | None = None,
    nome: str | None = None,
    progresso: Callable[[str], None] = lambda _: None,
) -> Resultado:
    """Muta `alvo` uma vez por ponto, roda `testes` para cada mutante, e restaura o fonte."""
    if restaurar_pendente(alvo):
        progresso(f"restaurado {alvo.name} da cópia que uma rodada interrompida deixou")
    original = alvo.read_bytes()
    if not testes:
        raise ValueError(f"nenhum arquivo de teste importa {alvo}")
    apagar_pyc(alvo)
    if not rodar(testes):
        raise RuntimeError(f"os testes de {alvo.name} reprovam sem mutação nenhuma: nada a medir")
    arvore = ast.parse(original.decode("utf-8"))
    linhas = original.decode("utf-8").splitlines()
    escolhidos = pontos(arvore, limite)
    resultado = Resultado(nome or alvo.as_posix(), [t.name for t in testes], mutantes=len(escolhidos))
    copia = copia_de(alvo)
    copia.write_bytes(original)
    try:
        for numero, ponto in enumerate(escolhidos, 1):
            alvo.write_bytes(mutante(arvore, ponto).encode("utf-8"))
            apagar_pyc(alvo)
            if rodar(testes):
                trecho = linhas[ponto.linha - 1].strip()[:100] if ponto.linha else ""
                resultado.sobreviventes.append(Sobrevivente(ponto.linha, ponto.operador, trecho))
            else:
                resultado.mortos += 1
            progresso(f"{numero}/{len(escolhidos)} L{ponto.linha} [{ponto.operador}]")
    finally:
        alvo.write_bytes(original)
        apagar_pyc(alvo)
        copia.unlink(missing_ok=True)
    return resultado


def gravar(resultado: Resultado, limite: int | None, registro: Path, forcar: bool) -> str | None:
    """Põe o escore do módulo no registro. Recusa (e devolve o motivo) se ele desceu."""
    dados = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {"modulos": {}}
    anterior = dados["modulos"].get(resultado.modulo)
    escore = round(resultado.escore, 3)
    if anterior is not None and escore < anterior["escore"] and not forcar:
        return f"{resultado.modulo}: escore {escore:.0%} abaixo do registrado {anterior['escore']:.0%}"
    dados["modulos"][resultado.modulo] = {
        "data": datetime.date.today().isoformat(),
        "limite": limite,
        "mutantes": resultado.mutantes,
        "mortos": resultado.mortos,
        "escore": escore,
        "testes": resultado.testes,
        "sobreviventes": [asdict(s) for s in resultado.sobreviventes],
    }
    dados["modulos"] = dict(sorted(dados["modulos"].items()))
    registro.write_bytes((json.dumps(dados, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("modulos", nargs="+", type=Path, help="arquivos .py sob src/")
    parser.add_argument("--limite", type=int, default=50, help="mutantes por módulo, amostrados em ordem de linha")
    parser.add_argument("--gravar", action="store_true", help=f"grava o escore em {REGISTRO.relative_to(RAIZ)}")
    parser.add_argument("--forcar", action="store_true", help="com --gravar, grava mesmo um escore menor")
    args = parser.parse_args(argv)

    recusas = []
    for modulo in args.modulos:
        alvo = modulo.resolve()
        testes = testes_que_importam(nome_do_modulo(alvo))
        inicio = time.perf_counter()
        resultado = mutar(
            alvo,
            testes,
            rodar_pytest(RAIZ),
            limite=args.limite,
            nome=alvo.relative_to(RAIZ).as_posix(),
            progresso=lambda texto: print("  ", texto, flush=True),
        )
        print(
            f"{resultado.modulo}: {len(testes)} arquivos de teste, mutantes {resultado.mutantes}, "
            f"mortos {resultado.mortos}, sobreviventes {len(resultado.sobreviventes)}, "
            f"escore {resultado.escore:.0%} ({time.perf_counter() - inicio:.0f} s)"
        )
        for vivo in resultado.sobreviventes:
            print(f"  L{vivo.linha} [{vivo.operador}] {vivo.trecho}")
        if args.gravar:
            recusa = gravar(resultado, args.limite, REGISTRO, args.forcar)
            if recusa:
                print("Nada gravado:", recusa, file=sys.stderr)
                recusas.append(recusa)
    return 1 if recusas else 0


if __name__ == "__main__":
    sys.exit(main())
