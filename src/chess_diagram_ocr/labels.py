"""A única porta para o `data/labels.csv` (S-51).

**O problema, medido.** O arquivo era lido e escrito com pandas em cinco módulos --
`dataset.py`, `audit.py`, `dataset_browser.py`, `splits.py` e `cli/migrate_labels.py` --, e
cada um conhecia o esquema da S-19 por conta própria. `LABEL_COLUMNS` morava em `dataset.py`
e `_write_labels` era privado dele, então `dataset_browser.update_row` importava um `_nome`
de outro módulo e o `audit.py` reimplementava a gravação. São 3.313 rótulos de trabalho
humano acumulado atrás de cinco portas que precisavam concordar sobre ordem de coluna,
`fillna("")` e `lineterminator` sem que nada garantisse que concordassem.

**Elas não concordavam.** Três caminhos do `audit.py` -- `apply_side_to_move_fixes`,
`quarantine_fatal_labels` e `remove_duplicate_labels`, todos alcançáveis por
`cvoff-audit --fix` -- gravavam com `df.to_csv(csv_path)` direto no destino. Duas
consequências, e as duas anulavam garantias que a documentação afirmava:

- **Não era escrita atômica.** O docstring do `atomic_io` lista o `labels.csv` entre os três
  arquivos que ele protege. Estes três caminhos passavam por fora: `to_csv` trunca o destino
  antes de escrever, e o que estava sendo truncado era o dataset inteiro.
- **Não normalizavam os inteiros da S-58.** `cvoff-audit --fix` reintroduzia o `20.0` que a
  S-58 tinha acabado de corrigir, e o arquivo voltava a ter os dois formatos.

**Por que `csv` da biblioteca padrão e não pandas.** A S-58 existe porque o pandas infere
tipo: `source_page` tem célula vazia em 98,6% das linhas, a coluna virava `float64`, e `20`
voltava como `20.0`. A correção de lá foi `dtype=str, keep_default_na=False` em toda leitura
-- uma disciplina que precisava ser lembrada em cinco lugares. Aqui não há o que lembrar:
todas as colunas do esquema **são** texto, e o `csv.DictReader` nunca leu outra coisa. O
defeito deixa de ser evitado e passa a não existir.

`_as_integer_text` continua na escrita, e continua pelo mesmo motivo da S-58: um arquivo que
já tem `20.0` gravado converge sozinho na próxima gravação, sem comando de migração.

**O que esta classe acrescenta ao que existia.** `transaction()` -- hoje a aba Dataset
regrava as 3.313 linhas a cada correção. E um dono para o esquema: o campo novo que a S-52
quer entra em um lugar, e o dia em que 3.313 virar 30.000, trocar CSV por SQLite é reescrever
uma classe.
"""

from __future__ import annotations

import csv
import io
import logging
import os
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

from .atomic_io import atomic_write_bytes

logger = logging.getLogger(__name__)

LABEL_COLUMNS: tuple[str, ...] = (
    "filename",
    "fen",
    "side_to_move",
    "source_pdf",
    "source_page",
    "source_diagram",
    "detection_source",
    "created_at",
    "corrected_by",
)
"""Esquema do `labels.csv` a partir da S-19. Só `filename` e `fen` são obrigatórios.

O esquema antigo (`filename,fen`) continua carregando: coluna ausente vira valor vazio. São
3.195 rótulos existentes, e quebrá-los para ganhar colunas seria o pior negócio possível.

`side_to_move` é o campo que motivou o resto. Sem ele o dataset perde a única informação que
o PDF dava de graça e que a imagem do tabuleiro não contém -- e foi essa perda que fez
`_normalize_fen` completar 3.244 rótulos com `w` fixo. As colunas de origem (`source_*`)
existem para o que a Fase 1 já pediu e não pôde fazer: agrupar o split por livro (S-07),
auditar por fonte e voltar ao PDF para recortar de novo.
"""

REQUIRED_COLUMNS: frozenset[str] = frozenset({"filename", "fen"})

OCR_ACEITO = "ocr-aceito"
OCR_CORRIGIDO = "ocr-corrigido"
FILA_REVISAO = "fila-revisao"
DATASET_RECORRIGIDO = "dataset-recorrigido"
NET_REMOTO = "net-remoto"

