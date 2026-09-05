"""A aba "Galeria" no segundo frontend: um diagrama por vez, sincronizado com a página (S-67/S-503).

**O que ela é, e o que ela não é.** Não é um segundo editor de posição -- a aba Resultado já é
isso, e duplicá-la criaria dois lugares para corrigir a mesma casa. Aqui a unidade de trabalho é a
**anotação de exportação**: o número do lance, a vez, se aquele diagrama sai com link de análise e
os headers de PGN que só quem conhece o livro pode preencher.

Por isso o que aparece no centro é o **recorte original** do livro, e não o tabuleiro redesenhado
a partir da FEN. Quem está digitando "lance 24" está lendo a legenda impressa, e um tabuleiro
redesenhado esconde justamente a fonte dessa informação.

**Toda a lógica está fora daqui, e agora nos dois lados.** `ui/gallery_model.py` decide navegação,
anotação, casamento com a base e o que pode ser sobrescrito; `ui/galeria_declarada.py` -- aberto na
S-503 -- decide as medidas, o tri-estado do link, as quatro ações do foco e **a contabilidade da
varredura em lote**. O que este arquivo escreve é widget, thread e o vaivém entre os dois.

---

**Quatro diferenças do Qt, e as quatro são de mecanismo.**

1. **A thread da varredura fala por sinal.** São três operações longas -- varrer o livro, buscar
   por nome, buscar por posição --, e as três vêm de fora da thread da janela. No Tk é
   `self.after(0, ...)`; aqui cada uma tem o seu sinal, e o Qt escolhe a conexão em fila sozinho.
2. **A legenda é um `QTextEdit` somente-leitura**, e não um `tk.Text` com as teclas recusadas uma
   a uma. O Tk não tem "leitura": `state=DISABLED` também recusa a seleção e pinta de cinza, e por
   isso o outro lado filtra `<Key>` à mão. `setReadOnly(True)` é exatamente o que se queria lá.
3. **O recorte é um `QPixmap` num `QLabel`**, e não um `PhotoImage` guardado contra a coleta: o
   `QLabel` é dono do pixmap, e a linha de comentário do outro lado ("a referência tem de
   sobreviver a esta função") não tem equivalente aqui.
4. **O foco vem no `showEvent`**, que é o `<Map>` de lá: sem ele `atalhos.destino` não encontra
   esta aba na cadeia, e a seta continua indo para o painel de Resultado (S-400).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QShowEvent
from PyQt6.QtWidgets import (
    QBoxLayout,
    QButtonGroup,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.config import DEFAULT_PDF_DIR, DEFAULT_READING_ORDER
from chess_diagram_ocr.gallery import DiagramAnnotation, load_annotations
from chess_diagram_ocr.gallery_scan import build_gallery_index, load_index, save_index
from chess_diagram_ocr.games_cache import PositionStore, open_store
from chess_diagram_ocr.games_db import (
    DiagramMatch,
    database_paths,
    match_entries,
    match_positions,
    scan_by_players,
    scan_by_positions,
)
from chess_diagram_ocr.games_index import DEFAULT_INDEX_PATH
from chess_diagram_ocr.logging_setup import onde_esta_o_rastro
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dialogos import DialogoDePartidas, perguntar_bases, perguntar_escopo
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.rolagem import em_rolagem
from chess_diagram_ocr.service import OcrService
from chess_diagram_ocr.ui import atalhos, espaco, estilos, strings, tokens
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.escolha_de_bases import store_path_for
from chess_diagram_ocr.ui.escopo_da_varredura import ScanScope
from chess_diagram_ocr.ui.galeria_declarada import (
    ACOES_PROPRIAS,
    BOARD_VIEW_SIZE,
    CAPTION_LINES,
    LARGURA_DA_LATERAL,
    LARGURA_MINIMA_DA_GALERIA,
    LINK_CHOICES,
    SEM_BASE,
    LivroVarrido,
    galeria_empilhada,
    mesmo_arquivo,
    resumo_do_lote,
)
from chess_diagram_ocr.ui.gallery_model import HEADER_FIELDS, GalleryModel, describe_origin

logger = logging.getLogger(__name__)

__all__ = ["LARGURA_MINIMA_DA_GALERIA", "PainelDaGaleria"]

LARGURA_MAXIMA_DO_WIDGET = 16_777_215
"""O `QWIDGETSIZE_MAX` do Qt, que o PyQt6 não exporta. É o valor com que `setMaximumWidth` volta a
dizer "sem teto" -- `setFixedWidth` cravou os dois lados, e desfazê-lo pede o número."""


class PainelDaGaleria(QWidget):
    """Percorre os diagramas do livro e grava as anotações de exportação."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status. A janela decide onde ela aparece."""

    pediu_pagina = pyqtSignal(int)
    """Pede ao visualizador para ir àquela página. Um sinal porque a galeria não conhece o painel
    de PDF -- e não deveria: são abas irmãs, não uma dona da outra."""

    anotacoes_mudaram = pyqtSignal()
    """A anotação de exportação deste livro mudou -- quem pinta o violeta da página precisa saber
    (S-116)."""

    _lote_pronto = pyqtSignal(object, object, object)
    """Interno: `(escopo, resultados, aberto)` vindo da thread da varredura."""

    _progrediu = pyqtSignal(str)
    _busca_pronta = pyqtSignal(object, int)
    _busca_falhou = pyqtSignal(str)
    _posicoes_prontas = pyqtSignal(object, int)
    _posicoes_paradas = pyqtSignal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        service: OcrService,
        pdf_path: Callable[[], Path | None],
        model_path: Callable[[], Path],
        max_boards: Callable[[], int],
        sumidouro_de_revisao: Callable[[], Any] | None = None,
        busy: BusyRegistry | None = None,
        perguntar_escopo_de_varredura: Callable[[Path | None], ScanScope | None] | None = None,
        perguntar_bases_de_partidas: Callable[[Sequence[Path]], Sequence[Path] | None] | None = None,
        pasta_da_galeria: Path | None = None,
    ) -> None:
        """`pasta_da_galeria` é onde o índice e as anotações deste livro moram. `None` é
        `data/gallery/`, que é o do produto.

        **Injetável, e não por configuração.** É a mesma razão que `GalleryModel.gallery_dir`
        registra no próprio docstring: sem ela, testar a gravação exige remendar um global -- e o
        teste que tentou isso gravou no `data/` de verdade. Este painel escreve por três caminhos
        (`save_index`, `load_index` e `GalleryModel.save`), e os três leem o padrão do argumento na
        definição; passar o diretório em um só deixaria dois escrevendo no lugar errado."""
        super().__init__(parent)
        self._service = service
        self._pdf_path = pdf_path
        self._model_path = model_path
        self._max_boards = max_boards
        self._perguntar_escopo = perguntar_escopo_de_varredura
        """Quem pergunta **quais livros** varrer. `None` abre o diálogo de verdade.

        Injetável porque uma janela modal não se dirige de um roteiro de teste."""
        self._perguntar_bases = perguntar_bases_de_partidas
        self._pasta = pasta_da_galeria
        """Quem pergunta **em quais bases** procurar. `None` abre o diálogo de verdade."""

        self._bases: tuple[Path, ...] | None = None
        """As bases escolhidas nesta sessão. `None` é "ninguém escolheu ainda" -- e aí valem todos
        os `.pgn` da pasta, que é o que a S-93 fixou.

        A escolha vale para a sessão e para **tudo** que lê base nesta aba: as duas buscas, o cache
        de posições e a lista de candidatas. Guardá-la só dentro de uma das buscas faria a janela
        procurar num conjunto e responder com o cache de outro."""

        self._sumidouro_de_revisao = sumidouro_de_revisao
        """Quem quer a fila de revisão desta varredura (S-119). Esta aba não conhece a de Revisão;
        ela só oferece o que leu a quem a janela apontar."""

        self._busy_registry = busy
        self._busy_token: BusyToken | None = None

        self.model = GalleryModel()
        self._store: PositionStore | None = None
        """A conexão aberta com o cache de posições (S-140). Uma por painel, e não por livro."""
        self._cancelar = threading.Event()
        self._varrendo = False
        self._sincronizando = False
        """Guarda de reentrância: pedir a página ao visualizador faz ele avisar de volta que a
        página mudou, e sem isto os dois se chamariam em círculo."""
        self._ultima_copia: dict[str, str] = {}
        """O que a última cópia para todos espalhou, para o desfazer. Só da sessão."""
        self._coletor_do_lote: Any = None
        """O sumidouro da fila de revisão desta varredura, guardado entre o começo e o fim.

        Ele **não** viaja pelo sinal que traz os resultados: um sumidouro é um `QObject` filho
        deste painel, e mandá-lo por sinal só para receber de volta o que já está aqui seria
        confundir "atravessa a fronteira de thread" com "precisa ser transportado"."""
        self._montando = False

        self._montar()
        self._lote_pronto.connect(self._lote_terminou)
        self._progrediu.connect(self.lbl_varredura.setText)
        self._busca_pronta.connect(self._busca_terminou)
        self._busca_falhou.connect(self._falhou)
        self._posicoes_prontas.connect(self._posicoes_terminaram)
        self._posicoes_paradas.connect(self._posicoes_pararam)
        self.refresh()
        atalhos.conferir_dono(self, "PainelDaGaleria")

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        # **A aba rola, e não exige a altura dela da janela** (S-552, a metade perdida da S-150).
        # Os 420 px do recorte e os 260 da lateral são medidos (S-154) e continuam inteiros; o que
        # muda é que a soma deles -- `711 x 800`, o maior mínimo das seis abas -- deixa de ser o
        # piso da janela. Era ela quem punha a altura mínima em 902 px. Ver `qt/rolagem.py`.
        corpo = QWidget(self)
        self.rolagem = em_rolagem(self, corpo)
        fora = QVBoxLayout(corpo)
        fora.setContentsMargins(*(espaco.linha(),) * 4)
        fora.setSpacing(espaco.linha())

        topo = BarraFluida(corpo)
        self.btn_varrer = self._botao(topo, strings.VARRER_LIVRO, self.varrer)
        dica_em(
            self.btn_varrer,
            "Pergunta antes quais livros varrer: o que está aberto, outros escolhidos em disco, "
            f"ou todos os .pdf de {DEFAULT_PDF_DIR.name}. Com mais de um livro, os que já têm "
            "índice completo são pulados.",
        )
        self.btn_cancelar = self._botao(topo, "Cancelar", self.cancelar_varredura)
        self.btn_cancelar.setEnabled(False)
        dica_em(
            self.btn_cancelar,
            "Só fica ativo enquanto uma varredura ou busca está rodando.\n"
            "A varredura do livro retoma da página seguinte à última terminada; a busca por\n"
            "posição descarta a passada inteira, porque meia base lida dá contagens que não valem.",
        )
        self.btn_por_nome = self._botao(topo, "Buscar por nome", self.buscar_por_nome)
        dica_em(
            self.btn_por_nome,
            "Procura na base de partidas os diagramas cuja legenda traz os jogadores, e preenche "
            "lance, vez e headers -- só onde estiver vazio. Uma passada pela base, e nada sai da "
            "máquina. Pergunta antes em quais .pgn procurar.",
        )
        self.btn_por_posicao = self._botao(topo, "Buscar pela posição", self.buscar_por_posicao)
        dica_em(
            self.btn_por_posicao,
            "Procura pelas 64 casas de cada diagrama, e não pela legenda: alcança todo diagrama, "
            "inclusive os sem nome nenhum impresso. Reproduz os lances da base inteira -- cerca de "
            "meia hora na primeira vez, segundos nas seguintes, porque a resposta fica guardada. "
            "Dá para cancelar. Pergunta antes em quais .pgn procurar -- e cada conjunto de bases "
            "guarda as respostas dele em separado.",
        )
        # O lote de diagramas mora aqui, e não no menu (S-544): a origem dele é **o livro
        # varrido**, e é esta aba que tem o índice da varredura na mão. O comando de menu do lote
        # exporta a sala de estudo, que é a outra origem -- as duas existem porque quem diagrama
        # um livro inteiro quer os 500 diagramas dele, e quem prepara uma aula quer os oito que
        # analisou.
        self.btn_diagramas = self._botao(topo, "Exportar os diagramas", self.exportar_diagramas)
        dica_em(
            self.btn_diagramas,
            "Grava um arquivo de imagem por diagrama deste livro -- PNG ou SVG, no tamanho e na "
            "pele escolhidos --, com o nome dizendo livro, página e diagrama.\n"
            "Fica cinza enquanto o livro não tiver sido varrido.",
        )
        self.lbl_varredura = QLabel("", topo)
        topo.adicionar(self.lbl_varredura)
        fora.addWidget(topo)

        # **Uma fila que muda de sentido** (S-552, terceira rodada). `QBoxLayout` em vez de
        # `QHBoxLayout` porque é o mesmo leiaute em duas direções: `setDirection` troca lado a lado
        # por um sobre o outro sem remontar widget nenhum, e sem uma segunda montagem que
        # divergiria da primeira. Quem decide *quando* é `galeria_declarada.galeria_empilhada`.
        meio = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        meio.setSpacing(espaco.folga())
        meio.addLayout(self._centro(), 1)
        # A lateral com largura fixa: ela reserva o que pede, e o centro fica com o resto (S-154).
        self.lateral = self._lateral()
        self.lateral.setFixedWidth(LARGURA_DA_LATERAL)
        meio.addWidget(self.lateral)
        self._meio = meio
        fora.addLayout(meio, 1)
        fora.addWidget(self._rodape())
        self._arranjar(self._largura_do_viewport())

    def _botao(self, pai: QWidget, rotulo: str, funcao: Callable[[], object], papel: str = estilos.NEUTRO) -> QPushButton:
        botao = QPushButton(rotulo, pai)
        botao.clicked.connect(funcao)
        tema.aplicar_papel(botao, papel)
        if isinstance(pai, BarraFluida):
            pai.adicionar(botao)
        return botao

    def _centro(self) -> QVBoxLayout:
        centro = QVBoxLayout()
        centro.setSpacing(espaco.linha())

        self.recorte = QLabel("", self)
        self.recorte.setFixedSize(BOARD_VIEW_SIZE, BOARD_VIEW_SIZE)
        self.recorte.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # O canvas da galeria era o único do `ui/` fora do sistema de cor da S-144: ele nascia
        # com o fundo de fábrica do Tk e escrevia o aviso num `#888` cravado. Aqui a superfície e
        # o texto vêm do token desde a primeira linha.
        tema.pintar(self.recorte, "background-color", tokens.SUPERFICIE_TABULEIRO)
        centro.addWidget(self.recorte, 0, Qt.AlignmentFlag.AlignHCenter)

        self.lbl_posicao = QLabel("nenhum diagrama varrido", self)
        centro.addWidget(self.lbl_posicao, 0, Qt.AlignmentFlag.AlignHCenter)

        navegacao = QHBoxLayout()
        navegacao.addStretch(1)
        for rotulo, passo, absoluto in (
            (strings.PRIMEIRO, 0, True),
            (f"{strings.ANTERIOR} anterior", -1, False),
            (f"próximo {strings.PROXIMO}", 1, False),
            (strings.ULTIMO, -1, True),
        ):
            navegacao.addWidget(self._botao(self, rotulo, partial(self._ir, passo, absoluto=absoluto)))
        navegacao.addStretch(1)
        centro.addLayout(navegacao)

        # A legenda impressa, inteira e **selecionável**: ela é a fonte do que a pessoa digita nos
        # campos ao lado, e enquanto foi um rótulo era a única coisa da tela que não se podia
        # aproveitar. `setReadOnly` é exatamente o que o outro frontend consegue filtrando `<Key>`
        # tecla a tecla -- lá `state=DISABLED` também recusaria a seleção e pintaria de cinza.
        self.legenda = QTextEdit(self)
        self.legenda.setReadOnly(True)
        self.legenda.setFixedHeight(CAPTION_LINES * tema.altura_de_linha_atual())
        centro.addWidget(self.legenda)
        centro.addWidget(
            self._botao(self, "Copiar legenda", self.copiar_legenda), 0, Qt.AlignmentFlag.AlignHCenter
        )
        return centro

    def _lateral(self) -> QGroupBox:
        lateral = QGroupBox(strings.CABECALHOS_DO_PGN, self)
        grade = QGridLayout(lateral)
        grade.setContentsMargins(*(espaco.folga(),) * 4)
        grade.setVerticalSpacing(espaco.minima())

        self.campos_de_header: dict[str, QLineEdit] = {}
        for linha, nome in enumerate(HEADER_FIELDS):
            grade.addWidget(QLabel(nome, lateral), linha, 0)
            campo = QLineEdit(lateral)
            # `editingFinished` é `<FocusOut>` e `<Return>` de uma vez: o Qt o emite nos dois, e é
            # exatamente o par que o outro frontend amarra à mão em cada campo.
            campo.editingFinished.connect(partial(self._gravar_header, nome))
            grade.addWidget(campo, linha, 1)
            self.campos_de_header[nome] = campo

        livre = len(HEADER_FIELDS)
        grade.addWidget(QLabel("outro", lateral), livre, 0)
        self.campo_livre_nome = QLineEdit(lateral)
        self.campo_livre_valor = QLineEdit(lateral)
        grade.addWidget(self.campo_livre_nome, livre, 1)
        grade.addWidget(self.campo_livre_valor, livre + 1, 1)
        grade.addWidget(self._botao(lateral, "Gravar", self._gravar_header_livre), livre + 2, 1)

        # Junto dos campos que ele limpa, e não com os dois de baixo: aqueles agem sobre o livro
        # inteiro, e este só sobre este diagrama. A distância na tela é a diferença de alcance --
        # foi confundir as duas que espalhou quatro campos por 1.405 diagramas (S-76).
        self.btn_limpar = self._botao(lateral, "Limpar os headers", self.limpar_headers, estilos.DESTRUTIVO)
        self.btn_limpar.setEnabled(False)
        dica_em(
            self.btn_limpar,
            "Apaga os headers DESTE diagrama, todos de uma vez -- para quando a base preencheu "
            "com a partida errada. O lance, a vez e a partida escolhida ficam. Não mexe em nenhum "
            "outro diagrama.\nFica cinza quando este diagrama não tem nenhum header preenchido.",
        )
        grade.addWidget(self.btn_limpar, livre + 3, 0, 1, 2)

        # A procedência da base fica **junto dos campos que ela preencheu**, e não na barra de
        # status: a barra fala do último gesto, e esta pergunta ("quem preencheu isto?") se faz ao
        # chegar num diagrama, que pode ser dias depois da busca.
        self.lbl_origem = QLabel("", lateral)
        self.lbl_origem.setWordWrap(True)
        tema.pintar(self.lbl_origem, "color", tokens.PRONTO_TEXTO)
        grade.addWidget(self.lbl_origem, livre + 4, 0, 1, 2)

        self.btn_candidatas = self._botao(lateral, "Partidas da base", self.abrir_lista_de_partidas)
        self.btn_candidatas.setEnabled(False)
        dica_em(
            self.btn_candidatas,
            "As partidas da base que contêm esta posição. Escolher uma preenche lance, vez e "
            "headers, e a escolha fica registrada -- uma nova busca na base não a desfaz.\n"
            "Fica cinza enquanto a busca na base não achou candidata para este diagrama.",
        )
        grade.addWidget(self.btn_candidatas, livre + 5, 0, 1, 2)

        # O rótulo diz a **direção** da cópia. "Aplicar a todos" foi lido como "salvar os headers
        # deste diagrama" -- e o clique espalhou quatro campos por 1.405 diagramas.
        copiar = self._botao(lateral, "Copiar headers para todos", self.copiar_para_todos)
        dica_em(
            copiar,
            "Copia os headers deste diagrama para TODOS os outros do livro, sobrescrevendo o que "
            "eles tiverem nesses campos. Os campos já se salvam sozinhos ao sair deles -- este "
            "botão não é para salvar, é para propagar.",
        )
        grade.addWidget(copiar, livre + 6, 0, 1, 2)

        self.btn_desfazer = self._botao(lateral, "Desfazer a cópia", self.desfazer_copia)
        self.btn_desfazer.setEnabled(False)
        dica_em(
            self.btn_desfazer,
            "Remove dos outros diagramas os valores que a última cópia espalhou. Não recupera o "
            "que a cópia sobrescreveu -- por isso a pergunta antes.\n"
            "Fica cinza até haver uma cópia desta sessão para desfazer.",
        )
        grade.addWidget(self.btn_desfazer, livre + 7, 0, 1, 2)
        grade.setRowStretch(livre + 8, 1)
        return lateral

    def _rodape(self) -> QGroupBox:
        """"Este diagrama": lance, lado a jogar, link, e o botão de copiar.

        **Uma `BarraFluida` e não um `QHBoxLayout`** (S-552, terceira rodada), pela razão que o
        cabeçalho de `qt/barra.py` já escreve: `QHBoxLayout` não reflui, e onze controles em fila
        davam **694 px** de largura mínima ao rodapé -- os mesmos 706 px de conteúdo que punham a
        barra de rolagem horizontal na aba, mesmo depois de as duas colunas passarem a empilhar.
        Fila que quebra em fileiras é o widget que este projeto já tem para isto, e é o mesmo da
        barra de cima desta aba.
        """
        rodape = QGroupBox("Este diagrama", self)
        fora = QVBoxLayout(rodape)
        fora.setContentsMargins(*(espaco.folga(),) * 4)
        deitado = BarraFluida(rodape)
        fora.addWidget(deitado)

        deitado.adicionar(QLabel("Lance", rodape))
        self.campo_lance = QLineEdit(rodape)
        self.campo_lance.setFixedWidth(60)
        self.campo_lance.editingFinished.connect(self._gravar_lance)
        deitado.adicionar(self.campo_lance)

        deitado.adicionar(QLabel(strings.LADO_A_JOGAR, rodape))
        self.lado = QButtonGroup(rodape)
        for rotulo, valor in (("brancas", "w"), ("pretas", "b")):
            botao = QRadioButton(rotulo, rodape)
            botao.setProperty("valor", valor)
            self.lado.addButton(botao)
            deitado.adicionar(botao)
        self.lado.buttonClicked.connect(lambda _botao: self._gravar_lado())

        deitado.adicionar(QLabel("Lichess", rodape))
        self.link = QButtonGroup(rodape)
        for rotulo, valor in LINK_CHOICES:
            botao = QRadioButton(rotulo, rodape)
            botao.setProperty("valor", valor)
            self.link.addButton(botao)
            deitado.adicionar(botao)
        self.link.buttonClicked.connect(lambda _botao: self._gravar_link())

        deitado.adicionar(self._botao(rodape, "Copiar link", self.copiar_link))
        return rodape

    def showEvent(self, a0: QShowEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """**O teclado vem junto com a aba** (S-400), como o `<Map>` do outro lado.

        Sem isto o foco fica onde estava, `atalhos.destino` não encontra esta aba na cadeia e a
        seta continua indo para o painel de Resultado. Dar o foco ao recorte não tira a seta de
        dentro dos campos: ali quem responde é `acoes_proprias`, que devolve vazio.
        """
        super().showEvent(a0)
        self.recorte.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.recorte.setFocus()
        # **E o arranjo se decide aqui também** (S-552, terceira rodada), pela razão da S-551: numa
        # janela que já nasce no tamanho final a aba nunca é redimensionada depois de aparecer, e
        # uma regra que morasse só no `resizeEvent` rodaria uma vez, com o viewport ainda em zero.
        self._arranjar(self._largura_do_viewport())

    def resizeEvent(self, a0: Any) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(a0)
        self._arranjar(self._largura_do_viewport())

    def _largura_do_viewport(self) -> int:
        """A largura que a aba tem **sem rolar**. Zero antes do primeiro desenho, e é o que
        `galeria_empilhada` lê como "ainda não há decisão"."""
        area = self.rolagem.viewport()
        return area.width() if area is not None else 0

    def _arranjar(self, largura: int) -> None:
        """Duas colunas, ou o cabeçalho sob o recorte. Quem decide é `galeria_empilhada` (S-552).

        **A lateral perde a largura fixa ao empilhar, e é o que faz o arranjo valer a pena**: os
        260 px da S-154 são o que ela precisa *ao lado* do recorte; embaixo dele ela tem a coluna
        inteira, e os dez pares rótulo/campo deixam de disputar 260 px com nada.
        """
        empilha = galeria_empilhada(largura)
        direcao = (
            QBoxLayout.Direction.TopToBottom if empilha else QBoxLayout.Direction.LeftToRight
        )
        if self._meio.direction() == direcao:
            return
        self._meio.setDirection(direcao)
        if empilha:
            self.lateral.setMinimumWidth(0)
            self.lateral.setMaximumWidth(LARGURA_MAXIMA_DO_WIDGET)
        else:
            self.lateral.setFixedWidth(LARGURA_DA_LATERAL)

    # ----------------------------------------------------------------------------- varredura

    def _ocupado(self, ocupado: bool) -> None:
        """Liga e desliga os três botões que disputam a única thread longa desta aba.

        O que o `_varrendo` já garantia -- que uma busca não começa em cima de outra -- passa a
        aparecer na tela: um botão que não pode ser clicado agora **parece** que não pode.
        """
        for botao in (self.btn_varrer, self.btn_por_nome, self.btn_por_posicao):
            botao.setEnabled(not ocupado)
        self.btn_cancelar.setEnabled(ocupado)
        if not ocupado:
            # Aqui, e não em cada desfecho: soltar o registro é a metade do par que se esquece, e
            # uma operação que ficou registrada depois de terminar faz a janela perguntar para
            # sempre (S-112).
            self._soltar_ocupado()

    def _registrar_ocupado(self, nome: str, *, loses_work: bool, detail: str = "") -> None:
        if self._busy_registry is None:
            return
        self._busy_token = self._busy_registry.register(
            nome, loses_work=loses_work, cancellable=True, detail=detail, cancel=self.cancelar_varredura
        )

    def _soltar_ocupado(self) -> None:
        if self._busy_token is not None:
            self._busy_token.release()
            self._busy_token = None

    def varrer(self) -> None:
        """Pergunta **quais livros** e varre os escolhidos, um a um, em thread (S-119).

        O índice desta aba é o superconjunto -- todo diagrama, sem gate -- e a fila de revisão é
        montada do mesmo fluxo, pelo sumidouro. Duas passadas pelo mesmo PDF custavam 338 s + 299 s
        no `PDF/1000 Chess Problems`.
        """
        if self._varrendo:
            return
        escopo = self._escolher_escopo()
        if escopo is None:
            # Desistiu no diálogo: nem rodapé, nem log. Cancelar não é evento.
            return
        if escopo.is_empty:
            # Pré-condição: rodapé com severidade de aviso, e não caixa modal (S-164).
            self.estado.emit(
                "Nenhum livro para varrer: abra um PDF, escolha um em disco ou ponha .pdf na pasta padrão."
            )
            return
        self._comecar_varredura(escopo)

    def _escolher_escopo(self) -> ScanScope | None:
        if self._perguntar_escopo is not None:
            return self._perguntar_escopo(self._pdf_path())
        return perguntar_escopo(self, open_book=self._pdf_path(), folder=DEFAULT_PDF_DIR)

    def _comecar_varredura(self, escopo: ScanScope) -> None:
        aberto = self._pdf_path()
        # A fila de revisão é **do livro aberto**: alimentá-la com diagramas de outro livro
        # montaria uma fila que diz uma procedência e carrega outra.
        varre_o_aberto = aberto is not None and any(mesmo_arquivo(aberto, livro) for livro in escopo.books)

        self._varrendo = True
        self._cancelar.clear()
        # Criado aqui, na thread da janela, porque ele lê a configuração dela -- e só aqui.
        coletor = (
            self._sumidouro_de_revisao()
            if self._sumidouro_de_revisao is not None and varre_o_aberto
            else None
        )
        # `loses_work=False` desde a S-120: a varredura retoma da página seguinte à última
        # terminada, então fechar a janela custa **a página em curso**, e não o livro.
        self._coletor_do_lote = coletor
        detalhe = escopo.books[0].name if len(escopo.books) == 1 else f"{len(escopo.books)} livros"
        self._registrar_ocupado("varredura do livro", loses_work=False, detail=detalhe)
        self._ocupado(True)
        self.lbl_varredura.setText("varrendo...")
        threading.Thread(
            target=self._trabalho_de_varredura, args=(escopo, coletor, aberto), daemon=True
        ).start()

    def cancelar_varredura(self) -> None:
        """Cancela a operação longa em curso -- e o que se perde depende de qual é ela.

        A varredura do livro não descarta o que já leu; a busca por posição **descarta a passada
        inteira**: meia base lida dá contagens que não valem, e é a contagem que decide se
        preencher é honesto.
        """
        self._cancelar.set()
        self.lbl_varredura.setText("cancelando...")

    def _trabalho_de_varredura(self, escopo: ScanScope, coletor: Any, aberto: Path | None) -> None:
        """Os livros do escopo, um a um, na mesma thread e com o mesmo modelo carregado.

        **Um livro que quebra não derruba o lote** (S-121): com 34 livros, interromper no primeiro
        PDF corrompido faria a pessoa descobrir o problema três horas depois, com os 30 seguintes
        por varrer. O erro vira linha do relatório; o rastro completo fica no log.
        """
        resultados: list[LivroVarrido] = []
        for numero, caminho in enumerate(escopo.books, start=1):
            if self._cancelar.is_set():
                break
            resultados.append(
                self._varrer_um(
                    caminho,
                    numero=numero,
                    livros=len(escopo.books),
                    coletor=coletor if mesmo_arquivo(caminho, aberto) else None,
                    pular_completos=escopo.skip_complete,
                )
            )
        self._lote_pronto.emit(escopo, resultados, aberto)

    def _varrer_um(
        self, caminho: Path, *, numero: int, livros: int, coletor: Any, pular_completos: bool
    ) -> LivroVarrido:
        try:
            # Retomar de onde parou (S-120): o índice no disco pode ser parcial de uma varredura
            # cancelada, e `build_gallery_index` ignora sozinho o que estiver completo.
            anterior = self._ler_indice(caminho)
            if pular_completos and anterior is not None and anterior.complete and anterior.entries:
                return LivroVarrido(caminho, pulado=f"{len(anterior.entries)} diagrama(s), índice completo")
            indice = build_gallery_index(
                caminho,
                self._model_path(),
                resume_from=anterior,
                max_boards_per_page=self._max_boards(),
                reading_order=DEFAULT_READING_ORDER,
                cancel_event=self._cancelar,
                progress_callback=partial(
                    self._progresso, coletor=coletor, nome=caminho.name, numero=numero, livros=livros
                ),
                # `model_session` empresta o modelo do serviço em vez de carregar outro (S-57).
                model_session=self._service.model_session(self._model_path()),
                caption_reader=getattr(self._service, "caption_reader", None),
                # A fila de revisão sai desta mesma passada (S-119).
                on_scanned=None if coletor is None else coletor.feed,
            )
            self._gravar_indice(caminho, indice)
            return LivroVarrido(caminho, indice=indice)
        except Exception as exc:  # noqa: BLE001 - a varredura toca modelo, PDF e disco
            logger.exception("Varredura de %s falhou.", caminho.name)
            return LivroVarrido(caminho, erro=exc)

    def _progresso(
        self,
        pagina: int,
        total: int,
        _diagramas: int,
        _aceitos: int,
        coletor: Any = None,
        nome: str = "",
        numero: int = 1,
        livros: int = 1,
    ) -> None:
        onde = "" if livros == 1 else f"livro {numero} de {livros} · "
        if self._busy_token is not None:
            # O número no registro é o que vira barra determinada no rodapé (S-164). **Um só**: a
            # varredura é uma desde a S-119, e dois registros dariam duas barras contando o mesmo.
            self._busy_token.update(f"{onde}página {pagina} de {total}", feito=pagina, total=total)
        self._progrediu.emit(
            f"varrendo {onde}página {pagina} de {total}..."
            if livros == 1
            else f"{onde}{nome[:24]}: página {pagina} de {total}..."
        )
        if coletor is not None:
            coletor.progress(pagina, total)

    def _lote_terminou(self, escopo: ScanScope, resultados: list[LivroVarrido], aberto: Path | None) -> None:
        """Fecha a operação e conta o que aconteceu -- por livro, ou em uma linha para o lote.

        **A fila de revisão é entregue daqui**, e não da thread: `aplicar_varredura` grava o
        arquivo e redesenha uma tabela, e as duas coisas são da thread da janela (S-119).
        """
        self._varrendo = False
        self._ocupado(False)

        # Só o livro aberto volta para a tela desta aba. Carregar o índice de outro deixaria a
        # galeria mostrando diagramas de um livro que o visualizador não tem aberto, e a sincronia
        # das duas abas (S-67) passaria a virar páginas erradas.
        if aberto is not None and any(mesmo_arquivo(item.path, aberto) for item in resultados):
            self.load_pdf(aberto)
        if self._coletor_do_lote is not None:
            # A fila fica como estava quando nada foi lido; o que não pode ficar é a aba de
            # revisão com o botão cinza para sempre por causa do que aconteceu deste lado.
            self._coletor_do_lote.deliver(cancelled=self._cancelar.is_set())
            self._coletor_do_lote = None
        # **A varredura é o momento em que os números das abas mudam** (S-398), e era o único que
        # não avisava a janela.
        self.anotacoes_mudaram.emit()

        if not resultados:
            self.lbl_varredura.setText("cancelada")
            self.estado.emit("Varredura cancelada antes do primeiro livro: nada foi lido.")
            return
        if len(resultados) == 1 and len(escopo.books) == 1:
            self._relatar_um_livro(resultados[0], aberto)
            return
        for item in resultados:
            logger.info("Varredura: %s", item.resumo)
        feitos = sum(1 for item in resultados if item.indice is not None)
        self.lbl_varredura.setText(f"{feitos} de {len(escopo.books)} livro(s)")
        self.estado.emit(f"Galeria: {resumo_do_lote(resultados, pedidos=len(escopo.books))}.")

    def _relatar_um_livro(self, item: LivroVarrido, aberto: Path | None) -> None:
        """Diz **quanto do livro** foi varrido, e não só quantos diagramas saíram (S-120).

        Um índice truncado é indistinguível de um completo pelo número de diagramas -- é a parte
        do defeito que custa mais que o tempo perdido --, então o estado parcial vira texto na
        tela, com a página em que a varredura parou e o convite a continuar.
        """
        if item.erro is not None:
            self.lbl_varredura.setText("falhou")
            QMessageBox.critical(self, "Galeria", f"Não foi possível varrer o livro:\n{item.erro}")
            return
        if item.pulado:  # defensivo: com um livro só o escopo não pula nada
            self.lbl_varredura.setText("pulado")
            self.estado.emit(f"Galeria: {item.path.name} pulado — {item.pulado}.")
            return

        indice = item.indice
        do_aberto = aberto is not None and mesmo_arquivo(item.path, aberto)
        # Do modelo quando é o livro da tela (é ele que a pessoa vai navegar agora), do índice
        # quando não é: o modelo não foi trocado, e citar o número dele seria falar do livro errado.
        quantos = len(self.model) if do_aberto else len(indice or ())
        onde = "" if do_aberto else f" em {item.path.name}"
        if bool(getattr(indice, "complete", True)):
            self.lbl_varredura.setText(f"{quantos} diagrama(s)")
            self.estado.emit(f"Galeria: {quantos} diagrama(s) varrido(s){onde}, livro inteiro.")
            return
        ate = int(getattr(indice, "last_page_done", -1))
        self.lbl_varredura.setText(f"{quantos} diagrama(s) — parcial até a página {ate + 1}")
        self.estado.emit(
            f"Galeria: **parcial**. {quantos} diagrama(s){onde} até a página {ate + 1}; "
            "varrer de novo continua daí, sem repetir o que já foi lido."
        )

    # ------------------------------------------------------------------- busca na base (S-72)

    def _bases_atuais(self) -> list[Path]:
        """As bases que valem agora: as escolhidas, ou a pasta inteira enquanto ninguém escolheu."""
        return database_paths() if self._bases is None else list(self._bases)

    def _caminho_do_cache(self, bases: Sequence[Path]) -> Path:
        """O arquivo de cache **deste** conjunto de bases. Ver `escolha_de_bases.store_path_for`."""
        return store_path_for(bases, default_bases=database_paths())

    def _escolher_bases(self) -> list[Path] | None:
        """Pergunta em quais bases procurar. `None` é "desistiu", e aí nada acontece.

        A resposta é adotada **antes** de a busca começar: trocar o conjunto troca o cache de
        posições junto, e uma busca que rodasse com o conjunto novo e o cache antigo devolveria
        contagens de uma base sobre as partidas de outra.
        """
        atuais = self._bases_atuais()
        if self._perguntar_bases is not None:
            escolhidas = self._perguntar_bases(atuais)
        else:
            escolhidas = perguntar_bases(self, selected=atuais)
        if escolhidas is None:
            return None
        escolhidas = list(escolhidas)
        if escolhidas == atuais:
            # Confirmar o que já valia não pode custar uma reabertura do cache: a conexão em pé
            # responde pelo mesmo conjunto, e fechá-la e reabri-la seria trabalho por nada.
            self._bases = tuple(escolhidas)
            return escolhidas
        self._bases = tuple(escolhidas)
        self.model.database_paths = tuple(escolhidas)
        # Reabre o cache no arquivo deste conjunto. Sem isto a conexão aberta continuaria
        # respondendo pelo conjunto anterior -- e ela é a que preenche a lista de candidatas.
        self._abrir_cache_de_posicoes()
        return escolhidas

    def buscar_por_nome(self) -> None:
        """Procura na base de partidas o que as legendas deste livro nomeiam (S-72/S-93).

        **Uma passada por livro, não por diagrama.** Ler a base inteira custa ~150 s por gigabase;
        os pares de nomes vão todos juntos, e a resposta sai para os 178 de uma vez.
        """
        if self._varrendo:
            return
        if self.model.is_empty:
            # Pré-condição de uma frase: rodapé (S-164). O `SEM_BASE` abaixo continua modal -- ele
            # é uma instrução de várias linhas, e o rodapé é uma linha só.
            self.estado.emit("Varra o livro antes: a busca usa as legendas dos diagramas.")
            return
        if not self._bases_atuais():
            QMessageBox.information(self, "Base de partidas", SEM_BASE)
            return
        bases = self._escolher_bases()
        if not bases:
            return
        pares = self.model.pending_pairs()
        if not pares:
            self.estado.emit(
                "Nenhuma legenda deste livro traz os dois jogadores; a base não tem por onde procurar."
            )
            return

        self._varrendo = True
        self._cancelar.clear()
        # Curta perto das outras duas: ~150 s por gigabase, uma passada só. Fechar no meio custa
        # esse tempo de novo, e nada além dele.
        self._registrar_ocupado("busca por nome na base", loses_work=False, detail=f"{len(pares)} par(es)")
        self._ocupado(True)
        self.lbl_varredura.setText(f"procurando {len(pares)} par(es) em {len(bases)} base(s)...")
        threading.Thread(target=self._trabalho_por_nome, args=(bases, pares), daemon=True).start()

    def _trabalho_por_nome(self, bases: list[Path], pares: set[tuple[str, str]]) -> None:
        try:
            partidas = scan_by_players(
                bases,
                pares,
                progress=lambda lidas: self._progrediu.emit(f"base: {lidas / 1e6:.1f} M partidas lidas..."),
                cancel=self._cancelar,
            )
            casamentos = match_entries(self.model.index.entries, partidas)
            self._busca_pronta.emit(casamentos, len(partidas))
        except Exception as exc:  # noqa: BLE001 - a base é de terceiro e o arquivo é enorme
            logger.exception("Busca na base falhou.")
            self._busca_falhou.emit(str(exc))

    def _busca_terminou(self, casamentos: list[DiagramMatch], pares_achados: int) -> None:
        self._varrendo = False
        self._ocupado(False)

        relatorio = self.model.apply_matches(casamentos)
        self._gravar()
        self.refresh(request_page=False)
        self.lbl_varredura.setText(f"{len(casamentos)} diagrama(s) casado(s)")
        self.estado.emit(
            f"Base: {pares_achados} par(es) com partida, {relatorio.confirmed} leitura(s) confirmada(s), "
            f"{relatorio.fields} campo(s) preenchido(s) em {relatorio.touched} diagrama(s). "
            "Nada foi sobrescrito."
        )

    def _falhou(self, detalhe: str) -> None:
        self._varrendo = False
        self._ocupado(False)
        self.lbl_varredura.setText("falhou")
        QMessageBox.critical(self, "Base de partidas", f"Não foi possível ler a base:\n{detalhe}")

    # ------------------------------------------------------- busca pela posição (S-92)

    def buscar_por_posicao(self) -> None:
        """Procura na base as **posições** deste livro -- todas, numa passada só (S-92).

        **O que ela alcança, e o caminho por nome não.** A busca por nome depende de a legenda
        trazer os dois jogadores, e a maioria não traz: no acervo medido, 53,9% dos diagramas não
        casaram com partida nenhuma. Aqui a pergunta são as **64 casas lidas**, que todo diagrama
        tem.

        **E o preço é dito antes.** Meia hora atrás de um botão que não avisa é uma janela travada;
        a caixa diz quantas posições faltam, quanto custa e que a resposta fica guardada. Se nada
        faltar, a base **não é aberta** e a resposta sai do cache na hora.
        """
        if self._varrendo:
            return
        if self.model.is_empty:
            self.estado.emit("Varra o livro antes: a busca usa as posições dos diagramas.")
            return
        if not self._bases_atuais():
            QMessageBox.information(self, "Base de partidas", SEM_BASE)
            return
        bases = self._escolher_bases()
        if not bases:
            return

        alvos = {entrada.placement for entrada in self.model.index.entries if entrada.placement}
        self._abrir_cache_de_posicoes()
        if self._store is None:
            self.estado.emit("O cache de posições não abriu; a busca precisa dele para não repetir a base.")
            return
        faltando = self._store.missing(alvos)
        if not faltando:
            self._posicoes_terminaram(alvos, 0)
            return
        resposta = QMessageBox.question(
            self,
            "Base de partidas",
            f"{len(faltando)} das {len(alvos)} posições deste livro nunca foram perguntadas à "
            f"base ({len(bases)} arquivo(s) .pgn).\n\n"
            "Procurá-las custa uma passada pelos arquivos inteiros, reproduzindo os lances de "
            "milhões de partidas: cerca de meia hora por gigabase. As outras posições já saem do "
            "cache.\n\n"
            "A resposta fica guardada -- da próxima vez isto responde em segundos, e um livro novo "
            "custa só as posições que ele trouxer.\n\n"
            "Dá para cancelar no meio, mas aí a passada é descartada inteira: meia base lida dá "
            "contagens que não valem.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if resposta != QMessageBox.StandardButton.Ok:
            return

        self._varrendo = True
        self._cancelar.clear()
        # **A mais cara do programa**, ~56 min medidos na Fase 13, e a única cujo resultado é
        # tudo-ou-nada: o cache só é gravado depois da passada inteira.
        self._registrar_ocupado(
            "busca por posição na base", loses_work=True, detail=f"{len(faltando)} posição(ões)"
        )
        self._ocupado(True)
        self.lbl_varredura.setText(f"base: {len(faltando)} posição(ões) a procurar...")
        threading.Thread(
            target=self._trabalho_por_posicao,
            args=(bases, alvos, faltando, self._caminho_do_cache(bases)),
            daemon=True,
        ).start()

    def _trabalho_por_posicao(
        self, bases: list[Path], alvos: set[str], faltando: set[str], caminho_do_cache: Path
    ) -> None:
        """A passada pela base, fora da thread da janela -- **com a conexão dela** (S-140).

        A conexão de `self._store` é da thread da janela e continua respondendo à tela enquanto
        isto roda; uma segunda, aberta e fechada aqui, é o que evita duas threads no mesmo objeto
        de banco.
        """
        try:
            indice = scan_by_positions(
                bases, faltando, progress=self._progresso_por_posicao, cancel=self._cancelar
            )
            if self._cancelar.is_set():
                self._posicoes_paradas.emit("cancelada")
                return
            if not indice.complete:
                # Descartada sem ninguém ter cancelado: um processo morreu no meio (S-171).
                self._posicoes_paradas.emit("interrompida")
                return
            # `faltando` inteiro, e não só as posições que casaram: uma posição que a base não
            # conhece precisa ficar registrada como **perguntada**, senão ela volta ao alvo de toda
            # busca futura -- e no acervo medido essas são a maioria (S-84).
            with open_store(caminho_do_cache, database=bases) as gravacao:
                gravacao.update(indice, faltando)
            self._posicoes_prontas.emit(alvos, indice.games_read)
        except Exception as exc:  # noqa: BLE001 - a base é de terceiro e o arquivo é enorme
            logger.exception("Busca por posição falhou.")
            self._busca_falhou.emit(str(exc))

    def _progresso_por_posicao(self, feitos: int, total: int) -> None:
        if self._busy_token is not None:
            # A mais cara do programa -- ~56 min medidos na Fase 13 -- e a que mais precisa de uma
            # fração: só o número diz se vale esperar ou cancelar agora (S-164).
            self._busy_token.update(f"pedaço {feitos} de {total}", feito=feitos, total=total)
        self._progrediu.emit(f"base: pedaço {feitos} de {total}...")

    def _posicoes_terminaram(self, alvos: set[str], games_read: int) -> None:
        """Aplica o que a base respondeu e **deixa o cache em pé** para a lista de candidatas.

        O botão "Partidas da base" acende no mesmo gesto: a conexão que a tela já tem enxerga as
        linhas que a thread gravou. Mandar a pessoa reabrir o livro para vê-las seria esconder o
        que ela pagou meia hora para ter.
        """
        self._varrendo = False
        self._ocupado(False)
        cache = self._store
        if cache is None:  # pragma: no cover - só acontece se o cache fechou no meio
            self.estado.emit("A busca terminou, mas o cache de posições fechou antes de responder.")
            return
        self.model.position_cache = cache

        casamentos = match_positions(self.model.index.entries, cache.to_index(alvos))
        relatorio = self.model.apply_matches(casamentos)
        self._gravar()
        self.refresh(request_page=False)
        self.lbl_varredura.setText(f"{len(casamentos)} diagrama(s) casado(s) por posição")
        if not games_read:
            origem = "sem abrir a base (tudo do cache)"
        elif games_read >= 1_000_000:
            origem = f"{games_read / 1e6:.1f} M partidas lidas"
        else:
            # Uma base pequena lida em "0,0 M" pareceria uma varredura que não leu nada.
            origem = f"{games_read} partidas lidas"
        self.estado.emit(
            f"Base por posição: {origem}, {relatorio.confirmed} leitura(s) confirmada(s), "
            f"{relatorio.fields} campo(s) preenchido(s) em {relatorio.touched} diagrama(s). "
            "Nada foi sobrescrito."
        )

    def _posicoes_pararam(self, motivo: str) -> None:
        """Cancelada ou interrompida -- e a frase é diferente nos dois casos, de propósito.

        No cancelamento a pessoa sabe o que fez; na interrupção (S-171) ela não fez nada e precisa
        saber que **pode tentar de novo** -- nada foi gravado, então as colocações continuam por
        perguntar. Nos dois, o que a tela não pode fazer é deixar parecer que gravou.
        """
        self._varrendo = False
        self._ocupado(False)
        self.lbl_varredura.setText(motivo)
        if motivo == "cancelada":
            self.estado.emit(
                "Busca por posição cancelada. Uma passada interrompida viu parte da base, e as "
                "contagens dela não valem -- nada foi gravado no cache."
            )
            return
        self.estado.emit(
            "A busca por posição foi interrompida: um dos processos de leitura da base morreu. "
            "Nada foi gravado, e as posições continuam por perguntar -- dá para tentar de novo. "
            # Onde o rastro está, e não "no log" (S-421): num checkout não há arquivo de log.
            + onde_esta_o_rastro()
        )

    # ------------------------------------------------------- a lista de candidatas (S-86)

    def abrir_lista_de_partidas(self) -> DialogoDePartidas | None:
        """Abre a lista de partidas que contêm a posição deste diagrama.

        **Lê o cache, não a base.** É o que faz disto um clique e não uma janela travada por meia
        hora: a varredura já respondeu, e a resposta está em `data/games_positions.sqlite`.
        """
        candidatas, _total = self.model.current_candidates()
        # Sem candidata a janela ainda abre **se a legenda nomeia os jogadores**: é o caminho da
        # S-87, e ele alcança os 1.922 diagramas do acervo (53,9%) cuja posição não casou.
        if not candidatas and self.model.current_caption_pair() is None:
            QMessageBox.information(
                self,
                "Partidas da base",
                "Nenhuma partida da base contém esta posição, e a legenda não nomeia os dois "
                "jogadores para procurar por nome.\n\n"
                'Se este livro nunca foi perguntado à base pela posição, o botão "Buscar pela '
                'posição" faz isso -- ou, para o acervo inteiro de uma vez:  cvoff-games --all',
            )
            return None
        dialogo = DialogoDePartidas(self, modelo=self.model)
        dialogo.aplicou.connect(self._candidata_aplicada)
        dialogo.show()
        return dialogo

    def _candidata_aplicada(self, mensagem: str) -> None:
        """Volta da janela de candidatas: grava, redesenha e conta o que houve.

        **E avisa quem pinta as caixas da página** (S-116): escolher uma candidata é o que grava
        `confirmed_from`, e é o violeta do visualizador.
        """
        self._gravar()
        self.refresh(request_page=False)
        self.anotacoes_mudaram.emit()
        self.estado.emit(mensagem)

    def _abrir_cache_de_posicoes(self) -> None:
        """Deixa o cache de posições aberto e apontado à base de agora. Falha em silêncio.

        Sem cache o botão fica desligado e o resto da aba funciona igual: a lista é um caminho a
        mais, e não uma pré-condição para anotar um livro.

        **Aberto uma vez, e não relido por livro (S-140).** A base é reconferida a cada chamada
        porque é a única coisa que pode ter mudado: um `.pgn` a mais na pasta muda as contagens de
        tudo que está guardado, e uma conexão aberta antes dele responderia o número de ontem.
        """
        bases = self._bases_atuais()
        caminho = self._caminho_do_cache(bases)
        try:
            if self._store is not None:
                if self._store.path == caminho and self._store.matches(bases):
                    self.model.position_cache = self._store
                    return
                self._store.close()
                self._store = None
            self._store = open_store(caminho, database=bases)
            self.model.position_cache = self._store
        except Exception:  # noqa: BLE001 - cache é material derivado; sem ele a aba segue
            logger.exception("Não foi possível ler o cache de posições.")
            self._store = None
            self.model.position_cache = None

    def _atualizar_botao_de_candidatas(self) -> None:
        candidatas, total = self.model.current_candidates()
        if not candidatas:
            pode_por_nome = self.model.current_caption_pair() is not None
            self.btn_candidatas.setText("Procurar por nome" if pode_por_nome else "Partidas da base")
            self.btn_candidatas.setEnabled(pode_por_nome)
            return
        # O número no botão é o que faz a pessoa saber que há o que escolher **antes** de clicar:
        # um diagrama com 47 candidatas e um com uma só pedem gestos diferentes.
        self.btn_candidatas.setText(f"Partidas da base ({total})")
        self.btn_candidatas.setEnabled(True)

    # ------------------------------------------------------------------------ ciclo de vida

    def load_pdf(self, pdf_path: Path | None, *, request_page: bool = True) -> None:
        """Troca o livro: carrega o índice já varrido, se houver, e as anotações.

        `request_page` desligado é o caminho de quem **abre** o PDF: ali o visualizador acabou de
        restaurar a página em que o usuário parou (S-25), e a galeria pedir a página do seu
        primeiro diagrama jogaria essa restauração fora.
        """
        if pdf_path is None:
            self.model = GalleryModel()
            self.refresh(request_page=request_page)
            return

        indice = self._ler_indice(pdf_path)
        self.model = GalleryModel(
            index=indice if indice is not None else self.model.index.__class__(),
            # As anotações são carregadas mesmo sem varredura: elas não dependem do índice, e desde
            # a S-71 a aba Resultado escreve o número do lance por aqui.
            annotations=self._ler_anotacoes(pdf_path),
            pdf_path=pdf_path,
            database_paths=tuple(self._bases_atuais()),
            index_path=DEFAULT_INDEX_PATH,
            gallery_dir=self._pasta,
        )
        self._abrir_cache_de_posicoes()
        if indice is None:
            self.lbl_varredura.setText("livro ainda não varrido")
        self.refresh(request_page=request_page)

    # ---------------------------------------------------------------- onde o livro é gravado
    #
    # Os três lêem `data/gallery/` quando ninguém disse outra coisa, e é o mesmo diretório nos
    # três: um índice gravado num lugar e lido de outro é um livro que "desvarreu" sozinho.

    def _ler_indice(self, pdf_path: Path):  # noqa: ANN202 - `GalleryIndex | None`, sem importá-lo
        return load_index(pdf_path) if self._pasta is None else load_index(pdf_path, directory=self._pasta)

    def _gravar_indice(self, pdf_path: Path, indice: Any) -> Path:
        if self._pasta is None:
            return save_index(pdf_path, indice)
        return save_index(pdf_path, indice, directory=self._pasta)

    def _ler_anotacoes(self, pdf_path: Path):  # noqa: ANN202 - `GalleryAnnotations`
        if self._pasta is None:
            return load_annotations(pdf_path)
        return load_annotations(pdf_path, directory=self._pasta)

    # ------------------------------------------------- anotação vinda de fora (S-71)
    # A aba Resultado também edita o número do lance, e as duas têm de falar do mesmo diagrama.
    # Quem guarda a anotação em memória é este painel -- duas cópias do mesmo arquivo JSON
    # divergiriam, e a última a gravar apagaria o que a outra tinha escrito.

    def move_number_at(self, page_index: int, diagram_index: int) -> int | None:
        return self.model.annotations.get(page_index, diagram_index).move_number

    def set_move_number(self, page_index: int, diagram_index: int, value: int | None) -> None:
        """Grava o número do lance daquele diagrama. `None` apaga a declaração.

        Em branco **apaga** em vez de gravar zero: não declarar e declarar vazio são coisas
        diferentes, e só a primeira deixa a exportação decidir.
        """
        self.model.annotations.update(page_index, diagram_index, move_number=value)
        self._gravar()
        if self.model.pdf_path is not None:
            self.refresh(request_page=False)

    def sync_to_page(self, page_index: int) -> None:
        """O visualizador virou a página; a galeria acompanha se houver diagrama lá."""
        if self._sincronizando or self.model.is_empty:
            return
        if self.model.sync_to_page(page_index):
            self.refresh(request_page=False)

    def _ir(self, passo: int, *, absoluto: bool = False) -> None:
        if absoluto:
            mudou = self.model.go_to(0 if passo >= 0 else len(self.model) - 1)
        else:
            mudou = self.model.step(passo)
        if mudou:
            self.refresh()

    # ------------------------------------------------------ o dono das ações (S-400)

    def acoes_proprias(self) -> frozenset[str]:
        """As ações globais que esta aba atende enquanto tem o foco. Ver `ACOES_PROPRIAS`.

        **Vazio enquanto o cursor está num campo**, pela mesma razão da sala de estudo: esta aba
        tem o campo do lance, os oito de header e a legenda selecionável, e ali `←` é do campo.
        `atalhos.cede_a_sequencia` é a régua que os dois frontends usam.
        """
        from PyQt6.QtWidgets import QApplication

        foco = QApplication.focusWidget()
        if isinstance(foco, (QLineEdit, QTextEdit)):
            return frozenset()
        return ACOES_PROPRIAS

    def atender(self, acao: str) -> Callable[[], object] | None:
        """A função desta aba para aquela ação, ou `None` se ela não a atende.

        São os mesmos quatro comandos dos botões de navegação, e de propósito: `atalhos.destino`
        devolve **função**, e uma segunda escrita de "o que a seta faz aqui" seria a divergência
        que o catálogo da S-324 veio tirar do programa.
        """
        return {
            "diagrama_anterior": partial(self._ir, -1),
            "proximo_diagrama": partial(self._ir, 1),
            "primeira_pagina": partial(self._ir, 0, absoluto=True),
            "ultima_pagina": partial(self._ir, -1, absoluto=True),
        }.get(acao)

    # -------------------------------------------------------------------------------- edição

    def _gravar_se_mudou(self, antes: DiagramAnnotation) -> None:
        """Grava só se a anotação de fato mudou (S-109).

        O modelo já é no-op quando nada muda; o que esta guarda evita é a **escrita**. Os quatro
        `_gravar_*` são disparados ao *passar* por um campo -- e sem isto percorrer os headers de
        um diagrama reescreveria o arquivo do livro inteiro oito vezes, uma por campo.
        """
        if self.model.current_annotation != antes:
            self._gravar()

    def _gravar_lance(self) -> None:
        if self._montando:
            return
        antes = self.model.current_annotation
        escrito = self.campo_lance.text().strip()
        if not escrito:
            self.model.edit(move_number=None)
        else:
            try:
                self.model.edit(move_number=max(1, int(escrito)))
            except ValueError:
                # Devolver o campo ao valor gravado e não abrir caixa: digitar e apagar é normal,
                # e um diálogo por tecla errada tornaria a galeria insuportável.
                self.estado.emit(f"Lance inválido: {escrito!r}. Mantido o valor anterior.")
        self._gravar_se_mudou(antes)

    def _valor_marcado(self, grupo: QButtonGroup) -> str:
        marcado = grupo.checkedButton()
        return "" if marcado is None else str(marcado.property("valor"))

    def _gravar_lado(self) -> None:
        if self._montando:
            return
        antes = self.model.current_annotation
        self.model.edit(side_to_move=self._valor_marcado(self.lado) or None)
        self._gravar_se_mudou(antes)

    def _gravar_link(self) -> None:
        if self._montando:
            return
        antes = self.model.current_annotation
        escolha = self._valor_marcado(self.link)
        self.model.edit(lichess_link=None if escolha == "" else escolha == "sim")
        self._gravar_se_mudou(antes)

    def _gravar_header(self, nome: str) -> None:
        if self._montando:
            return
        antes = self.model.current_annotation
        self.model.set_header(nome, self.campos_de_header[nome].text())
        self._gravar_se_mudou(antes)

    def _gravar_header_livre(self) -> None:
        nome = self.campo_livre_nome.text().strip()
        if not nome:
            return
        self.model.set_header(nome, self.campo_livre_valor.text())
        self.campo_livre_nome.clear()
        self.campo_livre_valor.clear()
        self._gravar()
        self.estado.emit(f"Header {nome} gravado neste diagrama.")

    def limpar_headers(self) -> None:
        """Apaga os headers **deste** diagrama, todos de uma vez -- perguntando antes (S-94).

        A pergunta **nomeia os valores que vão sair**: uma confirmação que não diz o que vai
        acontecer não é confirmação, é obstáculo -- e aqui o que se apaga pode ser meia hora de
        digitação de quem tinha o livro na mão. Não há desfazer, e a caixa diz isso.
        """
        valores = dict(self.model.current_annotation.headers)
        if not valores:
            self.estado.emit("Este diagrama não tem header declarado; não há o que limpar.")
            return
        listados = "\n".join(f"    {nome} = {valor}" for nome, valor in sorted(valores.items()))
        if not self._confirmar_destrutivo(
            "Limpar os headers",
            f"Apagar {len(valores)} header(s) deste diagrama?\n\n{listados}\n\n"
            "Só deste diagrama, e não dá para desfazer. O lance, a vez e a partida escolhida na "
            "lista de candidatas ficam como estão.",
        ):
            self.estado.emit("Limpeza cancelada.")
            return

        apagados = self.model.clear_headers()
        self._gravar()
        self.refresh(request_page=False)
        self.estado.emit(f"{len(apagados)} header(s) apagado(s) deste diagrama: {', '.join(apagados)}.")

    def _confirmar_destrutivo(self, titulo: str, pergunta: str) -> bool:
        """Uma pergunta de aviso cujo botão **padrão é cancelar**.

        É o `default=messagebox.CANCEL` do outro lado, e ele não é zelo: as duas perguntas que
        passam por aqui apagam trabalho manual, e num diálogo cujo padrão é OK um `Enter` de
        reflexo confirma o que a pessoa ia ler.
        """
        caixa = QMessageBox(self)
        caixa.setIcon(QMessageBox.Icon.Warning)
        caixa.setWindowTitle(titulo)
        caixa.setText(pergunta)
        caixa.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        caixa.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return caixa.exec() == QMessageBox.StandardButton.Ok

    def copiar_para_todos(self) -> None:
        """Copia os headers deste diagrama para o livro inteiro -- **perguntando antes**.

        A pergunta nomeia os valores e conta os diagramas porque a ação é irreversível na parte que
        importa: ela **sobrescreve** o mesmo campo em centenas de anotações, e o valor anterior
        deixa de existir. Um clique já espalhou "Ljubojevic / Browne / Amsterdam / 1972" por 1.405
        diagramas de um livro de 1.408.
        """
        valores = self.model.headers_to_apply()
        if not valores:
            self.estado.emit("Nada a copiar: nenhum header preenchido neste diagrama.")
            return
        alvos = max(0, len(self.model) - 1)
        listados = "\n".join(f"    {nome} = {valor}" for nome, valor in valores.items())
        if not self._confirmar_destrutivo(
            "Copiar headers para todos",
            f"Copiar estes valores para os outros {alvos} diagrama(s) do livro?\n\n{listados}\n\n"
            "O que esses diagramas tiverem nesses campos será sobrescrito, e o valor anterior não "
            "poderá ser recuperado.",
        ):
            self.estado.emit("Cópia cancelada.")
            return

        atingidos = self.model.apply_headers_to_all()
        self._ultima_copia = dict(valores)
        self.btn_desfazer.setEnabled(bool(atingidos))
        self._gravar()
        self.estado.emit(f"Headers copiados para {atingidos} outro(s) diagrama(s). Dá para desfazer.")

    def desfazer_copia(self) -> None:
        """Tira dos outros diagramas o que a última cópia espalhou.

        Apaga **pelo valor**, e não pela chave: o `Event` que a base preencheu certo em cada
        diagrama e o que foi digitado um a um continuam onde estão.
        """
        if not self._ultima_copia:
            return
        atingidos = self.model.revert_headers(self._ultima_copia)
        self._ultima_copia = {}
        self.btn_desfazer.setEnabled(False)
        self._gravar()
        self.refresh(request_page=False)
        self.estado.emit(f"Cópia desfeita: header removido de {atingidos} diagrama(s).")

    # ------------------------------------------------------------------------ cópia e desenho

    def caption(self) -> str:
        """A legenda como está na tela. É por aqui que o teste a lê, sem tocar no widget."""
        return self.legenda.toPlainText().strip()

    def copiar_legenda(self) -> None:
        """Copia a legenda inteira. Nada sai da máquina -- é a área de transferência local."""
        from PyQt6.QtWidgets import QApplication

        conteudo = self.caption()
        if not conteudo:
            self.estado.emit("Este diagrama não tem legenda para copiar.")
            return
        area = QApplication.clipboard()
        if area is not None:
            area.setText(conteudo)
        self.estado.emit("Legenda copiada.")

    def exportar_diagramas(self) -> object:
        """Os diagramas varridos deste livro como arquivos soltos, um por posição (S-544).

        **A origem é o índice da varredura, e não a sala de estudo.** São as duas metades do
        mesmo item: aqui saem os quinhentos diagramas de um livro digitalizado, com a FEN que o
        modelo leu e a página impressa no nome do arquivo; do lado da sala saem os que alguém
        analisou. A decisão de o que vira `ItemDoLote` é de `ui/lote_de_diagramas.da_galeria`.
        """
        from chess_diagram_ocr.qt.lote_de_diagramas import abrir_lote_de_diagramas
        from chess_diagram_ocr.ui.lote_de_diagramas import da_galeria

        aberto = self.model.pdf_path
        livro = Path(aberto).stem if aberto else ""
        itens = da_galeria(self.model.index.entries, livro=livro)
        if not itens:
            self.estado.emit("Varra o livro antes: não há diagrama indexado para exportar.")
            return None
        return abrir_lote_de_diagramas(
            self,
            itens=itens,
            origem=f"{len(itens)} diagrama(s) varrido(s) de {livro or 'este livro'}.",
            pasta=Path(aberto).parent if aberto else DEFAULT_PDF_DIR,
            busy=self._busy_registry,
        )

    def copiar_link(self) -> None:
        from PyQt6.QtWidgets import QApplication

        url = self.model.lichess_url()
        if not url:
            return
        area = QApplication.clipboard()
        if area is not None:
            area.setText(url)
        self.estado.emit("Link do Lichess copiado. Nada saiu da máquina.")

    def _gravar(self) -> None:
        caminho = self.model.save()
        if caminho is not None:
            self.estado.emit(f"Galeria: {self.model.annotated_count()} diagrama(s) anotado(s).")

    def refresh(self, *, request_page: bool = True) -> None:
        """Redesenha tudo a partir do modelo. Único caminho de atualização da tela.

        `_montando` é a guarda contra o laço: escrever num campo dispara o sinal dele, que
        chamaria de volta quem acabou de escrever -- e no Qt `setChecked` de um `QRadioButton`
        dispara mesmo quando o valor não muda.
        """
        self._montando = True
        try:
            atual = self.model.current
            self.lbl_posicao.setText(self.model.describe_position())
            self._desenhar_recorte(atual)

            anotacao = self.model.current_annotation
            self.campo_lance.setText("" if anotacao.move_number is None else str(anotacao.move_number))
            self._marcar(self.lado, anotacao.side_to_move or (atual.side_to_move if atual else "w"))
            self._marcar(
                self.link,
                "" if anotacao.lichess_link is None else ("sim" if anotacao.lichess_link else "não"),
            )
            for nome, campo in self.campos_de_header.items():
                campo.setText(anotacao.headers.get(nome, ""))
            self.lbl_origem.setText(describe_origin(anotacao))
            self._mostrar_legenda(atual.caption if atual else "")
            # Desligado onde não há header: um botão que responde "não há o que limpar" é um botão
            # que mente sobre estar disponível, e a pergunta que ele abriria seria vazia.
            self.btn_limpar.setEnabled(bool(anotacao.headers))
            # Cinza sem índice: exportar zero diagramas abriria um diálogo para dizer que não há
            # nada, e a resposta certa a "varra o livro antes" é o botão não convidar ao clique.
            self.btn_diagramas.setEnabled(not self.model.is_empty)
            self._atualizar_botao_de_candidatas()
        finally:
            self._montando = False

        if request_page and atual is not None:
            # A guarda evita o círculo: o visualizador avisa de volta que a página mudou.
            self._sincronizando = True
            try:
                self.pediu_pagina.emit(atual.page_index)
            finally:
                self._sincronizando = False

    def _marcar(self, grupo: QButtonGroup, valor: str) -> None:
        for botao in grupo.buttons():
            if str(botao.property("valor")) == valor:
                botao.setChecked(True)
                return

    def _mostrar_legenda(self, conteudo: str) -> None:
        """Troca o texto exibido. Recomeça no topo: legenda nova, rolagem antiga é confusão."""
        self.legenda.setPlainText(conteudo)
        barra = self.legenda.verticalScrollBar()
        if barra is not None:
            barra.setValue(0)

    def _desenhar_recorte(self, atual: object) -> None:
        caminho = getattr(atual, "image_path", "")
        if not caminho or not Path(caminho).exists():
            self._dizer_no_lugar_do_recorte(
                "varra o livro para ver os diagramas" if self.model.is_empty else "recorte não encontrado"
            )
            return
        pixmap = QPixmap(str(caminho))
        if pixmap.isNull():
            logger.warning("Não foi possível abrir o recorte %s.", caminho)
            self._dizer_no_lugar_do_recorte("recorte ilegível")
            return
        # O `QLabel` é dono do pixmap: não há a referência a segurar que o Tk exige.
        self.recorte.setPixmap(
            pixmap.scaled(
                BOARD_VIEW_SIZE,
                BOARD_VIEW_SIZE,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _dizer_no_lugar_do_recorte(self, frase: str) -> None:
        self.recorte.setPixmap(QPixmap())
        self.recorte.setText(frase)
        tema.pintar(self.recorte, "color", tokens.TEXTO_SECUNDARIO)


_ = atalhos  # noqa: B018 - a régua de foco que `acoes_proprias` cita; ver `ui/atalhos.py`
