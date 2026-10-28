"""A barra do painel de Resultado como dado: grupos por tarefa, e o que vai para o "Mais" (S-528,
terceira barra).

**O que havia, medido em 2026-09-05 na janela a 1024x768 -- que é a aba que abre primeiro.** O
painel montava **nove botões de texto em quatro fileiras**: uma linha de navegação (`◄`, `►`,
"Selecionado", o seletor), uma de FEN ("Aplicar FEN digitada", "Copiar FEN"), uma de lado a jogar,
e uma `BarraFluida` com cinco ("Salvar a posição", "Salvar todas as posições da página",
"Desfazer", "Refazer", "Limpar") mais a caixa "Mapa de incerteza". Nenhum ícone. Ao lado, na mesma
tela, o painel do PDF desenha catorze traços de 16 px numa fila de 32 px de altura -- é a
diferença de gramática que o crítico da S-527 já tinha medido entre a sala e o livro, e que a
S-528 fechou de um lado só.

**A gramática é a mesma, e é por isso que este arquivo é só uma tabela.** A forma -- `Acao`,
`Item`, `cabem`, `dica_de` -- é `ui/barra.py`; o widget é `qt/barra.BarraEmFila`, o mesmo da sala e
o mesmo do livro. Aqui ficam as quatro decisões que são deste painel:

1. **Os grupos são cinco, e são as cinco perguntas de quem confere um diagrama lido**: qual dos
   diagramas da página (`DIAGRAMA`), o que a posição é por extenso (`FEN`), como corrigir o que o
   modelo errou (`CORRECAO`), o que guardar (`GRAVAR`) e o que ver por baixo das peças (`VISTA`).
2. **Dois controles ficam fora da fila, e não é esquecimento.** O campo de FEN é um `QLineEdit` de
   uma linha inteira -- ele **é** o conteúdo, não um gesto --, e o par de rádios "Lado a jogar"
   é uma pergunta de duas respostas exclusivas, que um botão de barra não sabe fazer. Os dois
   continuam em linhas próprias, abaixo da fila. O que saiu das quatro fileiras foram os **nove
   botões**, que é o que o crítico contou.
3. **O seletor de diagrama é encaixado, e não é ação.** `[2] de 7` é um `QSpinBox` pendurado por
   `BarraEmFila.encaixar` depois de "Diagrama anterior": a seta, o número e a outra seta são um
   controle só, e é a mesma decisão que a S-528 tomou para o campo de página do livro.
4. **O mapa de incerteza vai para o "Mais", pela razão de "marcar diagramas" no livro.** Ele é
   preferência e não gesto: liga-se uma vez e esquece-se. Eram ~180 px permanentes de `QCheckBox`
   com texto numa coluna de 494 px.

**As teclas não são registradas por esta barra.** `sequencia_de` devolve sempre `""`, como na do
livro: os comandos são da janela e já têm dono em `atalhos.ATALHOS`. Registrá-los de novo aqui
daria duas donas para a mesma tecla, que é a colisão que `atalhos.conferir_dono` acusa.

**E não há modos.** `grupos_desligados` devolve sempre vazio, e é a diferença em relação às outras
duas tabelas: aqui o que acende e apaga cada botão não é um estado do painel, é **uma pergunta por
ação** -- há diagrama lido? há o que desfazer? há o que refazer? --, e cada resposta é também a
frase que a dica mostra quando o botão está cinza (S-165/S-32). Um modo por grupo perderia
justamente o *porquê*, que é o item daquela regra.

Nada de `PyQt6`: quem monta widget não decide, e quem decide é afirmável sem abrir janela.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from . import barra as _barra
from . import strings
from .barra import ICONE_DO_MAIS, MAIS, ROTULO_DO_MAIS, SEPARADOR_DA_TECLA, Item, cabem, dica_de

__all__ = [
    "ACOES",
    "CORRECAO",
    "DIAGRAMA",
    "FEN",
    "GRAVAR",
    "GRUPOS",
    "ICONE_DO_MAIS",
    "MAIS",
    "METODOS_DO_PAINEL",
    "MODO_UNICO",
    "MODOS",
    "ROTULO_DO_MAIS",
    "SEPARADOR_DA_TECLA",
    "VISTA",
    "Acao",
    "Item",
    "acao",
    "cabem",
    "dica_de",
    "do_grupo",
    "grupos_desligados",
    "por_acao",
    "principais",
    "rotulo_do_grupo",
    "secundarias",
    "sequencia_de",
    "sufixo_de_diagramas",
]

DIAGRAMA = "diagrama"
FEN = "fen"
CORRECAO = "correcao"
GRAVAR = "gravar"
VISTA = "vista"

GRUPOS: tuple[str, ...] = (DIAGRAMA, FEN, CORRECAO, GRAVAR, VISTA)
"""Os cinco, na ordem da barra -- que é a ordem em que se confere um diagrama: escolhe-se qual,
lê-se a posição, corrige-se o que o modelo errou, e grava-se."""

_ROTULOS_DE_GRUPO: dict[str, str] = {
    DIAGRAMA: "Diagrama",
    FEN: "FEN",
    CORRECAO: "Correção",
    GRAVAR: "Gravar",
    VISTA: "Vista",
}
"""Como o grupo se escreve quando vira cabeçalho de seção no menu "Mais"."""

COPIAR_FEN_LIDA = "copiar_fen_lida"
"""O único nome fora do catálogo desta barra, e a distinção é real.

