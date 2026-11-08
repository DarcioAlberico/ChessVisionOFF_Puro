# Roadmap da solidez — Fases 110 a 121 (S-800 a S-873)

Revisão do programa inteiro em 2026-11-08, feita sobre `origin/main` (`e8c9f64a`) com o método
*ub-mode*: primeiro funcionar (a decisão num lugar só, a forma do dado antes da lógica, o teste que
falha antes do conserto, a premissa atacada quando dois consertos caem no mesmo portão), depois
ficar certo (causa-raiz, unidades verificáveis, teste de comportamento, CRAP, duplicação,
mutação), e a prática (registro, commits pequenos). A spec de cada item está em
[SPEC_SOLIDEZ.md](SPEC_SOLIDEZ.md).

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
> | S-702, S-710 a S-712, S-715 a S-718, S-720 | [SPEC_TEXTO_PRECISO.md](SPEC_TEXTO_PRECISO.md) |
> | S-800 a S-873 | [SPEC_SOLIDEZ.md](SPEC_SOLIDEZ.md) |

## 1. O que se mediu

| medida | valor em `e8c9f64a` | instrumento |
|---|---|---|
| funções e métodos em `src/` + `app_pyqt.py` | 9.130 (com os métodos contados uma vez por classe) | `radon cc` |
| funções com complexidade ciclomática ≥ 10 | 463 | `radon cc` |
| funções com complexidade ≥ 20 | 79 | `radon cc` |
| funções com CRAP ≥ 30 | *ver §1a* | crapper (cobertura × complexidade) |
| pares de funções com semelhança ≥ 0,8 | 65 (340 com ≥ 0,6) | dryer (Jaccard de 5-gramas de tokens normalizados) |
| `# type: ignore` | 192 (80 `arg-type`, 63 `attr-defined`) | `grep` |
| `except Exception` | 175 | `grep` |
| `Any` | 892 | `grep` |
| testes desligados por `@unittest.skip` incondicional | 26 | auditoria |
| maior arquivo | `qt/painel_de_texto.py`, 5.030 linhas, 294 métodos numa classe | `wc -l` |

As três ferramentas que o método pede (crapper, dryer, mutator) não existiam no projeto. Elas foram
escritas para esta revisão e entram no repositório na Fase 110 (S-801 a S-803), com catraca.

### 1a. As funções mais complexas

| função | complexidade | fase que a parte |
|---|---|---|
| `text/leitor.py` `_ler_pagina_do_livro` | 71 | 119 (S-860) |
| `text/ouro.py` `problemas` | 53 | 119 (S-861) |
| `ui/state.py` `state_from_dict` | 51 | 114 (S-828) |
| `field_eval.py` `evaluate_page` | 50 | 116 (S-835) |
| `cli/texto_train.py` `main` | 49 | 119 (S-863) |
| `pdf_to_pgn.py` `build_pgn_games` | 42 | 119 (S-858) |
| `cli/audit.py` `_print_report` | 39 | 119 (S-863) |
| `text/leitor.py` `linhas_do_glifo` | 37 | 119 (S-860) |
| `training.py` `Trainer.prepare` | 36 | 119 (S-858) |
| `text/fusao.py` `fundir` | 36 | 119 (S-861) |
| `pdf_text.py` `_page_lines` | 36 | 116 (S-836) |
| `detection/hybrid.py` `detect_diagrams` | 36 | 119 (S-859) |
| `pdf_to_pgn.py` `_scan_pages` | 35 | 116 (S-833) |
| `qt/painel_de_texto.py` `PainelDeTexto.eventFilter` | 34 | 114 (S-825) |

## 2. As premissas atacadas

Os 80 achados não são 80 problemas. Seis premissas, cada uma segurada por vários atores, geram a
maior parte deles. O roadmap remove a premissa em vez de consertar cada ator.

