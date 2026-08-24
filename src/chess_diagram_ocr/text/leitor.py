"""A página inteira lida como texto, e não só a faixa de legenda (S-211).

**Por que este módulo nasceu.** Da S-184 à S-199 o projeto montou tudo que é preciso para ler
texto de página -- binarização, box de caractere, linha, coluna, parágrafo, tabela, tarja -- e o
único cliente disso era `recognizer.GlyphRecognizer`, que lê **um recorte**: a faixa de legenda
que a `ocr_caption` manda. Ler o livro é outro pedido, e ele não estava servido por ninguém.

## O defeito que este módulo existe para não ter: a escala medida antes de excluir o diagrama

`GlyphRecognizer.read` faz, nesta ordem, `escala_de_texto(binaria)` e depois
`excluir_diagramas(...)`. Para uma faixa de legenda a ordem não importa, porque não há diagrama
dentro dela. Para a página inteira ela é o defeito: a escala é uma **mediana ponderada por massa
de tinta**, e as peças de um diagrama impresso têm 86 px de altura contra 23 de uma letra -- e
massa de tinta muito maior. A escala sai medindo o tabuleiro.

Medido em 2026-08-24, página 20 do `Reinfeld 1001` a 220 dpi:

    escala na página inteira            86      <- é a altura de uma peça
    escala com o diagrama mascarado     42
    altura real da letra (mediana)      23

E o efeito na leitura é total, não parcial: com escala 86 a peneira de área
(`MIN_AREA_GLIFO x escala²`) descarta **todas** as letras, e das 441 componentes da página
sobraram 3 caixas. A página lia uma linha.

`escala_fora_dos_diagramas` é a correção, e ela é uma função à parte em vez de uma mudança em
`read`: a assinatura de `read` já aceita `escala=`, exatamente para o caso de quem tem uma régua
melhor que a que ela mediria -- e mexer na ordem interna dela mexeria no caminho da legenda, que
está medido e não é o que este item pediu.

## O padrão é o classificador deste projeto, e a camada de texto é a exceção

**A primeira versão deste módulo tinha isto invertido.** Ela preferia a camada de texto do PDF
onde ela existisse -- 25 dos 42 livros de `PDF/` --, com o argumento de que a camada não é OCR: é
o que o editor escreveu, e vale 1,0 de confiança. O argumento vale para prosa. Para **notação de
xadrez** ele é falso, e o número diz de que tamanho.

### A camada de texto não codifica figurina

Medido em 2026-08-24 sobre 16 páginas de 4 livros que **têm** camada:

    fonte da leitura     figurinas Unicode (♔-♟)     notação ASCII (Nf3, Bxd4)
    camada de texto                            0                          212
    classificador                            360                           52

**Zero.** Não é "pouca precisão": onde o livro imprime `♘`, a camada devolve o codepoint cru da
fonte de xadrez, sem mapeamento nenhum -- no `AAGAARD`, `2.♘xd4 dxc2!` sai da camada como
`2.l0xd4 dxc2!`, e `33.♕a6!` sai como `33.fta6!`. O texto **parece** prosa e passa por qualquer
verificação de "tem texto?", e é justamente por isso que o defeito atravessou a primeira versão.

### E não há convenção comum entre livros

Nos mesmos 4 livros a camada usa três codificações diferentes: o `Dvoretsky` escreve o lance em
ASCII (`1.Kf2`), o `AAGAARD` numa fonte de xadrez sem mapeamento, e o `Kemeri` em ASCII outra vez.
Um consumidor da camada teria de saber de qual livro veio a página para saber o que a string
significa -- que é o oposto do que um formato de texto deveria custar.

Por isso `MOTOR_PADRAO` é `glifo`. `--motor camada` continua existindo para quem quiser a camada
de um livro específico, e `auto` é o glifo com a camada como **reserva**, só para o caso de os
pesos não carregarem -- e nesse caso quem cai avisa, em vez de trocar de motor em silêncio.

**Continua não havendo voto entre os dois**, e por isso a `PaginaLida` registra em cada bloco de
qual deles ele veio: a procedência é o que permite comparar depois sem remedir.

## O separador de colado paga na página, e a primeira medição não viu

**Esta seção existia dizendo o contrário, e a correção é o item.** Em 2026-08-24 eu medi o
separador da S-186 na página, achei ruído e o deixei desligado. O dono do projeto trouxe então uma
página de texto **itálico**, e ali a conclusão se inverte -- em itálico as letras encostam, e é
justamente onde o separador serve.

O que a primeira medição não viu, e por quê:

1. **a população.** Foram 12 páginas de prosa **em pé**. Itálico não estava lá, e é o caso;
2. **a régua.** Media CER e recall de número de lance. Nenhuma das duas enxerga `M♔king`, que é um
   par de letras colado lido como um símbolo de xadrez -- o erro custa dois caracteres num texto de
   mil, e apaga um nome próprio;
3. **a ordem.** Ela rodou **antes** das quatro correções de geometria. Com elas dentro, o que
   sobra para o separador é outro conjunto.

Remedido em 21 páginas de 7 livros, com as correções de geometria ligadas:

    referência                         páginas   nunca    auto      melhoram/pioram
    camada editorada (confiável)            11   0,1077   0,1071    3 / 0
    camada de OCR (suspeita)                10   0,2032   0,1953    6 / 3
    só as páginas com itálico                4   0,1227   0,1207    3 / 0

**Na referência confiável, `auto` não piora uma única página.** O ganho de CER é pequeno -- 0,0006
--, e a evidência forte não é ele: é o caso nomeado.

    nunca   Thus we s♔ that   ·   M♔king   ·   Mcoking
    auto    Thus we see that  ·   Mecking  ·   Mecking

O modo `sempre` continua fora, e agora com o motivo à vista: ele parte **figurina correta**
(`♘f4` vira `♘1f4`), e é exatamente isso que o árbitro do `auto` recusa. Custo do `auto`: 1,58 s
para 1,67 s por página.

## O separador na faixa de legenda continua desligado

A S-186 estava medida só em **faixa de legenda** (`docs/metrics/texto_colados.json`), onde perde.
A pergunta reabriu com um caso concreto de página: `40` saiu `co` e `44` saiu `M`. O argumento
para reabrir era estrutural e parecia forte -- o modelo **não tem nenhuma ligadura de dois
dígitos** (não existe `ligature_40`), então um par colado só poderia sair como uma classe de um
caractere ou como uma ligadura de **letras**, e cortar seria a única saída.

Medido em 12 páginas de 4 livros (`docs/metrics/texto_pagina.json`, bloco `colados`):

    modo      CER      vs nunca    número de lance de 2 dígitos
    nunca     0,2696    --         97 de 104   (93,3%)
    auto      0,2688    -0,0009    97 de 104   (93,3%)
    sempre    0,2826    +0,0129    97 de 104   (93,3%)

**Idêntico nos três modos.** E a razão é que a hipótese estava errada: os dígitos **não estão
colados**. Só 2,1% das caixas da p30 do `Kemeri` passam do piso de largura, e os números perdidos
não estão entre elas -- `10.` sai `1o.`, com o zero lido como `o` minúsculo, em **dois boxes bem
segmentados**. Os de dois dígitos que acertam (`12. Ta1`, `16. c4`, `22. Db3`) já vinham separados.
Não há o que cortar.

Fica registrado porque o erro de diagnóstico é o achado: `40`→`co` **parece** um corte perdido e é
duas confusões de um caractere. Quem for atrás dessa família de erro deve ir para o léxico da
S-209 ou para o treino, e não para a geometria.

## O modo bloco da S-188 entra desligado, e o número é o motivo

A S-188 prometia o maior ganho do plano -- 72,8% para 91,2% de acerto de caractere, medido no
projeto de origem sobre faixas de legenda -- e na página ela **não paga**. Medido em 2026-08-24
sobre 10 páginas de 2 livros, com a camada de texto da própria página como referência
(`docs/metrics/texto_pagina.json`):

    livro                       páginas    glifo    + bloco (S-188)    custo
    AAGAARD (camada de OCR)           6   0,1559             0,1468    1,0 s -> 40,7 s
    Dvoretsky (nativo digital)        4   0,1154             0,1414    0,5 s -> 33,6 s
    ---------------------------------------------------------------------------------
    média                            10   0,1397             0,1446      ~50x

No livro nativo digital ele **piora** 22,5%, e mesmo onde ajuda o ganho é de 0,009 de CER por 40
vezes o tempo. Ele fica, e fica exposto em `--bloco`: o ganho da medição de origem era sobre
**faixa de legenda**, que é texto curto e isolado, e ali ele pode continuar valendo. O que a
medição diz é que a página não é aquele caso -- e o padrão segue a medição.

## O que o número de CER inclui, e o que ele não prova

A referência é a camada de texto da mesma página, e ela **não é verdade de referência humana**: no
`AAGAARD` a camada é OCR de terceiro e traz os próprios erros (`6Jm gdd 1 7.gee 1` é literal do
arquivo). Isso põe um piso no CER que não é do glifo. A comparação entre as duas colunas continua
válida -- as duas são medidas contra a mesma referência --, mas **o valor absoluto de 0,14 não é o
erro do modelo**, e transformá-lo em "86% de acerto" seria inventar um número.
"""

