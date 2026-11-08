"""A leitura travada: arquivo do dono que não lê não é arquivo vazio (S-812).

**A premissa que este módulo remove.** Seis leitores de arquivo do dono -- `settings.json`,
`revisao.json`, `placar.json`, a sala de estudo, a fila de revisão e o lote de importação --
tratavam o arquivo que não liam como vazio, e o gravador seguinte escrevia o vazio por cima. Uma
vírgula sobrando no `settings.json` virava os padrões, e o próximo *Salvar* gravava `endpoint: ''`
sobre o que a pessoa tinha escrito; um `revisao.json` de esquema 2 com 600 itens carregava com 0, e
a próxima sessão o regravava com 0. "Arquivo do dono" é o dado que o programa não sabe refazer.

**Três estados, e o tipo diz qual.** `ler` devolve uma `Leitura`:

- `Lida` -- o arquivo leu, ou não existe (ausência é o primeiro dia, e o padrão é o certo);
- `Ilegivel` -- existe e não leu: JSON quebrado, byte que não é UTF-8, pasta sem permissão;
- `EsquemaFuturo` -- leu, mas foi gravado por uma versão mais nova do programa.

Os três carregam um `valor` em memória, e o programa segue com ele: a janela abre com os padrões, a
sala abre vazia. O que muda é a gravação. **Os gravadores aceitam só `Lida`**: o mypy acusa quem
passa outra coisa, e `gravavel` é a porta que a transforma, levantando `GravacaoRecusada` com a frase
para a pessoa. É a decisão D1(a) da solidez: o arquivo ilegível é copiado ao lado, como
`<nome>.ilegivel-<data><extensão>`, e nada é gravado por cima dele até o dono decidir.

**Por que copiar, se nada vai ser gravado por cima.** Porque a trava dura a sessão, e a pessoa pode
apagar o arquivo para destravar -- que é a saída que a frase oferece. A cópia é o que sobra dela.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Generic, TypeAlias, TypeVar, cast

from .atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

__all__ = [
    "MARCA_DA_COPIA",
    "ConteudoIlegivel",
    "EsquemaFuturo",
    "GravacaoRecusada",
    "Ilegivel",
    "Leitura",
    "Lida",
    "VersaoFutura",
    "com_valor",
    "conferir_esquema",
    "gravar_lista",
    "gravavel",
    "ler",
    "ler_lista",
]

T = TypeVar("T")
U = TypeVar("U")

MARCA_DA_COPIA = ".ilegivel-"
"""O que está no nome de toda cópia. Quem varre uma pasta de arquivos do dono pula esses nomes."""


class GravacaoRecusada(Exception):
    """A gravação foi pedida sobre uma leitura travada. `str(erro)` é a frase para a pessoa."""


class VersaoFutura(Exception):
    """Levantada por quem interpreta: o arquivo declara um esquema mais novo que o deste programa."""

    def __init__(self, versao: object) -> None:
        super().__init__(f"esquema {versao!r}")
        self.versao = versao


class ConteudoIlegivel(ValueError):
    """Levantada por quem interpreta quando o arquivo leu só em parte.

    `parcial` é o que deu para ler. Ele vira o `valor` da `Ilegivel`, para o programa seguir com o
    que há -- e a trava continua, porque gravar o parcial apagaria o resto.
    """

    def __init__(self, motivo: str, *, parcial: object = None) -> None:
        super().__init__(motivo)
        self.parcial = parcial


@dataclass(frozen=True)
class Lida(Generic[T]):
    """O arquivo leu (ou não existia). É a única leitura que um gravador aceita."""

    valor: T
    caminho: Path

    def com(self, valor: T) -> Lida[T]:
        """A mesma licença de gravar, com outro valor: é como se grava o que se mudou."""
        return Lida(valor, self.caminho)


@dataclass(frozen=True)
class Ilegivel(Generic[T]):
    """O arquivo existe e não leu. `valor` é o que o programa usa em memória."""

    valor: T
    caminho: Path
    copia: Path | None
    motivo: str

    @property
    def mensagem(self) -> str:
        return (
            f"{self.caminho.name} não pôde ser lido ({self.motivo}). {_onde_esta(self.copia)}"
            f"Nada será gravado por cima dele nesta sessão: conserte-o ou apague-o e abra de novo."
        )


@dataclass(frozen=True)
class EsquemaFuturo(Generic[T]):
    """O arquivo foi gravado por uma versão mais nova. `valor` é o que o programa usa em memória."""

    valor: T
    caminho: Path
    copia: Path | None
    versao: object

    @property
    def mensagem(self) -> str:
        return (
            f"{self.caminho.name} foi gravado por uma versão mais nova deste programa "
            f"(esquema {self.versao}). {_onde_esta(self.copia)}"
            "Nada será gravado por cima dele: abra-o com a versão que o gravou."
        )


Leitura: TypeAlias = Lida[T] | Ilegivel[T] | EsquemaFuturo[T]


def conferir_esquema(declarado: object, atual: int) -> None:
    """O esquema que o arquivo declara, conferido contra o `atual` deste programa (S-813).

    Levanta `VersaoFutura` se ele é mais novo, e `ValueError` (ilegível) se não é número. Ausente
    (`None`) é o esquema atual. **É número, e não `int`**: `"1.0"`, escrito à mão, é o esquema 1 --
    `int("1.0")` levantava, e o arquivo inteiro travava como ilegível --, e `"2.0"` ou `1.5` são
    futuros, e não ilegíveis nem o 1. Booleano não é número aqui, por mais que o Python o some.
    """
    if declarado is None:
        return
    if isinstance(declarado, bool):
        raise ValueError(f"esquema {declarado!r} não é número")
    try:
        numero = float(str(declarado))
    except ValueError:
        raise ValueError(f"esquema {declarado!r} não é número") from None
    if not math.isfinite(numero):
        raise ValueError(f"esquema {declarado!r} não é número")
    if numero > atual:
        raise VersaoFutura(declarado)


def ler_lista(
    texto: str, *, esquema: int, lista: str, ler_item: Callable[[object], T], chave: Callable[[T], str]
) -> tuple[dict[str, T], tuple[object, ...]]:
    """Um arquivo `{"esquema": N, "<lista>": [...]}`: os itens que leram, pela chave, e os crus (S-813).

    É o formato do baralho de revisão e do placar. Cada item no seu `try`, e um ruim entre
    seiscentos não trava os outros. O que não lê -- campo que não converte, chave vazia ou
    repetida -- é guardado como veio, para `gravar_lista` devolvê-lo igual: descartá-lo apagaria
    do disco, na primeira gravação, o que ninguém refaz. O topo que não é objeto e a lista que não
    é lista são o arquivo que não lê (`ValueError`); o esquema é o de `conferir_esquema`.
    """
    dados = json.loads(texto)
    if not isinstance(dados, dict):
        raise ValueError("o topo não é um objeto")
    conferir_esquema(dados.get("esquema"), esquema)
    itens = dados.get(lista, [])
    if not isinstance(itens, list):
        raise ValueError(f"{lista} não é uma lista")
    lidos: dict[str, T] = {}
    crus: list[object] = []
    for bruto in itens:
        try:
            item = ler_item(bruto)
        except (TypeError, ValueError) as erro:
            logger.warning("Item ilegível, guardado como veio: %s", erro)
            crus.append(bruto)
            continue
        nome = chave(item)
        if not nome or nome in lidos:
            crus.append(bruto)
            continue
        lidos[nome] = item
    return lidos, tuple(crus)


def gravar_lista(
    leitura: Leitura[T], *, esquema: int, lista: str, itens: Iterable[object], crus: Iterable[object]
) -> Path:
    """Grava o que `ler_lista` lê, onde foi lido, e só se a leitura deixa (`gravavel`).

    Os itens que leram vão primeiro, e os crus depois deles, iguais a como vieram (S-813).
    """
    lida = gravavel(leitura)
    atomic_write_json(lida.caminho, {"esquema": esquema, lista: [*itens, *crus]})
    return lida.caminho


def _onde_esta(copia: Path | None) -> str:
    if copia is None:
        return "Não foi possível guardar uma cópia. "
    return f"Uma cópia está em {copia.name}. "


def ler(caminho: Path, interpretar: Callable[[str], T], padrao: Callable[[], T]) -> Leitura[T]:
    """Lê um arquivo do dono. Único lugar em que "não leu" vira um dos três estados.

    `interpretar` recebe o texto e devolve o valor; levanta `VersaoFutura` para esquema mais novo,
    `ConteudoIlegivel` para leitura parcial, e qualquer outra exceção quer dizer ilegível. `padrao`
    dá o valor do primeiro dia e o da memória quando não leu.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return Lida(padrao(), caminho)
    try:
        texto = caminho.read_bytes().decode("utf-8")
        return Lida(interpretar(texto), caminho)
    except VersaoFutura as futura:
        logger.warning("%s é de um esquema mais novo (%r); a gravação fica travada.", caminho, futura.versao)
        return EsquemaFuturo(padrao(), caminho, copiar_ao_lado(caminho), futura.versao)
    except Exception as erro:  # noqa: BLE001 - arquivo do usuário pode falhar de qualquer forma
        # **Largo de propósito.** O que se protege é o arquivo, e uma forma que ninguém previu --
        # seção que é lista, número que é dicionário -- tem de travar como o JSON quebrado trava.
        # Deixar escapar seria pior duas vezes: a janela não abre (S-124), ou abre com o padrão e
        # grava por cima, que é o defeito.
        parcial = erro.parcial if isinstance(erro, ConteudoIlegivel) else None
        valor = padrao() if parcial is None else cast(T, parcial)
        logger.warning("%s não pôde ser lido (%s); a gravação fica travada.", caminho, erro)
        return Ilegivel(valor, caminho, copiar_ao_lado(caminho), _motivo(erro))


