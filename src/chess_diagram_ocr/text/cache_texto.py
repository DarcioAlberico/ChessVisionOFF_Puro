"""A leitura do Tesseract guardada: quem relê uma folha não paga o processo de novo (S-725).

**Só a janela o usa, e isso é o contrato.** `LeitorTesseract()` nasce sem cache, e é o que a régua, a bancada e os CLIs
recebem: uma medição que respondesse do disco mediria a leitura de outro dia, com o `tessdata` de outro dia, e sairia
plausível. Quem liga é `qt/painel_de_texto._ler`, a mesma regra da reserva da S-715.

**Uma entrada por folha, e não por linha.** A chave leva o sha de cada recorte, na ordem, e a entrada guarda as linhas do lote.
O lote é o que o executor lê num processo só (S-720), e por linha seriam ~40 arquivos por folha, um milhão no acervo. A linha
que muda relê a folha: quem muda uma linha é a segmentação do glifo, e aí costumam mudar várias.

**A chave é completa, porque a leitura errada aqui não dá erro nenhum.** Sha dos recortes, versão do executor e do
pré-processamento, versão do Tesseract, sha do `traineddata` de cada língua do processo, língua, `psm`, `dpi`, as opções e o sha
do modelo. O `modelo` é o do leitor de linha da Fase 105 (S-752): no Tesseract, quem faz esse papel é o `traineddata`, e ele sai
vazio. O classificador de glifo não entra: quem ele influencia é o recorte, e esse já está na chave.

**Disco cheio não custa a leitura.** `gravar` devolve a frase, e a leitura segue: a folha ganha um aviso, que não vai ao arquivo.

**O cache é texto de livro comercial**, e por isso `data/cache_texto/` está no `.gitignore`. Apagar a pasta é sempre seguro: é o
que o menu faz.
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import threading
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..atomic_io import atomic_write_text
from ..config import DATA_DIR
from . import tesseract

logger = logging.getLogger(__name__)

PASTA_PADRAO = DATA_DIR / "cache_texto"
"""Derivado de `DATA_DIR`, e não da raiz: é o que faz o `CVOFF_DATA_DIR` da suíte desviá-lo sem linha nova."""

TETO_MB = 200
"""Uma folha ocupa ~5,5 KB (no máximo 7,9, nas 27 do ouro-dev): 200 MB são mais folhas do que o acervo tem (26.730). Acima disso sai a usada há mais tempo."""

FRACAO_DEPOIS_DO_DESPEJO = 0.9
"""Despeja até aqui, e não até o teto: sem a folga, toda gravação depois de cheio varreria a pasta."""

VERSAO_DA_ENTRADA = 1


@dataclass(frozen=True)
class ChaveDaLeitura:
    """Tudo de que a leitura de um lote depende. Ver o cabeçalho."""

    recortes: str
    executor: str
    preprocessamento: str
    versao_do_tesseract: str
    tessdata: str
    lingua: str
    psm: int
    dpi: int
    opcoes: str = ""
    modelo: str = ""

    @property
    def nome(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode("utf-8")).hexdigest()


def sha_dos_recortes(recortes: Sequence[np.ndarray]) -> str:
    """Forma, tipo e bytes de cada recorte, na ordem: dois recortes iguais em linhas trocadas são outra folha."""
    soma = hashlib.sha256()
    for recorte in recortes:
        soma.update(repr((recorte.shape, str(recorte.dtype))).encode("ascii"))
        soma.update(recorte.tobytes())
    return soma.hexdigest()


_shas_de_arquivo: dict[tuple[str, int, int], str] = {}
_trava_dos_shas = threading.Lock()


def _sha_de_arquivo(caminho: Path) -> str:
    """Uma vez por versão do arquivo: 4 a 20 MB por folha lida seria o custo que o cache existe para tirar."""
    try:
        dados = caminho.stat()
    except OSError:
        return "ausente"
    chave = (str(caminho), dados.st_size, dados.st_mtime_ns)
    with _trava_dos_shas:
        if chave not in _shas_de_arquivo:
            _shas_de_arquivo[chave] = hashlib.sha256(caminho.read_bytes()).hexdigest()
        return _shas_de_arquivo[chave]


def sha_do_tessdata(motor: tesseract.Motor, lingua: str) -> str:
    """O sha de cada `traineddata` do processo: `rus+eng` depende dos dois (S-729)."""
    if motor.tessdata is None:
        return ""
    return "+".join(_sha_de_arquivo(motor.tessdata / f"{parte}.traineddata") for parte in tesseract.lingua_do_processo(lingua).split("+"))


def chave_de(
    recortes: Sequence[np.ndarray],
    *,
    motor: tesseract.Motor,
    lingua: str,
    dpi: int,
    psm: int = tesseract.PSM_DA_LINHA,
    opcoes: Sequence[str] = (),
    modelo: str = "",
) -> ChaveDaLeitura:
    return ChaveDaLeitura(
        recortes=sha_dos_recortes(recortes),
        executor=str(tesseract.VERSAO_DO_EXECUTOR),
        preprocessamento=tesseract.assinatura_do_preprocessamento(),
        versao_do_tesseract=motor.versao,
        tessdata=sha_do_tessdata(motor, lingua),
        lingua=tesseract.lingua_do_processo(lingua),
        psm=int(psm),
        dpi=int(dpi),
        opcoes=" ".join((*opcoes, str(tesseract.PALAVRAS_DO_USUARIO or ""))).strip(),
        modelo=modelo,
    )


def _linha_de(dados: Any) -> tesseract.LinhaDoTesseract:
    return tesseract.LinhaDoTesseract(str(dados["texto"]), tuple(float(c) for c in dados["confiancas"]))


class CacheDeLeitura:
    """A pasta, o teto e o despejo. Seguro entre threads; entre dois programas, o pior caso é uma folha lida de novo."""

    def __init__(self, pasta: Path | None = None, *, teto_mb: float = TETO_MB) -> None:
        self.pasta = Path(pasta) if pasta is not None else PASTA_PADRAO
        self.teto = int(teto_mb * 1024 * 1024)
        self._trava = threading.Lock()
        self._ocupado: int | None = None

    def _caminho(self, chave: ChaveDaLeitura) -> Path:
        nome = chave.nome
        return self.pasta / nome[:2] / f"{nome}.json"

    def _entradas(self) -> list[tuple[int, int, Path]]:
        """`(quando foi usada, tamanho, caminho)` de cada entrada. Quem some no meio da varredura não conta."""
        saida: list[tuple[int, int, Path]] = []
        for caminho in self.pasta.glob("??/*.json"):
            try:
                dados = caminho.stat()
            except OSError:
                continue
            saida.append((dados.st_mtime_ns, dados.st_size, caminho))
        return saida

    def ler(self, chave: ChaveDaLeitura) -> list[tesseract.LinhaDoTesseract] | None:
        """As linhas guardadas, ou `None`. **Entrada ilegível é falta, e sai da pasta**: o cache nunca derruba a leitura."""
        caminho = self._caminho(chave)
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            if dados["versao"] != VERSAO_DA_ENTRADA or dados["chave"] != asdict(chave):
                raise ValueError("entrada de outra chave")
            linhas = [_linha_de(item) for item in dados["linhas"]]
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as erro:
            logger.debug("Entrada do cache de leitura descartada (%s): %s", caminho.name, erro)
            self._apagar(caminho)
            return None
        try:
            os.utime(caminho)  # é o `mtime` que diz quem foi usada há mais tempo
        except OSError as erro:
            logger.debug("Sem marcar o uso de %s: %s", caminho.name, erro)
        return linhas

    def gravar(self, chave: ChaveDaLeitura, linhas: Sequence[tesseract.LinhaDoTesseract]) -> str:
        """Guarda o lote, e devolve a frase do aviso se não deu. **Nunca levanta**: a leitura já está feita."""
        entrada = {
            "versao": VERSAO_DA_ENTRADA,
            "chave": asdict(chave),
            "linhas": [{"texto": linha.texto, "confiancas": list(linha.confiancas)} for linha in linhas],
        }
        corpo = json.dumps(entrada, ensure_ascii=False)
        try:
            atomic_write_text(self._caminho(chave), corpo)
        except OSError as erro:
            logger.warning("O cache de leitura não gravou: %s", erro)
            causa = "o disco está cheio" if erro.errno == errno.ENOSPC else str(erro)
            return f"O cache de leitura não gravou esta folha: {causa}. A leitura não se perdeu."
        self._somar(len(corpo.encode("utf-8")))
        return ""

    def _somar(self, tamanho: int) -> None:
        with self._trava:
            if self._ocupado is None:
                self._ocupado = sum(n for _, n, _ in self._entradas())
            else:
                self._ocupado += tamanho
            if self._ocupado <= self.teto:
                return
            self._despejar()

    def _despejar(self) -> None:
        """Do uso mais antigo para o mais recente, até a folga. Quem mede de novo é a varredura: a conta anda sozinha entre programas."""
        entradas = sorted(self._entradas(), key=lambda e: e[0])
        ocupado = sum(n for _, n, _ in entradas)
        alvo = int(self.teto * FRACAO_DEPOIS_DO_DESPEJO)
        for _usada, tamanho, caminho in entradas:
            if ocupado <= alvo:
                break
            if self._apagar(caminho):
                ocupado -= tamanho
        self._ocupado = ocupado

    @staticmethod
    def _apagar(caminho: Path) -> bool:
        try:
            caminho.unlink()
        except FileNotFoundError:
            return True
        except OSError as erro:
            logger.debug("A entrada %s não saiu: %s", caminho.name, erro)
            return False
        return True

    def tamanho(self) -> int:
        """Bytes das entradas, medidos agora."""
        return sum(n for _, n, _ in self._entradas())

    def limpar(self) -> tuple[int, int]:
        """Apaga as entradas, e só elas. `(quantas saíram, quantos bytes)`. É o que o menu chama."""
        with self._trava:
            quantas = bytes_apagados = 0
            for _usada, tamanho, caminho in self._entradas():
                if self._apagar(caminho):
                    quantas += 1
                    bytes_apagados += tamanho
            for sub in self.pasta.glob("??"):
                try:
                    sub.rmdir()
                except OSError:  # sobrou o que não é nosso, ou alguém gravou agora: fica
                    continue
            self._ocupado = None
        return quantas, bytes_apagados


_padrao: CacheDeLeitura | None = None
_trava_do_padrao = threading.Lock()


def padrao() -> CacheDeLeitura:
    """O cache da janela, um por processo: a conta do que está ocupado vive nele."""
    global _padrao
    with _trava_do_padrao:
        if _padrao is None:
            _padrao = CacheDeLeitura()
        return _padrao


__all__ = [
    "FRACAO_DEPOIS_DO_DESPEJO",
    "PASTA_PADRAO",
    "TETO_MB",
    "CacheDeLeitura",
    "ChaveDaLeitura",
    "chave_de",
    "padrao",
    "sha_do_tessdata",
    "sha_dos_recortes",
]
