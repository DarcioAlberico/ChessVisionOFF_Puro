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
from dataclasses import dataclass

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


__all__ = ["Diagrama", "Elemento", "sequencia_de_leitura"]
