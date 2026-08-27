# Plano · Treinar o OCR nas imagens de `training_data/`, e ler a página com ele

> **O que este documento é.** O plano de execução do reconhecimento de texto por glifo: o que
> falta, em que ordem, com que comando, e como se sabe que cada passo acabou.
>
> **O que ele não é: especificação nova.** O roadmap é [ROADMAP_TEXTO.md](ROADMAP_TEXTO.md)
> (Fases 25 a 31) e a spec é [SPEC_TEXTO.md](SPEC_TEXTO.md) (S-178 a S-217), e os dois já
> descrevem este trabalho item a item. **Nenhuma S-NN nasce aqui.** Cada etapa abaixo diz qual
> item existente ela fecha; quando plano e spec divergirem, a spec manda.
>
> Medido em 2026-08-23, sobre `training_data/`, `models/char_classifier.pt`,
> `docs/metrics/texto_treino_20260823_*.json` e a saída de `cvoff-texto-status`. Os comandos que
> reproduzem cada número estão na seção 8.

---

## 1. Onde o trabalho está hoje, com número

**O treino já aconteceu.** Isto não é um plano para começar do zero: é o plano para tornar
defensável, e depois útil, um modelo que já está no disco.

    models/char_classifier.pt      314 classes   teste macro 0,9679   acurácia 0,9910
    models/char_meta.json          temperatura 1,5212   sha do par conferido na carga

O que a pasta tem, conferido no disco e não herdado de documento:

| o que | número | onde se confere |
|---|---:|---|
| recortes em `training_data/` | 607.713 | contagem de `*.png` na pasta |
| classes (subpastas) | 314 | uma subpasta por classe |
| imagens distintas | 178.370 | `imagens_distintas` do relatório de treino |
| cópias exatas | 429.343 | `copias_exatas` do mesmo relatório |
| recortes em quarentena | 694 | `data/quarentena_texto/`, com manifesto ao lado |

**A conta fecha com o roadmap, e a diferença é a S-202:** 607.713 + 694 = 608.407, que é o número
que a varredura de 2026-08-23 mediu antes de os rótulos contraditórios saírem da base. Ninguém
apagou nada -- os 694 foram *movidos*, e o manifesto diz de onde.

O estado por item, medido por `cvoff-texto-status` (sonda no disco, não opinião):

    Fase 25  A fronteira                6/7      só a S-183, e o que falta nela é humano
    Fase 26  Do pixel à linha           6/6      fechada nas Etapas 8 e 9 (2026-08-24)
    Fase 27  A coluna                   6/6      fechada
    Fase 28  Os casos que apagam texto  5/5      fechada na Etapa 1 (2026-08-23)
    Fase 29  A base de 608 mil          5/7      S-201 e S-203 esperam a origem responder
    Fase 30  O que o texto lido serve   0/5
    Fase 31  O que faz a base crescer   0/4

    Total: 28 atendidas, 3 parciais, 9 pendentes, de 40 itens.

**As Etapas 1 a 10 já foram feitas, menos a 7** -- ver a seção 4. O quadro acima é o de depois delas, e as
três parciais são a S-183 (falta trabalho humano) e a S-201/S-203 (falta o registro na origem).

---

## 2. O fato novo que reordena tudo: os pesos deixaram de faltar

Seis itens deste plano estão escritos com a frase *"depende dos pesos de 292 classes, que não
estão nesta máquina"*. **Isso era verdade até 2026-08-23 e não é mais.** O treino da S-204 não
foi um adiantamento de escopo: foi a saída do bloqueio, porque os pesos do PyBoxEditor
(sha `2009f803…`) não existem em nenhuma cópia local, e as que existem trazem 128, 150 e 155
classes, em formato 1, sem calibração.

**O que isso destrava, e o que continua trancado:**

| item | estava esperando | está esperando agora |
|---|---|---|
| S-183 · placar da faixa | pesos | **as 123 faixas de referência conferidas à mão** -- 0 de 123 têm `texto` |
| S-186 · o colado na horizontal | um árbitro, que é o classificador | nada -- é executável |
| S-188 · ler a linha | a tabela da S-183, para escolher o leitor | a S-183, e a decisão do motor de linha |
| S-189 · confiança calibrada | pesos calibrados | nada -- a temperatura existe desde 2026-08-23 |
| S-197 · texto girado | um árbitro para os quatro ângulos | nada -- é executável |
| S-198 · box de duas linhas | idem | nada -- é executável |

**O que não mudou:** este não é o modelo de 292 classes do PyBoxEditor, é o de casa, com 314
classes e treinado nesta base. Todo número herdado de lá -- os 72,8% por caractere, os 91,2% por
linha -- continua sendo hipótese até ser remedido aqui. É exatamente o que a S-183 e a S-188
pedem.

