"""A paleta de comandos: um campo, uma lista filtrada, Enter executa (S-231).

**O problema é de quantidade, e ele nasceu com a terceira pele.** A pele "Foco" tira 23 controles
da tela e os põe no menu (S-223). Cinco menus com 27 itens já é um mapa que se decora; 50 itens é
um mapa em que se procura -- e procurar comando em menu é a S-161 ao contrário: *"o que não era
botão não existia"* vira *"o que não está no menu que eu abri, eu não acho"*.

**O item é barato porque o catálogo da S-219 já é a lista.** Rótulo, grupo, tecla e ordem estão
todos lá; o que faltava eram o filtro e a janela. Ninguém escreve comando aqui: acrescentar uma
linha a `comandos.CATALOGO` acrescenta uma linha à paleta, como já acontece com a fila e a fita.

**O filtro é puro, e é a metade que importa.** `filtrar` é `(consulta, entradas) → entradas`, sem
`tkinter` e sem estado -- afirmável sem abrir janela, como `tabela.ancora` e
`comandos.fila_de_destaque`. A janela lá embaixo só desenha o que ele devolve, e é por isso que os
casos difíceis (o acento, o empate, o comando desabilitado) têm teste sem `Tk` nenhum.

**O nome do módulo é longo de propósito.** Neste programa `paleta` já é duas coisas -- a paleta de
peças do editor (`ui/board_widget.py`) e a paleta de cores (`tokens.paleta`) --, e uma terceira
seria a ambiguidade que `ui/menu.py` registra ao apelidar o próprio import: duas coisas com o
mesmo nome no mesmo arquivo é como se lê a errada.

**O que a paleta não é: o mapa da janela.** Ela é atalho para quem sabe o nome. A afirmação de que
todo comando tem casa em toda pele é da S-233 -- e é por isso que a paleta **não** conta para o
inventário de lá: se contasse, aquele teste passaria por construção e não mediria nada.
"""

from __future__ import annotations

import tkinter as tk
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from tkinter import ttk

from . import atalhos, comandos, menu, tabela, theme, tipografia, tokens

__all__ = [
    "ALTURA_EM_LINHAS",
    "COLUNAS",
    "MOTIVO_NA_LINHA_DE_CAMPO",
    "MOTIVO_SEM_FUNCAO",
    "MOTIVO_SUBMENU",
    "TITULO",
    "Entrada",
    "JanelaDaPaleta",
    "abrir",
    "filtrar",
    "inventario",
    "motivos_declarados",
]

TITULO = "Paleta de comandos"

MOTIVO_SEM_FUNCAO = "esta janela não amarra este comando a nenhuma função"
"""A resposta padrão para o comando que o catálogo declara e a janela não liga a nada.

Não é falha: `_comandos` de `app_tkinter` é montado com os painéis, e um roteiro que sobe a janela
sem eles amarra menos. O que a paleta não pode fazer é **sumir** com a linha -- ver `Entrada`."""

MOTIVO_SUBMENU = "é um submenu: a escolha está na barra de menus"
"""Abrir recente, Aparência e Densidade. Os três têm função amarrada e nenhuma delas é executável
daqui: a primeira monta uma lista de livros na hora de abrir o menu; as outras duas aplicam o
`StringVar` que o `radiobutton` acabou de mudar, e disparadas sem esse gesto reaplicam o que já
vale. **A lista cresceu sozinha na S-232**, que é o que `motivos_declarados` prometia: o motivo
sai do `tipo` do item em `menu.MENUS`, e ninguém veio aqui acrescentar "densidade"."""

MOTIVO_NA_LINHA_DE_CAMPO = "fica na linha de conjunto de campo, junto da página exibida"
"""Os três da S-77, e a razão de eles não terem item de menu é a mesma de não terem paleta: eles
anotam *aquela* página, e um comando que age sobre a página exibida sem que ela esteja à vista é o
gesto que grava verdade de referência errada."""


def motivos_declarados() -> dict[str, str]:
    """`ação → por que a paleta não a executa`, para o que **não** é falta de amarração.

    **Nenhum dos dois grupos é escrito aqui pela segunda vez.** Quem sabe que os três de anotação
    moram na linha de campo é `comandos.NA_LINHA_DE_CAMPO`; quem sabe que "Abrir recente" e
    "Aparência" são submenus é `ui/menu.py`, pelo `tipo` do item. Uma cópia dessas listas neste
    módulo seria a divergência que a S-219 veio fechar -- e ela apareceria no dia em que alguém
    acrescentasse o terceiro submenu.
    """
    submenus = (menu.RECENTES, menu.APARENCIA, menu.DENSIDADE)
    declarados = dict.fromkeys(comandos.NA_LINHA_DE_CAMPO, MOTIVO_NA_LINHA_DE_CAMPO)
    declarados.update(
        {item.acao: MOTIVO_SUBMENU for declarado in menu.MENUS for item in declarado.itens if item.tipo in submenus}
    )
    return declarados