from __future__ import annotations

import logging
import re as _re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from . import boxes as _boxes
from . import caixa_alta as _caixa_alta
from . import colados as _colados
from . import colunas as _colunas
from . import dicionario as _dicionario
from . import empilhados as _empilhados
from . import italico as _italico
from . import linhas as _linhas_mod
from . import marca_fina as _marca_fina
from . import negrito as _negrito
from . import notacao as _notacao
from . import numero as _numero
from . import paragrafos as _paragrafos
from .binarizacao import binarize
from .grade import Arranjo
from .pagina import (
    BlocoDeDiagrama,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaLida,
    Procedencia,
)

logger = logging.getLogger(__name__)

MotorDeTexto = Literal["auto", "camada", "glifo"]
MotorResolvido = Literal["camada", "glifo"]
"""O que `motor_escolhido` devolve: **nunca** `auto`.

Tipo próprio e não `MotorDeTexto` porque a resposta vira **procedência** de cada bloco, e
"auto" não é procedência de coisa nenhuma -- é uma pergunta, não uma origem."""
MOTORES: tuple[MotorDeTexto, ...] = ("auto", "camada", "glifo")

COLADOS_NA_PAGINA = _colados.AUTO
"""O separador de glifo colado (S-186) na **página**, que não é o padrão dele na faixa.

`colados.PADRAO` continua `nunca`, e tem de continuar: aquele número foi medido sobre 155 faixas
de legenda, e é o que descreve o que roda lá. Aqui a população é outra, e a medição também.

**Este item já tinha sido medido e recusado, e a recusa estava errada.** Ver "O separador de
colado paga na página, e a primeira medição não viu" no cabeçalho."""

MOTOR_PADRAO: MotorDeTexto = "glifo"
"""Quem lê por omissão: **o classificador treinado neste projeto**, e não a camada do PDF.

O porquê inteiro está em "A camada de texto não codifica figurina", no cabeçalho. Em uma linha:
a camada não erra *um pouco* na notação de xadrez, ela **não a representa** -- e para o que sobra
não há convenção comum entre livros."""

MIN_CARACTERES_DE_CAMADA = 40
"""Abaixo disto a camada de texto não conta como camada, e `auto` vai para o glifo.

**Não é zero, e o motivo está no acervo.** O `Reinfeld 1001` tem mediana de 3 caracteres por
página: cada página traz o número do exercício como texto de verdade e o resto como imagem
escaneada. Aceitar essa camada como "a página tem texto" faria o livro inteiro sair com uma linha
por página. 40 é uma linha curta de prosa -- menos que isso não é o corpo de uma página."""

FOLGA_DA_MASCARA = 8
"""Pixels a mais de cada lado ao mascarar o diagrama antes de medir a escala.

Serve só para a borda do tabuleiro não sobrar na máscara; **não** é a margem que tira o rótulo
das casas do texto -- essa é a `MARGEM_DIAGRAMA` da S-185, medida em alturas de caractere, e ela
não pode ser usada aqui porque é justamente a escala que ainda não se sabe."""


Retangulo = tuple[float, float, float, float]


def _retangulo(valores: Sequence[float]) -> Retangulo:
    """Quatro floats, com a **forma** que o resto do módulo declara.

    Existe porque `tuple(float(v) for v in r)` é `tuple[float, ...]` para o verificador de tipo, e
    um retângulo de três ou de cinco números atravessaria o módulo inteiro sem ninguém reclamar.
    """
    x0, y0, x1, y1 = valores
    return (float(x0), float(y0), float(x1), float(y1))


