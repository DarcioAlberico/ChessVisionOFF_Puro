"""Estado persistido da aplicação, tipado, versionado e gravado de forma atômica (S-25).

Três problemas concretos que este módulo substitui, todos medidos no `app_tkinter.py`:

1. **Gravação não atômica.** `_save_app_state` fazia read-modify-write com
   `path.write_text`, que trunca antes de escrever. Fechar o app (ou a máquina) nesse
   intervalo deixava `data/app_tkinter_state.json` com 0 byte -- e o app seguinte perdia o
   último PDF sem nenhuma pista do porquê. Ver `atomic_io`.

2. **Silêncio no descarte.** `_load_app_state` devolvia `False` para qualquer problema, do
   arquivo corrompido ao PDF que mudou de lugar. Os dois casos merecem tratamento
   diferente e nenhum merece silêncio: agora o inválido gera `warning` com o motivo.

3. **Duas leituras do mesmo arquivo.** `load_pdf` reabria o JSON por conta própria só para
   consultar `pdf_history`, com o seu próprio `try/except`. Uma cópia da lógica de leitura
   é uma cópia dos bugs dela.

O esquema é versionado desde já porque a Fase 4 acrescenta campos (fila de revisão,
heatmap) e a Fase 6 vai acrescentar mais. Estado de versão futura é **descartado**, não
adivinhado: um app antigo lendo campo novo pela metade é pior que um app antigo começando
limpo.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..arquivo_do_dono import ler_texto
from ..atomic_io import atomic_write_json
from . import viewport
from .livros import caminho_canonico, chave_do_livro

__all__ = [
    "AppState",
    "load_state",
    "save_state",
]

logger = logging.getLogger(__name__)

STATE_VERSION = 7
"""Versão 1 é o formato sem o campo `version`, que existe em disco hoje.

A **3** é a S-221, e ela só acrescenta `skin`. A **4** é a S-230, e acrescenta `piece_set` e
`piece_dir`. A **5** é a S-232, e acrescenta `densidade`. A **6** é a S-271, e acrescenta
`estudo_aberto` e `estudo_divisor`. A **7** é a S-519, e acrescenta `estudo_divisor_vertical`. Um
arquivo de qualquer versão anterior abre sem perder nada: o campo que falta cai
no padrão, que é "nada escolhido" -- e nada escolhido é a pele clássica, com o conjunto de peças de
sempre, a densidade que a pele sugerir e nenhum estudo aberto."""

MAX_PDF_HISTORY = 50
"""Tamanho do histórico de páginas por PDF. Sem teto ele cresce para sempre."""

MAX_RECENTES = 10
"""Quantos livros o menu "Abrir recente" mostra (S-161).

