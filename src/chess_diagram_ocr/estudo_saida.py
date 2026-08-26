"""O estudo virado documento, para sair do programa e para voltar à aba de texto (S-289).

**Por que um documento, e não um exportador novo.** A Fase 39 já decidiu, por formato, o que
acontece com negrito, itálico, título, cor e diagrama -- e o fez num lugar só justamente porque
"quatro exportadores escritos separadamente dariam quatro respostas, e três estariam erradas em
silêncio" (`text/exportacao.py`). Escrever um `.md` de estudo à mão seria o quinto exportador, e ele
estaria errado em três das quatro perguntas no dia seguinte.

O que faltava não era um exportador: era a **conversão**. `DocumentoRico` é a moeda -- o editor
produz uma, e a partir daqui o estudo também.

## A conversão usa os estilos que a S-249 já nomeou, e não inventa nenhum

| o que o estudo tem | vira |
|---|---|
| o endereço no livro (`Secrets.pdf · p. 143 · diagrama 2`) | `ESTILO_TITULO` |
| a posição do diagrama | uma corrida de **diagrama**, que os formatos já sabem desenhar |
| a linha de lances, com variantes e símbolos | `ESTILO_NOTACAO` |
| o comentário de um lance | `ESTILO_PROSA` |

`notacao` é o único estilo da S-249 **sem derivação automática** -- lá a régua que separa uma linha
de lances de uma linha de prosa não foi medida, e a regra 5 da SPEC_EDITOR manda entregar o pincel
manual em vez de pintar palpite. Aqui não há palpite: o que sai de `estudo_lista` **é** notação, por
construção. É a mesma etiqueta ganha por um caminho que não precisa de medição.

## O que **não** vai junto

A seta e a casa marcada. Elas moram em `[%cal]`/`[%csl]` dentro do comentário, e nenhum dos quatro
formatos tem como desenhá-las -- desenhá-las exigiria compor uma imagem do tabuleiro com as setas
por cima, que é um renderizador e não um exportador. `texto_do_comentario` as tira do texto, então
elas não vazam como encanamento; ficam no PGN, que é onde o ChessBase e o Lichess as leem.

Nada de `tkinter` aqui, e nada de arquivo: quem escolhe o destino é o painel.
"""

from __future__ import annotations

from chess_diagram_ocr.estudo import Estudo, texto_do_comentario
from chess_diagram_ocr.text import rico

# **O submódulo direto, e não o pacote.** `estudo_lista` mora em `ui/` por vizinhança de assunto e
# não por dependência -- ele não importa `tkinter`, e está na lista de `SEM_TKINTER`. Importá-lo pelo
# caminho dele deixa isso dito: o que este módulo usa é a travessia da árvore, e não a interface.
from chess_diagram_ocr.ui.estudo_lista import RAIZ, RESULTADO, trechos

__all__ = ["BLOCO_DO_DIAGRAMA", "notacao_do_estudo", "para_documento"]

BLOCO_DO_DIAGRAMA = 0
"""O `bloco` da corrida de diagrama, e a chave em `exportacao.exportar(recortes=...)`.

Zero e não `rico.SEM_BLOCO`: `SEM_BLOCO` significa "escrito à mão", e a posição do diagrama **veio
da página**. O número é o índice do único diagrama que um estudo tem -- ele é de um diagrama só, por
construção da `Ancora`."""


def _corrida(texto: str, estilo: str) -> rico.Corrida:
    return rico.Corrida(texto=texto, atributos=rico.Atributos(estilo=estilo))


def notacao_do_estudo(estudo: Estudo) -> str:
    """A linha do estudo em notação, numa linha só -- com variantes, símbolos e comentários.

    É o que vai para a aba de texto (o inverso da S-283) e o corpo do documento exportado. Sai de
    `estudo_lista`, e não de um `StringExporter` novo, porque a numeração de variante é a parte que
    todo visualizador de PGN erra e aquele módulo é conferido contra o exportador do `chess.pgn`.

    **É o `texto` do trecho, e não o `pgn`**, e a diferença é o leitor. `Trecho.pgn` escreve `$5` e
    `{ a italiana }` porque é o que um arquivo PGN precisa; aqui o destino é um parágrafo que alguém
    vai ler, e o livro imprime `4...Bc5!? a italiana`. Quem quiser a forma de arquivo já tem uma:
    `Estudo.para_pgn`.
    """
    corpo = "".join(
        trecho.texto for trecho in trechos(estudo) if trecho.papel not in (RAIZ, RESULTADO)
    )
    return " ".join(corpo.split())


def para_documento(estudo: Estudo) -> rico.DocumentoRico:
    """O estudo como `DocumentoRico`, pronto para `text/exportacao.exportar`.

    **A ordem é a de quem lê**: o endereço, a posição, a linha. É a mesma ordem em que o livro
    imprime -- o diagrama e, embaixo dele, a análise.
    """
    corridas: list[rico.Corrida] = []

    titulo = estudo.ancora.rotulo() if estudo.ancora.valida else "Estudo avulso"
    corridas.append(_corrida(f"{titulo}\n\n", rico.ESTILO_TITULO))

    # A marca do diagrama, e ela **nunca desaparece** -- é a regra que a S-250 escreveu para os
    # quatro formatos: "um diagrama desenhado sem marca correspondente seria invisível para o texto".
    corridas.append(
        rico.Corrida(
            texto="[Diagrama 1]",
            tipo=rico.DIAGRAMA,
            bloco=BLOCO_DO_DIAGRAMA,
            atributos=rico.Atributos(alinhamento=rico.ALINHAMENTO_CENTRO),
        )
    )
    corridas.append(_corrida("\n\n", rico.ESTILO_PROSA))
    corridas.append(_corrida(f"FEN: {estudo.raiz.board().fen()}\n\n", rico.ESTILO_PROSA))

    raiz = texto_do_comentario(estudo.raiz.comment or "")
    if raiz:
        corridas.append(_corrida(f"{raiz}\n\n", rico.ESTILO_PROSA))

    linha = notacao_do_estudo(estudo)
    if linha:
        corridas.append(_corrida(f"{linha}\n", rico.ESTILO_NOTACAO))

    return rico.DocumentoRico(corridas=tuple(corridas)).normalizado()
