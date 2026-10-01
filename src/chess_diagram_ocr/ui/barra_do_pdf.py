"""A barra do painel do PDF como dado: grupos por tarefa, e o que vai para o "Mais" (S-528).

**O que havia, medido em 2026-09-04 na janela a 1400x950.** `qt/painel_do_pdf.py` montava duas
`BarraFluida` com dezesseis controles de **texto** -- `QPushButton` e `QCheckBox` --, e elas
quebravam em duas fileiras a 675 px e em **três** a 520, que é o piso do painel: 176 px de cromo
antes da folha, contra 32 px da barra da sala ao lado. O crítico da S-527 pôs as duas na mesma
foto: *"a diferença de gramática entre as duas barras incomoda muito ao lado"* -- de um lado
ícones de 16 px agrupados por tarefa, do outro "OCR todos diagramas" e "Roda vira a página" em
caixas de texto que refluem.

**A gramática é a mesma, e é por isso que este arquivo é só uma tabela.** A forma -- `Acao`,
`Item`, `cabem`, `dica_de` -- é `ui/barra.py`; o widget é `qt/barra.BarraEmFila`, o mesmo da sala.
Aqui ficam as cinco decisões que são deste painel:

1. **Os grupos são cinco, e são as cinco perguntas de quem lê um livro digitalizado**: qual livro
   (`LIVRO`), que folha (`PAGINA`), como ela aparece (`VISTA`), o que se lê nela (`LEITURA`) e o
   que sai daqui (`EXPORTAR`). Não são os grupos do catálogo: lá `pagina_anterior` é
   `VISUALIZACAO` e `ler_melhor` é `OCR`, porque a pergunta de lá é *em que menu*. A cobertura é
   `comandos.NAS_BARRAS_DO_PDF`, inteira e nada além dela, cobrada nos dois sentidos.
2. **Duas ações com texto, e as duas são as pontas do trabalho**: "Abrir PDF" é o que se faz antes
   de tudo, e "OCR melhor diagrama" é o que a tela existe para fazer -- é o único `PRIMARIO` do
   painel, e a ênfase vem do catálogo (S-324). As outras doze são traço de 16 px com o rótulo e a
   tecla na dica, como na sala.
3. **O par de página é um par**, com a mesma prioridade: `◀` sem `▶` é meia navegação. E o campo
   `[21] de 289` não é ação -- é um `QSpinBox` pendurado na fila por `BarraEmFila.encaixar`, que o
   faz aparecer e sumir junto com as duas setas. Pô-lo numa segunda linha era metade do defeito.
4. **Os dois botões de zoom vão para o "Mais", e é decisão e não corte.** O deslizador logarítmico
   da S-225 fica logo abaixo da folha, com a porcentagem ao lado: `−` e `+` na fila seriam o
   terceiro controle do mesmo número na mesma tela. Eles continuam a um clique, e continuam em
   `Ctrl+-` / `Ctrl++`.
5. **Marcar diagramas e roda vira a página são preferências, não gestos.** Liga-se uma vez e
   esquece-se; eram dois `QCheckBox` na fila -- ~230 px permanentes -- e agora são dois itens
   marcáveis do "Mais", que é onde o menu da janela já os oferece.

**As teclas não são registradas por esta barra.** `sequencia_de` devolve sempre `""`: os dezesseis
comandos são da janela e já têm dono no menu (`atalhos.ATALHOS`), e registrá-los de novo aqui daria
duas donas para a mesma tecla -- que é justamente a colisão que `atalhos.conferir_dono` acusa. Na
sala é o contrário, e por isso o gancho existe: `TECLAS_DA_SALA` só vale dentro da aba.

Nada de `PyQt6`: quem monta widget não decide, e quem decide é afirmável sem abrir janela.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from . import barra as _barra
from .barra import ICONE_DO_MAIS, MAIS, ROTULO_DO_MAIS, SEPARADOR_DA_TECLA, Item, cabem, dica_de

__all__ = [
    "ACOES",
    "COM_LIVRO",
    "EXPORTAR",
    "GRUPOS",
    "ICONE_DO_MAIS",
    "LEITURA",
    "LIVRO",
    "MAIS",
    "METODOS_DO_PAINEL",
    "MODOS",
    "PAGINA",
    "ROTULO_DO_MAIS",
    "SEM_LIVRO",
    "SEPARADOR_DA_TECLA",
    "TRANCADO",
    "VISTA",
    "Acao",
    "Item",
    "acao",
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

# Em minúsculas, e é o formato de `barra_da_sala.POSICAO`: é chave, não texto de tela.
LIVRO = "livro"
PAGINA = "pagina"
VISTA = "vista"
LEITURA = "leitura"
EXPORTAR = "exportar"

GRUPOS: tuple[str, ...] = (LIVRO, PAGINA, VISTA, LEITURA, EXPORTAR)
"""Os cinco, na ordem da barra -- que é a ordem em que se usa o painel: abre-se o livro, vai-se à
folha, enquadra-se, lê-se, e no fim exporta-se o livro inteiro."""

_ROTULOS_DE_GRUPO: dict[str, str] = {
    LIVRO: "Livro",
    PAGINA: "Página",
    VISTA: "Vista",
    LEITURA: "Leitura",
    EXPORTAR: "Exportar",
}
"""Como o grupo se escreve quando vira cabeçalho de seção no menu "Mais"."""

METODOS_DO_PAINEL: dict[str, str] = {
    "abrir_pdf": "abrir_pdf",
    "abrir_no_leitor": "abrir_no_leitor_do_sistema",
    "pagina_anterior": "pagina_anterior",
    "proxima_pagina": "proxima_pagina",
    "ajustar_largura": "ajustar_a_largura",
    "ajustar_pagina": "ajustar_a_pagina",
    "zoom_menos": "diminuir_zoom",
    "zoom_mais": "aumentar_zoom",
    "marcar_diagramas": "alternou_marcacao",
    "roda_vira_pagina": "alternou_virada",
    "ler_melhor": "ler_o_melhor",
    "ler_pagina": "ler_a_pagina",
    "selecionar_area": "alternar_selecao",
    "tirar_caixa": "dispensar_a_selecionada",
    "exportar_pgn": "pedir_exportacao",
    "cancelar_exportacao": "pedir_cancelamento",
}
"""Comando do catálogo -> método de `PainelDoPdf`, no formato de `sala_declarada.COMANDOS_DA_ABA`.

