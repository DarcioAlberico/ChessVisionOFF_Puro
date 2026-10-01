"""O tema da janela em Qt: uma folha de estilo tirada dos mesmos papéis do Tk (S-501).

**O que muda em relação a `ui/theme.py`, e é uma coisa só.** Lá o tema é de terceiro: o
`ttkbootstrap` pinta o cromo, e `ui/tokens.py` existe em boa parte para *perguntar* a ele o que
ele deu -- daí o `Estilo` Protocol, o `_DO_TEMA` e o `_resposta_do_tema`, que separa resposta de
herança. Aqui não há terceiro. O Qt não traz tema de cor nenhum: ou a janela declara a folha, ou
ela sai com o cinza de fábrica do sistema. Então **este módulo é o tema**, e a paleta que ele
pinta é a mesma que a S-145 mediu.

Isso simplifica uma coisa e nenhuma outra: `tokens.cor(papel, None, cromo_escuro=...)` deixa de
ser o caminho de degradação e passa a ser a resposta inteira. **Não é a reserva por falta de
tema; é a paleta, porque o tema somos nós.** Os quatro caminhos de `tokens.cor` continuam
valendo -- o cromo da pele (`NO_CROMO_ESCURO`) e o pino das superfícies de documento são
justamente o que faz a pele "Foco" escurecer o cromo sem escurecer a folha do livro, e isso vale
igual nos dois frontends.

**O eixo de tema colapsa, e a ausência é decisão.** No Tk existem dois eixos: a pele (com o seu
`cromo_escuro`) e o tema `ttkbootstrap` (30 nomes, trocável por `CVOFF_TTK_THEME`). O segundo
não tem contraparte em Qt sem alguém escrever trinta folhas de estilo, e escrevê-las seria
inventar aparência que ninguém pediu. Fica o eixo que carrega significado -- a pele --, e
`cromo_escuro` continua sendo dela.

**O contrato de degradação é o mesmo desde a S-53: aparência não derruba ferramenta.** Nenhuma
função daqui levanta por causa de folha de estilo, fonte exótica ou `QApplication` ausente.

---

**Por que a folha é construída por uma função pura.** `folha_de_estilo()` não toca `QApplication`
nem widget: ela recebe a base de fonte e a densidade e devolve texto. É o que permite afirmar a
paleta e o espaço inteiros -- as três peles, as duas densidades -- sem servidor gráfico, que é a
mesma razão de `ui/tokens.py` não importar `tkinter`. O que precisa de aplicação viva fica em
`aplicar_tema`, e são duas linhas.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication, QWidget

from chess_diagram_ocr.ui import espaco, estilos, icones, pele, tipografia, tokens
from chess_diagram_ocr.ui import folha_de_estilo as folha_de_estilo_pura

logger = logging.getLogger(__name__)

_Pintavel = TypeVar("_Pintavel", bound=QWidget)
"""Devolver o **mesmo** tipo é o que preserva `rotulo.setText(...)` no ponto de chamada -- a
mesma razão de `theme.pintar` ser genérica."""

# A folha, o recheio e o papel do botão **mudaram de casa** e continuam sendo lidos daqui (F9).
# Eles são decisão de cor e de espaço, não desenho, e por isso moram em `ui/folha_de_estilo.py`
# -- onde um teste consegue afirmá-los sem binding de Qt instalado, que é o que faz o portão de
# contraste do §11.3 rodar no venv da suíte. O reexporte é para que os quinze pontos de chamada
# e os testes já escritos não precisem saber que a fronteira se moveu. `folha_de_estilo` e
# `RECHEIO_DO_TEMA` são definidos adiante: a folha pura mais as regras da barra em fila.
RECHEIO_DA_FOLHA = folha_de_estilo_pura.RECHEIO_DA_FOLHA

__all__ = [
    "CONTROLES_COM_ANEL_DE_FOCO",
    "CONTROLES_COM_MOLDURA",
    "ID_DO_SEPARADOR",
    "INDICADOR_DA_MARCA",
    "LADO_DO_INDICADOR",
    "MARCA_DO_MENU",
    "PROPRIEDADE_DE_PAPEL",
    "RECHEIO_DA_FOLHA",
    "RECHEIO_DO_TEMA",
    "altura_de_linha_atual",
    "altura_do_titulo_atual",
    "alto_contraste_em_vigor",
    "anel_de_foco",
    "ao_repintar",
    "aplicar_paleta",
    "aplicar_papel",
    "aplicar_tema",
    "cor_atual",
    "cromo_escuro_em_vigor",
    "folha_de_estilo",
    "fonte_atual",
    "fonte_base",
    "fonte_pintada",
    "gravar_marcas",
    "lado_do_indicador",
    "pasta_das_marcas",
    "pintar",
    "ponto_do_radio",
    "repintar",
]

_cromo_escuro = False
_alto_contraste = False
"""Se a pele em uso declara cromo escuro. Módulo e não parâmetro pela razão de `ui/theme.py`:
`cor_atual` é chamada de quinze lugares que não conhecem pele nenhuma -- e não deviam conhecer."""

_repinturas: list[Callable[[], object]] = []
"""O que precisa ser repintado quando a pele muda.

