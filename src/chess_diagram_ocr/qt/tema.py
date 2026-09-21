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
# e os testes já escritos não precisem saber que a fronteira se moveu.
folha_de_estilo = folha_de_estilo_pura.folha_de_estilo
RECHEIO_DO_TEMA = folha_de_estilo_pura.RECHEIO_DO_TEMA
RECHEIO_DA_FOLHA = folha_de_estilo_pura.RECHEIO_DA_FOLHA

__all__ = [
    "PROPRIEDADE_DE_PAPEL",
    "RECHEIO_DA_FOLHA",
    "RECHEIO_DO_TEMA",
    "altura_de_linha_atual",
    "altura_do_titulo_atual",
    "ao_repintar",
    "aplicar_paleta",
    "aplicar_papel",
    "aplicar_tema",
    "alto_contraste_em_vigor",
    "cromo_escuro_em_vigor",
    "cor_atual",
    "folha_de_estilo",
    "fonte_atual",
    "fonte_base",
    "fonte_pintada",
    "gravar_marcas",
    "pasta_das_marcas",
    "pintar",
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
