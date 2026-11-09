# Roadmap da solidez — Fases 110 a 121 (S-800 a S-910)

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
> | S-585 a S-598 | [ROADMAP_PDF_COM_PGN.md](ROADMAP_PDF_COM_PGN.md) |
> | S-599 | [PLANO_FAIXAS_REVERSAS.md](PLANO_FAIXAS_REVERSAS.md) |
> | S-601 a S-668 | [SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md) |
> | S-702, S-710 a S-712, S-715 a S-718, S-720 | [SPEC_TEXTO_PRECISO.md](SPEC_TEXTO_PRECISO.md) |
> | S-800 a S-910 | [SPEC_SOLIDEZ.md](SPEC_SOLIDEZ.md) |

## 1. O que se mediu

| medida | valor em `e8c9f64a` | instrumento |
|---|---|---|
| funções e métodos em `src/` + `app_pyqt.py` | 5.932 (um por `def`) | `radon cc` |
| funções com complexidade ciclomática ≥ 10 | 383 | `radon cc` |
| funções com complexidade ≥ 20 | 72 | `radon cc` |
| cobertura de linhas da suíte | 85,5% no total; 51,8% em `cli/` | `coverage` sobre a suíte inteira (7.383 passaram) |
| funções com CRAP ≥ 10 | 611 (176 na raiz do pacote, 135 em `qt/`, 133 em `cli/`, 105 em `text/`, 56 em `ui/`, 4 em `detection/`, 2 em `app_pyqt.py`) | crapper |
| funções com CRAP ≥ 30 | 139 | crapper |
| módulos de produção com 0% de cobertura | 3: `pdf_substituicao.py`, `ui/substituicao.py`, `ui/selecao_de_area.py` (626 instruções, sem chamador) | `coverage` |
| pares de funções com semelhança ≥ 0,8 | 65 (340 com ≥ 0,6) | dryer (Jaccard de 5-gramas de tokens normalizados) |
| `# type: ignore` | 192 (80 `arg-type`, 63 `attr-defined`) | `grep` |
| `except Exception` | 170 em `src/` (176 com `app_pyqt.py`) | `grep` |
| `Any` | 892 | `grep` |
| testes desligados por `@unittest.skip` incondicional | 26 | auditoria |
| maior arquivo | `qt/painel_de_texto.py`, 5.030 linhas, 280 métodos numa classe | `wc -l` e `ast` |

As três ferramentas que o método pede (crapper, dryer, mutator) não existiam no projeto. Elas foram escritas
para esta revisão e entram no repositório na Fase 110 (S-801 a S-803), com catraca. A complexidade é a do
`radon`; o `ruff` (C901) conta diferente e dá números menores. A cobertura foi medida num worktree, onde
`tests/test_environment.py` falha por desenho e os testes que pedem `PDF/`, `models/*.pt` ou `pgn_database/`
pulam (44 pulos); o número é um piso.

**O CRAP mais alto é de código sem chamador:** `pdf_substituicao.achar_coordenadas`, complexidade 29 e zero
de cobertura, CRAP 870 (S-881). Fora de `cli/`, nove funções de produção passam de CRAP 100 (S-886); em
`cli/`, a maioria das funções de CRAP alto são os comandos de medição `texto_*`, que só rodam à mão.

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
| `text/leitor.py` `montar` | 34 | 119 (S-861) |

## 2. As premissas atacadas

Os 117 achados não são 117 problemas. Seis premissas, cada uma segurada por vários atores, geram a maior
parte deles. O roadmap remove a premissa em vez de consertar cada ator.

1. **"Arquivo que não lê é arquivo vazio."** Sete leitores de arquivo do dono tratam o arquivo ilegível, ou
   de esquema mais novo, como começo do zero, e o gravador seguinte escreve o vazio por cima:
   `settings.json`, `revisao.json`, `placar.json`, o estudo da sala, a fila de revisão, o lote de importação
   e as folhas do caderno do texto. O cache de posições, que não é arquivo do dono mas custa uma hora, faz o
   mesmo: esvazia-se quando o conjunto de bases *parece* diferente. O incidente de 2026-10-18, com ~9.810
   linhas apagadas do cache, é esta premissa. **Remoção:** um tipo de leitura com três estados (lido,
   ilegível, de esquema futuro), e o ilegível trava a gravação (S-812, S-896); o cache nunca apaga ao abrir
   (S-806).
