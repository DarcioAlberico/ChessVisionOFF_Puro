#!/bin/sh
# Compila docs/metrics/texto_prosa_20261106.json (portão G100) a partir dos JSONL, que têm texto de livro e ficam fora do repositório.
# Uso, da raiz do worktree, com PYTHONPATH=src: compilar_g100.sh <pasta dos JSONL> [saida.json]
#
# Como os JSONL nasceram (OMP_NUM_THREADS=3, QT_QPA_PLATFORM=offscreen, CVOFF_RAIZ no checkout com PDF/), em pedaços, com
# --limite-segundos e o mesmo --dados:
#   texto_prosa --conjunto ouro --split dev --dados dev_a.jsonl                       (e dev_b.jsonl, a segunda corrida)
#   texto_prosa --conjunto prata --dados prata_a.jsonl                                (e prata_b.jsonl, a segunda corrida)
#   texto_prosa --conjunto ouro --split dev --degradar medio --dados deg.jsonl
#   texto_prosa --conjunto ouro --split teste --abrir-teste --motor auto,camada_prosa --dados teste.jsonl
#   suite_diagramas.py dev_a.jsonl diag_dev.json; suite_diagramas.py prata_a.jsonl diag_prata.json   (Python do tronco)
#   suite_ler.py dev_a.jsonl suite2_dev.jsonl --diagramas diag_dev.json --pastas ...  (Python da suíte; idem prata)
#   texto_prosa --importar suite=suite2_dev.jsonl --dados dev_a.jsonl --saida dev_a_suite.jsonl     (idem prata)
G="$1"
SAIDA="${2:-docs/metrics/texto_prosa_20261106.json}"
PY="${PY:-python}"
"$PY" -m chess_diagram_ocr.cli.texto_prosa --compilar "$SAIDA" --medido-em 2026-11-06 --pares camada_prosa-auto \
  --bloco "ouro_dev=$G/dev_a_suite.jsonl" \
  --bloco "ouro_teste=$G/teste.jsonl" \
  --bloco "degradado_medio_dev=$G/deg.jsonl" \
  --bloco "prata=$G/prata_a_suite.jsonl" \
  --bloco "prata_admitida=$G/prata_a_suite.jsonl?oraculo_max=0.10" \
  --ressalva "Tempo sob contenção (outras medições na máquina, OMP_NUM_THREADS=3): os segundos_* não julgam o G4, que se mede na janela com a máquina parada." \
  --ressalva "ouro_teste foi aberto uma vez pelo portão G100, só com os motores auto (o padrão de hoje, que é o glifo) e camada_prosa. Nenhuma palavra errada foi lida e nada se decidiu olhando este bloco. Não é a M0 (falta a auditoria visual da saída) nem a M1 (bancada, motor fusao): é a linha de base. O split tem só inglês e português; a terceira língua segue pendente (pendencias do manifesto)." \
  --ressalva "O commit em codigo é o que leu as folhas. O relatório foi compilado depois, num commit que só acrescenta palavras_de_prosa_achadas_em_qualquer_ordem à conta, sem tocar leitor nenhum." \
  --ressalva "ouro_dev são os cinco livros aprovados na auditoria visual da S-702; é dev contaminado." \
  --ressalva "degradado_medio_dev: as mesmas folhas do dev, perfil medio de text/degradacao.py com semente por folha. Sem calibração contra scan real (S-703 pendente, M5 sem número). camada_prosa e tess_oraculo aí usam a camada do PDF, que não degrada: não são medida de robustez do reconhecimento." \
  --ressalva "prata só ordena (referência = OCR de terceiro), e a camada_prosa dela lê como o glifo, porque a admissão recusa esses livros. Nunca somar ao ouro." \
  --ressalva "suite é a Suite_de_Edicao_de_Xadrez (claude/rotulagem-diagramas, 39ab634), o OCR da imagem (OcrService.recognize_image a 300 dpi, com os diagramas da régua pintados de branco; ver suite_ler.py). Sem a máscara ela inventa texto no tabuleiro: 1,27% de CER no ouro_dev, contra 0,36% com ela."
