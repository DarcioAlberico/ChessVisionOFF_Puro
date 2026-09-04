"""O que a sala de estudo declara fora do widget (S-244/S-279/S-280/S-307/S-503).

**A tabela `comando -> método` é a parte que mais importa.** A janela gera as ligações a partir
dela: um comando novo da sala entra numa linha e chega ao menu, à paleta e às três peles sozinho.
Escrever `lambda p: p.promover_variante()` no arquivo da janela seria a segunda declaração do par,
e a primeira é esta -- que é onde os métodos estão. `comandos.acoes_fora_do_catalogo(COMANDOS_DA_ABA)`
tem de ser vazio, e é o critério de aceite da S-280.

**E ela vale para os dois frontends.** Os nomes de método são os mesmos dos dois lados justamente
porque a tabela é uma: um `qt/painel_de_estudo.py` que chamasse os métodos por outro nome exigiria
uma segunda tabela, e a segunda tabela é o lugar onde um comando some sem ninguém notar -- ele
continua no catálogo, continua no menu, e não faz nada.

**As seis constantes são medições**, e o docstring de cada uma carrega o número. `TAMANHO_MAXIMO_DE_PGN`
é a que mais custou: 5,2 MB de PGN custam 18,8 s e 220 MB de pico, e `pgn_database/` tem arquivos
de 8,6 GB e 10,3 GB.

**`cor_de_seta_por_modificador` é a decisão que o toolkit divide ao meio.** Qual modificador dá
qual cor é do Lichess e do Chess.com, e vale nos dois frontends; *como se lê o modificador* não é
-- no Tk são bits de `event.state`, com o Alt declarado em dois valores porque ele não é o mesmo em
Windows e em X11, e no Qt é um `enum`. A função pura recebe os três booleanos já extraídos.

`ui/study_panel.py` reexportava tudo o que está aqui, e saiu no corte do Tk (S-506). Quem consome
agora é `qt/painel_de_estudo.py`, `qt/painel_de_resultado.py`, `qt/tabuleiro_de_jogo.py` e
`qt/janela.py`.
"""

from __future__ import annotations

from enum import Enum

from ..estudo import Ancora, PosicaoDeEstudo
from . import comandos as _comandos
from . import estudo_lista as _lista

__all__ = [
    "ACOES_PROPRIAS",
    "CANDIDATOS_DO_MOTOR",
    "COMANDOS_DA_ABA",
    "LADO_AMPLIADO",
    "LADO_DO_RECORTE",
    "FRACAO_PADRAO_DO_TABULEIRO",
    "PAPEIS_COLADOS",
    "PARTIDAS_MAXIMAS_DE_PGN",
    "RECUO_POR_NIVEL",
    "TAMANHO_MAXIMO_DE_PGN",
    "Sincronia",
    "cor_de_seta_por_modificador",
    "decidir_sincronia",
    "posicao_de_estudo",
    "nags_oferecidos",
]

RECUO_POR_NIVEL = 18
"""Pixels de recuo por nível de variante na lista. O recuo satura em
`estudo_lista.NIVEL_MAXIMO_DE_RECUO`; a numeração, nunca.

**O recuo só passou a existir na tela na S-514.** Ele era aplicado num `<span>`, e o
`QTextDocument` **descarta** margem em elemento inline: o número estava certo, era lido, e não
pintava um pixel. Quem recua agora é o bloco -- ver `qt/painel_de_estudo._redesenhar_lista`."""

PAPEIS_COLADOS: frozenset[str] = frozenset({_lista.NUMERO, _lista.ABRE})
"""Trechos cujo espaço **não** pode quebrar linha: eles pertencem ao que vem depois (S-515).

`12.` e `Ba4` são dois trechos e um lance; `(` e o primeiro lance da variante, a mesma coisa.
Deixá-los quebrar põe o número no fim de uma linha e o lance no começo da seguinte, que é ilegível
em notação.

**Todo o resto quebra normalmente, e esse é o item.** A lista trocava *todo* espaço por `&nbsp;`,
e o `QTextEdit` -- cujo modo de fábrica é `WrapAtWordBoundaryOrAnywhere` -- ficava sem nenhuma
fronteira de palavra na linha: sem onde quebrar, ele quebrava **em qualquer lugar**. Medido em
2026-09-01 num documento de 240 px: `1. Nf3 Nc6 2. Nf3 N` / `c6 3. Nf3 Nc6 4. Nf`. Na foto de
760 px o defeito aparecia duas vezes na tela -- `O-O` saía como `O-` / `O`, e a frase do
comentário como `guard` / `am`."""

