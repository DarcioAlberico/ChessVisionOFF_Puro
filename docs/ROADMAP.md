# Roadmap — ChessVisionOFF_Puro

Base: [ANALISE.md](ANALISE.md). Detalhes de implementação: [SPEC.md](SPEC.md). Números medidos: [BASELINE.md](BASELINE.md).

Estimativas em dias de trabalho focado de uma pessoa. As fases são sequenciais por dependência: cada uma depende de algo que a anterior estabelece.

---

## Visão geral

```
Fase 0  Higienização do repositório          1–2 d   ▸ desbloqueia tudo, custo cresce se atrasar
Fase 1  Verdade e medição                    3–5 d   ▸ sem isso "melhorou" é indemonstrável
Fase 2  Precisão do OCR                      5–8 d   ▸ maior ganho de qualidade do projeto
Fase 3  Semântica: lado a jogar e metadados  4–6 d   ▸ concluída — metade dos exercícios saía errada
Fase 4  Produtividade humana                 5–8 d   ▸ ataca o gargalo real (tempo do usuário)
Fase 5  Modelo e desempenho                  4–6 d   ▸ só faz sentido depois da Fase 1
Fase 6  Consolidação do produto              5–8 d   ▸ unificação, i18n, empacotamento
```

Total: ~27 a 43 dias. As Fases 0 a 2 (9 a 15 dias) entregam a maior parte do valor.

---

## Fase 0 — Higienização do repositório ✅ concluída (2026-07-25)

**Por que primeiro:** é o único item cujo custo aumenta com o tempo. Depois do primeiro commit, 3,3 GB de PNGs e PDFs ficam no histórico do git para sempre.

| # | Entrega | Ref. spec | Status |
|---|---|---|---|
| 0.1 | `.gitignore` cobrindo `data/samples/`, `PDF/`, `PGN/`, `models/*.pt`, `Python-Easy-Chess-GUI-master/`, lixo de raiz | S-01 | ✅ |
| 0.2 | Remover `Python-Easy-Chess-GUI-master/`, `pecg_*` da árvore | S-01 | ✅ removidos do disco |
| 0.3 | Commit inicial com árvore limpa | S-01 | ✅ 41 arquivos, 0,57 MB |
| 0.4 | `pyproject.toml`: `[build-system]`, `[tool.setuptools]` src-layout, `[project.scripts]`, deps de dev, remover markers `<3.9` mortos | S-02 | ✅ |
| 0.5 | Instalação editável funcionando; remover as gambiarras de `sys.path` | S-02 | ✅ 5 removidas |
| 0.6 | `ruff` + `mypy` configurados; CI no GitHub Actions rodando lint + testes | S-03 | ✅ |
| 0.7 | `logging` no lugar de `print`; strings em pt-BR | S-04 | ✅ parcial (ver abaixo) |

**Critério de saída:** atingido. `uv sync --extra dev` → `ruff` limpo, `mypy` limpo em 17 arquivos, `pytest` 8/8, CI verde.

### O que a Fase 0 encontrou de quebrado

Três bugs latentes que as ferramentas expuseram, corrigidos no mesmo commit:

1. **`dataset.py`** — uma célula FEN vazia no `labels.csv` derrubava todo o carregamento com `AttributeError: 'float' object has no attribute 'strip'`. O pandas entrega `NaN` (float) e `is_valid_fen` só capturava `ValueError`. Reproduzido e corrigido.
2. **`pdf_io.render_pdf_page`** — devolvia view somente-leitura sobre o buffer do `Pixmap`; escrita in-place levantava `ValueError`. Agora devolve array próprio e gravável.
3. **`_load_checkpoint`** — duplicado idêntico em `inference.py` e `training.py`; consolidado em `checkpoint.py` com validação de formato.

Efeito colateral útil do gate de plataforma (`sys_platform == 'win32'` em `pythonnet`/`pywebview`): o `uv.lock` perdeu 6 pacotes `pyobjc-*` de macOS **sem alterar nenhuma versão já resolvida**.

### Pendências conhecidas da Fase 0

- **0.7 (acentuação)** — o `logging` está feito e os `except Exception: pass` silenciosos foram eliminados, mas as strings de UI seguem sem acento ("posicao", "Configuracao"). A centralização em `ui/strings.py` depende da decomposição do Tkinter (S-31, Fase 6); acentuar antes disso criaria conflito com aquela refatoração.
- **`requires-python`** — mantido em `==3.10.*`. Relaxar para `>=3.10,<3.14` permitiria matriz de CI, mas exigiria re-resolver o lock; deixado para quando houver motivo.

---

## Fase 1 — Verdade e medição ✅ concluída (2026-07-25)

**Por que agora:** hoje não existe conjunto de teste. Qualquer mudança da Fase 2 em diante seria adivinhação.

