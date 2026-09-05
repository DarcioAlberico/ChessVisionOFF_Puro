"""O catálogo de comandos da janela, declarado como dado (S-324).

**Três lugares declaravam comando, e nenhum deles era a lista.** `ui/menu.py` sabia o rótulo e a
posição na barra de menus; `ui/atalhos.py`, a tecla e como ela se escreve; `ui/pdf_panel.py`
montava o botão à mão, com o rótulo em literal. O nome do comando -- `"ler_pagina"`, `"salvar"` --
já ligava os três desde a S-161. O que não existia era o **registro**: nada dizia que `ler_pagina`
tem rótulo "Ler esta página", pertence ao grupo OCR e é uma das ações em destaque.

**A consequência, medida.** O rótulo do botão está em `pdf_panel.py:312` e o do menu em
`menu.py:110`, e eles **não são o mesmo texto**: "OCR todos diagramas" contra "Ler esta página".
Não é duplicação -- é divergência já consumada, e nada no programa a comparava. Com uma pele isso
é dívida tolerável. Com três (S-221), cada pele teria a sua ideia de o que existe, que é a S-161
de novo em outra forma: *"o que não era botão não existia"*.

**Este módulo não substitui `menu.MENUS`, e essa fronteira é o item.** O menu decide *onde na
barra de menus*; o catálogo decide *o que o comando é*. `MENUS` passa a referenciar o catálogo em
vez de repetir o rótulo, e `menu.montar` recusa item cujo `acao` não esteja aqui -- a disciplina
de `menu.comandos_faltando`, agora nos dois sentidos.

**Nenhum rótulo muda.** É o achado 1 do ROADMAP_APARENCIA: as propostas são visuais, não são
propostas de texto. Por isso `rotulo` (o do menu, longo) e `rotulo_curto` (o do botão de hoje)
convivem numa linha só, em vez de um deles apagar o outro. O ganho não é ter um texto: é os dois
passarem a ser **comparáveis**, que é exatamente o que faltava.

Nada de `tkinter` aqui, como em `ui/tokens.py` e `ui/atalhos.py`: quem monta widget não decide, e
quem decide é afirmável sem abrir janela.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from . import estilos, strings

__all__ = [
    "CATALOGO",
    "Comando",
    "ESTUDO",
    "GRUPOS",
    "NAS_BARRAS_DO_PDF",
    "NA_JANELA_DE_BUSCA",
    "NA_LINHA_DE_CAMPO",
    "acoes_fora_do_catalogo",
    "comando",
    "do_grupo",
    "estilo",
    "fila_de_destaque",
    "papel",
    "por_acao",
    "primarios_por_grupo",
    "rotulo",
    "rotulo_alternado",
    "rotulo_de_botao",
    "rotulo_do_grupo",
]

ARQUIVO = "ARQUIVO"
EDICAO = "EDICAO"
VISUALIZACAO = "VISUALIZACAO"
OCR = "OCR"
ACERVO = "ACERVO"
ESTUDO = "ESTUDO"
AJUDA = "AJUDA"

GRUPOS: tuple[str, ...] = (ARQUIVO, EDICAO, VISUALIZACAO, OCR, ACERVO, ESTUDO, AJUDA)
"""Os sete, e o conjunto é fechado.

Não são invenção: são os cinco menus de `menu.MENUS` com **Ferramentas partido em dois**, que é a
divisão que a Imagem 2 desenha e que o menu já insinuava com o separador de `menu.py:113`.

O corte entre `OCR` e `ACERVO` é uma pergunta, e não um gosto: **`OCR` age sobre a página aberta;
`ACERVO` age sobre o livro inteiro ou sobre o modelo que o lê.** Por isso "Ler esta página" é OCR
e "Varrer o livro" é ACERVO, e por isso treinar e recarregar o modelo caem em ACERVO junto da
anotação de conjunto de campo -- as três são sobre a máquina de ler, não sobre a folha na tela.

**Eram seis, e o sétimo é `ESTUDO`** (S-280). A pergunta dele é a terceira que faltava: `OCR` age
sobre a página aberta, `ACERVO` sobre o livro ou sobre o modelo, e `ESTUDO` sobre a **análise da
posição** -- a árvore de variantes, a anotação do lance e o motor. Ele entra depois de `ACERVO` e
antes de `AJUDA` porque a ordem desta tupla é a da barra de menus, e a Ajuda fecha a barra.

O conjunto continua fechado, e um oitavo grupo continua levantando: o critério para abrir um é o
que abriu este -- **haver uma pergunta que nenhum dos outros responde**, e não haver comandos
demais num deles.
"""

_ROTULOS_DE_GRUPO: dict[str, str] = {
    ARQUIVO: "Arquivo",
    EDICAO: "Edição",
    VISUALIZACAO: "Visualização",
    OCR: "OCR",
    ACERVO: "Acervo",
    ESTUDO: "Estudo",
    AJUDA: "Ajuda",
}
"""Como o grupo se escreve quando ele vira cabeçalho (a fita da S-227).

