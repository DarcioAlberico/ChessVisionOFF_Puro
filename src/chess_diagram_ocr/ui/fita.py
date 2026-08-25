"""A fita de grupos nomeados da pele "Fita", gerada do catálogo (S-227/S-228).

**O que a Imagem 2 propõe é agrupamento, e ele já existe como dado.** Ela desenha quatro grupos com
cabeçalho -- Arquivo, OCR, Edição, Visualização -- e treze comandos distribuídos entre eles. Quando
a spec foi escrita, não havia agrupamento declarado em lugar nenhum: as duas barras do PDF eram
duas listas planas, e o único agrupamento existente era o separador visual de `menu.py`, que só o
menu conhecia. A S-219 declarou os seis grupos, e a fita é a primeira pele que os desenha.

**A fita mostra quem tem ícone, e essa regra não é arbitrária.** Um botão de fita é ícone com
rótulo; um comando sem ícone não tem como ser um. Os da S-220 caem exatamente nos quatro grupos da
imagem, e ACERVO e AJUDA ficam **vazios**, sem cabeçalho. Os comandos restantes continuam
alcançáveis pelo menu, que é o que a regra 2 exige e a S-233 mede.

**O grupo é a unidade de quebra, e é isso que distingue esta fita da barra.** `ui/barra.py` quebra
por item e afirma que *nenhum item é descartado*; a fita herda a propriedade usando a **mesma**
`BarraFluida`, com os grupos como itens. Um grupo partido ao meio não é um grupo, e a única quebra
aceitável é entre grupos. Não há segunda implementação de quebra neste projeto.

**A altura é o risco desta pele, e ela tem orçamento (S-228).** A S-151 mediu o defeito que a fita
arrisca recriar: cinco barras empilhadas = ~200 px, 20% da altura da janela, sobre o painel cuja
única razão de existir é mostrar a página grande. E a fita é pior que a barra num aspecto --
quebrar uma barra custa ~28 px; quebrar uma fita custa outra linha de fita, que é ~100. Daí os dois
modos, o orçamento em pixel declarado em `ORCAMENTO`, e `altura_da_fita`, que é **pura**: a altura
se afirma na suíte sem `winfo_height` no critério.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from tkinter import ttk

from . import atalhos, comandos, icones, pele, strings, theme, tipografia, tokens
from .barra import ESPACO_ENTRE_ITENS, BarraFluida
from .tooltip import Tooltip

__all__ = [
    "COMPACTO",
    "HISTERESE",
    "LADO_DO_ICONE",
    "LINHAS_DO_ROTULO",
    "MODOS",
    "ORCAMENTO",
    "PLENO",
    "Fita",
    "GrupoDeFita",
    "acoes_da_fita",
    "altura_atual",
    "altura_da_fita",
    "grupos",
    "montar",
    "quebrar_rotulo",
]

PLENO = "pleno"
"""Ícone grande, rótulo embaixo, cabeçalho de grupo à vista. É a Imagem 2 desenhada."""

COMPACTO = "compacto"
"""Ícone pequeno, rótulo ao lado, cabeçalho na dica. É a mesma fita numa janela que não a comporta."""

MODOS: tuple[str, ...] = (PLENO, COMPACTO)

LADO_DO_ICONE: dict[str, int] = {PLENO: 32, COMPACTO: 20}
"""O lado do ícone em cada modo, em pixel.

No pleno ele fica **acima** do rótulo: sem uma palavra grudada nele, o ícone carrega o
reconhecimento sozinho, e 32 px é o tamanho em que o traço de `ui/icones.py` (9% do lado, ~3 px)
ainda se lê como desenho. No compacto ele volta a ser marca ao lado do texto, como a pílula da
pele "Foco" -- e 20 px é o que não faz o botão crescer além da linha de texto."""

ORCAMENTO: dict[str, int] = {PLENO: 120, COMPACTO: 64}
"""Quanta altura cada modo pode gastar, em pixel. **Declarado, e verificado na suíte.**

