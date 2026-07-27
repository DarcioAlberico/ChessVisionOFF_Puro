"""Resultados de OCR guardados por página, para navegar sem perder o reconhecimento.

**O problema.** O estado do OCR na interface é uma lista só (`result_items` e as edições
que a acompanham). Reconhecer a página 17 e ir para a 18 não apaga nada: a lista continua
sendo a da 17, e o seletor "Selecionado" segue apontando para diagramas que não são os da
página na tela. Voltar para a 17 também não traz nada de volta -- é preciso rodar o OCR de
novo, e as correções feitas à mão se vão.

**O que este módulo guarda.** Por página: os itens do OCR, as FENs editadas, os lados a
jogar editados e qual diagrama estava selecionado. As listas são guardadas **por
referência**, então uma correção feita enquanto a página está na tela já entra no cache --
não há um passo de "salvar" que possa ser esquecido.

**Por que com teto.** Cada item carrega o recorte 800×800×3 do tabuleiro, 1,83 MiB. Uma
página de exercícios com 9 diagramas custa ~16,5 MiB, e um livro tem centenas de páginas:
sem teto, navegar por 100 páginas reconhecidas custaria 1,6 GiB. O mesmo raciocínio da
S-26, e o mesmo remédio -- LRU.

**Por que os parâmetros entram na chave.** Reconhecer a página 17 a 220 DPI e voltar a ela
depois de mudar para 300 DPI não pode devolver o recorte antigo: ele foi feito de outra
imagem. Segue a decisão da S-24 ("retomar com parâmetros diferentes não é retomar") --
entrada com parâmetros divergentes é descartada, não adaptada.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_CACHED_PAGES = 8
"""~130 MiB no pior caso (9 diagramas por página). Cobre o vai-e-vem real entre páginas
vizinhas sem transformar a navegação num vazamento de memória."""


@dataclass(frozen=True)
class PageOcrParams:
    """O que precisa ser igual para um resultado guardado ainda valer.

    Não inclui `reading_order`: ela é global e mudá-la renumera os diagramas sem mudar o
    recorte. Inclui `model_path` porque trocar de modelo muda a FEN lida, e `orientation`
    porque muda qual leitura venceu (S-13).
    """

    dpi: int
    max_boards: int
    orientation: str
    model_path: str

    def describe_difference(self, other: PageOcrParams) -> str:
        """Em que os parâmetros diferem, em pt-BR, para o log dizer o motivo do descarte."""
        rótulos = {
            "dpi": "DPI",
            "max_boards": "máximo de diagramas",
            "orientation": "orientação",
            "model_path": "modelo",
        }
        partes = [
            f"{rótulos[campo]} {getattr(other, campo)!r} → {getattr(self, campo)!r}"
            for campo in rótulos
            if getattr(self, campo) != getattr(other, campo)
        ]
        return "; ".join(partes)


@dataclass
class PageResults:
    """O reconhecimento de uma página e as correções feitas sobre ele."""

    page_index: int
    params: PageOcrParams
    items: list[dict[str, Any]] = field(default_factory=list)
    fen_edits: list[str] = field(default_factory=list)
    side_edits: list[str] = field(default_factory=list)
    selected_index: int = 0

    def __post_init__(self) -> None:
        if not (len(self.items) == len(self.fen_edits) == len(self.side_edits)):
            raise ValueError(
                f"Listas de tamanhos diferentes: {len(self.items)} itens, "
                f"{len(self.fen_edits)} FENs, {len(self.side_edits)} lados a jogar."
            )

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def has_hand_edits(self) -> bool:
        """Se alguma coisa nesta página foi corrigida à mão.

        Serve para avisar antes de descartar: perder uma leitura do modelo custa rodar o
        OCR de novo, perder uma correção humana custa o trabalho da pessoa.
        """
        return any(
            item.get("edited_by_hand") or item.get("side_to_move_source") == "manual" for item in self.items
        )

    def clamped_index(self) -> int:
        if not self.items:
            return 0
        return max(0, min(self.selected_index, len(self.items) - 1))


class PageResultsCache:
    """Cache LRU de `PageResults`, com chave `(documento, página)`."""

    def __init__(self, max_pages: int = DEFAULT_MAX_CACHED_PAGES) -> None:
        self.max_pages = max(1, int(max_pages))
        self._entries: OrderedDict[tuple[str, int], PageResults] = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: tuple[str, int]) -> bool:
        return key in self._entries

    @property
    def cached_pages(self) -> list[tuple[str, int]]:
        """Da mais antiga para a mais recente, que é a ordem em que serão descartadas."""
        return list(self._entries)

    def put(self, document: str, results: PageResults) -> None:
        key = (document, results.page_index)
        self._entries[key] = results
        self._entries.move_to_end(key)

        while len(self._entries) > self.max_pages:
            (descartado_doc, descartada), saindo = self._entries.popitem(last=False)
            if saindo.has_hand_edits:
                # Aviso, nao bloqueio: quem quer guardar correcao salva a amostra no
                # dataset (Ctrl+S). Este cache e conveniencia de navegacao, nao persistencia
                # -- e prometer o contrario seria pior que o teto.
                logger.warning(
                    "Pagina %d de %s saiu do cache de navegacao e tinha correcao feita a mao. "
                    "Correcoes so ficam guardadas quando a amostra e salva no dataset.",
                    descartada,
                    descartado_doc,
                )
            else:
                logger.debug("Pagina %d de %s saiu do cache de navegacao.", descartada, descartado_doc)

    def get(self, document: str, page_index: int, params: PageOcrParams) -> PageResults | None:
        """Resultado guardado da página, ou `None` se não há ou se os parâmetros mudaram."""
        key = (document, page_index)
        guardado = self._entries.get(key)
        if guardado is None:
            return None

        if guardado.params != params:
            diferenca = params.describe_difference(guardado.params)
            logger.info(
                "Resultado guardado da pagina %d descartado: %s. Rode o OCR de novo.",
                page_index,
                diferenca,
            )
            del self._entries[key]
            return None

        self._entries.move_to_end(key)
        return guardado

    def discard(self, document: str, page_index: int) -> None:
        self._entries.pop((document, page_index), None)

    def discard_document(self, document: str) -> None:
        """Usado ao abrir outro PDF: resultado de outro documento não serve para nada."""
        for key in [k for k in self._entries if k[0] == document]:
            del self._entries[key]

    def clear(self) -> None:
        self._entries.clear()


class PageSwitch(str, Enum):
    """O que fazer com o editor ao trocar de página."""

    RESTORE = "restore"
    """Há reconhecimento guardado desta página: trazer de volta."""

    CLEAR = "clear"
    """Não há, e o que está no editor é de outra página: limpar."""

    KEEP = "keep"
    """Não há, e o que está no editor não veio de página nenhuma: não tocar."""


def decide_page_switch(*, stored: PageResults | None, current_is_page_result: bool) -> PageSwitch:
    """A decisão que evita que navegar destrua trabalho não relacionado.

    O caso que obriga o terceiro valor: o usuário abre uma amostra do dataset (ou um item
    da fila de revisão) no editor e depois mexe na página do PDF ao lado. O conteúdo do
    editor não tem nada a ver com a página exibida, e limpá-lo porque "esta página não tem
    reconhecimento" apagaria o trabalho dele por um motivo que não é dele.

    `CLEAR` só vale quando o que está na tela é, ele mesmo, o resultado de outra página --
    aí ele é enganoso, porque o seletor "Selecionado" aponta para diagramas que não estão
    na página exibida. Era exatamente esse o sintoma relatado.
    """
    if stored is not None:
        return PageSwitch.RESTORE
    return PageSwitch.CLEAR if current_is_page_result else PageSwitch.KEEP


def page_index_from_origin(origin: str) -> int | None:
    """Página de PDF a que uma origem de OCR se refere, ou `None` se não for uma.

    As origens em uso hoje:

    | origem | é resultado de página? |
    |---|---|
    | `pdf:livro.pdf:page:17` | sim |
    | `pdf:livro.pdf:page:17:crop=(10,20)-(300,400)` | **não** |
    | `local-image:foto.png` | não |

    O recorte de área fica fora de propósito. Ele reconhece um pedaço escolhido a mão, e
    guardá-lo como "o resultado da página 17" faria a navegação devolver dois diagramas
    onde a página tem nove -- pior que não guardar nada, porque parece completo.
    """
    if not origin.startswith("pdf:") or ":crop=" in origin:
        return None

    marcador = ":page:"
    if marcador not in origin:
        return None
    try:
        return int(origin.rsplit(marcador, 1)[1])
    except ValueError:
        return None
