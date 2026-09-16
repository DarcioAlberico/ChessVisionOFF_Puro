"""A folha de estilo do cromo, e a paleta que ela não alcança -- **sem importar Qt** (F9).

**Por que ela mudou de `qt/` para cá, e é a fronteira do projeto e não arrumação.** O tronco tem
duas pastas: `ui/`, que decide, e `qt/`, que desenha. A folha de estilo é a decisão de cor e de
espaço da janela inteira -- qual cinza é painel, qual é botão, qual azul é foco, quanto respira
cada controle -- e ela morava em `qt/tema.py` só porque o consumidor dela é `QApplication`.
O preço disso era exato e mensurável: o venv da suíte **não tem binding de Qt nenhum**, então o
portão do SPEC §11.3 ("contraste WCAG AA em 100 % dos pares") não podia ser afirmado por teste
lá -- o `import` morria antes da primeira asserção. Uma decisão que só se verifica onde o
toolkit está instalado é uma decisão que a ADR-0009 não consegue mais mover.

Aqui ela é texto: `folha_de_estilo(...)` devolve uma string, `PAPEIS_DA_PALETA` é um dicionário
de nomes. Quem traduz nome de papel em `QPalette.ColorRole` é `qt/tema.py`, em cinco linhas, e
essa tradução é a única coisa que precisa de Qt.

**A folha e a paleta são duas camadas, e a segunda não é redundância.** O QSS decide o que ele
alcança; `QPalette` é a resposta do que é desenhado **por baixo** dele -- e o caso que obrigou a
descoberta foi fotografado: um item de `QListWidget` é pintado por um *delegate*, que lê
`QPalette.Highlight` e não vê `::item:selected`. A prancha de controles saiu com a linha da
lista no azul de fábrica do Windows e a linha da tabela no `SELECAO` da paleta -- **duas cores
de "selecionado" na mesma imagem**. As duas camadas leem `tokens.cor`, então não há um segundo
lugar onde a cor é escolhida; há um segundo lugar onde ela é **entregue**.
"""

from __future__ import annotations

from collections.abc import Callable

from chess_diagram_ocr.ui import espaco, estilos, folha, icones, pele, tipografia, tokens


def tinta_do_papel(papel: str) -> str:
    """O **token de letra** que um botão daquele papel usa. É o que o ícone dele também usa (F9).

    **O defeito que isto fecha foi fotografado.** `qt/fila.py` e `qt/fita.py` desenhavam todo
    ícone em `TEXTO_PADRAO` -- claro no cromo escuro -- e punham o desenho dentro de um botão
    cujo rótulo é `TEXTO_SOBRE_ENFASE`, que na paleta escura é quase preto. O resultado está em
    `depois_escuro_1280x800_estudo.png`: o disquete de "Salvar a posição" sai **branco sobre o
    azul claro do primário**, ao lado de um rótulo preto. Ícone e rótulo, na mesma linha do mesmo
    botão, em cores opostas -- e o ícone a 1,7:1 da face em que ele está.

    **A decisão é daqui, e a razão é a fronteira do projeto.** "Que cor tem o ícone de um botão
    primário" é uma escolha de aparência, não um desenho: `qt/` só precisa saber a que perguntar.
    Enquanto ela morou no ponto de chamada, ela morou em **dois** pontos de chamada -- e foi por
    isso que os dois erraram igual.

    Papel desconhecido cai no neutro em vez de levantar: um catálogo com papel novo desenha o
    ícone na cor do texto, que é a resposta conservadora, e quem levanta por papel escrito errado
    é `estilos.estilo_de_botao`, no lugar em que a lista mora.
    """
    return tokens.TEXTO_SOBRE_ENFASE if estilos.tem_enfase(papel) else tokens.TEXTO_PADRAO


def letra_do_pressionado(face_pressionada: str, letra_em_repouso: str) -> str:
    """A cor do rótulo sobre a face **já escurecida** do botão pressionado. Pura (F9-C2).

    **Escurecer a face sem reescolher a letra troca um defeito por outro.** Medido: na pele escura
    o destrutivo pressionado fica `#bb544c`, e a letra de repouso (`#141013`, quase preta) cai a
    **4,03:1** sobre ele -- abaixo do piso AA, no botão que apaga coisas, no instante do clique. O
    branco sobre a mesma face dá 4,68:1.

    Então a escolha é entre dois valores que a janela já usa, e é a face de baixo que decide: a
    letra de repouso daquele papel, ou o branco puro. Nenhuma cor nova, e nenhuma das quatro
    combinações (dois papéis x duas peles) fica abaixo de 4,5:1 -- é o que
    `test_o_pressionado_escurece_nas_duas_peles` cobra.
    """
    candidatas = (letra_em_repouso, tokens.BRANCO)
    return max(candidatas, key=lambda letra: tokens.razao_de_contraste(letra, face_pressionada))


__all__ = [
    "A_FOLHA",
    "ESCURECIMENTO_DO_PRESSIONADO",
    "O_WIDGET",
    "PAPEIS_DA_PALETA",
    "PAPEL_PINTADO",
    "PAPEIS_DA_PALETA_MORTA",
    "PROPRIEDADE_DE_APOIO",
    "QUEM_PINTA",
    "PROPRIEDADE_DE_PAPEL",
    "RAIO_NA_BASE",
    "RECHEIO_DA_FOLHA",
    "RECHEIO_DO_TEMA",
    "folha_de_estilo",
    "letra_do_pressionado",
    "tinta_do_papel",
]

RAIO_NA_BASE = 4
"""O raio de canto de botão, campo, escolha e aba, em pixel na base de referência (F9-C2).

**Era `espaco.minima()` -- 2 px --, e 2 px é indistinguível de canto reto.** O crítico do ciclo 1
amostrou o canto superior esquerdo de um botão em `amostrario_claro.png` e achou **um único
pixel** de mistura entre a borda e o fundo: *"botão retangular de canto vivo com filete de 1 px é
a assinatura do Fusion do Qt, e é o que faz a janela ler como demo"*.

Quatro pixels dão três pixels de mistura no mesmo canto -- a curva passa a existir para o olho sem
o botão virar pastilha. O número não é `espaco.minima() * 2` por acaso de aritmética: raio de canto
**não é folga**, e derivá-lo de `FOLGA_MINIMA` amarrava a forma do controle ao vão entre dois
controles, que são decisões independentes. Ele escala com a fonte como todo o resto (`_escalado`),
com piso 3 -- abaixo disso a curva volta a ser o pixel único que ela veio corrigir."""

ESCURECIMENTO_DO_PRESSIONADO = 0.20
"""Quanto a face de um botão com ênfase escurece ao ser pressionada. Ver `letra_do_pressionado`.

**A direção estava invertida na pele escura, e o crítico do ciclo 1 mediu**: `PRIMARIO`
`#6ea8fe -> #98c1fe` e `DESTRUTIVO` `#e4665d -> #ec928c`. Pressionar **clareava**, o que se lê
como recuar -- o oposto da affordance, e o contrário do que Affinity, Resolve e Chessbase fazem
nas duas peles.

A causa era `afastar`, que anda para longe da **letra**: na pele escura a letra é quase preta
(`#141013`), então afastar-se dela é clarear. `afastar` continua certo para o `:hover` -- ele foi
escolhido para o contraste do rótulo, e o número que ele salvou está no §3.3 do relatório do ciclo
1 --, e é **só** o `:pressed` que inverte de regra: pressionado escurece, sempre.

O peso é 0,20 e ele foi **buscado, não escolhido**: é o menor valor múltiplo de 0,02 acima de 0,18
em que a diferença de luminância é visível nas duas peles (ΔL 0,043 na clara e 0,150 na escura) e
em que o par letra/face continua acima de 4,5:1 nas quatro combinações -- com a letra escolhida
pela face escurecida, que é o que `letra_do_pressionado` faz."""

