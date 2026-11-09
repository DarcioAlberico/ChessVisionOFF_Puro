"""O executor do Tesseract: um processo por folha, sem console, sem órfão, e sem calar erro (S-720).

**Fora de `ocr.py`, e é a primeira decisão do item.** `ocr.py` tem um `TesseractRecognizer` para faixa
e página, mas está no digest da S-218: mexer nele invalida os quatro relatórios de campo. E aquele
descarta palavra abaixo de `MIN_CONFIDENCE`, que aqui é o sinal da marca por palavra.

**Um TIFF de várias páginas pelo stdin, uma linha por página, em `psm 7`.** Medido na rodada 6: empilhar
as linhas numa imagem só (`psm 6`) muda o reconhecimento -- 14 de 55 linhas no *Dvoretsky*, e o TSV
devolveu 62 linhas para 55. O TIFF deu **zero** linhas diferentes da leitura por processo, a uma fração
do custo. Por stdin e nunca por caminho: caminho acentuado quebra em máquina cp1252, e esta máquina,
em UTF-8, não reproduz o defeito.

**O contrato distingue "não leu" de "leu vazio".** `None` é motor ausente, timeout ou erro: a linha fica
com o glifo e a folha ganha aviso. `""` é o Tesseract dizendo que ali não há texto. Confundir os dois
apagaria texto em silêncio toda vez que o binário faltasse.

**Resolução segura.** Só caminho absoluto: bundle, `TESSERACT_CMD`, o PATH varrido **sem** o diretório
corrente -- com nome nu o Windows procura primeiro na pasta corrente, e um PDF aberto de uma pasta
qualquer executaria o que estivesse lá -- e a pasta de instalação padrão. A versão é conferida: um 4.x
no PATH leria sem erro e diferente, e o número medido não valeria para ele.
"""

from __future__ import annotations

import io
import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

VERSOES_MEDIDAS = (5,)
"""As versões principais em que os números do roadmap valem."""

LINGUAS: tuple[str, ...] = ("eng", "por", "spa", "deu", "nld", "fra", "ron", "rus")
"""As línguas do acervo, na ordem em que a caixa as oferece. `ocr._TESSERACT_LANGS` não conhece `nl`."""

LINGUA_PADRAO = "eng"

TIMEOUT_MINIMO = 10.0
TIMEOUT_POR_LINHA = 1.0
"""Segundos. O teto é 10× o p99 medido por folha, com piso de 10 s: um Tesseract travado não pode prender
a `Tarefa` do Qt, e uma folha de 80 linhas lidas em 4 s não pode ser morta por um teto curto."""

TETO_DE_MEGAPIXELS = 60.0
"""Acima disto a imagem não vai ao Tesseract: ~124 MB por processo a 600 dpi, e um PDF pode pedir gigabytes."""

MARGEM_DO_RECORTE = 10
"""Pixels brancos em volta da linha. Sem eles o `psm 7` come a primeira e a última letra."""

_NOMES_DO_BINARIO = ("tesseract.exe", "tesseract") if os.name == "nt" else ("tesseract",)
_INSTALADO_EM = (Path(r"C:\Program Files\Tesseract-OCR"), Path(r"C:\Program Files (x86)\Tesseract-OCR"))
_CRIAR_SEM_JANELA = 0x08000000


@dataclass(frozen=True)
class Motor:
    """O Tesseract achado, ou o motivo de não haver um."""

    binario: Path | None = None
    tessdata: Path | None = None
    versao: str = ""
    motivo: str = ""
    """A frase para o aviso, quando `binario` é `None`."""

    @property
    def disponivel(self) -> bool:
        return self.binario is not None


@dataclass(frozen=True)
class Palavra:
    """Uma palavra do TSV. A caixa está em pixels da imagem daquela página do TIFF."""

    texto: str
    confianca: float
    caixa: tuple[int, int, int, int]
    pagina: int = 1
    bloco: int = 0
    paragrafo: int = 0
    linha: int = 0


@dataclass(frozen=True)
class LinhaDoTesseract:
    """O que o Tesseract leu num recorte: o texto, e a confiança palavra a palavra (0 a 1)."""

    texto: str
    confiancas: tuple[float, ...] = ()
    palavras: tuple[Palavra, ...] = field(default=(), compare=False)


