"""A ordem em que a página se lê (S-193).

**O diagrama é um objeto da coluna, não um buraco nela.** Hoje o diagrama e o texto vivem em
mundos separados: `detection/hybrid.py` acha o tabuleiro, `pdf_text.py` acha a legenda, e
`assign_lines_to_diagrams` costura os dois **para a legenda**. Não há nada que diga *em que ponto
do fluxo de leitura* o diagrama entra. Para a FEN isso não importa; para exportar o livro,
importa: o diagrama entre o parágrafo 3 e o 4 tem de sair entre o 3 e o 4.

## O elemento que atravessa a calha não pode ser jogado numa coluna

Título, diagrama largo e faixa de cabeçalho cobrem as duas colunas, e forçá-los numa delas
embaralha a página. Eles servem de **separador horizontal**: o que está acima é lido coluna a
coluna, depois vem o elemento, depois o que está abaixo. É a regra do projeto de origem, e ela
resolve os dois casos com a mesma linha de raciocínio.

## A região vem antes da coluna (S-507)

O parágrafo acima resolve o elemento transversal **dentro** de uma grade de colunas que já existe.
Falta o caso em que ele impede a grade de existir: um bloco de largura inteira de quatro linhas
cobre a calha em todas elas, e `colunas.detectar_colunas` devolve *uma* coluna para a folha
inteira -- as duas colunas de baixo saem intercaladas linha a linha.

Por isso a folha é primeiro partida em **regiões** horizontais, cada uma com as colunas que valem
dentro dela, e a ordem é região a região. Ver `text/regioes.py`, que traz a medição. Dentro de
cada região vale tudo o que está escrito acima, sem mudança.

## Exclusão e reinserção usam o mesmo retângulo

O diagrama sai da segmentação em `boxes.excluir_diagramas` e volta aqui na sequência de leitura.
Os dois usam o `bbox` que a S-12 já carrega em cada `DiagramCandidate` -- se fossem dois
retângulos diferentes haveria duas verdades sobre onde o diagrama está, e a que perdesse
produziria um buraco ou um objeto duplicado.

## Coluna a coluna é prosa, e nem toda página é prosa (S-216)

Uma folha de exercícios é uma **grade**, e há livro que a numera atravessando as colunas. Lê-la
coluna a coluna a desordena. Quem parte a página em fileiras é `grade.cortes_de_fileira`, e quem
decide se ela é grade é o **chamador**, pelo parâmetro `arranjo` -- porque a direção da grade não
está na geometria, está no número impresso, e é constante por livro. Ver `text/grade.py`.

`arranjo="prosa"` é o padrão, e é o lado seguro do erro: nada muda enquanto ninguém souber, por
medição, que aquele livro é uma grade lida em fileiras.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, TypeVar

from .boxes import Caixa
from .colunas import atravessa, atribuir_coluna
from .grade import Arranjo, cortes_de_fileira
from .linhas import ordem_em_faixa
from .regioes import Regiao, atribuir_regiao, detectar_regioes


@dataclass(frozen=True)
class Diagrama:
    """Um diagrama da página, do ponto de vista da leitura. O conteúdo dele é da S-211."""

    bbox: tuple[float, float, float, float]
    indice: int = 0
    """A posição na lista que o detector devolveu, para o chamador reencontrar o candidato."""

    @property
    def caixa(self) -> Caixa:
        """O retângulo como `Caixa`, para as réguas de coluna valerem igual para os dois."""
        x0, y0, x1, y1 = self.bbox
        return Caixa(int(x0), int(y0), int(x1), int(y1))


Elemento = Caixa | Diagrama


def _y_topo(elemento: Elemento) -> int:
    return elemento.y1 if isinstance(elemento, Caixa) else elemento.caixa.y1


def _como_caixa(elemento: Elemento) -> Caixa:
    return elemento if isinstance(elemento, Caixa) else elemento.caixa


def sequencia_de_leitura(
    caixas: Sequence[Caixa],
    diagramas: Sequence[Diagrama] = (),
    *,
    colunas: Sequence[tuple[int, int]] | None = None,
    regioes: Sequence[Regiao] | None = None,
    arranjo: Arranjo = "prosa",
) -> list[Elemento]:
    """Caixas de caractere e diagramas na ordem em que um humano os lê.

    Sem `colunas` nem `regioes`, a folha é partida por `regioes.detectar_regioes` sobre as
    **caixas de caractere**: o diagrama não entra na projeção da calha, e não deveria -- um
    diagrama largo encostado na calha a apagaria, que é o mesmo defeito da letra do cabeçalho um
    nível acima.

    `colunas=` é o atalho de quem já sabe que a folha é homogênea: vale como uma região única com
    essas colunas. `regioes=` é o caminho de quem já as achou -- o motor de glifo, que consumiu as
    caixas de caractere para segmentar e não pode redescobri-las a partir das linhas.

    `arranjo="grade"` parte a região em fileiras antes de lê-la coluna a coluna, que é a ordem de
    uma folha de exercícios numerada atravessando as colunas (S-216). O padrão é `"prosa"`, e
    **não há detecção automática**: a direção da grade é constante por livro e sai da numeração
    impressa, não da geometria da página.
    """
    elementos: list[Elemento] = [*caixas, *diagramas]
    if not elementos:
        return []

    if regioes is None and colunas is None:
        regioes = detectar_regioes(caixas) if caixas else []
    if regioes is not None and len(regioes) > 1:
        # **A região vem antes da coluna** (S-507): o parágrafo de largura inteira não pertence a
        # coluna nenhuma, e lê-lo dentro da grade de colunas da região de baixo é o que embaralha
        # a folha. Dentro de cada região vale tudo o que a S-193 já decidiu.
        #
        # **`atribuir_regiao`, e não o intervalo.** O diagrama não entrou na conta que cortou a
        # folha, então o topo dele pode cair acima da primeira região; quem ficasse de fora sairia
        # no fim da página, que é o defeito que a S-190 registra para a caixa fora de toda coluna.
        por_regiao: dict[int, list[Elemento]] = {}
        for elemento in elementos:
            por_regiao.setdefault(atribuir_regiao(_como_caixa(elemento), regioes), []).append(elemento)
        por_ordem: list[Elemento] = []
        for indice, regiao in enumerate(regioes):
            desta = por_regiao.get(indice)
            if desta:
                por_ordem.extend(
                    sequencia_de_leitura(
                        [e for e in desta if isinstance(e, Caixa)],
                        [e for e in desta if isinstance(e, Diagrama)],
                        colunas=regiao.colunas,
                        arranjo=arranjo,
                    )
                )
        return por_ordem
    if colunas is None:
        colunas = regioes[0].colunas if regioes else []
    if len(colunas) <= 1:
        return _ordenar_faixa_unica(elementos)

    # Os cortes saem das caixas de caractere pelo mesmo motivo que a calha: o diagrama **preenche**
    # o vão entre duas fileiras, e deixá-lo entrar apagaria todos eles.
    cortes = cortes_de_fileira(caixas) if arranjo == "grade" and caixas else []

    def em_ordem(quais: Sequence[Elemento]) -> list[Elemento]:
        return _por_fileiras(quais, colunas, cortes) if cortes else _por_colunas(quais, colunas)

    transversais = sorted(
        (e for e in elementos if atravessa(_como_caixa(e), colunas)),
        key=_y_topo,
    )
    if not transversais:
        return em_ordem(elementos)

    identidades = {id(e) for e in transversais}
    restantes = [e for e in elementos if id(e) not in identidades]

    saida: list[Elemento] = []
    for transversal in transversais:
        topo = _y_topo(transversal)
        acima = [e for e in restantes if _como_caixa(e).y2 <= topo]
        if acima:
            ids_acima = {id(e) for e in acima}
            restantes = [e for e in restantes if id(e) not in ids_acima]
            saida.extend(em_ordem(acima))
        saida.append(transversal)

    saida.extend(em_ordem(restantes))
    return saida


def _por_fileiras(
    elementos: Sequence[Elemento],
    colunas: Sequence[tuple[int, int]],
    cortes: Sequence[int],
) -> list[Elemento]:
    """Fileira a fileira; dentro de cada uma, coluna a coluna. Ver a S-216.

    **A fileira vem antes da coluna, e é toda a diferença.** Com a ordem invertida sai a leitura
    de prosa, que é o que a S-193 já faz -- e é o que embaralha a grade numerada atravessando as
    colunas.

    O elemento entra na fileira pelo **topo** dele: um diagrama é mais alto que o corte seguinte e
    pertence à fileira em que começa, não à que a base dele alcança.
    """
    fileiras: list[list[Elemento]] = [[] for _ in range(len(cortes) + 1)]
    for elemento in elementos:
        topo = _y_topo(elemento)
        indice = sum(1 for corte in cortes if topo >= corte)
        fileiras[indice].append(elemento)
    return [e for fileira in fileiras if fileira for e in _por_colunas(fileira, colunas)]


def _por_colunas(elementos: Sequence[Elemento], colunas: Sequence[tuple[int, int]]) -> list[Elemento]:
    """Coluna a coluna; dentro de cada uma, linha a linha."""
    saida: list[Elemento] = []
    for i in range(len(colunas)):
        desta = [e for e in elementos if atribuir_coluna(_como_caixa(e), colunas) == i]
        if desta:
            saida.extend(_ordenar_faixa_unica(desta))
    return saida


def _ordenar_faixa_unica(elementos: Sequence[Elemento]) -> list[Elemento]:
    """Ordem de leitura sem coluna: por banda, e por `x` dentro dela.

    O diagrama entra pela caixa dele, como qualquer outro elemento: é o que o põe **entre** os
    parágrafos em vez de no fim da página.
    """
    por_caixa: dict[int, Elemento] = {}
    caixas: list[Caixa] = []
    for elemento in elementos:
        caixa = _como_caixa(elemento)
        por_caixa[id(caixa)] = elemento
        caixas.append(caixa)
    return [por_caixa[id(c)] for c in ordem_em_faixa(caixas)]


# --------------------------------------------------------------------------------------------
# S-211 · O modelo de página: coluna -> bloco -> linha -> texto | diagrama | tabela
# --------------------------------------------------------------------------------------------
#
# **O problema que ele resolve é de número de verdades, não de conveniência.** Hoje quem recebe
# a página é `service.RecognizedDiagram`, uma lista de diagramas -- e enquanto o produto for
# diagrama isso basta. Com texto, coluna e tabela na conta, cada destino (o PGN, o dataset, a
# fila, o editor de texto) recomporia a página do seu jeito, e a página passaria a existir em
# quatro versões que ninguém compara. É o mesmo defeito que a Fase 6 consertou quando havia duas
# telas implementando o pipeline duas vezes.
#
# **Todo bloco carrega bbox, confiança e procedência, sem exceção.** A procedência é o campo que
# não existia em lugar nenhum e que decide o resto: uma linha vinda da camada de texto do PDF é
# registro do que o editor escreveu, e vale 1,0; uma linha vinda do classificador de glifo é
# palpite calibrado; uma linha corrigida à mão é a mais valiosa das três e é a única que nunca
# pode ser sobrescrita por uma releitura. Sem o campo, as três viram "texto" e a informação de
# quanto confiar nelas se perde na primeira serialização.
#
# **Nada aqui decide apresentação.** A ordem de leitura é do domínio; como desenhar é da
# interface. É a regra que organiza este projeto, e ela vale igual para o bloco de texto.

Procedencia = Literal["camada", "glifo", "tesseract", "rapidocr", "humano"]
"""De onde saiu o texto deste bloco.

