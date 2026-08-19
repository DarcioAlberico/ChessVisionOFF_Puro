# Roadmap — Fases 7 a 13

Continuação de [ROADMAP.md](ROADMAP.md), que fecha na Fase 6. Especificação detalhada em
[SPEC_FASE7.md](SPEC_FASE7.md) (S-37 a S-75). Para o *como* de hoje,
[ARCHITECTURE.md](ARCHITECTURE.md); para os números de referência,
[BASELINE.md](BASELINE.md);
para o que foi medido nesta fase — **inclusive o que não entrou** —
[EXPERIMENTS_FASE7.md](EXPERIMENTS_FASE7.md).

**Data da análise:** 2026-08-09 · **Ramo:** `fase-5-modelo-desempenho` · **Commit base:** `ee308dd`

> **As Fases 14 a 19 estão em [ROADMAP_FASE14.md](ROADMAP_FASE14.md)** (avaliação de
> 2026-08-16), especificadas em [SPEC_FASE14.md](SPEC_FASE14.md) (S-95 a S-142).
>
> **Elas alcançam este documento em dois pontos, e vale ler antes de usá-lo como referência.**
> A 7.7 concluiu que a taxa de exportação é *"uma catraca que só desce"* e atribuiu isso à
> distribuição bimodal da confiança. A explicação está um nível abaixo: **uma métrica de
> confiança não pode medir correção**, e o conjunto de campo tem 1 FEN de referência em 39
> diagramas — que é uma alucinação do próprio modelo sobre uma capa (S-95). Além disso, **três
> diagramas impressos cruzam split, um deles nas três partições** (S-98), e **17,9% do conjunto
> de campo está em páginas de que já há amostra rotulada em `train`** — o que ainda não
> contamina o checkpoint atual, mas contamina o próximo retreino (S-97).
>
> Consequência para a leitura desta fase: os vereditos de **S-38b, S-40, S-62a e S-62b** não
> estão errados — estão **não tomados**.

---

## Como esta análise foi feita, e o que ela mede

O projeto tem 0,9906 de acurácia exata por tabuleiro no split de teste. Esse número é
honesto: o modelo nunca viu aquelas 320 amostras, o split é estável e agrupado, e o
BASELINE.md descreve corretamente o intervalo de confiança. O problema é outro — **ele
mede uma coisa que não é o produto.**

As 320 amostras de teste são recortes de `data/samples/`: tabuleiros que **um humano já
aprovou**, salvos pelo próprio fluxo de correção. O produto não lê recortes aprovados. Ele
lê páginas de PDF. Então esta análise fez a medição que faltava: rodar `OcrService.
recognize_page` sobre páginas reais, com o checkpoint de produção
(`models/piece_classifier.pt`), em 8 livros do acervo, 5 páginas de cada.

| livro | diagramas | conf. mín. média | abaixo do gate (0,80) | fatalmente ilegais | orientação incerta |
|---|---|---|---|---|---|
| Polgar 5334 (tabuleiro em fonte) | 24 | **1,000** | 0 | 0 | 0 |
| Schiller (scan limpo) | 18 | 0,927 | 2 | 0 | 0 |
| Reinfeld ES (scan puro) | 17 | 0,922 | 1 | 0 | 1 |
| Aagaard Endgame (vetorial) | 14 | 0,893 | 2 | 0 | 2 |
| Karpov 1 (vetorial) | 18 | 0,846 | 3 | **3** | 2 |
| Kemeri (scan alemão) | 2 | 0,795 | 1 | 0 | 0 |
| Gallagher (scan puro) | 6 | **0,262** | 6 | 0 | 2 |
| Euwe Band 1-2 (scan hachurado) | 2 | **0,000** | 2 | 0 | 0 |
| **total** | **101** | — | **17** | **3** | **7** |

**Este levantamento foi a estimativa; o conjunto de campo da S-41 o substituiu.** A tabela
acima conta só os diagramas que o detector achou, e por isso é otimista. O número atual, sobre
15 páginas anotadas à mão, está em `docs/metrics/field_20260809.json` e se reproduz com
`cvoff-field`: **taxa de exportação 0,6842 (26 de 38)**.

**O número que reorganiza o roadmap:** o gate de exportação rejeita **17 de 101** diagramas
de página real (16,8%) contra **3 de 320** no split de teste (0,94%). É um fator de **18×**.
Não é o modelo que está ruim — é o conjunto de teste que não representa a entrada.

Isso muda a ordem das prioridades de forma direta. Melhorar o classificador rende centésimos
num número que já está no teto e que não descreve o campo. As três coisas que rendem estão
todas **antes ou fora** do classificador: o que chega até ele, como chega, e o que a página
diz em texto.

---

## Fase 7.0 — Fora de fase: seis defeitos que a segunda análise encontrou ✅ concluída (2026-08-09)

Estes não eram melhorias. Eram coisas quebradas, e três delas anulavam garantias que a
documentação afirmava. Vieram antes de qualquer item novo.

| # | defeito | efeito medido | item | estado |
|---|---|---|---|---|
| 1 | `ensure_splits` nunca é chamada em produção | **45 amostras invisíveis ao treino**, em silêncio | S-56 | ✅ |
| 2 | as três verificações não rodam neste diretório | 33 módulos de teste não coletam; `mypy` não roda | S-37 | ✅ |
| 3 | o lock do modelo não cobre exportação nem varredura | a corrida que a S-31 diz ter fechado continuava aberta em 2 dos 3 caminhos | S-57 | ✅ |
| 4 | `save_checkpoint` não passa pelo `atomic_io` | treino interrompido podia deixar `.pt` corrompido | S-57 | ✅ |
| 5 | `source_page`/`source_diagram` viram `float` no round-trip | `20` virava `20.0`, e o arquivo tinha os dois formatos | S-58 | ✅ |
| 6 | fechar a janela durante treino/exportação descarta em silêncio | até ~9 min por época de CPU perdidos sem aviso | S-60 | ✅ |
| — | o consentimento da S-32 não sobrevive a um redirect | a imagem podia sair para um host nunca aprovado | S-59 | ✅ |

**O que a implementação mediu.** A suíte foi de 611 para **655 testes** (mais 501 subtestes),
`ruff` e `mypy` limpos, e o roteiro headless do CONTRIBUTING monta a janela, reconhece a
página 80 do Karpov 1 e navega entre os 6 diagramas.

Três coisas que só apareceram ao escrever o código:

- **A calibração supunha que sempre existe um checkpoint.** Cancelar antes da primeira época
  deixava `train_model` lendo um `.pt` que nunca foi escrito. A suposição era invisível
  enquanto o treino não podia ser interrompido antes de gravar o primeiro.
- **Os testes de rede passaram a sair para a rede.** Eles substituíam
  `urllib.request.urlopen`; com o envio indo pelo *opener* próprio da S-59, o mock deixou de
  interceptar e três testes tentaram resolver `exemplo.invalido` de verdade. Falharam por
  sorte — num ambiente com DNS curinga teriam **passado**. Virou teste.
- **O `--extra onnx` sumiu no `uv sync`.** Ressincronizar com `--extra dev` apenas desinstala
  o que o outro extra trouxe. Restaurado; o comando certo aqui é
  `uv sync --extra dev --extra onnx`.

**O que ficou de fora, de propósito.** A matriz de CI em Linux que a S-37 sugere:
`tests/test_shortcuts.py` importa `tkinter` no topo e cria widgets, então um job `ubuntu`
precisaria de `xvfb` ou de `skipIf`. Entregar um job que falha é pior que não entregar, e
isso é trabalho separado.

**O que precisa da sua decisão.** `data/splits.csv` **não** foi alterado: o próximo
`cvoff-train` atribui os 46 splits que faltam, e 4 deles caem no `test` — que por desenho da
S-07 é irreversível. O ensaio a seco (sobre cópias) confirmou 37 train / 5 val / 4 test em
0,87 s, com **zero** amostras antigas movidas. O `data/labels.csv` também não foi tocado; ele
converge sozinho para `20` na próxima gravação.

### 7.0.1 — A amostra que você salva não chega ao treino

O defeito mais caro do levantamento, e o mais silencioso.

`splits.ensure_splits` existe, está correta, tem teste, e o docstring dela diz exatamente o
que ela faz: *"Carrega os splits existentes e atribui split apenas às amostras novas."*
**Nenhum código de produção a chama.** Verificado por varredura: todos os consumidores —
`training.train_model:391`, `cli/evaluate.py:176`, `cli/experiment.py:41`,
`cli/export_onnx.py:87`, `dataset_browser.py:111` — chamam `load_splits`, que só lê.

O que isso produz, passo a passo:

1. O usuário corrige um diagrama e salva → `append_training_sample` grava a linha no
   `labels.csv`. **Nenhum split é atribuído.**
2. O usuário clica "Treinar modelo" → `train_model(splits_path=data/splits.csv)` →
   `load_splits` → a amostra nova não está no mapa.
3. `BoardFenDataset._load_entries:168` faz `if self.splits.get(filename) != self.split:
   continue`. Como `None != "train"`, a amostra é **descartada**.

Medido agora:

```
splits.csv      : train 2.569 · val 306 · test 320   = 3.195
labels.csv      : 3.240 rótulos utilizáveis
                                                       -------
amostras invisíveis ao treino por falta de split:          45
```

E as 45 não são amostras quaisquer: são **as únicas 46 com procedência preenchida** (menos
uma cuja imagem sumiu). São as mais recentes, salvas depois da S-31, com `source_pdf`,
`source_page` e `detection_source` — exatamente as que mais custaram trabalho.

O descarte é mudo em três níveis. `_load_entries` avisa sobre imagem ausente e sobre rótulo
ilegal, e **não** avisa sobre este caso. O log do treino diz *"Split persistido em uso: 2.569
tabuleiros de treino"* — um número que já as exclui. E a aba Dataset as mostra normalmente,
porque `dataset_browser` não filtra por split.

A intenção do código está certa e o docstring a explica: *"Amostras sem split registrado são
ignoradas, para que uma amostra nova nunca entre por acidente no conjunto de teste."* Só que
sem ninguém atribuindo o split, "nunca entra por acidente" virou "nunca entra".

Isto anula o ciclo que o README chama de fluxo recomendado — *"5. Salvar exemplos corrigidos.
6. Treinar modelo. 7. Repetir ciclo para reduzir correções manuais."* O passo 6 não vê o
passo 5. → **S-56**.

### 7.0.2 — As três verificações não rodam neste diretório

O projeto foi movido de `C:\PythonChess\ChessVisionOFF_Puro`
para `C:\Python-Chess2\ChessVisionOFF_Puro`, e o `.venv` não foi ressincronizado:

```
.venv/Lib/site-packages/__editable__.chessvisionoff_puro-0.1.0.pth
  → C:\PythonChess\ChessVisionOFF_Puro\src      (diretório que não existe mais)
```

Consequência medida:

| verificação | estado |
|---|---|
| `pytest` | **33 módulos não coletam** — `ModuleNotFoundError: No module named 'chess_diagram_ocr'` |
| `mypy` | **não roda** — `uv trampoline failed to canonicalize script path` |
| `ruff` | passa (não importa o pacote) |

Com `PYTHONPATH=src`, **611 testes e 498 subtestes passam em 33 s**. O código está inteiro;
o que quebrou foi o ponteiro do ambiente.

O que interessa não é o `uv sync` que conserta isso em 30 segundos. É que **nada no
repositório notou.** A suíte inteira depende de o pacote estar instalado em modo editável, e
não há `tests/conftest.py` nem `pythonpath` na configuração do pytest. Um clone movido, um
`.venv` copiado, um checkout num caminho diferente — os três desligam 611 testes em silêncio,
e o sintoma (`ModuleNotFoundError` em 33 arquivos) parece um problema muito maior do que é.

O CI não pega porque roda `uv sync --frozen` num runner limpo, sempre no mesmo caminho.

→ **S-37**.

### 7.0.3 — O lock do modelo cobre um caminho dos três

O `ARCHITECTURE.md` afirma, na seção Threads:

> O modelo é compartilhado entre elas e fica **sob lock durante o uso**, não só durante a
> carga: o treino reescreve o mesmo `.pt` que um OCR concorrente leria (S-31).

Verificado: vale para **um** dos três caminhos.

| operação longa | thread | como obtém o modelo |
|---|---|---|
| OCR de uma página | `app_tkinter._ocr_worker` | `OcrService.model_session` — **sob lock** ✅ |
| exportação de um livro | `ui/export_controller` → `save_pdf_positions_to_pgn` → `pdf_to_pgn.iter_pdf_diagrams:410` | `load_model()` direto — **sem lock** ❌ |
| varredura da fila | `ui/review_panel` → `build_review_queue` → o mesmo `iter_pdf_diagrams:410` | `load_model()` direto — **sem lock** ❌ |
| treino | `ui/training_dialog` | reescreve o `.pt` ❌ |

E o outro lado da corrida: `checkpoint.save_checkpoint:121` faz `torch.save(payload, path)`
direto no destino. O módulo `atomic_io` existe exatamente para isso e o docstring dele lista
os três arquivos que protege — estado da app, fila de revisão e `labels.csv`. **O checkpoint
não está na lista.**

A corrida concreta: o treino termina uma época que melhorou e chama `save_checkpoint`, que
trunca e reescreve 8,7 MB; a thread de exportação, no meio de um livro de 1.121 páginas,
está em `load_model` → `torch.load` no mesmo arquivo. A janela é pequena, mas o treino grava
uma vez por época que melhora e a exportação roda por dezenas de minutos.

Ironia útil: o caminho **rápido** (OCR de uma página, ~2 s) é o protegido; os **longos** —
exportação e varredura, que são os que de fato coexistem com um treino — não são. → **S-57**.

### 7.0.4 — O `labels.csv` tem dois formatos para a mesma coluna

O diff atual do arquivo mostra o sintoma:

```diff
-board_20260726_094154_249679.png,...,A Matter of Endgame Technique.pdf,20,1,contour,...
+board_20260726_094154_249679.png,...,A Matter of Endgame Technique.pdf,20.0,1.0,contour,...
```

`append_training_sample` grava `str(source_page)` de um `int` — sai `20`. Na gravação
seguinte, `_write_labels` faz `pd.read_csv` do arquivo inteiro; como a coluna tem células
vazias (98,6% delas), o pandas a tipa como `float64`, e `20` volta como `20.0`.

Três consequências:

1. **O arquivo tem os dois formatos misturados.** No estado atual, a última linha traz `8,6`
   e as anteriores `8.0,6.0`.
2. **Toda gravação suja linhas alheias.** O diff de hoje tem 7 inserções e 1 remoção, e a
   remoção é uma linha antiga que só mudou de `20` para `20.0`. Num arquivo que é 3.241
   rótulos de trabalho humano, ruído de diff esconde mudança real.
3. **`DatasetEntry.source_page` é a string `"20.0"`.** A aba Dataset mostra `20.0`, e
   qualquer comparação com um número de página falha. A recuperação de procedência da S-52
   teria de normalizar isso antes de casar qualquer coisa.

→ **S-58**.

### 7.0.5 — Dois detalhes menores, medidos

**O consentimento da S-32 não sobrevive a um redirect.** `predict_fen_via_net:161` usa
`urllib.request.urlopen`, que segue redirects por padrão. A S-32 promete que o aviso "nomeia
o host de destino" e que o consentimento fica gravado **por endereço**. Um `302` manda a
imagem para um host que o usuário nunca aprovou, e nada no log diz que isso aconteceu.
Também não há validação de esquema: `HttpFenProvider` aceita qualquer string, e
`CVOFF_REMOTE_FEN_URL=file:///C:/...` faria `urlopen` ler um arquivo local. Nenhum dos dois
é explorável de fora — o endpoint é declarado pelo usuário — mas os dois enfraquecem a
garantia que a S-32 existe para dar. → **S-59**.

**Retomar uma exportação depois de treinar mistura dois modelos.** `export_checkpoint`
guarda `ScanParams.model_path` para decidir se um parcial pode continuar, e o docstring do
módulo promete que outro modelo descarta o parcial. Ele compara o **caminho**, não o modelo —
e o treino reescreve sempre o mesmo `models/piece_classifier.pt`. Exportar metade de um
livro, cancelar, treinar, retomar produz um PGN com metade das posições lidas por um modelo e
metade por outro, sem aviso. → parte da **S-57**.

