# Especificação da prosa precisa — Fases 100 a 107 (S-700 a S-772)

Base: [ROADMAP_TEXTO_PRECISO.md](ROADMAP_TEXTO_PRECISO.md), que traz o número de 2026-10-30, o
diagnóstico, as metas com os portões, as decisões do dono e a ordem dos itens. A linha de base está em
[metrics/texto_prosa_20261030.json](metrics/texto_prosa_20261030.json), e os scripts que a mediram em
`docs/metrics/texto_prosa_2026-10-30/`. O reconhecimento que estes itens medem e consertam é o da
[SPEC_TEXTO.md](SPEC_TEXTO.md).

> **Onde mora a spec de cada item (S-NN).**
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143, S-175, S-176, S-454, S-455 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170, S-177 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-294, S-295, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293, S-521 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-451 a S-453 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |
> | S-507 a S-520 | [SPEC_ESTUDO_QT.md](SPEC_ESTUDO_QT.md) |
> | S-522 a S-526 | [SPEC_REVISAO_EXTERNA_2.md](SPEC_REVISAO_EXTERNA_2.md) |
> | S-500 a S-506, S-527 a S-580 | [SPEC_SUITE.md](SPEC_SUITE.md) |
> | S-581 a S-584 | [PLANO_COLUNAS_SOLUCOES.md](PLANO_COLUNAS_SOLUCOES.md) |
> | S-601 a S-668 | [SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md) |
> | S-702 | [SPEC_TEXTO_PRECISO.md](SPEC_TEXTO_PRECISO.md) |

Cada item traz o problema (com número quando há), a decisão, onde mora, e o **critério de aceite**,
escrito para virar teste. A spec nasce com o primeiro item entregue, e os outros entram aqui quando
forem entregues; até lá, o que vale para eles é o roadmap.

## Fase 100 — A régua da prosa

### S-702 · Conjuntos ouro-dev e ouro-teste congelados, com admissão que não usa motor nenhum

**Problema.** Todos os números de prosa de 2026-10-30 foram medidos em livros que serviram para
desenhar a régua, a taxonomia e as regras de fusão: dev contaminado. Um portão medido neles promete
só o que já foi visto. E a referência é a camada do PDF, que só vale quando é a tinta: o
*Gaprindashvili* parece editorado e tem a notação em lixo de OCR; o ClearScan tem glifo vetorizado e
Unicode de OCR; o *Kemeri* é scan com camada invisível e um carimbo visível.

**Decisão.** Três peças, todas sem motor de leitura nenhum:

1. **A admissão** (`src/chess_diagram_ocr/text/admissao.py`), os critérios (a)–(d) do roadmap,
   portados sem mudança do protótipo `admissao.py` de 2026-10-30. A função é `admitir_folha(pagina,
   retangulos, *, produtor, perfil)`; a decisão em si é `decidir(trechos, ...)`, pura, e é o que os
   testes exercitam. O perfil de livro (30 folhas igualmente espaçadas, só `get_texttrace`) é
   `perfil_do_livro(documento)`, calculado uma vez por documento aberto. Os retângulos de diagrama
   entram de fora — a S-716 tem os do glifo, e o sorteio os pega da montagem da camada —, e o módulo
   não chama leitor nenhum. Lê o PDF por conta própria, e não pelo `pdf_text.py`, que está no digest
   da S-218. É a função que a S-716 vai reaproveitar. Do regex de fonte de diagrama do protótipo
   saíram `skaknew-diagram`, `diagramtt` e `chessalpha`, que `diagram` e `alpha` já cobrem: a decisão
   não muda, e cada alternativa que ficou tem um teste que a pega sozinha.
2. **O manifesto** (`assets/texto_prosa/ouro.json`, versionado, fora de `data/`, lido pela raiz do
   projeto e listado em `VERSIONADOS` da disciplina da suíte) e o módulo que o lê, valida, sorteia e
   acrescenta (`src/chess_diagram_ocr/text/ouro.py`).