1. **"Arquivo que não lê é arquivo vazio."** Sete leitores tratam o arquivo ilegível, ou de esquema
   mais novo, como começo do zero, e o gravador seguinte escreve o vazio por cima: `settings.json`,
   `revisao.json`, `placar.json`, o estudo da sala, a fila de revisão, o lote de importação e o
   cache de posições (que se esvazia quando o conjunto de bases *parece* diferente). O incidente de
   2026-10-18, com ~9.810 linhas apagadas do cache, é esta premissa. **Remoção:** um tipo de leitura
   com três estados (lido, ilegível, de esquema futuro), e o ilegível trava a gravação (S-812).
2. **"O resultado assíncrono é da página N."** A janela, a aba Texto e a detecção de fundo marcam o
   resultado só pela página, e o livro pode ter mudado. O diagrama do livro A entra no livro B e,
   com Ctrl+S, no dataset de treino. **Remoção:** uma `Ancora(documento, pagina)` pura, capturada no
   pedido e conferida na chegada, nos três lugares (S-822).
3. **"Copiar para manter igual."** Comentários como *"Escrito igual ao de lá de propósito"* justificam
   uma cópia em vez de um import. Há o árbitro de confiança em três cópias, o pipeline de
   reconhecimento em duas (o medido e o exportado), a regra de fonte de diagrama em duas que já
   discordam, a camada de OCR em três, a identidade do livro em cinco e a impressão digital da base
   em duas. **Remoção:** cada decisão num módulo, importada (Fases 116, 118 e 119).
4. **"A mensagem é o dado."** Contadores publicados nos relatórios de campo contam substrings de
   frases em português (`"trocas diferentes"`, `"falta o rei"`). Reescrever a frase zera o contador.
   **Remoção:** campo tipado ou enum no resultado (S-835).
5. **"O relógio decide."** A decodificação restrita para em 0,5 s de relógio, então a mesma
   probabilidade pode sair em FEN diferente numa máquina carregada. **Remoção:** orçamento em
   expansões (S-834).
6. **"Quem chama sabe."** Não há borda de exceção no processo Qt, e em PyQt6 exceção em slot é
   `qFatal`: a janela some sem log. O projeto pôs `try` slot por slot. **Remoção:** um
   `sys.excepthook` no `main` (S-800).

## 3. Glossário

| termo | quer dizer |
|---|---|
| **âncora** | o par `(documento, página)` em que um pedido assíncrono foi feito; o resultado só vale se a tela ainda está na mesma âncora |
| **arquivo do dono** | dado que o programa não sabe refazer: `settings.json`, `revisao.json`, `placar.json`, o estudo, a fila de revisão, o lote, os rótulos |
| **leitura travada** | estado de um arquivo do dono que não leu, ou que é de esquema futuro; o programa segue em memória e recusa gravar por cima |
| **camada de arquivo / camada efetiva** | o que está gravado em `settings.json` / o que vale agora, depois das variáveis `CVOFF_*`; só a primeira é gravada |
| **impressão digital da base** | nome e tamanho de cada base de partidas, inclusive membro de `.zip`; decide se o cache e o índice ainda valem |
| **caminho de medição** | o código que os quatro relatórios de campo de `docs/metrics/` exercitam; tocar nele obriga a remedir (S-218) |
| **regime** | a configuração de aumento de dados com que um checkpoint foi treinado; a letra (`augh`, `augx`) é o nome curto dela |
| **colocação** | as 64 casas de um tabuleiro, peça ou vazio; o tipo que substitui a string de FEN dentro do programa (S-842) |
| **catraca** | teste que guarda uma contagem e falha quando ela sobe; descer é sempre permitido e baixa o teto |
| **CRAP** | `cc² × (1 − cobertura)³ + cc` por função; acima de 10 a função pede teste ou divisão |

## 4. A ordem e o porquê

A ordem segue "faça primeiro o que ajuda todas as fases seguintes" e, depois, o risco para o dado
do dono.

