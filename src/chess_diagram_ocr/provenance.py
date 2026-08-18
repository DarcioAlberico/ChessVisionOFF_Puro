"""Recuperar a procedência dos rótulos órfãos, por hash perceptual (S-52).

**O problema, medido no `data/labels.csv`.** `source_pdf` e `source_page` estão preenchidas
em **46 de 3.313 linhas (1,4%)**. A S-19 criou as colunas e a S-31 as preenche a partir da
`RecognitionOrigin`, mas só para as amostras salvas depois dela; as 3.195 anteriores foram
gravadas quando a origem não era registrada, e a `migrate_labels` diz corretamente que não há
como inventá-la.

Três consequências que não são cosméticas, e a primeira é a que paga o item:

1. **A S-07 não pode agrupar o split por livro.** Hoje o split é por hash do nome do arquivo,
   agrupado por diagrama duplicado. Agrupar por livro -- o que impede o teste de medir "quão
   bem o modelo lê *este* livro" em vez de "quão bem ele generaliza" -- precisa de
   `source_pdf`, e 98,6% não tem.
2. **A auditoria por fonte de detecção não tem dados**: 40 linhas em 3.313.
3. Voltar ao PDF para recortar de novo, que a S-19 lista como motivo das colunas, é
   impossível para 98,6% do dataset.

**A procedência é recuperável, e por um caminho que o projeto já tem.** Cada PNG de
`data/samples/` é o recorte de um diagrama que está em algum dos 27 PDFs do acervo. Casar os
dois é comparação de imagem, e `audit.dhash` já faz exatamente isso para achar duplicatas --
inclusive com a resolução de 16×16 que a auditoria mediu ser necessária (um dHash 8×8 sobre
diagrama de xadrez é degenerado: o downsample alinha com a grade e o hash captura o padrão
xadrezado, que é igual em todos).

**O item reporta a taxa; não promete 100%.** Não casam, por construção:

- amostra vinda de imagem local ou de recorte de área feito à mão (a S-20 permite os dois);
- amostra de um PDF que saiu do acervo;
- amostra cujo enquadramento mudou -- o detector de hoje não é o de quando ela foi salva, e
  a S-38a mudou justamente o refino do recorte.

O último não é hipótese: é o custo previsível de comparar um recorte de 2026-07 com o que o
detector produz em 2026-08. Por isso o relatório traz o **histograma de distância**, e não só
a contagem acima do limiar: é ele que diz se o limiar está no lugar certo ou se está cortando
casamento bom.

**O custo, e por que o índice mora em disco.** Construí-lo é detectar diagramas em ~12 mil
páginas: a S-61 mediu 0,043 s de render mais 0,562 s de detecção por página do `Karpov`, o
que dá horas de CPU para o acervo. O índice é JSONL incremental, uma linha por diagrama, com
um cabeçalho por livro -- então dá para construí-lo um livro por vez, e uma interrupção custa
o livro corrente e não a varredura inteira.

**O casamento é vetorizado, e precisa ser.** 3.195 amostras contra dezenas de milhares de
diagramas são centenas de milhões de distâncias de Hamming. Em Python puro (`bin(a ^
b).count("1")`, que é o que o `audit` usa para comparar algumas centenas) isso levaria horas;
com os hashes empacotados numa matriz `uint8` e a contagem de bits por tabela de consulta,
leva segundos.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .atomic_io import atomic_write_bytes, read_image
from .audit import DUPLICATE_HASH_SIZE, dhash
from .config import DEFAULT_MAX_BOARDS, PROJECT_ROOT
from .labels import LabelStore

logger = logging.getLogger(__name__)

DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "provenance_index.jsonl"

DEFAULT_DPI = 220
"""O mesmo DPI do pipeline. Não é escolha livre: o índice precisa ver o diagrama como o
detector o viu quando a amostra foi salva, e mudar o DPI muda o recorte."""

DEFAULT_MAX_DISTANCE = 6
"""Distância de Hamming máxima, em 256 bits, para aceitar um casamento.