---

## 3. As duas dívidas que nenhum trabalho local paga

Elas são a mesma dívida vista de dois ângulos, e as duas saem da mesma falta: **o recorte não diz
de onde veio.** Os arquivos se chamam `<uuid>.png`, não há sidecar, não há índice, e o `mtime` é
de uma migração em massa -- 70% deles carregam a mesma data.

1. **Procedência (S-201).** O relatório do modelo publicado declara, por extenso:
   `procedencia: {humano: 0, modelo: 0, desconhecida: 607713}`. A regra da S-201 diz que amostra
   `desconhecida` entra no treino e **nunca** em validação nem teste. Aplicada hoje ao pé da
   letra, ela deixa o conjunto de teste vazio -- não sobra métrica nenhuma.
2. **Livro (S-203).** Sem livro não existe o teste do "livro novo", e **nenhum número deste plano
   mede generalização de fonte**. O que existe é o degrau abaixo, entregue e travado por teste:
   `split_por_grupo`, o relatório de vazamento, e o `cvoff-texto-train` que **recusa treinar** se
   um grupo aparecer em dois lados.

**A ação que paga as duas é uma só, e não é aqui: recuperar `uuid -> (livro, página, quem
rotulou)` no `PyBoxEditor_Tkinter`**, que foi quem recortou.

**Desde 2026-08-23 o lado de cá está pronto e esperando** (Etapas 3 e 4): o formato está definido
em `text/procedencia.py`, o split por livro está implementado e travado por teste, o `cvoff-audit`
já reprova rótulo de modelo no teste, e as duas S carregam a sonda
`arquivo:data/texto_procedencia.csv` para que nenhuma diga `implementada` enquanto o arquivo não
existir. O que falta é o arquivo:

    uuid,livro,pagina,procedencia,rotulado_em
    00001b60-272a-46f2-9dbf-044fe779e336,Yusupov Build Up 1,212,humano,2026-02-16
    0000f4c1-8e2c-4b71-9a10-2b7f6d3e5a44,,,,

Célula vazia é permitida e quer dizer "não se sabe"; a linha que falta quer dizer a mesma coisa,
e as duas caem na mesma regra -- a diferença é que a primeira é uma ausência **declarada**.

Enquanto ele não chega, a regra deste plano é a que a S-204 já aplicou: **o número sai com a
ressalva escrita no próprio relatório**, no campo `split`, e não numa nota de rodapé que se perde
na citação.

---

## 4. As etapas, em ordem

Cada etapa diz: **o que fecha**, por que vem agora, o que se faz, e como se prova que acabou. O
tamanho é relativo -- P (uma sessão), M (algumas), G (uma fase inteira).

### Etapa 1 · Colher o que os pesos destravaram -- P ✅ **feita em 2026-08-23**

**Fechou:** S-182, S-197 e S-198. A Fase 28 passou a 5/5 e a Fase 25 a 6/7 -- só a S-183 continua
aberta ali, e o que falta nela é humano.

**O que se fez, e o que cada coisa mediu.**

**S-197 -- a tabela dos quatro ângulos.** `cvoff-texto-vertical`, 534 linhas de 30 livros. O
acervo é de texto de pé, então a linha é **girada por transposição** (`vertical.girar`, novo, o
avesso de `endireitar`): a ida e a volta fecham byte a byte, e a resposta certa vem ao lado da
leitura sem custar anotação.

    lido a       0°       90°      180°     270°
              0,8572   0,5061   0,6992   0,5143      argmax da média: 0,9363 (500 de 534)

A matriz é **circulante**, e isso é a prova de que a simulação está certa -- girar a página
permuta as leituras e nada mais. Por isso as quatro fileiras dão o mesmo acerto por construção:
há um número, não quatro. Em produção (`decidir_angulo`, que só tenta 0, 90 e 270): **0,9775** de
não mexer no texto de pé, **0,9195** e **0,9326** de marcar o girado, e **0,9176** de deixar
quieta a linha de 180°, que não é candidata.

**S-198 -- o ganho do corte, e um dos dois passos não paga.** `cvoff-texto-duas-linhas`, 155
faixas de 11 livros, cada faixa dilatada em 2 pt:

    cru                 CER 0,2725
    descarte            CER 0,2248     ganho de 0,0477   -> entrou no GlyphRecognizer
    descarte e corte    CER 0,2337     custo de 0,0089   -> ficou fora

`descartar_fragmentos` está no caminho de leitura desde esta medição. `separar` continua
implementado, travado por teste e **não chamado**: disparou em 15 das 155 faixas e piorou o
número. Lá ele valia +0,3 de F1.

