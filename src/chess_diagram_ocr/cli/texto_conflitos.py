"""`cvoff-texto-conflitos`: a mesma imagem sob dois rótulos -- achar, mostrar, e mover (S-202).

Três modos, e o padrão é o que não mexe em nada:

    cvoff-texto-conflitos                    lista o que existe, e o que as decisões dizem
    cvoff-texto-conflitos --folha f.png      desenha os glifos em disputa, para alguém julgar
    cvoff-texto-conflitos --aplicar          move os perdedores para a quarentena
    cvoff-texto-conflitos --desfazer m.json  traz todos de volta

**O comando não julga.** Ele lê `data/texto_conflitos.json`, que é trabalho humano e é
versionado, e recusa aplicar um grupo cujo estado no disco não seja o que a decisão descreve.
Ver o cabeçalho de `text/conflitos.py` para por que a maioria não pode decidir sozinha.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from datetime import date
from pathlib import Path

from ..atomic_io import atomic_write_bytes, atomic_write_text
from ..config import PROJECT_ROOT, caminho_para_relatorio
from ..logging_setup import configure_logging
from . import cli_errors

logger = logging.getLogger(__name__)

BASE_PADRAO = PROJECT_ROOT / "training_data"
DECISOES = PROJECT_ROOT / "data" / "texto_conflitos.json"
QUARENTENA = PROJECT_ROOT / "data" / "quarentena_texto"
METRICAS = PROJECT_ROOT / "docs" / "metrics"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Acha a mesma imagem arquivada sob dois caracteres, e move o rotulo perdedor."
    )
    parser.add_argument("--base", type=Path, default=BASE_PADRAO)
    parser.add_argument("--decisoes", type=Path, default=DECISOES)
    parser.add_argument("--quarentena", type=Path, default=QUARENTENA)
    parser.add_argument("--aplicar", action="store_true", help="Move os perdedores. Sem isto, so relata.")
    parser.add_argument("--desfazer", type=Path, metavar="MANIFESTO", help="Devolve a base o que um manifesto moveu.")
    parser.add_argument("--folha", type=Path, metavar="PNG", help="Desenha os glifos em disputa para revisao humana.")
    parser.add_argument("--relatorio", type=Path, help="Padrao: docs/metrics/texto_dedupe_<data>.json")
    parser.add_argument(
        "--quase",
        action="store_true",
        help="Mede tambem a quase-duplicata (S-202). Decodifica a base, entao custa alguns minutos.",
    )
    parser.add_argument("--limiar-quase", type=float, default=None, help="Padrao: 0,03, medido nesta base.")
    parser.add_argument("--tarefas", type=int, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _desenhar_folha(conflitos: list, base: Path, destino: Path, decisoes: dict) -> None:
    """Uma ficha por conflito: o glifo ampliado, os rótulos em disputa, e o que já se decidiu."""
    import cv2
    import numpy as np

    from ..text.conflitos import Conflito

    ESCALA, COLUNAS, LEGENDA = 6, 6, 46
    cel = 32 * ESCALA
    linhas = (len(conflitos) + COLUNAS - 1) // COLUNAS
    folha = np.full((linhas * (cel + LEGENDA), COLUNAS * cel, 3), 255, np.uint8)

    for i, conflito in enumerate(conflitos):
        assert isinstance(conflito, Conflito)
        pasta, nomes = next(iter(sorted(conflito.arquivos.items())))
        with open(base / pasta / nomes[0], "rb") as arquivo:
            bruto = arquivo.read()
        imagem = cv2.imdecode(np.frombuffer(bruto, np.uint8), cv2.IMREAD_GRAYSCALE)
        if imagem is None:
            continue
        if imagem.shape != (32, 32):
            imagem = cv2.resize(imagem, (32, 32), interpolation=cv2.INTER_AREA)

        r, c = divmod(i, COLUNAS)
        y0 = r * (cel + LEGENDA)
        grande = cv2.resize(imagem, (cel, cel), interpolation=cv2.INTER_NEAREST)
        folha[y0 : y0 + cel, c * cel : (c + 1) * cel] = cv2.cvtColor(grande, cv2.COLOR_GRAY2BGR)
        cv2.rectangle(folha, (c * cel, y0), (c * cel + cel - 1, y0 + cel - 1), (180, 180, 180), 1)

        decisao = decisoes.get(conflito.sha256, {})
        venc = decisao.get("vencedor")
        texto = "  ".join(f"{p}={n}" for p, n in conflito.rotulos.items())
        veredito = f"-> {venc}" if venc else ("-> indecidivel" if decisao else "(sem decisao)")
        cor = (0, 130, 0) if venc else (0, 0, 190)
        cv2.putText(folha, texto[:34], (c * cel + 4, y0 + cel + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 60), 1, cv2.LINE_AA)
        cv2.putText(folha, veredito, (c * cel + 4, y0 + cel + 31), cv2.FONT_HERSHEY_SIMPLEX, 0.42, cor, 1, cv2.LINE_AA)
        cv2.putText(folha, conflito.sha256[:10], (c * cel + 4, y0 + cel + 43), cv2.FONT_HERSHEY_PLAIN, 0.7, (150, 150, 150), 1, cv2.LINE_AA)

    destino.parent.mkdir(parents=True, exist_ok=True)
    ok, buffer = cv2.imencode(".png", folha)
    if not ok:  # pragma: no cover - cv2 falhando a codificar PNG em memória
        raise OSError("nao foi possivel codificar a folha de contato")
    atomic_write_bytes(destino, buffer.tobytes())


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    from ..text import conflitos as cf

    if args.desfazer:
        voltaram = cf.desfazer(args.desfazer)
        print(f"{voltaram} recortes voltaram para a base.")
        return 0

    if not Path(args.base).is_dir():
        raise ValueError(f"a base de treino nao esta em {args.base}")

    print(f"Procurando a mesma imagem sob dois rotulos em {args.base}...")

    def progresso(nome: str, i: int, n: int) -> None:
        if i % 50 == 0 or i == n:
            print(f"  {i:3d}/{n}  {nome}", flush=True)

    varredura = cf.varrer_hashes(args.base, tarefas=args.tarefas or cf.TAREFAS_PADRAO, progresso=progresso)
    achados = varredura.conflitos
    print()
    print(
        f"recortes: {varredura.recortes:,}  |  imagens distintas: {varredura.imagens_distintas:,}  |  "
        f"copias exatas: {varredura.copias_exatas:,} "
        f"({100 * varredura.copias_exatas / max(1, varredura.recortes):.1f}%)".replace(",", ".")
    )
    print(f"grupos em conflito: {len(achados)}  |  recortes envolvidos: {sum(c.total for c in achados)}")

    quase = None
    if args.quase:
        from ..text import dataset as ds
        from ..text import dedupe

        limiar = args.limiar_quase if args.limiar_quase is not None else dedupe.LIMIAR_PADRAO
        print()
        print(f"medindo a quase-duplicata (limiar {limiar:.2f}, descritor de lado {dedupe.LADO_DESCRITOR})...")
        v = ds.varrer(args.base, tarefas=args.tarefas or ds.TAREFAS_PADRAO, progresso=progresso)
        _, quase = dedupe.agrupar(v.X, v.y, v.grupos, dims=v.dims, limiar=limiar)
        print(
            f"  {quase.grupos_antes:,} grupos exatos -> {quase.grupos_depois:,} grupos  "
            f"({100 * quase.reducao:.1f}% absorvidos, {quase.fundidos:,} fusoes)".replace(",", ".")
        )

    decisoes = cf.ler_decisoes(args.decisoes) if Path(args.decisoes).exists() else {}
    if not decisoes:
        print(f"nenhuma decisao lida de {args.decisoes}: nada pode ser aplicado.")
    plano = cf.conferir(achados, decisoes)

    julgados = [c for c in achados if c.sha256 in decisoes]
    com_vencedor = [c for c in julgados if decisoes[c.sha256].get("vencedor")]
    print(f"  julgados: {len(julgados)}  |  com vencedor: {len(com_vencedor)}  |  "
          f"indecidiveis: {len(julgados) - len(com_vencedor)}")
    if plano.sem_decisao:
        print(f"  SEM DECISAO: {len(plano.sem_decisao)} grupos (o primeiro e {plano.sem_decisao[0][:12]}...)")
    if plano.divergentes:
        print(f"  DIVERGENTES: {len(plano.divergentes)} grupos mudaram no disco desde o julgamento")
        print("    a decisao descreve outra coisa; refaca o julgamento antes de aplicar")

    print()
    for motivo, quantos in sorted(plano.por_motivo.items()):
        print(f"  sairiam por {motivo}: {quantos} recortes")
    print(f"  total: {len(plano.mover)} recortes")

    if args.folha:
        _desenhar_folha(achados, Path(args.base), Path(args.folha), decisoes)
        print(f"\nfolha de contato -> {args.folha}")

    relatorio = Path(args.relatorio) if args.relatorio else METRICAS / f"texto_dedupe_{date.today():%Y%m%d}.json"
    pares = Counter(" x ".join(sorted(c.rotulos)) for c in achados)
    atomic_write_text(
        relatorio,
        json.dumps(
            {
                "quando": date.today().isoformat(),
                "base": caminho_para_relatorio(args.base),
                "recortes": varredura.recortes,
                "imagens_distintas": varredura.imagens_distintas,
                "copias_exatas": varredura.copias_exatas,
                "grupos_em_conflito": len(achados),
                "recortes_em_conflito": sum(c.total for c in achados),
                "julgados": len(julgados),
                "com_vencedor": len(com_vencedor),
                "indecidiveis": len(julgados) - len(com_vencedor),
                "a_mover": {"total": len(plano.mover), **plano.por_motivo},
                "pares": dict(pares.most_common()),
                # O julgamento registrado, e nao so o que sobrou no disco. Depois de `--aplicar`
                # a base fica limpa e `grupos_em_conflito` cai para zero -- e um relatorio que so
                # dissesse isso apagaria a memoria de que os 83 existiram e de como foram
                # decididos. Esta secao e o que sobrevive ao conserto.
                "julgamentos_registrados": {
                    "arquivo": caminho_para_relatorio(args.decisoes),
                    "grupos": len(decisoes),
                    "com_vencedor": sum(1 for d in decisoes.values() if d.get("vencedor")),
                    "indecidiveis": sum(1 for d in decisoes.values() if not d.get("vencedor")),
                    "pares": dict(
                        Counter(" x ".join(sorted(d["rotulos"])) for d in decisoes.values()).most_common()
                    ),
                },
                "quase_duplicata": (
                    {
                        "limiar": quase.limiar,
                        "lado_descritor": 24,
                        "grupos_antes": quase.grupos_antes,
                        "grupos_depois": quase.grupos_depois,
                        "fusoes": quase.fundidos,
                        "maior_grupo": quase.maior_grupo,
                    }
                    if quase is not None
                    else "NAO MEDIDA NESTA CORRIDA. Rode com --quase; o padrao so faz a passada de hash."
                ),
                "decisoes": [
                    {
                        "sha256": c.sha256,
                        "rotulos": c.rotulos,
                        "vencedor": decisoes.get(c.sha256, {}).get("vencedor"),
                        "confianca": decisoes.get(c.sha256, {}).get("confianca"),
                        "motivo": decisoes.get(c.sha256, {}).get("motivo"),
                    }
                    for c in achados
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    print(f"relatorio -> {relatorio}")

    if not args.aplicar:
        print("\n(nada foi movido: use --aplicar)")
        return 0

    manifesto = cf.aplicar(plano, args.base, args.quarentena)
    print()
    print(f"movidos para {args.quarentena}")
    print(f"manifesto -> {manifesto}")
    print(f"para desfazer: cvoff-texto-conflitos --desfazer {manifesto}")
    print("\nA base mudou: rode `cvoff-texto-train --revarrer` para refazer o cache e treinar.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
