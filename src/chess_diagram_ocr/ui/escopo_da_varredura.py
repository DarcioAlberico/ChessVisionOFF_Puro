"""Quais livros a varredura percorre, e a única regra que isso tem (S-119/S-503).

`ScanScope` e `books_in_folder`. As duas eram puras dentro de `ui/scan_scope.py` -- o docstring
de `skip_complete` já dizia, com todas as letras, que a regra é *"de negócio, não de tela"* --, e
mesmo assim ninguém as lia sem carregar o Tk junto: `ScanScopeDialog` herda de `tk.Toplevel`, e
classe-base é avaliada na importação.

**O `ScanScope` atravessa três módulos**, e é o que torna o endereço importante: a Galeria monta,
a fila de revisão recebe, e o segundo frontend precisa dos dois. Uma segunda classe com o mesmo
nome faria `isinstance` responder diferente conforme a janela, que é o tipo de defeito que não
aparece no teste de nenhuma das duas.

`ui/scan_scope.py` reexportava tudo o que está aqui, e saiu no corte do Tk (S-506). Quem consome
agora é `qt/dialogos.py` e `qt/painel_da_galeria.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import DEFAULT_PDF_DIR

__all__ = ["ABERTO", "ESCOLHER", "PASTA", "ScanScope", "books_in_folder"]

ABERTO = "aberto"
ESCOLHER = "escolher"
PASTA = "pasta"
@dataclass(frozen=True)
class ScanScope:
    """Os livros escolhidos, e de que pergunta eles vieram."""

    kind: str
    books: tuple[Path, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.books

    @property
    def skip_complete(self) -> bool:
        """Pular o livro cujo índice já está completo?

        Mais de um livro é "varra o que falta"; um livro é "varra este". Ver o cabeçalho do
        módulo -- é a única regra deste arquivo, e ela é de negócio, não de tela.
        """
        return len(self.books) > 1


def books_in_folder(directory: Path = DEFAULT_PDF_DIR) -> list[Path]:
    """Os `.pdf` da pasta, em ordem de nome. Pasta que não existe é lista vazia, e não erro.

    Ordenado pelo mesmo motivo do `cvoff-scan`: a varredura de um acervo é interrompida e
    retomada, e uma ordem estável faz "continuar de onde parou" significar alguma coisa.
    """
    pasta = Path(directory)
    if not pasta.is_dir():
        return []
    return sorted(caminho for caminho in pasta.glob("*.pdf") if caminho.is_file())


