"""A barra de menus da janela, declarada como dado (S-161).

**O que havia antes: nada.** `grep -rn "tk.Menu" src/ app_tkinter.py` devolvia vazio. Os ~70
comandos da janela eram botões permanentemente visíveis, e isso produz três consequências juntas:
as barras ocupavam 20% da altura (S-151), a ação rara competia com a frequente pelo mesmo olhar, e
**o que não era botão não existia** — não havia "Abrir recente", nem "Abrir o log", nem a lista dos
dez atalhos, que depois da S-150 deixou de ser conveniência (num notebook, `Ctrl+S` era o único
caminho para salvar).

**Declarado como dado, e é isso que o torna verificável.** `MENUS` é uma tupla de tuplas: nenhum
`tkinter` até `montar`. Um teste percorre a declaração e afirma que todo comando com atalho mostra
o acelerador, sem abrir janela -- e `montar` recusa uma declaração cujo comando ninguém amarrou, em
vez de desenhar um item de menu que não faz nada.

**O que o menu não é.** Ele não substitui botão: dá casa ao comando raro e ao que não cabia em
barra nenhuma. O botão de salvar continua na tela porque salvar é o gesto do minuto a minuto; o
"Abrir o log" nunca teve botão e nem devia ter.

**O rótulo saiu daqui na S-324, e a fronteira é essa.** Este módulo decide *onde na barra de
menus*; `ui/comandos.py` decide *o que o comando é* -- como ele se chama, a que grupo pertence,
com que ênfase se desenha. `MENUS` referencia o catálogo em vez de repetir o texto, e `montar`
ganhou a trava no sentido que faltava: item cujo `acao` ninguém registrou levanta, como já
levantava o item que ninguém amarrou a uma função.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # só para as anotações; ver a nota de `montar` sobre o import tardio
    pass


# Apelidado: neste módulo `comandos` já é o nome do mapa `acao -> função` que `montar` recebe, e
# duas coisas com o mesmo nome no mesmo arquivo é como se lê o errado. `strings` saiu junto: o
# único uso dele aqui era o rótulo de "Varrer o livro", que agora mora no catálogo.
from . import comandos as catalogo

logger = logging.getLogger(__name__)

__all__ = [
    "APARENCIA",
    "DENSIDADE",
    "MENUS",
    "Item",
    "Menu",
    "acoes_declaradas",
    "acoes_fora_do_catalogo",
    "comandos_faltando",
]

COMANDO = "COMANDO"
INTERRUPTOR = "INTERRUPTOR"
"""Item com marca de ligado/desligado -- os dois de visualização que o `AppState` já guarda."""

SEPARADOR = "SEPARADOR"
RECENTES = "RECENTES"
"""Submenu montado na hora, com os livros que o `AppState` lembra (S-156)."""

DENSIDADE = "DENSIDADE"
"""Submenu de `radiobutton`, um por densidade de `ui/pele.py` (S-232).

Irmão de `APARENCIA` e não filho: os dois são eixos de aparência, e o que os separa é que a pele
**sugere** a densidade e a pessoa **decide**. Ver o comentário no catálogo sobre por que o caminho
ficou `Ver > Densidade` e não `Ver > Aparência > Densidade`."""

APARENCIA = "APARENCIA"
"""Submenu de `radiobutton`, um por pele registrada em `ui/pele.py` (S-221).

