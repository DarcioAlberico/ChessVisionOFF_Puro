"""Os quatro diálogos do programa, no segundo frontend (S-86/S-119/S-503).

**Quais bases procurar**, **que livros varrer**, **qual partida é esta** e **o treino em curso**.
Os quatro são perguntas modais, e por isso moram juntos: o que eles têm em comum não é o assunto
-- é a forma. Um `QDialog` que devolve a escolha ou `None`, e nada mais.

**Nenhuma das decisões é escrita aqui.** Elas foram abertas na S-503, cada uma no seu módulo puro,
e este arquivo as chama:

- `ui/escolha_de_bases.py` -- o tamanho legível, **onde mora o cache de cada conjunto** e o que se
  perde ao trocar. A do meio é a que custa: a contagem de partidas de uma posição muda quando um
  `.pgn` entra, e sem um cache por conjunto experimentar uma base sozinha apagaria ~56 min de
  respostas do acervo inteiro.
- `ui/escopo_da_varredura.py` -- `ScanScope` e a regra de pular o livro completo.
- `ui/lista_de_partidas.py` -- as colunas da candidata e **o travessão**: numa candidata não
  verificada a coluna "Lance" mostra `—` e não `0`, porque a partida não contém a posição.
- `ui/pedido_de_treino.py` -- os parâmetros congelados no clique e a ordem das métricas (S-27).

---

**O modal do Qt é `exec()`, e é onde os dois frontends mais divergem.** O Tk pede `grab_set()` e
`wait_window()`, devolve pelo atributo `chosen`, e quem chama lê o atributo depois. `QDialog.exec()`
já é o laço de eventos aninhado **e** o resultado -- `Accepted` ou `Rejected` --, então a função
`perguntar_*` de cada diálogo cabe em três linhas e a leitura do atributo continua existindo para
o teste, que não abre laço nenhum.

**O `Escape` fecha de graça**, e os quatro dependem disso: no Tk é um `bind` explícito mais o
`WM_DELETE_WINDOW`, e esquecer o segundo deixa o `X` da janela devolvendo "confirmado" em vez de
"desisti".
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.config import DEFAULT_PDF_DIR
from chess_diagram_ocr.games_db import DEFAULT_DATABASE_DIR, PositionHit, database_paths
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.tabela import Coluna, TabelaQt
from chess_diagram_ocr.ui import espaco, estilos, strings, tipografia, tokens
from chess_diagram_ocr.ui.escolha_de_bases import cache_note, describe_size
from chess_diagram_ocr.ui.escopo_da_varredura import (
    ABERTO,
    ESCOLHER,
    PASTA,
    ScanScope,
    books_in_folder,
)
from chess_diagram_ocr.ui.lista_de_partidas import COLUNAS as COLUNAS_DE_PARTIDA
from chess_diagram_ocr.ui.lista_de_partidas import NEIGHBOUR_RADIUS, linha, rotulo, texto_busca
from chess_diagram_ocr.ui.pedido_de_treino import TrainingRequest, format_metrics, summarize_run

logger = logging.getLogger(__name__)

__all__ = [
    "ControladorDeTreino",
    "DialogoDeBases",
    "DialogoDeEscopo",
    "DialogoDePartidas",
    "DialogoDeTreino",
    "perguntar_bases",
    "perguntar_escopo",
]


def _mesmo(um: Path, outro: Path) -> bool:
    """O mesmo `.pgn`, apesar da grafia do caminho. Sem `resolve` obrigatório: 19 GB não mudam de
    lugar, e o que interessa aqui é não listar o mesmo arquivo duas vezes."""
    try:
        return um.resolve() == outro.resolve()
    except OSError:  # pragma: no cover - caminho que o sistema recusa resolver
        return str(um).lower() == str(outro).lower()


class DialogoDeBases(QDialog):
    """A lista de `.pgn` com caixas de marcar. Devolve pelo atributo `escolhidas` após `exec`.

    `escolher` e `nota` existem para o teste: o diálogo de arquivo do sistema não se dirige de um
    roteiro, e a frase do cache depende de um SQLite que um teste de widget não deveria montar.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        selected: Sequence[Path] | None = None,
        folder: Path = DEFAULT_DATABASE_DIR,
        escolher: Callable[[], Sequence[str]] | None = None,
        nota: Callable[[Sequence[Path]], str] = cache_note,
    ) -> None:
        super().__init__(parent)
        self._folder = Path(folder)
        self._escolher = escolher
        self._nota = nota
        self.escolhidas: tuple[Path, ...] | None = None
        """`None` enquanto ninguém confirmou -- e depois de cancelar, também."""

        # A pasta primeiro, e o que veio de fora depois: a ordem da pasta é a identidade que o
        # índice por nome usa (ver `database_paths`), e embaralhá-la aqui confundiria a leitura.
        da_pasta = database_paths(self._folder)
        marcados = list(selected) if selected is not None else list(da_pasta)
        de_fora = [caminho for caminho in marcados if not any(_mesmo(caminho, outro) for outro in da_pasta)]
        self._bases: list[Path] = [*da_pasta, *de_fora]
        self._marcadas: dict[str, bool] = {
            str(base): any(_mesmo(base, escolhido) for escolhido in marcados) for base in self._bases
        }
        self._caixas: dict[str, QCheckBox] = {}

        self.setWindowTitle("Base de partidas")
        self._montar()
        self._atualizar()

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.folga())
        fora.addWidget(QLabel("Contra quais arquivos as buscas vão perguntar?", self))

        self._corpo = QWidget(self)
        self._pilha = QVBoxLayout(self._corpo)
        self._pilha.setContentsMargins(0, 0, 0, 0)
        rolagem = QScrollArea(self)
        rolagem.setWidget(self._corpo)
        rolagem.setWidgetResizable(True)
        fora.addWidget(rolagem, 1)
        self._desenhar_lista()

        botoes = QHBoxLayout()
        for texto_botao, funcao in (
            ("Marcar todas", lambda: self._marcar(True)),
            ("Desmarcar todas", lambda: self._marcar(False)),
            ("Adicionar .pgn de outra pasta…", self.adicionar_do_disco),
        ):
            botao = QPushButton(texto_botao, self)
            botao.clicked.connect(funcao)  # type: ignore[arg-type]
            tema.aplicar_papel(botao, estilos.NEUTRO)
            botoes.addWidget(botao)
        botoes.addStretch(1)
        fora.addLayout(botoes)

        self.lbl_total = QLabel("", self)
        # A frase do cache é o que decide entre "clico agora" e "hoje não": ela diz se a busca
        # custa minutos ou se descarta ~56 min de respostas já pagas.
        self.lbl_nota = QLabel("", self)
        self.lbl_nota.setWordWrap(True)
        for alvo in (self.lbl_total, self.lbl_nota):
            tema.pintar(alvo, "color", tokens.TEXTO_SECUNDARIO)
            fora.addWidget(alvo)

        self.caixa_de_botoes = QDialogButtonBox(self)
        botao_ok = self.caixa_de_botoes.addButton("Procurar", QDialogButtonBox.ButtonRole.AcceptRole)
        assert botao_ok is not None  # o Qt só devolve `None` para papel que ele não monta
        self.btn_ok = botao_ok
        self.caixa_de_botoes.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self.caixa_de_botoes.accepted.connect(self.confirmar)
        self.caixa_de_botoes.rejected.connect(self.reject)
        dica_em(
            self.btn_ok,
            "Fica cinza enquanto nenhuma base estiver marcada:\n"
            "a busca precisa de pelo menos um .pgn para ter onde procurar.",
        )
        fora.addWidget(self.caixa_de_botoes)

    def _desenhar_lista(self) -> None:
        while (item := self._pilha.takeAt(0)) is not None:
            if (widget := item.widget()) is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._caixas.clear()
        for base in self._bases:
            faixa = QWidget(self._corpo)
            deitado = QHBoxLayout(faixa)
            deitado.setContentsMargins(0, 0, 0, 0)
            caixa = QCheckBox(base.name, faixa)
            caixa.setChecked(self._marcadas[str(base)])
            caixa.toggled.connect(lambda ligado, chave=str(base): self._alternou(chave, ligado))
            self._caixas[str(base)] = caixa
            tamanho = QLabel(f"  {describe_size(base)}", faixa)
            tema.pintar(tamanho, "color", tokens.TEXTO_SECUNDARIO)
            deitado.addWidget(caixa)
            deitado.addWidget(tamanho)
            deitado.addStretch(1)
            self._pilha.addWidget(faixa)

    # ------------------------------------------------------------------------------- decisão

    @property
    def selecao(self) -> tuple[Path, ...]:
        return tuple(base for base in self._bases if self._marcadas[str(base)])

    def _alternou(self, chave: str, ligado: bool) -> None:
        self._marcadas[chave] = ligado
        self._atualizar()

    def _marcar(self, valor: bool) -> None:
        for chave in self._marcadas:
            self._marcadas[chave] = valor
            if (caixa := self._caixas.get(chave)) is not None:
                caixa.setChecked(valor)
        self._atualizar()

    def _atualizar(self) -> None:
        escolhidas = self.selecao
        bytes_ = 0
        for base in escolhidas:
            try:
                bytes_ += base.stat().st_size
            except OSError:
                pass
        total = f"{bytes_ / 1e9:.1f} GB".replace(".", ",")
        self.lbl_total.setText(f"{len(escolhidas)} base(s) marcada(s), {total} no total.")
        self.lbl_nota.setText(self._nota(escolhidas))
        self.btn_ok.setEnabled(bool(escolhidas))

    def adicionar_do_disco(self) -> None:
        """Traz `.pgn` de fora da pasta padrão, já marcados. Repetir um que já está na lista é nada."""
        if self._escolher is not None:
            trazidos: Sequence[str] = self._escolher()
        else:  # pragma: no cover - diálogo do sistema
            trazidos, _filtro = QFileDialog.getOpenFileNames(
                self, "Bases de partidas", str(self._folder), "PGN (*.pgn);;Todos (*.*)"
            )
        for bruto in trazidos or ():
            caminho = Path(bruto)
            ja = next((base for base in self._bases if _mesmo(base, caminho)), None)
            if ja is not None:
                self._marcadas[str(ja)] = True
                continue
            self._bases.append(caminho)
            self._marcadas[str(caminho)] = True
        self._desenhar_lista()
        self._atualizar()

    def confirmar(self) -> None:
        escolhidas = self.selecao
        if not escolhidas:
            # O botão já está cinza; o `Return` chegaria aqui de qualquer jeito.
            return
        self.escolhidas = escolhidas
        self.accept()


