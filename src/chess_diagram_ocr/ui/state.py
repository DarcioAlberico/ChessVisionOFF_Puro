"""Estado persistido da aplicação, tipado, versionado e gravado de forma atômica (S-25).

Três problemas concretos que este módulo substitui, todos medidos no `app_tkinter.py`:

1. **Gravação não atômica.** `_save_app_state` fazia read-modify-write com
   `path.write_text`, que trunca antes de escrever. Fechar o app (ou a máquina) nesse
   intervalo deixava `data/app_tkinter_state.json` com 0 byte -- e o app seguinte perdia o
   último PDF sem nenhuma pista do porquê. Ver `atomic_io`.

2. **Silêncio no descarte.** `_load_app_state` devolvia `False` para qualquer problema, do
   arquivo corrompido ao PDF que mudou de lugar. Os dois casos merecem tratamento
   diferente e nenhum merece silêncio: agora o inválido gera `warning` com o motivo.

3. **Duas leituras do mesmo arquivo.** `load_pdf` reabria o JSON por conta própria só para
   consultar `pdf_history`, com o seu próprio `try/except`. Uma cópia da lógica de leitura
   é uma cópia dos bugs dela.

O esquema é versionado desde já porque a Fase 4 acrescenta campos (fila de revisão,
heatmap) e a Fase 6 vai acrescentar mais. Estado de versão futura é **descartado**, não
adivinhado: um app antigo lendo campo novo pela metade é pior que um app antigo começando
limpo.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

STATE_VERSION = 2
"""Versão 1 é o formato sem o campo `version`, que existe em disco hoje."""

MAX_PDF_HISTORY = 50
"""Tamanho do histórico de páginas por PDF. Sem teto ele cresce para sempre."""


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class AppState:
    """O que a aplicação lembra entre execuções."""

    last_pdf: str = ""
    last_page: int = 0
    pdf_zoom: float = 0.7
    board_zoom: float = 0.85
    pdf_history: dict[str, int] = field(default_factory=dict)
    """Última página vista por PDF, indexado pelo caminho absoluto."""

    show_heatmap: bool = True
    """Heatmap de incerteza ligado no tabuleiro de resultado (S-21)."""

    review_queue_path: str = ""
    """Fila de revisão aberta por último (S-22). Vazio = nenhuma."""

    def page_for(self, pdf_path: Path) -> int:
        """Página em que este PDF foi deixado. 0 se ele nunca foi aberto."""
        return int(self.pdf_history.get(_history_key(pdf_path), 0))

    def remember_page(self, pdf_path: Path, page_index: int) -> None:
        key = _history_key(pdf_path)
        history = self.pdf_history
        history.pop(key, None)
        history[key] = int(page_index)
        while len(history) > MAX_PDF_HISTORY:
            # dict preserva ordem de insercao: o primeiro e o menos recentemente tocado.
            history.pop(next(iter(history)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "last_pdf": self.last_pdf,
            "last_page": int(self.last_page),
            "pdf_zoom": float(self.pdf_zoom),
            "board_zoom": float(self.board_zoom),
            "pdf_history": {str(key): int(value) for key, value in self.pdf_history.items()},
            "show_heatmap": bool(self.show_heatmap),
            "review_queue_path": self.review_queue_path,
        }


def _history_key(pdf_path: Path) -> str:
    try:
        return str(Path(pdf_path).resolve())
    except OSError:
        # Caminho de rede fora do ar: o não resolvido ainda serve de chave.
        return str(pdf_path)


def _migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Traz um estado de versão anterior para o esquema corrente.

    A versão 1 (sem o campo `version`) já tinha `last_pdf`, `last_page`, `pdf_zoom` e
    `pdf_history` com os mesmos significados -- migrar é só reconhecê-la, e é por isso que
    a numeração começa nela em vez de fingir que o formato antigo não existiu.
    """
    version = raw.get("version", 1)
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"campo `version` inválido: {version!r}")
    if version > STATE_VERSION:
        raise ValueError(f"estado gravado por versão mais nova ({version} > {STATE_VERSION})")
    return raw


def state_from_dict(raw: dict[str, Any]) -> AppState:
    """Constrói o estado a partir do dicionário lido, ignorando campo de tipo errado.

    Campo com tipo inesperado cai para o padrão em vez de derrubar a leitura inteira: uma
    entrada estragada no histórico não deve custar ao usuário o último PDF aberto.
    """
    raw = _migrate(raw)
    state = AppState()

    last_pdf = raw.get("last_pdf")
    if isinstance(last_pdf, str):
        state.last_pdf = last_pdf

    last_page = raw.get("last_page")
    if isinstance(last_page, int) and not isinstance(last_page, bool):
        state.last_page = max(0, last_page)

    pdf_zoom = raw.get("pdf_zoom")
    if isinstance(pdf_zoom, (int, float)) and not isinstance(pdf_zoom, bool):
        state.pdf_zoom = _clamp(float(pdf_zoom), 0.25, 2.0)

    board_zoom = raw.get("board_zoom")
    if isinstance(board_zoom, (int, float)) and not isinstance(board_zoom, bool):
        state.board_zoom = _clamp(float(board_zoom), 0.45, 1.8)

    history = raw.get("pdf_history")
    if isinstance(history, dict):
        state.pdf_history = {
            str(key): int(value)
            for key, value in history.items()
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        }

    show_heatmap = raw.get("show_heatmap")
    if isinstance(show_heatmap, bool):
        state.show_heatmap = show_heatmap

    queue_path = raw.get("review_queue_path")
    if isinstance(queue_path, str):
        state.review_queue_path = queue_path

    return state


def load_state(path: Path) -> AppState:
    """Lê o estado. Arquivo ausente ou inválido devolve o padrão -- e diz por quê no log."""
    path = Path(path)
    if not path.exists():
        return AppState()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Estado da aplicação descartado (%s): %s", path, exc)
        return AppState()

    if not isinstance(raw, dict):
        logger.warning("Estado da aplicação descartado (%s): esperado objeto JSON, veio %s", path, type(raw).__name__)
        return AppState()

    try:
        return state_from_dict(raw)
    except ValueError as exc:
        logger.warning("Estado da aplicação descartado (%s): %s", path, exc)
        return AppState()


def save_state(path: Path, state: AppState) -> None:
    """Grava o estado de forma atômica. Falha de escrita é registrada, não propagada.

    Não derrubar a aplicação por causa do estado é a decisão que já existia; o que muda é
    que a falha agora aparece no log com o caminho, em vez de sumir.
    """
    try:
        atomic_write_json(Path(path), state.to_dict())
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Não foi possível salvar o estado da aplicação em %s: %s", path, exc)
