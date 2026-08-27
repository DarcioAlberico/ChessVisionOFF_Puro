"""O PDF pesquisável: a camada de texto invisível sobre a página (S-210 e S-253).

**O acervo tem livros sem camada de texto** -- 11 dos 41 na amostra de 2026-08-24 -- e livros cuja
camada erra a notação inteira: a S-211 mediu **zero figurinas** na camada contra 360 no
classificador, com três codificações diferentes em quatro livros. Buscar `Nf3` num livro de xadrez é
a coisa mais óbvia a querer fazer, e não dá.

**Este módulo tem as duas pontas, e elas não competem.**

| item | de onde vem o texto | quantas folhas | granularidade |
|---|---|---|---|
| **S-253** (`escrever`) | o `DocumentoRico` que uma pessoa corrigiu | uma -- a folha aberta | bloco |
| **S-210** (`escrever_camada`) | a `PaginaLida` que o motor leu | o livro | **linha** |

A da S-253 é a melhor versão que aquela página vai ter, e por isso ela é de uma folha só: alguém
sentou e corrigiu. A da S-210 é a que existe para as 400 folhas que ninguém vai corrigir -- e é por
linha porque só assim o retângulo que a busca devolve cobre a palavra, e não o parágrafo.

## Três regras, e as três são sobre honestidade

**A página não muda um pixel.** O texto entra em `render_mode=3` (invisível), sobre a página
original, e o teste compara os pixmaps de antes e depois byte a byte.

**A posição vem do bloco e o texto vem da corrida.** Cada corrida sabe de que bloco veio
(`Corrida.bloco`, S-235), e o bloco tem bbox. **Corrida escrita do zero (`bloco == SEM_BLOCO`) não
entra na camada**: não há onde a pôr, e inventar posição é pior que não ter o texto. O relatório a
conta.

**A procedência vai no metadado do PDF.** Um PDF cuja camada foi corrigida à mão é um documento
diferente de um cuja camada saiu do OCR, e quem o receber precisa poder saber. É a S-219 outra vez:
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
from typing import Any, cast

from .pagina import BlocoDeDiagrama
from .rico import DocumentoRico

__all__ = [
    "FIGURINA_PARA_LETRA",
    "FONTE_DA_CAMADA",
    "PISO_DA_CAMADA",
    "Linha",
    "ParSemMapeamento",
    "Relatorio",
    "RelatorioDaCamada",
    "Trecho",
    "camada",
    "contar_losangos",
    "escrever",
    "escrever_camada",
    "latino",
    "linhas_da_camada",
    "pares_sem_mapeamento",
    "transliterar",
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
            # `render_mode=3` é o texto invisível: ele entra na busca e não pinta um pixel.
            if _escrever_no_maior_corpo(folha, caixa, trecho.texto) <= 0:
                continue
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


def _escrever_no_maior_corpo(folha: object, caixa: object, texto: str) -> float:
    """Escreve o texto no maior corpo em que ele cabe na caixa. `0` quando nenhum coube.

    `insert_textbox` devolve o espaço que sobrou -- **negativo quando não coube** --, e é a única
    forma honesta de escolher o corpo: a caixa é a do bloco lido, e o texto corrigido pode ser mais
    longo que o que estava impresso. Escrever fora da caixa poria a busca no lugar errado.

    **A sonda é a escrita, e não um ensaio dela (S-303).** Esta função chamava-se
    `_corpo_que_cabe` e tinha nome de medição, mas `insert_textbox` do PyMuPDF termina em
    `if rc >= 0: img.commit(overlay)` -- ela **grava**. Os dois chamadores gravavam de novo
    logo depois, e toda linha entrava duas vezes na camada invisível: um PDF exportado devolvia
    `Nf3 exd5\nNf3 exd5\n` onde a folha tem uma linha só. Invisível na tela, visível em toda
    busca, em todo copiar-e-colar e em todo índice que leia o arquivo.

    A saída **não** é medir com `fitz.get_text_length`: essa régua não reproduz a quebra de
    linha do `insert_textbox`, e escolheria um corpo que depois não cabe -- e aí o trecho
    sumiria sem ser contado. A saída é assumir o que a função sempre fez: o corpo que couber
    é o que fica escrito, e `overlay` volta ao padrão, que é o que a escrita real usava.
    """
    for corpo in (11.0, 10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0):
        sobra = folha.insert_textbox(  # type: ignore[attr-defined]
            caixa, texto, fontsize=corpo, fontname=FONTE_DA_CAMADA, render_mode=3
        )
        if sobra >= 0:
            return corpo
    return 0.0


def _metadado(livro: object, doc: DocumentoRico, quando: str) -> Mapping[str, str]:
    """O metadado do PDF, declarando **que a camada tem correção humana** e de quando (S-253/S-219).

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

