"""`rico.Atributos` virando formato do Qt -- e o que isso apaga do lado do Tk (S-249/S-504).

**A tradução é direta, e é a maior economia do porte inteiro.** `ui/texto_panel.py` gasta três
mecanismos para pintar um trecho, e os três existem por uma limitação do `tk.Text`: **uma
etiqueta só pode dar uma fonte ao trecho, e a última criada vence.** Daí

- `NEGRITO_ITALICO`, uma etiqueta só para o par -- "uma tag do Tk não sabe somar duas fontes";
- `_etiqueta_de_fonte`, que gera `fonte:titulo:bi:2` sob demanda, uma por combinação de estilo,
  peso, pendor e degrau de corpo;
- `_fontes_desenhadas`, o cache dessas etiquetas, refeito a cada troca de zoom.

`QTextCharFormat` tem `setFontWeight`, `setFontItalic`, `setFontUnderline`, `setFontStrikeOut`,
`setForeground`, `setBackground` e `setFontPointSize` como propriedades **independentes**. Os três
mecanismos somem, e com eles some o defeito que o docstring de `_pintar_estilos` registra: *"com a
fonte na etiqueta do estilo, o negrito de dentro dele sumiria"*.

**O que não muda são as decisões.** Que estilo de parágrafo tem que papel de fonte é
`PAPEL_DO_ESTILO`, que o degrau vira ponto só em `tipografia.corpo`, que a cor do autor sai de
`ui/texto_cores.py` e a faixa de confiança de `PAPEIS_DA_FAIXA` -- tudo isso é de lá, e este
módulo chama. **Nenhum tamanho em pixel entra aqui**, que é o critério de aceite da S-249:
`tipografia` escala pela fonte do sistema desde a S-147.

**Puro o bastante para ser testado sem janela**, e é por isso que ele é um módulo. `QTextCharFormat`
não precisa de janela nem de `QApplication` com tela: um teste afirma que negrito e itálico convivem
no mesmo trecho -- que é justamente o que não dava para afirmar do outro lado.
"""

from __future__ import annotations

import logging

from PyQt6.QtGui import QColor, QFont, QTextBlockFormat, QTextCharFormat

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.text import rico
from chess_diagram_ocr.ui import texto_cores, tipografia, tokens

logger = logging.getLogger(__name__)

__all__ = [
    "ALINHAMENTO_DO_QT",
    "PAPEL_DA_MARCA",
    "PAPEL_DO_ESTILO",
    "bloco_de",
    "formato_de",
    "recuo_de",
]

PAPEL_DO_ESTILO: dict[str, str] = {
    rico.ESTILO_TITULO: tipografia.TITULO,
    rico.ESTILO_PROSA: tipografia.CORPO,
    rico.ESTILO_NOTACAO: tipografia.DADO,
    rico.ESTILO_LEGENDA: tipografia.AUXILIAR,
}
"""Estilo de parágrafo -> papel de fonte de `ui/tipografia.py` (S-249).

**A mesma tabela de `ui/texto_panel.py`, e a igualdade é cobrada pelo teste.** Ela não foi movida
para um módulo comum porque é de *apresentação* e as duas janelas podem legitimamente divergir num
dia -- mas enquanto não divergirem por decisão, divergirem por descuido é o defeito.

`NOTACAO` cai em `DADO` porque `DADO` é a monoespaçada, e uma linha de lances alinhada é o que a
proporcional estraga."""

PAPEL_DA_MARCA = tokens.TEXTO_SECUNDARIO
"""A cor de `[Diagrama N]`: ela é do texto e não do documento, e não disputa com a prosa."""

ALINHAMENTO_DO_QT: dict[str, int] = {}
"""`alinhamento de `rico` -> flag do Qt`. Preenchido abaixo, depois do import de `Qt`."""


