"""A aba que rola, e o piso que a torna suficiente (S-150, segunda metade).

**O defeito, fotografado.** Em 1100×760 com a aba Resultado aberta, a fila de ações do rodapé —
"Aplicar FEN", "Salvar posição reconhecida", "Salvar todos", "Corrigir Net", "2ª opinião" — é
cortada ao meio pela borda inferior, e **não há rolagem que a alcance**. Em 940×620, com o
Dataset, somem "Aplicar", "Limpar" e o botão "Remover".

O programa continua funcionando — `Ctrl+S` salva —, e é isso que torna o defeito difícil de
ver: ele não gera erro, gera um usuário que não sabe que existe um botão.

A primeira metade da S-150 pôs o piso (`ui/geometria.py`) e registrou o que faltava com todas as
letras: **a altura de 800 não cabe num notebook de 1366×768**. Um piso sozinho ou trava a janela
acima da tela ou devolve o botão cortado; é a rolagem que fecha a lacuna, e por isso as duas
metades são um item só.

**Por que não o `ScrolledFrame` do `ttkbootstrap`.** Ele existe e serviria — mas só quando a
biblioteca está instalada, e o contrato de degradação de `ui/theme.py` diz que sem ela a janela
abre igual. Um painel que rola com a biblioteca e corta sem ela é pior que os dois casos
consistentes, porque o defeito volta exatamente em quem tem o ambiente mais magro.

**A decisão é pura, o widget só executa.** Quanta altura o conteúdo recebe e se a barra aparece
são duas funções sem `tkinter`, afirmáveis nos três regimes (sobra, empata, falta) sem abrir
janela. É a regra da Fase 6 aplicada à aparência, e é ela que faz o critério de aceite caber num
`assertEqual`.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from . import abas, theme, tokens

logger = logging.getLogger(__name__)

__all__ = [
    "PASSO_DA_RODA",
    "AbaRolavel",
    "aba_rolavel",
    "altura_do_conteudo",
    "precisa_de_barra",
    "selecionar_aba",
]

PASSO_DA_RODA = 3
"""Unidades de canvas por giro. Três é o padrão do Windows, e o mesmo do visualizador de PDF."""


def altura_do_conteudo(pedida: int, viewport: int) -> int:
    """A altura que o conteúdo recebe dentro do canvas rolável. **Nunca menor que o viewport.**

    É a linha que separa "rolável" de "quebrado", e ela não é óbvia. Dentro de um canvas o
    `expand=True` de um filho deixa de significar "cresça até a janela": o contêiner não tem
    altura própria, então o tabuleiro do Resultado encolheria para o tamanho **pedido** pelo
    `tk.Canvas` — 265 px de fábrica — mesmo com a janela em 1080 de altura.

    Forçar o piso do viewport devolve o comportamento de hoje quando há espaço, e só então a
    rolagem entra. Sem isto, o item consertaria a janela pequena estragando a grande.
    """
    return max(int(pedida), int(viewport))


def precisa_de_barra(pedida: int, viewport: int) -> bool:
    """Se a barra vertical deve estar na tela.

    Aparece só quando falta espaço, e é decisão de produto: uma barra permanente rouba ~17 px
    de largura de um painel cujo `minsize` é 420, e ainda por cima anuncia rolagem onde não há
    — o que faz o usuário procurar conteúdo que não existe.
    """
    return int(pedida) > int(viewport)


class AbaRolavel(ttk.Frame):
    """Um `Frame` cujo conteúdo rola verticalmente quando não cabe. Monte dentro de `conteudo`.

    A barra é criada uma vez e **empacotada e desempacotada** conforme a necessidade, em vez de
    criada e destruída: destruir e recriar a cada `<Configure>` pisca durante o arrasto do
    divisor, que é justamente quando ela mais aparece e some.
    """

    def __init__(self, parent: tk.Misc, *, padding: int = 0) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            borderwidth=0,
            background=theme.cor_atual(tokens.SUPERFICIE_PADRAO),
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._barra = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._ao_rolar)
        self._barra_visivel = False

        self.conteudo = ttk.Frame(self.canvas, padding=padding)
        """Onde o painel se monta. É este `Frame` que rola, e não o `AbaRolavel`."""

        self._janela = self.canvas.create_window((0, 0), window=self.conteudo, anchor="nw")
        self._reavaliacao_agendada = False

        self.canvas.bind("<Configure>", lambda _evento: self._agendar_reavaliacao())
        self._ligar_reavaliacao_do_conteudo()
        self._ligar_roda()

    # ------------------------------------------------------------------------ geometria

    def _ligar_reavaliacao_do_conteudo(self) -> None:
        """Escuta `<Configure>` de **qualquer descendente**, e o motivo é sutil.

        A altura que decide tudo aqui é a **pedida** pelo conteúdo, e o Tk não emite evento
        quando ela muda: emite quando a altura *real* muda. Como esta classe **força** a altura
        real do `conteudo` (é o que faz o conteúdo curto preencher a aba), o `conteudo` deixa de
        emitir `<Configure>` exatamente nas duas transições que importam --

        - o conteúdo cresce além do viewport e a barra deveria **entrar**;
        - o conteúdo encolhe abaixo dele e a barra deveria **sair**.

        Foi assim que a primeira versão deste módulo ficou com a barra presa nos dois sentidos,
        e o teste que a pegou é o `test_a_barra_entra_e_sai_conforme_o_espaco`.

        Quem **de fato** emite é o descendente que mudou -- é a mudança dele que faz a altura
        pedida mudar. `bind_all` com filtro por prefixo do caminho Tk custa uma comparação de
        string por evento, e o `after_idle` junta a rajada de um arrasto de divisor numa
        reavaliação só.
        """
        prefixo = f"{self.conteudo!s}."
        self.bind_all(
            "<Configure>",
            lambda evento: self._agendar_reavaliacao() if str(evento.widget).startswith(prefixo) else None,
            add="+",
        )

    def _agendar_reavaliacao(self) -> None:
        """Junta a rajada de `<Configure>` de um arrasto numa reavaliação por ciclo ocioso."""
        if self._reavaliacao_agendada:
            return
        self._reavaliacao_agendada = True
        try:
            self.after_idle(self._reavaliar)
        except tk.TclError:  # pragma: no cover - widget destruído durante o evento
            self._reavaliacao_agendada = False

    def _reavaliar(self) -> None:
        """Reaplica a decisão das duas funções puras ao canvas."""
        self._reavaliacao_agendada = False
        try:
            largura, viewport = self.canvas.winfo_width(), self.canvas.winfo_height()
            pedida = self.conteudo.winfo_reqheight()
        except tk.TclError:  # pragma: no cover - widget destruído durante o evento
            return
        altura = altura_do_conteudo(pedida, viewport)
        self.canvas.itemconfigure(self._janela, width=largura, height=altura)
        self.canvas.configure(scrollregion=(0, 0, largura, altura))
        self._mostrar_barra(precisa_de_barra(pedida, viewport))

    def _mostrar_barra(self, visivel: bool) -> None:
        if visivel == self._barra_visivel:
            return
        if visivel:
            self._barra.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            self._barra.pack_forget()
            self.canvas.yview_moveto(0.0)
        self._barra_visivel = visivel

    def _ao_rolar(self, inicio: float, fim: float) -> None:
        self._barra.set(inicio, fim)

    # ----------------------------------------------------------------------------- roda

    def _ligar_roda(self) -> None:
        """A roda vem da janela inteira, e não deste canvas — pelo motivo da S-68.

        No Windows o `<MouseWheel>` vai para o widget com **foco**, não para o que está sob o
        ponteiro: ligada só aqui, a roda não rolaria a aba enquanto o cursor de texto estivesse
        no campo de FEN. É a mesma conclusão que `ui/pdf_panel.py` já tinha tirado, e por isso
        a mesma solução — `bind_all` mais um retângulo comparado com as coordenadas do widget.

        **`add="+"` nos dois lados, e é isso que faz os dois conviverem.** `bind_all` sem ele
        *substitui* a ligação anterior da mesma sequência: o visualizador de PDF é construído
        depois das abas e apagaria esta em silêncio — roda funcionando na página e morta na aba
        ao lado, sem erro nenhum a que se agarrar.
        """
        raiz = self.winfo_toplevel()
        raiz.bind_all("<MouseWheel>", self._na_roda, add="+")
        # X11 não tem `MouseWheel`: a roda são os botões 4 e 5, sem delta.
        raiz.bind_all("<Button-4>", lambda evento: self._na_roda(evento, delta=120), add="+")
        raiz.bind_all("<Button-5>", lambda evento: self._na_roda(evento, delta=-120), add="+")

    def _sob_o_ponteiro(self, evento: tk.Event) -> bool:
        """Se o ponteiro está sobre este canvas. Aritmética, e não `winfo_containing`.

        O motivo é o medido na S-68: no Windows `winfo_containing` resolve pelo
        `WindowFromPoint` do sistema e devolve `None` quando qualquer outra janela cobre aquele
        ponto da tela — inclusive um tooltip do próprio programa.
        """
        if not self.canvas.winfo_exists() or not self.canvas.winfo_ismapped():
            return False
        x = int(evento.x_root) - self.canvas.winfo_rootx()
        y = int(evento.y_root) - self.canvas.winfo_rooty()
        return 0 <= x < self.canvas.winfo_width() and 0 <= y < self.canvas.winfo_height()

    def _na_roda(self, evento: tk.Event, *, delta: int | None = None) -> str | None:
        """Rola, **e só quando há o que rolar**.

        Sem barra na tela não há rolagem a fazer, e devolver `"break"` aqui engoliria a roda de
        quem estivesse por baixo. É a diferença entre "esta aba não rola" e "a roda parou de
        funcionar nesta aba"."""
        if not self._barra_visivel or not self._sob_o_ponteiro(evento):
            return None
        movimento = delta if delta is not None else int(getattr(evento, "delta", 0))
        if not movimento:
            return None
        self.canvas.yview_scroll(-PASSO_DA_RODA if movimento > 0 else PASSO_DA_RODA, "units")
        return "break"


