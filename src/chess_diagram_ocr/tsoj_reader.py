"""Leitor externo `Chess_diagram_to_FEN` como segunda opinião **local** (S-66).

**O que é.** Um adaptador para o projeto de Jost Triller (MIT,
https://github.com/tsoj/Chess_diagram_to_FEN), que lê a posição de um diagrama já recortado.
Satisfaz o `RemoteFenProvider` da S-32 -- que é `Protocol` justamente para isto: o docstring
daquele módulo já dizia que "um segundo modelo local satisfaz a mesma interface".

**Por que ele, e por que local.** Medido nos 20 diagramas do `Niemeijer - Zwarte Magie
(1945)`, onde o classificador local afunda (confiança mínima média 0,25, zero acima do gate):

| | leitor local | este |
|---|---|---|
| coerentes com o tema do livro (1 rei de cada, ≥1 dama preta, sem peão na borda) | 12/20 | **18/20** |
| p6_d0 / p6_d1 / p13_d2, conferidos casa a casa | 60 / 41 / 23 de 64 | **64 / 64 / 64** |

E local quer dizer local: nada sai da máquina, então este caminho **não passa pelo
consentimento da S-32**. Ele existe em boa parte para tornar aquele desnecessário.

**Só dois dos cinco modelos.** O pacote traz `existence`, `quad`, `image_rotation`,
`position` e `orientation` -- 296,1 MiB. Os dois primeiros respondem "há tabuleiro?" e "onde
estão os cantos?", que o `board_detection` deste projeto já respondeu antes de chegar aqui.
Medido, a poda para `position` + `orientation` (232,8 MiB, -21%) **não custou leitura**: os
três diagramas conferidos à mão continuaram 64/64, e o teste do tema subiu de 18/20 para
19/20. O que se perde é a guarda de imagem deitada 90°/180°, que mudou 1 dos 20 -- e que aqui
não faz falta porque o recorte já vem alinhado pelo detector.

**Duas asperezas do projeto de origem, tratadas aqui e não lá.** Ele declara
`requires-python >=3.11` e usa `ProjectiveTransform.from_estimate`, do scikit-image 0.26;
neste projeto o Python é 3.10 e o skimage para em 0.25.2, e sem ponte toda chamada morre em
`AttributeError`. E o `render_config` dele resolve `resources/pieces` relativo ao diretório
**corrente** no momento do import. As duas coisas são tratadas em `_imported_module`, que é
onde elas devem estar: não vale editar um clone de terceiro que o usuário vai atualizar.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

__all__ = ["TsojDiagramReader", "TsojUnavailableError", "build_local_provider"]

MODULE_NAME = "chess_diagram_to_fen"
"""O módulo de entrada do clone. Também serve de sonda: sem ele, o caminho não é um clone."""

_IMPORT_LOCK = threading.Lock()
"""O import mexe em `sys.path` e no diretório corrente, que são globais do processo.

