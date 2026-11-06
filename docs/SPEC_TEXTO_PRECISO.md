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
> | S-599 | [PLANO_FAIXAS_REVERSAS.md](PLANO_FAIXAS_REVERSAS.md) |
> | S-601 a S-668 | [SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md) |
> | S-700 a S-772 | [SPEC_TEXTO_PRECISO.md](SPEC_TEXTO_PRECISO.md) |

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


## S-700 · A régua no pacote ✅ implementada (2026-11-06)

**Problema.** A régua morava em `docs/metrics/texto_prosa_2026-10-30/banco.py`, sem teste, e seis medições já se
apoiavam nela. O `Placar.somar` dela perdia inserção, WER e figurina, e a normalização não era idempotente:
`a-\n\nb` e `a-\nb-\nc` só se juntavam na segunda passada.

**Decisão.** `src/chess_diagram_ocr/text/regua_prosa.py`, sem I/O: `normalizar(texto, modo, lingua)`,
`classe_do_token(token, lingua)`, `classes_por_char`, `alinhar`, `pontuar(ref, hip, lingua)` → `Placar`, mais a
`familia` de cada palavra errada, o `ic95` de dois níveis e a `diferenca_pareada` (semente 7, 2.000 reamostras), e as
funções puras da montagem (`linhas_da_pagina`, `cruza_diagrama`, `crescer_diagrama`). O espaço colapsa antes de o hífen
juntar, e o hífen não consome as letras em volta: é o conserto da idempotência. O módulo não importa nada do pacote: em
particular, nem `text/fusao.py` nem o caminho contrário, porque o instrumento não pode dividir código com o medido.

**Critério de aceite.** `tests/test_text_regua_prosa.py`: alinhamento contra Levenshtein de força bruta em 500 pares;
atribuição de inserção, inclusive no fim do texto; `if the`→`ifthe` custa no CER de prosa e dá S=1, D=1; token inventado
dá I=1; normalização idempotente em 2.000 textos sorteados.

**A saída: reproduzido até a 4ª casa.** `docs/metrics/texto_prosa_2026-11-06/reproduzir_regua.py` repontua os JSONL de
2026-10-30 sem rodar motor. Com o classificador do protótipo injetado (`classificar=`) e a normalização do protótipo: **zero
diferença** em CER, WER, notação, espaço, figurina e inserções, nos quatro conjuntos do ouro e nos dois conferidos
sem eles (`degradado`, `prata_admitida`); é a prova do alinhamento e do placar. Com a normalização nova, os ouros seguem sem diferença, e
degradado e prata mudam até 0,1 p.p. no `tess_oraculo` da prata (0,02 p.p. no resto): é só a linha lida vazia, onde o hífen agora se
junta. A diferença que sobra é a do classificador da S-701, medida abaixo.

**Achado: o `tess_pagina` publicado em 2026-10-30 estava inflado por CRLF.** O stdout do Tesseract no Windows vem em `\r\n`
(1.328 `\r` nas 28 folhas do ouro), e o protótipo pagava um erro por linha só por isso: na folha 155 do Dvoretsky, 33 erros de
prosa contra 3, com os mesmos 286 tokens. `normalizar` agora faz de toda quebra `\n`, e o `--prototipo` só reproduz o `tess_pagina`
com a normalização antiga. A frase do roadmap "numa folha normal é pior que as caixas do glifo" fica para ser relida com o número
novo da S-713.

**Desvios.** O `Placar.wer_prosa()` agora é o (S+D+I)/N que o relatório publica; o do protótipo era `1 − palavras certas / N`,
que nenhum relatório usava.

## S-701 · O classificador de token, testado contra o que já enganou ✅ implementada (2026-11-06)

**Problema.** Metade do erro que parecia de reconhecimento em 2026-10-30 era de régua, e ainda era: o lixo de figurina
da camada de terceiro contava como prosa, e o lance com sinal colado também (memória `lance-com-sinal-e-regua-cega`).

**Decisão.** `classe_do_token(token, lingua)` devolve `prosa`, `notacao`, `outro` ou **`ruido`**, com
`VERSAO_CLASSIFICADOR` no relatório.

- **Letra de peça por língua só acrescenta** (`LETRAS_DE_PECA`, as oito do acervo, nos códigos de três letras; aceita `pt` e
  `eng+por`). `B`, `D`, `T`, `C`, `R`, `N`, `K`, `Q`, `S`, `L`, `F` soltos são notação em qualquer livro, como no protótipo:
  a régua é inclusiva, e restringir à língua tiraria da notação o `Q` de um livro em português que cita em inglês. `P`
  só é peça em holandês, e `Кр`, `Ф`, `Л`, `С`, `К` só em russo. **`A` solto é prosa até em espanhol**, onde é quase sempre a preposição.
- **Novo em notação:** `19.Bd3`, `Rfc1²`, `Rxg5i`, `24...f4e` (sinal em código de fonte); `1...B`;
  `Nc5).`; `Rg8-Rg6.`; `6…g6!?`, `8.Rxg6+–`; `31.Bxg6fxg632.Qf4` (a camada sem espaço); `97×f6)`.
- **Saiu de notação:** `b3-pawn`, `f4-pawn,` (o regex cirílico sem âncora no fim), `af7anca`.
- **Novo `ruido`:** o que termina numa casa e não tem peça nem palavra antes (`.l:tb1`, `'ii'xa4`, `Wxf7`, `tlld7+`, `©e7`,
  `\x15d7`; `peão-g6` continua prosa, pela vogal), os padrões da admissão, `=I=`, e a letra solta de fonte (`ç`, `æ+`).
- **Linha** só de `a–h`/`1–8` (quatro ou mais, todos diferentes), `abcdefgh`, ou só de letras acentuadas, é `outro`.
- **Retângulo de diagrama crescido de uma casa** ao excluir linhas da referência, mas só para a linha sem palavra nem lance
  (`fora_da_referencia`). *Desvio do roadmap, medido:* nas 27 folhas do dev o retângulo crescido tira 15 linhas a mais, e 9 são
  texto de verdade ao lado do diagrama (`As brancas jogam`), que contariam como inserção de todo motor que as leu certo. As 6 que
  ele tinha de tirar são a fileira do Seirawan, e seguem saindo.

**Critério de aceite.** Tabela de 124 tokens rotulados à mão nas oito línguas, zero divergência; 26 que a régua recusa como
prosa, um por família da seção 1.6. Os casos saíram também de varrer os JSONL de 2026-10-30 atrás de "prosa" com dígito ou sinal.

**O efeito, medido nos JSONL de 2026-10-30, sem rodar motor** (CER de prosa, `tip`, publicado → classificador novo):

| conjunto | glifo | Tesseract | oráculo | fusão v5 |
|---|---:|---:|---:|---:|
| ouro sem folha perdida | 3,61 → 3,59% | 1,33 → 1,32% | 0,16 → 0,15% | 1,25 → 1,23% |
| ouro, seis livros limpos | 2,47 → 2,44% | 0,23 → 0,22% | 0,10 → 0,09% | 0,28 → 0,25% |
| degradado médio | 57,16 → 57,16% | 18,61 → 18,53% | 6,50 → 6,44% | 19,22 → 19,15% |
| prata admitida | 14,37 → 12,71% | **6,03 → 3,85%** | **3,65 → 1,40%** | **7,00 → 4,84%** |

No ouro o conserto é pequeno: 6 tokens de 5.647 mudam de classe nas 28 folhas, e 4 no estrato misto. **Na prata não:** 244
tokens de lixo de figurina saem da prosa, e o erro do Tesseract cai em um terço. O WER dela vai de 13,12% a 7,68%. A prata
continua só ordenando, mas o número de scan "6,0% do Tesseract" do roadmap era em boa parte a figurina escrita como lixo.

*Achado:* `text/notacao.fatiar` continua conservador (S-208), e o classificador da fusão, próprio dela, ainda não reconhece
`Rg8-Rg6` nem `31.Bxg6fxg632`: são dois instrumentos, e a guarda de grafo de import é de outro item.

## S-703 · O scan-ouro: a ferramenta, sem a transcrição ✅ implementada (2026-11-06)

**Problema.** Sem verdade humana em scan, M3 e M4 não existem, e os 14,4% do glifo são contra OCR de terceiro. A transcrição custa ~15 horas e depende
da decisão D3, que o dono não tomou. O que não dependia dele era a ferramenta: sem ela, as 15 horas seriam num editor que reabre a folha com
o que já foi corrigido (S-612) e carimba o bloco inteiro de `humano`. **Nada foi transcrito. M3 e M4 seguem sem número.**

**Decisão.** Quatro peças, e todas sem leitor nenhum.

- **O manifesto**, `assets/texto_prosa/scan_ouro.json`, só identidades, e `text/scan_ouro.py`: `carregar`, `gravar`, `problemas`, `sha_da_folha`. 30 folhas de 10
  livros em 6 línguas: 3 livros `clearscan`, 4 `ate_150`, 3 `de_300`, ou 12 folhas (40%) de até 150 dpi. 15 no misto, 12 na prosa, 3 `a_conferir`. Dev e teste com 5
  livros cada, e as três produções nos dois. 6 folhas de dupla digitação, uma por produção em cada split. Cada folha guarda o sha dos bytes dela no PDF.
- **O sorteio**, `docs/metrics/texto_scan_ouro_2026-11-06/sortear.py`: livros por `sha256(semente:identidade)`, folhas por `sha256(identidade + folha)`, as funções do ouro.
  Bachmann e Neumann entram por exigência do item, e no dev, porque as S-743 e S-721 os viram; **livro visto não vai ao teste**. Um livro por série ou autor, no máximo
  3 por língua.
- **O caderno**, `text/transcricao_scan.py`. `CadernoDaPassada` só conhece o arquivo da sua passada: `passada_1.jsonl`, `passada_2.jsonl`, com linha, partida, `sha_imagem`, `sha_folha`,
  segundos e `completa`. A pasta é recusada dentro de um repositório, e sem o backup declarado (`backup.json`, na própria pasta) nada grava. `gravar` chama `exigir_transcricao` e
  `dado_corrigido.exigir_documento_cego` a cada linha, e copia o arquivo para o backup. A procedência `transcricao:<passada>` mora em `text/procedencia.py`: `classe` a traduz
  para `humano`, e `exigir_transcricao` é mais estreita que `exigir_verdade`, recusando também o `humano` do bloco.
- **A tela**, `qt/modo_transcricao.py`, comando `modo_transcricao` (`alternar_transcricao`, grupo Verdade da aba Leitura). O editor da aba sai de cena, porque mostra a leitura
  de um motor. Cada linha é uma faixa impressa com um campo ao lado, `Enter` leva à seguinte, seis botões escrevem a figurina e `Linha a mais` cobre o que a geometria não achou.
  A faixa é a geometria de `leitor.segmentar` com o detector de diagrama, sem classificador. A pasta fica em `AppState.texto_transcricao_pasta`. Erro sai na frase de estado, nunca em caixa.

**Regra que o item não pedia: a segunda passada só parte do vazio.** As duas partindo da mesma camada concordariam nos erros que ninguém viu, e o acordo mediria a camada.

**O relógio.** `Relogio` soma o tempo entre uma tecla e a seguinte, e uma pausa conta no máximo 5 minutos. `custo` estima o conjunto a partir de duas folhas concluídas; a tela e o
`--acordo` mostram. É a resposta à D3 com o relógio de quem digitou, em vez dos "20 a 30 minutos" do roadmap.

**A verificação.** `cvoff-texto-prosa --conjunto scan-ouro --acordo --transcricao <pasta>` imprime o acordo por folha (S+D+I sobre o maior comprimento, normalização `cru`), a
folha que volta, o custo e o estado do backup, e sai com 0, 1 (há folha que volta) ou 3 (nada para medir). `--conjunto scan-ouro --split dev --transcricao <pasta> --dados <jsonl>` mede
contra a verdade digitada, e só quando **o split inteiro** tem verdade pronta; sem isso, diz `M3 e M4 sem número` e sai com 3. O split `teste` pede `--abrir-teste`, que grava
`primeira_leitura_do_teste` antes de ler, como no ouro.

**Onde mora.** `text/scan_ouro.py`, `text/transcricao_scan.py`, `text/procedencia.py`, `qt/modo_transcricao.py`, `qt/painel_de_texto.py` (`alternar_transcricao`), `cli/texto_prosa.py` (`--acordo`,
`--transcricao`), `text/bancada_prosa.py` (`preparar_folha(verdade=)`). O módulo novo não se chama `text/transcricao.py` porque esse já é o da S-183, das 123 faixas de legenda.

**Critério de aceite.** `tests/test_text_scan_ouro.py`: o manifesto cumpre a entrega, e cada regra de `problemas` reprova um manifesto falsificado; a segunda passada não vê a primeira;
glifo e rapidocr não gravam, `humano` e `corrigido_de:` também não; sem dados, o CLI diz e não zera. `tests/test_qt_modo_transcricao.py`, por efeito na tela e no arquivo.
**Falsificação:** tirar as duas portas de `gravar` deixa vermelhos os testes das portas, e o resto verde.

*Achado:* **a geometria não separa prosa de misto.** Nas 27 folhas do ouro-dev, com os estratos conhecidos, a fração de linhas cheias dá AUC 0,63. Por isso o conteúdo da folha sai
da camada de terceiro que o PDF já traz, pelo `ouro.estrato_do_texto` do sorteio da S-702: nenhum motor nosso roda, mas é um OCR que foi lido. **O preço:** livro sem camada não entra no
sorteio, e o `teste` sai de um grupo mais estreito: dos 43 candidatos, 17 têm mediana abaixo de 200 caracteres de camada. Só 3 livros de até 150 dpi com camada não foram vistos.

*Achado:* **o Bachmann não tem camada**, e o item o exige: as três folhas dele são `a_conferir`, e a conta da metade no misto vale no pior caso (15 de 30 sem contá-las). Depois da
transcrição, o conteúdo real de toda folha sai da régua sobre a verdade. **E o `dpi` 72 dele é nominal**: a página mede 1216 × 1864 pt e a imagem tem esses mesmos pixels. O estrato `ate_150` vem
daí; a altura-x nativa, perto de 10 px, é a do estrato.

*Achado:* a faixa é a mesma geometria dos motores, e ela erra como eles. Na folha 71 do Bachmann, `Stellung nach dem 13. Zug von Schwarz.` são três faixas, e a tabela de lances sai em duas colunas de faixas.
A pessoa digita o que cada faixa mostra, e a referência fica na ordem do produto; a linha partida não vira erro de medição, e a de outra ordem também não.

**Desvios.** A verificação de M3 e M4 por estrato não roda, porque não há verdade. O manifesto traz os **estratos previstos**: a conta real só existe depois. A camada entra na escolha, e o pedido era "sem
leitor nenhum": nenhum leitor roda, e o achado acima diz o que isso custa. `tesseract` fica fora do teste de porta porque a procedência só existe na página a partir da S-722.

## S-704 · A degradação sintética, reprodutível, em duas famílias ✅ implementada (2026-11-06)

**Problema.** O perfil `medio` de 2026-10-30 equivale a ~110 dpi e leva o glifo a 57,2%, contra 14,4% na prata: não foi calibrado
contra nada, morava num script, e a semente era o índice da folha.

**Decisão.** `src/chess_diagram_ocr/text/degradacao.py`: `aplicar(img_rgb, perfil, semente)`, `semente_da_folha(identidade, folha)`
(não depende da ordem da corrida), geometria intacta. **Duas famílias com geradores diferentes:** `AUMENTO`, os cinco perfis de
`degradar.py`, byte a byte (reduz, desfoca, ruído gaussiano, manchas, JPEG; `default_rng`), que o aumento de dados da Fase 105 pode
ver; e `RESERVADA`, três perfis `fotocopia_*`, outra física (tinta que borra desigual, sombra de baixa frequência, contraste amassado,
estrias de sensor, poeira em grumos; sem redução nem JPEG; `MT19937`), **só para medir a M5**. `perfil_de_aumento` recusa os nomes dela.

**O perfil `calibrado` fica pendente, com o recuo.** Ele depende da S-703 (humano, D3). `aplicar(..., "calibrado")` levanta
`PerfilPendente` com a frase do recuo da seção 7: a M5 fica sem número, e os perfis publicados dizem que não foram calibrados. Os
números de `fotocopia_*` também não saíram de scan real.

**Critério de aceite.** `tests/test_text_degradacao.py`: mesma folha e semente dão os mesmos bytes, no mesmo processo e em outro;
a família de aumento é o protótipo byte a byte; a tinta fica a até 2 px; o aumento recusa a família reservada.

**Desvios.** A verificação pede o `resumo.py` do Tesseract no perfil calibrado contra o scan-ouro-dev: não existe sem a S-703. O
`degradado` da linha de base da S-706 usa `semente_da_folha`, e não o índice, por isso não é o mesmo ruído de 2026-10-30.

## S-705 · A prata, só para ordenar ✅ implementada (2026-11-06)

**Problema.** Os scans com camada de terceiro eram uma lista num relatório, sem estrato, e os números deles se liam como erro.

**Decisão.** `assets/texto_prosa/prata.json` (versionado, só identidades) e `src/chess_diagram_ocr/text/prata.py`: `carregar`, `gravar`,
`problemas` (com o ouro à mão, também o livro que estivesse nos dois) e `estrato_de_producao(fontes, dpi)`, sem leitor nenhum. São os
dez livros e as trinta folhas de `prata_todas` de 2026-10-30, para a ordenação continuar comparável: 3 `clearscan` (fontes `Fd<n>`),
3 `ate_150` e 4 `de_300`. `docs/metrics/texto_prosa_2026-11-06/prata_manifesto.py` o escreve. O relatório carimba `"uso": "ordenação"`
em todo dicionário com número da prata, e a tela imprime a palavra ao lado de cada um; `compilar_bloco` recusa folha de conjunto,
split ou perfil diferentes num bloco só, e é assim que a prata nunca se soma ao ouro.

**Critério de aceite.** `tests/test_text_prata.py` e `BlocoTests` em `tests/test_cli_texto_prosa.py`; o filtro `oraculo_max=0.10` fica
escrito em `prata_admitida`. **Medido (ordenação):** no bloco `prata`, Tesseract na página 8,25%, nas linhas certas 9,20%, nas do glifo 10,08%, fusão
11,14%, glifo 21,20%, suíte 24,01%, com os três estratos separados.