PROPRIEDADE_DE_APOIO = "apoio"
"""A propriedade dinâmica que marca um rótulo como **texto de apoio** (`AUXILIAR`) (F9-C2).

Contagem, unidade, procedência, dica de estado vazio: texto que acompanha um dado sem ser o dado.
Ela existe pela mesma razão de `PROPRIEDADE_DE_PAPEL` -- o seletor `QLabel[apoio="true"]` é o
mecanismo do Qt para o que `style="..."` faz no `ttk` --, e o valor é a string `"true"` porque é
como o Qt escreve booleano de propriedade dinâmica em folha de estilo."""

# ------------------------------------------------------------------------- o papel do botão

PROPRIEDADE_DE_PAPEL = "papel"
"""A propriedade dinâmica que carrega o papel de `ui/estilos.py` até a folha de estilo.

**É o equivalente Qt do nome de estilo `ttk`, e a tradução é obrigatória.** Lá o papel vira
nome de estilo do `ttkbootstrap`; aqui vira propriedade que o seletor
`QPushButton[papel="PRIMARIO"]` lê. O que
**não** muda é quem decide o papel: `ui/estilos.py` continua sendo a única fonte, e
`estilos.conferir_barra` -- que é pura -- continua cobrando uma ênfase por barra nos dois
frontends.

O valor é o próprio nome do papel (`"PRIMARIO"`, `"DESTRUTIVO"`) e não um segundo vocabulário:
uma segunda tabela de nomes seria a divergência que `estilos.estilo_de_botao` existe para não
deixar acontecer.
"""


# ------------------------------------------------------------------------ a folha de estilo

RECHEIO_DO_TEMA: dict[str, tuple[int, int]] = {
    "QPushButton": (10, 4),
    "QToolButton": (10, 4),
    "QLineEdit": (5, 5),
    "QComboBox": (5, 4),
}
"""`seletor -> (horizontal, vertical)` em pixel na base 9, do que o **`ttkbootstrap` dava e o Qt
não dá**.

Os números não são novos: são a medição que está escrita em `ui/folha.py`, feita sob
`bootstrap-light` e `bootstrap-dark`, e o docstring de lá explica por que a folha do Tk **não**
os escreve -- naquele frontend o tema já os deu, e sobrescrevê-los foi medido e piorou (o botão
de fita encolheu de 58 para 50 px).

Aqui a conta inverte. Não há `ttkbootstrap`, então ninguém deu: um `QPushButton` sem folha sai
com o recheio de fábrica do estilo da plataforma, que no `Fusion` é outro número e no `offscreen`
da CI é outro ainda. **Herdar os quatro valores medidos é o que faz os dois frontends
desenharem o mesmo botão** -- e é por isso que eles ficam aqui em vez de virar um quinto papel
em `ui/tipografia.py`: eles não são uma escala nova, são o que o outro tema já entregava.

`_escalado` os faz acompanhar a fonte do sistema e a densidade, que é o que `ui/folha.py`
ganhou ao derivar tudo de `tipografia.FOLGAS` -- um pixel cravado aqui ignoraria quem aumentou a
fonte do Windows, que é o defeito de DPI da S-148 num lugar menor.
"""

RECHEIO_DA_FOLHA: dict[str, str] = {
    "QTabBar::tab": "TNotebook.Tab",
    "QCheckBox": "TCheckbutton",
    "QRadioButton": "TRadiobutton",
    "QSpinBox": "TSpinbox",
    "QDoubleSpinBox": "TSpinbox",
    "QGroupBox": "TLabelframe",
}
"""`seletor Qt -> classe de `ui/folha.py``, para o recheio sair da mesma tabela nos dois frontends.

**Nenhum número aqui, e é o item.** A folga da aba, a da caixa de seleção e a do grupo são
decisões que já passaram por revisão na S-441 -- e `folha.recheio` é pura, então este módulo
pergunta a ela em vez de repetir a resposta. Um dia em que a folga da aba mude, ela muda para as
duas janelas.

`QDoubleSpinBox` mapeia para a mesma classe do `QSpinBox` porque no Tk os dois são `TSpinbox`:
dois campos de número lado a lado com recheio diferente é a inconsistência que aquela folha
existe para não deixar acontecer.
"""


def _escalado(pixel: int, *, base: int, densidade: str) -> int:
    """Um pixel medido na base de referência, reescrito para esta fonte e esta densidade.

    É a conta de `tipografia.folga` sem a tabela de papéis: os quatro valores de
    `RECHEIO_DO_TEMA` não são papéis da escala, são o que o outro tema entregava. O piso de 1 é
    o mesmo e vale pela mesma razão -- dois vizinhos colados viram um controle só para o olho.
    """
    proporcional = pixel * base / tipografia.BASE_DE_REFERENCIA
    return max(1, round(proporcional * tipografia.FATOR_DE_FOLGA[densidade]))


