# PDF digital com o PGN do livro — plano e especificação (S-585 a S-593)

Livro digital costuma vir com o `.pgn` das partidas e linhas do autor: uma partida por seção do
capítulo, com a árvore inteira de variantes. Cada diagrama do PDF é um nó dessa árvore. Ter o nó é
ter a FEN exata, o lado a jogar que a imagem não diz, e a análise do autor a partir dali. Este
documento é o plano e a especificação no mesmo arquivo, como o
[ROADMAP_MESA_DE_TEXTO.md](ROADMAP_MESA_DE_TEXTO.md) começou: as seções `### S-NNN` moram só aqui.

## O que foi medido antes de escrever uma linha (2026-10-29)

O livro da amostra é o Harikrishna, *Beat the French Defence with 3.Nc3* (Thinkers Publishing): o
PDF de 748 páginas que o calibre gerou de um EPUB, e o PGN de 120 partidas («Chapter N / Game N»),
só lances, variantes e NAGs, 12.697 nós e 10.910 posições distintas.

- **Cada diagrama tem legenda na camada de texto**: «Position after: 5.dxc5». São 1.177 legendas
  para 1.001 imagens. Com o capítulo tirado do sumário do PDF, 1.175 legendas acham candidato.
- **Contra o modelo de produção** (`cvoff-livro-com-pgn`, o código desta entrega): 1.180
  diagramas; **951 conferem** casa por casa com o nó, **22 o PGN corrige** (até duas casas),
  **17 discordam** (três a seis casas), **188 faltam no PDF** e 2 ficam sem nó. Das 990 imagens,
  973 (98%) se resolvem sem ninguém olhar.
- **Os que discordam são erro do modelo**, não do PGN: cavalo lido como bispo, a torre de a1 e o
  peão de c2 que somem. São o exemplo difícil que mais ensina no treino (S-593).
- **~188 diagramas faltam no PDF**: a legenda existe e a imagem não, perdida na conversão. Só o PGN
  os pode redesenhar (S-591).
- **Sem usar a legenda**, procurando a leitura do modelo em todas as posições do livro, saem os
  mesmos casos exatos e os de uma casa: o livro sem legenda também é casado.

**Três defeitos que a medição achou e que estão travados em teste:**

1. 21 das 120 partidas têm duas linhas em branco entre o cabeçalho e os lances, e o
   `chess.pgn.read_game` as partia em duas (S-585).
2. A legenda cuja imagem faltou pegava a imagem da legenda de cima: 130 «discordâncias» eram isso
   (S-587).
3. A imagem do pé da página cuja legenda abre a seguinte era rasterizada na página da legenda: 77
   «discordâncias» eram isso (S-587).

## Onde cada coisa mora

| camada | arquivo | o quê |
|---|---|---|
| puro | `pgn_do_livro.py` | leitura tolerante, rótulo do lance, índice por rótulo e por posição |
| puro | `livro_com_pgn.py` | legendas e imagens da página, capítulo pelo sumário, casamento, estados, associação PDF ↔ PGN |
| linha de comando | `cli/livro_com_pgn.py` | `cvoff-livro-com-pgn`, a régua |
| janela | `qt/livro_com_pgn.py` | carregar e esquecer o PGN, a página lida, a Revisão, o Estudo, os que faltam |
| dataset | `importacao_de_imagens.py` | o lote «PDF + PGN do livro» |

**Nada disto está no caminho de medição (S-218).** O `service.py` lê a imagem como sempre; a FEN do
livro entra depois, em `janela._chegaram_itens`. Os relatórios de campo não mudam.

---

### S-585 · O PGN do livro lido inteiro

**Problema.** O `read_game` termina a partida na segunda linha em branco depois do cabeçalho: sai
uma partida só com cabeçalho e outra só com lances. O «Abrir um .pgn…» do Estudo descartava a
primeira (sem lance, sem posição) e mostrava a segunda sem «Chapter 3 / Game 2».

