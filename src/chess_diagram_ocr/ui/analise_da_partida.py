"""A partida inteira analisada: quanto cada lance custou, e onde o gráfico o desenha (S-537).

**A pergunta que isto responde é a do dia seguinte ao torneio**: *em que lance eu perdi?* A sala
já sabia avaliar **uma** posição desde a S-33 e gravar o número no lance desde a S-285; o que não
existia era passar a partida inteira pelo motor e dizer, em uma tela, onde a avaliação virou.

**Três decisões moram aqui, e nenhuma delas precisa de motor nem de janela.**

1. **Quanto um lance custou.** A avaliação antes e a avaliação depois, as duas do ponto de vista de
   quem jogou, e a diferença. É aritmética, e é justamente por isso que ela tem de estar num lugar
   só: escrita duas vezes -- uma no relatório, outra na marca do lance -- as duas versões divergem
   no primeiro mate.
2. **Onde estão os cortes.** `?!`, `?` e `??` não são opinião: são 50, 100 e 300 centipeões de
   perda, que é a tabela clássica do Lichess (`lila`, `Advice.scala`) e a mesma que o Scid usa. O
   Lichess de hoje refinou para perda de **expectativa de vitória** -- 6, 10 e 20 pontos
   percentuais --, e o motivo do refinamento é o caso "já estava ganho": perder 300 cp partindo de
   +15 não é erro nenhum. Aqui esse caso é resolvido pelo **teto** (`TETO_DE_AVALIACAO`), que é o
   que o próprio Lichess faz antes de qualquer conta: acima de dez peões a diferença deixa de
   contar, porque acima de dez peões a partida acabou.
3. **Como o gráfico desenha.** A curva é a de `engine.fracao_de_vantagem` -- a mesma da barra
   lateral, e não uma segunda --, e o eixo do tempo é o **ply**, não o lance: um erro das pretas no
   lance 24 e um das brancas no 25 são dois pontos vizinhos, e agrupá-los por lance esconderia um
   dos dois.

**O símbolo vai para o PGN, e é isso que o torna útil.** O juízo não é uma cor na tela: é o NAG
`$2`/`$4`/`$6` no lance, que a lista já desenha (`ui/estudo_lista.py`), que o `Ctrl+Z` desfaz e que
sobrevive ao arquivo -- qualquer programa de xadrez lê `12. Bd3?? $4`. Uma marca só de tela seria a
análise que se perde ao fechar a sala.

Nada de `PyQt6`: quem desenha o gráfico é `qt/analise_da_partida.py`, e ele não decide nada.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..engine import fracao_de_vantagem

__all__ = [
    "ERRO",
    "ERRO_GRAVE",
    "IMPRECISAO",
    "NAG_DE_JUIZO",
    "PROFUNDIDADE_MAXIMA",
    "PROFUNDIDADE_MINIMA",
    "PROFUNDIDADE_PADRAO",
    "TETO_DE_AVALIACAO",
    "TETO_POR_LANCE_MS",
    "Avaliado",
    "avaliacao_em_centipeoes",
    "classificar",
    "frase_de_progresso",
    "frase_final",
    "indice_no_x",
    "julgar",
    "percurso",
    "pontos_do_grafico",
    "resumo",
    "y_do_meio",
]

PROFUNDIDADE_PADRAO = 16
"""Plies por lance, de fábrica. É o corte entre "responde algo" e "responde a verdade".

**Medido em 2026-09-04**, Stockfish dev-20230303, 1 thread, `Hash` 128 MB, sobre a Imortal
(45 plies, 46 posições, `scratchpad/medir_motor.py`):

| profundidade | a partida inteira | juízos que diferem da 16 |
|---|---|---|
| 12 | 1,6 s | 4 |
| 16 | 8,5 s | — |
| 20 | 42,1 s | 3 |

