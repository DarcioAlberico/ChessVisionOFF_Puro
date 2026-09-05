"""O que o rodapé **decide**, sem tocar em toolkit nenhum (S-163/S-501).

Severidade de uma mensagem, quando ela expira, e as descrições do documento, dos dispositivos e
da operação em curso. São funções puras, e o docstring de `ui/rodape.py` já dizia por que elas
existem apartadas do widget: é o que permite afirmar "erro não expira" e "a página concluída fala
em verde" sem abrir janela, no mesmo espírito de `ui/busy.py`.

**Por que elas mudaram de arquivo na S-501.** Faltava a consequência de estarem apartadas. O
`ui/rodape.py` importava `tkinter` na primeira linha do corpo, e tinha de importar:
`RodapeDaJanela` herdava de `ttk.Frame`, e classe-base é avaliada na importação. Então a decisão pura era pura e,
ainda assim, ninguém conseguia lê-la sem carregar o Tk junto.

O segundo frontend precisa exatamente destas funções e de widget nenhum. Copiá-las daria duas
tabelas de severidade para manter, e a primeira mensagem de erro que uma reconhecesse e a outra
não seria uma janela dizendo "isto falhou" em vermelho e a outra dizendo o mesmo em cinza -- que
é o defeito 3 do cabeçalho de `ui/rodape.py`, agora entre janelas.

`ui/rodape.py` reexportava tudo o que está aqui, e saiu inteiro no corte do Tk (S-506). Quem
consome agora é `qt/rodape.py`, `qt/janela.py` e `ui/dispositivos.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from . import tokens
from .busy import BusyOperation

logger = logging.getLogger(__name__)





# ------------------------------------------------------------------------- severidade

INFORMACAO = "INFO"
"""O caso comum: uma confirmação do que acabou de ser feito.

O valor é `"INFO"` e não `"INFORMACAO"` porque a varredura de acentuação da S-04 procura
`informacao` nos literais de `ui/` -- e ela está certa em não distinguir chave de texto de tela:
uma exceção ali seria a brecha por onde volta a string que o usuário lê errada. Mudar a chave é
mais barato que abrir a guarda, e nenhuma das três chaves aparece na tela."""

AVISO = "AVISO"
"""Algo não aconteceu, e a pessoa precisa de outra ação para que aconteça."""

ERRO = "ERRO"
"""Falhou. É a única severidade que **não expira** — ver `EXPIRACAO_MS`."""

SEVERIDADES: tuple[str, ...] = (INFORMACAO, AVISO, ERRO)

PAPEL_DE_TEXTO: dict[str, str] = {
    INFORMACAO: tokens.TEXTO_PADRAO,
    AVISO: tokens.ATENCAO,
    ERRO: tokens.PROBLEMA_TEXTO,
}
"""Severidade → papel de cor da S-145. Os três são papéis de **texto**, e isso não é detalhe.

`ATENCAO` é o âmbar escuro `#8a5a00` e não o `#ffb02e` da marcação, justamente porque este aqui
vai ser lido como letra: a S-146 mediu que o âmbar da caixa reprova em contraste como texto. O
teste deste módulo afirma os três contra a superfície da janela, com número."""

MARCAS_DE_ERRO: tuple[str, ...] = (
    "falha",
    "falhou",
    "erro",
    "não foi possível",
    "não pôde",
    "inválid",
    "corrompid",
    "ilegível",
)
"""Marcas de que a frase relata uma falha.

**Por que inferir, e não só declarar.** `_set_status` tem 60 e poucos chamadores em seis painéis,
e todos escrevem uma frase pronta. Quem chama **pode** declarar a severidade — o parâmetro
existe e é o caminho preferido —, mas exigir isso de todos os 60 no mesmo item significaria ou
uma passada mecânica sem leitura, ou um rodapé que só sabe colorir os poucos convertidos. A
inferência é o piso: nenhuma frase de falha fica cinza por esquecimento.

A lista é de raízes e não de palavras: "inválid" pega inválido, inválida e inválidas."""

MARCAS_DE_AVISO: tuple[str, ...] = ("⚠", "não encontrad", "cancelad", "aguarde", "abra um pdf")
"""Marcas de que a frase pede uma ação antes de a coisa acontecer.

