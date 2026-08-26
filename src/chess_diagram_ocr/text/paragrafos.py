"""Onde um parágrafo termina e outro começa (S-192).

Ordem não é parágrafo. Saber que a linha 12 vem antes da 13 não diz onde um parágrafo acaba, e
sem isso o texto exportado é uma parede.

**Quatro regras juntas, porque nenhuma sozinha cobre este material.** A prosa usa recuo; a
notação em negrito entre parágrafos usa espaço em branco; nenhuma das duas vê o fim da coluna --
lá o salto vertical é **negativo**, porque a leitura volta ao topo da página --; e há livro em que
a notação nem espaço em branco usa: o que a separa da prosa é só o peso da fonte.

    recuo    a linha começa mais à direita que a margem da coluna
    salto    o vão até a linha anterior passa de uma altura de linha e meia
    troca    a coluna mudou
    peso     o negrito mudou, e os dois lados são conhecidos

## O peso, e a folha 51 do Dvoretsky que o mediu

Naquela página a prosa e a notação se alternam num entrelinhamento **constante** -- 19 pt de uma
linha à seguinte, dentro do parágrafo e entre parágrafos, sem distinção. O recuo existe (29 pt de
margem, 40 pt de recuo), mas ali ele não é visto por outra razão, e o salto não existe. Sem a
quarta regra, cinco dos oito parágrafos de texto da folha saíam grudados:

    The only saving line starts with a paradoxical move that forces the black pawn to advance.
    1.Rc8!! b5                                        <- em negrito, e no mesmo bloco do de cima

E o estrago não para no corte. `BlocoDeTexto.de_linhas` só declara o peso do bloco quando **todas**
as linhas concordam, então o parágrafo grudado sai `negrito=None` -- e a aba passa a dizer *"o
livro não informa"* numa página em que o livro informa cada lance. Ver `text/negrito.py`.

**A regra só vale entre dois pesos conhecidos.** `None` de um lado não abre parágrafo nenhum: nos
26 livros do acervo cuja camada não registra peso, toda linha é `None`, e a regra fica inerte --
que é o que se quer de uma régua que não tem o que medir.

Medido em 2026-08-25 sobre 96 folhas dos 12 livros do acervo que registram peso: 94 dos 1.557
blocos de texto (6,0%) misturavam peso dentro de si, e todos os 94 eram parágrafo indevidamente
grudado -- nenhum era um parágrafo real que a regra fosse partir ao meio.

## A margem é por coluna, e a mediana da página não serve

É a lição da F61 no projeto de origem: a mediana das esquerdas de uma página de duas colunas não
é margem nenhuma. Metade das linhas começa em 122 e metade em 893, e a mediana cai num dos dois
-- com ela, ou a coluna da direita inteira parece recuada (cada linha vira um parágrafo) ou a da
esquerda perde todos os recuos que tem.

**E a métrica é da página, não do trecho.** São medianas, e a mediana de cinco linhas entre dois
diagramas não diz onde fica a margem da coluna.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

RECUO_DE_PARAGRAFO = 0.4
"""Recuo que abre parágrafo, em alturas de linha.

**Era 0,8, e o número nunca tinha sido medido** -- ele veio com a S-192, quando referência de
parágrafo não existia. Ela existe desde a S-257, e a S-258 varreu o corte contra ela.

Medido em 2026-08-26 sobre `docs/metrics/texto_paragrafo_referencia.jsonl`, nas folhas que a
referência sabe julgar -- as lidas pela **camada de texto**, onde o sinal do fim de linha é
confiável (precisão 0,94):

    recuo   acertos  falsos  perdidos  precisão  recall      F1
     0,80        44       3        26    0,9362  0,6286  0,7521   <- o valor antigo
     0,40        48       3        22    0,9412  0,6857  0,7934
     0,30        48       3        22    0,9412  0,6857  0,7934
     0,15        48       4        22    0,9231  0,6857  0,7869

