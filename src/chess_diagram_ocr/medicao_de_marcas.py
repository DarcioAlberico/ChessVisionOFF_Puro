"""A medição dos leitores de marca: o teste congelado e os alarmes, na mesma régua para todos.

Quem mede é o `cvoff-marcas medir` e a janela do modelo de marcas (`qt/treino_de_marcas.py`), e os dois
precisam do mesmo número: um modelo que a janela aprovasse com uma conta e o comando com outra seria um
modelo aprovado duas vezes por razões diferentes. Por isso a conta mora aqui, sem Qt e sem `print`.

**Duas perguntas, e as duas valem.** O teste congelado (`teste_de_marcas`) diz quantas marcas reais cada
leitor acha e quantas inventa nos diagramas anotados. As amostras de validação e teste que ninguém anotou
dizem quantos diagramas sem marca cada leitor aponta -- os alarmes, que uma pessoa teria de recusar. Um
modelo que acha uma marca a mais e alarma em dez diagramas é pior para quem confere; só as duas juntas
dizem isso (2026-11-22: o v5 achava 181 de 181 e alarmava em 10 de 3.000).

**Cada imagem é lida uma vez**, e todos os leitores olham a mesma. Ler o teste para um leitor e depois
para outro mediria duas vezes o disco, e o detector clássico custa mais que o modelo.

Este módulo não importa Qt nem torch: o leitor do modelo chega pronto, como função.
"""

from __future__ import annotations

import json
import random
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import teste_de_marcas as tm
from .atomic_io import read_image

__all__ = [
    "AMOSTRAS_DE_ALARME",
    "Comparacao",
    "Leitor",
    "amostras_sem_anotacao",
    "anotadas_em",
    "comparar",
    "em_que_perde",
    "ler_rgb",
]

Leitor = Callable[[np.ndarray], Mapping[str, str]]
"""Recorte RGB -> `{"c6": "bolinha-branca"}`. O detector clássico e o modelo cabem nesta forma."""

AMOSTRAS_DE_ALARME = 1000
"""Quantas amostras sem anotação a janela lê para contar alarmes: ~3 min em CPU para três leitores. O
comando aceita mais (`--alarmes`), e as medições do PR #71 usaram 3.000."""


def ler_rgb(caminho: Path) -> np.ndarray | None:
    """A amostra em RGB, ou `None` quando o PNG não abre."""
    imagem = read_image(caminho)
    return None if imagem is None else cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)


def anotadas_em(anotacoes: Path) -> set[str]:
    """As amostras de `samples/` que têm anotação de marca: elas não contam como "sem marca"."""
    caminho = Path(anotacoes)
    if not caminho.exists():
        return set()
    imagens = json.loads(caminho.read_text(encoding="utf-8")).get("imagens", {})
    return {str(e.get("amostra")) for e in imagens.values() if isinstance(e, dict) and e.get("amostra")}


def amostras_sem_anotacao(
    splits: Mapping[str, object], fora: Iterable[str], quantas: int, semente: int = 42
) -> list[str]:
    """`quantas` amostras de validação e teste que não estão em `fora`, sorteadas com `semente`.

    Só validação e teste: o modelo de marcas treinou sobre as casas vazias do treino, e alarme ali seria
    medido sobre o que ele já viu como "sem marca". A mesma semente sorteia as mesmas amostras, e é isso
    que deixa comparar duas medições.
    """
    excluidas = set(fora)
    candidatas = sorted(
        nome for nome, particao in splits.items() if str(particao) in ("val", "test") and nome not in excluidas
    )
    return random.Random(semente).sample(candidatas, min(max(0, quantas), len(candidatas)))


@dataclass
class Leitura:
    """O que um leitor disse: no teste, por amostra; nos alarmes, só as amostras em que deu marca."""

    no_teste: dict[str, dict[str, str]] = field(default_factory=dict)
    apontadas: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class Comparacao:
    """Os leitores medidos na mesma régua."""

    casos: list[tm.CasoDeTeste]
    leituras: dict[str, Leitura]
    amostras_lidas: int = 0
    """Quantas amostras sem anotação abriram: o denominador dos alarmes."""
    cancelada: bool = False

    def placar(self, rotulo: str) -> tm.Placar:
        return tm.pontuar(self.casos, self.leituras[rotulo].no_teste)

    def alarmes(self, rotulo: str) -> int:
        """Em quantos diagramas sem anotação o leitor deu pelo menos uma marca."""
        return len(self.leituras[rotulo].apontadas)


def comparar(
    leitores: Mapping[str, Leitor],
    casos: Sequence[tm.CasoDeTeste],
    samples_dir: Path,
    amostras: Sequence[str] = (),
    *,
    cancelar: threading.Event | None = None,
    progresso: Callable[[int, int], None] | None = None,
) -> Comparacao:
    """Lê o teste e as `amostras` com todos os `leitores`, cada imagem uma vez.

    `progresso(feitas, total)` vem a cada imagem; `cancelar` é conferido entre imagens, e a comparação
    cancelada devolve o que leu até ali, marcada como tal -- um placar pela metade não é placar.
    """
    leituras = {rotulo: Leitura() for rotulo in leitores}
    comparacao = Comparacao(casos=list(casos), leituras=leituras)
    trabalho = [(caso.amostra, True) for caso in casos] + [(nome, False) for nome in amostras]
    for feitas, (nome, do_teste) in enumerate(trabalho, start=1):
        if cancelar is not None and cancelar.is_set():
            comparacao.cancelada = True
            break
        tabuleiro = ler_rgb(Path(samples_dir) / nome)
        if tabuleiro is not None:
            if not do_teste:
                comparacao.amostras_lidas += 1
            for rotulo, ler in leitores.items():
                casas = dict(ler(tabuleiro))
                if do_teste:
                    leituras[rotulo].no_teste[nome] = casas
                elif casas:
                    leituras[rotulo].apontadas[nome] = casas
        if progresso is not None:
            progresso(feitas, len(trabalho))
    return comparacao


def em_que_perde(comparacao: Comparacao, novo: str, base: str) -> list[str]:
    """As frases do que o leitor `novo` faz pior que `base`. Lista vazia é "não perde em nada".

    Três contas, as da régua: marcas reais achadas no teste, marcas inventadas no teste e diagramas
    sem anotação apontados. Uma só pior já basta para a janela pedir confirmação antes de instalar.
    """
    perdas: list[str] = []
    p_novo, p_base = comparacao.placar(novo), comparacao.placar(base)
    achadas_novo, achadas_base = sum(p_novo.acertos.values()), sum(p_base.acertos.values())
    if achadas_novo < achadas_base:
        perdas.append(f"acha {achadas_novo} marcas do teste, contra {achadas_base}")
    falsos_novo, falsos_base = sum(p_novo.falsos.values()), sum(p_base.falsos.values())
    if falsos_novo > falsos_base:
        perdas.append(f"inventa {falsos_novo} marcas no teste, contra {falsos_base}")
    alarmes_novo, alarmes_base = comparacao.alarmes(novo), comparacao.alarmes(base)
    if alarmes_novo > alarmes_base:
        perdas.append(f"aponta {alarmes_novo} diagramas sem anotação, contra {alarmes_base}")
    return perdas
