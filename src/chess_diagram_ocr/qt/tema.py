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
from collections.abc import Callable
from typing import TypeVar

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication, QWidget

from chess_diagram_ocr.ui import espaco, estilos, folha, pele, tipografia, tokens

logger = logging.getLogger(__name__)

_Pintavel = TypeVar("_Pintavel", bound=QWidget)
"""Devolver o **mesmo** tipo é o que preserva `rotulo.setText(...)` no ponto de chamada -- a
mesma razão de `theme.pintar` ser genérica."""

__all__ = [
    "CONTROLES_COM_ANEL_DE_FOCO",
    "CONTROLES_COM_MOLDURA",
    "ID_DO_SEPARADOR",
    "INDICADOR_DA_MARCA",
    "LADO_DO_INDICADOR",
    "PROPRIEDADE_DE_PAPEL",
    "RECHEIO_DO_TEMA",
    "altura_de_linha_atual",
    "anel_de_foco",
    "ao_repintar",
    "aplicar_papel",
    "aplicar_tema",
    "cor_atual",
    "cromo_escuro_em_vigor",
    "folha_de_estilo",
    "fonte_atual",
    "fonte_base",
    "lado_do_indicador",
    "pintar",
    "ponto_do_radio",
    "repintar",
]

_cromo_escuro = False
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
    fonte.setBold(len(especificacao) > 2)
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


# ------------------------------------------------------------------------- o papel do botão

PROPRIEDADE_DE_PAPEL = "papel"
"""A propriedade dinâmica que carrega o papel de `ui/estilos.py` até a folha de estilo.

**É o `style="primary.TButton"` do Qt, e a tradução é obrigatória.** Lá o papel vira nome de
estilo `ttk`; aqui vira propriedade que o seletor `QPushButton[papel="PRIMARIO"]` lê. O que
**não** muda é quem decide o papel: `ui/estilos.py` continua sendo a única fonte, e
`estilos.conferir_barra` -- que é pura -- continua cobrando uma ênfase por barra nos dois
frontends.

O valor é o próprio nome do papel (`"PRIMARIO"`, `"DESTRUTIVO"`) e não um segundo vocabulário:
uma segunda tabela de nomes seria a divergência que `estilos.estilo_de_botao` existe para não
deixar acontecer.
"""


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
    "QPushButton": (10, 4),
    "QToolButton": (10, 4),
    # O botão só com ícone: quatro pixels de recheio horizontal (o mesmo vertical -- a fila tem uma
    # altura). Medido em 2026-09-04: com 10 cabiam 8 botões a 702 px; com 5, 10; com 4, as catorze
    # principais cabem na aba de 804 px que a janela de 1920×1080 abre.
    SELETOR_DO_NIVEL_ICONE: (4, 4),
    "QLineEdit": (5, 5),
    "QComboBox": (5, 4),
}
"""`seletor -> (horizontal, vertical)` em pixel na base 9, do que o **`ttkbootstrap` dava e o Qt
não dá**.

Os números não são novos: são a medição que está escrita em `ui/folha.py`, feita sob
`bootstrap-light` e `bootstrap-dark`, e o docstring de lá explica por que a folha do Tk **não**
os escreve -- naquele frontend o tema já os deu, e sobrescrevê-los foi medido e piorou (o botão
de fita encolheu de 58 para 50 px).

Aqui a conta inverte. Não há `ttkbootstrap`, então ninguém deu: um `QPushButton` sem folha sai
com o recheio de fábrica do estilo da plataforma, que no `Fusion` é outro número e no `offscreen`
da CI é outro ainda. **Herdar os quatro valores medidos é o que faz os dois frontends
desenharem o mesmo botão** -- e é por isso que eles ficam aqui em vez de virar um quinto papel
em `ui/tipografia.py`: eles não são uma escala nova, são o que o outro tema já entregava.

`_escalado` os faz acompanhar a fonte do sistema e a densidade, que é o que `ui/folha.py`
ganhou ao derivar tudo de `tipografia.FOLGAS` -- um pixel cravado aqui ignoraria quem aumentou a
fonte do Windows, que é o defeito de DPI da S-148 num lugar menor.
"""

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

