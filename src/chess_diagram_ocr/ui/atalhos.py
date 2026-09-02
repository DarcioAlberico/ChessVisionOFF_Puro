"""Os atalhos de teclado, **declarados uma vez** (S-161/S-165).

**O defeito que isto fecha.** Os atalhos existiam como um dicionário literal dentro de
`app_tkinter._bind_shortcuts`: sequência do Tk → função. Nada mais no programa sabia deles.
Consequência, medida com a janela aberta: **nenhum dos dez aparece na interface** — não há menu,
não há legenda, e o tooltip de um botão não diz que existe tecla para aquilo. Depois da S-150 isso
deixou de ser conveniência: num notebook de 1366×768 o `Ctrl+S` era o único caminho para salvar, e
ele não estava escrito em lugar nenhum.

**Uma tabela, três clientes.** `bind_shortcuts` liga, o menu mostra o acelerador e a legenda da
S-165 lista. Se fossem duas listas elas divergiriam -- é exatamente o que aconteceu com os rótulos
de procedência antes da S-04, e o que a S-134 documenta sobre índices que ninguém verifica.

**Eram dez, e não onze.** A avaliação escreveu "onze atalhos" e listou dez (`←`, `→`, `Ctrl+S`,
`Ctrl+Shift+S`, `Ctrl+R`, `Del`, `Ctrl+N`, `PgUp`, `PgDn`, `Ctrl+0`); `_bind_shortcuts` ligava dez.
Ficou corrigido aqui e o teste conta, porque um número que ninguém consegue reproduzir é o
mecanismo da S-135.

**São onze desde a S-223**, e o décimo primeiro é `Ctrl+Enter`. Ele não entrou por simetria: a
fila de ações da pele "Foco" só admite comando que tenha tecla, e `aplicar_fen` é o gesto que
**fecha** o ciclo corrigir → salvar sem ter uma. Quem digita uma FEN à mão estava obrigado a largar
o teclado para aplicá-la, com as mãos já dentro do campo -- que é a mesma situação de notebook que
a S-150 mediu para o `Ctrl+S`.

**A ação é um nome, e não uma função.** Cada linha aponta para um identificador (`"salvar"`), e
quem tem os widgets é que diz o que aquele nome faz. É o que permite a este módulo -- e ao
`ui/menu.py`, que consome os mesmos nomes -- não importar `tkinter` nem conhecer painel nenhum.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "ATALHOS",
    "CEDIDA_PELA_GUARDA",
    "GANHA_DO_TK",
    "SOBREPOSICOES_NO_EDITOR",
    "TECLAS_DO_EDITOR",
    "Atalho",
    "DonoDeAcoes",
    "acao_de",
    "acelerador",
    "cede_a_sequencia",
    "conferir_dono",
    "descricao_completa",
    "destino",
    "por_acao",
    "sobreposicao",
    "teclas_cedidas_ao_editor",
]


@dataclass(frozen=True)
class Atalho:
    """Uma tecla, o que ela faz, e como ela se escreve para ser lida."""

    sequencia: str
    """A sequência do Tk, como `bind_all` a quer: `"<Control-s>"`."""

    rotulo: str
    """Como a pessoa lê: `"Ctrl+S"`. Declarado e não derivado -- `<Prior>` vira "Page Up", e
    nenhuma regra de tradução acerta isso sem uma tabela de exceções do tamanho desta."""

    acao: str
    """O nome do comando. Quem tem os widgets amarra o nome à função."""

    descricao: str
    """O que ele faz, em pt-BR, como a legenda e o menu vão dizer."""

    no_editor: str = ""
    """O que a **mesma tecla** faz quando o foco está no editor de texto (S-244). Vazio = o mesmo.

    Existe porque a tecla passou a ter dois destinos, e uma legenda que contasse um só seria pior
    que não ter legenda: quem lesse "Ctrl+S salva a posição" e apertasse dentro do texto veria o
    texto ser gravado, e concluiria que a legenda mente sobre o resto.

    **Não é um atalho novo.** `ATALHOS` continua com as catorze sequências de sempre -- o que a
    S-244 acrescentou foi destino conforme o foco, e não tecla."""

    na_sala: str = ""
    """O que a **mesma tecla** faz quando o foco está na sala de estudo (S-281). Vazio = o mesmo.

    Irmão de `no_editor`, e pela mesma razão: `←` é "diagrama anterior" em toda a janela e "lance
    anterior" dentro da sala, e uma legenda que contasse um destino só seria pior que não ter
    legenda. Quem atende é `study_panel.ACOES_PROPRIAS`, pelo mecanismo da S-244.

    **E foi ele que trouxe `Home` e `End` para esta tabela.** A sala precisava de "início" e "fim
    da linha", e aqui não entra tecla sem comando global -- então a pergunta virou *o que Home e
    End fazem no resto da janela?*. A resposta estava faltando desde sempre: `Page Up` e `Page
    Down` viram **uma** página, e nada levava à primeira nem à última."""


ATALHOS: tuple[Atalho, ...] = (
    Atalho(
        "<Left>",
        "←",
        "diagrama_anterior",
        "Diagrama anterior desta página",
        na_sala="Lance anterior do estudo",
    ),
    Atalho(
        "<Right>",
        "→",
        "proximo_diagrama",
        "Próximo diagrama desta página",
        na_sala="Próximo lance do estudo",
    ),
    # Antes de salvar porque é o que vem antes no gesto: aplica-se a FEN digitada e **então**
    # se grava. A guarda de foco de `ui/shortcuts.py` cede a tecla a qualquer campo de texto, e
    # é dentro do campo de FEN que esta faz sentido -- por isso o campo declara a mesma sequência
    # para si (S-117), e a tabela continua sendo a única declaração dela.
    Atalho("<Control-Return>", "Ctrl+Enter", "aplicar_fen", "Aplicar ao tabuleiro a FEN digitada"),
    Atalho(
        "<Control-s>",
        "Ctrl+S",
        "salvar",
        "Salvar a posição do diagrama selecionado",
        no_editor="Grava o texto da folha no arquivo do editor (.cvtxt)",
    ),
    Atalho("<Control-S>", "Ctrl+Shift+S", "salvar_todos", "Salvar todos os diagramas lidos da página"),
    Atalho("<Control-r>", "Ctrl+R", "ler_pagina", "Ler esta página de novo (OCR de todos os diagramas)"),
    Atalho("<Delete>", "Del", "apagar_casa", "Apagar a peça da casa selecionada no tabuleiro"),
    # Depois do apagar porque é o que vem depois no gesto: erra-se a casa e desfaz-se. As duas
    # teclas são as do sistema, e a escolha é de reconhecimento e não de gosto -- `Ctrl+Z` num
    # editor que fizesse outra coisa seria a pior surpresa possível num programa de correção.
    Atalho(
        "<Control-z>",
        "Ctrl+Z",
        "desfazer",
        "Desfazer a última mudança no tabuleiro",
        no_editor="Desfaz a última edição do texto",
    ),
    Atalho(
        "<Control-y>",
        "Ctrl+Y",
        "refazer",
        "Refazer a mudança que o desfazer tirou",
        no_editor="Refaz a edição do texto que o desfazer tirou",
    ),
    # As duas da S-267, e elas fecham uma declaração vazia: `achar` e `substituir` estavam em
    # `texto_panel.ACOES_PROPRIAS` -- "a aba atende esta ação global enquanto tem o foco" -- e não
    # havia ação global nenhuma para atender. A tabela não tinha as teclas, então a declaração da
    # aba não fazia nada, e `Ctrl+F` num editor de texto não fazia nada tampouco.
    #
    # **Elas não têm `no_editor`, e é o oposto do `Ctrl+S`.** Ali a mesma tecla tem dois destinos
    # conforme o foco; aqui ela tem **um**, porque a janela só tem uma busca e ela é a do texto da
    # folha. Fora do editor, `Ctrl+F` abre a mesma janela de busca -- que é melhor que não fazer
    # nada, e é o que um programa com uma busca só deve fazer.
    Atalho("<Control-f>", "Ctrl+F", "achar", "Achar no texto da folha"),
    Atalho("<Control-h>", "Ctrl+H", "substituir", "Achar e substituir no texto da folha"),
    Atalho("<Control-n>", "Ctrl+N", "proximo_da_fila", "Abrir o próximo item pendente da fila de revisão"),
    Atalho("<Prior>", "Page Up", "pagina_anterior", "Página anterior do livro"),
    Atalho("<Next>", "Page Down", "proxima_pagina", "Próxima página do livro"),
    # **As duas da S-281**, e elas fecham o par que faltava: virar uma página tinha tecla desde a
    # S-70, e ir à primeira ou à última não tinha nenhuma. Ver `na_sala` para o outro motivo de
    # elas existirem -- e para por que ele veio primeiro.
    Atalho(
        "<Home>",
        "Home",
        "primeira_pagina",
        "Primeira página do livro",
        na_sala="Início da linha do estudo",
    ),
    Atalho(
        "<End>",
        "End",
        "ultima_pagina",
        "Última página do livro",
        na_sala="Fim da linha do estudo",
    ),
    Atalho("<Control-0>", "Ctrl+0", "ajustar_largura", "Ajustar a página à largura do visualizador"),
    # **As três da S-333**, e elas fecham o enquadramento: ajustar à largura tinha tecla desde a
    # S-165, e aumentar, diminuir e ajustar à página não tinham nenhuma. As três estão a um botão
    # de distância na barra do visualizador, e é justamente por isso que a falta passou -- quem
    # está lendo uma folha já tem a mão no mouse. Quem não tem é quem lê pelo teclado.
    #
    # `Ctrl++` e `Ctrl+-` são as do navegador e as do leitor de PDF do sistema, e são as mesmas
    # que o editor de texto usa para o corpo dele: a sobreposição está declarada logo abaixo, e
    # dentro do editor a tecla continua sendo dele.
    Atalho(
        "<Control-plus>",
        "Ctrl++",
        "zoom_mais",
        "Aproximar a página",
        no_editor="Aumenta o corpo do texto da folha",
    ),
    Atalho(
        "<Control-minus>",
        "Ctrl+-",
        "zoom_menos",
        "Afastar a página",
        no_editor="Diminui o corpo do texto da folha",
    ),
    Atalho("<Control-9>", "Ctrl+9", "ajustar_pagina", "Enquadrar a folha inteira na tela"),
    # Fora do gesto, e por isso no fim: as treze de cima agem sobre o diagrama ou sobre a página,
    # e esta age sobre o **programa** -- ela é como se acha um comando quando não se sabe em que
    # menu ele mora. `<Control-P>` e não `<Control-Shift-p>` pela mesma razão do `Ctrl+Shift+S`:
    # o Tk entrega a maiúscula, e o modificador escrito à mão nunca chega no Windows (S-20).
    Atalho("<Control-P>", "Ctrl+Shift+P", "paleta_de_comandos", "Abrir a paleta de comandos e procurar pelo nome"),
)
"""Os dezoito atalhos do ciclo corrigir → salvar → próximo (S-20/S-70/S-223/S-229/S-231/S-267/S-281).

