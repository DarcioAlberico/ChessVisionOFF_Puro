"""A lista de lances da sala de estudo: um `QTextBrowser` com âncoras e variantes dobráveis (S-866).

**Saiu de `qt/painel_de_estudo.py` com os três atributos que eram só dela**: os trechos desenhados, as
variantes que eles formam e as que estão dobradas (S-516). Quem decide o que a lista mostra continua
sendo `ui/estudo_lista.py`, conferido contra o `StringExporter`, e quem decide o que some numa dobra
é `ui/estudo_dobra.py`; aqui fica o HTML e a memória do que foi desenhado.

**O clique é resolvido na hora, e por isso o caminho não vai na âncora.** O `href` leva o índice do
trecho, e o painel pergunta a esta lista, no clique, que caminho aquele índice tem agora -- promover
ou apagar variante muda os índices de variação, e um caminho guardado na montagem apontaria para o
lance que ocupou o lugar do antigo (S-268).
"""

from __future__ import annotations

import html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTextBrowser, QWidget

from chess_diagram_ocr.estudo import Caminho, Estudo
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import estudo_dobra, estudo_lista, tipografia, tokens
from chess_diagram_ocr.ui.sala_declarada import PAPEIS_COLADOS, RECUO_POR_NIVEL

__all__ = ["ListaDeLances"]