**Fechar a janela durante uma operação longa descarta em silêncio.** `_on_close:390` grava o
estado, destrói o leitor, fecha o motor e chama `root.destroy()`. Não pergunta nada. As oito
threads do app são `daemon=True` e nenhuma é aguardada, então um treino de 9 min por época ou
uma exportação de 1.121 páginas morre no `destroy`. O treino não tem cancelamento (o
`ARCHITECTURE.md` registra isso), então fechar a janela é o único jeito de pará-lo — e é o
jeito que pode corromper o `.pt` da 7.0.3. → **S-60**.

---

## Fase 7 — Ler o acervo que existe, não o que o dataset representa

Objetivo: fechar o fator de 18× entre a medição de laboratório e a de campo. Quatro itens,
nesta ordem, porque cada um depende do anterior para ser medível.

### 7.0.6 — O conjunto de campo, e o que ele corrigiu na primeira medição ✅ (S-41)

Existe agora: **15 páginas anotadas à mão, 38 diagramas, 3 páginas sem diagrama nenhum**,
cobrindo cinco regimes. `data/field_set.jsonl` é versionado (é texto); medir contra ele
precisa dos PDFs, e o teste pula quando eles não estão.

Cada página foi conferida olhando o render com as caixas do rascunho desenhadas em cima. O
rascunho vem de `cvoff-field --draft`, que roda o pipeline e grava o que ele leu com
`reviewed: false` — anotar passa a ser corrigir em vez de digitar, e o campo `reviewed` é o
que impede o atalho de virar trapaça: medir o pipeline contra a própria saída dele daria
recall 1,0 e não significaria nada.

**A linha de base, medida em 2026-08-09:**

| métrica | valor |
|---|---|
| recall de detecção | 0,9211 (35 de 38) |
| precisão de detecção | 0,9722 (35 de 36) |
| **taxa de exportação** | **0,6842 (26 de 38)** |

| regime | exportação |
|---|---|
| tabuleiro em fonte (Polgar) | 1,000 (6/6) |
| vetorial (Karpov, Aagaard) | 0,857 (12/14) |
| scan hachurado (Kemeri, Euwe) | 0,500 (2/4) |
| scan puro (Reinfeld, Gallagher) | 0,429 (6/14) |

**O número honesto é 0,68, não os 0,83 que a análise estimou.** A estimativa anterior contava
só os diagramas que o detector achou; o conjunto de campo conta também os que ele perdeu. É
exatamente a diferença que motivou o item.

#### O que a primeira medição corrigiu na hipótese da S-38

A análise dizia que o falso positivo do `Karpov 1` p80 era o detector escolhendo uma região
que não é tabuleiro. **Está errado, e o conjunto de campo mostrou isso na primeira rodada:**
as 6 caixas daquela página estão todas certas, sobre os 6 diagramas reais.

O que acontece é outra coisa, e é pior. `detection/hybrid.refine_candidate_with_contour` roda
o detector de contorno **dentro** do bbox já correto para alinhar melhor o recorte — e quando
o contorno acha o quad errado, ela substitui um recorte perfeito por um trapézio de texto.
Medido nos 6 candidatos daquela página, `_board_pattern_score` antes e depois do refino:

| candidato | recorte cru | depois do refino | |
|---|---|---|---|
| #0 | 0,3138 | 0,6042 | melhora |
| #1 | 0,2000 | 0,4616 | melhora |
| #2 | 0,3511 | **0,2388** | **piora** |
| #3 | 0,2000 | 0,4271 | melhora |
| #4 | 0,2892 | **0,2252** | **piora — é o lixo de 8 reis brancos** |
| #5 | 0,3306 | 0,5059 | melhora |

O refino ajuda em 4 e atrapalha em 2, e num dos dois o estrago é total: o recorte cru do
candidato #4 é um diagrama impecável, e o refinado é ilegível.

O docstring de `refine_candidate_with_contour` já tem o raciocínio certo — *"devolve o
candidato original quando o contorno não acha nada na região, caso em que o recorte cru é o
melhor que se tem, e não há razão para piorá-lo"*. Ele só confere se achou **alguma coisa**,
nunca se o que achou é **melhor**. A S-38 fica mais barata e mais precisa por causa disso:
comparar o sinal antes e depois, e manter o refino só quando ele não piora.

---

### 7.0.6b — O recorte que trazia o rodapé junto, e três guardas que calaram ✅ (S-64)

**Achado por uso, não por varredura**, e é isso que o torna instrutivo: a pergunta era "por
que os diagramas 420 e 421 da página 81 do `Karpov 1` saem piores que os outros quatro da
mesma página?". Eles saíam a 0,7905 e 0,9385 contra 1,0000 dos vizinhos.

**A resposta não era confiança baixa. Era posição errada.**

A imagem que o PDF embute não é só o tabuleiro: ela inclui a faixa de avaliação (`△`, `+−`)
**abaixo** dele. `split_board_into_cells` divide a imagem em oito filas iguais, e num recorte
de 712 px cujo tabuleiro tem 630 cada fila lida mede 89 px onde a real mede 79. **O desvio
acumula para baixo**: na fila 1 ele já passa de uma casa inteira, a última fila lida cai no
rodapé e sai vazia, e as torres da primeira fila são lidas na segunda.

```
N°420   conf 0,7905 → 1,0000
  antes   2rr2k1/1p1b1p2/8/1p6/4P3/7K/2R2R2/8
  depois  2rr2k1/1p1b1p2/8/1p6/1PBPP1p1/4BP1n/7K/2R2R2

N°421   conf 0,9385 → 1,0000     ← passava pelo gate de exportação
  antes   2bqk1nr/3p1p1p/2n1p1n1/4P3/2P5/PP6/R2Q1RK1/8
  depois  2bqk1nr/3p1p1p/2n1p1p1/rp2P3/2B1PB2/2N5/PP4PP/R2Q1RK1
```

O "depois" foi conferido contra o render, casa por casa.

#### Três guardas deviam ter pego isso, e as três calaram

Vale registrar quais, porque o padrão se repete e nenhuma delas estava quebrada:

| guarda | por que calou |
|---|---|
| **`trim_to_grid`** | procura as 7 linhas internas da grade no perfil de gradiente. Em casa **hachurada** essas linhas não existem: a fronteira clara/escura é textura, não traço |
| **`refine_candidate_with_contour`** | achou um quad **pior**, e a S-38a corretamente o descartou. O que sobrou foi o recorte cru |
| **`board_texture_score`** | 0,3607 no recorte errado contra 0,3897 no certo — **0,03**, e a tolerância da S-38a é 0,02 |

A terceira linha é a que mais importa. O sinal que a S-38a usa para julgar um recorte é
**quase cego ao alinhamento da grade**, que é justamente o que decide se a leitura está
certa. Um recorte deslocado quase uma casa e um recorte perfeito são, para ele, a mesma
coisa. Isso não invalida a S-38a — ela continua pegando o trapézio de texto, que é outra
ordem de erro — mas delimita o que ela pode prometer.

E `trim_to_grid` não falhou por limiar apertado: ela desiste em `_board_span`, **antes** de
avaliar a periodicidade. O passo mediano entre picos de gradiente sai 9 px e 32 px onde a
casa tem 82 e 88 — o que ela acha é a moldura e as bordas das peças. Afrouxar
`min_periodicity` não mudaria nada, e há teste que trava essa premissa.

#### A correção: um segundo aparo, com um sinal que existe nessas imagens

`trim_to_frame` procura a **moldura impressa** — uma linha reta escura que atravessa a imagem
inteira. Contar pixels escuros por linha e por coluna separa isso de qualquer outra coisa com
folga: uma fila cheia de peças pretas chega a ~0,45 de preenchimento, a moldura passa de
0,95. Ela roda **só quando `trim_to_grid` não confiou**, e recusa quando o que sobra dentro
da moldura não é quase quadrado ou não cobre a maior parte da imagem.

**O que mudou, medido em 606 diagramas de 6 livros** (o "antes" é literalmente o
comportamento anterior, com a função desligada):

| livro | diagramas | conf. média | abaixo do gate | FENs corrigidas |
|---|---|---|---|---|
| **Karpov 1** | 173 | 0,9635 → **0,9889** | 14 → **4** | **10** |
| **Kemeri 1937** | 15 | 0,9330 → **0,9661** | 2 → **1** | 0 |
| Karpov 2 | 114 | 0,9493 → 0,9493 | 10 → 10 | 0 |
| Polgar 5334 | 108 | 1,0000 → 1,0000 | 0 → 0 | 0 |
| Aagaard Endgame | 120 | 1,0000 → 1,0000 | 0 → 0 | 0 |
| Reinfeld ES | 76 | 0,8449 → 0,8449 | 21 → 21 | 0 |

**Zero regressão.** Nenhum diagrama piorou em nenhum dos seis livros, e nos quatro que não
têm o defeito nada se moveu — que é o que se quer de uma segunda tentativa condicionada à
falha da primeira.

#### E a métrica primária da Fase 7 se moveu

Contra o conjunto de campo da S-41, mesmo checkpoint, mesmo conjunto:

| | antes (S-43) | depois (S-64) |
|---|---|---|
| recall de detecção | 0,9211 | **0,9211** |
| precisão de detecção | 0,9722 | **0,9722** |
| detectados e legais | 34 | **35** |
| acima do gate | 26 | **28** |
| **taxa de exportação** | **0,6842** | **0,7368** |

| regime | antes | depois |
|---|---|---|
| **vetorial** (Karpov, Aagaard) | 0,857 | **1,000** (14/14) |
| tabuleiro em fonte (Polgar) | 1,000 | 1,000 |
| scan hachurado (Kemeri, Euwe) | 0,500 | 0,500 |
| scan puro (Reinfeld, Gallagher) | 0,429 | 0,429 |

**+0,0526 na taxa de exportação, e a precisão de detecção não se moveu** — que é a condição
que o critério de saída da Fase 7 impõe. É o primeiro item desde a S-38a a mover a métrica
primária, e ele veio de uma pergunta sobre dois diagramas.

O regime vetorial está fechado. O que sobra para os 0,85 é inteiramente scan: 10 dos 10
diagramas que não chegam ao PGN são do `Reinfeld`, `Gallagher` e `Euwe`, e nove deles são
confiança baixa — o problema de domínio que a **S-40** ataca. Números em
`docs/metrics/field_20260809_s64_moldura.json`.

---

### 7.0.7 — O refino do contorno passou a conferir o que entrega ✅ (S-38a)

A metade da S-38 que a medição acima revelou, implementada e medida contra o conjunto de
campo. `refine_candidate_with_contour` compara `board_texture_score` do recorte cru com o do
refinado e fica com o melhor, com tolerância de 0,02 para o ruído de reamostragem.

**Efeito medido, 38 diagramas anotados:**

| | antes | depois |
|---|---|---|
| recall de detecção | 0,9211 | 0,9211 |
| precisão de detecção | 0,9722 | 0,9722 |
| **detectados que produzem posição legal** | **33 de 35** | **35 de 35** |
| acima do gate | 26 | 26 |
| taxa de exportação | 0,6842 | 0,6842 |

**A métrica primária não se moveu, e isso é o resultado.** As duas posições fatalmente
ilegais do `Karpov 1` p80 desapareceram — mas as leituras que as substituíram saem com
confiança 0,664 e 0,467, ainda abaixo do gate de 0,80. O ganho é de **natureza**, não de
quantidade: uma posição ilegal é lixo que polui o `.review.pgn` e pesa `WEIGHT_ILLEGAL` na
fila; uma posição legal a 0,66 é um diagrama legível a uma ou duas casas do certo.

O refino continua acontecendo onde ajuda: em todo o conjunto de campo, apenas **2 refinos
foram descartados**, exatamente os dois previstos, e ambos com o motivo no log.

Isto também é um recado sobre o método. Se a única medida fosse "posições ilegais", este
item pareceria uma vitória (2 → 0). Se fosse só a taxa de exportação, pareceria inútil. São
as duas juntas que dizem a verdade: o problema saiu do recorte e ficou inteiro na leitura.

### 7.0.8 — O que a medição diz para **não** fazer agora

A outra metade da S-38 — o `BoardVerifier` como piso para todo candidato — estava
sequenciada em seguida. **A medição desaconselha.**

Precisão de detecção hoje: **0,9722, um falso positivo em 36**. Um piso de textura tem, no
máximo, esse um para ganhar, e tem 35 verdadeiros para arriscar. O único falso positivo é a
caixa do bloco de texto na página 124 do `Gallagher`, num livro cuja página inteira é um
scan — caso em que o piso teria de ser agressivo justamente onde os diagramas verdadeiros
têm menos textura.

Onde a taxa de exportação de fato se perde, dos 12 diagramas que não chegam ao PGN:

| motivo | quantos |
|---|---|
| detectado, legal, **confiança abaixo de 0,80** | 9 |
| não detectado | 3 |
| detectado mas ilegal | 0 |

**Nove dos doze são confiança.** É o problema de domínio que a 7.2 descreve — casa
hachurada, papel amarelado, granulação — e quem o ataca é a **S-39** (`BoardNormalizer`) e a
**S-40** (aumento dirigido), não um filtro de detecção. O próximo item é a S-39.

O `BoardVerifier` continua especificado e continua certo como arquitetura: hoje nenhum
candidato precisa parecer um tabuleiro para ser lido, e o caminho da imagem embutida não
olha os pixels. Só não é onde está o retorno agora, e implementá-lo antes de medir seria
fazer o que a Fase 5 aprendeu a não fazer.

---

### 7.0.9 — Normalizar o tabuleiro: medido, e **nada entrou ligado** (S-39)

A hipótese da 7.2 abaixo parecia forte, e a medição a desmontou. Os números completos estão
em [EXPERIMENTS_FASE7.md](EXPERIMENTS_FASE7.md); o resumo é curto porque o resultado é.

Dez variantes de normalização no conjunto de campo, uma etapa por vez e em combinação:

| variante | taxa de exportação |
|---|---|
| **nenhuma (base)** | **0,6842** |
| deskew · campo plano · CLAHE — isolados ou juntos | 0,6842, **idênticos** |
| qualquer combinação com supressão de trama | **0,0000** |

**Campo plano e CLAHE não mudam nada, e o motivo é interessante.** Não é que estejam
desligados: medida no tabuleiro do Euwe p25, a diferença média de pixel é 3,67 e 3,00. Eles
alteram a imagem e não alteram a leitura — porque `build_train_transform` já usa
`ColorJitter(brightness=0.3, contrast=0.3)`, e o modelo **já foi treinado a ignorar
exatamente esse tipo de ajuste global**. O aumento genérico que a S-40 chama de insuficiente
já cobre metade do que a S-39 propunha fazer na inferência.

**A trama não é separável da peça por escala.** A hachura do Euwe tem período de ~12,5 px
numa casa de 100 px — a ordem de grandeza do traço da peça. Testado por mediana e por
morfologia, que separam por escala de formas diferentes: o kernel que começa a mover o Euwe
(0,000 → 0,10 no melhor caso, ainda **oito vezes abaixo do gate**) é o mesmo que derruba
`Karpov` e `Polgar` de 1,000 para 0,05–0,79. Não há janela.

**O que fica.** `preprocess.py`, com tudo desligado e a medição no docstring — a mesma
decisão que a Fase 5 tomou com o TTA e com a temperatura calibrada. `estimate_skew` é
correto e barato, devolve 0,0 em todos os 38 diagramas do conjunto, e isso também é
informação: o warp da S-12 não está deixando sobra de rotação.

**O que isto muda no plano.** A S-39 e a S-40 eram um par — tornar a entrada parecida com o
treino, ou tornar o treino parecido com a entrada. A medição elimina a primeira metade.
Sobram duas saídas, e as duas são de **treino**:

1. **S-40, aumento dirigido** — sintetizar hachura e granulação sobre as amostras limpas. O
   `ColorJitter` acabou de provar que o modelo aprende invariância quando o aumento a ensina.
2. **Anotar os livros hachurados** — as 3.289 amostras vêm quase todas dos livros fáceis.
   Meia dúzia de páginas do Euwe e do Gallagher corrigidas à mão põem o domínio no treino sem
   ninguém precisar simulá-lo. Mais barato de acertar, mais caro em tempo seu.