@dataclass(frozen=True)
class _Cru:
    """Uma linha lida, antes de virar parágrafo. Geometria em **pixels** da página.

    `coluna` vem de quem leu, e não de quem monta. **É a correção do defeito central deste
    módulo**: no caminho do glifo a coluna é achada nas caixas de **caractere**, antes de as linhas
    existirem, porque `quebrar_em_linhas` junta numa linha só as duas colunas que compartilham a
    mesma banda -- e daí em diante não há como desfazer. Ver `segmentar`.
    """

    texto: str
    caixa: _boxes.Caixa
    confianca: float
    procedencia: Procedencia
    coluna: int = 0
    negrito: bool | None = None
    """`None` é "não se sabe" -- ver `text/negrito.py`. Quem preenche é `ler_pagina`, que é quem
    tem o documento na mão; `linhas_do_glifo` e `linhas_da_camada` deixam em `None`."""


def _envolver(caixas: Sequence[Retangulo]) -> Retangulo:
    if not caixas:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(c[0] for c in caixas),
        min(c[1] for c in caixas),
        max(c[2] for c in caixas),
        max(c[3] for c in caixas),
    )


def escala_fora_dos_diagramas(
    binaria: np.ndarray,
    diagramas: Sequence[Retangulo] = (),
    *,
    folga: int = FOLGA_DA_MASCARA,
) -> int:
    """A altura de caractere da página, medida **sem** o que está dentro de um diagrama.

    Ver "O defeito que este módulo existe para não ter", no cabeçalho. Os retângulos vêm em pixels
    da mesma imagem. Sem diagrama nenhum é `escala_de_texto` e não copia a imagem.
    """
    if binaria.size == 0:
        return 0
    if not diagramas:
        return _boxes.escala_de_texto(binaria)

    altura, largura = binaria.shape[:2]
    mascarada = binaria.copy()
    for x0, y0, x1, y1 in diagramas:
        ex0 = max(0, int(x0) - folga)
        ey0 = max(0, int(y0) - folga)
        ex1 = min(largura, int(x1) + folga)
        ey1 = min(altura, int(y1) + folga)
        if ex1 > ex0 and ey1 > ey0:
            mascarada[ey0:ey1, ex0:ex1] = 0

    escala = _boxes.escala_de_texto(mascarada)
    if escala > 0:
        return escala
    # A página é **só** diagrama: mascarar apagou toda a tinta. Devolver 0 faria a peneira de área
    # aceitar tudo; medir na imagem inteira dá a régua do tabuleiro, que é a única que existe ali.
    return _boxes.escala_de_texto(binaria)


def _caixa_de(retangulo: Sequence[float]) -> _boxes.Caixa:
    x0, y0, x1, y1 = retangulo
    return _boxes.Caixa(int(x0), int(y0), int(x1), int(y1))


def linhas_da_camada(page: object, *, escala_px: float) -> list[_Cru]:
    """As linhas da camada de texto do PDF, em pixels da página renderizada.

    `escala_px` é `dpi / 72`: a camada mora em pontos e a geometria deste módulo é em pixels, e
    converter aqui em vez de mais tarde é o que impede as duas de se misturarem.

    Confiança 1,0 e procedência `camada` para todas, e não é otimismo: a camada de texto **não é
    uma leitura**, é o que o gerador do PDF escreveu. Ver `pdf_text.TextLine.confidence`.
    """
    from ..pdf_text import page_text_lines

    cruas: list[_Cru] = []
    for linha in page_text_lines(page):  # type: ignore[arg-type]
        texto = linha.text.strip()
        if not texto:
            continue
        x0, y0, x1, y1 = linha.bbox
        cruas.append(
            _Cru(
                texto=texto,
                caixa=_caixa_de((x0 * escala_px, y0 * escala_px, x1 * escala_px, y1 * escala_px)),
                confianca=float(linha.confidence),
                procedencia="camada",
            )
        )
    return cruas


def leitor_de_linha_padrao() -> object | None:
    """O segundo opinante da S-188, ou `None` quando o extra não está instalado.

    RapidOCR e não outro pelo motivo que a S-42 já mediu: é o único que não baixa nada na primeira
    execução -- os modelos vêm no wheel. `None` é caminho normal e não erro: sem ele o leitor cai
    para a leitura por caractere, que é a que sempre existiu.
    """
    from ..ocr import build_recognizer
    from ..settings import OcrSettings

    try:
        return build_recognizer(OcrSettings(enabled=True, engine="rapidocr"))
    except Exception as exc:  # pragma: no cover - extra ausente
        logger.debug("Sem leitor de linha para o modo bloco da S-188: %s", exc)
        return None


def _colapsar_espaco(texto: str) -> str:
    """Espaços repetidos viram um. Existe porque o modo bloco os produz aos pares.

    `texto_da_linha` põe um espaço onde o vão entre boxes é largo, e a leitura de bloco **já
    trouxe** o espaço dentro do pedaço casado àquele box -- então `e5, but` sai `e5,  but`. Colapsar
    aqui, e não em `texto_da_linha`: aquela função está medida no caminho da legenda, e um espaço a
    menos ali mudaria um CER publicado.
    """
    return " ".join(texto.split())