`camada` é a camada de texto do PDF -- não é palpite, é o que o editor escreveu. `glifo` é o
classificador da Fase 29. `tesseract` é o leitor de linha da fusão (S-722), e o nome é o do motor, como
`rapidocr`, o motor de fora que já existia na S-43. `humano` é correção à mão, e é a única procedência que
uma releitura não tem direito de apagar.
"""

PROCEDENCIAS: tuple[Procedencia, ...] = ("camada", "glifo", "tesseract", "rapidocr", "humano")
"""Os valores aceitos, e é só isso que esta tupla é: o conjunto que `de_json` cobra.

**A ordem aqui não significa nada, e dizer que significava foi um defeito.** A primeira versão
afirmava no docstring que ela era "crescente de quanto se confia", e `BlocoDeTexto.de_linhas`
tirava a pior procedência com um `min` sobre o índice -- que devolvia `camada`, a **melhor** das
quatro. Um parágrafo com uma linha adivinhada saía marcado como registro, que é exatamente o
contrário do que o campo existe para dizer. Quem responde essa pergunta agora é
`ORDEM_DE_CONFIANCA`, que é uma tupla separada porque a resposta merecia ser escrita, e não
deduzida da ordem em que alguém digitou quatro nomes."""

ORDEM_DE_CONFIANCA: tuple[Procedencia, ...] = ("rapidocr", "glifo", "tesseract", "camada", "humano")
"""As mesmas cinco, da menos para a mais confiável. **Aqui a ordem é o dado.**

`humano` no topo porque é a única que uma releitura não tem direito de apagar; `camada` acima das
leituras porque não é leitura -- é o que o editor do PDF escreveu; e `glifo` acima de `rapidocr`
porque é o motor de casa, calibrado (S-205) e medido neste acervo, enquanto o outro entra sem
calibração e não lê acento.

**`tesseract` acima de `glifo` é medido na prosa, e é só na prosa que ele escreve** (S-722): 1,33% contra
3,61% de CER no digital, 6,0% contra 14,4% no scan. A notação ele estraga, e a fusão não a deixa com ele. A
confiança dele ainda não é calibrada (S-760), e isto aqui não fala dela: fala de quem responde pelo texto.
Por isso uma linha mista de glifo e Tesseract continua `glifo`, como saía antes de ele ter nome."""

GRAVAR_FORMATO_NOVO = False
"""Grava `tesseract`, `procedencia_em` e `confianca_em` no arquivo? **Só depois do portão G102** (S-722).

