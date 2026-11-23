"""O modelo de marcas: diz qual marca uma casa tem, e não qual peça.

**O que ele é.** A metade da leitura que o modelo de peças não faz (decisão de 2026-11-04: dois datasets e
dois modelos). O de peças lê a casa com estrela como vazia; este diz que ali há uma estrela, para as
conversões (EPUB, DOCX, HTML, PGN) poderem desenhá-la. Um não corrige o outro: discordância vira
conferência, e a saída de um nunca vira rótulo do outro.

**Só marca de casa, e só na casa vazia.** As classes são as de `marcas_de_casa.TIPOS_DE_CASA` sem `outra`,
mais "sem marca". Seta, reta e moldura atravessam casas e são outro problema (um detector geométrico): aqui
elas aparecem só como distração, desenhadas na casa vazia com o rótulo "sem marca", para o modelo aprender
que um pedaço de seta não é um X. A casa com peça é sempre "sem marca": as 181 marcas anotadas até
2026-11-22 estão todas em casa vazia, e marca sobre peça é um rótulo que ninguém fez.

**Treina só com marca sintética.** As marcas reais são poucas (cerca de 0,15% dos diagramas) e são o teste
(`teste_de_marcas.py`): nenhuma amostra do teste entra no treino, nem pelas casas sem marca. A marca é a de
`augment.MarcaEmVazia.desenhar`, a mesma que ensinou o modelo de peças a ler a marca como vazia, desenhada
sobre a casa vazia **real** do acervo, antes do aumento genérico: a hachura, o papel e o desfoque da página
ficam por baixo e por cima dela como num livro.

**A ponte de tipos.** O aumento fala `estrela`, `ponto` e `oca`; a anotação fala `estrela-preta`,
`bolinha-preta` e `bolinha-branca`. `DO_AUMENTO` é a tradução, num lugar só.

**A arquitetura é a do modelo de peças** (`model.PieceClassifier`, cinza 64 px, cabeça linear), com 7
saídas: o mesmo recorte de casa e o mesmo pré-processamento, sem uma segunda forma de cortar o tabuleiro.

**O checkpoint diz o que é.** `metadata["modelo"] == "marcas"` e a lista de classes vão gravados, e
`carregar` recusa qualquer `.pt` sem isso: o modelo de peças tem a mesma arquitetura, e trocá-los por engano
daria peças lidas como marca sem erro nenhum.

**Medido em 2026-11-22** (3 épocas, limiar 0,5; `cvoff-marcas medir`): no teste congelado, 180 das 181 marcas,
contra 179 do detector clássico; a que falta é o pingo cinza e borrado de uma revista de 1929. Nas 4.127
amostras de validação e teste que ninguém anotou, nenhum alarme falso (o detector dá 2: uma peça em ampulheta
lida como X e um cavalo lido como estrela branca), e os dois acham um diagrama de três estrelas que ninguém
tinha anotado. O modelo acha também um X riscando uma peça, que o rótulo não cobre. Cada distração saiu de um
erro visto nas casas apontadas, em seis treinos: ver `QUEBRAS_DE_TRACO`, `SUJEIRAS`, `BOLINHA_MINIMA` e
`SorteioDeMarca`.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, Dataset

from . import marcas_de_casa as mc
from .atomic_io import atomic_write_bytes
from .augment import AugmentConfig, MarcaEmVazia, desenhar_marca, from_letters
from .checkpoint import load_checkpoint, save_checkpoint
from .config import BOARD_SIZE
from .dataset import EMPTY_LABEL, BoardFenDataset, BoardGroupedSampler, board_groups
from .fen_utils import square_name
from .model import DEFAULT_ARCH, ArchConfig, PieceClassifier, preprocess_cell_to_tensor
from .splits import Split
from .training import build_train_transform

logger = logging.getLogger(__name__)

__all__ = [
    "CLASSES_DE_MARCA",
    "DO_AUMENTO",
    "LIMIAR_PADRAO",
    "QUEBRAS_DE_TRACO",
    "SUJEIRAS",
    "TRACOS_DE_DISTRACAO",
    "CasasComMarca",
    "ModeloDeMarcas",
    "Progresso",
    "ResultadoDoTreino",
    "SorteioDeMarca",
    "carregar",
    "instalar",
    "leitor_de_marcas",
    "desenhar_letra",
    "desenhar_quebra",
    "treinar",
]

SEM_MARCA = 0
CLASSES_DE_MARCA: tuple[str, ...] = ("sem-marca", *(tipo for tipo in mc.TIPOS_DE_CASA if tipo != mc.OUTRA))
"""A saída do modelo, na ordem: o índice 0 é "sem marca", o resto são as marcas de casa da anotação."""

DO_AUMENTO: dict[str, str] = {
    "estrela": mc.ESTRELA_PRETA,
    "estrela-branca": mc.ESTRELA_BRANCA,
    "x": mc.X,
    "cruz": mc.CRUZ,
    "ponto": mc.BOLINHA_PRETA,
    "oca": mc.BOLINHA_BRANCA,
}
"""O tipo de `augment.TIPOS_DE_MARCA` que desenha cada marca de casa da anotação."""

TRACOS_DE_DISTRACAO: tuple[str, ...] = ("reta", "seta", "moldura")
"""Os traços do aumento que entram com rótulo "sem marca": pedaço de seta não é marca de casa."""

QUEBRAS_DE_TRACO: tuple[str, ...] = ("vertice", "pontilhada", "ponta")
"""Os traços que o aumento não desenha, e que os primeiros modelos leram como marca (2026-11-22, teste congelado):
o vértice do zigue-zague do *Finais*, duas meias-retas que se encontram na casa, lido como X; a reta
pontilhada de quadradinhos do *Manual de Finales*, lida como bolinha preta; e a ponta da reta que termina
dentro da casa, contínua ou tracejada, lida como bolinha preta depois que a marca passou a vir atravessada
por traço -- a reta do aumento sempre atravessa a casa inteira, e a de um livro começa e acaba no meio
dela. Moram aqui, e não em `augment.TIPOS_DE_MARCA`, porque um tipo novo lá mudaria o sorteio do treino do
modelo de peças."""

SUJEIRAS: tuple[str, ...] = ("sujeira", "letra")
"""O que não é traço nem marca e o modelo v5 leu como marca (2026-11-22, alarmes em amostras sem anotação):
pingos de sujeira na hachura, lidos como bolinha preta, e as letras C e D impressas dentro da casa, lidas como
bolinha branca. Entram como distração com rótulo "sem marca"."""

PINGO_MAXIMO = 0.07
"""O maior pingo de `sujeira`, em fração do lado da casa."""

BOLINHA_MINIMA = 0.14
"""A menor bolinha preta que o treino desenha. O aumento herdado desenha "ponto" desde 8% da casa, que é o
tamanho de um pingo de sujeira: as reais do teste congelado vão de 29% a 38%, e o detector clássico não
aceita forma abaixo de 14% (`detector_de_marcas.LADO_MINIMO`). O vão entre 7% e 14% separa os dois rótulos."""

LETRAS_DA_CASA = "abcdefghABCDEFGHKRNB12345678=!?#"
"""As letras que a distração `letra` imprime. Ficam de fora as que **são** marca ou se confundem com uma:
O, o, 0 e Q (bolinha branca), x, X, + e * (X e cruz)."""

_FONTES = (
    cv2.FONT_HERSHEY_SIMPLEX,
    cv2.FONT_HERSHEY_DUPLEX,
    cv2.FONT_HERSHEY_COMPLEX,
    cv2.FONT_HERSHEY_TRIPLEX,
    cv2.FONT_HERSHEY_PLAIN,
)

_SUPERAMOSTRA = 4
"""A mesma suavização de borda de `augment._cobertura_de_marca`: grade 4x mais fina, reduzida por média."""

LIMIAR_PADRAO = 0.5
"""A probabilidade mínima da marca para ela ser dada. O que sobra abaixo dele é "sem marca"."""

REGIME_PADRAO = "hspe"
"""O aumento genérico por cima da marca: hachura, granulação, papel e espessura do traço. Sem a inversão
(`i`), que troca a estrela preta pela branca e mentiria o rótulo; sem o espelhamento (`m`), que nada
acrescenta a marcas simétricas e confunde o lado da ponta da seta."""

MODELO = "marcas"
VERSAO_DO_MODELO = 1


def _classe(tipo: str) -> int:
    return CLASSES_DE_MARCA.index(tipo)


def _cobertura_de_quebra(
    tamanho: int,
    tipo: str,
    *,
    vertice: tuple[float, float],
    angulos: tuple[float, float],
    espessura: float,
    periodo: float = 0.0,
) -> torch.Tensor:
    """A fração de cada pixel coberta pelo traço `tipo` de `QUEBRAS_DE_TRACO`, em [0, 1].

    Medidas em fração do lado da casa, com `(0, 0)` no centro. `vertice` é o ponto de encontro das duas
    meias-retas (ou um ponto da pontilhada, ou a ponta da meia-reta), `angulos` as direções delas em
    radianos, e `periodo` o passo entre os pontos da pontilhada, que são quadradinhos do lado da espessura,
    ou o do tracejado da ponta (0 = contínua).
    """
    n = tamanho * _SUPERAMOSTRA
    eixo = (torch.arange(n, dtype=torch.float32) + 0.5) / n - 0.5
    v, u = torch.meshgrid(eixo, eixo, indexing="ij")
    du, dv = u - vertice[0], v - vertice[1]
    meia = espessura / 2
    if tipo == "vertice":
        dentro = torch.zeros_like(u, dtype=torch.bool)
        for angulo in angulos:
            cos, sen = float(np.cos(angulo)), float(np.sin(angulo))
            ao_longo = du * cos + dv * sen
            de_lado = -du * sen + dv * cos
            dentro |= (ao_longo >= -meia) & (de_lado.abs() <= meia)
    elif tipo == "pontilhada":
        cos, sen = float(np.cos(angulos[0])), float(np.sin(angulos[0]))
        ao_longo = du * cos + dv * sen
        de_lado = -du * sen + dv * cos
        dentro = (de_lado.abs() <= meia) & (torch.remainder(ao_longo, periodo) < espessura)
    elif tipo == "ponta":
        cos, sen = float(np.cos(angulos[0])), float(np.sin(angulos[0]))
        ao_longo = du * cos + dv * sen
        de_lado = -du * sen + dv * cos
        dentro = (ao_longo >= 0) & (de_lado.abs() <= meia)
        if periodo > 0:
            dentro = dentro & (torch.remainder(ao_longo, periodo) < periodo * 0.6)
    else:
        raise ValueError(f"Traço desconhecido: {tipo!r} (válidos: {', '.join(QUEBRAS_DE_TRACO)})")
    cobertura = dentro.to(torch.float32).unsqueeze(0).unsqueeze(0)
    return F.avg_pool2d(cobertura, _SUPERAMOSTRA).squeeze(0).squeeze(0)


def desenhar_quebra(
    x: torch.Tensor,
    tipo: str,
    *,
    vertice: tuple[float, float],
    angulos: tuple[float, float],
    espessura: float,
    periodo: float = 0.0,
    tinta: float = 0.05,
) -> torch.Tensor:
    """O traço `tipo` de `QUEBRAS_DE_TRACO` impresso na casa, como `augment.desenhar_marca` imprime os dele."""
    alfa = _cobertura_de_quebra(
        x.shape[-1], tipo, vertice=vertice, angulos=angulos, espessura=espessura, periodo=periodo
    ).to(dtype=x.dtype, device=x.device)
    return x * (1.0 - alfa) + tinta * alfa


def _faixa(baixo: float, alto: float) -> float:
    return float(baixo + (alto - baixo) * torch.rand(()))


def _quebra_sorteada(x: torch.Tensor, tipo: str) -> torch.Tensor:
    """O traço de `QUEBRAS_DE_TRACO` com medidas sorteadas: metade nas oito direções do tabuleiro."""
    if torch.rand(()) < 0.5:
        primeiro = float(torch.randint(8, ()).item()) * np.pi / 4
    else:
        primeiro = _faixa(0.0, 2 * np.pi)
    if tipo == "vertice":
        abertura = _faixa(0.25 * np.pi, 0.85 * np.pi) * (1 if torch.rand(()) < 0.5 else -1)
        return desenhar_quebra(
            x,
            tipo,
            vertice=(_faixa(-0.3, 0.3), _faixa(-0.3, 0.3)),
            angulos=(primeiro, primeiro + abertura),
            espessura=_faixa(0.03, 0.10),
            tinta=_faixa(0.0, 0.35),
        )
    if tipo == "ponta":
        return desenhar_quebra(
            x,
            tipo,
            vertice=(_faixa(-0.4, 0.4), _faixa(-0.4, 0.4)),
            angulos=(primeiro, primeiro),
            espessura=_faixa(0.02, 0.10),
            periodo=_faixa(0.15, 0.40) if torch.rand(()) < 0.4 else 0.0,
            tinta=_faixa(0.0, 0.35),
        )
    espessura = _faixa(0.05, 0.12)
    return desenhar_quebra(
        x,
        tipo,
        vertice=(_faixa(-0.35, 0.35), _faixa(-0.35, 0.35)),
        angulos=(primeiro, primeiro),
        espessura=espessura,
        periodo=espessura * _faixa(1.6, 3.0),
        tinta=_faixa(0.0, 0.25),
    )


def _sujeira_sorteada(x: torch.Tensor) -> torch.Tensor:
    """De um a três pingos de até `PINGO_MAXIMO`, em qualquer lugar da casa: a sujeira da impressão."""
    for _ in range(int(torch.randint(1, 4, ()).item())):
        x = desenhar_marca(
            x,
            "ponto",
            largura=_faixa(0.02, PINGO_MAXIMO),
            centro=(_faixa(-0.4, 0.4), _faixa(-0.4, 0.4)),
            tinta=_faixa(0.0, 0.45),
        )
    return x


def desenhar_letra(
    x: torch.Tensor, letra: str, *, altura: float, centro: tuple[float, float], fonte: int, tinta: float
) -> torch.Tensor:
    """A `letra` impressa na casa, com `altura` em fração do lado e o centro deslocado de `centro`."""
    lado = x.shape[-1] * _SUPERAMOSTRA
    escala = 1.0
    (largura_px, altura_px), _ = cv2.getTextSize(letra, fonte, escala, 1)
    escala = altura * lado / max(altura_px, 1)
    espessura = max(1, round(escala * 1.6))
    (largura_px, altura_px), _ = cv2.getTextSize(letra, fonte, escala, espessura)
    tela = np.zeros((lado, lado), dtype=np.uint8)
    origem = (
        round(lado / 2 + centro[0] * lado - largura_px / 2),
        round(lado / 2 + centro[1] * lado + altura_px / 2),
    )
    cv2.putText(tela, letra, origem, fonte, escala, 255, espessura, cv2.LINE_AA)
    cobertura = torch.from_numpy(tela.astype(np.float32) / 255.0).unsqueeze(0).unsqueeze(0)
    alfa = F.avg_pool2d(cobertura, _SUPERAMOSTRA).squeeze(0).squeeze(0).to(dtype=x.dtype, device=x.device)
    return x * (1.0 - alfa) + tinta * alfa


def _letra_sorteada(x: torch.Tensor) -> torch.Tensor:
    letra = LETRAS_DA_CASA[int(torch.randint(len(LETRAS_DA_CASA), ()).item())]
    return desenhar_letra(
        x,
        letra,
        altura=_faixa(0.25, 0.6),
        centro=(_faixa(-0.2, 0.2), _faixa(-0.2, 0.2)),
        fonte=_FONTES[int(torch.randint(len(_FONTES), ()).item())],
        tinta=_faixa(0.0, 0.35),
    )


def _bolinha_preta_sorteada(x: torch.Tensor) -> torch.Tensor:
    """A bolinha preta de `BOLINHA_MINIMA` a 50% da casa, centrada como as do aumento."""
    return desenhar_marca(
        x,
        "ponto",
        largura=_faixa(BOLINHA_MINIMA, 0.50),
        centro=(_faixa(-0.05, 0.05), _faixa(-0.05, 0.05)),
        tinta=_faixa(0.0, 0.15),
        papel=_faixa(0.85, 1.0),
    )


class SorteioDeMarca:
    """Sorteia o que vai na casa vazia: uma marca de casa, um traço de distração ou nada.

    Devolve a casa e a classe. Usa o RNG do torch, como o aumento, para o `DataLoader` semear os workers.

    **A marca atravessada por traço** (`p_traco_na_marca`) vem desligada por padrão, e a razão foi medida.
    Sem ela o modelo aprende que "tem linha, então não é marca", e perde a bolinha que o *Finais* põe no
    meio de uma reta tracejada (1 das 24 bolinhas brancas do teste). Com ela, em 0,3, a bolinha voltou, mas
    a ponta de reta e o pontilhado passaram a ser lidos como bolinha preta: 3 a 6 marcas inventadas no
    teste e 3 alarmes falsos em 3.000 amostras, em dois treinos (2026-11-22). Trocar uma marca perdida por
    várias inventadas é pior para quem confere. O traço vem antes da marca, como na página: o miolo da
    bolinha oca cobre a linha.
    """

    def __init__(self, p_marca: float = 0.5, p_traco: float = 0.3, p_traco_na_marca: float = 0.0) -> None:
        if p_marca < 0 or p_traco < 0 or p_marca + p_traco > 1 or not 0 <= p_traco_na_marca <= 1:
            raise ValueError(
                f"Probabilidades inválidas: marca {p_marca}, traço {p_traco}, traço na marca {p_traco_na_marca}"
            )
        self.p_marca = p_marca
        self.p_traco = p_traco
        self.p_traco_na_marca = p_traco_na_marca
        self._desenho = MarcaEmVazia(1.0)
        self._tipos = tuple(DO_AUMENTO)

    def _traco(self, x: torch.Tensor, *, com_sujeira: bool = True) -> torch.Tensor:
        tracos = (*TRACOS_DE_DISTRACAO, *QUEBRAS_DE_TRACO, *(SUJEIRAS if com_sujeira else ()))
        tipo = tracos[int(torch.randint(len(tracos), ()).item())]
        if tipo == "sujeira":
            return _sujeira_sorteada(x)
        if tipo == "letra":
            return _letra_sorteada(x)
        if tipo in QUEBRAS_DE_TRACO:
            return _quebra_sorteada(x, tipo)
        return self._desenho.desenhar(x, tipo)

    def __call__(self, x: torch.Tensor) -> tuple[torch.Tensor, int]:
        sorte = float(torch.rand(()))
        if sorte < self.p_marca:
            tipo = self._tipos[int(torch.randint(len(self._tipos), ()).item())]
            if float(torch.rand(())) < self.p_traco_na_marca:
                x = self._traco(x, com_sujeira=False)
            if tipo == "ponto":
                return _bolinha_preta_sorteada(x), _classe(DO_AUMENTO[tipo])
            return self._desenho.desenhar(x, tipo), _classe(DO_AUMENTO[tipo])
        if sorte < self.p_marca + self.p_traco:
            return self._traco(x), SEM_MARCA
        return x, SEM_MARCA


class CasasComMarca(Dataset):
    """As casas de `BoardFenDataset`, com a marca sorteada nas vazias e a classe da marca de rótulo.

    `fixo=True` é a validação: cada casa recebe sempre o mesmo sorteio (semente pelo índice), para duas
    épocas serem medidas na mesma régua.
    """

    def __init__(
        self,
        base: BoardFenDataset,
        sorteio: SorteioDeMarca,
        transform: Callable[[torch.Tensor], torch.Tensor] | None = None,
        *,
        fixo: bool = False,
        semente: int = 0,
    ) -> None:
        self.base = base
        self.sorteio = sorteio
        self.transform = transform
        self.fixo = fixo
        self.semente = semente
        self.canais = base.arch.image_channels

    def __len__(self) -> int:
        return len(self.base.index_map)

    def _item(self, idx: int) -> tuple[torch.Tensor, int]:
        entrada, casa = self.base.index_map[idx]
        x, peca = self.base.square(entrada, casa, None)
        x = x[: self.canais]
        classe = SEM_MARCA
        if peca == EMPTY_LABEL:
            x, classe = self.sorteio(x)
        if self.transform is not None:
            x = self.transform(x)
        return x, classe

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        if not self.fixo:
            return self._item(idx)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(self.semente * 1_000_003 + idx)
            return self._item(idx)


def sem_as_amostras(base: BoardFenDataset, excluidas: Iterable[str]) -> int:
    """Tira de `base` as casas dos tabuleiros `excluidas`, e devolve quantos tabuleiros saíram."""
    fora = set(excluidas)
    tirados = {i for i, entrada in enumerate(base.entries) if entrada.filename in fora}
    if tirados:
        base.index_map = [(entrada, casa) for entrada, casa in base.index_map if entrada not in tirados]
    return len(tirados)


def _limitar(base: BoardFenDataset, tabuleiros: int | None, semente: int) -> None:
    """Fica com `tabuleiros` tabuleiros sorteados, para um treino curto de conferência."""
    if not tabuleiros:
        return
    presentes = sorted({entrada for entrada, _ in base.index_map})
    if tabuleiros >= len(presentes):
        return
    escolhidos = set(random.Random(semente).sample(presentes, tabuleiros))
    base.index_map = [(entrada, casa) for entrada, casa in base.index_map if entrada in escolhidos]


@dataclass
class ResultadoDoTreino:
    melhor_epoca: int
    melhor_f1: float
    historico: list[dict[str, float]] = field(default_factory=list)
    tabuleiros_treino: int = 0
    tabuleiros_val: int = 0
    excluidos: int = 0
    cancelado: bool = False
    """Parou a pedido. O que está em `saida` é a melhor época **terminada**, ou nada se nenhuma terminou."""


Progresso = Callable[[int, int, float, "float | None"], None]
"""`(época, épocas, fração da época feita, F1 das marcas na validação)`. O F1 só vem com a época
terminada; no meio dela, `None`. A fração 1,0 sem F1 quer dizer "os lotes acabaram e a validação
começou". É o que a janela do modelo de marcas mostra na barra."""


