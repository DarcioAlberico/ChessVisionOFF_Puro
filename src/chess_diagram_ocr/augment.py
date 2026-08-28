"""Aumento de dados dirigido ao acervo (S-40).

**O que o aumento era.** `training.build_train_transform` fazia
`GaussianBlur + ColorJitter + RandomAffine(2°)`: um conjunto genérico e razoável que não
contém **nenhuma** das degradações que os livros deste acervo têm.

**E a S-39 mostrou que essa metade importa mais do que parecia.** Tentar limpar a imagem na
inferência não funcionou -- campo plano e CLAHE não mudam nada porque o `ColorJitter` já
ensinou o modelo a ignorá-los, e a supressão de trama destrói a peça junto com a hachura,
por dois métodos independentes (docs/EXPERIMENTS_FASE7.md). Sobrou o caminho inverso:
**o treino tem de ver hachura.**

O resultado negativo da S-39 também é a evidência a favor deste módulo. Ele prova que o
modelo *aprende invariância quando o aumento a ensina* -- foi exatamente isso que o
`ColorJitter` fez com brilho e contraste, a ponto de tornar duas etapas de normalização
inúteis.

**O erro concreto a consertar**, medido no `Euwe Band 1-2` p25: o modelo lê as três
primeiras filas corretamente (`r4rk1/pp3ppp/2n1q3`) e confunde **bispo branco com peão
branco em casa hachurada**. Não é "o tabuleiro é ilegível" -- é uma confusão de classe num
contexto de fundo específico.

**Tudo aqui é `nn.Module` piclável, e isso não é estilo.** No Windows o `DataLoader` com
`num_workers > 0` usa `spawn`, e a pipeline inteira é pickleada para cada worker. Uma
`lambda` aqui faria o carregamento paralelo da S-26 falhar com `PicklingError` num ponto do
código que não tem nada a ver com paralelismo -- foi por isso que `_clamp01` existe.

**Sobre o espelhamento horizontal.** É a única transformação deste módulo cuja validade
depende do domínio, e ela é válida: o classificador decide *casa → peça*, e um cavalo
espelhado continua sendo um cavalo. Dobra o dataset de graça, e é a mais barata das oito.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AugmentConfig:
    """Probabilidade de cada degradação. `0.0` desliga.

    Os defaults são o **conjunto genérico de antes da S-40**, para que `AugmentConfig()`
    continue reproduzindo o treino que produziu o checkpoint atual. Ligar as dirigidas muda
    o modelo, e é a grade da S-40 que decide quais valem -- não o gosto de quem escreveu.
    """

    # --- o que já existia
    blur: float = 0.30
    jitter: float = 1.0
    affine: float = 1.0

    # --- dirigidas ao acervo, desligadas até a medição dizer o contrário
    hflip: float = 0.0
    hatch: float = 0.0
    speckle: float = 0.0
    paper: float = 0.0
    invert: float = 0.0

    hatch_period_px: tuple[int, int] = (4, 12)
    """Período da hachura em pixels da **casa** (64×64 na entrada do modelo).

    Medido no acervo: a hachura do `Euwe` tem ~12,5 px numa casa de 100 px no tabuleiro de
    800, o que dá ~8 px numa casa reamostrada para 64. A faixa cobre isso com folga dos dois
    lados, porque outros livros hachuram mais fino."""

    @property
    def version(self) -> str:
        """Identidade do regime de aumento, para os metadados do checkpoint.

        Sem isto, "o modelo A é melhor que o B" pode estar comparando dois regimes de
        aumento -- que é a mesma armadilha que a S-27 fechou para arquitetura e semente.

        **E ela estava meio aberta (S-376).** Só as cinco dirigidas entravam na assinatura:
        `AugmentConfig(jitter=0.0)` e `AugmentConfig()` -- dois regimes que treinam modelos
        diferentes -- saíam ambos como `aug0`, e o checkpoint não guardava nada que os
        separasse. Quem só usa os padrões não vê diferença nenhuma: a assinatura antiga é a
        que continua saindo, e o sufixo só aparece quando algum genérico sai do padrão.
        """
        ativos = "".join(
            letra
            for letra, valor in (
                ("m", self.hflip),
                ("h", self.hatch),
                ("s", self.speckle),
                ("p", self.paper),
                ("i", self.invert),
            )
            if valor > 0.0
        )
        base = f"aug{ativos}" if ativos else "aug0"

        padrao = {campo.name: campo.default for campo in fields(self)}
        fora_do_padrao = "".join(
            f"{letra}{getattr(self, nome):g}"
            for letra, nome in (("b", "blur"), ("j", "jitter"), ("a", "affine"))
            if getattr(self, nome) != padrao[nome]
        )
        if self.hatch > 0.0 and self.hatch_period_px != padrao["hatch_period_px"]:
            fora_do_padrao += "t{}x{}".format(*self.hatch_period_px)
        return f"{base}-{fora_do_padrao}" if fora_do_padrao else base


DEFAULT_AUGMENT = AugmentConfig()


class _Sometimes(nn.Module):
    """Aplica a transformação com probabilidade `p`, usando o RNG do torch.

    O RNG do torch e não o `random` do stdlib: `training.set_seed` semeia os três, mas só o
    do torch é semeado por worker pelo `DataLoader`. Com `random`, dois workers aplicariam a
    mesma sequência de degradações.
    """

    def __init__(self, p: float) -> None:
        super().__init__()
        self.p = float(p)

    def _should(self) -> bool:
        return self.p >= 1.0 or (self.p > 0.0 and bool(torch.rand(()) < self.p))


class RandomHorizontalFlipCell(_Sometimes):
    """Espelha a casa. Rótulo-preservante: um cavalo espelhado continua sendo um cavalo."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.flip(x, dims=[-1]) if self._should() else x