**O formato novo não é reversível por interruptor depois de gravado**: um programa anterior não abre `.cvtxt` nem
caderno com `tesseract` (estoura `PaginaInvalida`). Enquanto a fusão for experimental, ler o novo e o antigo é de
graça, e gravar o novo não: desligada, a folha sai como saía antes deste item, com o `tesseract` escrito `glifo` e sem
os intervalos. **Os campos continuam inteiros em memória**, e a aba e a exportação os leem; o que se perde ao reabrir é
o detalhe. Quem liga é o G102, junto com a virada do padrão."""


def procedencia_gravada(procedencia: Procedencia) -> Procedencia:
    """O que vai para o arquivo. Ver `GRAVAR_FORMATO_NOVO`: sem ele, `tesseract` sai como a fusão saía, `glifo`."""
    return "glifo" if procedencia == "tesseract" and not GRAVAR_FORMATO_NOVO else procedencia


def menos_confiavel(procedencias: Sequence[Procedencia]) -> Procedencia:
    """A pior das procedências dadas, por `ORDEM_DE_CONFIANCA`. `camada` quando não há nenhuma.

    É o que decide a procedência de um bloco a partir das linhas dele, e a regra é a mesma da
    confiança: **um bloco vale o que vale o pior pedaço dele.**
    """
    if not procedencias:
        return "camada"
    return min(procedencias, key=ORDEM_DE_CONFIANCA.index)


def trechos_de_procedencia(palavras: Iterable[tuple[str, Procedencia]]) -> tuple[tuple[int, int, Procedencia], ...]:
    """`[(palavra, de quem)]`, na ordem em que um `" ".join` as escreve, como intervalos de `LinhaLida.procedencia_em`.

    Vizinhas de mesma origem viram um trecho, com o espaço entre elas. **Uma origem só não pede detalhe**, e sai
    vazio: o campo da linha já diz tudo, e o arquivo não carrega um intervalo por linha para repetir isso.
    """
    saida: list[tuple[int, int, Procedencia]] = []
    posicao = 0
    for texto, quem in palavras:
        if saida and saida[-1][2] == quem:
            saida[-1] = (saida[-1][0], posicao + len(texto), quem)
        else:
            saida.append((posicao, posicao + len(texto), quem))
        posicao += len(texto) + 1
    return tuple(saida) if len(saida) > 1 else ()


def trechos_de_confianca(palavras: Iterable[tuple[str, float | None]]) -> tuple[tuple[int, int, float], ...]:
    """`[(palavra, confiança de quem a escreveu)]` como intervalos de `LinhaLida.confianca_em`. `None` fica sem trecho."""
    saida: list[tuple[int, int, float]] = []
    posicao = 0
    for texto, confianca in palavras:
        if confianca is not None:
            saida.append((posicao, posicao + len(texto), float(confianca)))
        posicao += len(texto) + 1
    return tuple(saida)


V = TypeVar("V")

_NAO_BRANCO = re.compile(r"\S+")


def remapear_com_valor(
    trechos: Iterable[tuple[int, int, V]],
    remapear: Callable[[Sequence[tuple[int, int]]], Sequence[tuple[int, int]]],
) -> tuple[tuple[int, int, V], ...]:
    """Os intervalos com valor sobre um texto reescrito. `remapear` é o mesmo que o `negrito_em` usa.

    **Um de cada vez, e é por isso que esta função existe**: `camada.remapear` une marcas vizinhas, que é a regra certa
    para o negrito e errada aqui, em que cada intervalo tem o seu valor. O que a reescrita comeu não vira intervalo.
    """
    return tuple((inicio, fim, valor) for a, b, valor in trechos for inicio, fim in remapear([(a, b)]) if inicio < fim)


UNIDADES = ("pt", "px")
"""`pt` são pontos do PDF, `px` são pixels da imagem renderizada.

