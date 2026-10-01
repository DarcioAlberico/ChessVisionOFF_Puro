"""Papel de botão → nome de estilo `ttk`, e nada mais (S-144).

**O que havia antes.** `ttkbootstrap` 2.2.0 instalado, `bootstrap-light` aplicado com sucesso,
e `grep -rn bootstyle src/ app_tkinter.py` devolvendo **zero linhas**. O sistema de design
estava pago, carregado e sem um único cliente.

O custo não é estético. "Salvar posição reconhecida" e **"Remover"** — que apaga linha do
`labels.csv`, isto é, trabalho humano — eram o mesmo botão cinza. Numa fila de cinco botões de
peso igual o olho não encontra a ação principal, e a destrutiva não pede cuidado nenhum.

**A restrição, medida nesta máquina.** Na 2.2.0 os widgets de `tkinter.ttk` não são mais
remendados para aceitar `bootstyle`:

    ttk.Button(parent, bootstyle="primary")     -> TclError: unknown option "-bootstyle"
    ttk.Button(parent, style="primary.TButton")  -> funciona

E num `Tk` **sem** `ttkbootstrap`, com o tema `vista`, `style="primary.TButton"` não levanta: o
Tk desenha o botão padrão. É o caminho que preserva o contrato de degradação de `ui/theme.py`
sem trocar a classe de nenhum widget da janela.

**Três papéis, e não quatro.** Mais que três deixa de ser hierarquia e vira paleta: se tudo tem
ênfase, nada tem. A regra de uso está em `PRIMARIO` -- **uma por barra de ações, nunca duas.**
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = [
    "DESTRUTIVO",
    "NEUTRO",
    "PRIMARIO",
    "conferir_barra",
    "conferir_tela",
    "estilo_de_botao",
    "tem_enfase",
]

PRIMARIO = "PRIMARIO"
"""A ação que o atalho de teclado também faz, e **uma por barra**.

O critério não é "a mais importante" -- é verificável: se `Ctrl+S` salva, o botão de salvar é o
primário daquela barra. Duas ênfases numa barra é o mesmo que nenhuma, e o teste não tem como
saber qual das duas era para ser; a regra amarrada ao atalho tem.
"""

DESTRUTIVO = "DESTRUTIVO"
"""Apaga trabalho humano: "Remover", "Quarentena", "Limpar os headers".

Vermelho não é decoração aqui. `labels.csv` é rótulo corrigido à mão, e a S-76 é o registro do
que custa um botão destrutivo que não parece um: 1.405 diagramas sobrescritos por um clique.
"""

NEUTRO = "NEUTRO"
"""Todo o resto. Devolve `""`, que é o estilo padrão do `ttk` -- e não um nome inventado."""

PAPEIS_DE_BOTAO: tuple[str, ...] = (PRIMARIO, DESTRUTIVO, NEUTRO)

COM_ENFASE: frozenset[str] = frozenset({PRIMARIO, DESTRUTIVO})
"""Os papéis que ganham **face** própria -- fundo saturado e letra clara sobre ele.

