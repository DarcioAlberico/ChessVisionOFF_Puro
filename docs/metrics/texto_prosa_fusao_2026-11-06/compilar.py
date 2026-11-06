"""Compila `docs/metrics/texto_prosa_fusao_2026-11-06.json` (S-721, S-729, S-743) a partir dos JSONL, que ficam fora do repositório.

    compilar.py <pasta dos JSONL> <saida.json>

Como os JSONL nasceram, com OMP_NUM_THREADS=3, QT_QPA_PLATFORM=offscreen, CVOFF_RAIZ no checkout com PDF/ e PYTHONPATH=<worktree>/src, em
pedaços abaixo de três minutos, pelo mesmo --dados:

    texto_prosa --conjunto ouro --split dev --motor glifo,camada_prosa,fusao,tess,tess_oraculo --dados dev_a.jsonl --limite-segundos 150
    texto_prosa --conjunto prata --motor glifo,fusao,tess,tess_oraculo --dados prata_a.jsonl --limite-segundos 150
    texto_prosa --conjunto ouro --split dev --motor glifo,fusao --dados dev_b.jsonl        (a segunda corrida: texto igual folha a folha)
    digitos.py livro Bachmann deu dig_bachmann.json; digitos.py livro Neumann fra dig_neumann.json; digitos.py prata dig_prata.json
    legalidade.py ouro fens_ouro.jsonl leg_ouro.json; legalidade.py prata fens_prata.jsonl leg_prata.json
    alternativas.py prata; alternativas.py ouro                                            (os números estão escritos abaixo)

As FEN vêm do classificador de peças de produção, por `OcrService.recognize_page`, gravadas por folha. A ablação (`ablacao.json`) é cada
constante de `fusao.py`, `leitor.py`, `arbitro.py` e `tesseract.py` trocada por vez, relendo as mesmas leituras em cache: ver a chave `ablacao`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ALTERNATIVAS = {
    "o_que_e": "lstm_choice_mode=2, que só sai no hOCR: palavra com forma de lance que a gramática não aceita, em linha de notação",
    "prata": {"folhas": 27, "invalidas": 619, "resolvidas_pelo_mapa": 78, "resolvidas_so_pelas_alternativas": 240, "das_quais_trocam_um_digito": 16},
    "ouro_dev": {"folhas": 27, "invalidas": 325, "resolvidas_pelo_mapa": 11, "resolvidas_so_pelas_alternativas": 141, "das_quais_trocam_um_digito": 6},
    "leitura": "as outras alternativas trocam a letra de peça (Hb4 por Bb4 ou Kb4), que é a figurina do glifo. Pagar um processo a mais por folha por 0,6 dígito não entra.",
}

RUSSO = {
    "livro": "Пилавов, 8 folhas espaçadas, a mesma amostra lida com rus e com rus+eng",
    "leitura": "só com rus a notação em letra sai cirílica (№х45, Вхд5); com eng ao lado sai Nxd5, Bxd5. Conferido à mão nas linhas: não há ouro nem prata em russo.",
}

REPLAY = {
    "o_que_e": "juiz sem a gramática do árbitro: da posição inicial, a partir de um número 1, quantos lances longos fecham legais",
    "neumann": {"sem_arbitro": [20, 30], "com_arbitro": [33, 47]},
    "bachmann": {"sem_arbitro": [2, 2], "com_arbitro": [3, 3]},
    "leitura": "o Bachmann das folhas sorteadas quase não tem começo de partida: o número é pequeno demais para dizer alguma coisa.",
}

RESSALVAS = [
    "ouro_dev é dev contaminado, e os dois limiares do árbitro e as regras da S-721 foram escritos olhando estas folhas. O split teste não foi aberto: a fusão no teste é do G102.",
    "prata só ordena: a referência é OCR de terceiro, que também lê Tfl por Tf1. É por isso que dígito forçado aparece como erro de prosa ali: a coluna delta da ablação mostra o árbitro custando +0,07 p.p. de prosa na prata admitida, e a contagem de casas válidas mostra o que ele acerta.",
    "Tempo sob contenção (duas outras medições na máquina): os segundos_* não julgam o G4.",
    "O commit em codigo é o que leu as folhas. Depois dele só mudaram scripts desta pasta e a documentação.",
    "A ablação relê as leituras do glifo, do detector e do Tesseract de um cache em disco, do mesmo commit: a coluna é a diferença de regra, e nenhuma leitura se repete. O número de cada motor sai dos JSONL sem cache.",
]


def _ler(caminho: Path) -> object:
    return json.loads(caminho.read_text(encoding="utf-8"))


def main() -> int:
    pasta, saida = Path(sys.argv[1]), Path(sys.argv[2])
    comando = [
        sys.executable, "-m", "chess_diagram_ocr.cli.texto_prosa", "--compilar", str(saida), "--medido-em", "2026-11-06",
        "--item", "S-721, S-729, S-743: a fusão por token por estrato, o árbitro de notação e o dígito de estilo antigo",
        "--bloco", f"ouro_dev={pasta / 'dev_a.jsonl'}",
        "--bloco", f"ouro_dev_misto={pasta / 'dev_a.jsonl'}?estrato=misto",
        "--bloco", f"prata={pasta / 'prata_a.jsonl'}",
        "--bloco", f"prata_admitida={pasta / 'prata_a.jsonl'}?oraculo_max=0.10",
    ]
    for ressalva in RESSALVAS:
        comando += ["--ressalva", ressalva]
    subprocess.run(comando, check=True)
    relatorio = json.loads(saida.read_text(encoding="utf-8"))
    relatorio["pergunta"] = "Com a regra por estrato e o árbitro, a fusão fica sem perder da prosa do Tesseract puro e sem perder notação do glifo?"
    relatorio["legalidade_g1c"] = {"ouro_dev": _ler(pasta / "leg_ouro.json"), "prata": _ler(pasta / "leg_prata.json")}
    relatorio["digitos"] = {"bachmann": _ler(pasta / "dig_bachmann.json"), "neumann": _ler(pasta / "dig_neumann.json"), "prata": _ler(pasta / "dig_prata.json")}
    relatorio["alternativas_do_tesseract"] = ALTERNATIVAS
    relatorio["russo"] = RUSSO
    relatorio["replay_da_posicao_inicial"] = REPLAY
    relatorio["ablacao"] = _ler(pasta / "ablacao.json")
    saida.write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