**A unidade viaja com a página porque perdê-la é um defeito silencioso.** Um bbox em pixels a 220
dpi lido como pontos aponta para fora da folha, e nada estoura: o retângulo simplesmente não
casa com nada. A anotação de campo já aprendeu isso na S-41, e o motivo é o mesmo -- 220 dpi hoje,
300 amanhã."""


class PaginaInvalida(ValueError):
    """O JSON não descreve uma `PaginaLida`: falta campo, procedência é outra, bbox não tem 4."""


def _bbox_de(valor: Any, onde: str) -> tuple[float, float, float, float]:
    """Quatro números, ou `PaginaInvalida` dizendo onde. Existe para o erro apontar o campo."""
    try:
        x0, y0, x1, y1 = (float(v) for v in valor)
    except (TypeError, ValueError) as exc:
        raise PaginaInvalida(f"{onde}: bbox precisa de quatro números, veio {valor!r}") from exc
    return (x0, y0, x1, y1)


def _procedencia_de(valor: Any, onde: str) -> Procedencia:
    if valor not in PROCEDENCIAS:
        raise PaginaInvalida(f"{onde}: procedência {valor!r} não é uma de {PROCEDENCIAS}")
    return valor  # type: ignore[return-value]


def _envolver(caixas: Sequence[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    """O retângulo que contém todos. `(0, 0, 0, 0)` quando não há nenhum -- e é o certo aqui.

    Um bloco vazio não tem lugar na página, e inventar um retângulo infinito para ele faria
    `atribuir_coluna` mandá-lo para uma coluna qualquer.
    """
    if not caixas:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(c[0] for c in caixas),
        min(c[1] for c in caixas),
        max(c[2] for c in caixas),
        max(c[3] for c in caixas),
    )


@dataclass(frozen=True)
class LinhaLida:
    """Uma linha de texto com a régua de quanto confiar nela.

    Não é a `paragrafos.Linha`, e a diferença é o assunto: aquela carrega `topo`, `esquerda` e
    `altura` porque o cliente dela é a régua de recuo; esta carrega bbox, confiança e procedência
    porque o cliente dela é quem lê e quem corrige. Elas se encontram em `de_paragrafo`.
    """

    texto: str
    bbox: tuple[float, float, float, float]
    confianca: float = 1.0
    procedencia: Procedencia = "camada"
    negrito: bool | None = None
    """A linha está em negrito? **`None` é "não se sabe", e não é o mesmo que `False`.**

    Dos 42 livros do acervo, 13 registram peso de fonte na camada de texto e 29 não -- e um livro
    que não registra não pode declarar que nada ali é negrito. Ver `text/negrito.py`, que também
    explica por que isto **não** sai da imagem."""

    italico: bool | None = None
    """A linha está inclinada? `None` é "não se sabe", como em `negrito` -- e por razão oposta.

    **O itálico sai da imagem, e o negrito não.** `text/italico.py` mede o pendor da linha e separa:
    +0,116 de mediana nas linhas itálicas contra +0,000 nas linhas em pé, sem sobreposição, em 157
    linhas da folha 311 do `Secrets of Chess Training`. O negrito não teve essa sorte -- a espessura
    do traço não passou do acaso (82,2% contra 82,7%), e por isso ele vem da camada.

    `None` aqui é o caminho da **camada**, que não passa pela binária e não tem pendor para medir --
    e a linha curta demais, que não tem população (`italico.MIN_BOXES_PARA_MEDIR`). Ver S-236."""

    negrito_em: tuple[tuple[int, int], ...] = ()
    """Onde, dentro de `texto`, está o negrito -- intervalos `[início, fim)` de caractere (S-429).

    **Isto é o detalhe, e `negrito` é o resumo.** Os dois vêm da mesma camada e não se contradizem:
    o campo acima responde "esta linha é de peso?" pela maioria da largura, este responde "quais
    letras têm peso?". Vazio quer dizer *não há detalhe* -- ou porque nada ali é negrito, ou porque
    não deu para casar o texto lido com o da camada --, e aí quem desenha usa o resumo, que é o
    comportamento de antes deste campo existir.

    Medido no acervo, 44,2% das linhas com peso misturam peso dentro de si, e é toda essa população
    que o resumo sozinho erra -- para mais ou para menos. Ver `text/camada.py`."""

    italico_em: tuple[tuple[int, int], ...] = ()
    """Onde, dentro de `texto`, está o itálico. Mesmo contrato do `negrito_em` acima (S-429).

    **A diferença é a origem, e ela deixa este campo mais vazio.** O peso só tem uma fonte, a
    camada, então o detalhe dele vale sempre. O pendor tem duas -- a binária, que responde por
    linha, e a camada, que responde por span --, e só a segunda sabe dizer *onde*. Por isso este
    campo só é preenchido no motor `camada`: no de glifo a folha é scan, e a camada dali é palpite
    de outro OCR sobre a mesma imagem, que não pode sobrescrever o pendor medido na binária. Ver o
    comentário em `leitor.ler_pagina`, ao lado da chamada.

    Nos 12 livros que declaram pendor, 68,6% das linhas itálicas o misturam dentro de si."""

    revisar_em: tuple[tuple[int, int], ...] = ()
    """Quais palavras de `texto` pedem olho (S-718), em intervalos `[início, fim)` como os de estilo.

    **Vive em memória, e `para_json` não o escreve**: é recalculado a cada leitura, e o que sobrevive
    ao arquivo é a faixa da corrida que ele produz. O `ESQUEMA` subiu na S-722 e ele continuou fora: é derivado da
    folha inteira, e quem grava o dado de que a marca sai são os campos abaixo."""

    procedencia_em: tuple[tuple[int, int, Procedencia], ...] = ()
    """De quem é cada trecho de `texto`, em `[início, fim, procedência)` (S-722). O mesmo desenho de `negrito_em`.

    **Isto é o detalhe, e `procedencia` é o resumo: a menos confiável das que compõem a linha.** Vazio quer dizer que não
    há detalhe a dar: uma origem só, ou arquivo gravado antes deste campo. Com ele, os trechos cobrem todas as palavras,
    e só o espaço entre duas origens fica de fora. **É a única procedência por intervalo do programa**: a S-716 a
    prometia em memória, e o que havia era o `so_da_camada` por linha, que passou a ser derivado daqui."""

    confianca_em: tuple[tuple[int, int, float], ...] = ()
    """Quanto vale cada palavra de `texto` (S-722), em `[início, fim, valor)`. Só os motores que combinam leitores o preenchem, e só onde se sabe.

    **Na fusão, a prosa traz a confiança calibrada da S-760**, a probabilidade de a palavra estar certa, e `confianca` é a da mais fraca. O lance fica com
    a de quem o escreveu: a referência da notação é a camada, e calibrar contra ela mediria a referência. Com `confianca_palavra.LIGADO` desligado, tudo aqui
    é a de quem escreveu, e `confianca` é a do glifo."""

    def procedencia_no(self, posicao: int) -> Procedencia:
        """De quem é o caractere nesta posição de `texto`. Sem detalhe que o cubra, vale o campo da linha."""
        return next((quem for inicio, fim, quem in self.procedencia_em if inicio <= posicao < fim), self.procedencia)

    @property
    def pede_formato_novo(self) -> bool:
        """Só o formato novo guarda o que esta linha sabe: é o que decide se a folha paga versão (S-710, S-722)."""
        return self.procedencia == "tesseract" or bool(self.procedencia_em) or bool(self.confianca_em)

    def para_json(self) -> dict[str, Any]:
        dados: dict[str, Any] = {
            "texto": self.texto,
            "bbox": list(self.bbox),
            "confianca": self.confianca,
            "procedencia": procedencia_gravada(self.procedencia),
            "negrito": self.negrito,
            "italico": self.italico,
            "negrito_em": [list(t) for t in self.negrito_em],
            "italico_em": [list(t) for t in self.italico_em],
        }
        if GRAVAR_FORMATO_NOVO and self.procedencia_em:
            dados["procedencia_em"] = [list(t) for t in self.procedencia_em]
        if GRAVAR_FORMATO_NOVO and self.confianca_em:
            dados["confianca_em"] = [list(t) for t in self.confianca_em]
        return dados

    @classmethod
    def de_json(cls, dados: Any, onde: str = "linha") -> LinhaLida:
        if not isinstance(dados, dict):
            raise PaginaInvalida(f"{onde}: esperava objeto, veio {type(dados).__name__}")
        return cls(
            texto=str(dados.get("texto", "")),
            bbox=_bbox_de(dados.get("bbox"), onde),
            confianca=float(dados.get("confianca", 1.0)),
            procedencia=_procedencia_de(dados.get("procedencia"), onde),
            negrito=_negrito_de(dados.get("negrito"), onde),
            italico=_tres_estados(dados.get("italico"), onde, "italico"),
            negrito_em=_trechos_de(dados.get("negrito_em"), onde, "negrito_em"),
            italico_em=_trechos_de(dados.get("italico_em"), onde, "italico_em"),
            procedencia_em=_procedencias_em(dados.get("procedencia_em"), onde),
            confianca_em=_confiancas_em(dados.get("confianca_em"), onde),
        )


def _trio_de(par: Any, onde: str, campo: str) -> tuple[int, int, Any]:
    """`(início, fim, valor)`, com o mesmo contrato de `_trechos_de`: `fim > início >= 0`, ou `PaginaInvalida`."""
    try:
        inicio, fim, valor = par
        inicio, fim = int(inicio), int(fim)
    except (TypeError, ValueError) as exc:
        raise PaginaInvalida(f"{onde}: {campo} tem item que não é (início, fim, valor): {par!r}") from exc
    if not 0 <= inicio < fim:
        raise PaginaInvalida(f"{onde}: {campo} tem item fora de ordem ou negativo: {par!r}")
    return (inicio, fim, valor)


def _procedencias_em(valor: Any, onde: str) -> tuple[tuple[int, int, Procedencia], ...]:
    """Ausente é vazio, e ilegível levanta: as duas metades de `_trechos_de`, pela mesma razão."""
    if valor is None:
        return ()
    if not isinstance(valor, (list, tuple)):
        raise PaginaInvalida(f"{onde}: procedencia_em é uma lista -- veio {valor!r}")
    saida: list[tuple[int, int, Procedencia]] = []
    for item in valor:
        inicio, fim, quem = _trio_de(item, onde, "procedencia_em")
        saida.append((inicio, fim, _procedencia_de(quem, onde)))
    return tuple(saida)


def _confiancas_em(valor: Any, onde: str) -> tuple[tuple[int, int, float], ...]:
    if valor is None:
        return ()
    if not isinstance(valor, (list, tuple)):
        raise PaginaInvalida(f"{onde}: confianca_em é uma lista -- veio {valor!r}")
    saida: list[tuple[int, int, float]] = []
    for item in valor:
        inicio, fim, confianca = _trio_de(item, onde, "confianca_em")
        if isinstance(confianca, bool) or not isinstance(confianca, (int, float)):
            raise PaginaInvalida(f"{onde}: confianca_em tem valor que não é número: {item!r}")
        saida.append((inicio, fim, float(confianca)))
    return tuple(saida)


def _trechos_de(valor: Any, onde: str, campo: str) -> tuple[tuple[int, int], ...]:
    """Os intervalos de estilo de um arquivo, ou `PaginaInvalida` dizendo qual campo.

    **Ausente é vazio, e ilegível levanta** -- as duas metades de `_tres_estados`, pela mesma razão:
    um `.json` gravado antes da S-429 não tem o campo e não é inválido por isso, mas um campo que
    está lá e não descreve intervalo nenhum é arquivo corrompido, e engoli-lo desenharia o negrito
    no lugar errado sem ninguém saber por quê.

    `fim > inicio >= 0` faz parte do contrato e não é conferido depois: um par vazio ou invertido
    atravessaria `rico` sem erro e sumiria na tela, que é o defeito mais caro de achar."""
    if valor is None:
        return ()
    if not isinstance(valor, (list, tuple)):
        raise PaginaInvalida(f"{onde}: {campo} é uma lista de pares -- veio {valor!r}")
    saida: list[tuple[int, int]] = []
    for par in valor:
        try:
            inicio, fim = (int(v) for v in par)
        except (TypeError, ValueError) as exc:
            raise PaginaInvalida(f"{onde}: {campo} tem par que não é (início, fim): {par!r}") from exc
        if not 0 <= inicio < fim:
            raise PaginaInvalida(f"{onde}: {campo} tem par fora de ordem ou negativo: {par!r}")
        saida.append((inicio, fim))
    return tuple(saida)


def _tres_estados(valor: Any, onde: str, campo: str) -> bool | None:
    """`True`, `False` ou `None` -- e um arquivo antigo, sem o campo, vira `None`.

    Campo ausente é "não se sabe", que é exatamente o que um arquivo gravado antes deste campo
    existir sabe sobre ele. Não paga versão de esquema por isso.

    Um só leitor para `negrito` e `italico`: são a mesma pergunta de três estados, e dois leitores
    iguais lado a lado seriam dois lugares para consertar quando o terceiro campo chegasse."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    raise PaginaInvalida(f"{onde}: {campo} é True, False ou ausente -- veio {valor!r}")