def _motivo(erro: BaseException) -> str:
    if isinstance(erro, UnicodeDecodeError):
        return f"o byte {erro.object[erro.start:erro.start + 1]!r} na posição {erro.start} não é UTF-8"
    if isinstance(erro, OSError):
        return erro.strerror or erro.__class__.__name__
    return str(erro) or erro.__class__.__name__


def com_valor(leitura: Leitura[T], valor: U) -> Leitura[U]:
    """A mesma leitura -- mesmo estado, caminho e cópia -- com outro valor em memória.

    É como quem monta o valor a partir do lido (o lote junta a pasta com o andamento) devolve o que
    montou sem perder a trava.
    """
    if isinstance(leitura, Lida):
        return Lida(valor, leitura.caminho)
    if isinstance(leitura, Ilegivel):
        return Ilegivel(valor, leitura.caminho, leitura.copia, leitura.motivo)
    return EsquemaFuturo(valor, leitura.caminho, leitura.copia, leitura.versao)


def gravavel(leitura: Leitura[T]) -> Lida[T]:
    """A leitura, se ela deixa gravar. Levanta `GravacaoRecusada` com a frase, se não deixa."""
    if isinstance(leitura, Lida):
        return leitura
    raise GravacaoRecusada(leitura.mensagem)


def conferir_versao_exata(dados: object, chave: str, atual: int) -> None:
    """O topo do JSON é um objeto, e a versão em `chave` é exatamente a `atual` (S-812).

    Para o arquivo sem migração (a fila de revisão, o lote de importação): a versão mais nova
    levanta `VersaoFutura` (a leitura trava como `EsquemaFuturo`), e qualquer outra levanta
    `ValueError` (ilegível) -- ler uma mais velha e regravar seria apagar o que ela tinha. O
    arquivo que lê esquema antigo usa `ler_lista`, com `conferir_esquema` (S-813).
    """
    if not isinstance(dados, dict):
        raise ValueError("o topo não é um objeto")
    versao = dados.get(chave)
    if isinstance(versao, int) and versao > atual:
        raise VersaoFutura(versao)
    if versao != atual:
        raise ValueError(f"versão {versao!r} desconhecida")


