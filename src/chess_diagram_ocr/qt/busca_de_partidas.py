"""O diálogo que pergunta à base por jogador, torneio, ano, Elo, resultado e ECO (S-533).

**O que só existe deste lado.** Os campos, a tabela, a paginação e a thread. Quem decide o que é
uma pergunta malfeita, o que a frase de resumo diz e quais são as colunas é
`ui/busca_de_partidas.py`; quem responde é `games_index.buscar`.

**A busca vai para uma `Tarefa`, e não é zelo.** `games_index.buscar` abre o sqlite, conta até
`TETO_DE_CONTAGEM` e ordena a página -- centenas de milissegundos na gigabase de 10,3 milhões de
partidas, e segundos quando o filtro pede a posição corrente (aí ela **relê** até dois mil
candidatas do `.pgn`). Na linha de eventos isso é a janela branca do Windows dizendo "não está
respondendo"; numa thread é uma frase que muda de "Procurando na base…" para o resumo.

**Uma busca de cada vez.** Enquanto a `Tarefa` roda, "Buscar" fica cinza: duas consultas
concorrentes ao mesmo arquivo não quebram nada -- o sqlite é aberto só para leitura --, mas a
segunda a chegar sobrescreveria a tabela da primeira, e qual delas está na tela passaria a
depender do disco.

**Três estados sem tabela, e eles não dizem a mesma coisa** (a lição da S-135 e do
`estudo_partidas`): *"Procurando na base…"* é a thread; *"Nenhuma partida · Carlsen · 2019"* é a
base respondendo que não tem -- com a pergunta ao lado, porque o formulário pode ter um ano
digitado errado; e o índice ausente ou em obras é `IndiceIndisponivel`, cuja frase já vem com a
instrução, e ao lado dela fica o botão que constrói o índice sem sair daqui.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.games_index import DEFAULT_INDEX_PATH, PAGINA, IndiceIndisponivel, buscar
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.tabela import TabelaQt
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.ui import espaco, estilos, tokens
from chess_diagram_ocr.ui.busca_de_partidas import (
    COLUNAS,
    EM_BUSCA,
    RESULTADOS,
    Filtro,
    de_campos,
    linha,
    problemas,
    resumo,
)

logger = logging.getLogger(__name__)

__all__ = ["DialogoDeBusca"]

LARGURA_DO_NUMERO = 72
"""Quantos pixels os campos de ano, de Elo e de ECO ocupam. Quatro dígitos e nada mais: um campo
de ano com a largura de um campo de nome convida a escrever nele o que não é ano."""


class DialogoDeBusca(QDialog):
    """O formulário, a lista e a página -- sobre o índice por nome (S-533).

    **Não é modal**: quem procura uma partida quer o tabuleiro ao lado, e escolher uma na lista
    abre-a na sala **sem fechar a busca** -- a lista continua ali para a próxima. É o oposto de
    `DialogoDeBases`, que é uma pergunta com resposta única.

    Quem abre a partida não é este diálogo: ele emite `partida_escolhida(caminho, offset)`, que é
    onde ela mora no `.pgn`, e a sala lê os bytes de lá. Ler a partida aqui dentro poria leitura de
    arquivo num widget, e a leitura é de quem vai usá-la.
    """

    partida_escolhida = pyqtSignal(object, int)
    """`(caminho, offset)` da partida que a pessoa escolheu -- o `Path` da base e o byte em que ela
    começa. `object` e não `str` porque um membro de `.zip` é um `Path` composto (S-531), e a
    conversão para texto e de volta perderia isso."""

    indice_pedido = pyqtSignal()
    """A pessoa pediu para construir o índice daqui. Quem o constrói é a sala, que já tem o diálogo
    de progresso e o registro de ocupação da janela (S-532)."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        bases: Sequence[Path] = (),
        indice: Path = DEFAULT_INDEX_PATH,
        posicao: str = "",
    ) -> None:
        super().__init__(parent)
        self._bases = tuple(bases)
        self._indice = indice
        self._posicao = posicao
        """A colocação do tabuleiro da sala, quando há uma. Vazia esconde a caixa de marcar: uma
        opção que não pode ser usada é pior que uma opção ausente (S-32)."""

        self._tarefa: Tarefa | None = None
        self._filtro = Filtro()
        self._offset = 0
        self._proximo = 0
        """Onde a próxima página começa, ou zero quando não há próxima. Vem de
        `Busca.proximo_offset`, que com o filtro por posição conta as **examinadas** e não as
        devolvidas."""
        self._achados: tuple[Any, ...] = ()

        self.setWindowTitle("Buscar partidas na base")
        self.resize(940, 520)
        self._montar()

    # ------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.folga())
        fora.addLayout(self._formulario())

        # **A tabela ordena pelo cabeçalho** (S-533, r2): clicar em "Elo" para achar a partida
        # mais forte da página é o gesto de toda sessão de quem usa uma base, e é o que o
        # ChessBase faz. A ordenação é **da página**, não da base -- as cem linhas que estão na
        # tela --, e é por isso que ela não substitui o `ORDER BY` da consulta: pedir "as mais
        # fortes da base" é o campo de Elo mínimo, e ele vai na pergunta.
        self.tabela = TabelaQt(COLUNAS, self, ordenavel=True)
        self.tabela.setSelectionMode(TabelaQt.SelectionMode.SingleSelection)
        self.tabela.itemDoubleClicked.connect(lambda *_ignorado: self.escolher_selecionada())
        # **Enter também abre**, e por atalho de widget e não pelo botão padrão do diálogo: num
        # `QDialog` o Return vai para o botão com `autoDefault`, e quem acabou de rolar a lista com
        # as setas espera que ele abra a linha marcada -- não que refaça a busca.
        for tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            atalho = QShortcut(QKeySequence(tecla), self.tabela)
            atalho.setContext(Qt.ShortcutContext.WidgetShortcut)
            atalho.activated.connect(self.escolher_selecionada)
        fora.addWidget(self.tabela, 1)

        self.lbl_resumo = QLabel("", self)
        self.lbl_resumo.setWordWrap(True)
        fora.addWidget(self.lbl_resumo)
        fora.addLayout(self._rodape())
        self._atualizar_paginas()

    def _campo(self, largura: int = 0) -> QLineEdit:
        campo = QLineEdit(self)
        if largura:
            campo.setFixedWidth(largura)
        # Enter em qualquer campo busca: é o gesto de quem acabou de digitar o nome.
        campo.returnPressed.connect(self.buscar)
        return campo

    def _formulario(self) -> QGridLayout:
        """Três linhas: quem, onde e quando, e o que a partida foi.

        A ordem é a da pergunta que se faz em voz alta -- *as partidas do Carlsen, em Wijk aan Zee,
        entre 2015 e 2020, que ele ganhou de brancas, na Najdorf* --, e não a das colunas da tabela.
        """
        grade = QGridLayout()
        grade.setHorizontalSpacing(espaco.folga())
        grade.setVerticalSpacing(espaco.linha())

        grade.addWidget(QLabel("Brancas", self), 0, 0)
        self.campo_brancas = self._campo()
        grade.addWidget(self.campo_brancas, 0, 1)
        grade.addWidget(QLabel("Pretas", self), 0, 2)
        self.campo_pretas = self._campo()
        grade.addWidget(self.campo_pretas, 0, 3)
        self.caixa_qualquer_cor = QCheckBox("Qualquer cor", self)
        self.caixa_qualquer_cor.setChecked(True)
        dica_em(
            self.caixa_qualquer_cor,
            "Procura cada nome dos dois lados. Desmarque para pedir a cor: as partidas em que o\n"
            "primeiro nome tinha as brancas, e não todas as partidas dele.",
        )
        grade.addWidget(self.caixa_qualquer_cor, 0, 4, 1, 2)

        grade.addWidget(QLabel("Evento", self), 1, 0)
        self.campo_evento = self._campo()
        dica_em(self.campo_evento, "Um pedaço do nome basta: \"Tata\" acha \"Tata Steel Masters 2019\".")
        grade.addWidget(self.campo_evento, 1, 1)
        grade.addWidget(QLabel("Ano", self), 1, 2)
        anos = QHBoxLayout()
        self.campo_ano_de = self._campo(LARGURA_DO_NUMERO)
        self.campo_ano_ate = self._campo(LARGURA_DO_NUMERO)
        anos.addWidget(self.campo_ano_de)
        anos.addWidget(QLabel("até", self))
        anos.addWidget(self.campo_ano_ate)
        anos.addStretch(1)
        grade.addLayout(anos, 1, 3)
        grade.addWidget(QLabel("Elo mínimo", self), 1, 4)
        self.campo_elo = self._campo(LARGURA_DO_NUMERO)
        dica_em(self.campo_elo, "O menor dos dois Elos da partida: é o nível dela, e não a média.")
        grade.addWidget(self.campo_elo, 1, 5)

        grade.addWidget(QLabel("Resultado", self), 2, 0)
        self.lista_resultado = QComboBox(self)
        for valor, rotulo in RESULTADOS:
            self.lista_resultado.addItem(rotulo, valor)
        grade.addWidget(self.lista_resultado, 2, 1)
        grade.addWidget(QLabel("ECO", self), 2, 2)
        codigos = QHBoxLayout()
        self.campo_eco_de = self._campo(LARGURA_DO_NUMERO)
        self.campo_eco_ate = self._campo(LARGURA_DO_NUMERO)
        codigos.addWidget(self.campo_eco_de)
        codigos.addWidget(QLabel("até", self))
        codigos.addWidget(self.campo_eco_ate)
        codigos.addStretch(1)
        grade.addLayout(codigos, 2, 3)
        self.caixa_posicao = QCheckBox("Só as que passam pela posição do tabuleiro", self)
        self.caixa_posicao.setVisible(bool(self._posicao))
        dica_em(
            self.caixa_posicao,
            "A posição não está no índice: cada candidata que os outros filtros deixarem passar é\n"
            "lida e reproduzida. Estreite os outros filtros antes de marcar isto.",
        )
        grade.addWidget(self.caixa_posicao, 2, 4, 1, 2)
        grade.setColumnStretch(1, 3)
        grade.setColumnStretch(3, 2)
        return grade

    def _rodape(self) -> QHBoxLayout:
        rodape = QHBoxLayout()
        self.btn_buscar = QPushButton("Buscar", self)
        # `lambda` e nao `self.buscar` direto: o `clicked` do Qt carrega um `checked: bool`, e
        # `buscar` so aceita `offset` por nome -- um posicional a mais ali seria `TypeError` no
        # clique, num caminho que nenhum teste de unidade percorre.
        self.btn_buscar.clicked.connect(lambda: self.buscar())
        tema.aplicar_papel(self.btn_buscar, estilos.PRIMARIO)
        self.btn_anterior = QPushButton("Página anterior", self)
        self.btn_anterior.clicked.connect(self.pagina_anterior)
        self.btn_proxima = QPushButton("Próxima página", self)
        self.btn_proxima.clicked.connect(self.proxima_pagina)
        self.btn_indexar = QPushButton("Indexar base…", self)
        self.btn_indexar.clicked.connect(self.indice_pedido.emit)
        dica_em(
            self.btn_indexar,
            "A busca só responde com o índice em dia. Acrescentou um torneio à pasta? Ele lê só\n"
            "o que mudou.",
        )
        fechar = QPushButton("Fechar", self)
        fechar.clicked.connect(self.reject)
        for botao in (self.btn_buscar, self.btn_anterior, self.btn_proxima, self.btn_indexar, fechar):
            # Sem `autoDefault`: com ele, o Enter da lista dispararia o primeiro botão do rodapé em
            # vez do atalho da tabela.
            botao.setAutoDefault(False)
            if botao is not self.btn_buscar:
                tema.aplicar_papel(botao, estilos.NEUTRO)
        rodape.addWidget(self.btn_buscar)
        rodape.addWidget(self.btn_anterior)
        rodape.addWidget(self.btn_proxima)
        rodape.addStretch(1)
        rodape.addWidget(self.btn_indexar)
        rodape.addWidget(fechar)
        return rodape

    # --------------------------------------------------------------------------- busca

    def definir_posicao(self, placement: str) -> None:
        """A colocação do tabuleiro da sala mudou -- é o que a caixa de marcar passa a filtrar.

        Existe porque o diálogo é **reusado** entre aberturas (ver `PainelDeEstudo.buscar_partidas`)
        e a posição é a única coisa dele que envelhece: os campos são de quem digitou, e a base é a
        mesma. Sem isto, a segunda abertura filtraria pela posição da primeira, em silêncio.
        """
        self._posicao = placement
        self.caixa_posicao.setVisible(bool(placement))
        if not placement:
            self.caixa_posicao.setChecked(False)

    def filtro_dos_campos(self) -> Filtro:
        """O que está escrito no formulário, como `Filtro`. Nada é convertido aqui: ver `de_campos`."""
        return de_campos(
            brancas=self.campo_brancas.text(),
            pretas=self.campo_pretas.text(),
            qualquer_cor=self.caixa_qualquer_cor.isChecked(),
            evento=self.campo_evento.text(),
            ano_de=self.campo_ano_de.text(),
            ano_ate=self.campo_ano_ate.text(),
            elo_minimo=self.campo_elo.text(),
            resultado=str(self.lista_resultado.currentData() or ""),
            eco_de=self.campo_eco_de.text(),
            eco_ate=self.campo_eco_ate.text(),
            posicao=self._posicao if self.caixa_posicao.isChecked() else "",
        )

    def buscar(self, *, offset: int = 0) -> bool:
        """Dispara a busca numa thread. Devolve se ela começou.

        Não começa com uma busca em curso nem com o formulário malfeito -- e nos dois casos a
        frase de baixo diz qual dos dois foi.
        """
        if self._tarefa is not None:
            return False
        filtro = self.filtro_dos_campos()
        erros = problemas(filtro)
        if erros:
            self.tabela.preencher(())
            self._escrever("\n".join(erros), atencao=True)
            return False
        self._filtro, self._offset = filtro, offset
        self.tabela.preencher(())
        self._achados = ()
        self._escrever(EM_BUSCA)
        self.btn_buscar.setEnabled(False)
        bases, indice = self._bases, self._indice
        tarefa = Tarefa(
            lambda: buscar(filtro, bases, indice, limite=PAGINA, offset=offset),
            parent=self,
            nome="busca de partidas",
        )
        tarefa.pronto.connect(self._chegou)
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._terminou)
        self._tarefa = tarefa
        tarefa.start()
        return True

    def _chegou(self, resposta: Any) -> None:
        self._achados = tuple(resposta.achados)
        self.tabela.preencher(linha(achado) for achado in self._achados)
        self._escrever(
            resumo(
                self._filtro,
                resposta.total,
                teto=resposta.total_e_teto,
                mostrados=len(self._achados),
                desde=resposta.offset,
                examinadas=resposta.examinadas,
            )
        )
        self._proximo = resposta.proximo_offset if resposta.ha_mais else 0
        self._atualizar_paginas()

    def _falhou(self, mensagem: str, excecao: object) -> None:
        """O índice ausente ou em obras não é defeito: é um estado com saída, e a saída é o botão.

        A frase de `IndiceIndisponivel` já traz a instrução (*"Refaça o índice: menu da sala de
        estudo…"*); qualquer outra falha vira log **e** frase, porque uma tabela que não muda não
        diz que houve erro.
        """
        if not isinstance(excecao, IndiceIndisponivel):
            logger.warning("A busca de partidas falhou: %s", mensagem)
        self._escrever(mensagem, atencao=True)

    def _terminou(self) -> None:
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.deleteLater()
        self.btn_buscar.setEnabled(True)

    def esperar(self, espera_ms: int = 30_000) -> bool:
        """Espera a busca em curso terminar. Devolve se terminou -- é o par de `Indexador.esperar`."""
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(espera_ms))

    # ------------------------------------------------------------------------- páginas

    def proxima_pagina(self) -> bool:
        return self.buscar(offset=self._proximo) if self._proximo else False

    def pagina_anterior(self) -> bool:
        return self.buscar(offset=max(0, self._offset - PAGINA)) if self._offset else False

    def _atualizar_paginas(self) -> None:
        self.btn_anterior.setEnabled(self._offset > 0)
        self.btn_proxima.setEnabled(self._proximo > 0)

    # -------------------------------------------------------------------------- escolha

    def selecionada(self) -> Any:
        """O achado da linha marcada, ou `None`.

        `posicao_selecionada` e não `indexOfTopLevelItem`: com a ordenação pelo cabeçalho ligada,
        a altura da linha na tela deixa de ser a posição dela em `_achados`, e a segunda abriria
        a partida errada -- sem erro nenhum, com uma partida plausível na mesa.
        """
        indice = self.tabela.posicao_selecionada()
        return self._achados[indice] if 0 <= indice < len(self._achados) else None

    def escolher_selecionada(self) -> None:
        """Emite `partida_escolhida` para a linha marcada. **Não fecha o diálogo**: ver a classe."""
        achado = self.selecionada()
        if achado is None:
            return
        self.partida_escolhida.emit(achado.caminho, achado.offset)

    def _escrever(self, texto: str, *, atencao: bool = False) -> None:
        self.lbl_resumo.setText(texto)
        tema.pintar(self.lbl_resumo, "color", tokens.PROBLEMA_TEXTO if atencao else tokens.TEXTO_SECUNDARIO)
