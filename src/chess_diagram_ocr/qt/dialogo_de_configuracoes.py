"""*Ferramentas ▸ Configurações…* -- a janela que grava `data/settings.json`.

Até aqui o arquivo só era **lido**: a interface não tinha onde mudar o motor de OCR, o
executável do motor UCI, e muito menos as épocas do treino, que eram um número dentro de
`qt/janela.py`. Esta janela monta um controle por `Campo` de `ui/configuracoes.CAMPOS`
(a tabela pura, testada contra `settings.Settings`), uma aba por seção, e devolve um
`Settings` novo por `configuracoes.trocar` -- nunca escreve num dataclass congelado.

**O que ela não faz.** Não aplica nada "ao vivo": quem lê preferência lê na hora de usar
(`_pedido_de_treino` monta o pedido no clique; `sala_declarada` pergunta pelo motor ao abrir
a sala). Gravar e fechar é o contrato inteiro, e é o que deixa esta janela sem estado
próprio além do formulário.

**Acessibilidade.** Todo controle recebe `accessibleName` = o rótulo da tabela, e a ajuda
vira dica; é o que `caissa.ui.audit.teclado` cobra de cada diálogo do produto. O botão
*Restaurar padrões* volta a tabela a `Settings()` -- os padrões de fábrica, que são os
números que estavam escritos na janela antes desta existir.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr import settings as preferencias
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.ui import configuracoes, espaco, estilos, folha_de_estilo

__all__ = ["DialogoDeConfiguracoes", "abrir"]

TITULO = "Configurações"
ABA_DO_LEITOR_LOCAL = "remote_fen"
"""A seção `local_reader` não tem aba própria; ver `configuracoes.ABAS`."""


class DialogoDeConfiguracoes(QDialog):
    """Uma aba por seção, um controle por campo, e `valores()` de volta como `Settings`."""

    def __init__(
        self,
        pai: QWidget | None = None,
        *,
        configuracao: preferencias.Settings | None = None,
        ao_salvar: Callable[[preferencias.Settings], None] | None = None,
    ) -> None:
        super().__init__(pai)
        self.setWindowTitle(TITULO)
        self.resize(640, 420)
        self._inicial = configuracao if configuracao is not None else preferencias.Settings()
        self._ao_salvar = ao_salvar
        self._controles: dict[str, QWidget] = {}

        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.linha())
        self.abas = QTabWidget(self)
        self.abas.setAccessibleName("Seções das configurações")
        fora.addWidget(self.abas, 1)

        formularios: dict[str, QFormLayout] = {}
        for secao, titulo in configuracoes.ABAS:
            pagina = QWidget(self.abas)
            formulario = QFormLayout(pagina)
            formulario.setSpacing(espaco.linha())
            formularios[secao] = formulario
            self.abas.addTab(pagina, titulo)
        for campo in configuracoes.CAMPOS:
            secao = ABA_DO_LEITOR_LOCAL if campo.secao == "local_reader" else campo.secao
            controle = self._controle(campo)
            self._controles[campo.chave] = controle
            rotulo = QLabel(campo.rotulo, self)
            rotulo.setBuddy(controle)
            formularios[secao].addRow(rotulo, controle)

        self.lbl_onde = QLabel(
            f"Gravado em {preferencias.DEFAULT_SETTINGS_PATH}. Vale a partir do próximo uso: "
            "o próximo treino, a próxima página lida.",
            self,
        )
        self.lbl_onde.setProperty(folha_de_estilo.PROPRIEDADE_DE_APOIO, "true")
        self.lbl_onde.setWordWrap(True)
        fora.addWidget(self.lbl_onde)

        self.botoes = QDialogButtonBox(self)
        self.btn_salvar = self.botoes.addButton("Salvar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_cancelar = self.botoes.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_padroes = self.botoes.addButton("Restaurar padrões", QDialogButtonBox.ButtonRole.ResetRole)
        for botao, nome, papel in (
            (self.btn_salvar, "Salvar as configurações", estilos.PRIMARIO),
            (self.btn_cancelar, "Cancelar", estilos.NEUTRO),
            (self.btn_padroes, "Restaurar os padrões de fábrica", estilos.NEUTRO),
        ):
            botao.setAccessibleName(nome)
            tema.aplicar_papel(botao, papel)
        self.botoes.accepted.connect(self.accept)
        self.botoes.rejected.connect(self.reject)
        self.btn_padroes.clicked.connect(lambda _marcado=False: self.preencher(preferencias.Settings()))
        fora.addWidget(self.botoes)

        self.preencher(self._inicial)

    # ------------------------------------------------------------------ um controle por tipo

    def _controle(self, campo: configuracoes.Campo) -> QWidget:
        tipo = campo.tipo
        if tipo == configuracoes.INTEIRO:
            caixa = QSpinBox(self)
            caixa.setRange(int(campo.minimo or 0), int(campo.maximo or 1_000_000))
            caixa.setSingleStep(int(campo.passo or 1))
            controle: QWidget = caixa
        elif tipo == configuracoes.DECIMAL:
            decimal = QDoubleSpinBox(self)
            decimal.setDecimals(campo.decimais)
            decimal.setRange(float(campo.minimo or 0.0), float(campo.maximo or 1e9))
            decimal.setSingleStep(float(campo.passo or 0.1))
            controle = decimal
        elif tipo == configuracoes.INTERRUPTOR:
            controle = QCheckBox(self)
        elif tipo == configuracoes.ESCOLHA:
            escolha = QComboBox(self)
            escolha.addItems(list(campo.opcoes))
            controle = escolha
        elif tipo == configuracoes.CAMINHO:
            controle = _CampoDeCaminho(self, campo.rotulo)
        else:  # TEXTO e LISTA
            controle = QLineEdit(self)
        controle.setAccessibleName(campo.rotulo)
        if campo.ajuda:
            dica_em(controle, campo.ajuda)
        return controle

    # ------------------------------------------------------------------------- ler e escrever

    def preencher(self, configuracao: preferencias.Settings) -> None:
        """Poe um `Settings` nos controles. E o que *Restaurar padroes* faz com `Settings()`."""
        for campo in configuracoes.CAMPOS:
            valor = configuracoes.ler(configuracao, campo)
            controle = self._controles[campo.chave]
            if isinstance(controle, QSpinBox):
                controle.setValue(int(valor))
            elif isinstance(controle, QDoubleSpinBox):
                controle.setValue(float(valor))
            elif isinstance(controle, QCheckBox):
                controle.setChecked(bool(valor))
            elif isinstance(controle, QComboBox):
                posicao = controle.findText(str(valor))
                if posicao < 0:
                    controle.addItem(str(valor))
                    posicao = controle.count() - 1
                controle.setCurrentIndex(posicao)
            elif isinstance(controle, _CampoDeCaminho):
                controle.definir(str(valor))
            elif isinstance(controle, QLineEdit):
                texto = ", ".join(valor) if isinstance(valor, tuple | list) else str(valor)
                controle.setText(texto)

    def valores(self) -> preferencias.Settings:
        """O `Settings` que a tela descreve agora -- o inicial com os controles por cima."""
        lidos: dict[str, Any] = {}
        for campo in configuracoes.CAMPOS:
            controle = self._controles[campo.chave]
            if isinstance(controle, QSpinBox | QDoubleSpinBox):
                lidos[campo.chave] = controle.value()
            elif isinstance(controle, QCheckBox):
                lidos[campo.chave] = controle.isChecked()
            elif isinstance(controle, QComboBox):
                lidos[campo.chave] = controle.currentText().strip()
            elif isinstance(controle, _CampoDeCaminho):
                lidos[campo.chave] = controle.texto()
            elif isinstance(controle, QLineEdit):
                texto = controle.text().strip()
                if campo.tipo == configuracoes.LISTA:
                    lidos[campo.chave] = tuple(p.strip() for p in texto.split(",") if p.strip())
                else:
                    lidos[campo.chave] = texto
        return configuracoes.trocar(self._inicial, lidos)

    def accept(self) -> None:
        if self._ao_salvar is not None:
            self._ao_salvar(self.valores())
        super().accept()


class _CampoDeCaminho(QWidget):
    """Um `QLineEdit` com *Escolher…* ao lado. Pasta ou arquivo, decidido pelo rótulo."""

    def __init__(self, pai: QWidget, rotulo: str) -> None:
        super().__init__(pai)
        self._pasta = "pasta" in rotulo.lower()
        linha = QHBoxLayout(self)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(espaco.linha())
        self.campo = QLineEdit(self)
        self.campo.setAccessibleName(rotulo)
        self.btn = QPushButton("Escolher…", self)
        self.btn.setAccessibleName(f"Escolher: {rotulo}")
        tema.aplicar_papel(self.btn, estilos.NEUTRO)
        self.btn.clicked.connect(lambda _marcado=False: self._escolher())
        linha.addWidget(self.campo, 1)
        linha.addWidget(self.btn)

    def setAccessibleName(self, nome: str) -> None:  # noqa: N802 - API do Qt
        super().setAccessibleName(nome)
        self.campo.setAccessibleName(nome)

    def _escolher(self) -> None:
        if self._pasta:
            escolhido = QFileDialog.getExistingDirectory(self, "Escolher a pasta", self.campo.text())
        else:
            escolhido, _filtro = QFileDialog.getOpenFileName(self, "Escolher o arquivo", self.campo.text())
        if escolhido:
            self.campo.setText(escolhido)

    def definir(self, texto: str) -> None:
        self.campo.setText(texto)

    def texto(self) -> str:
        return self.campo.text().strip()


def abrir(pai: QWidget | None, *, dizer: Callable[[str], None] | None = None) -> DialogoDeConfiguracoes:
    """Le o arquivo, abre a janela e grava ao salvar. Devolve o dialogo (modal por `exec`)."""

    def gravar(novo: preferencias.Settings) -> None:
        preferencias.save_settings(preferencias.DEFAULT_SETTINGS_PATH, novo)
        if dizer is not None:
            dizer(f"Configurações gravadas em {preferencias.DEFAULT_SETTINGS_PATH.name}.")

    dialogo = DialogoDeConfiguracoes(pai, configuracao=preferencias.load_settings(), ao_salvar=gravar)
    dialogo.exec()
    return dialogo
