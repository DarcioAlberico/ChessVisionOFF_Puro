"""O rótulo de uma aba, e quanto trabalho ela carrega (S-162).

**O problema.** Seis abas dizendo só o nome. Quanto há para fazer em cada uma -- 129 pendentes na
Revisão, 3.936 linhas no Dataset, 1.480 diagramas na Galeria -- é informação que só aparecia
**depois** de clicar, e é justamente ela que decide qual aba abrir.

**Por que o rótulo é função pura.** Porque a decisão está nos casos de borda, e são três: sem
contagem conhecida (a aba nunca foi carregada), contagem zero (que **não** vira "(0)": uma fila
vazia é um estado bom, e anunciá-lo com um zero entre parênteses é ruído permanente) e o milhar em
pt-BR, que é ponto e não vírgula.

**E o rótulo mudou de dono.** O `AppState` guarda a aba aberta pelo **rótulo** desde a S-156, e um
rótulo que agora carrega número deixaria de casar assim que a contagem mudasse -- a sessão seguinte
cairia na primeira aba, em silêncio. `nome_base` é o que separa as duas coisas: o nome é a
identidade, a contagem é o estado.
"""

from __future__ import annotations

from . import formato

__all__ = [
    "ABAS",
    "ABA_DE_TRABALHO",
    "DO_ACERVO",
    "DO_DIAGRAMA",
    "RENOMEADAS",
    "contagem_no_rotulo",
    "nome_atual",
    "nome_base",
    "rotulo",
]

RESULTADO = "Resultado"
ESTUDO = "Estudo"
"""Era `ANALISE = "Análise"` até a S-272.

**O nome descrevia o que a aba fazia quando ela só tinha o motor**: analisar uma posição. Desde a
Fase 43 ela guarda estudos -- um por diagrama do livro, com árvore de variantes, anotação e um PGN
que sobrevive ao fechamento --, e "Análise" passou a nomear a menor parte do que ela é.

**"Estudo" e não "Sala de estudo" nem "Tabuleiro de estudo".** As outras seis são substantivos de
uma palavra, e a faixa de abas é onde a S-150 mediu o aperto de largura. A *sala* é o conceito, e
ela está por extenso em `ui/sala_declarada.py` e no ROADMAP_ESTUDO."""

REVISAO = "Revisão"
TEXTO = "Texto"
DATASET = "Dataset"
GALERIA = "Galeria"
CONFIGURACAO = "Configuração"

DO_DIAGRAMA: tuple[str, ...] = (RESULTADO, ESTUDO, REVISAO, TEXTO)
"""As abas que mudam de conteúdo quando se clica num retângulo da página."""

DO_ACERVO: tuple[str, ...] = (DATASET, GALERIA, CONFIGURACAO)
"""As que falam do livro inteiro. A Configuração fecha a fila: é a aba do primeiro dia."""

ABAS: tuple[str, ...] = DO_DIAGRAMA + DO_ACERVO
"""As abas do painel esquerdo, **na ordem** -- e a ordem é o item (S-162).

Elas misturavam dois níveis, e **o corte entre os dois grupos é onde a barra muda de assunto**.
Seis abas de peso igual escondiam que quatro delas seguem o diagrama aberto e três não.

**São sete, e não seis.** A S-162 arrumou seis; a S-211 acrescentou a `Texto`, do lado do diagrama
aberto -- ela responde "o que está escrito nesta folha?", que é a mesma pergunta de contexto que o
`Resultado` e a `Revisão` respondem. A spec da S-226 ainda dizia seis, e é este número que vale.

**Declarada aqui porque uma pele não pode esconder aba nenhuma** (regra 2 da SPEC_APARENCIA). A
Imagem 1 não desenha faixa de abas; o que a S-226 muda é o **peso** dela, não o conteúdo -- e o
teste compara a barra montada com esta tupla, em cada pele registrada."""

ABA_DE_TRABALHO = RESULTADO
"""Onde a janela abre num checkout novo (S-162).

Era a Configuração: três caminhos de arquivo e os parâmetros de treino, isto é, a aba do primeiro
dia e quase nunca depois. O trabalho começa no Resultado, que é onde o diagrama clicado na página
aparece."""


def rotulo(nome: str, contagem: int | None = None) -> str:
    """`Revisão (129)`, ou só `Revisão` quando não há número que importe.

    `None` é "ainda não sei" -- a aba que nunca carregou --, e `0` é "não há nada aqui". Os dois
    ficam sem parênteses, e a razão é a mesma: o parêntese existe para dizer *quanto falta*.
    """
    limpo = str(nome).strip()
    if not contagem:
        return limpo
    return f"{limpo} ({formato.inteiro(contagem)})"


def nome_base(texto: str) -> str:
    """O nome da aba sem a contagem: `Revisão (129)` → `Revisão`.

    É o que o `AppState` guarda e o que `rolagem.selecionar_aba` compara. Sem isto, lembrar a aba
    aberta entre execuções (S-156) pararia de funcionar no dia em que a fila mudasse de tamanho --
    e falharia em silêncio, caindo na primeira aba.
    """
    limpo = str(texto).strip()
    if limpo.endswith(")") and " (" in limpo:
        return limpo.rsplit(" (", 1)[0].strip()
    return limpo


RENOMEADAS: dict[str, str] = {"Análise": ESTUDO}
"""Abas que já se chamaram outra coisa: nome guardado -> nome de hoje (S-272).

**É a única memória disso no programa, e ela é para sempre.** O `AppState` guarda a aba aberta pelo
**rótulo** desde a S-156, e `rolagem.selecionar_aba` compara nome com nome. Renomear uma aba sem
esta tabela faz o guardado não casar com nada: `selecionar_aba` devolve `False`, a janela abre na
primeira aba e ninguém fica sabendo -- que é exatamente o defeito silencioso contra o qual o
cabeçalho deste módulo já avisava a propósito da contagem no rótulo.

Uma linha por rename, e ela custa menos que o dia em que alguém for descobrir por que a aba deixou
de ser lembrada."""


def nome_atual(guardado: str) -> str:
    """O nome de hoje da aba que uma sessão anterior guardou.

    Nome que nunca foi renomeado passa igual, inclusive o que não existe mais -- e aí a resposta
    continua sendo a de antes: a janela fica onde já estava.
    """
    base = nome_base(guardado)
    return RENOMEADAS.get(base, base)


def contagem_no_rotulo(texto: str) -> int | None:
    """A contagem que o rótulo mostra, ou `None`. Existe para o teste ler o que a tela diz."""
    limpo = str(texto).strip()
    if not (limpo.endswith(")") and " (" in limpo):
        return None
    numero = limpo.rsplit(" (", 1)[1][:-1].replace(".", "")
    return int(numero) if numero.isdigit() else None