A ordem é a do gesto, e não a alfabética: navegar entre diagramas, aplicar a FEN, salvar, reler,
corrigir casa, desfazer, puxar da fila, virar página, enquadrar. É a mesma ordem em que a legenda
os mostra.

**O décimo segundo e o décimo terceiro são da S-229**, e eles fecham um buraco que a tabela tornava
visível: dez das onze teclas agiam sobre o diagrama, e nenhuma o devolvia ao estado anterior.

**O décimo quarto é a paleta de comandos (S-231)**, e ele é o primeiro que não age sobre o
documento. Entrar aqui é o que lhe dá a legenda e o acelerador no menu Ajuda de graça -- e é a
única declaração da tecla no programa, que é o que `test_ui_legenda` cobra varrendo os literais
`<Control...>` de todo o `ui/`."""


TECLAS_DO_EDITOR: dict[str, str] = {
    "negrito": "<Control-b>",
    "italico": "<Control-i>",
    "sublinhado": "<Control-u>",
    "alinhar_esquerda": "<Control-l>",
    "alinhar_centro": "<Control-e>",
    "alinhar_direita": "<Control-r>",
    "justificar": "<Control-j>",
    "aumentar_corpo": "<Control-bracketright>",
    "diminuir_corpo": "<Control-bracketleft>",
    "selecionar_tudo": "<Control-a>",
    "aproximar_texto": "<Control-plus>",
    "afastar_texto": "<Control-minus>",
    # **`Ctrl+H` está aqui e em `ATALHOS`, e a duplicata é obrigatória** (S-267). Medido: em
    # `tk8.6/text.tcl` o `Ctrl+H` da **classe** `Text` é backspace -- herança de terminal --, e um
    # `bind_all` roda **depois** dela (bindtags: widget, classe, toplevel, all). Ligada só na
    # janela, a tecla apagaria um caractere e **então** abriria a substituição, toda vez.
    #
    # O `bind` no widget roda primeiro e devolve `"break"`, que mata os dois de baixo. `Ctrl+F` não
    # precisa disto e por isso não está aqui: medido no mesmo lugar, a classe `Text` não faz nada
    # com ele nesta versão do Tk.
    "substituir": "<Control-h>",
}
"""As teclas próprias do editor de texto (S-241/S-259/S-260) -- **e por que não estão em `ATALHOS`**.

