"""O que a aba de texto declara fora do widget (S-240/S-262/S-264/S-266/S-423/S-504).

A tabela `comando -> método`, as duas listas de escolha exclusiva, os limites do zoom da vista, os
três motores de leitura, o que a conferência de léxico pula e quando a digitação fecha um passo de
desfazer. Nada aqui toca toolkit.

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

import re
from collections.abc import Sequence
from dataclasses import dataclass
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
    "DIAGRAMAS_AO_CENTRO",
    "DIAGRAMAS_A_ESQUERDA",
    "ESCAPE_DA_PALETA",
    "FAMILIAS_DA_LETRA",
    "FAMILIA_DA_LETRA_PADRAO",
    "MOTORES",
    "NOME_DA_FAMILIA",
    "NOME_DO_TAMANHO",
    "TAMANHOS_DA_MINIATURA",
    "TAMANHO_DA_MINIATURA_PADRAO",
    "ROTULO_DO_CORPO_MISTO",
    "ZOOM_MAXIMO",
    "ZOOM_MINIMO",
    "Digitacao",
    "alinhamento_dos_diagramas",
    "codigo_unicode",
    "contar_palavras",
    "continua_a_digitacao",
    "digitacao_depois",
    "fora_do_livro",
    "frase_do_lexico",
    "frase_das_palavras",
    "frase_do_rodape",
    "largura_da_miniatura",
    "linha_do_indice",
    "paradas_do_zoom",
    "porcentagem_do_zoom",
    "proxima_familia_da_letra",
    "proximo_tamanho_da_miniatura",
]

PALAVRAS_NA_FRASE = 5
"""Quantas das palavras fora do léxico a frase do rodapé nomeia (item 29). Cinco cabem no rodapé
e já dizem se a conta é de erro de OCR (`qwv`, `zzt`) ou de nome próprio (`Capablanca`)."""


def frase_do_lexico(achadas: Sequence[str], total: int) -> str:
    """A frase da conferência do léxico (S-209/S-266), **com as primeiras palavras** (item 29).

    «3 de 120 palavra(s) fora do léxico» obrigava a rolar a folha atrás das marcas para saber se
    valia a pena olhar; com `(qwv, zzt, Capablanca)` a pessoa decide do rodapé. Repetidas uma
    vez só, na ordem em que aparecem; mais que `PALAVRAS_NA_FRASE` ganham reticências.
    """
    if not achadas:
        return f"Nenhuma das {total} palavra(s) está fora do léxico. Nada foi corrigido (S-209)."
    unicas: list[str] = []
    for palavra in achadas:
        if palavra not in unicas:
            unicas.append(palavra)
    mostradas = ", ".join(unicas[:PALAVRAS_NA_FRASE]) + ("…" if len(unicas) > PALAVRAS_NA_FRASE else "")
    return f"{len(achadas)} de {total} palavra(s) fora do léxico ({mostradas}). Nada foi corrigido (S-209)."

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


def paradas_do_zoom(base: int) -> tuple[int, ...]:
    """Os degraus de zoom que **mudam a letra**, do menor ao maior (S-630). Pura.

    A régua do rodapé tem uma parada por degrau que dá um corpo diferente, e não uma por degrau:
    `tipografia.corpo` não desce de `MINIMO_LEGIVEL`, então numa fonte de sistema de 9 pt os degraus
    −3 e −2 dão os mesmos 7 pt. Uma régua com as doze posições teria duas que não fazem nada, e a
    pessoa concluiria que o controle travou. Dos degraus que empatam, fica o mais perto de zero --
    é o que `aplicar_zoom` grava, e voltar a ele não pula a letra.
    """
    from chess_diagram_ocr.ui import tipografia

    por_corpo: dict[int, int] = {}
    for degrau in range(ZOOM_MINIMO, ZOOM_MAXIMO + 1):
        corpo = tipografia.corpo(degrau, base=base)
        if corpo not in por_corpo or abs(degrau) < abs(por_corpo[corpo]):
            por_corpo[corpo] = degrau
    return tuple(sorted(por_corpo.values()))


def porcentagem_do_zoom(degrau: int, base: int) -> int:
    """O zoom em porcentagem, como o rodapé o escreve: a letra da vista sobre a letra sem zoom. Pura.

    Porcentagem porque é a unidade que todo editor usa para isto (o WordCraft escreve `135%` ao lado
    da régua), e **derivada do corpo**, e não um número novo: é a mesma conta de `tipografia.corpo`
    que o desenho faz, então `100%` é sempre a letra de sem zoom, em qualquer fonte de sistema.
    """
    from chess_diagram_ocr.ui import tipografia

    return round(100 * tipografia.corpo(degrau, base=base) / tipografia.corpo(0, base=base))

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


PAUSA_DA_DIGITACAO = 1.0
"""Segundos sem tecla que fecham o passo de desfazer da digitação.

