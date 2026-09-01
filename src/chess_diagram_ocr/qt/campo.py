"""A anotação do conjunto de campo: a página vira verdade de referência (S-95/S-301/S-505).

**Por que este painel existe, e por que ele quase não foi portado.** Três ações do catálogo --
`anotar_pagina`, `anotar_sem_diagrama` e `tirar_do_campo` -- eram atendidas por botões da janela
do Tk, e por botões só: elas não estavam na tabela `_comandos`, então a comparação das duas
janelas ação a ação passava em verde sem elas. Quem as teria acusado era `ui/alcance.perdidos()`,
que respondia "que ação do catálogo ninguém alcança" -- e ela mesma saiu no corte, porque
perguntava sobre os três cromos do Tk. As duas guardas caíram no mesmo dia, e o buraco entre elas
era exatamente do tamanho deste arquivo.

**O buraco foi fechado depois, e por duas guardas.**
`test_ui_comandos.test_todo_comando_do_catalogo_alcanca_alguem` cobra que toda ação do catálogo
alcance o menu ou esteja declarada como exceção, e
`test_qt_janela.test_todo_comando_do_catalogo_tem_dono_nesta_janela` cobra que a declaração tenha
dono chamável. Apagar este painel hoje deixa as duas vermelhas, que é o que não aconteceu da
primeira vez.

**O que se perderia.** `data/field_set.jsonl` é o conjunto que `cvoff-field` mede, e ele só cresce
por este clique -- página a página, conferida por gente. Sem a anotação na janela, o conjunto
congela onde está e os quatro relatórios de campo param de poder ser refeitos.

**O que é decisão e mora fora daqui.** `ui/field_draft.py` responde o que é um rascunho de página,
o que `describe()` diz, quando um diagrama pode ser referência e quantos já estão anotados;
`field_eval.py` lê e grava o arquivo. Este módulo é botão, rótulo e a pergunta antes de apagar.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from chess_diagram_ocr.config import PROJECT_ROOT
from chess_diagram_ocr.field_eval import load_field_set, upsert_page
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.ui import comandos, espaco, estilos
from chess_diagram_ocr.ui.field_draft import REGIMES, FieldDraft, diagramas_ja_anotados
from chess_diagram_ocr.ui.page_overlay import PageBoxes

logger = logging.getLogger(__name__)

__all__ = ["ACOES_PROPRIAS", "PainelDeCampo"]

ACOES_PROPRIAS = frozenset(comandos.NA_LINHA_DE_CAMPO)
"""As três ações do catálogo que este painel atende. Ver o docstring do módulo.

**Tirada de `comandos.NA_LINHA_DE_CAMPO` e não escrita de novo.** Aquela lista já existe para a
paleta poder dizer *por que* não executa estes três, e repeti-los aqui seria a segunda cópia de
uma decisão declarada -- que diverge no primeiro nome que alguém acrescenta a uma só das duas.
O docstring dela promete que "existir como lista declarada é o que permite o teste cobrar que não
haja uma segunda"; esta linha é o que cumpre a promessa."""

SEM_LIVRO = "Abra um PDF antes de anotar a página."
SEM_CAIXA = (
    "Nenhum diagrama selecionado. Clique com o botão direito sobre a caixa que você quer tirar."
)
"""A mesma frase de tirar a caixa da página: dois comandos de tirar não ensinam dois gestos."""

CAMINHO_DO_CONJUNTO = PROJECT_ROOT / "data" / "field_set.jsonl"
"""O mesmo arquivo que `cvoff-field --set` lê de fábrica. Um caminho e não dois, porque anotar
num arquivo e medir noutro é o defeito que não dá sintoma: as duas pontas funcionam."""


