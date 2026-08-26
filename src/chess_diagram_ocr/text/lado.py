"""O lado a jogar lido pelo classificador deste projeto, e não por motor de fora (S-207).

**O problema é de cobertura.** O lado a jogar tem dez fontes declaradas em `semantics.SideSource`,
e para os livros sem camada de texto a que sobra é `default` -- o palpite. A S-42 abriu o caminho
do OCR para eles, com RapidOCR, opt-in e desligado por padrão. Este item põe o classificador de
314 classes treinado neste acervo no mesmo lugar.

## O item é barato porque a costura já existe

`ocr.build_recognizer` já constrói o `glifo` (S-181), `CaptionReader` já lê a faixa em volta do
diagrama com o motor que lhe derem (S-43), e `pdf_text` já transforma a linha lida em declaração
de lado. O que faltava eram **duas coisas**, e as duas são de honestidade e não de mecanismo:

1. a linha lida pelo classificador saía marcada `origin="ocr"` -- indistinguível do RapidOCR.
   `[SideToMoveSource "ocr"]` significava dois motores de qualidades diferentes;
2. não havia medição por livro. Sem ela, "o glifo lê o lado" é opinião.

A primeira virou `LineOrigin`/`SideOrigin` com os valores `glifo` e `glifo-page-scope`; a segunda
é `cvoff-texto-lado` e o `docs/metrics/texto_lado.json`.

## As duas regras da S-43 valem aqui, e a segunda tem um número por trás

O PGN sai com `[SideToMoveSource "glifo"]`, **nunca disfarçado de camada de texto**, e com
`[SideToMoveConfidence]` ao lado. A confiança não é inventada: o classificador devolve uma por
caractere, e `GlyphRecognizer` já entrega a legenda com a **mínima** delas -- que é o número certo
para uma frase de três palavras em que um caractere errado inverte o sentido (`White`/`Black`).

## A contradição é informação, e não erro a esconder

Quando o texto diz "pretas jogam" e a legalidade da S-17 diz que quem não joga estaria em xeque,
`semantics.infer_side_to_move` já faz a coisa certa: a legalidade vence, e o par sai com
`SideToMove.conflicting=True` -- que a fila da S-22 pontua com `WEIGHT_SOURCES_DISAGREE`. **Não há
prioridade fixa que resolva isso**: nos dois casos há algo para um humano olhar, porque ou o
reconhecimento leu uma peça errada, ou a legenda foi associada ao diagrama vizinho.

Este módulo **não** decide contradição: ele a conta. `contradicoes` é a coluna da tabela por livro,
e `test_a_contradicao_vai_para_a_fila_e_nao_e_resolvida_calada` prova que ela chega à fila com
motivo escrito em vez de sumir num `if`.

## Por que uma função aqui, e não só o `--ocr-engine glifo` que já existia

`lado_por_glifo` é o ponto em que a leitura de uma faixa vira uma resposta de lado a jogar **com a
procedência certa carimbada**, sem passar pela varredura inteira. É o que a medição por livro
chama, e é o que qualquer chamador que já tenha o recorte da legenda na mão pode chamar sem abrir
o PDF de novo.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

FONTE = "glifo"
"""O valor de `semantics.SideSource` que este módulo produz. Ver `ocr.MOTOR_DE_CASA`."""

FONTE_DE_PAGINA = "glifo-page-scope"
"""O mesmo, para a declaração que vale para a página inteira. Ver `pdf_text.SideOrigin`."""


@dataclass(frozen=True)
class LadoLido:
    """O que o classificador achou numa faixa de legenda, com a procedência já carimbada."""

    cor: Any
    """`chess.WHITE` ou `chess.BLACK`. `Any` para este módulo não importar `chess` no topo --
    ele é lido por `text_status` com `ast`, e a fronteira do subpacote `text/` é fina de propósito."""

    evidencia: str
    """O trecho que decidiu. Existe para o usuário poder discordar (S-43)."""

    confianca: float
    fonte: str = FONTE

    @property
    def duvidoso(self) -> bool:
        """A leitura veio abaixo do piso de aceite do OCR. Ver `ocr.MIN_CONFIDENCE`."""
        from ..ocr import MIN_CONFIDENCE

        return self.confianca < float(MIN_CONFIDENCE)


def lado_por_glifo(
    texto: str,
    *,
    confianca: float = 1.0,
    escopo_de_pagina: bool = False,
) -> LadoLido | None:
    """A declaração de lado a jogar nesta linha lida pelo glifo, ou `None`.

    **A régua é a mesma da camada de texto, e isso é a decisão do item.** Quem reconhece o padrão
    é `pdf_text._side_from_line` -- as mesmas expressões, nos mesmos idiomas, com a mesma exigência
    de formato de legenda. Um segundo reconhecedor de "White to move" aqui divergiria do primeiro
    na primeira frase que só um dos dois cobrisse, e o acervo tem oito idiomas para produzi-la.

    O que muda em relação à camada não é o que se procura: é **em que texto** se procura, e com
    que confiança a resposta viaja.

    `caption_like=True` porque uma faixa de legenda é, por construção, uma legenda: ela foi
    recortada em volta do diagrama. A exigência de abertura de linha existe para prosa, e prosa é
    o que não chega aqui.
    """
    from ..pdf_text import _side_from_line

    achado = _side_from_line(texto, caption_like=True)
    if achado is None:
        return None
    cor, evidencia = achado
    return LadoLido(
        cor=cor,
        evidencia=evidencia,
        confianca=float(confianca),
        fonte=FONTE_DE_PAGINA if escopo_de_pagina else FONTE,
    )


def lado_de_linhas(linhas: Sequence[Any], *, escopo_de_pagina: bool = False) -> LadoLido | None:
    """A primeira declaração entre as linhas lidas, ou `None`. **Contradição devolve `None`.**

    Duas linhas da mesma faixa dizendo lados opostos não é uma para escolher: é a faixa dizendo as
    duas coisas, e devolver a primeira seria decidir por ordem de leitura. É a mesma regra de
    `pdf_text.page_scope_declaration`, e ela existe porque a alternativa -- desempatar por
    confiança -- daria uma resposta com aparência de fundamento onde não há nenhum.
    """
    achados = [
        lado
        for linha in linhas
        if (
            lado := lado_por_glifo(
                str(getattr(linha, "text", getattr(linha, "texto", ""))),
                confianca=float(getattr(linha, "confidence", getattr(linha, "confianca", 1.0))),
                escopo_de_pagina=escopo_de_pagina,
            )
        )
        is not None
    ]
    if not achados:
        return None
    if len({lado.cor for lado in achados}) > 1:
        logger.debug("a faixa declara os dois lados; sem resposta de glifo")
        return None
    return achados[0]


# --------------------------------------------------------------------------------------
# A medicao por livro, que e o que este item acrescenta a S-43
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PorLivro:
    """A linha da tabela de um livro: quantos diagramas cada resposta cobriu.

    As três colunas que o item pede -- lido, `default`, contradição -- mais o total, sem o qual
    nenhuma das três é interpretável.
    """

    livro: str
    diagramas: int = 0
    lidos: int = 0
    """Diagramas cujo lado veio do glifo (`glifo` ou `glifo-page-scope`)."""

    de_outra_fonte: int = 0
    """Vieram da camada de texto, da legalidade ou da base -- o glifo não era necessário."""

    assumidos: int = 0
    """Continuaram `default`: ninguém respondeu."""

    contradicoes: int = 0
    """A leitura e a legalidade da S-17 discordaram. **Vão para a fila, não para o lixo.**"""

    duvidosos: int = 0
    """Lidos abaixo do piso de confiança do OCR. Saem com `[SideToMoveConfidence]` no PGN."""

    @property
    def cobertura(self) -> float:
        """Fração dos diagramas do livro em que o glifo respondeu."""
        return 0.0 if not self.diagramas else self.lidos / self.diagramas

    @property
    def deixaram_de_ser_palpite(self) -> int:
        """A pergunta do item: quantos diagramas **deixam de sair `default`** por causa do glifo."""
        return self.lidos

    def para_json(self) -> dict[str, Any]:
        return {
            "livro": self.livro,
            "diagramas": self.diagramas,
            "lidos": self.lidos,
            "de_outra_fonte": self.de_outra_fonte,
            "assumidos": self.assumidos,
            "contradicoes": self.contradicoes,
            "duvidosos": self.duvidosos,
            "cobertura": round(self.cobertura, 4),
        }


def contabilizar(
    livro: str,
    lados: Sequence[Any],
    confiancas: Sequence[float] = (),
) -> PorLivro:
    """Uma linha da tabela a partir dos `semantics.SideToMove` de um livro.

    Recebe as decisões prontas, e não os PDFs: quem varre é o comando, e uma função que abrisse
    arquivo não poderia ser testada sem um. As contagens saem de dois campos que já existem --
    `source` e `conflicting` --, e é por isso que este item é barato.

    `confiancas` vem em paralelo porque **a confiança não mora no `SideToMove`**: ela é do
    `DiagramContext` que originou a decisão (`side_to_move_confidence`), e é de lá que o
    `[SideToMoveConfidence]` do PGN sai. Ausente, nenhum lido conta como duvidoso -- que é o
    estado certo para "não se mediu", e não para "todos confiantes".
    """
    lidos = de_outra = assumidos = contradicoes = duvidosos = 0
    for posicao, lado in enumerate(lados):
        fonte = str(getattr(lado, "source", ""))
        if getattr(lado, "conflicting", False):
            contradicoes += 1
        if fonte in (FONTE, FONTE_DE_PAGINA):
            lidos += 1
            if posicao < len(confiancas) and _abaixo_do_piso(confiancas[posicao]):
                duvidosos += 1
        elif fonte == "default":
            assumidos += 1
        else:
            de_outra += 1
    return PorLivro(
        livro=livro,
        diagramas=len(lados),
        lidos=lidos,
        de_outra_fonte=de_outra,
        assumidos=assumidos,
        contradicoes=contradicoes,
        duvidosos=duvidosos,
    )


def _abaixo_do_piso(confianca: float) -> bool:
    """O mesmo piso que a S-42 usa para aceitar uma leitura de OCR. Um corte, num lugar só."""
    from ..ocr import MIN_CONFIDENCE

    return float(confianca) < float(MIN_CONFIDENCE)


def total(linhas: Sequence[PorLivro]) -> PorLivro:
    """A linha de fechamento da tabela. `livro` vira `"todos"`.

    Existe porque a soma das colunas é a resposta à pergunta do item -- *quantos diagramas dos
    livros sem camada deixam de sair `default`* -- e refazê-la em cada chamador daria duas contas
    para o mesmo número."""
    return PorLivro(
        livro="todos",
        diagramas=sum(uma.diagramas for uma in linhas),
        lidos=sum(uma.lidos for uma in linhas),
        de_outra_fonte=sum(uma.de_outra_fonte for uma in linhas),
        assumidos=sum(uma.assumidos for uma in linhas),
        contradicoes=sum(uma.contradicoes for uma in linhas),
        duvidosos=sum(uma.duvidosos for uma in linhas),
    )


def tabela(linhas: Sequence[PorLivro]) -> list[str]:
    """A tabela por livro, para a tela. A última linha é o total."""
    saida = ["livro                                  diag   lidos  outra  default  contra  dúvida"]
    for linha in [*linhas, total(linhas)]:
        saida.append(
            f"  {linha.livro[:36]:<36s} {linha.diagramas:5d}  {linha.lidos:6d} "
            f"{linha.de_outra_fonte:6d}  {linha.assumidos:7d} {linha.contradicoes:7d} {linha.duvidosos:7d}"
        )
    return saida
