"""O que a aba de texto declara fora do widget (S-240/S-262/S-264/S-266/S-423/S-504).

A tabela `comando -> método`, as duas listas de escolha exclusiva, os limites do zoom da vista, os
três motores de leitura e o que a conferência de léxico pula. Nada aqui toca toolkit.

**A tabela é a parte que mais importa, e a razão é a mesma da sala de estudo.** A janela gera as
ligações a partir dela: um comando novo entra numa linha e chega ao menu, à paleta e às três peles
sozinho. Ela nasceu duplicada -- `cli/editor_inventario.py` de um lado, `app_tkinter._comandos` do
outro, com quarenta linhas de `lambda p: p.negrito()` --, e o sintoma daquela divergência era um
item de menu que não faz nada.

**Ela vale para os dois frontends**, e é por isso que os métodos de `qt/painel_de_texto.py` se
chamam exatamente como os de `ui/texto_panel.py`. Uma segunda tabela seria o lugar onde um comando
some sem ninguém notar.

**`MOTORES` traz o achado da S-423 junto.** O primeiro da lista é o padrão, e ele era o `glifo` --
que precisa de `models/char_classifier.pt`, e esse arquivo **não vem no repositório**. Num clone
novo a aba abria com o motor que não pode funcionar, tendo `auto` na mesma caixa: a primeira
leitura de texto da vida de quem instala falhava por falta de um arquivo.

`ui/texto_panel.py` reexportava tudo o que está aqui, e saiu no corte do Tk (S-506). Quem consome
agora é `qt/painel_de_texto.py`, `qt/janela.py` e `cli/editor_inventario.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ..text import rico

if TYPE_CHECKING:  # pragma: no cover - só o verificador de tipo precisa disto
    from ..text.leitor import MotorDeTexto
else:
    MotorDeTexto = Literal["auto", "camada", "glifo"]

__all__ = [
    "ACOES_PROPRIAS",
    "ALINHAMENTO",
    "CAIXA",
    "COMANDOS_DA_ABA",
    "COMANDO_DA_ESCOLHA",
    "ESCAPE_DA_PALETA",
    "ETIQUETA_DO_LEXICO",
    "MOTORES",
    "ROTULO_DO_CORPO_MISTO",
    "ZOOM_MAXIMO",
    "ZOOM_MINIMO",
    "fora_do_livro",
]

ACOES_PROPRIAS: frozenset[str] = frozenset({"salvar", "desfazer", "refazer", "achar", "substituir"})
"""As ações globais que esta aba atende **enquanto tem o foco** (S-244).

`Ctrl+S` com o cursor no texto salva o texto, e não a posição do tabuleiro. Não é tecla nova: é a
mesma tecla com destino conforme o foco, que é o que qualquer programa faz e o que esta aba não
fazia -- a guarda de `ui/shortcuts.py` cedia a tecla a todo campo de texto (por medição, desde a
S-20), e do outro lado ninguém a ligava. O resultado era um silêncio de duas camadas.

Quem confere que cada ação declarada é de fato atendida é `atalhos.conferir_dono`, na montagem:
declarar e não atender come a tecla e não faz nada, que é pior que não declarar."""

ALINHAMENTO = "alinhamento"
CAIXA = "caixa"
"""Os dois grupos de escolha exclusiva da barra. Chave de `COMANDO_DA_ESCOLHA`, e nada mais."""

COMANDO_DA_ESCOLHA: dict[str, dict[str, str]] = {
    ALINHAMENTO: {
        rico.ALINHAMENTO_ESQUERDA: "alinhar_esquerda",
        rico.ALINHAMENTO_CENTRO: "alinhar_centro",
        rico.ALINHAMENTO_DIREITA: "alinhar_direita",
        rico.ALINHAMENTO_JUSTIFICADO: "justificar",
    },
    CAIXA: {
        rico.CAIXA_ALTA: "maiusculas",
        rico.CAIXA_BAIXA: "minusculas",
        rico.CAIXA_INICIAIS: "capitular",
    },
}
"""Nome do domínio -> comando do catálogo, para as listas da barra (S-259/S-262).

**Existe para o rótulo do item da lista não ser escrito no painel.** `centro` é o nome que o
documento guarda; "Centralizar" é como a interface o chama, e quem tem os rótulos é
`ui/comandos.py`. Sem esta tabela, cada item de menu levaria um rótulo em literal."""

ETIQUETA_DO_LEXICO = "fora_do_lexico"
"""A marca de "o léxico não conhece esta palavra" (S-266).

**Ela não é do documento, e é a única marca desta aba que não é.** Faixa, atributo, bloco e
procedência descrevem o texto e sobrevivem à gravação; esta é **derivada** do texto e do léxico, e
recalculá-la é mais barato e mais correto do que gravá-la -- um `.cvtxt` de ontem com marcas de um
léxico que mudou seria pior que nenhuma marca."""

ROTULO_DO_CORPO_MISTO = "–"
"""O que o mostrador de corpo diz quando não há **um** degrau no alvo (S-292).

Meia-risca e não `"?"` nem `"0"`: `0` é um degrau de verdade -- "este trecho está no corpo do
estilo dele" -- e mostrá-lo onde há dois degraus diferentes na seleção seria o mostrador afirmando
o que ele não sabe."""

ZOOM_MINIMO = -3
ZOOM_MAXIMO = 8
"""Os limites do zoom **da vista** (S-264), em degraus, como o corpo do trecho.