**Os dois lados melhoram**: quatro cortes certos a mais, sem um falso a mais. E o platô entre 0,20
e 0,45 é chato, que é o sinal de que o valor não está sintonizado num acaso do conjunto -- abaixo
de 0,20 a precisão começa a cair. 0,40 é o meio dele.

O valor bate com o que a S-258 tinha previsto sobre a referência de 24 folhas (F1 0,7832 -> 0,8328);
as contagens absolutas diferem porque a referência foi refeita, e o relatório da S-258 diz por quê.

**`SALTO_DE_PARAGRAFO` foi varrido junto e não mostra vão** -- ver o docstring dele.

**E a varredura achou uma coisa maior que este item.** Nas folhas lidas pelo **glifo** -- os livros
sem camada, que são a razão de o leitor existir -- a referência dá precisão de **0,43**, e nenhum
candidato de recuo se distingue de outro. `cortar` faz ali mais que o dobro de blocos que a
referência vê começos. O corte não é o problema: é que a população de "linha" que a segmentação
entrega não é a que estas regras descrevem. Está em `docs/metrics/texto_paragrafo.json`, na chave
`varredura_por_motor`, e é item próprio."""

SALTO_DE_PARAGRAFO = 0.6
"""Salto vertical extra que abre parágrafo, em alturas de linha. O corte é `1 + este valor`.

**Varrido junto com o recuo na S-258, e não mostra vão.** Baixá-lo de 0,6 para 0,3 sobe o recall e
derruba a precisão: é troca, e não ganho. Ele fica, e a varredura está em
`docs/metrics/texto_paragrafo.json` para que a afirmação continue conferível."""


@dataclass(frozen=True)
class Linha:
    """Uma linha já lida, do ponto de vista da diagramação."""

    topo: int
    esquerda: int
    altura: int
    texto: str
    coluna: int = 0
    """Em qual faixa de `colunas.detectar_colunas` esta linha está. Zero na página de coluna
    única, que é o caso em que tudo isto some."""

    negrito: bool | None = None
    """O peso da fonte desta linha, quando o livro o registra -- ver `text/negrito.py`.

    `None` é **"não se sabe"**, e é o padrão: quem monta a linha sem peso nenhum -- os testes, a
    camada de um livro que não o registra -- fica com a diagramação de três regras que sempre
    existiu. Ver "O peso" no cabeçalho."""


@dataclass(frozen=True)
class Paragrafo:
    texto: str
    linhas: tuple[Linha, ...] = field(default_factory=tuple)

    @property
    def coluna(self) -> int:
        return self.linhas[0].coluna if self.linhas else 0


QUANTIL_DA_MARGEM = 0.5
"""Que quantil das esquerdas é a margem da coluna. `0.5` é a mediana (S-257).

**O parâmetro existe porque a pergunta foi medida, e não porque alguém quis afrouxá-la.** A
suspeita era boa: a mediana morre numa diagramação de recuo de primeira linha com parágrafos
curtos -- quase metade das linhas começa no recuo, a mediana devolve o recuo no lugar da margem,
e `recuou` fica falso para a coluna inteira, em silêncio. Um quantil baixo conserta isso ali e
despedaça parágrafo em outro lugar. Qual dos dois lados pesa mais é medição, e não argumento.

Medido em 2026-08-26 contra `docs/metrics/texto_paragrafo_referencia.jsonl` -- 24 folhas de 14 livros, 1.273
linhas com referência, 323 começos de parágrafo. O relatório está em
`docs/metrics/texto_paragrafo_referencia.json`:

    quantil   acertos   falsos   perdidos   blocos
       0,10       226       25         97      484
       0,50       224       25         99      409

**Dois acertos em 323.** É a diferença inteira entre os dois candidatos sobre o que a referência
sabe julgar, com o mesmo número de falsos. Os 75 blocos a mais do quantil baixo caem quase todos
em linha que a referência não julga -- ela cobre 1.273 das 1.675 --, e por isso são cortes que
ninguém mediu, nem a favor nem contra.

