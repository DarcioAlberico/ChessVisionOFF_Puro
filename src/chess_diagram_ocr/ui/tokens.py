"""A paleta do produto, num lugar só — papéis semânticos, não hexadecimais (S-145).

**O que havia antes.** 25 cores cravadas em 8 arquivos, sem lugar onde a paleta existisse
inteira. As consequências foram medidas, não supostas:

- **três verdes com três significados de "bom"**: `#00c07a` "já salvo" no visualizador,
  `#2e7d32` "veio da base" na Galeria, e o `success` do tema (`#146c43`) que ninguém usava;
- **dois cinzas** para o mesmo papel de texto secundário, `#555555` em três arquivos e
  `#666666` num quarto;
- nenhuma delas passava pelo `Style`, então nenhuma respondia a troca de tema.

**Duas camadas, e a separação é o item.** Em cima, os **papéis**: o painel pede `PRONTO` ou
`TEXTO_SECUNDARIO` e nunca um hexadecimal. Embaixo, a **resolução**: dado o `Style` em uso,
o papel vira cor — preferindo o token do tema quando existe, e caindo na reserva quando não.

**Sem `tkinter` aqui.** O módulo recebe um objeto com `.lookup(...)` e não sabe de onde ele
veio; é o que permite testar a paleta inteira sem abrir janela, e é a mesma disciplina do
`board_render`, que desenha sem widget.

**A regra de cor-de-marcação contra cor-de-texto (S-146).** Um verde que serve de borda de
retângulo sobre a página **não** serve de texto sobre branco: a razão de contraste que importa
é outra em cada caso. Por isso `PRONTO` e `PRONTO_TEXTO` são dois papéis, e não um com dois
usos — ver `razao_de_contraste`, que é o instrumento que decide.
"""

from __future__ import annotations

from typing import Protocol

__all__ = [
    "NO_CROMO_ESCURO",
    "PAPEIS",
    "RESERVA",
    "SUPERFICIES",
    "SUPERFICIES_DE_DOCUMENTO",
    "cor",
    "paleta",
    "distancia_de_matiz",
    "matiz",
    "razao_de_contraste",
    "saturacao",
    "sobre_superficie",
    "tema_e_escuro",
]


class Estilo(Protocol):
    """O mínimo que este módulo usa de um `ttk.Style`. Existe para não importar `tkinter`."""

    def lookup(self, layout: str, option: str) -> object: ...


# --------------------------------------------------------------------------- os papéis

TEXTO_SECUNDARIO = "TEXTO_SECUNDARIO"
"""Texto de apoio: contagem, material, linha do motor. Um cinza, não dois."""

PRONTO = "PRONTO"
"""**Marcação** de "este diagrama já rendeu amostra". Borda de retângulo sobre a página."""

PRONTO_TEXTO = "PRONTO_TEXTO"
"""O mesmo significado, como **texto**. Cor diferente por obrigação, não por gosto (S-146)."""

A_FAZER = "A_FAZER"
"""Marcação de "o detector achou isto aqui" — localizado e ainda não lido."""

LIDO = "LIDO"
"""Marcação de "o OCR já leu este" — lido e ainda não salvo."""

DISPENSADO = "DISPENSADO"
"""Marcação de "a base reconheceu, não precisa de olho nenhum" (S-75)."""

ATENCAO = "ATENCAO"
PROBLEMA = "PROBLEMA"
"""Casa culpada, posição ilegal, ação destrutiva."""

DIVERGENTE = "DIVERGENTE"
"""Casa em que duas leituras discordam (a 2ª opinião da S-66)."""

PROBLEMA_TEXTO = "PROBLEMA_TEXTO"
DIVERGENTE_TEXTO = "DIVERGENTE_TEXTO"
"""Os mesmos dois significados, como **texto** -- a mensagem de erro do rodapé, o aviso do campo,
a linha "achada por nome" da lista de partidas.

**Nasceram na S-224, e o cromo escuro é quem os separou.** Até aqui `PROBLEMA` e `DIVERGENTE`
faziam as duas coisas com um nome só: contorno de casa no tabuleiro e letra sobre o cromo. Na
paleta clara isso passou despercebido porque **o mesmo valor serve aos dois** -- `#c0392b` dá
3,96:1 sobre a casa clara e 4,77:1 sobre o cinza do cromo. Sobre um cromo escuro os dois usos
pedem valores opostos: a letra precisa clarear para ser lida, e o contorno precisa **não**
clarear, porque ele é medido contra as casas, que não seguem pele nenhuma.

É a S-158 outra vez -- *um papel, um significado* --, encontrada por um caminho novo. Na pele
clássica os dois pares têm o mesmo valor de propósito: separar os nomes não muda um pixel de
hoje, e é o que permite que só a pele escura os afaste."""

