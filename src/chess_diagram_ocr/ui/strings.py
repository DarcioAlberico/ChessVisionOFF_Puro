"""Vocabulário compartilhado da interface (S-04).

**O que entra aqui, e o que não.** Não é um catálogo de todas as strings: um dicionário com
duzentas constantes usadas uma vez cada troca um literal legível por uma indireção, e piora
o código de layout sem nada em troca. Entra o que **duas telas precisam dizer igual** ou o
que tem significado além do texto.

**Por que isso importa, medido.** Os rótulos de procedência do lado a jogar existiam em dois
lugares -- `ui/result_panel.py` e o Streamlit (hoje `examples/streamlit_demo.py`) -- e já
tinham divergido: o Tkinter
dizia "deduzido da posicao" e o Streamlit "deduzido da legalidade da posicao"; "assumido"
contra "assumido (o PDF nao diz)". É o mesmo mecanismo da S-31 aplicado a texto -- duas
implementações do mesmo conceito, e a segunda seguindo por conta própria.

**A acentuação é a outra metade.** A Fase 0 deixou as strings sem acento ("posicao",
"Configuracao") porque centralizá-las dependia da decomposição do Tkinter, que só veio na
6.2. `WORDS_REQUIRING_ACCENTS` é a lista que o teste usa para impedir que voltem.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

SIDE_SOURCE_LABELS: dict[str, str] = {
    "text": "declarado no texto do PDF",
    "ocr": "lido por OCR da legenda",
    "text-page-scope": "declarado no cabeçalho da página",
    "ocr-page-scope": "lido por OCR do cabeçalho da página",
    "legality": "deduzido da legalidade da posição",
    "default": "assumido (o PDF não diz)",
    "manual": "definido por você",
    "queue": "vindo da fila de revisão",
}
"""De onde saiu o lado a jogar (S-16/S-17/S-19).

Aparece ao lado do rádio "Brancas/Pretas" nas duas telas e no header
`[SideToMoveSource]` do PGN. "Pretas jogam" lido de uma legenda e "pretas jogam" assumido
pelo padrão têm o mesmo texto e valores completamente diferentes para quem vai conferir --
é essa diferença que o rótulo carrega, e por isso ele não pode variar entre as telas."""

SIDE_SOURCE_CONFLICT = "texto e posição discordam — confira"
"""A discordância da S-17 tem rótulo próprio porque não é uma procedência: é o aviso de que
duas fontes se contradizem e uma delas está errada."""

DETECTION_SOURCE_LABELS: dict[str, str] = {
    "embedded": "imagem embutida no PDF",
    "contour": "contorno detectado na página",
    "hybrid": "imagem embutida, alinhada pelo contorno",
}
"""Como o diagrama foi localizado (S-12). Vale para auditar o dataset por fonte."""

ORIENTATION_LABELS: dict[str, str] = {
    "auto": "Automática",
    "0": "0 graus",
    "180": "180 graus",
}
"""Tri-estado da S-13, no lugar do checkbox que valia para a página inteira."""


def side_source_label(source: str, *, conflicting: bool = False) -> str:
    """Rótulo de procedência do lado a jogar, ou `""` quando não há o que dizer."""
    if conflicting:
        return SIDE_SOURCE_CONFLICT
    return SIDE_SOURCE_LABELS.get(source, "")


SIDE_LABELS: dict[str, str] = {"w": "Brancas", "b": "Pretas"}
"""Como a interface chama os dois lados. Um nome por conceito (S-04, S-169).

Existia escrito à mão no rádio do Resultado e no cabeçalho da lista de partidas, e a coluna
"Lado" do Dataset publicava a letra crua do CSV -- três grafias do mesmo par."""

# ------------------------------------------------------- um conceito, um nome (S-166)

VARRER_LIVRO = "Varrer o livro"
"""O mesmo gesto tinha dois nomes: "Varrer PDF" na Revisão e "Varrer livro" na Galeria.

As duas percorrem o livro inteiro com o mesmo modelo; o que muda é o que cada uma **grava** --
uma monta a fila de revisão, a outra o índice da galeria. A diferença fica no rótulo da aba e no
tooltip, não no verbo: dois verbos para o mesmo gesto fazem a pessoa procurar a terceira varredura
que não existe."""

LADO_A_JOGAR = "Lado a jogar"
"""Chamado assim no Resultado e de "Vez" na Galeria, para o mesmo campo com os mesmos dois valores.