def perguntar_bases(
    pai: QWidget | None,
    *,
    selected: Sequence[Path] | None = None,
    folder: Path = DEFAULT_DATABASE_DIR,
    escolher: Callable[[], Sequence[str]] | None = None,
    nota: Callable[[Sequence[Path]], str] = cache_note,
) -> tuple[Path, ...] | None:
    """Abre o diálogo modal e devolve as bases marcadas, ou `None` se a pessoa desistiu."""
    dialogo = DialogoDeBases(pai, selected=selected, folder=folder, escolher=escolher, nota=nota)
    dialogo.exec()
    return dialogo.escolhidas


class DialogoDeEscopo(QDialog):
    """Pergunta que livros varrer. Devolve pelo atributo `escopo` depois do `exec`.

    `escolher` existe para o teste: o diálogo de arquivo do sistema não se dirige de um roteiro, e
    o que se quer afirmar é que a escolha vira lista de livros -- não que o Qt sabe abrir a caixa
    de abrir arquivo.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        open_book: Path | None = None,
        folder: Path = DEFAULT_PDF_DIR,
        escolher: Callable[[], Sequence[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._livro_aberto = open_book
        self._folder = Path(folder)
        self._escolher = escolher
        self._da_pasta = books_in_folder(self._folder)
        self.escopo: ScanScope | None = None
        """`None` enquanto ninguém confirmou -- e depois de fechar no X, também."""

        self.setWindowTitle(strings.VARRER_LIVRO)
        self._montar()

    def _montar(self) -> None:
        from PyQt6.QtWidgets import QRadioButton

        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.folga())
        fora.addWidget(QLabel("Varrer quais livros?", self))

        nome = self._livro_aberto.name if self._livro_aberto is not None else "nenhum PDF aberto"
        self.opcao_aberto = QRadioButton(f"Este livro — {nome}", self)
        self.opcao_aberto.setEnabled(self._livro_aberto is not None)
        self.opcao_escolher = QRadioButton("Escolher livro(s) em disco…", self)
        self.opcao_pasta = QRadioButton(
            f"Todos os livros da pasta padrão — {len(self._da_pasta)} livro(s)", self
        )
        self.opcao_pasta.setEnabled(bool(self._da_pasta))
        for opcao in (self.opcao_aberto, self.opcao_escolher, self.opcao_pasta):
            fora.addWidget(opcao)
        # O padrão é o que o botão sempre fez. Sem PDF aberto ele não existe, e aí o padrão é a
        # pasta -- que é a razão de o diálogo poder ser aberto sem livro nenhum na tela.
        (self.opcao_aberto if self._livro_aberto is not None else self.opcao_pasta).setChecked(True)

        # O caminho da pasta e a regra do "pula os completos" ficam na tela, e não numa dica: são
        # as duas coisas que decidem se o clique custa minutos ou horas.
        for texto_secundario in (
            str(self._folder),
            "Com mais de um livro, os que já têm índice completo são pulados —\n"
            "varrer de novo custa a leitura inteira e não acrescenta diagrama.",
        ):
            alvo = QLabel(texto_secundario, self)
            tema.pintar(alvo, "color", tokens.TEXTO_SECUNDARIO)
            fora.addWidget(alvo)

        botoes = QDialogButtonBox(self)
        botoes.addButton("Varrer", QDialogButtonBox.ButtonRole.AcceptRole)
        botoes.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        botoes.accepted.connect(self.confirmar)
        botoes.rejected.connect(self.reject)
        fora.addWidget(botoes)

    def tipo(self) -> str:
        """Qual das três opções está marcada -- `ABERTO`, `ESCOLHER` ou `PASTA`."""
        if self.opcao_aberto.isChecked():
            return ABERTO
        return ESCOLHER if self.opcao_escolher.isChecked() else PASTA

    def _escolher_em_disco(self) -> list[Path]:
        if self._escolher is not None:
            trazidos: Sequence[str] = self._escolher()
        else:  # pragma: no cover - diálogo do sistema
            inicial = self._livro_aberto.parent if self._livro_aberto is not None else self._folder
            trazidos, _filtro = QFileDialog.getOpenFileNames(
                self, "Livros a varrer", str(inicial), "PDF (*.pdf);;Todos (*.*)"
            )
        return [Path(caminho) for caminho in trazidos or ()]

    def confirmar(self) -> None:
        """Fecha com a escolha feita -- exceto se o seletor de arquivos foi cancelado.

        Cancelar a caixa de abrir arquivo é "escolhi errado", e não "desisti de varrer": o diálogo
        continua aberto para a pessoa marcar outro escopo, que é o que ela ia querer fazer de
        qualquer jeito.
        """
        tipo = self.tipo()
        if tipo == ABERTO:
            livros = [self._livro_aberto] if self._livro_aberto is not None else []
        elif tipo == ESCOLHER:
            livros = self._escolher_em_disco()
            if not livros:
                return
        else:
            livros = list(self._da_pasta)

        self.escopo = ScanScope(kind=tipo, books=tuple(livros))
        self.accept()


def perguntar_escopo(
    pai: QWidget | None,
    *,
    open_book: Path | None = None,
    folder: Path = DEFAULT_PDF_DIR,
    escolher: Callable[[], Sequence[str]] | None = None,
) -> ScanScope | None:
    """Abre o diálogo modal e devolve o escopo, ou `None` se a pessoa desistiu."""
    dialogo = DialogoDeEscopo(pai, open_book=open_book, folder=folder, escolher=escolher)
    dialogo.exec()
    return dialogo.escopo


COLUNAS_DA_LISTA: tuple[Coluna, ...] = tuple(
    Coluna(chave, titulo, largura, elastica=chave in ("white", "black", "event"))
    for chave, titulo, largura in COLUNAS_DE_PARTIDA
)
"""As colunas de `ui/lista_de_partidas.py` traduzidas para a `Coluna` da S-153.

