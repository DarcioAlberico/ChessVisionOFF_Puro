"""A moldura que envolve a folha, e por que ela apagava a folha inteira (S-711).

**O sintoma parecia ser a região escura, e não era.** A folha perdida do *Chess Evolution* tem uma faixa azul
na lateral, a do *Kmoch* tem a borda escura do scanner, e o roadmap supunha que o escuro confundia a medida da
escala. Medido em 2026-11-05, o maior componente de cada folha perdida é **a folha inteira**: `(0, 0, 2571,
1819)`, com 22% da tinta, feito de um filete fino na borda ligado à faixa. E `caixas_de_caractere` só pega
contorno externo, então tudo o que está dentro dele deixa de existir: `caixas=1`, e o glifo lê `h`.

A prova é a folha 501 do mesmo livro: a mesma faixa azul, de `(0, 0, 377, 1819)`, sem o filete fechando a volta,
dá 1.691 caixas e lê normal. **O que apaga não é o escuro, é o que envolve.** Por isso o critério é geométrico
e estreito: só sai o componente cuja caixa cobre a folha nas duas direções, e a folha sem moldura não muda em
um pixel.

**Sai da binária, e não da imagem.** A letra que encosta na moldura é parte do componente, e sai com ela: numa
folha desenhada são 20 de 500 caixas, e nenhum caso real apareceu. O que o conserto não traz é o texto claro de
dentro da faixa, que é o título corrente do fascículo: a camada o tem, e ler o negativo de uma faixa vertical é
outro item. Um quadro abaixo de `COBERTURA_MINIMA` continua apagando a folha, e a guarda da S-710 o avisa.

**O que estava dentro pode não ser texto.** Em contracapa manchada e marca d'água sai ruído onde antes não saía
nada, e é a guarda que o acusa: ver `guarda_de_leitura.RUIDO_POR_TOKEN`.
"""

from __future__ import annotations

import cv2
import numpy as np

TIRAR_MOLDURA = True
"""A reversão da S-711: desligada, a folha volta a ser lida como antes, com a guarda da S-710 acusando a perda."""

COBERTURA_MINIMA = 0.9
"""Quanto da folha a caixa do componente tem de cobrir, em cada direção, para ser moldura.

Não é 1,0 porque o scan raramente fecha na última fileira de pixels. Um diagrama de página inteira não chega
aqui: ele não encosta nas duas bordas opostas nas duas direções, e a margem tira mais que 10%."""


def tirar_moldura(binaria: np.ndarray) -> tuple[np.ndarray, int]:
    """A binária sem o componente que envolve a folha, e quantos saíram. **A mesma binária se não há nenhum.**

    Devolver o objeto recebido é parte do contrato: a folha sem moldura sai idêntica, e sem custo de cópia.
    """
    if not TIRAR_MOLDURA or binaria.size == 0:
        return binaria, 0
    altura, largura = binaria.shape[:2]
    n, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(binaria, connectivity=8)
    envolventes = [
        k
        for k in range(1, n)
        if estatisticas[k, cv2.CC_STAT_WIDTH] >= COBERTURA_MINIMA * largura
        and estatisticas[k, cv2.CC_STAT_HEIGHT] >= COBERTURA_MINIMA * altura
    ]
    if not envolventes:
        return binaria, 0
    limpa = binaria.copy()
    limpa[np.isin(rotulos, envolventes)] = 0
    return limpa, len(envolventes)


__all__ = ["COBERTURA_MINIMA", "TIRAR_MOLDURA", "tirar_moldura"]