# --------------------------------------------------------------------------------------
# S-210 -- a camada feita do que o MOTOR leu, e nao do que uma pessoa corrigiu
# --------------------------------------------------------------------------------------

PISO_DA_CAMADA = 0.30
"""Confiança mínima de uma linha para ela entrar na camada invisível.

**É a trava de honestidade deste item, e ela é a mesma ideia da que a spec herdou.** Lá a regra era
*"glifo cuja votação não fecha continua `U+FFFD` e vai para o relatório com o motivo"* -- porque
trocar um losango por um palpite errado é pior que o losango, que pelo menos se vê. Aqui a matéria
é outra (ver `pares_sem_mapeamento`), e a mesma regra cai sobre a linha lida: **uma leitura em que
o modelo não teve votação folgada não entra na camada.**

O motivo é o que a camada invisível faz. Ela não se vê: quem busca `Nf3` e recebe um acerto
acredita que o livro diz `Nf3` *ali*. Uma linha lida com 0,12 de confiança que entrasse na camada
produziria acerto falso **sem nada na tela para desmenti-lo** -- o defeito é pior que o de uma
leitura errada visível, exatamente pela mesma razão que o losango.

O valor é o `ocr.MIN_CONFIDENCE` da S-42, e não um número novo: é o piso com que este projeto já
decide se uma leitura de motor vale como dado. `documento.corte_de_revisar` lê o mesmo."""

FIGURINA_PARA_LETRA = {
    "♔": "K", "♕": "Q", "♖": "R", "♗": "B", "♘": "N", "♙": "P",
    "♚": "K", "♛": "Q", "♜": "R", "♝": "B", "♞": "N", "♟": "P",
}
"""Figurina -> letra do algébrico inglês, para a camada de busca.

## Por que transliterar, quando o item diz "entrega a camada só para o alfabeto latino"

O problema com que a S-210 abre é literal: *"Um leitor não consegue buscar `Nf3` num livro de
xadrez -- que é a coisa mais óbvia a querer buscar num livro de xadrez."* E a S-211 mediu que o
classificador lê **360 figurinas** onde a camada do PDF lê zero. Sem esta tabela, tudo que o motor
leu de mais precioso -- a notação -- cai fora da camada pelo buraco da fonte, e o item entregaria
uma camada de tudo **menos** o que motivou o item.

**A camada é um índice, e não uma renderização**, e é isso que autoriza a troca. A página continua
mostrando `♘`; o que muda é o que a busca encontra. Escrever `N` onde a página imprime `♘` não é
pôr um caractere errado na página -- é pôr na busca a forma que quem busca digita.

**A ambiguidade existe e está declarada:** a letra depende do idioma (`N`/`S`/`C`/`T`), e a tabela
escolhe o **inglês**, que é a única convenção comum entre os oito idiomas do acervo. Quem busca em
alemão por `Sf3` não acha; quem busca por `Nf3` acha em qualquer livro. `--sem-figurinas` desliga a
troca e devolve o comportamento que a fonte impõe, com a contagem ao lado.

Peça branca e preta vão para a **mesma** letra: o algébrico não distingue cor, quem distingue é de
quem é a vez."""

