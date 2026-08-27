"""Avaliação sobre páginas reais, e as métricas que faltavam (S-41).

**O que este módulo mede que nenhum outro media.** Toda métrica do projeto é sobre *o que
foi encontrado*: `evaluation.py` avalia recortes já rotulados, `batch.BookResult` reporta
taxa de aceite sobre o que a varredura produziu, a fila de revisão ordena o que entrou nela.
Nenhuma responde à pergunta que decide se um livro foi convertido: **dos diagramas que a
página tem, quantos saíram?**

Sem esse número, um ajuste que corte 20% dos falsos positivos e 5% dos verdadeiros aparece
como melhora em todos os painéis existentes -- a confiança média sobe, a taxa de ilegais cai
-- e é uma piora no produto.

**Por que um conjunto novo em vez do split de teste.** As 320 amostras de `test` são recortes
de `data/samples/`: tabuleiros que um humano já aprovou, salvos pelo próprio fluxo de
correção. O produto não lê recortes aprovados, lê páginas de PDF. Medido em 2026-08-09 sobre
101 diagramas de página real, o gate de exportação rejeita **17 (16,8%)** contra **3 de 320
(0,94%)** no split de teste. Fator de 18×. O classificador está no teto de uma métrica que
não descreve a entrada.

**As páginas sem diagrama são obrigatórias.** São elas que medem falso positivo, e nenhuma
métrica atual as vê -- foi assim que uma coluna de texto do `Karpov 1` pôde virar um
"tabuleiro" com oito reis brancos sem que nada acusasse.

**A anotação é humana, e o arquivo diz quando não é.** `draft_page` gera um rascunho a partir
do que o pipeline lê hoje, para que anotar seja corrigir em vez de digitar. Um rascunho não
revisado **não é verdade de referência**: medir contra a própria saída do modelo dá 100% em
tudo e não significa nada. Por isso `reviewed` existe, começa `False`, e `evaluate_field`
recusa páginas não revisadas em vez de silenciosamente inflar o número.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import subprocess
import time
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text
from .board_detection import NoBoardDetectedError
from .checkpoint import CheckpointDescription, describe_checkpoint, git_commit, git_worktree_dirty
from .config import ACCEPT_MIN_CONFIDENCE, PROJECT_ROOT
from .service import OcrService, RecognitionOptions, RecognizedDiagram

logger = logging.getLogger(__name__)

FIELD_SET_VERSION = 1

MIN_COMPARABLE_SHARE = 0.5
"""Abaixo disto o relatório recusa imprimir exatidão, e diz quantos conferiu (S-96).

Metade é um corte de bom senso, e não uma medição -- não há como medir qual fração torna uma
taxa confiável sem antes ter a taxa. O que o número protege é conhecido e tem data: com 1
posição de referência em 39 diagramas, o relatório publicava `conditional_exact = 1,000`, e
esse 1,000 tinha exatamente a mesma aparência de um 1,000 sobre 300 diagramas.

Subir o corte é seguro; baixá-lo devolve o problema. Quem quiser o número bruto tem `--json`,
onde `comparable` e `exact` continuam saindo crus, com `annotated` ao lado para a conta ser
refeita."""

MATCH_IOU = 0.5
"""IoU mínimo para uma detecção contar como o diagrama anotado.

0,5 é frouxo de propósito. O que se mede aqui é **achou ou não achou**, não a qualidade do
recorte -- essa já tem dono, é a `min_confidence`, que despenca quando a grade sai de
registro. Exigir 0,9 misturaria as duas perguntas e faria um recorte 5 px deslocado contar
como diagrama perdido.
"""

Bbox = tuple[float, float, float, float]


def bbox_iou(a: Bbox, b: Bbox) -> float:
    """IoU de dois retângulos `(x0, y0, x1, y1)`, em qualquer unidade comum."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    largura, altura = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    intersecao = largura * altura
    if intersecao <= 0:
        return 0.0
    uniao = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - intersecao
    return intersecao / uniao if uniao > 0 else 0.0


@dataclass(frozen=True)
class AnnotatedDiagram:
    """Um diagrama que a página tem, segundo um humano."""

    bbox: Bbox
    """Em **pontos do PDF**, não em pixels: a anotação sobrevive a uma troca de DPI."""

    placement: str = ""
    """Campo de peças da FEN. Vazio quando só a existência do diagrama foi anotada.

    Anotar a posição inteira custa muito mais que anotar a caixa, e as duas perguntas são
    separáveis: sem `placement` a página ainda mede recall e precisão de detecção, que é o
    que não existia. `exact` simplesmente não conta essa página."""

    side_to_move: str = ""
    """`w`, `b` ou vazio quando a página não declara e o anotador não quis supor."""

    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        dados: dict[str, Any] = {"bbox": [round(value, 2) for value in self.bbox]}
        if self.placement:
            dados["placement"] = self.placement
        if self.side_to_move:
            dados["side_to_move"] = self.side_to_move
        if self.note:
            dados["note"] = self.note
        return dados

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AnnotatedDiagram:
        caixa = [float(value) for value in raw.get("bbox", (0, 0, 0, 0))]
        if len(caixa) != 4:
            raise ValueError(f"bbox precisa de 4 números; recebido {raw.get('bbox')!r}")
        return cls(
            bbox=(caixa[0], caixa[1], caixa[2], caixa[3]),
            placement=str(raw.get("placement", "")).strip(),
            side_to_move=str(raw.get("side_to_move", "")).strip(),
            note=str(raw.get("note", "")).strip(),
        )


@dataclass(frozen=True)
class FieldPage:
    """Uma página anotada. `diagrams` vazio é um dado, não uma lacuna."""

    pdf: str
    page: int
    diagrams: tuple[AnnotatedDiagram, ...] = ()

    reviewed: bool = False
    """Um humano conferiu esta linha.

    Rascunho não revisado não é verdade de referência: medir o pipeline contra a própria
    saída dele dá 100% em tudo. `evaluate_field` recusa páginas com `reviewed=False`."""

    regime: str = ""
    """Que caso esta página cobre: `scan-hachurado`, `vetorial`, `sem-diagrama`, `solucoes`,
    `fotografia`, `fonte`. Existe para o relatório poder dizer *onde* o pipeline falha, e
    não só quanto."""

    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        dados: dict[str, Any] = {
            "pdf": self.pdf,
            "page": self.page,
            "reviewed": self.reviewed,
            "diagrams": [diagram.to_dict() for diagram in self.diagrams],
        }
        if self.regime:
            dados["regime"] = self.regime
        if self.note:
            dados["note"] = self.note
        return dados

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> FieldPage:
        return cls(
            pdf=str(raw["pdf"]),
            page=int(raw["page"]),
            diagrams=tuple(AnnotatedDiagram.from_dict(item) for item in raw.get("diagrams", ())),
            reviewed=bool(raw.get("reviewed", False)),
            regime=str(raw.get("regime", "")).strip(),
            note=str(raw.get("note", "")).strip(),
        )