def _negrito_de(valor: Any, onde: str) -> bool | None:
    """Ver `_tres_estados`."""
    return _tres_estados(valor, onde, "negrito")


def _indice_de_legenda(valor: Any, onde: str) -> int | None:
    """O índice de diagrama de `legenda_de`, ou `None` -- e ausente é `None` (S-249).

    Ausente é "este parágrafo não é legenda de ninguém", que é exatamente o que um arquivo gravado
    antes deste campo existir sabe sobre ele. Não paga versão de esquema por isso.

    Valor que **não** é índice levanta, como em `_tres_estados`: aqui o campo aponta para um
    diagrama da mesma página, e um apontador estragado desenharia a legenda no lugar errado --
    silenciosamente.
    """
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise PaginaInvalida(f"{onde}: legenda_de é um índice de diagrama ou ausente -- veio {valor!r}")
    if valor < 0:
        raise PaginaInvalida(f"{onde}: legenda_de não pode ser negativo -- veio {valor!r}")
    return valor


@dataclass(frozen=True)
class BlocoDeTexto:
    """Um parágrafo, com as linhas que o compõem.

    A confiança do bloco é a **mínima** das linhas, pelo mesmo motivo que a `TextBox` da S-181 usa
    a mínima dos caracteres: um parágrafo com uma linha adivinhada no meio não é um parágrafo 90%
    confiável, e a média esconderia exatamente a linha que alguém precisa olhar.
    """

    tipo: str = field(default="texto", init=False)
    linhas: tuple[LinhaLida, ...] = ()
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    confianca: float = 1.0
    procedencia: Procedencia = "camada"
    recuado: bool = False
    """Este parágrafo abriu por recuo. A interface o usa para reproduzir a diagramação; o domínio
    o usa para nada, e é por isso que ele é um `bool` e não um número de pontos."""

    negrito: bool | None = None
    """O parágrafo inteiro em negrito. `None` é "não se sabe"; ver `LinhaLida.negrito`."""

    italico: bool | None = None
    """O parágrafo inteiro em itálico. `None` é "não se sabe"; ver `LinhaLida.italico`."""

    legenda_de: int | None = None
    """O índice do diagrama de que este parágrafo é a **legenda**, ou `None` (S-249).

    **É o vínculo que faltava na `PaginaLida`.** Quem casa linha com diagrama é
    `pdf_text.assign_lines_to_diagrams`, e ele roda dentro do caminho de leitura, com a página
    aberta. Até 2026-08-25 o resultado morria ali: a página ficava com o `BlocoDeDiagrama` e os
    `BlocoDeTexto` lado a lado, **sem** dizer qual descreve qual -- e o editor não tinha como
    pintar a legenda de legenda (S-249), nem a S-253 como saber que aquele parágrafo é legenda.

    Guardar o índice, e não o bloco, é o mesmo desenho de `BlocoDeDiagrama.indice`: índice
    serializa, referência não -- e é por ele que a interface reencontra o diagrama."""

    @property
    def texto(self) -> str:
        return " ".join(linha.texto for linha in self.linhas)

    def procedencia_da_palavra(self, numero: int) -> Procedencia:
        """De quem é a palavra `numero` de `texto.split()`. É o que diz quem errou numa palavra corrigida (S-762, S-722)."""
        restante = numero
        for linha in self.linhas:
            palavras = list(_NAO_BRANCO.finditer(linha.texto))
            if restante < len(palavras):
                return linha.procedencia_no(palavras[restante].start())
            restante -= len(palavras)
        return self.procedencia

    @classmethod
    def de_linhas(cls, linhas: Sequence[LinhaLida], *, recuado: bool = False) -> BlocoDeTexto:
        """Fecha o bloco derivando bbox, confiança e procedência das linhas -- sem inventar nada.

        A procedência do bloco é a **menos confiável** das linhas dele: um parágrafo em que uma
        linha veio do glifo não é um parágrafo da camada de texto, e dizer que é faria a interface
        pintá-lo como registro.
        """
        if not linhas:
            return cls()
        pesos = {linha.negrito for linha in linhas}
        pendores = {linha.italico for linha in linhas}
        return cls(
            linhas=tuple(linhas),
            bbox=_envolver([linha.bbox for linha in linhas]),
            confianca=min(linha.confianca for linha in linhas),
            procedencia=menos_confiavel([linha.procedencia for linha in linhas]),
            recuado=recuado,
            # **O bloco só é negrito se TODAS as linhas forem.** Um parágrafo com uma linha em
            # negrito não é um parágrafo em negrito, e `None` em qualquer linha contamina o
            # conjunto -- não se sabe do todo o que não se sabe de uma parte.
            negrito=pesos.pop() if len(pesos) == 1 else None,
            # A mesma regra para o pendor, e ela é mais exigente do que parece: um parágrafo de
            # prosa com **uma** frase em itálico sai `None`, e é o certo. A régua da S-236 é da
            # linha, e o bloco não sabe mais do que as linhas dele.
            italico=pendores.pop() if len(pendores) == 1 else None,
        )

    def para_json(self) -> dict[str, Any]:
        return {
            "tipo": "texto",
            "bbox": list(self.bbox),
            "confianca": self.confianca,
            "procedencia": procedencia_gravada(self.procedencia),
            "recuado": self.recuado,
            "negrito": self.negrito,
            "italico": self.italico,
            "legenda_de": self.legenda_de,
            "linhas": [linha.para_json() for linha in self.linhas],
        }

    @classmethod
    def de_json(cls, dados: dict[str, Any], onde: str) -> BlocoDeTexto:
        return cls(
            linhas=tuple(
                LinhaLida.de_json(item, f"{onde}.linhas[{i}]") for i, item in enumerate(dados.get("linhas", []))
            ),
            bbox=_bbox_de(dados.get("bbox"), onde),
            confianca=float(dados.get("confianca", 1.0)),
            procedencia=_procedencia_de(dados.get("procedencia"), onde),
            recuado=bool(dados.get("recuado", False)),
            negrito=_negrito_de(dados.get("negrito"), onde),
            italico=_tres_estados(dados.get("italico"), onde, "italico"),
            legenda_de=_indice_de_legenda(dados.get("legenda_de"), onde),
        )


@dataclass(frozen=True)
class BlocoDeDiagrama:
    """O diagrama como objeto da coluna. O conteúdo dele continua sendo do `RecognizedDiagram`.

    **Ele guarda `indice` e não o tabuleiro.** O `board_rgb` de um diagrama são ~1,5 MB, e uma
    `PaginaLida` serializável que os carregasse não caberia em JSON nenhum. `indice` é a posição na
    lista que o detector devolveu -- a mesma chave que a S-12 já usa --, e é por ela que a
    interface reencontra o recorte quando precisa desenhá-lo.

    `confianca` aqui é a do **detector**, não a da leitura das peças: é a resposta para "isto é um
    diagrama?", e não para "é este o tabuleiro?". Juntá-las num número só foi o defeito que a
    `DiagramCandidate.detector_score` já documenta.
    """

    tipo: str = field(default="diagrama", init=False)
    indice: int = 0
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    confianca: float = 1.0
    procedencia: Procedencia = "glifo"
    placement: str = ""
    """Só o campo de peças da FEN, quando já houve leitura. Vazio é "não lido" -- e é diferente de
    um tabuleiro vazio, que tem placement `8/8/8/8/8/8/8/8`."""

    @property
    def texto(self) -> str:
        """O que este bloco vira no texto corrido: uma marca, e nunca a FEN.

        **A marca é conteúdo do editor, e é por isso que ela é estável.** Quem edita o texto de uma
        página precisa poder mover o diagrama de lugar, e para isso o diagrama tem de ter uma
        representação textual que sobreviva a ir e voltar. `[Diagrama N]` é ela.
        """
        return f"[Diagrama {self.indice + 1}]"

    def para_json(self) -> dict[str, Any]:
        return {
            "tipo": "diagrama",
            "indice": self.indice,
            "bbox": list(self.bbox),
            "confianca": self.confianca,
            "procedencia": procedencia_gravada(self.procedencia),
            "placement": self.placement,
        }

    @classmethod
    def de_json(cls, dados: dict[str, Any], onde: str) -> BlocoDeDiagrama:
        return cls(
            indice=int(dados.get("indice", 0)),
            bbox=_bbox_de(dados.get("bbox"), onde),
            confianca=float(dados.get("confianca", 1.0)),
            procedencia=_procedencia_de(dados.get("procedencia"), onde),
            placement=str(dados.get("placement", "")),
        )