Um grupo sem rótulo legível é um grupo que não se desenha, e a constante `"VISUALIZACAO"` não é
texto de interface. Quatro destes são os cabeçalhos da Imagem 2, na grafia de `ui/strings.py`.
"""


@dataclass(frozen=True)
class Comando:
    """Um comando da janela, e tudo o que se sabe dele fora de um widget."""

    acao: str
    """O nome que ata tudo: `"ler_pagina"`. É o mesmo de `menu.py` e `atalhos.py`, e é a chave."""

    rotulo: str
    """Como o comando se chama, por extenso -- o texto do menu, que agora tem um dono só."""

    grupo: str
    """Um dos sete de `GRUPOS`. Fora deles levanta, e é por isso que o conjunto é fechado."""

    papel: str
    """`estilos.PRIMARIO`, `DESTRUTIVO` ou `NEUTRO`. Papel desconhecido levanta `KeyError`."""

    icone: str = ""
    """Nome no catálogo de ícones da S-220. Vazio é a resposta correta hoje: o repositório não
    tem um único ícone (achado 6 do roadmap), e declarar nome de ícone que ninguém desenha seria
    a promessa que a S-161 registra como o defeito de item de menu sem comando."""

    destaque: bool = False
    """Entra na fila curta da pele "Foco" (S-223). Ver `fila_de_destaque` antes de ligar um novo."""

    rotulo_alternado: str = ""
    """O texto do botão **enquanto o comando está ligado**, para os que alternam. Vazio = não alterna.

    Existe porque a S-222 encontrou o buraco: o `selecionar_area` troca o próprio rótulo para
    "Cancelar seleção" por `configure(text=...)`, e a varredura da S-324 só olhava o `text=` do
    **construtor**. Eram dois literais escritos à mão que o teste dava por limpos -- e, na
    remontagem de cromo, dois rótulos que voltariam errados com a seleção ainda ligada."""

    rotulo_curto: str = ""
    """O texto que o **botão** mostra, quando ele difere do rótulo do menu. Vazio = são o mesmo.

    Existe porque nenhum item desta fase troca rótulo de comando nenhum (achado 1 do roadmap), e
    porque os dois textos já divergiam: encurtá-los para um só mudaria a janela de hoje, e apagar
    a diferença esconderia a dívida em vez de registrá-la. Aqui os dois ficam lado a lado, numa
    linha, onde um teste finalmente os compara."""

    def __post_init__(self) -> None:
        # `estilo_de_botao` é quem sabe quais papéis existem, e ele já levanta `KeyError` com a
        # mensagem certa. Repetir a lista aqui seria a segunda declaração que este módulo veio
        # tirar do programa.
        estilos.estilo_de_botao(self.papel)
        if self.grupo not in GRUPOS:
            raise KeyError(f"grupo desconhecido: {self.grupo!r}. Os válidos estão em GRUPOS.")

    @property
    def alternado(self) -> str:
        """O texto de ligado, com o de desligado como resposta para quem não alterna."""
        return self.rotulo_alternado or self.no_botao

    @property
    def no_botao(self) -> str:
        """O texto do botão: o curto quando ele existe, o do menu quando não."""
        return self.rotulo_curto or self.rotulo


CATALOGO: tuple[Comando, ...] = (
    # ---------------------------------------------------------------------------- ARQUIVO
    Comando("abrir_pdf", "Abrir PDF…", ARQUIVO, estilos.NEUTRO, icone="abrir_pdf", rotulo_curto="Abrir PDF"),
    Comando("abrir_recente", "Abrir recente", ARQUIVO, estilos.NEUTRO),
    Comando("abrir_no_leitor", "Abrir no leitor do sistema", ARQUIVO, estilos.NEUTRO),
    Comando(
        "exportar_pgn",
        "Exportar o livro para PGN…",
        ARQUIVO,
        estilos.NEUTRO,
        icone="exportar_pgn",
        rotulo_curto=f"Exportar PDF {strings.SETA} PGN",
    ),
    # Sem item de menu hoje, e por isso ele **precisa** estar aqui: é o comando que só existe
    # como botão, e a S-233 mede exatamente esse caso quando for esconder controle.
    Comando(
        "cancelar_exportacao",
        "Cancelar a exportação",
        ARQUIVO,
        estilos.NEUTRO,
        rotulo_curto="Cancelar exportação",
    ),
    # Os do **editor de texto** que são sobre arquivo (S-240). O grupo é ARQUIVO e não EDICAO --
    # que é o que a spec da S-240 escreveu -- pela pergunta que separa os seis: Arquivo é *que
    # documento*, e `exportar_pgn` já mora aqui. Pôr `exportar_rtf` em EDICAO seria a divergência
    # que o catálogo existe para impedir, com dois exportadores em dois grupos. O que a spec
    # pedia junto disso -- que EDICAO continue com um PRIMARIO só -- vale igual, e vale nos dois.
    Comando("abrir_texto", "Abrir texto de folha…", ARQUIVO, estilos.NEUTRO, rotulo_curto="Abrir…"),
    Comando("salvar_texto", "Salvar o texto da folha", ARQUIVO, estilos.NEUTRO, rotulo_curto="Salvar"),
    Comando("salvar_texto_como", "Salvar o texto da folha como…", ARQUIVO, estilos.NEUTRO),
    Comando("exportar_txt", "Exportar o texto para .txt", ARQUIVO, estilos.NEUTRO, rotulo_curto="Salvar .txt"),
    Comando("exportar_md", "Exportar o texto para Markdown…", ARQUIVO, estilos.NEUTRO),
    Comando("exportar_html", "Exportar o texto para HTML…", ARQUIVO, estilos.NEUTRO),
    Comando("exportar_rtf", "Exportar o texto para RTF…", ARQUIVO, estilos.NEUTRO),
    Comando(
        "exportar_pdf_pesquisavel",
        "Exportar a folha como PDF pesquisável…",
        ARQUIVO,
        estilos.NEUTRO,
    ),
    Comando("sair", "Sair", ARQUIVO, estilos.NEUTRO),
    # ----------------------------------------------------------------------------- EDICAO
    Comando("aplicar_fen", "Aplicar a FEN digitada", EDICAO, estilos.NEUTRO, icone="aplicar_fen", destaque=True),
    Comando("apagar_casa", "Apagar a peça da casa selecionada", EDICAO, estilos.NEUTRO, icone="apagar_casa"),
    # O primário do grupo, e o critério de `estilos.PRIMARIO` o confirma: `Ctrl+S` salva.
    # **Em destaque no lugar do exportar** (S-223): a Imagem 1 desenhou "exportar" na fila e
    # omitiu "salvar", e a medida do fluxo diz o contrário -- exporta-se uma vez por livro e
    # salva-se uma vez por diagrama. Uma fila dimensionada por importância em vez de frequência
    # é a barra de 21 botões outra vez.
    Comando("salvar", "Salvar a posição", EDICAO, estilos.PRIMARIO, icone="salvar", destaque=True),
    Comando("salvar_todos", "Salvar todas as posições da página", EDICAO, estilos.NEUTRO),
    Comando("diagrama_anterior", "Diagrama anterior", EDICAO, estilos.NEUTRO, icone="diagrama_anterior"),
    Comando("proximo_diagrama", "Próximo diagrama", EDICAO, estilos.NEUTRO, icone="proximo_diagrama", destaque=True),
    Comando("proximo_da_fila", "Próximo item da fila de revisão", EDICAO, estilos.NEUTRO),
    # Os três da Imagem 2 que **não existiam** (S-229). O roadmap os registrou como achado 4:
    # `grep -rn 'undo' src/` devolvia zero linhas de implementação. Ficam no fim do grupo porque
    # é onde a ordem de declaração já os punha -- a fita e o menu leem daqui, e reordenar seria
    # declarar duas vezes em que ordem os comandos vivem.
    Comando("desfazer", "Desfazer a última mudança no tabuleiro", EDICAO, estilos.NEUTRO, icone="desfazer", rotulo_curto="Desfazer"),
    Comando("refazer", "Refazer o que foi desfeito", EDICAO, estilos.NEUTRO, icone="refazer", rotulo_curto="Refazer"),
    # **"Limpar" é o tabuleiro, e não o editor.** A spec da S-229 aponta para o `clear` de
    # `DiagramEditorModel`, que esvazia o editor inteiro -- listas, vínculo e índice --, e esse não
    # é um estado que uma pilha de posições saiba devolver. O critério de aceite do próprio item
    # decide a leitura: ele lista "limpar" entre as **sete origens de mudança de posição** que o
    # desfazer tem de reverter. Então limpar é esvaziar as 64 casas, e é desfazível.
    Comando("limpar_tabuleiro", "Limpar o tabuleiro", EDICAO, estilos.NEUTRO, icone="limpar_tabuleiro", rotulo_curto="Limpar"),
    # ------------------------------------------------- o editor de texto (S-240 a S-249)
    #
    # **Nenhum deles pede ênfase, e nenhum tem ícone.** A ênfase: EDICAO já tem o seu primário --
    # `salvar`, a posição do tabuleiro --, e duas ênfases na mesma barra é o mesmo que nenhuma
    # (`ui/estilos.py`). O ícone: `icone=""` é declaração e não esquecimento -- a fita da S-227
    # desenha o cromo da **janela**, e estes moram na barra da própria aba e no menu Texto. Um
    # ícone aqui os poria na fita ao lado de "Abrir PDF", que não é onde eles agem.
    Comando("negrito", "Negrito", EDICAO, estilos.NEUTRO),
    Comando("italico", "Itálico", EDICAO, estilos.NEUTRO),
    Comando("sublinhado", "Sublinhado", EDICAO, estilos.NEUTRO),
    Comando("tachado", "Tachado", EDICAO, estilos.NEUTRO),
    Comando(
        "limpar_formato",
        "Limpar a formatação do trecho",
        EDICAO,
        estilos.NEUTRO,
        rotulo_curto="Limpar formato",
    ),
    Comando("cor_do_texto", "Cor do texto…", EDICAO, estilos.NEUTRO),
    Comando("realce", "Realce do trecho…", EDICAO, estilos.NEUTRO),
    Comando("limpar_cor", "Limpar a cor do autor", EDICAO, estilos.NEUTRO, rotulo_curto="Limpar cor"),
    Comando("achar", "Achar no texto…", EDICAO, estilos.NEUTRO),
    Comando("substituir", "Substituir no texto…", EDICAO, estilos.NEUTRO),
    Comando("substituir_todos", "Substituir todos", EDICAO, estilos.NEUTRO),
    # A paleta e os estilos (S-246 a S-249). `inserir_figurina` e `inserir_avaliacao` são comandos
    # **com argumento**: a paleta de comandos da S-231 os mostra uma vez, e a escolha do símbolo é
    # da lista que eles abrem -- é o mesmo desenho de `aparencia`, que abre um submenu.
    Comando("paleta_de_glifos", "Paleta de glifos e símbolos", EDICAO, estilos.NEUTRO, rotulo_curto="Paleta"),
    Comando("inserir_figurina", "Inserir figurina", EDICAO, estilos.NEUTRO),
    Comando("inserir_avaliacao", "Inserir símbolo de avaliação", EDICAO, estilos.NEUTRO),
    Comando("estilo_titulo", "Estilo do parágrafo: título", EDICAO, estilos.NEUTRO, rotulo_curto="Título"),
    Comando("estilo_prosa", "Estilo do parágrafo: prosa", EDICAO, estilos.NEUTRO, rotulo_curto="Prosa"),
    Comando("estilo_notacao", "Estilo do parágrafo: notação", EDICAO, estilos.NEUTRO, rotulo_curto="Notação"),
    Comando("estilo_legenda", "Estilo do parágrafo: legenda", EDICAO, estilos.NEUTRO, rotulo_curto="Legenda"),
    # ------------------------------------- as ferramentas da Fase 41 (S-259 a S-262)
    #
    # **Os onze entram um a um, e o agrupador da barra não é comando.** A barra da aba mostra
    # "Alinhar" e "Caixa", que abrem listas -- mas quem *faz* alguma coisa é o item da lista, e é ele
    # que precisa de nome: a paleta da S-231 procura por nome, e "centralizar" é o que quem procura
    # digita. Os dois rótulos de grupo moram em `ui/strings.py`, que é onde o vocabulário que não é
    # ação já mora; pô-los aqui obrigaria o menu a uma linha "Alinhamento…" ao lado dos quatro itens
    # que ela abriria, pela regra de alcance da S-233.
    Comando(
        "alinhar_esquerda",
        "Alinhar o parágrafo à esquerda",
        EDICAO,
        estilos.NEUTRO,
        rotulo_curto="Esquerda",
    ),
    # O rótulo longo diz "e a figura" porque é o que ele faz, e porque é a pergunta que traz alguém
    # ao menu: centralizar um diagrama é a mesma escolha que centralizar o parágrafo dele (S-259).
    Comando(
        "alinhar_centro",
        "Centralizar o parágrafo e a figura",
        EDICAO,
        estilos.NEUTRO,
        rotulo_curto="Centralizar",
    ),
    Comando(
        "alinhar_direita",
        "Alinhar o parágrafo à direita",
        EDICAO,
        estilos.NEUTRO,
        rotulo_curto="Direita",
    ),
    Comando("justificar", "Justificar o parágrafo", EDICAO, estilos.NEUTRO, rotulo_curto="Justificar"),
    # Os dois de um caractere e meio, pela mesma razão de `zoom_mais` e `zoom_menos`: um rótulo tão
    # curto é o caso em que "escrito à mão" parece inofensivo, e é onde ninguém descobre depois o
    # que o botão fazia.
    Comando(
        "aumentar_corpo",
        "Aumentar o corpo do texto",
        EDICAO,
        estilos.NEUTRO,
        rotulo_curto="A+",
    ),
    Comando(
        "diminuir_corpo",
        "Diminuir o corpo do texto",
        EDICAO,
        estilos.NEUTRO,
        rotulo_curto="A-",
    ),
    Comando(
        "corpo_normal",
        "Voltar o corpo do texto ao normal",
        EDICAO,
        estilos.NEUTRO,
        rotulo_curto="Corpo normal",
    ),
    # **Os três rótulos curtos são escritos na caixa que eles produzem**, e isso é decisão e não
    # descuido: "MAIÚSCULAS" numa lista de três itens diz o que o item faz sem precisar de exemplo.
    Comando("maiusculas", "Trecho em MAIÚSCULAS", EDICAO, estilos.NEUTRO, rotulo_curto="MAIÚSCULAS"),
    Comando("minusculas", "Trecho em minúsculas", EDICAO, estilos.NEUTRO, rotulo_curto="minúsculas"),
    Comando(
        "capitular",
        "Trecho com Iniciais Maiúsculas",
        EDICAO,
        estilos.NEUTRO,
        rotulo_curto="Iniciais Maiúsculas",
    ),
    # ------------------------------------- a Fase 42 (S-263 a S-266)
    #
    # **Os quatro da área de transferência existiam como tecla e não como comando**, e a diferença
    # é a da S-161: `Ctrl+C` funciona no `tk.Text` de fábrica desde sempre, mas quem não sabe disso
    # não tem onde descobrir. Um menu Texto com vinte e nove linhas e sem "Copiar" diz, sem querer,
    # que a aba não copia.
    Comando("recortar", "Recortar o trecho", EDICAO, estilos.NEUTRO, rotulo_curto="Recortar"),
    Comando("copiar", "Copiar o trecho", EDICAO, estilos.NEUTRO, rotulo_curto="Copiar"),
    Comando("colar", "Colar no cursor", EDICAO, estilos.NEUTRO, rotulo_curto="Colar"),
    Comando(
        "selecionar_tudo",
        "Selecionar o texto inteiro da folha",
        EDICAO,
        estilos.NEUTRO,
        rotulo_curto="Selecionar tudo",
    ),
    # Os quatro da vista da aba e os dois do léxico **não** ficam aqui: eles são de VISUALIZACAO e
    # de OCR, e são declarados nos blocos daqueles grupos. A ordem de declaração é a ordem em que
    # `do_grupo` os devolve, e é a ordem em que a paleta da S-231 os mostra -- um comando de OCR
    # declarado no meio do bloco de EDICAO aparece antes de `ler_pagina` numa busca por "ocr", que
    # é uma resposta que ninguém lê como certa.
    # ----------------------------------------------------------------------- VISUALIZACAO
    # ---------------------------------- a vista da **aba de texto** (S-264/S-265)
    #
    # **Zoom é da vista, corpo é do documento**, e os rótulos longos dizem isso porque é a única
    # confusão possível entre dois pares de comandos que fazem a letra crescer na tela. O zoom não
    # entra no arquivo, não é exportado e vale para a folha inteira.
    #
    # Ficam **antes** dos da página do PDF porque o grupo é lido de cima para baixo na paleta, e um
    # comando de zoom de texto entre "Página anterior" e "Próxima página" leria como navegação.
    Comando(
        "aproximar_texto",
        "Aproximar o texto na tela (não muda o documento)",
        VISUALIZACAO,
        estilos.NEUTRO,
        rotulo_curto="Aproximar",
    ),
    Comando(
        "afastar_texto",
        "Afastar o texto na tela (não muda o documento)",
        VISUALIZACAO,
        estilos.NEUTRO,
        rotulo_curto="Afastar",
    ),
    Comando(
        "zoom_do_texto_normal",
        "Voltar o texto ao tamanho de tela normal",
        VISUALIZACAO,
        estilos.NEUTRO,
        rotulo_curto="Zoom normal",
    ),
    Comando(
        "quebrar_linha",
        "Quebrar as linhas na largura da janela",
        VISUALIZACAO,
        estilos.NEUTRO,
        rotulo_curto="Quebrar linha",
    ),
    Comando("pagina_anterior", "Página anterior", VISUALIZACAO, estilos.NEUTRO),
    Comando("proxima_pagina", "Próxima página", VISUALIZACAO, estilos.NEUTRO),
    # **As duas da S-281**, e elas não nasceram de um pedido: nasceram do par de teclas que a sala
    # de estudo precisava. `Home` e `End` são "início e fim da linha" dentro do estudo, e a tabela
    # da S-161 não aceita tecla sem comando global -- então a pergunta virou *o que Home e End
    # fazem no resto da janela?*, e a resposta óbvia estava faltando desde sempre: `Page Up` e
    # `Page Down` viram uma página, e nada levava à primeira ou à última.
    Comando("primeira_pagina", "Primeira página do livro", VISUALIZACAO, estilos.NEUTRO),
    Comando("ultima_pagina", "Última página do livro", VISUALIZACAO, estilos.NEUTRO),
    Comando("ajustar_largura", "Ajustar à largura", VISUALIZACAO, estilos.NEUTRO, icone="ajustar_largura"),
    Comando("ajustar_pagina", "Ajustar à página", VISUALIZACAO, estilos.NEUTRO, icone="ajustar_pagina"),
    # Os dois botões de um caractere. Um rótulo de um caractere é o caso em que "escrito à mão"
    # parece inofensivo -- e é onde a S-225 vai trocar os dois por um deslizador sem ter onde
    # descobrir o que eles faziam, se o texto continuasse sendo a única declaração deles.
    Comando(
        "zoom_menos",
        "Diminuir o zoom da página",
        VISUALIZACAO,
        estilos.NEUTRO,
        icone="zoom_menos",
        rotulo_curto="-",
    ),
    Comando(
        "zoom_mais",
        "Aumentar o zoom da página",
        VISUALIZACAO,
        estilos.NEUTRO,
        icone="zoom_mais",
        rotulo_curto="+",
    ),
    Comando(
        "marcar_diagramas",
        "Marcar os diagramas na página",
        VISUALIZACAO,
        estilos.NEUTRO,
        rotulo_curto="Marcar diagramas",
    ),
    Comando(
        "tirar_caixa",
        "Tirar a caixa do diagrama selecionado",
        VISUALIZACAO,
        estilos.NEUTRO,
        rotulo_curto="Tirar a caixa",
    ),
    Comando("devolver_caixas", "Devolver as caixas tiradas desta página", VISUALIZACAO, estilos.NEUTRO),
    # A escolha de pele (S-221). Fica em VISUALIZACAO porque é o menu onde ela mora, e não
    # ganha ícone: quem desenha submenu com ícone é a fita, e aparência não é comando de fita.
    Comando("aparencia", "Aparência", VISUALIZACAO, estilos.NEUTRO),
    # O segundo eixo de aparência (S-232), e ele fica **ao lado** da pele e não dentro dela. A
    # spec escreveu o caminho `Ver > Aparência > Densidade`, e aninhá-lo custaria a disciplina que
    # vale mais: aqui toda linha de menu é um `Item` de `menu.MENUS`, contável por
    # `acoes_declaradas` -- que é de onde a S-233 vai tirar o inventário de alcance. Um comando
    # montado por dentro de outro submenu não aparece em lista nenhuma.
    Comando("densidade", "Densidade", VISUALIZACAO, estilos.NEUTRO),
    # O terceiro eixo de aparência (S-230/S-506), e ele fica ao lado dos outros dois pela mesma
    # razão da densidade: comando montado por dentro de outro submenu não aparece em lista
    # nenhuma. Era um controle da aba Configuração, que a janela do Qt não tem -- e com ela o
    # registro de `ui/conjuntos.py` ficou declarando três conjuntos que nada alcançava.
    Comando("conjunto_de_pecas", "Peças", VISUALIZACAO, estilos.NEUTRO),
    Comando(
        "roda_vira_pagina",
        "A roda do mouse vira a página",
        VISUALIZACAO,
        estilos.NEUTRO,
        rotulo_curto="Roda vira a página",
    ),
    # -------------------------------------------------------------------------------- OCR
    Comando(
        "ler_pagina",
        "Ler esta página",
        OCR,
        estilos.NEUTRO,
        icone="ler_pagina",
        destaque=True,
        rotulo_curto="OCR todos diagramas",
    ),
    # **O primário do grupo é este, e o critério de `estilos.PRIMARIO` diz que devia ser o de
    # cima.** Lá está escrito "a ação que o atalho de teclado também faz", e `Ctrl+R` é
    # `ler_pagina`. O catálogo registra a janela como ela é -- trocar a ênfase é mudar a pele
    # clássica, que a regra 1 da SPEC_APARENCIA proíbe a esta fase. Fica anotado para a S-223,
    # que é quem decide a fila de ações: ou `Ctrl+R` ganha o botão primário, ou o critério de
    # `estilos.PRIMARIO` está errado e é ele que muda.
    Comando(
        "ler_melhor",
        "Ler o melhor diagrama da página",
        OCR,
        estilos.PRIMARIO,
        icone="ler_melhor",
        rotulo_curto="OCR melhor diagrama",
    ),
    # Os três da aba de texto: ler a folha é OCR pela pergunta do grupo -- age sobre a página
    # aberta agora. `ler_folha` **não** é primário, e é a única perda visível desta fase: hoje o
    # botão da aba sai em azul, e OCR já tem o seu primário (`ler_melhor`). O critério de
    # `estilos.PRIMARIO` é "a ação que o atalho de teclado também faz", e `Ler folha` não tem
    # tecla -- a ênfase de hoje já contrariava o critério, e é ela que sai.
    Comando("ler_folha", "Ler o texto desta folha", OCR, estilos.NEUTRO, rotulo_curto="Ler folha"),
    Comando(
        "folha_da_pagina_aberta",
        "Pôr no campo a folha que o visualizador mostra",
        OCR,
        estilos.NEUTRO,
        rotulo_curto="Da página aberta",
    ),
    Comando(
        "modo_bloco",
        "Ler o texto em modo bloco (lento)",
        OCR,
        estilos.NEUTRO,
        rotulo_curto="Modo bloco (lento)",
    ),
    Comando(
        "selecionar_area",
        "Selecionar área para ler",
        OCR,
        estilos.NEUTRO,
        icone="selecionar_area",
        rotulo_alternado="Cancelar seleção",
        rotulo_curto="Selecionar área (OCR)",
    ),
    # O léxico da S-209 na aba de texto (S-266). É OCR pela pergunta do grupo -- ele confere o que
    # o motor leu da folha aberta --, e o rótulo longo diz as **duas** coisas que ele faz e não faz,
    # porque a segunda é a que dá confiança para usar a primeira sobre uma página de OCR.
    Comando(
        "marcar_fora_do_lexico",
        "Marcar o que o léxico não conhece (não corrige nada)",
        OCR,
        estilos.NEUTRO,
        rotulo_curto="Conferir palavras",
    ),
    Comando(
        "limpar_marcas_do_lexico",
        "Limpar as marcas do léxico",
        OCR,
        estilos.NEUTRO,
        rotulo_curto="Limpar marcas",
    ),
    # ----------------------------------------------------------------------------- ACERVO
    Comando("varrer_livro", strings.VARRER_LIVRO, ACERVO, estilos.NEUTRO),
    # A fila da S-546 é ACERVO pela mesma pergunta do vizinho de cima -- ela age sobre livros
    # inteiros --, e as reticências dizem que ela abre uma janela em vez de começar a varrer:
    # é o mesmo contrato de "Indexar base…" e "Treinar o modelo".
    Comando("varrer_fila", "Varrer uma fila de livros…", ACERVO, estilos.NEUTRO),
    Comando("recarregar_modelo", "Recarregar o modelo", ACERVO, estilos.NEUTRO),
    Comando("treinar", "Treinar o modelo", ACERVO, estilos.NEUTRO),
    # Os três da linha de conjunto de campo (S-77). Nenhum tem item de menu, e a S-223 decidiu
    # que eles **não** ganham um: anotar verdade de referência sobre a página que não está à
    # vista é como se grava métrica errada.
    Comando("anotar_pagina", "Anotar página", ACERVO, estilos.PRIMARIO),
    Comando("anotar_sem_diagrama", "Sem diagrama", ACERVO, estilos.NEUTRO),
    Comando("tirar_do_campo", "Tirar o selecionado", ACERVO, estilos.NEUTRO),
    # ----------------------------------------------------------------------------- ESTUDO
    #
    # **O sétimo grupo, e ele é o item** (S-280). Medido antes: 13 botões na aba de estudo e
    # **zero** comandos no catálogo -- logo, zero na paleta da S-231, zero na legenda da S-165,
    # nenhum item de menu, e nenhuma das três peles capaz de desenhar um controle dela. É a S-161
    # pela terceira vez: *"o que não era botão não existia"*, agora com uma aba inteira no papel.
    #
    # O conjunto dos seis era fechado porque era "os cinco menus com Ferramentas partido em dois",
    # e a sala não é nenhum deles: promover variante não é `EDICAO` (que é edição de texto e de
    # tabuleiro), não é `VISUALIZACAO` (que não muda dado) e não é `OCR`. Distribuí-los faria a
    # fita da S-227 mostrar "Promover a variante" debaixo de "Edição", ao lado de "Colar" -- que é
    # a vizinhança que este módulo existe para impedir.
    Comando(
        "estudo_do_diagrama",
        "Estudar o diagrama selecionado",
        ESTUDO,
        estilos.PRIMARIO,
        rotulo_curto="Carregar OCR atual",
    ),
    Comando(
        "estudo_da_posicao_inicial",
        "Estudar a posição inicial",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Posição inicial",
    ),
    Comando("virar_tabuleiro", strings.VIRAR_TABULEIRO, ESTUDO, estilos.NEUTRO),
    Comando("trocar_vez", "Trocar o lado a jogar", ESTUDO, estilos.NEUTRO, rotulo_curto="Trocar vez"),
    # `estudo_aplicar_fen` e não `aplicar_fen`: aquele é o do **editor de diagrama**, tem
    # `Ctrl+Enter` desde a S-223 e escreve na posição que vai virar amostra. São dois campos de FEN
    # em duas abas, e um nome só faria a tecla de uma agir na outra.
    Comando(
        "estudo_aplicar_fen",
        "Aplicar a FEN digitada no estudo",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Aplicar FEN",
    ),
    Comando("copiar_fen", "Copiar a FEN do estudo", ESTUDO, estilos.NEUTRO, rotulo_curto="Copiar FEN"),
    # "Salvar" e não "Salvar PGN" desde a segunda rodada da S-527: o botão mora no grupo Exportar da
    # barra da sala, com o disquete ao lado e a dica dizendo o formato, e os 26 px de "PGN" eram o que
    # faltava para as catorze principais caberem a 1920 px. O menu continua dizendo o formato.
    Comando("salvar_estudo", "Salvar o estudo em PGN…", ESTUDO, estilos.NEUTRO, rotulo_curto="Salvar"),
    Comando(
        "lance_anterior",
        "Lance anterior",
        ESTUDO,
        estilos.NEUTRO,
        icone="diagrama_anterior",
        rotulo_curto=strings.ANTERIOR,
    ),
    Comando(
        "proximo_lance",
        "Próximo lance",
        ESTUDO,
        estilos.NEUTRO,
        icone="proximo_diagrama",
        rotulo_curto=strings.PROXIMO,
    ),
    Comando(
        "inicio_da_linha",
        "Início da linha",
        ESTUDO,
        estilos.NEUTRO,
        icone="inicio_da_linha",
        rotulo_curto=strings.PRIMEIRO,
    ),
    Comando(
        "fim_da_linha",
        "Fim da linha",
        ESTUDO,
        estilos.NEUTRO,
        icone="fim_da_linha",
        rotulo_curto=strings.ULTIMO,
    ),
    Comando(
        "promover_variante",
        "Promover a variante um nível",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Promover",
    ),
    Comando(
        "promover_a_principal",
        "Promover a variante a linha principal",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Principal",
    ),
    Comando("rebaixar_variante", "Rebaixar a variante", ESTUDO, estilos.NEUTRO, rotulo_curto="Rebaixar"),
    # Os dois DESTRUTIVOS da aba, e são os únicos: apagar variante e apagar continuação são as
    # duas ações que tiram trabalho humano da árvore. As duas perguntam antes quando há o que
    # perder -- ver `study_panel._confirmar_apagar` --, e o papel é o que faz a pele desenhá-las
    # como o que elas são.
    Comando(
        "apagar_variante",
        "Apagar a variante",
        ESTUDO,
        estilos.DESTRUTIVO,
        rotulo_curto="Apagar variante",
    ),
    Comando(
        "apagar_continuacao",
        "Apagar daqui em diante",
        ESTUDO,
        estilos.DESTRUTIVO,
        rotulo_curto="Apagar daqui",
    ),
    Comando("simbolo_do_lance", "Símbolo do lance…", ESTUDO, estilos.NEUTRO, rotulo_curto="Símbolo"),
    Comando(
        "dobrar_variantes",
        "Dobrar todas as variantes",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Dobrar",
        rotulo_alternado="Desdobrar",
    ),
    # ------------------------------------------------------- o livro dentro da sala (Fase 47)
    Comando(
        "mostrar_diagrama",
        "Mostrar o recorte do diagrama",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Recorte",
        rotulo_alternado="Esconder recorte",
    ),
    Comando(
        "linha_do_livro",
        "Jogar a linha impressa no livro",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Linha do livro",
    ),
    Comando(
        "ir_para_a_pagina",
        "Ir para a página do diagrama",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Ver a página",
    ),
    # --------------------------------------------------- o motor e a base de partidas (Fase 48)
    Comando(
        "analisar_posicao",
        "Analisar a posição com o motor",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Analisar posição",
    ),
    Comando(
        "analise_continua",
        "Análise contínua enquanto se navega",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Análise contínua",
        rotulo_alternado="Parar a análise",
    ),
    Comando(
        "variante_do_motor",
        "Pôr a linha do motor como variante",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Linha do motor",
    ),
    # A partida inteira pelo motor (S-537): cada lance avaliado, o gráfico e os erros marcados.
    # Mora no grupo Motor da barra da sala, dentro do "Mais" -- analisa-se uma partida por sessão,
    # e a operação leva minutos.
    Comando(
        "analisar_partida",
        "Analisar a partida inteira com o motor…",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Analisar partida",
    ),
    # As opções do motor (S-536). **É o único comando do grupo Motor que existe sem motor**, e
    # tem de ser: é por ele que se informa onde o binário está numa máquina em que a procura
    # automática não achou nada.
    Comando(
        "opcoes_do_motor",
        "Opções do motor de análise…",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Opções do motor",
    ),
    Comando(
        "partidas_da_posicao",
        "Partidas que chegaram a esta posição",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Partidas",
    ),
    # A outra metade da janela de aberturas do ChessBase (S-535): `partidas_da_posicao` diz
    # **quais** partidas passam por aqui, e esta diz **o que se joga daqui** -- cada lance com
    # quantas partidas, como elas terminaram, com que Elo e em que ano.
    Comando(
        "arvore_de_aberturas",
        "Árvore de aberturas desta posição",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Árvore",
    ),
    # A pergunta que não nasce de um diagrama (S-533): "as partidas de Carlsen em 2019 com Elo
    # acima de 2700 na Najdorf". `partidas_da_posicao` responde pela posição do tabuleiro e só por
    # ela; esta abre o formulário de seis campos sobre o índice por nome.
    Comando(
        "buscar_partidas",
        "Buscar partidas na base por jogador, evento, ano, Elo e ECO…",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Buscar partidas",
    ),
    # O índice por nome construído de dentro da janela (S-532), que até a S-527 só existia como
    # `cvoff-games --build-index` num terminal: a busca por nome de "Partidas" o recusa quando ele
    # está atrasado, e a saída tem de ser um comando da sala e não uma frase de aviso.
    Comando(
        "indexar_base",
        "Indexar a base de partidas por nome…",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Indexar base",
    ),
    # ----------------------------------------------------- o que entra e o que sai (Fase 49)
    Comando("colar_estudo", "Colar posição ou partida…", ESTUDO, estilos.NEUTRO, rotulo_curto="Colar"),
    Comando("abrir_pgn", "Abrir um .pgn…", ESTUDO, estilos.NEUTRO, rotulo_curto="Abrir PGN"),
    # As três saídas são as da Fase 39, alimentadas pelo estudo em vez de pelo documento -- e por
    # isso os rótulos são os mesmos daquela aba: o que muda é o que entra no exportador, não o
    # formato. `salvar_estudo` (o PGN) já mora acima: ele é a saída que não perde nada.
    Comando("exportar_estudo_md", "Exportar o estudo para Markdown…", ESTUDO, estilos.NEUTRO, rotulo_curto=".md"),
    Comando("exportar_estudo_html", "Exportar o estudo para HTML…", ESTUDO, estilos.NEUTRO, rotulo_curto=".html"),
    Comando("exportar_estudo_rtf", "Exportar o estudo para RTF…", ESTUDO, estilos.NEUTRO, rotulo_curto=".rtf"),
    # O quarto formato é da S-545, e entra na mesma fileira porque é a mesma pergunta -- "em que
    # formato?". A diferença dele é que a página existe: os três de cima entregam o estudo como
    # texto marcado, e quem pagina é o programa que abrir o arquivo; o PDF sai **já paginado**,
    # com margem, cabeçalho e número de página, e é por isso que a decisão da paginação é nossa.
    Comando("exportar_estudo_pdf", "Exportar o estudo para PDF…", ESTUDO, estilos.NEUTRO, rotulo_curto=".pdf"),
    # Imprimir **não** é um quinto formato, e por isso não está no agrupador "Exportar": o gesto
    # termina no papel e passa pela pré-visualização, que é onde se confere a quebra antes de
    # gastar folha. O PDF e a impressão desenham a mesma paginação, e é a mesma decisão pura.
    Comando("imprimir_estudo", "Imprimir o estudo…", ESTUDO, estilos.NEUTRO, rotulo_curto="Imprimir"),
    # O lote de diagramas (S-544) sai do grupo ESTUDO pela pergunta do grupo -- ele age sobre a
    # análise que está aberta --, e é o único comando da sala cujo produto não é **um** arquivo:
    # uma sala de quinhentos estudos vira quinhentos PNGs, um por diagrama.
    Comando(
        "exportar_diagramas_lote",
        "Exportar os diagramas em lote…",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Diagramas em lote",
    ),
    Comando(
        "estudo_para_o_texto",
        "Levar a linha do estudo para a aba Texto",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Para o texto",
    ),
    # ---------------------------------------------------------------------- treinar (Fase 50)
    Comando(
        "modo_treino",
        "Treinar: adivinhar o lance da linha",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Treinar",
        rotulo_alternado="Parar o treino",
    ),
    # Os dois da Fase 83, e os dois moram no "Mais" da barra pela régua de `fila_de_destaque`:
    # extrai-se uma vez por livro e abre-se a agenda uma vez por sessão -- nenhum dos dois é gesto
    # de lance. `modo_treino` acima continua sendo o do lance a lance, e por isso continua na fila.
    Comando(
        "taticas_do_livro",
        "Extrair as táticas deste livro…",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Táticas do livro",
    ),
    Comando(
        "treinar_agenda",
        "Treinar a agenda de hoje…",
        ESTUDO,
        estilos.NEUTRO,
        rotulo_curto="Revisar hoje",
    ),
    # ------------------------------------------------------------------------------ AJUDA
    # Antes da legenda porque as duas são a mesma pergunta em duas metades -- "o que existe"
    # e "que tecla faz" --, e a paleta é a que responde primeiro. Sem ícone e sem `destaque`:
    # ela não é comando de fita nem de fila, e a porta dela é a tecla (S-231).
    Comando("paleta_de_comandos", "Paleta de comandos", AJUDA, estilos.NEUTRO),
    Comando("legenda_de_atalhos", "Atalhos de teclado", AJUDA, estilos.NEUTRO),
    Comando("abrir_log", "Abrir o arquivo de log", AJUDA, estilos.NEUTRO),
    Comando("sobre", "Sobre o ChessVisionOFF", AJUDA, estilos.NEUTRO),
)
"""Os comandos da janela, em ordem de grupo e, dentro dele, na ordem em que já se liam.