"Lado a jogar" ganha porque é o nome do conceito no PGN (`SideToMove`) e porque "Vez" sozinho, num
rodapé, não diz vez de quê."""

MAPA_DE_INCERTEZA = "Mapa de incerteza"
"""Era "Heatmap de incerteza" -- metade em inglês, e a metade que nomeia a coisa."""

ZOOM_DO_TABULEIRO = "Zoom do tabuleiro"
"""Era "Zoom board". "Zoom" fica: entrou no português e não tem substituto de uma palavra."""

ZOOM_DA_PAGINA = "Zoom PDF"
"""O rótulo do zoom do visualizador. Estava cravado em `ui/pdf_panel.py`, e a S-225 lhe deu um
segundo cliente -- o deslizador da pele "Foco". Dois rótulos escritos à mão para o mesmo controle
é como eles divergem, que é o defeito que a S-324 mediu nos comandos."""

VIRAR_TABULEIRO = "Virar o tabuleiro"
"""Era "Virar board" -- verbo em português e substantivo em inglês na mesma frase de duas palavras."""

CORRIGIR_PELA_REDE = "Corrigir pela rede"
"""Era "Corrigir Net". "Net" não é o nome de nada: o botão manda o recorte a um serviço externo
(S-32), e o que a pessoa precisa saber antes de clicar é justamente que **a imagem sai da máquina**."""

CONJUNTO = "Conjunto"
"""Era "Split", a coluna que diz se a amostra é de treino, validação ou teste."""

TAMANHO_DO_LOTE = "Tamanho do lote"
TAXA_DE_APRENDIZADO = "Taxa de aprendizado"
"""Eram "Batch size" e "Learning rate". São termos de quem treina modelo, e quem treina neste
programa é quem corrige diagramas -- a aba de configuração não é documentação de framework."""

CABECALHOS_DO_PGN = "Cabeçalhos do PGN"
"""Era "Headers do PGN". "PGN" fica (é o nome do formato); "headers" tem tradução de uso corrente."""

LIVRO_EM_PDF = "Livro em PDF"
"""Era `PDF (direita)`: um grupo cujo nome descrevia a **posição dele na tela**. Além de não
nomear nada, ele mente assim que alguém arrasta o divisor."""

STATUS_DA_FILA: dict[str, str] = {"pending": "pendente", "done": "revisado", "skipped": "pulado"}
"""O estado de um item da fila de revisão, como a tela o escreve (S-166).

`pending` aparecia **em 129 linhas** da coluna Status enquanto o filtro ao lado dizia "Só
pendentes". A chave continua sendo o valor gravado no arquivo -- o que muda é o que se lê."""

PRIMEIRO = "⏮"
ANTERIOR = "◀"
PROXIMO = "▶"
ULTIMO = "⏭"
CONJUNTO_DE_PECAS = "Conjunto de peças"
"""O rótulo da escolha da S-230, na Configuração.

Ao lado dos outros rótulos de campo e não no menu de aparência: conjunto é eixo próprio, e a
pergunta que ele responde -- com que desenho as peças aparecem -- não é a pergunta da pele."""

PASTA_DE_PECAS = "Pasta de peças"
"""O caminho dos 12 PNGs do usuário. Só vale com o conjunto "Pasta do usuário" escolhido."""

ALINHAR = "Alinhar"
CAIXA = "Caixa"
"""Os dois agrupadores da barra da aba de texto (S-259/S-262). **Não são comandos.**

A regra 4 da SPEC_EDITOR manda todo comando do editor para `ui/comandos.py`, e estes dois não são
comandos: são o rótulo do botão que **abre a lista** de quatro alinhamentos e de três caixas. Quem
faz alguma coisa é o item da lista, e cada um deles é um comando do catálogo, com item de menu
próprio.

A diferença tem consequência medida: um comando no catálogo precisa de casa numa das três peles ou
de item de menu (`ui/alcance.py`), e um agrupador que fosse comando obrigaria o menu a ter uma linha
"Alinhamento…" ao lado dos quatro itens que ela abriria -- a redundância que o menu existe para não
ter. É a mesma decisão que `LADO_A_JOGAR` e `CONJUNTO` já são: rótulo de grupo, e não de ação."""

