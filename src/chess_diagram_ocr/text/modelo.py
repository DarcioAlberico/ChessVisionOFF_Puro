"""O classificador de caracteres, carregado pinado ao metadado que o descreve (S-179).

**O par não pode se descasar, e o estrago de descasar é calado.** `idx_to_char` traduz índice em
caractere; índices de outro treino apontam para as letras erradas. Nada levanta, nada avisa -- o
OCR só passa a ler outra coisa. É a mesma família do defeito que fez 127 amostras treinarem a
classe errada por meses no projeto de origem, e a mesma que a S-40 já trava aqui do lado do
classificador de peças, recusando retomar uma exportação com o modelo trocado.

Daí esta ser a **única** porta para o classificador existir, e daí ela levantar em vez de
devolver `None`: um reconhecedor que carregou o par errado responde com a confiança de sempre.

**O que o metadado manda, e por quê:**

| campo | o que ele decide | o que acontece sem ele |
|---|---|---|
| `num_classes` | a última camada da rede | pesos de outro formato: `load_state_dict` já falhava alto |
| `idx_to_char` | índice -> caractere | é o descasamento calado; não tem como faltar |
| `modelo_sha256` | se este `.pt` é o descrito | o par trocado passa |
| `classes_sha256` | se a lista de classes é a do treino | renomear pasta não desalinha, mas trocar a lista sim |
| `temperatura` | a escala da confiança | softmax cru, e **toda** régua deste plano se desregula |

**A temperatura é obrigatória aqui, e no projeto de origem não era.** Lá ela tem de tolerar
modelo anterior à calibração; aqui todo modelo sai de `cvoff-texto-train`, que calibra na
validação antes de gravar (S-205) e não tem caminho que produza pesos sem temperatura. E o
achado que justifica a diferença é do outro lado do projeto: a avaliação de 2026-08-18 nomeou
que a métrica primária **mede confiança e não correção**. Herdar um caminho que aceita confiança
não calibrada seria repetir isso de propósito.

**Os pesos não moram no repositório.** São 2,6 MB de binário, e o `.gitignore` manda `*.pt` para
fora desde a S-29. O metadado mora (`models/char_meta.json`, 9 KB) porque é ele que descreve as
classes -- e é exatamente essa assimetria que torna o `modelo_sha256` necessário: quem clona
recebe o metadado sem o modelo, e basta aparecer um `.pt` de outra rodada com o mesmo número de
classes para o par ficar trocado.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from ..config import PROJECT_ROOT
from .classes import char_to_folder

if TYPE_CHECKING:  # pragma: no cover - só para o verificador de tipos
    import torch

logger = logging.getLogger(__name__)

CAMINHO_PADRAO_META = PROJECT_ROOT / "models" / "char_meta.json"
"""O metadado é versionado. Os pesos não -- ver o cabeçalho deste módulo."""

LADO = 32
"""Lado do recorte que a rede recebe. **Não é ajustável**: a base de treino inteira foi gravada
nesse tamanho, e mudá-lo aqui compara maçã com laranja."""

SCHEMA_MINIMO = 2
"""`schema_version` 1 não tem impressão digital nem calibração. Ver o cabeçalho."""


class ModeloInvalido(RuntimeError):
    """O par (modelo, metadado) não é utilizável. A mensagem diz qual dos dois e por quê."""


def impressao_do_arquivo(caminho: Path) -> str:
    """SHA-256 do conteúdo, em blocos. Vazio quando o arquivo não pode ser lido."""
    digest = hashlib.sha256()
    try:
        with caminho.open("rb") as arquivo:
            for pedaco in iter(lambda: arquivo.read(1 << 20), b""):
                digest.update(pedaco)
    except OSError:
        return ""
    return digest.hexdigest()


def impressao_das_classes(idx_to_char: dict[int, str]) -> str:
    """SHA-256 do mapa índice->caractere.

    A forma canônica é `"{indice}\\t{caractere}"` por linha, ordenada por índice, unida por
    `\\n` -- **igual à do projeto de origem, byte a byte**, senão o `classes_sha256` gravado lá
    não pode ser conferido aqui.
    """
    itens = sorted(idx_to_char.items())
    return hashlib.sha256("\n".join(f"{i}\t{c}" for i, c in itens).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Arquitetura:
    """A forma da rede, como **dado** e não como código (S-204).

    **Ela precisou virar dado no dia em que a grade de variantes começou.** Até aqui a forma era
    a `SimpleCNN` do projeto de origem, cravada: 1→32→64→128, densa 2.048→256. Um braço de grade
    que mude os canais ou a densa produz pesos que `load_state_dict` recusa -- que é o
    comportamento certo --, e a única saída honesta é a que a S-204 já pedia: **a grade muda os
    dois lados de uma vez ou não muda nenhum.** O metadado passa a dizer qual forma carregar.

    Metadado sem este campo é o formato de antes da grade, e ele carrega como a forma padrão --
    que é literalmente a que ele descreve.
    """

    canais: tuple[int, int, int] = (32, 64, 128)
    densa: int = 256

    @property
    def versao(self) -> str:
        """Identidade da forma, para o metadado e para a tabela da grade."""
        return f"c{'-'.join(str(c) for c in self.canais)}d{self.densa}"

    @property
    def parametros(self) -> int:
        """Contagem aproximada, para a tabela: é o número que a hipótese da S-204 questiona.

        A densa domina: com (32, 64, 128) e 256, ela sozinha são 128×4×4×256 = 524.288 dos
        620.300 parâmetros -- 85%. Para 12 classes de peça isso não pagava; para 314 de texto,
        ninguém tinha medido.
        """
        a, b, c = self.canais
        conv = (1 * a * 9 + a) + (a * b * 9 + b) + (b * c * 9 + c)
        return conv + (c * 4 * 4 * self.densa + self.densa)

    def como_dicionario(self) -> dict[str, Any]:
        return {"canais": list(self.canais), "densa": self.densa}

    @classmethod
    def de_dicionario(cls, dados: Any) -> Arquitetura:
        """O que o metadado trouxe, ou a forma padrão quando ele não traz nada."""
        if not isinstance(dados, dict):
            return cls()
        canais = dados.get("canais")
        if not (isinstance(canais, list) and len(canais) == 3 and all(isinstance(c, int) for c in canais)):
            raise ModeloInvalido(f"arquitetura com canais inválidos: {canais!r}")
        densa = dados.get("densa")
        if not isinstance(densa, int) or densa <= 0:
            raise ModeloInvalido(f"arquitetura com densa inválida: {densa!r}")
        return cls(canais=(canais[0], canais[1], canais[2]), densa=densa)


ARQUITETURA_PADRAO = Arquitetura()
"""A do projeto de origem, e a do par que está publicado."""


@dataclass(frozen=True)
class MetadadoDeClasses:
    """O `models/char_meta.json` já validado. Construído só por `ler_metadado`."""

    idx_to_char: dict[int, str]
    num_classes: int
    temperatura: float
    modelo_sha256: str
    classes_sha256: str
    treinado_em: str
    arquitetura: Arquitetura = ARQUITETURA_PADRAO

    @property
    def alfabeto(self) -> tuple[str, ...]:
        """Os caracteres que o modelo conhece, em ordem de índice."""
        return tuple(self.idx_to_char[i] for i in sorted(self.idx_to_char))


def ler_metadado(caminho: Path = CAMINHO_PADRAO_META) -> MetadadoDeClasses:
    """Lê e confere o metadado. Levanta `ModeloInvalido` com o motivo em pt-BR."""
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ModeloInvalido(f"Não foi possível ler o metadado das classes em {caminho}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ModeloInvalido(f"{caminho.name} não é um JSON válido: {exc}") from exc

    if not isinstance(bruto, dict):
        raise ModeloInvalido(f"{caminho.name} não contém um objeto.")

    schema = bruto.get("schema_version", 1)
    if not isinstance(schema, int) or schema < SCHEMA_MINIMO:
        raise ModeloInvalido(
            f"{caminho.name} está no formato {schema}, e este projeto exige o {SCHEMA_MINIMO}. "
            "O formato antigo não traz impressão digital nem calibração, e sem as duas a "
            "confiança que o modelo reporta não corresponde a nada."
        )

    mapa_bruto = bruto.get("idx_to_char")
    if not isinstance(mapa_bruto, dict) or not mapa_bruto:
        raise ModeloInvalido(f"{caminho.name} não traz `idx_to_char`, que é o que traduz índice em caractere.")
    try:
        idx_to_char = {int(chave): str(valor) for chave, valor in mapa_bruto.items()}
    except (TypeError, ValueError) as exc:
        raise ModeloInvalido(f"{caminho.name} tem `idx_to_char` com chave que não é índice: {exc}") from exc

    num_classes = bruto.get("num_classes")
    if not isinstance(num_classes, int) or num_classes != len(idx_to_char):
        raise ModeloInvalido(
            f"{caminho.name} declara {num_classes} classes e o mapa tem {len(idx_to_char)}. "
            "Os dois vêm da mesma rodada de treino ou nenhum dos dois vale."
        )

    faltando = sorted(set(range(num_classes)) - set(idx_to_char))
    if faltando:
        raise ModeloInvalido(
            f"{caminho.name} tem buraco em `idx_to_char`: falta o índice {faltando[0]}. "
            "A saída da rede é indexada de 0 a n-1, e um buraco vira um caractere errado."
        )

    temperatura = bruto.get("temperatura")
    if not isinstance(temperatura, int | float) or not float(temperatura) > 0:
        raise ModeloInvalido(
            f"{caminho.name} não traz uma `temperatura` positiva. Um modelo sem calibração "
            "reporta softmax cru, e é a confiança que decide o corte de legenda, o árbitro do "
            "corte de glifo e a ordem da fila de revisão. Calibre antes de usar."
        )

    if float(temperatura) == 1.0:
        # **Ausência e 1,0 são coisas diferentes, e por isso uma levanta e a outra avisa.**
        # Ausência é silêncio: ninguém decidiu nada, e o padrão neutro seria um chute nosso.
        # Um 1,0 escrito é uma declaração -- "este modelo está em softmax cru, e eu sei".
        #
        # O aviso existe porque a declaração vira invisível depois de gravada, e foi assim que
        # o projeto de origem rodou um dia inteiro sem calibração sem ninguém notar (a F25 de lá
        # só achou porque foi medir outra coisa). Medido lá: sem calibração, o filtro "só
        # pendentes" mostra 11% dos erros da rede; com ela, 23%.
        logger.warning(
            "%s declara temperatura 1,0: este modelo está em softmax cru. A confiança que ele "
            "reporta é o que decide o corte de legenda, o árbitro do corte de glifo e a ordem da "
            "fila de revisão -- nenhum desses números é comparável com os de um modelo "
            "calibrado. Ver a S-205.",
            caminho.name,
        )

    modelo_sha = str(bruto.get("modelo_sha256", "") or "")
    if not modelo_sha:
        raise ModeloInvalido(
            f"{caminho.name} não traz `modelo_sha256`. Sem ele não há como saber se o `.pt` ao "
            "lado é o modelo que este metadado descreve, e um par trocado lê outra coisa em "
            "silêncio."
        )

    classes_sha = str(bruto.get("classes_sha256", "") or "")
    recalculado = impressao_das_classes(idx_to_char)
    if classes_sha and classes_sha != recalculado:
        raise ModeloInvalido(
            f"{caminho.name} foi editado depois de gravado: `classes_sha256` diz {classes_sha[:12]}… "
            f"e a lista de classes dá {recalculado[:12]}…"
        )

    desconhecidas = [c for c in idx_to_char.values() if not c]
    if desconhecidas:
        raise ModeloInvalido(f"{caminho.name} tem classe com caractere vazio.")

    return MetadadoDeClasses(
        idx_to_char=idx_to_char,
        num_classes=num_classes,
        temperatura=float(temperatura),
        modelo_sha256=modelo_sha,
        classes_sha256=classes_sha or recalculado,
        treinado_em=str(bruto.get("treinado_em", "") or ""),
        arquitetura=Arquitetura.de_dicionario(bruto.get("arquitetura")),
    )


def pastas_do_metadado(meta: MetadadoDeClasses) -> dict[str, str]:
    """`nome de pasta -> caractere`, para quem varre a base de treino no disco (S-200).

    Usa `folder_to_char` em modo estrito na volta, que é o ponto: uma pasta que não decodifica
    tem de ser um achado nomeado, e não uma classe que some.
    """
    return {char_to_folder(c): c for c in meta.idx_to_char.values()}


def _construir_rede(num_classes: int, arquitetura: Arquitetura = ARQUITETURA_PADRAO) -> torch.nn.Module:
    """A `SimpleCNN` do projeto de origem, com a forma que o metadado disser.

    **A forma continua sendo ditada pelos pesos, e é por isso que ela virou dado.** Três blocos
    conv com `MaxPool2d(2)` cada, achatamento de `canais[2]*4*4`, densa até `densa`,
    `Dropout(0.5)`, densa até `num_classes`. Qualquer desvio entre o que se constrói e o que o
    `.pt` tem faz `load_state_dict` recusar -- o que é o comportamento certo. O padrão é
    exatamente a forma do porte literal, e é a do par publicado.

    **Os nomes das camadas não mudam com a forma**, e isso não é detalhe: um `.pt` do projeto de
    origem tem de continuar carregando aqui, e ele traz `conv1`, `fc1` e companhia.
    """
    import torch.nn as nn
    import torch.nn.functional as F

    a, b, c = arquitetura.canais
    achatado = c * 4 * 4

    class SimpleCNN(nn.Module):
        def __init__(self, num_classes: int) -> None:
            super().__init__()
            self.conv1 = nn.Conv2d(1, a, kernel_size=3, padding=1)
            self.pool1 = nn.MaxPool2d(2, 2)
            self.conv2 = nn.Conv2d(a, b, kernel_size=3, padding=1)
            self.pool2 = nn.MaxPool2d(2, 2)
            self.conv3 = nn.Conv2d(b, c, kernel_size=3, padding=1)
            self.pool3 = nn.MaxPool2d(2, 2)
            self.fc1 = nn.Linear(achatado, arquitetura.densa)
            self.dropout = nn.Dropout(0.5)
            self.fc2 = nn.Linear(arquitetura.densa, num_classes)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            x = self.pool1(F.relu(self.conv1(x)))
            x = self.pool2(F.relu(self.conv2(x)))
            x = self.pool3(F.relu(self.conv3(x)))
            x = x.view(-1, achatado)
            x = F.relu(self.fc1(x))
            x = self.dropout(x)
            return self.fc2(x)

    return SimpleCNN(num_classes)


class ClassificadorDeGlifo:
    """Um recorte de 32x32 em cinza -> (caractere, confiança calibrada).

    Construído só por `carregar_classificador`, que é quem confere o par.
    """

    def __init__(self, modelo: Any, meta: MetadadoDeClasses, device: str) -> None:
        self._modelo = modelo
        self._meta = meta
        self._device = device

    @property
    def meta(self) -> MetadadoDeClasses:
        return self._meta

    @property
    def device(self) -> str:
        return self._device

    def _entrada(self, recortes: list[np.ndarray]) -> torch.Tensor:
        """Lote de recortes -> tensor `(n, 1, 32, 32)` em [0, 1].

        **A polaridade é a da página: tinta escura sobre papel claro, em cinza cru.** A base de
        treino foi gravada assim -- não binarizada, não invertida --, e alimentar o modelo com
        tinta branca troca todas as classes por outras com folga de confiança. Quem inverte é
        `text/negativo.py` (S-195), antes de chegar aqui, e só onde a página está em negativo.
        """
        import cv2
        import torch

        lote = np.empty((len(recortes), 1, LADO, LADO), dtype=np.float32)
        for i, recorte in enumerate(recortes):
            cinza = cv2.cvtColor(recorte, cv2.COLOR_RGB2GRAY) if recorte.ndim == 3 else recorte
            lote[i, 0] = cv2.resize(cinza, (LADO, LADO)).astype(np.float32) / 255.0
        return torch.from_numpy(lote).to(self._device)

    def probabilidades(self, recortes: list[np.ndarray]) -> np.ndarray:
        """Matriz `(n, num_classes)` já dividida pela temperatura. Vazia para lote vazio."""
        import torch
        import torch.nn.functional as F

        if not recortes:
            return np.empty((0, self._meta.num_classes), dtype=np.float32)

        with torch.no_grad():
            logits = self._modelo(self._entrada(recortes))
            probs = F.softmax(logits / self._meta.temperatura, dim=1)
        return probs.cpu().numpy().astype(np.float32)

    def classificar(self, recortes: list[np.ndarray]) -> list[tuple[str, float]]:
        """`[(caractere, confiança), ...]`, um por recorte, na mesma ordem."""
        probs = self.probabilidades(recortes)
        if probs.size == 0:
            return []
        indices = probs.argmax(axis=1)
        return [(self._meta.idx_to_char[int(i)], float(probs[linha, i])) for linha, i in enumerate(indices)]

    def margem(self, recortes: list[np.ndarray]) -> list[float]:
        """`1 - p2/p1` por recorte: o vencedor estava claramente à frente?

        Está aqui porque o custo é zero -- as probabilidades já foram calculadas --, e não
        porque alguma coisa já a use. **A S-212 só a liga depois de medir**: no projeto de
        origem, duas fases concluíram que a margem ordena a fila melhor que a confiança, e a
        terceira mostrou que as duas estavam medindo errado.
        """
        probs = self.probabilidades(recortes)
        if probs.size == 0:
            return []
        duas = np.sort(probs, axis=1)[:, -2:]
        p1, p2 = duas[:, 1], duas[:, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            margens = np.where(p1 > 0.0, 1.0 - p2 / p1, 0.0)
        return [float(min(1.0, max(0.0, m))) for m in margens]


_CACHE: dict[tuple[str, str, str, int, int], ClassificadorDeGlifo] = {}
"""Chave: (caminho dos pesos, caminho do metadado, device, mtime_ns, tamanho).

