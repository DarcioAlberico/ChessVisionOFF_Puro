"""Normalização do tabuleiro antes de virar 64 casas (S-39).

**O caso que motivou.** Euwe Band 1-2, página 25: o recorte está perfeito -- grade alinhada,
tabuleiro inteiro, `board_texture_score` de 1,0000 -- e a leitura sai com `min_confidence`
de **0,0000** e posição errada. Não é detecção nem capacidade do modelo. É que as casas
escuras daquele livro são **hachuradas com linhas diagonais** em vez de cinza sólido, sobre
papel amarelado de 1956, e essa textura não existe no domínio de treino.

O que o modelo recebia até aqui, em `model.preprocess_cell_to_tensor`:

    cvtColor(RGB2GRAY) → resize(64×64) → /255

Sem normalização de iluminação, sem equalização, sem supressão de trama, sem correção de
rotação residual. A hachura sobrevive ao downsample como estrutura de alta frequência dentro
de cada casa.

**A restrição que organiza o desenho: ser quase identidade num diagrama limpo.** Medido no
conjunto de campo, o `Polgar` sai a 1,000 de taxa de exportação e o `Karpov` a 0,857. Um
normalizador que "melhorasse" esses estragaria mais do que conserta. Cada etapa aqui é ou
uma operação que não faz nada quando não há o que corrigir (o campo plano de uma imagem
uniforme é uma constante; o deskew de uma grade alinhada é 0°), ou tem a força limitada por
esse critério.

**Por que no tabuleiro e não na casa.** Iluminação e trama são propriedades da página.
Estimá-las sobre 100×100 px de uma casa é estimá-las sobre ruído -- e uma casa vazia não tem
como saber se está clara porque é clara ou porque o scanner iluminou demais ali.

**A armadilha do domínio, e por que ela não é hipotética.** Normalizar na inferência e não no
treino cria um segundo desencontro de domínio -- o inverso do atual. As 3.289 amostras de
`data/samples/` foram gravadas cruas. A saída é normalizar **na leitura**, em
`BoardFenDataset._load_board`, com os mesmos parâmetros da inferência: o disco continua com o
original, e trocar de normalização é retreinar, não re-anotar.

E a consequência que não pode passar em silêncio: um checkpoint treinado com normalização e
outro sem são **incompatíveis**, e `ArchConfig.version` precisa distingui-los. Sem isso volta
o defeito que a S-27 corrigiu, com outra roupa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)

MAX_SKEW_DEGREES = 3.0
"""Sobra de rotação que vale a pena procurar.

O warp da S-12 corrige perspectiva; o que sobra é fração de grau a poucos graus. Procurar
além disso não acha rotação -- acha o ângulo em que a busca casa com outra coisa, e girar
um tabuleiro alinhado por 8° é estragá-lo.
"""

SKEW_STEP_DEGREES = 0.25
SKEW_PROBE_SIDE = 256
"""Lado em que a busca de rotação roda. 32 px por casa basta para a periodicidade da grade,
e 25 rotações de 256×256 custam ~4 ms contra ~90 ms em 800×800."""

MIN_SKEW_GAIN = 1.02
"""Ganho mínimo de periodicidade para valer girar.

