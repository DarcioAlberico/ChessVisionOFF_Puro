"""O final resolvido por tabela, e não por busca: quando perguntar e o que dizer (S-538).

**Um motor num final de cinco peças ainda está chutando, e agora isso está medido.** Contra as
tabelas de 3 e 4 peças desta máquina (2026-09-04, Stockfish dev-20230303): na posição de Philidor
de torre contra bispo ele diz **`+0,26` a profundidade 23** sobre uma **tábua teórica**, e num
bispo-e-cavalo contra rei ele diz **`+2,31` a profundidade 25** sobre um **mate forçado com 56 de
zeragem**. Não existe "+0,26" nem "+2,31" ali. As tablebases Syzygy resolveram esses finais por
retroanálise: a resposta delas não é uma estimativa, é o resultado.

**A pasta é opcional e sem padrão, e é a mesma regra da S-32.** Os arquivos de cinco peças são
~1 GB e os de seis, ~150 GB: nada disso vem no repositório e nada disso se presume. Sem pasta
configurada, nada muda -- o painel continua mostrando o que o motor disse, como sempre mostrou.

**Perguntar é barato, e é isso que autoriza perguntar antes do motor.** Medido em 500 consultas:
mediana de **123 µs**, p95 de **196 µs**, pior caso de 1,1 ms, e 6,6 ms na primeira (que paga a
varredura do diretório). Uma análise a 800 ms é ~6.500 vezes mais cara que a consulta.

**O que Syzygy sabe, e o que ele não sabe.** WDL diz o resultado com jogo perfeito (`+2` ganho,
`+1` ganho que a regra dos 50 lances anula, `0` tábua, e os negativos espelhados); DTZ diz quantos
lances faltam até a próxima captura ou lance de peão. **Nenhum dos dois é distância até o mate.**
"Mate em N" é o que o *motor* diz quando ele mesmo carrega as tabelas -- e é por isso que a S-536
manda `SyzygyPath` para o processo também: as duas metades da resposta chegam, cada uma de quem a
tem. O que este módulo escreve é o resultado exato e a distância que a tabela de fato guarda, sem
inventar um número que o arquivo não contém.

Nada de `PyQt6`, e nada de `chess.syzygy`: quem abre a pasta é `tablebase.py`, e aqui só se decide
se vale perguntar e como a resposta se lê.
"""

from __future__ import annotations

__all__ = [
    "centipeoes_de",
    "deve_consultar",
    "frase_do_resultado",
    "vence_o_motor",
]

PECAS_MAXIMAS = 7
"""Acima disto não existe tabela, e perguntar seria abrir arquivos que não podem estar lá.

Sete porque as tabelas de sete peças existem; quase ninguém as tem no disco, e é a própria tabela
que responde "não tenho" -- `tablebase.py` trata isso como resposta e não como erro. O teto aqui
serve para não pagar a ida ao disco em toda posição de meio-jogo, que é onde a sala passa o tempo."""

_RESULTADO_DE_WDL: dict[int, str] = {
    2: "vitória",
    1: "vitória teórica",
    0: "tábuas",
    -1: "derrota teórica",
    -2: "derrota",
}
"""O WDL como se lê, do ponto de vista de **quem está no lance** -- que é como Syzygy o devolve.

`±1` é o "cursed win"/"blessed loss": a posição é ganha, e a regra dos 50 lances a transforma em
tábua antes de a zeragem acontecer. Chamá-lo de "vitória" seria mentir sobre o resultado da
partida; chamá-lo de "tábuas" seria esconder que o final é ganho e que o adversário tem de saber
contar até 50. "Teórica" é a palavra que os dois lados dessa frase aceitam."""


def deve_consultar(pecas: int, *, tem_pasta: bool) -> bool:
    """Vale perguntar à tabela nesta posição? Sem pasta, nunca (S-538).

    A contagem inclui os dois reis, que é como Syzygy nomeia os arquivos (`KRvK` são três peças).
    """
    return bool(tem_pasta) and 0 < int(pecas) <= PECAS_MAXIMAS


def vence_o_motor(wdl: int | None) -> bool:
    """A tabela ganha do motor quando ela **responde**. `None` é "não tenho este final".

    Não é preferência: a tabela sabe o resultado e o motor estima. O `None` é o caso comum de
    quem tem só os arquivos de cinco peças e chegou a uma posição de seis, e ali a estimativa do
    motor volta a ser a melhor resposta que existe.
    """
    return wdl is not None


def frase_do_resultado(wdl: int | None, dtz: int | None = None, *, brancas_jogam: bool = True) -> str:
    """O resultado exato, nomeando **de quem** ele é, com a distância que a tabela guarda.

    **O sujeito da frase é a cor, e não "você".** O WDL de Syzygy é do lado que está no lance, e
    uma frase que dissesse "vitória" ao lado de um tabuleiro com as pretas a jogar seria lida como
    vitória das brancas por qualquer um -- é o mesmo defeito que `Evaluation` conserta ao
    normalizar a pontuação para as brancas.

    **O sujeito é sempre quem está no lance**, e não "quem ganha": o WDL de Syzygy é do lado que
    joga, e é essa a frase que ele autoriza. Escrevê-la sempre como vitória obrigaria a inverter o
    resultado antes -- uma conta a mais, num lugar em que trocar o sinal por engano dá uma tela que
    afirma o contrário do arquivo.

    A zeragem aparece com o nome que ela tem: não é "mate em N", e chamá-la assim poria na tela um
    número que a tabela não contém.
    """
    if wdl is None:
        return ""
    resultado = _RESULTADO_DE_WDL.get(int(wdl), "")
    if not resultado:
        return ""
    if int(wdl) == 0:
        return "Tábuas (tabela de finais)."
    lado = "brancas" if brancas_jogam else "pretas"
    frase = f"Tabela de finais: {resultado} das {lado}"
    if dtz is not None and int(dtz):
        frase += f", zeragem em {abs(int(dtz))}"
    return frase + "."


def centipeoes_de(wdl: int | None, *, brancas_jogam: bool = True, teto: int = 1000) -> int | None:
    """O resultado como número, do ponto de vista das brancas, para a barra e o gráfico.

    **A barra não pode ficar parada quando a tabela fala.** Ela é o que se lê de longe, e uma
    tabela dizendo "tábuas" com a barra ainda em +3,45 é a tela discordando de si mesma. Ganho vai
    ao teto, tábua vai a zero, e a barra fica onde o resultado manda.

    O `±1` (a vitória que os 50 lances anulam) vale **zero**: no placar da partida ela é tábua, e é
    o placar que a barra mostra. A frase ao lado é quem diz que o final é ganho.
    """
    if wdl is None:
        return None
    valor = int(wdl)
    if abs(valor) < 2:
        return 0
    ganho = valor > 0
    return int(teto) if ganho == bool(brancas_jogam) else -int(teto)
