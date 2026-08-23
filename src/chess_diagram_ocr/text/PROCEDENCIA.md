# De onde veio o que está nesta pasta (S-178)

O reconhecedor de texto deste projeto é um **porte** do `DarcioAlberico/PyBoxEditor_Tkinter`
(repositório privado, Tkinter + PyTorch), e não uma reescrita. A decisão e os três caminhos
considerados estão em [`docs/ROADMAP_TEXTO.md`](../../../docs/ROADMAP_TEXTO.md).

**Este arquivo existe porque um porte sem procedência envelhece mal.** Em três meses haveria um
`text/preprocess.py` aqui e um `core/preprocess.py` lá que divergiram, e ninguém conseguiria
dizer qual conserto está em qual. A coluna que importa é a última: um porte literal e um porte
adaptado envelhecem de formas diferentes, e só a última coluna diz qual é qual.

**Origem de referência:** commit `e327343` (`master`, 2026-08-22),
*"Cinco ligaduras chegaram depois do último treino, e agora o modelo as conhece"*.

## O que foi portado

| arquivo aqui | origem | porte | o que mudou |
|---|---|---|---|
| `classes.py` | `core/learner.py` (`char_to_folder`, `folder_to_char`, `EXTRAS_LEGIVEIS`, `LEGADO`, `NomeDePastaInvalido`) | **literal** | anotações de tipo (o `mypy` daqui cobre `src/`); `nome_e_legal_no_windows` é novo, e trava aqui o que lá estava só no comentário |
| `modelo.py` | `core/neural_trainer.py` (`NeuralPredictor`, `impressao_do_modelo`, `impressao_das_classes`) e `core/neural_model.py` (`SimpleCNN`) | **adaptado** | ver "As quatro divergências" abaixo |
| `recognizer.py` | não tem origem: é a fronteira deste projeto | novo | implementa `ocr.TextRecognizer` (S-42). A segmentação provisória dele saiu em 2026-08-22, com a S-184/S-185/S-187 |
| `binarizacao.py` | `core/preprocess.py` (`binarize`, `fracao_de_tinta`, `tinta_plausivel`, `TINTA_PLAUSIVEL`, `METODOS`) | **literal** | anotações de tipo; `metodo_escolhido` é novo, e existe para a medição poder nomear o ramo em vez de comparar saídas pixel a pixel |
| `boxes.py` | `core/preprocess.escala_de_texto` e `core/livro.py` (`MIN_AREA_GLIFO`, `MARGEM_DIAGRAMA`) | **adaptado** | a `Caixa` substitui o `BoxEntry` de lá, que carrega estado de edição e de UI; `caixas_de_caractere` e `excluir_diagramas` reúnem aqui o que lá estava espalhado pelo `livro.extrair` |
| `colunas.py` | `core/services/box_service.py` (`detectar_colunas`, `_linhas_por_x`, `_fundir_faixas_estreitas`, `_por_colunas` e as cinco constantes) | **literal** no algoritmo e nas constantes | sai do `BoxService` (uma classe com 1.617 linhas e estado de UI) e vira funções; `calha` e `atravessa` são recortes novos da mesma lógica |
| `paragrafos.py` | `core/livro.py` (`_agrupar_em_paragrafos`, `_metricas_por_coluna`, `RECUO_DE_PARAGRAFO`, `SALTO_DE_PARAGRAFO`) | **literal** | a `Linha` daqui é um dado de diagramação; a de lá carrega o texto já classificado e o `Paragrafo` tem `titulo`, que é da exportação e não foi portado |
| `pagina.py` | `core/services/box_service.sort_boxes_reading_order` | **adaptado** | o diagrama é um elemento de primeira classe (`Diagrama`), e não um `BoxEntry` disfarçado; a parte de pilha girada não veio, e é da S-197 |
| `linhas.py` | `core/leitura_de_linha.py` (`quebrar_em_linhas`, `CAIXA_CURTA`, `FOLGA_DE_LINHA`, `FOLGA_DE_COLUNA`) e `box_service._linhas` | **literal** | `bandas` é o `_linhas` de lá, com a regra da F64 (o fundo da banda sai só das caixas altas); `ordem_em_faixa` é novo, e é a ordem correta **para faixa** -- a de página é `pagina.sequencia_de_leitura` |
| `negativo.py` | `core/negativo.py` | **literal** no algoritmo e nas oito constantes | a `Caixa` no lugar do `BoxEntry`; `substituir_tarjas` faz o que o `aplicar` de lá faz, sem devolver a binarização corrigida (quem a usava é o separador de colados, que é a S-186) |
| `trama.py` | `core/trama.py` | **literal** | a `TOLERANCIA_QUADRADO` vinha importada do `core/diagrama.py` de lá para haver **uma** definição; aqui ela é declarada, porque o detector deste projeto tem a régua dele em `detection/` e prendê-las agora acoplaria dois módulos sem medição que justifique |
| `vertical.py` | `core/vertical.py` | **adaptado** | o árbitro é **injetado** (`Arbitro`), e não importado: lá o módulo chama o classificador, aqui quem chama passa um chamável. É o que permite propor geometria sem depender de `torch`, e o que deixa a suíte travar o árbitro |
| `duas_linhas.py` | não tem origem direta: a F12 de lá mora dentro do `box_service` | novo | `separar` e `partir` reconstroem a F12; `e_fragmento` e `descartar_fragmentos` são daqui, e vêm da medição da S-185 |
| `tabela.py` | não tem origem direta: a F72 de lá mora no `livro.py` | novo | a grade vem da imagem, como lá; a saída é uma estrutura (`Tabela`/`Celula`) e não texto com espaços |
| `../../../models/char_meta.json` | `model_meta.json` do commit acima | **era cópia byte a byte; deixou de ser em 2026-08-23** | ver abaixo |
| `dataset.py` | não tem origem: a varredura de lá vive dentro do `CharacterDataset` do `neural_trainer` | novo | a S-202/S-203 deste projeto: hash de cópia exata, split atômico por grupo, relatório de vazamento |
| `treino.py` | `core/neural_trainer.py` (`NeuralTrainer.train`, `SimpleCNN`) | **adaptado** | ver "O treino que não veio de lá" abaixo |

