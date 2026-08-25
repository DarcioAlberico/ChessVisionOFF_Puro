"""O rascunho automático da aba de texto, e a recuperação depois do fechamento (S-255).

**Uma sessão de correção custa caro e não é reproduzível.** A leitura da folha custa ~1 s com o
glifo e ~40 s com o modo bloco (`docs/metrics/texto_pagina.json`); a correção à mão custa a tarde de
alguém, e **é a única coisa desta aba que não sai de graça de uma releitura** -- é o que a docstring
de `salvar` já dizia antes de existir arquivo nenhum.

Até aqui ela vivia só na memória do widget até alguém apertar Salvar. Fechar a aba, fechar o
programa, uma falha do Tk, um `TclError` numa thread -- e sumia tudo. O programa **já sabe** que isso
é sério: `BusyRegistry` tem `loses_work` justamente para avisar quando fechar custa trabalho.

## Cinco decisões, e cada uma tem um porquê medido

**Grava por inatividade, e não por relógio.** Um relógio fixo grava no meio da digitação e disputa o
disco com quem está trabalhando. O painel reagenda a gravação a cada tecla, e ela acontece alguns
segundos depois da última.

**Grava só quando está sujo.** A aba já rastreia isso (`_sujo`), e reescrever o mesmo arquivo a cada
quatro segundos é desgaste de disco por nada.

**Escreve com `atomic_write_text`**, pelo mesmo motivo de sempre: o que está no disco é trabalho
humano, e um arquivo truncado por cima do anterior seria pior que rascunho nenhum.

**Um rascunho por folha de cada documento, com chave estável.** É o mesmo desenho de
`ui/state._history_key`: o caminho **resolvido** distingue dois livros de mesmo nome em pastas
diferentes, que é o caso que aquele módulo já tratava. O nome do arquivo carrega o nome legível *e*
a impressão do caminho, para a pasta ser legível por quem a abrir.

**Na abertura, oferece -- e não aplica.** Sobrescrever o que a pessoa acabou de ler com um rascunho
de ontem é o contrário do que ela quer. Quem decide é ela, e recusar **não apaga**: o rascunho
continua lá para a próxima abertura.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import PROJECT_ROOT
from . import arquivo
from .rico import DocumentoRico

logger = logging.getLogger(__name__)

__all__ = [
    "ESPERA_SEGUNDOS",
    "PASTA_PADRAO",
    "TETO_POR_DOCUMENTO",
    "Rascunho",
    "achar",
    "caminho_de",
    "chave_de",
    "descartar",
    "gravar",
    "podar",
]

PASTA_PADRAO = PROJECT_ROOT / "data" / "rascunhos"
"""Onde os rascunhos moram. Em `data/`, como todo artefato de trabalho deste projeto."""

ESPERA_SEGUNDOS = 4.0
"""Quanto tempo de **inatividade** antes de gravar.

Quatro segundos é mais longo que a pausa entre duas palavras e mais curto que a pausa entre dois
parágrafos: quem está digitando não é interrompido, e quem parou para pensar já tem o trabalho no
disco. Não é relógio -- ver o cabeçalho."""

TETO_POR_DOCUMENTO = 8
"""Quantos rascunhos de um mesmo livro a pasta guarda. O mais antigo sai primeiro.

Oito é o que cabe numa sessão de trabalho sobre um livro sem a pasta virar depósito: quem corrige
folha a folha volta às anteriores, e quem passou de oito folhas atrás já salvou as primeiras."""

_SUFIXO_DA_CHAVE = 10
"""Quantos caracteres da impressão do caminho entram no nome do arquivo.