def segmentar(
    imagem_rgb: np.ndarray,
    diagramas: Sequence[Retangulo] = (),
    *,
    escala: int | None = None,
    empilhados: bool = True,
) -> tuple[np.ndarray, np.ndarray, int, list[_boxes.Caixa], list[tuple[int, int]]]:
    """`(cinza, binaria, escala, caixas de caractere, faixas de coluna)` -- a página antes da linha.

    **A ordem destas quatro coisas é o item, e ela estava invertida.** A primeira versão deste
    módulo mandava a página inteira para `GlyphRecognizer.read`, que é um leitor de **faixa**: ele
    quebra em linhas sobre a imagem toda, e numa página de duas colunas as duas linhas que
    compartilham a banda viram **uma** linha. Medido em 2026-08-24 na página 58 do `AAGAARD`:

        `This is a big mistake. The rook is needed to after 44...Qxd1 45.c8=Q Kf6! ...`
                    coluna da esquerda            coluna da direita

    Depois disso não há como desfazer -- a linha já está costurada --, e a coluna detectada a
    partir dessas caixas é **uma**. O CER contra a camada de texto foi de 0,7861 com o texto
    intercalado contra 0,0475 na página de coluna única do mesmo livro: o erro era todo de ordem,
    e nenhum dele era de reconhecimento.

    Por isso a coluna é achada aqui, nas caixas de **caractere**, que é a população para que
    `colunas.calha` foi medida -- e por isso ela é chamada sem `calha_minima`: o piso de largura
    mediana de caractere é o certo quando as caixas são caracteres. Ver `calha_de_linhas`, que é o
    remendo do caminho da camada, onde só existem linhas.
    """
    import cv2

    cinza = cv2.cvtColor(imagem_rgb, cv2.COLOR_RGB2GRAY) if imagem_rgb.ndim == 3 else imagem_rgb
    cinza = np.ascontiguousarray(cinza)
    binaria = binarize(cinza)
    if escala is None:
        escala = escala_fora_dos_diagramas(binaria, diagramas)
    if escala <= 0:
        return (cinza, binaria, 0, [], [])

    caixas = _boxes.unir_pingos(_boxes.caixas_de_caractere(binaria, escala=escala), escala=escala)
    if empilhados:
        # **`:`, `;` e `=` são dois contornos**, e sem isto o classificador nunca vê nenhum dos
        # três inteiro -- ele responde `.` duas vezes, corretamente. Ver `text/empilhados.py`.
        caixas = _empilhados.unir(
            caixas, escala=escala, extras=_empilhados.barras(binaria, escala=escala)
        )
        caixas = _linhas_mod.ordem_em_faixa(caixas)
    if diagramas:
        caixas = _boxes.excluir_diagramas(
            caixas, [_retangulo(r) for r in diagramas], escala=escala
        )
    faixas = _colunas.detectar_colunas(caixas) if caixas else []
    return (cinza, binaria, escala, caixas, faixas)


def _arbitro_de_confianca(
    cinza: np.ndarray, classificador: object
) -> Callable[[Sequence[_boxes.Caixa]], float]:
    """Caixas -> confiança média delas. **O mesmo árbitro que o `cvoff-texto-colados` mede.**

    Escrito igual ao de lá de propósito: se o separador for medido com um árbitro e rodar com
    outro, a tabela que decidiu ligá-lo deixa de descrever o que está ligado.
    """

    def julgar(caixas: Sequence[_boxes.Caixa]) -> float:
        recortes = [c.recortar(cinza) for c in caixas]
        recortes = [r for r in recortes if r.size]
        if not recortes:
            return 0.0
        lidos = classificador.classificar(recortes)  # type: ignore[attr-defined]
        return float(sum(c for _, c in lidos) / len(lidos)) if lidos else 0.0

    return julgar


