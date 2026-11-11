"""Os limites de relógio da suíte, multiplicados por um fator do ambiente (S-872).

**O defeito.** Um teste que afirma "cancelar para em menos de 1,5 s" ou "a consulta custa menos de
5 ms" mede o código **e** a máquina. Ocioso, o número é o do código; com outros quatro agentes
dividindo a CPU, ou sob `coverage`, que põe um rastreador em cada linha, é o da máquina -- e o
teste reprova sem defeito nenhum. Foi medido nesta suíte: `test_busy` levando 58 s numa rodada
carregada, e as esperas de cancelamento e de GIL estourando só em conjunto.

**A regra.** Todo limite de relógio passa por `limite()`, que o multiplica por `fator()`:
`CVOFF_FATOR_DE_TEMPO` quando definida, 3 sob `coverage`, 1 no resto. O número escrito no teste
continua sendo o critério do item, medido em máquina ociosa; o fator diz quanto mais lenta esta
máquina está agora. Quem roda a suíte num agente lento põe a variável; ninguém sobe o número do teste.

**O que não passa por aqui.** Uma espera que só aguarda um evento (`esperar_ate`, em
`tests/qt_app.py`) também escala, mas **reprova** no estouro: uma espera que voltasse calada deixaria
a asserção seguinte reprovar com uma frase que não diz que o tempo acabou. E onde o teste compara
duas medidas da mesma máquina (o filho que não segura o GIL contra o trabalho que ele faz), as duas
escalam juntas, e a razão entre elas é o que se afirma.
"""

from __future__ import annotations

import os
import sys

VARIAVEL = "CVOFF_FATOR_DE_TEMPO"
FATOR_SOB_COBERTURA = 3.0
"""Medido no `coverage` 7 com o rastreador em C: o Python puro fica 2 a 3 vezes mais lento."""


def sob_cobertura() -> bool:
    """Se há um `coverage` medindo este processo (o `pytest --cov` e o `coverage run`)."""
    coverage = sys.modules.get("coverage")
    return coverage is not None and coverage.Coverage.current() is not None


def fator() -> float:
    """`CVOFF_FATOR_DE_TEMPO`, ou 3 sob cobertura, ou 1. Um valor que não é número positivo levanta:
    um fator ignorado calado é a reprovação por relógio de volta, sem ninguém saber por quê."""
    texto = os.environ.get(VARIAVEL, "").strip()
    if not texto:
        return FATOR_SOB_COBERTURA if sob_cobertura() else 1.0
    valor = float(texto.replace(",", "."))
    if valor <= 0:
        raise ValueError(f"{VARIAVEL}={texto!r}: o fator de tempo tem de ser positivo")
    return valor


def limite(segundos: float) -> float:
    """O limite do teste, em segundos, nesta máquina."""
    return segundos * fator()


def limite_ms(milissegundos: int) -> int:
    """O mesmo, em milissegundos inteiros -- o que o `QTest.qWait` e o `QThread.wait` recebem."""
    return round(milissegundos * fator())
