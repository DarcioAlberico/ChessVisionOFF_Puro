# Origem: Editor_Diagramas_de_Xadrez/src/chess_pdf_editor/pdf_service.py
#         (`operation_signature`, `_write_space_cropbox`, `_to_write_space`, `erase_signature`)
#         e .../types.py (`OverlayOperation`, `EraseOperation`).
# Absorvido em 2026-09-07. Alterações: (a) a conversão entre os dois espaços de coordenada
#         deixou de depender do `fitz` e virou aritmética pura -- lá ela só existia dentro de
#         `page.derotation_matrix`, e nenhum teste podia afirmar a ida-e-volta sem abrir um PDF;
#         (b) as duas listas de operações passaram a ter desfazer, e ele é o `ui/historico.py`
#         do tronco em vez de uma segunda pilha; (c) `whiteout_padding_pt` saiu -- ver `FOLGA_PADRAO_PT`.
"""O que é uma substituição de diagrama dentro de um PDF, antes de qualquer PyMuPDF (F9).

**O item que este módulo porta.** O `Editor_Diagramas_de_Xadrez` sabe apagar um retângulo da
página e carimbar um tabuleiro novo no lugar dele, preservando o espaço de coordenadas da página.
É a capacidade mais valiosa daquele aplicativo, e ela vinha misturada com o `fitz`: a regra e a
biblioteca no mesmo arquivo, de forma que a parte **decidida** -- que retângulo, com que folga,
com que assinatura, em que espaço -- não tinha como ser afirmada sem abrir um documento.

Aqui ficam as decisões. O PyMuPDF fica em `chess_diagram_ocr/pdf_substituicao.py`, pela mesma
regra que põe `pdf_io.py` fora de `ui/`: leitura e escrita de arquivo não são decisão de
interface, e `ui/` é o que roda sem janela e sem disco.

---

## Os dois espaços de coordenada, e por que eles são o item (ASSETS §2.8)

Tudo o que a pessoa vê e escolhe está no espaço de `page.rect`: a seleção sobre a página
renderizada, o retângulo gravado no projeto, a caixa que o detector devolveu. Mas **escrever** na
página -- `show_pdf_page`, `insert_image`, `add_redact_annot`, `draw_rect`, `insert_text`,
`insert_link` -- e **ler texto** dela, inclusive o `clip=` do `get_text`, é no espaço de escrita,
que é o que `page.transformation_matrix` produz.

Os dois só coincidem quando não há rotação nem CropBox deslocada -- que é o caso comum, e é
justamente o que faz o defeito passar despercebido até alguém abrir um livro escaneado de lado.
A conversão é uma só, e a origem mede 80 geometrias (as quatro rotações combinadas com qualquer
CropBox e qualquer MediaBox):

    vista   = (escrita − origem) * rotacao
    escrita = vista * derotacao + origem

onde `origem` é o canto superior-esquerdo da CropBox **no espaço de escrita**. Sem rotação essa
origem é `(0, 0)` -- a `transformation_matrix` já embute o deslocamento da CropBox --, e é por
isso que o caso comum atravessa isto inalterado.

**Por que a matemática é pura aqui.** Na origem ela morava em `fitz.Rect * page.derotation_matrix`,
e afirmar a ida-e-volta exigia um PDF girado no disco. As duas matrizes e a origem são seis
`float` e um par: `EspacoDeEscrita` os recebe prontos e a conversão vira aritmética, afirmável
para as quatro rotações sem abrir arquivo nenhum. Quem lê as três coisas do documento é
`pdf_substituicao.espaco_de_escrita`, numa função de quatro linhas.

## A pilha de desfazer é a do tronco, e não uma segunda

`ui/historico.Historico` é uma **pilha de estados**, e o docstring dele explica por quê: uma pilha
de gestos precisa saber inverter cada operação, e o sintoma de esquecer a oitava é um desfazer que
devolve um estado que nunca existiu. O argumento vale igual aqui -- acrescentar, remover, editar a
folga, trocar a FEN, apagar uma faixa de coordenada --, então a lista de operações pendentes é
serializada num texto canônico e é **esse texto** que entra na pilha existente.

O custo é o que aquele módulo já mediu e aceitou: cem estados de uma lista de 60 diagramas são
alguns quilobytes. O ganho é não haver duas respostas para "o que `Ctrl+Z` faz".
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

from . import historico

__all__ = [
    "SEM_ROTACAO",
    "Apagamento",
    "EspacoDeEscrita",
    "PilhaDeSubstituicoes",
    "Retangulo",
    "Substituicao",
    "assinatura_da_pagina",
    "folga_aplicada",
    "quer_link_lichess",
    "vazio",
]

Retangulo = tuple[float, float, float, float]
"""`(x0, y0, x1, y1)` em **pontos do PDF**, no espaço de `page.rect` -- o que a pessoa vê.

