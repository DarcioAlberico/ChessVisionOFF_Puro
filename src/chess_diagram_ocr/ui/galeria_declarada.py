"""O que a aba Galeria mede, oferece e relata -- sem toolkit nenhum (S-67/S-120/S-154/S-503).

Quatro coisas, e nenhuma delas é widget:

1. **As medidas do leiaute** -- o lado do recorte, a largura da lateral e o piso que a aba de
   fato precisa. `LARGURA_MINIMA_DA_GALERIA` é somada das partes, e é o número que o painel
   esquerdo passou a ter de piso (S-154).
2. **O que a aba oferece** -- o tri-estado do link e as quatro ações que ela atende com o foco.
3. **A contabilidade da varredura em lote** -- `LivroVarrido`, `mesmo_arquivo` e as duas frases
   de relatório. É a parte que mais custa reescrever certo, e a que este módulo existe para não
   ter duas cópias.
4. **O aviso de quem não tem base**, um só, porque os dois botões dizem a mesma coisa.

**Por que a contabilidade é a parte perigosa.** `mesmo_arquivo` decide *duas* coisas -- se a fila
de revisão é alimentada e se a galeria recarrega no fim --, e errar para menos deixa a fila vazia
sem dizer por quê; errar para mais mistura livros na mesma fila. E `resumo_do_lote` é a única
linha que alguém lê depois de deixar o acervo varrendo por três horas: ela precisa distinguir
"pulado", "parcial" e "erro", que é justamente a distinção que uma segunda implementação
simplifica sem perceber.

**Por que isso pede endereço próprio.** `ui/gallery_panel.py` importa `tkinter` **e** `PIL.ImageTk`
na primeira linha do corpo, e o segundo frontend precisa das quatro coisas e de widget nenhum.

`ui/gallery_panel.py` reexportava tudo o que está aqui, e saiu no corte do Tk (S-506). Quem
consome agora é `qt/painel_da_galeria.py`.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..gallery_scan import GalleryIndex
from ..games_db import DEFAULT_DATABASE_DIR
from ..logging_setup import onde_esta_o_rastro

__all__ = [
    "ACOES_PROPRIAS",
    "BOARD_VIEW_SIZE",
    "CAPTION_LINES",
    "LARGURA_DA_LATERAL",
    "LARGURA_MINIMA_DA_GALERIA",
    "LINK_CHOICES",
    "SEM_BASE",
    "LivroVarrido",
    "mesmo_arquivo",
    "resumo_do_lote",
]

BOARD_VIEW_SIZE = 420
"""Lado do recorte na tela. Fixo: a galeria é para percorrer, e um tamanho que muda a cada
diagrama faria a imagem pular sob o ponteiro a cada avanço."""

LARGURA_DA_LATERAL = 260
"""Largura reservada para a coluna "Headers do PGN", **medida** e não estimada (S-154).

O `winfo_reqwidth` da lateral montada é **240 px** em `ttk` puro e **246** sob o
`bootstrap-light` -- dez rótulos de campo, dez `Entry` de `width=26` e o `padding=8` do
`LabelFrame`, com o tema acrescentando 6 px de moldura. 260 é o maior dos dois com folga, e a
folga é o item: reservar o número exato de um tema deixa a coluna 6 px curta no outro, que é a
mesma família de defeito, menor.

`tests/test_ui_galeria_layout.py` compara este número com a medição de verdade -- acrescentar um
campo ao PGN sem mexer aqui falha o teste, em vez de voltar a cortar a coluna."""

FOLGA_DO_CORPO = 40
"""O que fica entre a lateral e o recorte, e nas bordas: `padx=(10, 0)` mais o `padding` do painel."""

LARGURA_MINIMA_DA_GALERIA = BOARD_VIEW_SIZE + LARGURA_DA_LATERAL + FOLGA_DO_CORPO
"""O que esta aba de fato precisa de largura, somado das partes (S-154).

**É este número que o painel esquerdo passou a ter de piso.** Os 420 de `LARGURA_MINIMA_ESQUERDA`
eram da S-31, de quando a Galeria não existia -- e a consequência estava fotografada: na posição
padrão do divisor sobravam ~680 px para 700 pedidos, e quem perdia era a lateral, porque o centro
já tinha tomado o espaço com `expand=True`. Campos cortados, "Copiar headers para to…" cortado, o
texto verde de procedência cortado."""

CAPTION_LINES = 8
"""Altura da legenda em linhas. O resto rola -- e **nada é cortado**.

Ela era um `Label` com `caption[:220]`, o que bastava enquanto ela fosse só pista de contexto.
Deixou de bastar quando o texto passou a ser matéria-prima: o que se copia de uma legenda truncada
é uma legenda truncada, e o pedaço que falta costuma ser justamente o nome do segundo jogador ou o
ano."""

LINK_CHOICES: tuple[tuple[str, str], ...] = (("padrão", ""), ("com link", "sim"), ("sem link", "não"))
"""Tri-estado na tela, igual ao do arquivo. "padrão" é o que a exportação decidir."""

ACOES_PROPRIAS: frozenset[str] = frozenset(
    {"diagrama_anterior", "proximo_diagrama", "primeira_pagina", "ultima_pagina"}
)
"""As ações globais que esta aba atende **enquanto tem o foco** (S-400).