FRACAO_PADRAO_DO_TABULEIRO = 1.0
"""Que fração da coluna o tabuleiro da sala ocupa quando ninguém escolheu nada (S-518).

É o padrão de `AppState.board_zoom`, que existia sem leitor. **Fração e não pixel**: o teto de 560
px é herança do canvas de tamanho fixo do Tk, e numa janela grande ele deixava o resto da coluna
virar vazio -- medido em 41,5% da área do widget a 1250x1000, antes da S-507.

**É 1,0, e a folga não se perde nisso**: `BoardGeometry.fit` já desconta `margem_de_coordenada()`
antes de enquadrar, então "a coluna inteira" quer dizer a coluna menos a esteira que as coordenadas
ocupam. Um valor menor foi tentado e medido pior: a 900x800 dava 415 px de tabuleiro contra 455, e
a diferença virava vazio na aba cujo assunto é justamente o tabuleiro. Quem quiser menor tem o
`board_zoom` no `data/janela.json`."""

LADO_DO_RECORTE = 220
"""Lado máximo da miniatura do diagrama, em pixels (S-282).

Cerca de um terço do tabuleiro no arranjo padrão: grande o bastante para se conferir uma casa
duvidosa, pequeno o bastante para não disputar a coluna com o tabuleiro."""

LADO_AMPLIADO = 640
"""Lado máximo do recorte ampliado (S-282). Acima do que qualquer diagrama do acervo tem: os
recortes saem em ~400 px, e o teto existe só para o dia em que um livro traga uma prancha inteira."""

CANDIDATOS_DO_MOTOR = 3
"""Quantas linhas o motor devolve na análise contínua (S-286).

Três e não cinco: a quarta e a quinta de um motor a 800 ms já são ruído, e a pergunta de quem
estuda um livro quase nunca é qual é o melhor lance -- é se o lance que o livro dá está entre os
candidatos."""

TAMANHO_MAXIMO_DE_PGN = 20 * 1024 * 1024
"""O maior `.pgn` que o comando "Abrir PGN…" aceita, em bytes (S-307).

**Por que existe um teto.** `abrir_pgn` lia o arquivo inteiro para a memória na thread da janela, e
`pgn_database/` -- a pasta que `estudo_partidas.py` manda usar -- tem arquivos de 8,6 GB e 10,3 GB.
Medido: 5,2 MB de PGN custam 18,8 s e 220 MB de pico, o que dá ~3,5 min de janela congelada num
arquivo de 62 MB; nos de gigabytes o `read_text` levanta `MemoryError`, que **não** é `OSError` e
por isso escapava da guarda.

Vinte megabytes é o corte entre "coleção de um livro" e "base de partidas". A base grande não deixa
de ser consultável: quem a consulta é a busca por posição da S-73, que indexa em vez de carregar."""

PARTIDAS_MAXIMAS_DE_PGN = 5000
"""E um teto de partidas, para o arquivo pequeno com muita partida dentro.

O teto é **argumento** de `estudos_de_pgn`, e não constante lá dentro: o mesmo laço lê o arquivo da
sala, e um limite global truncaria em silêncio a sala de quem tem mais estudos que o teto -- perda
de análise humana, o oposto do que este item quer."""


