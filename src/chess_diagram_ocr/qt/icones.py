"""O ícone declarado em `ui/icones.py`, entregue como `QIcon` (S-220/S-503).

**Nenhum traço é redesenhado aqui.** Os catorze ícones são polígonos e arcos declarados numa caixa
de 100×100 em `ui/icones.py`, e `icones.imagem(nome, tamanho, cor)` os desenha em PIL -- sem passar
por toolkit nenhum. Ela nasceu separada do `PhotoImage` do Tk exatamente para isto: *"para que o
desenho seja afirmável sem janela"* -- e a metade do Tk saiu na triagem da S-511. Este módulo faz
a última perna, PIL → Qt, e nada mais.

**A cor continua sendo do chamador**, como do outro lado: quem monta a fita pergunta ao token e
passa o hexadecimal, e é o que faz o mesmo traço servir ao cromo claro e ao escuro sem uma segunda
arte. Um ícone com cor própria seria a decisão que a S-220 tirou do desenho.

**`None` para nome desconhecido, e não exceção** -- a mesma escolha de `icones.imagem`, pela mesma
razão: ícone que falta desenha um botão só com texto, que é legível, e nenhum ícone pode impedir a
janela de abrir (regra 4 da SPEC_APARENCIA).

**O cache é daqui.** `ui/icones.py` guardava `ImageTk.PhotoImage`, que precisava de referência
viva para o Tk não recolher a imagem, e aquele cache saiu com o Tk. Um `QIcon` não tem esse
problema, mas tem o outro -- redesenhar catorze polígonos em supersample a cada remontagem de fita
é trabalho repetido por gesto de janela --, e a chave continua sendo `(nome, tamanho, cor)`.

**O ícone desabilitado é desenhado aqui, e não gerado pelo Qt** (S-554). Ver `PAPEL_APAGADO`.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QImage, QPixmap

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import degradacao, icones, tokens

logger = logging.getLogger(__name__)

__all__ = [
    "PAPEL_APAGADO",
    "cache_de_icones",
    "icone",
    "limpar_cache",
    "pixmap",
    "tinta_apagada",
    "vestir",
    "vestiu_de_icone",
]

PAPEL_APAGADO = tokens.TEXTO_MORTO
"""O papel da tinta de um ícone **desabilitado** -- e é o mesmo com que a folha pinta a letra dele
(S-554).

**O defeito, medido pelo crítico na janela de verdade em 2026-09-04.** Na pele "Foco" o botão só
com ícone desabilitado saía **idêntico** ao habilitado: razão de contraste da tinta contra a face
**9,47 ligado e 9,47 desligado**, com a mesma contagem de pixels de traço (39 e 39). Onze dos
catorze botões da barra da sala são só-ícone, então o critério de aceite da S-527 -- *"Variante e
Exportar ficam cinza sem estudo"* -- era **vácuo** naquela pele. Na clássica funcionava (5,65
contra 3,23), e é isso que fazia o defeito passar despercebido.

**A causa: quem apagava o ícone era o Qt, e ele apaga clareando.** `QToolButton:disabled` da folha
só declara `color:`, que vale para o **texto**; o desenho vem do `QIcon`, e um `QIcon` que não
tenha pixmap para `QIcon.Mode.Disabled` manda o estilo gerar um -- `QCommonStyle` remapeia os tons
contra a `QPalette` e desloca para o claro. Numa paleta clara, clarear é apagar; numa escura,
**clarear é destacar**. Medido aqui sob `offscreen`, na pele "Foco": a razão máxima da tinta
**subia** de 13,41 para 14,03 ao desabilitar.

**A saída é desenhar o estado, e não deixar o toolkit adivinhá-lo.** `icone()` registra um segundo
pixmap para `QIcon.Mode.Disabled`, na cor que este papel resolve contra a pele em uso -- que é
**exatamente** a que `QToolButton:disabled` e `QPushButton:disabled` já dão à letra ao lado. Ícone e
rótulo apagam juntos porque apagam pela mesma decisão, e não por duas que por enquanto concordam.

