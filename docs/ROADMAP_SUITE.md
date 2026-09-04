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
> | S-527 a S-580 | [SPEC_SUITE.md](SPEC_SUITE.md) |

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
| 80 | ◻ | — |
| 81 | ◻ | — |
| 82 | ◻ | — |
| 83 | ◻ | — |
| 84 | ◻ | — |
| 85 | ◻ | — |
| 86 | ◻ | — |