Sobe mais que `rico.CORPO_MAXIMO` porque a pergunta é outra: o corpo de um trecho é hierarquia
dentro da folha, e oito degraus ali seriam outro documento; o zoom é **acuidade de quem lê**, e
quem está conferindo um scan ruim de perto quer o dobro da letra sem mudar nada do que vai ser
gravado."""

ESCAPE_DA_PALETA = "\\"
"""O prefixo das sequências de teclado da S-248. Ver `text/paleta.SEQUENCIAS_DECLARADAS`."""

MOTORES: tuple[MotorDeTexto, ...] = ("auto", "glifo", "camada")
"""Os mesmos três de `text/leitor.py`, e a caixa da barra os oferece nesta ordem.

`auto` é o glifo **com a camada como reserva**: com o classificador no lugar ele lê igual, e sem
ele cai na camada de texto do PDF avisando no log. É a mesma regra do resto do programa --
degradar dizendo, em vez de recusar em silêncio."""


def fora_do_livro(doc: rico.DocumentoRico) -> tuple[tuple[int, int], ...]:
    """Os intervalos do documento que **não** são texto do livro: a marca e o separador (S-266).

    É o que a conferência do léxico pula. `[Diagrama 3]` é referência que o *programa* escreveu, e
    marcá-la como palavra desconhecida seria a aba avisando sobre si mesma -- um aviso que aparece
    em toda folha com diagrama e não diz nada sobre a leitura.
    """
    intervalos: list[tuple[int, int]] = []
    posicao = 0
    for corrida in doc.corridas:
        fim = posicao + len(corrida.texto)
        if corrida.tipo != rico.TEXTO:
            intervalos.append((posicao, fim))
        posicao = fim
    return tuple(intervalos)


COMANDOS_DA_ABA: dict[str, str] = {
    "abrir_texto": "abrir_documento",
    "salvar_texto": "salvar_documento",
    "salvar_texto_como": "salvar_documento_como",
    "exportar_txt": "salvar",
    "ler_folha": "ler",
    "folha_da_pagina_aberta": "sincronizar_com_a_pagina",
    "modo_bloco": "modo_bloco_mudou",
    "cor_do_texto": "escolher_cor",
    "realce": "escolher_realce",
    "paleta_de_glifos": "alternar_paleta",
    "negrito": "negrito",
    "italico": "italico",
    "sublinhado": "sublinhado",
    "tachado": "tachado",
    "limpar_formato": "limpar_formato",
    "limpar_cor": "limpar_cor",
    "achar": "achar",
    "substituir": "substituir",
    "inserir_figurina": "inserir_figurina",
    "inserir_avaliacao": "inserir_avaliacao",
    "estilo_titulo": "estilo_titulo",
    "estilo_prosa": "estilo_prosa",
    "estilo_notacao": "estilo_notacao",
    "estilo_legenda": "estilo_legenda",
    "recortar": "recortar",
    "copiar": "copiar",
    "colar": "colar",
    "selecionar_tudo": "selecionar_tudo",
    "aproximar_texto": "aproximar_texto",
    "afastar_texto": "afastar_texto",
    "zoom_do_texto_normal": "zoom_do_texto_normal",
    "quebrar_linha": "quebrar_linha",
    "marcar_fora_do_lexico": "marcar_fora_do_lexico",
    "limpar_marcas_do_lexico": "limpar_marcas_do_lexico",
    "alinhar_esquerda": "alinhar_esquerda",
    "alinhar_centro": "alinhar_centro",
    "alinhar_direita": "alinhar_direita",
    "justificar": "justificar",
    "aumentar_corpo": "aumentar_corpo",
    "diminuir_corpo": "diminuir_corpo",
    "corpo_normal": "corpo_normal",
    "maiusculas": "maiusculas",
    "minusculas": "minusculas",
    "capitular": "capitular",
    "exportar_md": "exportar_md",
    "exportar_html": "exportar_html",
    "exportar_rtf": "exportar_rtf",
    "exportar_pdf_pesquisavel": "exportar_pdf_pesquisavel",
}
"""Comando do catálogo -> método desta classe que o atende (S-240/S-256).

**A tabela mora aqui, e não na janela nem no inventário, porque o dono do método é esta classe.**
Ela tinha nascido em `cli/editor_inventario.py`, para o inventário poder cobrar que todo comando do
editor tivesse dono; do outro lado, `app_tkinter._comandos` repetia as mesmas linhas em `lambda`.
Duas listas do mesmo par, e a segunda com quarenta linhas de `lambda p: p.negrito()` -- exatamente
a divergência que `ui/comandos.py` tirou dos rótulos, com o agravante de que aqui o sintoma é um
item de menu que não faz nada.

Agora a janela **gera** as ligações desta tabela e o inventário a lê, e um comando novo entra numa
linha só. O nome do comando e o do método divergem em oito casos, e todos por bom motivo:
`ler_folha` é `ler` porque o painel só lê folha, `exportar_txt` é `salvar` porque era assim antes do
catálogo, e `cor_do_texto` é `escolher_cor` porque o comando abre uma lista em vez de pintar."""
