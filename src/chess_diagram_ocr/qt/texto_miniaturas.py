"""Os diagramas no texto: a miniatura, a preferência da vista, a dica, o menu e o diagrama que vai à sala (S-865).

**Saiu de `qt/painel_de_texto.py` com a preferência dos diagramas** -- onde eles ficam quando ninguém
os alinhou (S-620), o tamanho da miniatura (S-623) e o texto ao lado (S-624) --, que é vista e não
documento: trocar não grava nada. A marca `[Diagrama N]` é texto do documento; a figura antes dela
é do widget, e morre com ele.

As funções de módulo são sem Qt: o recorte do diagrama na folha renderizada e o desenho dele a
partir da FEN são os mesmos para a miniatura na tela e para o PNG da exportação.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
from PyQt6.QtGui import (
    QAction,
    QHelpEvent,
    QMouseEvent,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextDocumentFragment,
    QTextFormat,
    QTextImageFormat,
)
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QToolTip

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.imagens import pixmap_de_rgb
from chess_diagram_ocr.text import rico
from chess_diagram_ocr.ui.livros import chave_do_livro
from chess_diagram_ocr.ui.texto_declarado import (
    DIAGRAMAS_A_ESQUERDA,
    DIAGRAMAS_AO_CENTRO,
    NOME_DO_TAMANHO,
    TAMANHO_DA_MINIATURA_PADRAO,
    TAMANHOS_DA_MINIATURA,
    alinhamento_dos_diagramas,
    largura_da_miniatura,
    proximo_tamanho_da_miniatura,
)

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

logger = logging.getLogger(__name__)

__all__ = ["LARGURA_DA_MINIATURA", "MiniaturasDoTexto", "png_da_posicao", "posicao_de", "recorte_da_folha"]

LARGURA_DA_MINIATURA = TAMANHOS_DA_MINIATURA[TAMANHO_DA_MINIATURA_PADRAO]
"""A miniatura do diagrama dentro do texto, em pixel, no corpo do sistema.

