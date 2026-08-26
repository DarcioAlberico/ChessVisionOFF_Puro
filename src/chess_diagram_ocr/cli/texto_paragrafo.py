"""`cvoff-texto-paragrafo` -- a referência de parágrafo, e a varredura dos dois cortes (S-257/S-258).

    cvoff-texto-paragrafo --semear            # monta a referência a partir de PDF/
    cvoff-texto-paragrafo                     # varre os candidatos sobre a referência do disco

**Este comando existe porque a medição da S-257 não existia como comando.** Ela saiu de um
`medir_paragrafo.py` no diretório de trabalho da sessão, e o campo `como_reproduzir` do relatório
diz isso com todas as letras. Um número que só um script perdido reproduz é um número que ninguém
confere -- e a S-258 pede exatamente que a varredura inteira fique registrada.

## O sinal da referência é o fim da linha, e ele não é circular

Em texto justificado **toda** linha alcança a margem direita, menos a última de cada parágrafo.
Então a linha seguinte a uma que não alcança **começa** parágrafo. O sinal não olha nem o recuo nem
o vão vertical, que são as duas réguas sob medição -- e é isso que o torna utilizável para julgá-las.

Onde a coluna não é justificada ele não diz nada, e ali a referência é `null`: declarado, e não
escondido. `linhas_com_referencia` é o denominador honesto.

**O que foi recusado como referência**, e vale repetir porque parecia a escolha óbvia: o `group_id`
da camada do PDF, isto é, o bloco que o produtor gravou. Medido no `AAGAARD`: dezoito linhas com
quatro parágrafos visíveis saem num bloco só. **O bloco do produtor é a COLUNA de prosa, não o
parágrafo.**

## As folhas sem camada entram, e é critério de aceite da S-258

As 24 folhas da referência de 2026-08-26 vêm todas de livro **com** camada de texto, porque é dela
que sai o bbox de cada linha. Só que o leitor roda sobre livro que não a tem -- e um corte
sintonizado só onde a camada existe pode estar sintonizado na camada. `--com-glifo` lê folhas de
livro sem camada com o classificador e as acrescenta à referência, com a **mesma** régua de fim de
linha sobre os bbox que o glifo devolve.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from ..config import DEFAULT_PDF_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging
from ..text import paragrafos as _paragrafos
from . import EXIT_BAD_INPUT, EXIT_OK, cli_errors

logger = logging.getLogger(__name__)

REFERENCIA = PROJECT_ROOT / "docs" / "metrics" / "texto_paragrafo_ampliada.jsonl"
"""A referência **ampliada** da S-258, e não a da S-257.

**Arquivo próprio, e não crescimento do de lá.** `texto_paragrafo_referencia.jsonl` é a evidência
de uma medição que **decidiu** -- a S-257 varreu o quantil da margem, recusou a troca e publicou
`texto_paragrafo_referencia.json` sobre aquelas 24 folhas. Sobrescrevê-lo deixaria aquele relatório
citando um conjunto que já não existe, que é o defeito que a S-100 persegue e que
`test_o_relatorio_bate_com_a_referencia_no_disco` pega.

O que a S-258 pede é que a referência **ganhe folhas de livro sem camada**, e ela ganhou: as 23
daqui incluem 16 lidas pelo glifo, que as 24 de lá não tinham. As duas ficam no disco, cada uma com
o relatório que a mediu."""
DESTINO = PROJECT_ROOT / "docs" / "metrics" / "texto_paragrafo.json"

TOLERANCIA_DA_MARGEM_DIREITA = 0.02
"""Fração da largura da coluna dentro da qual a linha "alcança" a margem direita.

2% da coluna. Menos que isso e a variação de espaçamento do justificado passa a contar como fim de
parágrafo; mais, e a penúltima linha curta deixa de contar."""

FRACAO_MINIMA_JUSTIFICADA = 0.6
"""Quanto da coluna tem de alcançar a direita para ela contar como justificada.