**`TEXTO_MORTO`, e não mais `TEXTO_SECUNDARIO`**, e é a mesma regra lida de novo: desde o F9-C10 a
letra do controle morto é papel próprio (`ui/folha_de_estilo.py`, ver `tokens.TEXTO_MORTO`), e um
ícone apagado no secundário ao lado de um rótulo apagado no morto seriam as duas decisões que este
papel existe para não ter.

**Vale para toda a janela**, e é por isso que mora aqui e não na barra da sala: os quatro lugares
que desenham ícone em botão -- a barra da sala, a fila, a fita e a navegação da sala de estudo --
passam por esta função, e um segundo caminho seria a divergência que este módulo existe para não
ter."""

_cache: dict[tuple[str, int, str, str, float], QIcon] = {}


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


def tinta_apagada() -> str:
    """A cor de um ícone desabilitado na pele **em uso**. Ver `PAPEL_APAGADO`.

    Pergunta ao tema em vez de receber por parâmetro porque a resposta não depende do chamador:
    ligado, o ícone carrega o papel do botão (o primário desenha na letra da ênfase, o destrutivo
    no vermelho); desligado, não há papel a carregar -- a folha pinta os três com a mesma tinta, e
    quatro chamadores repetindo essa decisão seria o primeiro deles a esquecê-la.
    """
    return tema.cor_atual(PAPEL_APAGADO)


def icone(nome: str, tamanho: int, cor: str, *, escala: float = 1.0) -> QIcon | None:
    """O ícone pronto para um `QAbstractButton`, nos estados ligado e desligado. `None` se o nome
    não existe.

    **O `QIcon` guarda o pixmap no tamanho pedido e não deixa o Qt reescalar.** Um `QIcon` vazio
    a que se pede um tamanho que ele não tem devolve o mais próximo esticado, e o traço de
    `ui/icones.py` -- 9% do lado -- vira uma mancha quando 20 px são esticados para 32. Cada
    tamanho é um desenho, e é por isso que a chave do cache o inclui.

    **E o contrário também é mancha** (S-527): a barra da sala desenhava a 32 px e pedia 16 no
    botão, e a redução pela metade transformava o traço de 2 px num meio-tom de 1 -- "mais" saía
    sem nenhum pixel forte. O desenho é feito **no tamanho em que vai ser mostrado**; `escala` é o
    `devicePixelRatio` da tela, e só numa tela de alta densidade (`> 1`) o pixmap nasce maior, já
    marcado com a razão para o Qt o desenhar no tamanho lógico pedido.

    **O desabilitado é um segundo desenho, e não uma conversão do primeiro** (S-554): ver
    `PAPEL_APAGADO`. A tinta dele entra na chave do cache porque ela vem da pele -- dois desenhos
    do mesmo traço na mesma cor de traço podem apagar para cinzas diferentes.

    Um ícone sem o pixmap apagado continua servindo: o Qt gera o dele, que é o estado de antes
    deste item. É a regra 4 outra vez -- desenho que falta não pode impedir o botão de existir.
    """
    escala = max(1.0, float(escala))
    apagada = tinta_apagada()
    chave = (nome, max(1, int(tamanho)), cor, apagada, round(escala, 2))
    guardado = _cache.get(chave)
    if guardado is not None:
        return guardado
    lado = round(chave[1] * escala)
    desenho = pixmap(nome, lado, cor)
    if desenho is None:
        return None
    pronto = QIcon()
    for modo, traco in ((QIcon.Mode.Normal, desenho), (QIcon.Mode.Disabled, pixmap(nome, lado, apagada))):
        if traco is None:
            continue
        if escala != 1.0:
            traco.setDevicePixelRatio(escala)
        pronto.addPixmap(traco, modo, QIcon.State.Off)
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