**A tabela é a declaração, e o widget não conhece método nenhum.** Antes disto, seis dos dezesseis
controles eram ligados por `lambda` escrito no meio da montagem -- `lambda: self.leitura_pedida
.emit(True)` --, e um `lambda` no ponto de montagem é o lugar onde um botão deixa de fazer o que o
menu faz sem que nada acuse. Os dois nomes que divergem do comando são os dois que emitem sinal em
vez de agir (`ler_o_melhor`, `pedir_exportacao`): a leitura e a exportação são da janela, e o
painel só diz que pediram."""


@dataclass(frozen=True)
class Acao(_barra.Acao):
    """Uma ação da barra do PDF. A forma é `ui/barra.Acao`; aqui não há campo novo nenhum.

    A classe existe porque `GRUPOS`, `IRMAS` e `METODOS` são `ClassVar`: são elas que fazem a
    mesma forma servir a duas tabelas sem que uma enxergue a outra.
    """

    GRUPOS: ClassVar[tuple[str, ...]] = GRUPOS


ACOES: tuple[Acao, ...] = (
    # ------------------------------------------------------------------------------ LIVRO
    # Abrir é o passo de antes, e é o único da fila que se faz com a tela vazia -- por isso tem
    # texto e por isso o grupo `LIVRO` continua ligado quando não há livro (ver `_DESLIGADOS`).
    #
    # **Prioridade 3 e não 6** (segunda rodada, 2026-09-05): o crítico mediu a fila a 520 px -- o
    # piso do painel até a S-552 -- e "Abrir PDF" era um dos primeiros a cair no "Mais". Um botão
    # que se faz **antes de tudo**, e que é a única saída do estado sem livro, não pode sair da
    # fila antes de "Ajustar à largura". `ler_pagina` e `ajustar_largura` desceram um degrau para
    # abrir o lugar; a ordem dos outros não mudou.
    Acao("abrir_pdf", LIVRO, "abrir_pdf", prioridade=3, com_texto=True),
    Acao(
        "abrir_no_leitor",
        LIVRO,
        "leitor",
        principal=False,
        dica="Abre o livro no leitor de PDF do sistema, na janela dele: rolagem contínua e busca\n"
        "de texto. Fica cinza enquanto não há livro aberto.",
    ),
    # ----------------------------------------------------------------------------- PAGINA
    # **Prioridade 2 e um par**: virar folha é o gesto mais repetido do painel, e uma seta sem a
    # outra é meia navegação. O campo `[21] de 289` é encaixado depois de "Página anterior" e
    # acompanha as duas.
    Acao("pagina_anterior", PAGINA, "folha_anterior", prioridade=2),
    Acao("proxima_pagina", PAGINA, "folha_seguinte", prioridade=2),
    # ------------------------------------------------------------------------------ VISTA
    Acao("ajustar_largura", VISTA, "ajustar_largura", prioridade=6),
    Acao("ajustar_pagina", VISTA, "ajustar_pagina", prioridade=7),
    Acao(
        "zoom_menos",
        VISTA,
        "zoom_menos",
        principal=False,
        dica="O deslizador logo abaixo da folha faz o mesmo, com a porcentagem ao lado.",
    ),
    Acao(
        "zoom_mais",
        VISTA,
        "zoom_mais",
        principal=False,
        dica="O deslizador logo abaixo da folha faz o mesmo, com a porcentagem ao lado.",
    ),
    Acao(
        "marcar_diagramas",
        VISTA,
        "marcar",
        principal=False,
        marcavel=True,
        dica="Os retângulos numerados que a detecção achou, desenhados sobre a folha.\n"
        "Desligar não apaga a detecção: só para de desenhá-la.",
    ),
    Acao(
        "roda_vira_pagina",
        VISTA,
        "roda",
        principal=False,
        marcavel=True,
        dica="Com a folha inteira na tela, a roda passa para a próxima em vez de rolar.\n"
        "Desligada, a roda rola a folha ampliada como em qualquer leitor.",
    ),
    # ---------------------------------------------------------------------------- LEITURA
    # O único `PRIMARIO` do painel, e a ênfase é do catálogo (S-324/S-506): abrir o livro é o
    # passo de antes, ler o diagrama é o que esta tela faz.
    Acao("ler_melhor", LEITURA, "ler_melhor", prioridade=1, com_texto=True),
    Acao("ler_pagina", LEITURA, "ler_pagina", prioridade=4),
    Acao(
        "selecionar_area",
        LEITURA,
        "selecionar_area",
        prioridade=5,
        marcavel=True,
        dica="Enquanto ligado, arrastar sobre a folha recorta em vez de mover a página --\n"
        "e o que o retângulo cercar é reconhecido na hora.",
    ),
    Acao(
        "tirar_caixa",
        LEITURA,
        "tirar_a_caixa",
        principal=False,
        dica="Tira da página o retângulo do diagrama selecionado. Sem seleção não há o que tirar:\n"
        "clique com o botão direito sobre a caixa antes.",
    ),
    # --------------------------------------------------------------------------- EXPORTAR
    # O livro inteiro para PGN é de uma vez por acervo, e o cancelar é o par dele -- os dois no
    # fim da fila, e no "Mais" quando a coluna é estreita. Cancelar também mora no rodapé da
    # janela enquanto a exportação roda, que é o lugar em que a barra de progresso está.
    Acao("exportar_pgn", EXPORTAR, "exportar_pgn", prioridade=8),
    Acao("cancelar_exportacao", EXPORTAR, "cancelar", prioridade=9),
)
"""As dezesseis ações do painel do PDF: `comandos.NAS_BARRAS_DO_PDF` inteira, e nada além dela.