`ATALHOS` é a tabela dos atalhos **da janela**: cada linha vale em qualquer lugar dela, passa pela
guarda de foco de `ui/shortcuts.py` e ganha item de menu, acelerador e linha na legenda. Estas três
não são isso: elas só existem **dentro** do widget de texto, ligadas por `Text.bind`, e fora dele
não fazem nada. Pô-las lá dentro seria prometer `Ctrl+B` na Galeria.

Ficam aqui mesmo assim, e o motivo é o teste: `test_ui_legenda` varre todo o `ui/` atrás de
literais `<Control...>` e só perdoa este arquivo, justamente para que nenhuma tecla seja declarada
num painel. É a mesma disciplina, com o campo de FEN da S-117 como precedente.

**O `Ctrl+I` obriga a guarda.** Em `tk8.6/text.tcl:211`, `bind Text <Control-i>` insere uma
tabulação; quem ligar a tecla sem devolver `"break"` recebe o itálico **e** o tab. `Ctrl+B` e
`Ctrl+U` caem em `bind Text <Control-KeyPress> {# nothing}` e não têm o problema -- e é por isso que
todas devolvem `"break"`: quem acrescentar a próxima não vai reler este parágrafo.

**As seis da Fase 41 são as do Word, e três delas tomam tecla que o `tk.Text` já usa.** `Ctrl+E`
leva o cursor ao fim da linha no binding de fábrica, `Ctrl+L` centraliza a rolagem e `Ctrl+J` insere
uma quebra; as três são de teclado Emacs, e nenhuma delas é o que se espera num editor de texto do
Windows. O `"break"` é o que as substitui, e é a mesma decisão que o `Ctrl+I` obrigou -- a diferença
é que ali o binding de fábrica **somava** com o nosso, e aqui ele seria o único a acontecer.