2. **"O resultado assíncrono é da página N."** A janela marca a leitura e a detecção só pela página, a aba
   Texto arquiva a folha do campo e não a que leu, a detecção de fundo rotula o sinal com o pedido mais
   recente, e o editor empilha o desfazer de um diagrama na pilha de outro. O livro e o diagrama podem ter
   mudado. O diagrama do livro A entra no livro B e, com Ctrl+S, no dataset de treino. **Remoção:** uma
   `AncoraDaTela(documento, pagina)` pura, capturada no pedido e conferida na chegada pela janela, pela aba
   Texto e pela detecção (S-823, S-824, S-829), e um desfazer que só empilha o diagrama selecionado (S-887).
3. **"Copiar para manter igual."** Comentários como *"Escrito igual ao de lá de propósito"* justificam uma
   cópia em vez de um import. Há o árbitro de confiança em três cópias, o pipeline de reconhecimento em duas
   (o medido e o exportado), a regra de fonte de diagrama em duas que já discordam, a camada de OCR em
   quatro, o pré-processamento de glifo em duas, a fusão da fila retomada em três chamadores, a identidade
   do livro em sete, a impressão digital da base em duas, as iniciais de peça por língua em três, e a FEN da
   posição em dois jeitos (com o roque inferido nas táticas, sem roque no lance seguinte e na estipulação).
   **Remoção:** cada decisão num módulo, importada (S-807, S-816, S-827, S-833, S-836, S-849, S-852, S-854,
   S-880 e S-901, nas Fases 111, 112, 116 e 118).
4. **"A mensagem é o dado."** Contadores publicados nos relatórios de campo contam substrings de frases em
   português (`"trocas diferentes"`, `"falta o rei"`). Reescrever a frase zera o contador. **Remoção:**
   campo tipado ou enum no resultado (S-835).
5. **"O relógio decide."** A decodificação restrita para em 0,5 s de relógio, então a mesma probabilidade
   pode sair em FEN diferente numa máquina carregada. **Remoção:** orçamento em expansões (S-834).
6. **"Quem chama sabe."** Não há borda de exceção no processo Qt, e em PyQt6 exceção em slot é `qFatal`: a
   janela some sem log. O projeto pôs `try` slot por slot. O mesmo vale para o processo de trabalho que
   isola o MuPDF: duas quedas e a página perigosa passa a rodar dentro da janela. **Remoção:** um
   `sys.excepthook` no `main` (S-800), e a página que derruba o leitor vira erro, nunca chamada em linha
   (S-874).

## 3. Glossário