def load_field_set(path: Path) -> list[FieldPage]:
    """Lê o `.jsonl`. Linha em branco é ignorada; linha inválida derruba, com o número dela.

    JSONL e não JSON pelo mesmo motivo do checkpoint de exportação (S-24): acrescentar uma
    página anotada não reescreve as anteriores, e um arquivo cortado no meio ainda tem valor
    até a última linha inteira.
    """
    path = Path(path)
    if not path.exists():
        return []

    paginas: list[FieldPage] = []
    for numero, linha in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        texto = linha.strip()
        if not texto or texto.startswith("//"):
            continue
        try:
            paginas.append(FieldPage.from_dict(json.loads(texto)))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}:{numero}: linha inválida no conjunto de campo ({exc})") from exc
    return paginas


def save_field_set(path: Path, pages: Iterable[FieldPage]) -> None:
    """Grava o `.jsonl` ordenado por (livro, página), de forma atômica (S-25)."""
    ordenadas = sorted(pages, key=lambda pagina: (pagina.pdf, pagina.page))
    corpo = "\n".join(json.dumps(pagina.to_dict(), ensure_ascii=False) for pagina in ordenadas)
    atomic_write_text(Path(path), corpo + "\n" if corpo else "")


def upsert_page(path: Path, page: FieldPage) -> int:
    """Grava uma página anotada, **substituindo** a anterior do mesmo (livro, página).

    Devolve o total de páginas revisadas no arquivo depois da gravação -- que é o número que
    interessa a quem está anotando, e o que a 7.7 pede para crescer.

    Substituir em vez de acrescentar porque a mesma página é anotada mais de uma vez na
    prática: confirma-se rápido, encontra-se um diagrama que faltou e volta-se a ela. Duas
    linhas do mesmo par fariam `evaluate_field` contar a página duas vezes, com pesos
    diferentes.
    """
    paginas = [item for item in load_field_set(path) if (item.pdf, item.page) != (page.pdf, page.page)]
    paginas.append(page)
    save_field_set(path, paginas)
    return sum(1 for item in paginas if item.reviewed)


def field_set_identity(pages: Iterable[FieldPage]) -> dict[str, int]:
    """Quantas páginas revisadas e quantos diagramas anotados o conjunto tem (S-100).

    **É a identidade que faltava para duas medições serem comparáveis.** O conjunto passou de
    15 páginas/38 diagramas para 17/39 em 2026-08-15, e todas as medições citadas nos
    documentos até então são do conjunto antigo: `cvoff-field` devolve 0,7179 onde os docs
    dizem 0,7368, e a precisão de detecção aparece em 0,9231 contra 0,9722. Nenhuma dessas
    comparações é limpa -- as duas pontas mediram conjuntos diferentes --, e nada avisava.

    O peso disso é que as tabelas que **reprovaram** S-38b, S-40, S-62a e S-62b comparam
    variantes sobre 38 diagramas; uma variante medida hoje entra numa tabela com que não é
    comparável.

    Só as revisadas, porque é o que `evaluate_field` mede: rascunho não é verdade de
    referência. Os dois números já saem no JSON do relatório com estes nomes -- o que faltava
    era compará-los.
    """
    revisadas = [pagina for pagina in pages if pagina.reviewed]
    return {
        "pages": len(revisadas),
        "annotated": sum(len(pagina.diagrams) for pagina in revisadas),
    }


# ------------------------------------------------------- com que código, e com que modelo

MEASUREMENT_ENTRY = "chess_diagram_ocr.cli.field"
"""Onde o fecho de importação começa (S-219).

**No CLI, e não em `field_eval`.** É o comando que monta o conjunto e fixa `dpi`,
`accept-threshold` e `max-boards`, e mudança ali move número tanto quanto mudança no
detector. Começar em `field_eval` deixaria essa camada de fora do digest.
"""


def _module_file(dotted: str, root: Path) -> Path | None:
    parts = dotted.split(".")
    base = root / "src" / Path(*parts)
    if base.is_dir():
        return base / "__init__.py" if (base / "__init__.py").exists() else None
    arquivo = base.with_suffix(".py")
    return arquivo if arquivo.exists() else None


def _imports_of(arquivo: Path, dotted: str) -> set[str]:
    """Os módulos **do pacote** que este importa, achados por `ast`.

    `ast` e não `import`: importar puxaria `torch` e abriria o modelo só para responder de que
    código o relatório saiu. É a mesma escolha do `text_status.py`, e pelo mesmo motivo.
    """
    try:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):  # pragma: no cover - arquivo em edição
        return set()

    # **Dentro de um `__init__.py` o pacote é o próprio módulo, e não o pai.** Errar isto fazia
    # `from .hybrid import ...` em `detection/__init__.py` resolver para
    # `chess_diagram_ocr.hybrid`, que não existe -- e `detection/hybrid.py`, o módulo cuja
    # mudança moveu os quatro relatórios de 22/08, ficava **fora** do digest. Um digest que
    # deixa de fora justamente o módulo que se move é o defeito que este item veio consertar.
    if arquivo.name == "__init__.py":
        pacote = dotted
    else:
        pacote = dotted.rsplit(".", 1)[0] if "." in dotted else dotted
    achados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            if no.level:
                base = pacote.split(".")
                subida = no.level - 1
                prefixo = ".".join(base[: len(base) - subida]) if subida else pacote
                alvo = f"{prefixo}.{no.module}" if no.module else prefixo
            elif no.module and no.module.startswith(PACOTE):
                alvo = no.module
            else:
                continue
            achados.add(alvo)
            achados.update(f"{alvo}.{a.name}" for a in no.names)
        elif isinstance(no, ast.Import):
            achados.update(a.name for a in no.names if a.name.startswith(PACOTE))
    return achados


PACOTE = "chess_diagram_ocr"


OPTIONAL_BACKENDS = (f"{PACOTE}.text",)
"""Motores que só entram quando alguém os liga, e que ficam fora do digest quando não entraram.

`--ocr` nasce `off`, e o classificador de glifo é alcançado por **um import tardio dentro de
`ocr.build_recognizer`** -- deliberado, e o comentário lá diz que é o ponto. Com o motor
desligado esse código não roda, e código que não rodou não pode ter mudado o número.

**Podar é o oposto de afrouxar aqui.** A alternativa é digerir a subárvore inteira do `text/`,
que hoje muda várias vezes por dia: a guarda ficaria vermelha o tempo todo por mudança que
comprovadamente não toca a medição, e uma guarda que grita sempre é apagada. O que mantém isso
honesto é que o motor usado sai **gravado no relatório** -- então a poda é visível, e uma
corrida com `--ocr glifo` digere o `text/` junto.
"""