def folha_de_estilo(
    *,
    cromo_escuro: bool = False,
    base: int = tipografia.BASE_DE_REFERENCIA,
    densidade: str = pele.CONFORTAVEL,
    marcas: dict[str, str] | None = None,
    altura_do_titulo: int | None = None,
) -> str:
    """A folha de estilo inteira, como texto. **Pura: não toca `QApplication` nem widget.**

    É o que permite afirmar a paleta e o espaço das três peles e das duas densidades numa
    máquina sem tela -- a mesma razão de `ui/tokens.py` não importar `tkinter`, e o que faz o
    teste desta folha rodar na CI sem servidor gráfico.

    `marcas` são os caminhos dos dois desenhos do indicador de seleção -- `icones.MARCA_VISTO` e
    `icones.MARCA_TRACO` --, gerados por quem tem toolkit (`qt/tema.py`) e passados como texto.
    Ausentes, o indicador volta ao preenchimento sólido: a folha nunca depende de arquivo para
    desenhar, e um caminho que sumiu deixa a caixa marcada legível pela cor, que é o estado do
    ciclo 1. Ver `_indicador`.

    `altura_do_titulo` é a altura **em pixel** da fonte com que o Qt vai pintar
    `QGroupBox::title`, medida por quem tem toolkit (`qt/tema.altura_do_titulo_atual`). Ausente,
    a folha a estima com `tipografia.altura_do_texto` -- ver a faixa do título, abaixo. É a mesma
    fronteira de `marcas`: o número que só existe com tela entra como dado, e a função continua
    pura e afirmável no venv sem binding de Qt.

    Levanta `KeyError` para densidade desconhecida, por `tipografia.folga`.
    """

    def cor(papel: str) -> str:
        return tokens.cor(papel, None, cromo_escuro=cromo_escuro)

    def do_tema(seletor: str) -> str:
        h, v = RECHEIO_DO_TEMA[seletor]
        return f"{_escalado(v, base=base, densidade=densidade)}px {_escalado(h, base=base, densidade=densidade)}px"

    def da_folha(seletor: str) -> str:
        h, v = folha.recheio(RECHEIO_DA_FOLHA[seletor], base=base, densidade=densidade)
        return f"{v}px {h}px"

    superficie = cor(tokens.SUPERFICIE_PADRAO)
    texto = cor(tokens.TEXTO_PADRAO)
    secundario = cor(tokens.TEXTO_SECUNDARIO)
    morto = cor(tokens.TEXTO_MORTO)
    dica = cor(tokens.SUPERFICIE_DICA)
    linha = tipografia.folga(tipografia.FOLGA_DE_LINHA, base=base, densidade=densidade)
    minima = tipografia.folga(tipografia.FOLGA_MINIMA, base=base, densidade=densidade)
    vao = folha.vao_do_indicador(base=base, densidade=densidade)
    # **A faixa do título sai da mesma escala que o pinta, e este é o bloqueante do ciclo 13.**
    # Ela era `margin-top: linha px` -- um degrau de `FOLGA_DE_LINHA`, 6 px na confortável e
    # **4 px na compacta** --, e `_escala_tipografica` manda desenhar o título com
    # `escala(base)[TITULO]`, 12 pt, **21 px de altura**. Dois números de escalas diferentes
    # reservando e ocupando o mesmo lugar: o Qt punha o quadro do grupo a 4 px do topo, o
    # primeiro filho subia até lá, e a metade de baixo de cada letra do título saía **debaixo
    # dele** -- 6 de 6 títulos na compacta, pior caso 8 px de 21, medido nas três peles e nas
    # quatro larguras. `Lances`, `Comentário do lance` e `Filtros` chegavam à tela cortados ao
    # meio, e estava fotografado desde o ciclo 10 sem que régua nenhuma o visse: todas elas
    # perguntam a medida do texto a `QWidget.fontMetrics()`, e quem pinta é a folha.
    #
    # Agora as duas linhas leem a **mesma** fonte. Um degrau a mais no título move a faixa junto,
    # e a deriva deixa de ser possível em vez de ser reconsertada no ciclo seguinte.
    titulo_em_pontos = tipografia.escala(base)[PAPEL_PINTADO["QGroupBox::title"]]
    faixa_do_titulo = (
        int(altura_do_titulo)
        if altura_do_titulo and int(altura_do_titulo) > 0
        else tipografia.altura_do_texto(titulo_em_pontos)
    )

    regras = [
        # A superfície e a letra de base. Em Qt é preciso dizê-las: sem folha, o `QWidget` sai
        # com a cor do estilo da plataforma, e sob a pele "Foco" isso daria cromo claro com
        # rótulos pintados para fundo escuro -- meia dúzia de rótulos ilegíveis, que é
        # exatamente o defeito que a S-224 mediu no outro frontend.
        f"QWidget {{ background-color: {superficie}; color: {texto}; }}",
        # As superfícies de **documento** não são cromo e não seguem a pele: a folha do livro e
        # o tabuleiro ficam na paleta medida, e é `tokens.SUPERFICIES_DE_DOCUMENTO` que
        # garante isso. Aqui elas só não são sobrescritas -- quem as pinta é o `QPainter` de
        # `qt/visor.py` e de `qt/tabuleiro.py`, com `cor_atual`.
        f"QToolTip {{ background-color: {dica}; color: {tokens.sobre_superficie(dica)};"
        f" border: 1px solid {cor(tokens.CONTORNO_DE_CROMO)}; padding: {linha}px; }}",
        f"QPushButton {{ padding: {do_tema('QPushButton')}; }}",
        # **O botão comum desabilitado desenhava igual ao habilitado, e a medição é esta** (S-506):
        # fotografei a barra do visualizador antes e durante a exportação e diferenciei as duas
        # imagens -- a fileira com "OCR todos diagramas", "Exportar PDF → PGN" e "Cancelar
        # exportação" saiu **pixel a pixel idêntica**, com três daqueles botões trocando de estado.
        #
        # A causa é a linha do `QWidget` acima: uma cor vinda de folha de estilo vale em todos os
        # estados e anula o acinzentamento que o Qt faria pela paleta. `PRIMARIO` e `DESTRUTIVO`
        # escapavam por terem `:disabled` próprio, logo abaixo; o comum não tinha nenhum -- e é o
        # comum que o par exportar/cancelar usa para dizer qual dos dois está vivo.
        # **A tinta do morto é papel próprio desde o F9-C10** (`tokens.TEXTO_MORTO`). Enquanto
        # ela era `TEXTO_SECUNDARIO`, a distância entre o rótulo vivo e o morto era de 2,82:1 na
        # clássica e **1,88:1 na Foco** -- e o produto usa 3,0:1 como piso para uma listra de
        # tabela. Hoje: 3,66:1 e 3,27:1.
        f"QPushButton:disabled {{ color: {morto}; }}",
        f"QToolButton:disabled {{ color: {morto}; }}",
        f"QToolButton {{ padding: {do_tema('QToolButton')}; }}",
        f"QLineEdit {{ padding: {do_tema('QLineEdit')}; }}",
        f"QComboBox {{ padding: {do_tema('QComboBox')}; }}",
    ]

    # O recheio que sai de `ui/folha.py`, um seletor por classe. Um `try` por classe seria
    # teatro aqui: `folha.recheio` é pura e só levanta para classe fora da tabela, que é erro
    # deste módulo e não do ambiente -- e o `KeyError` dela é justamente o que o expõe.
    regras += [f"{seletor} {{ padding: {da_folha(seletor)}; }}" for seletor in RECHEIO_DA_FOLHA]

    # O vão entre o indicador e o rótulo (S-442). Em Qt ele é `spacing` e não
    # `indicatormargin`, e é a propriedade que o `QCheckBox` de fato lê.
    regras += [f"QCheckBox {{ spacing: {vao}px; }}", f"QRadioButton {{ spacing: {vao}px; }}"]

    # A ênfase da S-444. **Também aqui o tema não dá de graça, e pela razão oposta à do Tk:**
    # lá o `ttkbootstrap` pintava os três papéis do mesmo `#f0f0f0` e a folha corrigia; aqui
    # não existe papel nenhum até esta linha. O `[papel="..."]` é o seletor de propriedade
    # dinâmica, que é o mecanismo do Qt para o que `style="primary.TButton"` faz lá.
    letra = cor(tokens.TEXTO_SOBRE_ENFASE)
    # **O realce vai para longe da letra, e não para perto dela** (F9). A versão anterior
    # misturava a face **com a letra** (`mistura(face, letra, 0.18)`), o que é exatamente a
    # direção que apaga o rótulo: medido, `#ffffff` sobre a face primária clareada dá **4,47:1**
    # sob o ponteiro e **3,09:1** pressionada -- o botão mais importante da janela perde o piso
    # AA no instante em que a pessoa vai clicar nele, que é o pior momento possível para isso
    # acontecer. Agora ele mistura com o **oposto** da letra: escurece no tema claro, clareia no
    # escuro, e o contraste do rótulo **sobe** com o realce em vez de cair.
    for papel, token in (
        (estilos.PRIMARIO, tokens.BOTAO_PRIMARIO),
        (estilos.DESTRUTIVO, tokens.BOTAO_DESTRUTIVO),
    ):
        face = cor(token)
        sob_o_ponteiro = tokens.afastar(face, letra, tokens.REALCE_DE_ENFASE)
        # **O pressionado escurece, nas duas peles** -- ver `ESCURECIMENTO_DO_PRESSIONADO`. Ele
        # deixou de usar `afastar` de propósito: `afastar` anda para longe da letra, e na pele
        # escura a letra é quase preta, então o botão **clareava** ao ser pressionado.
        pressionado = tokens.escurecer(face, ESCURECIMENTO_DO_PRESSIONADO)
        letra_pressionada = letra_do_pressionado(pressionado, letra)
        regras += [
            f'QPushButton[{PROPRIEDADE_DE_PAPEL}="{papel}"]'
            f" {{ background-color: {face}; color: {letra}; border: 1px solid {face}; }}",
            # A borda acompanha a face em cada estado: sem isto ela fica na cor do repouso sobre
            # a face realçada, e o resultado é um contorno de 1 px a 1,44:1 em volta do botão --
            # uma linha desenhada que não se lê como borda nem some.
            f'QPushButton[{PROPRIEDADE_DE_PAPEL}="{papel}"]:hover'
            f" {{ background-color: {sob_o_ponteiro}; border: 1px solid {sob_o_ponteiro}; }}",
            f'QPushButton[{PROPRIEDADE_DE_PAPEL}="{papel}"]:pressed'
            f" {{ background-color: {pressionado}; color: {letra_pressionada};"
            f" border: 1px solid {pressionado}; }}",
            # O desabilitado é o do cromo, e não a face apagada. "Limpar os headers" **nasce
            # desabilitado**, e uma face vermelha sólida num botão que não responde é um pedido
            # de cuidado sobre uma ação que não existe -- é a medição da S-444, e ela vale aqui.
            f'QPushButton[{PROPRIEDADE_DE_PAPEL}="{papel}"]:disabled'
            f" {{ background-color: {superficie}; color: {morto};"
            f" border: 1px solid {cor(tokens.SEPARADOR)}; }}",
            # **O anel de foco do botao com enfase e a letra dele, e nao o azul de foco.** Sobre
            # uma face saturada o `FOCO` some: `#84b6ff` sobre `#6ea8fe` da 1,15:1. A letra ja e
            # a cor medida contra aquela face -- 4,5:1 no minimo, por `test_a_enfase_passa_no_piso`
            # --, entao ela e o unico valor que se ve em volta dos dois papeis sem uma cor nova.
            f'QPushButton[{PROPRIEDADE_DE_PAPEL}="{papel}"]:focus'
            f" {{ border: 2px solid {letra}; }}",
        ]

    # A faixa de abas discreta da pele "Foco" (S-226): a diferença é o **peso**, e a aba ativa se
    # separa por cor e por negrito. Em Qt isto é seletor de estado e não `style.map`, e por isso
    # cabe na folha em vez de precisar de um registro à parte.
    regras += [
        f"QTabBar::tab:selected {{ color: {texto}; font-weight: bold; }}",
        f"QTabBar::tab:!selected {{ color: {secundario}; }}",
        f"QGroupBox {{ margin-top: {faixa_do_titulo}px;"
        f" border: 1px solid {cor(tokens.CONTORNO_DE_CROMO)};"
        f" border-radius: {max(3, _escalado(RAIO_NA_BASE, base=base, densidade=densidade))}px; }}",
        f"QGroupBox::title {{ subcontrol-origin: margin; left: {linha}px; padding: 0 {minima}px; }}",
    ]
    regras += _escala_tipografica(base=base)
    regras += _relevo(cor, base=base, densidade=densidade, marcas=marcas or {})
    return "\n".join(regras)