`Ctrl+]` e `Ctrl+[` para o corpo são as do Word também. Elas entram por nome de tecla
(`bracketright`) e não por caractere, porque o caractere depende do teclado: num ABNT2 o `]` está
noutro lugar, e o nome da tecla é o que o Tk resolve igual nos dois.

**`Ctrl+A` é a tecla que faltava, e ela é uma correção e não um acréscimo** (S-263). No `tk.Text`
de fábrica ela leva o cursor ao **início da linha** -- herança de Emacs que nenhum programa de
Windows faz --, e "selecionar tudo" não tinha tecla nenhuma. Quem apertava `Ctrl+A` para selecionar
a folha via o cursor pular e concluía que a aba não fazia aquilo.

**Recortar, copiar e colar não estão aqui, e é decisão.** O Tk liga `<<Cut>>`, `<<Copy>>` e
`<<Paste>>` a `Ctrl+X/C/V` no widget de fábrica, e declará-las de novo aqui seria a segunda
declaração da mesma tecla -- o defeito que esta tabela existe para impedir. O que faltava a elas era
**comando**, e não tecla: ver `ui/comandos.py`."""


CEDIDA_PELA_GUARDA = "cedida-pela-guarda"
"""A tecla é da janela, e dentro do editor ela é do editor: ali a da janela está morta.

**Quem cede mudou, e o valor continua certo** (S-294). Até aquele item quem cedia era o cobertor de
`shortcuts.ignores_widget`, que entregava *toda* tecla a *todo* campo de texto. Agora quem cede é
`owns_key`: o editor **declara** `<Control-r>` em `TECLAS_DO_EDITOR` e liga a tecla no próprio
widget, e a regra da S-117 -- quem declarou a tecla fica com ela -- é o que a segura.

A troca é para melhor, e a diferença aparece se alguém tirar a tecla do editor: antes ela
continuaria morta ali (o cobertor cedia de qualquer jeito), e agora ela volta a ser da janela.

