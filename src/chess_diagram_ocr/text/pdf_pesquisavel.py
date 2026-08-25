"""O PDF pesquisável do próprio livro, com o texto que uma pessoa já corrigiu (S-253).

**O acervo tem livros sem camada de texto** -- 11 dos 41 na amostra de 2026-08-24 -- e livros cuja
camada erra a notação inteira: a S-211 mediu **zero figurinas** na camada contra 360 no
classificador, com três codificações diferentes em quatro livros. Buscar `Nf3` num livro de xadrez é
a coisa mais óbvia a querer fazer, e não dá.

A **S-210** planeja a camada invisível a partir do que o motor leu. **Este item é a outra ponta:** a
camada feita do texto que **uma pessoa já corrigiu** -- que é a melhor versão daquela página que vai
existir.

## Três regras, e as três são sobre honestidade

**A página não muda um pixel.** O texto entra em `render_mode=3` (invisível), sobre a página
original, e o teste compara os pixmaps de antes e depois byte a byte.

**A posição vem do bloco e o texto vem da corrida.** Cada corrida sabe de que bloco veio
(`Corrida.bloco`, S-235), e o bloco tem bbox. **Corrida escrita do zero (`bloco == SEM_BLOCO`) não
entra na camada**: não há onde a pôr, e inventar posição é pior que não ter o texto. O relatório a
conta.

**A procedência vai no metadado do PDF.** Um PDF cuja camada foi corrigida à mão é um documento
diferente de um cuja camada saiu do OCR, e quem o receber precisa poder saber. É a S-218 outra vez:
o relatório diz com que código e com que modelo foi medido.

## A fonte é o bloqueio, e ele é declarado

A camada com figurina precisa de uma fonte que tenha os glifos de xadrez, e **nenhuma fonte é
copiada para cá antes de a licença ser conferida** -- a mesma trava que a S-210 registra e que
`docs/ROADMAP_TEXTO.md` mantém. Sem fonte redistribuível, este item entrega a camada do alfabeto
latino e **conta** quantas figurinas ficaram de fora. Não falha: entrega o que dá e diz o que não
deu, que é a regra de degradação de `ui/theme.py` aplicada a texto.

A base 14 do PDF cobre Latin-1, e é o que a `helv` embutida oferece sem arquivo nenhum. Todo
caractere fora dela sai da camada e entra na contagem.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .pagina import BlocoDeDiagrama
from .rico import DocumentoRico

__all__ = [
    "FONTE_DA_CAMADA",
    "Relatorio",
    "Trecho",
    "camada",
    "escrever",
    "latino",
]

FONTE_DA_CAMADA = "helv"
"""A Helvetica da base 14 do PDF: sem arquivo, sem licença a conferir, e cobre Latin-1.

Trocar por uma fonte com figurinas é o que fecha o buraco -- e é decisão de licença, não de
código: ver "A fonte é o bloqueio"."""

FOLGA_DA_CAIXA = 2.0
"""Pontos acrescentados à bbox do bloco antes de escrever.