"Abra um PDF primeiro" não é erro do programa nem confirmação de trabalho: é a resposta de que
falta um passo — e é uma das frases que hoje abre `messagebox` só por não ter onde ser lida."""

EXPIRACAO_MS: dict[str, int | None] = {INFORMACAO: 20_000, AVISO: 40_000, ERRO: None}
"""Quanto tempo cada severidade fica na tela. `None` = fica até ser substituída.

**20 s para informação, e o número tem motivo.** É mais que a olhada que segue um clique e menos
que o gesto seguinte; o defeito 2 acima é uma mensagem verdadeira que virou mobília — "Dataset
carregado: 3936 amostras." lida uma vez e depois ocupando o rodapé por meia hora de trabalho na
Galeria.

**Erro não expira.** Um erro que a pessoa não leu é um erro que não aconteceu, e ela pode estar
com os olhos na página do livro no segundo em que ele apareceu. Ele sai quando a mensagem
seguinte o substituir, que é quando existe algo mais recente para dizer."""


def severidade_de(texto: str) -> str:
    """A severidade que a frase relata, quando quem a escreveu não declarou.

    A ordem das duas listas importa: "Não foi possível abrir o arquivo" tem marca de erro **e**
    de aviso, e é erro. Frase vazia é informação — o rodapé limpo não é um estado de alarme.
    """
    frase = str(texto).casefold()
    if any(marca in frase for marca in MARCAS_DE_ERRO):
        return ERRO
    if any(marca in frase for marca in MARCAS_DE_AVISO):
        return AVISO
    return INFORMACAO


def expira_em_ms(severidade: str) -> int | None:
    """Em quantos milissegundos a mensagem sai da tela, ou `None` quando ela fica.

    Levanta `KeyError` para severidade desconhecida, como `tokens.cor` e `estilos.estilo_de_botao`:
    uma severidade escrita errada que caísse no padrão viraria um erro que expira em silêncio.
    """
    if severidade not in EXPIRACAO_MS:
        raise KeyError(f"severidade desconhecida: {severidade!r}. As válidas estão em SEVERIDADES.")
    return EXPIRACAO_MS[severidade]


def com_origem(texto: str, origem: str = "") -> str:
    """A mensagem com o painel que a escreveu à frente, quando há um.

    É a metade legível do defeito 2: a mensagem continua sendo a última de qualquer painel, mas
    passa a dizer **de qual** — "Dataset: 3.936 amostras carregadas" lido enquanto se trabalha na
    Galeria é informação; a mesma frase sem dono é confusão.
    """
    frase = str(texto).strip()
    nome = str(origem).strip()
    return f"{nome}: {frase}" if (frase and nome) else frase


# ------------------------------------------------------- o estado do documento (zona 2)


def descricao_dos_diagramas(
    total: int, *, lidos: int = 0, salvos: int = 0, confirmados: int = 0, todos_salvos: bool = False
) -> str:
    """O que se sabe dos diagramas da página exibida.

    **Veio da barra de zoom do visualizador**, onde estava espremida no fim da terceira faixa de
    controles (S-151/S-163): é estado do documento, não controle de visualização, e a diferença
    aparece quando a barra reflui e a frase vai para a segunda linha junto com o botão de zoom.

    Só a fração em "N de M salvo(s)": "2 salvo(s)" não diz se falta um ou sete, e é a fração que
    decide se vale terminar a página agora ou virá-la (S-142).
    """
    if total <= 0:
        return "nenhum diagrama nesta página"
    if todos_salvos:
        # Uma frase, e não mais uma parcela na soma (S-142): a página concluída é o único estado
        # em que não sobra nada a fazer, e ele merece ser lido sem contar.
        return f"✓ página concluída · {total} diagrama(s) salvo(s)"
    partes = [f"{total} diagrama(s)"]
    if lidos:
        partes.append(f"{lidos} lido(s)")
    if confirmados:
        partes.append(f"{confirmados} confirmado(s) pela base")
    if salvos:
        partes.append(f"{salvos} de {total} salvo(s)")
    return " · ".join(partes)


def papel_do_documento(todos_salvos: bool) -> str:
    """A cor do estado do documento: verde na página concluída, cinza de apoio no resto.

    O verde é o mesmo significado que os retângulos da página já dizem de cada diagrama (S-142),
    e é `PRONTO_TEXTO` e não `PRONTO` porque aqui ele é letra — a distinção que a S-146 mediu.
    """
    return tokens.PRONTO_TEXTO if todos_salvos else tokens.TEXTO_SECUNDARIO


def descricao_do_documento(livro: str, pagina: int | None = None, total: int | None = None, diagramas: str = "") -> str:
    """`Karpov A · p. 12 de 402 · 3 de 5 salvo(s)` — o que está aberto, num lugar só.

    Sem livro não há documento e a zona fica vazia: um "p. 1 de 0" seria pior que nada. A página
    é dita em base 1, como o campo da tela e como o título da janela (S-167) — e uma página fora
    da faixa é omitida em vez de mostrada, pela mesma razão daquele item.
    """
    nome = str(livro).strip()
    if not nome:
        return ""
    partes = [nome]
    if pagina is not None and pagina >= 0 and (total is None or pagina < total):
        partes.append(f"p. {pagina + 1} de {total}" if total else f"p. {pagina + 1}")
    if diagramas.strip():
        partes.append(diagramas.strip())
    return " · ".join(partes)


# ------------------------------------------------------ os dois modelos torch (zona 4)

# **Desde 2026-08-23 a janela tem dois modelos torch.** O de peças (8,8 MB) e o de caracteres
# (2,6 MB) passam a conviver no mesmo processo, e cada um escolhe o dispositivo por conta
# própria: `inference.load_model` e `text.modelo._escolher_device` fazem a mesma pergunta ao
# torch em dois lugares diferentes. É o risco 5 do `ROADMAP_TEXTO`, e o que ele prevê é a
# repetição do defeito que a S-30 mediu -- uma máquina com placa mas com o torch `+cpu`
# instalado roda na CPU **em silêncio**, e a diferença entre 7,5 min e ~45 s por época era
# invisível.
#
# Com dois modelos o silêncio fica pior, porque eles podem discordar: nada impede que o de peças
# esteja em `cuda:0` e o de caracteres em `cpu` na mesma sessão. A zona diz os dois, sempre, e a
# dica carrega a descrição inteira -- o nome da placa não cabe no rodapé e não deve custar
# largura à mensagem.

SEM_MODELO = "ainda não"
"""O de peças carrega na primeira leitura, e não ao abrir a janela: até lá não há dispositivo.