def _flags() -> dict[str, int]:
    from PyQt6.QtCore import Qt

    return {
        rico.ALINHAMENTO_ESQUERDA: int(Qt.AlignmentFlag.AlignLeft),
        rico.ALINHAMENTO_CENTRO: int(Qt.AlignmentFlag.AlignHCenter),
        rico.ALINHAMENTO_DIREITA: int(Qt.AlignmentFlag.AlignRight),
        rico.ALINHAMENTO_JUSTIFICADO: int(Qt.AlignmentFlag.AlignJustify),
    }


ALINHAMENTO_DO_QT.update(_flags())


def _fonte(atributos: rico.Atributos, *, base: tuple[int, str, str]) -> tuple[str, int]:
    """`(família, corpo em ponto)` deste trecho. **O degrau vira ponto só em `tipografia`.**

    Duas origens, como em `texto_panel._fonte_do_trecho`:

    - **com estilo de parágrafo**, a origem é o papel dele, resolvido contra a fonte do sistema;
    - **sem estilo**, a origem é o papel `CORPO`.

    A segunda diverge do Tk de propósito, e a razão de lá não existe aqui: o `tk.Text` nasce em
    `TkFixedFont` -- Courier New 10 no Windows --, e derivar do papel `CORPO` faria "aumentar o
    corpo" trocar a família e *diminuir* o tamanho. O `QTextEdit` nasce na fonte da aplicação, que
    já é a do sistema, então o papel e o widget concordam e não há de que se defender.

    Somar o degrau ao tamanho **já desenhado** daria um número que acumula a cada redesenho -- a
    fonte cresceria sozinha. A conta parte sempre da origem, nunca do que está na tela.
    """
    tamanho, proporcional, monoespacada = base
    papel = PAPEL_DO_ESTILO[atributos.estilo] if atributos.estilo else tipografia.CORPO
    familia = monoespacada if papel == tipografia.DADO else proporcional
    return familia, tipografia.corpo(atributos.corpo, base=tamanho, papel=papel)


def formato_de(
    corrida: rico.Corrida,
    *,
    base: tuple[int, str, str] | None = None,
    cromo_escuro: bool = False,
) -> QTextCharFormat:
    """O `QTextCharFormat` desta corrida: fonte, peso, pendor, traços e as duas cores.

    **Sete propriedades independentes, e nenhuma etiqueta combinada.** É o parágrafo do cabeçalho
    deste módulo posto em código: negrito, itálico e estilo de parágrafo convivem no mesmo trecho
    porque o Qt os guarda separados.

    `base` é `(tamanho, proporcional, monoespaçada)` -- o que `tema.fonte_base()` devolve. Ele é
    parâmetro para o teste poder fixar a fonte do sistema em vez de depender da máquina, que é a
    mesma razão de `tipografia.fonte` receber `base=`.
    """
    if base is None:
        base = tema.fonte_base()
    atributos = corrida.atributos
    formato = QTextCharFormat()

    familia, corpo = _fonte(atributos, base=base)
    formato.setFontFamilies([familia])
    formato.setFontPointSize(float(corpo))
    # `Bold`/`Normal` e não `setFontWeight(700)`: o enum é o que o Qt promete e o inteiro é o que
    # ele aceita hoje. O papel TITULO já vem em negrito por `tipografia.fonte`, e por isso o
    # `or` -- um título deixa de ser negrito só se alguém desmarcar, e aí o atributo manda.
    negrito = atributos.negrito or atributos.estilo == rico.ESTILO_TITULO
    formato.setFontWeight(QFont.Weight.Bold if negrito else QFont.Weight.Normal)
    formato.setFontItalic(atributos.italico)
    formato.setFontUnderline(atributos.sublinhado)
    formato.setFontStrikeOut(atributos.tachado)

    formato.setForeground(QColor(_cor_da_letra(corrida, cromo_escuro=cromo_escuro)))
    if atributos.realce:
        formato.setBackground(QColor(_papel(texto_cores.papel_de_realce(atributos.realce), cromo_escuro)))
    return formato