SETA = "→"
"""Os glifos de navegação, no lugar de `|<`, `<<`, `>>`, `>|` e `->` (S-166).

ASCII imitando símbolo é de terminal, não de janela: `>|` não é uma seta, é duas letras que
lembram uma. Os cinco existem em Unicode, estão na Segoe UI e em qualquer fonte de sistema desde
o Windows 7."""


LIMITE_DE_NOMES_NA_CONFIRMACAO = 5
"""Quantos nomes de arquivo a pergunta de remoção lista antes de resumir o resto.

Cinco cabem numa caixa sem rolagem e são o bastante para reconhecer o que foi selecionado. Acima
disso a lista deixa de ser conferência e vira parede de texto -- e uma pergunta que ninguém lê é
uma pergunta que não protege nada."""


def frase_de_remocao(nomes: Sequence[str], *, arquivo: str = "labels.csv") -> str:
    """A pergunta antes de apagar: **o quê**, quantos e de onde (S-170).

    A caixa dizia "Remover 3 amostra(s) do labels.csv?". Ela contava e não nomeava, e o que está
    prestes a ser apagado é rótulo corrigido à mão -- a S-76 é o registro do que custa um gesto
    destrutivo mal confirmado neste projeto (1.405 diagramas sobrescritos por um clique).

    Uma amostra é dita pelo nome; muitas são ditas pela contagem **e** pelos nomes, porque a
    seleção de um `Treeview` é fácil de estender sem querer -- um `Shift+clique` a mais pega dez
    linhas, e a única defesa é ver quais.
    """
    lista = [str(nome).strip() for nome in nomes if str(nome).strip()]
    if not lista:
        return f"Nenhuma amostra selecionada para remover do {arquivo}."
    if len(lista) == 1:
        return f"Remover a amostra {lista[0]} do {arquivo}?"
    mostrados = lista[:LIMITE_DE_NOMES_NA_CONFIRMACAO]
    resto = len(lista) - len(mostrados)
    cauda = f" e mais {resto}" if resto else ""
    return f"Remover {len(lista)} amostras do {arquivo}?\n\n" + ", ".join(mostrados) + cauda + "."


def status_da_fila(codigo: str) -> str:
    """O estado de um item da fila, em pt-BR. Devolve o valor cru se for um que não conhecemos.

    O cru e não um travessão: um estado novo no arquivo é informação, e escondê-lo faria a tela
    mentir sobre o que está gravado (mesma regra de `detection_source_label`).
    """
    return STATUS_DA_FILA.get(codigo, codigo)


PRODUTO = "ChessVisionOFF"
"""O nome do produto. Um lugar só, porque ele aparece no título, no ícone e no bundle."""

DISTRIBUICAO = "chessvisionoff-puro"
"""O nome da distribuição no `pyproject.toml`. É por ele que a versão é lida."""


def _versao_instalada() -> str:
    """A versão do pacote instalado, ou `""` quando não há instalação a consultar.

    Lida e não cravada (S-161): duas verdades sobre a mesma versão divergem na primeira publicação
    que esquecer uma delas, e a que fica errada é sempre a da tela, porque ninguém a testa.

    Vazio num ambiente sem a distribuição -- um checkout sem `uv sync`, ou um bundle congelado que
    não carregue os metadados. A caixa "Sobre" mostra o nome do produto sem número, que é honesto:
    melhor não dizer a versão do que dizer uma errada.
    """
    try:
        return version(DISTRIBUICAO)
    except PackageNotFoundError:
        return ""


VERSAO = _versao_instalada()

LIMITE_DO_LIVRO_NO_TITULO = 42
"""Quantos caracteres do nome do livro cabem no título antes de ele ser encurtado.

A barra de tarefas do Windows mostra ~30 e o Alt-Tab ~60; 42 é o meio, e o que importa é que o
encurtamento aconteça **no meio** e não no fim -- ver `titulo_da_janela`."""


FRACAO_DA_CABECA = 3
"""Que fração do limite fica com o **começo** do nome: um terço, e o resto com o fim.

Não é simetria, e o teste é quem mostrou por quê. Com metade para cada lado,
`Yusupov A - Boost your Chess 1 - The Fundamentals.pdf` e o volume **2** produziam títulos
idênticos: o número caía exatamente no pedaço elidido. O começo só precisa identificar o autor,
o que três ou quatro palavras fazem; é o fim que carrega o volume e o subtítulo, que é o que
distingue um livro do vizinho na estante."""


