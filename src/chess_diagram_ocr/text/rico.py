"""O documento do editor como dado, e não como tag do widget (S-235).

**O defeito que este módulo existe para impedir.** O que a aba de texto entrega quando alguém salva
é uma `str` -- `self.editor.get("1.0", "end-1c")` --, e tudo o mais que está na tela fica de fora: as
tags de faixa, o negrito que a S-237 acabou de trazer da camada, as miniaturas. Enquanto a aba não
tinha formatação, isso era barato. Deixa de ser no primeiro recurso de edição: um
`tag_configure("negrito", font=...)` resolve o negrito **na tela** em quatro linhas e entrega, no
botão Salvar, exatamente o mesmo `.txt` de antes.

E o defeito não apareceria em teste de interface nenhum, porque na tela está tudo certo. Apareceria
no arquivo de quem passou a tarde corrigindo uma página.

**Tag do Tk não é dado: ela nasce no widget, vive no widget e morre com ele.** Este módulo é o outro
lado -- o documento que sobrevive ao widget, sem `import tkinter`, na mesma regra que pôs
`text/documento.py` fora da janela.

## A corrida, e por que ela carrega quatro coisas que não são texto

Uma `Corrida` é um trecho contíguo de texto com os mesmos atributos. Além deles ela carrega:

    faixa          a régua de confiança, que é de outro dono (text/documento.py)
    bloco          de que bloco da PaginaLida ela saiu -- SEM_BLOCO quando foi escrita à mão
    procedencia    quem leu aquilo: camada, glifo, rapidocr, humano -- ou None
    tipo           texto, diagrama ou separador

**`faixa` não entra em `Atributos`, e essa fronteira é o item.** Confiança é medida do
reconhecimento; atributo é escolha de quem escreve. Num campo só, "pintar de vermelho" e "o motor
adivinhou" seriam a mesma informação -- e é a colisão que a S-242 vai ter de desfazer canal a canal.

**`bloco` é o que torna a correção aproveitável.** Sem ele, corrigir uma palavra não tem como dizer
*sobre que bloco* a correção foi feita, e a S-239 não tem o que entregar à fila da S-212.

## Duas decisões que a implementação virou, e as duas divergem do desenho da spec

1. **`procedencia` é `Procedencia | None`, e não `"humano"` por padrão.** O separador entre dois
   blocos não foi lido por ninguém e não foi escrito por ninguém: dizer que ele é humano seria
   inventar autoria de uma linha em branco. `None` é "não veio de leitura", que é o mesmo idioma do
   `LinhaLida.negrito` da S-237 -- e quem carimba `"humano"` de fato é a S-239, no momento em que a
   edição acontece.

2. **`cor` e `estilo` nascem com o registro vazio.** Os dois são campos reais e validados, e hoje o
   único valor válido é `""`, porque quem povoa `CORES_DE_AUTOR` é a S-242 e quem povoa `ESTILOS` é
   a S-249. É a mesma decisão do `Comando.icone` da S-219: o campo existe e recusa nome que ninguém
   desenhou, em vez de aceitar qualquer coisa e virar promessa vazia.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields
from typing import Any, get_args

from . import documento
from .pagina import PaginaLida, Procedencia

SEM_BLOCO = -1
"""O `bloco` de uma corrida que não saiu da página: texto escrito à mão.

Não é `None` porque o campo é índice, e um índice ausente que se compara com `is None` num laço de
edição é uma condição a mais em todo lugar que o lê. `-1` nunca é índice válido de `PaginaLida.blocos`."""

TEXTO = "texto"
DIAGRAMA = "diagrama"
SEPARADOR = "separador"
TIPOS: tuple[str, ...] = (TEXTO, DIAGRAMA, SEPARADOR)
"""Os mesmos três de `documento.Segmento.tipo`, e o conjunto é fechado.

Fechado porque `para_texto` e a fusão dependem dele: uma corrida de tipo desconhecido não tem como
saber se pode ser fundida com a vizinha nem o que o exportador deve fazer com ela."""

PROCEDENCIAS: tuple[str, ...] = get_args(Procedencia)
"""As quatro de `text/pagina.py`, **derivadas do `Literal`** e não recopiadas.

