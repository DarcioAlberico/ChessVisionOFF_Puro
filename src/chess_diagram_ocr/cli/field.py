"""`cvoff-field` — mede o pipeline sobre páginas reais anotadas (S-41).

Dois modos, e a separação entre eles é o item:

    cvoff-field --draft "PDF/livro.pdf:80,140,201"   # rascunho para você corrigir
    cvoff-field                                       # mede contra o que foi revisado

O rascunho existe porque anotar 60 páginas do zero custa horas; corrigir o que o pipeline já
leu custa minutos. Ele sai com `reviewed: false`, e a medição pula tudo que não foi revisado
-- medir contra a própria saída do modelo daria recall 1,0 e não significaria nada.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from ..config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_DATASET_CSV,
    DEFAULT_MODEL_PATH,
    DEFAULT_PDF_DIR,
    PROJECT_ROOT,
)
from ..field_eval import (
    MIN_COMPARABLE_SHARE,
    FieldPage,
    FieldReport,
    Measurement,
    draft_page,
    evaluate_field,
    load_field_set,
    measurement_fingerprint,
    save_field_set,
)
from ..labels import LabelStore, pages_with_training_samples
from ..logging_setup import configure_logging, default_log_file
from ..service import OcrService, RecognitionOptions
from ..splits import load_splits
from . import cli_errors
from ._ocr import add_ocr_argument, caption_reader_from_args

logger = logging.getLogger(__name__)

DEFAULT_FIELD_SET = PROJECT_ROOT / "data" / "field_set.jsonl"
DEFAULT_SPLITS = DEFAULT_DATASET_CSV.parent / "splits.csv"


def _training_pages(labels: Path, splits: Path) -> dict[tuple[str, int], int]:
    """As páginas de que há amostra em `train` (S-97). Vazio quando não há o que cruzar.

    Falta de arquivo não é erro: num clone limpo o `labels.csv` existe e o `splits.csv`
    não, e a medição de campo tem de rodar assim mesmo -- o alerta é um extra, não um
    pré-requisito.
    """
    if not Path(labels).exists() or not Path(splits).exists():
        return {}
    return pages_with_training_samples(LabelStore(Path(labels)).read(), load_splits(Path(splits)))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Avalia o pipeline sobre páginas reais anotadas à mão (S-41).",
        epilog=(
            "A métrica primária é a taxa de exportação: dos diagramas que a página tem, "
            "quantos saem detectados, legais e acima do gate."
        ),
    )
    parser.add_argument("--set", type=Path, default=DEFAULT_FIELD_SET, dest="field_set")
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--max-boards", type=int, default=12)
    parser.add_argument("--orientation", default="auto", choices=("auto", "0", "180"))
    parser.add_argument("--accept-threshold", type=float, default=ACCEPT_MIN_CONFIDENCE)
    parser.add_argument("--json", type=Path, default=None, help="Grava o relatório em JSON.")
    parser.add_argument(
        "--nota",
        default="",
        help=(
            "Texto livre gravado dentro do relatorio, para o que nenhum digest captura -- "
            'tipicamente a condicao da maquina. Ex.: --nota "medido com a maquina ociosa".'
        ),
    )
    parser.add_argument(
        "--draft",
        action="append",
        default=[],
        metavar="PDF:PAGINAS",
        help=(
            "Acrescenta rascunhos ao conjunto, sem medir. Ex.: "
            '--draft "1937 Kemeri.pdf:80,140" --draft "outro.pdf:12"'
        ),
    )
    parser.add_argument("--regime", default="", help="Rótulo do regime dos rascunhos desta chamada.")
    parser.add_argument(
        "--no-placement",
        action="store_true",
        help=(
            "Rascunho só com as caixas, sem a FEN. Anotar a caixa é olhar a página; conferir "
            "a posição é ler 64 casas. Sem a FEN o conjunto ainda dá recall, precisão e taxa "
            "de exportação -- que é a métrica primária."
        ),
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_DATASET_CSV,
        help="Rótulos, para marcar as páginas de que há amostra de treino (S-97).",
    )
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS, help="Partição, para o mesmo fim.")
    parser.add_argument("--show-misses", type=int, default=10, help="Quantos diagramas perdidos listar.")
    add_ocr_argument(parser)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _parse_draft(spec: str) -> tuple[str, list[int]]:
    """`"livro.pdf:80,140"` → `("livro.pdf", [80, 140])`.

    `rsplit` e não `split`: nome de arquivo com `:` é raro mas o Windows tem `C:\\...`, e
    cortar no primeiro dois-pontos transformaria a unidade em nome de livro.
    """
    nome, separador, paginas = spec.rpartition(":")
    if not separador or not nome:
        raise ValueError(f"Esperado PDF:PAGINAS, recebido {spec!r}")
    numeros = [int(parte) for parte in paginas.split(",") if parte.strip()]
    if not numeros:
        raise ValueError(f"Nenhuma página em {spec!r}")
    return nome, numeros


def _run_draft(args: argparse.Namespace, options: RecognitionOptions, service: OcrService) -> int:
    existentes = {(pagina.pdf, pagina.page): pagina for pagina in load_field_set(args.field_set)}
    acrescentadas = 0

    for spec in args.draft:
        nome, paginas = _parse_draft(spec)
        caminho = Path(nome) if Path(nome).exists() else Path(args.pdf_dir) / nome
        if not caminho.exists():
            print(f"PDF não encontrado: {caminho}")
            return 2

        for numero in paginas:
            chave = (caminho.name, numero)
            if chave in existentes and existentes[chave].reviewed:
                # Sobrescrever uma pagina ja revisada trocaria a verdade de referencia pela
                # saida do modelo -- exatamente o que o campo `reviewed` existe para impedir.
                print(f"  {caminho.name} p{numero}: já revisada, mantida como está")
                continue
            rascunho = draft_page(
                caminho,
                numero,
                options=options,
                service=service,
                regime=args.regime,
                with_placement=not args.no_placement,
            )
            existentes[chave] = rascunho
            acrescentadas += 1
            print(f"  {caminho.name} p{numero}: {len(rascunho.diagrams)} diagrama(s) no rascunho")

    save_field_set(args.field_set, existentes.values())
    print()
    print(f"{acrescentadas} rascunho(s) em {args.field_set}.")
    print("Agora confira cada linha: acrescente o que o detector perdeu, remova o que ele")
    print("inventou, confira as FENs, e troque `\"reviewed\": false` por `true`.")
    return 0


def _print_measurement(measurement: Measurement | None) -> None:
    """Com o que este número foi medido, impresso **antes** dele (S-324).

    Antes e não depois porque é a pergunta que se faz ao colar o relatório numa tabela, e
    quem cola lê o começo. O JSON de `--json` traz estes campos e mais alguns -- tamanho,
    commit do treino --, e é ele que entra na tabela; isto aqui é para quem está olhando.
    """
    if measurement is None:
        return

    modelo = measurement.model
    print(f"  Modelo ........................ {modelo.path}")
    if modelo.sha256:
        print(f"    impressão (sha256) .......... {modelo.sha256}")
    if modelo.best_metric is not None:
        epoca = f", época {modelo.best_epoch}" if modelo.best_epoch is not None else ""
        print(f"    treino ...................... {modelo.best_metric_name or 'melhor métrica'} "
              f"{modelo.best_metric:.4f}{epoca}")
    if modelo.arch_version:
        print(f"    arquitetura ................. {modelo.arch_version}")
    if modelo.temperature != 1.0:
        print(f"    temperatura ................. {modelo.temperature:.4f}")
    if modelo.unreadable:
        # Nao e detalhe: um relatorio medido com um `.pt` que nao pode ser identificado nao
        # entra em tabela comparativa nenhuma, e quem esta olhando precisa saber disso agora.
        print(f"    identidade .................. incompleta ({modelo.unreadable})")
    print(f"  Gate de confiança ............. {measurement.accept_threshold:.2f}")
    print(f"  DPI ........................... {measurement.dpi}")
    if measurement.code_commit:
        # Metade do numero e deteccao, e deteccao e codigo. Um relatorio medido numa arvore
        # suja nao e reproduzivel, e quem for cola-lo numa tabela precisa ver isso aqui.
        sujo = "  **árvore com mudança não commitada**" if measurement.code_dirty else ""
        print(f"  Código ........................ {measurement.code_commit}{sujo}")
    print()


def _print_report(report: FieldReport, limit: int) -> None:
    print()
    print("=" * 78)
    print("Avaliação de campo")
    print("=" * 78)
    _print_measurement(report.measurement)
    if report.pages == 0:
        print("  Nenhuma página revisada no conjunto. Nada foi medido.")
        print()
        return

    print(f"  Páginas revisadas .............. {report.pages} ({report.pages_without_diagram} sem diagrama)")
    print(f"  Diagramas anotados ............. {report.annotated}")
    print()
    print("  Detecção")
    print(f"    Detectados ................... {report.detected}")
    print(f"    Casados com a anotação ....... {report.matched}")
    print(f"    Falsos positivos ............. {report.false_positives}")
    print(f"    Recall ....................... {report.detection_recall:.4f}")
    print(f"    Precisão ..................... {report.detection_precision:.4f}")
    print()
    print("  Do anotado até o PGN")
    print(f"    Detectados e legais .......... {report.legal}")
    print(f"    Detectados e acima do gate ... {report.above_gate}")
    print(f"    **Taxa de exportação** ....... {report.export_rate:.4f}  ({report.exported}/{report.annotated})")
    if report.contaminated:
        # A Fase 7 nasceu de "o conjunto de teste nao representa a entrada". O conjunto de
        # campo herdou uma versao menor do mesmo problema, e o remedio aqui e o mesmo de
        # sempre: publicar o vies em vez de estima-lo.
        print(
            f"    Em páginas com treino ........ {report.contaminated} de {report.annotated}"
            f"  ({report.contaminated / report.annotated:.0%})"
        )
        print(
            f"    **Exportação limpa** ......... {report.clean_export_rate:.4f}"
            f"  ({report.exported - report.contaminated_exported}/{report.clean_annotated})"
        )
    print()
    print("  Do PGN até estar certo (S-96)")
    print(
        f"    Conferíveis .................. {report.comparable} de {report.annotated} anotados"
        f"  ({report.comparable_share:.0%})"
    )
    if report.has_enough_comparable:
        print(
            f"    **Exatidão de campo** ........ {report.field_exact:.4f}"
            f"  ({report.exported_exact}/{report.exported_comparable} exportados)"
        )
        print(f"    Exatidão condicional ......... {report.conditional_exact:.4f}  ({report.exact}/{report.comparable})")
        print(f"    **Exportados e errados** ..... {report.exported_wrong}")
    else:
        # A taxa de exportacao diz que o modelo teve confianca; ela nao diz que ele leu certo.
        # Sem conferivel bastante, imprimir um numero de exatidao seria dar aparencia de
        # medicao ao que nao foi medido -- foi assim que um 1,000 sobre n=1, contra uma
        # alucinacao numa capa de livro, passou meses como a exatidao do produto.
        print(
            f"    Exatidão ..................... insuficiente para medir"
            f"  ({report.comparable} de {report.annotated}, mínimo {MIN_COMPARABLE_SHARE:.0%})"
        )
        print("      A taxa de exportação acima mede **confiança**, não correção: uma leitura")
        print("      confiantemente errada entra nela como acerto. Confira a FEN dos diagramas")
        print("      que passam o gate -- é a S-99, e são os que viram PGN sem ninguém olhar.")

    print()
    print("  Decodificação e custo (S-62)")
    print(
        f"    Casas reparadas pelo decode .. {report.repaired_squares}"
        f"  ({report.repairs_per_diagram:.3f} por diagrama lido)"
    )
    print(f"    Diagramas com reparo ......... {report.repaired_diagrams}")
    print(f"      reparados e exportados ..... {report.repaired_exported}")
    print(f"      reparados e barrados ....... {report.repaired_blocked}")
    if report.repaired_diagrams:
        # A separação da S-132. Enquanto era um número só ao lado da taxa de exportação, ele
        # sugeria que o reparo estava ajudando a exportar -- e a parcela "ajudou" é zero por
        # aritmética, não por acaso deste conjunto.
        print()
        print("      Uma casa reparada carrega a confiança da SEGUNDA opção, que não passa de")
        print("      0,5, e o gate é 0,80. Nenhum diagrama reparado passa -- e isso não depende")
        print("      do modelo. Ver decode.decode_constrained (S-132).")
    print(f"    Custo por diagrama ........... {report.seconds_per_diagram:.3f} s")

    if report.per_regime:
        print()
        print("  Por regime")
        for nome, parcial in sorted(report.per_regime.items(), key=lambda item: item[1].export_rate):
            alvo = f"{parcial.exported}/{parcial.annotated}" if parcial.annotated else "sem diagrama"
            fp = f", {parcial.false_positives} falso(s) positivo(s)" if parcial.false_positives else ""
            print(f"    {nome:20} exportação {parcial.export_rate:.3f}  ({alvo}{fp})")

    if report.per_book:
        print()
        print("  Por livro")
        for nome, parcial in sorted(report.per_book.items(), key=lambda item: item[1].export_rate):
            alvo = f"{parcial.exported}/{parcial.annotated}" if parcial.annotated else "sem diagrama"
            print(f"    {nome[:46]:48} {parcial.export_rate:.3f}  ({alvo})")

    if report.contaminated_pages:
        print()
        print(f"  Páginas de que há amostra de **treino** ({len(report.contaminated_pages)}):")
        print("    Não medem generalização: o próximo modelo treinado sobre os splits de hoje")
        print("    terá visto estes diagramas. Ao crescer o conjunto (S-99), prefira páginas")
        print("    que não estejam aqui.")
        for descricao in report.contaminated_pages[:limit]:
            print(f"      {descricao}")
        if len(report.contaminated_pages) > limit:
            print(f"      ... e outras {len(report.contaminated_pages) - limit}")

    if report.wrong:
        # Antes do que nao saiu, e de proposito: este e o dano maior. O barrado vai para o
        # `.review.pgn` e alguem olha; o errado entra no PGN e no dataset como verdade.
        print()
        print(f"  O que saiu **errado** para o PGN ({len(report.wrong)}):")
        for descricao in report.wrong[:limit]:
            print(f"      {descricao}")
        if len(report.wrong) > limit:
            print(f"      ... e outros {len(report.wrong) - limit}")

    if report.misses:
        print()
        print(f"  O que não chegou ao PGN ({len(report.misses)}):")
        for descricao in report.misses[:limit]:
            print(f"      {descricao}")
        if len(report.misses) > limit:
            print(f"      ... e outros {len(report.misses) - limit}")
    print()


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    options = RecognitionOptions(
        model_path=args.model,
        orientation=args.orientation,
        max_boards=args.max_boards,
        dpi=args.dpi,
    )
    # O criterio de aceite da S-43 e uma comparacao: o mesmo conjunto, com e sem OCR. Por
    # isso o leitor entra pelo servico, e nao por um caminho paralelo -- o que se mede tem
    # de ser o pipeline que a exportacao usa.
    service = OcrService(model_path=args.model, caption_reader=caption_reader_from_args(args))

    if args.draft:
        try:
            return _run_draft(args, options, service)
        except ValueError as exc:
            print(f"Erro: {exc}")
            return 2

    paginas: list[FieldPage] = load_field_set(args.field_set)
    if not paginas:
        print(f"Conjunto de campo vazio ou inexistente: {args.field_set}")
        print('Comece com: cvoff-field --draft "1937 Kemeri.pdf:80,140,201" --regime scan')
        return 1

    revisadas = sum(1 for pagina in paginas if pagina.reviewed)
    print(f"{len(paginas)} página(s) no conjunto, {revisadas} revisada(s).")

    report = evaluate_field(
        paginas,
        options=options,
        service=service,
        accept_threshold=args.accept_threshold,
        pdf_dir=args.pdf_dir,
        training_pages=_training_pages(args.labels, args.splits),
    )
    _print_report(report, limit=args.show_misses)

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        # **A impressão entra aqui, e não no `as_dict` (S-219).** O `as_dict` também serve os
        # relatórios por livro e por regime, e a impressão repetida em cada um deles diria a
        # mesma coisa dezenas de vezes. Ela é do arquivo, não do recorte.
        dados = report.as_dict()
        dados["measured_with"] = measurement_fingerprint(args.model, ocr_engine=args.ocr, note=args.nota)
        args.json.write_text(json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Relatório em {args.json}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
