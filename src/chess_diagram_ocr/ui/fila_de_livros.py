"""A fila de livros a varrer: estado por livro, transições legais e as frases (S-546).

**O que estava faltando.** `batch.py` varre uma biblioteca inteira desde a S-34, e a única porta
dela é `cvoff-batch` -- um comando de terminal. Quem tem centenas de PDFs e usa a janela só
consegue exportar **um** livro por vez (`qt/exportador.py`), escolhendo o destino num diálogo a
cada um. A varredura em lote existe; o que não existia era como pedi-la de dentro do programa.

**Por que a decisão mora aqui.** Três coisas da fila não são desenho:

1. **Que transições são legais.** Um livro vai de `pendente` a `lendo`, e de `lendo` a um dos três
   fins. Voltar de `pronto` a `lendo` é o defeito que duplica trabalho; sair de `pendente` direto
   para `pronto` é o relatório que mente. A tabela abaixo é a regra, e ela é afirmável sem janela.
2. **O que cada linha diz.** A frase de estado é o que o usuário lê ao lado do nome do livro, e é
   ela que carrega o resultado -- diagramas achados, exportados, ilegais, tempo. Um `QTableView`
   que montasse essa frase por conta própria a montaria diferente do rodapé.
3. **Quanto o conjunto andou.** A fração do conjunto é *livros terminados mais a fração do livro em
   curso*, e não "páginas feitas sobre páginas totais": o número de páginas de um livro só se sabe
   ao abri-lo, e uma barra que ficasse parada em zero até o primeiro `progress` chegar seria uma
   barra que mente justamente no começo, que é quando alguém olha para ela.

**O `pulado` é um estado, e não um detalhe do `batch`.** `BatchOptions.skip_existing` pula o livro
cujo PGN já está no disco -- é o que torna a varredura retomável sem estado próprio (S-34). Uma
fila que mostrasse "pronto" para ele estaria dizendo que ele foi lido agora; uma que o escondesse
faria a pessoa procurar na lista o livro que ela acabou de acrescentar.

Quem executa é `qt/fila_de_livros.py`: thread, tabela e botões. Aqui não há toolkit nenhum.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from .tabela import Coluna

__all__ = [
    "COLUNAS",
    "PENDENTE",
    "FilaDeLivros",
    "LivroNaFila",
    "estado_do_resultado",
    "frase_de_resumo",
    "linha_da_tabela",
]

PENDENTE = "pendente"
LENDO = "lendo"
PRONTO = "pronto"
FALHOU = "falhou"
CANCELADO = "cancelado"
PULADO = "pulado"

TRANSICOES: dict[str, frozenset[str]] = {
    PENDENTE: frozenset({LENDO, PULADO, CANCELADO}),
    LENDO: frozenset({PRONTO, FALHOU, CANCELADO, PULADO}),
    PRONTO: frozenset(),
    FALHOU: frozenset(),
    CANCELADO: frozenset(),
    PULADO: frozenset(),
}
"""De cada estado, para onde ele pode ir. Os quatro fins são finais, e é isso que a tabela diz.

`pendente -> cancelado` existe porque cancelar uma fila de cinquenta livros no terceiro deixa
quarenta e sete que nunca começaram: eles não são "pendentes" -- ninguém vai voltar para eles
sozinho --, e chamá-los assim faria a frase de resumo prometer um trabalho que não vai acontecer.

**`pulado` é alcançável dos dois lados, e isso não é folga.** É o `skip_existing` da S-34: o livro
cujo PGN já está no disco não é lido. Só que quem descobre isso é `_run_one`, **depois** de
`on_book_start` já ter avisado que a varredura chegou naquele livro -- então na fila da janela ele
passa por `lendo` por um instante. Recusar `lendo -> pulado` faria a transição levantar dentro de
um slot do Qt, que derruba o processo; e adiar o `comecar` até a primeira página chegar deixaria
sem sinal justamente o livro que não tem página nenhuma.
"""

_FINAIS = frozenset(estado for estado, seguintes in TRANSICOES.items() if not seguintes)

_ESTADO_DO_STATUS = {
    "ok": PRONTO,
    "pulado": PULADO,
    "falhou": FALHOU,
    "cancelado": CANCELADO,
}
"""`batch.BookResult.status -> estado da fila`. A tradução mora aqui, e não no painel, porque é
decisão: o `status` é o vocabulário do relatório em disco e o estado é o que a tela mostra."""

COLUNAS: tuple[Coluna, ...] = (
    Coluna("livro", "Livro", 320, elastica=True),
    Coluna("situacao", "Situação", 210),
    Coluna("diagramas", "Diagramas", 90, numerica=True),
    Coluna("exportados", "Exportados", 90, numerica=True),
    Coluna("ilegais", "Ilegais", 70, numerica=True),
    Coluna("tempo", "Tempo", 80, numerica=True),
)
"""As colunas da fila, nas mesmas `Coluna` das outras duas tabelas do programa (S-153).

