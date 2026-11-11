"""A sessão da janela: o que ela lembra entre execuções, e como ela fecha (S-31).

Saiu de `qt/janela.py` pela regra de corte da S-31 (`tests/test_packaging.py`), **sem mudar uma
decisão**: são os mesmos seis métodos, com `janela` onde estava `self`. A decisão de cada campo é de
`ui/state.py` e de `ui/geometria.py`; o que mora aqui é o trajeto entre o disco e os widgets, nas
duas direções, e a ordem do fechamento.

`closeEvent`, `_gravar_estado` e `_anotar_arranjo` continuam existindo na classe, delegando para cá:
o primeiro porque o Qt só o chama ali, os outros dois porque são a face que os testes medem.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import QMessageBox

from chess_diagram_ocr.processo_de_trabalho import processo_de_trabalho
from chess_diagram_ocr.qt import dialogos, plataforma
from chess_diagram_ocr.qt.trabalho import esperar_as_tarefas
from chess_diagram_ocr.ui import abas, geometria, sala_declarada
from chess_diagram_ocr.ui.geometria import LARGURA_MINIMA_DAS_ABAS, LARGURA_MINIMA_DO_VISOR
from chess_diagram_ocr.ui.page_results import paginas_editadas
from chess_diagram_ocr.ui.state import save_state

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.janela import JanelaPrincipal

logger = logging.getLogger(__name__)

__all__ = [
    "ESPERA_AO_FECHAR_MS",
    "anotar_arranjo",
    "aplicar_estado",
    "confirmar_fechamento",
    "fechar",
    "gravar_estado",
    "restaurar_arranjo",
]

ESPERA_AO_FECHAR_MS = 15_000
"""Quanto o fechamento espera pela tarefa em curso, em milissegundos."""


def aplicar_estado(janela: JanelaPrincipal) -> None:
    """Põe nos widgets o que veio do disco, e só então libera a gravação (S-156/S-291/S-322).

    **Depois de `_ligar` e não antes.** Marcar um interruptor dispara o sinal dele, e o sinal
    só chega a quem escuta depois da fiação -- restaurar antes deixaria a marca na tela e o
    efeito dela por acontecer, que é a metade pior dos dois estados possíveis.
    """
    estado = janela._estado
    restaurar_arranjo(janela)
    # `last_pdf` vazio é "nunca houve sessão anterior", e aí não há zoom escolhido a
    # restaurar: quem enquadra a primeira abertura é o ajuste à página da S-157.
    if estado.last_pdf:
        janela.pdf.aplicar_zoom(estado.pdf_zoom)
    # Depois do zoom (F9-C3): `aplicar_zoom` desliga o enquadramento.
    janela.pdf.definir_enquadramento(estado.pdf_enquadramento)
    janela.pdf.marcar_diagramas.setChecked(estado.show_diagram_boxes)
    janela.pdf.roda_vira_pagina.setChecked(estado.wheel_flips_page)
    janela.painel.mostrar_incerteza = estado.show_heatmap
    janela.texto.aplicar_estado(estado)  # zoom, quebra, motor e os diagramas (S-620, S-623)
    for nome, ligado in {**janela.mesa.estados(), **janela.texto.interruptores_da_vista()}.items():
        janela.menu.marcar(nome, ligado=ligado)  # a mesa (S-640) e a vista dos diagramas (S-620, S-624)
    janela.estudo.leiaute.posicionar_divisor(estado.estudo_divisor)
    janela.estudo.leiaute.posicionar_divisor_vertical(estado.estudo_divisor_vertical)
    # O leitor que `board_zoom` nunca teve (S-518): o campo era gravado, era lido do disco, e
    # não chegava a widget nenhum.
    janela.estudo.leiaute.definir_fracao_do_tabuleiro(estado.board_zoom)
    # Daqui para baixo o disco já está nos widgets, e gravar volta a ser honesto (S-322).
    janela._estado_aplicado = True


def restaurar_arranjo(janela: JanelaPrincipal) -> None:
    """Tamanho, posição, divisor e aba de onde a sessão anterior parou (S-156).

    A geometria passa por `geometria_a_aplicar`, a mesma decisão pura do outro frontend: sem ela, trocar
    de monitor entre duas sessões abre a janela fora da tela, sem erro nenhum a que se agarrar. **E o
    piso é o desta janela** (S-552, terceira rodada): o `PISO_MEDIDO`, medido numa janela **sem rolagem**,
    devolvia 1180x800 numa tela de 1024x768 -- esta rola, e o piso dela é a soma (`com_a_medicao`).
    """
    alvo = geometria.geometria_a_aplicar(
        janela._estado.window_geometry,
        plataforma.monitores(),
        piso=geometria.piso_da_janela(LARGURA_MINIMA_DAS_ABAS, LARGURA_MINIMA_DO_VISOR, com_a_medicao=False),
    )
    lida = geometria.geometria_de_texto(alvo) if alvo else None
    if lida is not None:
        janela.setGeometry(lida.x, lida.y, lida.largura, lida.altura)
    # O divisor **não** vem aqui: ver `showEvent`.
    # A área de trabalho na primeira abertura, e a guardada nas seguintes (S-162). `nome_atual`
    # traduz o nome que uma sessão antiga guardou e que desde então foi renomeado; um nome de
    # modo (`Resultado`, o que toda sessão anterior ao passo 17 guardou) abre a `Livro` nele.
    janela.abas.mostrar_area(abas.nome_atual(janela._estado.active_tab) or abas.MODO_DE_TRABALHO)


def anotar_arranjo(janela: JanelaPrincipal) -> None:
    """Lê da tela o arranjo de agora e o põe no estado (S-156/S-311).

    **Janela não mostrada não é janela medida** (S-311). Antes do `show()` o divisor devolve os
    tamanhos declarados na montagem, que são do leiaute e não da pessoa: gravá-los apagaria a
    posição da sessão anterior antes de alguém tocar em nada. `isVisible` é o `winfo_ismapped`
    deste lado.

    A geometria sai de `normalGeometry` quando ela existe: é a que a janela tem **fora** do
    maximizado e do minimizado, e é a única que faz sentido restaurar. Ela é o que substitui a
    recusa do `1x1+-32000+-32000` que o Tk devolvia para uma janela minimizada.

    **A aba fica fora da guarda**, e é a diferença entre ela e as outras duas: qual área está à
    frente é verdade com a janela mostrada ou não, e é o `QTabWidget` que responde -- não há
    medida de pixel envolvida. O nome é o da **área** (o modo `Revisão`, e não a aba `Livro`).
    """
    nome = janela.abas.nome_da_area_atual()
    if nome:
        janela._estado.active_tab = nome
    if not janela.isVisible():
        return
    normal = janela.normalGeometry()
    atual = normal if not normal.isEmpty() else janela.geometry()
    texto = f"{atual.width()}x{atual.height()}{atual.x():+d}{atual.y():+d}"
    janela._estado.window_geometry = geometria.geometria_gravavel(texto) or janela._estado.window_geometry
    # **E a fração só é gravada quando ela é escolha** (S-552, 5ª rodada). Gravá-la sempre
    # transformava a repartição de fábrica numa decisão de alguém: a sessão seguinte lia a
    # fração da largura em que a anterior por acaso fechou e a aplicava numa largura diferente
    # -- fechada a 1400 e reaberta a 1366, a aba ficava com 702 px em vez dos 720 preferidos, o
    # viewport com 684 e a Galeria empilhava. A mesa guarda as duas alças, cada uma na sua
    # chave (S-640), e a do trabalho só quando alguém a escolheu.
    janela.mesa.anotar(escolhida=not janela._divisor_de_fabrica)


def gravar_estado(janela: JanelaPrincipal) -> None:
    """Anota o que a próxima sessão precisa e grava. Nunca levanta -- `save_state` registra.

    **Nada é gravado antes de `aplicar_estado` (S-322)**: até lá os widgets estão nos padrões
    de fábrica, e escrevê-los por cima do disco apagaria a escolha da sessão anterior sem que
    ninguém tivesse mudado nada.

    `board_zoom` **é** gravado (a docstring dizia o contrário até a S-828): é a fração do
    tabuleiro da sala (S-518), que `aplicar_estado` entrega a `definir_fracao_do_tabuleiro`
    e que volta daqui por `fracao_do_tabuleiro`, como as alças dos divisores.
    """
    janela._gravacao_adiada.stop()  # o que estava agendado é este: quem chama direto o conclui
    if not janela._estado_aplicado:
        logger.debug("Estado ainda não aplicado aos widgets: gravação adiada (S-322).")
        return
    estado = janela._estado
    estado.last_pdf = str(janela._pdf) if janela._pdf is not None else ""
    estado.last_page = janela.pdf.page_index
    estado.pdf_zoom = float(janela.pdf.zoom)
    estado.pdf_enquadramento = janela.pdf.enquadramento
    estado.show_diagram_boxes = bool(janela.pdf.marcar_diagramas.isChecked())
    estado.wheel_flips_page = bool(janela.pdf.roda_vira_pagina.isChecked())
    estado.show_heatmap = janela.painel.mostrar_incerteza
    janela.texto.anotar_estado(estado)
    estado.review_queue_path = str(janela.revisao.queue_path)
    estado.estudo_aberto = janela.estudo.chave_do_estudo_aberto
    # `or` o guardado: o divisor devolve `0.0` enquanto não há geometria medida, e zero
    # significa "nunca guardado" -- gravá-lo apagaria a alça da sessão anterior.
    estado.estudo_divisor = janela.estudo.leiaute.fracao_do_divisor or estado.estudo_divisor
    estado.estudo_divisor_vertical = (
        janela.estudo.leiaute.fracao_do_divisor_vertical or estado.estudo_divisor_vertical
    )
    estado.board_zoom = janela.estudo.leiaute.fracao_do_tabuleiro
    anotar_arranjo(janela)
    save_state(janela._caminho_do_estado, estado)


def fechar(janela: JanelaPrincipal, a0: Any) -> None:
    """Espera a tarefa em curso, grava a sala de estudo e pergunta pelo que se perde.

    Um `QThread` vivo quando o objeto que o representa é destruído derruba o processo com
    `QThread: Destroyed while thread is still running` -- e num bundle isso é uma janela que
    some sem deixar rastro.

    **A espera é limitada, e o limite é generoso**: ler uma página de nove diagramas na CPU
    leva alguns segundos, e fechar no meio disso é gesto comum. Estourar o limite não impede o
    fechamento -- não há nada melhor a fazer com uma thread presa --, mas fica no log.
    """
    perdidas = [operacao for operacao in janela.busy.running() if operacao.loses_work]
    editadas = paginas_editadas(janela.painel.paginas, janela.painel.modelo)  # correções à mão (A7)
    if (perdidas and not confirmar_fechamento(janela, perdidas)) or (
        editadas and not dialogos.perguntar_descarte(janela, editadas, ao_fechar=True)
    ) or not janela.texto.confirmar_fechamento():  # o texto digitado e não gravado na aba Texto
        if a0 is not None:
            a0.ignore()
        return
    # A sala vai para o disco antes de tudo: ela é o único painel cujo trabalho não tem outra
    # cópia, e o `Ctrl+Z` dela não sobrevive à janela (S-271).
    janela.estudo.salvar_agora()
    janela.mesa_destacada.fechar()  # o texto volta à aba e a janela da mesa fecha junto (S-646)
    # E o arranjo depois dela, **antes da espera pela tarefa**: uma thread presa não pode
    # custar o último livro, a página e o divisor de quem já mandou fechar (S-156).
    gravar_estado(janela)
    # O motor é um processo (S-523) e a sala pode tê-lo trocado nas preferências (S-536): o
    # fechado é o dela, e sem levantar (`encerrar_o_motor`, F9-C16).
    sala_declarada.encerrar_o_motor(janela.estudo.motor.analisador)
    processo_de_trabalho().encerrar(matar=True)  # o filho pendurado não segura o processo (S-906)
    janela._detector.parar(ESPERA_AO_FECHAR_MS)
    # Nenhuma tarefa tem pai (F9-C2, S-826): destruí-las a correr derrubava o processo sem
    # rastro (o portão `comandos` mediu: exit 255, nada no log). A espera é cortesia, e é de
    # **todas** -- a leitura, o aquecimento, as dos painéis (a exportação do texto que acaba
    # em vez de ficar pela metade) --; a que estoura o prazo fica no log e termina sozinha.
    janela._aquecimento.cancelar()   # o relógio de uma janela fechada não dispara mais
    if pendentes := esperar_as_tarefas(ESPERA_AO_FECHAR_MS):
        logger.warning("A janela fechou com tarefas em andamento (%s); elas terminam sozinhas.", ", ".join(t.nome for t in pendentes))
    if a0 is not None:
        a0.accept()


def confirmar_fechamento(janela: JanelaPrincipal, perdidas: Sequence[Any]) -> bool:
    """Pergunta antes de fechar sobre uma operação que perde trabalho (S-60/S-112).

    **Só as que perdem**, e é o item: a varredura do livro retoma de onde parou e a busca por
    nome custa a passada de novo -- perguntar sobre elas ensinaria a fechar a caixa sem ler,
    e aí a pergunta que importa (a busca por posição, ~56 min de tudo-ou-nada) passaria batida.
    """
    nomes = ", ".join(operacao.name for operacao in perdidas)
    caixa = QMessageBox(janela)
    caixa.setIcon(QMessageBox.Icon.Warning)
    caixa.setWindowTitle("Fechar")
    caixa.setText(f"Estas operações perdem o trabalho feito se a janela fechar agora:\n\n  {nomes}")
    caixa.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    caixa.setDefaultButton(QMessageBox.StandardButton.No)
    return caixa.exec() == QMessageBox.StandardButton.Yes