O histórico guarda 50 porque a pergunta dele é "em que página eu parei neste livro?", e essa vale
para o acervo inteiro. A do menu é outra -- "qual dos últimos eu quero de volta?" --, e 50 linhas
num submenu não são uma lista de recentes: são o acervo em ordem de acesso, que é o que a aba
Galeria já é."""


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class AppState:
    """O que a aplicação lembra entre execuções."""

    last_pdf: str = ""
    last_page: int = 0
    pdf_zoom: float = 0.7
    board_zoom: float = 1.0
    """Que fração da coluna o tabuleiro da sala ocupa (S-518).

    **Era 0,85 e não tinha leitor.** O número vinha do deslizador do Tk, onde o canvas do estudo era
    de tamanho fixo e a fração era do canvas; aqui o tabuleiro **é** a coluna, e o padrão certo é
    ocupá-la -- `BoardGeometry.fit` já desconta a margem das coordenadas antes de enquadrar. Quem
    quiser menor troca aqui, e o valor sobrevive à sessão."""

    pdf_enquadramento: str = viewport.ENQUADRAMENTO_LARGURA
    """Como o visor enquadra a folha: `LARGURA`, `PAGINA` ou `LIVRE` (F9-C3).

    **O zoom sozinho não bastava, e o número diz por quê.** Até aqui a sessão guardava
    apenas `pdf_zoom`, e um zoom é a resposta a uma pergunta feita numa janela de um
    tamanho: reaberto noutro tamanho, ele desenha a mesma página em 31 % da largura útil
    tanto a 1280 quanto a 1920. Medido nas 36 capturas do ciclo 2: **366 px de página nas
    três resoluções, idênticos ao pixel** -- a 1920 são 29 % de um viewport de 819×850, e
    os outros 71 % são branco.

    O que se guarda agora é a **pergunta**, e ela se responde de novo a cada mudança de
    área. `LIVRE` é a resposta de quem escolheu o zoom à mão, e ela continua sendo
    respeitada -- ver `ui/viewport.ENQUADRAMENTOS`.

    O padrão é `LARGURA` e não `LIVRE`: um estado gravado antes deste campo não tem
    enquadramento nenhum a restaurar, e "caiba na largura" é a resposta que uma janela de
    leitura dá quando ninguém disse outra coisa."""

    pdf_history: dict[str, int] = field(default_factory=dict)
    """Última página vista por PDF, indexado pelo caminho absoluto."""

    show_heatmap: bool = True
    """Heatmap de incerteza ligado no tabuleiro de resultado (S-21)."""

    show_diagram_boxes: bool = True
    """Diagramas marcados sobre a página no visualizador (S-68).

    Ligado por padrão: é como se descobre que a marcação existe. Quem a desliga costuma estar
    lendo o texto do livro, e essa escolha tem de sobreviver ao fechamento da janela -- senão
    ela vira uma tarefa a refazer toda vez."""

    wheel_flips_page: bool = True
    """A roda vira a página ao chegar na borda (S-70).

    Ligado por padrão porque é o que devolve a leitura corrida que a aba "Leitura" dava. Quem
    trabalha um diagrama de cada vez costuma desligar, e a escolha tem de durar."""

    review_queue_path: str = ""
    """Fila de revisão aberta por último (S-22). Vazio = nenhuma."""

    window_geometry: str = ""
    """Tamanho e posição da janela, no formato do Tk (`1700x980+120+40`). Vazio = nunca guardada.

    O estado lembrava o PDF, a página, os dois zooms e três interruptores -- e não lembrava o
    arranjo da janela, que é o que o usuário reconstrói primeiro ao voltar (S-156). Validada
    contra os monitores atuais na hora de aplicar: ver `ui/geometria.geometria_corrigida`."""

    sash_fraction: float = 0.0
    """Onde o divisor está, como fração da largura da janela. `0.0` = nunca guardada.

    Zero e não 0,42: "não guardado" e "guardado em 0,42" são estados diferentes, e o segundo
    tem de sobreviver a alguém mudar o padrão. `_set_initial_sashes` reposicionava o divisor em
    42% a **cada** abertura -- quem trabalha com o PDF grande o arrastava e o perdia toda
    sessão."""

    active_tab: str = ""
    """Rótulo da aba aberta por último. Vazio = nenhuma, e a janela abre na primeira.

    **O rótulo e não o índice**, porque índice não sobrevive a reordenar as abas -- e a S-162
    é, literalmente, reordená-las. Um rótulo que não existe mais cai na primeira aba, que é o
    mesmo comportamento de não ter nada guardado."""

    skin: str = ""
    """Nome da pele escolhida em `Ver ▸ Aparência` (S-221). Vazio = nunca escolhida.

    **Vazio e não `"classica"`**, embora a spec tenha escrito o segundo. O nome da pele padrão é
    de `ui/pele.py`, e cravá-lo aqui o declararia num segundo lugar -- exatamente a fenda que a
    S-324 acabou de fechar para os comandos. Vazio já significa "cai no padrão", e é o que
    `active_tab`, `window_geometry` e `review_queue_path` neste mesmo arquivo já querem dizer.

    **E não é validado aqui**, pelo mesmo motivo da geometria: pele registrada é pergunta de quem
    vai aplicá-la. `pele.escolhida` responde, e nomeia no log a que não existe."""

    piece_set: str = ""
    """Nome do conjunto de peças escolhido na Configuração (S-230). Vazio = nunca escolhido.

    **Vazio e não `"padrao"`**, pela mesma razão de `skin`: o nome do conjunto padrão é de
    `ui/conjuntos.py`, e cravá-lo aqui o declararia num segundo lugar. E, como a pele, **não é
    validado aqui**: conjunto registrado é pergunta de quem vai desenhá-lo, e `conjuntos.escolhido`
    responde nomeando no log o que não existe."""

    densidade: str = ""
    """A densidade escolhida em `Ver ▸ Aparência ▸ Densidade` (S-232). Vazio = nunca escolhida.

    **Vazio e não `"confortavel"`**, e aqui o vazio significa mais do que "cai no padrão": ele é a
    diferença entre *não decidi* e *decidi o que a pele sugeria*. A fita sugere compacta; quem
    nunca abriu o menu tem o vazio e recebe a sugestão de cada pele ao trocar. Quem escolheu
    confortável guarda `"confortavel"` e continua confortável **também na fita** -- que é o
    critério de aceite "a escolha explícita sobrepõe a sugestão da pele, e sobrevive à troca".
    Cravar o padrão aqui apagaria essa diferença no primeiro salvamento.

    **E não é validada aqui**, pela mesma razão de `skin` e `piece_set`: densidade registrada é
    pergunta de quem vai aplicá-la, e `pele.densidade_em_vigor` responde nomeando no log a que não
    existe."""

    texto_motor: str = ""
    """O motor de leitura escolhido na aba Texto (`ui/texto_declarado.MOTORES`), ou `""` para o
    padrão da aba (item 17 de 2026-10-09). Não é validado aqui, pela razão de `skin`: quem o
    aplica é `PainelDeTexto.definir_motor`, que ignora um nome que não conhece."""
    texto_lingua: str = ""
    """A língua do livro que o Tesseract lê (S-717). Vazio é a padrão; a S-723 a leva ao caderno."""

    texto_zoom: int = 0
    """Degraus de zoom da aba de texto (S-291). `0` = tamanho normal.

    **É o terceiro zoom do programa**, e os outros dois já eram lembrados desde a versão 1 do
    formato -- pela razão que este arquivo repete em `show_diagram_boxes` e em `sash_fraction`:
    escolha de visualização que se perde a cada abertura vira tarefa a refazer toda vez.

    `0` é o padrão **e** um valor válido, e aqui isso não custa nada: ao contrário de `skin` e
    `sash_fraction`, "não guardado" e "guardado em zero" pedem exatamente o mesmo do programa."""

    texto_quebra: bool = True
    """As linhas da aba de texto quebram na largura da janela? (S-291)

    Ligado por padrão porque é como a aba nasceu e é o certo para prosa. Quem desliga está lendo
    **notação** -- uma linha de lances quebrada deixa de ser uma linha de lances --, e essa escolha
    dura tanto quanto a de `wheel_flips_page`, que é o interruptor vizinho com o mesmo argumento."""

    texto_diagramas: str = ""
    """«Diagramas no texto» (S-620): `""` centralizados, `"esquerda"` à esquerda."""
    texto_miniatura: str = ""
    """O tamanho da miniatura do diagrama no texto (S-623): `pequeno`, `medio` ou `grande`; `""` é o padrão."""
    texto_familia: str = ""
    """A letra de leitura da folha (S-632): `""` a proporcional do tema, `serifada` ou `monoespacada`."""
    texto_ao_lado: bool = False
    """O texto corre ao lado do diagrama que se desenha à esquerda (S-624)."""
    texto_ultima_cor: str = ""
    texto_ultimo_realce: str = ""
    """A última cor de letra e de realce dos botões partidos da fita (S-650). `""` é a primeira do autor."""
    texto_ler_ao_chegar: bool = False
    """Com a mesa acompanhando a página, a folha sem caderno é lida ao chegar (S-644). Desligada por padrão."""
    texto_fita_recolhida: bool = False
    """A fita do Texto recolhida com `Ctrl+F1` (S-652)."""
    texto_transcricao_pasta: str = ""
    """A pasta da transcrição do scan-ouro (S-703), fora do repositório. O backup é declarado dentro dela."""
    texto_glifos_recentes: list[str] = field(default_factory=list)
    """Os glifos usados por último na paleta (S-650), do mais novo ao mais velho."""
    texto_mesa: str = ""
    """A mesa de texto se arma ao abrir o Texto? (S-640) `ui/mesa`: `""` e `texto` ligam, `nunca`
    desliga. Não é validada aqui além do tipo, pela razão de `skin`: quem a aplica é `mesa.ligada`."""

    mesa_fraction: float = 0.0
    """A parte da largura que o PDF ocupa **na mesa de texto** (S-640). `0` = nunca guardada.

    Separada de `sash_fraction` porque a mesa troca os lados do divisor: gravar a fração dela por cima
    da outra faria a janela abrir, na sessão seguinte, com a coluna do trabalho do tamanho que o PDF
    tinha na mesa. As duas disposições lembram cada uma a sua alça."""

    estudo_aberto: str = ""
    """A chave do diagrama cujo estudo estava aberto na sala (S-271). Vazio = nenhum.

    É `estudo.Ancora.chave()`, e não o caminho do PDF nem o número da página: a sala é do livro e o
    estudo é do **diagrama**, e voltar ao livro sem voltar ao diagrama devolveria a pessoa à porta da
    sala em vez de à mesa em que ela estava.

    **Não é validada aqui**, pela mesma razão de `skin` e `window_geometry`: se aquele diagrama ainda
    existe é pergunta de quem for abrir o livro, e uma chave que não casa com nada tem a mesma
    resposta de não ter nada guardado."""

    estudo_divisor_vertical: float = 0.0
    """Onde está o divisor entre a lista de lances e o comentário, como fração (S-519). `0.0` = nunca
    guardado.

    **Um campo novo e não uma reforma do de baixo**, porque são dois divisores com assuntos
    diferentes: o horizontal reparte tabuleiro e coluna de leitura, o vertical reparte a coluna de
    leitura entre lances, comentário e motor. Guardá-los juntos faria mexer num mover o outro no
    arquivo, e o zero de "nunca guardado" deixaria de distinguir qual dos dois nunca foi mexido."""

    estudo_divisor: float = 0.0
    """Onde está o divisor entre o tabuleiro e a lista de lances, como fração (S-276). `0.0` = nunca
    guardado, e aí o peso do `PanedWindow` decide.

    Zero e não 0,6, pela mesma razão de `sash_fraction`: "não guardado" e "guardado em 0,6" são
    estados diferentes, e o segundo tem de sobreviver a alguém mudar o padrão."""

    piece_dir: str = ""
    """A pasta de peças do usuário (S-230). Vazio = nenhuma escolhida.

    Guardada **junto** e não em lugar do nome: quem experimenta a pasta própria, volta ao padrão e
    depois quer a sua de novo não deve ter de reencontrá-la no disco. É a mesma decisão de
    `sash_fraction`, onde "não guardado" e "guardado" são estados diferentes."""

    def recentes(
        self, limite: int = MAX_RECENTES, *, existe: Callable[[Path], bool] | None = None
    ) -> list[str]:
        """Os livros abertos que **ainda existem**, do mais recente para o mais antigo (S-161).

        Sai de graça do `pdf_history`: `remember_page` reinsere a chave a cada visita, então a
        ordem do dicionário **é** a de uso. Um segundo arquivo de "recentes" seria uma segunda
        verdade sobre a mesma coisa, e o projeto já registrou o que isso custa (S-75).

        **O filtro de existência não é zelo, é o que a janela dirigida encontrou.** O histórico
        desta máquina tem 29 entradas e **13 delas apontam para a pasta `C:/PythonChess/`**, a pasta de
        antes de o projeto ser movido (o mesmo evento que a S-37 documenta). Um submenu com 13 itens
        que falham ao serem clicados é a mesma família de defeito que `ui/menu.montar` recusa ao
        exigir comando para todo item declarado -- só que descoberto pelo usuário, um clique por vez.

        `existe` é injetável para o teste poder afirmar isso sem tocar em disco, como
        `campos.diagnosticar_caminho` já fazia.
        """
        confere = existe if existe is not None else Path.exists
        vivos = [caminho for caminho in reversed(list(self.pdf_history)) if confere(Path(caminho))]
        return vivos[:limite]

    def page_for(self, pdf_path: Path) -> int:
        """Página em que este PDF foi deixado. 0 se ele nunca foi aberto."""
        guardada = self._entrada_do_livro(pdf_path)
        return 0 if guardada is None else int(self.pdf_history[guardada])

    def remember_page(self, pdf_path: Path, page_index: int) -> None:
        history = self.pdf_history
        guardada = self._entrada_do_livro(pdf_path)
        if guardada is not None:
            history.pop(guardada)
        history[_history_key(pdf_path)] = int(page_index)
        while len(history) > MAX_PDF_HISTORY:
            # dict preserva ordem de insercao: o primeiro e o menos recentemente tocado.
            history.pop(next(iter(history)))

    def _entrada_do_livro(self, pdf_path: Path) -> str | None:
        """A entrada do histórico que é este livro, por qualquer grafia (S-827).

        A grafia gravada é o caso de toda virada de página, e sai sem varrer; as outras (`..`, caixa,
        a gravada quando o caminho não resolvia) passam por `chave_do_livro`, uma vez por livro.
        """
        exata = _history_key(pdf_path)
        if exata in self.pdf_history:
            return exata
        chave = chave_do_livro(pdf_path)
        return next((gravada for gravada in self.pdf_history if chave_do_livro(gravada) == chave), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "last_pdf": self.last_pdf,
            "last_page": int(self.last_page),
            "pdf_zoom": float(self.pdf_zoom),
            "pdf_enquadramento": str(self.pdf_enquadramento),
            "board_zoom": float(self.board_zoom),
            "pdf_history": {str(key): int(value) for key, value in self.pdf_history.items()},
            "show_heatmap": bool(self.show_heatmap),
            "show_diagram_boxes": bool(self.show_diagram_boxes),
            "wheel_flips_page": bool(self.wheel_flips_page),
            "review_queue_path": self.review_queue_path,
            "window_geometry": self.window_geometry,
            "sash_fraction": float(self.sash_fraction),
            "active_tab": self.active_tab,
            "skin": self.skin,
            "densidade": self.densidade,
            "piece_set": self.piece_set,
            "piece_dir": self.piece_dir,
            "texto_zoom": int(self.texto_zoom),
            "texto_quebra": bool(self.texto_quebra),
            "texto_motor": str(self.texto_motor),
            "texto_lingua": str(self.texto_lingua),
            "texto_diagramas": str(self.texto_diagramas),
            "texto_miniatura": str(self.texto_miniatura),
            "texto_familia": str(self.texto_familia),
            "texto_ao_lado": bool(self.texto_ao_lado),
            "texto_ler_ao_chegar": bool(self.texto_ler_ao_chegar),
            "texto_transcricao_pasta": str(self.texto_transcricao_pasta),
            "texto_ultima_cor": str(self.texto_ultima_cor),
            "texto_ultimo_realce": str(self.texto_ultimo_realce),
            "texto_fita_recolhida": bool(self.texto_fita_recolhida),
            "texto_glifos_recentes": [str(g) for g in self.texto_glifos_recentes][:20],
            "texto_mesa": str(self.texto_mesa),
            "mesa_fraction": float(self.mesa_fraction),
            "estudo_aberto": self.estudo_aberto,
            "estudo_divisor": float(self.estudo_divisor),
            "estudo_divisor_vertical": float(self.estudo_divisor_vertical),
        }


def _history_key(pdf_path: Path) -> str:
    """Como o livro é gravado no histórico: um caminho que se abre, e que `recentes` mostra."""
    return caminho_canonico(pdf_path)


def _migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Traz um estado de versão anterior para o esquema corrente.

    A versão 1 (sem o campo `version`) já tinha `last_pdf`, `last_page`, `pdf_zoom` e
    `pdf_history` com os mesmos significados -- migrar é só reconhecê-la, e é por isso que
    a numeração começa nela em vez de fingir que o formato antigo não existiu.

    **A chave do modo bloco sai aqui (S-726)**, e sem versão nova: o programa anterior lê o arquivo
    sem ela, e com a versão subida ele o recusaria. Quem a tinha ligada lê como todo mundo.
    """
    version = raw.get("version", 1)
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"campo `version` inválido: {version!r}")
    if version > STATE_VERSION:
        raise ValueError(f"estado gravado por versão mais nova ({version} > {STATE_VERSION})")
    return {chave: valor for chave, valor in raw.items() if chave != "texto_bloco"}


