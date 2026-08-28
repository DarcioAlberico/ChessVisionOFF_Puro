"""`cvoff-texto-placar` — a faixa de legenda lida pelas três fontes, na mesma tabela (S-183).

    cvoff-texto-placar --referencia docs/metrics/texto_faixa_referencia.jsonl

**É o item que decide se a Fase 26 acontece.** Todo número que a `docs/SPEC_TEXTO.md` atribui ao
PyBoxEditor foi medido no acervo *dele*. A pergunta que nunca foi feita é a daqui: **na faixa de
legenda deste acervo, o classificador de glifo lê melhor que o RapidOCR?** Sem esta tabela, as
seis fases seguintes se justificam por herança -- que é o defeito que a Fase 19 deste projeto
veio consertar.

**As duas réguas, e as duas são necessárias.**

| régua | o que mede |
|---|---|
| `cer` | erro de caractere contra a legenda transcrita à mão, normalizado pelo tamanho dela |
| `campos` | lado a jogar, número do exercício, jogadores e evento saem certos? |

Um motor que lê 90% dos caracteres e erra o dígito do exercício é pior do que a primeira coluna
sugere; um que perde em caractere pode ganhar na segunda, que é a que o programa usa. Publicar
uma sem a outra é escolher a que favorece a conclusão de quem publica.

**O conjunto de referência é trabalho humano, e o comando não o inventa.** Sem ele, o comando
diz o que falta e sai -- ver `--exemplo`, que imprime uma linha do formato para copiar.

## O formato da referência

Um JSON por linha (`.jsonl`), com a faixa identificada pelo **retângulo do diagrama** em pontos
do PDF -- o mesmo `bbox_pdf` que a S-12 carrega em cada `DiagramCandidate`, porque é ele que a
`CaptionReader` dilata e apaga por dentro:

    {"pdf": "AAGAARD - Practical Chess Defence.pdf", "pagina": 11,
     "bbox_pt": [72.0, 120.0, 300.0, 350.0],
     "texto": "Hickl - Yusupov\\nBremen 1998",
     "lado": null, "numero": null,
     "jogadores": ["Hickl", "Yusupov"], "evento": "Bremen", "ano": 1998}

`pagina` é 1-based, como o leitor de PDF mostra. Campo que a legenda **não** diz fica `null`, e
isso não é ausência de dado: é a resposta certa, e um motor que o preenche está inventando.

## A semeadura, e por que ela não vira circularidade

Achar as faixas é trabalho mecânico -- é o `detect_diagrams` da S-12 que sabe onde estão os
diagramas. Transcrever a legenda é que é humano. `--semear` faz a primeira metade: varre o
acervo, escreve uma linha por diagrama com o `bbox_pt` já preenchido e, **nos livros que têm
camada de texto**, pré-preenche `texto` com o que a camada diz.

Isso troca "transcrever 60 legendas do zero" por "conferir 60 legendas", e é a diferença entre
uma tarefa que se faz e uma que não se começa. Mas cria um risco óbvio: a camada de texto é
**uma das três fontes medidas**, e medi-la contra uma referência copiada dela dá zero por
construção.

Três coisas o contêm, e as três são verificáveis:

1. **`"conferido": false` é recusado pela medição.** Uma linha semeada não entra na tabela até
   um humano dizer que olhou. Não é honra: é o único ponto do processo em que alguém compara o
   texto com a **página impressa**, que é onde a verdade está.
2. **`texto_semente` fica gravado ao lado.** Se o humano não mudou nada, `texto == texto_semente`,
   e a tabela reporta essas células como `circulares_camada` -- com o número à vista, em vez de
   uma média que esconde de onde veio.
3. **Os 7 livros de scan puro não têm o que semear.** `texto` sai vazio, e são justamente eles
   que decidem a fase. Ali não há atalho, e não deveria haver.
"""

from __future__ import annotations

import argparse
import json
import logging
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_bytes, atomic_write_json, atomic_write_text
from ..config import DEFAULT_PDF_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging
from ..ocr import KNOWN_ENGINES, build_recognizer
from ..settings import OcrSettings, load_settings
from . import EXIT_BAD_INPUT, add_verbose, cli_errors

logger = logging.getLogger(__name__)

