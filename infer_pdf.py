#!/usr/bin/env python
"""Invocador fino mantido por compatibilidade. Equivalente ao comando `cvoff-infer`."""

from __future__ import annotations

from chess_diagram_ocr.cli.infer import main

if __name__ == "__main__":
    raise SystemExit(main())