@dataclass(frozen=True)
class BlocoDeTabela:
    """A tabela como tabela, e não como nove linhas de texto embaralhadas (S-199).

    As células vêm em ordem de leitura, uma tupla de linhas de textos -- a forma que sobrevive a
    JSON e que a interface consegue desenhar sem reconstruir a grade.
    """

    tipo: str = field(default="tabela", init=False)
    celulas: tuple[tuple[str, ...], ...] = ()
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    confianca: float = 1.0
    procedencia: Procedencia = "glifo"

    @property
    def forma(self) -> tuple[int, int]:
        return (len(self.celulas), max((len(linha) for linha in self.celulas), default=0))

    @property
    def texto(self) -> str:
        """Linhas separadas por tabulação -- o formato que cola em planilha e volta inteiro."""
        return "\n".join("\t".join(linha) for linha in self.celulas)

    def para_json(self) -> dict[str, Any]:
        return {
            "tipo": "tabela",
            "celulas": [list(linha) for linha in self.celulas],
            "bbox": list(self.bbox),
            "confianca": self.confianca,
            "procedencia": procedencia_gravada(self.procedencia),
        }

    @classmethod
    def de_json(cls, dados: dict[str, Any], onde: str) -> BlocoDeTabela:
        return cls(
            celulas=tuple(tuple(str(c) for c in linha) for linha in dados.get("celulas", [])),
            bbox=_bbox_de(dados.get("bbox"), onde),
            confianca=float(dados.get("confianca", 1.0)),
            procedencia=_procedencia_de(dados.get("procedencia"), onde),
        )


@dataclass(frozen=True)
class BlocoDeTarja:
    """Texto claro sobre fundo escuro (S-195), já positivado e lido.

    É um bloco à parte e não um `BlocoDeTexto` com uma flag porque a **releitura** dele é outra: ela
    precisa positivar a faixa antes de segmentar, e um bloco que não diz isso obrigaria quem relê a
    adivinhar pela cor média do recorte.
    """

    tipo: str = field(default="tarja", init=False)
    linhas: tuple[LinhaLida, ...] = ()
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    confianca: float = 1.0
    procedencia: Procedencia = "glifo"

    @property
    def texto(self) -> str:
        return " ".join(linha.texto for linha in self.linhas)

    def para_json(self) -> dict[str, Any]:
        return {
            "tipo": "tarja",
            "bbox": list(self.bbox),
            "confianca": self.confianca,
            "procedencia": procedencia_gravada(self.procedencia),
            "linhas": [linha.para_json() for linha in self.linhas],
        }

    @classmethod
    def de_json(cls, dados: dict[str, Any], onde: str) -> BlocoDeTarja:
        return cls(
            linhas=tuple(
                LinhaLida.de_json(item, f"{onde}.linhas[{i}]") for i, item in enumerate(dados.get("linhas", []))
            ),
            bbox=_bbox_de(dados.get("bbox"), onde),
            confianca=float(dados.get("confianca", 1.0)),
            procedencia=_procedencia_de(dados.get("procedencia"), onde),
        )


Bloco = BlocoDeTexto | BlocoDeDiagrama | BlocoDeTabela | BlocoDeTarja

_BLOCOS: dict[str, Any] = {
    "texto": BlocoDeTexto,
    "diagrama": BlocoDeDiagrama,
    "tabela": BlocoDeTabela,
    "tarja": BlocoDeTarja,
}


def bloco_de_json(dados: Any, onde: str = "bloco") -> Bloco:
    """Despacha pelo campo `tipo`. Um tipo desconhecido levanta em vez de virar bloco de texto.

    **Virar texto seria a resposta errada**, e é a tentadora: uma tabela lida por uma versão nova
    e aberta por uma velha sairia como um parágrafo de células colada, sem nada avisando. Melhor
    recusar o arquivo e dizer qual campo não se entende.
    """
    if not isinstance(dados, dict):
        raise PaginaInvalida(f"{onde}: esperava objeto, veio {type(dados).__name__}")
    tipo = dados.get("tipo")
    classe = _BLOCOS.get(str(tipo))
    if classe is None:
        raise PaginaInvalida(f"{onde}: tipo de bloco {tipo!r} não é um de {sorted(_BLOCOS)}")
    return classe.de_json(dados, onde)  # type: ignore[no-any-return]


@dataclass(frozen=True)
class Coluna:
    """Uma tira da página, com os blocos dela em ordem de leitura.

    **Era "uma faixa vertical da página", e desde a S-507 é uma tira de uma região.** Numa folha
    homogênea -- a esmagadora maioria -- as duas leituras coincidem, e o `indice` sai igual ao de
    antes. Numa folha com bloco de largura inteira em cima de duas colunas, a tira do bloco cobre
    a folha toda e não é faixa vertical de nada: forçá-la a ser uma das colunas é justamente o que
    embaralhava a página.
    """

    indice: int = 0
    """A posição desta tira **na ordem de leitura**, contada de cima para baixo e da esquerda para
    a direita. Não é a coluna geométrica: numa folha de três regiões de duas colunas ela vai de 0
    a 5. Quem quer a coluna geométrica pergunta ao `bbox`."""

    blocos: tuple[Bloco, ...] = ()
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    @property
    def texto(self) -> str:
        """Blocos separados por linha em branco -- o parágrafo é a unidade, não a linha."""
        return "\n\n".join(bloco.texto for bloco in self.blocos if bloco.texto)

    def para_json(self) -> dict[str, Any]:
        return {
            "indice": self.indice,
            "bbox": list(self.bbox),
            "blocos": [bloco.para_json() for bloco in self.blocos],
        }

    @classmethod
    def de_json(cls, dados: Any, onde: str = "coluna") -> Coluna:
        if not isinstance(dados, dict):
            raise PaginaInvalida(f"{onde}: esperava objeto, veio {type(dados).__name__}")
        return cls(
            indice=int(dados.get("indice", 0)),
            blocos=tuple(
                bloco_de_json(b, f"{onde}.blocos[{i}]") for i, b in enumerate(dados.get("blocos", []))
            ),
            bbox=_bbox_de(dados.get("bbox"), onde),
        )


ESQUEMA = 3
"""Até que versão do formato de `para_json` este programa lê. Sobe quando um campo muda de significado, não quando nasce.

Campo novo com padrão é compatível nos dois sentidos e não paga versão -- é a mesma regra do
`char_meta.json` da S-179.

**O 2 é a exceção escrita (S-710), e só a folha com aviso o paga.** `avisos` diz que a leitura pode
estar incompleta, e um programa que abre o arquivo e o ignora mostraria como inteira uma folha que o
arquivo sabe que não é: esse campo muda o que o resto do arquivo significa. Por isso a folha **sem**
aviso continua saindo no formato 1, sem o campo, e um programa anterior a este a abre como sempre.

**O 3 é a S-722, pela mesma regra.** Um programa anterior recusa `tesseract`, e ignoraria os intervalos. Só a folha que
os tem o paga, e só depois do G102: ver `GRAVAR_FORMATO_NOVO`. O 1 e o 2 continuam legíveis, e saem como sempre saíram."""