CORRIGIDO = "CORRIGIDO"
"""**Marcação** de casa que o decodificador reescreveu em relação ao que o modelo leu.

Era `#3d7dd4`, um azul a **3,6° de matiz** do `#4da3ff` que a página usa para "localizado e
ainda não lido" -- a mesma cor, dois significados, nos dois painéis que ficam lado a lado
(S-158). Virou uma azeitona escura por eliminação medida: das 360 matizes, as únicas livres de
todos os papéis com que esta pode ser confundida estão entre 70° e 90°.

E a troca **melhorou o que a antiga fazia mal**: o azul dava 3,01:1 sobre a casa clara e
**1,31:1** sobre a escura -- uma borda que sumia em metade do tabuleiro. Esta dá 8,32 e 3,62."""

VIZINHA_TEXTO = "VIZINHA_TEXTO"
"""A procedência "veio do diagrama vizinho", como **texto**, na lista de partidas.

Chamava-se `CORRIGIDO_TEXTO` e era descrita como "o mesmo azul, como texto" -- mas o
significado nunca foi o mesmo: "esta casa foi reescrita" e "esta partida veio do diagrama ao
lado" são duas coisas, e carregavam uma matiz só. Renomear é o item (S-158): um papel, um
significado."""

SUPERFICIE_PAGINA = "SUPERFICIE_PAGINA"
"""O fundo do canvas do visualizador de PDF."""

SUPERFICIE_TABULEIRO = "SUPERFICIE_TABULEIRO"
"""O fundo do canvas do tabuleiro — **dos dois**, e é esse o item (S-147).

Havia dois papéis aqui, `SUPERFICIE_TABULEIRO` (`#f2f2f2`) e `SUPERFICIE_ESTUDO` (`#262421`),
e o **mesmo** `InteractiveBoard` aparecia claro numa aba e escuro na aba vizinha porque cada
painel passava um `background=` diferente para o construtor. Nada além do argumento justificava
a diferença: a escolha "claro no Resultado" é anterior à S-20, de quando aquele canvas era
somente-leitura.

O valor que sobrou é o tom de esteira escuro, e não o claro, porque é ele que dá **11,03:1** às
coordenadas — ver `sobre_superficie`. A S-146 tratou o sintoma escolhendo a cor da letra contra
o fundo; unificar a superfície resolve a mesma coisa pela origem."""

SUPERFICIE_DICA = "SUPERFICIE_DICA"
"""O amarelo pálido do tooltip e da caixa de ajuda."""

MOLDURA = "MOLDURA"
"""O anel de 2 px desenhado em volta do tabuleiro, um degrau abaixo da esteira.

Depois da S-147 a esteira já é escura, então a moldura deixou de ser o que separa o tabuleiro
do painel e passou a ser o que assenta o tabuleiro na esteira. Daí ela ser **mais escura** que
`SUPERFICIE_TABULEIRO`, e não a mesma cor: duas cores iguais em papéis diferentes é o defeito
que a S-145 mediu."""

COORDENADA = "COORDENADA"
"""As letras a–h e os números 8–1. **Resolvida contra a superfície** — ver `sobre_superficie`."""

CASA_CLARA = "CASA_CLARA"
CASA_ESCURA = "CASA_ESCURA"
CASA_ULTIMO_LANCE = "CASA_ULTIMO_LANCE"
ALVO = "ALVO"
"""A identidade do tabuleiro. Não segue tema: xadrez impresso é claro-e-escuro em qualquer
tema, e um tabuleiro que muda de cor com a janela deixa de ser reconhecível como tabuleiro."""

CONTORNO_DE_SELECAO = "CONTORNO_DE_SELECAO"
"""A casa que está selecionada agora. **Contorno, e não preenchimento** (S-160).

Havia dois amarelos no tabuleiro, `#f7ec74` (selecionada) e `#cdd26a` (último lance), a
**1,32:1** um do outro — e frequentemente adjacentes, porque selecionar a casa de destino do
lance que acabou de ser jogado é o gesto mais comum da aba Análise.

A saída não foi um terceiro amarelo: foi tirar a seleção do canal de preenchimento. É o mesmo
raciocínio que `ui/pdf_panel.py` já aplicava às caixas da página — *uma propriedade visual, uma
informação* —, e que aqui faltava. O amarelo ficou sozinho no papel dele, e a seleção passou a
ser forma.

**Acromático de propósito.** Depois da S-158 não sobrou matiz livre no tabuleiro: azul, violeta,
vermelho, verde e azeitona já têm dono, e a única faixa vaga era um ciano a 21° do azul da
página. Um cinza quase preto não disputa matiz com ninguém — e dá 13,42:1 sobre a casa clara,
5,85 sobre a escura e **11,42 sobre o amarelo do último lance**, que é o par que o item existe
para separar."""