| # | Entrega | Ref. spec | Status |
|---|---|---|---|
| 1.1 | `fen_utils.is_legal_position()` usando `Board.status()`; `is_valid_fen` passa a ser explicitamente sintática | S-05 | ✅ `check_position` devolve os problemas em texto |
| 1.2 | CLI de auditoria: relatório de rótulos ilegais, duplicatas, imagens órfãs | S-06 | ✅ `cvoff-audit` |
| 1.3 | Sanear os 100 rótulos ilegais (49 corrigir/remover; 51 `OPPOSITE_CHECK` → marcar lado a jogar preto) | S-06 | ✅ 0 ilegais em 3.195 linhas |
| 1.4 | Deduplicação por hash perceptual da imagem | S-06 | ✅ resolvida por agrupamento (ver abaixo) |
| 1.5 | Split treino/validação/teste **persistido em arquivo**, estável sob crescimento do dataset | S-07 | ✅ 2.569 / 306 / 320 |
| 1.6 | Harness de avaliação: acurácia por casa, **exata por tabuleiro**, por classe, matriz de confusão, taxa de posição ilegal | S-08 | ✅ `cvoff-eval` |
| 1.7 | Baseline registrado em `docs/BASELINE.md` (número honesto, em conjunto de teste) | S-08 | ✅ [BASELINE.md](BASELINE.md) |
| 1.8 | Testes de `fen_utils`, `dataset`, `inference`; fixtures versionados; teste de regressão de acurácia | S-09 | ⚠ parcial (ver abaixo) |

**Critério de saída:** atingido. `cvoff-eval --split test` imprime acurácia exata por tabuleiro; `cvoff-audit` reporta 0 rótulos ilegais; baseline medido com modelo que nunca viu o conjunto de teste.

### Decisões e desvios da Fase 1

- **1.2 mora no pacote, não em `tools/`.** O plano dizia `tools/audit_dataset.py`. Virou `cvoff-audit` (`cli/audit.py` + `audit.py`) porque a lógica de auditoria é testável e reutilizável — `find_duplicate_groups` é usada pelo `splits.py`. Um script solto em `tools/` não seria importável nem entraria no `mypy`. O mesmo vale para `cvoff-eval` no lugar de `tools/evaluate.py`.
- **1.4 — os redundantes ficaram no dataset, de propósito.** A detecção acha 234 amostras redundantes em 220 grupos (~7%). Elas **não** foram removidas: o problema real não era ocupar espaço, era a mesma posição cair em treino *e* em teste. O `splits.py` resolve isso na raiz atribuindo split por **grupo**, não por arquivo. Verificado: **0 dos 220 grupos** está espalhado entre splits. Remover as cópias jogaria fora variações de recorte que são aumento de dados legítimo. Se um dia atrapalharem, `cvoff-audit --dedupe` aplica a remoção.

### Pendências conhecidas da Fase 1

- **1.8 (fixtures e regressão)** — os testes de `fen_utils`, `dataset`, `inference`, `decode`, `splits` e `audit` existem e rodam sem dados. Falta o **teste de regressão de acurácia**, que depende de fixtures versionados (S-09): hoje `data/samples/` está fora do git, então um teste de acurácia pularia na CI e daria falsa sensação de cobertura. O baseline em `docs/BASELINE.md` cumpre o papel de trava manual até lá.
- **O checkpoint não guarda com que `val_loss` foi salvo.** Consequência prática, encontrada ao retomar o treino do baseline: retomar zera o controle de melhor época e a primeira época sobrescreve o arquivo mesmo se for pior. Hoje há um `warning` avisando; a correção é gravar metadados no checkpoint (item 5.3).

---

## Fase 2 — Precisão do OCR (5–8 dias) — em andamento

**Por que é o núcleo:** ganho de precisão sem retreinar o modelo. Todos os itens exploram informação que já existe e está sendo descartada.

| # | Entrega | Ref. spec | Status |
|---|---|---|---|
| 2.1 | `predict_board()` retorna distribuição por casa, não só o argmax | S-10 | ✅ `BoardPrediction.probs` |
| 2.2 | Confiança = mínimo/entropia por casa em vez de média; `min_square_confidence` no `DiagramPosition` | S-10 | ✅ mínimo, entropia e `uncertain_squares` |
| 2.3 | **Decodificação com restrições**: busca sobre as probabilidades por casa sujeita às regras (1 rei de cada cor, ≤8 peões, nada na 1ª/8ª fila, ≤16 peças) | S-11 | ✅ `decode.py` |
| 2.4 | Extração de diagrama por **imagem embutida** do PDF (`page.get_image_info`) com recorte da moldura/legenda | S-12 | ✅ `detection/embedded.py` |
| 2.5 | Detector híbrido: candidatos embutidos + contorno, desempate por legalidade e concordância | S-12 | ✅ `detection/hybrid.py`, com desempate diferente (ver abaixo) |
| 2.6 | Auto-orientação por tentativa (0°/180°) escolhendo a mais plausível; `rotate_180` deixa de ser global | S-13 | ✅ `predict_with_orientation` |
| 2.7 | Unificar `reading_order` entre GUI e export (padrão único, configurável) | S-14 | ✅ `DEFAULT_READING_ORDER` + header `[ReadingOrder]` |
| 2.8 | Gate de exportação: posições ilegais ou de baixa confiança vão para `*.review.pgn` separado | S-15 | ✅ `ExportReport` |

