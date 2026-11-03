"""As preferências: o que a janela monta a partir delas, quem as edita e o motor que as segue (S-523/S-536).

**O defeito que isto conserta.** `qt/janela.py` não importava `settings.py` para nada além do OCR
de glifos. `PainelDeEstudo` aceita `analyzer` desde o porte e a janela nunca passava um -- e
`None` **esconde a seção inteira** (S-33), então uma máquina *com* Stockfish mostrava exatamente
o que uma máquina sem ele mostraria. E o `OcrService` nascia sem `caption_reader`, embora
`service.py` diga por escrito que *quem lê a configuração é a interface* (S-43): a perda pesa nos
livros sem camada de texto, onde a legenda é a única pista do número do lance. Do lado do Tk as
duas ligações existiam (`_build_analyzer`, e o serviço construído com `caption_reader_from_settings`);
o corte as levou sem que nada acusasse -- o padrão da S-500 a S-512, mais duas vezes.

**Por que fora de `qt/janela.py`.** As duas funções não precisam de widget nenhum: são a leitura
de `data/settings.json` virando os dois objetos que o pipeline e a sala recebem prontos, e por
isso são afirmáveis sem `QApplication`. E a janela está na catraca da S-136; o que só ela pode
fazer é ligar um painel ao outro, não construir o que os painéis recebem.

---

**A S-536 acrescentou as outras duas metades da mesma pergunta: quem edita, e quem aplica.**

`DialogoDoMotor` é o formulário -- caminho do binário, `Hash`, `Threads`, `MultiPV`, tempo por
posição e a pasta de tablebases da S-538 --, com os tetos vindos **desta** máquina e a validação em
pt-BR. Ele não decide nada: os limites, as frases e o que é válido são de `ui/motor_declarado.py`.

`MotorVivo` é quem aplica **sem reiniciar o programa**, e é onde mora a única sutileza de mecanismo
do item. Trocar `Hash` num motor aberto é `setoption`; trocar o binário é derrubar um processo e
subir outro -- e as duas coisas podem levar segundos, porque o `close()` de um motor que está
pensando espera ele responder. As duas rodam numa `Tarefa` de `qt/trabalho.py`: a janela continua
desenhando enquanto o motor troca, que é o critério de aceite da S-536.

**O motor é o mesmo objeto antes e depois de trocar de binário**, e isso não é economia: a janela
guarda uma referência a ele e é ela quem o fecha no `closeEvent`. Se a troca criasse outro
`EngineAnalyzer`, o processo novo ficaria vivo depois de a janela fechar -- é para isso que existe
`EngineAnalyzer.trocar_binario`. O único caso em que nasce objeto novo é o da máquina que abriu
**sem** motor nenhum, e ali a sala passa a ser a dona dele (ver `PainelDeEstudo.analisador`).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.config import DEFAULT_MODEL_PATH
from chess_diagram_ocr.engine import EngineAnalyzer, find_engine
from chess_diagram_ocr.ocr_caption import caption_reader_from_settings
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.service import OcrService
from chess_diagram_ocr.settings import EngineSettings, Settings
from chess_diagram_ocr.ui import espaco, estilos, motor_declarado, tokens

logger = logging.getLogger(__name__)

__all__ = [
    "DialogoDoMotor",
    "MotorVivo",
    "memoria_da_maquina_mb",
    "motor_das_preferencias",
    "nucleos_da_maquina",
    "servico_das_preferencias",
]


def servico_das_preferencias(preferencias: Settings) -> OcrService:
    """O serviço do produto, com o OCR de legenda que as preferências autorizam (S-43/S-523).

    A configuração vem antes do serviço porque o OCR de legenda entra por ele. Construir o leitor
    aqui, e não dentro do serviço, é a separação da S-32: quem lê a configuração é a interface, e o
    pipeline recebe pronto o que ela autorizou. `None` -- OCR desligado, ou sem o extra instalado --
    é o pipeline de sempre.
    """
    return OcrService(
        model_path=DEFAULT_MODEL_PATH,
        caption_reader=caption_reader_from_settings(preferencias.ocr),
    )


def motor_das_preferencias(
    preferencias: Settings, *, env: dict[str, str] | None = None
) -> EngineAnalyzer | None:
    """Procura o motor. Não achar é o caso normal, e não é erro (S-33).

    O caminho das preferências vem primeiro, e **só ele** alcança um binário fora do `PATH` e dos
    diretórios conhecidos -- `find_engine()` sem argumento devolve `None` numa máquina em que o
    Stockfish mora numa pasta própria. `env` é o de `find_engine`, e existe para o teste não
    depender do `PATH` de quem o roda.

    O processo **não** é aberto aqui: `EngineAnalyzer` só o abre na primeira análise, e quem o fecha
    é a janela, no `closeEvent` -- um motor é um processo, não um widget, e sem `close()` cada
    abertura do programa deixaria um `stockfish.exe` vivo.
    """
    caminho = find_engine(preferencias.engine.path or None, env=env)
    if caminho is None:
        logger.info("Nenhum motor de análise encontrado; a seção de avaliação fica oculta.")
        return None
    logger.info("Motor de análise disponível: %s", caminho)
    return analisador_de(caminho, preferencias.engine)


def analisador_de(caminho: Path, opcoes: EngineSettings) -> EngineAnalyzer:
    """Um `EngineAnalyzer` com **todas** as preferências dentro (S-536).

    Existe porque a troca de binário precisa montar o motor novo do mesmo jeito que a abertura
    montou o primeiro, e uma segunda lista de argumentos aqui perderia a opção seguinte que
    alguém acrescentasse -- é o par de implementações que a S-31 registra.
    """
    return EngineAnalyzer(
        caminho,
        movetime_ms=opcoes.movetime_ms,
        threads=opcoes.threads,
        hash_mb=opcoes.hash_mb,
        multipv=opcoes.multipv,
        syzygy_path=opcoes.syzygy_path,
    )


# --------------------------------------------------------- os números desta máquina (S-536)


def nucleos_da_maquina() -> int:
    """Quantos núcleos há. Um quando o sistema não diz -- é o piso, e nunca zero."""
    return max(1, int(os.cpu_count() or 1))


def memoria_da_maquina_mb() -> int:
    """Memória física, em MB. Zero quando o sistema não diz.

    **Zero é resposta e não erro**: `motor_declarado.teto_de` já responde com o piso quando a
    memória é desconhecida, e uma exceção aqui impediria o diálogo de abrir por causa de um
    número que só serve para desenhar o teto de um campo.
    """
    try:
        sysconf = getattr(os, "sysconf", None)
        if sysconf is not None and "SC_PHYS_PAGES" in getattr(os, "sysconf_names", {}):  # pragma: no cover - POSIX
            return int(sysconf("SC_PAGE_SIZE") * sysconf("SC_PHYS_PAGES") / (1024 * 1024))
        import ctypes

        class _Status(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        estado = _Status()
        estado.dwLength = ctypes.sizeof(_Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))  # type: ignore[attr-defined]
        return int(estado.ullTotalPhys / (1024 * 1024))
    except Exception as exc:  # noqa: BLE001 - ver o docstring: o número é só o teto de um campo
        logger.debug("Memória da máquina não pôde ser lida: %s", exc)
        return 0


# ------------------------------------------------------------------- o formulário (S-536)


class DialogoDoMotor(QDialog):
    """Caminho do binário, as quatro opções e a pasta de tablebases. Devolve por `valores()`.

    **Os tetos são desta máquina e aparecem no campo**, e é a diferença entre uma preferência e um
    convite ao erro: um `Hash` que aceita 32 GB numa máquina de 8 é uma janela que trava quando
    alguém experimenta. O `QSpinBox` já recusa fora da faixa; a validação em pt-BR existe para o
    caminho e para dizer **por que**, que é o que uma caixa que só não deixa digitar não diz.

    Nada aqui decide: os limites são de `ui/motor_declarado.teto_de`, as frases de `validar`, e o
    que uma mudança faz com o processo é de `plano_de_aplicacao`.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        opcoes: EngineSettings | None = None,
        memoria_mb: int | None = None,
        nucleos: int | None = None,
        escolher_binario: Any = None,
        escolher_pasta: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(motor_declarado.TITULO)
        self._antes = opcoes or EngineSettings()
        self._memoria = memoria_da_maquina_mb() if memoria_mb is None else int(memoria_mb)
        self._nucleos = nucleos_da_maquina() if nucleos is None else int(nucleos)
        self._escolher_binario = escolher_binario
        self._escolher_pasta = escolher_pasta
        self.campos: dict[str, QSpinBox] = {}
        self._montar()

    def _montar(self) -> None:
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        pilha.setSpacing(espaco.folga())

        grade = QGridLayout()
        grade.setHorizontalSpacing(espaco.folga())
        grade.setVerticalSpacing(espaco.linha())
        linha = 0

        grade.addWidget(QLabel("Binário do motor:", self), linha, 0)
        self.campo_caminho = QLineEdit(self._antes.path, self)
        dica_em(
            self.campo_caminho,
            "Vazio deixa o programa procurar sozinho: no PATH, na pasta engines/ do projeto e nas\n"
            "instalações conhecidas de Stockfish. Trocar este campo derruba o motor e sobe outro.",
        )
        grade.addWidget(self.campo_caminho, linha, 1)
        procurar = QPushButton("Procurar…", self)
        tema.aplicar_papel(procurar, estilos.NEUTRO)
        procurar.clicked.connect(self._procurar_binario)
        grade.addWidget(procurar, linha, 2)
        linha += 1

        for registro in motor_declarado.OPCOES:
            teto = motor_declarado.teto_de(registro.chave, memoria_mb=self._memoria, nucleos=self._nucleos)
            rotulo = f"{registro.rotulo} ({registro.unidade}):" if registro.unidade else f"{registro.rotulo}:"
            grade.addWidget(QLabel(rotulo, self), linha, 0)
            campo = QSpinBox(self)
            campo.setRange(registro.piso, teto)
            campo.setValue(max(registro.piso, min(teto, int(getattr(self._antes, registro.chave)))))
            campo.setSuffix(f"   (até {teto})")
            if registro.dica:
                dica_em(campo, registro.dica)
            grade.addWidget(campo, linha, 1)
            self.campos[registro.chave] = campo
            linha += 1

        grade.addWidget(QLabel("Pasta de tablebases:", self), linha, 0)
        self.campo_tablebase = QLineEdit(self._antes.syzygy_path, self)
        dica_em(
            self.campo_tablebase,
            "Pasta com os arquivos .rtbw/.rtbz das tablebases Syzygy. Vazia: nada muda.\n"
            "Com ela, os finais que a tabela cobre passam a ter resultado exato em vez de estimativa.",
        )
        grade.addWidget(self.campo_tablebase, linha, 1)
        pasta = QPushButton("Procurar…", self)
        tema.aplicar_papel(pasta, estilos.NEUTRO)
        pasta.clicked.connect(self._procurar_pasta)
        grade.addWidget(pasta, linha, 2)
        grade.setColumnStretch(1, 1)
        pilha.addLayout(grade)

        self.lbl_erro = QLabel("", self)
        self.lbl_erro.setWordWrap(True)
        tema.pintar(self.lbl_erro, "color", tokens.PROBLEMA_TEXTO)
        pilha.addWidget(self.lbl_erro)

        self.lbl_maquina = QLabel(
            f"Esta máquina: {self._nucleos} núcleo(s), {self._memoria or '?'} MB de memória.", self
        )
        tema.pintar(self.lbl_maquina, "color", tokens.TEXTO_SECUNDARIO)
        pilha.addWidget(self.lbl_maquina)

        botoes = QDialogButtonBox(parent=self)
        botoes.addButton("Aplicar", QDialogButtonBox.ButtonRole.AcceptRole)
        botoes.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)
        self.resize(max(560, self.sizeHint().width()), self.sizeHint().height())

    def _procurar_binario(self) -> None:
        if self._escolher_binario is not None:
            escolhido = self._escolher_binario()
        else:  # pragma: no cover - o diálogo do sistema não se dirige de um roteiro
            escolhido, _filtro = QFileDialog.getOpenFileName(self, "Binário do motor UCI", self._antes.path)
        if escolhido:
            self.campo_caminho.setText(str(escolhido))

    def _procurar_pasta(self) -> None:
        if self._escolher_pasta is not None:
            escolhida = self._escolher_pasta()
        else:  # pragma: no cover - idem
            escolhida = QFileDialog.getExistingDirectory(self, "Pasta de tablebases", self._antes.syzygy_path)
        if escolhida:
            self.campo_tablebase.setText(str(escolhida))

    def valores(self) -> EngineSettings:
        """O que está nos campos agora, como `EngineSettings`."""
        return EngineSettings(
            path=self.campo_caminho.text().strip().strip('"'),
            movetime_ms=int(self.campos[motor_declarado.MOVETIME].value()),
            threads=int(self.campos[motor_declarado.THREADS].value()),
            hash_mb=int(self.campos[motor_declarado.HASH].value()),
            multipv=int(self.campos[motor_declarado.MULTIPV].value()),
            syzygy_path=self.campo_tablebase.text().strip().strip('"'),
        )

    def erro(self) -> str:
        """A primeira frase de recusa, ou vazio. É o que `_confirmar` mostra e o teste lê."""
        pedido = self.valores()
        for problema in (
            motor_declarado.validar_caminho(pedido.path),
            motor_declarado.validar_pasta_de_tablebase(pedido.syzygy_path),
        ):
            if problema:
                return problema
        for registro in motor_declarado.OPCOES:
            problema = motor_declarado.validar(
                registro.chave,
                getattr(pedido, registro.chave),
                memoria_mb=self._memoria,
                nucleos=self._nucleos,
            )
            if problema:
                return problema
        return ""

    def _confirmar(self) -> None:
        """Recusa **na própria janela**, e não numa caixa em cima dela.

        Uma segunda caixa para dizer "o caminho não existe" faria fechar a caixa e voltar ao campo
        -- dois cliques para uma correção de um caractere. A frase fica ao lado do campo, que é
        onde a correção acontece.
        """
        problema = self.erro()
        self.lbl_erro.setText(problema)
        if problema:
            return
        self.accept()