@dataclass(frozen=True)
class Linha:
    """Uma linha da camada: o que escrever, onde, e o quanto o motor confiou nela."""

    texto: str
    bbox: tuple[float, float, float, float]
    pagina: int
    confianca: float = 1.0
    procedencia: str = "glifo"


@dataclass(frozen=True)
class RelatorioDaCamada:
    """O que a camada da S-210 levou, o que ficou de fora e por quê."""

    paginas: int = 0
    linhas: int = 0
    caracteres: int = 0
    figurinas: int = 0
    """Figurinas transliteradas para letra do algébrico. Ver `FIGURINA_PARA_LETRA`."""

    fora_da_fonte: int = 0
    """Caracteres que a fonte da camada não escreve, depois da transliteração."""

    abaixo_do_piso: int = 0
    """Linhas que o motor leu sem votação folgada. **Não entram**, e é o item."""

    ja_tinham_camada: int = 0
    """Páginas cujo PDF já traz texto. A nossa **soma** à delas -- ver `escrever_camada`."""

    escrito: Path | None = None
    seco: bool = False
    avisos: tuple[str, ...] = field(default_factory=tuple)

    def resumo(self) -> str:
        partes = [f"{self.paginas} página(s), {self.linhas} linha(s), {self.caracteres} caractere(s)"]
        if self.figurinas:
            partes.append(f"{self.figurinas} figurina(s) como letra")
        if self.abaixo_do_piso:
            partes.append(f"{self.abaixo_do_piso} linha(s) abaixo do piso")
        if self.fora_da_fonte:
            partes.append(f"{self.fora_da_fonte} caractere(s) fora da fonte")
        return " · ".join(partes)


def transliterar(texto: str) -> tuple[str, int]:
    """`(texto com as figurinas como letra, quantas foram trocadas)`. Ver `FIGURINA_PARA_LETRA`."""
    if not any(c in FIGURINA_PARA_LETRA for c in texto):
        return (texto, 0)
    trocadas = 0
    saida: list[str] = []
    for caractere in texto:
        letra = FIGURINA_PARA_LETRA.get(caractere)
        if letra is None:
            saida.append(caractere)
        else:
            saida.append(letra)
            trocadas += 1
    return ("".join(saida), trocadas)


def linhas_da_camada(
    pagina: object,
    *,
    piso: float = PISO_DA_CAMADA,
    figurinas: bool = True,
) -> tuple[tuple[Linha, ...], RelatorioDaCamada]:
    """As linhas que entram na camada de uma `PaginaLida`. **Pura**: não abre PDF nenhum.

    ## Por linha, e não por bloco -- é o que faz o critério de aceite ser verdade

    A `camada` da S-253 escreve **por bloco**, e ali é o certo: o `DocumentoRico` só tem bbox de
    bloco. Aqui a `PaginaLida` tem bbox de **linha** (`LinhaLida.bbox`), e usá-la é o que torna
    verdadeiro o critério *"a busca por uma palavra da página a encontra, e o retângulo devolvido
    cobre a palavra"*. Com um retângulo de parágrafo, a busca acha a palavra e devolve o parágrafo
    inteiro -- que é a mesma coisa que não saber onde ela está.

    ## O que não entra, e as três razões são diferentes

    | fica de fora | por quê |
    |---|---|
    | linha abaixo de `piso` | o motor não teve votação folgada -- ver `PISO_DA_CAMADA` |
    | bloco de diagrama | `[Diagrama N]` nunca esteve impresso na página |
    | caractere fora da Latin-1 | a fonte da camada não o escreve, e `?` poria um erro na busca |

    A linha da camada de texto do PDF (`procedencia == "camada"`) **entra**: ela vale 1,0 e é o que
    o editor escreveu. O piso não a alcança, e é o certo -- ela não é palpite de motor nenhum.
    """
    from .pagina import BlocoDeDiagrama

    achadas: list[Linha] = []
    caracteres = figurinas_trocadas = fora = abaixo = 0
    for coluna in getattr(pagina, "colunas", ()):
        for bloco in getattr(coluna, "blocos", ()):
            if isinstance(bloco, BlocoDeDiagrama):
                continue
            for linha in getattr(bloco, "linhas", ()):
                bruto = str(getattr(linha, "texto", "")).strip()
                if not bruto:
                    continue
                confianca = float(getattr(linha, "confianca", 1.0))
                if confianca < piso:
                    abaixo += 1
                    continue
                texto, trocadas = transliterar(bruto) if figurinas else (bruto, 0)
                cabivel, perdidos = latino(texto)
                fora += perdidos
                if not cabivel.strip():
                    continue
                achadas.append(
                    Linha(
                        texto=cabivel,
                        bbox=tuple(float(v) for v in linha.bbox),  # type: ignore[arg-type]
                        pagina=int(getattr(pagina, "pagina", 0)),
                        confianca=confianca,
                        procedencia=str(getattr(linha, "procedencia", "glifo")),
                    )
                )
                caracteres += len(cabivel)
                figurinas_trocadas += trocadas

    return tuple(achadas), RelatorioDaCamada(
        paginas=1 if achadas else 0,
        linhas=len(achadas),
        caracteres=caracteres,
        figurinas=figurinas_trocadas,
        fora_da_fonte=fora,
        abaixo_do_piso=abaixo,
    )

