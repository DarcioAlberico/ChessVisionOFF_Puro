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
    "illegal_ok",
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

ILLEGAL_OK = "1"
"""Valor da coluna `illegal_ok`: **uma pessoa confirmou** que esta posição ilegal é a certa.

**O problema que ele resolve.** Um livro de xadrez não é feito só de posições jogáveis. Um
capítulo sobre estrutura de peões desenha o esqueleto sem rei nenhum; um diagrama de final
mostra três peças; um tabuleiro vazio ilustra as coordenadas. Ler qualquer um desses
corretamente produz uma FEN que `check_position` chama de fatalmente ilegal -- e até aqui o
projeto tratava "fatalmente ilegal" e "erro de anotação" como a mesma coisa, porque em 3.313
rótulos vindos de posições completas eles de fato eram.

Não são. A regra continua valendo para o que ela foi escrita: **rei faltando porque o modelo
não viu o rei** é erro, e gravá-lo ensina o modelo a repetir o erro. O que muda é que agora
existe um jeito de dizer a diferença, e quem diz é a única entidade capaz disso -- a pessoa
que está olhando o diagrama e o PDF ao mesmo tempo. A interface pergunta antes de gravar; o
"sim" vira esta coluna.

**Por que uma coluna, e não um valor de `corrected_by`.** São eixos diferentes. Um diagrama
de estrutura pode ter chegado por qualquer um dos seis caminhos da `CORRECTED_BY_VALUES`, e
colapsar os dois campos perderia o caminho para ganhar a marca.

**O que a marca desliga**, e é por isso que ela precisa existir em vez de só a caixa de
diálogo: os três lugares que tratam ilegalidade fatal como defeito -- o descarte do
`BoardFenDataset` (que manteria a amostra fora de todo treino), a lista `fatal` da auditoria e
a quarentena do `cvoff-audit --fix` (que **tiraria a linha do arquivo**). Sem a coluna, salvar
com confirmação seria salvar num lugar onde o comando seguinte apaga.

Ela é gravada pela mesma escrita que grava a FEN, e some sozinha: regravar o rótulo já legal
limpa a célula (ver `dataset_browser.update_row`), porque a marca descreve a FEN que está na
linha e não um perdão permanente para o arquivo.
"""

OCR_ACEITO = "ocr-aceito"
OCR_CORRIGIDO = "ocr-corrigido"
FILA_REVISAO = "fila-revisao"
DATASET_RECORRIGIDO = "dataset-recorrigido"
NET_REMOTO = "net-remoto"
SEGUNDA_OPINIAO = "segunda-opiniao"

CORRECTED_BY_VALUES: tuple[str, ...] = (
    OCR_ACEITO,
    OCR_CORRIGIDO,
    FILA_REVISAO,
    DATASET_RECORRIGIDO,
    NET_REMOTO,
    SEGUNDA_OPINIAO,
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
| `segunda-opiniao` | a FEN veio do segundo leitor **local** da S-66 |

`segunda-opiniao` é separado de `net-remoto` porque a diferença é justamente a que a coluna
existe para registrar: um é uma requisição a um host de terceiro, o outro é um modelo rodando
nesta máquina. Colapsá-los faria o CSV afirmar uma chamada de rede que nunca houve.

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
    from_second_opinion: bool = False,
    from_queue: bool = False,
    from_dataset: bool = False,
    read_placement: str = "",
    saved_placement: str = "",
) -> str:
    """Por qual caminho esta amostra chegou ao rótulo (S-52, S-66).

    Mora aqui e não no painel pela regra que organizou a Fase 6: o que dá para testar não
    fica na janela. São seis caminhos e uma ordem de precedência, e os dois merecem um teste
    que não precise abrir uma janela do Tk para rodar.

    A ordem vai do mais específico para o mais genérico. Os quatro primeiros são caminhos
    **declarados** -- quem chama sabe que veio da Net, do segundo leitor local, da fila ou da
    aba Dataset --, e só quando nenhum deles vale a resposta depende de comparar o que o
    modelo leu com o que está sendo salvo.

    `from_net` vem antes de `from_second_opinion` porque é o mais forte dos dois: se a imagem
    chegou a sair da máquina, é isso que a linha precisa registrar, mesmo que um segundo
    leitor local tenha opinado depois.

    Essa comparação é entre campos de peças, e não o `edited_by_hand` da `RecognizedDiagram`:
    aquele só é marcado pela edição por clique, e digitar uma FEN nova no campo de texto é
    correção do mesmo jeito. O que interessa é se o rótulo salvo difere do que o modelo leu.
    """
    if from_net:
        return NET_REMOTO
    if from_second_opinion:
        return SEGUNDA_OPINIAO
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
    illegal_ok: str = ""
    """Marca da posição ilegal deliberada. Ver `ILLEGAL_OK` -- leia por `illegal_accepted`."""

    @property
    def illegal_accepted(self) -> bool:
        """Uma pessoa confirmou que esta posição ilegal é a leitura certa do diagrama.

        Aceita mais de uma grafia porque a coluna é texto num CSV que gente edita à mão: um
        `sim` digitado no lugar de `1` significa a mesma coisa, e lê-lo como "não" desfaria a
        decisão de quem digitou -- que é exatamente o desfazer que esta coluna existe para
        impedir.
        """
        return self.illegal_ok.strip().lower() in ("1", "true", "sim", "yes", "x")

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