Grande o bastante para reconhecer a posição, pequena o bastante para a linha seguinte caber na
tela. É o mesmo alvo de `texto_panel._miniatura`."""


def recorte_da_folha(folha: np.ndarray, bloco: object, *, dpi: int) -> np.ndarray | None:
    """O pedaço da folha renderizada em que o bloco está, ou `None` sem `bbox` útil.

    **O bbox do bloco está em pontos e a folha em pixels**, e o fator entre os dois é o DPI com
    que ela foi renderizada. Usar outro aqui recortaria o lugar errado da folha em silêncio.
    Pura, e sem Qt: é a mesma função para a miniatura na tela e para o PNG da exportação.
    """
    bbox = getattr(bloco, "bbox", None)
    if bbox is None:
        return None
    fator = dpi / 72.0
    altura, largura = folha.shape[:2]
    x0 = max(0, int(bbox[0] * fator))
    y0 = max(0, int(bbox[1] * fator))
    x1 = min(largura, int(bbox[2] * fator))
    y1 = min(altura, int(bbox[3] * fator))
    if x1 <= x0 or y1 <= y0:
        return None
    return folha[y0:y1, x0:x1]


def posicao_de(doc: rico.DocumentoRico, corrida: rico.Corrida) -> str:
    """O campo de peças do bloco desta marca, ou `""` quando ninguém o leu."""
    return str(getattr(doc.bloco_de(corrida), "placement", "") or "")


def png_da_posicao(placement: str, *, lado_px: int) -> bytes | None:
    """O diagrama desenhado da FEN, em PNG, ou `None` sem posição ou quando o desenho falha.

    Desenha com as peças do próprio programa (`desenho_de_diagrama`, sem Qt): a mesma figura que
    a exportação do livro usa. O `import` é tardio porque ele carrega a Pillow e o conjunto de
    peças, e a aba abre sem precisar deles.
    """
    if not placement:
        return None
    try:
        from chess_diagram_ocr.desenho_de_diagrama import png_do_diagrama

        return png_do_diagrama(placement, lado_px=lado_px)
    except Exception as erro:  # noqa: BLE001 - a figura é conforto; a marca fica
        logger.debug("Diagrama não desenhado da posição %r: %s", placement, erro)
        return None


def _url(nome: str):  # noqa: ANN202 - QUrl, importado tarde para o módulo abrir sem QtCore
    from PyQt6.QtCore import QUrl

    return QUrl(nome)


class MiniaturasDoTexto(QObject):
    """A figura de cada `[Diagrama N]`, a preferência dos diagramas, a dica, o menu e o diagrama que vai à sala."""

    def __init__(self, aba: PainelDeTexto) -> None:
        super().__init__(aba)
        self._aba = aba
        self.diagramas = DIAGRAMAS_AO_CENTRO
        """«Diagramas no texto» (S-620). É vista e preferência, e não documento: trocar não grava nada."""
        self.tamanho_da_miniatura = TAMANHO_DA_MINIATURA_PADRAO
        """O tamanho da miniatura (S-623): `ui/texto_declarado.TAMANHOS_DA_MINIATURA`."""
        self._texto_ao_lado = False
        """O texto contorna o diagrama que se desenha à esquerda (S-624). Vista, como a preferência da S-620."""

    # --------------------------------------------------------------------- a figura de cada marca

    def inserir_miniatura(self, cursor: QTextCursor, corrida: rico.Corrida) -> None:
        """A imagem do diagrama, **antes** da marca -- e a marca continua no texto.

        Parece redundante numa tela onde a imagem já aparece, e é o contrário: a imagem é do
        widget e morre com ele, a marca é do texto e sobrevive a salvar, copiar e colar. Um
        editor que trocasse a marca pela imagem perderia o diagrama na primeira exportação.

        A imagem **não** entra no mapa: ela não é do documento, e é justamente por isso que
        `texto_espelho.Mapa` existe.
        """
        figura = self._imagem_do_diagrama(corrida)
        if figura is None:
            return
        mapa = figura.scaledToWidth(self.largura_da_miniatura(), Qt.TransformationMode.SmoothTransformation)
        nome = f"diagrama:{corrida.bloco}"
        documento = cursor.document()
        if documento is not None:
            documento.addResource(QTextDocument.ResourceType.ImageResource.value, _url(nome), mapa)
        # Com a medida escrita no formato, e não só no pixmap: é o que o Qt usa para o leiaute, e é
        # o que um teste consegue ler de volta sem desenhar a tela.
        imagem = QTextImageFormat()
        imagem.setName(nome)
        imagem.setWidth(mapa.width())
        imagem.setHeight(mapa.height())
        # O texto alternativo (item 14): é o que o leitor de tela diz no lugar da figura, e o que
        # o `toHtml` escreve no `alt`. A marca vem logo abaixo, mas a marca é texto do documento, e
        # a figura precisa dizer por si o que é.
        numero = int(getattr(self._aba.documento.bloco_de(corrida), "indice", corrida.bloco)) + 1
        folha = "" if self._aba._pagina is None else f" da folha {int(self._aba._pagina.pagina) + 1}"
        imagem.setProperty(QTextFormat.Property.ImageAltText, f"Diagrama {numero}")
        imagem.setProperty(QTextFormat.Property.ImageTitle, f"Diagrama {numero}{folha}")
        # **A figura tem bloco próprio** (S-602): é ele que `EspelhoDaFolha.formatar_blocos` alinha com a marca.
        # Depois de um separador ela já começa um bloco em branco; sem separador antes -- `rico.editar`
        # deixa apagá-lo e escrever `Antes.[Diagrama 1]` -- ela cairia no meio da prosa.
        if cursor.positionInBlock() > 0:
            cursor.insertBlock()
        if self._flutua(corrida):
            self._inserir_flutuante(cursor, imagem)
        else:
            cursor.insertImage(imagem)
        cursor.insertBlock()

    def _flutua(self, corrida: rico.Corrida) -> bool:
        """A figura desta marca flutua à esquerda, com o texto ao lado (S-624)? Só a que se desenha à esquerda."""
        if not self._texto_ao_lado:
            return False
        padrao = alinhamento_dos_diagramas(self.diagramas)
        return rico.alinhamento_efetivo(corrida, padrao_do_diagrama=padrao) == rico.ALINHAMENTO_ESQUERDA

    @staticmethod
    def _inserir_flutuante(cursor: QTextCursor, imagem: QTextImageFormat) -> None:
        """A figura flutuante, **pelo importador de HTML do Qt**, que é o único que a sabe fazer (S-624).

        A figura que flutua é um `QTextImageFormat` que aponta para um objeto de quadro com
        `FloatLeft`, e o quadro tem de estar registrado no documento: `QTextDocument.createObject`
        chamado do Python devolve um quadro de índice −1, que o leiaute ignora. O `<img align=left>`
        registra o quadro e, ao contrário do `QTextFrame` inserido pelo cursor, **não** põe
        `U+FDD0`/`U+FDD1` no texto cru -- a figura continua sendo um `texto_espelho.OBJETO` só, e `texto_espelho.Mapa` e
        `texto_espelho._texto_da_tela` não mudam. O texto alternativo e o título entram depois, por mescla, que
        preserva o índice do objeto.
        """
        largura, altura = round(imagem.width()), round(imagem.height())
        cursor.insertFragment(
            QTextDocumentFragment.fromHtml(f'<img src="{imagem.name()}" width="{largura}" height="{altura}" align="left">')
        )
        figura = QTextCursor(cursor)
        figura.movePosition(QTextCursor.MoveOperation.PreviousCharacter, QTextCursor.MoveMode.KeepAnchor)
        extra = QTextCharFormat()
        for propriedade in (QTextFormat.Property.ImageAltText, QTextFormat.Property.ImageTitle):
            extra.setProperty(propriedade, imagem.property(propriedade))
        figura.mergeCharFormat(extra)

    def _imagem_do_diagrama(self, corrida: rico.Corrida) -> QPixmap | None:
        """A figura da miniatura: **o recorte da folha, ou o desenho da posição lida**.

        O recorte é a verdade impressa e vem primeiro. Sem folha -- o `.cvtxt` aberto com o livro
        fora do lugar, ou noutra máquina -- a miniatura nascia vazia mesmo quando o OCR de
        diagramas do produto já tinha lido a posição (item 6). Aí ela é desenhada da FEN, com as
        peças que o próprio programa desenha (`desenho_de_diagrama`), e a pessoa vê o diagrama em
        vez de uma marca solta. É desenho e não leitura: quem corrige a posição corrige na aba Livro.
        """
        recorte = self._recorte(corrida)
        if recorte is not None:
            return pixmap_de_rgb(recorte)
        png = png_da_posicao(posicao_de(self._aba.documento, corrida), lado_px=self.largura_da_miniatura())
        if png is None:
            return None
        mapa = QPixmap()
        return mapa if mapa.loadFromData(png, "PNG") and not mapa.isNull() else None

    def tem_miniatura(self, corrida: rico.Corrida) -> bool:
        """Há figura para esta marca -- recorte da folha ou posição lida -- sem desenhá-la."""
        return self._recorte(corrida) is not None or bool(posicao_de(self._aba.documento, corrida))

    def largura_da_miniatura(self) -> int:
        """A miniatura **acompanha o zoom da vista** (S-264): a mesma razão que a letra.

        `LARGURA_DA_MINIATURA` é a largura no corpo do sistema; com a vista em +3 degraus sobre
        um corpo de 9 pt a miniatura cresce um terço, e com a vista em -2 ela encolhe. Sem isto,
        aproximar a folha deixava a letra do tamanho que a pessoa pediu e o diagrama do tamanho de
        antes -- cada vez menor em relação ao texto que fala dele.
        """
        corpo_do_sistema = max(1, tema.fonte_base()[0])
        corpo_da_vista = self._aba.espelho.base[0] if self._aba.espelho.base is not None else corpo_do_sistema
        return max(48, round(largura_da_miniatura(self.tamanho_da_miniatura) * corpo_da_vista / corpo_do_sistema))

    def _recorte(self, corrida: rico.Corrida) -> np.ndarray | None:
        """O pedaço da folha em que o diagrama está, ou `None` sem folha renderizada.

        **O bbox do bloco está em pontos e a folha em pixels**, e o fator entre os dois é o DPI
        com que ela foi renderizada -- é por isso que ele é o mesmo `self._aba._dpi` dos dois lados.
        Usar outro aqui recortaria o lugar errado da folha em silêncio.

        Sem imagem a marca continua no texto e o editor abre igual: é o mesmo contrato de
        `texto_panel._inserir_miniatura`, e é o que faz a aba funcionar num checkout sem PDF.
        """
        if self._aba._pagina_rgb is None:
            return None
        return recorte_da_folha(self._aba._pagina_rgb, self._aba.documento.bloco_de(corrida), dpi=self._aba._dpi)

    # ----------------------------------------------------------- os diagramas no texto (Fase 92)

    @property
    def diagramas_a_esquerda(self) -> bool:
        return self.diagramas == DIAGRAMAS_A_ESQUERDA

    def definir_diagramas(self, preferencia: str) -> None:
        """«Diagramas no texto» (S-620). Redesenha **sem** tornar a folha "por gravar": não é edição."""
        preferencia = DIAGRAMAS_A_ESQUERDA if preferencia == DIAGRAMAS_A_ESQUERDA else DIAGRAMAS_AO_CENTRO
        if preferencia == self.diagramas:
            return
        self.diagramas = preferencia
        self._aba.vista.redesenhar()

    @property
    def texto_ao_lado(self) -> bool:
        return self._texto_ao_lado

    def definir_texto_ao_lado(self, ligado: bool) -> None:
        """O texto ao lado do diagrama à esquerda (S-624). Vista: redesenha sem tornar a folha «por gravar»."""
        if bool(ligado) == self._texto_ao_lado:
            return
        self._texto_ao_lado = bool(ligado)
        self._aba.vista.redesenhar()

    def alternar_texto_ao_lado(self) -> None:
        self.definir_texto_ao_lado(not self._texto_ao_lado)
        self._aba.estado.emit(
            "O texto corre ao lado dos diagramas que ficam à esquerda."
            if self._texto_ao_lado
            else "Os diagramas à esquerda voltam a ter a linha só para eles."
        )

    def interruptores_da_vista(self) -> dict[str, bool]:
        """As marcas que o menu Texto mostra para a vista desta aba, para a janela pô-las ao abrir."""
        return {
            "diagramas_a_esquerda": self.diagramas_a_esquerda,
            "texto_ao_lado": self._texto_ao_lado,
            "ler_ao_chegar": self._aba.caderno.ler_ao_chegar,
        }

    def alternar_diagramas_a_esquerda(self) -> None:
        self.definir_diagramas(DIAGRAMAS_AO_CENTRO if self.diagramas_a_esquerda else DIAGRAMAS_A_ESQUERDA)
        self._aba.estado.emit(
            "Os diagramas que ninguém alinhou ficam à esquerda do texto."
            if self.diagramas_a_esquerda
            else "Os diagramas que ninguém alinhou voltam ao centro do texto."
        )

    def definir_tamanho_da_miniatura(self, tamanho: str) -> None:
        """O tamanho da miniatura (S-623). Vista, e não documento: não grava nada nem muda a exportação."""
        tamanho = tamanho if tamanho in TAMANHOS_DA_MINIATURA else TAMANHO_DA_MINIATURA_PADRAO
        if tamanho == self.tamanho_da_miniatura:
            return
        self.tamanho_da_miniatura = tamanho
        self._aba.vista.redesenhar()

    def mudar_tamanho_da_miniatura(self) -> None:
        self.definir_tamanho_da_miniatura(proximo_tamanho_da_miniatura(self.tamanho_da_miniatura))
        self._aba.estado.emit(
            f"Miniaturas {NOME_DO_TAMANHO[self.tamanho_da_miniatura]} "
            f"({TAMANHOS_DA_MINIATURA[self.tamanho_da_miniatura]} px no corpo do sistema)."
        )

    def alinhar_os_diagramas_da_folha(self, alinhamento: str) -> None:
        """Todos os diagramas desta folha num passo só de desfazer (S-621)."""
        novo = rico.alinhar_diagramas(self._aba.documento, alinhamento)
        if novo is self._aba.documento:
            self._aba.estado.emit("Os diagramas desta folha já estão assim.")
            return
        quantos = rico.diagramas_a_alinhar(self._aba.documento, alinhamento)
        self._aba.espelho.aplicar(novo)
        self._aba.estado.emit(f"{quantos} diagrama(s) desta folha realinhado(s); Ctrl+Z desfaz os {quantos} de uma vez.")

    def alinhar_diagramas_do_caderno(self, alinhamento: str) -> int:
        """Todos os diagramas de todas as folhas do caderno (S-621), com a conta antes. Devolve quantas folhas mudaram.

        A pergunta diz quantos diagramas de quantas folhas, e cada folha mudada guarda a de antes como
        `anterior` (S-611). A folha da tela muda pela pilha, para `Ctrl+Z` desfazê-la como as outras edições.
        """
        from chess_diagram_ocr.qt import dialogos

        cad = self._aba.caderno.aberto
        if cad is None or cad.somente_leitura:
            self._aba.estado.emit("Abra um livro com caderno para alinhar os diagramas dele.")
            return 0
        self._aba.caderno.guardar_a_folha()
        mudar: list[tuple[int, rico.DocumentoRico, int]] = []
        for estado in cad.folhas():
            doc = cad.folha(estado.pagina)
            if doc is not None and (quantos := rico.diagramas_a_alinhar(doc, alinhamento)):
                mudar.append((estado.pagina, doc, quantos))
        if not mudar:
            self._aba.estado.emit("Nenhum diagrama do caderno muda com isso.")
            return 0
        total = sum(q for _p, _d, q in mudar)
        destino = {"esquerda": "à esquerda", "centro": "ao centro"}.get(alinhamento, "como a preferência")
        if not dialogos.ha_quem_responda():
            return 0
        resposta = QMessageBox.question(
            self._aba,
            "Texto",
            f"Alinhar {total} diagrama(s) de {len(mudar)} folha(s) {destino}? A versão de antes de cada folha "
            "fica como anterior no caderno.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return 0
        na_tela = None if self._aba.caderno.caderno_da_tela() is None else int(self._aba.documento.origem.pagina)  # type: ignore[union-attr]
        for pagina, doc, _quantos in mudar:
            if pagina == na_tela:
                cad.visitar(pagina)
                self._aba.espelho.aplicar(rico.alinhar_diagramas(self._aba.documento, alinhamento))
                self._aba.caderno.guardar_a_folha()
                continue
            guardada = cad.estado(pagina)
            cad.visitar(pagina)
            cad.gravar(
                rico.alinhar_diagramas(doc, alinhamento),
                estado=None if guardada is None else guardada.estado,
                correcoes=0 if guardada is None else guardada.correcoes,
            )
        self._aba.caderno.mostrar_indice()
        self._aba.estado.emit(f"{total} diagrama(s) de {len(mudar)} folha(s) alinhado(s) {destino}.")
        return len(mudar)

    # -------------------------- as posições e a notação que a janela dá e pergunta (S-283, S-595)

    def definir_posicoes(self, pagina: int, posicoes: Sequence[str]) -> None:
        """O campo de peças de cada diagrama da folha, como o OCR de diagramas do produto leu.

        A aba Livro lê a posição com o classificador de peças; esta aba só sabia **onde** cada
        diagrama está. Com a FEN no bloco, o `.cvtxt` a guarda, o `.md` e o `.html` a escrevem
        (item 5) e a miniatura pode nascer dela quando o livro não está. Chega pela janela a cada
        leitura de diagramas (`_chegaram_itens`), em qualquer ordem em relação à leitura do texto:
        a folha que já está na tela recebe na hora, **sem virar alteração por gravar** -- a posição
        é leitura, não edição.
        """
        chave = (chave_do_livro(self._aba._pdf), int(pagina))
        self._aba._posicoes[chave] = tuple(str(p or "") for p in posicoes)
        if (
            self._aba._pagina is None
            or int(self._aba._pagina.pagina) != int(pagina)
            or chave_do_livro(self._aba._pagina.documento) != chave[0]
        ):
            return
        nova = self._aba._pagina.com_posicoes(self._aba._posicoes[chave])
        if nova is self._aba._pagina:
            return
        self._aba._pagina = nova
        self._aba.documento = rico.DocumentoRico(corridas=self._aba.documento.corridas, origem=nova)
        if self._aba._documento_gravado.origem is not None:
            self._aba._documento_gravado = rico.DocumentoRico(corridas=self._aba._documento_gravado.corridas, origem=nova)
        self._aba.espelho.desenhar(selecao=self._aba.espelho.selecao_atual())
        self._aba.vista.atualizar_status()

    def inserir_diagramas_do_livro(self, pagina: int, faltam: Sequence[tuple[str, str]]) -> int:
        """Os diagramas que o PDF perdeu, postos na folha antes da legenda de cada um (S-595).

        `faltam` é `(lance da legenda, campo de peças)`, do PGN do livro. A marca vai para o começo
        da linha «Position after: <lance>» -- é onde a imagem estaria, logo acima da legenda -- e a
        figura nasce da FEN (`rico.inserir_diagrama`). **É uma edição**, numa jogada só: `Ctrl+Z`
        tira todos, e a folha passa a ter o que gravar.

        Fica de fora o lance cuja legenda a folha não tem (o leitor de texto a partiu, ou a folha é
        de outra página) e a posição que a folha já mostra -- pedir duas vezes não duplica. Devolve
        quantos entraram.
        """
        from chess_diagram_ocr.livro_com_pgn import legenda_da_linha
        from chess_diagram_ocr.pgn_do_livro import lance_da_legenda

        if self._aba._pagina is None or int(self._aba._pagina.pagina) != int(pagina) or not faltam:
            return 0
        legendas: dict[str, int] = {}  # o lance da legenda -> onde a linha dela começa
        comeco = 0
        for linha in self._aba.documento.para_texto().split("\n"):
            lance = lance_da_legenda(legenda_da_linha(linha))
            if lance:
                legendas.setdefault(lance, comeco)
            comeco += len(linha) + 1
        ja_na_folha = {posicao_de(self._aba.documento, corrida) for corrida in self._aba.documento.diagramas}
        lugares = sorted(
            (legendas[lance], placement)
            for lance, placement in ((lance_da_legenda(lance), placement) for lance, placement in faltam)
            if lance in legendas and placement not in ja_na_folha
        )
        novo, andou = self._aba.documento, 0
        for onde, placement in lugares:
            antes = len(novo.para_texto())
            novo = rico.inserir_diagrama(novo, onde + andou, placement)
            andou += len(novo.para_texto()) - antes
        if novo is self._aba.documento:
            return 0
        self._aba.espelho.aplicar(novo)
        sem_legenda = [lance for lance, _ in faltam if lance_da_legenda(lance) not in legendas]
        fora = f" Sem a legenda na folha lida, ficaram de fora: {', '.join(sem_legenda)}." if sem_legenda else ""
        self._aba.estado.emit(f"{len(lugares)} diagrama(s) do PGN do livro posto(s) na folha; desfazer os tira.{fora}")
        return len(lugares)

    def notacao_do_diagrama(self, pagina: int, diagrama: int) -> str:
        """A notação que o livro imprimiu ao lado daquele diagrama, ou `""` (S-283).

        **É o vínculo da S-249 com um cliente.** `BlocoDeTexto.legenda_de` diz de qual diagrama
        cada parágrafo é a legenda, e até a sala de estudo isso só pintava o estilo `legenda` na
        tela. A sala pergunta a mesma coisa por outro motivo: o parágrafo ao lado do diagrama 3
        costuma trazer a linha que o autor dá para aquela posição.

        **Devolve `""` em três casos, e todos são "ainda não sei"**: não há folha lida, a folha
        lida é de outra página, ou nenhum parágrafo daquele diagrama é notação. Nenhum deles é
        erro -- ler a folha custa de 1 s a 40 s, e é decisão de quem lê.

        O corte "é notação" é o de `text/notacao.e_linha_de_notacao`, o mesmo que a S-249 usa para
        pintar o estilo: a **maioria** dos tokens do parágrafo é lance.
        """
        from chess_diagram_ocr.text import notacao
        from chess_diagram_ocr.text import pagina as pagina_mod

        lida = self._aba._pagina
        if lida is None or int(lida.pagina) != int(pagina):
            return ""
        trechos = [
            bloco.texto
            for bloco in lida.blocos
            if isinstance(bloco, pagina_mod.BlocoDeTexto)
            and bloco.legenda_de == int(diagrama)
            and notacao.e_linha_de_notacao(bloco.texto)
        ]
        return " ".join(trechos).strip()

    # ---------------------------------------------------------------- os eventos da folha (S-825)

    def dica_na_folha(self, evento: QEvent) -> bool:
        """A dica sobre a miniatura (item 23): o que ela é, a posição, e o que o clique faz."""
        if not isinstance(evento, QHelpEvent):
            return False
        dica = self._dica_da_marca(evento.pos())
        if dica:
            QToolTip.showText(evento.globalPos(), dica, self._aba.editor.viewport())
        else:
            QToolTip.hideText()
        return True

    def clique_na_folha(self, evento: QEvent) -> bool:
        """O clique esquerdo na miniatura seleciona a marca dela (item 8)."""
        if not isinstance(evento, QMouseEvent) or evento.button() != Qt.MouseButton.LeftButton:
            return False
        return self._clicou_na_miniatura(evento.position().toPoint())

    def duplo_clique_na_folha(self, evento: QEvent) -> bool:
        """O duplo clique esquerdo na miniatura pede o diagrama na sala (item 8)."""
        if not isinstance(evento, QMouseEvent) or evento.button() != Qt.MouseButton.LeftButton:
            return False
        return self._ativou_a_miniatura(evento.position().toPoint())

    # ---------------------------------------------------------------------- a miniatura (item 8)

    def _marca_sob(self, ponto: QPoint) -> tuple[int, int, rico.Corrida] | None:
        """A marca `[Diagrama N]` da miniatura que está sob o ponto: `(começo, fim, corrida)`.

        A miniatura é um caractere do widget que não existe no documento (`texto_espelho.Mapa`); a marca dela
        vem logo depois, no bloco seguinte. O cursor que o Qt dá para o ponto cai antes ou depois
        do caractere da imagem, e por isso se sondam os dois.
        """
        documento = self._aba.editor.document()
        if documento is None:
            return None
        posicao = self._aba.editor.cursorForPosition(ponto).position()
        for p in (posicao, posicao - 1):
            if p < 0:
                continue
            sonda = QTextCursor(documento)
            sonda.setPosition(p + 1)  # `charFormat` é o do caractere **antes** do cursor: o `p`
            if sonda.position() != p + 1 or not sonda.charFormat().isImageFormat():
                continue
            achado = self.marca_em(self._aba.espelho.mapa.deslocamento(p + 2))
            if achado is not None:
                return achado
        # Sobre o texto da própria marca (item 12): `[Diagrama 3]` é o diagrama tanto quanto a
        # figura -- e é tudo o que há dele quando não há figura nenhuma.
        return self.marca_em(self._aba.espelho.mapa.deslocamento(posicao))

    def marca_em(self, deslocamento: int) -> tuple[int, int, rico.Corrida] | None:
        """A marca de diagrama que contém o deslocamento do documento, ou `None`."""
        comeco = 0
        for corrida in self._aba.documento.corridas:
            fim = comeco + len(corrida.texto)
            if corrida.e_diagrama and comeco <= deslocamento < fim:
                return comeco, fim, corrida
            comeco = fim
        return None

    def _dica_da_marca(self, ponto: QPoint) -> str:
        """O texto da dica sobre a miniatura ou a marca, ou `""` fora delas (item 23).

        Três linhas: o que é («Diagrama 3 da folha 14»), a posição quando se sabe (a FEN, que o
        item 20 também copia) e o que o gesto faz -- a dica é onde quem passa o mouse descobre o
        duplo clique e o botão direito sem ter de adivinhar.
        """
        achado = self._marca_sob(ponto)
        if achado is None:
            return ""
        corrida = achado[2]
        numero = int(getattr(self._aba.documento.bloco_de(corrida), "indice", corrida.bloco)) + 1
        folha = "" if self._aba._pagina is None else f" da folha {int(self._aba._pagina.pagina) + 1}"
        linhas = [f"Diagrama {numero}{folha}"]
        posicao = posicao_de(self._aba.documento, corrida)
        linhas.append(f"FEN: {posicao}" if posicao else "Posição ainda não lida (OCR dos diagramas na aba Livro)")
        linhas.append("Duplo clique abre no Estudo · botão direito: copiar, apagar")
        return "\n".join(linhas)

    def _clicou_na_miniatura(self, ponto: QPoint) -> bool:
        """O clique na miniatura seleciona a marca dela: é a marca que se apaga, move e copia.

        Sem isto o clique punha o cursor ao lado de um caractere invisível, e a pessoa apagava a
        figura sem apagar o diagrama (`_trocado` avisa, mas avisar é o segundo melhor).
        """
        achado = self._marca_sob(ponto)
        if achado is None:
            return False
        comeco, fim, _corrida = achado
        cursor = self._aba.editor.textCursor()
        cursor.setPosition(self._aba.espelho.mapa.posicao(comeco))
        cursor.setPosition(self._aba.espelho.mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self._aba.editor.setTextCursor(cursor)
        self._aba.editor.setFocus()
        return True

    def abrir_menu_de_contexto(self, ponto: QPoint) -> None:
        menu = self.menu_de_contexto(ponto)
        folha = self._aba.editor.viewport()
        menu.exec(folha.mapToGlobal(ponto) if folha is not None else self._aba.editor.mapToGlobal(ponto))
        menu.deleteLater()

    def menu_de_contexto(self, ponto: QPoint) -> QMenu:
        """O menu do botão direito: o padrão do editor e, sobre uma miniatura, o que ela sabe fazer.

        Três ações, e as três já existiam por outro caminho -- é o que as mantém fora do catálogo
        de comandos (S-256): abrir na sala é o duplo clique (item 8), copiar a imagem é o que a
        aba Livro faz com o recorte, apagar o diagrama é apagar a marca, que o clique já
        seleciona. O menu é onde quem não sabe do duplo clique descobre que a miniatura é viva.
        """
        menu = self._aba.editor.createStandardContextMenu(ponto)
        assert menu is not None  # o Qt só devolve `None` sem documento, e o editor sempre tem um
        self._aba.correcao.sugestoes_no_menu(menu, ponto)
        self._aba.caderno.no_menu(menu)
        achado = self._marca_sob(ponto)
        if achado is None:
            return menu
        comeco, fim, corrida = achado
        numero = int(getattr(self._aba.documento.bloco_de(corrida), "indice", -1)) + 1
        menu.addSeparator()
        estudar = QAction(f"Abrir o diagrama {numero} no Estudo", menu)
        estudar.triggered.connect(lambda: self._ativou_a_miniatura(ponto))
        copiar = QAction(f"Copiar a imagem do diagrama {numero}", menu)
        copiar.triggered.connect(lambda: self._copiar_miniatura(corrida))
        apagar = QAction(f"Apagar o diagrama {numero} da folha", menu)
        apagar.triggered.connect(lambda: self._apagar_diagrama(comeco, fim, numero))
        for acao in (estudar, copiar, apagar):
            menu.addAction(acao)
        return menu

    def _copiar_miniatura(self, corrida: rico.Corrida) -> None:
        """A figura do diagrama -- recorte ou desenho -- vai para a área de transferência, **e a
        FEN vai junto como texto** quando se sabe (item 20).

        Um só gesto para os dois destinos: quem cola num editor de imagens recebe a figura; quem
        cola numa caixa de texto -- um programa de xadrez, um e-mail -- recebe o campo de peças.
        """
        from PyQt6.QtCore import QMimeData

        figura = self._imagem_do_diagrama(corrida)
        posicao = posicao_de(self._aba.documento, corrida)
        if figura is None and not posicao:
            self._aba.estado.emit("Este diagrama não tem figura nem posição para copiar.")
            return
        conteudo = QMimeData()
        if figura is not None:
            conteudo.setImageData(figura.toImage())
        if posicao:
            conteudo.setText(posicao)
        area = QApplication.clipboard()
        if area is not None:
            area.setMimeData(conteudo)
        o_que = "Imagem e FEN do diagrama copiadas." if figura is not None and posicao else (
            "Imagem do diagrama copiada." if figura is not None else "FEN do diagrama copiada."
        )
        self._aba.estado.emit(o_que)

    def _apagar_diagrama(self, comeco: int, fim: int, numero: int) -> None:
        """Tira a marca inteira -- e com ela a figura. É uma edição: `Ctrl+Z` a devolve."""
        self._aba.espelho.aplicar(rico.apagar(self._aba.documento, comeco, fim), selecao=(comeco, comeco))
        self._aba.estado.emit(f"O diagrama {numero} saiu da folha; desfazer o devolve.")

    def ativar_marca_selecionada(self) -> bool:
        """Se a seleção é exatamente uma marca `[Diagrama N]`, pede o diagrama na sala."""
        inicio, fim = self._aba.espelho.intervalo()
        achado = self.marca_em(inicio) if fim > inicio else None
        if achado is None or (achado[0], achado[1]) != (inicio, fim):
            return False
        return self._ativar(achado[2])

    def _ativou_a_miniatura(self, ponto: QPoint) -> bool:
        """O duplo clique na miniatura pede o diagrama na sala de estudo (`diagrama_ativado`)."""
        achado = self._marca_sob(ponto)
        return achado is not None and self._ativar(achado[2])

    def _ativar(self, corrida: rico.Corrida) -> bool:
        """O diagrama da marca vai à sala: pelo índice, ou pela posição quando não tem caixa (S-595)."""
        bloco = self._aba.documento.bloco_de(corrida)
        indice = getattr(bloco, "indice", None)
        if indice is None or self._aba._pagina is None:
            return False
        if getattr(bloco, "procedencia", "") == "humano" and not any(getattr(bloco, "bbox", ())):
            self._aba.diagrama_sem_caixa_ativado.emit(int(self._aba._pagina.pagina), posicao_de(self._aba.documento, corrida))
        else:
            self._aba.diagrama_ativado.emit(int(self._aba._pagina.pagina), int(indice))
        return True