def linhas_do_glifo(
    imagem_rgb: np.ndarray,
    diagramas: Sequence[Retangulo] = (),
    *,
    reconhecedor: object | None = None,
    escala: int | None = None,
    modo_bloco: bool = False,
    colados: str = COLADOS_NA_PAGINA,
    caixa_alta: bool = True,
    marca_fina: bool = True,
    empilhados: bool = True,
    italico: bool = True,
    dicionario: bool = False,
    numeros: bool = True,
    juntar_lance: bool = True,
) -> tuple[list[_Cru], list[tuple[int, int]]]:
    """As linhas lidas pelo classificador de glifo, **coluna a coluna**, e as faixas achadas.

    `escala=None` a mede com `escala_fora_dos_diagramas`. `modo_bloco=True` liga a S-188 -- ler a
    linha, e não o caractere. **Desligado por padrão, e o número que decidiu isso está no cabeçalho
    deste módulo**: na página inteira ele custa ~50x o tempo e piora o livro nativo digital.

    `colados` liga o separador de glifo colado (S-186). Entra em `auto` na página -- e não em
    `nunca`, que é o padrão dele na faixa de legenda. Ver `COLADOS_NA_PAGINA`.

    `caixa_alta` decide maiúscula/minúscula das oito letras de mesma forma pela **altura** do box:
    CER 0,1434 -> 0,1114 em 11 páginas, 11 melhoram e nenhuma piora. Ver `text/caixa_alta.py`.

    `marca_fina` promove a apóstrofo a vírgula que está no alto da linha (`Black,s` -> `Black's`).
    Também entra ligada, mas **pelo motivo certo**: o ganho de CER dela é da ordem do ruído, e o
    que ela paga é legibilidade. Ver o cabeçalho de `text/marca_fina.py`, que explica por que o
    teto é baixo -- o modelo não tem as aspas curvas.

    `empilhados` funde o glifo de dois contornos -- `:`, `;` e `=`. Sem ela os três têm recall
    **zero**: nunca chegam inteiros ao classificador, que responde `.` duas vezes, corretamente.
    CER 0,1115 -> 0,1078. Ver `text/empilhados.py`.

    `italico` troca `/` por `l` em linha inclinada: em itálico o `l` é um traço pendido, que é o
    desenho do `/`. Ligada, e o **controle importa mais que o ganho** -- `1/2-1/2` é resultado de
    partida, e o `/` legítimo é preservado porque a linha dele não é itálica. Ver
    `text/italico.py`.

    `juntar_lance` junta o número de lance que a segmentação partiu (`1 5` -> `15`), e **só
    dentro de fatia de notação** -- `In 1968` fica. Aplica-se apenas ao caminho do **glifo**: a
    camada é a referência das medições deste subpacote, e normalizá-la mexeria na régua.

    `numeros` troca por `0` o oval que está dentro de um número (`2o` -> `20`) e conserta o roque
    (`O.O` -> `0-0`). Ligada: o sintoma cai de 29 para 2 em 22 páginas, e nenhuma piora. Ver
    `text/numero.py`, que também registra o que **não** dá para consertar assim.

    `marcar_negrito` anota o peso da fonte em cada linha, **da camada de texto e nunca da
    imagem**: 13 dos 41 livros o registram, e nos outros o campo fica `None` -- "não se sabe", que
    não é `False`. Ver `text/negrito.py`, que traz o número da via recusada.

    `dicionario` deixa o léxico desempatar entre os candidatos do modelo. **Desligado, e o número
    é zero**: medido em 6 páginas, ele não corrige nada -- as correções de geometria acima já
    levaram o que era alcançável, e o léxico do acervo tem pouco inglês. Ver
    `docs/metrics/texto_dicionario.json`.

    Devolve as faixas junto porque quem monta não pode redescobri-las: as caixas de caractere já
    foram consumidas aqui, e detectá-las de novo a partir das linhas é o defeito que `segmentar`
    documenta.
    """
    from .duas_linhas import descartar_fragmentos
    from .linhas import envolve, ordem_em_faixa, quebrar_em_linhas, texto_da_linha

    cinza, binaria, escala, caixas, faixas = segmentar(
        imagem_rgb, diagramas, escala=escala, empilhados=empilhados
    )
    if not caixas:
        return ([], faixas)

    if reconhecedor is None:
        from .recognizer import build_glyph_recognizer

        reconhecedor = build_glyph_recognizer(
            leitor_de_linha=leitor_de_linha_padrao() if modo_bloco else None
        )
    classificador = reconhecedor.classifier  # type: ignore[attr-defined]
    leitor_de_linha = getattr(reconhecedor, "_leitor_de_linha", None)
    lexico = _dicionario.carregar() if dicionario else frozenset()

    # **O separador de colado entra aqui, e entra desligado** (S-186). Ele parte um contorno que
    # tem dois glifos, e o arbitro -- o proprio classificador -- confirma o corte comparando a
    # confianca media dos dois pedacos com a do inteiro. Sem arbitro nao corta: custou 2,3 pontos
    # de F1 no projeto de origem, e a regra e a mesma da S-197 e da S-198.
    if colados != _colados.NUNCA and caixas:
        caixas = _colados.separar(
            binaria,
            caixas,
            escala=escala,
            arbitro=_arbitro_de_confianca(cinza, classificador),
            modo=colados,
        )

    cruas: list[_Cru] = []
    for indice, _faixa in enumerate(faixas or [(0, 0)]):
        desta = (
            [c for c in caixas if max(0, _colunas.atribuir_coluna(c, faixas)) == indice]
            if len(faixas) > 1
            else list(caixas)
        )
        if not desta:
            continue
        grupos = descartar_fragmentos(quebrar_em_linhas(ordem_em_faixa(desta)), escala=escala)
        for grupo in grupos:
            recortes = [c.recortar(cinza) for c in grupo]
            if caixa_alta or marca_fina or empilhados or italico or numeros or lexico:
                # **Duas correções de geometria, e a mesma razão para as duas**: o recorte que o
                # classificador recebe é o bbox apertado, então o que distingue dois glifos pelo
                # *tamanho* (`s`/`S`) ou pela *posição na linha* (`'`/`,`) é apagado antes de ele
                # ver a imagem. Uma olha altura, a outra olha onde a marca assenta.
                probs = classificador.probabilidades(recortes)
                i2c = classificador.meta.idx_to_char
                lidos = (
                    _caixa_alta.decidir(probs, [c.altura for c in grupo], i2c)
                    if caixa_alta
                    else [(i2c[int(probs[k].argmax())], float(probs[k].max())) for k in range(len(grupo))]
                )
                if marca_fina:
                    lidos = _marca_fina.corrigir(lidos, probs, grupo, i2c)
                if empilhados:
                    # O resize apaga a proporção junto com o tamanho: fundido, o `=` sai `:`.
                    lidos = _empilhados.corrigir(lidos, probs, grupo, i2c)
                if italico:
                    # Em linha inclinada o `l` é um traço pendido, que é o desenho do `/`.
                    lidos = _italico.corrigir(lidos, probs, grupo, i2c, binaria)
                if numeros:
                    # O oval dentro de um número é zero, e nenhuma palavra é dígito seguido de `o`.
                    lidos = _numero.corrigir(lidos, probs, grupo, i2c)
                if lexico:
                    # **Por último, e é a ordem certa**: as correções de geometria acima mudam a
                    # palavra que o dicionário vai julgar, e julgá-la antes delas seria julgar um
                    # texto que não é o que sai.
                    lidos = _dicionario.corrigir(lidos, probs, grupo, i2c, lexico)
            else:
                lidos = classificador.classificar(recortes)
            if not lidos:
                continue
            if leitor_de_linha is not None:
                from .leitura_de_linha import em_bloco

                casados = em_bloco(cinza, grupo, lidos, leitor_de_linha)
                lidos = [(item.caractere, item.confianca) for item in casados]
            texto = _colapsar_espaco(texto_da_linha(grupo, [char for char, _ in lidos]))
            if juntar_lance:
                # **Só a notação separa `1 5` de `In 1968`**, e a geometria não: os dois vãos têm
                # o mesmo tamanho. Ver `text/notacao.py`, que traz a medição.
                texto = _notacao.juntar_numero_de_lance(texto)
            if not texto:
                continue
            cruas.append(
                _Cru(
                    texto=texto,
                    caixa=_caixa_de(envolve(grupo)),
                    confianca=min(conf for _, conf in lidos),
                    procedencia="glifo",
                    coluna=indice,
                )
            )
    return (sem_rotulos_de_eixo(cruas), faixas)


def _para_pontos(caixa: _boxes.Caixa, escala_px: float) -> Retangulo:
    """Pixels da página renderizada -> pontos do PDF.

    **A `PaginaLida` sai em pontos, e não em pixels do DPI com que se leu.** É a lição da S-41: a
    anotação precisa sobreviver a uma troca de DPI, e um bbox em pixels de 220 lido como de 300
    aponta para outro lugar da folha sem nada estourar.
    """
    fator = escala_px or 1.0
    return (caixa.x1 / fator, caixa.y1 / fator, caixa.x2 / fator, caixa.y2 / fator)


EIXO_SOLTO = _re.compile(r"^[a-h1-8]$")
"""Uma linha que é só um rótulo de eixo. A mesma régua da `pdf_text._AXIS_LABEL`."""

MIN_EIXOS_NA_FILA = 6
"""Quantos rótulos distintos numa linha só a fazem ser a borda de um tabuleiro.

Seis, e não oito, e o número é o mesmo `_MIN_AXIS_LABELS` da S-217 pela mesma razão: o scan perde
rótulo de canto, e exigir os oito faria a régua falhar justamente nas páginas piores."""