**No Qt quem cede é `qt/atalhos.cede_a_tecla`**, lendo no widget em foco as teclas que o editor
declarou para si -- e o editor declara exatamente `teclas_cedidas_ao_editor()`. O `bind` no widget
virou um `QShortcut` com alcance no editor; a regra é a mesma (S-511)."""

GANHA_DO_TK = "ganha-do-tk"
"""A tecla é da janela e a aba a toma para si; o `bind` no widget existe para vencer a **classe**
`Text`, que roda antes de todo `bind_all` e faria outra coisa com ela.

**No Qt não há classe `Text`, e o valor continua certo pelo outro lado**: a tecla é da janela, a
guarda a entrega à aba por `acoes_proprias` (S-244), e o editor **não** a reclama para si -- é a
que `teclas_cedidas_ao_editor` deixa de fora, para a mesma tecla não ter dois donos."""

SOBREPOSICOES_NO_EDITOR: dict[str, str] = {
    "<Control-r>": CEDIDA_PELA_GUARDA,
    "<Control-h>": GANHA_DO_TK,
    # As duas da S-333. `Ctrl++` e `Ctrl+-` aproximam a **página** na janela e o **corpo do
    # texto** dentro do editor, que é o que as duas teclas fazem em qualquer programa com as duas
    # coisas. Cedidas pela guarda, como o `Ctrl+R`: o editor as declara e as liga no próprio
    # widget, e ali a da janela está morta.
    "<Control-plus>": CEDIDA_PELA_GUARDA,
    "<Control-minus>": CEDIDA_PELA_GUARDA,
}
"""Sequências que estão nas **duas** tabelas, e por que cada uma pode estar (S-259/S-267).

**Sobreposição declarada, e não colisão.** São dois motivos diferentes, e a diferença tem teste:

`CEDIDA_PELA_GUARDA` -- `Ctrl+R` é "ler esta página" desde a S-165 e continua sendo, em toda a
janela menos dentro do editor, onde ela é "alinhar à direita" desde a Fase 41. Quem a cede ali é
`ui/shortcuts.owns_key`: o editor a declara em `TECLAS_DO_EDITOR` e a liga no próprio widget. O
sinal disso é a ação **não** estar em `texto_panel.ACOES_PROPRIAS`.

**Até a S-294 quem cedia era outra coisa**, e vale registrar porque o valor desta entrada não
mudou e o mecanismo sim: era o cobertor de `ignores_widget`, que entregava *toda* tecla a *todo*
campo de texto -- e com ele `Ctrl+S` também morria ali, sem que ninguém tivesse decidido isso.

`GANHA_DO_TK` -- `Ctrl+H` é "substituir" nas duas tabelas, a mesma ação, e a duplicata é
obrigatória: a classe `Text` liga essa tecla a **backspace**, e um `bind_all` roda depois dela. Sem
o `bind` no widget, a tecla apagaria um caractere antes de abrir a substituição. O sinal disso é a
ação **estar** em `ACOES_PROPRIAS` e a tecla do editor apontar para ela.

O que não pode acontecer é a **próxima** entrar em silêncio, e é isso que esta tabela compra: a
sobreposição seguinte reprova `test_ui_atalhos_destino` até alguém escrever aqui de qual dos dois
tipos ela é -- ou trocar a tecla.