Vale menos aqui que no Tk, e continua valendo. A folha de estilo alcança sozinha todo widget que
o Qt desenha -- é a vantagem do QSS sobre o `ttk.Style`, e ela apaga de saída metade do defeito
que a S-224 mediu. O que ela **não** alcança é quem pinta com `QPainter`: a página do PDF, o
tabuleiro e as caixas sobre a folha não têm folha de estilo, e o fundo deles é lido na construção
como era no Tk. Quem pinta se registra ao lado de onde pintou; quem troca a pele chama um lugar.
"""


# --------------------------------------------------------------------- a ponte com os tokens


def cor_atual(papel: str) -> str:
    """Um papel da S-145 resolvido contra a pele em uso. É o que os painéis chamam.

    Papel desconhecido **levanta**, e isso é de propósito: a tolerância deste módulo é a ambiente
    -- fonte que não responde, folha que o Qt recusa --, não a papel escrito errado. É a
    disciplina de `tokens.cor`, e a razão está escrita lá.

    Sem `style`, e a ausência é o item: ver o cabeçalho. Em Qt não existe tema de terceiro a
    quem perguntar, e a paleta medida é a resposta e não a reserva.
    """
    return tokens.cor(papel, None, cromo_escuro=_cromo_escuro)


def ao_repintar(repintura: Callable[[], object]) -> None:
    """Registra o que refazer quando a pele mudar. Chame ao lado de onde pintou."""
    _repinturas.append(repintura)


def repintar() -> None:
    """Refaz o que foi pintado fora da folha de estilo. Nunca levanta, e esquece o que morreu.

    Um widget destruído entre o registro e a troca não é erro: é a janela de antes. No Qt o
    sintoma de tocá-lo é um `RuntimeError: wrapped C/C++ object ... has been deleted` -- o
    equivalente do `TclError` de lá, com outro nome e a mesma causa. Ele sai da lista em vez de
    derrubar a repintura dos outros.
    """
    vivos: list[Callable[[], object]] = []
    for repintura in _repinturas:
        try:
            repintura()
        except RuntimeError:
            continue
        except Exception as exc:  # noqa: BLE001 - uma repintura que falha não derruba as outras
            logger.warning("Repintura falhou e foi descartada: %s", exc)
            continue
        vivos.append(repintura)
    _repinturas[:] = vivos


def pintar(widget: _Pintavel, propriedade: str, papel: str) -> _Pintavel:
    """Pinta uma propriedade CSS do widget com a cor do papel, e a repinta na troca de pele.

    Devolve o próprio widget, para caber onde ele já era anônimo. É o par de `ao_repintar` para
    o caso comum -- e o caso comum é justamente o que se esquece.

    **Some com o restante da folha daquele widget, e é por isso que ela é para exceção.** Um
    `setStyleSheet` no widget substitui a regra dele inteira, não acrescenta a ela. O caminho
    normal em Qt é a folha da aplicação, que já resolve cor por classe; isto é para quem precisa
    de uma cor que depende de estado -- o rótulo que fica vermelho quando a posição é ilegal.
    """

    def aplicar() -> None:
        widget.setStyleSheet(f"{propriedade}: {cor_atual(papel)};")

    aplicar()
    ao_repintar(aplicar)
    return widget


def pintar_varios(widget: _Pintavel, **propriedades: str) -> _Pintavel:
    """`pintar` para mais de uma propriedade de uma vez: `pintar_varios(w, color=X, border=Y)`.

    Existe porque `pintar` **substitui** a folha do widget (ver lá): dois `pintar` seguidos no
    mesmo widget deixam só o segundo. Quem precisa de fundo **e** contorno -- o recorte da
    Galeria, desde o passo 16 da OCR_UI -- declara os dois numa chamada. O valor de cada
    propriedade é um papel de `tokens`; `border` e `outline` ganham `1px solid` na frente.
    """

    def aplicar() -> None:
        regras = []
        for propriedade, papel in propriedades.items():
            nome = propriedade.replace("_", "-")
            valor = cor_atual(papel)
            if nome in ("border", "outline"):
                valor = f"1px solid {valor}"
            regras.append(f"{nome}: {valor};")
        widget.setStyleSheet(" ".join(regras))

    aplicar()
    ao_repintar(aplicar)
    return widget


# ----------------------------------------------------------------------------- a tipografia

FAMILIA_DE_RESERVA = ("Segoe UI", "Consolas")
"""Família proporcional e monoespaçada de quando o Qt não responde. As mesmas de `ui/theme.py`."""


def fonte_base() -> tuple[int, str, str]:
    """`(tamanho, família proporcional, família monoespaçada)` do sistema.

    **É daqui que a escala inteira deriva**, como no Tk: quem aumenta a fonte do Windows aumenta
    a do programa. O que muda é de quem se pergunta -- `QApplication.font()` no lugar da
    `TkDefaultFont`, e `QFontDatabase` no lugar de `tkinter.font.families()`.

    `pointSize()` devolve `-1` quando a fonte foi declarada em pixel, que é o caso de algumas
    configurações de Linux; aí vale `pixelSize()`, pela mesma razão pela qual `ui/theme.py`
    aceita o tamanho negativo do Tk -- a escala só precisa da magnitude.
    """
    tamanho, proporcional, monoespacada = tipografia.BASE_DE_REFERENCIA, *FAMILIA_DE_RESERVA
    try:
        aplicacao = QApplication.instance()
        if aplicacao is None:
            # Sem aplicação não há fonte de sistema a ler, e isto **não** é erro: a folha é
            # construída por função pura de propósito, e o teste que a afirma não abre janela.
            return tamanho, proporcional, monoespacada
        fonte = QApplication.font()
        tamanho = abs(int(fonte.pointSize())) or abs(int(fonte.pixelSize())) or tamanho
        proporcional = str(fonte.family() or proporcional)
        do_qt = str(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family() or monoespacada)
        monoespacada = tipografia.familia_monoespacada(QFontDatabase.families(), do_qt)
    except Exception as exc:  # noqa: BLE001 - Qt sem tela ou fonte exótica: a reserva serve
        logger.debug("Fonte do sistema não lida (%s): usando %s.", exc, FAMILIA_DE_RESERVA)
    return tamanho, proporcional, monoespacada


def fonte_atual(papel: str, *, negrito: bool = False) -> QFont:
    """Um papel da S-149 resolvido contra a fonte do sistema, já como `QFont`.

    Como `cor_atual`: tolerante a ambiente, intolerante a papel escrito errado -- quem levanta é
    `tipografia.fonte`, e a razão está lá.

    **Devolve `QFont` e não a tupla do Tk**, e é a única diferença. A tupla `(família, tamanho,
    "bold")` é a linguagem do `font=` do Tk; aqui o consumidor é `setFont`, e converter no ponto
    de chamada faria cada painel escrever a mesma conversão.
    """
    base, proporcional, monoespacada = fonte_base()
    especificacao = tipografia.fonte(
        papel, base=base, familia=proporcional, mono=monoespacada, negrito=negrito
    )
    fonte = QFont(especificacao[0], especificacao[1])
    # **Os dois eixos da escala, e não só o tamanho** (F9-C3). `tipografia.fonte` devolve a
    # especificação do Tk, que só sabe dizer `"bold"`; o peso de verdade -- 700 no título, 600 no
    # texto que se aperta, 400 no resto -- está em `tipografia.PESOS`, e é aqui que ele entra.
    # `negrito=True` continua ganhando, porque ele é do chamador: a linha escolhida numa lista
    # precisa de peso sem mudar de nível hierárquico.
    fonte.setWeight(QFont.Weight(700 if negrito else tipografia.peso(papel)))
    return fonte


def tabular(fonte: QFont) -> QFont:
    """A mesma fonte com algarismos de largura única (`tnum`). Ver `tipografia.PROPRIEDADE_TABULAR`.

    Tolerante: um Qt sem `setFeature` (anterior ao 6.7) devolve a fonte como veio, e o contador
    continua legível -- só dança. Aparência não derruba ferramenta.
    """
    try:
        fonte.setFeature(QFont.Tag("tnum"), 1)
    except (AttributeError, TypeError):  # pragma: no cover - Qt antigo
        pass
    return fonte


def altura_de_linha_atual(densidade: str = pele.CONFORTAVEL) -> int:
    """A altura de linha de uma tabela para esta fonte e esta densidade, em pixel (S-232).

    O `linespace` vem do Qt quando há aplicação e da conta de `tipografia` quando não há -- a
    mesma reserva de `theme.altura_de_linha_atual`, e pela mesma razão: a decisão continua
    afirmável sem janela.
    """
    base, _proporcional, _mono = fonte_base()
    reserva = round(tipografia.escala(base)[tipografia.CORPO] * 5 / 3)
    try:
        from PyQt6.QtGui import QFontMetrics

        linha = int(QFontMetrics(fonte_atual(tipografia.CORPO)).lineSpacing()) or reserva
    except Exception:  # noqa: BLE001 - sem aplicação ou fonte exótica: a reserva serve
        linha = reserva
    return tipografia.altura_de_linha(linha, densidade=densidade)


def fonte_pintada(seletor: str) -> QFont:
    """A `QFont` com que aquele subcontrole é **desenhado**. Levanta para seletor que a folha não
    pinta.

    **É a pergunta que faltava nesta frente, e a falta dela custou o ciclo 13.** `QWidget.font()`
    responde o que a varredura de `qt/escala.py` pôs no objeto; a folha declara outra coisa no
    `QSS` de subcontrole. Toda régua e todo cálculo de reserva desta janela perguntava uma e media
    a outra -- 9 pt contra 12 pt, peso 400 contra 700 -- e o resultado eram títulos com a metade
    de baixo apagada e cabeçalhos escritos `Resultad·`.

    **Qual das duas ganha depende do seletor, e está medido em `folha_de_estilo.QUEM_PINTA`**
    (F9-C16): a folha ganha em `QHeaderView::section`, `QTabBar::tab:selected` e
    `QLabel[apoio="true"]`, e **perde** em `QGroupBox::title`, onde o Qt desenha com a fonte do
    widget. Esta função responde certo nos dois porque `folha_de_estilo.PAPEL_PINTADO` tira o
    degrau do título de `tipografia.PAPEL_POR_CLASSE["QGroupBox"]` -- que é o mesmo degrau que
    `qt/escala.aplicar_escala` põe no widget. Por construção, e não por as duas tabelas dizerem
    `TITULO` uma ao lado da outra.

    Levanta `KeyError` para seletor fora de `folha_de_estilo.PAPEL_PINTADO`, e é a disciplina de
    `tokens.cor` e de `tipografia.fonte`: um seletor escrito errado que caísse no corpo devolveria
    uma largura plausível e sem significado, que é exatamente o modo de falhar deste ciclo.
    """
    papel = folha_de_estilo_pura.PAPEL_PINTADO.get(seletor)
    if papel is None:
        raise KeyError(
            f"a folha não pinta {seletor!r}. Os que ela pinta estão em "
            f"folha_de_estilo.PAPEL_PINTADO: {sorted(folha_de_estilo_pura.PAPEL_PINTADO)}."
        )
    return fonte_atual(papel)


def altura_do_titulo_atual() -> int:
    """A altura em pixel da fonte com que a folha **pinta** `QGroupBox::title`. Nunca levanta.

    **É a metade desta camada do bloqueante do ciclo 13.** A folha declara
    `QGroupBox::title { font-size: 12pt; font-weight: bold }` e reserva a faixa em que ele cabe
    com `margin-top`; enquanto a reserva saía de `espaco.linha()` -- 4 px na compacta -- o
    primeiro filho do grupo subia para dentro do título e apagava a metade de baixo de cada
    letra. Quem sabe quanto o desenho mede é `QFontMetrics` da fonte que o desenha, e é o que
    esta função pergunta.

    **Ela existe aqui e não em `ui/folha_de_estilo.py` pela fronteira de sempre**: a folha é pura
    e roda no venv sem binding de Qt. Sem aplicação -- ou com fonte exótica --, a reserva é a
    conta pura de `tipografia.altura_do_texto`, que é **por cima** de propósito: reservar de mais
    é ar, reservar de menos é letra apagada.
    """
    base = fonte_base()[0]
    papel = folha_de_estilo_pura.PAPEL_PINTADO["QGroupBox::title"]
    reserva = tipografia.altura_do_texto(tipografia.escala(base)[papel])
    try:
        from PyQt6.QtGui import QFontMetrics

        if QApplication.instance() is None:
            return reserva
        return int(QFontMetrics(fonte_pintada("QGroupBox::title")).height()) or reserva
    except Exception as exc:  # noqa: BLE001 - sem aplicação ou fonte exótica: a reserva serve
        logger.debug("Altura do título não medida (%s): reservando %s px.", exc, reserva)
        return reserva


# ------------------------------------------------------------------------- o papel do botão

PROPRIEDADE_DE_PAPEL = folha_de_estilo_pura.PROPRIEDADE_DE_PAPEL
"""Reexportado de `ui/folha_de_estilo.py`, onde a decisão mora. Aqui fica quem a **aplica**."""


def aplicar_papel(botao: QWidget, papel: str) -> QWidget:
    """Declara o papel de ênfase do botão. Devolve o próprio botão, para caber na montagem.

    Levanta `KeyError` para papel desconhecido -- delegado a `estilos.estilo_de_botao`, que é
    quem tem a lista. Um papel escrito errado que virasse botão cinza é exatamente o estado de
    que a S-144 tirou a janela, e ele voltaria sem ninguém notar.

    O neutro também é declarado, e não omitido: `unpolish`/`polish` abaixo precisa de um valor
    para reavaliar o seletor quando um botão **deixa** de ser primário, e a ausência da
    propriedade não dispara isso.
    """
    estilos.estilo_de_botao(papel)  # levanta para papel desconhecido; a lista é de lá
    botao.setProperty(PROPRIEDADE_DE_PAPEL, papel)
    # Sem isto o Qt não reavalia o seletor de um widget já mostrado: trocar a propriedade em
    # execução não repinta nada, e o sintoma é um botão que só fica azul se nascer azul.
    estilo = botao.style()
    if estilo is not None:
        estilo.unpolish(botao)
        estilo.polish(botao)
    return botao


# ------------------------------------------------------------------------ a folha de estilo
#
# **A folha em vigor é a de `ui/folha_de_estilo.py` (F9)**, e as declarações abaixo são as da
# barra em fila e do indicador (S-520/S-522/S-527/S-553), que nasceram nesta casa quando a folha
# ainda morava aqui. Entram na folha, por `_regras_da_barra_em_fila`, só as que a folha pura não
# tem: o recheio do botão só-ícone, o indicador de menu do "Mais", o traço entre os grupos da fila,
# o papel no `QToolButton`, o marcado do botão comum e o anel de foco no indicador da caixa e do
# rádio. As que dizem o mesmo que a folha pura com outro desenho -- `RELEVO_DO_BOTAO`,
# `CONTROLES_COM_MOLDURA`, `CONTROLES_COM_ANEL_DE_FOCO`, `INDICADOR_DA_MARCA` e `MARCA_DO_MENU` --
# ficam declaradas e **não** entram: a face, a moldura, o anel e o indicador que valem são os do F9.

PROPRIEDADE_DE_NIVEL = "nivel"
"""A propriedade do `QToolButton` que diz se ele desenha só o ícone (`NIVEL_ICONE`) ou ícone e texto
(`NIVEL_TEXTO`) -- é `barra_da_sala.Acao.com_texto` chegando à folha (S-527, segunda rodada).