def measured_modules(
    root: Path | None = None,
    entry: str = MEASUREMENT_ENTRY,
    *,
    with_ocr: bool = False,
) -> list[str]:
    """Os módulos do pacote que uma corrida de `cvoff-field` exercita, em ordem.

    Fecho de importação a partir de `entry`, e **não** uma lista escrita à mão. A lista à mão
    envelhece em silêncio: ela pegaria o defeito de hoje -- que foi em `detection/hybrid.py` --
    e deixaria passar o de amanhã, que virá de outro módulo. Um digest que passa batido é pior
    que digest nenhum, porque quem lê confia nele.

    O fecho não alcança `ui/`: nada no caminho da medição a importa, e por isso mexer na
    interface não invalida um relatório de campo. Sobre `text/`, ver `OPTIONAL_BACKENDS`.
    """
    raiz = root or PROJECT_ROOT
    vistos: set[str] = set()
    fila = [entry]
    arquivos: dict[str, Path] = {}
    while fila:
        dotted = fila.pop()
        if dotted in vistos:
            continue
        vistos.add(dotted)
        if not with_ocr and any(dotted == b or dotted.startswith(f"{b}.") for b in OPTIONAL_BACKENDS):
            continue
        arquivo = _module_file(dotted, raiz)
        if arquivo is None:
            continue
        arquivos[dotted] = arquivo
        fila.extend(_imports_of(arquivo, dotted) - vistos)
    return sorted(arquivos)


def _digest_of(caminhos: Iterable[Path], raiz: Path) -> str:
    """Digest de código: **o nome entra junto com o conteúdo.**

    Para módulo o nome é significado -- renomear `hybrid.py` muda o que roda tanto quanto
    editá-lo, e um digest cego ao nome diria que nada mudou. É o oposto do modelo, ver
    `_digest_file`.
    """
    acumulador = hashlib.sha256()
    for caminho in sorted(caminhos):
        acumulador.update(caminho.relative_to(raiz).as_posix().encode("utf-8"))
        acumulador.update(caminho.read_bytes())
    return acumulador.hexdigest()[:16]


def _digest_file(caminho: Path) -> str:
    """Digest de artefato: **só o conteúdo.**

    Para o modelo o nome não é significado, é rótulo -- e um rótulo enganoso foi exatamente o
    problema. Copiar `piece_classifier.pt` para `controle_20260816.pt` não faz dois modelos, e
    dois arquivos de mesmo nome em máquinas diferentes podem ser pesos distintos.
    """
    acumulador = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            acumulador.update(bloco)
    return acumulador.hexdigest()[:16]


def _model_path_relativo(caminho: Path, raiz: Path) -> str:
    """O caminho do modelo como um relatório deve publicá-lo: relativo à raiz quando cabe.

    **O `path` é o campo que quem abre o arquivo lê primeiro, e por isso ele tem de comparar.**
    O padrão do `--model` chega já resolvido de `PROJECT_ROOT` e o valor passado à mão chega
    como o usuário digitou, então os quatro relatórios de 2026-08-23 saíram com um absoluto e
    três relativos -- mesmo comando, mesma máquina. Dois danos, e o segundo é o que importa:

    1. publica o layout do disco de quem mediu num arquivo versionado de repositório público;
    2. **quebra a comparação que este item existe para permitir.** O mesmo modelo medido em duas
       máquinas daria `path` diferente com `digest` igual. O digest salva quem confere; quem lê
       a olho conclui que são modelos distintos, e é a olho que se lê.

    Fora da árvore continua absoluto, e aí não é ruído: é a informação de que o modelo não mora
    no repositório.
    """
    try:
        return caminho.resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return caminho.resolve().as_posix()


