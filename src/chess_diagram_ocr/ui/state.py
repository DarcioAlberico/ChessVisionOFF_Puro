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

from ..atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

STATE_VERSION = 4
"""Versão 1 é o formato sem o campo `version`, que existe em disco hoje.

A **3** é a S-221, e ela só acrescenta `skin`. A **4** é a S-230, e acrescenta `piece_set` e
`piece_dir`. Um arquivo de qualquer versão anterior abre sem perder nada: o campo que falta cai no
padrão, que é "nada escolhido" -- e nada escolhido é a pele clássica com o conjunto de peças de
sempre."""

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
    board_zoom: float = 0.85
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
    S-219 acabou de fechar para os comandos. Vazio já significa "cai no padrão", e é o que
    `active_tab`, `window_geometry` e `review_queue_path` neste mesmo arquivo já querem dizer.

    **E não é validado aqui**, pelo mesmo motivo da geometria: pele registrada é pergunta de quem
    vai aplicá-la. `pele.escolhida` responde, e nomeia no log a que não existe."""

    piece_set: str = ""
    """Nome do conjunto de peças escolhido na Configuração (S-230). Vazio = nunca escolhido.

    **Vazio e não `"padrao"`**, pela mesma razão de `skin`: o nome do conjunto padrão é de
    `ui/conjuntos.py`, e cravá-lo aqui o declararia num segundo lugar. E, como a pele, **não é
    validado aqui**: conjunto registrado é pergunta de quem vai desenhá-lo, e `conjuntos.escolhido`
    responde nomeando no log o que não existe."""

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
        return int(self.pdf_history.get(_history_key(pdf_path), 0))

    def remember_page(self, pdf_path: Path, page_index: int) -> None:
        key = _history_key(pdf_path)
        history = self.pdf_history
        history.pop(key, None)
        history[key] = int(page_index)
        while len(history) > MAX_PDF_HISTORY:
            # dict preserva ordem de insercao: o primeiro e o menos recentemente tocado.
            history.pop(next(iter(history)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "last_pdf": self.last_pdf,
            "last_page": int(self.last_page),
            "pdf_zoom": float(self.pdf_zoom),
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
            "piece_set": self.piece_set,
            "piece_dir": self.piece_dir,
        }


def _history_key(pdf_path: Path) -> str:
    try:
        return str(Path(pdf_path).resolve())
    except OSError:
        # Caminho de rede fora do ar: o não resolvido ainda serve de chave.
        return str(pdf_path)


def _migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Traz um estado de versão anterior para o esquema corrente.

    A versão 1 (sem o campo `version`) já tinha `last_pdf`, `last_page`, `pdf_zoom` e
    `pdf_history` com os mesmos significados -- migrar é só reconhecê-la, e é por isso que
    a numeração começa nela em vez de fingir que o formato antigo não existiu.
    """
    version = raw.get("version", 1)
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"campo `version` inválido: {version!r}")
    if version > STATE_VERSION:
        raise ValueError(f"estado gravado por versão mais nova ({version} > {STATE_VERSION})")
    return raw


def state_from_dict(raw: dict[str, Any]) -> AppState:
    """Constrói o estado a partir do dicionário lido, ignorando campo de tipo errado.

    Campo com tipo inesperado cai para o padrão em vez de derrubar a leitura inteira: uma
    entrada estragada no histórico não deve custar ao usuário o último PDF aberto.
    """
    raw = _migrate(raw)
    state = AppState()

    last_pdf = raw.get("last_pdf")
    if isinstance(last_pdf, str):
        state.last_pdf = last_pdf

    last_page = raw.get("last_page")
    if isinstance(last_page, int) and not isinstance(last_page, bool):
        state.last_page = max(0, last_page)

    pdf_zoom = raw.get("pdf_zoom")
    if isinstance(pdf_zoom, (int, float)) and not isinstance(pdf_zoom, bool):
        state.pdf_zoom = _clamp(float(pdf_zoom), 0.25, 2.0)

    board_zoom = raw.get("board_zoom")
    if isinstance(board_zoom, (int, float)) and not isinstance(board_zoom, bool):
        state.board_zoom = _clamp(float(board_zoom), 0.45, 1.8)

    history = raw.get("pdf_history")
    if isinstance(history, dict):
        state.pdf_history = {
            str(key): int(value)
            for key, value in history.items()
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        }

    show_heatmap = raw.get("show_heatmap")
    if isinstance(show_heatmap, bool):
        state.show_heatmap = show_heatmap

    show_boxes = raw.get("show_diagram_boxes")
    if isinstance(show_boxes, bool):
        state.show_diagram_boxes = show_boxes

    flips = raw.get("wheel_flips_page")
    if isinstance(flips, bool):
        state.wheel_flips_page = flips

    queue_path = raw.get("review_queue_path")
    if isinstance(queue_path, str):
        state.review_queue_path = queue_path

    # Os três da S-156. Nenhum é validado aqui além do tipo: a geometria depende dos monitores
    # que existem **agora**, e essa pergunta é de quem vai aplicá-la, não de quem a lê do disco.
    geometry = raw.get("window_geometry")
    if isinstance(geometry, str):
        state.window_geometry = geometry

    sash = raw.get("sash_fraction")
    if isinstance(sash, (int, float)) and not isinstance(sash, bool):
        state.sash_fraction = _clamp(float(sash), 0.0, 1.0)

    tab = raw.get("active_tab")
    if isinstance(tab, str):
        state.active_tab = tab

    skin = raw.get("skin")
    if isinstance(skin, str):
        state.skin = skin

    # Os dois da S-230, e nenhum é validado aqui além do tipo -- pelo mesmo motivo da pele e da
    # geometria: conjunto registrado e pasta que existe são perguntas de quem vai usá-los.
    piece_set = raw.get("piece_set")
    if isinstance(piece_set, str):
        state.piece_set = piece_set

    piece_dir = raw.get("piece_dir")
    if isinstance(piece_dir, str):
        state.piece_dir = piece_dir

    return state


def load_state(path: Path) -> AppState:
    """Lê o estado. Arquivo ausente ou inválido devolve o padrão -- e diz por quê no log."""
    path = Path(path)
    if not path.exists():
        return AppState()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
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
