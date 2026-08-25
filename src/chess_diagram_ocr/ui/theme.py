"""O tema da janela (S-53, parte (a)).

`ttkbootstrap` é a única mudança de interface que a Fase 10 faz, e a razão é que ela é a
única que não fecha porta nenhuma: **mesma API de widget**, `ttk.Treeview` intacto, e todo o
código de painel continua igual. Custo de um dia, risco quase nulo.

`CustomTkinter` ficou de fora por um motivo objetivo e não estético: não tem equivalente
decente de `Treeview`, então a aba Dataset continuaria em `ttk` e a tela ficaria com dois
visuais. O porte para Qt fica adiado por **gatilho**, e os dois gatilhos estão registrados
no `ARCHITECTURE.md` -- não aqui, porque quem os procura não vai procurar num módulo de tema.

**A degradação é o contrato.** Se `ttkbootstrap` não estiver instalado, a janela abre em
`ttk` puro exatamente como antes, e o log diz isso uma vez. Um checkout sem o extra, um
bundle que não o incluiu ou um tema com nome errado não podem impedir o app de abrir --
tema é aparência, e aparência não derruba ferramenta.
"""

from __future__ import annotations

import logging
import os
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TypeVar

from . import pele, tipografia, tokens

logger = logging.getLogger(__name__)

_Pintavel = TypeVar("_Pintavel", bound=tk.Misc)
"""Devolver o **mesmo** tipo é o que preserva `lbl.config(text=...)` no ponto de chamada --
a mesma razão de `barra.BarraFluida.adicionar` ser genérica."""

__all__ = [
    "DEFAULT_THEME",
    "ESTILO_DE_ABAS_DISCRETO",
    "TEMA_ESCURO",
    "altura_de_linha_atual",
    "ao_repintar",
    "apply_theme",
    "available_themes",
    "cor_atual",
    "estilo_atual",
    "fonte_atual",
    "fonte_base",
    "pintar",
    "repintar",
]

DEFAULT_THEME = "bootstrap-light"
"""Claro, alto contraste e sóbrio.

A escolha não é gosto: o produto é ler diagrama impresso em papel branco e comparar com o
que o modelo leu. Um tema escuro põe o tabuleiro claro do `InteractiveBoard` e a página
renderizada do PDF sobre fundo preto, e o olho passa a corrigir contraste em vez de
posição. `CVOFF_TTK_THEME` troca para quem discordar -- `available_themes()` lista os 30.

É um nome da era 2.0 de propósito. Os nomes antigos (`litera`, `flatly`, ...) ainda
resolvem, mas cada abertura da janela emitiria um `DeprecationWarning`, e a biblioteca diz
que eles saem na 3.0.
"""

TEMA_ESCURO = "bootstrap-dark"
"""O par escuro do padrão, para a pele que declara `cromo_escuro` (S-224).

Não é um tema novo nem uma paleta nova: é o irmão do `bootstrap-light` na mesma família, e a
biblioteca declara os dois. Escolher um tema de outra família mudaria acento e raio de borda
junto com o fundo, e a pele "Foco" não pediu isso -- ela pediu cromo escuro."""

THEME_ENV = "CVOFF_TTK_THEME"

_cromo_escuro = False
"""Se a pele em uso declara cromo escuro. Módulo e não parâmetro porque `cor_atual` é chamada
de quinze lugares que não conhecem pele nenhuma -- e não deviam conhecer."""

_repinturas: list[Callable[[], None]] = []
"""O que precisa ser repintado quando o tema ou a pele mudam (S-224).

**O defeito que isto fecha.** Seis pontos da janela leem a cor **na construção** e a guardam no
widget: o fundo do canvas do PDF, o do tabuleiro, o do quadro rolável e três rótulos. Trocar de
pele em execução -- que a S-222 passou a permitir -- deixava os seis com a cor da pele anterior,
e o docstring de `registrar_estilos` já previa por escrito que trocar de tema em execução
"precisa reaplicá-la". Reaplicar o estilo nomeado não alcança quem pintou fora do `Style`.

Quem pinta se registra ao lado de onde pintou, numa linha; quem troca a pele chama `repintar`."""