Dizer "ainda não" e não "cpu" é a diferença entre o que se sabe e o que se supõe -- e supor aqui
é o mesmo erro que a S-30 nomeia."""

SEM_PESOS = "sem pesos"
"""O de caracteres não vem no repositório: 2,6 MB de binário, e `*.pt` é ignorado desde a S-29.

Este é o estado de **todo clone**, e por isso ele é um texto normal da zona e não um aviso: a
janela funciona inteira sem o classificador de caracteres. Onde apontar o arquivo é a dica, que
vem de `OcrSettings.glyph_disabled_reason` (S-182)."""

DESLIGADO = "desligado"
"""Os pesos estão no disco, e mesmo assim não há classificador de caracteres carregado.

**São dois estados diferentes e dizê-los com a mesma palavra esconderia o mais comum dos dois.**
O motor de leitura é uma preferência (S-42): com `rapidocr` escolhido, ou com o OCR de legenda
desligado, o `glifo` não sobe -- e ninguém precisa procurar um arquivo que já está lá."""


def _dispositivo_curto(descricao: str) -> str:
    """`cuda:0 (NVIDIA GeForce RTX 4060)` -> `cuda:0`. O resto vai para a dica."""
    return descricao.strip().split(" ", 1)[0]


def dispositivo_do_classificador_de_pecas(descricao: str | None) -> str:
    """`peças cuda:0`. `None` é "ainda não carregado", que é o estado ao abrir a janela.

    `descricao` é o que `inference.describe_device` devolve -- a longa, com o nome da placa --,
    e não o `"cuda"` cru: quem sabe se a CUDA pedida está de fato disponível é aquela função, e
    duplicar a pergunta aqui daria duas respostas para um fato só.
    """
    return f"peças {_dispositivo_curto(descricao) if descricao else SEM_MODELO}"


def dispositivo_do_classificador_de_caracteres(descricao: str | None, *, ausencia: str = SEM_PESOS) -> str:
    """`texto cpu`. `None` é "não há classificador de caracteres carregado" (S-182).

    **`None` não é falha.** O metadado das classes é versionado e os pesos não, então o clone
    limpo cai aqui por construção -- e a zona diz isso em vez de ficar muda, que era o defeito
    que o item nomeia: o motor `glifo` silenciosamente desligado, sem ninguém saber por quê.

    `ausencia` distingue as duas razões de não haver um: `SEM_PESOS`, o padrão, e `DESLIGADO`,
    para quando os pesos estão no disco e o motor escolhido é outro. Quem sabe qual é o caso é
    quem lê a configuração, e não o rodapé.
    """
    return f"texto {_dispositivo_curto(descricao) if descricao else ausencia}"


@dataclass(frozen=True)
class Dispositivos:
    """O que a zona 4 mostra, vindo de quem carrega os modelos.

    Existe para que `acompanhar` peça **uma** coisa por tique em vez de quatro argumentos
    posicionais que ninguém lê na ordem certa -- o mesmo motivo de `Ocupacao`. Os padrões são o
    estado de quem acabou de abrir a janela num clone limpo.
    """

    pecas: str | None = None
    caracteres: str | None = None
    motivo: str = ""
    ausencia: str = SEM_PESOS


def descricao_dos_dispositivos(
    pecas: str | None, caracteres: str | None, *, motivo: str = "", ausencia: str = SEM_PESOS
) -> tuple[str, str]:
    """`(o que a zona mostra, a dica que ela carrega)`.

    A dica traz as descrições por extenso porque é onde elas cabem, e o `motivo` da ausência dos
    pesos quando há um -- ele diz **onde apontar o arquivo**, e uma zona de rodapé não tem
    largura para um caminho.
    """
    curto = (
        f"{dispositivo_do_classificador_de_pecas(pecas)} · "
        f"{dispositivo_do_classificador_de_caracteres(caracteres, ausencia=ausencia)}"
    )

    longo = [
        f"Classificador de peças: {pecas or 'ainda não carregado; ele entra na primeira leitura.'}",
        f"Classificador de caracteres: {caracteres or 'pesos ausentes.'}",
    ]
    if not caracteres and motivo.strip():
        longo.append(motivo.strip())
    return curto, "\n".join(longo)


# ---------------------------------------------------------- a operação em curso (zona 3)

PARADO = "PARADO"
"""Nada rodando: a barra fica vazia e o botão de cancelar, desabilitado."""

INDETERMINADO = "INDETERMINADO"
"""Roda sem total conhecido — a barra anda, e o que informa é o `detail` ao lado."""

DETERMINADO = "DETERMINADO"
"""Roda com total conhecido — a barra mostra a fração, e ela responde "quanto falta?" (S-164).