O outro frontend monta um `ttk.Treeview` à mão e declara `stretch=` coluna a coluna; aqui a
declaração vira a mesma `Coluna` que o resto do programa usa, e daí saem o alinhamento e a largura
mínima de graça. **Três elásticas e não uma** -- nomes e evento são os campos sem tamanho
previsível, e é neles que a leitura acontece."""


class DialogoDePartidas(QDialog):
    """Mostra as candidatas do diagrama atual e aplica a que a pessoa escolher (S-86).

    **A janela é só widget.** Filtrar, escolher, espalhar aos vizinhos e decidir o que pode ser
    sobrescrito são decisões do `GalleryModel`, que se testa sem abrir janela nenhuma. O que mora
    aqui é a tabela, o campo de filtro e o vaivém entre os dois.

    **A cor de cada linha é por item, e não por etiqueta.** O `ttk.Treeview` pinta por tag e
    reconfigura as tags na troca de tema; o Qt pinta a célula, e é `_repovoar` que decide a cor a
    cada desenho. As quatro situações continuam sendo as mesmas quatro: a escolhida em negrito, a
    que a legenda confirma em verde, a que veio da busca por nome, e a que os vizinhos também têm.
    """

    aplicou = pyqtSignal(str)
    """Uma frase sobre o que a escolha preencheu. Quem a mostra é a Galeria."""

    def __init__(self, parent: QWidget | None = None, *, modelo: Any) -> None:
        super().__init__(parent)
        self._modelo = modelo
        self._todas: tuple[PositionHit, ...] = ()
        self._visiveis: list[PositionHit] = []
        self._por_nome: set[str] = set()
        """As que vieram da busca por nome (S-87), para a lista dizer de onde cada uma veio."""

        self.setWindowTitle("Partidas da base")
        self.resize(900, 420)
        self._montar()
        self.recarregar()

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.folga(),) * 4)
        fora.setSpacing(espaco.folga())

        topo = QHBoxLayout()
        topo.addWidget(QLabel("filtro", self))
        self.campo_filtro = QLineEdit(self)
        # A cada tecla, e não no Return: com 32 candidatas o filtro é para *reduzir enquanto se
        # olha*, e exigir confirmação a cada tentativa faria a pessoa digitar o nome inteiro.
        self.campo_filtro.textChanged.connect(lambda _texto: self._repovoar())
        topo.addWidget(self.campo_filtro, 1)
        self.lbl_contagem = QLabel("", self)
        tema.pintar(self.lbl_contagem, "color", tokens.TEXTO_SECUNDARIO)
        topo.addWidget(self.lbl_contagem)
        fora.addLayout(topo)

        self.tabela = TabelaQt(COLUNAS_DA_LISTA, self)
        self.tabela.setSelectionMode(TabelaQt.SelectionMode.SingleSelection)
        self.tabela.itemDoubleClicked.connect(lambda *_: self.aplicar_selecionada())
        self.tabela.itemSelectionChanged.connect(self._atualizar_botao_de_vizinhos)
        fora.addWidget(self.tabela, 1)

        rodape = QHBoxLayout()
        self.btn_aplicar = QPushButton("Aplicar", self)
        self.btn_aplicar.clicked.connect(self.aplicar_selecionada)
        self.btn_por_nome = QPushButton("Procurar por nome", self)
        self.btn_por_nome.clicked.connect(self.procurar_por_nome)
        self.btn_vizinhos = QPushButton("Aplicar aos vizinhos...", self)
        self.btn_vizinhos.clicked.connect(self.aplicar_aos_vizinhos)
        self.btn_vizinhos.setEnabled(False)
        dica_em(
            self.btn_vizinhos,
            "Fica cinza quando os diagramas vizinhos desta página não têm partida escolhida:\n"
            "é deles que sai o palpite, e sem eles não há o que copiar.",
        )
        for botao in (self.btn_aplicar, self.btn_por_nome, self.btn_vizinhos):
            tema.aplicar_papel(botao, estilos.NEUTRO)
            rodape.addWidget(botao)
        rodape.addStretch(1)
        fechar = QPushButton("Fechar", self)
        # `Esc` já fecha num `QDialog`; o botão existe para quem procura o gesto com o mouse.
        fechar.clicked.connect(self.reject)
        tema.aplicar_papel(fechar, estilos.NEUTRO)
        rodape.addWidget(fechar)
        fora.addLayout(rodape)

    # -------------------------------------------------------------------------------- lista

    def recarregar(self) -> None:
        self._todas, total = self._modelo.current_candidates()
        guardadas = len(self._todas)
        # "32 de 147" é obrigatório, não decorativo: sem ele a pessoa escolhe achando que viu
        # tudo, e a partida certa pode estar entre as 115 que a varredura não guardou.
        self.lbl_contagem.setText(
            f"{guardadas} de {total} partida(s)" if total > guardadas else f"{total} partida(s)"
        )
        self._repovoar()

    def _repovoar(self) -> None:
        from chess_diagram_ocr.games_db import agrees_with_caption
        from chess_diagram_ocr.pdf_text import fold

        alvo = fold(self.campo_filtro.text())
        self._visiveis = [hit for hit in self._todas if not alvo or alvo in fold(texto_busca(hit))]
        escolhida = self._modelo.current_annotation.chosen_game
        par = self._modelo.current_caption_pair()
        vizinhas = self._modelo.neighbour_game_keys(radius=NEIGHBOUR_RADIUS)

        self.tabela.preencher(linha(hit) for hit in self._visiveis)
        negrito = tema.fonte_atual(tipografia.CORPO, negrito=True)
        for indice, hit in enumerate(self._visiveis):
            item = self.tabela.topLevelItem(indice)
            if item is None:  # pragma: no cover - acabou de ser inserido
                continue
            if escolhida and hit.key == escolhida:
                # Negrito no corpo, e não um degrau acima: a linha escolhida precisa de peso e
                # não de nível -- subir de tamanho faria a linha crescer e a lista pular ao
                # trocar de escolha.
                for coluna in range(len(COLUNAS_DA_LISTA)):
                    item.setFont(coluna, negrito)
                continue
            if par is not None and agrees_with_caption(hit, par):
                papel = tokens.PRONTO_TEXTO
            elif hit.key in self._por_nome:
                papel = tokens.DIVERGENTE_TEXTO
            elif hit.key in vizinhas:
                papel = tokens.VIZINHA_TEXTO
            else:
                continue
            self._pintar(item, papel)
        if self._visiveis:
            primeiro = self.tabela.topLevelItem(0)
            if primeiro is not None:
                self.tabela.setCurrentItem(primeiro)
        self._atualizar_botao_de_vizinhos()

    def _pintar(self, item: Any, papel: str) -> None:
        from PyQt6.QtGui import QBrush, QColor

        pincel = QBrush(QColor(tema.cor_atual(papel)))
        for coluna in range(len(COLUNAS_DA_LISTA)):
            item.setForeground(coluna, pincel)

    def selecionada(self) -> PositionHit | None:
        indice = self.tabela.indexOfTopLevelItem(self.tabela.currentItem())
        if not 0 <= indice < len(self._visiveis):
            return None
        return self._visiveis[indice]

    def _atualizar_botao_de_vizinhos(self) -> None:
        escolhida = self.selecionada()
        vizinhos = (
            [] if escolhida is None else self._modelo.neighbours_with_game(escolhida, radius=NEIGHBOUR_RADIUS)
        )
        self.btn_vizinhos.setEnabled(bool(vizinhos))
        self.btn_vizinhos.setText(
            f"Aplicar aos vizinhos ({len(vizinhos)})..." if vizinhos else "Aplicar aos vizinhos..."
        )

    # ------------------------------------------------------------------------------ a escolha

    def aplicar_selecionada(self) -> None:
        escolhida = self.selecionada()
        if escolhida is None:
            return
        conflitos = self._modelo.conflicts_with(escolhida)
        sobrescrever = False
        if conflitos:
            # A base nunca sobrescreve (S-72); uma pessoa escolhendo pode -- mas o que *ela*
            # digitou não some calado. O que veio da base é trocado nos dois casos.
            resposta = QMessageBox.question(
                self,
                "Partidas da base",
                "Esta partida discorda do que você digitou em:\n\n"
                f"  {', '.join(rotulo(campo) for campo in conflitos)}\n\n"
                "Substituir pelo que a partida escolhida diz?\n"
                "Responder Não aplica o resto e deixa esses campos como estão.",
            )
            sobrescrever = resposta == QMessageBox.StandardButton.Yes
        campos = self._modelo.choose_game(escolhida, overwrite=sobrescrever)
        self.aplicou.emit(
            f"Partida escolhida: {escolhida.label} -- {len(campos)} campo(s) preenchido(s)."
            if campos
            else f"Partida escolhida: {escolhida.label}. Nada a preencher; a escolha ficou registrada."
        )
        self._repovoar()

    def procurar_por_nome(self) -> None:
        """Pergunta à base pelos nomes da legenda e junta o que ela achar à lista (S-87).

        **Junta, não substitui.** A lista do cache é o que a varredura mediu sobre a posição; a
        busca por nome alcança o que ela não podia guardar -- a partida cortada pelo teto de 32, e
        a que a posição não casou. Trocar uma pela outra perderia a metade que já estava certa.
        """
        if self._modelo.current_caption_pair() is None:
            QMessageBox.information(
                self,
                "Partidas da base",
                "A legenda deste diagrama não nomeia os dois jogadores, então não há por onde "
                "procurar por nome.",
            )
            return
        achadas = self._modelo.search_games_by_name()
        conhecidas = {hit.key for hit in self._todas}
        novas = tuple(hit for hit in achadas if hit.key not in conhecidas)
        self._por_nome.update(hit.key for hit in achadas)
        if not achadas:
            # **A saída é a ação, e não um comando de terminal** (S-527/S-532). Até aqui a caixa
            # mandava rodar `cvoff-games --build-index`; o índice se constrói de dentro da janela,
            # e o botão daqui é o mesmo `indexar_com_dialogo` da sala de estudo.
            caixa = QMessageBox(self)
            caixa.setIcon(QMessageBox.Icon.Information)
            caixa.setWindowTitle("Partidas da base")
            caixa.setText(
                "A busca por nome não achou partida com esta posição.\n\n"
                "Se o índice da base ainda não foi construído -- ou está atrasado --, construa-o "
                "agora: ele lê só o que mudou e mostra o andamento."
            )
            indexar = caixa.addButton("Indexar agora", QMessageBox.ButtonRole.AcceptRole)
            caixa.addButton(QMessageBox.StandardButton.Close)
            caixa.exec()
            if caixa.clickedButton() is indexar:
                self.indexar_base()
            return
        self._todas = (*self._todas, *novas)
        sem_posicao = sum(1 for hit in novas if not hit.verified)
        aviso = f", {sem_posicao} sem a posição (só headers)" if sem_posicao else ""
        self.lbl_contagem.setText(
            f"{len(self._todas)} partida(s), {len(novas)} pela busca por nome{aviso}"
        )
        self._repovoar()

    def indexar_base(self) -> None:
        """O índice por nome de dentro desta janela, com barra e Cancelar (S-532); a frase final vai
        para a contagem. Guardado em `_indexador` porque um `QObject` sem referência é recolhido."""
        from chess_diagram_ocr.qt import indice_da_base

        self._indexador = indice_da_base.indexar_com_dialogo(self, database_paths())
        self._indexador.terminou.connect(
            lambda resultado: self.lbl_contagem.setText(indice_da_base.frase_final(resultado))
        )

    def aplicar_aos_vizinhos(self) -> None:
        escolhida = self.selecionada()
        if escolhida is None:
            return
        vizinhos = self._modelo.neighbours_with_game(escolhida, radius=NEIGHBOUR_RADIUS)
        if not vizinhos:
            return
        resposta = QMessageBox.question(
            self,
            "Partidas da base",
            f"Aplicar {escolhida.label} a {len(vizinhos)} diagrama(s) vizinho(s)?\n\n"
            "Só entram os que têm esta partida entre as candidatas deles, e cada um recebe o "
            "lance dele -- é a mesma partida em outro momento.",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        tocados = self._modelo.apply_game_to_neighbours(escolhida, radius=NEIGHBOUR_RADIUS)
        self.aplicou.emit(f"{escolhida.label}: aplicada a {tocados} diagrama(s) vizinho(s).")


class DialogoDeTreino(QDialog):
    """O modal do treino em curso: status, métricas e uma barra que não sabe quanto falta.

    **Fechar esconde em vez de destruir**, como do outro lado: o treino continua rodando, e
    destruir a janela deixaria a thread escrevendo em widgets que já não existem. `Esc` faz o
    mesmo -- ele **esconde**, e não cancela nada: quem cancela o treino é o botão do rodapé.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        from PyQt6.QtWidgets import QProgressBar

        super().__init__(parent)
        self.setWindowTitle("Treinando modelo")
        self.resize(520, 170)
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.linha())
        fora.addWidget(QLabel("Status do treino", self))
        self.lbl_status = QLabel("", self)
        self.lbl_metricas = QLabel("", self)
        for alvo in (self.lbl_status, self.lbl_metricas):
            alvo.setWordWrap(True)
            fora.addWidget(alvo)
        self.barra = QProgressBar(self)
        # Mínimo e máximo em zero é a barra indeterminada do Qt -- o `mode="indeterminate"` do
        # `ttk`. Ela não sabe quanto falta porque o treino também não: quem sabe é o rodapé, que
        # conta épocas.
        self.barra.setRange(0, 0)
        fora.addWidget(self.barra)

    def reject(self) -> None:
        """`Esc` e o X escondem. O treino segue, e a janela volta inteira no próximo `mostrar`."""
        self.hide()

    def escrever(self, status: str, metricas: str = "") -> None:
        self.lbl_status.setText(status)
        self.lbl_metricas.setText(metricas)


