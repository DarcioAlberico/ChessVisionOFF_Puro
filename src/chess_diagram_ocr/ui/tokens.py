"""A paleta do produto, num lugar só — papéis semânticos, não hexadecimais (S-145).

**O que havia antes.** 25 cores cravadas em 8 arquivos, sem lugar onde a paleta existisse
inteira. As consequências foram medidas, não supostas:

- **três verdes com três significados de "bom"**: `#00c07a` "já salvo" no visualizador,
  `#2e7d32` "veio da base" na Galeria, e o `success` do tema (`#146c43`) que ninguém usava;
- **dois cinzas** para o mesmo papel de texto secundário, `#555555` em três arquivos e
  `#666666` num quarto;
- nenhuma delas passava pelo `Style`, então nenhuma respondia a troca de tema.

**Duas camadas, e a separação é o item.** Em cima, os **papéis**: o painel pede `PRONTO` ou
`TEXTO_SECUNDARIO` e nunca um hexadecimal. Embaixo, a **resolução**: dado o `Style` em uso,
o papel vira cor — preferindo o token do tema quando existe, e caindo na reserva quando não.

**Sem `tkinter` aqui.** O módulo recebe um objeto com `.lookup(...)` e não sabe de onde ele
veio; é o que permite testar a paleta inteira sem abrir janela, e é a mesma disciplina do
`board_render`, que desenha sem widget.

**A regra de cor-de-marcação contra cor-de-texto (S-146).** Um verde que serve de borda de
retângulo sobre a página **não** serve de texto sobre branco: a razão de contraste que importa
é outra em cada caso. Por isso `PRONTO` e `PRONTO_TEXTO` são dois papéis, e não um com dois
usos — ver `razao_de_contraste`, que é o instrumento que decide.
"""

from __future__ import annotations

from typing import Protocol

__all__ = [
    "PAPEIS",
    "RESERVA",
    "cor",
    "paleta",
    "razao_de_contraste",
    "sobre_superficie",
]


class Estilo(Protocol):
    """O mínimo que este módulo usa de um `ttk.Style`. Existe para não importar `tkinter`."""

    def lookup(self, layout: str, option: str) -> object: ...


# --------------------------------------------------------------------------- os papéis

TEXTO_SECUNDARIO = "TEXTO_SECUNDARIO"
"""Texto de apoio: contagem, material, linha do motor. Um cinza, não dois."""

PRONTO = "PRONTO"
"""**Marcação** de "este diagrama já rendeu amostra". Borda de retângulo sobre a página."""

PRONTO_TEXTO = "PRONTO_TEXTO"
"""O mesmo significado, como **texto**. Cor diferente por obrigação, não por gosto (S-146)."""

A_FAZER = "A_FAZER"
"""Marcação de "o detector achou isto aqui" — localizado e ainda não lido."""

LIDO = "LIDO"
"""Marcação de "o OCR já leu este" — lido e ainda não salvo."""

DISPENSADO = "DISPENSADO"
"""Marcação de "a base reconheceu, não precisa de olho nenhum" (S-75)."""

ATENCAO = "ATENCAO"
PROBLEMA = "PROBLEMA"
"""Casa culpada, posição ilegal, ação destrutiva."""

DIVERGENTE = "DIVERGENTE"
"""Casa em que duas leituras discordam (a 2ª opinião da S-66)."""

CORRIGIDO = "CORRIGIDO"
"""**Marcação** de casa que o humano reescreveu em relação ao que o modelo leu."""

CORRIGIDO_TEXTO = "CORRIGIDO_TEXTO"
"""O mesmo azul, como **texto** -- a procedência "veio do diagrama vizinho" na lista de partidas.

O par existe pelo mesmo motivo de `PRONTO`/`PRONTO_TEXTO`, e foi o próprio teste da S-146 que o
exigiu: o `#3d7dd4` da borda dá **3,63:1** como texto, abaixo do piso AA. A spec da S-146 listou
dois pares reprovados; este é um terceiro, e apareceu porque a paleta passou a ter instrumento."""

SUPERFICIE_PAGINA = "SUPERFICIE_PAGINA"
"""O fundo do canvas do visualizador de PDF."""

SUPERFICIE_TABULEIRO = "SUPERFICIE_TABULEIRO"
"""O fundo do canvas do tabuleiro do Resultado."""

SUPERFICIE_ESTUDO = "SUPERFICIE_ESTUDO"
"""O fundo do canvas do tabuleiro de Análise, que é escuro."""