# ----------------------------------------------------- aplicar sem reiniciar (S-536)


class MotorVivo(QObject):
    """O motor da sessão, seguindo as preferências sem que a janela feche (S-536).

    `aplicado(analisador, frase)` chega quando a mudança está de pé -- `analisador` é `None` quando
    o caminho novo não aponta para motor nenhum, e aí a seção some como sempre somiu (S-33).
    """

    aplicado = pyqtSignal(object, str)
    falhou = pyqtSignal(str, object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        analisador: EngineAnalyzer | None = None,
        procurar: Any = find_engine,
    ) -> None:
        super().__init__(parent)
        self._analisador = analisador
        self._procurar = procurar
        self._tarefa: Tarefa | None = None

    @property
    def analisador(self) -> EngineAnalyzer | None:
        return self._analisador

    @property
    def ocupado(self) -> bool:
        return self._tarefa is not None

    def esperar(self, espera_ms: int) -> bool:
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(espera_ms))

    def aplicar(self, antes: EngineSettings, depois: EngineSettings) -> bool:
        """Põe as preferências novas de pé. Devolve se há trabalho de verdade a fazer.

        **O que não fala com o processo é aplicado aqui mesmo**, na linha de eventos: `multipv` e
        `movetime_ms` são dois atributos Python, e mandá-los para uma thread seria uma thread para
        atribuir um inteiro. O que fala com o processo -- `setoption`, ou derrubar e subir -- vai
        para a `Tarefa`, porque o `lock` do motor pode estar com uma análise em curso.
        """
        if self._tarefa is not None:
            return False
        plano = motor_declarado.plano_de_aplicacao(antes, depois)
        if not plano.mudou:
            self.aplicado.emit(self._analisador, plano.frase())
            return False
        self._aplicar_por_analise(plano.por_analise)
        if not plano.trocar_processo and not plano.do_processo:
            self.aplicado.emit(self._analisador, plano.frase())
            return True

        atual = self._analisador
        procurar = self._procurar
        opcoes = dict(plano.do_processo)
        trocar = plano.trocar_processo

        def _trabalho() -> EngineAnalyzer | None:
            if not trocar:
                if atual is not None:
                    atual.reconfigurar(opcoes)
                return atual
            caminho = procurar(depois.path or None)
            if atual is not None:
                atual.close()
            if caminho is None:
                return None
            if atual is not None:
                # **O mesmo objeto**, para a referência que a janela guarda continuar valendo.
                atual.trocar_binario(caminho)
                atual.movetime_ms = depois.movetime_ms
                atual.multipv = depois.multipv
                atual.reconfigurar(_opcoes_uci(depois))
                atual.start()
                return atual
            novo = analisador_de(caminho, depois)
            novo.start()
            return novo

        tarefa = Tarefa(_trabalho, parent=self, nome="opções do motor")
        tarefa.pronto.connect(lambda motor: self._pronto(motor, plano.frase()))
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._terminou)
        self._tarefa = tarefa
        tarefa.start()
        return True

    def _aplicar_por_analise(self, valores: dict[str, int]) -> None:
        motor = self._analisador
        if motor is None:
            return
        if motor_declarado.MULTIPV in valores:
            motor.multipv = int(valores[motor_declarado.MULTIPV])
        if motor_declarado.MOVETIME in valores:
            motor.movetime_ms = int(valores[motor_declarado.MOVETIME])

    def _pronto(self, motor: Any, frase: str) -> None:
        self._analisador = motor
        self.aplicado.emit(motor, frase)

    def _falhou(self, mensagem: str, excecao: object) -> None:
        # Um motor que não subiu deixa a sala sem motor, e não com um objeto que sempre falha.
        self._analisador = None
        logger.warning("As opções do motor não puderam ser aplicadas: %s", mensagem)
        self.falhou.emit(mensagem, excecao)

    def _terminou(self) -> None:
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.deleteLater()


def _opcoes_uci(opcoes: EngineSettings) -> dict[str, int | str]:
    """As opções de protocolo daquelas preferências. É o que um motor recém-aberto recebe."""
    return {"Threads": opcoes.threads, "Hash": opcoes.hash_mb, "SyzygyPath": opcoes.syzygy_path}
