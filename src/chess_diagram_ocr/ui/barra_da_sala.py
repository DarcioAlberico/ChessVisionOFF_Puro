"""A barra da sala de estudo como dado: grupos por tarefa, o que é principal e o que vai para "Mais" (S-527).

**O que havia, medido em 2026-09-04.** `qt/painel_de_estudo.py` montava três `BarraFluida` com 28
botões de texto (31 com motor), e a 715 px de largura -- a metade esquerda de uma janela de 1400 --
elas quebravam em **quatro fileiras**: 130 px de altura antes do tabuleiro, sem ícone, sem separador,
e "Apagar variante" a um botão de "Símbolo". Um enxadrista compara isso com o ChessBase (faixa
agrupada por tarefa, ícone com rótulo curto, o resto num menu) e com o Lichess (o que não é do momento
fica escondido).

**Três decisões, e as três moram aqui e não no widget.**

1. **O grupo é a tarefa, não o menu.** `comandos.GRUPOS` tem um grupo só para a sala inteira --
   `ESTUDO` --, porque ali a pergunta é *onde na barra de menus*. Aqui a pergunta é *o que a pessoa
   está fazendo*: montando a posição, editando a árvore, consultando o livro, consultando a base,
   pedindo ao motor, tirando o estudo daqui, treinando. São sete, e o separador da barra cai entre
   eles.
2. **Principal é frequência, e não importância.** É a régua de `comandos.fila_de_destaque`
   -- *"exporta-se uma vez por livro e salva-se uma vez por diagrama"*. O que se faz a cada lance
   fica na barra; o que se faz uma vez por sessão vai para "Mais", e continua a um clique. Nenhum
   comando sai da aba: `comandos.acoes_fora_do_catalogo(COMANDOS_DA_ABA)` continua vazio, e esta
   tabela cobre `COMANDOS_DA_ABA` inteira menos os quatro de navegação, que a S-517 já pôs sob o
   tabuleiro. **E dentro da fila há dois níveis** (segunda rodada, 2026-09-04): três botões com
   ícone e texto -- o primário, o interruptor do treino e o salvar -- e onze só com ícone, com o
   rótulo e a tecla na dica. É a hierarquia do ChessBase, e é o que faz a fila caber: com catorze
   rótulos só cinco ficavam a 714 px.
3. **Uma fila, sempre -- e é `cabem` quem decide quem fica nela.** A 715 px não cabem quinze
   botões com rótulo, e a S-151 mediu o que acontece quando uma barra esconde sem avisar: *"sem
   aviso, sem reticências"*. A saída não é quebrar (é o que as quatro fileiras faziam) nem cortar:
   é o botão que não cabe **ir para o "Mais"**, na ordem inversa da prioridade, e voltar quando a
   janela alarga. A decisão é pura, como `ui/barra.arranjo`; o widget mede e executa.

**O ícone não entra pelo catálogo, e isso é decisão.** `medidas_da_fita.grupos()` põe na fita da
janela *todo* comando do catálogo que declare `icone` -- foi assim que os quatro de navegação
chegaram lá na S-520. Dar ícone aos trinta da sala pelo catálogo despejaria os trinta no cromo da
janela, ao lado de "Abrir PDF", que não é onde eles agem. O nome do traço fica **nesta** tabela, e
os traços novos em `icones.ICONES_DA_SALA`, que tem a sua própria ponte nos dois sentidos.

**Rótulo e tecla não são reescritos.** O curto é `comandos.rotulo_de_botao`, o longo é
`comandos.rotulo`, a tecla é `atalhos.acelerador`. Só o que o catálogo não tem -- o interruptor
"Seguir OCR", que era um `QCheckBox` com o texto escrito no widget, e os dois agrupadores "Exportar"
e "Mais" -- declara texto aqui, uma vez.

**A forma é de `ui/barra.py` desde a S-528.** `Acao`, `Item`, `cabem` e `dica_de` valem para
qualquer barra em fila, e o painel do PDF é a segunda; o que sobrou aqui é **a tabela da sala**.
Os nomes continuam alcançáveis por este módulo, que é por onde a sala e os testes dela os citam.

Nada de `PyQt6`: quem monta widget não decide, e quem decide é afirmável sem abrir janela.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import atalhos
from . import barra as _barra
from .barra import ICONE_DO_MAIS, MAIS, ROTULO_DO_MAIS, SEPARADOR_DA_TECLA, Item, cabem, dica_de
from .sala_declarada import COMANDOS_DA_ABA

__all__ = [
    "ACOES",
    "COM_ESTUDO",
    "EXPORTAR_ESTUDO",
    "GRUPOS",
    "ICONE_DO_MAIS",
    "MAIS",
    "METODOS_PROPRIOS",
    "MODOS",
    "NAVEGACAO",
    "ROTULO_DO_MAIS",
    "SEGUIR_OCR",
    "SEM_ESTUDO",
    "SEPARADOR_DA_TECLA",
    "TREINANDO",
    "Acao",
    "Item",
    "acao",
    "acoes_para",
    "cabem",
    "dica_de",
    "do_grupo",
    "grupos_desligados",
    "modo",
    "principais",
    "rotulo_do_grupo",
    "secundarias",
    "sequencia_de",
]

# ---------------------------------------------------------------------------------- os grupos

# Em minúsculas, e é o formato de `pele.CLASSICA` e de `abas.DATASET`: é chave, não texto de tela
# -- `test_strings` acusaria "POSICAO" como português sem acento, e teria razão se fosse rótulo.
POSICAO = "posicao"
VARIANTE = "variante"
LIVRO = "livro"
BASE = "base"
MOTOR = "motor"
EXPORTAR = "exportar"
TREINO = "treino"

GRUPOS: tuple[str, ...] = (POSICAO, VARIANTE, LIVRO, BASE, MOTOR, EXPORTAR, TREINO)
"""Os sete, na ordem da barra -- que é a ordem em que a pessoa os usa numa sessão de livro.

