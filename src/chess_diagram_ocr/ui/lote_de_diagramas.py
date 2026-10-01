"""O lote de diagramas: o que sai, com que nome, em que formato e de que tamanho (S-544).

**O que faltava.** O projeto sabia desenhar **um** diagrama a partir de uma FEN desde a Fase 83 --
`diagrama_svg.svg_da_posicao` e `diagrama_png.png_da_posicao`, com a régua, a plaqueta de lado a
jogar e o contraste já medidos. O que não existia era o **lote**: os dois só eram chamados de
dentro de `epub.py` e de `docx_saida.py`, para embutir a figura num documento, e não havia caminho
nenhum -- nem janela, nem comando de linha -- que gravasse os diagramas **soltos**. Quem converte
um livro digitalizado e diagrama noutro programa precisa exatamente disso: quinhentos arquivos de
imagem, no tamanho da coluna dele, com nome que diga de que página cada um veio.

Este módulo é **a decisão**, e nada mais. Quem escreve arquivo é `diagramas_em_lote.py`; quem
pergunta as escolhas é `qt/lote_de_diagramas.py`, aberto de dois lugares -- a sala de estudo, pelo
menu, e a aba Galeria, pelo botão. Aqui ficam as quatro perguntas que não são de desenho nem de
disco:

1. **O que o lote contém.** Uma origem -- o estudo aberto, um PGN inteiro, um livro varrido, a
   galeria -- vira uma lista de `ItemDoLote`, e cada item carrega a **procedência**: livro, página,
   diagrama, número do exercício. A procedência não é enfeite: é o que faz o arquivo achável seis
   meses depois, e é o que nomeia o arquivo.
2. **Como cada arquivo se chama.** Sem caractere que o sistema recuse, sem colisão -- nem entre
   dois nomes iguais, nem entre dois que só diferem por maiúscula, que no Windows e no macOS são
   o mesmo arquivo --, e com o número **preenchido com zeros à esquerda** para que a ordem do
   gerenciador de arquivos seja a ordem do livro.
3. **Em que formato e de que tamanho.** PNG e SVG, e um `tamanho` só para os dois: pixel no PNG,
   `width`/`height` no SVG -- que continua vetor, com o mesmo `viewBox`.
4. **Com que pele e que conjunto de peças**, e o que entra em volta do tabuleiro.

Sem toolkit e sem disco, como todo módulo de `ui/`.

## A pele do diagrama é outra coisa que a pele da janela

`ui/pele.py` decide arranjo e densidade de **cromo**, e `tokens.SUPERFICIES_DE_DOCUMENTO` prende o
tabuleiro na paleta medida de propósito (S-224): o trabalho da janela é comparar diagrama impresso
com o que o modelo leu, e um damero que muda de cor com a aparência deixa de servir para isso.

Um arquivo exportado não está nessa comparação -- ele vai para dentro de outro livro. E o livro que
o editor está montando pode ser impresso **numa tinta só**, onde dois marrons viram duas manchas
parecidas. Por isso há duas peles aqui, e só duas: a do produto e a de uma tinta. A segunda é
**derivada** da primeira por `tokens.cinza_equivalente`, cor a cor -- não é uma paleta nova
escolhida a olho. A razão de contraste da WCAG é definida sobre a luminância, então converter por
luminância preserva **exatamente** os números que a S-146 mediu para a régua e para a plaqueta. Uma
terceira pele inventada seria a "cor plausível e sem significado" que `ui/tokens.py` existe para
impedir.

## A faixa é uma proporção, e é a mesma nos dois formatos

`diagrama_svg.MARGEM` é 15 sobre uma casa de 45 -- **um terço**. `diagrama_png.MARGEM_PX` é 28 sobre
uma casa de 70 -- **dois quintos** --, e o docstring de lá diz "como `MARGEM` no SVG". Não é: o PNG
e o SVG do mesmo diagrama saíam com molduras de larguras diferentes, e ninguém comparava. Aqui a
faixa é declarada uma vez, **em porcentagem da casa**, e os dois desenhistas a recebem pronta. O
padrão é o do PNG (40%), que é o que foi medido com uma régua de fonte real desenhada dentro dele.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..diagrama_svg import CASA, Cores, cores_padrao
from ..estudo import Estudo
from ..estudo_paragrafos import DIAGRAMA, paragrafos, titulo_do_estudo
from . import conjuntos, tokens

__all__ = [
    "MARGEM_MAXIMA",
    "MARGEM_PADRAO",
    "PADRAO",
    "PELES_DO_DIAGRAMA",
    "PNG",
    "SVG",
    "TAMANHOS",
    "TAMANHO_MAXIMO",
    "TAMANHO_MINIMO",
    "TAMANHO_PADRAO",
    "UMA_TINTA",
    "Formato",
    "ItemDoLote",
    "Opcoes",
    "PeleDoDiagrama",
    "cores_da_pele",
    "da_galeria",
    "de_estudos",
    "do_estudo",
    "formato_registrado",
    "frase_do_lote",
    "nomes_do_lote",
]
"""`LIMITE_DO_NOME` e `pele_registrada` ficaram **de fora de propósito**: os dois são aplicados
aqui dentro, pelas funções que são a API -- o limite por `_nome_bruto`, o registro por `Opcoes`,
`cores_da_pele` e `frase_do_lote`. Exportá-los seria oferecer duas portas para a mesma decisão, e
é a segunda que envelhece. `formato_registrado` fica porque `diagramas_em_lote.py` o chama: quem
grava o arquivo precisa da extensão, e ela é do formato."""

# --------------------------------------------------------------------------- os formatos

PNG = "png"
SVG = "svg"


@dataclass(frozen=True)
class Formato:
    """Um formato de saída do lote. A chave é a extensão sem o ponto, e é o que vai para o disco."""

    nome: str
    rotulo: str
    """Como a pessoa lê na escolha. É o nome do formato, como "FEN" e "PGN" -- não se traduz."""

    vetor: bool
    """Se ele cresce sem perder. Decide duas coisas: se o tamanho pedido tem teto, e se o conjunto
    de peças escolhido tem efeito -- o SVG desenha as peças do `python-chess`, que são caminho."""

    @property
    def extensao(self) -> str:
        return f".{self.nome}"


FORMATOS: tuple[Formato, ...] = (
    Formato(PNG, "PNG", vetor=False),
    Formato(SVG, "SVG", vetor=True),
)
"""Os dois, na ordem em que a escolha os lista. O PNG primeiro porque é o que **todo** programa
abre; o SVG é o que não serrilha, e quem sabe que precisa dele o escolhe."""

_FORMATO_POR_NOME: dict[str, Formato] = {registro.nome: registro for registro in FORMATOS}


def formato_registrado(nome: str) -> Formato:
    """O formato daquele nome. Levanta `KeyError` -- os registrados estão em `FORMATOS`."""
    if nome not in _FORMATO_POR_NOME:
        raise KeyError(f"formato de diagrama desconhecido: {nome!r}. Os registrados estão em FORMATOS.")
    return _FORMATO_POR_NOME[nome]


# ------------------------------------------------------------------------------- a pele

PADRAO = "padrao"
UMA_TINTA = "uma_tinta"


@dataclass(frozen=True)
class PeleDoDiagrama:
    """Uma pele do diagrama exportado: a chave, o rótulo, e se ela vai para uma tinta só."""

    nome: str
    rotulo: str
    uma_tinta: bool = False


PELES_DO_DIAGRAMA: tuple[PeleDoDiagrama, ...] = (
    PeleDoDiagrama(PADRAO, "Padrão"),
    PeleDoDiagrama(UMA_TINTA, "Uma tinta", uma_tinta=True),
)
"""As duas. Ver o cabeçalho: a segunda é derivada da primeira, e não uma paleta nova."""

_PELE_POR_NOME: dict[str, PeleDoDiagrama] = {registro.nome: registro for registro in PELES_DO_DIAGRAMA}


def pele_registrada(nome: str) -> PeleDoDiagrama:
    """A pele daquele nome. Levanta `KeyError` -- as registradas estão em `PELES_DO_DIAGRAMA`."""
    if nome not in _PELE_POR_NOME:
        raise KeyError(f"pele de diagrama desconhecida: {nome!r}. As registradas estão em PELES_DO_DIAGRAMA.")
    return _PELE_POR_NOME[nome]


def cores_da_pele(nome: str) -> Cores:
    """As cores do diagrama naquela pele, prontas para os dois desenhistas.

    A de uma tinta converte **cada** cor por luminância e resolve a régua de novo pelo instrumento
    da S-146 (`tokens.sobre_superficie`): a moldura cinza não é a moldura marrom, e a letra que se
    lê sobre uma pode não ser a que se lê sobre a outra.
    """
    base = cores_padrao().resolvidas()
    if not pele_registrada(nome).uma_tinta:
        return base
    moldura = tokens.cinza_equivalente(base.moldura)
    return Cores(
        clara=tokens.cinza_equivalente(base.clara),
        escura=tokens.cinza_equivalente(base.escura),
        moldura=moldura,
        coordenada=tokens.sobre_superficie(moldura),
        peca_clara=tokens.cinza_equivalente(base.peca_clara),
        peca_escura=tokens.cinza_equivalente(base.peca_escura),
    )


# ---------------------------------------------------------------------------- o tamanho

TAMANHO_MINIMO = 120
"""Abaixo disto a casa fica com 13 px e a peça branca vira mancha -- ver `ui/conjuntos.TRACO`."""

TAMANHO_MAXIMO = 4000
"""O teto do PNG. Quatro mil pixels é uma página inteira a 300 pontos por polegada; acima disso o
arquivo cresce ao quadrado para responder a uma pergunta que o SVG responde de graça."""

TAMANHO_PADRAO = 640
"""O lado do arquivo, em pixel. 640 porque é a largura de uma coluna de livro a 150 pontos por
polegada -- e porque é perto do tamanho nativo (8 × 70 + 2 × 28 = 616), onde a peça não é
reamostrada nem para cima nem para baixo."""

TAMANHOS: tuple[int, ...] = (240, 360, 480, 640, 800, 1200, 1600, 2400)
"""Os tamanhos oferecidos na escolha, que continua aceitando qualquer valor da faixa. Uma lista
porque "quanto?" com uma caixa de digitar vazia é uma pergunta sem resposta padrão."""

MARGEM_PADRAO = 40
"""A faixa em volta do tabuleiro, **em porcentagem da casa**. Ver o cabeçalho."""

MARGEM_MAXIMA = 60
"""Acima disso a moldura come metade da figura e o tabuleiro deixa de ser o assunto dela."""

LIMITE_DO_NOME = 60
"""Quantos caracteres do nome do livro entram no nome do arquivo.