Abaixo disto a coluna não é justificada, o sinal não diz nada, e a referência sai `null` -- que é
o certo: inventar referência onde o sinal cala mediria o inventor."""

LINHAS_MINIMAS_NA_COLUNA = 6
"""Coluna curta demais não tem população para a fração acima significar coisa alguma."""

RECUOS = (0.15, 0.20, 0.30, 0.40, 0.45, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00)
"""Os candidatos de `RECUO_DE_PARAGRAFO`. O valor em uso (0,80) está entre eles de propósito: uma
varredura que não contivesse o vigente não permitiria comparar."""

SALTOS = (0.30, 0.45, 0.60, 0.75, 0.90)
"""Os candidatos de `SALTO_DE_PARAGRAFO`. A S-258 varreu e não achou vão; a varredura fica para
que a afirmação continue conferível."""


@dataclass(frozen=True)
class LinhaDaReferencia:
    """Uma linha da referência: o bbox que o leitor deu, e se ela **começa** parágrafo.

    `comeca=None` é "o sinal não diz" -- coluna não justificada, ou a primeira linha da coluna,
    que não tem anterior de quem herdar a resposta.
    """

    texto: str
    bbox: tuple[float, float, float, float]
    comeca: bool | None

    coluna: int = 0
    """A faixa de `colunas.detectar_colunas` em que a linha está.

    **Gravado, e não derivado.** A referência da S-257 não o trazia -- ela saiu de um script --, e
    sem ele a varredura tem de adivinhar a coluna pela volta do `y`. Adivinhar muda
    `metricas_por_coluna`, que muda a margem, que muda o corte: as contagens absolutas daquele
    relatório e deste diferem por isso, e a conclusão não."""

    def para_json(self) -> dict[str, Any]:
        return {
            "texto": self.texto,
            "bbox": [round(v, 2) for v in self.bbox],
            "comeca": self.comeca,
            "coluna": self.coluna,
        }


MAX_FRACAO_DE_NOTACAO = 0.4
"""Acima disto a coluna é lista de lances, e o sinal do fim de linha não diz nada nela.

**Este corte não estava na medição da S-257, e a falta dele quase inverteu a conclusão da S-258.**
A referência de lá foi semeada à mão sobre folhas de prosa; a semeadura automática deste comando
pegou o acervo inteiro, e com ela a precisão de *todos* os candidatos caiu de ~0,94 para ~0,47.

A causa não é o corte de recuo: é que numa coluna de notação **toda** linha é curta e irregular --
`28. Txe5 Dd7` não alcança margem nenhuma --, então o sinal marca começo de parágrafo em quase toda
linha, e nenhum candidato tem como acertar isso. A referência estava medindo a própria inadequação
dela.