**O que entrou:** tudo o que `menu.MENUS` declara, tudo o que `atalhos.ATALHOS` liga, os botões
das duas barras de `ui/pdf_panel.py` e os três da linha de conjunto de campo. São os quatro
lugares que a S-324 nomeia, e o teste cobra os quatro.

**O que não entrou, e por quê.** Os controles de dentro de uma aba -- Galeria, Dataset, Revisão,
Configuração -- não são comandos da *janela*: eles pertencem ao painel que os desenha e não
mudam de lugar quando a pele muda. É a mesma linha que `menu.MENUS` já traçava ao deixar de fora
os botões de navegação da Galeria. `ui/result_panel.py` é o caso de fronteira: os três botões
dele ("Aplicar FEN", "Salvar posição reconhecida", "Salvar todos") **são** comandos da janela e
estão aqui, mas o painel ainda escreve os rótulos dele à mão -- por isso os três não declaram
`rotulo_curto`, que seria uma promessa que ninguém cumpre. Registrado para a S-233."""


NAS_BARRAS_DO_PDF: tuple[str, ...] = (
    # a barra do livro: o que se faz **com** a página exibida
    "abrir_pdf",
    "abrir_no_leitor",
    "ler_melhor",
    "ler_pagina",
    "tirar_caixa",
    "exportar_pgn",
    "cancelar_exportacao",
    # a barra de navegação: o que se faz **na** página
    "pagina_anterior",
    "proxima_pagina",
    "zoom_menos",
    "zoom_mais",
    "ajustar_largura",
    "ajustar_pagina",
    "selecionar_area",
    "roda_vira_pagina",
    "marcar_diagramas",
)
"""Os comandos que as duas barras de `qt/painel_do_pdf.py` desenham (S-233).