As três operações longas do produto sabem o total: páginas do livro na exportação, páginas na
varredura da Galeria e da fila, épocas no treino. A busca por nome na base não sabe, e é por isso
que os dois modos existem em vez de um."""


@dataclass(frozen=True)
class Ocupacao:
    """O que a zona de operação mostra, decidido a partir do `BusyRegistry`."""

    modo: str
    fracao: float | None
    texto: str
    cancelavel: bool


def ocupacao(operacoes: Sequence[BusyOperation]) -> Ocupacao:
    """A projeção de `BusyRegistry.running()` para o que a barra do rodapé mostra (S-164).

    Uma operação fala o nome dela com o detalhe que ela mesma mantém ("época 3 de 8"), e a barra
    fica determinada quando ela sabe o total; duas ou mais falam a contagem, porque três nomes
    numa linha não caberiam e a pergunta que sobra é "ainda há coisa rodando?".

    **Duas operações voltam ao modo indeterminado, e isso é escolha.** Somar frações de coisas
    diferentes -- 120 de 402 páginas com 3 de 8 épocas -- daria um número que não é o progresso de
    nada; e mostrar a fração de uma só faria a barra falar de uma operação enquanto o texto ao
    lado fala das duas.
    """
    if not operacoes:
        return Ocupacao(PARADO, None, "", False)
    cancelavel = any(operacao.cancellable for operacao in operacoes)
    if len(operacoes) > 1:
        return Ocupacao(INDETERMINADO, None, f"{len(operacoes)} operações em andamento", cancelavel)
    unica = operacoes[0]
    fracao = unica.fracao
    modo = INDETERMINADO if fracao is None else DETERMINADO
    return Ocupacao(modo, fracao, unica.describe(), cancelavel)


# ------------------------------------------------------------------- as três zonas juntas


@dataclass(frozen=True)
class Estado:
    """As três zonas resolvidas. É o que o widget desenha, e o que o teste afirma."""

    mensagem: str
    severidade: str
    documento: str
    papel_do_documento: str
    ocupacao: Ocupacao


def compor(
    *,
    mensagem: str = "",
    origem: str = "",
    severidade: str | None = None,
    documento: str = "",
    todos_salvos: bool = False,
    operacoes: Sequence[BusyOperation] = (),
) -> Estado:
    """As três zonas a partir de (mensagem, origem, operações em curso).

    **O que esta função existe para impedir** é o defeito 2 dito por inteiro: as três zonas são
    independentes, então um painel que escreve uma mensagem não apaga o livro e a página em que a
    pessoa está, e uma operação que termina não apaga a mensagem que ela deixou.
    """
    texto = com_origem(mensagem, origem)
    return Estado(
        mensagem=texto,
        severidade=severidade if severidade is not None else severidade_de(texto),
        documento=documento,
        papel_do_documento=papel_do_documento(todos_salvos),
        ocupacao=ocupacao(operacoes),
    )

# ------------------------------------------------------- o que as duas janelas medem igual

INTERVALO_DE_ACOMPANHAMENTO_MS = 400
"""De quanto em quanto tempo o rodapé relê o `BusyRegistry`.

