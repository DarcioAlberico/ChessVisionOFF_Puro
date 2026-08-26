"""A lista de lances como dado: trechos com papel, nível e caminho (S-273).

**O que ela substitui.** Um `StringExporter` despejado num `tk.Text` de cinco linhas com
`state=DISABLED`. Não se clicava num lance, não se via qual era o corrente, e com variantes o
resultado era `1. e4 e5 2. Nf3 ( 2. Bc4 Bc5 ) Nc6` corrido -- achar onde se estava era impossível.

**E a parte difícil não é desenhar: é numerar.** A regra do PGN é que o primeiro lance de qualquer
variante imprime o número (com `...` se for das pretas); dentro dela, brancas imprimem `N.` e pretas
não imprimem nada -- **exceto** logo depois de um comentário ou de uma subvariante, onde as pretas
voltam a imprimir `N...`. O plugin que serviu de referência resolve isso com quatro condicionais
aninhadas e mesmo assim só cobre variante de profundidade 1.

## A trava que torna este módulo seguro

`texto_de(trechos(e))` tem de ser igual, token a token, ao que
`chess.pgn.StringExporter(headers=False, variations=True, comments=True)` produz para o mesmo
estudo. Não é elegância: a numeração de variante é a parte que todo visualizador de PGN erra, e o
`StringExporter` acerta há anos. **Enquanto a igualdade valer, não estamos adivinhando.** É a mesma
trava que a S-235 usou para o `para_texto()` do documento rico.

Por isso a travessia daqui é a mesma do `chess.pgn._accept`: emite o lance, depois os **irmãos** dele
como variantes entre parênteses, e só então a continuação da linha. Trocar essa ordem produz um PGN
que parece certo e numera errado.

## Dois papéis que não são texto de PGN

`RAIZ` é a posição do diagrama como item clicável -- ela não existe no PGN, e `texto_de` a ignora.
É a pendência que o plugin de referência registra no próprio código (*"TODO: Allow to show the root
position"*).

`NAG` e `COMENTARIO` **desenham uma coisa e gravam outra**: a lista mostra `!` e a frase da pessoa, o
PGN grava `$1` e `{ [%cal Gf3g5] a frase }`. Daí o campo `token`: `texto` é o que se lê, `pgn` é o
que se compara. Sem essa separação, ou a lista mostraria `$1` e os comandos de seta, ou a trava
acima deixaria de valer.

Nada de `tkinter` aqui: quem desenha é `ui/study_panel.py`, e o que ele desenha é afirmável sem
abrir janela.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from ..estudo import Caminho, Estudo, caminho_de, simbolo_de_nag, texto_do_comentario

__all__ = [
    "ABRE",
    "COMENTARIO",
    "FECHA",
    "LANCE",
    "NAG",
    "NIVEL_MAXIMO_DE_RECUO",
    "NUMERO",
    "RAIZ",
    "RESULTADO",
    "Trecho",
    "ate",
    "texto_de",
    "trecho_do_caminho",
    "trechos",
]

RAIZ = "raiz"
"""A posição do diagrama, como item. **O único papel que não é texto do PGN.**"""

NUMERO = "numero"
"""`12. ` ou `12... `. Clicável, e leva ao mesmo lance que o `LANCE` ao lado."""

LANCE = "lance"
COMENTARIO = "comentario"
NAG = "nag"
ABRE = "abre"
FECHA = "fecha"
RESULTADO = "resultado"
"""`*`, `1-0`, `0-1`. Sai no `texto_de` porque o `StringExporter` o escreve; a aba o esconde quando é
`*`, que é o caso de todo estudo que não veio de uma partida terminada."""

NIVEL_MAXIMO_DE_RECUO = 4
"""Quantos níveis de variante o recuo distingue antes de saturar.

