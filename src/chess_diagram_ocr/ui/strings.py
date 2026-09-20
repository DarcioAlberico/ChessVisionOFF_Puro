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

SEM_MOTOR_STATUS = (
    "Nenhum motor UCI foi encontrado nesta máquina, e os comandos de análise estão desligados."
)
"""O que a barra de status diz quando um comando de motor é alcançado sem motor (F9-C16).

**A frase de antes era uma receita que não funcionava**: *"Sem motor UCI instalado: ponha o
Stockfish em engines/ e reabra."* Instalar o Stockfish e reabrir **não mudava nada**, porque nada
em `src/` procurava o binário -- `engine.find_engine` não tinha um único chamador (F9-C15 §6.1).
A carta §3.3 cobra que a mensagem de erro diga o que fazer a seguir; esta dizia, e mandava fazer o
que não resolve, que é pior do que não dizer.

Hoje a janela procura (`qt/janela._motor_de_analise`) e, quando não acha, **desabilita os três
comandos** -- de modo que esta frase é a rede de segurança de um caminho que o menu já não oferece,
e não a explicação principal. Quem explica é `SEM_MOTOR_DICA`, na dica do item desabilitado."""

SEM_MOTOR_DICA = (
    "Precisa de um motor UCI, e nenhum foi encontrado nesta máquina.\n"
    "Ponha o binário do Stockfish na pasta engines/ do projeto, ou informe o caminho\n"
    "em «engine.path» no settings.json, e abra o programa de novo."
)
"""Por que aqueles três itens do menu estão cinza. **A dica é a única superfície que sobra.**

Uma `QAction` desabilitada não recebe clique e não mostra mensagem: a dica é o único lugar em que
o motivo cabe. Sem ela, um item cinza faz procurar o defeito na própria máquina.

**Os dois caminhos escritos aqui são os dois que `engine.find_engine` de fato percorre**, e essa é
a diferença para a frase de antes: `CANDIDATE_DIRS` começa por `engines/`, e
`settings.EngineSettings.path` é lido em `qt/janela._motor_de_analise`. A instrução é executável, e
foi executada -- ver o §1 do relatório do ciclo 16."""

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

ESCONDER_INCERTEZA = "Esconder incerteza"
"""A caixa da aba Resultado desde o passo 13 da OCR_UI: a tinta de hesitação está **ligada por
padrão**, e a caixa é o gesto de quem já conferiu a página e quer ver as peças limpas. Marcar
para esconder, e não marcar para mostrar, é o sentido do padrão: a caixa nasce desmarcada."""

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

PRIMEIRO = "|◀"
ANTERIOR = "◀"
PROXIMO = "▶"
ULTIMO = "▶|"
"""Os quatro glifos de navegação, e **os quatro saem do mesmo bloco Unicode** (F9).

`PRIMEIRO` e `ULTIMO` eram `⏮` e `⏭` (U+23EE/U+23ED, *Media Controls*). Segoe UI não tem os dois:
a captura `depois_escuro_1280x800_galeria.png` mostra os botões de extremidade da Galeria com uma
**caixa vazia** -- o glifo de reserva do Qt para "não existe nessa fonte" -- ao lado de dois
triângulos que desenham. Dois botões de uma fileira de quatro sem símbolo nenhum.

A troca não é por outro glifo exótico: `◀` e `▶` (U+25C0/U+25B6, *Geometric Shapes*) já estavam
desenhando, e a barra é um `|` de ASCII. "Ir para o primeiro" continua se lendo, e passa a se
ler em qualquer fonte -- que é o que um símbolo de interface tem de fazer.
"""
ESPACO_INQUEBRAVEL = "\u00a0"
"""U+00A0. Quem o desenha não quebra a linha nele -- é o que ata a última palavra à anterior."""


