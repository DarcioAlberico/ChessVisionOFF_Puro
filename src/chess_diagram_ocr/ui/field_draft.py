"""A anotação de uma página do conjunto de campo, montada na tela (S-77).

**Por que isto existe.** As Fases 7 e 11 estão com o código pronto e o critério de saída
aberto, e as duas travam no mesmo lugar: o conjunto de campo tem 15 páginas e 38 diagramas, e
a 7.7 mostrou que com 38 diagramas a taxa de exportação não distingue dois modelos -- a
vizinhança do gate está vazia, então nenhuma mudança pode ganhar um diagrama. **Quatro itens
(S-38b, S-40, S-62a, S-62b) foram julgados por essa métrica.** Crescer o conjunto é a única
coisa que os desbloqueia, e crescer o conjunto era editar JSONL à mão.

**O que muda.** O visualizador já desenha onde estão os diagramas (S-68) e a precisão do
detector é 0,9722 -- então, na maioria das páginas, anotar é **confirmar**. Este módulo é a
lista de trabalho dessa confirmação: começa no que o detector achou, aceita tirar o falso
positivo e acrescentar o que faltou, e vira uma `FieldPage` revisada.

**O que ele não faz, e não pode fazer.** Decidir quantos diagramas a página tem. Essa é a
única informação do projeto que não existe em lugar nenhum senão no olho de quem abre o livro
-- é por isso que `reviewed` começa `False` no rascunho da S-41 e por isso este módulo exige um
gesto humano para gravar. Um conjunto de campo gerado pelo próprio pipeline mede o modelo
contra ele mesmo e dá 1,000 em tudo.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from chess_diagram_ocr.field_eval import AnnotatedDiagram, Bbox, FieldPage, bbox_iou

logger = logging.getLogger(__name__)

__all__ = ["REGIMES", "FieldDraft"]

REGIMES: tuple[str, ...] = (
    "scan-puro",
    "scan-hachurado",
    "vetorial",
    "fonte",
    "sem-diagrama",
)
"""Os regimes que o conjunto de campo separa (S-41).

Não é taxonomia por gosto: a 7.4 mostra a taxa de exportação em 1,000 nos dois primeiros
regimes e em 0,429 no scan puro. Uma média sobre os quatro esconde exatamente a diferença que
decide onde vale trabalhar."""

SAME_DIAGRAM_IOU = 0.5
"""Acima disto, a caixa nova é a mesma que já está na lista -- o mesmo limiar com que o
`field_eval` casa detecção e anotação. Usar outro aqui faria a tela aceitar como diagrama novo
o que a avaliação contaria como repetido."""


@dataclass
class FieldDraft:
    """A lista de diagramas que a pessoa está confirmando para uma página."""

    pdf_name: str = ""
    page: int = 0
    regime: str = ""
    diagrams: list[AnnotatedDiagram] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.diagrams

    def reset_from(self, boxes: Iterable[tuple[Bbox, str]]) -> None:
        """Recomeça a partir do que está desenhado na tela: `(bbox, colocação)`.

        A colocação entra quando o diagrama já foi lido, e fica vazia quando ele só foi
        localizado. As duas formas são anotação válida: o conjunto de campo mede **detecção,
        legalidade e gate**, e a S-41 já aceita página anotada só com as caixas.
        """
        self.diagrams = [
            AnnotatedDiagram(bbox=tuple(bbox), placement=placement or "")  # type: ignore[arg-type]
            for bbox, placement in boxes
        ]

    def add(self, bbox: Bbox, *, note: str = "") -> bool:
        """Acrescenta um diagrama que o detector não achou. `False` se já estava lá.

        Acrescentar é o gesto que o rascunho da S-41 não sabe fazer -- "o rascunho não sabe o
        que o detector não achou" --, e é justamente o que mede **recall**. Sem ele, o conjunto
        de campo só conteria diagramas que o pipeline já encontra, e a métrica nasceria com
        1,000 de recall por construção.
        """
        nova = tuple(float(valor) for valor in bbox)
        if len(nova) != 4:
            return False
        if any(bbox_iou(nova, existente.bbox) >= SAME_DIAGRAM_IOU for existente in self.diagrams):  # type: ignore[arg-type]
            return False
        self.diagrams.append(AnnotatedDiagram(bbox=nova, note=note))  # type: ignore[arg-type]
        self.diagrams.sort(key=lambda item: (round(item.bbox[1], 1), round(item.bbox[0], 1)))
        return True

    def remove(self, index: int) -> bool:
        """Tira o falso positivo. `False` se o índice não existe."""
        if not 0 <= index < len(self.diagrams):
            return False
        self.diagrams.pop(index)
        return True

    def index_at(self, bbox: Bbox) -> int | None:
        """Qual item da lista corresponde a esta caixa da tela, se algum."""
        for indice, item in enumerate(self.diagrams):
            if bbox_iou(tuple(bbox), item.bbox) >= SAME_DIAGRAM_IOU:  # type: ignore[arg-type]
                return indice
        return None

    def to_page(self) -> FieldPage:
        """A página pronta para o arquivo, **marcada como revisada**.

        `reviewed=True` só aparece aqui, e é o ponto do módulo: quem confirma é gente. O
        rascunho da S-41 grava `False` porque ele é a saída do modelo, e medir o modelo contra
        a própria saída dá 1,000 em tudo e não significa nada.
        """
        regime = self.regime or ("sem-diagrama" if self.is_empty else "")
        return FieldPage(
            pdf=self.pdf_name,
            page=int(self.page),
            diagrams=tuple(self.diagrams),
            reviewed=True,
            regime=regime,
        )

    def describe(self) -> str:
        """O que a barra de status mostra: quantos diagramas e em que regime."""
        if self.is_empty:
            return "página sem diagrama"
        plural = "s" if len(self.diagrams) > 1 else ""
        return f"{len(self.diagrams)} diagrama{plural}" + (f" · {self.regime}" if self.regime else "")

    @classmethod
    def from_page(cls, page: FieldPage) -> FieldDraft:
        """Retoma uma página já anotada, para corrigi-la em vez de recomeçá-la."""
        return cls(
            pdf_name=page.pdf,
            page=page.page,
            regime=page.regime,
            diagrams=[replace(item) for item in page.diagrams],
        )
