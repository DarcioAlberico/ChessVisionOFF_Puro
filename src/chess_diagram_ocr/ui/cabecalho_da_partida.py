"""O cabeçalho da partida na sala: quais campos, como se lê, e o que a edição grava (S-530).

**O que havia, medido em 2026-09-04.** A sala tinha os headers e não os mostrava. `Estudo.de_posicao`
escreve `Event`, `Site`, `Result`, `Round`, `SourcePDF`, `Page`, `Diagram` e `Caption`; um estudo
aberto de um `.pgn` traz `White`, `Black`, `WhiteElo`, `BlackElo`, `Date` e `ECO` junto; a busca na
base (S-533) devolve partidas com os oito de `games_db._KEPT_HEADERS`. Nada disso chegava à tela:
`qt/painel_de_estudo.py` desenhava tabuleiro, lista de lances, comentário e FEN, e **nenhum dos
nove campos**. Quem abrisse Capablanca–Alekhine na sala via um tabuleiro sem nome, sem torneio e
sem resultado -- e, exportando, gravava de volta um PGN cujos headers ele nunca pôde conferir.

O ChessBase põe a linha acima do tabuleiro e abre "Game data" com duplo clique. É o que este
módulo declara, e é tudo o que ele faz: **quais** são os campos, **como** eles viram uma frase de
duas linhas, e **o que** uma edição escreve de volta.

**Três decisões, e as três são de dado e não de widget.**

1. **Os nove campos são os do ChessBase, e não os oito de `_KEPT_HEADERS`.** Faltam lá os dois
   `Elo`, porque aquela lista é a do que o **índice** guarda por partida, e Elo não é chave de
   busca ali. Na sala eles são metade da pergunta "que partida é esta?", e o PGN os carrega como
   qualquer outro header. `ECO` fica de fora do formulário na outra direção: ele é **deduzido** da
   posição (S-534) e já aparece na faixa sob o tabuleiro -- um campo editável ao lado de uma
   dedução automática é o par de valores que diverge.
2. **Vazio é o valor de fábrica do padrão, e não a ausência da chave.** O `chess.pgn` nasce com
   `Event: "?"`, `Date: "????.??.??"` e `Result: "*"`, e **apagar** uma das sete etiquetas
   obrigatórias tira a chave do jogo -- o PGN exportado sai sem ela, que é um PGN inválido. Então
   um campo esvaziado grava o vazio **daquele** campo (ver `valor_vazio`), e só os dois `Elo`, que
   não são obrigatórios, somem de verdade.
3. **A frase tem duas linhas, e a segunda é a secundária.** Jogadores e resultado numa; torneio,
   local, data e rodada na outra. É a hierarquia do ChessBase, e é o que faz a linha caber em
   494 px -- a largura da coluna do tabuleiro a 1400x950 -- sem elidir o nome de ninguém.

Nada de `PyQt6`: `qt/painel_de_estudo.py` desenha os dois rótulos e monta o diálogo; quem diz o que
eles escrevem é isto, e é afirmável sem abrir janela.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..estudo import EVENTO, LOCAL

__all__ = [
    "CAMPOS",
    "ICONE",
    "RESULTADOS",
    "SEPARADOR",
    "TITULO",
    "Campo",
    "campo",
    "data_legivel",
    "linhas",
    "mudancas",
    "valores_para_o_formulario",
]
"""**O que a API deste módulo é, e o que ficou de fora dela.** `DE_FABRICA`, `OBRIGATORIOS`,
`SEM_JOGADORES`, `TRAVESSAO`, `preenchido` e `valor_vazio` são lidos pelas quatro funções acima, no
próprio módulo, e nenhum tem cliente de fora -- exportá-los seria pôr no `__all__` nomes que só o
teste toca, que é o que a triagem da S-511 tirou de vinte módulos."""

TITULO = "Cabeçalho da partida"
"""O título do diálogo, e a dica do botão que o abre. Um texto só para os dois."""

ICONE = "editar_cabecalho"
"""O traço do botão que abre o diálogo, em `icones.ICONES_DA_SALA`.