def e_fila_de_eixo(texto: str) -> bool:
    """A linha é a fila `a b c d e f g h` (ou a coluna de filas) de um tabuleiro?

    **A régua é estrutural, e não o texto literal, e isso foi medido.** A primeira versão casava
    `^a b c d e f g h$` e funcionou -- até o modo bloco da S-188 entrar: o segundo opinante lê a
    fila como `a b d f a C e h`, porque rótulo isolado é o pior caso para um leitor de linha, e a
    régua literal deixou de casar. A borda voltou ao texto da página em todo diagrama.

    O que ela é de fato é o mesmo da `pdf_text._axis_label_strip`: rótulos **de um caractere só**,
    do alfabeto do tabuleiro, e **distintos**. É por serem distintos que a coluna de resultados de
    uma tabela de torneio (`1 1 0 1`) não cai aqui -- ver a docstring de lá, que mediu o caso.
    """
    partes = texto.split()
    if len(partes) < MIN_EIXOS_NA_FILA:
        return False
    marcas = [p.lower() for p in partes]
    if any(not EIXO_SOLTO.match(m) for m in marcas):
        return False
    return len(set(marcas)) >= MIN_EIXOS_NA_FILA


def sem_rotulos_de_eixo(cruas: Sequence[_Cru]) -> list[_Cru]:
    """Tira as bordas de diagrama que sobraram como texto, pela régua medida na S-217.

    `excluir_diagramas` já tira o que está **dentro** do retângulo do tabuleiro, com margem; os
    rótulos moram fora dele, e alargar a margem até alcançá-los comeria a legenda, que fica à
    mesma distância. Quem os separa de texto de verdade não é a distância: é serem **alinhados** e
    **distintos** -- as oito filas, cada uma uma vez. A coluna de resultados de uma tabela de
    torneio também é alinhada, mas é `1`, `1`, `0`, `1`, e sobrevive à conta. Ver
    `pdf_text._axis_label_strip`, que é a função que decide, reusada aqui em vez de reescrita.
    """
    from ..pdf_text import _MIN_AXIS_LABELS, _axis_label_strip

    fora: set[int] = {i for i, c in enumerate(cruas) if e_fila_de_eixo(c.texto)}
    soltos = [i for i, c in enumerate(cruas) if EIXO_SOLTO.match(c.texto.strip())]
    if len(soltos) >= _MIN_AXIS_LABELS:
        itens = [
            (cruas[i].texto.strip(), (float(cruas[i].caixa.x1), float(cruas[i].caixa.y1),
                                      float(cruas[i].caixa.x2), float(cruas[i].caixa.y2)))
            for i in soltos
        ]
        fora |= {soltos[k] for k in _axis_label_strip(itens)}
    return [c for i, c in enumerate(cruas) if i not in fora]


def calha_de_linhas(caixas: Sequence[_boxes.Caixa]) -> int:
    """O piso de largura de calha para quem projeta **linhas**, e não caracteres.

    **O piso de `colunas.calha` sai da largura mediana de caractere, e alimentá-lo com caixas de
    linha o multiplica por vinte.** Medido em 2026-08-24 na página 60 do `AAGAARD`, duas colunas
    a 220 dpi:

        largura mediana da caixa de linha    552 px  ->  piso 441 px
        calha de verdade                      34 px
        largura mediana de caractere real     ~14 px  ->  piso  ~11 px

    Com o piso em 441 a calha nunca é achada e a página sai com as duas colunas intercaladas linha
    a linha -- que foi exatamente o que a primeira versão deste módulo produziu.

    O termo de caractere **sai da conta** em vez de ser estimado: uma largura de caractere
    adivinhada a partir da altura da linha erra por fonte, e o que sobra (1% da largura do texto,
    e o piso absoluto) já é a régua que a S-190 mediu para o caso do `Nunn`. Quem impede que um vão
    de sumário passe por calha continua sendo `COLUNA_MINIMA`, que funde a faixa estreita demais
    para ser coluna -- e ele não depende deste piso.
    """
    if not caixas:
        return _colunas.CALHA_MINIMA_ABSOLUTA
    largura = max(c.x2 for c in caixas) - min(c.x1 for c in caixas)
    return max(int(largura * _colunas.CALHA_DA_PAGINA), _colunas.CALHA_MINIMA_ABSOLUTA)


def montar(
    cruas: Sequence[_Cru],
    diagramas: Sequence[Retangulo] = (),
    *,
    escala_px: float = 1.0,
    arranjo: Arranjo = "prosa",
    confiancas: Sequence[float] = (),
    placements: Sequence[str] = (),
    faixas: Sequence[tuple[int, int]] | None = None,
) -> tuple[Coluna, ...]:
    """Linhas e diagramas -> colunas de blocos, na ordem em que a página se lê.

    Os retângulos de diagrama vêm em **pixels**, como as linhas: a ordem de leitura e a atribuição
    de coluna são geometria, e geometria com duas unidades na mesma conta é o defeito que
    `_para_pontos` documenta.
    """
    from .pagina import Diagrama, sequencia_de_leitura

    if not cruas and not diagramas:
        return ()

    por_id = {id(c.caixa): c for c in cruas}
    caixas = [c.caixa for c in cruas]
    objetos = [Diagrama(bbox=_retangulo(r), indice=i) for i, r in enumerate(diagramas)]

    # **Quem leu manda na coluna.** O caminho do glifo já a achou nas caixas de caractere, que é a
    # população certa (ver `segmentar`); redescobri-la aqui, a partir das linhas, é o defeito que
    # produziu texto intercalado. `faixas=None` é o caminho da camada, onde só existem linhas -- e
    # aí o piso da calha é o de `calha_de_linhas`.
    if faixas is None:
        faixas = _colunas.detectar_colunas(caixas, calha_minima=calha_de_linhas(caixas)) if caixas else []
        de_linha = {id(c.caixa): max(0, _colunas.atribuir_coluna(c.caixa, faixas)) for c in cruas}
    else:
        faixas = list(faixas)
        de_linha = {id(c.caixa): c.coluna for c in cruas}
    ordem = sequencia_de_leitura(caixas, objetos, colunas=faixas or None, arranjo=arranjo)

    # **As métricas de recuo são da página inteira, e por coluna.** Ver o cabeçalho de
    # `paragrafos`: a mediana de cinco linhas entre dois diagramas não diz onde fica a margem.
    de_paragrafo: dict[int, _paragrafos.Linha] = {}
    todas: list[_paragrafos.Linha] = []
    for c in cruas:
        linha = _paragrafos.Linha(
            topo=c.caixa.y1,
            esquerda=c.caixa.x1,
            altura=c.caixa.altura,
            texto=c.texto,
            coluna=de_linha.get(id(c.caixa), 0),
        )
        de_paragrafo[id(c.caixa)] = linha
        todas.append(linha)
    metricas = _paragrafos.metricas_por_coluna(todas) if todas else {}

    # Uma tira por coluna, preservando a ordem de leitura dentro dela. O diagrama fecha a tira
    # corrente: é o que o põe **entre** os parágrafos, e não no fim da coluna (S-193).
    tiras: dict[int, list[list[_Cru] | Diagrama]] = {}
    corrente: dict[int, list[_Cru]] = {}

    def coluna_de(caixa: _boxes.Caixa) -> int:
        """A coluna de uma caixa: a que a linha já trouxe, ou a geometria para o diagrama."""
        conhecida = de_linha.get(id(caixa))
        if conhecida is not None:
            return conhecida
        return max(0, _colunas.atribuir_coluna(caixa, faixas)) if len(faixas) > 1 else 0

    def fechar(indice: int) -> None:
        acumulado = corrente.pop(indice, None)
        if acumulado:
            tiras.setdefault(indice, []).append(acumulado)

    for elemento in ordem:
        if isinstance(elemento, Diagrama):
            indice = coluna_de(elemento.caixa)
            fechar(indice)
            tiras.setdefault(indice, []).append(elemento)
            continue
        cru = por_id.get(id(elemento))
        if cru is None:
            continue
        indice = coluna_de(elemento)
        corrente.setdefault(indice, []).append(cru)
    for indice in list(corrente):
        fechar(indice)

    saida: list[Coluna] = []
    for indice in sorted(tiras):
        blocos: list[BlocoDeTexto | BlocoDeDiagrama] = []
        for tira in tiras[indice]:
            if isinstance(tira, Diagrama):
                blocos.append(
                    BlocoDeDiagrama(
                        indice=tira.indice,
                        bbox=_para_pontos(_caixa_de(tira.bbox), escala_px),
                        confianca=float(confiancas[tira.indice]) if tira.indice < len(confiancas) else 1.0,
                        placement=str(placements[tira.indice]) if tira.indice < len(placements) else "",
                    )
                )
                continue
            blocos.extend(_blocos_de_texto(tira, de_paragrafo, metricas, escala_px))
        if blocos:
            saida.append(
                Coluna(
                    indice=indice,
                    blocos=tuple(blocos),
                    bbox=_envolver([b.bbox for b in blocos]),
                )
            )
    return tuple(saida)