class RandomHatch(_Sometimes):
    """Sobrepõe listras diagonais escuras, como as casas do `Euwe Band 1-2` (1956).

    Gerada por `sin` sobre a soma das coordenadas em vez de linhas desenhadas: sai
    diferenciável, sem `cv2` no meio do `DataLoader`, e o período e a fase variam de graça.
    Só escurece (`x * (1 - amplitude * faixa)`) porque é isso que tinta sobre papel faz.
    """

    def __init__(self, p: float, period_px: tuple[int, int] = (4, 12)) -> None:
        super().__init__(p)
        self.period_px = period_px

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if not self._should():
            return x

        altura, largura = x.shape[-2], x.shape[-1]
        baixo, alto = self.period_px
        periodo = float(torch.randint(baixo, alto + 1, ()).item())
        fase = float(torch.rand(()) * 2 * torch.pi)
        # Sinal +1 ou -1: a hachura do acervo aparece nas duas diagonais.
        sentido = 1.0 if bool(torch.rand(()) < 0.5) else -1.0
        amplitude = float(0.15 + 0.35 * torch.rand(()))

        linhas = torch.arange(altura, dtype=x.dtype, device=x.device).unsqueeze(1)
        colunas = torch.arange(largura, dtype=x.dtype, device=x.device).unsqueeze(0)
        onda = torch.sin((linhas + sentido * colunas) * (2 * torch.pi / periodo) + fase)
        faixa = (onda > 0).to(x.dtype)
        return x * (1.0 - amplitude * faixa)


class RandomSpeckle(_Sometimes):
    """Granulação de scan: ruído gaussiano mais sal-e-pimenta esparso."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if not self._should():
            return x
        sigma = float(0.01 + 0.05 * torch.rand(()))
        ruidoso = x + torch.randn_like(x) * sigma
        fracao = float(0.001 + 0.01 * torch.rand(()))
        sorteio = torch.rand_like(x)
        ruidoso = torch.where(sorteio < fracao / 2, torch.zeros_like(x), ruidoso)
        return torch.where(sorteio > 1.0 - fracao / 2, torch.ones_like(x), ruidoso)


class RandomPaper(_Sometimes):
    """Papel amarelado e iluminação desigual: ganho suave com gradiente linear.

    Multiplicativo e de baixa frequência de propósito -- é o que o `ColorJitter` **não**
    cobre. Ele muda brilho e contraste globais; aqui um canto fica mais escuro que o outro,
    que é o que um scanner de livro de 1956 faz.
    """

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if not self._should():
            return x
        altura, largura = x.shape[-2], x.shape[-1]
        ganho_base = float(0.75 + 0.2 * torch.rand(()))
        inclinacao = float(0.3 * (torch.rand(()) - 0.5))

        eixo_h = torch.linspace(0, 1, altura, dtype=x.dtype, device=x.device).unsqueeze(1)
        eixo_w = torch.linspace(0, 1, largura, dtype=x.dtype, device=x.device).unsqueeze(0)
        campo = ganho_base + inclinacao * (eixo_h + eixo_w) / 2.0
        return x * campo


class RandomInvert(_Sometimes):
    """Diagrama de contraste invertido. Raro no acervo, e barato de cobrir."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return 1.0 - x if self._should() else x


def _clamp01(x: torch.Tensor) -> torch.Tensor:
    return torch.clamp(x, 0.0, 1.0)


class Clamp01(nn.Module):
    """`_clamp01` como módulo: uma função de topo também é piclável, mas um `nn.Module`
    entra no `repr` do `Compose` e aparece nos metadados do checkpoint."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return _clamp01(x)


def build_augmentations(config: AugmentConfig = DEFAULT_AUGMENT) -> list[nn.Module]:
    """As degradações dirigidas ao acervo, na ordem em que uma página real as sofre.

    A ordem importa e não é arbitrária: o papel amarela **antes** de a tinta da hachura ser
    impressa em cima, e a granulação do scanner vem por último porque ela é do scanner, não
    da página. Inverter isso produziria uma hachura amarelada, que nenhum livro tem.
    """
    etapas: list[nn.Module] = []
    if config.hflip > 0:
        etapas.append(RandomHorizontalFlipCell(config.hflip))
    if config.invert > 0:
        etapas.append(RandomInvert(config.invert))
    if config.paper > 0:
        etapas.append(RandomPaper(config.paper))
    if config.hatch > 0:
        etapas.append(RandomHatch(config.hatch, config.hatch_period_px))
    if config.speckle > 0:
        etapas.append(RandomSpeckle(config.speckle))
    return etapas