def sem_orfa(frase: str) -> str:
    """A frase com a **última** palavra atada à anterior por espaço inquebrável (F9-C9, §4.7).

    **Uma órfã é a última linha de um parágrafo com uma palavra só**, e o crítico do ciclo 9
    mediu a pior desta janela: `'inteira.'`, sozinha numa linha, **5,7 % de uma medida de
    627 px**, centrada -- e ela é a última linha da `MENSAGEM_VAZIA`, *a primeira frase que o
    produto mostra*. Um parágrafo que termina assim parece cortado; o olho lê a palavra solta
    como um erro antes de a ler como texto.

    **O conserto é de composição e não de redação**, e é por isso que ele mora aqui e não em cada
    frase: quem escreve a frase não sabe em que largura ela vai quebrar, e o mesmo texto é
    desenhado em três peles e em quatro larguras. O espaço inquebrável diz ao compositor *"estas
    duas palavras andam juntas"*, que é a regra tipográfica de sempre, e o `QTextLayout` a
    respeita sem que nenhum painel precise saber dela.

    **Só a última**, e não todas: atar mais do que o necessário empurra a quebra para trás e
    produz uma linha anterior frouxa -- troca uma falta por outra. Frase de uma palavra volta
    inalterada; não há a que atar.

    Pura, e por isso afirmável sem abrir janela -- que é a fronteira deste módulo.
    """
    partes = str(frase).rsplit(" ", 1)
    if len(partes) < 2 or not partes[0].strip():
        return str(frase)
    return f"{partes[0]}{ESPACO_INQUEBRAVEL}{partes[1]}"


GALERIA_VAZIA_TITULO = "Nenhum diagrama ainda"
GALERIA_VAZIA_FRASE = sem_orfa(
    "A Galeria mostra os diagramas que uma varredura já encontrou neste livro. "
    "Varra o livro para começar; a varredura pode ser interrompida e continua de onde parou."
)
REVISAO_VAZIA_TITULO = "Nenhum item na fila"
REVISAO_VAZIA_FRASE = sem_orfa(
    "A fila de revisão junta os diagramas em que a leitura ficou duvidosa. "
    "Varre um livro para enfileirar o que precisar de olho, ou abre uma fila já gravada."
)
GALERIA_LEGENDA_VAZIA = sem_orfa(
    "A legenda impressa do diagrama aparece aqui depois da varredura."
)
"""O que o poço da legenda da Galeria diz enquanto está vazio (F9-C5, §7.14).

**Era o único poço grande da janela que não dizia o que espera receber:** `782x170 px` cujo
interior mede `770x158 = 121,7 kpx a 0,00 % de tinta`, sem rótulo e sem `placeholderText`,
entre a fila de navegação e `Copiar legenda`. O `accessibleName` existia -- um leitor de tela
anunciava "Legenda impressa do diagrama" --, e quem **olha** não via nada.

A frase diz as duas coisas: **o que** cai ali (a legenda impressa) e **quando** (depois da
varredura), que é o que separa "vazio porque ainda não" de "vazio porque não tem"."""

PARTIDAS_VAZIAS_TITULO = "Nenhuma partida guardada"
PARTIDAS_VAZIAS_FRASE = sem_orfa(
    "A lista traz as partidas que a varredura guardou para este diagrama. "
    "Procure por nome para trazer candidatas da base sem varrer de novo."
)
FILTRO_SEM_RESULTADO_TITULO = "Nenhuma partida com esse filtro"
FILTRO_SEM_RESULTADO_FRASE = sem_orfa(
    "O filtro casa com jogador, evento e resultado. Apague o que está escrito para ver as "
    "guardadas de novo."
)
COLECAO_VAZIA_TITULO = "Nenhuma partida neste arquivo"
COLECAO_VAZIA_FRASE = sem_orfa(
    # **As duas crases eram desenhadas** (F9-C15 §5.5): `.pgn` chegava à tela com os acentos
    # graves, num retrato ampliado do próprio ciclo 14. É marcação de Markdown vazando para texto
    # de interface -- a mesma família das aspas retas que esta frente caçou no ciclo 12. Aspas
    # angulares são o que este arquivo já usa para citar («Bases…», logo abaixo).
    "O arquivo abriu, e não há partida legível dentro dele. Escolha outro arquivo .pgn, ou abra "
    "este num editor para ver o que ele traz."
)
BUSCA_SEM_AGULHA_TITULO = "Digite o que procurar"
BUSCA_SEM_AGULHA_FRASE = sem_orfa(
    "As ocorrências aparecem aqui enquanto você digita, com o trecho em volta de cada uma."
)
BUSCA_SEM_ACHADO_TITULO = "Nada achado"
BUSCA_SEM_ACHADO_FRASE = sem_orfa(
    "Nenhuma ocorrência na folha lida. Diferenciar maiúsculas e casar a figurina mudam o que "
    "conta como igual."
)
POSICAO_SEM_PARTIDA_TITULO = "Nenhuma partida chega aqui"
POSICAO_SEM_PARTIDA_FRASE = sem_orfa(
    "A base não tem partida que passe por esta posição. Feche e escolha outra posição no "
    "tabuleiro, ou troque a base em «Bases…»."
)
"""Os cinco estados vazios das telas de diálogo (F9-C14, item 4 do §7 do ciclo 13).

**A janela principal tinha o componente em quatro lugares e os treze diálogos em nenhum.** Medido
pelo crítico do ciclo 13: cinco diálogos abrem com uma vista vazia na tela e **0 de 5** usavam
`qt/vazio.EstadoVazio` -- `DialogoDePartidas` abria com uma grade de 878x300 px em branco e um
`0 partida(s)` num canto, e `_JanelaDeColecao` escrevia `"0 partida(s) em colecao.pgn. Escolha
uma:"` sobre uma lista vazia, uma frase que se contradiz na segunda oração.

Cada uma tem as mesmas três partes das da janela: **o título diz o que falta, a frase diz por que
está vazio e o que enche, e o botão faz** -- e onde não há botão que resolva (a busca sem agulha
digitada) as duas primeiras continuam obrigatórias. É o mesmo contrato de `GALERIA_VAZIA_TITULO`,
um andar abaixo."""