`Ctrl+L`, `Ctrl+E` e `Ctrl+J` **não** estão aqui: elas não são atalho da janela nenhum. O que elas
sobrepõem é o binding de fábrica do `tk.Text`, que é outro assunto e está no docstring acima."""


por_acao: dict[str, Atalho] = {atalho.acao: atalho for atalho in ATALHOS}
"""Índice por nome de comando. É por aqui que o menu descobre o acelerador de um item."""

por_sequencia: dict[str, Atalho] = {atalho.sequencia: atalho for atalho in ATALHOS}
"""Índice pela tecla. É por aqui que a guarda de foco descobre **que ação** aquela tecla pede
(S-244) -- sem isso ela teria de receber o nome por parâmetro em todo `bind`, e a tabela deixaria
de ser a única declaração da ligação tecla-ação."""


# ------------------------------------------------------ o que a guarda de foco cede, e a quem
#
# **Por que estas cinco listas moram aqui e não em `ui/shortcuts.py`, que é quem as usa** (S-501).
# Elas eram de lá e são **puras**: dizem que *ações* um campo de texto de fato usa, e derivam as
# teclas desta tabela. O que `ui/shortcuts.py` acrescenta é a única parte que conhece toolkit --
# quais classes de widget são campo de texto --, e essa parte é diferente em cada frontend.
#
# Deixá-las lá obrigava o segundo frontend a importar um módulo que importa `tkinter` só para ler
# um `frozenset`, ou a copiá-lo. A cópia é o defeito: `ACOES_DO_CAMPO` é a lista que decide se
# `Ctrl+S` salva com o cursor dentro do campo de FEN, e duas cópias dela divergem no primeiro item
# que alguém acrescentar a uma só -- que é a medição da S-294 esperando para acontecer de novo.

ACOES_DO_CAMPO: frozenset[str] = frozenset(
    {
        "diagrama_anterior",   # <-
        "proximo_diagrama",    # ->
        "primeira_pagina",     # Home
        "ultima_pagina",       # End
        "apagar_casa",         # Del
        "desfazer",            # Ctrl+Z
        "refazer",             # Ctrl+Y
    }
)
"""As ações da janela cujas teclas **qualquer** campo de texto de fato usa (S-294).

Navegação, edição e o desfazer do próprio widget: cada uma tem comportamento de fábrica dentro do
campo, e deixar o atalho da janela passar por cima o quebraria -- digitar uma FEN trocaria de
diagrama a cada seta, que é o defeito que a guarda existe para impedir desde a S-20.

**Declaradas por ação, e não por sequência.** A regra deste projeto é que só esta tabela escreve
tecla (`test_ui_legenda.test_so_a_tabela_escreve_sequencia_de_tecla`), e ela é a regra certa:
remapear `desfazer` acima e esquecer aqui deixaria a guarda cedendo uma tecla que não é mais a do
desfazer. Aqui se diz o **significado**; a tecla sai da tabela."""

ACOES_SO_DO_MULTILINHA: frozenset[str] = frozenset({"pagina_anterior", "proxima_pagina"})
"""`PgUp`/`PgDn` são cedidas só a quem rola.

Num campo de uma linha -- o campo de FEN -- elas não fazem coisa nenhuma, e cedê-las ali era
desligar "página anterior/seguinte" em troca de nada."""

TECLAS_DE_EDICAO: frozenset[str] = frozenset({"<Up>", "<Down>", "<BackSpace>"})
"""As teclas de edição que **não são atalho de janela nenhum**, e por isso não têm ação a citar.