Quem separa notação de prosa é `notacao.e_linha_de_notacao`, medida na S-249. 0,4 é folgado de
propósito: prosa de xadrez cita lance o tempo todo, e um corte apertado descartaria a página inteira
do `AAGAARD`."""


def _e_coluna_de_prosa(textos: Sequence[str]) -> bool:
    """A coluna é prosa, ou é lista de lances? Ver `MAX_FRACAO_DE_NOTACAO`."""
    from ..text.notacao import e_linha_de_notacao

    if not textos:
        return False
    de_notacao = sum(1 for texto in textos if e_linha_de_notacao(texto))
    return de_notacao / len(textos) <= MAX_FRACAO_DE_NOTACAO


def marcar_comecos(
    bboxes: Sequence[tuple[float, float, float, float]],
    textos: Sequence[str] = (),
) -> list[bool | None]:
    """`comeca` de cada linha de **uma coluna**, pelo sinal do fim da linha.

    A linha seguinte a uma que **não** alcança a margem direita começa parágrafo. A primeira da
    coluna fica `None`: ela pode ser continuação da coluna anterior, e afirmar que começa daria
    um acerto de graça por coluna -- é o que o campo `sem_a_primeira_linha_da_coluna` do relatório
    da S-257 isolava, e aqui ela simplesmente não entra.

    `textos`, quando vem, descarta a coluna de notação inteira -- ver `MAX_FRACAO_DE_NOTACAO`.
    """
    if len(bboxes) < LINHAS_MINIMAS_NA_COLUNA:
        return [None] * len(bboxes)
    if textos and not _e_coluna_de_prosa(textos):
        return [None] * len(bboxes)

    direitas = [b[2] for b in bboxes]
    esquerdas = [b[0] for b in bboxes]
    largura = max(direitas) - min(esquerdas)
    if largura <= 0:
        return [None] * len(bboxes)

    limite = max(direitas) - largura * TOLERANCIA_DA_MARGEM_DIREITA
    alcanca = [d >= limite for d in direitas]
    if sum(alcanca) / len(alcanca) < FRACAO_MINIMA_JUSTIFICADA:
        return [None] * len(bboxes)

    saida: list[bool | None] = [None]
    saida.extend(not alcanca[i - 1] for i in range(1, len(bboxes)))
    return saida


def _colunas_da_pagina(pagina: Any) -> list[list[tuple[str, tuple[float, float, float, float]]]]:
    """As linhas de cada coluna da `PaginaLida`, em ordem de leitura, com bbox."""
    saida: list[list[tuple[str, tuple[float, float, float, float]]]] = []
    for coluna in getattr(pagina, "colunas", ()):
        desta: list[tuple[str, tuple[float, float, float, float]]] = []
        for bloco in getattr(coluna, "blocos", ()):
            for linha in getattr(bloco, "linhas", ()):
                texto = str(getattr(linha, "texto", "")).strip()
                if texto:
                    desta.append((texto, tuple(float(v) for v in linha.bbox)))  # type: ignore[arg-type]
        if desta:
            saida.append(desta)
    return saida


def semear_folha(pagina: Any, livro: str, folha: int) -> dict[str, Any] | None:
    """Uma linha do `.jsonl` da referência, ou `None` quando nenhuma coluna é justificada."""
    linhas: list[LinhaDaReferencia] = []
    for indice, coluna in enumerate(_colunas_da_pagina(pagina)):
        marcas = marcar_comecos(
            [bbox for _texto, bbox in coluna], [texto for texto, _bbox in coluna]
        )
        linhas.extend(
            LinhaDaReferencia(texto=texto, bbox=bbox, comeca=marca, coluna=indice)
            for (texto, bbox), marca in zip(coluna, marcas, strict=True)
        )
    if not any(linha.comeca is not None for linha in linhas):
        return None
    return {"livro": livro, "folha": folha, "linhas": [linha.para_json() for linha in linhas]}


@dataclass(frozen=True)
class Placar:
    """O quanto um candidato acerta sobre o que a referência sabe julgar."""

    recuo: float
    salto: float
    acertos: int
    falsos: int
    perdidos: int
    blocos: int

    @property
    def precisao(self) -> float:
        return 0.0 if not (self.acertos + self.falsos) else self.acertos / (self.acertos + self.falsos)

    @property
    def recall(self) -> float:
        return 0.0 if not (self.acertos + self.perdidos) else self.acertos / (self.acertos + self.perdidos)

    @property
    def f1(self) -> float:
        soma = self.precisao + self.recall
        return 0.0 if soma <= 0 else 2 * self.precisao * self.recall / soma

    def para_json(self) -> dict[str, Any]:
        return {
            "recuo": self.recuo,
            "salto": self.salto,
            "acertos": self.acertos,
            "falsos": self.falsos,
            "perdidos": self.perdidos,
            "blocos": self.blocos,
            "precisao": round(self.precisao, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


def _linhas_de_paragrafo(registro: dict[str, Any]) -> tuple[list[Any], list[bool | None]]:
    """`(as `paragrafos.Linha` da folha, o `comeca` de cada uma)`.

    **A coluna vem do arquivo quando ele a traz, e da volta do `y` quando não.** A referência da
    S-257 foi gravada sem o campo -- ela saiu de um script --, e uma nova coluna sempre recomeça
    acima da última linha da anterior. Derivar é menos exato que gravar, e por isso `--semear`
    grava; a derivação existe para que o arquivo antigo continue mensurável.
    """
    linhas: list[Any] = []
    comecos: list[bool | None] = []
    coluna = 0
    topo_anterior = None
    for bruta in registro.get("linhas", []):
        x0, y0, _x1, y1 = (float(v) for v in bruta["bbox"])
        declarada = bruta.get("coluna")
        if declarada is None:
            if topo_anterior is not None and y0 < topo_anterior - 1.0:
                coluna += 1
        else:
            coluna = int(declarada)
        topo_anterior = y0
        linhas.append(
            _paragrafos.Linha(
                topo=int(round(y0)),
                esquerda=int(round(x0)),
                altura=max(1, int(round(y1 - y0))),
                texto=str(bruta.get("texto", "")),
                coluna=coluna,
            )
        )
        comecos.append(bruta.get("comeca"))
    return linhas, comecos


def varrer(
    registros: Sequence[dict[str, Any]],
    recuos: Sequence[float] = RECUOS,
    saltos: Sequence[float] = SALTOS,
) -> list[Placar]:
    """Um placar por candidato, sobre o que a referência sabe julgar.

    **Só as linhas com `comeca` diferente de `None` entram na conta.** Onde o sinal cala, tanto um
    corte quanto o outro estão sem juiz -- e contá-las como negativas premiaria o candidato que
    corta menos, que é o viés que este relatório existe para não ter.
    """
    placares: list[Placar] = []
    for salto in saltos:
        for recuo in recuos:
            acertos = falsos = perdidos = blocos = 0
            for registro in registros:
                linhas, comecos = _linhas_de_paragrafo(registro)
                if not linhas:
                    continue
                cortes = _paragrafos.cortar(linhas, recuo=recuo, salto=salto)
                blocos += len(cortes)
                previstos = set()
                indice = 0
                for paragrafo in cortes:
                    previstos.add(indice)
                    indice += len(paragrafo.linhas)
                for posicao, esperado in enumerate(comecos):
                    if esperado is None:
                        continue
                    previu = posicao in previstos
                    if previu and esperado:
                        acertos += 1
                    elif previu and not esperado:
                        falsos += 1
                    elif not previu and esperado:
                        perdidos += 1
            placares.append(Placar(recuo, salto, acertos, falsos, perdidos, blocos))
    return placares


def _tem_camada(pdf: Path, *, folhas: int = 6, minimo: int = 2000) -> bool:
    """O livro traz camada de texto utilizável nas primeiras folhas?"""
    import fitz

    doc = fitz.open(pdf)
    try:
        return sum(len(doc[i].get_text()) for i in range(min(folhas, doc.page_count))) > minimo
    finally:
        doc.close()


def semear(
    *,
    livros: int,
    folhas_por_livro: int,
    com_glifo: bool,
    dpi: int = 220,
) -> list[dict[str, Any]]:
    """Monta a referência a partir de `PDF/`. Ver o cabeçalho para o sinal.

    Os livros **com** camada são lidos por ela: é de graça, e o bbox de linha vem pronto. Os **sem**
    camada só existem para o classificador, e é `--com-glifo` que os traz -- critério de aceite da
    S-258, porque um corte sintonizado só onde a camada existe pode estar sintonizado na camada.
    """
    from ..text.leitor import ler_pagina

    reconhecedor = None
    if com_glifo:
        from ..text.recognizer import ModeloInvalido, build_glyph_recognizer

        try:
            reconhecedor = build_glyph_recognizer()
        except ModeloInvalido as exc:
            logger.warning("Sem classificador de glifo (%s): só entram livros com camada.", exc)
            com_glifo = False

    registros: list[dict[str, Any]] = []
    com_camada = sem_camada = 0
    for pdf in sorted(DEFAULT_PDF_DIR.glob("*.pdf")):
        if len(registros) >= livros * folhas_por_livro:
            break
        import fitz

        doc = fitz.open(pdf)
        total = doc.page_count
        doc.close()
        if total < 4:
            continue

        tem = _tem_camada(pdf)
        if not tem and not com_glifo:
            continue
        motor = "camada" if tem else "glifo"
        passo = max(1, total // (folhas_por_livro + 1))
        achadas = 0
        for indice in range(passo, total, passo):
            if achadas >= folhas_por_livro:
                break
            try:
                pagina = ler_pagina(pdf, indice, dpi=dpi, motor=motor, reconhecedor=reconhecedor)
            except (ValueError, RuntimeError, OSError) as exc:
                logger.debug("folha %d de %s não lida (%s)", indice + 1, pdf.name, exc)
                continue
            registro = semear_folha(pagina, pdf.name, indice)
            if registro is None:
                continue
            registro["motor"] = motor
            registros.append(registro)
            achadas += 1
        if achadas:
            logger.info("%s: %d folha(s) por %s", pdf.name[:44], achadas, motor)
            if tem:
                com_camada += 1
            else:
                sem_camada += 1

    logger.info("Referência: %d folha(s); %d livro(s) com camada, %d sem.", len(registros), com_camada, sem_camada)
    return registros


def ler_referencia(caminho: Path) -> list[dict[str, Any]]:
    """As folhas do `.jsonl`, ou lista vazia quando ele não existe."""
    if not caminho.exists():
        return []
    return [
        json.loads(linha)
        for linha in caminho.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]


def resumo_da_referencia(registros: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Quantas folhas, linhas, linhas julgáveis e começos a referência tem, e de que motor."""
    linhas = com_referencia = comecos = 0
    por_motor: dict[str, int] = {}
    livros: set[str] = set()
    for registro in registros:
        livros.add(str(registro.get("livro", "")))
        motor = str(registro.get("motor", "camada"))
        por_motor[motor] = por_motor.get(motor, 0) + 1
        for bruta in registro.get("linhas", []):
            linhas += 1
            if bruta.get("comeca") is not None:
                com_referencia += 1
                comecos += bool(bruta.get("comeca"))
    return {
        "folhas": len(registros),
        "livros": len(livros),
        "folhas_por_motor": por_motor,
        "linhas": linhas,
        "linhas_com_referencia": com_referencia,
        "comecos_de_paragrafo": comecos,
    }


