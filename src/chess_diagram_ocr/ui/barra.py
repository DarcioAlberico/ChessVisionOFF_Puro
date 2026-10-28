"""As duas formas de barra de ferramentas deste projeto: a que quebra (S-151) e a que enfileira
(S-527/S-528). As duas são decisão pura; os widgets que as executam moram em `qt/barra.py`.

**A segunda metade deste arquivo é a forma nova, e ela é a que ganha.** A barra que quebra
resolve o defeito de esconder botão sem avisar, e resolve **empilhando fileiras** -- a S-151 media
cinco barras e 200 px de cromo. A barra em fila resolve o mesmo defeito sem gastar altura: o que
não cabe vai para um menu "Mais", e a fila continua sendo uma. A sala de estudo foi a primeira
(S-527) e o painel do PDF é a segunda (S-528); `Acao`, `Item`, `cabem` e `dica_de` moram aqui
porque são a **forma**, e cada tabela -- `ui/barra_da_sala.py`, `ui/barra_do_pdf.py` -- declara o
seu conteúdo.

---

# A barra que quebra em vez de cortar (S-151)

**O defeito.** `ui/pdf_panel.py` empilhava **cinco** barras antes de a página aparecer: ~200 px,
20% da altura da janela gastos em controle permanente, sobre o painel cuja única razão de
existir é mostrar a página grande.

E nenhuma delas refluía. Todas usavam `pack(side=LEFT)` numa linha de altura fixa, e quando
falta largura o Tk simplesmente **não desenha** o que passou da borda: em 1100 de largura somem
"Exportar PDF → PGN", "Cancelar exportação", "Tirar o selecionado" e a contagem de diagramas da
página. Sem aviso, sem reticências, sem `>>`.

**O que o `pack` não sabe, e esta barra sabe.** Que a linha pode ser duas. Dado o que cada item
pede e quanto há disponível, `arranjo` distribui os itens em linhas — e a propriedade que o
teste afirma é a que hoje falha: **nenhum item é descartado**, em nenhuma largura.

**Por que não um botão de transbordo.** Ele foi a primeira ideia e não sobrevive ao Tk: um
widget não muda de pai depois de criado, então "mover o que sobrou para dentro de um menu"
exigiria recriar cada controle — com os `Tooltip`, os `state=DISABLED` e as variáveis atados a
ele. Quebrar em mais uma linha custa ~28 px e não custa nenhuma dessas amarras, e a linha extra
só aparece na largura em que o transbordo apareceria.

**A decisão é pura; o widget só executa.** `arranjo` não toca `tkinter` e é afirmada nos três
regimes — cabe em uma linha, cabe em duas, não cabe em nenhuma.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar

from . import atalhos, comandos, estilos

logger = logging.getLogger(__name__)

__all__ = [
    "ESPACO_ENTRE_ITENS",
    "ICONE_DO_MAIS",
    "MAIS",
    "ROTULO_DO_MAIS",
    "SEPARADOR_DA_TECLA",
    "Acao",
    "Item",
    "arranjo",
    "cabem",
    "dica_de",
    "linhas_necessarias",
]

ESPACO_ENTRE_ITENS = 6
"""O `padx` entre dois controles da mesma linha. Entra na conta porque ele é largura também."""

# **Por que uma moldura por linha, e não um `grid` só.** Foram duas tentativas erradas antes,
# e as duas vieram de o `grid` do Tk ser uma tabela:
#
# 1. `grid(row=n, column=i)` dá a **mesma** largura à coluna `i` de todas as linhas. Com
#    "Próxima página" (92 px) na coluna 1 da primeira e "Ajustar à página" (95) na coluna 1 da
#    segunda, a coluna passa a medir 95 nas duas, cada linha engorda pelo item mais largo da
#    outra, e o `grid` **desmapeia** o que não coube -- o defeito original de volta.
# 2. Dar a cada linha uma faixa de colunas própria (0..99, 100..199) não isola nada: as colunas
#    do `grid` são dispostas da esquerda para a direita para a grade **inteira**, então a linha
#    2 nasce depois da largura somada da linha 1. Medido: os dois últimos botões começavam em
#    x=490 numa barra de 500 px.
#
# Uma `ttk.Frame` por linha, com os itens empacotados `in_=` ela, torna as linhas independentes
# de verdade. Os itens continuam sendo filhos da **barra** -- `pack(in_=...)` aceita qualquer
# descendente do pai --, então nada precisa ser recriado quando o arranjo muda.


def arranjo(
    larguras: Sequence[int],
    disponivel: int,
    *,
    espaco: int = ESPACO_ENTRE_ITENS,
) -> list[list[int]]:
    """Distribui os itens em linhas, na ordem em que vieram. Devolve índices por linha.

    **Nenhum item é descartado, em nenhuma largura** — é essa a propriedade que hoje falha, e é
    ela que o teste afirma nos três regimes. Um item mais largo que a barra inteira ocupa uma
    linha sozinho e é cortado na borda; cortar um é melhor que esconder três, e é o único caso
    em que a barra não tem saída.

    A ordem é preservada de propósito: reordenar controles entre larguras faria o mesmo botão
    mudar de lugar ao arrastar o divisor, e a memória motora de quem usa o programa todo dia
    vale mais que a linha economizada.
    """
    linhas: list[list[int]] = []
    atual: list[int] = []
    usado = 0
    for indice, largura in enumerate(larguras):
        pedido = int(largura) + (espaco if atual else 0)
        if atual and usado + pedido > int(disponivel):
            linhas.append(atual)
            atual, usado = [], 0
            pedido = int(largura)
        atual.append(indice)
        usado += pedido
    if atual:
        linhas.append(atual)
    return linhas


def linhas_necessarias(larguras: Sequence[int], disponivel: int, *, espaco: int = ESPACO_ENTRE_ITENS) -> int:
    """Quantas linhas a barra vai ocupar. É o que o critério de aceite mede."""
    return len(arranjo(larguras, disponivel, espaco=espaco))


# ==================================================================================================
# A barra que enfileira em vez de quebrar (S-527/S-528)
# ==================================================================================================
#
# **A forma, e não o conteúdo.** Uma barra em fila é uma fileira de botões agrupados por tarefa,
# com ícone e rótulo curto, e um "Mais ▾" no fim que recebe o que não coube. Quem diz *quais* são
# os grupos, quais ações são principais e em que ordem elas saem é a **tabela** de cada barra --
# `ui/barra_da_sala.py` e `ui/barra_do_pdf.py`. O que está aqui é o que as duas têm igual: a linha
# da tabela (`Acao`), a conta de quem cabe (`cabem`) e a dica (`dica_de`).
#
# A separação existe porque a segunda barra veio depois: a S-527 escreveu tudo em
# `ui/barra_da_sala.py`, e a S-528 -- que trouxe o painel do PDF para a mesma gramática -- teria
# de repetir a forma inteira ou importar "a barra da sala" para desenhar um painel que não é a
# sala. A tabela do PDF é a prova de que a forma é forma: ela declara cinco grupos, nenhum deles
# da sala, e não escreve uma linha de mecanismo.

MAIS = "mais"
"""O nome do botão de transbordo. Não é ação de nenhuma tabela: ele **é** a barra."""

ROTULO_DO_MAIS = "Mais"
ICONE_DO_MAIS = "mais"

SEPARADOR_DA_TECLA = " · "
"""Entre o rótulo e a tecla na primeira linha da dica: `Promover a variante · Ctrl+↑`."""


@dataclass(frozen=True)
class Acao:
    """Uma linha de uma barra em fila: tudo o que o widget precisa saber sem abrir janela.

    **Os três `ClassVar` são o que a subclasse preenche**, e é o que faz a mesma forma servir a
    duas tabelas. Eles não são estado de instância: `GRUPOS` é o vocabulário de grupos daquela
    barra, `IRMAS` é a tabela inteira -- é por ela que um agrupador acha os itens do submenu -- e
    `METODOS` é o `ação -> método do painel`. Cada módulo de tabela define a sua `Acao(Acao)`, com
    `GRUPOS` na declaração e os outros dois atribuídos ao pé do arquivo, quando a tupla existe.
    """

    GRUPOS: ClassVar[tuple[str, ...]] = ()
    """Os grupos válidos desta barra, na ordem em que ela os desenha."""

    IRMAS: ClassVar[tuple[Acao, ...]] = ()
    """A tabela inteira desta barra. Atribuída depois da tupla, no pé do módulo dela."""

    METODOS: ClassVar[Mapping[str, str]] = {}
    """`ação -> nome do método do painel`. O agrupador não tem, e é por isso que `metodo` é `""`."""

    acao: str
    """O nome do comando em `ui/comandos.py` -- ou um nome próprio, para o que o catálogo não tem."""

    grupo: str
    """Um dos de `GRUPOS`."""

    icone: str
    """Nome em `icones.ICONES` ou num dos dicionários de barra. Obrigatório para quem pode virar
    botão: a barra é dirigida a ícone, e uma ação sem traço seria um botão de texto no meio de
    botões com desenho. Vazio só para quem mora dentro de um agrupador (`dentro_de`)."""

    principal: bool = True
    """Ganha botão na barra. `False` vai direto para o menu "Mais"."""

    prioridade: int = 0
    """Entre as principais, quem **fica** quando falta largura: 1 sai por último. Ver `cabem`.

    **Duas principais com a mesma prioridade são um par**, e o par entra e sai da fila junto:
    "Promover" sem "Rebaixar" ao lado é um botão que sobe e nenhum que desce, e o crítico da S-527
    o viu assim a 1400 px. É a única igualdade permitida, e o teste cobra quais são os pares."""

    com_texto: bool = False
    """O botão escreve o rótulo curto ao lado do ícone. `False` desenha **só o ícone**, e o rótulo
    fica na dica -- que é a primeira linha dela, com a tecla.

    É a hierarquia do ChessBase, e foi o que a primeira rodada da S-527 não tinha: catorze botões
    com texto não cabem em 714 px. O texto é para o que se lê de longe; o resto é um traço de 16 px
    que a pessoa aprende em dois cliques, como em toda barra de ferramentas."""

    marcavel: bool = False
    """Interruptor: o botão fica pressionado e o item de menu ganha a marca."""

    dica: str = ""
    """A explicação além do rótulo longo."""

    rotulo_proprio: str = ""
    """Só para o que o catálogo não tem. Para comando do catálogo é vazio, e o texto vem de lá."""

    dentro_de: str = ""
    """O agrupador em que esta ação mora, quando ela é item de submenu e não botão. Não é principal
    e **não** vai para o "Mais": o lugar dela é o submenu do agrupador."""

    def __post_init__(self) -> None:
        if self.grupo not in type(self).GRUPOS:
            raise KeyError(f"grupo desconhecido: {self.grupo!r}. Os válidos estão em GRUPOS.")
        if self.no_catalogo and self.rotulo_proprio:
            raise ValueError(f"{self.acao}: comando do catálogo não escreve rótulo próprio")
        if not self.no_catalogo and not self.rotulo_proprio:
            raise ValueError(f"{self.acao}: fora do catálogo precisa de rótulo próprio")
        if self.dentro_de and self.principal:
            raise ValueError(f"{self.acao}: item de submenu não é botão da fila")
        if not self.dentro_de and not self.icone:
            raise ValueError(f"{self.acao}: ação que pode virar botão precisa de ícone")

    @property
    def no_catalogo(self) -> bool:
        return self.acao in comandos.por_acao

    @property
    def agrupador(self) -> bool:
        """Abre um submenu em vez de fazer alguma coisa."""
        return any(registro.dentro_de == self.acao for registro in type(self).IRMAS)

    @property
    def itens_do_submenu(self) -> tuple[str, ...]:
        """O que este agrupador abre, na ordem da tabela. Vazio para quem não é agrupador."""
        return tuple(registro.acao for registro in type(self).IRMAS if registro.dentro_de == self.acao)

    @property
    def rotulo_curto(self) -> str:
        """O texto do botão."""
        return self.rotulo_proprio or comandos.rotulo_de_botao(self.acao)

    @property
    def rotulo_longo(self) -> str:
        """A primeira linha da dica: o texto do menu, por extenso."""
        return comandos.rotulo(self.acao) if self.no_catalogo else self.rotulo_proprio

    @property
    def papel(self) -> str:
        """O papel de ênfase, do catálogo; neutro para o que está fora dele."""
        return comandos.papel(self.acao) if self.no_catalogo else estilos.NEUTRO

    @property
    def metodo(self) -> str:
        """O método do painel que a ação chama, ou `""` para o agrupador."""
        return type(self).METODOS.get(self.acao, "")

    @property
    def alterna_no_metodo(self) -> bool:
        """Quem inverte o estado de um interruptor: o método do painel, ou o próprio botão.

        **A régua é `rotulo_alternado`, e não "está no catálogo"** (S-528). Um interruptor que
        declara os dois rótulos é um interruptor que o menu e a paleta acionam **sem botão**, e o
        método dele precisa inverter `isChecked()` sozinho -- é o contrato da S-222. O botão não
        pode alternar também: alternaria duas vezes, que é o defeito que a medição de 2026-09-04
        achou no clique de "Treinar". Sem `rotulo_alternado`, o método só **lê** o estado, e quem
        alterna é o botão: é o caso de "Seguir OCR" na sala e o dos dois `QCheckBox` de preferência
        do painel do PDF, que a S-528 trouxe para a fila.

        A primeira redação era `return self.no_catalogo`, e ela dava a mesma resposta para as cinco
        da sala -- as quatro do catálogo têm `rotulo_alternado`, e o teste da S-527 cobra isso.
        Ela só passa a errar quando a segunda tabela chega, que é agora.
        """
        return self.no_catalogo and bool(comandos.comando(self.acao).rotulo_alternado)


def dica_de(registro: Acao) -> str:
    """A dica inteira: o rótulo longo **com a tecla na mesma linha**, e a explicação se houver.

    A primeira linha é o título -- o que é e como se chama pelo teclado, de uma vez: `Promover a
    variante · Ctrl+↑`. A primeira rodada da S-527 escrevia a tecla numa terceira linha (`Tecla: X`,
    o formato de `qt/fita._dica`), e o crítico pediu a tecla junto do rótulo: para um botão **só com
    ícone** a dica é o único lugar em que o rótulo aparece, e rótulo e tecla são a mesma resposta
    ("o que é isto?"). A explicação da S-347/S-516 vem depois, uma frase por linha.

    A tecla vem de `atalhos.acelerador`, que responde pela tabela da janela e pela da sala
    (`TECLAS_DA_SALA`); ação fora do catálogo não tem tecla.
    """
    tecla = atalhos.acelerador(registro.acao) if registro.no_catalogo else ""
    titulo = f"{registro.rotulo_longo}{SEPARADOR_DA_TECLA}{tecla}" if tecla else registro.rotulo_longo
    linhas = [titulo]
    if registro.dica:
        linhas.append(registro.dica)
    return chr(10).join(linhas)


@dataclass(frozen=True)
class Item:
    """Um botão principal como a conta o vê: quanto pede, quem sai antes, e de que grupo é."""

    largura: int
    prioridade: int
    grupo: str


def cabem(
    itens: Sequence[Item],
    disponivel: int,
    *,
    reserva: int,
    espaco: int,
    separador: int,
) -> frozenset[int]:
    """Os índices dos itens que ficam na fila; os outros vão para o "Mais". Pura.

    **Por prioridade, e em prefixo.** Os itens entram do mais prioritário para o menos, e a conta
    para no primeiro que não cabe -- mesmo que um menos prioritário e mais estreito coubesse depois.
    É o que faz a resposta ser enunciável: *"os n de maior prioridade"*, e não um subconjunto que
    muda de forma a cada pixel. A ordem em que eles se desenham é a da barra, não a da prioridade.

    `reserva` é o botão "Mais", que está sempre na fila: é ele que recebe quem não coube, então não
    pode ser o primeiro a sair -- e é também onde entra o que a barra pendurou fora da tabela (o
    campo de página do PDF, por exemplo). `separador` é a barra vertical entre dois grupos
    vizinhos, e ela entra na conta porque é largura também: um grupo que perde todos os botões
    perde o separador.

    **Itens de mesma prioridade são um bloco**: entram juntos ou não entram. É o par "Promover" /
    "Rebaixar" -- um sem o outro é um botão que sobe e nenhum que desce --, e é o que faz "mesma
    prioridade" querer dizer alguma coisa em vez de ser desempatada pela posição na tabela.

    Um `disponivel` menor que a reserva devolve vazio: tudo no "Mais", e a fila continua sendo uma.
    """
    blocos: dict[int, list[int]] = {}
    for indice, item in enumerate(itens):
        blocos.setdefault(item.prioridade, []).append(indice)
    dentro: list[int] = []
    for prioridade in sorted(blocos):
        tentativa = [*dentro, *blocos[prioridade]]
        grupos = {itens[i].grupo for i in tentativa}
        largura = sum(itens[i].largura for i in tentativa)
        largura += espaco * len(tentativa)  # o vão antes de cada item; o do "Mais" conta abaixo
        largura += (len(grupos) - 1) * (separador + espaco)
        largura += reserva
        if largura > disponivel:
            break
        dentro = tentativa
    return frozenset(dentro)
