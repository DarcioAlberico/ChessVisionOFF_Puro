"""Motor de OCR opcional e plugável (S-42).

**O problema, medido nos 27 PDFs do acervo.** 7 livros (2.654 páginas) não têm camada de
texto nenhuma: para eles `pdf_text.contexts_for_pdf_page` devolve `DiagramContext()` vazio,
sempre, e todo diagrama sai `[SideToMoveSource "default"]`. Outros 5 estão num terceiro
regime que a S-16 não distingue -- a camada existe e **falha em parte das páginas**
(`Gaprindashvili` e `Vishy Anand` têm texto em 14 de 30 páginas amostradas, `400
Quebra-cabeças` e `Yusupov` em 22, `La Combinación` em 26). São scans com OCR parcial do
distribuidor, e para eles a decisão não pode ser por livro: tem de ser por página.

**Por que uma interface, e não uma biblioteca escolhida.** O mesmo desenho da S-32 para o
`RemoteFenProvider`, e pelo mesmo motivo: o recurso é opcional, o projeto funciona sem ele,
e a escolha de motor não pode vazar para o resto do código. `build_recognizer` é o único
caminho para um reconhecedor existir, e devolver `None` é caminho normal -- igual ao
`find_engine` da S-33, não é erro não achar.

**Qual é o padrão, e por que não é por acurácia.** Os critérios que este projeto já
declarou -- funciona offline, nada sai da máquina no uso padrão, Windows, CPU, instalação
por `uv sync` -- eliminam a maioria antes de comparar qualidade:

| motor | peso | offline na 1ª execução | veredito |
|---|---|---|---|
| **RapidOCR** | ~15 MB, no `onnxruntime` que o extra `onnx` da S-30 já traz | **sim**, modelos no wheel | **padrão** |
| EasyOCR | ~100 MB baixados no primeiro uso | **não** | suportado, opt-in explícito |
| Tesseract | binário externo | sim | suportado se já instalado |

EasyOCR não pode ser o padrão enquanto o README prometer que nada sai da máquina no uso
padrão: baixar 100 MB de modelo na primeira execução é tráfego que o usuário não pediu, e a
promessa da S-32 vale para a rede inteira, não só para a correção remota. Quem o quiser
escreve `"engine": "easyocr"` no `data/settings.json` -- e aí a decisão é dele, declarada.

**Ressalva honesta sobre idioma.** O modelo de reconhecimento que o RapidOCR embarca é
`ch`+`en`. Ele lê o alfabeto latino, e não há medição neste projeto sobre o que ele faz com
`ñ`, `ß` e acentuação portuguesa. Isso importa menos do que parece para o caminho crítico:
`fold()` já derruba acento antes de casar padrão, e `LAS BLANCAS JUEGAN PRIMERO` não tem
nenhum. Importa para `[Event]` e `[White]`/`[Black]`, e ali um erro de acento é um erro
visível que o usuário corrige. Quem precisar dos quatro idiomas de verdade usa o EasyOCR.

**O que este módulo não faz.** Não decide *onde* ler -- rodar OCR na página inteira é errado
por custo, por falso positivo e porque o tabuleiro vira texto. Quem recorta é a S-43
(`ocr_caption.CaptionReader`), e é ela que faz o resultado entrar pela porta da S-16 em vez
de por uma paralela.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import numpy as np

from .settings import OcrSettings

logger = logging.getLogger(__name__)

MOTOR_DE_CASA = "glifo"
"""O nome do único motor deste projeto. **Uma definição, e três módulos a leem** (S-207).