def selecionar_aba(notebook: ttk.Notebook, rotulo: str) -> bool:
    """Seleciona a aba com este rótulo. Devolve se ela existia (S-156).

    **Por rótulo e não por índice**, porque índice não sobrevive a reordenar as abas — e a
    S-162 é, literalmente, reordená-las. Um rótulo que não existe mais deixa a janela na aba em
    que ela já estava, que é o mesmo comportamento de não haver nada guardado.

    Devolve booleano em vez de silenciar: quem restaura estado precisa poder registrar que o
    guardado não valia mais.
    """
    if not rotulo:
        return False
    procurado = abas.nome_base(rotulo)
    try:
        for indice in range(int(notebook.index("end"))):
            # Pelo **nome**, e não pelo rótulo inteiro: desde a S-162 ele carrega a contagem, e
            # "Revisão (129)" guardado não casaria com "Revisão (54)" na sessão seguinte -- a
            # janela cairia na primeira aba sem nada dizer.
            if abas.nome_base(str(notebook.tab(indice, "text"))) == procurado:
                notebook.select(indice)
                return True
    except tk.TclError as exc:  # pragma: no cover - notebook destruído no meio da restauração
        logger.debug("Aba %r não selecionada: %s", rotulo, exc)
    return False


def aba_rolavel(notebook: ttk.Notebook, texto: str, *, padding: int = 0) -> ttk.Frame:
    """Adiciona ao `notebook` uma aba rolável e devolve **o pai** em que montar o conteúdo.

    A aba já entra no `notebook` aqui: quem chama recebe um `Frame` e monta dentro dele como
    montaria dentro do próprio `Notebook`, sem precisar lembrar de adicionar o hospedeiro
    depois. É a diferença entre a rolagem ser um detalhe de como se abre uma aba e ser uma
    estrutura que cada chamador reconstrói igual — e que o primeiro esquecido reconstrói
    diferente.

    **Quais abas rolam, e por que não todas.** Resultado, Configuração e Galeria são as de
    altura mínima real — as três em que a fila de ações fica abaixo de um tabuleiro ou de uma
    lista de campos. Dataset e Revisão ficam de fora porque a altura delas é a do `Treeview`,
    que já rola por conta própria; Análise, porque o tabuleiro dela ocupa o que sobrar por
    construção. Rolagem dentro de rolagem é um gesto ambíguo: o mesmo giro de roda tem dois
    destinos possíveis e o usuário não vê qual dos dois vai responder.
    """
    host = AbaRolavel(notebook, padding=padding)
    notebook.add(host, text=texto)
    return host.conteudo