Existe porque o recheio horizontal de dez pixels, certo para um botão com texto, é o que impedia a
fila de caber: um botão só com ícone saía com 41 px para um traço de 16, e a 702 px de aba cabiam
oito. Com o recheio de `RECHEIO_DO_TEMA` para o nível de ícone cabem dez, que era a meta do crítico."""

NIVEL_ICONE = "icone"
NIVEL_TEXTO = "texto"
SELETOR_DO_NIVEL_ICONE = f'QToolButton[{PROPRIEDADE_DE_NIVEL}="{NIVEL_ICONE}"]'

RECHEIO_DO_TEMA: dict[str, tuple[int, int]] = {
    **folha_de_estilo_pura.RECHEIO_DO_TEMA,
    # O botão só com ícone: quatro pixels de recheio horizontal (o mesmo vertical -- a fila tem uma
    # altura). Medido em 2026-09-04: com 10 cabiam 8 botões a 702 px; com 5, 10; com 4, as catorze
    # principais cabem na aba de 804 px que a janela de 1920×1080 abre.
    SELETOR_DO_NIVEL_ICONE: (4, 4),
}
"""`seletor -> (horizontal, vertical)` em pixel na base 9: os quatro de `ui/folha_de_estilo.py` --
o que o `ttkbootstrap` dava e o Qt não dá, com a medição escrita lá -- mais o do botão só-ícone da
barra em fila (S-527), que é a única entrada que a folha pura ainda não declara."""

RELEVO_DO_BOTAO = 0.06
"""Quanto do texto entra na face do botão neutro, de 0 a 1 (S-520).

