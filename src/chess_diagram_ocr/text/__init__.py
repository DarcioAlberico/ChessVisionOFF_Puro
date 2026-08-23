"""Reconhecimento de texto da página (Fases 25 a 31, S-178 a S-216).

O que este subpacote é, em uma frase: **o classificador de glifo do `PyBoxEditor_Tkinter`,
portado com procedência, atrás das fronteiras que este projeto já tem.**

De onde veio cada arquivo, de qual commit, e o que foi mudado no porte: `PROCEDENCIA.md`, ao
lado deste. O plano inteiro está em `docs/ROADMAP_TEXTO.md` e `docs/SPEC_TEXTO.md`, e
`cvoff-texto-status` diz o que dele já existe no disco.

**Nada é importado no topo aqui, e é regra e não descuido.** `text.modelo` puxa `torch`,
`text.recognizer` puxa `cv2`, e importar `chess_diagram_ocr.text` não pode custar nenhum dos
dois: quem só quer perguntar se o subpacote existe -- o verificador de status, a interface ao
montar um menu, um teste de contrato em clone limpo -- não deve pagar o carregamento de um
framework. É a mesma razão do import tardio de `ocr_caption` em `cli/_ocr.py`.
"""

from __future__ import annotations

__all__: list[str] = []
