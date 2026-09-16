"""Aplica a escala tipográfica a toda a janela (F9-C2). **Só executa.**

A decisão -- que degrau cada widget ocupa -- é de `ui/tipografia.py`
(`PAPEL_POR_CLASSE` e `PROPRIEDADE_DE_PAPEL_DE_FONTE`). Aqui está a parte que precisa do
toolkit: andar pela árvore e chamar `setFont`.

**A medição que a obrigou.** O crítico do ciclo 1 contou a fonte de cada widget visível da
janela: **104 widgets, dois tamanhos (12 px e 11 px), um peso (400), uma família** -- e o papel
`TITULO`, que existe em `DEGRAUS` desde a S-149, aplicado a **zero** deles. A escala estava
escrita e não estava desenhada, o que é a mesma coisa que não existir.

**Por que uma varredura, e não `setFont` espalhado pelos painéis.** É o argumento de
`qt/acessibilidade.py`, e ele vale duas vezes aqui: vinte chamadas seriam vinte lugares para
esquecer, e o grupo que o próximo item acrescentar nasceria no degrau errado. A varredura roda no
fim da montagem e alcança o que existir.

**Por que não basta folha de estilo.** `QGroupBox::title { font-weight: bold }` funciona para
desenhar, e o Qt de fato o honra. Mas o `QSS` de subcontrole **não** mexe em `QWidget.font()`, que
é onde o censo do crítico olha -- e um número que só melhora na fotografia é o defeito que este
ciclo veio corrigir. A varredura muda o objeto, e a folha continua ao lado dela para o caso do
tema ser trocado sem remontagem.

**O negrito não escorre.** Fonte em Qt é herdada: pôr `TITULO` num `QGroupBox` deixaria em
negrito os quinze controles dentro dele. Por isso a varredura, depois de marcar o grupo, **declara
`CORPO` em cada filho direto** que não tenha papel próprio -- explicitamente, que é o único jeito
de a herança parar. Sem essa segunda metade, o item 9 do §7 trocaria dois tamanhos por um.
"""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import QWidget

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import folha_de_estilo, tipografia

logger = logging.getLogger(__name__)

__all__ = ["aplicar_escala", "papel_do_widget"]


def papel_do_widget(widget: QWidget) -> str:
    """O degrau da escala que este widget ocupa, ou `""` se ele é corpo comum.

    A ordem é a de toda cascata desta frente -- o explícito ganha do derivado:

    1. a propriedade dinâmica `papel_de_fonte`, escrita por quem montou o widget;
    2. a propriedade `apoio` da folha de estilo, que já marca contagem, unidade e dica;
    3. a classe, por `ui/tipografia.PAPEL_POR_CLASSE`.
    """
    declarado = widget.property(tipografia.PROPRIEDADE_DE_PAPEL_DE_FONTE)
    if declarado:
        texto = str(declarado)
        if texto in tipografia.PAPEIS_DE_FONTE:
            return texto
        logger.warning("papel de fonte desconhecido em %s: %r", type(widget).__name__, texto)
    if widget.property(folha_de_estilo.PROPRIEDADE_DE_APOIO) in (True, "true"):
        return tipografia.AUXILIAR
    classes = tuple(classe.__name__ for classe in type(widget).__mro__)
    return tipografia.papel_de_fonte_por_classe(classes)


def aplicar_escala(raiz: QWidget) -> int:
    """Põe a fonte do degrau em cada widget que declara um. Devolve quantos mudaram.

    Tolerante como `nomear_tudo`: um widget em desmontagem ou uma fonte exótica não pode impedir
    a janela de abrir, e o que falhar fica no degrau do corpo -- que é o estado de antes.
    """
    mudados = 0
    corpo = tema.fonte_atual(tipografia.CORPO)
    for widget in [raiz, *raiz.findChildren(QWidget)]:
        try:
            papel = papel_do_widget(widget)
            if widget.property(tipografia.PROPRIEDADE_TABULAR) in (True, "true"):
                # O contador recebe o degrau dele (ou o corpo) **com** algarismos tabulares
                # (OCR_UI passo 16). Aqui e não em cada painel, pela razão do cabeçalho.
                widget.setFont(tema.tabular(tema.fonte_atual(papel or tipografia.CORPO)))
                mudados += 1
                continue
            if not papel or papel == tipografia.CORPO:
                continue
            widget.setFont(tema.fonte_atual(papel))
            mudados += 1
            # A herança para aqui: ver o cabeçalho do módulo. Só os filhos **diretos**, porque o
            # neto já herda do filho, que acabou de receber o corpo explicitamente.
            for filho in widget.findChildren(QWidget):
                if filho.parentWidget() is widget and not papel_do_widget(filho):
                    filho.setFont(corpo)
        except Exception:  # noqa: BLE001 - ver o cabeçalho: nenhuma fonte derruba a janela
            logger.debug("escala não aplicada em %s", type(widget).__name__, exc_info=True)
    return mudados
