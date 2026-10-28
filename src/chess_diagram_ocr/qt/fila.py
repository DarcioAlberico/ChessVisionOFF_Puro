"""A fila única de ações da pele "Foco", no segundo frontend (S-223/S-506).

**A decisão chega pronta, e nenhuma é reescrita aqui.** Quem está na fila é
`comandos.fila_de_destaque()` -- o catálogo filtrado por `destaque=True` e já agrupado --, e é ela
que faz "acrescentar um comando à fila" ser acrescentar uma palavra a uma linha do catálogo em vez
de vir mexer neste arquivo. O que este módulo escreve é a pílula, o separador e o registro do
rótulo que alterna.

**O separador não é decidido aqui tampouco.** `fila_de_destaque` devolve uma tupla por grupo, e
"barra só entre grupos, nunca na ponta" deixa de ser regra a cobrar e vira consequência da forma:
desenha-se uma barra **entre** tuplas consecutivas, e não há onde pôr uma sobrando.

**Por que `BarraFluida` e não uma linha só.** A fila cabe em uma linha em 1100 px, que é a largura
em que a S-151 mediu o defeito original -- mas "cabe hoje" não é uma propriedade. A barra fluida
garante a que importa: nenhum item é descartado, em nenhuma largura.

**A diferença para `qt/fita.py` é o orçamento de altura, e ela explica as duas existirem.** A fita
gasta ~99 px com ícone grande, rótulo embaixo e cabeçalho de grupo; a fila gasta a altura de um
botão comum e põe o ícone ao lado do texto. São as duas propostas que a S-221 registrou como peles
distintas, e cada uma é uma resposta diferente à mesma pergunta -- quanto do pixel vertical vale a
pena gastar com cromo.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QSizePolicy, QWidget

from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.ui import atalhos, comandos

logger = logging.getLogger(__name__)

__all__ = ["LADO_DO_ICONE", "REGIAO", "Fila", "acoes_da_fila", "montar"]

REGIAO = "Ações em destaque"
"""Como a fila se anuncia a um leitor de tela. É o nome que a S-223 dá a ela.

Texto de interface, e por isso escrito por extenso e acentuado -- ele é lido em voz alta, não
gravado em disco (a mesma separação da S-166 que `pele.ROTULOS_DE_DENSIDADE` faz)."""

LADO_DO_ICONE = 18
"""Lado do ícone da pílula, em pixel.