E o erro concreto que qualquer uma das duas precisa consertar tem nome: no Euwe p25 o modelo
lê as três primeiras filas **corretamente** e confunde **bispo branco com peão branco em casa
hachurada**. Não é "o tabuleiro é ilegível" — é uma confusão de classe específica num fundo
específico, e isso é o tipo de coisa que aumento de dados resolve.

---

### 7.1 — O detector aceita candidato que não é tabuleiro, e a arquitetura garante isso

`board_detection._extract_candidate_quads` calcula um `_board_pattern_score` — textura de
xadrez: contraste entre casas de paridade oposta mais periodicidade da grade. É um bom sinal.
Medido nos dois casos extremos:

| recorte | `_board_pattern_score` |
|---|---|
| tabuleiro real, casas hachuradas, papel amarelado (Euwe p25) | **1,0000** |
| coluna de texto corrido lida como tabuleiro (Karpov1 p80) | **0,2252** |

O sinal separa. O que não separa é o uso que se faz dele:

```python
score = geom_score * (0.55 + 0.45 * pattern_score)
```

**Pattern zero preserva 55% da nota.** Um bloco perfeitamente quadrado de texto tira nota de
geometria alta e passa com folga pelo piso `min_score = max(0,06, top × 0,25)`. Foi o que
aconteceu: na página 80 do Karpov 1 uma coluna de prosa virou candidato, foi deformada por
perspectiva num "tabuleiro", e o modelo leu

```
1q1KK1q1/3KK1P1/3PP3/qP2K1Pq/3KKP1P/2n1Kp1q/P1qP3P/K1R2k1K   conf 0,0004
```

oito reis brancos. O gate de exportação (S-15) pega isso — vai para `.review.pgn` como
ilegal. Mas ele consumiu uma vaga de `max_boards`, entrou na numeração `[Diagram "n"]`, e
apareceu no editor como um diagrama a conferir. Os seis diagramas de verdade daquela página
tiraram pattern entre 0,34 e 0,61; o falso positivo tirou 0,22. **Um piso em 0,30 matava o
falso positivo sem tocar em nenhum diagrama real daquela página.**

E há o lado que nem sinal tem: `detection/embedded.candidates_from_embedded_images` filtra
por **tamanho nativo, proporção e cobertura da página** — e nada mais. Nunca olha os pixels.
Uma imagem embutida quadrada de 400×400 que seja uma foto, um logotipo ou um selo entra como
diagrama com `detector_score` de 0,85.

Ou seja: **nenhum candidato, de nenhuma das duas fontes, precisa parecer um tabuleiro para
ser lido como um.** → **S-38** (`BoardVerifier`, um gate único no fim de `detect_diagrams`).

### 7.2 — A casa hachurada derruba a leitura, e o pré-processamento não faz nada a respeito

O caso mais instrutivo do levantamento é o Euwe Band 1-2, página 25:

- o recorte está **perfeito** — grade alinhada, tabuleiro inteiro, sem moldura;
- `_board_pattern_score` = **1,0000**, o detector tem plena razão;
- `min_confidence` = **0,0000**, e a posição sai errada.

O que a imagem tem: casas escuras **hachuradas com linhas diagonais** em vez de cinza sólido,
papel amarelado, granulação de scan de 1956. O que o modelo recebe:

```python
def preprocess_cell_to_tensor(cell_rgb, arch):
    image = cv2.cvtColor(cell_rgb, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(image, (64, 64), interpolation=cv2.INTER_AREA)
    return torch.from_numpy(resized.astype(np.float32) / 255.0).unsqueeze(0)
```

`cvtColor` → `resize` → `/255`. Nenhuma normalização de iluminação, nenhuma equalização,
nenhuma supressão de trama, nenhum tratamento de fundo. A hachura sobrevive ao downsample
como estrutura de alta frequência dentro de cada casa de 64×64, e o classificador — treinado
quase inteiramente em diagramas de casa sólida — vê uma textura que não existe no treino.

O mesmo vale para o `1937 Kemeri`, onde a página tem ainda **transparência do verso** (o
texto do outro lado da folha aparece atrás do diagrama) e uma **marca d'água azul** da
biblioteca digital atravessando a margem.

Dois caminhos, e os dois valem — um torna a entrada mais parecida com o treino, o outro torna
o treino mais parecido com a entrada:

- **S-39 · `BoardNormalizer`** — normalização de iluminação por campo plano (dividir pela
  versão muito borrada), CLAHE, supressão de trama por morfologia direcional, e correção de
  rotação residual pelas linhas da grade. Aplicada uma vez por tabuleiro, antes do corte em
  casas, e **gravada junto com a amostra** para que o treino veja o mesmo domínio.
- **S-40 · Aumento dirigido ao acervo** — o `build_train_transform` de hoje é
  `GaussianBlur + ColorJitter + RandomAffine(2°)`, um conjunto genérico que não contém
  nenhuma das degradações que o acervo tem: hachura diagonal, granulação de scan,
  transparência do verso, papel amarelado, inversão de diagrama, artefato de JPEG, moldura
  cortada. Também não usa espelhamento horizontal, que neste domínio é **rótulo-preservante**
  por casa (um cavalo espelhado continua sendo um cavalo) e dobra o dataset de graça.

### 7.3 — Não existe medida de quantos diagramas a página tem

Toda métrica do projeto é sobre **o que foi encontrado**: `evaluation.py` avalia recortes já
rotulados, `batch.py` reporta taxa de aceite sobre o que a varredura produziu, a fila de
revisão ordena o que entrou nela. Nenhuma responde à pergunta que decide se um livro foi
convertido ou não: **dos diagramas que a página tem, quantos saíram?**

Isso não é hipotético: sem esse número, um ajuste de `_board_pattern_score` que corte 20% dos
falsos positivos e 5% dos verdadeiros parece uma melhora em todos os painéis existentes — a
confiança média sobe, a taxa de ilegais cai — e é uma piora no produto.

Honestidade sobre o que este levantamento **não** achou: em 3 das páginas amostradas que
devolveram zero diagramas (Euwe p62, Karpov1 p261, Kemeri p144), a inspeção visual confirmou
que **a página realmente não tem diagrama** — são página de prosa, página de soluções e
página com fotografia. O detector estava certo nas três. Não há evidência de colapso de
recall; há ausência de instrumento para medi-lo.

→ **S-41** (conjunto de 60 páginas anotadas à mão, e a métrica de recall/precisão por página).

### 7.4 — O critério de saída da Fase 7

Um conjunto de avaliação **de campo**: N páginas reais dos livros difíceis, com os diagramas
anotados à mão. A métrica primária deixa de ser "acurácia exata sobre recortes aprovados" e
passa a ser **diagramas exportáveis por página** — detectado, legal e acima do gate.

**Número de partida (S-41, 2026-08-09): taxa de exportação 0,6842 — 26 de 38 diagramas.**
Alvo da Fase 7: **≥ 0,85**, sem que a precisão de detecção caia abaixo dos 0,9722.

**Onde está hoje: 0,7368 — 28 de 38** (S-64, 2026-08-09), com a precisão de detecção intacta
nos 0,9722. Faltam **5 diagramas** para o alvo.

> **2026-08-11 — a S-40 foi medida e o alvo continua a 5 diagramas.** Seis variantes de
> modelo, todas em 27 ou 28 de 38. A explicação está em 7.7 abaixo, e ela é sobre o
> instrumento antes de ser sobre os modelos.

E eles têm nome. Os 10 que não chegam ao PGN são **todos de scan**: 6 do `Reinfeld`, 2 do
`Gallagher`, 2 do `Euwe`. Nove são confiança abaixo do gate e um é falha de detecção. Os
regimes vetorial e de fonte estão em 1,000 e não têm mais nada a dar.

| regime | exportação | o que falta |
|---|---|---|
| tabuleiro em fonte (Polgar) | **1,000** (6/6) | — |
| vetorial (Karpov, Aagaard) | **1,000** (14/14) | — fechado pela S-64 |
| scan hachurado (Kemeri, Euwe) | 0,500 (2/4) | domínio: hachura e papel |
| scan puro (Reinfeld, Gallagher) | 0,429 (6/14) | domínio: granulação e papel amarelado |

Ou seja: **o que separa a Fase 7 do critério de saída é a S-40**, o aumento dirigido ao
acervo — e ela está implementada e não medida. É a única alavanca restante que o
levantamento aponta.

A estimativa original deste roadmap era 83,2%, e estava otimista pelo motivo que o item
existe para corrigir: ela contava só os diagramas que o detector achou.

### 7.5 — O custo de uma varredura, medido

Perfil de uma página do Karpov 1 (6 diagramas, 220 DPI, CPU):

| etapa | tempo |
|---|---|
| `render_pdf_page` | 0,043 s |
| `detect_diagrams_in_pdf_page` | 0,562 s |
| `contexts_for_pdf_page` | 0,104 s |
| inferência dos 6 diagramas, `orientation="auto"` | **2,237 s** |
| **total** | **~2,95 s/página** |

Extrapolado: ~20 min para os 402 páginas desse livro, ~55 min para o Reinfeld de 1.121, e
**~10 h para o acervo inteiro** (~12 mil páginas). É o número que a S-34 (varredura em lote)
enfrenta na prática, e ele explica por que a retomada da S-24 importa tanto.

Dois desperdícios estruturais aparecem no perfil:

**A orientação automática custa exatamente o dobro.** Medido no mesmo diagrama:
`predict_with_orientation(mode="auto")` = 0,104 s contra `mode="0"` = 0,050 s. Ela roda o
modelo duas vezes, sempre — e a inferência é 76% do tempo de página. **Cerca de metade de
toda varredura é gasta lendo cada diagrama de cabeça para baixo.** Não é desperdício
gratuito: a medição da S-13 mostra que a orientação por diagrama é necessária. Mas há duas
saídas, e as duas ficam mais baratas depois da S-45: as coordenadas resolvem a orientação
sem inferência nenhuma; e as duas orientações podem ir num único lote de 128 casas em vez de
dois de 64.

**Três aberturas do documento por página.** `render_pdf_page`, `detect_diagrams_in_pdf_page`
e `contexts_for_pdf_page` cada uma chama `_open_document`. Numa varredura completa:

| livro | páginas | `fitz.open` | custo total das aberturas |
|---|---|---|---|
| Polgar 5334 | 1.184 | 1,16 ms | 4,1 s |
| Karpov 1 | 402 | 5,25 ms | 6,3 s |
| **Yusupov (todos os volumes)** | **2.612** | **28,80 ms** | **225,7 s** |

Para quase todo o acervo o docstring está certo ao chamar isso de irrelevante. Para o maior
livro são quase 4 minutos de puro parsing de xref, e a diferença é de 50×. → **S-61**.

### 7.6 — As duas ineficiências corrigidas, e o que sobrou de propósito ✅ (S-61, 2026-08-11)

**(a) As duas orientações num único `forward`.** Página 80 do `Karpov 1`, 6 diagramas,
mediana de 5 repetições: **2,1105 s → 1,5937 s**, −24,5% na inferência, que é 76% do tempo de
página. A computação é a mesma; o que sai é o custo fixo de pedir um segundo lote.

Não é a metade que a análise apontou como desperdício, e não deveria ser: essa metade só cai
com o atalho por coordenadas, e a **S-45 foi adiada por medição**. O que sobra é este quarto,
e ele é de graça.

**(b) Uma abertura por varredura.** `OpenPdf` é o empréstimo; as funções por caminho
continuam sendo a porta dos CLIs.

| livro | páginas | por abertura | antes | depois |
|---|---|---|---|---|
| Polgar 5334 | 1.184 | 4,79 ms | 17,0 s | **0,005 s** |
| Karpov 1 | 402 | 17,39 ms | 21,0 s | **0,017 s** |
| **Secrets of Chess Training 1–5** | 1.181 | **40,34 ms** | **143,0 s** | **0,040 s** |

**"Nenhuma mudança de resultado" foi conferido onde importa.** As dez métricas do conjunto de
campo, com o checkpoint de produção, antes e depois: idênticas dígito a dígito. Um teste
sintético sozinho não provaria isso — ali as imagens são zeros, e a fusão de lote não teria
como divergir mesmo se estivesse errada.

**A decisão que o item obrigou a tomar.** O empréstimo **não levanta** quando o arquivo não
abre: devolve a origem intacta e deixa a etapa seguinte falhar. A tentação era validar ali — o
documento está sendo aberto de qualquer jeito. Mas até a S-61 esta abertura não existia, e
levantar aqui trocaria *"não consegui renderizar a página 1"* por um `FileNotFoundError` vindo
de uma camada que quem chamou não sabe que existe. **Uma otimização não deve mudar qual erro o
usuário vê.**

### 7.7 — A S-40 medida, e o que ela revelou sobre a própria métrica ✅ (2026-08-11)

O roadmap dizia que a S-40 era "a única alavanca restante que o levantamento aponta" para os
0,85. Ela foi puxada — duas vezes, a 8 e a 16 épocas — e o ponteiro não se moveu. O que a
medição encontrou no lugar vale mais que o veredito.

#### O veredito

Todas as variantes: `--fresh`, semente 42, mesmo split, mesmo dataset. O controle é o `aug0`
**retreinado**, não o checkpoint de produção — comparar contra produção compararia também os
meses de amostras que entraram desde que ele foi treinado.

| variante | épocas | exportação | casas reparadas | val. exata |
|---|---|---|---|---|
| **`aug0` — controle** | **16** | **0,7368** | **15** | 0,9790 |
| `mhsp` (espelho+hachura+granulação+papel) | 8 | 0,7368 | 17 | 0,9730 |
| **`mhsp`** | **16** | **0,7368** | **9** | **0,9820** |
| `m` (só espelhamento) | 8 | **0,7105** | 15 | 0,9760 |

**Pela letra do critério, a S-40 não entra**: ele pede ganho no conjunto de campo, e a métrica
primária dele não se moveu. E o controle está **convergido, verificado e não suposto**: oito
épocas a mais não superaram a sétima, e o checkpoint no disco não chegou a ser tocado.

O espelhamento sozinho — que a spec chamava de "a duplicação de dataset mais barata
disponível" e "rótulo-preservante por construção" — **piorou** a métrica primária.

#### O achado: o gate é uma catraca que só desce

Por que seis modelos diferentes deram sempre 27 ou 28 de 38? A distribuição da confiança
mínima dos 36 diagramas detectados, com o controle:

| faixa | diagramas |
|---|---|
| ≥ 0,99 | **27** |
| 0,95–0,99 | 0 |
| 0,80–0,95 | 1 |
| **0,60–0,80** | **0** ← a vizinhança do gate está vazia |
| 0,40–0,60 | 2 |
| < 0,40 | 6 |

**A distribuição é bimodal e o gate cai no vale.** O modelo ou tem certeza absoluta (27 de 36
acima de 0,99) ou está perdido; nada está a menos de 0,37 do corte por baixo. Daí a assimetria
que explica todos os números desta fase:

- para **ganhar** um diagrama, uma mudança de modelo precisa levar algo de ≤ 0,43 a ≥ 0,80 —
  quase dobrar;
- para **perder** um, basta derrubar um dos 27 que estavam em 0,99.

Foi o que aconteceu duas vezes — o `m` derrubou o `Kemeri` p187 e a S-62ab derrubou o `Kemeri`
p80 — e **nenhuma das seis variantes ganhou um único diagrama**. A taxa de exportação, neste
ponto de operação, é uma catraca que só clica para baixo, e isso é propriedade do conjunto e
não dos modelos.

#### O que isto recomenda, em ordem

1. **Crescer o conjunto de campo.** A S-41 planejava 60 páginas e entregou 15, com 38
   diagramas. Enquanto não houver diagramas na faixa 0,6–0,8, a taxa de exportação não
   distingue dois modelos — e **quatro** itens desta fase (S-38b, S-40, S-62a, S-62b) foram
   julgados por ela.
2. **Anotar os livros hachurados à mão.** Os 8 barrados estão **todos** abaixo de 0,43: são
   falhas de domínio, não de margem. É o que a S-39 já apontava, e nenhum ajuste de modelo
   treinado nos livros fáceis atravessa 0,37 de distância.
3. **Não mexer no gate.** Baixá-lo para 0,40 traria dois diagramas do `Gallagher` e junto tudo
   o que a S-15 existe para barrar. O vale entre 0,43 e 0,99 é a evidência de que 0,80 está
   num lugar razoável.

#### O candidato que fica no disco