3. **Os scripts** de `docs/metrics/texto_ouro_2026-10-30/`: `sortear.py` (o sorteio), `auditoria.py`
   (as folhas de conferência da auditoria visual), `acrescentar.py` (o livro que chega depois) e
   `reprovados_auditoria.tsv` (os reprovados pela auditoria, com o motivo).

**O manifesto guarda a identidade, não o nome** (decisão do dono, 2026-10-30: o repositório é
público). Cada livro e cada folha levam `identidade` — a de `caderno.identidade_de`, o resumo do
primeiro MiB do arquivo, reaproveitada —, e `ouro.localizar(identidades, pastas)` acha o PDF por ela;
renomear o arquivo não o tira do ouro. O campo `livro` da redação do roadmap saiu por isso. Os nomes,
as folhas recusadas e o critério de cada recusa ficam fora do repositório, nos dados locais da skill
`ocr-texto-preciso` (`d6_inventario.tsv`, `d6_sorteio.tsv`, `auditoria_s702/`).

Campos: por livro, `{identidade, split, lingua, origem, diagramacao, grupo, fora_do_treino, reprovado,
entrou_em}`; por folha, `{identidade, folha, lingua, estrato, split}`, com a folha em base 1. `split` é
`dev`, `teste` ou `reserva`. `lingua` é um código de três letras do Tesseract, de uma lista fechada com
as oito línguas do acervo (`ouro.LINGUAS`), e a da folha é a do livro. `origem` é `pdf` ou `ebook`
(ebook convertido em PDF, quase sempre pelo calibre: um leiaute que o acervo impresso não tem, e que
fica declarado para os portões o separarem). `diagramacao` é `vista` quando o livro tem o produtor e as
famílias de fonte de um livro dev, e um livro assim não entra no teste. `grupo` é a identidade do livro
que representa a série ou a diagramação; um livro da reserva do mesmo grupo de um livro do teste é
`fora_do_treino` — não se treina no irmão de série do teste (S-746). `reprovado` diz por que o livro
saiu do ouro; reprovado fica na reserva e fora do treino. `entrou_em` é a data em que um livro entrou a
mais no teste, vazia para os congelados. A guarda de `primeira_leitura_do_teste` cobre os congelados em
`congelado_em`; a primeira leitura de um livro acrescentado, a S-706 a registra à parte e depois de
`entrou_em` (está na entrada dela no roadmap). O manifesto tem 28 KB e vai no instalador junto com o
resto de `assets/` (o `packaging/cvoff.spec` empacota a pasta inteira); só tem identidades, nada no
programa o lê até a S-706, e `ouro.caminho_padrao()` o acha por `BUNDLE_ROOT` — a raiz do repositório
num checkout, a pasta do pacote no instalador.

**O sorteio.** Os livros se ordenam por `sha256("20261030:" + identidade)`, e as folhas de cada um por
`sha256(identidade + folha)`, folha em base 1, sem os 8% iniciais e finais. Nenhuma das duas ordens
depende de que outros livros estão na corrida nem da ordem em que foram listados. As folhas se
percorrem nessa ordem; entra a primeira que cai num estrato ainda incompleto e passa na admissão — a
admissão, que custa uma montagem da camada (~0,6 s), só é perguntada a quem já caiu num estrato que
precisa dela. Os estratos são os do dev: **prosa** (≥ 700 caracteres de prosa e ≥ 55% de prosa) e
**misto** (≥ 300 e de 20% a 55%), três de cada. O estrato que acaba antes completa com **todas** as
folhas do outro, na mesma ordem e pela mesma admissão. O classificador de token é o do protótipo
(`texto_prosa_2026-10-30/banco.py`, sha256 `9857cbee6af253dc` gravado no manifesto) até a régua das
S-700/S-701 entrar no pacote; o estrato de cada folha fica congelado, e trocar o classificador depois
não muda o que foi sorteado. As folhas dev não foram sorteadas agora: são as medidas em 2026-10-30,
escolhidas pelo classificador de então, e duas de prosa de um livro ficam com 695 e 696 caracteres de
prosa pelo atual — continuam no dev como foram medidas. Elas passam pela mesma admissão que as
sorteadas (o `sortear.py` para se uma for recusada), e todas as 27 passam. A `origem` dos livros dev
sai do produtor, como a dos candidatos: três são PDF e dois são ebook convertido.