@dataclass(frozen=True)
class Entrada:
    """Uma linha da paleta: o comando e, quando ela está cinza, **por quê**.

    **O motivo e o estado são o mesmo campo, e isso é o critério de aceite virado forma.** A spec
    pede que o comando desabilitado apareça *"cinza e com o motivo, e não some"*; com dois campos
    daria para construir uma entrada desabilitada e muda, e alguém construiria. Aqui não há como:
    `habilitado` é `not motivo`, então quem desabilita é obrigado a dizer por quê.

    **E não some porque sumir é o defeito que a S-165 mediu**: 13 controles sem tooltip, e a
    pessoa concluindo que o programa não faz aquilo. Uma paleta que esconde o comando indisponível
    responde "não existe" a uma pergunta que era "por que não posso agora?".
    """

    comando: comandos.Comando
    motivo: str = ""

    @property
    def habilitado(self) -> bool:
        return not self.motivo

    @property
    def acao(self) -> str:
        return self.comando.acao

    @property
    def rotulo(self) -> str:
        """O rótulo longo, o do menu. O curto é do botão, e aqui não há botão."""
        return self.comando.rotulo

    @property
    def grupo(self) -> str:
        """O grupo como a pessoa o lê -- "Visualização", e não `"VISUALIZACAO"`."""
        return comandos.rotulo_do_grupo(self.comando.grupo)

    @property
    def tecla(self) -> str:
        """O acelerador, ou `""`. Vem da mesma tabela que liga a tecla (`ui/atalhos.py`)."""
        return atalhos.acelerador(self.acao)

    @property
    def no_texto(self) -> str:
        """O que a coluna do comando mostra: o rótulo, e o motivo junto quando há um."""
        return f"{self.rotulo} — {self.motivo}" if self.motivo else self.rotulo


def _em_ordem_de_grupo() -> tuple[comandos.Comando, ...]:
    """O catálogo inteiro, agrupado na ordem de `comandos.GRUPOS`.

    Percorrer os grupos em vez de devolver `CATALOGO` direto **não** muda a ordem hoje -- o
    catálogo já é declarado assim, e há teste afirmando os dois iguais. Muda o que acontece no dia
    em que alguém acrescentar um comando no fim do arquivo: aqui ele cai no grupo dele, e não numa
    sétima faixa sem cabeçalho no pé da lista.
    """
    return tuple(registro for grupo in comandos.GRUPOS for registro in comandos.do_grupo(grupo))


def inventario(
    amarrados: Mapping[str, object] | None = None,
    *,
    motivos: Mapping[str, str] | None = None,
) -> tuple[Entrada, ...]:
    """Uma entrada por comando do catálogo, em ordem de grupo. **Sempre o catálogo inteiro.**

    `amarrados` é o mapa `ação → função` da janela; o que não estiver nele vira linha cinza com
    `MOTIVO_SEM_FUNCAO`. `None` -- o padrão -- é "não perguntei", e devolve tudo habilitado: é o
    que o teste do filtro quer, e não vale como afirmação sobre a janela.

    `motivos` sobrepõe os declarados, para quem sabe de um caso que este módulo não pode saber. O
    motivo declarado **ganha da amarração**: `aparencia` tem função ligada e mesmo assim não é
    executável daqui, e mostrá-la preta seria prometer um clique que não faz nada.
    """
    declarados = motivos_declarados()
    declarados.update(motivos or {})
    ligados = None if amarrados is None else set(amarrados)

    entradas: list[Entrada] = []
    for registro in _em_ordem_de_grupo():
        razao = declarados.get(registro.acao, "")
        if not razao and ligados is not None and registro.acao not in ligados:
            razao = MOTIVO_SEM_FUNCAO
        entradas.append(Entrada(registro, motivo=razao))
    return tuple(entradas)


def _dobrado(texto: str) -> str:
    """Minúscula, sem acento e sem espaço: como a consulta e o rótulo se comparam.

    **Sem acento** porque quem digita "pagina" quer "Ler esta página", e cobrar o acento para
    achar um comando é o teclado pedindo pedágio -- num programa cujos rótulos têm `ç`, `ã` e `é`
    em quinze linhas do catálogo.

    **Sem espaço** porque a consulta é uma subsequência: exigir que o espaço de "ler pag" casasse
    com um espaço do rótulo faria `"lerpag"` achar mais que `"ler pag"`, que é o contrário do que
    quem digita espera.
    """
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(
        letra for letra in decomposto if not unicodedata.combining(letra) and not letra.isspace()
    ).casefold()


