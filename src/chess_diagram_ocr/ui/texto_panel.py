"""A aba de texto: a página inteira num editor, com os diagramas onde eles estão (S-211).

**O que ela é, em uma frase: a `PaginaLida` na tela, editável.** O resto do programa trabalha
diagrama a diagrama -- o Resultado abre o tabuleiro clicado, a Revisão enfileira os duvidosos, a
Galeria lista o livro. Nenhuma dessas abas mostra o *texto* da página, e por isso a única forma de
conferir o que o OCR leu era abrir o JSON.

**Quase nada é decidido aqui.** Onde o diagrama entra no fluxo, o que merece destaque e o que vai
para o arquivo são de `text/documento.py`; o que a edição faz com um trecho é de `text/rico.py`; o
que a busca acha é de `text/busca.py`. Nenhum dos três importa `tkinter`, e é onde os testes moram.
Este arquivo é o que sobra depois disso: widgets, uma thread e um `after`.

## Onde a aba fica na barra, e por quê

Entre a Revisão e o Dataset (S-162): ela é do **diagrama aberto agora** e não do acervo. A
pergunta que ela responde -- "o que está escrito nesta folha?" -- é a mesma pergunta de contexto
que o Resultado e a Revisão respondem sobre o diagrama, e não uma navegação pelo livro, que é o
que as três abas seguintes fazem.

## O diagrama é desenhado no meio do texto, e a marca continua lá

A miniatura entra com `Text.image_create`, na posição exata em que `[Diagrama N]` está -- e a
marca **não** é apagada. Parece redundante numa tela onde a imagem já aparece, e é o contrário: a
imagem é do widget e morre com ele, a marca é do texto e sobrevive a salvar, copiar e colar. Um
editor que trocasse a marca pela imagem perderia o diagrama na primeira exportação.

## A leitura sai da thread da janela, e a razão é medida

Ler uma página de scan com o classificador de glifo custa ~1 s a 220 dpi, e ~40 s com o modo
bloco da S-188 ligado (`docs/metrics/texto_pagina.json`). Os dois travariam a janela -- o segundo
por tempo suficiente para o Windows a declarar "não respondendo". A leitura roda numa thread, o
resultado volta por `after`, e o `BusyRegistry` é quem avisa que há trabalho em curso.

# As ferramentas de edição (Fase 37)

## O deslocamento é a fronteira, e ela é estreita de propósito

As funções que decidem o que uma ferramenta faz são puras e falam em **deslocamento de
caractere**: `rico.alternar`, `rico.aplicar`, `busca.achar`. O que este arquivo acrescenta é a
conversão entre o índice do Tk (`"sel.first"`, `"insert"`) e esse deslocamento -- e ela é pequena
por construção, porque é justamente o pedaço que precisa do widget.

Não é `len` do texto do widget: a miniatura do diagrama vale um caractere para o Tk e nenhum para
o documento, e a quebra que o desenho acrescenta embaixo dela também não é do documento. Quem
conta certo é `texto_etiquetas.deslocamento`.

## Formato entra por etiqueta; texto entra por documento

Duas classes de comando, e a diferença decide o desfazer:

- **negrito, itálico, cor, realce** não mudam um caractere. São `tag_add`/`tag_remove` no
  intervalo, sem redesenho: o cursor fica onde estava, a rolagem não salta e a pilha de desfazer
  do Tk -- que é a do texto digitado -- continua inteira;
- **substituir em massa** muda o texto. Aí o caminho é o documento: a função pura devolve um
  `DocumentoRico` novo, o painel guarda um instantâneo do anterior e redesenha.

O redesenho **zera a pilha do Tk**, e isso foi medido aqui: desligar `-undo`, redesenhar e ligar de
novo *não* protege a pilha -- ela sobrevive com índices que já não descrevem o texto, e o
`Ctrl+Z` seguinte apaga um pedaço qualquer. Por isso `desenhar_documento` chama `edit_reset()`, e
por isso a substituição tem instantâneo próprio: sem ele, desfazer uma troca em massa seria
impossível em vez de ser inteira.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import TYPE_CHECKING, Literal

from ..text import arquivo, busca, correcao, documento, exportacao
from ..text import paleta as _paleta
from ..text import pdf_pesquisavel, rascunho, rico
from ..text.pagina import BlocoDeDiagrama, PaginaLida
from . import atalhos, comandos, texto_busca, texto_cores, texto_etiquetas, theme, tipografia, tokens
from . import texto as texto_ui
from .barra import BarraFluida
from .busy import BusyRegistry

if TYPE_CHECKING:  # pragma: no cover - só o verificador de tipo precisa disto
    from ..text.leitor import MotorDeTexto
else:
    MotorDeTexto = Literal["auto", "camada", "glifo"]

logger = logging.getLogger(__name__)

LADO_DA_MINIATURA = 132
"""Lado da miniatura do diagrama no texto, em pixels.

Grande o bastante para se reconhecer a posição sem abrir nada, e pequeno o bastante para o
parágrafo seguinte continuar visível. Não é o tabuleiro do editor -- quem quer jogar nele clica e
vai para a aba Resultado."""

PAPEL_DA_FAIXA = {
    documento.REVISAR: tokens.PROBLEMA,
    documento.CONFERIR: tokens.ATENCAO,
    documento.TRANQUILO: "",
}
"""O papel de cor de cada faixa de `documento`, resolvido em `ui/tokens.py`.

Papel e não hexadecimal, pela regra que `tokens` inteiro existe para manter: uma cor cravada aqui
seria a mesma tinta com outro significado nos dois painéis lado a lado, e no tema escuro ela pode
simplesmente sumir. `""` é "a cor normal do texto" -- e é deliberado que o trecho tranquilo **não**
peça papel nenhum: pintá-lo de preto é o que quebraria o tema escuro.

**Este mapa é o outro lado da S-242.** É ele que faz a cor da letra querer dizer confiança nesta
aba -- e é por isso que a paleta do autor não pode oferecer os mesmos papéis. Quem afirma a
interseção vazia é `tests/test_ui_texto_cor.py`, comparando este mapa com
`ui/texto_cores.PAPEIS_DA_FAIXA`."""

PAPEL_DA_MARCA = tokens.TEXTO_SECUNDARIO
"""A cor de `[Diagrama N]`. Secundário porque a marca é referência, e não texto do livro."""

NEGRITO_ITALICO = "negrito_italico"
"""A tag que desenha os dois juntos. **É desenho, e não documento** -- ver `_etiquetas` (S-236)."""

PAPEL_DO_ESTILO: dict[str, str] = {
    rico.ESTILO_TITULO: tipografia.TITULO,
    rico.ESTILO_PROSA: tipografia.CORPO,
    rico.ESTILO_NOTACAO: tipografia.DADO,
    rico.ESTILO_LEGENDA: tipografia.AUXILIAR,
}
"""Estilo de parágrafo -> papel de fonte de `ui/tipografia.py` (S-249).

**Nenhum tamanho em pixel entra aqui**, e é critério de aceite: `tipografia` escala pela fonte do
sistema desde a S-147, e cravar `12` quebraria quem aumentou a fonte do Windows -- o mesmo defeito
que `ui/texto.py` corrigiu para o `wraplength`. `NOTACAO` cai em `DADO` porque `DADO` é a
monoespaçada, e uma linha de lances alinhada é o que a proporcional estraga."""

ESCAPE_DA_PALETA = "\\"
"""O prefixo das sequências de teclado da S-248. Ver `text/paleta.SEQUENCIAS_DECLARADAS`."""

ACOES_PROPRIAS: frozenset[str] = frozenset({"salvar", "desfazer", "refazer", "achar", "substituir"})
"""As ações globais que esta aba atende **enquanto tem o foco** (S-244).

`Ctrl+S` com o cursor no texto salva o texto, e não a posição do tabuleiro. Não é tecla nova: é a
mesma tecla com destino conforme o foco, que é o que qualquer programa faz e o que esta aba não
fazia -- a guarda de `ui/shortcuts.py` cedia a tecla a todo campo de texto (por medição, desde a
S-20), e do outro lado ninguém a ligava. O resultado era um silêncio de duas camadas.

Quem confere que cada ação declarada é de fato atendida é `atalhos.conferir_dono`, na montagem:
declarar e não atender come a tecla e não faz nada, que é pior que não declarar."""

MOTORES: tuple[MotorDeTexto, ...] = ("glifo", "camada", "auto")
"""Os mesmos três de `text/leitor.py`, e a caixa da barra os oferece nesta ordem.

**`text/leitor.py` não é importado no topo deste arquivo, e é regra e não descuido.** Por
`text/recognizer.py` ele alcança o **torch**, e a aba de texto é construída na abertura da janela,
junto com as outras seis: pagar o carregamento de um framework de aprendizado para desenhar uma
barra de botões atrasaria a janela inteira por uma aba que talvez ninguém abra. O `import` mora
dentro de `ler`, que é o primeiro momento em que ele é de fato necessário -- a mesma razão do
import tardio de `ocr_caption` em `cli/_ocr.py`.

