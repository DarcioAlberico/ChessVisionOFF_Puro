"""Anotações por diagrama de um livro, e o que elas mudam na exportação (S-67).

**O que isto guarda.** Aquilo que o pipeline não tem como saber e a pessoa sabe: de quem é a
vez quando o texto não diz, em que lance a posição acontece, se aquele diagrama merece um link
de análise, e os headers de PGN que só quem conhece o livro pode preencher.

**Por que um arquivo por livro, e não colunas no `labels.csv`.** Os dois falam dos mesmos
diagramas e têm vidas diferentes. O `labels.csv` é o dataset de treino: uma linha existe lá
porque alguém salvou aquela imagem para o modelo aprender. Aqui a unidade é o *diagrama do
livro*, anotado para a exportação -- e a maioria deles nunca vira amostra de treino. Misturar
os dois faria uma anotação de exportação criar linha de dataset, ou obrigaria a salvar uma
amostra só para poder dizer "este é o lance 24".

**Ausente significa "faça como sempre".** Nenhum campo tem valor cheio por padrão, e uma
anotação vazia **não é gravada**. A diferença importa: `side_to_move=None` é "use o que a
S-17 deduziu", e `side_to_move="w"` é "eu conferi, são as brancas" -- e a segunda tem de
vencer a dedução, senão anotar não serviria para nada. O mesmo vale para `lichess_link`, que
é tri-estado de propósito: `None` segue o padrão escolhido na hora de exportar, `True` e
`False` são decisões daquele diagrama.

**A chave é `(page_index, diagram_index)`**, com a página em base 0 -- a mesma que
`build_pgn_games` já usa em `review_reasons`. Ela depende da ordem de leitura (S-14): mudar
`reading_order` renumera os diagramas da página e desloca as anotações. Por isso a ordem
usada fica gravada no arquivo, e `load_annotations` avisa quando ela não bate.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .atomic_io import atomic_write_json
from .config import DEFAULT_READING_ORDER, PROJECT_ROOT, ReadingOrder

logger = logging.getLogger(__name__)

__all__ = [
    "DiagramAnnotation",
    "GalleryAnnotations",
    "annotations_path_for",
    "lichess_analysis_url",
    "load_annotations",
    "save_annotations",
]

DEFAULT_GALLERY_DIR = PROJECT_ROOT / "data" / "gallery"

LICHESS_ANALYSIS_BASE = "https://lichess.org/analysis/"
"""Montar a URL é offline; **abri-la** manda a posição para o lichess.org.

Por isso o módulo só a constrói, e quem decide abrir é a interface -- a mesma separação que
a S-32 faz entre saber o endpoint e enviar a imagem.
"""

RESERVED_HEADERS = frozenset({"FEN", "SetUp"})
"""Headers que a anotação não pode sobrescrever.

Só estes dois, e o critério é estreito: **contradizer o diagrama**. `[FEN]` é a posição, e
deixá-la ser digitada num campo de texto livre criaria um PGN cujo header desmente o
diagrama que o gerou; `[SetUp "0"]` diria que não há posição inicial declarada quando há.
Vez a jogar e número do lance mudam a FEN pelos campos próprios, que sabem recompô-la.

