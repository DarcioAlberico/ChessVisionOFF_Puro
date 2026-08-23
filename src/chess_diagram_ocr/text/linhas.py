"""Onde uma linha de texto acaba e a próxima começa (S-187).

**A linha sai da ordem de leitura, e não da geometria da página.** É a decisão central deste
módulo, e ela é o oposto do que a intuição sugere. Quem já resolveu coluna, elemento transversal
e pilha girada é a ordenação; refazer isso aqui por coordenada desfaria o trabalho dela e
voltaria a intercalar as duas colunas de um livro de duas colunas.

O que sobra é cortar a sequência em três situações -- ela **desce**, **volta para a esquerda** ou
**sobe** -- e cada uma das três tem uma cicatriz medida atrás:

**Subir é o fim de uma coluna.** Ao passar da última linha da coluna da esquerda para a primeira
da direita, a sequência não desce (sobe para o topo da página) e não volta para a esquerda (vai
para bem mais à direita). Sem esta terceira regra as duas linhas saem coladas numa só -- medido
na página 118 do Nunn, o fim de `...followed by ♔f7.` saía preso ao cabeçalho `ROOK ENDINGS`, que
é a primeira coisa da coluna vizinha.

**Subir e descer são contra a linha inteira, não contra a caixa anterior.** Contra a anterior, a
régua corta *dentro* da linha: a vírgula mora na base e a letra seguinte começa acima do topo
dela, então `Gurgenidze,` e `1981` viravam duas linhas. E na outra direção, o apóstrofo e o hífen
-- caixas curtas plantadas no alto -- faziam a letra seguinte parecer ter descido uma linha.
Medido nas 10 páginas rotuladas, isso era **69 cortes no meio de linha em 532 (13%)**, contra 15
em 476 depois; no arquivo exportado é a prosa picada em três parágrafos.

**A caixa curta não fixa a base.** Uma linha que *começa* com aspas teria a régua no fundo das
aspas, e o defeito voltaria pela porta dos fundos. Enquanto só houver caixa curta na linha,
`desceu` não opina -- quem corta ali é o `voltou`, que é o fim de linha de verdade e dispara nos
mesmos pontos.

**A pilha girada fica de fora, e não é detalhe.** A 90° o texto se lê de baixo para cima, então
subir ali é o andamento normal da linha; cortar faria de cada letra uma linha. Quem preenche o
ângulo é a S-197, e até lá ele é sempre 0 -- a guarda está escrita porque escrevê-la depois
significaria reabrir este arquivo com a S-197 já dentro dele.
"""

from __future__ import annotations

from collections.abc import Sequence

from .boxes import Caixa

CAIXA_CURTA = 0.65
"""Abaixo desta fração da altura mediana, a caixa não fixa a base da linha.

É o apóstrofo, a aspa, o hífen, o ponto e a vírgula -- as caixas que não têm altura de letra e
por isso não dizem onde a linha se apoia."""

FOLGA_DE_LINHA = 0.25
"""Quanto a caixa nova precisa passar da base para ter descido de linha, em alturas medianas.

**Existe porque a vírgula raspa a base.** Ela desce um fio abaixo da linha de base, então o
centro dela fica meio pixel abaixo do fundo das letras -- e sem folga isso é "desceu uma linha".
Medido nas 10 páginas rotuladas, os 26 cortes que sobravam se separam em dois montes e entre eles
não há nada:

    vírgula raspando a base       0,02          (11 casos, todos vírgula)
    quebra de linha de verdade    0,66 - 4,88   (15 casos)
"""

FOLGA_DE_COLUNA = 1.0
"""Quanto a caixa nova precisa subir acima do topo da linha para ser a coluna vizinha.

**A `FOLGA_DE_LINHA` não serve aqui, e o motivo é físico.** Quem dispara o `subiu` sem ser troca
de coluna é a caixa curta plantada na altura de ascendente -- o apóstrofo de `can't` chegando
depois de `can`, que é todo altura de x. Ela sobe o vão entre as duas alturas, e esse vão chega a
~0,4 altura mediana em fonte comum: mais que os 0,25 que bastam para a vírgula.

Medido, o apóstrofo sobe 0,08-0,14 alturas medianas e a troca de coluna sobe 66-104. O vão entre
os dois montes é de 470x, e é por isso que o valor não é delicado."""

VAO_DE_ESPACO = 0.42
"""Vão horizontal, em larguras medianas da linha, a partir do qual entra um espaço.

Não veio de tabela, e a ressalva fica registrada: é o valor que separa palavra de palavra nas
fontes deste acervo, e quem o medir de verdade é quem precisar de espaçamento certo -- o texto
que sai daqui é consumido por `parse_context`, que já normaliza espaço."""