| termo | quer dizer |
|---|---|
| **âncora da tela** | o par `(documento, página)` em que um pedido assíncrono foi feito (`AncoraDaTela`); o resultado só vale se a tela ainda está na mesma âncora. Não confundir com a `Ancora(documento, pagina, diagrama)` do estudo |
| **arquivo do dono** | dado que o programa não sabe refazer: `settings.json`, `revisao.json`, `placar.json`, o estudo, a fila de revisão, o lote, as folhas do caderno, os rótulos |
| **leitura travada** | estado de um arquivo do dono que não leu, ou que é de esquema futuro; o programa segue em memória e recusa gravar por cima |
| **camada de arquivo / camada efetiva** | o que está gravado em `settings.json` / o que vale agora, depois das variáveis `CVOFF_*`; só a primeira é gravada |
| **impressão digital da base** | nome e tamanho de cada base de partidas, inclusive membro de `.zip`; decide se o cache e o índice ainda valem |
| **caminho de medição** | a corrente que os quatro relatórios de campo exercitam (`OcrService.recognize_page`); em módulos, é o fecho de medição |
| **regime** | a configuração de aumento de dados com que um checkpoint foi treinado; a letra (`augh`, `augx`) é o nome curto dela |
| **colocação** | as 64 casas de um tabuleiro, peça ou vazio; o tipo que substitui a string de FEN dentro do programa (S-842) |
| **catraca** | teste que guarda uma contagem e falha quando ela sobe; descer é sempre permitido e baixa o teto |
| **CRAP** | `cc² × (1 − cobertura)³ + cc` por função; acima de 10 a função pede teste ou divisão |
| **crapper, dryer, mutator** | as três ferramentas do método: CRAP por função, pares de funções quase iguais, e mutantes que a suíte deixa viver (S-801 a S-803) |
| **teste de caracterização** | teste que grava o que o código faz hoje, antes de uma refatoração, e confere que depois faz igual |
| **`TarefaAdiada`** | tarefa de teste que só entrega o resultado quando o teste manda; é como se testa "a tela mudou durante a tarefa" (S-805) |
| **fecho de medição** | os módulos que `field_eval.measured_modules()` acha por importação (36 com o OCR desligado, como nos quatro relatórios; 48 com `--ocr glifo`, que traz `text/`); `measurement_fingerprint()` grava o digest deles nos relatórios |
| **chave do livro** | `ChaveDoLivro`, a identidade de um livro pelo caminho (S-827); é o `documento` da âncora da tela |
| **estrato** | a classe de um livro do ouro pela origem da camada de texto (S-702); muda com a regra da S-849 só por decisão do dono (D9) |
| **portão** | a confiança mínima com que uma posição lida é aceita sem revisão (`gate_confidence`) |
| **camada (de texto)** | o texto embutido no PDF; não confundir com a camada de arquivo da configuração |
| **folha / página** | a folha é a página do livro vista pela aba Texto; o número de folha é o índice + 1 |
| **figurina** | o símbolo de peça impresso no lugar da letra (♘ por N) |
| **ouro-dev / ouro-teste** | os conjuntos de folhas com texto conferido das Fases 100 a 107 (S-702); o teste é congelado |
| **régua da prosa** | a medida de erro de caractere só na prosa, separada da notação (Fases 100 a 107) |

## 4. A ordem e o porquê

A ordem segue "faça primeiro o que ajuda todas as fases seguintes" e, depois, o risco para o dado do dono.

| fase | tema | itens | por que nesta posição |
|---|---|---|---|
| 110 | Alavancas | S-800 a S-805, S-874, S-906 | toda fase seguinte usa a borda (queda vira log), as catracas e a `TarefaAdiada`; a S-874 é a premissa 6 do lado do processo de trabalho |
| 111 | Caches e índices que não se apagam sozinhos | S-806 a S-809 | é o defeito que já custou uma hora de varredura (2026-10-18), e um `--census` o repete |
| 112 | Arquivos do dono e a identidade do livro | S-810 a S-817, S-827, S-878, S-892, S-896, S-897, S-905, S-908 | a mesma premissa nos arquivos do dono; a S-827 (a identidade do livro) e a S-812 (o tipo que todos usam) vêm primeiro |
| 113 | Escritas idempotentes e saídas corretas | S-818 a S-822, S-876, S-877, S-879, S-899 | rodar duas vezes ou cair no meio termina no mesmo estado; e o que sai (PGN, EPUB, DOCX, legenda casada, solução de tática) é o que o livro diz |
| 114 | A tela e o editor sabem de onde veio cada resultado | S-823 a S-826, S-828, S-829, S-875, S-882, S-883, S-887, S-888, S-891, S-893, S-894, S-910 | contamina o dataset em silêncio; depende da `TarefaAdiada` (S-805) |
| 115 | Interpretador, empacotamento e documentos | S-830 a S-832, S-884, S-885, S-907, S-909 | o 3.10 saiu de suporte em outubro de 2026 e vai dentro do `.exe` |
| 116 | Um pipeline só | S-833 a S-837, S-843, S-880 | os itens que mudam número no caminho de medição, explicados juntos na S-837; os que só tocam o fecho remedem no próprio commit (§7) |
| 117 | Treino honesto | S-838 a S-842, S-844 a S-846, S-889, S-890, S-900 | página de campo no treino invalida o número publicado |
| 118 | Texto: fronteira e decisões únicas | S-847 a S-856, S-898, S-901 a S-904 | coordenada com as Fases 100 a 107, que mexem nos mesmos arquivos |
| 119 | Complexidade e duplicação | S-857 a S-864, S-881 | depois das fases que mudam comportamento, para refatorar código já certo |
| 120 | Os arquivos-deus do Qt | S-865 a S-867 | depois da 114, que fecha os defeitos de tarefa que a divisão carrega |
| 121 | Testes que medem comportamento | S-868 a S-873, S-886, S-895 | os sobreviventes do mutator e a limpeza que sobrou |

