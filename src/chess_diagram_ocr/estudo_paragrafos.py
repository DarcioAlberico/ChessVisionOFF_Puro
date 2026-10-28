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

## A tipografia é do livro, e não a do widget

`estudo_lista.trechos` é tokenizador de **lista clicável**: cada trecho termina em espaço para que
dois itens vizinhos não se encostem na tela, e é por isso que uma linha crua sai `1. Kf2 !` e
`( 1... Kf5 ?! )`. Nenhum livro imprime assim -- imprime `1.Kf2!` e `(1...Kf5?!)`. **A cola é
decidida aqui**, pelo papel do trecho, e não no exportador: se cada formato colasse por conta
própria, o EPUB e o DOCX imprimiriam a mesma partida de dois jeitos.

| papel | regra |
|---|---|
| `NUMERO` (`1.`, `1...`) | o próximo cola nele -- `1.Kf2`, `1...Kf5` |
| `NAG` (`!`, `?!`, `⩲`) | cola no anterior -- `Kf2!`, `Kd4⩲` |
| `ABRE` (`(`) | o próximo cola nele -- `(1...Kf5` |
| `FECHA` (`)`) | cola no anterior -- `2.Kd4⩲)` |
| lance, comentário, resultado | espaço simples, como qualquer palavra |
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from chess_diagram_ocr.estudo import Estudo, no_em, texto_do_comentario
from chess_diagram_ocr.ui.estudo_lista import (
    ABRE,
    COMENTARIO,
    FECHA,
    NAG,
    NUMERO,
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

MARCA_DE_DIAGRAMA = "[%D]"
"""O comando que pede um diagrama, **inteiro**. É o `[%D]` do ChessBase; `trechos` guarda o
comentário inteiro em `Trecho.token`, então basta procurar ali.

**Inteiro e não por prefixo**: `"[%D"` casava também `{[%Depth 20]}`, que é o campo de profundidade
que o Fritz e o ChessBase gravam ao anotar com motor -- e um livro anotado por máquina ganhava um
diagrama em cada lance analisado. Quem escreve `[%D]` está pedindo um diagrama; quem escreve
`[%Depth 20]` está dizendo a que profundidade o motor viu a posição."""

_COLA_NO_ANTERIOR = frozenset({NAG, FECHA})
"""Papéis que se encostam no que veio antes: `Kf2!`, `2.Kd4⩲)`. Ver o cabeçalho."""

_COLA_O_PROXIMO = frozenset({NUMERO, ABRE})
"""Papéis em que o próximo se encosta: `1.Kf2`, `(1...Kf5`. Ver o cabeçalho."""

_SEM_VALOR = frozenset({"", "?", "??", "-", "*", "????.??.??"})
"""O que o PGN escreve para "não sei": não vira título."""


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
    """O nome do capítulo: o endereço no livro, o cabeçalho da partida, ou "Estudo avulso".

    **A âncora não é o único endereço que um estudo tem.** Ela vale para o que veio do OCR -- é o
    `Secrets.pdf · p. 143 · diagrama 2` que diz onde a posição está impressa. Um PGN colado, um
    arquivo de estudos, o que veio de uma base: nada disso tem âncora, e o sumário saía com
    trezentas entradas escritas `Estudo avulso` -- um índice que não indexa nada. O que essas
    partidas têm é cabeçalho, e é o que o catálogo de qualquer base mostra:
    `Carlsen, M. × Nepomniachtchi, I., Tata Steel, 2021.01.16`.

    `estudo_saida.para_documento` chama esta mesma função, porque dois títulos para o mesmo estudo
    seria o EPUB discordando do `.md`.
    """
    if estudo.ancora.valida:
        return estudo.ancora.rotulo()
    return _endereco_da_partida(estudo) or "Estudo avulso"


def _endereco_da_partida(estudo: Estudo) -> str:
    """`Brancas × Pretas, Evento, Data` com o que o cabeçalho tiver -- e `""` quando não tem nada.

    **Sem jogador não há partida**, e sem partida o título é "Estudo avulso". A regra não é
    formalidade: `Estudo.de_posicao` grava `Event = "ChessVisionOFF Estudo"` em toda posição criada
    aqui dentro, e um livro intitulado com o nome do próprio programa é o mesmo erro que o
    `dc:creator` da primeira rodada. Num estudo de composição só há o compositor (`White`), e é ele
    quem nomeia o capítulo -- "Sifers, Samouc. sahm. igri".
    """
    cabecalho = estudo.jogo.headers
    brancas, pretas = _campo(cabecalho, "White"), _campo(cabecalho, "Black")
    if not brancas and not pretas:
        return ""
    partes = [" × ".join(nome for nome in (brancas, pretas) if nome)]
    partes.extend(campo for campo in (_campo(cabecalho, "Event"), _data(cabecalho)) if campo)
    return ", ".join(parte for parte in partes if parte)


def _campo(cabecalho: Mapping[str, str], nome: str) -> str:
    valor = " ".join(str(cabecalho.get(nome, "") or "").split())
    return "" if valor in _SEM_VALOR else valor


def _data(cabecalho: Mapping[str, str]) -> str:
    """`2021.01.16` inteira; `2021.??.??` vira `2021`; `????.??.??` não vira nada."""
    partes: list[str] = []
    for pedaco in _campo(cabecalho, "Date").split("."):
        if not pedaco.isdigit():
            break
        partes.append(pedaco)
    return ".".join(partes)


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
        self.colar_o_proximo = False
        """O trecho anterior era um número de lance ou um `(`: o que vier encosta nele."""

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

    def lance(self, texto: str, nivel: int, *, papel: str = "") -> None:
        """Mais um pedaço da linha corrente. `papel` é o do trecho, e é ele que decide a cola."""
        texto = " ".join(str(texto).split())
        if not texto:
            return
        cola = self.colar_o_proximo or papel in _COLA_NO_ANTERIOR
        self.colar_o_proximo = papel in _COLA_O_PROXIMO
        tipo = LANCE if nivel == 0 else VARIANTE
        if self.pedacos and (tipo != self.tipo or (tipo == VARIANTE and nivel != self.nivel)):
            self.fechar()
        self.tipo, self.nivel = tipo, nivel
        if self.pedacos and not cola:
            self.pedacos.append(" ")
        self.pedacos.append(texto)

    def fechar(self) -> None:
        texto = "".join(self.pedacos).strip()
        self.pedacos = []
        self.colar_o_proximo = False
        if texto:
            self.saida.append(Paragrafo(self.tipo, texto, nivel=self.nivel))
        self.tipo, self.nivel = LANCE, 0

    # ------------------------------------------------------------------ a travessia

    def trecho(self, trecho: Trecho) -> None:
        if trecho.papel in (ABRE, FECHA):
            if trecho.nivel == 1:
                # O parêntese do primeiro nível não é impresso: o recuo já diz que é variante.
                self.fechar()
                if trecho.papel == ABRE:
                    self.tipo, self.nivel = VARIANTE, 1
            else:
                self.lance(trecho.texto, 1, papel=trecho.papel)
            return
        if trecho.papel == COMENTARIO:
            self._comentario(trecho)
            return
        self.lance(trecho.texto, min(trecho.nivel, 1), papel=trecho.papel)

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
