"""Onde a linha quebra, derivado da largura real do painel (S-152).

**O defeito.** Doze `wraplength` cravados, de 220 a 780 px, num painel esquerdo cuja largura
real varia de **420** (o `minsize`) a **~1.180** (com o divisor à direita). Nenhum dos doze
consulta `winfo_width`, e as duas falhas acontecem juntas em telas diferentes:

- com o painel **estreito**, o texto é cortado — o de procedência da Galeria, com
  `wraplength=220`, aparece truncado no meio da palavra ("Whit", "Jam", "antiga");
- com o painel **largo**, ele quebra cedo: quatro linhas curtas num espaço que caberia uma.

Um número cravado só está certo numa largura, e a janela tem todas.

**O teto existe, e não é o mesmo problema.** Linha de texto muito longa é ruim de ler mesmo
quando cabe — o olho perde o começo da linha seguinte. O limite fica aqui como **medida
tipográfica** (caracteres por linha) e não como pixel: 90 caracteres numa fonte de 9 pt e numa
de 14 pt são larguras diferentes e a mesma leitura, e é a leitura que se está fixando.

**A decisão é pura; o widget só a executa.** `largura_de_quebra` não toca `tkinter` e é afirmada
nos três regimes (estreito, confortável, largo). `acompanhar` é a metade que liga, e ela não
decide nada.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import font as tkfont

logger = logging.getLogger(__name__)

__all__ = [
    "AMOSTRA_DE_LARGURA",
    "FOLGA_LATERAL",
    "MEDIDA_EM_CARACTERES",
    "PISO_DE_QUEBRA",
    "acompanhar",
    "largura_de_quebra",
    "largura_media_do_caractere",
]

MEDIDA_EM_CARACTERES = 90
"""O teto de leitura, em caracteres por linha.

Entre 45 e 90 é o intervalo que a tipografia trata como confortável para texto corrido; 90 é o
topo dele porque o que este programa escreve em rótulo multi-linha é diagnóstico curto -- "a
posição é ilegal porque...", "3.936 amostras, 129 pendentes" --, e não parágrafo. Apertar mais
faria o painel largo desperdiçar espaço, que é metade do defeito que este item corrige."""

PISO_DE_QUEBRA = 200
"""Largura mínima de quebra, em pixels.

Existe por dois motivos que se parecem e não são o mesmo. Antes de a janela ser mapeada,
`winfo_width` devolve **1**, e sem piso todo rótulo nasceria com uma palavra por linha e só se
arrumaria no primeiro `<Configure>` -- um piscar a cada abertura. E num painel espremido no
`minsize`, quebrar exatamente na largura disponível dá linhas de duas palavras: aí é melhor a
linha passar um pouco e a rolagem da S-150 alcançá-la."""

FOLGA_LATERAL = 24
"""Quanto se desconta da largura do pai: as duas margens de `padx` que os painéis usam.

Sem ela o rótulo quebra na largura exata do pai e a última letra encosta na borda -- ou some,
quando o pai tem `padding`."""

AMOSTRA_DE_LARGURA = "abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ"
"""O texto medido para achar a largura média de um caractere.

Minúsculas, maiúsculas e um espaço, porque é a mistura do que os rótulos escrevem. Medir só
`"0"` -- o atalho comum -- superestima em fonte proporcional: o dígito é desenhado na largura
da tabular, e `i`, `l` e `t` são bem mais estreitos."""


def largura_de_quebra(
    largura_do_pai: int,
    largura_do_caractere: float,
    *,
    folga: int = FOLGA_LATERAL,
    medida: int = MEDIDA_EM_CARACTERES,
    piso: int = PISO_DE_QUEBRA,
) -> int:
    """Em quantos pixels a linha quebra, dada a largura do pai. Pura.

    Três regimes, e o teste afirma os três:

    - **estreito** (pai abaixo do piso, ou ainda não medido): devolve o piso;
    - **confortável**: devolve a largura disponível, e o texto usa o painel inteiro;
    - **largo**: devolve o teto de leitura, e o texto para de esticar.
    """
    disponivel = int(largura_do_pai) - folga
    teto = int(round(largura_do_caractere * medida))
    if disponivel < piso:
        return piso
    return min(disponivel, teto)


def largura_media_do_caractere(rotulo: tk.Widget) -> float:
    """A largura média de um caractere na fonte deste rótulo. Reserva quando o Tk não responde.

    A medida do teto é em caracteres (ver `MEDIDA_EM_CARACTERES`), e converter para pixel exige
    perguntar à fonte — que é o que faz o teto acompanhar quem aumentou a fonte do Windows, em
    vez de virar mais um pixel cravado com outro nome.
    """
    try:
        nome = str(rotulo.cget("font") or "") or "TkDefaultFont"
        fonte = tkfont.nametofont(nome) if nome.startswith("Tk") else tkfont.Font(root=rotulo, font=nome)
        return fonte.measure(AMOSTRA_DE_LARGURA) / len(AMOSTRA_DE_LARGURA)
    except Exception as exc:  # noqa: BLE001 - fonte exótica ou widget sem janela ainda
        logger.debug("Largura de caractere não medida (%s): usando a reserva.", exc)
        return 7.0


def acompanhar(rotulo: tk.Widget, pai: tk.Misc | None = None) -> tk.Widget:
    """Liga o `wraplength` do rótulo à largura do pai, e devolve o rótulo.

    Devolve o próprio rótulo para caber na linha que já existe --
    `texto.acompanhar(ttk.Label(...)).pack(...)` --, que é o que faz os doze pontos de chamada
    trocarem um argumento por uma chamada em vez de ganharem três linhas cada.

    O pai padrão é o `master` do rótulo, e ele é quem manda: é o `<Configure>` **dele** que
    chega quando o divisor se move. Escutar o `<Configure>` do próprio rótulo daria um laço --
    mudar o `wraplength` muda a altura pedida do rótulo, que dispara outro `<Configure>`.
    """
    alvo = pai if pai is not None else rotulo.master
    if alvo is None:  # pragma: no cover - rótulo sem pai não existe em Tk
        return rotulo

    def aplicar(largura: int) -> None:
        try:
            # `rotulo["wraplength"]` e não `configure(wraplength=...)`: o segundo é tipado por
            # `Misc`, que não tem essa opção -- ela é de `Label`, e o auxiliar aceita qualquer
            # widget que a tenha sem exigir a classe exata.
            rotulo["wraplength"] = largura_de_quebra(largura, largura_media_do_caractere(rotulo))
        except tk.TclError:  # pragma: no cover - rótulo destruído antes do evento
            pass

    alvo.bind("<Configure>", lambda evento: aplicar(int(evento.width)), add="+")
    aplicar(alvo.winfo_width())
    return rotulo