**Critério de saída:** zero posições ilegais no PGN exportado dos 27 PDFs; acurácia exata por tabuleiro no conjunto de teste ≥ baseline + margem medida; erros K↔Q do `1937 Kemeri.pdf` corrigidos.

**Baseline a bater:** 0,9906 de acurácia exata por tabuleiro no split `test` — ver [BASELINE.md](BASELINE.md). Atenção ao que esse número não é: com 3 erros em 320 tabuleiros, meio ponto de diferença é ruído, e a acurácia num PDF nunca revisado é muito mais baixa (46 dos 47 tabuleiros do Kemeri ficam abaixo do limiar de aceite).

### O que a primeira metade da Fase 2 mediu

Números completos em [BASELINE.md](BASELINE.md). O resumo:

- **A média das confianças era o número errado.** No conjunto de teste ela fica em 0,999 quando o tabuleiro está exato e ~0,75 nas casas erradas — mas 77% das casas são vazias e triviais, então a média do tabuleiro fica ~0,97 *mesmo com erro*. O mínimo por casa separa muito melhor: AUC 0,919 contra 0,905 da média. É por isso que a barra de status e os headers do PGN passaram a mostrar o mínimo primeiro.
- **A decodificação com restrições não muda nada no conjunto de teste — e muda muito no PDF.** No teste o argmax já produz 0 posições ilegais em 320 tabuleiros, então a busca nunca é acionada: o conjunto de teste é limpo demais para medir a S-11. Em `1937 Kemeri.pdf` (páginas 10–69, 47 tabuleiros), a ilegalidade real cai de **16 para 2**. Em nenhuma medição uma casa que o argmax acertava foi estragada.
- **2.7 era um bug de configuração, não de algoritmo.** `detect_boards` tinha `"row"` por padrão e a exportação passava `"column"`: numa página de duas colunas o `[Diagram "2"]` do PGN apontava para outra posição que a da tela. Os frontends nunca passavam o parâmetro, então herdavam o padrão errado.

### 2.4 e 2.5 — o levantamento mudou o peso do item, e a arbitragem mudou de forma

**Primeiro, quantos livros isso alcança.** A S-12 mede três PDFs e conclui que o diagrama vem
como imagem embutida. Levantados os 27, amostrando 12 páginas do meio de cada:

| o que a página tem | livros | a imagem embutida serve? |
|---|---|---|
| imagem quadrada por diagrama | **10** | sim |
| a página inteira é um scan | **12** | não: uma imagem só, cobrindo tudo |
| diagrama vetorial/fonte | 2 | não: não há imagem |
| misto | 3 | às vezes |

Ou seja, o caminho por contorno **não** é fallback para caso exótico, é a maioria do acervo.
Isso não derruba o item — os 10 incluem justamente os piores para o contorno (`1937 Kemeri`,
`AAGAARD`, `Schiller`, `Karpov`) — mas muda o que precisa ser robusto: o híbrido tem de sair
idêntico ao detector atual nos 14 livros sem imagem embutida, e sai (verificado).

**Segundo, as duas fontes não competem pela mesma coisa.** A S-12 propõe, quando elas
discordam, ler as duas e arbitrar por legalidade. Medido em 10 páginas de cada livro:

| livro | embutida crua | embutida + warp | contorno puro |
|---|---|---|---|
| `1937 Kemeri` | 0,478 / 0 ilegais | **0,538 / 0** | 0,431 / **2 ilegais** |
| `Schiller` | 0,137 / 0 | **0,360 / 0** | 0,257 / 0 |
| `Karpov 1` | 0,906 / 0 | **0,962** / 1 | 0,948 / 0 |
| `Euwe Band 1-2` | 0,010 / 1 | **0,025 / 1** | 0,014 / 2 |

O bbox embutido é melhor em **localizar** (sabe o que é diagrama e o que é figura); o warp por
contorno é melhor em **alinhar** (acha os cantos exatos, e recortar o bbox cru deixa a grade
8×8 fora de registro). Então não há o que arbitrar: a composição certa é **uma por candidato**
— bbox para saber onde olhar, contorno rodado *dentro* dele para alinhar. Sai melhor que as
duas fontes isoladas em 4 dos 5 livros, empata no quinto, e não paga inferência dupla.