**S-182 -- o rodapé diz o dispositivo dos dois modelos.** A zona nova mostra `peças cuda:0 ·
texto cpu`, com a descrição inteira na dica. Três estados para o de caracteres, e o terceiro era
o que faltava: `sem pesos` (o `.pt` não está no disco) é diferente de `desligado` (os pesos estão
lá e o motor escolhido é outro). O `packaging/cvoff.spec` passou a nomear o classificador de
caracteres na lista do que **não** entra no bundle, e o `--selftest` diz em qual estado a
instalação está sem mexer no código de saída.

**Os três achados que a etapa não previa.**

1. **Metade do acervo tem camada de texto gerada por OCR**, e medir CER contra ela é comparar
   dois palpites: a primeira corrida da S-198 deu **0,8644** por isso. `camada_de_ocr` (da S-216)
   nomeia 20 livros, e eles saem da medição listados um a um. **O `AAGAARD` é um deles** -- e é
   a página com que a Fase 26 mediu 0,21 → 0,14 → 0,22. A comparação relativa de lá continua
   válida; o 0,14 não é erro contra a verdade, e não deve ser citado como se fosse.
2. **A margem herdada sobrevive à calibração**, ao contrário do que uma corrida de fumaça de uma
   linha só sugeriu: a folga mediana é +0,3761 a 90 e +0,3881 a 270, contra a margem de 0,05.
   Está registrado na spec porque é o argumento de por que o item mede em vez de amostrar.
3. **Perguntar o dispositivo ao `CaptionReader` quebrava o digest dos relatórios de campo.**
   `ocr_caption.py` está no fecho de importação do `cvoff-field`, e uma propriedade nova ali
   invalidaria a S-219 por causa de uma linha de rodapé. A pergunta passou a ir ao cache de
   `text/modelo.py`, que é podado desse digest.

**O que ficou de dívida, e é pequena:** a catraca de `app_tkinter.py` subiu de 1.776 para 1.788
linhas, com o motivo registrado em `tests/test_packaging.py` e no `ROADMAP_FASE14`.

---

### Etapa 2 · O inventário, e o manifesto que fixa os números -- P ✅ **feita em 2026-08-23**

**Fechou:** S-200.

`cvoff-texto-inventario`, novo. Varre a pasta e grava dois arquivos em `docs/metrics/`: o
manifesto (`texto_inventario_<data>.json`) e o relatório de procedência
(`texto_procedencia_<data>.json`). Dois, e não um com duas seções -- eles envelhecem em ritmos
diferentes, e juntá-los faria o segundo parecer atualizado toda vez que o primeiro fosse refeito.

**A pasta está limpa nas três coisas que o item existia para pegar**, e isso é resultado e não
anticlímax: são os três defeitos que passam despercebidos entre 314 linhas iguais.

    recortes                                607.713 em 314 pastas
    tamanho em disco                        0,44 GB
    imagens distintas (somadas por classe)  178.370
    classes vazias                          0
    pastas cujo nome não decodifica         0
    PNGs ilegíveis                          0
    classes com menos de 3 recortes         52

**O número que divergia tem explicação, e agora tem manifesto.** Os 178.420 do roadmap contra os
178.370 do relatório de treino: os 694 recortes que a S-202 mandou para quarentena levaram junto
**50 grupos inteiros**. O mesmo para o total, 608.407 → 607.713.

**As 52 classes com menos de três recortes são o insumo da decisão que a Etapa 6 tem de tomar** --
são elas que produzem as 58 classes sem uma única amostra no teste.

As três regras do item estão travadas por teste: o comando **não escreve nada** dentro da pasta
inventariada (conferido por `mtime` de todos os arquivos), lê com `imdecode` e nunca com `imread`
(conferido no **código**, via `ast`, para que o cabeçalho possa explicar a regra), e nomeia os
achados em seção própria.

---

### Etapa 3 · A procedência declarada, mesmo valendo `desconhecida` -- P ✅ **feita em 2026-08-23**

**Fechou:** a metade local da S-201. O item continua `◐`, e o que falta não é código.

**O contrato do arquivo, escrito antes de o arquivo existir:** `text/procedencia.py` define
`data/texto_procedencia.csv` -- `uuid,livro,pagina,procedencia,rotulado_em` --, os três valores e
a regra que cada um carrega. Célula vazia é permitida e **não** é o mesmo que a linha não
existir: uma é ausência declarada, a outra é ausência descoberta.