## O `char_meta.json` deixou de ser cópia, e por quê

Até 2026-08-22 este arquivo era o `model_meta.json` de lá, byte a byte: 292 classes, temperatura
2,5208718319805. **Os pesos que ele descreve nunca estiveram nesta máquina** — são 2,6 MB de
`*.pth` ignorado lá e `*.pt` ignorado aqui, e o `.pth` de sha `2009f803…` que o metadado exige
não existe em nenhuma cópia local do projeto de origem (as que há trazem 128, 150 e 155 classes,
sem calibração). O motor `glifo` deste projeto, portanto, **nunca chegou a rodar**.

Em 2026-08-23 a `training_data/` chegou — 608.407 recortes em 314 classes — e o `cvoff-texto-train`
treinou o par aqui. O metadado passou a ser produzido por `treino.gravar_checkpoint`, no mesmo
formato (schema 2, `idx_to_char`, `modelo_sha256`, `classes_sha256`, `temperatura`), e a volta
para o formato de lá continua possível porque a forma canônica do `classes_sha256` não mudou.

**O que isso muda para quem for reaplicar um conserto de lá:** a linha do metadado não é mais
"compare e traga a diferença". Um metadado novo de lá descreve outro treino, com outras classes,
e trazê-lo para cá descasaria o par. O que continua valendo comparar é o **código** —
`char_to_folder`, `folder_to_char`, a forma da `SimpleCNN` e o pré-processamento.

## O treino que não veio de lá

O `NeuralTrainer` de lá treina com `augment_factor=8` sobre a pasta inteira, sem split, sem
calibração, e grava metadado de formato 1. Este projeto **não pode carregar** o que ele produz:
`ler_metadado` recusa formato 1 e recusa temperatura ausente. As quatro diferenças do `treino.py`:

1. **Split, e ele trava.** Lá o treino roda sobre tudo e a acurácia relatada é de treino. Aqui o
   split é atômico por grupo de cópia exata e `cvoff-texto-train` **aborta** se um grupo aparecer
   em dois lados. Nesta base isso não é detalhe: 70,7% dos recortes são cópia byte a byte.