COMANDOS_DA_ABA: dict[str, str] = {
    "estudo_do_diagrama": "load_from_recognized",
    "estudo_da_posicao_inicial": "load_initial_position",
    "virar_tabuleiro": "flip_board",
    "trocar_vez": "toggle_turn",
    "estudo_aplicar_fen": "apply_fen",
    "copiar_fen": "copy_fen",
    "salvar_estudo": "save_pgn",
    "lance_anterior": "undo_move",
    "proximo_lance": "redo_move",
    "inicio_da_linha": "go_to_start_of_line",
    "fim_da_linha": "go_to_end_of_line",
    "promover_variante": "promover_variante",
    "promover_a_principal": "promover_a_principal",
    "rebaixar_variante": "rebaixar_variante",
    "apagar_variante": "apagar_variante",
    "apagar_continuacao": "apagar_continuacao",
    "simbolo_do_lance": "escolher_simbolo",
    "dobrar_variantes": "alternar_dobra",
    "mostrar_diagrama": "alternar_recorte",
    "linha_do_livro": "jogar_a_linha_do_livro",
    "ir_para_a_pagina": "ir_para_a_pagina",
    "analisar_posicao": "analyse",
    "analise_continua": "alternar_analise_continua",
    "variante_do_motor": "variante_do_motor",
    "partidas_da_posicao": "partidas_da_posicao",
    "indexar_base": "indexar_base",
    "colar_estudo": "colar_estudo",
    "abrir_pgn": "abrir_pgn",
    "exportar_estudo_md": "exportar_estudo_md",
    "exportar_estudo_html": "exportar_estudo_html",
    "exportar_estudo_rtf": "exportar_estudo_rtf",
    "estudo_para_o_texto": "levar_para_o_texto",
    "modo_treino": "alternar_treino",
}
"""Comando do catálogo -> método desta aba (S-280).

**A janela gera as ligações desta tabela**, como faz com `texto_panel.COMANDOS_DA_ABA` desde a
S-240: um comando novo da sala entra aqui, numa linha, e chega ao menu, à paleta e às três peles
sozinho. Escrever `lambda p: p.promover_variante()` no `app_tkinter` seria a segunda declaração do
par comando-método, e a primeira é esta -- que é onde os métodos estão.

O nome do comando e o do método divergem em nove casos, e todos por bom motivo: os quatro de
navegação são `undo_move`/`redo_move`/`go_to_*_of_line` porque era assim antes do catálogo, e
`estudo_do_diagrama` é `load_from_recognized` porque o que ele carrega é o que o OCR leu.

`comandos.acoes_fora_do_catalogo(COMANDOS_DA_ABA)` tem de ser vazio, e é o critério de aceite da
S-280."""

class Sincronia(str, Enum):
    """O que "seguir o OCR selecionado" faz quando o painel de resultado muda (S-512)."""

    TROCA = "troca"
    """Outro diagrama: guardar o que estava aberto e ir para a outra mesa (S-270)."""

    ATUALIZA = "atualiza"
    """Mesmo diagrama, e o estudo ainda não tem lance: a correção de casa chega ao tabuleiro."""

    NADA = "nada"
    """Não mexer. É a resposta mais comum, e é ela que torna a ligação segura."""


def decidir_sincronia(aberta: Ancora, posicao: PosicaoDeEstudo, *, vazio: bool) -> Sincronia:
    """Se a sala deve seguir aquela posição, e como (S-512).

    **A ligação existia no Tk e caiu no porte.** `result_panel` chamava `on_sync_study` em três
    pontos e `app_tkinter` o repassava; a janela do Qt nunca ligou o fio, e a caixa "Seguir OCR
    selecionado" -- marcada de fábrica -- não seguia nada desde então.

    **Religá-la crua criaria outro defeito, e é por isso que esta função existe.** `_abrir` zera a
    pilha de desfazer da sala, e o sinal do painel de resultado dispara a **cada** atualização --
    inclusive a cada casa corrigida. Sem a guarda, corrigir uma casa apagaria o `Ctrl+Z` de quem
    estava analisando aquele mesmo diagrama.

    **Âncora inválida é `NADA`, e essa é a decisão menos óbvia das quatro.** Item de fila e amostra
    do dataset não têm par no livro: a âncora não identifica mesa, então "seguir" não sabe para
    onde ir -- e reabrir a cada atualização recomeçaria o estudo avulso em curso a cada tecla. O
    caminho para estudá-los continua sendo o botão "Carregar OCR atual", que é explícito e não
    passa por aqui.

    `vazio` é `Estudo.vazio()`, que já é a régua do que entra na `Sala`: sem lance, sem comentário,
    sem símbolo e sem seta. Um estudo assim não tem o que perder, então a posição de partida pode
    ser trocada por baixo dele; com um lance jogado, ela não pode -- o que existe ali é análise
    humana **sobre** aquela posição.
    """
    if not posicao.valida() or not posicao.ancora.valida:
        return Sincronia.NADA
    if posicao.ancora.chave() != aberta.chave():
        return Sincronia.TROCA
    return Sincronia.ATUALIZA if vazio else Sincronia.NADA


