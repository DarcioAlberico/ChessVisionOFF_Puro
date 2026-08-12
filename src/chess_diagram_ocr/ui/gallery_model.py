"""O estado da galeria: onde estou, o que edito e o que isso grava (S-67).

Sem `import tkinter`, pela regra que organizou a Fase 6: o que dá para testar não mora na
janela. O que está aqui é justamente o que erra sem alarde -- navegar até o fim da lista,
trocar de diagrama com o campo pela metade, "aplicar a todos" -- e nada disso deveria exigir
abrir um Tk para ser verificado.

**A regra que atravessa o módulo: o campo em branco apaga a declaração.** Não é o mesmo que
declarar vazio. Um `[White]` em branco significa "não declarei, use o que o PDF disser", e
por isso a anotação some do JSON em vez de virar uma entrada com string vazia -- senão o
arquivo cresceria com uma linha por diagrama visitado, e "visitei" não é "anotei".
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from chess_diagram_ocr.gallery import (
    RESERVED_HEADERS,
    DiagramAnnotation,
    GalleryAnnotations,
    lichess_analysis_url,
    save_annotations,
)
from chess_diagram_ocr.gallery_scan import GalleryEntry, GalleryIndex
from chess_diagram_ocr.semantics import compose_fen

__all__ = ["HEADER_FIELDS", "GalleryModel"]

HEADER_FIELDS: tuple[str, ...] = (
    "White",
    "Black",
    "Event",
    "Site",
    "Date",
    "Round",
    "Result",
    "Annotator",
)
"""Os headers com campo fixo no frame lateral.

