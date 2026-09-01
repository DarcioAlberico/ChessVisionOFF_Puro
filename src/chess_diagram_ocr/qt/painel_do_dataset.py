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
from collections.abc import Callable
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
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.tabela import TabelaQt
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

__all__ = ["JanelaDeEstatisticas", "PainelDoDataset"]


class JanelaDeEstatisticas(QDialog):
    """As estatísticas do dataset: classes, splits, livros e alertas de desequilíbrio.

    **Monoespaçada e sem quebra de linha** (S-149), como a do outro frontend: o corpo é uma tabela
    alinhada por espaço (`{name:>6}: {count:>7}`), e em proporcional ela deixa de ser tabela.
    `QPlainTextEdit` e não `QLabel` pela mesma razão de lá ser um `tk.Text`: o texto rola, e um
    rótulo de 40 linhas empurraria o diálogo para fora da tela.
    """

    def __init__(self, corpo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Estatísticas do dataset")
        self.resize(560, 520)
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.folga(),) * 4)
        self.corpo = QPlainTextEdit(corpo, self)
        self.corpo.setReadOnly(True)
        self.corpo.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.corpo.setFont(tema.fonte_atual(tipografia.DADO))
        fora.addWidget(self.corpo)


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
    ) -> None:
        super().__init__(parent)
        self._caminhos = caminhos
        self._conferir = conferir
        self.rows: list[DatasetRow] = []
        self.visible: list[DatasetRow] = []
        self._grupos_duplicados: list[list[str]] = []
        self._page = 0
        self._busy_registry = busy
        self._busy_token: BusyToken | None = None

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
        fora.setContentsMargins(*(espaco.linha(),) * 4)
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
        fora.addWidget(self.tabela, 1)

        paginador = BarraFluida(self)
        self._botao(paginador, "<", lambda: self.mudar_pagina(-1), estilos.NEUTRO).setMaximumWidth(40)
        self.lbl_pagina = QLabel("", paginador)
        paginador.adicionar(self.lbl_pagina)
        self._botao(paginador, ">", lambda: self.mudar_pagina(1), estilos.NEUTRO).setMaximumWidth(40)
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
            with Path(csv_path).open("r", encoding="utf-8", errors="replace") as arquivo:
                linhas = sum(1 for _ in arquivo)
        except OSError:
            return None
        # Menos o cabeçalho; um arquivo só com ele é dataset vazio, e não -1 amostras.
        return max(0, linhas - 1)

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
        self._stale = False
        # O lugar de quem estava conferindo, guardado antes da recarga (S-118). Por `filename` e
        # não por índice: a linha corrigida pode ter mudado de posição no filtro, e um índice
        # apontaria para a vizinha dela.
        selecionadas = {row.filename for row in self.linhas_selecionadas()}
        csv_path, samples_dir, splits_path = self._caminhos()
        try:
            self.rows = load_rows(
                csv_path, samples_dir, splits_path=splits_path, duplicate_groups=self._grupos_duplicados
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Dataset", f"Não foi possível ler o dataset:\n{exc}")
            return

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
        self.estado.emit("Procurando duplicatas... isto lê todas as imagens do dataset.")
        rotulos = [(row.filename, row.fen) for row in self.rows if row.image_exists]

        if self._busy_registry is not None:
            self._busy_token = self._busy_registry.register(
                "detecção de duplicatas",
                # Derivada: o hash perceptual não grava nada, e refazer recomputa a mesma resposta
                # a partir das mesmas imagens. Não é cancelável porque `find_duplicate_groups` não
                # tem por onde -- e inventar um `Event` que ninguém consulta seria oferecer um
                # botão que não para nada.
                loses_work=False,
                detail=f"{len(rotulos)} imagem(ns)",
            )
        self.btn_duplicatas.setEnabled(False)

        def _trabalho() -> None:
            try:
                grupos = find_duplicate_groups(samples_dir, rotulos)
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
