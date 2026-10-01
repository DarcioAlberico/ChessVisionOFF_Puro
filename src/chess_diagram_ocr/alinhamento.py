"""A régua de alinhamento do recorte: onde o damero ideal encaixa, em pixel (S-526).

**O que mede.** Um recorte sai reamostrado em `BOARD_SIZE` -- 800 px, 100 por casa. Num tabuleiro
alinhado, a máscara de damero ideal (casas claras e escuras alternadas num reticulado 8×8) encaixa
em (0, 0). Deslocando-a de −`ALCANCE_PX` a +`ALCANCE_PX` nos dois eixos, o deslocamento em que as
duas paridades mais diferem é o desalinhamento do recorte, em pixel: 100 px é uma casa inteira, e
acima de `LIMITE_DE_DESALINHAMENTO_PX` a peça começa a cair na casa vizinha -- o erro que nenhuma
métrica de classificação separa de um erro do modelo, porque para o classificador uma casa é o que
o recorte diz que é.

**A primeira versão estava errada, e o retrato a desmentiu.** Ela procurava picos de energia de
borda por coluna; nestes livros as casas são cor sólida e as **peças** têm a borda mais forte, e
ela dizia 100% de desalinhados numa folha de contato de doze tabuleiros impecáveis. Fica registrado
porque o número errado quase virou um achado (revisão externa de 2026-09-01).

**Pura, e barata.** Imagem integral e 64 médias por deslocamento; os 49×49 deslocamentos custam
dezenas de milissegundos por recorte, o que cabe no censo (`cvoff-census`), que é o instrumento
que percorre o acervo -- e é lá que ela mora, ao lado de `texture`.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

__all__ = [
    "ALCANCE_PX",
    "FORCA_MINIMA",
    "LIMITE_DE_DESALINHAMENTO_PX",
    "SEM_DAMERO",
    "Encaixe",
    "encaixe_do_damero",
]

ALCANCE_PX = 24
"""Até onde a máscara é deslocada, em cada eixo e sentido.

Menos de meia casa (50 px) de propósito: a partir dali o damero deslocado de uma casa inteira
encaixa de novo, com as paridades trocadas, e a régua não teria como distinguir os dois."""

LIMITE_DE_DESALINHAMENTO_PX = 12
"""Acima disto o recorte conta como desalinhado: a peça começa a cair na casa vizinha."""

FORCA_MINIMA = 0.02
"""Abaixo disto não há damero para encaixar -- cor lisa, foto, moldura -- e a régua responde
`SEM_DAMERO` em vez de um deslocamento aleatório. É a diferença média entre as duas paridades
no melhor encaixe, em fração de 255: 0,02 são cinco níveis de cinza, o ruído de quantização de
um recorte reamostrado. Ver a calibração na spec da S-526."""

SEM_DAMERO = -1
"""O `desalinhamento_px` de quem não tem damero: distingue "alinhado" de "nada para alinhar"."""


@dataclass(frozen=True)
class Encaixe:
    """Onde o damero encaixou. `dx`/`dy` positivos: a grade do recorte está à direita/abaixo."""

    dx: int
    dy: int
    forca: float
    """Diferença média entre as paridades no melhor encaixe, em fração de 255."""

    @property
    def confiavel(self) -> bool:
        return self.forca >= FORCA_MINIMA

    @property
    def desalinhamento_px(self) -> int:
        """O maior dos dois eixos, ou `SEM_DAMERO`. É o número que o censo grava."""
        return max(abs(self.dx), abs(self.dy)) if self.confiavel else SEM_DAMERO

    @property
    def desalinhado(self) -> bool:
        return self.confiavel and self.desalinhamento_px > LIMITE_DE_DESALINHAMENTO_PX


def encaixe_do_damero(warped_rgb: np.ndarray, *, alcance: int = ALCANCE_PX) -> Encaixe:
    """Desliza o damero ideal sobre o recorte e devolve o melhor encaixe.

    Aceita RGB ou cinza. Recorte pequeno demais para oito casas de ao menos oito pixels devolve
    `Encaixe(0, 0, 0.0)`, que é "sem damero" -- e não levanta, porque o censo passa por aqui
    candidato a candidato e um glifo de 15 pt não pode custar a página.
    """
    cinza = cv2.cvtColor(warped_rgb, cv2.COLOR_RGB2GRAY) if warped_rgb.ndim == 3 else warped_rgb
    lado = int(min(cinza.shape[:2]))
    casa = lado // 8
    if casa < 8:
        return Encaixe(0, 0, 0.0)
    cinza = cinza[:lado, :lado]

    integral = cv2.integral(cinza.astype(np.float64))
    paridade = (np.indices((8, 8)).sum(axis=0) % 2) == 0
    bordas = casa * np.arange(9)

    melhor_forca, melhor_dx, melhor_dy = 0.0, 0, 0
    for dy in range(-alcance, alcance + 1):
        ys = np.clip(dy + bordas, 0, lado)
        altura = (ys[1:] - ys[:-1])[:, None]
        for dx in range(-alcance, alcance + 1):
            xs = np.clip(dx + bordas, 0, lado)
            largura = (xs[1:] - xs[:-1])[None, :]
            areas = altura * largura
            validas = areas > 0
            if not (validas & paridade).any() or not (validas & ~paridade).any():
                continue
            somas = (
                integral[ys[1:, None], xs[None, 1:]]
                - integral[ys[:-1, None], xs[None, 1:]]
                - integral[ys[1:, None], xs[None, :-1]]
                + integral[ys[:-1, None], xs[None, :-1]]
            )
            medias = somas / np.maximum(areas, 1)
            claras = medias[validas & paridade].mean()
            escuras = medias[validas & ~paridade].mean()
            forca = abs(float(claras) - float(escuras)) / 255.0
            if forca > melhor_forca:
                melhor_forca, melhor_dx, melhor_dy = forca, dx, dy
    return Encaixe(dx=melhor_dx, dy=melhor_dy, forca=melhor_forca)