Os quatro botões de navegação existem desde a S-88 e **nenhuma tecla chegava a eles**: `←` e `→`
continuavam sendo do painel de resultado, e o efeito era o mesmo que a S-281 mediu na sala de
estudo, só que sem nada na tela para denunciá-lo -- percorrer a galeria com a seta trocava,
invisivelmente, o diagrama selecionado da aba Resultado, e o `Ctrl+S` seguinte gravava outro.

É a mesma resposta da sala: não são teclas novas, é a mesma tecla com destino conforme o foco.
`Home` e `End` seguem os botões |◀ e ▶| desta aba, que é o primeiro e o último diagrama do livro."""

SEM_BASE = (
    f"Nenhum arquivo .pgn em {DEFAULT_DATABASE_DIR}.\n\n"
    "A base é sua e fica fora do repositório -- ponha um .pgn nessa pasta. Pode ser mais de um: "
    "desde a S-93 todos os .pgn da pasta entram nas buscas."
)
"""O aviso de quem não tem base. Um só, porque os dois botões dizem a mesma coisa -- e duas cópias
do mesmo texto divergem na primeira vez que uma delas for corrigida."""


@dataclass
class LivroVarrido:
    """O que a varredura de um livro produziu, ou por que ela não aconteceu.

    Os três campos são mutuamente exclusivos, e é de propósito que sejam três e não um estado:
    "pulado" e "falhou" contam histórias diferentes no relatório, e um `indice=None` sozinho não
    distinguiria as duas. É o mesmo `BookResult` do `cvoff-scan`, na versão que a janela precisa.
    """

    path: Path
    indice: GalleryIndex | None = None
    pulado: str = ""
    erro: Exception | None = None

    @property
    def resumo(self) -> str:
        if self.erro is not None:
            return f"{self.path.name}: erro — {self.erro}"
        if self.pulado:
            return f"{self.path.name}: pulado — {self.pulado}"
        indice = self.indice
        parcial = "" if indice is None or indice.complete else " (parcial)"
        return f"{self.path.name}: {len(indice or ())} diagrama(s){parcial}"


def mesmo_arquivo(um: Path | None, outro: Path | None) -> bool:
    r"""O mesmo PDF, apesar de `..`, de barra invertida e de maiúsculas no Windows.

    Comparar `Path` cru diria que `PDF/livro.pdf` e `C:\...\PDF\Livro.pdf` são livros
    diferentes -- e é dessa comparação que dependem *duas* decisões: se a fila de revisão é
    alimentada, e se a galeria recarrega no fim. Errar para menos deixa a fila vazia sem dizer por
    quê; errar para mais mistura livros na mesma fila.
    """
    if um is None or outro is None:
        return False
    try:
        return os.path.normcase(Path(um).resolve()) == os.path.normcase(Path(outro).resolve())
    except OSError:  # pragma: no cover - caminho que o sistema recusa resolver
        return os.path.normcase(str(um)) == os.path.normcase(str(outro))


def resumo_do_lote(resultados: Sequence[LivroVarrido], *, pedidos: int) -> str:
    """A linha única que conta o lote inteiro: varridos, parciais, pulados, com erro e faltando.

    **É a única coisa que alguém lê depois de deixar o acervo varrendo por três horas**, e as
    quatro distinções são o item: "pulado por índice já completo" é trabalho poupado, "parcial" é
    trabalho a continuar, "com erro" é trabalho perdido, e "sem varrer" é o que o cancelamento
    deixou para trás. Um contador único diria o número certo e nenhuma das quatro coisas.

    `pedidos` é quantos livros o escopo tinha; a diferença para `resultados` é o que a varredura
    cancelada não alcançou.
    """
    feitos = [item for item in resultados if item.indice is not None]
    pulados = [item for item in resultados if item.pulado]
    erros = [item for item in resultados if item.erro is not None]
    parciais = [item for item in feitos if item.indice is not None and not item.indice.complete]
    diagramas = sum(len(item.indice or ()) for item in feitos)

    partes = [f"{len(feitos)} livro(s) varrido(s), {diagramas} diagrama(s)"]
    if parciais:
        partes.append(f"{len(parciais)} parcial(is) — varrer de novo continua de onde parou")
    if pulados:
        partes.append(f"{len(pulados)} pulado(s) por índice já completo")
    if erros:
        partes.append(f"{len(erros)} com erro -- {onde_esta_o_rastro()}")
    if faltaram := pedidos - len(resultados):
        partes.append(f"cancelada com {faltaram} livro(s) sem varrer")
    return "; ".join(partes)
