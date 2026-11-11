"""catraca_de_tipos: `type: ignore`, `Any` e `except Exception` por pacote, e só descem (S-804).

Conta três coisas que tiram o verificador de tipos do caminho, por pacote de `src/chess_diagram_ocr/`
(`qt`, `text`, `ui`, `cli`, `detection`, e `raiz` para os módulos de cima) e o `app_pyqt.py` à
parte, e compara com `docs/metrics/catraca_de_tipos.json`.

**Uso.**

    python tools/qualidade/catraca_de_tipos.py            # compara com o registro
    python tools/qualidade/catraca_de_tipos.py --gravar   # registra (recusa contagem que subiu)

Contagem que sobe reprova, com o pacote e a coisa na mensagem. Contagem que desce também reprova,
dizendo o número novo, até alguém regravar -- é assim que o teto desce e não volta a subir: quem
apagou um `Any` roda `--gravar` e o commit leva o registro junto. `--gravar --forcar` grava mesmo
com subida (um pacote novo, um arquivo que mudou de pacote); o diff do JSON é o que se revisa.

**O que conta.** Lido pela árvore, e não por `grep`: comentário e docstring que citam a coisa não
contam.

- `type_ignore`: os `# type: ignore` que o `ast` com `type_comments=True` devolve -- o mesmo leitor
  que o mypy usa, então conta exatamente os que o mypy obedece.
- `any`: cada uso do nome `Any` (`Any`, `typing.Any`), também dentro de anotação entre aspas. O
  `import` não conta; o uso, sim.
- `except_exception`: cada `except Exception` ou `except (..., Exception, ...)`.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
REGISTRO = RAIZ / "docs" / "metrics" / "catraca_de_tipos.json"

COISAS = ("type_ignore", "any", "except_exception")
Contagem = dict[str, dict[str, int]]


def _usos_de_any(arvore: ast.AST) -> Iterator[ast.AST]:
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name) and no.id == "Any":
            yield no
        elif isinstance(no, ast.Attribute) and no.attr == "Any":
            yield no


def _anotacoes_entre_aspas(arvore: ast.AST) -> Iterator[ast.expr]:
    """As anotações escritas como string, já lidas como expressão."""
    anotacoes: list[ast.expr | None] = []
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            anotacoes.append(no.returns)
        elif isinstance(no, ast.arg):
            anotacoes.append(no.annotation)
        elif isinstance(no, ast.AnnAssign):
            anotacoes.append(no.annotation)
    for anotacao in anotacoes:
        if anotacao is None:
            continue
        for no in ast.walk(anotacao):
            if isinstance(no, ast.Constant) and isinstance(no.value, str):
                try:
                    yield ast.parse(no.value, mode="eval").body
                except SyntaxError:
                    continue


def _pega_exception(tipo: ast.expr | None) -> bool:
    if isinstance(tipo, ast.Tuple):
        return any(_pega_exception(elemento) for elemento in tipo.elts)
    return isinstance(tipo, ast.Name) and tipo.id == "Exception"


def contar_fonte(fonte: str, nome: str = "<fonte>") -> dict[str, int]:
    """As três contagens de um módulo."""
    arvore = ast.parse(fonte, filename=nome, type_comments=True)
    assert isinstance(arvore, ast.Module)
    any_ = sum(1 for _ in _usos_de_any(arvore))
    any_ += sum(sum(1 for _ in _usos_de_any(expr)) for expr in _anotacoes_entre_aspas(arvore))
    excecoes = sum(1 for no in ast.walk(arvore) if isinstance(no, ast.ExceptHandler) and _pega_exception(no.type))
    return {"type_ignore": len(arvore.type_ignores), "any": any_, "except_exception": excecoes}


def pacote_de(caminho: Path, raiz: Path) -> str:
    """`app_pyqt.py`, `raiz` para os módulos de cima de `chess_diagram_ocr`, ou o subpacote."""
    relativo = caminho.relative_to(raiz)
    if relativo.parts[0] != "src":
        return relativo.as_posix()
    dentro = relativo.parts[2:]
    return dentro[0] if len(dentro) > 1 else "raiz"


def _arquivos(raiz: Path) -> Iterable[Path]:
    yield from sorted((raiz / "src").rglob("*.py"))
    app = raiz / "app_pyqt.py"
    if app.exists():
        yield app


def contar_arvore(raiz: Path) -> Contagem:
    """As contagens de `src/` e do `app_pyqt.py`, somadas por pacote."""
    total: Contagem = {}
    for arquivo in _arquivos(raiz):
        contas = contar_fonte(arquivo.read_text(encoding="utf-8"), str(arquivo))
        soma = total.setdefault(pacote_de(arquivo, raiz), dict.fromkeys(COISAS, 0))
        for coisa, n in contas.items():
            soma[coisa] += n
    return dict(sorted(total.items()))


def comparar(registrado: Contagem, agora: Contagem) -> tuple[list[str], list[str]]:
    """As subidas, que reprovam, e as descidas, que pedem regravar -- uma frase por contagem."""
    subidas: list[str] = []
    descidas: list[str] = []
    for pacote in sorted(set(registrado) | set(agora)):
        antes = registrado.get(pacote, {})
        hoje = agora.get(pacote, {})
        for coisa in COISAS:
            a, h = antes.get(coisa, 0), hoje.get(coisa, 0)
            if h > a:
                subidas.append(f"{pacote}: {coisa} subiu de {a} para {h}")
            elif h < a:
                descidas.append(f"{pacote}: {coisa} desceu de {a} para {h}")
    return subidas, descidas


def ler_registro(caminho: Path) -> Contagem:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    pacotes: Contagem = dados["pacotes"]
    return pacotes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--registro", type=Path, default=REGISTRO)
    parser.add_argument("--raiz", type=Path, default=RAIZ)
    parser.add_argument("--gravar", action="store_true", help="grava as contagens de hoje no registro")
    parser.add_argument("--forcar", action="store_true", help="com --gravar, grava mesmo com contagem que subiu")
    args = parser.parse_args(argv)

    agora = contar_arvore(args.raiz)
    for pacote, contas in agora.items():
        print(f"  {pacote:<14}" + "  ".join(f"{coisa} {contas[coisa]:>4}" for coisa in COISAS))
    subidas, descidas = comparar(ler_registro(args.registro), agora) if args.registro.exists() else ([], [])
    for frase in subidas:
        print("SUBIU:", frase, file=sys.stderr)
    for frase in descidas:
        print("DESCEU (regrave para baixar o teto):", frase, file=sys.stderr)
    if args.gravar:
        if subidas and not args.forcar:
            print("Nada gravado: há contagem que subiu. Desfaça, ou --forcar.", file=sys.stderr)
            return 1
        texto = json.dumps({"pacotes": agora}, ensure_ascii=False, indent=1) + "\n"
        args.registro.write_bytes(texto.encode("utf-8"))
        print(f"gravado {args.registro}")
        return 0
    return 1 if subidas or descidas else 0


if __name__ == "__main__":
    sys.exit(main())