def _texto(valor: object) -> str | None:
    return valor if isinstance(valor, str) else None


def _sim_ou_nao(valor: object) -> bool | None:
    return valor if isinstance(valor, bool) else None


def _numero(valor: object) -> float | None:
    """O número do JSON, sem o `bool` (que em Python é `int`): `true` não é zoom 1."""
    return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else None


def _inteiro(minimo: int | None = None) -> Callable[[object], int | None]:
    def ler(valor: object) -> int | None:
        if not isinstance(valor, int) or isinstance(valor, bool):
            return None
        return valor if minimo is None else max(minimo, valor)

    return ler


def _fracao(baixo: float, alto: float) -> Callable[[object], float | None]:
    def ler(valor: object) -> float | None:
        numero = _numero(valor)
        return None if numero is None else _clamp(numero, baixo, alto)

    return ler


def _enquadramento(valor: object) -> str | None:
    # Valor fora da lista cai no padrão, como todo campo deste arquivo: um estado de disco
    # corrompido não pode abrir a janela num modo que não existe.
    return str(valor) if valor in viewport.ENQUADRAMENTOS else None


def _historico(valor: object) -> dict[str, int] | None:
    """As entradas de página válidas, **aparadas ao teto** (S-828): o teto valia só para
    `remember_page`, e um arquivo com 500 entradas seguia com 500. A ordem do arquivo é a de uso
    (`recentes`), e ficam as últimas."""
    if not isinstance(valor, dict):
        return None
    validas = [
        (str(chave), int(pagina))
        for chave, pagina in valor.items()
        if isinstance(pagina, int) and not isinstance(pagina, bool) and pagina >= 0
    ]
    return dict(validas[-MAX_PDF_HISTORY:])