2. **A época é salva pela recall macro, não pela acurácia.** Com `lower_a` em 63.055 recortes e
   61 classes com um só, a acurácia é decidida por um punhado de classes.
3. **A calibração acontece dentro do treino.** É a S-205: o retreino apaga a calibração e ninguém
   nota. Aqui não há caminho que produza pesos sem temperatura.
4. **Sem aumento de dados.** O `augment_factor=8` de lá multiplicaria 142.740 amostras por oito
   numa máquina sem GPU. Fica como hipótese aberta, a medir contra o controle — que é este treino.

## O que **não** foi portado, e por quê

| lá | por que fica de fora |
|---|---|
| `ui/`, `core/services/box_service.py`, diálogos | tocam Tk. A regra deste projeto é que nenhuma lógica de reconhecimento vive numa interface; o que decide vira função pura aqui |
| `core/learner.py` (o k-NN, `CharacterLearner`) | é o **segundo** elo da cadeia de fallback de lá. Aqui a cadeia é outra: a camada de texto do PDF vem primeiro, e a S-183 é quem mede se um segundo elo se justifica |
| `easyocr` | baixa ~100 MB no primeiro uso, o que contradiz a promessa do README daqui. A escolha de leitor de linha é decisão em aberto -- ver os riscos do `ROADMAP_TEXTO` |
| os pesos (`custom_model.pth`) | 2,6 MB de binário, `*.pth` é ignorado lá e `*.pt` aqui. Ver `modelo.py` |
| as fontes (`assets/fonts/`, `fonts/`) | só a `NotoSansSymbols2` traz licença no repositório de origem. Nenhuma vem para cá antes de a licença ser conferida (S-210) |

## As quatro divergências de `modelo.py`

O `NeuralPredictor` de lá carrega **tolerando** o que este projeto recusa. As quatro diferenças
são deliberadas, e cada uma tem um motivo deste lado:

1. **Metadado de formato 1 é recusado.** Lá ele carrega com aviso, porque lá existem modelos
   anteriores à calibração e recusá-los quebraria quem já tem um treinado. Aqui o único modelo
   que existe é o de 2026-08-21, que traz impressão digital e temperatura.
2. **Temperatura ausente é recusada.** Lá vira 1,0 com aviso. Aqui a avaliação de 2026-08-18
   nomeou que a métrica primária **mede confiança e não correção** -- aceitar softmax cru seria
   repetir o achado de propósito.
3. **Levanta em vez de devolver `False`.** Lá o retorno é booleano e quem chama decide. Aqui
   `carregar_classificador` é a única porta para o classificador existir, e "carregou pela
   metade" não é um estado que deva ser representável.
4. **Classifica em lote, e não um recorte por vez.** Lá o `_probabilidades` roda uma imagem por
   chamada. Uma faixa de legenda tem dezenas de glifos, e uma passada de lote é a diferença
   entre um custo que cabe numa varredura de 10 h e um que não cabe (S-215 mede).

O que **não** mudou, e não pode mudar sem invalidar os pesos: a forma da `SimpleCNN`
(1→32→64→128, densa 2048→256, `Dropout(0.5)`, 256→n), o pré-processamento
(cinza → `resize(32, 32)` → `/255`), a **polaridade** (tinta escura sobre papel claro, cinza
cru -- não binarizado, não invertido) e a forma canônica do `classes_sha256`
(`"{indice}\t{caractere}"` por linha, ordenado por índice, unido por `\n`).

## Como reaplicar um conserto que aconteceu lá

```bash
gh api repos/DarcioAlberico/PyBoxEditor_Tkinter/commits?path=core/learner.py --jq '.[].sha'
gh api "repos/DarcioAlberico/PyBoxEditor_Tkinter/contents/core/learner.py?ref=<sha>" --jq .content | base64 -d
```

Compare com a coluna "porte": onde ela diz **literal**, a diferença que aparecer é um conserto a
trazer. Onde diz **adaptado**, leia antes as quatro divergências acima -- uma delas pode ser
exatamente o que mudou lá.