**O que não está aqui.** A precisão da prosa é das Fases 100 a 107
([ROADMAP_TEXTO_PRECISO.md](ROADMAP_TEXTO_PRECISO.md)). Quando um achado desta revisão já tinha item lá, ele
não ganhou número novo: a regra 5 da fusão é da S-721, o modo bloco da S-726, o cache do Tesseract da S-725,
a procedência por intervalo da S-722. A S-31 (janela abaixo de 600 linhas) continua aberta no
[ROADMAP.md](ROADMAP.md), e a S-867 trabalha para ela.

## 5. Os itens

Os títulos são os da spec, na ordem em que os itens devem ser feitos dentro de cada fase.

### Fase 110 — Alavancas

- **S-800** · Borda de exceção do processo, e o estado da sessão gravado antes da queda
- **S-874** · Página que derruba o processo de trabalho nunca roda no processo da janela
- **S-906** · O processo de trabalho tem prazo, e o fechamento o encerra
- **S-801** · crapper no repositório, com catraca de CRAP por função
- **S-802** · dryer no repositório, com catraca de pares duplicados
- **S-803** · mutator no repositório, com piloto em seis módulos puros
- **S-804** · Catraca de tipos, e as contagens que só descem
- **S-805** · Infraestrutura de teste

### Fase 111 — Caches e índices que não se apagam sozinhos

- **S-807** · Uma impressão digital de base só, que enxerga membro de `.zip`
- **S-806** · `open_store` nunca esvazia o cache
- **S-808** · URI de SQLite por `Path.as_uri()`, e versão ilegível não apaga o índice
- **S-809** · `--build-index` com subconjunto não apaga as outras bases

### Fase 112 — Arquivos do dono e a identidade do livro

- **S-827** · A identidade do livro numa função só
- **S-812** · Leitura travada
- **S-905** · Arquivo do usuário em BOM, ANSI ou UTF-16 abre, e `UnicodeDecodeError` não escapa
- **S-810** · Booleano estrito e faixas numéricas no `settings.json`
- **S-811** · Camada de arquivo e camada efetiva
- **S-813** · Baralho de revisão e placar sob a leitura travada
- **S-814** · Sala de estudo: partida que não lê sobrevive à gravação
- **S-815** · Fila de revisão: FEN corrigida sobrevive ao revarrer
- **S-816** · `cvoff-scan` retomado preserva as pendências
- **S-817** · Quarentena de rótulos em conflito sempre desfazível
- **S-878** · Lote e Galeria não confundem dois livros de mesmo nome
- **S-892** · "Aplicar aos vizinhos" não troca a partida que a pessoa escolheu
- **S-896** · Folha do caderno que não abre não é relida por cima
- **S-897** · O caderno acha o seu livro e a sua trava
- **S-908** · Hora gravada com fuso, e o rascunho mais novo não é apagado

### Fase 113 — Escritas idempotentes e saídas corretas

- **S-818** · Exportação de PGN atômica, e sem `.review.pgn` de rodada anterior
- **S-819** · Retomada de exportação sem perda de campo
- **S-820** · Importação de imagens idempotente
- **S-821** · PDF pesquisável idempotente e atômico
- **S-822** · Catraca de escrita: nada em `src/` grava fora do `atomic_io` sem exceção declarada
- **S-876** · Cabeçalho livre inválido não derruba a exportação do livro
- **S-877** · Caractere de controle não estraga o EPUB nem o DOCX
- **S-879** · Legenda com lance inexistente cai no casamento pela posição
- **S-899** · Solução de tática com número do meio da partida fecha

