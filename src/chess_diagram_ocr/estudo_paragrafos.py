"""O estudo em parágrafos de livro: linha, variante recuada, comentário, diagrama pedido (S-542/S-543).

**Por que uma travessia a mais, quando `estudo_saida.para_documento` já existe.** Aquela devolve o
estudo como `DocumentoRico` -- um título, um diagrama e **uma linha só** com tudo dentro, porque é
o que a aba de texto recebe e o que os quatro formatos da Fase 39 sabem escrever. Um livro não é
escrito assim. O livro imprime a linha principal em negrito, corta-a onde há comentário, recua a
variante um degrau e volta; e imprime um diagrama onde o autor pediu -- no PGN, é o comando `[%D]`
dentro do comentário do lance, a convenção do ChessBase e do Scid.

Este módulo é **a decisão de paginação**, e nada mais: ele diz que parágrafos existem, de que tipo,
com que recuo e com que texto. Quem escreve XHTML é `epub.py`; quem escreve OOXML é `docx_saida.py`;
os dois leem a mesma lista, e é isso que impede o EPUB e o DOCX de discordarem sobre onde a
variante começa. A travessia por baixo continua sendo `ui/estudo_lista.trechos` -- a numeração de
variante, que é a parte que todo visualizador erra, sai de lá e é conferida contra o `chess.pgn`.

## As regras, uma por linha

- A variante de **primeiro nível** vira parágrafo próprio, recuado, **sem os parênteses**: o recuo
  já diz que ela é variante. As mais fundas ficam dentro dela, entre parênteses, como `trechos`
  já as escreve -- recuar quatro níveis empurra a linha para fora da tela do leitor.
- O comentário de um lance da **linha principal** corta a linha e vira parágrafo de prosa; o da
  variante fica dentro dela. É a diferença entre o comentário do autor e o aparte.
- `[%D]` no comentário de um lance pede um diagrama **depois** do comentário, com a posição
  daquele lance. O da raiz sai sempre, porque é o diagrama do livro.
- A linha que continua depois de um comentário ou de uma variante é parágrafo novo e traz o
  número do lance de novo (`12...`), que é o que `trechos` já faz com `forcar`.
- O resultado `*` não sai; `1-0`, `0-1` e `1/2-1/2` saem no fim da linha principal.
"""

from __future__ import annotations

from dataclasses import dataclass

from chess_diagram_ocr.estudo import Estudo, no_em, texto_do_comentario
from chess_diagram_ocr.ui.estudo_lista import (
    ABRE,
    COMENTARIO,
    FECHA,
    RAIZ,
    RESULTADO,
    Trecho,
    trechos,
)

__all__ = [
    "COMENTARIO_DO_ESTUDO",
    "DIAGRAMA",
    "LANCE",
    "MARCA_DE_DIAGRAMA",
    "TITULO",
    "VARIANTE",
    "Paragrafo",
    "paragrafos",
    "titulo_do_estudo",
]

TITULO = "titulo"
DIAGRAMA = "diagrama"
COMENTARIO_DO_ESTUDO = "comentario"
LANCE = "lance"
VARIANTE = "variante"

MARCA_DE_DIAGRAMA = "[%D"
"""O começo do comando que pede um diagrama. É o `[%D]` do ChessBase; `trechos` guarda o comentário
inteiro em `Trecho.token`, então basta procurar ali."""


@dataclass(frozen=True)
class Paragrafo:
    """Um parágrafo do livro. `texto` para os de texto; `fen` e `virado` para o diagrama."""

    tipo: str
    texto: str = ""
    nivel: int = 0
    """0 é a linha principal; 1 é a variante recuada. Só `VARIANTE` tem nível acima de zero."""

    fen: str = ""
    virado: bool = False
    numero: int = 0
    """O número de ordem do diagrama no estudo, a partir de 1. Zero nos parágrafos de texto."""