Ponto e não pixel pela decisão da S-41, que `ui/page_overlay.py` já registra: o pixel só existe
em relação a um DPI, e o DPI é um campo da tela que a pessoa mexe."""

Matriz = tuple[float, float, float, float, float, float]
"""`(a, b, c, d, e, f)`, na convenção do PyMuPDF: `(x, y) -> (a·x + c·y + e, b·x + d·y + f)`."""

IDENTIDADE: Matriz = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

FOLGA_PADRAO_PT = 0.5
"""Meio ponto de folga em volta do diagrama, em cada lado, no apagamento.

**É uma folga e não uma margem de segurança generosa**, e o número é da origem. O que ela cobre é
o antialias da borda do diagrama impresso; o que ela **não** pode cobrir é a coordenada `a`--`h`
que o livro imprime em volta, porque apagar aquilo por engano estraga a página de quem só queria
trocar o tabuleiro. Quem trata das coordenadas é a detecção conservadora de
`pdf_substituicao.achar_coordenadas`, que é outra decisão e tem outro botão.

**Os quatro lados são independentes, e o campo único da origem não veio junto.** Lá havia
`whiteout_padding_pt` *e* os quatro `whiteout_padding_<lado>_pt`, com o primeiro servindo de
padrão dos outros por `getattr` -- dois caminhos para a mesma pergunta, e o `getattr` existia
porque as operações gravadas em projeto antigo não tinham os campos novos. Aqui a classe é nova e
não tem passado a acomodar: quatro campos, um significado cada."""


# --------------------------------------------------------------------- os dois espaços


def _ponto(x: float, y: float, m: Matriz) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _normalizado(x0: float, y0: float, x1: float, y1: float) -> Retangulo:
    """Os dois cantos em ordem. **Não é zelo: é o que a rotação exige.**

    Uma matriz de rotação de 90° troca os eixos e nega um deles, então o canto que entrou como
    superior-esquerdo sai como inferior-direito. Um retângulo com `x1 < x0` é vazio para o
    PyMuPDF -- `is_empty` responde `True` --, e o sintoma de não normalizar é uma substituição
    que simplesmente não acontece na página girada, sem erro nenhum.
    """
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


@dataclass(frozen=True)
class EspacoDeEscrita:
    """A ponte entre o espaço que a pessoa vê e o espaço em que se escreve na página.

    Os três campos saem do documento (`pdf_substituicao.espaco_de_escrita`) e daqui para baixo
    são números: é o que permite afirmar as quatro rotações sem abrir PDF.
    """

    origem: tuple[float, float] = (0.0, 0.0)
    """O canto superior-esquerdo da CropBox **em coordenadas de escrita**. `(0, 0)` sem rotação."""

    derotacao: Matriz = IDENTIDADE
    """`page.derotation_matrix`: leva do espaço da vista para o da escrita, antes da origem."""

    rotacao: Matriz = IDENTIDADE
    """`page.rotation_matrix`: o caminho de volta, depois de tirar a origem."""

    def para_escrita(self, retangulo: Retangulo) -> Retangulo:
        """Da seleção que a pessoa fez para onde o PyMuPDF de fato escreve."""
        ox, oy = self.origem
        x0, y0, x1, y1 = retangulo
        ax, ay = _ponto(x0, y0, self.derotacao)
        bx, by = _ponto(x1, y1, self.derotacao)
        return _normalizado(ax + ox, ay + oy, bx + ox, by + oy)

    def para_vista(self, retangulo: Retangulo) -> Retangulo:
        """O caminho de volta. Existe para o teste afirmar a ida-e-volta (ASSETS §2.12).

        A validação de ida-e-volta obrigatória é regra da casa, e aqui ela é barata: uma
        conversão que não volta é uma conversão errada, e o defeito dela aparece três camadas
        adiante, como um tabuleiro deitado no canto da página.
        """
        ox, oy = self.origem
        x0, y0, x1, y1 = retangulo
        ax, ay = _ponto(x0 - ox, y0 - oy, self.rotacao)
        bx, by = _ponto(x1 - ox, y1 - oy, self.rotacao)
        return _normalizado(ax, ay, bx, by)


SEM_ROTACAO = EspacoDeEscrita()
"""A página comum: sem `/Rotate` e sem CropBox deslocada. A conversão é a identidade.