CORRECTED_BY_VALUES: tuple[str, ...] = (
    OCR_ACEITO,
    OCR_CORRIGIDO,
    FILA_REVISAO,
    DATASET_RECORRIGIDO,
    NET_REMOTO,
)
"""Como a amostra chegou ao rótulo -- a coluna `corrected_by` (S-52).

**O valor útil não é o nome do usuário.** A coluna está no esquema desde a S-19, está no
`LABEL_COLUMNS`, está no CSV e está na assinatura de `append_training_sample`, e estava
preenchida em **0 de 3.313 linhas**. Uma coluna que ninguém escreve é pior que nenhuma
coluna, porque parece um dado.

Registrar o caminho responde a uma pergunta que hoje ninguém pode fazer: *as amostras que
vieram corrigidas à mão treinam melhor que as aceitas direto do OCR?* Se treinam, a fila de
revisão da S-22 vale mais do que se supõe; se não treinam, o esforço humano está indo para o
lugar errado. Nenhuma das duas respostas é obtenível de um `corrected_by` vazio.

| valor | quando |
|---|---|
| `ocr-aceito` | o modelo leu, o humano conferiu e salvou sem mexer |
| `ocr-corrigido` | o humano mudou pelo menos uma casa antes de salvar |
| `fila-revisao` | veio da fila de aprendizado ativo (S-22) |
| `dataset-recorrigido` | rótulo que já existia e foi regravado pela aba Dataset (S-23) |
| `net-remoto` | a FEN veio do serviço externo da S-32 |

Não é enumeração fechada em código -- `append_training_sample` aceita qualquer string, e um
chamador futuro pode ter um caminho que estes cinco não descrevem. É vocabulário, não
validação: fechá-lo obrigaria a mexer aqui para acrescentar um caminho, e o custo de um valor
desconhecido é um agrupamento a mais num relatório.
"""

SCHEMA_LEGACY = 1
"""`filename,fen` -- o esquema do primeiro commit até a S-19."""

SCHEMA_CURRENT = 2
"""O esquema da S-19, com procedência e lado a jogar."""

_INTEGER_TEXT_COLUMNS: tuple[str, ...] = ("source_page", "source_diagram")
"""Colunas que guardam inteiro em forma de texto. Ver `_as_integer_text`."""

LabelRow = dict[str, str]
"""Uma linha crua, com as colunas extras preservadas.

Existe por causa da quarentena, que acrescenta `motivo` ao esquema. Uma porta única que
descartasse coluna desconhecida perderia o motivo da exclusão na primeira gravação.
"""


def label_route(
    *,
    from_net: bool = False,
    from_queue: bool = False,
    from_dataset: bool = False,
    read_placement: str = "",
    saved_placement: str = "",
) -> str:
    """Por qual caminho esta amostra chegou ao rótulo (S-52).

    Mora aqui e não no painel pela regra que organizou a Fase 6: o que dá para testar não
    fica na janela. São cinco caminhos e uma ordem de precedência, e os dois merecem um teste
    que não precise abrir uma janela do Tk para rodar.

    A ordem vai do mais específico para o mais genérico. Os três primeiros são caminhos
    **declarados** -- quem chama sabe que veio da Net, da fila ou da aba Dataset --, e só
    quando nenhum deles vale a resposta depende de comparar o que o modelo leu com o que está
    sendo salvo.

    Essa comparação é entre campos de peças, e não o `edited_by_hand` da `RecognizedDiagram`:
    aquele só é marcado pela edição por clique, e digitar uma FEN nova no campo de texto é
    correção do mesmo jeito. O que interessa é se o rótulo salvo difere do que o modelo leu.
    """
    if from_net:
        return NET_REMOTO
    if from_queue:
        return FILA_REVISAO
    if from_dataset:
        return DATASET_RECORRIGIDO
    lido = read_placement.split(" ")[0]
    salvo = saved_placement.split(" ")[0]
    return OCR_CORRIGIDO if salvo != lido else OCR_ACEITO