**Montado do registro, e não listado à mão** -- é o mesmo princípio de `RECENTES`, com uma
diferença: o acervo muda enquanto o programa roda e por isso o submenu de livros se refaz a cada
abertura; o registro de peles é fixo na importação. O que varia aqui é a **marca**, e disso quem
cuida é o `StringVar`."""


@dataclass(frozen=True)
class Item:
    """Uma linha de menu: **qual** comando e de que tipo. O que ele *é* mora em `ui/comandos.py`.

    O rótulo saiu daqui na S-324. Ele continua legível como `item.rotulo` -- agora derivado do
    catálogo, e não guardado -- porque o menu escrevia o texto que `ui/pdf_panel.py` escrevia de
    novo, com outra redação, e nada comparava os dois.
    """

    acao: str = ""
    tipo: str = COMANDO

    @property
    def rotulo(self) -> str:
        """O texto da linha, tirado do catálogo. Vazio no separador, que não tem comando."""
        return catalogo.rotulo(self.acao) if self.acao else ""


@dataclass(frozen=True)
class Menu:
    titulo: str
    itens: tuple[Item, ...] = field(default_factory=tuple)


def _sep() -> Item:
    return Item(tipo=SEPARADOR)


MENUS: tuple[Menu, ...] = (
    Menu(
        "Arquivo",
        (
            Item("abrir_pdf"),
            Item("abrir_recente", RECENTES),
            Item("abrir_no_leitor"),
            _sep(),
            Item("exportar_pgn"),
            Item("cancelar_exportacao"),
            _sep(),
            Item("sair"),
        ),
    ),
    Menu(
        "Editar",
        (
            # Os três da S-229 abrem o menu, que é onde todo editor os põe -- e é onde quem
            # procura por eles olha primeiro, antes de saber que existe `Ctrl+Z` aqui.
            Item("desfazer"),
            Item("refazer"),
            _sep(),
            Item("aplicar_fen"),
            Item("apagar_casa"),
            Item("limpar_tabuleiro"),
            _sep(),
            Item("salvar"),
            Item("salvar_todos"),
            _sep(),
            Item("diagrama_anterior"),
            Item("proximo_diagrama"),
            Item("proximo_da_fila"),
        ),
    ),
    Menu(
        "Ver",
        (
            Item("pagina_anterior"),
            Item("proxima_pagina"),
            Item("primeira_pagina"),
            Item("ultima_pagina"),
            _sep(),
            Item("zoom_menos"),
            Item("zoom_mais"),
            Item("ajustar_largura"),
            Item("ajustar_pagina"),
            _sep(),
            Item("marcar_diagramas", INTERRUPTOR),
            # Ao lado do interruptor que liga a marcação, e não em Ferramentas: os dois falam
            # do mesmo objeto -- os retângulos sobre a página --, e a diferença entre eles é
            # "todos" contra "este" (S-177).
            Item("tirar_caixa"),
            Item("devolver_caixas"),
            _sep(),
            Item("roda_vira_pagina", INTERRUPTOR),
            _sep(),
            Item("aparencia", APARENCIA),
            Item("densidade", DENSIDADE),
        ),
    ),
    Menu(
        "Ferramentas",
        (
            Item("ler_pagina"),
            Item("ler_melhor"),
            Item("selecionar_area"),
            _sep(),
            # Um comando, e não dois: a varredura do livro alimenta a Galeria **e** a fila de
            # revisão na mesma passada (S-119). Enquanto eram duas passadas, "Varrer a fila de
            # revisão" era um segundo item aqui, com o mesmo custo do primeiro.
            Item("varrer_livro"),
            _sep(),
            Item("recarregar_modelo"),
            Item("treinar"),
        ),
    ),
    Menu(
        "Estudo",
        (
            # A aba tem barra própria, e mesmo assim tudo isto tem item de menu -- é a regra 2 da
            # SPEC_APARENCIA: o que a pele esconde, o menu alcança. Com vinte e quatro comandos
            # novos (S-280), um menu só é o que impede a barra da sala de virar a pilha de botões
            # que a S-151 mediu.
            Item("estudo_do_diagrama"),
            Item("estudo_da_posicao_inicial"),
            Item("estudo_aplicar_fen"),
            _sep(),
            Item("lance_anterior"),
            Item("proximo_lance"),
            Item("inicio_da_linha"),
            Item("fim_da_linha"),
            _sep(),
            Item("promover_variante"),
            Item("promover_a_principal"),
            Item("rebaixar_variante"),
            Item("apagar_variante"),
            Item("apagar_continuacao"),
            _sep(),
            Item("simbolo_do_lance"),
            _sep(),
            Item("virar_tabuleiro"),
            Item("trocar_vez"),
            Item("mostrar_diagrama"),
            _sep(),
            # Os três da Fase 47: o que só este programa pode oferecer, porque só ele tem a página
            # do livro do lado.
            Item("linha_do_livro"),
            Item("ir_para_a_pagina"),
            _sep(),
            Item("analisar_posicao"),
            Item("analise_continua"),
            Item("variante_do_motor"),
            Item("partidas_da_posicao"),
            _sep(),
            Item("modo_treino"),
            _sep(),
            Item("colar_estudo"),
            Item("abrir_pgn"),
            _sep(),
            Item("copiar_fen"),
            Item("salvar_estudo"),
            Item("exportar_estudo_md"),
            Item("exportar_estudo_html"),
            Item("exportar_estudo_rtf"),
            Item("estudo_para_o_texto"),
        ),
    ),
    Menu(
        "Texto",
        (
            # A aba tem barra própria, e mesmo assim tudo isto tem item de menu -- é a regra 2 da
            # SPEC_APARENCIA: o que a pele esconde, o menu alcança. Com vinte e oito comandos
            # novos, um menu só é o que impede a barra da aba de virar a pilha de botões que a
            # S-151 mediu.
            Item("ler_folha"),
            Item("folha_da_pagina_aberta"),
            Item("modo_bloco", INTERRUPTOR),
            _sep(),
            Item("abrir_texto"),
            Item("salvar_texto"),
            Item("salvar_texto_como"),
            _sep(),
            Item("recortar"),
            Item("copiar"),
            Item("colar"),
            Item("selecionar_tudo"),
            _sep(),
            Item("negrito"),
            Item("italico"),
            Item("sublinhado"),
            Item("tachado"),
            Item("limpar_formato"),
            _sep(),
            Item("cor_do_texto"),
            Item("realce"),
            Item("limpar_cor"),
            _sep(),
            Item("estilo_titulo"),
            Item("estilo_prosa"),
            Item("estilo_notacao"),
            Item("estilo_legenda"),
            _sep(),
            # **O alinhamento entra item a item, e não como submenu.** O menu é a rede de segurança
            # da regra 2 da SPEC_APARENCIA -- o que a pele esconde, ele alcança --, e um submenu
            # esconde os quatro atrás de mais um clique justamente para quem não achou o botão. A
            # barra da aba é que os agrupa, porque lá o espaço é o que falta (S-259).
            Item("alinhar_esquerda"),
            Item("alinhar_centro"),
            Item("alinhar_direita"),
            Item("justificar"),
            _sep(),
            Item("aumentar_corpo"),
            Item("diminuir_corpo"),
            Item("corpo_normal"),
            _sep(),
            Item("maiusculas"),
            Item("minusculas"),
            Item("capitular"),
            _sep(),
            Item("paleta_de_glifos"),
            Item("inserir_figurina"),
            Item("inserir_avaliacao"),
            _sep(),
            Item("achar"),
            Item("substituir"),
            # `substituir_todos` **não** está aqui: ele é o botão de dentro da janela de
            # busca, e como item de menu abria a mesma janela que "Substituir…" -- dois
            # rótulos para uma ação (S-343). Ver `comandos.NA_JANELA_DE_BUSCA`.
            Item("marcar_fora_do_lexico"),
            Item("limpar_marcas_do_lexico"),
            _sep(),
            # A vista da aba: o que muda como o texto **aparece**, e não o que ele é. Ficam no menu
            # Texto e não no menu Ver porque o menu Ver é da página do PDF -- o critério dos seis
            # menus é a pergunta que cada um responde, e a desta aba é "o texto desta folha".
            Item("aproximar_texto"),
            Item("afastar_texto"),
            Item("zoom_do_texto_normal"),
            Item("quebrar_linha", INTERRUPTOR),
            _sep(),
            Item("exportar_txt"),
            Item("exportar_md"),
            Item("exportar_html"),
            Item("exportar_rtf"),
            Item("exportar_pdf_pesquisavel"),
        ),
    ),
    Menu(
        "Ajuda",
        (
            Item("paleta_de_comandos"),
            Item("legenda_de_atalhos"),
            Item("abrir_log"),
            _sep(),
            Item("sobre"),
        ),
    ),
)
"""A barra inteira, como dado.

