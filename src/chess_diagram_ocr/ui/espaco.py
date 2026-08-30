"""O espaço da janela resolvido, e curto o bastante para caber dentro de um `pack` (S-447).

**O que havia antes.** `ui/tipografia.py` declarava os quatro papéis de folga desde a S-232 --
`FOLGA_DE_MOLDURA` 14, `FOLGA` 10, `FOLGA_DE_LINHA` 6, `FOLGA_MINIMA` 2 -- dizendo por escrito que
"são os números que já estão na janela, e não uma escala nova". E a adoção era de **quatro
chamadas**, as quatro no cromo. Dentro dos sete painéis a escala não era usada uma vez: eram
literais, 285 deles, com oito valores distintos onde a escala tem quatro.

**Por que este módulo existe, e não `tipografia.folga` direto.** A função de lá pede `base` e
`densidade` em toda chamada, porque ela é **pura** e não pode adivinhar nenhum dos dois -- é o que
permite afirmar a escala inteira sem abrir janela. Num `pack` isso vira

    padx=tipografia.folga(tipografia.FOLGA_DE_LINHA, base=theme.fonte_base()[0], densidade=...)

para dizer `padx=6`, e o painel passaria a precisar saber de densidade, que não é assunto dele.
Aqui a pergunta fica `padx=espaco.linha()`, e quem responde guarda a fonte e a densidade em vigor.

**Quem fixa as duas é `theme.registrar_estilos`**, no mesmo ponto em que ela aplica a folha de base
da S-441 -- e pela mesma razão: é a função que roda a cada tema, a cada pele e a cada troca de
densidade, então é o único lugar onde as duas são conhecidas sem que ninguém as passe adiante.

---

**O alcance da densidade, medido, e ele não é o que a spec prometia.** A `SPEC_ACABAMENTO.md`
pedia que "a densidade compacta encolha o interior dos sete painéis, e não só o cromo". Isso **não
acontece na troca em execução**, e a razão é estrutural: `padx`/`pady` são opções de `pack`, fixadas
quando o widget é empacotado, e `app_tkinter.remontar_cromo` -- que é o que a troca de densidade
chama -- diz no próprio docstring que "refaz o cromo **sem tocar o conteúdo**". Os sete painéis não
são remontados, e opção de `pack` não se reaplica sozinha.

O que este módulo entrega, então, é o outro lado do item, que é o durável: **o espaço do interior
passa a derivar da fonte do sistema**. Quem aumenta a fonte do Windows ganha vão proporcional em
vez de pixel cravado -- exatamente o argumento com que a S-149 derivou os tamanhos de letra. E a
densidade escolhida alcança o interior **na abertura seguinte**, porque ela é gravada no estado.
"""

from __future__ import annotations

from . import pele, tipografia

__all__ = [
    "ajustar",
    "folga",
    "linha",
    "minima",
    "moldura",
    "vigente",
]

_base: int = tipografia.BASE_DE_REFERENCIA
_densidade: str = pele.CONFORTAVEL


def ajustar(*, base: int, densidade: str) -> None:
    """Fixa a fonte e a densidade contra as quais os quatro papéis passam a resolver.

    Levanta `KeyError` para densidade desconhecida -- e levanta **antes** de guardar, para que uma
    chamada errada não deixe o módulo num estado meio trocado. Quem chama é
    `theme.registrar_estilos`; um painel que chamasse isto estaria decidindo densidade, que é
    escolha da pessoa (S-232).
    """
    tipografia.folga(tipografia.FOLGA, base=base, densidade=densidade)
    global _base, _densidade
    _base, _densidade = base, densidade


def vigente() -> tuple[int, str]:
    """`(base, densidade)` em vigor. Existe para o teste afirmar o que foi fixado."""
    return _base, _densidade


def moldura() -> int:
    """A moldura interna de um diálogo ou de um grupo. `14` na base de referência."""
    return tipografia.folga(tipografia.FOLGA_DE_MOLDURA, base=_base, densidade=_densidade)


def folga() -> int:
    """O vão de um bloco contra a borda que o contém. `10` na base de referência."""
    return tipografia.folga(tipografia.FOLGA, base=_base, densidade=_densidade)


def linha() -> int:
    """De uma linha de controles para a seguinte. `6` na base de referência."""
    return tipografia.folga(tipografia.FOLGA_DE_LINHA, base=_base, densidade=_densidade)


def minima() -> int:
    """Entre dois vizinhos do mesmo grupo. `2` na base de referência, e o piso é 1.

    O piso não é detalhe: dois botões colados viram um controle só para o olho, e a densidade
    compacta existe para caber, não para fundir -- está escrito em `tipografia.FOLGA_MINIMA`.
    """
    return tipografia.folga(tipografia.FOLGA_MINIMA, base=_base, densidade=_densidade)
