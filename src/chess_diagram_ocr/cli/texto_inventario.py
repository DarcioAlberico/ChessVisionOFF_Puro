"""`cvoff-texto-inventario` — o manifesto da base de caractere, antes de qualquer treino (S-200).

    cvoff-texto-inventario
    cvoff-texto-inventario --base training_data --minimo 3

**Por que ele vem antes.** O material prometido eram "cerca de 700 mil imagens de todas as
classes já verificadas manualmente". O que chegou são 607.713 recortes em 314 pastas, e as duas
únicas coisas que se sabia sobre eles vinham de varreduras feitas para alimentar o treino -- que
contam, e não gravam nada. O resultado é que **os números desta base já divergem entre
documentos**: o `ROADMAP_TEXTO` diz 178.420 imagens distintas e o relatório de treino gravou
178.370. Nenhum dos dois está errado; são varreduras de momentos diferentes, e nenhuma delas
deixou manifesto. Enquanto isso não existir, toda discussão sobre a base é discussão sobre
lembrança.

## Três regras, e nenhuma é detalhe

**1. O comando não escreve nada dentro da pasta inventariada.** Travado por teste. Um inventário
que mexe no que inventaria é a primeira peça de uma migração acidental.

**2. A leitura é `open()` + `cv2.imdecode`, nunca `cv2.imread`.** No Windows o `imread` devolve
`None` em caminho não-ASCII, indistinguível de "arquivo corrompido" -- e foi assim que a primeira
versão da migração no projeto de origem apagou PNGs válidos. Aqui um PNG ilegível é **contado e
nomeado**, o comando termina com sucesso, e nada é apagado nem movido.

**3. Achado é achado, e não uma linha igual às outras.** Classe vazia, classe abaixo do mínimo e
pasta cujo nome não decodifica saem numa seção própria. Uma classe vazia entre 314 passa
despercebida -- e é exatamente o que aconteceu com a `lower_ä` do projeto de origem, que ficou
vazia porque `cv2.imwrite` devolve `False` em caminho não-ASCII sem levantar erro.

## A procedência entra aqui, mesmo valendo `desconhecida` para tudo (S-201)

O manifesto declara, por classe e no total, quantas amostras são `humano`, `modelo` e
`desconhecida`. Hoje a resposta é 100% `desconhecida`, porque `data/texto_procedencia.csv` não
existe -- e **é essa a informação**: sem ela nenhum número desta base separa rótulo humano de
palpite de classificador. O contrato do arquivo está em `text/procedencia.py`.

Junto vai o aviso de distribuição da S-201: se `digit_1` passar `lower_e` num conjunto que se
declara humano, o comando **avisa com o número ao lado** -- não bloqueia.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from ..config import PROJECT_ROOT
from ..logging_setup import configure_logging
from . import add_verbose, cli_errors

logger = logging.getLogger(__name__)

BASE_PADRAO = PROJECT_ROOT / "training_data"
METRICAS = PROJECT_ROOT / "docs" / "metrics"

TAREFAS_PADRAO = 16
"""O mesmo da varredura de treino: o trabalho é leitura e `cv2`, e os dois soltam a GIL."""

DIMENSOES_LISTADAS = 6
"""Quantas dimensões distintas por classe entram no manifesto, da mais comum para a menos.