**A elegibilidade dos candidatos** (o inventário dos 76 PDFs, feito sem leitor: metadados, famílias
de fonte e o perfil de admissão): fora o livro de scan (critério (a) de livro), o de produtor de OCR
(d), o que não tem camada de texto e o que tem camada sem prosa legível; fora o livro dev, o conteúdo
de um livro dev (o original em inglês do *400 Quebra-cabeças*) e o que tem a diagramação de um livro
dev — mesmo produtor e famílias de fonte com Jaccard de 0,86 a 1,0, os 11 da diagramação do
Dvoretsky —, que vai à reserva com `diagramacao: vista`; e um livro por série, os outros na reserva
com o `grupo` do representante.

Os livros do teste: todos os candidatos das línguas que entram inteiras (português e espanhol) e, do
inglês, os primeiros da ordem por origem, na proporção das origens (maior resto), 16 no total — a meta
do G102 é 12, e quatro são folga. O livro que não dá seis folhas admitidas, ou que a auditoria visual
reprova, cede a vaga ao seguinte em inglês da mesma origem; quem entra passa pela mesma auditoria. Os
reprovados vêm de `reprovados_auditoria.tsv`, que o sorteio lê: rodado de novo com o mesmo inventário
e esse arquivo, o manifesto sai idêntico byte a byte (conferido também pelo crítico).

**O que saiu, em 2026-10-30.** Dos 76 PDFs da D6, 36 candidatos independentes (um por série, fora os
de scan, os de OCR de terceiro, os sem camada, os com a diagramação do Dvoretsky, o próprio Dvoretsky
e o original em inglês do *400 Quebra-cabeças*). O teste congelou com **16 livros e 96 folhas** (63 de
prosa e 33 mistas; seis livros não tinham três folhas mistas, quatro deles nenhuma, e completaram com
prosa): 14 em inglês e 2 em português; 10 ebooks e 6 PDFs; todos os 16 passaram na auditoria. Seis
livros cederam a vaga: o único em espanhol, que não tem nenhuma folha com prosa bastante para os
estratos (é de exercícios, umas 50 palavras por folha); um ebook sem folha nos estratos; um com cinco
folhas; e três reprovados na auditoria. O dev são os livros de 2026-10-30 que passaram na auditoria —
**cinco dos sete**, com as 27 folhas medidas naquele dia (20 de prosa, 7 mistas). A reserva tem 49
livros: 19 `fora_do_treino` (os irmãos de série dos livros do teste e os 5 reprovados) e 11 com a
diagramação vista.