Existe nomeada porque é o caso em que a origem passava despercebida -- e porque um teste que
queira falar de operações sem falar de geometria precisa de um espaço para passar."""


# --------------------------------------------------------------------- as operações


@dataclass(frozen=True)
class Substituicao:
    """Apagar este retângulo desta página e carimbar este diagrama no lugar.

    **Congelada de propósito.** A mesma lista viaja para a prévia, para a exportação e para a
    pilha de desfazer; uma operação mutável faria a prévia e o arquivo divergirem sem que nada
    dissesse -- e a origem registra exatamente esse defeito em `_operation_in_write_space`, que
    copia em vez de converter no lugar.
    """

    pagina: int
    retangulo: Retangulo
    placement: str
    """O campo de peças da FEN, no vocabulário do tronco (`ui/board_edit.placement_of`)."""

    lado: str = "w"
    lance: int = 1
    """Lado a jogar e número do lance. Nenhum dos dois muda um pixel do tabuleiro desenhado --
    eles saem no PDF **só** pelo link do Lichess, e é por isso que `quer_link_lichess` importa."""

    folga_esquerda_pt: float = FOLGA_PADRAO_PT
    folga_topo_pt: float = FOLGA_PADRAO_PT
    folga_direita_pt: float = FOLGA_PADRAO_PT
    folga_base_pt: float = FOLGA_PADRAO_PT
    borda_pt: float = 0.0
    """Contorno preto em volta do diagrama novo. `0` desenha nada, e é o padrão: o livro que
    imprime moldura já tem a dele fora do retângulo, e desenhar a segunda é o que faz a
    substituição parecer substituição."""

    link_lichess: bool | None = None
    """Link Lichess **deste** diagrama. `None` segue a opção global; `True`/`False` mandam nela.

    Três estados e não dois, e a razão é da origem: com dois, todo projeto antigo nasceria com um
    valor escolhido por nós em cada diagrama, e mudar a global depois deixaria de surtir efeito em
    qualquer um deles."""

    def com_retangulo(self, retangulo: Retangulo) -> Substituicao:
        """A mesma operação noutro retângulo. É o que a conversão de espaço usa -- cópia."""
        return replace(self, retangulo=retangulo)


@dataclass(frozen=True)
class Apagamento:
    """Só apagar. É a borracha: uma legenda que sobrou, a moldura do diagrama antigo."""

    pagina: int
    retangulo: Retangulo

    def com_retangulo(self, retangulo: Retangulo) -> Apagamento:
        return replace(self, retangulo=retangulo)


def folga_aplicada(op: Substituicao) -> Retangulo:
    """O retângulo que o apagamento cobre: o diagrama mais a folga de cada lado.

    Folga negativa é tratada como zero, e não recusada: ela chega de um campo numérico da
    interface, e recusar a exportação inteira por causa de um `-1` digitado seria
    desproporcional -- é o mesmo critério de `semantics.compose_fen` com o número de lance.
    """
    x0, y0, x1, y1 = op.retangulo
    return (
        x0 - max(0.0, op.folga_esquerda_pt),
        y0 - max(0.0, op.folga_topo_pt),
        x1 + max(0.0, op.folga_direita_pt),
        y1 + max(0.0, op.folga_base_pt),
    )


def quer_link_lichess(op: Substituicao, padrao_global: bool) -> bool:
    """Este diagrama leva link? Um lugar só decide, e todos os caminhos passam por aqui.

    A regra (`None` segue a global) escrita em três lugares -- prévia, exportação, galeria --
    seria o par mantido à mão: a prévia divergiria da exportação, e o que se promete é que as
    duas são o mesmo caminho de código.
    """
    return bool(padrao_global) if op.link_lichess is None else bool(op.link_lichess)


def vazio(retangulo: Retangulo) -> bool:
    """Retângulo sem área. Operação vazia não é erro -- é operação que não faz nada, e some."""
    x0, y0, x1, y1 = retangulo
    return not (x1 > x0 and y1 > y0)


# --------------------------------------------------------------------- as assinaturas

_CASAS = 3
"""Casas decimais da assinatura. Um ponto do PDF mede 1/72 de polegada; um milésimo dele é
1/72.000 -- muito abaixo do que qualquer arrasto de mouse produz, e acima do ruído de `float`."""


def assinatura_de_substituicao(op: Substituicao) -> tuple[object, ...]:
    """Identidade visual de uma substituição, para o cache da prévia.

    **Todo campo que muda um pixel da página tem de estar aqui.** Um que falte não produz erro:
    produz uma prévia que não se atualiza, o que é pior -- o que está na tela deixa de ser o que
    o PDF vai conter, e o cache incompleto quebra essa promessa sem quebrar o teste que a cobre.

    Foi o que aconteceu na origem com o link por diagrama: ele entrou no modelo e não entrou na
    assinatura, e trocar a escolha deixava a prévia mostrando o resultado anterior -- ao lado da
    miniatura da galeria, que mostrava o certo porque abria o próprio documento. Duas respostas
    para a mesma pergunta, na mesma tela.

    O teste que cobra isto é `tests/test_substituicao.py`, e ele não confere uma lista escrita à
    mão: ele varre os campos da `dataclass` e exige que cada um apareça, para que um campo novo
    entre na assinatura ou reprove.
    """
    x0, y0, x1, y1 = op.retangulo
    return (
        int(op.pagina),
        round(float(x0), _CASAS),
        round(float(y0), _CASAS),
        round(float(x1), _CASAS),
        round(float(y1), _CASAS),
        str(op.placement),
        str(op.lado),
        int(op.lance),
        round(float(op.folga_esquerda_pt), _CASAS),
        round(float(op.folga_topo_pt), _CASAS),
        round(float(op.folga_direita_pt), _CASAS),
        round(float(op.folga_base_pt), _CASAS),
        round(float(op.borda_pt), _CASAS),
        op.link_lichess,
    )


def assinatura_de_apagamento(op: Apagamento) -> tuple[object, ...]:
    x0, y0, x1, y1 = op.retangulo
    return (
        int(op.pagina),
        round(float(x0), _CASAS),
        round(float(y0), _CASAS),
        round(float(x1), _CASAS),
        round(float(y1), _CASAS),
    )


def assinatura_da_pagina(
    *,
    documento: str,
    pagina: int,
    substituicoes: Sequence[Substituicao],
    apagamentos: Sequence[Apagamento] = (),
    apagar_fundo: bool = True,
    link_lichess: bool = True,
    apagar_coordenadas: bool = False,
    escopo_do_desenho: str = "",
) -> tuple[object, ...]:
    """A identidade da página inteira já alterada. É a chave do documento de prévia.

    `escopo_do_desenho` é o que o desenho do tabuleiro depende e não está nas operações -- hoje,
    o caminho da fonte Merida em vigor, que pode ser trocado em execução. Ele faz parte da
    identidade do que foi renderizado, e esquecê-lo daria uma prévia que não muda ao trocar a
    fonte.
    """
    return (
        str(documento),
        int(pagina),
        bool(apagar_fundo),
        bool(link_lichess),
        bool(apagar_coordenadas),
        str(escopo_do_desenho),
        tuple(assinatura_de_substituicao(op) for op in substituicoes),
        tuple(assinatura_de_apagamento(op) for op in apagamentos),
    )


# --------------------------------------------------------------------- o estado, e o desfazer


def texto_do_estado(
    substituicoes: Sequence[Substituicao], apagamentos: Sequence[Apagamento] = ()
) -> str:
    """As duas listas como um texto canônico -- o que entra na pilha de `ui/historico.py`.

    **JSON e não `repr`.** O que se precisa é de um texto que volte exatamente ao que era e que
    compare igual quando nada mudou; `json` cumpre os dois com `float` (ele escreve `repr`, que
    ida-e-volta em `float` do Python é exata) e é legível quando alguém precisa olhar uma pilha
    no depurador. `repr` de `dataclass` voltaria só com `eval`, que não é preço a pagar por um
    texto interno.

    A ordem das chaves é fixa (`sort_keys`) porque o texto é comparado: dois estados iguais
    escritos em ordens diferentes fariam `Historico.registrar` aceitar uma edição que não houve, e
    a pilha encheria de estados idênticos -- exatamente o defeito que o `return False` dele evita.
    """
    return json.dumps(
        {
            "substituicoes": [
                {
                    "pagina": int(op.pagina),
                    "retangulo": [float(v) for v in op.retangulo],
                    "placement": str(op.placement),
                    "lado": str(op.lado),
                    "lance": int(op.lance),
                    "folga_esquerda_pt": float(op.folga_esquerda_pt),
                    "folga_topo_pt": float(op.folga_topo_pt),
                    "folga_direita_pt": float(op.folga_direita_pt),
                    "folga_base_pt": float(op.folga_base_pt),
                    "borda_pt": float(op.borda_pt),
                    "link_lichess": op.link_lichess,
                }
                for op in substituicoes
            ],
            "apagamentos": [
                {"pagina": int(op.pagina), "retangulo": [float(v) for v in op.retangulo]}
                for op in apagamentos
            ],
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def estado_do_texto(texto: str) -> tuple[tuple[Substituicao, ...], tuple[Apagamento, ...]]:
    """O caminho de volta. Texto vazio devolve as duas listas vazias.

    Texto vazio é estado normal e não erro: é com ele que `Historico` nasce quando ninguém
    passou nada, e recusá-lo obrigaria a pilha a conhecer o formato -- que é o contrário do que
    reusá-la significa.
    """
    if not texto.strip():
        return ((), ())
    dados = json.loads(texto)
    substituicoes = tuple(
        Substituicao(
            pagina=int(item["pagina"]),
            retangulo=(
                float(item["retangulo"][0]),
                float(item["retangulo"][1]),
                float(item["retangulo"][2]),
                float(item["retangulo"][3]),
            ),
            placement=str(item["placement"]),
            lado=str(item.get("lado", "w")),
            lance=int(item.get("lance", 1)),
            folga_esquerda_pt=float(item.get("folga_esquerda_pt", FOLGA_PADRAO_PT)),
            folga_topo_pt=float(item.get("folga_topo_pt", FOLGA_PADRAO_PT)),
            folga_direita_pt=float(item.get("folga_direita_pt", FOLGA_PADRAO_PT)),
            folga_base_pt=float(item.get("folga_base_pt", FOLGA_PADRAO_PT)),
            borda_pt=float(item.get("borda_pt", 0.0)),
            link_lichess=item.get("link_lichess"),
        )
        for item in dados.get("substituicoes", ())
    )
    apagamentos = tuple(
        Apagamento(
            pagina=int(item["pagina"]),
            retangulo=(
                float(item["retangulo"][0]),
                float(item["retangulo"][1]),
                float(item["retangulo"][2]),
                float(item["retangulo"][3]),
            ),
        )
        for item in dados.get("apagamentos", ())
    )
    return (substituicoes, apagamentos)


@dataclass
class PilhaDeSubstituicoes:
    """As operações pendentes de um livro, com desfazer e refazer.

    **Ela não tem pilha própria.** `ui/historico.Historico` é a pilha de estados do projeto desde
    a S-229, e o argumento dela vale aqui sem uma vírgula de mudança: uma pilha de gestos teria de
    saber inverter acrescentar, remover, mover, redimensionar, trocar a FEN, mexer em cada uma das
    quatro folgas e na borda -- e o dia em que a nona operação esquecesse o inverso, `Ctrl+Z`
    devolveria uma lista que nunca existiu.

    O que este objeto acrescenta é a tradução: lista de operações ↔ texto canônico. Um método por
    edição, e cada um devolve **se de fato mudou alguma coisa** -- que é o que o painel usa para
    decidir se reacende o botão de exportar.
    """

    _historico: historico.Historico = field(default_factory=historico.Historico)

    def __init__(
        self,
        substituicoes: Iterable[Substituicao] = (),
        apagamentos: Iterable[Apagamento] = (),
        *,
        teto: int = historico.TETO,
    ) -> None:
        self._historico = historico.Historico(
            texto_do_estado(tuple(substituicoes), tuple(apagamentos)), teto=teto
        )

    # ------------------------------------------------------------------------------ leitura

    @property
    def substituicoes(self) -> tuple[Substituicao, ...]:
        return estado_do_texto(self._historico.atual)[0]

    @property
    def apagamentos(self) -> tuple[Apagamento, ...]:
        return estado_do_texto(self._historico.atual)[1]

    @property
    def pode_desfazer(self) -> bool:
        return self._historico.pode_desfazer

    @property
    def pode_refazer(self) -> bool:
        return self._historico.pode_refazer

    @property
    def profundidade(self) -> int:
        return self._historico.profundidade

    def na_pagina(self, pagina: int) -> tuple[Substituicao, ...]:
        """As substituições daquela página, na ordem em que foram acrescentadas."""
        return tuple(op for op in self.substituicoes if op.pagina == pagina)

    def apagamentos_na_pagina(self, pagina: int) -> tuple[Apagamento, ...]:
        return tuple(op for op in self.apagamentos if op.pagina == pagina)

    def indice_em(self, pagina: int, x: float, y: float) -> int | None:
        """Qual substituição está sob aquele ponto, ou `None`. A **última** desenhada ganha.

        A última e não a primeira porque é ela que está por cima: duas operações sobrepostas na
        mesma página são desenhadas na ordem da lista, e clicar escolhe o que se vê. É a mesma
        regra que `page_overlay.hit_test` aplica às caixas do detector.
        """
        for indice in range(len(self.substituicoes) - 1, -1, -1):
            op = self.substituicoes[indice]
            if op.pagina != pagina:
                continue
            x0, y0, x1, y1 = op.retangulo
            if x0 <= x <= x1 and y0 <= y <= y1:
                return indice
        return None

    # ------------------------------------------------------------------------------ escrita

    def _gravar(
        self, substituicoes: Sequence[Substituicao], apagamentos: Sequence[Apagamento]
    ) -> bool:
        return self._historico.registrar(texto_do_estado(substituicoes, apagamentos))

    def acrescentar(self, op: Substituicao) -> bool:
        """Mais um diagrama a trocar. Devolve se a lista mudou."""
        return self._gravar([*self.substituicoes, op], self.apagamentos)

    def acrescentar_apagamento(self, op: Apagamento) -> bool:
        return self._gravar(self.substituicoes, [*self.apagamentos, op])

    def substituir(self, indice: int, op: Substituicao) -> bool:
        """Troca a operação daquele índice -- é o que mexer numa folga ou na FEN faz.

        Índice fora da lista devolve `False` em vez de levantar: quem chama é um painel com uma
        seleção que pode ter sido invalidada por um desfazer, e derrubar a janela por causa disso
        seria trocar um botão que não faz nada por um travamento.
        """
        atuais = list(self.substituicoes)
        if not 0 <= indice < len(atuais):
            return False
        atuais[indice] = op
        return self._gravar(atuais, self.apagamentos)

    def remover(self, indice: int) -> bool:
        atuais = list(self.substituicoes)
        if not 0 <= indice < len(atuais):
            return False
        del atuais[indice]
        return self._gravar(atuais, self.apagamentos)

    def remover_apagamento(self, indice: int) -> bool:
        atuais = list(self.apagamentos)
        if not 0 <= indice < len(atuais):
            return False
        del atuais[indice]
        return self._gravar(self.substituicoes, atuais)

    def limpar(self) -> bool:
        """Zera as duas listas -- e **continua sendo desfazível**, que é o item.

        Um "limpar" que apagasse o histórico junto seria o botão mais caro da janela: sessenta
        diagramas de trabalho num clique, sem volta. A S-76 deste projeto é o registro do que
        custa exatamente isso, com 1.405 diagramas.
        """
        return self._gravar((), ())

    def desfazer(self) -> bool:
        return self._historico.desfazer() is not None

    def refazer(self) -> bool:
        return self._historico.refazer() is not None

    def zerar(
        self, substituicoes: Iterable[Substituicao] = (), apagamentos: Iterable[Apagamento] = ()
    ) -> None:
        """Recomeça, sem passado. É o que trocar de livro chama.

        Trocar de livro **tem** de zerar: desfazer para dentro de outro documento devolveria
        operações com números de página de um PDF que não está mais aberto, e a exportação
        seguinte as aplicaria em páginas erradas. É a mesma razão que faz `Historico.zerar`
        existir para a troca de diagrama.
        """
        self._historico.zerar(texto_do_estado(tuple(substituicoes), tuple(apagamentos)))
