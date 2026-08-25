"""A pele da janela: qual aparência, declarada como dado e guardada no estado (S-221).

**Não havia onde guardar "qual aparência".** `AppState` lembra PDF, página, zoom, geometria, aba
aberta e dois interruptores de visualização -- e nada sobre cromo. O único eixo de aparência que
existia é o tema, e ele é **variável de ambiente** (`CVOFF_TTK_THEME`): escolhido antes de o
programa abrir e invisível de dentro dele. Quem quisesse comparar duas aparências fecharia o
programa duas vezes.

**Uma declaração, e não uma classe por pele.** O mesmo formato de `menu.MENUS` e de
`comandos.CATALOGO`, pela mesma razão: três montagens de widget são três lugares onde um comando
novo precisa ser lembrado, e o primeiro que alguém esquecer produz um programa em que a mesma
versão faz coisas diferentes conforme a aparência escolhida.

**Hoje há uma pele registrada, e isso é o item.** A fundação se prova quando ela não muda nada:
`Ver ▸ Aparência` lista a clássica, marcada, e a janela é a de hoje pixel a pixel. Quem
acrescenta linha aqui é a S-223 ("Foco") e a S-227 ("Fita") -- e registrar as duas antes de
existirem seria oferecer no menu uma escolha que não faz nada, que é o defeito que
`menu.montar` recusa desde a S-161.

**O eixo pele e o eixo tema ficam separados de propósito.** Pele decide arranjo e densidade; tema
decide cor. Amarrá-los faria "a fita clara com o tabuleiro escuro" ser impossível sem que ninguém
tivesse decidido isso.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = [
    "CLASSICA",
    "COMPACTA",
    "CONFORTAVEL",
    "CROMO_CLASSICO",
    "CROMO_FITA",
    "CROMO_FOCO",
    "DENSIDADES",
    "FITA",
    "FOCO",
    "PELES",
    "PELE_ENV",
    "Pele",
    "escolhida",
    "por_nome",
    "registrada",
    "valida",
]

CLASSICA = "classica"
"""A janela de hoje, e o padrão. Quem nunca abrir `Ver ▸ Aparência` tem exatamente ela."""

COMPACTA = "compacta"
CONFORTAVEL = "confortavel"
DENSIDADES: tuple[str, ...] = (COMPACTA, CONFORTAVEL)
"""O eixo que a S-232 vai consumir. Declarado aqui porque é propriedade **da pele**, e não do
widget: uma pele compacta que dependesse de cada painel lembrar de encolher seria a mesma
divergência que o catálogo de comandos veio fechar."""

FOCO = "foco"
"""A proposta da Imagem 1: uma fila só de ações e o documento ocupando todo o resto (S-223)."""

FITA = "fita"
"""A proposta da Imagem 2: grupos nomeados, ícone grande com rótulo (S-227)."""

PELE_ENV = "CVOFF_SKIN"
"""Acompanha `CVOFF_TTK_THEME`, para quem dirige o programa por script."""

CROMO_CLASSICO = "classico"
CROMO_FOCO = "foco"
CROMO_FITA = "fita"
"""Os nomes de montagem. São o valor de `Pele.montar_cromo`, e quem os executa é o painel."""


@dataclass(frozen=True)
class Pele:
    """Uma aparência: como o cromo se arruma, quão apertado, e se ele é escuro."""

    nome: str
    """A chave, e o que vai para o disco: `"classica"`. Minúscula e sem acento de propósito."""

    rotulo: str
    """Como a pessoa lê no menu: `"Clássica"`."""

    montar_cromo: str
    """O **nome** da montagem, e não a função. Quem a executa é o painel, e é isso que permite a
    este módulo não importar `tkinter` -- a mesma fronteira de `atalhos.Atalho.acao`."""

    densidade: str = CONFORTAVEL
    """Um de `DENSIDADES`. A janela de hoje é a confortável, por medição e não por escolha:
    é a que existe."""

    cromo_escuro: bool = False
    """O cromo escurece; a superfície de documento não (S-224). São coisas diferentes, e a
    Imagem 1 desenha exatamente isso -- cromo escuro com a página branca."""

    def __post_init__(self) -> None:
        if self.densidade not in DENSIDADES:
            raise KeyError(f"densidade desconhecida: {self.densidade!r}. As válidas estão em DENSIDADES.")


PELES: tuple[Pele, ...] = (
    Pele(CLASSICA, "Clássica", CROMO_CLASSICO),
    # Escura desde a S-224, e é a Imagem 1: cromo escuro com o documento claro. O que a pele
    # escurece é o cromo -- o tema `ttkbootstrap` que ela sugere, o fundo da dica, a superfície
    # de reserva e o texto sobre ela. A folha do livro e o tabuleiro ficam na paleta medida.
    Pele(FOCO, "Foco", CROMO_FOCO, cromo_escuro=True),
    # Clara, e a Imagem 2 é clara: o que ela propõe é agrupamento nomeado, não cromo escuro. Uma
    # fita escura seria uma decisão que ninguém tomou -- e a S-221 separou os eixos justamente
    # para que "a fita clara com o tabuleiro escuro" continuasse sendo escolha de quem a faz.
    Pele(FITA, "Fita", CROMO_FITA),
)
"""As peles registradas, na ordem em que o menu as lista.

Três desde a S-227, e é o pedido inteiro: *"o programa deve ter a opção da interface atual e essas
duas das imagens"*. A clássica é a primeira porque é o padrão -- quem nunca abrir `Ver ▸ Aparência`
tem a janela de sempre."""


por_nome: dict[str, Pele] = {registro.nome: registro for registro in PELES}


def registrada(nome: str) -> Pele:
    """A pele daquele nome. Levanta `KeyError` -- use `valida` quando o nome vem de fora."""
    if nome not in por_nome:
        raise KeyError(f"pele desconhecida: {nome!r}. As registradas estão em PELES.")
    return por_nome[nome]


def valida(nome: str) -> str:
    """O nome, se ele existe; `CLASSICA` com um `warning` que **nomeia** o inválido, se não.

    Não levanta, ao contrário de `registrada`: este é o caminho por onde entra o que veio do
    disco ou do ambiente, e nem estado antigo nem variável escrita errada podem impedir a janela
    de abrir. É o contrato de degradação de `ui/theme.py`, agora com um dono a mais.

    **Nomear o inválido é metade do valor.** `CVOFF_SKIN=fita` numa versão que ainda não tem a
    fita cai na clássica; sem o nome no log, quem a escreveu conclui que a variável não é lida.
    """
    if nome in por_nome:
        return nome
    if nome:
        logger.warning("Pele desconhecida: %r. Abrindo na %s.", nome, CLASSICA)
    return CLASSICA


def escolhida(guardada: str = "", *, ambiente: Mapping[str, str] | None = None) -> str:
    """A pele que vale ao abrir: `CVOFF_SKIN`, senão a guardada no estado, senão a clássica.

    **O ambiente ganha da guardada**, e é a diferença em relação a `theme.apply_theme`, onde o
    argumento explícito ganha da variável. Lá o argumento é de quem chama, no código; aqui a
    guardada é do disco, e uma variável de ambiente que o disco vencesse não serviria para o que
    ela existe -- abrir o programa numa aparência a partir de um roteiro.
    """
    fonte = ambiente if ambiente is not None else os.environ
    return valida(fonte.get(PELE_ENV, "") or guardada)