def resolver_binario(
    ambiente: Mapping[str, str] | None = None,
    *,
    congelado_em: Path | None = None,
    instalado_em: Sequence[Path] = _INSTALADO_EM,
) -> Path | None:
    """Onde está o binário, **sempre** como caminho absoluto. `None` se não há nenhum."""
    amb = os.environ if ambiente is None else ambiente
    base = congelado_em
    if base is None and getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", ""))
    candidatos: list[Path] = []
    if base is not None:
        candidatos += [base / "tesseract" / nome for nome in _NOMES_DO_BINARIO]
    declarado = amb.get("TESSERACT_CMD", "").strip().strip('"')
    if declarado and Path(declarado).is_absolute():
        candidatos.append(Path(declarado))
    for pasta in amb.get("PATH", "").split(os.pathsep):
        pasta = pasta.strip().strip('"')
        # **Só pasta absoluta.** `""` e `"."` no PATH são o diretório corrente, que é o que se evita.
        if pasta and Path(pasta).is_absolute():
            candidatos += [Path(pasta) / nome for nome in _NOMES_DO_BINARIO]
    for pasta_instalada in instalado_em:
        candidatos += [pasta_instalada / nome for nome in _NOMES_DO_BINARIO]
    return next((c for c in candidatos if c.is_file()), None)


def versao_de(texto: str) -> str:
    """A versão na saída de `--version`, que vem no stdout ou no stderr conforme o build. `""` se não há."""
    achada = re.search(r"tesseract\s+v?(\d+(?:\.\d+)*)", texto, re.I)
    return achada.group(1) if achada else ""


def versao_medida(versao: str) -> bool:
    return bool(versao) and versao.split(".")[0].isdigit() and int(versao.split(".")[0]) in VERSOES_MEDIDAS


def _opcoes_do_processo(ambiente: Mapping[str, str]) -> dict[str, object]:
    """Os três *pipes* explícitos e `CREATE_NO_WINDOW`: o bundle é `console=False`, e pisca console sem isso."""
    opcoes: dict[str, object] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "env": dict(ambiente),
    }
    if os.name == "nt":
        opcoes["creationflags"] = _CRIAR_SEM_JANELA
    return opcoes


_ERRO_NO_STDERR = re.compile(r"^\s*(error|failed)\b|can't open|cannot open", re.I)

_motor_em_cache: Motor | None = None


def achar_motor(*, de_novo: bool = False) -> Motor:
    """O motor desta máquina, procurado uma vez por processo: `--version` custa um processo novo."""
    global _motor_em_cache
    if _motor_em_cache is not None and not de_novo:
        return _motor_em_cache
    _motor_em_cache = examinar(resolver_binario())
    return _motor_em_cache


def examinar(binario: Path | None) -> Motor:
    """Confere o binário achado. Nunca levanta: **ausência não é erro no caminho da janela**."""
    if binario is None:
        return Motor(motivo="O Tesseract não foi encontrado nesta máquina.")
    try:
        processo = subprocess.Popen([str(binario), "--version"], **_opcoes_do_processo(os.environ))  # type: ignore[call-overload]  # noqa: S603
    except (OSError, subprocess.SubprocessError) as exc:
        return Motor(motivo=f"O Tesseract não abriu: {exc}.")
    try:
        saida, erro = processo.communicate(timeout=TIMEOUT_MINIMO)
    except subprocess.TimeoutExpired:
        processo.kill()
        processo.communicate()
        return Motor(motivo=f"O Tesseract não respondeu em {TIMEOUT_MINIMO:.0f} s.")
    versao = versao_de(saida.decode("utf-8", "replace") + "\n" + erro.decode("utf-8", "replace"))
    if not versao_medida(versao):
        return Motor(motivo=f"A versão {versao or 'desconhecida'} do Tesseract está fora da medida (5.x).")
    tessdata = binario.parent / "tessdata"
    return Motor(binario=binario, tessdata=tessdata if tessdata.is_dir() else None, versao=versao)


