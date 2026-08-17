"""Auditoria e saneamento do dataset de rótulos.

Responde três perguntas que hoje não têm resposta no projeto: quais rótulos estão
errados, quais são duplicatas, e o que está órfão. Ver S-06 em docs/SPEC.md.
"""

from __future__ import annotations

import logging
import shutil
from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .atomic_io import atomic_write_json
from .config import PIECE_CLASSES
from .fen_utils import check_position, is_syntactically_valid_fen, labels_from_fen
from .labels import LabelStore
from .splits import load_splits

logger = logging.getLogger(__name__)

# Resolução do hash perceptual.
#
# 16 (=256 bits) e não 8. Um dHash 8x8 sobre um diagrama de xadrez é degenerado: o
# downsample alinha exatamente com a grade 8x8 do tabuleiro, então o hash captura o
# padrão xadrezado -- que é idêntico em todos os diagramas -- e quase nada das peças.
#
# Medido em 7.139 pares de posições diferentes deste dataset:
#   dHash 8x8  -> distância mediana 15/64, com 25 pares distintos abaixo do limiar
#   dHash 16x16 -> distância mediana 52/256, com nenhum par distinto abaixo do limiar
DUPLICATE_HASH_SIZE = 16

# Distância de Hamming máxima para considerar duas imagens a mesma.
# Duas renderizações diferentes da mesma posição (livros distintos) ficam por volta de
# 10 bits, acima do limiar -- e é justamente o que se quer: não são cópias redundantes.
DUPLICATE_HAMMING_THRESHOLD = 3

# Teto de redundância, como fração dos rótulos utilizáveis (S-63).
#
# Não é um limite de qualidade: recorte diferente da mesma página é aumento de dados legítimo,
# e o BASELINE.md registra 234 redundantes em 220 grupos como estado aceito. O que este número
# vigia é **crescimento sem ninguém olhando** -- entre o BASELINE e a Fase 11 subiu para 248 em
# 227, e nada no projeto notou. 10% dá folga sobre os ~7% de hoje e dispara antes de a
# redundância virar um décimo do conjunto de validação.
DUPLICATE_SHARE_CEILING = 0.10


@dataclass(frozen=True)
class LabelIssue:
    filename: str
    fen: str
    kind: str
    """Um de: 'sintaxe', 'fatal', 'lado-a-jogar', 'imagem-ausente'."""
    problems: tuple[str, ...]
    suggested_fen: str | None = None
    """Correção automática possível, quando houver."""