`copiar_fen` **existe** no catálogo, e é "Copiar a FEN do estudo": ele copia a posição da sala, com
os lances jogados por cima. Este copia a FEN que o modelo **leu** desta página, que é o que se cola
num analisador para conferir a leitura. Reusar o comando da sala faria o menu prometer uma coisa e
o botão fazer outra -- que é o defeito que `ui/comandos.py` existe para não ter."""

MAPA_DE_INCERTEZA = "mapa_de_incerteza"
"""O interruptor da tinta de dúvida (S-21/S-506). Fora do catálogo pela razão de "marcar
diagramas" antes da S-528: ele não é comando da janela, é preferência de desenho deste painel."""

METODOS_DO_PAINEL: dict[str, str] = {
    "diagrama_anterior": "diagrama_anterior",
    "proximo_diagrama": "proximo_diagrama",
    "aplicar_fen": "aplicar_fen",
    COPIAR_FEN_LIDA: "copiar_fen_lida",
    "desfazer": "desfazer",
    "refazer": "refazer",
    "limpar_tabuleiro": "limpar_tabuleiro",
    "salvar": "salvar_atual",
    "salvar_todos": "salvar_todos",
    MAPA_DE_INCERTEZA: "alternou_mapa_de_incerteza",
}
"""Ação -> método de `PainelDeResultado`, no formato de `barra_do_pdf.METODOS_DO_PAINEL`.

**A tabela é a declaração, e o widget não conhece método nenhum.** Antes disto os nove botões eram
ligados por `lambda` escrito no meio da montagem (`lambda: self.andar(-1)`), que é o lugar em que
um botão deixa de fazer o que o menu faz sem que nada acuse."""


@dataclass(frozen=True)
class Acao(_barra.Acao):
    """Uma ação da barra do Resultado. A forma é `ui/barra.Acao`; aqui não há campo novo nenhum."""

    GRUPOS: ClassVar[tuple[str, ...]] = GRUPOS