| fase | tema | itens | por que nesta posição |
|---|---|---|---|
| 110 | Alavancas: borda de exceção, ferramentas e infraestrutura de teste | S-800 a S-805 | toda fase seguinte usa a borda (queda vira log), as catracas e a `TarefaAdiada` |
| 111 | Caches e índices que não se apagam sozinhos | S-806 a S-809 | é o defeito que já custou dado do dono, e um `--census` o repete |
| 112 | Arquivos do dono | S-810 a S-817 | a mesma premissa nos sete arquivos; S-812 é o tipo que todos usam |
| 113 | Escritas idempotentes e atômicas | S-818 a S-822 | rodar duas vezes ou cair no meio termina no mesmo estado |
| 114 | A tela sabe de onde veio cada resultado | S-823 a S-829 | contamina o dataset em silêncio; depende da `TarefaAdiada` (S-805) |
| 115 | Interpretador e documentos | S-830 a S-832 | o 3.10 saiu de suporte em outubro de 2026 e vai dentro do `.exe` |
| 116 | Um pipeline só: o que se mede é o que se exporta | S-833 a S-837 | todo o caminho de medição numa fase, para remedir uma vez (S-837) |
| 117 | Treino honesto | S-838 a S-846 | página de campo no treino invalida o número publicado |
| 118 | Texto: fronteira e decisões únicas | S-847 a S-856 | coordenada com as Fases 100 a 107, que mexem nos mesmos arquivos |
| 119 | Complexidade e duplicação | S-857 a S-864 | depois das fases que mudam comportamento, para refatorar código já certo |
| 120 | Os arquivos-deus do Qt | S-865 a S-867 | depois da 114, que fecha os defeitos de tarefa que a divisão carrega |
| 121 | Testes que medem comportamento | S-868 a S-873 | os sobreviventes do mutator e a limpeza que sobrou |

**O que não está aqui.** A precisão da prosa é das Fases 100 a 107
([ROADMAP_TEXTO_PRECISO.md](ROADMAP_TEXTO_PRECISO.md)). Quando um achado desta revisão já tinha
item lá, ele não ganhou número novo: a regra 5 da fusão é da S-721, o modo bloco da S-726, o cache
do Tesseract da S-725, a procedência por intervalo da S-722. A S-31 (janela abaixo de 600 linhas)
continua aberta no [ROADMAP.md](ROADMAP.md), e a S-867 trabalha para ela.

## 5. Os itens

### Fase 110 — Alavancas

- **S-800** · Borda de exceção do processo, e o estado da sessão gravado antes da queda
- **S-801** · crapper no repositório, com catraca de CRAP por função
- **S-802** · dryer no repositório, com catraca de pares duplicados
- **S-803** · mutator no repositório, com piloto em seis módulos puros
- **S-804** · Catraca de tipos: `warn_unused_ignores`, e as contagens de `type: ignore`, `Any` e `except Exception` que só descem
- **S-805** · Infraestrutura de teste: `TarefaAdiada` compartilhada, `QThread` visível à guarda de vazamento, guardas de dados ancoradas no checkout principal, PyQt6 ausente reprova

### Fase 111 — Caches e índices que não se apagam sozinhos

- **S-806** · `open_store` nunca esvazia o cache: as linhas são chaveadas pela impressão digital
- **S-807** · Uma impressão digital de base só, que enxerga membro de `.zip`
- **S-808** · URI de SQLite montada por `Path.as_uri()`, e versão ilegível não apaga o índice
- **S-809** · `--build-index` com subconjunto de bases não apaga as outras

### Fase 112 — Arquivos do dono

- **S-810** · Booleano estrito e faixas numéricas no `settings.json`: `"false"` não liga o envio remoto
- **S-811** · Camada de arquivo e camada efetiva: o ambiente não vai para o disco, e chave desconhecida sobrevive
- **S-812** · Leitura travada: o arquivo do dono que não lê vira cópia `.ilegivel` e trava a gravação
- **S-813** · Baralho de revisão e placar sob a leitura travada, com tolerância por item
- **S-814** · Sala de estudo: partida que não lê sobrevive à gravação
- **S-815** · Fila de revisão: FEN corrigida sobrevive ao revarrer, e a pasta de miniaturas leva o hash do caminho
- **S-816** · `cvoff-scan` retomado preserva as pendências das páginas já vistas (a S-119 do GUI, numa função só)
- **S-817** · Quarentena de rótulos em conflito sempre desfazível

