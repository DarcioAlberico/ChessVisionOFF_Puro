"""O catálogo de comandos da janela, declarado como dado (S-219).

**Três lugares declaravam comando, e nenhum deles era a lista.** `ui/menu.py` sabia o rótulo e a
posição na barra de menus; `ui/atalhos.py`, a tecla e como ela se escreve; `ui/pdf_panel.py`
montava o botão à mão, com o rótulo em literal. O nome do comando -- `"ler_pagina"`, `"salvar"` --
já ligava os três desde a S-161. O que não existia era o **registro**: nada dizia que `ler_pagina`
tem rótulo "Ler esta página", pertence ao grupo OCR e é uma das ações em destaque.

**A consequência, medida.** O rótulo do botão está em `pdf_panel.py:312` e o do menu em
`menu.py:110`, e eles **não são o mesmo texto**: "OCR todos diagramas" contra "Ler esta página".
Não é duplicação -- é divergência já consumada, e nada no programa a comparava. Com uma pele isso
é dívida tolerável. Com três (S-221), cada pele teria a sua ideia de o que existe, que é a S-161
de novo em outra forma: *"o que não era botão não existia"*.

**Este módulo não substitui `menu.MENUS`, e essa fronteira é o item.** O menu decide *onde na
barra de menus*; o catálogo decide *o que o comando é*. `MENUS` passa a referenciar o catálogo em
vez de repetir o rótulo, e `menu.montar` recusa item cujo `acao` não esteja aqui -- a disciplina
de `menu.comandos_faltando`, agora nos dois sentidos.

**Nenhum rótulo muda.** É o achado 1 do ROADMAP_APARENCIA: as propostas são visuais, não são
propostas de texto. Por isso `rotulo` (o do menu, longo) e `rotulo_curto` (o do botão de hoje)
convivem numa linha só, em vez de um deles apagar o outro. O ganho não é ter um texto: é os dois
passarem a ser **comparáveis**, que é exatamente o que faltava.

Nada de `tkinter` aqui, como em `ui/tokens.py` e `ui/atalhos.py`: quem monta widget não decide, e
quem decide é afirmável sem abrir janela.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from . import estilos, strings

__all__ = [
    "ACERVO",
    "AJUDA",
    "ARQUIVO",
    "CATALOGO",
    "Comando",
    "EDICAO",
    "GRUPOS",
    "NA_LINHA_DE_CAMPO",
    "OCR",
    "VISUALIZACAO",
    "acoes_fora_do_catalogo",
    "comando",
    "do_grupo",
    "em_destaque",
    "estilo",
    "fila_de_destaque",
    "papel",
    "por_acao",
    "primarios_por_grupo",
    "rotulo",
    "rotulo_alternado",
    "rotulo_de_botao",
    "rotulo_do_grupo",
]

ARQUIVO = "ARQUIVO"
EDICAO = "EDICAO"
VISUALIZACAO = "VISUALIZACAO"
OCR = "OCR"
ACERVO = "ACERVO"
AJUDA = "AJUDA"

GRUPOS: tuple[str, ...] = (ARQUIVO, EDICAO, VISUALIZACAO, OCR, ACERVO, AJUDA)
"""Os seis, e o conjunto é fechado.

Não são invenção: são os cinco menus de `menu.MENUS` com **Ferramentas partido em dois**, que é a
divisão que a Imagem 2 desenha e que o menu já insinuava com o separador de `menu.py:113`.

O corte entre `OCR` e `ACERVO` é uma pergunta, e não um gosto: **`OCR` age sobre a página aberta;
`ACERVO` age sobre o livro inteiro ou sobre o modelo que o lê.** Por isso "Ler esta página" é OCR
e "Varrer o livro" é ACERVO, e por isso treinar e recarregar o modelo caem em ACERVO junto da
anotação de conjunto de campo -- as três são sobre a máquina de ler, não sobre a folha na tela.
"""

_ROTULOS_DE_GRUPO: dict[str, str] = {
    ARQUIVO: "Arquivo",
    EDICAO: "Edição",
    VISUALIZACAO: "Visualização",
    OCR: "OCR",
    ACERVO: "Acervo",
    AJUDA: "Ajuda",
}
"""Como o grupo se escreve quando ele vira cabeçalho (a fita da S-227).