Sem isto, o deskew gira todo tabuleiro por 0,25° em busca de um ganho de 0,1% que é ruído --
e cada rotação reamostra a imagem, que é custo real e sem retorno.
"""


@dataclass(frozen=True)
class NormalizerConfig:
    """As etapas, cada uma desligável.

    **Todas desligadas por padrão, e por medição** (docs/EXPERIMENTS_FASE7.md, S-39). Não é
    preguiça nem "fica para depois": as quatro foram medidas no conjunto de campo, uma por
    vez e em combinação, e o resultado foi

    | variante | taxa de exportação |
    |---|---|
    | **nenhuma** | **0,6842** |
    | deskew, campo plano, CLAHE (isolados ou juntos) | 0,6842 — idênticos |
    | qualquer uma com supressão de trama | **0,0000** |

    Dois motivos, e nenhum era o esperado:

    1. **Campo plano e CLAHE não mudam nada** porque
       `training.build_train_transform` já usa `ColorJitter(brightness=0.3, contrast=0.3)`:
       o modelo foi treinado a ignorar exatamente esse tipo de ajuste global. Eles alteram a
       imagem (3,7 e 3,0 de diferença média de pixel) e não alteram a leitura.
    2. **A trama não é separável da peça por escala.** A hachura do `Euwe` tem período de
       ~12,5 px numa casa de 100 px, que é a ordem de grandeza do traço da peça. Medido por
       mediana e por morfologia: o kernel que começa a mover o Euwe (0,000 → 0,10, ainda 8×
       abaixo do gate) é o mesmo que derruba `Karpov` e `Polgar` de 1,000 para 0,05–0,79.

    Fica igual ao `TTA_ENABLED` e ao `APPLY_CALIBRATED_TEMPERATURE` da Fase 5: medido,
    desligado, documentado, e disponível para quem tiver outro acervo.
    """

    deskew: bool = False
    flat_field: bool = False
    hatch_suppression: bool = False
    clahe: bool = False

    clahe_clip: float = 2.0
    flat_field_sigma_ratio: float = 0.25
    """Sigma do desfoque do campo plano, como fração do lado do tabuleiro.

    Precisa ser **muito maior que a casa**: com sigma ~ um lado de casa, o desfoque segue o
    próprio padrão xadrezado e dividir por ele apagaria o contraste entre casas claras e
    escuras -- que é justamente o sinal. 1/4 do lado são 2 casas, e o que sobra é o campo de
    iluminação.
    """

    hatch_kernel_ratio: float = 0.045
    """Lado do filtro de mediana, como fração do lado do tabuleiro.

    A mediana remove linha fina e preserva traço grosso: numa janela maior que o período da
    hachura, os pixels da trama são minoria e a casa volta a ser lisa. A peça, que é sólida,
    atravessa. ~0,045 de 800 px são 36 px, ou ~1/3 de casa.
    """

    @property
    def version(self) -> str:
        """Identidade da normalização, para entrar em `ArchConfig.version`.

        `norm0` é "nenhuma etapa", que é o pipeline anterior à S-39 -- e é o que um
        checkpoint antigo, que não registra nada, tem de continuar significando.
        """
        ativos = "".join(
            letra
            for letra, ligado in (
                ("d", self.deskew),
                ("f", self.flat_field),
                ("h", self.hatch_suppression),
                ("c", self.clahe),
            )
            if ligado
        )
        return f"norm{ativos}" if ativos else "norm0"

    @property
    def is_identity(self) -> bool:
        return not (self.deskew or self.flat_field or self.hatch_suppression or self.clahe)

    @classmethod
    def from_version(cls, version: str) -> NormalizerConfig:
        if not version.startswith("norm"):
            raise ValueError(f"Versão de normalização deve começar com 'norm'; recebido {version!r}.")
        letras = version[4:]
        if letras in ("", "0"):
            return cls()
        desconhecidas = set(letras) - set("dfhc")
        if desconhecidas:
            raise ValueError(f"Etapas desconhecidas em {version!r}: {''.join(sorted(desconhecidas))}")
        return cls(
            deskew="d" in letras,
            flat_field="f" in letras,
            hatch_suppression="h" in letras,
            clahe="c" in letras,
        )


IDENTITY = NormalizerConfig()


def _odd(value: int, minimum: int = 3) -> int:
    return max(minimum, value | 1)


def _grid_periodicity(gray: np.ndarray) -> float:
    """Quanto os gradientes desta imagem se organizam numa grade 8×8.

    É o alvo que o deskew maximiza. Somar o gradiente por coluna e por linha e olhar a
    variância dos perfis mede exatamente o que uma grade alinhada tem e uma torta não: picos
    nítidos nas oito divisões, em vez de picos borrados por várias colunas.
    """
    gx = np.abs(np.diff(gray.astype(np.float32), axis=1)).mean(axis=0)
    gy = np.abs(np.diff(gray.astype(np.float32), axis=0)).mean(axis=1)
    return float(gx.var() + gy.var())


def estimate_skew(board_rgb: np.ndarray, *, max_degrees: float = MAX_SKEW_DEGREES) -> float:
    """Sobra de rotação do tabuleiro, em graus. `0.0` quando não vale girar.

    Busca direta em vez de Hough: o que se quer é o ângulo que deixa a **grade** mais nítida,
    e medir isso é mais barato e mais direto que achar retas e depois inferir o ângulo delas.
    A busca é limitada a `MAX_SKEW_DEGREES` porque além disso ela deixa de achar rotação e
    passa a achar o ângulo em que o critério casa com outra coisa.
    """
    gray = cv2.cvtColor(board_rgb, cv2.COLOR_RGB2GRAY)
    probe = cv2.resize(gray, (SKEW_PROBE_SIDE, SKEW_PROBE_SIDE), interpolation=cv2.INTER_AREA)
    centro = (SKEW_PROBE_SIDE / 2, SKEW_PROBE_SIDE / 2)

    base = _grid_periodicity(probe)
    melhor_angulo, melhor_valor = 0.0, base

    passo = SKEW_STEP_DEGREES
    angulo = -max_degrees
    while angulo <= max_degrees + 1e-9:
        if abs(angulo) > 1e-9:
            matriz = cv2.getRotationMatrix2D(centro, angulo, 1.0)
            girada = cv2.warpAffine(
                probe, matriz, (SKEW_PROBE_SIDE, SKEW_PROBE_SIDE), flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            )
            valor = _grid_periodicity(girada)
            if valor > melhor_valor:
                melhor_angulo, melhor_valor = angulo, valor
        angulo += passo

    if melhor_valor < base * MIN_SKEW_GAIN:
        return 0.0
    return melhor_angulo


def _apply_deskew(board_rgb: np.ndarray) -> np.ndarray:
    angulo = estimate_skew(board_rgb)
    if angulo == 0.0:
        return board_rgb
    altura, largura = board_rgb.shape[:2]
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), angulo, 1.0)
    return cv2.warpAffine(
        board_rgb, matriz, (largura, altura), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )


def _apply_flat_field(board_rgb: np.ndarray, sigma_ratio: float) -> np.ndarray:
    """Divide pela própria imagem muito desfocada: some o gradiente de iluminação e o papel.

    Numa imagem já uniforme o desfoque é praticamente uma constante, e dividir por constante
    e reescalar é identidade -- que é a restrição desta etapa.
    """
    lado = max(board_rgb.shape[:2])
    sigma = max(4.0, lado * sigma_ratio)
    fundo: np.ndarray = cv2.GaussianBlur(board_rgb.astype(np.float32), (0, 0), sigmaX=sigma, sigmaY=sigma)
    corrigida = board_rgb.astype(np.float32) / np.maximum(fundo, 1.0)
    corrigida *= float(fundo.mean())
    return np.clip(corrigida, 0, 255).astype(np.uint8)


def _apply_hatch_suppression(board_rgb: np.ndarray, kernel_ratio: float) -> np.ndarray:
    """Mediana com janela maior que o período da trama: linha fina some, traço grosso fica."""
    lado = max(board_rgb.shape[:2])
    kernel = _odd(int(lado * kernel_ratio))
    # `medianBlur` acima de 5 exige uint8, que é o que temos, mas fica caro em kernel grande;
    # o teto mantém o custo previsível num tabuleiro de 800 px.
    kernel = min(kernel, 41)
    return cv2.medianBlur(board_rgb, kernel)


def _apply_clahe(board_rgb: np.ndarray, clip: float) -> np.ndarray:
    """CLAHE sobre a luminância, preservando a cor.

    `tileGridSize=(8, 8)` cai exatamente numa casa por tile, o que é deliberado: o que se
    quer equalizar é o contraste **dentro** da casa, e um tile por casa é a granularidade em
    que "peça contra fundo" é a única coisa na janela.
    """
    lab = cv2.cvtColor(board_rgb, cv2.COLOR_RGB2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


class BoardNormalizer:
    """Normaliza o tabuleiro inteiro antes do corte em casas.

    Sem estado entre chamadas de propósito: a mesma instância é usada da thread de OCR, da
    de exportação e da de treino, e guardar qualquer coisa aqui reintroduziria a corrida que
    a S-31 fechou no modelo.
    """

    def __init__(self, config: NormalizerConfig = IDENTITY) -> None:
        self.config = config

    @property
    def version(self) -> str:
        return self.config.version

    def normalize(self, board_rgb: np.ndarray) -> np.ndarray:
        """A imagem normalizada, ou a mesma imagem quando nenhuma etapa está ligada.

        A ordem não é arbitrária. O deskew vem primeiro porque as três seguintes medem
        estatísticas locais, e medi-las sobre uma grade torta as mede sobre a borda errada.
        O campo plano vem antes da trama porque a mediana é não-linear e um gradiente de
        iluminação faria a janela dela decidir diferente em cada canto. O CLAHE vem por
        último porque é o único que **amplifica**, e amplificar antes de remover a trama
        amplificaria a trama.
        """
        if self.config.is_identity:
            return board_rgb

        imagem = board_rgb
        if self.config.deskew:
            imagem = _apply_deskew(imagem)
        if self.config.flat_field:
            imagem = _apply_flat_field(imagem, self.config.flat_field_sigma_ratio)
        if self.config.hatch_suppression:
            imagem = _apply_hatch_suppression(imagem, self.config.hatch_kernel_ratio)
        if self.config.clahe:
            imagem = _apply_clahe(imagem, self.config.clahe_clip)
        return imagem


# --------------------------------------------------------------- a página de scan puro (S-547)

COBERTURA_DE_SCAN = 0.70
"""A partir de que fração da página a maior imagem embutida **é** a página.

