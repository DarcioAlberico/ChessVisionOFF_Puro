"""crapper: o CRAP de cada função de `src/`, e a catraca sobre ele (S-801).

`CRAP = cc² × (1 − cobertura)³ + cc`, em que `cc` é a complexidade ciclomática do `radon` e a
cobertura é a fração das linhas executáveis da função (da primeira à última linha dela, como o
`radon` a delimita) que a suíte executou, segundo o JSON do `coverage`. Função toda coberta vale
o próprio `cc`; função sem teste nenhum vale `cc² + cc`.

**Uso.**

    coverage run -m pytest && coverage json        # grava coverage.json na raiz
    python tools/qualidade/crapper.py              # compara com docs/metrics/crap.json
    python tools/qualidade/crapper.py --gravar     # registra o estado atual

A catraca reprova quando o número de funções com CRAP >= 10 sobe, ou quando uma função que não
estava registrada acima de 30 passa a estar. As funções são identificadas por arquivo e nome
qualificado, e não por linha: a linha anda a cada edição acima dela.

O `radon` é dependência de desenvolvimento (extra `dev`) e só é importado por quem mede.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]
REGISTRO = RAIZ / "docs" / "metrics" / "crap.json"
COBERTURA = RAIZ / "coverage.json"

LIMIAR = 10.0
"""Função com CRAP a partir daqui entra no registro, e a contagem delas não pode subir."""

TETO_DO_NOVO = 30.0
"""Nenhuma função que o registro não traga acima disto pode chegar aqui."""


@dataclass(frozen=True)
class Bloco:
    """Uma função como o `radon` a vê: onde mora, onde começa e acaba, e a complexidade."""

    arquivo: str
    funcao: str
    linha: int
    fim: int
    cc: int


@dataclass(frozen=True)
class Medida:
    arquivo: str
    funcao: str
    linha: int
    cc: int
    cobertura: float
    crap: float


@dataclass(frozen=True)
class Linhas:
    """O que o `coverage` sabe de um arquivo: as linhas executáveis que rodaram e as que não."""

    executadas: frozenset[int]
    faltando: frozenset[int]


def crap(cc: int, cobertura: float) -> float:
    return cc * cc * (1.0 - cobertura) ** 3 + cc


def _relativo(caminho: str) -> str:
    return caminho.replace("\\", "/").removeprefix("./")


def ler_cobertura(dados: dict[str, object]) -> dict[str, Linhas]:
    """O JSON do `coverage json` (formato 3), com o caminho de cada arquivo em barra normal."""
    arquivos = dados.get("files")
    if not isinstance(arquivos, dict):
        raise ValueError("JSON de cobertura sem a chave 'files': não é a saída de `coverage json`")
    return {
        _relativo(nome): Linhas(frozenset(info["executed_lines"]), frozenset(info["missing_lines"]))
        for nome, info in arquivos.items()
    }


def cobertura_da_funcao(bloco: Bloco, linhas: Linhas | None) -> float:
    """Fração das linhas executáveis do bloco que rodaram. Arquivo que o `coverage` não viu é 0."""
    if linhas is None:
        return 0.0
    faixa = set(range(bloco.linha, bloco.fim + 1))
    rodaram = len(faixa & linhas.executadas)
    total = rodaram + len(faixa & linhas.faltando)
    return rodaram / total if total else 1.0


def medir(blocos: Iterable[Bloco], cobertura: dict[str, Linhas]) -> list[Medida]:
    """CRAP de cada bloco, do maior para o menor."""
    medidas = []
    for bloco in blocos:
        fracao = cobertura_da_funcao(bloco, cobertura.get(bloco.arquivo))
        medidas.append(
            Medida(
                bloco.arquivo, bloco.funcao, bloco.linha, bloco.cc, round(fracao, 4), round(crap(bloco.cc, fracao), 1)
            )
        )
    medidas.sort(key=lambda m: (-m.crap, m.arquivo, m.linha))
    return medidas


def blocos_do_radon(raiz: Path, pastas: Sequence[str] = ("src",)) -> list[Bloco]:
    """Toda função e método sob `pastas`, closures inclusive, com o nome qualificado do `radon`."""
    from radon.complexity import cc_visit
    from radon.visitors import Function

    # O `add_inner_blocks` do radon chama a closure de um método de `metodo.dentro`, sem a classe:
    # dois métodos homônimos em classes diferentes dariam o mesmo nome. O nome sai daqui.
    def funcoes(bloco: Any, prefixo: str) -> Iterable[tuple[str, Any]]:
        if isinstance(bloco, Function):
            nome = prefixo + bloco.fullname
            yield nome, bloco
            for closure in bloco.closures:
                yield from funcoes(closure, nome + ".")
            return
        for interna in bloco.inner_classes:
            for metodo in interna.methods:
                yield from funcoes(metodo, f"{prefixo}{bloco.name}.")
            yield from funcoes(interna._replace(methods=[]), f"{prefixo}{bloco.name}.")

    blocos = []
    for pasta in pastas:
        for caminho in sorted((raiz / pasta).rglob("*.py")):
            relativo = caminho.relative_to(raiz).as_posix()
            for topo in cc_visit(caminho.read_text(encoding="utf-8")):
                for nome, f in funcoes(topo, ""):
                    blocos.append(Bloco(relativo, nome, f.lineno, f.endline, f.complexity))
    return sorted(blocos, key=lambda b: (b.arquivo, b.linha))


def registro(medidas: Sequence[Medida], meta_da_cobertura: dict[str, object]) -> dict[str, object]:
    acima = [m for m in medidas if m.crap >= LIMIAR]
    return {
        "formula": "CRAP = cc^2 * (1 - cobertura)^3 + cc",
        "limiar": LIMIAR,
        "teto_do_novo": TETO_DO_NOVO,
        "cobertura": {
            "gerada_em": meta_da_cobertura.get("timestamp"),
            "versao_do_coverage": meta_da_cobertura.get("version"),
        },
        "funcoes_medidas": len(medidas),
        "funcoes_acima_do_limiar": len(acima),
        "funcoes_acima_do_teto": sum(m.crap >= TETO_DO_NOVO for m in medidas),
        "funcoes": [asdict(m) for m in acima],
    }


def comparar(registrado: dict[str, object], medidas: Sequence[Medida]) -> list[str]:
    """O que a catraca reprova: mais funções acima do limiar, ou função nova acima do teto."""
    registradas = registrado["funcoes"]
    assert isinstance(registradas, list)
    acima_do_teto = {(f["arquivo"], f["funcao"]) for f in registradas if f["crap"] >= TETO_DO_NOVO}
    falhas = []
    teto = registrado["funcoes_acima_do_limiar"]
    assert isinstance(teto, int)
    agora = sum(m.crap >= LIMIAR for m in medidas)
    if agora > teto:
        falhas.append(f"funções com CRAP >= {LIMIAR:g}: {agora}, e o registro permite {teto}")
    for m in medidas:
        if m.crap >= TETO_DO_NOVO and (m.arquivo, m.funcao) not in acima_do_teto:
            falhas.append(f"{m.arquivo}:{m.linha} {m.funcao}: CRAP {m.crap:g} (cc {m.cc}, cobertura {m.cobertura:.0%})")
    return falhas


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cobertura", type=Path, default=COBERTURA, help="JSON do `coverage json`")
    parser.add_argument("--registro", type=Path, default=REGISTRO)
    parser.add_argument("--gravar", action="store_true", help="grava o estado atual no registro")
    parser.add_argument(
        "--forcar", action="store_true", help="com --gravar, grava mesmo que a catraca reprove (troca de base)"
    )
    parser.add_argument("--mostrar", type=int, default=20, help="quantas das piores funções imprimir")
    args = parser.parse_args(argv)

    inicio = time.perf_counter()
    dados = json.loads(args.cobertura.read_text(encoding="utf-8"))
    medidas = medir(blocos_do_radon(RAIZ), ler_cobertura(dados))
    meta = dados.get("meta", {})
    print(
        f"{len(medidas)} funções, {sum(m.crap >= LIMIAR for m in medidas)} com CRAP >= {LIMIAR:g}, "
        f"{sum(m.crap >= TETO_DO_NOVO for m in medidas)} com CRAP >= {TETO_DO_NOVO:g} "
        f"({time.perf_counter() - inicio:.1f} s)"
    )
    for m in medidas[: args.mostrar]:
        print(f"{m.crap:8.1f} cc={m.cc:3d} cobertura={m.cobertura:4.0%} {m.arquivo}:{m.linha} {m.funcao}")

    falhas = comparar(json.loads(args.registro.read_text(encoding="utf-8")), medidas) if args.registro.exists() else []
    for falha in falhas:
        print("REPROVA:", falha, file=sys.stderr)
    if args.gravar:
        if falhas and not args.forcar:
            print("Nada gravado: a catraca reprova. Conserte, ou --forcar numa troca de base.", file=sys.stderr)
            return 1
        texto = json.dumps(registro(medidas, meta), ensure_ascii=False, indent=1) + "\n"
        args.registro.write_bytes(texto.encode("utf-8"))
        print(f"gravado {args.registro.relative_to(RAIZ).as_posix()}")
        return 0
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