@dataclass
class AuditReport:
    csv_path: Path
    samples_dir: Path
    total_rows: int = 0
    valid_rows: int = 0
    issues: list[LabelIssue] = field(default_factory=list)
    deliberate_illegal: list[LabelIssue] = field(default_factory=list)
    """Ilegais **confirmadas** por uma pessoa (coluna `illegal_ok`). Não são problema.

    Fora de `issues` de propósito: tudo que está lá é candidato ao `--fix`, e a correção
    automática destas seria mandá-las para a quarentena -- desfazendo a única decisão do
    arquivo que não pode ser deduzida da FEN. Ficam numa lista própria para continuarem
    visíveis no relatório sem entrarem em nenhum conserto."""

    duplicate_groups: list[list[str]] = field(default_factory=list)
    orphan_images: list[str] = field(default_factory=list)
    class_counts: Counter[str] = field(default_factory=Counter)

    def of_kind(self, kind: str) -> list[LabelIssue]:
        return [issue for issue in self.issues if issue.kind == kind]

    @property
    def duplicate_count(self) -> int:
        """Número de arquivos que são cópia de outro já presente."""
        return sum(len(group) - 1 for group in self.duplicate_groups)

    @property
    def duplicate_share(self) -> float:
        """Fração dos rótulos utilizáveis que é cópia de outro (S-63).

        Zero quando não há rótulo utilizável -- um CSV vazio não tem excesso de redundância,
        tem outro problema, e devolver `nan` aqui faria a comparação com o teto virar `False`
        por acidente em vez de por medição.
        """
        return self.duplicate_count / self.valid_rows if self.valid_rows else 0.0

    @property
    def duplicates_above_ceiling(self) -> bool:
        return self.duplicate_share > DUPLICATE_SHARE_CEILING

    def violations(self) -> list[str]:
        """Os limites **declarados** que este relatório viola, em pt-BR. Vazio é aprovado (S-102).

        **O que entra aqui é o que já era um limite escrito, não uma régua nova.** A auditoria
        relatava tudo e saía com código 0, inclusive com o teto da S-63 estourado em 11,0%;
        nada no fluxo a consultava antes de treinar, e a imagem ausente é, nas palavras do
        próprio relatório, *"descartada em silêncio no treino"*.

        **O que fica de fora, e por quê:**

        - **amostra sem split** não é violação: quem atribui é o `cvoff-train`, e ele o faz na
          linha seguinte (S-56). Barrar aqui seria barrar o conserto;
        - **ilegal confirmada à mão** (`illegal_ok`) é decisão humana registrada (S-70), não
          defeito;
        - **vazamento de split** (S-98) fica de fora porque o remédio é mover linha, que é
          irreversível na prática e por isso "lista e não move". Barrar o treino por algo que
          o comando se recusa a consertar deixaria o projeto sem saída.
        """
        violacoes = []
        fatais = len(self.of_kind("fatal"))
        if fatais:
            violacoes.append(f"{fatais} posição(ões) ilegal(is) fatal(is) -- conserto: cvoff-audit --quarantine")
        sintaxe = len(self.of_kind("sintaxe"))
        if sintaxe:
            violacoes.append(f"{sintaxe} FEN(s) não interpretável(is) -- conserto: corrija pela aba Dataset")
        ausentes = len(self.of_kind("imagem-ausente"))
        if ausentes:
            violacoes.append(f"{ausentes} rótulo(s) com PNG ausente -- conserto: cvoff-audit --drop-missing")
        if self.duplicates_above_ceiling:
            violacoes.append(
                f"redundância em {self.duplicate_share:.1%}, acima do teto de "
                f"{DUPLICATE_SHARE_CEILING:.0%} (S-63) -- conserto: cvoff-audit --dedupe, "
                "ou suba o teto explicitamente e registre por quê"
            )
        return violacoes