def available_themes() -> list[str]:
    """Nomes de tema que este ambiente aceita. Vazio quando `ttkbootstrap` não está lá."""
    try:
        import ttkbootstrap as tb
    except ImportError:
        return []
    return sorted(tb.Style().theme_names())


def apply_theme(
    root: tk.Misc,
    theme: str | None = None,
    *,
    cromo_escuro: bool = False,
    densidade: str = pele.CONFORTAVEL,
) -> str:
    """Aplica o tema e devolve o que de fato ficou valendo.

    Devolve o nome do tema `ttkbootstrap` em uso, ou `"ttk"` quando a biblioteca não está
    instalada. Nunca levanta: chamar isto não pode ser o motivo de a janela não abrir.

    **A pele só sugere, e o eixo continua separado** (S-221/S-224). A ordem é: o argumento
    explícito, a variável de ambiente, o padrão da pele, o padrão do programa. Quem escreveu
    `CVOFF_TTK_THEME` continua mandando -- e é o que mantém possível a combinação que a S-221
    quis preservar: a pele escura com o tema claro, se alguém decidir isso.
    """
    padrao_da_pele = TEMA_ESCURO if cromo_escuro else DEFAULT_THEME
    escolhido = theme or os.environ.get(THEME_ENV) or padrao_da_pele
    global _cromo_escuro
    _cromo_escuro = cromo_escuro

    try:
        import ttkbootstrap as tb
    except ImportError:
        logger.info(
            "ttkbootstrap não está instalado: a janela abre no tema padrão do ttk. "
            "`uv sync` traz a biblioteca; nada mais muda (S-53)."
        )
        return "ttk"

    # `tb.Style` nao recebe `master`: ele se prende ao root **padrao** do Tk. Dai `root` ser
    # parametro obrigatorio desta funcao mesmo sem ser repassado -- ele documenta a
    # pre-condicao real, que e existir uma janela antes de haver tema.
    if root is None:  # pragma: no cover - guarda de chamador, não de ambiente
        raise ValueError("apply_theme precisa da janela já criada: o tema se prende ao root do Tk.")

    try:
        style = tb.Style(theme=escolhido)
        # **O `theme=` do construtor não volta atrás, e isso foi medido** (S-224). `tb.Style` é
        # um singleton: instanciá-lo de novo com outro tema leva do claro ao escuro e **não**
        # leva do escuro ao claro -- o objeto continua o mesmo e o nome não muda. Só a troca de
        # pele expôs isso, porque até a S-222 ninguém trocava de tema com a janela aberta.
        # `theme_use` faz os dois sentidos, e chamá-lo quando o tema já é o pedido custa nada.
        if str(getattr(style.theme, "name", "")) != escolhido:
            style.theme_use(escolhido)
    except (tk.TclError, ValueError, KeyError, AttributeError) as exc:
        logger.warning(
            "Tema %r recusado (%s). Voltando para %r. Temas disponíveis: %s",
            escolhido,
            exc,
            DEFAULT_THEME,
            ", ".join(available_themes()) or "nenhum",
        )
        try:
            style = tb.Style(theme=DEFAULT_THEME)
        except Exception:  # noqa: BLE001 - aparência não derruba a ferramenta
            logger.warning("Nem o tema padrão foi aceito: seguindo com o ttk puro.")
            return "ttk"

    nome = str(getattr(style.theme, "name", escolhido))
    logger.info("Tema da interface: %s (ttkbootstrap).", nome)
    # Depois do tema, e dentro desta função de propósito (S-149): estilo declarado antes é
    # sobrescrito pelo tema, e deixar a ordem a cargo do chamador é o tipo de dependência
    # invisível que produz "funciona aqui e não lá". Aplicar o tema é aplicá-lo inteiro.
    registrar_estilos(densidade=densidade)
    repintar()
    return nome


