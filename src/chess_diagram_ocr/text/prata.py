"""A prata da régua da prosa: scans reais com camada de terceiro, que **só ordenam** motores (S-705).

A camada aqui é o OCR de outro programa, e não a tinta: medir contra ela diz quem lê parecido com o ABBYY ou o
Paper Capture, e não quanto se erra. Serve para dizer que um motor vai à frente de outro, nunca o erro absoluto, que é
da S-703. Por isso o relatório imprime **"ordenação"** ao lado de todo número prata, e nunca a soma ao ouro.

**Só identidades**, como o ouro (`caderno.identidade_de`): o repositório é público. E estratificada como o scan-ouro
da S-703, por produção e resolução, porque cada estrato erra de um jeito: `clearscan` (o Acrobat vetoriza o glifo e o Unicode
vem do OCR dele, fontes `Fd<n>`), `ate_150` (scan de até 150 dpi nativos, um quarto do acervo) e `de_300` (scan de 300 dpi
ou mais). O limite do estrato é de medida real: 149 e 299 dpi aparecem no acervo por causa do arredondamento da página.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chess_diagram_ocr.atomic_io import atomic_write_bytes
from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.text.ouro import LINGUAS, RESERVA, Manifesto

CAMINHO = Path("assets") / "texto_prosa" / "prata.json"
VERSAO = 1
USO = "ordenação"
"""A palavra que acompanha todo número desta fatia. É dela que o teste do relatório cobra."""

CLEARSCAN = "clearscan"
ATE_150 = "ate_150"
DE_300 = "de_300"
ESTRATOS = (CLEARSCAN, ATE_150, DE_300)

_FONTE_DO_CLEARSCAN = re.compile(r"^(?:[A-Z]{6}\+)?Fd\d+", re.I)
LIMITE_DO_SCAN_BAIXO = 155
LIMITE_DO_SCAN_ALTO = 295


@dataclass(frozen=True)
class LivroDaPrata:
    identidade: str
    lingua: str
    estrato: str
    dpi: int = 0
    """A resolução mediana das imagens de página; 0 no ClearScan sem imagem de página."""


@dataclass(frozen=True)
class FolhaDaPrata:
    identidade: str
    folha: int
    """Base 1, como nos relatórios."""
    lingua: str
    estrato: str


@dataclass(frozen=True)
class Prata:
    versao: int
    livros: tuple[LivroDaPrata, ...]
    folhas: tuple[FolhaDaPrata, ...]
    origem: str = ""


def estrato_de_producao(fontes: Iterable[str], dpi: int) -> str | None:
    """O estrato pela produção do PDF. `None` é o scan de resolução intermediária, fora dos três."""
    nomes = list(fontes)
    if nomes and sum(bool(_FONTE_DO_CLEARSCAN.match(f)) for f in nomes) * 2 >= len(nomes):
        return CLEARSCAN
    if 0 < dpi <= LIMITE_DO_SCAN_BAIXO:
        return ATE_150
    if dpi >= LIMITE_DO_SCAN_ALTO:
        return DE_300
    return None


def caminho_padrao() -> Path:
    return BUNDLE_ROOT / CAMINHO


def de_json(dados: dict[str, Any]) -> Prata:
    return Prata(
        versao=int(dados.get("versao", 0)),
        origem=str(dados.get("origem", "")),
        livros=tuple(LivroDaPrata(**livro) for livro in dados.get("livros", ())),
        folhas=tuple(FolhaDaPrata(**folha) for folha in dados.get("folhas", ())),
    )


def carregar(caminho: str | Path | None = None) -> Prata:
    with open(caminho or caminho_padrao(), encoding="utf-8") as arquivo:
        return de_json(json.load(arquivo))


def gravar(prata: Prata, caminho: str | Path) -> None:
    """Em LF e UTF-8, uma folha por linha, como o manifesto do ouro."""
    linhas = ["{", f'  "versao": {prata.versao},', f'  "origem": {json.dumps(prata.origem, ensure_ascii=False)},']
    for chave, itens, fim in (("livros", prata.livros, ","), ("folhas", prata.folhas, "")):
        corpo = ",\n".join(f"    {json.dumps(vars(item), ensure_ascii=False)}" for item in itens)
        linhas.append(f'  "{chave}": [\n{corpo}\n  ]{fim}')
    atomic_write_bytes(Path(caminho), ("\n".join(linhas) + "\n}\n").encode("utf-8"))


def problemas(prata: Prata, ouro: Manifesto | None = None) -> list[str]:
    """O que faz o manifesto não valer. Com `ouro`, também o livro nos dois: a camada dele é a tinta ou não é."""
    erros: list[str] = []
    if prata.versao != VERSAO:
        erros.append(f"versão {prata.versao}, esperada {VERSAO}")
    estrato_do_livro: dict[str, str] = {}
    lingua_do_livro: dict[str, str] = {}
    for livro in prata.livros:
        if not livro.identidade:
            erros.append("livro sem identidade")
        if livro.identidade in estrato_do_livro:
            erros.append(f"livro {livro.identidade} repetido")
        if livro.estrato not in ESTRATOS:
            erros.append(f"livro {livro.identidade} com estrato {livro.estrato!r}")
        if livro.lingua not in LINGUAS:
            erros.append(f"livro {livro.identidade} com língua {livro.lingua!r}")
        estrato_do_livro[livro.identidade] = livro.estrato
        lingua_do_livro[livro.identidade] = livro.lingua
    vistas: set[tuple[str, int]] = set()
    for folha in prata.folhas:
        if folha.identidade not in estrato_do_livro:
            erros.append(f"folha {folha.folha} de um livro que a prata não lista: {folha.identidade!r}")
            continue
        if folha.estrato != estrato_do_livro[folha.identidade]:
            erros.append(f"folha {folha.folha} de {folha.identidade} no estrato {folha.estrato}, e o livro não")
        if folha.lingua != lingua_do_livro[folha.identidade]:
            erros.append(f"folha {folha.folha} de {folha.identidade} em {folha.lingua!r}, e o livro não")
        if folha.folha < 1:
            erros.append(f"folha {folha.folha} de {folha.identidade}: a folha é em base 1")
        if (folha.identidade, folha.folha) in vistas:
            erros.append(f"folha {folha.folha} de {folha.identidade} repetida")
        vistas.add((folha.identidade, folha.folha))
    if prata.livros and {livro.estrato for livro in prata.livros} != set(ESTRATOS):
        erros.append(f"faltam estratos: {sorted(set(ESTRATOS) - {livro.estrato for livro in prata.livros})}")
    sem_folha = sorted(set(estrato_do_livro) - {f.identidade for f in prata.folhas})
    if sem_folha:
        erros.append(f"livros sem folha: {sem_folha}")
    if ouro is not None:
        no_ouro = {livro.identidade for livro in ouro.livros if livro.split != RESERVA}
        for identidade in sorted(no_ouro & set(estrato_do_livro)):
            erros.append(f"o livro {identidade} está na prata e no ouro: a camada dele não pode ser as duas coisas")
    return erros
