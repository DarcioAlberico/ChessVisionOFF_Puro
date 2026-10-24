"""O leitor de volta da aba Texto: o que a tela mostra, comparado ao que o documento diz (S-603).

**A guarda existe porque as duas metades passavam sozinhas.** `texto_formato.bloco_de` devolvia o
alinhamento certo, e os testes dele passavam; o `_desenhar` escrevia esse formato e o separador
seguinte o apagava, e nenhum teste lia o bloco desenhado. O documento dizia "centralizado" e a tela
mostrava à esquerda (o D1 do `docs/ROADMAP_MESA_DE_TEXTO.md`).

Este módulo não decide nada: ele pergunta às mesmas funções puras que o desenho usa
(`texto_formato.formato_de` e `bloco_de`) o que **deveria** estar em cada caractere e em cada bloco,
lê o que **está**, e devolve as diferenças em frases. Lista vazia é a tela concordando com o
documento.

**O parágrafo é o bloco de `rico`, e não o bloco do Qt.** Depois de um `Enter` no meio de um
parágrafo lido, os dois blocos do Qt continuam no mesmo bloco de `rico`; por isso o formato
esperado de um bloco do Qt é o da corrida em que ele começa, e não um formato guardado por bloco.
"""

from __future__ import annotations

from PyQt6.QtGui import QFont, QTextBlockFormat, QTextCharFormat, QTextCursor

from chess_diagram_ocr.qt import texto_formato
from chess_diagram_ocr.qt.painel_de_texto import OBJETO, PainelDeTexto
from chess_diagram_ocr.text import rico

__all__ = ["divergencias"]


def _corrida_em(doc: rico.DocumentoRico, deslocamento: int) -> rico.Corrida | None:
    comeco = 0
    for corrida in doc.corridas:
        fim = comeco + len(corrida.texto)
        if comeco <= deslocamento < fim:
            return corrida
        comeco = fim
    return None


def _do_caractere(esperado: QTextCharFormat, lido: QTextCharFormat) -> list[str]:
    """As propriedades que `formato_de` escreve, uma a uma."""
    erros: list[str] = []
    negrito = esperado.fontWeight() >= QFont.Weight.DemiBold.value
    if (lido.fontWeight() >= QFont.Weight.DemiBold.value) != negrito:
        erros.append(f"negrito {not negrito} na tela")
    for nome, ler in (
        ("itálico", QTextCharFormat.fontItalic),
        ("sublinhado", QTextCharFormat.fontUnderline),
        ("tachado", QTextCharFormat.fontStrikeOut),
    ):
        if ler(lido) != ler(esperado):
            erros.append(f"{nome} {ler(lido)} na tela")
    if round(lido.fontPointSize()) != round(esperado.fontPointSize()):
        erros.append(f"corpo {lido.fontPointSize()} na tela, {esperado.fontPointSize()} no documento")
    if lido.fontFamilies() != esperado.fontFamilies():
        erros.append(f"família {lido.fontFamilies()} na tela, {esperado.fontFamilies()} no documento")
    if lido.foreground().color().name() != esperado.foreground().color().name():
        erros.append(f"cor {lido.foreground().color().name()} na tela, {esperado.foreground().color().name()} no documento")
    tem_fundo = esperado.background().style().value != 0
    if tem_fundo != (lido.background().style().value != 0) or (
        tem_fundo and lido.background().color().name() != esperado.background().color().name()
    ):
        erros.append("realce diferente na tela")
    return erros


def _do_bloco(esperado: QTextBlockFormat, lido: QTextBlockFormat) -> list[str]:
    """As quatro propriedades que `bloco_de` escreve."""
    erros: list[str] = []
    if int(lido.alignment().value) != int(esperado.alignment().value):
        erros.append(f"alinhamento {int(lido.alignment().value)} na tela, {int(esperado.alignment().value)} no documento")
    for nome, ler in (
        ("recuo de primeira linha", QTextBlockFormat.textIndent),
        ("margem esquerda", QTextBlockFormat.leftMargin),
        ("margem de cima", QTextBlockFormat.topMargin),
    ):
        if round(ler(lido)) != round(ler(esperado)):
            erros.append(f"{nome} {ler(lido)} na tela, {ler(esperado)} no documento")
    return erros


def divergencias(painel: PainelDeTexto) -> list[str]:
    """Tudo em que a tela discorda do documento, em frases. Vazia = concordam."""
    doc = painel.documento
    qdoc = painel.editor.document()
    base = painel._base
    erros: list[str] = []

    comeco = 0
    for corrida in doc.corridas:
        esperado = texto_formato.formato_de(corrida, base=base)
        for k, letra in enumerate(corrida.texto):
            if letra == "\n":
                continue
            posicao = painel._mapa.posicao(comeco + k)
            cursor = QTextCursor(qdoc)
            cursor.setPosition(posicao + 1)  # `charFormat` é o do caractere **antes** do cursor
            for erro in _do_caractere(esperado, cursor.charFormat()):
                erros.append(f"caractere {comeco + k} ({letra!r}): {erro}")
        comeco += len(corrida.texto)

    bloco = qdoc.begin()
    while bloco.isValid():
        texto = bloco.text()
        if OBJETO in texto:
            # A figura mora no bloco da marca que vem logo abaixo dela (S-602).
            seguinte = bloco.next()
            corrida = _corrida_em(doc, painel._mapa.deslocamento(seguinte.position())) if seguinte.isValid() else None
            onde = f"bloco {bloco.blockNumber()} (miniatura)"
        elif not texto:
            corrida = None  # a linha em branco do separador (S-601)
            onde = f"bloco {bloco.blockNumber()} (em branco)"
        else:
            corrida = _corrida_em(doc, painel._mapa.deslocamento(bloco.position()))
            onde = f"bloco {bloco.blockNumber()} ({texto[:20]!r})"
        esperado = painel.formato_de_bloco(corrida)
        erros.extend(f"{onde}: {erro}" for erro in _do_bloco(esperado, bloco.blockFormat()))
        bloco = bloco.next()
    return erros