**Terceiro, a tensão que não tem solução limpa.** Duas medições se contradizem:

- Unir as fontes cegamente traz de volta o falso positivo que a embutida evitava (Kemeri: a
  figura que rende `8/8/8/8/8/8/8/8` volta pela porta do contorno).
- Mas tratar a lista embutida como completa **perde diagrama de verdade**: no `Schiller` e no
  `Karpov`, 4 por livro que o contorno acha não estão declarados como imagem.

Tentei um prior de tamanho para separar os dois casos; ele recupera o Schiller e o Karpov mas
não pega o falso positivo do Kemeri, que tem tamanho parecido com os diagramas reais. Diante
disso escolhi **recall**: diagrama perdido na detecção desaparece em silêncio e nada
downstream recupera, enquanto leitura ilegal é exatamente o que o gate da S-15 rejeita — e de
fato os 2 do Kemeri aparecem como "2 rejeitados" no export. Precisão é problema do gate,
recall é problema do detector.

Resultado no acervo (9 livros dos três grupos, 10 páginas cada): **281 diagramas detectados
contra 281** do detector atual, mesmo número de leituras-lixo, e confiança mínima média de
0,691 para **0,716**. No produto, o export das páginas 10–69 do Kemeri vai de **1 diagrama
aceito para 5**; o Reinfeld segue em 40 de 40, sem regressão.

**Consequência de projeto:** GUI e exportação passam a usar o mesmo
`detect_diagrams_in_pdf_page`. Deixar a GUI no contorno enquanto o export usa o híbrido
recriaria, no recorte, exatamente o bug que a S-14 corrigiu na numeração.

### 2.6 — o que a medição mudou no plano, e a armadilha que ela quase deixou passar

A S-13 propunha decidir a orientação por legalidade em primeiro lugar, `min_confidence` em
segundo e prior estrutural (peões **e reis**) como desempate leve. Medido nos 320 tabuleiros
do split de teste, cada sinal isolado:

| sinal | aponta certo | aponta errado | empata |
|---|---|---|---|
| legalidade | 52 | 0 | **268** |
| `min_confidence` | **320** | 0 | 0 |
| prior de peões | 264 | 9 | 47 |
| prior de reis | 267 | **37** | 16 |

A legalidade **não** pode ser o critério dominante: girar a posição 180° manda peão branco da
fila `r` para a `9-r`, e 2..7 vira 7..2 — continua legal. Ela cala em 84% dos casos, embora
nunca erre, então ficou como primeiro filtro. O prior de **reis** erra 37 vezes e ficou fora.

**A armadilha.** Com essa medição o critério de aceite passou de primeira: girando o conjunto
de teste inteiro, 0,9906 no original e 0,9906 no girado. Mas rodar num PDF de verdade mostrou
regressão: 8 dos 47 diagramas do Kemeri giraram sem motivo. Duas páginas cuja leitura de pé
era uma posição de meio-jogo claramente correta (`Q3brk1/pp2q1p1/...`, peões +3,5) tinham
margem de confiança de **0,001** e **0,019**.

A razão: no split de teste a orientação certa tem confiança ~1,0 e a girada ~0,07, então a
margem é enorme. Em página difícil as duas caem para ~0,04 e a margem vira ruído. O
`min_confidence` mede a *aparência* das peças e some junto com ela; o prior de peões mede a
*estrutura da posição* e continua informativo exatamente ali (+3,8 contra −4,2 nos mesmos
casos). Daí a regra por regime, em `predict_with_orientation`:

1. Uma orientação ilegal e a outra não → a legal.
2. Margem de confiança ≥ 0,20 → a mais confiante.
3. Senão, peões decidem por ≥ 1 fila → a que eles apontam.
4. Senão → a mais confiante, marcada `ambiguous` e mandada para revisão.

Resultado: as rotações espúrias do Kemeri caem de 8 para 6, e as 6 restantes são leituras
degeneradas (sem peão de alguma cor) das quais 5 saem marcadas para revisão. O critério de
aceite continua atingido.

**A lição de método:** conjunto de teste limpo não prova comportamento em entrada suja. Foi a
segunda vez nesta fase que o número do split de teste disse "não muda nada" ou "está ótimo" e
o PDF real discordou — a primeira foi a S-11.

### Pendência da S-13: diagrama impresso do ponto de vista das pretas

O que 2.6 resolve é **imagem de cabeça para baixo**: aí as peças aparecem invertidas e o
reparo é girar os pixels. Livro que imprime o diagrama do ponto de vista das pretas é outro
problema: as peças estão desenhadas para cima e o que muda é o mapeamento casa→índice. Girar
a imagem estragaria a leitura; o certo é inverter a ordem das 64 casas, o que **não custa
inferência nova**.