Um degrau, e não uma cor: seis por cento do texto sobre o painel dá a face; o dobro é o `:hover` e
o quádruplo é o pressionado e o marcado. Escalar a partir de um número só é o que faz os quatro
estados serem **um** desenho em vez de quatro escolhas -- e é o mesmo mecanismo de
`REALCE_DE_ENFASE`, que a S-444 já usa para o primário e o destrutivo."""

CONTROLES_COM_MOLDURA: tuple[str, ...] = (
    "QComboBox",
    "QLineEdit",
    "QSpinBox",
    "QAbstractItemView",
    "QTextEdit",
    "QPlainTextEdit",
)
"""As classes a que a folha declara moldura porque o estilo da plataforma deixou de desenhá-la (S-522).

Uma propriedade de folha num widget -- e a linha do `QWidget` da folha é uma -- faz o `windows11`
parar de pintar o cromo nativo dele: o preenchimento entra e a moldura não vem de lugar nenhum.
Medido na janela de verdade, borda contra superfície, para combo, campo de texto, spin, lista e
editor: **1,14:1** na pele clássica e **1,02:1** na "Foco". E a CI não tinha como ver, porque sob
`offscreen` o `fusion` desenha o cromo mesmo com folha aplicada -- 2,02:1 e 1,10:1 nas mesmas
fotografias. Declarar a borda é o que faz os dois estilos desenharem o mesmo controle.

`QAbstractItemView` alcança lista, árvore e tabela; `QTextEdit`, o `QTextBrowser`. O botão comum e o
`QGroupBox` já a declaravam (S-520, S-501) -- com o token de documento, que a S-522 trocou."""

CONTROLES_COM_ANEL_DE_FOCO: tuple[str, ...] = ("QPushButton", "QToolButton", *CONTROLES_COM_MOLDURA)
"""As classes a que a folha declara **anel de foco de teclado** (S-553).

**O defeito medido, e ele é o mesmo nas três peles.** Com o botão focado (`hasFocus()` verdadeiro)
a barra da sala desenhava **zero pixels** diferentes do não focado -- no primário, no comum e no
só-ícone. São doze paradas de `Tab` naquela fila, e nenhuma delas se vê. É a WCAG 2.4.7 AA, e é o
que o ChessBase e o Lichess desenham.

**A causa tem duas metades, e as duas foram medidas.** A folha declara `border: 1px solid
transparent` no `QToolButton` (para que ligar a cor de um estado não mova o conteúdo, S-527), e uma
borda de folha de estilo **substitui** o retângulo de foco que o estilo da plataforma desenharia.
E o `offscreen` da CI não desenharia esse retângulo nem sem folha nenhuma: medido, `QToolButton`,
`QPushButton`, `QComboBox`, `QCheckBox` e `QListWidget` saem com 0 px de diferença com a folha
vazia. Ou seja, **não há de quem herdar o anel**: ou a folha o declara, ou ele não existe.

**Todas as oito já têm moldura de 1 px, e é isso que faz o anel não custar layout.** O anel é a
moldura que já existe trocando de cor -- não `padding` novo, não `border-width` maior: os dois
moveriam o conteúdo em um pixel, que é o defeito que a moldura transparente do `QToolButton`
existe para não ter. (`outline` foi medido e **não serve**: com `outline: 1px solid` o
`QToolButton` continua desenhando 0 px de diferença; o `QPushButton` muda 64. O Qt não o aplica a
todo controle, e um anel que existe em metade da fila é pior que nenhum.)

