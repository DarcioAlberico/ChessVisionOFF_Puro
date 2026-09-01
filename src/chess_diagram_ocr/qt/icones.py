"""O ícone declarado em `ui/icones.py`, entregue como `QIcon` (S-220/S-503).

**Nenhum traço é redesenhado aqui.** Os catorze ícones são polígonos e arcos declarados numa caixa
de 100×100 em `ui/icones.py`, e `icones.imagem(nome, tamanho, cor)` os desenha em PIL -- sem passar
por toolkit nenhum. Ela já existia separada de `icones.icone` exatamente para isto: *"para que o
desenho seja afirmável sem janela"*. Este módulo faz a última perna, PIL → Qt, e nada mais.

**A cor continua sendo do chamador**, como do outro lado: quem monta a fita pergunta ao token e
passa o hexadecimal, e é o que faz o mesmo traço servir ao cromo claro e ao escuro sem uma segunda
arte. Um ícone com cor própria seria a decisão que a S-220 tirou do desenho.

**`None` para nome desconhecido, e não exceção** -- a mesma escolha de `icones.icone`, pela mesma
razão: ícone que falta desenha um botão só com texto, que é legível, e nenhum ícone pode impedir a
janela de abrir (regra 4 da SPEC_APARENCIA).

**O cache é daqui, e é separado do outro.** O de `ui/icones.py` guarda `ImageTk.PhotoImage`, que
precisa de referência viva para o Tk não recolher a imagem; um `QIcon` não tem esse problema, mas
tem o outro -- redesenhar catorze polígonos em supersample a cada remontagem de fita é trabalho
repetido por gesto de janela. As duas caches guardam objetos de toolkits diferentes com a mesma
chave `(nome, tamanho, cor)`, e por isso não podem ser uma só.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QImage, QPixmap

from chess_diagram_ocr.ui import degradacao, icones

logger = logging.getLogger(__name__)

__all__ = ["cache_de_icones", "icone", "limpar_cache", "pixmap"]

_cache: dict[tuple[str, int, str], QIcon] = {}


def pixmap(nome: str, tamanho: int, cor: str) -> QPixmap | None:
    """O ícone como `QPixmap`, ou `None` quando o nome não existe ou o desenho falhou.

    A conversão passa por `tobytes()` e `.copy()` pela mesma razão de `qt/imagens.py`: o `QImage`
    construído sobre um buffer emprestado não copia nada e morre junto com o buffer -- e aqui o
    buffer é um temporário da PIL, que some no fim desta linha.
    """
    desenho = icones.imagem(nome, tamanho, cor)
    if desenho is None:
        return None
    try:
        rgba = desenho.convert("RGBA")
        imagem = QImage(
            rgba.tobytes("raw", "RGBA"),
            rgba.width,
            rgba.height,
            4 * rgba.width,
            QImage.Format.Format_RGBA8888,
        ).copy()
    except Exception as exc:  # noqa: BLE001 - PIL exótica ou Qt que recusa o formato
        degradacao.avisar_uma_vez(
            logger, ("qpixmap", nome), "Ícone %r não virou imagem do Qt (%s).", nome, exc
        )
        return None
    return QPixmap.fromImage(imagem)


def icone(nome: str, tamanho: int, cor: str) -> QIcon | None:
    """O ícone pronto para um `QAbstractButton`. `None` se o nome não existe.

    **O `QIcon` guarda o pixmap no tamanho pedido e não deixa o Qt reescalar.** Um `QIcon` vazio
    a que se pede um tamanho que ele não tem devolve o mais próximo esticado, e o traço de
    `ui/icones.py` -- 9% do lado -- vira uma mancha quando 20 px são esticados para 32. Cada
    tamanho é um desenho, e é por isso que a chave do cache o inclui.
    """
    chave = (nome, max(1, int(tamanho)), cor)
    guardado = _cache.get(chave)
    if guardado is not None:
        return guardado
    desenho = pixmap(*chave)
    if desenho is None:
        return None
    pronto = QIcon()
    pronto.addPixmap(desenho, QIcon.Mode.Normal, QIcon.State.Off)
    _cache[chave] = pronto
    return pronto


def tamanho(lado: int) -> QSize:
    """`QSize` quadrado, que é a forma que `setIconSize` pede. Existe para não repetir o par."""
    return QSize(lado, lado)


def cache_de_icones() -> int:
    """Quantos ícones estão desenhados agora. Para teste e para depurar consumo."""
    return len(_cache)


def limpar_cache() -> None:
    """Esquece o que foi desenhado. A troca de pele chama isto: a cor mudou."""
    _cache.clear()


_ = Qt  # noqa: B018 - mantém o import de Qt legível para quem estender este módulo
