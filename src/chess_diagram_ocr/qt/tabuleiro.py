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
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from PIL import Image
from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PyQt6.QtWidgets import QWidget

from chess_diagram_ocr.config import BUNDLE_ROOT, IDX_TO_CLASS, UNCERTAIN_SQUARE_THRESHOLD
from chess_diagram_ocr.fen_utils import labels_from_fen
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import conjuntos, tokens
from chess_diagram_ocr.ui.desenho_do_tabuleiro import (
    GLIFO_CLARO,
    GLIFO_ESCURO,
    UNICODE_PIECES,
    BoardGeometry,
    heatmap_color,
    largura_util_do_canvas,
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

LARGURA_DO_TRACO = 0.022
"""Largura do contorno do glifo, como fração do lado da casa.

2,2 % de uma casa de 70 px são 1,5 px -- grosso o bastante para o traço se ver a 100 % e fino o
bastante para não engordar a letra. Fração e não pixel porque o tabuleiro vai de 240 a 560 px de
lado: um valor cravado sumiria no grande e engoliria o glifo no pequeno."""

MARGEM = 8
"""Folga em volta. É o mesmo `margin` que `board_widget` passa quando não desenha coordenadas --
e este tabuleiro não desenha."""

MAXIMO_DO_QT = 16777215
"""O teto de largura que o Qt trata como "sem teto" (`QWIDGETSIZE_MAX`).

Existe nomeado porque `resizeEvent` **repõe** o teto a cada passada, e ler o teto anterior para
recalculá-lo o faria só encolher: uma janela que volta a crescer nunca devolveria a largura ao
canvas."""

TAPETE_EM_VOLTA = 12
"""Largura do tapete em volta do tabuleiro, em pixel. **É um teto, e ele não existia** (F9-C2).

**O que o crítico do ciclo 1 mediu:** numa janela de 1920×1080, o tapete `#312e2b` ocupava
**10,9 % da janela contra 9,4 % do tabuleiro** -- a esteira escura, que é inerte, era maior que o
objeto que ela existe para assentar, e era a aresta de maior contraste da tela. A causa é uma
linha: `fillRect(self.rect(), SUPERFICIE_TABULEIRO)` pintava o **widget inteiro** de esteira, e o
tabuleiro parava em `MAX_DO_TABULEIRO`.

O tapete continua existindo, e pela razão da S-147: ele dá 11,03:1 às coordenadas e assenta o
tabuleiro em vez de deixá-lo flutuar. O que ele deixou de ser é **campo**; ele virou moldura. Doze
pixels são uma faixa que se vê e que não compete com nada -- e o resto do widget volta a ser a
superfície do painel, que é o que ele sempre foi por baixo."""

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
    """
    imagens: dict[str, QPixmap] = {}
    for classe in GLIFOS:
        caminho = Path(pasta) / f"{arquivo_da_peca(classe)}.png"
        if not caminho.exists():
            continue
        mapa = QPixmap(str(caminho))
        if not mapa.isNull():
            imagens[classe] = mapa
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

    def resizeEvent(self, a0: QResizeEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """O canvas nunca fica mais largo que alto (F9-C3, item 13).

        Quem decide é `ui/desenho_do_tabuleiro.largura_util_do_canvas`, e o porquê está lá: num
        tabuleiro quadrado e centrado, um canvas mais largo que alto é por construção dois vãos
        vazios -- e o do painel Resultado media 933×559 para desenhar 551, com
        `180×580 = 104,4 kpx a 0,17 % de tinta` entre o tabuleiro e a paleta de peças.

        **Um teto, e não um tamanho fixo**, porque é o teto que o `QHBoxLayout` respeita ao
        repartir a largura: o que sobra sai deste widget e vai para quem estiver ao lado. E ele é
        derivado da **altura**, que o layout horizontal não mexe -- então a passada extra converge
        de primeira, sem oscilar entre duas larguras.
        """
        super().resizeEvent(a0)
        self.setMaximumWidth(largura_util_do_canvas(self.height(), MAXIMO_DO_QT))

    def geometria(self) -> BoardGeometry:
        """Onde o tabuleiro está dentro do widget. **A mesma conta do produto** (S-155/S-501).

        Pública porque quem precisa dela não é só o `paintEvent`: o teste que amostra a cor de uma
        casa precisa saber onde a casa está, e recalculá-la do lado de fora é como se escreve um
        teste que continua passando depois de o enquadramento mudar.
        """
        return BoardGeometry.fit(
            self.width(),
            self.height(),
            min_size=LADO_MINIMO,
            # **O teto acompanha o painel, e deixou de ser absoluto** (F9-C2, §7 item 13). Com
            # `MAX_DO_TABULEIRO` cravado, a sala de estudo dava um tabuleiro de 560 px num canvas
            # de 759 px de altura -- 65 % de ocupação, com o resto virando esteira inerte. O teto
            # continua existindo como **piso do teto**: numa área menor que 560 px quem manda é a
            # área, e é a mesma conta de antes.
            max_size=max(MAX_DO_TABULEIRO, min(self.width(), self.height())),
            margin=MARGEM,
        )

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        geo = self.geometria()
        _pintar_o_tapete(pintor, self.rect(), geo)
        clara = QColor(tema.cor_atual(tokens.CASA_CLARA))
        escura = QColor(tema.cor_atual(tokens.CASA_ESCURA))
        for linha in range(8):
            for coluna in range(8):
                x0, y0, x1, y1 = geo.rect(linha, coluna)
                retangulo = QRectF(x0, y0, x1 - x0, y1 - y0)
                indice = self._indice_de_leitura(linha, coluna)
                pintor.fillRect(retangulo, clara if (linha + coluna) % 2 == 0 else escura)
                self._desenhar_peca(pintor, retangulo, self._classe_da_casa(indice))
                self._desenhar_incerteza(pintor, retangulo, indice)

        pintor.end()

    def _desenhar_peca(self, pintor: QPainter, casa: QRectF, classe: str) -> None:
        if classe == "empty":
            return
        mapa = self._pecas.get(classe)
        if mapa is not None:
            pintor.drawPixmap(casa.toRect(), self._preparada(classe, mapa, max(1, int(casa.width()))))
            return
        self._desenhar_glifo(pintor, casa, classe)

    def _desenhar_glifo(self, pintor: QPainter, casa: QRectF, classe: str) -> None:
        """O glifo de reserva, **contornado** -- e o contorno é o item, não enfeite (F9).

        **A medição.** O corpo da peça branca é `GLIFO_CLARO` (`#f8f8f8`) e a casa clara é
        `CASA_CLARA` (`#f0d9b5`): **1,29:1**. Um rei branco desenhado assim é uma peça que existe
        no FEN e não existe na tela em metade do tabuleiro -- e a metade é literal, são as 32
        casas claras. Na casa de último lance (`#cdd26a`) dá 1,52:1, e na casa escura 2,97:1, que
        ainda é abaixo do piso gráfico de 3,0.

        **O contorno resolve porque ele é a cor do outro glifo.** Peça branca com traço
        `GLIFO_ESCURO` dá 13,4:1 contra a casa clara; peça preta com traço `GLIFO_CLARO` dá
        16,3:1 contra a casa escura. É a mesma solução do xadrez impresso desde sempre -- a peça
        branca é um contorno preto com o miolo branco --, e é por isso que ela não precisa de
        nenhuma cor nova: as duas já estão na paleta, uma em cada peça.

        **`QPainterPath` e não quatro `drawText` deslocados.** O truque do texto repetido engrossa
        de forma diferente em cada direção e pisa no glifo vizinho quando a casa é pequena; o
        traço de `QPainterPath` acompanha a forma da letra e escala com ela. A largura sai de
        `LARGURA_DO_TRACO` * lado da casa, com piso de 1 px: um traço fixo some no tabuleiro
        grande e engole o glifo no pequeno.
        """
        corpo = QColor(GLIFO_ESCURO if classe.islower() else GLIFO_CLARO)
        traco = QColor(GLIFO_CLARO if classe.islower() else GLIFO_ESCURO)
        fonte = QFont(pintor.font())
        fonte.setPointSizeF(max(6.0, casa.height() * 0.72))

        caminho = QPainterPath()
        metricas = QFontMetricsF(fonte)
        texto = GLIFOS[classe]
        largura = metricas.horizontalAdvance(texto)
        linha_de_base = casa.center().y() + (metricas.ascent() - metricas.height() / 2.0)
        caminho.addText(casa.center().x() - largura / 2.0, linha_de_base, fonte, texto)

        pintor.save()
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        caneta = QPen(traco, max(1.0, casa.width() * LARGURA_DO_TRACO))
        caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pintor.setPen(caneta)
        pintor.setBrush(corpo)
        pintor.drawPath(caminho)
        pintor.restore()

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


def _pintar_o_tapete(pintor: QPainter, area: QRect, geo: BoardGeometry) -> None:
    """Pinta o painel embaixo e o tapete **só em volta** do tabuleiro. Ver `TAPETE_EM_VOLTA`."""
    pintor.fillRect(area, QColor(tema.cor_atual(tokens.SUPERFICIE_PADRAO)))
    faixa = QRect(
        int(geo.origin_x) - TAPETE_EM_VOLTA,
        int(geo.origin_y) - TAPETE_EM_VOLTA,
        int(geo.size) + 2 * TAPETE_EM_VOLTA,
        int(geo.size) + 2 * TAPETE_EM_VOLTA,
    )
    pintor.fillRect(faixa.intersected(area), QColor(tema.cor_atual(tokens.SUPERFICIE_TABULEIRO)))
