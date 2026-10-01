"""O baralho de revisão no disco: um arquivo para o acervo inteiro (S-540).

**Um só, e não um por livro -- ao contrário das táticas.** A pergunta que este arquivo responde é
*"o que eu tenho para revisar hoje?"*, e ela é do dia e não do livro: uma sessão de segunda-feira
mistura três exercícios do Reinfeld com dois estudos do Dvoretsky, e um arquivo por livro obrigaria
a abrir onze arquivos para montar uma fila de quinze itens. O vínculo com o livro não se perde
porque ele está **dentro da chave** (`taticas.Procedencia.chave`).

**Escrita atômica e por sessão inteira**, e não a cada item revisto: o arquivo é reescrito quando a
sessão fecha ou quando a fila esvazia, na forma que `estudo_arquivo.py` já usa. O custo é o do
arquivo -- mil itens com vinte revisões cada dão **2,1 MB** de JSON, medido em
`tests/test_revisao_espacada.py` --, e `atomic_write_json` escreve isso em milissegundos.

**A estabilidade é gravada com quatro casas**, e é o único arredondamento: 0,0001 dia são 8,6
segundos, e o arquivo continua legível a olho. Uma segunda gravação do que se leu dá byte a byte
o mesmo arquivo, que é a propriedade que importa num arquivo relido todo dia.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path

from .atomic_io import atomic_write_json
from .config import PROJECT_ROOT
from .revisao_espacada import Estado

logger = logging.getLogger(__name__)

__all__ = ["CAMINHO_PADRAO", "ESQUEMA", "Baralho", "carregar", "gravar"]

CAMINHO_PADRAO = PROJECT_ROOT / "data" / "revisao.json"
"""Em `data/`, como todo artefato de trabalho, e fora do git: é o histórico de estudo de alguém."""

ESQUEMA = 1

Baralho = dict[str, Estado]
"""Chave do item -> o estado dele. É o que `revisao_espacada.agenda` recebe."""


def carregar(*, caminho: Path | None = None) -> Baralho:
    """O baralho gravado. Vazio quando não há arquivo -- o primeiro dia é o caso normal.

    **Um estado ilegível não derruba os outros.** Um baralho de 600 itens em que um tem data
    corrompida ainda tem 599 agendamentos dentro, e perdê-los todos por causa de um seria perder
    meses de revisão -- que é o único dado deste programa que não se refaz varrendo o livro de novo.
    """
    origem = Path(caminho) if caminho is not None else CAMINHO_PADRAO
    if not origem.exists():
        return {}
    try:
        dados = json.loads(origem.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        logger.warning("O baralho de revisão não pôde ser lido (%s): %s", origem, erro)
        return {}
    if not isinstance(dados, dict) or int(dados.get("esquema", ESQUEMA)) > ESQUEMA:
        logger.warning("%s: esquema desconhecido ou topo que não é objeto.", origem.name)
        return {}

    baralho: Baralho = {}
    for bruto in dados.get("itens", []):
        try:
            estado = Estado.de_json(bruto)
        except (TypeError, ValueError) as erro:
            logger.debug("Item ilegível no baralho: %s", erro)
            continue
        if estado.chave:
            baralho[estado.chave] = estado
    return baralho


def gravar(baralho: Iterable[Estado] | Baralho, *, caminho: Path | None = None) -> Path:
    """Grava o baralho inteiro. Devolve o caminho, sempre -- inclusive o do baralho vazio.

    **Vazio não apaga o arquivo**, e é a diferença para `estudo_arquivo` e `taticas_arquivo`. Lá o
    vazio quer dizer "não há nada a guardar"; aqui ele pode querer dizer "a pessoa apagou o
    histórico", e um apagamento que deixa o arquivo antigo no disco ressuscitaria o histórico na
    abertura seguinte.
    """
    destino = Path(caminho) if caminho is not None else CAMINHO_PADRAO
    estados = list(baralho.values()) if isinstance(baralho, dict) else list(baralho)
    atomic_write_json(
        destino,
        {
            "esquema": ESQUEMA,
            "itens": [estado.para_json() for estado in sorted(estados, key=lambda e: e.chave)],
        },
    )
    return destino
