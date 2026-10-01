"""O estado vazio: título, frase e **o botão que resolve**, dentro do vazio (F9-C2, §7 item 14).

**O que o crítico do ciclo 1 mediu.** Três regiões grandes de painel com quase nenhuma tinta:
Galeria 514,7 kpx a **0,24 %**, Texto a **0,57 %**, Revisão 409,3 kpx a **0,00 %** -- e, na
Galeria, *"duas frases dizendo a mesma coisa a 320 px uma da outra"*, com o botão que resolve a
645 px de distância do vazio que ele preenche.

Um estado vazio não é uma frase: é a resposta a "o que eu faço agora", e a resposta tem de estar
onde a pergunta é feita. Os três elementos são obrigatórios e é por isso que o construtor os
exige: o **título** diz o que falta, a **frase** diz por quê, e o **botão** faz.

**A frase quebra linha, e isso é o item 3 do §7.** `QPlainTextEdit.placeholderText` não elide nem
quebra: o crítico mediu a dica da aba Texto **cortada em 77 px** em toda janela de 1280 px ou
menos, incluindo o tamanho mínimo. Um `QLabel` com `setWordWrap(True)` cabe em qualquer largura, e
é o que este widget usa.

**Os degraus são os da escala** (§7 item 9): o título é `TITULO` e a frase é `AUXILIAR`, ambos por
propriedade dinâmica, que é o que faz `qt/escala.aplicar_escala` alcançá-los sem este módulo saber
de fonte nenhuma.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import espaco, estilos, folha_de_estilo, tipografia

__all__ = ["EstadoVazio"]


class EstadoVazio(QWidget):
    """Título, frase e botão, centrados na região que está vazia. Ver o cabeçalho."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        titulo: str,
        frase: str,
        rotulo_do_botao: str = "",
        nome_acessivel: str = "",
        acao: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("estado_vazio", "true")
        # **Ele acompanha o que cobre, e sem isto ele desalinha na primeira mudança de janela.**
        # O `EstadoVazio` é sobreposto (não entra no leiaute do pai, para não empurrar nada), e
        # widget sobreposto não recebe geometria de ninguém: a que ele tinha quando apareceu fica.
        # Medido: a frase da aba Dataset saía **cortada à direita** a 1280 px porque a geometria
        # era a de 1920. O filtro é o mesmo mecanismo de `qt/painel_de_texto`, aqui uma vez só.
        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())
        pilha = QVBoxLayout(self)
        # `linha()` e não `margem_da_aba()`: o estado vazio já está **dentro** de uma região que
        # tem a margem da aba, e somar as duas margens é o que punha o piso da pele "Foco" um
        # pixel acima dos 768 do item 4 do §7. Medido.
        pilha.setContentsMargins(*(espaco.linha(),) * 4)
        pilha.setSpacing(espaco.linha())
        # A frase quebra linha e um `QLabel` que quebra pede altura por todas as linhas dele. O
        # piso zero é o que deixa a região encolher junto com a janela; a altura desejada continua
        # sendo a do texto, e é ela que o leiaute usa quando há espaço.
        self.setMinimumSize(0, 0)
        pilha.addStretch(1)

        self.titulo = QLabel(titulo, self)
        self.titulo.setProperty(tipografia.PROPRIEDADE_DE_PAPEL_DE_FONTE, tipografia.TITULO)
        self.titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pilha.addWidget(self.titulo)

        self.frase = QLabel(frase, self)
        self.frase.setProperty(folha_de_estilo.PROPRIEDADE_DE_APOIO, "true")
        self.frase.setWordWrap(True)
        self.frase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pilha.addWidget(self.frase)

        self.botao: QPushButton | None = None
        if rotulo_do_botao and acao is not None:
            self.botao = QPushButton(rotulo_do_botao, self)
            self.botao.clicked.connect(acao)  # type: ignore[arg-type]
            # **Neutro, e não a ênfase da tela** (§7 item 10): a tela inteira tem direito a uma
            # ênfase, e ela é `ler_melhor`. O que faz este botão ser achado é ele estar **dentro**
            # do vazio, e não a cor dele.
            tema.aplicar_papel(self.botao, estilos.NEUTRO)
            # **O nome acessível difere do rótulo, e o portão do teclado obriga.** O botão do
            # estado vazio é *o mesmo comando* de um botão da barra da aba -- é essa a proposta do
            # §7, trazer a ação para dentro do vazio --, e dois controles com o mesmo nome na mesma
            # aba é o que `teclado.nome_vazio_de_sentido` reprova por "repetido na aba": quem ouve
            # "Varrer o livro, botão" duas vezes não sabe se são dois ou se andou em círculo. O
            # rótulo desenhado continua o mesmo; o que muda é o que se **ouve**.
            self.botao.setAccessibleName(nome_acessivel or rotulo_do_botao)
            pilha.addWidget(self.botao, 0, Qt.AlignmentFlag.AlignHCenter)
        pilha.addStretch(1)

    def eventFilter(self, a0: object, a1: object) -> bool:  # noqa: N802 - assinatura do Qt
        """Cobre o pai de novo quando ele muda de tamanho. Ver o construtor."""
        pai = self.parentWidget()
        if a0 is pai and pai is not None and a1 is not None and a1.type() == QEvent.Type.Resize:
            self.setGeometry(pai.rect())
        return super().eventFilter(a0, a1)  # type: ignore[arg-type]
