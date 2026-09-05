"""A partida inteira analisada: quanto cada lance custou, e onde o gráfico o desenha (S-537).

**A pergunta que isto responde é a do dia seguinte ao torneio**: *em que lance eu perdi?* A sala
já sabia avaliar **uma** posição desde a S-33 e gravar o número no lance desde a S-285; o que não
existia era passar a partida inteira pelo motor e dizer, em uma tela, onde a avaliação virou.

**Três decisões moram aqui, e nenhuma delas precisa de motor nem de janela.**

1. **Quanto um lance custou.** A avaliação antes e a avaliação depois, as duas do ponto de vista de
   quem jogou, e a diferença. É aritmética, e é justamente por isso que ela tem de estar num lugar
   só: escrita duas vezes -- uma no relatório, outra na marca do lance -- as duas versões divergem
   no primeiro mate.
2. **Onde estão os cortes.** `?!`, `?` e `??` não são opinião: são 8, 15 e 25 pontos percentuais de
   **expectativa de vitória** perdidos, medidos na curva que o programa já usa para desenhar a
   barra. A primeira redação usava a tabela clássica em centipeões (50/100/300, do `lila` e do
   Scid) e o crítico mediu o que ela custa: em 256 lances de três partidas de torneio ela discorda
   do Lichess em 14 juízos, contra 4 desta. A razão é que meio peão não vale o mesmo em toda
   posição -- ver `_CORTES` para a medição e para por que os números não são os 6/10/20 do
   Lichess.
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

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..engine import TETO_DE_CENTIPEOES, fracao_de_vantagem

__all__ = [
    "ERRO",
    "ERRO_GRAVE",
    "IMPRECISAO",
    "NAG_DE_JUIZO",
    "PROFUNDIDADE_MAXIMA",
    "PROFUNDIDADE_MINIMA",
    "PROFUNDIDADE_PADRAO",
    "TETO_DE_AVALIACAO",
    "Avaliado",
    "avaliacao_em_centipeoes",
    "classificar",
    "frase_de_progresso",
    "frase_de_truncamento",
    "frase_do_ponto",
    "frase_final",
    "grava_avaliacao",
    "indice_no_x",
    "julgar",
    "peoes",
    "percurso",
    "perda_de_expectativa",
    "perda_media",
    "pontos_do_grafico",
    "precisao",
    "resumo",
    "teto_por_lance_ms",
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
"""Teto de tempo por posição **na profundidade padrão**. É o que limita o **cancelamento**.

O botão Cancelar é conferido entre uma posição e a seguinte -- interromper um `go` do UCI no meio
exige o protocolo assíncrono, e ele traria uma segunda forma de falar com o motor por causa de um
botão. Com o teto, a espera máxima entre o clique e a parada é o tempo de uma posição, e ela deixa
de depender de a posição ser um final simples ou um meio-jogo travado.

**Ele deixou de ser um número só, e a razão foi medida** -- ver `teto_por_lance_ms`."""

TETO_MAXIMO_POR_LANCE_MS = 30_000
"""Meio minuto: o teto do teto, e o que faz o Cancelar continuar existindo (S-537, 2ª rodada).

A profundidade 30 pede, medida nesta máquina, uma mediana de **15,9 s** por posição e um pior caso
de **34,2 s**. Deixar o teto crescer com ela sem limite seria trocar "o Cancelar espera uma
posição" por "o Cancelar espera o tempo que der": meio minuto é o maior atraso que ainda se pode
chamar de resposta ao botão, e a posição que passar disso sai truncada -- e **contada**, que é a
outra metade do conserto."""

FATOR_DE_TETO_POR_PLY = 1.4
"""Cada ply a mais custa 40% de tempo. Medido em 2026-09-04, e é a lei que escala o teto.

Amostra de 13 posições da partida ALG-ch 2012 (Stockfish dev-20230303, 1 thread, `Hash` 16 MB,
sem teto de tempo): a partida inteira sai em **10 s** a profundidade 16, **44 s** a 20, **188 s** a
24 e **953 s** a 30. Entre 16 e 24 isso é 1,44 por ply; entre 24 e 30, 1,31. Um e quatro é o meio,
e é o que `teto_por_lance_ms` usa."""

PROFUNDIDADE_MINIMA = 6
PROFUNDIDADE_MAXIMA = 30
"""O intervalo que o diálogo oferece. Abaixo de 6 o motor não vê a tática que ele existe para
achar; acima de 30 uma partida de 40 lances passa de meia hora, e o caminho para isso é analisar
uma posição de cada vez, que a sala já faz."""

TETO_DE_AVALIACAO = TETO_DE_CENTIPEOES
"""Dez peões, em centipeões. Toda avaliação é cortada aqui antes de qualquer diferença (S-537).

