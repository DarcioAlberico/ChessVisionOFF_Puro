"""A pasta de tablebases Syzygy aberta uma vez, consultada por posição (S-538).

**É o irmão de `engine.py`, e a assimetria entre os dois é o item.** O motor é um processo que
*estima*; a tabela é um arquivo que *sabe*. Nos finais que ela cobre, a resposta dela vence -- e
fora deles ela diz que não sabe, em vez de chutar. Os dois convivem: quem decide qual resposta vai
para a tela é `ui/finais.py`, e este módulo só abre a pasta e pergunta.

**Opcional de verdade, como o motor (S-33).** Sem pasta configurada, `abrir` devolve `None` e nada
no programa muda. Os arquivos de cinco peças somam ~1 GB e os de seis, ~150 GB: não vêm no
repositório, não têm caminho padrão e não são baixados por ninguém aqui.

**A pasta é aberta uma vez e fica aberta**, pela mesma razão que o processo do motor fica: cada
`open_tablebase` varre o diretório e abre descritores para cada arquivo, e fazer isso a cada
posição numa análise contínua a 800 ms custaria mais que a própria busca.

**Toda falha vira "não sei".** Uma posição com direito de roque não cabe em Syzygy (a tabela não
os representa), um arquivo pode estar truncado, o disco de rede pode sumir. Nenhum desses é motivo
para a sala parar de funcionar: é o contrato de degradação do projeto desde a S-53, e aqui ele é
literal -- a resposta "não tenho este final" já é uma resposta prevista.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess

logger = logging.getLogger(__name__)

__all__ = ["Finais", "Resultado", "abrir"]


@dataclass(frozen=True)
class Resultado:
    """O que a tabela sabe da posição, do ponto de vista de **quem está no lance**."""

    wdl: int
    """`+2` ganho, `+1` ganho que a regra dos 50 lances anula, `0` tábua, e os negativos
    espelhados. É a escala do próprio Syzygy, e traduzi-la aqui perderia a distinção do `±1`."""

    dtz: int | None
    """Lances até a próxima captura ou lance de peão, com o sinal do WDL. `None` quando a tabela
    de DTZ não está no disco -- há quem baixe só as WDL, que são um terço do tamanho."""


class Finais:
    """Uma pasta de Syzygy aberta. `consultar` devolve `None` para todo final que ela não cobre."""

    def __init__(self, pasta: str | Path, *, tabela: Any = None) -> None:
        self.pasta = Path(pasta)
        self._tabela = tabela
        """A tabela do `python-chess`, ou o que o teste injetar. `None` é "ainda não abri".

        Injetável porque um arquivo `.rtbw` de verdade não cabe nesta suíte -- o menor conjunto
        útil passa de 1 GB --, e sem a injeção o caminho que leva a resposta da tabela até a tela
        ficaria sem nenhuma afirmação. Ver `tests/test_tablebase.py`."""

    @property
    def aberta(self) -> bool:
        return self._tabela is not None

    def abrir(self) -> bool:
        """Abre a pasta. Devolve se deu certo; não levanta, porque ausência é caso normal."""
        if self._tabela is not None:
            return True
        if not self.pasta.is_dir():
            logger.info("Pasta de tablebases não existe: %s", self.pasta)
            return False
        try:
            import chess.syzygy

            self._tabela = chess.syzygy.open_tablebase(str(self.pasta))
        except Exception as exc:  # noqa: BLE001 - arquivo de terceiro, disco de rede, permissão
            logger.warning("Pasta de tablebases não pôde ser aberta (%s): %s", self.pasta, exc)
            return False
        return True

    def close(self) -> None:
        tabela, self._tabela = self._tabela, None
        if tabela is None:
            return
        try:
            tabela.close()
        except Exception as exc:  # pragma: no cover - encerramento é best-effort
            logger.debug("Falha ao fechar as tablebases: %s", exc)

    def __enter__(self) -> Finais:
        self.abrir()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def consultar(self, board: chess.Board) -> Resultado | None:
        """O resultado exato da posição, ou `None` quando a tabela não a cobre.

        **Direito de roque é `None` e não erro.** Syzygy não representa roque -- as tabelas são
        geradas sobre posições sem ele --, e `probe_wdl` levanta `ValueError` nesse caso. Numa
        posição de cinco peças com um rei que ainda pode rocar, a resposta certa é "não sei".
        """
        if not self.abrir():
            return None
        if board.castling_rights:
            return None
        assert self._tabela is not None
        try:
            wdl = self._tabela.get_wdl(board)
        except Exception as exc:  # noqa: BLE001 - ver o cabeçalho: toda falha vira "não sei"
            logger.debug("Consulta à tabela de finais falhou: %s", exc)
            return None
        if wdl is None:
            return None
        try:
            dtz = self._tabela.get_dtz(board)
        except Exception as exc:  # noqa: BLE001 - quem tem só as WDL cai aqui, e não é erro
            logger.debug("DTZ indisponível para esta posição: %s", exc)
            dtz = None
        return Resultado(wdl=int(wdl), dtz=None if dtz is None else int(dtz))


def abrir(pasta: str | Path | None) -> Finais | None:
    """A pasta das preferências virada leitor, ou `None` quando não há pasta (S-538).

    Não abre nada aqui: o primeiro `consultar` é quem paga a varredura do diretório, do mesmo modo
    que `EngineAnalyzer` só sobe o processo na primeira análise. Uma sessão que nunca chega a um
    final nunca toca o disco.
    """
    limpo = str(pasta or "").strip().strip('"')
    if not limpo:
        return None
    return Finais(limpo)