def _caminho_qss(caminho: str) -> str:
    r"""Um caminho de disco como o `url()` de uma folha de estilo Qt o aceita.

    A contrabarra do Windows é escape em QSS: `C:\...\visto.png` chega ao analisador como
    `C:...visto.png` e a imagem some sem uma linha de erro -- que é o pior modo de falha
    possível numa folha de estilo. A barra normal funciona nas três plataformas.
    """
    return caminho.replace("\\", "/")


O_WIDGET = "widget"
"""Quem pinta é `QWidget.font()`: o Qt **ignora** o `font-*` que a folha declara no seletor."""

A_FOLHA = "folha"
"""Quem pinta é a declaração da folha: ela ganha do `QWidget.font()`."""

QUEM_PINTA: dict[str, str] = {
    "QGroupBox::title": O_WIDGET,
    "QHeaderView::section": A_FOLHA,
    "QTabBar::tab:selected": A_FOLHA,
    f'QLabel[{PROPRIEDADE_DE_APOIO}="true"]': A_FOLHA,
}
"""`seletor da folha -> qual das duas fontes o Qt de fato usa para desenhar`. **Medido no pixel.**

**Os quatro seletores desta folha não obedecem à mesma regra, e tratá-los como se obedecessem foi
o décimo segundo instrumento cego** (F9-C15 §4). O crítico mediu, e eu reproduzi com o meu
`benchmarks/reports/ui/c16/c16_quem_pinta.py`, um `Comentário do lance` isolado por seletor, com a
folha declarando um tamanho e o widget tendo outro (referências: 9 pt = 109 px, 12 pt negrito =
159 px, 20 pt negrito = 267 px):

```
  QGroupBox::title       folha 20pt / widget  9pt -> 109 px      o WIDGET
                         folha 12pt / widget 20pt -> 265 px      o WIDGET
  QHeaderView::section   folha 20pt / widget  9pt -> 265 px      a FOLHA
                         folha 12pt / widget 20pt -> 157 px      a FOLHA
  QTabBar::tab:selected  idem ao cabeçalho                       a FOLHA
  QLabel[apoio="true"]   idem ao cabeçalho                       a FOLHA
```

**O `QSS` de subcontrole de `QGroupBox` é o único em que o Qt não honra a fonte** -- o
`QStylePainter` do grupo desenha o título com a fonte do próprio widget, e a regra da folha só
alcança cor, posição e recheio. Quem põe 12 pt negrito naquele título é
`tipografia.PAPEL_POR_CLASSE["QGroupBox"]`, por `qt/escala.aplicar_escala`; a regra gerada abaixo
é herança que o Qt descarta, e ela fica porque outro estilo poderia honrá-la -- não porque este
honre.

**A consequência prática é a régua.** `caissa.ui.audit.texto_pintado` perguntava a fonte à folha
nos dois casos, e por isso dizia 85 px onde a tela desenhava 34. Hoje ela lê esta tabela e
pergunta à fonte que ganha -- `texto_pintado.fonte_que_pinta`.

**A tabela não pode ficar para trás da folha**, e é o que
`test_quem_pinta_cobre_toda_regra_de_fonte_da_folha` cobra: todo seletor com declaração `font-*`
no texto gerado tem de ter resposta aqui, senão a régua volta a chutar."""