def escrever_camada(
    paginas: Sequence[object],
    destino: Path,
    *,
    origem: Path | None = None,
    piso: float = PISO_DA_CAMADA,
    figurinas: bool = True,
    so_sem_camada: bool = False,
    quando: str = "",
    seco: bool = False,
) -> RelatorioDaCamada:
    """Escreve o livro com a camada de texto invisível do que o **motor** leu (S-210).

    `paginas` são `PaginaLida` do mesmo livro. O PDF de saída tem **todas** as folhas do original
    -- as que não foram lidas simplesmente não ganham camada --, porque um livro pesquisável pela
    metade não é um livro pesquisável.

    ## A página não muda um pixel, e isso é conferível

    O texto entra em `render_mode=3`: ele participa da busca e não pinta. `test_a_pagina_nao_muda_um_pixel`
    compara os pixmaps de antes e depois byte a byte, que é o critério de aceite do item.

    ## Quando a folha já tem camada, a nossa **soma** à dela

    Não dá para tirar a que está lá: num PDF digital ela **é** o conteúdo da página, e removê-la
    mudaria o pixel. Então quem tiver as duas encontra as duas -- e o relatório conta as folhas em
    que isso aconteceu, com aviso. `so_sem_camada=True` pula essas folhas, que é o que serve a quem
    quer um livro sem texto duplicado; o padrão escreve, porque a S-211 mediu que a camada de
    origem **não representa figurina** e para notação ela não é alternativa à nossa.

    `seco=True` diz o que faria e não grava nada -- critério de aceite `test_o_dry_run_nao_escreve`.
    """
    import fitz

    lidas = [p for p in paginas if p is not None]
    if not lidas:
        return RelatorioDaCamada(avisos=("nenhuma página lida: não há camada a escrever",), seco=seco)

    caminho = Path(origem) if origem is not None else Path(str(getattr(lidas[0], "documento", "")))
    if not caminho.name:
        return RelatorioDaCamada(avisos=("sem livro de origem: a PaginaLida não guarda o caminho",), seco=seco)
    if not caminho.exists():
        return RelatorioDaCamada(avisos=(f"o livro {caminho.name} não está no lugar de antes",), seco=seco)

    total = RelatorioDaCamada()
    avisos: list[str] = []
    livro = fitz.open(caminho)
    try:
        for lida in lidas:
            indice = int(getattr(lida, "pagina", -1))
            if not 0 <= indice < livro.page_count:
                avisos.append(f"a folha {indice + 1} não existe em {caminho.name}")
                continue
            folha = livro[indice]
            tinha = bool(folha.get_text().strip())
            if tinha and so_sem_camada:
                total = _somar(total, RelatorioDaCamada(ja_tinham_camada=1))
                continue

            linhas, parcial = linhas_da_camada(lida, piso=piso, figurinas=figurinas)
            escritas = 0
            for linha in linhas:
                x0, y0, x1, y1 = linha.bbox
                caixa = fitz.Rect(x0 - FOLGA_DA_CAIXA, y0 - FOLGA_DA_CAIXA, x1 + FOLGA_DA_CAIXA, y1 + FOLGA_DA_CAIXA)
                if _escrever_no_maior_corpo(folha, caixa, linha.texto) <= 0:
                    continue
                escritas += 1
            total = _somar(
                total,
                RelatorioDaCamada(
                    paginas=1,
                    linhas=escritas,
                    caracteres=parcial.caracteres,
                    figurinas=parcial.figurinas,
                    fora_da_fonte=parcial.fora_da_fonte,
                    abaixo_do_piso=parcial.abaixo_do_piso,
                    ja_tinham_camada=1 if tinha else 0,
                ),
            )

        livro.set_metadata(_metadado_da_camada(livro, quando, piso, figurinas))
        if not seco:
            Path(destino).parent.mkdir(parents=True, exist_ok=True)
            livro.save(str(destino))
    finally:
        livro.close()

    if total.abaixo_do_piso:
        avisos.append(
            f"{total.abaixo_do_piso} linha(s) ficaram fora da camada: o motor leu abaixo de "
            f"{piso:.2f}, e uma busca que acertasse ali seria um acerto falso sem nada na tela "
            "para desmenti-lo"
        )
    if total.fora_da_fonte:
        avisos.append(
            f"{total.fora_da_fonte} caractere(s) fora da Latin-1 não entraram: a fonte da camada é "
            "a base 14, e nenhuma fonte é copiada para cá antes de a licença ser conferida"
        )
    if total.ja_tinham_camada:
        avisos.append(
            f"{total.ja_tinham_camada} folha(s) já tinham texto: a camada nova SOMA à que estava "
            "lá, porque tirar a de origem mudaria o pixel. Use --so-sem-camada para pulá-las"
        )
    return _somar(total, RelatorioDaCamada(escrito=None if seco else Path(destino), seco=seco, avisos=tuple(avisos)))


