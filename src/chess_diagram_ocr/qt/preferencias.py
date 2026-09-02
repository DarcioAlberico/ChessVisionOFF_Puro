"""O que a janela monta a partir das preferências antes de existir: o serviço e o motor (S-523).

**O defeito que isto conserta.** `qt/janela.py` não importava `settings.py` para nada além do OCR
de glifos. `PainelDeEstudo` aceita `analyzer` desde o porte e a janela nunca passava um -- e
`None` **esconde a seção inteira** (S-33), então uma máquina *com* Stockfish mostrava exatamente
o que uma máquina sem ele mostraria. E o `OcrService` nascia sem `caption_reader`, embora
`service.py` diga por escrito que *quem lê a configuração é a interface* (S-43): a perda pesa nos
livros sem camada de texto, onde a legenda é a única pista do número do lance. Do lado do Tk as
duas ligações existiam (`_build_analyzer`, e o serviço construído com `caption_reader_from_settings`);
o corte as levou sem que nada acusasse -- o padrão da S-500 a S-512, mais duas vezes.

**Por que fora de `qt/janela.py`.** As duas funções não precisam de widget nenhum: são a leitura
de `data/settings.json` virando os dois objetos que o pipeline e a sala recebem prontos, e por
isso são afirmáveis sem `QApplication`. E a janela está na catraca da S-136; o que só ela pode
fazer é ligar um painel ao outro, não construir o que os painéis recebem.
"""

from __future__ import annotations

import logging

from chess_diagram_ocr.config import DEFAULT_MODEL_PATH
from chess_diagram_ocr.engine import EngineAnalyzer, find_engine
from chess_diagram_ocr.ocr_caption import caption_reader_from_settings
from chess_diagram_ocr.service import OcrService
from chess_diagram_ocr.settings import Settings

logger = logging.getLogger(__name__)

__all__ = ["motor_das_preferencias", "servico_das_preferencias"]


def servico_das_preferencias(preferencias: Settings) -> OcrService:
    """O serviço do produto, com o OCR de legenda que as preferências autorizam (S-43/S-523).

    A configuração vem antes do serviço porque o OCR de legenda entra por ele. Construir o leitor
    aqui, e não dentro do serviço, é a separação da S-32: quem lê a configuração é a interface, e o
    pipeline recebe pronto o que ela autorizou. `None` -- OCR desligado, ou sem o extra instalado --
    é o pipeline de sempre.
    """
    return OcrService(
        model_path=DEFAULT_MODEL_PATH,
        caption_reader=caption_reader_from_settings(preferencias.ocr),
    )


def motor_das_preferencias(
    preferencias: Settings, *, env: dict[str, str] | None = None
) -> EngineAnalyzer | None:
    """Procura o motor. Não achar é o caso normal, e não é erro (S-33).

    O caminho das preferências vem primeiro, e **só ele** alcança um binário fora do `PATH` e dos
    diretórios conhecidos -- `find_engine()` sem argumento devolve `None` numa máquina em que o
    Stockfish mora numa pasta própria. `env` é o de `find_engine`, e existe para o teste não
    depender do `PATH` de quem o roda.

    O processo **não** é aberto aqui: `EngineAnalyzer` só o abre na primeira análise, e quem o fecha
    é a janela, no `closeEvent` -- um motor é um processo, não um widget, e sem `close()` cada
    abertura do programa deixaria um `stockfish.exe` vivo.
    """
    caminho = find_engine(preferencias.engine.path or None, env=env)
    if caminho is None:
        logger.info("Nenhum motor de análise encontrado; a seção de avaliação fica oculta.")
        return None
    logger.info("Motor de análise disponível: %s", caminho)
    return EngineAnalyzer(
        caminho,
        movetime_ms=preferencias.engine.movetime_ms,
        threads=preferencias.engine.threads,
    )