SETA_VERDE = "SETA_VERDE"
SETA_VERMELHA = "SETA_VERMELHA"
SETA_AZUL = "SETA_AZUL"
SETA_AMARELA = "SETA_AMARELA"
"""As quatro cores de seta e de casa marcada do tabuleiro de estudo (S-279).

**São quatro porque o formato só sabe quatro.** `chess.svg.Arrow.pgn` escreve `G`, `R`, `B` e `Y` e
transforma qualquer outra cor em verde na gravação -- uma quinta cor seria uma cor que não sobrevive
ao arquivo. Não é escolha de paleta: é o alfabeto de `[%cal]`/`[%csl]`, que é o mesmo do Lichess, do
ChessBase e do Scid.

**Elas moram aqui e não no tabuleiro** por uma razão que este módulo já registra em `CASA_CLARA`: a
seta é desenhada sobre as duas casas, a clara e a escura, e um hexadecimal cravado no renderizador
seria mais um número solto -- o defeito que a S-145 veio fechar. Os valores são escuros e saturados
o bastante para se lerem sobre `#f0d9b5` e sobre `#b58863` sem depender de transparência, que o
canvas do Tk não tem."""

TEXTO_SOBRE_MARCACAO = "TEXTO_SOBRE_MARCACAO"
"""O número dentro do retângulo do diagrama, e o rótulo sobre a casa. Escuro, sobre marcação."""

TRACEJADO = "TRACEJADO"
"""O tracejado da seleção de área, desenhado sobre a página renderizada."""

AUTOR_DESTAQUE = "AUTOR_DESTAQUE"
AUTOR_CITACAO = "AUTOR_CITACAO"
AUTOR_NOTA = "AUTOR_NOTA"
AUTOR_VARIANTE = "AUTOR_VARIANTE"
"""As quatro cores que **quem escreve** aplica à letra, no editor de texto (S-242).

Elas existem separadas de tudo o mais por uma razão de significado, e não de gosto: naquela aba a
cor da letra **já quer dizer** confiança -- `revisar` sai em `PROBLEMA` e `conferir` em `ATENCAO`
--, e uma paleta de autor que oferecesse aquelas duas tintas produziria a mesma cor com dois
significados na mesma linha. Nenhum papel da faixa entra na paleta do autor, e quem afirma a
interseção vazia é `tests/test_ui_texto_cor.py`.

**As matizes são escolhidas por distância, como manda a S-158**: 310°, 185°, 130° e 230°, com no
mínimo 45° entre si e 66° do vermelho da faixa. Os valores foram procurados, e não escolhidos: são
os mais claros de cada matiz que ainda passam 4,8:1 sobre `#f0f0f0` **e** sobre o branco."""

REALCE_DESTAQUE = "REALCE_DESTAQUE"
REALCE_CITACAO = "REALCE_CITACAO"
REALCE_NOTA = "REALCE_NOTA"
REALCE_VARIANTE = "REALCE_VARIANTE"
"""O mesmo conceito no **fundo** da letra -- o canal que a S-242 dá ao autor.

Realce e não cor de letra é a decisão do item: o fundo é um canal livre naquela aba, e ninguém lê
"amarelo atrás da palavra" como *"o motor adivinhou"*.

**A régua deles é ao contrário**: o que se afirma não é o contraste do realce, e sim o do que vai
**por cima** dele. Cada valor é o mais saturado da sua matiz que mantém as três tintas que podem
cair ali -- `PROBLEMA`, `ATENCAO` e o texto normal -- acima de 4,7:1. É por isso que eles são
superfícies (`SUPERFICIES`) e escurecem com o tema, como a dica."""

TEXTO_PADRAO = "TEXTO_PADRAO"
SUPERFICIE_PADRAO = "SUPERFICIE_PADRAO"
"""A reserva de quando o próprio `Style` não responde.

Elas existem porque `board_widget` pergunta ao tema a cor de texto e de fundo para desenhar a
paleta de peças dentro de um canvas -- e um `Style` de tema exótico devolve string vazia. Sem
elas o `or "#000000"` ficava cravado no painel, que é o que este módulo veio tirar."""


PAPEIS: tuple[str, ...] = (
    TEXTO_SECUNDARIO,
    PRONTO,
    PRONTO_TEXTO,
    A_FAZER,
    LIDO,
    DISPENSADO,
    ATENCAO,
    PROBLEMA,
    DIVERGENTE,
    PROBLEMA_TEXTO,
    DIVERGENTE_TEXTO,
    CORRIGIDO,
    VIZINHA_TEXTO,
    SUPERFICIE_PAGINA,
    SUPERFICIE_TABULEIRO,
    SUPERFICIE_DICA,
    MOLDURA,
    COORDENADA,
    CASA_CLARA,
    CASA_ESCURA,
    CASA_ULTIMO_LANCE,
    CONTORNO_DE_SELECAO,
    ALVO,
    SETA_VERDE,
    SETA_VERMELHA,
    SETA_AZUL,
    SETA_AMARELA,
    TEXTO_SOBRE_MARCACAO,
    TRACEJADO,
    AUTOR_DESTAQUE,
    AUTOR_CITACAO,
    AUTOR_NOTA,
    AUTOR_VARIANTE,
    REALCE_DESTAQUE,
    REALCE_CITACAO,
    REALCE_NOTA,
    REALCE_VARIANTE,
    TEXTO_PADRAO,
    SUPERFICIE_PADRAO,
)
"""Todos os papéis. A tupla existe para o teste poder afirmar que a resolução é **total**."""