Ele não entra por `ui/comandos.py`: editar o cabeçalho ainda **não é comando do catálogo** -- não
tem item de menu nem tecla --, e um traço com a chave de um comando inexistente é arte órfã. A
ponte com esta constante é cobrada em `tests/test_ui_barra_da_sala.py`, junto com a da barra."""

SEPARADOR = " · "
"""Entre os pedaços da segunda linha, e é o mesmo separador do rodapé da janela."""

TRAVESSAO = " — "
"""Entre os dois jogadores. Travessão e não hífen: é como o livro imprime o par."""

SEM_JOGADORES = "Jogadores não informados"
"""A primeira linha quando não há nome nenhum. **Diz o que falta, e não fica em branco**: uma
faixa vazia acima do tabuleiro é espaço que ninguém sabe que é editável."""


@dataclass(frozen=True)
class Campo:
    """Um campo do formulário: a chave do PGN, como ele se chama em português, e a forma dele."""

    chave: str
    """A etiqueta do PGN, em inglês -- é o formato do arquivo, e não texto de tela."""

    rotulo: str
    """Como o campo se chama para quem preenche."""

    escolhas: tuple[str, ...] = ()
    """Os valores possíveis, quando são poucos e fechados. Só o resultado tem."""

    estreito: bool = False
    """Cabe ao lado do campo anterior, na mesma linha do formulário. É o caso dos dois `Elo`."""

    dica: str = ""


RESULTADOS: tuple[str, ...] = ("*", "1-0", "0-1", "1/2-1/2")
"""Os quatro valores que a etiqueta `Result` aceita, com o "em andamento" primeiro.

Lista fechada e não campo livre: `1:0`, `1-0 ` e `1–0` (com travessão) são o que se digita sem
querer, e qualquer um deles faz o PGN ser recusado por quem o ler. `*` é o de fábrica, e é o certo
para um estudo que saiu de um diagrama -- a posição do livro quase nunca é o fim da partida."""

OBRIGATORIOS: frozenset[str] = frozenset(
    {"Event", "Site", "Date", "Round", "White", "Black", "Result"}
)
"""As sete etiquetas do *Seven Tag Roster*, que todo PGN tem de trazer.

**Apagar uma delas não é esvaziá-la.** `del jogo.headers["White"]` tira a chave do jogo, e o PGN
exportado sai sem ela -- inválido para qualquer leitor. Quem esvazia um destes campos grava o valor
de fábrica (ver `valor_vazio`); só o que está fora desta lista some de verdade."""

_VAZIOS_PROPRIOS: dict[str, str] = {"Date": "????.??.??", "Result": "*"}
"""Os dois obrigatórios cujo vazio não é `?`. É a tabela do `chess.pgn.Headers`."""

_PLACEHOLDER = "?"

DE_FABRICA: dict[str, str] = {"Event": EVENTO, "Site": LOCAL}
"""O que `Estudo.de_posicao` escreve nestes dois quando o estudo saiu de um **diagrama**.

**Eles contam como vazio na frase, e não no formulário.** `ChessVisionOFF Estudo · Local` é o
programa se apresentando, e não o torneio em que a partida foi jogada: mostrá-lo acima do
tabuleiro é escrever ruído no lugar onde se espera ler "Kemeri 1937". No diálogo os dois aparecem
como estão, porque ali a pergunta é outra -- o que **está** gravado no PGN.

Comparados por valor e não apagados: quem digitar um evento de verdade o vê na hora, e quem
exportar continua com o header que o resto do projeto escreve (`pdf_to_pgn.py:698-699`)."""

CAMPOS: tuple[Campo, ...] = (
    Campo("White", "Brancas"),
    Campo("WhiteElo", "Elo", estreito=True, dica="Fica fora do PGN quando vazio: Elo não é etiqueta obrigatória."),
    Campo("Black", "Pretas"),
    Campo("BlackElo", "Elo", estreito=True, dica="Fica fora do PGN quando vazio: Elo não é etiqueta obrigatória."),
    Campo("Event", "Evento"),
    Campo("Site", "Local"),
    Campo(
        "Date",
        "Data",
        dica="No formato do PGN: `1927.11.16`. Parte desconhecida vai como `??`, e a faixa\n"
        "sob o tabuleiro mostra o que der para ler dela.",
    ),
    Campo("Round", "Rodada"),
    Campo("Result", "Resultado", escolhas=RESULTADOS),
)
"""Os nove campos, na ordem do formulário: os dois pares de jogador e Elo, o torneio, e o fim.