RECHEIO_DA_FOLHA: dict[str, str] = {
    "QTabBar::tab": "TNotebook.Tab",
    "QCheckBox": "TCheckbutton",
    "QRadioButton": "TRadiobutton",
    "QSpinBox": "TSpinbox",
    "QDoubleSpinBox": "TSpinbox",
    "QGroupBox": "TLabelframe",
}
"""`seletor Qt -> classe de `ui/folha.py``, para o recheio sair da mesma tabela nos dois frontends.

**Nenhum número aqui, e é o item.** A folga da aba, a da caixa de seleção e a do grupo são
decisões que já passaram por revisão na S-441 -- e `folha.recheio` é pura, então este módulo
pergunta a ela em vez de repetir a resposta. Um dia em que a folga da aba mude, ela muda para as
duas janelas.

`QDoubleSpinBox` mapeia para a mesma classe do `QSpinBox` porque no Tk os dois são `TSpinbox`:
dois campos de número lado a lado com recheio diferente é a inconsistência que aquela folha
existe para não deixar acontecer.
"""


def _escalado(pixel: int, *, base: int, densidade: str) -> int:
    """Um pixel medido na base de referência, reescrito para esta fonte e esta densidade.

    É a conta de `tipografia.folga` sem a tabela de papéis: os quatro valores de
    `RECHEIO_DO_TEMA` não são papéis da escala, são o que o outro tema entregava. O piso de 1 é
    o mesmo e vale pela mesma razão -- dois vizinhos colados viram um controle só para o olho.
    """
    proporcional = pixel * base / tipografia.BASE_DE_REFERENCIA
    return max(1, round(proporcional * tipografia.FATOR_DE_FOLGA[densidade]))