DATASET_LENDO_TITULO = "Lendo o dataset"
DATASET_LENDO_FRASE = sem_orfa(
    "As amostras estão sendo lidas do disco. A tabela aparece assim que a leitura terminar."
)
"""A espera da aba Dataset, dita **dentro da tabela** (F9-C2).

A leitura do `labels.csv` saiu da thread da janela no item 5 do §7 -- eram 1.302 ms de janela
morta no primeiro clique da aba --, e o preço da troca é um intervalo em que a tabela existe e
está vazia. Uma tabela de dataset em branco é uma afirmação sobre o arquivo; esta frase diz que a
afirmação ainda não foi feita."""

ASPA_ABRE = "“"
ASPA_FECHA = "”"
"""As aspas **tipográficas** que envolvem um nome de controle citado numa frase (F9-C7, §4.10).

Carta §3.3, bloco Tipografia. As três mensagens de estado vazio citam o rótulo de um botão, e o
`"` reto -- aspas de máquina de escrever -- estava em **12 das 36 capturas**.

**Declaradas, e não digitadas em cada frase**, por duas razões que já custaram caro nesta frente:
o par tem de ser o mesmo nas três mensagens, e quem procura *"que nomes esta frase cita"* precisa
de um par estável para procurar. `tests/test_qt_janela.EstadoVazioNaTelaTests` aceita os **dois**
pares -- reto e tipográfico --, para que trocar as aspas nunca possa *apagar* a cobrança em vez de
a manter: uma regex de aspa reta contra uma frase de aspa curva devolve zero citações e passa em
verde. `benchmarks/reports/ui/c8/c8_vazio_na_tela.py` faz o mesmo do lado do arnês, e é por isso
que ele existe ao lado do `c7_vazio_na_tela.py` do crítico, que só conhece a reta."""

TEXTO_VAZIO_TITULO = "Nenhuma folha lida"
TEXTO_VAZIO_FRASE = sem_orfa(
    f"Use {ASPA_ABRE}Ler folha{ASPA_FECHA} para transcrever a página aberta no visualizador, "
    f"ou {ASPA_ABRE}Achar no texto…{ASPA_FECHA} para procurar numa folha já lida."
)
"""Os três estados vazios de verdade, do item 14 do §7 (F9-C2).

**O crítico do ciclo 1 mediu a tinta:** Galeria 514,7 kpx a **0,24 %**, Texto a **0,57 %** e
Revisão 409,3 kpx a **0,00 %** -- e, na Galeria, duas frases dizendo a mesma coisa a 320 px uma da
outra, com o botão que resolve a 645 px do vazio que ele preenche.

Cada um tem **três** partes, e as três são obrigatórias: o título diz o que falta, a frase diz por
que a região está vazia e o que a enche, e o botão faz. A frase de Texto continua sendo
`EDITOR_VAZIO`, que já nomeava os dois caminhos de saída pelos rótulos que estão nos botões -- ela
só deixou de ser `placeholderText`, que não quebra linha e era cortada em 77 px em qualquer janela
abaixo de 1350 px."""

