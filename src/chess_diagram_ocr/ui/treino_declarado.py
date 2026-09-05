"""O que a tela de treino decide, sem abrir janela nenhuma (S-539/S-540/S-541).

Três coisas moram aqui, e nenhuma delas precisa de Qt:

1. **Em que balde cai o lance que a pessoa jogou** (`classificar_o_lance`). Igual ao do gabarito,
   igualmente bom, ou erro -- e a régua do "igualmente bom" é a perda da S-537, e não um número
   novo. Este é o item que o placar da S-541 conta.
2. **O andamento de um exercício** (`Tentativa`): qual meio-lance se espera agora, o que acontece
   quando ele vem errado, e quando a linha acabou. É uma máquina de estados de quatro linhas, e
   ela está aqui porque é ela que decide se o exercício conta como acerto -- não o widget.
3. **As frases**: a da agenda do dia, a do placar, a do gabarito com a procedência. Elas mudam
   junto com as decisões acima e são o que um teste consegue afirmar.

**Por que o balde do meio existe.** Sem ele, treinar sobre uma partida de torneio classifica como
erro toda transposição e todo lance de igual valor -- o placar mede a memória daquela partida em
vez do xadrez de quem treina. Com ele, `Bd3` no lugar de `Bc2` conta como acerto quando o motor diz
que os dois valem o mesmo, e a frase diz que o lance da partida foi o outro.

**A perda vem do motor, e sem motor o balde do meio não existe** -- e é honesto: sem quem avalie, a
única coisa que se pode afirmar é se o lance foi o do gabarito. `classificar_o_lance` chamada sem
perda devolve `CERTO` ou `ERRADO`, e a frase não promete comparação nenhuma.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..placar import CERTO, EQUIVALENTE, ERRADO, PlacarDoLivro
from . import analise_da_partida as regua
from . import formato

__all__ = [
    "DECORACAO",
    "Julgamento",
    "Tentativa",
    "classificar_o_lance",
    "frase_da_agenda",
    "frase_do_fim",
    "frase_do_gabarito",
    "frase_do_placar",
    "frase_do_resultado",
    "mesmo_lance",
    "rotulo_do_desfecho",
]

DECORACAO = "+#!?±∓⩲⩱"
"""O que um lance carrega **depois** dele e que não muda o lance: xeque, mate e o juízo do autor.

