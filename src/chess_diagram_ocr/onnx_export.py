"""Exportação para ONNX e backend alternativo de inferência (S-30).

**O que isto resolve.** O torch instalado é `2.10.0+cpu`: sem CUDA, toda inferência roda
em CPU eager. Em CPU, o ONNX Runtime costuma render 2 a 4× sobre o torch eager para
modelos pequenos como este, porque funde convolução+BN+ReLU e dispensa o overhead de
despacho do autograd. Isso importa no modo interativo (a UI reconhece a página a cada
clique) e importa na distribuição empacotada da S-36, onde levar o torch inteiro custa
~200 MB contra ~15 MB do runtime.

**O que isto não resolve.** Não é aceleração de treino. E não substitui a wheel CUDA:
numa máquina com GPU, instalar `torch` com CUDA continua sendo o ganho maior (ver
`docs/` e a mensagem de `describe_device`).

O critério de aceite da S-30 é rigoroso de propósito -- saída idêntica ao torch em
tolerância de 1e-4 sobre o conjunto de teste. Um backend que fosse 3× mais rápido e
divergisse na terceira casa produziria outras FENs, e "mais rápido" não vale isso.

**O `.onnx` sai com o contrato ao lado.** Sozinho ele não diz os nomes das classes, o preparo
da casa, a ordem de leitura nem a temperatura -- tudo isso morava no `.pt` irmão e neste
código, e outro programa não tinha de onde tirar. O `<nome>.json` que `export_onnx` grava
junto diz, amarrado ao `.onnx` pelo SHA-256, e `leitor_de_diagrama_onnx.py` é quem o lê: um
arquivo só, sem torch e sem este pacote, que um editor de outro projeto copia.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .atomic_io import atomic_write_path, atomic_write_text
from .checkpoint import Checkpoint, describe_checkpoint, load_checkpoint
from .config import APPLY_CALIBRATED_TEMPERATURE, BOARD_SIZE, PIECE_CLASSES
from .leitor_de_diagrama_onnx import (
    Contrato,
    ContratoInvalido,
    caminho_do_contrato,
    ler_contrato,
    sha256_do_arquivo,
)
from .model import DEFAULT_ARCH, SQUARES_PER_BOARD, ArchConfig, build_model

logger = logging.getLogger(__name__)

ONNX_OPSET = 17
INPUT_NAME = "cells"
OUTPUT_NAME = "logits"


def _recusar_json_alheio(output_path: Path) -> None:
    """O contrato não sobrescreve um `.json` que não seja outro contrato.

    `--output models/char_meta.onnx` gravaria o contrato por cima do metadado do classificador
    de caracteres, e o texto deixaria de abrir sem que nada aqui acusasse. Conferido **antes** de
    exportar, para não deixar um `.onnx` sem par.
    """
    contrato = caminho_do_contrato(output_path)
    if not contrato.exists():
        return
    try:
        Contrato.de_dicionario(json.loads(contrato.read_text(encoding="utf-8")), contrato.name)
    except (OSError, ValueError) as exc:
        raise FileExistsError(
            f"{contrato} já existe e não é um contrato de exportação ONNX; escolha outro --output."
        ) from exc


def export_onnx(model_path: Path, output_path: Path, *, arch: ArchConfig | None = None) -> Path:
    """Grava o checkpoint como ONNX com eixo de lote dinâmico, e o contrato `.json` ao lado.

    O lote é dinâmico porque o pipeline chama o modelo com 64 casas (um tabuleiro), 448
    (um tabuleiro com TTA) e 512 (oito tabuleiros na avaliação). Um eixo fixo obrigaria a
    preencher ou reexportar.
    """
    model_path, output_path = Path(model_path), Path(output_path)
    _recusar_json_alheio(output_path)
    checkpoint = load_checkpoint(model_path, map_location="cpu")
    if arch is None:
        arch = ArchConfig.from_version(checkpoint.arch_version) if checkpoint.arch_version else DEFAULT_ARCH

    model = build_model(arch, pretrained=False)
    model.load_state_dict(checkpoint.state, strict=True)
    model.eval()

    # Uma casa basta para tracar as cabecas por casa. A da S-62b precisa das 64 juntas -- e o
    # eixo dinamico passa a contar tabuleiros, nao casas: exportar com 1 casa nao falharia no
    # export, falharia na primeira inferencia, que e o pior lugar para descobrir isso.
    cells_in_example = SQUARES_PER_BOARD if arch.head == "board" else 1
    example = torch.zeros(cells_in_example, arch.in_channels, arch.image_size, arch.image_size)
    atomic_write_path(
        output_path,
        lambda temporario: torch.onnx.export(
            model,
            (example,),
            str(temporario),
            input_names=[INPUT_NAME],
            output_names=[OUTPUT_NAME],
            dynamic_axes={INPUT_NAME: {0: "batch"}, OUTPUT_NAME: {0: "batch"}},
            opset_version=ONNX_OPSET,
            # Exportador TorchScript, nao o dynamo. O dynamo e o padrao no torch 2.10 e exige
            # `onnxscript`, uma dependencia a mais para um extra que existe justamente para
            # reduzir o que a distribuicao empacotada (S-36) precisa carregar. Esta rede sao
            # tres blocos conv e uma cabeca linear -- nao ha nada aqui que o tracing perca.
            #
            # Este caminho esta marcado como deprecado pelo torch e um dia sai. Quando sair, a
            # migracao e remover este argumento e acrescentar `onnxscript` ao extra `onnx`; o
            # `cvoff-export-onnx` confere paridade de 1e-4 contra o torch, entao a troca e
            # verificavel em um comando.
            dynamo=False,
        ),
    )
    contrato = contrato_da_exportacao(checkpoint, arch, output_path)
    atomic_write_text(
        caminho_do_contrato(output_path), json.dumps(contrato.como_dicionario(), indent=2, ensure_ascii=False) + "\n"
    )
    logger.info(
        "ONNX gravado em %s com o contrato em %s (arquitetura %s, opset %d, %.1f MB). Temperatura "
        "%.4f NÃO vai no grafo: ela vai no contrato e é aplicada sobre os logits por quem chama.",
        output_path,
        caminho_do_contrato(output_path).name,
        arch.version,
        ONNX_OPSET,
        output_path.stat().st_size / 1e6,
        checkpoint.temperature,
    )
    return output_path


def contrato_da_exportacao(checkpoint: Checkpoint, arch: ArchConfig, onnx_path: Path) -> Contrato:
    """O que outro programa precisa para usar o `.onnx` sem ler este código.

    A origem leva o nome do `.pt`, não o caminho: o contrato viaja para outra máquina, e um
    caminho absoluto só publicaria a pasta de quem exportou.
    """
    origem = describe_checkpoint(checkpoint.path).as_dict()
    origem["path"] = Path(checkpoint.path).name
    return Contrato(
        onnx_sha256=sha256_do_arquivo(onnx_path),
        arquitetura=arch.version,
        classes=tuple(PIECE_CLASSES),
        canais=arch.channels,
        lado_da_casa=arch.image_size,
        coordenadas=arch.coords,
        lote_multiplo_de=SQUARES_PER_BOARD if arch.head == "board" else 1,
        temperatura=float(checkpoint.temperature),
        lado_do_tabuleiro=BOARD_SIZE,
        nome_da_entrada=INPUT_NAME,
        nome_da_saida=OUTPUT_NAME,
        opset=ONNX_OPSET,
        temperatura_aplicada_pelo_programa=APPLY_CALIBRATED_TEMPERATURE,
        origem=origem,
    )


class OnnxPieceClassifier:
    """Adaptador com a mesma superfície que o pipeline usa de um `nn.Module`.

    `board_probabilities` só precisa de três coisas do modelo: ser chamável com um tensor,
    ter `.arch` e ter `.temperature`. Implementar exatamente isso -- em vez de herdar de
    `nn.Module` -- deixa o backend trocável sem que nada mais no código saiba.
    """

    def __init__(self, onnx_path: Path, arch: ArchConfig, *, temperature: float = 1.0, providers: list[str] | None = None):
        import onnxruntime  # importado aqui: o pacote e opcional

        self.arch = arch
        self.temperature = temperature
        self.path = Path(onnx_path)
        options = onnxruntime.SessionOptions()
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = onnxruntime.InferenceSession(
            str(onnx_path), options, providers=providers or ["CPUExecutionProvider"]
        )
        self._input = self.session.get_inputs()[0].name

    def __call__(self, batch: torch.Tensor) -> torch.Tensor:
        logits = self.session.run(None, {self._input: batch.detach().cpu().numpy().astype(np.float32)})[0]
        return torch.from_numpy(logits)

    def eval(self) -> OnnxPieceClassifier:
        return self

    def to(self, device: str) -> OnnxPieceClassifier:
        if device != "cpu":
            logger.warning("Sessão ONNX foi criada para CPU; ignorando pedido de %s.", device)
        return self


def load_onnx_model(onnx_path: Path, checkpoint_path: Path | None = None) -> tuple[OnnxPieceClassifier, str]:
    """Carrega o ONNX, com arquitetura e temperatura do contrato `.json`, ou do `.pt` irmão sem ele.

    **O contrato vence o `.pt`.** O `.pt` de mesmo nome é reescrito a cada treino (S-57), e um
    `.onnx` exportado antes passaria a ler a temperatura do modelo novo. O contrato está preso a
    este `.onnx` pelo SHA-256 e recusa outro arquivo. O caminho pelo `.pt` fica para o `.onnx`
    exportado antes de o contrato existir.
    """
    onnx_path = Path(onnx_path)
    if caminho_do_contrato(onnx_path).exists():
        contrato = ler_contrato(onnx_path)
        if list(contrato.classes) != list(PIECE_CLASSES):
            raise ContratoInvalido(
                f"{caminho_do_contrato(onnx_path).name} declara as classes {list(contrato.classes)}, e o "
                f"programa decodifica pelas {list(PIECE_CLASSES)}: cada índice viraria outra peça."
            )
        arch = ArchConfig.from_version(contrato.arquitetura)
        return OnnxPieceClassifier(onnx_path, arch, temperature=contrato.temperatura), "cpu"

    arch, temperature = DEFAULT_ARCH, 1.0

    sibling = checkpoint_path or onnx_path.with_suffix(".pt")
    if Path(sibling).exists():
        checkpoint = load_checkpoint(Path(sibling), map_location="cpu")
        arch = ArchConfig.from_version(checkpoint.arch_version) if checkpoint.arch_version else DEFAULT_ARCH
        temperature = checkpoint.temperature
    else:
        logger.warning(
            "Sem contrato .json nem checkpoint .pt ao lado de %s: assumindo arquitetura %s e "
            "temperatura 1,0. Se o ONNX for de outra arquitetura, a inferência sai errada em "
            "silêncio; exporte de novo com `cvoff-export-onnx` para ter o contrato.",
            onnx_path.name,
            arch.version,
        )

    return OnnxPieceClassifier(onnx_path, arch, temperature=temperature), "cpu"


@dataclass
class ParityReport:
    """Comparação numérica entre torch e ONNX sobre as mesmas entradas."""

    samples: int
    max_abs_diff: float
    mean_abs_diff: float
    argmax_disagreements: int
    tolerance: float

    @property
    def passes(self) -> bool:
        return self.max_abs_diff <= self.tolerance and self.argmax_disagreements == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "samples": self.samples,
            "max_abs_diff": self.max_abs_diff,
            "mean_abs_diff": self.mean_abs_diff,
            "argmax_disagreements": self.argmax_disagreements,
            "tolerance": self.tolerance,
            "passes": self.passes,
        }


def compare_backends(
    torch_model: torch.nn.Module,
    onnx_model: OnnxPieceClassifier,
    batches: list[torch.Tensor],
    *,
    tolerance: float = 1e-4,
) -> ParityReport:
    """Roda os dois backends nas mesmas entradas e mede a divergência.

    Compara **probabilidades**, não logits: é o que o resto do pipeline consome, e é onde
    a tolerância de 1e-4 da S-30 tem significado. Conta também as discordâncias de argmax,
    porque uma divergência pequena exatamente num empate muda a classe -- e aí a FEN muda,
    por mais que o número pareça desprezível.
    """
    max_diff = 0.0
    total_diff = 0.0
    total = 0
    disagreements = 0

    torch_model.eval()
    for batch in batches:
        with torch.inference_mode():
            reference = torch.softmax(torch_model(batch), dim=1).cpu().numpy().astype(np.float64)
        candidate = torch.softmax(onnx_model(batch), dim=1).numpy().astype(np.float64)

        diff = np.abs(reference - candidate)
        max_diff = max(max_diff, float(diff.max()))
        total_diff += float(diff.sum())
        total += diff.size
        disagreements += int((reference.argmax(axis=1) != candidate.argmax(axis=1)).sum())

    return ParityReport(
        samples=sum(int(batch.shape[0]) for batch in batches),
        max_abs_diff=max_diff,
        mean_abs_diff=total_diff / total if total else 0.0,
        argmax_disagreements=disagreements,
        tolerance=tolerance,
    )


def num_classes() -> int:
    return len(PIECE_CLASSES)
