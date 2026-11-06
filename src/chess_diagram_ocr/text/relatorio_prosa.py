"""O relatório da régua da prosa: agrega os registros de folha, sem texto de livro nenhum (S-706, S-705, S-713).

**Entra JSONL com texto, sai JSON só com números e identidades.** O relatório vai para `docs/metrics/`, num repositório
público: as palavras erradas viram contagem por família, e nunca exemplo. Sem I/O: quem lê e grava é o `cli/texto_prosa.py`.

**A prata nunca se soma ao ouro**, e todo número dela leva `"uso": "ordenação"`: `compilar_bloco` recusa folhas de
conjuntos, splits ou perfis diferentes num bloco só, e `relatorio_prosa.rotular` carimba cada dicionário com número.

**O teste sai mais curto.** Sem `por_livro`, sem livro de origem na taxonomia, e o CLI não imprime número por folha:
quem o abre não pode ver para que lado ajustar. O pior livro sai como número, sem dizer qual (seção 3 do roadmap).

**Tempo em chave separada.** Toda chave de tempo começa por `segundos_`, e é por esse prefixo que `achatar` as tira:
duas corridas têm de sair idênticas fora elas. O tempo destas corridas não julga o G4, que se mede na janela com a máquina
parada.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from . import regua_prosa as regua
from .prata import USO as USO_DA_PRATA

PRATA = "prata"
OURO = "ouro"
TESTE = "teste"

PARES_PADRAO: tuple[tuple[str, str], ...] = (
    ("fusao", "glifo"),
    ("camada_prosa", "glifo"),
    ("fusao", "tess"),
    ("tess", "tess_oraculo"),
    ("fusao", "suite"),
    ("suite", "glifo"),
    ("suite", "tess"),
)
"""Calculados quando os dois motores estão no bloco. O par pedido a mais entra por `--pares a-b`."""

_CHAVES_DE_NUMERO = ("cer_", "wer_", "delta_pp", "figurina_")


def _r(valor: float, casas: int = 5) -> float:
    return round(float(valor), casas)


def filtrar(registros: Sequence[dict[str, Any]], filtro: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Os subconjuntos publicados saem daqui, e não de seleção à mão: `(ficam, fora com o motivo)`.

    `sem_folha_perdida` tira a folha em que o glifo achou ≤ 2 linhas e a camada ≥ 10; `oraculo_max`, a de oráculo acima do
    limite (a regra da prata); `so_livro`, `sem_livro` e `estrato` fazem o que dizem. O filtro vai escrito no bloco.
    """
    conhecidos = {"sem_folha_perdida", "oraculo_max", "so_livro", "sem_livro", "estrato"}
    desconhecidos = set(filtro) - conhecidos
    if desconhecidos:
        raise ValueError(f"filtro desconhecido: {sorted(desconhecidos)}")
    ficam, fora = [], []
    for r in registros:
        motivo = ""
        if filtro.get("so_livro") and r["identidade"] not in filtro["so_livro"]:
            motivo = "so_livro"
        elif r["identidade"] in filtro.get("sem_livro", ()):
            motivo = "sem_livro"
        elif filtro.get("estrato") and r.get("estrato") != filtro["estrato"]:
            motivo = "estrato"
        elif filtro.get("sem_folha_perdida") and r["n_linhas"]["glifo"] <= 2 and r["n_linhas"]["ref"] >= 10:
            motivo = "folha perdida pelo leiaute"
        elif filtro.get("oraculo_max") is not None and "tess_oraculo|tip" in r["placar"]:
            p = r["placar"]["tess_oraculo|tip"]
            if p["erros"]["prosa"] / max(1, p["total"]["prosa"]) > float(filtro["oraculo_max"]):
                motivo = f"oraculo acima de {filtro['oraculo_max']}"
        if motivo:
            fora.append({"identidade": r["identidade"], "folha": r["folha"], "motivo": motivo})
        else:
            ficam.append(r)
    return ficam, fora


def _motores(registros: Sequence[dict[str, Any]]) -> list[str]:
    comuns = set(registros[0]["hip"])
    for r in registros[1:]:
        comuns &= set(r["hip"])
    return [m for m in registros[0]["hip"] if m in comuns]