DISPENSAR = "×"
"""O glifo de "tirar isto de cena", no botão que dispensa o retângulo selecionado (F9-C2).

`U+00D7` (sinal de multiplicação) e **não** `U+2715` nem `U+2717`: é a mesma lição da S-506 --
os dois do bloco *Dingbats* faltam no Segoe UI e saem como caixa vazia, enquanto o de Latin-1
desenha em qualquer fonte que exista num Windows. O nome por extenso fica no `accessibleName` e
na dica; o glifo é só a forma."""

NENHUM_PDF_ABERTO = "nenhum livro aberto"
"""O que o rótulo do bloco [Livro] diz enquanto não há PDF. Era literal no painel (F9-C2).

"PDF" é o formato do arquivo; "livro" é o que a pessoa abriu. O resto da janela já diz livro --
`LIVRO_EM_PDF`, `VARRER_LIVRO`, o rodapé --, e esta era a última frase que dizia a sigla."""

EDITOR_VAZIO = (
    f"Nenhuma folha lida. Use {ASPA_ABRE}Ler folha{ASPA_FECHA} para transcrever a página aberta "
    f"no visualizador, ou {ASPA_ABRE}Achar no texto…{ASPA_FECHA} para procurar numa folha já lida."
)
"""O que o editor de texto diz quando não há folha nenhuma nele (F9).

**Estado vazio sem orientação reprova sozinho** (carta dos críticos, §3.3), e a aba Texto era
exatamente isso: um retângulo branco de 940x880 px sem uma palavra -- a captura
`depois_claro_1920x1080_texto.png` é meio ecrã de nada. A frase nomeia os **dois** caminhos de
saída, e nomeia-os pelo rótulo que está no botão logo acima: quem lê a frase não precisa procurar
o que ela quer dizer.
"""

DIAGRAMAS_DA_PAGINA = "Diagramas reconhecidos nesta página"
"""O nome acessível da lista do topo da aba Resultado (F9-C2, defeito nº 1).

Ela se anunciava como `"Lista"` -- o último degrau da cascata de `ui/nomes_acessiveis.py`, que é
genérico de propósito. Um leitor de tela lê o nome e **em seguida** o papel: "Lista, lista". O
portão do ciclo 2 (`teclado.nome_vazio_de_sentido`, motivo *eco do papel*) reprova exatamente
isso, e o conserto é dizer o que a lista guarda."""

DETALHES_DO_DIAGRAMA = "Detalhes do diagrama"
"""O nome acessível do painel de texto selecionável da aba Resultado (F9).

Ele recebe foco porque o texto dele é **selecionável** -- é de onde a pessoa copia a explicação
de por que a posição é ilegal --, e um controle que recebe foco e não tem nome é anunciado como
"texto estático" e mais nada. A derivação automática de `qt/acessibilidade.py` não o alcança de
propósito: nomear todo `QLabel` por classe encheria a janela de "texto" repetido."""

CONJUNTO_DE_PECAS = "Conjunto de peças"
"""O rótulo da escolha da S-230, na Configuração.

Ao lado dos outros rótulos de campo e não no menu de aparência: conjunto é eixo próprio, e a
pergunta que ele responde -- com que desenho as peças aparecem -- não é a pergunta da pele."""

PASTA_DE_PECAS = "Pasta de peças"

ORIENTACAO_DO_DIAGRAMA = "Orientação do diagrama"
"""O rótulo da linha de orientação, na aba Configuração.

Ele vira constante na S-448 porque passou a ser lido **duas** vezes: uma para desenhar a linha e
outra em `ROTULOS_DA_CONFIGURACAO`, de onde sai a largura da coluna. Dois literais iguais em dois
lugares é o defeito que a S-166 fechou no resto da janela."""

