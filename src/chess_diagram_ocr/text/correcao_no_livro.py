"""Corrigir uma vez, corrigir no livro inteiro: as palavras do livro e a troca em todas as folhas do caderno (S-766).

**O que a S-721 mediu e recusou.** O `--user-words` do Tesseract, por onde o roadmap pretendia entrar, muda 1 de 316 linhas, e para pior: o LSTM não
o ouve. O que sobra são duas portas, as duas fora do motor.

**1 · As palavras do livro entram nos árbitros.** O nome que o dono escreveu vai ao `lexico.txt` do caderno (S-657), e `ler_pagina(palavras_do_livro=)` o
faz existir para a fusão e para a marca, nas folhas lidas depois. **Não conserta o que os dois leitores erram juntos:** ele decide entre duas leituras, e
tira a marca do nome certo. O que ele faz por número está em `docs/metrics/texto_confianca_2026-11-06.json`.

**2 · A troca em massa, com prévia obrigatória.** `aplicar` só aceita uma `Previa`, e não os dois textos: a função não tem como trocar o que ninguém viu. É a regra da
S-213 (`semelhanca.SemPrevisualizacao`), e a S-76 é o registro do que custa um botão destrutivo que não parece um. Cada folha vai ao caderno como corrigida, com a versão de
antes em `.anterior.cvtxt`: **«Voltar à versão anterior desta folha» desfaz uma folha, e as outras ficam.** Só folha que já está no caderno muda: a que ninguém leu não tem o que trocar.

A folha que mudou entre a prévia e o aplicar fica como está, e é contada: o contexto que a pessoa aprovou não é mais o que está lá. A folha `conferida` vem desmarcada: alguém já disse que ela está certa.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from . import busca as _busca
from . import caderno as _caderno
from . import correcao as _correcao
from . import dado_corrigido as _dado_corrigido
from . import fusao as _fusao
from .rico import DocumentoRico

logger = logging.getLogger(__name__)

_BORDAS = ".,;:!?()[]{}'\"’‘“”«»…"
_PALAVRA = re.compile(r"^[^\W\d_]{2,}(?:['’-][^\W\d_]+)*$")


class SemPrevia(TypeError):
    """Pediram uma troca em massa sem a prévia. Levanta em vez de trocar: ver o cabeçalho."""


def palavra_do_livro(texto: str) -> str:
    """A palavra que pode ir ao léxico do livro, ou vazio. Lance, número e sinal solto não são nome de ninguém."""
    nu = texto.strip(_BORDAS)
    return nu if _PALAVRA.match(nu) and _fusao.classe_do_token(nu) == _fusao.PROSA else ""


def palavras_novas(doc: DocumentoRico, *, existe: Callable[[str], bool]) -> tuple[str, ...]:
    """O que a mão escreveu nesta folha e o léxico não conhece: é o que o dono ensinou. Só o par palavra a palavra da S-762."""
    achadas: dict[str, None] = {}
    for par in _dado_corrigido.pares_tocados(doc):
        nova = palavra_do_livro(par.depois)
        if nova and not existe(nova):
            achadas[nova] = None
    return tuple(achadas)


def ensinar(cad: _caderno.Caderno, doc: DocumentoRico, *, existe: Callable[[str], bool]) -> tuple[str, ...]:
    """Leva ao caderno as palavras novas da folha, e devolve as que entraram agora."""
    return tuple(p for p in palavras_novas(doc, existe=existe) if cad.acrescentar_ao_lexico(p))


@dataclass(frozen=True)
class NaFolha:
    """Uma ocorrência na lista da prévia."""

    pagina: int
    ocorrencia: _busca.Ocorrencia
    conferida: bool = False

    @property
    def rotulo(self) -> str:
        return f"Folha {self.pagina + 1}: {self.ocorrencia.contexto}"


@dataclass(frozen=True)
class Previa:
    """O que a pessoa vai aprovar: a troca, cada ocorrência, e o resumo de cada folha no momento em que foi vista."""

    antes: str
    depois: str
    ocorrencias: tuple[NaFolha, ...] = ()
    resumos: tuple[tuple[int, str], ...] = ()

    @property
    def folhas(self) -> tuple[int, ...]:
        return tuple(pagina for pagina, _ in self.resumos)

    def desmarcadas_por_padrao(self) -> frozenset[int]:
        """Os índices que a lista abre desmarcados: os de folha conferida."""
        return frozenset(i for i, o in enumerate(self.ocorrencias) if o.conferida)


@dataclass(frozen=True)
class Aplicado:
    """O que `aplicar` fez, para a frase do rodapé."""

    trocas: int = 0
    folhas: tuple[int, ...] = ()
    folhas_que_mudaram: tuple[int, ...] = ()
    """As que mudaram desde a prévia, e por isso ficaram como estavam."""
    folhas_que_nao_gravaram: tuple[int, ...] = ()
    palavra_nova: bool = False


def _resumo(doc: DocumentoRico) -> str:
    return hashlib.sha256(doc.para_texto().encode("utf-8")).hexdigest()


def previa(cad: _caderno.Caderno, antes: str, depois: str) -> Previa:
    """Procura a palavra inteira, com a caixa dela, em todas as folhas do caderno. Nada é gravado."""
    if not antes.strip() or antes == depois:
        return Previa(antes, depois)
    ocorrencias: list[NaFolha] = []
    resumos: list[tuple[int, str]] = []
    for estado in cad.folhas():
        doc = cad.folha(estado.pagina)
        if doc is None:
            continue
        achadas = _busca.achar(doc, antes, diferenciar_caixa=True, palavra_inteira=True)
        if achadas:
            resumos.append((estado.pagina, _resumo(doc)))
            ocorrencias.extend(NaFolha(estado.pagina, o, estado.estado == _caderno.CONFERIDA) for o in achadas)
    return Previa(antes, depois, tuple(ocorrencias), tuple(resumos))


def aplicar(cad: _caderno.Caderno, vista: Previa, *, fora: Iterable[int] = ()) -> Aplicado:
    """Troca as ocorrências da prévia, menos os índices de `fora`, folha a folha. **Só aceita a prévia**: ver o cabeçalho."""
    if not isinstance(vista, Previa):
        raise SemPrevia("A troca em todas as folhas só parte de uma prévia: chame `previa` e mostre a lista.")
    excluidas = set(fora)
    por_folha: dict[int, list[_busca.Ocorrencia]] = {}
    for i, item in enumerate(vista.ocorrencias):
        if i not in excluidas:
            por_folha.setdefault(item.pagina, []).append(item.ocorrencia)
    resumos = dict(vista.resumos)
    trocas = 0
    feitas: list[int] = []
    mudaram: list[int] = []
    sem_gravar: list[int] = []
    for pagina, ocorrencias in sorted(por_folha.items()):
        doc = cad.folha(pagina)
        if doc is None or _resumo(doc) != resumos.get(pagina):
            mudaram.append(pagina)
            continue
        novo = _busca.substituir(doc, ocorrencias, vista.depois)
        cad.visitar(pagina)
        try:
            feito = cad.gravar(_correcao.com_procedencia_humana(novo), estado=_caderno.EDITADA, correcoes=len(_correcao.correcoes(novo)))
        except OSError as erro:
            logger.warning("A folha %d não gravou na troca em massa: %s", pagina + 1, erro)
            feito = ""
        if feito == _caderno.GRAVADA:
            trocas += len(ocorrencias)
            feitas.append(pagina)
        else:
            sem_gravar.append(pagina)
    nova = palavra_do_livro(vista.depois)
    try:
        entrou = bool(feitas and nova) and cad.acrescentar_ao_lexico(nova)
    except OSError as erro:
        logger.warning("O léxico do livro não gravou: %s", erro)
        entrou = False
    return Aplicado(trocas, tuple(feitas), tuple(mudaram), tuple(sem_gravar), entrou)


def frase_da_previa(vista: Previa) -> str:
    if not vista.ocorrencias:
        return f"«{vista.antes}» não aparece em nenhuma folha do caderno."
    return f"«{vista.antes}» -> «{vista.depois}»: {len(vista.ocorrencias)} ocorrência(s) em {len(vista.folhas)} folha(s). Confira a lista: só as marcadas mudam."


def frase_do_resultado(feito: Aplicado) -> str:
    partes = [f"{feito.trocas} troca(s) em {len(feito.folhas)} folha(s). Cada folha volta sozinha por «Voltar à versão anterior desta folha»"]
    if feito.folhas_que_mudaram:
        partes.append(f"{len(feito.folhas_que_mudaram)} folha(s) mudaram depois da prévia e ficaram como estavam")
    if feito.folhas_que_nao_gravaram:
        partes.append(f"{len(feito.folhas_que_nao_gravaram)} folha(s) não gravaram")
    return ". ".join(partes) + "."


def ocorrencias_por_folha(vista: Previa) -> dict[int, Sequence[NaFolha]]:
    saida: dict[int, list[NaFolha]] = {}
    for item in vista.ocorrencias:
        saida.setdefault(item.pagina, []).append(item)
    return dict(saida)


__all__ = [
    "Aplicado",
    "NaFolha",
    "Previa",
    "SemPrevia",
    "aplicar",
    "ensinar",
    "frase_da_previa",
    "frase_do_resultado",
    "ocorrencias_por_folha",
    "palavra_do_livro",
    "palavras_novas",
    "previa",
]
