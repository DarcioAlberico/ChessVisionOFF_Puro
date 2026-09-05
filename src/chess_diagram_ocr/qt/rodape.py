"""O rodapé do segundo frontend: mensagem, documento, dispositivos e operação (S-163/S-501).

**A decisão não é reescrita.** Severidade, expiração e as três descrições vêm de
`ui/estado_do_rodape.py`, que é puro desde a S-501 justamente para isto: as duas janelas do mesmo
produto não podem discordar sobre o que é um erro. Copiar a tabela de `MARCAS_DE_ERRO` daria uma
janela dizendo "isto falhou" em vermelho e a outra dizendo o mesmo em cinza -- que é o defeito 3
do cabeçalho de `ui/rodape.py`, agora entre frontends.

**As quatro zonas e a ordem delas são as de lá**, e a razão é a mesma: a mensagem é a única que
cede espaço. No Tk isso é a ordem do `pack`; aqui é o `stretch` do `QHBoxLayout` -- a mensagem
leva 1 e as outras 0, e por isso uma mensagem longa encolhe a si mesma em vez de empurrar para
fora o livro e a página, que é o que a pessoa consulta o tempo todo.

**A altura é fixa por construção, e não por pixel cravado.** Todo widget existe sempre; o que
muda é texto, cor e estado. Nada aparece nem desaparece, então nada muda a altura -- e é por isso
que a barra de progresso e o botão de cancelar ficam desabilitados em vez de escondidos.

---

**O `QStatusBar` foi considerado e não serve.** Ele traz uma mensagem temporária e um canto de
widgets permanentes, o que cobriria duas das quatro zonas -- mas a mensagem dele não tem
severidade nem prazo por severidade, e `showMessage(texto, ms)` só aceita um prazo por chamada,
o que devolveria a expiração para o ponto de chamada. `EXPIRACAO_MS` diz que erro **não expira**,
e essa é uma decisão do projeto que não pode virar um argumento que alguém esquece.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.ui import espaco, estilos, tipografia, tokens
from chess_diagram_ocr.ui.busy import BusyOperation
from chess_diagram_ocr.ui.estado_do_rodape import (
    DETERMINADO,
    FOLGA_ENTRE_ZONAS,
    INDETERMINADO,
    INTERVALO_DE_ACOMPANHAMENTO_MS,
    LARGURA_DA_BARRA,
    LARGURA_MINIMA_DA_MENSAGEM,
    PAPEL_DE_TEXTO,
    PARADO,
    Dispositivos,
    compor,
    descricao_dos_dispositivos,
    expira_em_ms,
    ocupacao,
    papel_do_documento,
)

logger = logging.getLogger(__name__)

__all__ = ["DICA_DO_CANCELAR", "RodapeDaJanela", "ZonaDaMensagem"]

DICA_DO_CANCELAR = (
    "Só fica ativo quando há operação longa que sabe parar limpo.\n"
    "Cancelar aqui vale para todas as que estiverem rodando."
)
"""O mesmo texto do outro rodapé, e a igualdade é o item: uma dica que explicasse o botão de um
jeito numa janela e de outro na outra seria duas respostas para a mesma pergunta."""


class ZonaDaMensagem(QLabel):
    """A zona de mensagem: um rótulo que **cede largura em vez de exigi-la** (S-552, 5ª rodada).

    **O defeito, e ele é de janela e não de rodapé.** Um `QLabel` de uma linha responde, como
    mínimo, a largura do **texto inteiro** -- `QLabel::minimumSizeHint` é `sizeForWidth(0)`, e sem
    quebra de linha isso é a frase medida de ponta a ponta. Esse mínimo sobe pelo `QHBoxLayout` do
    rodapé, pelo `QVBoxLayout` da janela e chega ao `minimumSizeHint` dela. Medido a 1024x768 com
    frases de 120, 200, 300, 600 e 2000 caracteres, o piso da janela ia a **1057, 1457, 1957, 3457
    e 10457 px** -- e `resize(1024, 768)` era recusado até chegar uma frase menor.

    E o caminho não é hipotético: o erro de modelo ausente tem ~600 caracteres e é escrito por
    `janela._falhou` -> `_dizer`. **A mensagem que ensina a consertar o modelo tornava a janela
    maior que a tela e a si mesma ilegível.**

    **`setWordWrap` não serve, e essa foi a primeira tentativa.** Ele troca largura por altura: o
    mínimo horizontal cai para a maior palavra, mas o vertical passa a ser a altura do texto
    quebrado na largura mais estreita possível -- e o rodapé, cuja altura é fixa por construção
    (ver o cabeçalho deste módulo), viraria uma faixa de doze linhas na mesma frase de 600
    caracteres. Trocar um piso de largura por um de altura não é consertar.

    **O que serve são três coisas juntas**, e nenhuma delas sozinha:

    1. **Um teto declarado de exigência** (`LARGURA_MINIMA_DA_MENSAGEM`). `sizeHint` e
       `minimumSizeHint` param de falar do texto e passam a falar da zona; a largura de fato vem do
       esticamento, que é o que sempre decidiu quem cede espaço aqui.
    2. **Elisão à direita** (`QFontMetrics.elidedText`), refeita a cada `resizeEvent`. **À direita
       e não no meio**: numa frase de erro o começo é o que a classifica -- é dele que
       `estado_do_rodape.severidade_de` tira a severidade --, e `"Não foi possível…"` diz o que
       `"…em C:/modelos/piece_classifier.pt"` não diz.
    3. **A frase inteira na dica.** Elidir sem isso seria esconder a instrução em vez de encurtá-la;
       com isso, o rodapé mostra o começo e o ponteiro parado revela o resto.

    `frase()` devolve o que foi escrito e `text()` o que está na tela -- e são coisas diferentes
    desde esta rodada, e é por isso que `RodapeDaJanela.mensagem()` pergunta pela primeira.
    """

    def __init__(self, parent: QWidget | None = None, *, largura_minima: int = LARGURA_MINIMA_DA_MENSAGEM) -> None:
        super().__init__("", parent)
        self._frase = ""
        self._largura_minima = max(1, int(largura_minima))
        # **O mínimo explícito é o que grampeia o item do leiaute**, e não só a dica: `qSmartMinSize`
        # usa `minimumSize()` por cima de `minimumSizeHint()` quando ele é positivo. Os dois estão
        # aqui de propósito -- o primeiro fecha o caminho do leiaute, o segundo faz o widget
        # responder a verdade quando alguém lhe pergunta direto.
        self.setMinimumWidth(self._largura_minima)

    def frase(self) -> str:
        """A mensagem inteira, como ela foi escrita -- antes da elisão."""
        return self._frase

    def definir_frase(self, frase: str) -> None:
        """Escreve a mensagem. O que couber vai para a tela; o resto, para a dica."""
        self._frase = str(frase)
        self._reescrever()

    def _reescrever(self) -> None:
        """Recorta a frase na largura de agora. Chamado ao escrever, ao redimensionar e ao repintar."""
        largura = max(0, self.contentsRect().width())
        recortada = self.fontMetrics().elidedText(self._frase, Qt.TextElideMode.ElideRight, largura)
        self.setText(recortada)
        # Dica só quando há o que revelar: uma dica repetindo o que já está na tela é ruído, e é o
        # mesmo critério de `dica_em` para texto vazio.
        dica_em(self, self._frase if recortada != self._frase else "")

    def resizeEvent(self, a0: QResizeEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(a0)
        self._reescrever()

    def sizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        """A largura da **zona**, e não a do texto. A altura continua sendo a de uma linha."""
        return QSize(self._largura_minima, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        """O mesmo, e é este que a janela lia como piso antes desta rodada."""
        return QSize(self._largura_minima, super().minimumSizeHint().height())


class RodapeDaJanela(QWidget):
    """O rodapé: irmão do painel principal, e não filho dele.

    Quem o cria põe-o por último no leiaute vertical da janela -- é isso que faz dele o último a
    ser cortado quando ela encolhe, em vez do primeiro (defeito 5 da S-163).
    """

    def __init__(self, parent: QWidget | None = None, *, cancelar: Callable[[], object] | None = None) -> None:
        super().__init__(parent)
        self._cancelar = cancelar
        self._severidade = ""
        """A severidade da mensagem que está na tela. Ver `_repintar_mensagem` (S-393)."""
        self._modo_da_barra = PARADO

        vertical = QVBoxLayout(self)
        vertical.setContentsMargins(0, 0, 0, 0)
        vertical.setSpacing(0)

        risco = QFrame(self)
        risco.setFrameShape(QFrame.Shape.HLine)
        vertical.addWidget(risco)

        linha = QHBoxLayout()
        # O 3 não está na escala de propósito, e a razão é a de `ui/rodape.py`: o rodapé é
        # deliberadamente fino, e ele fica entre `FOLGA_MINIMA` (2) e `FOLGA_DE_LINHA` (6) --
        # nenhum dos dois é o que ele quer. Inventar um quinto papel para servir a um sítio só
        # seria a escala deixando de descrever a janela (S-447).
        linha.setContentsMargins(espaco.folga(), 3, espaco.folga(), 3)
        linha.setSpacing(FOLGA_ENTRE_ZONAS)
        vertical.addLayout(linha)

        auxiliar = tema.fonte_atual(tipografia.AUXILIAR)

        # **A mensagem primeiro, e com `stretch=1`.** No Tk a ordem do `pack` é o que decide quem
        # cede espaço; aqui é o esticamento, e por isso a mensagem pode vir na ordem de leitura.
        #
        # E é uma `ZonaDaMensagem` e não um `QLabel` cru: um rótulo comum **exige** a largura do
        # texto inteiro, e o esticamento acima só reparte a sobra -- a exigência passava por baixo
        # dele e virava piso da janela. Ver a classe.
        self._lbl_mensagem = ZonaDaMensagem(self)
        self._lbl_mensagem.setFont(tema.fonte_atual(tipografia.CORPO))
        self._lbl_mensagem.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        linha.addWidget(self._lbl_mensagem, 1)

        # A quarta zona vem **à esquerda do documento** e não à direita: livro e página são o que
        # a pessoa consulta o tempo todo, e o dispositivo é o que ela olha uma vez por sessão.
        # Quem fica mais perto da mensagem é quem cede espaço primeiro.
        self._lbl_dispositivos = QLabel("", self)
        self._lbl_dispositivos.setFont(auxiliar)
        tema.pintar(self._lbl_dispositivos, "color", tokens.TEXTO_SECUNDARIO)
        linha.addWidget(self._lbl_dispositivos, 0)

        self._lbl_documento = QLabel("", self)
        self._lbl_documento.setFont(auxiliar)
        tema.pintar(self._lbl_documento, "color", tokens.TEXTO_SECUNDARIO)
        linha.addWidget(self._lbl_documento, 0)

        self._lbl_ocupacao = QLabel("", self)
        self._lbl_ocupacao.setFont(auxiliar)
        linha.addWidget(self._lbl_ocupacao, 0)

        self._barra = QProgressBar(self)
        self._barra.setFixedWidth(LARGURA_DA_BARRA)
        self._barra.setTextVisible(False)
        self._barra.setRange(0, 100)
        self._barra.setValue(0)
        linha.addWidget(self._barra, 0)

        self._btn_cancelar = QPushButton("Cancelar", self)
        tema.aplicar_papel(self._btn_cancelar, estilos.NEUTRO)
        self._btn_cancelar.setEnabled(False)
        self._btn_cancelar.clicked.connect(self._ao_cancelar)
        dica_em(self._btn_cancelar, DICA_DO_CANCELAR)
        linha.addWidget(self._btn_cancelar, 0)

        # **Um relógio só, e ele é de disparo único e rearmado.** Um `QTimer` repetitivo
        # continuaria disparando depois de a janela fechar e antes de o objeto morrer, e o
        # sintoma seria um `RuntimeError` sobre um rótulo já destruído -- o equivalente do
        # `after` órfão que a S-402 mediu no outro frontend.
        self._expiracao = QTimer(self)
        self._expiracao.setSingleShot(True)
        self._expiracao.timeout.connect(self._expirar)
        self._acompanhamento = QTimer(self)
        self._acompanhamento.setSingleShot(True)

        tema.ao_repintar(self._repintar_mensagem)

    # --------------------------------------------------------------------------- mensagem

    def mostrar(self, texto: str, *, origem: str = "", severidade: str | None = None) -> None:
        """Escreve na zona de mensagem, com a cor da severidade e o prazo dela.

        Chamado da linha de eventos. Quem está noutra thread passa por sinal -- é o que
        `qt/trabalho.Tarefa` já faz, e é a contraparte do `root.after` do outro frontend.
        """
        estado = compor(mensagem=texto, origem=origem, severidade=severidade)
        self._severidade = estado.severidade
        self._lbl_mensagem.definir_frase(estado.mensagem)
        self._repintar_mensagem()
        self._reagendar_expiracao(expira_em_ms(estado.severidade))

    def _repintar_mensagem(self) -> None:
        """A mensagem que está na tela, na cor da pele de agora (S-393).

        **A cor era resolvida na hora de escrever e nunca mais.** Trocar de pele com um erro no
        rodapé deixava o texto na cor da anterior: preto de erro sobre o cromo escuro, com 1,30:1
        de contraste -- abaixo dos 4,5:1 que a S-144 usa como régua. O defeito é do mesmo tipo
        nos dois toolkits, e a resposta também.
        """
        if not self._severidade:
            return
        try:
            cor = tema.cor_atual(PAPEL_DE_TEXTO[self._severidade])
            self._lbl_mensagem.setStyleSheet(f"color: {cor};")
            # A pele nova traz outra fonte, e o que cabia na anterior pode não caber mais: a
            # elisão é refeita aqui pela mesma razão que a cor -- ela foi resolvida na hora de
            # escrever, e a hora de escrever passou.
            self._lbl_mensagem.definir_frase(self._lbl_mensagem.frase())
        except RuntimeError:  # pragma: no cover - rodapé destruído entre a troca e a repintura
            return

    def mensagem(self) -> str:
        """O que está escrito na zona de mensagem agora.

        Existe para o roteiro headless do `CONTRIBUTING.md`, pela mesma razão de `ui/rodape.py`:
        um roteiro documentado que não roda é pior que nenhum.

        **A frase inteira, e não o que coube** (S-552, 5ª rodada): desde a `ZonaDaMensagem` o que
        está na tela pode estar elidido, e um roteiro que lesse a tela passaria a afirmar o
        tamanho da janela em vez do que o programa disse.
        """
        return self._lbl_mensagem.frase()

    def _reagendar_expiracao(self, prazo: int | None) -> None:
        self._expiracao.stop()
        if prazo is not None:
            self._expiracao.start(prazo)

    def _expirar(self) -> None:
        self._lbl_mensagem.definir_frase("")
        self._severidade = ""

    # ------------------------------------------------------------------ estado do documento

    def definir_documento(self, texto: str, todos_salvos: bool = False) -> None:
        """A zona do documento: livro, página e o que se sabe dos diagramas dela.

        Os dois parâmetros são posicionais para que o método **seja** o callback que o painel de
        PDF espera, sem um `lambda` de adaptação no meio -- é o contrato de `ui/rodape.py`.
        """
        self._lbl_documento.setText(texto)
        self._lbl_documento.setStyleSheet(f"color: {tema.cor_atual(papel_do_documento(todos_salvos))};")

    def documento(self) -> str:
        """O que a zona mostra agora. Existe pelo mesmo motivo que `mensagem()`."""
        return self._lbl_documento.text()

    # -------------------------------------------------------------- dispositivo dos modelos

    def definir_dispositivos(self, dispositivos: Dispositivos) -> None:
        """A zona dos dois modelos torch: o curto na tela, o longo na dica (S-182).

        Recebe as **descrições**, e não os objetos: o rodapé não importa `torch` nem sabe que
        existe um `OcrService`.
        """
        texto, dica = descricao_dos_dispositivos(
            dispositivos.pecas,
            dispositivos.caracteres,
            motivo=dispositivos.motivo,
            ausencia=dispositivos.ausencia,
        )
        self._lbl_dispositivos.setText(texto)
        dica_em(self._lbl_dispositivos, dica)

    def dispositivos(self) -> str:
        """O que a zona mostra agora. Existe pelo mesmo motivo que `mensagem()`."""
        return self._lbl_dispositivos.text()

    # -------------------------------------------------------------------- operação em curso

    def aplicar_ocupacao(self, operacoes: Sequence[BusyOperation]) -> None:
        """Põe na zona de operação o que o `BusyRegistry` diz que está rodando.

        A troca de modo é feita só quando ele muda: no Qt, reescrever o intervalo da barra
        indeterminada a cada tique reinicia a animação quatro vezes por segundo e ela parece
        travada -- o mesmo sintoma do `start()` repetido no Tk. O **valor** da determinada, ao
        contrário, é escrito em todo tique: é ele que anda.
        """
        atual = ocupacao(operacoes)
        try:
            self._lbl_ocupacao.setText(atual.texto)
            self._btn_cancelar.setEnabled(atual.cancelavel)
            if atual.modo != self._modo_da_barra:
                self._trocar_modo_da_barra(atual.modo)
            if atual.modo == DETERMINADO and atual.fracao is not None:
                self._barra.setValue(round(atual.fracao * 100.0))
        except RuntimeError as exc:  # pragma: no cover - rodapé destruído entre dois tiques
            logger.debug("Não foi possível atualizar a barra do rodapé: %s", exc)

    def _trocar_modo_da_barra(self, modo: str) -> None:
        self._modo_da_barra = modo
        if modo == INDETERMINADO:
            # `(0, 0)` é como o Qt diz "indeterminada". Não há `start()`/`stop()`: a animação é
            # consequência da faixa, e é por isso que a troca de modo é a única coisa a evitar
            # repetir.
            self._barra.setRange(0, 0)
            return
        self._barra.setRange(0, 100)
        self._barra.setValue(0)

    def acompanhar(
        self,
        operacoes: Callable[[], Sequence[BusyOperation]],
        *,
        dispositivos: Callable[[], Dispositivos] | None = None,
        intervalo_ms: int = INTERVALO_DE_ACOMPANHAMENTO_MS,
    ) -> None:
        """Relê o registro a cada `intervalo_ms`, até o rodapé ser destruído.

        O rodapé é quem pergunta, e não as sete operações que avisam: um `BusyToken` que se
        esquecesse de avisar deixaria a barra girando para sempre, e a S-112 registra que
        `release()` esquecido é o erro que de fato acontece.

        `dispositivos` entra **no mesmo tique**, e não num segundo relógio, porque a pergunta é
        da mesma natureza: nenhum dos dois modelos avisa quando muda.
        """
        self.aplicar_ocupacao(operacoes())
        if dispositivos is not None:
            self.definir_dispositivos(dispositivos())
        # Religado a cada volta em vez de repetitivo: o relógio é filho do rodapé, então ele
        # morre junto -- e um disparo único que já passou não fica pendente sobre um widget morto.
        #
        # O `try` é porque `disconnect()` sem nada ligado **levanta** no Qt, em vez de ser uma
        # chamada sem efeito -- e a primeira volta é exatamente esse caso. Sem ele, o rodapé só
        # acompanharia a partir da segunda chamada, que nunca aconteceria.
        try:
            self._acompanhamento.timeout.disconnect()
        except TypeError:
            pass
        self._acompanhamento.timeout.connect(
            lambda: self.acompanhar(operacoes, dispositivos=dispositivos, intervalo_ms=intervalo_ms)
        )
        self._acompanhamento.start(intervalo_ms)

    def _ao_cancelar(self) -> None:
        if self._cancelar is not None:
            self._cancelar()