Um grupo sem rótulo legível é um grupo que não se desenha, e a constante `"VISUALIZACAO"` não é
texto de interface. Quatro destes são os cabeçalhos da Imagem 2, na grafia de `ui/strings.py`.
"""


@dataclass(frozen=True)
class Comando:
    """Um comando da janela, e tudo o que se sabe dele fora de um widget."""

    acao: str
    """O nome que ata tudo: `"ler_pagina"`. É o mesmo de `menu.py` e `atalhos.py`, e é a chave."""

    rotulo: str
    """Como o comando se chama, por extenso -- o texto do menu, que agora tem um dono só."""

    grupo: str
    """Um dos seis de `GRUPOS`. Fora deles levanta, e é por isso que o conjunto é fechado."""

    papel: str
    """`estilos.PRIMARIO`, `DESTRUTIVO` ou `NEUTRO`. Papel desconhecido levanta `KeyError`."""

    icone: str = ""
    """Nome no catálogo de ícones da S-220. Vazio é a resposta correta hoje: o repositório não
    tem um único ícone (achado 6 do roadmap), e declarar nome de ícone que ninguém desenha seria
    a promessa que a S-161 registra como o defeito de item de menu sem comando."""

    destaque: bool = False
    """Entra na fila curta da pele "Foco" (S-223). Ver `em_destaque` antes de ligar um novo."""

    rotulo_alternado: str = ""
    """O texto do botão **enquanto o comando está ligado**, para os que alternam. Vazio = não alterna.

    Existe porque a S-222 encontrou o buraco: o `selecionar_area` troca o próprio rótulo para
    "Cancelar seleção" por `configure(text=...)`, e a varredura da S-219 só olhava o `text=` do
    **construtor**. Eram dois literais escritos à mão que o teste dava por limpos -- e, na
    remontagem de cromo, dois rótulos que voltariam errados com a seleção ainda ligada."""

    rotulo_curto: str = ""
    """O texto que o **botão** mostra, quando ele difere do rótulo do menu. Vazio = são o mesmo.

    Existe porque nenhum item desta fase troca rótulo de comando nenhum (achado 1 do roadmap), e
    porque os dois textos já divergiam: encurtá-los para um só mudaria a janela de hoje, e apagar
    a diferença esconderia a dívida em vez de registrá-la. Aqui os dois ficam lado a lado, numa
    linha, onde um teste finalmente os compara."""

    def __post_init__(self) -> None:
        # `estilo_de_botao` é quem sabe quais papéis existem, e ele já levanta `KeyError` com a
        # mensagem certa. Repetir a lista aqui seria a segunda declaração que este módulo veio
        # tirar do programa.
        estilos.estilo_de_botao(self.papel)
        if self.grupo not in GRUPOS:
            raise KeyError(f"grupo desconhecido: {self.grupo!r}. Os válidos estão em GRUPOS.")

    @property
    def alternado(self) -> str:
        """O texto de ligado, com o de desligado como resposta para quem não alterna."""
        return self.rotulo_alternado or self.no_botao

    @property
    def no_botao(self) -> str:
        """O texto do botão: o curto quando ele existe, o do menu quando não."""
        return self.rotulo_curto or self.rotulo


CATALOGO: tuple[Comando, ...] = (
    # ---------------------------------------------------------------------------- ARQUIVO
    Comando("abrir_pdf", "Abrir PDF…", ARQUIVO, estilos.NEUTRO, icone="abrir_pdf", rotulo_curto="Abrir PDF"),
    Comando("abrir_recente", "Abrir recente", ARQUIVO, estilos.NEUTRO),
    Comando("abrir_no_leitor", "Abrir no leitor do sistema", ARQUIVO, estilos.NEUTRO),
    Comando(
        "exportar_pgn",
        "Exportar o livro para PGN…",
        ARQUIVO,
        estilos.NEUTRO,
        icone="exportar_pgn",
        rotulo_curto=f"Exportar PDF {strings.SETA} PGN",
    ),
    # Sem item de menu hoje, e por isso ele **precisa** estar aqui: é o comando que só existe
    # como botão, e a S-233 mede exatamente esse caso quando for esconder controle.
    Comando(
        "cancelar_exportacao",
        "Cancelar a exportação",
        ARQUIVO,
        estilos.NEUTRO,
        rotulo_curto="Cancelar exportação",
    ),
    Comando("sair", "Sair", ARQUIVO, estilos.NEUTRO),
    # ----------------------------------------------------------------------------- EDICAO
    Comando("aplicar_fen", "Aplicar a FEN digitada", EDICAO, estilos.NEUTRO, icone="aplicar_fen", destaque=True),
    Comando("apagar_casa", "Apagar a peça da casa selecionada", EDICAO, estilos.NEUTRO, icone="apagar_casa"),
    # O primário do grupo, e o critério de `estilos.PRIMARIO` o confirma: `Ctrl+S` salva.
    # **Em destaque no lugar do exportar** (S-223): a Imagem 1 desenhou "exportar" na fila e
    # omitiu "salvar", e a medida do fluxo diz o contrário -- exporta-se uma vez por livro e
    # salva-se uma vez por diagrama. Uma fila dimensionada por importância em vez de frequência
    # é a barra de 21 botões outra vez.
    Comando("salvar", "Salvar a posição", EDICAO, estilos.PRIMARIO, icone="salvar", destaque=True),
    Comando("salvar_todos", "Salvar todas as posições da página", EDICAO, estilos.NEUTRO),
    Comando("diagrama_anterior", "Diagrama anterior", EDICAO, estilos.NEUTRO, icone="diagrama_anterior"),
    Comando("proximo_diagrama", "Próximo diagrama", EDICAO, estilos.NEUTRO, icone="proximo_diagrama", destaque=True),
    Comando("proximo_da_fila", "Próximo item da fila de revisão", EDICAO, estilos.NEUTRO),
    # Os três da Imagem 2 que **não existiam** (S-229). O roadmap os registrou como achado 4:
    # `grep -rn 'undo' src/` devolvia zero linhas de implementação. Ficam no fim do grupo porque
    # é onde a ordem de declaração já os punha -- a fita e o menu leem daqui, e reordenar seria
    # declarar duas vezes em que ordem os comandos vivem.
    Comando("desfazer", "Desfazer a última mudança no tabuleiro", EDICAO, estilos.NEUTRO, icone="desfazer", rotulo_curto="Desfazer"),
    Comando("refazer", "Refazer o que foi desfeito", EDICAO, estilos.NEUTRO, icone="refazer", rotulo_curto="Refazer"),
    # **"Limpar" é o tabuleiro, e não o editor.** A spec da S-229 aponta para o `clear` de
    # `DiagramEditorModel`, que esvazia o editor inteiro -- listas, vínculo e índice --, e esse não
    # é um estado que uma pilha de posições saiba devolver. O critério de aceite do próprio item
    # decide a leitura: ele lista "limpar" entre as **sete origens de mudança de posição** que o
    # desfazer tem de reverter. Então limpar é esvaziar as 64 casas, e é desfazível.
    Comando("limpar_tabuleiro", "Limpar o tabuleiro", EDICAO, estilos.NEUTRO, icone="limpar_tabuleiro", rotulo_curto="Limpar"),
    # ----------------------------------------------------------------------- VISUALIZACAO
    Comando("pagina_anterior", "Página anterior", VISUALIZACAO, estilos.NEUTRO),
    Comando("proxima_pagina", "Próxima página", VISUALIZACAO, estilos.NEUTRO),
    Comando("ajustar_largura", "Ajustar à largura", VISUALIZACAO, estilos.NEUTRO, icone="ajustar_largura"),
    Comando("ajustar_pagina", "Ajustar à página", VISUALIZACAO, estilos.NEUTRO, icone="ajustar_pagina"),
    # Os dois botões de um caractere. Um rótulo de um caractere é o caso em que "escrito à mão"
    # parece inofensivo -- e é onde a S-225 vai trocar os dois por um deslizador sem ter onde
    # descobrir o que eles faziam, se o texto continuasse sendo a única declaração deles.
    Comando(
        "zoom_menos",
        "Diminuir o zoom da página",
        VISUALIZACAO,
        estilos.NEUTRO,
        icone="zoom_menos",
        rotulo_curto="-",
    ),
    Comando(
        "zoom_mais",
        "Aumentar o zoom da página",
        VISUALIZACAO,
        estilos.NEUTRO,
        icone="zoom_mais",
        rotulo_curto="+",
    ),
    Comando(
        "marcar_diagramas",
        "Marcar os diagramas na página",
        VISUALIZACAO,
        estilos.NEUTRO,
        rotulo_curto="Marcar diagramas",
    ),
    Comando(
        "tirar_caixa",
        "Tirar a caixa do diagrama selecionado",
        VISUALIZACAO,
        estilos.NEUTRO,
        rotulo_curto="Tirar a caixa",
    ),
    Comando("devolver_caixas", "Devolver as caixas tiradas desta página", VISUALIZACAO, estilos.NEUTRO),
    # A escolha de pele (S-221). Fica em VISUALIZACAO porque é o menu onde ela mora, e não
    # ganha ícone: quem desenha submenu com ícone é a fita, e aparência não é comando de fita.
    Comando("aparencia", "Aparência", VISUALIZACAO, estilos.NEUTRO),
    # O segundo eixo de aparência (S-232), e ele fica **ao lado** da pele e não dentro dela. A
    # spec escreveu o caminho `Ver > Aparência > Densidade`, e aninhá-lo custaria a disciplina que
    # vale mais: aqui toda linha de menu é um `Item` de `menu.MENUS`, contável por
    # `acoes_declaradas` -- que é de onde a S-233 vai tirar o inventário de alcance. Um comando
    # montado por dentro de outro submenu não aparece em lista nenhuma.
    Comando("densidade", "Densidade", VISUALIZACAO, estilos.NEUTRO),
    Comando(
        "roda_vira_pagina",
        "A roda do mouse vira a página",
        VISUALIZACAO,
        estilos.NEUTRO,
        rotulo_curto="Roda vira a página",
    ),
    # -------------------------------------------------------------------------------- OCR
    Comando(
        "ler_pagina",
        "Ler esta página",
        OCR,
        estilos.NEUTRO,
        icone="ler_pagina",
        destaque=True,
        rotulo_curto="OCR todos diagramas",
    ),
    # **O primário do grupo é este, e o critério de `estilos.PRIMARIO` diz que devia ser o de
    # cima.** Lá está escrito "a ação que o atalho de teclado também faz", e `Ctrl+R` é
    # `ler_pagina`. O catálogo registra a janela como ela é -- trocar a ênfase é mudar a pele
    # clássica, que a regra 1 da SPEC_APARENCIA proíbe a esta fase. Fica anotado para a S-223,
    # que é quem decide a fila de ações: ou `Ctrl+R` ganha o botão primário, ou o critério de
    # `estilos.PRIMARIO` está errado e é ele que muda.
    Comando(
        "ler_melhor",
        "Ler o melhor diagrama da página",
        OCR,
        estilos.PRIMARIO,
        icone="ler_melhor",
        rotulo_curto="OCR melhor diagrama",
    ),
    Comando(
        "selecionar_area",
        "Selecionar área para ler",
        OCR,
        estilos.NEUTRO,
        icone="selecionar_area",
        rotulo_alternado="Cancelar seleção",
        rotulo_curto="Selecionar área (OCR)",
    ),
    # ----------------------------------------------------------------------------- ACERVO
    Comando("varrer_livro", strings.VARRER_LIVRO, ACERVO, estilos.NEUTRO),
    Comando("recarregar_modelo", "Recarregar o modelo", ACERVO, estilos.NEUTRO),
    Comando("treinar", "Treinar o modelo", ACERVO, estilos.NEUTRO),
    # Os três da linha de conjunto de campo (S-77). Nenhum tem item de menu, e a S-223 decidiu
    # que eles **não** ganham um: anotar verdade de referência sobre a página que não está à
    # vista é como se grava métrica errada.
    Comando("anotar_pagina", "Anotar página", ACERVO, estilos.PRIMARIO),
    Comando("anotar_sem_diagrama", "Sem diagrama", ACERVO, estilos.NEUTRO),
    Comando("tirar_do_campo", "Tirar o selecionado", ACERVO, estilos.NEUTRO),
    # ------------------------------------------------------------------------------ AJUDA
    # Antes da legenda porque as duas são a mesma pergunta em duas metades -- "o que existe"
    # e "que tecla faz" --, e a paleta é a que responde primeiro. Sem ícone e sem `destaque`:
    # ela não é comando de fita nem de fila, e a porta dela é a tecla (S-231).
    Comando("paleta_de_comandos", "Paleta de comandos", AJUDA, estilos.NEUTRO),
    Comando("legenda_de_atalhos", "Atalhos de teclado", AJUDA, estilos.NEUTRO),
    Comando("abrir_log", "Abrir o arquivo de log", AJUDA, estilos.NEUTRO),
    Comando("sobre", "Sobre o ChessVisionOFF", AJUDA, estilos.NEUTRO),
)
"""Os comandos da janela, em ordem de grupo e, dentro dele, na ordem em que já se liam.