**Decisão.** `pgn_do_livro.fluxo_tolerante` embrulha o arquivo aberto (só `readline`, sem lê-lo
para a memória: o mesmo laço lê bases de 10 GB) e junta as linhas em branco que vêm depois de um
cabeçalho e antes de um lance. Antes de outro `[` elas ficam: ali há duas partidas de verdade.
`estudo_arquivo.estudos_de_pgn` passa a ler por ele.

**Aceite.** O texto do Harikrishna dá duas partidas com cabeçalho; sem o fluxo dá três (a
sabotagem); cabeçalho sem lance seguido de outra partida continua sendo duas. Testes em
`tests/test_pgn_do_livro.py`.

### S-586 · O índice da árvore

**Decisão.** `IndiceDoLivro` guarda cada nó com capítulo (`Event`), seção (`Site`), o rótulo do
lance como o livro o escreve (`5.dxc5`, `3...c5`), o caminho na árvore (`estudo.caminho_de`) e a
FEN, em ordem de leitura (a principal antes das variantes). Duas perguntas: `com_rotulo(capitulo,
lance)` e `com_posicao(campo)`. `no(k)` devolve o nó do `chess.pgn` para o Estudo.

**Aceite.** Rótulos, ordem, as duas buscas e a volta ao nó, em `tests/test_pgn_do_livro.py`.

### S-587 · A imagem e a sua legenda

**Decisão.** `livro_com_pgn.diagramas_da_pagina` lê o `get_text("dict")` da página: a imagem de uma
legenda é a mais baixa acima dela **sem outra legenda no meio**; uma legenda no alto da página sem
imagem acima pega a que sobrou no pé da anterior, e o diagrama guarda as duas páginas
(`pagina` é a da imagem, `pagina_da_legenda` a da legenda). Imagem sem legenda também é diagrama.
O capítulo vem do sumário (`capitulos_do_sumario`), casado por palavra inteira: «Chapter 1» não
casa com «Chapter 10». As legendas conhecidas estão em `PADROES_DE_LEGENDA` (inglês, português,
alemão, espanhol).

**Aceite.** As páginas 21, 26 e 27 do Harikrishna, reproduzidas em `tests/test_livro_com_pgn.py`.

### S-588 · O nó de cada diagrama e o estado dele

**Decisão.** Candidatos pela legenda no capítulo (e, sem nenhum, sem a desambiguação a mais do
livro: `12.Nbc3` no livro, `12.Nc3` no PGN); sem legenda, pela posição lida, e a até duas casas de
uma única posição. Com leitura, o candidato **mais perto dela** ganha, e a ordem do livro só
desempata -- com o modelo errando uma casa nenhum candidato é exato, e a ordem sozinha escolhia o nó
de outra partida a 15 casas. Estados: `confere`, `corrigido` (até `CASAS_CORRIGIVEIS` = 2),
`discorda`, `faltando`, `sem_no`, `sem_leitura`.

**Por que duas casas.** Das discordâncias medidas, 15 eram de uma casa e nenhuma de duas; acima
disso o par imagem-legenda pode estar errado, e decidir sozinho trocaria um erro do modelo por um
erro de pareamento.

**Aceite.** Estados pela leitura, o candidato mais perto, o capítulo que separa a mesma jogada, a
legenda sem imagem e o livro sem legenda, em `tests/test_livro_com_pgn.py`.

### S-589 · A régua: `cvoff-livro-com-pgn`

`cvoff-livro-com-pgn --pdf X --pgn Y [--sem-modelo] [--json saida.json]` casa o livro inteiro e
conta os estados, listando os que discordam. É a conta desta página, refeita sobre o código que a
janela usa. O PDF da amostra não está no repositório (fica em `PDF/`, fora do git, como os outros
livros), e por isso o relatório não é publicado em `docs/metrics/`.

### S-590 · Carregar PGN do livro