RESERVA: dict[str, str] = {
    TEXTO_SECUNDARIO: "#555555",
    PRONTO: "#00c07a",
    PRONTO_TEXTO: "#146c43",
    A_FAZER: "#4da3ff",
    LIDO: "#ffb02e",
    DISPENSADO: "#9aa1ad",
    ATENCAO: "#8a5a00",
    PROBLEMA: "#c0392b",
    DIVERGENTE: "#8e44ad",
    PROBLEMA_TEXTO: "#c0392b",
    DIVERGENTE_TEXTO: "#8e44ad",
    CORRIGIDO: "#2b4008",
    VIZINHA_TEXTO: "#1565c0",
    SUPERFICIE_PAGINA: "#1c1c1c",
    SUPERFICIE_TABULEIRO: "#312e2b",
    SUPERFICIE_DICA: "#ffffe0",
    MOLDURA: "#1f1d1b",
    COORDENADA: "#5c5c5c",
    CASA_CLARA: "#f0d9b5",
    CASA_ESCURA: "#b58863",
    CASA_ULTIMO_LANCE: "#cdd26a",
    CONTORNO_DE_SELECAO: "#141414",
    ALVO: "#3f7f4c",
    SETA_VERDE: "#15781b",
    SETA_VERMELHA: "#882020",
    SETA_AZUL: "#003088",
    SETA_AMARELA: "#c07c00",
    TEXTO_SOBRE_MARCACAO: "#101010",
    TRACEJADO: "#ff5cc8",
    AUTOR_DESTAQUE: "#bb1ea1",
    AUTOR_CITACAO: "#14747d",
    AUTOR_NOTA: "#147925",
    AUTOR_VARIANTE: "#425ce0",
    REALCE_DESTAQUE: "#ffe8fb",
    REALCE_CITACAO: "#bdf9ff",
    REALCE_NOTA: "#b9ffc5",
    REALCE_VARIANTE: "#eaeeff",
    TEXTO_PADRAO: "#000000",
    SUPERFICIE_PADRAO: "#f0f0f0",
}
"""O valor de cada papel quando não há tema a consultar.

**Reserva e não padrão**: num `Tk` sem `ttkbootstrap` a janela abre com estas cores, e é o
mesmo contrato de degradação que `ui/theme.py` promete desde a S-53 — aparência não derruba
ferramenta.

Duas entradas mudaram de valor em relação ao que estava cravado, e as duas por medição (S-146):
`COORDENADA` era `#d8d8d8`, que sobre o antigo `#f2f2f2` do tabuleiro do Resultado dá **1,27:1**
— desenhado e ilegível; e `ATENCAO` ganhou um âmbar escuro porque o `#ffb02e` da marcação
reprova como texto.

**Esta tabela é a do tema claro.** As superfícies têm um segundo valor em `_NO_ESCURO`, e a
escolha entre os dois é de `tema_e_escuro` — ver `SUPERFICIES`.
"""


SUPERFICIES: tuple[str, ...] = (
    SUPERFICIE_PAGINA,
    SUPERFICIE_TABULEIRO,
    SUPERFICIE_DICA,
    MOLDURA,
    REALCE_DESTAQUE,
    REALCE_CITACAO,
    REALCE_NOTA,
    REALCE_VARIANTE,
)
"""Os papéis que são **fundo de canvas**, e por isso os únicos que seguem o tema (S-147).

O achado: `ttkbootstrap` traz 30 temas e metade deles é escura, mas quatro retângulos da janela
eram imunes a `CVOFF_TTK_THEME` porque estavam desenhados fora do `Style` — o canvas do PDF, os
dois tabuleiros e o tooltip. Quem exercesse a variável documentada em `ui/theme.py:33` ficava
com um amarelo-pálido de dica levando texto claro por cima, ilegível, e com a página do livro
numa moldura mais clara que a janela em volta.

**Só os fundos, e de propósito.** A identidade do tabuleiro (`CASA_CLARA`, `CASA_ESCURA`) não
entra: xadrez impresso é claro-e-escuro em qualquer tema, e um tabuleiro que troca de cor com a
janela deixa de ser reconhecível como tabuleiro. As marcações também não: elas são desenhadas
sobre a **página renderizada**, cujo fundo é o papel do livro e não o tema.
"""


