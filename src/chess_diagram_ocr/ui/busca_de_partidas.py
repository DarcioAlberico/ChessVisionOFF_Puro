"""O que a busca de partidas pergunta à base, e como ela conta o que achou (S-533).

**A pergunta mudou de forma.** Até a S-532 a base respondia a uma pergunta só -- *que partidas
têm esta posição?* (S-73) e *que partidas são deste par de nomes?* (S-87) --, e as duas nascem de
um diagrama de livro. Quem estuda com a base aberta pergunta outra coisa: *as partidas de Carlsen
em 2019 com Elo acima de 2700 na Najdorf*. São seis campos, e o valor está na **combinação** deles:
cada um sozinho devolve dezenas de milhares de linhas.

**Este módulo é a pergunta; `games_index.buscar` é a resposta.** Aqui ficam o que se pode
perguntar (`Filtro`), o que é pergunta malfeita (`problemas`), as colunas da tabela (`COLUNAS`,
`linha`) e a frase que diz o que voltou (`resumo`). Nada aqui abre arquivo nem monta widget: é a
mesma fronteira de `ui/indice_da_base.py`, e pelo mesmo motivo -- a frase tem de sair igual no
diálogo e no rodapé, e a régua é afirmável sem janela.

**O filtro guarda o que a pessoa digitou, e não o que o índice consulta.** `Carlsen`, `carlsen` e
`Carlsen, Magnus` são a mesma busca, e quem os iguala é `games_db.surname`, do outro lado -- do
mesmo jeito que a base grava `Carlsen, Magnus` e o livro escreve `Carlsen`. Guardar aqui a forma
dobrada faria a frase de resumo dizer `carlsen` de volta a quem escreveu `Carlsen`.

**Uma busca sem filtro que estreite é recusada, e isso é medida e não zelo.** `ORDER BY date DESC
LIMIT 100` sobre dez milhões de linhas sem cláusula nenhuma é uma varredura da tabela inteira
seguida de uma ordenação de dez milhões de linhas -- dezenas de segundos, com a resposta sendo "as
cem mais recentes da base", que ninguém foi ali procurar. Jogador, evento, ECO, ano e Elo têm
árvore no índice (`games_index._INDICES_DE_BUSCA`); resultado e posição **não**, e por isso eles
refinam mas não escolhem. Ver `problemas`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..eco import codigo_do_header
from .tabela import Coluna

__all__ = [
    "COLUNAS",
    "EM_BUSCA",
    "RESULTADOS",
    "Filtro",
    "de_campos",
    "linha",
    "problemas",
    "resumo",
]

ANO_MINIMO = 1475
"""O ano da primeira partida registrada com as regras modernas (Valência, 1475).

Não é erudição: é o piso que separa "o ano está errado" de "o ano é antigo". Um `19` digitado no
lugar de `1990` passa por qualquer piso menor e devolve a base inteira desde sempre."""

ANO_MAXIMO = 2100
"""E o teto, pelo mesmo motivo: `20190` é um `2019` com um dedo a mais, e sem teto ele vira um
filtro que nunca casa -- e "nenhuma partida" é a resposta que **não** diz que houve erro de
digitação."""

ELO_MAXIMO = 4000
"""Acima disso não é rating: o maior Elo já publicado é 2882. O teto existe para pegar o `27000`,
que num campo de Elo mínimo devolve zero partidas em silêncio."""

NAO_E_NUMERO = -1
"""O que `de_campos` põe num campo numérico que **foi preenchido e não é número**.

