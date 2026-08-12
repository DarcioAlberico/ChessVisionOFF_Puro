"""Duas leituras do mesmo diagrama, e as casas em que elas discordam (S-66).

**O problema que isto resolve.** Conferir um diagrama é olhar 64 casas. Quem captura um
livro novo faz isso diagrama a diagrama, e é o custo humano que limita quantas amostras
entram no `labels.csv` -- não o tempo de máquina, que é de décimos de segundo.

Duas leituras independentes do mesmo recorte cortam esse custo, porque **onde as duas
concordam quase nunca há erro**, e o que sobra para o olho humano é a diferença.

**Medido no `Niemeijer - Zwarte Magie (1945)`**, 20 diagramas de 5 páginas, comparando o
classificador local com o `Chess_diagram_to_FEN` (leitor externo, ver `tsoj_reader`):

| | |
|---|---|
| concordância total (0 casas divergentes) | 0 / 20 |
| **mediana de casas em desacordo** | **4,5** |
| até 5 casas em desacordo | 11 / 20 |
| pior caso | 41 |

E em três diagramas cuja posição foi conferida à mão, casa a casa, o conjunto em desacordo
era **exatamente** o conjunto de erros do leitor local -- 4 de 4, 23 de 23, 41 de 41. Nenhum
erro fora dele. Nesse livro, olhar 4,5 casas em vez de 64 não perdia nada.

**O que este módulo não afirma.** Que a segunda leitura está certa. Ela erra também: no mesmo
conjunto, 2 dos 20 saíram com dois reis brancos e nenhum preto. Por isso a saída daqui é uma
*marcação*, não uma correção automática -- quem decide continua sendo quem olha. E o número
acima vale para **um livro de um regime**; num acervo em que o leitor local já vai a 1,000 de
confiança, a mesma marcação pode apontar casa certa. Ver `disputed_squares` sobre por que
mesmo assim ela não custa nada nesse caso.

**Por que aqui e não no painel.** Pela regra que organizou a Fase 6: o que dá para testar não
mora na janela. Comparar duas colocações e contar divergências é aritmética, e merece teste
que não precise abrir um Tk.
"""

from __future__ import annotations

from dataclasses import dataclass

from .fen_utils import labels_from_fen, square_name

COLLAPSE_DISPUTED = 15
"""Acima de tantas casas em desacordo, as duas leituras não estão discordando -- uma desabou.

Não é limiar de qualidade, é de **modo de revisão**. Com 3 ou 4 casas marcadas o olho vai
direto nelas e confirma o resto de graça. Com 41 marcadas não sobra "resto": a leitura de
base não serve de âncora e sai mais barato conferir a segunda leitura inteira, do zero.

O valor vem da distribuição medida no Niemeijer, que é bimodal e com o vale largo: 11 dos 20
diagramas ficaram em 5 casas ou menos e 5 ficaram em 21 ou mais. O maior do grupo de baixo é
**12** e o menor do grupo de cima é **21** -- não há nenhum diagrama entre os dois. Um limiar
posto dentro de um vão vazio não precisa de calibração fina por livro.
"""


def disputed_squares(placement_a: str, placement_b: str) -> tuple[int, ...]:
    """Índices em ordem de leitura (0 = a8) das casas em que as duas colocações diferem.

    Aceita FEN completa ou só o campo de peças: `labels_from_fen` já corta no primeiro
    espaço. É de propósito -- as duas leituras chegam de fontes diferentes e uma delas
    costuma trazer ` w - - 0 1` grudado, e exigir que o chamador normalize seria transferir
    para ele um cuidado que esta função pode ter sozinha.

    **Custo quando a marcação erra.** Numa página em que o leitor local já está certo, uma
    casa marcada à toa custa um olhar e nada mais: o valor da casa não muda, a procedência
    não muda, e nada é gravado. O erro caro é o inverso -- casa errada **não** marcada --, e
    esse só acontece quando as duas leituras erram igual, que é o que a independência delas
    torna raro.
    """
    a = labels_from_fen(placement_a)
    b = labels_from_fen(placement_b)
    return tuple(index for index, (x, y) in enumerate(zip(a, b, strict=True)) if x != y)


@dataclass(frozen=True)
class SecondOpinion:
    """O que a segunda leitura viu, e onde ela contradiz a primeira."""

    placement: str
    """A colocação que o segundo leitor devolveu, só o campo de peças."""

    baseline: str
    """A colocação que estava no editor -- a leitura do modelo local."""

    reader: str
    """Quem leu, para a barra de status e o log. Não é o nome do usuário."""

    disputed: tuple[int, ...]
    """Casas em desacordo, em ordem de leitura."""

    @property
    def agreement(self) -> float:
        """Fração das 64 casas em que as duas concordam, em 0..1."""
        return (64 - len(self.disputed)) / 64.0

    @property
    def collapsed(self) -> bool:
        """Uma das duas desabou: rever casa a casa não compensa. Ver `COLLAPSE_DISPUTED`."""
        return len(self.disputed) > COLLAPSE_DISPUTED

    @property
    def disputed_names(self) -> tuple[str, ...]:
        return tuple(square_name(index) for index in self.disputed)

    def describe(self) -> str:
        """Uma linha em pt-BR para a barra de status.

        Nomeia as casas quando são poucas, porque aí a frase substitui a busca visual; e para
        de nomear quando são muitas, porque uma lista de 41 casas não é informação, é ruído.
        """
        if not self.disputed:
            return f"{self.reader} leu a mesma posição: as 64 casas batem."
        if self.collapsed:
            return (
                f"{self.reader} leu {len(self.disputed)} casas diferentes das 64 -- as duas "
                f"leituras não se parecem. Confira a posição inteira."
            )
        casas = ", ".join(self.disputed_names)
        return f"{self.reader} discorda em {len(self.disputed)} casa(s): {casas}. Confira só elas."


def compare(baseline: str, placement: str, *, reader: str) -> SecondOpinion:
    """Constrói o parecer. `ValueError` se qualquer das colocações não tiver 8×8 casas."""
    return SecondOpinion(
        placement=placement.split(" ")[0],
        baseline=baseline.split(" ")[0],
        reader=reader,
        disputed=disputed_squares(baseline, placement),
    )
