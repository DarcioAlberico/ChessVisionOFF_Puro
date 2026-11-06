"""`cvoff-texto-prosa` -- a régua da prosa sobre um manifesto, e o relatório publicado (S-706).

    cvoff-texto-prosa --conjunto ouro --split dev --motor glifo,camada_prosa,fusao --dados fora/dev.jsonl
    cvoff-texto-prosa --conjunto ouro --conferir-admissao
    cvoff-texto-prosa --compilar docs/metrics/texto_prosa_AAAAMMDD.json --bloco ouro_dev=fora/dev.jsonl \\
        --bloco "prata_admitida=fora/prata.jsonl?oraculo_max=0.10"
    cvoff-texto-prosa --comparar a.json b.json

**Duas etapas, porque só uma pode ver texto de livro.** Medir grava um JSONL por folha em `--dados`, **fora do
repositório** (o comando recusa um caminho dentro dele): tem texto de livro comercial. `--compilar` lê esses JSONL e escreve o
relatório, que só tem números e identidades.

**Medir em pedaços.** `--limite-segundos` para depois da folha em curso, e rodar de novo com o mesmo `--dados` continua de onde
parou: a folha já gravada não é lida outra vez. Cada processo descarta uma leitura de aquecimento, porque a primeira
`ler_pagina` de um processo pode sair diferente (`primeira-leitura-do-processo-difere`).

**O split `teste` só abre com `--abrir-teste`**, grava `primeira_leitura_do_teste` no manifesto **antes** de ler (por livro, para
o livro acrescentado depois do congelamento), e não imprime número por folha. A identidade de quem lê
vai no registro: `--exigir-src` aborta se o pacote importado não for o da árvore que se quer medir.

**`--conferir-admissao` não conta como leitura do teste.** Ela só refaz a admissão sem motor que o sorteio da S-702 já fez, e
imprime o critério da folha recusada; texto nenhum é lido por leitor nenhum.

**Medir um motor novo:** ver o cabeçalho de `text/bancada_prosa.py`. O motor que já entra por `ler_pagina(motor=...)` só precisa de
`--motor nome`; o de outro processo, de `--importar nome=hip.jsonl`, com `{identidade, folha, texto}` por linha.

Uso: `.venv/Scripts/python.exe -m chess_diagram_ocr.cli.texto_prosa`, num worktree com `PYTHONPATH=<worktree>/src` e
`--raiz` no checkout que tem `PDF/` e `PDF Digitais/` (o `cvoff-*` instalado importa o pacote do checkout principal).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)

MOTORES_PADRAO = "glifo,camada_prosa,fusao,tess,tess_oraculo,tess_pagina"


@dataclass(frozen=True)
class FolhaDoConjunto:
    conjunto: str
    split: str
    identidade: str
    folha: int
    """Base 1, como nos relatórios."""
    lingua: str
    estrato: str


def folhas_do_conjunto(conjunto: str, split: str, *, manifesto: str | None = None) -> list[FolhaDoConjunto]:
    """As folhas de um manifesto. O ouro é do split pedido; a prata não tem split."""
    if conjunto == "ouro":
        from ..text import ouro

        m = ouro.carregar(manifesto)
        erros = ouro.problemas(m)
        if erros:
            raise SystemExit(f"o manifesto do ouro não vale: {erros}")
        return [FolhaDoConjunto("ouro", split, f.identidade, f.folha, f.lingua, f.estrato) for f in m.do_split(split)]
    from ..text import prata

    p = prata.carregar(manifesto)
    erros = prata.problemas(p)
    if erros:
        raise SystemExit(f"o manifesto da prata não vale: {erros}")
    return [FolhaDoConjunto("prata", "", f.identidade, f.folha, f.lingua, f.estrato) for f in p.folhas]


def abrir_o_teste(folhas: Iterable[FolhaDoConjunto], *, manifesto: str | None, hoje: str) -> str | None:
    """Grava a primeira leitura **antes** de qualquer folha ser lida. Devolve a data que ficou no manifesto."""
    from ..text import ouro

    caminho = manifesto or ouro.caminho_padrao()
    m = ouro.carregar(caminho)
    novo = ouro.registrar_leitura_do_teste(m, hoje, sorted({f.identidade for f in folhas}))
    if novo != m:
        ouro.gravar(novo, caminho)
    return novo.primeira_leitura_do_teste


def _pasta_do_repositorio() -> Path:
    import chess_diagram_ocr

    return Path(chess_diagram_ocr.__file__).resolve().parents[2]


def recusar_dentro_do_repositorio(caminho: str | Path) -> None:
    """Os JSONL de medição têm texto de livro comercial, e o repositório é público."""
    alvo = Path(caminho).resolve()
    for raiz in (_pasta_do_repositorio(), Path.cwd().resolve()):
        if (raiz / ".git").exists() and alvo.is_relative_to(raiz):
            raise SystemExit(f"--dados dentro do repositório ({alvo}): o arquivo tem texto de livro. Grave-o fora.")


def _git(raiz: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, text=True, check=False).stdout.strip()


def _sha(caminho: Path | None) -> str:
    if caminho is None or not caminho.is_file():
        return ""
    return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]


def codigo_medido(*, exigir_src: str = "") -> dict[str, Any]:
    """Com que árvore isto foi medido, sem caminho absoluto. `exigir_src` aborta se o pacote morar em outra."""
    raiz = _pasta_do_repositorio()
    if exigir_src and not raiz.is_relative_to(Path(exigir_src).resolve()):
        raise SystemExit(f"o pacote importado mora em {raiz}, e não sob {exigir_src}: use PYTHONPATH=<arvore>/src")
    return {
        "pacote": f"{raiz.name}/src",
        "commit": _git(raiz, "rev-parse", "HEAD"),
        "src_sujo": bool(_git(raiz, "status", "--porcelain", "--", "src")),
    }


def _procedencia_dos_motores(modelo: str, linguas: Iterable[str]) -> dict[str, Any]:
    from ..text import tesseract
    from ..text.modelo import CAMINHO_PADRAO_META

    motor = tesseract.achar_motor()
    pesos = Path(modelo) if modelo else CAMINHO_PADRAO_META.with_name("char_classifier.pt")
    return {
        "modelo_sha256": _sha(pesos),
        "tesseract": motor.versao,
        "tessdata_sha256": {
            lingua: _sha(motor.tessdata / f"{lingua}.traineddata") if motor.tessdata else "" for lingua in sorted(set(linguas))
        },
    }


def _ja_medidas(dados: Path) -> set[tuple[str, int]]:
    if not dados.is_file():
        return set()
    with dados.open(encoding="utf-8") as arquivo:
        return {(r["identidade"], r["folha"]) for r in map(json.loads, arquivo)}


def _achar_livros(folhas: Sequence[FolhaDoConjunto], pastas: Sequence[str]) -> dict[str, Path]:
    from ..text import ouro

    identidades = {f.identidade for f in folhas}
    achados = ouro.localizar(identidades, pastas)
    faltam = sorted(identidades - set(achados))
    if faltam:
        raise SystemExit(f"livros que não estão em {list(pastas)}: {faltam}")
    return achados


def medir(args: argparse.Namespace) -> int:
    from ..pdf_io import render_pdf_page
    from ..text import bancada_prosa, degradacao
    from ..text.leitor import ler_pagina
    from ..text.recognizer import build_glyph_recognizer

    if not args.dados:
        raise SystemExit("medir precisa de --dados, fora do repositório")
    recusar_dentro_do_repositorio(args.dados)
    dados = Path(args.dados)
    split = args.split if args.conjunto == "ouro" else ""
    teste = args.conjunto == "ouro" and split == "teste"
    if teste and not args.abrir_teste:
        raise SystemExit("o split teste só abre no portão da fase: passe --abrir-teste de propósito (S-702)")
    motores = [m.strip() for m in args.motor.split(",") if m.strip()]
    desconhecidos = sorted(set(motores) - set(bancada_prosa.motores_conhecidos()))
    if desconhecidos:
        raise SystemExit(f"motor desconhecido: {desconhecidos}; os que existem: {bancada_prosa.motores_conhecidos()}")
    if args.degradar:
        degradacao.familia_do_perfil(args.degradar)
    folhas = folhas_do_conjunto(args.conjunto, split, manifesto=args.manifesto)
    if args.livro:
        folhas = [f for f in folhas if f.identidade in set(args.livro)]
    if args.folhas_maximas:
        folhas = folhas[: args.folhas_maximas]
    if not folhas:
        raise SystemExit("nenhuma folha para medir")
    achados = _achar_livros(folhas, args.pasta or _pastas_padrao(args.raiz))
    if teste:
        lido = abrir_o_teste(folhas, manifesto=args.manifesto, hoje=args.medido_em or date.today().isoformat())
        print(f"# teste aberto; primeira_leitura_do_teste = {lido}", flush=True)
    feitas = _ja_medidas(dados)
    faltam = [f for f in folhas if (f.identidade, f.folha) not in feitas]
    print(f"# {len(folhas)} folhas no conjunto, {len(feitas)} já em {dados.name}, {len(faltam)} a medir", flush=True)
    if not faltam:
        return 0
    codigo = codigo_medido(exigir_src=args.exigir_src)
    codigo.update(_procedencia_dos_motores(args.modelo, [f.lingua for f in folhas]))
    print(f"# pacote {codigo['pacote']} commit {codigo['commit'][:10]}{' (src sujo)' if codigo['src_sujo'] else ''}", flush=True)
    reconhecedor = build_glyph_recognizer(args.modelo) if args.modelo else build_glyph_recognizer()
    inicio = time.perf_counter()
    aquecido = False
    with dados.open("a", encoding="utf-8", newline="\n") as saida:
        for n, f in enumerate(faltam, start=1):
            if args.limite_segundos and time.perf_counter() - inicio > args.limite_segundos:
                print(f"# parou pelo limite: faltam {len(faltam) - n + 1} folhas. Rode de novo com o mesmo --dados.", flush=True)
                return 3
            pdf = str(achados[f.identidade])
            indice = f.folha - 1
            imagem = render_pdf_page(pdf, indice, args.dpi)
            if args.degradar:
                imagem = degradacao.aplicar(imagem, args.degradar, degradacao.semente_da_folha(f.identidade, f.folha))
            if not aquecido:
                ler_pagina(pdf, indice, motor="glifo", reconhecedor=reconhecedor, imagem_rgb=imagem, dpi=args.dpi)
                aquecido = True
            folha = bancada_prosa.preparar_folha(pdf, indice, lingua=f.lingua, imagem=imagem, reconhecedor=reconhecedor, dpi=args.dpi, reserva=args.reserva)
            registro = bancada_prosa.medir_folha(folha, motores)
            registro.update(
                conjunto=f.conjunto, split=f.split, perfil=args.degradar, identidade=f.identidade, folha=f.folha,
                lingua=f.lingua, estrato=f.estrato, codigo=codigo,
            )
            saida.write(json.dumps(registro, ensure_ascii=False) + "\n")
            saida.flush()
            print(_linha_da_folha(registro, n, len(faltam), mostrar_numero=not teste), flush=True)
    return 0


def _linha_da_folha(registro: dict[str, Any], n: int, total: int, *, mostrar_numero: bool) -> str:
    if not mostrar_numero:
        return f"  {n}/{total}"
    numeros = []
    for motor in registro["hip"]:
        p = registro["placar"][f"{motor}|tip"]
        numeros.append(f"{motor}={p['erros']['prosa'] / max(1, p['total']['prosa']):.4f}")
    return f"  {n}/{total} {registro['identidade'][:8]} f{registro['folha']} " + " ".join(numeros)


def _pastas_padrao(raiz: str) -> list[str]:
    base = Path(raiz) if raiz else _pasta_do_repositorio()
    return [str(base / "PDF"), str(base / "PDF Digitais")]


def conferir_admissao(args: argparse.Namespace) -> int:
    """Lista a folha recusada e o critério. Sem motor nenhum: é o que a S-702 adiou para este comando."""
    import fitz

    from ..text import admissao
    from ..text.leitor import ler_pagina

    splits = [args.split] if args.split_dado and args.conjunto == "ouro" else (["dev", "teste"] if args.conjunto == "ouro" else [""])
    recusadas_no_total = 0
    for split in splits:
        folhas = folhas_do_conjunto(args.conjunto, split, manifesto=args.manifesto)
        achados = _achar_livros(folhas, args.pasta or _pastas_padrao(args.raiz))
        criterios: Counter[str] = Counter()
        for identidade in sorted({f.identidade for f in folhas}):
            caminho = str(achados[identidade])
            with fitz.open(caminho) as doc:
                perfil, produtor = admissao.perfil_do_livro(doc), admissao.produtor_de(doc)
                for f in (x for x in folhas if x.identidade == identidade):
                    retangulos = [d.bbox for d in ler_pagina(caminho, f.folha - 1, motor="camada").diagramas]
                    resposta = admissao.admitir_folha(doc[f.folha - 1], retangulos, produtor=produtor, perfil=perfil)
                    if not resposta.admitida:
                        criterios[resposta.criterio or "?"] += 1
                        print(f"recusada: {identidade} folha {f.folha} critério {resposta.criterio}", flush=True)
        rotulo = split or args.conjunto
        print(f"# {rotulo}: {len(folhas)} folhas, {sum(criterios.values())} recusadas {dict(criterios)}", flush=True)
        recusadas_no_total += sum(criterios.values())
    # Na prata a recusa é o normal: os livros são de OCR de terceiro. No ouro, é defeito.
    return 1 if recusadas_no_total and args.conjunto == "ouro" else 0


def _ler_registros(caminho: str | Path) -> list[dict[str, Any]]:
    with open(caminho, encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo]


def _filtro_do_bloco(consulta: str) -> dict[str, Any]:
    """`oraculo_max=0.10&sem_folha_perdida=1&so_livro=a,b`, o que vai escrito no relatório."""
    filtro: dict[str, Any] = {}
    for chave, valor in parse_qsl(consulta):
        if chave == "oraculo_max":
            filtro[chave] = float(valor)
        elif chave in ("so_livro", "sem_livro"):
            filtro[chave] = valor.split(",")
        elif chave == "sem_folha_perdida":
            filtro[chave] = valor not in ("0", "")
        else:
            filtro[chave] = valor
    return filtro


def compilar(args: argparse.Namespace) -> int:
    from ..text import regua_prosa, relatorio_prosa

    pares = [tuple(p.split("-", 1)) for p in (args.pares or "").split(",") if p]
    blocos: dict[str, Any] = {}
    procedencia: dict[str, Any] = {"modelo_sha256": set(), "tesseract": set(), "tessdata_sha256": {}, "commit": set(), "src_sujo": False}
    for pedido in args.bloco:
        nome, _, resto = pedido.partition("=")
        caminho, _, consulta = resto.partition("?")
        registros = _ler_registros(caminho)
        filtro = _filtro_do_bloco(consulta)
        blocos[nome] = relatorio_prosa.compilar_bloco(registros, filtro=filtro, pares=pares)  # type: ignore[arg-type]
        for r in registros:
            c = r["codigo"]
            procedencia["modelo_sha256"].add(c.get("modelo_sha256", ""))
            procedencia["tesseract"].add(c.get("tesseract", ""))
            procedencia["commit"].add(c["commit"])
            procedencia["src_sujo"] = procedencia["src_sujo"] or bool(c["src_sujo"])
            procedencia["tessdata_sha256"].update(c.get("tessdata_sha256", {}))
    relatorio = {
        "item": "S-706: a linha de base da prosa, pelo cvoff-texto-prosa",
        "medido_em": args.medido_em or date.today().isoformat(),
        "pergunta": "Quanto cada motor erra na prosa (o texto que não é lance nem avaliação), por conjunto?",
        "regua": {"modulo": "src/chess_diagram_ocr/text/regua_prosa.py", "classificador": regua_prosa.VERSAO_CLASSIFICADOR,
                  "normalizacoes": list(regua_prosa.MODOS), "classes": list(regua_prosa.CLASSES),
                  "estatistica": f"IC95 em dois níveis (livro, folha), {regua_prosa.REAMOSTRAS} reamostras, semente {regua_prosa.SEMENTE}"},
        "referencia": "a camada montada por ler_pagina(motor='camada'), sem as linhas que cruzam diagrama e sem as de nenhuma "
                      "palavra nem lance que cruzam o retângulo crescido de uma casa",
        "motores": {"tess": "Tesseract nas caixas do glifo", "tess_oraculo": "Tesseract nas linhas visuais da camada",
                    "tess_pagina": "Tesseract na folha inteira, psm 3", "auto": "o padrão de hoje, que é o glifo"},
        "codigo": {k: sorted(v) if isinstance(v, set) else v for k, v in procedencia.items()},
        "ressalvas": list(args.ressalva or []),
        "conjuntos": blocos,
    }
    Path(args.compilar).write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    for nome, bloco in blocos.items():
        for linha in relatorio_prosa.linhas_na_tela(nome, bloco):
            print(linha)
    return 0


def comparar(args: argparse.Namespace) -> int:
    from ..text import relatorio_prosa

    a, b = (json.loads(Path(c).read_text(encoding="utf-8")) for c in args.comparar)
    erros = relatorio_prosa.diferencas(a, b)
    for erro in erros[:40]:
        print(erro)
    print(f"{len(erros)} diferenças fora as chaves segundos_*")
    return 1 if erros else 0


def importar(args: argparse.Namespace) -> int:
    """Acrescenta a hipótese de um motor de fora ao JSONL, com a mesma referência e o mesmo placar."""
    from ..text import bancada_prosa

    if not args.dados or not args.saida:
        raise SystemExit("--importar precisa de --dados e --saida")
    recusar_dentro_do_repositorio(args.saida)
    nome, _, caminho = args.importar.partition("=")
    externas = {(r["identidade"], r["folha"]): r for r in _ler_registros(caminho)}
    registros = _ler_registros(args.dados)
    faltam = [(r["identidade"], r["folha"]) for r in registros if (r["identidade"], r["folha"]) not in externas]
    if faltam:
        raise SystemExit(f"o motor {nome} não leu {len(faltam)} folhas: {faltam[:5]}...")
    with open(args.saida, "w", encoding="utf-8", newline="\n") as saida:
        for r in registros:
            externa = externas[(r["identidade"], r["folha"])]
            r["hip"][nome] = externa["texto"]
            r["placar"].update(bancada_prosa.pontuar_hipoteses(r["ref"], {nome: externa["texto"]}, r["lingua"]))
            if "segundos" in externa:
                r["tempo"][nome] = externa["segundos"]
            saida.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(registros)} folhas com {nome} em {args.saida}")
    return 0


def repontuar(args: argparse.Namespace) -> int:
    """Refaz o placar pelos textos gravados: mudar a régua não pede rodar motor nenhum."""
    from ..text import bancada_prosa

    if not args.saida:
        raise SystemExit("--repontuar precisa de --saida")
    recusar_dentro_do_repositorio(args.saida)
    registros = _ler_registros(args.repontuar)
    with open(args.saida, "w", encoding="utf-8", newline="\n") as saida:
        for r in registros:
            r["placar"] = bancada_prosa.pontuar_hipoteses(r["ref"], r["hip"], r["lingua"])
            saida.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(registros)} folhas repontuadas em {args.saida}")
    return 0


def construir_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cvoff-texto-prosa", description="A régua da prosa sobre um manifesto (S-706).")
    ap.add_argument("--conjunto", choices=("ouro", "prata"), default="ouro")
    ap.add_argument("--split", choices=("dev", "teste"), default=None, help="do ouro; padrão: dev")
    ap.add_argument("--abrir-teste", action="store_true", help="autoriza ler o split teste, e grava a primeira leitura antes")
    ap.add_argument("--motor", default=MOTORES_PADRAO, help=f"separados por vírgula; padrão: {MOTORES_PADRAO}")
    ap.add_argument("--degradar", default="", help="perfil de text/degradacao.py, com semente por folha")
    ap.add_argument("--dados", default="", help="o JSONL por folha, fora do repositório: tem texto de livro")
    ap.add_argument("--limite-segundos", type=float, default=0.0, help="para depois da folha em curso; rode de novo para continuar")
    ap.add_argument("--livro", action="append", help="só esta identidade; pode repetir")
    ap.add_argument("--folhas-maximas", type=int, default=0)
    ap.add_argument("--raiz", default=os.environ.get("CVOFF_RAIZ", ""), help="o checkout com PDF/ e PDF Digitais/")
    ap.add_argument("--pasta", action="append", help="onde procurar os PDF, no lugar das duas da raiz")
    ap.add_argument("--manifesto", default=None, help="outro manifesto no lugar do versionado")
    ap.add_argument("--modelo", default="", help="o char_classifier.pt; padrão: o de models/")
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--reserva", action="store_true", help="liga a reserva da S-715, como a janela")
    ap.add_argument("--exigir-src", default="", help="aborta se o pacote importado não morar sob esta pasta")
    ap.add_argument("--medido-em", default="", help="a data do relatório e da primeira leitura; padrão: hoje")
    ap.add_argument("--conferir-admissao", action="store_true", help="lista a folha recusada e o critério, sem motor")
    ap.add_argument("--compilar", default="", help="escreve o relatório neste JSON, a partir dos --bloco")
    ap.add_argument("--bloco", action="append", default=[], help="nome=arquivo.jsonl[?filtro=valor&...]; o filtro vai escrito no relatório")
    ap.add_argument("--pares", default="", help="pares a mais, a-b,c-d, além dos padrão")
    ap.add_argument("--ressalva", action="append", help="frase para a chave ressalvas do relatório")
    ap.add_argument("--comparar", nargs=2, metavar=("A", "B"), help="compara dois relatórios fora as chaves segundos_*")
    ap.add_argument("--importar", default="", help="nome=hip.jsonl: a hipótese de um motor de fora, com --dados e --saida")
    ap.add_argument("--repontuar", default="", help="arquivo.jsonl: refaz o placar pelos textos, com --saida")
    ap.add_argument("--saida", default="", help="o JSONL de --importar e --repontuar")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    args.split_dado = args.split is not None
    args.split = args.split or "dev"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    logging.basicConfig(level=logging.WARNING)
    if args.comparar:
        return comparar(args)
    if args.compilar:
        return compilar(args)
    if args.importar:
        return importar(args)
    if args.repontuar:
        return repontuar(args)
    if args.conferir_admissao:
        return conferir_admissao(args)
    return medir(args)


if __name__ == "__main__":
    raise SystemExit(main())
