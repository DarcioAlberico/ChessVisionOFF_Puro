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

__all__ = ["cache_de_icones", "icone", "limpar_cache", "pixmap", "vestir", "vestiu_de_icone"]

_cache: dict[tuple[str, int, str], QIcon] = {}


def vestir(
    botao: object, nome_do_icone: str, papel: str, *, lado: int = 0, manter_texto: bool = False
) -> bool:
    """Põe o desenho no botão e **apaga o glifo de texto**. `False` se não havia desenho.

    **É o item 4 do §9 do ciclo 5 com o escopo do §4.7 do ciclo 7.** O ciclo 6 pôs os nove
    botões da barra do visor numa grade única de 16×16 -- e a varredura que o mediu lia
    `j.pdf.findChildren`, o painel do visualizador e mais nada. Na janela inteira sobravam
    **onze** caracteres de texto fazendo papel de ícone, com caixas de tinta de 5×3 a 9×12 px, e
    o par que mais dói: `◀` com **15 px²** de tinta ao lado de `▶` com **36** -- 2,4×, entre dois
    botões que deveriam ser espelho. Ampliado a 10×, o `◀` do Segoe UI não tem ápice: é um traço
    horizontal chato, e "voltar um lance" fica sem direção legível.

    **O texto sai, e é por isso que este ajudante existe em vez de um `setIcon` em cada painel.**
    Um botão com ícone **e** glifo desenha os dois lado a lado, com o dobro da largura e a mesma
    ambiguidade.

    **`manter_texto` é para o botão que tem palavra, e ele foi achado olhando a captura.** O
    paginador da Galeria escrevia `"◀ anterior"` -- glifo **mais** palavra --, e o censo o
    contava como "tem letra, logo não é glifo-ícone". Ampliada, a captura mostra o defeito
    inteiro: o `◀` do Segoe UI rende um traço horizontal chato de 5×3 px, e o botão lê-se
    `"- anterior"`. Com `manter_texto`, o glifo sai e o desenho entra **ao lado da palavra**, que
    é o que o botão sempre quis dizer. `False` -- Pillow ausente, nome desconhecido -- deixa o glifo onde está, que é a
    degradação da regra 4 da SPEC_APARENCIA: nenhum ícone pode impedir a janela de abrir.

    O lado padrão é o mesmo de `qt/painel_do_pdf._vestir_de_icone` (`folga + linha`), e vem de lá
    pela razão de sempre: dois tamanhos de ícone na mesma janela são duas famílias.

    **`lado` existe para a família que não é cromo, e ele foi achado olhando a captura.** A paleta
    de peças desenha *peça* a `paleta_de_pecas.LADO_DO_ICONE` = 26 px; o `✕` vestido com o lado do
    cromo saía com **16 px no meio de doze vizinhos de 26**, que é o defeito do item 4 em
    miniatura -- o mesmo que este método veio fechar, um botão adiante.
    """
    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.ui import espaco, folha_de_estilo

    lado = lado or espaco.folga() + espaco.linha()
    desenho = icone(nome_do_icone, lado, tema.cor_atual(folha_de_estilo.tinta_do_papel(papel)))
    if desenho is None:
        return False
    if not manter_texto:
        botao.setText("")  # type: ignore[attr-defined]
    botao.setIcon(desenho)  # type: ignore[attr-defined]
    botao.setIconSize(QSize(lado, lado))  # type: ignore[attr-defined]
    # O alvo de clique não pode encolher com o rótulo: o piso da S-442 para um controle de
    # ponteiro, e um botão de ícone sem piso sai com a largura do desenho.
    botao.setMinimumWidth(lado + espaco.folga())  # type: ignore[attr-defined]
    return True


def vestiu_de_icone(botao: object) -> bool:
    """Se aquele botão está mostrando desenho e nenhum texto. É o que o portão do item 4 lê."""
    return bool(botao.icon().availableSizes()) and not botao.text()  # type: ignore[attr-defined]


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