E os sinais são outros: como as imagens de casa são idênticas nas duas interpretações, o
`min_confidence` é rigorosamente igual e não diz nada. Só o prior estrutural pode decidir —
que é justamente o sinal mais fraco. Não medi quantos diagramas assim existem nos 27 PDFs;
antes de implementar, vale contar.

### Decisão pendente: qual modelo o app usa

`DEFAULT_MODEL_PATH` continua apontando para `models/piece_classifier.pt`, o checkpoint
antigo treinado sobre todo o dataset. Ele é **pior** que o baseline no conjunto de teste
(0,9875 contra 0,9906), apesar de tê-lo visto no treino.

Trocar o default não é automático porque nenhuma das duas opções é a certa:

- `piece_classifier_baseline.pt` mede generalização de forma honesta, mas foi treinado com
  2.569 dos 3.195 tabuleiros — desperdiça 20% dos dados de propósito, para manter `test`
  reservado.
- O modelo **de produção** ideal treina em `train` + `val` (2.875 tabuleiros) e mantém só o
  `test` de fora. Esse checkpoint ainda não existe.

Enquanto não existir, o baseline serve para medir e o antigo para usar. Vale produzir o de
produção junto com a S-27, que arruma o treino reprodutível.

### Decisões da Fase 2

- **Posição rejeitada vai para o `.review.pgn`, não para o lixo.** A S-15 diz que a rejeitada "não vai para PGN; entra no relatório". Aqui ela vai para o arquivo de revisão junto com as de baixa confiança, marcada com `[Review "ilegal: ..."]`. O motivo: uma posição ilegal costuma estar a uma casa da correta, e é exatamente o que vale a pena corrigir à mão — descartá-la perderia o diagrama. O que a S-15 exige de fato, o PGN **principal** sem nenhuma posição ilegal, continua garantido.
- **Limiar de aceite em 0,80 é provisório.** Escolhido a partir da distribuição medida (mínimo ≥ 0,90 em quase todo tabuleiro exato). O número derivado da curva de calibração só sai com a S-28.

---

## Fase 3 — Semântica: lado a jogar e metadados ✅ concluída (2026-07-26)

**Por que:** até aqui 100% dos exercícios saíam como "brancas jogam"; em livros de tática ~50% está errado. Era o maior erro semântico do produto.

| # | Entrega | Ref. spec | Status |
|---|---|---|---|
| 3.1 | Extração do texto vizinho ao diagrama + associação por proximidade geométrica | S-16 | ✅ `pdf_text.py`, por linha e por grupo (ver abaixo) |
| 3.2 | Classificador de lado a jogar por padrões multilíngue | S-16 | ✅ pt/en/de/es/fr + símbolos |
| 3.3 | Inferência de lado a jogar por legalidade quando não há texto | S-17 | ✅ `semantics.infer_side_to_move` |
| 3.4 | Inferência de direitos de roque a partir da posição de reis/torres | S-17 | ✅ `infer_castling_rights` + `[CastlingSource]` |
| 3.5 | Metadados no PGN: número do exercício, jogadores, evento, ano | S-18 | ✅ headers novos em `build_pgn_games` |
| 3.6 | Campo `side_to_move` no `labels.csv` e na UI de correção | S-19 | ✅ esquema novo, `cvoff-migrate-labels`, Tkinter e Streamlit |
| 3.7 | Deduplicação de diagramas repetidos entre páginas | S-18 | ✅ `mark_duplicates` + `--dedupe` |

**Critério de saída:** atingido nos livros onde ele é mensurável, e **impossível no livro que o texto do roadmap escolheu** — ver a última seção.

### O levantamento que decidiu o desenho: quantos livros o texto alcança

Os 27 PDFs, 40 páginas amostradas de cada:

| a camada de texto declara o lado a jogar | livros |
|---|---|
| sim, em legenda ao lado de cada diagrama | **3** |
| tem texto, mas sem declarar o lado | 12 |
| não tem camada de texto (scan puro) | 12 |

O texto resolve a minoria — e é por isso que a S-17 não é um complemento da S-16, é metade do
item. Nos 24 livros restantes a única fonte é a própria posição.

Rodar os padrões na página inteira dá a impressão de cobertura muito maior: 8 livros
"parciais". Todos são falso positivo de prosa — `"se as brancas jogarem 32 f2×g2"`,
`"it was possible for White to play 20.Nd3"`, `"White moves first"` numa nota de rodapé. O
que separa declaração de comentário não é o padrão, é onde ele está.

### O que a S-16 supunha e a medição desmentiu

**A legenda fica acima, não abaixo.** A spec manda priorizar o texto abaixo do diagrama. Dos
quatro livros com legenda, três a põem acima (`Schiller`, `AAGAARD`, `Karpov`); só o
`400 Quebra-cabeças` a põe abaixo.