def ambiente_do_processo(motor: Motor, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """O ambiente do processo. **O `TESSDATA_PREFIX` daqui sobrescreve o que estiver no ambiente.**

    Um `TESSDATA_PREFIX` de outra instalação leria com os pesos dela, e o resultado seria outro. Um
    Tesseract por folha com `OMP_THREAD_LIMIT=1`: quem paraleliza é quem chama, e cada processo com
    doze threads em doze núcleos derruba o tempo em vez de ganhar.
    """
    ambiente = dict(os.environ if base is None else base)
    if motor.tessdata is not None:
        ambiente["TESSDATA_PREFIX"] = str(motor.tessdata)
    ambiente["OMP_THREAD_LIMIT"] = "1"
    return ambiente


class _Trabalho:
    """Um *Job Object* com `KILL_ON_JOB_CLOSE`: fechar a janela não deixa `tesseract.exe` órfão.

    Sem efeito fora do Windows, e falhar ao criá-lo não é erro: perde-se a garantia, e não a leitura.
    """

    def __init__(self) -> None:
        self._alca: int | None = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

            class _Limites(ctypes.Structure):
                _fields_ = [
                    ("a", ctypes.c_int64),
                    ("b", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class _Estendido(ctypes.Structure):
                _fields_ = [
                    ("Basic", _Limites),
                    ("Io", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateJobObjectW.restype = wintypes.HANDLE
            kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
            kernel.SetInformationJobObject.argtypes = (
                wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
            )
            alca = kernel.CreateJobObjectW(None, None)
            if not alca:
                return
            limites = _Estendido()
            limites.Basic.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if kernel.SetInformationJobObject(alca, 9, ctypes.byref(limites), ctypes.sizeof(limites)):
                self._alca = alca
                self._kernel = kernel
        except (OSError, AttributeError, ValueError) as exc:  # pragma: no cover - API do Windows
            logger.debug("Sem Job Object para o Tesseract: %s", exc)

    def incluir(self, processo: subprocess.Popen[bytes]) -> None:
        if self._alca is not None:
            self._kernel.AssignProcessToJobObject(self._alca, int(processo._handle))  # type: ignore[attr-defined]  # noqa: SLF001


_trabalho: _Trabalho | None = None


def _no_trabalho(processo: subprocess.Popen[bytes]) -> None:
    global _trabalho
    if _trabalho is None:
        _trabalho = _Trabalho()
    _trabalho.incluir(processo)


class FalhaDoTesseract(RuntimeError):
    """O processo não entregou leitura. A mensagem vira aviso; ninguém mostra texto vazio calado."""


def rodar(
    motor: Motor,
    imagem: bytes,
    *,
    lingua: str,
    dpi: int,
    psm: int,
    timeout: float,
    popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
) -> str:
    """Um processo, a imagem pelo stdin, o TSV de volta. Levanta `FalhaDoTesseract` e nunca devolve `""` calado."""
    if motor.binario is None:
        raise FalhaDoTesseract(motor.motivo or "O Tesseract não foi encontrado.")
    comando = [str(motor.binario), "stdin", "stdout", "-l", lingua, "--psm", str(psm), "--dpi", str(int(dpi)), "tsv"]
    try:
        processo = popen(comando, **_opcoes_do_processo(ambiente_do_processo(motor)))
    except OSError as exc:
        raise FalhaDoTesseract(f"O Tesseract não abriu: {exc}.") from exc
    _no_trabalho(processo)
    try:
        saida, erro = processo.communicate(imagem, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        processo.kill()
        processo.communicate()
        raise FalhaDoTesseract(f"O Tesseract passou de {timeout:.0f} s e foi interrompido.") from exc
    mensagem = erro.decode("utf-8", "replace").strip().splitlines()
    if processo.returncode != 0:
        raise FalhaDoTesseract(f"O Tesseract terminou com erro: {mensagem[-1] if mensagem else processo.returncode}.")
    # Saída 0 com erro no stderr existe (página que ele não abriu, no meio do TIFF). "Estimating resolution"
    # e afins são informação, e passam: só a palavra de erro derruba.
    grave = next((linha for linha in mensagem if _ERRO_NO_STDERR.search(linha)), None)
    if grave is not None:
        raise FalhaDoTesseract(f"O Tesseract avisou um erro: {grave}.")
    return saida.decode("utf-8", "replace")


def palavras_do_tsv(texto: str) -> list[Palavra]:
    """As palavras de uma saída TSV do Tesseract, em ordem. Só o nível 5 traz palavra."""
    palavras: list[Palavra] = []
    for linha in texto.splitlines()[1:]:
        campos = linha.split("\t")
        if len(campos) < 12 or campos[0] != "5" or not campos[11].strip():
            continue
        try:
            x, y, largura, altura = (int(c) for c in campos[6:10])
            confianca = float(campos[10])
            palavras.append(
                Palavra(
                    texto=campos[11],
                    confianca=max(0.0, confianca) / 100.0,
                    caixa=(x, y, x + largura, y + altura),
                    pagina=int(campos[1]),
                    bloco=int(campos[2]),
                    paragrafo=int(campos[3]),
                    linha=int(campos[4]),
                )
            )
        except ValueError:
            continue
    return palavras


def confiancas_por_token(palavras: Sequence[Palavra]) -> tuple[float, ...]:
    """Uma confiança por token de `" ".join(p.texto for p in palavras).split()` (S-853).

    A palavra do TSV pode trazer espaço Unicode dentro (U+2009), e `split()` a parte em duas: contada uma vez,
    ela deslocava a confiança de todas as palavras seguintes, ou cortava as últimas, sem erro nenhum.
    """
    return tuple(p.confianca for p in palavras for _ in p.texto.split())


def _tiff_de(recortes: Sequence[np.ndarray]) -> bytes:
    """Um TIFF de várias páginas, uma linha em cada, com a margem branca. Sem compressão: é um cano."""
    import cv2
    from PIL import Image

    imagens = []
    for recorte in recortes:
        cinza = cv2.cvtColor(recorte, cv2.COLOR_RGB2GRAY) if recorte.ndim == 3 else recorte
        m = MARGEM_DO_RECORTE
        imagens.append(
            Image.fromarray(cv2.copyMakeBorder(cinza, m, m, m, m, cv2.BORDER_CONSTANT, value=255))
        )
    corpo = io.BytesIO()
    imagens[0].save(corpo, format="TIFF", save_all=True, append_images=imagens[1:])
    return corpo.getvalue()


def ler_linhas(
    recortes: Sequence[np.ndarray],
    *,
    lingua: str = LINGUA_PADRAO,
    dpi: int = 220,
    motor: Motor | None = None,
    rodar_tesseract: Callable[..., str] = rodar,
) -> list[LinhaDoTesseract | None]:
    """Um recorte de linha por página do TIFF, um processo só. Levanta `FalhaDoTesseract`.

    Recorte vazio responde `None` sem ir ao processo: ele não tem como ser página de TIFF, e tirá-lo
    deslocaria todas as respostas seguintes. **`None` e não `""`** (S-853): é o contrato do
    `leitor_de_linha` -- `None` é "não leu", e a linha fica com o glifo; `""` é "leu vazio", e a fusão
    derrubava a prosa do glifo por uma leitura que nunca aconteceu.
    """
    achado = achar_motor() if motor is None else motor
    validos = [i for i, r in enumerate(recortes) if r.size]
    saida: list[LinhaDoTesseract | None] = [None for _ in recortes]
    if not validos:
        return saida
    tsv = rodar_tesseract(
        achado,
        _tiff_de([recortes[i] for i in validos]),
        lingua=lingua,
        dpi=dpi,
        psm=7,
        timeout=max(TIMEOUT_MINIMO, TIMEOUT_POR_LINHA * len(validos)),
    )
    por_pagina: dict[int, list[Palavra]] = {}
    for palavra in palavras_do_tsv(tsv):
        por_pagina.setdefault(palavra.pagina, []).append(palavra)
    for posicao, indice in enumerate(validos, start=1):
        palavras = por_pagina.get(posicao, [])
        saida[indice] = LinhaDoTesseract(" ".join(p.texto for p in palavras), confiancas_por_token(palavras), tuple(palavras))
    return saida


def ler_folha(
    cinza: np.ndarray,
    *,
    lingua: str = LINGUA_PADRAO,
    dpi: int = 220,
    psm: int = 3,
    motor: Motor | None = None,
    rodar_tesseract: Callable[..., str] = rodar,
) -> list[Palavra]:
    """A folha inteira, com o leiaute do próprio Tesseract (S-715). Caixas em pixels de `cinza`.

    A imagem vai por PNG: o `psm 3` não tem a questão de página, e PNG é menor no cano. O teto de
    megapixels vale aqui, onde a imagem é a folha toda.
    """
    import cv2

    achado = achar_motor() if motor is None else motor
    if cinza.size == 0:
        return []
    if cinza.shape[0] * cinza.shape[1] / 1e6 > TETO_DE_MEGAPIXELS:
        raise FalhaDoTesseract(f"A folha passa de {TETO_DE_MEGAPIXELS:.0f} MP e não foi ao Tesseract.")
    ok, png = cv2.imencode(".png", cinza)
    if not ok:
        raise FalhaDoTesseract("A folha não pôde ser codificada para o Tesseract.")
    tsv = rodar_tesseract(achado, png.tobytes(), lingua=lingua, dpi=dpi, psm=psm, timeout=max(TIMEOUT_MINIMO, 60.0))
    return palavras_do_tsv(tsv)


__all__ = [
    "LINGUAS",
    "LINGUA_PADRAO",
    "MARGEM_DO_RECORTE",
    "TETO_DE_MEGAPIXELS",
    "TIMEOUT_MINIMO",
    "TIMEOUT_POR_LINHA",
    "VERSOES_MEDIDAS",
    "FalhaDoTesseract",
    "LinhaDoTesseract",
    "Motor",
    "Palavra",
    "achar_motor",
    "ambiente_do_processo",
    "examinar",
    "ler_folha",
    "ler_linhas",
    "palavras_do_tsv",
    "resolver_binario",
    "rodar",
    "versao_de",
    "versao_medida",
]