_NO_ESCURO: dict[str, str] = {
    SUPERFICIE_PAGINA: "#0d0d0d",
    SUPERFICIE_TABULEIRO: "#171614",
    SUPERFICIE_DICA: "#33312a",
    MOLDURA: "#0a0908",
    REALCE_DESTAQUE: "#290022",
    REALCE_CITACAO: "#002529",
    REALCE_NOTA: "#002907",
    REALCE_VARIANTE: "#000729",
}
"""O valor de cada superfície quando o tema em uso é escuro.

Cada entrada é **mais escura** que a de `RESERVA` — é essa a propriedade que o teste afirma,
por luminância e não por olho. E é ela que faz o critério de aceite da S-147 ser verificável sem
abrir janela nos 30 temas.

O `#171614` do tabuleiro é o antigo `SUPERFICIE_ESTUDO` (`#262421`) mais escuro um degrau: a cor
do tabuleiro de Análise não foi jogada fora, virou o valor de tema escuro da superfície única.
"""


SUPERFICIES_DE_DOCUMENTO: tuple[str, ...] = (SUPERFICIE_PAGINA, SUPERFICIE_TABULEIRO, MOLDURA)
"""As superfícies em que o **documento** é desenhado: a folha do livro e o tabuleiro (S-224).

Elas seguem o tema, como desde a S-147 -- e **não seguem a pele**. É a fronteira inteira da
S-224: o produto é comparar diagrama impresso em papel branco com o que o modelo leu, e a paleta
que faz isso funcionar foi medida (S-146, S-158, S-159). Uma aparência nova pode escurecer o
cromo em volta; o que ela não pode é mudar o fundo contra o qual as doze marcações foram
medidas."""

NO_CROMO_ESCURO: dict[str, str] = {
    SUPERFICIE_DICA: "#33312a",
    SUPERFICIE_PADRAO: "#1f2124",
    TEXTO_PADRAO: "#e9eaec",
    TEXTO_SECUNDARIO: "#a7adb6",
    # Os cinco abaixo são a conta que registrar uma pele escura obriga a assinar. Sobre
    # `#1f2124` os valores da paleta clara dão 2,50, 2,97, 2,72, 2,75 e 2,81 -- todos abaixo do
    # piso AA de 4,5:1, porque foram escolhidos contra um fundo claro. Aqui eles sobem em
    # **luminosidade**, com matiz e saturação preservadas: `PROBLEMA` continua sendo o vermelho
    # de "pare", e `PRONTO_TEXTO` o verde de "já rendeu amostra". Um papel que trocasse de matiz
    # entre peles seria dois significados com um nome, que é o defeito da S-158.
    PRONTO_TEXTO: "#1ea466",
    PROBLEMA_TEXTO: "#dd7065",
    ATENCAO: "#c78200",
    DIVERGENTE_TEXTO: "#b37acb",
    VIZINHA_TEXTO: "#4492eb",
    # As oito da S-242, pela mesma conta e com a matiz preservada ao grau: as quatro de letra
    # sobem em luminosidade até cruzar 5,0:1 sobre `#1f2124`, e os quatro realces descem até que o
    # que cai por cima deles -- as duas tintas de faixa do cromo escuro e o texto claro -- passe
    # 4,7:1. Repetem `_NO_ESCURO` de propósito, como `SUPERFICIE_DICA`: escurecer por tema ou por
    # pele tem de dar no mesmo lugar.
    AUTOR_DESTAQUE: "#da61c6",
    AUTOR_CITACAO: "#289ea9",
    AUTOR_NOTA: "#27a53c",
    AUTOR_VARIANTE: "#798ae0",
    REALCE_DESTAQUE: "#290022",
    REALCE_CITACAO: "#002529",
    REALCE_NOTA: "#002907",
    REALCE_VARIANTE: "#000729",
}
"""O valor de cada papel de **cromo** quando a pele declara `cromo_escuro` (S-224).

Nove: os dois que a spec nomeia, os dois de texto que eles obrigam, e os cinco que a medição
cobrou. Um cromo escuro com `TEXTO_PADRAO` preto é texto invisível, e -- desde a S-220 --
**ícone** invisível, que é literalmente o defeito que o ícone-como-traço existe para não ter.

**A matiz é preservada em todos os cinco, e isso foi medido**: o desvio máximo é de 0,2°. O que
muda é a luminosidade, o mínimo para cruzar 5,0:1 -- com folga sobre o piso de 4,5, porque um
valor que passa por 0,04 é um valor que a próxima mexida derruba sem avisar.

`SUPERFICIE_DICA` repete o valor de `_NO_ESCURO` de propósito: a dica é cromo, e escurecer por
tema ou por pele tem de dar no mesmo lugar. Ter duas dicas escuras diferentes seria a mesma cor
com dois donos, que é o defeito que a S-145 mediu.

**A pele ganha do tema para estes quatro.** "Cromo segue a pele" é literal: quem escolher a
"Foco" e forçar um tema claro por `CVOFF_TTK_THEME` recebe o cromo da pele, porque foi a pele
que ele escolheu por último e é ela que a janela está desenhando."""


