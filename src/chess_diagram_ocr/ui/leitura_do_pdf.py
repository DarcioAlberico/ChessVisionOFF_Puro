"""O que o visualizador de PDF decide fora do widget (S-31/S-69/S-330/S-503).

Três números medidos, a cor da caixa e o leitor do sistema. Nenhum deles toca toolkit, e os três
números são o tipo de constante que uma segunda implementação copia com o valor certo e o
significado errado:

- **`MIN_SELECTION_PX` é medida da folha, e não da tela** (S-330). A comparação era feita nas
  coordenadas do canvas, que já vêm multiplicadas pelo zoom: a 25% o piso valia 48 px de página, e
  a 200%, 6 px. O mesmo arrasto era "muito pequeno" numa vista e recorte válido na outra.
- **`CLICK_SLOP_PX` é o que separa clique de arrasto**, e é ele que deixa a rolagem pela mão
  conviver com os diagramas marcados: sem folga, o clique de quem apoia a mão vira arrasto e não
  abre diagrama nenhum; com folga demais, arrastar a barra abriria um diagrama por acidente.
- **`PASSO_DE_ZOOM` é aditivo**, e não multiplicativo: um clique, um passo previsível.

**`open_in_system_reader` tem três ramos, e é de propósito.** Sem o WebView2 (S-69) não sobrou
nada de específico de Windows no projeto, e deixar um `os.startfile` sozinho reintroduziria a
dependência de plataforma pela porta dos fundos -- por um botão.

**A cor da caixa não é uma segunda decisão.** Quem diz em que ponto do trabalho um diagrama está é
`page_overlay.estado_da_caixa`, que é pura e é a mesma dos dois lados; `box_color` só resolve o
papel de cor daquele estado. `qt/visor.py` resolve o mesmo papel pela mesma tabela de `tokens`.

`ui/pdf_panel.py` reexporta tudo o que está aqui.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import tokens
from .page_overlay import DiagramBox

__all__ = [
    "BOX_OUTLINE",
    "BOX_OUTLINE_CONFIRMED",
    "BOX_OUTLINE_RECOGNIZED",
    "BOX_OUTLINE_SAVED",
    "CLICK_SLOP_PX",
    "MIN_SELECTION_PX",
    "PASSO_DE_ZOOM",
    "SELECTION_HALO_PX",
    "box_color",
    "open_in_system_reader",
]

PASSO_DE_ZOOM = 0.1
"""Quanto um clique em `+` ou `-` muda o zoom. Aditivo, e não multiplicativo: um clique, um passo
previsível."""

MIN_SELECTION_PX = 12
"""Arrasto menor que isto é clique errado, não seleção. Abaixo disso o recorte não conteria nem
uma casa do tabuleiro.

**Doze pixels de página, e não de tela (S-330).** O que a constante quer dizer -- "menos que isto
não contém casa nenhuma" -- é uma afirmação sobre a folha, então é na folha que ela se mede."""

CLICK_SLOP_PX = 4
"""Quanto o ponteiro pode andar entre apertar e soltar e ainda ser um clique.

Sem folga, o clique de quem apoia a mão no mouse vira arrasto e não abre diagrama nenhum; com
folga demais, arrastar a barra de rolagem abriria um diagrama por acidente."""

SELECTION_HALO_PX = 4
"""Folga da segunda borda do diagrama selecionado, para fora da caixa.

Para **fora** porque a caixa encosta no diagrama: uma borda por dentro cairia sobre as casas da
primeira fila, e a caixa existe justamente para conferir a posição."""

# --- as três cores são **um** eixo: em que ponto do trabalho aquele diagrama está. A seleção
# --- deixou de ser cor na S-71 justamente para não disputar este eixo.
BOX_OUTLINE = tokens.RESERVA[tokens.A_FAZER]
"""Localizado pelo detector, ainda não lido."""

BOX_OUTLINE_RECOGNIZED = tokens.RESERVA[tokens.LIDO]
"""Lido pelo OCR e **ainda não salvo**: o que falta fazer nesta página."""

BOX_OUTLINE_SAVED = tokens.RESERVA[tokens.PRONTO]
"""Já tem amostra no `labels.csv`. Verde é a cor de "pronto", e é para isso que ela serve.

Vale mesmo antes de a página ser lida: quem responde é a procedência gravada no CSV, não o que
está em memória. Abrir um livro pela quinta vez e ver de verde o que já foi feito é a única forma
barata de responder "onde eu parei?"."""

BOX_OUTLINE_CONFIRMED = tokens.RESERVA[tokens.DISPENSADO]
"""A base de partidas reconheceu a posição (S-75). Violeta porque não é nem "feito" nem "a fazer":
é **"não precisa"**, que é um estado que a tela não tinha."""


def box_color(box: DiagramBox) -> str:
    """A cor do retângulo, pelo ponto em que aquele diagrama está.

    A precedência é: salvo > confirmado > lido > localizado -- da informação mais adiantada para a
    menos. Salvo vem antes de confirmado porque ele é trabalho **seu** já feito: um diagrama salvo
    e confirmado não precisa de nada, e o que interessa saber ao olhar a página é que aquele já
    rendeu amostra. Salvo e confirmado valem inclusive antes de a página ser lida, e é isso que faz
    a marcação servir a um livro trabalhado ontem.
    """
    if box.saved:
        return BOX_OUTLINE_SAVED
    if box.confirmed:
        return BOX_OUTLINE_CONFIRMED
    return BOX_OUTLINE_RECOGNIZED if box.recognized else BOX_OUTLINE


def open_in_system_reader(pdf_path: Path) -> None:
    """Abre o PDF no leitor padrão do sistema, na janela dele.

    Substitui o WebView2 embutido (S-69) e cabe em oito linhas porque não tenta ser uma aba: quem
    quer ler o livro ganha o leitor de verdade, com rolagem contínua e busca de texto, e o app não
    promete saber o que acontece lá dentro -- que era a promessa que a aba "Leitura" não tinha como
    cumprir.

    Os três ramos existem porque, sem o WebView2, **não sobrou nada de específico de Windows no
    projeto**. Deixar um `os.startfile` sozinho aqui reintroduziria a dependência de plataforma
    pela porta dos fundos, e por um botão.
    """
    alvo = str(Path(pdf_path).resolve())
    if sys.platform == "win32":
        # `os.startfile` só existe no Windows -- daí o `getattr`, que mantém os três ramos
        # verificáveis nas três plataformas em vez de depender de um `type: ignore`.
        getattr(os, "startfile")(alvo)  # noqa: B009
    elif sys.platform == "darwin":
        subprocess.Popen(["open", alvo])
    else:
        subprocess.Popen(["xdg-open", alvo])
