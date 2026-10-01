"""As abas emprestadas pela suíte como donas de comandos (OCR_UI ciclo 2, passo C8).

Duas coisas que a janela não deve saber por dentro: **quem responde** por cada comando
declarado em `caissa.ui.views.declarados` (a aba, quando montada; a frase de ausência, quando
não), e **qual aba está à frente** quando um comando global (`salvar`, `ler_pagina`, virar a
página) tem de ir a ela em vez de ao painel Resultado.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from chess_diagram_ocr.qt import painel_de_revisao_de_texto, painel_de_rotulagem
from chess_diagram_ocr.ui import estado_do_rodape

__all__ = ["MOTIVO_AUSENTE", "donos", "metodo_da_aba_a_frente"]

MOTIVO_AUSENTE = "Esta ação é da aba da suíte, que não está ao alcance nesta instalação."


def _ausente(dizer: Callable[[str, str], None]) -> Callable[[], None]:
    return lambda: dizer(MOTIVO_AUSENTE, estado_do_rodape.AVISO)


def donos(rotulagem: Any, revisao: Any, *, dizer: Callable[[str, str], None]) -> dict[str, Callable[[], Any]]:
    """`comando -> chamável` para as duas abas; sem a aba, a frase de ausência é a dona."""
    tabela: dict[str, Callable[[], Any]] = {}
    for aba, declarados in ((rotulagem, painel_de_rotulagem.comandos()),
                            (revisao, painel_de_revisao_de_texto.comandos())):
        for acao, metodo in declarados.items():
            alvo = getattr(aba, metodo, None) if aba is not None else None
            tabela[acao] = alvo if callable(alvo) else _ausente(dizer)
    # Com a suíte fora do alcance as tabelas vêm vazias, e os nomes do catálogo ainda
    # precisam de dono: a frase, para o comando existir no menu e dizer por que não faz nada.
    for acao in ("rotulagem_ler_pagina", "rotulagem_salvar", "rotulagem_desenhar",
                 "revisao_texto_gravar", "revisao_texto_abrir"):
        tabela.setdefault(acao, _ausente(dizer))
    return tabela


def metodo_da_aba_a_frente(abas: Any, candidatas: Sequence[Any], metodos: Sequence[str]) -> Callable[[], Any] | None:
    """O primeiro de `metodos` que a aba à frente tem, quando ela é uma das `candidatas`."""
    try:
        atual = abas.area_atual()
    except Exception:  # noqa: BLE001 - sem abas montadas não há aba à frente
        return None
    if atual is None or not any(atual is aba for aba in candidatas if aba is not None):
        return None
    for nome in metodos:
        alvo = getattr(atual, nome, None)
        if callable(alvo):
            return alvo
    return None
