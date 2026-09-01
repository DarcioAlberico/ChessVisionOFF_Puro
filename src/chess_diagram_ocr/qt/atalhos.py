"""Os atalhos do segundo frontend: a mesma tabela, a mesma guarda, outro toolkit (S-501).

**A tabela não é reescrita, e é o item.** `ui/atalhos.py` continua sendo o único lugar do projeto
que escreve tecla -- é a regra que `test_ui_legenda.test_so_a_tabela_escreve_sequencia_de_tecla`
cobra --, e ela escreve na linguagem do Tk (`"<Control-s>"`). O que este módulo faz é **traduzir**,
numa função pura de 20 linhas. Declarar as vinte e uma teclas de novo em `QKeySequence` daria duas
tabelas para manter, e a segunda divergiria no primeiro remapeamento -- que é exatamente o defeito
que `ACOES_DO_CAMPO` documenta ao declarar ação em vez de tecla.

**Por que um filtro de eventos e não `QShortcut`.** A guarda da S-20 precisa de três respostas
para uma tecla: *trate e consuma*, *ceda ao campo em foco*, *ceda a quem declarou a tecla para si*.
Em Tk isso é o par `"break"` / `None` que `shortcuts.guard` devolve. O `QShortcut` só tem a
primeira: ele dispara antes do widget em foco e não tem como devolver a tecla depois -- ceder `←`
ao campo de FEN exigiria reenviar o evento à mão, e um evento reenviado chega com a ordem de
processamento trocada.

Um `eventFilter` na aplicação vê a tecla **antes** do widget em foco e responde `True` (consumi) ou
`False` (siga), que é o mesmo par de respostas com outros nomes. A guarda passa a ser a mesma
função nos dois frontends, e a única coisa que muda de lado é a lista de classes que contam como
campo de texto.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QKeyEvent, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from chess_diagram_ocr.ui import atalhos

logger = logging.getLogger(__name__)

__all__ = [
    "MULTILINHA",
    "TECLAS_NOMEADAS",
    "WIDGETS_DE_TEXTO",
    "GuardaDeAtalhos",
    "cede_a_tecla",
    "contem",
    "e_campo_de_texto",
    "ligar",
    "sequencia_qt",
]


def contem(painel: object, widget: object) -> bool:
    """Aquele widget está dentro deste painel? É o `contem` de `ui/desfazivel.Desfazivel` (S-243).

    **Um lugar só, e não um por painel.** Três painéis disputam o `Ctrl+Z` e os três precisam
    responder isto; três laços iguais é onde um deles deixa de subir por `parentWidget` e a tecla
    passa a fazer coisa diferente naquele painel, sem sintoma nenhum.

    Sobe pelo `parentWidget` em vez de usar `isAncestorOf` porque este módulo é chamado com objetos
    de mentira nos testes -- a mesma razão do duck typing de `ui/atalhos._cadeia`, e a razão de o
    parâmetro ser `object`.
    """
    atual = widget
    for _ in range(40):
        if atual is None:
            return False
        if atual is painel:
            return True
        pai = getattr(atual, "parentWidget", None)
        atual = pai() if callable(pai) else None
    return False

WIDGETS_DE_TEXTO: tuple[type, ...] = (
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QComboBox,
    QAbstractSpinBox,
)
"""Widgets em que as teclas de navegação são do widget, não do app.

São os equivalentes de `shortcuts.TEXT_ENTRY_WIDGETS`, um a um: `QLineEdit` é o `Entry`,
`QTextEdit`/`QPlainTextEdit` são o `tk.Text`, e `QComboBox` é o `ttk.Combobox`.

`QAbstractSpinBox` e não `QSpinBox` porque ele é a base de `QSpinBox`, `QDoubleSpinBox` e
`QDateTimeEdit` -- e a razão de o `ttk.Spinbox` estar na lista de lá vale para os três: as setas
dentro dele já incrementam o número, e deixar o atalho passar mudaria o diagrama duas vezes por
tecla."""

MULTILINHA: tuple[type, ...] = (QTextEdit, QPlainTextEdit)
"""Os que rolam. `PgUp`/`PgDn` são deles; num campo de uma linha essas teclas não fazem nada."""

TECLAS_NOMEADAS: dict[str, str] = {
    "Left": "Left",
    "Right": "Right",
    "Up": "Up",
    "Down": "Down",
    "Home": "Home",
    "End": "End",
    "Prior": "PgUp",
    "Next": "PgDown",
    "Delete": "Del",
    "BackSpace": "Backspace",
    "Return": "Return",
    "KP_Enter": "Enter",
    "Escape": "Esc",
    "Tab": "Tab",
    "space": "Space",
    "plus": "+",
    "minus": "-",
}
"""`nome do Tk -> nome do Qt`, para as teclas que os dois chamam de coisas diferentes.