O `mtime_ns` e o tamanho estão na chave para que **trocar o arquivo no disco invalide o
cache**. Sem eles, retreinar durante uma sessão deixaria o classificador antigo em memória
respondendo com o mapa novo -- que é o descasamento que este módulo inteiro existe para
impedir, entrando pela porta dos fundos.
"""


def _escolher_device(pedido: str | None) -> str:
    if pedido:
        return pedido
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def carregar_classificador(
    meta: Path = CAMINHO_PADRAO_META,
    pesos: Path | None = None,
    *,
    device: str | None = None,
) -> ClassificadorDeGlifo:
    """Recusa por hash **antes** do `torch.load`. Não devolve `None`: ou carrega, ou levanta.

    `pesos=None` procura o `.pt` ao lado do metadado, com o mesmo nome-base.
    """
    meta = Path(meta)
    metadado = ler_metadado(meta)

    if pesos is None:
        pesos = meta.with_suffix(".pt")
        if not pesos.exists():
            pesos = meta.parent / f"{meta.stem.replace('_meta', '')}_classifier.pt"
    pesos = Path(pesos)

    if not pesos.exists():
        raise ModeloInvalido(
            f"Os pesos do classificador de caracteres não estão em {pesos}.\n\n"
            "Eles não vêm no repositório: são 2,6 MB de binário, e o `.gitignore` manda `*.pt` "
            "para fora. Aponte o arquivo em data/settings.json (`ocr.glyph_model`) ou em "
            "CVOFF_OCR_GLYPH_MODEL. O metadado que descreve as classes está em "
            f"{meta.name} e é o que diz qual `.pt` serve. `cvoff-texto-train` refaz o par."
        )

    encontrado = impressao_do_arquivo(pesos)
    if encontrado != metadado.modelo_sha256:
        raise ModeloInvalido(
            f"{pesos.name} não é o modelo descrito por {meta.name}.\n\n"
            f"  o metadado espera  {metadado.modelo_sha256}\n"
            f"  o arquivo tem      {encontrado or '(ilegível)'}\n\n"
            "Os dois precisam vir da mesma rodada de treino: o metadado traduz índice em "
            "caractere, e índices de outro treino apontam para as letras erradas, sem erro "
            "nenhum e sem aviso nenhum."
        )

    device = _escolher_device(device)
    try:
        estado = pesos.stat()
        chave = (str(pesos.resolve()), str(meta.resolve()), device, estado.st_mtime_ns, estado.st_size)
    except OSError as exc:  # pragma: no cover - arquivo sumiu entre o hash e o stat
        raise ModeloInvalido(f"Não foi possível inspecionar {pesos}: {exc}") from exc

    em_cache = _CACHE.get(chave)
    if em_cache is not None:
        return em_cache

    import torch

    rede = _construir_rede(metadado.num_classes, metadado.arquitetura)
    try:
        rede.load_state_dict(torch.load(pesos, map_location=device))
    except (RuntimeError, KeyError) as exc:
        raise ModeloInvalido(
            f"{pesos.name} tem o hash certo mas não carrega na rede de {metadado.num_classes} "
            f"classes ({exc}). O metadado e os pesos foram gravados por versões diferentes do "
            "treino."
        ) from exc
    rede.to(device)
    rede.eval()

    classificador = ClassificadorDeGlifo(rede, metadado, device)
    _CACHE[chave] = classificador
    logger.info(
        "Classificador de caracteres pronto: %d classes, temperatura %.4f, treinado em %s, em %s.",
        metadado.num_classes,
        metadado.temperatura,
        metadado.treinado_em or "(data não registrada)",
        device,
    )
    return classificador


def dispositivo_em_uso() -> str | None:
    """O dispositivo do classificador de caracteres carregado nesta sessão, ou `None`.

    **Pergunta ao cache, e não carrega nada.** É o que o rodapé precisa saber (S-182), e ele não
    pode ser o motivo de 2,6 MB de pesos subirem para a memória: quem decide carregar é quem vai
    classificar.

    `None` quer dizer "não há classificador carregado", e as duas razões normais para isso são
    os pesos não estarem no disco e o motor de leitura escolhido ser outro (S-42). Distinguir as
    duas é da configuração, não daqui.

    Devolve o **último** carregado quando há mais de um: o cache guarda uma entrada por par de
    arquivos, e um retreino no meio da sessão põe a nova ao lado da velha.
    """
    for classificador in reversed(_CACHE.values()):
        return classificador.device
    return None


def limpar_cache() -> None:
    """Esvazia o cache de classificadores. Para os testes, e para quem retreina em sessão."""
    _CACHE.clear()


__all__ = [
    "ARQUITETURA_PADRAO",
    "CAMINHO_PADRAO_META",
    "LADO",
    "Arquitetura",
    "ClassificadorDeGlifo",
    "MetadadoDeClasses",
    "ModeloInvalido",
    "carregar_classificador",
    "dispositivo_em_uso",
    "impressao_das_classes",
    "impressao_do_arquivo",
    "ler_metadado",
    "limpar_cache",
    "pastas_do_metadado",
]