Dez hexadecimais são 40 bits: numa pasta de dezenas de rascunhos, a chance de dois caminhos
diferentes colidirem é desprezível, e o nome continua legível."""

_LIMPEZA = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class Rascunho:
    """Um rascunho no disco, e o que se sabe dele sem o abrir."""

    caminho: Path
    quando: datetime
    folha: int

    @property
    def data_legivel(self) -> str:
        """Como a pergunta de recuperação escreve a data. Ver o critério de aceite do item."""
        return self.quando.strftime("%d/%m/%Y %H:%M")


def chave_de(documento: str | Path, folha: int) -> str:
    """A chave estável daquele documento e daquela folha.

    **Resolvida**, como `ui/state._history_key`: dois livros de mesmo nome em pastas diferentes têm
    rascunhos diferentes, e é exatamente o caso que aquele módulo já tratava. Caminho de rede fora
    do ar não levanta -- o não resolvido ainda serve de chave.
    """
    bruto = str(documento or "sem-documento")
    try:
        bruto = str(Path(bruto).resolve())
    except OSError:  # pragma: no cover - caminho de rede fora do ar
        pass
    impressao = hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:_SUFIXO_DA_CHAVE]
    nome = _LIMPEZA.sub("_", Path(bruto).stem)[:40] or "texto"
    return f"{nome}_f{int(folha) + 1}_{impressao}"


def caminho_de(documento: str | Path, folha: int, *, pasta: Path | None = None) -> Path:
    """Onde o rascunho daquela folha mora."""
    return (Path(pasta) if pasta is not None else PASTA_PADRAO) / f"{chave_de(documento, folha)}{arquivo.EXTENSAO}"


def _origem_de(doc: DocumentoRico) -> tuple[str, int] | None:
    pagina = doc.origem
    if pagina is None:
        return None
    return (pagina.documento or "sem-documento", pagina.pagina)


def gravar(doc: DocumentoRico, *, pasta: Path | None = None) -> Path | None:
    """Grava o rascunho da folha deste documento. `None` quando não há folha a que atá-lo.

    Documento sem página de origem não tem chave estável: gravá-lo num nome inventado criaria um
    rascunho que ninguém encontra de volta, que é lixo com aparência de proteção.
    """
    origem = _origem_de(doc)
    if origem is None:
        return None
    destino = caminho_de(origem[0], origem[1], pasta=pasta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    arquivo.gravar(destino, doc)
    podar(origem[0], pasta=pasta)
    return destino


def achar(documento: str | Path, folha: int, *, pasta: Path | None = None) -> Rascunho | None:
    """O rascunho daquela folha, se houver. **Não o abre**: quem decide é quem for oferecer."""
    destino = caminho_de(documento, folha, pasta=pasta)
    if not destino.exists():
        return None
    try:
        quando = datetime.fromtimestamp(destino.stat().st_mtime)
    except OSError:  # pragma: no cover - arquivo sumiu entre o `exists` e o `stat`
        return None
    return Rascunho(caminho=destino, quando=quando, folha=int(folha))


def carregar(rascunho: Rascunho) -> DocumentoRico:
    """O documento daquele rascunho. Levanta `arquivo.ArquivoInvalido` como qualquer `.cvtxt`."""
    return arquivo.carregar(rascunho.caminho)


def descartar(documento: str | Path, folha: int, *, pasta: Path | None = None) -> bool:
    """Apaga o rascunho daquela folha. Devolve se havia um.

    Chamado quando o trabalho **chegou a um lugar melhor**: ou a pessoa salvou o `.cvtxt`, ou ela
    recuperou o rascunho (e o que vale passou a ser o que está na tela). Recusar a oferta **não**
    apaga -- é critério de aceite.
    """
    destino = caminho_de(documento, folha, pasta=pasta)
    if not destino.exists():
        return False
    try:
        destino.unlink()
    except OSError as erro:  # pragma: no cover - arquivo em uso
        logger.debug("Rascunho não pôde ser apagado (%s): %s", destino, erro)
        return False
    return True


def podar(documento: str | Path, *, pasta: Path | None = None, teto: int = TETO_POR_DOCUMENTO) -> list[Path]:
    """Deixa no máximo `teto` rascunhos daquele livro, **e o mais antigo sai primeiro**.

    A poda é por documento e não pela pasta inteira: quem trabalha em dois livros na mesma semana
    não pode perder o rascunho de um porque abriu muitas folhas do outro.
    """
    raiz = Path(pasta) if pasta is not None else PASTA_PADRAO
    if not raiz.exists():
        return []
    prefixo = chave_de(documento, 0).rsplit("_f", 1)[0]
    impressao = chave_de(documento, 0).rsplit("_", 1)[-1]
    do_livro = [
        caminho
        for caminho in raiz.glob(f"*{arquivo.EXTENSAO}")
        if caminho.name.startswith(prefixo) and impressao in caminho.name
    ]
    if len(do_livro) <= teto:
        return []
    por_idade = sorted(do_livro, key=lambda c: c.stat().st_mtime)
    apagados: list[Path] = []
    for caminho in por_idade[: len(do_livro) - teto]:
        try:
            caminho.unlink()
            apagados.append(caminho)
        except OSError as erro:  # pragma: no cover - arquivo em uso
            logger.debug("Rascunho antigo não pôde ser apagado (%s): %s", caminho, erro)
    return apagados


def frase_de_recuperacao(rascunho: Rascunho) -> str:
    """A pergunta que a aba faz. **Diz a data**, porque é ela que decide a resposta.

    "Há um rascunho" não é pergunta respondível: um rascunho de dez minutos atrás é o trabalho que
    a pessoa acabou de perder, e um de três semanas é lixo que ela já esqueceu.
    """
    return (
        f"Há um rascunho não salvo desta folha, de {rascunho.data_legivel}.\n\n"
        "Recuperar o texto do rascunho? Recusar não o apaga."
    )