### Fase 114 — A tela e o editor sabem de onde veio cada resultado

- **S-823** · `AncoraDaTela(documento, pagina)` pura
- **S-824** · Aba Texto arquiva a folha que leu
- **S-825** · O `eventFilter` do `PainelDeTexto` por tabela
- **S-826** · Tarefa sem pai em todos os painéis
- **S-828** · `AppState` tipado no `PainelDeTexto`, e o histórico aparado na leitura
- **S-829** · `DeteccaoDeFundo` leva a âncora no próprio sinal
- **S-887** · O Ctrl+Z do editor nunca aplica a posição de outro diagrama
- **S-888** · Desfazer volta a posição e a procedência juntas
- **S-893** · O campo de FEN aplica também a vez que mostra
- **S-894** · O PGN do livro que chega atrasado não apaga a correção em andamento
- **S-891** · As setas andam na direção da tela com o tabuleiro virado
- **S-875** · O motor que caiu é reaberto na próxima análise
- **S-882** · "Segunda opinião remota" só aparece quando tem quem a use
- **S-883** · O leitor tsoj não troca a pasta corrente fora da trava
- **S-910** · Número com vírgula e ordem alfabética pela mesma régua da tela

### Fase 115 — Interpretador, empacotamento e documentos

- **S-830** · Python 3.13 como interpretador padrão
- **S-831** · Documentos no presente do Qt, e os status que se contradizem
- **S-832** · A tabela de faixas e o `ARCHITECTURE.md` que enxergam tudo
- **S-884** · No `.exe`, o OCR que falta é dito na janela
- **S-885** · CI com permissão mínima e ações fixadas
- **S-907** · Arrastar um PDF para o ícone abre o livro
- **S-909** · O arquivo de log não leva o nome do usuário

### Fase 116 — Um pipeline só

- **S-843** · O normalizador de tabuleiro sai
- **S-833** · A exportação reconhece pela mesma função que os relatórios medem
- **S-834** · Decodificação restrita sem relógio
- **S-835** · Contadores de campo por campo tipado, não por frase
- **S-836** · Fonte de diagrama e rótulo de eixo numa regra só
- **S-880** · O lance seguinte e a estipulação jogam com o direito de roque
- **S-837** · Remedição dos quatro relatórios de campo

### Fase 117 — Treino honesto

- **S-838** · Página de campo nunca vai para o treino
- **S-839** · O regime do checkpoint guardado inteiro
- **S-840** · `ArchConfig.from_version` recusa o que não conhece
- **S-841** · O dataset conta e diz o que descarta
- **S-842** · Colocação: um parser de FEN só, na fronteira
- **S-889** · A posição do PGN do livro tem rota própria no rótulo
- **S-890** · Posição que nenhum lado a jogar torna legal é fatal
- **S-844** · Identidade de livro nos splits
- **S-845** · `torch.load` só com `weights_only`
- **S-846** · O sal do split fixado por valor
- **S-900** · O split por livro do texto não aborta o treino

### Fase 118 — Texto: fronteira e decisões únicas

- **S-854** · Classificador de glifo e pré-processamento, um só para PyTorch e ONNX
- **S-847** · `ocr.glyph_model` chega à leitura de página
- **S-848** · `PaginaLida.de_json` na fronteira
- **S-849** · "Camada de OCR" numa regra só
- **S-850** · Cache de perfil do livro sem `id()`
- **S-851** · A folha extraída uma vez por leitura
- **S-852** · Um árbitro de confiança só
- **S-853** · Contrato do leitor de linha: `None` é "não leu"
- **S-855** · Tipos fechados no texto
- **S-856** · Exceções estreitas no texto e no perfil de cor
- **S-898** · Apagar um bloco inteiro conta como correção
- **S-901** · Letras de peça por língua e meia-risca numa constante só
- **S-902** · A busca com figurina não troca peão por bispo
- **S-903** · O léxico do livro grava e confere com a mesma dobra de caixa
- **S-904** · Mudar a caixa devolve a seleção certa