**Declarado aqui e montado lá, e a distância entre os dois tem guarda.** O painel constrói os
dezesseis controles à mão -- `QPushButton` pelo `_botao`, `QCheckBox` pelos dois interruptores --,
com estado, dica e função diferentes em cada um. O que a lista compra é o inventário poder lê-la sem
abrir janela; quem cobra que as duas concordem é
`test_ui_comandos.test_a_declaracao_das_barras_bate_com_o_que_o_painel_desenha`, que varre aquele
arquivo por `ast`.

**A lista mudou de significado no corte do Tk (S-506).** Antes ela era a tela da pele *clássica*,
desenhada por `_montar_barras` de `ui/pdf_panel.py`, e quem a cobrava era
`tests/test_ui_alcance.py` -- função, módulo e teste saíram juntos. Agora ela é o que
`qt/painel_do_pdf.py` desenha, que é a única tela que existe.

**Cinco tinham perdido o botão no porte e voltaram**: `ler_melhor`, `ler_pagina`, `tirar_caixa`,
`exportar_pgn` e `cancelar_exportacao`. No intervalo em que a lista ficou sem leitor eles sumiram
dela sem ninguém notar -- continuavam alcançáveis pelo menu, pela paleta e pela tecla, e é por isso
que a conta do catálogo passava em verde sobre a ausência. **Alcance não é presença**, e esta lista
é a que responde pela segunda.