**A `QCheckBox` e a `QRadioButton` continuam fora desta lista, e agora por outro motivo.** Na
primeira rodada elas ficaram de fora por medo: declarar propriedade nelas faria o `windows11` parar
de pintar o cromo nativo, e ali o cromo nativo é o **indicador**. O medo estava certo na causa e
errado na conclusão -- o estrago **já estava feito** desde a S-442, que declarou `spacing`, e desde
a S-441, que declarou `padding`. O crítico fotografou o resultado em 2026-09-05: o rádio marcado
saía como texto pelado, sem indicador nenhum, na aba que abre primeiro. Quem declara o indicador
agora é `INDICADOR_DA_MARCA`, logo abaixo, e o anel de foco delas vai **no indicador** e não no
widget: um `QCheckBox:focus { border: ... }` cercaria o rótulo inteiro e moveria o texto de todo
diálogo em um pixel a cada `Tab`, que é justamente o que esta lista existe para não fazer.
"""


LADO_DO_INDICADOR = 13
"""O lado do quadradinho da caixa de seleção e do círculo do rádio, em pixel na base 9 (S-553,
segunda rodada).

**Treze porque é o que o Windows desenha a 96 DPI**, e a folha o escala pela fonte do sistema como
escala todo o resto -- um pixel cravado aqui ignoraria quem aumentou a fonte, que é o defeito de
DPI da S-148 num lugar menor.

**A densidade não entra, e é a diferença em relação a `_escalado`.** Folga é espaço em volta e pode
encolher: é para isso que a pele compacta existe. Isto é o alvo do ponteiro, e encolhê-lo 30% na
compacta seria trocar "cabe mais linha na tela" por "erra-se mais o clique" -- o piso de alvo é o
que a WCAG 2.5.5 mede, e ele não é uma folga."""

INDICADOR_DA_MARCA: tuple[str, ...] = ("QCheckBox", "QRadioButton")
"""As duas classes cujo indicador a folha desenha inteiro (S-553, segunda rodada).

**O defeito medido, e ele estava na aba que abre primeiro.** "Lado a jogar: Pretas" selecionado
saía como texto pelado -- indicador nenhum --, e a caixa de seleção saía como um `✓` solto sem
quadro quando marcada contra um quadro vazio quando desmarcada: duas gramáticas para o mesmo par de
estados. A causa é a da S-522, e vale para todo widget: **uma propriedade de folha faz o
`windows11` parar de pintar o cromo nativo daquele widget**. Aqui o cromo nativo é o indicador, e
`spacing` (S-442) e `padding` (S-441) bastaram para apagá-lo.

**A marca é tinta de ênfase dentro da mesma moldura, e é uma gramática só.** Desmarcado: campo da
superfície com a moldura do cromo. Marcado: a moldura e o campo viram `BOTAO_PRIMARIO` -- na caixa,
a face inteira; no rádio, o ponto no meio, que é o desenho que todo toolkit dá a um rádio.
Desabilitado: a marca cai para `TEXTO_SECUNDARIO`, que é o mesmo apagamento do botão comum
desabilitado (S-506). Focado: a moldura de 1 px troca de cor pela cor do anel, exatamente como nas
outras oito classes -- sem `padding` novo e sem `border-width` maior, para o `Tab` não mover o
rótulo.

**Por que não há um glifo de `✓`.** Uma folha de estilo só põe imagem por `url(...)`, que quer
dizer arquivo ou recurso compilado -- e um `✓` de arquivo teria cor fixa, o que quebraria as três
peles. `folha_de_estilo` é pura de propósito (ver o cabeçalho) e não pode desenhar um `QPixmap`.
Então a marca da caixa é a **face**, que é o que o desenho chato de qualquer interface moderna faz,
e ela combina com o ponto do rádio: nos dois, marcado é tinta de ênfase dentro da moldura."""

MARCA_DO_MENU = "QMenu"
"""O item de menu marcável usa a **mesma** gramática das duas acima (S-553, terceira rodada).

**Havia duas gramáticas de "marcado" na mesma janela**, e o crítico as fotografou lado a lado: a
caixa marcada era face de ênfase dentro da moldura, e o item de menu marcado era um `✓` nativo --
tique sem quadro, e quadro sem tique, para o mesmo par de estados. Duas gramáticas custam o mesmo
que duas palavras para a mesma coisa: quem aprende uma não lê a outra.

**Qual das duas ficou, e por quê.** A face, e por três razões, nesta ordem: ela é a que já vale nas
duas classes onde "marcado" aparece mais -- as caixas de todo diálogo e os rádios do rodapé da
Galeria --; ela **não depende de imagem**, e é o que a mantém dentro de uma folha pura que serve às
três peles (ver o parágrafo acima); e ela é o desenho que o Windows 11 dá a uma caixa marcada, de
modo que o menu passa a concordar com o sistema em vez de discordar da própria janela.