class PainelDeCampo(QWidget):
    """A barra de anotação, sob a página. Três botões, um regime e uma frase de estado.

    **Ela não conhece a janela**: tudo que precisa saber vem por função -- que livro está aberto,
    que página, que caixas há nela e o que o editor corrigiu. É o mesmo contrato dos outros
    painéis, e é o que faz este arquivo ser testável sem montar a janela inteira.
    """

    estado = pyqtSignal(str)
    """A frase para o rodapé. Como em todos os painéis: ele não conhece o rodapé."""

    def __init__(
        self,
        pai: QWidget | None = None,
        *,
        pdf_path: Callable[[], Path | None],
        page_index: Callable[[], int],
        caixas: Callable[[], PageBoxes | None],
        caixa_selecionada: Callable[[], int | None],
        colocacoes: Callable[[], dict[int, tuple[str, bool]]],
        aviso_de_treino: Callable[[], str] = lambda: "",
        caminho_do_conjunto: Path | None = None,
    ) -> None:
        super().__init__(pai)
        self._pdf = pdf_path
        self._pagina = page_index
        self._caixas = caixas
        self._selecionada = caixa_selecionada
        self._colocacoes = colocacoes
        self._aviso_de_treino = aviso_de_treino
        self._conjunto = caminho_do_conjunto or CAMINHO_DO_CONJUNTO
        """`None` é o arquivo do produto. O parâmetro existe para o teste não anotar no conjunto
        de verdade -- é o mesmo motivo do `pasta_da_galeria` da Galeria."""

        fora = QVBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(espaco.linha())

        barra = QHBoxLayout()
        barra.setSpacing(espaco.linha())
        self.regime = QComboBox(self)
        self.regime.addItems(list(REGIMES))
        dica_em(self.regime, "Em que condição esta página foi lida. Entra na anotação e separa as\nmedições por regime.")
        barra.addWidget(self.regime)
        self.btn_anotar = self._botao(barra, "anotar_pagina", self.anotar_pagina, estilos.PRIMARIO)
        self.btn_sem_diagrama = self._botao(barra, "anotar_sem_diagrama", self.anotar_sem_diagrama)
        self.btn_tirar = self._botao(barra, "tirar_do_campo", self.tirar_do_campo, estilos.DESTRUTIVO)
        barra.addStretch(1)
        fora.addLayout(barra)

        self.lbl_estado = QLabel("", self)
        self.lbl_estado.setWordWrap(True)
        fora.addWidget(self.lbl_estado)
        self.atualizar()

    def _botao(self, barra: QHBoxLayout, acao: str, alvo: Callable[[], object], papel: str = estilos.NEUTRO) -> QPushButton:
        """Rótulo, papel e dica do catálogo -- este arquivo não escreve texto de interface."""
        botao = QPushButton(comandos.rotulo_de_botao(acao), self)
        botao.clicked.connect(lambda _marcado=False: alvo())
        tema.aplicar_papel(botao, papel)
        dica_em(botao, comandos.rotulo(acao))
        barra.addWidget(botao)
        return botao

    # ------------------------------------------------------------------------ o que a tela diz

    def atualizar(self) -> None:
        """Diz, ao virar a página, se ela já está anotada e se ela serve de referência.

        O aviso de treino é a metade da S-97 que fica na tela: anotar uma página de que já há
        amostra em `train` acrescenta ao conjunto de campo um diagrama que o próximo modelo terá
        visto. Não é proibido -- o conjunto é pequeno demais para recusar página --, mas precisa
        ser uma escolha e não um acidente, e a hora de saber é **antes** do clique.
        """
        livro = self._pdf()
        if livro is None:
            self.lbl_estado.setText("")
            return
        gravadas = {(p.pdf, p.page): p for p in self._ler()}
        pagina = gravadas.get((livro.name, self._pagina()))
        estado = "página não anotada" if pagina is None else f"anotada: {FieldDraft.from_page(pagina).describe()}"
        self.lbl_estado.setText(f"{estado}{self._aviso_de_treino()}")

    def _ler(self) -> list:
        try:
            return load_field_set(self._conjunto)
        except (OSError, ValueError) as erro:
            # Conjunto ilegível não pode derrubar a janela: ele é informação lateral até o clique.
            logger.debug("Não foi possível ler o conjunto de campo: %s", erro)
            return []

    # ------------------------------------------------------------------- as três do catálogo

    def anotar_pagina(self) -> None:
        """Grava a página no conjunto de campo, revisada.

        **É o gesto que alimenta a medição de campo**, e o único: `data/field_set.jsonl` não
        cresce por mais nenhum caminho. Confira antes -- é isto que mede o pipeline, e um erro
        aqui vira erro na métrica.
        """
        self._gravar(vazia=False)

    def anotar_sem_diagrama(self) -> None:
        """A página não tem diagrama nenhum, e isso também é referência.

        Página de texto puro que o detector "acha" um diagrama é falso positivo, e sem esta
        anotação a medição nunca vê o caso.
        """
        if not self._confirmar_apagar_anotacao():
            return
        self._gravar(vazia=True)

    def tirar_do_campo(self) -> None:
        """Tira da anotação o diagrama selecionado -- o falso positivo que o detector achou.

        **A seleção vem do visualizador, e não do editor (S-306).** Vinha do índice do editor,
        que vale **0** com a lista vazia: a guarda passava sempre e o comando tirava do arquivo o
        diagrama nº 1, que ninguém selecionara.
        """
        livro = self._pdf()
        if livro is None:
            self.estado.emit(SEM_LIVRO)
            return
        caixas = self._caixas()
        if caixas is None or not len(caixas):
            self.estado.emit("Nenhuma caixa nesta página para tirar.")
            return
        selecionada = self._selecionada()
        if selecionada is None or not 0 <= selecionada < len(caixas.boxes):
            self.estado.emit(SEM_CAIXA)
            return

        rascunho = self._rascunho()
        indice = rascunho.index_at(caixas.boxes[selecionada].bbox_pdf)
        if indice is None or not rascunho.remove(indice):
            self.estado.emit("Esse diagrama não está na anotação desta página.")
            return
        total = upsert_page(self._conjunto, rascunho.to_page())
        self.lbl_estado.setText(f"{rascunho.describe()} · {total} página(s) no conjunto")
        self.estado.emit(f"Diagrama tirado da anotação. Ficaram {rascunho.describe()}.")

    # ------------------------------------------------------------------------------- por baixo

    def _gravar(self, *, vazia: bool) -> None:
        livro = self._pdf()
        if livro is None:
            self.estado.emit(SEM_LIVRO)
            return
        pagina = self._pagina()
        rascunho = FieldDraft(pdf_name=livro.name, page=pagina) if vazia else self._rascunho()
        rascunho.regime = "sem-diagrama" if vazia else (self.regime.currentText() or rascunho.regime)
        total = upsert_page(self._conjunto, rascunho.to_page())
        self.lbl_estado.setText(f"{rascunho.describe()} · {total} página(s) no conjunto")
        self.estado.emit(
            f"Página {pagina + 1} anotada no conjunto de campo: {rascunho.describe()}. "
            f"O conjunto tem {total} página(s) revisada(s)."
        )

    def _rascunho(self) -> FieldDraft:
        """A anotação desta página: a que já existe no arquivo, ou o que está na tela.

        Retomar a existente é o que permite corrigir sem recomeçar -- confirma-se rápido, acha-se
        um diagrama que faltou, e volta-se a ela.
        """
        livro = self._pdf()
        nome = livro.name if livro is not None else ""
        pagina = self._pagina()
        gravadas = {(p.pdf, p.page): p for p in self._ler()}
        existente = gravadas.get((nome, pagina))
        if existente is not None:
            return FieldDraft.from_page(existente)

        rascunho = FieldDraft(pdf_name=nome, page=pagina, regime=self.regime.currentText())
        caixas = self._caixas()
        conferidos = self._colocacoes()
        rascunho.reset_from(
            [
                (caixa.bbox_pdf, *conferidos.get(indice, ("", False)))
                for indice, caixa in enumerate(caixas.boxes if caixas is not None else ())
            ]
        )
        return rascunho

    def _confirmar_apagar_anotacao(self) -> bool:
        """"Sem diagrama" sobre folha já anotada: pergunta nomeando o que se perde (S-301).

        Quem decide se há o que perder é `field_draft.diagramas_ja_anotados`, e o docstring de lá
        diz por que a pergunta é sobre o **arquivo** e não sobre o rascunho da tela.
        """
        livro = self._pdf()
        if livro is None:
            return True
        pagina = self._pagina()
        quantos = diagramas_ja_anotados(self._ler(), livro.name, pagina)
        if not quantos:
            return True
        plural = "s" if quantos > 1 else ""
        resposta = QMessageBox.question(
            self,
            "Marcar a página como sem diagrama",
            f"A página {pagina + 1} está anotada com {quantos} diagrama{plural} "
            f"revisado{plural}.\n\nMarcá-la como sem diagrama descarta essa anotação, e ela "
            f"não volta. Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resposta == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------ o dono das ações (S-244/S-400)

    def acoes_proprias(self) -> frozenset[str]:
        return ACOES_PROPRIAS

    def atender(self, acao: str) -> Callable[[], object] | None:
        return {
            "anotar_pagina": self.anotar_pagina,
            "anotar_sem_diagrama": self.anotar_sem_diagrama,
            "tirar_do_campo": self.tirar_do_campo,
        }.get(acao)