**A regra entra no split por uma máscara, e não por um filtro.** `split_por_grupo` e
`split_por_livro` recebem `medivel`, e o **grupo** que contiver uma amostra não-medível fica
inteiro no treino -- filtrar amostra a amostra quebraria a atomicidade do grupo.

**O `cvoff-audit` passou a cobrar**, lendo `docs/metrics/texto_vazamento.json`: reprova rótulo de
`modelo` no teste sempre, e rótulo `desconhecido` no teste **quando há registro no disco**.

**A decisão que a etapa forçava, resolvida assim:** sem registro nenhum, aplicar a regra ao pé da
letra deixaria validação e teste vazios -- não haveria número. O caminho sem registro mede assim
mesmo e grava a ressalva onde ela é lida junto com o número. No dia em que o arquivo existir, a
regra passa a valer sozinha, e `--desconhecida-no-teste` é o único jeito de desligá-la, deixando
rastro. **Nenhuma flag é necessária hoje**, e é isso que evita a permissão que ninguém revoga.

**O aviso de distribuição não dispara nesta base**, e o relatório diz isso: `lower_a` (63.055) e
`lower_e` (33.855) estão os dois acima de `digit_1` (26.792). Indício de que a base não é
dominada por rótulo de modelo -- não é prova.

---

### Etapa 4 · O contrato da procedência -- M ✅ **o lado de cá está pronto**

**Fechou:** o código inteiro da S-203. O item é `◐` porque **nada disso rodou sobre livro de
verdade** -- os cinco critérios de aceite estão cumpridos em base sintética, com teste, e a base
real não tem livro.

`dataset.split_por_livro`, chamado por `cvoff-texto-train` quando há registro de livro; sem ele o
comando cai para `split_por_grupo` e **escreve por extenso qual dos dois usou**. Três regras, e as
três são a mesma vista de ângulos diferentes: amostra sem livro fica no treino, amostra não-medível
fica no treino, e o grupo que atravessa dois livros volta ao treino inteiro.

**Um livro de cada lado é reservado antes de distribuir o resto.** A distribuição proporcional
pura falha com livro desigual: com um de 900 e dois de 50, encher o teste até a fração consome
dois dos três e deixa a **validação vazia** -- e sem validação não há época escolhida nem
temperatura. Reservar primeiro transforma "existe um livro só do teste" de probabilidade em
garantia. Menos de três livros levanta, em vez de improvisar.

**O relatório de vazamento virou artefato próprio:** `cvoff-texto-train --so-split` parte,
confere e grava `docs/metrics/texto_vazamento.json` em um minuto a partir do cache, sem treinar.
Um relatório que só existisse depois de um treino inteiro não seria refeito a cada mudança de
semente -- e o critério pedia um que rodasse de verdade.

**Dois defeitos que a primeira corrida com livro de verdade pegou, e os dois viraram teste.**
O primeiro é de desenho: a máscara da S-201 estava sendo aplicada *dentro* do split por livro, e
com rótulo de modelo espalhado isso punha o mesmo livro dos dois lados -- `livros_em_dois_lados`
acusou, e o comando recusou treinar. O segundo é de higiene: o caminho do relatório de vazamento
era fixo, então a corrida sobre base sintética **sobrescreveu o relatório publicado** e o
`cvoff-audit` passou a auditar a base de mentira sem que nada dissesse isso. Agora é `--vazamento`.

**O que continua sendo de fora, e é o pedido:** exportar `uuid -> (livro, página, quem rotulou)`
no `PyBoxEditor_Tkinter`. A sonda `arquivo:data/texto_procedencia.csv` está nas duas S (201 e 203)
para que nenhuma delas diga `implementada` enquanto o arquivo não existir.

---

### Etapa 5 · A calibração medida, e não só aplicada -- P ✅ **feita em 2026-08-23**

**Fechou:** S-205.

`text/calibracao.py`, novo — `calibrar`, a curva de confiabilidade, os dois ECE e a prosa saíram
de `text/treino.py`, que era onde a sonda do item já dizia que eles não deviam estar. A separação
não é arrumação: a curva é medida sobre um modelo que **já existe** tantas vezes quanto sobre um
recém-treinado, e enterrá-la no treino obrigaria a retreinar para medir.

`cvoff-texto-train --so-calibracao` carrega o par publicado, refaz os logits crus sobre as 13.693
imagens de validação e grava `docs/metrics/texto_ece_<data>.json`. Não treina.

**A trava do item virou número:** temperatura publicada **1,5212**, refeita agora **1,5211**. O
metadado descreve o modelo que está no disco — antes isso era promessa.

**E o achado é a distância entre as duas réguas:**

    ECE ponderado    antes 0,0040  ->  depois 0,0037
    ECE por faixa    antes 0,1131  ->  depois 0,1080     <- é este que decide