**A alternativa medida e recusada:** pôr o tique **dentro** da face, como o Windows faz. O `✓` só
entra numa folha de estilo por `url(...)`, que quer dizer arquivo ou recurso -- e um arquivo tem cor
fixa, o que quebraria a pele escura. Fazê-lo direito exigiria um `QPixmap` desenhado fora da folha
(como `qt/icones.py` faz), gravado em disco a cada troca de pele para o `url()` o alcançar, e a
folha deixaria de ser afirmável por leitura de texto -- que é como todo este arquivo é testado. O
tique é um detalhe; a gramática única é o item."""


def ponto_do_radio(marca: str, campo: str) -> str:
    """O pincel do rádio marcado: anel de campo com o ponto no meio, como texto de QSS.

    Um `qradialgradient` e não uma imagem, pela razão escrita em `INDICADOR_DA_MARCA`: a folha é
    pura, e a cor tem de seguir a pele. As paradas são duras de propósito -- o que se quer é um
    ponto, não um borrão --, e a de 0,42 dá um ponto de ~5,5 px num indicador de 13.
    """
    return (
        "qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,"
        f" stop:0 {marca}, stop:0.42 {marca}, stop:0.5 {campo}, stop:1 {campo})"
    )


def lado_do_indicador(base: int = tipografia.BASE_DE_REFERENCIA) -> int:
    """`LADO_DO_INDICADOR` reescrito para esta fonte. Piso de 12 px: abaixo disso o ponto do rádio
    fica com menos de 5 px e some."""
    return max(12, round(LADO_DO_INDICADOR * base / tipografia.BASE_DE_REFERENCIA))


def anel_de_foco(*, cromo_escuro: bool = False, sobre_enfase: bool = False) -> str:
    """A cor do anel de foco daquele controle. **Pura, e não é um papel novo** (S-553).

    É a tinta que o próprio controle já usa: sobre o cromo -- botão comum, botão de ferramenta
    chato, campo, lista -- `TEXTO_PADRAO`; sobre a face de ênfase, `TEXTO_SOBRE_ENFASE`. As duas
    são obrigadas a se ler ali de qualquer forma: a primeira é a letra da janela, e a segunda passa
    `AA_TEXTO` sobre as duas faces por medição da S-444. Um décimo papel em `ui/tokens.py` para
    dizer "a cor do anel" seria a mesma cor com dois donos, que é o defeito que a S-145 fechou.

    **E é o que separa o anel do marcado, que é o critério do item.** O `QToolButton:checked` se
    diz por **duas** coisas -- a face funda e uma moldura na cor de ênfase (S-527) --, e o anel usa
    a letra, que nunca é a cor de ênfase. Os quatro estados ficam distintos aos pares: parado
    (moldura transparente), marcado (face funda e moldura de ênfase), focado (moldura de letra),
    marcado e focado (face funda e moldura de letra). O marcado não perde o que o diz, porque o que
    o diz de verdade é a face; o que o foco toma emprestado é a moldura, que é onde o foco mora em
    toda interface que o desenha.
    """
    papel = tokens.TEXTO_SOBRE_ENFASE if sobre_enfase else tokens.TEXTO_PADRAO
    return tokens.cor(papel, None, cromo_escuro=cromo_escuro)


ID_DO_SEPARADOR = "separador-da-fila"
"""`objectName` do traço entre grupos da fila, que a folha pinta com a moldura do cromo (S-522)."""


def _regras_da_barra_em_fila(
    *, cromo_escuro: bool, base: int, densidade: str
) -> tuple[list[str], list[str]]:
    """As regras que a folha pura não tem, como `(antes, depois)` dela. **Pura.**

    **Antes** vai o que tem seletor próprio: o empate de especificidade com um estado da folha pura
    (`QToolButton:checked`, `:disabled`, `:hover`) tem de ser desfeito a favor do estado, que vem
    depois -- é a mesma ordem em que a S-527 as escreveu. **Depois** vai o que tem de ganhar de
    uma regra da folha pura com o mesmo peso: o marcado do botão comum ganha do `:hover`, e o anel
    no indicador ganha da moldura dele.

    **O papel no `QToolButton` fala a gramática da folha pura** (`QPushButton[papel=...]` em
    `ui/folha_de_estilo.py`): o realce anda para longe da letra, o pressionado escurece e o
    desabilitado apaga para `TEXTO_MORTO` -- a mesma tinta de `qt/icones.PAPEL_APAGADO`, para o
    ícone e o rótulo do botão apagarem juntos (S-554). O destrutivo ganha a **cor**, e não a face:
    dois blocos vermelhos sólidos numa fila de botões chatos pediriam cuidado o tempo todo (S-527).
    """

    def cor(papel: str) -> str:
        return tokens.cor(papel, None, cromo_escuro=cromo_escuro)

    def escalado(pixel: int) -> int:
        return folha_de_estilo_pura._escalado(pixel, base=base, densidade=densidade)

    superficie = cor(tokens.SUPERFICIE_PADRAO)
    morto = cor(tokens.TEXTO_MORTO)
    separador = cor(tokens.SEPARADOR)
    letra = cor(tokens.TEXTO_SOBRE_ENFASE)
    horizontal, vertical = RECHEIO_DO_TEMA[SELETOR_DO_NIVEL_ICONE]

    # Os dois papéis com face, **nomeados uma vez**: a guarda de `test_ui_estilos` conta por `ast`
    # quantas vezes um arquivo cita o papel primário.
    (papel_primario, token_primario), (papel_destrutivo, token_destrutivo) = (
        (estilos.PRIMARIO, tokens.BOTAO_PRIMARIO),
        (estilos.DESTRUTIVO, tokens.BOTAO_DESTRUTIVO),
    )
    face = cor(token_primario)
    sob_o_ponteiro = tokens.afastar(face, letra, tokens.REALCE_DE_ENFASE)
    pressionado = tokens.escurecer(face, folha_de_estilo_pura.ESCURECIMENTO_DO_PRESSIONADO)
    letra_pressionada = folha_de_estilo_pura.letra_do_pressionado(pressionado, letra)
    ferramenta_primaria = f'QToolButton[{PROPRIEDADE_DE_PAPEL}="{papel_primario}"]'
    anel = anel_de_foco(cromo_escuro=cromo_escuro)

    antes = [
        f"{SELETOR_DO_NIVEL_ICONE} {{ padding: {escalado(vertical)}px {escalado(horizontal)}px; }}",
        # O indicador de menu **na linha do texto**, e não no canto de baixo: é o chevron do
        # "Mais ▾", que o crítico da S-527 mediu solto ~8 px abaixo da base da letra. O botão com
        # menu instantâneo (`popupMode` 2) reserva o recheio à direita para ele.
        "QToolButton::menu-indicator { subcontrol-origin: padding; subcontrol-position: center right; }",
        f'QToolButton[popupMode="2"] {{ padding-right: {escalado(16)}px; }}',
        # O separador da fila é um `QWidget` de 1 px pintado aqui, e não um `QFrame.VLine`: o
        # `VLine` desenha com a cor de **texto** da paleta, e não com a da folha (S-522).
        f"QWidget#{ID_DO_SEPARADOR} {{ background-color: {tokens.moldura_sobre(superficie)}; }}",
        f"{ferramenta_primaria} {{ background-color: {face}; color: {letra}; border: 1px solid {face}; }}",
        f"{ferramenta_primaria}:hover {{ background-color: {sob_o_ponteiro}; border: 1px solid {sob_o_ponteiro}; }}",
        f"{ferramenta_primaria}:pressed {{ background-color: {pressionado}; color: {letra_pressionada};"
        f" border: 1px solid {pressionado}; }}",
        f"{ferramenta_primaria}:disabled {{ background-color: {superficie}; color: {morto};"
        f" border: 1px solid {separador}; }}",
        f"{ferramenta_primaria}:focus {{ border: 2px solid {letra}; }}",
        f'QToolButton[{PROPRIEDADE_DE_PAPEL}="{papel_destrutivo}"] {{ color: {cor(token_destrutivo)}; }}',
    ]
    depois = [
        # **O botão comum marcado se vê** (S-520): o marcado do `QPushButton` não tinha regra, e um
        # modo ligado num botão marcável desenhava igual ao desligado. A tinta é a do
        # `QToolButton:checked` da folha pura -- uma gramática de "ligado" para os dois botões.
        f"QPushButton:checked {{ background-color: {cor(tokens.SELECAO)}; color: {cor(tokens.TEXTO_SOBRE_SELECAO)};"
        f" border: 1px solid {cor(tokens.FOCO)}; }}",
        # **O anel de foco da caixa e do rádio vai no indicador** (S-553, segunda rodada): no
        # widget ele cercaria o rótulo inteiro. É a moldura de 2 px do indicador da folha pura
        # trocando de cor -- nenhum pixel a mais --, na tinta de `anel_de_foco`, que se lê sobre o
        # campo e sobre a face de ênfase do marcado, onde o azul de foco sumiria.
        f"QCheckBox::indicator:focus, QRadioButton::indicator:focus {{ border: 2px solid {anel}; }}",
        f"QCheckBox::indicator:checked:focus, QRadioButton::indicator:checked:focus {{ border: 2px solid {anel}; }}",
    ]
    return antes, depois


def folha_de_estilo(
    *,
    cromo_escuro: bool = False,
    base: int = tipografia.BASE_DE_REFERENCIA,
    densidade: str = pele.CONFORTAVEL,
    marcas: dict[str, str] | None = None,
    altura_do_titulo: int | None = None,
) -> str:
    """A folha de estilo inteira, como texto: a de `ui/folha_de_estilo.py` e a da barra em fila.

    **Pura, como a de lá**: não toca `QApplication` nem widget, e levanta `KeyError` para densidade
    desconhecida. `marcas` e `altura_do_titulo` vão direto para a folha pura -- ver lá. As regras
    próprias desta casa e a ordem delas estão em `_regras_da_barra_em_fila`.
    """
    antes, depois = _regras_da_barra_em_fila(cromo_escuro=cromo_escuro, base=base, densidade=densidade)
    pura = folha_de_estilo_pura.folha_de_estilo(
        cromo_escuro=cromo_escuro,
        base=base,
        densidade=densidade,
        marcas=marcas,
        altura_do_titulo=altura_do_titulo,
    )
    return "\n".join([*antes, pura, *depois])


def aplicar_paleta(alvo: QApplication, *, cromo_escuro: bool) -> None:
    """Põe os papéis na `QPalette` da aplicação, além da folha de estilo.

    **A folha não alcança tudo, e a prancha de controles é quem mostrou onde.** Um item de
    `QListWidget` é desenhado por um *delegate*, que pinta o fundo do selecionado com
    `QPalette.Highlight` -- `QStyle.drawPrimitive(PE_PanelItemViewItem)` lê `option.palette`, e
    não a folha. A fotografia de `amostrario_claro.png` tinha a linha da lista no azul de fábrica
    do Windows e a linha da tabela no `SELECAO` da paleta: **duas cores de "selecionado" na mesma
    imagem**, que é exatamente o defeito que `ui/tokens.py` existe para não ter.

    **Quem decide continua sendo `ui/`.** O mapa papel-de-paleta -> papel-de-token é
    `folha_de_estilo.PAPEIS_DA_PALETA`, um dicionário de strings; aqui só se traduz o nome em
    `QPalette.ColorRole` e se pinta. É a mesma fronteira da folha de estilo, e é o que permite
    afirmar a paleta inteira num venv sem binding de Qt.

    Nome público desde a F9: ela é chamada de `aplicar_tema` e do arnês de auditoria, e um
    privado chamado de dois lugares é um público envergonhado.
    """
    from PyQt6.QtGui import QColor, QPalette

    def tinta(papel: str) -> QColor:
        return QColor(tokens.cor(papel, None, cromo_escuro=cromo_escuro))

    def papel_de(nome: str) -> object | None:
        # `getattr` e não um `dict` de enums: um nome de papel que o Qt desta versão não tenha
        # não pode custar a paleta inteira -- é o mesmo contrato de degradação de `aplicar_tema`.
        return getattr(QPalette.ColorRole, nome, None)

    paleta = QPalette(alvo.palette())
    for grupo in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for nome, token in folha_de_estilo_pura.PAPEIS_DA_PALETA.items():
            papel = papel_de(nome)
            if papel is not None:
                paleta.setColor(grupo, papel, tinta(token))
    for nome, token in folha_de_estilo_pura.PAPEIS_DA_PALETA_MORTA.items():
        papel = papel_de(nome)
        if papel is not None:
            paleta.setColor(QPalette.ColorGroup.Disabled, papel, tinta(token))
    alvo.setPalette(paleta)


def alto_contraste_em_vigor() -> bool:
    """Se `aplicar_tema` deixou o alto contraste do sistema valendo (C14): quem desenha à mão --
    o tabuleiro, o visor -- pergunta aqui para trocar cor por contorno."""
    return _alto_contraste


def cromo_escuro_em_vigor() -> bool:
    """Se o cromo desta sessão está escuro. É o que `aplicar_tema` deixou valendo.

    Existe para o teste poder afirmar o **efeito** da troca de pele sem ler um privado -- e para
    quem desenha à mão (o tabuleiro, o visor) poder perguntar sem repetir a decisão.

    **Vem do PR #25**, que atacou a troca de pele em paralelo a este trabalho. A diferença entre
    afirmar isto e afirmar a *chamada* de `aplicar_tema` com um `mock` é a diferença entre medir o
    efeito e medir o caminho: o segundo continua verde no dia em que `aplicar_tema` receber o
    argumento e não fizer nada com ele.
    """
    return _cromo_escuro


def pasta_das_marcas() -> Path:
    """Onde os dois desenhos do indicador ficam. Uma pasta por usuário, estável entre sessões.

    Estável e não `mkdtemp` de propósito: a folha de estilo é reconstruída a cada troca de pele e
    de densidade, e uma pasta nova por troca encheria o temporário do usuário de pastas de dois
    arquivos que ninguém apaga.
    """
    return Path(tempfile.gettempdir()) / "chessvisionoff-marcas"


def gravar_marcas(
    *,
    cromo_escuro: bool,
    base: int = tipografia.BASE_DE_REFERENCIA,
    densidade: str = pele.CONFORTAVEL,
) -> dict[str, str]:
    """Desenha o visto e o traço do indicador em disco e devolve `{nome: caminho}` (F9-C2).

    **Por que em disco.** `url()` de folha de estilo Qt lê arquivo ou recurso compilado, e nada
    mais: não existe forma de entregar um `QPixmap` a um `QSS`. Compilar um `.rcc` poria arte
    binária no repositório para um desenho que já é declarativo em `ui/icones.MARCAS` -- e que
    precisa mudar de cor com a pele, o que um recurso compilado não faz.

    **A tinta é `TEXTO_SOBRE_ENFASE`, e ela não é escolha nova.** É a letra que a folha já põe
    sobre a face primária, e o portão `test_a_enfase_passa_no_piso` garante que ela fica acima de
    4,5:1 contra aquela face nas duas peles. A marca é um rótulo desenhado: usar a mesma tinta é o
    que a mantém sob o mesmo portão. `sobre_superficie` **não** serve aqui, e foi medido: ela
    devolve a letra de cromo (`#5c5c5c` na pele escura), que sobre `#6ea8fe` some.

    Devolve `{}` -- e a folha volta ao preenchimento sólido do ciclo 1 -- se a Pillow não estiver
    lá ou se a pasta não puder ser escrita. Aparência não derruba ferramenta (S-53).
    """
    lado = max(8, round(14 * base / tipografia.BASE_DE_REFERENCIA))
    tinta = tokens.cor(tokens.TEXTO_SOBRE_ENFASE, None, cromo_escuro=cromo_escuro)
    caminhos: dict[str, str] = {}
    try:
        pasta = pasta_das_marcas()
        pasta.mkdir(parents=True, exist_ok=True)
        for nome in (icones.MARCA_VISTO, icones.MARCA_TRACO):
            desenho = icones.imagem(nome, lado, tinta)
            if desenho is None:
                continue
            # O nome carrega a cor e o lado: duas peles abertas na mesma sessão gravariam o mesmo
            # arquivo com tintas diferentes, e a segunda leria o cache da primeira.
            arquivo = pasta / f"{nome}_{tinta.lstrip('#')}_{lado}.png"
            if not arquivo.exists():
                desenho.save(arquivo)
            caminhos[nome] = str(arquivo)
    except Exception as exc:  # noqa: BLE001 - ver o docstring: sem marca, a face sólida serve
        logger.warning("Marcas do indicador não gravadas (%s): a caixa fica só com a cor.", exc)
        return {}
    return caminhos


def aplicar_tema(
    aplicacao: QApplication | None = None,
    *,
    cromo_escuro: bool = False,
    densidade: str = pele.CONFORTAVEL,
) -> str:
    """Aplica a folha na aplicação e devolve o que ficou valendo. Nunca levanta.

    Devolve `"qss"` quando a folha entrou e `"sem_folha"` quando não havia aplicação a que aplicá-la
    -- que é o mesmo par de respostas de `theme.apply_theme` (`nome do tema` / `"ttk"`), com os
    nomes deste lado. Chamar isto não pode ser o motivo de a janela não abrir.

    **Fixa o espaço junto, e dentro desta função de propósito** (S-447). `espaco.ajustar` é o que
    faz `espaco.linha()` responder sem que cada painel saiba de densidade, e esta é a única
    função do frontend que conhece fonte **e** densidade sem que ninguém as passe adiante -- é o
    argumento de `theme.registrar_estilos`, e ele não muda de toolkit.
    """
    global _cromo_escuro, _alto_contraste
    _cromo_escuro = cromo_escuro

    base = fonte_base()[0]
    try:
        espaco.ajustar(base=base, densidade=densidade)
    except KeyError as exc:
        # Densidade escrita errada é erro de chamador, mas ele não pode custar a janela: cai na
        # confortável, que é o padrão, e o log diz o nome recusado.
        logger.warning("Densidade %s recusada (%s): seguindo na confortável.", densidade, exc)
        densidade = pele.CONFORTAVEL
        espaco.ajustar(base=base, densidade=densidade)

    alvo = aplicacao or QApplication.instance()
    if not isinstance(alvo, QApplication):
        logger.info("Sem QApplication: a folha de estilo não foi aplicada (S-501).")
        return "sem_folha"

    # C14 do ciclo 2: com o alto contraste do Windows ligado, a pele **não** entra. A paleta que
    # a pessoa escolheu no sistema é a que vale (Carta §3.2); folha e paleta próprias por cima
    # dela seriam exatamente o que o modo existe para impedir. A folha que estivesse aplicada
    # é retirada, para a troca de pele em sessão respeitar a mesma regra.
    from chess_diagram_ocr.qt.plataforma import alto_contraste_ativo

    _alto_contraste = alto_contraste_ativo()
    if _alto_contraste:
        alvo.setStyleSheet("")
        alvo.setPalette(alvo.style().standardPalette())
        logger.info("Alto contraste do sistema ativo: folha e paleta próprias não aplicadas (C14).")
        repintar()
        return "alto_contraste"

    try:
        alvo.setStyleSheet(
            folha_de_estilo(
                cromo_escuro=cromo_escuro,
                base=base,
                densidade=densidade,
                marcas=gravar_marcas(cromo_escuro=cromo_escuro, base=base, densidade=densidade),
                altura_do_titulo=altura_do_titulo_atual(),
            )
        )
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.warning("Folha de estilo não aplicada (%s): a janela abre no cinza do sistema.", exc)
        return "sem_folha"

    # **A paleta é a segunda camada, e sem esta chamada a primeira mente.** O `QStyle` desenha o
    # item selecionado de toda `QAbstractItemView` a partir de `option.palette`, e não da folha:
    # sem isto a lista sai no azul de fábrica do Windows e a tabela no `SELECAO` -- duas cores de
    # "selecionado" na mesma janela, fotografado em `amostrario_claro.png`. Ela não pode derrubar
    # a janela pela mesma razão da folha: aparência não derruba ferramenta.
    try:
        aplicar_paleta(alvo, cromo_escuro=cromo_escuro)
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.warning("Paleta não aplicada (%s): o desenho nativo segue com a do sistema.", exc)

    logger.info(
        "Tema da interface: folha própria, cromo %s, densidade %s (Qt).",
        "escuro" if cromo_escuro else "claro",
        densidade,
    )
    repintar()
    return "qss"