ESQUEMA_DOS_AVISOS = 2

FOLHA_NAO_LIDA = "folha_nao_lida"
LEITURA_PARCIAL = "leitura_parcial"
LEIAUTE_DE_RESERVA = "leiaute_de_reserva"
CAMADA_NA_FOLHA = "camada_na_folha"
CAMADA_RECUSADA = "camada_recusada"
LEITOR_INDISPONIVEL = "leitor_indisponivel"
CACHE_NAO_GRAVADO = "cache_nao_gravado"
AVISOS: tuple[str, ...] = (
    FOLHA_NAO_LIDA,
    LEITURA_PARCIAL,
    LEIAUTE_DE_RESERVA,
    CAMADA_NA_FOLHA,
    CAMADA_RECUSADA,
    LEITOR_INDISPONIVEL,
    CACHE_NAO_GRAVADO,
)
"""Os códigos conhecidos. **`de_json` aceita um que não esteja aqui**: quem lê um aviso de versão mais
nova ainda o mostra pela mensagem, e recusar o arquivo por isso perderia a folha inteira."""

AVISOS_DA_SESSAO: frozenset[str] = frozenset({CACHE_NAO_GRAVADO})
"""O que é da leitura de agora, e não da folha (S-725): uma folha inteira não passa a dizer, no arquivo, que o disco esteve cheio."""


@dataclass(frozen=True)
class Aviso:
    """Algo que quem lê a folha precisa saber sobre a leitura dela, e que o texto não diz (S-710).

    `dado` é o número que disparou, quando há um: a densidade de leitura, por exemplo. **Aviso nunca
    muda texto**, e quem o desenha é a aba. A mensagem é frase de gente, escrita onde ele nasce, para
    o arquivo reaberto dizer a mesma coisa sem depender de tabela nenhuma.
    """

    codigo: str
    mensagem: str
    dado: float | None = None

    def para_json(self) -> dict[str, Any]:
        return {"codigo": self.codigo, "mensagem": self.mensagem, "dado": self.dado}

    @classmethod
    def de_json(cls, dados: Any, onde: str = "aviso") -> Aviso:
        if not isinstance(dados, dict) or not isinstance(dados.get("codigo"), str):
            raise PaginaInvalida(f"{onde}: aviso sem código -- veio {dados!r}")
        dado = dados.get("dado")
        try:
            return cls(str(dados["codigo"]), str(dados.get("mensagem", "")), None if dado is None else float(dado))
        except (TypeError, ValueError) as exc:
            raise PaginaInvalida(f"{onde}: dado do aviso não é número -- veio {dado!r}") from exc