**Trinta vezes**, e a causa é aritmética: 96% das amostras caem numa faixa só, a de 0,93 a 1,00,
onde o modelo diz 0,998 e acerta 0,998. O ECE ponderado mede aquela faixa e mais nada. **É a mesma
lição da macro contra a acurácia**, agora aplicada à calibração — e a segunda vez que ela aparece
nesta fase.

**A faixa que o ponderado esconde é a única em que alguma coisa é decidida.** O corte de legenda
adivinhada está em 0,30; os árbitros da S-186, da S-197 e da S-198 comparam confianças no meio da
escala. Lá o modelo é **pessimista**: onde diz 0,83, acerta 0,94.

| faixa | n | ele diz | ele acerta |
|---|---:|---:|---:|
| 0,60–0,67 | 40 | 0,630 | 0,775 |
| 0,80–0,87 | 91 | 0,830 | 0,945 |
| **0,93–1,00** | **13.164** | **0,998** | **0,998** |

A temperatura melhorou isso pouco porque **ela minimiza a NLL, e não o ECE** — e essa distinção
não tinha como aparecer antes deste relatório. O que ela fez de fato, visto pela contagem: empurrou
**258 amostras** para fora da faixa do topo, espalhando-as por 0,53–0,93, que é justamente a região
que as quatro decisões consultam.

**A segunda trava também entrou:** `treinar` chama a calibração dentro de um `try`, e a falha vira
temperatura 1,0, rastro no log e `falhou: True` no resultado — nunca um `.pt` calado. Um modelo com
temperatura 1,0 e um aviso é pior que um calibrado e muito melhor que nenhum modelo depois de vinte
épocas de CPU.

---

### Etapa 6 · O que ainda faltava do critério da S-204 -- M ✅ **feita em 2026-08-23**

**Fechou:** o resto da S-204 — o aumento de dados aplicado a caractere, a grade de variantes, e a
decisão sobre as classes que nenhuma medição alcança.

**A grade, seis braços, 10 épocas cada com a mesma semente e o mesmo split:**

| braço | val macro | val acurácia | parâmetros | segundos |
|---|---:|---:|---:|---:|
| pesos-de-classe | **0,9647** | 0,9871 | 617.216 | 659 |
| controle | 0,9632 | **0,9898** | 617.216 | 626 |
| aumento-leve | 0,9598 | 0,9883 | 617.216 | 714 |
| densa-128 | 0,9554 | 0,9882 | 354.944 | 661 |
| canais-menores | 0,9430 | 0,9835 | 154.496 | **286** |
| aumento-forte | 0,9420 | 0,9851 | 617.216 | 776 |

**A grade não achou vencedora, e é isso que a tabela diz.** O primeiro ganha do controle por
**0,0015**, e a S-204 já tinha medido que o ruído da macro entre épocas consecutivas desta base é
**0,0068** — quatro vezes maior. O segundo colocado ainda ganha na acurácia. O `test` confirmou a
vencedora (macro 0,9543) para fechar o protocolo, e **nada foi promovido**: trocar o publicado por
outro que empata dentro do ruído seria mexer por mexer.

**O aumento de dados não paga, e é a terceira vez.** A Fase 5 mediu que o aumento genérico não
ajudou para peças; a S-204, que os pesos de classe não ajudaram para caractere; agora o aumento
dirigido ao glifo também não. Três hipóteses que todo mundo assume, três medições, três nãos.

**E o módulo existe mesmo assim, porque responde uma pergunta que ninguém tinha feito:**
`text/aumento.py` não é o de peças aplicado a caractere. **Espelhar é a degradação mais barata lá
e a mais danosa aqui** — um `b` espelhado é um `d`, e os pares que ele ensinaria a confundir são
os 83 grupos de rótulo contraditório da S-202. Sete degradações de scanner e gráfica, nenhuma troca
de eixo, e dois testes que impedem uma de voltar por engano.

**A hipótese da S-204 sobre a forma virou trade-off medido**, não veredito: `densa-128` custa
0,0078 de macro e economiza 43% dos pesos; `canais-menores` custa 0,0202 e roda em **286 s contra
626** — menos da metade do tempo, numa máquina que treina em CPU.

Para isso a forma precisou **virar dado**: `modelo.Arquitetura` no metadado, lida por
`carregar_classificador`. Um braço que mudasse canais produziria pesos que `load_state_dict`
recusa, e a saída é a que a própria S-204 apontava — a grade muda os dois lados de uma vez ou não
muda nenhum.

