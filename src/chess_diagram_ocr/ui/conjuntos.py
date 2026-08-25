"""O conjunto de peças do tabuleiro, declarado como dado e escolhível (S-230).

**O que havia.** `PieceImages` recebe um diretório e o chamador passa sempre o mesmo:
`assets/piece_images/`. Doze PNGs, um conjunto, sem alternativa -- e trocá-lo era sobrescrever os
arquivos, o que muda o conjunto de todo mundo e não tem volta.

**O que a Imagem 2 propõe, e o que dela entra.** Ela mostra peças fotográficas de um tabuleiro de
madeira real. **Isso não entra**, e a razão é de produto: o tabuleiro da janela é onde se *corrige*
a leitura, casa a casa, contra um diagrama impresso -- sombra, perspectiva e madeira atrapalham
exatamente essa comparação. O que entra da imagem é a ideia de que o conjunto é uma escolha.

**Três conjuntos, e a mesma forma do registro de peles (S-221).** Uma declaração, e não uma classe
por conjunto: o `padrao` é o de hoje e continua sendo o padrão; o `traco` é o mesmo desenho com o
traço engrossado, para quem trabalha com o tabuleiro pequeno; e a `pasta` é um caminho do usuário,
validado por `ui/campos.py`.

**O conjunto é eixo próprio.** Pele decide arranjo e densidade; tema decide cor; conjunto decide o
desenho das peças. Qualquer conjunto vale com qualquer pele, e amarrá-los faria "a fita clara com
as peças de traço grosso" ser impossível sem que ninguém tivesse decidido isso -- é a mesma
separação que `ui/pele.py` já defende entre pele e tema.

Sem `tkinter` e sem `PIL` aqui, como em `ui/pele.py` e `ui/tokens.py`: quem desenha é
`ui/board_render.py`, e o registro é afirmável sem abrir janela e sem carregar imagem.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "CONJUNTOS",
    "CONJUNTO_ENV",
    "PADRAO",
    "PASTA",
    "PECAS",
    "TRACO",
    "Conjunto",
    "ausentes",
    "escolhido",
    "por_nome",
    "registrado",
    "valida",
]

PADRAO = "padrao"
"""Os 12 PNGs de `assets/piece_images/`. Quem nunca escolher nada tem exatamente eles."""

TRACO = "traco"
"""Os mesmos desenhos com o traço engrossado, para o tabuleiro pequeno.

**Derivado, e não uma segunda arte.** A paleta de edição e a Galeria desenham as peças a 20-24 px,
e a redução apaga a linha fina: as peças brancas -- que são contorno preto com miolo claro -- viram
manchas iguais entre si. Engrossar depois de reduzir devolve a linha no tamanho em que ela é
mostrada, que é onde o problema está.

Doze arquivos novos resolveriam o mesmo e teriam de ser desenhados, versionados e mantidos em par
com os primeiros; é o argumento do achado 6 do ROADMAP_APARENCIA sobre ícone em PNG, aplicado a
peça: arte de arquivo não sobrevive a uma segunda condição de exibição."""

PASTA = "pasta"
"""Os 12 arquivos de uma pasta do usuário, por nome (`wk.png`, `bq.png`, ...).

Pasta incompleta **avisa e usa o que houver**, e não recusa: `PieceImages` já degrada para símbolo
Unicode quando o arquivo falta, peça a peça. Recusar o conjunto inteiro por causa de um arquivo
seria trocar um comportamento que existe por um erro que não precisa existir."""

CONJUNTO_ENV = "CVOFF_PIECES"
"""Acompanha `CVOFF_SKIN` e `CVOFF_TTK_THEME`, para quem dirige o programa por script."""

PECAS: tuple[str, ...] = (
    "wp", "wn", "wb", "wr", "wq", "wk",
    "bp", "bn", "bb", "br", "bq", "bk",
)
"""Os 12 nomes de arquivo, sem extensão, na ordem em que a paleta os desenha.