`models/s40_mhsp_16ep.pt` domina o controle em tudo que hoje é mensurável: **40% menos reparo**
do decodificador (9 contra 15), melhor validação (0,9820 contra 0,9790), mesmo custo, mesma
taxa de exportação. O padrão de `AugmentConfig()` **não** foi trocado por causa disso — essa
decisão precisa de um conjunto de campo com poder de resolução, e é o item 1 acima. Mas o
candidato existe, está medido, e é por onde o próximo retreino de produção deve começar.


---

## Fase 8 — OCR de verdade: a informação que 7 livros têm e o projeto não lê

A S-16 construiu um leitor de camada de texto cuidadoso — associação por linha e não por
bloco, agrupamento por coluna, filtro de prosa, número de página corrente. Ele funciona. E
tem um teto que nenhum refinamento de regex atravessa: **7 dos 27 livros não têm camada de
texto nenhuma.**

Levantamento sobre os 27 PDFs, 30 páginas amostradas de cada:

| o que a camada de texto oferece | livros | páginas |
|---|---|---|
| declara o lado a jogar em legenda | 3 | 2.909 |
| tem texto, mas não declara o lado | 17 | 8.898 |
| **não tem camada de texto (scan puro)** | **7** | **2.654** |

Para esses 7 livros, `contexts_for_pdf_page` devolve `DiagramContext()` vazio, sempre. Sem
lado a jogar, sem número de exercício, sem jogadores, sem evento. Todo diagrama sai
`[SideToMoveSource "default"]`.

**Sobre a diferença para o número da S-16.** Os docstrings de `pdf_text.py` e `semantics.py`
dizem "12 não têm camada de texto". Esta medição diz 7, e as duas estão certas com critérios
diferentes: a de agora conta como scan puro só o livro em que ≤20% das 30 páginas amostradas
têm mais de 40 caracteres. Cinco livros ficam no meio — `Gaprindashvili` e `Vishy Anand` têm
texto em 14 de 30 páginas, `400 Quebra-cabeças` e `Yusupov` em 22, `La Combinación` em 26.
São scans com OCR **parcial**, provavelmente do próprio distribuidor.

A diferença importa para o escopo da Fase 8: esses 5 livros não são "resolvidos pela camada
de texto" nem "sem texto" — são um terceiro regime, em que a camada existe e falha em metade
das páginas. Um motor de OCR os cobre **também**, e a S-43 precisa tratar o caso híbrido
(usar a camada onde ela existe, o OCR onde ela falta) em vez de decidir por livro.

### 8.1 — O que está impresso nessas páginas, verificado

Não é especulação. Duas páginas dos livros sem camada de texto, renderizadas e olhadas:

**`Reinfeld_1001_Sacrificios_y_Combinaciones_Brillantes_1977.pdf`, página 40.** Seis
diagramas em grade 2×3. No topo da página, em caixa alta: **`LAS BLANCAS JUEGAN PRIMERO`**.
Sob cada diagrama, o número do exercício: `193`, `194`, `195`, `196`, `197`, `198`.

Duas informações que o projeto quer muito, impressas com clareza, num livro de 320 páginas e
~1.900 exercícios que hoje sai inteiro como "brancas jogam / default" — e onde o palpite
está certo por coincidência nas páginas de brancas e errado em todas as de pretas.

Detalhe que a S-16 precisaria mudar mesmo se houvesse texto: `MARGIN_BAND = 0,07` descarta a
faixa de 7% do topo e do rodapé por completo, como cabeçalho corrente. O
`LAS BLANCAS JUEGAN PRIMERO` mora exatamente nessa faixa. Hoje ele seria jogado fora como
ruído — e é uma **declaração de escopo de página**, não um cabeçalho.

**`GALLAGHER - Winning With the King's Gambit.pdf`, página 80.** Um diagrama na coluna
direita, com dois glifos alinhados à sua esquerda: **`76`** na altura da oitava fila e
**`B`** logo abaixo. É a convenção Batsford/Cadogan: número do diagrama, e `W`/`B` para o
lado a jogar.

`_match_side_symbol` conhece `◻□▫⬜◽⚪` e `◼■▪⬛◾⚫`. Não conhece `W`/`B`. A convenção mais
comum da literatura inglesa de xadrez não está implementada — nem para os livros que **têm**
camada de texto.

### 8.2 — Qual biblioteca de OCR, e por que a resposta não é a óbvia

A pergunta certa não é "qual OCR é melhor". É "que problema de OCR este projeto tem". E ele
tem três, muito diferentes entre si:

| problema | o que é | tamanho |
|---|---|---|
| **A. glifo único posicional** | `W`/`B` ao lado do diagrama; `a`–`h`/`1`–`8` nas bordas | 1 caractere, posição conhecida |
| **B. número em fonte de display** | `193` sob o diagrama, `76` ao lado | 1–4 dígitos, posição conhecida |
| **C. texto livre de legenda** | `Hickl – Yusupov`, `Bremen 1998`, `LAS BLANCAS JUEGAN PRIMERO` | 1–3 linhas |

Só **C** é OCR no sentido usual. **A** e **B** são classificação de imagem com vocabulário
fechado, numa região que o `bbox_pdf` da S-12 já localiza — e o projeto **já tem toda a
maquinaria para isso**: um classificador de recorte pequeno, um laço de treino com split
estável, calibração de temperatura, fila de revisão por aprendizado ativo e um editor para
corrigir rótulo. Um "classificador de glifo de legenda" reaproveita 90% da Fase 5.

Isso importa porque muda a recomendação: **o motor de OCR entra como dependência opcional
para C, e A e B não dependem dele.** O caminho crítico — lado a jogar — não fica refém de
um download de modelo.

Para C, comparadas as opções sob os critérios que este projeto já declarou (funciona
offline, nada sai da máquina, Windows, CPU, instalação por `uv sync`):

| biblioteca | peso instalado | offline no 1º uso | CPU | idiomas do acervo | veredito |
|---|---|---|---|---|---|
| **RapidOCR (onnxruntime)** | ~15 MB de modelos, roda no `onnxruntime` que o extra `onnx` da S-30 **já instala** | sim, modelos vão no wheel | rápido | en · pt · es · de | **recomendado como padrão** |
| EasyOCR | ~100 MB, baixados na 1ª execução | **não** — quebra a promessa de offline do README | detector CRAFT é lento em CPU | 80+ | alternativa suportada, opt-in explícito |
| PaddleOCR | traz PaddlePaddle, ~500 MB | sim, com cache prévio | bom | melhor acurácia em texto denso | não vale o peso aqui |
| Tesseract | binário externo | sim | ok | bom com `--psm 7`/`--psm 10` | opcional, para quem já o tem |
| docTR | traz TF ou torch + pesos | não | ok | bom | redundante |

A recomendação é **RapidOCR como padrão** por um motivo que não é acurácia: ele é o único que
não muda a natureza do projeto. `onnxruntime` já é dependência opcional declarada; os modelos
vêm no pacote; nada baixa nada na primeira execução; e o extra fica em `[project.optional-
dependencies] ocr`, do mesmo jeito que `onnx` e pelo mesmo motivo.

EasyOCR fica suportado atrás da mesma interface — quem quiser trocar troca uma linha de
`settings.json` — mas **não pode ser o padrão** enquanto o README prometer que nada sai da
máquina no uso padrão: baixar 100 MB de modelo na primeira execução é tráfego de rede que o
usuário não pediu.

→ **S-42** (interface `TextRecognizer` + provedores), **S-43** (leitor de faixa de legenda),
**S-44** (glifo `W`/`B` e número, sem OCR), **S-45** (coordenadas → orientação).

### 8.3 — As coordenadas do tabuleiro fecham a pendência da S-13 — **medido: não fecham, e talvez não haja o que fechar**

> **Levantamento de 2026-08-09.** Coordenadas legíveis na camada de texto em **52 de 380
> diagramas (13,7%)**, dos quais **48 são do `Polgar`**, que já lê a 1,000. E dos 49
> conclusivos, **49 apontam ponto de vista das brancas e nenhum das pretas** — a pendência
> que esta seção existe para fechar não apareceu uma vez. O item saiu do sequenciamento.
> Números em [EXPERIMENTS_FASE7.md](EXPERIMENTS_FASE7.md); o texto abaixo é a proposta
> original, mantida porque o raciocínio continua certo para um acervo que tenha o caso.

A S-13 deixou uma pendência nomeada no ROADMAP: **diagrama impresso do ponto de vista das
pretas**. Ali as peças estão desenhadas para cima e o que muda é o mapeamento casa→índice,
não os pixels — girar a imagem estraga a leitura, e nenhum sinal de imagem resolve, porque a
imagem é legítima nas duas interpretações.

Existe um sinal que resolve, e está impresso na maioria dos diagramas de livro moderno: as
**coordenadas nas bordas**. Se a coluna da esquerda lê `8 7 6 5 4 3 2 1` de cima para baixo,
é ponto de vista das brancas; se lê `1 2 3 4 5 6 7 8`, é das pretas. Uma linha de OCR sobre
uma tira de 8 caracteres, ou — melhor — oito classificações de dígito com vocabulário de 8
classes.

Efeito colateral valioso: as coordenadas também dão o **registro exato da grade**. Se o
detector achou os cantos com 3 px de erro, as posições dos oito rótulos dizem onde as linhas
realmente estão, e o warp pode ser corrigido antes de cortar as casas. Fecha o mesmo problema
que a S-12 atacou por outro lado.

Ressalva honesta: nem todo livro imprime coordenadas. Nas páginas que olhei, o Reinfeld não
tem, o Gallagher não tem, o Euwe não tem — o Aagaard e o Karpov têm. O item precisa medir a
cobertura antes de prometer alcance, e a S-45 diz isso em letra.

### 8.3b — O motor de OCR entrou; a medição dele não ✅ código (S-42, S-43)

Implementados em 2026-08-09. Vale separar com clareza o que está pronto do que está provado,
porque neste item as duas coisas não coincidem.

**O que existe.** `ocr.py` com a interface `TextRecognizer` e três provedores — RapidOCR
(padrão), EasyOCR e Tesseract —, atrás de um `build_recognizer` que devolve `None` quando o
recurso está desligado, o motor é desconhecido ou o extra não está instalado. `ocr_caption.py`
lê **a faixa em volta do diagrama**, apaga o interior do tabuleiro antes de o motor ver a
imagem, e devolve a mesma `TextLine` que `page_text_lines` devolve — de forma que todo o
aparato da S-16 continua valendo sem uma linha de mudança. A opção `--ocr` está em
`cvoff-field` e `cvoff-export`, e o extra é `uv sync --extra ocr`.

Duas regras de precedência, escolhidas para que ligar o OCR não possa piorar um livro que já
funciona: o motor **só roda no diagrama cuja vizinhança a camada de texto deixou vazia** (por
diagrama, não por livro — é o que os 5 livros de OCR parcial exigem), e a declaração de
escopo de página só preenche o diagrama que a legenda não respondeu.

**O que está medido.** Com `--ocr off`, o conjunto de campo dá **0,6842 — idêntico**. E das
15 páginas, **0 produzem declaração de escopo pela camada de texto**: o único comportamento
novo que roda sem motor não dispara uma vez aqui. O caminho novo está inerte, como tinha de
estar.

**O que não está medido, e é o critério de aceite principal.** Nenhum motor está instalado
nesta máquina. A página 40 do `Reinfeld` saindo com os 6 diagramas em `WHITE` e os exercícios
193–198 — o alvo do item — continua sem número, e o custo por página com o motor ligado
também. A instrumentação está no log; falta rodar.

**O que isso pede de você.** `uv sync --extra ocr` instala ~15 MB de modelos que vêm no
wheel, sem download na primeira execução — é o motivo de o RapidOCR ser o padrão, e a
promessa do README continua de pé. Mas é uma dependência a mais, e a decisão é sua. Depois
dela, `cvoff-field --ocr rapidocr` responde em um comando se o item entregou o que promete.

**Uma nota de método.** A linha `legal` do conjunto de campo saiu de 35 para 34 entre a
medição da S-38a e esta. Não é desta entrega: `models/piece_classifier.pt` foi reescrito às
07:49 de 2026-08-09, depois da medição das 04:33, e `legal` é função só do campo de peças
lido. Fica registrado porque o `field_20260809_s38a.json` descreve um checkpoint que não está
mais em disco — comparação futura parte do `field_20260809_s43_sem_ocr.json`.

### 8.4 — O critério de saída da Fase 8

Hoje, **3 dos 27 livros** resolvem o lado a jogar por texto e **118 de 3.195 rótulos** por
legalidade; o resto é o padrão "brancas". A Fase 8 fecha quando a procedência
`[SideToMoveSource]` deixa de ser `default` em pelo menos **12 dos 27 livros** — e quando
cada um dos novos casos é rastreável ao trecho que decidiu, como a S-16 já faz com
`side_to_move_evidence`.

---

### 8.5 — O critério de saída, medido — e o defeito que a medição achou ✅ (2026-08-11)

O critério estava escrito desde o início e **não tinha instrumento**. Agora tem:
`cvoff-sides` amostra páginas de cada livro do acervo pelo pipeline que a exportação usa e
conta de onde veio cada `[SideToMoveSource]`. É a mesma lacuna que a S-41 fechou para a
Fase 7, e o mesmo remédio.

#### O motor foi instalado, e o alvo da S-43 não funcionava

`uv pip install rapidocr-onnxruntime` — 14,2 MiB, modelos no wheel, nada baixado na primeira
execução. A promessa do README continua de pé.

E a primeira coisa que a medição mostrou foi que **o critério de aceite principal da S-43
falhava**. O `LAS BLANCAS JUEGAN PRIMERO` da página 40 do `Reinfeld` não chegava a lugar
nenhum, e o motivo é geométrico: `page_scope_declaration` lia a faixa de `MARGIN_BAND`, 7% da
altura, que naquela página são 34,6 pt — a linha do cabeçalho não cabe. O motor recebia a
metade de cima dos glifos e devolvia `TIEAANDDIVEDA` **com 0,71 de confiança**.

**O 0,71 é a lição.** Um motor de OCR não avisa quando recebe meia linha: ele devolve algo com
forma de texto e uma confiança que nenhum limiar razoável barra. O corte de 0,3 da S-42 existe
para descartar adivinhação, e aqui ele não tinha o que fazer — o defeito era do recorte.

`SCOPE_BAND = 0,12` é constante **separada** de `MARGIN_BAND`, e a separação é o item: uma
decide o que **descartar** como cabeçalho corrente, e apertá-la erra para o lado seguro; a
outra é o que o **motor vê**, e apertá-la corta a linha ao meio.

#### O acervo, com e sem motor

32 livros (cresceu dos 27 que a spec cita), 12 páginas por livro, 645 diagramas:

| | sem OCR | com RapidOCR |
|---|---|---|
| **assumido (`default`)** | **566 (87,8%)** | **498 (77,2%)** |
| resolvido por texto ou OCR | 51 | **120** |
| resolvido por legalidade | 28 | 27 |

| critério | sem OCR | com RapidOCR |
|---|---|---|
| livros com procedência ≠ `default` | 17 de 32 | **19 de 32** |
| **dos quais por texto ou OCR** | **10** | **14** |
| livros com a maioria resolvida | 3 | **5** |

**A Fase 8 fecha — e a manchete engana se ficar sozinha.** Os 12 livros do critério já estavam
atingidos **sem** OCR, porque `legality` também não é `default` e ela existe desde a S-17. O
que a Fase 8 entregou é a coluna de texto: **10 → 14 livros**, e 68 diagramas que deixaram de
ser palpite.

Onde eles estão é o que torna o número concreto:

| livro | assumidos antes | depois |
|---|---|---|
| **`Reinfeld_1001_Sacrificios`** | 40 de 41 | **0 de 41** |
| `Gaprindashvili — Imagination in Chess` | 24 de 28 | **5 de 28** |
| `Aagaard — Excelling at Chess Calculation` | 23 de 23 | **15 de 23** |
| `Silman — Complete Book of Chess Strategy` | 9 de 9 | 8 de 9 |

O `Reinfeld` é o item inteiro numa linha: ~1.900 exercícios em 320 páginas, metade deles de
pretas, que até aqui saíam **todos** como `default` = brancas — certo por coincidência em
metade e errado na outra. Os dois últimos são do terceiro regime que a 8.2 identificou, o de
camada de texto **parcial**; nenhum dos dois tinha uma única procedência antes.

