"""A mesma imagem arquivada sob dois caracteres: achar, julgar, e mover o perdedor (S-202).

**Isto não é duplicata, é rótulo que se contradiz, e a diferença decide tudo.** Duas cópias do
mesmo `e` são redundância: não ensinam nada novo, mas nada de errado. O mesmo arquivo, byte a
byte, dentro de `digit_1` **e** dentro de `lower_l` é outra coisa — as duas não podem estar
certas, e nenhum modelo pode acertar as duas. Medido em `training_data/` em 2026-08-23: **83
grupos, 1.557 recortes**, e os pares são a lista de homóglifos que se espera de livro —
`digit_1`×`lower_l` (13 grupos), `lower_v`×`upper_V` (7), `digit_0`×`lower_o` (6),
`sym_39`×`sym_44` (5, a apóstrofe e a vírgula).

O precedente é do projeto de origem e está no cabeçalho de `classes.py`: `sym_f7` guardava 127
imagens da casa de xadrez `f7` colidindo com o `?` de `sym_63`, e **corrigir o rótulo fez o
modelo já treinado acertar 127 de 127, sem retreinar**. Rótulo é mais barato que arquitetura.

**Metade não tem conserto, e dizê-lo é parte do conserto.** Dos 83, **50 são indecidíveis a
partir do recorte**, e não por falta de esforço: `v` e `V` têm o *mesmo desenho*, e o que os
separa é a altura relativa à linha — que o recorte apagou. Pior: os recortes foram gravados em
32x32 já na origem, então nem o tamanho nativo do PNG sobrou para desempatar (conferido: `p10` e
`p90` da altura de `lower_v` e de `upper_V` são 32 e 32). A mesma imagem **é** as duas coisas, e
só o contexto da linha diria qual — contexto que a base não guardou.

Daí o desenho deste módulo: **ele não decide nada.** Quem decide é um humano olhando o glifo, e a
decisão mora num arquivo versionado (`data/texto_conflitos.json`) com o motivo escrito ao lado.
O módulo acha, confere, e move.

**Por que não vencer por maioria.** Era a regra óbvia, e a base a desmente: a ficha 15 tem 30
recortes em `lower_f` contra 2 em `ligature_ft`, e o desenho **é** um "ft" — a maioria é que está
errada. Aconteceu quatro vezes nos 83. Uma regra automática de maioria teria consagrado o erro em
cada uma delas, com a confiança de 15 contra 1.

**Nada é apagado.** É lei desta fase, e vem de um acidente: a primeira migração do projeto de
origem usou `cv2.imread` como teste de integridade, e no Windows ele falha em caminho não-ASCII —
PNGs válidos foram apagados como se estivessem corrompidos. Aqui o perdedor vai para
`data/quarentena_texto/<classe>/`, com um manifesto que `desfazer` lê de volta.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from ..config import caminho_para_relatorio
from .classes import NomeDePastaInvalido, char_to_folder, folder_to_char

logger = logging.getLogger(__name__)

DECISOES_PADRAO = Path("data") / "texto_conflitos.json"
QUARENTENA_PADRAO = Path("data") / "quarentena_texto"
TAREFAS_PADRAO = 16

INDECIDIVEL = "indecidivel"
"""`confianca` de um grupo que ninguém conseguiu ler. Ver o cabeçalho: metade dos 83 é assim."""


class DecisaoInvalida(RuntimeError):
    """O arquivo de decisões não descreve a base que está no disco."""


@dataclass(frozen=True)
class Conflito:
    """Um grupo de arquivos byte a byte iguais espalhados por duas ou mais classes."""

    sha256: str
    arquivos: dict[str, list[str]]

    @property
    def rotulos(self) -> dict[str, int]:
        return {pasta: len(nomes) for pasta, nomes in sorted(self.arquivos.items())}

    @property
    def total(self) -> int:
        return sum(len(n) for n in self.arquivos.values())


@dataclass(frozen=True)
class Achados:
    """O que uma passada de hash sobre a base viu, e não só os conflitos.

    A S-202 pede que o relatório diga **quantas cópias exatas** foram achadas, e essa contagem
    sai de graça da mesma passada que acha o conflito -- cobrá-la numa segunda varredura seria
    reler 0,6 GB para responder o que já estava na mão.
    """

    conflitos: list[Conflito]
    recortes: int
    imagens_distintas: int

    @property
    def copias_exatas(self) -> int:
        return self.recortes - self.imagens_distintas


@dataclass
class Plano:
    """O que `aplicar` faria, antes de fazer. `conferir` devolve isto e não mexe em nada."""

    mover: list[tuple[str, str]] = field(default_factory=list)
    """`(classe, nome do arquivo)` de cada recorte que sai da base."""

    por_motivo: dict[str, int] = field(default_factory=dict)
    sem_decisao: list[str] = field(default_factory=list)
    divergentes: list[str] = field(default_factory=list)
    """Grupos cujo estado no disco não é o que a decisão descreve. Ver `DecisaoInvalida`."""


def _hash_de(caminho: Path) -> str:
    digest = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for pedaco in iter(lambda: arquivo.read(1 << 16), b""):
            digest.update(pedaco)
    return digest.hexdigest()


def _hashes_da_pasta(pasta: Path, nomes: list[str], tarefas: int) -> list[str]:
    """Os hashes dos arquivos de uma classe, em paralelo.

    Função nomeada e não `lambda` dentro do laço: uma closure sobre a variável do laço lê o
    valor no momento em que a thread roda, não no momento em que foi criada. Aqui o `with` do
    executor fecha antes da iteração seguinte, então não haveria defeito -- mas é uma garantia
    que depende de quem editar depois não mover uma linha, e a função tira a dúvida.
    """
    with ThreadPoolExecutor(max(1, tarefas)) as executor:
        return list(executor.map(lambda nome: _hash_de(pasta / nome), nomes, chunksize=256))


def achar(
    base: Path,
    *,
    tarefas: int = TAREFAS_PADRAO,
    progresso: Callable[[str, int, int], None] | None = None,
) -> list[Conflito]:
    """Só os grupos em conflito. Ver `varrer_hashes` para a contagem que vem junto."""
    return varrer_hashes(base, tarefas=tarefas, progresso=progresso).conflitos


def varrer_hashes(
    base: Path,
    *,
    tarefas: int = TAREFAS_PADRAO,
    progresso: Callable[[str, int, int], None] | None = None,
) -> Achados:
    """Uma passada de SHA-256 sobre a base: conflitos, total, e imagens distintas.

    Não decodifica imagem: o conflito é sobre bytes idênticos, e `imdecode` custaria o triplo
    para responder a mesma pergunta. Pasta cujo nome não fecha a ida-e-volta de `classes.py` é
    ignorada, pelo mesmo motivo de `dataset.varrer` -- ela não é classe.
    """
    base = Path(base)
    pastas = sorted(p for p in base.iterdir() if p.is_dir())
    onde: dict[str, dict[str, list[str]]] = {}

    for posicao, pasta in enumerate(pastas):
        if progresso is not None:
            progresso(pasta.name, posicao + 1, len(pastas))
        try:
            if char_to_folder(folder_to_char(pasta.name, strict=True)) != pasta.name:
                continue
        except NomeDePastaInvalido:
            continue
        nomes = sorted(os.listdir(pasta))
        for nome, digest in zip(nomes, _hashes_da_pasta(pasta, nomes, tarefas), strict=True):
            onde.setdefault(digest, {}).setdefault(pasta.name, []).append(nome)

    conflitos = sorted(
        (Conflito(digest, classes) for digest, classes in onde.items() if len(classes) > 1),
        key=lambda c: (-c.total, c.sha256),
    )
    recortes = sum(len(nomes) for classes in onde.values() for nomes in classes.values())
    return Achados(conflitos=conflitos, recortes=recortes, imagens_distintas=len(onde))


def ler_decisoes(caminho: Path = DECISOES_PADRAO) -> dict[str, dict[str, Any]]:
    """`sha256 -> decisão`. Levanta `DecisaoInvalida` com o motivo em pt-BR."""
    caminho = Path(caminho)
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DecisaoInvalida(f"não foi possível ler as decisões em {caminho}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DecisaoInvalida(f"{caminho.name} não é um JSON válido: {exc}") from exc
    if not isinstance(bruto, list):
        raise DecisaoInvalida(f"{caminho.name} devia ser uma lista de decisões.")

    decisoes: dict[str, dict[str, Any]] = {}
    for linha in bruto:
        sha = str(linha.get("sha256", ""))
        if len(sha) != 64:
            raise DecisaoInvalida(f"{caminho.name} tem decisão sem `sha256` de 64 dígitos: {linha}")
        if not str(linha.get("motivo", "")).strip():
            # **O motivo é obrigatório, e não é burocracia.** Uma decisão sem motivo é
            # indistinguível de um chute, e daqui a seis meses ninguém saberá qual das duas foi.
            raise DecisaoInvalida(f"{caminho.name}: a decisão de {sha[:12]}… não diz por quê.")
        decisoes[sha] = linha
    return decisoes


def conferir(conflitos: list[Conflito], decisoes: dict[str, dict[str, Any]]) -> Plano:
    """O que sairia da base, sem mexer em nada.

    **Um grupo cujo estado no disco não bate com o que a decisão descreve não é aplicado.** Se a
    contagem por classe mudou desde o julgamento, a imagem passou a significar outra coisa e o
    julgamento tem de ser refeito -- aplicar assim mesmo moveria arquivo que ninguém olhou.
    """
    plano = Plano()
    for conflito in conflitos:
        decisao = decisoes.get(conflito.sha256)
        if decisao is None:
            plano.sem_decisao.append(conflito.sha256)
            continue
        if decisao.get("rotulos") != conflito.rotulos:
            plano.divergentes.append(conflito.sha256)
            continue

        vencedor = decisao.get("vencedor")
        if vencedor:
            perdedores = [p for p in conflito.arquivos if p != vencedor]
            motivo = "rotulo errado"
        else:
            # Indecidível: o grupo inteiro sai. Custa **uma** amostra ao treino, porque o treino
            # usa um recorte por grupo de cópia exata -- e deixar a contradição custa mais.
            perdedores = list(conflito.arquivos)
            motivo = "indecidivel"
        for pasta in perdedores:
            for nome in conflito.arquivos[pasta]:
                plano.mover.append((pasta, nome))
        plano.por_motivo[motivo] = plano.por_motivo.get(motivo, 0) + len(
            [n for p in perdedores for n in conflito.arquivos[p]]
        )
    return plano


def aplicar(
    plano: Plano,
    base: Path,
    quarentena: Path = QUARENTENA_PADRAO,
    *,
    manifesto: Path | None = None,
) -> Path:
    """Move os perdedores para a quarentena e grava o manifesto. Devolve o caminho dele.

    A ordem é: mover primeiro, gravar o manifesto depois, com o que **de fato** saiu. Gravar o
    manifesto antes deixaria, numa falha no meio, um mapa de volta que descreve arquivos que
    continuam na base.
    """
    base, quarentena = Path(base), Path(quarentena)
    movidos: list[dict[str, str]] = []
    for pasta, nome in plano.mover:
        origem = base / pasta / nome
        if not origem.exists():
            logger.warning("%s/%s já não está na base; nada a mover.", pasta, nome)
            continue
        destino = quarentena / pasta / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(origem), str(destino))
        movidos.append({"classe": pasta, "arquivo": nome})

    manifesto = Path(manifesto) if manifesto else quarentena / f"manifesto_{datetime.now():%Y%m%d_%H%M%S}.json"
    manifesto.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        manifesto,
        json.dumps(
            {
                "quando": datetime.now().replace(microsecond=0).isoformat(),
                "base": caminho_para_relatorio(base),
                "quarentena": caminho_para_relatorio(quarentena),
                "por_motivo": plano.por_motivo,
                "movidos": movidos,
            },
            ensure_ascii=False,
            indent=1,
        ),
    )
    return manifesto


def desfazer(manifesto: Path) -> int:
    """Devolve à base tudo o que um manifesto diz ter movido. Quantos voltaram."""
    dados = json.loads(Path(manifesto).read_text(encoding="utf-8"))
    base, quarentena = Path(dados["base"]), Path(dados["quarentena"])
    voltaram = 0
    for item in dados["movidos"]:
        origem = quarentena / item["classe"] / item["arquivo"]
        if not origem.exists():
            continue
        destino = base / item["classe"] / item["arquivo"]
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(origem), str(destino))
        voltaram += 1
    return voltaram


__all__ = [
    "DECISOES_PADRAO",
    "INDECIDIVEL",
    "QUARENTENA_PADRAO",
    "TAREFAS_PADRAO",
    "Achados",
    "Conflito",
    "DecisaoInvalida",
    "Plano",
    "achar",
    "aplicar",
    "conferir",
    "desfazer",
    "ler_decisoes",
    "varrer_hashes",
]