### Fase 119 — Complexidade e duplicação

- **S-857** · Argumentos comuns dos 47 comandos num lugar
- **S-858** · Partir `build_pgn_games` e `Trainer.prepare`
- **S-859** · Partir a detecção em cadeias de filtros
- **S-860** · Partir `_ler_pagina_do_livro` e `linhas_do_glifo`
- **S-861** · Partir `problemas` e `fundir`
- **S-862** · Constantes de caminho e de padrão num lugar
- **S-863** · Os `main` de CLI de complexidade alta
- **S-864** · Os pares gêmeos do dryer
- **S-881** · A substituição de diagrama no PDF: ligar ou retirar

### Fase 120 — Os arquivos-deus do Qt

- **S-865** · `PainelDeTexto` em cinco módulos
- **S-866** · `PainelDeEstudo` sem o motor, a análise, as táticas e o índice
- **S-867** · O bloco de resposta da janela vira decisão pura

### Fase 121 — Testes que medem comportamento

- **S-868** · Os 26 testes desligados
- **S-869** · As dezesseis guardas "sem tkinter" saem
- **S-870** · Testes de texto da fonte trocados por testes de comportamento
- **S-871** · Guardas de varredura com piso, e o registro de comandos como catraca
- **S-872** · Testes de "não levanta" que conferem o efeito, e tempo escalável
- **S-873** · Os sobreviventes do mutator nos seis módulos-piloto
- **S-886** · As funções de produção com CRAP acima de 100 ganham teste
- **S-895** · A guarda de órfãos enxerga módulo sem `__all__`

## 6. Decisões que são do dono

Na spec elas aparecem como "D1 da solidez" a "D9 da solidez", para não confundir com as decisões D1 a D9 do
[ROADMAP_TEXTO_PRECISO.md](ROADMAP_TEXTO_PRECISO.md).

| decisão | item | opções |
|---|---|---|
| D1. Arquivo do dono ilegível | S-812 | (a) copiar para `.ilegivel` e travar a gravação até o dono decidir (recomendado), (b) só travar |
| D2. Identidade do livro nos splits | S-844 | (a) hash do conteúdo do PDF, (b) tabela de apelidos declarada em `data/` |
| D3. `text/vertical.py` | S-855 | (a) ligar a S-197 no caminho da página, (b) mover para o CLI que o usa |
| D4. Os 26 testes desligados | S-868 | (a) apagar, (b) reescrever contra o leiaute atual |
| D5. Piso do interpretador | S-830 | (a) piso 3.13, e o CI só em 3.13 (a troca vem antes da S-837, pela ordem das fases); (b) piso 3.11, com uma perna 3.11 no CI |
| D6. Renomear `procedencias.py` | S-862 | (a) `origem_do_texto.py`, (b) deixar |
| D7. A substituição de diagrama no PDF | S-881 | (a) ligar o painel e testar, (b) retirar os três módulos |
| D8. O `onnxruntime` no `.exe` | S-884 | (a) entra no bundle, (b) fica fora e a janela diz por quê |
| D9. Livro que muda de estrato pela regra única da camada de OCR | S-849 | (a) aceitar a regra, (b) manter o estrato antigo com nota |

## 7. Como cada fase fecha

Cada item fecha com: o teste que falhou antes e passa depois, `ruff check .`, `mypy` e `pytest` verdes num
worktree, as catracas da Fase 110 sem subir e um commit que diz por que, o que mudou e como foi provado.
**Todo commit que edita um módulo do fecho de medição remede os quatro relatórios de campo** (S-218), em
qualquer fase: são os 36 módulos de `field_eval.measured_modules()` com o OCR desligado, entre eles
`atomic_io`, `board_detection`, `checkpoint`, `config`, `cor_por_livro`, `dataset`, `decode`, `detection/*`,
`djvu_*`, `engine`, `estipulacao`, `fen_utils`, `field_eval`, `inference`, `labels`, `lance_seguinte`,
`model`, `ocr`, `ocr_caption`, `orientation`, `pdf_io`, `pdf_text`, `preprocess`, `procedencias`,
`semantics`, `service`, `settings`, `splits` e `cli/field`. Fora da Fase 116, os números têm de voltar
idênticos; na Fase 116, a S-837 explica os que mudam. `text/` fica fora do fecho dos quatro relatórios; com
`--ocr glifo` ele entra.