Existe porque a pergunta "este botão tem face de ênfase?" é feita de fora, e a resposta é daqui:
`ui/folha_de_estilo.tinta_do_papel` precisa dela para decidir em que cor o **ícone** do botão é
desenhado, e enquanto ela era uma tupla escrita no ponto de chamada, o papel estava declarado em
dois lugares. O neutro fica de fora por definição -- ele é a ausência de ênfase, e não uma
terceira face."""


def tem_enfase(papel: str) -> bool:
    """Se um botão daquele papel é desenhado com face própria. Papel desconhecido é `False`.

    Não levanta, ao contrário de `estilo_de_botao`: quem pergunta isto está escolhendo uma cor de
    desenho, e um papel novo que ainda não tenha face merece o tratamento neutro em vez de uma
    janela que não abre. Quem cobra papel escrito errado é `estilo_de_botao`, no caminho em que o
    erro é do chamador.
    """
    return papel in COM_ENFASE


_ESTILOS: dict[str, str] = {
    PRIMARIO: "primary.TButton",
    DESTRUTIVO: "danger.TButton",
    NEUTRO: "",
}


def estilo_de_botao(papel: str) -> str:
    """O nome de estilo `ttk` daquele papel. Função pura: não toca widget nem `Style`.

    Levanta `KeyError` para papel desconhecido em vez de cair no neutro: um papel escrito
    errado que virasse botão cinza é exatamente o estado de que este módulo veio tirar a
    janela, e ele voltaria sem ninguém notar.
    """
    if papel not in _ESTILOS:
        raise KeyError(f"papel de botão desconhecido: {papel!r}. Os válidos estão em PAPEIS_DE_BOTAO.")
    return _ESTILOS[papel]


def conferir_tela(papeis: Iterable[str], *, onde: str = "esta tela") -> list[str]:
    """Os excessos de ênfase de uma **tela inteira**. Pura, e **não levanta** (F9-C2, §7 item 10).

    **A regra da barra não alcançava a tela, e o crítico do ciclo 1 mediu a diferença**: cada
    barra tinha a sua ênfase e obedecia `conferir_barra`, mas a janela desenha o painel do PDF, o
    painel de campo e a aba ao mesmo tempo -- então Resultado, Estudo e Revisão saíam com **três**
    botões primários simultâneos, e as outras três abas com dois. Uma barra correta vezes três é
    uma tela errada.

    **Devolve em vez de levantar, e é a diferença de contrato com `conferir_barra`.** Aquela é
    chamada na montagem de uma barra, onde o excesso é erro de programação e tem de doer; esta é
    chamada com a janela viva, e uma janela que se recusa a abrir porque um botão está da cor
    errada troca um defeito de aparência por uma queda -- que é o contrato de degradação da S-53.
    Quem chama registra a lista; o número entra no relatório da frente.

    Levanta `KeyError` para papel desconhecido, pela mesma razão de `conferir_barra`: um papel
    escrito errado passaria a contar como neutro, e a tela com duas ênfases passaria no portão.
    """
    vistos = list(papeis)
    for papel in vistos:
        if papel not in _ESTILOS:
            raise KeyError(f"papel de botão desconhecido: {papel!r}. Os válidos estão em PAPEIS_DE_BOTAO.")
    return [papel for papel in vistos if papel == PRIMARIO][1:]


def conferir_barra(papeis: Iterable[str], *, onde: str = "esta barra") -> None:
    """Recusa uma barra de ações com mais de um `PRIMARIO` (S-446). Pura: não toca widget.

    **A regra já estava escrita em `PRIMARIO` e só era cobrada num lugar.**
    `comandos.primarios_por_grupo` a afirma por **grupo do catálogo**, e é o que trava a fila e a
    fita. Nenhuma das duas alcança uma barra montada à mão dentro de um painel -- que é
    exatamente onde a S-445 encosta -- e duas ênfases numa barra é o mesmo que nenhuma: o olho
    não tem como saber qual das duas era para ser a ação.

    **Zero primário passa, e isso é critério e não folga.** Nem toda fileira tem uma ação que o
    teclado também faz, e inventar uma para cumprir cota devolveria a barra ao estado que a
    S-144 mediu -- cinco botões de peso igual, agora com um azul arbitrário no meio.

    Levanta `ValueError` para o excesso e `KeyError` para papel desconhecido, pela mesma razão de
    `estilo_de_botao`: um papel escrito errado que fosse ignorado aqui passaria a contar como
    neutro, e a barra com duas ênfases passaria no teste.
    """
    vistos = list(papeis)
    for papel in vistos:
        if papel not in _ESTILOS:
            raise KeyError(f"papel de botão desconhecido: {papel!r}. Os válidos estão em PAPEIS_DE_BOTAO.")
    quantos = vistos.count(PRIMARIO)
    if quantos > 1:
        raise ValueError(
            f"{onde} declara {quantos} ações primárias, e o máximo é uma. "
            "Duas ênfases numa barra é o mesmo que nenhuma -- ver `estilos.PRIMARIO`."
        )