_DO_TEMA: dict[str, tuple[str, str]] = {
    PRONTO_TEXTO: ("success.TLabel", "foreground"),
    PROBLEMA: ("danger.TLabel", "foreground"),
    TEXTO_SECUNDARIO: ("secondary.TLabel", "foreground"),
}
"""Papéis que o tema **pode** responder melhor que a reserva, e onde perguntar.

**Só três, e de propósito.** O resto ou é identidade do tabuleiro (que não segue tema) ou é
marcação sobre a página renderizada, onde o fundo é a página e não o tema — perguntar ao
`Style` ali devolveria uma cor pensada para outro fundo.

**"Pode" e não "responde"**: nos 30 temas do `ttkbootstrap` 2.2.0 medidos aqui, nenhum dos três
estilos declara `foreground` próprio, e `style.lookup` devolve o do `TLabel` base para os três —
ver `_resposta_do_tema`, que é quem separa resposta de herança. A tabela fica porque um tema de
sistema, ou uma versão seguinte da biblioteca, pode declarar; o que ela não faz mais é aceitar a
herança como se fosse escolha.
"""


def _hex_do_tema(style: Estilo, layout: str, opcao: str) -> str | None:
    """O que o `Style` responde, se for um `#rrggbb`. `None` para tudo o mais.

    Um tema pode devolver string vazia, um nome do sistema (`SystemButtonFace`) ou levantar;
    nenhum dos três é cor, e nos três a reserva serve.
    """
    try:
        resposta = style.lookup(layout, opcao)
    except Exception:  # noqa: BLE001 - Style de tema exótico pode levantar; a reserva serve
        return None
    texto = str(resposta or "").strip().lower()
    return texto if texto.startswith("#") and len(texto) == 7 else None


def _resposta_do_tema(style: Estilo, layout: str, opcao: str) -> str | None:
    """O hex do papel **quando o tema dá um diferente do que dá ao estilo base** (S-163).

    **O defeito que isto conserta, medido nesta máquina.** `_DO_TEMA` promete que o tema responde
    melhor que a reserva para três papéis de texto. Sob `bootstrap-light`, o que ele responde é:

        TLabel            foreground=#212529
        success.TLabel    foreground=#212529
        danger.TLabel     foreground=#212529
        secondary.TLabel  foreground=#212529

    Os quatro iguais — inclusive depois de um widget pedir o estilo, que era a explicação mais
    plausível (o `ttkbootstrap` constrói estilo sob demanda) e não é a certa. `style.lookup` sobe
    a cadeia de herança do Tk até achar a opção, então um estilo derivado que **não** declara
    `foreground` devolve o do pai sem dizer que não tinha o seu. A consequência não era estética:
    "já salvo" (verde), "posição ilegal" (vermelho) e contagem de apoio (cinza) resolviam para o
    **mesmo** `#212529` na janela em execução, e as três cores que a S-146 mediu com número nunca
    chegavam à tela. Foi o rodapé da S-163 que expôs isto, ao pedir a primeira delas para colorir
    letra: o erro apareceu preto.

    A regra é a mais conservadora que resolve: resposta igual à do estilo base é **ausência** de
    resposta, e aí vale a reserva — que é medida. Continua valendo o caso legítimo do tema que de
    fato declara a cor daquele papel, e é ele que este `if` deixa passar.
    """
    resposta = _hex_do_tema(style, layout, opcao)
    if resposta is None:
        return None
    base = _hex_do_tema(style, layout.rsplit(".", 1)[-1], opcao)
    return None if resposta == base else resposta


LIMIAR_DE_TEMA_ESCURO = 0.18
"""Abaixo desta luminância de fundo, o tema é escuro.

Não é 0,5, porque luminância relativa é perceptual e comprime o claro. O número saiu de medir
os **30 temas** do `ttkbootstrap` 2.2.0 nesta máquina — 15 claros e 15 escuros, cada um pelo
fundo que dá a um `TFrame`:

| | tema | fundo | luminância |
|---|---|---|---|
| o mais **escuro** dos claros | `tokyo-night-light` | `#e1e2e7` | 0,762 |
| o mais **claro** dos escuros | `everforest-dark` | `#2d353b` | 0,034 |

Entre 0,034 e 0,762 não existe tema nenhum: os dois grupos não se aproximam, eles se ignoram.
0,18 fica no meio geométrico dessa vala, a 5× do teto escuro e a 4× do piso claro, e o teste
afirma a classificação dos 30 — não do limiar.
"""


def tema_e_escuro(style: Estilo | None = None) -> bool:
    """Se o tema em uso é escuro, lido do fundo que ele dá a um `TFrame` (S-147).

    **Por que perguntar ao `TFrame` e não ao nome do tema.** A lista de nomes escuros do
    `ttkbootstrap` muda entre versões, e `CVOFF_TTK_THEME` aceita qualquer nome que o Tk
    conheça — inclusive tema de sistema que a biblioteca nunca viu. O fundo do painel é o que
    de fato vai estar ao lado das quatro superfícies na tela, então é ele que decide.

    Sem `style`, ou com um que não responde, devolve `False`: a reserva é a paleta clara, e o
    contrato de degradação diz que sem tema a janela abre como abria.
    """
    if style is None:
        return False
    fundo = _hex_do_tema(style, "TFrame", "background")
    return fundo is not None and _luminancia(fundo) < LIMIAR_DE_TEMA_ESCURO


