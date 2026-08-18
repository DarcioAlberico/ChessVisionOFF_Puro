"""Como um número vira texto na tela, e a precisão que ele não tem (S-169).

**Dois defeitos com a mesma raiz: a tela mostra o que a estrutura guarda.**

*Precisão falsa.* A fila de revisão mostrava prioridade com uma casa decimal — `1623.8`,
`1617.2`, `1135.5` — num número que ninguém compara nesse detalhe. A casa decimal é ruído com
aparência de exatidão: ela sugere que 1623,8 e 1623,7 são coisas diferentes, e não são. E a
confiança aparecia como `0.082`, num programa que fala de confiança em porcentagem em todo
outro lugar.

*Dado cru.* A coluna "Lado" do Dataset publicava `w`, `b` e `—` — as letras do CSV. O
`ui/strings.py` existe desde a S-04 justamente para "brancas" ter um nome só, e a tabela
mostrava a letra do arquivo.

**Formatar é da apresentação; ordenar é do dado.** É a regra que este módulo existe para
segurar, e o defeito que ela previne é clássico: ordenar pela string formatada põe `1000` antes
de `999`, e `9,9%` antes de `82,0%`. Toda função aqui devolve **texto**, e nenhuma entra no
caminho de comparação.

Sem `tkinter`: são funções de valor para string, afirmáveis com valor típico, zero, negativo e
ausente — que são exatamente os quatro casos em que um formatador erra.
"""

from __future__ import annotations

from . import strings

__all__ = [
    "AUSENTE",
    "confianca",
    "inteiro",
    "lado_a_jogar",
    "porcentagem",
    "prioridade",
    "texto_ou_ausente",
]

AUSENTE = "—"
"""O travessão de "esta linha não tem esse dado".

Um só, e não o `""` de um lugar com o `-` de outro: célula vazia se lê como falha de carga, e
duas grafias de ausência fazem parecer que são duas ausências diferentes."""


def texto_ou_ausente(valor: object) -> str:
    """Texto, ou o travessão quando não há nada. É o piso de toda coluna de texto."""
    texto = "" if valor is None else str(valor).strip()
    return texto or AUSENTE


def inteiro(valor: float | int | None) -> str:
    """Um número sem casa decimal, com separador de milhar em pt-BR (`1.624`).

    O separador não é enfeite: `1623` e `16234` têm larguras parecidas e magnitudes de ordem
    diferente, e numa coluna alinhada à direita (S-153) o ponto é o que se lê antes do dígito.
    """
    if valor is None:
        return AUSENTE
    return f"{round(float(valor)):,}".replace(",", ".")


def prioridade(valor: float | None) -> str:
    """A prioridade da fila de revisão, **sem a casa decimal** (S-169).

    Ela dizia `1623.8`. Ninguém compara prioridade nessa resolução -- a fila é lida de cima para
    baixo, e a única pergunta é "qual vem antes". Uma casa decimal ali é ruído com aparência de
    exatidão, e o custo dela é fazer duas linhas praticamente iguais parecerem distintas.
    """
    return inteiro(valor)


def porcentagem(fracao: float | None, *, casas: int = 1) -> str:
    """Uma fração de 0 a 1 como porcentagem em pt-BR (`8,2%`).

    Vírgula decimal porque o resto da interface é pt-BR, e o mesmo número escrito com ponto num
    lugar e vírgula noutro é o defeito que a S-04 mediu no vocabulário, aplicado a número.
    """
    if fracao is None:
        return AUSENTE
    return f"{float(fracao) * 100:.{casas}f}".replace(".", ",") + "%"


def confianca(valor: float | None) -> str:
    """A confiança mínima de um diagrama, em porcentagem.

    Era `0.082` na fila e `8%` na barra de status do mesmo programa. Duas grafias do mesmo
    número obrigam quem lê a converter de cabeça para comparar as duas telas.
    """
    return porcentagem(valor)


def lado_a_jogar(codigo: str | None) -> str:
    """`w`/`b` como a interface os chama. Qualquer outra coisa vira o travessão.

    O código do CSV não é para ser lido: ele é do arquivo. Publicá-lo na tela obriga o usuário
    a saber que `w` quer dizer brancas -- o que é óbvio em inglês e não é o idioma da janela.
    """
    return strings.SIDE_LABELS.get(str(codigo or "").strip().lower(), AUSENTE)
