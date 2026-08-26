"""A fila de revisão de caractere, ordenada por valor de informação (S-212).

**O problema é de aritmética.** Uma página tem ~2.000 caracteres; a 98% de acerto são 40 erros, e
achá-los a olho é o que torna a revisão inviável. A S-22 resolveu isto para diagramas ordenando
por valor de informação -- corrigir um diagrama que o modelo já lê com 0,999 não ensina nada. Para
caractere a fila não existia.

## A régua é a da S-189, e ela já está calculada

O item manda ordenar pela **divergência entre a leitura por linha e a por caractere**, que é onde
o erro se concentra. Essa divergência não é uma medida nova a inventar aqui: a S-189 já a
transformou em número, e o número é a própria confiança.

    confianca_por_concordancia(glifo, bloco)  =  max(...)  quando as duas leituras concordam
                                                 min(...)  quando divergem

Divergir **não é meio-termo** -- é o cabeçalho da S-189 --, e por isso a confiança de um box
divergente é a menor das duas. Ordenar por `1 - confiança` *é* ordenar por divergência, com a
calibração que já foi medida. Reinventar um segundo escalar de divergência daria dois números
para a mesma pergunta, e a primeira vez que discordassem não haveria como dizer qual estava certo.

## E é isso que faz a cor e a posição concordarem, por construção

O critério de aceite que mais importa aqui é negativo: *"a cor do box na tela e a posição na fila
concordam -- lá elas discordaram, e um box verde no topo da fila destrói a confiança na fila
inteira"*. A garantia não é um teste; é não haver duas fontes. A cor sai de
`documento.faixa_de_confianca`, e a fila ordena por `1 - confiança`. **A mesma função, o mesmo
número.** `test_a_cor_do_box_e_a_posicao_na_fila_concordam` afirma a monotonia, mas ela é
consequência, e não algo que este módulo precise manter à mão.

O corte que separa `conferir` de `tranquilo` (`documento.CORTE_DE_CONFERIR`, 0,75) foi declarado
lá com um comentário dizendo que quem decidiria se ele está no lugar certo seria esta S-212.
`distribuicao` é a resposta: ela conta a fila por faixa, e é o que permite dizer se 0,75 separa
"o modelo tinha certeza" de "o modelo escolheu" **neste** acervo.

## A régua muda quando o leitor de linha não roda, e a fila diz qual usou

`modo_bloco` está **desligado por padrão** desde a S-188 -- na página inteira ele custa ~50x o
tempo e piora o livro nativo digital. Sem ele não há segunda leitura, e portanto não há
divergência: todo box tem `do_glifo == do_bloco`, e a fila ordena pela confiança do classificador
sozinho. Isso não é defeito, é o estado normal do programa -- e a fila **declara** em qual dos
dois mundos ela foi montada (`Fila.regua`), porque uma fila que não diz por que ordenou assim é
uma lista.

## A margem fica de fora, e a recusa é medida

`ClassificadorDeGlifo.margem` existe e custa zero -- as probabilidades já foram calculadas. Ela
**não** entra na ordenação, e o motivo está escrito no projeto de origem: duas fases de lá
concluíram que a margem ordena melhor que a confiança, e a terceira mostrou que **as duas estavam
medindo errado**; refeita com os defeitos corrigidos, a margem perdeu. O item é explícito: *"a
ordenação por margem só entra com tabela ao lado"*. Ela viaja no item (`Item.margem`) para que a
tabela possa ser feita sem remontar a fila, e não é lida por `ordenar`.

## A fila sobrevive a salvar e reabrir, inclusive o que já foi revisado

No projeto de origem, salvar zerava a fila, e o defeito ficou documentado como desenho por meses.
Aqui o estado de cada item é campo do item, e `de_json`/`para_json` o levam nos dois sentidos --
`revisado` e `descartado` continuam na fila, fora de `pendentes`, e nunca voltam ao topo por terem
sido relidos.

**Nada aqui escreve em `training_data/`.** Esta fila diz o que olhar; quem transforma correção em
amostra é a S-214, que tem a quarentena e a etapa humana no meio. É a regra nº 2 da
`SPEC_TEXTO`, e as duas pontas têm a cicatriz.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from ..config import PROJECT_ROOT
from .documento import faixa_de_confianca

logger = logging.getLogger(__name__)

VERSAO = 1
"""Versão do arquivo da fila. Sobe quando um campo muda de significado, não quando nasce um."""

CAMINHO_PADRAO = PROJECT_ROOT / "data" / "fila_caractere.json"

Estado = Literal["pendente", "revisado", "descartado"]
ESTADOS: tuple[Estado, ...] = ("pendente", "revisado", "descartado")

Regua = Literal["divergencia", "confianca"]
"""Por que a fila ordenou assim. Ver "A régua muda" no cabeçalho."""


@dataclass(frozen=True)
class Item:
    """Uma leitura para alguém olhar, com de onde ela veio e o quanto ela vale.

    `do_glifo` e `do_bloco` são as duas leituras da S-189. Quando o leitor de linha não rodou --
    o padrão -- as duas são iguais, e é assim que `Fila.regua` sabe em que mundo está.
    """

    documento: str
    pagina: int
    coluna: int
    linha: int
    texto: str
    """O que saiu da leitura. Um caractere quando o item é de box, a linha quando é de linha."""

    confianca: float
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    box: int = -1
    """Índice do box dentro da linha, ou `-1` quando o item é a linha inteira."""

    do_glifo: str = ""
    do_bloco: str = ""
    procedencia: str = "glifo"
    margem: float = -1.0
    """`1 - p2/p1` do classificador, ou `-1` quando não se mediu. **Não entra na ordenação** --
    ver "A margem fica de fora" no cabeçalho."""

    estado: Estado = "pendente"
    corrigido: str = ""
    """O que a mão pôs no lugar. Vazio enquanto ninguém corrigiu, e vazio também quando a mão
    confirmou a leitura -- quem diz que houve passagem humana é `estado`, não este campo."""

    @property
    def divergem(self) -> bool:
        """As duas leituras da S-189 discordaram neste item."""
        return bool(self.do_bloco) and self.do_glifo != self.do_bloco

    @property
    def tem_duas_leituras(self) -> bool:
        return bool(self.do_glifo) and bool(self.do_bloco)

    @property
    def valor(self) -> float:
        """O valor de informação: `1 - confiança`. Ver o cabeçalho para por que é só isto."""
        return 1.0 - float(self.confianca)

    @property
    def faixa(self) -> str:
        """A mesma faixa que pinta o box na tela. **A mesma função**, e não o mesmo número."""
        return faixa_de_confianca(self.confianca, self.procedencia)

    @property
    def chave(self) -> tuple[str, int, int, int, int]:
        """A identidade do item na página. É o que o desempate usa, e o que reabrir casa."""
        return (self.documento, self.pagina, self.coluna, self.linha, self.box)

    def para_json(self) -> dict[str, Any]:
        return {
            "documento": self.documento,
            "pagina": self.pagina,
            "coluna": self.coluna,
            "linha": self.linha,
            "box": self.box,
            "texto": self.texto,
            "confianca": round(float(self.confianca), 6),
            "bbox": [round(float(v), 3) for v in self.bbox],
            "do_glifo": self.do_glifo,
            "do_bloco": self.do_bloco,
            "procedencia": self.procedencia,
            "margem": round(float(self.margem), 6),
            "estado": self.estado,
            "corrigido": self.corrigido,
        }

    @classmethod
    def de_json(cls, dados: Any) -> Item:
        if not isinstance(dados, dict):
            raise FilaInvalida(f"item: esperava objeto, veio {type(dados).__name__}")
        bbox = dados.get("bbox") or (0.0, 0.0, 0.0, 0.0)
        if len(tuple(bbox)) != 4:
            raise FilaInvalida(f"item: bbox com {len(tuple(bbox))} números, esperava 4")
        estado = dados.get("estado", "pendente")
        return cls(
            documento=str(dados.get("documento", "")),
            pagina=int(dados.get("pagina", 0)),
            coluna=int(dados.get("coluna", 0)),
            linha=int(dados.get("linha", 0)),
            box=int(dados.get("box", -1)),
            texto=str(dados.get("texto", "")),
            confianca=float(dados.get("confianca", 0.0)),
            bbox=tuple(float(v) for v in bbox),  # type: ignore[arg-type]
            do_glifo=str(dados.get("do_glifo", "")),
            do_bloco=str(dados.get("do_bloco", "")),
            procedencia=str(dados.get("procedencia", "glifo")),
            margem=float(dados.get("margem", -1.0)),
            estado=estado if estado in ESTADOS else "pendente",
            corrigido=str(dados.get("corrigido", "")),
        )


class FilaInvalida(ValueError):
    """O arquivo da fila não é o que ele diz ser. Mesma forma de `pagina.PaginaInvalida`."""


def ordenar(itens: Iterable[Item]) -> list[Item]:
    """Os itens por valor de informação decrescente. O de menor confiança vem primeiro.

    **Não há bandas de peso aqui, e a ausência é a decisão do item.** A tentação é a da S-22 --
    faixas separadas por ordem de grandeza, uma dominando as de baixo -- e ela está recusada:
    pôr a divergência numa banda acima da confiança colocaria um box divergente de 0,99 na frente
    de um box de 0,10, isto é, **um box verde no topo da fila**, que é exatamente o defeito que o
    critério de aceite proíbe. A divergência já entra pela confiança (S-189); ver o cabeçalho.

    O desempate é `chave`, e não a ordem de chegada: duas execuções sobre a mesma página têm de
    produzir a mesma fila, senão "o terceiro item" não quer dizer nada entre uma sessão e outra.
    """
    return sorted(itens, key=lambda item: (-item.valor, item.chave))


@dataclass(frozen=True)
class Fila:
    """A fila inteira, com a régua que a ordenou e o estado de cada item.

    Congelada, como a `PaginaLida`: marcar um item devolve uma fila nova. É o que impede o defeito
    que a S-22 documenta na `ReviewQueue` mutável -- alguém ordena, alguém marca, e a posição que
    a tela mostrava deixou de ser a que o objeto tem.
    """

    itens: tuple[Item, ...] = ()
    versao: int = VERSAO

    @property
    def regua(self) -> Regua:
        """`divergencia` quando houve duas leituras; `confianca` quando só o glifo rodou.

        Basta **um** item com as duas leituras: o leitor de linha roda para a página toda ou para
        nenhuma dela, e um único item com `do_bloco` diz que ele rodou."""
        return "divergencia" if any(item.tem_duas_leituras for item in self.itens) else "confianca"

    @property
    def pendentes(self) -> tuple[Item, ...]:
        return tuple(item for item in self.itens if item.estado == "pendente")

    @property
    def divergentes(self) -> tuple[Item, ...]:
        return tuple(item for item in self.itens if item.divergem)

    def __len__(self) -> int:
        return len(self.itens)

    def __iter__(self) -> Iterator[Item]:
        return iter(self.itens)

    def distribuicao(self) -> dict[str, int]:
        """Quantos itens em cada faixa de cor. É a resposta ao `CORTE_DE_CONFERIR` de 0,75.

        `documento.CORTE_DE_CONFERIR` foi declarado com um comentário dizendo que quem decidiria
        se ele está no lugar certo seria esta S-212. Esta contagem é o que permite decidir: um
        corte que mande 90% da página para `conferir` não separa nada.
        """
        contagem = {"revisar": 0, "conferir": 0, "tranquilo": 0}
        for item in self.itens:
            contagem[item.faixa] = contagem.get(item.faixa, 0) + 1
        return contagem

    def marcar(self, chave: tuple[str, int, int, int, int], estado: Estado, corrigido: str = "") -> Fila:
        """Uma fila nova com esse item noutro estado. Chave desconhecida devolve a mesma fila.

        **A ordem não é refeita.** Marcar um item revisado não pode mexer na posição dos outros:
        quem está revisando conta na tela, e uma fila que se reordena a cada correção faz a pessoa
        perder o lugar -- que é a queixa que a S-22 registra sobre listas que se remexem.
        """
        achou = False
        novos: list[Item] = []
        for item in self.itens:
            if not achou and item.chave == chave:
                novos.append(replace(item, estado=estado, corrigido=corrigido))
                achou = True
            else:
                novos.append(item)
        if not achou:
            logger.debug("marcar: item %r não está na fila", chave)
            return self
        return replace(self, itens=tuple(novos))

    def para_json(self) -> dict[str, Any]:
        return {
            "versao": self.versao,
            "regua": self.regua,
            "itens": [item.para_json() for item in self.itens],
        }

    @classmethod
    def de_json(cls, dados: Any) -> Fila:
        """Reabre a fila **sem reordenar**, e é o item.

        Reordenar aqui pareceria inofensivo e desfaria a metade do critério de aceite que fala do
        que já foi revisado: um item marcado tem `estado`, não posição, e se a leitura reordenasse
        pelo valor ele voltaria para perto do topo -- a fila reabriria diferente da que se fechou.
        """
        if not isinstance(dados, dict):
            raise FilaInvalida(f"fila: esperava objeto, veio {type(dados).__name__}")
        versao = int(dados.get("versao", 0))
        if versao > VERSAO:
            raise FilaInvalida(f"fila gravada na versão {versao}; esta build lê até a {VERSAO}")
        itens = dados.get("itens")
        if not isinstance(itens, list):
            raise FilaInvalida("fila: 'itens' não é uma lista")
        return cls(itens=tuple(Item.de_json(bruto) for bruto in itens), versao=max(1, versao))

    def salvar(self, caminho: Path | str = CAMINHO_PADRAO) -> Path:
        from ..atomic_io import atomic_write_text

        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(destino, json.dumps(self.para_json(), ensure_ascii=False, indent=2) + "\n")
        return destino

    @classmethod
    def abrir(cls, caminho: Path | str = CAMINHO_PADRAO) -> Fila:
        """A fila do disco, ou uma vazia quando o arquivo não existe.

        Arquivo ausente é caminho normal -- ninguém revisou nada ainda --, e arquivo **estragado**
        não é: ele levanta `FilaInvalida`, porque devolver uma fila vazia por cima de um arquivo
        ilegível apagaria em silêncio o trabalho de quem revisou uma tarde.
        """
        origem = Path(caminho)
        if not origem.exists():
            return cls()
        return cls.de_json(json.loads(origem.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------------------
# De onde os itens vêm
# --------------------------------------------------------------------------------------

SO_O_QUE_PEDE_OLHO = ("revisar", "conferir")
"""As faixas que entram na fila por omissão. `tranquilo` fica fora, e é o ponto da fila.