Elas nunca chegam à guarda hoje -- nada as liga na janela inteira --, e estão aqui para o dia em
que alguma delas virar atalho: o campo de texto continua sendo o dono, e a lista já diz isso."""


def _sequencias(acoes: frozenset[str]) -> frozenset[str]:
    """As sequências daquelas ações, pela tabela. Ação sem tecla é ignorada, e não levanta.

    Ignorar em vez de levantar porque isto roda na **importação** do módulo: uma ação que perdesse
    a tecla derrubaria a janela inteira por causa de uma linha desta lista, e o que ela merece é
    deixar de ser cedida."""
    return frozenset(
        atalho.sequencia for acao in acoes if (atalho := por_acao.get(acao)) is not None
    )


CEDIDAS_A_TODO_CAMPO: frozenset[str] = _sequencias(ACOES_DO_CAMPO) | TECLAS_DE_EDICAO
CEDIDAS_SO_AO_MULTILINHA: frozenset[str] = _sequencias(ACOES_SO_DO_MULTILINHA)


def cede_a_sequencia(sequencia: str, *, e_campo: bool, e_multilinha: bool) -> bool:
    """A guarda deve ceder **esta tecla** a um campo com estas duas propriedades? (S-294) Pura.

    Não toca widget: quem responde "isto é campo de texto?" e "isto rola?" é o frontend, porque a
    resposta é uma lista de classes de toolkit. O que se decide aqui é o que vale nos dois.

    `←` dentro de um campo pertence ao campo; `Ctrl+S` não pertence a campo nenhum -- a régua é a
    lista do que o widget **de fato usa**, e não "é campo de texto?". O defeito que isso conserta
    está escrito em `ui/shortcuts.cede_a_tecla`: até a S-294 a guarda cedia os dezoito atalhos da
    janela, e com o cursor no campo de FEN `Ctrl+S` não salvava, `Ctrl+N` não ia para o próximo e
    `PgDn` não virava a página. Nenhuma delas faz coisa alguma dentro de um campo -- a tecla
    simplesmente morria.

    `sequencia=""` cede, como antes: quem chama sem dizer que tecla ligou não dá como responder, e
    o lado seguro é o comportamento anterior.
    """
    if not e_campo:
        return False
    if not sequencia:
        return True
    if sequencia in CEDIDAS_A_TODO_CAMPO:
        return True
    return e_multilinha and sequencia in CEDIDAS_SO_AO_MULTILINHA


def descricao_completa(atalho: Atalho) -> str:
    """O que a tecla faz -- **e o que ela faz nos lugares que a tomam para si** (S-244/S-281).

    Numa etiqueta só, e não em três colunas: a legenda lê os rótulos aos pares, e uma coluna a
    mais faria a janela mentir sobre a própria estrutura. Linhas dentro do mesmo rótulo é o que a
    S-244 pede -- *"uma tecla que faz duas coisas e uma legenda que só conta uma é pior que não
    ter legenda"*.

    **Três destinos e não dois, desde a S-281**: `←` é "diagrama anterior" na janela e "lance
    anterior" dentro da sala de estudo. O laço abaixo é o que faz o quarto destino, quando houver,
    entrar sem ninguém editar esta função.

    **Mora aqui, e não na janela que a mostra** (S-501). Era `legenda._descricao`, num arquivo
    cuja classe herda de `tk.Toplevel` -- então nem o import tardio o abria. A frase é sobre a
    *tabela*, não sobre a janela: quem sabe que uma tecla tem três destinos é quem os declara.
    """
    linhas = [atalho.descricao]
    for onde, texto in (("No editor de texto", atalho.no_editor), ("Na sala de estudo", atalho.na_sala)):
        if texto:
            linhas.append(f"{onde}: {texto}")
    return chr(10).join(linhas)


def acelerador(acao: str) -> str:
    """O rótulo da tecla daquele comando, ou `""` quando ele não tem uma.

    Devolve vazio em vez de levantar: a maioria dos itens de menu **não** tem atalho, e essa é a
    resposta certa para eles -- ao contrário de `tokens.cor`, onde não haver cor é um defeito.
    """
    atalho = por_acao.get(acao)
    return atalho.rotulo if atalho is not None else ""


# ------------------------------------------------- o destino conforme o foco (S-244)


@runtime_checkable
class DonoDeAcoes(Protocol):
    """Um painel que **toma para si** algumas ações globais enquanto tem o foco.

    `ui/shortcuts.guard` cede a tecla a qualquer campo de texto desde a S-20, e por medição: `←`
    dentro de um campo pertence ao campo, e `Del` apaga um caractere em vez da peça. O efeito
    colateral é que os catorze atalhos globais **passam direto** por um `tk.Text` -- e, do lado do
    Tk, `bind Text <Control-KeyPress> {# nothing}` come o que sobrou. Com o cursor no editor de
    texto, `Ctrl+S` não salvava a posição (a guarda cedeu) e não salvava o texto (ninguém ligou):
    a tecla mais esperada de um editor era um silêncio de duas camadas.

    A saída não é tirar a guarda -- ela existe por medição -- e não é acrescentar tecla. É tornar o
    ceder **tipado**: o painel em foco declara quais ações são dele, e a guarda pergunta antes de
    ceder.
    """

    def acoes_proprias(self) -> frozenset[str]:
        """Os nomes de comando que este painel atende enquanto tem o foco."""

    def atender(self, acao: str) -> Callable[[], object] | None:
        """A função deste painel para aquela ação, ou `None` se ele não a atende."""


def conferir_dono(dono: DonoDeAcoes, nome: str = "") -> None:
    """Levanta se o painel **declara** uma ação e não a atende (critério de aceite da S-244).

    É a mesma disciplina de `ligacoes`, que recusa atalho declarado sem comando, e pelo mesmo
    motivo: declarar "eu trato salvar" e não tratar é a promessa vazia que este módulo veio proibir
    -- com o agravante de que aqui ela **come a tecla**, e o global também deixa de responder.
    """
    faltando = sorted(acao for acao in dono.acoes_proprias() if dono.atender(acao) is None)
    if faltando:
        quem = nome or type(dono).__name__
        raise KeyError(f"{quem} declara ação que não atende: {', '.join(faltando)}")


def _cadeia(foco: object) -> list[object]:
    """O widget em foco e os pais dele, do mais interno para o mais externo.

    Sobe pelo `master` porque quem declara ações é o **painel**, e quem tem o foco é o `tk.Text`
    dentro dele. Duck typing de propósito: este módulo não importa `tkinter`, e o teste passa
    objetos de mentira com um `master`.

    **E pelo `parent()` quando não há `master`** (S-501). É o mesmo passo com o nome do outro
    toolkit: no Qt o pai de um widget é um método, não um atributo. Sem isto a cadeia pararia no
    widget em foco, e a declaração de ações da S-244 -- que é do **painel** -- nunca seria
    consultada no segundo frontend, sem erro nenhum a que se agarrar.
    """
    cadeia: list[object] = []
    atual = foco
    while atual is not None and len(cadeia) < 40:
        cadeia.append(atual)
        atual = _pai(atual)
    return cadeia


def _pai(widget: object) -> object:
    """O pai daquele widget, pelo nome que o toolkit dele usa. `None` quando não há.

    O `master` vem primeiro porque é atributo e não custa chamada; um `parent` que não seja
    chamável -- ou que levante, como o de um widget já destruído -- vale como ausência de pai, que
    é o que interrompe a subida em vez de derrubar a tecla.
    """
    pai = getattr(widget, "master", None)
    if pai is not None:
        return pai
    metodo = getattr(widget, "parent", None)
    if not callable(metodo):
        return None
    try:
        return metodo()
    except Exception:  # noqa: BLE001 - widget destruído no meio da subida: a cadeia acaba aqui
        return None


def destino(
    acao: str, foco: object, globais: Mapping[str, Callable[[], object]]
) -> Callable[[], object] | None:
    """A função que atende esta ação agora: a do widget em foco, se ele a declarar; senão a global.

    Devolve `None` quando ninguém a atende -- e quem chama decide o que fazer com isso. Devolver uma
    função vazia esconderia o caso, que é o de uma tecla ligada a um comando que a janela ainda não
    montou (o roteiro headless faz isso).
    """
    for widget in _cadeia(foco):
        if not isinstance(widget, DonoDeAcoes):
            continue
        try:
            if acao in widget.acoes_proprias():
                atendida = widget.atender(acao)
                if atendida is not None:
                    return atendida
        except Exception:  # noqa: BLE001 - painel meio construído não pode derrubar a tecla
            continue
    return globais.get(acao)


def acao_de(sequencia: str) -> str:
    """Que ação aquela tecla pede, ou `""` para uma sequência que a tabela não declara."""
    atalho = por_sequencia.get(sequencia)
    return atalho.acao if atalho is not None else ""


# ------------------------------------------------ as teclas que o editor divide com a janela


def sobreposicao(sequencia: str) -> str | None:
    """Como a janela e o editor dividem esta tecla do editor, ou `None` quando só o editor a declara.

    `CEDIDA_PELA_GUARDA` ou `GANHA_DO_TK`, lidos de `SOBREPOSICOES_NO_EDITOR`. Levanta `KeyError`
    para uma tecla que está nas **duas** tabelas sem linha ali: é "a sobreposição seguinte", que a
    tabela existe para impedir de entrar em silêncio -- e ela reprova na montagem do painel de
    texto, e não só no teste (S-511).
    """
    if sequencia not in por_sequencia:
        return None
    tipo = SOBREPOSICOES_NO_EDITOR.get(sequencia)
    if tipo is None:
        raise KeyError(f"{sequencia} está em ATALHOS e em TECLAS_DO_EDITOR sem sobreposição declarada")
    return tipo


def teclas_cedidas_ao_editor() -> frozenset[str]:
    """As sequências que o editor toma para si enquanto tem o foco: as só dele, e as cedidas.

    Fica de fora a que a janela ganha (`GANHA_DO_TK`): ali a guarda entrega a ação à aba por
    `acoes_proprias`, e o editor reclamá-la seria a mesma tecla com dois donos. É o que
    `qt/painel_de_texto.py` declara no próprio widget, e o que `qt/atalhos.cede_a_tecla` lê.
    """
    return frozenset(sequencia for sequencia in TECLAS_DO_EDITOR.values() if sobreposicao(sequencia) != GANHA_DO_TK)
