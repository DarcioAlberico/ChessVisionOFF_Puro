"""A fita da aba Texto, declarada como dado (S-650): abas, grupos e os comandos de cada um.

**A barra de hoje tinha os comandos e não tinha a forma**: botões de texto numa linha que quebrava,
sem grupo nem aba -- e o pedido trouxe a imagem do WordCraft, com a fita do Word. Esta é a forma,
e ela é **dado**: cada item é o nome de um comando do catálogo (`ui/comandos.py`), e quem desenha
é `qt/fita_do_texto.py`. A fita da janela principal (`qt/fita.py`, `comandos.GRUPOS`) não é tocada:
ela tem um conjunto fechado de grupos e serve a outra pergunta.

Os nomes com `@` não são comandos: são os controles que **colhem** um valor em vez de agir -- a
caixa de corpo em pontos, as listas de cor e de realce, a galeria de estilos, o campo da folha, o
motor e o modo bloco. O widget os recebe prontos do painel, que é quem sabe o que eles mostram.

**Pura**, sem toolkit: é o que deixa o inventário do editor (S-256) cobrar, **lendo esta
declaração**, que todo comando da aba está na fita ou na aba Arquivo -- e não uma lista literal num
teste, que envelheceria a cada comando novo (a memória "teste não congela lista do catálogo").
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ABAS",
    "ACESSO_RAPIDO",
    "CONTROLES",
    "CONTROLE_DO_COMANDO",
    "DE_ESTADO",
    "Aba",
    "Grupo",
    "acoes",
    "controles",
    "na_fita",
]


@dataclass(frozen=True)
class Grupo:
    """Um grupo da fita: o nome que aparece embaixo dele e os itens, na ordem."""

    nome: str
    itens: tuple[str, ...]


@dataclass(frozen=True)
class Aba:
    nome: str
    grupos: tuple[Grupo, ...]


CONTROLES = frozenset({"@corpo", "@cor", "@realce", "@galeria", "@folha", "@motor", "@modo_bloco"})
"""Os controles que colhem valor. Ver o cabeçalho."""

ABAS: tuple[Aba, ...] = (
    # **Nenhum grupo passa de ~550 px**, e é regra: a fita quebra entre grupos e não dentro de um, e
    # um grupo mais largo que a coluna da mesa (770 px numa janela de 1.400) era cortado e alargava a
    # aba inteira -- o editor ganhava rolagem horizontal. Por isso os grupos do Word vêm em dois.
    Aba(
        "Arquivo",
        (
            Grupo("Documento", ("abrir_texto", "salvar_texto", "salvar_texto_como")),
            Grupo("Exportar a folha", ("exportar_txt", "exportar_md", "exportar_html", "exportar_rtf")),
            Grupo("Exportar mais", ("exportar_pdf_pesquisavel", "exportar_caderno")),
        ),
    ),
    Aba(
        "Página inicial",
        (
            Grupo("Área de transferência", ("colar", "recortar", "copiar")),
            Grupo("Pincel", ("pincel_de_formatacao", "copiar_formato", "colar_formato")),
            Grupo("Fonte", ("@corpo", "aumentar_corpo", "diminuir_corpo", "corpo_normal")),
            Grupo("Caixa", ("maiusculas", "minusculas", "capitular")),
            Grupo("Ênfase", ("negrito", "italico", "sublinhado", "tachado", "limpar_formato")),
            Grupo("Cor", ("@cor", "limpar_cor", "@realce")),
            Grupo("Parágrafo", ("alinhar_esquerda", "alinhar_centro", "alinhar_direita", "justificar", "marcas_de_formatacao")),
            Grupo("Estilos", ("@galeria",)),
            Grupo("Edição", ("achar", "substituir", "selecionar_tudo")),
        ),
    ),
    Aba(
        "Inserir",
        (
            Grupo("Xadrez", ("inserir_figurina", "inserir_avaliacao", "paleta_de_glifos", "codigo_unicode")),
            Grupo(
                "Diagramas da folha",
                ("diagramas_da_folha_a_esquerda", "diagramas_da_folha_ao_centro", "diagramas_da_folha_como_a_preferencia"),
            ),
            Grupo("Diagramas no texto", ("diagramas_a_esquerda", "texto_ao_lado", "tamanho_da_miniatura")),
        ),
    ),
    Aba(
        "Leitura",
        (
            Grupo("Folha", ("@folha", "@motor", "@modo_bloco")),
            Grupo("Ler", ("ler_folha", "folha_da_pagina_aberta", "ler_folha_de_novo", "ler_ao_chegar")),
            Grupo(
                "Caderno",
                ("marcar_folha_conferida", "voltar_a_versao_anterior", "descartar_correcoes", "indice_do_caderno"),
            ),
        ),
    ),
    Aba(
        "Revisão",
        (
            Grupo("Léxico", ("marcar_fora_do_lexico", "proxima_fora_do_lexico", "limpar_marcas_do_lexico")),
            Grupo("Correções", ("lista_de_correcoes",)),
            Grupo("Parágrafo", ("mover_paragrafo_acima", "mover_paragrafo_abaixo")),
        ),
    ),
    Aba(
        "Exibir",
        (
            Grupo("Mostrar", ("painel_de_navegacao", "bloco_impresso", "quebrar_linha")),
            Grupo("Mesa", ("mesa_de_texto", "mesa_sempre", "destacar_mesa")),
            Grupo("Zoom", ("aproximar_texto", "afastar_texto", "zoom_do_texto_normal", "familia_da_letra")),
            Grupo("Foco", ("modo_foco", "recolher_fita")),
        ),
    ),
)
"""As abas da fita. A primeira é a Arquivo, como no Word, e a que abre é a Página inicial."""

ACESSO_RAPIDO: tuple[str, ...] = ("salvar_texto", "desfazer", "refazer")
"""A barra de acesso rápido, ao lado das abas -- a do WordCraft (`crates/engine/src/ribbon.rs:24`)."""

DE_ESTADO = frozenset(
    {
        "negrito",
        "italico",
        "sublinhado",
        "tachado",
        "alinhar_esquerda",
        "alinhar_centro",
        "alinhar_direita",
        "justificar",
        "pincel_de_formatacao",
        "marcas_de_formatacao",
    }
)
"""Os botões que mostram o que vale sob o cursor (S-650): marcados, desmarcados, ou desmarcados no misto."""


CONTROLE_DO_COMANDO: dict[str, str] = {
    "modo_bloco": "@modo_bloco",
    "cor_do_texto": "@cor",
    "realce": "@realce",
    # Os quatro estilos são as amostras da galeria (S-651): botões de novo ao lado dela eram a mesma
    # escolha duas vezes, e alargavam a fita além da coluna da mesa.
    "estilo_titulo": "@galeria",
    "estilo_prosa": "@galeria",
    "estilo_notacao": "@galeria",
    "estilo_legenda": "@galeria",
}
"""Os comandos do catálogo que, na fita, são um controle: a caixa do modo bloco e as duas listas de
cor. É o que o inventário consulta para não os dar por fora da fita."""


def na_fita(acao: str) -> bool:
    """O comando está na fita -- como botão, ou como o controle que faz o mesmo?"""
    return acao in acoes() or CONTROLE_DO_COMANDO.get(acao, "") in controles()


def acoes() -> tuple[str, ...]:
    """Os comandos da fita e da barra de acesso rápido, na ordem, sem repetir e sem os controles."""
    vistos: dict[str, None] = {}
    for aba in ABAS:
        for grupo in aba.grupos:
            for item in grupo.itens:
                if item not in CONTROLES:
                    vistos.setdefault(item, None)
    for item in ACESSO_RAPIDO:
        vistos.setdefault(item, None)
    return tuple(vistos)


def controles() -> tuple[str, ...]:
    """Os controles que a fita espera receber do painel, na ordem em que aparecem."""
    return tuple(i for aba in ABAS for grupo in aba.grupos for i in grupo.itens if i in CONTROLES)