class ListaDeLances(QTextBrowser):
    """Os lances do estudo, com a linha principal em negrito e as variantes recuadas e dobráveis."""

    def __init__(self, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.setOpenLinks(False)
        # Uma parada do Tab, e não uma por lance: o `QTextBrowser` anda de âncora em âncora com o
        # Tab (180 teclas numa partida de 120 lances), e de volta, com o Shift+Tab, não sai mais
        # dela -- medido: 2.000 teclas (OCR_UI ciclo 2, fase 5, crítico do ciclo 4, o portão
        # `teclado` com a tecla de verdade). Os lances se percorrem pelas setas da sala, e o clique
        # num lance continua levando a ele.
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                     | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.setFont(tema.fonte_atual(tipografia.CORPO))
        self.trechos: tuple[estudo_lista.Trecho, ...] = ()
        self.variantes: tuple[estudo_dobra.Variante, ...] = ()
        self.dobradas: set[Caminho] = set()
        """As variantes dobradas, por caminho do primeiro lance delas (S-516).

        Estado de **vista**: não entra na pilha de desfazer, não vai para o PGN e não sobrevive
        à sessão. Caminho que deixou de existir simplesmente não casa com variante nenhuma."""

    def desenhar(self, estudo: Estudo, *, treinando: bool) -> None:
        """Refaz a lista inteira e **reancora os trechos** (S-274).

        O índice do trecho vai no `href` e é resolvido **na hora do clique**: promover ou apagar
        variante muda os índices de variação, e um caminho guardado na montagem apontaria para o
        lance que ocupou o lugar do antigo (S-268).
        """
        self.trechos = estudo_lista.trechos(estudo)
        corrente = estudo.caminho()
        if treinando:
            # O corte do treino (S-290): o que vem depois do lance corrente some da tela e continua
            # na árvore. É o item inteiro -- "a linha some, e o tabuleiro cobra o lance".
            self.trechos = estudo_lista.ate(self.trechos, corrente)

        secundario = tema.cor_atual(tokens.TEXTO_SECUNDARIO)
        fundo = tema.cor_atual(tokens.SUPERFICIE_DICA)
        # As variantes dobradas (S-516). O miolo some, os dois parênteses ficam, e o `(` é o
        # controle: clicar nele desdobra. Quem decide o que some é `ui/estudo_dobra`, e o lance
        # corrente nunca some -- ver o cabeçalho de lá.
        self.variantes = estudo_dobra.variantes(self.trechos)
        ocultos = estudo_dobra.escondidos(self.trechos, self.dobradas, corrente)
        # **Dobrada de verdade**, e não só declarada: a que contém o lance corrente continua na
        # lista de dobradas e é desenhada aberta, então ela não pode mostrar o `(…)`.
        dobrados = {
            variante.abre
            for variante in self.variantes
            if variante.fecha > variante.abre + 1 and variante.abre + 1 in ocultos
        }
        partes: list[str] = []
        aberto: int | None = None
        for indice, trecho in enumerate(self.trechos):
            if not trecho.texto or indice in ocultos:
                continue
            # **Cada corrida de mesmo recuo é um bloco, e o bloco é o que recua** (S-514). Era um
            # `margin-left` no `<span>`, e o `QTextDocument` descarta margem em elemento inline: o
            # número era lido, estava certo, e não pintava um pixel.
            #
            # A variante abre bloco mesmo no mesmo recuo, senão duas irmãs -- `( 2. Bc4 ) ( 2. d4 )`
            # -- correriam na mesma linha. É o que os dois `<br>` de antes faziam, ditos pela
            # estrutura em vez de por quebra solta.
            comeca = trecho.papel == estudo_lista.ABRE
            if aberto != trecho.recuo or comeca:
                if aberto is not None:
                    partes.append("</div>")
                partes.append(f'<div style="margin-left:{trecho.recuo * RECUO_POR_NIVEL}px">')
                aberto = trecho.recuo
            partes.append(_trecho_em_html(indice, trecho, secundario, fundo, corrente))
            if indice in dobrados:
                partes.append(
                    f'<a href="dobra:{indice}" style="text-decoration:none">'
                    f'<span style="color:{secundario}">…&nbsp;</span></a>'
                )
        if aberto is not None:
            partes.append("</div>")
        self.setHtml("".join(partes))
        self.scrollToAnchor("corrente")

    def caminho_do_trecho(self, indice: int) -> Caminho | None:
        """O caminho que o trecho `indice` tem **agora**, ou `None` se ele não é navegável."""
        if not 0 <= indice < len(self.trechos):
            return None
        return self.trechos[indice].caminho

    def texto_do_lance(self, caminho: Caminho) -> str:
        """O lance daquele caminho como a lista o escreve, com o número colado (S-517).

        **O texto sai dos mesmos trechos que a lista desenha**, e não de uma segunda formatação:
        `estudo_lista.trecho_do_caminho` acha o trecho do nó, e o `NUMERO` colado nele -- quando há
        um -- é o mesmo `12.` que a lista mostra. Uma segunda montagem daria `12. Ba4` aqui e
        `12...Ba4` ali no dia em que a numeração de variante mudasse.

        Na raiz o trecho é o `RAIZ`, e o texto dele já é "posição do diagrama" ou "posição inicial"
        conforme o estudo tenha vindo do livro -- que é exatamente o que se quer ler ali.
        """
        indice = estudo_lista.trecho_do_caminho(self.trechos, caminho)
        if indice < 0:
            return ""
        trecho = self.trechos[indice]
        anterior = self.trechos[indice - 1] if indice else None
        numero = (
            anterior.texto
            if anterior is not None
            and anterior.papel == estudo_lista.NUMERO
            and anterior.caminho == trecho.caminho
            else ""
        )
        return f"{numero}{trecho.texto}".strip()

    # ------------------------------------------------------------------ dobrar variantes (S-516)

    def alternar_uma_dobra(self, indice: int) -> bool:
        """Dobra ou desdobra a variante cujo `(` está no trecho `indice`. **A identidade é o caminho.**

        Devolve se havia variante ali: a lista pode ter sido refeita entre o desenho e o clique.
        """
        alvo = next((v for v in self.variantes if v.abre == indice), None)
        if alvo is None:
            return False
        if alvo.chave in self.dobradas:
            self.dobradas.discard(alvo.chave)
        else:
            self.dobradas.add(alvo.chave)
        return True

    def alternar_todas(self) -> str:
        """Dobra **todas** as variantes, ou desdobra todas se já houver alguma dobrada. Devolve a
        frase do rodapé."""
        if self.dobradas:
            self.dobradas.clear()
            return "Variantes desdobradas."
        if self.variantes:
            self.dobradas = {variante.chave for variante in self.variantes}
            return f"{len(self.dobradas)} variante(s) dobrada(s)."
        return "Este estudo não tem variante para dobrar."


def _trecho_em_html(
    indice: int,
    trecho: estudo_lista.Trecho,
    secundario: str,
    fundo: str,
    corrente: object,
) -> str:
    """Um trecho como HTML: cor por papel, e âncora quando ele é navegável.

    **Cor e peso saem de `ui/tokens.py` e de `ui/tipografia.py`**, como as tags do outro lado:
    nada de hexadecimal escrito aqui. A linha principal em negrito e as variantes em peso
    normal é a hierarquia sem gastar matiz -- o recurso escasso do programa depois da S-158.

    **O recuo não está mais aqui** (S-514): quem recua é o bloco que `desenhar` abre, porque margem
    em `<span>` o `QTextDocument` ignora.
    """
    estilo: list[str] = []
    apagados = (
        estudo_lista.NUMERO,
        estudo_lista.ABRE,
        estudo_lista.FECHA,
        estudo_lista.RESULTADO,
        estudo_lista.RAIZ,
    )
    if trecho.papel in apagados:
        estilo.append(f"color:{secundario}")
    if trecho.papel == estudo_lista.COMENTARIO:
        estilo.append(f"color:{secundario}")
        estilo.append("font-size:smaller")
    if trecho.papel == estudo_lista.NAG or (trecho.papel == estudo_lista.LANCE and trecho.nivel == 0):
        estilo.append("font-weight:bold")
    e_corrente = trecho.caminho is not None and trecho.caminho == corrente and trecho.papel in (
        estudo_lista.LANCE,
        estudo_lista.RAIZ,
    )
    if e_corrente:
        estilo.append(f"background-color:{fundo}")
        estilo.append(f"color:{tokens.sobre_superficie(fundo)}")

    # **Só o que gruda no vizinho leva `&nbsp;`** (S-515). Era *todo* espaço, e sem nenhuma
    # fronteira de palavra o `QTextEdit` -- `WrapAtWordBoundaryOrAnywhere` de fábrica -- quebrava
    # em qualquer caractere: `O-O` saía `O-`/`O`, e a frase do comentário, `guard`/`am`. Quais
    # papéis grudam é decisão de `ui/sala_declarada.PAPEIS_COLADOS`.
    texto = html.escape(trecho.texto)
    if trecho.papel in PAPEIS_COLADOS:
        texto = texto.replace(" ", "&nbsp;")
    marca = ' name="corrente"' if e_corrente else ""
    corpo = f'<span style="{";".join(estilo)}">{texto}</span>' if estilo else f"<span>{texto}</span>"
    if trecho.papel == estudo_lista.ABRE:
        # **O `(` é o controle da dobra** (S-516), e não um glifo novo ao lado dele. Um `▸`
        # sairia de fonte de queda -- é o que a S-508 mediu nos quatro botões de navegação --,
        # e um triângulo desenhado ao lado de cada variante seria ruído numa lista de notação.
        # O parêntese já delimita a variante; o que faltava era ele responder ao clique.
        return f'<a href="dobra:{indice}" style="text-decoration:none">{corpo}</a>'
    if trecho.caminho is None:
        return f"<a{marca}>{corpo}</a>" if marca else corpo
    return f'<a href="trecho:{indice}"{marca} style="text-decoration:none">{corpo}</a>'
