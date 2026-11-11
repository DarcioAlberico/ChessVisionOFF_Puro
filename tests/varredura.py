"""Os arquivos que uma guarda de varredura lê, com piso (S-871).

**Uma varredura que não acha nada passa.** Um glob sobre uma pasta que mudou de lugar devolve a
lista vazia, e a guarda que percorre essa lista fica verde sobre nada -- foi o que aconteceu no
corte do Tk, quando a varredura de threads continuou apontando para `ui/` e passou a ver zero
threads (memória "guarda de varredura fica vácua no corte"). O piso é o número abaixo do qual a
lista deixa de ser o universo que a guarda diz varrer: abaixo dele a guarda reprova, e não
absolve.

O piso fica abaixo do número de hoje com folga para tirar alguns arquivos, e não para achar zero;
quando a pasta encolher de verdade, desce-se o piso no mesmo commit, e o número de hoje fica no
comentário de quem chama.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PACOTE = RAIZ / "src" / "chess_diagram_ocr"


def fontes(pasta: Path, padrao: str = "*.py", *, piso: int, recursivo: bool = False) -> list[Path]:
    """Os arquivos de `pasta` que casam com `padrao`, em ordem; reprova se forem menos que `piso`."""
    achados = sorted(pasta.rglob(padrao) if recursivo else pasta.glob(padrao))
    if len(achados) < piso:
        raise AssertionError(
            f"a varredura de {pasta} ({padrao}) achou {len(achados)} arquivo(s), abaixo do piso {piso}: "
            "a pasta mudou de lugar ou o padrão deixou de casar, e a guarda passaria verde sobre nada"
        )
    return achados


def da_interface() -> list[Path]:
    """Os `.py` de `ui/` e de `qt/`, o universo de quase toda guarda de interface.

    80 em `ui/` e 89 em `qt/` em 2026-11-09.
    """
    return fontes(PACOTE / "ui", piso=60) + fontes(PACOTE / "qt", piso=60)
