"""Quais diagramas de um livro já têm amostra gravada -- lido **fora** da thread da janela (F9-C2).

**O defeito, com a pilha que o instrumento devolveu.** O arnês `caissa.ui.audit.bloqueio` mediu a
abertura de um livro em **250 ms** de thread da interface parada, e a pilha do pior travamento não
é a que o relatório do ciclo 1 publicou:

    janela.py:987 abrir_pdf → painel_do_pdf.py:407 load_pdf → janela.py:952 _abriu_livro
      → janela.py:981 _carregar_marcas_salvas → labels.py:357 read → labels.py:380 _load_rows
      → csv.py:111 __next__

Não é o PyMuPDF: é o `csv` lendo o `labels.csv` inteiro para responder uma pergunta sobre **um**
livro. O ciclo 1 propôs mover o rasterizador para a thread de trabalho, e o rasterizador não é o
pior caso -- é o segundo.

**Por que uma classe e não um `Tarefa` solto no ponto de chamada.** Trocar de livro antes de a
leitura anterior terminar é o caso normal de quem procura o livro certo em três tentativas, e uma
resposta que chega atrasada não pode sobrescrever a pergunta de agora. `LeitorDeMarcas` guarda o
livro que pediu e **descarta a resposta que não é dele** -- o mesmo contrato de
`qt/trabalho.DeteccaoDeFundo`, e a mesma razão.

**O estado enquanto a resposta não chegou é "nenhuma marca", e isso é honesto.** A alternativa
seria manter as marcas do livro anterior por 250 ms, que é desenhar afirmação errada sobre o
livro novo. Vazio diz "ainda não sei", e a resposta chega antes de a pessoa conseguir ler a
primeira página.

---

**A terceira porta do mesmo `csv`, fechada no F9-C3.** O ciclo 2 tirou o `labels.csv` da abertura
do livro (acima) e do rótulo da aba (`painel_do_dataset.contagem_de_amostras`) e deixou passar a
que dispara **a cada gesto**: `janela._aviso_de_treino`, chamado de `campo.atualizar()` a cada
`_pagina_apareceu`, construía um `LabelStore` novo e lia as 5.431 linhas na thread da janela.
Medido com e sem a leitura, seis viradas de cada lado, mediana: **166,2 ms contra 115,7 ms --
50,5 ms por virada, 30 % dela, 3,2x o portão de 16 ms sozinha** (`custo_aviso.py`, ciclo 3). E o
custo cresce com o acervo: são 20 colunas × 5.431 linhas normalizadas a cada virada.

`paginas_com_amostra_de_treino` é a **mesma técnica** de `contagem_de_amostras`: a resposta é
guardada por `(tamanho, mtime)` dos **dois** arquivos que a produzem. Não é thread nem memória de
instância -- `LabelStore(csv).read()` construía um objeto novo a cada chamada, o que matava
qualquer memória de instância por construção.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from chess_diagram_ocr.labels import LabelStore, pages_with_training_samples, saved_diagrams_by_page
from chess_diagram_ocr.processo_de_trabalho import processo_de_trabalho
from chess_diagram_ocr.qt.trabalho import Tarefa, manter_viva
from chess_diagram_ocr.splits import load_splits
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken

logger = logging.getLogger(__name__)

__all__ = [
    "LeitorDeMarcas",
    "amostras_de_treino_guardadas",
    "ler_marcas_e_treino",
    "limpar_memoria_de_treino",
    "marcas_do_livro",
    "paginas_com_amostra_de_treino",
]

_Marca = tuple[str, int, int]
"""`(caminho, tamanho, mtime em ns)` de um arquivo -- a chave de invalidação da S-116/F9-C2."""

_TREINO: tuple[tuple[_Marca, _Marca], dict[tuple[str, int], int]] | None = None
"""A última resposta de `paginas_com_amostra_de_treino`, com a marca dos dois arquivos.