def _blocos_de_texto(
    tira: Sequence[_Cru],
    de_paragrafo: dict[int, _paragrafos.Linha],
    metricas: dict[int, tuple[int, int]],
    escala_px: float,
) -> list[BlocoDeTexto]:
    """Uma tira de linhas contíguas -> parágrafos, com a régua de recuo da página."""
    linhas = [de_paragrafo[id(c.caixa)] for c in tira if id(c.caixa) in de_paragrafo]
    if not linhas:
        return []
    volta = {id(de_paragrafo[id(c.caixa)]): c for c in tira if id(c.caixa) in de_paragrafo}

    blocos: list[BlocoDeTexto] = []
    for paragrafo in _paragrafos.cortar(linhas, metricas or None):
        lidas: list[LinhaLida] = []
        for linha in paragrafo.linhas:
            cru = volta.get(id(linha))
            if cru is None:
                continue
            lidas.append(
                LinhaLida(
                    texto=cru.texto,
                    bbox=_para_pontos(cru.caixa, escala_px),
                    confianca=cru.confianca,
                    procedencia=cru.procedencia,
                    negrito=cru.negrito,
                )
            )
        if not lidas:
            continue
        margem = metricas.get(paragrafo.coluna, (0, 1))
        primeira = paragrafo.linhas[0]
        recuado = primeira.esquerda > margem[0] + margem[1] * _paragrafos.RECUO_DE_PARAGRAFO
        blocos.append(BlocoDeTexto.de_linhas(lidas, recuado=recuado))
    return blocos


def motor_escolhido(motor: MotorDeTexto = MOTOR_PADRAO, *, tem_modelo: bool = True) -> MotorResolvido:
    """Qual dos dois vai ler. `auto` é o glifo, com a camada como **reserva**; ver o cabeçalho.

    Devolve `camada` ou `glifo`, nunca `auto` -- quem chama registra a resposta na `PaginaLida`, e
    "auto" não é uma procedência.

    **Não olha mais a página, e a mudança é o item.** Até 2026-08-24 ela media quanto texto a
    camada trazia e a preferia acima de `MIN_CARACTERES_DE_CAMADA`. A pergunta estava errada: o
    que decide não é *quanto* a camada traz, é *o que* ela traz -- e para notação de xadrez ela
    não traz nada de aproveitável. Ver a medição das figurinas no cabeçalho.

    `tem_modelo=False` é o único caso em que `auto` cai para a camada: sem classificador não há
    leitura nenhuma, e uma camada imperfeita é melhor que uma página em branco. É reserva
    declarada, e quem a aciona **avisa** -- ver `ler_pagina`.
    """
    if motor in ("camada", "glifo"):
        return motor  # type: ignore[return-value]
    return "glifo" if tem_modelo else "camada"


def _ha_classificador(reconhecedor: object | None = None) -> bool:
    """Dá para ler com o glifo? Só isto decide a reserva do `auto`.

    Um reconhecedor já construído responde sozinho. Sem ele, a pergunta é se os pesos carregam --
    e ela é feita **uma vez**, porque `carregar_classificador` guarda o resultado em cache.
    """
    if reconhecedor is not None:
        return True
    try:
        from .modelo import CAMINHO_PADRAO_META, carregar_classificador

        carregar_classificador(CAMINHO_PADRAO_META, None)
    except Exception as exc:  # noqa: BLE001 - pesos ausentes é caminho normal, não erro
        logger.debug("Classificador de glifo indisponível: %s", exc)
        return False
    return True


