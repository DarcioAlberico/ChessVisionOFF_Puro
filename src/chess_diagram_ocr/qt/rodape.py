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

**A altura é fixa por construção, e não por pixel cravado.** A altura da linha é a do **botão de
cancelar**, que existe sempre -- desabilitado quando não há o que cancelar. É por isso que o
rodapé não muda de altura quando uma operação começa.

**A barra de progresso é a exceção, e ela foi paga caro** (F9-C3). O parágrafo acima dizia "nada
aparece nem desaparece" e a barra era o preço: ela nascia `visivel=True, 0 de 100, sem texto` e
**nunca** se escondia -- não havia um `setVisible` neste arquivo. Nas 36 capturas do ciclo 2 ela é
um retângulo vazio de 120×26 no canto inferior direito, com borda de 1 px e raio de 4, desenhado
como um campo de texto vazio ao lado de um `Cancelar` cinzento. Ela some agora quando não há
operação (`estado_do_rodape.Ocupacao.mostra_barra`), e a altura não muda porque quem a sustenta é
o botão.

---

**O `QStatusBar` foi considerado e não serve.** Ele traz uma mensagem temporária e um canto de
widgets permanentes, o que cobriria duas das quatro zonas -- mas a mensagem dele não tem
severidade nem prazo por severidade, e `showMessage(texto, ms)` só aceita um prazo por chamada,
o que devolveria a expiração para o ponto de chamada. `EXPIRACAO_MS` diz que erro **não expira**,
e essa é uma decisão do projeto que não pode virar um argumento que alguém esquece.
"""

from __future__ import annotations

import logging
import weakref
from collections.abc import Callable, Sequence

from PyQt6 import sip
from PyQt6.QtCore import Qt, QTime, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.rotulo import RotuloElidido
from chess_diagram_ocr.ui import espaco, estilos, strings, tipografia, tokens
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
    Mensagens,
    compor,
    descricao_dos_dispositivos,
    expira_em_ms,
    ocupacao,
    papel_do_documento,
)

logger = logging.getLogger(__name__)

__all__ = ["DICA_DO_CANCELAR", "LARGURA_DA_MENSAGEM", "RodapeDaJanela"]

LARGURA_DA_MENSAGEM = 480
"""Quanto a mensagem **tem garantido** enquanto está na tela: cerca de setenta caracteres.

