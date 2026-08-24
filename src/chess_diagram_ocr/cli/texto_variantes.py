"""`cvoff-texto-variantes` — a grade que decide o que entra no treino de verdade (S-204).

    cvoff-texto-variantes --epocas 10
    cvoff-texto-variantes --bracos controle aumento-leve

**O que a S-204 devia.** O item entregou o treino e ficou devendo duas coisas: o aumento de dados
aplicado a caractere, e a grade de variantes. As duas são a mesma pergunta -- *o que mudar no
treino melhora o modelo?* --, e as duas só têm resposta medida.

## A regra que a grade existe para respeitar

**A grade roda no `val`. O `test` é tocado uma vez, pela vencedora, e mais nada.**

Isso não é formalidade: a S-204 mediu o preço de ignorá-la. Nos pesos de classe, o ganho no `val`
foi de +0,0091 e no `test` de +0,0013 -- sete vezes menor. Parte disso é viés de seleção, e é
estrutural: a época é escolhida **porque** maximiza a macro do `val`, então o `val` da época
escolhida é otimista por construção. Quem comparasse braços no `val` e concluísse dali diria
"ajuda" com folga aparente.

## O orçamento é curto, igual para todos, e isso é uma ressalva de verdade

Cada braço é um treino, e um treino completo desta base custa ~26 min de CPU. A grade roda com um
orçamento **fixo e menor** -- o padrão é 10 épocas, contra as 25 da corrida publicada -- porque
seis braços completos custariam uma tarde.

**E a ressalva é a que essa escolha merece:** um aumento de dados costuma pagar tarde, e um
orçamento curto pode inverter a ordem entre um braço que converge rápido e outro que converge
melhor. A tabela diz o orçamento em que foi medida, e a vencedora não é promovida por ela -- ela
é confirmada no `test` e, se for para produção, retreinada com o orçamento cheio. A grade escolhe
**o que** medir a fundo, e não o que publicar.

## Os braços, e por que cada um está aqui

| braço | o que ele testa |
|---|---|
| `controle` | o treino como ele está hoje. Sem ele a tabela não tem zero |
| `aumento-leve` | as sete degradações de scanner e gráfica, na intensidade que o acervo pede |
| `aumento-forte` | o outro lado do joelho -- existe para a curva ter dois pontos, não porque mais seja melhor |
| `pesos-de-classe` | a hipótese que a S-204 já mediu e reprovou, refeita sob este orçamento |
| `densa-128` | a hipótese da S-204 sobre a forma: a densa 2.048→256 são 85% dos parâmetros |
| `canais-menores` | 16→32→64 com densa 128: um quarto dos parâmetros |

**Espelhamento não é braço**, e o motivo está em `text/aumento.py`: um `b` espelhado é um `d`.
É a única transformação do módulo de peças que aqui é ativamente danosa.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from ..atomic_io import atomic_write_text
from ..config import PROJECT_ROOT
from ..logging_setup import configure_logging
from ..text.modelo import ARQUITETURA_PADRAO, Arquitetura
from . import cli_errors

logger = logging.getLogger(__name__)

METRICAS = PROJECT_ROOT / "docs" / "metrics"
BASE_PADRAO = PROJECT_ROOT / "training_data"
CACHE_PADRAO = PROJECT_ROOT / "models" / ".texto_base_cache.npz"

EPOCAS_DA_GRADE = 10
"""O orçamento de cada braço. Ver "O orçamento é curto" no cabeçalho."""


@dataclass(frozen=True)
class Braco:
    """Um braço da grade: um nome, e o que ele muda em relação ao controle."""

    nome: str
    o_que_testa: str
    aumento: str = "desligado"
    pesos_de_classe: bool = False
    arquitetura: Arquitetura = ARQUITETURA_PADRAO

    def como_dicionario(self) -> dict[str, Any]:
        from ..text import aumento as aug

        return {
            "nome": self.nome,
            "o_que_testa": self.o_que_testa,
            "aumento": aug.de_nome(self.aumento).versao,
            "pesos_de_classe": self.pesos_de_classe,
            "arquitetura": self.arquitetura.versao,
            "parametros": self.arquitetura.parametros,
        }


BRACOS: tuple[Braco, ...] = (
    Braco("controle", "o treino como ele esta hoje"),
    Braco("aumento-leve", "as sete degradacoes na intensidade que o acervo pede", aumento="leve"),
    Braco("aumento-forte", "o outro lado do joelho", aumento="forte"),
    Braco("pesos-de-classe", "a hipotese que a S-204 reprovou, sob este orcamento", pesos_de_classe=True),
    Braco("densa-128", "a densa e 85% dos parametros", arquitetura=Arquitetura(densa=128)),
    Braco(
        "canais-menores",
        "um quarto dos parametros",
        arquitetura=Arquitetura(canais=(16, 32, 64), densa=128),
    ),
)

POR_NOME = {braco.nome: braco for braco in BRACOS}


@dataclass
class Preparo:
    """A base partida, igual para todos os braços. **É o que torna a comparação uma comparação.**"""

    varredura: Any
    grupos: np.ndarray
    lado: np.ndarray
    idx_treino: np.ndarray
    idx_val: np.ndarray
    idx_teste: np.ndarray
    resumo_quase: Any = None
    classes_sem_teste: list[str] = field(default_factory=list)


def preparar(args: argparse.Namespace) -> Preparo:
    """Varre (ou lê o cache), agrupa a quase-duplicata e parte -- **do mesmo jeito que o treino**.

    O split é função pura de `(y, grupos, frações, semente)`, e por isso esta função reproduz o
    de `cvoff-texto-train` sem guardá-lo em lugar nenhum. `tests/test_texto_variantes.py` afirma
    que os dois batem: se um dia divergirem, a grade estaria comparando braços sobre outra base
    que não a do treino, e a tabela mediria o split.
    """
    from ..text import dataset as ds
    from ..text import dedupe

    varredura = ds.ler_cache(args.cache) if Path(args.cache).exists() and not args.revarrer else ds.varrer(args.base)
    grupos, resumo_quase = dedupe.agrupar(
        varredura.X, varredura.y, varredura.grupos, dims=varredura.dims, limiar=dedupe.LIMIAR_PADRAO
    )
    lado = ds.split_por_grupo(
        varredura.y,
        grupos,
        fracoes=(max(0.0, 1.0 - args.val - args.teste), args.val, args.teste),
        semente=args.semente,
    )
    vazados = ds.vazamento(grupos, lado)
    if vazados:
        raise ValueError(f"o split deixou {len(vazados)} grupos em mais de um lado; a grade nao roda sobre isso.")

    rep_medicao = ds.representantes(grupos)
    rep_treino = ds.representantes(varredura.grupos)
    tabela = ds.contagem_por_lado(varredura.y[rep_medicao], lado[rep_medicao], len(varredura.classes))
    return Preparo(
        varredura=varredura,
        grupos=grupos,
        lado=lado,
        idx_treino=np.flatnonzero((lado == ds.TREINO) & rep_treino),
        idx_val=np.flatnonzero((lado == ds.VALIDACAO) & rep_medicao),
        idx_teste=np.flatnonzero((lado == ds.TESTE) & rep_medicao),
        resumo_quase=resumo_quase,
        classes_sem_teste=[
            c.pasta for i, c in enumerate(varredura.classes) if tabela[i, ds.TESTE] == 0
        ],
    )


def rodar_braco(braco: Braco, preparo: Preparo, args: argparse.Namespace) -> dict[str, Any]:
    """Um braço treinado com o orçamento da grade, medido **só no `val`**."""
    from ..text import aumento as aug
    from ..text import treino as tr

    comeco = time.perf_counter()
    resultado = tr.treinar(
        preparo.varredura.X,
        preparo.varredura.y,
        preparo.idx_treino,
        preparo.idx_val,
        len(preparo.varredura.classes),
        epocas=args.epocas,
        lote=args.lote,
        taxa=args.taxa,
        paciencia=0,  # **Sem parada antecipada**: orçamento fixo é o que torna os braços comparáveis.
        semente=args.semente,
        device=args.device or "cpu",
        pesos_de_classe=braco.pesos_de_classe,
        aumento=aug.de_nome(braco.aumento),
        arquitetura=braco.arquitetura,
    )
    return {
        **braco.como_dicionario(),
        "val_macro": resultado.metricas["val_macro"],
        "val_acuracia": resultado.metricas["val_acuracia"],
        "temperatura": resultado.temperatura,
        "epoca_escolhida": resultado.melhor,
        "segundos": round(time.perf_counter() - comeco, 1),
        "_estado": resultado.estado,
    }


def emissoes_sem_medida(
    estado: dict[str, Any], preparo: Preparo, args: argparse.Namespace, arquitetura: Arquitetura
) -> dict[str, Any]:
    """Quantas vezes o modelo prevê uma classe que **nenhuma medição alcança**.

    **É o número que decide o que fazer com elas**, e a S-204 pede a decisão sem ele. As classes
    com menos de três imagens distintas caem inteiras no treino: o modelo passa a poder emitir
    esses rótulos e ninguém mediu se ele acerta. Duas saídas são defensáveis -- mantê-las
    declarando `n=0`, ou cortá-las com `--minimo 3` --, e o que separa as duas é isto: se elas
    quase nunca são previstas, mantê-las custa nada; se são, cada emissão é um erro invisível,
    porque não há verdade contra a qual conferi-la.
    """
    from ..text import treino as tr

    sem_teste = set(preparo.classes_sem_teste)
    if not sem_teste or preparo.idx_teste.size == 0:
        return {"previstas": 0, "de": int(preparo.idx_teste.size), "classes": []}

    indices = {
        i for i, c in enumerate(preparo.varredura.classes) if c.pasta in sem_teste
    }
    logits, _ = tr.logits_de(
        estado,
        preparo.varredura.X,
        preparo.varredura.y,
        preparo.idx_teste,
        len(preparo.varredura.classes),
        device=args.device or "cpu",
        lote=args.lote,
        arquitetura=arquitetura,
    )
    previstos = logits.argmax(axis=1)
    quais = [int(i) for i in np.unique(previstos) if int(i) in indices]
    return {
        "previstas": int(sum(int((previstos == i).sum()) for i in indices)),
        "de": int(preparo.idx_teste.size),
        "classes": [preparo.varredura.classes[i].pasta for i in quais],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A grade de variantes do treino de caractere, medida no val (S-204).",
    )
    parser.add_argument("--base", type=Path, default=BASE_PADRAO)
    parser.add_argument("--cache", type=Path, default=CACHE_PADRAO)
    parser.add_argument("--revarrer", action="store_true")
    parser.add_argument("--saida", type=Path, help="Padrao: docs/metrics/texto_variantes_<data>.json")
    parser.add_argument("--bracos", nargs="+", choices=sorted(POR_NOME), help="Padrao: todos.")
    parser.add_argument("--epocas", type=int, default=EPOCAS_DA_GRADE)
    parser.add_argument("--lote", type=int, default=256)
    parser.add_argument("--taxa", type=float, default=1e-3)
    parser.add_argument("--semente", type=int, default=20260823)
    parser.add_argument("--val", type=float, default=0.1)
    parser.add_argument("--teste", type=float, default=0.1)
    parser.add_argument("--device", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    from ..text import treino as tr

    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    escolhidos = [POR_NOME[nome] for nome in (args.bracos or [b.nome for b in BRACOS])]
    preparo = preparar(args)
    print()
    print(
        f"grade de {len(escolhidos)} braco(s), {args.epocas} epocas cada, semente {args.semente}: "
        f"treino {preparo.idx_treino.size:,} | val {preparo.idx_val.size:,} | "
        f"teste {preparo.idx_teste.size:,} (intocado ate a vencedora)".replace(",", ".")
    )
    print()

    linhas: list[dict[str, Any]] = []
    for posicao, braco in enumerate(escolhidos, start=1):
        print(f"[{posicao}/{len(escolhidos)}] {braco.nome}: {braco.o_que_testa}", flush=True)
        linha = rodar_braco(braco, preparo, args)
        linhas.append(linha)
        print(
            f"    val macro {linha['val_macro']:.4f}  acuracia {linha['val_acuracia']:.4f}  "
            f"{linha['segundos']:.0f}s",
            flush=True,
        )

    vencedora = max(linhas, key=lambda linha: linha["val_macro"])
    print()
    print(f"vencedora no val: {vencedora['nome']} (macro {vencedora['val_macro']:.4f})")
    print("confirmando no teste -- e a unica vez que ele e tocado nesta grade...")

    metricas_teste, _ = tr.avaliar_split(
        vencedora["_estado"],
        preparo.varredura.X,
        preparo.varredura.y,
        preparo.idx_teste,
        len(preparo.varredura.classes),
        device=args.device or "cpu",
        lote=args.lote,
        arquitetura=POR_NOME[vencedora["nome"]].arquitetura,
    )
    print(f"  TESTE macro {metricas_teste['macro']:.4f} | acuracia {metricas_teste['acuracia']:.4f}")

    emissoes = emissoes_sem_medida(
        vencedora["_estado"], preparo, args, POR_NOME[vencedora["nome"]].arquitetura
    )
    print(
        f"  classes que nenhuma medicao alcanca: {len(preparo.classes_sem_teste)}; "
        f"previstas {emissoes['previstas']} vez(es) em {emissoes['de']} amostras de teste"
    )
    return _gravar(args, preparo, linhas, vencedora, metricas_teste, emissoes)


def _gravar(
    args: argparse.Namespace,
    preparo: Preparo,
    linhas: list[dict[str, Any]],
    vencedora: dict[str, Any],
    metricas_teste: dict[str, float],
    emissoes: dict[str, Any] | None = None,
) -> int:
    """A tabela em `docs/metrics/`, e a ressalva do orçamento junto com ela."""
    saida = Path(args.saida) if args.saida else METRICAS / f"texto_variantes_{date.today():%Y%m%d}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)

    ordenadas = sorted(linhas, key=lambda linha: -linha["val_macro"])
    relatorio = {
        "quando": f"{date.today():%Y-%m-%d}",
        "base": "training_data",
        "orcamento": {
            "epocas": args.epocas,
            "lote": args.lote,
            "taxa": args.taxa,
            "semente": args.semente,
            "paciencia": 0,
        },
        # **A ressalva vai no arquivo, e não numa nota de rodapé que se perde na citação.**
        "ressalva": (
            f"orcamento fixo de {args.epocas} epocas, contra as 25 da corrida publicada. Um "
            "aumento de dados costuma pagar tarde, e um orcamento curto pode inverter a ordem "
            "entre um braco que converge rapido e outro que converge melhor. A vencedora aqui e "
            "a que merece a corrida cheia, e nao a que deve ser publicada."
        ),
        "amostras": {
            "treino": int(preparo.idx_treino.size),
            "validacao": int(preparo.idx_val.size),
            "teste": int(preparo.idx_teste.size),
        },
        "classes": len(preparo.varredura.classes),
        # A decisão que a S-204 pede sobre as classes que nunca são medidas -- ver `_sem_teste`.
        "classes_sem_teste": {
            "quantas": len(preparo.classes_sem_teste),
            "quais": preparo.classes_sem_teste,
            # **O número que decide entre mantê-las e cortá-las.** Ver `emissoes_sem_medida`.
            "emissoes_no_teste": emissoes or {},
        },
        "bracos": [{k: v for k, v in linha.items() if not k.startswith("_")} for linha in ordenadas],
        "vencedora_no_val": vencedora["nome"],
        "confirmacao_no_teste": {
            "braco": vencedora["nome"],
            "macro": metricas_teste["macro"],
            "acuracia": metricas_teste["acuracia"],
            "amostras": metricas_teste["amostras"],
        },
    }
    atomic_write_text(saida, json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("  braco              val macro   val acuracia   parametros   segundos")
    for linha in ordenadas:
        print(
            f"  {linha['nome']:18s} {linha['val_macro']:9.4f}   {linha['val_acuracia']:12.4f}   "
            f"{linha['parametros']:10,d}   {linha['segundos']:8.0f}".replace(",", ".")
        )
    print()
    print(f"tabela-> {saida}")
    return 0


if __name__ == "__main__":  # pragma: no cover - execução direta
    raise SystemExit(main())
