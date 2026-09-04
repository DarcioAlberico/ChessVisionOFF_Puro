# Especificação da suíte de treino — Fases 80 a 86 (S-527 a S-580)

Os itens de [ROADMAP_SUITE.md](ROADMAP_SUITE.md), um a um. A faixa S-527 a S-580 está reservada para
este documento; um número sem seção aqui é item ainda não entregue, e não item perdido.

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

Cada item tem **Problema** (com `arquivo:linha` do estado em `0cf5492`), **Solução**, **Critério de
aceite**, **Testes** e **O que o crítico recusou** -- o registro das rodadas em que a fotografia da
janela foi comparada lado a lado com o ChessBase e o Lichess, e o que faltava em cada uma.

---

## S-527 · A barra da sala de estudo agrupada por tarefa, com ícones vetoriais e rótulo curto — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-528 · A barra do painel do PDF na mesma gramática, e a página com mais área — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-529 · O painel do motor: barra de avaliação vertical, linhas MultiPV clicáveis, profundidade — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-530 · O cabeçalho da partida (jogadores, Elo, evento, data, resultado) visível e editável — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-531 · Ler `.pgn.gz`, `.pgn.bz2` e `.zip` de PGN sem descompactar para o disco — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-532 · Índice incremental: só o que mudou é relido, com progresso e cancelamento na janela — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-533 · Busca por jogador, torneio, ano, Elo, resultado e ECO, com filtros combinados e lista — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-534 · Classificação ECO embutida, gravada no índice e mostrada na sala — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-535 · Árvore de aberturas: da posição corrente, cada lance com N, %, Elo médio e ano — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-536 · Opções do motor (Hash, Threads, MultiPV, caminho) nas preferências, sem reiniciar — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-537 · Análise de partida: cada lance avaliado, gráfico de avaliação e erros marcados — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-538 · Tablebases Syzygy quando a pasta existir: resultado exato nos finais — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-539 · Táticas do próprio acervo: FEN reconhecida + solução impressa vira exercício — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-540 · Repetição espaçada dos estudos e das táticas, com agenda do dia — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-541 · "Adivinhe o lance" com placar persistente e comparação com o motor — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-542 · Exportar estudo e texto para EPUB, com diagramas como SVG — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-543 · Exportar para DOCX — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-544 · Diagramas em lote como PNG/SVG, no tamanho e na pele escolhidos — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-545 · Imprimir e gerar PDF do estudo com a paginação de livro — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-546 · Fila de PDFs com progresso por livro, cancelável, e o resultado ao lado do nome — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-547 · Caminho para scans puros: binarização e reamostragem antes da detecção — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-548 · Relatório de qualidade por livro: páginas lidas, diagramas, legalidade, tempo — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-549 · Guarda genérica: nenhum módulo de `ui/` importa `PyQt6` — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-550 · As S-500 a S-506 do corte do Tk ganham seção de spec (dívida de documentação) — ◻ em andamento

_Seção a escrever pelo executor do item._
