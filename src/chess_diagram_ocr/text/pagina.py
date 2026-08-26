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

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from .boxes import Caixa
from .colunas import atravessa, atribuir_coluna, detectar_colunas
from .grade import Arranjo, cortes_de_fileira
from .linhas import ordem_em_faixa


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
    arranjo: Arranjo = "prosa",
) -> list[Elemento]:
    """Caixas de caractere e diagramas na ordem em que um humano os lê.

    `colunas=None` as detecta com `colunas.detectar_colunas` sobre as **caixas de caractere**:
    o diagrama não entra na projeção da calha, e não deveria -- um diagrama largo encostado na
    calha a apagaria, que é o mesmo defeito da letra do cabeçalho um nível acima.

    `arranjo="grade"` parte a página em fileiras antes de ler cada uma coluna a coluna, que é a
    ordem de uma folha de exercícios numerada atravessando as colunas (S-216). O padrão é
    `"prosa"`, e **não há detecção automática**: a direção da grade é constante por livro e sai da
    numeração impressa, não da geometria da página.
    """
    elementos: list[Elemento] = [*caixas, *diagramas]
    if not elementos:
        return []

    if colunas is None:
        colunas = detectar_colunas(caixas) if caixas else []
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

Procedencia = Literal["camada", "glifo", "rapidocr", "humano"]
"""De onde saiu o texto deste bloco.

`camada` é a camada de texto do PDF -- não é palpite, é o que o editor escreveu. `glifo` é o
classificador da Fase 29. `rapidocr` é o motor de fora, que já existia na S-43. `humano` é
correção à mão, e é a única procedência que uma releitura não tem direito de apagar.
"""

PROCEDENCIAS: tuple[Procedencia, ...] = ("camada", "glifo", "rapidocr", "humano")
"""Os valores aceitos, e é só isso que esta tupla é: o conjunto que `de_json` cobra.

**A ordem aqui não significa nada, e dizer que significava foi um defeito.** A primeira versão
afirmava no docstring que ela era "crescente de quanto se confia", e `BlocoDeTexto.de_linhas`
tirava a pior procedência com um `min` sobre o índice -- que devolvia `camada`, a **melhor** das
quatro. Um parágrafo com uma linha adivinhada saía marcado como registro, que é exatamente o
contrário do que o campo existe para dizer. Quem responde essa pergunta agora é
`ORDEM_DE_CONFIANCA`, que é uma tupla separada porque a resposta merecia ser escrita, e não
deduzida da ordem em que alguém digitou quatro nomes."""

ORDEM_DE_CONFIANCA: tuple[Procedencia, ...] = ("rapidocr", "glifo", "camada", "humano")
"""As mesmas quatro, da menos para a mais confiável. **Aqui a ordem é o dado.**

`humano` no topo porque é a única que uma releitura não tem direito de apagar; `camada` acima das
duas leituras porque não é leitura -- é o que o editor do PDF escreveu; e `glifo` acima de
`rapidocr` porque é o motor de casa, calibrado (S-205) e medido neste acervo, enquanto o outro
entra sem calibração. Essa última é a única das três que é escolha e não fato, e é por isso que
está escrita."""


def menos_confiavel(procedencias: Sequence[Procedencia]) -> Procedencia:
    """A pior das procedências dadas, por `ORDEM_DE_CONFIANCA`. `camada` quando não há nenhuma.

    É o que decide a procedência de um bloco a partir das linhas dele, e a regra é a mesma da
    confiança: **um bloco vale o que vale o pior pedaço dele.**
    """
    if not procedencias:
        return "camada"
    return min(procedencias, key=ORDEM_DE_CONFIANCA.index)

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

    def para_json(self) -> dict[str, Any]:
        return {
            "texto": self.texto,
            "bbox": list(self.bbox),
            "confianca": self.confianca,
            "procedencia": self.procedencia,
            "negrito": self.negrito,
            "italico": self.italico,
        }

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
        )


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
            "procedencia": self.procedencia,
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
            "procedencia": self.procedencia,
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
            "procedencia": self.procedencia,
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
            "procedencia": self.procedencia,
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
    """Uma faixa vertical da página, com os blocos dela em ordem de leitura."""

    indice: int = 0
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


ESQUEMA = 1
"""Versão do formato de `para_json`. Sobe quando um campo muda de significado, não quando nasce.

Campo novo com padrão é compatível nos dois sentidos e não paga versão -- é a mesma regra do
`char_meta.json` da S-179."""


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

    # ---------------------------------------------------------------------------- serialização

    def para_json(self) -> dict[str, Any]:
        return {
            "esquema": ESQUEMA,
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
        )


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
    "ESQUEMA",
    "ORDEM_DE_CONFIANCA",
    "PROCEDENCIAS",
    "UNIDADES",
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
    "sequencia_de_leitura",
]