def _classe_erros(registros: Sequence[dict[str, Any]], motor: str, modo: str, classe: str) -> tuple[list[int], list[int]]:
    placares = [r["placar"][f"{motor}|{modo}"] for r in registros]
    return [p["erros"].get(classe, 0) for p in placares], [p["total"].get(classe, 0) for p in placares]


def _linha_do_motor(registros: Sequence[dict[str, Any]], motor: str, modo: str) -> dict[str, Any]:
    placares = [r["placar"][f"{motor}|{modo}"] for r in registros]
    livros = [r["identidade"] for r in registros]
    erros, totais = _classe_erros(registros, motor, modo, regua.PROSA)
    ponto, baixo, alto = regua.ic95(erros, totais, livros)
    wer = {k: sum(p["wer"][k] for p in placares) for k in "sdin"}
    figura = {k: sum(p["fig"][k] for p in placares) for k in ("ref", "hip", "tp")}

    def taxa(classe: str) -> float:
        e, t = _classe_erros(registros, motor, modo, classe)
        return sum(e) / max(1, sum(t))

    achadas = [
        regua.palavras_achadas(regua.normalizar(r["ref"], modo, r["lingua"]), regua.normalizar(r["hip"][motor], modo, r["lingua"]), r["lingua"])
        for r in registros
    ]

    return {
        "cer_prosa": _r(ponto),
        "ic95_prosa_dois_niveis": [_r(baixo), _r(alto)],
        "wer_prosa_sdi": _r((wer["s"] + wer["d"] + wer["i"]) / max(1, wer["n"])),
        "wer_partes": wer,
        "cer_notacao": _r(taxa(regua.NOTACAO)),
        "cer_outro": _r(taxa(regua.OUTRO)),
        "cer_ruido": _r(taxa(regua.RUIDO)),
        "cer_espaco": _r(taxa(regua.ESPACO)),
        "insercoes": sum(p["insercoes"] for p in placares),
        "figurina_revocacao": _r(figura["tp"] / max(1, figura["ref"])),
        "figurina_precisao": _r(figura["tp"] / max(1, figura["hip"])),
        "palavras_de_prosa_achadas_em_qualquer_ordem": _r(sum(a for a, _ in achadas) / max(1, sum(t for _, t in achadas))),
    }


def _taxonomia(registros: Sequence[dict[str, Any]], motor: str, *, com_livros: bool) -> dict[str, Any]:
    familias: Counter[str] = Counter()
    origem: dict[str, Counter[str]] = defaultdict(Counter)
    for r in registros:
        for chave, n in r["placar"][f"{motor}|{regua.TIP}"]["trocas"].items():
            ref, _, hip = chave.partition(" -> ")
            if not any(c.isalpha() for c in ref):
                continue
            familia = regua.familia(ref, hip)
            familias[familia] += n
            origem[familia][r["identidade"]] += n
    total = sum(familias.values())
    saida: dict[str, Any] = {"palavras_erradas": total, "familias": {}}
    for familia, n in familias.most_common():
        item: dict[str, Any] = {"palavras": n, "fracao": _r(n / max(1, total), 4)}
        if com_livros:
            item["livros"] = dict(origem[familia].most_common())
        saida["familias"][familia] = item
    return saida


def _par(registros: Sequence[dict[str, Any]], a: str, b: str, classe: str) -> dict[str, Any]:
    ea, ta = _classe_erros(registros, a, regua.TIP, classe)
    eb, tb = _classe_erros(registros, b, regua.TIP, classe)
    ponto, baixo, alto = regua.diferenca_pareada(ea, ta, eb, tb, [r["identidade"] for r in registros])
    return {
        "delta_pp": _r(ponto * 100, 3),
        "ic95_pp": [_r(baixo * 100, 3), _r(alto * 100, 3)],
        "folhas_melhores": sum(x < y for x, y in zip(ea, eb, strict=True)),
        "folhas_piores": sum(x > y for x, y in zip(ea, eb, strict=True)),
    }