Mais que o intervalo entre duas teclas de quem digita devagar, menos que a parada de quem terminou
a palavra e foi conferir a folha: o `Ctrl+Z` depois da pausa desfaz o que veio depois dela, e não a
tarde inteira. Não é relógio de gravação -- esse é `text/rascunho.ESPERA_SEGUNDOS`, e responde a
outra pergunta."""


@dataclass(frozen=True)
class Digitacao:
    """O passo de desfazer que a digitação mantém aberto: as teclas seguintes entram nele.

    **Sem isto cada tecla seria um passo**, e desfazer a palavra `cavalo` custaria seis `Ctrl+Z`.
    Com o passo aberto para sempre, um `Ctrl+Z` apagaria o parágrafo inteiro que a pessoa escreveu
    em dez minutos. O passo fecha no que muda a intenção: o cursor que pulou, a pausa, trocar
    escrever por apagar, colar, e toda ferramenta -- quem chama zera o passo nelas.
    """

    cursor: int
    """Onde a última tecla deixou o cursor, em deslocamento do documento."""

    apagando: bool
    """O passo é de apagar (`Backspace`, `Delete`), e não de escrever."""

    quando: float
    """O relógio monotônico da última tecla, em segundos."""


def continua_a_digitacao(
    aberta: Digitacao | None, inicio: int, fim: int, novo: str, *, agora: float
) -> bool:
    """Esta edição -- `[inicio, fim)` trocado por `novo` -- entra no passo aberto? Pura.

    Entra quando continua o gesto: escrever exatamente onde a última tecla deixou o cursor, ou
    apagar encostado nele -- `Backspace` apaga o que termina no cursor, `Delete` o que começa nele.
    Não entra depois de `PAUSA_DA_DIGITACAO`, nem quando se troca escrever por apagar, nem quando
    ela escreve por cima de uma seleção (o cursor pulou para selecionar) ou traz mais de uma letra
    de uma vez (colar é um passo só dele).
    """
    if aberta is None or agora - aberta.quando > PAUSA_DA_DIGITACAO or len(novo) > 1:
        return False
    apagando = not novo
    if apagando != aberta.apagando:
        return False
    if apagando:
        return aberta.cursor in (inicio, fim)
    return inicio == fim == aberta.cursor


def digitacao_depois(inicio: int, fim: int, novo: str, *, agora: float) -> Digitacao | None:
    """O passo que fica aberto depois desta edição -- `None` quando ela mesma o fecha (colar)."""
    if len(novo) > 1:
        return None
    return Digitacao(cursor=inicio + len(novo), apagando=not novo, quando=agora)


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
    "exportar_caderno": "exportar_caderno",
    "diagramas_a_esquerda": "alternar_diagramas_a_esquerda",
    "texto_ao_lado": "alternar_texto_ao_lado",
    "ler_ao_chegar": "alternar_ler_ao_chegar",
    "tamanho_da_miniatura": "mudar_tamanho_da_miniatura",
    "familia_da_letra": "mudar_familia_da_letra",
    "diagramas_da_folha_a_esquerda": "diagramas_da_folha_a_esquerda",
    "diagramas_da_folha_ao_centro": "diagramas_da_folha_ao_centro",
    "diagramas_da_folha_como_a_preferencia": "diagramas_da_folha_como_a_preferencia",
    "pincel_de_formatacao": "pincel_de_formatacao",
    "copiar_formato": "copiar_formato",
    "colar_formato": "colar_formato",
    "marcas_de_formatacao": "alternar_marcas_de_formatacao",
    "painel_de_navegacao": "alternar_navegacao",
    "bloco_impresso": "alternar_bloco_impresso",
    "modo_foco": "alternar_modo_foco",
    "recolher_fita": "alternar_fita",
    "proxima_fora_do_lexico": "proxima_fora_do_lexico",
    "lista_de_correcoes": "mostrar_correcoes",
    "mover_paragrafo_acima": "mover_paragrafo_acima",
    "mover_paragrafo_abaixo": "mover_paragrafo_abaixo",
    "codigo_unicode": "codigo_unicode",
    "ler_folha_de_novo": "ler_de_novo",
    "voltar_a_versao_anterior": "voltar_a_anterior",
    "descartar_correcoes": "descartar_correcoes",
    "indice_do_caderno": "alternar_indice",
    "marcar_folha_conferida": "marcar_conferida",
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


def frase_do_rodape(
    *,
    folha: int | None,
    trechos: int,
    diagramas: int,
    miniaturas: int,
    por_gravar: bool,
    correcoes: int = 0,
    do_caderno: bool = False,
    conferidas: tuple[int, int] | None = None,
    gravado_as: str = "",
) -> str:
    """O rodapé da aba: que folha está na tela, o que ela tem e se há o que gravar. Pura.

    **O rótulo existia e ficava vazio** desde o porte para o Qt. A frase responde às três
    perguntas de quem volta à aba depois de um tempo -- "é a folha certa?", "os diagramas estão
    aqui?", "eu gravei?" -- sem obrigar a olhar o campo da folha, rolar até o fim ou tentar fechar.
    A contagem de miniaturas só aparece quando falta alguma: "3 diagramas" já diz que estão.

    `folha` é o índice 0-based da página, ou `None` para texto sem página de origem. `correcoes`
    é quantos pares antes/depois a mão fez sobre o que o motor leu (`text/correcao`), contados na
    pausa da digitação e na gravação -- é o número que o `.cvtxt` tem de mais caro (item 24).
    `do_caderno` diz que a folha está guardada no caderno do livro (S-612): «Folha 3 do caderno».
    `conferidas` é `(conferidas, folhas do livro)` (S-613), e só aparece com uma conferida ao menos:
    "0 de 289" no rodapé de quem nunca marcou nada seria ruído.
    `gravado_as` é a hora em que o caderno gravou a folha, `"14:32"` (S-655): a resposta a "eu
    gravei?" quando não há nada por gravar. Vazio, a frase não diz nada sobre a gravação.
    """
    if trechos == 0:
        return ""
    if folha is None:
        partes = ["Texto sem folha de origem"]
    else:
        partes = [f"Folha {folha + 1} do caderno" if do_caderno else f"Folha {folha + 1}"]
    partes.append(f"{trechos} trecho(s)")
    if diagramas:
        quantos = f"{diagramas} diagrama(s)"
        if miniaturas < diagramas:
            quantos += f", {miniaturas} com miniatura"
        partes.append(quantos)
    if correcoes:
        partes.append(f"{correcoes} correção(ões)")
    if por_gravar:
        partes.append("por gravar")
    elif gravado_as:
        partes.append(f"gravado às {gravado_as}")
    if conferidas is not None and conferidas[0]:
        partes.append(f"{conferidas[0]} de {conferidas[1]} folhas conferidas")
    return " · ".join(partes)


DIAGRAMAS_AO_CENTRO = ""
DIAGRAMAS_A_ESQUERDA = "esquerda"
"""A preferência «Diagramas no texto» (S-620): centralizados (o padrão, `""`) ou à esquerda. Ela
decide só a marca que ninguém alinhou; o alinhamento escrito na marca vence as duas."""


def alinhamento_dos_diagramas(preferencia: str) -> str:
    """O alinhamento que a marca sem escolha recebe sob esta preferência. Desconhecida vale o padrão."""
    return "esquerda" if preferencia == DIAGRAMAS_A_ESQUERDA else "centro"


TAMANHOS_DA_MINIATURA: dict[str, int] = {"pequeno": 160, "medio": 240, "grande": 320}
"""O tamanho da miniatura do diagrama no texto (S-623), em pixel no corpo do sistema, antes do zoom
da vista. **O padrão é o médio**: na mesa o editor tem metade da tela, e 160 px é pequeno para
conferir uma posição. É vista, e não documento: não vai ao `.cvtxt` nem muda a exportação."""

TAMANHO_DA_MINIATURA_PADRAO = "medio"

NOME_DO_TAMANHO: dict[str, str] = {"pequeno": "pequenas", "medio": "médias", "grande": "grandes"}


def largura_da_miniatura(tamanho: str) -> int:
    """A largura daquele tamanho, em pixel no corpo do sistema. Desconhecido vale o padrão."""
    return TAMANHOS_DA_MINIATURA.get(tamanho, TAMANHOS_DA_MINIATURA[TAMANHO_DA_MINIATURA_PADRAO])


def proximo_tamanho_da_miniatura(tamanho: str) -> str:
    """O comando do menu anda em roda: pequenas, médias, grandes, pequenas."""
    nomes = tuple(TAMANHOS_DA_MINIATURA)
    atual = tamanho if tamanho in TAMANHOS_DA_MINIATURA else TAMANHO_DA_MINIATURA_PADRAO
    return nomes[(nomes.index(atual) + 1) % len(nomes)]


FAMILIA_DA_LETRA_PADRAO = ""
FAMILIAS_DA_LETRA: tuple[str, ...] = (FAMILIA_DA_LETRA_PADRAO, "serifada", "monoespacada")
"""A letra de leitura da folha (S-632): a proporcional do tema (o padrão, `""`), uma serifada do
sistema -- mais perto do impresso, para conferir lado a lado na mesa -- ou a monoespaçada, que separa
`l`/`1`/`I` e `O`/`0`, onde o OCR mais erra. É vista, como o zoom: não vai ao `.cvtxt` nem muda a
exportação, e a notação continua na monoespaçada nas três."""

NOME_DA_FAMILIA: dict[str, str] = {"": "proporcional", "serifada": "serifada", "monoespacada": "monoespaçada"}


def proxima_familia_da_letra(familia: str) -> str:
    """O comando anda em roda, como o das miniaturas: proporcional, serifada, monoespaçada. Desconhecida vale o padrão."""
    atual = familia if familia in FAMILIAS_DA_LETRA else FAMILIA_DA_LETRA_PADRAO
    return FAMILIAS_DA_LETRA[(FAMILIAS_DA_LETRA.index(atual) + 1) % len(FAMILIAS_DA_LETRA)]


_PALAVRA = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")


def contar_palavras(texto: str) -> int:
    """Quantas palavras há no texto (S-655): letras e dígitos seguidos, com o apóstrofo dentro.
    `e4` e `Nf3` contam como palavra, como contam para quem lê a folha. Pura e barata: o rodapé a
    chama na pausa da digitação, e não por tecla."""
    return sum(1 for _ in _PALAVRA.finditer(texto))


def frase_das_palavras(total: int, selecionadas: int | None = None) -> str:
    """`357 palavras`, ou `12 de 357 palavras` com seleção (S-655)."""
    if selecionadas is not None:
        return f"{selecionadas} de {total} palavras"
    return "1 palavra" if total == 1 else f"{total} palavras"


_HEXA = re.compile(r"[Uu]\+([0-9A-Fa-f]{4,6})$|([0-9A-Fa-f]{4})$")


def codigo_unicode(antes: str) -> tuple[int, str] | None:
    """O `Alt+X` do Word (S-659): `(quantos caracteres apagar antes do cursor, o que escrever)`.

    Se o texto antes do cursor termina em 4 dígitos hexadecimais, ou em `U+` e 4 a 6, eles viram o
    caractere; senão, o caractere antes do cursor vira o código dele. `0161` vira `š`, e `š` volta
    a `0161` -- e `Proke0161` vira `Prokeš`. **Sem `U+` são quatro, e não até seis**: as letras de
    `a` a `f` são dígito hexadecimal, e `de0161` leria `DE0161`, que não é caractere nenhum.
    `None` quando não há o que trocar.
    """
    achado = _HEXA.search(antes)
    if achado is not None:
        valor = int(achado.group(1) or achado.group(2), 16)
        if 0 < valor <= 0x10FFFF and not 0xD800 <= valor <= 0xDFFF:
            return len(achado.group(0)), chr(valor)
    if not antes:
        return None
    return 1, f"{ord(antes[-1]):04X}"


ESTADO_POR_EXTENSO: dict[str, str] = {"lida": "lida", "editada": "corrigida", "conferida": "conferida"}
"""Como o índice do caderno diz o estado de uma folha (S-613). `editada` é «corrigida» na tela:
é a palavra de quem corrige, e a do índice em disco fica sendo a do código."""

MARCA_DO_ESTADO: dict[str, str] = {"lida": "○", "editada": "●", "conferida": "√"}
"""A marca da frente de cada linha: círculo vazio, círculo cheio, visto. **O visto é `U+221A`**, e
não o `U+2713` dos *Dingbats*: medido em 2026-10-24 com `QRawFont.supportsCharacter`, o Segoe UI
não tem o `U+2713` nem o `U+2714` -- a lição da S-506 com o `U+2715` --, e tem os três daqui."""


def linha_do_indice(pagina: int, estado: str, correcoes: int, gravada_em: str) -> str:
    """Uma linha do índice das folhas (S-613): `"√ Folha 12 · conferida · 7 correções · 24/10 14:02"`."""
    partes = [f"{MARCA_DO_ESTADO.get(estado, '○')} Folha {pagina + 1}", ESTADO_POR_EXTENSO.get(estado, estado)]
    if correcoes:
        partes.append(f"{correcoes} correção" if correcoes == 1 else f"{correcoes} correções")
    if len(gravada_em) >= 16:  # ISO: `2026-10-24T14:02:11`
        partes.append(f"{gravada_em[8:10]}/{gravada_em[5:7]} {gravada_em[11:16]}")
    return " · ".join(partes)
