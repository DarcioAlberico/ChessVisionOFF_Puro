"""A aba de Revisão no segundo frontend: a fila da S-22 na tela (S-22/S-119/S-503).

**O painel não reconhece nada, não guarda modelo e não varre.** Ele mostra a fila ordenada e
devolve o item escolhido a quem tem o editor de posição -- a mesma fronteira do outro lado, e a
razão de este arquivo ser curto: `review_queue.py` decide o que entra na fila, com que
prioridade, como duas varreduras se fundem e o que "revisado" significa. Nada disso é reescrito.

**A varredura é uma só, e ela é da Galeria** (S-119). Este painel pede a varredura do livro e
recebe a fila de volta pelo `SumidouroDeRevisao`. Duas passadas pelo mesmo PDF custavam
338 s + 299 s no `PDF/1000 Chess Problems`, e o botão continua aqui só porque quem está na fila
não deveria ter de saber que a varredura "mora" na outra aba.

---

**A diferença que morde entre os dois frontends é uma linha, e ela é a thread.** O sumidouro é
alimentado pela thread da varredura, e o aviso de progresso tem de chegar a um widget. No Tk isso
é `panel.after(0, ...)`; aqui é um **sinal**, com a conexão em fila que o Qt faz sozinho quando
emissor e receptor estão em threads diferentes. As duas formas existem pela mesma razão -- tocar
num widget da thread errada derruba o programa --, e é por isso que `ui/varredura_de_revisao.py`
compartilha o acumulador e **não** o sumidouro: um sumidouro comum teria de esconder essa
diferença atrás de uma função, e a função esconderia justamente o que quem lê precisa ver.

**`entregar` continua tendo de ser chamado na thread da janela**, como do outro lado. O sinal
resolve o progresso, que é texto; a entrega mexe na tabela, na fila e no arquivo, e um sinal ali
tornaria a ordem "entregou, depois terminou" dependente da linha de eventos. Quem chama é a
Galeria, que já está na thread certa quando a varredura acaba.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.pdf_to_pgn import ScannedDiagram
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.tabela import TabelaQt
from chess_diagram_ocr.review_queue import (
    DEFAULT_CACHE_DIR,
    DEFAULT_QUEUE_PATH,
    ReviewQueue,
    error_rate,
    merge_queues,
)
from chess_diagram_ocr.ui import espaco, estilos, formato, strings, tabela, tipografia
from chess_diagram_ocr.ui.varredura_de_revisao import AcumuladorDaFila, PedidoDeVarredura

logger = logging.getLogger(__name__)

__all__ = ["COLUNAS", "PainelDeRevisao", "SumidouroDeRevisao"]

COLUNAS: tuple[tabela.Coluna, ...] = (
    tabela.Coluna("prioridade", "Prio.", 60, numerica=True),
    tabela.Coluna("página", "Pag.", 50, numerica=True),
    tabela.Coluna("diagrama", "Diag.", 50, numerica=True),
    tabela.Coluna("confiança", "Conf. min", 80, numerica=True),
    tabela.Coluna("status", "Status", 80),
    tabela.Coluna("motivo", "Motivo", 460, elastica=True),
)
"""Quatro números e dois textos, as mesmas de `ui/review_panel.COLUNAS`.

