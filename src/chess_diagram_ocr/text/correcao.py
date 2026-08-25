"""A correção humana: o que a pessoa mudou, e sobre que leitura (S-239).

**`Procedencia` tem `"humano"` desde a S-201, e nada no programa o escrevia.** Uma palavra corrigida
à mão saía da aba como texto, no meio de um `.txt`, sem nada dizendo que houve intervenção -- e há
dois destinos planejados esperando exatamente essa informação: a **S-212** (fila de revisão de
caractere) e a **S-213** (aplicar a todos os semelhantes). As duas precisam de *"o que uma pessoa
corrigiu, e sobre que glifo"*. O editor é o único lugar do programa onde isso acontece.

## A correção não é guardada: ela é **derivada**, e isso é o item

O desenho da spec previa gravar cada par `antes`/`depois` dentro do `.cvtxt`. A implementação não
faz isso, e o motivo é que não precisa: o arquivo já guarda **os dois lados**.

    origem.blocos[N].texto     o que o motor leu     -- a `PaginaLida`, intocada
    as corridas com bloco N    o que está na tela    -- depois da edição

A correção é a diferença entre os dois, e recalculá-la é barato. Gravá-la seria uma **segunda fonte
para a mesma pergunta**, e a primeira vez que alguém editasse o arquivo por fora as duas
discordariam -- sem nada para dizer qual estava certa. É a mesma razão pela qual a S-238 tirou
`documento` e `folha` do formato: derivado não se duplica.

## O par é mínimo, e não o bloco inteiro

`difflib` sobre o texto do bloco devolve só os trechos que mudaram: `Black,s` -> `Black's` vira
`(",", "'")`, e não o parágrafo de 400 caracteres em volta. É o que torna o relatório utilizável --
a S-213 quer saber quantas vezes a vírgula virou apóstrofo, não quantos parágrafos foram tocados.

## Duas regras, e as duas são a cicatriz das duas pontas

**A correção é registro, e não rótulo.** Este módulo não escreve em `training_data/` e não cria
amostra. Ele descreve o que mudou e oferece um relatório; quem decide se aquilo vira rótulo é a
S-212, que tem a fila e o critério. Um editor que alimentasse a base direto seria um caminho de
rótulo sem revisão -- exatamente o defeito de que a base já tem cicatriz (S-180, 127 amostras
rotuladas na classe errada).

**Corrida escrita do zero não é correção.** `bloco == SEM_BLOCO` é texto que a pessoa acrescentou,
e não texto que o motor errou. Contá-lo inflaria qualquer estatística de erro do OCR com o que
alguém digitou por conta própria. Ela é marcada como `humano` -- porque a mão a escreveu -- e fica
**fora** de `correcoes`.

## O diagrama fica de fora, e é decisão

`[Diagrama N]` é referência, não leitura: apagá-la ou movê-la é editar a estrutura do texto, não
corrigir o que o motor leu. Deixá-la entrar encheria o relatório de pares
`("[Diagrama 3]", "")` que nenhuma classe de caractere pode consumir.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Any

from .pagina import BlocoDeDiagrama, Procedencia
from .rico import SEM_BLOCO, TEXTO, Corrida, DocumentoRico

__all__ = [
    "Correcao",
    "blocos_editados",
    "com_procedencia_humana",
    "correcoes",
    "resumo",
    "texto_por_bloco",
]


@dataclass(frozen=True)
class Correcao:
    """Um trecho que o motor leu de um jeito e a pessoa escreveu de outro."""

    bloco: int
    """Índice em `PaginaLida.blocos` -- é por ele que se volta à bbox e ao recorte."""

    antes: str
    """O que o motor leu. Vazio quando a pessoa **acrescentou** algo que não estava lá."""

    depois: str
    """O que a pessoa escreveu. Vazio quando ela **apagou** o que o motor tinha lido."""

    motor: Procedencia
    """Quem tinha lido o bloco: `camada`, `glifo` ou `rapidocr`.

    Vem da `PaginaLida`, que não muda com a edição -- é ela que continua sabendo quem errou."""

    @property
    def e_troca(self) -> bool:
        """Trocou uma coisa por outra -- o caso que a S-213 sabe aplicar aos semelhantes."""
        return bool(self.antes) and bool(self.depois)

    def para_json(self) -> dict[str, Any]:
        return {"bloco": self.bloco, "antes": self.antes, "depois": self.depois, "motor": self.motor}


def texto_por_bloco(doc: DocumentoRico) -> dict[int, str]:
    """O que está na tela **hoje**, agrupado pelo bloco de onde saiu.

    Uma edição parte a corrida original em várias -- digitar no meio de um parágrafo dá três, e as
    três continuam com o mesmo `bloco`. Juntá-las de novo é o que permite comparar com o texto que o
    motor leu, que é um só.
    """
    junto: dict[int, list[str]] = {}
    for corrida in doc.corridas:
        if corrida.bloco == SEM_BLOCO:
            continue
        junto.setdefault(corrida.bloco, []).append(corrida.texto)
    return {indice: "".join(pedacos) for indice, pedacos in junto.items()}


def _blocos_comparaveis(doc: DocumentoRico) -> dict[int, tuple[str, Procedencia]]:
    """Por bloco: o que o motor leu, e quem leu. Só os que podem ser corrigidos.

    Fora ficam os diagramas -- ver o cabeçalho -- e os índices que a página não tem, que só
    aparecem num arquivo mexido por fora.
    """
    if doc.origem is None:
        return {}
    blocos = doc.origem.blocos
    saida: dict[int, tuple[str, Procedencia]] = {}
    for indice in texto_por_bloco(doc):
        if not 0 <= indice < len(blocos):
            continue
        bloco = blocos[indice]
        if isinstance(bloco, BlocoDeDiagrama):
            continue
        saida[indice] = (bloco.texto, bloco.procedencia)
    return saida


def correcoes(doc: DocumentoRico) -> tuple[Correcao, ...]:
    """Os pares `antes`/`depois` mínimos entre o que o motor leu e o que está na tela.

    Devolve vazio para um documento sem origem: sem `PaginaLida` não há leitura contra a qual
    comparar, e todo o texto é da mão de quem escreveu -- que não é correção de coisa nenhuma.
    """
    atual = texto_por_bloco(doc)
    achadas: list[Correcao] = []
    for indice, (antes, motor) in sorted(_blocos_comparaveis(doc).items()):
        depois = atual[indice]
        if antes == depois:
            continue
        achadas.extend(_pares(indice, antes, depois, motor))
    return tuple(achadas)


def _pares(bloco: int, antes: str, depois: str, motor: Procedencia) -> Iterable[Correcao]:
    """O diff caractere a caractere, sem os trechos que ficaram iguais.

    `SequenceMatcher` sobre `str` compara caracteres, que é a granularidade que a S-212 consome --
    comparar palavras devolveria `("Black,s", "Black's")` e deixaria o trabalho de achar a vírgula
    para quem lê o relatório.
    """
    for operacao, i1, i2, j1, j2 in SequenceMatcher(None, antes, depois, autojunk=False).get_opcodes():
        if operacao == "equal":
            continue
        yield Correcao(bloco=bloco, antes=antes[i1:i2], depois=depois[j1:j2], motor=motor)


def blocos_editados(doc: DocumentoRico) -> frozenset[int]:
    """Os blocos cujo texto na tela já não é o que o motor leu."""
    atual = texto_por_bloco(doc)
    return frozenset(
        indice
        for indice, (antes, _motor) in _blocos_comparaveis(doc).items()
        if atual[indice] != antes
    )


def com_procedencia_humana(doc: DocumentoRico) -> DocumentoRico:
    """O mesmo documento, com `procedencia="humano"` onde a mão passou.

    São dois casos, e os dois são a mesma frase -- *a mão escreveu isto*:

    - corrida de um bloco **editado**: o motor leu, alguém corrigiu, e continuar dizendo `glifo`
      faria a `faixa_de_confianca` pintar de vermelho o que uma pessoa acabou de conferir;
    - corrida **sem bloco** e de texto: acrescentada do zero, sem leitura nenhuma por trás.

    O separador fica de fora dos dois: ele é estrutura que o leitor produziu, e ninguém o escreveu.

    **É idempotente**, e precisa ser: `documento_atual` a aplica a cada gravação, e a comparação que
    a decide é contra a `PaginaLida`, que a marcação não toca.
    """
    editados = blocos_editados(doc)
    if not editados and all(c.procedencia is not None or c.bloco != SEM_BLOCO for c in doc.corridas):
        return doc
    novas = tuple(_marcada(corrida, editados) for corrida in doc.corridas)
    return DocumentoRico(corridas=novas, origem=doc.origem)


def _marcada(corrida: Corrida, editados: frozenset[int]) -> Corrida:
    if corrida.bloco in editados:
        return replace(corrida, procedencia="humano")
    if corrida.bloco == SEM_BLOCO and corrida.tipo == TEXTO:
        return replace(corrida, procedencia="humano")
    return corrida


def resumo(achadas: Sequence[Correcao]) -> dict[str, Any]:
    """O relatório: quantas correções, sobre que motor, e quais trocas mais se repetem.

    A lista de pares é o produto deste módulo para a **S-213**: uma vírgula que virou apóstrofo oito
    vezes na mesma página é a evidência de que o caso vale ser aplicado aos semelhantes, e é
    exatamente o que o número ao lado do par diz.

    Ordenada por frequência e depois pelo par, e não só por frequência: sem o desempate, duas trocas
    de mesma contagem trocam de lugar entre execuções e o relatório deixa de ser comparável com o
    anterior por `diff`.
    """
    por_motor = Counter(c.motor for c in achadas)
    trocas = Counter((c.antes, c.depois) for c in achadas)
    return {
        "total": len(achadas),
        "blocos": len({c.bloco for c in achadas}),
        "por_motor": dict(sorted(por_motor.items())),
        "trocas": [
            {"antes": antes, "depois": depois, "vezes": vezes}
            for (antes, depois), vezes in sorted(trocas.items(), key=lambda item: (-item[1], item[0]))
        ],
    }