def cor(papel: str, style: Estilo | None = None, *, cromo_escuro: bool = False) -> str:
    """O hexadecimal de um papel. `style=None` devolve a reserva.

    Levanta `KeyError` para papel desconhecido, em vez de devolver um cinza: um papel escrito
    errado que resolvesse para *alguma* cor viraria um widget de cor plausível e sem
    significado, que é exatamente o estado de que este módulo veio tirar o projeto.

    Quatro caminhos, nesta ordem: o **cromo da pele** (`NO_CROMO_ESCURO`, S-224), o que o tema
    responde melhor (`_DO_TEMA`), a superfície de canvas sob tema escuro (`_NO_ESCURO`, S-147),
    e a reserva.

    **`cromo_escuro` faz duas coisas opostas, e é a fronteira da S-224.** Escurece o cromo, e
    **prende** as superfícies de documento na paleta medida: a folha e o tabuleiro não escurecem
    porque alguém trocou de aparência. Trocar de *tema* continua movendo as duas, como desde a
    S-147 -- tema é o eixo de cor, e essa escolha é de quem a faz.
    """
    if papel not in RESERVA:
        raise KeyError(f"papel de cor desconhecido: {papel!r}. Os válidos estão em PAPEIS.")
    if cromo_escuro and papel in NO_CROMO_ESCURO:
        return NO_CROMO_ESCURO[papel]
    if style is not None and papel in _DO_TEMA:
        do_tema = _resposta_do_tema(style, *_DO_TEMA[papel])
        if do_tema is not None:
            return do_tema
    if cromo_escuro and papel in SUPERFICIES_DE_DOCUMENTO:
        return RESERVA[papel]
    if papel in _NO_ESCURO and tema_e_escuro(style):
        return _NO_ESCURO[papel]
    return RESERVA[papel]


def paleta(style: Estilo | None = None, *, cromo_escuro: bool = False) -> dict[str, str]:
    """A paleta inteira resolvida. É o que o teste percorre para afirmar totalidade."""
    return {papel: cor(papel, style, cromo_escuro=cromo_escuro) for papel in PAPEIS}


# ------------------------------------------------------------------- contraste (S-146)


def _canal(valor: float) -> float:
    return valor / 12.92 if valor <= 0.03928 else ((valor + 0.055) / 1.055) ** 2.4