class ControladorDeTreino(QDialog):
    """Roda o treino numa thread e mantém o modal em dia (S-27/S-31/S-60/S-309).

    **Um `QDialog` só para ter sinais** -- ele nunca é mostrado; quem aparece é o
    `DialogoDeTreino`. A herança existe porque a thread do treino precisa falar com widgets, e no
    Qt isso é sinal: `escreveu` e `terminou` atravessam a fronteira de thread pela conexão em fila
    que o Qt escolhe sozinho. Do outro lado esse papel é do `root.after(0, ...)`.

    **A ordem das métricas e o resumo vêm de `ui/pedido_de_treino.py`**, que é puro: qual número a
    pessoa lê primeiro é a decisão da S-27, e ela não é reescrita aqui.
    """

    escreveu = pyqtSignal(str, str)
    """`(status, métricas)`, vindo da thread do treino."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status."""

    falhou = pyqtSignal(str)
    terminou = pyqtSignal()
    """Ao fim do treino, com ou sem sucesso. É onde o modelo é invalidado -- o `.pt` que estava
    em memória pode não ser mais o que está no disco (S-31)."""

    controles = pyqtSignal(bool)
    """Liga e desliga os controles da aba enquanto o treino roda."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        pedido: Callable[[], TrainingRequest],
        busy: Any = None,
    ) -> None:
        super().__init__(parent)
        self._pedido = pedido
        self._busy = busy
        self._busy_token: Any = None
        self._cancelar: threading.Event | None = None
        self._rodando = False
        self._total_de_epocas = 0
        self.dialogo: DialogoDeTreino | None = None
        self.escreveu.connect(self._escrever_agora)
        self.falhou.connect(self._mostrar_falha)

    @property
    def rodando(self) -> bool:
        return self._rodando

    def iniciar(self) -> None:
        if self._rodando:
            # Rodapé (S-164): a zona de operação ao lado já mostra "treino do modelo (época 3 de
            # 8)", e uma caixa modal dizendo o mesmo é um clique para saber o que está na tela.
            self.estado.emit("Já existe um treino em execução.")
            return

        pedido = self._pedido()
        self._rodando = True
        self._total_de_epocas = pedido.epochs
        self._cancelar = threading.Event()
        if self._busy is not None:
            self._busy_token = self._busy.register(
                "treino do modelo",
                # O checkpoint da melhor época já está no disco; o que se perde é o progresso
                # desde ela -- que em CPU é ~9 min por época, e por isso vale perguntar.
                loses_work=True,
                cancellable=True,
                detail=f"época 1 de {pedido.epochs}",
                cancel=self.cancelar,
            )
        self.controles.emit(False)
        self.escrever("Preparando treino...", "")
        self.mostrar()
        threading.Thread(target=self._trabalho, args=(pedido, self._cancelar), daemon=True).start()

    def cancelar(self) -> None:
        """Pede o cancelamento. A resposta vem entre épocas, não no meio de uma (S-60)."""
        if self._cancelar is None:
            return
        self._cancelar.set()
        self.estado.emit("Cancelando treino... termina a época atual e para.")

    # ---------------------------------------------------------------------------------- modal

    def mostrar(self) -> DialogoDeTreino:
        """Abre o modal, ou traz de volta o que foi escondido."""
        if self.dialogo is None:
            self.dialogo = DialogoDeTreino(self.parentWidget())
        self.dialogo.show()
        self.dialogo.raise_()
        return self.dialogo

    def fechar(self) -> None:
        if self.dialogo is not None:
            self.dialogo.close()
            self.dialogo.deleteLater()
            self.dialogo = None

    def escrever(self, status: str, metricas: str = "") -> None:
        """Atualiza o modal **de qualquer thread**; o trabalho chama isto a cada época.

        Da thread do treino o sinal atravessa por conexão em fila e o texto chega na thread da
        janela; da própria thread da janela a conexão é direta, e o efeito é o mesmo. É o
        `root.after(0, ...)` do outro lado, com o desvio feito pelo Qt em vez de à mão.
        """
        self.escreveu.emit(status, metricas)

    def _escrever_agora(self, status: str, metricas: str) -> None:
        if self.dialogo is not None:
            self.dialogo.escrever(status, metricas)

    def _mostrar_falha(self, detalhe: str) -> None:
        QMessageBox.critical(self.parentWidget(), "Erro no treino", detalhe)

    # -------------------------------------------------------------------------------- trabalho

    def _progresso(self, row: dict[str, Any]) -> None:
        epoca = int(row.get("epoch", 0))
        status = f"Treinando... época {epoca}/{self._total_de_epocas}"
        self.estado.emit(status)
        self.escrever(status, format_metrics(row))
        if self._busy_token is not None:
            # Com o número, e não só com a frase: é o que faz a barra do rodapé ser determinada
            # (S-164). Época é a unidade em que o treino de verdade progride -- ~9 min cada em CPU.
            self._busy_token.update(
                f"época {epoca} de {self._total_de_epocas}", feito=epoca, total=self._total_de_epocas
            )

    def _trabalho(self, pedido: TrainingRequest, cancelar: threading.Event) -> None:
        from chess_diagram_ocr.training import train_model

        try:
            self.estado.emit("Treinando modelo...")
            self.escrever("Treinando modelo...", "")
            run = train_model(
                csv_path=pedido.csv_path,
                samples_dir=pedido.samples_dir,
                model_path=pedido.model_path,
                epochs=pedido.epochs,
                batch_size=pedido.batch_size,
                lr=pedido.lr,
                progress_cb=self._progresso,
                splits_path=pedido.splits_path,
                fresh=pedido.fresh,
                # O `Event` que o botão "Cancelar" do rodapé aciona (S-309).
                cancel_event=cancelar,
            )
            resumo = summarize_run(run)
            # Sem caixa modal ao fim (S-164): o modal do treino **já está aberto** e mostra o
            # resumo -- a caixa era uma segunda cópia do que está a 20 px dela, e um treino de uma
            # hora terminava exigindo um clique para liberar a janela.
            #
            # Cancelado não é concluído nem falhou (S-309): o checkpoint da melhor época gravada
            # continua no disco e continua sendo o melhor conhecido. Dizer "Treino concluído"
            # sobre uma parada na época 2 de 8 seria a interface mentindo sobre o que ela fez.
            if run.cancelled:
                epocas = len(run.history)
                feito = f"Treino cancelado na época {epocas} de {self._total_de_epocas}."
                sobrou = resumo or "nenhuma época superou o checkpoint que já existia."
                self.estado.emit(f"{feito} {sobrou}")
                self.escrever(feito, sobrou)
            else:
                self.estado.emit(
                    f"Treino concluído. Melhor época: {run.best_epoch} de {len(run.history)}. {resumo}"
                )
                self.escrever("Treino concluído.", resumo)
        except Exception as exc:  # noqa: BLE001 - falha de treino vira mensagem, não queda
            logger.exception("Falha no treino disparado pela interface.")
            self.estado.emit("Falha no treino.")
            self.escrever("Falha no treino.", str(exc))
            self.falhou.emit(str(exc))
        finally:
            self.terminou.emit()

    def concluir(self) -> None:
        """Devolve os controles e fecha o modal. Ligue em `terminou`, que chega da thread."""
        self._rodando = False
        self._cancelar = None
        if self._busy_token is not None:
            self._busy_token.release()
            self._busy_token = None
        self.controles.emit(True)
        self.fechar()


_ = (Qt, QListWidget, QListWidgetItem, strings)  # noqa: B018 - imports que os painéis herdam daqui