*Achado:* folha de duas colunas na prata não fecha com a montagem da camada, e o CER dela mede a ordem junto. Por isso o relatório publica
`palavras_de_prosa_achadas_em_qualquer_ordem` ao lado: Tesseract na página 92,3%, suíte 91,7%, Tesseract nas linhas do glifo 89,0%, fusão 88,3%.

## S-706 · `cvoff-texto-prosa` e a linha de base publicada ✅ implementada (2026-11-06)

**Problema.** Cada medição da prosa saía de um script próprio; nenhum gravava a abertura do teste, e todos deixavam o JSONL perto do repositório.

**Decisão.** Três peças. `text/bancada_prosa.py`: `preparar_folha`, `medir_folha`, os motores `tess`, `tess_oraculo`, `tess_pagina`, e `registrar_motor`,
`motor_de_linha`. `text/relatorio_prosa.py`: agrega sem texto de livro, com `achatar` e `diferencas`. `cli/texto_prosa.py`, a entrada `cvoff-texto-prosa`.

- **Medir** grava um JSONL por folha em `--dados`, recusado dentro do repositório. `--limite-segundos` para depois da folha em curso, e o mesmo
  `--dados` continua. Cada processo descarta uma leitura de aquecimento; cada folha traz `codigo` (pacote, commit, `src_sujo`, modelo, Tesseract, `tessdata`).
  `--exigir-src` aborta se o pacote importado for de outra árvore.
- **O teste** pede `--abrir-teste`, grava `primeira_leitura_do_teste` **antes** de ler (`ouro.registrar_leitura_do_teste`) e não imprime número por folha.
  O livro acrescentado depois do congelamento grava em `leituras_dos_acrescentados`, só presente quando existe, e `ouro.problemas` reprova a leitura de
  antes de `entrou_em`. A data é a da primeira abertura, e não sobe.
- **`--compilar`** escreve IC95 de dois níveis, `tip` e `cru`, taxonomia por família com o livro de origem (sem exemplo), pares, `por_estrato`,
  `por_livro` e `segundos_*` à parte. O filtro vem na linha do bloco (`nome=a.jsonl?oraculo_max=0.10`) e vai escrito no relatório. O bloco do teste sai sem
  `por_livro` e sem livro na taxonomia; o pior livro sai como número, sem nome.
- **`--conferir-admissao`** lista folha recusada e critério, sem leitor. Não conta como leitura do teste: é a mesma admissão que o sorteio já fez.
  Medido: **0 recusadas** em 27 do dev e em 96 do teste.
- **`--comparar`**, `--importar nome=hip.jsonl` (motor de outro processo, `{identidade, folha, texto}`) e `--repontuar`.

**Como medir um motor novo (a S-721).** O que entra por `ler_pagina(motor="nome")`: `--motor nome`, e nada mais; mudar a regra da fusão e rodar `--motor fusao`
mede a regra nova. Uma função sobre a folha: `bancada_prosa.registrar_motor("nome", funcao)`. Outro `LeitorDeLinha`: `motor_de_linha(leitor)`. Outro processo: `--importar`.
Num worktree, `python -m chess_diagram_ocr.cli.texto_prosa` com `PYTHONPATH=<worktree>/src` e `CVOFF_RAIZ` no checkout com os PDF; o `cvoff-*` instalado importa o principal.
A sequência da medição está em `docs/metrics/texto_prosa_2026-11-06/compilar_g100.sh`.

**O portão G100: passou, com o relatório em `docs/metrics/texto_prosa_20261106.json`.** Duas corridas no dev, no degradado e na prata, **zero diferença** fora `segundos_*`
(`--comparar`; no degradado, a segunda corrida foi num worktree limpo no mesmo commit, e a única diferença é o nome da pasta do pacote); o teste correu uma vez, de propósito, com `primeira_leitura_do_teste = 2026-11-06` gravada antes. Medido em `3ebb61ec` (árvore limpa), compilado depois.

| CER de prosa, `tip` [IC95 de dois níveis] | glifo (`auto`) | camada na prosa | fusão | Tesseract | oráculo | Tesseract na página | suíte |
|---|---:|---:|---:|---:|---:|---:|---:|
| ouro-dev, 27 folhas, 5 livros | 2,82% [0,78; 4,82] | 0,20% [0; 0,62] | 0,32% [0,07; 0,82] | 0,27% | 0,11% | 0,37% | 0,36% |
| WER (S+D+I) no dev | 11,47% | 0,29% | 1,04% | 0,97% | 0,80% | 2,20% | 2,58% |
| **ouro-teste, 96 folhas, 16 livros** | **6,93% [3,31; 12,19]** | **3,25% [0,75; 7,12]** | — | — | — | — | — |
| WER no teste | 18,66% | 3,78% | — | — | — | — | — |
| degradado médio (dev), sem calibração | 49,91% | — | 11,72% | 10,74% | 1,55% | 2,36% | — |
| prata admitida, 19 folhas (ordenação) | 11,27% | — | 3,90% | 3,12% | 1,78% | 2,77% | 14,37% |

**O dev é otimista, e o teste diz quanto:** o glifo erra 2,5 vezes mais nos livros que nunca serviram para desenhar nada. A camada na prosa contra a própria camada dá 3,25% no teste,
com 99,4% das palavras achadas em qualquer ordem: o que sobra ali é montagem, e é a M0 do G107 que julga isso, não esta linha de base. Nenhuma folha do teste se perdeu pelo leiaute, e nenhum
aviso saiu. O tempo foi medido sob contenção, e não julga o G4.

**Desvios.** A linha de base do teste é só de `auto` e `camada_prosa`, porque o portão o abriu só para o padrão de hoje; `fusao` no teste fica para o G102. O `--conjunto scan-ouro --acordo` da S-703
não existe: depende do trabalho humano. A G5 (`captura`) e a G1 (c), de legalidade, não entraram no relatório: são de portões de outras fases, e o `medir.py` da primeira entrega segue valendo para a G5.

**Critério de aceite.** `tests/test_cli_texto_prosa.py`: o teste não abre sem pedir, a data está gravada na primeira leitura, a segunda abertura não a muda, o relatório sai sem as palavras do livro,
duas corridas iguais, `--comparar` acusa diferença fora do tempo, filtro escrito, motor registrado e importado. `RelatorioPublicadoTests` confere o relatório versionado. `tests/test_text_prata.py`, a guarda por livro acrescentado.

## S-707 · A suíte irmã na mesma régua, e o que a S-721 reaproveita ✅ implementada (2026-11-06)

**Medida.** `docs/metrics/texto_prosa_2026-11-06/suite_ler.py`, com o Python da suíte (`claude/rotulagem-diagramas`, `39ab634`) e nada escrito lá: `OcrService.recognize_image` a 300 dpi, a
configuração padrão dela, nas folhas do ouro-dev e da prata, importado como motor `suite`. **`recognize_image`, e não `recognize` com o PDF:** com a página na mão, ela lê primeiro a camada, e medir isso contra
a camada daria ~0 por construção. **Os diagramas vão pintados de branco** (`suite_diagramas.py`, os retângulos da régua): em produção ela os recebe da frente de visão, e por `recognize_image` eles não têm
por onde entrar. Sem a máscara ela inventa texto no tabuleiro: 1,27% de CER no dev, contra 0,36% com ela. Os modelos Tesseract por livro **não foram medidos**: `book_anchor` só existe com um livro registrado, e nenhum das folhas tem.

| | fusão (tronco) | suíte | fusão − suíte |
|---|---:|---:|---|
| dev: CER de prosa | 0,32% | 0,36% | −0,03 p.p. [−0,76; +0,53], **empate** |
| dev: WER de prosa | 1,04% | 2,58% | |
| dev: palavras achadas em qualquer ordem | 99,37% | 99,42% | |
| dev: CER de notação | 11,07% | 12,21% | −1,14 p.p. [−5,46; +1,67] |
| dev: figurina, revocação / precisão | **83,8% / 85,3%** | **49,7% / 80,5%** | |
| prata (ordenação): CER de prosa | 11,14% | 24,01% | −12,87 p.p. [−23,39; −4,11] |
| prata (ordenação): palavras achadas em qualquer ordem | 88,29% | 91,68% | |

Por estrato, na prata (ordenação), fusão contra suíte: `clearscan` 2,80% e 18,71%; `ate_150` 17,74% e 28,51%; `de_300` 14,17% e 25,77%. **Esse CER não decide:** a suíte acha mais palavras que a fusão, e paga pela ordem em que as lê, contra uma
referência que é o OCR de outro. No dev, por livro, ela ganha na prosa em três (*Hertan* 0,29% contra 0,94%, *Dvoretsky* 0,08% contra 0,21%) e perde no Seirawan (1,31% contra 0,09%): é o leiaute do Tesseract, e o Tesseract na página mostra o mesmo.

**A decisão, escrita para a S-721.** O pipeline dela não entra: na prosa empata com a fusão, e perde 34 p.p. de revocação de figurina, porque só pede o glifo na região que parece notação e ancora tudo no Tesseract. A regra de roteamento do tronco (notação de qualquer lado ao glifo) fica.
O árbitro por região também não: a pergunta dele, "a camada é confiável?", a S-716 responde pela admissão, sem depender do motor avaliado. **O que a S-721 leva da suíte são regras de `caissa/ocr/fusion.py`, cada uma medida na régua antes de entrar:**

1. *A âncora não se troca por outra leitura quando já é palavra ou lance* (regra 4 do módulo; lá, sem ela o CER de uma página de fax foi de 0,031 a 0,082). É a generalização do veto de léxico da fusão v5.
2. *`_keep_number_prefix`*: o número de lance da âncora sobrevive à troca (`17...Ae5` e `7...♘e5` dão `17...♘e5`). É a regra 2 da fusão, com o parêntese aberto a mais.
3. *`_truncates_long_notation`*: leitura mais curta que é um pedaço da notação longa não vence (`h5–h4.` contra `...h7—h5—h4.`).
4. *Disputa vira revisão* (regra 6): o slot sem vencedor claro fica com a âncora e marca revisar. Serve à G5 da S-718, que hoje captura 26 a 50%.

**Fora da régua de hoje:** o leiaute. O Tesseract na página acha 92,3% das palavras na prata contra 88,3% da fusão, e é a S-712 e a S-715 que respondem a isso, e não a S-721. A **D9** (quem escreve o livro exportado) segue do dono: o medido recomenda o tronco enviar as folhas, por causa da figurina.

**Critério de aceite.** Motor `suite` no `ouro_dev` e na `prata`, com os pares `fusao - suite`, e `RelatorioPublicadoTests` o confere. A suíte não foi tocada: `git status` dela igual antes e depois. **Desvio:** o roadmap pede `resumo.py --pares`; quem dá o par é o relatório do `cvoff-texto-prosa`.

## S-710 · Guarda de leitura incompleta, e o campo de avisos que a página não tinha ✅ implementada (2026-11-05)

### Problema

Medido em 2026-10-30, 5 de 67 folhas saíam com um bloco só (`h`, `.`), sem log nem exceção. Quem lê o livro não
tem como saber que faltam 40 linhas. `PaginaLida` nem tinha onde dizer isso.

### Solução

`text/guarda_de_leitura.py`: a **densidade de leitura**, caracteres lidos ÷ componentes de tinta com altura de
letra fora dos diagramas. Abaixo de 0,5, o aviso `folha_nao_lida`. A perda parcial tem sinal próprio,
`leitura_parcial`: linhas lidas contra as estimadas pela projeção, e lidos contra os caracteres da camada.
Folha com pouca tinta (capa, branco, só diagrama) é classe à parte, e não avisa.

**A primeira versão foi reprovada pelo crítico, e o motivo importa.** A *Polgar 5334* avisava em 16 de 25 folhas,
com nada perdido: seis diagramas por folha, e as coordenadas e o número em volta de cada um contavam como letra. A
máscara agora cresce uma casa de cada lado, e quem leu ao menos 60% do que a camada tem não perdeu a folha. O mínimo
subiu de 40 para 100 componentes, pelas duas capas que avisavam.

`PaginaLida.avisos`, com ida e volta em `para_json`. **`ESQUEMA` é 2 só na folha com aviso**: a folha comum continua
no formato 1, sem o campo, e um programa anterior a abre como sempre; é o que mantém a promessa da seção 5a do roadmap,
de que a primeira entrega não muda arquivo gravado. O selo mora em `PainelDeTexto.selo_da_folha` e lê da origem do
documento, então a folha reaberta do caderno continua dizendo que não foi lida.

### Critério de aceite

`tests/test_text_guarda_de_leitura.py`, `tests/test_text_fiacao_da_prosa.py` e `tests/test_qt_texto_prosa.py`. As sete
folhas do roadmap avisavam, e depois da S-711 não avisam mais, porque voltaram a ser lidas. A varredura, 14 folhas de cada um dos 58 livros, 812 no total, está em
[metrics/texto_prosa_primeira_entrega.json](metrics/texto_prosa_primeira_entrega.json), por tipo de folha: nenhuma com
camada abaixo de 0,7 sem aviso, e nenhuma das folhas de *Polgar*, *Reinfeld* e das duas capas que avisavam. **O "5 de 67"
do roadmap estava muito abaixo da realidade:** em 120 folhas de cada, o *Chess Evolution 2014* perdia 113 e o *2013*, 60.
A causa foi consertada na S-711, e na varredura sobram dez avisadas: quatro com texto que o glifo não leu, e seis de
sinal solto saído de dentro de uma moldura (ver S-711). Cinco destas são capas e contracapas conferidas à vista, que são quatro
folhas distintas, porque um livro está duas vezes no acervo. A sexta é texto de verdade que o glifo despedaçou.

A guarda dos testes foi provada por mutação, com a lista do crítico mais os consertos das rodadas seguintes: um mutante
equivalente sobrevive (o número partido, em que o sufixo de mesmo tamanho é o próprio número).

## S-711 · A moldura que envolve a folha ✅ implementada (2026-11-05)

### Problema

O roadmap supunha que a região escura na borda confundia a escala. **Medido, não é isso.** O maior componente de cada folha
perdida é a folha inteira, `(0, 0, 2571, 1819)`: um filete fino na borda, ligado à faixa lateral do *Chess Evolution* ou à
borda escura do scan do *Kmoch*. `caixas_de_caractere` só pega contorno externo, e tudo o que está dentro dele deixa de
existir: `caixas=1`, e o glifo lê `h`. A folha 501, com a mesma faixa e sem o filete fechando a volta, dá 1.691 caixas.

### Solução

`text/moldura.py`: `tirar_moldura` apaga da binária o componente cuja caixa cobre ao menos 90% da folha nas duas direções,
antes de medir a escala e de achar as caixas. A folha sem moldura devolve o mesmo objeto, e não muda em um pixel. A reversão
é a constante `moldura.TIRAR_MOLDURA`.

**Tirar a moldura abre o que havia dentro, e nem sempre é texto.** Contracapa manchada e marca d'água davam `h` e o aviso de
folha não lida; sem a moldura, davam milhares de sinais soltos e nenhum aviso. Por isso a folha com moldura que devolve até
`guarda_de_leitura.RUIDO_POR_TOKEN` = 1,3 caractere por token, com ao menos 40 caracteres, sai com `folha_nao_lida`. O corte
vem de 117 folhas com moldura de 10 livros, um deles duas vezes no acervo: as que dão ruído vão de 1,02 a 1,29, e a seguinte é
1,39. Fora da moldura o mesmo
número é tabela de torneio, e não avisa. A fração de palavras existentes **não serve de corte**: nos livros holandeses ela é de
2% com o texto lido.

**A camada não absolve o ruído.** O *Niemeijer*, índice 4, é texto de verdade que o glifo despedaçou: 3.101 caracteres em 2.789
tokens, contra 1.624 caracteres de camada. Pela contagem ele "batia" com ela e saía calado; agora avisa, e o aviso é a verdade ali.
Entre aquelas 117 folhas, nenhuma com ruído tem camada, e na varredura é a única folha que a regra muda. Somando a leitura do
crítico, são 498 folhas com moldura e 15 com ruído, todas avisadas: 14 sem camada, e o *Niemeijer*.

**Sem aviso, e ruim: o texto despedaçado acima de 1,3.** Não é um livro só. Entre 1,3 e 1,7 há 14 folhas do *Mieses*, 13 do
*Niemeijer*, 2 do *Kmoch* e uma do *Pachman*, e o *Niemeijer* vai até 3,61. Lendo mais de 1,3 vez o que a camada tem, são 23 de 27 folhas no
*Niemeijer* e 52 de 63 no *Mieses*. É defeito aberto: o efeito de subir o corte não foi medido.

### Critério de aceite

`tests/test_text_moldura.py`, com folhas desenhadas: o filete sozinho, o filete com a faixa, e o que **não** é moldura
(faixa sozinha, fio entre colunas, tabela, diagrama com margem), e `RuidoEmolduradoTests` em
`tests/test_text_fiacao_da_prosa.py`. Em `metrics/texto_prosa_primeira_entrega.json`:

| | antes | depois |
|---|---:|---:|
| folhas perdidas em 120 do *Chess Evolution 2014* | 113 | **0** |
| folhas perdidas em 120 do *Chess Evolution 2013* | 60 | **0** |
| CER de prosa do glifo, `ouro_dev_completo` | 12,94% | **3,78%** |
| CER de prosa do glifo, nos 5 livros aprovados na auditoria | 2,83% | 2,83% |
| *Chess Evolution 2013* 903, na fusão | 99,9% | **2,0%** |

Os livros sem moldura não mudam: o número dos aprovados é idêntico. **As folhas voltam pelo caminho normal**, com figurina e
sem aviso, e é por isso que quase nada chega mais à reserva da S-715.

**O que a *Saída* do roadmap pedia, e o que saiu.** Ela foi escrita para outro mecanismo, e dois pontos não se cumpriram:

- **Tesseract nas linhas do glifo a até 1 p.p. do oráculo: não cumprido.** Em 24 folhas de prosa dos dois *Chess Evolution*,
  5,28% contra 0,99%, diferença de +4,29 p.p. [+1,39; +8,76] (`portao_da_s711` no relatório). A folha agora lê, e o que falta
  é leiaute: a linha intercalada, da S-712, **que depois o cumpriu**: +0,39 p.p. nessas folhas, e +0,56 em 40 não vistas.
- **Varredura do acervo inteiro: não feita.** O que há é a amostra de 14 folhas por livro. O censo do crítico, só da moldura,
  viu 2.468 de 26.730 folhas com o componente, em PDF a 220 dpi.
