"""A bancada da régua da prosa: uma folha, a referência montada, e cada motor lendo a mesma imagem (S-706, S-713).

**Como medir um motor novo (a S-721 começa aqui).** Três portas, da mais à menos integrada:

1. **Ele entra por `ler_pagina(motor="nome")`:** nada a fazer. `cvoff-texto-prosa --motor nome` o mede, porque todo nome de
   `leitor.MOTORES` passa por `_ler_pelo_leitor`. Mudar a regra de `motor="fusao"` e rodar `--motor fusao` mede a regra nova.
2. **É um leitor de linha, ou uma função sobre a folha:** `registrar_motor("nome", funcao)`, com `funcao(folha) -> str`, e
   `motor_de_linha(leitor)` faz a função de um `LeitorDeLinha`, nas caixas que o glifo achou. Quem registra chama o `main`
   do CLI, ou `medir_folha` direto.
3. **Roda em outro processo ou outro Python (a suíte irmã):** grave um JSONL com `{identidade, folha, texto}` e use
   `cvoff-texto-prosa --importar nome=hip.jsonl --dados folhas.jsonl --saida novas.jsonl`. A referência e o placar são os mesmos.

Em todas, o texto da hipótese é **o que o produto mostraria**, linhas em ordem de leitura, e o placar sai de `regua_prosa`.
Medir por fora da montagem mede a ordem das colunas (`medir-texto-so-com-camada-editorada`).

**A referência é a camada, montada pelo mesmo `ler_pagina`, com a mesma imagem e o mesmo dpi**, menos as linhas que cruzam
o retângulo de um diagrama, da camada ou do glifo, e as sem palavra nem lance que cruzam o retângulo crescido de uma casa
(`regua_prosa.fora_da_referencia`). No Seirawan o diagrama é desenhado em fonte.

**Leiaute contra reconhecimento (S-713).** `tess` é o Tesseract nas caixas que o glifo achou; `tess_oraculo`, nas linhas
visuais da camada, apertadas à tinta; `tess_pagina`, na folha inteira, com o leiaute dele. `perda_de_leiaute` = `tess` − `tess_oraculo`.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import fusao as _fusao
from . import regua_prosa as regua

logger = logging.getLogger(__name__)

DPI_PADRAO = 220


@dataclass
class FolhaEmMedida:
    """O que um motor recebe: a folha, já com a imagem que todos os motores leem."""

    pdf: Any
    indice: int
    """Base 0, como `ler_pagina`."""
    lingua: str
    dpi: int
    imagem: np.ndarray
    reconhecedor: object | None
    referencia: Any
    glifo: Any
    linhas_da_referencia: list[Any]
    diagramas: Sequence[Sequence[float]]
    leitor_de_linha: Any = None
    reserva: bool = False
    paginas: dict[str, Any] = field(default_factory=dict)


MotorDeBancada = Callable[[FolhaEmMedida], str]


def recortar(imagem: np.ndarray, caixa: Sequence[float], dpi: int, folga: float = 0.12) -> np.ndarray:
    """O recorte de uma linha, com a mesma folga nos dois conjuntos de caixas: é o que permite comparar os dois."""
    s = dpi / 72.0
    x0, y0, x1, y1 = (v * s for v in caixa)
    margem = max(2, int(round((y1 - y0) * folga)))
    altura, largura = imagem.shape[:2]
    return imagem[
        max(0, int(y0) - margem): min(altura, int(np.ceil(y1)) + margem),
        max(0, int(x0) - margem): min(largura, int(np.ceil(x1)) + margem),
    ]


def caixas_visuais(linhas: Sequence[Any], imagem: np.ndarray, dpi: int) -> list[tuple[Sequence[float], list[int]]]:
    """As linhas visuais da camada, apertadas à tinta: `[(caixa em pontos, índices das linhas)]`.

    Só junta com o grupo **imediatamente anterior**, à direita dele e a menos de uma altura: é o trecho em negrito partido
    da mesma linha. Juntar por sobreposição vertical funde as duas colunas (o oráculo do *Chess Evolution* foi de 1% a 50%).
    """
    import cv2

    s = dpi / 72.0
    grupos: list[list[Any]] = []
    for k, linha in enumerate(linhas):
        x0, y0, x1, y1 = linha.bbox
        h = max(1e-6, y1 - y0)
        if grupos:
            gx0, gy0, gx1, gy1 = grupos[-1][0]
            sobre = min(y1, gy1) - max(y0, gy0)
            vao = x0 - gx1
            if sobre >= 0.5 * min(h, gy1 - gy0) and -0.5 * h <= vao <= 1.0 * h:
                grupos[-1][0] = (min(x0, gx0), min(y0, gy0), max(x1, gx1), max(y1, gy1))
                grupos[-1][1].append(k)
                continue
        grupos.append([(x0, y0, x1, y1), [k]])
    saida: list[tuple[Sequence[float], list[int]]] = []
    altura, largura = imagem.shape[:2]
    for (x0, y0, x1, y1), indices in grupos:
        a0, b0 = max(0, int(x0 * s)), max(0, int(y0 * s))
        a1, b1 = min(largura, int(x1 * s) + 1), min(altura, int(y1 * s) + 1)
        pedaco = imagem[b0:b1, a0:a1]
        if pedaco.size:
            cinza = cv2.cvtColor(pedaco, cv2.COLOR_RGB2GRAY) if pedaco.ndim == 3 else pedaco
            _, binaria = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            ys, xs = np.nonzero(binaria)
            if len(xs):
                x0, x1 = (a0 + xs.min()) / s, (a0 + xs.max() + 1) / s
                y0, y1 = (b0 + ys.min()) / s, (b0 + ys.max() + 1) / s
        saida.append(((x0, y0, x1, y1), sorted(indices)))
    return saida


def _ler_recortes(folha: FolhaEmMedida, leitor: Any, recortes: Sequence[np.ndarray]) -> list[str]:
    if not recortes:
        return []
    leitura = leitor.ler_linhas(recortes, lingua=folha.lingua, dpi=folha.dpi)
    if leitura.falha:
        raise RuntimeError(f"o leitor de linha não leu: {leitura.falha}")
    return ["" if linha is None else linha.texto for linha in leitura.linhas]


def motor_de_linha(leitor: Any) -> MotorDeBancada:
    """Um `LeitorDeLinha` nas caixas que o glifo achou: o leiaute de produção, e a porta de quem traz outro leitor."""

    def ler(folha: FolhaEmMedida) -> str:
        linhas = regua.linhas_da_pagina(folha.glifo)
        return regua.texto_de(_ler_recortes(folha, leitor, [recortar(folha.imagem, ln.bbox, folha.dpi) for ln in linhas]))

    return ler


def _leitor_da_folha(folha: FolhaEmMedida) -> Any:
    if folha.leitor_de_linha is None:
        from . import leitor_de_linha

        folha.leitor_de_linha = leitor_de_linha.LeitorTesseract()
    return folha.leitor_de_linha


def _tess(folha: FolhaEmMedida) -> str:
    return motor_de_linha(_leitor_da_folha(folha))(folha)


def _tess_oraculo(folha: FolhaEmMedida) -> str:
    visuais = caixas_visuais(folha.linhas_da_referencia, folha.imagem, folha.dpi)
    recortes = [recortar(folha.imagem, caixa, folha.dpi) for caixa, _ in visuais]
    return regua.texto_de(_ler_recortes(folha, _leitor_da_folha(folha), recortes))


def _tess_pagina(folha: FolhaEmMedida) -> str:
    """O Tesseract com o leiaute dele, `psm 3`, diagramas pintados de branco com 8 px de folga."""
    import cv2

    s = folha.dpi / 72.0
    cinza = cv2.cvtColor(folha.imagem, cv2.COLOR_RGB2GRAY).copy()
    for caixa in folha.diagramas:
        x0, y0, x1, y1 = (int(v * s) for v in caixa)
        cinza[max(0, y0 - 8): y1 + 8, max(0, x0 - 8): x1 + 8] = 255
    palavras, falha = _leitor_da_folha(folha).ler_folha(cinza, lingua=folha.lingua, dpi=folha.dpi)
    if falha:
        raise RuntimeError(f"o leitor de linha não leu a folha: {falha}")
    linhas: dict[tuple[int, int, int], list[str]] = {}
    for palavra in palavras:
        linhas.setdefault((palavra.bloco, palavra.paragrafo, palavra.linha), []).append(palavra.texto)
    return regua.texto_de(" ".join(v) for v in linhas.values())


MOTORES_DE_BANCADA: dict[str, MotorDeBancada] = {
    "tess": _tess,
    "tess_oraculo": _tess_oraculo,
    "tess_pagina": _tess_pagina,
}


def registrar_motor(nome: str, funcao: MotorDeBancada) -> None:
    """Põe um motor na bancada, para `--motor nome` e `medir_folha`. Ver o cabeçalho."""
    MOTORES_DE_BANCADA[nome] = funcao


def _ler_pelo_leitor(folha: FolhaEmMedida, motor: str) -> Any:
    from .leitor import ler_pagina

    return ler_pagina(
        folha.pdf, folha.indice, motor=motor, reconhecedor=folha.reconhecedor, imagem_rgb=folha.imagem, dpi=folha.dpi,  # type: ignore[arg-type]
        lingua=folha.lingua, reserva=folha.reserva, leitor_de_linha=folha.leitor_de_linha,
    )


def motores_conhecidos() -> tuple[str, ...]:
    from .leitor import MOTORES

    return (*MOTORES, *MOTORES_DE_BANCADA)


def preparar_folha(
    pdf: Any,
    indice: int,
    *,
    lingua: str,
    imagem: np.ndarray,
    reconhecedor: object | None,
    dpi: int = DPI_PADRAO,
    leitor_de_linha: Any = None,
    reserva: bool = False,
) -> FolhaEmMedida:
    """A referência da folha e a leitura do glifo, que todo motor de bancada e a própria referência usam."""
    from .leitor import ler_pagina

    referencia = ler_pagina(pdf, indice, motor="camada", imagem_rgb=imagem, dpi=dpi)
    glifo = ler_pagina(pdf, indice, motor="glifo", reconhecedor=reconhecedor, imagem_rgb=imagem, dpi=dpi, lingua=lingua)
    diagramas = [d.bbox for d in referencia.diagramas] + [d.bbox for d in glifo.diagramas]
    todas = regua.linhas_da_pagina(referencia)
    linhas = [ln for ln in todas if not regua.fora_da_referencia(ln.texto, ln.bbox, diagramas, lingua)]
    return FolhaEmMedida(
        pdf=pdf, indice=indice, lingua=lingua, dpi=dpi, imagem=imagem, reconhecedor=reconhecedor, referencia=referencia,
        glifo=glifo, linhas_da_referencia=linhas, diagramas=diagramas, leitor_de_linha=leitor_de_linha, reserva=reserva,
    )


def preservacao_de_figurina(glifo: Sequence[str], fundida: Sequence[str]) -> tuple[int, int]:
    """Quantos tokens com figurina do glifo chegam idênticos ao outro texto (G1, sem referência)."""
    figurinas = [t for linha in glifo for t in linha.split() if re.search(r"[♔-♟]", t)]
    restam = Counter(t for linha in fundida for t in linha.split())
    presentes = 0
    for token in figurinas:
        if restam[token] > 0:
            restam[token] -= 1
            presentes += 1
    return presentes, len(figurinas)


def pontuar_hipoteses(ref: str, hipoteses: dict[str, str], lingua: str) -> dict[str, dict[str, Any]]:
    """O placar de cada hipótese, nas duas normalizações, com as chaves do JSONL: `motor|tip`, `motor|cru`."""
    placar = {}
    for modo in regua.MODOS:
        r = regua.normalizar(ref, modo, lingua)
        for motor, texto in hipoteses.items():
            placar[f"{motor}|{modo}"] = regua.pontuar(r, regua.normalizar(texto, modo, lingua), lingua).para_dict()
    return placar


def medir_folha(folha: FolhaEmMedida, motores: Sequence[str]) -> dict[str, Any]:
    """Lê a folha com cada motor e devolve o registro do JSONL: **com texto de livro**, e por isso fora do repositório."""
    from .leitor import MOTORES

    hipoteses: dict[str, str] = {}
    tempo: dict[str, float] = {}
    avisos: dict[str, list[str]] = {}
    preservacao: dict[str, list[int]] = {}
    vetos: dict[str, list[list[str]]] = {}
    linhas_do_glifo = [ln.texto for ln in regua.linhas_da_pagina(folha.glifo)]
    for motor in motores:
        inicio = time.perf_counter()
        if motor in MOTORES:
            ouvidos: list[list[str]] = []
            _fusao.OUVINTE_DE_VETOS = lambda glifo, palavra, destino=ouvidos: destino.append([glifo, palavra])
            try:
                pagina = _ler_pelo_leitor(folha, motor)
            finally:
                _fusao.OUVINTE_DE_VETOS = None
            vetos[motor] = ouvidos
            linhas = [ln.texto for ln in regua.linhas_da_pagina(pagina)]
            hipoteses[motor] = regua.texto_de(linhas)
            avisos[motor] = [a.codigo for a in pagina.avisos]
            preservacao[motor] = list(preservacao_de_figurina(linhas_do_glifo, linhas))
        elif motor in MOTORES_DE_BANCADA:
            hipoteses[motor] = MOTORES_DE_BANCADA[motor](folha)
        else:
            raise ValueError(f"motor desconhecido: {motor!r}; os que existem: {motores_conhecidos()}")
        tempo[motor] = time.perf_counter() - inicio
    ref = regua.texto_de(ln.texto for ln in folha.linhas_da_referencia)
    return {
        "ref": ref,
        "hip": hipoteses,
        "placar": pontuar_hipoteses(ref, hipoteses, folha.lingua),
        "tempo": tempo,
        "avisos": avisos,
        "preservacao": preservacao,
        "vetos": vetos,
        "n_linhas": {
            "ref": len(folha.linhas_da_referencia),
            "ref_no_diagrama": len(regua.linhas_da_pagina(folha.referencia)) - len(folha.linhas_da_referencia),
            "glifo": len(linhas_do_glifo),
        },
    }


__all__ = [
    "DPI_PADRAO",
    "MOTORES_DE_BANCADA",
    "FolhaEmMedida",
    "caixas_visuais",
    "medir_folha",
    "motor_de_linha",
    "motores_conhecidos",
    "pontuar_hipoteses",
    "preparar_folha",
    "preservacao_de_figurina",
    "recortar",
    "registrar_motor",
]
