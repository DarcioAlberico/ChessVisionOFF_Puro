"""O estado do editor de diagramas, fora do widget (S-49).

**Por que isto saiu do `ResultPanel`.** As quatro origens -- OCR de página, imagem local,
item da fila de revisão e amostra do dataset -- abrem o **mesmo** editor, e o que distingue
uma da outra é um de três vínculos mutuamente exclusivos. Distingui-los é o que faz `Ctrl+S`
gravar uma amostra nova num caso e **regravar a linha existente** no outro; errar isso cria
uma segunda amostra da mesma imagem e deixa o rótulo errado no arquivo (S-23).

É a regra de negócio mais delicada da interface, e ela morava dentro de um `ttk.Frame`.
Testá-la exigia dirigir a janela -- que é o que o roteiro headless faz, e foi ele que pegou
o defeito de navegação que 509 testes verdes não pegaram. Um teste que precisa de janela é
um teste que quase não se escreve, e o resultado prático é que quase não se escreveu.

Aqui não há `import tkinter`. `save_target()` responde "o que acontece se eu salvar agora?"
em duas linhas de teste, e `load()` é o **ponto único** de troca de vínculo -- antes eram
quatro caminhos que zeravam dois campos e escreviam o terceiro, cada um por conta própria.

**Por que as listas continuam paralelas.** `fen_edits[i]` é o que o usuário está editando
*agora*; `items[i].placement` é o que o modelo leu. Fundi-los perderia a leitura original,
que é o que o heatmap e a comparação com o rótulo precisam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from chess_diagram_ocr.labels import DATASET_RECORRIGIDO, label_route
from chess_diagram_ocr.second_opinion import SecondOpinion, compare
from chess_diagram_ocr.service import RecognitionOrigin, RecognizedDiagram

__all__ = [
    "DiagramEditorModel",
    "EditorBinding",
    "SaveKind",
    "SaveTarget",
]


class EditorBinding(str, Enum):
    """A que o conteúdo do editor está preso. Os quatro estados são exclusivos."""

    NONE = "none"
    """Imagem local ou recorte de área: não há nada para onde voltar."""

    PAGE = "page"
    """Resultado de uma página inteira de PDF. Vai para o cache por página."""

    REVIEW = "review"
    """Item da fila de revisão. Salvar também fecha o item na fila (S-22)."""

    SAMPLE = "sample"
    """Linha da aba Dataset. Salvar **regrava** o rótulo em vez de criar amostra (S-23)."""


class SaveKind(str, Enum):
    NOTHING = "nothing"
    """Não há o que salvar, ou a FEN não é válida."""

    NEW_SAMPLE = "new_sample"
    """Grava uma amostra nova no `labels.csv` e a imagem em `data/samples/`."""

    REWRITE_ROW = "rewrite_row"
    """Regrava a linha que já existe. Nunca cria imagem nem linha nova."""


@dataclass(frozen=True)
class SaveTarget:
    """O que acontece ao salvar o diagrama selecionado. Uma resposta, não uma ação.

    O modelo decide **o quê**; quem executa continua sendo o painel, porque gravar arquivo
    e mostrar caixa de erro são assuntos dele. A separação é o que torna a regra testável:
    conferir que abrir um item da fila e salvar não cria amostra nova passa a ser comparar
    um `SaveKind`.
    """

    kind: SaveKind
    index: int = -1
    fen: str = ""
    side: str = "w"

    filename: str | None = None
    """Só em `REWRITE_ROW`: a linha do `labels.csv` a regravar."""

    settle_position: int | None = None
    """Só quando o vínculo é `REVIEW`: a posição a fechar na fila depois de salvar."""

    route: str = ""
    """Valor de `corrected_by` (S-52): **como** a amostra chegou ao rótulo."""


@dataclass
class DiagramEditorModel:
    """As três listas paralelas, o índice selecionado e o vínculo -- sem Tk."""

    items: list[RecognizedDiagram] = field(default_factory=list)
    fen_edits: list[str] = field(default_factory=list)
    side_edits: list[str] = field(default_factory=list)
    selected: int = 0

    binding: EditorBinding = EditorBinding.NONE
    page_key: tuple[str, int] | None = None
    """De que página de PDF vem o que está no editor. `None` = não veio de uma página
    inteira: imagem local, recorte de área, item da fila ou amostra do dataset."""

    review_position: int | None = None
    editing_sample: str | None = None
    origin: RecognitionOrigin | None = None

    net_corrected: set[int] = field(default_factory=set)
    """Índices cuja FEN veio do serviço externo da S-32. Alimenta `label_route`."""

    second_opinion: dict[int, tuple[int, ...]] = field(default_factory=dict)
    """Por índice, as casas em que o segundo leitor discordou do primeiro (S-66).

    Guardado por diagrama, e não no widget, pela mesma razão de `fen_edits`: o usuário anda
    pelos diagramas da página e volta, e uma marca que morresse na troca obrigaria a rodar a
    segunda leitura de novo -- 0,3 s de máquina, mas a lista do que ainda falta conferir
    perdida."""

    # ------------------------------------------------------------------- troca de vínculo

    def load(
        self,
        items: list[RecognizedDiagram],
        fens: list[str] | None = None,
        sides: list[str] | None = None,
        *,
        binding: EditorBinding,
        page_key: tuple[str, int] | None = None,
        review_position: int | None = None,
        editing_sample: str | None = None,
        origin: RecognitionOrigin | None = None,
    ) -> None:
        """Ponto único de troca de vínculo. Antes havia quatro caminhos que faziam isso.

        Cada um zerava dois campos e escrevia o terceiro por conta própria, e o defeito
        possível era sempre o mesmo: esquecer de zerar um. Um editor com `editing_sample` e
        `review_position` ao mesmo tempo grava a linha do dataset **e** fecha um item da fila
        que não foi corrigido.
        """
        expected = {
            EditorBinding.PAGE: page_key,
            EditorBinding.REVIEW: review_position,
            EditorBinding.SAMPLE: editing_sample,
        }
        ancora = expected.get(binding)
        if binding is not EditorBinding.NONE and ancora is None:
            raise ValueError(f"O vínculo {binding.value!r} exige a âncora correspondente, e ela não veio.")
        for outro, valor in expected.items():
            if outro is not binding and valor is not None:
                raise ValueError(
                    f"Vínculo {binding.value!r} com âncora de {outro.value!r}: os três são mutuamente exclusivos."
                )

        self.items = items
        self.fen_edits = list(fens) if fens is not None else [d.placement for d in items]
        self.side_edits = list(sides) if sides is not None else [d.side_to_move for d in items]
        self.binding = binding
        self.page_key = page_key
        self.review_position = review_position
        self.editing_sample = editing_sample
        self.origin = origin
        # Os indices sao por carregamento: o diagrama 2 desta pagina nao e o diagrama 2 da
        # anterior, e herdar a marca de "veio da Net" gravaria a procedencia errada.
        self.net_corrected.clear()
        self.second_opinion.clear()
        self.selected = 0

    def adopt(
        self,
        items: list[RecognizedDiagram],
        fens: list[str],
        sides: list[str],
        *,
        page_key: tuple[str, int],
        origin: RecognitionOrigin | None = None,
        selected: int = 0,
    ) -> None:
        """Restaura um resultado de página vindo do cache, **por referência**.

        Correção feita durante a edição anterior já está nas listas guardadas; copiá-las
        aqui desfaria a edição. É o único caminho que não passa por `load`, e é por isso
        que ele tem nome próprio em vez de um parâmetro a mais.

        **A procedência entra junto com as listas (S-451).** Ela não entrava, e o campo ficava
        com o da *última página lida* -- ou `None`, depois de uma passagem pela fila de revisão
        ou pela aba Dataset, que carregam sem origem. `page_key` dizia a página certa e `origin`
        dizia outra, e quem grava amostra lê `origin`: voltar a uma página guardada e salvar
        escrevia no `labels.csv` o `source_page` da página errada, ou nenhum. O diagrama nunca
        ficava verde, porque o verde é esse mesmo `source_page` lido de volta -- e reabrir o
        livro não consertava, porque o defeito estava na linha gravada e não na tela.
        """
        self.items = items
        self.fen_edits = fens
        self.side_edits = sides
        self.binding = EditorBinding.PAGE
        self.page_key = page_key
        self.origin = origin
        self.review_position = None
        self.editing_sample = None
        self.net_corrected.clear()
        self.second_opinion.clear()
        self.selected = max(0, min(selected, len(items) - 1)) if items else 0

    def clear(self) -> None:
        self.items = []
        self.fen_edits = []
        self.side_edits = []
        self.selected = 0
        self.binding = EditorBinding.NONE
        self.page_key = None
        self.review_position = None
        self.editing_sample = None
        self.origin = None
        self.net_corrected.clear()
        self.second_opinion.clear()

    def unbind_page(self) -> None:
        """Solta o vínculo com a página sem apagar o conteúdo do editor.

        Trocar de PDF invalida o cache, cuja chave é (documento, página); o que está na tela
        continua sendo editável, só não pertence mais a página nenhuma.
        """
        self.page_key = None
        if self.binding is EditorBinding.PAGE:
            self.binding = EditorBinding.NONE

    # ------------------------------------------------------------------------- navegação

    @property
    def count(self) -> int:
        return len(self.items)

    def clamped_index(self) -> int:
        if not self.items:
            return 0
        return max(0, min(self.selected, len(self.items) - 1))

    def select(self, index: int) -> int:
        """Seleciona, limitando à faixa válida. Devolve o índice que de fato ficou."""
        self.selected = self.clamped_index() if not self.items else max(0, min(index, len(self.items) - 1))
        return self.selected

    def step(self, delta: int) -> int:
        """Anterior/próximo, sem dar a volta: nas pontas fica onde está."""
        return self.select(self.selected + delta)

    @property
    def current(self) -> RecognizedDiagram | None:
        return self.items[self.clamped_index()] if self.items else None

    def fen_at(self, index: int | None = None) -> str:
        idx = self.clamped_index() if index is None else index
        return self.fen_edits[idx] if 0 <= idx < len(self.fen_edits) else ""

    def side_at(self, index: int | None = None) -> str:
        idx = self.clamped_index() if index is None else index
        return self.side_edits[idx] if 0 <= idx < len(self.side_edits) else "w"

    # ----------------------------------------------------------------------------- edição

    def set_fen(self, fen: str, index: int | None = None) -> None:
        """O que o campo de texto tem agora. Não marca edição à mão: digitar não é corrigir
        o tabuleiro, e o campo é sincronizado a cada navegação."""
        idx = self.clamped_index() if index is None else index
        if 0 <= idx < len(self.fen_edits):
            self.fen_edits[idx] = fen.strip()

    def apply_placement(self, placement: str, index: int | None = None) -> bool:
        """Uma peça mudou no tabuleiro. Devolve se algo foi de fato registrado."""
        idx = self.clamped_index() if index is None else index
        if not (0 <= idx < len(self.fen_edits)):
            return False
        self.fen_edits[idx] = placement
        self.items[idx].edited_by_hand = True
        return True

    def set_side(self, side: str, index: int | None = None) -> bool:
        """Troca o lado a jogar. A legalidade depende dele: pode resolver o "xeque
        invertido" sem mexer em nenhuma peça (S-17)."""
        idx = self.clamped_index() if index is None else index
        if not (0 <= idx < len(self.side_edits)):
            return False
        self.side_edits[idx] = side
        self.items[idx].set_side_to_move(side)
        return True

    def mark_net_corrected(self, index: int, fen: str) -> bool:
        """Registra que esta FEN veio do serviço externo da S-32.

        Sem isto ela seria gravada como `ocr-corrigido`, e a pergunta que a coluna existe
        para responder -- amostra corrigida à mão treina melhor? -- passaria a contar leitura
        de terceiro como trabalho humano.
        """
        if not (0 <= index < len(self.fen_edits)):
            return False
        self.fen_edits[index] = fen
        self.net_corrected.add(index)
        return True

    def mark_second_opinion(self, index: int, placement: str, *, reader: str) -> SecondOpinion | None:
        """Adota a leitura do segundo leitor local e guarda onde ela contradiz a primeira.

        Devolve o parecer, ou `None` se o índice não existe mais -- o mesmo contrato de
        `mark_net_corrected`, e pelo mesmo motivo: a leitura roda em thread e a página pode
        ter mudado no meio.

        **Por que adota em vez de só marcar.** Marcar sem adotar deixaria o usuário
        corrigindo casa por casa à mão, que é exatamente o custo que a S-66 existe para
        cortar. Adotar sem marcar trocaria um leitor por outro em silêncio. As duas coisas
        juntas é o que dá o ganho medido: a posição já vem trocada e a marca roxa diz quais
        casas mudaram, para o olho ir direto nelas.

        O que **não** se perde: `items[index].placement` continua sendo a leitura do modelo
        local, então o heatmap, o `label_route` e a comparação com o rótulo seguem falando
        do modelo principal. Aqui só muda `fen_edits`.
        """
        if not (0 <= index < len(self.fen_edits)):
            return None
        parecer = compare(self.fen_edits[index], placement, reader=reader)
        self.fen_edits[index] = parecer.placement
        self.second_opinion[index] = parecer.disputed
        return parecer

    def disputed_squares(self, index: int) -> tuple[int, ...]:
        """As casas em disputa deste diagrama, ou vazio se a segunda leitura não rodou."""
        return self.second_opinion.get(index, ())

    @property
    def has_hand_edits(self) -> bool:
        """Alguma FEN difere do que o modelo leu, ou alguma peça foi arrastada."""
        return any(item.edited_by_hand for item in self.items) or any(
            fen != item.placement for item, fen in zip(self.items, self.fen_edits, strict=False)
        )

    # --------------------------------------------------------------------------- gravação

    def label_route(self, index: int, fen: str) -> str:
        """O que o editor sabe sobre a procedência, traduzido para `labels.label_route`."""
        return label_route(
            from_net=index in self.net_corrected,
            from_second_opinion=index in self.second_opinion,
            from_queue=self.binding is EditorBinding.REVIEW,
            read_placement=self.items[index].placement if 0 <= index < len(self.items) else "",
            saved_placement=fen,
        )

    def save_target(self, index: int | None = None) -> SaveTarget:
        """O que salvar agora significa, dado o vínculo.

        Três respostas, e a diferença entre elas é o defeito que a S-23 fechou:

        - vínculo `SAMPLE` → **regravar** a linha do `labels.csv`. Criar amostra nova aqui
          duplicaria a imagem e deixaria o rótulo errado no arquivo.
        - vínculo `REVIEW` → amostra nova **e** fechar o item na fila.
        - qualquer outro → amostra nova.
        """
        if not self.items:
            return SaveTarget(kind=SaveKind.NOTHING)

        idx = self.clamped_index() if index is None else index
        if not (0 <= idx < len(self.fen_edits)):
            return SaveTarget(kind=SaveKind.NOTHING)

        fen = self.fen_edits[idx]
        side = self.side_at(idx)

        if self.binding is EditorBinding.SAMPLE:
            return SaveTarget(
                kind=SaveKind.REWRITE_ROW,
                index=idx,
                fen=fen,
                side=side,
                filename=self.editing_sample,
                route=DATASET_RECORRIGIDO,
            )

        return SaveTarget(
            kind=SaveKind.NEW_SAMPLE,
            index=idx,
            fen=fen,
            side=side,
            settle_position=self.review_position if self.binding is EditorBinding.REVIEW else None,
            route=self.label_route(idx, fen),
        )

    def settled(self) -> None:
        """O item da fila foi fechado: o vínculo com ela acabou."""
        self.review_position = None
        if self.binding is EditorBinding.REVIEW:
            self.binding = EditorBinding.NONE
