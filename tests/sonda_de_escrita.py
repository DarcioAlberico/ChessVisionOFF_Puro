"""A escrita **deste** processo nos dados de quem roda a suíte, vista por auditoria (S-805).

**A pergunta da guarda é "este processo de teste escreveu nos dados reais?", e não "alguém
escreveu?".** Até 2026-11-09 a guarda comparava a listagem e o `mtime` do `data/` antes e depois, e
isso responde à segunda: com o programa aberto no checkout principal, rotulando diagramas -- uma
amostra nova em `data/samples/` a cada ~15 s --, a suíte rodada num worktree acusava ERROR na
desmontagem de testes que não tinham gravado nada. O efeito no disco não diz de quem ele é.

**A resposta vem do `sys.addaudithook`**, que o interpretador chama *antes* de cada operação
auditada deste processo: `open` com flags de escrita (`w`, `a`, `x`, `+`, ou `O_WRONLY`, `O_RDWR`,
`O_CREAT`, `O_APPEND`, `O_TRUNC` no `os.open`), `os.remove`, `os.rename` (que é também o evento do
`os.replace`), `os.mkdir`, `os.rmdir`, `shutil.rmtree`, `os.truncate`, `os.utime`, `os.chmod`, os
destinos de `os.link`/`os.symlink`, e o `sqlite3.connect` que não seja `mode=ro` -- é por ele que
passa o cache de posições, que o SQLite grava em C sem nenhum `open` do Python. Como o evento sai
antes da operação, a tentativa que falha também conta.

**Um gancho de auditoria não sai mais**: `instalar` põe um só por processo, e ele só anota numa
lista. Quem confere e limpa a lista é a fixture de cada teste, no `conftest`.

**O que ele não vê.** (a) Um **subprocesso** lançado por um teste é outro interpretador, e o gancho
do pai não chega lá -- é o que tira o falso positivo, e é também um ponto cego: o filho é protegido
pelo `CVOFF_DATA_DIR` e pelo `CVOFF_PGN_DATABASE_DIR` desviados, que ele herda pelo
`tests/subprocesso.py`, e não por esta sonda. (b) Código em C que abre arquivo por conta própria --
`QImage.save` do Qt, `cv2.imwrite`, o `doc.save` do PyMuPDF direto no destino -- não levanta evento;
o projeto grava imagem pelo `atomic_io` (um `open` do Python) e troca arquivo por `os.replace`, que
são vistos. (c) `os.stat` não tem evento: ler e existir ficam fora, e não são escrita.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

FLAGS_DE_ESCRITA = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
"""Qualquer uma destas no `open` é escrita. O `open` do Python as calcula do modo (`"w"` dá
`O_WRONLY|O_CREAT|O_TRUNC`), e o `os.open` as recebe cruas: os dois chegam ao mesmo evento."""

CAMINHOS_ESCRITOS: dict[str, tuple[int, ...]] = {
    "os.remove": (0,),
    "os.rename": (0, 1),
    "os.mkdir": (0,),
    "os.rmdir": (0,),
    "shutil.rmtree": (0,),
    "os.truncate": (0,),
    "os.utime": (0,),
    "os.chmod": (0,),
    "os.link": (1,),
    "os.symlink": (1,),
}
"""Evento de auditoria → posições dos argumentos que são caminho mexido. Renomear tira de um lugar e
põe noutro, e os dois contam."""

EVENTOS = frozenset({"open", "sqlite3.connect", *CAMINHOS_ESCRITOS})
"""O filtro da primeira linha do gancho: ele é chamado para todo evento do processo -- cada import,
cada `compile` --, e o que não está aqui sai sem custo além de uma consulta."""


@dataclass(frozen=True)
class Escrita:
    """Uma escrita vista: o caminho normalizado, o evento que a levantou e a thread em que ela correu."""

    caminho: str
    evento: str
    thread: int

    def descrita(self) -> str:
        onde = "thread principal" if self.thread == threading.main_thread().ident else f"thread {self.thread}"
        return f"{self.caminho} ({self.evento}, {onde})"


def normalizado(caminho: object) -> str | None:
    """O caminho absoluto em caixa do sistema; `None` para descritor de arquivo ou nome que não é caminho.

    **Sem `resolve()`**: o gancho roda dentro de cada operação auditada, e quem resolve link chama mais
    operações. `abspath` e `normcase` são aritmética de texto.
    """
    if not isinstance(caminho, (str, bytes, os.PathLike)):
        return None
    try:
        return os.path.normcase(os.path.abspath(os.fsdecode(caminho)))
    except (TypeError, ValueError):  # nome com NUL, ou um PathLike que não devolve texto
        return None


def caminho_do_banco(banco: object) -> str | None:
    """O arquivo que o `sqlite3.connect` abre para escrever, ou `None` (memória, ou URI `mode=ro`)."""
    if not isinstance(banco, (str, bytes, os.PathLike)):
        return None
    nome = os.fsdecode(banco)
    if nome in ("", ":memory:"):
        return None
    if nome.startswith("file:"):
        corpo, _, consulta = nome[len("file:") :].partition("?")
        if "mode=ro" in consulta.split("&"):
            return None
        nome = unquote(corpo)
    return nome


def caminhos_escritos(evento: str, args: tuple[object, ...]) -> tuple[object, ...]:
    """Os caminhos que o evento escreve; vazio para leitura e para evento que não escreve."""
    if evento == "open":
        flags = args[2] if len(args) > 2 else 0
        return (args[0],) if isinstance(flags, int) and flags & FLAGS_DE_ESCRITA else ()
    if evento == "sqlite3.connect":
        banco = caminho_do_banco(args[0]) if args else None
        return () if banco is None else (banco,)
    return tuple(args[i] for i in CAMINHOS_ESCRITOS.get(evento, ()) if i < len(args))


class Sonda:
    """O gancho de auditoria e a lista do que ele viu cair dentro das pastas vigiadas."""

    def __init__(self) -> None:
        self.raizes: tuple[str, ...] = ()
        self._escritas: list[Escrita] = []

    def vigiar(self, pastas: Iterable[Path]) -> None:
        """As pastas cuja escrita é anotada: cada uma como escrita e como resolvida, se for um link."""
        formas = set()
        for pasta in pastas:
            for forma in (pasta, pasta.resolve()):
                texto = normalizado(forma)
                if texto is not None:
                    formas.add(texto.rstrip(os.sep))
        self.raizes = tuple(sorted(formas))

    def dentro(self, caminho: str) -> bool:
        return any(caminho == raiz or caminho.startswith(raiz + os.sep) for raiz in self.raizes)

    def __call__(self, evento: str, args: tuple[object, ...]) -> None:
        if evento not in EVENTOS or not self.raizes:
            return
        for bruto in caminhos_escritos(evento, args):
            caminho = normalizado(bruto)
            if caminho is not None and self.dentro(caminho):
                self._escritas.append(Escrita(caminho, evento, threading.get_ident()))

    def recolher(self) -> list[Escrita]:
        """O que foi visto desde a última colheita, e a lista esvaziada desse tanto.

        Esvazia só o que leu: uma thread que anote entre a cópia e o corte fica para a próxima.
        """
        vistas = list(self._escritas)
        del self._escritas[: len(vistas)]
        return vistas


SONDA = Sonda()
_INSTALADA: list[bool] = []


def instalar(pastas: Iterable[Path]) -> Sonda:
    """Põe o gancho -- uma vez por processo, porque não há como tirá-lo -- e diz o que ele vigia."""
    SONDA.vigiar(pastas)
    if not _INSTALADA:
        sys.addaudithook(SONDA)
        _INSTALADA.append(True)
    return SONDA
