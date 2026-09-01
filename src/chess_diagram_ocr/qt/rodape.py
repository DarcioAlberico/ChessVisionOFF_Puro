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

from PyQt6.QtCore import Qt, QTimer
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

__all__ = ["DICA_DO_CANCELAR", "RodapeDaJanela"]

DICA_DO_CANCELAR = (
    "Só fica ativo quando há operação longa que sabe parar limpo.\n"
    "Cancelar aqui vale para todas as que estiverem rodando."
)
"""O mesmo texto do outro rodapé, e a igualdade é o item: uma dica que explicasse o botão de um
jeito numa janela e de outro na outra seria duas respostas para a mesma pergunta."""


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
        self._lbl_mensagem = QLabel("", self)
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
        self._lbl_mensagem.setText(estado.mensagem)
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
        except RuntimeError:  # pragma: no cover - rodapé destruído entre a troca e a repintura
            return

    def mensagem(self) -> str:
        """O que está escrito na zona de mensagem agora.

        Existe para o roteiro headless do `CONTRIBUTING.md`, pela mesma razão de `ui/rodape.py`:
        um roteiro documentado que não roda é pior que nenhum.
        """
        return self._lbl_mensagem.text()

    def _reagendar_expiracao(self, prazo: int | None) -> None:
        self._expiracao.stop()
        if prazo is not None:
            self._expiracao.start(prazo)

    def _expirar(self) -> None:
        self._lbl_mensagem.setText("")
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