E o lado não é detalhe de apresentação: é o que decide **de quem é cada legenda**. No `Karpov`
o vão acima do diagrama mede 10 pt e o abaixo 7 pt, então por distância pura cada diagrama
rouba a legenda do diagrama seguinte e a página inteira sai deslocada de um exercício — o
`№79` vira `№81`. Mesmo erro no `Schiller`. A correção é decidir o lado **por página** (o lado
que consegue legenda para mais diagramas vence) e só então distribuir.

**A unidade é o grupo, não a linha nem o bloco.** Um bloco do `Karpov` cobre as legendas das
duas colunas (`№79. Steinitz - Bird` em x 82–181 e `№80. Steinitz - Mortimer` em x 278–402):
associado inteiro, cada diagrama herda o adversário do vizinho. Mas distribuir linha a linha
quebra o `Schiller`, onde o `6` da legenda de baixo cai a 15 pt do diagrama de cima e a 31 pt
do seu — o número não anda sozinho, pertence ao mesmo bloco que os jogadores e o evento. A
unidade certa é o bloco quebrado por coluna.

**Prosa não é legenda, mas cortar toda prosa custa recall.** O crivo por formato (bloco curto)
dá precisão, e derrubaria os exercícios do `AAGAARD`, que grudam o enunciado no comentário
(`"Black to play - Mark Dvoretsky invented this variation..."`). O que separa os dois casos é
a posição na linha: os falsos positivos medidos são todos oracionais e ficam no meio da frase;
os verdadeiros em parágrafo **abrem** a linha. Em legenda o padrão vale onde estiver.

**Não existe deslocamento constante entre número impresso e índice da página.** A primeira
versão do filtro de numeração media essa constante amostrando o documento. No `Reinfeld 1001`
ela vai de **-10 na página 46 a -29 na 1012**, porque o scan tem páginas a mais que o livro.
O que um número de página é não é uma função afim do índice: é um contador *localmente*
consecutivo, e é assim que ele é reconhecido agora — a página vizinha traz o sucessor dele na
mesma coluna. Sem esse filtro o `Reinfeld` reporta "exercício 10" para o número da página, que
fica a 16 pt do diagrama e escapa da faixa de margem.

**O português do acervo tem cinco formas, não duas.** Levantadas as legendas dos 400
exercícios do `400 Quebra-cabeças`: `brancas jogam` (117), `jogada das pretas` (52), `jogada
de pretas` (27), `pretas jogam` (13), `jogar de pretas` (12), `jogam as pretas` (1). Cobrir só
as duas formas que a spec lista deixava 39 exercícios sem lado a jogar num livro que declara
todos — foi o que a primeira medição do critério de aceite mostrou (74%).

### Critério de aceite da S-16, medido

Verdade independente do próprio extrator: no `400 Quebra-cabeças` o número esperado vem da
aritmética (1 diagrama por página, `página - 9`) e não do texto; no `AAGAARD` o lado a jogar é
conferido pelo **multiconjunto** de declarações da página inteira, o que testa a associação,
que é o que pode dar errado.

| livro | amostra | lado a jogar | nº do exercício |
|---|---|---|---|
| `400 Quebra-cabeças` | 50 exercícios | **100%** (50/50) | **100%** (50/50) |
| `AAGAARD - Practical Chess Defence` | 89 declarações / 90 números | **98,9%** | **94,4%** |

Alvos da S-16: ≥95% e ≥90%. Atingidos.

### Critério de aceite da S-17, medido no dataset

Aplicada a regra "o lado que não joga não pode estar em xeque" aos 3.195 rótulos do
`labels.csv`:

- os **51** rótulos que a Fase 1 corrigiu à mão como `OPPOSITE_CHECK` são recuperados
  **51/51** pela regra, sem que ninguém lhe dissesse a resposta;
- **0** posições legais são alteradas;
- ao todo 118 rótulos têm a vez imposta pela posição; os outros 3.077 não têm resposta e ficam
  no padrão, declarado como padrão.

### O efeito no produto

Exportação real, mesmo modelo e mesmas páginas:

| livro (páginas) | diagramas | lado do texto | da legalidade | assumido | saem "pretas jogam" |
|---|---|---|---|---|---|
| `400 Quebra-cabeças` (20–69) | 50 | 50 | 0 | 0 | **21** |
| `AAGAARD` (99–129) | 102 | 88 | 4 | 10 | **55** |
| `Schiller` (20–49) | 178 | 0 | 30 | 148 | **25** |
| `1937 Kemeri` (10–69) | 47 | 7 | 4 | 36 | **5** |
| `Reinfeld 1001` (10–69) | 59 | 0 | 0 | 59 | 0 |

