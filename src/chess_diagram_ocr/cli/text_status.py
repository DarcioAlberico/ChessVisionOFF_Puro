"""`cvoff-texto-status` — o que do plano de texto já existe no disco (S-178 a S-216).

    cvoff-texto-status                 # tudo, agrupado por fase
    cvoff-texto-status --fase 25       # só uma fase
    cvoff-texto-status --pendentes     # só o que falta
    cvoff-texto-status --json          # para a CI

**O que ele responde, e o que ele não responde.** Ele olha o disco: arquivo no lugar, símbolo
definido, extra declarado. Sonda atendida quer dizer *o código foi escrito*, não *o item está
pronto* -- quem verifica o critério de aceite é a suíte, e um item com sonda verde e teste
vermelho é um item quebrado. A saída diz "sonda atendida" por isso.

**Ele não lê o documento para decidir.** A marcação escrita na `docs/SPEC_TEXTO.md` é intenção;
o disco é fato. Comparar os dois é trabalho de `tests/test_text_status.py`, que falha quando eles
discordam -- e é essa trava que impede a marcação do documento de virar enfeite.

O código de saída é 0 mesmo com tudo pendente: um plano por fazer é o estado normal de um plano,
e falhar aqui ensinaria a ignorar o comando. Quem quiser um portão usa `--exigir`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import IO

from ..logging_setup import configure_logging
from ..text_status import (
    ESTADOS,
    MANIFESTO,
    RAIZ,
    SIMBOLO_DE_ESTADO,
    TITULO_DA_FASE,
    Resultado,
    marcacoes_da_spec,
    resumo,
    verificar,
)
from . import EXIT_FAILURE, add_verbose, cli_errors

FASES = sorted(TITULO_DA_FASE)


def _so_ascii(stream: IO[str] | None = None) -> bool:
    """O console consegue escrever `✅ ◐ ⬜`?

    **Sem esta pergunta o comando levanta em vez de responder.** O `cmd.exe` da máquina em que
    este projeto roda usa cp1252, e `print("⬜")` ali é `UnicodeEncodeError` -- a falha não é
    cosmética, é o comando inteiro caindo. O `configure_logging` já tenta reconfigurar os fluxos
    para UTF-8 (é o mesmo defeito, do lado do log); quando ele não consegue -- console antigo,
    saída já embrulhada --, o traço vira ASCII em vez de o comando morrer.
    """
    alvo = stream if stream is not None else sys.stdout
    codificacao = getattr(alvo, "encoding", None)
    if not codificacao:
        return False
    try:
        "".join(SIMBOLO_DE_ESTADO.values()).encode(codificacao)
    except (LookupError, UnicodeEncodeError):
        return True
    return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diz quais itens do plano de reconhecimento de texto já existem no disco (S-178 a S-216).",
        epilog=(
            "Sonda atendida quer dizer que o codigo foi escrito, nao que o item passa no criterio "
            "de aceite -- esse esta na docs/SPEC_TEXTO.md e quem o verifica e a suite."
        ),
    )
    parser.add_argument("--raiz", type=Path, default=RAIZ, help="Raiz do repositório a inspecionar.")
    parser.add_argument("--fase", type=int, choices=FASES, help="Restringe a uma fase.")
    parser.add_argument("--pendentes", action="store_true", help="Só o que ainda não está inteiro.")
    parser.add_argument("--json", action="store_true", help="Saída legível por máquina.")
    parser.add_argument(
        "--exigir",
        metavar="S-NNN",
        action="append",
        help="Falha (código 1) se o item não estiver com todas as sondas atendidas. Repetível.",
    )
    parser.add_argument("--sondas", action="store_true", help="Mostra cada sonda e o que ela respondeu.")
    add_verbose(parser)
    return parser.parse_args(argv)


def _linha(resultado: Resultado, *, com_sondas: bool, ascii_puro: bool) -> list[str]:
    item = resultado.item
    linhas = [f"  {resultado.simbolo(ascii_puro=ascii_puro)}  {item.id}  {item.titulo}"]
    if com_sondas:
        for sonda in item.sondas:
            marca = "sim" if sonda in resultado.atendidas else "nao"
            linhas.append(f"          [{marca}] {sonda}")
    elif resultado.estado == "parcial":
        linhas.append(f"          falta: {', '.join(resultado.faltando)}")
    return linhas


def _texto(
    resultados: list[Resultado], *, com_sondas: bool, marcado: dict[str, str], ascii_puro: bool = False
) -> str:
    saida: list[str] = []
    for fase in FASES:
        da_fase = [r for r in resultados if r.item.fase == fase]
        if not da_fase:
            continue
        contagem = resumo(da_fase)
        saida.append("")
        traco = "-" if ascii_puro else "—"
        saida.append(
            f"Fase {fase} {traco} {TITULO_DA_FASE[fase]}   ({contagem['feito']}/{len(da_fase)} com sonda atendida)"
        )
        for resultado in da_fase:
            saida.extend(_linha(resultado, com_sondas=com_sondas, ascii_puro=ascii_puro))

    total = resumo(resultados)
    saida.append("")
    saida.append(
        f"Total: {total['feito']} atendidas, {total['parcial']} parciais, "
        f"{total['pendente']} pendentes, de {len(resultados)} itens."
    )

    divergentes = _divergencias(resultados, marcado)
    if divergentes:
        saida.append("")
        saida.append("A spec e o disco discordam nestes itens (tests/test_text_status.py falha por isso):")
        saida.extend(f"  {linha}" for linha in divergentes)
    return "\n".join(saida)


def _divergencias(resultados: list[Resultado], marcado: dict[str, str]) -> list[str]:
    """Item cuja marcação na spec não corresponde ao que as sondas acharam.

    A regra é assimétrica de propósito. `implementada` com sonda pendente é o defeito que este
    comando existe para pegar -- o documento afirmando o que não há. `planejada` com sonda
    atendida é o caso benigno de quem escreveu o código antes de atualizar o cabeçalho, e ele
    também aparece, porque a spec desatualizada é a que ninguém confia.
    """
    fora = []
    for resultado in resultados:
        declarado = marcado.get(resultado.item.id)
        if declarado is None:
            fora.append(f"{resultado.item.id}: sem seção na spec")
            continue
        esperado = {"feito": "implementada", "parcial": "parcial", "pendente": "planejada"}[resultado.estado]
        if declarado != esperado:
            fora.append(f"{resultado.item.id}: a spec diz '{declarado}' e o disco diz '{esperado}'")
    return fora


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)
    raiz = Path(args.raiz)

    resultados = verificar(raiz, fase=args.fase)
    if args.pendentes:
        resultados = [r for r in resultados if r.estado != "feito"]

    try:
        marcado = marcacoes_da_spec(raiz)
    except OSError:  # pragma: no cover - repositorio sem a spec
        marcado = {}

    if args.json:
        print(
            json.dumps(
                {
                    "itens": [
                        {
                            "id": r.item.id,
                            "fase": r.item.fase,
                            "titulo": r.item.titulo,
                            "estado": r.estado,
                            "atendidas": list(r.atendidas),
                            "faltando": list(r.faltando),
                            "spec": marcado.get(r.item.id),
                        }
                        for r in resultados
                    ],
                    "resumo": resumo(resultados),
                    "divergencias": _divergencias(resultados, marcado),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(_texto(resultados, com_sondas=args.sondas, marcado=marcado, ascii_puro=_so_ascii()))

    if args.exigir:
        conhecidos = {r.item.id: r for r in verificar(raiz)}
        faltando = []
        for pedido in args.exigir:
            resultado = conhecidos.get(pedido)
            if resultado is None:
                faltando.append(f"{pedido}: não está no manifesto")
            elif resultado.estado != "feito":
                faltando.append(f"{pedido}: {resultado.estado} ({', '.join(resultado.faltando)})")
        if faltando:
            print("")
            print("Exigido e não atendido:")
            for linha in faltando:
                print(f"  {linha}")
            return EXIT_FAILURE

    return 0


__all__ = ["ESTADOS", "MANIFESTO", "main", "parse_args"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
