"""O arquivo da sala de estudo: um PGN por livro, uma partida por diagrama (S-271).

**O que se perdia.** Nenhum dos 20 campos do `AppState` é do estudo, e a única saída era um
`filedialog` que dependia de alguém lembrar de clicar. Fechar o programa -- ou o Tk cair numa
thread, que é o caso que `BusyRegistry.loses_work` já trata -- levava a análise da tarde junto.

O desenho é o de `text/rascunho.py` (S-255), e ele já vinha medido: grava por **inatividade** e não
por relógio, só quando está sujo, com `atomic_write_text`, com chave estável derivada do caminho
**resolvido**. O que muda é a granularidade.

## Um arquivo por livro, e não um por diagrama

Três razões, e a terceira é a que decide:

1. dezenas de arquivos por livro numa pasta é depósito, não coleção;
2. a pergunta que se faz depois é *"o que eu já estudei neste livro?"*, e ela se responde abrindo
   **um** arquivo;
3. **um PGN com muitas partidas é o que o ChessBase e o Scid chamam de base.** O arquivo que sai
   daqui abre nos dois, com `SourcePDF`, `Page` e `Diagram` dizendo de onde cada estudo veio. É a
   regra 2 da SPEC_ESTUDO levada até o fim: o formato não é nosso.

O preço é reescrever o arquivo inteiro a cada gravação. Medido pelo tamanho: 50 estudos de 30
meios-lances com comentário dão ~90 KB, e `atomic_write_text` escreve isso em milissegundos. Se um
dia não der, o conserto é gravar por lote -- não é trocar de formato.

## A recuperação não é uma pergunta, e é a diferença para a S-255

Lá o rascunho concorre com uma releitura que sai de graça: perguntar "quer o rascunho de ontem?" é
razoável porque a resposta "não" ainda deixa a pessoa com a folha lida. Aqui **não há releitura** --
não existe outro lugar de onde a análise possa vir. Perguntar seria oferecer apagar o trabalho.
Abrir o livro carrega a sala, e pronto.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from pathlib import Path
from typing import TextIO

import chess.pgn

from .atomic_io import atomic_write_text
from .config import PROJECT_ROOT
from .estudo import Estudo, Sala

logger = logging.getLogger(__name__)

__all__ = [
    "ESPERA_SEGUNDOS",
    "EXTENSAO",
    "PASTA_PADRAO",
    "caminho_de",
    "carregar",
    "chave_de",
    "estudos_de_pgn",
    "gravar",
]

PASTA_PADRAO = PROJECT_ROOT / "data" / "estudos"
"""Onde as salas moram. Em `data/`, como todo artefato de trabalho deste projeto, e fora do git:
é análise de alguém sobre um livro que nem está no repositório."""

EXTENSAO = ".pgn"
"""E é `.pgn` de verdade, não um `.pgn` nosso: o arquivo abre no ChessBase e no Scid como está."""

ESPERA_SEGUNDOS = 4.0
"""Quanto tempo de **inatividade** antes de gravar. É o número da S-255, e pela mesma razão: mais
longo que a pausa entre dois lances e mais curto que a pausa entre duas ideias."""

_SUFIXO_DA_CHAVE = 10
_LIMPEZA = re.compile(r"[^A-Za-z0-9_.-]+")


def chave_de(documento: str | Path) -> str:
    """A chave estável daquele livro: nome legível mais a impressão do caminho resolvido.

    **Resolvido**, como `ui/state._history_key` e `text/rascunho.chave_de`: dois livros de mesmo nome
    em pastas diferentes têm salas diferentes, e é exatamente o caso que aqueles módulos já tratam.
    """
    bruto = str(documento or "sem-documento")
    try:
        bruto = str(Path(bruto).resolve())
    except OSError:  # pragma: no cover - caminho de rede fora do ar
        pass
    impressao = hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:_SUFIXO_DA_CHAVE]
    nome = _LIMPEZA.sub("_", Path(bruto).stem)[:40] or "estudo"
    return f"{nome}_{impressao}"


def caminho_de(documento: str | Path, *, pasta: Path | None = None) -> Path:
    """Onde a sala daquele livro mora."""
    raiz = Path(pasta) if pasta is not None else PASTA_PADRAO
    return raiz / f"{chave_de(documento)}{EXTENSAO}"


def para_pgn(sala: Sala) -> str:
    """A sala inteira como um PGN de muitas partidas, em ordem de página e diagrama."""
    return "\n\n".join(estudo.para_pgn() for estudo in sala.estudos())


def gravar(sala: Sala, *, pasta: Path | None = None) -> Path | None:
    """Grava a sala daquele livro. `None` quando não há livro a que atá-la.

    Sala sem documento não tem chave estável: gravá-la num nome inventado criaria um arquivo que
    ninguém acha de volta, que é lixo com aparência de proteção. É a mesma decisão de
    `text/rascunho.gravar`, que devolve `None` para documento sem folha de origem.

    **Sala que esvaziou apaga o arquivo.** Deixar um PGN de zero partidas no disco faria a próxima
    abertura carregar nada e o usuário concluir que a gravação não funciona.
    """
    if not sala.documento:
        return None
    destino = caminho_de(sala.documento, pasta=pasta)
    corpo = para_pgn(sala)
    if not corpo:
        if destino.exists():
            try:
                destino.unlink()
            except OSError as erro:  # pragma: no cover - arquivo em uso
                logger.debug("Sala vazia não pôde ser apagada (%s): %s", destino, erro)
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destino, corpo + "\n")
    return destino


def carregar(documento: str | Path, *, pasta: Path | None = None) -> Sala:
    """A sala daquele livro. Sala vazia quando não há arquivo -- ausência é o caso normal.

    Uma partida ilegível **não derruba as outras**: ela vira uma linha de log e a leitura segue. Um
    PGN de 50 estudos em que o 12 está corrompido ainda tem 49 tardes de trabalho dentro.
    """
    sala = Sala(str(documento or ""))
    origem = caminho_de(documento, pasta=pasta)
    if not origem.exists():
        return sala

    try:
        texto = origem.read_text(encoding="utf-8", errors="replace")
    except OSError as erro:  # pragma: no cover - arquivo em uso
        logger.warning("Sala de estudo não pôde ser lida (%s): %s", origem, erro)
        return sala

    for estudo in estudos_de_pgn(texto, documento=str(documento or ""), onde=origem.name):
        if not sala.guardar(estudo):
            logger.debug("Estudo sem âncora ou sem lance descartado de %s", origem.name)
    return sala


def estudos_de_pgn(
    texto: str | TextIO,
    *,
    documento: str = "",
    onde: str = "PGN colado",
    limite: int | None = None,
) -> list[Estudo]:
    """As partidas daquele PGN, uma por estudo, na ordem em que estão no arquivo (S-288).

    **Uma partida ilegível não derruba as outras**: ela vira uma linha de log e a leitura segue. Um
    PGN de 50 estudos em que o 12 está corrompido ainda tem 49 tardes de trabalho dentro -- e um PGN
    de outra pessoa, aberto pelo comando da S-288, tem ainda mais motivo para ser lido até o fim.

    `onde` só aparece no log, e existe porque este laço serve a dois chamadores: o arquivo da sala e
    o `.pgn` que alguém abriu. "Partida ilegível" sem dizer de onde é a mensagem que não ajuda.

    **`texto` aceita um fluxo aberto (S-307).** Ler um `.pgn` inteiro para a memória antes de
    fatiá-lo é o que fazia a aba engasgar: `pgn_database/` é a pasta que este projeto manda usar,
    e tem arquivos de 8,6 GB e 10,3 GB. Passar o arquivo aberto faz o `read_game` consumir sob
    demanda, que é o que ele sempre soube fazer.

    **`limite` é parâmetro e não constante, e o padrão é "sem limite".** Este mesmo laço lê o
    arquivo da sala em `carregar`: um teto global truncaria em silêncio a sala de quem tem mais
    estudos que o teto -- perda de análise humana, o oposto do que o item quer. Quem trunca é
    quem abre PGN de fora, e é ele quem avisa na tela.
    """
    fluxo: TextIO = io.StringIO(texto or "") if isinstance(texto, str) else texto
    achados: list[Estudo] = []
    while True:
        if limite is not None and len(achados) >= limite:
            logger.info("%s: leitura parada em %d partidas pelo teto pedido.", onde, limite)
            break
        try:
            jogo = chess.pgn.read_game(fluxo)
        except Exception as erro:  # noqa: BLE001 - PGN de fora pode falhar de muitas formas
            logger.warning("Partida ilegível em %s: %s", onde, erro)
            break
        if jogo is None:
            break
        if not _tem_conteudo(jogo):
            # **`read_game` devolve uma partida para qualquer texto**: sem lance, sem `[FEN]` e com
            # os headers de fábrica. É o que sai de um `.txt` qualquer, e abri-lo como estudo daria
            # um tabuleiro na posição inicial dizendo que veio de um arquivo de xadrez.
            logger.debug("Bloco sem lance e sem posição descartado de %s", onde)
            continue
        achados.append(Estudo.de_jogo(jogo, documento=documento))
    return achados


def _tem_conteudo(jogo: chess.pgn.Game) -> bool:
    """A partida diz alguma coisa: tem lance, tem posição declarada ou tem anotação na raiz."""
    if jogo.variations or jogo.nags or (jogo.comment or "").strip():
        return True
    return bool(jogo.headers.get("FEN"))