Copiar a lista aqui seria a segunda declaração do mesmo conjunto -- e a que ficaria para trás no dia
em que uma quinta procedência entrasse."""

CORES_DE_AUTOR: tuple[str, ...] = ()
"""Os nomes de cor que o autor pode aplicar. **Vazio hoje, e é a resposta certa.**

Quem povoa isto é a S-242, que ainda precisa decidir o canal: a aba já usa cor de letra para dizer
confiança (`revisar` em `tokens.PROBLEMA`), e uma cor de autor no mesmo canal seria a mesma tinta com
dois significados na mesma linha.

**São nomes, e nunca hexadecimal nem papel de `ui/tokens.py`.** O domínio nomeia o conceito e a
interface o resolve em cor -- é o que `PAPEL_DA_FAIXA` já faz com `revisar` e `conferir`, e é o que
mantém este módulo sem saber que existe uma janela."""

ESTILOS: tuple[str, ...] = ()
"""Os estilos de parágrafo -- título, prosa, notação, legenda. **Vazio até a S-249.**

Pelo mesmo motivo do acima: um estilo declarado que nada aplica é o item de menu sem comando que a
S-161 registra como defeito."""


@dataclass(frozen=True)
class Atributos:
    """Como um trecho é desenhado. Só o que o autor escolhe -- confiança não mora aqui."""

    negrito: bool = False
    italico: bool = False
    sublinhado: bool = False
    cor: str = ""
    """Nome em `CORES_DE_AUTOR`. `""` é "sem cor de autor", e é o único válido até a S-242."""

    estilo: str = ""
    """Nome em `ESTILOS`. `""` é "sem estilo declarado", e é o único válido até a S-249."""

    def __post_init__(self) -> None:
        # Levanta em vez de cair no vazio, pela razão de `estilos.estilo_de_botao`: um nome escrito
        # errado que virasse "sem cor" é exatamente o estado que este campo veio impedir, e ele
        # voltaria sem ninguém notar.
        if self.cor and self.cor not in CORES_DE_AUTOR:
            raise KeyError(f"cor de autor desconhecida: {self.cor!r}. As válidas estão em CORES_DE_AUTOR.")
        if self.estilo and self.estilo not in ESTILOS:
            raise KeyError(f"estilo desconhecido: {self.estilo!r}. Os válidos estão em ESTILOS.")

    @property
    def padrao(self) -> bool:
        """Nada foi escolhido neste trecho. É o que a fusão e a serialização perguntam."""
        return self == PADRAO

    def para_json(self) -> dict[str, Any]:
        """Só o que difere do padrão.

        **O arquivo não guarda os cinco campos de todo trecho**, e não é economia de bytes: é o que
        faz um campo novo -- a cor da S-242, o estilo da S-249 -- entrar sem mudar uma linha dos
        arquivos já gravados. Quem lê preenche o resto com o padrão."""
        atual = {campo.name: getattr(self, campo.name) for campo in fields(self)}
        return {nome: valor for nome, valor in atual.items() if valor != getattr(PADRAO, nome)}

    @classmethod
    def de_json(cls, dados: Any) -> Atributos:
        """O que o arquivo trouxer, e o padrão para o resto. Chave desconhecida é ignorada.

        Ignorada e não recusada porque o caso é um arquivo gravado por uma versão **mais nova**, que
        conhece um atributo que esta não conhece: abrir o texto sem aquele atributo é melhor que
        recusar o arquivo inteiro. Quem recusa versão futura é o formato da S-238, que tem o número
        para comparar -- aqui não há."""
        if not isinstance(dados, dict):
            return PADRAO
        conhecidos = {campo.name for campo in fields(cls)}
        return cls(**{nome: valor for nome, valor in dados.items() if nome in conhecidos})


PADRAO = Atributos()
"""O trecho sem escolha nenhuma. Instância única para a comparação da fusão ser barata."""


@dataclass(frozen=True)
class Corrida:
    """Um trecho contíguo de texto com os mesmos atributos -- a unidade do documento."""

    texto: str
    atributos: Atributos = PADRAO
    faixa: str = documento.TRANQUILO
    """A régua de confiança, de `text/documento.py`. **Não é atributo**: ver o cabeçalho."""

    bloco: int = SEM_BLOCO
    """Índice em `PaginaLida.blocos`, ou `SEM_BLOCO` para texto escrito à mão."""

    procedencia: Procedencia | None = None
    """Quem leu isto, ou `None` quando não veio de leitura nenhuma. Ver o cabeçalho."""

    tipo: str = TEXTO

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS:
            raise KeyError(f"tipo de corrida desconhecido: {self.tipo!r}. Os válidos estão em TIPOS.")
        if self.procedencia is not None and self.procedencia not in PROCEDENCIAS:
            raise KeyError(f"procedência desconhecida: {self.procedencia!r}. As válidas estão em PROCEDENCIAS.")
        if self.faixa not in documento.FAIXAS:
            raise KeyError(f"faixa desconhecida: {self.faixa!r}. As válidas estão em documento.FAIXAS.")

    @property
    def e_diagrama(self) -> bool:
        return self.tipo == DIAGRAMA

    @property
    def da_pagina(self) -> bool:
        """Saiu de um bloco da página -- e não da mão de quem edita."""
        return self.bloco != SEM_BLOCO

    def _chave_de_fusao(self) -> tuple[Any, ...]:
        """Tudo o que **não** é o texto. Duas corridas com a mesma chave são a mesma corrida partida."""
        return (self.atributos, self.faixa, self.bloco, self.procedencia, self.tipo)

    def para_json(self) -> dict[str, Any]:
        dados: dict[str, Any] = {"texto": self.texto}
        # Os quatro campos de contexto só aparecem quando dizem alguma coisa, pela mesma razão de
        # `Atributos.para_json`: um documento de prosa comum não carrega quatro chaves por trecho.
        if not self.atributos.padrao:
            dados["atributos"] = self.atributos.para_json()
        if self.faixa != documento.TRANQUILO:
            dados["faixa"] = self.faixa
        if self.bloco != SEM_BLOCO:
            dados["bloco"] = self.bloco
        if self.procedencia is not None:
            dados["procedencia"] = self.procedencia
        if self.tipo != TEXTO:
            dados["tipo"] = self.tipo
        return dados

    @classmethod
    def de_json(cls, dados: Any) -> Corrida:
        if not isinstance(dados, dict):
            raise ValueError(f"corrida: esperava objeto, veio {type(dados).__name__}")
        return cls(
            texto=str(dados.get("texto", "")),
            atributos=Atributos.de_json(dados.get("atributos")),
            faixa=str(dados.get("faixa", documento.TRANQUILO)),
            bloco=int(dados.get("bloco", SEM_BLOCO)),
            procedencia=dados.get("procedencia"),
            tipo=str(dados.get("tipo", TEXTO)),
        )


def fundir(corridas: Iterable[Corrida]) -> tuple[Corrida, ...]:
    """Junta corridas vizinhas que só diferem no texto, e descarta as vazias.

    **Sem isto, digitar é o que estraga o documento.** Cada tecla numa implementação ingênua produz
    uma corrida de um caractere, e uma página corrigida à mão viraria mil corridas com os mesmos
    cinco atributos repetidos mil vezes -- no arquivo, na exportação e em toda travessia.

    Idempotente por construção: fundir o que já está fundido não acha vizinhas com a mesma chave.
    """
    saida: list[Corrida] = []
    for corrida in corridas:
        if not corrida.texto:
            # Corrida vazia não é conteúdo, e mantê-la faria a contagem de corridas depender de
            # quantas vezes alguém apagou uma seleção.
            continue
        if saida and saida[-1]._chave_de_fusao() == corrida._chave_de_fusao():
            anterior = saida[-1]
            saida[-1] = Corrida(
                texto=anterior.texto + corrida.texto,
                atributos=anterior.atributos,
                faixa=anterior.faixa,
                bloco=anterior.bloco,
                procedencia=anterior.procedencia,
                tipo=anterior.tipo,
            )
            continue
        saida.append(corrida)
    return tuple(saida)


@dataclass(frozen=True)
class DocumentoRico:
    """O que o editor mostra e o que o arquivo guarda -- a `PaginaLida` mais o que a mão fez nela."""

    corridas: tuple[Corrida, ...] = ()
    origem: PaginaLida | None = None
    """A página que originou isto, inteira. `None` para um documento escrito do zero.

    Vai junto porque é o que permite reabrir o arquivo e ainda ter bbox, confiança e diagrama --
    isto é, **recortar a miniatura de novo a partir do PDF** em vez de embutir imagem no arquivo.
    Ela já serializa sem perda por critério de aceite da S-211."""

    def para_texto(self) -> str:
        """O texto corrido, sem atributo nenhum.

        **Esta é a trava de não-regressão do item:** enquanto ela devolver o mesmo que
        `"".join(s.texto for s in documento.segmentos(pagina))`, trocar a fonte do `.txt` não muda o
        `.txt` de ninguém."""
        return "".join(corrida.texto for corrida in self.corridas)

    @property
    def diagramas(self) -> tuple[Corrida, ...]:
        """As corridas de diagrama, na ordem em que aparecem no texto."""
        return tuple(c for c in self.corridas if c.e_diagrama)

    def bloco_de(self, corrida: Corrida) -> Any:
        """O bloco da `PaginaLida` de onde a corrida saiu, ou `None` se ela não veio da página."""
        if self.origem is None or not corrida.da_pagina:
            return None
        blocos = self.origem.blocos
        return blocos[corrida.bloco] if 0 <= corrida.bloco < len(blocos) else None

    def normalizado(self) -> DocumentoRico:
        """O mesmo documento com as corridas fundidas. Ver `fundir`."""
        return DocumentoRico(corridas=fundir(self.corridas), origem=self.origem)

    def para_json(self) -> dict[str, Any]:
        """O documento como JSON. **Sem número de versão**, que é do formato de arquivo (S-238).

        Misturar os dois faria este módulo ter opinião sobre compatibilidade de arquivo, que é
        assunto de quem grava o arquivo -- e são duas coisas que envelhecem em ritmos diferentes."""
        dados: dict[str, Any] = {"corridas": [c.para_json() for c in self.corridas]}
        if self.origem is not None:
            dados["origem"] = self.origem.para_json()
        return dados

    @classmethod
    def de_json(cls, dados: Any) -> DocumentoRico:
        if not isinstance(dados, dict):
            raise ValueError(f"documento: esperava objeto, veio {type(dados).__name__}")
        origem = dados.get("origem")
        return cls(
            corridas=tuple(Corrida.de_json(c) for c in dados.get("corridas", ())),
            origem=PaginaLida.de_json(origem) if origem is not None else None,
        )


def de_pagina(pagina: PaginaLida) -> DocumentoRico:
    """A página lida como documento do editor. **A única ponte entre os dois.**

    O editor deixa de percorrer `documento.segmentos` direto e passa a desenhar isto, e a fronteira
    continua onde estava: `documento.py` é quem decide faixa, separador e ordem de leitura; este
    módulo não redecide nada disso -- traduz.

    O índice do bloco sai por **identidade** e não por igualdade: dois parágrafos com o mesmo texto,
    a mesma bbox e a mesma confiança são dataclasses congeladas iguais, e casá-los por `==` daria o
    mesmo índice aos dois -- que é a correção do primeiro indo para o bloco errado.
    """
    indice_de = {id(bloco): i for i, bloco in enumerate(pagina.blocos)}
    corridas: list[Corrida] = []
    for segmento in documento.segmentos(pagina):
        bloco = segmento.bloco
        corridas.extend(
            _corridas_do_segmento(
                segmento,
                bloco=indice_de.get(id(bloco), SEM_BLOCO) if bloco is not None else SEM_BLOCO,
                procedencia=getattr(bloco, "procedencia", None) if bloco is not None else None,
            )
        )
    return DocumentoRico(corridas=tuple(corridas), origem=pagina)


def _corridas_do_segmento(segmento: documento.Segmento, *, bloco: int, procedencia) -> list[Corrida]:  # noqa: ANN001
    """O segmento partido nas corridas que o desenham -- uma por trecho de mesma tipografia.

    **Por que um bloco vira mais de uma corrida.** O atributo do bloco é "todas as linhas ou
    `None`", e essa regra conservadora custa tudo na página real: medida a folha 311 do `Secrets of
    Chess Training`, ela tem **19 linhas em itálico** -- uma citação de 17 linhas seguidas -- e
    **nenhum bloco itálico**, porque a citação e a prosa em volta caíram no mesmo parágrafo de 38
    linhas. Desenhar por bloco ali seria desenhar nada.

    A `LinhaLida` sabe o que o bloco não sabe, e este é o lugar de usar: linhas vizinhas de mesma
    tipografia viram uma corrida.

    **E o texto não muda um caractere.** O corte é feito exatamente nos pontos em que `bloco.texto`
    junta as linhas, e o espaço da junção fica no fim da corrida anterior. Se a soma não bater com o
    que o bloco diz -- outro tipo de bloco, outra regra de junção --, sai uma corrida só: o texto
    vale mais que o atributo, e é ele que a S-235 travou.
    """
    tipo = _tipo_do_segmento(segmento)
    comum = {"faixa": segmento.faixa, "bloco": bloco, "procedencia": procedencia, "tipo": tipo}
    inteiro = Corrida(
        texto=segmento.texto,
        atributos=Atributos(negrito=segmento.negrito, italico=segmento.italico),
        **comum,
    )
    linhas = getattr(segmento.bloco, "linhas", ())
    if tipo != TEXTO or len(linhas) < 2:
        return [inteiro]
    if " ".join(linha.texto for linha in linhas) != segmento.texto:
        return [inteiro]

    grupos = _agrupar(linhas)
    saida: list[Corrida] = []
    for k, ((negrito, italico), textos) in enumerate(grupos):
        junta = " ".join(textos)
        # O espaço da junção fica no fim da corrida anterior, e não no começo da seguinte: assim a
        # corrida itálica começa na primeira letra da citação, e não num espaço em pé antes dela.
        saida.append(
            Corrida(
                texto=junta if k == len(grupos) - 1 else junta + " ",
                atributos=Atributos(negrito=negrito, italico=italico),
                **comum,
            )
        )
    return saida


def _agrupar(linhas: Sequence[Any]) -> list[tuple[tuple[bool, bool], list[str]]]:
    """Linhas vizinhas de mesma tipografia, na ordem. `None` conta como "não", como na tela."""
    grupos: list[tuple[tuple[bool, bool], list[str]]] = []
    for linha in linhas:
        chave = (getattr(linha, "negrito", None) is True, getattr(linha, "italico", None) is True)
        if grupos and grupos[-1][0] == chave:
            grupos[-1][1].append(linha.texto)
            continue
        grupos.append((chave, [linha.texto]))
    return grupos


def _tipo_do_segmento(segmento: documento.Segmento) -> str:
    """O tipo da corrida a partir do tipo do segmento, recusando o que não conhecemos.

    `documento.Segmento.tipo` é `str` livre; `Corrida.tipo` é fechado. A conversão é onde essa
    diferença aparece, e deixá-la implícita faria um segmento de tipo novo virar corrida de texto em
    silêncio -- e o editor desenharia uma tabela como se fosse parágrafo.
    """
    if segmento.tipo not in TIPOS:
        raise KeyError(f"segmento de tipo desconhecido: {segmento.tipo!r}. Os válidos estão em TIPOS.")
    return segmento.tipo


def corridas_de_texto(texto: str, *, atributos: Atributos = PADRAO) -> tuple[Corrida, ...]:
    """Um documento escrito do zero: uma corrida, sem bloco e sem procedência.

    Existe para o caminho que a S-238 vai precisar -- abrir um arquivo cujo PDF sumiu -- e para os
    testes não montarem uma `PaginaLida` inteira só para afirmar uma fusão.
    """
    return fundir([Corrida(texto=texto, atributos=atributos)])


def de_texto(texto: str) -> DocumentoRico:
    """Um documento sem página: só o que alguém escreveu."""
    return DocumentoRico(corridas=corridas_de_texto(texto))


__all__ = [
    "CORES_DE_AUTOR",
    "DIAGRAMA",
    "ESTILOS",
    "PADRAO",
    "PROCEDENCIAS",
    "SEM_BLOCO",
    "SEPARADOR",
    "TEXTO",
    "TIPOS",
    "Atributos",
    "Corrida",
    "DocumentoRico",
    "corridas_de_texto",
    "de_pagina",
    "de_texto",
    "fundir",
]
