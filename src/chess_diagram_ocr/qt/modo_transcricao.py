"""O modo transcrição da aba Texto: a folha do scan-ouro, linha a linha, às cegas (S-703).

**Ele toma o lugar do editor, e não conversa com ele.** O editor da aba mostra a leitura de um motor, e quem transcreve não pode vê-la: por
isso o editor some enquanto o modo está ligado, e o modo nunca pede o documento dele. Cada folha parte do vazio ou da camada de terceiro, e
`CadernoDaPassada.gravar` confere isso a cada gravação (S-762).

**Nada de caixa.** O que dá errado sai na frase de estado: exceção num slot do PyQt6 mata o processo, e caixa modal trava a suíte.
A pasta se escolhe por `escolher_pasta`, que o teste troca.

**Linha a linha com a faixa impressa ao lado** (S-643): a faixa é o recorte da imagem que os motores vão ler, e cada linha é um campo, em que
`Enter` leva à seguinte. Quando a geometria parte uma linha em duas faixas, digita-se o que cada faixa mostra: a ordem é a de leitura do produto.

**Toda a lógica é de `text/transcricao_scan.py`**; aqui só há widget.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.imagens import pixmap_de_rgb
from chess_diagram_ocr.text import dado_corrigido as _dado_corrigido
from chess_diagram_ocr.text import ouro as _ouro
from chess_diagram_ocr.text import procedencia as _procedencia
from chess_diagram_ocr.text import scan_ouro as _scan_ouro
from chess_diagram_ocr.text import transcricao_scan as _transcricao
from chess_diagram_ocr.ui import estilos, strings

logger = logging.getLogger(__name__)

FIGURINAS = "♔♕♖♗♘♙"
LARGURA_DA_FAIXA = 760
SEGUNDOS_ENTRE_GRAVACOES = 120
"""O rascunho vai ao disco sozinho a cada tanto: são horas de alguém, e a queda de luz não pergunta."""

_FALHAS_DE_GRAVACAO = (
    _dado_corrigido.FolhaAncorada,
    _procedencia.VerdadeContaminada,
    _transcricao.PastaNoRepositorio,
    _transcricao.SemBackup,
    ValueError,
    OSError,
)


def _escolher_pasta_de_verdade(pai: QWidget, titulo: str) -> str:
    return QFileDialog.getExistingDirectory(pai, titulo)


class LinhaDeTranscricao(QWidget):
    """Uma linha: a faixa impressa à esquerda e o campo à direita."""

    def __init__(self, recorte: np.ndarray | None, texto: str, parent: QWidget | None = None, *, fator: float = 1.0) -> None:
        super().__init__(parent)
        caixa = QHBoxLayout(self)
        caixa.setContentsMargins(0, 0, 0, 0)
        self.faixa = QLabel(self)
        self.faixa.setAccessibleName("Linha impressa")
        self.faixa.setMinimumWidth(LARGURA_DA_FAIXA)
        if recorte is not None and recorte.size:
            # **Um fator só por folha**: com um por linha, a linha curta sairia gigante, e a letra impressa é o que se compara.
            altura, largura = recorte.shape[:2]
            self.faixa.setPixmap(
                pixmap_de_rgb(np.ascontiguousarray(recorte)).scaled(
                    max(1, round(largura * fator)), max(1, round(altura * fator)),
                    Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.faixa.setFixedHeight(max(1, round(altura * fator)))
        caixa.addWidget(self.faixa)
        self.campo = QLineEdit(texto, self)
        self.campo.setAccessibleName("Linha digitada")
        caixa.addWidget(self.campo, 1)


class ModoTranscricao(QWidget):
    fechar_pedido = pyqtSignal()
    pasta_mudou = pyqtSignal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        manifesto: _scan_ouro.ScanOuro | None = None,
        escolher_pasta: Callable[[QWidget, str], str] = _escolher_pasta_de_verdade,
        agora: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(parent)
        self.manifesto = manifesto if manifesto is not None else _scan_ouro.carregar()
        self._escolher_pasta = escolher_pasta
        self._agora = agora
        self.pasta: Path | None = None
        self.caderno: _transcricao.CadernoDaPassada | None = None
        self._achados: dict[str, Path] = {}
        self._pasta_dos_livros: Path | None = None
        self._folha: _scan_ouro.FolhaDoScanOuro | None = None
        self._aberta: _transcricao.FolhaAberta | None = None
        self._documento = _transcricao.documento_da_partida((), (), _transcricao.VAZIO, indice=0)
        self._partida = _transcricao.VAZIO
        self._relogio: _transcricao.Relogio | None = None
        self._parado_com = 0.0
        self._alterada = False
        self._completa = False
        self._tiques = 0
        self.linhas: list[LinhaDeTranscricao] = []
        self._montar()
        self._tique_do_relogio = QTimer(self)
        self._tique_do_relogio.setInterval(1000)
        self._tique_do_relogio.timeout.connect(self._tique)

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        caixa = QVBoxLayout(self)
        topo = QHBoxLayout()
        topo.addWidget(QLabel(strings.TRANSCRICAO_PASSADA, self))
        self.escolha_de_passada = QComboBox(self)
        self.escolha_de_passada.setAccessibleName(strings.TRANSCRICAO_PASSADA)
        for passada in _transcricao.PASSADAS:
            self.escolha_de_passada.addItem(str(passada), passada)
        self.escolha_de_passada.currentIndexChanged.connect(self._trocar_passada)
        topo.addWidget(self.escolha_de_passada)
        topo.addWidget(QLabel(strings.TRANSCRICAO_FOLHA, self))
        self.escolha_de_folha = QComboBox(self)
        self.escolha_de_folha.setAccessibleName(strings.TRANSCRICAO_FOLHA)
        self.escolha_de_folha.activated.connect(self._trocar_folha)
        topo.addWidget(self.escolha_de_folha, 1)
        topo.addWidget(QLabel(strings.TRANSCRICAO_PARTIDA, self))
        self.escolha_de_partida = QComboBox(self)
        self.escolha_de_partida.setAccessibleName(strings.TRANSCRICAO_PARTIDA)
        self.escolha_de_partida.activated.connect(self._trocar_partida)
        topo.addWidget(self.escolha_de_partida)
        self.botao_de_pasta = QPushButton(strings.TRANSCRICAO_ESCOLHER_PASTA, self)
        tema.aplicar_papel(self.botao_de_pasta, estilos.NEUTRO)
        self.botao_de_pasta.clicked.connect(self._pedir_pasta)
        topo.addWidget(self.botao_de_pasta)
        self.botao_de_backup = QPushButton(strings.TRANSCRICAO_ESCOLHER_BACKUP, self)
        tema.aplicar_papel(self.botao_de_backup, estilos.NEUTRO)
        self.botao_de_backup.clicked.connect(self._pedir_backup)
        topo.addWidget(self.botao_de_backup)
        self.botao_de_fechar = QPushButton(strings.TRANSCRICAO_FECHAR, self)
        tema.aplicar_papel(self.botao_de_fechar, estilos.NEUTRO)
        self.botao_de_fechar.clicked.connect(self.fechar_pedido)
        topo.addWidget(self.botao_de_fechar)
        caixa.addLayout(topo)
        self.frase = QLabel("", self)
        self.frase.setWordWrap(True)
        self.frase.setAccessibleName("Estado da transcrição")
        caixa.addWidget(self.frase)
        self.rolagem = QScrollArea(self)
        self.rolagem.setWidgetResizable(True)
        self.corpo = QWidget(self.rolagem)
        self.corpo_das_linhas = QVBoxLayout(self.corpo)
        self.corpo_das_linhas.addStretch(1)
        self.rolagem.setWidget(self.corpo)
        caixa.addWidget(self.rolagem, 1)
        base = QHBoxLayout()
        for figurina in FIGURINAS:
            botao = QPushButton(figurina, self)
            tema.aplicar_papel(botao, estilos.NEUTRO)
            botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            botao.setAccessibleName(f"Escrever a figurina {figurina}")
            botao.clicked.connect(lambda _marcado=False, f=figurina: self._escrever(f))
            base.addWidget(botao)
        self.botao_de_linha = QPushButton(strings.TRANSCRICAO_LINHA_A_MAIS, self)
        tema.aplicar_papel(self.botao_de_linha, estilos.NEUTRO)
        self.botao_de_linha.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.botao_de_linha.clicked.connect(self._linha_a_mais)
        base.addWidget(self.botao_de_linha)
        base.addStretch(1)
        self.mostrador = QLabel(_transcricao.relogio_por_extenso(0), self)
        self.mostrador.setAccessibleName("Tempo nesta folha")
        base.addWidget(self.mostrador)
        self.botao_de_concluir = QPushButton(strings.TRANSCRICAO_CONCLUIR, self)
        tema.aplicar_papel(self.botao_de_concluir, estilos.NEUTRO)
        self.botao_de_concluir.clicked.connect(self.concluir)
        base.addWidget(self.botao_de_concluir)
        caixa.addLayout(base)
        self.custo = QLabel("", self)
        self.custo.setAccessibleName("Custo medido da transcrição")
        caixa.addWidget(self.custo)
        self._encher_partidas()
        self._dizer(strings.TRANSCRICAO_ESCOLHA_A_PASTA)

    def _dizer(self, frase: str) -> None:
        self.frase.setText(frase)

    # ----------------------------------------------------------------------- o que vem de fora

    def definir_livro(self, pdf: Path | None) -> None:
        """O livro aberto na janela só diz em que pasta os PDF do acervo estão: as folhas vêm do manifesto, e não dele."""
        if pdf is None or Path(pdf).parent == self._pasta_dos_livros:
            return
        self._pasta_dos_livros = Path(pdf).parent
        self._achados = _ouro.localizar({livro.identidade for livro in self.manifesto.livros}, [self._pasta_dos_livros])
        self._encher_folhas()

    def definir_pasta(self, pasta: str | Path) -> bool:
        """A pasta da transcrição. Recusada a de dentro de um repositório, e a frase diz por quê."""
        if not str(pasta):
            return False
        try:
            self.caderno = _transcricao.CadernoDaPassada(pasta, self.passada)
        except _transcricao.PastaNoRepositorio as exc:
            self.caderno = None
            self.pasta = None
            self._dizer(str(exc))
            return False
        self.pasta = Path(pasta)
        self._encher_folhas()
        self._dizer_estado()
        return True

    def ativar(self) -> None:
        self._tique_do_relogio.start()
        if self._folha is not None:
            self._relogio = _transcricao.Relogio(self._agora(), inicial=self._parado_com)

    def desativar(self) -> bool:
        """O modo saiu de cena: o que estiver digitado vai ao disco, e o relógio para. `False` é o digitado que não foi: quem chama não apaga."""
        gravou = self.guardar()
        self._parado_com = self._segundos()
        self._tique_do_relogio.stop()
        return gravou

    # ------------------------------------------------------------------------------- a passada

    @property
    def passada(self) -> int:
        return int(self.escolha_de_passada.currentData() or _transcricao.PASSADAS[0])

    def _trocar_passada(self, _indice: int = 0) -> None:
        """**A troca fecha a folha da outra passada na tela**: o que estava digitado vai para o caderno dela, e os campos somem.

        Se não foi, a passada volta e os campos ficam: trocar apagaria o digitado.
        """
        if not self.guardar():
            self.escolha_de_passada.blockSignals(True)
            self.escolha_de_passada.setCurrentIndex(self.escolha_de_passada.findData(self.caderno.passada if self.caderno is not None else 1))
            self.escolha_de_passada.blockSignals(False)
            return
        self._limpar_linhas()
        self._folha = None
        self._aberta = None
        self._relogio = None
        if self.pasta is not None:
            self.caderno = _transcricao.CadernoDaPassada(self.pasta, self.passada)
        self._encher_partidas()
        self._encher_folhas()
        self._dizer_estado()

    def _encher_partidas(self) -> None:
        self.escolha_de_partida.clear()
        for partida in _transcricao.partidas_da_passada(self.passada):
            self.escolha_de_partida.addItem(strings.TRANSCRICAO_PARTIDAS[partida], partida)

    def _folhas_da_passada(self) -> list[_scan_ouro.FolhaDoScanOuro]:
        """A segunda passada só digita as folhas da dupla digitação."""
        folhas = self.manifesto.folhas
        return [f for f in folhas if f.dupla] if self.passada != _transcricao.PASSADAS[0] else list(folhas)

    def _encher_folhas(self) -> None:
        concluidas = self.caderno.concluidas() if self.caderno is not None else set()
        atual = self.escolha_de_folha.currentData()
        self.escolha_de_folha.clear()
        for f in self._folhas_da_passada():
            marca = " ✓" if (f.identidade, f.folha) in concluidas else ""
            falta = "" if f.identidade in self._achados else " (livro não achado)"
            dupla = " · dupla" if f.dupla else ""
            self.escolha_de_folha.addItem(f"{f.identidade[:8]} folha {f.folha} · {f.producao} · {f.conteudo} · {f.lingua}{dupla}{marca}{falta}", (f.identidade, f.folha))
        if atual is not None:
            self._selecionar_folha(atual)

    # ---------------------------------------------------------------------------------- a folha

    def _selecionar_folha(self, chave: tuple[str, int]) -> None:
        """Por laço, e não por `findData`: o Qt não compara tupla de Python guardada num item."""
        for k in range(self.escolha_de_folha.count()):
            if self.escolha_de_folha.itemData(k) == chave:
                self.escolha_de_folha.setCurrentIndex(k)
                return

    def _trocar_folha(self, indice: int) -> None:
        dados = self.escolha_de_folha.itemData(indice)
        if dados is not None and not self.abrir(*dados) and self._folha is not None:
            # A caixa não pode dizer uma folha com outra na tela.
            self._selecionar_folha((self._folha.identidade, self._folha.folha))

    def abrir(self, identidade: str, folha: int) -> bool:
        """Abre a folha **desta** passada: o que este caderno tem dela, ou a partida. O da outra passada não chega aqui."""
        alvo = next((f for f in self._folhas_da_passada() if (f.identidade, f.folha) == (identidade, folha)), None)
        if alvo is None:
            self._dizer(strings.TRANSCRICAO_FORA_DA_PASSADA)
            return False
        if self.caderno is None:
            self._dizer(strings.TRANSCRICAO_ESCOLHA_A_PASTA)
            return False
        pdf = self._achados.get(identidade)
        if pdf is None:
            self._dizer(strings.TRANSCRICAO_LIVRO_NAO_ACHADO)
            return False
        if not self.guardar():
            # **O digitado fica na tela, e a frase da recusa fica de pé**: seguir apagaria os campos, e a frase seguinte diria que está tudo em dia.
            return False
        try:
            aberta = _transcricao.abrir_folha(pdf, folha - 1)
        except (OSError, RuntimeError, ValueError, IndexError) as exc:
            logger.exception("A folha %s de %s não abriu.", folha, identidade)
            self._dizer(f"A folha {folha} não abriu: {exc}")
            return False
        if aberta.sha_folha != alvo.sha_folha:
            self._dizer(strings.TRANSCRICAO_OUTRA_COPIA)
            return False
        self._folha = alvo
        self._aberta = aberta
        guardada = self.caderno.ler(identidade, folha)
        self._partida = guardada.partida if guardada is not None else str(self.escolha_de_partida.currentData())
        textos = list(guardada.linhas) if guardada is not None else self._textos_da_partida(self._partida)
        self._documento = _transcricao.documento_da_partida(
            self._textos_da_partida(self._partida), aberta.caixas, self._partida, indice=folha - 1,
        )
        self._completa = guardada.completa if guardada is not None else False
        self._relogio = _transcricao.Relogio(self._agora(), inicial=guardada.segundos if guardada is not None else 0.0)
        self._desenhar_linhas(textos)
        self.escolha_de_partida.setEnabled(guardada is None)
        self._alterada = False
        self._dizer_estado()
        return True

    def _textos_da_partida(self, partida: str) -> list[str]:
        assert self._aberta is not None
        if partida == _transcricao.CAMADA:
            return list(self._aberta.textos_da_camada)
        return [""] * len(self._aberta.caixas)

    def _trocar_partida(self, _indice: int = 0) -> None:
        """A partida só muda enquanto a folha está intocada: depois disso, trocar apagaria digitação."""
        if self._folha is None or self._alterada or self.caderno is None or self.caderno.ler(self._folha.identidade, self._folha.folha) is not None:
            return
        self.abrir(self._folha.identidade, self._folha.folha)

    def _limpar_linhas(self) -> None:
        for linha in self.linhas:
            self.corpo_das_linhas.removeWidget(linha)
            linha.hide()
            linha.deleteLater()
        self.linhas = []

    def _acrescentar_linha(self, recorte: np.ndarray | None, texto: str, posicao: int | None = None, *, fator: float = 1.0) -> LinhaDeTranscricao:
        linha = LinhaDeTranscricao(recorte, texto, self.corpo, fator=fator)
        linha.campo.textEdited.connect(self._editou)
        linha.campo.returnPressed.connect(self._ir_para_a_seguinte)
        indice = len(self.linhas) if posicao is None else posicao
        self.linhas.insert(indice, linha)
        self.corpo_das_linhas.insertWidget(indice, linha)
        return linha

    def _desenhar_linhas(self, textos: list[str]) -> None:
        assert self._aberta is not None
        self._limpar_linhas()
        caixas = self._aberta.caixas
        mais_larga = max((x1 - x0 for x0, _y0, x1, _y1 in caixas), default=1.0)
        fator = min(1.0, LARGURA_DA_FAIXA / max(1.0, mais_larga + 2 * _transcricao.FOLGA_DA_FAIXA))
        for k in range(max(len(caixas), len(textos))):
            recorte = _transcricao.recorte_da_linha(self._aberta.imagem, caixas[k]) if k < len(caixas) else None
            self._acrescentar_linha(recorte, textos[k] if k < len(textos) else "", fator=fator)

    def _editou(self, _texto: str = "") -> None:
        self._alterada = True
        self.escolha_de_partida.setEnabled(False)
        if self._relogio is not None:
            self._relogio.atividade(self._agora())

    def _campo_atual(self) -> QLineEdit | None:
        foco = QApplication.focusWidget()
        return foco if isinstance(foco, QLineEdit) and any(linha.campo is foco for linha in self.linhas) else None

    def _ir_para_a_seguinte(self) -> None:
        atual = self._campo_atual()
        for k, linha in enumerate(self.linhas):
            if linha.campo is atual and k + 1 < len(self.linhas):
                self.linhas[k + 1].campo.setFocus()
                self.rolagem.ensureWidgetVisible(self.linhas[k + 1])
                return

    def _escrever(self, figurina: str) -> None:
        campo = self._campo_atual()
        if campo is not None:
            campo.insert(figurina)
            self._editou()

    def _linha_a_mais(self) -> None:
        """A linha que a geometria não achou. Sem faixa, logo abaixo do campo com o cursor."""
        if self._folha is None:
            return
        atual = self._campo_atual()
        posicao = next((k + 1 for k, linha in enumerate(self.linhas) if linha.campo is atual), len(self.linhas))
        self._acrescentar_linha(None, "", posicao).campo.setFocus()
        self._editou()

    # ---------------------------------------------------------------------------------- gravar

    def _segundos(self) -> float:
        return self._relogio.segundos(self._agora()) if self._relogio is not None else 0.0

    def _registro(self, *, completa: bool, passada: int) -> _transcricao.FolhaDaPassada:
        """`passada` é a do caderno, e não a da caixa: na troca, o que estava digitado é da passada que sai."""
        assert self._folha is not None and self._aberta is not None
        return _transcricao.FolhaDaPassada(
            identidade=self._folha.identidade,
            folha=self._folha.folha,
            passada=passada,
            procedencia=_procedencia.transcricao(passada),
            linhas=tuple(linha.campo.text() for linha in self.linhas),
            partida=self._partida,
            sha_imagem=self._aberta.sha_imagem,
            sha_folha=self._aberta.sha_folha,
            dpi=_transcricao.DPI,
            segundos=self._segundos(),
            completa=completa,
            gravado_em=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _gravar(self, *, completa: bool) -> bool:
        if self.caderno is None or self._folha is None or self._aberta is None:
            self._dizer(strings.TRANSCRICAO_ESCOLHA_A_PASTA)
            return False
        try:
            backup_em_dia = self.caderno.gravar(self._registro(completa=completa, passada=self.caderno.passada), self._documento)
        except _FALHAS_DE_GRAVACAO as exc:
            # **Não levanta**: exceção em slot do PyQt6 mata o processo, e aqui ela é a recusa que precisa ser lida.
            self._dizer(strings.TRANSCRICAO_NAO_GRAVOU.format(motivo=exc))
            return False
        self._alterada = False
        self._completa = completa
        self._dizer_estado(strings.TRANSCRICAO_BACKUP_FALHOU if not backup_em_dia else "")
        return True

    def guardar(self) -> bool:
        """O rascunho vai ao disco, se há o que levar. Sem marcar a folha como concluída, a menos que ela já estivesse."""
        if not self._alterada or self._folha is None:
            return True
        return self._gravar(completa=self._completa)

    def concluir(self, _marcado: bool = False) -> None:
        """A pessoa disse que a folha terminou: é só assim que ela mede, conta no acordo e estima o custo."""
        if not any(linha.campo.text().strip() for linha in self.linhas):
            self._dizer(strings.TRANSCRICAO_FOLHA_VAZIA)
            return
        if self._gravar(completa=True):
            self._encher_folhas()

    def _tique(self) -> None:
        self.mostrador.setText(_transcricao.relogio_por_extenso(self._segundos()))
        self._tiques += 1
        if self._tiques % SEGUNDOS_ENTRE_GRAVACOES == 0:
            self.guardar()

    # ---------------------------------------------------------------------------------- pastas

    def _pedir_pasta(self, _marcado: bool = False) -> None:
        escolhida = self._escolher_pasta(self, strings.TRANSCRICAO_ESCOLHER_PASTA)
        if escolhida and self.definir_pasta(escolhida):
            self.pasta_mudou.emit(str(self.pasta))

    def _pedir_backup(self, _marcado: bool = False) -> None:
        if self.pasta is None:
            self._dizer(strings.TRANSCRICAO_ESCOLHA_A_PASTA)
            return
        escolhida = self._escolher_pasta(self, strings.TRANSCRICAO_ESCOLHER_BACKUP)
        if not escolhida:
            return
        try:
            _transcricao.declarar_backup(self.pasta, escolhida)
        except _FALHAS_DE_GRAVACAO as exc:
            self._dizer(str(exc))
            return
        self._dizer_estado()

    def _dizer_estado(self, extra: str = "") -> None:
        partes = []
        if self.pasta is None:
            partes.append(strings.TRANSCRICAO_ESCOLHA_A_PASTA)
        else:
            estado = _transcricao.estado_do_backup(self.pasta)
            partes.append(strings.TRANSCRICAO_ESTADO.format(passada=self.passada, pasta=self.pasta, backup=strings.TRANSCRICAO_BACKUPS[estado]))
            ilegiveis = _transcricao.linhas_ilegiveis(self.pasta, self.passada)
            if ilegiveis:
                partes.append(strings.TRANSCRICAO_LINHAS_ILEGIVEIS.format(quantas=ilegiveis))
            self._mostrar_custo()
        if not self._achados:
            partes.append(strings.TRANSCRICAO_ABRA_UM_LIVRO)
        if extra:
            partes.append(extra)
        self._dizer(" ".join(partes))

    def _mostrar_custo(self) -> None:
        """Só o tempo desta passada: o texto da outra não vem junto, e a segunda digitação continua às cegas."""
        if self.caderno is None:
            return
        registros = [r for r in self.caderno.registros_concluidos() if r.completa]
        duplas = sum(f.dupla for f in self.manifesto.folhas)
        self.custo.setText(_transcricao.custo_por_extenso(_transcricao.custo(registros, folhas=len(self.manifesto.folhas), duplas=duplas)))


__all__ = ["ModoTranscricao"]
