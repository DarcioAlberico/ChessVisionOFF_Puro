"""Dobrar variantes na lista de lances: o que se esconde, e o que não pode se esconder (S-516).

**O gatilho deste item, e ele é medido.** A lista corrida serve bem um estudo de livro -- 66
trechos na fotografia de 2026-09-01, que é o tamanho típico de um diagrama anotado. Ela deixa de
servir quando o estudo passa de umas três dezenas de lances com subvariantes, que é o que acontece
ao abrir uma partida anotada pelo "Abrir PGN…" (o comando aceita 20 MB). Ali, achar a linha em que
se está exige rolar a lista inteira, e a subvariante de terceiro grau ocupa a mesma altura da
principal.

**A decisão que este módulo carrega é uma só: o que fica escondido.** Ela é pura, e é a única parte
do dobrar que tem regra -- desenhar o `(…)` é do widget.

**A identidade de uma variante é o caminho do primeiro lance dela**, e não o índice do `(` na
lista. Índices de trecho mudam a cada redesenho, e promover ou apagar variante reordena as irmãs:
uma dobra guardada por índice se mudaria de dona no gesto seguinte, que é a mesma armadilha que a
S-268 documenta para a navegação. Caminho que deixou de existir simplesmente não casa com nenhuma
variante, e a dobra some -- que é a degradação certa para estado de **vista**.

**E o lance corrente nunca se esconde.** Uma dobra que engolisse o nó em que se está deixaria a
lista sem dizer onde a pessoa está, e o tabuleiro ao lado mostrando uma posição que a lista não
tem. A dobra continua declarada -- ela volta a valer quando a navegação sai dali --, mas não é
aplicada enquanto contiver o corrente.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..estudo import Caminho
from . import estudo_lista

__all__ = ["Variante", "escondidos", "variantes"]


@dataclass(frozen=True)
class Variante:
    """Um `( ... )` da lista: onde ele abre, onde fecha, quem ele é, e o que há dentro."""

    abre: int
    """Índice do trecho `ABRE`. É onde o widget desenha o controle."""

    fecha: int
    """Índice do trecho `FECHA` correspondente."""

    chave: Caminho
    """O caminho do primeiro lance da variante -- a identidade dela. Ver o cabeçalho."""

    caminhos: frozenset[Caminho]
    """Todo caminho que esta variante contém, **inclusive os das subvariantes dela**.

    É o que responde "o corrente está aqui dentro?" sem a lista precisar percorrer nada de novo."""


def variantes(trechos: Sequence[estudo_lista.Trecho]) -> tuple[Variante, ...]:
    """As variantes daquela lista, da mais interna para a mais externa em ordem de fechamento.

    Um `ABRE` sem `FECHA` -- que a travessia de `estudo_lista` não produz, mas um corte de treino
    pode -- é descartado: uma variante sem fim não tem o que esconder.
    """
    pilha: list[int] = []
    achadas: list[Variante] = []
    for indice, trecho in enumerate(trechos):
        if trecho.papel == estudo_lista.ABRE:
            pilha.append(indice)
            continue
        if trecho.papel != estudo_lista.FECHA or not pilha:
            continue
        abre = pilha.pop()
        dentro = trechos[abre + 1 : indice]
        caminhos = frozenset(t.caminho for t in dentro if t.caminho is not None)
        chave = next((t.caminho for t in dentro if t.caminho is not None), None)
        if chave is None:
            continue  # variante sem lance nenhum: não há o que dobrar nem como nomeá-la
        achadas.append(Variante(abre=abre, fecha=indice, chave=chave, caminhos=caminhos))
    return tuple(achadas)


def escondidos(
    trechos: Sequence[estudo_lista.Trecho],
    dobradas: Iterable[Caminho],
    corrente: Caminho | None = None,
) -> frozenset[int]:
    """Os índices de trecho que não se desenham, dadas as variantes dobradas.

    **Os dois parênteses ficam.** O que some é o miolo, e o widget desenha `(…)` no lugar -- uma
    variante dobrada que sumisse inteira não diria que existe, e o gesto de desdobrá-la não teria
    onde acontecer.

    Dobra que contém o `corrente` **não é aplicada** (ver o cabeçalho). Ela continua na lista de
    dobradas: sair dali com a seta devolve o estado que a pessoa pediu, sem ela precisar pedir de
    novo.
    """
    alvo = frozenset(dobradas)
    if not alvo:
        return frozenset()
    ocultos: set[int] = set()
    for variante in variantes(trechos):
        if variante.chave not in alvo:
            continue
        if corrente is not None and corrente in variante.caminhos:
            continue
        ocultos.update(range(variante.abre + 1, variante.fecha))
    return frozenset(ocultos)