### Fase 113 — Escritas idempotentes e atômicas

- **S-818** · Exportação de PGN atômica, e sem `.review.pgn` de rodada anterior
- **S-819** · Retomada de exportação sem perda de campo
- **S-820** · Importação de imagens idempotente: andamento por item, amostra deduplicada por conteúdo
- **S-821** · PDF pesquisável idempotente e atômico
- **S-822** · Catraca de escrita: nada em `src/` grava arquivo do dono fora do `atomic_io`

### Fase 114 — A tela sabe de onde veio cada resultado

- **S-823** · `Ancora(documento, pagina)` pura, usada pela leitura, pela detecção e pela folha
- **S-824** · Aba Texto arquiva a folha que leu, não a que o campo mostra
- **S-825** · `eventFilter` por tabela, com borda, nos seis filtros que não a têm
- **S-826** · Tarefa sem pai em todos os painéis, e o fechamento espera a aba Texto
- **S-827** · A identidade do livro numa função só
- **S-828** · `AppState` tipado no `PainelDeTexto`, e o histórico aparado na leitura
- **S-829** · `DeteccaoDeFundo` leva a âncora no próprio sinal

### Fase 115 — Interpretador e documentos

- **S-830** · Python 3.13 como interpretador padrão, do `.python-version` ao `.exe`
- **S-831** · Documentos no presente do Qt, e os status que se contradizem
- **S-832** · A tabela de faixas e o `ARCHITECTURE.md` que enxergam tudo

### Fase 116 — Um pipeline só

- **S-833** · A exportação reconhece pela mesma função que os relatórios medem
- **S-834** · Decodificação restrita sem relógio
- **S-835** · Contadores de campo por campo tipado, não por frase
- **S-836** · Fonte de diagrama e rótulo de eixo numa regra só
- **S-837** · Remedição dos quatro relatórios de campo, uma vez, depois de S-833 a S-836

### Fase 117 — Treino honesto

- **S-838** · Página de campo nunca vai para o treino
- **S-839** · O regime do checkpoint guardado inteiro, e a letra que não perde informação
- **S-840** · `ArchConfig.from_version` recusa o que não conhece
- **S-841** · O dataset conta e diz o que descarta, e o nome da amostra não colide
- **S-842** · Colocação: um parser de FEN só, na fronteira
- **S-843** · O normalizador de tabuleiro sai
- **S-844** · Identidade de livro nos splits (decisão do dono: hash de conteúdo ou tabela de apelidos)
- **S-845** · `torch.load` só com `weights_only`
- **S-846** · O sal do split fixado por valor

### Fase 118 — Texto: fronteira e decisões únicas

- **S-847** · `ocr.glyph_model` chega à leitura de página
- **S-848** · `PaginaLida.de_json` na fronteira: erro único, derivado recalculado
- **S-849** · "Camada de OCR" numa regra só
- **S-850** · Cache de perfil do livro sem `id()`
- **S-851** · A folha extraída uma vez por leitura
- **S-852** · Um árbitro de confiança só
- **S-853** · Contrato do leitor de linha: `None` é "não leu", e a falha da reserva vira aviso
- **S-854** · Classificador de glifo e pré-processamento de glifo, um só para PyTorch e ONNX
- **S-855** · Tipos fechados no texto: `Literal`, `StrEnum` e `OpcoesDeLeitura`
- **S-856** · Exceções estreitas no texto, e nada cacheado que veio de exceção

### Fase 119 — Complexidade e duplicação