A leitura roda em thread (o primeiro carregamento leva ~7 s), e duas threads importando ao
mesmo tempo deixariam o processo num diretório que ninguém pediu.
"""


class TsojUnavailableError(RuntimeError):
    """O leitor externo não está instalado ou não pôde ser carregado. Mensagem em pt-BR."""


@contextlib.contextmanager
def _cwd(path: Path) -> Iterator[None]:
    anterior = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(anterior)


def _bridge_skimage() -> None:
    """`ProjectiveTransform.from_estimate` para quem só tem scikit-image 0.25.

    O método novo é açúcar sobre o antigo: `estimate()` faz a mesma conta e devolve se
    convergiu. A ponte não muda resultado, só assinatura -- e some sozinha no dia em que o
    projeto subir para o skimage 0.26, porque o `hasattr` passa a ser verdadeiro.
    """
    from skimage.transform import ProjectiveTransform

    if hasattr(ProjectiveTransform, "from_estimate"):
        return

    def _from_estimate(cls: type, origem: Any, destino: Any) -> Any:
        transformacao = cls()
        transformacao.estimate(origem, destino)
        return transformacao

    ProjectiveTransform.from_estimate = classmethod(_from_estimate)  # type: ignore[attr-defined]
    logger.debug("Ponte de compatibilidade do scikit-image instalada para o leitor externo.")


def _imported_module(checkout: Path) -> Any:
    """Importa o módulo do clone, com `sys.path` e diretório corrente arrumados.

    Não guarda o resultado em cache aqui: `sys.modules` já é o cache, e um segundo cache
    esconderia do usuário que trocar o caminho nas preferências exige reiniciar.
    """
    if MODULE_NAME in sys.modules:
        return sys.modules[MODULE_NAME]

    entrada = checkout / f"{MODULE_NAME}.py"
    if not entrada.is_file():
        raise TsojUnavailableError(
            f"{entrada} não existe. O leitor externo é um clone de "
            f"https://github.com/tsoj/Chess_diagram_to_FEN com os pesos baixados "
            f"(`./download_models.sh`); aponte o caminho do clone nas preferências."
        )
    if not (checkout / "models").is_dir():
        raise TsojUnavailableError(
            f"{checkout / 'models'} não existe. O clone está lá, mas os pesos não foram "
            f"baixados: rode `./download_models.sh` dentro dele."
        )

    with _IMPORT_LOCK:
        if MODULE_NAME in sys.modules:
            return sys.modules[MODULE_NAME]
        try:
            _bridge_skimage()
            # O diretorio corrente importa: `src/render_config.py` do clone le
            # `resources/pieces` relativo a ele no momento do import.
            with _cwd(checkout):
                if str(checkout) not in sys.path:
                    sys.path.insert(0, str(checkout))
                import importlib

                return importlib.import_module(MODULE_NAME)
        except TsojUnavailableError:
            raise
        except Exception as exc:  # dependencia faltando, peso corrompido, versao incompativel
            # **No `.exe` a resposta é outra, e ela é sabida (S-366).** O clone importa
            # `skimage` e `scipy`, e o bundle não os leva -- 95 MB para um caminho que exige o
            # usuário ter clonado um repositório de terceiro e baixado 232 MiB de pesos. Dizer
            # "não pôde ser carregado: No module named 'skimage'" mandaria alguém procurar um
            # defeito onde há uma decisão de empacotamento.
            if getattr(sys, "frozen", False):
                raise TsojUnavailableError(
                    "A segunda opinião local não está disponível na versão empacotada: o leitor "
                    "externo depende de bibliotecas que o executável não leva (scipy e "
                    "scikit-image, 95 MB). Use a instalação de desenvolvimento para esta opção."
                ) from exc
            raise TsojUnavailableError(
                f"O leitor externo está em {checkout} mas não pôde ser carregado: {exc}"
            ) from exc


class TsojDiagramReader:
    """Segunda opinião local. Recebe o recorte já alinhado e devolve o campo de peças."""

    def __init__(self, checkout: Path, *, game: str = "chess") -> None:
        self.checkout = Path(checkout)
        self.game = game

    @property
    def name(self) -> str:
        return f"Chess_diagram_to_FEN ({self.game}, local)"

    def predict(self, image_rgb: np.ndarray) -> str:
        """A colocação lida, ou `TsojUnavailableError` / `RuntimeError` com o motivo.

        Devolve **só o campo de peças**, e não a FEN completa que o projeto de origem monta:
        o lado a jogar dali é sempre `w` fixo, e adotá-lo apagaria o que a S-17 deduz do
        texto da página. Quem chama já tem essa informação e não deve perdê-la aqui.
        """
        if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
            raise ValueError(f"Esperada imagem RGB (H, W, 3), recebida {image_rgb.shape}.")

        modulo = _imported_module(self.checkout)
        from PIL import Image

        imagem = Image.fromarray(np.ascontiguousarray(image_rgb.astype(np.uint8)), mode="RGB")

        # `get_board_from_cropped_img` + `is_board_flipped` em vez de `get_fen`: o recorte ja
        # veio do detector deste projeto, entao os tres modelos de localizacao do `get_fen`
        # nao teriam o que acrescentar -- e sao 63,3 MiB de peso a carregar. Ver o docstring
        # do modulo para o que a poda custou (nada, medido).
        with _cwd(self.checkout):
            posicao = modulo.get_board_from_cropped_img(imagem, self.game)
            if posicao is None:
                raise RuntimeError("O leitor externo não reconheceu um tabuleiro neste recorte.")
            if modulo.is_board_flipped(posicao, self.game):
                posicao = modulo.rotate_board(posicao, self.game)
            fen = str(posicao.fen())

        return fen.split(" ")[0]


def build_local_provider(settings: Any) -> TsojDiagramReader | None:
    """O leitor local que a configuração autoriza, ou `None`.

    Mesmo contrato do `net_correction.build_provider`, e pelo mesmo motivo: ser o **único**
    caminho para um leitor existir é o que permite provar que, sem configuração, ele não roda.
    Aqui a prova vale menos que lá -- nada sai da máquina --, mas 232,8 MiB de peso carregados
    sem ninguém pedir também não são de graça.
    """
    if not getattr(settings, "is_usable", False):
        return None
    return TsojDiagramReader(Path(settings.path))