O recuo satura e a **numeração não**: um recuo que cresce sem limite empurra a linha para fora da
janela, e a informação de que aquilo é uma subvariante de quinto nível não vale a linha ilegível. O
número do lance, esse, nunca satura -- ele é a informação."""


@dataclass(frozen=True)
class Trecho:
    """Um pedaço da lista: o que se lê, o que se grava, e a que lance ele pertence."""

    texto: str
    """O que a aba desenha. Vazio significa "não desenhe nada" -- é o caso do comentário que só
    tem comandos de seta, que existe no PGN e não tem o que mostrar."""

    papel: str
    caminho: Caminho | None = None
    """O nó a que um clique leva. `None` em pontuação e no resultado, que não são lugar nenhum."""

    nivel: int = 0
    """0 é a linha principal; 1 é variante, 2 é subvariante, e daí para cima."""

    token: str = ""
    """O texto do PGN, quando ele difere do desenhado. Ver o cabeçalho."""

    @property
    def pgn(self) -> str:
        return self.token or self.texto

    @property
    def recuo(self) -> int:
        return min(self.nivel, NIVEL_MAXIMO_DE_RECUO)


class _Estado:
    """`force_movenumber` do `StringExporterMixin`, com o mesmo nome de coisa que ele tem lá."""

    def __init__(self) -> None:
        self.forcar = True


def trechos(estudo: Estudo) -> tuple[Trecho, ...]:
    """A lista inteira daquele estudo, da raiz ao resultado."""
    saida: list[Trecho] = []
    jogo = estudo.jogo
    saida.append(Trecho(texto=_rotulo_da_raiz(estudo), papel=RAIZ, caminho=(), nivel=0))

    estado = _Estado()
    if jogo.comment:
        _comentario(saida, jogo.comment, (), 0, estado)
    _linha(saida, jogo, jogo.board(), 0, estado)

    saida.append(Trecho(texto=f"{jogo.headers.get('Result', '*')} ", papel=RESULTADO, nivel=0))
    return tuple(saida)


def texto_de(lista: tuple[Trecho, ...] | list[Trecho]) -> str:
    """O PGN que esses trechos formam -- e é isto que o teste compara com o `StringExporter`."""
    return "".join(trecho.pgn for trecho in lista if trecho.papel != RAIZ)


def ate(lista: tuple[Trecho, ...] | list[Trecho], caminho: Caminho) -> tuple[Trecho, ...]:
    """A lista **cortada no lance corrente**, para o modo de treino (S-290).

    O que vem depois some -- a continuação, as variantes, o resultado. É o que faz o treino ser
    treino: a linha some, e o tabuleiro cobra o lance.

    **Corta, e não filtra.** Filtrar os descendentes deixaria parênteses órfãos na tela -- um `(` de
    variante cujo conteúdo sumiu --, e um `)` sem par lido como notação é pior que a linha inteira à
    mostra. Cortar no último trecho do nó corrente não tem esse problema, e diz a mesma coisa.

    Caminho que não está na lista devolve **só a raiz**, que é o que se vê antes do primeiro lance.
    """
    ultimo = -1
    for indice, trecho in enumerate(lista):
        if trecho.caminho == caminho and trecho.papel in (LANCE, NAG, COMENTARIO, RAIZ):
            ultimo = indice
    if ultimo < 0:
        return tuple(trecho for trecho in lista if trecho.papel == RAIZ)
    return tuple(lista[: ultimo + 1])


def trecho_do_caminho(lista: tuple[Trecho, ...] | list[Trecho], caminho: Caminho) -> int:
    """O índice do trecho de `LANCE` daquele caminho, ou `-1`. É como a aba acha o lance corrente."""
    for indice, trecho in enumerate(lista):
        if trecho.papel in (LANCE, RAIZ) and trecho.caminho == caminho:
            return indice
    return -1


# ------------------------------------------------------------------------------ travessia


def _rotulo_da_raiz(estudo: Estudo) -> str:
    """"posição do diagrama" quando o estudo veio do livro; "posição inicial" quando não.

    São duas coisas diferentes, e quem estuda sabe a diferença: uma é o que está impresso na página,
    a outra é o começo de uma partida.
    """
    return "posição do diagrama " if estudo.ancora.valida else "posição inicial "


def _linha(
    saida: list[Trecho], no: chess.pgn.GameNode, tabuleiro: chess.Board, nivel: int, estado: _Estado
) -> None:
    """Emite a continuação de `no`. `tabuleiro` é a posição **em** `no`, e é consumido aqui."""
    board = tabuleiro.copy(stack=False)
    atual = no
    while atual.variations:
        filhos = list(atual.variations)
        principal = filhos[0]
        _no(saida, principal, board, nivel, estado)

        for alternativa in filhos[1:]:
            # Os irmãos vêm **depois** do lance principal e **antes** da continuação dele. É a ordem
            # de `chess.pgn._accept`, e trocá-la produz um PGN que parece certo e numera errado.
            saida.append(Trecho(texto="( ", papel=ABRE, nivel=nivel + 1))
            estado.forcar = True
            _no(saida, alternativa, board, nivel + 1, estado)
            depois = board.copy(stack=False)
            depois.push(alternativa.move)
            _linha(saida, alternativa, depois, nivel + 1, estado)
            saida.append(Trecho(texto=") ", papel=FECHA, nivel=nivel + 1))
            estado.forcar = True

        board.push(principal.move)
        atual = principal


def _no(
    saida: list[Trecho], no: chess.pgn.GameNode, board: chess.Board, nivel: int, estado: _Estado
) -> None:
    """Um lance e o que vem colado nele: comentário de entrada, número, SAN, símbolos, comentário."""
    lance = no.move
    if lance is None:  # pragma: no cover - só a raiz tem `move` vazio, e ela não entra aqui
        return
    caminho = caminho_de(no)

    if no.starting_comment:
        _comentario(saida, no.starting_comment, caminho, nivel, estado)

    if board.turn == chess.WHITE:
        saida.append(Trecho(f"{board.fullmove_number}. ", NUMERO, caminho, nivel))
    elif estado.forcar:
        saida.append(Trecho(f"{board.fullmove_number}... ", NUMERO, caminho, nivel))

    saida.append(Trecho(f"{board.san(lance)} ", LANCE, caminho, nivel))
    estado.forcar = False

    for nag in sorted(no.nags):
        saida.append(
            Trecho(texto=f"{simbolo_de_nag(nag)} ", papel=NAG, caminho=caminho, nivel=nivel, token=f"${nag} ")
        )

    if no.comment:
        _comentario(saida, no.comment, caminho, nivel, estado)


def _comentario(
    saida: list[Trecho], bruto: str, caminho: Caminho, nivel: int, estado: _Estado
) -> None:
    """Um comentário: desenha a frase da pessoa, grava o comentário inteiro.

    A chave `}` é retirada como o `StringExporterMixin` a retira -- ela fecharia o comentário no meio
    e o PGN deixaria de ser legível.
    """
    visivel = texto_do_comentario(bruto)
    token = "{ " + str(bruto).replace("}", "").strip() + " } "
    saida.append(
        Trecho(
            texto=f"{visivel} " if visivel else "",
            papel=COMENTARIO,
            caminho=caminho,
            nivel=nivel,
            token=token,
        )
    )
    estado.forcar = True