SUPERFICIE_DICA = "SUPERFICIE_DICA"
"""O amarelo pálido do tooltip e da caixa de ajuda."""

MOLDURA = "MOLDURA"
"""A borda desenhada em volta do tabuleiro."""

COORDENADA = "COORDENADA"
"""As letras a–h e os números 8–1. **Resolvida contra a superfície** — ver `sobre_superficie`."""

CASA_CLARA = "CASA_CLARA"
CASA_ESCURA = "CASA_ESCURA"
CASA_SELECIONADA = "CASA_SELECIONADA"
CASA_ULTIMO_LANCE = "CASA_ULTIMO_LANCE"
ALVO = "ALVO"
"""A identidade do tabuleiro. Não segue tema: xadrez impresso é claro-e-escuro em qualquer
tema, e um tabuleiro que muda de cor com a janela deixa de ser reconhecível como tabuleiro."""

TEXTO_SOBRE_MARCACAO = "TEXTO_SOBRE_MARCACAO"
"""O número dentro do retângulo do diagrama, e o rótulo sobre a casa. Escuro, sobre marcação."""

SELECAO = "SELECAO"
"""O tracejado da seleção de área, desenhado sobre a página renderizada."""

TEXTO_PADRAO = "TEXTO_PADRAO"
SUPERFICIE_PADRAO = "SUPERFICIE_PADRAO"
"""A reserva de quando o próprio `Style` não responde.

Elas existem porque `board_widget` pergunta ao tema a cor de texto e de fundo para desenhar a
paleta de peças dentro de um canvas -- e um `Style` de tema exótico devolve string vazia. Sem
elas o `or "#000000"` ficava cravado no painel, que é o que este módulo veio tirar."""


PAPEIS: tuple[str, ...] = (
    TEXTO_SECUNDARIO,
    PRONTO,
    PRONTO_TEXTO,
    A_FAZER,
    LIDO,
    DISPENSADO,
    ATENCAO,
    PROBLEMA,
    DIVERGENTE,
    CORRIGIDO,
    CORRIGIDO_TEXTO,
    SUPERFICIE_PAGINA,
    SUPERFICIE_TABULEIRO,
    SUPERFICIE_ESTUDO,
    SUPERFICIE_DICA,
    MOLDURA,
    COORDENADA,
    CASA_CLARA,
    CASA_ESCURA,
    CASA_SELECIONADA,
    CASA_ULTIMO_LANCE,
    ALVO,
    TEXTO_SOBRE_MARCACAO,
    SELECAO,
    TEXTO_PADRAO,
    SUPERFICIE_PADRAO,
)
"""Todos os papéis. A tupla existe para o teste poder afirmar que a resolução é **total**."""


RESERVA: dict[str, str] = {
    TEXTO_SECUNDARIO: "#555555",
    PRONTO: "#00c07a",
    PRONTO_TEXTO: "#146c43",
    A_FAZER: "#4da3ff",
    LIDO: "#ffb02e",
    DISPENSADO: "#9b7bff",
    ATENCAO: "#8a5a00",
    PROBLEMA: "#c0392b",
    DIVERGENTE: "#8e44ad",
    CORRIGIDO: "#3d7dd4",
    CORRIGIDO_TEXTO: "#1565c0",
    SUPERFICIE_PAGINA: "#1c1c1c",
    SUPERFICIE_TABULEIRO: "#f2f2f2",
    SUPERFICIE_ESTUDO: "#262421",
    SUPERFICIE_DICA: "#ffffe0",
    MOLDURA: "#312e2b",
    COORDENADA: "#5c5c5c",
    CASA_CLARA: "#f0d9b5",
    CASA_ESCURA: "#b58863",
    CASA_SELECIONADA: "#f7ec74",
    CASA_ULTIMO_LANCE: "#cdd26a",
    ALVO: "#3f7f4c",
    TEXTO_SOBRE_MARCACAO: "#101010",
    SELECAO: "#00ff88",
    TEXTO_PADRAO: "#000000",
    SUPERFICIE_PADRAO: "#f0f0f0",
}
"""O valor de cada papel quando não há tema a consultar.

**Reserva e não padrão**: num `Tk` sem `ttkbootstrap` a janela abre com estas cores, e é o
mesmo contrato de degradação que `ui/theme.py` promete desde a S-53 — aparência não derruba
ferramenta.

Duas entradas mudaram de valor em relação ao que estava cravado, e as duas por medição (S-146):
`COORDENADA` era `#d8d8d8`, que sobre `SUPERFICIE_TABULEIRO` dá **1,27:1** — desenhado e
ilegível; e `ATENCAO` ganhou um âmbar escuro porque o `#ffb02e` da marcação reprova como texto.
"""