É a ordem do "Game data" do ChessBase, e ela não é alfabética de propósito -- ela é a ordem em que
se copia a legenda de um livro: quem jogou contra quem, onde, quando, e como terminou."""

_POR_CHAVE: dict[str, Campo] = {campo.chave: campo for campo in CAMPOS}


def valor_vazio(chave: str) -> str:
    """O que gravar quando o campo fica em branco. `""` quer dizer "tire a etiqueta do jogo".

    Ver `OBRIGATORIOS`: as sete do *Seven Tag Roster* têm um vazio próprio e não podem sumir.
    """
    if chave not in OBRIGATORIOS:
        return ""
    return _VAZIOS_PROPRIOS.get(chave, _PLACEHOLDER)


def _sem_valor(chave: str, valor: str | None) -> bool:
    """Se aquilo é o vazio do **formato**: campo em branco, `?`, `????.??.??`, `*` ou `-`."""
    texto = str(valor or "").strip()
    return not texto or texto == valor_vazio(chave) or texto in {_PLACEHOLDER, "-"}


def preenchido(chave: str, valor: str | None) -> bool:
    """Se aquele valor diz alguma coisa **a quem lê a frase**.

    Além do vazio do formato, o que o próprio programa escreve não conta: ver `DE_FABRICA`.
    """
    return not _sem_valor(chave, valor) and str(valor or "").strip() != DE_FABRICA.get(chave)


def valores_para_o_formulario(headers: Mapping[str, str]) -> dict[str, str]:
    """O que cada campo mostra quando o diálogo abre: o valor gravado, ou vazio para o do formato.

    **O `?` não vai para o campo**, e é o item: um formulário que abre com sete interrogações
    obriga quem digita a apagar cada uma antes de escrever, e quem não apagar grava `?Capablanca`.

    **`DE_FABRICA` aparece aqui, ao contrário da frase**, e a diferença é a pergunta de cada tela:
    a faixa acima do tabuleiro responde "que partida é esta?", e `ChessVisionOFF Estudo` não é
    resposta; o formulário responde "o que está gravado no PGN?", e ali ele é. Esconder os dois
    também aqui faria "Gravar" sem tocar em nada **apagar** o header que o resto do projeto
    escreve -- `mudancas` veria `""` no lugar de `ChessVisionOFF Estudo` e gravaria `?`.
    """
    return {
        campo.chave: ("" if _sem_valor(campo.chave, headers.get(campo.chave)) else str(headers.get(campo.chave, "")).strip())
        for campo in CAMPOS
    }


def mudancas(antes: Mapping[str, str], depois: Mapping[str, str]) -> dict[str, str]:
    """O que a edição de fato mudou, já normalizado para gravar. Vazio quando nada mudou.

    **Devolver só o que mudou é o que mantém o `Ctrl+Z` honesto**: `_marcar_sujo` empilha o PGN
    inteiro a cada chamada, e abrir o diálogo e fechá-lo em "Gravar" sem tocar em nada criaria um
    passo de desfazer que não desfaz coisa alguma -- o defeito que a S-275 evitou na árvore.

    O valor devolvido já é o que vai para o header: o texto digitado, ou o vazio daquele campo.
    """
    resultado: dict[str, str] = {}
    for campo in CAMPOS:
        novo = str(depois.get(campo.chave, "")).strip() or valor_vazio(campo.chave)
        atual = str(antes.get(campo.chave, "")).strip()
        if novo != atual:
            resultado[campo.chave] = novo
    return resultado


def data_legivel(texto: str | None) -> str:
    """`1927.11.16` -> `16/11/1927`; `1927.11.??` -> `11/1927`; `1927.??.??` -> `1927`.

    **A data do PGN é parcial por padrão**, e a maior parte do acervo só tem o ano -- é o que os
    livros de torneio imprimem. Mostrar `1927.??.??` é mostrar a sintaxe do formato a quem quer
    ler a partida; mostrar `1927` é responder a pergunta. Texto que não é uma data do PGN volta
    como veio: um `Date` escrito à mão como "verão de 1927" é informação, e comê-la seria pior.
    """
    partes = str(texto or "").strip().split(".")
    if len(partes) != 3 or not partes[0].isdigit():
        return str(texto or "").strip() if preenchido("Date", texto) else ""
    ano, mes, dia = partes
    if dia.isdigit() and mes.isdigit():
        return f"{int(dia):02d}/{int(mes):02d}/{ano}"
    if mes.isdigit():
        return f"{int(mes):02d}/{ano}"
    return ano


def _jogador(headers: Mapping[str, str], nome: str, elo: str) -> str:
    quem = str(headers.get(nome, "")).strip() if preenchido(nome, headers.get(nome)) else ""
    pontos = str(headers.get(elo, "")).strip() if preenchido(elo, headers.get(elo)) else ""
    if quem and pontos:
        return f"{quem} ({pontos})"
    return quem or pontos


def linhas(headers: Mapping[str, str]) -> tuple[str, str]:
    """As duas linhas que a sala escreve acima do tabuleiro.

    A primeira é `Brancas (Elo) — Pretas (Elo)  1-0`, e ela nunca fica vazia: sem nome nenhum ela
    diz `SEM_JOGADORES`, porque uma faixa em branco acima do tabuleiro é espaço que ninguém sabe
    que é editável. A segunda junta torneio, local, data e rodada com `SEPARADOR`, e some inteira
    quando não há nenhum dos quatro -- ali o vazio não esconde nada, o botão já está ao lado.
    """
    brancas = _jogador(headers, "White", "WhiteElo")
    pretas = _jogador(headers, "Black", "BlackElo")
    par = TRAVESSAO.join(p for p in (brancas, pretas) if p) if (brancas or pretas) else SEM_JOGADORES
    resultado = str(headers.get("Result", "")).strip()
    primeira = f"{par}{SEPARADOR}{resultado}" if preenchido("Result", resultado) else par

    pedacos = [
        str(headers.get(chave, "")).strip()
        for chave in ("Event", "Site")
        if preenchido(chave, headers.get(chave))
    ]
    data = data_legivel(headers.get("Date"))
    if data:
        pedacos.append(data)
    rodada = _rodada(headers)
    if rodada:
        pedacos.append(rodada)
    return primeira, SEPARADOR.join(pedacos)


def _rodada(headers: Mapping[str, str]) -> str:
    """`rodada 12`, ou vazio quando o `Round` é a **coordenada do livro** e não uma rodada.

    `Estudo.de_posicao` escreve `Round = "{página}.{diagrama}"` -- é a convenção que
    `pdf_to_pgn.py:698-699` já usava, e ela é útil: o PGN exportado diz de onde o diagrama saiu.
    Acima do tabuleiro ela é ruído com cara de dado: `rodada 21.1` num livro de torneio parece a
    vigésima primeira rodada, e o livro tem catorze.

    A comparação é com os headers `Page` e `Diagram`, que o mesmo construtor escreve ao lado. Um
    `Round` de verdade que por acaso fosse igual à coordenada some da faixa, e é o preço -- ele
    continua no formulário e no PGN, e a alternativa seria a faixa mentir sempre.
    """
    valor = str(headers.get("Round", "")).strip()
    if not preenchido("Round", valor):
        return ""
    coordenada = f"{str(headers.get('Page', '')).strip()}.{str(headers.get('Diagram', '')).strip()}"
    return "" if valor == coordenada else f"rodada {valor}"


def campo(chave: str) -> Campo:
    """O registro daquele campo. Levanta para chave que o formulário não tem."""
    if chave not in _POR_CHAVE:
        raise KeyError(f"campo fora do cabeçalho: {chave!r}. Os válidos estão em CAMPOS.")
    return _POR_CHAVE[chave]