PAPEL_PINTADO: dict[str, str] = {
    # **A fonte deste título é a do widget** (ver `QUEM_PINTA`), e por isso o degrau dele **é**
    # o que `PAPEL_POR_CLASSE` põe no `QGroupBox` -- lido de lá, e não repetido aqui. Enquanto
    # eram dois literais iguais em dois módulos, a faixa e a tinta ficavam em 21 px por
    # coincidência: bastava tirar `QGroupBox` da outra tabela para o título cair a 9 pt dentro
    # de uma faixa de 21 px, com o portão publicando `0 cobertos` (F9-C15 §4.2).
    "QGroupBox::title": tipografia.PAPEL_POR_CLASSE["QGroupBox"],
    "QHeaderView::section": tipografia.PAPEL_POR_CLASSE["QHeaderView"],
    f'QLabel[{PROPRIEDADE_DE_APOIO}="true"]': tipografia.AUXILIAR,
}
"""`seletor da folha -> degrau da escala com que ela o pinta`. **É a tabela que fecha a deriva.**

**O bloqueante do ciclo 13 foi dois números de escalas diferentes falando do mesmo lugar**, e a
lição não é o número: é que ninguém tinha onde perguntar *"com que fonte a folha pinta isto?"*.
Quem precisava saber -- `qt/tabela._largura_da_secao`, para dar largura a uma coluna;
`qt/tema.altura_do_titulo_atual`, para reservar a faixa do título -- perguntava a
`QWidget.font()`, que é a **outra** fonte, e as duas divergem por 12 pt contra 9 pt e por 700
contra 400. O cabeçalho `Resultado` pedia 76 px e ganhava uma seção medida sobre 52.

Agora a pergunta tem dono. `_escala_tipografica` **gera as regras a partir desta tabela**, e
`qt/tema.fonte_pintada` a responde já como `QFont`. Um seletor novo entra aqui uma vez e as duas
pontas -- o que desenha e o que reserva -- andam juntas por construção.

**E o degrau dos dois seletores de subcontrole vem de `tipografia.PAPEL_POR_CLASSE`** (F9-C16):
são a mesma decisão dita de dois lados, e enquanto foram dois literais o que as mantinha iguais
era coincidência. Quem responde *"com que fonte"* é esta tabela; quem responde *"qual das duas
fontes ganha"* é `QUEM_PINTA`, logo acima. São duas perguntas, e por isso duas tabelas."""


def _escala_tipografica(*, base: int) -> list[str]:
    """Os degraus da escala que a folha consegue dizer sozinha (F9-C2, §7 item 9).

    **Quem de fato pinta cada um destes seletores está medido em `QUEM_PINTA`, e não é o mesmo
    nos dois** (F9-C16). Em `QHeaderView::section` a regra daqui ganha do `QWidget.font()`; em
    `QGroupBox::title` o Qt a **descarta** e desenha com a fonte do widget, que é o que
    `qt/escala.aplicar_escala` põe lá a partir de `tipografia.PAPEL_POR_CLASSE`. Esta função
    escrevia, até o ciclo 15, que *"o QSS de subcontrole é o que o Qt honra ao pintar o título"* --
    e essa frase, medida no pixel, é falsa para metade dos seletores dela.

    A regra do título continua sendo gerada por duas razões, e nenhuma delas é "o Qt a honra":
    ela dá **cor** e **posição** ao título, que o Qt honra; e ela é a declaração escrita do degrau,
    que outro estilo pode honrar. O que mudou é que nada mais **depende** dela para saber com que
    fonte o título é desenhado.

    `QLabel[apoio="true"]` é a exceção que a folha resolve inteira: um rótulo não tem filho, então
    a regra de nível de widget não escorre para ninguém -- e o Qt, para regra de nível de widget,
    **muda** a fonte do objeto. É o degrau `AUXILIAR` do §7 item 9 aplicado a contagem, unidade,
    procedência e dica de estado vazio, sem uma linha de varredura.

    **As regras saem de `PAPEL_PINTADO` e não de três linhas escritas à mão** (F9-C14): quem
    reserva espaço para este texto -- a faixa do título, a largura da coluna -- lê a mesma tabela,
    e é isso que impede o desencontro que reprovou o ciclo 13 de voltar por outra porta.
    """
    pontos = tipografia.escala(base)
    regras = []
    for seletor, papel in PAPEL_PINTADO.items():
        declaracoes = f"font-size: {pontos[papel]}pt;"
        peso = tipografia.peso(papel)
        if peso >= tipografia.PESOS[tipografia.TITULO]:
            declaracoes += " font-weight: bold;"
        elif peso != tipografia.PESOS[tipografia.CORPO]:
            declaracoes += f" font-weight: {peso};"
        regras.append(f"{seletor} {{ {declaracoes} }}")
    return regras