- **"Nenhuma folha do ouro-dev muda de texto": superado.** As folhas 903 e 1210 mudam, porque eram as perdidas. As outras
  26 saem idênticas.

**A S-711 muda o relatório de estilo.** Com o *Kmoch* e os *Chess Evolution* lidos, `metrics/texto_estilo_por_motor.json` passa a
contar folhas que antes não contavam, e foi remedido: a perda de negrito vai de 9,4% a 7,3%, e a de itálico de 16,5% a 32,1%. Os
livros que já contavam quase não mudam; a população é outra, e o total não compara. **O que aparece é defeito que a folha
perdida escondia:** o *Chess Evolution 2014* perde 85 de 106 itálicos. Fica para o G102.

### O que ela não entrega

O texto claro de dentro da faixa, que é o título corrente do fascículo e está na camada: cerca de 30 caracteres por folha, que a
referência tem e o glifo não. A linha intercalada foi a S-712.

### O que ela não pega

**Perda parcial em folha cujo texto ruim tem tanta letra quanto o bom**: a densidade não vê, e os dois sinais de
`leitura_parcial` só veem quando faltam linhas ou caracteres em quantidade. A promessa é a perda total.

## S-712 · A caixa que não é letra ✅ implementada (2026-11-06)

### Problema

O roadmap supunha duas linhas encostadas que viram uma caixa. **Medido, não é isso.** A "linha" das folhas 278 e 577 do *Chess
Evolution 2013* é `(0, 0, 466, 595)`: a folha de alto a baixo. A faixa azul lateral, solta, chega à lista como uma caixa de
caractere de `(0, 0, 377, 1819)`. `linhas.bandas` ordena por `y1`, ela entra primeiro e abre uma banda com o fundo no pé da folha,
e as letras das primeiras linhas da coluna entram nessa banda, ordenadas por `x`: `k15n.ig..♘ht/da4.!th1o6u`. O recorte do leitor de
linha é o retângulo disso, e o Tesseract também erra. É a mesma faixa da S-711, onde o filete a ligava à borda.

**O caso não era só do *Chess Evolution*.** Num *Aagaard* a borda do scan fazia o mesmo: 75 linhas onde a coluna tem 34.

### Solução

Três mudanças, cada uma com a sua reversão:

- **`text/gigantes.py`** (`TIRAR_GIGANTES`): tira da lista, depois de `quadros.molduras_nas_caixas` e antes das regiões, a caixa acima
  de 8 escalas, e a "mancha" de ao menos 3 escalas nos dois lados e 80% de tinta, que é a foto. **É o conserto.** Sai da lista, e não
  da binária: da binária, o miolo das letras brancas da faixa viraria sinal.
- **`moldura._miolo_da_faixa`** (sai com `TIRAR_MOLDURA`): quando a faixa sai como moldura, o miolo das letras brancas sobra como tinta
  solta, e era uma coluna a mais de lixo (`a i ws dof May 2014 1 ...`). Só a parte grossa da moldura é preenchida: nem o filete nem o
  anel que dá a volta na folha cercam nada que deva sair.
- **`duas_linhas.partir_linhas_altas`** (`PARTIR_LINHA_ALTA`): é a *Entrega* do roadmap. Acima de 1,8 mediana da tira, corta onde a
  contagem de caixas por fileira cai a um quarto da fileira mais cheia. **Paga pouco:** no ouro-dev e no *Chess Evolution* não muda
  nenhum texto, e na prata o Tesseract vai de 13,30% a 13,17%, com 4 folhas melhores e 1 pior.

### Critério de aceite

`tests/test_text_linha_intercalada.py` e `tests/test_text_moldura.py`, com folhas desenhadas: a faixa sozinha, o fio, o quadro aberto,
a capitular, a foto, o anel grosso, e o caso que **tem de reproduzir** o defeito com a constante desligada. Em
[metrics/texto_prosa_s712.json](metrics/texto_prosa_s712.json), de `6c1b0ade` para `fa537741`:

| | antes | depois |
|---|---:|---:|
| perda de leiaute, 40 folhas **não vistas** dos dois *Chess Evolution* | +3,83 p.p. [+1,78; +6,88] | **+0,56 p.p. [+0,33; +0,86]** |
| perda de leiaute, as 24 folhas olhadas para achar o conserto | +4,29 p.p. [+1,39; +8,76] | +0,39 p.p. [+0,19; +0,67] |
| Tesseract nas linhas do glifo, 40 não vistas | 5,14% | 1,88% |
| linhas acima de 1,8 mediana no ouro-dev | não medido | **0 de 891** |
| linhas acima de 1,8 mediana em 808 folhas do acervo | 1.868 (4,4%) | 1.266 (3,0%) |
| CER de prosa, ouro-dev: glifo / camada na prosa / fusão / Tesseract | 3,78 / 1,04 / 1,31 / 1,40% | **2,84 / 0,31 / 0,47 / 0,46%** |
| CER de prosa, prata: glifo / fusão / Tesseract | 24,6 / 15,0 / 14,4% | 23,2 / 14,1 / 13,2% |

Nas 40 não vistas, o Tesseract melhora em 33 folhas, fica igual em 6 e piora em 1; o glifo melhora em 35 e não piora em nenhuma. No
ouro-dev, 24 das 28 folhas saem com o mesmo texto, e nenhuma piora: **os 5 livros aprovados na auditoria dão exatamente o mesmo número**
(0,221% na camada, 2,83% no glifo), porque o ganho é todo das quatro folhas do *Chess Evolution*, que é um dos dois reprovados. O
oráculo não muda: o que caiu foi a perda de leiaute. O glifo fica em 5,11% nas não vistas e é ainda o padrão.

**O que saiu.** Ligando e desligando no mesmo processo, em 808 folhas: 837 caixas a menos, de 177 folhas, e cada uma era lida como um
caractere só. Vi as folhas de onde saíram mais: capa, contracapa, código de barras, e o miolo da faixa. 44 tocam texto da camada: 24 são
os dígitos do código de barras de uma contracapa, 7 são o título da faixa do *Chess Evolution*, e o resto é capa, camada de OCR de
terceiro, e duas ou três caixas que só cruzam uma linha.

**A guarda continua inteira.** Folhas perdidas nas 120 de cada *Chess Evolution*: 0. Na varredura, avisadas sobem de 10 a 12, as duas a
mais em contracapa (*Silman* 387, sobre fundo vermelho, e *Boleslavsky* 257): com menos sinal solto lido, elas ficam logo abaixo do corte
de 0,5, e o aviso é verdadeiro. `metrics/texto_estilo_por_motor.json` foi remedido: negrito 7,3%, itálico 32,3%, praticamente igual.

### O que ela não entrega

- **O acervo inteiro não fica sem linha alta.** Sobram 1.266 de 42.495, 450 delas em primeira folha de livro. O resto é título grande,
  tabuleiro que o detector não viu, tarja e scan ruim. O limite de 1,8 mediana é sinal, e não defeito.
- **O pedaço da vizinha não volta para a linha dele:** a partição o deixa como linha à parte, ou o descarta como fragmento.
- **O rodapé que atravessa a calha** (`www.chess-n` + `ewsletter.com`, em quase toda folha do *Chess Evolution 2014*) continua partido entre
  as duas colunas. Ele é parte do que sobra da perda de leiaute, e é da detecção de região.
- **Na prata, duas folhas pioram na fusão:** *Kmoch* 30 e 105. A camada do *Kmoch* é desalinhada da tinta, e a régua ali é fraca.
- **A faixa entre 3 e 8 escalas não foi examinada caixa a caixa**: título e capitular ficam, e uma foto com menos de 80% de tinta também.

## S-713 · A perda de leiaute como métrica de primeira classe ✅ implementada (2026-11-06)

**Decisão.** `relatorio_prosa` publica `perda_de_leiaute` em todo bloco que tem `tess` e `tess_oraculo`: a diferença pareada com IC95 de dois níveis, `cer_tess`, `cer_tess_oraculo` e `cer_tess_pagina` ao lado, e, por livro, a mesma conta com IC por folha. O bloco do teste sairia sem o por livro.

| | perda de leiaute | Tesseract nas linhas do glifo | oráculo | Tesseract na página |
|---|---:|---:|---:|---:|
| ouro-dev | **+0,16 p.p. [−0,01; +0,56]** | 0,27% | 0,11% | 0,37% |
| degradado médio | **+9,19 p.p. [+3,74; +15,53]** | 10,74% | 1,55% | 2,36% |
| prata (ordenação) | +0,88 p.p. [−1,61; +2,94] | 10,08% | 9,20% | 8,25% |

No dev, o custo mora num livro: o *Hertan*, +0,63 p.p. [0; +1,59]; os outros quatro dão 0. O orçamento da seção 3 é ≤ +0,10 p.p., e o ponto não cabe nele. A S-714 pede ≤ 2 p.p. no perfil médio, e está a +9,19.

*Achado:* **a reserva custa menos do que a seção 1 dizia.** O `tess_pagina` publicado em 2026-10-30 pagava um erro por linha, de CRLF (S-700): 0,37% no dev, e não os 2,24% de lá, medidos em outros livros também. Ele é o melhor na prata e no degradado, depois do oráculo.

**Critério de aceite.** `test_perda_de_leiaute_por_livro_com_ic_e_tess_pagina`, e o relatório versionado traz os cinco livros do dev (`RelatorioPublicadoTests`).

## S-714 · A poeira que estica a linha ✅ implementada (2026-11-06)

### Problema

No perfil médio de hoje, com S-711 e S-712 dentro, a perda de leiaute é +6,52 p.p. [+1,35; +12,65] nas 28 folhas do ouro-dev, e
+10,17 nos cinco livros em que o oráculo presta. O roadmap supunha, em ordem, binarização, poeira e linhas que tocam. **É a poeira.**
Uma mancha na margem tem o tamanho de um ponto final, passa pela régua de área, entra na linha, e `envolve` leva a caixa até ela. A
caixa de `Apesar das pretas`, no *Seirawan* 58, ia da margem à margem e invadia a linha de cima; com 62 px de altura, onde a linha
tem 38, o Tesseract em `psm 7` devolve vazio.

### Solução

`text/poeira.py`, com a reversão em `TIRAR_POEIRA`. Duas réguas, porque são duas manchas:

- **`sem_poeira`, a mancha solta**, antes de `unir_pingos`: caixa pequena (maior lado abaixo de 0,5 altura mediana) a mais de uma
  altura mediana de qualquer letra e de qualquer outra caixa pequena. Só vale com **6 ou mais** na folha (`POEIRA_MINIMA_NA_FOLHA`). Em
  210 folhas limpas dos sete livros há de 0 a 3, 184 delas com 0; no perfil médio, de 18 a 136. **A outra caixa pequena conta** porque as
  reticências espaçadas de `9 . . . Cxe4`, no *Capablanca* limpo, eram os únicos pontos que uma folha limpa tinha a perder.
- **`aparar`, a mancha entre duas linhas**, na linha já formada: ela não está solta, e é a que mais custa. Sai a caixa pequena com o
  centro a mais de 0,35 mediana do miolo (a mediana dos topos e dos fundos das letras), e a caixa pequena na ponta a mais de 1,5 mediana
  da vizinha. A que `unir_pingos` já colou numa letra sai cortando a letra no que uma letra alcança: 0,9 mediana acima do topo do
  miolo (a maiúscula acentuada) e 0,5 abaixo do fundo (o descendente). Passou disso em mais de uma mediana, a caixa não é letra com
  mancha, e fica para a S-198 e a S-712. Vem depois de `partir_linhas_altas`: antes dela, a linha pode ter outra linha dentro.

Em `leitor.py`, duas chamadas e um `import`.

### Critério de aceite

`tests/test_text_poeira.py`, com caixas desenhadas e a fiação pelo `segmentar`, e a constante desligada devolve exatamente as linhas de
antes (conferido em duas folhas reais). Em [metrics/texto_prosa_s714.json](metrics/texto_prosa_s714.json), pareado contra o leiaute de
hoje, Tesseract nas caixas do glifo, IC95 de dois níveis, tudo no **perfil médio sem calibração**:

| | antes | depois |
|---|---:|---:|
| perda de leiaute, 28 folhas olhadas | +6,52 p.p. [+1,35; +12,65] | **−3,18 p.p. [−9,10; +1,51]** |
| a mesma, sem os dois livros de oráculo ruim (20 folhas) | +10,17 p.p. [+4,07; +16,81] | **+0,85 p.p. [−1,35; +3,10]** |
| perda de leiaute, 21 folhas **não vistas** | +10,54 p.p. [+0,92; +21,90] | **−0,06 p.p. [−4,49; +3,89]** |
| a mesma, sem os dois livros (15 folhas) | +11,40 p.p. [+3,26; +21,91] | **+2,46 p.p. [−0,24; +6,21]** |
| CER de prosa, Tesseract, 28 olhadas | 13,02% | **3,32%** (−9,70 [−14,93; −5,15]; 27 melhores, 1 pior) |
| CER de prosa, Tesseract, 21 não vistas | 14,27% | **3,67%** (nenhuma pior) |
| CER de prosa, fusão, 28 olhadas | 16,15% | 6,72% |
| CER de prosa, glifo, 28 olhadas | 53,35% | 51,96% |
| **ouro limpo**, 28 folhas: glifo / Tesseract / fusão | 1,21 / 0,46 / 0,47% | **1,20 / 0,46 / 0,47%** |

No ouro limpo o Tesseract lê todas as linhas iguais, e o glifo muda duas, as duas para melhor (`Perdidas".` e `Marocey`).

**A saída cumpre-se com ressalva, e a ressalva é o oráculo.** A *Saída* pede ≤ 2 p.p.: nas folhas olhadas sim, com qualquer recorte; nas não
vistas, sim com os sete livros, e fica em +2,46 sem os dois. O número negativo com os sete é o oráculo errando mais que as caixas do
glifo (26,0% no *Capablanca*, 6,4% no *Chess Evolution*), e não mérito delas. Por isso a linha de cinco livros é a que importa, e o
limite superior do IC dela, +3,10 e +6,21, não cabe em 2. Pior livro: *Seirawan*, +3,41 nas olhadas e +5,48 nas não vistas.

**Os outros dois suspeitos, medidos.** Binarização: o Otsu sobe mesmo, de ~140 a ~205 no perfil médio, e a tinta dobra. Trocá-lo pelo
meio entre papel e tinta, sobre a poeira, leva o Tesseract a 3,01% (27 folhas), o *Seirawan* a 0,39%, e o glifo a 7.532 inserções contra
1.150: parte as letras dele. **Medido, não entra**; o Otsu alto fica como está. Linhas que tocam: 14 linhas acima de 1,8 mediana em 898,
3 depois do filtro. Não são a causa.

### O que ela não entrega

- **O perfil calibrado não existe**: depende da S-703, que é humana. O perfil médio é sintético, e a mancha dele é um ponto escuro de
  um pixel a meia resolução. Em scan de verdade a poeira tem outra forma, e o corte de 6 caixas soltas não foi visto em scan nenhum.
- **O glifo continua em ~52%** no perfil médio: o conserto é da caixa, e o glifo erra por dentro dela.
- **Há linhas inteiras que o `psm 7` ainda devolve vazias** com a caixa certa ou quase: é onde mora o que resta no *Seirawan* e no *Minhas 60* 217.
- **A mancha sobre uma letra é acento**, e fica: a régua não a distingue, e a caixa só cresce até o corte acima.
- A mancha entre as palavras de uma linha também fica: não muda a caixa, e é indistinguível de um ponto.

## S-715 · O leiaute de reserva ✅ implementada (2026-11-05)

### Problema

O Tesseract lendo a página inteira, com o leiaute dele, nunca desaba; numa folha normal é pior que as caixas do
glifo. Vale exatamente onde a guarda dispara.

### Solução

`leitor._linhas_da_reserva`: com a guarda acionada, a folha é relida em `psm 3`, com os diagramas em branco, e sai
com o aviso `leiaute_de_reserva`. A notação continua do glifo onde ele achou caixa de altura de linha. Sem
Tesseract, a folha sai como o glifo a leu, com `leitor_indisponivel`.

**O interruptor vem desligado, e só a janela o liga** (`ler_pagina(reserva=True)`, em `qt/painel_de_texto._ler`).
Ligada por padrão, ela mudava a régua: `rodar.py`, `cobertura.py` e os CLIs que publicam relatório passariam a dar um
número que depende de haver Tesseract na máquina, e o *Chess Evolution* 903 ia de 1 linha a 69 no meio de uma medição.

**O conserto que a medição pediu, e o roadmap não previa.** Em folha de duas colunas com fio no meio, o `psm 3`
escreve as duas colunas na mesma linha: no *Kmoch* 106, 369 palavras em 40 linhas, onde a folha tem 70, e o texto
sairia intercalado. `_partida_no_vao` parte a linha na calha, tanto no vão largo quanto no token `|`, que é o fio
lido como letra. `montar` acha as colunas nas caixas resultantes. O CER contra a camada caiu de 0,79 para 0,29.

### Critério de aceite

Medido **antes da S-711**, em `2e030e3`, e reproduzido pelo crítico até a 4ª casa: *Chess Evolution 2013* 903 e 1210 com 4,6% e
2,1% de CER de prosa; as três do *Kmoch* com 100%, 97,2% e 96% das linhas da camada, que está desalinhada da tinta e por isso
não dá CER, e a folha 106 conferida à vista pelo crítico. Nenhuma folha legível do ouro aciona a reserva. **Depois da S-711 essas
folhas não chegam mais aqui:** no acervo, ela só dispara em quatro folhas de 812, em que o glifo não leu o texto. A linha curta sem
palavra que exista, que era o resto da faixa, sai da folha relida.

## S-716 · A prosa da camada nos livros digitais ✅ implementada (2026-11-05)

### Problema

A camada foi recusada como motor por causa da **notação**, que ela não representa, e não da prosa. Nos livros
nascidos digitais a prosa dela é a tinta.

### Solução

`motor="camada_prosa"`, com o rótulo "Camada na prosa (livro digital)". `text/camada_prosa.py` põe cada palavra da
camada na linha do glifo que contém o centro dela (caixa crescida 15% na vertical), e `text/fusao.py` funde. A
admissão é a de `text/admissao.py`, com o perfil do livro em memória. Folha recusada lê como o glifo, com
`camada_recusada`; capa e branco (`sem_texto`) não avisam.

