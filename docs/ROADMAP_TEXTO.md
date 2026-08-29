# Roadmap — Fases 25 a 31: o texto da página

Como o reconhecedor de caracteres do **PyBoxEditor_Tkinter** entra neste projeto, e o que ele
muda: hoje uma página vira uma FEN e mais nada; no fim destas fases ela vira **colunas, linhas
de texto, tabelas e diagramas**, na ordem em que se lê.

**O plano de execução deste roadmap** — as dez etapas, em ordem, com o que fecha cada item e o
que depende do dono — está em [PLANO_OCR_TEXTO.md](PLANO_OCR_TEXTO.md), escrito depois que o
classificador foi treinado em 2026-08-23. **Onde este documento diz que um item "depende dos
pesos que faltam", leia a seção 2 de lá**: os pesos deixaram de faltar naquele dia, e seis itens
trocaram de bloqueio.

A especificação item a item está em [SPEC_TEXTO.md](SPEC_TEXTO.md). O verificador que responde
"o que disto já existe no disco?" é `cvoff-texto-status`, e a seção
[Como conferir](#como-conferir-o-que-já-foi-implementado) explica como usá-lo.

> **Onde mora a spec de cada item (S-NN).**
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143, S-175, S-176 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170, S-177 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-294, S-295, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |

---

## Aviso sobre os números deste documento

**Nenhum número atribuído ao PyBoxEditor foi medido nesta máquina.** Eles vêm do `ROADMAP.md` e
do `docs/SPEC.md` daquele repositório, lidos no commit de 2026-08-22, e foram medidos no acervo
*dele* — Yusupov, Aagaard, Kasparov, Nunn —, que só parcialmente coincide com o acervo daqui.

Este projeto tem cicatriz de número herdado: a Fase 19 existe porque doze afirmações do `README`
e da `ARCHITECTURE` estavam erradas ao mesmo tempo, e `tests/test_docs.py` nasceu disso. Então a
regra vale também para número de fora: **um número do PyBoxEditor citado aqui é hipótese até ser
remedido no acervo daqui**, e cada fase abaixo tem um item que faz essa remedição. Onde o texto
diz "medido lá", leia "ainda não medido aqui".

---

## Onde os dois projetos estão hoje

### O que este projeto sabe fazer com texto, e é pouco

| capacidade | onde mora | alcance |
|---|---|---|
| ler a camada de texto do PDF | `pdf_text.py` (S-16) | linha, bloco, coluna dentro do bloco; só onde a camada existe |
| achar a legenda de *aquele* diagrama | `pdf_text.assign_lines_to_diagrams` | grupo = bloco quebrado por coluna |
| lado a jogar, número, jogadores, evento | `pdf_text.parse_context` | padrões em 4 idiomas, com filtro de prosa |
| OCR quando não há camada de texto | `ocr.py` + `ocr_caption.py` (S-42/S-43) | **só a faixa em volta do diagrama**, com o tabuleiro apagado |

E o buraco, medido aqui: **7 dos 27 livros do acervo (2.654 páginas) não têm camada de texto
nenhuma**, e outros 5 estão num regime pior — a camada existe e falha em parte das páginas
(`Gaprindashvili` e `Vishy Anand`: texto em 14 de 30 páginas amostradas; `400 Quebra-cabeças` e
`Yusupov`: 22; `La Combinación`: 26). Para os sete, todo diagrama sai
`[SideToMoveSource "default"]`.

O S-42 respondeu a isso com um motor de fora (RapidOCR), plugável, desligado por padrão. É a
resposta certa para o problema que ela tinha — e é uma resposta **de faixa de legenda**. Ela não
lê a página, não conhece coluna, não sabe o que é notação de xadrez e não aprende com o acervo.

### O que o PyBoxEditor sabe fazer, e é o que falta aqui

O reconhecedor de lá é um classificador de **glifo recortado**, treinado nestes mesmos livros:

- `SimpleCNN`, entrada 1×32×32, **292 classes**, ~620 mil parâmetros, ~2,6 MB de arquivo;
- as classes não são um alfabeto: são `digit_*`, `lower_*`, `upper_*`, `sym_<ord>` e
  `ligature_*` — inclusive **ligaduras tipográficas** (`fi`, `ffl`), **casas de xadrez coladas**
  (`e4`, `xf6`), **figurinas** (`♔♕♖♗♘♙`) e **símbolos de avaliação** (`±`, `∓`, `⩲`, `⩱`, `∞`);
- `model_meta.json` guarda `label_map`, `idx_to_char`, `temperatura` (2,5209), `modelo_sha256`
  e `classes_sha256` — o modelo e o metadado não se descasam, e isso é a F7.3 de lá;
- em torno dele há 96 fases de trabalho medido: segmentação, coluna, linha, tarja, trama, texto
  girado, tabela, léxico, notação, PDF pesquisável.

Os dois números que mais importam, medidos lá:

    classificador sozinho, sobre recorte já segmentado      99,83%
    pipeline inteiro, sobre página real (F1, 10 páginas)     94,2

**A distância entre os dois é de segmentação, não de modelo.** É a frase que o roadmap de lá
repete desde a F1.5, e é a que organiza estas fases: portar o classificador dá um classificador
excelente, não um leitor de página. O trabalho é achar onde está cada glifo, em que linha, em
que coluna, e o que fazer com o que não é texto.

---

## O que se quer no fim

Uma página deixa de ser "imagem de onde saem tabuleiros" e passa a ser **um documento**:

```
página
├── coluna 1
│   ├── parágrafo   "In this position White has a decisive resource..."
│   ├── linha       "1...♗xb7 2.♗xb7 ♘d7 3.♗xa8 ♕xa8 4.♘f3±"   ← notação validada
│   ├── diagrama    FEN + lado a jogar + legenda        ← o que o projeto já faz
│   └── parágrafo   ...
├── coluna 2
│   ├── tarja       "J.Bolbochan – L.Pachman"           ← texto branco sobre preto
│   └── tabela      3×5, célula a célula
└── rótulo girado   "Analysis diagram"
```

Disso saem quatro coisas que hoje não existem:

1. **O lado a jogar dos 7 livros sem camada de texto**, lido do desenho e não adivinhado.
2. **A partida em PGN a partir da notação impressa**, validada contra as regras — e não só a
   posição do diagrama.
3. **Um PDF pesquisável** com camada de texto invisível que acerta a notação, que é justamente
   onde a camada de fábrica desses livros erra tudo.
4. **Uma base de treino que cresce com o uso**, pelo mesmo laço que já existe para diagramas.

---

## A decisão que organiza tudo: portar, não depender

Três caminhos foram considerados, e dois estão descartados por motivo concreto.

**Depender do PyBoxEditor como biblioteca — não.** Ele é repositório privado, sem `pyproject`,
com módulos que se importam como `core.*` na raiz. Instalá-lo aqui obrigaria a publicar o pacote
ou a versionar um caminho de disco, e traria `easyocr` (≈100 MB baixados no primeiro uso) e uma
segunda cópia do `torch`. A promessa do README daqui — *nada sai da máquina no uso padrão* —
morre na primeira execução.

**Reescrever — não.** O que está lá não é código, é medição: 96 fases, e várias delas registram
**o que não funcionou**. `core/altura_relativa.py` existe inteiro para dizer que a altura
relativa à linha *não* desempata homóglifo; a F24 registra que voto e margem perdem; a F36
registra que o filtro de figurina custa. Reescrever joga fora exatamente a parte cara.

**Portar módulo a módulo, para `src/chess_diagram_ocr/text/`, com procedência — sim.** Cada
módulo portado registra de qual arquivo e de qual commit veio, para que um conserto lá em cima
possa ser reaplicado aqui sem arqueologia. É o que a S-178 institui.

E o porte obedece à regra que organiza este projeto: **nenhuma lógica de reconhecimento vive
numa interface.** Os módulos de lá são quase todos `core/` puro e atravessam bem; os que tocam
Tk (`box_service`, os diálogos) **não são portados** — a fronteira deles vira função pura aqui.

---

## A costura que torna a primeira fase barata

Este projeto já tem o encaixe pronto, e ele não foi feito para isto — foi feito na S-42 para
não amarrar o projeto a um motor de OCR:

```python
@runtime_checkable
class TextRecognizer(Protocol):
    def read(self, image: np.ndarray) -> list[TextBox]: ...
```

`ocr_caption.CaptionReader` consome esse protocolo e devolve `pdf_text.TextLine` **em pontos do
PDF** — o mesmo formato que `pdf_text.page_text_lines` produz da camada de texto. Consequência:
quem implementar `TextRecognizer` herda de graça todo o aparato da S-16 — agrupamento por
coluna, `dominant_placement`, `assign_lines_to_diagrams`, os tiers de legenda, o filtro de prosa,
a checagem de contradição.

**Então a Fase 25 inteira cabe atrás desse protocolo**, sem tocar em `pdf_text.py`, em
`ocr_caption.py` nem na interface. Um `GlyphRecognizer` que segmenta a faixa, classifica cada
recorte com a rede de 292 classes e devolve `TextBox` é uma peça substituível medida contra as
que já existem. Se perder para o RapidOCR na faixa de legenda, o porte para na Fase 25 e o custo
foi de uma fase — que é a razão de ela vir primeiro.

---

## Visão geral das fases

| fase | tema | o que passa a existir | depende de |
|---|---|---|---|
| **25** | A fronteira, e a prova de vida | o subpacote `text/`, o modelo pinado, e um `TextRecognizer` de casa medido contra o RapidOCR | nada |
| **26** | Do pixel à linha | segmentação, ordem de leitura, e a leitura **por linha** que o alinhamento distribui pelos boxes | 25 |
| **27** | A coluna | a calha achada na imagem; parágrafo, recuo e o diagrama como objeto da coluna | 26 |
| **28** | Os quatro casos que apagam texto | tarja, trama, texto girado, box que engoliu duas linhas, tabela | 26 |
| **29** | A base de 608 mil | inventário, procedência, split por livro, retreino e calibração | 25 (só a fronteira) |
| **30** | O que o texto lido serve | lado a jogar, PGN da notação, léxico, PDF pesquisável, modelo de página | 27, 28 |
| **31** | O que faz a base crescer | fila de revisão de caractere, "aplicar aos semelhantes", coleta em quarentena | 29, 30 |

As Fases 25→26→27 são o caminho crítico. A Fase 28 é paralela à 27 e pode esperar. A **Fase 29
não depende da 26**: assim que a fronteira existir (Fase 25), o inventário das 700 mil imagens
pode começar — e ele é o item de maior risco do plano inteiro, então deve começar cedo.

---

## Fase 25 — A fronteira, e a prova de que o modelo atravessa ◐ **código entregue; falta a medição**

**Itens S-178 a S-183.** Entregues em 2026-08-22: S-178, S-179, S-180 e S-181 fechados; S-182 e
S-183 parciais, e o que falta em cada um está na seção dele na spec.

**A S-182 fechou em 2026-08-23** (Etapa 1 do [`PLANO_OCR_TEXTO.md`](PLANO_OCR_TEXTO.md)): o
rodapé passou a dizer o dispositivo dos **dois** modelos torch, e o empacotamento nomeia o
classificador de caracteres na lista do que fica fora do bundle. **A S-183 continua parcial, e o
que falta nela não é código:** as 123 faixas de referência estão semeadas e nenhuma foi
transcrita.

> **O que a implementação achou, e não estava previsto.**
>
> 1. **O extra `texto` sairia vazio.** O classificador traz `torch`, `opencv-python` e `pillow`,
>    e os três já são obrigatórios. A S-182 mudou de forma: o que porteia o recurso é o **arquivo
>    de pesos**, não uma dependência. O motivo está registrado na seção dela.
> 2. **Os pesos de 292 classes não estão nesta máquina.** As cópias locais do PyBoxEditor são de
>    fevereiro (155 e 150 classes, sem impressão digital e sem calibração), e o `.pth` atual é
>    ignorado pelo git lá. O metadado veio (`models/char_meta.json`, do commit `e327343`), e é
>    ele que descreve as 292 classes. **Sem os pesos, a S-183 não pode rodar** — o placar precisa
>    do modelo de verdade, não de um construído para teste.
> 3. **O `allowlist` do glifo é melhor que o dos outros três motores, e é estrutural.** Ele
>    restringe o *decodificador* — as colunas proibidas saem da matriz de probabilidades antes do
>    argmax — em vez de filtrar a saída. O comentário de `ocr.filter_by_allowlist` já dizia o que
>    o filtro posterior custa: *"o motor já escolheu `8` em vez de `B` antes de chegar aqui, e
>    apagar o `8` não traz o `B` de volta"*. Aqui traz.
>
> **Para destravar a fase, faltam duas coisas, e as duas são suas.** Os pesos
> (`custom_model.pth` do PyBoxEditor, 2,6 MB, sha256 `2009f803…`), apontados por
> `ocr.glyph_model` em `data/settings.json` ou por `CVOFF_OCR_GLYPH_MODEL`; e a conferência das
> 123 faixas já semeadas em `docs/metrics/texto_faixa_referencia.jsonl`.

> **O que a execução de 2026-08-22 mediu, e o que ela desenterrou.**
>
> **1. Os pesos de 292 classes não estão nesta máquina, e isso foi verificado, não suposto.**
> Varredura do disco inteiro: dois `custom_model.pth`, de fevereiro, com **155 e 150 classes**,
> `schema_version` 1, sem impressão digital e sem calibração. Nenhum tem figurina no mapa de
> classes. O de 2026-08-21 é `.gitignore` no repositório de origem e só existe onde ele foi
> treinado.
>
> **2. O caminho portado funciona — provado com pesos treinados de verdade.** Rodando o par de
> 155 classes como diagnóstico (não como medição: ele é anterior às figurinas e está em softmax
> cru), sobre seis linhas de texto da página 21 do `AAGAARD`, contra o que a camada de texto diz:
>
>     camada  'The Defensive Thinking Frame'      glifo  'The Defens1ve Th1nhng Frame'   CER 0,14
>     camada  'In this apparently harmless...'    glifo  'In an1s appaently harmless...' CER 0,16
>     camada  'Black, a master of prophylaxis'    glifo  'Black, a master of prophylcx1s' CER 0,11
>
>     CER médio nas seis linhas: 0,21
>
> Isto não é um número publicável — modelo errado, sem calibração, segmentação provisória. É a
> prova de que a `SimpleCNN` portada carrega, de que a polaridade do pré-processamento está certa
> e de que o `GlyphRecognizer` atravessa. **E o padrão de erro é exatamente o que a F17 previu**:
> `i`→`1`, `th`→`an`, `ki`→`h`. Nenhum desses é decidível olhando um glifo por vez, e é o
> argumento inteiro da S-188, agora observado neste acervo em vez de herdado do outro.
>
> **3. A semeadura desenterrou um defeito de produção da S-16.** Em **19 das 123 faixas, de 7
> livros**, o `caption` que `contexts_for_page` devolve são as filas do tabuleiro impresso em
> fonte de diagrama. O `_is_diagram_font_row` só conhece a fonte Merida; estes livros usam a do
> exportador do Lichess. **O `Polgar` está entre os sete**, e é o livro para o qual o filtro foi
> escrito. Registrado, não consertado de passagem: mexer nesse filtro muda a legenda de todo o
> acervo e precisa da medição dele.

O objetivo é um só: **descobrir, com o menor investimento possível, se o classificador de lá
serve aqui.** Nada de página inteira, nada de coluna, nada de retreino. Só o modelo, o mapa de
classes, e a faixa de legenda que a S-43 já recorta e já sabe entregar.

O que entra:

- o subpacote `text/`, com o arquivo de procedência que diz de onde veio cada módulo;
- o carregamento do modelo **pinado por hash**, no mesmo desenho da S-40: `model_meta.json`
  manda, e um `.pt` que não bate com `modelo_sha256` é recusado, não usado em silêncio;
- `char_to_folder`/`folder_to_char` portados sem uma linha de diferença — a lista
  `EXTRAS_LEGIVEIS` é fechada, e alargá-la aqui faria as duas bases divergirem sem aviso;
- `GlyphRecognizer`, que implementa `TextRecognizer` e nada mais;
- o extra `texto` no `pyproject`, opcional pela mesma regra do `onnx`, do `ocr` e do
  `second-opinion`;
- **o placar**: a mesma faixa de legenda lida por três fontes — camada de texto (onde existe),
  RapidOCR, e o glifo — sobre o conjunto de campo.

**O critério de saída é uma decisão, não um número.** Se o glifo não ganhar do RapidOCR nos 7
livros sem camada de texto, o porte para aqui e fica registrado por quê. Se ganhar, as fases
seguintes têm justificativa medida em vez de herdada.

---

## Fase 26 — Do pixel à linha ✅ **concluída (2026-08-24)**

**Itens S-184 a S-189.** Entregues em 2026-08-22: S-184 (binarização), S-185 (caixa de caractere)
e S-187 (linha). Os outros três dependiam dos pesos de 292 classes que não estavam nesta máquina,
e fecharam em 2026-08-24 — nas Etapas 8 e 9 do [`PLANO_OCR_TEXTO.md`](PLANO_OCR_TEXTO.md), com o
classificador que a S-204 treinou.

**E os dois maiores números que esta fase prometia não se confirmaram, o que é o resultado:**

- **S-186, o separador de glifo colado: piora.** 155 faixas de 11 livros — `nunca` CER 0,2248,
  `auto` 0,2400, `sempre` 0,5034. O árbitro não salva o separador, só reduz o estrago; e a
  conclusão sobrevive a cinco limiares de largura. As classes de ligadura já absorviam o problema,
  como a spec suspeitava. **Padrão: desligado.**
- **S-188, ler a linha em vez do caractere: empata.** 0,2248 contra 0,2230 — ganho de **0,0018**,
  onde lá foram 18,4 pontos. O roadmap avisava que o 91,2% era do EasyOCR e não atravessaria a
  troca de motor sem medição; atravessou como zero. **Padrão: desligado.**
- **S-189, a confiança por concordância: paga sozinha.** Onde as duas leituras concordam, 98,6%
  dos caracteres estão na referência; onde divergem, 48,2%. É o melhor sinal de erro que este
  projeto tem, e é o que a fila da S-212 precisa. **O leitor de linha entra como segundo
  opinante, e não como leitor.**

> **O que a entrega mediu, e é a primeira vez que a segmentação deste projeto tem número.**
> Página 21 do `AAGAARD`, seis linhas, sempre com o mesmo modelo de diagnóstico de 155 classes --
> só a segmentação muda entre as linhas da tabela:
>
>     segmentação provisória da Fase 25         CER 0,21
>     S-184/S-185/S-187, faixa justa            CER 0,14   <- -33%
>     S-184/S-185/S-187, faixa dilatada em 2pt  CER 0,22
>
> **A segunda linha é o ganho; a terceira é um aviso.** A faixa dilatada é o que `ocr_caption`
> produz de verdade (`radius_pt`), e ela encosta na linha de cima: os fragmentos de descendente
> entram como caixas próprias e custam 8 pontos de CER. O corte de linha os separa corretamente
> em linha à parte -- quem os descarta é o chamador, e é trabalho da S-198.
>
> **E o caminho até o 0,14 passou por 0,35 e 0,46**, o que vale mais que o número final. Com a
> régua de área no lugar da de altura, o pingo do `i` passa a sair como caixa própria e
> `Defensive` vira `Defens1.ve` -- pior que a provisória. A régua de altura acertava esse caso
> **por descartar o pingo**, e o preço dela era descartar junto o ponto final de verdade. O que
> faltava era `unir_pingos`; e a primeira versão dela mediu "caixa curta" contra a escala da
> página (30 px, altura de maiúscula) quando a haste de um `i` tem 18. Está tudo na seção da
> S-185, e travado por teste.

Aqui está o trabalho de verdade, e é o que a distância entre 99,83% e 94,2 nomeia. Quatro
problemas em cadeia, e cada um tem cicatriz registrada lá:

1. **Binarizar.** Limiar fixo funciona em página limpa e falha em scan com iluminação irregular
   — o caso normal. O `preprocess` de lá escolhe pelo **resultado** (fração de tinta entre
   0,05% e 35%), não pelo histograma, porque a bimodalidade mentia justamente na página com
   sombra de encadernação.
2. **Achar o box.** `findContours`, e depois uma régua de escala que separa caractere de
   respingo. **É área, não altura**: cortar por altura fazia o livro sair sem pontuação
   (`5.♔xf2` virava `5♔d2`).
3. **Separar o colado.** Dois caracteres que saem num contorno só. Lá isso rende pouco hoje
   (+0,1 de F1) porque as classes de ligadura absorveram parte do problema — o que é um achado
   e não uma falha, e precisa ser remedido aqui antes de valer o esforço.
4. **Ler a linha, não o caractere.** É a F17 de lá, e o ganho é grande:

       por caractere    72,8%
       por linha, com alinhamento    91,2%

   O mecanismo: `Bib1i0g[aPhY` vira `Bibliography`. Nenhum glifo isolado decide isso.

**A peça que este projeto ainda não tem, e que a F17 exige, é o leitor de linha.** Lá ele é o
`english_g2` do EasyOCR, um CRNN treinado em linha. Aqui o EasyOCR está descartado como padrão
pelo mesmo motivo da S-42 — baixa ~100 MB no primeiro uso. **A escolha do leitor de linha é uma
decisão em aberto que precisa do dono do projeto**, e está registrada na lista de riscos abaixo
com as três opções e o que cada uma custa.

Sem leitor de linha, a Fase 26 entrega segmentação e leitura por caractere: pela tabela de lá,
isso é ~73% e não ~91%. É útil (a legenda curta sobrevive bem), e não é o alvo.

---

## Fase 27 — A coluna ✅ **concluída (2026-08-22)**

**Itens S-190 a S-194, mais a S-216.** É o que o pedido chama de *"além de colunas no pdf"*, e é a primeira fase
deste plano que fecha inteira -- ela é geometria, e por isso não depende dos pesos que faltam.

> **A ordem de leitura tem número, e ele é bom: `tau` médio 0,0096 em 57 páginas de 17 livros**,
> 32 delas em ordem exata. `tau` é a fração de pares invertidos; 0,50 seria as duas colunas
> intercaladas, que é o defeito que a fase veio consertar.
>
> **A referência não foi anotada à mão, e a troca é a decisão da fase.** A spec pedia 12 páginas
> anotadas; nos livros com camada de texto o próprio PDF já traz a ordem de leitura, escrita pela
> diagramação. Nenhum dos dois lados olha para o outro, e sai de graça.
>
> **E ela precisou de um guarda, achado na primeira execução.** O `tau` médio deu 0,0965 e o pior
> caso 0,53. Investigado: no `400 Quebra-cabeças ..._hq` a camada emite o rodapé, depois a metade
> de baixo e **só então o topo**. Nossa ordem estava certa; a referência é que não era ordem de
> leitura. Com o guarda geométrico -- uma coluna não desce, duas descem uma vez --, 0,0965 vira
> 0,0096.
>
> **62% das páginas com camada de texto a emitem fora da ordem de leitura** (93 de 150). É o
> argumento mais forte que este projeto tem para não confiar nela, e apareceu de graça.
>
> **O limite que sobrou está medido e não corrigido.** O pior caso restante é o `Karpov`, `tau`
> 0,229: ali a camada emite linha a linha atravessando as colunas e nós lemos coluna a coluna --
> e as duas ordens são legítimas, porque a página é uma **grade de exercícios** numerada da
> esquerda para a direita, não prosa em duas colunas. Distinguir grade de prosa é item próprio.
>
> **Fechado pela S-216 em 2026-08-23, e ela desmentiu duas coisas escritas acima.** A primeira é
> o sinal: não há régua geométrica que separe as duas direções, porque o `Schiller` e o `Karpov`
> têm grades indistinguíveis numeradas ao contrário uma da outra -- o que decide é o **número
> impresso**, e ele é constante por livro. A segunda é a referência: "escrita pela diagramação"
> vale para parte do acervo, e **não vale nos três livros de grade**, que trazem camada do
> `Adobe Acrobat Paper Capture`. Contra o número impresso, esse motor erra a direção em 21 de 205
> páginas, nos dois sentidos.
>
> Com a direção calibrada por livro, o `tau` das 172 páginas dos livros calibrados cai de 0,127
> para **0,026**, e **nenhum livro piora**. E o atalho tentador -- ligar "grade ⇒ linha a linha"
> para todos -- também faz o agregado cair, para 0,094, **enquanto leva o `Schiller` de 0,0004 a
> 0,1705**. Um portão de "o `tau` médio tem de cair" aprovaria justamente a mudança errada, e é
> por isso que a régua da S-216 é o número impresso.
>
> **E o livro que o número impresso não alcança é calibrado pela camada, marcado como hipótese.**
> O `Yusupov` tem 64 páginas de grade e nenhum número legível; ele recebe direção pela preferência
> da camada (48 páginas votam `grade` contra 6), com `"hipotese": true` no relatório, fora do
> `acerto` que o `--baseline` trava, e com o `tau` publicado em duas colunas: **0,0676 só com o
> confirmado, 0,0328 com a hipótese**. A distância entre os dois é metade do ganho, e é o que a
> S-188 vai confirmar ou desmentir. Quanto vale esse palpite também está medido: por página a
> camada acerta 96,5%, e **por livro acerta 3 de 4** -- no `Secrets` ela erra por unanimidade.

**Item S-216 (2026-08-23), acrescentado à fase depois de ela fechar.** A grade de exercícios, e a
direção que só o número impresso diz. É o limite acima, medido e corrigido; a fase continua
fechada, e o item novo mora no fim da numeração porque é lá que item novo nasce.

O projeto já ordena por coluna **dentro de um bloco da camada de texto**
(`pdf_text._split_into_columns`). Isso não é o mesmo que saber onde a coluna acaba na *imagem*,
e a diferença aparece em três lugares, todos medidos lá:

- **o parágrafo**: sem saber onde a coluna termina, o último parágrafo da esquerda sai colado no
  primeiro da direita;
- **o recuo**: a margem que abre parágrafo é a mediana das esquerdas, e sem coluna essa mediana
  não é margem de coluna nenhuma;
- **o lugar da figura**: o diagrama pertence a uma coluna, e sem isso ele flutua.

Duas armadilhas que a F70 e a F61 de lá compraram com medição, e que esta fase herda:

- **uma letra do cabeçalho apagava a calha da página inteira** — a causa era um `OR` sobre
  boxes; a correção é contar **linhas**, não boxes;
- **coluna estreita demais não é coluna** — sem esse piso, uma margem virava coluna e a página
  saía em três.

---

## Fase 28 — Os casos que apagam texto ✅ **concluída (2026-08-23)**

**Itens S-195 a S-199.** Entregues em 2026-08-22: S-195 (tarja), S-196 (trama) e S-199 (tabela).
A S-197 e a S-198 esperavam o árbitro — o classificador que não estava nesta máquina —, e
fecharam em 2026-08-23, na Etapa 1 do [`PLANO_OCR_TEXTO.md`](PLANO_OCR_TEXTO.md):

- **S-197, a tabela dos quatro ângulos**, 534 linhas de 30 livros giradas por transposição:
  argmax da média **0,9363** (lá, 99,7%). Em produção, 0,9775 de não mexer no texto de pé e
  0,9195/0,9326 de marcar o girado — e a folga mediana é **sete vezes** a margem exigida, que
  por isso sobrevive à calibração.
- **S-198, o ganho do corte**, 155 faixas de 11 livros: o **descarte de fragmento paga**
  (CER 0,2725 → 0,2248) e entrou no `GlyphRecognizer`; o **corte não paga** (0,2337) e continua
  fora, com o número no relatório. Lá ele valia +0,3 de F1.

> **A medição da S-198 achou um defeito de referência que vale para todo este documento.**
> Metade do acervo tem camada de texto **gerada por OCR**, e medir CER contra ela é comparar dois
> palpites — a primeira corrida deu 0,8644 por isso. O `AAGAARD` é um desses livros, e é a página
> com que a Fase 26 mediu 0,21 → 0,14 → 0,22: aquela comparação relativa continua válida, e o
> 0,14 **não é erro contra a verdade**.

> **O árbitro é injetado, e é o que permitiu entregar sem os pesos.** `vertical.decidir_angulo` e
> `duas_linhas.partir` recebem um chamável que devolve confiança por recorte, em vez de importar
> o classificador. Assim os dois módulos propõem geometria sem depender de `torch`, e a suíte
> pode **travar** o árbitro para afirmar por que uma pilha foi aceita — o que um árbitro de
> verdade não permitiria.
>
> **E a regra que os dois carregam é a mesma, e é a lição mais cara do projeto de origem: sem
> árbitro, não mexer.** Separar glifo colado sem classificador que confirmasse custou lá 2,3
> pontos de F1; marcar ângulo por geometria pura teria o mesmo defeito. Com o árbitro ausente,
> `marcar` devolve a entrada intacta e `partir` não corta — e há teste com esse nome.
>
> **A S-198 ganhou uma segunda metade que não estava na spec**, e ela veio da medição da S-185:
> além de partir o box alto demais, ela **descarta a linha que é só fragmento**. A faixa dilatada
> da `ocr_caption` encosta na linha de cima, e os pedaços de descendente que entram custam 8
> pontos de CER (0,14 → 0,22 na mesma página).
>
> **Um defeito achado ao escrever teste**, e é do tipo que não daria erro: em `trama`, um bloco
> menor que duas margens produzia `y2 - margem` negativo, e o `numpy` fatia a partir do fim — o
> recorte saía de **outro lugar da página**, não vazio. O sintoma seriam glifos com coordenadas
> plausíveis vindos de onde ninguém olhou.

Não são casos raros: são o cabeçalho, o quadro de pontuação e a tabela de finais destes livros.
O que os une é a **forma de falha**: o texto não sai errado, ele **não sai**, e nada acusa.

| caso | o que acontece hoje | o que o conserto faz |
|---|---|---|
| tarja preta com o nome dos jogadores | a tarja inteira vira um contorno; 20 caracteres somem | inverte a faixa, apara a borda pelas linhas cheias, lê dentro |
| trama de meio-tom (quadro de pontuação) | a mediana de altura cai a 2 px e a régua descarta os caracteres | rebinariza o recorte: dentro do painel o Otsu corta acima da trama |
| rótulo girado ("Analysis diagram") | lido **errado, em silêncio**: 94,2% de pé contra 8,4% girado | a geometria propõe a pilha, o classificador escolhe o ângulo |
| box que engoliu duas linhas | o descendente encosta na linha de baixo e come um caractere | corta pelo vale, com árbitro |
| tabela de finais | moldura fechada, `RETR_EXTERNAL`, e as 276 caixas de dentro **não saem** | a grade vem da imagem; dentro da célula não se lê como se lê a página |

O caso do texto girado é o mais perigoso dos cinco, e por isso ganha destaque: **ele devolve
outra letra com confiança normal**. Um erro que se anuncia custa revisão; um que não se anuncia
custa confiança no programa inteiro.

---

## Fase 29 — A base de 608 mil ◐ **seis fechados; dois esperam a origem responder**

**Itens S-200 a S-206.** É a fase de maior risco do plano, e a razão está na próxima seção.

O que ela faz, em ordem: inventariar → separar por procedência → deduplicar → **partir por
livro** → treinar → calibrar → medir honesto.

**Estado em 2026-08-23**, depois das Etapas 2 a 4 do [`PLANO_OCR_TEXTO.md`](PLANO_OCR_TEXTO.md):

| item | estado | o que falta |
|---|---|---|
| S-200 · inventário | ✅ | — |
| S-201 · procedência | ◐ | o registro na origem, e a decisão sobre a `training_data_2` |
| S-202 · duplicata | ✅ | — |
| S-203 · split por livro | ◐ | o livro; o código existe e é exercido em base sintética |
| S-204 · treino | ✅ | — |
| S-205 · calibração | ✅ | — |
| S-206 · placar honesto | ✅ | — |

**A S-201 e a S-203 ficaram paradas na mesma coisa, e é por isso que as duas carregam a mesma
sonda nova:** `arquivo:data/texto_procedencia.csv`. O contrato do arquivo está escrito
(`text/procedencia.py`), o split por livro está implementado e travado por teste, o `cvoff-audit`
já reprova rótulo de modelo no teste — **e nada disso roda sobre livro nenhum**, porque a pasta
não tem. Só o `PyBoxEditor_Tkinter` pode produzir esse arquivo: foi quem recortou.

**O inventário fixou os números que divergiam entre documentos.** 607.713 recortes, 314 pastas,
178.370 imagens distintas, **zero** classes vazias, zero pastas indecifráveis e zero PNGs
ilegíveis. Os 178.420 que este documento citava eram de antes de a S-202 mover 694 recortes para
quarentena — eles levaram junto 50 grupos inteiros.

**O split é por livro, e isto não é negociável.** A avaliação de 2026-08-18 deste projeto abriu
com quatro achados, e três são de contaminação: a verdade de referência é a leitura do próprio
modelo, um sexto do conjunto de campo vira treino no próximo retreino, e o split de teste também
está contaminado. Repetir esse defeito com 700 mil amostras produziria um número alto e vazio —
e desta vez com autoridade estatística, que é pior.

A calibração de temperatura entra no fim do treino, e não como passo separado: lá, a F25 mediu
que **o retreino apaga a calibração** e ninguém notava.

> **A grade não achou vencedora, e isso é uma resposta (S-204, 2026-08-23).** Seis braços, 10
> épocas cada, e o primeiro colocado ganha do controle por **0,0015** — um quinto do ruído de
> 0,0068 que a própria S-204 mediu entre épocas consecutivas. **O aumento de dados dirigido ao
> glifo não paga** (0,9598 contra 0,9632 do controle), e é a terceira vez que este projeto mede
> uma hipótese que todo mundo assume e recebe um não: aumento genérico para peças, pesos de classe
> para caractere, e agora aumento dirigido. O que a grade rendeu de utilizável é um trade-off:
> `canais-menores` perde 0,0202 de macro e roda em **menos da metade do tempo**.

> **A curva mediu o que a temperatura sozinha não dizia (S-205, 2026-08-23).** O ECE ponderado
> desta validação é 0,0037 e o ECE **por faixa** é 0,1080 — trinta vezes maior. A diferença é que
> 96% das amostras caem numa faixa só, a de 0,93 a 1,00, onde o modelo é quase perfeito; o número
> ponderado mede aquela faixa e mais nada. **E é no meio da escala que as quatro decisões que
> consultam confiança acontecem** — lá o modelo é pessimista, dizendo 0,83 onde acerta 0,94. É a
> mesma lição da macro contra a acurácia, pela segunda vez nesta fase.

---

## Fase 30 — O que o texto lido serve ✅ **completa em 2026-08-26**

**Itens S-207 a S-211.** É onde o texto vira produto.

| item | o que ele entregou |
|---|---|
| **S-207** · lado a jogar pelo glifo | `glifo` e `glifo-page-scope` como fontes declaradas, e a tabela por livro: **3 de 146 diagramas assumidos (2,1%)** deixam de sair `default` |
| **S-208** · notação validada, e o PGN | `text/notacao.py`: fatiar, validar, e o PGN que sai das regras |
| **S-209** · o léxico | `text/lexico.py`: a sinalização que nunca troca, os quatro perfis como dados, e a junção da hifenizada |
| **S-210** · PDF pesquisável | `escrever_camada`: a camada invisível **por linha**, do que o motor leu, com a página idêntica pixel a pixel |
| **S-211** · modelo de página | `PaginaLida`: coluna → bloco → linha → texto \| diagrama \| tabela |

**Os três números que a fase produziu e que não estavam no plano:**

1. **A lista de idioma sozinha não serve neste acervo.** 60,0% de alarme falso contra 7,1% do
   acervo sozinho e 5,65% dos três juntos. As 10.010 palavras de `idioma.txt.gz` vêm de listas de
   fora e não cobrem os oito idiomas das páginas; quem carrega o peso é `acervo.txt.gz`. O 5,65%
   do perfil `completo`, esse sim, **confirma o 5,8% que a S-209 citou do projeto de origem**.
2. **Zero `U+FFFD` no acervo.** O caminho `ToUnicode` da S-210 -- o mais barato, que a spec cita
   com 216 pares no Yusupov -- não tem material aqui, e por isso não foi construído. O defeito de
   mapeamento destes livros é o codepoint cru da fonte de xadrez, não o losango.
3. **O terceiro guarda da junção é o que mais trabalha.** Das 5 quebras hifenizadas das camadas
   editoradas, as 5 são termo de xadrez (`f-pawn`, `h-file`, `a-pawn`) ou lance -- e três delas
   *juntariam*, porque estão na lista. Sem ele, a passada apagaria a grafia que o livro escolheu
   na construção mais comum da prosa de xadrez.

O item que muda mais coisa é o **modelo de página** (S-211): hoje `RecognizedDiagram` é o que a
UI recebe, e a página não existe como objeto. Com coluna, linha, tabela e diagrama num só
modelo, a exportação para PGN, para PDF pesquisável e para a fila de revisão passa a ler da
mesma estrutura — que é a regra da Fase 6 aplicada ao documento.

O léxico (S-209) tem uma propriedade que vale repetir porque ela contraria o instinto:
**palavra fora do dicionário é sinalizada, nunca aproximada da mais parecida.** Medido lá: dos
18 lances tão maltratados que escapam do detector de notação e caem no léxico, **nenhum** está
no dicionário; com correção automática, seriam 18 lances reescritos como palavra.

Em 2026-08-25 entrou a metade de **dados** desse item: as duas listas empacotadas
(`assets/lexico/idioma.txt.gz` e `nomes.txt.gz`, 160 mil palavras), construídas por
`cvoff-texto-lexico` a partir de listas de fora. Com elas o dicionário de `text/dicionario.py`
passou a **ligado por padrão** — 6 correções em 40 páginas, as 6 confirmadas pela camada
editorada, nenhuma palavra certa quebrada, ao custo de 1% do tempo de página. E há um número que
o plano não esperava: **partir palavra colada, que o item prevê, dá 0 acertos contra 5 erros
neste acervo** — os nomes próprios são o que estraga (`carrying` → `carr ying`, de `Carr` e
`Ying`). Está tudo em `docs/metrics/texto_dicionario.json`.

---

## Fase 31 — O que faz a base crescer ✅ **completa em 2026-08-26**

**Itens S-212 a S-215.**

| item | estado | o que ele entregou |
|---|---|---|
| S-212 · fila de revisão de caractere | ✅ | `text/fila.py`: ordena pela confiança da S-189 -- que **é** a divergência -- e a cor da tela sai da mesma função, então elas não têm como discordar |
| S-213 · aplicar a todos os semelhantes | ✅ | `text/semelhanca.py` + `cvoff-texto-semelhanca`: os três rigores medidos nesta base, e a pré-visualização como tipo e não como conselho |
| S-214 · coleta em quarentena | ✅ | `text/coleta.py`: reservatório, dedução dupla, confiança na frente do nome -- e `promover` gravando procedência `humano` |
| S-215 · orçamento por página | ✅ | `text/custo.py` + `cvoff-texto-custo`: **fator 2,21x, política `sob-demanda`** |

Este projeto já tem o laço para diagramas: reconhecer → corrigir no tabuleiro → `Ctrl+S` →
dataset. Para caractere o laço não existia, e sem ele as 700 mil imagens são um número que só
diminui de valor.

**Os três números que a fase produziu, e que não estavam no plano:**

1. **O texto custa 2,21x a varredura de hoje** (0,833 s/página contra 0,377), e a política que
   isso escolhe é *texto sob demanda, por página* -- não em toda varredura. `contornos` é a maior
   etapa do lado do texto (0,186 s/página), **acima da classificação** (0,156): o gargalo é a
   segmentação, e não a rede.
2. **A segunda condição da S-213 vale muito mais aqui do que no projeto de origem.** No limiar de
   0,30 ela leva a precisão de 82,76% para **99,71%**, com a cobertura igual até a quarta casa --
   ela remove quase só os pares errados. É ela que permite um rigor `amplo` com 56,8% de cobertura.
3. **O limiar da quase-duplicata não serve a este item.** O `dedupe.LIMIAR_PADRAO` (0,03) entrega
   100% de precisão com 6% de cobertura: um lote que não alcança nada. Os dois assuntos usam a
   mesma régua e não o mesmo corte.

**E a S-214 destravou metade da S-201.** `procedencia.acrescentar` nasceu com ela -- o módulo só
sabia ler --, e toda amostra promovida da quarentena entra com livro, página, data e `humano`. Os
608 mil recortes que já existem continuam com UUID puro e origem perdida: isso é pergunta para o
dono dos dados, e não código.

Três peças, e uma regra:

- **a fila de revisão de caractere**, ordenada por valor de informação, como a S-22 fez para
  diagramas;
- **"aplicar a todos os semelhantes"**: corrigir um `e` lido como `c` e ter de repetir em 300 é
  o que faz uma página custar horas. O critério é a **imagem**, não o caractere lido — casar por
  caractere acharia os 300 errados e junto viriam os `c` legítimos;
- **a coleta em quarentena**: o recorte de baixa confiança vai para `revisao_ocr/<palpite>/`, e
  **só entra na base depois que um humano mover a pasta**.

A regra: **o palpite do modelo nunca entra na base como rótulo.** É a mesma cicatriz das duas
pontas — lá, 127 amostras mal rotuladas treinaram a classe errada sem ninguém notar; aqui, a
verdade de referência contaminada é o achado nº 1 da avaliação de agosto.

---

## As 700 mil imagens: o risco que precisa ser resolvido antes do primeiro treino

> **Atualização de 2026-08-23 — a pasta chegou, e o resto desta seção é a avaliação de risco
> feita antes de vê-la.** O texto abaixo fica como estava, porque ele é o raciocínio que levou à
> ordem da Fase 29 e essa ordem se provou certa. O que a varredura mediu:
>
> - são **608.407 recortes em 314 classes** (0,61 GB), e não ~700 mil — o número que se conta em
>   arquivos, 608.408, inclui um `.learner_cache.npz` que não é recorte;
> - **178.420 imagens distintas**: 70,7% da pasta é cópia byte a byte;
> - **83 grupos sob dois rótulos** ao mesmo tempo (1.557 recortes), quase todos homóglifos;
> - **nenhum registro de livro ou página** — o nome é UUID puro. O split por livro da S-203, que
>   é o único que mede generalização de fonte, **não é executável** sem recuperar isso na origem.
>
> Sobre a suspeita da `training_data_2`: aqui `lower_a` (63.055) e `lower_e` (33.855) estão os
> dois acima de `digit_1` (26.792), que é a ordem que se espera de texto de livro — o sinal
> citado abaixo não dispara. Isso é indício de que a base não é dominada por rótulo de modelo,
> não é prova; a pergunta continua sendo do dono dos dados.
>
> Os números completos e o que eles mudam item a item estão na Fase 29 do
> [`SPEC_TEXTO.md`](SPEC_TEXTO.md).

O material prometido é *"as imagens de todas as classes de caracteres que já verifiquei
manualmente, cerca de 700 mil"*. O `docs/SPEC.md` do PyBoxEditor, §5.2, descreve duas bases:

    training_data/     103 classes, 128.850 imagens   — a base de treino
    training_data_2/    68 classes, 192.600 imagens   — **rótulos suspeitos de serem do modelo**

Sobre a segunda, a spec de lá é explícita, e vale ler a conclusão dela inteira:

> O formato é exatamente o que `LearningService.batch_extract_and_classify` grava. A distribuição
> reforça: a classe maior é `digit_1` (16.962), acima de `lower_e` (16.090) — em texto de livro o
> `e` domina com folga. Um excesso de `1` é a assinatura do classificador confundindo `l`, `i` e
> `I`. **Decisão pendente, e é do dono dos dados**: só quem gerou a pasta sabe se aqueles rótulos
> foram conferidos.

As duas somam 321.450. **O conjunto de 700 mil é maior que as duas juntas**, e a pergunta que
decide a Fase 29 é: *o que são as outras ~380 mil, e a `training_data_2` está dentro?*

Por isso a S-200 e a S-201 vêm **antes** de qualquer treino, e a S-201 exige que cada amostra
carregue de onde veio. Uma amostra sem procedência conhecida não é recusada — ela entra marcada
como `desconhecida` e **fica fora do split de teste**, que é o mínimo para o número final
significar alguma coisa.

Há um segundo sinal que o inventário tem de conferir cedo: a classe `lower_ä` da base de lá
ficou **vazia** porque `cv2.imwrite` devolve `False` em caminho não-ASCII no Windows, sem
levantar erro. Uma classe vazia num inventário de 700 mil passa despercebida com facilidade — e
este é um projeto que roda em Windows.

---

## Riscos e decisões que precisam do dono do projeto

**1. Qual é o leitor de linha.** É a decisão que mais muda o resultado da Fase 26.

| opção | o que custa | o que rende |
|---|---|---|
| EasyOCR, como lá | ~100 MB no primeiro uso; contradiz a promessa do README no uso padrão | é a única com número medido: 72,8% → 91,2% |
| RapidOCR (já é extra aqui) | nada — os modelos vêm no wheel | **nenhum número**; é outro modelo, e o alinhamento da F17 pode render diferente |
| um CRNN de casa, treinado nas 700 mil | uma fase inteira, e dados de **linha**, que a base não tem (ela é de glifo) | controle total, e nada baixa |

A recomendação é **RapidOCR primeiro, medido** (ele já é dependência opcional declarada), com
EasyOCR como opt-in explícito para quem aceitar o download — que é exatamente o desenho que a
S-42 já usa para motores.

**2. A procedência das 700 mil.** Sem resposta, a Fase 29 entrega um número que não se pode
publicar. Ver a seção acima.

**3. O custo por página, e o teto. ✅ medido em 2026-08-26 (S-215).** A S-61 mediu ~2,95 s por
página só do pipeline de diagramas, e a varredura do acervo leva ~10 h. OCR de glifo em página
inteira **soma** a isso, e o número que ninguém tinha agora existe:

    hoje (só diagramas)   0,377 s/página
    o texto soma          0,456 s/página
    total                 0,833 s/página     fator 2,21x  ->  política `sob-demanda`

**O `hoje` não é o 2,95 s da S-61, e nenhum dos dois está errado**: aquele perfil é de uma página
com **6 diagramas**, e a inferência -- 76% do tempo -- escala com o número deles. Por isso o fator
é medido contra a mesma amostra, na mesma corrida, e não contra o número arquivado. Ver
`docs/metrics/texto_custo_20260826.json`.

**4. As fontes.** O PyBoxEditor redistribui `NotoSansSymbols2-Regular.ttf` (com `OFL.txt`),
`SimbolosDeXadrez.ttf`, `SkakNew-Diagram.otf` e `IS-TT-01.TTF`. Só a primeira traz licença no
repositório. **Nenhuma fonte é copiada para cá antes de a licença ser conferida**, e isso
bloqueia parte da S-210 (o PDF pesquisável precisa de fonte que tenha os glifos de xadrez).

**5. Dois modelos torch no mesmo processo.** O classificador de peças (8,8 MB) e o de caracteres
(2,6 MB) passam a conviver. O modelo de threads da S-17 e a escolha de dispositivo precisam
cobrir os dois, e a barra de status precisa dizer qual dispositivo cada um usa.

**6. A classe de ligadura injeta caractere.** Medido lá: em **60 dos 336 caracteres errados**
(18%) o modelo prevê uma ligadura onde a verdade tem um caractere só — `f6` no lugar de `5`. Não
reverte a decisão de ter classes de par, que rendeu +0,4 de F1; diz onde coletar amostra, e é um
balde de erro que a Fase 29 tem de olhar de frente.

---

## Sequenciamento sugerido

```
    S-178 ─ S-179 ─ S-180 ─ S-181 ─ S-182 ─ S-183      Fase 25   (caminho crítico)
                              │                 └──────────────► decisão: segue ou para
                              │
      ┌───────────────────────┴───────────────────────┐
      ▼                                               ▼
    S-200 ─ S-201 ─ S-202 ─ S-203 ─ S-204 ─ S-205    S-184 ─ S-185 ─ S-186 ─ S-187 ─ S-188 ─ S-189
        Fase 29 (começa cedo: é o maior risco)              Fase 26
                          │                                     │
                          │                        ┌────────────┴────────────┐
                          ▼                        ▼                         ▼
                        S-206                  S-190 … S-194            S-195 … S-199
                                                  Fase 27                  Fase 28
                                                     └───────────┬───────────┘
                                                                 ▼
                                                          S-207 … S-211      Fase 30
                                                                 │
                                                                 ▼
                                                          S-212 … S-215      Fase 31
```

Três regras de sequenciamento:

1. **A Fase 25 termina numa decisão.** Se o placar da S-183 não justificar, o plano para ali, e
   o que foi gasto é uma fase.
2. **A Fase 29 começa junto com a 26**, não depois. O inventário das 700 mil é trabalho de
   disco e de decisão humana; ele não bloqueia a segmentação e é bloqueado por nada.
3. **Nada da Fase 30 embarca antes da S-215.** Um leitor de página que triplique o custo de uma
   varredura de 10 h é uma regressão, e o lugar de descobrir isso é antes. **Cumprido em
   2026-08-26**: o fator é 2,21x, e a política que ele escolhe é *texto sob demanda, por página*.
    reprova a corrida em que o custo por página piorar além de 10%,
   e nomeia a etapa.

---

## Como conferir o que já foi implementado

Esta é a parte que responde *"o que disto já existe?"* sem depender de alguém manter uma
checklist à mão.

```bash
uv run cvoff-texto-status
```

O comando lê o manifesto de `src/chess_diagram_ocr/text_status.py` — um item por S-NN, cada um
com uma **sonda**: um módulo que precisa importar, um símbolo que precisa existir, um arquivo
que precisa estar no disco. Ele não pergunta ao documento; ele olha o código. A saída é uma
tabela por fase, com três estados:

    ✅  a sonda achou tudo
    ◐   a sonda achou parte (módulo existe, símbolo não)
    ⬜  nada ainda

Opções:

```bash
uv run cvoff-texto-status --fase 25       # só uma fase
uv run cvoff-texto-status --pendentes     # só o que falta
uv run cvoff-texto-status --json          # para a CI
```

**E há uma trava, que é o que faz isto valer.** `tests/test_text_status.py` compara o manifesto
com a `SPEC_TEXTO.md` e falha quando os dois discordam: item marcado `✅ implementada` no
documento cuja sonda não acha nada, item no manifesto sem seção na spec, item na spec fora do
manifesto. É a mesma ideia da S-134 — documentação não tem compilador, então o que ela tem é uma
suíte que falha quando alguém escreve o que não entregou.
**Três comandos novos respondem a perguntas de escopo, e não de qualidade** (Fase 31 e S-207):

```bash
uv run cvoff-texto-custo        # quanto o texto soma a varredura, etapa a etapa (S-215)
uv run cvoff-texto-semelhanca   # a precisao de "aplicar a todos os semelhantes" (S-213)
uv run cvoff-texto-lado         # quantos diagramas deixam de sair `default` com o glifo (S-207)
```

O primeiro tem `--baseline`: ele **reprova** a corrida em que o custo por página piorar além da
margem, e nomeia a etapa. É a mesma trava do `cvoff-census --fail-on-loss` -- regressão de
desempenho é regressão.