Zero já quer dizer "em branco", e as duas coisas não são a mesma: um campo vazio é um filtro que
não existe, e `dois mil` digitado no ano é um filtro que a pessoa quis e errou. Sem o segundo
valor, `int("dois mil")` levantaria dentro do diálogo -- ou, pior, seria engolido e a busca sairia
sem o filtro que se pediu."""

EM_BUSCA = "Procurando na base…"
"""O que a tabela diz enquanto a thread trabalha. A busca vai para uma `Tarefa` porque uma consulta
com `ORDER BY` sobre a gigabase pode custar centenas de milissegundos, e a janela não pode parar."""

SEM_ACHADO = "Nenhuma partida"
"""O começo da frase quando o filtro não casa nada. É frase e não tabela vazia porque uma tabela
vazia não diz **de que pergunta** ela está vazia -- ver `resumo`."""

RESULTADOS: tuple[tuple[str, str], ...] = (
    ("", "Qualquer"),
    ("1-0", "Vitória das brancas (1-0)"),
    ("0-1", "Vitória das pretas (0-1)"),
    ("1/2-1/2", "Empate (1/2-1/2)"),
    ("*", "Sem resultado (*)"),
)
"""`valor gravado no PGN -> como a lista o escreve`.

O valor é o do header `[Result]`, letra por letra, porque é ele que a coluna `result` do índice
guarda; o rótulo traz o valor entre parênteses porque é assim que ele aparece na coluna da tabela,
e quem procurou `1-0` na lista precisa reconhecê-lo lá."""

COLUNAS: tuple[Coluna, ...] = (
    Coluna("brancas", "Brancas", 150),
    Coluna("elo_brancas", "Elo", 55, numerica=True),
    Coluna("pretas", "Pretas", 150),
    Coluna("elo_pretas", "Elo", 55, numerica=True),
    Coluna("resultado", "Resultado", 80),
    Coluna("evento", "Evento", 200, elastica=True),
    Coluna("data", "Data", 92),
    Coluna("eco", "ECO", 55),
)
"""As oito colunas da lista, na ordem da pergunta: **quem contra quem** primeiro, porque é o que
se lê para reconhecer a partida; depois onde e quando; o ECO por último, que é a etiqueta dela.

Os dois Elos ficam **colados no jogador de cada um** e não numa coluna só no fim: `2882` sozinho
não diz de quem é, e a comparação que interessa -- quem era o mais forte dos dois -- é entre
vizinhos. Elo é número e alinha à direita, pelo mesmo motivo da S-153.