Acima de dez peões a diferença entre duas avaliações não é informação sobre o lance: os dois lados
dela são "acabou". O corte é o mesmo que o `engine` aplica ao que a tabela de finais lhe manda
(S-538), e por isso ele é **o mesmo número** -- `engine.TETO_DE_CENTIPEOES` -- e não uma segunda
constante com o mesmo valor.

O mate entra pelo mesmo caminho: ele vale `TETO_DE_AVALIACAO` com o sinal de quem o dá."""

IMPRECISAO = "imprecisao"
ERRO = "erro"
ERRO_GRAVE = "erro_grave"
"""Os três juízos, como chave. Minúsculos e sem acento porque são identificador e não texto de
tela -- a mesma regra de `pele.CLASSICA`; quem os escreve para o usuário é `rotulo_de_juizo`."""

JUIZOS: tuple[str, ...] = (IMPRECISAO, ERRO, ERRO_GRAVE)

_CORTES: tuple[tuple[int, str], ...] = ((25, ERRO_GRAVE), (15, ERRO), (8, IMPRECISAO))
"""Perda de **expectativa de vitória**, em pontos percentuais -> juízo (S-537, segunda rodada).

**O que estava aqui, e por que ele estava errado.** Eram 300, 100 e 50 *centipeões* -- a tabela
clássica do `lila` e do Scid. Ela julga a mesma perda de meio peão do mesmo jeito no equilíbrio e
com dez peões de diferença, e o xadrez não é assim: sair de 0,00 para -0,60 muda a partida, e sair
de +9 para +8,40 não muda nada. O Lichess de hoje já não usa essa tabela -- ele julga por perda de
expectativa de vitória, 6/10/20 pontos --, e o crítico mediu o custo de não fazê-lo: numa partida
de torneio de verdade (ALG-ch Women 2012), **6 dos 12** juízos discordavam do Lichess, com
`9...O-O` (0,46 -> 2,94) saindo `?` onde o Lichess dá `??` e `27...Kh7` (+3,04 -> +3,86) saindo
`?!` onde o Lichess não marca nada.

**A curva é a que o programa já tem, e é por isso que os números não são 6/10/20.** A expectativa
daqui é `engine.fracao_de_vantagem` -- a do Elo, `1/(1+10^(-cp/400))` --, a mesma que desenha a
barra lateral e o gráfico logo abaixo destes cortes. Ela é 1,56 vez mais íngreme no miolo que a do
Lichess (`2/(1+e^(-0,00368208·cp))-1`) e satura antes, então os mesmos 6/10/20 marcariam bem mais
lances. Usar a curva do Lichess aqui seria pôr uma segunda curva no programa, discordando do
desenho ao lado -- que é exatamente o defeito que a S-529 registra.

**Os cortes foram medidos, e não convertidos.** 256 lances de três partidas do gigabase
(`scratchpad/r2/calibrar.py`), profundidade 16: a tabela em peões discorda do Lichess em **14**;
esta, em **4**. A varredura do espaço inteiro dá um platô -- 24 a 26 para o grave, 15 a 16 para o
erro, 8 para a imprecisão --, todos com 4 divergências; 25/15/8 é o meio dele. Marcados: 29 lances
de 256, contra 28 do Lichess e 32 da tabela em peões.