É o mesmo número de `detection/embedded.MAX_PAGE_COVERAGE`, e de propósito: lá ele decide
"esta imagem é o fundo e não um diagrama", aqui ele decide "esta página é um scan". São a mesma
observação lida de dois lados, e dois números para ela divergiriam.
"""

DPI_ALVO_DE_SCAN = 300
"""O DPI para o qual reamostrar, quando a reamostragem estiver ligada.

Medido, e **não é o padrão** (ver `ScanConfig`): a 300 DPI o `Koblenz` perde 8 dos 120 diagramas
e o `Niemeijer` perde 33 dos 51, porque o detector de contorno tem limiares em pixel e uma
página maior muda o que eles alcançam. Fica declarado porque é o número que a medição usou.
"""

JANELA_DE_SAUVOLA = 0.025
"""Lado da janela do Sauvola, como fração do lado da página. ~55 px numa página de 2.200."""

K_DE_SAUVOLA = 0.2
R_DE_SAUVOLA = 128.0
"""Os dois parâmetros do limiar local `T = m · (1 + k · (s/R − 1))`, nos valores do artigo."""

OTSU = "otsu"
SAUVOLA = "sauvola"
BINARIZACOES: tuple[str, ...] = (OTSU, SAUVOLA)


@dataclass(frozen=True)
class ScanConfig:
    """O caminho da página de scan puro: binarizar e reamostrar antes da detecção.

    **Desligado por padrão, e por medição.** A S-547 mediu **livro inteiro**, sem amostragem, com o
    modelo de 2026-09-04: os dois livros do acervo que exportam zero, e três que a mesma porta de
    scan seleciona e que já vão bem. "Acima do gate" é a confiança mínima do tabuleiro contra
    `ACCEPT_MIN_CONFIDENCE` -- o **teto** do que a exportação aceitaria, que ainda exige legalidade
    e orientação; "FEN legal" é `check_position` com o lado a jogar assumido branco. As três
    colunas são proxies, e comparáveis entre si porque a regra é a mesma em toda variante.

    | livro | variante | diagramas | FEN legais | acima do gate |
    |---|---|---|---|---|
    | `Koblenz` (70 p) | nenhuma | 120 | 64 | **0** |
    | | Otsu | 120 | 64 | **0** |
    | | Sauvola | 120 | 56 | **0** |
    | | 300 DPI | 112 | 74 | **0** |
    | `Niemeijer` (32 p) | nenhuma | 51 | 42 | **0** |
    | | Otsu | **79** | 57 | **0** |
    | | Sauvola | 72 | 55 | **0** |
    | | 300 DPI | **18** | 13 | **0** |
    | `Reinfeld_1001` (320 p) | nenhuma | 995 | 992 | **985** |
    | | Otsu | 935 | 930 | **918** |
    | | Sauvola | 1000 | 994 | **984** |
    | `Estrin` (88 p) | nenhuma | 118 | 112 | **116** |
    | | Otsu | 117 | 112 | **115** |
    | | Sauvola | 118 | 112 | **115** |
    | | 300 DPI | 118 | 112 | **116** |
    | `Euwe Band 7` (56 p) | nenhuma | 80 | 79 | **55** |
    | | Otsu | 80 | 78 | **46** |
    | | Sauvola | 80 | 79 | **48** |
    | | 300 DPI | 80 | 80 | **58** |

    Três leituras, e nenhuma delas é "ligue isto":

    1. **A binarização move a detecção e não move a exportação.** No `Niemeijer` o Otsu acha 55%
       mais diagramas -- 79 contra 51 -- e nenhum deles passa do gate de confiança, então o livro
       continua exportando zero. Achar mais do que não se consegue ler não é ganho.
    2. **Ela custa nos livros que já vão bem, e os três medidos perderam.** O `Reinfeld_1001`
       perde 67 dos 985 com Otsu e 1 dos 985 com Sauvola; o `Euwe Band 7` -- que a porta seleciona
       porque a página inteira é uma imagem -- perde 9 dos 55 com Otsu e 7 com Sauvola; o `Estrin`
       perde 1 dos 116 com qualquer um dos dois. É o risco real do item, e ele se realizou.
    3. **A reamostragem para 300 DPI perde diagrama**, e muito: −8 no `Koblenz` e −33 no
       `Niemeijer`. O detector de contorno tem limiares em pixel. A medição **renderizou** a 300
       DPI, que é o melhor caso: reamostrar a partir dos 220 não sai melhor que isso.

    Fica na forma do `NormalizerConfig` acima, pelo mesmo motivo dele: medido, desligado,
    documentado, e disponível para quem tiver outro acervo.
    """

    binarizacao: str = ""
    """`""`, `"otsu"` ou `"sauvola"`. Vazio é o caminho de sempre: a página como foi renderizada."""

    dpi_alvo: int = 0
    """Para que DPI reamostrar. `0` não reamostra, que é o padrão."""

    def __post_init__(self) -> None:
        if self.binarizacao and self.binarizacao not in BINARIZACOES:
            raise ValueError(
                f"binarização desconhecida: {self.binarizacao!r}. As válidas são {list(BINARIZACOES)}, "
                "ou vazio para não binarizar."
            )
        if self.dpi_alvo < 0:
            raise ValueError(f"dpi_alvo não pode ser negativo; veio {self.dpi_alvo}.")

    @property
    def is_identity(self) -> bool:
        return not self.binarizacao and self.dpi_alvo <= 0


SEM_CAMINHO_DE_SCAN = ScanConfig()


def pagina_e_scan(tem_camada_de_texto: bool, cobertura_de_imagem: float) -> bool:
    """Se esta página é um scan puro: sem texto extraível **ou** coberta por uma imagem só.

    **`ou`, e não `e`, e a diferença foi medida** sobre os 46 PDFs de `PDF/`, 24 páginas amostradas
    de cada um: o `ou` seleciona **26** livros e o `e` selecionaria **11**. Os dois sinais
    discordam em livro demais para um `e` valer: o `Koblenz` e o `Gunderam` têm camada de texto nas
    24 páginas **e** são scan de página inteira nas 24 (o OCR de quem digitalizou deixou o texto
    lá); o `Simple Chess` não tem camada em página nenhuma e também não tem imagem de página
    inteira em 23 das 24. Um `e` deixaria os três de fora.

    **E o que a medição mostrou de mais importante é que esta porta não separa o que interessa.**
    Entre os 26 selecionados estão, lado a lado, o `Reinfeld_1001` (985 dos 995 tabuleiros acima do
    gate) e o `Koblenz` (0 dos 120) -- medidos no mesmo dia, com o mesmo modelo. "É um scan" e "é
    um scan que o modelo não lê" são perguntas diferentes, e só a primeira tem resposta barata. Ver
    `ScanConfig` para o que se decidiu por causa disso.
    """
    return not tem_camada_de_texto or cobertura_de_imagem >= COBERTURA_DE_SCAN


def _sauvola(cinza: np.ndarray, janela: int, k: float) -> np.ndarray:
    """Limiar local de Sauvola: `T = m · (1 + k · (s/R − 1))`, por janela deslizante.

    Média e desvio saem de dois `boxFilter` -- `E[x²] − E[x]²` --, que é a forma por imagem
    integral: o custo não depende do tamanho da janela, e uma janela de 55 px numa página de
    2.200 seria proibitiva calculada pixel a pixel.
    """
    janela = _odd(janela, minimum=3)
    valores = cinza.astype(np.float32)
    media = cv2.boxFilter(valores, -1, (janela, janela), normalize=True, borderType=cv2.BORDER_REFLECT)
    media_dos_quadrados = cv2.boxFilter(
        valores * valores, -1, (janela, janela), normalize=True, borderType=cv2.BORDER_REFLECT
    )
    desvio = np.sqrt(np.maximum(media_dos_quadrados - media * media, 0.0))
    limiar = media * (1.0 + k * (desvio / R_DE_SAUVOLA - 1.0))
    return np.where(valores > limiar, 255, 0).astype(np.uint8)


def binarizar_pagina(page_rgb: np.ndarray, metodo: str) -> np.ndarray:
    """A página em preto e branco, ainda como RGB de três canais.

    Três canais e não um: tudo o que consome a página renderizada -- `detect_diagrams`, o recorte
    do tabuleiro, o `board_texture_score` -- espera `(H, W, 3)`, e devolver um canal só faria a
    troca aparecer como erro de forma três camadas adiante.

    **Otsu é global e Sauvola é local**, e é essa a escolha. Otsu procura um corte só para a
    página inteira: numa página de scan com sombra de lombada, o lado escuro vira preto sólido.
    Sauvola decide por janela e atravessa a sombra, ao custo de inventar textura no papel liso.
    Medido (ver `ScanConfig`), nenhum dos dois paga -- e o que separa os dois números é menor que
    o que separa qualquer um deles do caminho sem binarização.
    """
    if metodo not in BINARIZACOES:
        raise ValueError(f"binarização desconhecida: {metodo!r}. As válidas são {list(BINARIZACOES)}.")
    cinza = cv2.cvtColor(page_rgb, cv2.COLOR_RGB2GRAY)
    if metodo == OTSU:
        _limiar, binaria = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    else:
        lado = max(cinza.shape[:2])
        binaria = _sauvola(cinza, max(15, int(lado * JANELA_DE_SAUVOLA)), K_DE_SAUVOLA)
    saida: np.ndarray = cv2.cvtColor(binaria.astype(np.uint8), cv2.COLOR_GRAY2RGB)
    return saida


def reamostrar_pagina(page_rgb: np.ndarray, *, dpi: float, dpi_alvo: int) -> np.ndarray:
    """A página reescalada de `dpi` para `dpi_alvo`. Identidade quando os dois coincidem.

    `INTER_AREA` para reduzir e `INTER_CUBIC` para ampliar, que é a regra do OpenCV: a média de
    área não tem o que fazer ao ampliar, e a cúbica ao reduzir deixa serrilhado que o detector de
    contorno lê como borda.
    """
    if dpi_alvo <= 0 or dpi <= 0:
        return page_rgb
    escala = dpi_alvo / float(dpi)
    if abs(escala - 1.0) < 1e-6:
        return page_rgb
    altura, largura = page_rgb.shape[:2]
    destino = (max(1, round(largura * escala)), max(1, round(altura * escala)))
    interpolacao = cv2.INTER_AREA if escala < 1.0 else cv2.INTER_CUBIC
    redimensionada: np.ndarray = cv2.resize(page_rgb, destino, interpolation=interpolacao)
    return redimensionada


def preparar_pagina_de_scan(
    page_rgb: np.ndarray, config: ScanConfig = SEM_CAMINHO_DE_SCAN, *, dpi: float = 220.0
) -> np.ndarray:
    """A página pronta para a detecção. **A mesma imagem** quando nada está ligado.

    A reamostragem vem primeiro porque a binarização mede estatísticas em janela de pixels: fazê-la
    antes seria decidir o limiar numa escala e usá-lo noutra. É a mesma ordem, e o mesmo
    argumento, do `BoardNormalizer.normalize` acima.
    """
    if config.is_identity:
        return page_rgb
    imagem = reamostrar_pagina(page_rgb, dpi=dpi, dpi_alvo=config.dpi_alvo)
    if config.binarizacao:
        imagem = binarizar_pagina(imagem, config.binarizacao)
    return imagem