**O que a taxa de exportação diz sobre isso: nada, e é o esperado.** Ela continua em 0,7368
com e sem motor, porque conta detecção, legalidade e gate de confiança — o OCR não toca
nenhum dos três. Foi para medir o que ela não vê que o `cvoff-sides` existe.

Custo: **2,0 a 3,4 s por diagrama** cuja vizinhança a camada de texto deixou vazia. É por
diagrama e não por página, e é por isso que a regra de precedência da S-43 — o motor só roda
onde a camada calou — não é economia de estilo.

---

## Fase 9 — O que ainda mora no lugar errado

A Fase 6 fez a decomposição grande: tirou o pipeline das duas telas e o pôs em `service.py`,
quebrou o `app_tkinter.py` de 2.544 linhas em 14 módulos de UI. O resultado é bom e a regra
que o organiza ("o que dá para testar não fica na janela") é a certa.

O que sobrou são cinco concentrações que a Fase 6 não tinha por que atacar, porque não eram
duplicação entre telas — são **objetos grandes demais para o que fazem**.

### 9.1 — Inventário, medido

| onde | tamanho | o que está misturado |
|---|---|---|
| `training.train_model()` | **259 linhas**, 18 parâmetros | montagem de dataset, resolução de split, retomada de checkpoint, laço de época, escolha de melhor época, parada antecipada, calibração, log |
| `ui/result_panel.ResultPanel` | **672 linhas, 41 métodos** | 3 listas paralelas de estado, 3 vínculos exclusivos de origem, layout, gravação no CSV, correção remota em thread |
| `app_tkinter.ChessOcrTkApp` | **626 linhas, 52 métodos** | 11 `tk.Variable` de configuração, 5 fábricas de parâmetro, orquestração de thread de OCR, consentimento remoto, atalhos |
| `ui/board_widget.InteractiveBoard` | **606 linhas, 43 métodos** | posição, seleção, pincel, arrasto, heatmap, tooltip de 3 classes, desenho no canvas, coordenadas |
| `inference.predict_with_orientation()` | **112 linhas** | quatro regras de decisão em cascata, com os limiares e a explicação em pt-BR embutidos |

E uma dispersão que não aparece em contagem de linhas: **o `labels.csv` é lido e escrito com
pandas em cinco módulos** — `dataset.py`, `audit.py`, `dataset_browser.py`, `splits.py` e
`cli/migrate_labels.py`. Cada um conhece o esquema da S-19 por conta própria. `LABEL_COLUMNS`
mora em `dataset.py` e `_write_labels` é privado dele, então `dataset_browser.update_row`
reimplementa a gravação. São 3.241 rótulos de trabalho humano acumulado atrás de cinco portas
diferentes.

> **✅ Resolvida (S-51, 2026-08-09).** Eram **seis**, não cinco: a varredura que o critério de
> aceite exige encontrou `review_queue.rare_classes_from_labels`, que nenhum levantamento
> tinha listado. E as portas não concordavam — três caminhos do `audit.py` gravavam sem
> escrita atômica e sem a normalização da S-58, o que fazia `cvoff-audit --fix` reintroduzir
> o `20.0` que a S-58 acabara de corrigir. Ver 9.4.

### 9.2 — O que extrair, e por que cada um

Não é decomposição por gosto. Cada extração abaixo tem uma consequência concreta:

| classe nova | de onde sai | o que passa a ser possível |
|---|---|---|
| **`Trainer`** (S-46) | `train_model` | testar a política de "melhor época" sem treinar; retomar de forma inspecionável; trocar o laço por um com validação a cada N passos |
| **`OrientationPolicy`** (S-47) | `predict_with_orientation` | medir cada regra isolada contra o conjunto de campo; acrescentar a regra das coordenadas (S-45) sem mexer no resto; ver a Fase 2 já mediu que a ordem das regras importa e mudou |
| **`DiagramEditorModel`** (S-48) | `ResultPanel` | as 3 listas paralelas e os 3 vínculos exclusivos viram um objeto testável sem Tk — e é ali que mora o bug que o roteiro headless da Fase 5 pegou |
| **`BoardModel` + `BoardRenderer`** (S-49) | `InteractiveBoard` | o modelo serve ao Tk e a qualquer outro frontend; o renderer vira o único ponto a reescrever numa eventual troca de framework |
| **`LabelStore`** (S-50) | 5 módulos | uma porta para o CSV, com escrita atômica e esquema num lugar só; e a base para trocar CSV por SQLite quando 3.241 virar 30.000 |
| **`BoardVerifier`** (S-38) | `board_detection` + `detection/embedded` | um gate para toda fonte de candidato, em vez de meio gate numa delas |
| **`BoardNormalizer`** (S-39) | `preprocess_cell_to_tensor` | o pré-processamento vira objeto com parâmetros, gravável no checkpoint junto com `arch_version` |

### 9.3 — A procedência que se perdeu, e o que ela custa

Medido no `data/labels.csv` de hoje, 3.241 linhas:

| coluna | preenchida | vazia |
|---|---|---|
| `source_pdf` | 46 (1,4%) | **3.195 (98,6%)** |
| `source_page` | 46 | 3.195 |
| `detection_source` | 40 (1,2%) | 3.201 |
| `side_to_move` | 189 (5,8%) | **3.052 (94,2%)** |
| `corrected_by` | **0 (0%)** | 3.241 |

A S-19 criou as colunas e a S-31 as preenche a partir da `RecognitionOrigin` — mas só para as
amostras salvas **depois** dela. As 3.195 anteriores foram gravadas quando a origem não era
registrada, e a `migrate_labels` diz corretamente que não há como inventá-la.

Três consequências que não são cosméticas:

1. **A S-07 não pode agrupar o split por livro.** O split é por hash do nome do arquivo,
   agrupado por diagrama duplicado. Agrupar por livro — que é o que impede o teste de medir
   "quão bem o modelo lê *este* livro" em vez de "quão bem ele generaliza" — precisa de
   `source_pdf`, e 98,6% não tem.
2. **A auditoria por fonte de detecção não tem dados.** 40 linhas em 3.241.
3. **`corrected_by` é coluna morta.** Está no esquema, no `LABEL_COLUMNS`, no CSV e em
   `append_training_sample(corrected_by=...)`. Nenhum chamador jamais passa um valor.

A procedência **é recuperável**, e por um caminho que este projeto tem tudo para fazer:
casar cada PNG de `data/samples/` contra os diagramas detectados nos 27 PDFs por hash
perceptual (`audit.dhash` já existe e já é usado para achar duplicatas). → **S-51**.

Sobre `corrected_by`: ou passa a ser preenchida (o valor útil não é o nome do usuário — é
**como** a amostra chegou ao rótulo: `ocr-aceito`, `ocr-corrigido`, `fila-revisao`,
`dataset-recorrigido`, `net-remoto`), ou sai do esquema. Uma coluna que ninguém escreve é
pior que nenhuma coluna, porque parece um dado. → **S-52**.

---

### 9.4 — A porta única do `labels.csv`, e os três defeitos que ela achou ✅ (S-51)

A extração que a 9.2 listava por último acabou vindo primeiro, e por um motivo prático: a
S-52 precisa gravar um campo novo, e gravá-lo em cinco lugares seria escrever o defeito antes
de consertá-lo.

**O item era organização; o que ele encontrou era conserto.** Três caminhos do `audit.py` —
`apply_side_to_move_fixes`, `quarantine_fatal_labels` e `remove_duplicate_labels`, todos
alcançáveis por `cvoff-audit --fix` — gravavam com `df.to_csv(csv_path)` direto no destino:

| garantia que a documentação afirmava | o que de fato acontecia |
|---|---|
| o `atomic_io` protege o `labels.csv` | `to_csv` trunca o destino antes de escrever, e o que estava sendo truncado era o dataset inteiro |
| a S-58 fez o arquivo convergir para um formato de inteiro | `--fix` reintroduzia o `20.0`, e o arquivo voltava a ter os dois |

O `save_splits` tinha o mesmo defeito de atomicidade, num arquivo que carrega a fronteira
entre treino e teste — a decisão mais irreversível do projeto por desenho da S-07.

**Eram seis portas, não cinco.** O critério de aceite pedia uma varredura que provasse que
nenhum `read_csv`/`to_csv` sobrevive fora do módulo. Ela encontrou
`review_queue.rare_classes_from_labels`, que nenhum levantamento tinha listado — e é
exatamente por isso que a varredura é um teste e não uma revisão manual.

**Uma decisão que a spec não previa: `csv` da biblioteca padrão, não pandas.** A S-58 existe
porque o pandas infere tipo, e a correção dela era uma disciplina que precisava ser lembrada
em cinco lugares. Com `csv.DictReader` não há tipo a inferir. O defeito deixou de ser evitado
e passou a não existir.

**Medido:** a saída é **byte a byte idêntica** à anterior, sobre o `labels.csv` real de 3.313
linhas e o `splits.csv` de 3.311 — e idêntica aos arquivos versionados, que não mudaram um
byte. Suíte de 805 para 813 testes.

**E `corrected_by` deixou de ser coluna morta** (metade da S-52). Toda amostra nova sai com o
caminho pelo qual chegou ao rótulo, nas duas telas. A regra mora em `labels.label_route` e não
no painel — a mesma regra da Fase 6: o que dá para testar não fica na janela. As 3.313 linhas
anteriores saem em `caminho não registrado` em `dataset_browser.route_distribution`, e é esse
número encolhendo que dirá se a coluna passou a valer alguma coisa.

Detalhe que só apareceu ao escrever o código: um caminho **já** gravava algo — o painel punha
`corrected_by="tkinter"` ao regravar uma amostra da aba Dataset. O nome da tela é precisamente
a informação sem valor que a spec avisa para não guardar.

### 9.5 — A procedência recuperada por hash perceptual ✅ código (S-52)

`provenance.py` e `cvoff-provenance`. O índice é JSONL incremental — um livro por vez, e um
livro reindexado substitui o que havia dele —, e o casamento é vetorizado, porque 3.195
amostras contra dezenas de milhares de diagramas são centenas de milhões de distâncias de
Hamming.

**Validado contra verdade de referência, e é isto que dá confiança na cadeia.** As amostras
salvas depois da S-31 têm procedência gravada, então o casamento pode ser conferido em vez de
acreditado. Índice das 20 primeiras páginas do `1937 Kemeri`:

| sonda | resultado |
|---|---|
| 12 amostras daquelas páginas, com procedência conhecida | **12 de 12**, distância 0, **página certa** |
| os 3.195 órfãos contra o mesmo índice | **0** casamentos; impostor mais próximo a **7 bits** |

**E é aqui que a medição pede cautela.** Um recorte deslocado em 6 px num tabuleiro de 800
custa 6 bits, que é exatamente o limiar; o impostor mais próximo estava a 7. **A folga é de um
bit** — e isso com um índice de 11 entradas, o caso mais fácil possível. Com o acervo inteiro
o impostor mais próximo só pode chegar mais perto.

Por isso o comando **não grava por padrão**: `--match` relata a taxa e o histograma de
distância, e `--apply` é um segundo passo. O histograma existe exatamente para que o limiar
seja escolhido olhando dados em vez de herdado desta linha.

**O que falta, e é decisão sua:** indexar os 27 PDFs (~12 mil páginas, horas de CPU). Sem
isso não há taxa real sobre os 3.195 órfãos — só a garantia de que o mecanismo acerta quando
tem o que casar.

**E o que a recuperação destrava**, quando vier: `splits.groups_by_book` agrupa o split por
livro, que é o que faz o `test` responder "quão bem o modelo lê um livro que nunca viu" em vez
de "um diagrama parecido com os que viu". Com duas ressalvas registradas no próprio docstring:
`ensure_splits` nunca move amostra já registrada, então o agrupamento só vale para amostras
novas ou numa reatribuição do zero; e 27 livros dão 27 grupos, o que reduz muito a
granularidade do split.

---

### 9.6 — As quatro extrações, e o que cada uma destravou ✅ (S-47 a S-50)

A 9.2 dizia que extração sem consequência não entra nesta spec. As quatro entraram, e o que
segue é a consequência de cada uma **medida em teste que antes não existia** — não em linhas
economizadas.

| item | o que saiu | o que passou a ser possível | testes novos |
|---|---|---|---|
| **S-47 `Trainer`** | `train_model`, 259 linhas | perguntar à política de melhor época **sem treinar** | 15 |
| **S-48 `OrientationPolicy`** | `predict_with_orientation`, 112 linhas | medir cada regra isolada; trocar a ordem da cascata | 18 |
| **S-49 `DiagramEditorModel`** | `ResultPanel` | responder "o que `Ctrl+S` faz agora?" sem janela | 23 |
| **S-50 `BoardModel`/`BoardRenderer`** | `InteractiveBoard` | clique→arrasta→solta sem canvas; redesenho parcial | 39 |

Suíte de **813 para 957 testes** (mais 739 subtestes), `ruff` e `mypy` limpos, e o roteiro
headless do CONTRIBUTING continua reconhecendo os 6 diagramas da página 80 do `Karpov 1` e
navegando entre eles.

**O defeito histórico que a S-47 finalmente pôs num teste de três linhas.** O ROADMAP
registra que "a primeira versão da 5.3 estava errada, e foi o uso que mostrou": retomar
zerava o controle de melhor época e a primeira época da retomada sobrescrevia o checkpoint
mesmo sendo pior. Ele sobreviveu duas fases porque **não havia como perguntar à política sem
rodar um treino inteiro**. Hoje:

```python
policy = BestEpochPolicy("val_board_exact_acc", 0.9906, best_epoch=12)
self.assertFalse(policy.observe(0.9800, epoch=1))
self.assertEqual(policy.best_epoch, 12)
```

**A S-48 mudou o que a cascata é, não o que ela decide.** Resultado idêntico ao de antes — as
regras são as mesmas, na mesma ordem, com os mesmos limiares. O que mudou é que
`explain()` responde o que **cada** regra disse sobre um diagrama, inclusive as que calaram,
e trocar a ordem passou a ser trocar uma tupla. O teste que mais diz sobre o item é o que
resolve o mesmo par de leituras com duas ordens e recebe duas respostas.

`CoordinateRule` entrou na cascata e **cala em 100% dos diagramas**, porque nada produz
`BoardCoordinates`. É deliberado, e está no docstring do tipo: a S-45 foi medida e adiada
(13,7% de cobertura, 48 dos 52 num livro que já lê a 1,000, e zero diagramas do ponto de
vista das pretas). O que a regra faz é transformar a S-45, quando ela voltar, num problema de
**produzir o dado** em vez de um problema de mexer na política — por vinte linhas.

**A S-49 encontrou um defeito, como a S-51 tinha encontrado três.** `save_all` nunca olhava o
vínculo do editor: com uma linha da aba Dataset aberta, "Salvar todos" criava uma **amostra
nova** da mesma imagem em vez de regravar o rótulo. É exatamente o defeito que a S-23 fechou
no caminho do `Ctrl+S`, e que continuava aberto ao lado. Só apareceu porque `save_target()`
passou a ser uma pergunta que se faz uma vez e se responde em dois lugares.

**A S-50 entregou o redesenho parcial, e ele tem um limite honesto.** `BoardChange.dirty` diz
quais casas mudaram, e `draw_dirty` redesenha só elas — arrastar uma peça toca 2 casas, não
64. Mas o parcial vale **só no modo de edição**: em modo de jogo o conjunto de alvos legais
muda a cada seleção, e ele não está em `dirty`. Ali o total continua, e o comentário no
código diz isso. O modo de edição é o que importa para o custo, porque é onde o arraste
acontece.

**O critério de aceite que não foi atingido, e o número real.** A S-49 pedia `ResultPanel`
abaixo de 400 linhas; ele ficou em **648** (a spec foi escrita quando o arquivo tinha 672, e
ele já estava em 800 quando o item começou). O que saiu foi o que o item existe para tirar —
**zero linhas de regra de edição sobrevivem ali** — mais o botão "Corrigir Net", que virou
`ui/net_button.py` por não ter nada a ver com editar diagrama. O que sobrou é layout (~95
linhas de `_build`), repasse para o modelo e caixas de diálogo. Cortar mais seria separar um
widget da própria construção, e isso é organização sem consequência — que é o que a 9.2
proíbe. `InteractiveBoard` foi de 606 para **390**, com 452 no arquivo.

---

## Fase 10 — A interface, e a decisão que ninguém tomou