**A ordem das prioridades é a da frequência, medida contra os 520 px do piso do painel**: 1 ler o
melhor diagrama, 2 o par de página, 3 ler a página inteira, 4 selecionar área, 5 ajustar à largura,
6 abrir o livro, 7 ajustar à página, 8 exportar, 9 cancelar. Duas com texto e oito só com ícone; as
seis restantes nunca têm botão."""

por_acao: dict[str, Acao] = {registro.acao: registro for registro in ACOES}

Acao.IRMAS = ACOES
Acao.METODOS = METODOS_DO_PAINEL


def acao(nome: str) -> Acao:
    """O registro daquela ação. Levanta `KeyError` para nome que a barra não tem."""
    if nome not in por_acao:
        raise KeyError(f"ação fora da barra do PDF: {nome!r}")
    return por_acao[nome]


def rotulo_do_grupo(grupo: str) -> str:
    if grupo not in _ROTULOS_DE_GRUPO:
        raise KeyError(f"grupo desconhecido: {grupo!r}. Os válidos estão em GRUPOS.")
    return _ROTULOS_DE_GRUPO[grupo]


def do_grupo(grupo: str) -> tuple[Acao, ...]:
    rotulo_do_grupo(grupo)
    return tuple(registro for registro in ACOES if registro.grupo == grupo)


def principais() -> tuple[Acao, ...]:
    """As que ganham botão, na ordem da barra."""
    return tuple(registro for registro in ACOES if registro.principal)


def secundarias() -> tuple[Acao, ...]:
    """As que vão direto para o "Mais", na ordem da barra."""
    return tuple(registro for registro in ACOES if not registro.principal and not registro.dentro_de)


def sequencia_de(nome: str) -> str:
    """Vazio, sempre: as teclas destes dezesseis são da janela. Ver o cabeçalho."""
    _ = nome
    return ""


# ------------------------------------------------------------------------------------ os modos

SEM_LIVRO = "sem-livro"
"""Nenhum PDF aberto. Não há folha para virar, enquadrar, ler nem exportar -- e os botões dizem
isso em vez de responder com uma frase no rodapé. `LIVRO` continua ligado: "Abrir PDF" é
justamente a saída deste modo."""

COM_LIVRO = "com-livro"

TRANCADO = "trancado"
"""Uma operação longa da janela está em curso (varredura, exportação, treino).