# ------------------------------------------------------------------ a ponte com os tokens


def estilo_atual() -> ttk.Style | None:
    """O `Style` que a janela está usando agora, ou `None` se não houver janela.

    Existe porque `ui/tokens.py` não importa `tkinter` — é o que permite afirmar a paleta
    inteira sem abrir janela — e alguém precisa levar o `Style` até lá. Este módulo já é o que
    sabe de tema, então a ponte mora aqui e não num painel.

    `ttk.Style()` se prende ao root **padrão** do Tk; sem root ele levanta, e um painel que
    pergunta a cor antes de existir janela é erro de ordem, não de tema.
    """
    try:
        return ttk.Style()
    except (tk.TclError, RuntimeError):  # pragma: no cover - sem root: cai na reserva
        return None


def ao_repintar(repintura: Callable[[], None]) -> None:
    """Registra o que refazer quando o tema ou a pele mudarem. Chame ao lado de onde pintou.

    A alternativa era um método `repintar()` em cada painel, e ela erra por onde a S-224 mediu:
    o painel que pinta **um** canvas passaria a ter um método público sobre cor, e quem trocasse
    a pele teria de lembrar de chamá-lo em cinco painéis. Aqui a lembrança é local -- quem pinta
    registra na linha seguinte -- e quem troca a pele chama um lugar só.
    """
    _repinturas.append(repintura)


def repintar() -> None:
    """Refaz o que foi pintado fora do `Style`. Nunca levanta, e esquece o que já morreu.

    Um widget destruído entre o registro e a troca não é erro: é a janela de antes. Ele sai da
    lista em vez de derrubar a repintura dos outros -- aparência não derruba ferramenta.
    """
    vivos: list[Callable[[], None]] = []
    for repintura in _repinturas:
        try:
            repintura()
        except tk.TclError:
            continue
        except Exception as exc:  # noqa: BLE001 - uma repintura que falha não derruba as outras
            logger.warning("Repintura falhou e foi descartada: %s", exc)
            continue
        vivos.append(repintura)
    _repinturas[:] = vivos


def pintar(widget: _Pintavel, opcao: str, papel: str) -> _Pintavel:
    """Pinta a opção do widget com a cor do papel, **e a repinta quando a pele mudar**.

    Devolve o próprio widget, para caber no ponto de chamada onde o widget já era anônimo --
    `texto.acompanhar(theme.pintar(ttk.Label(...), "foreground", tokens.TEXTO_SECUNDARIO))`.

    É o par de `ao_repintar` para o caso comum, e existe porque o caso comum é justamente o que
    se esquece: um `foreground=` no construtor guarda a cor no widget e nunca mais olha para o
    papel. Numa janela de um tema só isso nunca apareceu; com uma pele escura, é meia dúzia de
    rótulos ilegíveis (S-224).
    """

    def aplicar() -> None:
        widget.configure(**{opcao: cor_atual(papel)})

    aplicar()
    ao_repintar(aplicar)
    return widget


def cor_atual(papel: str) -> str:
    """Um papel da S-145 resolvido contra o tema em uso (S-147).

    É o que os painéis chamam. Sem janela, sem `ttkbootstrap` ou com um `Style` que não
    responde, devolve a reserva clara — o mesmo contrato de degradação do resto do módulo.

    Papel desconhecido **levanta**, e isso é de propósito: a tolerância aqui é a tema ausente,
    não a papel escrito errado (ver `tokens.cor`).
    """
    return tokens.cor(papel, estilo_atual(), cromo_escuro=_cromo_escuro)


FAMILIA_DE_RESERVA = ("Segoe UI", "Consolas")
"""Família proporcional e monoespaçada de quando o Tk não responde.

São as duas que a janela já usava cravadas, e ficam aqui como **último** recurso: o caminho
normal é perguntar à `TkDefaultFont` e à `TkFixedFont`, que é o que faz a escala acompanhar a
configuração de fonte do Windows em vez de ignorá-la."""