E não é que os dois façam a mesma coisa: eles discordam sobre 1.952 linhas em 133 das 226 colunas
do acervo (59%). Mexem muito e empatam -- a margem da coluna não é onde o corte de parágrafo se
ganha ou se perde.

Por isso a mediana fica. É a regra 5 da SPEC_EDITOR: régua sem vão medido não entra ligada, e
isso vale igual para a troca que parecia óbvia."""


def metricas_por_coluna(
    linhas: Sequence[Linha], *, quantil: float = QUANTIL_DA_MARGEM
) -> dict[int, tuple[int, int]]:
    """`{coluna: (margem esquerda, altura de linha)}`, medidas na **página inteira**.

    Ver "A margem é por coluna" no cabeçalho. `quantil` é o parâmetro da S-257: ele existe para a
    medição poder varrer candidatos sem monkeypatch, e o padrão é o que ela mandou manter -- ver
    `QUANTIL_DA_MARGEM`.

    **A altura continua sendo a mediana**, e não segue o quantil: ela mede o corpo da fonte, que é
    simétrico por natureza -- não há "altura de primeira linha" como há recuo de primeira linha.
    """
    metricas: dict[int, tuple[int, int]] = {}
    for coluna in {linha.coluna for linha in linhas}:
        desta = [linha for linha in linhas if linha.coluna == coluna]
        esquerdas = sorted(linha.esquerda for linha in desta)
        alturas = sorted(linha.altura for linha in desta)
        posicao = min(len(esquerdas) - 1, max(0, int(len(esquerdas) * quantil)))
        metricas[coluna] = (esquerdas[posicao], alturas[len(alturas) // 2] or 1)
    return metricas


def cortar(
    linhas: Sequence[Linha],
    metricas: dict[int, tuple[int, int]] | None = None,
    *,
    recuo: float = RECUO_DE_PARAGRAFO,
    salto: float = SALTO_DE_PARAGRAFO,
) -> list[Paragrafo]:
    """Linhas -> parágrafos, pelas quatro regras do cabeçalho.

    `metricas=None` as tira destas mesmas linhas, que é o que serve a quem chama com a página
    toda. Quem chama com um trecho passa as da página -- ver o cabeçalho.

    **`recuo` e `salto` são parâmetros pelo mesmo motivo que `quantil` é** (S-257): a medição
    varre candidatos, e varrer com monkeypatch mede um módulo remendado em vez do que roda. Os
    padrões são os valores em uso, então quem não os passa não muda de comportamento.
    """
    if not linhas:
        return []
    if metricas is None:
        metricas = metricas_por_coluna(linhas)

    paragrafos: list[Paragrafo] = []
    atual: list[Linha] = []
    anterior: Linha | None = None
    for linha in linhas:
        margem, altura = metricas.get(linha.coluna, (linha.esquerda, linha.altura or 1))
        trocou = anterior is not None and linha.coluna != anterior.coluna
        recuou = linha.esquerda > margem + altura * recuo
        saltou = (
            anterior is not None
            and not trocou
            and linha.topo - anterior.topo > altura * (1 + salto)
        )
        # **Só entre dois pesos conhecidos.** `None` de um lado é "não se sabe", e não se abre
        # parágrafo sobre o que não se sabe -- ver "O peso" no cabeçalho.
        pesou = (
            anterior is not None
            and linha.negrito is not None
            and anterior.negrito is not None
            and linha.negrito != anterior.negrito
        )
        if atual and (recuou or saltou or trocou or pesou):
            paragrafos.append(_fechar(atual))
            atual = []
        atual.append(linha)
        anterior = linha
    if atual:
        paragrafos.append(_fechar(atual))
    return paragrafos


def _fechar(linhas: list[Linha]) -> Paragrafo:
    return Paragrafo(texto=" ".join(linha.texto for linha in linhas), linhas=tuple(linhas))


__all__ = [
    "RECUO_DE_PARAGRAFO",
    "SALTO_DE_PARAGRAFO",
    "Linha",
    "Paragrafo",
    "cortar",
    "metricas_por_coluna",
]
