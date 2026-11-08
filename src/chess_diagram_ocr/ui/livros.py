r"""A identidade de um livro pelo caminho: `ChaveDoLivro` (S-827).

"É o mesmo livro?" era decidido em sete lugares -- a galeria (`normcase`), a aba Texto
(`casefold`, e `resolve ==` com `.lower()` na falha), o histórico de páginas (só `resolve`), a
troca de livro da janela (`!=` cru), a fusão da fila de revisão (`source_pdf ==` cru) -- e, para
as bases `.pgn`, no diálogo de bases. Com `resolve` funcionando eles concordavam, porque ele
devolve a caixa do disco e tira o `..`. **Num caminho de rede fora do ar** `resolve` levanta, e
cada um caía num atalho diferente: `PDF\sub\..\Livro.pdf` e `PDF/Livro.pdf` eram o mesmo livro
para um e dois livros para outro.

A regra, num lugar só:

1. `resolve` quando dá (o disco diz a caixa, o atalho simbólico e o `..`);
2. quando não dá, `os.path.abspath`, que tira o `..`, completa o relativo e acerta a barra **sem
   tocar no disco** -- o caminho que não resolve não pode virar outro livro por isso;
3. `os.path.normcase` por cima: no Windows o sistema de arquivos não distingue caixa nem barra, e
   no POSIX distingue as duas, que é o que `normcase` já sabe.

"Nenhum livro" (`None` ou `""`) não tem chave: `""` não é a pasta atual, e dois "nenhum" não são o
mesmo livro (`mesmo_livro`). Quem precisa saber se *a tela mudou* compara as chaves, e
`None == None` diz "continua sem livro".
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ChaveDoLivro", "caminho_canonico", "chave_do_livro", "mesmo_livro"]

Caminho = str | os.PathLike[str]


@dataclass(frozen=True)
class ChaveDoLivro:
    """A identidade de um livro. Igual quando é o mesmo arquivo; serve de chave de dicionário.

    `texto` é o caminho canônico já em `normcase`: serve para comparar e para guardar, **não** para
    mostrar (no Windows ele sai em minúsculas). Para mostrar, ou para gravar um caminho que alguém
    vai abrir, use `caminho_canonico`.
    """

    texto: str

    @property
    def curta(self) -> str:
        """Oito dígitos hexadecimais que seguem a identidade: o sufixo de nome que separa dois
        livros de mesmo nome em pastas diferentes (filas, miniaturas, saídas do lote)."""
        return hashlib.sha1(self.texto.encode("utf-8")).hexdigest()[:8]

    def __str__(self) -> str:
        return self.texto


def caminho_canonico(caminho: Caminho) -> str:
    """O caminho absoluto do livro, na caixa do disco quando ele resolve. Ver o docstring do módulo."""
    bruto = os.fspath(caminho)
    try:
        return str(Path(bruto).resolve())
    except OSError:  # caminho de rede fora do ar, ou que o sistema recusa resolver
        return os.path.abspath(bruto)


def chave_do_livro(caminho: Caminho | None) -> ChaveDoLivro | None:
    """A chave do livro em `caminho`, ou `None` sem livro (`None` ou `""`)."""
    if caminho is None or not os.fspath(caminho):
        return None
    return ChaveDoLivro(os.path.normcase(caminho_canonico(caminho)))


def mesmo_livro(um: Caminho | None, outro: Caminho | None) -> bool:
    """O mesmo livro, apesar de `..`, de barra invertida e de caixa, e com o caminho que não resolve.

    Sem livro de um dos lados, não: "nenhum livro" não é o mesmo livro que nada.
    """
    chave = chave_do_livro(um)
    return chave is not None and chave == chave_do_livro(outro)