def _luminancia(hexadecimal: str) -> float:
    texto = hexadecimal.lstrip("#")
    if len(texto) != 6:
        raise ValueError(f"cor precisa ser #rrggbb; recebido {hexadecimal!r}")
    r, g, b = (int(texto[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.2126 * _canal(r) + 0.7152 * _canal(g) + 0.0722 * _canal(b)


def razao_de_contraste(a: str, b: str) -> float:
    """A razão WCAG 2.1 entre duas cores, entre 1,0 e 21,0. Simétrica.

    É o instrumento da S-146, e ele mora aqui porque a S-145 é quem declara os pares: um par
    que reprova é um defeito da paleta, não do painel que a usou.

    Âncoras conhecidas, que os testes afirmam: `#000000`/`#ffffff` = 21,0 e `#777777`/`#ffffff`
    = 4,48 — o cinza que fica logo abaixo do piso AA de 4,5.
    """
    la, lb = _luminancia(a), _luminancia(b)
    clara, escura = max(la, lb), min(la, lb)
    return (clara + 0.05) / (escura + 0.05)


AA_TEXTO = 4.5
"""Piso WCAG 2.1 AA para texto normal."""

AA_GRAFICO = 3.0
"""Piso para elemento gráfico -- borda, traço, ícone. É o que vale para as marcações."""


# ------------------------------------------------- um eixo, um significado (S-158)

PAGINA = "página"
TABULEIRO = "tabuleiro"
"""As duas superfícies em que a janela desenha marcação. Não são decoração: são o que decide
quais papéis podem ser confundidos. Duas marcações na **mesma** superfície competem pelo mesmo
olhar; em superfícies diferentes, a forma já as separa (a página usa retângulo com etiqueta
preenchida, o tabuleiro usa contorno de casa)."""

SIGNIFICADO: dict[str, tuple[str, str]] = {
    A_FAZER: (PAGINA, "o detector achou isto e ninguém leu ainda"),
    LIDO: (PAGINA, "o OCR leu e ainda não foi salvo"),
    PRONTO: (PAGINA, "já rendeu amostra no labels.csv"),
    DISPENSADO: (PAGINA, "a base reconheceu: não precisa de olho nenhum"),
    TRACEJADO: (PAGINA, "a área que você está selecionando agora"),
    CORRIGIDO: (TABULEIRO, "o decodificador reescreveu esta casa"),
    DIVERGENTE: (TABULEIRO, "as duas leituras discordam desta casa"),
    PROBLEMA: (TABULEIRO, "esta casa torna a posição ilegal"),
    ALVO: (TABULEIRO, "a peça arrastada pode ir para cá"),
    CONTORNO_DE_SELECAO: (TABULEIRO, "esta é a casa selecionada agora"),
}
"""**O eixo, declarado uma vez**: papel → (superfície, o que ele diz ao usuário) (S-158).

O achado que isto fecha: duas paletas, cada uma impecavelmente documentada no seu arquivo,
dizendo coisas diferentes com a mesma cor a 30 cm de distância na mesma janela. Violeta na
página queria dizer "pule"; violeta no tabuleiro queria dizer "pare". Nenhum dos dois arquivos
estava errado sozinho — e é por isso que nenhuma auditoria de arquivo achou isto.

A tabela existe para o teste poder **gerar** os pares que competem, em vez de alguém listá-los
à mão e esquecer o próximo. Quem acrescentar uma marcação declara aqui o que ela significa, e
descobre na hora se a matiz que escolheu já quer dizer outra coisa."""

SEPARACAO_MINIMA_DE_MATIZ = 40.0
"""Quantos graus de matiz dois papéis da mesma superfície precisam ter entre si.

Não é um número de gosto: abaixo de ~30° duas cores de luminância parecida deixam de ser
nomeáveis separadamente ("azul" e "azul"), e a faixa azul é a mais comprimida de todas — foi
exatamente onde o defeito estava, com `A_FAZER` e `CORRIGIDO` a **3,6°** um do outro. 40 dá
folga para a compressão perceptual sem exigir cores que não passem no contraste."""

SATURACAO_NEUTRA = 0.2
"""Abaixo desta saturação, o papel não tem matiz a disputar e fica isento da regra.

É o caso de `DISPENSADO`: "a base reconheceu, não precisa de você" é o único estado que deve
**recuar** em vez de competir, e um cinza-ardósia diz isso melhor que qualquer matiz. A isenção
não é uma brecha — é o reconhecimento de que a regra é sobre matiz, e cinza não tem uma."""


def _canais(hexadecimal: str) -> tuple[float, float, float]:
    texto = hexadecimal.lstrip("#")
    if len(texto) != 6:
        raise ValueError(f"cor precisa ser #rrggbb; recebido {hexadecimal!r}")
    return tuple(int(texto[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def matiz(hexadecimal: str) -> float:
    """A matiz da cor, em graus (0 a 360). Cinza devolve 0, e `saturacao` é quem diz que é cinza."""
    r, g, b = _canais(hexadecimal)
    maior, menor = max(r, g, b), min(r, g, b)
    faixa = maior - menor
    if faixa == 0:
        return 0.0
    if maior == r:
        return (60 * ((g - b) / faixa) + 360) % 360
    if maior == g:
        return 60 * ((b - r) / faixa) + 120
    return 60 * ((r - g) / faixa) + 240


def saturacao(hexadecimal: str) -> float:
    """A saturação HSL, de 0 (cinza) a 1. É o que decide se a matiz vale alguma coisa."""
    r, g, b = _canais(hexadecimal)
    maior, menor = max(r, g, b), min(r, g, b)
    if maior == menor:
        return 0.0
    luminosidade = (maior + menor) / 2
    return (maior - menor) / (2 - maior - menor if luminosidade > 0.5 else maior + menor)


def distancia_de_matiz(a: str, b: str) -> float:
    """A menor distância entre duas matizes, em graus (0 a 180). Circular: 350° e 10° distam 20.

    O instrumento da S-158, e ele mora aqui pelo mesmo motivo de `razao_de_contraste`: duas
    marcações que se confundem são defeito **da paleta**, não do painel que as usou.
    """
    diferenca = abs(matiz(a) - matiz(b)) % 360
    return min(diferenca, 360 - diferenca)


def sobre_superficie(superficie: str, *, claro: str = "#e8e8e8", escuro: str = "#5c5c5c") -> str:
    """A cor de texto legível **sobre a superfície em que ele vai ser desenhado** (S-146).

    O defeito que isto conserta: `COORDENADA` era uma constante `#d8d8d8`, escolhida para o
    tabuleiro escuro da Análise, e o Resultado desenhava sobre `#f2f2f2`. Razão **1,27:1** — as
    letras a–h estavam na tela e não podiam ser lidas. Num programa cujo trabalho é dizer "o
    bispo está em c4", a régua que nomeia c4 era invisível.

    A escolha é a que der mais contraste contra aquele fundo, e o teste afirma o número dos
    dois lados — é o mesmo mecanismo que a Galeria já usava para o `tk.Text` da legenda, e que
    aqui faltou.

    As coordenadas foram o primeiro cliente; o segundo é o **texto do tooltip** (S-147), que
    tinha o mesmo defeito com outro nome: fundo cravado em amarelo-pálido e cor de letra herdada
    do tema. Sob tema escuro, letra clara sobre `#ffffe0`.
    """
    return claro if razao_de_contraste(claro, superficie) >= razao_de_contraste(escuro, superficie) else escuro
