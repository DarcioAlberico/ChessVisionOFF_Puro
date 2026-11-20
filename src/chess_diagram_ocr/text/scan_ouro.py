"""O scan-ouro: que folhas escaneadas recebem verdade humana, e em que split (S-703).

**É o único jeito de dizer o erro absoluto em scan.** A camada de terceiro (a prata, S-705) só ordena; sem este conjunto, M3 e M4 não
existem. E o conjunto vale ~15 horas de alguém, então ele é escolhido **antes** de a primeira letra ser digitada, e congelado.

**Só identidades**, como o ouro e a prata (`caderno.identidade_de`): o repositório é público. A transcrição é texto de livro comercial, e
mora fora dele (`text/transcricao_scan.py`); aqui ficam o livro, a folha e o sha da folha.

**Dois eixos, e os dois têm nome próprio** porque "estrato" já quer dizer duas coisas: `producao` é o da prata (`clearscan`, `ate_150`,
`de_300`), por livro, e é por ela que M3 e M4 se publicam; `conteudo` é o do ouro (`prosa`, `misto`), por folha.

**Nenhum leitor roda na escolha.** A produção sai das fontes e da resolução das imagens. O conteúdo sai do texto da **camada de terceiro**
que o PDF já traz, pelo mesmo `ouro.estrato_do_texto` do sorteio da S-702: nem o glifo, nem o Tesseract, nem a fusão olham a folha. A camada
é o único jeito de saber, porque a geometria não separa prosa de misto (medido nas 27 folhas do ouro-dev, ver `SPEC_TEXTO_PRECISO.md`). O
livro sem camada nenhuma entra com `conteudo = a_conferir`, que a verdade decide depois, e por isso a conta da "metade no misto" não o
conta: ela vale no pior caso.

**O sorteio.** Livros por `sha256(semente:identidade)`, folhas por `sha256(identidade + folha)`, com a folha em base 1: as funções do ouro,
reaproveitadas. **Livro já visto não vai ao teste**: `visto` marca o que as regras da fusão e do árbitro olharam. O gerador está em
`docs/metrics/texto_scan_ouro_2026-11-06/sortear.py`.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from chess_diagram_ocr.atomic_io import atomic_write_bytes
from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.text.ouro import LINGUAS, MISTO, PROSA
from chess_diagram_ocr.text.prata import ATE_150, CLEARSCAN, DE_300, ESTRATOS

CAMINHO = Path("assets") / "texto_prosa" / "scan_ouro.json"
"""Relativo à raiz do repositório, e fora de `data/`, pelo mesmo motivo do ouro: o `conftest` desvia o `DATA_DIR` da suíte."""

VERSAO = 1
DEV = "dev"
TESTE = "teste"
SPLITS = (DEV, TESTE)
A_CONFERIR = "a_conferir"
CONTEUDOS = (PROSA, MISTO, A_CONFERIR)

FOLHAS_MINIMAS = 30
LIVROS_MINIMOS = 8
LINGUAS_MINIMAS = 5
FRACAO_ATE_150 = 1 / 3
"""Um quarto do acervo é scan de até 150 dpi, e é onde o reconhecimento mais sofre: pelo menos um terço das folhas."""
FRACAO_NO_MISTO = 1 / 2
FRACAO_DUPLA = 0.20
DUPLAS_MINIMAS = 6

_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA = re.compile(r"^[0-9a-f]{16}$")


@dataclass(frozen=True)
class LivroDoScanOuro:
    identidade: str
    split: str
    lingua: str
    producao: str
    dpi: int = 0
    """A resolução mediana das imagens de página; 0 no ClearScan sem imagem de página."""
    grupo: str = ""
    """A série ou o autor: dois livros do mesmo grupo não caem em splits diferentes."""
    visto: bool = False
    """As regras da fusão e do árbitro foram escritas olhando este livro. Só pode estar no dev."""
    seculo_xix: bool = False


@dataclass(frozen=True)
class FolhaDoScanOuro:
    identidade: str
    folha: int
    """Base 1, como nos relatórios."""
    lingua: str
    producao: str
    conteudo: str
    split: str
    dupla: bool = False
    """Esta folha é digitada duas vezes, às cegas (≥ 20% das folhas, ≥ 6)."""
    sha_folha: str = ""
    """O sha dos bytes da folha no PDF (`sha_da_folha`). Outra cópia do livro com outra folha não é a mesma verdade."""


@dataclass(frozen=True)
class ScanOuro:
    versao: int
    congelado_em: str
    primeira_leitura_do_teste: str | None
    livros: tuple[LivroDoScanOuro, ...]
    folhas: tuple[FolhaDoScanOuro, ...]
    sorteio: dict[str, Any] = field(default_factory=dict)

    def do_split(self, split: str) -> tuple[FolhaDoScanOuro, ...]:
        return tuple(f for f in self.folhas if f.split == split)


def caminho_padrao() -> Path:
    return BUNDLE_ROOT / CAMINHO


def de_json(dados: dict[str, Any]) -> ScanOuro:
    return ScanOuro(
        versao=int(dados.get("versao", 0)),
        congelado_em=str(dados.get("congelado_em", "")),
        primeira_leitura_do_teste=dados.get("primeira_leitura_do_teste"),
        livros=tuple(LivroDoScanOuro(**livro) for livro in dados.get("livros", ())),
        folhas=tuple(FolhaDoScanOuro(**folha) for folha in dados.get("folhas", ())),
        sorteio=dict(dados.get("sorteio", {})),
    )


def carregar(caminho: str | Path | None = None) -> ScanOuro:
    with open(caminho or caminho_padrao(), encoding="utf-8") as arquivo:
        return de_json(json.load(arquivo))


def gravar(manifesto: ScanOuro, caminho: str | Path) -> None:
    """Em LF e UTF-8, um item por linha: o diff de um livro trocado é uma linha."""
    cabeca = {
        "versao": manifesto.versao,
        "congelado_em": manifesto.congelado_em,
        "primeira_leitura_do_teste": manifesto.primeira_leitura_do_teste,
        "sorteio": manifesto.sorteio,
    }
    linhas = ["{"]
    for chave, valor in cabeca.items():
        linhas.append(f"  {json.dumps(chave)}: {json.dumps(valor, ensure_ascii=False, sort_keys=True)},")
    for chave, itens, fim in (("livros", manifesto.livros, ","), ("folhas", manifesto.folhas, "")):
        corpo = ",\n".join(f"    {json.dumps(vars(item), ensure_ascii=False)}" for item in itens)
        linhas.append(f'  "{chave}": [\n{corpo}\n  ]{fim}')
    atomic_write_bytes(Path(caminho), ("\n".join(linhas) + "\n}\n").encode("utf-8"))


def registrar_leitura_do_teste(manifesto: ScanOuro, hoje: str) -> ScanOuro:
    """A primeira vez que um motor lê o split teste, com a data de quem abriu. Não se sobrescreve."""
    if manifesto.primeira_leitura_do_teste:
        return manifesto
    return replace(manifesto, primeira_leitura_do_teste=hoje)


def sha_da_folha(documento: Any, indice: int) -> str:
    """O sha dos bytes da folha dentro do PDF: o conteúdo da página e as imagens dela, sem renderizar nada."""
    pagina = documento[indice]
    resumo = hashlib.sha256(pagina.read_contents())
    for xref in sorted({imagem[0] for imagem in pagina.get_images(full=True)}):
        resumo.update(documento.xref_stream_raw(xref) or b"")
    return resumo.hexdigest()[:16]


def problemas(manifesto: ScanOuro) -> list[str]:
    """O que faz o manifesto não valer: é a saída do item, travada por teste."""
    erros: list[str] = []
    if manifesto.versao != VERSAO:
        erros.append(f"versão {manifesto.versao}, esperada {VERSAO}")
    if not _DATA.match(manifesto.congelado_em):
        erros.append(f"data de congelamento inválida: {manifesto.congelado_em!r}")
    if manifesto.primeira_leitura_do_teste and manifesto.primeira_leitura_do_teste < manifesto.congelado_em:
        erros.append(f"o teste foi lido em {manifesto.primeira_leitura_do_teste}, antes de congelar em {manifesto.congelado_em}")
    livros: dict[str, LivroDoScanOuro] = {}
    for livro in manifesto.livros:
        if not livro.identidade:
            erros.append("livro sem identidade")
        if livro.identidade in livros:
            erros.append(f"livro {livro.identidade} repetido: um livro está em um split só")
        if livro.split not in SPLITS:
            erros.append(f"livro {livro.identidade} no split {livro.split!r}")
        if livro.lingua not in LINGUAS:
            erros.append(f"livro {livro.identidade} em {livro.lingua!r}")
        if livro.producao not in ESTRATOS:
            erros.append(f"livro {livro.identidade} com produção {livro.producao!r}")
        if livro.visto and livro.split == TESTE:
            erros.append(f"o livro {livro.identidade} já foi visto, e está no teste")
        livros[livro.identidade] = livro
    grupos: dict[str, set[str]] = {}
    for livro in manifesto.livros:
        if livro.grupo:
            grupos.setdefault(livro.grupo, set()).add(livro.split)
    erros.extend(f"o grupo {grupo} está nos dois splits" for grupo, splits in sorted(grupos.items()) if len(splits) > 1)
    vistas: set[tuple[str, int]] = set()
    for f in manifesto.folhas:
        dono = livros.get(f.identidade)
        if dono is None:
            erros.append(f"folha {f.folha} de um livro que o manifesto não lista: {f.identidade!r}")
            continue
        if f.folha < 1:
            erros.append(f"folha {f.folha} de {f.identidade}: a folha é em base 1")
        if (f.identidade, f.folha) in vistas:
            erros.append(f"folha {f.folha} de {f.identidade} repetida")
        vistas.add((f.identidade, f.folha))
        if (f.split, f.lingua, f.producao) != (dono.split, dono.lingua, dono.producao):
            erros.append(f"folha {f.folha} de {f.identidade} difere do livro em split, língua ou produção")
        if f.conteudo not in CONTEUDOS:
            erros.append(f"folha {f.folha} de {f.identidade} com conteúdo {f.conteudo!r}")
        if not _SHA.match(f.sha_folha):
            erros.append(f"folha {f.folha} de {f.identidade} sem o sha da folha")
    erros.extend(f"livro {i} sem folha" for i in sorted(set(livros) - {f.identidade for f in manifesto.folhas}))
    n = len(manifesto.folhas)
    if n < FOLHAS_MINIMAS:
        erros.append(f"{n} folhas, e o mínimo é {FOLHAS_MINIMAS}")
    if len(livros) < LIVROS_MINIMOS:
        erros.append(f"{len(livros)} livros, e o mínimo é {LIVROS_MINIMOS}")
    linguas = {livro.lingua for livro in manifesto.livros}
    if len(linguas) < LINGUAS_MINIMAS:
        erros.append(f"{len(linguas)} línguas, e o mínimo é {LINGUAS_MINIMAS}")
    for split in SPLITS:
        producoes = {livro.producao for livro in manifesto.livros if livro.split == split}
        if livros and producoes != set(ESTRATOS):
            erros.append(f"faltam produções no {split}: {sorted(set(ESTRATOS) - producoes)}")
    if livros and abs(sum(livro.split == DEV for livro in manifesto.livros) - sum(livro.split == TESTE for livro in manifesto.livros)) > 1:
        erros.append("os splits não têm metade dos livros cada um")
    if livros and not any(livro.seculo_xix for livro in manifesto.livros):
        erros.append("nenhum livro de tipografia do século XIX")
    if n and sum(f.producao == ATE_150 for f in manifesto.folhas) < FRACAO_ATE_150 * n:
        erros.append("menos de um terço das folhas em scan de até 150 dpi")
    # `a_conferir` não conta: a conta vale no pior caso.
    if n and sum(f.conteudo == MISTO for f in manifesto.folhas) < FRACAO_NO_MISTO * n:
        erros.append("menos de metade das folhas no misto")
    duplas = [f for f in manifesto.folhas if f.dupla]
    if n and (len(duplas) < DUPLAS_MINIMAS or len(duplas) < FRACAO_DUPLA * n):
        erros.append(f"{len(duplas)} folhas com dupla digitação: o mínimo é {DUPLAS_MINIMAS} e {FRACAO_DUPLA:.0%}")
    return erros


__all__ = [
    "A_CONFERIR",
    "ATE_150",
    "CLEARSCAN",
    "CONTEUDOS",
    "DE_300",
    "DEV",
    "SPLITS",
    "TESTE",
    "FolhaDoScanOuro",
    "LivroDoScanOuro",
    "ScanOuro",
    "caminho_padrao",
    "carregar",
    "de_json",
    "gravar",
    "problemas",
    "registrar_leitura_do_teste",
    "sha_da_folha",
]
