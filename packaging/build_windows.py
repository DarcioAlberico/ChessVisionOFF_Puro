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
import re
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


def _extras_declarados() -> dict[str, list[str]]:
    """Cada extra de `[project.optional-dependencies]` e os nomes de distribuicao que ele pede.

    Leitor de vinte linhas em vez de `tomllib`, pelo mesmo motivo de `tests/test_docs.py` e de
    `text_status._extras_do_pyproject`: `tomllib` e 3.11+ e a faixa de `requires-python` comeca
    no 3.10 (S-436). E o terceiro parser de TOML escrito a mao neste repositorio -- quando o
    piso da faixa subir, os tres viram um `tomllib` so.
    """
    texto = (PROJETO / "pyproject.toml").read_text(encoding="utf-8")
    extras: dict[str, list[str]] = {}
    dentro = False
    atual: str | None = None
    for linha in texto.splitlines():
        despida = linha.strip()
        if despida.startswith("[") and despida.endswith("]") and "=" not in despida:
            dentro = despida == "[project.optional-dependencies]"
            atual = None
            continue
        if not dentro or despida.startswith("#"):
            continue
        abertura = re.match(r"([A-Za-z0-9_-]+)\s*=\s*\[", despida)
        if abertura:
            atual = abertura.group(1)
            extras[atual] = []
            continue
        if atual is None:
            continue
        if despida.startswith("]"):
            atual = None
            continue
        pedido = re.match(r'"([A-Za-z0-9._-]+)', despida)
        if pedido:
            extras[atual].append(pedido.group(1))
    return extras


def extras_instalados() -> list[str]:
    """Quais extras estao de fato no ambiente que esta gerando este bundle.

    **O numero do bundle e funcao da venv, e nao so do commit** -- e era isso que faltava
    registrar (S-438). O PyInstaller coleta o que esta *instalado*, nao o que o `pyproject.toml`
    declara, e o proprio README conta essa historia: `pythonnet` e `clr_loader` continuaram
    dentro do bundle muito depois de a S-69 remover o codigo que os usava. Consequencia direta:
    o mesmo commit gera 684 MB numa venv com `onnx`+`ocr` e 570 MB numa com so `dev`+
    `packaging`. Sem este campo, os dois numeros parecem uma regressao de 114 MB em vez de duas
    configuracoes.
    """
    from importlib.metadata import PackageNotFoundError, distribution

    presentes: list[str] = []
    for extra, pedidos in sorted(_extras_declarados().items()):
        if not pedidos:
            continue
        for nome in pedidos:
            try:
                distribution(nome)
            except PackageNotFoundError:
                break
        else:
            presentes.append(extra)
    return presentes


def conferir_o_readme(mb: int, arquivos: int, extras: list[str]) -> None:
    """Avisa, com o conserto na mao, quando o build acabou de envelhecer o README.

    **O laco nao fechava.** O build sobrescreve `docs/metrics/bundle.json`, e
    `tests/test_docs.py` compara esse arquivo com o numero que o README publica -- entao rodar o
    comando que o proprio README manda rodar deixava a arvore suja e a suite vermelha, com um
    `AssertionError: (570, 4039) != (684, 4275)` que nao diz o que fazer. Quem mede e quem sabe
    o numero novo; dizer a frase aqui custa dez linhas.
    """
    readme = PROJETO / "README.md"
    try:
        texto = readme.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - README ilegivel nao e problema do build
        return
    achado = re.search(r"\*\*([\d.]+) MB, ([\d.]+) arquivos\*\*", texto)
    if achado is None:  # pragma: no cover - o teste de docs cobre a ausencia
        return
    citado_mb = int(achado.group(1).replace(".", ""))
    citado_arquivos = int(achado.group(2).replace(".", ""))
    if (citado_mb, citado_arquivos) == (mb, arquivos):
        return
    logger.warning(
        "O README publica %d MB, %d arquivos e este build deu %d MB, %d arquivos. "
        "Atualize a frase de README.md e diga os extras (este bundle saiu com: %s). "
        "Sem isso, `tests/test_docs.py` reprova -- e com razao.",
        citado_mb,
        citado_arquivos,
        mb,
        arquivos,
        ", ".join(extras) or "nenhum",
    )


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

    **`extras` vai junto desde a S-438, e é o que faltava para o número ser comparável.** O
    commit dizia de que *código* o bundle saiu, e não de que *ambiente* -- e o ambiente é metade
    da resposta, porque o PyInstaller coleta o que está instalado. Dois builds do mesmo commit
    mediram 684 MB e 570 MB, e a diferença inteira eram os extras `onnx` e `ocr` presentes numa
    venv e ausentes na outra. Sem o campo, isso se lê como 114 MB de regressão.
    """
    arquivos = [f for f in SAIDA.rglob("*") if f.is_file()]
    mb = round(tamanho_em_mb(SAIDA))
    extras = extras_instalados()
    metricas: dict[str, object] = {
        "mb": mb,
        "arquivos": len(arquivos),
        "extras": extras,
        "data": date.today().isoformat(),
        "commit": _commit_atual(),
    }
    destino = PROJETO / "docs" / "metrics" / "bundle.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(metricas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Métricas do bundle em %s: %s", destino.relative_to(PROJETO), metricas)
    conferir_o_readme(mb, len(arquivos), extras)
    return float(mb)


MODELOS_QUE_ACOMPANHAM = (
    ("piece_classifier.pt", "sem ele o bundle abre e não lê diagrama nenhum"),
    # **Os dois do texto, e eles vão juntos (S-388).** O motor `glifo` precisa dos pesos **e**
    # do metadado -- `carregar_classificador` acha o `.pt` ao lado do `char_meta.json` --, e o
    # build copiava só o de peças: no `.exe`, a aba Texto oferecia o motor `glifo` na caixa e
    # ele nunca subia, nem com os pesos postos à mão em `models/`.
    ("char_classifier.pt", "sem ele o motor `glifo` da aba Texto não sobe"),
    ("char_meta.json", "sem ele os pesos de caractere não são carregáveis"),
)
"""O que é copiado para `models/` **ao lado** do executável, e o que falta sem cada um.

Ao lado, e não dentro: um modelo embutido no `.exe` seria o único que o usuário não consegue
trocar depois de um retreino -- é a decisão que o docstring de `cvoff.spec` explica."""


def copiar_checkpoint() -> None:
    """Põe os modelos ao lado do executável, e **diz o que falta** quando falta.

    O aviso nomeia a consequência de cada ausência: um bundle sem `char_meta.json` abre, lê
    diagrama, e a aba Texto oferece um motor que não sobe -- e sem esta linha ninguém saberia
    por quê.
    """
    for nome, consequencia in MODELOS_QUE_ACOMPANHAM:
        origem = PROJETO / "models" / nome
        if not origem.exists():
            logger.warning("Sem %s: %s. Ponha-o em models/ ao lado do executável.", nome, consequencia)
            continue
        destino = SAIDA / "models" / nome
        shutil.copy2(origem, destino)
        logger.info("Modelo incluído: %s (%.1f MB).", nome, destino.stat().st_size / (1024 * 1024))


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
