"""A sugestão de marcas da conferência, quando dois leitores olham o mesmo recorte.

Os leitores são o detector clássico (`detector_de_marcas.py`, pela forma) e o modelo de marcas
(`modelo_de_marcas.py`). Medidos em 2026-11-22 no teste congelado e em 4.127 amostras sem anotação, o modelo
achou mais marcas e deu menos alarmes falsos; mesmo assim, **um não corrige o outro** (decisão de 2026-11-04):
com marca em ~0,15% dos diagramas, deixar um leitor apagar o que o outro viu é aceitar em silêncio o erro de
quem venceu.

**A regra.** Onde os dois dizem a mesma marca, ela é a sugestão. Onde só um diz, ou dizem marcas diferentes,
a casa entra na sugestão e vira discordância, que a tela mostra por extenso: quem confere decide. No tipo
diferente, a sugestão leva o do modelo, que errou menos tipo no teste; a frase da discordância diz os dois.

**Sugestão não é anotação.** Nada daqui muda a FEN nem o arquivo de marcas: só o "Aceitar a sugestão" da
conferência transforma a sugestão em anotação.

O módulo não importa Qt nem torch.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from . import marcas_de_casa as mc
from .config import PROJECT_ROOT

__all__ = ["MODELO_DE_MARCAS", "Opiniao", "descrever_discordancias", "juntar"]

MODELO_DE_MARCAS = PROJECT_ROOT / "models" / "marcas.pt"
"""O modelo de marcas que a conferência usa. Mora aqui, e não em `config.py`, que está no fecho de medição
(S-218): mudar `config.py` venceria os relatórios de campo por uma constante que nenhuma medição lê. Sem o
arquivo, a conferência sugere só pelo detector, como antes do modelo."""

NADA = "nada"
"""Como a frase da discordância diz que um leitor não viu marca na casa."""


@dataclass(frozen=True)
class Opiniao:
    """A sugestão para a tela e onde os leitores discordam."""

    casas: dict[str, str] = field(default_factory=dict)
    """`{"c6": "bolinha-branca"}`: o que aparece em fantasma no tabuleiro."""
    discordancias: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    """`casa -> (detector, modelo)`, com `None` onde o leitor não viu marca."""
    com_modelo: bool = False
    """Se o modelo de marcas leu este recorte. Sem ele, a sugestão é só a do detector, como antes dele."""


def juntar(detector: Mapping[str, str], modelo: Mapping[str, str] | None) -> Opiniao:
    """A sugestão dos dois leitores. `modelo=None` é o modelo ausente: vale o detector, sem discordância."""
    if modelo is None:
        return Opiniao(casas=dict(detector))
    casas: dict[str, str] = {}
    discordancias: dict[str, tuple[str | None, str | None]] = {}
    for casa in sorted(set(detector) | set(modelo)):
        do_detector, do_modelo = detector.get(casa), modelo.get(casa)
        casas[casa] = do_modelo if do_modelo is not None else str(do_detector)
        if do_detector != do_modelo:
            discordancias[casa] = (do_detector, do_modelo)
    return Opiniao(casas=casas, discordancias=discordancias, com_modelo=True)


def _nome(tipo: str | None) -> str:
    return NADA if tipo is None else mc.NOMES.get(tipo, tipo)


def descrever_discordancias(opiniao: Opiniao, casas: Mapping[str, object] | None = None) -> str:
    """A frase da tela: `"c6: modelo bolinha branca, detector nada"`. `casas` restringe às casas pendentes."""
    partes = [
        f"{casa}: modelo {_nome(do_modelo)}, detector {_nome(do_detector)}"
        for casa, (do_detector, do_modelo) in opiniao.discordancias.items()
        if casas is None or casa in casas
    ]
    return "; ".join(partes)