A auditoria usa 3 para "é a mesma imagem", que é o critério certo para achar duplicata: ali
um falso positivo apaga um rótulo. Aqui um falso positivo escreve uma procedência errada, que
é ruim mas reparável, e um falso **negativo** deixa a linha órfã para sempre. O limiar
afrouxa por isso.

**Medido em 2026-08-09, e o resultado pede cautela.** Duas sondas, as duas contra um índice
de 11 diagramas das 20 primeiras páginas do `1937 Kemeri`:

| sonda | resultado |
|---|---|
| 12 amostras **com procedência gravada** daquelas páginas | 12 de 12, todas a distância **0**, todas na página certa |
| os **3.195 órfãos** contra o mesmo índice | **0** casamentos; o impostor mais próximo a **7 bits** |

O acerto de 12 em 12 valida a cadeia inteira -- hash, índice, casamento e página. O `0` de
distância era esperado: essas amostras foram salvas pelo caminho `embedded` com o detector de
hoje, então o recorte é o mesmo. Um recorte deslocado em 6 px num tabuleiro de 800 custa
**6 bits** (medido em `tests/test_provenance.py`), que é exatamente este limiar.

**E é aí que está o aperto:** o casamento verdadeiro reenquadrado chega a 6, e o impostor mais
próximo estava a 7. A folga é de **um bit**. Pior: 11 diagramas de índice é o caso mais fácil
possível -- com o acervo inteiro (dezenas de milhares de entradas) o impostor mais próximo só
pode chegar mais perto, nunca mais longe.

Por isso o `cvoff-provenance` **não grava por padrão**: ele relata a taxa e o histograma, e
gravar é um segundo comando. O número aqui é um ponto de partida conferível, não uma
constante confiável.
"""

INDEX_VERSION = 1

_POPCOUNT = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(axis=1).astype(np.uint16)
"""Bits em 1 de cada byte, pré-calculado. É o que torna o casamento vetorizado."""


@dataclass(frozen=True)
class IndexEntry:
    """Um diagrama encontrado num PDF do acervo, com o hash da imagem dele."""

    source_pdf: str
    source_page: int
    """Número **impresso na coluna do CSV**, que é 1-based -- ver `append_training_sample`."""

    source_diagram: int
    detection_source: str
    hash_hex: str
    """dHash de 256 bits em hexadecimal. Texto porque o índice é JSONL e um int de 256 bits
    não sobrevive a um round-trip de JSON em todo leitor."""

    def to_dict(self) -> dict[str, object]:
        return {
            "source_pdf": self.source_pdf,
            "source_page": self.source_page,
            "source_diagram": self.source_diagram,
            "detection_source": self.detection_source,
            "hash": self.hash_hex,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> IndexEntry:
        return cls(
            source_pdf=str(raw.get("source_pdf", "")),
            source_page=int(str(raw.get("source_page", 0))),
            source_diagram=int(str(raw.get("source_diagram", 0))),
            detection_source=str(raw.get("detection_source", "")),
            hash_hex=str(raw.get("hash", "")),
        )


@dataclass(frozen=True)
class ProvenanceMatch:
    """Uma amostra casada com um diagrama do acervo."""

    filename: str
    source_pdf: str
    source_page: int
    source_diagram: int
    detection_source: str
    distance: int
    """Hamming do dHash. 0 é idêntico; acima de ~8 não é a mesma imagem."""

    runner_up: int | None = None
    """Distância do **segundo** melhor casamento, quando há outro diagrama no acervo.

    Existe porque a distância sozinha não diz se o casamento é seguro. Um diagrama a 4 bits
    do melhor e a 5 do segundo é ambíguo mesmo estando abaixo do limiar -- e é exatamente o
    caso do mesmo diagrama impresso em dois livros, que este acervo tem.
    """

    @property
    def is_ambiguous(self) -> bool:
        """O segundo lugar está perto demais para o primeiro significar alguma coisa."""
        return self.runner_up is not None and self.runner_up - self.distance < AMBIGUITY_MARGIN


AMBIGUITY_MARGIN = 4
"""Bits de folga que o melhor casamento precisa ter sobre o segundo para valer.