As 106 posições que saem como "pretas jogam" saíam todas erradas antes. E o gancho que a
Fase 2 deixou fechou: no `AAGAARD` a fila de revisão cai de **7 para 1**, porque o xeque
invertido que a S-15 mandava conferir agora tem resposta — 4 pela legalidade e 2 pelo texto.

### Decisões da Fase 3

- **A legalidade vence o texto quando eles discordam, e o caso vai para revisão.** Emitir uma
  FEN que se sabe ilegal seria pior de todos os jeitos, e é o que o gate rejeitaria adiante.
  Mas a discordância significa que uma das duas fontes está errada — casa lida errado ou
  legenda associada ao diagrama vizinho —, e as duas causas merecem olho humano.
- **Lado a jogar assumido continua sendo aceito pelo gate.** Ele é a maioria (3.077 dos 3.195
  rótulos, 148 dos 178 diagramas do `Schiller`): mandá-lo para revisão mandaria quase tudo.
  O que muda é o PGN registrar `[SideToMoveSource "default"]`, para que "brancas jogam" possa
  ser conferido em vez de apenas acreditado.
- **A migração do `labels.csv` não preenche `w` no que não tem resposta.** Gravar o padrão
  numa coluna nova repetiria exatamente o erro que a S-19 existe para corrigir, agora com
  aparência de dado conferido. Fica vazia, que é o que ela é.
- **Deduplicação anota por padrão e só remove sob `--dedupe`.** A mesma posição aparecer duas
  vezes é comum e legítimo — enunciado e solução, ou o mesmo final em capítulos diferentes.
  Nas páginas medidas há 1 repetição em 436 diagramas; remover por conta própria custaria mais
  do que resolveria.
- **O roque inferido entra por padrão, marcado como inferido.** A posição não diz se o rei já
  se moveu, só que ele *poderia* não ter se movido. O erro tem lado: num meio-jogo com rei em
  e1 e torres nos cantos, `KQkq` é quase sempre certo; num final onde seria falso, é
  irrelevante. O `-` fixo de antes errava em toda posição de abertura.

### A pendência que a Fase 3 não resolve, e o critério de saída que não dá para atingir

O critério escrito neste roadmap pede ≥95% de acerto de lado a jogar em 50 exercícios do
`1001 Winning Chess Sacrifices`. Medido: esse livro **não tem** o que ler. A camada de texto
tem uma única linha por página — o número impresso — e nenhuma das 59 posições exportadas das
páginas 10–69 tem a vez imposta pela posição. Todas caem no padrão. Não há fonte de informação
no arquivo que responda à pergunta, e nenhuma implementação da S-16 ou da S-17 mudaria isso.

O critério da S-16, que nomeia o `AAGAARD` e o `400 Quebra-cabeças`, é o mensurável, e foi
atingido nos dois. Para os 12 livros sem camada de texto e sem xeque no diagrama, o lado a
jogar continua sendo um palpite — agora um palpite **declarado como tal**. Resolvê-lo de
verdade exige o motor da S-33 (o lado com ameaça imediata costuma ser o que joga) ou OCR sobre
a imagem da página, e nenhum dos dois pertence a esta fase.

---

## Fase 4 — Produtividade humana (5–8 dias)

**Por que:** com a Fase 2 pronta, o gargalo passa a ser o tempo do usuário corrigindo. Hoje corrigir significa editar uma string FEN à mão.

| # | Entrega | Ref. spec |
|---|---|---|
| 4.1 | **Editor de posição por clique/arraste** na aba de resultado (reaproveitar o código de arraste do tabuleiro de estudo) | S-20 |
| 4.2 | **Heatmap de incerteza**: casas de baixa confiança destacadas no tabuleiro reconhecido | S-21 |
| 4.3 | Painel de legalidade: mostra o `Board.status()` em linguagem clara ("faltando rei preto") | S-21 |
| 4.4 | Fila de revisão ordenada por incerteza (aprendizado ativo) atravessando páginas | S-22 |
| 4.5 | Navegador/editor do dataset: listar, filtrar por status, recorrigir, remover amostras | S-23 |
| 4.6 | Exportação com cancelamento e retomada (checkpoint por página) | S-24 |
| 4.7 | Atalhos de teclado para o ciclo corrigir→salvar→próximo | S-20 |
| 4.8 | Escrita atômica do estado da app; parar de silenciar exceções | S-25 |

**Critério de saída:** medir tempo para corrigir 20 diagramas antes e depois; alvo de redução ≥50%.

---

## Fase 5 — Modelo e desempenho (4–6 dias)

**Por que só agora:** sem a Fase 1 não há como saber se uma mudança de modelo ajudou. E a análise mostra que o classificador **não é** o gargalo atual — este é o item de menor prioridade relativa.