**A terceira língua ficou pendente** (decisão do dono, 2026-10-30). A D6 pede três línguas no teste, e o
espanhol que veio não tem prosa; o manifesto congelou com inglês e português e declara `pendencias:
["terceira_lingua"]`. A guarda aceita menos de três línguas só com a pendência declarada, e reprova a
pendência que ficou depois de cumprida. **O livro que o dono trouxer entra a mais**, sem trocar nenhum
sorteado: `acrescentar.py <ouro.json> <pdf> <lingua> <origem> --serie=<identidade|nenhuma>
[--data=AAAA-MM-DD]` sorteia as folhas dele com a mesma regra e a mesma admissão e chama
`ouro.acrescentar_ao_teste`, que mantém os livros do teste e todas as folhas como estavam, na mesma
ordem, marca `fora_do_treino` os irmãos de série dele na reserva e tira a pendência quando as línguas se
cumprem. A elegibilidade é a dos candidatos, e o script mede a parte que se mede: recusa o livro que já
está no manifesto, o que está no acervo `PDF/` (o programa já o leu — o *Chess Evolution 2014*, da série
de um livro dev, mora lá), o que tem a diagramação de um livro dev (a regra do inventário, mesmo
produtor e Jaccard ≥ 0,8, que o reproduz sem divergência nos 64 livros que ele não pôs fora) e o que dá
menos de seis folhas. A série não se mede — o *Chess Evolution 2013* do acervo foi regravado por outro
programa e não se parece com o 2014 em produtor nem em fonte —, e por isso `--serie` é obrigatório:
série de livro dev ou da diagramação de um não entra, e série que já tem livro no teste também não.
Depois, antes do commit, `auditoria.py <ouro.json> <pasta> <identidade>` e a conferência por quem não
sorteou. Cada recusa foi exercitada numa cópia do manifesto (o *Chess Evolution 2014*, o livro sem
`--serie`, a série de um livro dev, a diagramação do Dvoretsky, um livro de três folhas), e o caminho
que aceita também, com um livro aprovado tirado da cópia e acrescentado de volta. O `sortear.py` não se
roda de novo com o livro no inventário: ele reproduz o manifesto de antes do acréscimo, e o acréscimo se
reproduz pelo `acrescentar.py` com a mesma `--data` (sem ela, `entrou_em` é o dia da corrida).

**Achado: o (c) recusa o símbolo de avaliação gravado em uso privado.** Em dois livros do teste a
admissão recusou a maioria das folhas perguntadas por (c): 22 de 28 num, cuja fonte de texto traz as
figurinas em Unicode (♕♔♘) e o símbolo de avaliação que vem depois do lance num caractere de uso
privado; e 44 de 50 no outro, com o caractere privado em fontes Type3 sem nome. A tinta é legítima; a
camada é que não diz que símbolo é aquele, e a recusa é coerente com "a camada só é referência quando
é a tinta". Efeito: as seis folhas desses dois livros no teste são as sem esse caractere, mais pobres
em anotação que o livro.

**Auditoria visual.** Feita em 2026-10-30 por cinco agentes que não sortearam e só receberam as folhas
de conferência e a regra de divergência. `auditoria.py` sorteia 20 linhas por livro entre as folhas do
manifesto (`sha256(identidade + folha + ":" + linha)`, linhas da montagem da camada sem as que cruzam
diagrama e sem as de menos de 12 caracteres, que não dão o que conferir) e desenha cada uma como o
recorte da tinta a 200 dpi com a camada embaixo, mais um `.json` com o código de cada caractere fora do
ASCII; a saída tem texto de livro e fica fora do repositório, com o veredito de cada livro
(`auditoria_s702/vereditos.tsv`). Divergência é a camada não dizer o que a tinta diz — letra, palavra,
figurina de outra peça ou faltando, símbolo trocado por outro caractere —; não é a figurina escrita como
a letra da mesma peça, ligadura sem letra perdida, aspas, traços indistinguíveis, espaço, hífen de fim
de linha. Resultado: **27 livros conferidos**, e passaram 5 dos 7 dev e 17 dos 20 que o sorteio chegou a
pôr no teste (um destes, aprovado, saiu do teste depois, quando o conserto das sobras devolveu a vaga ao
livro que a tinha perdido). Os cinco reprovados, com o motivo, estão em `reprovados_auditoria.tsv`, por
três defeitos:

- **símbolo de avaliação em código de fonte ChessBase** — a camada guarda `³ µ ƒ © ‚` onde a tinta
  mostra ⩱, ∓, ↑, a compensação e a seta (2 livros do teste). Num livro aprovado, a própria tinta
  imprime esses caracteres, e ali a camada é fiel;
- **figurina impressa fora da linha da camada** — a figurina está na linha impressa e a montagem da
  camada para antes dela (1 livro do teste e o *Melhores Finais de Capablanca*, dev);
- **ligadura que perde letra** — o `ft` da fonte do *Chess Evolution 2013* (dev) vira só `f` na
  camada (`after` → `afer`), e o ± vai para uso privado.