São os oito que um diagrama de livro costuma ter declarável. Qualquer outro header continua
possível pelo par livre da tela -- `DiagramAnnotation.headers` é um dicionário, não um
conjunto fechado.
"""


@dataclass
class GalleryModel:
    """O índice varrido, a posição atual e as anotações -- os três juntos e sem widget."""

    index: GalleryIndex = field(default_factory=GalleryIndex)
    annotations: GalleryAnnotations = field(default_factory=GalleryAnnotations)
    pdf_path: Path | None = None
    position: int = 0

    gallery_dir: Path | None = None
    """Onde gravar. `None` usa `data/gallery/`.

    Existe para ser injetável, e não por configuração: `save_annotations` recebe o diretório
    por argumento padrão, que é resolvido na definição -- sem este campo, testar a gravação
    exigiria remendar um global, e o teste que tentou isso gravou no `data/` de verdade."""

    # ------------------------------------------------------------------------ navegação

    def __len__(self) -> int:
        return len(self.index)

    @property
    def is_empty(self) -> bool:
        return len(self.index) == 0

    @property
    def current(self) -> GalleryEntry | None:
        """O diagrama selecionado, ou `None` quando o livro não foi varrido."""
        if self.is_empty:
            return None
        return self.index.entries[self.clamped_position()]

    def clamped_position(self) -> int:
        """A posição corrigida para dentro da lista. Nunca levanta."""
        if self.is_empty:
            return 0
        return max(0, min(self.position, len(self.index) - 1))

    def go_to(self, position: int) -> bool:
        """Vai para uma posição. Devolve se mudou -- quem chama redesenha só quando mudou."""
        if self.is_empty:
            return False
        alvo = max(0, min(int(position), len(self.index) - 1))
        if alvo == self.clamped_position():
            self.position = alvo
            return False
        self.position = alvo
        return True

    def step(self, delta: int) -> bool:
        """Anterior/próximo. **Não circula**: chegar ao fim da lista é informação.

        Circular faria o último diagrama do livro parecer o primeiro, e numa galeria de
        centenas ninguém percebe a volta -- percebe que "o livro tem menos do que eu pensava".
        """
        return self.go_to(self.clamped_position() + int(delta))

    def sync_to_page(self, page_index: int) -> bool:
        """Segue o visualizador de PDF: mostra o diagrama daquela página, se houver.

        Página sem diagrama **não move a galeria**. Virar para uma página de texto e ver o
        diagrama saltar para outro lugar seria pior que não seguir: a pessoa perderia o que
        estava anotando por ter rolado o PDF.
        """
        posicao = self.index.position_of(int(page_index))
        return self.go_to(posicao) if posicao is not None else False

    @property
    def page_index(self) -> int | None:
        """A página do diagrama atual, para o visualizador de PDF seguir a galeria."""
        atual = self.current
        return None if atual is None else atual.page_index

    # ------------------------------------------------------------------------ anotação

    @property
    def current_annotation(self) -> DiagramAnnotation:
        atual = self.current
        return DiagramAnnotation() if atual is None else self.annotations.get(*atual.key)

    def edit(self, **campos: object) -> DiagramAnnotation | None:
        """Muda campos da anotação do diagrama atual. `None` se não há diagrama."""
        atual = self.current
        if atual is None:
            return None
        return self.annotations.update(atual.page_index, atual.diagram_index, **campos)

    def set_header(self, name: str, value: str) -> DiagramAnnotation | None:
        """Grava um header. Valor em branco **remove** a declaração -- ver o docstring."""
        atual = self.current
        if atual is None:
            return None
        nome = name.strip()
        if not nome or nome in RESERVED_HEADERS:
            return self.current_annotation

        headers = dict(self.current_annotation.headers)
        texto = value.strip()
        if texto:
            headers[nome] = texto
        else:
            headers.pop(nome, None)
        return self.edit(headers=headers)

    def apply_headers_to_all(self, names: tuple[str, ...] = HEADER_FIELDS) -> int:
        """Copia os headers declarados neste diagrama para todos os outros. Devolve quantos.

        Só os **declarados**: um campo em branco aqui não apaga o que outro diagrama tem.
        Aplicar a todos é para preencher `Event` e `Site` de um livro inteiro de uma vez, e
        transformar isso num apagador em massa seria um jeito caro de perder trabalho.
        """
        origem = {
            nome: valor
            for nome, valor in self.current_annotation.headers.items()
            if nome in names and valor
        }
        if not origem or self.is_empty:
            return 0

        atingidos = 0
        for entrada in self.index.entries:
            if entrada.key == (self.current.key if self.current else None):
                continue
            anterior = self.annotations.get(*entrada.key)
            headers = {**anterior.headers, **origem}
            if headers != anterior.headers:
                self.annotations.set(entrada.page_index, entrada.diagram_index, replace(anterior, headers=headers))
                atingidos += 1
        return atingidos

    def save(self) -> Path | None:
        """Grava as anotações do livro. `None` quando não há livro aberto."""
        if self.pdf_path is None:
            return None
        if self.gallery_dir is None:
            return save_annotations(self.pdf_path, self.annotations)
        return save_annotations(self.pdf_path, self.annotations, directory=self.gallery_dir)

    # ------------------------------------------------------------------------ derivados

    def effective_fen(self) -> str:
        """A FEN que este diagrama terá no PGN, já com a declaração por cima.

        É o que a galeria mostra e o que alimenta o link do Lichess. Recalcular aqui em vez
        de guardar evita o defeito clássico: mudar o lance e o link continuar apontando para
        a posição antiga.
        """
        atual = self.current
        if atual is None:
            return ""
        anotacao = self.current_annotation
        lado = anotacao.side_to_move or atual.side_to_move
        return compose_fen(atual.placement, lado == "w", fullmove=anotacao.move_number or 1)

    def lichess_url(self) -> str:
        return lichess_analysis_url(self.effective_fen()) if self.current is not None else ""

    def exports_lichess_link(self, *, default: bool) -> bool:
        """Se este diagrama sai com link, dado o padrão da exportação."""
        declarado = self.current_annotation.lichess_link
        return default if declarado is None else declarado

    def annotated_count(self) -> int:
        """Quantos diagramas do livro têm alguma declaração. Vai para a barra de status."""
        return len(self.annotations.entries)

    def describe_position(self) -> str:
        """`"diagrama 12 de 340 — página 47"`, para o rótulo de navegação."""
        if self.is_empty:
            return "nenhum diagrama varrido"
        atual = self.index.entries[self.clamped_position()]
        return f"diagrama {self.clamped_position() + 1} de {len(self.index)} — página {atual.page_number}"