**Uma entrada só, e de módulo em vez de instância.** Uma só porque a pergunta é sempre sobre o
mesmo par de arquivos -- há um `labels.csv` por sessão --, e guardar mais seria memória que
ninguém lê. De módulo porque quem pergunta (`janela._aviso_de_treino`) responde a um método de
painel e não guarda estado de dataset; `limpar_memoria_de_treino()` existe para o teste, que
precisa de duas respostas diferentes para o mesmo caminho."""


def _marca_de(caminho: Path) -> _Marca | None:
    """`(caminho, tamanho, mtime)` -- ou `None` quando o arquivo não existe."""
    try:
        estado = caminho.stat()
    except OSError:
        return None
    return (str(caminho), estado.st_size, estado.st_mtime_ns)


def limpar_memoria_de_treino() -> None:
    """Esquece a resposta guardada. Existe para o teste; o produto invalida pela `mtime`."""
    global _TREINO
    _TREINO = None


def paginas_com_amostra_de_treino(csv: Path, splits: Path) -> dict[tuple[str, int], int]:
    """`{(livro, página em base 0): quantas amostras de treino}` -- lido uma vez por gravação.

    O par `(tamanho, mtime)` dos dois arquivos é o mesmo critério de invalidação de
    `ui/games_cache.py` e de `contagem_de_amostras`, e ele erra do lado seguro: um arquivo
    reescrito com o mesmo tamanho **e** o mesmo mtime é um arquivo que o sistema de arquivos diz
    não ter mudado. Gravar uma amostra muda os dois, e a virada seguinte relê.

    Arquivo ausente devolve vazio **sem guardar**: um `labels.csv` que ainda não existe é uma
    resposta que muda no instante em que alguém grava a primeira amostra, e a `mtime` de um
    arquivo inexistente não tem como avisar disso.
    """
    global _TREINO
    marca_do_csv, marca_dos_splits = _marca_de(Path(csv)), _marca_de(Path(splits))
    if marca_do_csv is None or marca_dos_splits is None:
        return {}
    chave = (marca_do_csv, marca_dos_splits)
    if _TREINO is not None and _TREINO[0] == chave:
        return _TREINO[1]
    try:
        paginas = pages_with_training_samples(LabelStore(Path(csv)).read(), load_splits(Path(splits)))
    except (OSError, ValueError) as erro:
        # Aviso ausente é melhor que janela quebrada: é informação lateral (S-97).
        logger.debug("Não foi possível checar amostras de treino da página: %s", erro)
        return {}
    _TREINO = (chave, paginas)
    return paginas


def amostras_de_treino_guardadas(csv: Path, splits: Path) -> dict[tuple[str, int], int] | None:
    """A resposta de `paginas_com_amostra_de_treino` **se já está guardada e vale**; senão `None`.

    É o que a thread da janela pode perguntar (OCR_UI passo 15): a leitura fria custava 50 ms
    na abertura do livro, e ela agora roda no processo de trabalho junto com as marcas
    (`ler_marcas_e_treino`). `None` é "ainda não sei", e quem recebe escreve o aviso quando a
    resposta chegar.
    """
    marca_do_csv, marca_dos_splits = _marca_de(Path(csv)), _marca_de(Path(splits))
    if marca_do_csv is None or marca_dos_splits is None:
        return {}
    chave = (marca_do_csv, marca_dos_splits)
    if _TREINO is not None and _TREINO[0] == chave:
        return _TREINO[1]
    return None


def _guardar_treino(chave: object, paginas: object) -> None:
    global _TREINO
    if isinstance(chave, tuple) and isinstance(paginas, dict):
        _TREINO = (chave, paginas)  # type: ignore[assignment]


def ler_marcas_e_treino(
    csv: Path, splits: Path, livro: str
) -> tuple[dict[int, set[int]], tuple[_Marca, _Marca] | None, dict[tuple[str, int], int]]:
    """As marcas do livro **e** as páginas com amostra de treino, numa passada só pelo CSV.

    Função de módulo, com argumentos simples, porque roda no processo de trabalho: as duas
    perguntas leem o mesmo `labels.csv`, e lê-lo uma vez fora do processo da janela é o que tira
    de lá os 50 ms da abertura e a disputa pelo GIL que uma thread deixaria.
    """
    marca_do_csv, marca_dos_splits = _marca_de(Path(csv)), _marca_de(Path(splits))
    try:
        entradas = LabelStore(Path(csv)).read()
    except OSError as exc:
        logger.warning("Marcas de salvo indisponíveis (%s): %s", csv, exc)
        return ({}, None, {})
    marcas = saved_diagrams_by_page(entradas, livro)
    if marca_do_csv is None or marca_dos_splits is None:
        return (marcas, None, {})
    try:
        treino = pages_with_training_samples(entradas, load_splits(Path(splits)))
    except (OSError, ValueError) as erro:
        logger.debug("Não foi possível checar amostras de treino da página: %s", erro)
        return (marcas, None, {})
    return (marcas, (marca_do_csv, marca_dos_splits), treino)


def marcas_do_livro(csv: Path, livro: str) -> dict[int, set[int]]:
    """As marcas de `livro` no CSV. **Pura o bastante para rodar em qualquer thread.**

    Não toca widget nem `QObject`: é só disco e dicionário, que é o requisito para ela poder ser
    o corpo de uma `Tarefa`. CSV ausente devolve vazio -- um checkout sem dados não é falha, e
    ali a resposta honesta é "nenhuma".
    """
    try:
        return saved_diagrams_by_page(LabelStore(csv).read(), livro)
    except OSError as exc:
        logger.warning("Marcas de salvo indisponíveis (%s): %s", csv, exc)
        return {}


class LeitorDeMarcas(QObject):
    """Lê as marcas de um livro numa thread e entrega em `prontas`. Ver o cabeçalho."""

    prontas = pyqtSignal(str, object)
    """`(nome do livro, {página: {índices}})`. O nome vai junto para o receptor conferir."""

    def __init__(
        self,
        csv: Callable[[], Path],
        parent: QObject | None = None,
        *,
        ocupado: BusyRegistry | None = None,
        splits: Callable[[], Path] | None = None,
        em_processo: bool = True,
    ) -> None:
        super().__init__(parent)
        self._csv = csv
        self._splits = splits if splits is not None else (lambda: csv().parent / "splits.csv")
        self._em_processo = em_processo
        """Se a leitura roda no processo de trabalho (o produto) ou na própria thread (testes)."""
        self._tarefa: Tarefa | None = None
        self._pedido = ""
        self._ocupado = ocupado
        self._ficha: BusyToken | None = None
        self._desistiu = False
        """A pessoa cancelou pelo rodapé. Ver `_cancelar`."""

    def pedir(self, livro: Path) -> None:
        """Começa a leitura das marcas daquele livro. Substitui um pedido em curso."""
        self._pedido = livro.name
        caminho, splits = self._csv(), self._splits()
        nome = livro.name
        em_processo = self._em_processo

        def ler() -> object:
            if em_processo:
                return processo_de_trabalho().executar(ler_marcas_e_treino, caminho, splits, nome)
            return ler_marcas_e_treino(caminho, splits, nome)

        # **Sem pai**, e a referência viva é de `qt/trabalho.manter_viva`: uma `QThread` filha de
        # um widget é destruída com ele, e o destrutor aborta o processo se a thread ainda roda.
        tarefa = manter_viva(Tarefa(ler, nome="marcas salvas"))
        tarefa.pronto.connect(lambda resultado, quem=nome: self._chegou(quem, resultado))
        tarefa.falhou.connect(lambda mensagem, _exc, quem=nome: self._falhou(quem, mensagem))
        self._tarefa = tarefa
        self._registrar(nome)
        tarefa.start()

    # ------------------------------------------------------------------ o rodapé sabe disto

    def _registrar(self, livro: str) -> None:
        """Põe a leitura no `BusyRegistry` -- o que faz o rodapé falar dela (F9-C3).

        **Por que isto passou dois ciclos sem existir.** A entrada desta thread em
        `test_busy.SEM_REGISTRO` responde *"perde trabalho ao fechar a janela?"* -- não, é leitura
        --, e ela foi usada para responder *"precisa de indicação de progresso?"*, que é outra
        pergunta. O resultado media: com a leitura correndo, o rodapé escrevia "Lendo o
        dataset..." na zona de mensagem e a barra ao lado ficava em **0 de 100 com o `Cancelar`
        desabilitado**, porque o registro é o único caminho pelo qual o rodapé fica sabendo.

        **Indeterminada, e o motivo é medido e não preguiça.** O total de linhas é conhecido
        (`painel_do_dataset.contagem_de_amostras`), e mesmo assim `total=` fica em zero: quem
        conta as linhas é `LabelStore._load_rows`, dentro de `labels.py`, que não tem callback de
        progresso -- e uma barra **determinada** que ninguém pode fazer andar fica parada em 0 %
        até o fim, que é exatamente o defeito bloqueante nº 2 do ciclo 3 com outro nome. O
        `detail` diz o livro; a barra anda porque não sabe onde está, que é a verdade.
        """
        self._desistiu = False
        if self._ocupado is None:
            return
        self._ficha = self._ocupado.register(
            "marcas salvas do livro",
            # Leitura: fechar a janela no meio não perde nada, e a próxima abertura refaz a
            # pergunta. É o mesmo motivo que estava escrito em `test_busy.SEM_REGISTRO`.
            loses_work=False,
            cancellable=True,
            cancel=self._cancelar,
            detail=livro,
        )

    def _cancelar(self) -> None:
        """Desiste da leitura: a resposta que chegar depois é descartada.

        **O que este cancelamento faz, dito sem folga.** Ele devolve a janela agora e joga fora a
        resposta; a leitura do arquivo termina sozinha alguns milissegundos depois, porque
        `LabelStore.read()` não tem ponto de interrupção público e `labels.py` não é desta frente.
        O que o botão promete -- *"parar limpo"* -- é o que ele entrega: nada é gravado, nada fica
        pela metade, e a janela deixa de esperar.
        """
        self._desistiu = True
        self._soltar()

    def _soltar(self) -> None:
        ficha, self._ficha = self._ficha, None
        if ficha is not None:
            ficha.release()

    def _chegou(self, livro: str, resultado: object) -> None:
        self._soltar()
        marcas, chave, treino = resultado if isinstance(resultado, tuple) else (resultado, None, {})
        # As amostras de treino valem para qualquer livro: são do CSV, e a chave é dele.
        _guardar_treino(chave, treino)
        if livro != self._pedido or self._desistiu:
            # A pessoa já abriu outro livro, ou desistiu. Ver o cabeçalho e `_cancelar`: a
            # resposta que não é da pergunta de agora é descartada.
            return
        self.prontas.emit(livro, marcas)

    def _falhou(self, livro: str, mensagem: str) -> None:
        logger.warning("Marcas de %s não lidas (%s).", livro, mensagem)
        self._soltar()
        if livro == self._pedido and not self._desistiu:
            self.prontas.emit(livro, {})

    def esperar(self, ms: int = 2000) -> bool:
        """Espera a leitura em curso terminar. Existe para o fechamento e para o teste."""
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(ms))