Do pior para o melhor, na ordem em que são consultados: o primeiro corte que a perda alcança ganha."""

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


def peoes(centipeoes: int) -> str:
    """Centipeões escritos como o tabuleiro os lê: `4,10`. Vírgula, porque a janela é pt-BR.

    Existe porque a mesma grafia é pedida em três lugares -- o rótulo do lance julgado, a frase do
    treino da S-541 e o placar --, e três `f"{x/100:.2f}".replace(".", ",")` divergiriam na
    primeira vez que alguém mudasse a casa decimal de um deles.
    """
    return f"{int(centipeoes) / 100:.2f}".replace(".", ",")


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


def expectativa(centipeoes: int) -> float:
    """A avaliação como **chance de ganhar**, de 0 a 100. É a curva da barra, em porcento.

    Uma linha, e ela é o item: `engine.fracao_de_vantagem` é a mesma função que desenha a barra
    lateral e o gráfico. O juízo de um lance passou a ser medido nesta escala (ver `_CORTES`), e
    escrevê-la aqui como uma segunda logística seria o defeito que a S-529 registra -- um número
    julgando o lance e outro desenhando a barra ao lado dele.
    """
    return 100.0 * fracao_de_vantagem(int(centipeoes), None)


def perda_de_expectativa(antes: int, depois: int, *, brancas_jogaram: bool) -> float:
    """Quantos pontos percentuais de chance de vitória o lance custou a quem o jogou.

    Nunca negativa, pela mesma razão de `perda_do_lance`: um lance que "melhora" a avaliação é o
    motor tendo mudado de ideia com mais um ply, e não um lance ganho.
    """
    sinal = 1.0 if brancas_jogaram else -1.0
    return max(0.0, sinal * (expectativa(antes) - expectativa(depois)))


def classificar(perda_de_chance: float) -> str:
    """O juízo daquela perda de expectativa, ou `""` quando não há juízo a dar.

    **A maioria dos lances não recebe símbolo, e é assim que tem de ser.** Uma partida em que
    metade dos lances é `?!` não diz nada; a marca só vale enquanto for rara -- medido: 29 lances
    marcados em 256.

    O argumento é **pontos percentuais de chance de vitória**, e não centipeões: ver `_CORTES` para
    a medição que trocou a escala.
    """
    valor = float(perda_de_chance)
    for corte, juizo in _CORTES:
        if valor >= corte:
            return juizo
    return ""


def julgar(antes: int, depois: int, *, brancas_jogaram: bool) -> tuple[int, str]:
    """A perda do lance **em centipeões** e o juízo dela **em expectativa** (S-537, 2ª rodada).

    Os dois números, e cada um responde uma pergunta diferente: a perda em peões é o que o
    relatório escreve (`perdeu 2,48`) e o que soma no ACPL, porque é a linguagem em que se fala de
    uma posição; o juízo sai da chance de vitória, porque é ali que meio peão significa coisas
    diferentes em posições diferentes.

    **A regra da "posição já decidida" sumiu, e é o conserto** (segunda rodada). Ela existia porque
    a escala em peões não sabia que +18 e +9 são a mesma coisa: o teto só apaga a diferença quando
    os dois lados dele estouram, e de +18 para +9 sobrava um "erro" numa posição ganha. A regra
    tapava isso com um limiar (`POSICAO_DECIDIDA`, cinco peões) que só olhava para **quem estava
    ganhando** -- e o crítico achou o outro lado dela: com as pretas perdidas, cair de -6 para -10
    saía como *erro grave*, porque a regra não protegia quem já tinha perdido.

    A escala de expectativa não precisa de regra nenhuma. Os dois casos saem certos por
    construção: +18 -> +9 custa **0,24** ponto de chance, e -6 -> -10 custa **2,75** -- os dois bem
    abaixo do corte de imprecisão. Uma regra a menos, e a que sumiu era a que tinha o defeito.
    """
    perda = perda_do_lance(antes, depois, brancas_jogaram=brancas_jogaram)
    return perda, classificar(perda_de_expectativa(antes, depois, brancas_jogaram=brancas_jogaram))


def teto_por_lance_ms(profundidade: int) -> int:
    """Quanto o motor pode gastar numa posição, para a profundidade pedida (S-537, 2ª rodada).

    **O teto era fixo em 3 s, e com ele a profundidade que o diálogo oferece não existia.** Medido
    pelo crítico: pedindo 30, **41 de 46** posições paravam no teto e a profundidade média
    alcançada era 23,5 -- pedir 30 custava o mesmo que pedir 24 e dava o mesmo resultado, com o
    diálogo prometendo outra coisa. Remedido aqui em 13 posições sem teto nenhum: a profundidade 16
    tem pior caso de **0,55 s**, a 20 de **1,33 s**, a 24 de **8,97 s** e a 30 de **34,2 s**.

    O teto passa a crescer com a profundidade na lei medida (`FATOR_DE_TETO_POR_PLY`), ancorado nos
    3 s da profundidade padrão: 3,0 s a 16, 11,5 s a 20, e o teto do teto
    (`TETO_MAXIMO_POR_LANCE_MS`) de 24 em diante. Com isso as profundidades 16, 20 e 24 chegam
    inteiras nas 13 posições medidas, e só a 30 trunca -- **uma** delas, que o relatório conta.
    """
    plies = max(PROFUNDIDADE_MINIMA, min(PROFUNDIDADE_MAXIMA, int(profundidade)))
    escalado = TETO_POR_LANCE_MS * (FATOR_DE_TETO_POR_PLY ** (plies - PROFUNDIDADE_PADRAO))
    return max(TETO_POR_LANCE_MS, min(TETO_MAXIMO_POR_LANCE_MS, int(round(escalado))))


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

    perda_de_chance: float = 0.0
    """Pontos percentuais de expectativa que o lance custou. É por ele que o juízo foi dado."""

    profundidade: int = 0
    """A profundidade que o motor **alcançou** nesta posição. Ver `frase_de_truncamento`."""

    acabou: bool = False
    """A posição depois do lance é mate ou afogamento -- não há o que avaliar nela (S-537).

    Existe por causa do `[%eval #1]` que o crítico achou gravado na posição já matada: um mate já
    dado não é "mate em um", e escrever isso no arquivo é escrever um número falso num campo que
    outros programas leem. Quem decide o que fazer com ele é `grava_avaliacao`."""

    @property
    def rotulo(self) -> str:
        """`24... Bd3?? -- erro grave (perdeu 4,10)`. A linha que o relatório mostra."""
        simbolo = {IMPRECISAO: "?!", ERRO: "?", ERRO_GRAVE: "??"}.get(self.juizo, "")
        numero = f"{self.numero}." if self.brancas else f"{self.numero}..."
        return f"{numero} {self.san}{simbolo} — {rotulo_de_juizo(self.juizo)} (perdeu {peoes(self.perda)})"


def grava_avaliacao(avaliado: Any) -> bool:
    """Este lance ganha `[%eval]` no arquivo? Não, quando a posição depois dele já acabou (S-537).

    **O caso é o último lance de uma partida que termina em mate.** O UCI responde `score mate 0`
    ali -- "quem está no lance está mateado" --, `engine._to_white_pov` normaliza para `±1` porque
    a barra e a conta de perda precisam do sinal, e o resultado era `[%eval #1]` gravado no PGN de
    uma posição em que o mate **já aconteceu**. Nenhum programa de xadrez escreve isso; o Lichess
    simplesmente não grava avaliação na posição final.

    A avaliação continua existindo para o relatório e para o gráfico -- ela é o que diz que o
    último lance não foi um erro --, só não vai para o arquivo.
    """
    return not bool(getattr(avaliado, "acabou", False))


def perda_media(avaliados: Sequence[Any] | None, *, brancas: bool) -> int:
    """O ACPL daquela cor: a perda média por lance, em centipeões (S-537, segunda rodada).

    **É o número que a ChessBase e o Lichess põem no topo do relatório**, e o único que compara
    duas partidas: a contagem de erros diz quantas vezes alguém tropeçou, e o ACPL diz o quanto.
    Uma partida de dois `??` e nada mais e uma de vinte imprecisões podem ter a mesma contagem e
    ACPL muito diferente.

    Cor sem lance nenhum devolve zero -- não há média de nada, e um traço na tela é pior que um
    zero que ninguém vai ler numa partida sem lances daquela cor.
    """
    perdas = [int(lance.perda) for lance in avaliados or () if bool(lance.brancas) == bool(brancas)]
    return int(round(sum(perdas) / len(perdas))) if perdas else 0


def precisao(avaliados: Sequence[Any] | None, *, brancas: bool) -> int:
    """A precisão daquela cor, de 0 a 100 (S-537, segunda rodada).

    **A fórmula é a do Lichess**, aplicada à expectativa **daqui**:
    `103,1668·e^(-0,04354·perda) - 3,1669`, por lance, e a média disso. Ela existe porque o ACPL
    sozinho é enganoso: 100 centipeões perdidos num equilíbrio são a partida, e os mesmos 100 com
    seis peões de vantagem não são nada -- a exponencial sobre a perda de **chance** já sabe disso,
    e é a mesma escala em que os cortes de `?!`/`?`/`??` foram medidos.

    Medido na partida do crítico (ALG-ch Women 2012): brancas **91**, pretas **85**, com ACPL 28 e
    53. Pela curva do Lichess os mesmos lances dariam 92 e 87 -- a diferença é a curva, não a
    fórmula, e ela é a mesma que o cabeçalho de `ui/motor_declarado.py` tabela.

    Média simples e não a média harmônica ponderada por volatilidade que o Lichess usa: a
    ponderação dele existe para punir o erro na posição decisiva, e ela pede uma janela deslizante
    sobre a partida -- um segundo modelo, para mover o número em um ou dois pontos.
    """
    perdas = [
        float(getattr(lance, "perda_de_chance", 0.0) or 0.0)
        for lance in avaliados or ()
        if bool(lance.brancas) == bool(brancas)
    ]
    if not perdas:
        return 100
    notas = [max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * perda) - 3.1669)) for perda in perdas]
    return int(round(sum(notas) / len(notas)))


def frase_de_truncamento(avaliados: Sequence[Any] | None, profundidade: int) -> str:
    """Quantas posições **não** chegaram à profundidade pedida. Vazio quando todas chegaram.

    **Ela existe porque o teto de tempo mente em silêncio** (S-537, segunda rodada). O crítico
    pediu profundidade 30 e recebeu 23,5 de média, sem nada na tela dizendo isso: o relatório
    afirmava a mesma coisa que afirmaria se as 46 posições tivessem chegado lá. `teto_por_lance_ms`
    reduziu muito o caso, e não pode eliminá-lo -- um meio-jogo travado a 30 plies passa de meio
    minuto em qualquer máquina --, então o que sobra tem de estar escrito.
    """
    pedida = int(profundidade)
    if pedida <= 0:
        return ""
    curtas = [lance for lance in avaliados or () if 0 < int(getattr(lance, "profundidade", 0)) < pedida]
    if not curtas:
        return ""
    menor = min(int(lance.profundidade) for lance in curtas)
    return (
        f"{len(curtas)} posição(ões) pararam no teto de tempo antes da profundidade {pedida} "
        f"(a mais curta chegou a {menor})."
    )


def resumo(avaliados: Sequence[Any] | None) -> str:
    """Quantos de cada juízo, o ACPL e a precisão, por cor. É o topo do relatório.

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
        detalhe = ", ".join(
            f"{achados[juizo]} {rotulo_de_juizo(juizo, achados[juizo])}"
            for juizo in JUIZOS
            if achados.get(juizo)
        )
        numeros = (
            f"precisão {precisao(avaliados, brancas=brancas)}%, "
            f"perda média {perda_media(avaliados, brancas=brancas)} centipeões"
        )
        partes.append(f"{nome}: {detalhe or 'sem erro'} — {numeros}")
    return f"{total} lance(s) analisados. " + " | ".join(partes)