@dataclass(frozen=True)
class PaginaLida:
    """A página como objeto: colunas de blocos, e o que está nas margens (S-211).

    **Imutável e serializável sem perda**, e as duas coisas pelo mesmo motivo: ela é o que quatro
    consumidores leem, e um deles é a interface, que a guarda enquanto o usuário edita. Uma página
    mutável compartilhada entre a aba de texto e a exportação produziria o defeito clássico -- o
    PGN sai com o texto de antes da correção, e não há como saber onde ele se perdeu.

    `unidade` é o que impede o outro defeito silencioso; ver `UNIDADES`.
    """

    pagina: int = 0
    """Índice 0-based da página no documento -- a mesma chave que a `pdf_panel` usa."""

    largura: float = 0.0
    altura: float = 0.0
    unidade: str = "pt"
    colunas: tuple[Coluna, ...] = ()
    cabecalho: LinhaLida | None = None
    rodape: LinhaLida | None = None
    numero_impresso: int | None = None
    """O número que a página **mostra**, que não é `pagina + 1`: quem o acha é
    `pdf_text.running_page_number`, e ele não é função afim do índice -- ver a docstring de lá."""

    documento: str = ""
    """Identidade do livro, para a página saber de onde veio quando é gravada sozinha."""

    avisos: tuple[Aviso, ...] = ()
    """O que a leitura sabe de si mesma: folha que não foi lida inteira, leiaute de reserva (S-710)."""

    modelo: str = ""
    """O sha do classificador que leu a folha, vazio quando não foi ele ou não se sabe (S-762).

    Campo novo com padrão: não paga `ESQUEMA`, e um programa anterior o ignora. É o que a correção precisa para dizer de quem veio o erro."""

    marca_por_palavra: bool = False
    """A marca desta folha é por palavra, e não a faixa de confiança do bloco (S-718).

    **Só o motor que combina dois leitores a liga.** A confiança do glifo não pode ser pintada sobre
    texto que outro leitor escreveu: no *Hertan* o texto certo do Tesseract sairia `revisar` porque o
    glifo errou ali. **Vai ao arquivo**: campo novo com padrão, que não paga `ESQUEMA`, como `modelo`. Sem ele, a folha reaberta voltava a contar
    pela confiança do glifo sobre texto de outro leitor. `LinhaLida.revisar_em` continua em memória: o que sobrevive é a faixa da corrida."""

    # -------------------------------------------------------------------------------- leituras

    @property
    def blocos(self) -> tuple[Bloco, ...]:
        """Todos os blocos, na ordem de leitura -- coluna a coluna."""
        return tuple(bloco for coluna in self.colunas for bloco in coluna.blocos)

    @property
    def diagramas(self) -> tuple[BlocoDeDiagrama, ...]:
        return tuple(b for b in self.blocos if isinstance(b, BlocoDeDiagrama))

    def texto(self, *, com_marcas: bool = True) -> str:
        """O texto corrido da página, na ordem em que ela se lê.

        `com_marcas=False` deixa o diagrama de fora em vez de escrever `[Diagrama N]`, que é o que
        quem exporta prosa quer. O padrão é **com** as marcas, porque é o que o editor carrega: sem
        elas, o diagrama entre o parágrafo 3 e o 4 desapareceria do texto e voltaria no fim -- o
        defeito que a S-193 existe para não ter.
        """
        partes: list[str] = []
        for coluna in self.colunas:
            for bloco in coluna.blocos:
                if not com_marcas and isinstance(bloco, BlocoDeDiagrama):
                    continue
                if bloco.texto:
                    partes.append(bloco.texto)
        return "\n\n".join(partes)

    @property
    def confianca_minima(self) -> float:
        """A do pior bloco. `1.0` numa página sem bloco nenhum -- não há nada de que duvidar."""
        return min((b.confianca for b in self.blocos), default=1.0)

    def procedencias(self) -> dict[Procedencia, int]:
        """Quantos blocos de cada procedência. É o que a barra de status da aba de texto mostra."""
        contagem: dict[Procedencia, int] = {}
        for bloco in self.blocos:
            contagem[bloco.procedencia] = contagem.get(bloco.procedencia, 0) + 1
        return contagem

    def caracteres_por_procedencia(self) -> dict[Procedencia, int]:
        """Quantos caracteres (fora o espaço) de cada procedência, lendo os intervalos onde há (S-722).

        É a resposta de que `procedencias` não dá conta: um bloco misto conta inteiro como `glifo`, por mais que quase
        todo ele tenha vindo do Tesseract."""
        contagem: dict[Procedencia, int] = {}
        for linha in self._linhas_dos_blocos():
            for posicao, caractere in enumerate(linha.texto):
                if not caractere.isspace():
                    quem = linha.procedencia_no(posicao)
                    contagem[quem] = contagem.get(quem, 0) + 1
        return contagem

    def _linhas_dos_blocos(self) -> Iterator[LinhaLida]:
        for bloco in self.blocos:
            yield from getattr(bloco, "linhas", ())

    @property
    def tem_detalhe_de_procedencia(self) -> bool:
        return any(linha.procedencia_em for linha in self._linhas_dos_blocos())

    @property
    def pede_formato_novo(self) -> bool:
        """Esta folha sabe algo que só o formato da S-722 guarda?"""
        margens = [linha for linha in (self.cabecalho, self.rodape) if linha is not None]
        return (
            any(bloco.procedencia == "tesseract" for bloco in self.blocos)
            or any(linha.pede_formato_novo for linha in self._linhas_dos_blocos())
            or any(linha.pede_formato_novo for linha in margens)
        )

    # ---------------------------------------------------------------------------- serialização

    def _avisos_gravados(self) -> tuple[Aviso, ...]:
        return tuple(aviso for aviso in self.avisos if aviso.codigo not in AVISOS_DA_SESSAO)

    def _esquema_gravado(self) -> int:
        if GRAVAR_FORMATO_NOVO and self.pede_formato_novo:
            return ESQUEMA
        return ESQUEMA_DOS_AVISOS if self._avisos_gravados() else 1

    def para_json(self) -> dict[str, Any]:
        dados: dict[str, Any] = {
            "esquema": self._esquema_gravado(),
            "documento": self.documento,
            "pagina": self.pagina,
            "largura": self.largura,
            "altura": self.altura,
            "unidade": self.unidade,
            "numero_impresso": self.numero_impresso,
            "cabecalho": self.cabecalho.para_json() if self.cabecalho else None,
            "rodape": self.rodape.para_json() if self.rodape else None,
            "colunas": [coluna.para_json() for coluna in self.colunas],
        }
        if self._avisos_gravados():
            dados["avisos"] = [aviso.para_json() for aviso in self._avisos_gravados()]
        if self.modelo:
            dados["modelo"] = self.modelo
        if self.marca_por_palavra:
            dados["marca_por_palavra"] = True
        return dados

    @classmethod
    def de_json(cls, dados: Any) -> PaginaLida:
        """O inverso de `para_json`, e a ida-e-volta é travada por teste.

        Não aceita esquema de versão futura: um arquivo gravado por uma versão que sabe mais campos
        que esta seria lido pela metade, e "lido pela metade" é o que ninguém percebe.
        """
        if not isinstance(dados, dict):
            raise PaginaInvalida(f"esperava objeto no topo, veio {type(dados).__name__}")
        esquema = int(dados.get("esquema", ESQUEMA))
        if esquema > ESQUEMA:
            raise PaginaInvalida(f"esquema {esquema} é mais novo que o que esta versão lê ({ESQUEMA})")
        unidade = str(dados.get("unidade", "pt"))
        if unidade not in UNIDADES:
            raise PaginaInvalida(f"unidade {unidade!r} não é uma de {UNIDADES}")
        numero = dados.get("numero_impresso")
        cabecalho = dados.get("cabecalho")
        rodape = dados.get("rodape")
        return cls(
            documento=str(dados.get("documento", "")),
            pagina=int(dados.get("pagina", 0)),
            largura=float(dados.get("largura", 0.0)),
            altura=float(dados.get("altura", 0.0)),
            unidade=unidade,
            colunas=tuple(
                Coluna.de_json(c, f"colunas[{i}]") for i, c in enumerate(dados.get("colunas", []))
            ),
            cabecalho=LinhaLida.de_json(cabecalho, "cabecalho") if cabecalho else None,
            rodape=LinhaLida.de_json(rodape, "rodape") if rodape else None,
            numero_impresso=int(numero) if numero is not None else None,
            avisos=tuple(Aviso.de_json(a, f"avisos[{i}]") for i, a in enumerate(dados.get("avisos") or [])),
            modelo=str(dados.get("modelo", "") or ""),
            marca_por_palavra=dados.get("marca_por_palavra") is True,
        )

    def com_posicoes(self, posicoes: Sequence[str]) -> PaginaLida:
        """A mesma página com o campo de peças de cada diagrama preenchido, por `indice`.

        **Quem lê a posição é o OCR de diagramas do produto**, não o leitor de texto: este sabe
        onde o diagrama está (`bbox`) e aquele sabe o que há nele. Os dois numeram pelo mesmo
        detector (`indice` é a posição na lista que ele devolveu -- a chave da S-12), e é por ela
        que as duas leituras se encontram. Um `""` em `posicoes` é "não lido" e não apaga o que o
        bloco já tinha; um índice além da lista fica como está.

        Devolve **a própria página** quando nada muda, para quem compara por identidade.
        """

        def com(bloco: Bloco) -> Bloco:
            if not isinstance(bloco, BlocoDeDiagrama) or bloco.indice >= len(posicoes):
                return bloco
            nova = str(posicoes[bloco.indice] or "")
            return replace(bloco, placement=nova) if nova and nova != bloco.placement else bloco

        colunas = tuple(replace(c, blocos=tuple(com(b) for b in c.blocos)) for c in self.colunas)
        return self if colunas == self.colunas else replace(self, colunas=colunas)


def de_diagramas(
    diagramas: Sequence[tuple[float, float, float, float]],
    *,
    pagina: int = 0,
    largura: float = 0.0,
    altura: float = 0.0,
    unidade: str = "pt",
    documento: str = "",
    confiancas: Sequence[float] = (),
    placements: Sequence[str] = (),
) -> PaginaLida:
    """A `PaginaLida` de uma página **só de diagramas** -- o que a interface recebe hoje.

    Existe para a equivalência ser verificável em vez de afirmada: uma página sem texto tem de
    produzir uma `PaginaLida` com os mesmos diagramas, na mesma ordem, e é isso que o teste
    `test_a_pagina_so_de_diagramas_equivale_ao_de_hoje` compara. É também a ponte pela qual a aba
    de texto mostra algo num livro que ainda não passou pelo OCR de texto.
    """
    blocos = tuple(
        BlocoDeDiagrama(
            indice=i,
            bbox=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
            confianca=float(confiancas[i]) if i < len(confiancas) else 1.0,
            placement=str(placements[i]) if i < len(placements) else "",
        )
        for i, b in enumerate(diagramas)
    )
    colunas = (Coluna(indice=0, blocos=blocos, bbox=_envolver([b.bbox for b in blocos])),) if blocos else ()
    return PaginaLida(
        documento=documento,
        pagina=pagina,
        largura=largura,
        altura=altura,
        unidade=unidade,
        colunas=colunas,
    )


__all__ = [
    "AVISOS",
    "AVISOS_DA_SESSAO",
    "CACHE_NAO_GRAVADO",
    "CAMADA_NA_FOLHA",
    "CAMADA_RECUSADA",
    "ESQUEMA",
    "ESQUEMA_DOS_AVISOS",
    "FOLHA_NAO_LIDA",
    "GRAVAR_FORMATO_NOVO",
    "LEIAUTE_DE_RESERVA",
    "LEITOR_INDISPONIVEL",
    "LEITURA_PARCIAL",
    "ORDEM_DE_CONFIANCA",
    "PROCEDENCIAS",
    "UNIDADES",
    "Aviso",
    "Bloco",
    "BlocoDeDiagrama",
    "BlocoDeTabela",
    "BlocoDeTarja",
    "BlocoDeTexto",
    "Coluna",
    "Diagrama",
    "Elemento",
    "LinhaLida",
    "PaginaInvalida",
    "PaginaLida",
    "Procedencia",
    "bloco_de_json",
    "de_diagramas",
    "menos_confiavel",
    "procedencia_gravada",
    "remapear_com_valor",
    "trechos_de_confianca",
    "trechos_de_procedencia",
    "sequencia_de_leitura",
]
