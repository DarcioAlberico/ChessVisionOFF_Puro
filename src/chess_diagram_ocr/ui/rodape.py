"""O rodapé da janela: mensagem com severidade, estado do documento e operação em curso (S-163).

**O que havia antes**, uma linha em `app_tkinter.py`:

    ttk.Label(self.left_frame, textvariable=self.status_var).pack(anchor="w", pady=(6, 0))

Um `ttk.Label` cru dentro do **painel esquerdo**, e cinco consequências, todas observadas com a
janela aberta:

1. ficava longe do painel direito, onde o trabalho acontece — a página do PDF é clicada à
   direita e a resposta aparecia embaixo à esquerda;
2. mostrava o que aconteceu por último em **qualquer** painel: "Dataset carregado: 3936
   amostras." permanecia na tela enquanto a pessoa navegava a Galeria;
3. não tinha severidade — erro, aviso e confirmação com a mesma aparência, e é por isso que 73
   `messagebox` foram necessários: a única forma de dizer "isto falhou" era interromper;
4. não tinha altura fixa nem separador, então o comprimento do texto movia o layout acima dele;
5. **saía da janela** quando ela encolhia (S-150).

**Três zonas, e a ordem do `pack` é o item.** Mensagem (esquerda, `expand=True`), estado do
documento e operação em curso (direita). As duas da direita são empacotadas **antes**, porque o
`pack` reparte na ordem em que recebe: ao contrário, uma mensagem longa empurraria para fora
exatamente o que não pode sair — o livro e a página em que a pessoa está. É a mesma lição que a
S-154 mediu na lateral da Galeria.

**A altura é fixa por construção, e não por pixel cravado.** Todo widget do rodapé existe
sempre; o que muda é texto, cor e estado. Nada aparece nem desaparece, então nada muda a altura
— e por isso não há `pack_propagate(False)` com número mágico aqui. O teste mede: a altura
pedida com o rodapé vazio é a mesma com mensagem longa e operação rodando.

**Por que a decisão é pura e mora aqui.** Severidade, expiração e as três descrições são
funções sem `tkinter`: é o que permite afirmar "erro não expira" e "a página concluída fala em
verde" sem abrir janela, no mesmo espírito de `ui/busy.py`.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from tkinter import ttk

from . import theme, tipografia, tokens
from .busy import BusyOperation
from .tooltip import Tooltip

logger = logging.getLogger(__name__)

__all__ = [
    "AVISO",
    "DETERMINADO",
    "ERRO",
    "EXPIRACAO_MS",
    "INDETERMINADO",
    "INFORMACAO",
    "PAPEL_DE_TEXTO",
    "PARADO",
    "SEVERIDADES",
    "Estado",
    "Ocupacao",
    "RodapeDaJanela",
    "compor",
    "descricao_do_documento",
    "descricao_dos_diagramas",
    "expira_em_ms",
    "ocupacao",
    "papel_do_documento",
    "severidade_de",
]


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
    ERRO: tokens.PROBLEMA,
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


# ------------------------------------------------------------------------------ o widget

INTERVALO_DE_ACOMPANHAMENTO_MS = 400
"""De quanto em quanto tempo o rodapé relê o `BusyRegistry`.