As três acharam **catorze** lances com símbolo -- a Imortal é uma partida de sacrifício, e um terço
dos lances dela passa do corte de imprecisão; numa partida de torneio o número é bem menor. O que
muda com a profundidade é *quais* catorze.

Dezesseis é onde a curva de custo vira: cinco vezes o tempo de 12 para trocar quatro juízos, e mais
cinco vezes o tempo para trocar outros três. Quem quiser os outros três tem o campo no diálogo."""

TETO_POR_LANCE_MS = 3000
"""Teto de tempo por posição, além da profundidade pedida. É o que limita o **cancelamento**.

O botão Cancelar é conferido entre uma posição e a seguinte -- interromper um `go` do UCI no meio
exige o protocolo assíncrono, e ele traria uma segunda forma de falar com o motor por causa de um
botão. Com o teto, a espera máxima entre o clique e a parada é o tempo de uma posição, e ela deixa
de depender de a posição ser um final simples ou um meio-jogo travado."""

PROFUNDIDADE_MINIMA = 6
PROFUNDIDADE_MAXIMA = 30
"""O intervalo que o diálogo oferece. Abaixo de 6 o motor não vê a tática que ele existe para
achar; acima de 30 uma partida de 40 lances passa de meia hora, e o caminho para isso é analisar
uma posição de cada vez, que a sala já faz."""

TETO_DE_AVALIACAO = 1000
"""Dez peões, em centipeões. Toda avaliação é cortada aqui antes de qualquer diferença (S-537).

**É o que impede o falso erro grave numa partida já decidida.** Sem teto, ir de +18 para +9 conta
como 900 centipeões de perda -- um "erro grave" numa posição em que qualquer lance ganha. Com o
teto, as duas viram +10 e a perda é zero, que é a leitura certa: acima de dez peões a diferença
entre duas avaliações não é informação sobre o lance.

O mate entra pelo mesmo caminho: ele vale `TETO_DE_AVALIACAO` com o sinal de quem o dá."""

POSICAO_DECIDIDA = 500
"""Cinco peões: acima disto, para os dois lados de um lance, ele não recebe juízo (S-537).