Medido pela auditoria e registrado no `audit.DUPLICATE_HASH_SIZE`: duas renderizações
diferentes da **mesma** posição, em livros distintos, ficam por volta de 10 bits uma da
outra. Uma folga de 4 separa "é este diagrama" de "é um dos dois, e não sei qual".
"""


@dataclass
class ProvenanceIndex:
    """O índice inteiro, em memória, com os hashes empacotados para comparação vetorizada."""

    entries: list[IndexEntry] = field(default_factory=list)
    dpi: int = DEFAULT_DPI
    hash_size: int = DUPLICATE_HASH_SIZE
    built_at: str = ""
    pages_by_book: dict[str, int] = field(default_factory=dict)
    """Quantas páginas de cada livro foram varridas. É o que permite construir por partes."""

    @property
    def books(self) -> set[str]:
        return set(self.pages_by_book)

    def matrix(self) -> np.ndarray:
        """Os hashes como `(N, bytes)` de `uint8`, prontos para o XOR vetorizado."""
        largura = self.hash_size * self.hash_size // 8
        if not self.entries:
            return np.zeros((0, largura), dtype=np.uint8)
        return np.array([_hash_to_bytes(entry.hash_hex, largura) for entry in self.entries], dtype=np.uint8)

    def book_ids(self) -> np.ndarray:
        """Um inteiro por entrada, identificando o livro. Serve ao desempate vetorizado.

        Comparar `source_pdf` em Python dentro do laço de casamento seria uma varredura de
        dezenas de milhares de strings por amostra -- o mesmo erro de escala que a matriz de
        hashes existe para evitar.
        """
        ordem = {nome: indice for indice, nome in enumerate(sorted({e.source_pdf for e in self.entries}))}
        return np.array([ordem[entry.source_pdf] for entry in self.entries], dtype=np.int32)

    # ------------------------------------------------------------------------ persistência

    def save(self, path: Path) -> None:
        """Grava o índice como JSONL, com um cabeçalho na primeira linha.

        Mesmo formato do `.partial.jsonl` da S-24, e pelo mesmo motivo: acrescentar não
        reescreve, e uma linha rasgada é detectável -- ela não parseia e é descartada, sem
        levar as anteriores junto.
        """
        cabecalho = {
            "version": INDEX_VERSION,
            "dpi": self.dpi,
            "hash_size": self.hash_size,
            "built_at": self.built_at or _now(),
            "pages_by_book": self.pages_by_book,
        }
        linhas = [json.dumps(cabecalho, ensure_ascii=False)]
        linhas.extend(json.dumps(entry.to_dict(), ensure_ascii=False) for entry in self.entries)

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, ("\n".join(linhas) + "\n").encode("utf-8"))
        logger.info("Índice de procedência gravado em %s (%d diagramas).", path, len(self.entries))

    @classmethod
    def load(cls, path: Path) -> ProvenanceIndex:
        """Lê o índice. Arquivo ausente devolve um índice vazio, que é o primeiro uso."""
        path = Path(path)
        if not path.exists():
            return cls()

        linhas = path.read_text(encoding="utf-8").splitlines()
        if not linhas:
            return cls()

        try:
            cabecalho = json.loads(linhas[0])
        except json.JSONDecodeError:
            raise ValueError(f"{path} não começa com um cabeçalho de índice válido.") from None

        indice = cls(
            dpi=int(cabecalho.get("dpi", DEFAULT_DPI)),
            hash_size=int(cabecalho.get("hash_size", DUPLICATE_HASH_SIZE)),
            built_at=str(cabecalho.get("built_at", "")),
            pages_by_book={str(k): int(v) for k, v in dict(cabecalho.get("pages_by_book", {})).items()},
        )
        descartadas = 0
        for linha in linhas[1:]:
            if not linha.strip():
                continue
            try:
                indice.entries.append(IndexEntry.from_dict(json.loads(linha)))
            except (json.JSONDecodeError, ValueError, TypeError):
                descartadas += 1
        if descartadas:
            logger.warning("%d linha(s) ilegíveis no índice foram descartadas.", descartadas)
        return indice

    def without_book(self, book: str) -> ProvenanceIndex:
        """Uma cópia sem as entradas de um livro. É o que permite reindexá-lo sozinho."""
        return replace(
            self,
            entries=[entry for entry in self.entries if entry.source_pdf != book],
            pages_by_book={nome: n for nome, n in self.pages_by_book.items() if nome != book},
        )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_to_bytes(hash_hex: str, largura: int) -> np.ndarray:
    valor = int(hash_hex or "0", 16)
    return np.frombuffer(valor.to_bytes(largura, "big"), dtype=np.uint8)


def hash_board_rgb(board_rgb: np.ndarray, *, hash_size: int = DUPLICATE_HASH_SIZE) -> str:
    """dHash de um tabuleiro em RGB, em hexadecimal.

    Converte para BGR antes porque é o que `audit.dhash` espera, e a conversão para cinza
    pondera os canais: alimentar RGB onde se espera BGR trocaria os pesos de R e B e daria um
    hash diferente para a mesma imagem. É o tipo de engano que não quebra nada visivelmente e
    faz o casamento inteiro falhar.
    """
    return format(dhash(cv2.cvtColor(board_rgb, cv2.COLOR_RGB2BGR), hash_size=hash_size), "x")


def hash_image_file(path: Path, *, hash_size: int = DUPLICATE_HASH_SIZE) -> str | None:
    """dHash de um PNG do `data/samples/`. `None` quando a imagem não abre."""
    imagem = read_image(path)
    if imagem is None:
        return None
    return format(dhash(imagem, hash_size=hash_size), "x")


# --------------------------------------------------------------------------------------
# Construcao do indice
# --------------------------------------------------------------------------------------

ProgressCallback = Callable[[str, int, int, int], None]
"""(livro, página 1-based, total de páginas, diagramas acumulados)."""


def build_index(
    pdf_dir: Path,
    *,
    dpi: int = DEFAULT_DPI,
    hash_size: int = DUPLICATE_HASH_SIZE,
    max_boards_per_page: int = DEFAULT_MAX_BOARDS,
    books: Sequence[str] = (),
    page_limit: int | None = None,
    base: ProvenanceIndex | None = None,
    cancel_event: threading.Event | None = None,
    progress: ProgressCallback | None = None,
) -> ProvenanceIndex:
    """Varre os PDFs e indexa o dHash de cada diagrama detectado.

    **Caro**: horas de CPU para o acervo inteiro (S-61). Por isso `books` permite fazer um
    livro por vez, e `base` permite acrescentar a um índice já construído -- um livro
    reindexado substitui as entradas anteriores dele, e não as duplica.

    `cancel_event` é conferido antes de cada página. O que já foi indexado é devolvido: uma
    varredura interrompida no livro 20 de 27 não desperdiça os 19 anteriores.
    """
    from .detection import detect_diagrams_in_pdf_page
    from .pdf_io import get_pdf_page_count, render_pdf_page

    pdf_dir = Path(pdf_dir)
    indice = base or ProvenanceIndex(dpi=dpi, hash_size=hash_size)
    if indice.dpi != dpi or indice.hash_size != hash_size:
        raise ValueError(
            f"O índice existente foi construído com dpi={indice.dpi} e hash_size={indice.hash_size}; "
            f"misturá-lo com dpi={dpi}/hash_size={hash_size} produziria casamentos sem sentido."
        )

    alvos = _books_to_scan(pdf_dir, books)
    if not alvos:
        logger.warning("Nenhum PDF encontrado em %s.", pdf_dir)
        return indice

    for caminho in alvos:
        if cancel_event is not None and cancel_event.is_set():
            logger.info("Indexação cancelada antes de %s.", caminho.name)
            break

        indice = indice.without_book(caminho.name)
        total_paginas = get_pdf_page_count(caminho)
        ultimo = total_paginas if page_limit is None else min(page_limit, total_paginas)
        encontrados = 0

        for page_index in range(ultimo):
            if cancel_event is not None and cancel_event.is_set():
                logger.info("Indexação cancelada em %s página %d.", caminho.name, page_index + 1)
                # O livro fica com a contagem parcial gravada, para que a proxima execucao
                # saiba que ele nao esta inteiro -- ver `pages_by_book` no relatorio.
                indice.pages_by_book[caminho.name] = page_index
                return indice

            try:
                page_rgb = render_pdf_page(caminho, page_index, dpi=dpi)
                candidatos = detect_diagrams_in_pdf_page(
                    caminho, page_index, page_rgb, max_boards=max_boards_per_page
                )
            except Exception as exc:  # noqa: BLE001 - um PDF ruim nao pode parar os outros 26
                logger.warning("Falha ao indexar %s página %d: %s", caminho.name, page_index + 1, exc)
                continue

            for ordem, candidato in enumerate(candidatos, start=1):
                indice.entries.append(
                    IndexEntry(
                        source_pdf=caminho.name,
                        source_page=page_index + 1,
                        source_diagram=ordem,
                        detection_source=str(candidato.source),
                        hash_hex=hash_board_rgb(candidato.board_rgb, hash_size=hash_size),
                    )
                )
                encontrados += 1

            if progress is not None:
                progress(caminho.name, page_index + 1, ultimo, encontrados)

        indice.pages_by_book[caminho.name] = ultimo
        logger.info("%s: %d páginas, %d diagramas indexados.", caminho.name, ultimo, encontrados)

    indice.built_at = _now()
    return indice


def _books_to_scan(pdf_dir: Path, books: Sequence[str]) -> list[Path]:
    if not books:
        return sorted(pdf_dir.glob("*.pdf"))

    alvos: list[Path] = []
    for nome in books:
        caminho = Path(nome) if Path(nome).exists() else pdf_dir / nome
        if caminho.exists():
            alvos.append(caminho)
        else:
            logger.warning("PDF não encontrado, ignorado: %s", nome)
    return alvos


# --------------------------------------------------------------------------------------
# Casamento
# --------------------------------------------------------------------------------------


@dataclass
class MatchReport:
    """O resultado do casamento, com a taxa que o item promete reportar."""

    considered: int = 0
    """Amostras que entraram na busca -- as sem procedência, por padrão."""

    matched: int = 0
    ambiguous: int = 0
    unreadable: int = 0
    """PNGs que não abriram. São os órfãos que a auditoria já relata."""

    matches: list[ProvenanceMatch] = field(default_factory=list)
    by_book: dict[str, int] = field(default_factory=dict)
    distances: dict[int, int] = field(default_factory=dict)
    """Histograma da **melhor** distância por amostra, casada ou não.

    É o que diz se o limiar está no lugar. Um pico logo acima do corte significa casamento
    bom sendo recusado; um platô significa que não há o que casar.
    """

    @property
    def rate(self) -> float:
        return self.matched / self.considered if self.considered else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "considered": self.considered,
            "matched": self.matched,
            "ambiguous": self.ambiguous,
            "unreadable": self.unreadable,
            "rate": round(self.rate, 4),
            "by_book": dict(sorted(self.by_book.items())),
            "distances": {str(k): v for k, v in sorted(self.distances.items())},
        }


def match_samples(
    samples_dir: Path,
    index: ProvenanceIndex,
    filenames: Iterable[str],
    *,
    max_distance: int = DEFAULT_MAX_DISTANCE,
    keep_ambiguous: bool = False,
) -> MatchReport:
    """Casa cada amostra com o diagrama mais parecido do acervo.

    `filenames` é quem entra na busca -- normalmente as amostras **sem** procedência, porque
    reescrever a das 46 que já a têm não acrescenta nada e arrisca sobrescrever um dado bom
    com um casamento ruim.

    Ambíguas ficam de fora por padrão: uma procedência errada é pior que uma vazia, porque
    parece um dado. `keep_ambiguous` existe para quem quiser inspecioná-las.
    """
    samples_dir = Path(samples_dir)
    report = MatchReport()

    matriz = index.matrix()
    if matriz.size == 0:
        logger.warning("Índice de procedência vazio: nada a casar.")
        return report

    largura = matriz.shape[1]
    livros = index.book_ids()
    for filename in filenames:
        report.considered += 1
        hash_hex = hash_image_file(samples_dir / filename, hash_size=index.hash_size)
        if hash_hex is None:
            report.unreadable += 1
            continue

        alvo = _hash_to_bytes(hash_hex, largura)
        distancias = _POPCOUNT[np.bitwise_xor(matriz, alvo)].sum(axis=1)

        melhor = int(np.argmin(distancias))
        distancia = int(distancias[melhor])
        report.distances[distancia] = report.distances.get(distancia, 0) + 1
        if distancia > max_distance:
            continue

        segundo = _runner_up(distancias, livros, melhor)
        entrada = index.entries[melhor]
        casamento = ProvenanceMatch(
            filename=filename,
            source_pdf=entrada.source_pdf,
            source_page=entrada.source_page,
            source_diagram=entrada.source_diagram,
            detection_source=entrada.detection_source,
            distance=distancia,
            runner_up=segundo,
        )
        if casamento.is_ambiguous:
            report.ambiguous += 1
            if not keep_ambiguous:
                continue

        report.matches.append(casamento)
        report.matched += 1
        report.by_book[entrada.source_pdf] = report.by_book.get(entrada.source_pdf, 0) + 1

    return report


def _runner_up(distancias: np.ndarray, livros: np.ndarray, melhor: int) -> int | None:
    """Distância do melhor casamento em **outro livro**.

    Um diagrama que aparece duas vezes no mesmo livro -- o `Reinfeld` repete exercícios entre
    a seção de problemas e a de soluções -- não torna o casamento ambíguo: as duas ocorrências
    respondem "veio deste livro", que é o que a S-07 precisa. Ambiguidade de verdade é entre
    livros diferentes, e é por isso que o segundo lugar é procurado só fora do primeiro.
    """
    de_fora = livros != livros[melhor]
    if not de_fora.any():
        return None
    return int(distancias[de_fora].min())


# --------------------------------------------------------------------------------------
# Aplicacao
# --------------------------------------------------------------------------------------


def samples_without_provenance(store: LabelStore) -> list[str]:
    """Os nomes das amostras cuja `source_pdf` está vazia -- os órfãos do item."""
    return [entry.filename for entry in store.read() if entry.filename and not entry.source_pdf]


def apply_matches(
    store: LabelStore,
    matches: Sequence[ProvenanceMatch],
    *,
    overwrite: bool = False,
    backup: bool = True,
) -> int:
    """Grava a procedência recuperada no `labels.csv`. Devolve quantas linhas mudaram.

    Uma gravação só, pela `transaction` da S-51: sem ela seriam 3.195 reescritas do arquivo
    inteiro. E backup antes, porque isto escreve em 3.195 linhas de trabalho humano de uma vez
    -- é a operação mais ampla que o projeto faz sobre esse arquivo.

    `overwrite=False` protege as 46 linhas que já têm procedência de verdade: elas foram
    gravadas pela `RecognitionOrigin` no momento em que a amostra foi salva, o que é uma fonte
    melhor que qualquer casamento por imagem.
    """
    if not matches:
        return 0

    if backup and store.exists():
        store.backup()

    existentes = {entry.filename: entry for entry in store.read()}
    aplicadas = 0
    with store.transaction() as tx:
        for match in matches:
            atual = existentes.get(match.filename)
            if atual is None:
                logger.debug("Casamento para %s ignorado: não está no CSV.", match.filename)
                continue
            if atual.source_pdf and not overwrite:
                continue

            campos = {
                "source_pdf": match.source_pdf,
                "source_page": str(match.source_page),
                "source_diagram": str(match.source_diagram),
            }
            # `detection_source` so entra onde esta vazia mesmo com `overwrite`: ali o valor
            # existente descreve como *aquela* amostra foi achada, e o do indice descreve como
            # o detector de hoje a acharia. Sao respostas para perguntas diferentes.
            if not atual.detection_source:
                campos["detection_source"] = match.detection_source

            if tx.update(match.filename, **campos):
                aplicadas += 1

    logger.info("Procedência recuperada em %d linha(s) do %s.", aplicadas, store.path)
    return aplicadas