ROTULOS_DA_CONFIGURACAO: tuple[str, ...] = (
    "Modelo (.pt)",
    "CSV labels",
    "Pasta samples",
    PASTA_DE_PECAS,
    ORIENTACAO_DO_DIAGRAMA,
    "DPI",
    "Max diagramas",
    "Épocas",
    TAMANHO_DO_LOTE,
    TAXA_DE_APRENDIZADO,
)
"""Os dez rótulos do formulário de Configuração, num lugar só (S-448).

A coluna de rótulo sai do mais longo deles -- hoje `ORIENTACAO_DO_DIAGRAMA`, com 22 caracteres --,
e é isso que faz "nenhum rótulo é cortado" e "todos os campos começam na mesma coluna" valerem por
construção, e não por conferência.

**Antes eram três medidas diferentes do mesmo formulário**: `16` cravado em `campos._linha`, `24`
no rótulo da orientação, e o que o `ttk.Spinbox` do `_spin_row` resolvesse por conta própria. Com
`16`, "Taxa de aprendizado" -- 19 caracteres -- era desenhado como `Taxa de aprendizad`.

Moram aqui e não no `app_tkinter` porque são texto que a pessoa lê, que é o que este módulo guarda
desde a S-166 -- e porque um rótulo novo que entrasse no formulário sem passar por aqui voltaria a
ser cortado sem ninguém notar."""
"""O caminho dos 12 PNGs do usuário. Só vale com o conjunto "Pasta do usuário" escolhido."""

ALINHAR = "Alinhar"
CAIXA = "Caixa"
"""Os dois agrupadores da barra da aba de texto (S-259/S-262). **Não são comandos.**

A regra 4 da SPEC_EDITOR manda todo comando do editor para `ui/comandos.py`, e estes dois não são
comandos: são o rótulo do botão que **abre a lista** de quatro alinhamentos e de três caixas. Quem
faz alguma coisa é o item da lista, e cada um deles é um comando do catálogo, com item de menu
próprio.

A diferença tem consequência medida: um comando no catálogo precisa de casa numa das três peles ou
de item de menu -- é o que `test_ui_comandos.test_todo_comando_do_catalogo_alcanca_alguem` cobra
desde o corte do Tk, no lugar do `ui/alcance.py` --, e um agrupador que fosse comando obrigaria o
menu a ter uma linha "Alinhamento…" ao lado dos quatro itens que ela abriria -- a redundância que
o menu existe para não ter. É a mesma decisão que `LADO_A_JOGAR` e `CONJUNTO` já são: rótulo de
grupo, e não de ação."""

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


LIMITE_DA_LEGENDA = 120
"""Quantos caracteres da legenda o parágrafo de detalhes do Resultado mostra (OCR_UI passo 13).

**Medido: uma legenda inteira forçava a janela a 1.323 px de altura.** A legenda de um diagrama
do Kemeri (p. 80) traz o parágrafo de análise inteiro -- dezenove linhas --, e o rótulo de
detalhes, que quebra linha, pedia a altura de todas elas como **mínimo**: a janela deixava de caber
em 768 (a régua da F9-C2) na primeira página lida com legenda longa. Uma linha basta para dizer
de que diagrama se trata; o texto inteiro está no modo Texto, que é o lugar dele."""


def resumo_da_legenda(legenda: str, limite: int = LIMITE_DA_LEGENDA) -> str:
    """A legenda numa linha só, cortada no fim com reticências. Vazio continua vazio."""
    plana = " ".join(str(legenda).split())
    if len(plana) <= limite:
        return plana
    return plana[: max(0, limite - 1)].rstrip() + "…"


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


# ------------------------------------------- os estados com ação do diagrama (OCR_UI C2, C1/X5)

REPARADAS_MOSTRAR = "Mostrar as casas reparadas"
REPARADAS_ESCONDER = "Esconder as casas reparadas"
"""O botão do estado «reparado em N casas»: pinta no tabuleiro as casas em que o decodificador
trocou a classe mais provável pela que fecha a posição (`changed_squares`), e desfaz a pintura."""

ORIENTACAO_COMPARAR = "Ver girada 180°"
ORIENTACAO_VOLTAR = "Voltar à leitura original"
"""O botão do estado «orientação ambígua»: a outra leitura possível é a mesma posição girada de
180°; o clique a põe no tabuleiro como edição (desfazível), e o segundo clique a tira."""