Listar todas encheria o arquivo de cauda: nesta base há classes com dezenas de formatos, e o que
decide alguma coisa são as duas ou três que dominam -- mais a **contagem** de distintas, que sai
inteira ao lado."""


@dataclass
class Pasta:
    """Uma pasta da base, contada. `caractere` é `None` quando o nome não decodifica."""

    nome: str
    caractere: str | None
    recortes: int = 0
    bytes_em_disco: int = 0
    ilegiveis: list[str] = field(default_factory=list)
    dimensoes: Counter[str] = field(default_factory=Counter)
    procedencias: Counter[str] = field(default_factory=Counter)
    digests: int = 0
    """Imagens distintas por SHA-256 do arquivo. É a mesma conta que a S-202 usa."""

    def como_dicionario(self) -> dict[str, Any]:
        return {
            "pasta": self.nome,
            "caractere": self.caractere,
            "recortes": self.recortes,
            "imagens_distintas": self.digests,
            "bytes": self.bytes_em_disco,
            "dimensoes_distintas": len(self.dimensoes),
            "dimensoes": dict(self.dimensoes.most_common(DIMENSOES_LISTADAS)),
            "ilegiveis": len(self.ilegiveis),
            "procedencia": dict(self.procedencias),
        }


def _decodificar(caminho: Path) -> tuple[str, bytes | None, tuple[int, int] | None]:
    """`(nome, sha-256 do arquivo, dimensão)`. Dimensão `None` quer dizer "não decodifica".

    **Nunca `cv2.imread`** -- ver a regra 2 no cabeçalho. O `imdecode` está em
    `text.dataset.cv2_imdecode_cinza`, que é o ponto de entrada único dessa regra no projeto.
    """
    from ..text.dataset import cv2_imdecode_cinza

    try:
        with open(caminho, "rb") as arquivo:
            bruto = arquivo.read()
    except OSError:
        return caminho.name, None, None
    imagem = cv2_imdecode_cinza(bruto)
    if imagem is None:
        return caminho.name, hashlib.sha256(bruto).digest(), None
    return caminho.name, hashlib.sha256(bruto).digest(), (int(imagem.shape[0]), int(imagem.shape[1]))


def inventariar_pasta(caminho: Path, *, tarefas: int = TAREFAS_PADRAO, registro: Any = None) -> Pasta:
    """Uma pasta contada, sem escrever nada nela e sem levantar por arquivo ruim."""
    import cv2

    from ..text.classes import NomeDePastaInvalido, char_to_folder, folder_to_char
    from ..text.dataset import procedencia_de

    cv2.setNumThreads(1)  # o paralelismo é nosso, e aninhá-lo derruba a taxa

    try:
        caractere: str | None = folder_to_char(caminho.name, strict=True)
        if caractere is not None and char_to_folder(caractere) != caminho.name:
            caractere = None
    except NomeDePastaInvalido:
        caractere = None

    pasta = Pasta(nome=caminho.name, caractere=caractere)
    arquivos = sorted(caminho.iterdir()) if caminho.is_dir() else []
    vistos: set[bytes] = set()

    with ThreadPoolExecutor(max(1, tarefas)) as executor:
        for nome, digest, dimensao in executor.map(_decodificar, arquivos, chunksize=256):
            alvo = caminho / nome
            try:
                pasta.bytes_em_disco += alvo.stat().st_size
            except OSError:  # pragma: no cover - arquivo sumiu no meio da varredura
                pass
            if digest is None or dimensao is None:
                pasta.ilegiveis.append(f"{caminho.name}/{nome}")
                continue
            pasta.recortes += 1
            vistos.add(digest)
            pasta.dimensoes[f"{dimensao[0]}x{dimensao[1]}"] += 1
            pasta.procedencias[procedencia_de(Path(nome).stem, registro)] += 1

    pasta.digests = len(vistos)
    return pasta


def inventariar(
    base: Path, *, minimo: int = 1, tarefas: int = TAREFAS_PADRAO, registro: Any = None
) -> dict[str, Any]:
    """O manifesto inteiro. **Não escreve nada dentro de `base`.**"""
    from ..text.dataset import BaseVazia

    base = Path(base)
    pastas = sorted(p for p in base.iterdir() if p.is_dir())
    if not pastas:
        raise BaseVazia(f"{base} não tem nenhuma pasta de classe.")

    medidas: list[Pasta] = []
    for posicao, caminho in enumerate(pastas, start=1):
        medida = inventariar_pasta(caminho, tarefas=tarefas, registro=registro)
        medidas.append(medida)
        if posicao % 25 == 0 or posicao == len(pastas):
            logger.info("  %3d/%d  %s", posicao, len(pastas), caminho.name)

    vazias = [m.nome for m in medidas if m.recortes == 0]
    abaixo = [
        {"pasta": m.nome, "recortes": m.recortes}
        for m in medidas
        if 0 < m.recortes < minimo
    ]
    indecifraveis = [m.nome for m in medidas if m.caractere is None]
    ilegiveis = [nome for m in medidas for nome in m.ilegiveis]

    procedencias: Counter[str] = Counter()
    for m in medidas:
        procedencias.update(m.procedencias)

    from ..text import procedencia as pr
    from ..text.dataset import Classe, aviso_de_distribuicao

    aviso = aviso_de_distribuicao(
        [Classe(m.nome, m.caractere or "?", m.recortes, len(m.ilegiveis)) for m in medidas]
    )

    return {
        "quando": f"{date.today():%Y-%m-%d}",
        "base": base.name,
        "pastas": len(medidas),
        "recortes": sum(m.recortes for m in medidas),
        "imagens_distintas_por_classe": sum(m.digests for m in medidas),
        "bytes": sum(m.bytes_em_disco for m in medidas),
        "minimo": minimo,
        # **Os achados vêm antes da tabela**, e não depois: uma classe vazia no meio de 314
        # linhas iguais é uma classe vazia que ninguém vê.
        "achados": {
            "classes_vazias": vazias,
            "classes_abaixo_do_minimo": abaixo,
            "pastas_que_nao_decodificam": indecifraveis,
            "pngs_ilegiveis": len(ilegiveis),
        },
        "pngs_ilegiveis": ilegiveis[:100],
        "procedencia": {valor: int(procedencias.get(valor, 0)) for valor in pr.VALORES},
        "registro_de_procedencia": pr.resumo(registro or {}),
        "aviso_de_distribuicao": aviso,
        "por_classe": [m.como_dicionario() for m in medidas],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventaria a base de caractere e grava o manifesto. Nao escreve na pasta (S-200).",
    )
    parser.add_argument("--base", type=Path, default=BASE_PADRAO, help="Pasta com uma subpasta por classe.")
    parser.add_argument("--saida", type=Path, help="Padrao: docs/metrics/texto_inventario_<data>.json")
    parser.add_argument("--minimo", type=int, default=3, help="Abaixo disto a classe vira achado (padrao 3).")
    parser.add_argument("--tarefas", type=int, default=TAREFAS_PADRAO, help="Threads da leitura.")
    parser.add_argument("--procedencia", type=Path, help="Padrao: data/texto_procedencia.csv, se existir.")
    add_verbose(parser)
    return parser.parse_args(argv)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    from ..text import procedencia as pr

    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    registro = pr.ler(args.procedencia)
    logger.info("Inventariando %s...", args.base)
    manifesto = inventariar(args.base, minimo=args.minimo, tarefas=args.tarefas, registro=registro)

    saida = Path(args.saida) if args.saida else METRICAS / f"texto_inventario_{date.today():%Y%m%d}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(saida, json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")

    # **Dois arquivos, e não um com duas seções.** O manifesto responde "o que há na pasta"; o
    # relatório de procedência responde "quem rotulou isto", que é a pergunta da S-201 e a que
    # decide se um número pode ser publicado. Elas envelhecem em ritmos diferentes -- a primeira
    # muda quando a pasta muda, a segunda quando a origem responde --, e juntá-las faria a
    # segunda parecer atualizada toda vez que a primeira fosse refeita.
    procedencias = METRICAS / f"texto_procedencia_{date.today():%Y%m%d}.json"
    atomic_write_text(
        procedencias,
        json.dumps(
            {
                "quando": manifesto["quando"],
                "base": manifesto["base"],
                "recortes": manifesto["recortes"],
                "registro": manifesto["registro_de_procedencia"],
                "arquivo": str(args.procedencia or pr.CAMINHO_PADRAO.relative_to(PROJECT_ROOT).as_posix()),
                "total": manifesto["procedencia"],
                "aviso_de_distribuicao": manifesto["aviso_de_distribuicao"],
                # **A decisão que falta, nomeada no relatório em vez de numa conversa.** A S-201
                # pede que a resposta sobre a `training_data_2` fique registrada com data e com
                # quem decidiu; enquanto ela não vem, o campo diz que não veio.
                "decisao_sobre_a_origem": {
                    "pergunta": (
                        "a training_data_2 do PyBoxEditor, cujos rótulos a spec de lá declara "
                        "suspeitos de serem do modelo, está dentro desta base?"
                    ),
                    "resposta": None,
                    "decidida_em": None,
                    "por": None,
                },
                "por_classe": [
                    {"pasta": c["pasta"], "procedencia": c["procedencia"]}
                    for c in manifesto["por_classe"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    achados = manifesto["achados"]
    print()
    print(
        f"{manifesto['recortes']:,} recortes em {manifesto['pastas']} pasta(s), "
        f"{manifesto['bytes'] / 1e9:.2f} GB".replace(",", ".")
    )
    print(f"  imagens distintas (somadas por classe): {manifesto['imagens_distintas_por_classe']:,}".replace(",", "."))
    print(f"  procedencia: {manifesto['registro_de_procedencia']}")
    for valor in pr.VALORES:
        print(f"    {valor:14s} {manifesto['procedencia'][valor]:,}".replace(",", "."))

    print()
    print("achados")
    print(f"  classes vazias: {len(achados['classes_vazias'])}")
    if achados["classes_vazias"]:
        print(f"    {', '.join(achados['classes_vazias'][:12])}")
    print(f"  classes abaixo de {manifesto['minimo']} recortes: {len(achados['classes_abaixo_do_minimo'])}")
    if achados["classes_abaixo_do_minimo"]:
        nomes = ", ".join(f"{a['pasta']} ({a['recortes']})" for a in achados["classes_abaixo_do_minimo"][:12])
        print(f"    {nomes}")
    print(f"  pastas que nao decodificam: {len(achados['pastas_que_nao_decodificam'])}")
    if achados["pastas_que_nao_decodificam"]:
        print(f"    {', '.join(achados['pastas_que_nao_decodificam'][:12])}")
    print(f"  PNGs ilegiveis (contados, nao apagados): {achados['pngs_ilegiveis']}")

    if manifesto["aviso_de_distribuicao"]:
        print()
        print(f"AVISO: {manifesto['aviso_de_distribuicao']}")

    print()
    print(f"manifesto-> {saida}")
    print(f"procedencia-> {procedencias}")
    return 0


if __name__ == "__main__":  # pragma: no cover - execução direta
    raise SystemExit(main())
