"""Gera o bundle Windows e prepara a pasta que o usuário recebe (S-55).

    uv sync --extra dev --extra packaging
    uv run python packaging/build_windows.py

Faz três coisas que o `pyinstaller` sozinho não faz, e as três são o motivo deste arquivo
existir em vez de uma linha no README:

1. **Cria as pastas graváveis ao lado do executável.** `data/`, `models/`, `PDF/`, `PGN/` e
   `logs/` nascem vazias na `dist/`. Sem isso o primeiro `Ctrl+S` do usuário falharia ao
   gravar num diretório que não existe -- e falharia depois de ele ter corrigido um diagrama.
2. **Copia o checkpoint, se houver.** Um bundle sem `models/piece_classifier.pt` abre e não
   lê nada; o programa avisa, mas a primeira impressão é de coisa quebrada.
3. **Mede o tamanho e o grava em `docs/metrics/bundle.json`.** O README declara um número, e
   um número declarado que ninguém recalcula envelhece: ele ficou publicando *"696 MB, 5.247
   arquivos"* de um build de 2026-08-09 que já não existia -- e que nem tinha 5.247 arquivos.
   Agora o número sai do disco, é versionado com o commit que o produziu, e
   `tests/test_docs.py` falha se o README divergir dele (S-135).

Não assina o executável nem gera instalador: SmartScreen vai avisar na primeira execução, e
resolver isso exige um certificado de assinatura de código, que é uma decisão (e uma
despesa) do dono do projeto.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

PROJETO = Path(__file__).resolve().parents[1]
SPEC = PROJETO / "packaging" / "cvoff.spec"
SAIDA = PROJETO / "dist" / "ChessVisionOFF"

PASTAS_DO_USUARIO = ("data", "models", "PDF", "PGN", "logs")
"""Nascem vazias ao lado do `.exe`. Ficam de fora do bundle, e por motivos diferentes.

As quatro primeiras são do **usuário**: rótulo corrigido, checkpoint, livro, PGN exportado.
Dentro do bundle elas sumiriam a cada reinstalação.

`logs/` é do **programa**, e entrou na S-127. Ela é criada aqui e não só na primeira falha
porque é para onde a `cvoff.spec` manda olhar quando a janela não abre -- e uma pasta que só
existe depois do problema é uma instrução que não se pode seguir. `configure_logging` também a
cria sozinha, o que cobre a pasta apagada à mão."""

logger = logging.getLogger("cvoff.build")


def tamanho_em_mb(pasta: Path) -> float:
    return sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file()) / (1024 * 1024)


def build(*, limpar: bool) -> int:
    if not SPEC.exists():
        logger.error("Spec não encontrada em %s.", SPEC)
        return 2

    comando = [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm"]
    if limpar:
        comando.append("--clean")

    logger.info("Rodando: %s", " ".join(comando))
    resultado = subprocess.run(comando, cwd=PROJETO, check=False)
    if resultado.returncode != 0:
        logger.error("PyInstaller falhou com código %d.", resultado.returncode)
        return resultado.returncode

    if not SAIDA.exists():
        logger.error("O build terminou sem erro mas %s não existe.", SAIDA)
        return 1

    preparar_pastas_do_usuario()
    copiar_checkpoint()

    mb = gravar_metricas()
    logger.info("Pronto: %s (%.0f MB, %d arquivos).", SAIDA, mb, sum(1 for _ in SAIDA.rglob("*")))
    logger.info("Zipe a pasta inteira. Ela roda numa máquina Windows sem Python instalado.")
    if mb > 1500:
        logger.warning(
            "Passou de 1,5 GB. Vale conferir se algo de desenvolvimento entrou -- a lista "
            "`excludes` da spec é onde isso se corrige."
        )
    return 0


def preparar_pastas_do_usuario() -> None:
    for nome in PASTAS_DO_USUARIO:
        destino = SAIDA / nome
        destino.mkdir(parents=True, exist_ok=True)
        logger.info("Pasta gravável pronta: %s", destino.relative_to(SAIDA))


def _commit_atual() -> str:
    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJETO,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # pragma: no cover - maquina sem git
        return "desconhecido"
    return resultado.stdout.strip() or "desconhecido"


def gravar_metricas() -> float:
    """Mede a `dist/` e grava `docs/metrics/bundle.json`. Devolve o tamanho em MB.

    **O commit vai junto de propósito.** Sem ele o arquivo diz "696 MB" e não diz de quê: o
    número que o README publicava era de um build que ainda levava `pythonnet` e `clr_loader`,
    removidos na S-69, e ninguém tinha como saber isso lendo o número. Com o commit, a
    defasagem é uma pergunta que o `git log` responde.

    **A unidade é a do `tamanho_em_mb`, que é binária (`1024²`)** — a mesma que o explorador de
    arquivos do Windows mostra, e a mesma de que saiu o "696 MB" que o README publica desde a
    S-55. Trocá-la por `10**6` faria o mesmo bundle passar a medir 730 e pareceria que ele
    engordou. O campo se chama `mb` porque é assim que o README o chama; a unidade está aqui.
    """
    arquivos = [f for f in SAIDA.rglob("*") if f.is_file()]
    mb = round(tamanho_em_mb(SAIDA))
    metricas: dict[str, object] = {
        "mb": mb,
        "arquivos": len(arquivos),
        "data": date.today().isoformat(),
        "commit": _commit_atual(),
    }
    destino = PROJETO / "docs" / "metrics" / "bundle.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(metricas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Métricas do bundle em %s: %s", destino.relative_to(PROJETO), metricas)
    return float(mb)


def copiar_checkpoint() -> None:
    origem = PROJETO / "models" / "piece_classifier.pt"
    if not origem.exists():
        logger.warning(
            "Sem %s: o bundle abre, mas não lê diagrama nenhum até alguém pôr um checkpoint "
            "em models/ ao lado do executável.",
            origem.name,
        )
        return
    destino = SAIDA / "models" / origem.name
    shutil.copy2(origem, destino)
    logger.info("Checkpoint incluído: %s (%.1f MB).", destino.name, destino.stat().st_size / (1024 * 1024))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="apaga o cache do PyInstaller antes. Mais lento, e o que se faz quando o build anterior mentiu.",
    )
    args = parser.parse_args()
    return build(limpar=args.clean)


if __name__ == "__main__":
    raise SystemExit(main())
