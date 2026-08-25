"""O que o editor de texto mostra, decidido **sem** `import tkinter` (S-211).

**A regra que organiza este arquivo é a da Fase 6: o que dá para testar não mora na janela.** O
que a aba de texto faz é percorrer uma `PaginaLida` e desenhar; o que ela *decide* -- onde o
diagrama entra no fluxo, qual trecho merece destaque, o que vai para o arquivo quando alguém
salva -- é isto aqui, e é afirmável num teste que nunca abre uma janela.

## Por que o destaque é por faixa, e não por número

A confiança de um bloco é um `float`, e pintar um gradiente contínuo com ele daria uma página
onde tudo tem uma cor levemente diferente de tudo -- que é o mesmo que nada ter cor. As faixas
são três, e o corte de cada uma tem dono:

    revisar    abaixo de `ocr.MIN_CONFIDENCE`   o motor estava adivinhando (S-42)
    conferir   abaixo de `CORTE_DE_CONFERIR`    leitura boa, mas não é registro
    tranquilo  o resto, e a camada de texto

**O corte de baixo é emprestado de propósito.** `MIN_CONFIDENCE = 0.30` é o número que a S-42
mediu para decidir que uma legenda é adivinhada, e ter aqui um segundo corte para a mesma
pergunta faria a aba de texto discordar do resto do programa sobre o que é palpite.

## O diagrama é conteúdo, e a marca é o que o torna editável

`[Diagrama N]` sai de `BlocoDeDiagrama.texto`, e o editor a substitui pela miniatura na tela. Ela
não é decoração: é o que permite mover o diagrama de lugar no texto, e é o que volta ao arquivo
quando alguém exporta. Um diagrama desenhado sem marca correspondente seria invisível para o
texto -- e a primeira edição o perderia.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from .pagina import Bloco, BlocoDeDiagrama, PaginaLida

REVISAR = "revisar"
CONFERIR = "conferir"
TRANQUILO = "tranquilo"
FAIXAS: tuple[str, ...] = (REVISAR, CONFERIR, TRANQUILO)

CORTE_DE_CONFERIR = 0.75
"""Acima disto a leitura não pede conferência. **Não é herdado e não é medido**, e o comentário é
a honestidade do número: ele separa "o modelo tinha certeza" de "o modelo escolheu", e o que
decide se ele está no lugar certo é a S-212, que ainda não existe. Enquanto isso ele é um corte
declarado num lugar só, que é melhor que três cortes espalhados pela janela."""


def corte_de_revisar() -> float:
    """O corte de baixo, emprestado da S-42. Função e não constante para não copiar o número."""
    from ..ocr import MIN_CONFIDENCE

    return float(MIN_CONFIDENCE)


def faixa_de_confianca(confianca: float, procedencia: str = "") -> str:
    """Em qual das três faixas este bloco cai. Ver o cabeçalho.

    **A camada de texto e a correção humana nunca pedem revisão**, mesmo que alguém tenha gravado
    uma confiança baixa nelas: não são leituras, são registro. Sem esta linha, um arquivo com
    `confianca: 0.0` numa linha da camada pintaria a página inteira de vermelho.
    """
    if procedencia in ("camada", "humano"):
        return TRANQUILO
    if confianca < corte_de_revisar():
        return REVISAR
    if confianca < CORTE_DE_CONFERIR:
        return CONFERIR
    return TRANQUILO


@dataclass(frozen=True)
class Segmento:
    """Um pedaço do que o editor desenha: um texto com faixa, ou um diagrama."""

    tipo: str
    """`texto`, `diagrama` ou `separador`."""

    texto: str
    faixa: str = TRANQUILO
    bloco: Bloco | None = None
    coluna: int = 0
    negrito: bool = False
    """O bloco está em negrito. **`None` do modelo vira `False` aqui, e é deliberado**: a tela
    desenha ou não desenha, não tem um terceiro estado -- e "não se sabe" se desenha como normal,
    que é o lado seguro. Quem precisa da diferença lê `PaginaLida`."""

    italico: bool = False
    """O bloco está em itálico. `None` vira `False` pela mesma razão do `negrito` acima (S-236)."""

    @property
    def e_diagrama(self) -> bool:
        return self.tipo == "diagrama"


SEPARADOR = Segmento(tipo="separador", texto="\n\n")
"""A linha em branco entre dois blocos.