def _encurtar(nome: str, limite: int = LIMITE_DO_LIVRO_NO_TITULO) -> str:
    """Encurta pelo **meio**, preservando o começo e -- sobretudo -- o fim do nome.

    Cortar no fim é o que quase todo programa faz e é o pior corte possível para um acervo de
    xadrez: "Yusupov A — Boost your Chess 1", "…2" e "…3" viram três títulos idênticos.
    """
    if len(nome) <= limite:
        return nome
    cabeca = (limite - 1) // FRACAO_DA_CABECA
    return f"{nome[:cabeca]}…{nome[len(nome) - (limite - 1 - cabeca) :]}"


def titulo_da_janela(livro: str = "", pagina: int | None = None, total: int | None = None) -> str:
    """O título da janela: o que mudou primeiro, o produto no fim (S-167).

    Era `"Chess Diagram OCR - Tkinter"` -- que nomeia o **toolkit**, a única informação da frase
    que não interessa a quem usa o programa, e não diz o que está aberto. Ao voltar de outra
    janela pelo Alt-Tab, o título é a única coisa que se lê.

    A ordem não é estética: a barra de tarefas e o Alt-Tab cortam pela **direita**, então o que
    varia tem de vir antes. Sem livro aberto sobra o produto sozinho, que é a resposta honesta
    para "o que é esta janela".

    A página é dita em base 1, como o campo da tela -- e uma página fora da faixa do livro é
    omitida em vez de mostrada: um título que diz "p. 0 de 402" está errado sobre a única coisa
    que ele foi acrescentado para dizer.
    """
    nome = str(livro).strip()
    if not nome:
        return PRODUTO
    partes = [_encurtar(nome)]
    if pagina is not None and pagina >= 0 and (total is None or pagina < total):
        partes.append(f"p. {pagina + 1} de {total}" if total else f"p. {pagina + 1}")
    return f"{' · '.join(partes)} — {PRODUTO}"


def sobre_o_produto(tema: str = "", *, versao: str = VERSAO) -> str:
    """O texto da caixa "Sobre" do menu Ajuda (S-161).

    Diz as três coisas que alguém abre "Sobre" para saber: o que é o programa, que versão está
    rodando e **em que ambiente** -- o tema em uso responde se o `ttkbootstrap` subiu ou se a
    janela caiu no `ttk` puro, que é a pergunta do contrato de degradação da S-53 e hoje só se
    responde lendo o log.
    """
    linhas = [
        f"{PRODUTO} {versao}",
        "",
        "Lê diagramas de xadrez de PDF e exporta as posições em FEN e PGN.",
    ]
    if tema:
        linhas.extend(["", f"Tema em uso: {tema}"])
    return "\n".join(linhas)


def detection_source_label(source: str) -> str:
    """Rótulo da fonte de detecção. Devolve o valor cru se for um que não conhecemos."""
    return DETECTION_SOURCE_LABELS.get(source, source)


WORDS_REQUIRING_ACCENTS: tuple[str, ...] = (
    "analise",
    "apos",
    "area",
    "automatica",
    "cabeca",
    "codigo",
    "conclusao",
    "conclusoes",
    "confianca",
    "configuracao",
    "configuracoes",
    "continuacao",
    "continuacoes",
    "correcao",
    "correcoes",
    "decisao",
    "decisoes",
    "deteccao",
    "disponivel",
    "epoca",
    "execucao",
    "execucoes",
    "exportacao",
    "exportacoes",
    "indisponivel",
    "informacao",
    "informacoes",
    "invalida",
    "invalido",
    "maximo",
    "media",
    "memoria",
    "metricas",
    "minimo",
    "nao",
    "numero",
    "opcao",
    "opcoes",
    "orientacao",
    "orientacoes",
    "padrao",
    "padroes",
    "pagina",
    "peca",
    "plausivel",
    "plausiveis",
    "posicao",
    "posicoes",
    "possivel",
    "promocao",
    "proximo",
    "revisao",
    "revisoes",
    "sao",
    "selecao",
    "selecoes",
    "tambem",
    "ultimo",
    "usuario",
    "versao",
    "voce",
)
"""Palavras que, sem acento, estão erradas em pt-BR.

Serve ao teste que impede a regressão da pendência 0.7. É uma lista de raízes: o teste
compara ignorando plural e gênero, para que "posicoes" e "invalidos" também sejam pegos."""
