"""A mesa de texto: o PDF à esquerda e o editor à direita, na própria janela (S-640/S-645).

**O pedido** foi "quando clicar no botão Texto, uma janela com o PDF à esquerda e o editor à
direita". A janela já tem as duas coisas -- o visualizador do livro e a aba Texto --, só que na
ordem contrária e com a aba espremida na coluna estreita da esquerda. A mesa é a **mesma janela com
o divisor trocado de lado**: o PDF que aparece à esquerda é o visualizador de verdade, com as caixas
dos diagramas e o sincronismo de folha que já funcionam. **Destacar a mesa numa janela própria** é
a S-646 (`qt/mesa_destacada.py`), para quem tem dois monitores; ela esperou a guarda de atalhos
passar a perguntar em que janela está o foco.

Este módulo é a decisão, sem toolkit: **quando** a mesa vale, e com que fração. Quem troca os lados
é `qt/disposicao_de_mesa.py`.
"""

from __future__ import annotations

__all__ = [
    "ACOES_DA_MESA_DESTACADA",
    "CARTAO_DA_MESA",
    "FOLHA_ANTERIOR_NA_MESA",
    "FOLHA_POR_LER_NA_MESA",
    "FOLHA_SEGUINTE_NA_MESA",
    "TITULO_DA_MESA",
    "FRACAO_PADRAO",
    "LARGURA_MINIMA",
    "MESA_AO_ABRIR_O_TEXTO",
    "MESA_NUNCA",
    "MESA_SEMPRE",
    "folha_vizinha",
    "fracao_da_mesa",
    "frase_da_folha_da_mesa",
    "ligada",
    "sempre",
    "vale_a_mesa",
]

MESA_AO_ABRIR_O_TEXTO = "texto"
MESA_NUNCA = "nunca"
MESA_SEMPRE = "sempre"
"""As três posições da preferência (`AppState.texto_mesa`), e `""` -- nunca escolhida -- é a primeira.

**Mora no estado da sessão, e não em `settings.py`**, e a razão é medida: `settings` está no caminho
de medição dos relatórios de campo (S-218), e uma seção nova ali muda a impressão do código que os
quatro relatórios declaram. **`sempre` é a terceira**, a que a segunda revisão do plano propôs: o PDF
à esquerda em toda área, e não só com o Texto à frente -- para quem confere o livro em qualquer aba.
Ela chegou com o resto do que faltava da aba Texto (2026-10-28), num segundo interruptor do menu."""

LARGURA_MINIMA = 1000
"""Abaixo desta largura de janela, em pixel, a mesa não se arma.

Com menos que isto, dar ao editor a metade larga deixaria o visualizador abaixo do mínimo dele, e o
divisor grampearia os dois lados num arranjo que não é nenhum dos dois. A disposição de antes fica."""

FRACAO_PADRAO = 0.45
"""A parte da largura que o PDF ocupa na mesa, na primeira vez: um pouco menos da metade.

O PDF está ali para ser **conferido**, e uma coluna de página inteira se lê em 45%; o editor é onde
se trabalha, e é ele que precisa das linhas compridas."""


ACOES_DA_MESA_DESTACADA: tuple[str, ...] = ("salvar", "desfazer", "refazer", "achar", "substituir")
"""As ações da tabela de atalhos que a janela da mesa destacada atende (S-646), **e só elas**.

São as do texto (`ui/texto_declarado.ACOES_PROPRIAS`), para que `Ctrl+F` com o foco na folha da mesa
ache no texto em vez de não fazer nada. As outras -- `Del`, as setas, `PgUp`/`PgDn`, `Ctrl+N` -- são
da janela principal, e com o foco na mesa elas não fazem nada: é o critério de aceite da S-646."""

TITULO_DA_MESA = "Mesa de texto"
CARTAO_DA_MESA = "O texto está na mesa, numa janela própria."
FOLHA_POR_LER_NA_MESA = "Esta folha ainda não foi lida. Ela aparece aqui quando o editor ao lado a ler."
"""O lugar da folha na janela da mesa quando o editor está no vazio «Ler a folha N» (S-644): mostrar
a folha de antes ao lado do convite a ler outra seria a folha e o texto discordando."""
FOLHA_ANTERIOR_NA_MESA = "Folha anterior"
FOLHA_SEGUINTE_NA_MESA = "Folha seguinte"
"""O cartão que ocupa o lugar da aba Texto enquanto a mesa está destacada, com «Mostrar» e «Trazer de volta»."""


def ligada(preferencia: str) -> bool:
    """A preferência guardada liga a mesa? `""` (nunca escolhida) e nome desconhecido valem o padrão. Pura."""
    return preferencia != MESA_NUNCA


def sempre(preferencia: str) -> bool:
    """A mesa vale em toda área, e não só com o Texto à frente? Pura."""
    return preferencia == MESA_SEMPRE


def vale_a_mesa(preferencia: str, *, texto_a_frente: bool, largura: int, destacada: bool = False) -> bool:
    """A mesa deve estar armada agora? Pura.

    **Perguntada ao trocar de área, e não a cada redimensionamento** -- quem chama é a troca de modo
    e a primeira aparição da janela. Arrastar a borda da janela não pode trocar os lados no meio do
    trabalho; a largura aqui é a do instante em que a pessoa entrou na área.

    Preferência desconhecida (o estado gravado por outra versão) vale como o padrão.

    **Com a mesa destacada** (S-646) o texto está noutra janela, e na aba Texto da principal fica o
    cartão: o PDF ao lado de um cartão seria a mesa sem o texto, e a folha já está na janela da mesa.
    Só a posição `sempre`, que quer o PDF à esquerda em toda área, arma assim mesmo.
    """
    if largura < LARGURA_MINIMA or not ligada(preferencia):
        return False
    return sempre(preferencia) or (texto_a_frente and not destacada)


def folha_vizinha(indice: int, passo: int, total: int) -> int | None:
    """A folha `passo` folhas adiante (ou atrás) na janela da mesa, ou `None` fora do livro. Pura.

    `total` zero é o livro que não se sabe: sem ele não há para onde virar.
    """
    alvo = int(indice) + int(passo)
    if total <= 0 or not 0 <= alvo < total:
        return None
    return alvo


def frase_da_folha_da_mesa(indice: int, total: int) -> str:
    """O rótulo entre as setas da janela da mesa: «Folha 13 de 289». Pura; `indice` é 0-based."""
    return f"Folha {int(indice) + 1} de {int(total)}" if total > 0 else f"Folha {int(indice) + 1}"


def fracao_da_mesa(guardada: float) -> float:
    """A fração do PDF na mesa: a da sessão anterior, ou a de fábrica. Pura.

    Zero é "nunca guardada", como em `AppState.sash_fraction`. Fora de (0,1) também cai no padrão:
    uma fração de 1,0 deixaria o editor sem largura nenhuma.
    """
    return guardada if 0.0 < guardada < 1.0 else FRACAO_PADRAO
