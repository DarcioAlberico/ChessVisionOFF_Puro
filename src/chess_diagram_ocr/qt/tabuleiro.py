"""O tabuleiro desenhado com `QPainter`, a partir do campo de peças da FEN.

**O que é reusado e o que não.** As cores, a geometria e a rampa de calor são as mesmas do
produto -- `ui/tokens.py` e `ui/desenho_do_tabuleiro.py`, os dois sem toolkit de propósito -- e as
peças são os mesmos PNGs de `assets/piece_images/`. O que este módulo escreve do zero é o desenho,
e só ele.

**O achado deste arquivo foi fechado na S-501, e vale registrar o que ele era.** Até então o
cabeçalho dizia:

    `ui/board_render.py` tem duas coisas que este arquivo gostaria: `BoardGeometry.fit` e
    `heatmap_color`. As duas são cálculo puro -- e mesmo assim não dá para importá-las, porque o
    módulo em que moram importa `tkinter` e `PIL` na primeira linha. É o único ponto do fluxo em
    que o segundo frontend teve de repetir uma decisão em vez de chamá-la, e é por isso que a
    incerteza aqui aparece como **contorno** na casa e não como calor.

As duas mudaram para `ui/desenho_do_tabuleiro.py`, que não importa nem um nem outro, e este
arquivo passou a chamá-las. A incerteza voltou a ser calor, `UNICODE_PIECES` deixou de existir em
duas cópias, e o enquadramento é o mesmo `BoardGeometry.fit` que o produto usa -- o que significa
que o tabuleiro das duas janelas, na mesma área, tem o mesmo tamanho e a mesma origem.

**A tinta da incerteza tem alfa aqui, e não `stipple`.** O `BoardRenderer` do Tk pinta a casa
quente com `stipple="gray50"` e explica por quê: *"é o único jeito de tingir sem apagar a casa no
canvas do Tk, que não tem canal alfa"*. O Qt tem, então a mesma decisão -- tingir sem esconder a
peça -- é cumprida com meia opacidade de verdade, e não com uma trama de pixels alternados.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, cast

from PIL import Image
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPaintEvent, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from chess_diagram_ocr.config import BUNDLE_ROOT, IDX_TO_CLASS, UNCERTAIN_SQUARE_THRESHOLD
from chess_diagram_ocr.fen_utils import labels_from_fen
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import conjuntos, degradacao, tokens
from chess_diagram_ocr.ui.desenho_do_tabuleiro import (
    COORD_FONT,
    COORD_OFFSET_PX,
    UNICODE_PIECES,
    BoardGeometry,
    heatmap_color,
    margem_de_coordenada,
    reguas,
)
from chess_diagram_ocr.ui.pecas import engrossar_traco

logger = logging.getLogger(__name__)

PASTA_DE_PECAS = BUNDLE_ROOT / "assets" / "piece_images"
"""Os mesmos PNGs do produto. `BUNDLE_ROOT` e não `PROJECT_ROOT` porque peça é recurso
somente-leitura que viaja dentro do pacote -- a distinção é da S-55."""

LADO_MINIMO = 240
MAX_DO_TABULEIRO = 560
"""O piso e o teto do tabuleiro, em pixel. **São os do produto** (`ui/board_widget.py`).

Eram 220 e teto nenhum. Alinhar não é zelo: os dois entram em `BoardGeometry.fit`, e com números
diferentes a mesma posição na mesma área desenharia um tabuleiro de tamanho diferente em cada
janela -- o que faz "comparar as duas telas lado a lado" deixar de responder, que é justamente
para o que a versão de teste existe."""

MARGEM = margem_de_coordenada()
"""A folga em volta: o que as coordenadas precisam para caberem inteiras (S-508).

**Era `8`**, com o comentário *"é o mesmo `margin` que `board_widget` passa quando não desenha
coordenadas -- e este tabuleiro não desenha"*. Ele passou a desenhar, e o número deixou de ser
escolhido aqui: sai de `margem_de_coordenada()`, que é a mesma função dos dois lados e que carrega
a medição de por que `28` cortava a base de "a b c d e f g h" (S-155).

A conta é `2 x (deslocamento + meia altura da fonte)`, e `BoardGeometry.fit` a divide entre os dois
lados -- então o que sobra de cada lado é metade disto."""

GLIFOS = UNICODE_PIECES
"""O desenho de reserva, quando o PNG da peça não está no disco.