Os dois números não são gosto. **120 px é 12%** de uma janela de 1000 de altura -- abaixo dos 20%
que a S-151 chamou de defeito, e acima dos ~56 px das duas barras de hoje, que é o que a fita custa
a mais em troca de legibilidade. **64 px** é o que cabe sem a fita competir com a página num
1366×768, que é a tela em que a S-151 mediu o problema original."""

LINHAS_DO_ROTULO = 2
"""Em quantas linhas o rótulo do botão pode quebrar. **Duas nos dois modos**, e isso foi medido.

**Medido, e não escolhido.** Sem quebra, "Apagar a peça da casa selecionada" vira um botão de 230
px e a fita inteira pede mais de 2.000 -- ela nasceria em duas linhas em qualquer tela, o que
derrota a fita antes de o orçamento chegar.

> ## O achado da S-228: "rótulo ao lado" é **mais largo**, e não mais estreito
>
> A spec desenha o modo compacto com o rótulo ao lado do ícone, e a intuição é que uma linha só de
> texto ocupa menos. Ela ocupa menos **altura** e muito mais **largura**, e a fita paga em largura:
>
> | forma | largura de uma linha | linhas em 1366 | altura em 1366 |
> |---|---:|---:|---:|
> | pleno: ícone 32 em cima, 2 linhas, cabeçalho | 1.375 px | 2 | 200 px |
> | compacto com o rótulo em **uma** linha | 2.317 px | **3** | 106 px |
> | compacto com o rótulo em **duas** linhas | 1.726 px | 2 | **90 px** |
>
> Uma linha de rótulo transformaria o modo que existe para caber num modo que pede **três** linhas
> de fita na tela em que ele foi inventado para servir. O compacto herda a quebra do pleno, e o que
> o faz compacto são as outras três coisas: ícone menor, rótulo ao lado e cabeçalho na dica --
> 44 px de linha contra 99, que é o que o orçamento pede.
>
> **E o compacto é mais largo que o pleno mesmo assim** -- 1.726 contra 1.375, com a mesma quebra.
> Não é anomalia, é a forma: o rótulo sai de baixo do ícone e vai para o lado dele, e **o que era
> altura vira largura**. O modo compacto compra altura e paga em largura, e é por isso que reduzir
> o rótulo a uma linha -- que parece "compactar mais" -- é o que o destrói.

**E não se encurta o rótulo**: nenhum item desta fase troca o texto de comando nenhum (achado 1 do
roadmap). As mesmas palavras, noutra quebra."""

HISTERESE = 24
"""Quantos pixels a mais a janela precisa ter para a fita **voltar** ao modo pleno.

Sem ela a troca é reversível no mesmo pixel: uma janela arrastada até a vizinhança do limiar troca
de modo a cada pixel de tremor, e cada troca **destrói e recria os dezessete botões**. Vinte e
quatro pixels é mais que o tremor de um arrasto e menos que um botão -- separa os dois sentidos sem
chegar a exigir arrastar a janela duas vezes para desfazer o que ela acabou de fazer.

**O que ela não é.** A primeira redação deste docstring justificava a histerese por um laço --
"o compacto pede menos largura, o recipiente encolhe até a largura pedida, e a largura pedida volta
a autorizar o pleno". **A premissa é falsa, e foi medida:** o compacto pede *mais* largura que o
pleno (1.726 px contra 1.375), porque o rótulo sai de baixo do ícone e vai para o lado dele -- o que
era altura vira largura. O laço descrito não existe, e a razão de a histerese ficar é a de cima,
que é outra."""

# ------------------------------------------------------------------- as medidas do ttk.Button
#
# **Medidas, e não estimativas.** Os três números abaixo saíram de montar o botão e ler
# `winfo_reqheight` nos três tamanhos de ícone (20, 24 e 32) e nas duas contagens de linha, com o
# tema padrão do programa. A conta que eles fecham é exata nas seis combinações -- é por isso que
# `altura_da_fita` pode prometer 2 px de tolerância contra o widget montado em vez de "mais ou
# menos isso".

MOLDURA_DO_BOTAO = 14
"""Borda mais preenchimento vertical de um `ttk.Button`, somando os dois lados."""

FOLGA_ACIMA_DO_ROTULO = 4
"""O vão que o `compound=TOP` abre entre o ícone e a primeira linha do rótulo."""

MOLDURA_DO_CABECALHO = 4
"""Borda mais preenchimento vertical do `ttk.Label` que desenha o nome do grupo."""

ESPACO_ATE_O_CABECALHO: dict[str, int] = {pele.CONFORTAVEL: 2, pele.COMPACTA: 0}
"""O vão entre a fila de botões e o cabeçalho do grupo, por densidade.