def label_origins(csv_path: Path) -> dict[str, tuple[str, str, str]]:
    """`{arquivo: (source_pdf, source_page, source_diagram)}` para o agrupamento da S-98.

    A tripla é a chave de "é o mesmo diagrama impresso", e ela é **exata**: não depende de
    limiar de imagem, e por isso pega o caso que o guarda de dHash não pega -- a mesma página
    reextraída com recorte deslocado, que é o que acontece ao revarrer um livro depois de a
    detecção mudar.

    Os valores saem como texto e **como estão no CSV**, sem conversão de base: aqui a tripla
    serve só de chave de igualdade, e converter para depois comparar seria trabalho que só
    poderia introduzir divergência com `saved_diagrams_by_page`, que converte porque a
    interface conta em base 0.

    Linha sem `source_pdf` ou sem `source_page` entra com a tripla vazia e o chamador a
    descarta -- são 84,1% do acervo, e inventar procedência seria pior que não ter.
    """
    return {
        entry.filename: (entry.source_pdf.strip(), entry.source_page.strip(), entry.source_diagram.strip())
        for entry in LabelStore(csv_path).read()
        if entry.filename
    }


def saved_diagrams_by_page(
    entries: Iterable[DatasetEntry], source_pdf: str
) -> dict[int, set[int]]:
    """Quais diagramas de cada página deste livro já têm amostra salva (S-71).

    Devolve `{índice da página: {índices dos diagramas}}`, os dois **em base 0** -- que é como
    a interface conta. O CSV guarda os dois em base 1, porque `source_page` é o número que o
    usuário vê no leitor de PDF (ver `RecognitionOrigin.sample_fields`) e `source_diagram` é o
    número que aparece no seletor "Selecionado". A conversão fica aqui, num lugar só.

    Serve para o visualizador pintar de verde o que já foi salvo -- inclusive **antes** de
    rodar o OCR na página, que é quando a informação vale mais: ela responde "onde eu parei
    neste livro?" sem custar uma leitura.

    Linha sem procedência é ignorada, e não é caso raro: 98,6% do acervo é anterior à S-19 e
    tem `source_page` vazio. Ignorar é o único tratamento honesto -- não dá para inventar de
    que página veio uma amostra que não declarou.

    `source_pdf` é o **nome** do arquivo, não o caminho: é o que a S-19 grava.
    """
    por_pagina: dict[int, set[int]] = {}
    alvo = str(source_pdf).strip()
    if not alvo:
        return por_pagina

    for entry in entries:
        if entry.source_pdf.strip() != alvo:
            continue
        try:
            pagina = int(float(entry.source_page)) - 1
            diagrama = int(float(entry.source_diagram)) - 1
        except (TypeError, ValueError):
            continue
        if pagina < 0 or diagrama < 0:
            continue
        por_pagina.setdefault(pagina, set()).add(diagrama)
    return por_pagina