def _git(args: list[str], raiz: Path) -> str | None:
    try:
        saida = subprocess.run(
            ["git", *args], cwd=raiz, capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - clone sem git instalado
        return None
    return saida.stdout.strip() if saida.returncode == 0 else None


def measurement_fingerprint(
    model_path: Path | None = None,
    root: Path | None = None,
    *,
    ocr_engine: str = "off",
    note: str = "",
) -> dict[str, Any]:
    """Com que código e com que modelo este relatório foi medido (S-219).

    **O que isto conserta.** Até 2026-08-23 o relatório de campo não gravava nem uma coisa nem
    outra, e os quatro JSON de 2026-08-22 só se distinguiam pelo nome do arquivo. Custou meia
    hora identificar empiricamente qual modelo gerou cada um -- rodando candidatos até
    reproduzir bit a bit --, e escondeu um defeito pior: os quatro tinham sido medidos com
    código de gerações diferentes, metade antes e metade depois da S-176, e `detected`,
    `matched` e `false_positives` divergiam entre eles. Detecção não depende de modelo, então
    aquele quarteto era impossível numa medição sã, e **nada avisava**.

    A S-100 já ensinou a forma da solução: publicar a identidade do que foi medido e **falhar**
    quando ela diverge. Ela cobre o conjunto (`pages`/`annotated`); esta cobre as outras duas
    entradas, que são o modelo e o código.

    `dirty` não é detalhe: nesta árvore quase nunca há commit limpo, e um relatório medido com
    a árvore suja é indistinguível de um medido no commit se só o `commit` for gravado. É o
    `code.digest` que decide, e o `commit` serve para achar a vizinhança.
    """
    raiz = root or PROJECT_ROOT
    ligado = bool(ocr_engine) and ocr_engine != "off"
    modulos = measured_modules(raiz, with_ocr=ligado)

    modelo: dict[str, Any] | None = None
    if model_path is not None:
        caminho = Path(model_path)
        modelo = {
            "path": _model_path_relativo(caminho, raiz),
            "digest": _digest_file(caminho) if caminho.is_file() else None,
        }

    sujo = _git(["status", "--porcelain", "--untracked-files=no"], raiz)
    # **Um digest por módulo, e não um só para o conjunto.** Um hash agregado diz *que* mudou e
    # nunca *o quê*, e o custo disso é quem lê ter de bissectar à mão -- que foi como as quatro
    # medições de 22/08 acabaram meio numa geração de código e meio noutra. Com o mapa, a guarda
    # nomeia o módulo que se moveu.
    fontes: list[tuple[str, Path]] = []
    for dotted in modulos:
        arquivo = _module_file(dotted, raiz)
        if arquivo is not None:
            fontes.append((dotted.removeprefix(f"{PACOTE}."), arquivo))

    por_modulo = {nome: _digest_of([arquivo], raiz) for nome, arquivo in fontes}
    return {
        "model": modelo,
        "commit": _git(["rev-parse", "HEAD"], raiz),
        "dirty": None if sujo is None else bool(sujo),
        "ocr": ocr_engine or "off",
        # **A condição da máquina não sai de nenhum digest, e precisa caber em algum lugar.**
        # `seconds` variou de 58 a 113 entre corridas do mesmo modelo em 2026-08-23, e a causa
        # foi contenção de CPU, não código. Sem um campo onde dizer isso, quem abrir o arquivo
        # daqui a um mês lê a queda como ganho -- e a mensagem do commit, que é onde a ressalva
        # normalmente iria parar, não viaja junto com o JSON.
        "note": note.strip(),
        "code": {
            "digest": _digest_of([arquivo for _, arquivo in fontes], raiz),
            "entry": MEASUREMENT_ENTRY,
            # **A lista sai por extenso de propósito.** Um fecho que encolheu -- alguém tirou um
            # import e o módulo saiu do digest -- é invisível dentro de um hash e óbvio numa
            # lista. Quem lê o relatório consegue ver que o caminho medido é o que ele espera.
            "modules": por_modulo,
        },
    }


# --------------------------------------------------------------------------- relatório


@dataclass(frozen=True)
class Measurement:
    """**Com o que** este relatório foi medido (S-324).

    O relatório dizia tudo sobre *o resultado* e nada sobre *o run*. Em 2026-08-22 quatro
    modelos foram medidos sobre as mesmas 66 páginas e os quatro JSON de `docs/metrics/` só
    se distinguiam pelo **nome do arquivo** -- a tabela comparativa da S-99 dependia de quem
    gravou ter lembrado o que rodou, o que é a mesma classe de defeito que a S-100 fechou
    para o *conjunto* e que aqui continuava aberta para o *modelo*.

    Os campos são os que mudam o número e não apareciam:

    - o **modelo**, que é a pergunta que a tabela faz;
    - o **gate**, porque `export_rate` é literalmente "quantos passaram deste corte";
    - o **DPI**, porque ele muda o que o detector vê antes de o modelo ver qualquer coisa;
    - o **código**, porque metade do número é detecção, e detecção é código e não modelo.

    O código entrou por um caso medido, e não por simetria. Os mesmos quatro relatórios de
    2026-08-22 foram medidos antes de uma mudança na detecção que levou o recall de uma
    página de 0,800 para 1,000 e sumiu com um falso positivo. Nenhum campo deles mudou, e a
    guarda da S-100 não pega: ela compara `pages` e `annotated` do **conjunto**, e mudança de
    código não move nenhum dos dois.

    Não pretende ser o run inteiro. Orientação, `max_boards` e o leitor de legenda também
    mexem no número; entram aqui quando alguém tiver dois relatórios que só diferem por eles
    -- é o que aconteceu com o modelo e com o código, e é o que justifica gravá-los.
    """

    model: CheckpointDescription
    accept_threshold: float
    dpi: int
    """Os três sem valor padrão, de propósito.

    Um padrão aqui seria um número que o relatório afirma sem ter sido informado -- e afirmar
    o gate errado é pior que não afirmar nada, porque tem a mesma aparência de uma medição.
    Quem monta isto é `describe_measurement`, a partir do que o pipeline de fato usou."""

    code_commit: str = ""
    """O commit da árvore que **rodou a medição**. Vazio quando não há `git` para perguntar.

    Diferente de `model.train_commit`, que é o commit de que saiu o **treino**. Os dois
    respondem perguntas distintas e podem estar a semanas de distância."""

    code_dirty: bool = False
    """A árvore tinha mudança não commitada quando mediu.

    Sem isto o `code_commit` mente por omissão: ele aponta para o HEAD, e o que rodou foi o
    HEAD **mais** o que estava por commitar. Um relatório assim não é reproduzível, e é o
    campo que diz isso em voz alta em vez de deixar o commit dar a impressão contrária."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.as_dict(),
            "accept_threshold": round(self.accept_threshold, 4),
            "dpi": self.dpi,
            "code_commit": self.code_commit,
            "code_dirty": self.code_dirty,
        }


@lru_cache(maxsize=1)
def _code_revision() -> tuple[str, bool]:
    """O commit e a sujeira da árvore, perguntados uma vez por processo (S-324).

    Cache não é só economia dos ~120 ms de dois `git` -- é a resposta mais correta. O que o
    campo descreve é **o código que está rodando**, e esse foi fixado quando o Python
    importou os módulos. Commitar no meio de uma sessão não troca o que já está carregado, e
    perguntar de novo faria o relatório apontar para um commit que não foi o que mediu.
    """
    return git_commit(), git_worktree_dirty()


def describe_measurement(
    options: RecognitionOptions,
    *,
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
) -> Measurement:
    """Monta a identidade a partir do que já foi decidido para o run (S-324).

    A partir das `options`, e não de argumentos soltos: o que se quer gravar é o que o
    pipeline **de fato usou**, e um segundo caminho para a mesma informação é um segundo
    lugar onde ela pode divergir.
    """
    commit, sujo = _code_revision()
    return Measurement(
        model=describe_checkpoint(options.model_path),
        accept_threshold=accept_threshold,
        dpi=options.dpi,
        code_commit=commit,
        code_dirty=sujo,
    )


@dataclass
class FieldReport:
    """O que o pipeline entrega sobre páginas reais.

    A métrica primária é `export_rate`, e não a exatidão: é ela que responde "quantos
    diagramas do livro chegam ao PGN sem passar por mão humana". As outras três existem para
    dizer **onde** ela se perde -- na detecção, na legalidade ou na confiança.
    """

    pages: int = 0
    pages_without_diagram: int = 0
    annotated: int = 0
    detected: int = 0
    matched: int = 0
    false_positives: int = 0
    legal: int = 0
    above_gate: int = 0
    exported: int = 0
    comparable: int = 0
    """Diagramas casados cuja anotação traz `placement`, e que portanto podem ser conferidos."""

    exact: int = 0

    exported_comparable: int = 0
    """Dos exportados, os que têm posição de referência para conferir (S-96).

    É o denominador honesto da exatidão de campo. Um diagrama que passou o gate e não tem
    referência não conta nem como acerto nem como erro -- ele conta como *não medido*, que é
    uma terceira coisa e a mais comum hoje."""

    exported_exact: int = 0
    """Dos exportados com referência, os que a leitura acertou casa por casa (S-96)."""

    contaminated: int = 0
    """Diagramas anotados em páginas de que há amostra rotulada em `train` (S-97).

    Não são descartados do total -- o conjunto já é pequeno demais para jogar fora 18% dele.
    O que muda é que passam a **aparecer**, e que as taxas ganham uma versão limpa ao lado."""

    contaminated_exported: int = 0
    """Dos contaminados, os que saíram. É o que a taxa limpa tira do numerador."""

    repaired_squares: int = 0
    """Casas que `decode_constrained` teve de consertar no que o argmax devolveu (S-62).

    É a métrica do critério de aceite da S-62, e ela mora aqui porque o item manda medi-la
    **no conjunto de campo** e não no split de teste. Mede a distância entre o que o modelo
    sabe e o que a posição impõe: um modelo que decide as 64 casas juntas deveria precisar de
    menos reparo, e "pelo menos metade" é o corte que a spec fixou antes da primeira linha de
    código."""

    repaired_diagrams: int = 0
    """Diagramas **lidos** em que o decodificador teve de consertar pelo menos uma casa."""

    repaired_exported: int = 0
    """Dos reparados e casados com uma anotação, os que passaram no gate (S-132).

    **É estruturalmente zero**, e o número existe para dizer isso em voz alta. Uma casa reparada
    carrega a confiança da segunda opção, que não passa de 0,5, e `min_confidence` é o mínimo
    sobre as 64 — contra um gate de 0,80. Ver `decode.decode_constrained`.

    Enquanto "casas reparadas" aparecia como um número só ao lado da taxa de exportação, ele
    sugeria que o reparo estava ajudando a exportar. Somar os dois lados de uma soma em que uma
    das parcelas é sempre zero é a forma mais barata de esconder isso."""

    repaired_blocked: int = 0
    """Dos reparados e casados, os que o gate barrou. Hoje é o total dos casados reparados."""

    seconds: float = 0.0
    """Tempo de `recognize_page` somado. Com `detected`, dá o custo por diagrama.

    Não é cronômetro decorativo: o terceiro critério da S-62 é que a cabeça nova não passe de
    1,5× o custo de hoje, porque acima disso ela compete com a S-61, que quer cortar o custo
    pela metade."""

    per_regime: dict[str, FieldReport] = field(default_factory=dict)
    per_book: dict[str, FieldReport] = field(default_factory=dict)
    misses: list[str] = field(default_factory=list)
    """Descrição de cada diagrama anotado que não saiu, para o relatório poder mostrar."""

    contaminated_pages: list[str] = field(default_factory=list)
    """Que páginas têm amostra de treino, para quem for crescer o conjunto saber de onde fugir."""

    wrong: list[str] = field(default_factory=list)
    """Os que **saíram errados**: passaram o gate e a FEN não bate com a referência (S-96).

    Categoria separada de `misses` porque o dano é de outra natureza e maior. O que não sai vai
    para o `.review.pgn`, que é onde deve ir; o que sai errado entra no PGN e no dataset **como
    verdade**, com confiança alta, e ninguém olha. Somar os dois numa taxa só esconde
    exatamente a diferença que decide onde vale trabalhar."""

    measurement: Measurement | None = None
    """Com que modelo, gate e DPI este relatório foi medido (S-324).

    **Só o total tem.** Os sub-relatórios por regime e por livro são fatias do mesmo run, e
    repetir a identidade dentro de cada um encheria o JSON de cópias da mesma frase. Por isso
    `as_dict` omite a chave quando ela é `None`, e por isso `_accumulate` não a propaga.

    `None` também é o que sai de `evaluate_page`, que mede uma página contra uma leitura já
    pronta e legitimamente não sabe de onde a leitura veio.
    """

    @property
    def detection_recall(self) -> float:
        return self.matched / self.annotated if self.annotated else 0.0

    @property
    def detection_precision(self) -> float:
        return self.matched / self.detected if self.detected else 0.0

    @property
    def export_rate(self) -> float:
        """**A métrica primária.** Anotados que saem detectados, legais e acima do gate."""
        return self.exported / self.annotated if self.annotated else 0.0

    @property
    def conditional_exact(self) -> float:
        """Exatidão da FEN entre os casados com posição anotada. Comparável com a de hoje."""
        return self.exact / self.comparable if self.comparable else 0.0

    @property
    def clean_annotated(self) -> int:
        """Anotados em páginas de que **não** há amostra de treino (S-97)."""
        return self.annotated - self.contaminated

    @property
    def clean_export_rate(self) -> float:
        """A taxa de exportação sobre o subconjunto limpo. **É a que vale** (S-97).

        A geral inclui páginas cujos diagramas o próximo modelo terá visto no treino, e é por
        isso que a Fase 7 nasceu: medir o modelo no que ele aprendeu dá o número errado para
        cima. Aqui a diferença entre as duas é o tamanho do viés -- e ela é publicada, e não
        estimada."""
        return (self.exported - self.contaminated_exported) / self.clean_annotated if self.clean_annotated else 0.0

    @property
    def field_exact(self) -> float:
        """**Dos que chegaram ao PGN, quantos estão certos** (S-96).

        A `export_rate` responde *quanto sai do livro*, e ela sozinha não distingue uma leitura
        certa de uma **confiantemente errada** -- as duas passam o gate e as duas contam como
        sucesso. Foi essa cegueira que a 7.7 encontrou como "uma catraca que só desce" e
        atribuiu à distribuição bimodal da confiança; a explicação está um nível abaixo, e é
        que uma métrica de confiança não pode medir correção.

        O denominador são os exportados **com referência**, e não todos os exportados: quem não
        tem posição anotada não foi medido, e diluí-lo no denominador faria a exatidão cair
        quando o que faltou foi anotação."""
        return self.exported_exact / self.exported_comparable if self.exported_comparable else 0.0

    @property
    def exported_wrong(self) -> int:
        """Quantos saíram para o PGN com a posição errada. É o número que mais dói (S-96)."""
        return self.exported_comparable - self.exported_exact

    @property
    def comparable_share(self) -> float:
        """Que fração dos anotados tem posição de referência. Zero significa "não medido"."""
        return self.comparable / self.annotated if self.annotated else 0.0

    @property
    def has_enough_comparable(self) -> bool:
        """Se há amostra para a palavra "exatidão" significar alguma coisa (S-96).

        Abaixo de `MIN_COMPARABLE_SHARE` o relatório **recusa imprimir o número** e diz quantos
        foram conferidos. O motivo tem nome e data: em 2026-08-16 o conjunto tinha 1 posição de
        referência em 39 diagramas, e ela era a leitura do próprio modelo sobre uma capa de
        livro -- uma posição sem rei branco. O relatório publicava `conditional_exact = 1,000`,
        e um 1,000 sobre n=1 tem a mesma aparência de um 1,000 sobre n=300.

        Um número que não tem amostra não deve ter aparência de número."""
        return self.annotated > 0 and self.comparable_share >= MIN_COMPARABLE_SHARE

    @property
    def repairs_per_diagram(self) -> float:
        """Casas reparadas por diagrama **detectado** (S-62).

        Por detectado e não por anotado: o reparo é uma propriedade do que o modelo leu, e um
        diagrama que o detector perdeu não teve leitura para reparar. Dividir pelos anotados
        misturaria a qualidade do decodificador com a do detector."""
        return self.repaired_squares / self.detected if self.detected else 0.0

    @property
    def seconds_per_diagram(self) -> float:
        return self.seconds / self.detected if self.detected else 0.0

    def as_dict(self) -> dict[str, Any]:
        dados: dict[str, Any] = {
            "pages": self.pages,
            "pages_without_diagram": self.pages_without_diagram,
            "annotated": self.annotated,
            "detected": self.detected,
            "matched": self.matched,
            "false_positives": self.false_positives,
            "detection_recall": round(self.detection_recall, 4),
            "detection_precision": round(self.detection_precision, 4),
            "legal": self.legal,
            "above_gate": self.above_gate,
            "exported": self.exported,
            "export_rate": round(self.export_rate, 4),
            "comparable": self.comparable,
            "exact": self.exact,
            "conditional_exact": round(self.conditional_exact, 4),
            # S-96: o JSON sai cru, inclusive quando o relatorio de texto recusa o numero. Ele
            # e a entrada de quem refaz a conta, e `comparable_share` diz o quanto confiar.
            "comparable_share": round(self.comparable_share, 4),
            "enough_comparable": self.has_enough_comparable,
            "exported_comparable": self.exported_comparable,
            "exported_exact": self.exported_exact,
            "exported_wrong": self.exported_wrong,
            "field_exact": round(self.field_exact, 4),
            # S-97: o vies que o conjunto carrega, publicado ao lado do numero que ele afeta.
            "contaminated": self.contaminated,
            "contaminated_exported": self.contaminated_exported,
            "clean_annotated": self.clean_annotated,
            "clean_export_rate": round(self.clean_export_rate, 4),
            "repaired_squares": self.repaired_squares,
            "repaired_diagrams": self.repaired_diagrams,
            "repaired_exported": self.repaired_exported,
            "repaired_blocked": self.repaired_blocked,
            "repairs_per_diagram": round(self.repairs_per_diagram, 4),
            "seconds": round(self.seconds, 3),
            "seconds_per_diagram": round(self.seconds_per_diagram, 4),
            "per_regime": {nome: relatorio.as_dict() for nome, relatorio in sorted(self.per_regime.items())},
            "per_book": {nome: relatorio.as_dict() for nome, relatorio in sorted(self.per_book.items())},
        }
        if self.measurement is None:
            return dados
        # A identidade na frente, e de proposito: quem abre um relatorio precisa saber **de
        # quem** e o numero antes de ler o numero (S-324).
        return {"measurement": self.measurement.as_dict(), **dados}

    def summary(self) -> str:
        exatidao = (
            f"exatidão de campo {self.field_exact:.3f} (n={self.exported_comparable})"
            if self.has_enough_comparable
            else f"exatidão não medida ({self.comparable} de {self.annotated} conferidos)"
        )
        sujeira = f" (limpa {self.clean_export_rate:.3f}, {self.contaminated} contaminados)" if self.contaminated else ""
        return (
            f"{self.annotated} diagramas anotados em {self.pages} páginas "
            f"({self.pages_without_diagram} sem diagrama) | "
            f"recall {self.detection_recall:.3f} | precisão {self.detection_precision:.3f} | "
            f"**exportação {self.export_rate:.3f}**{sujeira} | {exatidao}"
        )


def _accumulate(alvo: FieldReport, parcela: FieldReport) -> None:
    alvo.pages += parcela.pages
    alvo.pages_without_diagram += parcela.pages_without_diagram
    alvo.annotated += parcela.annotated
    alvo.detected += parcela.detected
    alvo.matched += parcela.matched
    alvo.false_positives += parcela.false_positives
    alvo.legal += parcela.legal
    alvo.above_gate += parcela.above_gate
    alvo.exported += parcela.exported
    alvo.comparable += parcela.comparable
    alvo.exact += parcela.exact
    alvo.exported_comparable += parcela.exported_comparable
    alvo.exported_exact += parcela.exported_exact
    alvo.contaminated += parcela.contaminated
    alvo.contaminated_exported += parcela.contaminated_exported
    alvo.repaired_squares += parcela.repaired_squares
    alvo.repaired_diagrams += parcela.repaired_diagrams
    alvo.repaired_exported += parcela.repaired_exported
    alvo.repaired_blocked += parcela.repaired_blocked
    alvo.seconds += parcela.seconds
    alvo.misses.extend(parcela.misses)
    alvo.wrong.extend(parcela.wrong)
    alvo.contaminated_pages.extend(parcela.contaminated_pages)


def _match(annotated: Sequence[AnnotatedDiagram], read: Sequence[RecognizedDiagram]) -> dict[int, int]:
    """Casa anotação com leitura pelo melhor IoU, sem repetir leitura.

    Guloso sobre os pares ordenados por IoU, em vez de "o melhor para cada anotação": numa
    página em que duas anotações vizinhas apontam para a mesma leitura, escolher por
    anotação faria a segunda ficar sem par mesmo havendo leitura livre para ela.
    """
    pares = [
        (bbox_iou(anotado.bbox, lido.bbox_pdf), indice_anotado, indice_lido)
        for indice_anotado, anotado in enumerate(annotated)
        for indice_lido, lido in enumerate(read)
        if lido.bbox_pdf is not None
    ]
    pares.sort(reverse=True)

    casados: dict[int, int] = {}
    usados: set[int] = set()
    for iou, indice_anotado, indice_lido in pares:
        if iou < MATCH_IOU or indice_anotado in casados or indice_lido in usados:
            continue
        casados[indice_anotado] = indice_lido
        usados.add(indice_lido)
    return casados


def evaluate_page(
    page: FieldPage,
    read: Sequence[RecognizedDiagram],
    *,
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
    seconds: float = 0.0,
    training_samples: int = 0,
) -> FieldReport:
    """Compara o que o pipeline leu numa página com o que a anotação diz que ela tem.

    `training_samples` é quantas amostras de `train` vêm desta página (S-97). Acima de zero, os
    diagramas dela contam em `contaminated` e saem da taxa limpa -- ver
    `labels.pages_with_training_samples` para o que o número significa e o que ele **não**
    significa.
    """
    relatorio = FieldReport(
        pages=1,
        pages_without_diagram=1 if not page.diagrams else 0,
        annotated=len(page.diagrams),
        detected=len(read),
        seconds=seconds,
        # Sobre **tudo** que foi lido, inclusive o falso positivo: o reparo mede o trabalho
        # que o decodificador teve, e ele teve esse trabalho ali tambem (S-62).
        repaired_squares=sum(len(lido.changed_squares) for lido in read),
        repaired_diagrams=sum(1 for lido in read if lido.changed_squares),
    )

    casados = _match(page.diagrams, read)
    relatorio.matched = len(casados)
    relatorio.false_positives = len(read) - len(casados)

    contaminada = training_samples > 0 and bool(page.diagrams)
    if contaminada:
        relatorio.contaminated = len(page.diagrams)
        relatorio.contaminated_pages.append(
            f"{page.pdf} p{page.page}: {len(page.diagrams)} diagrama(s) anotado(s), "
            f"{training_samples} amostra(s) de treino desta página"
        )

    for indice, anotado in enumerate(page.diagrams):
        alvo = casados.get(indice)
        if alvo is None:
            relatorio.misses.append(f"{page.pdf} p{page.page}: não detectado {anotado.bbox}")
            continue

        lido = read[alvo]
        legal = lido.is_fatal is not True
        acima = lido.min_confidence >= accept_threshold
        exportado = legal and acima
        relatorio.legal += int(legal)
        relatorio.above_gate += int(acima)
        if lido.changed_squares:
            # A separação da S-132. `repaired_exported` é estruturalmente zero -- ver
            # `decode.decode_constrained` --, e é por isso que ele é publicado: um número que
            # só pode ser zero, impresso, é uma afirmação; somado ao outro, é um disfarce.
            relatorio.repaired_exported += int(exportado)
            relatorio.repaired_blocked += int(not exportado)
        if exportado:
            relatorio.exported += 1
            relatorio.contaminated_exported += int(contaminada)
        else:
            motivo = "ilegal" if not legal else f"confiança {lido.min_confidence:.3f}"
            relatorio.misses.append(f"{page.pdf} p{page.page}: detectado mas barrado ({motivo})")

        if not anotado.placement:
            continue

        certo = lido.placement == anotado.placement
        relatorio.comparable += 1
        relatorio.exact += int(certo)

        # S-96: exportado e errado e a categoria que mais custa, e por isso ela e contada
        # separada em vez de sair no complemento de uma taxa. O que nao sai vai para o
        # `.review.pgn`; o que sai errado entra no PGN e no dataset como verdade.
        if exportado:
            relatorio.exported_comparable += 1
            relatorio.exported_exact += int(certo)
            if not certo:
                relatorio.wrong.append(
                    f"{page.pdf} p{page.page}: exportado e errado "
                    f"(confiança {lido.min_confidence:.3f})\n"
                    f"        leu       {lido.placement}\n"
                    f"        referência {anotado.placement}"
                )

    return relatorio


class MissingFieldPdfError(FileNotFoundError):
    """Um PDF citado pelo conjunto de campo não está onde a medição vai procurá-lo (S-219).

    **É uma falha, e não um dado.** Até 2026-08-22 o laço de `evaluate_field` capturava
    `Exception` inteira e transformava qualquer tropeço em `lidos = []` -- e "o arquivo não
    existe" é indistinguível, nessa forma, de "esta página não tem tabuleiro". Naquele dia 11
    páginas entraram no conjunto com o nome do livro em codificação dupla
    (`Eröffnungswege` gravado como `ErÃ¶ffnungswege`), nenhum dos arquivos abriu, e o
    relatório saiu com `detection_recall` **0,7596** onde o pipeline valia **0,9364**. O
    único sinal foi um WARNING com a mesma frase que uma página legitimamente vazia produz.

    Uma métrica medida sobre arquivos que não abriram não é uma métrica ruim, é um número
    sobre outra coisa -- e ele foi para os documentos como se fosse regressão do detector.
    Por isso isto derruba a medição em vez de baixá-la.

    `FileNotFoundError` e não uma classe solta porque `cli.run_main` já traduz `OSError` para
    pt-BR e devolve `EXIT_BAD_INPUT`: um caminho errado no conjunto é entrada inválida, que é
    exatamente a classe 2.
    """


class FieldPageReadError(RuntimeError):
    """Falha ao ler uma página do conjunto que **não** é "esta página não tem tabuleiro".

    PDF que existe mas não abre, página fora do arquivo, backend sem checkpoint: nada disso é
    resultado de medição. A mensagem carrega o caminho, o número da página e o texto original
    da exceção -- o original porque é ele que `cli.message_for` traduz e `cli.classify` lê.
    """


def _pdf_path(page: FieldPage, pdf_dir: Path | None) -> Path:
    """Onde a medição procura o PDF desta página. Um lugar só, para o pré-voo e o laço."""
    return Path(pdf_dir) / page.pdf if pdf_dir is not None else Path(page.pdf)


def _undo_double_encoding(nome: str) -> str | None:
    """`"ErÃ¶ffnungswege.pdf"` → `"Eröffnungswege.pdf"`, quando o nome passou por UTF-8 duas vezes.

    `None` quando a volta não muda nada ou não é possível -- o nome já estava certo.
    """
    try:
        recuperado = nome.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return recuperado if recuperado != nome else None


def _name_keys(nome: str) -> set[str]:
    """As formas do nome que são "o mesmo arquivo" para efeito de sugestão.

    Codificação dupla desfeita, NFC (o macOS grava NFD) e caixa dobrada: são as três maneiras
    de o conjunto e o disco discordarem sobre um nome que um humano leria como igual.
    """
    variantes = {nome}
    recuperado = _undo_double_encoding(nome)
    if recuperado:
        variantes.add(recuperado)
    return {unicodedata.normalize("NFC", variante).casefold() for variante in variantes}


def _look_alike(caminho: Path) -> str | None:
    """Um arquivo da mesma pasta que só difere do procurado pela codificação do nome.

    A sugestão é o que separa "arrume o conjunto" de "procure o que aconteceu": sem ela, o
    incidente de 2026-08-22 continua sendo 11 caminhos que não existem e nenhuma pista de que
    os arquivos estavam ali o tempo todo, com o nome certo.
    """
    pasta = caminho.parent
    procuradas = _name_keys(caminho.name)
    try:
        existentes = sorted(item.name for item in pasta.iterdir() if item.is_file())
    except OSError:
        return None
    return next((nome for nome in existentes if _name_keys(nome) & procuradas), None)


def missing_field_pdfs(pages: Sequence[FieldPage], *, pdf_dir: Path | None = None) -> list[Path]:
    """Os PDFs das páginas **revisadas** que não estão onde a medição vai procurar.

    Só as revisadas porque só elas são medidas: um rascunho pendente citando um PDF que ainda
    não chegou à máquina não pode impedir a medição do resto.
    """
    caminhos: dict[Path, None] = {}
    for pagina in pages:
        if pagina.reviewed:
            caminhos.setdefault(_pdf_path(pagina, pdf_dir), None)
    return [caminho for caminho in caminhos if not caminho.is_file()]


def require_field_pdfs(pages: Sequence[FieldPage], *, pdf_dir: Path | None = None) -> None:
    """Confere **antes de medir** que todo PDF citado abre, ou levanta `MissingFieldPdfError`.

    Pré-voo e não checagem no laço por dois motivos. O primeiro é tempo: uma medição de campo
    leva minutos por livro, e descobrir no oitavo que o terceiro não existia é descobrir tarde.
    O segundo é que a lista completa é o diagnóstico -- 11 nomes com o mesmo defeito dizem
    "codificação", um nome de cada vez diz "arquivo faltando".
    """
    faltando = missing_field_pdfs(pages, pdf_dir=pdf_dir)
    if not faltando:
        return

    pasta = Path(pdf_dir) if pdf_dir is not None else Path.cwd()
    linhas = []
    for caminho in faltando:
        rotulo = caminho.name if caminho.parent == pasta else str(caminho)
        parecido = _look_alike(caminho)
        sugestao = f'  (a pasta tem "{parecido}" -- nome em codificação dupla?)' if parecido else ""
        linhas.append(f"  - {rotulo}{sugestao}")

    cabecalho = (
        f"{len(faltando)} PDF(s) citados pelo conjunto de campo não foram encontrados.\n"
        f"Pasta procurada: {pasta}"
    )
    raise MissingFieldPdfError(
        "\n".join([cabecalho, *linhas]) + "\n"
        "Corrija o campo `pdf` do conjunto ou aponte --pdf-dir para a pasta certa. "
        "A medição não roda sem eles: o recall sairia baixo por arquivo ausente, e não por "
        "falha do pipeline -- e os dois números têm a mesma aparência no relatório."
    )


def evaluate_field(
    pages: Sequence[FieldPage],
    *,
    options: RecognitionOptions,
    service: OcrService | None = None,
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
    pdf_dir: Path | None = None,
    on_page: Any = None,
    training_pages: Mapping[tuple[str, int], int] | None = None,
) -> FieldReport:
    """Roda o pipeline sobre as páginas anotadas e devolve o relatório consolidado.

    Páginas com `reviewed=False` são **puladas com aviso**. Contá-las inflaria o número com
    a própria saída do modelo, que é exatamente o que o conjunto existe para não fazer.

    **Página sem tabuleiro é resultado; arquivo que não abre é falha (S-219).** Só
    `NoBoardDetectedError` vira zero diagramas detectados -- é a mesma decisão que a S-34
    tomou para o livro que falha no meio da varredura em lote, e é o que permite ao relatório
    cobrir o livro inteiro. Qualquer outra exceção derruba a medição: um número medido sobre
    arquivos que não abriram descreve outra coisa, e no relatório ele tem a mesma aparência de
    uma regressão do detector. Ver `MissingFieldPdfError` para o dia em que teve.

    Os PDFs citados são conferidos **antes** da primeira leitura, por `require_field_pdfs`.

    `training_pages` vem de `labels.pages_with_training_samples` e marca as páginas de que
    há amostra em `train` (S-97). `None` desliga a checagem -- é o que os testes usam, e é
    o comportamento anterior.

    O relatório sai carimbado com **que modelo, que gate e que DPI** produziram estes números
    (S-324): sem isso, dois relatórios de dois modelos sobre o mesmo conjunto são dois
    arquivos idênticos com nomes diferentes.
    """
    require_field_pdfs(pages, pdf_dir=pdf_dir)
    service = service or OcrService(model_path=options.model_path)
    # Antes do laco, e nao no fim: um run que nao mediu pagina nenhuma ainda tem de dizer com
    # que modelo ele nao mediu nada. E aqui, e nao na CLI, porque a identidade e do que foi
    # medido -- deixa-la com quem chama recria o "dependia de quem gravou lembrar" (S-324).
    total = FieldReport(measurement=describe_measurement(options, accept_threshold=accept_threshold))
    puladas = 0

    for pagina in pages:
        if not pagina.reviewed:
            puladas += 1
            continue

        caminho = _pdf_path(pagina, pdf_dir)
        inicio = time.perf_counter()
        try:
            lidos = service.recognize_page(caminho, pagina.page, options=options)
        except NoBoardDetectedError as exc:
            # A única falha que é medição: a página existe, foi aberta, e não tem tabuleiro --
            # que é o mesmo que o detector dizer "nenhum". Vale recall zero nesta página, e o
            # `debug` basta porque a página já aparece no relatório, em `misses`.
            logger.debug("Nenhum tabuleiro em %s p%d (%s).", pagina.pdf, pagina.page, exc)
            lidos = []
        except Exception as exc:
            # Tudo o mais -- PDF que não abre, página fora do arquivo, backend sem checkpoint --
            # é defeito de entrada ou de ambiente, e até a S-219 virava zero detectados sem
            # nada avisar. O `from` preserva a causa; a mensagem acrescenta qual página parou.
            raise FieldPageReadError(f"Falha ao ler {caminho} (página {pagina.page}): {exc}") from exc
        decorrido = time.perf_counter() - inicio

        parcela = evaluate_page(
            pagina,
            lidos,
            accept_threshold=accept_threshold,
            seconds=decorrido,
            training_samples=(training_pages or {}).get((pagina.pdf, pagina.page), 0),
        )
        _accumulate(total, parcela)
        _accumulate(total.per_book.setdefault(pagina.pdf, FieldReport()), parcela)
        if pagina.regime:
            _accumulate(total.per_regime.setdefault(pagina.regime, FieldReport()), parcela)
        if on_page is not None:
            on_page(pagina, parcela)

    if puladas:
        logger.warning(
            "%d página(s) do conjunto de campo ainda não revisadas e ficaram de fora. "
            "Rascunho não é verdade de referência: revise e marque `reviewed: true`.",
            puladas,
        )
    return total


def draft_page(
    pdf: Path,
    page: int,
    *,
    options: RecognitionOptions,
    service: OcrService | None = None,
    regime: str = "",
    with_placement: bool = True,
) -> FieldPage:
    """Rascunho de anotação a partir do que o pipeline lê hoje, para anotar ser corrigir.

    Sai com `reviewed=False`, sempre, e é a única coisa que impede este atalho de virar
    trapaça: um rascunho medido contra si mesmo dá recall 1,0 e exatidão 1,0.

    O que o humano precisa fazer depois: **acrescentar** os diagramas que faltaram (o
    rascunho não sabe o que o detector não achou), **remover** os falsos positivos, conferir
    as FENs, e marcar `reviewed: true`.
    """
    service = service or OcrService(model_path=options.model_path)
    try:
        lidos = service.recognize_page(Path(pdf), page, options=options)
    except Exception as exc:  # noqa: BLE001 - página sem diagrama levanta, e é um rascunho válido
        logger.debug("Nada lido em %s p%d (%s); rascunho sai vazio.", pdf, page, exc)
        lidos = []

    diagramas = tuple(
        AnnotatedDiagram(
            bbox=lido.bbox_pdf,
            placement=lido.placement if with_placement else "",
            side_to_move=lido.side_to_move if lido.side_to_move_source != "default" else "",
            note=f"rascunho: conf {lido.min_confidence:.3f}, {lido.detection_source or 'contorno'}",
        )
        for lido in lidos
        if lido.bbox_pdf is not None
    )
    return FieldPage(pdf=Path(pdf).name, page=page, diagrams=diagramas, reviewed=False, regime=regime)