**O terceiro eixo que o critério nomeia — a resolução — não tem braço, e o motivo é o de sempre.**
`LADO` é 32 porque a base inteira foi gravada assim, e 58% dos recortes já chegaram nesse tamanho.
Treinar em 64 seria ampliar um recorte de 32 (não acrescenta informação) ou reextrair da página —
que **esta base não permite**, porque nenhum recorte sabe de que página veio. É a mesma falta que
trava a S-201 e a S-203, pela terceira vez.

**A decisão sobre as 58 classes que nenhuma medição alcança, com o número que faltava:** elas são
previstas **duas vezes em 13.693** amostras de teste. **Mantê-las, declarando `n=0` por classe** —
cortá-las tiraria 99 recortes de trabalho humano do modelo para eliminar duas previsões em treze
mil, e a classe cortada não some: ela volta como erro na vizinha.

---

### Etapa 7 · O placar da faixa -- **o portão continua fechado, e a chave é humana** ◐

**Fecha:** S-183. E ela não fechou, porque o que falta não é código.

As 123 faixas de `docs/metrics/texto_faixa_referencia.jsonl` continuam com `conferido: false`, e a
medição as recusa -- **que é o desenho certo**: é o único ponto do processo em que alguém compara
o texto com a página impressa, que é onde a verdade está. Uma referência vinda de um motor faria a
tabela medir o motor contra ele mesmo.

**O que foi feito em 2026-08-24 é tornar essa transcrição barata.**
`cvoff-texto-placar --exportar <pasta>` grava um PNG por faixa -- **exatamente a imagem que os
motores leem**, a banda dilatada em `radius_pt` com o interior do diagrama apagado. Transcrever
deixou de exigir abrir 27 PDFs nas páginas certas 123 vezes; virou olhar 123 imagens.

**E o outro lado da mesma conta: `cvoff-texto-transcrever`.** Olhar 123 imagens ainda deixava
a metade chata — achar a linha certa do `.jsonl`, digitar com aspas escapadas e trocar a marca,
123 vezes, sem nada que contasse quanto falta. A janela põe o PNG à esquerda e o campo à
direita, abre na primeira pendente, grava na forma que o placar lê e mostra o placar de
conferidas. **Ela não tem, e não vai ter, um botão de preencher com OCR** — pelo mesmo motivo
que a medição recusa o não-conferido. O que a janela não muda é o portão: a transcrição
continua humana, e continua sendo 123.

**É o único pedido humano que trava três coisas ao mesmo tempo:** o portão da Fase 25, o critério
de aceite da S-186 (que teve de medir contra a camada editorada) e a régua forte da S-189.

---

### Etapa 8 · O leitor de linha e a confiança por concordância -- G ✅ **feita em 2026-08-24**

**Fechou:** S-188 e S-189.

    CER por caractere   0,2248
    CER por linha       0,2230     ganho de +0,0018

**O ganho de 18,4 pontos que este plano prometia virou 0,0018.** O roadmap avisava que o 91,2% era
do `english_g2` do EasyOCR e não atravessaria a troca de motor sem medição -- atravessou como
zero, com o RapidOCR que ele mesmo recomendava. A leitura por linha **fica desligada**, que é o
que o critério manda fazer com um ganho assim.

**E a outra metade paga sozinha.** Sobre os mesmos 6.816 caracteres:

| as duas leituras | n | na referência | confiança média |
|---|---:|---:|---:|
| concordam | 4.935 | **0,9856** | 0,9672 |
| divergem | 1.881 | **0,4822** | 0,8405 |

Onde as duas discordam, metade está errada; onde concordam, 1,4% está. **A discordância é o melhor
sinal de erro que este projeto tem** — e é exatamente o que a fila de revisão da S-212 precisa
para ordenar trabalho humano. O leitor de linha entra como **segundo opinante**, não como leitor.

**E a curva mostrou que essa confiança ordena bem e mede mal:** ECE 0,1490 ponderado e 0,3416 por
faixa. Onde ela diz 0,99 acerta 0,88; onde diz 0,36 acerta 0,98. A causa estava escrita na spec
antes da medição — metade da comparação está calibrada (o glifo, pela S-205) e a outra metade não
(a confiança do RapidOCR nunca passou por calibração). **Ela serve para ordenar a fila da S-212, e
não para cortar por limiar.**

**Um defeito de forma que virou teste:** a âncora do alinhamento tinha um caractere por caixa, e as
classes de ligadura devolvem dois (`fi`, `xf6`, `♗a`). A correção não é alargar a âncora — é
lembrar de que caixa veio cada posição dela, e regrupar depois.

---

### Etapa 9 · O colado na horizontal -- M ✅ **feita em 2026-08-24**