### 10.1 — O estado de hoje, sem adjetivos

Tkinter + `ttk`, ~2.500 linhas em 14 módulos, com um roteiro headless que dirige a janela e
já pegou um defeito que 509 testes verdes não pegaram. Funciona, é testável, não tem
dependência pesada, e depois da Fase 6 **não tem lógica de negócio dentro**.

Isso é bom o bastante para não justificar reescrita por estética. Mas há três lugares onde a
escolha de framework já está cobrando, e todos os três são mensuráveis:

**Tabela do dataset.** `DatasetPanel` pagina em blocos de N linhas, e o comentário no código
diz por quê: *"3.195 linhas de uma vez travam o Treeview do Tk"*. A paginação é uma
mitigação, e ela custa o que mitiga — filtrar e ordenar valem por página, não pelo conjunto.
Um `QTableView` com modelo virtual mostra 3.241 linhas sem paginar, e 30.000 também.

**O tabuleiro.** `InteractiveBoard.redraw()` tem 79 linhas de desenho manual no canvas —
casas, heatmap, peças, coordenadas, seleção, arrasto — e é redesenhado inteiro a cada
mudança. Um `QGraphicsScene` dá zoom, pan, itens com z-order e sobreposição sem que nada
disso seja escrito.

**As sobreposições de OCR que a Fase 8 vai querer.** Mostrar sobre a página os bbox de texto
reconhecido, com a confiança em cor e o texto editável no lugar, é o caso de uso natural de
uma cena gráfica. No canvas do Tk é trabalho manual de coordenadas.

### 10.2 — As opções, com o custo real

| opção | custo | o que muda | quando faz sentido |
|---|---|---|---|
| **Ficar no Tk** | 0 | nada | se a Fase 8 não trouxer sobreposição sobre a página |
| **`ttkbootstrap`** | ~1 dia | tema moderno, mesma API de widget, `ttk.Treeview` continua igual | ganho estético imediato, risco quase nulo — **fazer de qualquer forma** |
| **`CustomTkinter`** | ~1 semana | visual melhor, **mas não é drop-in**; não tem equivalente decente de `Treeview` | não recomendado: paga a migração e ainda precisa do Tk para a tabela |
| **PySide6 / Qt** | ~3–4 semanas | tabela virtual, cena gráfica, `QThread`+sinais no lugar de `root.after`, `QPdfView` nativo, DPI correto, `QAction` para atalhos | quando a sobreposição de OCR ou o dataset > 10 mil linhas cobrarem |

A Fase 6 tornou essa migração **afordável pela primeira vez** — com o pipeline em
`service.py`, portar a UI é portar UI, não reescrever o OCR junto. Foi exatamente esse o custo
que impediu antes.

A recomendação não é "migre" nem "não migre". É **decidir por gatilho e não por gosto**
(→ **S-53**): `ttkbootstrap` agora, e o porte para Qt disparado por um de dois eventos
observáveis — a Fase 8 exigir sobreposição editável sobre a página renderizada, ou o
`labels.csv` passar de 10 mil linhas. Enquanto nenhum dos dois acontecer, o Tk é a escolha
certa e a migração é otimização prematura.

### 10.3 — O Streamlit precisa de uma decisão, não de mais um item

O fechamento da Fase 6 registra com honestidade o que a paridade não entregou: o Streamlit
tem o mesmo *pipeline*, e não tem o editor por clique (S-20), o painel de legalidade (S-21),
a fila de revisão (S-22) nem a aba de dataset (S-23) — são widgets de Tk.

São 588 linhas mantidas, testadas junto e citadas no README, que hoje servem para **ver** o
resultado e não para **trabalhar** nele. O fluxo de valor do produto é corrigir → salvar →
treinar, e ele não existe ali.

Duas saídas defensáveis, e a pior escolha é continuar sem escolher:

- **Aposentar**, movendo para `examples/` e dizendo no README que é demonstração do serviço;
- **Assumir** como interface remota de verdade, o que significa o editor de posição no
  navegador — `streamlit-drawable-canvas` ou um componente próprio — e a fila de revisão.

→ **S-54**.

### 10.4 — S-36 continua aberta

Empacotamento para Windows nunca foi feito. Hoje, usar o projeto exige Python 3.10, `uv` e
linha de comando. Com a Fase 6 fechada e a interface estável, é o item que transforma "meu
projeto" em "programa que outra pessoa usa". → **S-55**.

---

### 10.5 — A Fase 10 fechada: o tema, a decisão e o programa ✅ (S-53, S-54, S-55)

**S-53 — `ttkbootstrap` entrou, e o porte para Qt ficou amarrado a gatilho.** Um módulo,
`ui/theme.py`, aplicado antes do primeiro widget; padrão `bootstrap-light`, trocável por
`CVOFF_TTK_THEME` entre os 30 temas. O que precisou de teste não foi o tema bonito — foi a
**degradação**: sem a biblioteca, com um nome de tema errado, ou num bundle que não a
incluiu, a janela abre em `ttk` puro e o log diz por quê. Aparência não pode ser motivo de a
ferramenta não abrir.

Escolha de padrão que não é gosto: claro, porque o produto é comparar diagrama impresso em
papel branco com o que o modelo leu, e um tema escuro põe o tabuleiro claro e a página
renderizada sobre fundo preto. E um nome da era 2.0, porque os antigos (`litera`, `flatly`)
emitiriam um `DeprecationWarning` a cada abertura.

**A parte (b) da S-53 é a que dura.** Os dois gatilhos do porte para Qt estão registrados no
[ARCHITECTURE.md](ARCHITECTURE.md), onde a próxima pessoa os encontra — sobreposição editável
sobre a página, ou `labels.csv` acima de 10 mil linhas. Hoje ele tem **3.313**, 33% do
gatilho. E o porte ficou mais barato do que a spec supunha: a S-50 isolou `board_render.py`
como único arquivo de desenho, e a S-49 tirou o estado do editor do widget.

**S-54 — o Streamlit foi aposentado.** `app_streamlit.py` virou `examples/streamlit_demo.py`,
e o README parou de chamá-lo de "interface web alternativa". A escolha foi entre assumir a
promessa (~1 semana: editor por clique no navegador, painel de legalidade, fila de revisão) e
desfazê-la; desfazer venceu porque não há uso remoto real, e a pior saída era continuar sem
escolher. Ele continua rodando e continua testado — `streamlit.testing.v1.AppTest` o executa
sem navegador —, e continua sendo útil por um motivo honesto: ele importa o `OcrService` e
quebra quando a fachada muda, que é o alarme que se quer de um exemplo.

**S-55 — o programa existe, e foi medido.** `packaging/cvoff.spec` + `packaging/build_windows.py`,
PyInstaller em `--onedir`. **696 MB, 5.247 arquivos**, build completo: leitor **e** treinador.

O peso é quase todo torch, e ele está ali por decisão de produto: o ciclo que dá valor ao
projeto é *corrigir → salvar → treinar*, e um bundle só de leitura (~5x menor, com
`onnxruntime` e o `.onnx` da S-30) entregaria um programa sem o botão "Treinar modelo". O
caminho para fazê-lo está descrito na spec, para quando a pergunta voltar.

| ponto | o que foi feito |
|---|---|
| `--onedir`, não `--onefile` | `--onefile` extrairia ~700 MB para o `%TEMP%` **a cada execução** |
| `config.PROJECT_ROOT` num bundle | ramo `sys.frozen`: a raiz gravável é a pasta do `.exe`, não o pacote |
| `BUNDLE_ROOT`, novo | recursos do programa (`assets/`) vão dentro; dados do usuário, ao lado |
| WebView2 | runtime do sistema, não empacotável. A aba Leitura degrada, como já degradava — *a aba saiu na S-69 e o ponto deixou de existir* |
| Stockfish, Streamlit | fora, pelos motivos de sempre — e o Streamlit também pela S-54 |

**O defeito que o item existia para evitar, verificado.** `PROJECT_ROOT` usava
`Path(__file__).resolve().parents[2]`, que num bundle aponta para **dentro** do pacote — e o
`labels.csv` é 3.313 rótulos de trabalho humano, o último arquivo que se quer num diretório
que a reinstalação apaga. Conferido no bundle real: o `.exe` gravou
`dist/ChessVisionOFF/data/app_tkinter_state.json` e leu
`dist/ChessVisionOFF/models/piece_classifier.pt`, ambos **ao lado** do executável.

**E como se confere uma instalação numa máquina que não é a sua.** `--selftest` abre um PDF,
reconhece a página e escreve as FENs no log, sem janela — e depois confere que o caminho de
**treino** também monta, porque ler não prova treinar e um bundle incompleto só falharia
quando o usuário clicasse "Treinar modelo", depois de já ter corrigido dezenas de diagramas.
Códigos de saída distintos para faltas distintas (2 sem PDF, 3 sem checkpoint, 4 lê mas não
treina).

Medido no bundle contra o mesmo comando no checkout, página 80 do `Karpov 1`:

| | checkout | bundle |
|---|---|---|
| diagramas | 6 | **6** |
| FENs | — | **idênticas, as seis** |
| confiança mínima | 1,000 · 1,000 · 0,939 · 1,000 · 0,790 · 1,000 | **idênticas** |
| caminho de treino monta | sim | **sim** |

**O que este item não entrega, e é decisão sua.** O executável não é assinado: o SmartScreen
vai avisar na primeira execução de quem receber o `.zip`, e resolver isso exige um
certificado de assinatura de código — dinheiro e um processo, não uma linha de spec. E não há
instalador: o produto é uma pasta que se descompacta, o que é suficiente para o critério de
aceite ("roda numa máquina Windows limpa") e insuficiente para parecer software comercial.

---

### 10.6 — A paleta de edição, e três coisas que ela não dizia ✅ (S-65)

Pedido de uso, não achado por varredura: *"troca essa fonte pelas imagens da pasta assets"*.
O que a mudança encontrou foi mais do que fonte.

Os 12 botões desenhavam `♙♘♗` — símbolos Unicode, que dependem de a máquina ter uma fonte que
os desenhe. No Windows a `Segoe UI Symbol` os renderiza finos e de altura irregular, e as
brancas quase somem no fundo claro do botão. Agora são as peças de `assets/piece_images/`, as
mesmas do tabuleiro: **a paleta mostra o que o clique vai colocar.**

Duas coisas apareceram ao mexer nisso, e as duas custavam mais que a fonte:

- **O pincel ativo era invisível.** Pincel é um modo, e a única forma de saber qual peça
  estava carregada era clicar numa casa e ver o que saía — executar a ação destrutiva para
  poder conferi-la. Os botões viraram `Radiobutton` com estado ligado, e clicar no botão já
  aceso larga o pincel.
- **Desfazer custava três gestos.** Pôr a peça errada exigia largar o pincel, clicar com o
  direito e pegar o pincel de volta. `BoardModel.paint` passou a alternar: clicar de novo na
  mesma peça apaga. Pôr e tirar viraram o mesmo gesto.

**O que a implementação descobriu.** Nenhuma variante de `Toolbutton` do tema em uso desenha
estado selecionado quando o botão tem imagem e não tem texto — renderizados lado a lado, o
aceso e o apagado saem idênticos. Daí o `Radiobutton` clássico, que é o único em que o
`selectcolor` é escolhido em vez de herdado. E as cores saem do tema: metade dos 30 temas do
`ttkbootstrap` é escura, e nos escuros as peças pretas somem — por isso o ícone vai sobre a
cor da casa clara, que é como ele se parece no tabuleiro.

Sem `assets/piece_images/`, a paleta volta ao Unicode. Uma peça faltando não impede a aba de
abrir.

---

### 10.7 — A segunda opinião que não sai da máquina ✅ (S-66)

O `RemoteFenProvider` da S-32 é `Protocol`, e o docstring dele já dizia por quê: "um segundo
modelo local satisfaz a mesma interface". A S-66 é essa frase cobrada. O adaptador para o
`Chess_diagram_to_FEN` (MIT, Jost Triller) lê um diagrama já recortado, e **nada sai da
máquina** — então este caminho não passa pelo consentimento da S-32. Ele existe em boa parte
para tornar aquele desnecessário.

O que ele resolve não é acurácia, é **custo humano**. Conferir um diagrama é olhar 64 casas, e
é isso que limita quantas amostras entram no `labels.csv` — não o tempo de máquina, que é de
décimos de segundo. Medido no `Niemeijer - Zwarte Magie (1945)`, 20 diagramas de um livro onde
o classificador local afunda (confiança mínima média 0,25, **zero** acima do gate):

| | leitor local | externo |
|---|---|---|
| coerentes com o tema do livro | 12/20 | **18/20** |
| mediana de casas em desacordo entre os dois | — | **4,5** |

E o achado que decide o desenho: nos três diagramas conferidos à mão, casa a casa, o conjunto
em desacordo era **exatamente** o conjunto de erros do leitor local — 4 de 4, 23 de 23, 41 de
41. Nenhum erro fora dele. Naquele livro, olhar 4,5 casas em vez de 64 não perdia nada.

**O que ele não afirma** é que a segunda leitura está certa: 2 dos 20 saíram com dois reis
brancos e nenhum preto. Por isso a saída é uma *marcação* e não uma correção automática — e o
número vale para um livro de um regime. Num acervo em que o leitor local vai a 1,000, a mesma
marcação pode apontar casa certa.

---

### 10.8 — A aba Galeria: o que o pipeline não tem como saber ✅ (S-67)

Há informação que só existe na cabeça de quem está com o livro aberto: em que lance a posição
acontece, de quem é a vez quando o texto não diz, os headers do exercício. O produto não tinha
onde guardá-la. Agora tem — `data/gallery/<livro>.json`, um diagrama por vez, sincronizado com
a página.

**Não é um segundo editor**, e é isso que decide a tela: a unidade de trabalho aqui é a
anotação, então o que aparece no centro é o **recorte original do livro**, e não o tabuleiro
redesenhado a partir da FEN — quem digita "lance 24" está lendo a legenda impressa.

Duas decisões que valem além deste item:

- **Arquivo por livro, e não colunas no `labels.csv`.** Os dois falam dos mesmos diagramas e
  têm vidas diferentes: uma linha existe no CSV porque alguém salvou aquela imagem para o
  modelo aprender, e a maioria dos diagramas de um livro nunca vira amostra de treino.
  Misturá-los obrigaria a salvar uma amostra só para poder dizer "este é o lance 24".
- **Ausente significa "faça como sempre".** Anotação vazia não é gravada, porque não declarar
  e declarar vazio são coisas diferentes — e só a primeira deixa a S-17 decidir.

---

## Fase 11 — O modelo, e por que ele vem por último

A Fase 5 gastou uma grade inteira de experimentos para descobrir que a arquitetura não era o
problema: `res32`, `mobilenet_v3_small` e a referência empatam em 0,9906, e TTA, pesos de
classe e temperatura calibrada pioraram ou não mudaram nada. A medição de campo desta análise
explica por quê — o gargalo está antes do classificador, não nele.

Então esta fase tem uma pré-condição, e ela é o item: **só começa depois que o conjunto de
campo da S-41 disser que o erro restante é de classificação.** Fica especificada agora porque
a decisão de *não* fazê-la precisa ser tão explícita quanto a de fazê-la.

O que ela propõe, quando a hora chegar (→ **S-62**): o modelo decide 64 vezes de forma
independente, e é por isso que `decode.py` existe — a decodificação com restrições é uma busca
posterior que conserta o que o modelo não sabia que estava errado. Dois degraus para dar ao
modelo o que hoje só o decodificador tem:

- **canais de coordenada e paridade** na entrada da casa (fila, coluna, casa clara/escura):
  ~1% de parâmetros, um retreino, e a confusão peão-na-primeira-fila some por construção;
- **cabeça por tabuleiro** — as 64 saídas do tronco viram uma sequência e uma cabeça leve
  (auto-atenção ou GRU bidirecional) decide as 64 classes juntas.

O decodificador **não** sai: ele continua sendo a garantia dura. O que muda é a frequência com
que ele precisa reparar — e `DecodeResult.changed_squares` já mede exatamente isso, o que faz
deste um item com critério de aceite pronto antes de a primeira linha ser escrita.

Junto vai a higiene do dataset (→ **S-63**), que a auditoria de hoje já relata e não tem como
corrigir: 49 imagens órfãs (~90 MiB), 1 rótulo sem imagem, e as redundâncias que cresceram de
234 em 220 grupos (BASELINE.md) para **248 em 227** sem nada monitorando. Continuam todas no
mesmo split — verificado, 0 grupos espalhados —, mas o crescimento não é acompanhado.

