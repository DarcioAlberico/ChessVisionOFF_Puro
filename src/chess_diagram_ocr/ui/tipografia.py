"""A escala de fontes do produto, num lugar só — papéis, não números (S-149).

**O que havia antes.** Segoe UI 9 em toda a janela: título de grupo, rótulo de campo, dado e
barra de status com o mesmo tamanho e o mesmo peso. Uma tela sem hierarquia nenhuma para o olho
seguir — tudo igualmente importante é o mesmo que nada importante.

E havia um caso pior que uniformidade. **A FEN é o dado central deste produto**, e ela aparecia
em fonte proporcional. Em proporcional `1`, `l` e `I` têm larguras diferentes, `8/8/8` não
alinha com o `8/8/8` da linha de baixo, e comparar duas leituras da mesma posição — que é a
tarefa da aba Revisão e da segunda opinião da S-66 — passa a exigir contar caractere com o dedo
na tela. O projeto já tinha monoespaçada em dois lugares (`Consolas 10`, cravada) e não a tinha
onde ela decide alguma coisa.

**Este módulo é o irmão do `ui/tokens.py`, e pela mesma razão.** Sem `tkinter` aqui: a escala é
função pura de um tamanho-base, afirmável em 9, 10 e 12 sem abrir janela. Quem lê a
`TkDefaultFont` do sistema e entrega o resultado aos painéis é `ui/theme.py`, que já é o módulo
que sabe de aparência aplicada.

**Derivada, e não cravada.** Os tamanhos saem da `TkDefaultFont`: quem aumenta a fonte do
Windows aumenta a do programa junto. Uma escala de números fixos ignora essa configuração — e
ignorá-la é o mesmo defeito de DPI da S-148 num lugar menor.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = [
    "AUXILIAR",
    "CORPO",
    "DADO",
    "DEGRAUS",
    "MONOESPACADAS_PREFERIDAS",
    "PAPEIS_DE_FONTE",
    "TITULO",
    "escala",
    "familia_monoespacada",
    "fonte",
]

TITULO = "TITULO"
"""Título de grupo (`LabelFrame`) e cabeçalho de seção: um degrau acima, e em negrito.

Os dois canais juntos de propósito. Só o tamanho, e a diferença de 1 pt não se vê; só o
negrito, e o título compete com o rótulo em vez de mandar nele."""

CORPO = "CORPO"
"""Rótulo, botão, texto de linha. O Segoe UI 9 de hoje, e o que a escala inteira referencia."""

AUXILIAR = "AUXILIAR"
"""Texto secundário: contagem, procedência, linha do motor, barra de status.

Já tinha cor própria desde a S-145 (`TEXTO_SECUNDARIO`) e não tinha tamanho — o que fazia a
hierarquia depender só de contraste, que é o canal mais frágil dos dois."""

DADO = "DADO"
"""**Monoespaçada**: FEN, coluna de FEN, linha de PGN, caminho de arquivo.

O papel existe pelo que a proporcional faz com estes quatro, e não por estilo: `rn1qkbnr` e
`rnbqkbnr` têm a mesma largura em monoespaçada e larguras diferentes em proporcional. Comparar
duas leituras é alinhar duas linhas, e alinhar exige largura igual por caractere."""

PAPEIS_DE_FONTE: tuple[str, ...] = (TITULO, CORPO, AUXILIAR, DADO)
"""Todos os papéis. Existe para o teste afirmar que a resolução é **total**."""

DEGRAUS: dict[str, int] = {
    TITULO: +1,
    CORPO: 0,
    AUXILIAR: -1,
    DADO: 0,
}
"""Quantos pontos cada papel fica **acima ou abaixo** da `TkDefaultFont` do sistema.

Quatro papéis e três tamanhos: `DADO` tem o tamanho do corpo porque ele não é ênfase, é outra
**família** — aumentá-lo faria a FEN gritar numa tela onde ela já ocupa a linha inteira.