**Fechou:** S-186, e a resposta é que ele fica desligado.

    modo       CER      cortes   faixas com corte
    nunca     0,2248        0        0            <- o padrão
    auto      0,2400       48       33
    sempre    0,5034      617      127

**O árbitro não salva o separador: ele só reduz o estrago.** E a conclusão não é do limiar — o
braço `auto` foi refeito em cinco larguras suspeitas e perde em todas, com a curva monótona
apontando para o óbvio: quanto menos ele corta, melhor. Sem essa varredura, "o separador piora"
seria indistinguível de "o limiar estava mal escolhido".

A explicação estava na spec **antes** da medição: as classes de ligadura já absorvem o problema.
O modelo lê `fi` inteiro, e o que o separador acha para cortar são glifos que ele já lia bem.

---

### Etapa 10 · O placar honesto, com as duas réguas -- P ✅ **feita em 2026-08-24**

**Fechou:** S-206.

| régua | valor | n |
|---|---:|---:|
| acurácia do classificador | **0,9910** | 13.693 recortes |
| acerto na página (1 − CER) | **0,6555** | 22 páginas |
| F1 de caractere na página | 0,7663 | 22 páginas |
| **livro novo** | **n/d** | 0 — não existe nesta base (S-203) |

**A distância é de 33,5 pontos, e ela é o trabalho que sobra.** O classificador acerta o recorte
que lhe dão; o que a página perde está em *achar* o recorte. O comando **recusa** publicar só a
primeira linha.

**E depois desta fase, os itens que atacavam essa distância são menos do que se esperava:** a
S-186 mediu que o separador piora e a S-188 que a leitura por linha empata. O que sobra apontando
para o meio dela é a segmentação (S-185), o texto girado (S-197) e o trabalho humano da S-212.

> **Um defeito que a primeira corrida escondeu.** O detector era chamado com `page.parent` onde
> ele espera o **caminho**: a abertura falhava, o `except` engolia, e a página era medida sem
> exclusão de diagrama. Silencioso por construção — aquele `except` existe para a detecção não
> derrubar a medição.

---

## 5. A ordem, e por que ela é essa

    E1 colher o destravado ──┐
    E2 inventário ───────────┼──► E3 procedência local ──► E5 ECE ──► E6 grade e augment
    E4 contrato do livro ────┘        (paralelas entre si; nenhuma bloqueia a outra)
                                                  │
    E7 PLACAR DA FAIXA  ◄─────────────────────────┘   ◄── portão: decide se o resto acontece
        │
        ├──► E8 leitor de linha + confiança      (o maior ganho, e o maior custo)
        ├──► E9 o colado
        └──► E10 placar honesto

Três regras de sequenciamento, e as duas primeiras vêm do roadmap:

1. **A Etapa 7 é um portão.** Se o glifo não ganhar do RapidOCR na faixa deste acervo, as etapas 8
   a 10 não se justificam, e o que foi gasto é uma fase -- que é o desenho da Fase 25.
2. **E1 a E6 não esperam o portão.** São inventário, procedência, calibração e medição da base:
   trabalho de disco que nada bloqueia, e que o portão não invalida.
3. **E4 tem uma metade que não é nossa.** Ela começa hoje pelo contrato e termina quando o
   `PyBoxEditor_Tkinter` responder. Nada mais espera por ela -- só os três critérios da S-203 que
   falam de livro.

---

## 6. Definição de pronto, medida pela máquina

O projeto já tem o juiz: `cvoff-texto-status` lê o disco e diz quais sondas existem. Este plano não
inventa outro critério.

| etapa | fecha | sonda que passa a existir |
|---|---|---|
| E1 ✅ | S-197, S-198, S-182 | `metrica:texto_vertical`, `metrica:texto_duas_linhas`, `ui.rodape:dispositivo_do_classificador_de_caracteres` |
| E2 ✅ | S-200 | `cli.texto_inventario:main`, `metrica:texto_inventario` |
| E3 ✅ | S-201 (metade local) | `text.dataset:procedencia_de`, `metrica:texto_procedencia` |
| E4 ◐ | S-203 -- o código; falta o dado | `text.dataset:split_por_livro`, `metrica:texto_vazamento` |
| E5 ✅ | S-205 | `text.calibracao:calibrar`, `metrica:texto_ece` |
| E6 ✅ | S-204 (resto do critério) | `metrica:texto_variantes` -- a sonda do item já estava atendida |
| E7 ◐ | S-183 | `metrica:texto_faixa` -- falta a transcrição humana das 123 faixas |
| E8 ✅ | S-188, S-189 | `text.leitura_de_linha:em_bloco`, `…:confianca_por_concordancia`, `metrica:texto_linha`, `metrica:texto_calibracao` |
| E9 ✅ | S-186 | `text.colados:separar`, `metrica:texto_colados` |
| E10 ✅ | S-206 | `metrica:texto_placar_final` |