---

### 11.1 — A Fase 11 feita, e reprovada nos próprios critérios ✅ (S-62, S-63, 2026-08-11)

A pré-condição acima dizia que a fase "só começa depois que o conjunto de campo disser que o
erro restante é de classificação". Ele nunca disse isso, e continua não dizendo. A fase foi
feita mesmo assim, e o resultado é a terceira evidência de que a pré-condição estava certa.

#### S-62 — os dois degraus, implementados e medidos

Contra o controle `aug0` retreinado, no conjunto de campo, com a máquina livre:

| variante | parâmetros | exportação | legais | **casas reparadas** | s/diagrama |
|---|---|---|---|---|---|
| **`aug0` — controle** | 2,19 M | **0,7368** | 35 | **15** | 0,315 |
| **(a) coordenadas e paridade** | **2,19 M** (+0,04%) | 0,7368 | 35 | **10** (−33%) | **0,308** |
| (b) cabeça por tabuleiro | 3,26 M | 0,7368 | 35 | **19** (+27%) | 0,461 |
| (a) + (b) | 3,26 M | **0,7105** | **34** | 19 | 0,363 |

Os três critérios de aceite, escritos antes da primeira linha de código:

| critério | alvo | (a) | (b) | (a)+(b) |
|---|---|---|---|---|
| reparo cai **pelo menos pela metade** | ≤ 7 | 10 ✗ | 19 ✗ | 19 ✗ |
| a taxa de exportação **sobe** | > 0,7368 | ✗ | ✗ | **✗✗** |
| custo ≤ 1,5× | ≤ 0,47 s | ✓ | ✓ | ✓ |

**Dois de três falham nos três: o item não entra.** É a mesma regra que descartou o TTA, os
pesos de classe e a temperatura calibrada, e ela não vale nada se for afrouxada quando o
resultado é simpático.

**Mas os três não falham igual.** A (a) é a única variante do projeto inteiro que fez o que a
S-62 existia para fazer — um terço menos de reparo, com **864 parâmetros a mais**, inferência
mais barata que o controle e validação idêntica a ele. A (b) é o oposto: 1,07 M de parâmetros,
27% mais reparo, 1,46× o custo, validação pior e instável. E os dois juntos herdam o pior dos
dois — perdem um diagrama e produzem a **única leitura fatalmente ilegal** de todas as
variantes medidas.

**A ironia que fecha a Fase 11.** A métrica de aceite da S-62 foi mais bem satisfeita pela
S-40 do que pela própria S-62:

| o que mudou | casas reparadas |
|---|---|
| **aumento dirigido, 16 épocas (S-40)** | **9** — −40% |
| canais de coordenada (S-62a) | 10 — −33% |
| cabeça por tabuleiro (S-62b) | 19 — +27% |

A S-62 existe sobre a tese de que o modelo precisa **saber** o que o decodificador sabe:
coordenada, paridade, as outras 63 casas. O que de fato reduziu a dependência do decodificador
foi mostrar ao modelo mais páginas feias. **Dado, não arquitetura** — que é exatamente o que a
Fase 5 já havia concluído sobre o classificador, e o que a medição de campo desta análise diz
desde a primeira linha.

**O que fica no código.** `--coords` e `--head board`, cada um com a sua `arch_version`
(`...-coords`, `...-board`), a garantia de que um checkpoint de um não carrega no outro, e um
teste de **paridade numérica** que prova que os canais zerados reproduzem o modelo de hoje bit
a bit. `ArchConfig()` não mudou: a produção continua sendo o que era, e a medição contra o
checkpoint de produção confirma isso dígito a dígito.

**Quando reabrir, e qual.** A (a), quando o conjunto de campo crescer. O critério que a reprova
é a taxa de exportação, e a 7.7 mostrou que ela não tem resolução para julgá-la: nenhum modelo
pode ganhar um diagrama num conjunto em que os 8 barrados estão a 0,37 do gate.

#### S-63 — a higiene, aplicada

`cvoff-audit --drop-missing --prune-orphans`, rodado no dataset real:

| | antes | depois |
|---|---|---|
| rótulos sem imagem | **5** | 0 — para `data/quarantine.csv` |
| imagens órfãs | **49** (41,4 MiB) | 0 — para `data/orphans/20260811_172159/` |
| rótulos utilizáveis | 3.449 | 3.449 |
| redundância | 284 em 259 grupos (**8,2%**) | abaixo do teto de 10% |

**Nenhuma das duas ações apaga nada, e a segunda mudou de desenho por causa da medição.** O
`--drop-missing` ia remover a linha — "não há o que recorrigir, a imagem sumiu". Rodado no
dataset real, os 5 rótulos nesse estado têm **todos** procedência preenchida: a imagem é
reextraível do livro e a FEN é trabalho humano que sobreviveria ao reencontro. Apagar seria
jogar fora a metade cara do par para limpar a metade barata.

O critério de aceite — `data/samples/` e `labels.csv` com o mesmo conjunto de nomes — é
conferido pelo próprio comando ao final, e ele o imprimiu.

E o teto de redundância já tem o que vigiar: 234 em 220 grupos no BASELINE, 248 em 227 na
análise da Fase 11, **284 em 259** hoje. Continua abaixo dos 10%, e agora o crescimento tem
quem o note.

---

## Fase 12 — A página exibida deixa de ser uma figura ✅ concluída (2026-08-12)

**Como esta fase apareceu.** Nenhum dos quatro itens saiu de varredura de código. Saíram de
usar o produto, e todos tocam a mesma coisa: o visualizador mostrava a página e **só isso**,
enquanto todo o trabalho acontecia nas outras abas. O detector da S-12 já sabia onde estão os
diagramas de cada página desde a Fase 2 — o resultado ia direto para o reconhecimento e nunca
chegava à tela.

| # | Entrega | Ref. spec | Status |
|---|---|---|---|
| 12.1 | Os diagramas da página viram retângulo desenhado e alvo de clique | S-68 | ✅ |
| 12.2 | A aba "Leitura" (WebView2) sai, e com ela a última dependência de plataforma | S-69 | ✅ |
| 12.3 | Roda, arrasto e zoom ancorado no canvas do projeto | S-70 | ✅ |
| 12.4 | Campo Lance ao lado da vez, e a cor que diz onde o trabalho parou | S-71 | ✅ |

**Critério de saída:** abrir um livro já trabalhado e saber, **sem rodar nada**, onde parou; e
escolher um diagrama apontando para ele, em vez de arrastar o mouse em volta dele. Os dois
atingidos e conferidos no app com `labels.csv` e galeria temporários.

### 12.1 — O que o clique precisou decidir, e o que só a página real respondeu (S-68)

`ui/page_overlay.py` é a parte que se verifica sem abrir janela: ponto do PDF → pixel de
canvas, qual retângulo o clique acertou, e o que aquele clique significa. Quatro decisões
ficaram registradas ali, e nenhuma é óbvia antes de ver a página:

- **A menor caixa vence.** O empate acontece: o caminho por contorno às vezes acha a moldura
  do exercício *e* o tabuleiro dentro dela, e as duas contêm o mesmo clique. Devolver a maior
  faria o clique no tabuleiro abrir a moldura — o candidato que o modelo lê pior.
- **Clicar num diagrama não lido reconhece a página inteira.** Ler o recorte isolado sairia da
  página rasterizada em vez da imagem embutida — 590×590 nativos contra ~430 px a 220 DPI no
  Kemeri (S-12) — e sem o contexto de texto que decide o lado a jogar (S-16/S-17). Seria um
  diagrama lido **pior** que pelo botão de sempre, sem que nada na tela dissesse por quê.
  Paga-se a página uma vez; dali em diante todo clique nela é instantâneo.
- **"OCR melhor diagrama" não apaga as outras caixas.** Ele lê um, e o detector achou seis.
  Com `max_boards=1` o contorno devolve o de maior *score*, não o primeiro em ordem de
  leitura — prometer que a caixa restante é a de número 1 seria falso.
- **O índice sai do detector, e não é renumerado.** Renumerar aqui recriaria, entre a tela e
  ela mesma, o desencontro que a S-14 corrigiu entre a tela e o PGN.

### 12.2 — O WebView2 sai, e foi a S-68 que o condenou (S-69)

A aba "Leitura" embutia o visualizador do Edge por `SetParent`. Um HWND nativo filho pinta
acima de qualquer item do canvas; o leitor interno do Edge não aceita JS injetado e não
informa em que página está. Ou seja: naquela aba não havia como desenhar os retângulos,
capturar o clique nem saber o que o usuário estava vendo. **A sincronia entre as duas abas era,
por construção, de mão única e cega.**