`Result` **não** está aqui, embora o export escreva `"*"`: um problema de mate anunciado tem
resultado declarável, e `"*"` é o padrão de quem não declarou, não uma verdade sobre a
posição.
"""


def lichess_analysis_url(fen: str) -> str:
    """URL do analisador do Lichess para uma FEN. Não acessa a rede."""
    return LICHESS_ANALYSIS_BASE + quote(fen.strip().replace(" ", "_"), safe="/_-")


@dataclass(frozen=True)
class DiagramAnnotation:
    """O que a pessoa declarou sobre um diagrama. Todo campo vazio é "não declarei"."""

    move_number: int | None = None
    """Número do lance cheio, que vira o último campo da FEN. `None` mantém 1."""

    side_to_move: str | None = None
    """`"w"`, `"b"` ou `None` para manter o que a S-17 deduziu."""

    lichess_link: bool | None = None
    """`None` segue o padrão da exportação; `True`/`False` decidem só este diagrama."""

    headers: dict[str, str] = field(default_factory=dict)
    """Headers de PGN extras. Aplicados por último: o que a pessoa escreve vence o inferido."""

    filled_from: str = ""
    """A partida da base que preencheu esta anotação, quando foi a base que preencheu (S-72).

    **Guarda a evidência, e não só a origem** -- `"Kasparov, Garry x Karpov, Anatoly,
    World-ch30 1984"` em vez de `"base"`. É o mesmo desenho do `side_to_move_evidence` da
    S-16, e pela mesma razão: quem discorda precisa saber *de quê* está discordando. Vazio é o
    normal, e significa que quem preencheu foi gente.
    """

    confirmed_from: str = ""
    """A base reconheceu esta posição -- ainda que não tenha preenchido campo nenhum (S-74).

    **Confirmar e preencher são coisas diferentes, e é por isso que são dois campos.** Uma
    posição que aparece em 300 partidas não identifica *qual* partida é, então ela não preenche
    header nenhum (ver `apply_matches`); mas ela responde a pergunta mais importante que a fila
    de revisão faz -- "esta leitura está certa?" --, porque as 64 casas bateram com uma posição
    que aconteceu num tabuleiro de verdade.

    Guarda a partida quando ela é única, e a contagem quando não é.
    """

    filled_fields: tuple[str, ...] = ()
    """Quais campos vieram da base, e **não** de uma pessoa.

    Sem isto o PGN mentiria com cara de procedência: a exportação marca a vez a jogar declarada
    na galeria como `[SideToMoveSource "manual"]`, que significa "uma pessoa conferiu e
    declarou" -- e depois da S-72 ela pode ter vindo de um casamento com a base, que é outra
    coisa e vale outro tanto. É o mesmo erro que a S-19 evitou ao não gravar `w` no
    `labels.csv` de quem não tem resposta.

    Por campo, e não uma bandeira por anotação, porque os dois se misturam no mesmo diagrama:
    a base preenche o lance e a pessoa corrige a vez. Editar um campo à mão o tira daqui --
    ver `GalleryModel.edit`.
    """

    @property
    def is_empty(self) -> bool:
        """Nada foi declarado. Anotação vazia não é gravada -- ver o docstring do módulo.

        `filled_from` não conta: ele descreve de onde vieram os outros campos, e uma anotação
        que só tivesse ele seria a procedência de coisa nenhuma. `confirmed_from` **conta**, e
        a diferença não é sutil: ele não descreve outro campo, ele é uma afirmação inteira --
        "a base reconheceu esta posição" --, e é o que tira o diagrama da fila de revisão
        (S-74). Descartá-lo por parecer vazio faria a fila reencher a cada varredura.
        """
        return (
            self.move_number is None
            and self.side_to_move is None
            and self.lichess_link is None
            and not self.headers
            and not self.confirmed_from
        )

    def to_dict(self) -> dict[str, Any]:
        dados: dict[str, Any] = {}
        if self.move_number is not None:
            dados["move_number"] = int(self.move_number)
        if self.side_to_move is not None:
            dados["side_to_move"] = self.side_to_move
        if self.lichess_link is not None:
            dados["lichess_link"] = bool(self.lichess_link)
        if self.headers:
            dados["headers"] = dict(self.headers)
        if self.filled_from:
            dados["filled_from"] = self.filled_from
        if self.filled_fields:
            dados["filled_fields"] = list(self.filled_fields)
        if self.confirmed_from:
            dados["confirmed_from"] = self.confirmed_from
        return dados

    @classmethod
    def from_dict(cls, dados: Any) -> DiagramAnnotation:
        if not isinstance(dados, dict):
            return cls()
        return cls(
            move_number=_inteiro_positivo(dados.get("move_number")),
            side_to_move=_lado(dados.get("side_to_move")),
            lichess_link=_tri_estado(dados.get("lichess_link")),
            headers=_headers(dados.get("headers")),
            filled_from=str(dados.get("filled_from") or ""),
            filled_fields=_campos(dados.get("filled_fields")),
            confirmed_from=str(dados.get("confirmed_from") or ""),
        )


def _inteiro_positivo(valor: Any) -> int | None:
    """Lance é contagem, então 0 e negativo não são "outro valor", são ausência."""
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return numero if numero >= 1 else None


def _lado(valor: Any) -> str | None:
    texto = str(valor or "").strip().lower()[:1]
    return texto if texto in ("w", "b") else None


def _tri_estado(valor: Any) -> bool | None:
    return None if valor is None else bool(valor)


def _campos(valor: Any) -> tuple[str, ...]:
    """Os nomes de campo preenchidos pela base, saneados. Qualquer outra coisa vira vazio."""
    if not isinstance(valor, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in valor if str(item).strip())


def _headers(valor: Any) -> dict[str, str]:
    """Só pares de texto, e nunca os reservados. Chave vazia some junto."""
    if not isinstance(valor, dict):
        return {}
    limpos: dict[str, str] = {}
    for chave, conteudo in valor.items():
        nome = str(chave).strip()
        if not nome or nome in RESERVED_HEADERS:
            continue
        texto = str(conteudo).strip()
        if texto:
            limpos[nome] = texto
    return limpos


@dataclass
class GalleryAnnotations:
    """As anotações de um livro, indexadas por `(page_index, diagram_index)`."""

    source_name: str = ""
    reading_order: ReadingOrder = DEFAULT_READING_ORDER
    entries: dict[tuple[int, int], DiagramAnnotation] = field(default_factory=dict)

    def get(self, page_index: int, diagram_index: int) -> DiagramAnnotation:
        """A anotação daquele diagrama, ou uma vazia. Nunca `None`: quem chama não deve ramificar."""
        return self.entries.get((int(page_index), int(diagram_index)), DiagramAnnotation())

    def set(self, page_index: int, diagram_index: int, annotation: DiagramAnnotation) -> None:
        """Grava a anotação -- ou **apaga a chave** se ela ficou vazia.

        Apagar é o que mantém o arquivo legível e o que faz "limpei os campos" significar
        "volte ao padrão" em vez de "declarei que não quero nada".
        """
        chave = (int(page_index), int(diagram_index))
        if annotation.is_empty:
            self.entries.pop(chave, None)
        else:
            self.entries[chave] = annotation

    def update(self, page_index: int, diagram_index: int, **campos: Any) -> DiagramAnnotation:
        """Muda alguns campos de uma anotação, preservando os outros. Devolve o resultado."""
        atual = self.get(page_index, diagram_index)
        novo = replace(atual, **campos)
        self.set(page_index, diagram_index, novo)
        return novo

    def as_mapping(self) -> dict[tuple[int, int], DiagramAnnotation]:
        """Cópia rasa para passar à exportação sem expor o dicionário interno."""
        return dict(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "source_name": self.source_name,
            "reading_order": self.reading_order,
            # Chave de JSON e string: "pagina.diagrama", a mesma forma do header [Round].
            "diagrams": {
                f"{pagina}.{diagrama}": anotacao.to_dict()
                for (pagina, diagrama), anotacao in sorted(self.entries.items())
            },
        }

    @classmethod
    def from_dict(cls, dados: Any) -> GalleryAnnotations:
        if not isinstance(dados, dict):
            return cls()
        entradas: dict[tuple[int, int], DiagramAnnotation] = {}
        for chave, valor in (dados.get("diagrams") or {}).items():
            pagina, _, diagrama = str(chave).partition(".")
            try:
                indice = (int(pagina), int(diagrama))
            except ValueError:
                logger.warning("Chave de diagrama ignorada na galeria: %r", chave)
                continue
            anotacao = DiagramAnnotation.from_dict(valor)
            if not anotacao.is_empty:
                entradas[indice] = anotacao

        ordem = str(dados.get("reading_order") or DEFAULT_READING_ORDER)
        if ordem not in ("row", "column"):
            ordem = DEFAULT_READING_ORDER
        return cls(
            source_name=str(dados.get("source_name") or ""),
            reading_order=ordem,  # type: ignore[arg-type]
            entries=entradas,
        )


def annotations_path_for(pdf_path: Path, *, directory: Path = DEFAULT_GALLERY_DIR) -> Path:
    """`data/gallery/<nome-do-pdf>.json`.

    Pelo `stem`, que é a convenção que `default_pgn_output_path` já usa para o PGN -- dois
    livros de mesmo nome em pastas diferentes colidiriam, e é o mesmo risco que o PGN corre
    desde sempre. Uniformidade vale mais aqui que uma segunda regra de nomeação.
    """
    return Path(directory) / f"{Path(pdf_path).stem}.json"


def load_annotations(
    pdf_path: Path,
    *,
    directory: Path = DEFAULT_GALLERY_DIR,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
) -> GalleryAnnotations:
    """Lê as anotações do livro. Arquivo ausente ou corrompido devolve conjunto vazio.

    Falhar para o lado do vazio é seguro aqui pelo mesmo motivo do `settings.py`: o vazio é
    "exporte como o pipeline decidiu", que é o comportamento anterior a este módulo.
    """
    caminho = annotations_path_for(pdf_path, directory=directory)
    anotacoes = GalleryAnnotations(source_name=Path(pdf_path).name, reading_order=reading_order)
    if not caminho.exists():
        return anotacoes

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Nao foi possivel ler %s (%s); seguindo sem anotacoes.", caminho, exc)
        return anotacoes

    carregado = GalleryAnnotations.from_dict(dados)
    if carregado.reading_order != reading_order:
        # Nao e erro: e um aviso de que os indices podem apontar para outro diagrama, porque
        # a numeracao de uma pagina depende da ordem de leitura (S-14).
        logger.warning(
            "As anotacoes de %s foram feitas com reading_order=%r e a exportacao esta em %r: "
            "os indices de diagrama podem nao corresponder.",
            Path(pdf_path).name,
            carregado.reading_order,
            reading_order,
        )
    carregado.source_name = carregado.source_name or Path(pdf_path).name
    return carregado


def save_annotations(
    pdf_path: Path,
    annotations: GalleryAnnotations,
    *,
    directory: Path = DEFAULT_GALLERY_DIR,
) -> Path:
    """Grava de forma atômica (S-25) e devolve o caminho escrito."""
    caminho = annotations_path_for(pdf_path, directory=directory)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(caminho, annotations.to_dict())
    return caminho