def _relevo(
    cor: Callable[[str], str], *, base: int, densidade: str, marcas: dict[str, str] | None = None
) -> list[str]:
    """O relevo do cromo: face, borda, foco, seleção e barra de rolagem (F9).

    **Por que isto precisou existir, e a medição está no bloco de papéis de `ui/tokens.py`.**
    A folha até aqui dizia duas coisas -- a superfície e a letra -- e deixava o resto ao desenho
    nativo. Mas `QWidget { background-color: ... }` alcança **toda** subclasse: botão, campo,
    lista e painel saíam do mesmo hexadecimal. Na pele clássica isso passa, porque o estilo da
    plataforma ainda desenha uma borda por cima; na pele escura não sobra nada, e a fotografia da
    aba Estudo mostra quatro fileiras de botões que se leem como rótulos.

    **A escolha é declarar o cromo inteiro em vez de remendar o botão.** Um tema que estiliza
    metade dos controles é pior que um que não estiliza nenhum: a metade não estilizada continua
    saindo no cinza de fábrica, e a janela fica com dois vocabulários visuais. Então aqui estão
    todos os controles que a janela usa -- e o critério de "usa" é ter aparecido nas 24 capturas
    da auditoria.

    **`:focus` é obrigação, não enfeite.** A janela promete navegação inteira por teclado
    (SPEC §10.6), e teclado sem foco visível é a promessa quebrada em silêncio: quem tabula não
    sabe onde está. O anel é `FOCO`, medido a 3,0:1 contra painel, botão e campo nas duas
    paletas, que é o piso da WCAG 2.4.11.

    Recebe `cor` já fechada sobre a pele, e não `cromo_escuro`: quem decide o valor é
    `tokens.cor`, e repetir a decisão aqui seria a divergência que `ui/tokens.py` existe para não
    ter.
    """
    superficie = cor(tokens.SUPERFICIE_PADRAO)
    elevada = cor(tokens.SUPERFICIE_ELEVADA)
    afundada = cor(tokens.SUPERFICIE_AFUNDADA)
    sobre = cor(tokens.SUPERFICIE_SOBRE)
    pressionada = cor(tokens.SUPERFICIE_PRESSIONADA)
    contorno = cor(tokens.CONTORNO_DE_CROMO)
    separador = cor(tokens.SEPARADOR)
    foco = cor(tokens.FOCO)
    selecao = cor(tokens.SELECAO)
    sobre_selecao = cor(tokens.TEXTO_SOBRE_SELECAO)
    trilho = cor(tokens.TRILHO_DE_ROLAGEM)
    polegar = cor(tokens.POLEGAR_DE_ROLAGEM)
    # **O polegar da régua precisa de um limite mais forte que o dos controles** (F9). Ele é um
    # disco de face elevada sobre um trilho quase da mesma luminância: medido, `#fbfbfc` sobre
    # `#e6e7ea` dá **1,20:1**, e o contorno de cromo sobre o trilho dá 2,56 -- nem o
    # preenchimento nem a borda alcançam os 3,0 da 1.4.11, e o resultado é um polegar que se
    # adivinha. `TEXTO_SECUNDARIO` é o cinza medido da S-146 e dá 6,03 contra o trilho na paleta
    # clara e 7,64 na escura, com a mesma matiz neutra do contorno.
    polegar_forte = cor(tokens.TEXTO_SECUNDARIO)
    texto = cor(tokens.TEXTO_PADRAO)
    secundario = cor(tokens.TEXTO_SECUNDARIO)
    morto = cor(tokens.TEXTO_MORTO)
    primario = cor(tokens.BOTAO_PRIMARIO)

    # **O raio deixou de ser `espaco.minima()`** (F9-C2): raio de canto não é folga, e 2 px é
    # canto reto. Ver `RAIO_NA_BASE`.
    raio = max(3, _escalado(RAIO_NA_BASE, base=base, densidade=densidade))
    linha = espaco.linha()
    minima = espaco.minima()
    # A barra de rolagem acompanha a fonte como todo o resto (S-148): um valor cravado ignora
    # quem aumentou a fonte do Windows, e é a única medida deste bloco que não sai de `espaco`
    # porque não é folga -- é largura de controle.
    barra = _escalado(12, base=base, densidade=densidade)
    indicador = _escalado(14, base=base, densidade=densidade)
    trilho_da_regua = max(4, _escalado(6, base=base, densidade=densidade))

    controles_com_face = ("QPushButton", "QToolButton", "QComboBox")
    campos = (
        "QLineEdit",
        "QTextEdit",
        "QPlainTextEdit",
        "QAbstractSpinBox",
        "QListView",
        "QTreeView",
        "QTableView",
        "QListWidget",
        "QTreeWidget",
        "QTableWidget",
    )

    regras: list[str] = []

    # ------------------------------------------------------------------ face dos controles
    for seletor in controles_com_face:
        regras += [
            f"{seletor} {{ background-color: {elevada}; color: {texto};"
            f" border: 1px solid {contorno}; border-radius: {raio}px; }}",
            f"{seletor}:hover {{ background-color: {sobre}; }}",
            f"{seletor}:pressed {{ background-color: {pressionada}; }}",
            # **Desabilitado perde a face inteira, e não só a letra.** Um botão morto com a
            # mesma face do vivo é o defeito que a fotografia da barra do visualizador mediu:
            # "Exportar PDF → PGN" e "Cancelar exportação" saíam pixel a pixel iguais com um
            # dos dois desligado.
            f"{seletor}:disabled {{ background-color: {superficie}; color: {morto};"
            f" border: 1px solid {separador}; }}",
            f"{seletor}:focus {{ border: 2px solid {foco}; padding: 0px; }}",
        ]
    regras += [
        f"QToolButton:checked {{ background-color: {selecao}; color: {sobre_selecao};"
        f" border: 1px solid {foco}; }}",
        # **`::drop-down` e `::up-button` ficam sem regra, e é decisão medida.** A primeira
        # versão deste bloco declarava `QComboBox::drop-down {{ border: none; width: ... }}` --
        # e a prancha de controles mostrou a caixa de escolha **sem seta nenhuma**. Em Qt,
        # estilizar uma subpeça faz o estilo nativo parar de desenhá-la inteira, e a seta é um
        # `::down-arrow` que só volta com um PNG em disco. Um controle de escolha que não se
        # anuncia como tal é pior que um com a seta do sistema: a seta nativa é desenhada com a
        # cor do texto, que a folha já define, e por isso ela acompanha a pele de graça.
        f"QComboBox QAbstractItemView {{ background-color: {elevada}; color: {texto};"
        f" border: 1px solid {contorno}; selection-background-color: {selecao};"
        f" selection-color: {sobre_selecao}; }}",
    ]

    # ------------------------------------------------------------------------ poços e listas
    for seletor in campos:
        regras += [
            # **`placeholder-text-color` é o conserto do bloqueante do ciclo 5, e a linha que
            # estava aqui antes não era ele.** O comentário anterior descrevia o defeito com
            # precisão -- *"o Qt desenha o `placeholderText` com a cor do texto a 50 % de
            # alfa"* -- e a regra que ele introduzia mexia em `selection-background-color`, o
            # realce da seleção, que não tem relação nenhuma com a dica. Sondado na janela
            # viva: `le.palette().color(Active, PlaceholderText)` devolvia **`#000000` com
            # alpha 128** na pele clara, e `#000000` a 50 % sobre o poço `#f8f9fb` compõe
            # `rgb(124,124,126)` -- **3,96:1**, abaixo do piso AA de 4,5. Não é
            # anti-aliasing; é a aritmética da composição, e nenhuma tabela de cor a via
            # porque o token que a tabela resolve (`TEXTO_SECUNDARIO`) é **opaco**.
            #
            # Declarada, a dica deixa de ser derivada: o Qt põe o valor na `QPalette` com
            # alpha 255 e desenha exatamente ele. `TEXTO_SECUNDARIO` dá **7,08:1** sobre o
            # poço claro e **7,95:1** sobre o escuro -- e **6,54:1** / **7,14:1** sobre a
            # superfície do campo desabilitado, que é o `:disabled` logo abaixo. A dica
            # continua distinta do texto de verdade (`TEXTO_PADRAO`), que é o que ela precisa
            # ser para não se ler como conteúdo.
            #
            # O arnês aprendeu o mesmo na mesma hora (`caissa.ui.audit.contraste`): ele
            # compõe o alfa antes de calcular a razão e deriva a dica da **folha**, não do
            # token -- senão continuaria publicando 7,08:1 para uma tela de 3,96:1.
            f"{seletor} {{ background-color: {afundada}; color: {texto};"
            f" border: 1px solid {contorno}; border-radius: {raio}px;"
            f" placeholder-text-color: {secundario};"
            f" selection-background-color: {selecao}; selection-color: {sobre_selecao}; }}",
            f"{seletor}:focus {{ border: 2px solid {foco}; }}",
            # A **letra** do campo morto é `TEXTO_MORTO` (F9-C10); a **dica** dele continua
            # sendo o secundário, e a diferença é a pergunta de cada uma: a letra diz "isto não
            # responde" e é medida contra a letra viva; a dica diz "isto espera um valor" e é
            # medida contra o poço. Igualá-las apagaria uma das duas.
            f"{seletor}:disabled {{ background-color: {superficie}; color: {morto};"
            f" placeholder-text-color: {secundario};"
            f" border: 1px solid {separador}; }}",
        ]
    regras += [
        f"QAbstractItemView::item:hover {{ background-color: {sobre}; }}",
        f"QAbstractItemView::item:selected {{ background-color: {selecao};"
        f" color: {sobre_selecao}; }}",
        f"QHeaderView::section {{ background-color: {elevada}; color: {texto};"
        f" border: none; border-right: 1px solid {separador};"
        f" border-bottom: 1px solid {contorno}; padding: {minima}px {linha}px; }}",
        f"QHeaderView::section:hover {{ background-color: {sobre}; }}",
    ]

    # --------------------------------------------------- indicador de marca e de escolha
    # **O preenchimento não bastava, e a WCAG diz por quê** (F9-C2, §7 item 17). No ciclo 1
    # "marcada" era um quadrado azul cheio e "indeterminada" um quadrado cinza cheio: mesma
    # forma, mesmo tamanho, **só a matiz separa** -- 1.4.1 nível A, reprovado. O argumento de
    # então -- "um visto em QSS precisa de um PNG em disco, e um PNG que falte apaga a marca" --
    # continua verdadeiro, e é por isso que ele virou a **reserva** em vez do desenho: a face
    # colorida fica onde estava, e a marca entra por cima quando o desenho existe.
    #
    # Os dois caminhos vêm de `qt/tema.py`, que gera os traços de `ui/icones.MARCAS` com a
    # Pillow que já desenha os ícones da fita. Sem eles, a folha sai exatamente como saía.
    marcas = marcas or {}
    regras += [
        f"QCheckBox::indicator, QRadioButton::indicator"
        f" {{ width: {indicador}px; height: {indicador}px;"
        f" background-color: {afundada}; border: 2px solid {contorno}; }}",
        f"QCheckBox::indicator {{ border-radius: {max(2, raio - 1)}px; }}",
        f"QRadioButton::indicator {{ border-radius: {indicador // 2 + 2}px; }}",
        f"QCheckBox::indicator:hover, QRadioButton::indicator:hover"
        f" {{ border: 2px solid {foco}; }}",
        f"QCheckBox::indicator:checked, QRadioButton::indicator:checked"
        f" {{ background-color: {primario}; border: 2px solid {primario}; }}",
        f"QCheckBox::indicator:indeterminate"
        f" {{ background-color: {secundario}; border: 2px solid {contorno}; }}",
        f"QCheckBox::indicator:disabled, QRadioButton::indicator:disabled"
        f" {{ background-color: {superficie}; border: 2px solid {separador}; }}",
        # **O RÓTULO da caixa morta era desenhado com a tinta viva** (F9-C10), e foi o meu
        # instrumento do estado morto que o achou: só o `::indicator` tinha regra de
        # `:disabled`, e a linha `QWidget { color: ... }` do topo vale em todos os estados e
        # anula o acinzentamento que o Qt faria pela paleta -- é a mesma causa que a S-506 mediu
        # no `QPushButton` comum, um widget adiante. Medido em `Só duplicatas` e
        # `Imagem ausente`, dois de dois, nas três peles.
        f"QCheckBox:disabled, QRadioButton:disabled {{ color: {morto}; }}",
        f"QCheckBox:focus, QRadioButton:focus {{ color: {texto}; }}",
    ]
    if marcas.get(icones.MARCA_VISTO):
        regras.append(
            f"QCheckBox::indicator:checked"
            f' {{ image: url("{_caminho_qss(marcas[icones.MARCA_VISTO])}"); }}'
        )
    if marcas.get(icones.MARCA_TRACO):
        regras.append(
            f"QCheckBox::indicator:indeterminate"
            f' {{ image: url("{_caminho_qss(marcas[icones.MARCA_TRACO])}"); }}'
        )

    # ------------------------------------------------------------------ barra de rolagem
    # **Ela era a prova mais barata de que o tema escuro não era um tema** (F9): sob a pele
    # escura o trilho e as setas continuavam saindo no branco do estilo da plataforma, porque
    # `QWidget { background-color }` não alcança as subpeças. Uma faixa branca de 12 px de cada
    # lado da página é o primeiro pixel que qualquer crítico vê.
    for eixo, largura in (("horizontal", "height"), ("vertical", "width")):
        regras.append(
            f"QScrollBar:{eixo} {{ background-color: {trilho}; {largura}: {barra}px;"
            f" margin: 0px; border: none; }}"
        )
    regras += [
        f"QScrollBar::handle {{ background-color: {polegar}; border-radius: {raio}px;"
        f" min-width: {barra * 2}px; min-height: {barra * 2}px; }}",
        f"QScrollBar::handle:hover {{ background-color: {texto}; }}",
        # As setas de fim de trilho saem: elas são alvo de 12 px que ninguém acerta, e o Qt
        # desenha o triângulo delas com a cor do estilo nativo -- o mesmo branco do trilho.
        "QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; border: none; }",
        "QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }",
    ]

    # ------------------------------------------------------------------------ faixa de abas
    # A faixa ganha forma: sem isto o `QTabBar` sai no desenho da plataforma, e a aba ativa se
    # distinguia só por negrito -- que é peso e não posição. Aqui ela sobe para a face elevada e
    # perde a borda de baixo, que é o que a liga ao painel.
    regras += [
        f"QTabWidget::pane {{ border: 1px solid {contorno}; border-radius: {raio}px;"
        f" background-color: {superficie}; top: -1px; }}",
        "QTabBar { background: transparent; }",
        f"QTabBar::tab {{ background-color: {superficie}; border: 1px solid {separador};"
        f" border-bottom: none; border-top-left-radius: {raio}px;"
        f" border-top-right-radius: {raio}px; margin-right: {minima}px; }}",
        f"QTabBar::tab:selected {{ background-color: {elevada};"
        f" border: 1px solid {contorno}; border-bottom: 2px solid {foco}; }}",
        f"QTabBar::tab:!selected:hover {{ background-color: {sobre}; color: {texto}; }}",
        f"QTabBar::tab:focus {{ border: 2px solid {foco}; }}",
    ]

    # ---------------------------------------------------------------- menu, barra e divisor
    regras += [
        f"QMenuBar {{ background-color: {superficie}; color: {texto};"
        f" border-bottom: 1px solid {separador}; }}",
        f"QMenuBar::item {{ background: transparent; padding: {minima}px {linha}px; }}",
        f"QMenuBar::item:selected {{ background-color: {selecao}; color: {sobre_selecao};"
        f" border: 1px solid {foco}; border-radius: {raio}px; }}",
        f"QMenu {{ background-color: {elevada}; color: {texto};"
        f" border: 1px solid {contorno}; padding: {minima}px; }}",
        f"QMenu::item {{ padding: {minima}px {linha * 2}px; }}",
        f"QMenu::item:selected {{ background-color: {selecao}; color: {sobre_selecao};"
        f" border: 1px solid {foco}; }}",
        f"QMenu::item:disabled {{ color: {morto}; }}",
        f"QMenu::separator {{ height: 1px; background-color: {separador};"
        f" margin: {minima}px 0px; }}",
        # **O divisor precisa ser visível e agarrável, e são duas coisas.** Visível é a linha de
        # 1 px; agarrável é a faixa de folga em volta dela, que o Qt não dá por padrão -- um
        # divisor de 1 px é um alvo que se erra, e errá-lo redimensiona o painel errado.
        #
        # **Seis pixels, e não três** (F9-C3). `max(3, minima)` dava exatamente **3 px** na
        # densidade padrão, porque `espaco.minima()` é 2: metade do alvo que o próprio Qt usa por
        # omissão, para a alça que reparte a janela inteira. Ela é o alvo mais consequente da tela
        # e era o menor.
        f"QSplitter::handle {{ background-color: {separador}; }}",
        f"QSplitter::handle:horizontal {{ width: {max(6, 3 * minima)}px; }}",
        f"QSplitter::handle:vertical {{ height: {max(6, 3 * minima)}px; }}",
        f"QSplitter::handle:hover {{ background-color: {foco}; }}",
        f"QStatusBar {{ background-color: {superficie}; color: {secundario};"
        f" border-top: 1px solid {separador}; }}",
        f"QToolBar {{ background-color: {superficie}; border: none;"
        f" spacing: {minima}px; }}",
        f"QToolBar::separator {{ background-color: {separador}; width: 1px;"
        f" margin: {minima}px {linha}px; }}",
        f"QFrame[frameShape=\"4\"] {{ color: {separador}; }}",
        f"QFrame[frameShape=\"5\"] {{ color: {separador}; }}",
    ]

    # ------------------------------------------------------- progresso, régua e dica de foco
    regras += [
        f"QProgressBar {{ background-color: {afundada}; border: 1px solid {contorno};"
        f" border-radius: {raio}px; text-align: center; color: {texto}; }}",
        f"QProgressBar::chunk {{ background-color: {primario}; border-radius: {raio}px; }}",
        # **`add-page` é obrigatório, e a prancha é quem provou.** Sem ele o Qt desenha o trecho
        # à direita do polegar com o estilo nativo -- e o resultado fotografado foi um retângulo
        # de contorno azul em volta da régua inteira, que se lia como barra de progresso cheia e
        # não como régua a 89%. Declarar dois dos três trechos é pior que declarar nenhum.
        f"QSlider::groove:horizontal {{ background-color: {trilho};"
        f" height: {trilho_da_regua}px; border-radius: {trilho_da_regua // 2}px; }}",
        f"QSlider::sub-page:horizontal {{ background-color: {primario};"
        f" height: {trilho_da_regua}px; border-radius: {trilho_da_regua // 2}px; }}",
        f"QSlider::add-page:horizontal {{ background-color: {trilho};"
        f" height: {trilho_da_regua}px; border-radius: {trilho_da_regua // 2}px; }}",
        # A margem negativa é o que faz o polegar transbordar o trilho em vez de ser espremido
        # dentro dele; o raio maior que a metade da altura é o que o faz redondo.
        f"QSlider::handle:horizontal {{ background-color: {elevada};"
        f" border: 2px solid {polegar_forte}; width: {indicador}px; height: {indicador}px;"
        f" margin: -{(indicador - trilho_da_regua) // 2 + 2}px 0px;"
        f" border-radius: {indicador // 2 + 2}px; }}",
        f"QSlider::handle:horizontal:hover {{ border: 2px solid {foco}; }}",
        # **O foco da régua é do widget, e não do polegar** -- e as duas formas óbvias foram
        # medidas e recusadas. `QSlider:focus::handle:horizontal` o Qt 6.11 **não** analisa como
        # subpeça: ele aplica a borda ao widget inteiro e **ignora o `:focus`**, então a régua sai
        # com um retângulo azul em volta o tempo todo (foi o defeito que a prancha fotografou).
        # `QSlider::handle:horizontal:focus` analisa, mas casa sempre -- subpeça não tem estado de
        # foco --, e o anel fica aceso sem que ninguém esteja lá.
        #
        # A saída é reservar a borda desde sempre e só trocar a cor: sem isto o anel empurraria o
        # trilho 2 px ao ganhar foco, que é o "algo que salta durante a interação" que a carta do
        # crítico reprova sozinho.
        # **O recheio é o que separa o anel do trilho** (F9). Sem ele o retângulo de foco encosta
        # na régua, e a prancha de controles mostra o resultado: um contorno azul de ponta a ponta
        # rente a um trilho azul, que se lê como **barra de progresso cheia** e não como régua com
        # foco. Quatro pixels de folga em volta bastam para o anel virar anel.
        f"QSlider {{ border: 2px solid transparent; padding: {minima * 2}px {minima}px; }}",
        f"QSlider:focus {{ border: 2px solid {foco}; border-radius: {raio}px; }}",
        # **A moldura do grupo troca de dono aqui** (F9). A regra anterior a pinta com `MOLDURA`,
        # que é `SUPERFICIES_DE_DOCUMENTO` e por isso não segue a pele: sob a pele escura ela dá
        # **1,04:1** contra o painel -- uma linha desenhada e invisível, que a fotografia da aba
        # Estudo mostra. Esta regra vem depois e ganha, pela cascata.
        f"QGroupBox::title {{ color: {secundario}; }}",
        "QLabel { background: transparent; }",
        f"QLabel:disabled {{ color: {morto}; }}",
    ]
    return regras