Pequeno de propósito, e é o mesmo número do outro frontend: a pílula tem rótulo ao lado, e o ícone
aqui é marca de reconhecimento e não a informação. O ícone grande com o rótulo embaixo é da fita
(S-228), que é outra pele e outro orçamento de altura."""


def acoes_da_fila() -> list[str]:
    """Os nomes dos comandos que a fila desenha, na ordem em que ela os desenha."""
    return [registro.acao for grupo in comandos.fila_de_destaque() for registro in grupo]


class Fila(BarraFluida):
    """A fila montada: pílulas agrupadas, com uma barra vertical entre grupos."""

    def __init__(
        self,
        parent: QWidget | None = None,
        amarrados: Mapping[str, Callable[[], object]] | None = None,
        *,
        lado_do_icone: int = LADO_DO_ICONE,
    ) -> None:
        super().__init__(parent)
        # **A fila é uma região, e ela tem de se anunciar como uma** (F9-C9) -- a mesma linha que
        # `qt/painel_do_pdf._bloco` tem desde o ciclo 2. Sem ela as pílulas chegavam ao leitor de
        # tela como comandos soltos, indistinguíveis do botão do painel que faz a mesma coisa:
        # medido, `"Ler esta página"` era anunciado por **dois** controles em cada uma das seis
        # abas, e `"Próximo diagrama"` por dois na Galeria, sem nada que dissesse qual é qual.
        self.setAccessibleName(REGIAO)
        self._amarrados = dict(amarrados or {})
        self._lado = int(lado_do_icone)
        self.botoes: dict[str, QPushButton] = {}
        """As pílulas por ação. É por aqui que o teste pergunta o que a fila desenhou."""
        self._construir()

    def _construir(self) -> None:
        for numero, grupo in enumerate(comandos.fila_de_destaque()):
            if numero:
                self.adicionar(self._separador())
            for registro in grupo:
                self.botoes[registro.acao] = self.adicionar(self._pilula(registro))  # type: ignore[assignment]

    def _pilula(self, registro: comandos.Comando) -> QPushButton:
        """Um comando em destaque: ícone à esquerda, rótulo à direita, tecla na dica.

        **O nome acessível é o rótulo por extenso, e não o texto do botão** (F9-C9) -- a mesma
        linha que `qt/painel_do_pdf._botao` tem desde o ciclo 2. Nenhum comando em destaque tem
        rótulo de glifo hoje, então o número desta pele não muda; o que muda é que ele deixa de
        depender disso. A pílula que amanhã mostrasse `▶` já chegaria ao leitor de tela como
        "Próximo lance", em vez de virar o defeito nº 1 do ciclo 1 numa terceira montagem.
        """
        botao = QPushButton(registro.no_botao, self)
        botao.setAccessibleName(comandos.nome_acessivel(registro.acao))
        botao.clicked.connect(lambda _marcado=False, f=self._amarrados[registro.acao]: f())
        tema.aplicar_papel(botao, comandos.papel(registro.acao))
        if registro.icone:
            # A cor sai do token na hora de desenhar, e é o que faz o mesmo traço servir ao cromo
            # claro e ao escuro (S-220). `vestir` devolve `False` quando não há desenho, e aí a
            # pílula fica só com texto -- nunca sem nada.
            qt_icones.vestir(
                botao,
                registro.icone,
                comandos.papel(registro.acao),
                lado=self._lado,
                manter_texto=not registro.so_glifo,
            )
        tecla = atalhos.acelerador(registro.acao)
        dica_em(botao, f"{registro.rotulo}\nTecla: {tecla}" if tecla else registro.rotulo)
        if registro.rotulo_alternado:
            # A fila também mostra o estado de um comando que é modo (S-396): "Selecionar área"
            # vira "Cancelar seleção", e ligar deixa de ter o mesmo aspecto de desligar.
            comandos.ao_alternar(registro.acao, botao.setText)
        return botao

    def _separador(self) -> QWidget:
        """A barra vertical entre grupos -- o que a Imagem 1 desenha entre a 2ª e a 3ª pílula.

        **Um `QWidget` de 1 px pintado pela folha, e não um `QFrame.VLine`** (S-522). O `VLine` era
        a forma óbvia, e o retrato a desmentiu: ele desenha com a cor de **texto** da paleta, e não
        com a da folha -- medido no `windows11`, 2 px em `#848688` na pele "Foco", mais claro que a
        borda das pílulas ao lado. A folha pinta `#separador-da-fila` com a mesma moldura que dá
        aos controles, e a troca de pele o repinta sozinha, como a qualquer regra de classe.
        """
        risco = QWidget(self)
        risco.setObjectName(tema.ID_DO_SEPARADOR)
        # Sem o atributo um `QWidget` puro ignora o `background-color` da folha: só quem o tem
        # pinta o próprio fundo.
        risco.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        risco.setFixedWidth(1)
        risco.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        return risco


def montar(
    pai: QWidget | None,
    amarrados: Mapping[str, Callable[[], object]],
    *,
    lado_do_icone: int = LADO_DO_ICONE,
) -> Fila:
    """A fila, montada. Levanta `KeyError` nomeando comando não amarrado.

    Levanta pela mesma razão que `qt/menu.montar` e `qt/fita.montar`: uma pílula grande, com
    ícone, que não faz nada é pior que a ausência dela -- a pessoa conclui que a função existe e
    está quebrada.
    """
    if faltando := sorted(acao for acao in acoes_da_fila() if acao not in amarrados):
        raise KeyError(f"comando em destaque sem função: {', '.join(faltando)}")
    return Fila(pai, amarrados, lado_do_icone=lado_do_icone)