Declarados aqui e não em `board_render.py` porque quem precisa deles **antes** de abrir imagem é
quem valida a pasta do usuário: dizer "faltam wq e bk" exige a lista, e a lista não pode morar
dentro do laço que tenta abri-los."""


@dataclass(frozen=True)
class Conjunto:
    """Um conjunto de peças: de onde vêm os desenhos e o que se faz com eles."""

    nome: str
    """A chave, e o que vai para o disco: `"padrao"`. Minúscula e sem acento, como a pele."""

    rotulo: str
    """Como a pessoa lê na Configuração: `"Padrão"`."""

    engrossa: bool = False
    """Se o traço é engrossado depois de reduzir ao tamanho de exibição."""

    do_usuario: bool = False
    """Se os arquivos vêm da pasta escolhida em vez de `assets/piece_images/`."""


CONJUNTOS: tuple[Conjunto, ...] = (
    Conjunto(PADRAO, "Padrão"),
    Conjunto(TRACO, "Traço grosso", engrossa=True),
    Conjunto(PASTA, "Pasta do usuário", do_usuario=True),
)
"""Os conjuntos registrados, na ordem em que a Configuração os lista.

O padrão é o primeiro porque é o padrão -- quem nunca abrir a Configuração tem o tabuleiro de
sempre, pixel a pixel, e é isso que este item promete não mudar."""


por_nome: dict[str, Conjunto] = {registro.nome: registro for registro in CONJUNTOS}


def registrado(nome: str) -> Conjunto:
    """O conjunto daquele nome. Levanta `KeyError` -- use `valida` quando o nome vem de fora."""
    if nome not in por_nome:
        raise KeyError(f"conjunto de peças desconhecido: {nome!r}. Os registrados estão em CONJUNTOS.")
    return por_nome[nome]


def valida(nome: str) -> str:
    """O nome, se ele existe; `PADRAO` com um `warning` que **nomeia** o inválido, se não.

    Não levanta, ao contrário de `registrado`: este é o caminho por onde entra o que veio do disco
    ou do ambiente, e nem estado antigo nem variável escrita errada podem impedir a janela de
    abrir. É o contrato de degradação de `ui/theme.py`, e o mesmo de `pele.valida`.
    """
    if nome in por_nome:
        return nome
    if nome:
        logger.warning("Conjunto de peças desconhecido: %r. Usando o %s.", nome, PADRAO)
    return PADRAO


def escolhido(guardado: str = "", *, ambiente: Mapping[str, str] | None = None) -> str:
    """O conjunto que vale ao abrir: `CVOFF_PIECES`, senão o guardado no estado, senão o padrão.

    O ambiente ganha do guardado, pela mesma razão de `pele.escolhida`: uma variável que o disco
    vencesse não serviria para o que ela existe -- abrir o programa num conjunto a partir de um
    roteiro, para fotografar os dois lado a lado.
    """
    fonte = ambiente if ambiente is not None else os.environ
    return valida(fonte.get(CONJUNTO_ENV, "") or guardado)


def ausentes(
    diretorio: Path | str,
    *,
    pecas: Iterable[str] = PECAS,
    existe: Callable[[Path], bool] | None = None,
) -> list[str]:
    """As peças que aquela pasta **não** tem, na ordem de `PECAS`. Vazio é o estado completo.

    Pura, com `existe` injetável -- a mesma disciplina de `campos.diagnosticar_caminho` e de
    `AppState.recentes`, e é o que permite afirmar o aviso sem criar doze arquivos no disco.

    Devolve a lista em vez de um booleano porque o valor do aviso está nos **nomes**: "faltam wq e
    bk" diz o que copiar para lá; "a pasta está incompleta" manda a pessoa conferir doze arquivos.
    """
    confere = existe if existe is not None else Path.exists
    base = Path(diretorio)
    return [peca for peca in pecas if not confere(base / f"{peca}.png")]