Sessenta e não duzentos: o caminho inteiro no Windows tem 260 caracteres por padrão, e um lote sai
para dentro de uma pasta que já tem caminho. Um nome de livro digitalizado costuma trazer editora,
ano e edição -- e o que identifica é o começo dele."""


@dataclass(frozen=True)
class Opcoes:
    """As escolhas do lote. Congelada, e validada na construção: escolha inválida não vira arquivo."""

    formato: str = PNG
    tamanho: int = TAMANHO_PADRAO
    pele: str = PADRAO
    conjunto: str = conjuntos.PADRAO
    pasta_de_pecas: str = ""
    """A pasta do conjunto do usuário. Vazia com qualquer outro conjunto (`ui/conjuntos.PASTA`)."""

    coordenadas: bool = True
    """As réguas `a`–`h` e `8`–`1`. **É uma opção só**: neste projeto régua e coordenada são a mesma
    coisa desenhada -- `diagrama_svg._reguas` --, e dar dois nomes a uma decisão é o defeito que a
    S-158 mediu. O que existe além delas é a **faixa** em que elas cabem, que é `margem`."""

    plaqueta: bool = True
    """O círculo de "as brancas jogam" na margem, como os livros imprimem."""

    margem: int = MARGEM_PADRAO

    def __post_init__(self) -> None:
        formato_registrado(self.formato)
        pele_registrada(self.pele)
        conjuntos.registrado(self.conjunto)
        if not TAMANHO_MINIMO <= self.tamanho <= TAMANHO_MAXIMO:
            raise ValueError(
                f"tamanho fora da faixa: {self.tamanho}. Entre {TAMANHO_MINIMO} e {TAMANHO_MAXIMO} pixels."
            )
        if not 0 <= self.margem <= MARGEM_MAXIMA:
            raise ValueError(f"margem fora da faixa: {self.margem}. Entre 0 e {MARGEM_MAXIMA} por cento da casa.")

    @property
    def com_faixa(self) -> bool:
        """Se há faixa em volta. Sem régua e sem plaqueta não há o que pôr nela, e ela não sai --
        é a regra que os dois desenhistas já aplicam, declarada aqui para o cálculo do tamanho."""
        return self.margem > 0 and (self.coordenadas or self.plaqueta)

    @property
    def casa_px(self) -> int:
        """O lado da casa em pixel, para o PNG sair **o mais perto possível** do tamanho pedido.

        As oito casas têm de ter o mesmo número inteiro de pixels: um lado que não seja múltiplo de
        oito põe uma coluna de 1 px de diferença em algum lugar do damero, e é a única coisa que se
        vê num diagrama de xadrez. Por isso o pedido é arredondado para o múltiplo mais próximo, e
        quem quiser o número exato lê `lado_px`.
        """
        casas = 8 + (2 * self.margem / 100 if self.com_faixa else 0)
        return max(8, round(self.tamanho / casas))

    @property
    def faixa_px(self) -> int:
        """A faixa em pixel, derivada da casa. Zero quando não há o que desenhar nela."""
        return round(self.casa_px * self.margem / 100) if self.com_faixa else 0

    @property
    def lado_px(self) -> int:
        """O lado que o arquivo PNG **realmente** vai ter. Difere do pedido por até quatro pixels."""
        return 8 * self.casa_px + 2 * self.faixa_px

    @property
    def faixa_svg(self) -> int:
        """A mesma faixa em unidades do `viewBox` do SVG, que tem a casa de `diagrama_svg.CASA`."""
        return round(CASA * self.margem / 100) if self.com_faixa else 0

    @property
    def lado_a_jogar(self) -> str | None:
        """O que passar aos desenhistas: `None` é "o que a FEN disser", `""` é "sem plaqueta"."""
        return None if self.plaqueta else ""

    @property
    def engrossar(self) -> bool:
        """Se o traço da peça é engrossado depois de reduzir. Só o PNG desenha peça de arquivo."""
        return conjuntos.registrado(self.conjunto).engrossa and self.formato == PNG

    @property
    def pasta_do_conjunto(self) -> Path | None:
        """A pasta de onde vêm as peças, ou `None` para a do pacote. Só o conjunto do usuário a tem."""
        if conjuntos.registrado(self.conjunto).do_usuario and self.pasta_de_pecas:
            return Path(self.pasta_de_pecas)
        return None


# ------------------------------------------------------------------------------ o item

@dataclass(frozen=True)
class ItemDoLote:
    """Um diagrama do lote, com a procedência que o nomeia.

    Os três números são **1-based** -- é como a pessoa lê a página do livro, e é como os headers
    `Page` e `Diagram` do PGN já saem (`estudo.Ancora`). Zero quer dizer "esta origem não tem".
    """

    fen: str
    livro: str = ""
    """O nome do livro ou do arquivo de origem, já sem pasta e sem extensão."""

    pagina: int = 0
    diagrama: int = 0
    exercicio: int = 0
    """A partida ou o exercício dentro da origem, quando ela tem mais de um."""

    titulo: str = ""
    """A legenda ou o cabeçalho, para o `<title>` do SVG e para a frase da tela. Não nomeia arquivo:
    um cabeçalho de partida tem vírgula, ponto e o nome de duas pessoas."""

    virado: bool = False


class DiagramaLido(Protocol):
    """O mínimo que `da_galeria` usa de uma entrada da galeria (`gallery_scan.GalleryEntry`).

    Existe para este módulo **não importar** `gallery_scan.py`: aquele arquivo abre o PDF e carrega
    o classificador, e uma decisão pura que só precisa de quatro campos não pode arrastar o `torch`
    para dentro de si. É a mesma razão de `estudo_partidas.Loja`.

    Os cinco são **propriedades e não atributos**, e a diferença não é estilo: um atributo de
    `Protocol` exige que o campo seja gravável, e `GalleryEntry` é congelada. Declarado assim, o
    protocolo pede o que este módulo faz -- ler -- e nada além.
    """

    @property
    def page_index(self) -> int: ...

    @property
    def diagram_index(self) -> int: ...

    @property
    def placement(self) -> str: ...

    @property
    def side_to_move(self) -> str: ...

    @property
    def caption(self) -> str: ...


def do_estudo(estudo: Estudo) -> tuple[ItemDoLote, ...]:
    """Os diagramas de um estudo: o da raiz e os que o autor pediu com `[%D]`.

    **A regra é a de `estudo_paragrafos`, e não uma segunda**: o lote solto e o capítulo do EPUB
    mostram os mesmos diagramas do mesmo estudo, ou o livro montado com estes arquivos discordaria
    do livro exportado pelo programa.
    """
    ancora = estudo.ancora
    livro = Path(ancora.nome_do_livro).stem if ancora.valida else ""
    titulo = titulo_do_estudo(estudo)
    return tuple(
        ItemDoLote(
            fen=paragrafo.fen,
            livro=livro,
            pagina=ancora.pagina + 1 if ancora.valida else 0,
            diagrama=paragrafo.numero,
            titulo=titulo,
            virado=paragrafo.virado,
        )
        for paragrafo in paragrafos(estudo)
        if paragrafo.tipo == DIAGRAMA
    )


def de_estudos(estudos: Sequence[Estudo], *, origem: str = "") -> tuple[ItemDoLote, ...]:
    """Os diagramas de vários estudos -- um PGN inteiro, ou a sala de um livro.

    `origem` é o nome do arquivo de onde eles vieram, e vira o `livro` de quem não tem âncora: um
    PGN colado não pertence a livro nenhum, e sem isso quinhentas partidas produziriam quinhentos
    arquivos chamados `diagrama_1`. O número do exercício é a **ordem na origem**, e não o índice
    da partida no arquivo: quem abre a pasta conta de um.
    """
    saida: list[ItemDoLote] = []
    for ordem, estudo in enumerate(estudos, start=1):
        for item in do_estudo(estudo):
            saida.append(
                ItemDoLote(
                    fen=item.fen,
                    livro=item.livro or _limpo(origem),
                    pagina=item.pagina,
                    diagrama=item.diagrama,
                    exercicio=ordem,
                    titulo=item.titulo,
                    virado=item.virado,
                )
            )
    return tuple(saida)


def da_galeria(entradas: Iterable[DiagramaLido], *, livro: str) -> tuple[ItemDoLote, ...]:
    """Os diagramas que a varredura de um livro achou (`gallery_scan.GalleryIndex.entries`).

    A FEN sai do `placement` mais o lado a jogar que a S-17 deduziu -- os outros campos são de
    partida, e um diagrama de livro não tem roque nem contagem de lances declarados. A legenda vira
    `titulo`, e não nome de arquivo: legenda de livro tem ponto, dois-pontos e barra.
    """
    return tuple(
        ItemDoLote(
            fen=f"{entrada.placement} {entrada.side_to_move or 'w'} - - 0 1",
            livro=_limpo(livro),
            pagina=entrada.page_index + 1,
            diagrama=entrada.diagram_index + 1,
            titulo=entrada.caption,
        )
        for entrada in entradas
    )


# ------------------------------------------------------------------------- o nome do arquivo

_ILEGAIS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
"""O que o Windows recusa num nome de arquivo, mais os caracteres de controle. É o conjunto mais
estreito dos três sistemas: o que passa aqui passa no macOS e no Linux."""

_SOBRAS = re.compile(r"[^A-Za-z0-9]+")
"""Tudo o que não é letra sem acento nem dígito vira um traço. Ver `_limpo`."""

_RESERVADOS = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))}
)
"""Os nomes de dispositivo do MS-DOS que o Windows ainda recusa como nome de arquivo -- `CON.png`
não é criável, e nem com outra extensão. Um livro chamado `Aux.pdf` existe."""


def _limpo(texto: str) -> str:
    """O texto como pedaço de nome de arquivo: sem acento, sem símbolo, sem espaço, sem repetição.

    **Sem acento de propósito, e não por medo do sistema de arquivos.** Windows, macOS e Linux
    guardam `Prokeš.png` sem reclamar. Quem reclama é o outro lado: o lote existe para ser
    consumido por um programa de diagramação, e caminho com acento ainda quebra em `\\includegraphics`
    do LaTeX, em script de linha de comando e em `.zip` aberto noutra máquina. A decomposição
    Unicode tira a marca e mantém a letra -- `Prokeš` vira `Prokes`, que ainda é o nome do sujeito.
    """
    sem_ilegal = _ILEGAIS.sub("-", str(texto or ""))
    decomposto = unicodedata.normalize("NFKD", sem_ilegal)
    sem_acento = "".join(letra for letra in decomposto if not unicodedata.combining(letra))
    return _SOBRAS.sub("-", sem_acento).strip("-")


def _nome_bruto(item: ItemDoLote, *, larguras: dict[str, int]) -> str:
    """O nome daquele item antes de resolver colisão. Ver `nomes_do_lote`."""
    partes: list[str] = []
    livro = _limpo(item.livro)[:LIMITE_DO_NOME].strip("-")
    if livro:
        partes.append(livro)
    for prefixo, valor in (("ex", item.exercicio), ("p", item.pagina), ("d", item.diagrama)):
        if valor > 0:
            partes.append(f"{prefixo}{valor:0{larguras[prefixo]}d}")
    if not partes:
        partes.append(_limpo(item.titulo)[:LIMITE_DO_NOME].strip("-") or "diagrama")
    nome = "_".join(partes)
    if nome.lower() in _RESERVADOS:
        nome = f"{nome}-1"
    return nome


def nomes_do_lote(itens: Sequence[ItemDoLote], formato: str = PNG) -> tuple[str, ...]:
    """O nome de arquivo de cada item, com extensão, na ordem em que eles chegaram.

    **Três decisões, e as três vieram de defeito real e não de precaução:**

    - *Zero à esquerda, com a largura do maior número do lote.* `ex1` e `ex10` num gerenciador de
      arquivos aparecem nesta ordem: 1, 10, 100, 11. Um editor que arrasta 500 diagramas para
      dentro da diagramação na ordem em que os vê põe o exercício 100 entre o 10 e o 11.
    - *Colisão resolvida por sufixo, e comparada sem maiúscula.* Dois diagramas da mesma página de
      livros de mesmo nome, ou `Prokeš` e `Prokes` no mesmo lote, dariam o mesmo nome -- e no
      Windows e no macOS `A.png` e `a.png` são **o mesmo arquivo**: o segundo apaga o primeiro em
      silêncio, que é a pior forma de perder trabalho de meia hora.
    - *A extensão vem do formato registrado*, e não de quem chama.
    """
    extensao = formato_registrado(formato).extensao
    larguras = {
        "ex": len(str(max((item.exercicio for item in itens), default=0))),
        "p": len(str(max((item.pagina for item in itens), default=0))),
        "d": len(str(max((item.diagrama for item in itens), default=0))),
    }
    vistos: set[str] = set()
    saida: list[str] = []
    for item in itens:
        base = _nome_bruto(item, larguras=larguras)
        nome, repetido = base, 1
        while nome.casefold() in vistos:
            repetido += 1
            nome = f"{base}-{repetido}"
        vistos.add(nome.casefold())
        saida.append(f"{nome}{extensao}")
    return tuple(saida)


def frase_do_lote(itens: Sequence[ItemDoLote], opcoes: Opcoes) -> str:
    """O que vai sair, numa linha, antes de sair. É o que a janela mostra acima do botão.

    Diz o **lado real** e não o pedido: o arredondamento para múltiplo de oito é invisível, e uma
    tela que prometesse 800 e entregasse 792 estaria mentindo sobre o único número que quem
    diagrama vai conferir.
    """
    if not itens:
        return "Nenhum diagrama nesta origem."
    registro = formato_registrado(opcoes.formato)
    medida = (
        f"{opcoes.tamanho} pixels, vetorial"
        if registro.vetor
        else f"{opcoes.lado_px} × {opcoes.lado_px} pixels"
    )
    return f"{len(itens)} diagrama(s) em {registro.rotulo}, {medida}, pele {pele_registrada(opcoes.pele).rotulo}."