def tabela(placares: Sequence[Placar], *, salto: float) -> list[str]:
    """A varredura do recuo, para a tela, com o valor em uso marcado."""
    linhas = [f"salto = {salto:.2f}", "  recuo   acertos  falsos  perdidos  precisão  recall      F1   blocos"]
    melhor = max((p for p in placares if p.salto == salto), key=lambda p: p.f1, default=None)
    for placar in placares:
        if placar.salto != salto:
            continue
        marca = ""
        if abs(placar.recuo - _paragrafos.RECUO_DE_PARAGRAFO) < 1e-9:
            marca = "  <- em uso"
        if melhor is not None and placar is melhor:
            marca += "  <- melhor F1"
        linhas.append(
            f"  {placar.recuo:5.2f}  {placar.acertos:8d} {placar.falsos:7d} {placar.perdidos:9d}"
            f"  {placar.precisao:8.4f} {placar.recall:7.4f} {placar.f1:7.4f} {placar.blocos:8d}{marca}"
        )
    return linhas


@cli_errors
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cvoff-texto-paragrafo",
        description="Monta a referência de parágrafo e varre os dois cortes (S-257, S-258).",
    )
    parser.add_argument("--semear", action="store_true", help="Monta a referência a partir de PDF/.")
    parser.add_argument("--livros", type=int, default=16, help="Livros na semeadura. Padrão: 16.")
    parser.add_argument("--folhas", type=int, default=2, help="Folhas por livro na semeadura. Padrão: 2.")
    parser.add_argument(
        "--com-glifo",
        action="store_true",
        help=(
            "Na semeadura, lê também livros SEM camada de texto, com o classificador. "
            "É critério de aceite da S-258: o leitor roda sobre livro que não tem camada."
        ),
    )
    parser.add_argument("--referencia", type=Path, default=REFERENCIA, help="O .jsonl da referência.")
    parser.add_argument("--json", type=Path, default=DESTINO, help="Onde a varredura é gravada.")
    parser.add_argument("--verbose", action="store_true", help="Log em DEBUG.")
    args = parser.parse_args(argv)

    configure_logging(verbose=args.verbose)

    if args.semear:
        if not DEFAULT_PDF_DIR.is_dir():
            logger.error("Pasta do acervo não encontrada: %s", DEFAULT_PDF_DIR)
            return EXIT_BAD_INPUT
        registros = semear(livros=args.livros, folhas_por_livro=args.folhas, com_glifo=args.com_glifo)
        if not registros:
            logger.error("Nenhuma folha justificada encontrada: a referência ficaria vazia.")
            return EXIT_BAD_INPUT
        args.referencia.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            args.referencia,
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registros),
        )
        print(f"Referência gravada em {args.referencia}")

    registros = ler_referencia(args.referencia)
    if not registros:
        logger.error("Referência vazia: rode com --semear antes.")
        return EXIT_BAD_INPUT

    resumo = resumo_da_referencia(registros)
    placares = varrer(registros)
    # **Separado por motor, e é o achado da S-258.** A referência julga bem a folha lida pela
    # camada (precisão ~0,94) e não julga a lida pelo glifo (~0,43): ali `cortar` faz mais que o
    # dobro de blocos que a referência vê começos. Uma média das duas esconderia as duas.
    por_motor = {
        motor: [p.para_json() for p in varrer([r for r in registros if r.get("motor") == motor])]
        for motor in sorted({str(r.get("motor", "camada")) for r in registros})
    }
    print("")
    print(
        f"{resumo['folhas']} folha(s) de {resumo['livros']} livro(s); {resumo['linhas']} linhas, "
        f"{resumo['linhas_com_referencia']} com referência, {resumo['comecos_de_paragrafo']} começos."
    )
    print(f"por motor: {resumo['folhas_por_motor']}")
    print("")
    for linha in tabela(placares, salto=_paragrafos.SALTO_DE_PARAGRAFO):
        print(linha)

    melhor = max(placares, key=lambda p: p.f1)
    em_uso = next(
        (
            p
            for p in placares
            if abs(p.recuo - _paragrafos.RECUO_DE_PARAGRAFO) < 1e-9
            and abs(p.salto - _paragrafos.SALTO_DE_PARAGRAFO) < 1e-9
        ),
        None,
    )
    for motor, linhas in por_motor.items():
        no_salto = [x for x in linhas if abs(x["salto"] - _paragrafos.SALTO_DE_PARAGRAFO) < 1e-9]
        if not no_salto:
            continue
        melhor_do_motor = max(no_salto, key=lambda x: x["f1"])
        em_uso_do_motor = next(
            (x for x in no_salto if abs(x["recuo"] - _paragrafos.RECUO_DE_PARAGRAFO) < 1e-9), None
        )
        print("")
        print(
            f"  {motor}: precisão ~{melhor_do_motor['precisao']:.2f}; melhor recuo "
            f"{melhor_do_motor['recuo']:.2f} (F1 {melhor_do_motor['f1']:.4f})"
            + (f", em uso {em_uso_do_motor['f1']:.4f}" if em_uso_do_motor else "")
        )

    print("")
    print(f"melhor F1: recuo={melhor.recuo:.2f} salto={melhor.salto:.2f} -> {melhor.f1:.4f}")
    if em_uso is not None:
        print(f"em uso:    recuo={em_uso.recuo:.2f} salto={em_uso.salto:.2f} -> {em_uso.f1:.4f}")

    dados: dict[str, Any] = {
        "item": "S-258",
        "medido_em": f"{date.today():%Y-%m-%d}",
        "sinal": (
            "o fim da linha: em texto justificado toda linha alcança a margem direita, menos a "
            "última de cada parágrafo. É independente do recuo e do vão vertical, que são as duas "
            "réguas sob medição."
        ),
        "criterio": {
            "tolerancia_da_margem_direita": TOLERANCIA_DA_MARGEM_DIREITA,
            "fracao_minima_de_linhas_justificadas": FRACAO_MINIMA_JUSTIFICADA,
            "linhas_minimas_na_coluna": LINHAS_MINIMAS_NA_COLUNA,
        },
        "referencia": str(args.referencia.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        **resumo,
        "em_uso": {"recuo": _paragrafos.RECUO_DE_PARAGRAFO, "salto": _paragrafos.SALTO_DE_PARAGRAFO},
        "melhor": melhor.para_json(),
        "varredura": [p.para_json() for p in placares],
        "varredura_por_motor": por_motor,
        "como_reproduzir": "cvoff-texto-paragrafo --semear --com-glifo, depois cvoff-texto-paragrafo",
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.json, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")
    print(f"Varredura gravada em {args.json}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