def titulo_do_estudo(estudo: Estudo) -> str:
    """O mesmo título de `estudo_saida.para_documento`: o endereço no livro, ou "Estudo avulso"."""
    return estudo.ancora.rotulo() if estudo.ancora.valida else "Estudo avulso"


def paragrafos(estudo: Estudo) -> tuple[Paragrafo, ...]:
    """O estudo inteiro, na ordem em que o livro o imprime."""
    montador = _Montador(estudo)
    montador.titulo()
    montador.diagrama(estudo.raiz.board().fen())
    raiz = texto_do_comentario(estudo.raiz.comment or "")
    if raiz:
        montador.comentario(raiz)

    for trecho in trechos(estudo):
        if trecho.papel == RAIZ or (trecho.papel == COMENTARIO and not trecho.caminho):
            continue
        if trecho.papel == RESULTADO:
            resultado = trecho.texto.strip()
            if resultado and resultado != "*":
                montador.lance(f"{resultado} ", 0)
            continue
        montador.trecho(trecho)
    montador.fechar()
    return tuple(montador.saida)


class _Montador:
    """Acumula o texto do parágrafo corrente e o fecha quando a regra manda."""

    def __init__(self, estudo: Estudo) -> None:
        self.estudo = estudo
        self.saida: list[Paragrafo] = []
        self.pedacos: list[str] = []
        self.tipo = LANCE
        self.nivel = 0
        self.diagramas = 0

    # ------------------------------------------------------------------ parágrafos prontos

    def titulo(self) -> None:
        self.saida.append(Paragrafo(TITULO, titulo_do_estudo(self.estudo)))

    def diagrama(self, fen: str) -> None:
        self.fechar()
        self.diagramas += 1
        self.saida.append(Paragrafo(DIAGRAMA, fen=fen, virado=self.estudo.invertido, numero=self.diagramas))

    def comentario(self, texto: str) -> None:
        self.fechar()
        self.saida.append(Paragrafo(COMENTARIO_DO_ESTUDO, texto.strip()))

    # ------------------------------------------------------------------ texto corrido

    def lance(self, texto: str, nivel: int) -> None:
        tipo = LANCE if nivel == 0 else VARIANTE
        if self.pedacos and (tipo != self.tipo or (tipo == VARIANTE and nivel != self.nivel)):
            self.fechar()
        self.tipo, self.nivel = tipo, nivel
        self.pedacos.append(texto)

    def fechar(self) -> None:
        texto = " ".join("".join(self.pedacos).split())
        self.pedacos = []
        if texto:
            self.saida.append(Paragrafo(self.tipo, texto, nivel=self.nivel))
        self.tipo, self.nivel = LANCE, 0

    # ------------------------------------------------------------------ a travessia

    def trecho(self, trecho: Trecho) -> None:
        if trecho.papel == ABRE:
            if trecho.nivel == 1:
                self.fechar()
                self.tipo, self.nivel = VARIANTE, 1
            else:
                self.lance(trecho.texto, 1)
            return
        if trecho.papel == FECHA:
            if trecho.nivel == 1:
                self.fechar()
            else:
                self.lance(trecho.texto, 1)
            return
        if trecho.papel == COMENTARIO:
            self._comentario(trecho)
            return
        self.lance(trecho.texto, min(trecho.nivel, 1))

    def _comentario(self, trecho: Trecho) -> None:
        pede_diagrama = MARCA_DE_DIAGRAMA in trecho.token
        if trecho.nivel == 0:
            if trecho.texto.strip():
                self.comentario(trecho.texto)
        elif trecho.texto.strip():
            self.lance(trecho.texto, 1)
        if pede_diagrama and trecho.caminho is not None:
            no = no_em(self.estudo.jogo, trecho.caminho)
            if no is not None:
                nivel = self.nivel
                self.diagrama(no.board().fen())
                # A variante continua no mesmo recuo depois do diagrama que ela pediu.
                if trecho.nivel > 0:
                    self.tipo, self.nivel = VARIANTE, max(nivel, 1)