`1623.8`, `40`, `1` e `0.082` alinhados à esquerda não se comparam por magnitude, e essa é a
leitura inteira de uma fila ordenada por prioridade (S-153). Quem traduz `numerica` em alinhamento
é `qt/tabela.py`, e não este arquivo."""

ALTURA_EM_LINHAS = 14
"""Quantas linhas a tabela mostra sem rolar. O mesmo `height=14` do outro frontend."""


class SumidouroDeRevisao(QObject):
    """Recebe cada diagrama da varredura da Galeria e entrega a fila pronta ao painel (S-119).

    **Um `QObject` e não um objeto simples**, e é a única razão de a classe existir deste lado: o
    aviso de progresso vem da thread da varredura e tem de chegar a um `QLabel`. Um sinal atravessa
    a fronteira de thread com a conexão em fila que o Qt escolhe sozinho; uma chamada direta
    derruba o processo, e nem sempre na hora -- que é o pior formato desse defeito.

    O acumulador é o de `ui/varredura_de_revisao.py`, compartilhado com o Tk: é ele que adia a
    leitura do `labels.csv` para a thread da varredura (S-116) e que responde "nada lido, nada
    entregue" (S-120).
    """

    progrediu = pyqtSignal(str)
    """A frase de progresso. Emitida da thread da varredura e recebida na da janela."""

    def __init__(self, painel: PainelDeRevisao, pedido: PedidoDeVarredura, *, cache_dir: Path) -> None:
        super().__init__(painel)
        self._painel = painel
        self._acumulador = AcumuladorDaFila(pedido, cache_dir=cache_dir)
        self.progrediu.connect(painel.mostrar_progresso)

    def feed(self, scanned: ScannedDiagram) -> None:
        """Um diagrama lido pela varredura. Roda na thread dela."""
        self._acumulador.feed(scanned)

    def progress(self, pagina: int, total: int) -> None:
        """A mesma página que a Galeria mostra, na barra desta aba. Vem da thread da varredura.

        Não abre um segundo registro de operação longa: a barra do rodapé é da varredura, e ela é
        uma só desde a S-119. O que falta aqui é só a pessoa que está *nesta* aba não ficar
        olhando uma frase parada enquanto o livro roda.
        """
        self.progrediu.emit(f"Varrendo o livro... página {pagina} de {total}")

    def deliver(self, *, cancelled: bool) -> None:
        """A fila pronta, na tela. **Tem de ser chamado na thread da janela.**

        Nada lido, nada entregue: uma varredura retomada que não achou página nova (S-120) não
        pode substituir a fila por uma vazia.
        """
        pronta = self._acumulador.pronta()
        if pronta is None:
            self._painel.terminar_varredura()
            return
        self._painel.aplicar_varredura(pronta, cancelled, pages=self._acumulador.paginas())
        self._painel.terminar_varredura()

    def release(self) -> None:
        """A varredura terminou sem entregar -- falhou, ou não havia o que varrer."""
        self._painel.terminar_varredura()


class PainelDeRevisao(QWidget):
    """Lista navegável da fila, com varredura em segundo plano e cancelamento."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status. A janela decide onde ela aparece."""

    abriu = pyqtSignal(object, int)
    """`(ReviewItem, posição na fila)` -- o item que a pessoa mandou corrigir.

    Um sinal e não uma função no construtor, como `qt/painel_de_resultado.py`: quem recebe é a
    janela, e é ela que sabe qual editor está aberto. O tipo do primeiro parâmetro é `object`
    porque `pyqtSignal` não conhece `ReviewItem`; a assinatura verdadeira está aqui."""

    pediu_varredura = pyqtSignal()
    """A varredura do livro, que é a da Galeria (S-119)."""

    pediu_cancelamento = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        pedido_de_varredura: Callable[[], PedidoDeVarredura | None] | None = None,
        queue_path: Path = DEFAULT_QUEUE_PATH,
        cache_dir: Path = DEFAULT_CACHE_DIR,
    ) -> None:
        """`pedido_de_varredura` é o que a janela tem configurado quando alguém manda varrer.

        `None` -- o padrão -- é o painel montado sem janela em volta, que é o que um roteiro de
        teste faz: ele abre, mostra a fila do arquivo e funciona; só não tem de onde varrer.
        """
        super().__init__(parent)
        self._pedido_de_varredura = pedido_de_varredura
        self.queue_path = Path(queue_path)
        self.cache_dir = Path(cache_dir)

        self.queue = ReviewQueue.load(self.queue_path)
        self.queue.sort()
        self._varrendo = False
        self._posicoes: list[int] = []
        """Posição na `queue.items` de cada linha visível, na ordem da tabela."""

        self._montar()
        self.refresh()

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.linha(),) * 4)
        fora.setSpacing(espaco.linha())

        barra = BarraFluida(self)
        self.btn_varrer = self._botao(barra, strings.VARRER_LIVRO, self.iniciar_varredura, estilos.NEUTRO)
        dica_em(
            self.btn_varrer,
            "Fica cinza enquanto a varredura roda: uma por vez, porque as duas leriam o mesmo\n"
            "livro com o mesmo modelo. Pergunta antes quais livros varrer; a fila desta aba\n"
            "só sai do PDF aberto -- é dele que ela declara a procedência.",
        )
        self.btn_cancelar = self._botao(barra, "Cancelar", self.cancelar_varredura, estilos.NEUTRO)
        self.btn_cancelar.setEnabled(False)
        dica_em(
            self.btn_cancelar,
            "Só fica ativo durante a varredura. O cancelamento termina a página em curso\n"
            "antes de parar, e os recortes já gravados continuam valendo.",
        )
        self._botao(barra, "Abrir fila", self.abrir_arquivo_de_fila, estilos.NEUTRO)
        self._botao(barra, "Salvar fila", self.salvar_fila, estilos.NEUTRO)
        self.so_pendentes = QCheckBox("Só pendentes", barra)
        self.so_pendentes.setChecked(True)
        self.so_pendentes.stateChanged.connect(lambda _valor: self.refresh())
        barra.adicionar(self.so_pendentes)
        fora.addWidget(barra)

        self.lbl_resumo = QLabel("", self)
        self.lbl_progresso = QLabel("", self)
        for rotulo in (self.lbl_resumo, self.lbl_progresso):
            rotulo.setWordWrap(True)
            fora.addWidget(rotulo)

        self.tabela = TabelaQt(COLUNAS, self)
        self.tabela.setSelectionMode(TabelaQt.SelectionMode.SingleSelection)
        self.tabela.itemDoubleClicked.connect(lambda *_: self.abrir_selecionado())
        self.tabela.itemSelectionChanged.connect(self._mostrar_motivo)
        self.tabela.setMinimumHeight(ALTURA_EM_LINHAS * tema.altura_de_linha_atual())
        fora.addWidget(self.tabela, 1)

        # O motivo **inteiro** do item selecionado, sob a tabela (S-153). Rolar para o lado numa
        # lista de 129 linhas custa a coluna de referência: a tabela dá a visão geral, o rodapé dá
        # o texto, e nenhuma das duas precisa escolher entre as duas coisas.
        self.lbl_motivo = QLabel("", self)
        self.lbl_motivo.setWordWrap(True)
        self.lbl_motivo.setFont(tema.fonte_atual(tipografia.CORPO))
        fora.addWidget(self.lbl_motivo)

        acoes = BarraFluida(self)
        self._botao(acoes, "Corrigir agora", self.abrir_selecionado, estilos.PRIMARIO)
        self._botao(acoes, "Marcar revisado", lambda: self.marcar_selecionado("done"), estilos.NEUTRO)
        self._botao(acoes, "Pular", lambda: self.marcar_selecionado("skipped"), estilos.NEUTRO)
        self._botao(acoes, "Reabrir", lambda: self.marcar_selecionado("pending"), estilos.NEUTRO)
        self._botao(acoes, "Próximo pendente", self.abrir_proximo_pendente, estilos.NEUTRO)
        fora.addWidget(acoes)

    def _botao(self, barra: BarraFluida, rotulo: str, funcao: object, papel: str) -> QPushButton:
        botao = QPushButton(rotulo, barra)
        botao.clicked.connect(funcao)  # type: ignore[arg-type]
        tema.aplicar_papel(botao, papel)
        barra.adicionar(botao)
        return botao

    # -------------------------------------------------------------------------------- tabela

    def refresh(self) -> None:
        """Redesenha a tabela a partir da fila, respeitando o filtro de pendentes."""
        so_pendentes = self.so_pendentes.isChecked()
        self._posicoes = [
            posicao
            for posicao, item in enumerate(self.queue.items)
            if not so_pendentes or item.status == "pending"
        ]
        self.tabela.preencher(
            (
                # Sem casa decimal, e a confiança em porcentagem (S-169): `1623.8` sugere que ele
                # difere de `1623.7`, e `0.082` é o mesmo número que a barra de status escreve
                # como `8,2%`.
                formato.prioridade(item.priority),
                item.page_number,
                item.diagram_index,
                formato.confianca(item.min_confidence),
                strings.status_da_fila(item.status),
                "; ".join(item.reasons),
            )
            for item in (self.queue.items[posicao] for posicao in self._posicoes)
        )
        if self.queue.items:
            taxa = error_rate(self.queue.items)
            self.lbl_resumo.setText(f"{self.queue.summary()} | {taxa:.0%} com sinal objetivo de erro")
        else:
            self.lbl_resumo.setText(f"Fila vazia. Abra um PDF e use '{strings.VARRER_LIVRO}'.")
        self._mostrar_motivo()

    def motivo_selecionado(self) -> str:
        """O motivo inteiro do item selecionado, ou vazio quando não há seleção (S-153).

        Função de leitura, sem widget de saída: é o que permite afirmar o **texto** do rodapé sem
        perguntar a um `QLabel` o que ele está mostrando.
        """
        posicao = self.posicao_selecionada()
        if posicao is None:
            return ""
        item = self.queue.items[posicao]
        return f"Motivo: {'; '.join(item.reasons)}" if item.reasons else "Motivo: sem sinal objetivo de erro."

    def _mostrar_motivo(self) -> None:
        self.lbl_motivo.setText(self.motivo_selecionado())

    def mostrar_progresso(self, frase: str) -> None:
        """A frase de progresso. É a ponta do sinal do sumidouro, e roda na thread da janela."""
        self.lbl_progresso.setText(frase)

    def posicao_selecionada(self) -> int | None:
        linha = self.tabela.indexOfTopLevelItem(self.tabela.currentItem())
        if not 0 <= linha < len(self._posicoes):
            return None
        return self._posicoes[linha]

    def selecionar_posicao(self, posicao: int) -> None:
        if posicao not in self._posicoes:
            return
        alvo = self.tabela.topLevelItem(self._posicoes.index(posicao))
        if alvo is not None:
            self.tabela.setCurrentItem(alvo)

    # -------------------------------------------------------------------------------- gestos

    def abrir_selecionado(self) -> None:
        posicao = self.posicao_selecionada()
        if posicao is None:
            self.estado.emit("Selecione um item da fila.")
            return
        self.abriu.emit(self.queue.items[posicao], posicao)

    def abrir_proximo_pendente(self) -> None:
        """Atalho do ciclo de correção: pega o mais prioritário ainda não resolvido."""
        for posicao, item in enumerate(self.queue.items):
            if item.status == "pending":
                self.selecionar_posicao(posicao)
                self.abriu.emit(item, posicao)
                return
        self.estado.emit("Nenhum item pendente na fila.")

    def marcar_selecionado(self, status: str) -> None:
        posicao = self.posicao_selecionada()
        if posicao is None:
            self.estado.emit("Selecione um item da fila.")
            return
        self.queue.mark(posicao, status)  # type: ignore[arg-type]
        self.salvar_fila(quieto=True)
        self.refresh()
        self.estado.emit(f"Item {self.queue.items[posicao].label} marcado como {status}.")

    def aplicar_correcao(self, posicao: int, fen: str, lado: str) -> None:
        """Grava na fila a correção que o editor fez e marca o item como revisado."""
        if not 0 <= posicao < len(self.queue.items):
            return
        self.queue.update_fen(posicao, fen, lado)
        self.queue.mark(posicao, "done")
        self.salvar_fila(quieto=True)
        self.refresh()

    # ----------------------------------------------------------------------------- varredura

    def iniciar_varredura(self) -> None:
        """Pede **a** varredura do livro -- a mesma da Galeria, e a única que existe (S-119)."""
        if self._varrendo:
            # As duas vão para o rodapé (S-164): "já está rodando" é o que a zona de operação ao
            # lado mostra, e "abra um PDF antes" é um passo que falta -- nenhuma é uma decisão.
            self.estado.emit("Já existe uma varredura de fila em execução.")
            return
        if not self.receivers(self.pediu_varredura):
            self.estado.emit("Esta janela não tem de onde varrer o livro.")
            return
        self.pediu_varredura.emit()

    def cancelar_varredura(self) -> None:
        if self.receivers(self.pediu_cancelamento):
            self.pediu_cancelamento.emit()
            self.lbl_progresso.setText("Cancelando... (termina a página atual)")

    def sumidouro(self) -> SumidouroDeRevisao | None:
        """O coletor que monta a fila a partir da varredura do livro (S-119).

        Chamado pela Galeria **na thread da janela**, antes de a varredura começar: ele lê a
        configuração daqui e não toca disco nenhum -- o `labels.csv` só é lido quando o primeiro
        diagrama chega, que já é na thread da varredura (S-116).

        `None` quando não há PDF aberto: a Galeria segue varrendo para a aba dela, e a fila fica
        como estava.
        """
        pedido = None if self._pedido_de_varredura is None else self._pedido_de_varredura()
        if pedido is None:
            return None
        self._varrendo = True
        self.btn_varrer.setEnabled(False)
        self.btn_cancelar.setEnabled(True)
        self.lbl_progresso.setText("Varrendo o livro...")
        return SumidouroDeRevisao(self, pedido, cache_dir=self.cache_dir)

    def aplicar_varredura(
        self, nova: ReviewQueue, cancelada: bool, *, pages: Collection[int] | None = None
    ) -> None:
        if self.queue.items and self.queue.source_pdf == nova.source_pdf:
            # Revarredura não pode ressuscitar o que já foi revisado -- é o que `merge_queues`
            # garante. `pages` é o que a passada de fato visitou (S-119): a varredura retoma de
            # onde parou (S-120), e sem isso a fusão encurtaria a fila para as páginas novas.
            nova = merge_queues(self.queue, nova, pages=pages)
        self.queue = nova
        self.salvar_fila(quieto=True)
        self.refresh()
        sufixo = " (cancelada)" if cancelada else ""
        self.lbl_progresso.setText(f"Varredura concluída{sufixo}. {self.queue.summary()}")
        self.estado.emit(f"Fila de revisão pronta{sufixo}: {self.queue.summary()}")

    def terminar_varredura(self) -> None:
        self._varrendo = False
        self.btn_varrer.setEnabled(True)
        self.btn_cancelar.setEnabled(False)

    # ------------------------------------------------------------------------------- arquivo

    def salvar_fila(self, quieto: bool = False) -> None:
        try:
            self.queue.save(self.queue_path)
            if not quieto:
                self.estado.emit(f"Fila salva em {self.queue_path}.")
        except OSError as exc:
            logger.warning("Não foi possível salvar a fila de revisão: %s", exc)
            if not quieto:
                QMessageBox.critical(self, "Fila de revisão", f"Não foi possível salvar a fila:\n{exc}")

    def abrir_arquivo_de_fila(self) -> None:
        caminho, _filtro = QFileDialog.getOpenFileName(
            self,
            "Abrir fila de revisão",
            str(self.queue_path.parent),
            "JSON (*.json);;Todos (*.*)",
        )
        if not caminho:
            return
        self.queue_path = Path(caminho)
        self.queue = ReviewQueue.load(self.queue_path)
        self.queue.sort()
        self.refresh()
        self.estado.emit(f"Fila carregada de {self.queue_path}.")


_ = Qt  # noqa: B018 - mantém o import legível para quem estender este painel
