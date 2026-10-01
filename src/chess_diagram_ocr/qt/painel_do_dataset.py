"""A aba "Dataset" no segundo frontend: listar, filtrar, recorrigir e remover (S-23/S-503).

**Toda a lógica de dados está em `dataset_browser.py`**, que é puro e testável -- o que é
legalidade, o que é duplicata, o que cada filtro deixa passar, e o que remover ou pôr de
quarentena significa no CSV. O que a tela mostra está em `ui/resumo_do_dataset.py` desde a S-503:
as oito colunas, a página de 200 linhas, a célula de cada amostra e os dois textos de estatística.
Este arquivo escreve o widget e nada mais.

**A separação não é estética.** Os 100 rótulos ilegais que a Fase 1 mediu precisam poder ser
corrigidos *pela interface*, e esse é o critério de aceite da S-23 -- se a regra de "o que é
ilegal" morasse no widget, não haveria como testá-la. E se o texto da estatística morasse em dois
widgets, as duas janelas passariam a discordar sobre quanto do dataset é a classe `p`.

---

**Três diferenças do Qt, e as três são de mecanismo.**

1. **A preguiça da S-116 é `showEvent` e não `<Map>`.** O sinal é o mesmo -- "a pessoa está
   olhando o Dataset agora" --, e a razão de ele existir é a medição: `load_rows` custa 689 ms
   sobre 3.936 linhas, e o `Ctrl+S` chamava isso a cada amostra gravada **mesmo com a aba nunca
   aberta**. Ver `showEvent`.
2. **A pergunta de três respostas não existe no Qt.** `messagebox.askyesnocancel` devolve
   `True`/`False`/`None`, e é assim que a remoção pergunta "apago o PNG também?". Um
   `QMessageBox` com `Yes|No|Cancel` responde o mesmo, mas os botões precisam ser nomeados: "Sim"
   e "Não" sozinhos, numa pergunta que já é "remover?", leem-se como confirmar e cancelar -- e a
   pessoa que quisesse preservar o PNG apertaria "Não" achando que estava desistindo. Ver
   `remover_selecionadas`.
3. **A thread da detecção de duplicatas fala por sinal.** São 3.195 imagens de 800×800, e o
   resultado chega de outra thread; tocar num widget de lá derruba o processo.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from dataclasses import fields
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.audit import find_duplicate_groups
from chess_diagram_ocr.dataset_browser import (
    DatasetRow,
    delete_rows,
    filter_rows,
    load_rows,
    page_after_change,
    quarantine_rows,
)
from chess_diagram_ocr.processo_de_trabalho import processo_de_trabalho
from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.tabela import TabelaQt
from chess_diagram_ocr.qt.trabalho import Tarefa, manter_viva
from chess_diagram_ocr.qt.vazio import EstadoVazio
from chess_diagram_ocr.ui import espaco, estilos, strings, tipografia
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.resumo_do_dataset import (
    COLUNAS,
    LEGALITY_CHOICES,
    PAGE_SIZE,
    SPLIT_CHOICES,
    TODOS,
    celulas,
    frase_de_pagina,
    linha_de_estatisticas,
    paginas,
    texto_de_estatisticas,
)

logger = logging.getLogger(__name__)

__all__ = ["CANCELADA", "PASSO_DO_PROGRESSO", "JanelaDeEstatisticas", "PainelDoDataset"]

CANCELADA = "cancelada"
"""A "falha" que não é falha: a pessoa mandou parar. Ver `_falhou_duplicatas`."""

PASSO_DO_PROGRESSO = 25
"""De quantas em quantas imagens a barra de duplicatas anda (F9-C2).