- **S-857** · Argumentos comuns dos 47 comandos num lugar, e `EntradaInvalida` decide o código de saída
- **S-858** · Partir `build_pgn_games` e `Trainer.prepare`
- **S-859** · Partir `detect_diagrams`, `_contour_candidates` e `classificar` em cadeias de filtros
- **S-860** · Partir `_ler_pagina_do_livro` e `linhas_do_glifo`
- **S-861** · Partir `problemas` e `fundir`
- **S-862** · Constantes de caminho e de padrão num lugar
- **S-863** · Os `main` de CLI de complexidade alta
- **S-864** · Os pares gêmeos do dryer (exportadores, diálogos, rodapés, `de_json`, `as_dict`)

### Fase 120 — Os arquivos-deus do Qt

- **S-865** · `PainelDeTexto` em cinco módulos
- **S-866** · `PainelDeEstudo` sem o motor, a análise, as táticas e o índice
- **S-867** · O bloco de resposta da janela vira decisão pura (a caminho da S-31)

### Fase 121 — Testes que medem comportamento

- **S-868** · Os 26 testes desligados: apagar ou virar item datado (decisão do dono)
- **S-869** · Guardas de importação que enxergam PyQt6
- **S-870** · Testes de texto da fonte trocados por testes de comportamento
- **S-871** · Guardas de varredura com piso, e o registro de 140 comandos como catraca
- **S-872** · Testes de "não levanta" que conferem o efeito, e tempo escalável
- **S-873** · Os sobreviventes do mutator nos seis módulos-piloto

## 6. Decisões que são do dono

| decisão | item | opções |
|---|---|---|
| D1. Arquivo do dono ilegível | S-812 | (a) copiar para `.ilegivel` e travar a gravação até o dono decidir (recomendado), (b) só travar |
| D2. Identidade do livro nos splits | S-844 | (a) hash do conteúdo do PDF, (b) tabela de apelidos declarada em `data/` |
| D3. `text/vertical.py` | S-855 | (a) ligar a S-197 no caminho da página, (b) mover para o CLI que o usa |
| D4. Os 26 testes desligados | S-868 | (a) apagar, (b) reescrever contra o leiaute atual |
| D5. Quando trocar o interpretador | S-830 | antes ou depois da remedição da S-837 |
| D6. Renomear `procedencias.py` | S-862 | (a) `origem_do_texto.py`, (b) deixar |

## 7. Como cada fase fecha

Cada item fecha com: o teste que falhou antes e passa depois, `ruff check .`, `mypy` e `pytest`
verdes num worktree, as catracas da Fase 110 sem subir e um commit que diz por que, o que mudou e
como foi provado. Itens do caminho de medição (Fase 116) só fecham com a S-837.

**Em worktree, uma falha é esperada:** `tests/test_environment.py`, porque a instalação editável
aponta para o checkout principal. Os `.pt` e o `PDF/` só existem no checkout principal, e a remedição
roda de lá, por `python -m`.

## 8. Registro desta revisão

| passo | o que se fez | por quê |
|---|---|---|
| 1 | worktree `claude/revisao-ub-mode` a partir de `origin/main` | o checkout principal tem sessões concorrentes e a `main` local estava defasada |
| 2 | `radon cc` sobre `src/` e `app_pyqt.py`, num alvo fora do `.venv` | medir complexidade sem mexer no ambiente que as outras sessões usam |
| 3 | suíte inteira sob `coverage` | o CRAP precisa da cobertura de cada função |
| 4 | dryer escrito e rodado | a ferramenta não existia; uma unidade conferida à mão antes de confiar no ranking |
| 5 | cinco auditorias em paralelo: texto, Qt, diagrama e modelo, persistência e CLI, testes e documentos | cada uma com prova por script ou leitura, marcada CONFIRMADO ou PLAUSÍVEL |
| 6 | os dois achados mais graves conferidos à mão | o cache apagado pelo `--census` e a leitura de A entrando em B |
| 7 | roadmap e spec escritos | a premissa antes do item, e um teste de aceite por item |
| 8 | três revisões independentes do texto e do código citado | cada uma procurando o que a anterior deixou passar |
