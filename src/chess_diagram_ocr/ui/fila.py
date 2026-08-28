"""A fila única de ações da pele "Foco", gerada do catálogo (S-223).

**O diagnóstico da Imagem 1 está certo; a contagem dela, não.** Ela mostra quatro comandos onde a
janela tem 21 nas duas barras do PDF, e desenhá-la ao pé da letra apagaria 23 controles. O que ela
acerta é o problema: numa fila de 21 botões de peso igual, o olho não encontra a ação do minuto a
minuto. É o argumento de `ui/estilos.py:12-16`, agora sobre quantidade em vez de ênfase.

**A fila é gerada, e é isso que a torna barata.** Ela sai dos comandos com `destaque=True` em
`ui/comandos.py`, agrupados por `grupo`. Acrescentar um comando à fila é acrescentar `destaque=True`
a uma linha do catálogo -- ninguém vem aqui.

**Os outros 23 controles não somem: eles vão para o menu**, que a S-161 construiu e que a própria
Imagem 1 mostra intacto no topo. Os três que só existiam como botão -- cancelar exportação e os
dois de zoom -- ganharam item de menu na S-223, e a linha do conjunto de campo é a exceção que
fica onde está: ela anota *aquela* página, e um comando de menu que age sobre a página exibida sem
que ela esteja à vista é o tipo de gesto que grava verdade de referência errada (S-77).

**Por que `BarraFluida` e não um `pack` de linha única.** A fila cabe em uma linha em 1100 px, que
é a largura em que a S-151 mediu o defeito original -- mas "cabe hoje" não é uma propriedade. A
barra fluida garante a que importa: **nenhum item é descartado**, em nenhuma largura.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from tkinter import ttk

from . import atalhos, comandos, icones, theme, tokens
from .barra import BarraFluida
from .tooltip import Tooltip

__all__ = ["LADO_DO_ICONE", "acoes_da_fila", "montar"]

LADO_DO_ICONE = 18
"""Lado do ícone da pílula, em pixel. Pequeno de propósito: a pílula tem rótulo ao lado, e o
ícone aqui é marca de reconhecimento, não a informação. O ícone grande com rótulo embaixo é da
fita (S-228), que é outra pele e outro orçamento de altura."""


def acoes_da_fila() -> list[str]:
    """Os nomes dos comandos que a fila desenha, na ordem em que ela os desenha."""
    return [registro.acao for grupo in comandos.fila_de_destaque() for registro in grupo]


def montar(pai: tk.Misc, amarrados: Mapping[str, Callable[[], None]], *, lado_do_icone: int = LADO_DO_ICONE) -> BarraFluida:
    """A fila, montada numa `BarraFluida`. Levanta `KeyError` nomeando comando não amarrado.

    Levanta pela mesma razão que `menu.montar`: uma pílula grande, com ícone, que não faz nada é
    pior que a ausência dela -- a pessoa conclui que a função existe e está quebrada.
    """
    if faltando := sorted(acao for acao in acoes_da_fila() if acao not in amarrados):
        raise KeyError(f"comando em destaque sem função: {', '.join(faltando)}")

    barra = BarraFluida(pai)
    # Um passo só, na ordem em que a fila se lê: a ordem de criação passa a ser a de exibição, e
    # o separador nasce com a altura das pílulas que já existem -- medida, e não escolhida a olho,
    # que é o que faz ele acompanhar a fonte do sistema que a S-149 deixou de cravar.
    altura = 0
    for numero, grupo in enumerate(comandos.fila_de_destaque()):
        if numero:
            barra.adicionar(_separador(barra, altura))
        for registro in grupo:
            pilula = _pilula(barra, registro, amarrados[registro.acao], lado_do_icone)
            altura = max(altura, pilula.winfo_reqheight())
            barra.adicionar(pilula)
    return barra


def _pilula(pai: tk.Misc, registro: comandos.Comando, funcao: Callable[[], None], lado: int) -> ttk.Button:
    """Um comando em destaque: ícone à esquerda, rótulo à direita, tecla no tooltip."""
    botao = ttk.Button(pai, text=registro.no_botao, style=comandos.estilo(registro.acao), command=funcao)
    # A cor do ícone é perguntada ao token na hora de desenhar, e é o que faz o mesmo traço
    # servir ao cromo claro e ao escuro (S-220). Ícone que não desenhou vira pílula só com
    # texto, e não pílula sem nada: `icones.icone` devolve `None` em vez de levantar.
    foto = icones.icone(registro.icone, lado, theme.cor_atual(tokens.TEXTO_PADRAO)) if registro.icone else None
    if foto is not None:
        botao.configure(image=foto, compound=tk.LEFT)
    tecla = atalhos.acelerador(registro.acao)
    Tooltip(botao, f"{registro.rotulo}\nTecla: {tecla}" if tecla else registro.rotulo)
    if registro.rotulo_alternado:
        # A fila também mostra o estado de um comando que é modo (S-396).
        comandos.ao_alternar(registro.acao, lambda texto: botao.configure(text=texto))
    return botao


def _separador(pai: tk.Misc, altura: int) -> tk.Frame:
    """A barra vertical entre grupos -- o que a Imagem 1 desenha entre a 2ª e a 3ª pílula.

    `tk.Frame` e não `ttk.Separator`: o separador do `ttk` só aparece com `fill=Y`, e quem
    empacota aqui é a `BarraFluida`, que empacota todos os itens do mesmo jeito. Um retângulo de
    um pixel na cor da moldura é o mesmo desenho sem pedir exceção à barra.
    """
    return tk.Frame(pai, width=1, height=max(altura, 1), bg=theme.cor_atual(tokens.MOLDURA))
