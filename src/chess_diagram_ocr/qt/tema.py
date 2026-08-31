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
    "PROPRIEDADE_DE_PAPEL",
    "RECHEIO_DO_TEMA",
    "altura_de_linha_atual",
    "ao_repintar",
    "aplicar_papel",
    "aplicar_tema",
    "cor_atual",
    "folha_de_estilo",
    "fonte_atual",
    "fonte_base",
    "pintar",
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

RECHEIO_DO_TEMA: dict[str, tuple[int, int]] = {
    "QPushButton": (10, 4),
    "QToolButton": (10, 4),
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
    moldura = cor(tokens.MOLDURA)
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
        f" border: 1px solid {moldura}; padding: {linha}px; }}",
        f"QPushButton {{ padding: {do_tema('QPushButton')}; }}",
        f"QToolButton {{ padding: {do_tema('QToolButton')}; }}",
        f"QLineEdit {{ padding: {do_tema('QLineEdit')}; }}",
        f"QComboBox {{ padding: {do_tema('QComboBox')}; }}",
    ]

    # O recheio que sai de `ui/folha.py`, um seletor por classe. Um `try` por classe seria
    # teatro aqui: `folha.recheio` é pura e só levanta para classe fora da tabela, que é erro
    # deste módulo e não do ambiente -- e o `KeyError` dela é justamente o que o expõe.
    regras += [f"{seletor} {{ padding: {da_folha(seletor)}; }}" for seletor in RECHEIO_DA_FOLHA]

    # O vão entre o indicador e o rótulo (S-442). Em Qt ele é `spacing` e não
    # `indicatormargin`, e é a propriedade que o `QCheckBox` de fato lê.
    regras += [f"QCheckBox {{ spacing: {vao}px; }}", f"QRadioButton {{ spacing: {vao}px; }}"]

    # A ênfase da S-444. **Também aqui o tema não dá de graça, e pela razão oposta à do Tk:**
    # lá o `ttkbootstrap` pintava os três papéis do mesmo `#f0f0f0` e a folha corrigia; aqui
    # não existe papel nenhum até esta linha. O `[papel="..."]` é o seletor de propriedade
    # dinâmica, que é o mecanismo do Qt para o que `style="primary.TButton"` faz lá.
    letra = cor(tokens.TEXTO_SOBRE_ENFASE)
    for papel, token in (
        (estilos.PRIMARIO, tokens.BOTAO_PRIMARIO),
        (estilos.DESTRUTIVO, tokens.BOTAO_DESTRUTIVO),
    ):
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
    return "\n".join(regras)


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