def folha_de_estilo(
    *,
    cromo_escuro: bool = False,
    base: int = tipografia.BASE_DE_REFERENCIA,
    densidade: str = pele.CONFORTAVEL,
) -> str:
    """A folha de estilo inteira, como texto. **Pura: não toca `QApplication` nem widget.**

    É o que permite afirmar a paleta e o espaço das três peles e das duas densidades numa
    máquina sem tela -- a mesma razão de `ui/tokens.py` não importar `tkinter`, e o que faz o
    teste desta folha rodar na CI sem servidor gráfico.

    Levanta `KeyError` para densidade desconhecida, por `tipografia.folga`.
    """

    def cor(papel: str) -> str:
        return tokens.cor(papel, None, cromo_escuro=cromo_escuro)

    def do_tema(seletor: str) -> str:
        h, v = RECHEIO_DO_TEMA[seletor]
        return f"{_escalado(v, base=base, densidade=densidade)}px {_escalado(h, base=base, densidade=densidade)}px"

    def da_folha(seletor: str) -> str:
        h, v = folha.recheio(RECHEIO_DA_FOLHA[seletor], base=base, densidade=densidade)
        return f"{v}px {h}px"

    superficie = cor(tokens.SUPERFICIE_PADRAO)
    texto = cor(tokens.TEXTO_PADRAO)
    secundario = cor(tokens.TEXTO_SECUNDARIO)
    # **A moldura do cromo é derivada da superfície, e não o token de documento** (S-522). Até
    # aqui era `cor(tokens.MOLDURA)` -- o anel do tabuleiro, preso na paleta medida pela S-224 --,
    # e sobre o cromo escuro da pele "Foco" isso dava `#1f1d1b` sobre `#1f2124`: **1,04:1**, borda
    # invisível no botão comum e no `QGroupBox`. Ver `tokens.moldura_sobre`.
    moldura = tokens.moldura_sobre(superficie)
    dica = cor(tokens.SUPERFICIE_DICA)
    linha = tipografia.folga(tipografia.FOLGA_DE_LINHA, base=base, densidade=densidade)
    minima = tipografia.folga(tipografia.FOLGA_MINIMA, base=base, densidade=densidade)
    vao = folha.vao_do_indicador(base=base, densidade=densidade)

    regras = [
        # A superfície e a letra de base. Em Qt é preciso dizê-las: sem folha, o `QWidget` sai
        # com a cor do estilo da plataforma, e sob a pele "Foco" isso daria cromo claro com
        # rótulos pintados para fundo escuro -- meia dúzia de rótulos ilegíveis, que é
        # exatamente o defeito que a S-224 mediu no outro frontend.
        f"QWidget {{ background-color: {superficie}; color: {texto}; }}",
        # As superfícies de **documento** não são cromo e não seguem a pele: a folha do livro e
        # o tabuleiro ficam na paleta medida, e é `tokens.SUPERFICIES_DE_DOCUMENTO` que
        # garante isso. Aqui elas só não são sobrescritas -- quem as pinta é o `QPainter` de
        # `qt/visor.py` e de `qt/tabuleiro.py`, com `cor_atual`.
        f"QToolTip {{ background-color: {dica}; color: {tokens.sobre_superficie(dica)};"
        f" border: 1px solid {tokens.moldura_sobre(dica)}; padding: {linha}px; }}",
        # **O botão comum desabilitado desenhava igual ao habilitado, e a medição é esta** (S-506):
        # fotografei a barra do visualizador antes e durante a exportação e diferenciei as duas
        # imagens -- a fileira com "OCR todos diagramas", "Exportar PDF → PGN" e "Cancelar
        # exportação" saiu **pixel a pixel idêntica**, com três daqueles botões trocando de estado.
        #
        # A causa é a linha do `QWidget` acima: uma cor vinda de folha de estilo vale em todos os
        # estados e anula o acinzentamento que o Qt faria pela paleta. `PRIMARIO` e `DESTRUTIVO`
        # escapavam por terem `:disabled` próprio, logo abaixo; o comum não tinha nenhum -- e é o
        # comum que o par exportar/cancelar usa para dizer qual dos dois está vivo.
        #
        # **A S-520 alargou o item, e o `:disabled` de uma linha virou os quatro estados.** O
        # desabilitado era o único que a S-506 precisava para o par exportar/cancelar; o resto do
        # botão comum continuava sendo o estilo da plataforma -- `windowsvista` na máquina de quem
        # usa e `fusion` na CI --, dois desenhos para o mesmo botão e nenhum dos dois escolhido. É
        # também o que fazia a fotografia da CI não poder ser comparada com a da máquina.
        #
        # A face é a mistura do painel com o texto, e não um papel novo: um botão que se separa do
        # fundo por um degrau é o desenho que as três peles já sugerem, e um papel a mais seria a
        # décima superfície de `tokens.py` para dizer "quase o fundo".
        f"QPushButton {{ padding: {do_tema('QPushButton')};"
        f" background-color: {tokens.mistura(superficie, texto, RELEVO_DO_BOTAO)};"
        f" border: 1px solid {moldura}; border-radius: {minima}px; }}",
        f"QPushButton:hover {{ background-color: {tokens.mistura(superficie, texto, 2 * RELEVO_DO_BOTAO)}; }}",
        f"QPushButton:pressed, QPushButton:checked {{"
        f" background-color: {tokens.mistura(superficie, texto, 4 * RELEVO_DO_BOTAO)};"
        f" border: 1px solid {cor(tokens.TEXTO_SECUNDARIO)}; }}",
        f"QPushButton:disabled {{ background-color: {superficie}; color: {secundario};"
        f" border: 1px solid {moldura}; }}",
        # **O botão de ferramenta é desenhado inteiro pela folha, e pela mesma razão do comum**
        # (S-527): com só o recheio declarado, a face sob o ponteiro, a pressionada e a marcada
        # eram do estilo da plataforma -- e no `windows11` o marcado desenhava **zero** pixels
        # diferentes do desmarcado (medido pelo crítico: "Seguir OCR" ligado e desligado saíam
        # idênticos). A moldura transparente está sempre lá para que ligar a cor de um estado não
        # mova o conteúdo em um pixel; a face marcada é a do botão comum marcado, e a moldura dela
        # é a cor de ênfase -- um interruptor ligado tem de ser lido de longe, e cinza sobre cinza
        # não é lido.
        f"QToolButton {{ padding: {do_tema('QToolButton')}; border: 1px solid transparent;"
        f" border-radius: {minima}px; }}",
        f"{SELETOR_DO_NIVEL_ICONE} {{ padding: {do_tema(SELETOR_DO_NIVEL_ICONE)}; }}",
        f"QToolButton:hover {{ background-color: {tokens.mistura(superficie, texto, 2 * RELEVO_DO_BOTAO)}; }}",
        f"QToolButton:pressed {{ background-color: {tokens.mistura(superficie, texto, 4 * RELEVO_DO_BOTAO)}; }}",
        # O indicador de menu **na linha do texto**, e não no canto de baixo: é o chevron do
        # "Mais ▾", que o crítico da S-527 mediu solto ~8 px abaixo da base da letra. O botão com
        # menu instantâneo (`popupMode` 2) reserva o recheio à direita para ele.
        "QToolButton::menu-indicator { subcontrol-origin: padding; subcontrol-position: center right; }",
        f'QToolButton[popupMode="2"] {{ padding-right: {_escalado(16, base=base, densidade=densidade)}px; }}',
        # O item desabilitado do menu cinza, pela razão de sempre: a cor de `QWidget` acima vale
        # em todo estado e anulava o acinzentamento da paleta. É também o que pinta o **cabeçalho
        # de grupo** do menu "Mais" (um item desabilitado em negrito, `qt/barra_da_sala.py`).
        f"QMenu::item:disabled {{ color: {secundario}; }}",
        f"QLineEdit {{ padding: {do_tema('QLineEdit')}; }}",
        f"QComboBox {{ padding: {do_tema('QComboBox')}; }}",
    ]

    # A moldura que o estilo da plataforma não dá (S-522): ver `CONTROLES_COM_MOLDURA`. O raio
    # vai só nos três controles de uma linha, que é onde ele já está no botão comum; lista e
    # editor são retângulos de conteúdo, e um canto arredondado ali cortaria a primeira letra.
    regras += [f"{seletor} {{ border: 1px solid {moldura}; }}" for seletor in CONTROLES_COM_MOLDURA]
    regras += [
        f"QComboBox, QLineEdit, QSpinBox {{ border-radius: {minima}px; }}",
        # O separador da fila é um `QWidget` de 1 px pintado aqui, e não um `QFrame.VLine`: o
        # `VLine` desenha com a cor de **texto** da paleta, e não com a da folha -- medido, 2 px
        # em `#848688` na "Foco", mais claro que a borda das pílulas ao lado (S-522).
        f"QWidget#{ID_DO_SEPARADOR} {{ background-color: {moldura}; }}",
    ]

    # O recheio que sai de `ui/folha.py`, um seletor por classe. Um `try` por classe seria
    # teatro aqui: `folha.recheio` é pura e só levanta para classe fora da tabela, que é erro
    # deste módulo e não do ambiente -- e o `KeyError` dela é justamente o que o expõe.
    regras += [f"{seletor} {{ padding: {da_folha(seletor)}; }}" for seletor in RECHEIO_DA_FOLHA]

    # O vão entre o indicador e o rótulo (S-442). Em Qt ele é `spacing` e não
    # `indicatormargin`, e é a propriedade que o `QCheckBox` de fato lê.
    regras += [f"QCheckBox {{ spacing: {vao}px; }}", f"QRadioButton {{ spacing: {vao}px; }}"]

    # **E o indicador que essas duas linhas apagaram** (S-553, segunda rodada). Ver
    # `INDICADOR_DA_MARCA` para o defeito fotografado e para por que a marca não é um glifo.
    #
    # A ordem dentro do bloco é a que desfaz os empates de QSS: repouso, ponteiro, desabilitado e
    # foco têm um pseudo-estado cada, e o marcado também -- então o marcado vem depois deles, e os
    # pares (`:checked:disabled`, `:checked:focus`) vêm por último, ganhando por especificidade.
    # Um indicador marcado e focado tem de mostrar as duas coisas, e é a regra da S-553.
    lado = lado_do_indicador(base)
    enfase = cor(tokens.BOTAO_PRIMARIO)
    anel = anel_de_foco(cromo_escuro=cromo_escuro)
    for classe in INDICADOR_DA_MARCA:
        # O rádio é redondo, e o raio conta a moldura de 1 px de cada lado; a caixa usa o mesmo
        # canto do botão comum, que é o que faz as duas parecerem do mesmo desenho.
        raio = (lado + 2) // 2 if classe == "QRadioButton" else minima
        regras += [
            f"{classe}::indicator {{ width: {lado}px; height: {lado}px;"
            f" border: 1px solid {moldura}; border-radius: {raio}px;"
            f" background-color: {superficie}; }}",
            f"{classe}::indicator:hover {{ border: 1px solid {texto}; }}",
            f"{classe}::indicator:disabled {{ border: 1px solid {moldura};"
            f" background-color: {superficie}; }}",
            f"{classe}::indicator:focus {{ border: 1px solid {anel}; }}",
        ]
    marcado = {
        "QCheckBox": lambda tinta: f"background-color: {tinta}; border: 1px solid {tinta};",
        "QRadioButton": lambda tinta: (
            f"background-color: {ponto_do_radio(tinta, superficie)}; border: 1px solid {tinta};"
        ),
    }
    for classe, desenho in marcado.items():
        regras += [
            f"{classe}::indicator:checked {{ {desenho(enfase)} }}",
            f"{classe}::indicator:checked:hover"
            f" {{ {desenho(tokens.mistura(enfase, cor(tokens.TEXTO_SOBRE_ENFASE), tokens.REALCE_DE_ENFASE))} }}",
            f"{classe}::indicator:checked:disabled {{ {desenho(secundario)} }}",
            f"{classe}::indicator:checked:focus {{ border: 1px solid {anel}; }}",
        ]

    # A ênfase da S-444. **Também aqui o tema não dá de graça, e pela razão oposta à do Tk:**
    # lá o `ttkbootstrap` pintava os três papéis do mesmo `#f0f0f0` e a folha corrigia; aqui
    # não existe papel nenhum até esta linha. O `[papel="..."]` é o seletor de propriedade
    # dinâmica, que é o mecanismo do Qt para o que `style="primary.TButton"` faz lá.
    letra = cor(tokens.TEXTO_SOBRE_ENFASE)
    # Os dois papéis com face, **nomeados uma vez**: a guarda de `test_ui_estilos` conta por `ast`
    # quantas vezes um arquivo cita o papel primário, e o `QToolButton` abaixo lê daqui.
    faces = (
        (estilos.PRIMARIO, tokens.BOTAO_PRIMARIO),
        (estilos.DESTRUTIVO, tokens.BOTAO_DESTRUTIVO),
    )
    for papel, token in faces:
        face = cor(token)
        regras += [
            f'QPushButton[{PROPRIEDADE_DE_PAPEL}="{papel}"]'
            f" {{ background-color: {face}; color: {letra}; border: 1px solid {face}; }}",
            f'QPushButton[{PROPRIEDADE_DE_PAPEL}="{papel}"]:hover'
            f" {{ background-color: {tokens.mistura(face, letra, tokens.REALCE_DE_ENFASE)}; }}",
            f'QPushButton[{PROPRIEDADE_DE_PAPEL}="{papel}"]:pressed'
            f" {{ background-color: {tokens.mistura(face, letra, tokens.REALCE_DE_ENFASE * 2)}; }}",
            # O desabilitado é o do cromo, e não a face apagada. "Limpar os headers" **nasce
            # desabilitado**, e uma face vermelha sólida num botão que não responde é um pedido
            # de cuidado sobre uma ação que não existe -- é a medição da S-444, e ela vale aqui.
            f'QPushButton[{PROPRIEDADE_DE_PAPEL}="{papel}"]:disabled'
            f" {{ background-color: {superficie}; color: {secundario}; border: 1px solid {moldura}; }}",
        ]

    # **O papel chega ao `QToolButton` por outro desenho** (S-527). A barra da sala é de botões
    # chatos (`autoRaise`), como toda barra de ferramentas: a face só aparece sob o ponteiro. Ali o
    # primário ganha a face inteira, que é o que "Carregar OCR atual" já tinha como `QPushButton`;
    # o destrutivo ganha a **cor** -- letra e traço em `BOTAO_DESTRUTIVO` --, e não a face: dois
    # blocos vermelhos sólidos numa fila de botões chatos pediriam cuidado o tempo todo, e o
    # ChessBase não pinta "apagar variante" de vermelho por isso. O ícone acompanha porque quem o
    # desenha pede a cor ao mesmo token (`qt/barra_da_sala.py`).
    #
    # E o `:disabled` é obrigatório pela mesma razão do botão comum: a cor de `QWidget` vinda da
    # folha vale em todos os estados e anula o acinzentamento da paleta.
    (papel_primario, token_primario), (papel_destrutivo, token_destrutivo) = faces
    primario = cor(token_primario)
    ferramenta_primaria = f'QToolButton[{PROPRIEDADE_DE_PAPEL}="{papel_primario}"]'
    regras += [
        f"{ferramenta_primaria}"
        f" {{ background-color: {primario}; color: {letra}; border: 1px solid {primario};"
        f" border-radius: {minima}px; }}",
        f"{ferramenta_primaria}:hover"
        f" {{ background-color: {tokens.mistura(primario, letra, tokens.REALCE_DE_ENFASE)}; }}",
        f'QToolButton[{PROPRIEDADE_DE_PAPEL}="{papel_destrutivo}"] {{ color: {cor(token_destrutivo)}; }}',
        f"QToolButton:checked {{ background-color: {tokens.mistura(superficie, texto, 4 * RELEVO_DO_BOTAO)};"
        f" border: 1px solid {primario}; }}",
        f"QToolButton:disabled {{ color: {secundario}; }}",
        f"{ferramenta_primaria}:disabled"
        f" {{ background-color: {superficie}; color: {secundario}; border: 1px solid {moldura}; }}",
    ]

    # A faixa de abas discreta da pele "Foco" (S-226): a diferença é o **peso**, e a aba ativa se
    # separa por cor e por negrito. Em Qt isto é seletor de estado e não `style.map`, e por isso
    # cabe na folha em vez de precisar de um registro à parte.
    regras += [
        f"QTabBar::tab:selected {{ color: {texto}; font-weight: bold; }}",
        f"QTabBar::tab:!selected {{ color: {secundario}; }}",
        f"QGroupBox {{ margin-top: {linha}px; border: 1px solid {moldura};"
        f" border-radius: {minima}px; }}",
        f"QGroupBox::title {{ subcontrol-origin: margin; left: {linha}px; padding: 0 {minima}px; }}",
    ]

    # **O anel de foco de teclado, e ele vem por último de propósito** (S-553). Ver
    # `CONTROLES_COM_ANEL_DE_FOCO` para o defeito medido e para por que `outline` não serve.
    #
    # Último porque `QToolButton:focus` e `QToolButton:checked` têm a mesma especificidade -- um
    # tipo e um pseudo-estado --, e em QSS o empate é desfeito pela ordem. Um botão marcado **e**
    # focado tem de mostrar o foco: quem está com o teclado precisa saber onde ele está, e o
    # marcado continua dito pela face funda, que esta regra não toca.
    #
    # A moldura é a que já existe trocando de cor -- 1 px, o mesmo de sempre --, e por isso o anel
    # não desloca um pixel de conteúdo. O seletor com propriedade (`[papel="PRIMARIO"]`) ganha do
    # seletor de classe por especificidade, então a ordem entre os dois blocos abaixo não importa.
    regras += [
        f"{seletor}:focus {{ border: 1px solid {anel_de_foco(cromo_escuro=cromo_escuro)}; }}"
        for seletor in CONTROLES_COM_ANEL_DE_FOCO
    ]
    na_enfase = anel_de_foco(cromo_escuro=cromo_escuro, sobre_enfase=True)
    regras += [
        f'QPushButton[{PROPRIEDADE_DE_PAPEL}="{papel}"]:focus {{ border: 1px solid {na_enfase}; }}'
        for papel, _token in faces
    ]
    # O botão de ferramenta só tem face no primário -- o destrutivo ali é cor de letra, e não face
    # --, então o anel do destrutivo é o do cromo e cai na regra de classe acima.
    regras.append(f"{ferramenta_primaria}:focus {{ border: 1px solid {na_enfase}; }}")
    return "\n".join(regras)


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
    global _cromo_escuro
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

    try:
        alvo.setStyleSheet(folha_de_estilo(cromo_escuro=cromo_escuro, base=base, densidade=densidade))
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.warning("Folha de estilo não aplicada (%s): a janela abre no cinza do sistema.", exc)
        return "sem_folha"

    logger.info(
        "Tema da interface: folha própria, cromo %s, densidade %s (Qt).",
        "escuro" if cromo_escuro else "claro",
        densidade,
    )
    repintar()
    return "qss"
