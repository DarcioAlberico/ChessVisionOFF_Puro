"""O inventário do editor de texto: nada de recurso sem comando, atalho e teste (S-256).

**Este plano acrescentou mais de vinte recursos a uma aba que tinha seis controles, e cada um deles
é fácil de fazer errado rápido.** `tag_configure("negrito", font=...)` mais um `tag_add` resolve o
negrito na tela em quatro linhas e entrega, no Salvar, o `.txt` de antes -- o achado 1 do
ROADMAP_EDITOR, que nenhum teste de interface pegaria porque **na tela está tudo certo**.

É a mesma classe de defeito que a S-233 mede para as peles, com um agravante: lá o comando existe e
está escondido; aqui o recurso **existe e não persiste**, que é pior, porque parece funcionar.

Este comando publica as quatro perguntas do item como um JSON em `docs/metrics/`, na disciplina da
S-218 -- com a data e o commit em que ele foi medido. Quem cobra as respostas é
`tests/test_texto_inventario_editor.py`; o que este arquivo faz é **deixá-las escritas**, para quem
ler o repositório em três meses não precisar rodar a suíte para saber o que a aba faz.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from dataclasses import fields
from datetime import date
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT
from ..logging_setup import configure_logging
from ..text import exportacao, paleta, rico
from ..ui import alcance, atalhos, menu, texto_panel
from . import cli_errors

logger = logging.getLogger(__name__)

DESTINO_PADRAO = PROJECT_ROOT / "docs" / "metrics" / f"editor_inventario_{date.today():%Y%m%d}.json"

_APELIDOS: dict[str, str] = texto_panel.COMANDOS_DA_ABA
"""Comando -> método do painel, **lido de quem tem os métodos** (`ui/texto_panel.py`).

O apelido continua aqui para o inventário e para os testes que o nomeiam; a declaração mudou de casa
quando a janela passou a gerar as ligações dela em vez de repeti-las em `lambda`. Ver o docstring de
`texto_panel.COMANDOS_DA_ABA`."""


def _commit() -> str:
    """O commit em que isto foi medido. `""` num checkout sem git -- e o campo sai mesmo assim."""
    try:
        pronto = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # pragma: no cover - maquina sem git
        return ""
    return pronto.stdout.strip() if pronto.returncode == 0 else ""


def inventario() -> dict[str, Any]:
    """As quatro perguntas da S-256, respondidas sem abrir janela nenhuma."""
    atributos = [campo.name for campo in fields(rico.Atributos)]
    por_formato = exportacao.suporte_por_formato()
    do_editor = list(_APELIDOS)
    no_menu = set(menu.acoes_declaradas())
    paleta_atual = paleta.paleta()
    return {
        "item": "S-256 · o inventário do editor de texto",
        "quando": f"{date.today():%Y-%m-%d}",
        "commit": _commit(),
        "atributos_do_documento": atributos,
        "suporte_por_formato": por_formato,
        "atributos_sem_formato_que_os_suporte": sorted(
            atributo
            for atributo in atributos
            if not any(tabela.get(atributo) for tabela in por_formato.values())
        ),
        "comandos_do_editor": do_editor,
        "comandos_do_editor_fora_do_menu": sorted(acao for acao in do_editor if acao not in no_menu),
        "peles_que_perdem_comando": alcance.perdidos(),
        "teclas_proprias_do_editor": dict(atalhos.TECLAS_DO_EDITOR),
        "acoes_que_a_aba_toma_para_si": sorted(texto_panel.ACOES_PROPRIAS),
        "paleta": {
            "prateleiras": {p.nome: len(p.simbolos) for p in paleta_atual.prateleiras},
            "simbolos": len(paleta_atual.simbolos),
            "fora_do_modelo": sorted(paleta_atual.fora_do_modelo),
            "sequencias": len(paleta_atual.sequencias()),
        },
    }


@cli_errors
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, default=DESTINO_PADRAO, help="Onde gravar o inventário.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose)

    dados = inventario()
    destino = Path(args.json)
    destino.parent.mkdir(parents=True, exist_ok=True)
    from ..atomic_io import atomic_write_text

    atomic_write_text(destino, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")
    logger.info("Inventário do editor gravado em %s", destino)

    print(f"comandos do editor .......... {len(dados['comandos_do_editor'])}")
    print(f"atributos do documento ...... {len(dados['atributos_do_documento'])}")
    print(f"formatos de exportação ...... {len(dados['suporte_por_formato'])}")
    print(f"símbolos na paleta .......... {dados['paleta']['simbolos']}")
    perdidos = dados["peles_que_perdem_comando"]
    print(f"peles que perdem comando .... {len(perdidos)}")
    return 1 if perdidos or dados["comandos_do_editor_fora_do_menu"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