def fonte_base() -> tuple[int, str, str]:
    """`(tamanho, família proporcional, família monoespaçada)` do sistema (S-149).

    Lidas da `TkDefaultFont` e da `TkFixedFont`, que é o que o Tk expõe da configuração do
    sistema. **É daqui que a escala inteira deriva**: quem aumenta a fonte do Windows aumenta a
    do programa, e uma escala de números fixos ignoraria isso.

    O tamanho vem negativo quando o Tk o expressa em pixels em vez de pontos; o sinal some
    porque a escala só precisa da magnitude, e um `-9` cravado num `font=` desenha do mesmo
    tamanho que `9` em quase toda tela.
    """
    tamanho, proporcional, monoespacada = 9, *FAMILIA_DE_RESERVA
    try:
        from tkinter import font as tkfont

        padrao = tkfont.nametofont("TkDefaultFont")
        tamanho = abs(int(padrao.cget("size"))) or tamanho
        proporcional = str(padrao.cget("family") or proporcional)
        do_tk = str(tkfont.nametofont("TkFixedFont").cget("family") or monoespacada)
        monoespacada = tipografia.familia_monoespacada(tkfont.families(), do_tk)
    except Exception as exc:  # noqa: BLE001 - sem root, sem Tk ou fonte exótica: a reserva serve
        logger.debug("Fonte do sistema não lida (%s): usando %s.", exc, FAMILIA_DE_RESERVA)
    return tamanho, proporcional, monoespacada


def fonte_atual(papel: str, *, negrito: bool = False) -> tuple[str, int] | tuple[str, int, str]:
    """Um papel da S-149 resolvido contra a fonte do sistema. É o que os painéis chamam.

    Como `cor_atual`: tolerante a ambiente, intolerante a papel escrito errado.
    """
    tamanho, proporcional, monoespacada = fonte_base()
    return tipografia.fonte(papel, base=tamanho, familia=proporcional, mono=monoespacada, negrito=negrito)


def altura_de_linha_atual(densidade: str = pele.CONFORTAVEL) -> int:
    """A altura de linha do `Treeview` para esta fonte e esta densidade, em pixel (S-232).

    O `linespace` vem do Tk quando há janela e da conta de `tipografia` quando não há -- a mesma
    reserva de `fita.linhas_de_fonte`, e pela mesma razão: a decisão continua afirmável sem root.

    **É `"Treeview"` e não um estilo nomeado.** Um estilo próprio exigiria `style=` nas duas
    tabelas do programa, e a primeira que alguém esquecesse ficaria na altura de fábrica -- que é
    o argumento de `ESTILO_DE_TITULO`, aqui ao lado, e o defeito que a S-153 mediu quando as duas
    tabelas erravam a mesma coisa por serem duas cópias.
    """
    base, _proporcional, _mono = fonte_base()
    reserva = round(tipografia.escala(base)[tipografia.CORPO] * 5 / 3)
    try:
        from tkinter import font as tkfont

        linha = int(tkfont.Font(font=fonte_atual(tipografia.CORPO)).metrics("linespace")) or reserva
    except Exception:  # noqa: BLE001 - sem root ou fonte exótica: a reserva serve
        linha = reserva
    return tipografia.altura_de_linha(linha, densidade=densidade)


ESTILO_DE_TABELA_DE_DADOS = "Dado.Treeview"
"""Nome do estilo de `Treeview` cujo corpo é monoespaçado. Pedido por quem quer, e são poucos."""

ESTILO_DE_TITULO = "TLabelframe.Label"