O `cv2` e o `numpy` **entram assim mesmo**, por `text/documento.py` -> `text/pagina.py` ->
`text/boxes.py`, e isso é anterior a esta aba: `pagina.py` importa `Caixa` no topo desde a S-193.
Fica dito para o próximo leitor não concluir, do parágrafo acima, que este arquivo é leve."""


class TextoPanel(ttk.Frame):
    """A aba `Texto`. Não reconhece nada: pede ao `text/leitor.py` e desenha o que volta."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        pdf_path: Callable[[], Path | None],
        page_index: Callable[[], int],
        on_status: Callable[[str], None],
        busy: BusyRegistry,
        on_page_request: Callable[[int], None] | None = None,
        dpi: int = 220,
        pasta_de_rascunhos: Path | None = None,
    ) -> None:
        super().__init__(master, padding=8)
        self._pdf_path = pdf_path
        self._page_index = page_index
        self._on_status = on_status
        self._busy = busy
        self._on_page_request = on_page_request
        self._dpi = dpi

        self._pagina: PaginaLida | None = None
        self._imagens: list[tk.PhotoImage] = []
        """As miniaturas vivas. **O Tk não segura a imagem** -- sem esta lista elas somem assim que
        o coletor passar, e o texto fica com buracos brancos onde havia diagrama."""
        self._pagina_rgb = None
        self._lendo = False
        self._sujo = False
        self._edicoes = 0
        """Quantas edições a aba recebeu. É o `edicao` do `ui/desfazivel.py` -- ver `contem`."""
        self._redesenhando = False
        self._instantaneos: list[tuple[int, rico.DocumentoRico]] = []
        self._refeitos: list[rico.DocumentoRico] = []
        self._janela_de_busca: texto_busca.JanelaDeBusca | None = None
        self._paleta = _paleta.paleta()
        """A paleta de glifos, derivada do metadado do modelo (S-246). Degrada sozinha."""

        self._sequencias = self._paleta.sequencias()
        r"""`\N` -> `♘`, conferido contra a paleta na montagem (S-248)."""

        self._fontes_desenhadas: set[str] = set()
        """As etiquetas de fonte combinada já configuradas -- ver `_etiqueta_de_fonte`."""

        self._painel_da_paleta: ttk.Frame | None = None
        self._exportando = False
        self._cancelar_exportacao = threading.Event()
        self._rascunho_agendado: str | None = None
        self._pasta_de_rascunhos: Path | None = pasta_de_rascunhos
        """Onde o rascunho da S-255 é gravado. `None` usa `text/rascunho.PASTA_PADRAO`; o teste
        passa uma pasta própria para não escrever em `data/` da máquina de quem roda a suíte."""

        self.formato_var: dict[str, tk.BooleanVar] = {
            atributo: tk.BooleanVar(value=False) for atributo in ("negrito", "italico", "sublinhado")
        }
        """O espelho do que vale sob o cursor, para os três interruptores da barra (S-241)."""

        self.folha_var = tk.StringVar(value="1")
        self.motor_var = tk.StringVar(value=MOTORES[0])
        self.bloco_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Abra um PDF e clique em Ler folha.")

        self._montar()

    # ------------------------------------------------------------------------------ construção

    def _montar(self) -> None:
        # `BarraFluida` e não `Frame`: a fila passou de dez itens para dezesseis com as
        # ferramentas da Fase 37, e `pack(side=LEFT)` numa linha só **não desenha** o que passa da
        # borda -- sem aviso e sem reticências, que é o defeito medido pela S-151.
        barra = BarraFluida(self)
        barra.pack(fill=tk.X, pady=(0, 6))

        barra.adicionar(ttk.Label(barra, text="Folha"))
        barra.adicionar(
            ttk.Spinbox(barra, from_=1, to=99999, width=7, textvariable=self.folha_var)
        )
        barra.adicionar(self._botao(barra, "folha_da_pagina_aberta", self.sincronizar_com_a_pagina))

        barra.adicionar(ttk.Label(barra, text="Motor"))
        barra.adicionar(
            ttk.Combobox(
                barra, values=MOTORES, textvariable=self.motor_var, width=8, state="readonly"
            )
        )

        # Rótulo do catálogo também aqui: a varredura da S-219 olha `Checkbutton`, e este era o
        # único texto de comando desta barra que não era botão.
        barra.adicionar(
            ttk.Checkbutton(
                barra,
                text=comandos.rotulo_de_botao("modo_bloco"),
                variable=self.bloco_var,
                command=self.modo_bloco_mudou,
            )
        )

        barra.adicionar(self._botao(barra, "ler_folha", self.ler))
        barra.adicionar(self._botao(barra, "abrir_texto", self.abrir_documento))
        barra.adicionar(self._botao(barra, "salvar_texto", self.salvar_documento))
        barra.adicionar(self._botao(barra, "exportar_txt", self.salvar))

        for atributo in self.formato_var:
            barra.adicionar(self._interruptor_de_formato(barra, atributo))
        barra.adicionar(self._menu_de_cor(barra, "cor_do_texto", self.pintar_letra))
        barra.adicionar(self._menu_de_cor(barra, "realce", self.pintar_realce))
        barra.adicionar(self._botao(barra, "achar", self.achar))
        barra.adicionar(self._botao(barra, "paleta_de_glifos", self.alternar_paleta))

        corpo = ttk.Frame(self)
        corpo.pack(fill=tk.BOTH, expand=True)
        self._corpo = corpo
        barra_de_rolagem = ttk.Scrollbar(corpo, orient=tk.VERTICAL)
        self.editor = tk.Text(
            corpo,
            wrap=tk.WORD,
            undo=True,
            padx=10,
            pady=8,
            spacing2=2,
            spacing3=8,
            yscrollcommand=barra_de_rolagem.set,
        )
        barra_de_rolagem.config(command=self.editor.yview)
        barra_de_rolagem.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._pintar_faixas()
        self.editor.bind("<<Modified>>", self._marcar_sujo)
        # O espelho dos interruptores segue o cursor. `<<Selection>>` não cobre a seta que anda sem
        # selecionar, e por isso as quatro estão aqui: um botão que diz "negrito" onde o texto não
        # é negrito é pior que um botão sem estado nenhum.
        for gatilho in ("<<Selection>>", "<ButtonRelease-1>", "<KeyRelease-Left>", "<KeyRelease-Right>"):
            self.editor.bind(gatilho, self._atualizar_ferramentas, add="+")
        self.editor.bind("<KeyRelease>", self._fechar_sequencia, add="+")
        self._ligar_teclas()

        rodape = ttk.Frame(self)
        rodape.pack(fill=tk.X, pady=(6, 0))
        texto_ui.acompanhar(ttk.Label(rodape, textvariable=self.status_var)).pack(side=tk.LEFT)

    def _interruptor_de_formato(self, pai: tk.Misc, acao: str) -> ttk.Checkbutton:
        """O botão de negrito, itálico ou sublinhado -- **e ele mostra o estado do cursor** (S-241).

        `Checkbutton` com estilo de botão, e não `Button`: o critério de aceite pede que o controle
        diga se o atributo já vale onde o cursor está, e um botão comum não tem onde dizê-lo. A
        variável é atualizada por `_atualizar_ferramentas`, que roda quando a seleção ou o cursor
        se movem -- ela é **espelho**, e não fonte: quem decide continua sendo `rico.vale_em_todo`.

        O rótulo vem do catálogo, como todo o resto desta barra (S-240): a varredura da S-219 olha
        `Checkbutton` também, e este é exatamente o caso que ela existe para pegar.
        """
        return ttk.Checkbutton(
            pai,
            text=comandos.rotulo_de_botao(acao),
            variable=self.formato_var[acao],
            style="Toolbutton",
            command=lambda: self.alternar(acao),
        )

    def _botao(self, pai: tk.Misc, acao: str, funcao: Callable[[], None]) -> ttk.Button:
        """Um botão da barra, **com o rótulo e a ênfase vindos do catálogo** (S-240).

        Nenhum `text=` escrito à mão sobra nesta aba, e é o critério de aceite do item: com três
        peles, o que não está no catálogo não aparece em nenhuma delas -- é a S-161 outra vez,
        *"o que não era botão não existia"*.
        """
        return ttk.Button(
            pai,
            text=comandos.rotulo_de_botao(acao),
            style=comandos.estilo(acao),
            command=funcao,
        )

    def _menu_de_cor(self, pai: tk.Misc, acao: str, ao_escolher: Callable[[str], None]) -> ttk.Menubutton:
        """O botão que abre a lista de cores do autor (S-242)."""
        botao = ttk.Menubutton(pai, text=comandos.rotulo_de_botao(acao))
        botao.configure(menu=self._lista_de_cores(botao, ao_escolher))
        return botao

    def _lista_de_cores(self, pai: tk.Misc, ao_escolher: Callable[[str], None]) -> tk.Menu:
        """A lista de cores do autor, para o botão da barra e para o item de menu (S-242).

        As cores saem de `rico.CORES_DE_AUTOR` pelo caminho de `ui/texto_cores.py`: nome no
        documento, papel na interface, hexadecimal em lugar nenhum. Um item por nome, mais
        "Limpar", que é o comando `limpar_cor` do catálogo -- e ele **não** tira a faixa.

        Uma função só para os dois clientes: duas listas divergiriam na primeira cor nova, que é o
        defeito que o catálogo de comandos tirou dos rótulos.
        """
        menu = tk.Menu(pai, tearoff=False)
        for nome in texto_cores.nomes():
            menu.add_command(label=nome.capitalize(), command=lambda n=nome: ao_escolher(n))
        menu.add_separator()
        menu.add_command(label=comandos.rotulo_de_botao("limpar_cor"), command=self.limpar_cor)
        return menu

    def escolher_cor(self) -> None:
        """Abre a lista de cores junto do ponteiro -- é por aqui que o item de menu entra."""
        self._abrir_lista_de_cores(self.pintar_letra)

    def escolher_realce(self) -> None:
        """O mesmo para o realce, que é o canal do autor (S-242)."""
        self._abrir_lista_de_cores(self.pintar_realce)

    def _abrir_lista_de_cores(self, ao_escolher: Callable[[str], None]) -> None:
        menu = self._lista_de_cores(self, ao_escolher)
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _ligar_teclas(self) -> None:
        """As três teclas de formato, e a guarda que o `Ctrl+I` obriga (S-241).

        Em `tk8.6/text.tcl:211`, `bind Text <Control-i>` insere **uma tabulação**. Quem ligar a
        tecla sem devolver `"break"` recebe as duas coisas: o itálico e o tab. `Ctrl+B` e `Ctrl+U`
        caem em `bind Text <Control-KeyPress> {# nothing}` e não têm o problema -- e é justamente
        por isso que as três devolvem `"break"` aqui: quem acrescentar a quarta não vai reler este
        parágrafo.

        As sequências saem de `atalhos.TECLAS_DO_EDITOR` e não de literais aqui: elas **não** são
        atalhos da janela -- só valem dentro deste widget --, mas a declaração de tecla mora num
        lugar só neste projeto, e é `ui/atalhos.py`. Ver o docstring de lá.
        """
        funcoes = {"negrito": self.negrito, "italico": self.italico, "sublinhado": self.sublinhado}
        for acao, sequencia in atalhos.TECLAS_DO_EDITOR.items():
            self.editor.bind(sequencia, lambda _e, f=funcoes[acao]: (f(), "break")[1])

    # -------------------------------------------------------------------------------- comandos

    def sincronizar_com_a_pagina(self) -> None:
        """Põe no campo a folha que o visualizador de PDF está mostrando.

        **É um botão e não um vínculo automático**, e a razão é o custo: virar a página do PDF é
        instantâneo, ler a folha com o glifo não é. Um vínculo dispararia uma leitura a cada rolagem
        -- e a aba de texto passaria a ser a razão de o programa ficar lento ao folhear.
        """
        self.folha_var.set(str(int(self._page_index()) + 1))

    def modo_bloco_mudou(self) -> None:
        """Diz no rodapé o que a próxima leitura vai custar (S-240).

        O comando **não** inverte a variável: quem a inverte é o widget que a carrega -- o
        `Checkbutton` da barra e o `checkbutton` do menu --, e inverter de novo aqui desfaria o
        clique. O que sobra para o comando é reagir, que é o mesmo desenho de `marcar_diagramas`.

        E reagir aqui é dizer o preço: o modo bloco custa ~40 s por folha contra ~1 s do glifo
        (`docs/metrics/texto_pagina.json`), e uma caixa marcada em silêncio é a explicação que
        falta quando a leitura seguinte demora quarenta vezes mais.
        """
        if bool(self.bloco_var.get()):
            self._on_status("Modo bloco ligado: a próxima leitura desta folha vai demorar mais.")
        else:
            self._on_status("Modo bloco desligado.")

    def folha_pedida(self) -> int:
        """O índice 0-based da folha no campo. `0` quando o campo não é um número."""
        try:
            return max(0, int(str(self.folha_var.get()).strip()) - 1)
        except ValueError:
            return 0

    def motor_pedido(self) -> MotorDeTexto:
        """O motor escolhido na caixa, ou `auto` se ela trouxer algo que não é motor.

        A caixa é `readonly`, então o valor de fora só chega por estado gravado de outra versão --
        e cair no primeiro da tupla é o certo: ele é o padrão do projeto, o classificador de casa.
        """
        escolhido = str(self.motor_var.get()).strip()
        return escolhido if escolhido in MOTORES else MOTORES[0]  # type: ignore[return-value]

    def ler(self) -> None:
        """Lê a folha pedida numa thread e desenha o resultado quando ele chega."""
        if self._lendo:
            self._on_status("Já há uma leitura em curso nesta aba.")
            return
        caminho = self._pdf_path()
        if caminho is None:
            # Rodapé e não caixa: é um passo que falta, e não uma escolha. Ver a tabela de
            # critérios em `tests/test_ui_retorno_modal.py`.
            self._on_status("Abra um PDF antes de ler o texto da folha.")
            return
        if self._sujo and not messagebox.askyesno(
            "Texto",
            "O texto desta aba foi editado. Ler de novo descarta as alterações. Continuar?",
            parent=self,
        ):
            return

        indice = self.folha_pedida()
        motor = self.motor_pedido()
        bloco = bool(self.bloco_var.get())
        self._lendo = True
        self.status_var.set(f"Lendo a folha {indice + 1}...")
        token = self._busy.register(
            f"Lendo o texto da folha {indice + 1}",
            loses_work=False,
            detail=f"motor {motor}" + (" · modo bloco" if bloco else ""),
        )

        def trabalhar() -> None:
            from ..text.leitor import ler_pagina

            try:
                pagina = ler_pagina(
                    caminho, indice, dpi=self._dpi, motor=motor, modo_bloco=bloco
                )
            except Exception as erro:  # noqa: BLE001 - a thread não pode derrubar a janela
                # **O nome tem de sair do `except` antes da lambda.** Em Python 3 o `as erro` é
                # apagado no fim do bloco, e uma lambda que o capturasse levantaria `NameError`
                # **dentro do `after`** -- isto é, na thread da janela, sobre um erro que já tinha
                # acontecido na outra. `ruff` pega isto como F821, e foi assim que apareceu.
                falha = erro
                logger.exception("Falha ao ler o texto da folha %d.", indice + 1)
                _na_janela(lambda: self._falhou(falha, token))
                return
            _na_janela(lambda: self._chegou(pagina, caminho, indice, token))

        def _na_janela(acao: Callable[[], None]) -> None:
            """Executa `acao` na thread da janela, e desiste em silêncio se ela já fechou.

            `after` é o mesmo caminho que a Galeria e a fila usam para voltar de uma thread. O que
            se acrescenta aqui é a guarda: fechar a aba durante uma leitura de 40 s destrói o
            widget, e um `after` sobre widget destruído levanta `TclError` **dentro da thread** --
            onde ninguém a pega, e o que se vê é um rastro no console de um programa que fechou
            normalmente.
            """
            try:
                self.after(0, acao)
            except (tk.TclError, RuntimeError):
                token.release()  # type: ignore[attr-defined]
                logger.debug("A aba de texto fechou antes de a leitura da folha voltar.")

        threading.Thread(target=trabalhar, name="leitura-de-texto", daemon=True).start()

    def _falhou(self, exc: Exception, token: object) -> None:
        token.release()  # type: ignore[attr-defined]
        self._lendo = False
        self.status_var.set(f"A folha não pôde ser lida: {exc}")
        self._on_status("A leitura de texto falhou; o motivo está no log.")

    def _chegou(self, pagina: PaginaLida, caminho: Path, indice: int, token: object) -> None:
        token.release()  # type: ignore[attr-defined]
        self._lendo = False
        self._pagina_rgb = self._renderizar(caminho, indice)
        self.desenhar(pagina)
        self._on_status(f"Folha {indice + 1} lida: {documento.resumo(pagina)}")

    def _renderizar(self, caminho: Path, indice: int):  # noqa: ANN202 - np.ndarray | None
        """A folha renderizada, de onde saem as miniaturas. `None` quando ela não pôde ser aberta."""
        try:
            from ..pdf_io import render_pdf_page

            return render_pdf_page(caminho, indice, dpi=self._dpi)
        except Exception as exc:  # noqa: BLE001 - miniatura é conforto, não função
            logger.debug("Sem imagem da folha %d para as miniaturas: %s", indice + 1, exc)
            return None

    # ---------------------------------------------------------------------------------- desenho

    def desenhar(self, pagina: PaginaLida) -> None:
        """Põe a página no editor. A ponte é `text/rico.de_pagina`, e é a única (S-235).

        Guardar a página aqui, e não só em `_chegou`, é o que faz `documento_atual` ter origem para
        devolver -- e o que permite desenhar uma página em teste sem simular a thread de leitura.
        """
        self._pagina = pagina
        self.desenhar_documento(rico.de_pagina(pagina))
        self.status_var.set(documento.resumo(pagina))
        # **Depois de desenhar, e não antes**: se a pessoa recusar a oferta, o que fica na tela é a
        # leitura que ela acabou de pedir (S-255).
        self.oferecer_rascunho(pagina)

    def desenhar_documento(self, doc: rico.DocumentoRico) -> None:
        """Desenha o documento -- venha ele de uma leitura ou de um arquivo (S-238).

        **Este laço não decide nada.** Faixa, ordem, separador e atributo já vieram decididos por
        `text/rico.py`; o que sobra aqui é `insert` e `image_create`. É a mesma fronteira que
        `text/documento.py` já mantinha, agora com o documento no meio -- e é ela que faz o negrito
        de uma corrida poder sobreviver ao arquivo, em vez de existir só enquanto o widget existir.
        """
        self._redesenhando = True
        try:
            self.editor.configure(state=tk.NORMAL)
            self._pintar_faixas()
            self.editor.delete("1.0", tk.END)
            self._imagens.clear()

            for corrida in doc.corridas:
                bloco = doc.bloco_de(corrida) if corrida.e_diagrama else None
                if isinstance(bloco, BlocoDeDiagrama):
                    self._inserir_miniatura(bloco)
                # **Toda corrida leva etiqueta, o separador inclusive.** Ele é indistinguível de
                # duas quebras digitadas à mão, e sem a etiqueta voltaria do widget como texto
                # comum -- o documento reaberto deixaria de ser igual ao salvo (S-238).
                self.editor.insert(tk.END, corrida.texto, self._etiquetas(corrida))

            # **Zera a pilha do Tk, e é obrigatório.** Ela guarda índices, não conteúdo: depois de
            # o texto inteiro ser trocado, desfazer apagaria um pedaço qualquer do texto novo.
            # Medido -- desligar `-undo` durante o redesenho não protege coisa nenhuma.
            self.editor.edit_reset()
            self.editor.edit_modified(False)
            self._sujo = False
        finally:
            self._redesenhando = False

    def _etiquetas(self, corrida: rico.Corrida) -> tuple[str, ...]:
        """As etiquetas do Tk desta corrida. A tabela mora em `ui/texto_etiquetas.py` (S-238).

        Ela saiu daqui porque a **volta** passou a existir: gravar precisa ler as etiquetas de novo,
        e duas tabelas -- uma para desenhar, outra para ler -- divergiriam no primeiro atributo novo.

        O que sobra aqui é a única etiqueta que **não** é documento: `NEGRITO_ITALICO`, que existe
        porque uma tag do Tk não sabe somar duas fontes. O par já está declarado nas duas etiquetas
        que vêm de lá, então `corrida_de` a ignora sozinha na volta -- ela não mapeia atributo nenhum.
        """
        etiquetas = texto_etiquetas.etiquetas_de(corrida)
        de_fonte = self._etiqueta_de_fonte(corrida)
        return (*etiquetas, de_fonte) if de_fonte else etiquetas

    def _inserir_miniatura(self, bloco: BlocoDeDiagrama) -> None:
        """A imagem do diagrama, **antes** da marca. Ver "O diagrama é desenhado no meio do texto".

        Só a imagem: `[Diagrama N]` é o texto da própria corrida, e quem o insere é o laço de
        `desenhar_documento`. Separar as duas é o que garante que a marca continue no texto mesmo
        quando não há folha renderizada de onde recortar a miniatura.
        """
        miniatura = self._miniatura(bloco)
        if miniatura is None:
            return
        self._imagens.append(miniatura)
        self.editor.image_create(tk.END, image=miniatura, padx=6, pady=4)
        # **Marcada como desenho, e não solta.** Esta quebra é para a marca cair embaixo da
        # miniatura -- ela não é do documento. Sem a etiqueta, ela voltaria como texto ao gravar e o
        # desenho seguinte acrescentaria outra: uma quebra a mais a cada salvar-e-reabrir (S-238).
        self.editor.insert(tk.END, "\n", (texto_etiquetas.DESENHO,))

    def _miniatura(self, bloco: BlocoDeDiagrama):  # noqa: ANN202 - tk.PhotoImage | None
        """O recorte do diagrama como imagem do Tk, ou `None` quando não há folha renderizada.

        O bbox do bloco está em **pontos** (ver `text/leitor._para_pontos`) e a folha em pixels; o
        fator entre os dois é o DPI com que ela foi renderizada, e é por isso que ele é o mesmo
        `self._dpi` dos dois lados. Usar outro aqui recortaria o lugar errado da folha em silêncio.
        """
        if self._pagina_rgb is None:
            return None
        try:
            from PIL import Image, ImageTk

            fator = self._dpi / 72.0
            altura, largura = self._pagina_rgb.shape[:2]
            x0 = max(0, int(bloco.bbox[0] * fator))
            y0 = max(0, int(bloco.bbox[1] * fator))
            x1 = min(largura, int(bloco.bbox[2] * fator))
            y1 = min(altura, int(bloco.bbox[3] * fator))
            if x1 <= x0 or y1 <= y0:
                return None
            recorte = Image.fromarray(self._pagina_rgb[y0:y1, x0:x1]).convert("RGB")
            recorte.thumbnail((LADO_DA_MINIATURA, LADO_DA_MINIATURA))
            # **`master=` e não o padrão**: sem ele a Pillow registra a imagem no *default root* do
            # `tkinter`, que não é necessariamente o interpretador deste widget. Com um `Tk` só --
            # o programa -- dá no mesmo; com dois, o `image_create` levanta
            # `TclError: image "pyimageN" doesn't exist`, porque a imagem nasceu no outro.
            return ImageTk.PhotoImage(recorte, master=self.editor)
        except Exception as exc:  # noqa: BLE001 - miniatura é conforto, não função
            logger.debug("Miniatura do diagrama %d não pôde ser feita: %s", bloco.indice + 1, exc)
            return None

    def _pintar_faixas(self) -> None:
        """Dá cor a cada faixa, a cada cor de autor e a cada realce, pelo papel deles em `tokens`.

        Chamado no desenho e não só na construção porque a paleta depende do tema, e o tema pode
        mudar com a janela aberta -- ver `ui/theme.py`. Uma cor resolvida uma vez ficaria com a do
        tema de quando a aba nasceu. **A cor do autor e a faixa se repintam juntas**, pelo mesmo
        caminho, que é critério de aceite da S-242.
        """
        for faixa, papel in PAPEL_DA_FAIXA.items():
            if papel:
                self.editor.tag_configure(faixa, foreground=tokens.cor(papel))
        self.editor.tag_configure("marca", foreground=tokens.cor(PAPEL_DA_MARCA))
        for nome in texto_cores.nomes():
            self.editor.tag_configure(
                texto_cores.etiqueta_de_cor(nome), foreground=tokens.cor(texto_cores.papel_de_cor(nome))
            )
            self.editor.tag_configure(
                texto_cores.etiqueta_de_realce(nome),
                background=tokens.cor(texto_cores.papel_de_realce(nome)),
            )
        # **A ordem importa, e o combinado vem por último.** No Tk a prioridade da tag é a ordem de
        # criação, e uma tag só pode dar *uma* fonte ao trecho: sem `NEGRITO_ITALICO` no fim, um
        # trecho com os dois sairia só itálico -- e o negrito que a S-237 leu da camada sumiria da
        # tela sem sumir do documento.
        self.editor.tag_configure("negrito", font=self._fonte(peso="bold"))
        self.editor.tag_configure("italico", font=self._fonte(pendor="italic"))
        self.editor.tag_configure(NEGRITO_ITALICO, font=self._fonte(peso="bold", pendor="italic"))
        self.editor.tag_configure("sublinhado", underline=True)
        self._pintar_estilos()

    def _pintar_estilos(self) -> None:
        """A geometria de cada estilo de parágrafo. **A fonte não entra aqui** (S-249).

        A etiqueta `estilo:X` leva recuo e espaço; a fonte vai numa etiqueta combinada, criada sob
        demanda em `_etiqueta_de_fonte`. Separá-las é o que permite um parágrafo de título ter uma
        palavra em negrito: no Tk **uma** etiqueta dá a fonte ao trecho, e a última criada vence --
        com a fonte na etiqueta do estilo, o negrito de dentro dele sumiria.
        """
        recuo = self._largura_do_recuo()
        for estilo in rico.ESTILOS:
            etiqueta = f"{texto_etiquetas.ATRIBUTO_COM_VALOR['estilo']}{estilo}"
            opcoes: dict[str, object] = {"lmargin1": 0, "lmargin2": 0, "spacing1": 0}
            if estilo == rico.ESTILO_PROSA:
                # Recuo de primeira linha, que é a diagramação que a S-199 mede na página.
                opcoes["lmargin1"] = recuo
            elif estilo == rico.ESTILO_TITULO:
                opcoes["spacing1"] = recuo
            elif estilo == rico.ESTILO_LEGENDA:
                opcoes["lmargin1"] = opcoes["lmargin2"] = recuo
            self.editor.tag_configure(etiqueta, **opcoes)
        self._fontes_desenhadas.clear()

    def _largura_do_recuo(self) -> int:
        """O recuo em pixels, **derivado da fonte do editor** e não cravado.

        Quatro espaços da fonte em uso: quem aumentou a fonte do Windows recebe um recuo maior,
        que é o que a S-147 impôs a toda medida desta interface."""
        try:
            return int(tkfont.Font(font=self.editor.cget("font")).measure("    "))
        except Exception as exc:  # noqa: BLE001 - widget sem janela ainda
            logger.debug("Recuo não derivado da fonte (%s): usando o do corpo.", exc)
            return 24

    def _etiqueta_de_fonte(self, corrida: rico.Corrida) -> str:
        """A etiqueta de **desenho** que dá a fonte a esta corrida, ou `""` quando não precisa.

        Uma etiqueta do Tk só pode dar **uma** fonte ao trecho, e três coisas a disputam: o estilo
        do parágrafo (corpo), o negrito e o itálico. A saída é a mesma da S-236 com
        `NEGRITO_ITALICO`, generalizada: uma etiqueta por combinação, criada sob demanda, e nenhuma
        delas mapeia atributo nenhum -- `corrida_de` as ignora sozinha na volta.
        """
        atributos = corrida.atributos
        estilo = atributos.estilo
        if not estilo:
            return NEGRITO_ITALICO if (atributos.negrito and atributos.italico) else ""
        nome = f"fonte:{estilo}:{'b' if atributos.negrito else ''}{'i' if atributos.italico else ''}"
        if nome not in self._fontes_desenhadas:
            papel = PAPEL_DO_ESTILO[estilo]
            base = theme.fonte_atual(papel, negrito=atributos.negrito)
            fonte = list(base) + (["italic"] if atributos.italico else [])
            self.editor.tag_configure(nome, font=tuple(fonte))
            self._fontes_desenhadas.add(nome)
        return nome

    def _fonte(
        self,
        *,
        peso: Literal["normal", "bold"] = "normal",
        pendor: Literal["roman", "italic"] = "roman",
    ) -> tkfont.Font | str:
        """A fonte do editor com outro peso ou outro pendor. Cai na do sistema se o Tk não responder.

        **Derivada da fonte do próprio editor**, e não cravada: quem aumentou a fonte do Windows tem
        de ver o negrito e o itálico no mesmo corpo do resto, e um nome de família fixo aqui
        ignoraria a escolha dele -- é a mesma razão de `ui/texto.largura_media_do_caractere`.
        """
        try:
            base = tkfont.Font(font=self.editor.cget("font")).actual()
            return tkfont.Font(
                family=str(base.get("family", "TkDefaultFont")),
                size=int(base.get("size", 0)),
                weight=peso,
                slant=pendor,
            )
        except Exception as exc:  # noqa: BLE001 - fonte exótica ou widget sem janela ainda
            logger.debug("Fonte %s/%s não derivada (%s): usando a do sistema.", peso, pendor, exc)
            partes = [p for p in ("TkDefaultFont", peso, pendor) if p not in ("normal", "roman")]
            return " ".join(partes)

    def _marcar_sujo(self, _evento: object = None) -> None:
        if self.editor.edit_modified():
            self._sujo = True
            self.editor.edit_modified(False)
            if not self._redesenhando:
                self._edicoes += 1
                self._agendar_rascunho()

    # ------------------------------------------------- deslocamento <-> índice do Tk (S-241)

    def deslocamento_de(self, indice: str) -> int:
        """O índice do Tk como deslocamento de caractere no documento. Ver o cabeçalho."""
        return texto_etiquetas.deslocamento(self.editor.dump("1.0", indice, text=True, tag=True))

    def indice_de(self, deslocamento: int) -> str:
        """O caminho de volta: deslocamento no documento -> índice do Tk.

        Percorre o despejo somando só o que é documento, e para no pedaço que contém o alvo. Sem
        isso, `f"1.0 + {n} chars"` erraria uma posição por diagrama da página -- a miniatura e a
        quebra do desenho contam para o Tk e não para o documento.
        """
        alvo = max(0, int(deslocamento))
        caminhado = 0
        abertas: set[str] = set()
        for item in self.editor.dump("1.0", tk.END, text=True, tag=True):
            chave, valor, indice = str(item[0]), str(item[1]), str(item[2])
            if chave == "tagon":
                abertas.add(valor)
            elif chave == "tagoff":
                abertas.discard(valor)
            elif chave == "text" and texto_etiquetas.DESENHO not in abertas:
                if caminhado + len(valor) >= alvo:
                    return f"{indice} + {alvo - caminhado} chars"
                caminhado += len(valor)
        return "end-1c"

    def intervalo_alvo(self) -> tuple[int, int]:
        """O intervalo em que a próxima ferramenta age: a seleção, ou a palavra sob o cursor.

        Quem decide é `rico.intervalo_alvo`, com o documento na mão -- aqui só se lê onde o cursor
        e a seleção estão. É a fronteira do cabeçalho: a regra de limite de palavra mora num lugar
        só, e ele não é este.
        """
        doc = self.documento_atual()
        try:
            inicio = self.deslocamento_de("sel.first")
            fim = self.deslocamento_de("sel.last")
        except tk.TclError:
            inicio = fim = self.deslocamento_de("insert")
        return rico.intervalo_alvo(doc, inicio, fim)

    # --------------------------------------------------------- as ferramentas de formato (S-241)

    def negrito(self) -> None:
        """Liga ou desliga o negrito no alvo. Ver `alternar`."""
        self.alternar("negrito")

    def italico(self) -> None:
        self.alternar("italico")

    def sublinhado(self) -> None:
        self.alternar("sublinhado")

    def alternar(self, atributo: str) -> None:
        """Alterna um atributo booleano no alvo -- **por etiqueta, sem redesenhar** (S-241).

        Quem decide ligar ou desligar é `rico.vale_em_todo`, sobre o documento: "vale em **todo** o
        intervalo?" e não "vale no primeiro caractere?". Selecionar uma frase cuja primeira palavra
        já está em negrito e apertar `Ctrl+B` tem de **completar** o negrito, e não apagá-lo.

        A escrita é `tag_add`/`tag_remove` porque nenhum caractere muda: assim o cursor fica onde
        estava, a rolagem não salta, e a pilha de desfazer do texto digitado continua inteira.
        """
        doc = self.documento_atual()
        inicio, fim = self.intervalo_alvo()
        if inicio == fim:
            return
        ligar = not rico.vale_em_todo(doc, inicio, fim, atributo)
        i0, i1 = self.indice_de(inicio), self.indice_de(fim)
        etiqueta = texto_etiquetas.ETIQUETA_DO_ATRIBUTO[atributo]
        (self.editor.tag_add if ligar else self.editor.tag_remove)(etiqueta, i0, i1)
        self._combinar_negrito_italico(i0, i1)
        self._carimbar_humano(i0, i1)
        self._depois_de_editar()

    def _combinar_negrito_italico(self, i0: str, i1: str) -> None:
        """Mantém a tag combinada em dia no intervalo. Ver `_pintar_faixas` sobre por que ela existe.

        Ela é **desenho e não documento** -- `corrida_de` a ignora na volta --, mas precisa
        acompanhar as duas de que depende: sem isto, ligar o negrito num trecho já itálico daria um
        trecho que o Tk desenha só em itálico, e a pessoa concluiria que o botão não funcionou.
        """
        self.editor.tag_remove(NEGRITO_ITALICO, i0, i1)
        deslocamento = self.deslocamento_de(i0)
        for corrida in self._corridas_entre(i0, i1):
            fim = deslocamento + len(corrida.texto)
            if corrida.atributos.negrito and corrida.atributos.italico:
                self.editor.tag_add(NEGRITO_ITALICO, self.indice_de(deslocamento), self.indice_de(fim))
            deslocamento = fim

    def _corridas_entre(self, i0: str, i1: str) -> tuple[rico.Corrida, ...]:
        """As corridas daquele trecho do widget, já traduzidas -- sem reconstruir o documento todo."""
        return texto_etiquetas.de_despejo(self.editor.dump(i0, i1, text=True, tag=True)).corridas

    def _carimbar_humano(self, i0: str, i1: str) -> None:
        """Troca a procedência do trecho por `humano` (S-239/S-241).

        Desmarcar à mão um itálico que a régua da S-236 detectou é uma **correção sobre o que o
        motor leu**, e é exatamente o tipo de informação que a fila da S-212 quer. Sem este
        carimbo, a marcação humana só apareceria quando o *texto* mudasse -- e o pincel manual
        seria invisível para o relatório.
        """
        for etiqueta in self.editor.tag_names():
            if etiqueta.startswith(texto_etiquetas.PREFIXO_DE_PROCEDENCIA):
                self.editor.tag_remove(etiqueta, i0, i1)
        self.editor.tag_add(f"{texto_etiquetas.PREFIXO_DE_PROCEDENCIA}humano", i0, i1)

    def limpar_formato(self) -> None:
        """Tira negrito, itálico e sublinhado do alvo. **Não** toca em cor nem em faixa."""
        inicio, fim = self.intervalo_alvo()
        if inicio == fim:
            return
        i0, i1 = self.indice_de(inicio), self.indice_de(fim)
        for atributo in ("negrito", "italico", "sublinhado"):
            self.editor.tag_remove(texto_etiquetas.ETIQUETA_DO_ATRIBUTO[atributo], i0, i1)
        self.editor.tag_remove(NEGRITO_ITALICO, i0, i1)
        self._carimbar_humano(i0, i1)
        self._depois_de_editar()

    def pintar_letra(self, nome: str) -> None:
        """Põe a cor do autor na **letra** do alvo (S-242)."""
        self._pintar(nome, texto_cores.etiqueta_de_cor, texto_cores.PREFIXO_DE_COR)

    def pintar_realce(self, nome: str) -> None:
        """Põe a cor do autor no **fundo** do alvo -- o canal que a confiança não usa (S-242)."""
        self._pintar(nome, texto_cores.etiqueta_de_realce, texto_cores.PREFIXO_DE_REALCE)

    def _pintar(self, nome: str, etiqueta_de: Callable[[str], str], prefixo: str) -> None:
        inicio, fim = self.intervalo_alvo()
        if inicio == fim:
            return
        i0, i1 = self.indice_de(inicio), self.indice_de(fim)
        # Uma cor por canal: a anterior sai antes de a nova entrar, senão o trecho carregaria duas
        # etiquetas do mesmo prefixo e a volta teria de escolher uma delas por desempate.
        for existente in self.editor.tag_names():
            if existente.startswith(prefixo):
                self.editor.tag_remove(existente, i0, i1)
        self.editor.tag_add(etiqueta_de(nome), i0, i1)
        self._carimbar_humano(i0, i1)
        self._depois_de_editar()

    def limpar_cor(self) -> None:
        """Tira a cor do autor -- letra e realce -- e **não** tira a faixa de confiança (S-242).

        A faixa é de outro dono: ela é a régua do reconhecimento, e apagá-la aqui esconderia que o
        motor estava adivinhando naquele trecho.
        """
        inicio, fim = self.intervalo_alvo()
        if inicio == fim:
            return
        i0, i1 = self.indice_de(inicio), self.indice_de(fim)
        for existente in self.editor.tag_names():
            if existente.startswith(texto_cores.PREFIXO_DE_COR) or existente.startswith(
                texto_cores.PREFIXO_DE_REALCE
            ):
                self.editor.tag_remove(existente, i0, i1)
        self._carimbar_humano(i0, i1)
        self._depois_de_editar()

    def _depois_de_editar(self) -> None:
        """O que toda ferramenta faz depois de escrever: marca sujo, conta a edição e espelha."""
        self._sujo = True
        self._edicoes += 1
        self._atualizar_ferramentas()

    def _atualizar_ferramentas(self, _evento: object = None) -> None:
        """Põe nos interruptores o que vale sob o cursor agora (S-241).

        Quem responde é `rico.vale_em_todo`, sobre o documento -- a mesma função que decide ligar ou
        desligar. Duas respostas para a mesma pergunta divergiriam, e a que ficaria errada seria a
        da tela, porque ninguém a testa.
        """
        try:
            doc = self.documento_atual()
            inicio, fim = self.intervalo_alvo()
        except tk.TclError:  # pragma: no cover - widget destruído entre o evento e o laço
            return
        for atributo, variavel in self.formato_var.items():
            variavel.set(inicio != fim and rico.vale_em_todo(doc, inicio, fim, atributo))

    # ------------------------------------------- a paleta e os estilos (S-246 a S-249)

    def alternar_paleta(self) -> None:
        """Abre ou fecha o painel lateral de glifos. **O foco não sai do texto** (S-248)."""
        if self._painel_da_paleta is not None:
            self._painel_da_paleta.destroy()
            self._painel_da_paleta = None
            self.editor.focus_set()
            return
        self._painel_da_paleta = self._montar_paleta(self._corpo)
        self._painel_da_paleta.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        self.editor.focus_set()

    def _montar_paleta(self, pai: tk.Misc) -> ttk.Frame:
        """As prateleiras, uma abaixo da outra, com um botão por símbolo.

        A prateleira "o modelo não lê" (S-247) é desenhada igual e **diz o que é**: inserir dali é
        permitido e marca a corrida, e esconder isso faria arquivos em que ninguém distingue o que
        foi lido do que foi inventado.
        """
        moldura = ttk.Frame(pai)
        for prateleira in self._paleta.prateleiras:
            grupo = ttk.LabelFrame(moldura, text=prateleira.nome)
            grupo.pack(fill=tk.X, pady=(0, 4))
            for k, simbolo in enumerate(prateleira.simbolos):
                # `takefocus=False` é o item: inserir com o painel aberto não pode tirar o cursor
                # do texto -- a próxima tecla tem de digitar no lugar em que se estava.
                ttk.Button(
                    grupo,
                    text=simbolo,
                    width=3,
                    takefocus=False,
                    command=lambda s=simbolo: self.inserir_simbolo(s),
                ).grid(row=k // 8, column=k % 8, padx=1, pady=1)
        return moldura

    def inserir_simbolo(self, simbolo: str) -> None:
        """Insere o símbolo no cursor, **marcando a corrida** se o modelo não o lê (S-247).

        A marca é `fora_do_modelo`, e ela viaja como etiqueta: sobrevive a salvar, reabrir e
        exportar, e é o que diz a quem receber o arquivo que aquele caractere não veio da página.
        """
        if not simbolo:
            return
        etiquetas: list[str] = []
        if self._paleta.marca(simbolo):
            etiquetas.append(texto_etiquetas.ETIQUETA_DO_ATRIBUTO["fora_do_modelo"])
        self.editor.insert(tk.INSERT, simbolo, tuple(etiquetas))
        self.editor.focus_set()
        self._depois_de_editar()

    def inserir_figurina(self) -> None:
        """Abre a lista de figurinas junto do ponteiro -- a porta de menu do mesmo gesto (S-248)."""
        self._menu_de_simbolos(_paleta.figurinas(self._paleta))

    def inserir_avaliacao(self) -> None:
        """O mesmo para os símbolos de avaliação."""
        self._menu_de_simbolos(_paleta.avaliacoes(self._paleta))

    def _menu_de_simbolos(self, simbolos: tuple[str, ...]) -> None:
        menu = tk.Menu(self, tearoff=False)
        for simbolo in simbolos:
            rotulo = f"{simbolo}  ·  fora do modelo" if self._paleta.marca(simbolo) else simbolo
            menu.add_command(label=rotulo, command=lambda s=simbolo: self.inserir_simbolo(s))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _fechar_sequencia(self, _evento: object = None) -> None:
        r"""Troca `\N` por `♘` **quando a sequência fecha** (S-248).

        Três regras, e as três são critério de aceite: a barra sozinha continua sendo barra; uma
        barra seguida de tecla que não abre sequência devolve os dois caracteres; e nada é trocado
        automaticamente enquanto se digita -- `Nf3` continua `Nf3`, porque a troca silenciosa sobre
        texto de OCR é o que a S-209 proíbe ao léxico com a frase que dá nome ao item.
        """
        if not self._sequencias:
            return
        maior = max(len(s) for s in self._sequencias) + len(ESCAPE_DA_PALETA)
        try:
            inicio = self.editor.index(f"insert - {maior} chars")
            trecho = self.editor.get(inicio, tk.INSERT)
        except tk.TclError:  # pragma: no cover - widget destruído entre a tecla e o laço
            return
        corte = trecho.rfind(ESCAPE_DA_PALETA)
        if corte < 0:
            return
        chave = trecho[corte + len(ESCAPE_DA_PALETA) :]
        simbolo = self._sequencias.get(chave)
        if simbolo is None:
            return
        quantos = len(chave) + len(ESCAPE_DA_PALETA)
        self.editor.delete(f"insert - {quantos} chars", tk.INSERT)
        self.inserir_simbolo(simbolo)

    def aplicar_estilo(self, estilo: str) -> None:
        """Põe o estilo no parágrafo do alvo e carimba `humano` (S-249).

        Quem decide o alcance é `rico.aplicar_estilo`: estilo é do **parágrafo**, e o parágrafo é o
        conjunto de corridas do mesmo bloco. Marcar meia frase marcaria meio parágrafo, e o desenho
        ficaria com dois corpos de fonte na mesma linha.

        Aqui o caminho é o do documento (e não o da etiqueta) porque o alcance passa das corridas
        tocadas: aplicar por etiqueta exigiria descobrir de novo, no widget, onde o bloco começa.
        """
        doc = self.documento_atual()
        inicio, fim = self.intervalo_alvo()
        novo = rico.aplicar_estilo(doc, inicio, fim, estilo)
        if novo == doc:
            return
        self._guardar_instantaneo(doc)
        self.desenhar_documento(novo)
        self._sujo = True
        self.mostrar_intervalo(inicio, fim)

    def estilo_titulo(self) -> None:
        self.aplicar_estilo(rico.ESTILO_TITULO)

    def estilo_prosa(self) -> None:
        self.aplicar_estilo(rico.ESTILO_PROSA)

    def estilo_notacao(self) -> None:
        self.aplicar_estilo(rico.ESTILO_NOTACAO)

    def estilo_legenda(self) -> None:
        self.aplicar_estilo(rico.ESTILO_LEGENDA)

    # ------------------------------------------------------------- achar e substituir (S-245)

    def achar(self) -> None:
        """Abre a janela de busca. Uma por vez -- reabrir traz a que já está aberta."""
        self._abrir_busca(substituindo=False)

    def substituir(self) -> None:
        """Abre a mesma janela, já com o campo de substituição à mostra."""
        self._abrir_busca(substituindo=True)

    def substituir_todos(self) -> None:
        """Abre a janela de busca no modo de confirmação: a lista antes da troca.

        **Não troca nada direto**, e é o item: `substituir todos` sobre uma página de OCR é a
        operação que apaga trabalho, e a S-76 é o registro do que custa um botão destrutivo que não
        parece um -- 1.405 diagramas sobrescritos por um clique.
        """
        self._abrir_busca(substituindo=True)

    def _abrir_busca(self, *, substituindo: bool) -> None:
        janela = self._janela_de_busca
        if janela is not None and janela.winfo_exists():
            janela.mostrar(substituindo=substituindo)
            return
        self._janela_de_busca = texto_busca.JanelaDeBusca(
            self,
            documento=self.documento_atual,
            ao_substituir=self.aplicar_substituicao,
            ao_mostrar=self.mostrar_intervalo,
            substituindo=substituindo,
        )

    def mostrar_intervalo(self, inicio: int, fim: int) -> None:
        """Rola até aquele trecho e o seleciona. É o que a lista da busca chama ao clicar."""
        i0, i1 = self.indice_de(inicio), self.indice_de(fim)
        self.editor.tag_remove(tk.SEL, "1.0", tk.END)
        self.editor.tag_add(tk.SEL, i0, i1)
        self.editor.mark_set(tk.INSERT, i0)
        self.editor.see(i0)
        self.editor.focus_set()

    def aplicar_substituicao(self, ocorrencias, novo: str) -> int:  # noqa: ANN001
        """Troca as ocorrências escolhidas e redesenha. Devolve quantas trocou.

        O instantâneo do documento anterior vai para a pilha **antes** do redesenho: é o que faz
        `desfazer` reverter a substituição **inteira**, e não troca a troca. Ver o cabeçalho sobre
        por que a pilha do Tk não serve para isto.
        """
        doc = self.documento_atual()
        novo_doc = busca.substituir(doc, ocorrencias, novo)
        if novo_doc.para_texto() == doc.para_texto():
            return 0
        self._guardar_instantaneo(doc)
        self.desenhar_documento(novo_doc)
        self._sujo = True
        return len(ocorrencias)

    # ------------------------------------------------------------------ desfazer e refazer (S-243)

    def _guardar_instantaneo(self, doc: rico.DocumentoRico) -> None:
        self._instantaneos.append((self._edicoes, doc))
        self._refeitos.clear()

    def desfazer(self) -> None:
        """Desfaz a última edição **deste** painel: primeiro a digitação, depois o documento.

        A ordem não é preferência: a pilha do Tk só tem o que foi digitado **depois** do último
        redesenho, então esgotá-la primeiro é o que devolve as coisas na ordem em que aconteceram.
        Quando ela acaba, o Tk levanta `TclError` -- e é aí que a substituição em massa é revertida.
        """
        try:
            self.editor.edit_undo()
            self._sujo = True
            return
        except tk.TclError:
            pass
        if not self._instantaneos:
            self._on_status("Não há mais nada para desfazer nesta aba.")
            return
        _, anterior = self._instantaneos.pop()
        self._refeitos.append(self.documento_atual())
        self.desenhar_documento(anterior)
        self._sujo = True

    def refazer(self) -> None:
        """Refaz o que o desfazer tirou, na mesma ordem invertida."""
        if self._refeitos:
            proximo = self._refeitos.pop()
            self._instantaneos.append((self._edicoes, self.documento_atual()))
            self.desenhar_documento(proximo)
            self._sujo = True
            return
        try:
            self.editor.edit_redo()
            self._sujo = True
        except tk.TclError:
            self._on_status("Não há nada para refazer nesta aba.")

    def contem(self, widget: object) -> bool:
        """Aquele widget é este painel ou está dentro dele? É como o foco escolhe o desfazível."""
        atual = widget
        for _ in range(40):
            if atual is None:
                return False
            if atual is self:
                return True
            atual = getattr(atual, "master", None)
        return False

    @property
    def edicao(self) -> int:
        """Quantas edições esta aba recebeu -- o critério de "o último editado" (S-243)."""
        return self._edicoes

    # ------------------------------------------------------------ o dono das ações (S-244)

    def acoes_proprias(self) -> frozenset[str]:
        """As ações globais que esta aba atende enquanto tem o foco. Ver `ACOES_PROPRIAS`."""
        return ACOES_PROPRIAS

    def atender(self, acao: str) -> Callable[[], None] | None:
        """A função desta aba para aquela ação, ou `None` se ela não a atende."""
        return {
            "salvar": self.salvar_documento,
            "desfazer": self.desfazer,
            "refazer": self.refazer,
            "achar": self.achar,
            "substituir": self.substituir,
        }.get(acao)

    # -------------------------------------------------------------- a exportação (S-250 a S-254)

    def exportar_md(self) -> None:
        """`.md` **porque ele diffa**: duas correções da mesma folha comparam linha a linha."""
        self._exportar(".md")

    def exportar_html(self) -> None:
        """`.html` **porque ele abre**: é o formato para mandar a folha corrigida para alguém."""
        self._exportar(".html")

    def exportar_rtf(self) -> None:
        """`.rtf` porque o Word abre -- e sem dependência nova nenhuma (S-252)."""
        self._exportar(".rtf")

    def _cores_do_html(self) -> dict[str, str]:
        """`classe do HTML -> hexadecimal`, resolvido **agora** contra o tema em uso (S-251).

        É a única vez em toda a spec do editor em que um hexadecimal é escrito num arquivo, e ele é
        **derivado**: `text/exportacao.py` não conhece uma cor sequer, e o teste afirma que nenhum
        literal de cor aparece lá.
        """
        cores = {
            f"cor-{nome}": tokens.cor(texto_cores.papel_de_cor(nome)) for nome in texto_cores.nomes()
        }
        cores.update(
            {f"realce-{nome}": tokens.cor(texto_cores.papel_de_realce(nome)) for nome in texto_cores.nomes()}
        )
        cores.update(
            {f"faixa-{faixa}": tokens.cor(papel) for faixa, papel in PAPEL_DA_FAIXA.items() if papel}
        )
        return cores

    def _exportar(self, extensao: str) -> None:
        """Pergunta o destino e exporta **fora da thread da janela** (S-254).

        O `.txt` de uma folha é imperceptível, e a aba estava certa em gravá-lo na thread da janela.
        Deixa de estar com o `.rtf` de imagens embutidas e com o PDF pesquisável, que abre o livro,
        escreve a camada e grava um arquivo novo -- e o molde para isso já existe duas vezes no
        programa: `ui/export_controller.py` e a leitura desta própria aba.
        """
        if self._exportando:
            self._on_status("Já há uma exportação em curso nesta aba.")
            return
        doc = self.documento_atual()
        if not doc.para_texto().strip():
            # Rodapé e não caixa: é um passo que falta, e não uma escolha (`test_ui_retorno_modal`).
            self._on_status("Não há texto nesta aba para exportar.")
            return
        formato = exportacao.formato_de(
            extensao, **({"cores": self._cores_do_html()} if extensao == ".html" else {})
        )
        destino = filedialog.asksaveasfilename(
            parent=self,
            title=f"Exportar o texto da folha para {formato.nome}",
            defaultextension=extensao,
            initialfile=arquivo.sugestao_de_nome(doc, extensao=extensao),
            filetypes=[(formato.nome, f"*{extensao}"), ("Todos", "*.*")],
        )
        if not destino:
            return
        self._exportar_em_thread(
            f"Exportando a folha para {formato.nome}",
            lambda: self._gravar_exportacao(doc, formato, Path(destino)),
        )

    def _gravar_exportacao(self, doc: rico.DocumentoRico, formato: object, destino: Path) -> str:
        relatorio = exportacao.exportar(doc, formato)  # type: ignore[arg-type]
        if self._cancelar_exportacao.is_set():
            return "Exportação cancelada: nada foi gravado."
        # **Atômica**: cancelar ou falhar no meio não deixa arquivo pela metade, que é a mesma
        # regra de `labels.csv` desde a S-111 -- o que está no disco é trabalho humano.
        exportacao.escrever(destino, relatorio)
        return exportacao.texto_do_relatorio(destino, relatorio, tamanho=destino.stat().st_size)

    def exportar_pdf_pesquisavel(self) -> None:
        """A folha com a camada de texto invisível, feita do que a pessoa corrigiu (S-253)."""
        if self._exportando:
            self._on_status("Já há uma exportação em curso nesta aba.")
            return
        doc = self.documento_atual()
        if doc.origem is None:
            self._on_status("O PDF pesquisável precisa da folha de origem: leia a folha primeiro.")
            return
        destino = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar a folha como PDF pesquisável",
            defaultextension=".pdf",
            initialfile=arquivo.sugestao_de_nome(doc, extensao=".pdf"),
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
        )
        if not destino:
            return

        def trabalhar() -> str:
            relatorio = pdf_pesquisavel.escrever(
                doc, Path(destino), seco=self._cancelar_exportacao.is_set()
            )
            return pdf_pesquisavel.texto_do_relatorio(relatorio)

        self._exportar_em_thread("Escrevendo a camada de texto da folha", trabalhar)

    def _exportar_em_thread(self, titulo: str, trabalho: Callable[[], str]) -> None:
        """O molde da S-254: thread para o trabalho, `after` para voltar, `BusyRegistry` no meio.

        **`loses_work=True`, ao contrário da leitura**: fechar no meio de uma exportação deixa
        trabalho pela metade, e o registro precisa dizer isso quando alguém tentar fechar a janela.
        """
        self._exportando = True
        self._cancelar_exportacao.clear()
        token = self._busy.register(
            titulo,
            loses_work=True,
            cancellable=True,
            cancel=self._cancelar_exportacao.set,
        )

        def rodar() -> None:
            try:
                relatorio = trabalho()
            except Exception as erro:  # noqa: BLE001 - a thread não pode derrubar a janela
                falha = erro
                logger.exception("Falha ao exportar o texto da folha.")
                _na_janela(lambda: self._exportou(f"A exportação falhou: {falha}", token))
                return
            _na_janela(lambda: self._exportou(relatorio, token))

        def _na_janela(acao: Callable[[], None]) -> None:
            """A mesma guarda da leitura: fechar a aba no meio não pode levantar dentro da thread."""
            try:
                self.after(0, acao)
            except (tk.TclError, RuntimeError):
                token.release()
                self._exportando = False
                logger.debug("A aba de texto fechou antes de a exportação voltar.")

        threading.Thread(target=rodar, name="escrita-de-texto", daemon=True).start()

    def _exportou(self, relatorio: str, token: object) -> None:
        token.release()  # type: ignore[attr-defined]
        self._exportando = False
        primeira = relatorio.splitlines()[0] if relatorio else ""
        self.status_var.set(relatorio.replace(chr(10), " · "))
        self._on_status(primeira or "Exportação concluída.")

    # ----------------------------------------------------------- o rascunho automático (S-255)

    def _agendar_rascunho(self) -> None:
        """Reagenda a gravação do rascunho para daqui a alguns segundos **de inatividade**.

        Reagendar a cada tecla é o item: um relógio fixo gravaria no meio da digitação e disputaria
        o disco com quem está trabalhando. Quem para de digitar tem o trabalho no disco alguns
        segundos depois; quem não parou não é interrompido.
        """
        if self._rascunho_agendado is not None:
            try:
                self.after_cancel(self._rascunho_agendado)
            except (tk.TclError, ValueError):  # pragma: no cover - agendamento já disparado
                pass
        try:
            self._rascunho_agendado = self.after(int(rascunho.ESPERA_SEGUNDOS * 1000), self.gravar_rascunho)
        except tk.TclError:  # pragma: no cover - aba destruída entre a tecla e o agendamento
            self._rascunho_agendado = None

    def gravar_rascunho(self) -> Path | None:
        """Grava o rascunho **se houver o que gravar**. Devolve o caminho, ou `None`.

        Só com o documento sujo: reescrever o mesmo arquivo a cada quatro segundos é desgaste de
        disco por nada, e a aba já rastreia a sujeira desde a S-238.
        """
        self._rascunho_agendado = None
        if not self._sujo or self._pagina is None:
            return None
        try:
            return rascunho.gravar(self.documento_atual(), pasta=self._pasta_de_rascunhos)
        except OSError as erro:  # noqa: BLE001 - rascunho é rede de segurança, não função
            logger.debug("Rascunho não pôde ser gravado: %s", erro)
            return None

    def oferecer_rascunho(self, pagina: PaginaLida) -> bool:
        """Se houver rascunho daquela folha, **oferece** recuperá-lo. Devolve se recuperou.

        Oferece e não aplica: sobrescrever o que a pessoa acabou de ler com um rascunho de ontem é
        o contrário do que ela quer. E recusar **não apaga** -- na próxima abertura a oferta volta.
        """
        achado = rascunho.achar(pagina.documento, pagina.pagina, pasta=self._pasta_de_rascunhos)
        if achado is None:
            return False
        if not messagebox.askyesno("Texto", rascunho.frase_de_recuperacao(achado), parent=self):
            return False
        try:
            doc = rascunho.carregar(achado)
        except (arquivo.ArquivoInvalido, OSError) as erro:
            logger.debug("Rascunho não abriu (%s): %s", achado.caminho, erro)
            self._on_status(f"O rascunho não pôde ser aberto: {erro}")
            return False
        self.abrir(doc)
        # Recuperado é trabalho que chegou a um lugar melhor -- a tela --, e o arquivo sai.
        rascunho.descartar(pagina.documento, pagina.pagina, pasta=self._pasta_de_rascunhos)
        self._on_status(f"Rascunho de {achado.data_legivel} recuperado.")
        return True

    # ----------------------------------------------------------------------------------- saída

    def texto_atual(self) -> str:
        """O que está no editor agora -- com as edições à mão, e não o que o OCR leu."""
        return self.editor.get("1.0", "end-1c")

    def documento_atual(self) -> rico.DocumentoRico:
        """O documento como ele está **na tela**, e não como a leitura o entregou (S-238).

        O widget é o estado vivo: faixa, atributo, bloco e procedência viajam como etiquetas do Tk,
        e é o `dump` que os devolve. A `PaginaLida` o widget não tem como devolver -- ela é a que
        está guardada aqui desde a leitura, e vai junto para que reabrir ainda tenha bbox e diagrama.
        """
        despejo = self.editor.dump("1.0", "end-1c", text=True, tag=True, image=True)
        bruto = texto_etiquetas.de_despejo(despejo, origem=self._pagina)
        # **A marcação é aplicada aqui, e não na gravação** (S-239): o que se salva, o que se exporta
        # e o que se conta no rodapé têm de ser o mesmo documento. Ela é derivada da `PaginaLida`, é
        # idempotente, e não toca no que o motor leu -- é a comparação com ele que a decide.
        return correcao.com_procedencia_humana(bruto)

    def salvar_documento(self) -> None:
        """Grava o `.cvtxt`: o texto, a formatação, a faixa, os diagramas e a página que os originou.

        **É este que fecha o ciclo**, e o `.txt` continua ao lado: quem quer colar o texto num e-mail
        quer o `.txt`, e quem quer voltar a corrigir amanhã quer este.
        """
        doc = self.documento_atual()
        if not doc.para_texto().strip():
            self._on_status("Não há texto nesta aba para salvar.")
            return
        destino = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar o texto da folha",
            defaultextension=arquivo.EXTENSAO,
            initialfile=arquivo.sugestao_de_nome(doc),
            filetypes=[(arquivo.NOME_DO_FORMATO, f"*{arquivo.EXTENSAO}"), ("Todos", "*.*")],
        )
        if not destino:
            return
        try:
            arquivo.gravar(Path(destino), doc)
        except OSError as erro:
            # Modal, e não rodapé: falha de gravação que ninguém vê é trabalho humano perdido em
            # silêncio, que é o critério declarado em `tests/test_ui_retorno_modal.py`.
            logger.exception("Falha ao gravar o documento em %s.", destino)
            messagebox.showerror("Texto", f"O arquivo não pôde ser gravado: {erro}", parent=self)
            return
        self._sujo = False
        # O trabalho chegou a um lugar melhor: o rascunho da S-255 sai.
        if self._pagina is not None:
            rascunho.descartar(
                self._pagina.documento, self._pagina.pagina, pasta=self._pasta_de_rascunhos
            )
        # A conta aparece porque a correção é o que o `.cvtxt` tem de mais caro -- e porque um
        # número no rodapé é o que faz alguém notar quando ele vem zerado (S-239).
        feitas = len(correcao.correcoes(doc))
        quanto = f" · {feitas} correção(ões) sobre o que o motor leu" if feitas else ""
        self._on_status(f"Texto gravado em {destino}{quanto}")

    def abrir_documento(self) -> None:
        """Abre um `.cvtxt` gravado antes, com os diagramas de volta se o livro ainda estiver lá."""
        if self._sujo and not messagebox.askyesno(
            "Texto",
            "O texto desta aba foi editado. Abrir outro arquivo descarta as alterações. Continuar?",
            parent=self,
        ):
            return
        origem = filedialog.askopenfilename(
            parent=self,
            title="Abrir texto de folha",
            filetypes=[(arquivo.NOME_DO_FORMATO, f"*{arquivo.EXTENSAO}"), ("Todos", "*.*")],
        )
        if not origem:
            return
        try:
            doc = arquivo.carregar(Path(origem))
        except (arquivo.ArquivoInvalido, OSError) as erro:
            logger.debug("Documento não abriu (%s): %s", origem, erro)
            messagebox.showerror("Texto", str(erro), parent=self)
            return
        self.abrir(doc)

    def abrir(self, doc: rico.DocumentoRico) -> None:
        """Põe o documento na tela e recupera o que só o PDF pode dar: as miniaturas.

        **O PDF ausente não é erro.** O texto abre igual, as miniaturas faltam, e o rodapé diz qual
        livro não foi encontrado -- a regra de degradação de `ui/theme.py`. O contrário faria uma
        pasta de trabalho movida de lugar bloquear o acesso ao que se corrigiu nela.
        """
        self._pagina = doc.origem
        self._pagina_rgb = None
        self._instantaneos.clear()
        self._refeitos.clear()
        aviso = ""
        caminho = arquivo.pdf_de(doc)
        if caminho is not None and doc.origem is not None:
            if caminho.exists():
                self._pagina_rgb = self._renderizar(caminho, doc.origem.pagina)
            else:
                aviso = f" · o livro {caminho.name} não está no lugar de antes: sem miniaturas"
        if doc.origem is not None:
            self.folha_var.set(str(doc.origem.pagina + 1))
        self.desenhar_documento(doc)
        resumo = documento.resumo(doc.origem) if doc.origem is not None else "texto sem página de origem"
        self.status_var.set(resumo + aviso)
        self._on_status(f"Texto aberto: {resumo}{aviso}")

    def salvar(self) -> None:
        """Grava o texto do editor num `.txt`, com o cabeçalho de procedência do `documento`.

        **Grava o que está na tela, e não a `PaginaLida`.** Se alguém corrigiu uma palavra, é a
        correção que tem valor -- é a única coisa nesta aba que não sai de graça de uma releitura.
        """
        conteudo = self.texto_atual().strip()
        if not conteudo:
            self._on_status("Não há texto nesta aba para salvar.")
            return
        sugestao = arquivo.sugestao_de_nome(self.documento_atual(), extensao=".txt")
        destino = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar o texto da folha",
            defaultextension=".txt",
            initialfile=sugestao,
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not destino:
            return
        cabecalho = ""
        if self._pagina is not None:
            cabecalho = documento.texto_para_arquivo(self._pagina).split("\n\n", 1)[0] + "\n\n"
        from ..atomic_io import atomic_write_text

        atomic_write_text(Path(destino), cabecalho + conteudo + "\n")
        self._sujo = False
        self._on_status(f"Texto gravado em {destino}")


__all__ = [
    "ACOES_PROPRIAS",
    "LADO_DA_MINIATURA",
    "MOTORES",
    "PAPEL_DA_FAIXA",
    "PAPEL_DA_MARCA",
    "TextoPanel",
]
