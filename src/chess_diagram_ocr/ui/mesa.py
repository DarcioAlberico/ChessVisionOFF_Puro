"""A mesa de texto: o PDF à esquerda e o editor à direita, na própria janela (S-640/S-645).

**O pedido** foi "quando clicar no botão Texto, uma janela com o PDF à esquerda e o editor à
direita". A janela já tem as duas coisas -- o visualizador do livro e a aba Texto --, só que na
ordem contrária e com a aba espremida na coluna estreita da esquerda. A mesa é a **mesma janela com
o divisor trocado de lado**: o PDF que aparece à esquerda é o visualizador de verdade, com as caixas
dos diagramas e o sincronismo de folha que já funcionam. Uma janela separada ficou para depois
(S-646 no `docs/ROADMAP_MESA_DE_TEXTO.md`): a guarda de atalhos é da aplicação inteira e não
pergunta em que janela está o foco.

Este módulo é a decisão, sem toolkit: **quando** a mesa vale, e com que fração. Quem troca os lados
é `qt/janela.py`.
"""

from __future__ import annotations

__all__ = [
    "FRACAO_PADRAO",
    "LARGURA_MINIMA",
    "MESAS",
    "MESA_AO_ABRIR_O_TEXTO",
    "MESA_NUNCA",
    "MESA_SEMPRE",
    "fracao_da_mesa",
    "vale_a_mesa",
]

MESA_AO_ABRIR_O_TEXTO = "texto"
MESA_SEMPRE = "sempre"
MESA_NUNCA = "nunca"

MESAS: tuple[str, ...] = (MESA_AO_ABRIR_O_TEXTO, MESA_SEMPRE, MESA_NUNCA)
"""As três posições da preferência, a primeira é o padrão. Conjunto fechado.

**Três e não um interruptor**, e a razão é a da segunda revisão do plano: trocar o divisor a cada
troca de modo reflui a janela inteira, e quem alterna entre o Texto e o Resultado o tempo todo
pode preferir que o PDF **fique** à esquerda (`sempre`) -- ou nunca saia da direita (`nunca`,
a disposição de antes)."""

LARGURA_MINIMA = 1000
"""Abaixo desta largura de janela, em pixel, a mesa não se arma.

Com menos que isto, dar ao editor a metade larga deixaria o visualizador abaixo do mínimo dele, e o
divisor grampearia os dois lados num arranjo que não é nenhum dos dois. A disposição de antes fica."""

FRACAO_PADRAO = 0.45
"""A parte da largura que o PDF ocupa na mesa, na primeira vez: um pouco menos da metade.

O PDF está ali para ser **conferido**, e uma coluna de página inteira se lê em 45%; o editor é onde
se trabalha, e é ele que precisa das linhas compridas."""


def vale_a_mesa(preferencia: str, *, texto_a_frente: bool, largura: int) -> bool:
    """A mesa deve estar armada agora? Pura.

    **Perguntada ao trocar de área, e não a cada redimensionamento** -- quem chama é a troca de modo
    e a primeira aparição da janela. Arrastar a borda da janela não pode trocar os lados no meio do
    trabalho; a largura aqui é a do instante em que a pessoa entrou na área.

    Preferência desconhecida (um `settings.json` de outra versão) vale como o padrão.
    """
    if largura < LARGURA_MINIMA:
        return False
    if preferencia == MESA_NUNCA:
        return False
    if preferencia == MESA_SEMPRE:
        return True
    return texto_a_frente


def fracao_da_mesa(guardada: float) -> float:
    """A fração do PDF na mesa: a da sessão anterior, ou a de fábrica. Pura.

    Zero é "nunca guardada", como em `AppState.sash_fraction`. Fora de (0,1) também cai no padrão:
    uma fração de 1,0 deixaria o editor sem largura nenhuma.
    """
    return guardada if 0.0 < guardada < 1.0 else FRACAO_PADRAO
