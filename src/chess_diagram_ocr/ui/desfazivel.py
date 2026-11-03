"""Quem desfaz quando se aperta `Ctrl+Z`: o foco decide, e a regra é pura (S-243).

**Duas pilhas, dois donos, uma tecla só.** A S-229 deu desfazer e refazer ao **tabuleiro**, com
pilha de posições em `ui/historico.py`. O editor de texto tem a dele desde sempre -- `tk.Text` com
`undo=True` --, e ela não tinha comando, botão nem item de menu: o desfazer existia e era
indescobrível.

Ligar a tecla a um dos dois seria escolher errado metade das vezes. Ligá-la aos dois faria `Ctrl+Z`
no texto mexer no tabuleiro que ninguém estava olhando -- que é exatamente o defeito que a S-117
mediu com as setas: *"analisar uma posição com as setas movia, invisivelmente, o cursor do editor
em outra aba"*.

## A regra, e o caso que ela existe para tratar

    1. o desfazível que **contém** o widget em foco
    2. senão, o **último que recebeu edição**
    3. senão, nenhum

O passo 2 é o item. Sem foco em nenhum dos dois -- o cursor num botão da barra, que é onde ele fica
depois de qualquer clique --, "nenhum" faria `Ctrl+Z` não fazer nada logo depois de uma edição, que
é o defeito clássico deste desenho. O último editado é a resposta que a pessoa espera, e ela é
barata: quem edita carimba um número que só cresce.

## A fronteira que este módulo não cruza

A pilha do editor continua sendo a do Tk. Reimplementá-la sobre o `DocumentoRico` seria refazer o
que o widget já faz bem, e a S-235 não exige isso: o documento é reconstruído do widget quando se
salva, e a pilha é do widget porque o gesto de digitar é do widget.

Nada de `tkinter` aqui: `contem` recebe um objeto qualquer, e é o painel que sabe o que é um widget.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

__all__ = ["Desfazivel", "alvo_de_desfazer"]


@runtime_checkable
class Desfazivel(Protocol):
    """O que um painel precisa oferecer para entrar na disputa pelo `Ctrl+Z`."""

    def contem(self, widget: object) -> bool:
        """Aquele widget está dentro deste desfazível? É o que o foco responde."""

    def desfazer(self) -> None: ...

    def refazer(self) -> None: ...

    @property
    def edicao(self) -> int:
        """Um número que **só cresce** a cada edição recebida. Zero = nunca editado.

        Não é relógio: é contador. Relógio de parede empataria duas edições no mesmo milissegundo
        -- e um contador não depende de a máquina estar com a hora certa, que é a mesma razão pela
        qual os scripts de medição deste projeto não chamam `Date.now`."""


def ultimo_editado(registrados: Sequence[Desfazivel]) -> Desfazivel | None:
    """O que recebeu edição por último, ou `None` se nenhum recebeu nenhuma.

    Empate fica com o **primeiro registrado**, e não com o último: a ordem de registro é a de
    construção da janela, e é estável entre execuções -- um empate resolvido pela ordem de iteração
    de um `set` faria a mesma tecla fazer coisas diferentes em dois dias iguais.
    """
    com_edicao = [d for d in registrados if getattr(d, "edicao", 0) > 0]
    if not com_edicao:
        return None
    return max(com_edicao, key=lambda d: (d.edicao, -registrados.index(d)))


def alvo_de_desfazer(foco: object, registrados: Sequence[Desfazivel]) -> Desfazivel | None:
    """Quem desfaz agora: o desfazível que contém o widget em foco, ou o último a receber edição.

    `foco` é o widget que tem o foco de teclado -- `root.focus_get()` --, e pode ser `None`: numa
    janela que acabou de abrir, ou logo depois de o foco sair para outro programa.
    """
    for desfazivel in registrados:
        try:
            if foco is not None and desfazivel.contem(foco):
                return desfazivel
        except Exception:  # noqa: BLE001 - widget destruído, ou painel que ainda não montou
            # Não derruba a tecla por causa de um painel: a pergunta seguinte pode responder, e o
            # pior caso é cair no último editado -- que é a resposta certa quando não há foco.
            continue
    return ultimo_editado(registrados)