def dhash(image_bgr: np.ndarray, hash_size: int = DUPLICATE_HASH_SIZE) -> int:
    """Hash perceptual (dHash) de `hash_size**2` bits.

    Compara cada pixel com o vizinho à direita numa versão reduzida em tons de cinza.
    Tolera recompressão e pequenas diferenças de recorte -- ao contrário de um hash de
    bytes, que muda completamente com 1 pixel de diferença.

    Ver DUPLICATE_HASH_SIZE sobre por que 8 não serve para tabuleiros de xadrez.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]

    value = 0
    for bit in diff.flatten():
        value = (value << 1) | int(bit)
    return value


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _normalized_placement(fen: str) -> str:
    return fen.split()[0] if " " in fen else fen


def _fen_with_turn(fen: str, turn_char: str) -> str:
    parts = fen.split()
    if len(parts) == 1:
        return f"{parts[0]} {turn_char} - - 0 1"
    parts[1] = turn_char
    return " ".join(parts)


def read_label_rows(csv_path: Path) -> list[tuple[str, str]]:
    """Os pares `(arquivo, FEN)` do CSV de rótulos, na ordem em que estão nele.

    Era privada deste módulo. Deixou de ser quando `training.resolve_splits` (S-56) passou a
    precisar da mesma leitura: importar um `_nome` de outro módulo é sinal de que a fronteira
    está no lugar errado, e a fronteira certa aqui é "quem sabe ler o esquema de rótulos".
    """
    return LabelStore(csv_path).read_pairs()


def audit_dataset(csv_path: Path, samples_dir: Path, *, check_duplicates: bool = True) -> AuditReport:
    """Percorre o CSV de rótulos e produz o relatório completo de problemas."""
    csv_path = Path(csv_path)
    samples_dir = Path(samples_dir)
    report = AuditReport(csv_path=csv_path, samples_dir=samples_dir)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV de rótulos não encontrado: {csv_path}")

    # Entradas inteiras, e nao os pares `(arquivo, FEN)`: e a coluna `illegal_ok` que separa
    # "o modelo perdeu o rei" de "o livro desenhou uma estrutura sem rei", e sem ela a
    # quarentena do `--fix` tiraria do arquivo justamente os diagramas que alguem confirmou.
    entries = LabelStore(csv_path).read()
    report.total_rows = len(entries)
    referenced: set[str] = set()
    usable_labels: list[tuple[str, str]] = []

    for entry in entries:
        filename, fen = entry.filename, entry.fen
        referenced.add(filename)

        if not fen or fen.lower() == "nan" or not is_syntactically_valid_fen(fen):
            report.issues.append(
                LabelIssue(filename=filename, fen=fen, kind="sintaxe", problems=("FEN vazia ou não interpretável",))
            )
            continue

        position = check_position(fen)
        if position.is_fatal and entry.illegal_accepted:
            # Nao e problema, e nao entra em `issues`: e um diagrama que uma pessoa olhou e
            # declarou certo. Continua contado a parte, porque um "sim" dado por engano tem de
            # ter onde aparecer.
            report.deliberate_illegal.append(
                LabelIssue(filename=filename, fen=fen, kind="ilegal-confirmada", problems=position.problems)
            )
        elif position.is_fatal:
            report.issues.append(
                LabelIssue(filename=filename, fen=fen, kind="fatal", problems=position.problems)
            )
        elif position.needs_side_to_move_flip:
            turn_char = "b" if position.legal_turn is False else "w"
            report.issues.append(
                LabelIssue(
                    filename=filename,
                    fen=fen,
                    kind="lado-a-jogar",
                    problems=position.problems,
                    suggested_fen=_fen_with_turn(fen, turn_char),
                )
            )

        if not (samples_dir / filename).exists():
            report.issues.append(
                LabelIssue(filename=filename, fen=fen, kind="imagem-ausente", problems=("arquivo não encontrado",))
            )
            continue

        if not position.is_fatal or entry.illegal_accepted:
            # "Utilizavel" aqui quer dizer "o treino vai ver esta linha", e desde a marca da
            # `illegal_ok` ele ve. Contar como inutilizavel o que entra no treino faria a
            # fracao de redundancia (S-63) ser calculada sobre uma base que nao existe.
            report.valid_rows += 1
            usable_labels.append((filename, fen))
            try:
                for class_idx in labels_from_fen(fen):
                    report.class_counts[PIECE_CLASSES[class_idx]] += 1
            except (ValueError, IndexError) as exc:
                logger.debug("Não foi possível contar classes de %s: %s", filename, exc)

    if samples_dir.exists():
        on_disk = {path.name for path in samples_dir.glob("*.png")}
        report.orphan_images = sorted(on_disk - referenced)

    if check_duplicates:
        report.duplicate_groups = find_duplicate_groups(samples_dir, usable_labels)

    return report


def find_duplicate_groups(
    samples_dir: Path,
    labels: Iterable[tuple[str, str]],
) -> list[list[str]]:
    """Agrupa amostras que são o mesmo diagrama: imagem perceptualmente igual **e** mesmo rótulo.

    `labels` são pares (nome do arquivo, FEN).

    Exigir o rótulo igual é deliberado. Se duas imagens iguais têm rótulos diferentes,
    uma das anotações está errada e não se sabe qual: remover às cegas descartaria a
    correta.

    Atenção ao que um grupo significa. Medido neste dataset, os grupos contêm dois casos:

    1. **Imagem byte a byte idêntica** -- a mesma amostra salva duas vezes (diferença de
       pixels 0,00%).
    2. **Mesmo diagrama reextraído** -- a mesma página processada de novo, com recorte
       ligeiramente diferente (26% a 38% dos pixels divergem, mas a estrutura é a mesma).

    O caso 2 não é lixo: recortes distintos funcionam como aumento de dados. Mas os dois
    casos compartilham uma consequência crítica -- membros de um grupo **não podem cair
    em splits diferentes**, senão a validação mede o que o modelo já viu no treino. Ver
    `groups_for_split` e S-07.

    Retorna apenas grupos com mais de um arquivo. O primeiro de cada grupo é o
    representante a manter.
    """
    samples_dir = Path(samples_dir)
    fingerprints: dict[str, tuple[str, int]] = {}

    for filename, fen in labels:
        path = samples_dir / filename
        if not path.exists():
            continue
        image = cv2.imread(str(path))
        if image is None:
            logger.warning("Imagem ilegível, ignorada na deduplicação: %s", path)
            continue
        fingerprints[filename] = (_normalized_placement(fen), dhash(image))

    # Agrupa primeiro por rótulo: só faz sentido comparar hashes dentro do mesmo rótulo,
    # e isso reduz drasticamente o custo (evita O(n^2) sobre os 3.244 arquivos).
    by_placement: dict[str, list[tuple[str, int]]] = {}
    for filename, (placement, value) in fingerprints.items():
        by_placement.setdefault(placement, []).append((filename, value))

    groups: list[list[str]] = []
    for candidates in by_placement.values():
        if len(candidates) < 2:
            continue

        remaining = sorted(candidates)
        while remaining:
            head_name, head_hash = remaining.pop(0)
            group = [head_name]
            rest: list[tuple[str, int]] = []
            for name, value in remaining:
                if hamming_distance(head_hash, value) <= DUPLICATE_HAMMING_THRESHOLD:
                    group.append(name)
                else:
                    rest.append((name, value))
            remaining = rest
            if len(group) > 1:
                groups.append(sorted(group))

    return sorted(groups, key=lambda g: g[0])


def duplicate_groups_touching(
    samples_dir: Path,
    labels: Iterable[tuple[str, str]],
    filenames: Collection[str],
) -> list[list[str]]:
    """Grupos de duplicata que contêm ao menos um arquivo de `filenames` (S-56).

    Existe por causa do custo. `find_duplicate_groups` lê as 3.289 imagens de
    `data/samples/` -- cerca de 6 GB -- para achar **todos** os grupos, e a atribuição de
    split só precisa dos grupos em que a amostra nova entra: as antigas já têm split
    registrado, e `ensure_splits` nunca as move.

    O corte é exato, não uma aproximação. `find_duplicate_groups` já agrupa por rótulo antes
    de comparar hash -- duas imagens com posições diferentes nunca caem no mesmo grupo --,
    então basta considerar as linhas cujo rótulo alguma amostra nova também tem. Um grupo
    formado só por amostras antigas não muda nada aqui.
    """
    alvo = {str(name) for name in filenames}
    if not alvo:
        return []

    pares = [(str(name), str(fen)) for name, fen in labels]
    placements_novos = {_normalized_placement(fen) for name, fen in pares if name in alvo}
    relevantes = [(name, fen) for name, fen in pares if _normalized_placement(fen) in placements_novos]

    logger.debug(
        "Deduplicação restrita a %d de %d linhas (%d rótulos distintos entre as amostras novas).",
        len(relevantes),
        len(pares),
        len(placements_novos),
    )
    grupos = find_duplicate_groups(samples_dir, relevantes)
    return [grupo for grupo in grupos if alvo.intersection(grupo)]


def filenames_without_split(csv_path: Path, splits_path: Path) -> list[str]:
    """Rótulos que não têm split registrado, na ordem do CSV (S-56).

    São invisíveis a qualquer treino que filtre por split: `BoardFenDataset` descarta o que
    o mapa não conhece, para que amostra nova não caia por acidente no conjunto de teste.
    Sem alguém atribuindo o split, porém, "não cai por acidente" vira "não entra nunca" --
    era o estado do projeto quando isto foi escrito, com 45 amostras fora do treino.
    """
    registrados = load_splits(Path(splits_path))
    return [name for name, _fen in read_label_rows(Path(csv_path)) if name and name not in registrados]


def backup_csv(csv_path: Path) -> Path:
    """Copia o CSV para um arquivo datado antes de qualquer escrita.

    Continua exportada com este nome porque é o que o `cvoff-audit` chama; o backup em si é
    do `LabelStore` desde a S-51, para que "como se faz backup de um CSV de rótulos" tenha
    uma resposta e não três (esta, a do `migrate_labels_csv` e a do CLI).
    """
    return LabelStore(csv_path).backup()


def apply_side_to_move_fixes(csv_path: Path, report: AuditReport) -> int:
    """Reescreve as FENs cujo único problema é o lado a jogar assumido errado.

    Não altera a posição das peças, apenas o campo de turno -- que hoje é preenchido
    com "w" por padrão para todo diagrama. O treino não é afetado (usa só a colocação
    das peças); o ganho é semântico, no PGN exportado.
    """
    fixes = {issue.filename: issue.suggested_fen for issue in report.of_kind("lado-a-jogar") if issue.suggested_fen}
    if not fixes:
        return 0

    # Uma gravacao no fim, e nao uma por correcao: um `--fix` que conserta 100 rotulos
    # reescrevia o arquivo 100 vezes. E, sobretudo, uma gravacao **atomica** -- ate a S-51
    # este caminho usava `to_csv` direto no destino, o que trunca o dataset inteiro antes de
    # escrever, e o `atomic_io` prometia cobrir justamente este arquivo.
    store = LabelStore(csv_path)
    applied = 0
    with store.transaction() as tx:
        for filename, suggested in fixes.items():
            if tx.update(filename, fen=suggested):
                applied += 1
    return applied


def quarantine_fatal_labels(csv_path: Path, report: AuditReport, quarantine_path: Path) -> int:
    """Move rótulos fatalmente ilegais para um CSV de quarentena.

    Não apaga nada: as linhas saem do labels.csv e ficam preservadas para recorreção
    posterior pela UI (S-23), junto com o motivo da exclusão.
    """
    fatal = {issue.filename: issue for issue in report.of_kind("fatal")}
    if not fatal:
        return 0

    # Uma chamada para o conjunto todo, com o motivo resolvido por linha: e o que a forma de
    # funcao do `extra` existe para permitir. Uma chamada por arquivo reescreveria os dois
    # CSVs uma vez por rotulo ilegal -- e o relatorio da Fase 1 encontrou 100 deles.
    movidas = LabelStore(csv_path).move_to(
        LabelStore(quarantine_path),
        fatal.keys(),
        extra=lambda filename: {"motivo": "; ".join(fatal[filename].problems)},
    )
    return len(movidas)


def remove_duplicate_labels(csv_path: Path, report: AuditReport) -> int:
    """Remove as linhas duplicadas, mantendo o primeiro arquivo de cada grupo."""
    to_remove = {name for group in report.duplicate_groups for name in group[1:]}
    if not to_remove:
        return 0

    return LabelStore(csv_path).remove(to_remove)


def dedupe_summary(report: AuditReport, splits_path: Path) -> dict[str, Any]:
    """O que um `--dedupe` tiraria de cada split, **antes** de tirar (S-101).

    **O alarme original deste item era falso, e o registro é o que sobra dele.** A primeira
    leitura foi que `remove_duplicate_labels` encolheria `val`/`test` "sem consultar o split" e
    quebraria a comparabilidade. A primeira metade é verdade; a segunda não. Medido: dos 373
    grupos redundantes, **0** se espalham entre splits, porque `splits.group_keys` mapeia cada
    membro para `sorted(group)[0]` -- exatamente o nome que `find_duplicate_groups` mantém.
    Toda linha de `val`/`test` que sai é cópia de um representante que fica no mesmo `val`/
    `test`, e o conjunto de diagramas **distintos** de cada split não muda.

    O que muda é a **contagem**: o `test` passaria de 354 para 332 linhas. Um número medido
    depois deixa de ser comparável, por denominador, com um medido antes -- e nada avisava. É o
    mesmo problema da S-100, noutro artefato.

    Por isso esta função existe e não muda comportamento nenhum: ela grava o denominador.
    """
    splits = load_splits(Path(splits_path))
    removidos = [name for group in report.duplicate_groups for name in group[1:]]

    antes: Counter[str] = Counter(splits.values())
    saindo: Counter[str] = Counter(splits.get(name, _SEM_SPLIT) for name in removidos)
    grupos_entre_splits = [
        group
        for group in report.duplicate_groups
        if len({splits.get(name, _SEM_SPLIT) for name in group}) > 1
    ]

    por_split = {
        nome: {
            "antes": antes.get(nome, 0),
            "removidos": saindo.get(nome, 0),
            "depois": antes.get(nome, 0) - saindo.get(nome, 0),
        }
        for nome in sorted(set(antes) | set(saindo))
    }
    return {
        "csv": str(report.csv_path),
        "rows_before": report.total_rows,
        "valid_before": report.valid_rows,
        "duplicate_groups": len(report.duplicate_groups),
        "removed": len(removidos),
        "by_split": por_split,
        # Zero hoje, e é o número que refuta o alarme original -- ver o docstring. Fica no
        # arquivo para que a próxima limpeza mostre se isso deixou de ser verdade.
        "groups_across_splits": len(grupos_entre_splits),
    }


_SEM_SPLIT = "(sem split)"
"""Como uma linha sem split aparece no resumo. Não é `""` para não sumir num relatório."""


def write_dedupe_summary(summary: dict[str, Any], directory: Path, *, stamp: str) -> Path:
    """Grava o resumo em `docs/metrics/dedupe_<stamp>.json`. Devolve o caminho.

    Em `docs/metrics/` e não em `data/`: é a mesma categoria dos relatórios de campo e de
    censo -- número publicado, versionado, e que serve para explicar por que um denominador
    mudou entre duas medições.
    """
    caminho = Path(directory) / f"dedupe_{stamp}.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(caminho, summary)
    return caminho


def orphans_dir_for(samples_dir: Path) -> Path:
    """Onde os órfãos aposentados vão parar: `data/orphans/`, irmão de `data/samples/`."""
    return Path(samples_dir).parent / "orphans"


def prune_orphan_images(report: AuditReport, *, orphans_dir: Path | None = None) -> list[Path]:
    """Aposenta os PNGs que nenhuma linha do CSV referencia (S-63). Devolve os destinos.

    **Move, não apaga**, e a diferença é o critério de aceite. São ~90 MiB de imagens que
    saíram do CSV pela aba Dataset (`dataset_browser.delete_rows` apaga a linha e deixa o
    arquivo), e uma remoção às cegas é irreversível para o caso em que a linha foi apagada por
    engano -- que é justamente o caso que produz órfão. O diretório datado é o backup que o
    `backup_csv` é para o CSV.

    Um órfão cujo nome já exista no destino de uma poda anterior **não** é sobrescrito: dois
    arquivos com o mesmo nome são dois trabalhos humanos diferentes, e o segundo ganha um
    sufixo em vez de apagar o primeiro.
    """
    if not report.orphan_images:
        return []

    origem = Path(report.samples_dir)
    destino_base = Path(orphans_dir) if orphans_dir is not None else orphans_dir_for(origem)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    destino = destino_base / stamp
    destino.mkdir(parents=True, exist_ok=True)

    movidos: list[Path] = []
    for name in report.orphan_images:
        atual = origem / name
        if not atual.exists():
            continue
        alvo = destino / name
        sufixo = 1
        while alvo.exists():
            alvo = destino / f"{atual.stem}-{sufixo}{atual.suffix}"
            sufixo += 1
        shutil.move(str(atual), str(alvo))
        movidos.append(alvo)

    logger.info("%d imagem(ns) órfã(s) movida(s) para %s", len(movidos), destino)
    return movidos


def drop_missing_labels(csv_path: Path, report: AuditReport, quarantine_path: Path) -> int:
    """Tira do CSV as linhas cujo PNG sumiu, **para a quarentena** (S-63). Devolve quantas.

    O inverso do órfão, e o mais silencioso dos dois: `dataset._load_entries` avisa por
    `warnings.warn`, que ninguém vê pela GUI, então o rótulo continua no arquivo parecendo
    trabalho preservado e não treina nada.

    **Para a quarentena e não para o lixo, e a medição é que decidiu isso.** A primeira versão
    apagava a linha: "não há o que recorrigir, a imagem não existe mais". Rodado no dataset
    real, os 5 rótulos nesse estado **têm todos procedência preenchida** -- `source_pdf` e
    `source_page` --, o que quer dizer que a imagem é reextraível do livro e a FEN é trabalho
    humano que sobreviveria ao reencontro. Apagar seria jogar fora a metade cara do par para
    limpar a metade barata.
    """
    ausentes = {issue.filename for issue in report.of_kind("imagem-ausente")}
    if not ausentes:
        return 0

    movidas = LabelStore(csv_path).move_to(
        LabelStore(quarantine_path),
        ausentes,
        extra={"motivo": "imagem ausente em data/samples/"},
    )
    return len(movidas)