Não é animação: o que muda nesse intervalo é o `detail` de uma operação de minutos. 400 ms é
imperceptível para quem espera e é 2,5 leituras por segundo de um dicionário sob lock."""

FOLGA_ENTRE_ZONAS = 10
LARGURA_DA_BARRA = 120


class RodapeDaJanela(ttk.Frame):
    """O rodapé: irmão do `PanedWindow`, e não filho de um painel.

    Quem o cria empacota-o com `side=tk.BOTTOM` **antes** do painel principal — é isso que faz
    dele o último a ser cortado quando a janela encolhe, em vez do primeiro (defeito 5).
    """

    def __init__(self, pai: tk.Misc, *, cancelar: Callable[[], object] | None = None) -> None:
        # `object` e não `None` no retorno: `BusyRegistry.request_cancel` devolve quantas
        # operações foram avisadas, e envolvê-lo num `lambda` só para descartar o número seria
        # uma linha existindo por causa de uma anotação.
        super().__init__(pai)
        self._cancelar = cancelar
        self._expiracao: str | None = None
        self._acompanhamento: str | None = None
        self._modo_da_barra = PARADO

        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, side=tk.TOP)
        linha = ttk.Frame(self, padding=(8, 3))
        linha.pack(fill=tk.X)

        # As duas zonas da direita primeiro: ver o docstring do módulo. A mensagem entra depois,
        # com `expand=True`, e por isso ela cede espaço em vez de tomá-lo.
        self._btn_cancelar = ttk.Button(linha, text="Cancelar", width=10, state=tk.DISABLED, command=self._ao_cancelar)
        self._btn_cancelar.pack(side=tk.RIGHT)
        Tooltip(
            self._btn_cancelar,
            "Só fica ativo quando há operação longa que sabe parar limpo.\n"
            "Cancelar aqui vale para todas as que estiverem rodando.",
        )
        self._barra = ttk.Progressbar(linha, mode="indeterminate", length=LARGURA_DA_BARRA)
        self._barra.pack(side=tk.RIGHT, padx=(FOLGA_ENTRE_ZONAS, 6))
        self._lbl_ocupacao = ttk.Label(linha, text="", font=theme.fonte_atual(tipografia.AUXILIAR))
        self._lbl_ocupacao.pack(side=tk.RIGHT)
        self._lbl_documento = ttk.Label(
            linha,
            text="",
            font=theme.fonte_atual(tipografia.AUXILIAR),
            foreground=theme.cor_atual(tokens.TEXTO_SECUNDARIO),
        )
        self._lbl_documento.pack(side=tk.RIGHT, padx=(FOLGA_ENTRE_ZONAS, FOLGA_ENTRE_ZONAS))
        self._lbl_mensagem = ttk.Label(linha, text="", anchor="w", font=theme.fonte_atual(tipografia.CORPO))
        self._lbl_mensagem.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ------------------------------------------------------------------------- mensagem

    def mostrar(self, texto: str, *, origem: str = "", severidade: str | None = None) -> None:
        """Escreve na zona de mensagem, com a cor da severidade e o prazo dela.

        Chamado da thread da janela. Quem está noutra thread passa por `root.after`, como
        `app_tkinter._set_status` já fazia com a `StringVar` que existia aqui antes.
        """
        estado = compor(mensagem=texto, origem=origem, severidade=severidade)
        self._lbl_mensagem.configure(
            text=estado.mensagem, foreground=theme.cor_atual(PAPEL_DE_TEXTO[estado.severidade])
        )
        self._reagendar_expiracao(expira_em_ms(estado.severidade))

    def mensagem(self) -> str:
        """O que está escrito na zona de mensagem agora.

        Existe para o roteiro headless do `CONTRIBUTING.md`, que lia `app.status_var.get()` -- a
        `StringVar` que este widget substituiu. Um roteiro documentado que não roda é pior que
        nenhum: ele é o que pega o defeito que 2.178 testes verdes não pegam.
        """
        return str(self._lbl_mensagem.cget("text"))

    def _reagendar_expiracao(self, prazo: int | None) -> None:
        if self._expiracao is not None:
            self._cancelar_agendamento(self._expiracao)
            self._expiracao = None
        if prazo is not None:
            self._expiracao = self.after(prazo, self._expirar)

    def _expirar(self) -> None:
        self._expiracao = None
        self._lbl_mensagem.configure(text="")

    # ---------------------------------------------------------------- estado do documento

    def definir_documento(self, texto: str, todos_salvos: bool = False) -> None:
        """A zona do documento: livro, página e o que se sabe dos diagramas dela.

        Os dois parâmetros são posicionais para que o método **seja** o callback que o
        `PdfPanel` espera (`on_document_state`), sem um `lambda` de adaptação no meio.
        """
        self._lbl_documento.configure(
            text=texto, foreground=theme.cor_atual(papel_do_documento(todos_salvos))
        )

    # ------------------------------------------------------------------ operação em curso

    def aplicar_ocupacao(self, operacoes: Sequence[BusyOperation]) -> None:
        """Põe na zona de operação o que o `BusyRegistry` diz que está rodando.

        A troca de modo é feita só quando ele muda -- `start()` chamado a cada tique reiniciaria a
        animação da barra indeterminada quatro vezes por segundo, e ela pareceria travada. O
        **valor** da barra determinada, ao contrário, é escrito em todo tique: é ele que anda.
        """
        atual = ocupacao(operacoes)
        self._lbl_ocupacao.configure(text=atual.texto)
        self._btn_cancelar.configure(state=tk.NORMAL if atual.cancelavel else tk.DISABLED)
        try:
            if atual.modo != self._modo_da_barra:
                self._trocar_modo_da_barra(atual.modo)
            if atual.modo == DETERMINADO and atual.fracao is not None:
                self._barra.configure(value=atual.fracao * 100.0)
        except tk.TclError as exc:  # pragma: no cover - barra destruída entre dois ticks
            logger.debug("Não foi possível atualizar a barra do rodapé: %s", exc)

    def _trocar_modo_da_barra(self, modo: str) -> None:
        self._modo_da_barra = modo
        if modo == INDETERMINADO:
            self._barra.configure(mode="indeterminate")
            self._barra.start(60)
            return
        self._barra.stop()
        self._barra.configure(mode="determinate", maximum=100.0, value=0.0)

    def acompanhar(
        self,
        operacoes: Callable[[], Sequence[BusyOperation]],
        *,
        intervalo_ms: int = INTERVALO_DE_ACOMPANHAMENTO_MS,
    ) -> None:
        """Relê o registro a cada `intervalo_ms`, até a janela ser destruída.

        O rodapé é quem pergunta, e não as sete operações que avisam: um `BusyToken` que se
        esquecesse de avisar o rodapé deixaria a barra girando para sempre, e a S-112 registra
        que `release()` esquecido é o erro que de fato acontece.
        """
        self.aplicar_ocupacao(operacoes())
        self._acompanhamento = self.after(intervalo_ms, lambda: self.acompanhar(operacoes, intervalo_ms=intervalo_ms))

    def _ao_cancelar(self) -> None:
        if self._cancelar is not None:
            self._cancelar()

    def _cancelar_agendamento(self, identificador: str) -> None:
        try:
            self.after_cancel(identificador)
        except (tk.TclError, ValueError) as exc:  # pragma: no cover - agendamento já disparado
            logger.debug("Agendamento do rodapé já havia disparado: %s", exc)

    def destroy(self) -> None:
        for identificador in (self._expiracao, self._acompanhamento):
            if identificador is not None:
                self._cancelar_agendamento(identificador)
        self._expiracao = self._acompanhamento = None
        super().destroy()
