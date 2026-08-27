"""Divisão treino/validação/teste estável e persistida.

O problema que isto resolve (ver ANALISE.md §3.4): a divisão anterior era
`torch.randperm` com semente fixa sobre `len(dataset.entries)`. A semente é fixa, mas o
**tamanho** não: ao crescer de 3.244 para 3.300 amostras, a permutação muda inteira e um
tabuleiro que era validação passa a treino. Como o treino sempre retoma o checkpoint
anterior, o modelo já viu o que hoje é validação -- e a métrica se contamina de forma
crescente e invisível.

A solução tem duas partes:

1. **Split por identidade, não por índice.** O bucket vem de um hash do nome do arquivo.
   Amostras novas recebem um split sem mover nenhuma das antigas.

2. **Split por grupo, não por arquivo.** Amostras que são o mesmo diagrama (ver
   `audit.find_duplicate_groups`) precisam cair no mesmo split. Sem isso, a mesma
   posição aparece em treino e em validação, e a validação deixa de medir generalização.
   Neste dataset isso afeta 234 amostras em 220 grupos -- ~7% do total.

Ver S-07 em docs/SPEC.md.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal

from .atomic_io import atomic_write_bytes

logger = logging.getLogger(__name__)

Split = Literal["train", "val", "test"]

SPLIT_SALT = "cvoff-v1"
"""Alterar isto reembaralha tudo. Só mude com intenção deliberada e registro."""

DEFAULT_VAL_PCT = 10
DEFAULT_TEST_PCT = 10


def _bucket(key: str, salt: str = SPLIT_SALT) -> int:
    """Bucket determinístico de 0 a 99 a partir de uma chave textual.

    Usa SHA-256 em vez de `hash()`: o `hash()` de str em Python é randomizado por
    processo (PYTHONHASHSEED), o que tornaria o split diferente a cada execução.
    """
    digest = hashlib.sha256(f"{salt}:{key}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 100


def assign_split(
    key: str,
    *,
    val_pct: int = DEFAULT_VAL_PCT,
    test_pct: int = DEFAULT_TEST_PCT,
    salt: str = SPLIT_SALT,
) -> Split:
    """Atribui um split a uma chave (nome de arquivo ou identificador de grupo)."""
    if val_pct < 0 or test_pct < 0 or val_pct + test_pct >= 100:
        raise ValueError("val_pct e test_pct devem ser positivos e somar menos de 100.")

    bucket = _bucket(key, salt=salt)
    if bucket < test_pct:
        return "test"
    if bucket < test_pct + val_pct:
        return "val"
    return "train"


def group_keys(filenames: Iterable[str], groups: Iterable[Iterable[str]]) -> dict[str, str]:
    """Mapeia cada arquivo para a chave do seu grupo.

    Arquivos que não pertencem a nenhum grupo são sua própria chave. Para os que
    pertencem, a chave é o nome do primeiro membro (ordenado), de forma que todos os
    membros derivem o mesmo split.
    """
    keys = {name: name for name in filenames}
    for group in groups:
        members = sorted(group)
        if len(members) < 2:
            continue
        representative = members[0]
        for member in members:
            keys[member] = representative
    return keys


def groups_by_book(provenance: Mapping[str, str]) -> list[list[str]]:
    """Agrupa as amostras por livro de origem, para o split por livro da S-07/S-52.

    `provenance` é `{nome do arquivo: source_pdf}`; amostra sem procedência fica de fora e
    continua com split individual, que é o comportamento de hoje.

    **Por que isto importa.** O split de hoje é por hash do nome do arquivo, agrupado por
    diagrama duplicado. Com ele, o mesmo livro aparece nos três conjuntos, e o número do
    `test` responde "quão bem o modelo lê um diagrama parecido com os que viu" -- não "quão
    bem ele lê um livro que nunca viu". A segunda pergunta é a do produto, e ela precisa que
    o livro inteiro caia de um lado só.

    **Duas ressalvas honestas, e as duas são consequência do desenho da S-07.**

    1. `ensure_splits` **nunca move uma amostra já registrada**, e é essa garantia que mantém
       o conjunto de teste confiável ao longo do tempo. Então agrupar por livro só passa a
       valer de fato para amostras novas ou numa reatribuição do zero (`--fresh`): as 3.313 já
       registradas continuam onde estão, com o livro espalhado entre os três conjuntos.
    2. Um acervo de 27 livros dá 27 grupos, e 10% deles é 2,7 livros. A granularidade do
       split cai muito: um livro grande pode levar sozinho mais que a fatia inteira de teste.
       Isso não é defeito do agrupamento, é o que agrupar por livro significa -- e é preciso
       olhar a distribuição resultante antes de adotá-lo.
    """
    por_livro: dict[str, list[str]] = {}
    for filename, book in provenance.items():
        if not book:
            continue
        por_livro.setdefault(book, []).append(filename)
    return [sorted(membros) for _livro, membros in sorted(por_livro.items()) if len(membros) > 1]


def groups_by_origin(origins: Mapping[str, tuple[str, str, str]]) -> list[list[str]]:
    """Agrupa as amostras que são **o mesmo diagrama impresso** (S-98).

    `origins` é `{nome do arquivo: (source_pdf, source_page, source_diagram)}`; amostra sem
    procedência fica de fora e continua com o guarda de imagem, que é o de hoje.

    **Por que o guarda de imagem não bastava.** `duplicate_groups_touching` agrupa por
    `placement` idêntico **e** dHash ≤ 3, e o 3 foi calibrado para *"a mesma amostra salva
    duas vezes"* (`audit.py:242-247`). Ele não vê a mesma página **reextraída com recorte
    deslocado** -- e isso acontece toda vez que um livro é varrido de novo depois de a
    detecção mudar, porque `append_training_sample` gera nome novo por timestamp e
    `ensure_splits` sorteia pelo hash do nome.

    Medido em 2026-08-16 no acervo: **3 triplas cruzam split**, e a do
    `Niemeijer - Zwarte Magie p10 d1` está nas **três** partições -- o mesmo diagrama impresso
    salvo quatro vezes. `find_duplicate_groups` devolve 373 grupos e **0 espalhados entre
    splits**, o que torna a frase do relatório da auditoria (*"a validação segue honesta"*)
    verdadeira pela definição de grupo e vazia na prática.

    **O alcance é declarado, e é pequeno:** 625 de 3.936 linhas (15,9%) têm procedência. Isto
    resolve as 3 triplas e **nenhum** dos casos sem procedência -- para esses o caminho é a
    S-121 (recuperar procedência por hash perceptual) e não este agrupamento. Prometer mais
    seria repetir o defeito que ele corrige: uma garantia que a definição torna verdadeira e
    a prática torna vazia.
    """
    por_origem: dict[tuple[str, str, str], list[str]] = {}
    for filename, origem in origins.items():
        pdf, page, diagram = origem
        if not pdf or not page:
            continue
        por_origem.setdefault((pdf, page, diagram), []).append(filename)
    return [sorted(membros) for _chave, membros in sorted(por_origem.items()) if len(membros) > 1]


def split_leaks(
    origins: Mapping[str, tuple[str, str, str]], splits: Mapping[str, Split]
) -> list[tuple[tuple[str, str, str], dict[str, Split]]]:
    """As triplas de procedência cujos arquivos caíram em splits diferentes (S-98).

    Devolve `[(chave de origem, {arquivo: split})]`, ordenado. Serve ao relatório da
    auditoria: **listar, não mover**. Mover uma linha de `test` é irreversível na prática --
    o `test` existe para responder uma pergunta uma vez --, então quem aplica é gente.
    """
    vazamentos = []
    for chave, membros in sorted(
        {
            origem: [nome for nome in origins if origins[nome] == origem]
            for origem in {o for f, o in origins.items() if o[0] and o[1] and f in splits}
        }.items()
    ):
        atribuidos = {nome: splits[nome] for nome in sorted(membros) if nome in splits}
        if len({*atribuidos.values()}) > 1:
            vazamentos.append((chave, atribuidos))
    return vazamentos


def compute_splits(
    filenames: Iterable[str],
    *,
    groups: Iterable[Iterable[str]] = (),
    val_pct: int = DEFAULT_VAL_PCT,
    test_pct: int = DEFAULT_TEST_PCT,
    salt: str = SPLIT_SALT,
) -> dict[str, Split]:
    """Calcula o split de cada arquivo, respeitando os grupos redundantes."""
    names = list(filenames)
    keys = group_keys(names, groups)
    return {name: assign_split(keys[name], val_pct=val_pct, test_pct=test_pct, salt=salt) for name in names}


def load_splits(path: Path) -> dict[str, Split]:
    path = Path(path)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        colunas = set(reader.fieldnames or ())
        required = {"filename", "split"}
        if not required.issubset(colunas):
            raise ValueError(f"{path} precisa das colunas {required}. Encontradas: {colunas}")

        result: dict[str, Split] = {}
        for row in reader:
            split = str(row.get("split", "")).strip()
            if split not in ("train", "val", "test"):
                raise ValueError(f"Split inválido em {path}: {split!r}")
            result[str(row.get("filename", "")).strip()] = split  # type: ignore[assignment]
    return result


def save_splits(path: Path, splits: Mapping[str, Split]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator=os.linesep)
    writer.writerow(["filename", "split"])
    writer.writerows(sorted(splits.items()))

    # Escrita atomica (S-25), como a do `labels.csv`. Este arquivo carrega uma decisao
    # irreversivel na pratica -- por desenho da S-07, uma amostra que caiu no `test` fica
    # la --, e ate a S-51 ele era gravado com `to_csv` direto no destino, que trunca antes
    # de escrever. Um corte de energia no meio nao perderia o arquivo: perderia a fronteira
    # entre treino e teste, que e o que torna toda medicao do projeto confiavel.
    atomic_write_bytes(path, buffer.getvalue().encode("utf-8"))
    logger.info("Splits gravados em %s (%d amostras).", path, len(splits))


def ensure_splits(
    filenames: Iterable[str],
    splits_path: Path,
    *,
    groups: Iterable[Iterable[str]] = (),
    val_pct: int = DEFAULT_VAL_PCT,
    test_pct: int = DEFAULT_TEST_PCT,
    salt: str = SPLIT_SALT,
) -> dict[str, Split]:
    """Carrega os splits existentes e atribui split apenas às amostras novas.

    Nunca altera a atribuição de uma amostra já registrada -- é essa garantia que
    mantém o conjunto de teste confiável ao longo do tempo.

    **Lista vazia nunca é razão para podar (S-300).** Podar um *subconjunto* é o comportamento
    desejado desta função -- amostra que saiu do CSV sai do arquivo de splits. Podar *tudo* é
    outra coisa, e era o que acontecia: `labels.csv` inexistente faz `LabelStore._load_rows`
    devolver `[]`, `training.resolve_splits` chegar aqui com `filenames` vazio, e `removed` virar
    o arquivo inteiro. Reproduzido: um `splits.csv` de três amostras voltava a ser só o
    cabeçalho.

    O que se perde não é dado -- é a **fronteira** entre treino e teste, que é o que torna toda
    medição do projeto comparável, e ela não se reconstrói: apagada, a amostra que era `test`
    volta a ser sorteada. E o aviso que existia para isso, o `ValueError("Dataset vazio")` de
    `Trainer.prepare`, só aparece **depois** da poda. Um `--csv` digitado errado bastava, e o
    botão "Treinar modelo" da janela não tem portão nenhum antes daqui.
    """
    names = list(filenames)
    existing = load_splits(splits_path)
    if not names:
        logger.warning(
            "Nenhuma amostra na lista: os %d splits gravados ficaram como estavam (S-300).",
            len(existing),
        )
        return dict(existing)
    keys = group_keys(names, groups)

    result: dict[str, Split] = {}
    added = 0
    for name in names:
        if name in existing:
            result[name] = existing[name]
            continue

        # Amostra nova: se o grupo dela já tem split definido, herda; senão, calcula.
        representative = keys[name]
        inherited = existing.get(representative) or result.get(representative)
        result[name] = inherited or assign_split(representative, val_pct=val_pct, test_pct=test_pct, salt=salt)
        added += 1

    removed = set(existing) - set(names)
    if removed:
        logger.info("%d amostras saíram do CSV e foram retiradas do arquivo de splits.", len(removed))
    if added or removed:
        save_splits(splits_path, result)
        logger.info("%d amostras novas receberam split.", added)

    return result


def splits_hash(splits: Mapping[str, Split]) -> str:
    """Identidade da divisão, para o checkpoint dizer sobre que partição ele foi treinado.

    Sem isso, "o modelo A é melhor que o B" pode estar comparando dois modelos avaliados
    em conjuntos de teste diferentes -- que é o erro que a S-07 existe para impedir e que
    nada, até aqui, impedia de voltar em silêncio ao crescer o dataset.
    """
    payload = "\n".join(f"{name}={split}" for name, split in sorted(splits.items()))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def split_counts(splits: Mapping[str, Split]) -> dict[str, int]:
    counts = {"train": 0, "val": 0, "test": 0}
    for split in splits.values():
        counts[split] += 1
    return counts