def _casamento(agulha: str, palheiro: str) -> tuple[int, int] | None:
    """Onde a consulta cabe como subsequência: `(início, vão)`. `None` quando não cabe.

    **Guloso e da esquerda para a direita**, e não o casamento mais apertado que existe: cada
    letra vai na primeira posição livre que a aceita. É o que torna a função previsível de ler e
    barata de rodar -- e o vão que ela devolve é do casamento que ela achou, que é o que a ordem
    usa para separar "apertado" de "espalhado".

    O vão é `última - primeira`: `"lp"` casa em "Limpar o tabuleiro" com vão 3 e em "Ler esta
    página" com vão 12, e é o primeiro que quem digitou quis dizer.
    """
    if not agulha:
        return (0, 0)
    primeira = -1
    posicao = 0
    for letra in agulha:
        achada = palheiro.find(letra, posicao)
        if achada < 0:
            return None
        if primeira < 0:
            primeira = achada
        posicao = achada + 1
    return (primeira, posicao - 1 - primeira)


def _no_grupo(agulha: str, grupo: str) -> tuple[int, int] | None:
    """O casamento no nome do grupo, e aqui ele é **trecho contíguo** e não subsequência.

    **Uma palavra curta casa qualquer coisa por subsequência, e o resultado é lixo.** Medido:
    `"sal"` é subsequência de `"visualizacao"` (o *s*, o *a* e o *l*), e digitar "sal" trazia os
    catorze comandos daquele grupo atrás de "Salvar a posição". `"ocr"`, `"arquivo"` e `"edicao"`
    -- que são o que alguém digita quando quer o grupo -- são trechos, e continuam achando.

    O rótulo é frase e o grupo é palavra: são regimes diferentes, e a mesma régua nos dois só
    parecia simples.
    """
    inicio = grupo.find(agulha)
    return None if inicio < 0 else (inicio, len(agulha) - 1)


def filtrar(consulta: str, entradas: Sequence[Entrada]) -> tuple[Entrada, ...]:
    """As entradas que a consulta alcança, na ordem em que a paleta as mostra.

    **Consulta vazia devolve tudo, na ordem em que veio** -- que é a de grupo, e não a da
    pontuação. É a lista inteira do programa, e reordená-la por "tem tecla" faria a paleta aberta
    parecer um ranking em vez de um índice.

    ## A ordem, e o que cada degrau resolve

    1. **vão menor primeiro**, e depois **início menor**: o casamento mais apertado, e entre dois
       igualmente apertados o que começa antes.
    2. **desabilitado desce, mas só no empate.** A spec pede "Enter executa o primeiro", e a
       leitura literal disso -- linha cinza sempre no fim -- foi medida e recusada: com ela,
       digitar `"anotar"` trazia "Desfazer a última mudança no tabuleiro" (a…n…o…t…a…r espalhado
       pela frase) **acima** de "Anotar página", que é a resposta. Enterrar a linha cinza sob
       casamento ruim desfaz o item ao lado, que existe para que ela seja **achada** e diga por
       quê. Então ela desce entre iguais, e o Enter sobre ela não faz nada -- que é a única parte
       do critério que importa: nada dispara por engano.
    3. **casou no rótulo ganha de casou no grupo**, e isto é *desempate* -- entre dois casamentos
       igualmente apertados, quem casou pelo nome é quem foi procurado. A consulta corre nos dois
       e **vale o melhor dos dois**, nunca "o rótulo se ele casar": medido, `"ocr"` casa no rótulo
       de "Devolver as caixas tiradas desta página" (o…c…r, espalhado por 26 letras) e no grupo de
       "Ler esta página" (vão 2, cravado). Com o rótulo acima do vão, a primeira subia; e
       preferindo o rótulo só por existir, "Folha da página aberta" -- que **é** do grupo OCR --
       ia para trás dela. O casamento no grupo é por **trecho** e não por subsequência, e
       `_no_grupo` diz por quê.
    4. **quem tem tecla sobe.** É o desempate que a spec pede, e ele também é *desempate* de
       propósito: posto acima da qualidade do casamento, `"l"` traria "Ajustar à largura"
       (`Ctrl+0`) na frente de "Ler esta página", que casa na primeira letra. Aqui ele decide
       entre iguais -- entre "Ler esta página" (`Ctrl+R`) e "Limpar o tabuleiro", que casam os
       dois em início 0 com vão 0, ele escolhe a que a pessoa já sabe apertar.
    5. **ordem do catálogo**, para que o resto seja estável e não dependa do `sort`.
    """
    agulha = _dobrado(consulta)
    if not agulha:
        return tuple(entradas)

    pontuadas: list[tuple[tuple[int, int, bool, bool, bool, int], Entrada]] = []
    for posicao, entrada in enumerate(entradas):
        # **O melhor dos dois, e não "o rótulo se ele casar".** Medido no catálogo depois de ele
        # crescer: "Folha da página aberta" é do grupo OCR e o rótulo dela casa `"ocr"` espalhado
        # por dezoito letras. Preferir o rótulo por existir jogava um comando **do grupo OCR**
        # para trás de um que não é dele -- uma resposta impossível de ler como certa.
        candidatos: list[tuple[int, int, bool]] = []
        for achado, veio_do_grupo in (
            (_casamento(agulha, _dobrado(entrada.rotulo)), False),
            (_no_grupo(agulha, _dobrado(entrada.grupo)), True),
        ):
            if achado is not None:
                candidatos.append((achado[1], achado[0], veio_do_grupo))
        if not candidatos:
            continue
        vao, inicio, veio_do_grupo = min(candidatos)
        chave = (vao, inicio, veio_do_grupo, not entrada.habilitado, not entrada.tecla, posicao)
        pontuadas.append((chave, entrada))
    return tuple(entrada for _, entrada in sorted(pontuadas, key=lambda par: par[0]))


