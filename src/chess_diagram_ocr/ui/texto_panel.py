"""A aba de texto: a página inteira num editor, com os diagramas onde eles estão (S-211).

**O que ela é, em uma frase: a `PaginaLida` na tela, editável.** O resto do programa trabalha
diagrama a diagrama -- o Resultado abre o tabuleiro clicado, a Revisão enfileira os duvidosos, a
Galeria lista o livro. Nenhuma dessas abas mostra o *texto* da página, e por isso a única forma de
conferir o que o OCR leu era abrir o JSON.

**Quase nada é decidido aqui.** Onde o diagrama entra no fluxo, o que merece destaque e o que vai
para o arquivo são de `text/documento.py`, que não importa `tkinter` e é onde os testes moram.
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

from ..text import arquivo, correcao, documento, rico
from ..text.pagina import BlocoDeDiagrama, PaginaLida
from . import estilos, texto_etiquetas, tokens
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
peça papel nenhum: pintá-lo de preto é o que quebraria o tema escuro."""

PAPEL_DA_MARCA = tokens.TEXTO_SECUNDARIO
"""A cor de `[Diagrama N]`. Secundário porque a marca é referência, e não texto do livro."""

NEGRITO_ITALICO = "negrito_italico"
"""A tag que desenha os dois juntos. **É desenho, e não documento** -- ver `_etiquetas` (S-236)."""

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

        self.folha_var = tk.StringVar(value="1")
        self.motor_var = tk.StringVar(value=MOTORES[0])
        self.bloco_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Abra um PDF e clique em Ler folha.")

        self._montar()

    # ------------------------------------------------------------------------------ construção

    def _montar(self) -> None:
        # `BarraFluida` e não `Frame`: com "Abrir" e "Salvar" a fila passou de oito para dez itens
        # (S-238), e `pack(side=LEFT)` numa linha só **não desenha** o que passa da borda -- sem
        # aviso e sem reticências, que é o defeito medido pela S-151.
        barra = BarraFluida(self)
        barra.pack(fill=tk.X, pady=(0, 6))

        barra.adicionar(ttk.Label(barra, text="Folha"))
        barra.adicionar(
            ttk.Spinbox(barra, from_=1, to=99999, width=7, textvariable=self.folha_var)
        )
        barra.adicionar(
            ttk.Button(barra, text="Da página aberta", command=self.sincronizar_com_a_pagina)
        )

        barra.adicionar(ttk.Label(barra, text="Motor"))
        barra.adicionar(
            ttk.Combobox(
                barra, values=MOTORES, textvariable=self.motor_var, width=8, state="readonly"
            )
        )

        barra.adicionar(
            ttk.Checkbutton(barra, text="Modo bloco (lento)", variable=self.bloco_var)
        )

        barra.adicionar(
            ttk.Button(
                barra,
                text="Ler folha",
                style=estilos.estilo_de_botao(estilos.PRIMARIO),
                command=self.ler,
            )
        )
        barra.adicionar(ttk.Button(barra, text="Abrir…", command=self.abrir_documento))
        barra.adicionar(ttk.Button(barra, text="Salvar", command=self.salvar_documento))
        barra.adicionar(ttk.Button(barra, text="Salvar .txt", command=self.salvar))

        corpo = ttk.Frame(self)
        corpo.pack(fill=tk.BOTH, expand=True)
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

        rodape = ttk.Frame(self)
        rodape.pack(fill=tk.X, pady=(6, 0))
        texto_ui.acompanhar(ttk.Label(rodape, textvariable=self.status_var)).pack(side=tk.LEFT)

    # -------------------------------------------------------------------------------- comandos

    def sincronizar_com_a_pagina(self) -> None:
        """Põe no campo a folha que o visualizador de PDF está mostrando.

        **É um botão e não um vínculo automático**, e a razão é o custo: virar a página do PDF é
        instantâneo, ler a folha com o glifo não é. Um vínculo dispararia uma leitura a cada rolagem
        -- e a aba de texto passaria a ser a razão de o programa ficar lento ao folhear.
        """
        self.folha_var.set(str(int(self._page_index()) + 1))

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

    def desenhar_documento(self, doc: rico.DocumentoRico) -> None:
        """Desenha o documento -- venha ele de uma leitura ou, um dia, de um arquivo (S-238).

        **Este laço não decide nada.** Faixa, ordem, separador e atributo já vieram decididos por
        `text/rico.py`; o que sobra aqui é `insert` e `image_create`. É a mesma fronteira que
        `text/documento.py` já mantinha, agora com o documento no meio -- e é ela que faz o negrito
        de uma corrida poder sobreviver ao arquivo, em vez de existir só enquanto o widget existir.
        """
        self.editor.configure(state=tk.NORMAL)
        self._pintar_faixas()
        self.editor.delete("1.0", tk.END)
        self._imagens.clear()

        for corrida in doc.corridas:
            bloco = doc.bloco_de(corrida) if corrida.e_diagrama else None
            if isinstance(bloco, BlocoDeDiagrama):
                self._inserir_miniatura(bloco)
            # **Toda corrida leva etiqueta, o separador inclusive.** Ele é indistinguível de duas
            # quebras digitadas à mão, e sem a etiqueta voltaria do widget como texto comum -- o
            # documento reaberto deixaria de ser igual ao salvo (S-238).
            self.editor.insert(tk.END, corrida.texto, self._etiquetas(corrida))

        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self._sujo = False

    def _etiquetas(self, corrida: rico.Corrida) -> tuple[str, ...]:
        """As etiquetas do Tk desta corrida. A tabela mora em `ui/texto_etiquetas.py` (S-238).

        Ela saiu daqui porque a **volta** passou a existir: gravar precisa ler as etiquetas de novo,
        e duas tabelas -- uma para desenhar, outra para ler -- divergiriam no primeiro atributo novo.

        O que sobra aqui é a única etiqueta que **não** é documento: `NEGRITO_ITALICO`, que existe
        porque uma tag do Tk não sabe somar duas fontes. O par já está declarado nas duas etiquetas
        que vêm de lá, então `corrida_de` a ignora sozinha na volta -- ela não mapeia atributo nenhum.
        """
        etiquetas = texto_etiquetas.etiquetas_de(corrida)
        if corrida.atributos.negrito and corrida.atributos.italico:
            return (*etiquetas, NEGRITO_ITALICO)
        return etiquetas

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
        """Dá cor a cada faixa pelo papel dela em `ui/tokens.py`.

        Chamado no desenho e não só na construção porque a paleta depende do tema, e o tema pode
        mudar com a janela aberta -- ver `ui/theme.py`. Uma cor resolvida uma vez ficaria com a do
        tema de quando a aba nasceu.
        """
        for faixa, papel in PAPEL_DA_FAIXA.items():
            if papel:
                self.editor.tag_configure(faixa, foreground=tokens.cor(papel))
        self.editor.tag_configure("marca", foreground=tokens.cor(PAPEL_DA_MARCA))
        # **A ordem importa, e o combinado vem por último.** No Tk a prioridade da tag é a ordem de
        # criação, e uma tag só pode dar *uma* fonte ao trecho: sem `NEGRITO_ITALICO` no fim, um
        # trecho com os dois sairia só itálico -- e o negrito que a S-237 leu da camada sumiria da
        # tela sem sumir do documento.
        self.editor.tag_configure("negrito", font=self._fonte(peso="bold"))
        self.editor.tag_configure("italico", font=self._fonte(pendor="italic"))
        self.editor.tag_configure(NEGRITO_ITALICO, font=self._fonte(peso="bold", pendor="italic"))

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


__all__ = ["LADO_DA_MINIATURA", "MOTORES", "PAPEL_DA_FAIXA", "PAPEL_DA_MARCA", "TextoPanel"]