def reparadas_em_casas(casas: Sequence[str]) -> str:
    """«Reparado em N casas: a1, b2» -- o estado que a tela não dizia (análise §7.5)."""
    quantas = len(casas)
    if quantas == 0:
        return ""
    plural = "" if quantas == 1 else "s"
    return f"Reparado em {quantas} casa{plural}: {', '.join(casas)}"


def orientacao_ambigua(motivo: str) -> str:
    """«Orientação ambígua: <motivo>», com o motivo que o serviço calculou."""
    razao = str(motivo).strip()
    return f"Orientação ambígua: {razao}" if razao else "Orientação ambígua"


def trocar_o_lado_para(lado: str) -> str:
    """O botão do rótulo de conflito: «Trocar para pretas» / «Trocar para brancas»."""
    return f"Trocar para {SIDE_LABELS.get(lado, lado).casefold()}"


# --------------------------------------- o que se perde ao fechar ou trocar de livro (OCR_UI C2, A7)

DESCARTAR_EDICOES_TITULO = "Descartar as correções"
"""O título da pergunta: nomeia a operação, como toda caixa (S-401)."""


def frase_de_edicoes_nao_gravadas(paginas: Sequence[int], *, livro: str = "", ao_fechar: bool = True) -> str:
    """A pergunta antes de perder correções feitas à mão e ainda não gravadas (análise §6.5).

    As páginas vêm em base 0 e saem em base 1, como a tela as numera. `ao_fechar` escolhe o
    fim da frase: fechar a janela perde tudo; abrir outro livro guarda as correções até o livro
    ser reaberto -- e a resposta "não" tem consequência diferente nos dois casos.
    """
    numeros = ", ".join(str(int(p) + 1) for p in paginas)
    plural = "" if len(paginas) == 1 else "s"
    onde = f" de {livro}" if livro else ""
    cabeca = f"A{plural} página{plural} {numeros}{onde} tem correções feitas à mão que não foram gravadas."
    if ao_fechar:
        return f"{cabeca}\n\nFechar agora perde essas correções. Fechar mesmo assim?"
    return (
        f"{cabeca}\n\nDescartar as correções? Responder {ASPA_ABRE}Não{ASPA_FECHA} as guarda até você "
        "reabrir esse livro."
    )


# ---------------------------------------------------- a caixa de falha e o rodapé (OCR_UI C2, A10)

COPIAR = "Copiar"
"""O botão da caixa de falha: título, mensagem e o rastro completo vão para a área de transferência,
para a pessoa colar num relato sem transcrever nada."""

MENSAGENS_ANTERIORES = "Mensagens"
"""O botão do rodapé que abre as últimas mensagens -- inclusive as que já expiraram."""

MENSAGENS_ANTERIORES_TITULO = "Mensagens desta sessão"
MENSAGENS_ANTERIORES_VAZIO = "Nenhuma mensagem ainda."


def titulo_de_falha(nome: str) -> str:
    """«A leitura não terminou», «A detecção não terminou»: a operação no título (S-401)."""
    operacao = str(nome).strip() or "operação"
    return f"A {operacao} não terminou"


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


TRADUZIDOS_PELO_QT: dict[str, str] = {
    "Abort": "Cancelar",
    "Apply": "Aplicar",
    "Cancel": "Cancelar",
    "Close": "Fechar",
    "Discard": "Descartar",
    "Help": "Ajuda",
    "Ignore": "Ignorar",
    "No": "Não",
    "NoToAll": "Não para tudo",
    "Ok": "OK",
    "Open": "Abrir",
    "Reset": "Restaurar",
    "RestoreDefaults": "Restaurar padrões",
    "Retry": "Repetir",
    "Save": "Salvar",
    "SaveAll": "Salvar tudo",
    "Yes": "Sim",
    "YesToAll": "Sim para tudo",
}
"""O que o **catálogo do próprio Qt** escreve em cada botão padrão em pt-BR. Medido, não suposto.

Lido de `PyQt6/Qt6/translations/qtbase_pt_BR.qm`, que esta árvore já traz, por
`benchmarks/reports/ui/c14/c14_catalogo_do_qt.py`: **18 de 18** dos `StandardButton` têm palavra
lá. Está escrito aqui, e não perguntado ao Qt em tempo de execução, porque o venv que guarda esta
decisão **não tem binding de Qt nenhum** -- é a mesma fronteira de `ui/folha_de_estilo.py`, e é o
que permite o teste afirmar a regra sem tela. O instrumento remede o `.qm` e diz se alguma palavra
mudou de versão, então a cópia envelhece **em voz alta**."""