def _as_integer_text(value: object) -> str:
    """`"20.0"` → `"20"`, preservando vazio e qualquer coisa que não seja número.

    O que não parece número passa intacto -- não é papel desta função decidir que um valor
    inesperado é lixo.
    """
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else text


@dataclass(frozen=True)
class DatasetEntry:
    """Uma linha do `labels.csv` no esquema da S-19, já limpa."""

    filename: str
    fen: str
    side_to_move: str = ""
    """`w`, `b` ou vazio. Redundante com a FEN de propósito -- ver `resolved_side_to_move`."""

    source_pdf: str = ""
    source_page: str = ""
    source_diagram: str = ""
    detection_source: str = ""
    created_at: str = ""
    corrected_by: str = ""

    @property
    def resolved_side_to_move(self) -> str:
        """A coluna manda; a FEN é o reserva.

        As duas são escritas juntas e não deviam divergir, mas a coluna carrega o que a
        legenda do PDF disse -- que numa posição legal dos dois jeitos é informação que a FEN
        sozinha não tem como recuperar. Se um dia divergirem, a mais informativa vence.
        """
        if self.side_to_move in ("w", "b"):
            return self.side_to_move
        parts = self.fen.split()
        return parts[1] if len(parts) > 1 and parts[1] in ("w", "b") else ""

    def to_row(self) -> LabelRow:
        return {campo.name: str(getattr(self, campo.name)) for campo in fields(self)}

    @classmethod
    def from_row(cls, row: LabelRow) -> DatasetEntry:
        return cls(**{campo.name: _clean(row.get(campo.name, "")) for campo in fields(cls)})


def _clean(value: object) -> str:
    """Valor textual de uma célula. `None` e o `"nan"` herdado viram string vazia.

    O `"nan"` não é hipótese acadêmica: é o que sobrava de um CSV lido pelo pandas sem
    `keep_default_na=False`, e ele existe gravado em arquivos antigos.
    """
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


