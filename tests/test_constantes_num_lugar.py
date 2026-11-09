"""Caminho e padrão escritos uma vez só em `src/` (S-862).

O DPI padrão era o literal `220` em ~30 lugares, e os nomes de arquivo `char_meta.json`,
`char_classifier.pt`, `field_set.jsonl` e `texto_conflitos.json` eram escritos à mão em dois ou
três módulos cada. Hoje as cópias concordam; o defeito é o dia em que uma delas mudar sozinha.

A guarda lê a árvore sintática, e não o texto: docstring e comentário citam esses nomes à vontade
(é como se explica o que um módulo faz), e o que ela cobra é o **literal de código**.
"""

from __future__ import annotations

import ast
import unittest
from collections.abc import Iterator
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PACOTE = RAIZ / "src" / "chess_diagram_ocr"

NOMES_DE_ARQUIVO = ("char_classifier.pt", "char_meta.json", "field_set.jsonl", "texto_conflitos.json")

DONO_DO_DPI = PACOTE / "config.py"
DPI_PADRAO = 220


def _modulos() -> Iterator[tuple[Path, ast.Module]]:
    for arquivo in sorted(PACOTE.rglob("*.py")):
        yield arquivo, ast.parse(arquivo.read_bytes(), filename=str(arquivo))


def _docstrings(arvore: ast.Module) -> set[int]:
    """`id` dos nós que são docstring: a primeira expressão-string de módulo, classe e função, e
    a string solta logo depois de uma atribuição (a convenção de documentar constante deste repo)."""
    ids: set[int] = set()
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if not isinstance(corpo, list):
            continue
        for instrucao in corpo:
            if (
                isinstance(instrucao, ast.Expr)
                and isinstance(instrucao.value, ast.Constant)
                and isinstance(instrucao.value.value, str)
            ):
                ids.add(id(instrucao.value))
    return ids


def _literais(arvore: ast.Module, texto: str) -> int:
    docs = _docstrings(arvore)
    return sum(
        1
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and no.value == texto and id(no) not in docs
    )


def _e_o_dpi(no: ast.AST) -> bool:
    """`220` ou `220.0` como literal -- e não `True`, que também é `int`."""
    return (
        isinstance(no, ast.Constant)
        and isinstance(no.value, (int, float))
        and not isinstance(no.value, bool)
        and no.value == DPI_PADRAO
    )


def _vale_220(no: ast.AST | None) -> bool:
    """O literal sozinho, ou como o último recurso de um `or` (`dpi or 220`)."""
    if no is None:
        return False
    if isinstance(no, ast.BoolOp) and isinstance(no.op, ast.Or):
        return any(_e_o_dpi(valor) for valor in no.values)
    return _e_o_dpi(no)


def _chama_dpi(alvo: ast.AST) -> bool:
    """`dpi`, `DPI`, `self._dpi`: o nome é o DPI, e não uma medida de tela que por acaso vale 220."""
    nome = alvo.id if isinstance(alvo, ast.Name) else alvo.attr if isinstance(alvo, ast.Attribute) else ""
    return nome.lstrip("_").lower() in ("dpi", "default_dpi")


def _dpi_220(arvore: ast.Module) -> Iterator[int]:
    """Linhas onde algo chamado `dpi` recebe `220` escrito à mão."""
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = no.args
            posicionais = args.posonlyargs + args.args
            pares = list(zip(posicionais[len(posicionais) - len(args.defaults):], args.defaults, strict=True))
            pares += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True) if d is not None]
            for arg, padrao in pares:
                if arg.arg.lstrip("_").lower() == "dpi" and _vale_220(padrao):
                    yield padrao.lineno
        elif isinstance(no, ast.AnnAssign) and _chama_dpi(no.target) and _vale_220(no.value):
            yield no.lineno
        elif isinstance(no, ast.Assign) and any(_chama_dpi(t) for t in no.targets) and _vale_220(no.value):
            yield no.lineno
        elif isinstance(no, ast.keyword) and no.arg is not None and no.arg.lstrip("_").lower() == "dpi":
            if _vale_220(no.value):
                yield no.value.lineno


class ConstantesNumLugarTests(unittest.TestCase):
    def test_cada_nome_de_arquivo_e_escrito_uma_vez(self) -> None:
        contagem = dict.fromkeys(NOMES_DE_ARQUIVO, 0)
        onde: dict[str, list[str]] = {nome: [] for nome in NOMES_DE_ARQUIVO}
        for arquivo, arvore in _modulos():
            for nome in NOMES_DE_ARQUIVO:
                n = _literais(arvore, nome)
                if n:
                    contagem[nome] += n
                    onde[nome].append(arquivo.relative_to(PACOTE).as_posix())
        for nome in NOMES_DE_ARQUIVO:
            with self.subTest(nome=nome):
                self.assertEqual(1, contagem[nome], f"{nome} escrito em {onde[nome]}")

    def test_o_dpi_padrao_tem_um_dono(self) -> None:
        achados = [
            f"{arquivo.relative_to(PACOTE).as_posix()}:{linha}"
            for arquivo, arvore in _modulos()
            if arquivo != DONO_DO_DPI
            for linha in _dpi_220(arvore)
        ]
        self.assertEqual([], achados, "o DPI padrão é `config.DEFAULT_DPI`")

    def test_a_guarda_do_dpi_nao_e_vacua(self) -> None:
        """Ela acha `dpi` com 220, e não acha as medidas de tela nem a régua calibrada a 220."""
        exemplos = {
            "def f(dpi: int = 220): ...": 1,
            "def f(*, dpi: float = 220.0): ...": 1,
            "@dataclass\nclass C:\n    dpi: int = 220\n": 1,
            "DPI = 220.0\n": 1,
            "self._dpi = dpi or 220\n": 1,
            "f(dpi=220)\n": 1,
            "DEFAULT_DPI = 220\n": 1,
            "LADO_DO_RECORTE = 220\n": 0,
            "DPI_DA_REGUA = 220\n": 0,
            "def f(lado: int = 220): ...": 0,
            "def f(dpi: bool = True): ...": 0,
        }
        for fonte, esperado in exemplos.items():
            with self.subTest(fonte=fonte):
                self.assertEqual(esperado, len(list(_dpi_220(ast.parse(fonte)))))

    def test_o_lado_do_descritor_vem_do_dedupe(self) -> None:
        """`"lado_descritor": 24` gravado à mão no relatório ao lado de `dedupe.LADO_DESCRITOR`."""
        achados = []
        for arquivo, arvore in _modulos():
            for no in ast.walk(arvore):
                if not isinstance(no, ast.Dict):
                    continue
                for chave, valor in zip(no.keys, no.values, strict=True):
                    if (
                        isinstance(chave, ast.Constant)
                        and chave.value == "lado_descritor"
                        and isinstance(valor, ast.Constant)
                    ):
                        achados.append(f"{arquivo.relative_to(PACOTE).as_posix()}:{valor.lineno}")
        self.assertEqual([], achados)


if __name__ == "__main__":
    unittest.main()
