"""A hora que se grava, e como se compara a que já foi gravada (S-908).

**Hora gravada leva o deslocamento.** `datetime.now().isoformat()` escreve a hora de parede sem dizer
de que fuso ela é: na hora repetida da volta do horário de verão, ou depois de trocar o fuso da
máquina, `02:30` pode ser anterior a `02:10`. O caderno comparava essas strings para decidir se um
rascunho era mais novo que a folha, e quem perdia era apagado. Aqui a hora sai com o deslocamento
local (`2026-11-08T14:02:11-03:00`): continua legível, `[11:16]` continua sendo a hora de parede, e
dois instantes se comparam como instantes.

**Ler aceita os dois formatos.** Os arquivos já gravados no disco do dono não têm deslocamento; valem
como a hora local daquele momento, que é o que eles sempre quiseram dizer. Hora ilegível vira `None`,
e quem compara decide o que a falta de hora quer dizer.

A guarda em `tests/test_relogio.py` acusa `datetime.now()` sem fuso e `fromtimestamp` sem `tz` no
resto de `src/`.
"""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["agora", "agora_iso", "com_fuso", "do_arquivo", "ler_iso"]


def agora() -> datetime:
    """Agora, em hora local com fuso. Para nome de arquivo, `agora():%Y%m%d_%H%M%S` dá a hora de parede."""
    return datetime.now(timezone.utc).astimezone()


def agora_iso() -> str:
    """Agora, em hora local com deslocamento, ao segundo: o que se grava num arquivo."""
    return agora().isoformat(timespec="seconds")


def do_arquivo(mtime: float) -> datetime:
    """O instante de um `st_mtime`, em hora local com fuso."""
    return datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone()


def com_fuso(instante: datetime) -> datetime:
    """`instante` com fuso: o ingênuo vale como hora local daquele momento."""
    return instante if instante.tzinfo is not None else instante.astimezone()


def ler_iso(texto: str) -> datetime | None:
    """Uma hora ISO gravada, com ou sem deslocamento, como instante com fuso. `None` se ilegível."""
    bruto = (texto or "").strip()
    if bruto.endswith("Z"):  # `fromisoformat` só aceita o `Z` a partir do 3.11
        bruto = bruto[:-1] + "+00:00"
    try:
        return com_fuso(datetime.fromisoformat(bruto))
    except (ValueError, OverflowError, OSError):  # o Windows recusa hora local antes de 1970
        return None
