"""`cvoff-texto-estilo-classificador` -- o classificador de estilo da palavra e o portão dele (S-662, S-663).

    cvoff-texto-estilo-classificador --json docs/metrics/texto_estilo_classificador.json

Treina uma rede pequena no conjunto da S-661 (`data/estilo/palavras.npz`) e a julga **fora do
livro**, nas duas populações que a S-663 pede: o render limpo do teste, e o mesmo teste degradado
como um scan (`estilo.degradar`, com semente fixa).

## Um livro de fora por rodada, e não a divisão fixa

O acervo dá sete livros com os dois estilos na camada. A divisão fixa da S-661 (70/10/20 por livro)
deixava o teste com **um** livro e 15 itálicos -- abaixo do que o portão julga --, e nenhum
negrito-itálico. O protocolo é o da medição de 2026-08-29 (`text/negrito.py`): **um livro de fora
por rodada**. Em cada rodada um livro é o teste, o seguinte na ordem é a validação -- onde o corte
de confiança é escolhido -- e os outros treinam; cada palavra é testada uma vez, sempre por uma
rede que nunca viu o livro dela, e as contas das rodadas se somam.

## O que decide

A régua é **precisão por classe**, com o corte de confiança escolhido na **validação** -- que também
é fora do livro -- e julgado no teste:

| uso | régua |
|---|---|
| aplicar sem perguntar | precisão >= 0,9929 (S-213) |
| sugerir | precisão >= 0,95 e cobertura >= 0,50 (R4) |

E duas medições de controle, de acerto global, que dizem se a rede aprendeu peso e não tamanho:
**chutar normal** e **chutar pela altura** da palavra. Se ela não vencer as duas, aprendeu o tamanho.
Se não passar na régua de sugerir, a Fase 96 termina aqui e a recusa da ROADMAP_EDITOR volta com o
número novo -- e o pincel manual (S-241) continua sendo a resposta.

## O que ele grava

O relatório, sempre; os pesos em `models/estilo_palavra.pt` (fora do git, como os outros), com a
semente, as classes e o resumo do conjunto -- para o relatório e os pesos dizerem do que vieram.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from ..atomic_io import atomic_write_text
from ..config import PROJECT_ROOT
from ..logging_setup import configure_logging
from ..text import estilo
from . import add_verbose, cli_errors

logger = logging.getLogger(__name__)

SEMENTE = 661
CONJUNTO_PADRAO = PROJECT_ROOT / "data" / "estilo" / "palavras.npz"
PESOS_PADRAO = PROJECT_ROOT / "models" / "estilo_palavra.pt"
SUPORTE_MINIMO = 20
"""Abaixo de quantas palavras de uma classe no teste o portão não a julga: a precisão de cinco
marcadas é sorte, e o relatório diz "sem amostra" em vez de um número."""

NORMAIS_POR_ESTILO = 3
"""Em cada época, quantas palavras `normal` entram por palavra de estilo. O acervo é 90% normal, e
sem isso a rede gasta o treino aprendendo a classe que já acerta chutando."""


def _rede(classes: int = len(estilo.CLASSES)):  # noqa: ANN202 - torch.nn.Module, importado tarde
    import torch
    from torch import nn

    class Rede(nn.Module):
        """Quatro convoluções e a média e o máximo **só sobre a largura útil** da palavra.

        Sem a máscara, a média contaria o papel acrescentado, e a rede aprenderia o comprimento da
        palavra -- outro tamanho disfarçado, como a altura que a S-663 manda vencer.
        """

        def __init__(self) -> None:
            super().__init__()
            canais = (1, 24, 48, 96, 128)
            camadas: list[nn.Module] = []
            for i in range(4):
                camadas += [nn.Conv2d(canais[i], canais[i + 1], 3, padding=1), nn.BatchNorm2d(canais[i + 1]), nn.ReLU()]
                if i < 3:
                    camadas.append(nn.MaxPool2d(2))
            self.corpo = nn.Sequential(*camadas)
            self.cabeca = nn.Sequential(nn.Dropout(0.2), nn.Linear(canais[-1] * 2, classes))

        def forward(self, x: torch.Tensor, larguras: torch.Tensor) -> torch.Tensor:
            f = self.corpo(x).mean(dim=2)  # (B, C, W')
            colunas = f.shape[-1]
            uteis = torch.clamp(torch.ceil(larguras.float() * colunas / estilo.LARGURA_MAXIMA), min=1)
            mascara = (torch.arange(colunas, device=x.device)[None, :] < uteis[:, None]).float()[:, None, :]
            media = (f * mascara).sum(-1) / mascara.sum(-1)
            maximo = (f - (1 - mascara) * 1e4).amax(-1)
            return self.cabeca(torch.cat([media, maximo], 1))

    return Rede()


def _tensor(imagens: np.ndarray):  # noqa: ANN202
    import torch

    return torch.from_numpy((255 - imagens.astype(np.float32))[:, None] / 255.0)


def probabilidades(rede: Any, imagens: np.ndarray, larguras: np.ndarray, *, lote: int = 512) -> np.ndarray:
    import torch

    rede.eval()
    saidas = []
    with torch.no_grad():
        for i in range(0, len(imagens), lote):
            x = _tensor(imagens[i : i + lote])
            w = torch.from_numpy(larguras[i : i + lote].astype(np.int64))
            saidas.append(torch.softmax(rede(x, w), 1).numpy())
    return np.concatenate(saidas) if saidas else np.zeros((0, len(estilo.CLASSES)), np.float32)


def degradado(imagens: np.ndarray, semente: int) -> np.ndarray:
    """O teste como um scan: cada palavra degradada uma vez, com semente fixa. Determinístico."""
    aleatorio = np.random.default_rng(semente)
    return np.stack([estilo.degradar(img, aleatorio) for img in imagens]) if len(imagens) else imagens


def treinar(
    dados: dict[str, np.ndarray], treino: np.ndarray, validacao: np.ndarray, *, epocas: int, semente: int
) -> tuple[Any, list[dict[str, float]]]:
    """Treina nos índices de `treino` e guarda o melhor estado pela perda em `validacao` (sem ela, o último)."""
    import torch
    from torch import nn

    torch.manual_seed(semente)
    aleatorio = np.random.default_rng(semente)
    rede = _rede()
    otimizador = torch.optim.Adam(rede.parameters(), lr=1e-3, weight_decay=1e-4)
    classes = dados["classes"]
    contagem = np.bincount(classes[treino], minlength=len(estilo.CLASSES)).astype(np.float64)
    peso = torch.tensor(1.0 / np.sqrt(np.maximum(contagem, 1.0)), dtype=torch.float32)
    perda_fn = nn.CrossEntropyLoss(weight=peso / peso.mean())
    estilos = treino[classes[treino] != 0]
    normais = treino[classes[treino] == 0]
    melhor, estado, historico = float("inf"), None, []
    for epoca in range(epocas):
        rede.train()
        quantos = min(len(normais), NORMAIS_POR_ESTILO * max(1, len(estilos)))
        indices = np.concatenate([estilos, aleatorio.choice(normais, quantos, replace=False)])
        aleatorio.shuffle(indices)
        comeco, soma = time.perf_counter(), 0.0
        for i in range(0, len(indices), 128):
            lote = indices[i : i + 128]
            imagens = dados["imagens"][lote].copy()
            for k in range(len(imagens)):
                if aleatorio.random() < 0.5:
                    imagens[k] = estilo.degradar(imagens[k], aleatorio)
            x = _tensor(imagens)
            w = torch.from_numpy(dados["larguras"][lote].astype(np.int64))
            y = torch.from_numpy(classes[lote].astype(np.int64))
            otimizador.zero_grad()
            perda = perda_fn(rede(x, w), y)
            perda.backward()
            otimizador.step()
            soma += perda.item() * len(lote)
        p = probabilidades(rede, dados["imagens"][validacao], dados["larguras"][validacao])
        verdade = classes[validacao]
        perda_val = float(-np.mean(np.log(np.maximum(p[np.arange(len(verdade)), verdade], 1e-9)))) if len(verdade) else 0.0
        acerto_val = float((p.argmax(1) == verdade).mean()) if len(verdade) else 0.0
        historico.append(
            {"epoca": epoca + 1, "perda_treino": round(soma / max(1, len(indices)), 4), "perda_validacao": round(perda_val, 4),
             "acerto_validacao": round(acerto_val, 4), "segundos": round(time.perf_counter() - comeco, 1)}
        )
        logger.info("época %d: %s", epoca + 1, historico[-1])
        if perda_val < melhor or not len(validacao):
            melhor, estado = perda_val, {k: v.clone() for k, v in rede.state_dict().items()}
    if estado is not None:
        rede.load_state_dict(estado)
    return rede, historico


Dobra = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
"""Uma rodada: `(probabilidades na validação, verdade na validação, no teste, verdade no teste)`."""


def julgar(p_val: np.ndarray, y_val: np.ndarray, p_teste: np.ndarray, y_teste: np.ndarray) -> dict[str, Any]:
    """As duas réguas numa rodada só. Ver `julgar_dobras`."""
    return julgar_dobras([(p_val, y_val, p_teste, y_teste)])


def julgar_dobras(dobras: list[Dobra]) -> dict[str, Any]:
    """As duas réguas, por classe de estilo, somadas sobre as rodadas. Pura (sobre arrays).

    Em cada rodada o corte sai da validação **dela**, e é aplicado ao teste dela; as marcadas, as
    certas e as que havia se somam. A rodada cuja validação não chega à régua não marca nada no
    teste dela -- as palavras daquele livro contam como não sugeridas, que é o que aconteceria.
    """
    saida: dict[str, Any] = {}
    for indice, nome in enumerate(estilo.CLASSES):
        if indice == 0:
            continue
        havia = sum(int((y == indice).sum()) for _pv, _yv, _p, y in dobras)
        sem_corte = _somar(estilo.regua(p, y, indice, 0.0) for _pv, _yv, p, y in dobras)
        linha: dict[str, Any] = {"no_teste": havia, "sem_corte": {"precisao": _r(sem_corte.precisao), "cobertura": _r(sem_corte.cobertura)}}
        for uso, regua in (("sugerir", estilo.REGUA_DE_SUGERIR), ("aplicar", estilo.REGUA_DE_APLICAR)):
            cortes = [estilo.corte_para(pv, yv, indice, regua) for pv, yv, _p, _y in dobras]
            medida = _somar(
                estilo.regua(p, y, indice, corte) if corte is not None else estilo.Regua(0, 0, int((y == indice).sum()))
                for corte, (_pv, _yv, p, y) in zip(cortes, dobras, strict=True)
            )
            passa = (
                havia >= SUPORTE_MINIMO
                and medida.precisao is not None
                and medida.precisao >= regua
                and (uso == "aplicar" or (medida.cobertura or 0.0) >= estilo.COBERTURA_DE_SUGERIR)
            )
            linha[uso] = {
                "cortes": [None if c is None else round(c, 4) for c in cortes],
                "marcadas": medida.marcadas,
                "precisao": _r(medida.precisao),
                "cobertura": _r(medida.cobertura),
                "passa": bool(passa),
            }
            if havia < SUPORTE_MINIMO:
                linha[uso]["motivo"] = f"sem amostra: {havia} no teste, o mínimo é {SUPORTE_MINIMO}"
        saida[nome] = linha
    return saida


def _somar(reguas: Any) -> estilo.Regua:
    lista = list(reguas)
    return estilo.Regua(sum(r.marcadas for r in lista), sum(r.certas for r in lista), sum(r.havia for r in lista))


def _r(valor: float | None) -> float | None:
    return None if valor is None else round(valor, 4)


def carregar(caminho: Path) -> dict[str, np.ndarray]:
    bruto = np.load(caminho, allow_pickle=False)
    particoes = dict(zip(bruto["identidades"].tolist(), bruto["particoes"].tolist(), strict=True))
    identidades = bruto["identidades"]
    return {
        "imagens": bruto["imagens"],
        "larguras": bruto["larguras"],
        "alturas": bruto["alturas"],
        "classes": bruto["classes"].astype(np.int64),
        "livros": bruto["livros"].astype(np.int64),
        "identidades": identidades,
        "particao": np.asarray([particoes[identidades[i]] for i in bruto["livros"]]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--conjunto", type=Path, default=CONJUNTO_PADRAO, help="O npz da S-661 (padrao: data/estilo/palavras.npz).")
    parser.add_argument("--epocas", type=int, default=6, help="Epocas de treino por rodada (padrao: 6).")
    parser.add_argument("--pesos", type=Path, default=PESOS_PADRAO, help="Onde gravar os pesos (padrao: models/estilo_palavra.pt).")
    parser.add_argument("--json", type=Path, help="Grava o relatorio neste caminho.")
    add_verbose(parser)
    return parser


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)
    import torch

    from ..checkpoint import git_commit, git_worktree_dirty

    if not Path(args.conjunto).exists():
        print(f"Sem o conjunto em {args.conjunto}: rode antes o cvoff-texto-estilo-conjunto.")
        return 0
    torch.set_num_threads(max(1, torch.get_num_threads()))
    dados = carregar(Path(args.conjunto))
    resumo = hashlib.sha1(Path(args.conjunto).read_bytes()).hexdigest()[:12]
    classes, alturas, livros = dados["classes"], dados["alturas"], dados["livros"]
    total = len(dados["identidades"])

    limpas: list[Dobra] = []
    degradadas: list[Dobra] = []
    acertos = {"limpo": [], "degradado": []}
    altura_prevista: list[str] = []
    verdade_toda: list[str] = []
    rodadas = []
    por_palavra_ms = 0.0
    for k in range(total):
        teste = np.flatnonzero(livros == k)
        val = np.flatnonzero(livros == (k + 1) % total)
        treino = np.flatnonzero((livros != k) & (livros != (k + 1) % total))
        rede, historico = treinar(dados, treino, val, epocas=args.epocas, semente=SEMENTE + k)
        p_val = probabilidades(rede, dados["imagens"][val], dados["larguras"][val])
        p_val_deg = probabilidades(rede, degradado(dados["imagens"][val], SEMENTE + 100 + k), dados["larguras"][val])
        comeco = time.perf_counter()
        p_limpo = probabilidades(rede, dados["imagens"][teste], dados["larguras"][teste])
        por_palavra_ms = max(por_palavra_ms, 1000 * (time.perf_counter() - comeco) / max(1, len(teste)))
        p_deg = probabilidades(rede, degradado(dados["imagens"][teste], SEMENTE + 200 + k), dados["larguras"][teste])
        y_val, y_teste = classes[val], classes[teste]
        limpas.append((p_val, y_val, p_limpo, y_teste))
        degradadas.append((p_val_deg, y_val, p_deg, y_teste))
        acertos["limpo"].extend((p_limpo.argmax(1) == y_teste).tolist())
        acertos["degradado"].extend((p_deg.argmax(1) == y_teste).tolist())
        nomes_treino = [estilo.CLASSES[c] for c in classes[treino]]
        altura_prevista.extend(estilo.chutar_pela_altura(alturas[treino].tolist(), nomes_treino, alturas[teste].tolist()))
        verdade_toda.extend(estilo.CLASSES[c] for c in y_teste)
        rodadas.append({
            "teste": str(dados["identidades"][k]),
            "validacao": str(dados["identidades"][(k + 1) % total]),
            "palavras_no_teste": len(teste),
            "acerto_limpo": round(float((p_limpo.argmax(1) == y_teste).mean()), 4) if len(teste) else None,
            "treino": historico,
        })
        logger.info("rodada %d de %d: %s", k + 1, total, {c: v for c, v in rodadas[-1].items() if c != "treino"})

    controle = {
        "chutar_normal": round(estilo.acerto(["normal"] * len(verdade_toda), verdade_toda), 4),
        "chutar_pela_altura": round(estilo.acerto(altura_prevista, verdade_toda), 4),
    }
    populacoes = {
        "limpo": {"acerto": round(float(np.mean(acertos["limpo"])), 4), "por_classe": julgar_dobras(limpas)},
        "degradado": {"acerto": round(float(np.mean(acertos["degradado"])), 4), "por_classe": julgar_dobras(degradadas)},
    }
    vence_o_controle = all(pop["acerto"] > max(controle.values()) for pop in populacoes.values())
    julgaveis = [n for n in estilo.CLASSES[1:] if populacoes["limpo"]["por_classe"][n]["no_teste"] >= SUPORTE_MINIMO]
    # Por classe, nas duas populações: a S-665 trata o itálico sozinho, e um negrito que não passa não
    # deve segurar um itálico que passa -- nem o contrário esconder o negrito que reprovou.
    sugerir = {
        n: vence_o_controle and all(populacoes[p]["por_classe"][n]["sugerir"]["passa"] for p in populacoes) for n in julgaveis
    }
    aplicar = {
        n: vence_o_controle and all(populacoes[p]["por_classe"][n]["aplicar"]["passa"] for p in populacoes) for n in julgaveis
    }
    passam = [n for n, ok in sugerir.items() if ok]
    veredito = {
        "vence_o_controle": vence_o_controle,
        "classes_julgadas": julgaveis,
        "sugerir_por_classe": sugerir,
        "aplicar_por_classe": aplicar,
        "decisao": (
            f"passa na regua de sugerir para {', '.join(passam)}: a S-664 pode abrir para essa(s) classe(s), e e mudanca de formato (R5)"
            if passam
            else "nao passa na regua de sugerir: a Fase 96 termina aqui, e o pincel manual (S-241) continua sendo a resposta"
        ),
    }

    pesos = None
    if passam:
        # Só quem passou ganha pesos: a rede final treina com **todos** os livros, o número de épocas
        # das rodadas e sem validação -- o portão já foi medido acima, fora do livro.
        rede, _ = treinar(dados, np.arange(len(classes)), np.zeros(0, np.int64), epocas=args.epocas, semente=SEMENTE)
        args.pesos.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {"estado": rede.state_dict(), "classes": list(estilo.CLASSES), "altura": estilo.ALTURA,
             "largura_maxima": estilo.LARGURA_MAXIMA, "semente": SEMENTE, "conjunto": resumo, "commit": git_commit()},
            args.pesos,
        )
        pesos = str(args.pesos.name)
    relatorio = {
        "item": "S-662 e S-663 · o classificador de estilo da palavra e o portão",
        "medido_em": date.today().isoformat(),
        "codigo": {"commit": git_commit(), "arvore_suja": git_worktree_dirty()},
        "conjunto": {"arquivo": str(args.conjunto.name), "resumo": resumo, "palavras": len(classes), "livros": total},
        "protocolo": "um livro de fora por rodada: o livro k e o teste, o k+1 a validacao (o corte), os outros treinam; as contas se somam",
        "semente": SEMENTE,
        "epocas_por_rodada": args.epocas,
        "rodadas": rodadas,
        "pesos": pesos,
        "custo_ms_por_palavra_cpu": round(por_palavra_ms, 3),
        "controle": controle,
        "populacoes": populacoes,
        "veredito": veredito,
    }
    print(f"teste: {len(classes)} palavras em {total} rodadas; acerto limpo {populacoes['limpo']['acerto']}, degradado {populacoes['degradado']['acerto']}; "
          f"controle {controle}")
    for nome in estilo.CLASSES[1:]:
        linha = populacoes["limpo"]["por_classe"][nome]
        print(f"  {nome}: {linha['no_teste']} no teste; sugerir {linha['sugerir']}; aplicar {linha['aplicar']}")
    print(veredito["decisao"])
    if args.json:
        atomic_write_text(args.json, json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
        print(f"Relatorio em {args.json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