Com `stretch=1` o Qt a encolhe **primeiro**: no leiaute de caixa, um item esticável entra no
aperto com o mínimo como largura desejada (`QLayoutStruct.smartSizeHint`), e o mínimo dela era
zero. O crítico da fase 5 do ciclo 2 mediu: com o livro de nome de 149 caracteres, a 1248x640 e a
1366x728, a mensagem ficava com **0 px** e o nome do livro com 985 -- toda mensagem de erro
sumia. Sem mensagem, o mínimo volta a zero e o nome do livro fica com o espaço."""

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

    ocupacao_mudou = pyqtSignal()
    """O registro avisou que algo começou ou terminou. **Só existe para trocar de thread** (F9-C4).

    `BusyRegistry.observe` chama de quem registrou -- e quem registra é a thread de trabalho.
    Tocar num `QWidget` de lá é o erro clássico do Qt. Um sinal com conexão automática entre
    threads diferentes é entregue **na fila da thread do receptor**, que é a da janela: é o menor
    mecanismo que faz o aviso chegar no lugar certo, e é `qt/` fazendo o que só `qt/` pode fazer.
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
        # **Elidida, e é o defeito do nome do livro no terceiro lugar** (OCR_UI ciclo 2, C18). Um
        # `QLabel` comum pede como largura mínima a frase inteira, e a frase do rodapé é o texto
        # mais variável da janela: medido com um livro aberto, uma frase sozinha subia o mínimo da
        # janela para 1.246 px -- cada mensagem longa empurrava a janela para fora de um portátil
        # a 150 %. A frase inteira fica na dica, em `mensagem()` e na lista das últimas cinquenta.
        self._lbl_mensagem = RotuloElidido("", self, largura_desejada=0)
        self._lbl_mensagem.setFont(tema.fonte_atual(tipografia.CORPO))
        self._lbl_mensagem.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        linha.addWidget(self._lbl_mensagem, 1)

        # **As últimas cinquenta, atrás de um botão** (OCR_UI ciclo 2, passo A10). O que expirou
        # da zona de mensagem deixava de existir; agora fica em `mensagens` e abre numa lista,
        # sem modal -- é uma janela de consulta, e a pessoa a fecha quando quiser.
        self.mensagens = Mensagens()
        self._btn_mensagens = QPushButton(strings.MENSAGENS_ANTERIORES, self)
        self._btn_mensagens.setAccessibleName(strings.MENSAGENS_ANTERIORES_TITULO)
        tema.aplicar_papel(self._btn_mensagens, estilos.NEUTRO)
        self._btn_mensagens.clicked.connect(self.abrir_mensagens)
        dica_em(self._btn_mensagens, "As últimas mensagens desta sessão, inclusive as que já saíram daqui.")
        # **O mínimo do botão é o dele** (OCR_UI ciclo 2, fase 5, portão da janela estendido).
        # Havia um piso de um pixel, para o botão não subir a largura mínima da janela; mas quem
        # cede nesta linha são os rótulos elididos, e um botão de 27 px não mostra o que abre.
        # Com a mensagem no piso dela e uma importação em curso (ocupação e barra na linha), o
        # portão mediu o botão com 27 dos 82 px, com a janela no mínimo e em todas as áreas. Sem o
        # piso de um pixel, o mínimo do rodapé sobe a largura do botão e continua abaixo de 950 px
        # com tudo à vista; quem decide a largura mínima da janela continua sendo o modo (1248).
        linha.addWidget(self._btn_mensagens, 0)
        self._janela_de_mensagens: QDialog | None = None

        # A quarta zona vem **à esquerda do documento** e não à direita: livro e página são o que
        # a pessoa consulta o tempo todo, e o dispositivo é o que ela olha uma vez por sessão.
        # Quem fica mais perto da mensagem é quem cede espaço primeiro.
        # Elidido pelo mesmo motivo da mensagem (C18): a descrição dos dispositivos cresce com o
        # motivo de uma ausência, e nenhum texto do rodapé decide a largura da janela.
        self._lbl_dispositivos = RotuloElidido("", self, largura_desejada=0)
        self._lbl_dispositivos.setFont(auxiliar)
        tema.pintar(self._lbl_dispositivos, "color", tokens.TEXTO_SECUNDARIO)
        linha.addWidget(self._lbl_dispositivos, 0)

        # **Elidido, e é o mesmo defeito nº 2 da crítica do ciclo 1 num segundo lugar.** A zona
        # do documento escreve `<livro> · p. 121 de 289 · ...`, e com o nome de 149 caracteres da
        # pasta `PDF/` ela pedia **996 px** de largura mínima -- sozinha, ela ainda subia o
        # `minimumSizeHint` da janela para 1513 px depois de a barra do visor já estar consertada.
        # O nome inteiro fica na dica; a frase inteira está no `documento()`, que é o que o teste
        # lê.
        # **`largura_desejada=0`: peça o texto inteiro** (F9-C7, §4.1). Com o teto de 130 px --
        # que é da barra do visor, onde ele evita refluxo -- este rótulo recebia 130 px, pedia
        # 313 e desenhava `'1937 Kemeri…esta página'` **com 1534 px livres na mesma faixa**. O
        # `minimumSizeHint` continua zero, então o nome de 149 caracteres continua sem decidir a
        # largura mínima da janela; o que muda é que, havendo folga, ele a usa.
        self._lbl_documento = RotuloElidido("", self, largura_desejada=0)
        self._lbl_documento.setFont(auxiliar)
        self._lbl_documento.setProperty(tipografia.PROPRIEDADE_TABULAR, "true")
        tema.pintar(self._lbl_documento, "color", tokens.TEXTO_SECUNDARIO)
        linha.addWidget(self._lbl_documento, 0)

        self._lbl_ocupacao = RotuloElidido("", self, largura_desejada=0)
        self._lbl_ocupacao.setProperty(tipografia.PROPRIEDADE_TABULAR, "true")
        self._lbl_ocupacao.setFont(auxiliar)
        linha.addWidget(self._lbl_ocupacao, 0)

        self._barra = QProgressBar(self)
        self._barra.setFixedWidth(LARGURA_DA_BARRA)
        self._barra.setTextVisible(False)
        self._barra.setRange(0, 100)
        self._barra.setValue(0)
        # **Nasce escondida** (F9-C3). Ver `estado_do_rodape.Ocupacao.mostra_barra`: ela aparece
        # em `aplicar_ocupacao` quando há operação e some quando a última termina. Quem sustenta a
        # altura da linha é o botão de cancelar, que continua sempre visível -- então esconder a
        # barra tira 120 px de largura e nenhum pixel de altura.
        self._barra.setVisible(False)
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
        self._lbl_mensagem.definir_texto(estado.mensagem)
        self._lbl_mensagem.setMinimumWidth(LARGURA_DA_MENSAGEM if estado.mensagem else 0)
        self._repintar_mensagem()
        self._reagendar_expiracao(expira_em_ms(estado.severidade))
        item = self.mensagens.registrar(
            estado.mensagem, estado.severidade, quando=QTime.currentTime().toString("HH:mm:ss")
        )
        lista = self._lista_de_mensagens()
        if item is not None and lista is not None:
            lista.addItem(item.linha())
            while lista.count() > len(self.mensagens):
                lista.takeItem(0)
            lista.scrollToBottom()

    def abrir_mensagens(self) -> QDialog:
        """Abre (ou traz à frente) a lista das últimas mensagens. Não modal, de propósito."""
        if self._janela_de_mensagens is None or sip.isdeleted(self._janela_de_mensagens):
            janela = QDialog(self.window())
            janela.setWindowTitle(strings.MENSAGENS_ANTERIORES_TITULO)
            janela.setModal(False)
            pilha = QVBoxLayout(janela)
            lista = QListWidget(janela)
            lista.setObjectName("lista_de_mensagens")
            lista.setAccessibleName(strings.MENSAGENS_ANTERIORES_TITULO)
            lista.setFont(tema.fonte_atual(tipografia.DADO))
            for mensagem in self.mensagens.todas():
                lista.addItem(mensagem.linha())
            if not self.mensagens.todas():
                lista.addItem(strings.MENSAGENS_ANTERIORES_VAZIO)
            pilha.addWidget(lista, 1)
            janela.resize(720, 360)
            self._janela_de_mensagens = janela
        janela = self._janela_de_mensagens
        lista = self._lista_de_mensagens()
        if lista is not None and lista.count() == 1 and lista.item(0).text() == strings.MENSAGENS_ANTERIORES_VAZIO:
            if self.mensagens.todas():
                lista.clear()
                for mensagem in self.mensagens.todas():
                    lista.addItem(mensagem.linha())
        janela.show()
        janela.raise_()
        if lista is not None:
            lista.scrollToBottom()
        return janela

    def _lista_de_mensagens(self) -> QListWidget | None:
        janela = self._janela_de_mensagens
        if janela is None or sip.isdeleted(janela):
            return None
        return janela.findChild(QListWidget, "lista_de_mensagens")

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
        return self._lbl_mensagem.texto_inteiro

    def _reagendar_expiracao(self, prazo: int | None) -> None:
        self._expiracao.stop()
        if prazo is not None:
            self._expiracao.start(prazo)

    def _expirar(self) -> None:
        self._lbl_mensagem.definir_texto("")
        self._lbl_mensagem.setMinimumWidth(0)
        self._severidade = ""

    # ------------------------------------------------------------------ estado do documento

    def definir_documento(self, texto: str, todos_salvos: bool = False) -> None:
        """A zona do documento: livro, página e o que se sabe dos diagramas dela.

        Os dois parâmetros são posicionais para que o método **seja** o callback que o painel de
        PDF espera, sem um `lambda` de adaptação no meio -- é o contrato de `ui/rodape.py`.
        """
        self._lbl_documento.definir_texto(texto)
        self._lbl_documento.setStyleSheet(f"color: {tema.cor_atual(papel_do_documento(todos_salvos))};")

    def documento(self) -> str:
        """O que a zona mostra agora. Existe pelo mesmo motivo que `mensagem()`.

        Devolve a frase **inteira** e não a desenhada: o rótulo elide para caber na janela, e o
        que o chamador (e o teste) perguntam é o que o rodapé está dizendo, não quantos pixels
        ele teve. Ver `qt/rotulo.RotuloElidido.texto_inteiro`.
        """
        return self._lbl_documento.texto_inteiro

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
        self._lbl_dispositivos.definir_texto(texto)
        dica_em(self._lbl_dispositivos, dica)

    def dispositivos(self) -> str:
        """O que a zona mostra agora. Existe pelo mesmo motivo que `mensagem()`."""
        return self._lbl_dispositivos.texto_inteiro

    def barra_de_progresso(self) -> QProgressBar:
        """A barra, para quem precisa **medir** o que ela ficou tendo (F9-C7, §4.2).

        Existe pela mesma razão de `mensagem()` e `dispositivos()`, e ganhou um segundo usuário:
        `caissa.ui.audit.progresso` lia `total=` no código e **deduzia** se a barra ficava
        determinada. Uma dedução não é uma medida -- bastaria a troca de modo sumir daqui para o
        portão continuar verde com a barra andando. Com este acessor ele pergunta ao widget:
        `minimum()`/`maximum()`, e `(0, 0)` é a marquise do Qt.

        Devolve o widget e não uma cópia do intervalo de propósito: quem mede quer o objeto de
        que a captura tirou os 59 px do bloco, não um número que este módulo escolheu publicar.
        """
        return self._barra

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
            self._lbl_ocupacao.definir_texto(atual.texto)
            self._btn_cancelar.setEnabled(atual.cancelavel)
            # **Escondida sem operação** (F9-C3). Antes de `mostra_barra` esta linha não existia,
            # e a barra ficava em `0/100` para sempre no canto de todas as capturas.
            self._barra.setVisible(atual.mostra_barra)
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

    def assinar_ocupacao(
        self,
        assinar: Callable[[Callable[[], None]], None],
        operacoes: Callable[[], Sequence[BusyOperation]],
    ) -> None:
        """Pede ao registro para avisar quando algo começa ou termina (F9-C4).

        **Por que o relógio de `acompanhar` não bastava, com o número.** Ele relê a cada 400 ms
        (`INTERVALO_DE_ACOMPANHAMENTO_MS`) e a zona de mensagem é escrita por sinal, no instante.
        Nesses até 400 ms o rodapé **contradiz a si mesmo**: em
        `benchmarks/reports/ui/c4/c4_claro_1280x800_dataset.png` ele diz "Lendo o dataset…" com a
        barra escondida e o `Cancelar` desabilitado -- 1 das 36 capturas, e é a mesma frase com
        que o defeito bloqueante nº 2 do ciclo 3 reprovou o ciclo 2.

        O relógio **fica**: ele é a rede contra o `release()` esquecido da S-112. Esta assinatura
        é o que faz as quatro zonas mudarem juntas.

        **O que é assinado é uma função guardada, e não `self.ocupacao_mudou.emit`.** O registro
        vive mais que o rodapé: uma leitura que termina depois de a janela ser destruída chama
        `release()`, que avisa os observadores. Um sinal ligado guarda o ponteiro C++ do emissor, e
        emitir por ele depois do destrutor **não levanta `RuntimeError` -- derruba o processo**
        (`Windows fatal exception: access violation`, achado com a suíte do tronco inteira). O
        `try` de `busy._avisar` não pega isso, porque não é exceção de Python. Quem sabe que um
        `QObject` pode estar morto por baixo do embrulho é `qt/`, e `sip.isdeleted` é a pergunta.
        """

        referencia = weakref.ref(self)

        def avisar() -> None:
            rodape = referencia()
            if rodape is None or sip.isdeleted(rodape):
                return
            rodape.ocupacao_mudou.emit()

        assinar(avisar)
        # Fila, e não `DirectConnection`: `register` é chamado da thread de trabalho, e o slot
        # toca widget. Ver `ocupacao_mudou`.
        self.ocupacao_mudou.connect(lambda: self.aplicar_ocupacao(operacoes()))

    def acompanhar(
        self,
        operacoes: Callable[[], Sequence[BusyOperation]],
        *,
        dispositivos: Callable[[], Dispositivos] | None = None,
        avisos: Callable[[Callable[[], None]], None] | None = None,
        intervalo_ms: int = INTERVALO_DE_ACOMPANHAMENTO_MS,
    ) -> None:
        """Relê o registro a cada `intervalo_ms`, até o rodapé ser destruído.

        O rodapé é quem pergunta, e não as sete operações que avisam: um `BusyToken` que se
        esquecesse de avisar deixaria a barra girando para sempre, e a S-112 registra que
        `release()` esquecido é o erro que de fato acontece.

        **E ele também é avisado, desde o F9-C4** (`assinar_ocupacao`): o relógio sozinho deixava
        até 400 ms em que a zona de mensagem já dizia "Lendo o dataset…" e a barra ao lado ainda
        estava escondida com o `Cancelar` cinzento. Os dois caminhos convivem porque respondem a
        perguntas diferentes -- "mudou agora?" e "continua verdade?".

        `dispositivos` entra **no mesmo tique**, e não num segundo relógio, porque a pergunta é
        da mesma natureza: nenhum dos dois modelos avisa quando muda.

        `avisos` é assinado **uma vez**, na primeira chamada -- a reagenda abaixo repassa `None`,
        senão cada tique acrescentaria um observador e o registro acumularia 150 por minuto.
        """
        if avisos is not None:
            self.assinar_ocupacao(avisos, operacoes)
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