**A folha que a guarda acusa não pode contornar a checagem de ligadura.** Quem manda ali é a montagem da camada, com
as palavras partidas no vão: nada se perde, e o lance fica como ela o escreve, sem figurina, o que o selo diz. Com a
reserva, **só a palavra de prosa suspeita** vem do Tesseract, lida na mesma caixa; o lance nunca, nem marcado, porque ele chega
bloqueado pela fonte de figurina com a letra certa. Sem reserva, a suspeita fica como está, e marcada `revisar`. As três versões anteriores erraram aqui, e valem de aviso: a primeira usava a camada crua, com `afer` e tudo;
a segunda punha as linhas do Tesseract no lugar do glifo, e `10.Qxd2` saía `10.8xd2`, com o selo falando de outra coisa; a terceira
só reconhecia o lance limpo, e o lance com sinal colado, que a camada escreve em código de fonte (`19.Bd3\uf0b1`, `Rxg5i`,
`24...f4e`), ia ao Tesseract e voltava `19.2d3+`. A conta de "1.298 de 1.300 intactos" não via isso, porque a régua chama esses
tokens de prosa. Hoje o instrumento conta lance por prefixo: **1.346 de 1.346 intactos**, em 28 folhas forçadas, e os 22 `afer`
viram `after`. O sinal solto da fonte de figurina (o `i` que voltava `eel`) também não pede outra leitura:
`PalavraDaCamada.de_figurina`.

**O PDF não precisa escrever o espaço.** No *Chess Evolution* ele é um salto de posição de 1,76 pt em corpo 13, sem
caractere nenhum, e `get_text("words")` devolvia tokens de até 52 letras. `palavras_da_folha` parte onde o vão passa
de 0,1 corpo, medido do **maior fim já visto**: o segundo caractere de uma ligadura mapeada direito tem largura zero,
e medir dele partia `Aerofl|ot`.

**(a)-(d) não bastam, e a checagem que a S-702 pediu está aqui.** Palavra com letra mais larga que 1,4× a mediana
dela na mesma fonte é ligadura que perdeu letra (`after` -> `afer` no *Chess Evolution 2013*), e fica com o glifo.
O `fi` mapeado direito mede a mesma largura, mas vem seguido de um `i` de largura zero, e não é acusado: sem essa
exceção, `first` saía `frst`. Palavra em fonte de figurina, com código que não é figurina em Unicode, também fica
com o glifo.

**Na camada, toda prosa existe** (`fusao.existe_na_camada`). O léxico não tem `arranca` nem `Gelfand`, e a regra
"notação do glifo, salvo palavra que existe" entregaria ao glifo a palavra certa do editor.

### Critério de aceite

M0 medida só nos livros aprovados na auditoria visual da S-702, em
`metrics/texto_prosa_primeira_entrega.json`, com G1 e G2 contra o glifo. **A G6 (negrito e itálico) não foi medida**
pela régua da S-660: o que há é teste de fiação de que o detalhe da camada chega à linha, e a medida fica para o G102. **A meta M0 de ≤ 0,05% é do portão G107, e
não está cumprida**: o que sobra é quase todo notação que a régua conta como prosa (`1...B` contra `1 B`) e leiaute do
*Hertan*. Nos livros com camada de OCR a admissão recusa, e o texto é o do glifo, caractere a caractere.

**A M0 não enxerga dois defeitos, e isso é da referência.** Ela mede contra a mesma camada: ligadura perdida e espaço
não escrito saem iguais nos dois lados. Foi o crítico, olhando a tinta, que os achou.

## S-717 · A fusão experimental na janela ✅ implementada (2026-11-05)

### Solução

`motor="fusao"`, com o rótulo "Glifo + Tesseract (experimental)", é a regra v5 de 2026-10-30, escrita sobre tokens e
aplicada **dentro** de `ler_pagina`, antes de `_com_negrito`, `_com_trechos` e da junção de hífen, para esses
trabalharem sobre o texto fundido. Medida nos aprovados na auditoria: 0,351% contra 0,279% do Tesseract puro, +0,072 p.p.
[0; +0,16], um pouco acima do teto de +0,1 que a S-721 pede; no ouro inteiro, −0,099 p.p. [−0,55; +0,11]. Duas regras da S-721 já entram: a palavra que só o glifo leu certo fica com ele
(regra 4), e a barra `|` não vence letra nem dígito, nem entra sem par, que eram 8 de 20 erros lidos à mão. O que sobra
de `|` é quando o glifo também não leu nada ali. A língua é escolhida à mão na caixa
nova da aba e fica no estado da janela; a S-723 a leva ao caderno. **Trocar a língua pede a leitura nova**, como trocar
de motor: o caderno anota `fusao:por`. O padrão não muda: `auto` continua o glifo.

### Critério de aceite

`tests/test_qt_texto_prosa.py` escolhe a opção na caixa, lê uma folha de um PDF desenhado no teste, e afirma o texto
mostrado e a língua pedida. A medida está em `metrics/texto_prosa_primeira_entrega.json`.

### O que ela não entrega

A regra v3 no scan, o `--user-words`, o dicionário desligado nas linhas de notação, o léxico da língua do livro e a
escala pela altura-x são da S-721, da S-728 e da S-720 completa: cada um muda o que o Tesseract lê, e a saída da S-720
pede o mesmo texto da corrida de 2026-10-30. Em alemão a fusão perde do Tesseract puro no *Brinckmann*, o que a S-721
já prevê com a v3. A leitura mostra o resultado de uma vez, sem o glifo primeiro.

## S-718 · A marca "revisar" honesta, por palavra ✅ implementada (2026-11-05)

### Problema

A confiança do glifo pintada sobre o texto do Tesseract marca `revisar` o texto certo porque o glifo errou ali. E os
sinais crus inundam: 10,0% a 40,1% das palavras, contra um teto de 5%.

### Solução

`fusao.marcar` ranqueia, e marca as mais suspeitas até 5% das palavras da folha, arredondando para baixo. Os sinais
são os de quem escreveu o token: discordância com o glifo, palavra fora do léxico e a confiança do próprio leitor.
Prosa da camada nunca é marcada. `LinhaLida.revisar_em` vive em memória, e o que atravessa o arquivo é a faixa da
corrida, sem mudar o formato. `Shift+F7` vai à próxima, por `rico.intervalos_a_revisar`, também na folha reaberta.

**Corrigir uma palavra não apaga as outras marcas do parágrafo.** O carimbo de `correcao.com_procedencia_humana` é por bloco, e
a folha reaberta perdia as marcas sem aviso, embora na mesma sessão elas sobrevivessem. Agora a marca fica se a **palavra** em que
ela está é, inteira, a que o motor leu, e a comparação é palavra com palavra. **Olhar a corrida não basta:** o editor grava a
diferença mínima, e corrigir `wbite` deixa `w` e `ite` como `revisar`. **Olhar caractere também não:** apagar `a ` em `to a and`
casa `to a` e `nd`, e `and` perdia a marca. A faixa do bloco inteiro continua saindo, e **quem separa os dois casos é o espaço**: a
marca da palavra é um token, e `rico._pedacos` garante que não há espaço nela, nem onde `camada.remapear` uniu duas vizinhas, em 17
de 414 folhas; a faixa tem espaço em algum pedaço que a edição deixa, salvo quando a mão troca o último branco dela (`correcao._marcas_intactas`). O espaço que a mão pôs não
conta. A marca do fim de uma linha e a do começo da seguinte são duas corridas (`rico._agrupar`). `Shift+F7` pergunta à mesma regra,
e não para nos pedaços nem antes de gravar. As guardas são `CorrigirAMarcaNoEditorTests`, pelo editor com `QTest`, e
`MarcaPorSorteioTests`, que sorteia correções gravando no meio.

**O que sobra:** até gravar, a tinta na tela continua nos pedaços. A faixa reduzida a uma palavra sem espaço fica marcada como se
fosse palavra (`wbite`, com ` knight` apagado, ou acrescentado). Apagar uma letra e digitar a mesma deixa os pedaços marcados, porque
a palavra é a que o motor leu. Uma marca de parte do token sai junto se a mão mexer no resto dele (`wlns,` trocado por `wlns.`), o que
não apareceu em 853 marcas de 62 folhas. O negrito em metade da palavra marcada dá duas paradas no `Shift+F7`. **E o alinhamento pode
errar quando a palavra escrita já existe por perto:** em `a wbite white`, corrigir `wbite` deixa a marca; em `the wlns rests`, digitar
outro `wlns` antes a tira. No sorteio, com palavra nova do próprio vocabulário, são de 25 a 40 de 3.000 rodadas em 60 palavras, e 10 de
1.500 em blocos de 8. Em folha real foi 1 em 294 trocas pela busca, e nenhuma em 1.629 outras edições. O efeito é só uma marca a mais
ou a menos, e o texto não muda.

**Desvio declarado:** as alternativas do `lstm_choice_mode=2`, que o roadmap cita, saem no hOCR e não no TSV. Aqui o
terceiro sinal é a confiança por palavra do TSV; a S-761 calibra.

### Critério de aceite

G5 provisória em `metrics/texto_prosa_primeira_entrega.json`, com a fração marcada travada em 5%: 4,8% das palavras
marcadas, com captura de 50% no ouro, 42% nos aprovados na auditoria e 26% na prata. **Longe do alvo de 90%, que é da
S-761.** O interruptor é `ler_pagina(marca_por_palavra=False)`, e vale a faixa de hoje.

## S-720 · O executor do Tesseract e o contrato `LeitorDeLinha` ✅ implementada (2026-11-05)

### Solução

`text/tesseract.py` e `text/leitor_de_linha.py`, fora de `ocr.py`, que está no digest da S-218. Um processo por
folha, com um TIFF de várias páginas pelo stdin, `psm 7`; `CREATE_NO_WINDOW` e os três canos explícitos; `kill` no
timeout; *Job Object* com `KILL_ON_JOB_CLOSE`; binário só por caminho absoluto, com o diretório corrente fora da
busca; `--version` conferida (5.x); `TESSDATA_PREFIX` do executor sobrescrevendo o do ambiente; teto de 60 MP; erro no
`stderr` com saída 0 também vira falha, e não texto vazio.

**Caminho acentuado:** a imagem vai pelo stdin, e o `TESSDATA_PREFIX` pelo ambiente. `test_tessdata_em_caminho_acentuado`
lê de verdade numa pasta com acento, **mas esta máquina tem a code page em UTF-8 e não reproduz o defeito de uma cp1252**.
A conferência numa máquina assim fica para a S-724, junto do instalador.

O contrato distingue **"não leu"** (`None`, com a frase na `Leitura.falha`) de **"leu vazio"** (`""`). Ausência do
motor nunca levanta no caminho da janela.

### Critério de aceite

`tests/test_text_tesseract.py`: o *parser* sobre saídas gravadas, sem o binário, processo falso que erra, estoura e
não abre. **Diferença zero** contra a leitura de um processo por linha em 2.908 linhas do ouro e da prata, a 0,71 s por
folha contra 3,2 s, em `metrics/texto_prosa_primeira_entrega.json`, chave `executor`. O G4 não se julga por esses
tempos: outras medições rodavam na máquina.

### O que ela não entrega

`--user-words` e `load_system_dawg=0`: um processo por folha tem uma configuração só, e separar as linhas de notação
é a S-721. A escala pela altura-x muda o texto lido, e entra medida. O timeout é 1 s por linha com piso de 10 s, e
ainda não 10× o p99 medido. O Tesseract no instalador é a S-724, que espera a D1.

## S-727 · Os CLIs de medição fixam o motor ✅ implementada (2026-11-06)

### Problema

O G102 vira o padrão de `ler_pagina`. Sem motor escrito, o que um CLI mede mudaria junto, em silêncio. Medido em
`cli/texto_*.py`: uma chamada sem `motor=` (`texto_lexico`, a junção no glifo), e três relatórios que usavam um motor
sem dizê-lo (`texto_custo`, `texto_estilo_motor` e a mesma junção).

### Decisão

Todo `ler_pagina` de CLI escreve o motor; quem publica relatório o grava. `MOTOR_MEDIDO` em `texto_custo` e
`MOTOR_DA_JUNCAO` em `texto_lexico` são a mesma constante na leitura e no relatório, para os dois não divergirem.
`texto_estilo_motor` grava `motores`; `texto_pesquisavel`, que não publica JSON, escreve o motor na saída. Número nenhum
muda: o que se escreveu é `glifo`, e é o `MOTOR_PADRAO` de hoje. Os relatórios antigos ficam como estão.

### Critério de aceite

`tests/test_texto_clis_motor.py`: varre os arquivos por `ast` e reprova chamada sem `motor=`, também com import dentro
de função, apelido, acesso pelo módulo e `**opcoes`. Os casos sintéticos provam que a guarda acusa, e um deles grita se
a varredura ficar vazia. `texto_placar_final` tem um homônimo local, e não conta.

## S-728 · Léxico por língua ✅ implementada (2026-11-06)

### Problema

`text/lexico.py` tem perfis, e não línguas: `idioma.txt.gz` mistura oito, e o que distingue uma palavra de `por` de uma
de `eng` não existe em lugar nenhum. A S-723 e a S-721 pressupõem que exista. O que se tem em disco, sem baixar nada, são
as listas de dentro dos `.traineddata` do Tesseract.

### Decisão

`assets/lexico/linguas/<código>.txt.gz`, uma por código do Tesseract, com `manifesto.json` e `LICENSE.tessdata` ao lado.
`cvoff-texto-lexico --linguas-de` as refaz byte a byte. `lexico.da_lingua(codigo)` é quem lê, e nenhum perfil as inclui.
A régua (`aceita_na_lingua`) deixa só minúsculas de 4 letras ou mais, e o alemão fica também com a inicial maiúscula.
Palavra curta tem tabela à mão em `text/fusao.py`: as curtas da lista bruta são lixo (`mk`, `Rd`, `Kf`).

Numa pasta própria, e não ao lado das outras, porque o README publica "três listas e 367.163 entradas" sobre o que o
perfil do glifo une, e essa frase continua verdadeira. `BUNDLE_ROOT`, porque `assets/` fica dentro do pacote.

### Critério de aceite

`tests/test_texto_lexico_linguas.py`: régua, byte a byte, sha e contagem do manifesto contra o disco, licença ao lado, e
nenhum perfil lendo a pasta. `test_docs` confere a contagem de cada língua no README, e `test_disciplina_da_suite`, que as
listas estão versionadas. **Diferença zero** do `motor="glifo"` em 28 folhas do ouro-dev, contra `a2937260`, com
`docs/metrics/texto_lingua_2026-11-06/medir.py glifo` e `comparar`.

### O que ela não entrega

Uma lista limpa. O corpus do Tesseract é da web: `after`, `para` e `avec` estão em sete das oito, e `fixes` está em `por`,
como conta `assets/lexico/PROCEDENCIA.md`. A lista diz que a palavra existe; não diz que ela é **só** daquela língua. A D5
(o `acervo.txt.gz`) segue com o dono.

## S-723 · A língua do livro ✅ implementada (2026-11-06)

### Problema

O Tesseract precisa saber a língua, e a caixa da S-717 a guardava no estado da janela: a escolha do livro em português valia
para o livro em alemão aberto depois. O `existe` da fusão usava `idioma.txt.gz`, que mistura oito línguas, e as `CURTAS` de seis:
`Pas` vencia `♔a5` num livro em português.

### Decisão

`text/lingua.py`, puro: um perfil de palavras funcionais à mão, uma contagem sem texto nenhum, e `decidir`, que responde `""`
quando a evidência não basta. **Só minúscula e nunca uma letra só**, porque `De` e `Le` são lance e `a` é coluna. Palavra de
várias línguas se reparte entre elas, e é isso que separa português de espanhol. O russo se decide pelo alfabeto.

**A fonte da folha é a camada, quando ela traz palavras; senão, o texto lido** (`texto_da_folha`). Numa folha russa o glifo escreve
latim sem sentido, e a camada, mesmo de OCR de terceiro, basta para dizer a língua.

`Caderno.lingua()` e `guardar_lingua`, em `lingua.json`, **fora do índice**: o índice se refaz das folhas, e uma escolha da pessoa
não pode sumir com ele. **A manual sempre vence a detectada.** Ela vem da caixa da fita ou de «Língua do livro…» no menu Texto, e
só o menu volta a «Detectar pelo livro». Nada em `settings.py`. `texto_lingua` do estado da janela virou só o padrão de quem ainda
não tem língua, e a do livro aberto não passa mais para ele.

`ler_pagina(lingua=)` já existia para o `tessdata`, e agora escolhe também o léxico: `fusao.existe_do_livro(lingua)` é a lista da
S-728, mais `acervo` e `nomes`, e as curtas **da língua**. Em `text/leitor.py` é uma linha. `fusao.LEXICO_POR_LINGUA` desliga. Em
`existe_no`, a régua de palavra passou a aceitar qualquer alfabeto, senão `după` e o russo nunca existiam. O `motor="glifo"` não muda:
**zero** folhas diferentes em 28 do ouro-dev contra `a2937260`.

As dez folhas sem resposta dizem no rodapé que a pessoa escolha, porque calar seria ler em inglês para sempre.

### Critério de aceite

`tests/test_texto_lingua.py`: o decisor com textos curtos das oito línguas, nunca lendo livro; `RelatorioTests` refaz a decisão sobre as
contagens de `metrics/texto_lingua_20261106.json`, confere a tabela à mão, reprova relatório de outro perfil, e reprova qualquer livro
com língua **errada**. `tests/test_qt_texto_prosa.py`: o que o leitor de linha de mentira recebeu, na primeira e na segunda leitura; a
manual vencendo; a língua voltando com o livro e não passando para outro; `OSError` sem derrubar o slot. Quinze mutantes, um por peça,
morrem.

**Medido em 54 livros deduplicados de `PDF/`, nas primeiras folhas com texto:** 52 certos, 2 sem resposta, nenhum errado (só o glifo:
50, 4, 0; só a camada: 38, 16, 0). Os sem resposta: `1000 Chess Problems`, sem prosa, e `Пилавов`, scan russo sem camada.

### Desvios

- **A saída pedia "todos os livros".** São 52 de 54, e não se ajustou nada para fechar a conta. Fica a recomendação: um scan cirílico sem
  camada se resolve com o `osd` do Tesseract, que não entrou por não ser palavra funcional e por valer um livro só.