Não é animação: o que muda nesse intervalo é o `detail` de uma operação de minutos. 400 ms é
imperceptível para quem espera e é 2,5 leituras por segundo de um dicionário sob lock."""

FOLGA_ENTRE_ZONAS = 10
LARGURA_DA_BARRA = 120
"""Os dois números de geometria do rodapé.

**Estão aqui, e não em cada widget, porque não são de toolkit nenhum** (S-501): são a largura da
barra de progresso e o vão entre as quatro zonas, e os dois frontends desenham o mesmo rodapé. Um
par de cópias divergiria na primeira vez que alguém achasse a barra estreita numa das janelas."""

LARGURA_MINIMA_DA_MENSAGEM = 100
"""O que a zona de mensagem reserva para si, em pixel -- e o teto do que ela **exige** (S-552).

**É o único número que impede a frase de virar piso de janela.** A zona é um rótulo de uma linha
sem quebra, e o mínimo de um rótulo assim é a largura do texto inteiro: medido a 1024x768, uma
frase de 120 caracteres punha o piso da janela em 1057 px, uma de 600 em 3457 e uma de 2000 em
**10457** -- e `resize(1024, 768)` era recusado até chegar uma frase menor. A frase que o programa
escreve para ensinar a consertar o modelo ausente tem ~600 caracteres, então era justamente o erro
que tornava a janela maior que a tela e a própria mensagem ilegível.

**Somado do que a frase precisa dizer para ser reconhecível, e não escolhido a olho.** O começo é
o que importa numa frase de erro, e o começo mais longo que o projeto reconhece é
`"não foi possível"` -- a maior das `MARCAS_DE_ERRO` --, que mede **82 px** na fonte `CORPO` das
três peles, 91 com a reticência da elisão. Cem é esse número com a folga do arredondamento, pela
razão de `galeria_declarada.LARGURA_DA_LATERAL`: reservar o valor exato de uma fonte deixa a zona
curta na seguinte.

**Ele não sobe o piso da janela**, e é o que faz dele um teto e não uma exigência nova: o resto do
rodapé pede 443 px, e 443 + 100 continua abaixo dos 945 que o divisor já exige. O que passar da
zona é elidido à direita e vai inteiro para a dica -- ver `qt/rodape.py`."""