DIVERGENCIAS_DECLARADAS: dict[str, str] = {
    "Abort": (
        "o catálogo do Qt escreve `Cancelar`, que é a MESMA palavra que ele dá ao `Cancel` -- e "
        "a única caixa de três botões do produto (`qt/exportador.py:104`) desenha os dois lado a "
        "lado. Duas legendas iguais na mesma caixa é pior do que uma palavra fora do catálogo."
    ),
}
"""Onde o produto escreve **outra** palavra que a do catálogo do Qt, e por quê. Uma entrada, hoje.

**A regra é: onde o Qt tem palavra, a palavra é do Qt.** Ela nasceu de uma regressão minha que o
crítico do ciclo 13 mediu: o `Ok` saía desenhado **`Confirmar`** em **32** caixas de aviso de um
botão só, inclusive a de *Sobre o produto* e vinte e tantas de erro. O argumento escrito era a
régua `LETRAS_MINIMAS` do portão de nome acessível -- que nasceu para reprovar `-`, `+` e `◀`,
**glifos que não anunciam nada**. `OK` não é glifo: é a palavra que o Windows em pt-BR usa, que o
catálogo do próprio Qt usa e que todo leitor de tela pronuncia. Uma régua de nome foi aplicada a
texto desenhado e escreveu a palavra errada em 32 telas.

Uma divergência só se sustenta com um motivo escrito aqui, e o teste cobra isso."""

BOTOES_PADRAO: dict[str, str] = {
    "Ok": "OK",
    "Cancel": "Cancelar",
    "Close": "Fechar",
    "Open": "Abrir",
    "Save": "Salvar",
    "SaveAll": "Salvar tudo",
    "Yes": "Sim",
    "YesToAll": "Sim para tudo",
    "No": "Não",
    "NoToAll": "Não para tudo",
    "Apply": "Aplicar",
    "Reset": "Restaurar",
    "RestoreDefaults": "Restaurar padrões",
    "Discard": "Descartar",
    "Retry": "Repetir",
    "Ignore": "Ignorar",
    "Abort": "Interromper",
    "Help": "Ajuda",
}
"""`QDialogButtonBox.StandardButton` -> o que ele diz **em português** (F9-C12).

**O olho achou o que a régua não procurava.** O portão de teclado do ciclo 12 passou a abrir os
doze diálogos do produto e todos passaram -- `0 sem nome, 0 sem papel, 0 nome vazio`. Fotografados
os treze, a primeira imagem mostrou um botão escrito **`Close`**: os botões padrão de um
`QDialogButtonBox` vêm traduzidos pelo Qt, e sem catálogo de tradução instalado o Qt fala inglês.
Medido nos treze diálogos: **7 de 12** botões padrão desenhados em inglês -- `Close` ×3, `Cancel`
×2, `Open` ×1 -- num produto inteiramente em pt-BR. Nenhuma régua desta frente olhava para
idioma, porque `Close` tem cinco letras, não é eco do papel e não é o valor do controle.

**A chave é o nome do enum e não o texto inglês**, de propósito: uma tabela `"Close" -> "Fechar"`
seria uma lista de palavras que envelhece com a versão do Qt e com o idioma da máquina. O enum é
estável, e é o que `qt/acessibilidade` consulta ao preparar cada diálogo. É isso que faz o produto
falar pt-BR numa máquina cujo Qt fala alemão -- medido: com o catálogo `de` instalado o Qt desenha
`['OK','Schließen','Abbrechen','Ja','Nein']` e o filtro devolve `['OK','Fechar','Cancelar','Sim','Não']`.

**As palavras são as do Qt** (`TRADUZIDOS_PELO_QT`), e a exceção se declara em
`DIVERGENCIAS_DECLARADAS`. A tabela existe para o caso em que o Qt **não** traduz -- nenhum, neste
`.qm`, e todos, numa máquina sem catálogo. Ela não existe para reescrever o vocabulário de quem já
tem um: foi assim que `Ok` virou `Confirmar` em 32 telas no ciclo 12."""