def gravar_json(leitura: Leitura[T], conteudo: object, *, indent: int = 2) -> Path:
    """Grava `conteudo` onde `leitura` leu. Só sobre uma leitura que leu (S-812)."""
    lida = gravavel(leitura)
    atomic_write_json(lida.caminho, conteudo, indent=indent)
    return lida.caminho


def copiar_ao_lado(caminho: Path, *, hoje: date | None = None) -> Path | None:
    """Copia o arquivo para `<nome>.ilegivel-<data><extensão>`, ao lado dele. `None` se não deu.

    A extensão fica no fim para a cópia abrir no mesmo programa que abre o original. Reabrir o
    mesmo arquivo ilegível no mesmo dia não multiplica cópias: a que já tem os mesmos bytes serve.
    """
    dia = (hoje or date.today()).isoformat()
    try:
        conteudo = caminho.read_bytes()
    except OSError as erro:
        logger.warning("A cópia de %s não pôde ser feita: %s", caminho, erro)
        return None
    for numero in range(1, 100):
        sufixo = "" if numero == 1 else f"-{numero}"
        destino = caminho.with_name(f"{caminho.stem}{MARCA_DA_COPIA}{dia}{sufixo}{caminho.suffix}")
        try:
            if destino.exists():
                if destino.read_bytes() == conteudo:
                    return destino
                continue
            shutil.copy2(caminho, destino)
            return destino
        except OSError as erro:
            logger.warning("A cópia de %s não pôde ser feita: %s", caminho, erro)
            return None
    return None
