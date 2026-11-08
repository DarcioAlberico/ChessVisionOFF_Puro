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
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

import chess.pgn

from .arquivo_do_dono import ConteudoIlegivel, Leitura, Lida, gravavel, ler
from .atomic_io import atomic_write_text
from .config import DATA_DIR
from .estudo import Estudo, Sala
from .pgn_do_livro import FluxoTolerante

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

PASTA_PADRAO = DATA_DIR / "estudos"
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
    """A sala inteira como um PGN de muitas partidas, em ordem de página e diagrama.

    As partidas cruas vão depois dos estudos, iguais a como vieram (S-814)."""
    return "\n\n".join([*(estudo.para_pgn() for estudo in sala.estudos()), *sala.crus])


def gravar(lida: Lida[Sala]) -> Path | None:
    """Grava a sala onde ela foi lida. `None` quando não há livro a que atá-la.

    Sala sem documento não tem chave estável: gravá-la num nome inventado criaria um arquivo que
    ninguém acha de volta, que é lixo com aparência de proteção. É a mesma decisão de
    `text/rascunho.gravar`, que devolve `None` para documento sem folha de origem.

    **Sala que esvaziou apaga o arquivo.** Deixar um PGN de zero partidas no disco faria a próxima
    abertura carregar nada e o usuário concluir que a gravação não funciona. Só sobre uma leitura
    que leu (S-812): apagar ou regravar a sala que não abriu levaria as tardes que estão nela.
    """
    lida = gravavel(lida)
    sala = lida.valor
    if not sala.documento:
        return None
    destino = lida.caminho
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


def carregar(documento: str | Path, *, pasta: Path | None = None) -> Leitura[Sala]:
    """A sala daquele livro. Sala vazia quando não há arquivo -- ausência é o caso normal.

    Uma partida ilegível **não derruba as outras**, e **não some** (S-814): a que não lê, a que tem
    lance ilegal (o `read_game` a cortaria ali, em silêncio), a sem âncora e a de âncora repetida
    ficam em `Sala.crus`, como texto, e voltam iguais na gravação. Um PGN de 50 estudos em que o 12
    está corrompido ainda tem 49 tardes de trabalho dentro -- e o 12 continua no disco.

    **O arquivo que não abre é leitura travada (S-812)**: arquivo em uso, ou um byte que não é
    UTF-8. Antes o byte virava `\ufffd` em silêncio, e a gravação seguinte o regravava assim -- a
    análise com acento escrita por outro programa saía estragada para sempre. A sala que não pôde
    ser lida até o fim também: a parte lida vale em memória, e a gravação fica travada.
    """
    nome = str(documento or "")
    origem = caminho_de(documento, pasta=pasta)

    def interpretar(texto: str) -> Sala:
        sala = Sala(nome)
        try:
            for jogo, trecho in _partidas(texto, onde=origem.name):
                estudo = _estudo_inteiro(jogo, documento=nome)
                if estudo is not None and estudo.ancora not in sala and sala.guardar(estudo):
                    continue
                if trecho.strip():
                    logger.warning("Partida de %s guardada como veio, sem abrir como estudo.", origem.name)
                    sala.crus.append(trecho.strip())
        except _LeituraParada as parada:
            raise ConteudoIlegivel(str(parada), parcial=sala) from parada
        return sala

    return ler(origem, interpretar, lambda: Sala(nome))


def _estudo_inteiro(jogo: chess.pgn.Game | None, *, documento: str) -> Estudo | None:
    """O estudo da partida, se ela leu inteira e diz alguma coisa. Lance ilegal não é inteira."""
    if jogo is None or jogo.errors or not _tem_conteudo(jogo):
        return None
    return Estudo.de_jogo(jogo, documento=documento)


class _LeituraParada(Exception):
    """O `read_game` levantou sem consumir nada: o resto do PGN não tem como ser lido."""


def _partidas(texto: str | TextIO, *, onde: str) -> Iterator[tuple[chess.pgn.Game | None, str]]:
    """Cada partida do PGN, com o trecho do texto de onde ela saiu. `None` é a que não leu.

    **`continue`, e não `break`, quando o `read_game` levanta (S-814):** ele já consumiu a partida
    ruim, e a seguinte começa onde ela acabou. Se ele levanta sem consumir nada, seguir seria um
    laço sem fim, e é `_LeituraParada`. O trecho só existe quando `texto` é `str`: de um fluxo
    aberto -- a base de 10 GB da S-307 -- não se guarda nada.
    """
    original = texto if isinstance(texto, str) else None
    fluxo = FluxoTolerante(io.StringIO(texto) if isinstance(texto, str) else texto)
    while True:
        antes = fluxo.posicao
        jogo: chess.pgn.Game | None
        try:
            jogo = chess.pgn.read_game(fluxo.arquivo)
        except Exception as erro:  # noqa: BLE001 - PGN de fora pode falhar de muitas formas
            if fluxo.posicao == antes:
                raise _LeituraParada(f"a leitura parou numa partida ilegível ({erro})") from erro
            logger.warning("Partida ilegível em %s: %s", onde, erro)
            jogo = None
        else:
            if jogo is None:
                return
        yield jogo, (original[antes:fluxo.posicao] if original is not None else "")


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

    **O fluxo é o tolerante (S-585)**: o PGN que vem com livro digital pode trazer duas linhas em
    branco entre o cabeçalho e os lances, e o `read_game` partia a partida em duas -- a metade com
    «Chapter 3 / Game 2» era descartada aqui, por não ter lance. Ver `pgn_do_livro`.
    """
    achados: list[Estudo] = []
    if limite is not None and limite <= 0:
        return achados
    try:
        for jogo, _trecho in _partidas(texto or "", onde=onde):
            if jogo is None:
                continue
            if not _tem_conteudo(jogo):
                # **`read_game` devolve uma partida para qualquer texto**: sem lance, sem `[FEN]` e
                # com os headers de fábrica. É o que sai de um `.txt` qualquer, e abri-lo como
                # estudo daria um tabuleiro na posição inicial dizendo que veio de um arquivo de
                # xadrez.
                logger.debug("Bloco sem lance e sem posição descartado de %s", onde)
                continue
            achados.append(Estudo.de_jogo(jogo, documento=documento))
            if limite is not None and len(achados) >= limite:
                logger.info("%s: leitura parada em %d partidas pelo teto pedido.", onde, limite)
                break
    except _LeituraParada as parada:
        logger.warning("Partida ilegível em %s: %s", onde, parada)
    return achados


def _tem_conteudo(jogo: chess.pgn.Game) -> bool:
    """A partida diz alguma coisa: tem lance, tem posição declarada ou tem anotação na raiz."""
    if jogo.variations or jogo.nags or (jogo.comment or "").strip():
        return True
    return bool(jogo.headers.get("FEN"))
