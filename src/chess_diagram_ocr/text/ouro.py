"""O ouro da régua da prosa: que livros e que folhas medem, e em que split (S-702).

**O teste só vale se foi escolhido antes de ser lido.** Os sete livros digitais com prosa do acervo
já foram usados para desenhar a régua, a taxonomia e as regras de fusão (dev contaminado), e um
portão medido neles promete só o que foi visto. O ouro-teste são livros que o programa nunca leu,
trazidos pelo dono (a D6 do `docs/ROADMAP_TEXTO_PRECISO.md`), com as folhas sorteadas por uma regra
fixa **antes** de qualquer motor tocá-las, e o manifesto commitado antes da primeira corrida.

**O manifesto guarda a identidade, não o nome.** O repositório é público, e a lista de livros que o
dono tem não precisa estar nele (decisão do dono, 2026-10-30). A identidade é a do caderno
(`caderno.identidade_de`: o resumo do primeiro MiB do arquivo), reaproveitada e não reimplementada;
o PDF é achado pela identidade numa lista de pastas, e renomear o arquivo não o tira do ouro.

**Splits.** `dev` são os livros de 2026-10-30 que passaram na auditoria visual; `teste` são os
sorteados da D6 que deram seis folhas e passaram na auditoria; `reserva` é todo o resto que não ficou
fora do inventário -- os da D6 não sorteados, os sorteados que cederam a vaga e os reprovados, dev
ou não. A reserva é material de desenvolvimento e de treino, menos os marcados `fora_do_treino`: os
da mesma série ou grupo de um livro do teste, e os reprovados. Um livro está em um split só, e cada
folha herda o split do livro.

**O sorteio.** Os livros se ordenam por `sha256(semente + ":" + identidade)`, e as folhas de um
livro por `sha256(identidade + folha)`, com a folha em base 1. A ordem não depende de que outros
livros estão na corrida nem da ordem em que foram listados. As folhas se percorrem nessa ordem, e
entram as primeiras que caem num estrato ainda incompleto e passam na admissão
(`text/admissao.py`). Os estratos são os do dev de 2026-10-30: **prosa** (≥ 700 caracteres de
prosa e ≥ 55% de prosa) e **misto** (≥ 300 e entre 20% e 55%), fora os 8% iniciais e finais do livro.

**O classificador de token entra de fora.** Quem decide o que é prosa é a régua das S-700/S-701,
que ainda não está no pacote; até lá, o sorteio usa o protótipo de
`docs/metrics/texto_prosa_2026-10-30/banco.py`, e o manifesto grava o sha256 dele. O estrato de uma
folha fica congelado no manifesto: trocar o classificador depois não muda o que foi sorteado.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from chess_diagram_ocr.atomic_io import atomic_write_bytes
from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.text.caderno import identidade_de

CAMINHO = Path("assets") / "texto_prosa" / "ouro.json"
"""Relativo à raiz do repositório, e fora de `data/`: o `conftest` desvia o `DATA_DIR` da suíte para
uma pasta vazia, e a guarda do manifesto ficaria vácua."""

VERSAO = 1
DEV = "dev"
TESTE = "teste"
RESERVA = "reserva"
SPLITS = (DEV, TESTE, RESERVA)
PROSA = "prosa"
MISTO = "misto"
ESTRATOS = (PROSA, MISTO)
ORIGENS = ("pdf", "ebook")
LINGUAS = ("eng", "por", "spa", "deu", "nld", "fra", "ron", "rus")
"""As línguas do acervo, nos códigos de três letras do Tesseract (os do relatório de 2026-10-30)."""
DIAGRAMACOES = ("nova", "vista")

PULAR = 0.08
"""A fração do começo e do fim do livro que o sorteio não olha: capa, sumário, índice, bibliografia."""

ESTRATO_PROSA = (700, 0.55, 1.01)
ESTRATO_MISTO = (300, 0.20, 0.55)
"""(mínimo de caracteres de prosa, fração mínima, fração máxima exclusiva) -- os de 2026-10-30."""

TESTE_MINIMO = 8
"""O mínimo de livros no teste (seção 3 do roadmap); a meta é 12."""

LINGUAS_MINIMAS_NO_TESTE = 3
PENDENCIA_DE_LINGUA = "terceira_lingua"
"""O teste congelado com menos línguas que o mínimo, e o livro que falta prometido (decisão do dono,
2026-10-30: o único livro em espanhol da D6 não tinha folha de prosa). O livro que chegar entra como
livro **a mais**, sem mexer nos já sorteados, e a pendência sai do manifesto no mesmo commit."""

_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class LivroDoOuro:
    identidade: str
    split: str
    lingua: str
    origem: str = "pdf"
    """`pdf` (o PDF da editora ou de outra origem) ou `ebook` (ebook convertido em PDF)."""
    diagramacao: str = "nova"
    """`vista` quando o livro tem o produtor e as fontes de um livro dev."""
    grupo: str = ""
    """Série ou diagramação: a identidade do livro que representa o grupo. Vazio, o livro é o grupo."""
    fora_do_treino: bool = False
    reprovado: str = ""
    """Por que o livro saiu do ouro (`auditoria: ...`). Reprovado fica na reserva, fora do treino: a
    camada dele não é a tinta, e nem a régua nem a linha de treino podem usá-la como verdade."""
    entrou_em: str = ""
    """A data em que um livro entrou **a mais** no teste (`acrescentar_ao_teste`); vazio para os
    congelados em `congelado_em`. A guarda de `primeira_leitura_do_teste` cobre os congelados; a
    primeira leitura de um livro acrescentado é registrada à parte pela S-706, e tem de vir depois
    desta data."""


@dataclass(frozen=True)
class FolhaDoOuro:
    identidade: str
    folha: int
    """Base 1, como nos relatórios."""
    lingua: str
    estrato: str
    split: str


@dataclass(frozen=True)
class Manifesto:
    versao: int
    congelado_em: str
    primeira_leitura_do_teste: str | None
    livros: tuple[LivroDoOuro, ...]
    folhas: tuple[FolhaDoOuro, ...]
    sorteio: dict[str, Any] = field(default_factory=dict)
    pendencias: tuple[str, ...] = ()
    """O que o teste ainda não cumpre e foi aceito assim, com nome. Ver `PENDENCIA_DE_LINGUA`."""

    def do_split(self, split: str) -> tuple[FolhaDoOuro, ...]:
        return tuple(f for f in self.folhas if f.split == split)


def caminho_padrao() -> Path:
    """Num checkout é a raiz do repositório; no instalador, a pasta do pacote, para onde o
    `packaging/cvoff.spec` copia `assets/`."""
    return BUNDLE_ROOT / CAMINHO


def de_json(dados: dict[str, Any]) -> Manifesto:
    return Manifesto(
        versao=int(dados.get("versao", 0)),
        congelado_em=str(dados.get("congelado_em", "")),
        primeira_leitura_do_teste=dados.get("primeira_leitura_do_teste"),
        livros=tuple(LivroDoOuro(**livro) for livro in dados.get("livros", ())),
        folhas=tuple(FolhaDoOuro(**folha) for folha in dados.get("folhas", ())),
        sorteio=dict(dados.get("sorteio", {})),
        pendencias=tuple(dados.get("pendencias", ())),
    )


def para_json(manifesto: Manifesto) -> dict[str, Any]:
    return {
        "versao": manifesto.versao,
        "congelado_em": manifesto.congelado_em,
        "primeira_leitura_do_teste": manifesto.primeira_leitura_do_teste,
        "pendencias": list(manifesto.pendencias),
        "sorteio": manifesto.sorteio,
        "livros": [vars(livro) for livro in manifesto.livros],
        "folhas": [vars(folha) for folha in manifesto.folhas],
    }


def carregar(caminho: str | Path | None = None) -> Manifesto:
    with open(caminho or caminho_padrao(), encoding="utf-8") as arquivo:
        return de_json(json.load(arquivo))


def gravar(manifesto: Manifesto, caminho: str | Path) -> None:
    """Grava em LF e UTF-8, uma folha por linha, para o diff de uma troca ser de uma linha."""
    dados = para_json(manifesto)
    linhas = ["{"]
    for chave in ("versao", "congelado_em", "primeira_leitura_do_teste", "pendencias", "sorteio"):
        linhas.append(f"  {json.dumps(chave)}: {json.dumps(dados[chave], ensure_ascii=False)},")
    for chave in ("livros", "folhas"):
        itens = [f"    {json.dumps(item, ensure_ascii=False)}" for item in dados[chave]]
        fim = "," if chave == "livros" else ""
        linhas.append(f'  "{chave}": [\n' + ",\n".join(itens) + f"\n  ]{fim}")
    atomic_write_bytes(Path(caminho), ("\n".join(linhas) + "\n}\n").encode("utf-8"))


def problemas(manifesto: Manifesto) -> list[str]:
    """O que faz o manifesto não valer. Vazio quer dizer que ele vale."""
    erros: list[str] = []
    if manifesto.versao != VERSAO:
        erros.append(f"versão {manifesto.versao}, esperada {VERSAO}")
    if not _DATA.fullmatch(manifesto.congelado_em):
        erros.append(f"congelado_em sem data AAAA-MM-DD: {manifesto.congelado_em!r}")
    leitura = manifesto.primeira_leitura_do_teste
    if leitura is not None and (not _DATA.fullmatch(str(leitura)) or str(leitura) < manifesto.congelado_em):
        erros.append(f"o teste foi lido em {leitura}, antes de o manifesto ser congelado em {manifesto.congelado_em}")
    splits_do_livro: dict[str, set[str]] = {}
    lingua_do_livro = {livro.identidade: livro.lingua for livro in manifesto.livros}
    for livro in manifesto.livros:
        if not livro.identidade:
            erros.append("livro sem identidade")
        if livro.split not in SPLITS:
            erros.append(f"livro {livro.identidade} com split {livro.split!r}")
        if livro.origem not in ORIGENS:
            erros.append(f"livro {livro.identidade} com origem {livro.origem!r}")
        if livro.diagramacao not in DIAGRAMACOES:
            erros.append(f"livro {livro.identidade} com diagramação {livro.diagramacao!r}")
        if livro.lingua not in LINGUAS:
            erros.append(f"livro {livro.identidade} com língua {livro.lingua!r}")
        if livro.entrou_em and (livro.split != TESTE or not _DATA.fullmatch(livro.entrou_em)
                                or livro.entrou_em < manifesto.congelado_em):
            erros.append(f"livro {livro.identidade} com entrou_em {livro.entrou_em!r}")
        splits_do_livro.setdefault(livro.identidade, set()).add(livro.split)
        if livro.reprovado and (livro.split != RESERVA or not livro.fora_do_treino):
            erros.append(f"livro {livro.identidade} reprovado ({livro.reprovado}) fora da reserva ou dentro do treino")
    for identidade, splits in splits_do_livro.items():
        if len(splits) > 1:
            erros.append(f"livro {identidade} em dois splits: {sorted(splits)}")
    vistas: set[tuple[str, int]] = set()
    for folha in manifesto.folhas:
        if not folha.identidade:
            erros.append(f"folha {folha.folha} sem identidade")
            continue
        if folha.identidade not in splits_do_livro:
            erros.append(f"folha {folha.folha} de um livro que o manifesto não lista: {folha.identidade}")
        elif folha.split not in splits_do_livro[folha.identidade]:
            erros.append(f"folha {folha.folha} de {folha.identidade} no split {folha.split}, e o livro não")
        if folha.identidade in lingua_do_livro and folha.lingua != lingua_do_livro[folha.identidade]:
            erros.append(f"folha {folha.folha} de {folha.identidade} em {folha.lingua!r}, e o livro em "
                         f"{lingua_do_livro[folha.identidade]!r}")
        if folha.estrato not in ESTRATOS:
            erros.append(f"folha {folha.folha} de {folha.identidade} com estrato {folha.estrato!r}")
        if folha.folha < 1:
            erros.append(f"folha {folha.folha} de {folha.identidade}: a folha é em base 1")
        if (folha.identidade, folha.folha) in vistas:
            erros.append(f"folha {folha.folha} de {folha.identidade} repetida")
        vistas.add((folha.identidade, folha.folha))
    teste = {livro.identidade: livro for livro in manifesto.livros if livro.split == TESTE}
    if teste:
        if len(teste) < TESTE_MINIMO:
            erros.append(f"o teste tem {len(teste)} livros, e o mínimo é {TESTE_MINIMO}")
        linguas = {livro.lingua for livro in teste.values()}
        pendente = PENDENCIA_DE_LINGUA in manifesto.pendencias
        if len(linguas) < LINGUAS_MINIMAS_NO_TESTE and not pendente:
            erros.append(f"o teste tem {len(linguas)} línguas, e o mínimo é {LINGUAS_MINIMAS_NO_TESTE}")
        if len(linguas) >= LINGUAS_MINIMAS_NO_TESTE and pendente:
            erros.append(f"o teste já tem {len(linguas)} línguas, e a pendência {PENDENCIA_DE_LINGUA} não saiu")
        vistas_no_teste = sorted(i for i, livro in teste.items() if livro.diagramacao != "nova")
        if vistas_no_teste:
            erros.append(f"livros do teste com diagramação de livro dev: {vistas_no_teste}")
        sem_folha = sorted(set(teste) - {f.identidade for f in manifesto.folhas})
        if sem_folha:
            erros.append(f"livros do teste sem folha: {sem_folha}")
        grupos_do_teste = {livro.grupo or livro.identidade for livro in teste.values()}
        for livro in manifesto.livros:
            if livro.split == RESERVA and (livro.grupo or livro.identidade) in grupos_do_teste and not livro.fora_do_treino:
                erros.append(f"livro {livro.identidade} é do grupo de um livro do teste e não está fora_do_treino")
    desconhecidas = sorted(set(manifesto.pendencias) - {PENDENCIA_DE_LINGUA})
    if desconhecidas:
        erros.append(f"pendências sem regra: {desconhecidas}")
    return erros


def acrescentar_ao_teste(
    manifesto: Manifesto,
    livro: LivroDoOuro,
    folhas: Sequence[tuple[int, str]],
    *,
    entrou_em: str,
    folhas_minimas: int = 6,
) -> Manifesto:
    """O livro que chega depois do congelamento entra **a mais** no teste -- a terceira língua pendente.

    Nada do que foi sorteado muda: os livros do teste e todas as folhas ficam como estão, na mesma
    ordem, e o livro novo e as folhas dele (sorteadas por `sortear_folhas`, como as outras) vão para o
    fim. Na reserva, só muda o `fora_do_treino` dos irmãos de série do livro novo. A pendência de
    língua sai quando o teste passa a ter as línguas mínimas.

    A elegibilidade é a dos candidatos do sorteio, e quem chama a diz no `livro`: a `diagramacao`
    (`vista` não entra) e o `grupo` da série (a série que já tem livro no teste não ganha outro). Um
    livro que o manifesto já lista não entra -- seria trocar o split dele --, nem o que traz menos de
    `folhas_minimas` folhas.
    """
    if any(x.identidade == livro.identidade for x in manifesto.livros):
        raise ValueError(f"o livro {livro.identidade} já está no manifesto")
    if livro.diagramacao != "nova":
        raise ValueError(f"o livro {livro.identidade} tem a diagramação de um livro dev")
    if len(folhas) < folhas_minimas:
        raise ValueError(f"o livro {livro.identidade} trouxe {len(folhas)} folhas, e o mínimo é {folhas_minimas}")
    grupo = livro.grupo
    if grupo and grupo in {x.grupo or x.identidade for x in manifesto.livros if x.split == TESTE}:
        raise ValueError(f"a série {grupo} já tem um livro no teste")
    if not _DATA.fullmatch(entrou_em) or entrou_em < manifesto.congelado_em:
        raise ValueError(f"entrou_em {entrou_em!r} não é data a partir de {manifesto.congelado_em}")
    novo = replace(livro, split=TESTE, fora_do_treino=False, reprovado="", entrou_em=entrou_em)
    irmaos = {x.identidade for x in manifesto.livros if grupo and x.split == RESERVA and (x.grupo or x.identidade) == grupo}
    livros = (*(replace(x, fora_do_treino=True) if x.identidade in irmaos else x for x in manifesto.livros), novo)
    linguas = {x.lingua for x in livros if x.split == TESTE}
    cumprida = len(linguas) >= LINGUAS_MINIMAS_NO_TESTE
    return replace(
        manifesto,
        livros=livros,
        folhas=(*manifesto.folhas, *(FolhaDoOuro(livro.identidade, f, livro.lingua, e, TESTE) for f, e in folhas)),
        pendencias=tuple(x for x in manifesto.pendencias if not (x == PENDENCIA_DE_LINGUA and cumprida)),
    )


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def ordem_dos_livros(identidades: Iterable[str], semente: str) -> list[str]:
    """Os livros na ordem do sorteio. Não depende da ordem em que foram listados."""
    return sorted(set(identidades), key=lambda identidade: (_sha(f"{semente}:{identidade}"), identidade))


def ordem_das_folhas(identidade: str, n_folhas: int, pular: float = PULAR) -> list[int]:
    """As folhas do livro (base 1) na ordem do sorteio, sem os `pular` iniciais e finais."""
    inicio, fim = int(n_folhas * pular), int(n_folhas * (1 - pular))
    folhas = range(inicio + 1, fim + 1)
    return sorted(folhas, key=lambda folha: (_sha(f"{identidade}{folha}"), folha))


def estrato_do_texto(texto: str, classificar: Callable[[str], str]) -> str | None:
    """O estrato de uma folha pelo texto da camada, com o classificador de token dado."""
    if len(texto) < ESTRATO_MISTO[0]:
        return None
    tokens = re.findall(r"\S+", texto)
    total = sum(len(t) for t in tokens)
    prosa = sum(len(t) for t in tokens if classificar(t) == "prosa")
    fracao = prosa / max(1, total)
    for nome, (minimo, de, ate) in ((PROSA, ESTRATO_PROSA), (MISTO, ESTRATO_MISTO)):
        if len(texto) >= minimo and prosa >= minimo and de <= fracao < ate:
            return nome
    return None


def sortear_folhas(
    identidade: str,
    n_folhas: int,
    estrato_de: Callable[[int], str | None],
    admitida: Callable[[int], bool],
    *,
    por_estrato: int = 3,
) -> list[tuple[int, str]]:
    """As folhas sorteadas de um livro: `por_estrato` de cada estrato, ou o outro completando.

    `estrato_de` e `admitida` recebem a folha em base 1. A admissão, que custa uma montagem da
    camada, só é perguntada para a folha que já caiu num estrato que ainda precisa dela. Se um
    estrato acaba antes de completar, o outro completa até `2 * por_estrato`, com **todas** as folhas
    dele na ordem do sorteio -- a primeira versão guardava só seis sobras, e um livro com centenas de
    folhas de prosa cedeu a vaga por isso (crítico da S-702). O livro que não chega lá volta com
    menos, e quem sorteia decide trocá-lo pelo seguinte.
    """
    escolhidas: dict[str, list[int]] = {PROSA: [], MISTO: []}
    sobras: dict[str, list[int]] = {PROSA: [], MISTO: []}
    alvo = 2 * por_estrato
    for folha in ordem_das_folhas(identidade, n_folhas):
        if all(len(v) >= por_estrato for v in escolhidas.values()):
            break
        estrato = estrato_de(folha)
        if estrato is None:
            continue
        if len(escolhidas[estrato]) >= por_estrato:
            sobras[estrato].append(folha)
            continue
        if admitida(folha):
            escolhidas[estrato].append(folha)
    falta = alvo - sum(len(v) for v in escolhidas.values())
    for estrato in ESTRATOS:
        for folha in sobras[estrato]:
            if falta <= 0:
                break
            if admitida(folha):
                escolhidas[estrato].append(folha)
                falta -= 1
    return [(folha, estrato) for estrato in ESTRATOS for folha in escolhidas[estrato]]


def sortear_livros(
    candidatos: Sequence[LivroDoOuro],
    total: int,
    semente: str,
    *,
    linguas_inteiras: Iterable[str] = (),
) -> list[str]:
    """Os livros do teste, na ordem do sorteio.

    Os candidatos de `linguas_inteiras` entram todos -- é o que garante as três línguas quando uma
    delas tem um livro só. O resto se divide entre as origens na proporção em que elas aparecem nos
    candidatos que sobraram (maior resto), e cada origem toma os primeiros da ordem do sorteio.
    """
    inteiras = set(linguas_inteiras)
    obrigatorios = [c.identidade for c in candidatos if c.lingua in inteiras]
    resto = [c for c in candidatos if c.lingua not in inteiras]
    vagas = max(0, total - len(obrigatorios))
    por_origem: dict[str, list[str]] = {}
    for c in resto:
        por_origem.setdefault(c.origem, []).append(c.identidade)
    cotas = _maior_resto({o: len(v) for o, v in por_origem.items()}, vagas)
    escolhidos = list(obrigatorios)
    for origem, ids in sorted(por_origem.items()):
        escolhidos.extend(ordem_dos_livros(ids, semente)[: cotas[origem]])
    return ordem_dos_livros(escolhidos, semente)


def _maior_resto(pesos: dict[str, int], vagas: int) -> dict[str, int]:
    soma = sum(pesos.values())
    if soma == 0:
        return dict.fromkeys(pesos, 0)
    exatas = {k: vagas * v / soma for k, v in pesos.items()}
    cotas = {k: min(int(x), pesos[k]) for k, x in exatas.items()}
    for k in sorted(pesos, key=lambda k: (-(exatas[k] - int(exatas[k])), k)):
        if sum(cotas.values()) >= min(vagas, soma):
            break
        if cotas[k] < pesos[k]:
            cotas[k] += 1
    return cotas


def localizar(identidades: Iterable[str], pastas: Iterable[str | Path]) -> dict[str, Path]:
    """Onde está cada livro, pela identidade do conteúdo. O que não se acha fica de fora do dicionário."""
    procurados = set(identidades)
    achados: dict[str, Path] = {}
    for pasta in pastas:
        pasta = Path(pasta)
        if not pasta.is_dir():
            continue
        for pdf in sorted(pasta.glob("*.pdf")):
            identidade = identidade_de(pdf)
            if identidade in procurados and identidade not in achados:
                achados[identidade] = pdf
    return achados