@dataclass(frozen=True)
class SavedSample:
    """A procedência de uma amostra recém-gravada, **na contagem da interface** (S-116).

    Base 0 nos dois índices, como `saved_diagrams_by_page` devolve -- e não como o CSV guarda.
    Existe para que a janela saiba o que ela mesma acabou de escrever sem ir perguntar ao
    arquivo: era o último custo do `Ctrl+S`, e ele cresce com o `labels.csv`.
    """

    source_pdf: str
    """O **nome** do arquivo, não o caminho: é o que a S-19 grava e o que o índice compara."""

    page_index: int
    diagram_index: int


def note_saved_diagram(
    por_pagina: dict[int, set[int]], saved: SavedSample, *, source_pdf: str
) -> bool:
    """Marca no índice de "já salvo" a amostra que a janela acabou de gravar. Devolve se entrou.

    **É o corte 2 da S-116**, e o que ele substitui é uma releitura do `labels.csv` inteiro
    (30,9 ms sobre 3.936 linhas, e crescendo) para descobrir uma linha que o próprio processo
    acabou de escrever.

    Ela mora aqui, e não no painel, pela mesma razão de `saved_diagrams_by_page`: a conversão
    entre a contagem do CSV e a da tela tem um lugar só, e as duas funções produzem o mesmo
    índice -- é isso que um teste pode afirmar, e afirma.

    Amostra de outro livro não entra: o índice é do que está aberto. Amostra sem procedência
    também não chega aqui, porque quem a monta devolve `None` antes (ver `_saved_sample`).
    """
    if not saved.source_pdf.strip() or saved.source_pdf.strip() != str(source_pdf).strip():
        return False
    if saved.page_index < 0 or saved.diagram_index < 0:
        return False
    por_pagina.setdefault(saved.page_index, set()).add(saved.diagram_index)
    return True


def pages_with_training_samples(
    entries: Iterable[DatasetEntry], splits: Mapping[str, str]
) -> dict[tuple[str, int], int]:
    """`{(livro, página em base 0): quantas amostras de treino}` (S-97).

    **Por que isto existe.** O conjunto de campo da S-41 nasceu porque o split de teste não
    representa a entrada do produto -- *"não é o modelo que está ruim, é o conjunto de teste
    que não representa a entrada"*. Mas nada impedia que uma página do conjunto de campo fosse
    também uma página de que há amostra rotulada em `train`, e medido em 2026-08-16 são **7 de
    39 diagramas anotados, 17,9%**: `Karpov p80` (6) e `1937 Kemeri` p187 (1).

    **A ressalva, e ela muda a leitura.** Isto não diz que o checkpoint em uso viu aquela
    página -- diz que **o próximo a ser treinado sobre estes splits verá**. Das nove amostras
    envolvidas hoje, oito são posteriores ao `piece_classifier.pt` de 2026-08-09. É uma
    armadilha que fecha no próximo retreino, e por isso o alerta vale mais agora que depois.

    Só conta `train`: amostra em `val`/`test` na mesma página é outro assunto, e o modelo não
    aprende com ela. Linha sem procedência é ignorada, como em `saved_diagrams_by_page`, e são
    84,1% do acervo -- o alcance deste alerta é o das amostras que declaram de onde vieram.
    """
    por_pagina: dict[tuple[str, int], int] = {}
    for entry in entries:
        livro = entry.source_pdf.strip()
        if not livro or splits.get(entry.filename) != "train":
            continue
        try:
            pagina = int(float(entry.source_page)) - 1
        except (TypeError, ValueError):
            continue
        if pagina < 0:
            continue
        chave = (livro, pagina)
        por_pagina[chave] = por_pagina.get(chave, 0) + 1
    return por_pagina


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