**O que entrou:** tudo o que `menu.MENUS` declara, tudo o que `atalhos.ATALHOS` liga, os botões
das duas barras de `ui/pdf_panel.py` e os três da linha de conjunto de campo. São os quatro
lugares que a S-219 nomeia, e o teste cobra os quatro.

**O que não entrou, e por quê.** Os controles de dentro de uma aba -- Galeria, Dataset, Revisão,
Configuração -- não são comandos da *janela*: eles pertencem ao painel que os desenha e não
mudam de lugar quando a pele muda. É a mesma linha que `menu.MENUS` já traçava ao deixar de fora
os botões de navegação da Galeria. `ui/result_panel.py` é o caso de fronteira: os três botões
dele ("Aplicar FEN", "Salvar posição reconhecida", "Salvar todos") **são** comandos da janela e
estão aqui, mas o painel ainda escreve os rótulos dele à mão -- por isso os três não declaram
`rotulo_curto`, que seria uma promessa que ninguém cumpre. Registrado para a S-233."""


NA_LINHA_DE_CAMPO: tuple[str, ...] = ("anotar_pagina", "anotar_sem_diagrama", "tirar_do_campo")
"""Os comandos que moram na linha de conjunto de campo, e **não** ganham item de menu (S-223).

A S-77 os pôs junto da página exibida de propósito: eles anotam *aquela* página, e um comando de
menu que age sobre a página exibida sem que ela esteja à vista é o tipo de gesto que grava verdade
de referência errada. São a única exceção à regra de que todo comando alcança o menu -- e existir
como lista declarada é o que permite o teste cobrar que não haja uma segunda."""


por_acao: dict[str, Comando] = {registro.acao: registro for registro in CATALOGO}
"""Índice por nome. É por aqui que o menu, o painel e a fila da S-223 acham o comando."""

if len(por_acao) != len(CATALOGO):  # pragma: no cover - defeito de declaração, não de execução
    # Levanta na importação, e só este caso levanta: um `acao` repetido faz o índice **perder**
    # em silêncio o primeiro dos dois, e a partir daí metade do programa usa um registro que
    # ninguém escreveu para ele. As outras regras do catálogo são cobradas por teste.
    repetidos = sorted({acao for acao, vezes in Counter(r.acao for r in CATALOGO).items() if vezes > 1})
    raise ValueError(f"comando declarado duas vezes no catálogo: {', '.join(repetidos)}")


def comando(acao: str) -> Comando:
    """O registro daquele comando. Levanta `KeyError` para nome que não existe.

    Levanta em vez de devolver `None`, como `tokens.cor` e `estilos.estilo_de_botao`: um nome
    escrito errado que virasse botão sem rótulo é pior que a exceção -- ele desenha.
    """
    if acao not in por_acao:
        raise KeyError(f"comando desconhecido: {acao!r}. Os declarados estão em CATALOGO.")
    return por_acao[acao]


def rotulo(acao: str) -> str:
    """O rótulo longo -- o que o menu mostra."""
    return comando(acao).rotulo


def rotulo_de_botao(acao: str) -> str:
    """O rótulo curto -- o que o botão mostra. Igual ao longo quando não há um curto."""
    return comando(acao).no_botao


def rotulo_alternado(acao: str) -> str:
    """O rótulo de **ligado** daquele comando. Igual ao normal quando ele não alterna."""
    return comando(acao).alternado


def papel(acao: str) -> str:
    """O papel de botão daquele comando: `PRIMARIO`, `DESTRUTIVO` ou `NEUTRO`."""
    return comando(acao).papel


def estilo(acao: str) -> str:
    """O nome de estilo `ttk` daquele comando, pronto para `ttk.Button(style=...)`.

    Existe para que o painel não precise escrever `estilos.estilo_de_botao(estilos.PRIMARIO)`:
    era ali que a ênfase ficava declarada pela segunda vez, longe de qualquer regra que a
    comparasse com a dos outros botões do mesmo grupo.
    """
    return estilos.estilo_de_botao(papel(acao))


def rotulo_do_grupo(grupo: str) -> str:
    """Como o grupo se escreve num cabeçalho. Levanta `KeyError` para grupo que não existe."""
    if grupo not in _ROTULOS_DE_GRUPO:
        raise KeyError(f"grupo desconhecido: {grupo!r}. Os válidos estão em GRUPOS.")
    return _ROTULOS_DE_GRUPO[grupo]


def do_grupo(grupo: str) -> tuple[Comando, ...]:
    """Os comandos daquele grupo, na ordem de declaração. É a fonte da fita da S-227."""
    rotulo_do_grupo(grupo)
    return tuple(registro for registro in CATALOGO if registro.grupo == grupo)


def em_destaque() -> tuple[Comando, ...]:
    """Os comandos da fila curta da pele "Foco" (S-223), na ordem de declaração.

    **Quatro, e todos têm atalho de teclado** -- que é o critério da S-223, e não o gosto: a
    mesma lógica com que `estilos.PRIMARIO` é definido como *"a ação que o atalho também faz"*.

    Não são exatamente os quatro da Imagem 1. Ela desenhou "exportar" e omitiu "salvar", e a
    medida do fluxo inverte os dois: exporta-se uma vez por livro e salva-se uma vez por
    diagrama. O quarto lugar foi para `salvar`; `aplicar_fen` ganhou `Ctrl+Enter`, que lhe
    faltava, e a razão está em `ui/atalhos.py`.
    """
    return tuple(registro for registro in CATALOGO if registro.destaque)


def fila_de_destaque() -> tuple[tuple[Comando, ...], ...]:
    """A fila da pele "Foco", já agrupada: uma tupla por grupo, na ordem de `GRUPOS`.

    **O separador não está aqui, e é de propósito.** Devolver grupos em vez de uma lista plana
    com marcas faz "separador só entre grupos, nunca na ponta" deixar de ser regra a cobrar e
    virar consequência da forma: quem desenha põe uma barra **entre** tuplas consecutivas, e não
    há onde pôr uma sobrando. Grupo sem comando em destaque não aparece.

    A ordem é a do catálogo, e não a da imagem. A Imagem 1 começa por "ler"; aqui a Edição vem
    antes do OCR porque é a ordem de `GRUPOS`, que é a da barra de menus. Reordenar a fila seria
    declarar pela segunda vez em que ordem os comandos vivem -- e é disso que a S-219 tirou o
    programa.
    """
    grupos = tuple(tuple(registro for registro in do_grupo(grupo) if registro.destaque) for grupo in GRUPOS)
    return tuple(grupo for grupo in grupos if grupo)


def primarios_por_grupo() -> dict[str, list[str]]:
    """`grupo → os comandos PRIMARIO dele`. Mais de um em qualquer grupo é o defeito.

    A regra é a de `ui/estilos.py:31-36` -- *uma ênfase por barra, nunca duas* --, e é aqui que
    ela **finalmente se afirma sem abrir janela**: enquanto a ênfase morava no `style=` de cada
    botão, contá-la exigia montar a barra e ler os widgets.

    Devolve em vez de levantar de propósito. Papel inválido é erro de digitação e levanta na
    construção; duas ênfases no mesmo grupo é decisão de desenho, e derrubar a janela por causa
    dela seria desproporcional -- quem cobra é o teste.
    """
    contagem: dict[str, list[str]] = {grupo: [] for grupo in GRUPOS}
    for registro in CATALOGO:
        if registro.papel == estilos.PRIMARIO:
            contagem[registro.grupo].append(registro.acao)
    return contagem


def acoes_fora_do_catalogo(acoes: Iterable[str]) -> list[str]:
    """Os nomes pedidos que o catálogo não conhece, ordenados. Vazio é o estado correto.

    O outro sentido da trava de `menu.comandos_faltando`: lá, comando declarado que ninguém
    amarrou; aqui, comando amarrado que ninguém declarou.
    """
    return sorted({acao for acao in acoes if acao and acao not in por_acao})