O texto invisível precisa **caber** para o `insert_textbox` o aceitar, e a bbox do bloco é o
retângulo justo das linhas lidas. Dois pontos é o mínimo que absorve o arredondamento das
métricas sem mover a busca de lugar."""


@dataclass(frozen=True)
class Trecho:
    """Um pedaço da camada: o que escrever, e onde."""

    texto: str
    bbox: tuple[float, float, float, float]
    bloco: int


@dataclass(frozen=True)
class Relatorio:
    """O que a camada levou, o que ficou de fora e por quê."""

    trechos: int = 0
    caracteres: int = 0
    fora_da_fonte: int = 0
    """Caracteres que a fonte da camada não escreve -- as figurinas, hoje."""

    sem_bloco: int = 0
    """Corridas escritas do zero, que não têm onde ser postas."""

    diagramas: int = 0
    escrito: Path | None = None
    seco: bool = False
    avisos: tuple[str, ...] = field(default_factory=tuple)

    def resumo(self) -> str:
        partes = [f"{self.trechos} trecho(s), {self.caracteres} caractere(s)"]
        if self.fora_da_fonte:
            partes.append(f"{self.fora_da_fonte} fora da fonte (figurinas)")
        if self.sem_bloco:
            partes.append(f"{self.sem_bloco} corrida(s) sem bloco de origem")
        return " · ".join(partes)


def latino(texto: str) -> tuple[str, int]:
    """O texto que a fonte da camada escreve, e **quantos caracteres ficaram de fora**.

    Latin-1 é o que a base 14 cobre. `♘` não cabe, e o que se faz com ele é contar -- escrevê-lo
    como `?` poria um caractere errado na busca de quem procurasse por ele.
    """
    dentro = []
    fora = 0
    for caractere in texto:
        if ord(caractere) < 256:
            dentro.append(caractere)
        else:
            fora += 1
    return "".join(dentro), fora


def camada(doc: DocumentoRico) -> tuple[tuple[Trecho, ...], Relatorio]:
    """Os trechos da camada e a conta do que ficou de fora. **Pura**: não abre PDF nenhum.

    Um trecho por bloco, e não por corrida: as corridas de um mesmo bloco são pedaços do mesmo
    parágrafo, e a bbox que se tem é a do bloco. Escrever cinco vezes no mesmo retângulo poria o
    texto cinco vezes na busca.
    """
    if doc.origem is None:
        return (), Relatorio(avisos=("o documento não guarda a página de origem",))
    blocos = doc.origem.blocos
    por_bloco: dict[int, list[str]] = {}
    sem_bloco = 0
    for corrida in doc.corridas:
        if not corrida.texto.strip():
            continue
        if not corrida.da_pagina:
            sem_bloco += 1
            continue
        por_bloco.setdefault(corrida.bloco, []).append(corrida.texto)

    trechos: list[Trecho] = []
    caracteres = 0
    fora = 0
    diagramas = 0
    for indice, pedacos in sorted(por_bloco.items()):
        if not 0 <= indice < len(blocos):
            continue
        bloco = blocos[indice]
        if isinstance(bloco, BlocoDeDiagrama):
            # A marca `[Diagrama N]` **não** entra na camada: ela nunca esteve impressa na página,
            # e a camada existe para espelhar o texto do livro. Ver o cabeçalho de `exportacao.py`.
            diagramas += 1
            continue
        texto, perdidos = latino("".join(pedacos))
        if not texto.strip():
            fora += perdidos
            continue
        trechos.append(Trecho(texto=texto, bbox=tuple(bloco.bbox), bloco=indice))  # type: ignore[arg-type]
        caracteres += len(texto)
        fora += perdidos
    return tuple(trechos), Relatorio(
        trechos=len(trechos),
        caracteres=caracteres,
        fora_da_fonte=fora,
        sem_bloco=sem_bloco,
        diagramas=diagramas,
    )


def escrever(
    doc: DocumentoRico,
    destino: Path,
    *,
    origem: Path | None = None,
    quando: str = "",
    seco: bool = False,
) -> Relatorio:
    """Escreve a folha com a camada invisível. Com `seco=True`, diz o que faria e não grava nada.

    `origem` é o PDF de onde a folha sai; por padrão, o que a `PaginaLida` guarda. O arquivo de
    saída tem **uma página** -- a folha corrigida --, e não o livro inteiro: a aba é da folha
    aberta, e gravar 400 páginas para publicar uma seria surpresa cara.
    """
    import fitz

    trechos, relatorio = camada(doc)
    pagina_lida = doc.origem
    caminho = Path(origem) if origem is not None else Path(pagina_lida.documento if pagina_lida else "")
    if pagina_lida is None or not caminho.name:
        return Relatorio(avisos=("sem página de origem: não há folha para escrever",), seco=seco)
    if not caminho.exists():
        return Relatorio(avisos=(f"o livro {caminho.name} não está no lugar de antes",), seco=seco)

    livro = fitz.open(caminho)
    try:
        if not 0 <= pagina_lida.pagina < livro.page_count:
            return Relatorio(avisos=(f"a folha {pagina_lida.pagina + 1} não existe em {caminho.name}",), seco=seco)
        saida = fitz.open()
        saida.insert_pdf(livro, from_page=pagina_lida.pagina, to_page=pagina_lida.pagina)
        folha = saida[0]
        escritos = 0
        for trecho in trechos:
            x0, y0, x1, y1 = trecho.bbox
            caixa = fitz.Rect(x0 - FOLGA_DA_CAIXA, y0 - FOLGA_DA_CAIXA, x1 + FOLGA_DA_CAIXA, y1 + FOLGA_DA_CAIXA)
            corpo = _corpo_que_cabe(folha, caixa, trecho.texto)
            if corpo <= 0:
                continue
            # `render_mode=3` é o texto invisível: ele entra na busca e não pinta um pixel.
            folha.insert_textbox(
                caixa, trecho.texto, fontsize=corpo, fontname=FONTE_DA_CAMADA, render_mode=3
            )
            escritos += 1
        saida.set_metadata(_metadado(livro, doc, quando))
        relatorio = Relatorio(
            trechos=escritos,
            caracteres=relatorio.caracteres,
            fora_da_fonte=relatorio.fora_da_fonte,
            sem_bloco=relatorio.sem_bloco,
            diagramas=relatorio.diagramas,
            escrito=None if seco else Path(destino),
            seco=seco,
            avisos=_avisos(relatorio),
        )
        if not seco:
            Path(destino).parent.mkdir(parents=True, exist_ok=True)
            saida.save(str(destino))
        saida.close()
        return relatorio
    finally:
        livro.close()


def _corpo_que_cabe(folha: object, caixa: object, texto: str) -> float:
    """O maior corpo, entre os candidatos, com que o texto cabe na caixa. `0` quando nenhum cabe.

    `insert_textbox` devolve o espaço que sobrou -- **negativo quando não coube** --, e é a única
    forma honesta de escolher o corpo: a caixa é a do bloco lido, e o texto corrigido pode ser mais
    longo que o que estava impresso. Escrever fora da caixa poria a busca no lugar errado.
    """
    for corpo in (11.0, 10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0):
        sobra = folha.insert_textbox(  # type: ignore[attr-defined]
            caixa, texto, fontsize=corpo, fontname=FONTE_DA_CAMADA, render_mode=3, overlay=False
        )
        if sobra >= 0:
            return corpo
    return 0.0


def _metadado(livro: object, doc: DocumentoRico, quando: str) -> Mapping[str, str]:
    """O metadado do PDF, declarando **que a camada tem correção humana** e de quando (S-253/S-218).

    Um PDF cuja camada foi corrigida à mão é outro documento, e quem o receber precisa poder saber.
    """
    from ..text import correcao

    original = dict(getattr(livro, "metadata", None) or {})
    feitas = len(correcao.correcoes(doc))
    original["producer"] = "ChessVisionOFF · camada de texto com correção humana (S-253)"
    original["keywords"] = f"camada=humana; correcoes={feitas}" + (f"; data={quando}" if quando else "")
    return {chave: valor for chave, valor in original.items() if isinstance(valor, str)}


def _avisos(relatorio: Relatorio) -> tuple[str, ...]:
    avisos: list[str] = []
    if relatorio.fora_da_fonte:
        avisos.append(
            f"{relatorio.fora_da_fonte} caractere(s) fora da camada: a fonte da base 14 não tem "
            "figurina, e nenhuma fonte é copiada para cá antes de a licença ser conferida"
        )
    if relatorio.sem_bloco:
        avisos.append(f"{relatorio.sem_bloco} corrida(s) sem bloco de origem ficaram fora da camada")
    return tuple(avisos)


def texto_do_relatorio(relatorio: Relatorio) -> str:
    """As três seções da S-254, na forma que o rodapé mostra."""
    onde = relatorio.escrito or ("nada (simulação)" if relatorio.seco else "nada")
    linhas = [f"escrito   {onde}", f"perdido   {relatorio.resumo()}"]
    linhas.append(f"avisado   {'; '.join(relatorio.avisos) or 'nada'}")
    return "\n".join(linhas)


def _sem_uso(_: Sequence[object]) -> None:  # pragma: no cover - reservado
    return None