`text/recognizer.NOME` é ele, `build_recognizer` o despacha por ele, e `ocr_caption` decide por
ele se a linha lida sai com procedência `glifo` ou `ocr`. Escrito três vezes, a primeira troca de
nome deixaria dois lugares certos e um errado -- e o errado seria o que grava o header do PGN."""

KNOWN_ENGINES: tuple[str, ...] = ("rapidocr", "easyocr", "tesseract", MOTOR_DE_CASA)
"""`glifo` entrou na S-181, e é o único de casa: o classificador de caractere portado do
PyBoxEditor_Tkinter (`text/recognizer.py`). Ele não baixa nada -- os pesos são apontados por
`OcrSettings.glyph_model` --, e é o único que restringe o **decodificador** pelo `allowlist` em
vez de filtrar a saída. Ver `docs/SPEC_TEXTO.md`."""

MIN_CONFIDENCE = 0.30
"""Abaixo disto o motor está adivinhando, e uma legenda adivinhada é pior que legenda
nenhuma: ela vira `[SideToMoveSource "ocr"]` e parece um dado lido. O corte é conservador de
propósito -- o caminho que o resultado vai percorrer (`_side_from_line`, `MAX_CAPTION_WORDS`,
os padrões da S-16) já é exigente, e o que sobrevive a ele com 0,3 de confiança tem forma de
legenda."""


@dataclass(frozen=True)
class TextBox:
    """Um trecho de texto reconhecido, em **pixels da imagem que foi passada**.

    Pixels, e não pontos do PDF: este módulo não sabe de onde a imagem veio. Converter para
    o sistema de coordenadas da página é trabalho de quem recortou, que é a S-43.
    """

    text: str
    bbox: tuple[float, float, float, float]
    confidence: float


@runtime_checkable
class TextRecognizer(Protocol):
    """Lê texto de uma imagem. Não presume qual motor, nem que exista um."""

    @property
    def name(self) -> str:
        """Como o motor aparece no log e na barra de status."""

    def read(self, image_rgb: np.ndarray, *, allowlist: str = "") -> list[TextBox]:
        """Os trechos reconhecidos, ou lista vazia. Nunca levanta por não achar texto.

        `allowlist` restringe o vocabulário -- `"WB"` para o marcador de lado a jogar,
        `"12345678"` para as coordenadas da borda. Não é detalhe: para glifo único é o que
        separa `B` de `8` e de `13`. Os motores a suportam de formas diferentes (o EasyOCR
        nativamente, o Tesseract por `tessedit_char_whitelist`, o RapidOCR não a suporta e
        aqui ela vira filtro posterior), e a interface esconde a diferença.
        """


def build_recognizer(settings: OcrSettings) -> TextRecognizer | None:
    """O reconhecedor que a configuração autoriza, ou `None`.

    `None` em três situações, e as três são caminho normal, não erro: o recurso está
    desligado, o motor pedido não existe, ou o extra não está instalado. É o mesmo contrato
    do `find_engine` da S-33 -- a ausência de um recurso opcional não pode derrubar um
    pipeline que funciona sem ele.
    """
    if not settings.enabled:
        return None

    motor = settings.engine.strip().lower()
    construtores = {
        "rapidocr": _build_rapidocr,
        "easyocr": lambda: _build_easyocr(settings.languages),
        "tesseract": lambda: _build_tesseract(settings.languages),
        "glifo": lambda: _build_glifo(settings.glyph_model),
    }
    construtor = construtores.get(motor)
    if construtor is None:
        logger.warning(
            "Motor de OCR desconhecido: %r. Conhecidos: %s. O OCR fica desligado.",
            settings.engine,
            ", ".join(KNOWN_ENGINES),
        )
        return None

    try:
        recognizer = construtor()
    except ImportError as exc:
        logger.warning(
            "OCR habilitado com o motor %r, mas ele não está instalado (%s). "
            "Instale com `uv sync --extra ocr`. O pipeline segue sem OCR.",
            motor,
            exc,
        )
        return None
    except Exception as exc:  # noqa: BLE001 - motor de terceiro; a falha dele nao é a nossa
        if motor == "glifo":
            # O `glifo` é o único motor de casa, e a mensagem dele já diz o que falta e onde
            # pôr. Embrulhá-la em "nao foi possivel inicializar" esconderia o que interessa.
            logger.warning("%s O pipeline segue sem OCR.", exc)
        else:
            logger.warning(
                "Nao foi possivel inicializar o motor de OCR %r (%s). O pipeline segue sem OCR.", motor, exc
            )
        return None

    logger.info("Motor de OCR pronto: %s", recognizer.name)
    return recognizer


# --------------------------------------------------------------------------------------
# Utilitarios comuns aos provedores
# --------------------------------------------------------------------------------------


def filter_by_allowlist(boxes: list[TextBox], allowlist: str) -> list[TextBox]:
    """Mantém só os caracteres permitidos, e descarta o que ficar vazio.

    Filtro posterior é pior que restringir o vocabulário no decodificador -- o motor já
    escolheu `8` em vez de `B` antes de chegar aqui, e apagar o `8` não traz o `B` de volta.
    Existe porque o RapidOCR não expõe o vocabulário, e não ter o filtro seria pior: uma
    caixa com `13` casaria como se fosse um marcador.
    """
    if not allowlist:
        return boxes

    permitidos = set(allowlist)
    filtradas: list[TextBox] = []
    for box in boxes:
        texto = "".join(ch for ch in box.text if ch in permitidos)
        if texto:
            filtradas.append(TextBox(text=texto, bbox=box.bbox, confidence=box.confidence))
    return filtradas


def _quad_to_bbox(points: Any) -> tuple[float, float, float, float]:
    """Quadrilátero de 4 pontos -> retângulo. O texto pode vir inclinado; o bbox não."""
    coords = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    return (
        float(coords[:, 0].min()),
        float(coords[:, 1].min()),
        float(coords[:, 0].max()),
        float(coords[:, 1].max()),
    )


def _as_bgr(image_rgb: np.ndarray) -> np.ndarray:
    """RGB -> BGR. Os três motores esperam a convenção do OpenCV."""
    array = np.ascontiguousarray(image_rgb)
    if array.ndim == 3 and array.shape[2] >= 3:
        return array[:, :, ::-1].copy()
    return array


# --------------------------------------------------------------------------------------
# Provedores
# --------------------------------------------------------------------------------------


class RapidOcrRecognizer:
    """RapidOCR sobre `onnxruntime`. O padrão, e o único que não baixa nada."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    @property
    def name(self) -> str:
        return "rapidocr"

    def read(self, image_rgb: np.ndarray, *, allowlist: str = "") -> list[TextBox]:
        if image_rgb.size == 0:
            return []

        resultado = self._engine(_as_bgr(image_rgb))
        # A API devolve `(lista, tempos)` e a lista é `None` quando não achou nada -- não
        # uma lista vazia, o que faria um `for` direto levantar.
        bruto = resultado[0] if isinstance(resultado, tuple) else resultado
        if not bruto:
            return []

        boxes: list[TextBox] = []
        for item in bruto:
            if len(item) < 3:
                continue
            quad, texto, score = item[0], str(item[1]).strip(), float(item[2])
            if texto and score >= MIN_CONFIDENCE:
                boxes.append(TextBox(text=texto, bbox=_quad_to_bbox(quad), confidence=score))
        return filter_by_allowlist(boxes, allowlist)