def _glifos(valor: object) -> list[str] | None:
    return [g for g in valor if isinstance(g, str) and g][:20] if isinstance(valor, list) else None


_CAMPOS: tuple[tuple[str, Callable[[object], object]], ...] = (
    ("last_pdf", _texto),
    ("last_page", _inteiro(minimo=0)),
    ("pdf_zoom", _fracao(0.25, 2.0)),
    ("pdf_enquadramento", _enquadramento),
    ("board_zoom", _fracao(0.45, 1.8)),
    ("pdf_history", _historico),
    ("show_heatmap", _sim_ou_nao),
    ("show_diagram_boxes", _sim_ou_nao),
    ("wheel_flips_page", _sim_ou_nao),
    ("review_queue_path", _texto),
    # Os três da S-156. Nenhum é validado aqui além do tipo: a geometria depende dos monitores
    # que existem **agora**, e essa pergunta é de quem vai aplicá-la, não de quem a lê do disco.
    ("window_geometry", _texto),
    ("sash_fraction", _fracao(0.0, 1.0)),
    ("active_tab", _texto),
    # Pele, densidade e conjunto de peças (S-221, S-230, S-232), e nenhum é validado aqui além do
    # tipo -- pelo mesmo motivo da geometria: o que está registrado é pergunta de quem vai usá-lo.
    ("skin", _texto),
    ("densidade", _texto),
    ("piece_set", _texto),
    ("piece_dir", _texto),
    # O zoom da aba Texto (S-291) **não é grampeado aqui**: os limites são da aba que o desenha, e
    # repeti-los os declararia num segundo lugar. Quem grampeia um `texto_zoom: 900` é `_aplicar_zoom`.
    ("texto_zoom", _inteiro()),
    ("texto_quebra", _sim_ou_nao),
    ("texto_motor", _texto),
    ("texto_lingua", _texto),
    ("texto_diagramas", _texto),
    ("texto_miniatura", _texto),
    ("texto_familia", _texto),
    ("texto_ao_lado", _sim_ou_nao),
    ("texto_ultima_cor", _texto),
    ("texto_ultimo_realce", _texto),
    ("texto_ler_ao_chegar", _sim_ou_nao),
    ("texto_transcricao_pasta", _texto),
    ("texto_fita_recolhida", _sim_ou_nao),
    ("texto_glifos_recentes", _glifos),
    ("texto_mesa", _texto),
    ("mesa_fraction", _fracao(0.0, 1.0)),
    ("estudo_aberto", _texto),
    ("estudo_divisor", _fracao(0.0, 1.0)),
    ("estudo_divisor_vertical", _fracao(0.0, 1.0)),
)
"""Como cada campo do `AppState` é lido do disco: o leitor devolve o valor, ou `None` quando o do
arquivo não serve (S-828). O padrão **não** está aqui: é o do próprio `AppState`, num lugar só."""