A escala é curta de propósito. Três degraus separados por 1 pt bastam para o olho ordenar
título, corpo e apoio numa janela densa; uma escala tipográfica de razão 1,25 -- que é o que se
usa em página web -- daria 7, 9, 11 e faria o auxiliar ficar ilegível a 100% de DPI."""

MINIMO_LEGIVEL = 7
"""Nenhum papel desce daqui, mesmo que a fonte do sistema esteja em 7.

O piso não é gosto: abaixo de 7 pt o Windows deixa de aplicar *hinting* na Segoe UI e as
hastes de `l`, `i` e `1` colapsam. Numa janela cujo trabalho é distinguir `1` de `l` numa FEN,
esse é exatamente o caractere que não pode colapsar."""


MONOESPACADAS_PREFERIDAS = ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Menlo", "Liberation Mono")
"""Monoespaçadas em ordem de preferência, antes de aceitar a que o Tk indicar.

**Por que não confiar direto na `TkFixedFont`.** No Windows ela resolve para **Courier New** —
uma fonte de máquina de escrever, de hastes finas, desenhada para impressão em 1955. Numa FEN
de 70 caracteres na tela ela é justamente onde `1` e `l` voltam a se parecer, que é o defeito
que a monoespaçada veio corrigir.

Consolas vem primeiro porque acompanha o Windows desde o Vista, tem zero cortado e distingue
`1`, `l` e `I` por desenho e não por largura. As outras cobrem Linux e macOS. `Courier New`
**não** está na lista de propósito: se nenhuma daqui existir, a reserva é a que o Tk indicar,
e aí ela entra por ser o que o sistema tem — não por ter sido escolhida."""


def familia_monoespacada(disponiveis: Iterable[object], reserva: str) -> str:
    """A melhor monoespaçada que este sistema tem, ou a `reserva` do Tk. Pura.

    `disponiveis` é o que `tkinter.font.families()` devolveu; qualquer iterável de nomes serve,
    e é o que permite testar a escolha em três sistemas diferentes sem ter os três.
    """
    try:
        instaladas = {str(nome).strip().casefold() for nome in disponiveis}
    except TypeError:  # pragma: no cover - Tk que não responde a lista de famílias
        return reserva
    for nome in MONOESPACADAS_PREFERIDAS:
        if nome.casefold() in instaladas:
            return nome
    return reserva


def escala(base: int) -> dict[str, int]:
    """O tamanho em pontos de cada papel, dado o tamanho-base do sistema.

    Função pura, e é o ponto: a escala é afirmável em 9, 10 e 12 sem abrir janela e sem trocar
    a fonte do Windows. Um `base` não positivo — o que uma `TkDefaultFont` exótica devolve —
    cai no piso, porque fonte de tamanho zero não é fonte pequena, é widget vazio.
    """
    if base <= 0:
        base = MINIMO_LEGIVEL
    return {papel: max(MINIMO_LEGIVEL, base + degrau) for papel, degrau in DEGRAUS.items()}


def fonte(
    papel: str,
    *,
    base: int,
    familia: str,
    mono: str,
    negrito: bool = False,
) -> tuple[str, int] | tuple[str, int, str]:
    """A especificação de fonte do Tk para um papel: `(família, tamanho[, peso])`.

    Levanta `KeyError` para papel desconhecido, e é a mesma disciplina de `tokens.cor`: um papel
    escrito errado que caísse no corpo viraria um widget de fonte plausível e sem significado,
    que é o estado de que este módulo veio tirar a janela.

    `negrito` é do chamador e não do papel porque há um uso legítimo fora do `TITULO` — a linha
    escolhida numa lista, que precisa de peso sem mudar de nível hierárquico.
    """
    if papel not in DEGRAUS:
        raise KeyError(f"papel de fonte desconhecido: {papel!r}. Os válidos estão em PAPEIS_DE_FONTE.")
    tamanho = escala(base)[papel]
    nome = mono if papel == DADO else familia
    return (nome, tamanho, "bold") if (negrito or papel == TITULO) else (nome, tamanho)
