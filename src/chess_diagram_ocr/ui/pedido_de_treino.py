"""Os parâmetros do treino e como uma época é lida (S-27/S-310/S-503).

`TrainingRequest`, `format_metrics` e `summarize_run`. As três eram puras dentro de
`ui/training_dialog.py`, e o docstring de `format_metrics` já dizia por quê: *"a ordem é uma
decisão de projeto, e trocá-la sem perceber é fácil"*.

**A ordem é a decisão inteira.** `val_board_exact_acc` vem primeiro porque é ela que decide qual
época é salva; a acurácia por casa fica em ~0,999 mesmo quando um em cada vinte tabuleiros sai com
erro, e mostrá-la primeiro faria quem olha ler um número ótimo sobre um treino medíocre. Duas
janelas com duas ordens seriam duas leituras do mesmo treino, e a errada é a convincente.

Diferente dos outros módulos abertos na S-503, este não estava atrás de uma classe-base: o
`ui/training_dialog.py` importa `tkinter` no topo porque o `TrainingController` monta um
`tk.Toplevel` -- o import é do módulo, não da herança. O efeito para quem lê é o mesmo.

`ui/training_dialog.py` reexporta tudo o que está aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..training import TrainingRun

__all__ = ["TrainingRequest", "format_metrics", "summarize_run"]
@dataclass(frozen=True)
class TrainingRequest:
    """Os parâmetros do treino lidos da tela, para não viajarem soltos entre threads.

    Congelados no momento do clique de propósito: mexer nos spinboxes com o treino em
    andamento não pode mudar o que já está rodando.
    """

    csv_path: Path
    samples_dir: Path
    model_path: Path
    epochs: int
    batch_size: int
    lr: float
    fresh: bool = False
    splits_path: Path | None = None


def format_metrics(row: dict[str, Any]) -> str:
    """Uma linha de métricas de época, na ordem que a S-27 decidiu.

    Testável sem Tk, e é o que de fato vale a pena travar: a ordem é uma decisão de projeto,
    e trocá-la sem perceber é fácil.
    """
    partes: list[str] = []
    epoca = row.get("epoch")
    if epoca is not None:
        partes.append(f"época={epoca}")
    for chave, rotulo in (
        ("val_board_exact_acc", "exata/tabuleiro"),
        ("train_loss", "train_loss"),
        ("train_square_acc", "train_acc"),
        ("val_loss", "val_loss"),
        ("val_square_acc", "val_acc/casa"),
    ):
        if chave in row:
            partes.append(f"{rotulo}={float(row[chave]):.4f}")
    if row.get("is_best"):
        partes.append("(melhor até agora)")
    return " | ".join(partes)


def summarize_run(run: TrainingRun) -> str:
    """Resumo do checkpoint que ficou no disco -- a **melhor** época, não a última.

    Mostrar a última faria o usuário ler uma métrica que não corresponde ao arquivo salvo:
    desde a S-27 o treino só grava por cima quando melhora.

    **A melhor época é a que `is_best` marca, e não `history[best_epoch - 1]` (S-310).** Os dois
    coincidem num treino do zero e divergem em toda retomada: `best_epoch` é do **checkpoint**,
    e pode valer 7 sobre um histórico de duas épocas -- o `IndexError` daí subia como "Falha no
    treino" ao fim de um treino bem-sucedido. E quando não estoura, mente: indexa a época errada
    desta execução e mostra a métrica dela.

    Nenhuma época melhor que o incumbente é um resultado, e não uma falha: aí o resumo fica
    vazio de propósito, e quem diz o que aconteceu é a frase de status.
    """
    melhores = [linha for linha in run.history if linha.get("is_best")]
    melhor = melhores[-1] if melhores else {}
    resumo = format_metrics(melhor)
    if run.ece_after is not None:
        resumo += f" | T={run.temperature:.3f}"
    return resumo

