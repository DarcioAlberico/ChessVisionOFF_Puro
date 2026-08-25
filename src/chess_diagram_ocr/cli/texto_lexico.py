"""`cvoff-texto-lexico` — empacota as listas de palavras em `assets/lexico/`.

    cvoff-texto-lexico "Lista de Palavras"
    cvoff-texto-lexico "Lista de Palavras" --dry-run

**Existe para que trocar a lista não seja mexer em código.** O dicionário de `text/dicionario.py`
lê arquivos de dados, e este comando é o que os produz: de um lado uma pasta de listas de texto,
do outro dois `.txt.gz` versionados. Rodar de novo sobre a mesma pasta dá **byte a byte** o mesmo
arquivo -- o gzip é gravado com `mtime=0` de propósito, senão cada reconstrução sujaria a árvore.

## Duas listas, e a separação é a da S-209

`idioma.txt.gz` são as palavras que começam em minúscula -- prosa de xadrez em oito idiomas.
`nomes.txt.gz` são as que começam em maiúscula -- sobrenome de jogador, cidade, torneio.

A S-209 mediu por que elas não podem ser um arquivo só: só o idioma dá 58,5% de recall com 12,1%
de alarme falso; com os nomes, 53,8% e 5,8%. **Nome próprio baixa o alarme e esconde erro**, e
quem escolhe é quem carrega. Aqui elas saem separadas para que a escolha exista.

## O que é recusado, e por quê

As mesmas quatro réguas de `text/dicionario.py`, aplicadas na entrada em vez de na leitura:
menos de `MIN_TAMANHO` letras é notação (`Kf`, `Nc`), dígito não é palavra, e o que casa com
`notacao.LANCE` sai fora. Um token com pontuação no meio (`A.Koros`) também sai: `PALAVRA` só
aceita letra, apóstrofo e hífen.

**Um arquivo é ignorado por nome, e a razão é medida.** `MegaDatabase(Jogadores with dot).txt`
está corrompido -- as linhas são concatenações de dois nomes partidos ao meio (`A.Koros` +
`partindras` -> `A.Korospartindras`), e depois das réguas acima ainda sobrariam **39.409**
palavras falsas como `Cortesulio`, `Linaresariano` e `Frauosep`. Palavra falsa no léxico é pior
que palavra faltando: a que falta só deixa de corrigir, a falsa vira **alvo** de correção.
"""

from __future__ import annotations

import argparse
import gzip
import io
import logging
import re
from collections import Counter
from pathlib import Path

from ..atomic_io import atomic_write_bytes
from ..config import PROJECT_ROOT
from ..logging_setup import configure_logging
from ..text.dicionario import CAMINHO_IDIOMA, CAMINHO_NOMES, MIN_TAMANHO, PALAVRA
from ..text.notacao import LANCE
from . import EXIT_BAD_INPUT, cli_errors

logger = logging.getLogger(__name__)

PASTA_PADRAO = PROJECT_ROOT / "Lista de Palavras"

IGNORADOS = ("MegaDatabase(Jogadores with dot).txt",)
"""Arquivos que não entram, por nome. Ver "O que é recusado" no cabeçalho."""

SEPARADOR = re.compile(r"[,\s/]+")
"""Onde a linha se parte em tokens.

`Aab, Manfred` são duas palavras, e a lista de jogadores traz o nome inteiro por linha. A vírgula
entra aqui porque é ela que separa sobrenome de nome nessa lista."""

ENVOLVE = ".,;:!?()[]'\""


def tokens(linha: str) -> list[str]:
    """Os tokens de uma linha, sem BOM e sem a pontuação que os envolve."""
    saida = []
    for pedaco in SEPARADOR.split(linha.replace("﻿", "")):
        limpo = pedaco.strip().strip(ENVOLVE)
        if limpo:
            saida.append(limpo)
    return saida


def aceita(token: str) -> bool:
    """Este token pode virar palavra do léxico? Ver "O que é recusado" no cabeçalho."""
    if len(token) < MIN_TAMANHO or any(c.isdigit() for c in token):
        return False
    return bool(PALAVRA.match(token)) and not LANCE.match(token)


def e_nome(token: str) -> bool:
    """Nome próprio, pela única marca que a lista dá: a primeira letra é maiúscula."""
    return token[:1].isupper()


def ler_lista(caminho: Path) -> tuple[list[str], int]:
    """As palavras aceitas de um arquivo, e quantos tokens foram recusados.

    **`errors="replace"` em vez de estourar**: as listas vêm de fora, e um byte inválido no meio
    de 259 mil linhas não pode derrubar a construção. O caractere de substituição não casa com
    `PALAVRA`, então o token que o contém morre na régua seguinte -- que é o que se quer.
    """
    aceitos: list[str] = []
    recusados = 0
    with caminho.open("r", encoding="utf-8-sig", errors="replace") as fh:
        for linha in fh:
            for token in tokens(linha):
                if aceita(token):
                    aceitos.append(token)
                else:
                    recusados += 1
    return aceitos, recusados