def state_from_dict(raw: dict[str, Any]) -> AppState:
    """Constrói o estado a partir do dicionário lido, ignorando campo de tipo errado.

    Campo com tipo inesperado cai para o padrão em vez de derrubar a leitura inteira: uma
    entrada estragada no histórico não deve custar ao usuário o último PDF aberto.
    """
    raw = _migrate(raw)
    state = AppState()
    for campo, ler in _CAMPOS:
        valor = ler(raw.get(campo))
        if valor is not None:
            setattr(state, campo, valor)
    return state


def load_state(path: Path) -> AppState:
    """Lê o estado. Arquivo ausente ou inválido devolve o padrão -- e diz por quê no log."""
    path = Path(path)
    if not path.exists():
        return AppState()

    try:
        raw = json.loads(ler_texto(path, do_usuario=False))
    except (OSError, ValueError) as exc:
        logger.warning("Estado da aplicação descartado (%s): %s", path, exc)
        return AppState()

    if not isinstance(raw, dict):
        logger.warning("Estado da aplicação descartado (%s): esperado objeto JSON, veio %s", path, type(raw).__name__)
        return AppState()

    try:
        return state_from_dict(raw)
    except ValueError as exc:
        logger.warning("Estado da aplicação descartado (%s): %s", path, exc)
        return AppState()


def save_state(path: Path, state: AppState) -> None:
    """Grava o estado de forma atômica. Falha de escrita é registrada, não propagada.

    Não derrubar a aplicação por causa do estado é a decisão que já existia; o que muda é
    que a falha agora aparece no log com o caminho, em vez de sumir.
    """
    try:
        atomic_write_json(Path(path), state.to_dict())
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Não foi possível salvar o estado da aplicação em %s: %s", path, exc)