Ver `julgar` para por que a regra existe além do teto. Cinco e não dez porque é onde "ganho" deixa
de depender do lance seguinte: com cinco peões de vantagem qualquer continuação razoável ganha, e
um símbolo de erro ali diz mais sobre o motor do que sobre quem jogou."""

IMPRECISAO = "imprecisao"
ERRO = "erro"
ERRO_GRAVE = "erro_grave"
"""Os três juízos, como chave. Minúsculos e sem acento porque são identificador e não texto de
tela -- a mesma regra de `pele.CLASSICA`; quem os escreve para o usuário é `rotulo_de_juizo`."""

JUIZOS: tuple[str, ...] = (IMPRECISAO, ERRO, ERRO_GRAVE)

_CORTES: tuple[tuple[int, str], ...] = ((300, ERRO_GRAVE), (100, ERRO), (50, IMPRECISAO))
"""Perda em centipeões -> juízo, do pior para o melhor. É a tabela do `lila`, na ordem em que ela
é consultada lá: o primeiro corte que a perda alcança ganha."""

NAG_DE_JUIZO: dict[str, int] = {IMPRECISAO: 6, ERRO: 2, ERRO_GRAVE: 4}
"""`?!` = $6, `?` = $2, `??` = $4 -- os códigos do padrão PGN, e os mesmos que
`estudo.NAGS_DE_LANCE` já oferece no menu de símbolos. A marca do motor e a que a pessoa põe à mão
são **a mesma coisa** no arquivo, e é assim que ela deve ser: um `??` continua sendo um `??`."""

_ROTULOS: dict[str, tuple[str, str]] = {
    IMPRECISAO: ("imprecisão", "imprecisões"),
    ERRO: ("erro", "erros"),
    ERRO_GRAVE: ("erro grave", "erros graves"),
}
"""Singular e plural, porque o resumo conta. "2 imprecisão" saiu na primeira fotografia, e um
`s` colado no fim não serve a nenhuma das três formas do português."""


def rotulo_de_juizo(juizo: str, quantos: int = 1) -> str:
    """Como o juízo se escreve na tela, no número certo. Vazio para "nada a dizer"."""
    formas = _ROTULOS.get(juizo)
    if formas is None:
        return ""
    return formas[0] if abs(int(quantos)) == 1 else formas[1]


def avaliacao_em_centipeoes(score_cp: int | None, mate_in: int | None) -> int:
    """A avaliação como um número só, do ponto de vista das brancas e já cortada no teto.

    **Mate vira `±TETO_DE_AVALIACAO` e não um número enorme.** Um mate em 3 e um mate em 30 são a
    mesma coisa para efeito de perda -- os dois são "acabou" --, e dar-lhes valores diferentes
    faria trocar um mate em 3 por um mate em 5 aparecer como erro grave. Não é.

    Posição sem avaliação nenhuma vale zero: é o que a barra já mostra, e é a única resposta que
    não inventa vantagem para nenhum lado.
    """
    if mate_in is not None:
        return TETO_DE_AVALIACAO if int(mate_in) > 0 else -TETO_DE_AVALIACAO
    if score_cp is None:
        return 0
    return max(-TETO_DE_AVALIACAO, min(TETO_DE_AVALIACAO, int(score_cp)))


def perda_do_lance(antes: int, depois: int, *, brancas_jogaram: bool) -> int:
    """Quantos centipeões o lance custou a quem o jogou. Nunca negativo.

    Os dois números vêm do ponto de vista das **brancas** -- é como `Evaluation` os normaliza --, e
    a perda é medida do ponto de vista de quem jogou: com as pretas no lance, a avaliação subir é
    a perda delas.

    **Nunca negativo, e isso é decisão.** Um lance que melhora a avaliação em relação ao que o
    motor previa não é um lance "ganho": é o motor tendo mudado de ideia com mais um ply de
    profundidade. Registrar isso como ganho encheria a partida de `!` que ninguém jogou.
    """
    diferenca = int(antes) - int(depois) if brancas_jogaram else int(depois) - int(antes)
    return max(0, diferenca)


def classificar(perda: int) -> str:
    """O juízo daquela perda, ou `""` quando não há juízo a dar.

    **A maioria dos lances não recebe símbolo, e é assim que tem de ser.** Uma partida em que
    metade dos lances é `?!` não diz nada; a marca só vale enquanto for rara. Cinquenta centipeões
    é meio peão, que é a menor diferença que muda o plano de quem joga.

    É só a tabela de cortes: quem julga um lance de verdade é `julgar`, que aplica antes a regra
    da posição já decidida.
    """
    valor = int(perda)
    for corte, juizo in _CORTES:
        if valor >= corte:
            return juizo
    return ""


def julgar(antes: int, depois: int, *, brancas_jogaram: bool) -> tuple[int, str]:
    """A perda do lance e o juízo dela, com a regra da **posição já decidida** (S-537).

    **A regra existe porque o teto sozinho não resolve o caso**, e foi medido: com o corte em
    `TETO_DE_AVALIACAO`, ir de +18 para +9 vira 1000 -> 900 e sai como "erro" -- numa posição em
    que qualquer lance ganha. O teto só apaga a diferença quando os **dois** lados dela estouram.

    O Lichess resolve o mesmo caso por outro caminho: ele julga por perda de **expectativa de
    vitória**, e naquela escala +18 e +9 são os dois ~99% -- a diferença some sozinha. Adotar a
    escala dele aqui significaria uma segunda curva no programa, discordando da que a barra
    lateral desenha; a regra explícita diz a mesma coisa e continua legível no relatório, que
    mostra a perda em peões.

    `POSICAO_DECIDIDA` é cinco peões, e o teste é dos dois lados: quem estava ganho por cinco peões
    e continua ganho por cinco peões não errou -- mas quem cai de +6 para +2 **errou**, e o juízo
    aparece.
    """
    perda = perda_do_lance(antes, depois, brancas_jogaram=brancas_jogaram)
    do_lado = (int(antes), int(depois)) if brancas_jogaram else (-int(antes), -int(depois))
    if min(do_lado) >= POSICAO_DECIDIDA:
        return perda, ""
    return perda, classificar(perda)


@dataclass(frozen=True)
class Passo:
    """Um lance da linha principal, como a análise o percorre."""

    numero: int
    brancas: bool
    san: str


def percurso(jogo: Any) -> tuple[tuple[str, ...], tuple[Passo, ...]]:
    """As FENs da linha principal e os lances que as ligam: `n+1` posições para `n` lances.

    **A conta é `n+1` e não `n`, e é ela que define o que o motor tem de fazer.** A perda de um
    lance é a diferença entre a avaliação *antes* dele e a avaliação *depois*, então a posição de
    partida também precisa ser avaliada -- e a avaliação "depois" de um lance é a "antes" do
    seguinte. Analisar par a par pediria `2n` buscas para responder o mesmo, e numa partida de 40
    lances isso é o dobro do tempo.

    **FEN e não `GameNode`, e isso é a fronteira de thread.** O motor roda fora da linha de
    eventos, e a árvore do estudo é editável enquanto ele pensa: passar nós para a thread seria
    lê-los enquanto alguém promove uma variante. A FEN é uma cópia, e a volta é feita por posição
    na linha principal.

    Só a linha principal: as variantes são o que quem estuda escreveu **sobre** a partida, e
    analisá-las junto multiplicaria o tempo por um número que ninguém pediu.
    """
    no = getattr(jogo, "game", lambda: jogo)()
    tabuleiro = no.board()
    fens = [tabuleiro.fen()]
    passos: list[Passo] = []
    for lance in no.mainline_moves():
        passos.append(
            Passo(numero=tabuleiro.fullmove_number, brancas=bool(tabuleiro.turn), san=tabuleiro.san(lance))
        )
        tabuleiro.push(lance)
        fens.append(tabuleiro.fen())
    return tuple(fens), tuple(passos)


@dataclass(frozen=True)
class Avaliado:
    """Um lance já passado pelo motor: o que ele valia, o que custou e como se chama."""

    ply: int
    numero: int
    brancas: bool
    san: str
    centipeoes: int
    mate_em: int | None
    perda: int
    juizo: str

    @property
    def rotulo(self) -> str:
        """`24... Bd3?? -- erro grave (perdeu 4,10)`. A linha que o relatório mostra."""
        simbolo = {IMPRECISAO: "?!", ERRO: "?", ERRO_GRAVE: "??"}.get(self.juizo, "")
        numero = f"{self.numero}." if self.brancas else f"{self.numero}..."
        perda = f"{self.perda / 100:.2f}".replace(".", ",")
        return f"{numero} {self.san}{simbolo} — {rotulo_de_juizo(self.juizo)} (perdeu {perda})"


def resumo(avaliados: Sequence[Any] | None) -> str:
    """Quantos de cada juízo, por cor. É a linha que o Lichess põe no topo do relatório.

    Por cor porque a pergunta é sobre a **própria** partida: quem manda analisar quer saber quantos
    erros cometeu, e um total somado com os do adversário não responde isso.
    """
    contagem: dict[bool, dict[str, int]] = {True: {}, False: {}}
    total = 0
    for lance in avaliados or ():
        total += 1
        if lance.juizo:
            contagem[bool(lance.brancas)][lance.juizo] = contagem[bool(lance.brancas)].get(lance.juizo, 0) + 1
    if not total:
        return "Não há lance para analisar nesta partida."
    partes = []
    for brancas, nome in ((True, "Brancas"), (False, "Pretas")):
        achados = contagem[brancas]
        if not achados:
            partes.append(f"{nome}: sem erro")
            continue
        detalhe = ", ".join(
            f"{achados[juizo]} {rotulo_de_juizo(juizo, achados[juizo])}"
            for juizo in JUIZOS
            if achados.get(juizo)
        )
        partes.append(f"{nome}: {detalhe}")
    return f"{total} lance(s) analisados. " + " | ".join(partes)


def frase_de_progresso(feito: int, total: int, san: str = "") -> str:
    """O que a barra de progresso escreve. Traz o lance para a espera ter conteúdo."""
    onde = f" ({san})" if san else ""
    return f"Analisando o lance {int(feito)} de {int(total)}{onde}…"


def frase_final(quantos: int, marcados: int, *, cancelado: bool) -> str:
    """A frase do rodapé quando acaba, e ela diz **quantos símbolos foram escritos**.

    Dizer só "análise concluída" esconderia o que a análise fez com a árvore: ela escreveu
    `[%eval]` em todos os lances e um símbolo em alguns, e isso é edição do arquivo.
    """
    if cancelado:
        return f"Análise da partida cancelada: {int(quantos)} lance(s) já avaliados ficam gravados."
    return f"Partida analisada: {int(quantos)} lance(s) avaliados, {int(marcados)} com símbolo."


# ----------------------------------------------------------------- o gráfico (S-537)


def y_do_meio(altura: int) -> int:
    """A linha do equilíbrio. Ela é desenhada porque sem ela o gráfico não tem zero."""
    return int(round(max(0, int(altura)) / 2))


def pontos_do_grafico(
    avaliados: Sequence[Any] | None, largura: int, altura: int
) -> tuple[tuple[int, int], ...]:
    """A polilinha do gráfico, em pixel, na ordem dos plies (S-537).

    **O eixo vertical é a fração de vantagem, e não os centipeões.** É a mesma curva da barra
    lateral (`engine.fracao_de_vantagem`), e a razão é a mesma: um gráfico linear em centipeões
    gastaria dois terços da altura com a faixa entre +3 e +10, em que a partida já acabou, e
    achataria contra a linha do meio justamente a faixa em que ela se decide.

    Brancas para **cima**: é o sentido da barra lateral virado 90°, e trocá-lo entre os dois
    desenhos da mesma tela seria o defeito que a S-158 registra para cor.

    Um ponto só devolve um ponto (o `QPainter` desenha nada com ele, e é a resposta certa: com um
    lance não há curva). Largura ou altura zero devolve vazio -- é a janela ainda sem geometria.
    """
    lista = list(avaliados or ())
    if not lista or int(largura) <= 0 or int(altura) <= 0:
        return ()
    return tuple(
        (
            _x_do_indice(indice, len(lista), int(largura)),
            _y_da_fracao(fracao_de_vantagem(lance.centipeoes, lance.mate_em), int(altura)),
        )
        for indice, lance in enumerate(lista)
    )


def _x_do_indice(indice: int, total: int, largura: int) -> int:
    if total <= 1:
        return 0
    return int(round(indice * (largura - 1) / (total - 1)))


def _y_da_fracao(fracao: float, altura: int) -> int:
    limpa = min(1.0, max(0.0, float(fracao)))
    return int(round((1.0 - limpa) * (altura - 1)))


def indice_no_x(x: int, total: int, largura: int) -> int:
    """Qual ply está sob aquele pixel. É o que faz o gráfico ser clicável (S-537).

    **Clicar no vale leva ao lance do vale**, que é o gesto inteiro deste item: o gráfico existe
    para achar onde a partida virou, e um gráfico que não leva até lá deixa a busca para o dedo de
    quem lê a lista. Fora da faixa devolve a ponta mais próxima -- clicar meio pixel antes do
    começo não pode ser "nenhum lance".
    """
    if total <= 0 or int(largura) <= 1:
        return 0
    fracao = int(x) / (int(largura) - 1)
    return max(0, min(int(total) - 1, int(round(fracao * (int(total) - 1)))))