- **O *Zhuravlev* é bilíngue**, e a tabela o diz à parte: declarado russo, e inglês conta como certo.
- A leitura para antes das dez folhas quando já há quatro folhas e cinco vezes a evidência mínima: a medida custava minutos por livro.
  O relatório diz quantas folhas cada um contou; a janela conta até dez.
- A tabela à mão está em `docs/metrics/texto_lingua_2026-11-06/linguas_declaradas.json`, lida pelo teste, e não no código dele.
- A primeira folha de um livro novo é lida no padrão. Detectar antes custaria outra leitura de glifo por folha.
- `lingua.json` não sobe `VERSAO_DO_INDICE`: é arquivo novo, que a versão antiga ignora.

## S-721 · A fusão por token, com a regra por estrato ✅ implementada (2026-11-06)

### Problema

A S-717 entregou a fusão mínima: a v5 em toda folha, sem a regra 5. **Medida nesta árvore antes de mexer**, no ouro-dev: prosa −0,025 p.p. contra o Tesseract puro [−0,119; +0,044], o que já passava; **notação +1,56 no teto contra o glifo, G1(a) em 98,8% e G2 com o piso abaixo de −1**, o que não passava. Na prata admitida, prosa +0,51 p.p. [−0,07; +1,53] e notação +12,6 p.p. contra o Tesseract: a v5 entrega a notação em letra ao glifo, e no scan o Tesseract a lê melhor. As pendências da S-723 (`Pas` contra `♔a5`, `Axed` contra `♘xc4`) eram a mesma família de `Das` contra `♔a4` e `fixes` contra `♕xe5`.

### Decisão

`fusao.fundir(regra=)`, no ponto do topo da Fase 102: `_ler_pagina_do_livro`, depois de `linhas_do_glifo`, antes de `_com_negrito`, `_com_trechos`, `montar` e da junção de hífen. **A regra sai de `leitor.regra_da_folha`, pela admissão, em tempo de execução**: critério (d), `a:livro_de_scan`, `a:invisivel`, `a:coberto_por_imagem` e folha sem camada são a v3; admitido ou recusado por (b) e (c) é a v5. `motor="fusao"` forçado num digital admitido é a bancada, como a M1 pede: a fusão não roda ali só em `auto` depois do G102. O padrão não mudou.

As regras da v5 e da v3 estão no cabeçalho de `fusao.py`. O que a medida acrescentou a elas, cada uma atrás de constante:

| constante | o que faz | sem ela, no ouro-dev (notação) | sem ela, na prata admitida (prosa; notação) |
|---|---|---:|---:|
| `LANCE_INTEIRO_NAO_SE_VETA` | peça e casa não perdem para palavra: `♔a4` e `Das`, `♕xe5` e `fixes`, `♘xc4` e `Axed`. As duas pendências da S-723 acabam aqui | +0,13 [0; +0,43], e 4 figurinas a menos | −0,00; 0 |
| `FIGURINA_FORA_DE_LANCE_PERDE` | `nta♔`, `ge♔h1ich` perdem para palavra de 4 letras ou mais, mesmo fora do léxico. Conta como veto | 0 | +0,08 [0; +0,29]; 0 |
| `LANCE_TORTO_NAO_ENTRA` | `14...♕c6` contra `14...` e `Hc6`: o `Hc6` sem par não entra | +0,41 [0; +1,54] | 0; 0 |
| `RETICENCIA_DO_LEITOR` | `6. . . ♕` e `6...` dão `6... ♕` | +0,44 [0; +1,36] | 0; 0 |
| `NUMERO_DO_GLIFO_NAO_SE_COLA` | `11` contra `28711` ou `Ea836`: fica o do glifo | 0 | 0; +0,04 [0; +0,29] |
| `SEM_PAR_NA_V3_SO_FIGURINA` | na v3, sem par só a figurina fica, salvo se o leitor leu a linha **vazia**: lá ele não viu | 0 | +0,03 [−0,09; +0,15]; +1,41 [−4,14; +4,6]; na prata inteira, +0,51 [+0,04; +1,27] e +3,46 [+0,53; +5,39] |
| `GUARDA_SO_O_QUE_EXISTE` | a regra 5 guarda **palavra**, e não o que o glifo inventou | prosa +0,16 [0; +0,42] | +1,18 [+0,12; +3,08]; +3,03 |

**A regra 5 como o roadmap a escreve põe a prosa de 0,24% em 0,42% no ouro-dev e reprova a saída**: é ruído do glifo entrando. Guardando só a palavra que existe, ela paga onde paga (prata inteira, −0,33 p.p. de prosa, [−1,04; +0,10]) e não custa no dev.

**As quatro regras da suíte (S-707), medidas:** a âncora que já é palavra ou lance não se troca entra como as duas primeiras linhas da tabela; `_keep_number_prefix` entra com o parêntese (`PARENTESE_DO_NUMERO`: um token em 57 folhas). **`_truncates_long_notation` não entra:** não disparou em nenhuma das 57 folhas, e regra sem caso é só código. **A disputa que vira revisão não entra:** a captura da G5 ficou em 64,4% com e sem no ouro-dev, e cai de 30,0% para 29,2% na prata, com 4,8% de palavras marcadas. Das 39 disputas do ouro, a maior parte é pontuação (`White's` contra `White’s`).

**O veto por léxico contra o veto por letras na v3.** Antes da exceção do lance inteiro e da figurina fora de lance, o por letras ganhava 0,10 p.p. na prata admitida, [−0,32; +0,00], e perdia 13 figurinas a mais. Com as duas regras, **os dois dão o mesmo texto folha a folha**, e a constante saiu.

**Os três ajustes que a S-720 adiou não pagaram, e ficam desligados:**

| ajuste | ouro-dev (prosa) | prata admitida (prosa) | por quê |
|---|---:|---:|---|
| `tesseract.ESCALA_PELA_ALTURA_X`, alvo de 20 a 30 px | +0,004 [−0,029; +0,048] | −0,007 [−0,104; +0,100]; na prata inteira −0,154 [−0,509; +0,066] | não abre de zero. A S-740 pode voltar a ele no scan |
| `leitor.DICIONARIO_FORA_NA_NOTACAO`, `load_system_dawg=0` | 0 | 0 | **0 de 120 linhas de notação mudam**: o LSTM não lê essa variável em tempo de execução |
| `tesseract.PALAVRAS_DO_USUARIO`, `--user-words` com os 349.565 nomes | 0 | não fecha | 1 de 316 linhas muda, e para pior (`areas` -> `areias`); **no `spa` o processo termina com erro**, com a lista toda. A S-766 pressupõe esse caminho, e precisa de outro |

### Onde mora

`src/chess_diagram_ocr/text/fusao.py` (`fundir`, `e_lance_inteiro`, as constantes), `leitor.py` (`regra_da_folha`, `GUARDA_PROSA_SEM_PAR`, `_lido_pelo_outro`), `tesseract.py` (`escalado`, `altura_x`, `rodar(opcoes=, formato=)`). A bancada ouve os vetos por `fusao.OUVINTE_DE_VETOS`, e `relatorio_prosa` publica a `guarda_de_notacao` de cada motor; `preservacao_de_figurina` deixou de contar o número de lance, porque `...♖xh4?` que recebe o `11` chegou. O CLI ganhou `--item`.

### Critério de aceite

`docs/metrics/texto_prosa_fusao_2026-11-06.json`, com S-729 ligada, medido no commit dela, sem cache:

| | medido | saída |
|---|---:|---|
| ouro-dev, prosa, fusão − Tesseract puro | **−0,034 p.p. [−0,123; +0,025]**; fusão 0,24%, Tesseract 0,27%; WER 0,58% e 0,97% | teto ≤ +0,1 ✅ |
| G1(a), figurinas fora dos vetos | **721 de 721**, mais 3 vetos, os 3 certos (`tipo`, `adequada.`, `aguda,`), nenhum de outra língua | ≥ 99,5% ✅ |
| G1(b), notação, fusão − glifo | **−1,84 p.p. [−3,88; −0,65]** | teto ≤ +1,0 ✅ |
| G2, revocação e precisão, fusão − glifo | **−0,12 [−0,54; 0]** e **−0,02 [−0,10; 0]** | piso ≥ −1,0 ✅ |
| estrato misto (dev), prosa contra o Tesseract | −0,033 p.p. [−0,119; 0] | IC contém zero ou abaixo ✅ |
| prata admitida, prosa contra o Tesseract (ordenação) | +0,18 p.p. [−0,12; +0,66]; na prata inteira, −0,13 [−0,91; +0,69] | IC contém zero ✅ |

Duas corridas do ouro-dev dão o mesmo texto folha a folha. `tests/test_text_fusao.py`: as regras, as pendências da S-723, o grafo de import transitivo (nada de `regua_prosa`, `relatorio_prosa`, `bancada_prosa` a partir de `fusao.py`) e a lista de curtas privada. `tests/test_text_fiacao_da_prosa.py`: intervalos de negrito caindo no texto fundido, junção de hífen igual com e sem fusão, leitor falso `None` deixando a folha igual à do glifo com aviso, a linha não lida ao lado da lida, o estrato por critério.

**Desvios.** A reserva da S-715 continua na v5: lá a folha já se perdeu, e não foi medida na v3. A confiança da linha fundida segue a do glifo até a S-760. Os limiares foram escritos no dev contaminado: quem julga é o G102.

## S-726 · O modo bloco sai do caminho da página ✅ implementada (2026-11-06)

### Problema

A S-188 foi recusada em agosto por um CER que misturava prosa com notação, e a caixa «Modo bloco (lento)» ficou na aba Texto, com o `--bloco` do `cvoff-texto-pagina`. O item pede a releitura só na prosa e, se a fusão vencer, a remoção com todos os consumidores: dois caminhos híbridos não convivem.

### A medição

Na régua da S-706, em `689132d6`, árvore limpa, `docs/metrics/texto_prosa_bloco_2026-11-06.json`. CER de prosa em `tip`, com IC95 de dois níveis. `glifo_bloco` é `ler_pagina(motor="glifo", modo_bloco=True)` com o RapidOCR do wheel, como a janela o chamava.

| conjunto | fusão | glifo | bloco | figurina (revocação): fusão, glifo, bloco |
|---|---:|---:|---:|---:|
| ouro-dev, 27 folhas, 5 livros | **0,24%** [0,04; 0,63] | 0,95% [0,29; 1,88] | 6,33% [4,62; 9,20] | 85,7, 85,8, **33,4** |
| prata, 30 folhas, 10 livros (só ordena) | **9,19%** [3,92; 16,25] | 19,71% [9,00; 32,47] | 16,20% [8,59; 25,62] | 83,1, 70,6, 81,0 |

Fusão − bloco, pareado: **−6,09 p.p. [−8,95; −4,48]** no ouro-dev, 27 folhas melhores e nenhuma pior; **−7,02 p.p. [−9,84; −4,44]** na prata, 30 melhores e nenhuma pior. **A fusão vence.** O WER diz o mesmo: 0,58% contra 20,16% no ouro-dev, e 15,13% contra 42,01% na prata.

### Quem não tem Tesseract

A fusão depende do Tesseract, e sem ele o que sobra é o glifo. Medido com um `LeitorTesseract` que não acha o binário: **diferença zero contra o glifo nas 57 folhas**, e a folha sai com o aviso `LEITOR_INDISPONIVEL`. A comparação que importa a essa pessoa é glifo contra bloco:

| | glifo | bloco | glifo − bloco | |
|---|---:|---:|---:|---|
| digital (ouro-dev) | 0,95% | 6,33% | −5,37 p.p. [−8,60; −3,06] | tirar **melhora**: 26 folhas melhores, 1 pior |
| scan, ClearScan (3 livros) | 4,37% | 6,93% | | tirar melhora |
| scan, ≥ 300 dpi (4 livros) | 23,24% | 19,65% | | o bloco à frente |
| scan, ≤ 150 dpi (3 livros) | 35,34% | 23,42% | | **o bloco à frente** |
| scan, os 10 livros | 19,71% | 16,20% | +3,51 p.p. [−1,43; +9,81] | IC contém zero; 16 folhas contra 14 |

**Tirar o modo bloco piora o scan ruim de quem não tem Tesseract, e o número é este.** O ganho está em cinco dos dez livros, e é grande em três, onde o glifo desaba: 38,87% → 9,32%, 40,90% → 29,67% e 58,18% → 50,19%; nos outros dois é de menos de 1 p.p., e nos outros cinco o bloco perde. Com o Tesseract, as mesmas três faixas dão 2,75%, 10,65% e 15,78%, abaixo do bloco em todas.

**Quem pode pagar esse preço é pouca gente, e o programa instalado não é ela.** O bloco precisa do RapidOCR, que é o extra `ocr`, e o `onnxruntime` está nos `excludes` de `packaging/cvoff.spec`. Simulado sem os dois módulos, `leitor_de_linha_padrao()` devolve `None`, e `ler_pagina(modo_bloco=True)` sai **idêntico** ao glifo, em silêncio, com o rodapé dizendo «modo bloco». O bundle em si não foi rodado. Sobra quem instala do código com `--extra ocr`, não tem Tesseract, lê scan e marcou a caixa: para essa pessoa, o caminho agora é instalar o Tesseract.

### Decisão

Sai do caminho da página, num commit só (`66c4a399`): o parâmetro de `ler_pagina` e `linhas_do_glifo`, `leitor_de_linha_padrao`, o `--bloco`, a caixa, o comando, o item do menu, o controle da fita, `texto_declarado`, o campo do índice do caderno e o do estado da janela. O inventário do editor foi regravado.

- **O estado antigo abre:** `ui/state._migrate` descarta a chave. **Sem versão nova**, porque o programa anterior lê o arquivo sem ela, e com a versão subida ele o recusaria.
- **O índice antigo do caderno abre:** `EstadoDaFolha.de_json` só deixa de ler a chave, e a próxima gravação a tira. A folha lida em blocos abre do caderno quando o motor é o mesmo, e a pessoa não perde a leitura sem ter pedido.
- **A frase da folha vazia** dizia «tente outro motor ou o modo bloco». Agora é `strings.FOLHA_SEM_TEXTO_LIDO`, «tente outro motor».

### Critério de aceite

`grep -rln "modo_bloco\|texto_bloco" src tests` acha só `ui/state.py`, a migração; `tests/test_texto_bloco_aposentado.py` faz essa varredura, com conjunto exato, para não ficar vácua, e monta os nomes das chaves para não ser um dos achados. O mesmo arquivo afirma o efeito: o arquivo antigo abre e a chave não volta ao disco, o índice antigo abre e a perde, a aba grava o estado sem ela, o `_ler` da aba chama `ler_pagina` com a assinatura real (`autospec`), e `--bloco` é erro de uso. Numa cópia da árvore de antes da remoção, 10 dos 11 testes falham; o que passa é o que fixa a versão do estado.

### Desvios

- **A frase não estava em `ui/strings.py`**, como o item dizia: estava literal em `qt/painel_de_texto.py`. Foi para lá.
- **O item contava 8 arquivos de teste**: hoje eram 9, com `test_qt_texto_prosa`, que nasceu depois da contagem.
- **`em_bloco` e `GlyphRecognizer(leitor_de_linha=)` ficam**, porque o item aposenta o caminho da página: são a faixa de legenda, medida no `cvoff-texto-linha`. A sonda S-188 do `text_status` procura `em_bloco` e `texto_linha`, os dois seguem lá, e ela fica verde, com um comentário. Nenhum chamador de `src/` passa mais `leitor_de_linha=` ao reconhecedor.
- **A etapa `leitura_de_linha` de `text/custo.py` fica**, zerada: tirá-la muda as onze etapas e a comparação com os relatórios publicados, e o nome dela não diz a opção.
- **`_colapsar_espaco` fica:** nasceu para o espaço dobrado do bloco, e tirá-la poderia mudar uma leitura; a outra trilha também mexe em `leitor.py`.
- O relatório não publica tempo como veredito: três trilhas dividiam a máquina.
- Reproduzir pede o commit medido, e `docs/metrics/texto_prosa_bloco_2026-11-06/medir_bloco.py` diz como: a remoção tirou o parâmetro que ele usa.

## S-729 · O árbitro de notação pela gramática, e o alcance da legalidade ✅ implementada (2026-11-06)

### Problema

Na v3 a notação em letra vem do Tesseract, e ele troca o dígito da casa: 13,8% das casas com forma de lance saem inválidas na prata (`Tfl`, `dS`, `ABR`). A regra de forma da S-721 não tem como julgar `21.` contra `27.`.

### Decisão

`text/arbitro.py`, chamado por `_com_prosa_de_outro_leitor` na folha inteira, depois de `fundir` e antes da marca, só no `motor="fusao"`. Três juízes, do mais barato ao mais caro: a **gramática** (a outra leitura quando ela é lance e esta não, a até duas edições; o dígito forçado da S-743; o número que o glifo partiu, sem duplicar, `1 1 ...♖xh4?` -> `11...♖xh4?`), a **continuidade** do número de lance, e a **legalidade**, quando quem chama passa `ler_pagina(posicao_do_diagrama=)`. Toda troca sai de uma leitura de um dos dois leitores ou de um homóglifo escrito na tabela, e figurina nunca é trocada por letra. `tesseract.lingua_do_processo` lê com `rus+eng` nos livros russos: com `rus` sozinho a notação em letra sai cirílica (`№х45`, `Вхд5`), e com `eng` sai `Nxd5`, `Bxd5`, em 8 folhas do *Пилавов* lidas lado a lado. A troca de homóglifo (`е`, `Ь`, `б`, `З`, `В`, `х`) só vale em token que a gramática chama de lance.

**A legalidade não paga, e a FEN fica de fora da janela.** Ela alcança **29 de 1.060 lances (2,7%) no ouro-dev e 28 de 1.550 (1,8%) na prata**: só a primeira fatia de lances depois de um diagrama tem posição conhecida. E troca **0 lance no ouro e 1 na prata**. Ler a FEN custa o classificador de peças por diagrama. Fica `posicao_do_diagrama`, sem chamador na janela, e o `leitor.posicoes_da_folha`. Quem paga é a gramática: ver abaixo. Continuar da posição inicial nas folhas que têm um `1.` e levar o tabuleiro de uma folha para a outra alcançaria mais, e não foi feito.