O evento é a elástica: é o único campo cujo comprimento não tem teto (`Tata Steel Masters 2019`
e `ch-RUS 1/2 final` na mesma coluna)."""

_SEPARADOR = " · "
"""Entre as partes do resumo. O mesmo de `eco.SEPARADOR` e o do título da janela: este projeto
separa fato de fato com ponto médio, e não com vírgula -- os fatos já têm vírgula dentro."""

_TRACO = "—"
"""O que uma célula sem valor mostra. **Travessão e não zero**, que é a decisão de
`ui/lista_de_partidas.linha`: `0` numa coluna de Elo é lido como um Elo, e a base não diz que
aquele jogador tem zero -- ela não diz nada."""

_FILTROS_COM_ARVORE = ("brancas", "pretas", "evento", "ano_de", "ano_ate", "elo_minimo", "eco_de", "eco_ate")
"""Os campos que têm índice no sqlite, e por isso escolhem em vez de varrer. Ver `Filtro.estreita`."""


class _Achado(Protocol):
    """O que `linha` precisa saber de uma partida achada -- os atributos de `games_index.Achado`.

    É `Protocol` e não o tipo de lá porque `games_index` importa **este** módulo (`Filtro` é o
    argumento de `buscar`), e nomear `Achado` aqui fecharia o ciclo. Estrutural resolve: o que a
    tabela lê são oito atributos, e quem os tiver serve.
    """

    @property
    def brancas(self) -> str: ...
    @property
    def elo_brancas(self) -> int: ...
    @property
    def pretas(self) -> str: ...
    @property
    def elo_pretas(self) -> int: ...
    @property
    def resultado(self) -> str: ...
    @property
    def evento(self) -> str: ...
    @property
    def data(self) -> str: ...
    @property
    def eco(self) -> str: ...


@dataclass(frozen=True)
class Filtro:
    """O que se pergunta à base, campo a campo. Vazio quer dizer "não filtra por isto".

    **Os nomes são o texto digitado**, e a comparação por sobrenome é de quem consulta
    (`games_index._clausulas` chama `games_db.surname`): `Carlsen`, `carlsen` e `Carlsen, Magnus`
    são a mesma busca, e o resumo devolve à pessoa o que ela escreveu.

    **Os números são `int` e não texto**, porque quem consulta os põe num `WHERE year >= ?`; a
    conversão -- e o que fazer com `dois mil` -- é de `de_campos`, que é a porta do formulário.
    """

    brancas: str = ""
    pretas: str = ""

    qualquer_cor: bool = True
    """Procurar cada nome dos **dois** lados. Verdadeiro de fábrica, e não é conveniência: o livro
    escreve `Coull - Stanciu` sem prometer quem tinha as brancas, e quem digita um nome só quer as
    partidas daquela pessoa -- não as partidas em que ela calhou de ter as brancas. Desmarcar é
    para a pergunta específica ("Carlsen **de brancas** contra a Najdorf")."""

    evento: str = ""
    """Trecho do nome do torneio, casado por pedaço (`LIKE`) e sem acento nem caixa. `Tata` acha
    `Tata Steel Masters 2019`: ninguém decora o nome inteiro de um torneio."""

    ano_de: int = 0
    ano_ate: int = 0
    elo_minimo: int = 0
    """O menor dos dois Elos da partida, e não a média: "Elo mínimo 2700" pergunta pelo **nível da
    partida**, e uma partida de 2882 contra 2100 não é uma partida de 2700."""

    resultado: str = ""
    """Um dos valores de `RESULTADOS`. Sozinho não basta para buscar -- ver `problemas`."""

    eco_de: str = ""
    eco_ate: str = ""
    """A faixa de códigos, inclusive nos dois extremos. Um só dos dois preenchido vira faixa de um
    código, e é a forma comum: `B90` é a Najdorf, e ninguém pede "de B90 a B90"."""

    posicao: str = ""
    """A colocação das 64 casas (o primeiro campo de uma FEN) que a partida tem de conter.

    Sozinha não basta: ela **não está no índice** -- guardá-la é a varredura de uma hora da S-92 --
    e é conferida relendo cada candidata que os outros filtros deixaram passar. Ver
    `games_index.TETO_DE_REPLAY`."""

    @property
    def estreita(self) -> bool:
        """Se ao menos um campo com árvore no índice está preenchido. Ver `problemas`."""
        return any(bool(str(getattr(self, campo)).strip()) for campo in _FILTROS_COM_ARVORE if getattr(self, campo))

    @property
    def vazio(self) -> bool:
        """Nenhum campo preenchido: o formulário como ele nasce."""
        return self == Filtro()


def _numero(texto: str, *, maximo: int) -> int:
    """`"2019"` -> 2019; `""` -> 0; `"dois mil"` -> `NAO_E_NUMERO`.

    O `maximo` corta antes da conversão para um campo colado por engano (uma partida inteira no
    campo do ano) não virar um inteiro de mil dígitos -- que é conversão instantânea em Python e
    parâmetro que o sqlite recusa lá adiante, longe daqui.
    """
    limpo = str(texto).strip()
    if not limpo:
        return 0
    if not limpo.isdigit() or len(limpo) > len(str(maximo)) + 1:
        return NAO_E_NUMERO
    return int(limpo)


def de_campos(
    *,
    brancas: str = "",
    pretas: str = "",
    qualquer_cor: bool = True,
    evento: str = "",
    ano_de: str = "",
    ano_ate: str = "",
    elo_minimo: str = "",
    resultado: str = "",
    eco_de: str = "",
    eco_ate: str = "",
    posicao: str = "",
) -> Filtro:
    """O `Filtro` a partir do que os campos do formulário têm escrito -- tudo texto.

    **Não levanta e não corrige**: um número malfeito vira `NAO_E_NUMERO` e um código ECO
    malfeito passa como está, para `problemas` poder dizer *qual* campo está errado. Um `de_campos`
    que consertasse calado ("2O19" vira 2019?) faria a busca responder outra pergunta.

    Os textos são aparados porque espaço à direita não é filtro -- é o que sobra de um `Ctrl+V`.
    """
    return Filtro(
        brancas=brancas.strip(),
        pretas=pretas.strip(),
        qualquer_cor=qualquer_cor,
        evento=evento.strip(),
        ano_de=_numero(ano_de, maximo=ANO_MAXIMO),
        ano_ate=_numero(ano_ate, maximo=ANO_MAXIMO),
        elo_minimo=_numero(elo_minimo, maximo=ELO_MAXIMO),
        resultado=resultado.strip(),
        eco_de=eco_de.strip(),
        eco_ate=eco_ate.strip(),
        posicao=posicao.strip(),
    )


def problemas(filtro: Filtro) -> tuple[str, ...]:
    """O que impede esta busca de sair, uma frase por problema. Vazio quer dizer "pode buscar".

    **Todas de uma vez, e não a primeira.** Um formulário de dez campos corrigido um erro por vez
    é dez viagens; a lista inteira cabe numa linha de aviso e a pessoa conserta tudo antes de
    clicar de novo.

    **A primeira delas não é sobre um campo: é sobre a busca.** Sem nenhum filtro com árvore no
    índice, a consulta varre a tabela inteira e ordena dez milhões de linhas -- e o resultado é
    "as cem partidas mais recentes da base", que não é resposta a pergunta nenhuma. Resultado e
    posição refinam o que os outros escolheram; escolher é dos outros.
    """
    achados: list[str] = []
    if not filtro.estreita:
        achados.append(
            "Preencha ao menos um filtro que estreite a busca: jogador, evento, ano, Elo mínimo ou ECO. "
            "O resultado e a posição só refinam o que os outros escolheram."
        )
    for valor, nome in ((filtro.ano_de, "ano inicial"), (filtro.ano_ate, "ano final")):
        if valor == NAO_E_NUMERO:
            achados.append(f"O {nome} precisa ser um ano de quatro dígitos.")
        elif valor and not ANO_MINIMO <= valor <= ANO_MAXIMO:
            achados.append(f"O {nome} está fora da faixa {ANO_MINIMO}–{ANO_MAXIMO}.")
    if filtro.ano_de > 0 and filtro.ano_ate > 0 and filtro.ano_de > filtro.ano_ate:
        achados.append(f"O ano inicial ({filtro.ano_de}) é depois do final ({filtro.ano_ate}).")
    if filtro.elo_minimo == NAO_E_NUMERO:
        achados.append("O Elo mínimo precisa ser um número.")
    elif filtro.elo_minimo > ELO_MAXIMO:
        achados.append(f"O Elo mínimo passa de {ELO_MAXIMO}, que é acima de qualquer rating publicado.")
    if filtro.resultado and filtro.resultado not in {valor for valor, _ in RESULTADOS}:
        achados.append(f"{filtro.resultado!r} não é um resultado de PGN. Os valores são 1-0, 0-1, 1/2-1/2 e *.")
    de, ate = codigo_do_header(filtro.eco_de), codigo_do_header(filtro.eco_ate)
    for escrito, achado, nome in ((filtro.eco_de, de, "inicial"), (filtro.eco_ate, ate, "final")):
        if escrito and not achado:
            achados.append(f"{escrito!r} não é um código ECO {nome}. Eles vão de A00 a E99.")
    if de and ate and de > ate:
        achados.append(f"O código ECO inicial ({de}) vem depois do final ({ate}).")
    return tuple(achados)


def linha(achado: _Achado) -> tuple[str, ...]:
    """A partida achada como linha da tabela, uma célula por coluna de `COLUNAS`.

    Célula sem valor sai com travessão: a base tem partidas sem Elo, sem data e sem ECO, e um `0`
    ou um `""` no lugar seriam lidos como "Elo zero" e "sem evento" -- afirmações que ninguém fez.
    """
    return (
        achado.brancas or _TRACO,
        str(achado.elo_brancas) if achado.elo_brancas else _TRACO,
        achado.pretas or _TRACO,
        str(achado.elo_pretas) if achado.elo_pretas else _TRACO,
        achado.resultado or _TRACO,
        achado.evento or _TRACO,
        achado.data or _TRACO,
        achado.eco or _TRACO,
    )


def _jogadores(filtro: Filtro) -> str:
    """`Carlsen × Anand`, `Carlsen`, ou com a cor dita quando ela foi exigida."""
    brancas, pretas = filtro.brancas.strip(), filtro.pretas.strip()
    if not brancas and not pretas:
        return ""
    if brancas and pretas:
        return f"{brancas} × {pretas}" if filtro.qualquer_cor else f"{brancas} de brancas × {pretas} de pretas"
    if filtro.qualquer_cor:
        return brancas or pretas
    return f"{brancas} de brancas" if brancas else f"{pretas} de pretas"


def _anos(filtro: Filtro) -> str:
    de, ate = max(filtro.ano_de, 0), max(filtro.ano_ate, 0)
    if de and ate:
        return str(de) if de == ate else f"{de}–{ate}"
    if de:
        return f"desde {de}"
    return f"até {ate}" if ate else ""


def _faixa_de_eco(filtro: Filtro) -> str:
    de, ate = codigo_do_header(filtro.eco_de), codigo_do_header(filtro.eco_ate)
    if de and ate:
        return de if de == ate else f"{de}–{ate}"
    return de or ate


def _contagem(total: int, *, teto: bool) -> str:
    if teto:
        return f"mais de {total:,} partidas".replace(",", ".")
    if total <= 0:
        return SEM_ACHADO
    return "1 partida" if total == 1 else f"{total:,} partidas".replace(",", ".")


def resumo(
    filtro: Filtro,
    total: int,
    *,
    teto: bool = False,
    mostrados: int = 0,
    desde: int = 0,
    examinadas: int = 0,
) -> str:
    """A linha sob a tabela: quantas há, e **de que pergunta** elas são.

    `1.234 partidas · Carlsen · 2015–2020 · B90`. A contagem sozinha não serve: com o formulário
    já apagado para a busca seguinte, "1.234" não diz de quê -- e "Nenhuma partida" sem os filtros
    ao lado parece defeito da base, quando quase sempre é um ano digitado errado.

    `teto` é a contagem que parou em `games_index.TETO_DE_CONTAGEM`: a frase diz *mais de*, porque
    é a informação inteira -- contar todas as partidas de `1.e4` custa segundos para dizer um
    número que ninguém lê até o fim.

    `mostrados`/`desde` são a página (`1–100 de 1.234 partidas`), e só aparecem quando a página não
    é a resposta toda. `examinadas` é o preço do filtro por posição: quantas candidatas foram
    lidas e reproduzidas para montar esta página.
    """
    contagem = _contagem(total, teto=teto)
    if mostrados and (desde or teto or mostrados < total):
        contagem = f"{desde + 1}–{desde + mostrados} de {contagem}"
    partes = [
        contagem,
        _jogadores(filtro),
        filtro.evento.strip(),
        _anos(filtro),
        f"Elo ≥ {filtro.elo_minimo}" if filtro.elo_minimo > 0 else "",
        filtro.resultado.strip(),
        _faixa_de_eco(filtro),
        "com a posição do tabuleiro" if filtro.posicao else "",
        f"{examinadas:,} candidatas lidas".replace(",", ".") if examinadas else "",
    ]
    return _SEPARADOR.join(parte for parte in partes if parte)