Uma atualização por imagem seriam 3.195 travessias de thread para uma barra de 200 px, em que
25 imagens não chegam a um pixel. O passo é o que faz a barra ser progresso e não tráfego."""


class _Desistiu(Exception):
    """A pessoa cancelou. Levantada de dentro do gerador de rótulos -- ver `detectar_duplicatas`."""


class JanelaDeEstatisticas(QDialog):
    """As estatísticas do dataset: classes, splits, livros e alertas de desequilíbrio.

    **Monoespaçada e sem quebra de linha** (S-149), como a do outro frontend: o corpo é uma tabela
    alinhada por espaço (`{name:>6}: {count:>7}`), e em proporcional ela deixa de ser tabela.
    `QPlainTextEdit` e não `QLabel` pela mesma razão de lá ser um `tk.Text`: o texto rola, e um
    rótulo de 40 linhas empurraria o diálogo para fora da tela.
    """

    def __init__(self, corpo: str, parent: QWidget | None = None) -> None:
        from PyQt6.QtWidgets import QDialogButtonBox

        super().__init__(parent)
        self.setWindowTitle("Estatísticas do dataset")
        self.resize(560, 520)
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.folga(),) * 4)
        fora.setSpacing(espaco.linha())
        # **Título desenhado e um botão que fecha** (F9-C13, §5.8). Ela era a única das treze
        # telas sem botão nenhum: um despejo monoespaçado num quadro de 560x520 px, sem uma
        # palavra em volta dizendo do que era a tabela. O `windowTitle` existe e a barra de
        # título de um `QDialog` sem moldura de sistema não o mostra em toda plataforma.
        titulo = QLabel("Estatísticas do dataset", self)
        titulo.setProperty(tipografia.PROPRIEDADE_DE_PAPEL_DE_FONTE, tipografia.TITULO)
        fora.addWidget(titulo)
        self.corpo = QPlainTextEdit(corpo, self)
        self.corpo.setAccessibleName("Estatísticas do dataset")
        self.corpo.setReadOnly(True)
        self.corpo.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.corpo.setFont(tema.fonte_atual(tipografia.DADO))
        fora.addWidget(self.corpo, 1)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        botoes.rejected.connect(self.reject)
        fora.addWidget(botoes)


def _linhas_em_tuplas(
    csv_path: Path, samples_dir: Path, *, splits_path: Path | None, duplicate_groups: list[list[str]]
) -> list[tuple[object, ...]]:
    """`load_rows` no processo de trabalho, devolvendo tuplas. Ver `_reler_agora`."""
    linhas = load_rows(csv_path, samples_dir, splits_path=splits_path, duplicate_groups=duplicate_groups)
    return [tuple(getattr(linha, campo.name) for campo in fields(DatasetRow)) for linha in linhas]


class PainelDoDataset(QWidget):
    """Tabela paginada do `labels.csv` com filtros, estatísticas e ações."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status. A janela decide onde ela aparece."""

    editar = pyqtSignal(object)
    """A `DatasetRow` que a pessoa mandou abrir no editor."""

    _duplicatas_prontas = pyqtSignal(object)
    """Interno: os grupos de duplicatas, vindos da thread do hash perceptual."""

    _duplicatas_falharam = pyqtSignal(str)

    COLUNAS = COLUNAS
    PAGE_SIZE = PAGE_SIZE

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        caminhos: Callable[[], tuple[Path, Path, Path]],
        conferir: Callable[[DatasetRow], str] | None = None,
        busy: BusyRegistry | None = None,
        em_processo: bool = True,
    ) -> None:
        super().__init__(parent)
        self._caminhos = caminhos
        self._conferir = conferir
        self._em_processo = em_processo
        """Se `load_rows` roda no processo de trabalho (o produto) ou na própria thread (testes).

        Ver `processo_de_trabalho`: a legalidade de 5.431 FENs é Python, e Python numa thread
        divide o GIL com a janela -- a primeira troca para esta aba travava 55 ms por isso."""
        self.rows: list[DatasetRow] = []
        self.visible: list[DatasetRow] = []
        self._grupos_duplicados: list[list[str]] = []
        self._page = 0
        self._busy_registry = busy
        self._busy_token: BusyToken | None = None

        self._ficha_da_leitura: BusyToken | None = None
        """O registro da leitura assíncrona do dataset (F9-C3). Ver `_registrar_a_leitura`.

        Separado de `_busy_token` porque as duas operações podem correr juntas -- a detecção de
        duplicatas chama `reload()` -- e um atributo só faria a segunda soltar a ficha da
        primeira, deixando o rodapé falando de uma operação que já acabou."""

        self._cancelou_a_leitura = False
        """A pessoa desistiu da leitura pelo botão do rodapé. Ver `_cancelar_a_leitura`."""

        self._contagem: tuple[tuple[str, int, int], int] | None = None
        """A última contagem de linhas do CSV, com a marca do arquivo. Ver `contagem_de_amostras`."""

        self._lendo: Tarefa | None = None
        """A leitura do dataset que está correndo agora, se houver (F9-C2). Ver `_reler_agora`.

        Guardada porque duas leituras simultâneas do mesmo CSV são trabalho jogado fora, e a
        segunda chegaria depois da primeira com as mesmas linhas -- e reescreveria a seleção que
        a pessoa já tinha refeito."""

        self._stale = True
        """Alguém gravou no `labels.csv` desde a última leitura desta aba (S-116).

        Começa **verdadeiro**: a aba nasce sem linha nenhuma, e a primeira vez que ela aparecer
        tem de ler. É o mesmo estado de "mudou desde que eu li"."""

        self._montar()
        self._duplicatas_prontas.connect(self._aplicar_duplicatas)
        self._duplicatas_falharam.connect(self._falhou_duplicatas)

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.margem_da_aba(),) * 4)
        fora.setSpacing(espaco.linha())

        barra = BarraFluida(self)
        self._botao(barra, "Recarregar", self.reload, estilos.NEUTRO)
        # Guardado em atributo porque ele precisa **ficar cinza** enquanto a detecção roda (S-314).
        self.btn_duplicatas = self._botao(barra, "Detectar duplicatas", self.detectar_duplicatas, estilos.NEUTRO)
        dica_em(
            self.btn_duplicatas,
            "Compara todas as imagens do dataset por hash perceptual. Fica cinza enquanto uma "
            "detecção está em andamento -- são 3.195 imagens de 800×800, e duas passadas ao "
            "mesmo tempo leem o disco duas vezes para dar a mesma resposta.",
        )
        self._botao(barra, "Estatísticas", self.mostrar_estatisticas, estilos.NEUTRO)
        fora.addWidget(barra)

        fora.addWidget(self._filtros())

        self.tabela = TabelaQt(COLUNAS, self)
        self.tabela.setSelectionMode(TabelaQt.SelectionMode.ExtendedSelection)
        # Corpo em monoespaçada (S-149): a coluna de FEN é a razão. Esta tabela é dado de ponta a
        # ponta -- arquivo, FEN, livro, data --, e é nela que duas linhas precisam alinhar para
        # serem comparadas.
        self.tabela.setFont(tema.fonte_atual(tipografia.DADO))
        self.tabela.itemDoubleClicked.connect(lambda *_: self.editar_selecionada())
        # **A tabela deixou de encher sozinha, e um retângulo em branco não explica isso**
        # (F9-C2). A leitura saiu da thread da janela no item 5 do §7, e o preço é 1,3 s em que a
        # tabela existe e está vazia. Sem esta frase, quem abre a aba vê uma tabela de dataset
        # vazia -- que é uma afirmação sobre o `labels.csv`, e não sobre a espera.
        self.vazio = EstadoVazio(
            self.tabela, titulo=strings.DATASET_LENDO_TITULO, frase=strings.DATASET_LENDO_FRASE
        )
        fora.addWidget(self.tabela, 1)

        paginador = BarraFluida(self)
        # **Os dois glifos ganham nome por extenso** (F9-C2): `"<"` e `">"` chegavam ao leitor de
        # tela como o nome do controle, e um sinal de menor não é uma palavra.
        anterior = self._botao(paginador, "<", lambda: self.mudar_pagina(-1), estilos.NEUTRO)
        anterior.setMaximumWidth(40)
        anterior.setAccessibleName("Página anterior da tabela")
        # `<` e `>` rendiam 6x6 px de tinta num botao de 30x26 (F9-C7, §4.7): o desenho e o
        # mesmo `pagina_anterior` da barra do visor, na mesma grade de 16x16.
        qt_icones.vestir(anterior, "pagina_anterior", estilos.NEUTRO)
        self.lbl_pagina = QLabel("", paginador)
        paginador.adicionar(self.lbl_pagina)
        proxima = self._botao(paginador, ">", lambda: self.mudar_pagina(1), estilos.NEUTRO)
        proxima.setMaximumWidth(40)
        proxima.setAccessibleName("Próxima página da tabela")
        qt_icones.vestir(proxima, "proxima_pagina", estilos.NEUTRO)
        fora.addWidget(paginador)

        acoes = BarraFluida(self)
        self._botao(acoes, "Abrir no editor", self.editar_selecionada, estilos.NEUTRO)
        self._botao(acoes, "Conferir com o modelo", self.conferir_selecionada, estilos.NEUTRO)
        self._botao(acoes, "Quarentena", self.quarentenar_selecionadas, estilos.DESTRUTIVO)
        self._botao(acoes, "Remover", self.remover_selecionadas, estilos.DESTRUTIVO)
        fora.addWidget(acoes)

        self.lbl_estatisticas = QLabel("", self)
        self.lbl_estatisticas.setWordWrap(True)
        fora.addWidget(self.lbl_estatisticas)

    def _filtros(self) -> QGroupBox:
        caixa = QGroupBox("Filtros", self)
        pilha = QVBoxLayout(caixa)
        pilha.setContentsMargins(*(espaco.linha(),) * 4)

        primeira = QHBoxLayout()
        primeira.setSpacing(espaco.folga())
        self.campo_busca = QLineEdit(caixa)
        self.campo_busca.setPlaceholderText("Arquivo, FEN ou livro")
        self.campo_busca.returnPressed.connect(self.aplicar_filtros)
        self.combo_legalidade = QComboBox(caixa)
        self.combo_legalidade.addItems(LEGALITY_CHOICES)
        self.combo_split = QComboBox(caixa)
        self.combo_split.addItems(SPLIT_CHOICES)
        for rotulo, controle in (
            ("Busca", self.campo_busca),
            ("Legalidade", self.combo_legalidade),
            (strings.CONJUNTO, self.combo_split),
        ):
            primeira.addWidget(QLabel(rotulo, caixa))
            primeira.addWidget(controle, 1 if controle is self.campo_busca else 0)
        pilha.addLayout(primeira)

        segunda = QHBoxLayout()
        segunda.setSpacing(espaco.folga())
        self.combo_livro = QComboBox(caixa)
        self.combo_livro.addItem(TODOS)
        self.so_duplicatas = QCheckBox("Só duplicatas", caixa)
        self.so_ausentes = QCheckBox("Imagem ausente", caixa)
        segunda.addWidget(QLabel("Livro", caixa))
        segunda.addWidget(self.combo_livro, 1)
        segunda.addWidget(self.so_duplicatas)
        segunda.addWidget(self.so_ausentes)
        self.btn_aplicar = QPushButton("Aplicar", caixa)
        self.btn_aplicar.clicked.connect(lambda: self.aplicar_filtros())
        self.btn_limpar = QPushButton("Limpar", caixa)
        self.btn_limpar.clicked.connect(self.limpar_filtros)
        for botao in (self.btn_aplicar, self.btn_limpar):
            tema.aplicar_papel(botao, estilos.NEUTRO)
            segunda.addWidget(botao)
        pilha.addLayout(segunda)
        return caixa

    def _botao(self, barra: BarraFluida, rotulo: str, funcao: object, papel: str) -> QPushButton:
        botao = QPushButton(rotulo, barra)
        botao.clicked.connect(funcao)  # type: ignore[arg-type]
        tema.aplicar_papel(botao, papel)
        barra.adicionar(botao)
        return botao

    # --------------------------------------------------------------------------------- dados

    def contagem_de_amostras(self) -> int | None:
        """Quantas linhas o `labels.csv` tem, **sem carregar o dataset** (S-162).

        A contagem vai para o rótulo da aba, e ela não pode custar o que custa abrir a aba: a
        S-116 mediu `load_rows` em 689 ms sobre 3.936 linhas e tornou esta aba preguiçosa
        justamente por isso.

        `None` quando o arquivo não existe: a aba nunca foi usada, e "(0)" ali seria afirmar que
        o dataset está vazio quando o que se sabe é que ele não foi encontrado.
        """
        csv_path, _amostras, _splits = self._caminhos()
        try:
            marca = Path(csv_path).stat()
        except OSError:
            return None
        # **A contagem é guardada por (tamanho, mtime), e a razão é uma medição** (F9-C2). Ela é
        # chamada de `janela._atualizar_abas`, que roda a cada abertura de livro, a cada virada de
        # página e a cada gravação -- e ela **lia o `labels.csv` inteiro** para responder um
        # número. O arnês pegou o efeito: depois de o `_carregar_marcas_salvas` sair da thread da
        # janela, esta linha virou a pior pilha do "abrir PDF", com 249 ms.
        #
        # O par tamanho/mtime é o mesmo critério de invalidação de `ui/games_cache.py`, e ele
        # erra do lado seguro: um arquivo reescrito com o mesmo tamanho **e** o mesmo mtime é um
        # arquivo que o sistema de arquivos diz não ter mudado.
        chave = (str(csv_path), marca.st_size, marca.st_mtime_ns)
        if self._contagem is not None and self._contagem[0] == chave:
            return self._contagem[1]
        try:
            with Path(csv_path).open("r", encoding="utf-8", errors="replace") as arquivo:
                linhas = sum(1 for _ in arquivo)
        except OSError:
            return None
        # Menos o cabeçalho; um arquivo só com ele é dataset vazio, e não -1 amostras.
        total = max(0, linhas - 1)
        self._contagem = (chave, total)
        return total

    def showEvent(self, a0: QShowEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """A aba apareceu. Se alguém gravou enquanto ela estava escondida, é agora que se paga.

        **É o `<Map>` do outro frontend**, e a razão é a mesma: quem grava uma amostra não tem
        como saber se esta aba está visível, e não deveria -- espalhar `if aba_visivel` pelos
        chamadores poria a mesma decisão em cinco lugares.
        """
        super().showEvent(a0)
        if self._stale:
            self._reler_agora()

    def reload(self) -> None:
        """Relê o dataset -- **ou anota que ele mudou, se esta aba não está na tela** (S-116).

        `load_rows` custa 689 ms medidos sobre o `labels.csv` de 3.936 linhas, e o caminho que
        mais chamava isto era o `Ctrl+S`: gravar uma amostra avisava a aba Dataset, que relia o
        arquivo inteiro **mesmo nunca tendo sido aberta**. O laço mais interno do projeto --
        corrigir, salvar, seta, corrigir -- pagava quase um segundo de janela travada por amostra.
        """
        if not self.isVisible():
            self._stale = True
            return
        self._reler_agora()

    def _reler_agora(self) -> None:
        """Relê o dataset **fora da thread da janela** (F9-C2, §7 item 5).

        **O congelamento que a mediana escondia.** O arnês do ciclo 1 tirava a mediana de três
        execuções e publicava 14,6 ms com `viola: False`; as execuções de verdade foram
        `1315 / 15 / 13` ms -- porque só a **primeira** troca para a aba dispara `showEvent`, e só
        ela lê o CSV. A pessoa vive **1,3 segundo** de janela morta no primeiro clique da aba
        Dataset, em toda sessão. A pilha é `load_rows -> labels.read -> csv.__next__`: disco e
        `csv`, que é exatamente o que cabe numa `qt/trabalho.Tarefa`.

        Enquanto a leitura corre, a aba fica cinza e o rodapé diz o que está acontecendo -- que é
        o contrato do §11.3 para operação longa, e o que a versão síncrona não tinha como
        oferecer.

        **E ela se registra, desde o F9-C3.** O ciclo 2 escreveu o `estado.emit("Lendo o
        dataset…")` acima e **não** chamou `busy.register`, e o resultado estava em doze das 36
        capturas: a barra de status dizia "Lendo o dataset…" enquanto a barra de progresso ao
        lado marcava **0 de 100 com o `Cancelar` desabilitado**. O registro é o único caminho
        pelo qual o rodapé -- e o portão `caissa.ui.audit.progresso`, que varre os pontos de
        registro -- ficam sabendo que há operação. Ver `_registrar_a_leitura`.
        """
        self._stale = False
        if self._lendo is not None:
            return  # já há uma leitura correndo; a segunda leria as mesmas linhas
        # O lugar de quem estava conferindo, guardado antes da recarga (S-118). Por `filename` e
        # não por índice: a linha corrigida pode ter mudado de posição no filtro, e um índice
        # apontaria para a vizinha dela.
        selecionadas = {row.filename for row in self.linhas_selecionadas()}
        csv_path, samples_dir, splits_path = self._caminhos()
        grupos = self._grupos_duplicados
        em_processo = self._em_processo

        def ler() -> list[DatasetRow]:
            if em_processo:
                # **Tuplas atravessam o processo, e as linhas nascem aqui, na thread.** Despickar
                # 5.431 `DatasetRow` no pai são 7,8 ms de GIL numa chamada C só; despickar as
                # tuplas são 3,0 ms, e reconstruir as linhas é Python que o interpretador reveza
                # com a janela a cada 0,5 ms (ver `qt/trabalho.INTERVALO_DE_TROCA_S`).
                tuplas = processo_de_trabalho().executar(
                    _linhas_em_tuplas, csv_path, samples_dir, splits_path=splits_path, duplicate_groups=grupos
                )
                return [DatasetRow(*tupla) for tupla in tuplas]
            return load_rows(csv_path, samples_dir, splits_path=splits_path, duplicate_groups=grupos)

        # **Sem pai**, por `qt/trabalho.manter_viva`: ver lá o modo de falha que isso evita.
        tarefa = manter_viva(Tarefa(ler, nome="dataset"))
        tarefa.pronto.connect(lambda linhas: self._dataset_chegou(linhas, selecionadas))
        tarefa.falhou.connect(self._dataset_falhou)
        self._lendo = tarefa
        self.setEnabled(False)
        self._mostrar_espera(True)
        # **A frase do rodapé saiu, e a de dentro do painel ficou** (F9-C5, §7.15).
        # `_mostrar_espera(True)` já escreve `strings.DATASET_LENDO_TITULO` -- "Lendo o
        # dataset" -- **no centro da tabela**, e o `estado.emit` escrevia a mesma frase na zona
        # de mensagem do rodapé, a ~500 px de distância na mesma captura. É a redundância que o
        # §7.10 do ciclo 3 mandou apagar na Galeria, num painel diferente.
        #
        # Quem fica é a de dentro, por dois motivos: ela está **dentro do vazio que explica** e
        # traz a segunda frase ("a tabela aparece assim que a leitura terminar"), que o rodapé
        # não tem espaço para dizer. E o rodapé não fica mudo: `_registrar_a_leitura` põe a
        # operação no `BusyRegistry`, e é ela que acende a barra, o `Cancelar` e o rótulo
        # "leitura do dataset (N amostra(s))" da zona de ocupação -- que diz **quanto**, e não
        # só que está lendo.
        self._registrar_a_leitura()
        tarefa.start()

    def _registrar_a_leitura(self) -> None:
        """Declara a leitura no `BusyRegistry`, com cancelamento (F9-C3, bloqueante nº 2).

        **A pergunta que a exceção em `test_busy.SEM_REGISTRO` respondia era outra.** Ela diz
        *"fechar a janela no meio não perde nada"*, e isso continua verdade -- e foi usada para
        responder *"não precisa de indicação de progresso"*, que é uma segunda pergunta e tem a
        resposta contrária: a pessoa **espera** por esta leitura, com a aba cinza.

        **A barra é indeterminada, e o número saiu de perto dela** (F9-C7, §4.2).

        O ciclo 6 escrevia `detail=f"{quantas} amostra(s)"` -- "5431" -- **ao lado de uma
        marquise**, e defendia a escolha assim: *"o total é conhecido, o número vai para o
        `detail`, onde ele é verdade; a barra anda, que é o que ela sabe"*. O crítico do ciclo 7
        mediu o resultado no pixel das 36 capturas: um bloco azul de **59 px** que anda e dá a
        volta na pista de 118 px, em **28** delas, com "5431" impresso a 200 px dele. A carta
        §3.3 reprova *"barra de progresso indeterminada onde o total é conhecido"*, e imprimir a
        contagem ali é afirmar exatamente o total que a barra não honra: quem lê conclui que o
        programa sabe onde está e escolheu não dizer.

        **A barra continua indeterminada porque a leitura não tem como andar.** Quem lê as
        linhas é `dataset_browser.load_rows` -> `labels.LabelStore._load_rows`, e nenhum dos dois
        aceita callback de progresso -- não há argumento por onde passá-la, e os dois módulos
        estão fora do que esta frente escreve. Uma barra **determinada** com um `feito` que
        ninguém pode incrementar fica parada em 0 % do começo ao fim, que é pior: ela parece
        travada. O conserto de verdade é dar progresso ao leitor, e ele é uma linha em
        `dataset_browser.load_rows` (o laço `for entry in entries`, que já é por amostra).

        **O que muda aqui é o que se afirma.** O `detail` passa a ser o arquivo que está sendo
        lido -- a mesma escolha de `qt/exportador.py`, `detail=pdf_path.name` --, e a contagem
        continua na tela onde ela não é denominador de nada: o rótulo da aba, `Dataset (5431)`,
        por `janela._atualizar_abas` -> `contagem_de_amostras`. Nada se perde e nada se promete.
        """
        if self._busy_registry is None:
            return
        self._cancelou_a_leitura = False
        csv_path, _amostras, _splits = self._caminhos()
        self._ficha_da_leitura = self._busy_registry.register(
            "leitura do dataset",
            # Leitura: nada é gravado, e a próxima abertura da aba refaz a pergunta.
            loses_work=False,
            cancellable=True,
            cancel=self._cancelar_a_leitura,
            detail=Path(csv_path).name,
        )

    def _cancelar_a_leitura(self) -> None:
        """Desiste da leitura: a aba volta agora e a resposta que chegar é descartada.

        **O que este cancelamento faz, dito sem folga.** Ele devolve a aba e joga fora o
        resultado; o `load_rows` em curso termina sozinho, porque a leitura do CSV não tem ponto
        de interrupção público e `dataset_browser.py` não é desta frente. O que o botão do rodapé
        promete -- *"parar limpo"* -- é o que ele entrega: nada gravado, nada pela metade, e a
        janela deixa de esperar.
        """
        self._cancelou_a_leitura = True
        self._soltar_a_leitura()
        self._mostrar_espera(False)
        self.setEnabled(True)
        self.estado.emit("Leitura do dataset cancelada.")

    def _soltar_a_leitura(self) -> None:
        ficha, self._ficha_da_leitura = self._ficha_da_leitura, None
        if ficha is not None:
            ficha.release()

    def aguardar_leitura(self, ms: int = 5000) -> bool:
        """Espera a leitura em curso e **entrega o resultado**. Devolve se havia o que esperar.

        Existe para o teste e para o fechamento, e as duas metades são necessárias: `wait()`
        devolve quando a thread termina, mas o `pronto` dela é entregue pela fila de eventos do
        Qt -- sem o `processEvents` o chamador acorda antes de `_dataset_chegou` rodar, e vê a
        tabela de antes. É o mesmo par que `qt/trabalho.DeteccaoDeFundo.parar` faz.
        """
        from PyQt6.QtWidgets import QApplication

        tarefa = self._lendo
        if tarefa is None:
            return False
        tarefa.wait(ms)
        aplicacao = QApplication.instance()
        if aplicacao is not None:
            for _ in range(4):
                aplicacao.processEvents()
        return True

    def _mostrar_espera(self, esperando: bool) -> None:
        """A frase sobre a tabela enquanto a leitura corre. Ver `_reler_agora`."""
        self.vazio.setGeometry(self.tabela.viewport().rect())
        self.vazio.setVisible(esperando)

    def _dataset_falhou(self, mensagem: str, _excecao: object) -> None:
        self._lendo = None
        self._soltar_a_leitura()
        self._mostrar_espera(False)
        self.setEnabled(True)
        if self._cancelou_a_leitura:
            return  # quem desistiu não precisa de um modal dizendo que desistiu
        QMessageBox.critical(self, "Dataset", f"Não foi possível ler o dataset:\n{mensagem}")

    def _dataset_chegou(self, linhas: object, selecionadas: set[str]) -> None:
        """A leitura terminou. Daqui para baixo é o corpo síncrono de antes, sem mudança."""
        self._lendo = None
        self._soltar_a_leitura()
        if self._cancelou_a_leitura:
            # Ver `_cancelar_a_leitura`: a resposta chegou depois de a pessoa desistir dela.
            self._stale = True
            return
        self._mostrar_espera(False)
        self.setEnabled(True)
        self.rows = list(linhas or [])

        livros = sorted({row.source_pdf for row in self.rows if row.source_pdf})
        escolhido = self.combo_livro.currentText()
        self.combo_livro.clear()
        self.combo_livro.addItems([TODOS, *livros])
        if escolhido in (TODOS, *livros):
            self.combo_livro.setCurrentText(escolhido)
        self.aplicar_filtros(manter_posicao=True)
        self._selecionar_arquivos(selecionadas)
        self.estado.emit(f"Dataset carregado: {len(self.rows)} amostras.")

    def _selecionar_arquivos(self, arquivos: set[str]) -> None:
        """Reseleciona, na página desenhada agora, as linhas que estavam selecionadas antes.

        Só o que está na página: uma linha que saiu dela pela mudança de filtro não tem item de
        tabela para selecionar, e persegui-la mudando de página seria adivinhar.
        """
        if not arquivos:
            return
        primeiro = None
        for indice, row in enumerate(self._pagina_atual()):
            if row.filename not in arquivos:
                continue
            item = self.tabela.topLevelItem(indice)
            if item is None:
                continue
            item.setSelected(True)
            primeiro = primeiro or item
        if primeiro is not None:
            self.tabela.setCurrentItem(primeiro)

    def _pagina_atual(self) -> list[DatasetRow]:
        inicio = self._page * self.PAGE_SIZE
        return self.visible[inicio : inicio + self.PAGE_SIZE]

    def aplicar_filtros(self, *, manter_posicao: bool = False) -> None:
        """Refiltra e redesenha. `manter_posicao` é para quem **não** mudou o filtro (S-118).

        Trocar um filtro é pedir outra lista, e ali voltar à primeira página é o certo. Salvar uma
        amostra não é: a lista é a mesma, e devolver a tabela ao começo perde o lugar de quem
        estava conferindo rótulo a rótulo.
        """
        legalidade = self.combo_legalidade.currentText()
        split = self.combo_split.currentText()
        livro = self.combo_livro.currentText()
        self.visible = filter_rows(
            self.rows,
            query=self.campo_busca.text(),
            legality=None if legalidade == LEGALITY_CHOICES[0] else legalidade,  # type: ignore[arg-type]
            split=None if split == SPLIT_CHOICES[0] else split,  # type: ignore[arg-type]
            source_pdf=None if livro == TODOS else livro,
            only_duplicates=self.so_duplicatas.isChecked(),
            only_missing_image=self.so_ausentes.isChecked(),
        )
        self._page = page_after_change(self._page, len(self.visible), self.PAGE_SIZE) if manter_posicao else 0
        self._desenhar_pagina()
        self.lbl_estatisticas.setText(linha_de_estatisticas(self.rows))

    def limpar_filtros(self) -> None:
        self.campo_busca.clear()
        self.combo_legalidade.setCurrentText(LEGALITY_CHOICES[0])
        self.combo_split.setCurrentText(SPLIT_CHOICES[0])
        self.combo_livro.setCurrentText(TODOS)
        self.so_duplicatas.setChecked(False)
        self.so_ausentes.setChecked(False)
        self.aplicar_filtros()

    def mudar_pagina(self, passo: int) -> None:
        ultima = paginas(len(self.visible), tamanho=self.PAGE_SIZE) - 1
        self._page = max(0, min(ultima, self._page + passo))
        self._desenhar_pagina()

    def _desenhar_pagina(self) -> None:
        self.tabela.preencher(celulas(row) for row in self._pagina_atual())
        self.lbl_pagina.setText(
            frase_de_pagina(self._page, len(self.visible), len(self.rows), tamanho=self.PAGE_SIZE)
        )

    # --------------------------------------------------------------------------------- ações

    def linhas_selecionadas(self) -> list[DatasetRow]:
        pagina = self._pagina_atual()
        indices = sorted(
            self.tabela.indexOfTopLevelItem(item) for item in self.tabela.selectedItems()[:: len(COLUNAS)]
        )
        return [pagina[indice] for indice in indices if 0 <= indice < len(pagina)]

    def editar_selecionada(self) -> None:
        linhas = self.linhas_selecionadas()
        if not linhas:
            self.estado.emit("Selecione uma amostra.")
            return
        self.editar.emit(linhas[0])

    def conferir_selecionada(self) -> None:
        """Roda o modelo na amostra e compara com o rótulo -- acha rótulo humano errado."""
        if self._conferir is None:
            return
        linhas = self.linhas_selecionadas()
        if not linhas:
            self.estado.emit("Selecione uma amostra.")
            return
        try:
            resultado = self._conferir(linhas[0])
        except Exception as exc:  # noqa: BLE001 - falha de modelo vira mensagem, não queda
            QMessageBox.critical(self, "Conferir com o modelo", f"Não foi possível conferir:\n{exc}")
            return
        # O resultado da conferência é uma linha, e ela vai para o rodapé (S-164): a caixa era
        # modal por não haver outro lugar, e conferir amostra a amostra é gesto de repetição --
        # exatamente onde um clique obrigatório por resposta custa mais.
        self.estado.emit(resultado)

    def quarentenar_selecionadas(self) -> None:
        """Move as amostras para o `quarantine.csv`: elas saem do treino e são recuperáveis.

        **O nome deste método é ASCII de propósito, e custou um segfault para descobrir.** Ele se
        chamava `pôr_em_quarentena`, que é o português certo; `clicked.connect` sobre um método
        cujo *nome* tem caractere não-ASCII **derruba o PyQt6 na hora da conexão**, sem exceção e
        sem mensagem -- o processo simplesmente morre. Ver a guarda em
        `tests/test_qt_painel_do_dataset.py`, que varre o pacote inteiro para que ninguém
        redescubra isto por acidente. Rótulo de tela continua acentuado; identificador ligado a
        sinal, não.
        """
        linhas = self.linhas_selecionadas()
        if not linhas:
            self.estado.emit("Selecione ao menos uma amostra.")
            return
        csv_path, _amostras, _splits = self._caminhos()
        destino = csv_path.with_name("quarantine.csv")
        resposta = QMessageBox.question(
            self,
            "Quarentena",
            f"Mover {len(linhas)} amostra(s) para {destino.name}?\n\n"
            "Elas saem do treino e continuam recuperáveis.",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        movidas = quarantine_rows(csv_path, [row.filename for row in linhas], destino)
        self.estado.emit(f"{movidas} amostra(s) movidas para quarentena.")
        self.reload()

    def remover_selecionadas(self) -> None:
        """Remove as amostras. A pergunta tem **três** respostas, e os botões dizem quais.

        `messagebox.askyesnocancel` do Tk devolve `True`/`False`/`None`, e o rótulo de cada botão
        é do sistema. Aqui os três são nomeados à mão, e isso não é enfeite: "Sim" e "Não" numa
        pergunta que já é "remover?" leem-se como confirmar e desistir -- quem quisesse preservar
        o PNG apertaria "Não" achando que estava cancelando, e a linha sumiria do mesmo jeito.
        """
        linhas = self.linhas_selecionadas()
        if not linhas:
            self.estado.emit("Selecione ao menos uma amostra.")
            return
        csv_path, samples_dir, _splits = self._caminhos()
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Remover amostras")
        # A pergunta **nomeia** o que vai sumir (S-170): contar não é conferir, e o que está
        # prestes a ser apagado é rótulo corrigido à mão. Ver `strings.frase_de_remocao`.
        caixa.setText(strings.frase_de_remocao([row.filename for row in linhas], arquivo=csv_path.name))
        com_png = caixa.addButton("Remover linha e apagar o PNG", QMessageBox.ButtonRole.DestructiveRole)
        so_linha = caixa.addButton("Remover só a linha", QMessageBox.ButtonRole.DestructiveRole)
        caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        caixa.exec()

        escolhido = caixa.clickedButton()
        if escolhido not in (com_png, so_linha):
            return
        removidas = delete_rows(
            csv_path,
            [row.filename for row in linhas],
            samples_dir=samples_dir,
            delete_images=escolhido is com_png,
        )
        self.estado.emit(f"{removidas} amostra(s) removidas.")
        self.reload()

    def mostrar_estatisticas(self) -> JanelaDeEstatisticas | None:
        if not self.rows:
            self.reload()
        if not self.rows:
            return None
        janela = JanelaDeEstatisticas(texto_de_estatisticas(self.rows), self)
        janela.show()
        return janela

    # ---------------------------------------------------------------------------- duplicatas

    def detectar_duplicatas(self) -> None:
        """Roda o hash perceptual em segundo plano: são 3.195 imagens de 800×800.

        **Um clique de cada vez (S-314).** Sem guarda, o segundo clique sobrescreve o registro do
        primeiro, e a chave vazada entra na pergunta de fechamento **de toda sessão seguinte**: a
        janela passa a avisar que há uma operação em andamento que terminou há horas, que é
        exatamente o que essa pergunta existe para não fazer.

        **O botão cinza e não uma bandeira.** Uma bandeira sozinha deixa o botão vivo e joga a
        resposta numa frase de rodapé que se perde; o botão cinza é a mesma resposta e não depende
        de a pessoa estar olhando.
        """
        if self._busy_token is not None:
            self.estado.emit("A detecção de duplicatas já está em andamento.")
            return
        if not self.rows:
            self.reload()
        _csv, samples_dir, _splits = self._caminhos()
        self.estado.emit("Procurando duplicatas… isto lê todas as imagens do dataset.")
        rotulos = [(row.filename, row.fen) for row in self.rows if row.image_exists]

        # **Cancelável e determinada, desde o F9-C2** (§7 item 7). O ciclo 1 registrava
        # `cancellable=False` com o argumento de que *"`find_duplicate_groups` não tem por onde"*,
        # e a barra ficava indeterminada com o total escrito ao lado dela, em texto -- que é o
        # defeito bloqueante que `caissa.ui.audit.progresso` acusou.
        #
        # **O "por onde" estava no argumento, e não na função.** `find_duplicate_groups` recebe um
        # `Iterable` de rótulos: um gerador que conta o que já saiu **é** a barra determinada, e um
        # gerador que levanta quando a bandeira sobe **é** o cancelamento. Nem uma linha de
        # `audit.py` muda, e a resposta parcial nunca é entregue -- cancelar é desistir, não
        # aceitar meia lista.
        self._cancelar_duplicatas = threading.Event()
        cancelar = self._cancelar_duplicatas
        if self._busy_registry is not None:
            self._busy_token = self._busy_registry.register(
                "detecção de duplicatas",
                # Derivada: o hash perceptual não grava nada, e refazer recomputa a mesma resposta
                # a partir das mesmas imagens.
                loses_work=False,
                cancellable=True,
                cancel=cancelar.set,
                detail=f"{len(rotulos)} imagem(ns)",
                total=len(rotulos),
            )
        self.btn_duplicatas.setEnabled(False)
        token = self._busy_token

        def _rotulos_contados() -> Iterator[tuple[str, str]]:
            for feito, par in enumerate(rotulos, 1):
                if cancelar.is_set():
                    raise _Desistiu
                if token is not None and feito % PASSO_DO_PROGRESSO == 0:
                    token.update(f"{feito} de {len(rotulos)} imagem(ns)", feito=feito, total=len(rotulos))
                yield par

        def _trabalho() -> None:
            try:
                grupos = find_duplicate_groups(samples_dir, _rotulos_contados())
            except _Desistiu:
                self._duplicatas_falharam.emit(CANCELADA)
                return
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao detectar duplicatas.")
                self._duplicatas_falharam.emit(str(exc))
                return
            self._duplicatas_prontas.emit(grupos)

        threading.Thread(target=_trabalho, daemon=True).start()

    def _soltar_ocupado(self) -> None:
        # Chamado dos **dois** desfechos, e não só do bem-sucedido: o caminho de exceção abre um
        # modal e retorna, e reabilitar depois dele deixaria o botão cinza para sempre -- trocar
        # um travamento por outro (S-314).
        if self._busy_token is not None:
            self._busy_token.release()
            self._busy_token = None
        self.btn_duplicatas.setEnabled(True)

    def _aplicar_duplicatas(self, grupos: list[list[str]]) -> None:
        self._soltar_ocupado()
        self._grupos_duplicados = grupos
        redundantes = sum(len(grupo) - 1 for grupo in grupos)
        self.estado.emit(f"{len(grupos)} grupos de duplicatas, {redundantes} amostras redundantes.")
        self.reload()

    def _falhou_duplicatas(self, detalhe: str) -> None:
        self._soltar_ocupado()
        QMessageBox.critical(self, "Duplicatas", f"Falha na detecção:\n{detalhe}")


_ = (QEvent, Qt)  # noqa: B018 - mantém os imports legíveis para quem estender este painel