**Os dois candidatos a mais que o roadmap cita não entram.** As alternativas do `lstm_choice_mode=2` saem no hOCR (agora há `rodar(formato=)`): trocar um caractere por uma delas resolve 240 palavras inválidas em 27 folhas da prata, **mas só 16 trocam um dígito** (`Ded!` -> `De4!`); as outras trocam a letra de peça (`Hb4` -> `Bb4` ou `Kb4`), que é a figurina, e o glifo já a tem. São 0,6 dígito por folha ao preço de um processo a mais. O top-k do glifo não foi ligado: não há o que oferecer a um juiz que troca um lance em 57 folhas.

### Onde mora

`src/chess_diagram_ocr/text/arbitro.py` (`arbitrar`, `e_estrita`, `forcado`, `Relato`, os interruptores `GRAMATICA`, `CONTINUIDADE`, `LEGALIDADE`), `leitor.py` (`posicoes_da_folha`, `linhas_depois_dos_diagramas`), `fusao.Token.do_leitor`. Scripts em `docs/metrics/texto_prosa_fusao_2026-11-06/`: `legalidade.py`, `alternativas.py`, `digitos.py`.

### Critério de aceite

| | sem o árbitro | com o árbitro | saída |
|---|---:|---:|---|
| ouro-dev, notação, CER | 9,80% | **9,01%**: −0,79 p.p. [−1,30; −0,12] | |
| ouro-dev, prosa | 0,235% | 0,235% | intacta |
| G1(c), ouro-dev: sequências que fecham legais | 12 de 19 (glifo: 12 de 19) | **12 de 19** | não cai ✅ |
| G1(c), prata (ordenação) | 14 de 28 (glifo: 13 de 32) | **14 de 28** | não cai ✅ |
| prata, casas válidas | 86,2% (72 inválidas em 521) | **99,5%** (3 em 542) | os dígitos voltam ✅ |
| prata, notação (ordenação) | | −0,77 p.p. [−1,51; −0,37] | |
| prata admitida, prosa (ordenação) | 3,23% | 3,30%: +0,07 [−0,01; +0,27] | a referência é OCR de terceiro, que também escreve `Tfl` |

`tests/test_text_arbitro.py`. Desligado (`arbitro.GRAMATICA = False`), valem as regras de forma da S-721.

**Desvios.** O alvo do roadmap é "por token de notação, candidatos do glifo e do Tesseract": os dois estão lá, sem o top-k e o hOCR, pelo medido acima. A descritiva inglesa (`R-Q1`) não tem forma própria na gramática, porque nenhuma folha medida a tem. **Sem prata nem ouro em russo**, o `rus+eng` foi conferido à mão. A continuidade não mudou nada no ouro-dev nem na prata; dispara no *Bachmann* e no *Neumann*.

## S-722 · O modelo de página guarda o que a fusão produz ✅ implementada (2026-11-06)

**Problema.** `LinhaLida` tinha uma `procedencia` e uma `confianca` por linha, e a fusão escreve por palavra: nas 27 folhas do
ouro-dev, 78,8% dos caracteres de prosa e notação (20.622 de 26.181) vieram do Tesseract, e todos saíam `glifo`. A faixa de confiança era
por bloco. A correção de uma palavra do Tesseract acusava o classificador (S-762), e a marca da S-761 não tinha onde se apoiar.

**Decisão.**

- **`tesseract` é procedência**, no `Literal`, em `PROCEDENCIAS` e na posição declarada de `ORDEM_DE_CONFIANCA`: `rapidocr`,
  `glifo`, `tesseract`, `camada`, `humano`. Acima do glifo porque é só na prosa que ele escreve, e ali erra 2,7× menos; a notação, a
  fusão não deixa com ele. Linha mista leva a menos confiável: glifo com Tesseract continua `glifo`, e camada com Tesseract vira
  `tesseract`, o que a S-703 precisa ver (`exigir_documento_cego`).
- **`procedencia_em` e `confianca_em`**, por intervalo de caractere, com o desenho de `negrito_em`, e um valor em cada intervalo. Vazio é
  "não há detalhe" e vale o campo da linha; uma origem só não gera intervalo. `confianca_em` é a de **quem escreveu** a palavra.
- **A escrita é uma só.** A S-716 prometia procedência por intervalo em memória, e o que havia era o `so_da_camada`, por linha. Agora
  `_com_prosa_de_outro_leitor`, `_camada_montada` e `_linhas_da_reserva` escrevem os mesmos campos, e o `so_da_camada` é derivado deles.
- **O formato novo só é gravado depois do G102**, atrás de `pagina.GRAVAR_FORMATO_NOVO`, desligada. Desligada, a folha sai como antes:
  `tesseract` escrito `glifo`, sem os intervalos, `esquema` 1 (2 com aviso) e `versao` 1. Ligada, só a folha que pede o formato paga: `esquema`
  3 e `versao` 2, a regra da S-710. A leitura aceita os três. **A constante é do arquivo**: em memória os campos estão sempre inteiros.
- **A aba lê os campos pelas corridas.** `rico.de_pagina` parte a corrida onde muda o leitor, e `Corrida.procedencia` passa a ser por
  palavra. O rodapé diz `Texto: 79% Tesseract, 21% glifo.`, porque o bloco misto conta inteiro como `glifo`.
- **A faixa pode marcar palavra.** `documento.faixas_da_linha`: sem a marca da S-718, `confianca_em` pinta palavra a palavra, com o corte de
  hoje, e a confiança do bloco não pinta nada. Com a marca ligada, só `revisar_em` pinta: o teto de 5% continua valendo, e o sinal cru da
  confiança, que inunda, não entra por cima. É onde a S-761 troca o corte. Na leitura de hoje a marca está ligada: nada muda na tela.
- **A exportação lê os campos**: o `.html` leva a faixa por palavra e `data-procedencia="tesseract"`, o `Relatorio` conta `procedencias`, e o
  `.txt` sai byte a byte igual. A folha sem Tesseract sai como saía.
- **`dado_corrigido.pares_tocados` diz quem errou por palavra.** O motor é o da palavra; a do Tesseract leva `corrigido_de:tesseract@desconhecido`,
  porque `PaginaLida.modelo` é o sha do classificador; a da camada não vira par. Vale para a folha lida; a reaberta do arquivo é `glifo` até o G102.

**Onde mora.** `text/pagina.py`, `text/leitor.py`, `text/rico.py`, `text/documento.py`, `text/arquivo.py`, `text/exportacao.py`,
`text/dado_corrigido.py`, `ui/strings.py`, `qt/painel_de_texto.py`. Testes em `tests/test_text_procedencia_em.py` e `tests/test_qt_texto_prosa.py`.

**Critério de aceite.** Ida e volta de `.cvtxt` e caderno com os campos; arquivo do esquema anterior abre igual; `menos_confiavel` com `tesseract` não
levanta; **texto igual** ao de antes do item nas 27 folhas do ouro-dev, com `motor="fusao"` (`sha` por folha, 0 de 27 diferentes); nenhuma das 27 grava
`tesseract` com a constante desligada.

**Desvios.** `revisar_em` não é gravado no formato novo: é derivado da folha inteira, e o que sobrevive é a faixa da corrida. A confiança da linha continua a do
glifo, até a S-760. A aba não pinta nada novo enquanto a marca da S-718 estiver ligada: a saída "a faixa pode marcar palavra" é a capacidade, e quem a usa é a S-761.

## S-725 · Desempenho, custo de varredura e cache ✅ implementada (2026-11-06)

**Problema.** Quem relê uma folha pagava o Tesseract de novo; o relatório de custo só conhecia o glifo (`texto_custo_20260826.json`, fator 2,21×), e dividia
as horas por um acervo de 12.000 folhas, a extrapolação da S-61, quando a pasta tem 26.730.

**Decisão.**

- **O um processo por folha já existia.** `tesseract.ler_linhas` é um processo, com o TIFF de várias páginas pelo stdin e `psm 7`, desde a S-720. Faltava a reserva
  que o item pede: `tesseract.LOTE_POR_FOLHA`, ligada; desligada, um processo por linha. É ela que mede o lote.
- **Cache em `data/cache_texto/`**, em `text/cache_texto.py`. Uma entrada por lote, porque por linha seriam ~40 arquivos por folha e um milhão no acervo. A chave leva o sha dos
  recortes na ordem, a versão do executor, a assinatura do pré-processamento (margem, escala, alvo, `rus+eng`: virar uma dessas constantes invalida sem ninguém lembrar de subir
  versão), a versão do Tesseract, o sha do `traineddata` de **cada** língua do processo, a língua, o `psm`, o `dpi`, as opções e o `modelo`. O `modelo` é o da S-752, passado por
  `LeitorTesseract(modelo=)`; no Tesseract quem faz esse papel é o `traineddata`, e ele sai vazio. O classificador de glifo não entra: o que ele muda é o recorte.
- **Teto de 200 MB, com despejo do usado há mais tempo**, pelo `mtime`, que a leitura atualiza. Despeja até 90%, para não varrer a pasta a cada gravação. Uma entrada ocupa 5,5 KB em média
  (7,9 KB no máximo), e o teto cabe o acervo inteiro.
- **Disco cheio vira aviso, e a leitura segue.** `gravar` nunca levanta: devolve a frase, e a folha ganha `CACHE_NAO_GRAVADO`. Esse aviso é da sessão, e **não vai ao arquivo**
  (`pagina.AVISOS_DA_SESSAO`): uma folha inteira não passa a dizer para sempre que o disco esteve cheio. Entrada ilegível é falta, e sai da pasta.
- **Só a janela liga.** `LeitorTesseract()` e `leitor_padrao()` nascem sem cache, e é o que a régua, a bancada e os CLIs recebem. Quem pede é `qt/painel_de_texto._ler`, a mesma
  regra da reserva da S-715, e um teste varre o pacote atrás de quem cita o módulo.
- **Limpeza** por «Limpar o cache de leitura», no menu Texto e na aba Revisão da fita, numa `Tarefa`: sem pergunta, porque apagar é sempre seguro. As folhas do caderno não mudam.
- **`cvoff-texto-custo --motor fusao`**, com a reserva, como a janela, e sem cache. O padrão continua `glifo` (S-727). Ganha `--limite-segundos`, `--ressalva` e as etapas `leitor_de_linha` e `fusao`.
- **`custo.PAGINAS_DO_ACERVO` = 26.730**, contadas em 58 PDFs, com as duplicatas, que uma varredura da pasta paga (1.544 folhas; sem elas, 25.186).

**O medido.** Em `docs/metrics/texto_cache_20261106.json`, sobre o `080d56e5`, com a árvore limpa: nas 27 folhas do ouro-dev (5 livros, 758 linhas), **0 folhas diferentes** do lote em
texto da página, em linhas do leitor com as confianças e em avisos, para a leitura por linha, o cache frio e o cache quente. Custo em `docs/metrics/texto_custo_fusao_20261106.json` e
`docs/metrics/texto_custo_glifo_20261106.json`, nas mesmas 18 folhas de 6 livros:

| motor | s/folha | o texto soma | fator | política | horas no acervo |
|---|---:|---:|---:|---|---:|
| `glifo` | 1,09 | 0,60 | 1,84× | sob demanda | 9,8 |
| `fusao` | 2,63 | 1,95 | 3,09× | sob demanda | 21,4 |

O leitor de linha é 0,75 s por folha, e a fusão, 0,013 s. **A fusão não muda de faixa**: continua abaixo dos 4× que a tiram da varredura. Quem decide é a D4.

**Ressalva, e ela vale para todo número de tempo acima.** Foram medidos com outras duas corridas na máquina e `OMP_NUM_THREADS=3`: entre duas corridas seguidas, o lado `hoje` foi de 0,72 a 0,93 s.
**Nenhum deles julga o G4**, que se mede depois, com a máquina parada, na janela e com o cache desligado. Servem de ordem de grandeza para a D4. Na mesma ressalva: 2,6 s por folha no lote, 7,8 s
por linha e 1,6 s com o cache quente, em que a diferença para o lote é só o processo do Tesseract: o glifo continua rodando, porque é dele que saem os recortes.

**Onde mora.** `text/cache_texto.py`, `text/tesseract.py`, `text/leitor_de_linha.py`, `text/custo.py`, `cli/texto_custo.py`, `qt/painel_de_texto.py`, `ui/comandos.py`, `ui/menu.py`, `ui/fita_do_texto.py`,
`ui/texto_declarado.py`, `ui/busy.py`. A medição em `docs/metrics/texto_cache_2026-11-06/medir.py`. Testes em `tests/test_text_cache_de_leitura.py` e `tests/test_qt_texto_prosa.py`.

**Critério de aceite.** Diferença zero acima; trocar `tessdata`, língua, `psm`, versão ou modelo invalida a entrada; o teto é cumprido e sai quem foi usado há mais tempo; a segunda leitura na aba não abre
processo; `data/cache_texto/` no `.gitignore` e na tabela de persistência; a régua sempre sem cache.

**Desvios.** A verificação pedia as 26 folhas do `rodar.py` de 2026-10-30, e foi feita nas 27 do ouro-dev de hoje. O G4 **não foi julgado**: é a parte da saída que espera a máquina parada. A folha inteira da
reserva (`psm 3`) não passa pelo cache: não é lida em nenhuma das 90 folhas legíveis, e a `Leitura` dela não tem por onde devolver o aviso. A entrada guarda texto e confiança, sem as caixas por palavra: nenhum
consumidor as lê neste caminho.

## Fase 103 — O glifo sem as cegueiras do 32×32

Toda a fase é regra de decisão, geometria e léxico, sem retreino, e cada conserto tem a sua constante. Contra o que se mediu: **os 5
livros aprovados na auditoria da S-702**, 27 folhas. O *Chess Evolution* e o *Capablanca*, que as Saídas do roadmap citam, foram
reprovados nela, e ficam à parte no relatório, como conferência. O **Hertan é do ouro-dev**, e está nas contas. O relatório é
[metrics/texto_prosa_glifo_2026-11-06.json](metrics/texto_prosa_glifo_2026-11-06.json), medido em `6b99f95e`, e `hoje` é tudo
desligado, que dá texto idêntico ao de `a2937260` nas 27 folhas. O IC depende da ordem dos livros, e ela é fixa: Dvoretsky, Hertan, *Minhas 60*,
400 Quebra-cabeças, Seirawan. Tudo aqui é dev contaminado: o portão G103 abre o teste, e é rodado
depois. Reproduzir: `texto_prosa_glifo_2026-11-06/medir_glifo.py`.

| CER de prosa, `tip` | antes | depois |
|---|---:|---:|
| ouro-dev, 27 folhas | 2,85% [0,77; 4,85] | **0,99%** [0,29; 1,97] |
| WER de prosa | 11,7% | **3,55%** |
| Hertan | 4,12% | 0,95% |
| *Minhas 60* | 6,52% | 2,84% |
| Dvoretsky | 1,89% | 0,37% |
| 400 Quebra-cabeças | 0,45% | 0,27% |
| Seirawan | 0,39% | 0,35% |

Diferença pareada na prosa: **−1,86 p.p. [−3,07; −0,43]**, 22 folhas melhores e nenhuma pior. **Notação, a G1(b):** −0,17 p.p.
[−0,62; 0,00], 3 folhas melhores e nenhuma pior. **Figurina, a G2:** revocação 85,2% → 85,9%, precisão 85,8% → 85,9%. Na prata, que só
ordena e é o caminho de reserva: prosa −0,81 p.p. [−1,22; −0,49], **29 folhas melhores e 1 pior** (*Kemeri* 226, por 1 caractere em 1.163, numa folha de
45% de erro), notação −1,50 p.p. [−2,95; −0,54] com nenhuma pior, figurina: revocação 60,2% → 69,6%, precisão 75,1% → 78,4%.

**A primeira versão foi reprovada pelo crítico**, e o que ele achou está nos itens: a regra de caixa trocava certo por errado fora do dev
(`ChessCafe`, `McClure`, `GMs`, `Nxa2`), e as guardas tinham vão. Os casos dele, relidos: `ChessCafe` (Hertan, folha 4), `McClure` (Yusupov, folha 961) e
`GMs` (*Chess Evolution 2014*, folhas 234, 243 e 422) saem como na camada, e no Aagaard, folhas 64 e 234, nenhuma captura sai com `X`. Na segunda
rodada: `[C42]`, `[C18]` e `[C84]` (*Chess Evolution 2014*, folhas 767, 71, 100 e 122) saem como na camada, e agora melhor que `hoje`, que dá `[c42]`.

**Os testes de decisão da S-764** moram em `tests/test_text_traco_vertical.py`, `test_text_caixa_coerente.py`, `test_text_fronteira.py`,
`test_text_ligadura.py`, `test_text_aspas.py` e `test_text_acento.py`, com o desenho comum em `tests/glifo_sintetico.py`: caixas
sintéticas, sem modelo nem livro, e rodam no CI. Cada família tem o caso que reproduz o defeito com a constante desligada.

`tests/test_text_fiacao_do_glifo.py` é a outra camada: uma folha desenhada, a segmentação de verdade e um classificador falso que responde pelo
tamanho do recorte, lidos por `linhas_do_glifo`. **Neutralizar cada uma das 9 chamadas acusa**, rodando **só** este arquivo: é assim que a conta vale.
A primeira versão desta frase rodava os testes de decisão junto, e o patch no módulo os derrubava, então a conta era vácua: `coerente`, a regra reprovada,
passava sem acusar neste arquivo. Agora um versalete, um `KC5` e a forma minúscula do léxico a prendem.

**Conferido revertendo, e o que isso vale.** 263 mutantes sistemáticos das constantes desta fase (cada interruptor; cada limiar a 0, metade, 1,5×, 3× e
negativo; cada lista vazia e sem cada elemento), com controle verde no mesmo processo: **os 263 acusam**. É só esse conjunto: mutante de lógica, de
condição ou de `<` por `<=` não está nele, e ele não é o conjunto de 86 de limiar e lista do crítico, em que a primeira versão perdia 36. Ele
tem de ser rodado de novo. As listas são iteradas por literal no teste: iterar a própria constante deixava a guarda vácua, e os mutantes mostraram.
`CORTE_ACENTUADA` a 1,5, que o crítico achou vivo, agora acusa. **A ±10% de cada limiar, 24 de 34 sobrevivem, e é o esperado**: o limiar fica no meio do vão
medido, e nenhum caso sintético o prende tão perto. Quem o segura ali é a medição das folhas, e não o CI.

## S-730 · Traço vertical contra ponto ✅ implementada (2026-11-06)

### Problema