def _guarda_de_notacao(registros: Sequence[dict[str, Any]], motor: str) -> dict[str, Any]:
    """G1(a) e G2 do motor contra o glifo: a figurina que chega, fora os vetos registrados, e o acerto pareado dela.

    G1(a) é presença, sem referência; G2 é revocação e precisão contra a referência, e o piso é do limite inferior.
    """
    presentes = sum(r["preservacao"][motor][0] for r in registros)
    total = sum(r["preservacao"][motor][1] for r in registros)
    vetos = sum(len(r.get("vetos", {}).get(motor, ())) for r in registros)
    livros = [r["identidade"] for r in registros]

    def par(campo: str) -> dict[str, Any]:
        def erros(m: str) -> tuple[list[int], list[int]]:
            figuras = [r["placar"][f"{m}|{regua.TIP}"]["fig"] for r in registros]
            return [f[campo] - f["tp"] for f in figuras], [f[campo] for f in figuras]

        em, tm = erros(motor)
        eg, tg = erros("glifo")
        ponto, baixo, alto = regua.diferenca_pareada(em, tm, eg, tg, livros)
        # Erro a menos é acerto a mais: o sinal inverte, e o intervalo troca de ponta.
        return {"delta_pp": _r(-ponto * 100, 3), "ic95_pp": [_r(-alto * 100, 3), _r(-baixo * 100, 3)]}

    return {
        "g1a_figurinas": total,
        "g1a_vetos_registrados": vetos,
        "g1a_chegam_identicas": presentes,
        "g1a_fracao_fora_dos_vetos": _r(min(1.0, presentes / max(1, total - vetos)), 4),
        "g2_revocacao": par("ref"),
        "g2_precisao": par("hip"),
    }


def _cer_de(registros: Sequence[dict[str, Any]], motor: str) -> float:
    erros, totais = _classe_erros(registros, motor, regua.TIP, regua.PROSA)
    return sum(erros) / max(1, sum(totais))