def _f1_das_marcas(confusao: np.ndarray) -> float:
    """O F1 médio das classes de marca (sem a "sem marca"), sobre a matriz `confusao[verdade, lido]`."""
    f1s = []
    for classe in range(1, confusao.shape[0]):
        acerto = confusao[classe, classe]
        lidos = confusao[:, classe].sum()
        verdade = confusao[classe, :].sum()
        if verdade == 0:
            continue
        precisao = acerto / lidos if lidos else 0.0
        revocacao = acerto / verdade
        f1s.append(0.0 if precisao + revocacao == 0 else 2 * precisao * revocacao / (precisao + revocacao))
    return float(np.mean(f1s)) if f1s else 0.0


def _avaliar(modelo: nn.Module, carregador: DataLoader, device: str) -> tuple[float, np.ndarray]:
    modelo.eval()
    n = len(CLASSES_DE_MARCA)
    confusao = np.zeros((n, n), dtype=np.int64)
    perda = 0.0
    total = 0
    with torch.no_grad():
        for x, y in carregador:
            x, y = x.to(device), y.to(device)
            logits = modelo(x)
            perda += float(F.cross_entropy(logits, y, reduction="sum"))
            total += int(y.numel())
            lido = logits.argmax(1)
            np.add.at(confusao, (y.cpu().numpy(), lido.cpu().numpy()), 1)
    return perda / max(total, 1), confusao


