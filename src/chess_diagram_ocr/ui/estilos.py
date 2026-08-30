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
    "PAPEIS_DE_BOTAO",
    "PRIMARIO",
    "conferir_barra",
    "estilo_de_botao",
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