Some `webview2_panel.py`, e com ele `pythonnet` e `pywebview` — não sobra dependência de
plataforma nenhuma no projeto, e o ponto que a S-55 carregava ("WebView2 é runtime do sistema,
não empacotável") deixou de existir. Para ler o livro com rolagem contínua e busca de texto, o
botão **Abrir no leitor do sistema** entrega o PDF ao leitor padrão da máquina.

### 12.3 — A leitura de volta, e o defeito que só a janela real mostrou (S-70)

O que a S-69 tirou era real: rolagem contínua e zoom. O que ficou no lugar foi um canvas com
duas barras de rolagem — suficiente para recortar e reconhecer, pouco para *ler*. `viewport.py`
devolve a parte que faltava, e as três decisões dele só se percebem errando ao usar: a roda que
**vira a página na borda** (com carência de 350 ms, senão uma roda inercial pula quatro páginas
por giro), o zoom **multiplicativo e ancorado no ponteiro** (aditivo de 0,1 dá salto de 33% em
0,3 e de 5% em 1,9 — a mesma tecla com efeitos diferentes), e o ajuste à largura, que é uma
conta e não um palpite.

**O defeito.** A primeira versão perguntava ao `winfo_containing` se o ponteiro estava sobre a
página. No Windows ele resolve pelo `WindowFromPoint` do sistema, então devolve `None` sempre
que *outra* janela cobre aquele ponto: medido com a janela do app atrás do terminal,
`winfo_containing(951, 346)` deu `None` num canvas de 909×740 posicionado exatamente ali — e a
roda simplesmente não fazia nada, **sem erro nenhum na tela**. Um tooltip aberto por cima daria
a mesma falha em uso normal. É a mesma lição que a Fase 5 registrou no teto de diagramas: o
modo de falha caro não é o erro, é o silêncio.

### 12.4 — "Onde eu parei?", respondido pelo CSV e não pela memória (S-71)

O campo **Lance** foi para o lado do "Lado a jogar" porque é a mesma leitura — os dois saem da
legenda impressa, e quem está com o livro aberto declara os dois de uma vez. Ele grava na
**mesma anotação que a Galeria edita** (S-67): duas cópias em memória do mesmo JSON
divergiriam, e a última a gravar apagaria o que a outra escreveu.

E a caixa do diagrama passou a ter três cores: **azul** localizado, **âmbar** lido e não salvo,
**verde** com amostra no `labels.csv`. Quem responde pelo verde é a procedência gravada no CSV
(S-19), não o que está em memória — então ele aparece ao abrir um livro trabalhado semana
passada, **antes de qualquer OCR**, e responde "onde eu parei?" sem custar uma leitura.

Dois defeitos que o item encontrou, os dois de silêncio:

- A Galeria só conhecia o livro **depois de uma varredura**. Sem varrer, `pdf_path` era `None`
  e `save()` descartava sem avisar: o número digitado sumiria.
- O caminho de **gravar amostra nova** não notificava ninguém — só o de regravar linha
  notificava —, então a aba Dataset não via a amostra recém-salva.

**A seleção deixou de ser uma cor**, porque a cor passou a carregar informação: ela era laranja
e apagava justamente o estado do diagrama que se acabou de abrir. A primeira tentativa foi
hachura, e os pontinhos caíam sobre as casas que se está tentando conferir — que é para o que a
caixa existe. Não há hachura mais rala entre as do Tk, então a seleção virou borda grossa mais
uma segunda borda **por fora** da caixa: por fora porque a caixa encosta no diagrama, e uma
borda interna cairia sobre a primeira fila de casas.

---

## Fase 13 — A base de partidas ✅ código completo (2026-08-13)

**De onde ela veio.** De uma ideia sua, não de análise: *"a galeria poderia autopreencher os
campos com dados lidos do PDF, consultados numa base de partidas"*. O que a medição fez foi
mudar duas vezes o desenho dela antes de qualquer linha de código.

| # | Entrega | Ref. spec | Status |
|---|---|---|---|
| 13.1 | Casamento por **nome**: legenda → partida → lance, na Galeria | S-72 | ✅ |
| 13.2 | Casamento por **posição**: `cvoff-games`, alcança todo diagrama | S-73 | ✅ |
| 13.3 | Medir outros livros, de outros gêneros | — | ✅ quatro livros, 3.563 diagramas |
| 13.4 | A confirmação tira o diagrama da fila de revisão | S-74 | ✅ |
| 13.5 | A quarta cor no visualizador: "não precisa" | S-75 | ✅ |

**Critério de saída:** um diagrama cuja posição está na base sai com lance, vez e headers sem
ninguém digitar — e nada do que a pessoa digitou é tocado. Atingido nos dois caminhos.

### 13.0 — O que a medição desmentiu antes de a primeira linha ser escrita

**Primeiro: o interpretador de legenda já existia, e o levantamento disse quanto ele alcança.**
A Fase 3 escreveu o `parse_context`, que devolve jogadores, evento e ano; a Galeria nunca o
chamou. Rodado nos 1.408 diagramas do `Secrets of Chess Training`:

| | |
|---|---|
| com legenda | 96,7% |
| rendem os **jogadores** | **12,6%** |
| rendem o **evento** | 1,1% |
| rendem o **ano** | 1,1% |

O texto dá o nome e cala sobre o resto. Isso definiu o papel da base: ela não entra para *ler*
os headers, entra para **completar a partir do pouco que o texto deu** — e para dar os dois
campos que fonte nenhuma do projeto sabia dar, o número do lance e a vez.

**Segundo: a base tem 10.547.416 partidas e ler os 9,7 GB custa 147 s.** Esse número mudou a
economia inteira. A proposta que eu tinha feito — indexar as ~800 milhões de posições num banco
de dezenas de GB — deixou de fazer sentido diante de **inverter a busca**: são as *nossas*
posições que vão para a memória, e a base passa uma vez.

**Terceiro, e é o que a Fase 13 tem de mais honesto: a hipótese do reparo morreu.** Eu havia
proposto usar a base para apontar o erro do OCR — posição lida a 1 ou 2 casas de um lance da
partida significaria "o modelo errou aqui". **Zero em 91 diagramas.** O casamento é binário: ou
bate nas 64 casas, ou a distância é grande. Neste livro quase todo diagrama sai com confiança
1,000, então não havia erro a reparar; e os livros onde o OCR erra são os de scan puro, que não
têm legenda com nomes e que o caminho por nome nunca alcança. A hipótese não foi refutada —
ficou **sem chance de aparecer**, que é coisa diferente e que vale registrar como tal.

### 13.1 e 13.2 — os dois caminhos, e o que cada um custa (S-72, S-73)

| | por nome | por posição |
|---|---|---|
| alcança | os 12,6% com jogadores na legenda | **todo diagrama** |
| casou, no livro medido | 61 de 1.408 | **761 posições de 1.404 (54,2%)** |
| preenchível pela regra dos ≤5 | 61 | **581 diagramas** |
| custo | ~150 s, um processo | **104 min** em dez |
| onde | botão da Galeria | `cvoff-games --positions` |

**O custo é por varredura, não por livro** — o conjunto-alvo cabe na memória sejam 1.400
posições ou 40 mil, então `--all` varre os 32 livros pelo preço de um. É a mesma economia que a
S-61 encontrou na abertura do PDF, num lugar onde ela vale 32×.

**E os dois caminhos se conferem.** Nos 61 diagramas que ambos alcançam: **61/61 no número do
lance e 61/61 na partida**. Duas rotas sem código em comum chegando ao mesmo lugar vale mais
que qualquer teste escrito à mão.

### 13.3 — quatro livros medidos, e a ressalva que caiu

Eu havia registrado que o 54,2% do Dvoretsky era "o melhor caso possível" e que outro gênero
cairia muito. Medido em mais três livros, na mesma passada:

| livro | diagramas | casaram | % | com partida única |
|---|---|---|---|---|
| `Secrets of Chess Training` (treino, partidas reais) | 1.408 | 764 | **54,3%** | 490 |
| `400 Quebra-cabeças de Estratégia` (pt-BR, outro autor) | 1.120 | 589 | **52,6%** | 537 |
| `1001 Winning Chess Sacrifices` (táticas, 1955) | 1.003 | 288 | **28,7%** | 241 |
| `Niemeijer — Zwarte Magie` (problemas compostos) | 32 | **0** | 0% | 0 |
| **total** | **3.563** | **1.641** | **46,1%** | |

**A ressalva caiu pela metade.** O `400 Quebra-cabeças` não tem nada em comum com o Dvoretsky
— outro autor, outra editora, outro idioma, estratégia em vez de treino — e ficou a 1,7 ponto
dele. Dois livros independentes na mesma faixa não são "o melhor caso possível".

O que cai é o **Reinfeld**, e a hipótese mais provável não é gênero: é **idade**. São táticas
de partidas de até 1955, muitas obscuras, e uma base montada a partir de bancos comerciais
cobre mal o que não virou clássico. Isso é testável — comparar a distribuição de anos dos
casamentos com a dos diagramas — e não foi testado.

O **Niemeijer deu zero**, como previsto, mas por **duas causas somadas**: são problemas
compostos (não são posições de partida) e o modelo não lê o livro (confiança mínima mediana
0,251, zero acima do gate). O experimento não separa as duas, e por isso ele não prova o que eu
queria que provasse — serve como o caso extremo de que **a base não resgata OCR ruim**, o que
até aqui eu vinha afirmando sem medir.

**O que a Fase 13 entregou de trabalho poupado**, somando os quatro: **11.746 campos
preenchidos em 1.409 diagramas**, e 1.641 leituras confirmadas — que é o número que esvazia a
fila de revisão (13.4).

### 13.4 e 13.5 — o que a confirmação vale além do preenchimento (S-74, S-75)

A fila da S-22 ordena por **estimativa de erro**; um casamento é a **resposta**. Confirmado, o
diagrama não vira item — e o que sobrevive é só o que a confirmação não responde: de quem é a
vez, porque a mesma colocação aparece com brancas e com pretas em partidas diferentes.

Isso mudou o desenho da S-72: **confirmar e preencher viraram coisas diferentes**. Uma posição
em 300 partidas não diz qual delas é (não preenche), mas diz que a leitura está certa
(confirma). Antes, o casamento ambíguo era descartado inteiro — e ele é 232 dos 1.641.

Na tela, a quarta cor: violeta para "não precisa", entre o âmbar de "lido" e o verde de
"salvo". Como o verde, vem do disco, então aparece ao abrir um livro casado ontem, antes de
qualquer OCR — no `400 Quebra-cabeças` isso é metade da página respondida sem uma leitura.

### O defeito de sequenciamento que custou 104 minutos

A varredura dos quatro livros rodou com o código **de antes** da correção de procedência, e os
11.746 campos foram gravados sem `filled_fields` e sem `confirmed_from`. O PGN teria dito
`[SideToMoveSource "manual"]` para 1.409 diagramas que ninguém conferiu, e a S-74 não tiraria
ninguém da fila.

A correção não foi só refazer: `cvoff-games` ganhou `--save-matches` / `--from-matches`. Nada
na varredura depende do que se faz com o resultado dela, e separar as duas coisas faz refazer
custar segundos em vez de 104 minutos — inclusive para mudar o `--max-games` ou a regra de
preenchimento.

### Os dois defeitos que só a execução mostrou

Nenhum apareceu em teste, e os dois viraram teste depois:

- **`tell()` em modo texto não é byte, é um *cookie* opaco** com o estado do decodificador.
  Comparado contra o fim do pedaço, encerrava o laço cedo: **5 partidas lidas de 2.000**, em
  silêncio — o modo de falha caro deste projeto, de novo. Um arquivo de três partidas não pega
  isso; o teste de regressão usa 300.
- **`spawn` reimporta o `__main__` do pai** (S-26). Chamado de um script sem guarda, cada filho
  reexecutava o script e criava mais filhos — travou a máquina aqui. A guarda agora é um
  marcador no ambiente, posto **antes** de o `Pool` existir.

---

## Sequenciamento sugerido

Se houver duas semanas:

| dia | itens | por que nesta ordem | estado |
|---|---|---|---|
| 0 | **S-56** (splits) + S-57 + S-58 + S-59 + S-60 | são defeitos, não melhorias; a S-56 sozinha devolve 45 amostras ao treino | ✅ |
| 1 | S-37 (ambiente) + S-41 (conjunto de campo) | sem os dois, nada do que vem depois é verificável | ✅ |
| 2 | S-38a (o refino não pode piorar) | o que a S-41 revelou na primeira medição | ✅ |
| — | ~~S-38b (`BoardVerifier`)~~ | **adiado por medição**: 1 falso positivo a ganhar, 35 verdadeiros a arriscar | ⏸ |
| 3 | ~~S-39 (`BoardNormalizer`)~~ | **medido, nada entrou ligado**: campo plano e CLAHE são no-op (o `ColorJitter` já ensinou), e a trama não é separável da peça por escala | ✅ medido |
| 4 | S-40 (aumento dirigido) — **implementado** | módulo, testes e `--augment`; desligado por padrão | ✅ código |
| 5 | ~~S-40 — **medir**~~ | **medido: não entra.** `mhsp` dá 0,7368, idêntico ao controle retreinado. O Euwe p25 sobe 60× (0,002 → 0,123) e continua 6,5× abaixo do gate | ✅ medido |
| 6 | **medir contra o conjunto de campo** | feito: a taxa de exportação **não** saiu de 0,7368, e a Fase 7 fica a 5 diagramas do alvo | ✅ |
| 6b | **S-61** (custo da varredura) | as duas ineficiências: −24,5% na inferência e uma abertura por varredura em vez de três por página | ✅ medido |
| — | ~~S-44 (glifo `W`/`B`)~~ | **medido: 0 ocorrências em 380 diagramas com texto.** O único livro que tem o marcador não tem camada de texto | ⏸ |
| 7–9 | **S-42 + S-43** (motor de OCR + faixa de legenda) | com a S-44 e a S-45 fora, é **o** item da Fase 8: os 7 livros sem texto e o `LAS BLANCAS JUEGAN PRIMERO` | ✅ código |
| 9b | S-42/S-43 — **instalar o extra e medir** | feito. E a medição achou o defeito: a faixa de escopo lia a metade de cima dos glifos. Corrigida, o `Reinfeld` sai de 40 assumidos em 41 para **0** | ✅ medido |
| 9c | **`cvoff-sides`** | o critério de saída da Fase 8 não tinha instrumento. Agora tem, e a Fase 8 fecha | ✅ |
| — | ~~S-45 (coordenadas)~~ | **medido: 13,7% de cobertura, 48/52 num livro que já lê a 1,000, e 0 diagramas do ponto de vista das pretas** | ⏸ |
| 10a | **S-51 (`LabelStore`)** | o `labels.csv` passa a ter uma porta, e o campo novo da S-52 tem onde entrar | ✅ |
| 10b | **S-52, metade: `corrected_by`** | a coluna sai de 0 de 3.313 preenchidas; a outra metade (hash perceptual) precisa de horas de CPU | ✅ metade |
| 10c | **S-52, metade: procedência por hash perceptual** | `provenance.py` + `cvoff-provenance`; validado contra verdade de referência (12/12 na página certa) | ✅ código |
| 10d | S-52 — **indexar o acervo e medir** | `cvoff-provenance --build` nos 32 PDFs (~12 mil páginas). Horas de CPU; é a sua decisão de quando | ← **a única pendência que sobrou** |
| 11–14 | **S-47 a S-50** (as extrações) | por último de propósito: refatorar antes de medir é refatorar no escuro | ✅ |
| 15 | **S-53** (`ttkbootstrap` + gatilhos de Qt) | a única mudança de UI que não fecha porta nenhuma | ✅ |
| 16 | **S-54** (o Streamlit) | a pior saída era continuar sem escolher. Aposentado | ✅ |
| 17 | **S-55** (empacotamento Windows) | é o que transforma "meu projeto" em "programa que outra pessoa usa" | ✅ |
| 18 | **S-63** (higiene do dataset) | as duas ações que a auditoria só relatava, e o teto de redundância | ✅ |
| 19 | ~~**S-62** (modelo por tabuleiro)~~ | **implementada e reprovada nos próprios critérios**: o reparo do decodificador sobe em vez de cair pela metade | ✅ medido |

E o que veio **depois** do fechamento, que não estava em plano nenhum porque saiu de uso e não
de varredura:

| dia | itens | por que | estado |
|---|---|---|---|
| — | **S-66** (segunda opinião local) | o `Protocol` da S-32 cobrado: 4,5 casas para olhar em vez de 64, sem nada sair da máquina | ✅ |
| — | **S-67** (Galeria) | a anotação de exportação não tinha onde morar | ✅ |
| — | **S-68 + S-69** (diagramas clicáveis; o WebView2 sai) | o detector já sabia onde eles estão desde a Fase 2, e o resultado nunca chegava à tela | ✅ |
| — | **S-70** (roda, arrasto, zoom ancorado) | devolve no canvas do projeto o que a aba do Edge levou embora | ✅ |
| — | **S-71** (lance e o verde de "já salvo") | "onde eu parei neste livro?", respondido pelo CSV antes de qualquer OCR | ✅ |
| — | **S-72** (base por nome) | a legenda dá o nome e cala sobre o resto: 12,6% com jogadores, 1,1% com ano | ✅ medido |
| — | **S-73** (base por posição) | 54,2% das posições do livro estão numa partida real, e o custo é por varredura e não por livro | ✅ medido |
| — | **medir um segundo livro** | o livro medido é do Dvoretsky, feito de partidas reais — é o melhor caso possível | ← pendente |

A ordem tem uma regra: **medição antes de mudança, e mudança antes de refatoração.** É a
mesma que as Fases 1 a 6 seguiram, e é o que permitiu à Fase 5 descartar TTA, pesos de classe
e temperatura calibrada com número em vez de opinião.

---

## Onde isto para, e o que continua esperando você

**Atualizado em 2026-08-13.** As seis fases estão fechadas no sentido de que **todos os itens
da spec têm destino decidido**: implementados, medidos-e-não-entram, ou adiados por medição.
Nenhum ficou por falta de tempo.

| fase | estado |
|---|---|
| **7** — ler o acervo que existe | código completo. **Critério de saída não atingido**: 0,7368 contra 0,85, e a 7.7 explica por que a métrica não consegue mais julgar |
| **8** — OCR de verdade | **fechada**. 19 de 32 livros com procedência ≠ `default`, 14 deles por texto ou OCR — contra 10 antes do motor |
| **9** e **10** | fechadas desde 2026-08-09, mais a S-66 e a S-67 documentadas depois (10.7, 10.8) |
| **11** — o modelo | **feita e reprovada nos próprios critérios**. Ver 11.1 |
| **12** — a página como lugar de trabalho | **fechada em 2026-08-12** (S-68 a S-71). Não estava em plano nenhum: saiu de uso |
| **13** — a base de partidas | **fechada em 2026-08-13** (S-72 a S-75). Quatro livros medidos: 1.641 leituras confirmadas e 11.746 campos preenchidos |

### Os quatro itens que a medição desaconselhou

Nenhum foi adiado por preguiça. Os quatro têm número:

| item | o que a medição disse |
|---|---|
| **S-38b** `BoardVerifier` | 1 falso positivo a ganhar contra 35 verdadeiros a arriscar |
| **S-44** glifo `W`/`B` | 0 ocorrências em 380 diagramas com camada de texto |
| **S-45** coordenadas | 13,7% de cobertura, e 0 diagramas do ponto de vista das pretas |
| **S-46** solução como validador | 21,3% dos diagramas têm algo com forma de lance perto, e só **13,7% desses** são legais na posição lida — o texto vizinho é a continuação da partida, não a solução |

### O que sobrou, e não é código

| pendência | o que falta | custo |
|---|---|---|
| **Crescer o conjunto de campo** | a S-41 planejava 60 páginas e entregou 15. **É a pendência que destrava as outras**: quatro itens desta fase foram julgados por uma métrica que hoje não tem resolução para julgá-los | ~2 h suas |
| **Anotar os livros hachurados** | os 8 diagramas barrados estão todos abaixo de 0,43 — falha de domínio, não de margem | tempo seu |
| **S-52** (procedência) | `cvoff-provenance --build` nos 32 PDFs, depois `--match` | horas de CPU |
| **Retreinar produção com `mhsp`** | `models/s40_mhsp_16ep.pt` domina o controle em tudo que é mensurável hoje. A troca do padrão de `AugmentConfig()` espera o item 1 | decisão sua |

### O que este dia mediu, e que vale mais que os vereditos

Três coisas que só apareceram por medir, e que valem para quem continuar:

1. **A taxa de exportação é uma catraca que só desce.** Seis variantes de modelo, todas em 27
   ou 28 de 38, e nenhuma ganhou um diagrama. A distribuição de confiança é bimodal com a
   vizinhança do gate vazia (7.7).
2. **Um motor de OCR não avisa quando recebe meia linha.** A faixa de escopo de 7% cortava o
   cabeçalho ao meio e o RapidOCR devolvia `TIEAANDDIVEDA` com **0,71 de confiança**. Nenhum
   limiar razoável pegaria isso; o que consertou foi 5 pontos percentuais de altura (8.5).
3. **Dado bateu arquitetura, de novo.** A métrica de aceite da S-62 foi mais bem satisfeita
   pelo aumento de dados da S-40 (−40% de reparo) do que pelos dois degraus arquiteturais que
   a S-62 propôs (−33% e +27%).

---

## Riscos e decisões que precisam do dono do projeto

| risco / decisão | observação |
|---|---|
| ~~**45 amostras fora do treino**~~ | **Resolvido em 2026-08-11.** O `cvoff-train` atribuiu as 39 que faltavam: 29 para `train`, 7 para `val`, 3 para `test`. O backup do arquivo anterior está em `data/splits.csv.bak-s40`. |
| ~~**O `.venv` aponta para um caminho que não existe**~~ | Resolvido. O `pythonpath` do `pytest` (S-37) é a guarda contra a repetição. |
| **`data/labels.csv` e `data/splits.csv` estão modificados e não commitados** | O `labels.csv` perdeu 5 linhas para a quarentena (S-63) e o `splits.csv` ganhou as 39 atribuições. Os dois têm backup datado ao lado. Commitar antes de treinar de novo. |
| **Dependência de OCR muda a promessa de offline** | **Decidido: RapidOCR instalado em 2026-08-11**, e a promessa continua de pé — 14,2 MiB, modelos no wheel, nada baixado na primeira execução (verificado). O EasyOCR continua opt-in e continua baixando ~100 MB; se um dia for a preferência, o README precisa mudar de texto. |
| **Anotar 60 páginas à mão custa tempo seu** | Subiu de "vale a pena" para **a pendência que destrava as outras**. Com 38 diagramas e zero na faixa 0,6–0,8, a taxa de exportação não distingue dois modelos — e quatro itens desta fase foram julgados por ela (7.7). Estimativa: ~2 h. |
| **Recuperar procedência (S-51) pode não casar tudo** | O casamento é por hash perceptual contra 27 PDFs. Amostras vindas de imagem local ou de PDF que saiu do acervo não casam. Espera-se recuperação parcial; o item precisa reportar a taxa, não prometer 100%. |
| **`ArchConfig` não versiona o pré-processamento** | Continua valendo para a S-39, que não entrou. A S-62 **estendeu** a chave para o que ela acrescentou (`...-coords`, `...-board`), então o defeito que a S-27 corrigiu não voltou por esse caminho. |
| **Reescrever a UI em Qt** | ~3–4 semanas e licença LGPL. A recomendação é **não fazer agora** e amarrar a decisão a um gatilho observável (S-53). |
| **Sem GPU** | Continua valendo: `torch 2.10.0+cpu`, 12 CPUs, época em ~9 min com a máquina livre. Medido em 2026-08-11: o aumento dirigido de fato não muda o custo por época, e a grade inteira desta análise (9 treinos) custou ~9 h de CPU. |
