"""Achar e substituir no documento -- e o que a substituição em massa sabe sobre OCR (S-245).

**Por que uma busca própria, e não a do `tk.Text`.** Numa aba cujo conteúdo é OCR, o erro **se
repete**: a S-211 mediu 241 substituições de caixa alta e 96 caracteres espúrios em 13 páginas, e a
S-186 mediu o `l` itálico virando `/` em **16 de 16** ocorrências do mesmo trecho. Quem corrige à
mão faz a mesma correção dezenas de vezes na mesma página e não tem como saber se pegou todas.

Este módulo faz três coisas que uma busca de widget não faria:

**1 · Ela conhece as classes do modelo.** Procurar `♘` acha `♘`; procurar `N` **oferece** achar
também `♘`, porque `text/notacao.FIGURINAS_DA_LETRA` sabe que as duas são a mesma peça em
codificações diferentes -- e porque o acervo mistura as duas (S-211: 360 figurinas contra 212
notações ASCII em 16 páginas). É oferta e não tradução: o interruptor nasce **desligado**.

**2 · Ela responde com a janela fechada.** `achar` percorre o `DocumentoRico`, e não o widget. É o
que permite a lista de confirmação da substituição em massa ser afirmada num teste -- e a lista é o
item: `substituir todos` sobre uma página de OCR é a operação que apaga trabalho, e a S-76 é o
registro do que custa um botão destrutivo que não parece um (1.405 diagramas sobrescritos por um
clique).

**3 · Cada troca vira uma `Correcao` da S-239.** Não porque este módulo a grave -- ele não grava
nada --, mas porque a substituição escreve **dentro da corrida**, preservando o `bloco`. Com o
bloco preservado, `text/correcao.correcoes` vê a diferença entre o que o motor leu e o que ficou na
tela, e o par `(",", "'")` aparece no relatório com o número de vezes. Uma substituição que
descartasse o bloco entregaria texto novo sem origem, e a S-213 -- *aplicar a todos os
semelhantes* -- perderia justamente o caso que ela existe para tratar.

## O que fica de fora, e é recusa e não esquecimento

**Expressão regular.** O público desta aba corrige texto de livro, e `regex` numa caixa de
substituição é a ferramenta com a maior razão entre poder e estrago da lista. O que ela resolveria
aqui -- casar `N` com `♘` -- o interruptor de figurina já resolve, e com uma pergunta a menos.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from . import notacao
from .rico import SEM_BLOCO, DocumentoRico, substituir_intervalo

__all__ = [
    "LADO_DO_CONTEXTO",
    "Ocorrencia",
    "achar",
    "padrao_de",
    "substituir",
    "substituir_todas",
]

LADO_DO_CONTEXTO = 28
"""Quantos caracteres de cada lado a ocorrência carrega para a lista de confirmação.

