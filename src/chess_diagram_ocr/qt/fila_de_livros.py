"""A fila de PDFs varrida de dentro da janela, com barra por livro e Cancelar (S-546).

**Por que ele existe.** A varredura da biblioteca inteira existe desde a S-34 e a única porta dela
era `cvoff-batch`, um comando de terminal. Na janela dá para exportar **um** livro
(`qt/exportador.py`), escolhendo destino num diálogo a cada um -- e quem tem centenas de PDFs
abre o terminal ou não faz. Este módulo é a mesma `batch.run_batch`, com a fila na tela.

**Uma thread só, e não uma por livro.** É a decisão medida da S-34: a inferência do `torch` já
ocupa os núcleos disponíveis, então dois livros ao mesmo tempo disputariam os mesmos núcleos e
ainda carregariam dois modelos. `run_batch` é sequencial por dentro, e o que roda fora da linha
de eventos é **ela**, inteira, numa `Tarefa` -- o `QThread` de `qt/trabalho.py`.

**Os avisos vêm da thread de trabalho e só emitem.** `on_book_start`, `on_page` e `on_book_done`
são chamados dentro do `run_batch`; tocar widget ali derruba o processo sem exceção. Cada um
emite um sinal, e o slot do outro lado -- na thread da interface -- é que muda a `FilaDeLivros` e
redesenha a tabela. É a mesma forma de `qt/indice_da_base.py`.

**Cancelar para no fim do livro em curso, e não no fim da fila.** O `threading.Event` é conferido
antes de cada livro por `run_batch` e entre páginas por `save_pdf_positions_to_pgn` (S-24): o que
já saiu fica gravado, e o livro interrompido deixa o parcial que a próxima rodada retoma. Os
livros que nunca começaram viram `cancelado` na hora, porque ninguém vai voltar a eles sozinho.

**O que ele não decide.** As transições, as frases de cada linha, o resumo e as colunas são de
`ui/fila_de_livros.py`. Aqui é a fiação: sinal, thread, tabela, botões.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.batch import (
    BatchOptions,
    BatchReport,
    BookResult,
    find_pdfs,
    gravar_relatorios_de_qualidade,
    run_batch,
)
from chess_diagram_ocr.qt import tabela as tabela_qt
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.ui import estilos
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.fila_de_livros import (
    COLUNAS,
    PENDENTE,
    FilaDeLivros,
    LivroNaFila,
    estado_do_resultado,
    frase_de_resumo,
    linha_da_tabela,
)

logger = logging.getLogger(__name__)

__all__ = ["DialogoDaFila", "VarreduraDeLivros", "abrir_fila_de_livros"]

POR_MIL = 1000
"""A escala das duas barras. Mil passos bastam para uma fila de centenas de livros andar sem
saltar, e cabem num `int` de `QProgressBar` sem conversão."""

Executor = Callable[..., BatchReport]
"""A varredura em si. É `batch.run_batch`, e é parâmetro para o teste poder pôr uma varredura de
mentira no lugar: montar a fila de verdade exigiria PDF, modelo `.pt` e minutos, e o que este
módulo tem para afirmar é a fiação -- sinal, thread, cancelamento --, não a leitura."""


class VarreduraDeLivros(QObject):
    """Roda `run_batch` numa thread e conta o andamento por sinal.

    `mudou` diz "a fila mudou, redesenhe" e é o único sinal de que a tabela precisa: quem quer
    saber *o que* mudou lê a `fila`, que é o modelo. `terminou(BatchReport)` e `falhou(mensagem,
    exceção)` são os dois fins possíveis, e exatamente um deles chega.
    """

    mudou = pyqtSignal()
    terminou = pyqtSignal(object)
    falhou = pyqtSignal(str, object)

    _comecou_livro = pyqtSignal(int)
    _andou = pyqtSignal(int, int, int)
    _acabou_livro = pyqtSignal(int, object)
    """Os três internos. São emitidos **na thread de trabalho** e recebidos na da interface: é a
    travessia, e por isso não são chamada direta."""

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        servico: Any = None,
        busy: BusyRegistry | None = None,
        executor: Executor = run_batch,
    ) -> None:
        """`servico` empresta o modelo sob o lock da S-31, um livro de cada vez (S-57).

        Sem ele cada livro carrega o próprio `.pt` -- que é o caminho do `cvoff-batch` e está
        certo lá, onde não há treino concorrente. Na janela há: o treino reescreve o mesmo
        arquivo que a fila estaria lendo por horas.
        """
        super().__init__(parent)
        self.fila = FilaDeLivros()
        self.relatorio: BatchReport | None = None
        """O que a última rodada fez; `None` enquanto nenhuma terminou."""
        self._tarefa: Tarefa | None = None
        self._cancelar = threading.Event()
        self._servico = servico
        self._busy = busy
        self._token: BusyToken | None = None
        self._executor = executor
        self._linhas: list[int] = []
        """Índice na fila de cada livro entregue ao `run_batch`, na ordem em que ele os recebeu."""
        self._ordem_atual = -1
        """Em que livro da lista entregue a varredura está, contado de zero.

        **É o único estado que as duas threads tocam**, e é um `int`: a de trabalho escreve em
        `_relatar_comeco` e lê nos outros dois avisos, a da interface não o toca. Um `int` é
        atribuído de uma vez em CPython, e é por isso que ele pode ser este e não um `Lock`. Ler a
        própria `FilaDeLivros` da thread de trabalho -- que era a forma óbvia -- seria ler uma
        lista que a interface reescreve, e não há nada que acuse isso quando dá errado.
        """

        self._comecou_livro.connect(self._marcar_comeco)
        self._andou.connect(self._marcar_avanco)
        self._acabou_livro.connect(self._marcar_fim)

    @property
    def ocupado(self) -> bool:
        return self._tarefa is not None

    def acrescentar(self, pdfs: Sequence[Path]) -> list[Path]:
        """Põe livros na fila. Devolve os que entraram -- repetido não entra duas vezes."""
        entraram = self.fila.acrescentar(pdfs)
        if entraram:
            self.mudou.emit()
        return entraram

    def remover(self, indices: Sequence[int]) -> list[Path]:
        """Tira livros da fila. Devolve os que saíram; vazio com a varredura em curso.

        **Recusada enquanto a varredura roda**, e não é excesso de zelo: a thread de trabalho
        guarda em `_linhas` a posição de cada livro que entregou ao `run_batch`, e tirar uma
        linha do meio faria o resultado do livro seguinte chegar na linha de outro. O gesto é de
        antes de começar -- que é quando a pessoa vê que acrescentou a pasta errada.
        """
        if self._tarefa is not None:
            return []
        sairam = self.fila.remover(indices)
        if sairam:
            self.mudou.emit()
        return sairam

    def iniciar(self, destino: Path, opcoes: BatchOptions | None = None) -> bool:
        """Começa a varredura dos pendentes. Falso se já há uma em curso, ou se não há pendente.

        Duas rodadas ao mesmo tempo escreveriam no mesmo PGN e disputariam os mesmos núcleos --
        é a recusa do `IndexadorDaBase`, pelo mesmo motivo.
        """
        if self._tarefa is not None:
            return False
        pendentes = [(indice, livro.pdf) for indice, livro in enumerate(self.fila) if livro.estado == PENDENTE]
        if not pendentes:
            return False

        self._linhas = [indice for indice, _pdf in pendentes]
        self._ordem_atual = -1
        livros = [pdf for _indice, pdf in pendentes]
        self._cancelar = threading.Event()
        self.relatorio = None
        cancelar = self._cancelar
        executor = self._executor
        configuracao = opcoes or BatchOptions()
        sessao = None
        if self._servico is not None:
            sessao = self._servico.model_session

        def _trabalho() -> BatchReport:
            return executor(
                livros,
                destino,
                options=configuracao,
                on_book_start=self._relatar_comeco,
                on_book_done=self._relatar_fim,
                on_page=self._relatar_pagina,
                session_factory=sessao,
                cancel_event=cancelar,
            )

        tarefa = Tarefa(_trabalho, parent=self, nome="fila de livros")
        tarefa.pronto.connect(self._pronto)
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._terminou)
        self._registrar_ocupado(len(livros))
        self._tarefa = tarefa
        tarefa.start()
        return True

    def cancelar(self) -> None:
        """Pede parada. O livro em curso termina a página e devolve o que já saiu (S-24).

        Os pendentes viram `cancelado` **agora**, e não quando a thread voltar: eles nunca vão
        começar, e deixá-los como "na fila" prometeria um trabalho que não vai acontecer.
        """
        self._cancelar.set()
        if self.fila.cancelar_restantes():
            self.mudou.emit()

    def esperar(self, espera_ms: int) -> bool:
        """Espera a rodada em curso terminar. Devolve se terminou."""
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(espera_ms))

    # --------------------------------------------------------------- da thread de trabalho

    def _relatar_comeco(self, _pdf: Path, indice: int, _total: int) -> None:
        self._ordem_atual = indice - 1
        self._comecou_livro.emit(self._ordem_atual)

    def _relatar_pagina(self, _pdf: Path, feitas: int, total: int, _diagramas: int) -> None:
        self._andou.emit(self._ordem_atual, feitas, total)

    def _relatar_fim(self, resultado: BookResult) -> None:
        self._acabou_livro.emit(self._ordem_atual, resultado)

    # ----------------------------------------------------------------- na thread da interface

    def _linha_de(self, ordem: int) -> int | None:
        if 0 <= ordem < len(self._linhas):
            return self._linhas[ordem]
        return None

    def _marcar_comeco(self, ordem: int) -> None:
        linha = self._linha_de(ordem)
        if linha is None:
            return
        # Um livro que ja foi cancelado (a fila parou antes de a thread chegar nele) nao volta a
        # `lendo`: a transicao recusaria, e uma excecao dentro de um slot derruba o processo.
        if self.fila[linha].estado == PENDENTE:
            self.fila.comecar(linha)
            self.mudou.emit()

    def _marcar_avanco(self, ordem: int, feitas: int, total: int) -> None:
        linha = self._linha_de(ordem)
        if linha is None:
            return
        self.fila.avancar(linha, feitas, total)
        self.mudou.emit()

    def _marcar_fim(self, ordem: int, resultado: Any) -> None:
        linha = self._linha_de(ordem)
        if linha is None or self.fila[linha].terminou:
            return
        self.fila.concluir(
            linha,
            estado_do_resultado(resultado.status),
            paginas=resultado.pages,
            diagramas=resultado.total_diagrams,
            exportados=resultado.accepted,
            ilegais=resultado.rejected,
            segundos=resultado.elapsed_s,
            erro=resultado.error,
        )
        self.mudou.emit()

    def _pronto(self, relatorio: Any) -> None:
        self.relatorio = relatorio
        self.terminou.emit(relatorio)

    def _falhou(self, mensagem: str, excecao: object) -> None:
        logger.warning("A fila de livros falhou: %s", mensagem)
        self.falhou.emit(mensagem, excecao)

    def _terminou(self) -> None:
        self._soltar_ocupado()
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.deleteLater()
        self.mudou.emit()

    def _registrar_ocupado(self, quantos: int) -> None:
        if self._busy is None:
            return
        self._token = self._busy.register(
            "fila de livros",
            # Cada livro pronto tem o PGN no disco, e o livro em curso tem o parcial da S-24:
            # fechar custa tempo, não trabalho.
            loses_work=False,
            cancellable=True,
            detail=f"{quantos} livro(s)",
            total=POR_MIL,
            cancel=self.cancelar,
        )

    def _soltar_ocupado(self) -> None:
        if self._token is not None:
            self._token.release()
            self._token = None


class DialogoDaFila(QDialog):
    """A fila na tela: tabela, duas barras e três botões.

    **Duas barras, e não uma.** A do conjunto responde "quanto falta para acabar" e a do livro
    responde "isto ainda está andando?" -- e num livro de 2.612 páginas a segunda é a única que
    se mexe por dezenas de minutos. Uma barra só teria de escolher qual das duas perguntas
    responder, e a escolhida seria a errada metade do tempo.

    Não é modal à aplicação nem à janela: uma varredura de horas é justamente o que se deixa
    rodando enquanto se faz outra coisa (S-164), e trancar a janela faria dela uma operação que
    não pode ser deixada só.

    **Fechar o diálogo não para a fila**, e quem o destrói tem de esperar a thread antes -- um
    `QThread` destruído rodando derruba o processo sem exceção. Ele não é `WA_DeleteOnClose`
    justamente por isso: fechar guarda a tela, e Cancelar é que para a varredura.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        varredura: VarreduraDeLivros | None = None,
        destino: Path | None = None,
        pasta_inicial: Path | None = None,
        opcoes: BatchOptions | None = None,
        relatorios: bool = True,
    ) -> None:
        super().__init__(parent)
        self.varredura = varredura or VarreduraDeLivros(self)
        self._destino = Path(destino) if destino is not None else Path("PGN")
        self._pasta_inicial = pasta_inicial
        self._opcoes = opcoes or BatchOptions()
        self._relatorios = relatorios
        """Gravar o relatório de qualidade por livro no fim da fila (S-548).

        Ligado por padrão porque o relatório custa um `stat` por livro e responde a pergunta que
        a fila deixa em aberto -- *este livro foi bem?* --, e desligável porque quem varre para
        conferir uma coisa só não quer cinquenta JSON ao lado dos PGN."""
        self.gravados: list[Path] = []
        """Os relatórios de qualidade da última rodada. Vazio antes da primeira."""
        self._parada = ""
        """A frase de "a fila inteira caiu", guardada e não escrita direto no rótulo.

        Escrevê-la direto durava um instante: o `finished` da tarefa chega **depois** do sinal de
        falha e redesenha o resumo por cima. Guardá-la faz de `redesenhar` a única voz do rótulo,
        que é a mesma regra de a tabela ser reescrita inteira.
        """
        self.setWindowTitle("Fila de livros")
        self.setMinimumWidth(760)

        fora = QVBoxLayout(self)
        self.tabela = tabela_qt.montar(self, COLUNAS)
        # Marcar mais de uma linha: quem apontou a pasta errada tira os dez livros de uma vez, e
        # não um a um. A tabela **não** é ordenável pelo cabeçalho: a ordem dela é a de execução,
        # e reordenar faria o livro em leitura saltar de lugar enquanto a barra anda.
        self.tabela.setSelectionMode(tabela_qt.TabelaQt.SelectionMode.ExtendedSelection)
        fora.addWidget(self.tabela, 1)

        self.barra_do_livro = QProgressBar(self)
        self.barra_do_livro.setRange(0, POR_MIL)
        self.barra_do_livro.setFormat("%p% do livro")
        fora.addWidget(self.barra_do_livro)

        self.barra_do_conjunto = QProgressBar(self)
        self.barra_do_conjunto.setRange(0, POR_MIL)
        self.barra_do_conjunto.setFormat("%p% da fila")
        fora.addWidget(self.barra_do_conjunto)

        self.resumo = QLabel("", self)
        self.resumo.setWordWrap(True)
        self.resumo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fora.addWidget(self.resumo)

        linha = QHBoxLayout()
        self.botao_acrescentar = QPushButton("Acrescentar livros…", self)
        self.botao_tirar = QPushButton("Tirar da fila", self)
        self.botao_comecar = QPushButton("Começar", self)
        self.botao_cancelar = QPushButton("Cancelar", self)
        tema.aplicar_papel(self.botao_acrescentar, estilos.NEUTRO)
        tema.aplicar_papel(self.botao_tirar, estilos.NEUTRO)
        tema.aplicar_papel(self.botao_comecar, estilos.PRIMARIO)
        tema.aplicar_papel(self.botao_cancelar, estilos.NEUTRO)
        estilos.conferir_barra(
            [estilos.NEUTRO, estilos.NEUTRO, estilos.PRIMARIO, estilos.NEUTRO], onde="a fila de livros"
        )
        for botao in (self.botao_acrescentar, self.botao_tirar, self.botao_comecar, self.botao_cancelar):
            linha.addWidget(botao)
        linha.addStretch(1)
        fora.addLayout(linha)

        self.botao_acrescentar.clicked.connect(self.escolher_livros)
        self.botao_tirar.clicked.connect(self.tirar_selecionado)
        self.botao_comecar.clicked.connect(self.comecar)
        self.botao_cancelar.clicked.connect(self.varredura.cancelar)
        self.varredura.mudou.connect(self.redesenhar)
        self.varredura.falhou.connect(self._deu_errado)
        # Ligado antes de `redesenhar`: o Qt chama os slots na ordem em que foram ligados, e o
        # que grava os relatorios tem de terminar antes de o resumo dizer onde eles estao.
        self.varredura.terminou.connect(self._gravar_relatorios)
        self.redesenhar()

    # ------------------------------------------------------------------------------ gestos

    def escolher_livros(self) -> None:
        """Pergunta os PDFs. Uma pasta escolhida entra com todos os livros dela (S-34)."""
        nomes, _filtro = QFileDialog.getOpenFileNames(
            self,
            "Acrescentar livros à fila",
            str(self._pasta_inicial) if self._pasta_inicial else "",
            "PDF (*.pdf);;Todos (*.*)",
        )
        if nomes:
            self.varredura.acrescentar([Path(nome) for nome in nomes])

    def tirar_selecionado(self) -> list[Path]:
        """Tira da fila os livros marcados na tabela. Devolve os que saíram.

        Acrescentar era irreversível até aqui: uma pasta escolhida entra com todos os PDFs dela
        (S-34), e quem apontasse a pasta errada tinha de fechar o diálogo e montar a fila de novo.
        A decisão de *quem pode sair* é de `ui/fila_de_livros.FilaDeLivros.remover`; aqui só se
        pergunta à tabela quais linhas estão marcadas.
        """
        marcados = [self.tabela.posicao_de(item) for item in self.tabela.selectedItems()]
        return self.varredura.remover([posicao for posicao in marcados if posicao >= 0])

    def acrescentar_pasta(self, pasta: Path) -> list[Path]:
        """Todos os PDFs de uma pasta, em ordem de nome. É o `find_pdfs` da S-34."""
        return self.varredura.acrescentar(find_pdfs(Path(pasta)))

    def comecar(self) -> bool:
        comecou = self.varredura.iniciar(self._destino, self._opcoes)
        if comecou:
            self._parada = ""
            self.gravados = []
            self.redesenhar()
        return comecou

    def _gravar_relatorios(self, relatorio: Any) -> None:
        """Um JSON de qualidade por livro, ao fim da fila (S-548).

        No fim e não a cada livro: o `BatchReport` é o mesmo objeto o tempo todo, e gravar
        cinquenta arquivos cinquenta vezes escreveria 1.275 arquivos para entregar cinquenta. O
        que protege contra a interrupção é o `--report` da própria varredura, que já é gravado a
        cada livro (S-34).
        """
        if not self._relatorios or not isinstance(relatorio, BatchReport):
            return
        self.gravados = gravar_relatorios_de_qualidade(relatorio, self._opcoes, self._destino)

    # ---------------------------------------------------------------------------- o desenho

    def redesenhar(self) -> None:
        """Reescreve a tabela, as duas barras, o resumo e o que está ligado.

        A tabela inteira, e não a linha que mudou: são dezenas de linhas de seis células curtas,
        e guardar um índice por livro para atualizar uma célula seria o estado que diverge
        quando a fila cresce no meio -- que é justamente o gesto de "Acrescentar livros…".
        """
        self.tabela.preencher([linha_da_tabela(livro) for livro in self.varredura.fila])
        self.barra_do_conjunto.setValue(int(self.varredura.fila.fracao * POR_MIL))
        self.barra_do_livro.setValue(int(self._fracao_do_livro() * POR_MIL))
        partes = [self._parada, frase_de_resumo(self.varredura.fila)]
        if self.gravados:
            # O caminho vai inteiro: quem acabou de varrer cinquenta livros precisa saber onde
            # procurar, e "na pasta de saída" não é um caminho.
            partes.append(f"Relatório de qualidade de {len(self.gravados)} livro(s) em {self._destino}.")
        self.resumo.setText(" ".join(parte for parte in partes if parte))
        rodando = self.varredura.ocupado
        self.botao_comecar.setEnabled(not rodando and bool(self.varredura.fila.pendentes))
        self.botao_cancelar.setEnabled(rodando)
        self.botao_acrescentar.setEnabled(True)
        # Tirar só antes de começar: com a varredura em curso, a posição de cada livro é o que
        # liga o resultado que chega da thread à linha da tabela. Ver `VarreduraDeLivros.remover`.
        self.botao_tirar.setEnabled(not rodando and bool(len(self.varredura.fila)))

    def _fracao_do_livro(self) -> float:
        atual = self.varredura.fila.em_curso
        if atual is None:
            return 0.0
        livro: LivroNaFila = self.varredura.fila[atual]
        return livro.fracao

    def _deu_errado(self, mensagem: str, _excecao: object) -> None:
        """A falha da fila inteira vai para o resumo, e não para uma caixa.

        Um livro que falha não derruba a varredura (S-34): o que chega aqui é a `run_batch`
        inteira ter caído, e mesmo isso não vale uma caixa modal em cima de uma operação que
        alguém deixou rodando -- é o critério da S-164.
        """
        self._parada = f"A fila parou: {mensagem}"
        self.redesenhar()


def abrir_fila_de_livros(
    parent: QWidget | None,
    *,
    servico: Any = None,
    busy: BusyRegistry | None = None,
    destino: Path | None = None,
    pasta_inicial: Path | None = None,
    opcoes: BatchOptions | None = None,
    mostrar: bool = True,
) -> DialogoDaFila:
    """Monta o diálogo com a varredura ligada ao serviço e o devolve.

    Quem o chama é um `connect` no menu ou na barra -- e nada mais: o módulo não conhece painel
    nenhum, pela mesma razão de `qt/indice_da_base.py`.

    `mostrar=False` não chama `show()`; é o caminho do teste sob `offscreen`.
    """
    varredura = VarreduraDeLivros(parent, servico=servico, busy=busy)
    dialogo = DialogoDaFila(
        parent, varredura=varredura, destino=destino, pasta_inicial=pasta_inicial, opcoes=opcoes
    )
    varredura.setParent(dialogo)
    if mostrar:
        dialogo.show()
    return dialogo
