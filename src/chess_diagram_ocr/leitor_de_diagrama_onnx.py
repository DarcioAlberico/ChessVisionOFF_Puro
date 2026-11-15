"""Leitor de diagrama pelo `.onnx` do classificador de peças, sem torch e sem este pacote (S-30).

**Para que serve.** É o arquivo que outro programa copia. Com o `.onnx` e o `.json` que o
`cvoff-export-onnx` grava lado a lado, ele lê um tabuleiro já recortado e devolve a colocação da
FEN usando só `numpy`, `opencv-python` e `onnxruntime`. Não importa nada de `chess_diagram_ocr`
nem `torch` -- `tests/test_leitor_de_diagrama_onnx.py` trava isso --, e por isso pode morar num
editor de outro projeto sem trazer o resto. Para outra linguagem, o `.json` sozinho descreve o
preparo passo a passo, e este arquivo é a implementação de referência.

**O preparo aqui é uma cópia, e de propósito.** O original mora em `model.py`
(`preprocess_cell_to_tensor`, `with_coordinate_channels`) e em
`board_detection.split_board_into_cells`, que falam torch e o pacote -- justamente o que o outro
programa não tem. A cópia não pode derivar: o teste compara o lote montado aqui com o do pacote
**byte a byte** em todas as arquiteturas da grade, e o `cvoff-export-onnx` refaz a comparação nos
tabuleiros reais do split de teste antes de dar o arquivo por bom.

**O contrato é o `.json`.** Ele diz o que o `.onnx` sozinho não diz: os nomes das classes, o
preparo da imagem, a ordem das casas, a temperatura e de que treino o arquivo saiu. E se amarra ao
`.onnx` pelo SHA-256, como o dos glifos (`text/onnx_glifos.py`): um `.json` de outra exportação
traduziria índice em peça errada sem erro nenhum.

**O que fica de fora.** A detecção do tabuleiro na página e o reparo por regras
(`decode.decode_constrained`: rei que falta, rei a mais, promoção impossível) não são rede e não
vão no `.onnx`. Este leitor entrega a classe mais provável de cada casa. A orientação também é de
quem chama: diagrama impresso com as pretas embaixo se gira 180° antes de ler.

Uso avulso::

    python leitor_de_diagrama_onnx.py piece_classifier.onnx tabuleiro.png [outro.png ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

SCHEMA_DO_CONTRATO = 1
"""Versão do `.json`. Sobe quando um campo muda de sentido; um leitor recusa o que é mais novo."""

CANAIS = ("gray", "rgb")
LOTES = (1, 64)
"""1: o modelo lê cada casa sozinha. 64: lê o tabuleiro inteiro (cabeça `board`, S-62b)."""

CASAS = 64
PLANOS_DE_COORDENADA = 3
VAZIA = "empty"


class ContratoInvalido(ValueError):
    """O `.json` falta, não se lê, ou não descreve o `.onnx` que está ao lado dele."""


def caminho_do_contrato(onnx: Path) -> Path:
    """O `.json` mora ao lado do `.onnx`, com o mesmo nome-base."""
    return Path(onnx).with_suffix(".json")


def sha256_do_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for pedaco in iter(lambda: arquivo.read(1 << 20), b""):
            digest.update(pedaco)
    return digest.hexdigest()


@dataclass(frozen=True)
class Contrato:
    """O que o `.json` declara, já conferido. `como_dicionario` e `de_dicionario` são o formato."""

    onnx_sha256: str
    arquitetura: str
    classes: tuple[str, ...]
    canais: str
    lado_da_casa: int
    coordenadas: bool
    lote_multiplo_de: int
    temperatura: float
    lado_do_tabuleiro: int = 800
    nome_da_entrada: str = "cells"
    nome_da_saida: str = "logits"
    opset: int = 17
    temperatura_aplicada_pelo_programa: bool = False
    origem: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.canais not in CANAIS:
            raise ContratoInvalido(f"canais {self.canais!r} não existe; os conhecidos são {', '.join(CANAIS)}.")
        if self.lote_multiplo_de not in LOTES:
            raise ContratoInvalido(f"lote_multiplo_de deve ser 1 ou 64; veio {self.lote_multiplo_de}.")
        if self.lado_da_casa <= 0:
            raise ContratoInvalido(f"lado_da_casa deve ser positivo; veio {self.lado_da_casa}.")
        if self.lado_do_tabuleiro <= 0 or self.lado_do_tabuleiro % 8:
            raise ContratoInvalido(f"lado_do_tabuleiro deve ser múltiplo positivo de 8; veio {self.lado_do_tabuleiro}.")
        if not self.classes or not all(self.classes) or len(set(self.classes)) != len(self.classes):
            raise ContratoInvalido("classes deve ser uma lista de nomes não vazios e distintos.")
        if not self.temperatura > 0:
            raise ContratoInvalido(f"temperatura deve ser positiva; veio {self.temperatura}.")

    @property
    def canais_de_entrada(self) -> int:
        return (1 if self.canais == "gray" else 3) + (PLANOS_DE_COORDENADA if self.coordenadas else 0)

    def passos(self) -> list[str]:
        """O preparo em prosa, para quem reimplementa noutra linguagem. Derivado dos campos."""
        lado, casa = self.lado_do_tabuleiro, self.lado_do_tabuleiro // 8
        passos = [
            f"Recorte só as 64 casas do tabuleiro (sem moldura nem coordenadas impressas), em RGB uint8, "
            f"e redimensione para {lado}x{lado} com interpolação bilinear (cv2.resize, o padrão).",
            f"Corte em 8x8 casas de {casa}x{casa} px, por fila: o índice 0 é o canto superior esquerdo, "
            "o 7 o superior direito e o 63 o inferior direito. Com as brancas embaixo, 0 é a8 e 63 é h1.",
            "Converta cada casa para cinza com cv2.COLOR_RGB2GRAY (0,299 R + 0,587 G + 0,114 B)."
            if self.canais == "gray"
            else "Mantenha os três canais de cada casa na ordem R, G, B.",
            f"Redimensione cada casa para {self.lado_da_casa}x{self.lado_da_casa} por média de área "
            "(cv2.INTER_AREA) e divida por 255: float32 em [0, 1].",
        ]
        if self.coordenadas:
            passos.append(
                "Acrescente três planos constantes depois dos da imagem: (fila + coluna) % 2, fila / 7 e "
                "coluna / 7, com fila e coluna (0 a 7) contadas a partir do canto superior esquerdo."
            )
        passos.append(
            f"Empilhe as 64 casas nessa ordem: a entrada é ({CASAS}, {self.canais_de_entrada}, "
            f"{self.lado_da_casa}, {self.lado_da_casa}) float32, e a saída ({CASAS}, {len(self.classes)})."
        )
        if self.lote_multiplo_de == CASAS:
            passos.append("O modelo lê o tabuleiro inteiro: o lote é múltiplo de 64, um tabuleiro por bloco.")
        return passos

    def como_dicionario(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_DO_CONTRATO,
            "modelo": "classificador de peças do ChessVisionOFF: uma casa por linha do lote, logits por classe",
            "onnx_sha256": self.onnx_sha256,
            "opset": self.opset,
            "arquitetura": self.arquitetura,
            "entrada": {
                "nome": self.nome_da_entrada,
                "forma": ["lote", self.canais_de_entrada, self.lado_da_casa, self.lado_da_casa],
                "tipo": "float32",
                "faixa": [0.0, 1.0],
                "lote_multiplo_de": self.lote_multiplo_de,
            },
            "saida": {
                "nome": self.nome_da_saida,
                "forma": ["lote", len(self.classes)],
                "preparo": "argmax dá a classe da casa; softmax(logits / temperatura) dá a confiança calibrada",
            },
            "num_classes": len(self.classes),
            "classes": list(self.classes),
            "classe_vazia": VAZIA,
            "temperatura": self.temperatura,
            "temperatura_aplicada_pelo_programa": self.temperatura_aplicada_pelo_programa,
            "preparo": {
                "lado_do_tabuleiro": self.lado_do_tabuleiro,
                "canais": self.canais,
                "lado_da_casa": self.lado_da_casa,
                "coordenadas": self.coordenadas,
                "passos": self.passos(),
            },
            "origem": dict(self.origem),
        }

    @classmethod
    def de_dicionario(cls, bruto: object, nome: str = "contrato") -> Contrato:
        if not isinstance(bruto, dict):
            raise ContratoInvalido(f"{nome} não é um objeto JSON.")
        versao = bruto.get("schema_version")
        if not isinstance(versao, int) or isinstance(versao, bool):
            raise ContratoInvalido(f"{nome} não traz `schema_version`.")
        if versao > SCHEMA_DO_CONTRATO:
            raise ContratoInvalido(
                f"{nome} é da versão {versao} do contrato, e este leitor conhece até a {SCHEMA_DO_CONTRATO}."
            )
        entrada, saida, preparo = (_objeto(bruto, chave, nome) for chave in ("entrada", "saida", "preparo"))
        classes = bruto.get("classes")
        if not isinstance(classes, list) or not all(isinstance(classe, str) for classe in classes):
            raise ContratoInvalido(f"{nome} não traz a lista `classes`.")
        if bruto.get("num_classes") != len(classes):
            raise ContratoInvalido(f"{nome} declara {bruto.get('num_classes')} classes e lista {len(classes)}.")
        origem = bruto.get("origem", {})
        contrato = cls(
            onnx_sha256=_texto(bruto, "onnx_sha256", nome),
            arquitetura=_texto(bruto, "arquitetura", nome),
            classes=tuple(classes),
            canais=_texto(preparo, "canais", nome),
            lado_da_casa=_inteiro(preparo, "lado_da_casa", nome),
            coordenadas=_booleano(preparo, "coordenadas", nome),
            lote_multiplo_de=_inteiro(entrada, "lote_multiplo_de", nome),
            temperatura=_numero(bruto, "temperatura", nome),
            lado_do_tabuleiro=_inteiro(preparo, "lado_do_tabuleiro", nome),
            nome_da_entrada=_texto(entrada, "nome", nome),
            nome_da_saida=_texto(saida, "nome", nome),
            opset=_inteiro(bruto, "opset", nome),
            temperatura_aplicada_pelo_programa=_booleano(bruto, "temperatura_aplicada_pelo_programa", nome),
            origem=dict(origem) if isinstance(origem, dict) else {},
        )
        forma = ["lote", contrato.canais_de_entrada, contrato.lado_da_casa, contrato.lado_da_casa]
        if entrada.get("forma") != forma:
            raise ContratoInvalido(f"{nome}: `entrada.forma` é {entrada.get('forma')}, e o preparo dá {forma}.")
        return contrato


def _objeto(dados: dict[str, object], chave: str, nome: str) -> dict[str, object]:
    valor = dados.get(chave)
    if not isinstance(valor, dict):
        raise ContratoInvalido(f"{nome} não traz o objeto `{chave}`.")
    return valor


def _texto(dados: dict[str, object], chave: str, nome: str) -> str:
    valor = dados.get(chave)
    if not isinstance(valor, str) or not valor:
        raise ContratoInvalido(f"{nome} não traz o texto `{chave}`.")
    return valor


def _inteiro(dados: dict[str, object], chave: str, nome: str) -> int:
    valor = dados.get(chave)
    if not isinstance(valor, int) or isinstance(valor, bool):
        raise ContratoInvalido(f"{nome} não traz o inteiro `{chave}`.")
    return valor


def _numero(dados: dict[str, object], chave: str, nome: str) -> float:
    valor = dados.get(chave)
    if not isinstance(valor, int | float) or isinstance(valor, bool):
        raise ContratoInvalido(f"{nome} não traz o número `{chave}`.")
    return float(valor)


def _booleano(dados: dict[str, object], chave: str, nome: str) -> bool:
    valor = dados.get(chave)
    if not isinstance(valor, bool):
        raise ContratoInvalido(f"{nome} não traz o booleano `{chave}`.")
    return valor


def ler_contrato(onnx: Path, *, conferir_sha256: bool = True) -> Contrato:
    """Lê o `.json` ao lado do `.onnx` e confere que ele descreve **este** arquivo."""
    onnx = Path(onnx)
    caminho = caminho_do_contrato(onnx)
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContratoInvalido(
            f"O contrato de {onnx.name} não está em {caminho}. Sem ele não há como saber o preparo "
            "nem traduzir índice em peça: exporte de novo com `cvoff-export-onnx`."
        ) from exc
    except ValueError as exc:
        raise ContratoInvalido(f"{caminho.name} não é um JSON válido: {exc}") from exc

    contrato = Contrato.de_dicionario(bruto, caminho.name)
    if conferir_sha256:
        encontrado = sha256_do_arquivo(onnx)
        if encontrado != contrato.onnx_sha256:
            raise ContratoInvalido(
                f"{onnx.name} não é o modelo descrito por {caminho.name}.\n\n"
                f"  o contrato espera  {contrato.onnx_sha256}\n"
                f"  o arquivo tem      {encontrado}\n\n"
                "Os dois precisam sair da mesma exportação: índices de outro treino apontam para as "
                "peças erradas, sem erro e sem aviso."
            )
    return contrato


def recortar_casas(tabuleiro_rgb: np.ndarray, lado_do_tabuleiro: int = 800) -> list[np.ndarray]:
    """As 64 casas na ordem de leitura. O espelho de `board_detection.split_board_into_cells`."""
    if tabuleiro_rgb.shape[0] != lado_do_tabuleiro or tabuleiro_rgb.shape[1] != lado_do_tabuleiro:
        tabuleiro_rgb = cv2.resize(tabuleiro_rgb, (lado_do_tabuleiro, lado_do_tabuleiro))
    passo = lado_do_tabuleiro // 8
    return [
        tabuleiro_rgb[fila * passo : (fila + 1) * passo, coluna * passo : (coluna + 1) * passo]
        for fila in range(8)
        for coluna in range(8)
    ]


def preparar_casa(casa_rgb: np.ndarray, contrato: Contrato) -> np.ndarray:
    """Recorte de casa (RGB uint8) -> (canais, lado, lado) float32. O espelho de `preprocess_cell_to_tensor`."""
    imagem = cv2.cvtColor(casa_rgb, cv2.COLOR_RGB2GRAY) if contrato.canais == "gray" else casa_rgb
    lado = contrato.lado_da_casa
    reduzida = cv2.resize(imagem, (lado, lado), interpolation=cv2.INTER_AREA)
    normalizada = reduzida.astype(np.float32) / 255.0
    if contrato.canais == "gray":
        return normalizada[np.newaxis]
    return np.ascontiguousarray(normalizada.transpose(2, 0, 1))


def planos_de_coordenada(indice: int, lado: int) -> np.ndarray:
    """Os três planos constantes da casa `indice` (S-62a). O espelho de `model.coordinate_channels`."""
    fila, coluna = divmod(indice, 8)
    valores = ((fila + coluna) % 2, fila / 7.0, coluna / 7.0)
    return np.stack([np.full((lado, lado), valor, dtype=np.float32) for valor in valores])


def preparar_tabuleiro(tabuleiro_rgb: np.ndarray, contrato: Contrato) -> np.ndarray:
    """Tabuleiro recortado (RGB uint8, qualquer tamanho) -> a entrada do modelo, (64, C, S, S) float32."""
    if tabuleiro_rgb.ndim != 3 or tabuleiro_rgb.shape[2] != 3 or tabuleiro_rgb.dtype != np.uint8:
        raise ValueError(f"esperava imagem RGB uint8 (altura, largura, 3); veio {tabuleiro_rgb.dtype} {tabuleiro_rgb.shape}.")
    casas = []
    for indice, casa in enumerate(recortar_casas(tabuleiro_rgb, contrato.lado_do_tabuleiro)):
        preparada = preparar_casa(casa, contrato)
        if contrato.coordenadas:
            preparada = np.concatenate((preparada, planos_de_coordenada(indice, contrato.lado_da_casa)))
        casas.append(preparada)
    return np.stack(casas)


def posicao_fen(casas: Sequence[str]) -> str:
    """64 nomes de classe na ordem de leitura -> o campo de colocação da FEN."""
    if len(casas) != CASAS:
        raise ValueError(f"esperava {CASAS} casas; vieram {len(casas)}.")
    filas = []
    for inicio in range(0, CASAS, 8):
        texto, vazias = "", 0
        for nome in casas[inicio : inicio + 8]:
            if nome == VAZIA:
                vazias += 1
                continue
            texto += (str(vazias) if vazias else "") + nome
            vazias = 0
        filas.append(texto + (str(vazias) if vazias else ""))
    return "/".join(filas)


def softmax(logits: np.ndarray, temperatura: float = 1.0) -> np.ndarray:
    escalados = logits.astype(np.float64) / temperatura
    escalados -= escalados.max(axis=1, keepdims=True)
    exponenciais = np.exp(escalados)
    return exponenciais / exponenciais.sum(axis=1, keepdims=True)


@dataclass(frozen=True)
class Leitura:
    """Um tabuleiro lido: a classe e as probabilidades de cada casa, na ordem de leitura."""

    casas: tuple[str, ...]
    probabilidades: np.ndarray

    @property
    def fen(self) -> str:
        return posicao_fen(self.casas)

    @property
    def confianca_minima(self) -> float:
        """A menor das 64 confianças: onde vale olhar primeiro."""
        return float(self.probabilidades.max(axis=1).min())


class LeitorDeDiagramaOnnx:
    """Abre o `.onnx` com o contrato ao lado e lê tabuleiros já recortados."""

    def __init__(self, onnx: Path, *, conferir_sha256: bool = True, providers: Sequence[str] | None = None) -> None:
        import onnxruntime  # aqui e não no topo: quem só quer ler o contrato não precisa dele

        self.caminho = Path(onnx)
        self.contrato = ler_contrato(self.caminho, conferir_sha256=conferir_sha256)
        opcoes = onnxruntime.SessionOptions()
        opcoes.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._sessao = onnxruntime.InferenceSession(
            str(self.caminho), opcoes, providers=list(providers or ["CPUExecutionProvider"])
        )
        entrada = self._sessao.get_inputs()[0]
        esperada = [self.contrato.canais_de_entrada, self.contrato.lado_da_casa, self.contrato.lado_da_casa]
        if entrada.name != self.contrato.nome_da_entrada or list(entrada.shape[1:]) != esperada:
            raise ContratoInvalido(
                f"{self.caminho.name} espera `{entrada.name}` {list(entrada.shape)}, e o contrato descreve "
                f"`{self.contrato.nome_da_entrada}` com {esperada} por casa."
            )

    def logits(self, tabuleiro_rgb: np.ndarray) -> np.ndarray:
        lote = preparar_tabuleiro(tabuleiro_rgb, self.contrato)
        return np.asarray(self._sessao.run(None, {self.contrato.nome_da_entrada: lote})[0])

    def probabilidades(self, tabuleiro_rgb: np.ndarray, *, calibrada: bool = False) -> np.ndarray:
        """(64, classes). `calibrada` divide pela temperatura; o programa, por padrão, não divide (S-28)."""
        return softmax(self.logits(tabuleiro_rgb), self.contrato.temperatura if calibrada else 1.0)

    def ler(self, tabuleiro_rgb: np.ndarray, *, calibrada: bool = False) -> Leitura:
        probabilidades = self.probabilidades(tabuleiro_rgb, calibrada=calibrada)
        casas = tuple(self.contrato.classes[indice] for indice in probabilidades.argmax(axis=1))
        return Leitura(casas=casas, probabilidades=probabilidades)


def ler_imagem_rgb(caminho: Path) -> np.ndarray:
    """Lê a imagem como RGB uint8. `np.fromfile` e não `cv2.imread`: este aceita caminho com acento."""
    try:
        dados = np.fromfile(str(caminho), dtype=np.uint8)
    except OSError as exc:
        raise ValueError(f"não consegui abrir a imagem {caminho}: {exc.strerror or exc}.") from exc
    imagem = cv2.imdecode(dados, cv2.IMREAD_COLOR) if dados.size else None
    if imagem is None:
        raise ValueError(f"não consegui ler a imagem {caminho}.")
    return cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lê tabuleiros recortados e escreve a colocação da FEN de cada um.")
    parser.add_argument("onnx", type=Path, help="O .onnx do cvoff-export-onnx, com o .json ao lado.")
    parser.add_argument("imagens", type=Path, nargs="+", help="Imagens de tabuleiro já recortado.")
    parser.add_argument("--girar-180", action="store_true", help="Lê como se o diagrama estivesse com as pretas embaixo.")
    args = parser.parse_args(argv)

    try:
        leitor = LeitorDeDiagramaOnnx(args.onnx)
    except (ContratoInvalido, OSError) as exc:
        print(exc, file=sys.stderr)
        return 2

    falhas = 0
    for caminho in args.imagens:
        try:
            imagem = ler_imagem_rgb(caminho)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            falhas += 1
            continue
        if args.girar_180:
            imagem = cv2.rotate(imagem, cv2.ROTATE_180)
        leitura = leitor.ler(imagem)
        print(f"{leitura.fen}\t{leitura.confianca_minima:.3f}\t{caminho}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