Vinte e oito de cada lado é o que faz caber uma linha de lista sem rolagem horizontal e ainda
mostrar a palavra em volta -- que é o que decide se aquela ocorrência deve ser trocada."""


@dataclass(frozen=True)
class Ocorrencia:
    """Um trecho que casou com a busca, e o bastante para se decidir sobre ele sem abrir a página."""

    inicio: int
    """Deslocamento em caracteres no `para_texto()` do documento."""

    fim: int
    texto: str
    """O que casou, **como está no documento** -- que pode não ser o que se digitou na busca: com o
    casamento de figurina ligado, procurar `N` acha `♘`, e é o `♘` que aparece aqui."""

    contexto: str
    """O trecho em volta, para a lista da confirmação. Ver `LADO_DO_CONTEXTO`."""

    bloco: int = SEM_BLOCO
    """De que bloco da página o trecho saiu. `SEM_BLOCO` para texto escrito à mão."""


def padrao_de(agulha: str, *, casar_figurina: bool = False, diferenciar_caixa: bool = False) -> re.Pattern[str]:
    """A expressão que procura aquela agulha. **Todo caractere é escapado** -- ver o cabeçalho.

    Com `casar_figurina`, cada inicial inglesa de peça vira uma classe com ela e as duas figurinas
    daquela peça, e cada figurina vira uma classe com ela, a irmã de outra cor e a inicial. É a
    única liberdade que o padrão tem, e ela é declarada em `text/notacao.py`.
    """
    partes: list[str] = []
    for caractere in agulha:
        alternativas = _alternativas(caractere) if casar_figurina else caractere
        partes.append(f"[{re.escape(alternativas)}]" if len(alternativas) > 1 else re.escape(caractere))
    return re.compile("".join(partes), 0 if diferenciar_caixa else re.IGNORECASE)


def _alternativas(caractere: str) -> str:
    """O caractere mais o que ele pode casar quando a figurina conta. Ele mesmo, quando não há."""
    maiuscula = caractere.upper()
    if maiuscula in notacao.FIGURINAS_DA_LETRA:
        return caractere + notacao.FIGURINAS_DA_LETRA[maiuscula]
    letra = notacao.LETRA_DA_FIGURINA.get(caractere)
    if letra is not None:
        return caractere + letra + notacao.FIGURINAS_DA_LETRA[letra]
    return caractere


def achar(
    doc: DocumentoRico,
    agulha: str,
    *,
    casar_figurina: bool = False,
    diferenciar_caixa: bool = False,
) -> tuple[Ocorrencia, ...]:
    """As ocorrências no documento, na ordem em que aparecem e sem sobreposição.

    Agulha vazia devolve vazio: uma busca sem termo que casasse com toda posição do texto acenderia
    a lista inteira da substituição em massa, que é o gesto mais caro desta aba.
    """
    if not agulha:
        return ()
    texto = doc.para_texto()
    padrao = padrao_de(agulha, casar_figurina=casar_figurina, diferenciar_caixa=diferenciar_caixa)
    por_posicao = _bloco_por_posicao(doc)
    achadas: list[Ocorrencia] = []
    for casamento in padrao.finditer(texto):
        inicio, fim = casamento.span()
        if inicio == fim:
            continue
        achadas.append(
            Ocorrencia(
                inicio=inicio,
                fim=fim,
                texto=casamento.group(0),
                contexto=_contexto(texto, inicio, fim),
                bloco=por_posicao[inicio] if inicio < len(por_posicao) else SEM_BLOCO,
            )
        )
    return tuple(achadas)


def _contexto(texto: str, inicio: int, fim: int) -> str:
    """O trecho em volta, com reticências onde ele foi cortado, e sem quebra de linha.

    A quebra vira espaço porque o contexto mora numa linha de lista: um `\\n` ali desenharia uma
    linha vazia no meio da confirmação, e a confirmação é o que impede a troca em massa errada.
    """
    esquerda = max(0, inicio - LADO_DO_CONTEXTO)
    direita = min(len(texto), fim + LADO_DO_CONTEXTO)
    trecho = texto[esquerda:direita].replace("\n", " ").strip()
    return ("…" if esquerda > 0 else "") + trecho + ("…" if direita < len(texto) else "")


def _bloco_por_posicao(doc: DocumentoRico) -> list[int]:
    """Para cada caractere do documento, o bloco de onde ele veio. É o que dá `Ocorrencia.bloco`."""
    saida: list[int] = []
    for corrida in doc.corridas:
        saida.extend([corrida.bloco] * len(corrida.texto))
    return saida


def substituir(doc: DocumentoRico, ocorrencias: Sequence[Ocorrencia], novo: str) -> DocumentoRico:
    """Troca aquelas ocorrências pelo texto novo, **de trás para a frente**.

    De trás para a frente porque cada troca desloca o que vem depois: aplicá-las na ordem direta
    faria a segunda ocorrência ser escrita no lugar errado assim que a primeira mudasse de tamanho.
    É o mesmo motivo pelo qual `text/leitor.py` aplica correções de trás para a frente.

    O atributo do trecho sobrevive (`rico.substituir_intervalo`), e o bloco também -- que é o que
    faz a troca continuar sendo uma correção **sobre aquele bloco** para a S-239.

    Ocorrência que se sobrepõe a outra é ignorada, e não aplicada duas vezes: a lista vem de
    `achar`, que já não as produz, mas quem chama pode ter juntado duas buscas.
    """
    if not ocorrencias:
        return doc
    limite = len(doc.para_texto()) + 1
    resultado = doc
    for ocorrencia in sorted(ocorrencias, key=lambda o: o.inicio, reverse=True):
        if ocorrencia.fim > limite or ocorrencia.inicio >= ocorrencia.fim:
            continue
        resultado = substituir_intervalo(resultado, ocorrencia.inicio, ocorrencia.fim, novo)
        limite = ocorrencia.inicio
    return resultado


def substituir_todas(
    doc: DocumentoRico,
    agulha: str,
    novo: str,
    *,
    casar_figurina: bool = False,
    diferenciar_caixa: bool = False,
    fora: Iterable[int] = (),
) -> tuple[DocumentoRico, int]:
    """Acha e troca de uma vez, devolvendo o documento novo e **quantas trocas fez**.

    `fora` são os índices da lista de `achar` que a pessoa desmarcou na confirmação. Eles não são
    trocados, e a contagem devolvida é a das trocas de fato -- é ela que o rodapé diz, e é ela que o
    teste compara com o número de ocorrências para o caso de a lista e a troca divergirem.
    """
    achadas = achar(doc, agulha, casar_figurina=casar_figurina, diferenciar_caixa=diferenciar_caixa)
    excluidas = set(fora)
    escolhidas = [o for i, o in enumerate(achadas) if i not in excluidas]
    return substituir(doc, escolhidas, novo), len(escolhidas)