ESTILO_DE_ABAS_DISCRETO = "Discreta.TNotebook"
"""A faixa de abas da pele "Foco" (S-226): sem moldura em relevo, e a diferença no **peso**.

A Imagem 1 não desenha faixa de abas nenhuma, e adotá-la ao pé da letra apagaria sete abas -- o
que a regra 2 proíbe. O que entra da imagem é o peso: a barra deixa de ser um relevo com sete
caixas e passa a ser sete palavras, das quais uma está acesa.

**A aba ativa se separa por cor e por negrito, e não por sublinhado.** Sublinhar exigiria um
`layout` de elemento próprio para a aba, que é escrito por tema e quebra em cada um dos trinta;
cor e peso de fonte são opções que todo tema aceita. A diferença que importa -- qual aba está
aberta -- fica dita por dois canais em vez de um."""
"""O rótulo de `LabelFrame`, **sem** prefixo: todo `LabelFrame` desta janela é título de grupo.

Um estilo nomeado exigiria `style=` nos 20 e poucos grupos da janela, e o primeiro que alguém
esquecesse voltaria ao corpo sem nada avisar. Redefinir o padrão faz a escala valer por
construção -- e se um dia existir um `LabelFrame` que não seja título, ele é que pede o
prefixo."""


def registrar_estilos(*, densidade: str = pele.CONFORTAVEL) -> None:
    """Declara no `Style` os papéis que só um estilo nomeado alcança (S-149). Nunca levanta.

    **Por que dois deles não cabem num `font=` de widget.**

    `ttk.Treeview` aplica a fonte à tabela inteira: não existe fonte por coluna. A coluna que
    pede monoespaçada é a de FEN, e a do Dataset é uma tabela de **dados** de ponta a ponta --
    arquivo, FEN, livro, data. Aplicar ao corpo inteiro é a leitura certa desse painel; a fila
    de Revisão, cuja coluna larga é prosa ("Motivo"), fica de fora de propósito.

    `LabelFrame` desenha o próprio rótulo por um sub-estilo, e um `font=` no construtor do
    widget não o alcança.

    Chamada pelo próprio `apply_theme`, no fim: estilo declarado antes do tema é sobrescrito
    por ele. Pública porque o teste a chama direto, e porque trocar de tema em execução — o que
    `CVOFF_TTK_THEME` permite entre execuções e um menu de preferências vai permitir dentro de
    uma — precisa reaplicá-la.
    """
    style = estilo_atual()
    if style is None:  # pragma: no cover - sem root não há estilo a registrar
        return
    try:
        style.configure(ESTILO_DE_TABELA_DE_DADOS, font=fonte_atual(tipografia.DADO))
        style.configure(ESTILO_DE_TITULO, font=fonte_atual(tipografia.TITULO))
    except tk.TclError as exc:  # pragma: no cover - Style exótico: a janela abre sem a escala
        logger.info("Estilos de tipografia não registrados (%s).", exc)

    # Bloco próprio, pela razão de sempre: a altura de linha é da S-232 e a tipografia é da
    # S-149, e um tema que recuse uma não pode levar a outra junto.
    try:
        style.configure("Treeview", rowheight=altura_de_linha_atual(densidade))
    except tk.TclError as exc:  # pragma: no cover - tema que não aceita `rowheight`
        logger.info("Altura de linha da tabela não registrada (%s).", exc)

    # Bloco próprio: um tema que recuse o estilo de abas não pode levar junto a tipografia, que
    # é de outro item. Aparência não derruba ferramenta, e uma metade não derruba a outra.
    try:
        style.configure(ESTILO_DE_ABAS_DISCRETO, borderwidth=0, tabmargins=(2, 6, 2, 0))
        style.configure(f"{ESTILO_DE_ABAS_DISCRETO}.Tab", borderwidth=0, padding=(14, 6))
        style.map(
            f"{ESTILO_DE_ABAS_DISCRETO}.Tab",
            foreground=[
                ("selected", cor_atual(tokens.TEXTO_PADRAO)),
                ("!selected", cor_atual(tokens.TEXTO_SECUNDARIO)),
            ],
            font=[("selected", fonte_atual(tipografia.CORPO, negrito=True))],
        )
    except tk.TclError as exc:  # pragma: no cover - tema que não aceita estilo de Notebook
        logger.info("Estilo de abas discreto não registrado (%s).", exc)