**Em worktree, uma falha é esperada:** `tests/test_environment.py`, porque a instalação editável aponta para
o checkout principal. Os `.pt` e o `PDF/` só existem no checkout principal, e a remedição roda num worktree
limpo, lendo-os do checkout principal por caminho, por `python -m`.

## 8. Registro desta revisão

| passo | o que se fez | por quê |
|---|---|---|
| 1 | worktree `claude/revisao-ub-mode` a partir de `origin/main` | o checkout principal tem sessões concorrentes e a `main` local estava defasada |
| 2 | `radon cc` sobre `src/` e `app_pyqt.py`, num alvo fora do `.venv` | medir complexidade sem mexer no ambiente que as outras sessões usam |
| 3 | suíte inteira sob `coverage` | o CRAP precisa da cobertura de cada função |
| 4 | dryer escrito e rodado | a ferramenta não existia; uma unidade conferida à mão antes de confiar na ordenação |
| 5 | cinco auditorias em paralelo: texto, Qt, diagrama e modelo, persistência e CLI, testes e documentos | cada uma com prova por script ou leitura, marcada CONFIRMADO ou PLAUSÍVEL |
| 6 | os dois achados mais graves conferidos à mão | o cache apagado pelo `--census` e a leitura de A entrando em B |
| 7 | roadmap e spec escritos | a premissa antes do item, e um teste de aceite por item |
| 8 | suíte sob `coverage` concluída: 7.383 passaram, 1 falha esperada (`test_environment`), 44 pulos | o CRAP, e os três módulos de produção com 0% |
| 9 | revisão 1: dois verificadores conferiram cada citação de S-800 a S-873 contra o código, e um terceiro auditou os módulos que as cinco auditorias não cobriram | 139 correções de linha, número e citação; quatro testes "que falham primeiro" que passariam hoje (S-806, S-810, S-845, S-854); a S-837 com a causa invertida; 13 itens novos (S-874 a S-886) |
| 10 | piloto do mutator num worktree separado: 50 mutantes em `splits.py`, `fen_utils.py` e `decode.py` | 68%, 58% e 74% só com o arquivo homônimo; os dois sobreviventes de `decode.py` conferidos morreram noutros arquivos, então a S-803 roda os testes que importam o módulo |
| 11 | revisão 2: um revisor da coerência e do método, e dois caçadores (camada `ui/` com os painéis Qt restantes, e os módulos secundários de `text/`) | a regra de remedição corrigida (o fecho tem 36 módulos e é tocado fora da Fase 116), dependências reordenadas (a S-827 abre a Fase 112, a S-843 abre a 116, a S-854 abre a 118), títulos regerados da spec, glossário e decisões completados, a S-869 reduzida a subtração e a S-825 sem `try` novo; 18 itens novos (S-887 a S-904), entre eles o Ctrl+Z que aplica a posição de outro diagrama e a folha do caderno relida por cima da correção |
| 12 | revisão 3: um verificador conferiu contra o código, rodando os testes, tudo o que a revisão 2 escreveu; um leitor de olhos novos conferiu os dois documentos por script; uma varredura transversal procurou padrões no programa inteiro | ~90 correções (16 lugares de `Tarefa` com pai, e não 14; o teste da S-834 refeito; a correção de UNC da S-808, que a proposta anterior quebraria; o fecho com `--ocr glifo`); 6 itens novos (S-905 a S-910), entre eles o `settings.json` em ANSI que impede o `.exe` de abrir, o processo de trabalho sem prazo e o PDF arrastado para o ícone |