É um segmento, e não uma quebra solta no laço de desenho, para que a contagem de segmentos do
teste bata com o que aparece na tela."""


def segmentos(pagina: PaginaLida) -> Iterator[Segmento]:
    """A página como uma sequência de pedaços a desenhar, na ordem de leitura.

    Um `SEPARADOR` entre blocos, e **nunca** antes do primeiro nem depois do último: um editor que
    abre com uma linha em branco no topo faz todo mundo apertar `Backspace` antes de começar.
    """
    primeiro = True
    for coluna in pagina.colunas:
        for bloco in coluna.blocos:
            texto = bloco.texto
            if not texto:
                continue
            if not primeiro:
                yield SEPARADOR
            primeiro = False
            yield Segmento(
                tipo="diagrama" if isinstance(bloco, BlocoDeDiagrama) else "texto",
                texto=texto,
                faixa=faixa_de_confianca(bloco.confianca, bloco.procedencia),
                bloco=bloco,
                coluna=coluna.indice,
                negrito=getattr(bloco, "negrito", None) is True,
                italico=getattr(bloco, "italico", None) is True,
            )


def texto_para_arquivo(pagina: PaginaLida, *, com_cabecalho: bool = True) -> str:
    """O que vai para o `.txt` quando alguém salva. Termina com uma quebra, como todo arquivo texto.

    `com_cabecalho` escreve uma linha dizendo de que página do que este texto veio. **Ela é
    comentário e não dado**, e por isso começa com `#`: quem colar o arquivo em outro lugar quer o
    texto, e quem voltar a ele em três meses quer saber de onde ele saiu.
    """
    corpo = pagina.texto(com_marcas=True)
    if not com_cabecalho:
        return corpo + "\n" if corpo else ""
    impresso = f", página impressa {pagina.numero_impresso}" if pagina.numero_impresso is not None else ""
    origem = pagina.documento or "documento não identificado"
    cabecalho = f"# {origem} — folha {pagina.pagina + 1}{impresso}\n\n"
    return cabecalho + corpo + "\n"


def contagem_por_faixa(pagina: PaginaLida) -> dict[str, int]:
    """Quantos blocos em cada faixa. É o que a linha de status da aba resume."""
    contagem = dict.fromkeys(FAIXAS, 0)
    for bloco in pagina.blocos:
        contagem[faixa_de_confianca(bloco.confianca, bloco.procedencia)] += 1
    return contagem


def estado_do_negrito(pagina: PaginaLida) -> str:
    """O que dizer sobre negrito nesta página, em uma frase curta.

    **Existe porque "nada em negrito" e "o livro não informa" pareciam a mesma coisa na tela**, e
    o segundo caso é a maioria: 28 dos 41 livros do acervo não trazem peso de fonte na camada. Sem
    esta frase, quem abre um deles conclui que a função está quebrada -- e foi exatamente o que
    aconteceu com o `A Matter of Endgame Technique`, cuja camada escreve o livro inteiro numa fonte
    só. Ver `text/negrito.py`.
    """
    pesos = [
        linha.negrito
        for bloco in pagina.blocos
        for linha in getattr(bloco, "linhas", ())
    ]
    if not pesos or all(p is None for p in pesos):
        return "negrito: o livro não informa"
    quantas = sum(1 for p in pesos if p)
    return f"{quantas} em negrito" if quantas else "nada em negrito"


def resumo(pagina: PaginaLida) -> str:
    """A linha de status: o que a página tem, e quanto dela pede olho.

    Fica aqui e não na janela porque é a frase que o teste consegue afirmar -- e porque ela muda
    junto com as faixas, que também são daqui.
    """
    contagem = contagem_por_faixa(pagina)
    procedencias = pagina.procedencias()
    partes = [f"{len(pagina.colunas)} coluna(s)", f"{len(pagina.blocos)} bloco(s)"]
    if pagina.diagramas:
        partes.append(f"{len(pagina.diagramas)} diagrama(s)")
    if procedencias:
        partes.append("de " + ", ".join(f"{v} {k}" for k, v in sorted(procedencias.items())))
    pedem_olho = contagem[REVISAR] + contagem[CONFERIR]
    if pedem_olho:
        partes.append(f"{pedem_olho} pedem conferência ({contagem[REVISAR]} adivinhados)")
    partes.append(estado_do_negrito(pagina))
    return " · ".join(partes)


def diagramas_visiveis(segs: Sequence[Segmento]) -> list[BlocoDeDiagrama]:
    """Os diagramas na ordem em que aparecem no texto -- a ordem em que o editor os desenha."""
    return [s.bloco for s in segs if s.e_diagrama and isinstance(s.bloco, BlocoDeDiagrama)]


__all__ = [
    "CONFERIR",
    "CORTE_DE_CONFERIR",
    "FAIXAS",
    "REVISAR",
    "SEPARADOR",
    "TRANQUILO",
    "Segmento",
    "contagem_por_faixa",
    "corte_de_revisar",
    "diagramas_visiveis",
    "estado_do_negrito",
    "faixa_de_confianca",
    "resumo",
    "segmentos",
    "texto_para_arquivo",
]