124 das 437 palavras erradas do glifo, 121 delas no Hertan (Arial): `will`→`wi..`, `I`→`.`. **A classe certa não está sempre em rank 2**:
dos 149 `l` lidos como `.`, ela está em rank 2 em 62 e em rank 6 em 87, atrás de quatro traços; os 13 `I` estão em rank 5. E a ordem entre
`l`, `I` e `1` não quer dizer nada: depois do resize, são a mesma mancha.

| caixa | n | altura / altura-de-x | largura / altura |
|---|---:|---:|---:|
| `l` lido `.` | 149 | 1,03 a 1,32 | 0,12 |
| `I` lido `.` | 13 | 1,03 a 1,32 | 0,12 a 0,19 |
| `.` certo | 1.095 | 0,15 a 0,28 | 0,80 a 1,25 |

### Solução

`text/traco_vertical.py`, depois de `traco` e antes de `marca_fina`. Caixa acima de `ALTURA_MINIMA` (0,85) e abaixo de `PROPORCAO_MAXIMA`
(0,35) não é `.`, `,`, `'`, `-` nem `—`: é traço, e **o contexto escolhe a letra**, não o modelo. Sozinho ou diante de apóstrofo é `I`; entre
maiúsculas, `I`; junto de dígito ou no fim de um lance (`Rf.`), `1`; no começo, o léxico e `palavras_curtas` separam `look` de `In`; onde
só o `i` faz palavra, `i` (`fixed`, em scan, sem o pingo); no resto, `l`.

**A regra irmã, da vírgula.** Em *Minhas 60* (Calibri), a vírgula é uma barra inclinada, e o modelo responde `/` a 0,999, com `,` fora das
oito primeiras: `entanto,`→`entantol`, porque depois o `italico` troca `/` por `l`. Altura de 0,48 a 0,53 e mais da metade abaixo da linha
de base é vírgula, e nem `/` nem `l` têm essa caixa. É a única decisão da fase que aceita uma classe que o modelo não pôs no topo.

Reversão: `traco_vertical.LIGADO`.

### Critério de aceite

`tests/test_text_traco_vertical.py`. Família, só com este item ligado: **124 → 0**, e Hertan **121 → 0** (o roadmap pedia ≤ 1/4); em nenhum
livro sobe. CER de prosa 2,85% → 2,09%, 12 folhas melhores e nenhuma pior. Notação −0,06 p.p. [−0,25; 0,00], nenhuma folha pior.
No *Chess Evolution*, reprovado, a família vai de 43 a 0.

### O que ela não entrega

`l` contra `1` em caixa que o modelo **já leu** como `l` ou `1` continua com o dicionário (S-508). `Short-SpeeIman` sobra: `I` lido entre
minúsculas não é marca.

## S-731 · Caixa coerente na palavra ✅ implementada (2026-11-06)

### Problema

59 palavras, e **o modelo acertava em quase todas**: nos 71 `W`, `S`, `U`, `O` e `C` lidos em minúscula, a classe certa estava em rank 1 em
70. Era a régua da S-211 que os derrubava: a mediana das alturas só é a altura-de-x em linha de prosa. Em linha com lance ela é a altura de
maiúscula (`White`→`white`), e na linha toda em maiúscula também (`DEFEsA`).

### Solução

Três mudanças em `text/caixa_alta.py`:

- **`x_height_da_linha`** (`XH_COERENTE`): a altura-de-x vem de `LETRAS_DE_X` (`aemnr`, sem haste, sem acento e com maiúscula de outro
  desenho). Sem duas delas, das altas seguras divididas por `RAZAO_ALTA_X` (1,40); sem altas, da escala da folha (`W` e `W?` sozinhos na
  linha). O corte de 1,25 não muda, e passa a estar no meio do vão:

| medida contra as letras de x | n | p1 | mediana | p99 |
|---|---:|---:|---:|---:|
| minúscula ambígua certa | 4.992 | 0,94 | 1,00 | 1,06 |
| maiúscula ambígua certa | 139 | 1,32 | 1,50 | 1,58 |

- **`coerente`** (`PALAVRA_COERENTE`): palavra só de letras, com duas ou mais maiúsculas de desenho próprio e nenhuma minúscula, sobe as
  ambíguas, o `p` e o `l`. É o que resolve o **versalete** (`'UNUSUAL SQUARES'`, com altura de letra de x), que altura nenhuma separa. Lance
  fica de fora pelo dígito, e `KxR` porque o `x` só sobe a partir de quatro letras. O `s` final de até 4 letras não sobe (`GMs`). Na outra
  direção, a ambígua depois de minúscula desce (`IvanchUk`), salvo em palavra que começa em maiúscula, seguida de 2 minúsculas e cuja forma
  minúscula não existe no léxico sem nomes (`ChessCafe`, `SacrifiCio`→`Sacrificio`), ou depois de `Mc`/`Mac`. Em palavra que começa em minúscula, nunca
  (`soViéticos`, `deCido`): na prata, a ambígua no meio da palavra vai de 20 a 8.
- **O lance que a régua estragou** (também `PALAVRA_COERENTE`): em scan, com as letras de x comidas, `Qxf7` saía `QXf7`, `Nxa2` saía `NXa2`, e a
  coluna `c` saía `C`: `Kc5`→`KC5`, `c2`→`C2`. O `X` diante de casa e o `C` diante de dígito de casa descem, e `Cc3`, a descritiva `C3A`, o rótulo `C3)` e
  o código ECO `C42` ficam. E `c` com dois dígitos sobe (`[c18]`→`[C18]`), porque não é casa nenhuma. Na prata, a coluna maiúscula diante de dígito vai de 5
  a 0, e a captura com `X`, de 3 a 0, contados no texto de saída.
- **`P` pela descida** (`P_PELA_DESCIDA`): `P` era lido `p` em *Minhas 60*, em rank 2 nos 11 casos. Esticados, são o mesmo desenho, e o `p`
  desce, enquanto o `P` não.

### Critério de aceite

`tests/test_text_caixa_coerente.py`. Só com este item: família **59 → 1**, com `já`→`Já` de sobra (o roadmap pedia ≤ 1/3); nenhum `DEFEsA`.
Acento+caixa 13 → 0. CER de prosa 2,85% → 2,50%, 19 folhas melhores e nenhuma pior. Notação −0,11 p.p. [−0,55; 0,00], e é daqui o ganho de
figurina: `Cd6`→`cd6` em linha com lance não acontece mais. No *Capablanca*, reprovado, 7 → 3, e no *Chess Evolution*, 19 → 0.

### O que ela não entrega

Linha só de ambíguas sem escala continua na mediana. Em scan, `will` pode sair `Will` e `winning`, `Winning`, onde as letras de x estão comidas:
visto na prata, com poucos casos, e a prata melhora em todas as folhas mesmo assim. `MIN_LETRAS_DE_X` 3 no lugar de 2 foi medido e não muda nada
que decida. A exceção `Mc`/`Mac` é lista: nome com maiúscula no meio e uma letra depois dela (`DeJr`) cai na regra.

## S-732 · Fronteira de palavra ✅ implementada (2026-11-06)

### Problema

38 palavras coladas, 22 no Dvoretsky: `of the`→`ofthe`. O `bbox` do `f` inclui o gancho, e `texto_da_linha` só vê o vão entre os `bbox`. O
vão da faixa de baixo separa melhor, mas não basta, porque `r|a`, `q|u` e `v|e` também têm o vão embaixo:

| vão de baixo, em alturas-de-x | p5 | mediana | p95 |
|---|---:|---:|---:|
| com espaço, já detectado | 0,48 | 0,72 | 1,24 |
| espaço que faltou | 0,20 | 0,54 | 1,01 |
| sem espaço | 0,05 | 0,16 | 0,33 |

E o léxico sozinho já perdeu: `lexico.PARTIR_COLADAS` registra 0 certas contra 5 erradas, com `carrying`→`carr ying`.

### Solução

`text/fronteira.py` e `colados.por_lexico`, com o léxico por árbitro nos dois:

- **partir** (`fronteira.LIGADO`): o vão de baixo propõe, a partir de 0,30, e fora do `f` exige também o vão de cima de 0,15; o léxico **sem
  nomes** e `palavras_curtas` dispõem, os dois pedaços têm de existir, e nome só vale de pedaço a partir de 6 letras. O pedaço da direita
  tem 3 letras ou mais, salvo depois do `f`: `transferem` e `romperam` não estão no léxico, e `transfer` + `em` estão. Ambiguidade não
  corrige. `of2.` parte por uma lista fechada, sem `e`, e `Be2.` e `e7.` ficam. O espaço entra na frente do caractere, e a confiança por letra
  continua casando.
- **juntar** (`JUNTAR_PARTIDAS`): `ga n ha ndo`→`ganhando`, quando a junção existe e algum token dela não. Token de 3 letras conta como
  existente, senão `cut off` vira `cutoff`.
- **o colado** (`colados.POR_LEXICO`): em palavra que não existe e sem peso de notação, a caixa larga é recortada no vale e os dois pedaços
  são relidos; se **uma só** leitura dos dois melhores de cada pedaço fizer palavra, fica, como dois caracteres numa caixa. É a medição de
  `GANHO_MINIMO` trocada por léxico: `tums`→`turns`, `acmal`→`actual`, `Ffxcher`→`Fischer`, `cof7ect`→`correct`. `w` e `v` não entram, os
  pedaços têm de ser letras, maiúscula só na primeira posição, palavra de 3 letras não é examinada (`bom`→`born` foi a primeira rodada),
  resposta com menos de 7 letras tem de estar no léxico sem nomes (`bem`→`Beni`), e dígito só é perdoado na caixa relida: `cof7ect` tem a
  classe `f7` numa caixa larga, e fora dela o dígito é tinta do livro.

`text/palavras_curtas.py` é a lista fechada, à mão, de palavra funcional de menos de 4 letras, que `lexico.MIN_TAMANHO` tira de propósito.

### Critério de aceite

`tests/test_text_fronteira.py`. Só com este item: fronteira **38 → 9** (o roadmap pedia ≤ 1/3), espaço 23 → 15, letra trocada 128 → 102, e
**as inserções caem**: 562 → 550. CER de prosa 2,85% → 2,53%, 13 folhas melhores e nenhuma pior. Notação igual.

### O que ela não entrega

`Reshevsky joga`, `de folga` e `se perdem` saem, e 9 sobram: `3 d4` em *Minhas 60*, que é notação, sem letra que o léxico arbitre, e colagens
sem vão embaixo. `comer` no lugar de `corner` é palavra que existe, e fica. `pamda`→`partida` precisa de dois cortes numa caixa, e fica.
O veto do corte da S-186 (`paM(ns`) não foi trocado, porque não aparece mais nestas folhas.

**Em scan, o léxico erra para o lado de cá:** `invulnerable`→`in vulnerable` e `erschien`→`er schien` partem, porque a palavra inteira não está
no léxico e os dois pedaços estão, e `cleanly`→`clearly` é um corte de colado que achou outra palavra que existe. Visto na prata, em poucos casos.
Nenhum desses é veto do léxico: palavra certa fora da lista continua exposta.

## S-733 · Ligadura sem o `1` a mais ✅ implementada (2026-11-06)

### Problema

14 palavras, 13 no Dvoretsky: `first`→`fi1rst`. No Times dele o `fi` tem duas caixas: o gancho com o pingo, que o modelo lê `fi`, e a haste,
lida `1` a 0,99, a 1 a 3 px. `flee`→`f1ee` é a classe `f1`, de lance.

### Solução

`text/ligadura.py`, depois do dicionário, que pula palavra com ligadura de qualquer jeito. A haste se funde à ligadura (`FOLGA` de meia haste),
e **funde a caixa**, para o vão seguinte não medir de um lugar que não está no texto. `f1` seguido de duas minúsculas vira `fl`, o que
lance nenhum faz. A haste é só `1` e `|`: `h-file` saía `h-fie` numa versão que aceitava `l`, e foi a prata que mostrou. Reversão:
`ligadura.LIGADO`.

### Critério de aceite

`tests/test_text_ligadura.py`. **Família 14 → 0**, nenhum `fi1` nem `f1` em palavra do ouro-dev, conferido no texto de saída. Notação igual.

## S-734 · Aspas duplas e apóstrofo ✅ implementada (2026-11-06)

### Problema

8 palavras no Dvoretsky e 13 + 4 caixas no ouro-dev: `"tail`→`'(tail`, `rook"`→`rook''`. As duas caixas de uma aspa dupla chegam separadas, a
2 a 4 px, e o modelo responde caixa a caixa; `"` tem 89 amostras contra 5.676 de `(`, e a classe certa está fora das oito primeiras.

### Solução

`marca_fina.aspas`, depois do dicionário: dois riscos no alto da linha, com vão de até uma largura, viram `"` numa caixa só; um `(` pequeno
no alto vira `'`. Reversão: `marca_fina.ASPAS_PELA_GEOMETRIA`.

### Critério de aceite

`tests/test_text_aspas.py`. Em `tip`: aspas duplas **8 → 0 no Dvoretsky**, pontuação 10 → 4. No *Capablanca*, reprovado: 7 → 3.

### Desvio: a Saída de pontuação, em `cru`, não se cumpre

O roadmap pede a pontuação em `cru` ≤ 1/2. **Ela sobe de 50 para 58**, e não por erro novo: são palavras que tinham outro erro e agora só têm
este. Das 58, 37 são do Hertan, e quase todas são `’` lido `'`: **o modelo não tem as aspas curvas**, e `cru` conta a diferença.

Simulando por fora do leitor, com aspas e apóstrofos curvados pelo contexto, a família vai a **12**, e nenhum dos 5 livros piora, porque o texto do
glifo não traz aspa reta onde a camada a tem. **Não entra**, e é decisão: `lexico.PONTUACAO_DE_BORDA` e as classes de token não aparam a curva, então `“tail` passaria a
ser palavra desconhecida para quem marca "revisar", e é uma mudança fora dos arquivos desta trilha. As metas valem em `tip`. Fica para quem
abrir a régua da marca.

## S-735 · Acento e segundo corte de caixa ✅ implementada (2026-11-06)

### Problema

15 + 13 palavras, 25 delas em *Minhas 60*: `não`→`näo`, `posição`→`posiCäo`. Três causas, e duas têm a classe certa à mão:

| troca | n | rank da certa | amostras em `training_data/` |
|---|---:|---:|---|
| `ã` lido `ä` | 23 | 2 | `ã` 3.797, **`ä` 15** |
| `ç` lido `C` | 19 | 1 ou 2 | `ç` 93, `C` 537 |
| `ê` lido `é` | 4 | 3 | `ê` 347, `é` 1.751 |

**A classe que vence é a que o modelo quase não viu**, e nenhum número daqui fala do modelo. Acima do piso de ~50 só `ã`, `ç`, `ê`, `é`, `ó`,
`õ`, `ú`, `Í`, `á`, `à`, `â`, `ć` e `č`; abaixo dele, `í` 32, `ö` 3, `Ö` 5, `Ó` 3, `Õ` 1, `Ú` 1, `Ć` 3, `Č` 3, `š` 7, `Š` 9, `ž` 2, `Ž` 1, `Ã` 1.

### Solução

- **`text/acento.py`** (`acento.LIGADO`): trocar um acento por outro, entre os três primeiros do modelo, se só a resposta existir. `corrigir` do
  dicionário não alcança isso, e está certo: `sem_troca_de_caixa` tira a mesma letra com outro acento porque `façanha` virava `facanha`, e
  `MIN_TAMANHO` tira `não`. Aqui nunca se tira nem se põe tinta. A única troca sem léxico é `äo` no fim da palavra ou antes de hífen, que
  nenhuma língua do acervo escreve.
- **A cedilha pela descida** (`caixa_alta.CEDILHA_PELA_DESCIDA`): `c` ou `C` com a caixa 0,25 altura-de-x abaixo da base, com `ç` entre as
  opções, é `ç`. `ç` desce de 0,38 a 0,50, e `C` e `c` vão até 0,06.
- **O segundo corte** (`caixa_alta.SEGUNDO_CORTE`, `CORTE_ACENTUADA` 1,65): `í ó õ ö ú ć č š ž` têm corte próprio. A minúscula acentuada mede
  **de 1,33 a 1,53** das letras de x (53 casos, 5 livros do dev), o que a memória `caixa-alta-nao-cobre-acentuada` dava como 1,46 pela mediana da linha. A
  maiúscula, cerca de 1,85: **esse lado é estimado**, porque nenhuma aparece no dev. A 1,5, o corte quebra: `após`→`apÓs`, `última`→`Última` em *Minhas 60*.

### Critério de aceite

`tests/test_text_acento.py`. Em *Minhas 60*: acento + acento+caixa **25 → 2** (o roadmap pedia ≤ 1/3). No todo, 28 → 6. **Nenhum `Õ` nem `Ó`
inventado**, conferido no texto de saída. Notação igual. Só com `acento.LIGADO`, o segundo corte e a cedilha: CER de prosa 2,85% → 2,68%, 6 folhas
melhores e nenhuma pior.

### O que ela não entrega

`importância`→`importancia` e `à`→`a` são tinta que se perdeu, e não acento trocado: a classe nem está nos três primeiros. **O segundo corte não
mudou nenhum caractere nestas 27 folhas**: não há maiúscula acentuada inventada para desfazer, e o que existe é a guarda, com o teste.

## S-736 · ADR: a geometria como entrada do classificador ✅ implementada (2026-11-06)

### Contexto

O classificador recebe o recorte esticado para 32×32, e toda a Fase 103 existe porque a altura relativa, a linha de base e a proporção se perdem
nesse caminho. A saída estrutural seria recortar de novo e dar as três como entrada da rede.

**Recortes esticados**, amostra de até 600 por classe de `training_data/` (607.719 recortes, 314 classes); uniforme em 3.000: 56,8%:

| classe | recortes | esticados | classe | recortes | esticados |
|---|---:|---:|---|---:|---:|
| `l` | 2.573 | 97,5% | `,` | 521 | 100% |
| `I` | 786 | 100% | `'` | 95 | 100% |
| `\|` | 2 | 100% | `"` | 89 | 19% |
| `1` | 26.757 | 72% | `s` / `S` | 4.511 / 432 | 100% / 100% |
| `.` | 20.434 | 69% | `c` / `C` | 12.755 / 537 | 96% / 46% |
| `i` | 18.903 | 66% | `ã` / `ä` | 3.797 / 15 | 2% / 53% |
| `!` | 13.788 | 21% | `ç` | 93 | 68% |

