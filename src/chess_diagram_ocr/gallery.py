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

from .atomic_io import atomic_write_json, atomic_write_text
from .config import DEFAULT_READING_ORDER, PROJECT_ROOT, ReadingOrder

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_HUMAN_EXTRACT",
    "DiagramAnnotation",
    "GalleryAnnotations",
    "HumanExtract",
    "annotations_path_for",
    "export_human",
    "human_only",
    "lichess_analysis_url",
    "load_annotations",
    "read_human_extract",
    "restore_human",
    "save_annotations",
    "write_human_extract",
]

DEFAULT_GALLERY_DIR = PROJECT_ROOT / "data" / "gallery"

DEFAULT_HUMAN_EXTRACT = PROJECT_ROOT / "data" / "gallery_human.jsonl"
"""O extrato do que **uma pessoa** digitou ou escolheu na galeria (S-115).

`data/gallery/` fica fora do repositório por dois motivos que continuam válidos: o
`*.index.json` é derivado do PDF, e o `<livro>.json` descreve o conteúdo de um livro protegido.
Mas dentro dele há trabalho que **não se refaz de jeito nenhum** -- a vez a jogar que alguém
conferiu na legenda, e as partidas escolhidas a mão na lista de candidatas da S-86.

A separação é a que o `filled_rule` já grava: o que a base preencheu volta com
`cvoff-games --apply` a partir do cache de posições; o que uma pessoa decidiu não volta.
Versionar só a segunda metade custa uma fração dos 13 MB e protege a parte irrecuperável."""

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

    chosen_game: str = ""
    """A partida que **uma pessoa** escolheu na lista de candidatas (S-86).

    Guarda a chave da partida -- `White|Black|Date|Round|Event` --, e não o índice dela na
    lista: a ordem muda quando a base muda, e "a terceira" apontaria para outra partida na
    execução seguinte.

    **É o que impede a próxima varredura de desfazer o trabalho.** `apply_matches` preenche o
    que está vazio e uma escolha humana costuma ter preenchido tudo -- mas ela também *troca* a
    partida, e sem esta marca um `cvoff-games --apply` posterior reescreveria a procedência com
    a candidata que o desempate automático prefere. É o mesmo defeito que a S-77 consertou no
    conjunto de campo: o que a pessoa decidiu não pode ser sobrescrito por quem só palpita.
    """

    filled_rule: str = ""
    """**Qual regra escolheu a partida** entre as candidatas (S-91). Vazio é anterior à S-91.

    `filled_from` diz *de que* partida veio o preenchimento; isto diz *por que* foi ela, e são
    perguntas diferentes cujas respostas valem tantos diferentes:

    | valor | o que significa | quanto vale |
    |---|---|---|
    | `unique` | a posição está numa partida só da base | não houve escolha a fazer |
    | `caption` | a legenda do livro nomeia exatamente esta | duas fontes independentes concordando |
    | `date` | havia várias e o desempate pegou a mais antiga | **palpite** -- ver abaixo |
    | `human` | uma pessoa escolheu na lista | a resposta |

    **O `date` existe para ser encontrado.** Medido em 2026-08-15, esse desempate discorda da
    legenda do livro 72,3% das vezes onde há legenda para conferir, contra um piso de ruído de
    26,5%. São 141 diagramas do acervo preenchidos assim antes da S-91, e sem este campo eles
    são indistinguíveis de dado conferido -- que é a definição de procedência inventada.
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
            # Como o `confirmed_from`, e pela mesma razão: escolher uma partida é uma afirmação
            # inteira, não a procedência de outro campo. Descartá-la faria a escolha da pessoa
            # sumir num diagrama cujos campos já estavam todos preenchidos.
            and not self.chosen_game
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
        if self.chosen_game:
            dados["chosen_game"] = self.chosen_game
        if self.filled_rule:
            dados["filled_rule"] = self.filled_rule
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
            chosen_game=str(dados.get("chosen_game") or ""),
            filled_rule=_regra(dados.get("filled_rule")),
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


FILL_RULES = ("unique", "caption", "date", "human")
"""As regras que podem ter escolhido a partida. Ver `DiagramAnnotation.filled_rule`."""


def _regra(valor: Any) -> str:
    """Regra desconhecida vira vazio -- "não sei por que esta partida" é uma resposta melhor
    que uma etiqueta inventada, e é o que o campo já significa nas anotações anteriores."""
    texto = str(valor or "").strip().lower()
    return texto if texto in FILL_RULES else ""


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


# ------------------------------------------------------- o extrato humano (S-115)

HUMAN_FIELDS = ("move_number", "side_to_move", "lichess_link", "headers", "chosen_game")
"""Os campos que o extrato carrega. Ver `human_only` para por que **estes**."""


def human_only(annotation: DiagramAnnotation) -> DiagramAnnotation:
    """O que **uma pessoa** declarou nesta anotação. Vazia quando foi tudo da base (S-115).

    O crivo é o `filled_fields`, que já responde exatamente esta pergunta campo a campo: o que
    está lá veio de um casamento com a base e volta com `cvoff-games --apply`; o que não está
    foi digitado.

    **Com uma exceção, e ela é o coração do item:** quando `filled_rule == "human"`, o
    `filled_fields` lista os campos que a *escolha da pessoa* pôs (ver `choose_game`) -- ela
    olhou a lista de candidatas e disse qual era. Tratá-los como "da base" jogaria fora
    justamente as 21 decisões mais caras do acervo.

    **`filled_from`, `filled_rule` e `confirmed_from` ficam de fora**: descrevem de onde vieram
    os outros campos, e uma varredura nova os reconstrói. O que o extrato guarda é o que
    varredura nenhuma reconstrói.

    **E uma anotação anterior à procedência por campo não declara nada.** `filled_from` cheio
    com `filled_fields` vazio só acontece numa anotação gravada pela versão do `apply_matches`
    anterior à correção de procedência (é o caso que `_recover_provenance` repara). Nela o
    crivo não funciona: tudo *parece* humano. Chamar isso de humano encheria o extrato de
    headers da base -- 1.694 campos, medidos -- e, pior, o `--import-human` os reescreveria
    como digitados, que é a procedência inventada que a S-72 e a S-94 existem para impedir.

    O caminho de recuperá-los existe e é outro: `cvoff-games --apply` reconhece os campos que
    batem com o casamento e devolve o `filled_fields` a eles. Depois disso, extrair de novo
    separa direito.
    """
    if annotation.filled_from and not annotation.filled_fields and annotation.filled_rule != "human":
        return DiagramAnnotation(
            lichess_link=annotation.lichess_link,
            chosen_game=annotation.chosen_game,
        )

    da_base = () if annotation.filled_rule == "human" else annotation.filled_fields
    return DiagramAnnotation(
        move_number=None if "move_number" in da_base else annotation.move_number,
        side_to_move=None if "side_to_move" in da_base else annotation.side_to_move,
        # A base nunca preenche o link nem escolhe partida: os dois são decisão de gente,
        # sempre, e por isso não passam pelo crivo.
        lichess_link=annotation.lichess_link,
        headers={
            nome: valor
            for nome, valor in annotation.headers.items()
            if f"header:{nome}" not in da_base
        },
        chosen_game=annotation.chosen_game,
    )


@dataclass
class HumanExtract:
    """O extrato e **o que ele não pôde separar**. Os dois juntos porque o segundo é ressalva."""

    records: list[dict[str, Any]] = field(default_factory=list)
    books: int = 0

    unresolved: int = 0
    """Anotações anteriores à procedência por campo -- ver `human_only`.

    Não entram no extrato, e o número precisa aparecer: sem ele, um extrato pequeno pareceria
    "há pouco trabalho humano" quando na verdade é "há trabalho que não dá para separar".
    O conserto é `cvoff-games --apply`, que devolve o `filled_fields` a elas (S-72)."""


def export_human(*, directory: Path = DEFAULT_GALLERY_DIR) -> HumanExtract:
    """Uma linha por diagrama com algo humano, de todos os livros da pasta. Ordenado.

    Ordenado por `(livro, página, diagrama)` e não pela ordem do disco: o extrato é
    versionado, e um arquivo cuja ordem muda a cada execução produz um diff ilegível a cada
    commit -- é a mesma razão pela qual `to_dict` ordena as chaves.
    """
    extrato = HumanExtract()
    for caminho in sorted(Path(directory).glob("*.json")):
        if caminho.name.endswith(".index.json") or ".bak-" in caminho.name:
            continue
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Galeria ilegível em %s (%s); fora do extrato.", caminho, exc)
            continue
        extrato.books += 1
        anotacoes = GalleryAnnotations.from_dict(dados)
        for (pagina, diagrama), anotacao in sorted(anotacoes.entries.items()):
            if anotacao.filled_from and not anotacao.filled_fields and anotacao.filled_rule != "human":
                extrato.unresolved += 1
            humano = human_only(anotacao)
            if humano.is_empty:
                continue
            extrato.records.append(
                {"book": caminho.stem, "at": f"{pagina}.{diagrama}", **humano.to_dict()}
            )
    return extrato


def write_human_extract(
    records: list[dict[str, Any]], path: Path = DEFAULT_HUMAN_EXTRACT
) -> Path:
    """Grava o extrato como JSONL. Uma linha por diagrama, para o diff ser por diagrama."""
    caminho = Path(path)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    corpo = "".join(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n" for registro in records)
    atomic_write_text(caminho, corpo)
    return caminho


def read_human_extract(path: Path = DEFAULT_HUMAN_EXTRACT) -> list[dict[str, Any]]:
    """Lê o extrato. Arquivo ausente é lista vazia; linha corrompida é pulada com aviso.

    Pular a linha e não derrubar o comando: o extrato é restaurado depois de um desastre, e um
    arquivo com uma linha truncada é exatamente a situação em que se quer as outras 5.952.
    """
    caminho = Path(path)
    if not caminho.exists():
        return []
    registros = []
    for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), start=1):
        if not linha.strip():
            continue
        try:
            registro = json.loads(linha)
        except json.JSONDecodeError as exc:
            logger.warning("Linha %d do extrato humano ignorada (%s).", numero, exc)
            continue
        if isinstance(registro, dict) and registro.get("book") and registro.get("at"):
            registros.append(registro)
        else:
            logger.warning("Linha %d do extrato humano sem livro ou posição; ignorada.", numero)
    return registros


def restore_human(
    records: list[dict[str, Any]], *, directory: Path = DEFAULT_GALLERY_DIR
) -> dict[str, int]:
    """Escreve o extrato de volta nas anotações. Devolve `{livro: diagramas tocados}`.

    **O que vem do extrato vence**, e sai do `filled_fields`: se a pessoa digitou `Event` e a
    varredura de reconstrução o preencheu pela base, quem está com o livro na mão é ela -- é a
    mesma regra da S-17, e é a razão de o extrato existir.

    Só toca no que o registro traz. Um livro reconstruído mantém tudo o que a base preencheu e
    que ninguém contradisse, e mantém o `confirmed_from`, que é afirmação sobre a **leitura** e
    não sobre quem preencheu.
    """
    por_livro: dict[str, int] = {}
    for livro, do_livro in _por_livro(records).items():
        caminho = Path(directory) / f"{livro}.json"
        anotacoes = GalleryAnnotations(source_name=livro)
        if caminho.exists():
            try:
                anotacoes = GalleryAnnotations.from_dict(json.loads(caminho.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Galeria ilegível em %s (%s); será refeita a partir do extrato.", caminho, exc)

        tocados = 0
        for chave, registro in do_livro:
            humano = DiagramAnnotation.from_dict(registro)
            anterior = anotacoes.get(*chave)
            declarados = _declared_fields(humano)
            restantes = tuple(campo for campo in anterior.filled_fields if campo not in declarados)
            anotacoes.set(
                *chave,
                replace(
                    anterior,
                    move_number=humano.move_number if humano.move_number is not None else anterior.move_number,
                    side_to_move=humano.side_to_move or anterior.side_to_move,
                    lichess_link=humano.lichess_link if humano.lichess_link is not None else anterior.lichess_link,
                    headers={**anterior.headers, **humano.headers},
                    chosen_game=humano.chosen_game or anterior.chosen_game,
                    filled_fields=restantes,
                    # Mesma aritmética do `_provenance_after` da tela: sem campo nenhum da base
                    # sobrando, os dois descrevem coisa nenhuma.
                    filled_from=anterior.filled_from if restantes else "",
                    filled_rule=anterior.filled_rule if restantes else "",
                ),
            )
            tocados += 1

        atomic_write_json(caminho, anotacoes.to_dict())
        por_livro[livro] = tocados
    return por_livro


def _declared_fields(annotation: DiagramAnnotation) -> set[str]:
    """Os nomes de `filled_fields` que esta anotação humana ocupa."""
    nomes = {nome for nome in ("move_number", "side_to_move") if getattr(annotation, nome) is not None}
    return nomes | {f"header:{nome}" for nome in annotation.headers}


def _por_livro(records: list[dict[str, Any]]) -> dict[str, list[tuple[tuple[int, int], dict[str, Any]]]]:
    """Agrupa por livro e converte `"80.0"` em `(80, 0)`. Uma leitura de arquivo por livro."""
    agrupado: dict[str, list[tuple[tuple[int, int], dict[str, Any]]]] = {}
    for registro in records:
        pagina, _, diagrama = str(registro.get("at", "")).partition(".")
        try:
            chave = (int(pagina), int(diagrama))
        except ValueError:
            logger.warning("Posição ignorada no extrato humano: %r", registro.get("at"))
            continue
        agrupado.setdefault(str(registro["book"]), []).append((chave, registro))
    return agrupado
