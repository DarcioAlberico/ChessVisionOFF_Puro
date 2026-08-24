"""`cvoff-texto-train`: treina o classificador de caracteres e grava o par pinado (S-204).

**O comando recusa treinar sobre um split que vaza.** É o critério da S-203 virado em trava: o
split é montado por `dataset.split_por_grupo`, o relatório de vazamento roda logo depois, e um
único grupo em dois lados aborta antes de a primeira época começar. Uma garantia que ninguém
confere é a que quebra calada.

**O que ele grava, e por que os três juntos.** Os pesos (`models/char_classifier.pt`), o
metadado (`models/char_meta.json`) e o relatório (`docs/metrics/texto_treino_<data>.json`). Os
dois primeiros são o par que `modelo.carregar_classificador` confere por hash; o terceiro é o que
permite ler o número meses depois sabendo o que ele mede -- incluindo o que ele **não** mede,
que nesta base é generalização de fonte.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np

from ..atomic_io import atomic_write_text
from ..config import PROJECT_ROOT, caminho_para_relatorio
from ..logging_setup import configure_logging
from . import cli_errors

logger = logging.getLogger(__name__)

BASE_PADRAO = PROJECT_ROOT / "training_data"
CACHE_PADRAO = PROJECT_ROOT / "models" / ".texto_base_cache.npz"
PESOS_PADRAO = PROJECT_ROOT / "models" / "char_classifier.pt"
META_PADRAO = PROJECT_ROOT / "models" / "char_meta.json"
METRICAS = PROJECT_ROOT / "docs" / "metrics"

SEMENTE_PADRAO = 20260823
"""Semente fixa, e escrita aqui em vez de sorteada: duas rodadas com a mesma base e a mesma
semente têm de dar o mesmo split, senão a comparação entre variantes compara sorteios."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Treina o classificador de caracteres sobre training_data/ e grava o par pinado."
    )
    parser.add_argument("--base", type=Path, default=BASE_PADRAO, help="Pasta com uma subpasta por classe.")
    parser.add_argument("--cache", type=Path, default=CACHE_PADRAO, help="Varredura em cache (.npz).")
    parser.add_argument("--revarrer", action="store_true", help="Ignora o cache e varre o disco de novo.")
    parser.add_argument("--so-varrer", action="store_true", help="Varre, relata e para. Nao treina.")
    parser.add_argument("--modelo", type=Path, default=PESOS_PADRAO)
    parser.add_argument("--meta", type=Path, default=META_PADRAO)
    parser.add_argument("--relatorio", type=Path, help="Padrao: docs/metrics/texto_treino_<data>.json")
    parser.add_argument("--epocas", type=int, default=None)
    parser.add_argument("--lote", type=int, default=None)
    parser.add_argument("--taxa", type=float, default=None)
    parser.add_argument("--paciencia", type=int, default=None)
    parser.add_argument("--semente", type=int, default=SEMENTE_PADRAO)
    parser.add_argument("--minimo", type=int, default=1, help="Classes abaixo deste corte ficam de fora.")
    parser.add_argument("--val", type=float, default=0.1, help="Fracao de grupos para validacao.")
    parser.add_argument("--teste", type=float, default=0.1, help="Fracao de grupos para teste.")
    parser.add_argument("--tarefas", type=int, default=None, help="Threads da varredura.")
    parser.add_argument(
        "--sem-quase-duplicata",
        action="store_true",
        help="Parte so pela copia exata. O padrao agrupa tambem as irmas quase iguais (S-202).",
    )
    parser.add_argument(
        "--limiar-quase",
        type=float,
        default=None,
        help="Distancia RMS abaixo da qual duas imagens da mesma classe sao irmas. Padrao: 0,03, medido nesta base.",
    )
    parser.add_argument(
        "--todos-os-recortes",
        action="store_true",
        help="Treina com todos os recortes, inclusive as copias. Padrao: uma imagem por grupo.",
    )
    parser.add_argument(
        "--pesos-de-classe",
        action="store_true",
        help="Pondera a perda pelo inverso da raiz da contagem. Hipotese aberta: a Fase 5 mediu que nao ajudou para pecas.",
    )
    parser.add_argument(
        "--procedencia",
        type=Path,
        help="Registro de procedencia e livro. Padrao: data/texto_procedencia.csv, se existir (S-201).",
    )
    parser.add_argument(
        "--ece",
        type=Path,
        help="Onde gravar a curva de confiabilidade. Padrao: docs/metrics/texto_ece_<data>.json.",
    )
    parser.add_argument(
        "--vazamento",
        type=Path,
        help="Onde gravar o relatorio de vazamento. Padrao: docs/metrics/texto_vazamento.json.",
    )
    parser.add_argument(
        "--so-calibracao",
        action="store_true",
        help="Mede a curva de confiabilidade e o ECE do par ja publicado, e para. Nao treina (S-205).",
    )
    parser.add_argument(
        "--so-split",
        action="store_true",
        help="Parte, grava o relatorio de vazamento e para. Nao treina (S-203).",
    )
    parser.add_argument(
        "--desconhecida-no-teste",
        action="store_true",
        help="Deixa amostra sem procedencia medir o modelo. So faz diferenca com registro no disco.",
    )
    parser.add_argument("--device", default=None, help="cpu ou cuda. Padrao: cuda se houver.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _carregar(args: argparse.Namespace):  # noqa: ANN202 - o tipo mora em text.dataset
    from ..text import dataset as ds

    if not args.revarrer and Path(args.cache).exists():
        print(f"Lendo a varredura em cache de {args.cache}...")
        return ds.ler_cache(args.cache)

    if not Path(args.base).is_dir():
        raise ValueError(f"a base de treino nao esta em {args.base}")

    print(f"Varrendo {args.base}...")

    def progresso(nome: str, i: int, n: int) -> None:
        if i % 25 == 0 or i == n:
            print(f"  {i:3d}/{n}  {nome}", flush=True)

    tarefas = args.tarefas or ds.TAREFAS_PADRAO
    return ds.varrer(args.base, tarefas=tarefas, minimo=args.minimo, progresso=progresso)


def _gravar_ece(args: argparse.Namespace, relatorio: dict) -> Path:
    """Grava a curva de confiabilidade e o ECE, e diz na tela o que eles disseram (S-205).

    O caminho é uma flag pelo mesmo motivo do relatorio de vazamento: uma corrida sobre base
    sintetica nao pode sobrescrever o numero publicado sem que nada diga isso.
    """
    caminho = Path(args.ece) if args.ece else METRICAS / f"texto_ece_{date.today():%Y%m%d}.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(caminho, json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"calibracao: {relatorio['leitura']}")
    print(f"  ECE ponderado    antes {relatorio['antes']['ece']:.4f}  ->  depois {relatorio['depois']['ece']:.4f}")
    print(
        f"  ECE por faixa    antes {relatorio['antes']['ece_por_faixa']:.4f}  ->  "
        f"depois {relatorio['depois']['ece_por_faixa']:.4f}   <- e este que decide"
    )
    if "temperatura_refeita" in relatorio:
        print(
            f"  temperatura publicada {relatorio['temperatura_publicada']:.4f}  "
            f"refeita agora {relatorio['temperatura_refeita']:.4f}"
        )
    print("  faixa de confianca   n      diz      acerta")
    for faixa in relatorio["depois"]["curva"]:
        print(
            f"   {faixa['de']:.2f}-{faixa['ate']:.2f}   {faixa['amostras']:6d}   "
            f"{faixa['confianca']:.4f}   {faixa['acerto']:.4f}"
        )
    print(f"  curva-> {caminho}")
    return caminho


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    from ..text import calibracao as cal
    from ..text import dataset as ds
    from ..text import treino as tr

    varredura = _carregar(args)
    print()
    print(ds.resumo(varredura))
    if varredura.pastas_indecifraveis:
        print(f"  pastas que nao decodificam para caractere: {', '.join(varredura.pastas_indecifraveis)}")
    if varredura.ilegiveis:
        print(f"  PNGs ilegiveis (contados, nao apagados): {len(varredura.ilegiveis)}")

    # A quase-duplicata entra **antes** do split, e e por isso que ela existe: agrupar as irmas
    # depois de partir nao desfaz o vazamento, so o documenta. Ver `text/dedupe.py`.
    grupos = varredura.grupos
    resumo_quase = None
    if not args.sem_quase_duplicata:
        from ..text import dedupe

        limiar = args.limiar_quase if args.limiar_quase is not None else dedupe.LIMIAR_PADRAO
        print(f"agrupando as quase-duplicatas (limiar {limiar:.2f}, descritor de lado {dedupe.LADO_DESCRITOR})...")
        grupos, resumo_quase = dedupe.agrupar(
            varredura.X, varredura.y, varredura.grupos, dims=varredura.dims, limiar=limiar
        )

    # ------------------------------------------------------------- procedencia e livro (S-201/S-203)
    #
    # **A regra e a mesma dos diagramas desde a S-19: amostra sem procedencia nao e recusada, e
    # marcada.** Rotulo de classificador e rotulo desconhecido entram no treino e ficam fora de
    # validacao e de teste -- medir contra um rotulo que ninguem conferiu produz um numero que
    # nao diz nada sobre o modelo.
    #
    # **Sem registro no disco, a regra esvaziaria as duas.** Hoje `data/texto_procedencia.csv`
    # nao existe e as 607.713 amostras sao `desconhecida`: aplicar a regra ao pe da letra
    # deixaria o teste vazio, e um comando que nao mede nao e mais honesto que um que mede com
    # ressalva. Entao o caminho sem registro mede assim mesmo e **grava a ressalva por extenso**,
    # no relatorio de treino e no de vazamento. O dia em que o arquivo chegar, a regra passa a
    # valer sozinha -- e `--desconhecida-no-teste` e o unico jeito de desliga-la, com registro.
    from ..text import procedencia as pr

    registro = pr.ler(args.procedencia)
    print()
    print(f"procedencia: {pr.resumo(registro)}")
    aviso = ds.aviso_de_distribuicao(varredura.classes)
    if aviso:
        print(f"  AVISO: {aviso}")

    nomes = varredura.nomes
    if nomes.size != varredura.total:
        # **Cache gravado antes da S-201**: ele tem os pixels e não tem os nomes, e sem nome
        # nenhum registro casa. O resultado e o mesmo da base de hoje -- tudo desconhecida --,
        # mas por outro motivo, e o motivo tem de aparecer.
        nomes = np.full(varredura.total, "", dtype="<U1")
        if registro:
            print("  ATENCAO: o cache nao guarda os nomes dos arquivos (foi gravado antes da S-201).")
            print("  Rode com --revarrer para o registro de procedencia poder casar com as amostras.")

    codigos = ds.codigos_de_procedencia(nomes, registro)
    livros, nomes_de_livro = ds.livros_de(nomes, registro)
    if registro and not args.desconhecida_no_teste:
        pode_medir = codigos >= pr.CODIGO[pr.HUMANO]
    else:
        pode_medir = np.ones(varredura.total, dtype=bool)
        if registro:
            print("  --desconhecida-no-teste: amostra sem procedencia vai medir o modelo.")

    fracoes = (max(0.0, 1.0 - args.val - args.teste), args.val, args.teste)
    tipo_de_split = "grupo de copia exata"
    ressalva = "NAO por livro -- a base nao registra livro de origem"
    try:
        if not registro or livros.max(initial=-1) < 0:
            raise ds.BaseVazia("sem registro de livro")
        lado = ds.split_por_livro(
            varredura.y, grupos, livros, fracoes=fracoes, semente=args.semente
        )
        tipo_de_split = "livro"
        ressalva = "livros inteiros em validacao e teste; o teste tem livro que o treino nao viu"
    except ds.BaseVazia as motivo:
        lado = ds.split_por_grupo(
            varredura.y, grupos, medivel=pode_medir, fracoes=fracoes, semente=args.semente
        )
        if registro:
            print(f"  split por livro indisponivel ({motivo}); caiu para o split por grupo.")

    # A trava da S-203: o relatorio de vazamento roda **antes** do treino, e um grupo em dois
    # lados aborta. Nao e aviso.
    vazados = ds.vazamento(grupos, lado)
    if vazados:
        raise ValueError(
            f"o split deixou {len(vazados)} grupos de copia exata em mais de um lado "
            f"(o primeiro e o grupo {vazados[0]}). Treinar sobre isso mede a memoria do modelo, "
            "e e exatamente o defeito que a S-203 existe para impedir."
        )

    # E a trava gemea, para o split por livro: um livro em dois lados desfaz o unico teste que
    # mede generalizacao de fonte, e desfaz em silencio.
    livros_vazados = ds.livros_em_dois_lados(livros, lado)
    if livros_vazados:
        raise ValueError(
            f"o split deixou {len(livros_vazados)} livro(s) em mais de um lado. O teste do "
            "'livro novo' e a razao de ser do split por livro (S-203)."
        )

    # **Treino e medicao contam grupos diferentes, e a diferenca e deliberada.**
    #
    # Val e teste contam **um por grupo de quase-duplicata**: se cinco imagens sao a mesma
    # renderizacao, elas tem de pesar uma vez, senao a metrica mede o tamanho do agrupamento.
    #
    # O treino conta **um por copia exata**, que e mais grosso: as irmas quase-iguais diferem de
    # verdade (ate 0,03 de distancia RMS) e sao amostra legitima -- elas so nao podem *atravessar*
    # o split, e disso quem cuida e `split_por_grupo`, que ja recebeu os grupos fundidos. Contar
    # o treino por quase-duplicata jogaria fora 23% das imagens distintas sem ganho nenhum.
    rep_medicao = ds.representantes(grupos)
    rep_treino = ds.representantes(varredura.grupos)
    idx_treino = np.flatnonzero((lado == ds.TREINO) & (rep_treino | args.todos_os_recortes))
    # **A S-201 filtra aqui, e não no split.** No split por livro o livro é atômico: tirar a
    # amostra não-medível do teste e deixá-la no treino poria o mesmo livro dos dois lados, que
    # é o vazamento que aquele split existe para impedir. Ela fica do lado que o livro dela
    # ficou, e simplesmente **não entra na conta**.
    idx_val = np.flatnonzero((lado == ds.VALIDACAO) & rep_medicao & pode_medir)
    idx_teste = np.flatnonzero((lado == ds.TESTE) & rep_medicao & pode_medir)

    tabela = ds.contagem_por_lado(varredura.y[rep_medicao], lado[rep_medicao], len(varredura.classes))
    sem_teste = int((tabela[:, ds.TESTE] == 0).sum())
    conflitos = ds.grupos_em_conflito(varredura.y, varredura.grupos)
    # **A contagem é sobre o que de fato entra**, e não sobre o lado inteiro: val e teste medem
    # um recorte por grupo de quase-duplicata, então contar os 59.721 recortes do lado do teste
    # diria uma coisa e a métrica mediria outra.
    por_lado_procedencia = {
        nome: {valor: int((codigos[indices] == pr.CODIGO[valor]).sum()) for valor in pr.VALORES}
        for nome, indices in (("treino", idx_treino), ("validacao", idx_val), ("teste", idx_teste))
    }
    so_no_teste = sorted(
        {nomes_de_livro[i] for i in np.unique(livros[lado == ds.TESTE]) if i >= 0}
        - {nomes_de_livro[i] for i in np.unique(livros[lado == ds.TREINO]) if i >= 0}
    )

    print()
    print(
        f"split por {tipo_de_split}: treino {idx_treino.size:,} | val {idx_val.size:,} "
        f"| teste {idx_teste.size:,}".replace(",", ".")
    )
    print("  grupos em dois lados: 0 (conferido antes de treinar)")
    print(f"  imagens distintas na base: {int(np.unique(varredura.grupos).size):,}".replace(",", "."))
    if resumo_quase is not None:
        print(
            f"  quase-duplicata: {resumo_quase.grupos_antes:,} grupos exatos -> "
            f"{resumo_quase.grupos_depois:,} grupos ({100 * resumo_quase.reducao:.1f}% absorvidos)".replace(",", ".")
        )
    else:
        print("  quase-duplicata: DESLIGADA (--sem-quase-duplicata): irmas podem atravessar o split")
    print(f"  classes sem nenhuma imagem distinta em teste: {sem_teste} de {len(varredura.classes)}")
    if conflitos.size:
        print(f"  grupos com a mesma imagem sob dois rotulos: {conflitos.size} (travados no treino)")
    if tipo_de_split == "livro":
        print(f"  livros: {len(nomes_de_livro)}; so no teste: {', '.join(so_no_teste) or 'nenhum'}")
        print(f"  amostras sem livro (ficam no treino): {int((livros < 0).sum()):,}".replace(",", "."))
    else:
        print("  o split e por copia exata, NAO por livro: esta base nao tem livro de origem")
        print("  registrado, entao nenhum numero abaixo mede generalizacao de fonte.")
    print(f"  procedencia no teste: {por_lado_procedencia['teste']}")

    # **O relatorio de vazamento e gravado sempre, e antes do treino.** A S-203 pede que ele
    # rode de verdade e vire criterio de aceite -- e um relatorio que so existe quando alguem
    # treina o modelo inteiro nao roda de verdade. `--so-split` produz este arquivo em um minuto,
    # a partir do cache, e e o que o `cvoff-audit` le.
    vazamento_json = {
        "quando": f"{date.today():%Y-%m-%d}",
        "base": caminho_para_relatorio(args.base),
        "split": tipo_de_split,
        "ressalva": ressalva,
        "semente": args.semente,
        "amostras": {
            "treino": int(idx_treino.size),
            "validacao": int(idx_val.size),
            "teste": int(idx_teste.size),
        },
        "grupos_em_dois_lados": len(vazados),
        "livros_em_dois_lados": len(livros_vazados),
        "livros": {
            "total": len(nomes_de_livro),
            "so_no_teste": so_no_teste,
            "sem_livro": int((livros < 0).sum()),
        },
        "procedencia_por_lado": por_lado_procedencia,
        "registro_de_procedencia": pr.resumo(registro),
        "desconhecida_no_teste_permitida": bool(args.desconhecida_no_teste),
    }
    # **O caminho é uma flag, e isso não é conforto.** Uma corrida sobre base sintética -- de
    # teste, ou de conferência -- sobrescrevia o relatório publicado e o `cvoff-audit` passava a
    # auditar a base de mentira sem que nada dissesse isso.
    caminho_vazamento = Path(args.vazamento) if args.vazamento else METRICAS / "texto_vazamento.json"
    caminho_vazamento.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        caminho_vazamento, json.dumps(vazamento_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  vazamento-> {caminho_vazamento}")

    if args.so_split:
        print()
        print("--so-split: parando antes do treino.")
        return 0

    if args.so_varrer:
        print()
        print("--so-varrer: parando antes do treino.")
        return 0

    device = args.device
    if device is None:
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"

    epocas = args.epocas if args.epocas is not None else tr.EPOCAS_PADRAO
    lote = args.lote if args.lote is not None else tr.LOTE_PADRAO
    taxa = args.taxa if args.taxa is not None else tr.TAXA_PADRAO
    paciencia = args.paciencia if args.paciencia is not None else tr.PACIENCIA_PADRAO

    if args.so_calibracao:
        # **Mede o par que está publicado, e não um que este comando acabou de treinar.** A
        # curva da S-205 descreve o modelo que o programa usa; refazer o treino para produzi-la
        # daria a curva de outro modelo, com a mesma cara.
        import torch

        from ..text import modelo as md

        classificador = md.carregar_classificador(args.meta, args.modelo, device=device)
        estado = torch.load(args.modelo, map_location=device)
        logits, verdade = tr.logits_de(
            estado, varredura.X, varredura.y, idx_val, len(varredura.classes), device=device, lote=lote
        )
        publicada = classificador.meta.temperatura
        relatorio_ece = cal.relatorio(logits, verdade, publicada)
        # **A temperatura refeita é a trava do item posta em número.** Se ela divergir da
        # publicada, o metadado está descrevendo outro modelo -- que é o defeito de processo que
        # a S-205 inteira existe para impedir.
        relatorio_ece["temperatura_publicada"] = publicada
        relatorio_ece["temperatura_refeita"] = cal.calibrar(logits, verdade)
        relatorio_ece["modelo_sha256"] = classificador.meta.modelo_sha256
        relatorio_ece["split"] = tipo_de_split
        _gravar_ece(args, relatorio_ece)
        return 0

    print()
    fonte = "todos os recortes" if args.todos_os_recortes else "uma imagem distinta por copia exata"
    print(f"treinando {len(varredura.classes)} classes em {device}: {epocas} epocas, lote {lote}, taxa {taxa}")
    print(f"  treino sobre {fonte}: {idx_treino.size:,} amostras".replace(",", "."))
    print(f"  a epoca e salva pela recall macro (classes com {tr.MINIMO_PARA_MACRO}+ em val); a acuracia vai ao lado")
    print()

    def mostrar(epoca: tr.Epoca) -> None:
        print(
            f"  epoca {epoca.numero:2d}/{epocas}  perda {epoca.perda:.4f}  "
            f"macro {epoca.macro:.4f}  acuracia {epoca.acuracia:.4f}  {epoca.segundos:.0f}s",
            flush=True,
        )

    resultado = tr.treinar(
        varredura.X,
        varredura.y,
        idx_treino,
        idx_val,
        len(varredura.classes),
        epocas=epocas,
        lote=lote,
        taxa=taxa,
        paciencia=paciencia,
        semente=args.semente,
        device=device,
        pesos_de_classe=args.pesos_de_classe,
        callback=mostrar,
    )

    print()
    print(f"melhor epoca: {resultado.melhor} (macro {resultado.metricas['val_macro']:.4f})")
    print(f"calibracao: {cal.esperanca_de_confianca(resultado.temperatura)}")
    if resultado.calibracao and not resultado.calibracao.get("falhou"):
        _gravar_ece(args, {**resultado.calibracao, "split": tipo_de_split})
    elif resultado.calibracao.get("falhou"):
        print("  a calibracao FALHOU: o modelo sai com temperatura 1,0. O rastro esta no log.")

    metricas_teste, recalls = tr.avaliar_split(
        resultado.estado, varredura.X, varredura.y, idx_teste, len(varredura.classes), device=device, lote=lote
    )
    print()
    print(f"TESTE  macro {metricas_teste['macro']:.4f} | acuracia {metricas_teste['acuracia']:.4f} "
          f"| {metricas_teste['amostras']:,} imagens distintas".replace(",", "."))

    extra = {
        "base": caminho_para_relatorio(args.base),
        "amostras": {"treino": int(idx_treino.size), "validacao": int(idx_val.size), "teste": int(idx_teste.size)},
        "imagens_distintas": int(np.unique(varredura.grupos).size),
        "grupos_em_conflito": int(conflitos.size),
        "treinou_com_copias": bool(args.todos_os_recortes),
        "procedencia": {
            valor: int((codigos == pr.CODIGO[valor]).sum()) for valor in pr.VALORES
        },
        "procedencia_por_lado": por_lado_procedencia,
        "split": f"{tipo_de_split}; {ressalva}",
        "copias_exatas": varredura.copias_exatas,
        "quase_duplicata": (
            None
            if resumo_quase is None
            else {
                "limiar": resumo_quase.limiar,
                "lado_descritor": 24,
                "grupos_antes": resumo_quase.grupos_antes,
                "grupos_depois": resumo_quase.grupos_depois,
                "fusoes": resumo_quase.fundidos,
                "maior_grupo": resumo_quase.maior_grupo,
            }
        ),
        "metricas": {
            "val_macro": resultado.metricas["val_macro"],
            "val_acuracia": resultado.metricas["val_acuracia"],
            "teste_macro": metricas_teste["macro"],
            "teste_acuracia": metricas_teste["acuracia"],
        },
    }
    meta = tr.gravar_checkpoint(resultado, varredura.classes, args.modelo, args.meta, extra=extra)
    print()
    print(f"pesos   -> {args.modelo}")
    print(f"metadado-> {args.meta}  ({meta['num_classes']} classes, temperatura {meta['temperatura']:.4f})")

    relatorio = Path(args.relatorio) if args.relatorio else METRICAS / f"texto_treino_{date.today():%Y%m%d}.json"
    relatorio.parent.mkdir(parents=True, exist_ok=True)
    por_classe = [
        {
            "pasta": c.pasta,
            "caractere": c.caractere,
            "total": c.total,
            "treino": int(tabela[i, ds.TREINO]),
            "val": int(tabela[i, ds.VALIDACAO]),
            "teste": int(tabela[i, ds.TESTE]),
            "recall_teste": None if np.isnan(recalls[i]) else float(recalls[i]),
        }
        for i, c in enumerate(varredura.classes)
    ]
    atomic_write_text(
        relatorio,
        json.dumps(
            {
                **extra,
                "treinado_em": meta["treinado_em"],
                "modelo_sha256": meta["modelo_sha256"],
                "temperatura": meta["temperatura"],
                "epocas": [vars(e) for e in resultado.historico],
                "epoca_escolhida": resultado.melhor,
                "hiperparametros": {
                    "epocas": epocas,
                    "lote": lote,
                    "taxa": taxa,
                    "paciencia": paciencia,
                    "semente": args.semente,
                    "pesos_de_classe": bool(args.pesos_de_classe),
                    "device": device,
                },
                "ilegiveis": varredura.ilegiveis,
                "pastas_indecifraveis": varredura.pastas_indecifraveis,
                "por_classe": por_classe,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"relatorio-> {relatorio}")

    if not Path(args.cache).exists() or args.revarrer:
        ds.gravar_cache(args.cache, varredura)
        print(f"cache    -> {args.cache}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
