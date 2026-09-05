"""Onde os exercícios de tática ficam no disco: um arquivo por livro (S-539).

**O desenho é o de `estudo_arquivo.py`, e a chave é literalmente a mesma função.** Um livro tem uma
sala de estudo e uma coleção de exercícios, e as duas têm de responder ao mesmo nome: `chave_de` é
importada de lá em vez de recopiada, e é isso que faz `Reinfeld_1001_a1b2c3d4e5.pgn` e
`Reinfeld_1001_a1b2c3d4e5.json` serem visivelmente do mesmo livro na mesma pasta `data/`.

**JSON e não PGN, e é a única divergência.** O estudo é uma árvore de variantes com comentário e
símbolo -- o PGN foi feito para isso, e o arquivo abre no ChessBase. Um exercício é uma FEN, uma
lista de lances e a procedência; escrevê-lo em PGN caberia, mas a procedência viraria header de
invenção nossa (`[Diagram]`, `[Solucao]`) e a leitura passaria a depender de o `chess.pgn` preservar
headers que só este programa entende. O que se ganharia -- abrir no ChessBase -- não é o que se faz
com um exercício: ele é para treinar aqui, e quem quiser o PGN exporta a sala.

**Gravação atômica, como todo arquivo de trabalho deste projeto** (S-25): a extração de um livro de
mil diagramas leva minutos, e uma interrupção no `write_text` deixaria zero byte no lugar dela.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from pathlib import Path

from .atomic_io import atomic_write_json
from .config import PROJECT_ROOT
from .estudo_arquivo import chave_de
from .taticas import Exercicio

logger = logging.getLogger(__name__)

__all__ = [
    "ESQUEMA",
    "EXTENSAO",
    "PASTA_PADRAO",
    "caminho_de",
    "carregar",
    "carregar_tudo",
    "chave_de",
    "gravar",
    "livros",
]

PASTA_PADRAO = PROJECT_ROOT / "data" / "taticas"
"""Ao lado de `data/estudos/`, e fora do git pela mesma razão: é o que saiu de um livro que o
repositório não tem."""

EXTENSAO = ".json"

ESQUEMA = 1
"""Versão do formato. Sobe quando um campo muda de significado, não quando nasce -- é a regra de
`text/pagina.ESQUEMA`, e campo novo com padrão é compatível nos dois sentidos."""


def caminho_de(livro: str | Path, *, pasta: Path | None = None) -> Path:
    """Onde moram os exercícios daquele livro."""
    raiz = Path(pasta) if pasta is not None else PASTA_PADRAO
    return raiz / f"{chave_de(livro)}{EXTENSAO}"


def gravar(
    livro: str | Path, exercicios: Sequence[Exercicio], *, pasta: Path | None = None
) -> Path | None:
    """Grava os exercícios daquele livro. `None` quando não há livro a que atá-los.

    **Coleção que esvaziou apaga o arquivo**, como a sala de estudo faz: um JSON de zero exercícios
    no disco faria a tela seguinte abrir vazia e quem a abriu concluir que a extração não funciona.
    """
    if not str(livro or "").strip():
        return None
    destino = caminho_de(livro, pasta=pasta)
    lista = list(exercicios)
    if not lista:
        if destino.exists():
            try:
                destino.unlink()
            except OSError as erro:  # pragma: no cover - arquivo em uso
                logger.debug("Coleção vazia não pôde ser apagada (%s): %s", destino, erro)
        return None
    atomic_write_json(
        destino,
        {
            "esquema": ESQUEMA,
            "livro": str(livro),
            "exercicios": [exercicio.para_json() for exercicio in lista],
        },
    )
    return destino


def carregar(livro: str | Path, *, pasta: Path | None = None) -> list[Exercicio]:
    """Os exercícios daquele livro. Lista vazia quando não há arquivo -- ausência é o caso normal.

    **Um exercício ilegível não derruba os outros**, que é a regra de `estudo_arquivo.carregar`:
    uma coleção de 300 em que o 12 está corrompido ainda tem 299 exercícios dentro.
    """
    origem = caminho_de(livro, pasta=pasta)
    if not origem.exists():
        return []
    try:
        dados = json.loads(origem.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        logger.warning("A coleção de táticas não pôde ser lida (%s): %s", origem, erro)
        return []
    return _exercicios_de(dados, origem.name)


def _exercicios_de(dados: object, onde: str) -> list[Exercicio]:
    if not isinstance(dados, dict):
        logger.warning("%s: esperava um objeto no topo.", onde)
        return []
    if int(dados.get("esquema", ESQUEMA)) > ESQUEMA:
        logger.warning("%s: esquema mais novo que o que esta versão lê.", onde)
        return []
    achados: list[Exercicio] = []
    for bruto in dados.get("exercicios", []):
        try:
            exercicio = Exercicio.de_json(bruto)
        except (TypeError, ValueError) as erro:
            logger.debug("Exercício ilegível em %s: %s", onde, erro)
            continue
        if exercicio.fen and exercicio.lances:
            achados.append(exercicio)
    return achados


def livros(*, pasta: Path | None = None) -> list[Path]:
    """Os arquivos de coleção que existem, em ordem de nome. Pasta ausente devolve vazio."""
    raiz = Path(pasta) if pasta is not None else PASTA_PADRAO
    if not raiz.is_dir():
        return []
    return sorted(raiz.glob(f"*{EXTENSAO}"))


def carregar_tudo(*, pasta: Path | None = None) -> list[Exercicio]:
    """Todos os exercícios de todos os livros extraídos, na ordem dos arquivos.

    É o que a agenda do dia consulta (S-540): ela agenda por chave, e a chave já traz o livro
    dentro -- então a fila de hoje pode misturar dois livros sem que nada se confunda.
    """
    achados: list[Exercicio] = []
    for arquivo in livros(pasta=pasta):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError) as erro:
            logger.warning("A coleção %s não pôde ser lida: %s", arquivo.name, erro)
            continue
        achados.extend(_exercicios_de(dados, arquivo.name))
    return achados


def por_chave(exercicios: Iterable[Exercicio]) -> dict[str, Exercicio]:
    """Os exercícios indexados pela chave da procedência -- o vínculo com a agenda (S-540)."""
    return {exercicio.chave: exercicio for exercicio in exercicios}