# ------------------------------------------------------ a paleta, por nome de papel (F9)

PAPEIS_DA_PALETA: dict[str, str] = {
    "Window": tokens.SUPERFICIE_PADRAO,
    "WindowText": tokens.TEXTO_PADRAO,
    "Base": tokens.SUPERFICIE_AFUNDADA,
    "AlternateBase": tokens.SUPERFICIE_PADRAO,
    "Text": tokens.TEXTO_PADRAO,
    "Button": tokens.SUPERFICIE_ELEVADA,
    "ButtonText": tokens.TEXTO_PADRAO,
    "BrightText": tokens.TEXTO_SOBRE_ENFASE,
    "Highlight": tokens.SELECAO,
    "HighlightedText": tokens.TEXTO_SOBRE_SELECAO,
    "ToolTipBase": tokens.SUPERFICIE_DICA,
    "ToolTipText": tokens.TEXTO_PADRAO,
    "PlaceholderText": tokens.TEXTO_SECUNDARIO,
    "Link": tokens.VIZINHA_TEXTO,
    "LinkVisited": tokens.DIVERGENTE_TEXTO,
    "Mid": tokens.CONTORNO_DE_CROMO,
    "Midlight": tokens.SUPERFICIE_SOBRE,
    "Dark": tokens.CONTORNO_DE_CROMO,
    "Light": tokens.SUPERFICIE_ELEVADA,
    "Shadow": tokens.SEPARADOR,
}
"""`QPalette.ColorRole` (pelo nome) -> papel de `ui/tokens.py`, para os grupos vivos.

**Nome e não `QPalette.ColorRole`, e é a fronteira inteira deste módulo.** O enum mora no
toolkit; o mapa é decisão. `qt/tema.py` faz `getattr(QPalette.ColorRole, nome)` e acabou --
cinco linhas de tradução contra vinte de decisão que passam a ser afirmáveis sem Qt instalado.

**`ToolTipText` está aqui porque a folha não o alcança.** O QSS pinta `QToolTip`, mas a dica é
uma janela de nível superior que o Qt monta a partir da paleta antes de a folha valer em alguns
caminhos; sem a linha, o texto da dica sai no preto de fábrica sobre o `#33312a` da dica escura.

**`Midlight` e `BrightText` entram por completude, e completude aqui tem custo zero**: um papel
de paleta deixado por resolver não fica neutro, fica com o valor do estilo da plataforma -- que
é claro. Meia paleta trocada é a mesma família de defeito que meia folha de estilo.
"""