**Seis menus, e o critério de cada um é uma pergunta.** Arquivo: que documento. Editar: o que
muda no diagrama aberto. Ver: como a página aparece. Ferramentas: o que roda sobre o livro. Texto:
o que muda no texto da folha aberta. Ajuda: o que o programa sabe sobre si.

**O sexto nasceu com a Fase 37**, e nasceu por tamanho: os vinte e oito comandos do editor cabem
em "Editar" pela pergunta -- os dois mexem no que está aberto agora --, e não cabem pelo desenho.
"Editar" tem catorze itens sobre o **diagrama**, e afogá-los em vinte e oito sobre o **texto**
tornaria os dois grupos igualmente difíceis de achar. O grupo do catálogo continua sendo EDICAO e
ARQUIVO, que é outra pergunta: o grupo diz *o que o comando é*, o menu diz *onde ele mora*.

O que **não** entrou: os campos de configuração (são estado, não comando), as anotações do conjunto
de campo (pertencem à página exibida e a S-77 as põe junto dela de propósito) e os botões de
navegação da Galeria (são de dentro de uma aba). Um menu que listasse os 70 controles não seria um
mapa da janela -- seria a mesma pilha de botões noutra vertical."""


def acoes_declaradas() -> list[str]:
    """Todo nome de comando que a barra usa, em ordem de declaração."""
    return [item.acao for menu in MENUS for item in menu.itens if item.tipo != SEPARADOR]


def comandos_faltando(comandos: Mapping[str, object]) -> list[str]:
    """Os comandos declarados que ninguém amarrou. Vazio é o estado correto.

    O submenu de recentes fica de fora: ele não tem função própria -- quem o preenche é o
    `recentes` de `montar`, e cada livro vira uma função na hora de abrir o menu.
    """
    exigidos = {
        item.acao
        for menu in MENUS
        for item in menu.itens
        if item.tipo in (COMANDO, INTERRUPTOR, APARENCIA, DENSIDADE)
    }
    return sorted(exigidos - set(comandos))


def acoes_fora_do_catalogo() -> list[str]:
    """Os itens declarados que `ui/comandos.py` não conhece. Vazio é o estado correto.

    O sentido que faltava. `comandos_faltando` pega o item que ninguém amarrou a uma função;
    este pega o item que ninguém declarou como comando -- o que, depois da S-324, é o que faria
    uma pele desenhar uma linha sem rótulo, ou nenhuma linha.
    """
    return catalogo.acoes_fora_do_catalogo(acoes_declaradas())
