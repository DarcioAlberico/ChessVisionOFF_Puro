# Roadmap da suíte de treino — Fases 80 a 86

O que separa este programa de uma suíte de treino que um enxadrista profissional usaria no lugar do
ChessBase, do Scid ou do Chessable, escrito em 2026-09-04 sobre a `suite-de-treino` (a pilha dos
PRs #27, #29, #30 e #31 juntada em `0cf5492`). Especificação item a item em
[SPEC_SUITE.md](SPEC_SUITE.md) (S-527 a S-580, faixa reservada; o que não for entregue fica em aberto).

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
> | S-235 a S-267, S-291 a S-293, S-521 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-451, S-452 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |
> | S-507 a S-520 | [SPEC_ESTUDO_QT.md](SPEC_ESTUDO_QT.md) |
> | S-522 a S-526 | [SPEC_REVISAO_EXTERNA_2.md](SPEC_REVISAO_EXTERNA_2.md) |
> | S-500 a S-506, S-527 a S-580 | [SPEC_SUITE.md](SPEC_SUITE.md) |

## O que este documento é

O pedido do dono foi uma suíte "no nível do ChessBase, Scid, Lichess, Chess.com, ChessKing e
Chessable, com reconhecimento de diagramas no nível do chessvision.ai e do chessocr", para quem tem
bases de vários gigabytes e uma pilha de PDFs de qualidades variadas. Isto não cabe num item, e por
isso virou sete fases, cada uma com o que dá para **medir**: a fotografia da janela sem tela
(`WA_DontShowOnScreen`, 1400×950), a contagem de linhas da catraca de `test_packaging`, o tempo de
indexar um `.pgn` de referência, e a suíte.

**Método de cada item:** um executor implementa; um crítico independente fotografa a janela, compara
lado a lado com o que o ChessBase e o Lichess mostram para o mesmo gesto, e devolve o que falta. O
item só fecha quando o crítico não acha mais nada. O que o crítico recusou e por quê fica registrado
na seção do item em [SPEC_SUITE.md](SPEC_SUITE.md), porque um número que contradisse a intuição é o
que este projeto guarda.

**O que fica de fora, e por quê:** formatos nativos do ChessBase (`.cbh`) e do Scid (`.si5`) -- são
formatos fechados ou sem biblioteca Python madura, e o `.pgn` é a moeda de troca de todos eles; jogo
em rede; e o repertório completo do Chessable, que é produto e não recurso. O que entra da repetição
espaçada é o agendamento sobre os estudos que já existem (S-540).

## Fase 80 — a barra e a sala (o que se vê primeiro)

A janela de hoje tem **quatro filas de botões de texto** sobre a sala de estudo e três sobre o PDF
(fotografia de 2026-09-04): 37 botões, nenhum com ícone, sem agrupamento. O ChessBase agrupa em
faixa por tarefa; o Lichess esconde o que não é do momento.

- **S-527** · A barra da sala de estudo agrupada por tarefa, com ícones vetoriais e rótulo curto
- **S-528** · A barra do painel do PDF na mesma gramática, e a página com mais área
- **S-529** · O painel do motor: barra de avaliação vertical, linhas MultiPV clicáveis, profundidade
- **S-530** · O cabeçalho da partida (jogadores, Elo, evento, data, resultado) visível e editável
- **S-551** · A coluna do tabuleiro cresce pela altura, e o divisor da sala se move (achado do crítico do S-527: ~230 px vazios sob o tabuleiro a 1400×950)
- **S-552** · A janela cabe em 1024 px de largura (achado do crítico do S-527: pedida a 1000×800, a janela fica em 1245×902)
- **S-553** · O foco de teclado se vê (achado do crítico do S-527, rodada 2: `hasFocus()` desenha 0 px diferentes nos 12 pontos de parada da barra)
- **S-554** · O ícone desabilitado apaga também na pele escura (achado do crítico do S-527, rodada 2: razão 9,47 habilitado contra 9,82 desabilitado -- o desligado é mais claro)

## Fase 81 — a base de partidas de vários gigabytes

- **S-531** · Ler `.pgn.gz`, `.pgn.bz2` e `.zip` de PGN sem descompactar para o disco
- **S-532** · Índice incremental: só o que mudou é relido, com progresso e cancelamento na janela
- **S-533** · Busca por jogador, torneio, ano, Elo, resultado e ECO, com filtros combinados e lista
- **S-534** · Classificação ECO embutida, gravada no índice e mostrada na sala
- **S-535** · Árvore de aberturas: da posição corrente, cada lance com N, %, Elo médio e ano

## Fase 82 — análise

- **S-536** · Opções do motor (Hash, Threads, MultiPV, caminho) nas preferências, sem reiniciar
- **S-537** · Análise de partida: cada lance avaliado, gráfico de avaliação e erros marcados
- **S-538** · Tablebases Syzygy quando a pasta existir: resultado exato nos finais

## Fase 83 — treino

- **S-539** · Táticas do próprio acervo: FEN reconhecida + solução impressa vira exercício
- **S-540** · Repetição espaçada dos estudos e das táticas, com agenda do dia
- **S-541** · "Adivinhe o lance" com placar persistente e comparação com o motor

## Fase 84 — o editor de materiais

- **S-542** · Exportar estudo e texto para EPUB, com diagramas como SVG
- **S-543** · Exportar para DOCX
- **S-544** · Diagramas em lote como PNG/SVG, no tamanho e na pele escolhidos
- **S-545** · Imprimir e gerar PDF do estudo com a paginação de livro

## Fase 85 — OCR em lote na janela

- **S-546** · Fila de PDFs com progresso por livro, cancelável, e o resultado ao lado do nome
- **S-547** · Caminho para scans puros: binarização e reamostragem antes da detecção
- **S-548** · Relatório de qualidade por livro: páginas lidas, diagramas, legalidade, tempo

## Fase 86 — as guardas que faltam

- **S-549** · Guarda genérica: nenhum módulo de `ui/` importa `PyQt6`
- **S-550** · As S-500 a S-506 do corte do Tk ganham seção de spec (dívida de documentação)

## Placar

| fase | estado | medido |
|---|---|---|
| 80 | ✅ 2026-09-05 | A barra da sala de 154 para 32 px e a do PDF de 118 para 32; o cabecalho da partida acima do tabuleiro; o tabuleiro cresce pela altura (616 para 662 px a 1920x1080); a janela deixou de crescer ao ler (piso de 902 para 553 px); foco de teclado e icone desabilitado visiveis nas tres peles |
| 81 | ✅ 2026-09-05 | PGN comprimido em streaming; indice incremental (8,63 GB do zero em ~20 min, segunda rodada em 0,005 s); busca por doze filtros abaixo de 1 s sobre 10,3 milhoes de partidas; ECO a 86,39% contra o header; arvore de aberturas em 0,6 ms de mediana |
| 82 | ✅ 2026-09-05 | Opcoes do motor sem reiniciar (setoption no processo aberto, 1,34 para 2,33 MN/s); barra de avaliacao que diz quem mateia; analise da partida por expectativa de vitoria, com as divergencias contra o Lichess caindo de 14 para 4 em 256 lances; Syzygy real a 123 us de mediana |
| 83 | ✅ 2026-09-05 | S-539 de 24 exercicios com zero corretos para 913, com 891 conferidos contra a tabela impressa e 195 de 200 confirmados pelo motor; S-540 e FSRS-4.5 conferido caso a caso contra a formula publicada; S-541 com placar no disco |
| 84 | ✅ 2026-09-05 | EPUB 3 com zero erro no epubcheck e DOCX que o Word le, com a tipografia de notacao que um editor reconhece; mil diagramas em lote em 3,01 s de SVG; o estudo impresso em vetor, com texto selecionavel |
| 85 | ✅ 2026-09-05 | A fila de livros na janela, com progresso por pagina (120 avisos em 81 s onde havia 4) e um relatorio de qualidade por livro; S-547 medida e recusada, com o numero: o Otsu acha 55% mais diagramas no livro que exporta zero e nenhum passa do gate |
| 86 | ✅ 2026-09-04 | S-549: 52 módulos de `ui/` sem toolkit, guarda acha 31/33 em `qt/`; S-550: sete seções, faixa em 27 cópias |

## O veredito

Sete rodadas de crítica independente, cada uma fotografando a janela sem mostrá-la, medindo pixel e
contraste e reproduzindo as consultas na gigabase. **Aprovado para AAA em 2026-09-05**, no commit
`2708309`, depois de sete itens reprovados e refeitos.

O que a crítica achou e nenhum executor acharia sozinho está escrito na seção de cada item, em
[SPEC_SUITE.md](SPEC_SUITE.md). O padrão que mais apareceu -- e o que este roadmap deixa de herança
-- é a **guarda que se pergunta ao próprio dado que deveria travar**: quatro delas foram achadas
revertendo o conserto e vendo a suíte continuar verde. Um docstring que descreve o caso não prova
que o caso foi medido.

### O que não é bloqueio, e o dono decide se vem depois

Ordenado pelo que pesa para um enxadrista com base de vários gigabytes e para quem edita material,
com estimativa grosseira:

| o que falta | por quê | esforço |
|---|---|---|
| Busca por posição sobre a base inteira | não há índice de posição: a pergunta que o ChessBase responde num piscar é varredura linear aqui | 3 a 5 semanas |
| Os cinco livros que exportam zero | a S-547 mediu a binarização e registrou honestamente que não há ganho; "é um scan" e "é um scan que o modelo não lê" são perguntas diferentes | 4 a 8 semanas, e é dado de treino, não pré-processamento |
| Repertório e preparação por adversário | não existe módulo nenhum, e é metade do valor do ChessBase para quem compete | 3 a 4 semanas |
| O curso no formato do Chessable | a repetição espaçada e o "adivinhe o lance" são o motor; falta o curso como objeto, com importação e progresso | 2 a 3 semanas |
| Análise em lote sobre a base | a S-537 analisa uma partida e, por decisão registrada, não guarda o resultado | 1 a 2 semanas |
| Elo máximo, número de lances e rodada na busca | a spec já escreveu o custo de cada um; dois pedem coluna nova e uma versão 7 do índice | 4 a 7 dias |
| ECO acima de 90% | hoje 86,39% exatos contra o header; o caminho é mais medição e mais linhas, não outra regra | 1 a 2 semanas de trabalho de dados |
| Sincronização entre máquinas | tudo é local | 2 a 4 semanas |
| Idioma | `ui/strings.py` são 411 linhas de pt-BR cravado, sem `gettext` | 1 a 2 semanas mais a tradução |
| LaTeX e `.cbv` na exportação | EPUB, DOCX, PDF, PNG e SVG existem e estão medidos | 2 a 4 dias cada |