É o único canal de densidade que esta fase liga -- o eixo inteiro é da S-232. Estar aqui como
parâmetro, e não como constante, é o que faz `altura_da_fita` continuar valendo quando ela chegar."""

ESPACO_ENTRE_BOTOES: dict[str, int] = {pele.CONFORTAVEL: 2, pele.COMPACTA: 1}
"""O `padx` entre dois botões do mesmo grupo. Largura, e não altura: não entra no orçamento."""


def quebrar_rotulo(texto: str, *, linhas: int = LINHAS_DO_ROTULO) -> str:
    """O rótulo repartido em até `linhas` linhas, na fronteira de palavra.

    Pura, e por isso conferível sem abrir janela -- e é o que permite afirmar que **nenhuma
    palavra some**: o `ttk.Button` não aceita `wraplength` (é opção de `tk.Button` e de `Label`),
    então quem reparte é este módulo, e não o widget.
    """
    palavras = str(texto).split()
    if len(palavras) <= 1 or linhas <= 1:
        return str(texto)
    largura = max(len(palavra) for palavra in palavras)
    largura = max(largura, -(-sum(len(p) + 1 for p in palavras) // linhas))
    montadas: list[str] = []
    for palavra in palavras:
        if montadas and len(montadas[-1]) + 1 + len(palavra) <= largura:
            montadas[-1] = f"{montadas[-1]} {palavra}"
        else:
            montadas.append(palavra)
    return "\n".join(montadas)


def altura_da_fita(
    modo: str,
    *,
    linha_de_texto: int,
    linha_de_apoio: int,
    densidade: str = pele.CONFORTAVEL,
) -> int:
    """A altura que a fita vai ocupar naquele modo, em pixel. **Pura** -- é o item.

    `linha_de_texto` e `linha_de_apoio` são o `linespace` das fontes de `CORPO` e de `AUXILIAR`,
    que é o que o Tk reporta e o que faz a conta acompanhar a fonte do sistema (S-149) em vez de
    cravar pontos. Quem os lê do Tk é `altura_atual`; quem os passa à mão é o teste, e é isso que
    permite afirmar o orçamento em 9, 10 e 12 pt sem trocar a fonte do Windows.

    **Nada de `winfo_height` no critério.** Um orçamento medido no widget montado só falha depois
    de a janela estar errada, e numa largura que o teste por acaso tenha escolhido. Aqui ele falha
    na conta, que é onde a decisão está.

    Levanta `KeyError` para modo ou densidade que não existem, como `tokens.cor`: um modo escrito
    errado que caísse no pleno devolveria um número plausível para o orçamento errado.
    """
    if modo not in LADO_DO_ICONE:
        raise KeyError(f"modo de fita desconhecido: {modo!r}. Os válidos estão em MODOS.")
    if densidade not in ESPACO_ATE_O_CABECALHO:
        raise KeyError(f"densidade desconhecida: {densidade!r}. As válidas estão em pele.DENSIDADES.")

    lado = LADO_DO_ICONE[modo]
    rotulo = LINHAS_DO_ROTULO * linha_de_texto
    if modo == COMPACTO:
        # Ícone **ao lado** do rótulo: a altura é a do mais alto dos dois, e não a soma. E o
        # cabeçalho não entra porque ele virou dica -- é daí que vem quase toda a economia.
        return max(lado, rotulo) + MOLDURA_DO_BOTAO

    botao = lado + FOLGA_ACIMA_DO_ROTULO + rotulo + MOLDURA_DO_BOTAO
    return botao + ESPACO_ATE_O_CABECALHO[densidade] + linha_de_apoio + MOLDURA_DO_CABECALHO


def linhas_de_fonte() -> tuple[int, int]:
    """`(linespace do corpo, linespace do apoio)` como o Tk os reporta, em pixel.

    A reserva é derivada do tamanho em pontos e não cravada: `round(pontos * 5 / 3)` devolve 15
    para 9 pt e 13 para 8 pt, que são exatamente os dois valores medidos. Sem janela -- ou com uma
    fonte que o Tk não descreva -- a conta segue valendo, e o orçamento continua afirmável.
    """
    tamanho, _proporcional, _mono = theme.fonte_base()
    escala = tipografia.escala(tamanho)
    reserva = (round(escala[tipografia.CORPO] * 5 / 3), round(escala[tipografia.AUXILIAR] * 5 / 3))
    try:
        from tkinter import font as tkfont

        corpo = int(tkfont.Font(font=theme.fonte_atual(tipografia.CORPO)).metrics("linespace"))
        apoio = int(tkfont.Font(font=theme.fonte_atual(tipografia.AUXILIAR)).metrics("linespace"))
    except Exception:  # noqa: BLE001 - sem root ou fonte exótica: a reserva serve
        return reserva
    return (corpo or reserva[0], apoio or reserva[1])


def altura_atual(modo: str, *, densidade: str = pele.CONFORTAVEL) -> int:
    """`altura_da_fita` resolvida contra a fonte deste sistema. É o que o painel pergunta."""
    corpo, apoio = linhas_de_fonte()
    return altura_da_fita(modo, linha_de_texto=corpo, linha_de_apoio=apoio, densidade=densidade)


@dataclass(frozen=True)
class GrupoDeFita:
    """Um grupo desenhado: o cabeçalho e os comandos dele, na ordem do catálogo."""

    grupo: str
    """A chave em `comandos.GRUPOS`."""

    rotulo: str
    """O cabeçalho, como a pessoa lê -- `comandos.rotulo_do_grupo`."""

    itens: tuple[comandos.Comando, ...]
    """Os comandos com ícone daquele grupo. Nunca vazio: grupo vazio não vira `GrupoDeFita`."""


def grupos() -> tuple[GrupoDeFita, ...]:
    """A fita como dado: um grupo por cabeçalho, na ordem de `comandos.GRUPOS`.

    **Grupo sem comando visível não aparece**, e não aparece como cabeçalho vazio: um título
    solto é pior que a ausência dele -- ele promete um grupo e entrega uma faixa em branco.
    """
    montados = [
        GrupoDeFita(
            grupo=grupo,
            rotulo=comandos.rotulo_do_grupo(grupo),
            itens=tuple(registro for registro in comandos.do_grupo(grupo) if registro.icone),
        )
        for grupo in comandos.GRUPOS
    ]
    return tuple(pronto for pronto in montados if pronto.itens)


def acoes_da_fita() -> list[str]:
    """Os nomes dos comandos que a fita desenha, na ordem em que ela os desenha."""
    return [registro.acao for grupo in grupos() for registro in grupo.itens]


class Fita(BarraFluida):
    """A fita montada, e o modo em que ela está agora (S-227/S-228).

    **Por que uma classe, e não uma função que devolve widgets.** A troca de modo não é uma
    reconfiguração: o ícone muda de tamanho (o cache de `ui/icones.py` é por tamanho), o rótulo
    muda de lado e de quebra, e o cabeçalho deixa de ser um widget para virar linha de dica.
    Alguém precisa saber remontar, e precisa lembrar do que remontar a partir de quê.

    **O limiar de troca é medido, e não escolhido.** Ele é a largura que a fita **plena** pede
    para caber em uma linha, lida do próprio widget na construção. A consequência é o critério de
    aceite escrito de graça: a fita entra em compacto exatamente quando a plena precisaria de uma
    segunda linha, e nunca depois disso.
    """

    def __init__(
        self,
        pai: tk.Misc,
        amarrados: Mapping[str, Callable[[], None]],
        *,
        modo: str | None = None,
        densidade: str = pele.CONFORTAVEL,
    ) -> None:
        super().__init__(pai)
        if modo is not None and modo not in LADO_DO_ICONE:
            raise KeyError(f"modo de fita desconhecido: {modo!r}. Os válidos estão em MODOS.")
        self._amarrados = dict(amarrados)
        self._densidade = densidade
        self._fixo = modo is not None
        """Modo pedido de fora é modo cravado: quem monta a fita num tamanho para fotografá-la ou
        para medi-la não quer que a largura da janela decida por ele."""

        self._modo = modo or PLENO
        self._botoes: dict[str, ttk.Button] = {}
        self._largura_plena = 0
        self._construir()
        if not self._fixo:
            # `add="+"`: a `BarraFluida` já ouve o `<Configure>` para rearranjar, e substituir a
            # ligação dela seria trocar a quebra por linha pela troca de modo.
            self.bind("<Configure>", self._ao_medir, add="+")

    # ------------------------------------------------------------------------------ leitura

    @property
    def modo(self) -> str:
        """`PLENO` ou `COMPACTO`, como a fita está desenhada agora."""
        return self._modo

    @property
    def densidade(self) -> str:
        return self._densidade

    @property
    def largura_de_troca(self) -> int:
        """A largura abaixo da qual a fita fica compacta -- medida, e não escolhida.

        É o que a fita **plena** pede para caber em uma linha: a soma dos grupos mais o espaço
        entre eles. Zero enquanto os botões ainda não têm tamanho pedido -- ver `_medir_plena`.
        """
        self._medir_plena()
        return self._largura_plena

    @property
    def acoes_desenhadas(self) -> list[str]:
        """Os comandos que estão na tela agora, na ordem em que a fita os desenha.

        Existe para o critério que a troca de modo poderia quebrar em silêncio: **nenhuma
        largura descarta comando**. Contar botões na árvore de widgets responderia o mesmo e
        confundiria o botão de um grupo com o de outro.
        """
        return [acao for acao in acoes_da_fita() if acao in self._botoes]

    def botao(self, acao: str) -> ttk.Button:
        """O botão daquele comando. Levanta `KeyError` para comando que a fita não desenha."""
        if acao not in self._botoes:
            raise KeyError(f"a fita não desenha o comando {acao!r}.")
        return self._botoes[acao]

    def altura_prevista(self) -> int:
        """O que `altura_da_fita` promete para o modo e a densidade atuais."""
        return altura_atual(self._modo, densidade=self._densidade)

    # ------------------------------------------------------------------------------ montagem

    def _construir(self) -> None:
        self._botoes.clear()
        for grupo in grupos():
            self.adicionar(self._grupo(grupo))
        self._medir_plena()

    def _medir_plena(self) -> None:
        """Guarda a largura que a fita plena pede em uma linha, **quando ela já for medível**.

        Chamada mais de uma vez de propósito, e ela desiste em silêncio nas primeiras. Dentro do
        `__init__` o Tk ainda não calculou o tamanho pedido dos botões: `winfo_reqwidth` devolve
        1 até as tarefas ociosas rodarem, e uma soma de uns seria um limiar de 22 px -- abaixo de
        qualquer janela, o que faria a fita nunca entrar em compacto. Medir de novo no primeiro
        `<Configure>` custa nada e é o primeiro instante em que o número existe.

        Só mede no modo pleno: no compacto os botões são outros, e a largura deles não responde
        a pergunta que o limiar faz.
        """
        if self._modo != PLENO or self._largura_plena:
            return
        larguras = [item.winfo_reqwidth() for item in self._itens]
        if not larguras or min(larguras) <= 1:
            return
        self._largura_plena = sum(larguras) + ESPACO_ENTRE_ITENS * (len(larguras) - 1)

    def _reconstruir(self) -> None:
        self.esvaziar()
        self._botoes.clear()
        for grupo in grupos():
            self.adicionar(self._grupo(grupo))

    def _ao_medir(self, evento: tk.Event) -> None:
        """Decide o modo pela largura que o evento trouxe. Nunca pela `winfo_width`.

        É a mesma razão da `BarraFluida`: durante um redimensionamento o widget ainda reporta a
        largura anterior quando o `<Configure>` chega, e decidir o modo contra ela deixaria a
        fita um evento atrás da janela.
        """
        self._medir_plena()
        largura = int(evento.width)
        if largura <= 1 or not self._largura_plena:
            return
        if self._modo == PLENO and largura < self._largura_plena:
            self._modo = COMPACTO
        elif self._modo == COMPACTO and largura >= self._largura_plena + HISTERESE:
            self._modo = PLENO
        else:
            return
        self._reconstruir()

    def _grupo(self, grupo: GrupoDeFita) -> ttk.Frame:
        """Um grupo inteiro num `Frame` -- e é o `Frame` que a barra arranja, nunca os botões dele."""
        moldura = ttk.Frame(self)
        corpo = ttk.Frame(moldura)
        corpo.pack(side=tk.TOP)
        for registro in grupo.itens:
            botao = self._botao(corpo, registro, grupo)
            botao.pack(side=tk.LEFT, padx=ESPACO_ENTRE_BOTOES[self._densidade])
            self._botoes[registro.acao] = botao
        if self._modo == COMPACTO:
            # **O cabeçalho vira dica** (S-228). Ele custa uma linha de texto por fita, e no modo
            # compacto essa linha é a diferença entre caber e competir com a página. O nome do
            # grupo não se perde: ele passa a abrir a dica de cada botão dele.
            return moldura
        cabecalho = ttk.Label(moldura, text=grupo.rotulo, anchor="center")
        # O cabeçalho **embaixo**, como a Imagem 2 desenha: o nome do grupo é a legenda de uma fila
        # de botões, e uma legenda acima competiria com a barra de menus por leitura.
        cabecalho.pack(side=tk.TOP, fill=tk.X, pady=(ESPACO_ATE_O_CABECALHO[self._densidade], 0))
        theme.pintar(cabecalho, "foreground", tokens.TEXTO_SECUNDARIO)
        cabecalho.configure(font=theme.fonte_atual(tipografia.AUXILIAR))
        return moldura

    def _botao(self, pai: tk.Misc, registro: comandos.Comando, grupo: GrupoDeFita) -> ttk.Button:
        """No pleno, ícone **acima** do rótulo, que é a forma da Imagem 2; no compacto, ao lado."""
        acima = self._modo == PLENO
        botao = ttk.Button(
            pai,
            text=quebrar_rotulo(registro.no_botao),
            style=comandos.estilo(registro.acao),
            command=self._amarrados[registro.acao],
            compound=tk.TOP if acima else tk.LEFT,
        )
        # A cor do ícone é perguntada ao token na hora de desenhar, e é o que faz o mesmo traço
        # servir ao cromo claro e ao escuro (S-220). Ícone que não desenhou vira botão só com
        # texto: `icones.icone` devolve `None` em vez de levantar.
        foto = icones.icone(registro.icone, LADO_DO_ICONE[self._modo], theme.cor_atual(tokens.TEXTO_PADRAO))
        if foto is not None:
            botao.configure(image=foto)
        Tooltip(botao, self._dica(registro, grupo))
        return botao

    def _dica(self, registro: comandos.Comando, grupo: GrupoDeFita) -> str:
        """O rótulo por extenso, a tecla, e -- no compacto -- o grupo que perdeu o cabeçalho."""
        titulo = registro.rotulo if self._modo == PLENO else f"{grupo.rotulo} {strings.SETA} {registro.rotulo}"
        tecla = atalhos.acelerador(registro.acao)
        return f"{titulo}\nTecla: {tecla}" if tecla else titulo


def montar(
    pai: tk.Misc,
    amarrados: Mapping[str, Callable[[], None]],
    *,
    modo: str | None = None,
    densidade: str = pele.CONFORTAVEL,
) -> Fita:
    """A fita, montada numa `BarraFluida` cujos **itens são os grupos**.

    `modo=None` deixa a largura decidir, que é o caso da janela; um modo explícito o crava, que é
    o caso de quem mede um dos dois orçamentos.

    Levanta `KeyError` nomeando comando não amarrado, como `menu.montar` e `fila.montar`: um
    botão grande, com ícone e rótulo, que não faz nada é pior que a ausência dele.
    """
    if faltando := sorted(acao for acao in acoes_da_fita() if acao not in amarrados):
        raise KeyError(f"comando da fita sem função: {', '.join(faltando)}")
    return Fita(pai, amarrados, modo=modo, densidade=densidade)
