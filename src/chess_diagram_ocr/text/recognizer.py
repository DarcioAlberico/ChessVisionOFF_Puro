"""O reconhecedor de glifo, atrás do protocolo que a S-42 já criou (S-181).

**O OCR de glifo não é uma via alternativa: é mais um `TextRecognizer`.** É a decisão que a S-43
tomou para o RapidOCR, e o motivo continua valendo -- quem satisfaz o protocolo herda de graça
todo o aparato da S-16: agrupamento por coluna, `dominant_placement`, `assign_lines_to_diagrams`,
os tiers de legenda, o filtro de prosa, a checagem de contradição. Por isso esta entrega **não
toca uma linha** de `ocr_caption.py` nem de `pdf_text.py`; a única mudança fora deste subpacote é
o nome `glifo` entrar em `ocr.KNOWN_ENGINES`.

**A segmentação era provisória e deixou de ser (2026-08-22).** Na Fase 25 ela vivia em funções
privadas daqui, escritas sem medição, justamente para que o verificador de status não dissesse
que a Fase 26 tinha começado quando ela não tinha. A S-184, a S-185 e a S-187 a substituíram
pelos módulos medidos, e este arquivo passou a ser o que ele devia ser desde o começo: a costura
entre a segmentação, o classificador e o protocolo.

O que ele **não** faz, e cada um tem dono: separar glifo colado é a S-186, ler a linha em bloco é
a S-188, e a confiança por concordância é a S-189.

**O que o glifo faz melhor que os outros três motores, e é estrutural.** O `allowlist` aqui
restringe o **decodificador**, e não a saída: as colunas proibidas saem da matriz de
probabilidades antes do argmax. Nos outros motores ele é filtro posterior -- e o comentário de
`ocr.filter_by_allowlist` já diz o que isso custa: *"o motor já escolheu `8` em vez de `B` antes
de chegar aqui, e apagar o `8` não traz o `B` de volta"*. Aqui traz.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..ocr import TextBox
from .binarizacao import binarize
from .boxes import Caixa, caixas_de_caractere, escala_de_texto, excluir_diagramas, unir_pingos
from .duas_linhas import descartar_fragmentos
from .linhas import envolve, ordem_em_faixa, quebrar_em_linhas, texto_da_linha
from .modelo import ClassificadorDeGlifo, ModeloInvalido, carregar_classificador

logger = logging.getLogger(__name__)

NOME = "glifo"


def _cinza(imagem: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.cvtColor(imagem, cv2.COLOR_RGB2GRAY) if imagem.ndim == 3 else imagem


class GlyphRecognizer:
    """Segmenta o recorte, classifica cada glifo, agrupa em linha, devolve `TextBox`."""

    def __init__(self, classificador: ClassificadorDeGlifo, leitor_de_linha: object | None = None) -> None:
        self._classificador = classificador
        self._leitor_de_linha = leitor_de_linha
        """O segundo opinante da S-188, que lê a **faixa da linha** em vez de o glifo.

        `None` é o caminho de sempre, e é o padrão: a medição da faixa de legenda foi feita sem
        ele, e ligá-lo por omissão mudaria um número já publicado. Quem o passa é o leitor de
        página (`text/leitor.py`), onde ele foi medido -- ver a docstring de lá."""

    @property
    def name(self) -> str:
        return NOME

    @property
    def classifier(self) -> ClassificadorDeGlifo:
        return self._classificador

    def read(
        self,
        image_rgb: np.ndarray,
        *,
        allowlist: str = "",
        escala: int | None = None,
        diagramas: list[tuple[float, float, float, float]] | None = None,
    ) -> list[TextBox]:
        """Uma `TextBox` por linha, em pixels da imagem recebida. Nunca levanta por não achar.

        `escala` é a altura de caractere **da página**, para quem lê uma faixa dentro dela: uma
        faixa de três letras não tem população para medir escala nenhuma, e medi-la ali daria uma
        régua que varia de faixa para faixa. Fora do protocolo `TextRecognizer` de propósito --
        os outros três motores não têm o que fazer com ela.
        """
        if image_rgb is None or getattr(image_rgb, "size", 0) == 0:
            return []

        cinza = _cinza(np.ascontiguousarray(image_rgb))
        binaria = binarize(cinza)
        if escala is None:
            escala = escala_de_texto(binaria)
        caixas = unir_pingos(caixas_de_caractere(binaria, escala=escala), escala=escala)
        if diagramas:
            caixas = excluir_diagramas(caixas, diagramas, escala=escala)
        grupos = quebrar_em_linhas(ordem_em_faixa(caixas))
        # **A linha que é só pedaço de descendente da vizinha some aqui** (S-198). A faixa que a
        # `ocr_caption` manda ler é dilatada, então ela encosta na linha de cima e o que entra
        # são caixas baixas demais para serem caractere -- e elas viram texto, com confiança de
        # leitura normal. Medido em 2026-08-23 sobre 155 faixas de 11 livros de camada
        # editorada (`docs/metrics/texto_duas_linhas.json`): **CER 0,2725 -> 0,2248**.
        #
        # O outro passo da S-198, `separar`, **não entra**: na mesma medição ele custou 0,0089
        # de CER, disparando em 15 das 155 faixas. O item previa +0,3 de F1 no acervo de lá; aqui
        # ele não paga, e o número está no relatório em vez de na intenção.
        grupos = descartar_fragmentos(grupos, escala=escala)
        if not grupos:
            return []

        permitidos = self._colunas_permitidas(allowlist)
        saida: list[TextBox] = []
        for grupo in grupos:
            lidos = self._classificar([c.recortar(cinza) for c in grupo], permitidos)
            if not lidos:
                continue
            if self._leitor_de_linha is not None:
                from .leitura_de_linha import em_bloco

                casados = em_bloco(cinza, grupo, lidos, self._leitor_de_linha)
                lidos = [(item.caractere, item.confianca) for item in casados]
            texto = texto_da_linha(grupo, [char for char, _ in lidos])
            if not texto:
                continue
            saida.append(
                TextBox(
                    text=texto,
                    bbox=envolve(grupo),
                    # **A mínima, e não a média.** Uma legenda com um caractere adivinhado no
                    # meio não é uma legenda 90% confiável, e o `MIN_CONFIDENCE = 0.30` da S-42
                    # existe justamente para cortar legenda adivinhada -- a média o burlaria.
                    confidence=min(confianca for _, confianca in lidos),
                )
            )
        return saida

    def _colunas_permitidas(self, allowlist: str) -> np.ndarray | None:
        """Os índices de classe que o `allowlist` deixa passar, ou `None` para todos.

        **Restringe o decodificador, e não a saída.** Um `allowlist` que não casa com classe
        nenhuma vira `None` -- decodificar com zero classes devolveria lixo, e a resposta certa
        para "só aceito o que não existe" é responder como sem restrição e deixar o chamador ver
        o que veio.
        """
        if not allowlist:
            return None
        permitidos = set(allowlist)
        indices = [i for i, c in self._classificador.meta.idx_to_char.items() if c and set(c) <= permitidos]
        if not indices:
            logger.warning(
                "allowlist %r não casa com nenhuma das %d classes do modelo; lendo sem restrição.",
                allowlist,
                self._classificador.meta.num_classes,
            )
            return None
        return np.asarray(sorted(indices), dtype=np.int64)

    def _classificar(self, recortes: list[np.ndarray], permitidos: np.ndarray | None) -> list[tuple[str, float]]:
        if not recortes:
            return []
        if permitidos is None:
            return self._classificador.classificar(recortes)

        probs = self._classificador.probabilidades(recortes)
        if probs.size == 0:
            return []
        restrito = probs[:, permitidos]
        escolhidos = restrito.argmax(axis=1)
        idx_to_char = self._classificador.meta.idx_to_char
        return [
            (idx_to_char[int(permitidos[coluna])], float(restrito[linha, coluna]))
            for linha, coluna in enumerate(escolhidos)
        ]


def build_glyph_recognizer(
    model_path: str | Path = "",
    meta_path: str | Path | None = None,
    *,
    leitor_de_linha: object | None = None,
) -> GlyphRecognizer:
    """O construtor que `ocr.build_recognizer` chama. Levanta `ModeloInvalido` com o motivo.

    `model_path` vazio deixa `carregar_classificador` procurar o `.pt` ao lado do metadado, que é
    o caminho de quem pôs o arquivo em `models/`.
    """
    from .modelo import CAMINHO_PADRAO_META

    meta = Path(meta_path) if meta_path else CAMINHO_PADRAO_META
    pesos = Path(model_path) if str(model_path).strip() else None
    return GlyphRecognizer(carregar_classificador(meta, pesos), leitor_de_linha)


__all__ = ["NOME", "Caixa", "GlyphRecognizer", "ModeloInvalido", "build_glyph_recognizer"]
