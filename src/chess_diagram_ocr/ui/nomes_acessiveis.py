"""Como um controle sem rótulo é anunciado por um leitor de tela (F9). **Sem toolkit.**

**O achado, medido pelo arnês `caissa.ui.audit.teclado`.** A janela tem 30 a 57 controles focáveis
por aba, e entre 4 e 15 deles chegam ao leitor de tela **sem nome nenhum**: doze `QLineEdit`, seis
réguas de zoom, cinco caixas de escolha, três editores de texto, duas tabelas. O Qt anuncia cada um
como o tipo dele -- "caixa de edição", "régua" --, sem dizer qual. Quem usa a janela sem ver não
descobre que a caixa de edição ao lado da palavra "Busca" é a busca; ele ouve "caixa de edição".

**A regra é uma cascata, e ela existe porque o nome quase sempre já está na tela.** O rótulo
"Busca" está desenhado à esquerda do campo; a dica do combo de condição explica o que ele faz. O
que falta não é texto -- é a **ligação** entre o texto e o controle, que o Qt só faz sozinha num
`QFormLayout`. Então a cascata procura o texto onde ele já está, nesta ordem:

1. o `accessibleName` que alguém já pôs -- ele ganha de tudo, e é a saída para o caso especial;
2. o texto do próprio widget (`text()`), que é o que o Qt já anunciaria;
3. a primeira linha da dica, que costuma ser a frase mais informativa da janela;
4. o rótulo vizinho no mesmo leiaute -- o `QLabel` imediatamente antes dele;
5. o nome declarado por classe, aqui embaixo, para o que não tem rótulo por natureza.

**Este módulo é os passos 4 e 5 sem Qt: ele decide, e `qt/acessibilidade.py` executa.** A decisão
é "que palavra descreve este controle", e ela é texto de interface como qualquer outro -- tem de
caber na mesma revisão de português, e tem de ser afirmável sem abrir janela.
"""

from __future__ import annotations

__all__ = [
    "CLASSES_COM_VALOR",
    "POR_CLASSE",
    "SUFIXO_DE_ROTULO",
    "limpar_rotulo",
    "nome_por_classe",
    "o_texto_e_valor",
]

CLASSES_COM_VALOR: frozenset[str] = frozenset(
    {"QSpinBox", "QDoubleSpinBox", "QAbstractSpinBox", "QLineEdit", "QSlider", "QProgressBar"}
)
"""Classes cujo `text()` é o **conteúdo** e não a identidade -- o passo 2 da cascata não vale.

**A medição está na crítica do ciclo 1, defeito nº 1.** O campo de página é um `QSpinBox`, e
`QSpinBox.text()` devolve `"121"`. Sem nome próprio, a cascata caía no passo 2 e o leitor de tela
anunciava **"121, campo de número"** nas seis abas -- e o nome mudava quando a pessoa virava a
página. Um nome que muda com o conteúdo não é nome: é o conteúdo lido duas vezes.

O mesmo vale para um `QLineEdit` com a FEN dentro (a aba Estudo anunciava
`"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"` como o **nome** do campo) e para a
régua, cujo `text()` não existe mas cuja família é a mesma.

Um `QPushButton` escrito "Salvar a posição" **não** está aqui, e a diferença é exatamente esta: o
texto de um botão é o que ele faz, e não muda quando o documento muda."""


def o_texto_e_valor(classes: tuple[str, ...]) -> bool:
    """Se, para esta hierarquia de classes, `text()` devolve conteúdo em vez de identidade. Pura.

    Recebe os **nomes** das classes, como `nome_por_classe`, e pela mesma razão: o módulo tem de
    ser afirmável sem importar Qt.
    """
    return any(classe in CLASSES_COM_VALOR for classe in classes)

POR_CLASSE: dict[str, str] = {
    "VisorDePagina": "Página do livro",
    "TabuleiroDeJogo": "Tabuleiro da partida",
    "TabuleiroEditavel": "Tabuleiro do diagrama",
    "Tabuleiro": "Tabuleiro",
    "TabelaQt": "Tabela de resultados",
    "QSlider": "Régua de zoom",
    "QTextBrowser": "Texto da página",
    "QTextEdit": "Editor de texto",
    "QPlainTextEdit": "Editor de texto",
    "QListWidget": "Lista",
    "QTreeWidget": "Tabela",
    "QTabWidget": "Abas",
    "QLineEdit": "Campo de texto",
    "QComboBox": "Escolha",
}
"""Classe do widget -> como ele se chama quando não há rótulo vizinho nem dica.

**É o último degrau da cascata, e por isso os nomes são genéricos de propósito.** Um nome
específico aqui seria uma mentira em metade dos usos -- há mais de uma régua na janela --, e o
leitor de tela já anuncia o **papel** junto: "Régua de zoom, régua" é redundante, "régua" sozinha
não diz o que ela move. O específico é trabalho do passo 4, que lê o rótulo que está na tela.

A ordem de consulta é a da hierarquia Python: `VisorDePagina` responde antes de `QWidget` porque
`qt/acessibilidade.py` sobe o `__mro__` e pára no primeiro nome conhecido."""

SUFIXO_DE_ROTULO = (":", "…", " ")
"""O que se tira do fim de um rótulo antes de ele virar nome acessível.

`"Busca:"` vira `"Busca"`. Os dois pontos são pontuação de leiaute -- eles dizem "o controle vem
a seguir" a quem **vê** --, e um leitor de tela que anuncia "Busca dois pontos, caixa de edição"
gasta uma sílaba para não dizer nada."""


def limpar_rotulo(texto: str) -> str:
    """O rótulo vizinho como nome acessível: sem pontuação de leiaute e sem acelerador.

    O `&` de acelerador some porque ele é notação do Qt e não texto: `"&Busca"` é lido como
    "e comercial busca" por um leitor de tela que receba a string crua.
    """
    limpo = texto.replace("&&", "\x00").replace("&", "").replace("\x00", "&").strip()
    while limpo and limpo.endswith(SUFIXO_DE_ROTULO):
        limpo = limpo[:-1].rstrip()
    return limpo


def nome_por_classe(classes: tuple[str, ...]) -> str:
    """O nome declarado da primeira classe conhecida da hierarquia. `""` se nenhuma o for.

    Recebe os **nomes** das classes e não as classes: é o que permite afirmar a tabela inteira
    sem importar Qt, que é a razão de este módulo morar em `ui/`.
    """
    for classe in classes:
        if classe in POR_CLASSE:
            return POR_CLASSE[classe]
    return ""