Monta-se a posição, edita-se a árvore, confere-se o livro e a base, pergunta-se ao motor, tira-se o
estudo daqui, e treinar é o que se faz com o estudo pronto. `MOTOR` só aparece quando há motor: sem
ele a seção inteira do painel não existe (S-33), e um grupo vazio com separador seria uma promessa."""

_ROTULOS_DE_GRUPO: dict[str, str] = {
    POSICAO: "Posição",
    VARIANTE: "Variante",
    LIVRO: "Livro",
    BASE: "Base",
    MOTOR: "Motor",
    EXPORTAR: "Exportar",
    TREINO: "Treino",
}
"""Como o grupo se escreve quando vira cabeçalho de seção no menu "Mais"."""

# ------------------------------------------------------------ o que o catálogo não declara

SEGUIR_OCR = "seguir_ocr"
"""O interruptor "Seguir OCR selecionado" (S-270/S-512). Não é comando do catálogo: nunca teve item
de menu nem tecla, e é lido pelo painel de resultado, não disparado por quem clica. Era um `QCheckBox`
com o texto escrito no widget; o texto vem para cá e o widget deixa de saber o que ele diz."""

EXPORTAR_ESTUDO = "exportar_estudo"
"""O agrupador "Exportar ▾", que abre os três formatos. Não faz nada sozinho: quem faz é cada item do
submenu, e é o item que tem nome no catálogo -- a mesma regra de `ALINHAR` e `CAIXA` em `ui/strings.py`."""

METODOS_PROPRIOS: dict[str, str] = {SEGUIR_OCR: "on_follow_ocr_toggle"}
"""Ação fora do catálogo -> método do painel, no mesmo formato de `COMANDOS_DA_ABA`."""

NAVEGACAO: tuple[str, ...] = ("inicio_da_linha", "lance_anterior", "proximo_lance", "fim_da_linha")
"""Os quatro que **não** estão nesta barra, na ordem em que se desenham: a S-517 os pôs sob o
tabuleiro, e é daqui que `qt/painel_de_estudo._barra_de_navegacao` os lê. A fronteira entre as duas
barras da sala fica declarada uma vez, e o teste a cobra nos dois sentidos contra `COMANDOS_DA_ABA`."""


@dataclass(frozen=True)
class Acao(_barra.Acao):
    """Uma ação da barra da sala. A forma é `ui/barra.Acao`; aqui fica o que é só da sala.

    `GRUPOS`, `IRMAS` e `METODOS` são amarrados ao pé do arquivo, quando a tupla já existe.
    """

    so_com_motor: bool = False
    """Existe só quando o painel foi montado com um motor (S-33)."""


Acao.GRUPOS = GRUPOS
"""O vocabulário de grupos que `__post_init__` cobra. Amarrado aqui, e não no corpo da classe,
porque o nome do módulo e o da classe seriam o mesmo e o mais interno venceria."""


ACOES: tuple[Acao, ...] = (
    # --------------------------------------------------------------------------- POSICAO
    # O que se faz a cada diagrama: carregar o que o OCR leu, e deixar a sala seguir o painel de
    # resultado. Virar, trocar a vez, aplicar e copiar FEN são de uma vez por estudo -- e a FEN
    # digitada já se aplica com Enter no próprio campo.
    Acao("estudo_do_diagrama", POSICAO, "carregar_ocr", prioridade=1, com_texto=True),
    Acao(
        SEGUIR_OCR,
        POSICAO,
        "seguir",
        prioridade=2,
        marcavel=True,
        rotulo_proprio="Seguir OCR",
        dica="Quando o painel de resultado troca de diagrama, a sala abre o estudo dele.\n"
        "Corrigir uma casa do mesmo diagrama chega ao tabuleiro só enquanto o estudo está vazio.",
    ),
    Acao("estudo_da_posicao_inicial", POSICAO, "posicao_inicial", prioridade=9),
    Acao("virar_tabuleiro", POSICAO, "virar", principal=False),
    Acao("trocar_vez", POSICAO, "trocar_vez", principal=False),
    Acao("estudo_aplicar_fen", POSICAO, "aplicar_fen", principal=False, dica="Enter no campo de FEN faz o mesmo."),
    Acao("copiar_fen", POSICAO, "copiar", principal=False),
    # -------------------------------------------------------------------------- VARIANTE
    # A cirurgia de árvore. Promover e rebaixar são **um par** (mesma prioridade: entram e saem
    # juntos), apagar a variante e anotar o lance são o gesto de quem lê um livro com o tabuleiro
    # ao lado; promover a principal e cortar daqui em diante são raros -- e o segundo é o que mais
    # apaga, então fica a um clique a mais de propósito.
    Acao("promover_variante", VARIANTE, "promover", prioridade=4),
    Acao("rebaixar_variante", VARIANTE, "rebaixar", prioridade=4),
    Acao("apagar_variante", VARIANTE, "apagar_variante", prioridade=5),
    Acao(
        "simbolo_do_lance",
        VARIANTE,
        "simbolo",
        prioridade=6,
        dica="O símbolo do lance. Escolher o mesmo de novo tira; escolher outro do mesmo grupo\n"
        "troca. Julgar o lance (!, ?) e julgar a posição (⩲, ±) são duas frases, e somam.",
    ),
    Acao(
        "dobrar_variantes",
        VARIANTE,
        "dobrar",
        prioridade=10,
        marcavel=True,
        dica="Esconde o miolo das variantes e deixa `(…)` no lugar. O `(` de cada uma também\n"
        "responde ao clique. A variante que contém o lance corrente não se dobra.",
    ),
    Acao("promover_a_principal", VARIANTE, "principal", principal=False),
    Acao("apagar_continuacao", VARIANTE, "apagar_daqui", principal=False),
    # ----------------------------------------------------------------------------- LIVRO
    Acao(
        "mostrar_diagrama",
        LIVRO,
        "recorte",
        prioridade=11,
        marcavel=True,
        dica="O recorte que o modelo leu, ao lado do tabuleiro. Fica cinza quando o estudo não\n"
        "veio de um diagrama do livro -- uma FEN digitada à mão não tem recorte.",
    ),
    Acao(
        "linha_do_livro",
        LIVRO,
        "livro",
        prioridade=13,
        dica="Joga na árvore a linha impressa ao lado deste diagrama, e para no primeiro lance\n"
        "que a posição não sustenta -- dizendo qual foi. Exige a folha lida na aba Texto.",
    ),
    Acao("ir_para_a_pagina", LIVRO, "ver_a_pagina", principal=False),
    # ------------------------------------------------------------------------------ BASE
    # Indexar é de uma vez por torneio acrescentado à pasta (S-532), e por isso mora no "Mais".
    Acao("partidas_da_posicao", BASE, "partidas", prioridade=12),
    # **Prioridade 15, a última da fila**, e é medida e não modéstia: a 714 px cabem onze botões
    # (S-527), e este é o décimo segundo. Ele é gesto de lance -- pergunta-se a árvore a cada
    # posição da abertura --, então ele **é** principal e aparece assim que a janela alarga; numa
    # janela estreita `cabem` o manda para o "Mais", que é onde ele custa um clique a mais.
    Acao(
        "arvore_de_aberturas",
        BASE,
        "arvore",
        prioridade=15,
        dica="Cada lance jogado desta posição, com quantas partidas, o resultado, o Elo e o ano.\n"
        "Responde pela árvore construída: sem ela, a janela diz isso e oferece construí-la.",
    ),
    Acao("abrir_pgn", BASE, "abrir_pdf", principal=False),
    Acao("colar_estudo", BASE, "colar", principal=False),
    # Buscar é do mesmo grupo e do mesmo gesto que "Partidas", e mesmo assim mora no "Mais": a
    # pergunta por posição sai do tabuleiro que já está na tela, e esta sai de um formulário de
    # seis campos -- é uma sessão de busca, e não um clique no meio da análise (S-533).
    Acao(
        "buscar_partidas",
        BASE,
        "filtrar",
        principal=False,
        dica="Jogador, evento, ano, Elo, resultado e ECO, combinados. Responde pelo índice por\n"
        "nome: sem ele em dia, a busca diz isso e oferece construí-lo.",
    ),
    Acao(
        "indexar_base",
        BASE,
        "indexar",
        principal=False,
        dica="Lê só os arquivos que mudaram desde a última vez, com barra e Cancelar.\n"
        "Até o índice ficar em dia, a busca por nome em \"Partidas\" não o usa.",
    ),
    # ----------------------------------------------------------------------------- MOTOR
    # A seção do motor abaixo da lista já tem o botão "Analisar posição" e a avaliação; na barra
    # fica o interruptor, que é o que se liga uma vez e se esquece.
    Acao(
        "analise_continua",
        MOTOR,
        "motor",
        prioridade=14,
        marcavel=True,
        so_com_motor=True,
        dica="O motor acompanha o lance corrente e grava a avaliação nele, em [%eval].\n"
        "Navegar cancela a análise em curso: a resposta atrasada é descartada.",
    ),
    Acao("analisar_posicao", MOTOR, "lupa", principal=False, so_com_motor=True),
    Acao("variante_do_motor", MOTOR, "linha_do_motor", principal=False, so_com_motor=True),
    Acao(
        "analisar_partida",
        MOTOR,
        "grafico",
        principal=False,
        so_com_motor=True,
        dica="Passa a linha principal inteira pelo motor, com barra e Cancelar. Grava a avaliação\n"
        "em cada lance e marca as imprecisões, os erros e os erros graves com o símbolo do PGN.",
    ),
    # **O único do grupo Motor que existe sem motor** (S-536), e tem de ser: numa máquina em que a
    # procura automática não achou binário nenhum, é por aqui que se diz onde ele está. Os outros
    # três desapareceriam junto com a seção, e com eles o caminho para fazê-la aparecer.
    Acao(
        "opcoes_do_motor",
        MOTOR,
        "ajustes",
        principal=False,
        dica="Caminho do binário, tabela de transposição, núcleos, linhas candidatas e a pasta de\n"
        "tablebases. O que muda é aplicado ao motor aberto: só trocar o binário sobe outro processo.",
    ),
    # -------------------------------------------------------------------------- EXPORTAR
    # O PGN é a saída que não perde nada, e é a que se usa; os três formatos de texto viram um
    # botão só, porque são a mesma pergunta ("em que formato?") e não três gestos.
    Acao("salvar_estudo", EXPORTAR, "salvar", prioridade=7, com_texto=True),
    Acao(EXPORTAR_ESTUDO, EXPORTAR, "exportar_pgn", prioridade=8, rotulo_proprio="Exportar"),
    Acao("exportar_estudo_md", EXPORTAR, "", principal=False, dentro_de=EXPORTAR_ESTUDO),
    Acao("exportar_estudo_html", EXPORTAR, "", principal=False, dentro_de=EXPORTAR_ESTUDO),
    Acao("exportar_estudo_rtf", EXPORTAR, "", principal=False, dentro_de=EXPORTAR_ESTUDO),
    # O quarto do agrupador (S-545). Ele é formato como os três, e a diferença -- sair já
    # paginado -- não é um segundo gesto: quem clica "Exportar ▾" está perguntando "em quê?".
    Acao("exportar_estudo_pdf", EXPORTAR, "", principal=False, dentro_de=EXPORTAR_ESTUDO),
    Acao("estudo_para_o_texto", EXPORTAR, "para_o_texto", principal=False),
    # Os dois que **não** entram no agrupador, e nem na fila. Imprimir termina no papel e abre a
    # pré-visualização; o lote de diagramas produz centenas de arquivos e pergunta sete coisas
    # antes. Nenhum dos dois é gesto de lance -- é a régua de `comandos.fila_de_destaque` --, e
    # por isso os dois moram no "Mais", a um clique, com ícone próprio.
    Acao(
        "imprimir_estudo",
        EXPORTAR,
        "imprimir",
        principal=False,
        dica="Pré-visualização paginada como livro: margem, cabeçalho com o nome do estudo e\n"
        "número de página. O diagrama sai em vetor, e a quebra não o separa do lance que o pede.",
    ),
    Acao(
        "exportar_diagramas_lote",
        EXPORTAR,
        "diagramas_em_lote",
        principal=False,
        dica="Um arquivo de imagem por diagrama, com o nome dizendo livro, página e diagrama.\n"
        "PNG ou SVG, no tamanho e na pele escolhidos, com prévia antes de gravar.",
    ),
    # ---------------------------------------------------------------------------- TREINO
    # Prioridade 3, com texto, e **marcado enquanto treina**: é o interruptor do modo, e o crítico
    # mediu que treinando nada na barra dizia isso -- o botão estava no "Mais" e o marcado não se
    # desenhava. O texto vira "Parar o treino" (`rotulo_alternado`) e a face marcada do tema o pinta.
    Acao(
        "modo_treino",
        TREINO,
        "treinar",
        prioridade=3,
        marcavel=True,
        com_texto=True,
        dica="A linha some e o tabuleiro cobra o lance. A árvore não muda: errar não cria\n"
        "variante -- para guardar o lance que você jogou, desligue o treino.",
    ),
    # **Os dois da Fase 83 vão para o "Mais", e é a régua de `fila_de_destaque` de novo** (S-539,
    # S-540): extrair as táticas é uma vez por livro -- a varredura leva minutos -- e abrir a
    # agenda é uma vez por sessão. O que se faz a cada lance é o `modo_treino` acima, e é ele que
    # fica na fila. Pôr os três lá empurraria um dos onze que hoje cabem a 714 px para o menu.
    Acao(
        "taticas_do_livro",
        TREINO,
        "extrair_taticas",
        principal=False,
        dica="Casa cada diagrama deste livro com a solução impressa e guarda o par como\nexercício. "
        "Diz quantos ficaram de fora e por quê. Leva minutos, e é cancelável.",
    ),
    Acao(
        "treinar_agenda",
        TREINO,
        "agenda",
        principal=False,
        dica="A fila de hoje da repetição espaçada: o que venceu, e alguns que você ainda não viu.\n"
        "Some por um mês e ela não vira uma parede -- o teto do dia adia o resto.",
    ),
)
"""As trinta e quatro ações da barra: trinta e dois comandos da aba, o interruptor e o agrupador.