Pôr as ~2.000 leituras da página numa lista seria a página outra vez, com mais passos."""


def _entra_na_fila(item: Item, aceitas: frozenset[str]) -> bool:
    """A faixa pede olho, **ou** as duas leituras da S-189 discordaram.

    ## O `ou` é o item, e a primeira versão não o tinha

    Sem ele, um box em que o glifo leu `c`, o leitor de linha leu `e` e a confiança combinada
    ficou em 0,90 **não entrava na fila**: a faixa dele é `tranquilo`. Mas a S-189 já tinha
    aplicado o `min` -- então 0,90 divergente quer dizer que as *duas* leituras estavam confiantes
    e ainda assim discordaram, que é a informação mais forte que esta página produz. Descartá-la
    por causa de um corte de cor seria jogar fora justamente o que o item existe para achar.

    **E isto não reabre o defeito do box verde no topo.** Quem admite não é quem ordena: a
    ordenação continua sendo só `1 - confiança`, então o divergente de 0,90 entra no **fim** da
    fila, atrás de todo box vermelho. O critério de aceite proíbe verde no topo, e não verde na
    fila -- um item presente porque duas leituras discordaram, no lugar em que a confiança dele o
    põe, é o contrário de uma fila que mente.
    """
    return item.faixa in aceitas or item.divergem


def de_pagina(
    pagina: Any,
    *,
    faixas: Sequence[str] = SO_O_QUE_PEDE_OLHO,
) -> list[Item]:
    """Uma `PaginaLida` como itens de fila, **uma linha por item**, já ordenados.

    ## Por que linha, e não caractere, neste caminho

    O item se chama "fila de revisão de caractere", e a granularidade de caractere existe -- é
    `de_lidos`. O que não existe é ela **no disco**: a `PaginaLida` guarda `LinhaLida`, e os boxes
    de caractere são consumidos dentro de `linhas_do_glifo` e descartados. Guardá-los custaria
    ~2.000 registros por página, e a S-215 acabou de pôr preço em tudo que se acrescenta ao
    caminho de página.

    Então há dois caminhos honestos em vez de um mentiroso: quem tem os boxes na mão (o leitor,
    durante a leitura) chama `de_lidos`; quem tem só o arquivo chama este, e recebe a linha. As
    duas ordenam pela mesma régua, e o `box=-1` diz qual é qual.

    `faixas` filtra pelo que pede olho. Passar `documento.FAIXAS` traz a página inteira.
    """
    aceitas = frozenset(faixas)
    achados: list[Item] = []
    for coluna in getattr(pagina, "colunas", ()):
        for bloco in getattr(coluna, "blocos", ()):
            for numero, linha in enumerate(getattr(bloco, "linhas", ())):
                item = Item(
                    documento=str(getattr(pagina, "documento", "")),
                    pagina=int(getattr(pagina, "pagina", 0)),
                    coluna=int(getattr(coluna, "indice", 0)),
                    linha=numero,
                    texto=linha.texto,
                    confianca=float(linha.confianca),
                    bbox=tuple(float(v) for v in linha.bbox),  # type: ignore[arg-type]
                    procedencia=str(linha.procedencia),
                )
                if _entra_na_fila(item, aceitas):
                    achados.append(item)
    return ordenar(achados)


def de_lidos(
    lidos: Sequence[Any],
    *,
    documento: str = "",
    pagina: int = 0,
    coluna: int = 0,
    linha: int = 0,
    caixas: Sequence[Any] = (),
    margens: Sequence[float] = (),
    faixas: Sequence[str] = SO_O_QUE_PEDE_OLHO,
) -> list[Item]:
    """Os `leitura_de_linha.Lido` de uma linha como itens de fila, um por box.

    É o caminho de granularidade de caractere, e o único em que `divergem` pode ser verdadeiro:
    `Lido` carrega as duas leituras da S-189 lado a lado. Quando o leitor de linha não rodou,
    `do_bloco` vem vazio e a régua da fila cai para a confiança -- ver o cabeçalho.

    `caixas` e `margens`, quando vêm, entram como bbox e como `Item.margem`. As duas são opcionais
    porque nenhuma é necessária para ordenar: a margem **não** é lida por `ordenar`, e a bbox só
    serve para a tela apontar onde olhar.
    """
    aceitas = frozenset(faixas)
    achados: list[Item] = []
    for indice, lido in enumerate(lidos):
        caixa = caixas[indice] if indice < len(caixas) else None
        item = Item(
            documento=documento,
            pagina=pagina,
            coluna=coluna,
            linha=linha,
            box=indice,
            texto=str(getattr(lido, "caractere", "")),
            confianca=float(getattr(lido, "confianca", 0.0)),
            bbox=_bbox_da_caixa(caixa),
            do_glifo=str(getattr(lido, "do_glifo", "")),
            do_bloco=str(getattr(lido, "do_bloco", "")),
            margem=float(margens[indice]) if indice < len(margens) else -1.0,
        )
        if _entra_na_fila(item, aceitas):
            achados.append(item)
    return ordenar(achados)


def _bbox_da_caixa(caixa: Any) -> tuple[float, float, float, float]:
    """`boxes.Caixa` -> os quatro números, e `(0,0,0,0)` quando não veio caixa nenhuma.

    **A `Caixa` nomeia os cantos `x1,y1,x2,y2`, e não `x0,y0,x1,y1`.** Escrito errado, este
    conversor devolveria `(x0=0, y0=0, x1, y1)` sem levantar nada -- `getattr` com padrão engole
    o nome trocado --, e a tela apontaria para o canto da página em vez do glifo."""
    if caixa is None:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        float(getattr(caixa, "x1", 0.0)),
        float(getattr(caixa, "y1", 0.0)),
        float(getattr(caixa, "x2", 0.0)),
        float(getattr(caixa, "y2", 0.0)),
    )