class EasyOcrRecognizer:
    """EasyOCR. Suportado, nunca padrão: baixa ~100 MB no primeiro uso."""

    def __init__(self, reader: Any) -> None:
        self._reader = reader

    @property
    def name(self) -> str:
        return "easyocr"

    def read(self, image_rgb: np.ndarray, *, allowlist: str = "") -> list[TextBox]:
        if image_rgb.size == 0:
            return []

        # `allowlist` nativo: aqui ela restringe o decodificador, que é onde a restrição
        # de fato vale alguma coisa. Ver `filter_by_allowlist`.
        extras = {"allowlist": allowlist} if allowlist else {}
        bruto = self._reader.readtext(np.ascontiguousarray(image_rgb), **extras)

        boxes: list[TextBox] = []
        for item in bruto or ():
            if len(item) < 3:
                continue
            quad, texto, score = item[0], str(item[1]).strip(), float(item[2])
            if texto and score >= MIN_CONFIDENCE:
                boxes.append(TextBox(text=texto, bbox=_quad_to_bbox(quad), confidence=score))
        return boxes


class TesseractRecognizer:
    """Tesseract via `pytesseract`, para quem já tem o binário instalado."""

    def __init__(self, pytesseract: Any, languages: tuple[str, ...]) -> None:
        self._pytesseract = pytesseract
        self._lang = "+".join(_TESSERACT_LANGS.get(idioma, idioma) for idioma in languages) or "eng"

    @property
    def name(self) -> str:
        return f"tesseract ({self._lang})"

    def read(self, image_rgb: np.ndarray, *, allowlist: str = "") -> list[TextBox]:
        if image_rgb.size == 0:
            return []

        config = f"--psm 6 -c tessedit_char_whitelist={allowlist}" if allowlist else "--psm 6"
        dados = self._pytesseract.image_to_data(
            np.ascontiguousarray(image_rgb),
            lang=self._lang,
            config=config,
            output_type=self._pytesseract.Output.DICT,
        )

        boxes: list[TextBox] = []
        for indice, texto_bruto in enumerate(dados.get("text", ())):
            texto = str(texto_bruto).strip()
            # O Tesseract devolve -1 para as caixas de layout (bloco, parágrafo, linha),
            # que não são texto reconhecido e cujo texto vem vazio de qualquer forma.
            score = float(dados["conf"][indice]) / 100.0
            if not texto or score < MIN_CONFIDENCE:
                continue
            x, y = float(dados["left"][indice]), float(dados["top"][indice])
            boxes.append(
                TextBox(
                    text=texto,
                    bbox=(x, y, x + float(dados["width"][indice]), y + float(dados["height"][indice])),
                    confidence=score,
                )
            )
        return boxes


