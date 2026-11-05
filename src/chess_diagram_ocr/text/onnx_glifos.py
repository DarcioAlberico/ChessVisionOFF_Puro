"""Exportação do classificador de caracteres para ONNX, com o metadado ao lado (S-30 para o texto).

**Por que existe.** A S-30 exporta só o classificador de peças (`onnx_export.py`). O de
caracteres -- a `SimpleCNN` de 32x32 que lê figurinas, sinais de avaliação e letras -- não tinha
caminho para fora do torch, e quem queria usá-lo em outro programa precisava reconverter à mão,
fora do repositório, sem paridade conferida e sem o mapa de classes amarrado ao arquivo.

**O par continua não podendo se descasar.** É a regra de `text/modelo.py` (S-179): índices de
outro treino apontam para as letras erradas, em silêncio. Por isso o exportador:

1. só exporta pelo `carregar_classificador`, que recusa o `.pt` por hash antes de carregar;
2. grava o `.json` **ao lado** do `.onnx`, com o mapa de classes, a temperatura e o SHA-256 do
   próprio `.onnx`; e
3. quem carrega (`ClassificadorDeGlifoOnnx`) confere esse SHA-256 antes de abrir a sessão.

**A temperatura não vai no grafo**, como na S-30: ela vai no `.json` e é aplicada sobre os
logits por quem chama. Assim o mesmo `.onnx` serve para quem quer a confiança calibrada e para
quem só quer o argmax.

**O consumidor não precisa de torch.** `ClassificadorDeGlifoOnnx` usa só `numpy`, `cv2` e
`onnxruntime` -- é o que permite levar o modelo para um programa empacotado sem os ~200 MB do
torch.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..atomic_io import atomic_write_text
from .modelo import (
    CAMINHO_PADRAO_META,
    LADO,
    ClassificadorDeGlifo,
    ModeloInvalido,
    carregar_classificador,
    impressao_do_arquivo,
)

logger = logging.getLogger(__name__)

ONNX_OPSET = 17
"""O mesmo da S-30: um opset só para os dois modelos do projeto."""

SCHEMA_DO_METADADO_ONNX = 1
"""Versão do `.json` que acompanha o `.onnx`. Sobe quando um campo muda de sentido."""

NOME_DA_ENTRADA = "glifos"
NOME_DA_SAIDA = "logits"


def caminho_do_metadado_onnx(onnx: Path) -> Path:
    """O `.json` mora ao lado do `.onnx`, com o mesmo nome-base: `chess-glyphs.onnx` -> `chess-glyphs.json`."""
    return Path(onnx).with_suffix(".json")


def exportar_glifos_onnx(
    saida: Path,
    meta: Path = CAMINHO_PADRAO_META,
    pesos: Path | None = None,
) -> Path:
    """Grava o classificador de caracteres como ONNX e o metadado ao lado. Devolve o `.onnx`.

    O lote é dinâmico porque a página manda de um a milhares de recortes de uma vez.
    """
    import torch

    classificador = carregar_classificador(meta, pesos, device="cpu")
    rede = classificador._modelo  # noqa: SLF001 -- a rede que o par conferido carregou
    rede.eval()

    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    exemplo = torch.zeros(1, 1, LADO, LADO)
    torch.onnx.export(
        rede,
        (exemplo,),
        str(saida),
        input_names=[NOME_DA_ENTRADA],
        output_names=[NOME_DA_SAIDA],
        dynamic_axes={NOME_DA_ENTRADA: {0: "lote"}, NOME_DA_SAIDA: {0: "lote"}},
        opset_version=ONNX_OPSET,
        # O exportador TorchScript, pelo mesmo motivo da S-30 (ver `onnx_export.py`): o dynamo
        # exige `onnxscript`, e esta rede são três blocos conv e duas densas.
        dynamo=False,
    )

    descricao = _metadado_onnx(classificador, saida)
    atomic_write_text(caminho_do_metadado_onnx(saida), json.dumps(descricao, indent=2, ensure_ascii=False))
    logger.info(
        "Classificador de caracteres exportado: %s (%d classes, opset %d, %.1f MB) e %s.",
        saida.name,
        classificador.meta.num_classes,
        ONNX_OPSET,
        saida.stat().st_size / 1e6,
        caminho_do_metadado_onnx(saida).name,
    )
    return saida


def _metadado_onnx(classificador: ClassificadorDeGlifo, onnx: Path) -> dict[str, Any]:
    """O que outro programa precisa para usar o `.onnx` sem ler este código."""
    meta = classificador.meta
    return {
        "schema_version": SCHEMA_DO_METADADO_ONNX,
        "modelo": "classificador de caracteres (SimpleCNN)",
        "onnx_sha256": impressao_do_arquivo(onnx),
        "opset": ONNX_OPSET,
        "entrada": {
            "nome": NOME_DA_ENTRADA,
            "forma": ["lote", 1, LADO, LADO],
            "tipo": "float32",
            "faixa": [0.0, 1.0],
            "preparo": (
                "recorte em cinza, redimensionado para 32x32 (cv2.resize, interpolação linear), "
                "dividido por 255; tinta escura sobre papel claro, sem binarizar nem inverter"
            ),
        },
        "saida": {
            "nome": NOME_DA_SAIDA,
            "forma": ["lote", meta.num_classes],
            "preparo": "softmax(logits / temperatura) dá a confiança calibrada",
        },
        "num_classes": meta.num_classes,
        "classes": list(meta.alfabeto),
        "temperatura": meta.temperatura,
        "origem": {
            "modelo_sha256": meta.modelo_sha256,
            "classes_sha256": meta.classes_sha256,
            "treinado_em": meta.treinado_em,
            "arquitetura": meta.arquitetura.como_dicionario(),
        },
    }


@dataclass(frozen=True)
class MetadadoOnnx:
    """O `.json` do `.onnx`, já conferido. Construído só por `ler_metadado_onnx`."""

    classes: tuple[str, ...]
    temperatura: float
    onnx_sha256: str


def ler_metadado_onnx(onnx: Path) -> MetadadoOnnx:
    """Lê o `.json` ao lado do `.onnx` e confere que ele descreve **este** arquivo."""
    onnx = Path(onnx)
    caminho = caminho_do_metadado_onnx(onnx)
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ModeloInvalido(
            f"O metadado de {onnx.name} não está em {caminho}. Sem ele não há como traduzir "
            "índice em caractere."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ModeloInvalido(f"{caminho.name} não é um JSON válido: {exc}") from exc

    classes = bruto.get("classes") if isinstance(bruto, dict) else None
    if not isinstance(classes, list) or not classes or not all(isinstance(c, str) and c for c in classes):
        raise ModeloInvalido(f"{caminho.name} não traz a lista `classes`.")
    if bruto.get("num_classes") != len(classes):
        raise ModeloInvalido(f"{caminho.name} declara {bruto.get('num_classes')} classes e lista {len(classes)}.")

    temperatura = bruto.get("temperatura")
    if not isinstance(temperatura, int | float) or not float(temperatura) > 0:
        raise ModeloInvalido(f"{caminho.name} não traz uma `temperatura` positiva.")

    esperado = str(bruto.get("onnx_sha256", "") or "")
    encontrado = impressao_do_arquivo(onnx)
    if esperado != encontrado:
        raise ModeloInvalido(
            f"{onnx.name} não é o modelo descrito por {caminho.name}.\n\n"
            f"  o metadado espera  {esperado or '(nada)'}\n"
            f"  o arquivo tem      {encontrado or '(ilegível)'}\n\n"
            "Os dois precisam sair da mesma exportação: índices de outro treino apontam para as "
            "letras erradas, sem erro e sem aviso."
        )
    return MetadadoOnnx(classes=tuple(classes), temperatura=float(temperatura), onnx_sha256=encontrado)


def preparar_recortes(recortes: list[np.ndarray]) -> np.ndarray:
    """Lote de recortes -> `(n, 1, 32, 32)` float32 em [0, 1], igual a `ClassificadorDeGlifo._entrada`.

    Repetido aqui sem torch de propósito: é o que o consumidor ONNX roda. O teste de paridade
    confere que os dois preparos dão o mesmo número.
    """
    import cv2

    lote = np.empty((len(recortes), 1, LADO, LADO), dtype=np.float32)
    for i, recorte in enumerate(recortes):
        cinza = cv2.cvtColor(recorte, cv2.COLOR_RGB2GRAY) if recorte.ndim == 3 else recorte
        lote[i, 0] = cv2.resize(cinza, (LADO, LADO)).astype(np.float32) / 255.0
    return lote


class ClassificadorDeGlifoOnnx:
    """A mesma superfície de `ClassificadorDeGlifo` (`probabilidades`, `classificar`), sem torch."""

    def __init__(self, onnx: Path, *, providers: list[str] | None = None) -> None:
        import onnxruntime  # importado aqui: o pacote é opcional (extra `onnx`)

        self.caminho = Path(onnx)
        self.meta = ler_metadado_onnx(self.caminho)
        opcoes = onnxruntime.SessionOptions()
        opcoes.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._sessao = onnxruntime.InferenceSession(
            str(self.caminho), opcoes, providers=providers or ["CPUExecutionProvider"]
        )
        self._entrada = self._sessao.get_inputs()[0].name

    def logits(self, lote: np.ndarray) -> np.ndarray:
        if lote.shape[0] == 0:
            return np.empty((0, len(self.meta.classes)), dtype=np.float32)
        return np.asarray(self._sessao.run(None, {self._entrada: lote.astype(np.float32)})[0])

    def probabilidades(self, recortes: list[np.ndarray]) -> np.ndarray:
        """Matriz `(n, num_classes)` já dividida pela temperatura. Vazia para lote vazio."""
        logits = self.logits(preparar_recortes(recortes)) / self.meta.temperatura
        logits -= logits.max(axis=1, keepdims=True) if logits.size else 0.0
        exp = np.exp(logits)
        return (exp / exp.sum(axis=1, keepdims=True)).astype(np.float32) if exp.size else exp.astype(np.float32)

    def classificar(self, recortes: list[np.ndarray]) -> list[tuple[str, float]]:
        """`[(caractere, confiança), ...]`, um por recorte, na mesma ordem."""
        probs = self.probabilidades(recortes)
        if probs.size == 0:
            return []
        indices = probs.argmax(axis=1)
        return [(self.meta.classes[int(i)], float(probs[linha, i])) for linha, i in enumerate(indices)]