# --------------------------------------------------------------------------------- a janela

COLUNAS: tuple[tabela.Coluna, ...] = (
    tabela.Coluna("comando", "Comando", 380, elastica=True),
    tabela.Coluna("tecla", "Tecla", 110),
    tabela.Coluna("grupo", "Grupo", 130),
)
"""Três colunas, e o grupo à direita como o menu põe o acelerador.

A elástica é a do comando, pela regra de `ui/tabela.py`: é a que não tem tamanho previsível --
mais ainda aqui, onde a linha desabilitada carrega o motivo junto do rótulo."""

ALTURA_EM_LINHAS = 14
"""Quantas linhas a lista mostra sem rolar. O catálogo tem mais que isso, e é de propósito: a
paleta não é o inventário (S-233) -- ela é o que sobra depois de digitar duas letras."""

TAG_DESABILITADO = "desabilitado"


class JanelaDaPaleta(tk.Toplevel):
    """Um campo em cima, a lista embaixo, e o teclado inteiro no campo.

    **As setas são ligadas no campo, e não na lista**, e é a única forma que funciona: quem tem o
    foco é o campo -- senão não se digita -- e uma lista sem foco não recebe `<Up>`/`<Down>`. Sem
    isto, navegar exigiria `Tab` até a lista, e aí a próxima letra digitada não iria para a
    consulta.
    """

    def __init__(
        self,
        pai: tk.Misc,
        amarrados: Mapping[str, Callable[[], None]],
        *,
        motivos: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(pai)
        self.title(TITULO)
        self.transient(pai if isinstance(pai, (tk.Tk, tk.Toplevel)) else None)

        self._amarrados = dict(amarrados)
        self._entradas = inventario(amarrados, motivos=motivos)
        self._visiveis: tuple[Entrada, ...] = ()

        moldura = ttk.Frame(self, padding=12)
        moldura.pack(fill=tk.BOTH, expand=True)

        self.consulta = tk.StringVar()
        self.campo = ttk.Entry(moldura, textvariable=self.consulta)
        self.campo.pack(fill=tk.X, pady=(0, 8))

        # `tabela.montar` e não um `Treeview` à mão: as duas barras e a largura mínima de coluna
        # são as regras da S-153, e escrevê-las de novo aqui é como o projeto chegou a duas
        # tabelas com o mesmo defeito.
        self.lista = tabela.montar(moldura, COLUNAS, height=ALTURA_EM_LINHAS, selectmode="browse")
        self.lista.tag_configure(TAG_DESABILITADO, foreground=theme.cor_atual(tokens.TEXTO_SECUNDARIO))

        ttk.Label(
            moldura,
            text="Enter executa · ↑ ↓ navegam · Esc fecha",
            foreground=theme.cor_atual(tokens.TEXTO_SECUNDARIO),
            font=theme.fonte_atual(tipografia.AUXILIAR),
        ).pack(fill=tk.X, pady=(8, 0))

        self.consulta.trace_add("write", self._refiltrar)
        for widget in (self.campo, self.lista):
            widget.bind("<Return>", self.executar)
            widget.bind("<Escape>", self.fechar)
            widget.bind("<Down>", lambda _evento: self.mover(1))
            widget.bind("<Up>", lambda _evento: self.mover(-1))
        self.lista.bind("<Double-Button-1>", self.executar)

        self._refiltrar()
        self.campo.focus_set()

    # ------------------------------------------------------------------------ o que o teste lê

    def visiveis(self) -> tuple[Entrada, ...]:
        """As entradas desenhadas agora, na ordem em que estão na lista."""
        return self._visiveis

    def selecionada(self) -> Entrada | None:
        """A entrada sob a seleção, ou `None` quando a consulta não achou nada."""
        escolhidos = self.lista.selection()
        if not escolhidos:
            return None
        return self._visiveis[self.lista.index(escolhidos[0])]

    def digitar(self, consulta: str) -> None:
        """Escreve no campo como quem digita. O `trace` refiltra, e é o mesmo caminho."""
        self.consulta.set(consulta)

    # ---------------------------------------------------------------------------- a mecânica

    def _refiltrar(self, *_argumentos: object) -> None:
        self._visiveis = filtrar(self.consulta.get(), self._entradas)
        self.lista.delete(*self.lista.get_children())
        for entrada in self._visiveis:
            self.lista.insert(
                "",
                tk.END,
                values=(entrada.no_texto, entrada.tecla, entrada.grupo),
                tags=() if entrada.habilitado else (TAG_DESABILITADO,),
            )
        self._selecionar(0)

    def _selecionar(self, indice: int) -> None:
        filhos = self.lista.get_children()
        if not filhos:
            return
        alvo = filhos[max(0, min(indice, len(filhos) - 1))]
        self.lista.selection_set(alvo)
        self.lista.focus(alvo)
        self.lista.see(alvo)

    def mover(self, passo: int) -> str:
        """Anda uma linha e **come o evento**: `"break"` impede o cursor de sair do campo.

        Não dá a volta na ponta. Uma lista circular faz a última linha aparecer onde a primeira
        deveria estar, e numa lista que rola isso é indistinguível de não ter andado.
        """
        escolhidos = self.lista.selection()
        atual = self.lista.index(escolhidos[0]) if escolhidos else 0
        self._selecionar(atual + passo)
        return "break"

    def executar(self, _evento: object = None) -> str:
        """Roda o comando selecionado, se ele estiver vivo. Linha cinza não faz nada e não fecha."""
        entrada = self.selecionada()
        if entrada is None or not entrada.habilitado:
            return "break"
        funcao = self._amarrados[entrada.acao]
        # Fecha **antes** de executar: metade destes comandos abre uma caixa de diálogo, e uma
        # paleta que continuasse por cima dela seria a janela pedindo duas respostas ao mesmo
        # tempo. É a mesma ordem do menu, que se recolhe antes de o comando rodar.
        self.destroy()
        funcao()
        return "break"

    def fechar(self, _evento: object = None) -> str:
        """Esc: sai sem executar nada."""
        self.destroy()
        return "break"

    def ligada(self, sequencia: str) -> bool:
        """Se a tecla está ligada no campo. **É o que separa os dois testes desta janela.**

        A S-117 registrou por que não se dirige o Tk com `event_generate` numa suíte: sem foco
        de verdade o evento de teclado não chega, e com `focus_force` o teste passa a depender do
        gerenciador de janelas da máquina. Então a decisão é testada onde ela é tomada -- em
        `executar`, `mover` e `fechar` -- e o que sobra a conferir é **que a tecla chega lá**,
        que é esta pergunta.
        """
        return bool(self.campo.bind(sequencia))


def abrir(
    pai: tk.Misc,
    amarrados: Mapping[str, Callable[[], None]],
    *,
    motivos: Mapping[str, str] | None = None,
) -> JanelaDaPaleta:
    """Abre a paleta. Uma por vez: reabrir traz a que já está aberta para a frente.

    Mesma regra da legenda (S-165), e aqui ela vale mais: a tecla que abre é a mesma que se
    aperta quando nada parece ter acontecido, e sem isto o segundo `Ctrl+Shift+P` empilharia uma
    paleta sobre a outra com duas consultas diferentes.
    """
    for filho in pai.winfo_children():
        if isinstance(filho, JanelaDaPaleta) and filho.winfo_exists():
            filho.lift()
            filho.campo.focus_set()
            return filho
    return JanelaDaPaleta(pai, amarrados, motivos=motivos)