def _por_livro(registros: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in registros:
        grupos[r["identidade"]].append(r)
    return grupos


def _perda_de_leiaute(registros: Sequence[dict[str, Any]], *, por_livro: bool) -> dict[str, Any] | None:
    """S-713: CER(leitor nas caixas do glifo) − CER(leitor nas caixas da camada), com IC pareado, e `tess_pagina` ao lado."""
    motores = _motores(registros)
    if "tess" not in motores or "tess_oraculo" not in motores:
        return None
    saida: dict[str, Any] = {
        "o_que_e": "CER de prosa (tess) - CER de prosa (tess_oraculo), mesmas folhas; negativo é permitido",
        **_par(registros, "tess", "tess_oraculo", regua.PROSA),
        "cer_tess": _r(_cer_de(registros, "tess")),
        "cer_tess_oraculo": _r(_cer_de(registros, "tess_oraculo")),
    }
    if "tess_pagina" in motores:
        saida["cer_tess_pagina"] = _r(_cer_de(registros, "tess_pagina"))
    if por_livro:
        saida["por_livro"] = {}
        for livro, folhas in _por_livro(registros).items():
            item = {**_par(folhas, "tess", "tess_oraculo", regua.PROSA), "cer_tess": _r(_cer_de(folhas, "tess")),
                    "cer_tess_oraculo": _r(_cer_de(folhas, "tess_oraculo"))}
            if "tess_pagina" in motores:
                item["cer_tess_pagina"] = _r(_cer_de(folhas, "tess_pagina"))
            saida["por_livro"][livro] = item
    return saida


def _segundos(registros: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    motores = sorted({m for r in registros for m in r.get("tempo", {})})
    media, p95 = {}, {}
    for m in motores:
        valores = sorted(r["tempo"][m] for r in registros if m in r.get("tempo", {}))
        media[m] = _r(sum(valores) / max(1, len(valores)), 3)
        p95[m] = _r(valores[min(len(valores) - 1, int(len(valores) * 0.95))], 3)
    return {"segundos_por_folha": media, "segundos_por_folha_p95": p95}


def _codigo_das_folhas(registros: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """`codigo.pacote` e `codigo.commit` de cada folha, agrupados: uma corrida normal é um grupo só."""
    grupos: dict[tuple[str, str, bool], list[str]] = defaultdict(list)
    for r in registros:
        c = r["codigo"]
        grupos[(c["commit"], c["pacote"], bool(c["src_sujo"]))].append(f"{r['identidade']}:{r['folha']}")
    return [{"commit": k[0], "pacote": k[1], "src_sujo": k[2], "folhas": v} for k, v in grupos.items()]


def rotular(dados: Any, uso: str) -> Any:
    """Carimba `uso` em todo dicionário que traz número da régua: a prata não pode ser citada sem a palavra."""
    if isinstance(dados, dict):
        saida = {k: rotular(v, uso) for k, v in dados.items()}
        if any(str(k).startswith(_CHAVES_DE_NUMERO) for k in dados):
            saida["uso"] = uso
        return saida
    if isinstance(dados, list):
        return [rotular(v, uso) for v in dados]
    return dados


def compilar_bloco(
    registros: Sequence[dict[str, Any]],
    *,
    filtro: Mapping[str, Any] | None = None,
    pares: Iterable[tuple[str, str]] = (),
) -> dict[str, Any]:
    """Um conjunto do relatório. Levanta se os registros vêm de conjuntos, splits ou perfis diferentes."""
    filtro = dict(filtro or {})
    ficam, fora = filtrar(registros, filtro)
    if not ficam:
        raise ValueError("o filtro não deixou folha nenhuma")
    origens = {(r["conjunto"], r["split"], r["perfil"]) for r in ficam}
    if len(origens) != 1:
        raise ValueError(f"um bloco é de um conjunto só, e a prata nunca se soma ao ouro: {sorted(origens)}")
    conjunto, split, perfil = origens.pop()
    teste = conjunto == OURO and split == TESTE
    motores = _motores(ficam)
    referencia = motores[0]
    wer = [r["placar"][f"{referencia}|{regua.TIP}"]["wer"]["n"] for r in ficam]
    total = {
        c: sum(r["placar"][f"{referencia}|{regua.TIP}"]["total"].get(c, 0) for r in ficam)
        for c in (regua.PROSA, regua.NOTACAO, regua.RUIDO)
    }
    bloco: dict[str, Any] = {
        "conjunto": conjunto,
        "split": split,
        "perfil": perfil,
        "uso": _uso(conjunto, split, perfil),
        "filtro": filtro,
        "fora_pelo_filtro": fora,
        "folhas": len(ficam),
        "livros": len({r["identidade"] for r in ficam}),
        "caracteres_de_prosa": total[regua.PROSA],
        "palavras_de_prosa": sum(wer),
        "caracteres_de_notacao": total[regua.NOTACAO],
        "caracteres_de_ruido": total[regua.RUIDO],
        "linhas_da_camada_fora_por_cruzar_diagrama": sum(r["n_linhas"]["ref_no_diagrama"] for r in ficam),
        "folhas_perdidas_pelo_leiaute": sum(r["n_linhas"]["glifo"] <= 2 and r["n_linhas"]["ref"] >= 10 for r in ficam),
        "motores": {m: {modo: _linha_do_motor(ficam, m, modo) for modo in regua.MODOS} for m in motores},
        "avisos": dict(Counter(a for r in ficam for v in r.get("avisos", {}).values() for a in v)),
        "preservacao_de_figurina_do_glifo": {
            m: _r(sum(r["preservacao"][m][0] for r in ficam) / max(1, sum(r["preservacao"][m][1] for r in ficam)), 4)
            for m in motores
            if all(m in r.get("preservacao", {}) for r in ficam) and m != "glifo"
        },
        "taxonomia": {m: _taxonomia(ficam, m, com_livros=not teste) for m in motores},
        "codigo_das_folhas": _codigo_das_folhas(ficam),
    }
    if "glifo" in motores:
        guardas = {m: _guarda_de_notacao(ficam, m) for m in motores if m != "glifo" and all(m in r.get("preservacao", {}) for r in ficam)}
        if guardas:
            bloco["guarda_de_notacao"] = guardas
    bloco["pares"] = {}
    pedidos = list(dict.fromkeys([*PARES_PADRAO, *pares]))
    for a, b in pedidos:
        if a in motores and b in motores:
            for classe in (regua.PROSA, regua.NOTACAO):
                bloco["pares"][f"{a} - {b} ({classe})"] = _par(ficam, a, b, classe)
    estratos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in ficam:
        estratos[r["estrato"]].append(r)
    bloco["por_estrato"] = {
        e: {
            "folhas": len(v),
            "livros": len({r["identidade"] for r in v}),
            "motores": {m: _resumo_de_cer(v, m) for m in motores},
        }
        for e, v in sorted(estratos.items())
    }
    perda = _perda_de_leiaute(ficam, por_livro=not teste)
    if perda is not None:
        bloco["perda_de_leiaute"] = perda
    grupos = _por_livro(ficam)
    if teste:
        bloco["pior_livro_sem_nome"] = {m: {"cer_prosa": _r(max(_cer_de(v, m) for v in grupos.values()))} for m in motores}
    else:
        bloco["por_livro"] = {
            livro: {
                "lingua": v[0]["lingua"],
                "estrato": v[0]["estrato"],
                "folhas": [r["folha"] for r in v],
                "motores": {m: {"cer_prosa": _r(_cer_de(v, m))} for m in motores},
            }
            for livro, v in grupos.items()
        }
    bloco.update(_segundos(ficam))
    return rotular(bloco, USO_DA_PRATA) if conjunto == PRATA else bloco


def _resumo_de_cer(registros: Sequence[dict[str, Any]], motor: str) -> dict[str, Any]:
    erros, totais = _classe_erros(registros, motor, regua.TIP, regua.PROSA)
    ponto, baixo, alto = regua.ic95(erros, totais, [r["identidade"] for r in registros])
    return {"cer_prosa": _r(ponto), "ic95_prosa_dois_niveis": [_r(baixo), _r(alto)]}


def _uso(conjunto: str, split: str, perfil: str) -> str:
    if conjunto == PRATA:
        return USO_DA_PRATA
    if perfil:
        return "robustez: fatia degradada, sem calibração contra scan real (S-704), nunca somada ao ouro"
    if split == TESTE:
        return "linha de base no teste, aberta uma vez pelo G100; nada se ajusta olhando isto"
    return "dev contaminado: desenvolver e diagnosticar, nenhum portão"


def achatar(dados: Any, prefixo: str = "") -> dict[str, Any]:
    """As chaves escalares de um JSON, `a.b.0.c`, **fora as `segundos_*`**: é o que duas corridas têm de ter igual."""
    saida: dict[str, Any] = {}
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            if str(chave).startswith("segundos_"):
                continue
            saida.update(achatar(valor, f"{prefixo}{chave}."))
    elif isinstance(dados, list):
        for i, valor in enumerate(dados):
            saida.update(achatar(valor, f"{prefixo}{i}."))
    else:
        saida[prefixo.rstrip(".")] = dados
    return saida


def diferencas(a: Any, b: Any) -> list[str]:
    """As chaves que diferem entre dois relatórios, fora o tempo. Vazio é a saída da S-706."""
    pa, pb = achatar(a), achatar(b)
    return [f"{k}: {pa.get(k)!r} != {pb.get(k)!r}" for k in sorted(set(pa) | set(pb)) if pa.get(k) != pb.get(k)]


def linhas_na_tela(nome: str, bloco: Mapping[str, Any]) -> list[str]:
    """O resumo do bloco para a tela. Na prata, **"ordenação" ao lado de cada número**."""
    marca = f" ({USO_DA_PRATA})" if bloco["conjunto"] == PRATA else ""
    saida = [f"{nome}: {bloco['folhas']} folhas, {bloco['livros']} livros, {bloco['caracteres_de_prosa']} caracteres de prosa [{bloco['uso']}]"]
    for motor, modos in bloco["motores"].items():
        tip = modos[regua.TIP]
        saida.append(
            f"  {motor:14s} CER prosa {100 * tip['cer_prosa']:6.2f}%{marca} "
            f"IC95 [{100 * tip['ic95_prosa_dois_niveis'][0]:.2f}; {100 * tip['ic95_prosa_dois_niveis'][1]:.2f}] "
            f"WER {100 * tip['wer_prosa_sdi']:6.2f}%{marca} notação {100 * tip['cer_notacao']:6.2f}%{marca} "
            f"figurina {100 * tip['figurina_revocacao']:.1f}/{100 * tip['figurina_precisao']:.1f}{marca}"
        )
    perda = bloco.get("perda_de_leiaute")
    if perda:
        saida.append(f"  perda de leiaute {perda['delta_pp']:+.2f} p.p.{marca} [{perda['ic95_pp'][0]:+.2f}; {perda['ic95_pp'][1]:+.2f}]")
    return saida


__all__ = [
    "PARES_PADRAO",
    "achatar",
    "compilar_bloco",
    "diferencas",
    "filtrar",
    "linhas_na_tela",
    "rotular",
]
