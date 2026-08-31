"""A fita de grupos nomeados no segundo frontend, gerada do mesmo catálogo (S-227/S-228/S-503).

**Três decisões chegam prontas, e nenhuma é reescrita aqui.**

1. *Quem está na fita* -- `medidas_da_fita.grupos()`, que é o catálogo filtrado por "tem ícone".
2. *Quanto ela pode custar* -- `ORCAMENTO`, e `altura_da_fita` para prever o custo.
3. *Como o rótulo quebra* -- `quebrar_rotulo`, e as duas linhas que a S-228 mediu.

O que este módulo escreve é o `QToolButton`, o cabeçalho e a troca de modo. É a mesma divisão de
`qt/barra.py`: a decisão é pura, o widget executa.

**A quebra por grupo é a `BarraFluida` do Qt, e não uma segunda implementação.** O grupo é a
unidade -- um grupo partido ao meio não é um grupo --, e a `LeiauteFluido` recebe cada grupo como
um item. É a mesma propriedade que o outro frontend herda pelo mesmo caminho, e a razão de
"nenhum comando é descartado" valer nos dois sem ser afirmado duas vezes.

**A altura prevista e a altura real são duas perguntas, e o Qt obriga a separá-las.** Do lado do
Tk as três medidas do botão (`MOLDURA_DO_BOTAO` e as duas irmãs) saíram de medir um `ttk.Button`,
e a conta fecha com 2 px de tolerância contra o widget montado. Um `QToolButton` tem o cromo dele,
que não é o mesmo -- então prever pela conta do `ttk` e cobrar isso do widget do Qt seria cobrar
do desenho errado. O que este módulo faz é o que importa: `altura_prevista()` responde pela
**mesma** conta dos dois lados (é ela que decide o modo, e ela é a decisão), e o teste cobra do
widget montado o **orçamento** -- que é o número que a S-228 declarou e o único que a pessoa
sente. Ver `altura_atual` e `altura_medida`.

**O limiar de troca é medido, e não escolhido**, como do outro lado: é a largura que a fita plena
pede para caber em uma linha. Aqui ele é mais barato de obter -- `sizeHint()` já responde antes de
a janela aparecer, enquanto o `winfo_reqwidth` do Tk devolve 1 até as tarefas ociosas rodarem. É a
razão de `_medir_plena` de lá desistir em silêncio nas primeiras chamadas e de este não precisar.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import ESPACO_ENTRE_ITENS, BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.ui import atalhos, comandos, pele, strings, tipografia, tokens
from chess_diagram_ocr.ui.medidas_da_fita import (
    COMPACTO,
    HISTERESE,
    LADO_DO_ICONE,
    LINHAS_DO_ROTULO,
    MODOS,
    ORCAMENTO,
    PLENO,
    GrupoDeFita,
    acoes_da_fita,
    altura_da_fita,
    espaco_ate_o_cabecalho,
    espaco_entre_botoes,
    grupos,
    quebrar_rotulo,
)

__all__ = [
    "COMPACTO",
    "MODOS",
    "ORCAMENTO",
    "PLENO",
    "Fita",
    "altura_atual",
    "linhas_de_fonte",
    "montar",
]


def linhas_de_fonte() -> tuple[int, int]:
    """`(linespace do corpo, linespace do apoio)` como o **Qt** os reporta, em pixel.

    O par de `fita.linhas_de_fonte`, e a única coisa que os dois frontends medem por caminhos
    diferentes: lá é `tkfont.Font(...).metrics("linespace")`, aqui é `QFontMetrics.lineSpacing()`.
    A reserva quando não há aplicação é a mesma conta de `tipografia` dos dois lados, pela mesma
    razão de `tema.altura_de_linha_atual`: o orçamento continua afirmável sem janela.
    """
    tamanho, _proporcional, _mono = tema.fonte_base()
    escala = tipografia.escala(tamanho)
    reserva = (round(escala[tipografia.CORPO] * 5 / 3), round(escala[tipografia.AUXILIAR] * 5 / 3))
    try:
        from PyQt6.QtGui import QFontMetrics

        corpo = int(QFontMetrics(tema.fonte_atual(tipografia.CORPO)).lineSpacing())
        apoio = int(QFontMetrics(tema.fonte_atual(tipografia.AUXILIAR)).lineSpacing())
    except Exception:  # noqa: BLE001 - sem aplicação ou fonte exótica: a reserva serve
        return reserva
    return (corpo or reserva[0], apoio or reserva[1])


def altura_atual(modo: str, *, densidade: str = pele.CONFORTAVEL) -> int:
    """`altura_da_fita` resolvida contra a fonte deste sistema. É o que a fita prevê para si.

    **A conta é a de `ui/medidas_da_fita.py`, e é de propósito que ela não tenha uma versão de
    Qt.** Ela é o que decide o modo, e um segundo modelo de altura faria as duas janelas trocarem
    de modo em larguras diferentes -- o que é a mesma fita se comportando de dois jeitos.
    """
    corpo, apoio = linhas_de_fonte()
    base, _proporcional, _mono = tema.fonte_base()
    return altura_da_fita(
        modo, linha_de_texto=corpo, linha_de_apoio=apoio, densidade=densidade, base=base
    )


class Fita(BarraFluida):
    """A fita montada, e o modo em que ela está agora.

    **Por que uma classe, e não uma função que devolve widgets** -- a mesma razão do outro
    frontend: a troca de modo não é uma reconfiguração. O ícone muda de tamanho (o cache de
    `qt/icones.py` é por tamanho), o rótulo muda de lado e o cabeçalho deixa de ser um widget para
    virar linha de dica. Alguém precisa saber remontar, e do que remontar a partir de quê.
    """

    def __init__(
        self,
        pai: QWidget | None,
        amarrados: Mapping[str, Callable[[], object]],
        *,
        modo: str | None = None,
        densidade: str = pele.CONFORTAVEL,
    ) -> None:
        super().__init__(pai)
        if modo is not None and modo not in LADO_DO_ICONE:
            raise KeyError(f"modo de fita desconhecido: {modo!r}. Os válidos estão em MODOS.")
        if densidade not in pele.DENSIDADES:
            raise KeyError(f"densidade desconhecida: {densidade!r}. As válidas estão em pele.DENSIDADES.")
        self._amarrados = dict(amarrados)
        self._densidade = densidade
        self._base = tema.fonte_base()[0]
        self._fixo = modo is not None or densidade == pele.COMPACTA
        """Modo pedido de fora é modo cravado, e densidade compacta também crava (S-232) -- as
        duas razões estão em `ui/fita.py`, e valem letra por letra deste lado."""

        self._modo = modo or (COMPACTO if densidade == pele.COMPACTA else PLENO)
        self._botoes: dict[str, QToolButton] = {}
        self._largura_plena = 0
        self._construir()

        # **Um seguidor por comando e por fita, registrado aqui e não em `_botao`.** "Selecionar
        # área" é um modo, e a fita tem de dizer em qual estado ele está (S-396) -- mas registrar
        # no botão faria cada troca de modo somar um seguidor morto, que é exatamente o defeito
        # que `test_a_fita_remontada_nao_carrega_a_de_antes` mede do outro lado. Registrado aqui,
        # o seguidor sobrevive à remontagem porque ele não guarda botão nenhum: ele procura, em
        # `self._botoes`, o botão que **agora** desenha aquele comando.
        for registro in (item for grupo in grupos() for item in grupo.itens if item.rotulo_alternado):
            comandos.ao_alternar(registro.acao, self._alternado(registro.acao))

    # ------------------------------------------------------------------------------ leitura

    @property
    def modo(self) -> str:
        """`PLENO` ou `COMPACTO`, como a fita está desenhada agora."""
        return self._modo

    @property
    def densidade(self) -> str:
        return self._densidade

    @property
    def largura_de_troca(self) -> int:
        """A largura abaixo da qual a fita fica compacta -- medida, e não escolhida.

        É o que a fita **plena** pede para caber em uma linha: a soma dos grupos mais o espaço
        entre eles. Ao contrário do Tk, o número existe desde a construção: `sizeHint()` do Qt
        responde antes de o widget ser mostrado, enquanto `winfo_reqwidth` devolve 1 até as
        tarefas ociosas rodarem -- que é a razão inteira de `_medir_plena` existir lá.
        """
        self._medir_plena()
        return self._largura_plena

    @property
    def acoes_desenhadas(self) -> list[str]:
        """Os comandos que estão na tela agora, na ordem em que a fita os desenha.

        Existe para o critério que a troca de modo poderia quebrar em silêncio: **nenhuma largura
        descarta comando.**
        """
        return [acao for acao in acoes_da_fita() if acao in self._botoes]

    def botao(self, acao: str) -> QToolButton:
        """O botão daquele comando. Levanta `KeyError` para comando que a fita não desenha."""
        if acao not in self._botoes:
            raise KeyError(f"a fita não desenha o comando {acao!r}.")
        return self._botoes[acao]

    def altura_prevista(self) -> int:
        """O que `altura_da_fita` promete para o modo e a densidade atuais."""
        return altura_atual(self._modo, densidade=self._densidade)

    def altura_medida(self) -> int:
        """A altura que a fita montada realmente pede, em pixel -- do widget, e não da conta.

        **Existe porque o cromo do `QToolButton` não é o do `ttk.Button`**, e as três medidas de
        `ui/medidas_da_fita.py` são daquele. Cobrar do widget do Qt uma previsão feita com as
        medidas do outro toolkit seria cobrar do desenho errado; o que os dois frontends têm em
        comum e o que a S-228 declarou é o **orçamento**, e é contra ele que esta responde.
        """
        return self.sizeHint().height()

    # ------------------------------------------------------------------------------ montagem

    def _construir(self) -> None:
        self._botoes.clear()
        for grupo in grupos():
            self.adicionar(self._grupo(grupo))
        self._medir_plena()

    def _medir_plena(self) -> None:
        """Guarda a largura que a fita plena pede em uma linha. Só no modo pleno.

        No compacto os botões são outros, e a largura deles não responde a pergunta que o limiar
        faz -- é a mesma guarda do outro lado, e a mesma razão.
        """
        if self._modo != PLENO or self._largura_plena:
            return
        larguras = [item.sizeHint().width() for item in self.findChildren(QWidget, "grupo-da-fita")]
        if not larguras or min(larguras) <= 1:
            return
        self._largura_plena = sum(larguras) + ESPACO_ENTRE_ITENS * (len(larguras) - 1)

    def _reconstruir(self) -> None:
        self.esvaziar()
        self._botoes.clear()
        for grupo in grupos():
            self.adicionar(self._grupo(grupo))

    def resizeEvent(self, a0: QResizeEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """Decide o modo pela largura que o evento trouxe, como o `<Configure>` do outro lado.

        **A largura vem do evento e não de `self.width()`**, pela mesma razão da `BarraFluida`:
        durante um redimensionamento o widget ainda reporta a largura anterior, e decidir o modo
        contra ela deixaria a fita um evento atrás da janela.
        """
        super().resizeEvent(a0)
        if self._fixo or a0 is None:
            return
        self._medir_plena()
        largura = int(a0.size().width())
        if largura <= 1 or not self._largura_plena:
            return
        if self._modo == PLENO and largura < self._largura_plena:
            self._modo = COMPACTO
        elif self._modo == COMPACTO and largura >= self._largura_plena + HISTERESE:
            self._modo = PLENO
        else:
            return
        self._reconstruir()

    def _grupo(self, grupo: GrupoDeFita) -> QWidget:
        """Um grupo inteiro num `QWidget` -- e é ele que a barra arranja, nunca os botões dele."""
        moldura = QWidget(self)
        moldura.setObjectName("grupo-da-fita")
        fora = QVBoxLayout(moldura)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(0)

        # **`QHBoxLayout` e não a `BarraFluida`**, e é a única linha deste módulo em que não
        # reusar é o certo: a barra fluida existe para quebrar, e o grupo é a unidade de quebra --
        # um grupo partido ao meio não é um grupo (S-227). Medido: com a fluida aqui dentro, a
        # fita a 400 px punha dois dos quatro grupos em duas linhas cada, e o que o olho lia era
        # sete grupos. O `QHBoxLayout` é o `pack(side=LEFT)` do outro lado -- ele não quebra, e um
        # grupo que não cabe é cortado na borda, que é o único caso sem saída que `arranjo` já
        # documenta.
        linha = QWidget(moldura)
        fila = QHBoxLayout(linha)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(espaco_entre_botoes(self._densidade, base=self._base))
        for registro in grupo.itens:
            botao = self._botao(linha, registro, grupo)
            fila.addWidget(botao)
            self._botoes[registro.acao] = botao
        fora.addWidget(linha, 0, Qt.AlignmentFlag.AlignHCenter)

        if self._modo == COMPACTO:
            # **O cabeçalho vira dica** (S-228): ele custa uma linha de texto por fita, e no modo
            # compacto essa linha é a diferença entre caber e competir com a página. O nome do
            # grupo não se perde -- ele passa a abrir a dica de cada botão dele.
            return moldura

        cabecalho = QLabel(grupo.rotulo, moldura)
        cabecalho.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        cabecalho.setFont(tema.fonte_atual(tipografia.AUXILIAR))
        tema.pintar(cabecalho, "color", tokens.TEXTO_SECUNDARIO)
        # O cabeçalho **embaixo**, como a Imagem 2 desenha: o nome do grupo é a legenda de uma
        # fila de botões, e uma legenda acima competiria com a barra de menus por leitura.
        fora.addSpacing(espaco_ate_o_cabecalho(self._densidade, base=self._base))
        fora.addWidget(cabecalho)
        return moldura

    def _botao(self, pai: QWidget, registro: comandos.Comando, grupo: GrupoDeFita) -> QToolButton:
        """No pleno, ícone **acima** do rótulo, que é a forma da Imagem 2; no compacto, ao lado.

        **`QToolButton` e não `QPushButton`**, e é o `compound=TOP` do outro lado: só o primeiro
        sabe pôr o ícone acima do texto (`ToolButtonTextUnderIcon`). Um `QPushButton` desenha
        sempre o ícone à esquerda, e a fita plena seria a fita compacta com o cabeçalho de volta.
        """
        acima = self._modo == PLENO
        botao = QToolButton(pai)
        botao.setText(quebrar_rotulo(registro.no_botao))
        botao.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextUnderIcon
            if acima
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        botao.clicked.connect(self._amarrados[registro.acao])
        tema.aplicar_papel(botao, comandos.papel(registro.acao))

        # A cor do ícone é perguntada ao token na hora de desenhar, e é o que faz o mesmo traço
        # servir ao cromo claro e ao escuro (S-220). Ícone que não desenhou vira botão só com
        # texto: `qt_icones.icone` devolve `None` em vez de levantar.
        lado = LADO_DO_ICONE[self._modo]
        desenho = qt_icones.icone(registro.icone, lado, tema.cor_atual(tokens.TEXTO_PADRAO))
        if desenho is not None:
            botao.setIcon(desenho)
            botao.setIconSize(qt_icones.tamanho(lado))
        dica_em(botao, self._dica(registro, grupo))
        return botao

    def _alternado(self, acao: str) -> Callable[[str], object]:
        """O seguidor de um comando que alterna: escreve no botão que **agora** o desenha.

        **Ele levanta quando a fita morre**, e é assim que sai da lista: `comandos.alternou` poda
        quem levanta, que é a mesma disciplina de `theme.repintar` e o que faz um botão de uma
        janela fechada não derrubar os das abertas. Do lado do Tk quem levanta é o `TclError` de
        um widget destruído; aqui é o `RuntimeError` do objeto C++ apagado, e o efeito é o mesmo.

        A diferença que morde é **quando**: `destroy()` do Tk é síncrono e `deleteLater` do Qt
        não, e `processEvents` não esvazia a fila de apagados. Ver `descartar` em
        `tests/qt_app.py`.
        """

        def escrever(texto: str) -> None:
            self._botoes[acao].setText(quebrar_rotulo(texto))

        return escrever

    def _dica(self, registro: comandos.Comando, grupo: GrupoDeFita) -> str:
        """O rótulo por extenso, a tecla, e -- no compacto -- o grupo que perdeu o cabeçalho."""
        titulo = (
            registro.rotulo
            if self._modo == PLENO
            else f"{grupo.rotulo} {strings.SETA} {registro.rotulo}"
        )
        tecla = atalhos.acelerador(registro.acao)
        return f"{titulo}\nTecla: {tecla}" if tecla else titulo


def montar(
    pai: QWidget | None,
    amarrados: Mapping[str, Callable[[], object]],
    *,
    modo: str | None = None,
    densidade: str = pele.CONFORTAVEL,
) -> Fita:
    """A fita, montada numa `BarraFluida` cujos **itens são os grupos**.

    `modo=None` deixa a largura decidir, que é o caso da janela; um modo explícito o crava, que é
    o caso de quem mede um dos dois orçamentos.

    Levanta `KeyError` nomeando comando não amarrado, como `qt/menu.montar`: um botão grande, com
    ícone e rótulo, que não faz nada é pior que a ausência dele.
    """
    if faltando := sorted(acao for acao in acoes_da_fita() if acao not in amarrados):
        raise KeyError(f"comando da fita sem função: {', '.join(faltando)}")
    return Fita(pai, amarrados, modo=modo, densidade=densidade)


_ = LINHAS_DO_ROTULO  # noqa: B018 - reexportado por `quebrar_rotulo`; ver `ui/medidas_da_fita.py`