_TESSERACT_LANGS = {"pt": "por", "en": "eng", "es": "spa", "de": "deu", "fr": "fra"}
"""Do código ISO-639-1 que a configuração usa para o `traineddata` do Tesseract."""


def _build_rapidocr() -> TextRecognizer:
    from rapidocr_onnxruntime import RapidOCR  # noqa: PLC0415 - import tardio é o ponto

    return RapidOcrRecognizer(RapidOCR())


def _build_glifo(model_path: str) -> TextRecognizer:
    """O classificador de caractere deste projeto (S-181). **Não é um motor de terceiro.**

    Ele levanta `ModeloInvalido` com a mensagem já escrita em pt-BR -- qual arquivo falta, onde
    apontá-lo, ou por que o par (pesos, metadado) não confere. Quem chama só a repassa; ver o
    ramo `glifo` em `build_recognizer`.
    """
    from .text.recognizer import build_glyph_recognizer  # noqa: PLC0415 - import tardio é o ponto

    return build_glyph_recognizer(model_path)


def _build_easyocr(languages: tuple[str, ...]) -> TextRecognizer:
    import easyocr  # noqa: PLC0415 - import tardio é o ponto

    # `gpu=False` explícito: esta máquina não tem GPU (BASELINE.md), e o padrão do EasyOCR
    # é tentar CUDA e cair para CPU com um aviso por instância.
    return EasyOcrRecognizer(easyocr.Reader(list(languages) or ["en"], gpu=False))


def _build_tesseract(languages: tuple[str, ...]) -> TextRecognizer:
    import pytesseract  # noqa: PLC0415 - import tardio é o ponto

    # Importar o wrapper não prova que o binário existe -- ele é um processo externo, e a
    # falha viria só na primeira leitura, dentro da varredura de um livro.
    pytesseract.get_tesseract_version()
    return TesseractRecognizer(pytesseract, languages)