É `COMANDOS_DA_ABA` inteira menos `NAVEGACAO`, mais `SEGUIR_OCR` e `EXPORTAR_ESTUDO`. A conta é
cobrada nos dois sentidos em `tests/test_ui_barra_da_sala.py`: comando da aba que a barra não
desenha, e ação da barra que a aba não tem.

**A ordem das prioridades é a da frequência, medida contra a largura de 714 px** (a aba Estudo a
1400×950): 1 carregar o OCR, 2 seguir o OCR, 3 treinar, 4 o par promover/rebaixar, 5 apagar a
variante, 6 o símbolo, 7 salvar, 8 exportar, 9 posição inicial, 10 dobrar, 11 recorte, 12 partidas,
13 linha do livro, 14 análise contínua. Três com texto e onze só com ícone: é o que faz onze
caberem onde antes cabiam cinco."""

por_acao: dict[str, Acao] = {registro.acao: registro for registro in ACOES}


def acao(nome: str) -> Acao:
    """O registro daquela ação. Levanta `KeyError` para nome que a barra não tem."""
    if nome not in por_acao:
        raise KeyError(f"ação fora da barra da sala: {nome!r}")
    return por_acao[nome]


def rotulo_do_grupo(grupo: str) -> str:
    if grupo not in _ROTULOS_DE_GRUPO:
        raise KeyError(f"grupo desconhecido: {grupo!r}. Os válidos estão em GRUPOS.")
    return _ROTULOS_DE_GRUPO[grupo]


def acoes_para(*, com_motor: bool) -> tuple[Acao, ...]:
    """As ações que esta montagem do painel tem: sem motor, o grupo `MOTOR` não existe."""
    return tuple(registro for registro in ACOES if com_motor or not registro.so_com_motor)


def do_grupo(grupo: str, *, com_motor: bool = True) -> tuple[Acao, ...]:
    rotulo_do_grupo(grupo)
    return tuple(registro for registro in acoes_para(com_motor=com_motor) if registro.grupo == grupo)


def principais(*, com_motor: bool = True) -> tuple[Acao, ...]:
    """As que ganham botão, na ordem da barra."""
    return tuple(registro for registro in acoes_para(com_motor=com_motor) if registro.principal)


def secundarias(*, com_motor: bool = True) -> tuple[Acao, ...]:
    """As que vão direto para o "Mais", na ordem da barra. Item de submenu não está aqui: o lugar
    dele é o agrupador."""
    return tuple(
        registro
        for registro in acoes_para(com_motor=com_motor)
        if not registro.principal and not registro.dentro_de
    )


def sequencia_de(nome: str) -> str:
    """A tecla que a **barra** registra para aquela ação, ou `""`.

    É o gancho que o widget consulta, e ele existe porque as duas barras em fila respondem
    diferente: as teclas da sala (`TECLAS_DA_SALA`) não estão na tabela da janela e precisam ser
    registradas pela própria barra, com alcance no painel; as do painel do PDF já estão no menu da
    janela, e registrá-las de novo daria duas donas para a mesma tecla -- que é a colisão que
    `atalhos.conferir_dono` existe para acusar.
    """
    return atalhos.sequencia_da_sala(nome) if nome in COMANDOS_DA_ABA else ""


# ------------------------------------------------------------------------------------ os modos

SEM_ESTUDO = "sem-estudo"
"""`Estudo.vazio()`: nem lance, nem comentário, nem símbolo, nem seta. Não há árvore para editar nem
estudo para exportar, e os botões dizem isso em vez de responder com uma frase no rodapé."""

COM_ESTUDO = "com-estudo"

TREINANDO = "treinando"
"""O treino da S-290: a linha some e o tabuleiro cobra o lance. Editar a árvore enquanto ela está
escondida é o que o Lichess esconde -- não é do momento."""

MODOS: tuple[str, ...] = (SEM_ESTUDO, COM_ESTUDO, TREINANDO)

_DESLIGADOS: dict[str, frozenset[str]] = {
    SEM_ESTUDO: frozenset({VARIANTE, EXPORTAR}),
    COM_ESTUDO: frozenset(),
    TREINANDO: frozenset({VARIANTE}),
}


def modo(*, vazio: bool, treinando: bool) -> str:
    """O modo da sala a partir de duas perguntas ao painel. Treinar ganha: só se treina com estudo."""
    if treinando:
        return TREINANDO
    return SEM_ESTUDO if vazio else COM_ESTUDO


def grupos_desligados(qual: str) -> frozenset[str]:
    """Os grupos cujas ações ficam desabilitadas naquele modo. Levanta para modo desconhecido."""
    if qual not in _DESLIGADOS:
        raise KeyError(f"modo desconhecido: {qual!r}. Os válidos estão em MODOS.")
    return _DESLIGADOS[qual]


# ------------------------------------------------------------------- a tabela amarrada à forma
#
# `IRMAS` é o que faz `agrupador` e `itens_do_submenu` responderem; `METODOS` é o que faz `metodo`
# responder. As duas são `ClassVar` de `ui/barra.Acao`, e cada tabela amarra as suas depois de a
# tupla existir -- que é a única ordem possível: a tupla é construída com a própria classe.

Acao.IRMAS = ACOES
Acao.METODOS = {**COMANDOS_DA_ABA, **METODOS_PROPRIOS}
