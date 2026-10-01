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
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import ESPACO_ENTRE_ITENS, BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.ui import (
    atalhos,
    comandos,
    pele,
    tipografia,
    tokens,
)
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
        for indice, grupo in enumerate(grupos()):
            self.adicionar(self._grupo(grupo, primeiro=indice == 0))
        self._igualar_a_altura()
        self._medir_plena()

    def _igualar_a_altura(self) -> None:
        """Um topo e uma altura por fila da fita. **É o conserto de uma regressão medida.**

        O ciclo 11 mediu o que o conserto do bloqueante do ciclo 10 deixou: nesta fita a 1366 px
        havia **4 topos distintos (0, 6, 49, 55) e 2 alturas (31, 43)**, e os seis botões
        vestidos só de ícone ficavam 12 px mais curtos e 6 px encravados entre vizinhos de 43 px
        -- a faixa cinza que aparece acima e abaixo das duas lupas no recorte a 3×. A causa é do
        Qt e é banal: a altura de um `QToolButton` é a do conteúdo dele, e o conteúdo varia --
        "Abrir PDF" quebra em duas linhas, "Desfazer" cabe numa, e um botão sem rótulo é só o
        ícone. Um `QHBoxLayout` centra os mais baixos, e centrar é o que produz o encravamento.

        **A altura sai do widget e não da conta de `ui/medidas_da_fita.py`**, e essa distinção o
        módulo já defende no docstring de `altura_medida`: as três medidas de lá saíram de um
        `ttk.Button`, e cravar o número delas num `QToolButton` seria cobrar do desenho errado.
        O que se afirma aqui é a **relação** -- todos iguais ao mais alto --, e ela é do
        toolkit. O mais alto é o de duas linhas de rótulo, que é o teto que `LINHAS_DO_ROTULO`
        já fixa: nenhum botão pode crescer além dele.

        Consequência de leiaute, e é a razão de o conserto ser este e não um `AlignTop`: com
        todos os grupos da mesma altura, as molduras de grupo passam a ter a mesma altura, e as
        filas que a `BarraFluida` quebra passam a ter um topo só.
        """
        if not self._botoes:
            return
        alto = max(botao.sizeHint().height() for botao in self._botoes.values())
        for botao in self._botoes.values():
            botao.setFixedHeight(alto)

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
        for indice, grupo in enumerate(grupos()):
            self.adicionar(self._grupo(grupo, primeiro=indice == 0))
        self._igualar_a_altura()

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

    def _grupo(self, grupo: GrupoDeFita, *, primeiro: bool = False) -> QWidget:
        """Um grupo inteiro num `QWidget` -- e é ele que a barra arranja, nunca os botões dele."""
        moldura = QWidget(self)
        moldura.setObjectName("grupo-da-fita")
        # **O nome do grupo é o que um leitor de tela anuncia ao entrar nele** -- a mesma linha
        # que `qt/painel_do_pdf._bloco` tem desde o ciclo 2, e que faltava aqui (F9-C9). Sem ela a
        # pessoa ouve vinte e quatro botões seguidos sem saber onde um grupo acaba, e -- medido no
        # portão de teclado -- **onze nomes desta fita batiam com os da barra do visor** em cada
        # aba, porque os dois lados anunciavam o comando e só um lado anunciava onde ele estava.
        # No modo compacto o cabeçalho visível vira dica (S-228); este nome não depende disso, e é
        # por isso que ele fica aqui e não junto do `QLabel`.
        moldura.setAccessibleName(grupo.rotulo)
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
        if self._modo == COMPACTO and not primeiro:
            # **A fronteira do grupo desenhada, quando o cabeçalho não pode ser** (F9-C12). No
            # compacto o nome do grupo vira dica (S-228), porque a linha de texto dele é a
            # diferença entre a fita caber e competir com a página -- e essa decisão está medida
            # e tem teste. O que ela não decidiu foi deixar o olho sem **nenhuma** separação: o
            # crítico do ciclo 11 leu vinte e quatro botões em duas filas seguidas e disse, com
            # razão, que aquilo é uma barra de duas alturas e não uma fita. Um filete custa 1 px
            # de largura e zero de altura, que é o recurso que a S-228 está protegendo.
            filete = QFrame(linha)
            filete.setObjectName("filete-entre-grupos")
            filete.setFrameShape(QFrame.Shape.VLine)
            tema.pintar(filete, "color", tokens.SEPARADOR)
            fila.addWidget(filete)
        for registro in grupo.itens:
            botao = self._botao(linha, registro, grupo)
            fila.addWidget(botao)
            self._botoes[registro.acao] = botao
        fora.addWidget(linha, 0, Qt.AlignmentFlag.AlignHCenter)

        # **O cabeçalho é desenhado nos dois modos** (OCR_UI_ROADMAP passo 12; R3.4: dica não é
        # rótulo). A S-228 o mandava para a dica no compacto para caber em 64 px; medido, a linha
        # auxiliar custa 17–20 px e a fita compacta com cabeçalho fecha em 61–63 px na fonte do
        # produto -- cabe. O orçamento compacto passou a contá-lo (`medidas_da_fita.altura_da_fita`).
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

        **O nome acessível é o rótulo por extenso, e não o texto do botão** (F9-C9). É a mesma
        linha que `qt/painel_do_pdf._botao` tem desde o ciclo 2, e ela faltava aqui: o crítico do
        ciclo 9 mediu **36 controles** desta fita chegando ao leitor de tela como `-`, `+`, `◀`,
        `▶`, `|◀`, `▶|` -- seis por aba, nas seis abas. É o defeito nº 1 do ciclo 1, reposto por
        um cromo que nasceu depois do conserto e que nenhum portão olhava.

        **E o glifo sai quando há desenho**, que é a segunda metade do mesmo defeito: até o ciclo
        9 os mesmos seis botões desenhavam o ícone **e** o glifo lado a lado -- o `◀` de 5×3 px
        que o ciclo 8 apagou em todo lugar menos aqui. A regra já existia e chama-se
        `qt/icones.vestir` (*"põe o desenho e apaga o glifo"*); o que faltava era esta fita passar
        por ela. Quem decide se o rótulo é glifo é o catálogo (`comandos.Comando.so_glifo`), e não
        uma lista escrita aqui.
        """
        acima = self._modo == PLENO
        botao = QToolButton(pai)
        # `na_fita`, e não `no_botao`: o glifo (`-`, `◀`) nunca chega à fita -- a palavra chega
        # (passo 12: 24 de 24 botões com rótulo desenhado; antes eram 18).
        botao.setText(quebrar_rotulo(registro.na_fita))
        botao.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextUnderIcon
            if acima
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        botao.setAccessibleName(comandos.nome_acessivel(registro.acao))
        botao.clicked.connect(self._amarrados[registro.acao])
        tema.aplicar_papel(botao, comandos.papel(registro.acao))

        # A cor do ícone é perguntada ao token na hora de desenhar, e é o que faz o mesmo traço
        # servir ao cromo claro e ao escuro (S-220). `vestir` devolve `False` quando não há
        # desenho -- nome desconhecido, Pillow ausente --, e aí o glifo fica onde está, que é a
        # degradação da regra 4 da SPEC_APARENCIA: nenhum ícone pode impedir a janela de abrir.
        lado = LADO_DO_ICONE[self._modo]
        # `manter_texto` sempre: o texto do botão da fita é uma palavra por construção
        # (`Comando.na_fita`), e `vestir` só apagaria um glifo que não está lá.
        qt_icones.vestir(
            botao,
            registro.icone,
            comandos.papel(registro.acao),
            lado=lado,
            manter_texto=True,
        )
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

        **O botão vestido de ícone não recebe texto** (F9-C9), e é a porta de trás do defeito
        deste ciclo: `setText` num botão cujo glifo o desenho substituiu reporia o glifo -- só
        que agora escrito pelo estado, e não pela montagem, onde nenhum censo o procura. Hoje
        nenhum dos seis comandos de glifo alterna, e é por isso que a guarda é barata; ela existe
        para o dia em que um deles passar a alternar.
        """

        def escrever(texto: str) -> None:
            # Um comando de glifo que alternasse escreveria o glifo pelo estado; a fita desenha
            # palavra, então o texto alternado só entra quando é palavra (passo 12).
            if comandos.comando(acao).so_glifo and not any(ch.isalpha() for ch in texto):
                return
            self._botoes[acao].setText(quebrar_rotulo(texto))

        return escrever

    def _dica(self, registro: comandos.Comando, grupo: GrupoDeFita) -> str:
        """O rótulo por extenso e a tecla. O grupo está no cabeçalho, nos dois modos (passo 12)."""
        del grupo  # desenhado, e não dito
        titulo = registro.rotulo
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
