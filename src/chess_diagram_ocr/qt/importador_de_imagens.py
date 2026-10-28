"""*Importar imagens*: diagramas de fora do programa para o dataset de treino.

Toda a decisão -- ler o relatório do ChessMeridaOCR, recortar, quando a FEN da fonte entra sozinha,
o que se grava no `labels.csv` e o andamento por pasta -- é de `importacao_de_imagens.py`, que é
puro e tem teste sem janela. Este arquivo é a janela: escolher a pasta, rodar a importação dos que
o modelo confirma e conferir o resto imagem a imagem.

**Duas threads e nenhum widget tocado fora da janela.** Ler um recorte com o modelo custa ~0,4 s, e
o lote do Sigil são 5.600 imagens; as duas coisas correm em `threading.Thread` e voltam por sinal,
como a detecção de duplicatas da aba Dataset. Enquanto o lote corre a conferência fica trancada:
as duas mexeriam nos mesmos itens.

**O modelo é carregado uma vez e na primeira leitura**, não ao abrir a janela: quem só vai olhar o
andamento de uma pasta não paga os segundos do `.pt`.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr import importacao_de_imagens as imp
from chess_diagram_ocr.fen_utils import is_syntactically_valid_fen
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.imagens import pixmap_de_rgb
from chess_diagram_ocr.qt.paleta_de_pecas import PaletaDePecas
from chess_diagram_ocr.qt.tabuleiro_editavel import TabuleiroEditavel
from chess_diagram_ocr.service import OcrService
from chess_diagram_ocr.ui import espaco, estilos, tipografia
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.legality import illegal_save_question

logger = logging.getLogger(__name__)

__all__ = ["FILTROS", "ORIGENS", "JanelaDeImportacao"]

ORIGENS: tuple[tuple[str, str], ...] = (
    (imp.COM_FEN, "Relatório do ChessMeridaOCR (imagens com FEN)"),
    (imp.SEM_FEN, "Pasta de imagens para conferir (sem FEN)"),
)

FILTROS: tuple[tuple[str, str], ...] = (
    ("aviso", "Pendentes com aviso"),
    ("pendentes", "Todas as pendentes"),
    ("puladas", "Puladas"),
    ("todas", "Todas"),
)

LADOS: tuple[tuple[str, str], ...] = (("w", "Brancas jogam"), ("b", "Pretas jogam"))

LADO_DA_IMAGEM = 300
"""Lado, em pixels, da imagem original e do recorte na conferência."""

ARQUIVO_DAS_PASTAS = "ultimas_pastas.json"


def _ler_com_modelo(servico: OcrService) -> Callable[[np.ndarray], str]:
    """Um leitor `recorte -> campo de peças` que empresta o modelo do serviço.

    Pelo `model_session` e não carregando o `.pt` aqui (S-57): o serviço carrega uma vez, na
    primeira leitura, e a trava dele cobre o uso -- uma leitura da conferência pode estar
    terminando quando o lote começa, e o mesmo modelo não roda em duas threads.
    """

    def ler(tabuleiro: np.ndarray) -> str:
        from chess_diagram_ocr.inference import predict_board

        with servico.model_session() as (modelo, dispositivo):
            return predict_board(tabuleiro, modelo, dispositivo).fen_board

    return ler


def _emitir(dono: QWidget, sinal: str, *argumentos: object) -> None:
    """Emite da thread de trabalho -- a não ser que a janela já tenha sido destruída.

    A leitura de um recorte pode terminar depois que a pessoa fechou a janela; o PyQt então levanta
    `RuntimeError` já ao buscar o sinal, e a resposta a uma janela que não existe mais é não responder.
    """
    try:
        getattr(dono, sinal).emit(*argumentos)
    except RuntimeError:
        logger.debug("Janela de importação fechada antes da resposta da thread.")


class JanelaDeImportacao(QDialog):
    """Escolher a pasta, importar os confirmados e conferir o resto, uma imagem por vez."""

    amostras_gravadas = pyqtSignal(int)
    """Quantas amostras entraram no `labels.csv` agora. A aba Dataset ouve para reler."""

    _leitura_pronta = pyqtSignal(int, object, str, str)
    """Interno: posição, recorte, qual recorte, campo de peças lido. Vem da thread de leitura."""

    _leitura_falhou = pyqtSignal(int, str)
    _lote_andou = pyqtSignal(int, int, int)
    _lote_acabou = pyqtSignal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        caminhos: Callable[[], tuple[Path, Path, Path]],
        modelo: Callable[[], Path],
        leitor: Callable[[np.ndarray], str] | None = None,
        diretorio_dos_lotes: Path | None = None,
        busy: BusyRegistry | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importar imagens para o dataset")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.resize(1180, 760)
        self._caminhos = caminhos
        self._modelo = modelo
        self._leitor = leitor
        self._servico: OcrService | None = None
        self._diretorio = diretorio_dos_lotes if diretorio_dos_lotes is not None else imp.DIRETORIO_DOS_LOTES

        self.lote: imp.Lote | None = None
        self._arquivo_do_lote: Path | None = None
        self._fila: list[int] = []
        self._i = 0
        self._recorte_atual: np.ndarray | None = None
        self._recorte_usado = ""
        self._leitura: threading.Thread | None = None
        self._rodando_lote: threading.Thread | None = None
        self._cancelar_lote = False
        self._busy = busy
        self._ficha: BusyToken | None = None
        """O registro do lote no rodapé da janela principal: a pergunta ao fechar e o Cancelar."""

        self._montar()
        self._leitura_pronta.connect(self._chegou_leitura)
        self._leitura_falhou.connect(self._falhou_leitura)
        self._lote_andou.connect(self._andou_lote)
        self._lote_acabou.connect(self._acabou_lote)
        self._origem_mudou()
        self._mostrar_item()

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.folga(),) * 4)
        fora.setSpacing(espaco.linha())

        titulo = QLabel("Importar imagens para o dataset", self)
        titulo.setProperty(tipografia.PROPRIEDADE_DE_PAPEL_DE_FONTE, tipografia.TITULO)
        fora.addWidget(titulo)

        fonte = QHBoxLayout()
        self.combo_origem = QComboBox(self)
        for _chave, rotulo in ORIGENS:
            self.combo_origem.addItem(rotulo)
        self.combo_origem.currentIndexChanged.connect(self._origem_mudou)
        dica_em(
            self.combo_origem,
            "Com FEN: a pasta do ChessMeridaOCR (um .html e a pasta imagens/ por livro, ou várias "
            "dessas). Sem FEN: qualquer pasta de imagens -- a proposta é a leitura do modelo e "
            "nada entra no dataset sem você conferir.",
        )
        self.campo_pasta = QLineEdit(self)
        self.campo_pasta.setPlaceholderText("Pasta das imagens")
        self.campo_pasta.returnPressed.connect(self.abrir_pasta)
        escolher = self._botao("Escolher…", self.escolher_pasta, estilos.NEUTRO)
        self.btn_abrir = self._botao("Abrir", self.abrir_pasta, estilos.NEUTRO)
        fonte.addWidget(self.combo_origem)
        fonte.addWidget(self.campo_pasta, 1)
        fonte.addWidget(escolher)
        fonte.addWidget(self.btn_abrir)
        fora.addLayout(fonte)

        lote = QHBoxLayout()
        self.lbl_resumo = QLabel("Nenhuma pasta aberta.", self)
        self.lbl_resumo.setWordWrap(True)
        self.btn_lote = self._botao("Importar os que o modelo confirma", self.importar_confirmados, estilos.NEUTRO)
        dica_em(
            self.btn_lote,
            "Recorta cada imagem pendente, lê com o modelo e grava no dataset as que dão a mesma "
            "posição da FEN do relatório. As que discordam ficam pendentes, com aviso, para "
            "conferir aqui. Pode cancelar e continuar depois.",
        )
        self.btn_cancelar = self._botao("Cancelar", self.cancelar_lote, estilos.NEUTRO)
        self.btn_cancelar.setVisible(False)
        self.barra = QProgressBar(self)
        self.barra.setVisible(False)
        lote.addWidget(self.lbl_resumo, 1)
        lote.addWidget(self.barra)
        lote.addWidget(self.btn_lote)
        lote.addWidget(self.btn_cancelar)
        fora.addLayout(lote)
        # **Uma linha na janela e não uma caixa** (`tests/test_ui_retorno_modal.py`): pasta que não
        # abre, FEN mal digitada e amostra recusada são notícia, e não pedem resposta. A única
        # caixa daqui é a pergunta da posição ilegal, que é decisão.
        self.lbl_aviso = QLabel("", self)
        self.lbl_aviso.setWordWrap(True)
        self.lbl_aviso.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fora.addWidget(self.lbl_aviso)

        self.conferencia = QGroupBox("Conferência", self)
        dentro = QVBoxLayout(self.conferencia)

        navegar = QHBoxLayout()
        self.combo_filtro = QComboBox(self.conferencia)
        for _chave, rotulo in FILTROS:
            self.combo_filtro.addItem(rotulo)
        self.combo_filtro.currentIndexChanged.connect(self._filtro_mudou)
        self.btn_anterior = self._botao("◀ Anterior", lambda: self.andar(-1), estilos.NEUTRO)
        self.btn_proxima = self._botao("Próxima ▶", lambda: self.andar(1), estilos.NEUTRO)
        self.lbl_posicao = QLabel("", self.conferencia)
        navegar.addWidget(QLabel("Mostrar", self.conferencia))
        navegar.addWidget(self.combo_filtro)
        navegar.addWidget(self.btn_anterior)
        navegar.addWidget(self.btn_proxima)
        navegar.addWidget(self.lbl_posicao, 1)
        dentro.addLayout(navegar)

        divisor = QSplitter(Qt.Orientation.Horizontal, self.conferencia)
        divisor.setChildrenCollapsible(False)
        self.img_original = self._quadro_de_imagem(divisor, "Imagem original")
        self.img_recorte = self._quadro_de_imagem(divisor, "Recorte que vai para o dataset")

        grupo = QGroupBox("Posição (clique e arraste para corrigir)", divisor)
        coluna = QVBoxLayout(grupo)
        linha_tabuleiro = QHBoxLayout()
        self.tabuleiro = TabuleiroEditavel(grupo)
        self.tabuleiro.setMinimumSize(280, 280)
        self.tabuleiro.posicao_mudou.connect(self._tabuleiro_mudou)
        self.paleta = PaletaDePecas(grupo)
        self.paleta.pincel.connect(self.tabuleiro.definir_pincel)
        linha_tabuleiro.addWidget(self.tabuleiro, 1)
        linha_tabuleiro.addWidget(self.paleta, 0, Qt.AlignmentFlag.AlignTop)
        # A sobra de largura fica depois da paleta, e não entre ela e o tabuleiro (ver F9-C3 no
        # `painel_de_resultado`).
        linha_tabuleiro.addStretch(0)
        coluna.addLayout(linha_tabuleiro, 1)
        linha_fen = QHBoxLayout()
        self.campo_fen = QLineEdit(grupo)
        self.campo_fen.setFont(tema.fonte_atual(tipografia.DADO))
        self.campo_fen.setAccessibleName("FEN da posição")
        self.campo_fen.returnPressed.connect(self._fen_digitada)
        self.combo_lado = QComboBox(grupo)
        for _chave, rotulo in LADOS:
            self.combo_lado.addItem(rotulo)
        linha_fen.addWidget(self.campo_fen, 1)
        linha_fen.addWidget(self.combo_lado)
        coluna.addLayout(linha_fen)
        self.lbl_leituras = QLabel("", grupo)
        self.lbl_leituras.setWordWrap(True)
        self.lbl_leituras.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        coluna.addWidget(self.lbl_leituras)
        trocar = QHBoxLayout()
        self.btn_fonte = self._botao("Usar a FEN do relatório", self.usar_fonte, estilos.NEUTRO)
        self.btn_modelo = self._botao("Usar a leitura do modelo", self.usar_modelo, estilos.NEUTRO)
        self.btn_recorte = self._botao("Usar a imagem inteira", self.trocar_recorte, estilos.NEUTRO)
        dica_em(
            self.btn_recorte,
            "Alterna entre o tabuleiro achado pelo detector e a imagem inteira como tabuleiro. "
            "Use quando o recorte do meio cortou casas ou pegou coordenadas.",
        )
        for botao in (self.btn_fonte, self.btn_modelo, self.btn_recorte):
            trocar.addWidget(botao)
        trocar.addStretch(1)
        coluna.addLayout(trocar)
        divisor.addWidget(grupo)
        divisor.setStretchFactor(2, 1)
        divisor.setSizes([LADO_DA_IMAGEM + 30, LADO_DA_IMAGEM + 30, 2 * LADO_DA_IMAGEM])
        dentro.addWidget(divisor, 1)

        self.lbl_item = QLabel("", self.conferencia)
        self.lbl_item.setWordWrap(True)
        self.lbl_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dentro.addWidget(self.lbl_item)

        acoes = QHBoxLayout()
        self.btn_salvar = self._botao("Salvar no dataset", self.salvar, estilos.PRIMARIO)
        self.btn_pular = self._botao("Pular", self.pular, estilos.NEUTRO)
        self.btn_descartar = self._botao("Descartar", self.descartar, estilos.NEUTRO)
        self.btn_reabrir = self._botao("Voltar a pendente", self.reabrir, estilos.NEUTRO)
        dica_em(self.btn_salvar, "Grava o recorte e a posição no labels.csv e vai para a próxima (Ctrl+S).")
        dica_em(self.btn_pular, "Deixa para depois e vai para a próxima (Ctrl+→). Fica no filtro Puladas.")
        dica_em(self.btn_descartar, "Não é um diagrama aproveitável: não volta a aparecer nas pendentes (Ctrl+D).")
        acoes.addStretch(1)
        for botao in (self.btn_reabrir, self.btn_descartar, self.btn_pular, self.btn_salvar):
            acoes.addWidget(botao)
        dentro.addLayout(acoes)
        fora.addWidget(self.conferencia, 1)

        for tecla, funcao in (
            ("Ctrl+S", self.salvar),
            ("Ctrl+Right", self.pular),
            ("Ctrl+Left", lambda: self.andar(-1)),
            ("Ctrl+D", self.descartar),
            ("PgDown", lambda: self.andar(1)),
            ("PgUp", lambda: self.andar(-1)),
        ):
            atalho = QShortcut(QKeySequence(tecla), self)
            atalho.activated.connect(funcao)

    def _botao(self, rotulo: str, funcao: Callable[[], object], papel: str) -> QPushButton:
        botao = QPushButton(rotulo, self)
        botao.setAutoDefault(False)
        botao.clicked.connect(lambda _marcado=False: funcao())
        tema.aplicar_papel(botao, papel)
        return botao

    def _quadro_de_imagem(self, divisor: QSplitter, titulo: str) -> QLabel:
        grupo = QGroupBox(titulo, divisor)
        caixa = QVBoxLayout(grupo)
        rotulo = QLabel(grupo)
        rotulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rotulo.setMinimumSize(LADO_DA_IMAGEM, LADO_DA_IMAGEM)
        caixa.addWidget(rotulo, 1)
        divisor.addWidget(grupo)
        return rotulo

    # --------------------------------------------------------------------------------- pasta

    def origem(self) -> str:
        return ORIGENS[self.combo_origem.currentIndex()][0]

    def _origem_mudou(self) -> None:
        ultima = self._ultimas_pastas().get(self.origem(), "")
        if ultima:
            self.campo_pasta.setText(ultima)
        self._habilitar()

    def escolher_pasta(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Pasta das imagens", self.campo_pasta.text())
        if pasta:
            self.campo_pasta.setText(pasta)
            self.abrir_pasta()

    def abrir_pasta(self, pasta: Path | str | None = None) -> bool:
        if self._rodando_lote is not None:
            return False
        texto = str(pasta) if pasta is not None else self.campo_pasta.text().strip()
        if not texto:
            return False
        try:
            lote, arquivo = imp.abrir_lote(texto, self.origem(), diretorio=self._diretorio)
        except (OSError, ValueError) as exc:
            self.lbl_aviso.setText(str(exc))
            return False
        self.lbl_aviso.clear()
        self.campo_pasta.setText(texto)
        self.lote, self._arquivo_do_lote = lote, arquivo
        self._lembrar_pasta(texto)
        self._gravar_andamento()
        # Abre no filtro que tem trabalho: com aviso quando há, senão todas as pendentes.
        filtro = "aviso" if imp.posicoes(lote, "aviso") else "pendentes"
        self.combo_filtro.blockSignals(True)
        self.combo_filtro.setCurrentIndex([chave for chave, _ in FILTROS].index(filtro))
        self.combo_filtro.blockSignals(False)
        self._refazer_fila(manter=None)
        self._mostrar_item()
        return True

    def _ultimas_pastas(self) -> dict[str, str]:
        try:
            dados = json.loads((self._diretorio / ARQUIVO_DAS_PASTAS).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(k): str(v) for k, v in dados.items()} if isinstance(dados, dict) else {}

    def _lembrar_pasta(self, pasta: str) -> None:
        dados = self._ultimas_pastas()
        dados[self.origem()] = pasta
        try:
            from chess_diagram_ocr.atomic_io import atomic_write_json

            atomic_write_json(self._diretorio / ARQUIVO_DAS_PASTAS, dados)
        except OSError as exc:
            logger.warning("Não deu para lembrar a pasta da importação: %s", exc)

    def _gravar_andamento(self) -> None:
        if self.lote is not None and self._arquivo_do_lote is not None:
            self.lote.salvar(self._arquivo_do_lote)

    # ------------------------------------------------------------------------------ fila

    def filtro(self) -> str:
        return FILTROS[self.combo_filtro.currentIndex()][0]

    def _filtro_mudou(self) -> None:
        self._refazer_fila(manter=self.posicao_atual())
        self._mostrar_item()

    def _refazer_fila(self, *, manter: int | None) -> None:
        """Recalcula as posições do filtro e fica no mesmo item, ou no que veio depois dele."""
        self._fila = imp.posicoes(self.lote, self.filtro()) if self.lote is not None else []
        if manter is None:
            self._i = 0
            return
        self._i = next((i for i, posicao in enumerate(self._fila) if posicao >= manter), len(self._fila))
        self._i = min(self._i, max(0, len(self._fila) - 1))

    def posicao_atual(self) -> int | None:
        if not self._fila or not 0 <= self._i < len(self._fila):
            return None
        return self._fila[self._i]

    def item_atual(self) -> imp.ItemDeImportacao | None:
        posicao = self.posicao_atual()
        return self.lote.itens[posicao] if self.lote is not None and posicao is not None else None

    def andar(self, passo: int) -> None:
        if not self._fila or self._rodando_lote is not None:
            return
        novo = max(0, min(len(self._fila) - 1, self._i + passo))
        if novo != self._i:
            self._i = novo
            self._mostrar_item()

    # ---------------------------------------------------------------------------- item

    def _mostrar_item(self) -> None:
        self._recorte_atual = None
        self._recorte_usado = ""
        item = self.item_atual()
        self._atualizar_resumo()
        if item is None or self.lote is None:
            self.img_original.clear()
            self.img_recorte.clear()
            self.tabuleiro.mostrar(imp.TABULEIRO_VAZIO)
            self.campo_fen.clear()
            self.lbl_leituras.clear()
            self.lbl_item.setText("Nada para conferir neste filtro." if self.lote is not None else "")
            self.lbl_posicao.clear()
            self._habilitar()
            return
        self.lbl_posicao.setText(f"{self._i + 1} de {len(self._fila)}")
        caminho = self.lote.caminho_da_imagem(item)
        pixmap = QPixmap(str(caminho))
        self.img_original.setPixmap(
            pixmap.scaled(LADO_DA_IMAGEM, LADO_DA_IMAGEM, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            if not pixmap.isNull() else QPixmap()
        )
        self.img_recorte.setText("Recortando…")
        proposta = item.fen_da_fonte or item.fen_do_modelo or imp.TABULEIRO_VAZIO
        self._mostrar_posicao(imp.campo_de_pecas(proposta))
        lado = item.lado or "w"
        self.combo_lado.setCurrentIndex(0 if lado == "w" else 1)
        detalhes = [f"{item.livro} · imagem {item.indice}", item.imagem]
        if item.legenda:
            detalhes.append(item.legenda)
        if item.status != imp.PENDENTE:
            detalhes.append(f"Situação: {item.status}" + (f" ({item.amostra})" if item.amostra else ""))
        if item.motivos:
            detalhes.append("Aviso: " + "; ".join(item.motivos))
        self.lbl_item.setText("\n".join(detalhes))
        self._descrever_leituras()
        self._habilitar()
        self._ler(self.posicao_atual(), item.recorte)  # type: ignore[arg-type]

    def _mostrar_posicao(self, campo: str) -> None:
        self.tabuleiro.mostrar(campo)
        self._tabuleiro_mudou(campo)

    def _tabuleiro_mudou(self, campo: str) -> None:
        lado = LADOS[self.combo_lado.currentIndex()][0]
        self.campo_fen.setText(f"{campo} {lado} - - 0 1")
        item = self.item_atual()
        if item is not None and item.fen_do_modelo:
            self.tabuleiro.definir_casas_problematicas(imp.casas_diferentes(campo, item.fen_do_modelo))

    def _fen_digitada(self) -> None:
        texto = self.campo_fen.text().strip()
        if not is_syntactically_valid_fen(texto):
            self.lbl_aviso.setText(f"FEN inválida: {texto}")
            return
        self.lbl_aviso.clear()
        partes = texto.split()
        if len(partes) > 1 and partes[1] in ("w", "b"):
            self.combo_lado.setCurrentIndex(0 if partes[1] == "w" else 1)
        self._mostrar_posicao(partes[0])

    def _descrever_leituras(self) -> None:
        item = self.item_atual()
        if item is None:
            self.lbl_leituras.clear()
            return
        linhas = []
        if item.fen_da_fonte:
            linhas.append(f"Relatório: {imp.campo_de_pecas(item.fen_da_fonte)}")
        if item.fen_do_modelo:
            linha = f"Modelo: {item.fen_do_modelo}"
            if item.fen_da_fonte:
                diferentes = len(imp.casas_diferentes(item.fen_da_fonte, item.fen_do_modelo))
                linha += " (igual ao relatório)" if not diferentes else f" ({diferentes} casas diferentes, em vermelho)"
            linhas.append(linha)
        else:
            linhas.append("Modelo: lendo…")
        self.lbl_leituras.setText("\n".join(linhas))

    def _ler(self, posicao: int, recorte: str) -> None:
        """Recorta e lê o item numa thread. A resposta só vale se ainda for o item na tela."""
        if self.lote is None:
            return
        caminho = self.lote.caminho_da_imagem(self.lote.itens[posicao])
        leitor = self._leitor_efetivo()

        def trabalho() -> None:
            try:
                tabuleiro, usado = imp.recortar(imp.ler_imagem(caminho), recorte)
                lida = leitor(tabuleiro)
            except Exception as exc:  # noqa: BLE001 - qualquer falha vira aviso na tela, não queda
                logger.exception("Leitura da importação falhou em %s", caminho)
                _emitir(self, "_leitura_falhou", posicao, str(exc))
                return
            _emitir(self, "_leitura_pronta", posicao, tabuleiro, usado, lida)

        self._leitura = threading.Thread(target=trabalho, name="importacao-leitura", daemon=True)
        self._leitura.start()

    def _leitor_efetivo(self) -> Callable[[np.ndarray], str]:
        if self._leitor is None:
            self._servico = OcrService(model_path=self._modelo())
            self._leitor = _ler_com_modelo(self._servico)
        return self._leitor

    def _chegou_leitura(self, posicao: int, tabuleiro: object, usado: str, lida: str) -> None:
        if self.lote is None or posicao != self.posicao_atual():
            return
        self._recorte_atual = tabuleiro  # type: ignore[assignment]
        self._recorte_usado = usado
        self.img_recorte.setPixmap(
            pixmap_de_rgb(tabuleiro).scaled(  # type: ignore[arg-type]
                LADO_DA_IMAGEM, LADO_DA_IMAGEM, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.btn_recorte.setText(
            "Usar a imagem inteira" if usado == imp.RECORTE_DETECTADO else "Usar o tabuleiro detectado"
        )
        anterior = self.lote.itens[posicao]
        self.lote.itens[posicao] = replace(anterior, fen_do_modelo=lida, recorte=usado)
        if not anterior.fen_da_fonte and self.tabuleiro.posicao() == imp.campo_de_pecas(
            anterior.fen_do_modelo or imp.TABULEIRO_VAZIO
        ):
            # Sem FEN da fonte a proposta é a leitura -- desde que a pessoa não tenha mexido ainda.
            self._mostrar_posicao(lida)
        else:
            self._tabuleiro_mudou(self.tabuleiro.posicao())
        self._descrever_leituras()
        self._habilitar()

    def _falhou_leitura(self, posicao: int, mensagem: str) -> None:
        if posicao != self.posicao_atual():
            return
        self.img_recorte.setText(f"Não deu para recortar:\n{mensagem}")
        self.lbl_leituras.setText("Modelo: sem leitura")
        self._habilitar()

    def usar_fonte(self) -> None:
        item = self.item_atual()
        if item is not None and item.fen_da_fonte:
            self._mostrar_posicao(imp.campo_de_pecas(item.fen_da_fonte))

    def usar_modelo(self) -> None:
        item = self.item_atual()
        if item is not None and item.fen_do_modelo:
            self._mostrar_posicao(item.fen_do_modelo)

    def trocar_recorte(self) -> None:
        posicao = self.posicao_atual()
        if posicao is None or self.lote is None or not self._recorte_usado:
            return
        outro = imp.RECORTE_INTEIRA if self._recorte_usado == imp.RECORTE_DETECTADO else imp.RECORTE_DETECTADO
        self.lote.itens[posicao] = replace(self.lote.itens[posicao], recorte=outro, fen_do_modelo="")
        self._recorte_atual = None
        self._recorte_usado = ""
        self.img_recorte.setText("Recortando…")
        self._descrever_leituras()
        self._habilitar()
        self._ler(posicao, outro)

    # ---------------------------------------------------------------------------- ações

    def salvar(self) -> bool:
        posicao, item = self.posicao_atual(), self.item_atual()
        if (
            posicao is None or item is None or self.lote is None or self._recorte_atual is None
            or item.status == imp.SALVO or self._rodando_lote is not None
        ):
            return False
        lado = LADOS[self.combo_lado.currentIndex()][0]
        fen = f"{self.tabuleiro.posicao()} {lado} - - 0 1"
        permitir = False
        pergunta = illegal_save_question(fen)
        if pergunta is not None:
            resposta = QMessageBox.question(self, "Posição ilegal", pergunta)
            if resposta != QMessageBox.StandardButton.Yes:
                return False
            permitir = True
        csv_path, samples_dir, _splits = self._caminhos()
        try:
            imp.gravar_item(
                self.lote,
                posicao,
                self._recorte_atual,
                fen,
                lado=lado,
                recorte=self._recorte_usado,
                csv_path=csv_path,
                samples_dir=samples_dir,
                corrected_by=imp.rota_da_conferencia(item, fen),
                allow_illegal=permitir,
                diretorio=self._diretorio,
            )
        except (OSError, ValueError) as exc:
            self.lbl_aviso.setText(f"Não foi gravada: {exc}")
            return False
        self.lbl_aviso.clear()
        self._gravar_andamento()
        self.amostras_gravadas.emit(1)
        self._seguir(posicao)
        return True

    def pular(self) -> None:
        self._marcar(imp.PULADO)

    def descartar(self) -> None:
        self._marcar(imp.DESCARTADO)

    def reabrir(self) -> None:
        self._marcar(imp.PENDENTE)

    def _marcar(self, status: str) -> None:
        posicao, item = self.posicao_atual(), self.item_atual()
        if posicao is None or item is None or self.lote is None or self._rodando_lote is not None:
            return
        if item.status == imp.SALVO:
            return
        imp.marcar(self.lote, posicao, status)
        self._gravar_andamento()
        self._seguir(posicao)

    def _seguir(self, posicao: int) -> None:
        """Depois de resolver um item: o próximo do filtro (o resolvido pode ter saído dele)."""
        if self.filtro() == "todas":
            self._refazer_fila(manter=posicao + 1)
        else:
            self._refazer_fila(manter=posicao)
        self._mostrar_item()

    # ------------------------------------------------------------------------------ lote

    def importar_confirmados(self) -> bool:
        if self.lote is None or self.lote.origem != imp.COM_FEN or self._rodando_lote is not None:
            return False
        csv_path, samples_dir, _splits = self._caminhos()
        lote = self.lote
        leitor = self._leitor_efetivo()
        self._cancelar_lote = False

        def trabalho() -> None:
            try:
                conta = imp.importar_os_que_concordam(
                    lote,
                    ler=leitor,
                    csv_path=csv_path,
                    samples_dir=samples_dir,
                    corrected_by=imp.IMPORTADO_COM_FEN,
                    progresso=lambda feitos, total, salvos: _emitir(self, "_lote_andou", feitos, total, salvos),
                    cancelar=lambda: self._cancelar_lote,
                    gravar_andamento=self._gravar_andamento,
                    diretorio=self._diretorio,
                )
                _emitir(self, "_lote_acabou", conta)
            except Exception as exc:  # noqa: BLE001 - a falha chega à tela, e o andamento fica gravado
                logger.exception("Importação em lote falhou")
                self._gravar_andamento()
                _emitir(self, "_lote_acabou", exc)

        if self._busy is not None:
            self._ficha = self._busy.register(
                "importação de imagens",
                loses_work=False,
                cancellable=True,
                cancel=self.cancelar_lote,
                detail=Path(lote.pasta).name,
                total=len(imp.posicoes(lote, "pendentes")),
            )
        self._rodando_lote = threading.Thread(target=trabalho, name="importacao-lote", daemon=True)
        self.barra.setVisible(True)
        self.barra.setRange(0, 0)
        self.btn_cancelar.setVisible(True)
        self.btn_lote.setVisible(False)
        self._habilitar()
        self._rodando_lote.start()
        return True

    def cancelar_lote(self) -> None:
        self._cancelar_lote = True
        self.btn_cancelar.setEnabled(False)

    def _andou_lote(self, feitos: int, total: int, salvos: int) -> None:
        self.barra.setRange(0, max(1, total))
        self.barra.setValue(feitos)
        self.lbl_resumo.setText(f"Lendo {feitos} de {total} -- {salvos} gravadas no dataset até agora.")
        if self._ficha is not None:
            self._ficha.update(f"{salvos} gravadas", feito=feitos, total=total)

    def _acabou_lote(self, resultado: object) -> None:
        thread, self._rodando_lote = self._rodando_lote, None
        if thread is not None:
            thread.join(timeout=5)
        self._soltar_ficha()
        self.barra.setVisible(False)
        self.btn_cancelar.setVisible(False)
        self.btn_cancelar.setEnabled(True)
        self.btn_lote.setVisible(True)
        if isinstance(resultado, Exception):
            self.lbl_aviso.setText(f"A importação parou: {resultado}")
            salvos = 0
        else:
            conta = resultado
            salvos = int(conta["salvos"])  # type: ignore[index]
            self.ultimo_resultado = conta
        if salvos:
            self.amostras_gravadas.emit(salvos)
        self.combo_filtro.setCurrentIndex(0)
        self._refazer_fila(manter=None)
        self._mostrar_item()

    def _soltar_ficha(self) -> None:
        ficha, self._ficha = self._ficha, None
        if ficha is not None:
            ficha.release()

    # ---------------------------------------------------------------------------- estado

    def _atualizar_resumo(self) -> None:
        if self._rodando_lote is not None:
            return
        self.lbl_resumo.setText(self.lote.resumo() if self.lote is not None else "Nenhuma pasta aberta.")

    def _habilitar(self) -> None:
        livre = self._rodando_lote is None
        item = self.item_atual()
        tem_item = item is not None and livre
        pendente_ou_pulado = tem_item and item.status in (imp.PENDENTE, imp.PULADO)  # type: ignore[union-attr]
        self.combo_origem.setEnabled(livre)
        self.campo_pasta.setEnabled(livre)
        self.btn_abrir.setEnabled(livre)
        self.btn_lote.setEnabled(
            livre and self.lote is not None and self.lote.origem == imp.COM_FEN
            and bool(imp.posicoes(self.lote, "pendentes"))
        )
        self.btn_lote.setVisible(livre and self.origem() == imp.COM_FEN)
        self.combo_filtro.setEnabled(livre)
        self.btn_anterior.setEnabled(tem_item and self._i > 0)
        self.btn_proxima.setEnabled(tem_item and self._i < len(self._fila) - 1)
        self.btn_salvar.setEnabled(bool(pendente_ou_pulado) and self._recorte_atual is not None)
        self.btn_pular.setEnabled(bool(tem_item) and item.status == imp.PENDENTE)  # type: ignore[union-attr]
        self.btn_descartar.setEnabled(bool(pendente_ou_pulado))
        self.btn_reabrir.setEnabled(bool(tem_item) and item.status in (imp.PULADO, imp.DESCARTADO))  # type: ignore[union-attr]
        self.btn_fonte.setEnabled(bool(tem_item) and bool(item.fen_da_fonte))  # type: ignore[union-attr]
        self.btn_fonte.setVisible(self.lote is None or self.lote.origem == imp.COM_FEN)
        self.btn_modelo.setEnabled(bool(tem_item) and bool(item.fen_do_modelo))  # type: ignore[union-attr]
        self.btn_recorte.setEnabled(bool(tem_item) and bool(self._recorte_usado))
        self.tabuleiro.setEnabled(bool(tem_item))
        self.paleta.habilitar(bool(tem_item))

    def aguardar(self, ms: int = 30_000) -> None:
        """Espera as threads e entrega os sinais delas. Para os testes."""
        from PyQt6.QtCore import QCoreApplication

        for thread in (self._leitura, self._rodando_lote):
            if thread is not None:
                thread.join(timeout=ms / 1000)
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()

    def done(self, a0: int) -> None:
        """Fechar (botão da janela, Esc) para o lote e grava o andamento antes de sair.

        É aqui e não no `closeEvent` porque o Esc chega por `reject`, que não passa por ele.
        """
        if self._rodando_lote is not None:
            self._cancelar_lote = True
            self._rodando_lote.join(timeout=10)
            self._rodando_lote = None
            self._soltar_ficha()
        self._gravar_andamento()
        super().done(a0)