def frase_de_progresso(feito: int, total: int, san: str = "") -> str:
    """O que a barra de progresso escreve. Traz o lance para a espera ter conteúdo.

    **Contando a partir de 1**, e a razão é o que o crítico leu na tela: `Analisando o lance 0 de
    62`. A análise avalia `n+1` posições para `n` lances (ver `percurso`), e a primeira delas é a
    posição *antes* do primeiro lance -- quem chamava passava o índice da posição como se fosse o
    número do lance. O lance 0 não existe, e 62 não era o número de lances (eram 61).
    """
    quantos = max(0, int(total))
    onde = f" ({san})" if san else ""
    return f"Analisando o lance {max(1, min(int(feito), quantos)) if quantos else 0} de {quantos}{onde}…"


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


def frase_do_ponto(avaliado: Any) -> str:
    """`ply 48 · 24... Rxf2 ?? · avaliação -2,52 · perdeu 2,50`. A dica do ponto do gráfico.

    **O gráfico só tinha forma, e forma sem número não se lê** (S-537, segunda rodada). Ele mostra
    onde a partida virou, e quem para o ponteiro num vale quer saber *qual lance* e *quanto*:
    encontrar isso obrigava a clicar (movendo o tabuleiro) ou a procurar na lista ao lado, que só
    tem os lances julgados.

    O ply vem primeiro porque é o eixo: é a única coordenada que o desenho tem e não escreve.
    """
    if avaliado is None:  # pragma: no cover - o gráfico só pergunta por ponto que existe
        return ""
    simbolo = {IMPRECISAO: " ?!", ERRO: " ?", ERRO_GRAVE: " ??"}.get(avaliado.juizo, "")
    numero = f"{avaliado.numero}." if avaliado.brancas else f"{avaliado.numero}..."
    partes = [
        f"ply {int(avaliado.ply)}",
        f"{numero} {avaliado.san}{simbolo}",
        f"avaliação {peoes(avaliado.centipeoes)}" if avaliado.mate_em is None else f"mate em {abs(int(avaliado.mate_em))}",
    ]
    if avaliado.perda:
        partes.append(f"perdeu {peoes(avaliado.perda)}")
    return " · ".join(partes)


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
