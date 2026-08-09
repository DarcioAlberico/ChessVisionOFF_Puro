# Roadmap — Fases 7 a 11

Continuação de [ROADMAP.md](ROADMAP.md), que fecha na Fase 6. Especificação detalhada em
[SPEC_FASE7.md](SPEC_FASE7.md) (S-37 a S-63). Para o *como* de hoje,
[ARCHITECTURE.md](ARCHITECTURE.md); para os números de referência,
[BASELINE.md](BASELINE.md);
para o que foi medido nesta fase — **inclusive o que não entrou** —
[EXPERIMENTS_FASE7.md](EXPERIMENTS_FASE7.md).

**Data da análise:** 2026-08-09 · **Ramo:** `fase-5-modelo-desempenho` · **Commit base:** `ee308dd`

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

**Número a bater, medido no conjunto de campo (S-41, 2026-08-09): taxa de exportação
0,6842 — 26 de 38 diagramas.** Alvo da Fase 7: **≥ 0,85**, sem que a precisão de detecção
caia abaixo dos 0,9722 de hoje.

A estimativa anterior deste roadmap era 83,2%, e estava otimista pelo motivo que o item
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

### 8.3 — As coordenadas do tabuleiro fecham a pendência da S-13

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

### 8.4 — O critério de saída da Fase 8

Hoje, **3 dos 27 livros** resolvem o lado a jogar por texto e **118 de 3.195 rótulos** por
legalidade; o resto é o padrão "brancas". A Fase 8 fecha quando a procedência
`[SideToMoveSource]` deixa de ser `default` em pelo menos **12 dos 27 livros** — e quando
cada um dos novos casos é rastreável ao trecho que decidiu, como a S-16 já faz com
`side_to_move_evidence`.

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
| 5 | S-40 — **medir** (~110 min de CPU) | a máquina estava em uso; é a sua decisão de quando | ← próximo |
| 6 | **medir contra o conjunto de campo** | fim da Fase 7: a taxa de exportação saiu de 0,6842 ou não | |
| 7 | S-44 (glifo `W`/`B` e número) | não depende de OCR; resolve o Gallagher e a convenção Batsford inteira |
| 8–9 | S-42 + S-43 (motor de OCR + faixa de legenda) | resolve o `LAS BLANCAS JUEGAN PRIMERO` e os 7 livros sem texto |
| 10 | S-45 (coordenadas) | fecha a pendência da S-13, se a cobertura medida justificar |
| 11 | S-51 (procedência) + S-52 (`corrected_by`) | destrava o split por livro, que melhora toda medição futura |
| 12–14 | S-46 a S-50 (as extrações) | por último de propósito: refatorar antes de medir é refatorar no escuro |

A ordem tem uma regra: **medição antes de mudança, e mudança antes de refatoração.** É a
mesma que as Fases 1 a 6 seguiram, e é o que permitiu à Fase 5 descartar TTA, pesos de classe
e temperatura calibrada com número em vez de opinião.

---

## Riscos e decisões que precisam do dono do projeto

| risco / decisão | observação |
|---|---|
| **45 amostras fora do treino** | Consertável em minutos (rodar `ensure_splits`). Mas a atribuição de split é irreversível na prática — uma amostra que cair no `test` fica lá para sempre, por desenho da S-07. Rodar às cegas move 10% delas para um conjunto de teste que você nunca poderá usar como treino. Vale conferir a lista antes. |
| **O `.venv` aponta para um caminho que não existe** | Consertável em 30 s (`uv sync --extra dev`). O item S-37 é a **guarda** contra a repetição, não o conserto. |
| **`data/labels.csv` está modificado e não commitado** | 7 linhas novas na árvore de trabalho. As mesmas 45 amostras da S-56. Commitar antes de mexer em split. |
| **Dependência de OCR muda a promessa de offline** | RapidOCR mantém a promessa (modelos no wheel). EasyOCR não (baixa na 1ª execução). Se a preferência for EasyOCR, o README precisa mudar de texto — a decisão é sua. |
| **Anotar 60 páginas à mão custa tempo seu** | É o único jeito de ter recall. Estimativa: ~2 h. Sem isso, a Fase 7 não tem critério de saída verificável e vira ajuste de constante no escuro. |
| **Recuperar procedência (S-51) pode não casar tudo** | O casamento é por hash perceptual contra 27 PDFs. Amostras vindas de imagem local ou de PDF que saiu do acervo não casam. Espera-se recuperação parcial; o item precisa reportar a taxa, não prometer 100%. |
| **`ArchConfig` não versiona o pré-processamento** | Se a S-39 entrar, um checkpoint treinado com normalização e outro sem passam a ser incompatíveis, e `arch_version` não distingue. A S-39 precisa estender a chave — do contrário volta em silêncio o defeito que a S-27 corrigiu. |
| **Reescrever a UI em Qt** | ~3–4 semanas e licença LGPL. A recomendação é **não fazer agora** e amarrar a decisão a um gatilho observável (S-53). |
| **Sem GPU** | Continua valendo o da Fase 5: `torch 2.10.0+cpu`, 12 CPUs, época em ~9 min. Todo número de tempo aqui é de CPU. O aumento dirigido da S-40 não muda o custo por época; o retreino, sim, porque exige `--fresh`. |