O nome do livro é a elástica: é o único conteúdo sem tamanho previsível. As quatro contagens são
numéricas, o que as alinha à direita -- numa fila de cinquenta livros, achar onde a exportação
caiu é comparar por magnitude, e isso não se faz com números encostados à esquerda.
"""


def _segundos(valor: float) -> str:
    """`33 s`, `4,2 min`, `1,3 h` -- na unidade em que quem esperou pensa no número."""
    if valor < 90:
        return f"{valor:.0f} s"
    if valor < 5400:
        return f"{valor / 60:.1f} min".replace(".", ",")
    return f"{valor / 3600:.1f} h".replace(".", ",")


@dataclass(frozen=True)
class Totais:
    """O que a fila leu, somado. Ver `FilaDeLivros.totais` sobre por que não é um dicionário."""

    paginas: int = 0
    diagramas: int = 0
    exportados: int = 0
    ilegais: int = 0


@dataclass(frozen=True)
class LivroNaFila:
    """Um livro da fila e tudo o que a varredura já disse sobre ele.

    Imutável, e trocado por `replace`: a fila é lida da thread da interface enquanto a varredura
    escreve da thread de trabalho, e um registro que mudasse no lugar seria lido pela metade --
    metade do resultado novo com metade do velho, sem exceção nenhuma para acusar.
    """

    pdf: Path
    estado: str = PENDENTE
    paginas_totais: int = 0
    paginas_feitas: int = 0
    diagramas: int = 0
    exportados: int = 0
    ilegais: int = 0
    segundos: float = 0.0
    erro: str = ""

    @property
    def nome(self) -> str:
        return self.pdf.name

    @property
    def terminou(self) -> bool:
        return self.estado in _FINAIS

    @property
    def fracao(self) -> float:
        """Quanto deste livro já foi lido, de 0 a 1. Um livro terminado é 1, mesmo sem páginas.

        Sem páginas totais a resposta é 0: enquanto o livro não foi aberto ninguém sabe quantas
        páginas ele tem, e inventar meio livro seria a barra andar por adivinhação.
        """
        if self.terminou:
            return 1.0
        if self.paginas_totais <= 0:
            return 0.0
        return min(1.0, self.paginas_feitas / self.paginas_totais)


def frase_de_estado(livro: LivroNaFila) -> str:
    """O que a coluna Situação diz sobre este livro. Fora do `__all__`: quem a chama é
    `linha_da_tabela`, aqui do lado, que é a API que a tabela consome.

    **O resultado fica ao lado do nome, e não num relatório à parte** (S-546): o que interessa
    saber de um livro varrido é quantos diagramas ele tinha e quantos saíram, e uma fila que
    dissesse só "pronto" obrigaria a abrir o PGN para descobrir que ele saiu vazio -- que é
    exatamente o caso dos cinco livros do acervo que exportam zero.
    """
    if livro.estado == PENDENTE:
        return "na fila"
    if livro.estado == PULADO:
        return "já exportado antes; não foi lido de novo"
    if livro.estado == FALHOU:
        return f"falhou — {livro.erro}" if livro.erro else "falhou"
    if livro.estado == LENDO:
        if livro.paginas_totais <= 0:
            return "abrindo o livro…"
        return f"lendo a página {livro.paginas_feitas} de {livro.paginas_totais}"
    partes = [f"{livro.diagramas} diagrama(s)", f"{livro.exportados} exportado(s)"]
    if livro.ilegais:
        partes.append(f"{livro.ilegais} ilegal(is)")
    partes.append(_segundos(livro.segundos))
    corpo = ", ".join(partes)
    if livro.estado == CANCELADO:
        cabeca = "cancelado" if livro.paginas_feitas else "cancelado antes de começar"
        return f"{cabeca}: {corpo}" if livro.paginas_feitas else cabeca
    return corpo


def linha_da_tabela(livro: LivroNaFila) -> tuple[str, str, str, str, str, str]:
    """As seis células desta linha, na ordem de `COLUNAS`.

    As contagens saem em branco enquanto o livro não terminou: um `0` numa coluna de resultado é
    indistinguível de "leu e não achou nada", e a fila tem justamente livros em que zero é o
    resultado de verdade.
    """
    vazio = livro.estado in (PENDENTE, LENDO)
    return (
        livro.nome,
        frase_de_estado(livro),
        "" if vazio else str(livro.diagramas),
        "" if vazio else str(livro.exportados),
        "" if vazio else str(livro.ilegais),
        "" if vazio else _segundos(livro.segundos),
    )


def estado_do_resultado(status: str) -> str:
    """O estado da fila para um `batch.BookResult.status`.

    Um status que este módulo não conhece vira `falhou`, e não uma exceção: a fila roda numa
    thread, e uma exceção ali derrubaria a varredura inteira por causa de um rótulo novo no
    relatório. Falhar por excesso de zelo é pior que mostrar um livro como falhado.
    """
    return _ESTADO_DO_STATUS.get(status, FALHOU)


class FilaDeLivros:
    """Os livros a varrer, com o estado de cada um e as transições que a tabela acima permite.

    Sem thread, sem widget e sem `batch`: quem roda a varredura é `qt/fila_de_livros.py`, e o que
    ele faz aqui é anotar o que aconteceu. É essa separação que deixa o cancelamento, o resumo e
    as frases serem afirmados sem abrir janela nenhuma.
    """

    def __init__(self, pdfs: Iterable[Path] = ()) -> None:
        self._livros: list[LivroNaFila] = []
        self.acrescentar(pdfs)

    def __len__(self) -> int:
        return len(self._livros)

    def __iter__(self) -> Iterator[LivroNaFila]:
        return iter(self._livros)

    def __getitem__(self, indice: int) -> LivroNaFila:
        return self._livros[indice]

    @property
    def livros(self) -> tuple[LivroNaFila, ...]:
        return tuple(self._livros)

    @property
    def pendentes(self) -> tuple[LivroNaFila, ...]:
        return tuple(livro for livro in self._livros if livro.estado == PENDENTE)

    @property
    def em_curso(self) -> int | None:
        """O índice do livro sendo lido, ou `None`. Nunca há dois: a varredura é sequencial."""
        for indice, livro in enumerate(self._livros):
            if livro.estado == LENDO:
                return indice
        return None

    def acrescentar(self, pdfs: Iterable[Path]) -> list[Path]:
        """Põe os PDFs no fim da fila e devolve os que **entraram**.

        O mesmo arquivo duas vezes é recusado em silêncio: ele seria lido duas vezes e escreveria
        no mesmo PGN, e o segundo passaria a ser um "pulado" que ninguém pediu. Quem quer reler
        um livro tira o PGN do caminho, que é a mesma regra do `--no-skip-existing`.
        """
        conhecidos = {livro.pdf for livro in self._livros}
        entraram: list[Path] = []
        for pdf in pdfs:
            caminho = Path(pdf)
            if caminho in conhecidos:
                continue
            conhecidos.add(caminho)
            self._livros.append(LivroNaFila(pdf=caminho))
            entraram.append(caminho)
        return entraram

    # ----------------------------------------------------------------------- as transições

    def _mudar(self, indice: int, estado: str, **campos: object) -> LivroNaFila:
        atual = self._livros[indice]
        if estado != atual.estado and estado not in TRANSICOES[atual.estado]:
            raise ValueError(
                f"{atual.nome}: de {atual.estado!r} não se vai para {estado!r}. "
                f"De {atual.estado!r} só se vai para {sorted(TRANSICOES[atual.estado]) or ['lugar nenhum']}."
            )
        novo = replace(atual, estado=estado, **campos)  # type: ignore[arg-type]
        self._livros[indice] = novo
        return novo

    def comecar(self, indice: int) -> LivroNaFila:
        """Este livro passou a ser lido."""
        return self._mudar(indice, LENDO)

    def avancar(self, indice: int, pagina: int, total: int) -> LivroNaFila:
        """O `progress_callback` da varredura: `pagina` é 1-based e `total` é o do livro.

        Não muda de estado -- é a única operação da fila que não é transição --, e por isso ela
        aceita o livro que já está em `lendo` e recusa qualquer outro: um avanço num livro
        terminado é um aviso atrasado de uma thread anterior, e aplicá-lo faria a linha voltar a
        andar depois de já ter dito o resultado.
        """
        atual = self._livros[indice]
        if atual.estado != LENDO:
            return atual
        novo = replace(atual, paginas_feitas=max(0, pagina), paginas_totais=max(0, total))
        self._livros[indice] = novo
        return novo

    def concluir(
        self,
        indice: int,
        estado: str,
        *,
        paginas: int = 0,
        diagramas: int = 0,
        exportados: int = 0,
        ilegais: int = 0,
        segundos: float = 0.0,
        erro: str = "",
    ) -> LivroNaFila:
        """O fim deste livro, com o resultado que vai ao lado do nome."""
        if estado not in _FINAIS:
            raise ValueError(f"{estado!r} não é um fim; os fins são {sorted(_FINAIS)}.")
        return self._mudar(
            indice,
            estado,
            paginas_totais=max(paginas, self._livros[indice].paginas_totais),
            paginas_feitas=paginas or self._livros[indice].paginas_feitas,
            diagramas=diagramas,
            exportados=exportados,
            ilegais=ilegais,
            segundos=segundos,
            erro=erro,
        )

    def cancelar_restantes(self) -> int:
        """Marca como cancelado todo livro que nunca vai começar. Devolve quantos foram.

        O livro **em curso** não é tocado: quem o termina é a thread, que responde ao pedido de
        cancelamento entre páginas e devolve o parcial que já saiu (S-24). Marcá-lo aqui apagaria
        da tela o resultado que ele ainda vai entregar.
        """
        quantos = 0
        for indice, livro in enumerate(self._livros):
            if livro.estado == PENDENTE:
                self._mudar(indice, CANCELADO)
                quantos += 1
        return quantos

    # -------------------------------------------------------------------------- o conjunto

    @property
    def fracao(self) -> float:
        """Quanto do conjunto já andou, de 0 a 1: livros terminados mais o pedaço do atual.

        Contar páginas do conjunto exigiria abrir os cinquenta PDFs antes de começar -- e o
        `page_count` de um PDF grande custa segundos (S-61). Livro é a unidade que já se conhece
        no instante em que a fila é montada.
        """
        if not self._livros:
            return 0.0
        return sum(livro.fracao for livro in self._livros) / len(self._livros)

    def contagem(self) -> dict[str, int]:
        """Quantos livros em cada estado. Estado sem nenhum livro **aparece com zero**.

        Uma contagem que omitisse os zeros faria a frase de resumo ter de perguntar duas vezes, e
        é o tipo de ausência que vira `KeyError` no dia em que alguém somar dois estados.
        """
        contagem = dict.fromkeys(TRANSICOES, 0)
        for livro in self._livros:
            contagem[livro.estado] += 1
        return contagem

    def totais(self) -> Totais:
        """O que a fila inteira leu, somado.

        Um `dataclass` e não um dicionário: as chaves seriam literais de string num módulo de
        `ui/`, e `tests/test_strings.py` varre literais de `ui/` procurando palavra em pt-BR sem
        acento -- `"paginas"` é exatamente isso. Escrever `"páginas"` como chave acentuaria um
        identificador para satisfazer uma varredura sobre **texto de tela**, que é o oposto do
        que ela existe para proteger.
        """
        return Totais(
            paginas=sum(livro.paginas_feitas for livro in self._livros),
            diagramas=sum(livro.diagramas for livro in self._livros),
            exportados=sum(livro.exportados for livro in self._livros),
            ilegais=sum(livro.ilegais for livro in self._livros),
        )

    @property
    def segundos(self) -> float:
        return sum(livro.segundos for livro in self._livros)

    def falhados(self) -> tuple[LivroNaFila, ...]:
        return tuple(livro for livro in self._livros if livro.estado == FALHOU)


def frase_de_resumo(fila: FilaDeLivros) -> str:
    """O que o rodapé diz quando a fila acaba. As falhas aparecem **por nome**.

    "3 livros falharam" não permite agir; os nomes permitem -- é a mesma regra do
    `BatchReport.summary`, e ela vale mais na janela do que no terminal, porque ali a saída
    rolou para cima e aqui a fila continua na tela.
    """
    if not len(fila):
        return "A fila está vazia: acrescente livros para varrer."

    contagem = fila.contagem()
    totais = fila.totais()
    partes = [f"{contagem[PRONTO]} livro(s) lido(s)"]
    if contagem[PULADO]:
        partes.append(f"{contagem[PULADO]} já exportado(s) antes")
    if contagem[CANCELADO]:
        partes.append(f"{contagem[CANCELADO]} cancelado(s)")
    if contagem[FALHOU]:
        partes.append(f"{contagem[FALHOU]} com falha")
    pendentes = contagem[PENDENTE] + contagem[LENDO]
    if pendentes:
        partes.append(f"{pendentes} por fazer")

    linhas = [
        f"{', '.join(partes)} em {_segundos(fila.segundos)}.",
        f"{totais.paginas} página(s), {totais.diagramas} diagrama(s), "
        f"{totais.exportados} exportado(s), {totais.ilegais} ilegal(is).",
    ]
    linhas.extend(f"falhou: {livro.nome} — {livro.erro}" for livro in fila.falhados())
    return " ".join(linhas)