Existe porque `assets/piece_images/` **não** é obrigatório: um checkout sem os artefatos de
dados abre a janela, e um tabuleiro em branco não diria se o que faltou foi a leitura ou a
imagem. O glifo Unicode responde essa pergunta sem depender de arquivo nenhum.

**É `desenho_do_tabuleiro.UNICODE_PIECES`, e não uma tabela própria** (S-501). Era uma cópia byte
a byte da de lá -- doze pares iguais, mantidos em dois lugares. O nome fica como apelido porque é
por ele que este módulo e o teste se referem à tabela."""

TINTA_DA_INCERTEZA = 128
"""Quanto da tinta quente cobre a casa, de 0 a 255. Meia opacidade.

É o `stipple="gray50"` do `BoardRenderer` dito com o canal alfa que o Tk não tem: metade da tinta,
para a peça por baixo continuar legível. Ver o cabeçalho."""


def arquivo_da_peca(classe: str) -> str:
    """`"P"` -> `"wp"`, `"n"` -> `"bn"`. O nome do PNG, que é cor + tipo em minúscula."""
    return ("w" if classe.isupper() else "b") + classe.lower()


def carregar_pecas(pasta: Path = PASTA_DE_PECAS) -> dict[str, QPixmap]:
    """As doze peças, lidas uma vez. Ausente sai de fora do dicionário, e não vazia.

    Um `QPixmap` nulo desenha nada e não levanta: se ele entrasse aqui, o tabuleiro ficaria
    vazio sem que ninguém pudesse dizer por quê. Fora do dicionário, o desenho cai no glifo.

    **E a queda avisa, uma vez** -- é a linha `pasta_de_pecas` de `degradacao.QUEDAS`, que apontava
    para o `PieceImages` do Tk e ficou sem dono no corte; aqui a pasta ausente caía no glifo em
    silêncio, que é a metade do contrato que a tabela proíbe (S-511).
    """
    imagens: dict[str, QPixmap] = {}
    for classe in GLIFOS:
        caminho = Path(pasta) / f"{arquivo_da_peca(classe)}.png"
        if not caminho.exists():
            continue
        mapa = QPixmap(str(caminho))
        if not mapa.isNull():
            imagens[classe] = mapa
    faltando = [classe for classe in GLIFOS if classe not in imagens]
    if faltando:
        degradacao.avisar_uma_vez(
            logger,
            ("pasta_de_pecas", str(pasta)),
            "Pasta de peças %s sem %d das %d imagens (%s): as ausentes saem como glifo.",
            pasta,
            len(faltando),
            len(GLIFOS),
            " ".join(faltando),
        )
    return imagens


def engrossada(mapa: QPixmap, lado: int) -> QPixmap:
    """A peça reduzida ao tamanho de exibição e com o traço engrossado (S-230).

    **Nesta ordem, e a ordem é o item.** Engrossar na fonte e reduzir depois perde a linha na
    mesma redução que ela existe para compensar -- está escrito em `ui/pecas.engrossar_traco`, e é
    por isso que esta função recebe o lado da casa em vez de devolver um desenho e deixar o
    `QPainter` reduzir.

    Devolve o mapa **como veio** quando a conversão falha: um conjunto de peças não pode custar o
    tabuleiro, e o desenho sem o traço grosso continua sendo o desenho certo.
    """
    reduzida = mapa.scaled(
        lado, lado, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    try:
        imagem = reduzida.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        bytes_por_linha = imagem.bytesPerLine()
        bruto = imagem.constBits()
        if bruto is None:
            return mapa
        bruto.setsize(imagem.height() * bytes_por_linha)
        # `cast` porque o `sip.voidptr` do PyQt não se declara como buffer, embora seja um: sem
        # ele o `mypy` recusa o `bytes(...)` que o Qt documenta como a forma de ler os pixels.
        origem = Image.frombytes(
            "RGBA",
            (imagem.width(), imagem.height()),
            bytes(cast(Any, bruto)),
            "raw",
            "RGBA",
            bytes_por_linha,
        )
        grossa = engrossar_traco(origem)
        saida = QImage(
            grossa.tobytes("raw", "RGBA"),
            grossa.width,
            grossa.height,
            QImage.Format.Format_RGBA8888,
        ).copy()
        return QPixmap.fromImage(saida)
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.info("Traço não engrossado (%s): a peça é desenhada como veio.", exc)
        return mapa


# ------------------------------------------------------------- o conjunto de peças (S-230/S-506)
#
# **Estado de módulo, e é o mesmo desenho de `qt/tema.py`.** O conjunto é um eixo de aparência da
# janela inteira, não uma propriedade de um tabuleiro: há dois na tela (o da aba Resultado e o da
# sala de estudo), e passar o nome pela construção de cada um faria "trocar de conjunto" ser uma
# chamada por tabuleiro -- que é como se esquece o segundo.

_CONJUNTO = conjuntos.PADRAO
_PASTA_DO_USUARIO = ""
_TABULEIROS: list[Callable[[], object]] = []
"""Quem recarrega quando o conjunto muda. Ver `_recarregar_todos`."""


def conjunto_em_vigor() -> str:
    """O nome do conjunto que os tabuleiros estão desenhando agora."""
    return _CONJUNTO


def pasta_do_conjunto(nome: str = "", pasta_do_usuario: str = "") -> Path:
    """De que pasta saem os PNGs daquele conjunto.

    Só o conjunto `pasta` sai de outro lugar; `padrao` e `traco` leem os mesmos doze arquivos de
    `assets/`, e a diferença entre os dois é o que se faz com eles depois de reduzir.

    Pasta do usuário vazia cai no padrão em vez de recusar: `conjuntos.PASTA` declara que pasta
    incompleta **avisa e usa o que houver**, e uma pasta que nem foi escolhida é o caso extremo
    disso -- o desenho cai no glifo Unicode, peça a peça, que é o que já acontece num checkout sem
    `assets/`.
    """
    registro = conjuntos.registrado(conjuntos.valida(nome or _CONJUNTO))
    escolhida = str(pasta_do_usuario or _PASTA_DO_USUARIO).strip()
    if registro.do_usuario and escolhida:
        return Path(escolhida)
    return PASTA_DE_PECAS


def definir_conjunto(nome: str, pasta_do_usuario: str = "") -> str:
    """Troca o conjunto de peças de **todos** os tabuleiros vivos. Devolve o que ficou valendo.

    `conjuntos.valida` e não `registrado`: o nome vem do disco ou do ambiente, e nem estado antigo
    nem variável escrita errada podem impedir a janela de abrir -- ela nomeia o inválido no log e
    cai no padrão.

    **Avisa a pasta incompleta uma vez, com os nomes.** "Faltam wq e bk" diz o que copiar para lá;
    "a pasta está incompleta" manda a pessoa conferir doze arquivos.
    """
    global _CONJUNTO, _PASTA_DO_USUARIO
    _CONJUNTO = conjuntos.valida(nome)
    _PASTA_DO_USUARIO = str(pasta_do_usuario or "").strip()
    if conjuntos.registrado(_CONJUNTO).do_usuario and _PASTA_DO_USUARIO:
        if faltam := conjuntos.ausentes(_PASTA_DO_USUARIO):
            logger.warning(
                "Pasta de peças incompleta (%s): faltam %s. O glifo Unicode desenha as ausentes.",
                _PASTA_DO_USUARIO,
                ", ".join(faltam),
            )
    _recarregar_todos()
    return _CONJUNTO


def ao_trocar_de_conjunto(recarregar: Callable[[], object]) -> None:
    """Registra um tabuleiro para ser recarregado na troca. Ver `qt/tema.ao_repintar`."""
    _TABULEIROS.append(recarregar)


def _recarregar_todos() -> None:
    """Recarrega quem está vivo e **esquece quem morreu**, como a repintura do tema.

    Um tabuleiro destruído entre o registro e a troca não é erro: é a janela de antes. No Qt o
    sintoma de tocá-lo é `RuntimeError: wrapped C/C++ object ... has been deleted`, e ele sai da
    lista em vez de derrubar a recarga dos outros.
    """
    vivos: list[Callable[[], object]] = []
    for recarregar in _TABULEIROS:
        try:
            recarregar()
        except RuntimeError:
            continue
        vivos.append(recarregar)
    _TABULEIROS[:] = vivos


class TabuleiroQt(QWidget):
    """Um tabuleiro somente-leitura: mostra o que o modelo leu, e não deixa editar.

    **Somente-leitura de propósito.** Editar casa a casa é o que a aba Resultado do produto
    faz, e ela grava amostra no `labels.csv` -- trabalho humano, com desfazer, quarentena e
    procedência. Uma segunda tela que escrevesse no mesmo arquivo não seria uma versão de
    teste: seria um segundo caminho de escrita sobre o dado que o projeto mais protege.
    """

    def __init__(self, parent: QWidget | None = None, *, pasta_de_pecas: Path | None = None) -> None:
        super().__init__(parent)
        self._pasta_pinada = Path(pasta_de_pecas) if pasta_de_pecas is not None else None
        """Uma pasta cravada por quem construiu. `None` segue o conjunto em vigor (S-230).

        Existe para o teste poder montar um tabuleiro sobre uma pasta que ele controla -- inclusive
        uma que não existe, que é como se afirma a queda para o glifo Unicode."""
        self._no_tamanho: dict[str, QPixmap] = {}
        self._lado_em_cache = 0
        """As peças já preparadas para o lado de casa de agora, e qual é esse lado.

        **Uma geração por tamanho, e não um cache que cresce.** Todas as 64 casas de um desenho têm
        o mesmo lado, então redimensionar a janela troca a geração inteira de uma vez -- guardar as
        anteriores seria guardar tamanhos que ninguém vai desenhar de novo."""
        self._pecas: dict[str, QPixmap] = {}
        self._recarregar_pecas()
        ao_trocar_de_conjunto(self._recarregar_pecas)
        self._classes: list[str] = ["empty"] * 64
        self._incertas: set[int] = set()
        self._heatmap = True
        """O mapa de incerteza esta ligado? (S-21)

        Ligado por padrao porque e como se descobre que ele existe. Quem trabalha com uma
        pagina de diagramas ja conferidos o desliga, e essa escolha sobrevive ao fechamento --
        `AppState.show_heatmap`."""
        self._confiancas: dict[int, float] = {}
        self._limiar = UNCERTAIN_SQUARE_THRESHOLD
        self._virado = False
        self._fracao = 0.0
        """Fração do widget que o tabuleiro pode ocupar; `0.0` usa `MAX_DO_TABULEIRO` (S-518)."""
        self._ultimo_lance: frozenset[int] = frozenset()
        """As casas do lance que chegou a esta posição, em índice de leitura (S-509).

        **Índice, e não `chess.Move`**: quem sabe traduzir um lance em duas casas é
        `BoardModel.last_move_squares`, que é puro; esta classe não conhece `chess` e não vai
        passar a conhecer por causa de uma marcação. Vazio na raiz, que é a posição que não veio
        de lance nenhum."""
        self.setMinimumSize(LADO_MINIMO, LADO_MINIMO)

    def _recarregar_pecas(self) -> None:
        """Relê os doze PNGs do conjunto em vigor e joga fora o que estava preparado."""
        self._pecas = carregar_pecas(
            self._pasta_pinada if self._pasta_pinada is not None else pasta_do_conjunto()
        )
        self._no_tamanho.clear()
        self._lado_em_cache = 0
        self.update()

    def _preparada(self, classe: str, mapa: QPixmap, lado: int) -> QPixmap:
        """A peça pronta para desenhar naquela casa, engrossada se o conjunto pedir.

        **O conjunto padrão sai por aqui sem passar por nada**, e é de propósito: ele é o desenho
        de sempre, e mandá-lo pelo caminho do redimensionamento trocaria o pixel de quem nunca
        escolheu conjunto nenhum -- que é justamente o que a S-230 promete não fazer.
        """
        if not conjuntos.registrado(conjunto_em_vigor()).engrossa:
            return mapa
        if self._lado_em_cache != lado:
            self._no_tamanho.clear()
            self._lado_em_cache = lado
        pronta = self._no_tamanho.get(classe)
        if pronta is None:
            pronta = engrossada(mapa, lado)
            self._no_tamanho[classe] = pronta
        return pronta

    # ------------------------------------------------------------------------------ estado

    def mostrar(
        self,
        placement: str,
        *,
        incertas: Sequence[int] = (),
        confiancas: Sequence[float] = (),
        limiar: float = UNCERTAIN_SQUARE_THRESHOLD,
        virado: bool = False,
    ) -> None:
        """Desenha um campo de peças. FEN inválida **levanta**, e não vira tabuleiro vazio.

        É a mesma decisão da S-361 em `labels_from_fen`, e pelo mesmo motivo: uma leitura ruim
        que vira 64 casas vazias é indistinguível de uma posição sem peças, e quem olha a tela
        conclui que o modelo não achou nada quando o que houve foi um caractere que ninguém
        soube ler.

        **`incertas` diz *quais* casas, `confiancas` diz *quão* quentes** -- e as duas são
        separadas porque quem chama já tem a primeira pronta (`RecognizedDiagram.uncertain_squares`)
        e nem sempre tem a segunda. Sem confiança, a casa marcada sai na cor do **limiar**, que é
        o topo da rampa: dizer "esta casa é duvidosa" sem inventar o quanto.
        """
        self._classes = [IDX_TO_CLASS[indice] for indice in labels_from_fen(placement)]
        self._incertas = {int(casa) for casa in incertas if 0 <= int(casa) < 64}
        self._limiar = float(limiar)
        self._confiancas = {
            casa: float(valor)
            for casa, valor in enumerate(confiancas)
            if casa in self._incertas
        }
        self._virado = bool(virado)
        self.update()

    def limpar(self) -> None:
        self._classes = ["empty"] * 64
        self._incertas = set()
        self._confiancas = {}
        self.update()

    @property
    def virado(self) -> bool:
        return self._virado

    def definir_heatmap(self, ligado: bool) -> None:
        """Liga ou desliga a tinta de incerteza. O que ela cobre continua sabido (S-21).

        **Desliga o desenho e não a medição**: `casas_incertas` continua respondendo, e é o que
        permite religá-lo sem reler a página. É o `set_heatmap_enabled` do outro frontend.
        """
        if self._heatmap == bool(ligado):
            return
        self._heatmap = bool(ligado)
        self.update()

    def casas_incertas(self) -> tuple[int, ...]:
        """As casas marcadas, em ordem de leitura. Existe para o teste afirmar o que a tela diz."""
        return tuple(sorted(self._incertas))

    # ------------------------------------------------------------------------------ desenho

    def _indice_de_leitura(self, linha: int, coluna: int) -> int:
        """Da posição na tela para o índice em ordem de leitura (0 = a8), respeitando o giro."""
        return (7 - linha) * 8 + (7 - coluna) if self._virado else linha * 8 + coluna

    def _classe_da_casa(self, indice: int) -> str:
        """Que peça desenhar naquela casa. **Gancho, e é para isso que ele existe.**

        A subclasse que edita precisa esconder a peça que está sendo arrastada -- ela aparece
        sob o ponteiro, e desenhá-la também na casa de origem a mostraria duas vezes. Sem este
        método, a única saída seria trocar `self._classes` antes de pintar e repor depois, que
        é estado temporário num atributo que o resto da classe lê como se fosse permanente.
        """
        return self._classes[indice]

    def definir_ultimo_lance(self, casas: Iterable[int] = ()) -> None:
        """As casas do último lance, em índice de leitura. Sem argumento, apaga a marca (S-509)."""
        novas = frozenset(int(casa) for casa in casas)
        if novas == self._ultimo_lance:
            return
        self._ultimo_lance = novas
        self.update()

    def esteira(self) -> QRectF:
        """O retângulo em que a esteira é pintada: o tabuleiro mais a margem da coordenada (S-507).

        **A esteira tem fim, e é este item.** Antes ela era o fundo do widget, e tudo o que não
        fosse tabuleiro virava quase-preto -- medido em 41,5% da área num painel de 685x782. É o
        mesmo defeito que a S-449 mediu e consertou no outro frontend em 2026-08-30, um dia antes
        de este arquivo entrar na árvore sem a correção.

        A folga sai de `MARGEM`, que sai de `margem_de_coordenada()`: a esteira é exatamente o que
        a coordenada precisa, porque é **sobre ela** que a coordenada é desenhada -- é o que dá
        11,03:1 à letra, e a razão de a S-147 tê-la escolhido escura.
        """
        geo = self.geometria()
        folga = MARGEM / 2
        return QRectF(
            geo.origin_x - folga,
            geo.origin_y - folga,
            geo.size + MARGEM,
            geo.size + MARGEM,
        ).intersected(QRectF(self.rect()))

    def heightForWidth(self, a0: int) -> int:  # noqa: N802 - assinatura do Qt
        """A altura que o widget quer para aquela largura: a mesma, porque o tabuleiro é quadrado.

        **Só vale para quem pedir** (S-517): o leiaute só consulta este método quando a política de
        tamanho do widget declara `setHeightForWidth(True)`, e quem declara é a sala de estudo. Sem
        isso, o widget fica com toda a altura sobrando da coluna e o tabuleiro flutua no meio dela
        -- o que punha ~100 px de vazio entre o tabuleiro e a faixa de navegação que deveria estar
        colada nele.

        A aba Resultado **não** declara, e continua com o arranjo de sempre: ali o tabuleiro divide
        a coluna com a lista de casas e a legenda, e amarrar a altura à largura mexeria nas três.
        """
        return int(a0)

    def definir_fracao(self, fracao: float) -> None:
        """Que fração do lado menor do widget o tabuleiro pode ocupar. `0.0` volta ao teto fixo.

        **É o teto virando argumento** (S-518). `MAX_DO_TABULEIRO` é herança do canvas de tamanho
        fixo do Tk, e ele vale para os dois tabuleiros: na aba Resultado está certo -- ali o
        tabuleiro divide a coluna com a lista de casas e a legenda, e crescer tira espaço de quem
        corrige. Na sala de estudo, não: o tabuleiro **é** a coluna, e parar em 560 px numa janela
        grande deixava o resto virar vazio.

        Fração e não pixel, pela mesma razão de `AppState.pdf_zoom` ser fração: o número que se
        guarda tem de valer no monitor de quem o guardou e no do dia seguinte.
        """
        novo = max(0.0, float(fracao))
        if novo == self._fracao:
            return
        self._fracao = novo
        self.update()

    def geometria(self) -> BoardGeometry:
        """Onde o tabuleiro está dentro do widget. **A mesma conta do produto** (S-155/S-501).

        Pública porque quem precisa dela não é só o `paintEvent`: o teste que amostra a cor de uma
        casa precisa saber onde a casa está, e recalculá-la do lado de fora é como se escreve um
        teste que continua passando depois de o enquadramento mudar.
        """
        teto = MAX_DO_TABULEIRO
        if self._fracao > 0:
            teto = max(LADO_MINIMO, int(min(self.width(), self.height()) * self._fracao))
        return BoardGeometry.fit(
            self.width(),
            self.height(),
            min_size=LADO_MINIMO,
            max_size=teto,
            margin=MARGEM,
        )

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """**Duas superfícies, e não uma** (S-507): o vazio enche o widget, a esteira tem tamanho.

        A ordem das camadas é a leitura: casa, marca do último lance, peça, incerteza. O último
        lance vai **debaixo** da peça porque é fato sobre a posição e não anotação humana -- é a
        mesma regra que põe as setas por cima de tudo em `tabuleiro_de_jogo.paintEvent`.
        """
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pintor.fillRect(self.rect(), QColor(tema.cor_atual(tokens.VAZIO_DE_CANVAS)))
        pintor.fillRect(self.esteira(), QColor(tema.cor_atual(tokens.SUPERFICIE_TABULEIRO)))

        geo = self.geometria()
        clara = QColor(tema.cor_atual(tokens.CASA_CLARA))
        escura = QColor(tema.cor_atual(tokens.CASA_ESCURA))
        ultimo = QColor(tema.cor_atual(tokens.CASA_ULTIMO_LANCE))
        for linha in range(8):
            for coluna in range(8):
                x0, y0, x1, y1 = geo.rect(linha, coluna)
                retangulo = QRectF(x0, y0, x1 - x0, y1 - y0)
                indice = self._indice_de_leitura(linha, coluna)
                pintor.fillRect(retangulo, clara if (linha + coluna) % 2 == 0 else escura)
                if indice in self._ultimo_lance:
                    pintor.fillRect(retangulo, ultimo)
                self._desenhar_peca(pintor, retangulo, self._classe_da_casa(indice))
                self._desenhar_incerteza(pintor, retangulo, indice)

        self._desenhar_coordenadas(pintor, geo)
        pintor.end()

    def _desenhar_coordenadas(self, pintor: QPainter, geo: BoardGeometry) -> None:
        """As letras a–h e os números 8–1, na margem que `MARGEM` reservou (S-508).

        **A cor é resolvida contra a esteira**, e não contra o fundo do widget. É a S-146 com a
        correção que a S-449 precisou fazer: quem desenha resolve contra o que está *debaixo* do
        que ele desenha, e desde que a esteira virou um retângulo o fundo do widget é o vazio --
        claro na pele clássica. Resolver contra ele daria letra escura sobre esteira escura.

        A ordem acompanha a virada: com as pretas embaixo, `a` fica à direita e `1` no topo.
        """
        fonte = QFont(COORD_FONT[0], COORD_FONT[1])
        fonte.setBold(COORD_FONT[2] == "bold")
        pintor.setFont(fonte)
        pintor.setPen(QPen(QColor(tokens.sobre_superficie(tema.cor_atual(tokens.SUPERFICIE_TABULEIRO)))))

        colunas, linhas = reguas(self._virado)
        lado = 2 * COORD_OFFSET_PX
        for indice, letra in enumerate(colunas):
            centro = QRectF(
                geo.origin_x + indice * geo.cell + geo.cell / 2 - lado / 2,
                geo.origin_y + geo.size + COORD_OFFSET_PX - lado / 2,
                lado,
                lado,
            )
            pintor.drawText(centro, int(Qt.AlignmentFlag.AlignCenter), letra)
        for indice, numero in enumerate(linhas):
            centro = QRectF(
                geo.origin_x - COORD_OFFSET_PX - lado / 2,
                geo.origin_y + indice * geo.cell + geo.cell / 2 - lado / 2,
                lado,
                lado,
            )
            pintor.drawText(centro, int(Qt.AlignmentFlag.AlignCenter), numero)

    def _desenhar_peca(self, pintor: QPainter, casa: QRectF, classe: str) -> None:
        if classe == "empty":
            return
        mapa = self._pecas.get(classe)
        if mapa is not None:
            pintor.drawPixmap(casa.toRect(), self._preparada(classe, mapa, max(1, int(casa.width()))))
            return
        fonte = QFont(pintor.font())
        fonte.setPointSizeF(max(6.0, casa.height() * 0.72))
        pintor.setFont(fonte)
        # **A tinta do glifo vem do tema, e não da reserva** (S-511). Eram os apelidos
        # `GLIFO_ESCURO`/`GLIFO_CLARO` de `desenho_do_tabuleiro`, que são o valor de `RESERVA` --
        # o hexadecimal de fábrica, que não acompanha a troca de pele. O papel é o mesmo; o que
        # muda é perguntar ao tema em vez de ler a reserva.
        papel = tokens.GLIFO_ESCURO if classe.islower() else tokens.GLIFO_CLARO
        pintor.setPen(QPen(QColor(tema.cor_atual(papel))))
        pintor.drawText(casa, int(Qt.AlignmentFlag.AlignCenter), GLIFOS[classe])

    def _desenhar_incerteza(self, pintor: QPainter, casa: QRectF, indice: int) -> None:
        """A casa duvidosa tingida com a rampa de calor, e contornada na mesma cor (S-501).

        **É a mesma rampa do produto**, `desenho_do_tabuleiro.heatmap_color`, e não uma segunda
        escala: duas escalas para "quão duvidosa é esta casa" seria o defeito que a S-31 corrigiu
        no pipeline, reintroduzido no desenho.

        A tinta cobre a peça em vez de ficar embaixo, exatamente como o `BoardRenderer` faz -- é
        o que faz a casa quente se ver mesmo quando há uma dama preta nela. O que muda é o meio:
        alfa de verdade no lugar do `stipple`, e o resultado é uma tinta lisa em vez de uma trama.

        Meio pixel de folga no contorno porque a caneta do Qt pinta centrada na linha: sem ela,
        metade do traço cai na casa vizinha, e duas casas quentes lado a lado dividem um contorno.
        """
        if not self._heatmap or indice not in self._incertas:
            return
        # Sem confiança medida, a cor é a do **limiar** -- o topo da rampa. Ver `mostrar`.
        confianca = self._confiancas.get(indice, self._limiar)
        tinta = QColor(heatmap_color(confianca, self._limiar))
        preenchimento = QColor(tinta)
        preenchimento.setAlpha(TINTA_DA_INCERTEZA)
        pintor.fillRect(casa, preenchimento)

        caneta = QPen(tinta)
        caneta.setWidthF(max(2.0, casa.width() * 0.06))
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        folga = caneta.widthF() / 2.0
        pintor.drawRect(casa.adjusted(folga, folga, -folga, -folga))