def treinar(
    *,
    csv_path: Path,
    samples_dir: Path,
    splits: Mapping[str, Split],
    saida: Path,
    excluidas: Iterable[str] = (),
    epocas: int = 5,
    lote: int = 256,
    lr: float = 1e-3,
    semente: int = 42,
    workers: int = 4,
    device: str | None = None,
    regime: str = REGIME_PADRAO,
    p_marca: float = 0.5,
    p_traco: float = 0.3,
    p_traco_na_marca: float = 0.0,
    tabuleiros_treino: int | None = None,
    tabuleiros_val: int | None = 1500,
    arch: ArchConfig = DEFAULT_ARCH,
    progresso: Progresso | None = None,
    cancelar: threading.Event | None = None,
) -> ResultadoDoTreino:
    """Treina do zero e grava em `saida` a época de melhor F1 das marcas na validação sintética.

    `excluidas` são as amostras do teste congelado: saem do treino e da validação inteiras, com as casas
    sem marca. `tabuleiros_val` limita a validação, que é sintética e não precisa do split todo.

    `progresso` recebe a fração da época a cada ~1% dos lotes e o F1 ao fim de cada época; `cancelar`
    é conferido a cada lote, e o cancelado para sem validar a época pela metade (`cancelado`).
    """
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(semente)
    random.seed(semente)
    np.random.seed(semente)

    excluidas = list(excluidas)
    treino = BoardFenDataset(csv_path, samples_dir, split="train", splits=splits, arch=arch)
    val = BoardFenDataset(csv_path, samples_dir, split="val", splits=splits, arch=arch)
    fora = sem_as_amostras(treino, excluidas) + sem_as_amostras(val, excluidas)
    _limitar(treino, tabuleiros_treino, semente)
    _limitar(val, tabuleiros_val, semente + 1)

    aumento: AugmentConfig = from_letters(regime)
    sorteio = SorteioDeMarca(p_marca, p_traco, p_traco_na_marca)
    conjunto_treino = CasasComMarca(treino, sorteio, build_train_transform(aumento))
    conjunto_val = CasasComMarca(val, sorteio, None, fixo=True, semente=semente)

    grupos = board_groups(treino.index_map)
    amostrador = BoardGroupedSampler(grupos, shuffle=True, seed=semente)
    persistentes = workers > 0
    carregador_treino = DataLoader(
        conjunto_treino, batch_size=lote, sampler=amostrador, num_workers=workers, persistent_workers=persistentes
    )
    carregador_val = DataLoader(
        conjunto_val, batch_size=lote, shuffle=False, num_workers=workers, persistent_workers=persistentes
    )

    modelo = PieceClassifier(arch, num_classes=len(CLASSES_DE_MARCA)).to(device)
    otimizador = torch.optim.Adam(modelo.parameters(), lr=lr)
    agendador = torch.optim.lr_scheduler.CosineAnnealingLR(otimizador, T_max=max(1, epocas))

    resultado = ResultadoDoTreino(
        melhor_epoca=0,
        melhor_f1=-1.0,
        tabuleiros_treino=len({e for e, _ in treino.index_map}),
        tabuleiros_val=len({e for e, _ in val.index_map}),
        excluidos=fora,
    )
    logger.info(
        "Treino de marcas: %d tabuleiros de treino, %d de validação, %d do teste tirados, em %s.",
        resultado.tabuleiros_treino,
        resultado.tabuleiros_val,
        fora,
        device,
    )
    lotes = max(1, len(carregador_treino))
    passo = max(1, lotes // 100)
    for epoca in range(1, epocas + 1):
        inicio = time.monotonic()
        modelo.train()
        soma = 0.0
        vistos = 0
        for lote_feito, (x, y) in enumerate(carregador_treino, start=1):
            if cancelar is not None and cancelar.is_set():
                resultado.cancelado = True
                return resultado
            x, y = x.to(device), y.to(device)
            otimizador.zero_grad(set_to_none=True)
            perda = F.cross_entropy(modelo(x), y)
            perda.backward()
            otimizador.step()
            soma += float(perda.detach()) * int(y.numel())
            vistos += int(y.numel())
            if progresso is not None and lote_feito % passo == 0 and lote_feito < lotes:
                progresso(epoca, epocas, lote_feito / lotes, None)
        if progresso is not None:
            # Os lotes acabaram e a validação começa: em CPU ela leva minutos, e quem olha a barra
            # cheia precisa saber que a época ainda não terminou.
            progresso(epoca, epocas, 1.0, None)
        agendador.step()
        perda_val, confusao = _avaliar(modelo, carregador_val, device)
        f1 = _f1_das_marcas(confusao)
        linha = {
            "epoca": epoca,
            "perda_treino": soma / max(vistos, 1),
            "perda_val": perda_val,
            "f1_marcas_val": f1,
            "segundos": time.monotonic() - inicio,
        }
        resultado.historico.append(linha)
        if progresso is not None:
            progresso(epoca, epocas, 1.0, f1)
        logger.info(
            "época %d: perda %.4f, val %.4f, F1 das marcas %.4f (%.0f s)",
            epoca,
            linha["perda_treino"],
            perda_val,
            f1,
            linha["segundos"],
        )
        if f1 > resultado.melhor_f1:
            resultado.melhor_f1 = f1
            resultado.melhor_epoca = epoca
            save_checkpoint(
                saida,
                {chave: valor.detach().cpu() for chave, valor in modelo.state_dict().items()},
                metadata={
                    "modelo": MODELO,
                    "versao_do_modelo": VERSAO_DO_MODELO,
                    "classes": list(CLASSES_DE_MARCA),
                    # `class_names` é a chave que `checkpoint.check_compatible` confere: o modelo de
                    # peças recusa este arquivo em vez de ler marca como peça.
                    "class_names": list(CLASSES_DE_MARCA),
                    "arch_version": arch.version,
                    "regime": regime,
                    "p_marca": p_marca,
                    "p_traco": p_traco,
                    "p_traco_na_marca": p_traco_na_marca,
                    "distracoes": [*TRACOS_DE_DISTRACAO, *QUEBRAS_DE_TRACO, *SUJEIRAS],
                    "bolinha_minima": BOLINHA_MINIMA,
                    "semente": semente,
                    "epoca": epoca,
                    "f1_marcas_val": f1,
                    "confusao_val": confusao.tolist(),
                    "tabuleiros_treino": resultado.tabuleiros_treino,
                    "tabuleiros_val": resultado.tabuleiros_val,
                    "excluidos_do_teste": fora,
                    "limiar": LIMIAR_PADRAO,
                },
            )
    return resultado


class ModeloDeMarcas:
    """O modelo carregado, pronto para ler as marcas de um tabuleiro recortado."""

    def __init__(self, modelo: PieceClassifier, metadata: Mapping[str, object], device: str = "cpu") -> None:
        self.modelo = modelo.eval()
        self.metadata = metadata
        self.device = device
        self.arch = modelo.arch
        limiar = metadata.get("limiar", LIMIAR_PADRAO)
        self.limiar = float(limiar) if isinstance(limiar, (int, float)) else LIMIAR_PADRAO

    def probabilidades(self, tabuleiro_rgb: np.ndarray) -> np.ndarray:
        """`(64, classes)`: a probabilidade de cada classe em cada casa, na ordem de leitura de a8."""
        if tabuleiro_rgb.shape[:2] != (BOARD_SIZE, BOARD_SIZE):
            # O mesmo redimensionamento de `BoardFenDataset._load_board`: o que o treino viu.
            tabuleiro_rgb = cv2.resize(tabuleiro_rgb, (BOARD_SIZE, BOARD_SIZE))
        passo = BOARD_SIZE // 8
        casas = [
            preprocess_cell_to_tensor(
                tabuleiro_rgb[fila * passo : (fila + 1) * passo, coluna * passo : (coluna + 1) * passo], self.arch
            )
            for fila in range(8)
            for coluna in range(8)
        ]
        with torch.no_grad():
            logits = self.modelo(torch.stack(casas).to(self.device))
        return torch.softmax(logits, dim=1).cpu().numpy()

    def ler(self, tabuleiro_rgb: np.ndarray, limiar: float | None = None) -> mc.MarcasDoDiagrama:
        """As marcas de casa deste recorte. É sugestão, como a do detector: a pessoa confirma."""
        limiar = self.limiar if limiar is None else limiar
        probabilidades = self.probabilidades(tabuleiro_rgb)
        casas: dict[str, str] = {}
        for indice, linha in enumerate(probabilidades):
            classe = int(linha.argmax())
            if classe != SEM_MARCA and float(linha[classe]) >= limiar:
                casas[square_name(indice)] = CLASSES_DE_MARCA[classe]
        return mc.MarcasDoDiagrama(casas=casas)


def leitor_de_marcas(caminho: Path, device: str = "cpu") -> Callable[[np.ndarray], dict[str, str]]:
    """O modelo de `caminho` como a conferência o chama: recorte RGB -> `{"c6": "bolinha-branca"}`."""
    modelo = carregar(caminho, device)
    return lambda tabuleiro: dict(modelo.ler(tabuleiro).casas)


def instalar(novo: Path, destino: Path, *, quando: str) -> Path | None:
    """Põe o checkpoint `novo` em `destino` e devolve onde ficou a cópia do que estava lá, se havia.

    A cópia é `marcas_antes_<quando>.pt`, ao lado do destino: o modelo trocado é o que as leituras
    usavam, e voltar a ele não pode depender de treinar de novo. A escrita é atômica, porque uma
    leitura aberta pode estar carregando o arquivo nesse instante. `novo` precisa ser um modelo de
    marcas (`carregar` confere): instalar o `.pt` de peças aqui leria peça como marca.
    """
    carregar(novo)
    destino = Path(destino)
    copia: Path | None = None
    if destino.exists():
        copia = destino.with_name(f"{destino.stem}_antes_{quando}{destino.suffix}")
        atomic_write_bytes(copia, destino.read_bytes())
    atomic_write_bytes(destino, Path(novo).read_bytes())
    return copia


def carregar(caminho: Path, device: str = "cpu") -> ModeloDeMarcas:
    """Abre um checkpoint do modelo de marcas. Um `.pt` de outro modelo levanta `ValueError`."""
    checkpoint = load_checkpoint(Path(caminho), map_location=device)
    metadata = dict(checkpoint.metadata)
    if metadata.get("modelo") != MODELO:
        raise ValueError(f"{caminho} não é um modelo de marcas (modelo: {metadata.get('modelo')!r}).")
    if list(metadata.get("classes", [])) != list(CLASSES_DE_MARCA):
        raise ValueError(f"{caminho} tem outras classes: {metadata.get('classes')!r}.")
    arch = ArchConfig.from_version(str(metadata.get("arch_version", DEFAULT_ARCH.version)))
    modelo = PieceClassifier(arch, num_classes=len(CLASSES_DE_MARCA))
    modelo.load_state_dict(checkpoint.state)
    return ModeloDeMarcas(modelo.to(device), metadata, device)