def _mediana(valores: list[int]) -> float:
    ordenados = sorted(valores)
    return float(ordenados[len(ordenados) // 2]) if ordenados else 0.0


FOLGA_DA_BANDA = 0.2
"""Quanto o centro da caixa nova pode passar do fundo médio da banda, em alturas dela própria."""


def bandas(caixas: Sequence[Caixa]) -> list[list[Caixa]]:
    """Agrupa por sobreposição vertical, de cima para baixo. **Independente da ordem de leitura.**

    É o agrupamento que a S-190 precisa e a ordem de leitura não pode dar: a calha se acha
    projetando linhas no eixo x, e a ordem de leitura depende da calha. Este é o lado geométrico
    do ovo e da galinha -- ele não sabe de coluna, e não precisa saber.

    **O fundo da banda sai só das caixas altas** (F64 no projeto de origem). O apóstrofo mora na
    altura de ascendente e a ordenação é por `y1`, então ele chega antes da letra que segue e
    **abre a banda sozinho**; com o fundo cravado na altura de x, nenhuma letra da linha consegue
    entrar. Medido lá nas 10 páginas rotuladas: 7 bandas feitas só de caixa curta, todas aspas ou
    apóstrofo, e no livro exportado isso é `White's` saindo `' White s`.

    Enquanto a banda só tiver caixa curta ela não tem fundo, e a próxima entra sem discussão --
    que é o certo: uma aspa não estabelece linha de base.
    """
    if not caixas:
        return []

    curto = (_mediana([c.altura for c in caixas]) or 1.0) * CAIXA_CURTA

    grupos: list[list[Caixa]] = []
    atual: list[Caixa] = []
    altos: list[int] = []  # os fundos do que já é letra na banda

    for caixa in sorted(caixas, key=lambda c: c.y1):
        if atual and altos:
            fundo = sum(altos) / len(altos)
            if (caixa.y1 + caixa.y2) / 2 > fundo + caixa.altura * FOLGA_DA_BANDA:
                grupos.append(atual)
                atual, altos = [], []
        atual.append(caixa)
        if caixa.altura >= curto:
            altos.append(caixa.y2)

    if atual:
        grupos.append(atual)
    return grupos


def ordem_em_faixa(caixas: Sequence[Caixa]) -> list[Caixa]:
    """Ordem de leitura **de uma faixa**: por banda, e por `x` dentro dela.

    **Correto para faixa, e insuficiente para página.** Uma faixa de legenda não tem coluna --
    é o retângulo em volta de um diagrama --, então agrupar por banda e ordenar por `x` é a
    ordem de leitura de verdade ali. Uma página tem coluna, e quem a resolve é
    `pagina.sequencia_de_leitura` (S-193).
    """
    return [caixa for banda in bandas(caixas) for caixa in sorted(banda, key=lambda c: c.x1)]


def quebrar_em_linhas(caixas: Sequence[Caixa]) -> list[list[Caixa]]:
    """Corta uma sequência **já em ordem de leitura** em linhas. Ver o cabeçalho."""
    if not caixas:
        return []

    mediana = _mediana([c.altura for c in caixas]) or 1.0
    curto = mediana * CAIXA_CURTA
    folga = mediana * FOLGA_DE_LINHA
    folga_acima = mediana * FOLGA_DE_COLUNA

    linhas: list[list[Caixa]] = []
    atual: list[Caixa] = []
    base: int | None = None  # o fundo do que já é letra nesta linha
    for caixa in caixas:
        if atual:
            anterior = atual[-1]
            desceu = base is not None and (caixa.y1 + caixa.y2) / 2 > base + folga
            voltou = caixa.x1 < anterior.x1 - anterior.altura
            girado = bool(caixa.angulo or anterior.angulo)
            subiu = not girado and caixa.y2 < min(c.y1 for c in atual) - folga_acima
            if desceu or voltou or subiu:
                linhas.append(atual)
                atual, base = [], None
        atual.append(caixa)
        if caixa.altura >= curto:
            base = caixa.y2 if base is None else max(base, caixa.y2)
    if atual:
        linhas.append(atual)
    return linhas


def texto_da_linha(linha: Sequence[Caixa], chars: Sequence[str], *, vao: float = VAO_DE_ESPACO) -> str:
    """Junta os caracteres da linha, pondo espaço onde o vão horizontal é largo o bastante."""
    if not linha or not chars:
        return ""
    largura = _mediana([c.largura for c in linha]) or 1.0
    limite = vao * largura

    partes = [chars[0]]
    for anterior, atual, char in zip(linha[:-1], linha[1:], chars[1:], strict=True):
        if atual.x1 - anterior.x2 > limite:
            partes.append(" ")
        partes.append(char)
    return "".join(partes).strip()


def envolve(linha: Sequence[Caixa]) -> tuple[float, float, float, float]:
    """O retângulo que cobre a linha inteira."""
    return (
        float(min(c.x1 for c in linha)),
        float(min(c.y1 for c in linha)),
        float(max(c.x2 for c in linha)),
        float(max(c.y2 for c in linha)),
    )


__all__ = [
    "CAIXA_CURTA",
    "FOLGA_DA_BANDA",
    "FOLGA_DE_COLUNA",
    "FOLGA_DE_LINHA",
    "VAO_DE_ESPACO",
    "bandas",
    "envolve",
    "ordem_em_faixa",
    "quebrar_em_linhas",
    "texto_da_linha",
]