Duas observações que não reprovam. Nos 27 livros, os auditores viram a camada escrever a letra da
peça onde a tinta tem a figurina em 15, a figurina em Unicode em 6, a tinta já em letra em 2, e não
descreveram as peças em 2 (os outros 2 são reprovados por figurina faltando). A régua normaliza
figurina para letra, mas a revocação de figurina (G2) só tem referência nos 6. E num livro do teste a
impressão traz `Ê` no lugar da figurina do rei, e a camada repete: o ouro mede contra a tinta, e o
leitor que lê a tinta lê `Ê`. Estas observações e o achado do (c) vêm em parte de livros do teste:
antes de virarem regra na S-701 ou na S-716, confirmam-se no dev ou na reserva — regra desenhada
olhando o teste anula o portão.

**Achado: a linha de base de 2026-10-30 mediu dois livros dev contra uma referência com defeito.** No
*Chess Evolution 2013*, toda palavra com `ft` lida certo conta como erro, para qualquer motor; no
*Capablanca*, a figurina que falta na referência conta como inserção na notação. Os números
publicados ficam como estão, com esta ressalva; a S-706 republica a linha de base nos cinco livros dev
admitidos. E (a)–(d) não bastam para a S-716: os cinco reprovados passam neles (ver a entrada da
S-716 no roadmap).

**Desvios da redação do roadmap.** (1) O nome do livro não vai ao manifesto (acima). (2) O teste
provisório — "folhas nunca lidas dos livros dev" — existia "até o teste existir"; com a D6 o teste
existe, e ele não foi feito (as folhas dos livros dev aparecem em dezenas de relatórios de formatos
diferentes, e provar que uma nunca foi lida custaria mais do que ele vale agora). (3) A verificação
pelo `cvoff-texto-prosa --conjunto ouro --conferir-admissao` espera a S-706, que cria o comando — e a
entrada dela no roadmap o leva, junto com a gravação de `primeira_leitura_do_teste`; até lá, o log do
sorteio lista cada folha recusada e o critério, e os testes abaixo fazem a guarda. (4) O roadmap pede
"todo trecho de texto da camada visível"; a admissão, como o protótipo validado, só olha os trechos
**fora** dos retângulos de diagrama — o que está dentro sai da referência de qualquer jeito. (5) A
*Saída* do roadmap pede a guarda de "manifesto de teste com data posterior à primeira leitura"; ela
cobre os livros congelados juntos, e a do livro acrescentado depois fica com a S-706, que registra a
leitura de cada um.

**Critério de aceite.**

- `tests/test_text_admissao.py`: cada critério reprova o que deve, e cada alternativa das listas por um
  caso que casa **só ela** — cada produtor e cada fonte de OCR (d); livro de scan, texto em modo 3 ou de
  opacidade 0, imagem de mais de 60% da folha desenhada depois do texto (a); cada padrão de lixo de
  figurina e o uso privado em fonte de texto em toda a faixa U+E000–U+F8FF (c); fileira de seis
  encostados, em cada fonte de diagrama, fora do diagrama (b) —, e o que não deve passa: o tabuleiro em
  fonte dentro do retângulo crescido de uma casa — em **cada** um dos retângulos da folha, porque o
  Dvoretsky tem dois por folha —, a figurina solta, cinco encostados, o uso privado em cada fonte de
  figurina, a moldura do tabuleiro em uso privado na folga dos quatro lados do retângulo (a de um livro
  do teste, que cerca o tabuleiro: a folga de cada lado tem o seu caso dentro e fora, a meio ponto da
  fronteira e em dois tamanhos de tabuleiro, o que prende a casa em um oitavo da largura, também num
  retângulo não quadrado e com tabuleiros de dois tamanhos na mesma folha), `Stuttgart` e `outgoing` (o
  ponto de `.tg` é literal), o texto invisível dentro do diagrama, a imagem de fundo desenhada antes do
  texto, a de 50% da folha. Trecho só de espaço não conta como texto. A linha de base tolera um quarto
  da altura (2 pt de desvio é a mesma linha, 3 e 6 pt não), e `FILEIRA` é 6. A **falsificação** do (b):
  o mesmo tabuleiro sem o retângulo reprova por (b), com fileira de 8. A extração se testa em PDFs
  gerados no teste e numa página falsa para a opacidade, porque o `PDF/` não está na CI.
