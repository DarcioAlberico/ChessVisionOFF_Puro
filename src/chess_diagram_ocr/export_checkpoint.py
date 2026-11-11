"""Checkpoint incremental da exportação, para cancelar e retomar (S-24).

O `1001 Winning Chess Sacrifices` tem 1.121 páginas. A 0,18 s por página são ~3,5 minutos
de varredura, e até aqui a única forma de interromper era fechar o app -- perdendo tudo.

O formato é JSONL de uma linha por página, e não um JSON único reescrito a cada página, por
duas razões que se somam:

- **Acrescentar não reescreve.** Um JSON único custaria O(páginas²) de escrita ao longo de
  um livro e, pior, teria uma janela de truncamento a cada página.
- **Linha rasgada é detectável.** Se a energia cair no meio da última linha, ela não parseia
  e é descartada; as anteriores continuam válidas. Um JSON único cortado ao meio não tem
  nada aproveitável.

A primeira linha é o cabeçalho com os parâmetros da varredura. Retomar com parâmetro
diferente (outro DPI, outra ordem de leitura, outro modelo) **não** é retomar: seria juntar
metade de um PGN com metade de outro. Nesse caso o parcial é descartado e a varredura
recomeça, com aviso no log.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from .arquivo_do_dono import ler_texto

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

    from .pdf_text import DiagramContext
    from .pdf_to_pgn import DiagramPosition
    from .semantics import SideToMove

logger = logging.getLogger(__name__)

CHECKPOINT_VERSION = 2
"""2 (S-819): a posição sai inteira, campo por campo de `dataclasses.fields`.

