# -*- mode: python ; coding: utf-8 -*-
"""Bundle Windows do ChessVisionOFF (S-55, reabre a S-36).

Rode pela raiz do projeto:

    uv sync --extra dev --extra packaging
    uv run pyinstaller packaging/cvoff.spec --noconfirm

Sai em `dist/ChessVisionOFF/`. Zipe essa pasta e ela roda numa máquina Windows sem Python.

---------------------------------------------------------------------------------------
POR QUE `--onedir` E NÃO `--onefile`

`--onefile` extrai o bundle inteiro para `%TEMP%` **a cada execução**. Com torch e
torchvision dentro, isso é ~800 MB de descompressão antes de a janela aparecer -- dezenas
de segundos toda vez que o programa abre, e o disco cheio se o antivírus segurar a pasta
temporária. `--onedir` paga a descompressão uma vez, na instalação.

POR QUE O BUNDLE É O PESADO (leitor **e** treinador)

O ciclo que o README chama de fluxo recomendado é *corrigir → salvar → treinar*, e o passo
3 precisa de torch. Um bundle só de leitura seria ~5x menor -- dá para fazer, e o caminho
está descrito abaixo --, mas entregaria um produto em que o botão "Treinar modelo" some.
Como o valor do projeto está em o usuário melhorar o próprio modelo com as próprias
correções, o build padrão leva o treino junto e custa o tamanho.

    O build leve, se um dia fizer sentido: trocar `torch`/`torchvision` por `onnxruntime` e
    o `.onnx` da S-30, remover `training`, `experiments` e os CLIs de treino dos
    `hiddenimports`, e pôr `torch` em `excludes`. A inferência não precisa de torch; o
    treino, sim. É decisão de produto e não de empacotamento, e por isso não é uma flag
    aqui.

O QUE **NÃO** VAI DENTRO, DE PROPÓSITO

- `data/`, `models/`, `PDF/`, `PGN/` -- são do usuário, e ficam **ao lado** do executável.
  `config._project_root()` resolve para a pasta do `.exe` quando `sys.frozen` está posto,
  e é isso que faz reinstalar não apagar 3.313 rótulos de trabalho humano.
- **WebView2** -- não é mais assunto: a aba "Leitura" que o embutia saiu na S-69, e com ela
  `pythonnet` e `pywebview`. O bundle deixou de depender de um runtime do sistema, e o
  visualizador do app não degrada em máquina nenhuma porque não há nada para degradar.
- **Stockfish** (S-33) -- opcional e externo desde sempre; `engine.find_engine` o procura.
- **Streamlit** -- desde a S-54 é demonstração em `examples/`, não interface. Empacotar um
  servidor web dentro de um app de desktop seria empacotar o exemplo.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJETO = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH vem do PyInstaller

# `ttkbootstrap` carrega temas de arquivos de dados, e `chess.svg`/`pymupdf` trazem tabelas
# que o analisador estático não enxerga. Sem isto o bundle abre e falha no primeiro tema.
datas = [
    (str(PROJETO / "assets"), "assets"),
]
datas += collect_data_files("ttkbootstrap")

# `torchvision.models` e os CLIs entram por nome porque nada os importa estaticamente: a
# arquitetura vem do checkpoint (S-27) e os `cvoff-*` são entrypoints declarados no
# pyproject, que o PyInstaller não lê.
hiddenimports = [
    "PIL._tkinter_finder",
    "torchvision.models",
    "torchvision.transforms.v2",
]
hiddenimports += collect_submodules("chess_diagram_ocr")

# O que só serve para desenvolver, medir ou demonstrar. Cada linha aqui é MB que o usuário
# baixa e nunca executa.
excludes = [
    "streamlit",
    "altair",
    # `pyarrow` vem junto do `streamlit`, e sozinho ele e a maior parte dos 115,4 MiB (16,6%
    # do bundle) que a S-137 mediu -- para um exemplo que a S-54 aposentou. Ele saiu das
    # dependencias obrigatorias no mesmo item; ficar aqui tambem e cinto e suspensorio,
    # porque quem instalar o extra `demo` e gerar o .zip nao deve empacota-lo por acidente.
    "pyarrow",
    # O `onnx` e um backend **alternativo** de inferencia (S-30), opcional de proposito: o
    # pipeline empacotado usa `torch`, e quem tem os dois no ambiente levaria os dois.
    "onnx",
    "onnxruntime",
    "pytest",
    "mypy",
    "ruff",
    "IPython",
    "notebook",
    "matplotlib",
    "tensorboard",
]

a = Analysis(  # noqa: F821
    [str(PROJETO / "app_tkinter.py")],
    pathex=[str(PROJETO / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ChessVisionOFF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # UPX desligado: ele comprime as DLLs do torch e alguns antivírus tratam binário
    # empacotado por UPX como suspeito. Trocar minutos de download por um falso positivo
    # de antivírus não vale.
    console=False,
    # Sem console: é um app de janela. O log vai para `logs/chessvisionoff.log`, ao lado deste
    # executável, e é lá que se olha quando algo falha -- inclusive quando a janela nem abre.
    #
    # Esta frase já esteve aqui sem ser verdade (S-127): `default_log_file()` devolvia `None`
    # sem `CVOFF_LOG_DIR`, e nada no bundle a definia. Um `.exe` que não abria não deixava
    # rastro nenhum, que é exatamente o modo de falha que desligar o console cria.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ChessVisionOFF",
)