def construir(pasta: Path) -> tuple[dict[str, set[str]], list[dict[str, object]]]:
    """As duas listas e o relatório por arquivo. Não escreve nada."""
    idioma: set[str] = set()
    nomes: set[str] = set()
    relatorio: list[dict[str, object]] = []

    for caminho in sorted(pasta.glob("*.txt")):
        if caminho.name in IGNORADOS:
            relatorio.append({"arquivo": caminho.name, "ignorado": True})
            logger.info("%s: ignorado (ver IGNORADOS).", caminho.name)
            continue
        aceitos, recusados = ler_lista(caminho)
        deste_idioma = {t.casefold() for t in aceitos if not e_nome(t)}
        deste_nomes = {t.casefold() for t in aceitos if e_nome(t)}
        idioma |= deste_idioma
        nomes |= deste_nomes
        relatorio.append(
            {
                "arquivo": caminho.name,
                "aceitos": len(aceitos),
                "recusados": recusados,
                "idioma": len(deste_idioma),
                "nomes": len(deste_nomes),
            }
        )

    # **A mesma palavra não vai nos dois arquivos.** `bishop` e `Bishop` são a mesma entrada
    # depois do `casefold`, e quem tem palavra em minúscula na lista é o idioma.
    nomes -= idioma
    return {"idioma": idioma, "nomes": nomes}, relatorio


def escrever(caminho: Path, palavras: set[str]) -> int:
    """Grava o `.txt.gz` ordenado, com `\\n` e `mtime=0`. Devolve o tamanho em bytes.

    **`mtime=0` não é detalhe**: o cabeçalho do gzip carrega a hora da compressão, e sem fixá-la
    dois arquivos com o mesmo conteúdo têm bytes diferentes. Reconstruir a lista sujaria a árvore
    de trabalho sem ninguém ter mudado uma palavra.
    """
    bruto = ("\n".join(sorted(palavras)) + "\n").encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as fh:
        fh.write(bruto)
    dados = buffer.getvalue()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(caminho, dados)
    return len(dados)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cvoff-texto-lexico",
        description="Empacota as listas de palavras em assets/lexico/{idioma,nomes}.txt.gz.",
    )
    parser.add_argument(
        "pasta",
        nargs="?",
        type=Path,
        default=PASTA_PADRAO,
        help=f"Pasta com as listas .txt. Padrão: {PASTA_PADRAO.name}/",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=CAMINHO_IDIOMA.parent,
        help="Pasta de saída. Padrão: assets/lexico/",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Conta e imprime, sem escrever arquivo nenhum."
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose)

    pasta = Path(args.pasta)
    if not pasta.is_dir():
        print(f"pasta de listas nao encontrada: {pasta}")
        return EXIT_BAD_INPUT

    listas, relatorio = construir(pasta)
    if not listas["idioma"] and not listas["nomes"]:
        print(f"nenhuma palavra aceita em {pasta}: os arquivos sao .txt com uma palavra por linha?")
        return EXIT_BAD_INPUT

    print(f"\n{pasta}")
    print(f"  {'arquivo':52s} {'aceitos':>9s} {'recusados':>10s} {'idioma':>8s} {'nomes':>8s}")
    for linha in relatorio:
        nome = str(linha["arquivo"])[:52]
        if linha.get("ignorado"):
            print(f"  {nome:52s} {'-- ignorado (lista corrompida) --':>39s}")
            continue
        print(
            f"  {nome:52s} {linha['aceitos']:>9d} {linha['recusados']:>10d} "
            f"{linha['idioma']:>8d} {linha['nomes']:>8d}"
        )

    destino = Path(args.saida)
    print()
    for nome, caminho in (("idioma", destino / CAMINHO_IDIOMA.name), ("nomes", destino / CAMINHO_NOMES.name)):
        palavras = listas[nome]
        if args.dry_run:
            print(f"  {caminho.name:16s} {len(palavras):>7d} palavras (dry-run: nao escrito)")
            continue
        tamanho = escrever(caminho, palavras)
        print(f"  {caminho.name:16s} {len(palavras):>7d} palavras   {tamanho / 1024:>6.0f} KiB -> {caminho}")

    inicial = Counter(p[:1] for p in listas["idioma"])
    logger.debug("Iniciais mais comuns no idioma: %s", inicial.most_common(5))
    return 0


if __name__ == "__main__":  # pragma: no cover - execução direta
    raise SystemExit(main())
