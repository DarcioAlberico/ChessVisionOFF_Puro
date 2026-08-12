"""Gera o bundle Windows e prepara a pasta que o usuário recebe (S-55).

    uv sync --extra dev --extra packaging
    uv run python packaging/build_windows.py

Faz três coisas que o `pyinstaller` sozinho não faz, e as três são o motivo deste arquivo
existir em vez de uma linha no README:

1. **Cria as pastas graváveis ao lado do executável.** `data/`, `models/`, `PDF/` e `PGN/`
   nascem vazias na `dist/`. Sem isso o primeiro `Ctrl+S` do usuário falharia ao gravar
   num diretório que não existe -- e falharia depois de ele ter corrigido um diagrama.
2. **Copia o checkpoint, se houver.** Um bundle sem `models/piece_classifier.pt` abre e não
   lê nada; o programa avisa, mas a primeira impressão é de coisa quebrada.
3. **Mede e relata o tamanho.** O README declara um número, e um número declarado que
   ninguém recalcula envelhece. Aqui ele sai do disco.

Não assina o executável nem gera instalador: SmartScreen vai avisar na primeira execução, e
resolver isso exige um certificado de assinatura de código, que é uma decisão (e uma
despesa) do dono do projeto.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

PROJETO = Path(__file__).resolve().parents[1]
SPEC = PROJETO / "packaging" / "cvoff.spec"
SAIDA = PROJETO / "dist" / "ChessVisionOFF"

PASTAS_DO_USUARIO = ("data", "models", "PDF", "PGN")
"""Nascem vazias ao lado do `.exe`. São do usuário, e por isso não vão dentro do bundle."""

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

    mb = tamanho_em_mb(SAIDA)
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