def ler_pagina(
    pdf_source: object,
    indice: int,
    *,
    dpi: int = 220,
    motor: MotorDeTexto = MOTOR_PADRAO,
    max_boards: int | None = None,
    arranjo: Arranjo = "prosa",
    reconhecedor: object | None = None,
    imagem_rgb: np.ndarray | None = None,
    modo_bloco: bool = False,
    colados: str = COLADOS_NA_PAGINA,
    caixa_alta: bool = True,
    marca_fina: bool = True,
    empilhados: bool = True,
    italico: bool = True,
    dicionario: bool = False,
    numeros: bool = True,
    juntar_lance: bool = True,
    marcar_negrito: bool = True,
) -> PaginaLida:
    """Uma página do PDF como `PaginaLida`: colunas de blocos, cabeçalho, rodapé, número impresso.

    `imagem_rgb` deixa quem já renderizou a página (a interface, sempre) não renderizá-la de novo:
    são ~200 ms por página a 220 dpi, e a aba de texto abriria com um atraso que ela não precisa
    ter. Quando vem, o `dpi` tem de ser o mesmo com que ela foi renderizada -- é o que liga pixels
    a pontos, e não há como conferir aqui.
    """
    from ..detection.hybrid import detect_diagrams_in_pdf_page
    from ..pdf_io import open_document, render_pdf_page
    from ..pdf_text import page_margin_lines, running_page_number

    escala_px = dpi / 72.0
    imagem = render_pdf_page(pdf_source, indice, dpi=dpi) if imagem_rgb is None else imagem_rgb  # type: ignore[arg-type]

    qual = motor_escolhido(motor, tem_modelo=_ha_classificador(reconhecedor))
    if motor == "auto" and qual == "camada":
        logger.warning(
            "Sem classificador de glifo: a folha %d vai pela camada de texto do PDF, que não "
            "representa figurina de xadrez. Ver text/leitor.py.",
            indice + 1,
        )

    with open_document(pdf_source) as doc:  # type: ignore[arg-type]
        page = doc[indice]
        largura = float(page.rect.width)
        altura = float(page.rect.height)
        cruas = linhas_da_camada(page, escala_px=escala_px) if qual == "camada" else []
        margem = [linha for linha in page_margin_lines(page) if linha.text.strip()]
        numero = running_page_number(doc, indice)
        documento = str(getattr(doc, "name", "") or "")
        spans_negrito = _negrito.spans_de_negrito(page) if marcar_negrito else []
        registra_negrito = (
            bool(spans_negrito) or _negrito.documento_registra_negrito(doc)
            if marcar_negrito
            else False
        )

    if max_boards:
        candidatos = detect_diagrams_in_pdf_page(pdf_source, indice, imagem, max_boards=max_boards)  # type: ignore[arg-type]
    else:
        candidatos = detect_diagrams_in_pdf_page(pdf_source, indice, imagem)  # type: ignore[arg-type]
    retangulos = [
        (
            c.bbox_pdf[0] * escala_px,
            c.bbox_pdf[1] * escala_px,
            c.bbox_pdf[2] * escala_px,
            c.bbox_pdf[3] * escala_px,
        )
        for c in candidatos
    ]
    confiancas = [float(c.detector_score) for c in candidatos]

    faixas: list[tuple[int, int]] | None = None
    if qual == "glifo":
        cruas, faixas = linhas_do_glifo(
            imagem, retangulos, reconhecedor=reconhecedor, modo_bloco=modo_bloco, colados=colados, caixa_alta=caixa_alta, marca_fina=marca_fina,
            empilhados=empilhados, italico=italico,
            dicionario=dicionario, numeros=numeros,
            juntar_lance=juntar_lance,
        )

    if marcar_negrito and cruas:
        cruas = _com_negrito(cruas, spans_negrito, registra_negrito, escala_px)

    cabecalho, rodape = _margens(margem, altura, qual)
    return PaginaLida(
        documento=documento,
        pagina=indice,
        largura=largura,
        altura=altura,
        unidade="pt",
        colunas=montar(
            cruas,
            retangulos,
            escala_px=escala_px,
            arranjo=arranjo,
            confiancas=confiancas,
            faixas=faixas,
        ),
        cabecalho=cabecalho,
        rodape=rodape,
        numero_impresso=numero,
    )


def _com_negrito(
    cruas: Sequence[_Cru],
    spans: Sequence[Retangulo],
    registra: bool,
    escala_px: float,
) -> list[_Cru]:
    """As mesmas linhas, com o peso da fonte anotado. Ver `text/negrito.py`.

    Os spans vêm em **pontos** e as caixas em **pixels**; a conversão acontece aqui, no único
    lugar em que as duas se encontram.
    """
    from dataclasses import replace

    bboxes = [_para_pontos(c.caixa, escala_px) for c in cruas]
    pesos = _negrito.marcar(bboxes, spans, registra=registra)
    return [replace(c, negrito=p) for c, p in zip(cruas, pesos, strict=True)]


def _margens(linhas: Sequence[object], altura: float, procedencia: MotorResolvido) -> tuple[LinhaLida | None, LinhaLida | None]:
    """A linha de cabeçalho e a de rodapé, das que moram na faixa de margem.

    A faixa vale para os dois lados, então quem separa é o `y`: acima da metade é cabeçalho. Só
    **uma** de cada, e a mais externa -- uma faixa de margem com três linhas tem um cabeçalho e
    duas linhas de texto que a régua da S-43 pegou por estarem perto da borda.
    """
    if not linhas:
        return (None, None)
    meio = altura / 2.0

    def como_lida(linha: object) -> LinhaLida:
        return LinhaLida(
            texto=str(linha.text).strip(),  # type: ignore[attr-defined]
            bbox=_retangulo(linha.bbox),  # type: ignore[attr-defined]
            confianca=float(getattr(linha, "confidence", 1.0)),
            procedencia=procedencia,
        )

    acima = [x for x in linhas if float(x.bbox[1]) < meio]  # type: ignore[attr-defined]
    abaixo = [x for x in linhas if float(x.bbox[1]) >= meio]  # type: ignore[attr-defined]
    cabecalho = como_lida(min(acima, key=lambda x: float(x.bbox[1]))) if acima else None  # type: ignore[attr-defined]
    rodape = como_lida(max(abaixo, key=lambda x: float(x.bbox[3]))) if abaixo else None  # type: ignore[attr-defined]
    return (cabecalho, rodape)


__all__ = [
    "FOLGA_DA_MASCARA",
    "MIN_CARACTERES_DE_CAMADA",
    "COLADOS_NA_PAGINA",
    "MOTORES",
    "MOTOR_PADRAO",
    "MotorResolvido",
    "MotorDeTexto",
    "e_fila_de_eixo",
    "escala_fora_dos_diagramas",
    "ler_pagina",
    "linhas_da_camada",
    "leitor_de_linha_padrao",
    "linhas_do_glifo",
    "segmentar",
    "calha_de_linhas",
    "montar",
    "sem_rotulos_de_eixo",
    "motor_escolhido",
]
