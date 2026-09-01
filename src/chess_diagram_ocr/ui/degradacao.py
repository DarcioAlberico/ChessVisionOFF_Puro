"""O contrato de degradação da aparência: cair um degrau, registrar uma vez, nunca levantar (S-234).

**O contrato é da S-53 e está em `ui/theme.py`:** *"um checkout sem o extra, um bundle que não o
incluiu ou um tema com nome errado não podem impedir o app de abrir -- tema é aparência, e
aparência não derruba ferramenta"*. `apply_theme` o cumpre: tema recusado cai no padrão, padrão
recusado cai no `ttk` puro, e nada levanta.

**A Fase 35 acrescentou eixos, e cada eixo novo é um modo de falha novo** -- pele, densidade,
ícone, conjunto de peças. Todos acontecem exatamente na abertura, que é o pior momento: uma
exceção ali não degrada nada, ela apaga o programa antes de ele existir.

Este módulo é duas coisas pequenas e uma útil:

- **`QUEDAS`**, o contrato como dado. Enquanto ele foi prosa em quatro docstrings, "as seis quedas
  funcionam" era uma frase; declarado, ele vira o que `test_ui_degradacao` percorre. É o mesmo
  movimento de `comandos.CATALOGO` e de `menu.MENUS`.
- **`avisar_uma_vez`**, que é o "registra uma vez" do contrato. Sem ele, o aviso de um ícone que
  não desenhou sai **uma vez por botão** -- dezessete linhas iguais numa fita, e a décima oitava
  quando a densidade mudar.
- **`abrir_cromo_de_prova`**, que sobe o cromo de uma pele numa janela retirada e devolve o que
  deu errado. É o que faz "as três peles abrem" ser afirmação verificada e não esperança.

**Nada de `tkinter` no topo, e é obrigatório e não estético:** `ui/icones.py` usa `avisar_uma_vez`,
e `ui/fila.py` importa `icones` -- um `import tkinter` aqui em cima fecharia o ciclo
`icones → degradacao → fila → icones`. Quem precisa de widget é `abrir_cromo_de_prova`, e ela
importa por dentro.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "QUEDAS",
    "Queda",
    "avisar_uma_vez",
    "avisos_dados",
    "esquecer_avisos",
    "por_chave",
]


@dataclass(frozen=True)
class Queda:
    """Uma falha de aparência prevista: o que quebra, para onde cai, e quem cumpre isso."""

    chave: str
    """O nome curto da queda. É por ele que o teste parametrizado acha a reprodução."""

    falha: str
    """O que deu errado, em pt-BR."""

    queda: str
    """O degrau abaixo -- o que a pessoa vê no lugar."""

    dono: str
    """O módulo (ou a função) que cumpre esta linha. É onde se procura quando ela falhar."""


QUEDAS: tuple[Queda, ...] = (
    Queda("pele", "pele desconhecida no disco ou em CVOFF_SKIN", "a pele clássica", "pele.valida"),
    Queda("densidade", "densidade desconhecida", "a densidade confortável", "pele.densidade_em_vigor"),
    Queda("icone", "ícone sem traço declarado", "o botão só com texto", "icones.imagem"),
    Queda("desenho", "Pillow indisponível ou desenho falho", "o botão só com texto", "icones.imagem"),
    # `board_render.PieceImages` era o dono, e ele saiu no corte do Tk (S-506): a tabela ficou
    # apontando para um módulo que não existe mais, que é o defeito que ela própria descreve.
    Queda("pasta_de_pecas", "pasta de peças ausente ou incompleta", "o símbolo Unicode, peça a peça", "qt/tabuleiro.carregar_pecas"),
    Queda("conjunto", "conjunto de peças desconhecido", "o conjunto padrão", "conjuntos.valida"),
)
"""As seis falhas de aparência previstas, e o degrau de cada uma.

**Nenhuma delas levanta**, e nenhuma delas é silenciosa: as duas metades juntas são o contrato. Um
degrau silencioso vira "o programa está estranho hoje"; uma exceção vira um programa que não abre.

A ordem é a da tabela da SPEC_APARENCIA, que é a ordem em que elas acontecem na abertura: primeiro
o que a janela **é** (pele, densidade), depois o que ela **desenha** (ícone, peça)."""


por_chave: dict[str, Queda] = {registro.chave: registro for registro in QUEDAS}


_avisados: set[tuple[str, ...]] = set()
"""As chaves de aviso já dadas neste processo. Do módulo, e não de uma instância, pela razão do
cache de `ui/icones.py`: este processo tem uma raiz Tk e um log."""


def avisar_uma_vez(
    registrador: logging.Logger,
    chave: tuple[str, ...] | str,
    mensagem: str,
    *args: Any,
) -> bool:
    """Registra `mensagem` no nível `warning` **na primeira vez** que aquela chave aparece.

    Devolve se avisou -- útil para o teste, e para quem quiser contar.

    **O `logger` é do chamador**, e não deste módulo: a linha do log tem de nomear quem tem o
    problema. Um aviso de ícone que saísse como `ui.degradacao` mandaria quem o lê procurar no
    módulo errado -- é a mesma razão de `icones.icone` receber a cor em vez de perguntá-la.

    **A chave inclui o valor, e não só o assunto.** `("icone", "abrir_pdf")` cala o segundo botão
    que pede o mesmo ícone que faltou, e **não** cala um ícone diferente que também falte: o
    segundo nome é informação nova. Uma chave só por assunto esconderia a metade do defeito que
    interessa.
    """
    marca = (chave,) if isinstance(chave, str) else tuple(chave)
    if marca in _avisados:
        return False
    _avisados.add(marca)
    registrador.warning(mensagem, *args)
    return True


def esquecer_avisos() -> None:
    """Zera a memória de avisos. É do teste, e da troca de pele que refaz o cromo inteiro."""
    _avisados.clear()


def avisos_dados() -> int:
    """Quantas chaves distintas já avisaram. Para teste e para depurar log ruidoso."""
    return len(_avisados)