def _somar(a: RelatorioDaCamada, b: RelatorioDaCamada) -> RelatorioDaCamada:
    """Acumula duas parciais. Os campos que não somam -- destino, seco, avisos -- vêm de `b`."""
    return RelatorioDaCamada(
        paginas=a.paginas + b.paginas,
        linhas=a.linhas + b.linhas,
        caracteres=a.caracteres + b.caracteres,
        figurinas=a.figurinas + b.figurinas,
        fora_da_fonte=a.fora_da_fonte + b.fora_da_fonte,
        abaixo_do_piso=a.abaixo_do_piso + b.abaixo_do_piso,
        ja_tinham_camada=a.ja_tinham_camada + b.ja_tinham_camada,
        escrito=b.escrito or a.escrito,
        seco=b.seco or a.seco,
        avisos=b.avisos or a.avisos,
    )


def _metadado_da_camada(livro: object, quando: str, piso: float, figurinas: bool) -> Mapping[str, str]:
    """A procedência da camada, no metadado do PDF.

    **É a S-219 outra vez.** Um PDF cuja camada saiu do classificador deste projeto é um documento
    diferente de um cuja camada veio do editor, e quem o receber precisa poder saber qual é --
    inclusive com que piso ela foi feita, que é o que decide o que ficou de fora.
    """
    atual = dict(getattr(livro, "metadata", None) or {})
    marca = f"ChessVisionOFF S-210: camada de glifo, piso {piso:.2f}"
    if figurinas:
        marca += ", figurina como letra"
    if quando:
        marca += f", {quando}"
    atual["keywords"] = " · ".join(x for x in (atual.get("keywords", ""), marca) if x)
    atual["producer"] = "ChessVisionOFF"
    return atual

# --------------------------------------------------------------------------------------
# O caminho vizinho da S-210, e a medicao que decidiu nao construi-lo
# --------------------------------------------------------------------------------------