| # | Entrega | Ref. spec |
|---|---|---|
| 5.1 | Cache do dataset limitado (LRU) — resolve os 5,8 GiB de RAM | S-26 |
| 5.2 | `num_workers` configurável | S-26 |
| 5.3 | Treino reprodutível: `--fresh`, `strict=True`, semente e split registrados no checkpoint | S-27 |
| 5.4 | Métricas de treino corretas: exata por tabuleiro, por classe, pesos de classe para o desbalanceamento | S-27 |
| 5.5 | Calibração de confiança (temperature scaling) no conjunto de validação | S-28 |
| 5.6 | Experimento controlado: entrada em cor vs cinza, 32/48/64 px, backbone alternativo — decidir por medição | S-29 |
| 5.7 | TTA leve (deslocamentos de ±2 px) com voto | S-29 |
| 5.8 | Instalar torch com CUDA; exportação ONNX opcional para CPU rápida | S-30 |

**Critério de saída:** treino de época completa sem exceder 2 GiB de RAM; métricas reprodutíveis entre execuções; ganho ou não-ganho de cada experimento registrado.

---

## Fase 6 — Consolidação do produto (5–8 dias)

| # | Entrega | Ref. spec |
|---|---|---|
| 6.1 | **Camada de serviço** `src/chess_diagram_ocr/service.py` — Tkinter e Streamlit passam a ser só apresentação | S-31 |
| 6.2 | Quebrar `app_tkinter.py` em módulos (`ui/pdf_panel.py`, `ui/result_panel.py`, `ui/study_panel.py`, `ui/state.py`) | S-31 |
| 6.3 | "Corrigir Net" opt-in, endpoint configurável, documentado, com aviso de envio externo | S-32 |
| 6.4 | Centralizar strings; pt-BR acentuado e consistente | S-04 |
| 6.5 | Engine (Stockfish) opcional na aba de análise: avaliação e melhor lance | S-33 |
| 6.6 | Processamento em lote de vários PDFs com relatório consolidado | S-34 |
| 6.7 | README reescrito (fluxos reais, resolução de problemas) + `CONTRIBUTING.md` | S-35 |
| 6.8 | Empacotamento Windows (PyInstaller) para uso sem Python instalado | S-36 |

**Critério de saída:** Streamlit e Tkinter com paridade de funcionalidades; `app_tkinter.py` abaixo de 600 linhas; executável rodando em máquina sem Python.

---

## Sequenciamento sugerido de curto prazo

Se o tempo disponível for uma semana, o corte de maior retorno é:

1. **Dia 1** — Fase 0 completa (0.1 a 0.5). Repositório versionado e instalável.
2. **Dia 2** — S-05 (legalidade real) + S-06 (auditoria e saneamento do dataset).
3. **Dia 3** — S-07 (split persistido) + S-08 (harness de avaliação e baseline honesto).
4. **Dias 4–5** — S-10 (confiança por casa) + S-11 (decodificação com restrições). Aqui vem o salto de qualidade.
5. **Dia 6** — S-15 (gate de exportação) + S-14 (ordenação unificada). Rodar os 27 PDFs e comparar com o baseline.
6. **Dia 7** — S-21 (heatmap + painel de legalidade). O usuário passa a ver onde o modelo está inseguro.

Ao fim da semana o PGN exportado deixa de conter posições ilegais, os erros K↔Q estão corrigidos, existe um número de acurácia confiável, e o repositório tem histórico.

---

## Riscos e decisões que precisam do dono do projeto

| Risco / decisão | Observação |
|---|---|
| **Os PDFs são material protegido** | Nunca versionar `PDF/`. Se o projeto for publicado, os livros não vão com ele. Decisão sobre distribuição é sua. |
| **`data/samples` com 2,7 GB** | **Decidido (2026-07-25): manter em 800×800.** A redução para 512×512 foi descartada para preservar a resolução original caso o modelo passe a usar entrada maior que 64 px por casa (ver S-29). Consequência: as amostras seguem fora do git e precisam de estratégia própria de backup — não há cópia remota hoje. |
| **Migração do `labels.csv`** | Adicionar `side_to_move` (Fase 3.6) muda o esquema. Script de migração com backup, e `dataset.py` aceitando os dois formatos por um período. |
| **`Python-Easy-Chess-GUI-master/`** | Presumo que seja referência de estudo, não dependência — nenhum código do projeto o importa (verificado). Se estiver errado, me avise antes de remover. |
| **Endpoint `helpman.komtera.lt`** | Serviço de terceiro sem contrato. Pode sair do ar. Tratar como opcional, nunca como dependência do fluxo principal. |
| **Sem GPU no ambiente atual** | torch é `+cpu`. Se houver GPU na máquina, instalar a wheel CUDA acelera treino em ~10×. Vale verificar antes da Fase 5. |