**`EXPORTAR` continua ligado, e é o item.** É o mesmo motivo pelo qual `trancar` nunca foi um
`setEnabled` no painel inteiro: o cancelar só existe durante a exportação, que é exatamente quando
tudo o mais está trancado -- obedecer à trava faria o botão ficar cinza na única situação em que
ele serve. Quem decide entre exportar e cancelar é a condição de cada um, não o modo."""

MODOS: tuple[str, ...] = (SEM_LIVRO, COM_LIVRO, TRANCADO)

_DESLIGADOS: dict[str, frozenset[str]] = {
    SEM_LIVRO: frozenset({PAGINA, VISTA, LEITURA, EXPORTAR}),
    COM_LIVRO: frozenset(),
    TRANCADO: frozenset({LIVRO, PAGINA, VISTA, LEITURA}),
}


def modo(*, livro: bool, trancado: bool) -> str:
    """O modo do painel a partir de duas perguntas. Trancado ganha: tranca-se com livro aberto."""
    if trancado:
        return TRANCADO
    return COM_LIVRO if livro else SEM_LIVRO


def grupos_desligados(qual: str) -> frozenset[str]:
    """Os grupos cujas ações ficam desabilitadas naquele modo. Levanta para modo desconhecido."""
    if qual not in _DESLIGADOS:
        raise KeyError(f"modo desconhecido: {qual!r}. Os válidos estão em MODOS.")
    return _DESLIGADOS[qual]