Não entram `x`, `=` nem a letra de desambiguação: `Nbd2` e `Nfd2` são dois cavalos diferentes, e
`exd5` não é `d5`. Ver `mesmo_lance`, que é o único lugar que apara por aqui."""


def mesmo_lance(jogado: str, esperado: str) -> bool:
    """Os dois textos são o **mesmo lance**? (S-541)

    **Comparar cadeia crua rejeita a resposta certa, e o caso é comum.** O gabarito de um exercício
    pode ter sido guardado como o livro o imprimiu -- `Ra8+` num lance que na verdade dá mate --,
    enquanto o que a tela tem em mãos é o SAN que o `chess` escreve a partir do tabuleiro, `Ra8#`.
    Com `str(jogado) == str(esperado)` a pessoa joga o lance do livro e o placar conta erro; o
    exercício volta amanhã como "não sabido", e a repetição espaçada passa a medir a grafia.

    O que se apara é só `DECORACAO`. A comparação continua **exata** no resto, e é por isso que ela
    não abre a porta que a S-15 fecha: um lance parecido continua sendo outro lance.
    """
    return str(jogado).strip().rstrip(DECORACAO) == str(esperado).strip().rstrip(DECORACAO)


_SIMBOLOS: dict[str, str] = {
    regua.IMPRECISAO: "?!",
    regua.ERRO: "?",
    regua.ERRO_GRAVE: "??",
}


@dataclass(frozen=True)
class Julgamento:
    """O que se decidiu do lance jogado: o balde, o símbolo e quanto ele custou."""

    resultado: str
    """Um de `placar.RESULTADOS`. É o que o placar conta."""

    juizo: str = ""
    """`imprecisao`, `erro` ou `erro_grave` -- os da S-537. Vazio quando não houve juízo a dar."""

    perda: int = 0
    """Centipeões perdidos contra o que o motor prefere. Zero também quando não se perguntou."""

    com_motor: bool = False
    """Houve avaliação? Sem ela, `resultado` só sabe distinguir o lance do gabarito dos outros."""

    @property
    def certo(self) -> bool:
        """O lance conta como acerto: o do gabarito ou um igualmente bom."""
        return self.resultado in (CERTO, EQUIVALENTE)

    @property
    def simbolo(self) -> str:
        return _SIMBOLOS.get(self.juizo, "")


def classificar_o_lance(
    jogado: str,
    esperado: str,
    *,
    antes: int | None = None,
    depois: int | None = None,
    brancas: bool = True,
) -> Julgamento:
    """Em que balde cai o lance jogado (S-541).

    **O lance do gabarito é `CERTO` mesmo quando o motor discorda dele**, e essa ordem é a decisão:
    quem treina o `1001 Sacrifices` está aprendendo a combinação de Reinfeld, e um Stockfish que
    prefere outra coisa não torna errado o lance que o livro pede. A discordância do motor com o
    **gabarito** é assunto da extração (`taticas.confirmar`), e não do lance de quem treina.

    **A régua é `analise_da_partida.julgar`, inteira, e não a tabela de cortes.** Ela recebe as duas
    avaliações -- antes e depois do lance -- e não um número de perda pronto, e é o que faz o treino
    herdar as duas regras que a S-537 mediu: o teto de dez peões e a **posição já decidida**. Um
    lance que cai de +18 para +9 não é erro nenhum, e um corte escrito aqui não saberia disso.

    É também o que mantém o treino e o relatório da partida dizendo a mesma coisa sobre o mesmo
    lance na mesma janela -- inclusive depois de a S-537 trocar a escala do juízo de centipeões
    para expectativa de vitória, o que já aconteceu uma vez.

    Sem as duas avaliações não há balde do meio: a única coisa afirmável é se o lance foi o do
    gabarito, e é o que a janela sem motor mostra.
    """
    if mesmo_lance(jogado, esperado):
        return Julgamento(resultado=CERTO, perda=0, com_motor=antes is not None)
    if antes is None or depois is None:
        return Julgamento(resultado=ERRADO, com_motor=False)
    perda, juizo = regua.julgar(int(antes), int(depois), brancas_jogaram=bool(brancas))
    if not juizo:
        return Julgamento(resultado=EQUIVALENTE, perda=perda, com_motor=True)
    return Julgamento(resultado=ERRADO, juizo=juizo, perda=perda, com_motor=True)


@dataclass
class Tentativa:
    """O andamento de **um** exercício: onde a linha está e quantas vezes se errou (S-539).

    **A árvore não muda, e é a regra da S-290 mantida.** O gabarito já está aqui; jogar sobre ele
    não cria variante, não grava nada e não desfaz nada. Errar continua sendo só errar.

    **Um erro não interrompe o exercício.** Quem erra tenta de novo, e é a segunda tentativa que faz
    o exercício valer `DIFICIL` em vez de `BOM` na agenda (`revisao_espacada.nota_do_treino`).
    Interromper na primeira faria a única resposta possível ser "ver a solução", e ver a solução é
    não saber a solução.
    """

    lances: tuple[str, ...] = field(default_factory=tuple)
    """A solução em SAN. Os de índice par são de quem resolve; os ímpares, a resposta."""

    ply: int = 0
    erros: int = 0
    revelou: bool = False

    @property
    def esperado(self) -> str:
        """O meio-lance que se espera agora. Vazio quando a linha acabou."""
        return self.lances[self.ply] if 0 <= self.ply < len(self.lances) else ""

    @property
    def terminou(self) -> bool:
        return self.ply >= len(self.lances)

    @property
    def tentativas(self) -> int:
        """Quantas vezes se respondeu nesta posição, contando a que acertou."""
        return self.erros + 1

    def acertou(self) -> str:
        """Avança um meio-lance e devolve a **resposta** que a máquina joga, se houver.

        A resposta do adversário é jogada sozinha porque ela é parte do gabarito e não do
        exercício: pedir que a pessoa jogue os dois lados transformaria a combinação numa digitação.
        """
        if self.terminou:
            return ""
        self.ply += 1
        resposta = self.lances[self.ply] if self.ply < len(self.lances) else ""
        if resposta:
            self.ply += 1
        return resposta

    def errou(self) -> None:
        self.erros += 1

    def revelar(self) -> tuple[str, ...]:
        """Mostra o resto da linha e marca o exercício como visto. Ver `nota_do_treino`."""
        self.revelou = True
        resto = self.lances[self.ply :]
        self.ply = len(self.lances)
        return resto


def frase_do_resultado(julgamento: Julgamento, jogado: str, esperado: str) -> str:
    """A frase que o rodapé do treino escreve depois de um lance (S-541).

    **Ela diz o que o lance custou quando há motor, e cala quando não há.** "Perdeu 1,40" numa
    janela sem motor seria um número inventado; "não é o lance da linha" continua sendo verdade nos
    dois casos.
    """
    if julgamento.resultado == CERTO:
        return f"{jogado} — certo."
    perda = regua.peoes(julgamento.perda)
    if julgamento.resultado == EQUIVALENTE:
        return f"{jogado} — vale o mesmo. A linha jogou {esperado} (perde {perda})."
    if not julgamento.com_motor:
        return f"{jogado} não é o lance da linha, que é {esperado}."
    rotulo = regua.rotulo_de_juizo(julgamento.juizo) or "erro"
    return f"{jogado}{julgamento.simbolo} — {rotulo}: perde {perda} contra {esperado}."


def frase_do_gabarito(lances: Any, procedencia: str = "", desfecho: str = "") -> str:
    """A solução escrita por extenso, com o que ela faz e a procedência atrás (S-539).

    A procedência não é enfeite: um exercício sem ela é uma posição que não se pode conferir no
    livro, e conferir no livro é o que se faz quando a solução não convence.

    **O desfecho aparece aqui e não antes**, e a diferença é o exercício: "dá mate" impresso ao
    lado do tabuleiro **antes** de a pessoa jogar é meia resposta -- e é justamente a metade que o
    livro esconde ao dizer só "as brancas jogam e ganham".
    """
    linha = " ".join(str(lance) for lance in (lances or ()))
    if not linha:
        return "Este exercício não tem solução gravada."
    frase = f"Solução: {linha}"
    rotulo = rotulo_do_desfecho(desfecho)
    if rotulo:
        frase += f" — {rotulo}"
    return f"{frase} ({procedencia})" if procedencia else frase


def frase_da_agenda(agenda: Any, *, volta_em: Any = None, colecao: int = 0) -> str:
    """`Hoje você tem 23 para revisar: 18 vencidos e 5 novos.` (S-540)

    **Os adiados aparecem, e é o número mais importante da frase.** Quem some por um mês volta com
    400 itens vencidos e vê uma fila de 60; sem a segunda frase, a conclusão é que o programa
    perdeu os outros 340. Dizer quantos ficaram para amanhã é o que transforma o teto de uma
    limitação numa decisão.

    **A fila vazia diz por que está vazia, e as duas razões são diferentes.** "Nada para revisar"
    servia tanto a quem não extraiu exercício nenhum quanto a quem já revisou tudo hoje -- e o que
    a segunda pessoa precisa saber é **quando** o material volta, não que ele sumiu. `volta_em` é a
    data do próximo vencimento (`revisao_espacada.proximo_vencimento`) e `colecao` é o tamanho da
    coleção; com os dois, a frase deixa de mandar extrair o que já está extraído.
    """
    quantos = getattr(agenda, "quantos", 0)
    if not quantos:
        return _fila_vazia(volta_em, colecao)
    vencidos = min(getattr(agenda, "vencidos", 0), quantos)
    novos = quantos - vencidos
    partes = []
    if vencidos:
        partes.append(f"{vencidos} vencido(s)")
    if novos:
        partes.append(f"{novos} novo(s)")
    frase = f"Hoje você tem {quantos} para revisar: {' e '.join(partes)}."
    adiados = getattr(agenda, "adiados", 0)
    if adiados:
        frase += f" Outros {adiados} ficam para amanhã."
    return frase


def _fila_vazia(volta_em: Any, colecao: int) -> str:
    if volta_em is None:
        return "Nada para revisar hoje. Volte amanhã, ou extraia as táticas de outro livro."
    quando = volta_em.strftime("%d/%m/%Y") if hasattr(volta_em, "strftime") else str(volta_em)
    frase = f"Nada vence hoje: o próximo volta em {quando}."
    if colecao:
        frase += f" A coleção tem {formato.inteiro(colecao)} exercício(s)."
    return frase


def frase_do_fim(exercicios: int, sessao: PlacarDoLivro) -> str:
    """O resumo do que se acabou de fazer, quando a fila do dia termina (S-540/S-541).

    **Uma sessão que acaba sem resumo acaba sem resultado.** A tela dizia "Fila de hoje concluída"
    ao lado de uma agenda que continuava anunciando os três exercícios de meia hora atrás, e o
    placar da sessão sumia junto com o último exercício -- trinta minutos sem nenhuma frase que
    diga como foram. É a mesma razão do placar por livro da S-541, uma escala abaixo.

    Sem lance nenhum a frase não inventa porcentagem: quem abriu e fechou a janela não teve sessão.
    """
    if not sessao.total:
        return f"Fila de hoje concluída: {exercicios} exercício(s), nenhum lance jogado."
    frase = (
        f"Fila de hoje concluída: {exercicios} exercício(s), "
        f"{sessao.bons} de {sessao.total} lance(s) certos "
        f"({formato.porcentagem(sessao.acerto, casas=0)})."
    )
    if sessao.perda:
        frase += f" Perdeu {regua.peoes(round(sessao.perda_media))} por lance, em média."
    return frase


def frase_do_placar(sessao: PlacarDoLivro, do_livro: PlacarDoLivro | None = None) -> str:
    """`sessão: 7 de 9 · Reinfeld 1001: 78% em 214 lances, perde 0,31 por lance` (S-541).

    Duas escalas na mesma linha porque elas respondem a perguntas diferentes -- ver o cabeçalho de
    `placar.py`. Sem lance nenhum na sessão, a frase é vazia: um placar `0 de 0` é ruído
    permanente, e é a mesma regra do `(0)` no rótulo de aba da S-162.

    **A perda média entra, e ela é a metade que faltava.** `PlacarDoLivro.perda_media` era
    calculada e nunca mostrada; sem ela, "78%" trata igual quem erra dois lances de 60 centipeões e
    quem larga a dama duas vezes. É a mesma distinção que a S-537 faz entre imprecisão e erro
    grave, aqui contada sobre a sessão inteira -- e ela só aparece quando houve motor, porque sem
    motor a perda é sempre zero e um `perde 0,00` fixo mentiria por omissão.
    """
    if not sessao.total:
        return ""
    partes = [f"sessão: {sessao.bons} de {sessao.total}"]
    if do_livro is not None and do_livro.total:
        from ..taticas import nome_curto

        porcento = formato.porcentagem(do_livro.acerto, casas=0)
        # **O nome curto, e o mesmo de `Procedencia.frase`**: o caminho inteiro de um livro do
        # acervo tem 80 caracteres, e escrito aqui ele empurra o número para fora da janela.
        linha = f"{nome_curto(do_livro.livro) or 'acervo'}: {porcento} em {do_livro.total} lance(s)"
        if do_livro.perda:
            linha += f", perde {regua.peoes(round(do_livro.perda_media))} por lance"
        partes.append(linha)
    return " · ".join(partes)


_DESFECHOS: dict[str, str] = {
    "mate": "dá mate",
    "ganha_material": "ganha material",
    "sem_ganho": "vantagem sem captura",
}


def rotulo_do_desfecho(desfecho: str) -> str:
    """Como o desfecho de `taticas.desfecho` se escreve na tela. Desconhecido devolve vazio.

    "Vantagem sem captura" e não "sem ganho": o campo se chama assim porque a conta é de material,
    e escrever "sem ganho" na tela diria à pessoa que a combinação não vale nada -- quando o que
    aconteceu é que o livro parou antes da captura.
    """
    return _DESFECHOS.get(str(desfecho), "")