class LabelStore:
    """A única porta para um CSV de rótulos. Escrita sempre atômica (S-25).

    Serve tanto ao `labels.csv` quanto ao CSV de quarentena, que é o mesmo esquema mais uma
    coluna. Não valida FEN nem legalidade: isso é decisão de quem grava, e `dataset.py` e
    `dataset_browser.py` a tomam de formas diferentes e certas para cada caso.
    """

    def __init__(self, csv_path: Path) -> None:
        self.path = Path(csv_path)
        self._pending: list[LabelRow] | None = None
        """Linhas em edição dentro de uma `transaction`. `None` fora de uma."""

    def __repr__(self) -> str:
        return f"LabelStore({str(self.path)!r})"

    # ------------------------------------------------------------------------- leitura

    def exists(self) -> bool:
        return self.path.exists()

    @property
    def schema_version(self) -> int:
        """Qual esquema o arquivo tem hoje. Arquivo ausente conta como o atual.

        Serve para uma pergunta que a S-52 vai fazer -- *este arquivo tem as colunas de
        procedência?* -- sem que ninguém precise reabrir o CSV para descobrir.
        """
        if not self.path.exists():
            return SCHEMA_CURRENT
        return SCHEMA_CURRENT if set(LABEL_COLUMNS).issubset(self.columns()) else SCHEMA_LEGACY

    def columns(self) -> tuple[str, ...]:
        """As colunas que o arquivo tem, na ordem em que estão nele."""
        if not self.path.exists():
            return LABEL_COLUMNS
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), [])
        return tuple(name.strip() for name in header)

    def read_rows(self) -> list[LabelRow]:
        """As linhas cruas, com as colunas extras preservadas."""
        if self._pending is not None:
            return [dict(row) for row in self._pending]
        return self._load_rows()

    def read(self) -> list[DatasetEntry]:
        """As linhas no esquema da S-19. Coluna extra não aparece aqui -- ver `read_rows`."""
        return [DatasetEntry.from_row(row) for row in self.read_rows()]

    def read_pairs(self) -> list[tuple[str, str]]:
        """Os pares `(arquivo, FEN)`, na ordem do arquivo.

        É o que a auditoria e `training.resolve_splits` precisam, e montar 3.313
        `DatasetEntry` para jogar sete campos fora seria trabalho por nada.
        """
        return [(_clean(row.get("filename")), _clean(row.get("fen"))) for row in self.read_rows()]

    def _load_rows(self) -> list[LabelRow]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            colunas = reader.fieldnames or []
            if not REQUIRED_COLUMNS.issubset(colunas):
                raise ValueError(
                    f"{self.path} precisa das colunas {set(REQUIRED_COLUMNS)}. Encontradas: {set(colunas)}"
                )
            # `restval`/`restkey` do DictReader deixariam `None` e listas soltas entrarem no
            # dicionario; normalizar aqui e o que garante que toda celula seja `str`.
            return [{nome: _clean(row.get(nome)) for nome in colunas} for row in reader]

    # -------------------------------------------------------------------------- escrita

    def append(self, entry: DatasetEntry | LabelRow) -> None:
        """Acrescenta uma linha ao fim, preservando a ordem do arquivo."""
        row = entry.to_row() if isinstance(entry, DatasetEntry) else dict(entry)
        rows = self._working_rows()
        rows.append(row)
        self._commit(rows)

    def update(self, filename: str, **fields_to_set: str) -> bool:
        """Regrava campos de uma amostra. `False` quando ela não está no arquivo.

        Campo desconhecido do esquema é aceito de propósito: a quarentena grava `motivo`, e
        recusá-lo obrigaria a um segundo caminho de escrita -- que é exatamente o que este
        módulo existe para não ter.
        """
        alvo = filename.strip()
        rows = self._working_rows()
        encontrado = False
        for row in rows:
            if _clean(row.get("filename")) != alvo:
                continue
            row.update({nome: _clean(valor) for nome, valor in fields_to_set.items()})
            encontrado = True

        if encontrado:
            self._commit(rows)
        return encontrado

    def remove(self, filenames: Collection[str]) -> int:
        """Remove as linhas cujos nomes estiverem na coleção. Devolve quantas saíram."""
        alvos = {name.strip() for name in filenames if name.strip()}
        if not alvos:
            return 0

        rows = self._working_rows()
        mantidas = [row for row in rows if _clean(row.get("filename")) not in alvos]
        removidas = len(rows) - len(mantidas)
        if removidas:
            self._commit(mantidas)
        return removidas

    def rewrite(self, entries: Sequence[DatasetEntry] | Sequence[LabelRow]) -> None:
        """Substitui o conteúdo inteiro. É o caminho da migração, não do uso normal."""
        self._commit([entry.to_row() if isinstance(entry, DatasetEntry) else dict(entry) for entry in entries])

    def move_to(
        self,
        destination: LabelStore,
        filenames: Collection[str],
        *,
        extra: Mapping[str, str] | Callable[[str], Mapping[str, str]] | None = None,
        drop: Collection[str] = (),
    ) -> list[LabelRow]:
        """Tira linhas daqui e as põe lá, com colunas extras opcionais. Devolve o que moveu.

        É a quarentena, e ela é **uma** operação: as linhas saírem daqui sem chegarem lá é
        perder rótulo, e chegarem lá sem sair daqui é duplicá-lo. A ordem escolhida -- gravar
        o destino antes de reescrever a origem -- é a que erra para o lado recuperável: uma
        falha entre as duas deixa a linha nos dois arquivos, e não em nenhum.

        `extra` aceita um mapa fixo ou uma função do nome do arquivo, porque os dois
        chamadores querem coisas diferentes e os dois estão certos: a quarentena pela UI tem
        um motivo só para a seleção inteira, e a da auditoria tem os problemas de legalidade
        **daquela** linha. Sem a forma de função, o segundo caso viraria uma chamada por
        arquivo -- e cada chamada é uma reescrita dos dois CSVs.

        `drop` é o caminho de volta. Restaurar da quarentena tem de **remover** a coluna
        `motivo`, e não esvaziá-la: uma coluna vazia continua sendo uma coluna, e o
        `labels.csv` ganharia um campo cujo valor é mentira para 3.313 linhas e verdade para
        nenhuma. Só some de fato quando some de todas as linhas -- ver `label_columns_for`.
        """
        alvos = {name.strip() for name in filenames if name.strip()}
        if not alvos:
            return []

        rows = self._working_rows()
        movidas = [dict(row) for row in rows if _clean(row.get("filename")) in alvos]
        if not movidas:
            return []

        for row in movidas:
            adicional = extra(_clean(row.get("filename"))) if callable(extra) else (extra or {})
            row.update({nome: _clean(valor) for nome, valor in adicional.items()})
            for nome in drop:
                row.pop(nome, None)

        destination.extend(movidas)
        self._commit([row for row in rows if _clean(row.get("filename")) not in alvos])
        return movidas

    def extend(self, rows: Iterable[LabelRow]) -> None:
        """Acrescenta várias linhas de uma vez."""
        novas = [dict(row) for row in rows]
        if not novas:
            return
        atuais = self._working_rows()
        atuais.extend(novas)
        self._commit(atuais)

    # ---------------------------------------------------------------------- transação

    @contextmanager
    def transaction(self) -> Iterator[LabelStore]:
        """Uma única gravação no fim, em vez de uma por operação.

        A aba Dataset da S-23 regrava as 3.313 linhas a cada correção; corrigir vinte
        amostras são vinte reescritas do arquivo inteiro. Aqui é uma.

        **Exceção descarta tudo.** Não é banco de dados -- não há journal, e o que se garante
        é o que a escrita atômica já garante: ou o arquivo novo inteiro, ou o antigo intacto.
        Manter as alterações parciais de um bloco que levantou seria pior que descartá-las,
        porque ninguém sabe em que ponto ele parou.
        """
        if self._pending is not None:
            raise RuntimeError("Já existe uma transação aberta neste LabelStore.")

        self._pending = self._load_rows()
        try:
            yield self
        except Exception:
            self._pending = None
            logger.warning("Transação em %s descartada por exceção; o arquivo não foi tocado.", self.path)
            raise
        else:
            rows, self._pending = self._pending, None
            self._write_rows(rows)

    # -------------------------------------------------------------------------- backup

    def backup(self) -> Path:
        """Copia o arquivo para um irmão datado. Levanta se não há o que copiar."""
        if not self.path.exists():
            raise FileNotFoundError(f"CSV de rótulos não encontrado: {self.path}")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        destino = self.path.with_name(f"{self.path.name}.bak-{stamp}")
        destino.write_bytes(self.path.read_bytes())
        logger.info("Backup do CSV de rótulos em %s", destino)
        return destino

    # ------------------------------------------------------------------------- interno

    def _working_rows(self) -> list[LabelRow]:
        return self._pending if self._pending is not None else self._load_rows()

    def _commit(self, rows: list[LabelRow]) -> None:
        if self._pending is not None:
            self._pending = rows
            return
        self._write_rows(rows)

    def _write_rows(self, rows: Sequence[LabelRow]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(self.path, render_csv(rows).encode("utf-8"))


def label_columns_for(rows: Sequence[LabelRow]) -> tuple[str, ...]:
    """As colunas do esquema, seguidas das extras na ordem em que apareceram.

    O esquema primeiro e sempre inteiro: um arquivo escrito a partir de linhas que não têm
    `corrected_by` continua tendo a coluna, vazia. Perder coluna do esquema porque nenhuma
    linha a preenchia faria o arquivo oscilar de forma entre gravações.
    """
    extras: list[str] = []
    for row in rows:
        for nome in row:
            if nome not in LABEL_COLUMNS and nome not in extras:
                extras.append(nome)
    return (*LABEL_COLUMNS, *extras)


def render_csv(rows: Sequence[LabelRow]) -> str:
    """O texto do CSV, byte a byte como o `_write_labels` da S-25/S-58 o produzia.

    Separada da gravação para poder ser comparada em teste com a saída do pandas -- que é o
    que garante que trocar a implementação não mexeu em 3.313 linhas versionadas.
    """
    colunas = label_columns_for(rows)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(colunas),
        lineterminator=os.linesep,
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        completa = {nome: _clean(row.get(nome, "")) for nome in colunas}
        for nome in _INTEGER_TEXT_COLUMNS:
            completa[nome] = _as_integer_text(completa[nome])
        writer.writerow(completa)
    return buffer.getvalue()
