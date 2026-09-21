"""O sidecar de proveniência do PGN exportado (A11 do ciclo 2 OCR/UI, X4 da análise).

**O que o PGN perde.** Os headers do PGN carregam `SourcePDF`, `Page`, `Diagram`,
`OCRMinConfidence`, `SideToMoveSource`, `DetectionSource`, `OCRProblems`, `OCRRotation` -- e
nada mais cabe num header sem virar ruído: a confiança das 64 casas, o retângulo na página, o
hash do recorte, o modelo que leu, o perfil do livro, as casas que o decodificador, a tinta ou
o lance seguinte trocaram, o que a pessoa declarou na galeria. Tudo isso existe no momento da
exportação e morria ali.

**O sidecar é aditivo.** Um JSONL ao lado do PGN (`<nome>.proveniencia.jsonl`): a primeira
linha é o cabeçalho (versão, PDF e seu hash, modelo, perfil, gate, data), cada linha seguinte
é um diagrama, e o PGN aponta para ele por dois headers -- `[ProvenanceFile]` e
`[ProvenanceKey]`. Quem não lê o sidecar não perde nada do que o PGN já dizia.

**A chave é estável por construção, não por conteúdo.** `p<página>:d<índice>` -- a mesma
identidade que numera os diagramas na tela e no `[Diagram]` desde a S-14, e que o A3 do ciclo
2 usa para casar a decisão humana com o diagrama (página + retângulo). **Não** é a FEN: duas
posições iguais em páginas diferentes são dois diagramas, com dois recortes, duas leituras e
duas confianças, e uma chave por FEN os fundiria -- é a colisão que `verificar` acusa e que a
sabotagem do passo produz de propósito.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSAO = 1
SUFIXO = ".proveniencia.jsonl"


class ColisaoDeProveniencia(ValueError):
    """Duas linhas do sidecar com a mesma chave: dois diagramas virariam um."""


def sidecar_path(output_path: Path | str) -> Path:
    """`Livro.pgn` → `Livro.proveniencia.jsonl`, na mesma pasta."""
    saida = Path(output_path)
    return saida.with_name(saida.stem + SUFIXO)


def chave(page_index: int, diagram_index: int) -> str:
    return f"p{int(page_index)}:d{int(diagram_index)}"


def hash_do_arquivo(path: Path | str | None) -> str:
    """SHA-256 do PDF -- o mesmo `content_hash` da suíte; vazio sem arquivo."""
    if path is None:
        return ""
    arquivo = Path(path)
    if not arquivo.is_file():
        return ""
    digest = hashlib.sha256()
    with arquivo.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Cabecalho:
    """A primeira linha do sidecar: o que valia para todas as posições."""

    source_name: str
    source_hash: str = ""
    model_identity: str = ""
    model_path: str = ""
    profile: dict[str, Any] = field(default_factory=dict)
    accept_threshold: float | None = None
    dpi: int | None = None
    exported_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "header", "version": VERSAO, "source_name": self.source_name,
            "source_hash": self.source_hash, "model_identity": self.model_identity,
            "model_path": self.model_path, "profile": dict(self.profile),
            "accept_threshold": self.accept_threshold, "dpi": self.dpi,
            "exported_at": self.exported_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **self.extra,
        }


def registro(position: Any, *, verdict: str = "", reason: str = "",
             annotation: Any = None) -> dict[str, Any]:
    """Uma linha do sidecar a partir de uma `DiagramPosition` (e da anotação da galeria)."""
    side = getattr(position, "side_to_move", None)
    context = getattr(position, "context", None)
    human: dict[str, Any] | None = None
    if annotation is not None:
        human = {
            "move_number": getattr(annotation, "move_number", None),
            "side_to_move": getattr(annotation, "side_to_move", None),
            "headers": dict(getattr(annotation, "headers", {}) or {}),
            "filled_from": getattr(annotation, "filled_from", ""),
            "confirmed_from": getattr(annotation, "confirmed_from", ""),
        }
    return {
        "kind": "diagram",
        "key": chave(position.page_index, position.diagram_index),
        "page_index": int(position.page_index),
        "diagram_index": int(position.diagram_index),
        "rect": list(position.bbox_pdf) if getattr(position, "bbox_pdf", None) else None,
        "image_hash": getattr(position, "image_hash", "") or "",
        "placement": position.fen,
        "fen": position.full_fen,
        "side": None if side is None else {
            "color": "w" if getattr(side, "color", True) else "b",
            "source": str(getattr(side, "source", "")),
            "reason": getattr(side, "reason", ""),
            "conflicting": bool(getattr(side, "conflicting", False)),
        },
        "confidence": getattr(position, "confidence", None),
        "min_confidence": getattr(position, "min_confidence", None),
        "gate_confidence": getattr(position, "gate_confidence", None),
        "square_confidences": [round(float(c), 4) for c in (getattr(position, "square_confidences", ()) or ())],
        "repairs": [list(r) for r in (getattr(position, "repairs", ()) or ())],
        "colour_repairs": list(getattr(position, "colour_repairs", ()) or ()),
        "next_move": getattr(position, "next_move", "") or "",
        "next_move_repairs": list(getattr(position, "next_move_repairs", ()) or ()),
        "is_legal": getattr(position, "is_legal", None),
        "is_fatal": getattr(position, "is_fatal", None),
        "problems": list(getattr(position, "problems", ()) or ()),
        "rotation": getattr(position, "rotation", None),
        "orientation_ambiguous": bool(getattr(position, "orientation_ambiguous", False)),
        "orientation_reason": getattr(position, "orientation_reason", ""),
        "detection_source": getattr(position, "detection_source", None),
        "duplicate_of": list(position.duplicate_of) if getattr(position, "duplicate_of", None) else None,
        "verdict": verdict,
        "reason": reason,
        "caption": (getattr(context, "caption", "") or "") if context is not None else "",
        "exercise_number": getattr(context, "exercise_number", None) if context is not None else None,
        "first_moves_text": (getattr(context, "first_moves_text", "") or "") if context is not None else "",
        "human": human,
    }


def verificar(registros: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """As linhas por chave; levanta `ColisaoDeProveniencia` se duas partilham a chave."""
    por_chave: dict[str, Mapping[str, Any]] = {}
    for linha in registros:
        if linha.get("kind") != "diagram":
            continue
        key = str(linha.get("key", ""))
        if not key:
            raise ColisaoDeProveniencia("linha de diagrama sem chave")
        if key in por_chave:
            outra = por_chave[key]
            raise ColisaoDeProveniencia(
                f"chave {key!r} repetida: página {outra.get('page_index')} diagrama "
                f"{outra.get('diagram_index')} e página {linha.get('page_index')} diagrama "
                f"{linha.get('diagram_index')} virariam um só")
        por_chave[key] = linha
    return por_chave


def write_sidecar(
    positions: Sequence[tuple[Any, str, str]],
    output_path: Path | str,
    *,
    cabecalho: Cabecalho,
    annotations: Mapping[tuple[int, int], Any] | None = None,
    key_of: Any = None,
) -> Path:
    """Grava o sidecar ao lado de `output_path` (o PGN) e devolve o caminho.

    `positions` são triplas `(posição, veredito, motivo)` -- aceitas e de revisão juntas: o
    sidecar é do livro exportado inteiro, e o `.review.pgn` aponta para o mesmo arquivo.
    `key_of` troca a chave (só a sabotagem do passo o faz: por FEN, para a colisão aparecer).
    """
    linhas: list[dict[str, Any]] = [cabecalho.as_dict()]
    for position, verdict, reason in positions:
        annotation = (annotations or {}).get((position.page_index, position.diagram_index))
        linha = registro(position, verdict=verdict, reason=reason, annotation=annotation)
        if key_of is not None:
            linha["key"] = str(key_of(position))
        linhas.append(linha)
    verificar(linhas)
    destino = sidecar_path(output_path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as handle:
        for linha in linhas:
            handle.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return destino


def read_sidecar(path: Path | str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """`(cabeçalho, {chave: linha})`; levanta `ColisaoDeProveniencia` em chave repetida."""
    cabecalho: dict[str, Any] = {}
    linhas: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            linha = json.loads(raw)
            if linha.get("kind") == "header":
                cabecalho = linha
            else:
                linhas.append(linha)
    return cabecalho, dict(verificar(linhas))