**Na pele "Foco" e na "Fita" estes controles existem e não são empacotados** (S-223): o que a pele
decide é o que aparece, e esta lista é o que o painel desenha."""


NA_JANELA_DE_BUSCA: tuple[str, ...] = ("substituir_todos",)
"""Os comandos que só existem **dentro** da janela de achar e substituir (S-343).

`substituir_todos` é o botão que troca as ocorrências marcadas na lista, e a lista só existe
naquela janela. Como comando da paleta ele abria a mesma janela que "Substituir…" -- dois rótulos
para uma ação, e o segundo prometendo uma troca em massa que ele não fazia.

Fica no catálogo porque é de lá que o botão tira o rótulo, e é declarado aqui para a paleta poder
dizer **por que** não o executa, em vez de mostrá-lo como se executasse."""


NA_LINHA_DE_CAMPO: tuple[str, ...] = ("anotar_pagina", "anotar_sem_diagrama", "tirar_do_campo")
"""Os comandos que moram na linha de conjunto de campo, e **não** ganham item de menu (S-223).

A S-77 os pôs junto da página exibida de propósito: eles anotam *aquela* página, e um comando de
menu que age sobre a página exibida sem que ela esteja à vista é o tipo de gesto que grava verdade
de referência errada. São a única exceção à regra de que todo comando alcança o menu -- e existir
como lista declarada é o que permite o teste cobrar que não haja uma segunda."""


por_acao: dict[str, Comando] = {registro.acao: registro for registro in CATALOGO}
"""Índice por nome. É por aqui que o menu, o painel e a fila da S-223 acham o comando."""

if len(por_acao) != len(CATALOGO):  # pragma: no cover - defeito de declaração, não de execução
    # Levanta na importação, e só este caso levanta: um `acao` repetido faz o índice **perder**
    # em silêncio o primeiro dos dois, e a partir daí metade do programa usa um registro que
    # ninguém escreveu para ele. As outras regras do catálogo são cobradas por teste.
    repetidos = sorted({acao for acao, vezes in Counter(r.acao for r in CATALOGO).items() if vezes > 1})
    raise ValueError(f"comando declarado duas vezes no catálogo: {', '.join(repetidos)}")


def comando(acao: str) -> Comando:
    """O registro daquele comando. Levanta `KeyError` para nome que não existe.

    Levanta em vez de devolver `None`, como `tokens.cor` e `estilos.estilo_de_botao`: um nome
    escrito errado que virasse botão sem rótulo é pior que a exceção -- ele desenha.
    """
    if acao not in por_acao:
        raise KeyError(f"comando desconhecido: {acao!r}. Os declarados estão em CATALOGO.")
    return por_acao[acao]


def rotulo(acao: str) -> str:
    """O rótulo longo -- o que o menu mostra."""
    return comando(acao).rotulo


def rotulo_de_botao(acao: str) -> str:
    """O rótulo curto -- o que o botão mostra. Igual ao longo quando não há um curto."""
    return comando(acao).no_botao


def rotulo_alternado(acao: str) -> str:
    """O rótulo de **ligado** daquele comando. Igual ao normal quando ele não alterna."""
    return comando(acao).alternado


_SEGUIDORES: dict[str, list[Callable[[str], object]]] = {}
"""Quem repinta o rótulo de um comando que alterna. Ver `ao_alternar` (S-396)."""


def ao_alternar(acao: str, aplicar: Callable[[str], object]) -> None:
    """Registra quem tem de mostrar o estado ligado/desligado daquele comando (S-396).

    **"Selecionar área" é um modo, e só a pele clássica dizia isso.** O botão dela troca o texto
    para "Cancelar seleção" desde a S-222; na "Foco" e na "Fita" o mesmo comando ligava o modo e
    o botão continuava escrito "Selecionar área" -- ligar e desligar tinham o mesmo aspecto, e o
    único jeito de saber em que estado se estava era arrastar o mouse sobre a folha e ver o que
    acontecia.

    Recebe uma função e não um widget de propósito: este módulo é o catálogo e não importa
    `tkinter`. Quem registra decide o que fazer com o texto -- a fita o quebra em duas linhas, a
    clássica o usa inteiro.
    """
    _SEGUIDORES.setdefault(acao, []).append(aplicar)


def alternou(acao: str, *, ligado: bool) -> None:
    """Avisa os seguidores daquele comando. Nunca levanta, e esquece o que já morreu.

    Mesma disciplina de `theme.repintar`: um botão destruído entre o registro e a troca é a
    janela de antes, e ele sai da lista em vez de derrubar os outros.
    """
    texto = rotulo_alternado(acao) if ligado else rotulo_de_botao(acao)
    vivos: list[Callable[[str], object]] = []
    for aplicar in _SEGUIDORES.get(acao, []):
        try:
            aplicar(texto)
        except Exception:  # noqa: BLE001 - widget morto, ou pele remontada: sai da lista
            continue
        vivos.append(aplicar)
    _SEGUIDORES[acao] = vivos


def papel(acao: str) -> str:
    """O papel de botão daquele comando: `PRIMARIO`, `DESTRUTIVO` ou `NEUTRO`."""
    return comando(acao).papel


def estilo(acao: str) -> str:
    """O nome de estilo `ttk` daquele comando, pronto para `ttk.Button(style=...)`.

    Existe para que o painel não precise escrever `estilos.estilo_de_botao(estilos.PRIMARIO)`:
    era ali que a ênfase ficava declarada pela segunda vez, longe de qualquer regra que a
    comparasse com a dos outros botões do mesmo grupo.
    """
    return estilos.estilo_de_botao(papel(acao))


def rotulo_do_grupo(grupo: str) -> str:
    """Como o grupo se escreve num cabeçalho. Levanta `KeyError` para grupo que não existe."""
    if grupo not in _ROTULOS_DE_GRUPO:
        raise KeyError(f"grupo desconhecido: {grupo!r}. Os válidos estão em GRUPOS.")
    return _ROTULOS_DE_GRUPO[grupo]


def do_grupo(grupo: str) -> tuple[Comando, ...]:
    """Os comandos daquele grupo, na ordem de declaração. É a fonte da fita da S-227."""
    rotulo_do_grupo(grupo)
    return tuple(registro for registro in CATALOGO if registro.grupo == grupo)


def fila_de_destaque() -> tuple[tuple[Comando, ...], ...]:
    """A fila da pele "Foco", já agrupada: uma tupla por grupo, na ordem de `GRUPOS` (S-223).

    **Quatro, e todos têm atalho de teclado** -- que é o critério da S-223, e não o gosto: a
    mesma lógica com que `estilos.PRIMARIO` é definido como *"a ação que o atalho também faz"*.
    Não são exatamente os quatro da Imagem 1. Ela desenhou "exportar" e omitiu "salvar", e a
    medida do fluxo inverte os dois: exporta-se uma vez por livro e salva-se uma vez por
    diagrama. O quarto lugar foi para `salvar`; `aplicar_fen` ganhou `Ctrl+Enter`, que lhe
    faltava, e a razão está em `ui/atalhos.py`. (Havia uma `em_destaque()` plana ao lado desta,
    que ninguém chamava; saiu na triagem da S-511 e o argumento dela veio para cá.)

    **O separador não está aqui, e é de propósito.** Devolver grupos em vez de uma lista plana
    com marcas faz "separador só entre grupos, nunca na ponta" deixar de ser regra a cobrar e
    virar consequência da forma: quem desenha põe uma barra **entre** tuplas consecutivas, e não
    há onde pôr uma sobrando. Grupo sem comando em destaque não aparece.

    A ordem é a do catálogo, e não a da imagem. A Imagem 1 começa por "ler"; aqui a Edição vem
    antes do OCR porque é a ordem de `GRUPOS`, que é a da barra de menus. Reordenar a fila seria
    declarar pela segunda vez em que ordem os comandos vivem -- e é disso que a S-324 tirou o
    programa.
    """
    grupos = tuple(tuple(registro for registro in do_grupo(grupo) if registro.destaque) for grupo in GRUPOS)
    return tuple(grupo for grupo in grupos if grupo)


def primarios_por_grupo() -> dict[str, list[str]]:
    """`grupo → os comandos PRIMARIO dele`. Mais de um em qualquer grupo é o defeito.

    A regra é a de `ui/estilos.py:31-36` -- *uma ênfase por barra, nunca duas* --, e é aqui que
    ela **finalmente se afirma sem abrir janela**: enquanto a ênfase morava no `style=` de cada
    botão, contá-la exigia montar a barra e ler os widgets.

    Devolve em vez de levantar de propósito. Papel inválido é erro de digitação e levanta na
    construção; duas ênfases no mesmo grupo é decisão de desenho, e derrubar a janela por causa
    dela seria desproporcional -- quem cobra é o teste.
    """
    contagem: dict[str, list[str]] = {grupo: [] for grupo in GRUPOS}
    for registro in CATALOGO:
        if registro.papel == estilos.PRIMARIO:
            contagem[registro.grupo].append(registro.acao)
    return contagem


def acoes_fora_do_catalogo(acoes: Iterable[str]) -> list[str]:
    """Os nomes pedidos que o catálogo não conhece, ordenados. Vazio é o estado correto.

    O outro sentido da trava de `menu.comandos_faltando`: lá, comando declarado que ninguém
    amarrou; aqui, comando amarrado que ninguém declarou.
    """
    return sorted({acao for acao in acoes if acao and acao not in por_acao})