Ao fim das dez, as Fases 25, 26, 28 e 29 fecham -- **menos os três critérios da S-203 que exigem
livro**, que continuam abertos até a origem responder, e é assim que devem aparecer.

---

## 7. O que precisa do dono, e não de código

1. **Transcrever as 123 faixas de referência** (Etapa 7). É o portão do plano inteiro, e a única
   coisa que nenhum comando pode fazer sozinho sem virar circularidade -- a referência não pode
   ser a leitura de um motor. O que existe para ajudar é `cvoff-texto-placar --exportar` (os
   PNGs) e `cvoff-texto-transcrever` (a janela); o que sobra é olhar e digitar.
2. **Exportar `uuid -> (livro, página, quem rotulou)` do `PyBoxEditor_Tkinter`** para
   `data/texto_procedencia.csv` (Etapas 3 e 4, e o formato já está definido). Sem esse arquivo
   nenhum número deste plano mede generalização de fonte, e a regra da S-201 não pode valer sem
   zerar a medição. **É o único pedido de fora que trava dois itens ao mesmo tempo.**
3. **Qual leitor de linha** (Etapa 8). RapidOCR (nada baixa, nenhum número medido) contra EasyOCR
   (~100 MB no primeiro uso, e é de onde vem o 91,2%) contra um CRNN de casa (uma fase inteira, e
   dados de **linha**, que esta base não tem -- ela é de glifo). Recomendação: RapidOCR primeiro,
   medido, com EasyOCR como opt-in explícito.
4. **As fontes.** Nenhuma fonte do PyBoxEditor é copiada para cá antes de a licença ser conferida;
   só a `NotoSansSymbols2` traz licença no repositório de lá. Isto bloqueia parte da S-210, que é
   Fase 30 e está fora deste plano.

---

## 8. Como reproduzir o que já está medido

    cvoff-texto-status                      # o placar de itens contra o disco

    cvoff-texto-train --so-varrer           # varre e relata a base, sem treinar
    cvoff-texto-train                       # o treino publicado: split por grupo, quase-duplicata, calibração
    cvoff-texto-train --pesos-de-classe     # o braço que foi medido e reprovado
    cvoff-texto-train --todos-os-recortes   # o braço com as cópias, 3,5x por época

    cvoff-texto-conflitos                   # os grupos sob dois rótulos, e a quarentena
    cvoff-texto-placar --exemplo            # o formato de uma linha da referência da faixa

    cvoff-texto-vertical                    # a tabela dos quatro ângulos (S-197)
    cvoff-texto-duas-linhas                 # o ganho do descarte e do corte (S-198)

Os relatórios das corridas de 2026-08-23 estão todos em `docs/metrics/`, e continuam lá pelo mesmo
motivo que a `ANALISE_DETECCAO` arquiva duas corridas do detector: comparar contra um arquivo que
foi sobrescrito não é comparar.

    texto_treino_20260823_s204.json        macro 0,9754   acurácia 0,9925   a base como veio
    texto_treino_20260823_s202.json        macro 0,9741   acurácia 0,9928   sem os rótulos contraditórios
    texto_treino_20260823_s202quase.json   macro 0,9679   acurácia 0,9910   irmãs não atravessam o split
    texto_treino_20260823_pesos.json       macro 0,9691   acurácia 0,9903   pesos de classe, não promovido

**O que está em `models/` é o terceiro**, e o mais baixo dos quatro na macro é o mais honesto: ele
é o único cujo split impede que a mesma renderização caia dos dois lados.

---

## 9. O que este plano deliberadamente não faz

- **Fase 30** -- lado a jogar por glifo, notação validada, léxico, PDF pesquisável e o modelo de
  página. Nada dela embarca antes de a S-215 medir o custo por página: a varredura do acervo já
  leva ~10 h, e OCR de glifo em página inteira **soma** a isso.
- **Fase 31** -- a fila de revisão de caractere, o "aplicar a todos os semelhantes" e a coleta em
  quarentena. É o laço que faz a base crescer, e ele só faz sentido depois que a página é lida.
- **Treinar um leitor de linha de casa.** Exige dados de **linha**, e `training_data/` é de glifo.
  Está na tabela da seção 7 como o que é: uma fase inteira, não uma etapa.
- **Consertar rótulo na origem.** É o que mais renderia (Etapa 6), e é trabalho no outro projeto --
  aqui só se registra o que a medição achou, classe por classe.