Só as que divergem. `Home`, `End`, `Tab` e as setas estão aqui por completude -- e porque uma
tabela em que só cabe a exceção obriga quem lê a saber de cor quais são as exceções.

**As três que de fato mordem** são `Prior`/`Next` (o Tk herdou os nomes do X11; o Qt usa `PgUp`
e `PgDown`), `Delete` (`Del` no Qt) e o par `plus`/`minus`, que no Tk são nomes e no Qt são o
próprio caractere."""


def sequencia_qt(sequencia: str) -> str:
    """Uma sequência do Tk escrita como o `QKeySequence` a quer. Pura: não toca Qt nem widget.

    `"<Control-s>"` vira `"Ctrl+S"`; `"<Prior>"` vira `"PgUp"`.

    **A letra maiúscula é `Shift`, e essa é a regra que não se pode adivinhar.** No Tk,
    `<Control-S>` e `<Control-s>` são teclas *diferentes*: a maiúscula quer dizer `Ctrl+Shift+S`.
    A tabela usa as duas -- `salvar` é `<Control-s>` e `salvar_todos` é `<Control-S>` --, e um
    tradutor que aplicasse `.upper()` sem olhar transformaria os dois no mesmo atalho e faria
    "salvar todos" apagar "salvar" sem erro nenhum a que se agarrar.

    Levanta `ValueError` para sequência que não é do formato `<...>`, e não devolve string vazia:
    uma tecla que não traduz e vira `""` sai como um `QKeySequence` inválido, que não dispara e não
    reclama -- um atalho que simplesmente não existe é o defeito mais caro deste módulo.
    """
    if not (sequencia.startswith("<") and sequencia.endswith(">")):
        raise ValueError(f"sequência do Tk precisa ser <...>; recebido {sequencia!r}")

    partes = sequencia[1:-1].split("-")
    *modificadores, tecla = partes
    if not tecla:  # `<Control-->` e afins: o traço final deixa a última parte vazia
        raise ValueError(f"sequência sem tecla: {sequencia!r}")

    pedacos = []
    for modificador in modificadores:
        nome = {"Control": "Ctrl", "Alt": "Alt", "Shift": "Shift", "Meta": "Meta"}.get(modificador)
        if nome is None:
            raise ValueError(f"modificador desconhecido em {sequencia!r}: {modificador!r}")
        pedacos.append(nome)

    if tecla in TECLAS_NOMEADAS:
        pedacos.append(TECLAS_NOMEADAS[tecla])
    elif len(tecla) == 1 and tecla.isalpha():
        # Ver o docstring: maiúscula é Shift, e `Shift` explícito na sequência não se duplica.
        if tecla.isupper() and "Shift" not in pedacos:
            pedacos.append("Shift")
        pedacos.append(tecla.upper())
    elif len(tecla) == 1:
        pedacos.append(tecla)
    elif tecla.startswith("F") and tecla[1:].isdigit():
        pedacos.append(tecla)
    else:
        raise ValueError(f"tecla desconhecida em {sequencia!r}: {tecla!r}")
    return "+".join(pedacos)


def e_campo_de_texto(widget: object) -> bool:
    """Este widget é campo de texto? Ver `cede_a_tecla`, que é quem decide o que ceder.

    É o `shortcuts.ignores_widget` deste lado, e como lá ele **sozinho não decide mais nada**: a
    razão é a S-294, e ceder todas as teclas a um campo desligava nove atalhos que campo de texto
    nenhum usa.
    """
    return isinstance(widget, WIDGETS_DE_TEXTO)


def cede_a_tecla(widget: object, sequencia: str) -> bool:
    """A guarda deve ceder **esta tecla** a este widget?

    A decisão é `atalhos.cede_a_sequencia`, que é pura e vale nos dois frontends; o que este
    módulo acrescenta são as duas listas de classe do Qt. É a mesma divisão de
    `ui/shortcuts.cede_a_tecla`, e é o que garante que `Ctrl+S` salva com o cursor dentro do
    campo nas duas janelas -- ou em nenhuma.
    """
    return atalhos.cede_a_sequencia(
        sequencia,
        e_campo=e_campo_de_texto(widget),
        e_multilinha=isinstance(widget, MULTILINHA),
    )


class GuardaDeAtalhos(QObject):
    """O filtro que vê a tecla antes do widget em foco e decide quem fica com ela.

    É o `bind_all` + `shortcuts.guard` do Tk, numa peça só. A ordem das três perguntas é a de lá,
    e ela **não** é arbitrária -- está medida na S-323:

    1. *O campo em foco usa esta tecla?* (`cede_a_tecla`) Se sim, cede. Vem primeiro para que
       nenhum painel precise lembrar de excluir os campos dele: a regra da S-20 vale sempre.
    2. *O painel em foco declarou esta ação para si?* (`atalhos.destino`, S-244) Se sim, é dele.
       É por aqui que `←` continua sendo "lance anterior" dentro da sala de estudo.
    3. Senão, é da janela.
    """

    def __init__(self, comandos: Mapping[str, Callable[[], object]], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._comandos = dict(comandos)
        # `sequência do Tk -> QKeySequence`, montado uma vez. Traduzir a cada tecla pressionada
        # seria refazer a mesma conta a 30 Hz enquanto alguém segura uma seta.
        self._teclas: dict[str, QKeySequence] = {}
        for atalho in atalhos.ATALHOS:
            if atalho.acao not in self._comandos:
                continue
            try:
                self._teclas[atalho.sequencia] = QKeySequence(sequencia_qt(atalho.sequencia))
            except ValueError as exc:
                # Uma tecla que não traduz não pode custar as outras vinte: ela sai no log com o
                # nome, e o resto da janela continua com teclado. É a disciplina de `folha.aplicar`.
                logger.warning("Atalho %s não traduzido para o Qt (%s).", atalho.sequencia, exc)

    def sequencia_do_evento(self, evento: QKeyEvent) -> str:
        """A sequência do **Tk** que este evento casa, ou `""`. É a tradução no sentido inverso.

        Compara `QKeySequence` e não texto: o Qt normaliza `Ctrl+Shift+S` e `Ctrl+S` com o
        modificador de shift de maneiras que a comparação de string erra em teclado não-ABNT.
        """
        combinacao = QKeySequence(evento.keyCombination())
        for sequencia, tecla in self._teclas.items():
            if tecla == combinacao:
                return sequencia
        return ""

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:  # noqa: N802 - assinatura do Qt
        """`True` consome a tecla; `False` a deixa seguir. É o `"break"` / `None` do Tk.

        O `except` largo é deliberado, e é a mesma razão de `qt/trabalho.py`: aqui é a borda do
        laço de eventos. Uma exceção que escapa de um filtro instalado na aplicação sobe para o
        `sys.excepthook`, e num processo sem console isso não vai a lugar nenhum -- o sintoma
        seria uma tecla que às vezes não faz nada, sem uma linha de log a que se agarrar.
        """
        if a1 is None or a1.type() != QEvent.Type.KeyPress or not isinstance(a1, QKeyEvent):
            return False
        try:
            sequencia = self.sequencia_do_evento(a1)
            if not sequencia:
                return False

            foco = QApplication.focusWidget()
            if cede_a_tecla(foco, sequencia):
                return False

            acao = atalhos.acao_de(sequencia)
            atendida = atalhos.destino(acao, foco, self._comandos) if acao else None
            if atendida is None:
                return False
            atendida()
            return True
        except Exception:  # noqa: BLE001 - ver o docstring: é a borda do laço de eventos
            logger.exception("O atalho falhou e a tecla foi devolvida à janela.")
            return False


def ligar(
    janela: QWidget,
    comandos: Mapping[str, Callable[[], object]],
    *,
    aplicacao: QApplication | None = None,
) -> GuardaDeAtalhos:
    """Liga os atalhos da tabela na janela inteira, sob a guarda de foco.

    Devolve a guarda, e **quem chama tem de guardá-la**: um `QObject` sem referência em Python é
    coletado, e um filtro coletado deixa de ser chamado sem que nada avise -- a janela
    simplesmente perde o teclado. Por isso ela nasce filha da janela, o que já a mantém viva, e
    ainda assim é devolvida: quem quiser desligá-la precisa do objeto.

    Comando que a tabela não declara é ignorado em silêncio, ao contrário de `atalhos.ligacoes`,
    que levanta nomeando o que falta. A diferença é o alcance: lá se liga a tabela **inteira** e
    um buraco é defeito; aqui a versão de teste implementa uma parte do fluxo de propósito, e
    exigir os vinte e um comandos obrigaria a inventar dezenove funções vazias.
    """
    guarda = GuardaDeAtalhos(comandos, parent=janela)
    alvo = aplicacao or QApplication.instance()
    if alvo is None:  # pragma: no cover - ligar atalho sem aplicação é erro de ordem
        logger.warning("Sem QApplication: os atalhos não foram ligados.")
        return guarda
    alvo.installEventFilter(guarda)
    return guarda
