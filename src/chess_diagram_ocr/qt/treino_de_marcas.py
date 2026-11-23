"""*Treinar o modelo de marcas…*: treinar, medir e instalar o modelo que diz qual marca a casa tem.

É o `cvoff-marcas` com tela, e nada além dele: as contas são de `modelo_de_marcas.treinar`, de
`medicao_de_marcas` e de `teste_de_marcas`, as mesmas do comando. O que a janela faz é a ordem:

1. **congela** as anotações novas no teste (`teste_de_marcas.acrescentar`): o que já estava não muda;
2. **treina** um modelo novo em `models/experiments/modelo_de_marcas/`, sem tocar no instalado;
3. **mede** o novo, o instalado e o detector clássico na mesma régua: o teste congelado e
   `AMOSTRAS_DE_ALARME` diagramas que ninguém anotou;
4. e só **instala** quando a pessoa pede, guardando uma cópia do anterior. Se o novo perde em qualquer
   das três contas (`medicao_de_marcas.em_que_perde`), a janela pergunta antes.

**Não modal, e fechar esconde.** O treino é longo -- uma época em CPU passa de dez minutos --, e a
janela principal continua usável. O trabalho fica registrado no rodapé (`BusyRegistry`), com «Cancelar»
e `loses_work`, como o treino do modelo de peças: o modelo já gravado é a melhor época terminada, e
o que se perde é o progresso desde ela.

**O torch só é importado na thread.** Montar esta janela na abertura do programa não pode custar a
carga da biblioteca: ela vem no primeiro «Treinar», e no primeiro «Instalar», que confere o arquivo.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr import medicao_de_marcas as md
from chess_diagram_ocr import teste_de_marcas as tm
from chess_diagram_ocr.config import PROJECT_ROOT
from chess_diagram_ocr.opiniao_das_marcas import caminho_do_modelo_de_marcas
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.relogio import agora
from chess_diagram_ocr.ui import espaco, estilos, folha_de_estilo, formato
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken

if TYPE_CHECKING:
    from chess_diagram_ocr.modelo_de_marcas import ResultadoDoTreino

__all__ = ["EPOCAS_PADRAO", "JanelaDoModeloDeMarcas", "RodadaDoTreino"]

logger = logging.getLogger(__name__)

EPOCAS_PADRAO = 3
"""As épocas do v6, o modelo instalado em 2026-11-22: três bastaram, e a validação sintética já não
separa uma receita da outra depois disso."""

PASTA_DOS_EXPERIMENTOS = PROJECT_ROOT / "models" / "experiments" / "modelo_de_marcas"

NOVO, INSTALADO, DETECTOR = "novo", "instalado", "detector"
NOMES_DOS_LEITORES = {NOVO: "Modelo novo", INSTALADO: "Modelo instalado", DETECTOR: "Detector clássico"}


@dataclass
class RodadaDoTreino:
    """O que uma rodada de «Treinar» deixou: o modelo novo, a medição dele e o que dizer."""

    caminho: Path | None = None
    """O checkpoint novo, ou `None` quando nenhuma época terminou."""
    resultado: ResultadoDoTreino | None = None
    comparacao: md.Comparacao | None = None
    congeladas: int = 0
    """Quantos diagramas anotados entraram no teste nesta rodada."""
    mensagem: str = ""


def _duracao(segundos: float) -> str:
    minutos = int(round(segundos / 60))
    return f"{minutos // 60} h {minutos % 60:02d} min" if minutos >= 60 else f"{max(1, minutos)} min"


class JanelaDoModeloDeMarcas(QDialog):
    """A janela do modelo de marcas. Ver o cabeçalho do módulo."""

    _andou = pyqtSignal(str, int, int)
    """`(frase, feito, total)`, da thread: a barra e o rótulo de estado."""
    _acabou = pyqtSignal(object)
    """A `RodadaDoTreino`, da thread, no fim -- com ou sem modelo novo."""
    instalado = pyqtSignal(str)
    """O caminho do modelo recém-instalado: quem tem o anterior carregado o esquece."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        caminhos: Callable[[], tuple[Path, Path, Path]],
        anotacoes: Path | None = None,
        teste: Path | None = None,
        modelo_instalado: Callable[[], Path] = caminho_do_modelo_de_marcas,
        experimentos: Path = PASTA_DOS_EXPERIMENTOS,
        busy: BusyRegistry | None = None,
        amostras_de_alarme: int = md.AMOSTRAS_DE_ALARME,
        workers: int | None = None,
        tabuleiros_val: int | None = 1500,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modelo de marcas")
        self.resize(680, 520)
        self._caminhos = caminhos
        self._anotacoes = Path(anotacoes) if anotacoes is not None else mc.ARQUIVO_DAS_MARCAS
        self._teste = Path(teste) if teste is not None else tm.ARQUIVO_DO_TESTE
        self._modelo_instalado = modelo_instalado
        self._experimentos = Path(experimentos)
        self._busy = busy
        self._ficha: BusyToken | None = None
        self._amostras_de_alarme = amostras_de_alarme
        self._workers = workers
        self._tabuleiros_val = tabuleiros_val
        self._cancelar: threading.Event | None = None
        self._trabalho: threading.Thread | None = None
        self.rodada: RodadaDoTreino | None = None
        self._montar()
        self._andou.connect(self._chegou_progresso)
        self._acabou.connect(self._chegou_rodada)

    # ------------------------------------------------------------------------------- a tela

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.linha())

        self.lbl_situacao = QLabel("", self)
        self.lbl_situacao.setWordWrap(True)
        fora.addWidget(self.lbl_situacao)

        grade = QGridLayout()
        grade.addWidget(QLabel("Épocas", self), 0, 0)
        self.spin_epocas = QSpinBox(self)
        self.spin_epocas.setRange(1, 30)
        self.spin_epocas.setValue(EPOCAS_PADRAO)
        grade.addWidget(self.spin_epocas, 0, 1)
        grade.addWidget(QLabel("Tabuleiros de treino (0 = todos)", self), 1, 0)
        self.spin_tabuleiros = QSpinBox(self)
        self.spin_tabuleiros.setRange(0, 1_000_000)
        self.spin_tabuleiros.setSingleStep(500)
        self.spin_tabuleiros.setToolTip("Um número pequeno faz um treino curto, para conferir o caminho antes do longo.")
        grade.addWidget(self.spin_tabuleiros, 1, 1)
        grade.setColumnStretch(2, 1)
        fora.addLayout(grade)

        botoes = QHBoxLayout()
        acoes: tuple[tuple[str, Callable[[], None], str], ...] = (
            ("Treinar", self.treinar, estilos.PRIMARIO),
            ("Cancelar", self.cancelar, estilos.NEUTRO),
            ("Instalar este modelo", self.instalar, estilos.NEUTRO),
        )
        feitos = []
        for rotulo, funcao, papel in acoes:
            botao = QPushButton(rotulo, self)
            botao.setAutoDefault(False)
            botao.clicked.connect(lambda _marcado=False, f=funcao: f())
            tema.aplicar_papel(botao, papel)
            botoes.addWidget(botao)
            feitos.append(botao)
        self.btn_treinar, self.btn_cancelar, self.btn_instalar = feitos
        self.btn_cancelar.setEnabled(False)
        self.btn_instalar.setEnabled(False)
        botoes.addStretch(1)
        fora.addLayout(botoes)

        self.barra = QProgressBar(self)
        self.barra.setRange(0, 1)
        self.barra.setValue(0)
        self.barra.setTextVisible(False)
        fora.addWidget(self.barra)
        self.lbl_estado = QLabel("", self)
        self.lbl_estado.setWordWrap(True)
        fora.addWidget(self.lbl_estado)

        self.tabela = QTableWidget(0, 3, self)
        self.tabela.setHorizontalHeaderLabels(
            ["Marcas achadas no teste", "Inventadas no teste", "Diagramas sem anotação apontados"]
        )
        cabecalho = self.tabela.horizontalHeader()
        if cabecalho is not None:
            cabecalho.setStretchLastSection(True)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        fora.addWidget(self.tabela, 1)

        self.lbl_veredito = QLabel("", self)
        self.lbl_veredito.setWordWrap(True)
        fora.addWidget(self.lbl_veredito)

        apoio = QLabel(
            "O modelo novo vai para models/experiments/modelo_de_marcas/ e só substitui o instalado "
            "quando você clicar em «Instalar este modelo». Fechar esta janela não interrompe o treino.",
            self,
        )
        apoio.setProperty(folha_de_estilo.PROPRIEDADE_DE_APOIO, "true")
        apoio.setWordWrap(True)
        fora.addWidget(apoio)

    @property
    def rodando(self) -> bool:
        return self._trabalho is not None

    def abrir(self) -> None:
        """Mostra a janela com a situação de agora: o modelo instalado e o teste congelado."""
        self.lbl_situacao.setText(self.situacao())
        self.show()
        self.raise_()
        self.activateWindow()

    def reject(self) -> None:
        """`Esc` e o X escondem: o treino segue, e a janela volta inteira no próximo «abrir»."""
        self.hide()

    def situacao(self) -> str:
        """A frase do topo: o que está instalado e com que régua um modelo novo será medido."""
        instalado = Path(self._modelo_instalado())
        linhas = [
            f"Modelo instalado: {instalado}" if instalado.exists() else "Nenhum modelo de marcas instalado: "
            "a conferência e a aba Texto usam só o detector clássico."
        ]
        try:
            casos = tm.ler_teste(self._teste)
        except ValueError as exc:
            linhas.append(f"O teste congelado não abre: {exc}")
        else:
            marcas = sum(len(caso.casas) for caso in casos)
            linhas.append(
                f"Teste congelado: {len(casos)} diagrama(s) reais com {marcas} marca(s). As anotações "
                "novas da conferência entram nele quando o treino começa."
            )
        return "\n".join(linhas)

    # ------------------------------------------------------------------------------ o treino

    def treinar(self) -> None:
        if self.rodando:
            return
        self._cancelar = threading.Event()
        self.rodada = None
        self.tabela.setRowCount(0)
        self.lbl_veredito.setText("")
        self.btn_instalar.setEnabled(False)
        self.btn_treinar.setEnabled(False)
        self.btn_cancelar.setEnabled(True)
        if self._busy is not None:
            self._ficha = self._busy.register(
                "treino do modelo de marcas",
                loses_work=True,
                cancellable=True,
                detail="preparando",
                cancel=self.cancelar,
            )
        epocas = self.spin_epocas.value()
        tabuleiros = self.spin_tabuleiros.value() or None
        self._chegou_progresso("Congelando as anotações novas no teste…", 0, 0)
        self._trabalho = threading.Thread(
            target=self._trabalhar,
            args=(epocas, tabuleiros, self._cancelar),
            name="treino-do-modelo-de-marcas",
            daemon=True,
        )
        self._trabalho.start()

    def cancelar(self) -> None:
        """Pede a parada. O treino confere a cada lote, e a medição a cada imagem."""
        if self._cancelar is not None:
            self._cancelar.set()
            self.lbl_estado.setText("Cancelando… o modelo já gravado é a melhor época terminada.")

    def esperar(self, segundos: float = 600.0) -> None:
        """Espera a thread terminar. Para os testes; a janela nunca espera."""
        if self._trabalho is not None:
            self._trabalho.join(segundos)

    def _dizer(self, frase: str, feito: int, total: int) -> None:
        """Da thread: a barra, o rótulo e o rodapé."""
        self._andou.emit(frase, feito, total)
        if self._ficha is not None:
            self._ficha.update(frase, feito=feito, total=total)

    def _trabalhar(self, epocas: int, tabuleiros: int | None, cancelar: threading.Event) -> None:
        rodada: RodadaDoTreino | None = None
        try:
            rodada = self._rodada(epocas, tabuleiros, cancelar)
        except (OSError, RuntimeError, ValueError, KeyError, cv2.error) as exc:
            logger.exception("Treino do modelo de marcas falhou.")
            rodada = RodadaDoTreino(mensagem=f"O treino falhou: {exc}")
        finally:
            self._acabou.emit(rodada or RodadaDoTreino(mensagem="O treino parou com um erro inesperado; veja o log."))

    def _rodada(self, epocas: int, tabuleiros: int | None, cancelar: threading.Event) -> RodadaDoTreino:
        from chess_diagram_ocr.detector_de_marcas import sugerir_marcas
        from chess_diagram_ocr.modelo_de_marcas import carregar, treinar
        from chess_diagram_ocr.splits import load_splits
        from chess_diagram_ocr.training import resolve_num_workers

        csv_path, samples_dir, splits_path = self._caminhos()
        novos, _fora = tm.casos_das_anotacoes(self._anotacoes, csv_path, samples_dir)
        congeladas = len(tm.acrescentar(self._teste, novos))
        casos = tm.ler_teste(self._teste)
        if not casos:
            return RodadaDoTreino(
                congeladas=congeladas,
                mensagem="O teste congelado está vazio: anote marcas na conferência da importação antes de treinar. "
                "Sem ele não há como saber se o modelo novo é melhor.",
            )
        fora = {caso.amostra for caso in casos} | md.anotadas_em(self._anotacoes)
        splits = load_splits(splits_path)
        saida = self._experimentos / f"marcas_{agora():%Y%m%d_%H%M%S}.pt"
        inicio = time.monotonic()

        def andou(epoca: int, total: int, fracao: float, f1: float | None) -> None:
            feito = (epoca - 1 + fracao) / total
            resta = (time.monotonic() - inicio) * (1 - feito) / feito if feito > 0 else 0.0
            frase = f"Treinando: época {epoca} de {total}"
            if f1 is not None:
                frase += f", F1 das marcas na validação sintética {formato.decimal(f1, 4)}"
            elif fracao >= 1.0:
                frase += ": conferindo a época na validação…"
            if 0.02 < feito < 1:
                frase += f". Faltam cerca de {_duracao(resta)}."
            self._dizer(frase, int(feito * 1000), 1000)

        resultado = treinar(
            csv_path=csv_path,
            samples_dir=samples_dir,
            splits=splits,
            saida=saida,
            excluidas=fora,
            epocas=epocas,
            workers=resolve_num_workers(self._workers),
            tabuleiros_treino=tabuleiros,
            tabuleiros_val=self._tabuleiros_val,
            progresso=andou,
            cancelar=cancelar,
        )
        if not saida.exists():
            return RodadaDoTreino(
                resultado=resultado, congeladas=congeladas, mensagem="Treino cancelado antes de a primeira época terminar."
            )

        novo = carregar(saida)
        leitores: dict[str, md.Leitor] = {NOVO: lambda tabuleiro: novo.ler(tabuleiro).casas}
        instalado_em = Path(self._modelo_instalado())
        if instalado_em.exists():
            instalado = carregar(instalado_em)
            leitores[INSTALADO] = lambda tabuleiro: instalado.ler(tabuleiro).casas
        leitores[DETECTOR] = lambda tabuleiro: sugerir_marcas(tabuleiro).casas
        amostras = md.amostras_sem_anotacao(splits, fora, self._amostras_de_alarme)
        comparacao = md.comparar(
            leitores,
            casos,
            samples_dir,
            amostras,
            cancelar=cancelar,
            progresso=lambda feitas, total: self._dizer(
                f"Medindo no teste e em {len(amostras)} diagramas sem anotação: {feitas} de {total}", feitas, total
            ),
        )
        mensagem = "Treino cancelado; o modelo novo é a melhor época que terminou." if resultado.cancelado else ""
        if comparacao.cancelada:
            mensagem = "Medição cancelada: o placar abaixo é parcial."
        return RodadaDoTreino(
            caminho=saida, resultado=resultado, comparacao=comparacao, congeladas=congeladas, mensagem=mensagem
        )

    # ---------------------------------------------------------------- a volta, na thread da janela

    def _chegou_progresso(self, frase: str, feito: int, total: int) -> None:
        self.lbl_estado.setText(frase)
        self.barra.setRange(0, max(0, total))
        self.barra.setValue(max(0, min(feito, total)))

    def _chegou_rodada(self, rodada: object) -> None:
        """Slot: não levanta (no PyQt6 uma exceção aqui derruba o processo)."""
        if not isinstance(rodada, RodadaDoTreino):
            return
        self.rodada = rodada
        self._trabalho = None
        self._cancelar = None
        if self._ficha is not None:
            self._ficha.release()
            self._ficha = None
        self.btn_treinar.setEnabled(True)
        self.btn_cancelar.setEnabled(False)
        self.barra.setRange(0, 1)
        self.barra.setValue(1 if rodada.comparacao is not None else 0)
        self.lbl_situacao.setText(self.situacao())
        partes = []
        if rodada.congeladas:
            partes.append(f"{rodada.congeladas} diagrama(s) anotado(s) entraram no teste congelado.")
        if rodada.resultado is not None and rodada.caminho is not None:
            partes.append(
                f"Melhor época {rodada.resultado.melhor_epoca}, gravada em {rodada.caminho}."
            )
        if rodada.mensagem:
            partes.append(rodada.mensagem)
        self.lbl_estado.setText(" ".join(partes))
        comparacao = rodada.comparacao
        if comparacao is None:
            return
        self._preencher(comparacao)
        base = INSTALADO if INSTALADO in comparacao.leituras else DETECTOR
        perdas = md.em_que_perde(comparacao, NOVO, base)
        if perdas:
            self.lbl_veredito.setText(f"O modelo novo perde para o {NOMES_DOS_LEITORES[base].lower()}: " + "; ".join(perdas) + ".")
        else:
            self.lbl_veredito.setText(f"O modelo novo não perde em nada para o {NOMES_DOS_LEITORES[base].lower()}.")
        self.btn_instalar.setEnabled(not comparacao.cancelada)

    def _preencher(self, comparacao: md.Comparacao) -> None:
        rotulos = list(comparacao.leituras)
        self.tabela.setRowCount(len(rotulos))
        self.tabela.setVerticalHeaderLabels([NOMES_DOS_LEITORES.get(r, r) for r in rotulos])
        for linha, rotulo in enumerate(rotulos):
            placar = comparacao.placar(rotulo)
            valores = (
                f"{sum(placar.acertos.values())} de {placar.marcas}",
                str(sum(placar.falsos.values())),
                f"{comparacao.alarmes(rotulo)} de {comparacao.amostras_lidas}",
            )
            for coluna, valor in enumerate(valores):
                self.tabela.setItem(linha, coluna, QTableWidgetItem(valor))
        self.tabela.resizeColumnsToContents()

    # ------------------------------------------------------------------------------- instalar

    def instalar(self) -> None:
        """Põe o modelo novo no lugar do instalado. Se ele perde em alguma conta, pergunta antes."""
        from chess_diagram_ocr.modelo_de_marcas import instalar

        rodada = self.rodada
        if rodada is None or rodada.caminho is None or rodada.comparacao is None:
            return
        comparacao = rodada.comparacao
        base = INSTALADO if INSTALADO in comparacao.leituras else DETECTOR
        perdas = md.em_que_perde(comparacao, NOVO, base)
        if perdas:
            resposta = QMessageBox.question(
                self,
                "Instalar o modelo novo?",
                f"O modelo novo perde para o {NOMES_DOS_LEITORES[base].lower()}:\n\n- "
                + "\n- ".join(perdas)
                + "\n\nInstalar mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
        destino = Path(self._modelo_instalado())
        try:
            copia = instalar(rodada.caminho, destino, quando=f"{agora():%Y%m%d_%H%M%S}")
        except (OSError, ValueError) as exc:
            # Na própria janela, e não numa caixa: não há o que decidir, e o modelo instalado ficou como estava.
            self.lbl_veredito.setText(f"O modelo novo não foi instalado: {exc}. O instalado continua o mesmo.")
            return
        self.btn_instalar.setEnabled(False)
        frase = f"Instalado em {destino}."
        if copia is not None:
            frase += f" O anterior ficou em {copia}."
        self.lbl_veredito.setText(frase + " As próximas leituras já usam o modelo novo.")
        self.lbl_situacao.setText(self.situacao())
        self.instalado.emit(str(destino))