**O custo de recortar de novo**, medido em 10 folhas dos 5 livros dev, com outras duas medições na máquina (ordem de grandeza): 1,2 s por folha
e 1.113 caixas por folha, para render, camada, segmentação e recorte; são 3.710 folhas nesses livros, cerca de **1,2 h de CPU**, e 4 milhões de
caixas antes de deduplicar, rótulo pela camada. Isso é o barato. O caro é o que vem junto:

1. **Nenhum dos 607.719 recortes sabe de onde veio** (`text/procedencia.py`: UUID puro, sem sidecar). Recortar de novo não é migrar a base, é
   trocá-la: o que veio de scan, a figurina e as ligaduras saem junto, e só os livros digitais voltam;
2. os livros digitais admitidos são os do dev e os de reserva treináveis (30), com a lista de exclusão da S-750 valendo, então o conjunto novo é
   mais estreito em fonte do que o de hoje;
3. rede nova, `char_meta` novo e ONNX novo, com treino de cerca de 10 min por época na RTX 5060;
4. trocar o modelo é S-218: os quatro relatórios de campo remedidos, e o modelo da notação do diagrama no caminho.

### Decisão

**Não fazer na Fase 105.** A Fase 103 tirou as famílias de geometria sem tocar no modelo: traço-ponto 124 → 0, caixa 59 → 1, acento+caixa 13 → 0.
O que sobra das 437 palavras são 116, e 79 são `letra trocada`, que é sobretudo segmentação em *Minhas 60*, e nenhuma entrada de geometria a
resolve. E a própria Fase 105 é sobre leitor de linha, que olha a linha inteira e não tem o problema do recorte apertado.

**O que muda a decisão:** o glifo sozinho não fechar o G103 por causa das famílias de geometria no teste, ou um livro novo com a família
traço-ponto de volta. Aí a reabertura é outra ADR, e começa pela procedência (S-201), sem a qual nada se migra.

### Consequências

As regras de geometria continuam morando fora da rede, cada uma com a sua constante e o seu teste. A primeira leitura delas num livro novo é o
G103. Se a base for um dia recortada de novo, as classes mais vazias que esta fase registrou (seção da S-735) são a primeira coisa a pedir.

## S-744 · O texto espaçado volta a ser palavra ✅ implementada (2026-11-06)

### Problema

O *Gutmayer* enfatiza espaçando as letras, e o vão passa do `linhas.VAO_DE_ESPACO`. **Quem sofre é o glifo, e não o Tesseract**: nas folhas
medidas o Tesseract lê a palavra inteira, e o glifo, que é o padrão, sai `k o m b i n i e r t e`, `F i gu re n`. O roadmap citava `f a t a l e n`, mas
a forma flexionada `fatalen` não está na lista alemã: fica como está, porque o critério é o léxico.

### Solução

`text/espacado.py`, com a reversão em `JUNTAR_ESPACADO`, chamado por `leitor._sem_espacado` depois dos dois motores (glifo e fusão), com
`dicionario` ligado. A camada não passa por ali: é a referência. A língua é a do livro (S-723), com `lexico.da_lingua` e `do_livro` (S-728) e as
curtas da língua; sem lista, nada acontece.

Corrida é a sequência de ao menos 3 tokens de uma ou duas letras, com metade de uma letra só. A maiúscula abre trecho, salvo na corrida toda em
maiúsculas. Cada trecho vira **uma** palavra, ou **várias** se há uma única cobertura inteira de menos pedaços (`d e r B a u e r` → `der Bauer`), ou fica
como estava. O nome da lista do livro só vale com maiúscula e trecho todo de uma letra. Só tira espaço: a contagem de `confiancas` sobrevive, e
`revisar_em` é remapeado.

**A primeira versão reconhecia a palavra no meio da corrida, e foi recusada pela auditoria**: `d e sHan d e`, `a. nOhn`, `gein e s`. Sobre o glifo a
corrida vem com erro, e 396 mil palavras e nomes acham alguma coisa em quase toda sequência. Agora, sobrou letra, o trecho fica.

### Critério de aceite

`tests/test_text_espacado.py`, sintético e sem livro, com a decisão inteira, e a fiação por `_sem_espacado`. Nas folhas do *Gutmayer*, motor `glifo`,
língua `deu`, contando as corridas de ao menos 3 letras soltas cuja junção a lista conhece:

| | antes | depois |
|---|---:|---:|
| 12 folhas olhadas para escrever a régua | 14 | 2 |
| 10 folhas **não vistas** | 7 | 3 |
| junções de palavras distintas, à vista, nas 22 folhas (50 junções) | | **0** |
| linhas mudadas no ouro-dev, limpo (882) e no perfil médio (898), com `eng` e `por` | | **0** |

**A saída não se cumpre inteira.** Zero palavra distinta juntada, sim. Zero palavra conhecida espaçada, não: sobram 5, porque a corrida tem letra a mais ou é pedaço de
palavra maior (`F i g u`), e é a regra acima, que escolheu não juntar na dúvida.

**Em cerca de um terço das junções (16 de 50) sai só um pedaço**, e não a palavra: `rung`, `mann`, `Laske`, porque o resto dela veio com erro (`S p i e1 m a n n` → `S p i e1 mann`). As letras
são as mesmas e nenhuma palavra de fora entra, mas o pedaço existe na lista por acaso.

### O que ela não entrega

- **Palavra com letra errada** fica: `1 e b e n d i g`. O léxico não a conhece, e aproximar é a decisão recusada da S-209.
- **Duas letras** (`z u`, `i n`) ficam: `a o` e `e a` são prosa. `der`, `und` e as outras curtas da língua entram.
- **Forma flexionada fora da lista** fica: `f a t a l e n`. A lista alemã tem 52.854 palavras, e o caderno do livro (`lexico.txt`) ainda não é consultado aqui.
- O **Tesseract** não muda, porque já lia a palavra inteira: aqui a régua quase não dispara. A camada de terceiro do *Gutmayer*, com 737 corridas, continua como é.

## S-745 · A escada de linhas de base: o degrau 0 e a tabela ✅ implementada (2026-11-06)

**Problema.** A S-755 tem de comparar o leitor da casa contra **o melhor** leitor que não exige modelo da casa, e ninguém tinha dito qual é. Do degrau 0, a S-721 já recusara `--user-words`,
`load_system_dawg=0` e a altura-x; faltavam os n-gramas de caractere desempatando as alternativas de `lstm_choice_mode=2`. Os degraus 1, 2 e 3 dependem de downloads.

**Decisão. O melhor degrau é a fusão de hoje**, `motor="fusao"` com Tesseract 5.5 e `tessdata` fast, sem nenhum ajuste do degrau 0: 0,235% [0,040%; 0,627%] de prosa no ouro-dev. No scan-ouro **não há número**. Nada muda no produto: os
n-gramas moram só em `docs/metrics/texto_escada_2026-11-06/ngramas.py`.

| degrau | o quê | estado | ouro-dev, Δ prosa pareado | prata (ordenação) | scan-ouro-dev |
|---|---|---|---|---|---|
| 0a | `--user-words` com os nomes | recusado pela S-721, não remedido | 0 [0; 0] | não fecha: o `spa` termina com erro | sem número |
| 0b | `load_system_dawg=0` na notação | recusado pela S-721, não remedido | 0 [0; 0] | 0 [0; 0] | sem número |
| 0c | escala pela altura-x | recusado pela S-721, não remedido | +0,004 [−0,029; +0,048] | −0,154 [−0,509; +0,066] | sem número |
| 0d | n-gramas, margem de 1 nat | **medido aqui, e recusado** | +0,042 [−0,008; +0,113] | +0,084 [−0,046; +0,174] | sem número |
| 1 | `tessdata_best` (S-741) | **pulado por recuo** (D2) | | | |
| 2 | ajuste fino do Tesseract (S-746) | **pulado por recuo** (D2, D7) | | | |
| 3 | PP-OCR latino em ONNX | **pulado por recuo** (D7) | | | |

**A medição dos n-gramas.** Trigramas de caractere por língua, contados nos tipos de `lexico.da_lingua`. Só palavra de letras, de 3 letras ou mais, fora do léxico, troca pela alternativa de confiança ≥ 5%, até duas posições, cujo trigrama ganha pela margem.
Mesmas caixas do glifo e mesmo placar, pela porta `registrar_motor` da bancada, nas 27 folhas do ouro-dev e nas 30 da prata. O par é contra a primeira escolha do próprio hOCR.

| CER de prosa, Δ contra `tess_hocr` | ouro-dev (0,286%) | prata (8,820%, ordenação) |
|---|---|---|
| margem 0,5 nat | +0,042 [−0,008; +0,113], 1 melhor, 7 piores | +0,094 [−0,032; +0,181], 2, 18 |
| margem 1 nat | +0,042 [−0,008; +0,113], 1, 7 | +0,084 [−0,046; +0,174], 2, 18 |
| margem 2 nats | +0,038 [−0,012; +0,111], 1, 6 | +0,063 [−0,065; +0,145], 2, 15 |
| controle: a alternativa que é do léxico | −0,004 [−0,017; 0], 1, 0 | +0,005 [−0,011; +0,022], 2, 3 |
| **teto**: a alternativa que está na referência | −0,046 [−0,133; 0], 6, 0 | −0,154 [−0,297; −0,073], 22, 0 |

**Por que não paga.** Nas 5.759 palavras do dev, com 1 nat, são 32 trocas: nenhuma leva a uma palavra da referência, e 11 estragam uma certa, quase sempre nome próprio (`Reshevsky` → `Resheysky`, `Najdorf` → `Nojdorf`), porque o que a lista da língua não conhece
é justamente o que o trigrama pune. Na prata, 147 trocas: 5 acertam, 36 estragam. E o teto é baixo: **até um oráculo que sabe a resposta só tira 0,046 p.p. no dev.** A letra certa quase nunca está nas alternativas.

**O custo, que a S-729 não mediu.** Ela recusou as alternativas por "um processo a mais por folha", sem número. É 0,88 s por folha no dev e 1,34 s na prata, se for um processo a mais; ou +15% (mediana, folha a folha) se o hOCR substituir o TSV, e aí a primeira escolha do hOCR
perde +0,017 p.p. [0; +0,045] no dev. Sob contenção, e não julga o G4. **O custo sozinho não o tornaria inviável. Quem recusa é o ganho.**

**Onde mora.** `docs/metrics/texto_escada_2026-11-06.json`, com `melhor_degrau`, `escada` e `ngramas`. `docs/metrics/texto_escada_2026-11-06/`: `ngramas.py` e `compilar.py`. Os JSONL ficam fora do repositório.

**Critério de aceite.** `EscadaPublicadaTests` em `tests/test_text_scan_ouro.py`: o melhor degrau tem nome, os degraus 1, 2 e 3 dizem `pulado por recuo`, o scan-ouro diz `sem número` e não zero, e o relatório não tem caminho absoluto.

**Desvios.** A verificação pede cada degrau pareado contra o anterior e no scan-ouro-dev: o par dos n-gramas é contra a primeira escolha do hOCR, e no scan-ouro não há verdade. A S-746 fica de fora, por recuo: só serve ao degrau 2. **O melhor degrau é provisório**: a D2 ou a D7 podem mudá-lo, e a S-755 tem de reler este relatório.

*Achado:* a primeira escolha do hOCR com `lstm_choice_mode=2` não é o TSV. Difere em 3 folhas do dev, e sempre para pior; na prata, 7 melhores e 10 piores. Quem for ler alternativas não pode supor que o texto é o mesmo.

## S-762 · A correção humana volta como dado, sem contaminar nada ✅ implementada (2026-11-06)

### Problema

`correcao.com_procedencia_humana` carimba o **bloco inteiro** como `humano` quando se edita um caractere, inclusive as palavras erradas que ninguém
conferiu. O carimbo serve à tela, que deixa de pintar o que a pessoa conferiu. Como dado, ele é falso nas duas direções: para a medição diz verdade onde há leitura de motor
por trás, o que a S-703 proíbe; para o treino, não diz qual palavra a mão tocou nem que modelo errou. E `coleta.promover` gravava `humano` em tudo o que passasse pela quarentena.

### Solução

`text/dado_corrigido.py`. **O carimbo fica como está, e nenhum caminho de dado o lê.** Duas portas:

- **A medição, fechada.** Procedência `corrigido_de:<motor>@<sha do modelo>`, em `text/procedencia.py`: `Registro.mede` é falso, `classe` a traduz para `modelo` em toda conta
  e regra de split (`dataset.procedencia_de`), e `violacoes_do_split` a reprova no teste. Duas guardas para quem vier: `procedencia.exigir_verdade(valor, onde=)` e
  `dado_corrigido.exigir_documento_cego(doc, onde=)`, que recusa o `.cvtxt` com leitura de motor por trás, corrigido ou não. **A tela da S-703 tem de chamar as duas**: o
  scan-ouro ainda não tem código, e a guarda espera por ele.
- **O treino, pela quarentena da S-214.** `pares_tocados` alinha **por palavra** o que o motor leu e o que ficou: só a troca de uma por uma, só de motor de leitura (`camada` não
  errou). `recortes_do_par` recorta só as letras que mudaram, só no par de mesmo tamanho, e só quando as caixas da linha casam uma a uma com as letras dela; senão, `sem_recorte`,
  e não se adivinha. `coleta.Recorte` leva a procedência, e `corrigidos.csv`, na raiz da quarentena, guarda o par; `promover` grava o `corrigido_de:` no lugar de `humano`.
  **O livro do teste nunca entra**, nem o que o manifesto tira do treino, nem livro sem identidade (`livro_recusado`), e a recusa vem antes de qualquer leitura de imagem.

**O sha.** `PaginaLida.modelo` é campo novo com padrão, sai do metadado que `carregar_classificador` já conferiu, e vai ao JSON só quando existe. **Não sobe `ESQUEMA` nem `arquivo.VERSAO`**,
e um programa anterior o ignora. `.cvtxt` de antes sai `@desconhecido`. **Não há valor novo no `Literal` de `Procedencia`**: a corrida continua `humano`, e `corrigido_de:` só existe em
registro e quarentena. A S-722, que vem depois em `pagina.py`, não colide além desse campo.

**Quem chama é uma pessoa**: `cvoff-texto-correcoes <pasta ou .cvtxt> --quarentena <pasta>`, que aceita a pasta do caderno. Gravar da janela a cada folha não entrou: a pasta padrão
fica dentro do programa, e levar à quarentena é decisão de quem está treinando.

### Critério de aceite

`tests/test_text_dado_corrigido.py`: só a palavra tocada vira par (com `wiil` errado e carimbado ao lado), `corrigido_de:` reprovado no split, na porta e no `.cvtxt`, livro do teste fora sem
abrir imagem, a conta de caixas que não fecha não adivinha, `promover` não lava a origem, ida e volta do `modelo` com o esquema em 1, e o comando do `.cvtxt` à quarentena.

Em folhas reais do dev, com uma letra trocada por bloco em 7 folhas de 3 livros, e o classificador como juiz de que o recorte é a letra certa: **85 pares, 70 com recorte, 69 dos 70 lidos
como a letra que o motor tinha lido ali**, e os 15 sem recorte são a conta que não fechou (8 deles numa folha do *Minhas 60*). Procedência gravada com o sha do `.pt` em uso.

### O que ela não entrega

- **A correção não treina nada**: fica na quarentena até uma pessoa mover a pasta, e nenhum treino foi rodado com ela.
- **Na fusão, o motor saía `glifo`** mesmo onde o Tesseract escreveu a palavra. A S-722 resolveu na folha lida; a reaberta do arquivo continua `glifo` até o G102.
- **Par de tamanho diferente** (`fi1rst` → `first`) conta e não vira recorte. O leitor de linha da Fase 105 é quem vai querer ele, com outro recorte.
- A correção não entra nas folhas seguintes: é a S-766.

## S-743 · O dígito de estilo antigo ✅ implementada (2026-11-06)

### Problema

Os livros do século XIX são Antiqua, e o que os destrói é o algarismo de estilo antigo. No *Bachmann*, a fusão saía com **27,7% das casas inválidas** (`Tgı-g2`, `Sbı-cg`, `Tdy-f7`, `Seö-f3`, `Sf3xeb`); no *Neumann*, com 13,8% (`dı-h5`, `e7-eb`).

### Decisão

O mapa de `arbitro._RANK`, **só na posição em que o dígito é obrigatório**: depois de uma coluna, onde só cabe de 1 a 8. `ı`, `I`, `l` e `|` são 1, `z` é 2, `g` é 3, `s` e `ö` são 5, `b` é 6, `y` é 7, `B` é 8. No número de lance o mapa é outro (`arbitro._NUMERO`), com o zero e sem o `g`, que pode ser 3 ou 9. A forma decide quanto contexto basta: a notação longa e o número colado no lance, nenhum; a curta (`Dhs`), um vizinho de notação; o peão (`es`), um de cada lado; a palavra que existe só cai entre dois lances. `B.` só é `8.` com `7.` ou `9.` por perto, e `A. B. Keres` fica. Fraktur fica de fora (D7).

A constante é `arbitro.DIGITO_FORCADO`.

### Critério de aceite

Em 19 folhas do *Bachmann* e 29 do *Neumann*, espaçadas e lidas pelo `motor="fusao"`, com `digitos.py`, cuja contagem é escrita à parte da gramática do árbitro:

| | casas válidas, antes | depois | `Io.`/`ıı.` antes | depois | número inválido antes de lance, depois |
|---|---:|---:|---:|---:|---:|
| *Bachmann* | 72,3% (145 em 524) | **100%** (531) | 1 | **0** | 1 (`(l)`) |
| *Neumann* | 86,2% (137 em 993) | **100%** (1.007) | 0 | **0** | 0 |

**Saída cumprida: nenhum `Io.`/`ıı.`, casas válidas ≥ 99%.** O juiz independente é pequeno, e diz o mesmo: da posição inicial, a partir de um número 1, o *Neumann* fecha legais 33 de 47 lances com o árbitro e 20 de 30 sem; o *Bachmann* das folhas sorteadas quase não tem começo de partida (3 de 3 e 2 de 2).

**Validade não é acerto:** uma casa válida pode ser a errada, e `g` por `3` num livro que usa `g` por `9` não muda a conta. Por isso o replay ao lado. `tests/test_text_arbitro.py`, `GramaticaTests`.