PAPEIS_DA_PALETA_MORTA: dict[str, str] = {
    "WindowText": tokens.TEXTO_MORTO,
    "Text": tokens.TEXTO_MORTO,
    "ButtonText": tokens.TEXTO_MORTO,
    "HighlightedText": tokens.TEXTO_MORTO,
    "Base": tokens.SUPERFICIE_PADRAO,
    "Button": tokens.SUPERFICIE_PADRAO,
    "Highlight": tokens.SUPERFICIE_PADRAO,
    "Window": tokens.SUPERFICIE_PADRAO,
}
"""O grupo `Disabled`, e ele é grupo próprio em vez de um alfa.

Sem estas linhas o Qt apaga o texto morto derivando-o do `WindowText` -- e a derivação dele
contra o cromo escuro cai em 2,6:1. Texto desabilitado é isento do critério 1.4.3 da WCAG;
**um número que ninguém escolheu**, não.

**Era `TEXTO_SECUNDARIO`, e passou a ser `TEXTO_MORTO` no F9-C10.** A escolha antiga dava ao
desabilitado a mesma legibilidade do texto de apoio -- e, com isso, **1,88:1** de distância entre
o rótulo vivo e o morto na pele Foco, com 22 de 22 rótulos mortos mais legíveis que o vivo mais
fraco. Um estado que o olho não separa não é um estado. Hoje a distância é 3,66:1 na clássica e
3,27:1 na Foco, e a legibilidade do morto continua em 5,04:1 e 4,10:1 contra a superfície -- ver
o docstring de `tokens.TEXTO_MORTO`, onde a conta e o que ela custou estão escritos.
"""