SEM_MAPEAMENTO = "�"
"""`U+FFFD`, o losango de substituição. É o que um PDF digital traz quando a fonte não diz que
caractere aquele glifo é."""


@dataclass(frozen=True)
class ParSemMapeamento:
    """Um par `(fonte, glifo)` que a camada do PDF não sabe traduzir, e quantas vezes ele aparece."""

    fonte: str
    ocorrencias: int


def pares_sem_mapeamento(livro: Path | str, *, paginas: int = 40) -> tuple[ParSemMapeamento, ...]:
    """Os pares `(fonte, glifo)` que a camada do PDF devolve como `U+FFFD`.

    ## Por que esta função existe, e por que o reescritor de `ToUnicode` **não** existe

    A S-210 descreve um caminho vizinho e mais barato: quando o PDF já é digital e o defeito é só
    de mapeamento -- fontes Type0/Identity-H em que o produtor escreveu `U+FFFD` para cada figurina
    --, dá para reescrever **só a tabela `ToUnicode`**, e o texto passa a copiar e buscar certo,
    sem OCR nenhum. O item cita 216 pares assim no Yusupov e 101 no Aagaard, e marca o número como
    *(medido lá)*.

    **Medido aqui em 2026-08-26, sobre 40 folhas de cada um dos 14 primeiros livros do acervo: zero.**
    Nenhum `U+FFFD` em nenhum deles. O defeito de mapeamento deste acervo é outro, e a S-211 já o
    tinha medido: a camada não devolve losango, devolve o **codepoint cru da fonte de xadrez** --
    `2.♘xd4` sai como `2.l0xd4` no AAGAARD, e como ASCII correto no Dvoretsky. Não há o que
    reescrever numa tabela que existe e está preenchida com outra coisa.

    Então o reescritor não foi construído, e esta função é **a medição que sustenta a recusa** --
    a regra nº 1 desta spec: nenhum número herdado conta como medição deste projeto. Ela fica no
    disco porque um acervo com um livro à la Yusupov faria o número deixar de ser zero, e aí o
    caminho vale a pena.

    Devolve os pares ordenados por ocorrência decrescente. Lista vazia é a resposta deste acervo.
    """
    import fitz

    documento = fitz.open(Path(livro))
    try:
        passo = max(1, documento.page_count // max(1, paginas))
        folhas = [documento[i].get_text("dict") for i in range(0, documento.page_count, passo)]
    finally:
        documento.close()
    return contar_losangos(folhas)


def contar_losangos(folhas: Sequence[Mapping[str, object]]) -> tuple[ParSemMapeamento, ...]:
    """A contagem pura, sobre os dicionários que `get_text("dict")` devolve.

    Separada de `pares_sem_mapeamento` porque a parte que abre PDF não é testável com um PDF
    sintético: a `helv` da base 14 **não carrega `U+FFFD`** -- ela o mapeia para `·` na gravação,
    e um teste que construísse a folha mediria o mapeamento da fonte de teste em vez desta conta.
    """
    contagem: dict[str, int] = {}
    for folha in folhas:
        # O `get_text("dict")` do PyMuPDF devolve dicionarios aninhados sem tipo declarado; o
        # `cast` diz o formato uma vez, em vez de um `type: ignore` por nivel de laco.
        blocos = cast("Sequence[Mapping[str, Any]]", folha.get("blocks") or ())
        for bloco in blocos:
            for linha in cast("Sequence[Mapping[str, Any]]", bloco.get("lines") or ()):
                for trecho in cast("Sequence[Mapping[str, Any]]", linha.get("spans") or ()):
                    quantos = str(trecho.get("text", "")).count(SEM_MAPEAMENTO)
                    if quantos:
                        fonte = str(trecho.get("font", "?"))
                        contagem[fonte] = contagem.get(fonte, 0) + quantos
    return tuple(
        ParSemMapeamento(fonte=fonte, ocorrencias=n)
        for fonte, n in sorted(contagem.items(), key=lambda par: (-par[1], par[0]))
    )


def _sem_uso(_: Sequence[object]) -> None:  # pragma: no cover - reservado
    return None