- **Paridade com o protótipo:** a admissão do pacote refez as 360 folhas da tabela publicada da S-716
  (12 livros × 30) com **0 diferenças** em todas as colunas. Essa tabela exercita quatro dos nove
  vereditos — a admissão e os oito critérios — (admitida, `sem_texto`, `d:produtor`, `a:livro_de_scan`);
  o crítico comparou ainda as 167 folhas que o sorteio final perguntou na D6, 66 delas recusadas por
  (c), também sem diferença, e refez a falsificação do (b) no Dvoretsky real (29 de 30 folhas recusadas
  sem os retângulos, todas com fileira de 8). `a:invisivel`, `a:coberto_por_imagem` e `d:fonte` ficam só
  com os testes sintéticos.
- `tests/test_text_ouro.py`: as três guardas do roadmap — folha sem identidade, livro em dois splits,
  teste lido antes de o manifesto ser congelado (`primeira_leitura_do_teste`, que a S-706 grava) — e
  cada outra guarda disparando sozinha num manifesto que fora dela vale: formato de cada data (a de
  leitura com `2026/11/02` e a de entrada com `2026/11/05`, que só o formato pega, e com lixo no fim),
  versão, livro sem identidade, split, origem, língua ou diagramação inválidos, estrato inválido, folha
  zero, folha repetida, folha de livro que o manifesto não lista ou no split errado, livro do teste sem
  folha ou com diagramação vista, teste de 7 livros com três línguas (e o de 8 vale, e `TESTE_MINIMO` é
  8), língua a menos sem a pendência, pendência que não saiu ou sem regra, folha numa língua e o livro
  noutra, `entrou_em` fora do teste ou de antes do congelamento, irmão de série do teste fora de
  `fora_do_treino` (também quando o livro do teste é membro e não representante da série), reprovado no
  teste mesmo fora do treino e reprovado na reserva dentro do treino; e ler e entrar no dia do
  congelamento valem. `LINGUAS` são as oito do acervo, e a língua da folha se confere com a do livro em
  todo split. O representante da série na reserva sai do treino quando o livro do teste é membro dela, a
  configuração que o `--serie` cria; e `entrou_em` vai e volta pelo arquivo. O sorteio bate com valores
  conhecidos, conferidos por uma reimplementação da regra; os estratos, com as fronteiras de 699/700 e
  290/300 caracteres e de 20% e 55%; a ordem não depende da lista; e o estrato se completa com **todas**
  as sobras (as seis primeiras recusadas e a sétima entra; 246 recusadas e as três últimas entram),
  perguntando a admissão a cada uma. O livro a mais entra sem mexer em nada sorteado, tira a pendência
  só com a língua nova, e não entra com diagramação vista, com menos de seis folhas, nem numa série que
  já tem livro no teste; os irmãos dele na reserva saem do treino. O acréscimo grava `entrou_em` e
  recusa data de antes do congelamento ou fora do formato; a língua de um livro da reserva não tira a
  pendência; a série inteira sai do treino, não só o representante; e a série do teste se reconhece
  também pelo `grupo` do livro do teste. `localizar` acha o livro renomeado, só os procurados, e o
  primeiro de dois arquivos iguais; e `caminho_padrao` segue o `BUNDLE_ROOT`. E o manifesto versionado
  vale, tem ≥ 12 livros no teste, seis folhas por livro, os cinco livros dev que passaram na auditoria,
  os mesmos reprovados que `reprovados_auditoria.tsv`, os estratos do código, o teste ainda não lido, e
  `gravar` o reproduz byte a byte.

**Reversão.** O manifesto é dado versionado: um livro reprovado sai num commit que diz o critério. A
admissão e o manifesto não têm chamador em produção até a S-716.
