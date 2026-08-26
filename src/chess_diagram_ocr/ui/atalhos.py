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
    "conferir_dono",
    "destino",
    "ligacoes",
    "por_acao",
    "por_sequencia",
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


ATALHOS: tuple[Atalho, ...] = (
    Atalho("<Left>", "←", "diagrama_anterior", "Diagrama anterior desta página"),
    Atalho("<Right>", "→", "proximo_diagrama", "Próximo diagrama desta página"),
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
    Atalho("<Control-0>", "Ctrl+0", "ajustar_largura", "Ajustar a página à largura do visualizador"),
    # Fora do gesto, e por isso no fim: as treze de cima agem sobre o diagrama ou sobre a página,
    # e esta age sobre o **programa** -- ela é como se acha um comando quando não se sabe em que
    # menu ele mora. `<Control-P>` e não `<Control-Shift-p>` pela mesma razão do `Ctrl+Shift+S`:
    # o Tk entrega a maiúscula, e o modificador escrito à mão nunca chega no Windows (S-20).
    Atalho("<Control-P>", "Ctrl+Shift+P", "paleta_de_comandos", "Abrir a paleta de comandos e procurar pelo nome"),
)
"""Os catorze atalhos do ciclo corrigir → salvar → próximo (S-20/S-70/S-223/S-229/S-231).

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
"""A tecla é da janela, e a guarda de foco já a cedia dentro do editor: ali ela estava morta."""

GANHA_DO_TK = "ganha-do-tk"
"""A tecla é da janela e a aba a toma para si; o `bind` no widget existe para vencer a **classe**
`Text`, que roda antes de todo `bind_all` e faria outra coisa com ela."""

SOBREPOSICOES_NO_EDITOR: dict[str, str] = {
    "<Control-r>": CEDIDA_PELA_GUARDA,
    "<Control-h>": GANHA_DO_TK,
}
"""Sequências que estão nas **duas** tabelas, e por que cada uma pode estar (S-259/S-267).

**Sobreposição declarada, e não colisão.** São dois motivos diferentes, e a diferença tem teste:

`CEDIDA_PELA_GUARDA` -- `Ctrl+R` é "ler esta página" desde a S-165 e continua sendo, em toda a
janela menos dentro de um campo de texto, onde a guarda de `ui/shortcuts.ignores_widget` **já cedia
a tecla desde a S-20**. Com o cursor no editor essa sequência não fazia nada antes de a Fase 41 a
ligar a "alinhar à direita": ligá-la ali não tira nada de ninguém, ocupa uma tecla morta naquele
widget. O sinal disso é a ação **não** estar em `texto_panel.ACOES_PROPRIAS`.

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


def acelerador(acao: str) -> str:
    """O rótulo da tecla daquele comando, ou `""` quando ele não tem uma.

    Devolve vazio em vez de levantar: a maioria dos itens de menu **não** tem atalho, e essa é a
    resposta certa para eles -- ao contrário de `tokens.cor`, onde não haver cor é um defeito.
    """
    atalho = por_acao.get(acao)
    return atalho.rotulo if atalho is not None else ""


def ligacoes(comandos: Mapping[str, Callable[[], None]]) -> dict[str, Callable[[], None]]:
    """O mapa `sequência → função` que `bind_shortcuts` consome, montado da tabela.

    Levanta `KeyError` nomeando os comandos que faltam. Um atalho declarado e não ligado é uma
    tecla que não faz nada e que a legenda promete -- pior que não tê-lo, porque a pessoa conclui
    que apertou errado.
    """
    faltando = sorted(atalho.acao for atalho in ATALHOS if atalho.acao not in comandos)
    if faltando:
        raise KeyError(f"atalho declarado sem comando: {', '.join(faltando)}")
    return {atalho.sequencia: comandos[atalho.acao] for atalho in ATALHOS}


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

    def atender(self, acao: str) -> Callable[[], None] | None:
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
    """
    cadeia: list[object] = []
    atual = foco
    while atual is not None and len(cadeia) < 40:
        cadeia.append(atual)
        atual = getattr(atual, "master", None)
    return cadeia


def destino(acao: str, foco: object, globais: Mapping[str, Callable[[], None]]) -> Callable[[], None] | None:
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