_DO_TEMA: dict[str, tuple[str, str]] = {
    PRONTO_TEXTO: ("success.TLabel", "foreground"),
    PROBLEMA: ("danger.TLabel", "foreground"),
    TEXTO_SECUNDARIO: ("secondary.TLabel", "foreground"),
}
"""Papéis que o tema responde melhor que a reserva, e onde perguntar.

**Só três, e de propósito.** O resto ou é identidade do tabuleiro (que não segue tema) ou é
marcação sobre a página renderizada, onde o fundo é a página e não o tema — perguntar ao
`Style` ali devolveria uma cor pensada para outro fundo.
"""


def cor(papel: str, style: Estilo | None = None) -> str:
    """O hexadecimal de um papel. `style=None` devolve a reserva.

    Levanta `KeyError` para papel desconhecido, em vez de devolver um cinza: um papel escrito
    errado que resolvesse para *alguma* cor viraria um widget de cor plausível e sem
    significado, que é exatamente o estado de que este módulo veio tirar o projeto.
    """
    if papel not in RESERVA:
        raise KeyError(f"papel de cor desconhecido: {papel!r}. Os válidos estão em PAPEIS.")
    if style is not None and papel in _DO_TEMA:
        layout, opcao = _DO_TEMA[papel]
        try:
            do_tema = style.lookup(layout, opcao)
        except Exception:  # noqa: BLE001 - Style de tema exótico pode levantar; a reserva serve
            do_tema = None
        texto = str(do_tema or "").strip()
        if texto.startswith("#") and len(texto) == 7:
            return texto.lower()
    return RESERVA[papel]


def paleta(style: Estilo | None = None) -> dict[str, str]:
    """A paleta inteira resolvida. É o que o teste percorre para afirmar totalidade."""
    return {papel: cor(papel, style) for papel in PAPEIS}


# ------------------------------------------------------------------- contraste (S-146)


def _canal(valor: float) -> float:
    return valor / 12.92 if valor <= 0.03928 else ((valor + 0.055) / 1.055) ** 2.4


def _luminancia(hexadecimal: str) -> float:
    texto = hexadecimal.lstrip("#")
    if len(texto) != 6:
        raise ValueError(f"cor precisa ser #rrggbb; recebido {hexadecimal!r}")
    r, g, b = (int(texto[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.2126 * _canal(r) + 0.7152 * _canal(g) + 0.0722 * _canal(b)


def razao_de_contraste(a: str, b: str) -> float:
    """A razão WCAG 2.1 entre duas cores, entre 1,0 e 21,0. Simétrica.

    É o instrumento da S-146, e ele mora aqui porque a S-145 é quem declara os pares: um par
    que reprova é um defeito da paleta, não do painel que a usou.

    Âncoras conhecidas, que os testes afirmam: `#000000`/`#ffffff` = 21,0 e `#777777`/`#ffffff`
    = 4,48 — o cinza que fica logo abaixo do piso AA de 4,5.
    """
    la, lb = _luminancia(a), _luminancia(b)
    clara, escura = max(la, lb), min(la, lb)
    return (clara + 0.05) / (escura + 0.05)


AA_TEXTO = 4.5
"""Piso WCAG 2.1 AA para texto normal."""

AA_GRAFICO = 3.0
"""Piso para elemento gráfico -- borda, traço, ícone. É o que vale para as marcações."""


def sobre_superficie(superficie: str, *, claro: str = "#e8e8e8", escuro: str = "#5c5c5c") -> str:
    """A cor de coordenada legível **sobre a superfície em que ela vai ser desenhada** (S-146).

    O defeito que isto conserta: `COORDENADA` era uma constante `#d8d8d8`, escolhida para o
    tabuleiro escuro da Análise, e o Resultado desenha sobre `#f2f2f2`. Razão **1,27:1** — as
    letras a–h estavam na tela e não podiam ser lidas. Num programa cujo trabalho é dizer "o
    bispo está em c4", a régua que nomeia c4 era invisível.

    A escolha é a que der mais contraste contra aquele fundo, e o teste afirma o número dos
    dois lados — é o mesmo mecanismo que a Galeria já usava para o `tk.Text` da legenda, e que
    aqui faltou.
    """
    return claro if razao_de_contraste(claro, superficie) >= razao_de_contraste(escuro, superficie) else escuro