ACOES: tuple[Acao, ...] = (
    # --------------------------------------------------------------------------- DIAGRAMA
    # **Prioridade 2 e um par**: `◄` sem `►` é meia navegação, e é a mesma decisão do par de
    # página do livro. O seletor `[2] de 7` é encaixado depois da primeira seta e acompanha as duas.
    Acao("diagrama_anterior", DIAGRAMA, "diagrama_anterior", prioridade=2),
    Acao("proximo_diagrama", DIAGRAMA, "proximo_diagrama", prioridade=2),
    # -------------------------------------------------------------------------------- FEN
    Acao(
        "aplicar_fen",
        FEN,
        "aplicar_fen",
        prioridade=3,
        dica="Lê a FEN digitada no campo abaixo e põe a posição dela no tabuleiro.\n"
        "Enter dentro do campo faz o mesmo.",
    ),
    Acao(
        COPIAR_FEN_LIDA,
        FEN,
        "copiar",
        prioridade=6,
        rotulo_proprio=strings.COPIAR_FEN,
        dica="Põe na área de transferência a FEN que o modelo leu, com as correções feitas aqui.",
    ),
    # --------------------------------------------------------------------------- CORRECAO
    # Desfazer e refazer são um par pela razão do de cima: quem desfaz por engano precisa do
    # caminho de volta na mesma fila, e não escondido no "Mais".
    Acao("desfazer", CORRECAO, "desfazer", prioridade=5),
    Acao("refazer", CORRECAO, "refazer", prioridade=5),
    Acao("limpar_tabuleiro", CORRECAO, "limpar_tabuleiro", prioridade=7),
    # ----------------------------------------------------------------------------- GRAVAR
    # O único `PRIMARIO` do painel, e a ênfase é do catálogo (S-324/S-446): a tela existe para
    # conferir uma leitura, e gravar a leitura conferida é o que ela faz. Com texto pela razão do
    # "OCR melhor diagrama" no livro -- o que se lê de longe.
    Acao("salvar", GRAVAR, "salvar", prioridade=1, com_texto=True),
    Acao("salvar_todos", GRAVAR, "salvar_todos", prioridade=4),
    # ------------------------------------------------------------------------------ VISTA
    Acao(
        MAPA_DE_INCERTEZA,
        VISTA,
        "mapa_de_incerteza",
        principal=False,
        marcavel=True,
        rotulo_proprio=strings.MAPA_DE_INCERTEZA,
        dica="Tinge as casas de leitura duvidosa. Desligado, a peça lida aparece limpa.",
    ),
)
"""A barra inteira, na ordem em que ela se desenha."""

por_acao: dict[str, Acao] = {registro.acao: registro for registro in ACOES}

Acao.IRMAS = ACOES
Acao.METODOS = METODOS_DO_PAINEL


def acao(nome: str) -> Acao:
    """O registro daquela ação. Levanta `KeyError` para nome que a barra não tem."""
    if nome not in por_acao:
        raise KeyError(f"ação fora da barra do resultado: {nome!r}")
    return por_acao[nome]


def rotulo_do_grupo(grupo: str) -> str:
    if grupo not in _ROTULOS_DE_GRUPO:
        raise KeyError(f"grupo desconhecido: {grupo!r}. Os válidos estão em GRUPOS.")
    return _ROTULOS_DE_GRUPO[grupo]


def do_grupo(grupo: str) -> tuple[Acao, ...]:
    rotulo_do_grupo(grupo)
    return tuple(registro for registro in ACOES if registro.grupo == grupo)


def principais() -> tuple[Acao, ...]:
    """As que ganham botão, na ordem da barra."""
    return tuple(registro for registro in ACOES if registro.principal)


def secundarias() -> tuple[Acao, ...]:
    """As que vão direto para o "Mais", na ordem da barra."""
    return tuple(registro for registro in ACOES if not registro.principal and not registro.dentro_de)


def sequencia_de(nome: str) -> str:
    """Vazio, sempre: as teclas destes comandos são da janela. Ver o cabeçalho."""
    _ = nome
    return ""


MODO_UNICO = "unico"
"""O único modo desta barra. Ver o cabeçalho: aqui quem acende e apaga é uma pergunta por ação."""

MODOS: tuple[str, ...] = (MODO_UNICO,)


def grupos_desligados(qual: str) -> frozenset[str]:
    """Vazio, sempre. Recusa modo desconhecido, como as outras duas tabelas."""
    if qual not in MODOS:
        raise KeyError(f"modo desconhecido: {qual!r}. Os válidos estão em MODOS.")
    return frozenset()


def sufixo_de_diagramas(total: int) -> str:
    """O ` de 7` que o seletor escreve depois do número. Pura.

    Era o `QLabel` "Selecionado" à esquerda do campo, e ele não dizia o total: para saber quantos
    diagramas a página tinha era preciso contar a lista acima. Dentro do campo, o número e o total
    não se separam, e o par pesa um widget em vez de dois -- é a decisão de `sufixo_de_paginas`
    (S-528), na escala deste painel.
    """
    return f" de {max(0, int(total))}"