ACOES_PROPRIAS: frozenset[str] = frozenset(
    {"diagrama_anterior", "proximo_diagrama", "primeira_pagina", "ultima_pagina"}
)
"""As ações globais que esta aba atende **enquanto tem o foco** (S-244/S-281).

`←` é "diagrama anterior" em toda a janela e "lance anterior" aqui dentro; `Home` é "primeira página
do livro" e aqui é "início da linha". Não são teclas novas: é a mesma tecla com destino conforme o
foco, que é o que qualquer programa de xadrez faz.

**Isto substitui quatro `canvas.bind`.** A aba ligava `<Left>`, `<Right>`, `<Home>` e `<End>` no
canvas do tabuleiro, e as três consequências estão medidas na S-281: as teclas só funcionavam depois
de clicar no tabuleiro, não apareciam em lugar nenhum, e sombreavam as globais -- a docstring de
`shortcuts.owns_key` cita este arquivo pelo nome. O conserto de lá tornou a colisão inofensiva; este
é o conserto de não a ter."""


# ------------------------------------------------- a posição que a sala recebe (S-269)
#
# **O núcleo é um só e os adaptadores são dois**, e a divisão é a mesma de `linhas_de_fonte` na
# fita: montar a `PosicaoDeEstudo` é decisão -- qual é a posição do diagrama selecionado é
# justamente a pergunta que a S-269 corrigiu --, e *de onde sai o texto da FEN* é do toolkit. No
# Tk o estado vivo é o widget (`fen_var`); no Qt o estado é o modelo (`fen_edits`), e cada painel
# lê o seu antes de chamar isto.

def posicao_de_estudo(
    placement: str,
    vez: str,
    *,
    documento: str = "",
    pagina: int = -1,
    diagrama: int = -1,
    lance: int | None = None,
    titulo: str = "",
) -> PosicaoDeEstudo | None:
    """Monta a posição que a janela entrega ao painel, ou `None` quando não há diagrama.

    Mora aqui, e não no `app_tkinter`, porque é uma decisão e não uma montagem de widget: qual é a
    posição do diagrama selecionado é justamente a pergunta que a S-269 corrigiu, e ela tem de ser
    afirmável sem abrir janela.
    """
    limpo = str(placement or "").strip()
    if not limpo:
        return None
    posicao = PosicaoDeEstudo(
        placement=limpo,
        vez="b" if str(vez).lower().startswith("b") else "w",
        lance=lance,
        ancora=Ancora(documento=documento, pagina=pagina, diagrama=diagrama, titulo=titulo),
    )
    return posicao if posicao.valida() else None


def cor_de_seta_por_modificador(*, shift: bool, alt: bool, ctrl: bool) -> str:
    """A cor da seta pelo modificador segurado: nada, `Shift`, `Alt`, `Ctrl` (S-279).

    É a ordem do Lichess e do Chess.com, e a escolha é de reconhecimento e não de gosto: quem
    desenha seta num tabuleiro já aprendeu esse gesto em outro lugar.

    **Recebe booleanos, e não o evento**, porque é aí que os dois frontends divergem: no Tk os
    modificadores são bits de `event.state` -- com o Alt declarado em dois valores, porque ele não é
    o mesmo em Windows e em X11 --, e no Qt são um `enum` de `KeyboardModifier`. A tabela de
    prioridade é a mesma, e é ela que mora aqui.
    """
    if shift:
        return "red"
    if alt:
        return "blue"
    if ctrl:
        return "yellow"
    return "green"


def nags_oferecidos() -> tuple[int, ...]:
    """Os símbolos que o menu de anotação oferece: os de lance e os de posição, nessa ordem.

    Julgar o lance (`!`, `?`) e julgar a posição (`⩲`, `±`) são duas frases, e somam -- é por isso
    que os dois grupos aparecem juntos e a escolha de um não tira o outro.
    """
    from .. import estudo as estudo_mod

    return estudo_mod.NAGS_DE_LANCE + estudo_mod.NAGS_DE_POSICAO


_ = _comandos  # noqa: B018 - o catálogo que `COMANDOS_DA_ABA` cobre; ver `acoes_fora_do_catalogo`
