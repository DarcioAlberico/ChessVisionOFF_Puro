"""Grade de experimentos de arquitetura, um fator por vez (S-29).

**A regra que a spec impõe e que este módulo torna executável:** cada variante treina do
zero, com a mesma semente e o mesmo split, e é comparada no mesmo conjunto -- e o
resultado é registrado **inclusive quando não ajuda**. Um experimento que não é registrado
vira folclore ("acho que RGB não funcionou"), e folclore custa a próxima pessoa refazê-lo.

**Onde comparar.** No `val`, não no `test`. O `test` é usado uma vez, no fim, pela variante
vencedora. Escolher arquitetura olhando o `test` transforma o conjunto reservado em
conjunto de validação com passos extras -- e é o erro que a Fase 1 inteira existe para
impedir. O `BASELINE.md` já avisa que 0,9906 vem de 3 erros em 320 e que ±1 ponto é ruído;
uma grade de 8 variantes escolhida no teste encontraria "vencedores" dentro desse ruído.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .evaluation import evaluate_split
from .model import ArchConfig, build_model, count_parameters
from .training import ClassWeighting, train_model

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Variant:
    """Uma linha da grade: o que muda em relação à referência, e só isso."""

    name: str
    factor: str
    """O fator da tabela da S-29 que esta variante exercita."""

    arch: ArchConfig = field(default_factory=ArchConfig)
    class_weights: ClassWeighting = "none"
    note: str = ""


def default_grid() -> list[Variant]:
    """A grade da S-29, um fator por vez a partir da referência.

    O fator "aumento de dados" da spec (ruído de JPEG, meio-tom de scan) ficou de fora
    desta grade: ele muda a pipeline de `build_train_transform`, não a arquitetura, e
    misturar os dois quebraria o "um fator por vez" que dá sentido à comparação.
    """
    return [
        Variant("referencia", "—", ArchConfig(), note="a arquitetura que produziu o baseline"),
        Variant("rgb", "canais", ArchConfig(channels="rgb"), note="importa em livro com diagrama colorido"),
        Variant("res32", "resolução", ArchConfig(image_size=32)),
        Variant("res48", "resolução", ArchConfig(image_size=48)),
        Variant("gap", "cabeça", ArchConfig(head="gap"), note="2,19 M → ~93 k parâmetros"),
        Variant("mobilenet", "backbone", ArchConfig(backbone="mobilenet_v3_small"), note="pré-treinada na ImageNet"),
        Variant("pesos_balanceados", "pesos de classe", ArchConfig(), class_weights="balanced"),
    ]


@dataclass
class VariantResult:
    name: str
    factor: str
    arch_version: str
    class_weights: str
    parameters: int
    epochs_run: int
    best_epoch: int
    val_board_exact_acc: float
    val_square_acc: float
    val_illegal: int
    temperature: float
    ece_val_before: float | None
    ece_val_after: float | None
    train_seconds: float
    eval_seconds: float
    note: str = ""
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_variant(
    variant: Variant,
    *,
    csv_path: Path,
    samples_dir: Path,
    splits_path: Path,
    splits: dict[str, Any],
    workdir: Path,
    epochs: int,
    seed: int,
    batch_size: int,
    num_workers: int | None,
) -> VariantResult:
    """Treina e avalia uma variante. Uma falha vira uma linha com `error`, não uma exceção.

    Uma variante que não roda (MobileNet sem os pesos pré-treinados em cache, por exemplo)
    é um resultado -- e derrubar a grade inteira por causa dela perderia as outras seis.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    model_path = workdir / f"{variant.name}.pt"

    started = time.perf_counter()
    try:
        run = train_model(
            csv_path=csv_path,
            samples_dir=samples_dir,
            model_path=model_path,
            epochs=epochs,
            batch_size=batch_size,
            splits_path=splits_path,
            fresh=True,
            arch=variant.arch,
            class_weights=variant.class_weights,
            seed=seed,
            num_workers=num_workers,
            patience=0,
        )
    except Exception as exc:  # noqa: BLE001 -- ver docstring
        logger.exception("Variante %s falhou.", variant.name)
        return VariantResult(
            name=variant.name,
            factor=variant.factor,
            arch_version=variant.arch.version,
            class_weights=variant.class_weights,
            parameters=0,
            epochs_run=0,
            best_epoch=0,
            val_board_exact_acc=float("nan"),
            val_square_acc=float("nan"),
            val_illegal=-1,
            temperature=1.0,
            ece_val_before=None,
            ece_val_after=None,
            train_seconds=time.perf_counter() - started,
            eval_seconds=0.0,
            note=variant.note,
            error=f"{type(exc).__name__}: {exc}",
        )
    train_seconds = time.perf_counter() - started

    started = time.perf_counter()
    report = evaluate_split(
        csv_path,
        samples_dir,
        model_path,
        split="val",
        splits=splits,
    )
    eval_seconds = time.perf_counter() - started

    return VariantResult(
        name=variant.name,
        factor=variant.factor,
        arch_version=variant.arch.version,
        class_weights=variant.class_weights,
        parameters=count_parameters(build_model(variant.arch, pretrained=False)),
        epochs_run=len(run.history),
        best_epoch=run.best_epoch,
        val_board_exact_acc=report.board_exact_accuracy,
        val_square_acc=report.square_accuracy,
        val_illegal=report.illegal_predictions,
        temperature=run.temperature,
        ece_val_before=run.ece_before,
        ece_val_after=run.ece_after,
        train_seconds=train_seconds,
        eval_seconds=eval_seconds,
        note=variant.note,
    )


def save_results(results: list[VariantResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([result.as_dict() for result in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Resultados da grade em %s", path)


def markdown_table(results: list[VariantResult], reference: str = "referencia") -> str:
    """A grade como tabela, com o delta em relação à referência já calculado."""
    baseline = next((r for r in results if r.name == reference), None)
    lines = [
        "| variante | fator | parâmetros | exata/tabuleiro (val) | Δ | por casa | ilegais | min/época |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for result in results:
        if result.error:
            lines.append(f"| `{result.name}` | {result.factor} | — | **não rodou** | — | — | — | {result.error} |")
            continue
        delta = ""
        if baseline is not None and not baseline.error and result.name != reference:
            diff = result.val_board_exact_acc - baseline.val_board_exact_acc
            delta = f"{diff:+.4f}"
        minutes = result.train_seconds / 60 / max(result.epochs_run, 1)
        lines.append(
            f"| `{result.name}` | {result.factor} | {result.parameters:,} | "
            f"{result.val_board_exact_acc:.4f} | {delta} | {result.val_square_acc:.6f} | "
            f"{result.val_illegal} | {minutes:.1f} |".replace(",", ".")
        )
    return "\n".join(lines)