**Decisão.** *Arquivo › Carregar PGN do livro…* associa o `.pgn` ao PDF aberto em
`data/livros_com_pgn.json`, pela identidade do conteúdo do PDF (a do caderno da aba Texto), e lê o
índice numa `Tarefa`. A partir daí, cada página lida passa por `qt/livro_com_pgn.LivroComPgn.aplicar`:

- `confere`, `corrigido` e `sem_leitura`: a posição e o lado a jogar do nó vão ao Resultado como
  edição desfazível (`PainelDeResultado.adotar_do_livro`), as casas trocadas em roxo e a frase
  «PGN do livro: Chapter 1 · Game 3 · 5.dxc5 -- ...» nos detalhes; o lado a jogar diz «do PGN do
  livro». A aba Texto recebe a mesma FEN, e é ela que o EPUB e o DOCX escrevem.
- `discorda`: a leitura fica, e o diagrama entra na Revisão (`PainelDeRevisao.acrescentar`) com a
  FEN do livro como sugestão, o peso de «fontes discordam» e o motivo escrito.
- `faltando`: o rodapé diz quais diagramas da página o PDF perdeu.

*Esquecer o PGN do livro* desfaz a associação.

**A rota do rótulo.** A FEN do livro não entra como «segunda opinião» no modelo do editor
(`from_book`/`book_squares` à parte de `second_opinion`): `labels.label_route` está no caminho de
medição, e contar o livro como segundo leitor gravaria a procedência errada.

**Aceite.** `tests/test_qt_livro_com_pgn.py`: a página casada adota a posição e o lado, a
discordância vai à Revisão uma vez só, e outra página não recebe o que é desta.

### S-591 · Os diagramas que faltam no PDF

**Decisão.** *Arquivo › Diagramas que faltam no PDF…* casa o livro inteiro (sem o modelo: só a
legenda) e lista cada diagrama sem imagem -- página, legenda, capítulo e partida --, com o tabuleiro
desenhado do PGN (`desenho_de_diagrama.png_do_diagrama`). Para cada um: ir à página, estudar na
árvore do livro, copiar a FEN, salvar a imagem.

**O que ficou para depois.** Pôr o diagrama que falta **dentro da folha** da aba Texto é uma
operação de edição nova -- uma corrida de diagrama a mais no documento, com o mapa de posições, a
guarda de paridade (S-603) e o desfazer --, e não cabe como efeito colateral de ler a página. A
miniatura já nasce da FEN quando não há recorte; o que falta é o comando que insere a marca.

### S-592 · Estudar na árvore do livro

**Decisão.** *Estudo › Estudar na árvore do livro* abre o diagrama selecionado no Resultado com a
partida inteira do autor, posicionada no nó (`PainelDeEstudo.abrir_no_livro`). A partida é uma
cópia (o Estudo edita a árvore, o índice não pode mudar) e leva `SourcePDF`, `Page`, `Diagram` e
`Caption`, que é como a sala a guarda junto dos outros estudos do livro.

### S-593 · O livro como lote do dataset

**Decisão.** A importação de imagens ganha a origem «PDF + PGN do livro»: cada diagrama casado vira
um item com a imagem recortada da página, a FEN do nó como `fen_da_fonte` (com o lado a jogar) e a
legenda. A conferência é a de sempre (`concorda`: o modelo lê a mesma posição), então os que
conferem entram com «Importar os que concordam» e os que discordam vão à conferência humana -- que
são exatamente os exemplos que o modelo erra. A procedência registra o livro e a página.

---

## O que fica fora, e por quê

- **A legenda de outros editores.** `PADROES_DE_LEGENDA` cobre a forma «Position after»/«Posição
  após» em quatro línguas. Livro com outra forma cai no casamento pela posição, que cobre os casos
  exatos e os de uma casa.
- **Transposição.** A mesma posição pode estar em dois nós com o lado a jogar diferente. Com
  legenda o capítulo e o rótulo decidem; sem legenda vale o primeiro na ordem do livro.
- **A Galeria.** O casamento acontece na página lida; a varredura do livro inteiro na Galeria não
  passa por ele nesta entrega.