def _cor_da_letra(corrida: rico.Corrida, *, cromo_escuro: bool) -> str:
    """A cor do trecho, e **a ordem das três origens é a decisão**.

    1. A **cor do autor** ganha: ela foi escolhida à mão, e a S-242 diz que "limpar cor" é um
       comando próprio justamente porque ela é de outro canal.
    2. A **marca do diagrama** vem depois: `[Diagrama N]` é do texto e não da prosa.
    3. A **faixa de confiança** por último: ela é o que o motor achou, e é a que cede.

    Inverter 1 e 3 faria uma anotação humana em amarelo virar vermelho porque o motor duvidou
    daquele trecho -- e a pessoa concluiria que a cor dela não pegou.
    """
    if corrida.atributos.cor:
        return _papel(texto_cores.papel_de_cor(corrida.atributos.cor), cromo_escuro)
    if corrida.e_diagrama:
        return _papel(PAPEL_DA_MARCA, cromo_escuro)
    # `""` para a faixa tranquila é deliberado: "a cor normal do texto". Pintá-la de preto é o
    # que quebraria o tema escuro -- está escrito em `PAPEL_DA_FAIXA`.
    papel = texto_cores.PAPEL_DA_FAIXA.get(corrida.faixa, "")
    return _papel(papel or tokens.TEXTO_PADRAO, cromo_escuro)


def _papel(papel: str, cromo_escuro: bool) -> str:
    """Um papel resolvido contra a pele. Nunca levanta: cor errada não derruba o editor."""
    try:
        return tokens.cor(papel, None, cromo_escuro=cromo_escuro)
    except KeyError:  # pragma: no cover - papel escrito errado é erro de programa, não de dado
        logger.warning("Papel de cor desconhecido no editor de texto: %s", papel)
        return tokens.RESERVA[tokens.TEXTO_PADRAO]


def recuo_de(estilo: str, *, base: tuple[int, str, str] | None = None) -> int:
    """O recuo deste estilo em pixel, **derivado da fonte** e não cravado (S-249).

    Quatro espaços da fonte em uso: quem aumentou a fonte do Windows recebe um recuo maior, que é
    o que a S-147 impôs a toda medida desta interface. O Tk mede com `Font.measure("    ")`; aqui
    a conta parte do corpo, porque `QFontMetrics` exigiria uma `QApplication` e este módulo é
    afirmável sem uma.
    """
    if base is None:
        base = tema.fonte_base()
    # ~0,55 do corpo por espaço nas proporcionais que este programa usa; quatro espaços dão ~2,2
    # corpos. O número não precisa ser exato -- ele é recuo de parágrafo, e o que importa é que
    # acompanhe a fonte em vez de ser um `24` cravado.
    return max(1, round(base[0] * 2.2))


def bloco_de(atributos: rico.Atributos, *, base: tuple[int, str, str] | None = None) -> QTextBlockFormat:
    """O `QTextBlockFormat` de um parágrafo: alinhamento, recuo e espaço acima.

    **Estilo e alinhamento são do parágrafo**, e não do trecho -- é a fronteira que
    `rico.aplicar_no_paragrafo` mantém, e a razão está lá: "marcar meia frase marcaria meio
    parágrafo, e o desenho ficaria com dois corpos de fonte na mesma linha".

    Os três recuos são os de `texto_panel._pintar_estilos`: prosa recua a **primeira** linha (a
    diagramação que a S-199 mede na página), legenda recua o bloco inteiro, e título ganha espaço
    acima em vez de recuo.
    """
    from PyQt6.QtCore import Qt

    formato = QTextBlockFormat()
    if atributos.alinhamento:
        formato.setAlignment(Qt.AlignmentFlag(ALINHAMENTO_DO_QT[atributos.alinhamento]))
    recuo = recuo_de(atributos.estilo, base=base)
    if atributos.estilo == rico.ESTILO_PROSA:
        formato.setTextIndent(recuo)
    elif atributos.estilo == rico.ESTILO_LEGENDA:
        formato.setLeftMargin(recuo)
    elif atributos.estilo == rico.ESTILO_TITULO:
        formato.setTopMargin(recuo)
    return formato