A 1 escrevia uma lista de chaves à mão que a dataclass deixou para trás: a página lida antes da
interrupção voltava sem a estipulação (`[Stipulation]`, `[OCRStipulation]`) e sem cinco campos
do contexto, e a posição aceita por reparo de estipulação saía sem dizer que foi reparada."""

VERSAO_ANTERIOR = 1
"""Ainda é retomada, com aviso: o que ela não guardou volta no padrão do campo."""

DEFAULT_CHECKPOINT_EVERY = 5
"""Páginas entre gravações. 5 a 220 DPI é ~1 s de trabalho arriscado por vez."""


def partial_path_for(output_path: Path) -> Path:
    """`PGN/livro.pgn` -> `PGN/livro.partial.jsonl`."""
    output_path = Path(output_path)
    return output_path.with_suffix(".partial.jsonl")


@dataclass(frozen=True)
class ScanParams:
    """O que precisa bater para um parcial poder ser continuado."""

    source_name: str
    model_path: str
    dpi: int
    max_boards_per_page: int
    orientation: str
    reading_order: str
    read_text: bool
    start_page: int
    end_page: int | None

    model_identity: str = ""
    """Identidade do arquivo de checkpoint, não do caminho (S-57).

    O caminho não distingue dois modelos: o treino reescreve sempre o mesmo
    `models/piece_classifier.pt`. Sem isto, exportar metade de um livro, cancelar, treinar e
    retomar produzia um PGN com metade das posições lidas por um modelo e metade por outro,
    **sem aviso** -- e o docstring deste módulo prometia justamente que "outro modelo"
    descartava o parcial.

    Default vazio para que um `.partial.jsonl` gravado antes desta mudança continue sendo
    lido: ele não sabia a identidade, e recusá-lo por isso jogaria fora horas de varredura.
    Ver `is_compatible_with`.
    """

    ocr_engine: str = ""
    """Motor de OCR de legenda em uso, ou vazio quando não havia (S-43).

    Mesma razão do `model_identity`, aplicada à outra fonte de metadado: retomar com OCR uma
    exportação começada sem ele produziria um PGN em que metade dos `[SideToMoveSource]` diz
    `default` e a outra metade `ocr` -- e a diferença não seria do livro, seria de quando
    cada página foi lida. O header existe para que a procedência signifique algo.

    Vazio, e não `None`, para casar com o "sem OCR" que é o padrão do projeto: um parcial
    gravado antes da S-43 e um gravado hoje com `--ocr off` são a mesma varredura, e têm de
    poder continuar um ao outro.
    """

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "model_path": self.model_path,
            "model_identity": self.model_identity,
            "ocr_engine": self.ocr_engine,
            "dpi": self.dpi,
            "max_boards_per_page": self.max_boards_per_page,
            "orientation": self.orientation,
            "reading_order": self.reading_order,
            "read_text": self.read_text,
            "start_page": self.start_page,
            "end_page": self.end_page,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ScanParams:
        return cls(
            source_name=str(raw.get("source_name", "")),
            model_path=str(raw.get("model_path", "")),
            model_identity=str(raw.get("model_identity", "")),
            ocr_engine=str(raw.get("ocr_engine", "")),
            dpi=int(raw.get("dpi", 0)),
            max_boards_per_page=int(raw.get("max_boards_per_page", 0)),
            orientation=str(raw.get("orientation", "")),
            reading_order=str(raw.get("reading_order", "")),
            read_text=bool(raw.get("read_text", True)),
            start_page=int(raw.get("start_page", 0)),
            end_page=None if raw.get("end_page") is None else int(raw["end_page"]),
        )

    def is_compatible_with(self, wanted: ScanParams) -> bool:
        """Se um parcial gravado com `self` pode ser continuado por uma varredura `wanted`.

        Tudo tem de bater, com uma exceção: quando **um dos dois** não registra a identidade
        do modelo, ela não pesa. É o caso de um parcial anterior à S-57, e recusá-lo por não
        saber algo que ninguém lhe perguntou descartaria trabalho já feito por uma
        formalidade.
        """
        if self.model_identity and wanted.model_identity:
            return self.to_dict() == wanted.to_dict()
        neutro = {"model_identity": ""}
        return {**self.to_dict(), **neutro} == {**wanted.to_dict(), **neutro}


@dataclass
class PartialExport:
    """O que um `.partial.jsonl` guarda: os parâmetros e as páginas já concluídas."""

    params: ScanParams
    positions: list[DiagramPosition] = field(default_factory=list)
    last_page_done: int = -1
    """Índice da última página **inteira** gravada. -1 quando nenhuma."""

    @property
    def resume_from(self) -> int:
        return self.last_page_done + 1

    @property
    def pages_done(self) -> int:
        return max(0, self.last_page_done + 1 - self.params.start_page)


# ---------------------------------------------------------------------- serialização


_T = TypeVar("_T", bound="DataclassInstance")

_Conversor = Callable[[object], object]


def _para_json(valor: object) -> object:
    """Dataclass vira objeto campo a campo, tupla vira lista; o resto o JSON já sabe escrever."""
    if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
        return _campos_para_json(valor)
    if isinstance(valor, (tuple, list)):
        return [_para_json(item) for item in valor]
    return valor


def _campos_para_json(instancia: DataclassInstance) -> dict[str, object]:
    return {campo.name: _para_json(getattr(instancia, campo.name)) for campo in dataclasses.fields(instancia)}


def _em_tuplas(valor: object) -> object:
    """O inverso do `_para_json` para o que não é dataclass: toda sequência destas dataclasses é tupla."""
    if isinstance(valor, list):
        return tuple(_em_tuplas(item) for item in valor)
    return valor


def _de_json(
    classe: type[_T],
    cru: object,
    aninhados: Mapping[str, _Conversor] | None = None,
) -> _T:
    """Remonta `classe` a partir de `fields()`, e não de uma lista de chaves escrita à mão (S-819).

    Chave que falta fica com o padrão do campo -- é o parcial gravado antes de o campo existir.
    Chave que sobra é recusada: lê-la em silêncio seria perder um campo do outro lado, o defeito
    que esta função existe para não ter. Só os campos que são dataclass têm conversor próprio
    (`aninhados`); os demais saem do JSON como estão, com lista de volta a tupla.
    """
    if not isinstance(cru, dict):
        raise TypeError(f"{classe.__name__}: esperava objeto, veio {type(cru).__name__}")
    conhecidos = {campo.name for campo in dataclasses.fields(classe)}
    sobra = sorted(set(cru) - conhecidos)
    if sobra:
        raise ValueError(f"{classe.__name__}: chave desconhecida no parcial: {', '.join(sobra)}")
    conversores = aninhados or {}
    argumentos = {
        nome: None if valor is None else conversores.get(nome, _em_tuplas)(valor)
        for nome, valor in cru.items()
    }
    return classe(**argumentos)


def _context_from_json(cru: object) -> DiagramContext:
    from .estipulacao import Estipulacao
    from .orientation import BoardCoordinates
    from .pdf_text import DiagramContext

    aninhados: dict[str, _Conversor] = {
        "coordinates": lambda valor: _de_json(BoardCoordinates, valor),
        "stipulation": lambda valor: _de_json(Estipulacao, valor),
    }
    return _de_json(DiagramContext, cru, aninhados)


def _side_from_json(cru: object) -> SideToMove:
    from .semantics import SideToMove

    return _de_json(SideToMove, cru)


def position_to_dict(position: DiagramPosition) -> dict[str, object]:
    return _campos_para_json(position)


def position_from_dict(raw: object) -> DiagramPosition:
    from .pdf_to_pgn import DiagramPosition

    return _de_json(DiagramPosition, raw, {"side_to_move": _side_from_json, "context": _context_from_json})


# ------------------------------------------------------------------------ escrita


class CheckpointWriter:
    """Acumula páginas e grava o parcial de tempos em tempos.

    O acúmulo existe porque gravar uma linha por página em livro de 1.121 páginas custaria
    1.121 `flush` -- e o que se ganha com isso é irrelevante: perder 5 páginas de trabalho
    numa queda é ~1 s de reprocessamento.
    """

    def __init__(
        self,
        path: Path,
        params: ScanParams,
        *,
        every: int = DEFAULT_CHECKPOINT_EVERY,
        resumed: bool = False,
    ) -> None:
        self.path = Path(path)
        self.params = params
        self.every = max(1, every)
        self._pending: list[tuple[int, list[DiagramPosition]]] = []
        self._started = resumed
        """`True` já de saída quando retomamos: as páginas novas vão ao fim do arquivo que
        existe, e reescrever o cabeçalho perderia tudo que ele guardava."""

    def record_page(self, page_index: int, positions: list[DiagramPosition]) -> None:
        self._pending.append((page_index, list(positions)))
        if len(self._pending) >= self.every:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        lines: list[str] = []
        if not self._started:
            header = {"kind": "header", "version": CHECKPOINT_VERSION, "params": self.params.to_dict()}
            lines.append(json.dumps(header, ensure_ascii=False))
        for page_index, positions in self._pending:
            lines.append(
                json.dumps(
                    {
                        "kind": "page",
                        "page_index": page_index,
                        "positions": [position_to_dict(position) for position in positions],
                    },
                    ensure_ascii=False,
                )
            )
        self._pending.clear()

        mode = "a" if self._started else "w"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open(mode, encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
        self._started = True

    def discard(self) -> None:
        """Apaga o parcial. Chamado quando a exportação chega ao fim com sucesso."""
        self._pending.clear()
        self.path.unlink(missing_ok=True)


def load_partial(path: Path, params: ScanParams) -> PartialExport | None:
    """Lê um parcial compatível com `params`. `None` se não houver ou não servir."""
    path = Path(path)
    if not path.exists():
        return None

    try:
        # Do programa (S-905): o acento rasgado pela queda estraga só a última linha, que o laço
        # abaixo descarta. Decodificar estrito jogava fora as páginas boas junto.
        raw_lines = ler_texto(path, do_usuario=False).splitlines()
    except OSError as exc:
        logger.warning("Parcial de exportação ilegível, será ignorado (%s): %s", path, exc)
        return None

    lines = [line for line in raw_lines if line.strip()]
    if not lines:
        return None

    try:
        header = json.loads(lines[0])
    except ValueError as exc:
        logger.warning("Parcial de exportação sem cabeçalho válido, será ignorado (%s): %s", path, exc)
        return None

    version = header.get("version")
    if header.get("kind") != "header" or version not in (CHECKPOINT_VERSION, VERSAO_ANTERIOR):
        logger.warning("Parcial de exportação de formato desconhecido, será ignorado: %s", path)
        return None

    stored = ScanParams.from_dict(header.get("params", {}))
    if not stored.is_compatible_with(params):
        logger.warning(
            "Parcial de exportação foi gerado com outros parâmetros e será ignorado: %s",
            _params_diff(stored, params),
        )
        return None

    if version == VERSAO_ANTERIOR:
        # Recusar jogaria fora a varredura inteira por campos que só a estipulação e o contexto
        # fino usam; retomar sem avisar faria a metade antiga do PGN calar sem que se saiba por quê.
        logger.warning(
            "Parcial de exportação da versão anterior (%d): as páginas já lidas voltam sem a "
            "estipulação e sem parte do contexto da legenda; reexporte do zero para tê-los: %s",
            VERSAO_ANTERIOR,
            path,
        )

    partial = PartialExport(params=stored)
    for line_number, line in enumerate(lines[1:], start=2):
        try:
            entry = json.loads(line)
            if entry.get("kind") != "page":
                continue
            page_index = int(entry["page_index"])
            positions = [position_from_dict(item) for item in entry.get("positions", [])]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            # Linha rasgada por interrupcao: acontece na ultima e so nela. Descartar o resto
            # e a leitura correta -- as paginas seguintes nao chegaram a ser gravadas.
            logger.warning("Parcial truncado na linha %d, retomando do que veio antes: %s", line_number, exc)
            break
        partial.positions.extend(positions)
        partial.last_page_done = max(partial.last_page_done, page_index)

    if partial.last_page_done < 0:
        return None
    return partial


def _params_diff(stored: ScanParams, wanted: ScanParams) -> str:
    changes = [
        f"{field_name}: {getattr(stored, field_name)!r} -> {getattr(wanted, field_name)!r}"
        for field_name in stored.to_dict()
        if getattr(stored, field_name) != getattr(wanted, field_name)
    ]
    if stored.model_identity != wanted.model_identity and stored.model_identity and wanted.model_identity:
        # O caminho e o mesmo e o arquivo nao: e o caso de ter treinado no meio da exportacao,
        # e sem esta linha a mensagem diria "model_identity mudou" sem dizer o que isso quer
        # dizer para quem esta olhando.
        changes.append("o arquivo do modelo mudou desde o parcial (houve treino?)")
    return "; ".join(changes) or "sem diferença aparente"