FONTE_CAMADA = "camada"
"""A camada de texto do PDF. Não é motor: é o controle, e nos 20 livros que a têm é o teto."""

FONTES_PADRAO = (FONTE_CAMADA, "rapidocr", "glifo")

REFERENCIA_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_faixa_referencia.jsonl"
SAIDA_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_faixa.json"

EXEMPLO = {
    "pdf": "AAGAARD - Practical Chess Defence.pdf",
    "pagina": 11,
    "bbox_pt": [72.0, 120.0, 300.0, 350.0],
    "texto": "Hickl - Yusupov\nBremen 1998",
    "lado": None,
    "numero": None,
    "jogadores": ["Hickl", "Yusupov"],
    "evento": "Bremen",
    "ano": 1998,
}


class ReferenciaInvalida(ValueError):
    """A linha do conjunto de referência não tem a forma que o comando sabe ler."""


@dataclass(frozen=True)
class Faixa:
    """Uma faixa de legenda transcrita à mão."""

    pdf: str
    pagina: int
    bbox_pt: tuple[float, float, float, float]
    texto: str
    lado: str | None
    numero: int | None
    jogadores: tuple[str, str] | None
    evento: str | None
    ano: int | None

    conferido: bool = False
    """Um humano comparou `texto` com a **página impressa**? Enquanto for `False`, esta linha
    não entra na tabela. Ver "A semeadura" no topo do módulo."""

    semeado_de: str | None = None
    """De onde veio o pré-preenchimento, quando houve. `"camada"` ou `None`."""

    texto_semente: str = ""
    """O que a semeadura escreveu. Se `texto` continuar igual a isto, ninguém corrigiu nada --
    e a célula da camada de texto é circular. A tabela conta essas células."""

    @property
    def intocada(self) -> bool:
        return bool(self.semeado_de) and self.texto == self.texto_semente

    @classmethod
    def de_json(cls, dados: Any, *, linha: int) -> Faixa:
        if not isinstance(dados, dict):
            raise ReferenciaInvalida(f"linha {linha}: não é um objeto JSON")
        for exigido in ("pdf", "pagina", "bbox_pt", "texto"):
            if exigido not in dados:
                raise ReferenciaInvalida(f"linha {linha}: falta o campo `{exigido}`")
        bbox = dados["bbox_pt"]
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ReferenciaInvalida(f"linha {linha}: `bbox_pt` precisa de quatro números")
        jogadores = dados.get("jogadores")
        return cls(
            pdf=str(dados["pdf"]),
            pagina=int(dados["pagina"]),
            bbox_pt=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
            texto=str(dados["texto"]),
            lado=(str(dados["lado"]).lower() if dados.get("lado") else None),
            numero=(int(dados["numero"]) if dados.get("numero") is not None else None),
            jogadores=((str(jogadores[0]), str(jogadores[1])) if isinstance(jogadores, list) and len(jogadores) == 2 else None),
            evento=(str(dados["evento"]) if dados.get("evento") else None),
            ano=(int(dados["ano"]) if dados.get("ano") is not None else None),
            conferido=bool(dados.get("conferido", False)),
            semeado_de=(str(dados["semeado_de"]) if dados.get("semeado_de") else None),
            texto_semente=str(dados.get("texto_semente", "") or ""),
        )

    def para_json(self) -> dict[str, Any]:
        return {
            "pdf": self.pdf,
            "pagina": self.pagina,
            "bbox_pt": [round(v, 2) for v in self.bbox_pt],
            "texto": self.texto,
            "lado": self.lado,
            "numero": self.numero,
            "jogadores": list(self.jogadores) if self.jogadores else None,
            "evento": self.evento,
            "ano": self.ano,
            "conferido": self.conferido,
            "semeado_de": self.semeado_de,
            "texto_semente": self.texto_semente,
        }


def carregar_referencia(caminho: Path) -> list[Faixa]:
    """Lê o `.jsonl`. Linha vazia é ignorada; linha malformada levanta nomeando o número."""
    faixas: list[Faixa] = []
    for numero, bruta in enumerate(caminho.read_text(encoding="utf-8").splitlines(), start=1):
        if not bruta.strip():
            continue
        try:
            dados = json.loads(bruta)
        except json.JSONDecodeError as exc:
            raise ReferenciaInvalida(f"linha {numero}: JSON inválido ({exc})") from exc
        faixas.append(Faixa.de_json(dados, linha=numero))
    return faixas


# --------------------------------------------------------------------------------------
# As duas reguas
# --------------------------------------------------------------------------------------


def _normalizar(texto: str) -> str:
    """Espaços colapsados e forma Unicode canônica. **Acento e caixa ficam.**

    Derrubar acento aqui esconderia justamente a ressalva que a S-42 registrou sobre o modelo
    `ch`+`en` do RapidOCR: ele lê alfabeto latino, e ninguém mediu o que ele faz com `ñ`, `ß` e
    acentuação portuguesa. Uma régua que normaliza isso responde a pergunta errada.
    """
    return " ".join(unicodedata.normalize("NFC", texto).split())


def distancia_de_edicao(a: str, b: str) -> int:
    """Levenshtein, em duas linhas de memória. Legenda tem dezenas de caracteres, não milhares."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        atual = [i]
        for j, cb in enumerate(b, start=1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def cer(previsto: str, referencia: str) -> float:
    """Erro de caractere normalizado. `0.0` é perfeito; passa de `1.0` quando o motor inventa.

    **Não é truncado em 1,0 de propósito.** Um motor que devolve o dobro de caracteres da
    referência é pior que um que não devolve nada, e truncar faria os dois empatarem.
    """
    esperado = _normalizar(referencia)
    if not esperado:
        return 0.0 if not _normalizar(previsto) else float("inf")
    return distancia_de_edicao(_normalizar(previsto), esperado) / len(esperado)


def campos_resolvidos(texto: str, faixa: Faixa) -> dict[str, bool]:
    """Cada campo da legenda saiu igual ao que o humano transcreveu?

    Usa o **mesmo** `parse_context` da S-16 que o pipeline usa -- medir com outro analisador
    mediria o analisador, e não o motor.
    """
    from ..pdf_text import parse_context

    contexto = parse_context(texto)
    lado_lido = None if contexto.side_to_move is None else ("w" if contexto.side_to_move else "b")
    return {
        "lado": lado_lido == faixa.lado,
        "numero": contexto.exercise_number == faixa.numero,
        "jogadores": contexto.players == faixa.jogadores,
        "evento": (contexto.event or None) == faixa.evento,
    }


# --------------------------------------------------------------------------------------
# As tres fontes
# --------------------------------------------------------------------------------------


def _texto_da_camada(page: Any, bbox_pt: tuple[float, float, float, float]) -> str:
    """O texto **cru** da faixa, como a camada o traz.

    **Cru de propósito, e a assimetria com a semeadura é deliberada.** A pergunta desta tabela é
    de leitura de faixa -- *quem lê melhor o que está impresso ali?* --, e os motores são medidos
    no cru. Passar só a camada pelo filtro de prosa e de fonte de diagrama da S-16 lhe daria uma
    vantagem que os outros dois não têm, e mediria o filtro em vez do leitor.

    A consequência é visível e fica registrada: num livro tipo `Polgar`, cujo tabuleiro **é**
    texto, a coluna da camada carrega as linhas de fonte de diagrama. O pipeline as descarta
    depois; esta régua, não.
    """
    from ..pdf_text import lines_near, page_text_lines

    vizinhas = lines_near(page_text_lines(page), bbox_pt)
    return "\n".join(vizinha.line.text for vizinha in vizinhas)


def _texto_do_motor(leitor: Any, page: Any, bbox_pt: tuple[float, float, float, float]) -> str:
    return "\n".join(linha.text for linha in leitor.lines_around(page, bbox_pt))


def _leitor_de(motor: str) -> Any:
    """Um `CaptionReader` do motor pedido, ou `None` com o motivo já logado."""
    from ..ocr_caption import build_caption_reader

    preferencias = OcrSettings(enabled=True, engine=motor, glyph_model=load_settings().ocr.glyph_model)
    reconhecedor = build_recognizer(preferencias)
    if reconhecedor is None:
        return None
    return build_caption_reader(reconhecedor)


def exportar(faixas: list[Faixa], destino: Path, *, pdf_dir: Path) -> int:
    """Grava um PNG por faixa, **exatamente a imagem que os motores leem**, para transcrever.

    **É a única parte da S-183 que dá para automatizar, e ela é a que decide se o item anda.** A
    referência tem de ser transcrita por um humano olhando a página impressa -- se ela vier de um
    motor, a tabela mede o motor contra ele mesmo. O que não precisa ser humano é *achar* a
    faixa, abrir o PDF na página certa e recortar: hoje quem for transcrever tem de fazer isso
    123 vezes à mão, e é esse o custo que trava o portão da Fase 25.

    A imagem é a faixa dilatada em `radius_pt` com o interior do diagrama **apagado**, que é o que
    `CaptionReader.lines_around` monta. Transcrever de outra imagem produziria uma referência que
    não corresponde ao que se mede.
    """
    import cv2
    import fitz

    from ..ocr_caption import DEFAULT_OCR_DPI, MIN_BAND_PT, _blank_region, _render_band
    from ..pdf_text import DEFAULT_RADIUS_PT

    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    gravadas = 0
    indice: list[dict[str, Any]] = []

    for numero, faixa in enumerate(faixas, start=1):
        caminho = pdf_dir / faixa.pdf
        if not caminho.exists():
            logger.warning("%s não está em %s; a faixa %d fica de fora.", faixa.pdf, pdf_dir, numero)
            continue
        with fitz.open(caminho) as doc:
            page = doc[faixa.pagina - 1]
            x0, y0, x1, y1 = faixa.bbox_pt
            banda = fitz.Rect(
                x0 - DEFAULT_RADIUS_PT, y0 - DEFAULT_RADIUS_PT,
                x1 + DEFAULT_RADIUS_PT, y1 + DEFAULT_RADIUS_PT,
            ) & page.rect
            if banda.is_empty or banda.width < MIN_BAND_PT or banda.height < MIN_BAND_PT:
                continue
            imagem, origem, zoom = _render_band(page, banda, dpi=DEFAULT_OCR_DPI)
            _blank_region(imagem, fitz.Rect(*faixa.bbox_pt), origin=origem, zoom=zoom)

        nome = f"{numero:03d}_p{faixa.pagina}.png"
        ok, buffer = cv2.imencode(".png", cv2.cvtColor(imagem, cv2.COLOR_RGB2BGR))
        if not ok:  # pragma: no cover - o encoder do OpenCV não falha em PNG de memória
            continue
        atomic_write_bytes(destino / nome, buffer.tobytes())
        indice.append({"n": numero, "arquivo": nome, "pdf": faixa.pdf, "pagina": faixa.pagina})
        gravadas += 1

    atomic_write_text(
        destino / "indice.json",
        json.dumps({"faixas": indice, "conferidas": 0, "total": len(faixas)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return gravadas


def medir(faixas: list[Faixa], fontes: tuple[str, ...], *, pdf_dir: Path) -> dict[str, Any]:
    """A tabela: uma célula por (fonte, régua), com o `n` de cada uma."""
    import fitz

    leitores = {}
    indisponiveis = []
    for fonte in fontes:
        if fonte == FONTE_CAMADA:
            continue
        leitor = _leitor_de(fonte)
        if leitor is None:
            indisponiveis.append(fonte)
        else:
            leitores[fonte] = leitor

    disponiveis = tuple(f for f in fontes if f == FONTE_CAMADA or f in leitores)
    por_fonte: dict[str, dict[str, Any]] = {
        f: {"cer": [], "campos": {"lado": 0, "numero": 0, "jogadores": 0, "evento": 0}, "n": 0, "por_livro": {}}
        for f in disponiveis
    }

    por_pdf: dict[str, list[Faixa]] = {}
    for faixa in faixas:
        por_pdf.setdefault(faixa.pdf, []).append(faixa)

    circulares = sum(1 for f in faixas if f.intocada)

    ausentes = []
    for nome, do_livro in sorted(por_pdf.items()):
        caminho = pdf_dir / nome
        if not caminho.exists():
            ausentes.append(nome)
            continue
        with fitz.open(caminho) as doc:
            for faixa in do_livro:
                page = doc[faixa.pagina - 1]
                for fonte in disponiveis:
                    lido = (
                        _texto_da_camada(page, faixa.bbox_pt)
                        if fonte == FONTE_CAMADA
                        else _texto_do_motor(leitores[fonte], page, faixa.bbox_pt)
                    )
                    acumulado = por_fonte[fonte]
                    erro = cer(lido, faixa.texto)
                    acumulado["cer"].append(erro)
                    acumulado["n"] += 1
                    for campo, certo in campos_resolvidos(lido, faixa).items():
                        acumulado["campos"][campo] += int(certo)
                    livro = acumulado["por_livro"].setdefault(nome, {"cer": [], "n": 0})
                    livro["cer"].append(erro)
                    livro["n"] += 1

    return {
        "fontes": list(disponiveis),
        "indisponiveis": indisponiveis,
        "pdfs_ausentes": ausentes,
        "faixas": len(faixas),
        # **A ressalva fica na tabela, e não no rodapé.** Uma faixa semeada da camada de texto
        # e nunca editada dá CER 0 para a camada por construção. Quem lê a coluna precisa saber
        # em quantas células isso vale -- ver "A semeadura" no topo do módulo.
        "circulares_camada": circulares,
        "resultado": {fonte: _resumir(dados) for fonte, dados in por_fonte.items()},
    }


def _resumir(dados: dict[str, Any]) -> dict[str, Any]:
    finitos = [e for e in dados["cer"] if e != float("inf")]
    return {
        "n": dados["n"],
        "cer_medio": (sum(finitos) / len(finitos)) if finitos else None,
        "cer_infinito": len(dados["cer"]) - len(finitos),
        "campos": {campo: {"certos": certos, "n": dados["n"]} for campo, certos in dados["campos"].items()},
        "por_livro": {
            livro: {"n": v["n"], "cer_medio": sum(x for x in v["cer"] if x != float("inf")) / max(1, v["n"])}
            for livro, v in sorted(dados["por_livro"].items())
        },
    }


# --------------------------------------------------------------------------------------
# A semeadura
# --------------------------------------------------------------------------------------


def semear(
    pdfs: list[Path],
    *,
    por_livro: int,
    dpi: float = 220.0,
) -> tuple[list[Faixa], list[str]]:
    """Uma linha de referência por diagrama achado, com o `bbox_pt` pronto e `conferido: false`.

    A varredura para no `por_livro`-ésimo diagrama de cada livro **e sorteia a página inicial
    pelo tamanho do livro**, e não pelas primeiras: as primeiras páginas de um livro de xadrez
    são prefácio e índice, e a legenda que interessa começa depois. É a mesma lição que a coleta
    do projeto de origem registrou -- "o teto guardava os primeiros N, que são as primeiras
    páginas", uma fonte, um estado de scan.

    Devolve `(faixas, avisos)`. Um livro que falha vira aviso e a varredura segue: é o contrato
    do `cvoff-batch`, e vale igual aqui.
    """
    import fitz
    import numpy as np

    from ..detection import detect_diagrams
    from ..pdf_text import contexts_for_page

    faixas: list[Faixa] = []
    avisos: list[str] = []
    zoom = dpi / 72.0

    for caminho in pdfs:
        achadas = 0
        try:
            doc = fitz.open(caminho)
        except Exception as exc:  # noqa: BLE001 - PDF de terceiro; ver o guarda do cvoff-batch
            avisos.append(f"{caminho.name}: não abriu ({exc})")
            continue
        with doc:
            total = doc.page_count
            # Começa a 15% do livro: antes disso é rosto, sumário e prefácio.
            for indice in range(int(total * 0.15), total):
                if achadas >= por_livro:
                    break
                try:
                    page = doc[indice]
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
                    candidatos = detect_diagrams(page, rgb)
                except Exception as exc:  # noqa: BLE001 - idem
                    avisos.append(f"{caminho.name} p.{indice + 1}: {exc}")
                    continue

                # **`contexts_for_page`, e não `lines_near` cru.** A primeira versão usava o cru
                # e semeava `t+v+t+l+` como legenda: é o tabuleiro do `Polgar`, impresso em
                # fonte de diagrama, que por isso vem na camada de texto como se fosse texto.
                # Quem sabe descartá-lo é o `_is_diagram_font_row` da S-16, e ele mora dentro do
                # `assign_lines_to_diagrams`. Semear pelo caminho de produção é também o que
                # garante que a referência e o pipeline concordem sobre **quais** linhas
                # pertencem a cada diagrama.
                bboxes = [c.bbox_pdf for c in candidatos]
                contextos = contexts_for_page(page, bboxes, page_number=indice + 1)
                for candidato, contexto in zip(candidatos, contextos, strict=True):
                    if achadas >= por_livro:
                        break
                    semente = contexto.caption.strip()
                    faixas.append(
                        Faixa(
                            pdf=caminho.name,
                            pagina=indice + 1,
                            bbox_pt=tuple(float(v) for v in candidato.bbox_pdf),  # type: ignore[arg-type]
                            texto=semente,
                            lado=None,
                            numero=None,
                            jogadores=None,
                            evento=None,
                            ano=None,
                            conferido=False,
                            semeado_de=(FONTE_CAMADA if semente else None),
                            texto_semente=semente,
                        )
                    )
                    achadas += 1
        if achadas == 0:
            avisos.append(f"{caminho.name}: nenhum diagrama achado; nada a semear")
    return faixas, avisos


# --------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara camada de texto, RapidOCR e glifo na mesma faixa de legenda (S-183).",
        epilog=(
            "O conjunto de referencia e transcrito a mao e nao vem no repositorio. Rode com "
            "--exemplo para ver o formato de uma linha."
        ),
    )
    parser.add_argument(
        "--referencia", type=Path, default=REFERENCIA_PADRAO, help="O .jsonl conferido à mão que serve de gabarito."
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Pasta do acervo de livros.")
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="Onde gravar o relatório desta medição.")
    parser.add_argument(
        "--fonte",
        action="append",
        choices=(FONTE_CAMADA, *KNOWN_ENGINES),
        help=f"Repetível. Padrão: {', '.join(FONTES_PADRAO)}.",
    )
    parser.add_argument("--exemplo", action="store_true", help="Imprime uma linha do formato e sai.")
    parser.add_argument(
        "--exportar",
        type=Path,
        help="Grava um PNG por faixa nessa pasta -- a mesma imagem que os motores leem -- e sai. "
        "E o que torna a transcricao possivel sem abrir 123 vezes o PDF na pagina certa.",
    )
    parser.add_argument(
        "--semear",
        action="store_true",
        help=(
            "Varre o acervo e escreve o esqueleto da referencia: bbox pronto, texto "
            "pre-preenchido da camada onde ela existe, tudo com conferido=false. Recusa "
            "sobrescrever um arquivo existente."
        ),
    )
    parser.add_argument("--por-livro", type=int, default=3, help="Quantas faixas semear por livro (padrao 3).")
    add_verbose(parser)
    return parser.parse_args(argv)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    if args.exemplo:
        print(json.dumps(EXEMPLO, ensure_ascii=False))
        return 0

    if args.exportar:
        if not args.referencia.exists():
            logger.error("%s não existe. Semeie primeiro com --semear.", args.referencia)
            return EXIT_BAD_INPUT
        faixas = carregar_referencia(args.referencia)
        gravadas = exportar(faixas, args.exportar, pdf_dir=args.pdf_dir)
        pendentes = sum(1 for f in faixas if not f.conferido)
        print(f"{gravadas} faixa(s) em {args.exportar}")
        for aviso in (
            f"  {pendentes} de {len(faixas)} ainda estao com `conferido: false`, e a medicao as recusa.",
            "  Transcreva o que esta impresso em cada PNG para o campo `texto` da linha de",
            f"  mesmo numero em {args.referencia}, e troque `conferido` por true.",
            "  **A referencia tem de vir da pagina, e nao de um motor** -- se ela vier de um,",
            "  a tabela mede o motor contra ele mesmo, que e o defeito que a S-183 evita.",
        ):
            print(aviso)
        return 0

    if args.semear:
        if args.referencia.exists():
            # **Sobrescrever apagaria conferência humana**, que é a coisa mais cara do processo.
            # Semear noutro arquivo e mesclar à mão é chato; apagar em silêncio é pior.
            logger.error(
                "%s já existe, e semear por cima apagaria o que já foi conferido. "
                "Use --referencia com outro caminho e mescle à mão.",
                args.referencia,
            )
            return EXIT_BAD_INPUT
        pdfs = sorted(p for p in args.pdf_dir.glob("*.pdf") if p.is_file())
        if not pdfs:
            logger.warning("Nenhum PDF em %s. Nada a semear.", args.pdf_dir)
            return 0

        logger.info("Semeando até %d faixas por livro em %d PDFs...", args.por_livro, len(pdfs))
        faixas, avisos = semear(pdfs, por_livro=args.por_livro)
        for aviso in avisos:
            logger.warning("%s", aviso)

        atomic_write_text(
            args.referencia,
            "\n".join(json.dumps(f.para_json(), ensure_ascii=False) for f in faixas) + "\n",
        )
        com_semente = sum(1 for f in faixas if f.semeado_de)
        logger.info(
            "%d faixas em %s (%d com texto da camada, %d em branco).\n"
            "**Nenhuma entra na tabela ainda**: confira cada `texto` contra a página impressa e "
            "troque `\"conferido\": false` por `true`. As em branco são os livros de scan puro, "
            "e são elas que decidem a fase.",
            len(faixas),
            args.referencia,
            com_semente,
            len(faixas) - com_semente,
        )
        return 0

    if not args.referencia.exists():
        # **Não é erro de uso: é o estado normal enquanto ninguém transcreveu.** Dizer o que
        # falta e sair com 0 é o que permite a CI rodar isto sem o conjunto.
        logger.warning(
            "O conjunto de referência não existe em %s.\n"
            "Ele é trabalho humano: ~60 faixas transcritas à mão -- três por livro nos 20 com "
            "camada de texto (onde a camada serve de controle) e seis nos 7 sem. Com menos que "
            "isso a tabela não separa os motores.\n"
            "`cvoff-texto-placar --exemplo` imprime o formato de uma linha.",
            args.referencia,
        )
        return 0

    todas = carregar_referencia(args.referencia)
    if not todas:
        logger.warning("%s está vazio. Sem faixa transcrita não há o que medir.", args.referencia)
        return 0

    # **A recusa do não-conferido é o que sustenta a tabela inteira.** Uma faixa semeada da
    # camada de texto e medida contra a camada de texto dá zero por construção; o `conferido`
    # é o único ponto do processo em que alguém compara com a página impressa.
    faixas = [f for f in todas if f.conferido]
    pendentes = len(todas) - len(faixas)
    if pendentes:
        logger.warning(
            "%d das %d faixas ainda estão com `conferido: false` e ficaram de fora. "
            "Confira o `texto` contra a página impressa antes de trocar a marca.",
            pendentes,
            len(todas),
        )
    if not faixas:
        logger.warning("Nenhuma faixa conferida. Não há o que medir ainda.")
        return 0

    fontes = tuple(args.fonte) if args.fonte else FONTES_PADRAO
    tabela = medir(faixas, fontes, pdf_dir=args.pdf_dir)
    tabela["nao_conferidas"] = pendentes

    for fonte in tabela["indisponiveis"]:
        logger.warning("A fonte %r não subiu e ficou fora da tabela.", fonte)
    for nome in tabela["pdfs_ausentes"]:
        logger.warning("%s não está em %s; as faixas dele ficaram de fora.", nome, args.pdf_dir)

    atomic_write_json(args.saida, tabela)
    logger.info("Tabela gravada em %s.", args.saida)

    for fonte, dados in tabela["resultado"].items():
        medio = dados["cer_medio"]
        print(f"{fonte:>10}  n={dados['n']:>4}  CER={'-' if medio is None else f'{medio:.4f}'}")
    if tabela["circulares_camada"]:
        print(
            f"\nRessalva: {tabela['circulares_camada']} faixa(s) marcadas como conferidas ainda "
            "estao identicas ao que a camada de texto semeou. Para essas, a coluna `camada` e "
            "circular."
        )
    return 0


__all__ = [
    "Faixa",
    "carregar_referencia",
    "cer",
    "distancia_de_edicao",
    "main",
    "medir",
    "parse_args",
    "semear",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
