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
> | S-500 a S-506, S-527 a S-580 | [SPEC_SUITE.md](SPEC_SUITE.md) |

Cada item tem **Problema** (com `arquivo:linha` do estado em `0cf5492`), **Solução**, **Critério de
aceite**, **Testes** e **O que o crítico recusou** -- o registro das rodadas em que a fotografia da
janela foi comparada lado a lado com o ChessBase e o Lichess, e o que faltava em cada uma.

---

## S-527 · A barra da sala de estudo agrupada por tarefa, com ícones vetoriais e rótulo curto — ✅ **implementada em 2026-09-04**

### Problema

`qt/painel_de_estudo.py:257` (`_barras`), `:342` (`_barra_de_fora`) e `:372` (`_entrada_e_saida`)
montavam três `BarraFluida` com 28 botões de texto (31 com motor) e um `QCheckBox` (`:285`), sem
ícone, sem separador e sem hierarquia. **Medido em 2026-09-04, a 1400×950** (a aba Estudo tem 714 px
de largura): as três barras quebravam em **cinco fileiras** (2 + 1 + 2) e ocupavam **154 px** acima
do divisor; o tabuleiro desenhava com 442 px de lado. Na fotografia `fotos/base/01_Estudo.png` são
quatro fileiras visíveis mais a linha da caixa. "Apagar variante" ficava a um botão de "Símbolo", e
"Carregar OCR atual" -- o único primário -- no meio de vinte e sete iguais.

Um segundo defeito apareceu na medição, e não estava no roadmap: **o clique de mouse em "Treinar"
não ligava o treino**. Um `QPushButton` marcável alterna `checked` antes de emitir `clicked`, e
`alternar_treino` inverte `isChecked()` de novo -- o clique ligava e desligava no mesmo gesto, e só o
menu e a paleta (que chamam o método sem botão) treinavam. Vale igual para "Recorte" e "Análise
contínua"; "Dobrar" escapava porque deriva o estado da lista de dobradas.

### Solução

**Uma decisão pura, `ui/barra_da_sala.py`.** A tabela `ACOES`: trinta ações (os 28 comandos de
`COMANDOS_DA_ABA` menos os quatro de navegação da S-517, mais o interruptor `SEGUIR_OCR` e o
agrupador `EXPORTAR_ESTUDO`), cada uma com **grupo por tarefa** (Posição, Variante, Livro, Base,
Motor, Exportar, Treino), nome do ícone, se é **principal** ou vai para o "Mais", **prioridade**
entre as principais, se é interruptor, e a explicação da dica. Rótulo curto, rótulo longo, papel e
tecla **não são reescritos**: vêm de `comandos` e `atalhos`; só o que o catálogo não tem ("Seguir
OCR", "Exportar", "Mais") declara texto ali, uma vez. Três funções puras: `modo(vazio, treinando)` →
`grupos_desligados(modo)` (sem estudo: Variante e Exportar cinza; treinando: Variante cinza);
`dica_de(acao)` (rótulo longo, explicação, `Tecla: X`); e `cabem(itens, disponivel, reserva, ...)`.

**O ícone não entra pelo catálogo, e isto foi decidido contra a letra do pedido.** O item pedia
"ícones desenhados por `QPainter` em `qt/icones.py`"; o projeto já tem o mecanismo -- traço declarado
em `ui/icones.py`, desenhado em PIL, entregue como `QIcon` por `qt/icones.py` (S-220/S-503) -- e um
segundo desenhador para a mesma família seria a divergência que a S-501 fechou. Os 24 traços novos
moram em `icones.ICONES_DA_SALA`, um **segundo dicionário** e não mais chaves em `ICONES`, porque
`medidas_da_fita.grupos()` põe na fita da janela todo comando do catálogo com `icone`: dar ícone aos
trinta pelo catálogo despejaria os trinta no cromo da janela ao lado de "Abrir PDF". Quatro reusam
traços existentes (`salvar`, `abrir_pdf`, `exportar_pgn`, `aplicar_fen`); os três formatos de
exportação não têm traço porque não têm botão.

**O widget, `qt/barra_da_sala.py`.** Uma fila de `QToolButton` chatos (`ToolButtonTextBesideIcon`,
ícone de 16 px), separador `QWidget#separador-da-fila` entre grupos, "Exportar ▾" com `QMenu` dos
três formatos, "Mais ▾" com `QMenu` seccionado por grupo. Cada ação da tabela é **uma `QAction`**,
que é ao mesmo tempo o botão da fila e o item do menu: texto, ícone, marcado e habilitado são um
estado só. É isso que deixa o resto do painel intacto -- `btn_dobra`, `btn_recorte`, `btn_treino`,
`btn_continua` e `seguir_ocr` passam a ser essas `QAction`s, e `setChecked`/`setText`/`setEnabled`/
`isChecked` são os mesmos nomes. Nenhum slot muda; `executar` ganha uma linha para
`METODOS_PROPRIOS`. `lbl_simbolo` e `lbl_placar`, que acompanhavam os botões "Símbolo" e "Treinar",
vão para a faixa sob o tabuleiro, ao lado do lance corrente e da vez.

**Quem cabe é decidido, não sofrido.** A 714 px não cabem quinze botões com rótulo, e a S-151 mediu o
que acontece quando uma barra esconde sem avisar. `cabem` recebe as larguras medidas e devolve, por
prioridade e em prefixo, quem fica; o que não coube **vai para o "Mais"** (antes das secundárias,
sob o cabeçalho do grupo) e volta quando a janela alarga. O `resizeEvent` só mede e pergunta.
**E a barra declara o próprio mínimo**: `minimumSizeHint` responde a largura do "Mais", não a soma
dos botões visíveis, que é o padrão do `QWidget`. Sem isso o pai nunca a estreitava -- medido na
primeira montagem: pedida a 500 px, a fila ficava com 1.387, e `cabem` decidia sobre uma largura
que não mudava. A fronteira com a S-517 também ficou declarada uma vez: `NAVEGACAO` é a tupla
ordenada que `_barra_de_navegacao` percorre, e não mais quatro literais no painel.

**O interruptor alterna uma vez.** Para os quatro marcáveis do catálogo, o `triggered` da `QAction`
devolve o estado que o clique alternou e chama o método, que alterna -- como faz para o menu.
`SEGUIR_OCR` é o contrário (o método lê o estado) e usa `toggled`, como o `QCheckBox` fazia. O
papel chega ao `QToolButton` por regras novas em `qt/tema.py`: primário com face, destrutivo pela
cor (letra e traço em `BOTAO_DESTRUTIVO`; dois blocos vermelhos sólidos numa fila chata pediriam
cuidado o tempo todo), e `:disabled` cinza, pela mesma razão do botão comum.

### Critério de aceite

- A barra do topo é **uma fila** em qualquer largura. ✅ **Medido a 1400×950: 154 px → 38 px**
  acima do divisor (−116 px, 75%); a fila tem 32 px. O tabuleiro foi de 442 para 450 px de lado --
  nesta janela ele é limitado pela **largura** da coluna (484 px), não pela altura, e o que a barra
  devolveu vira coluna livre sob o tabuleiro; ao arrastar o divisor para a direita, a altura deixa de
  ser o teto. Na fila cabem, a 714 px: Carregar OCR atual · Seguir OCR | Promover · Apagar variante
  · Símbolo | Mais ▾. Os outros nove principais estão no "Mais"; a 900 px de aba são oito na fila,
  a 1200 onze, e os catorze (quinze com motor) só a partir de 1.647 px -- a soma das larguras
  medidas, que é o que `largura_para_todas()` devolve. Remedido em 2026-09-04 depois da correção
  do mínimo (abaixo): os mesmos 38 px, 32 px e 450 px.
- Separador entre grupos; ícone vetorial em toda ação que pode virar botão; rótulo curto do
  catálogo ao lado do ícone; dica com rótulo longo, explicação e tecla. ✅
- `.md/.html/.rtf` viram "Exportar ▾"; a caixa "Seguir OCR selecionado" vira ação marcável no
  grupo Posição, nascendo marcada como antes. ✅
- Sem estudo, Variante e Exportar ficam cinza; treinando, Variante fica cinza; Posição e Treino
  nunca desligam. A condição própria da dobra (S-516) e do recorte (S-347) soma-se à do grupo. ✅
- Nenhum slot muda: `comandos.acoes_fora_do_catalogo(COMANDOS_DA_ABA)` continua vazio, a tabela
  cobre a aba inteira menos a navegação, e disparar cada `QAction` chama `executar` com o nome. ✅
- O catálogo continua sem `icone` para os comandos da sala além dos quatro de navegação: a fita da
  janela não muda. ✅ `tests/test_ui_icones.py` inalterado (dezenove em `ICONES`).
- O clique de mouse em "Treinar" liga o treino. ✅ (Defeito pré-existente, fechado de graça.)
- `qt/janela.py` não é tocado; `qt/painel_do_pdf.py` é da S-528. ✅

### Testes

- `tests/test_ui_barra_da_sala.py` (puro): cobertura nos dois sentidos contra `COMANDOS_DA_ABA`;
  método para toda ação e nenhum para o agrupador; ids únicos, nenhum grupo vazio, prioridades
  únicas; principal/Mais/submenu como partição; rótulo e papel lidos do catálogo; dica com tecla;
  quem alterna no método; ponte com `ICONES_DA_SALA` nos dois sentidos, caixa `0..100`, e o catálogo
  sem ícone novo; os três modos; `cabem` por prioridade, em prefixo, com o separador na conta e o
  "Mais" nunca fora; o módulo não importa toolkit.
- `tests/test_qt_barra_da_sala.py`: `QAction` com ícone e dica para toda ação; fila única, estreitar
  manda para o "Mais" e alargar devolve; texto ao lado do ícone; "Exportar ▾" com os três; disparo
  chega ao `executar` com o nome (afirmado pelo efeito, e não por `patch` depois do `connect`); o
  interruptor do catálogo devolve o estado antes de chamar; papel no botão e regras na folha; modo e
  condição se somam; sem motor não há grupo. No painel: o **clique de mouse** em "Treinar" liga uma
  vez; toda ação chega ao método; cinza sem estudo e treinando; os nomes antigos são as ações.
- As guardas gerais: `barra_da_sala.py` entrou em `SEM_TKINTER` (`test_editor_model`); em
  `test_ui_orfaos.SEM_CHAMADOR` entraram, com motivo, a tabela `ACOES`, os três valores de `modo`,
  o agrupador `EXPORTAR_ESTUDO` e `ICONES_DA_SALA`; `principais`/`secundarias` ganharam chamador no
  widget, `NAVEGACAO` no painel, e `EXPORTAR` e `tracos_de` saíram do `__all__` (uso interno).
- `tests/test_qt_painel_de_estudo.py::ArranjoTests`: "três fileiras" virou "uma fila e nenhuma
  `BarraFluida` no topo"; a navegação continua sob o tabuleiro (agora procurando `QPushButton`).

### O que o crítico recusou

_a preencher pelo crítico_

## S-528 · A barra do painel do PDF na mesma gramática, e a página com mais área — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-529 · O painel do motor: barra de avaliação vertical, linhas MultiPV clicáveis, profundidade — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-530 · O cabeçalho da partida (jogadores, Elo, evento, data, resultado) visível e editável — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-531 · Ler `.pgn.gz`, `.pgn.bz2` e `.zip` de PGN sem descompactar para o disco — ✅ **implementada em 2026-09-04**

### Problema

`games_db.py:189` listava a pasta com `pasta.glob("*.pgn")`: um `.pgn.gz`, um `.pgn.bz2` ou um
`.zip` com PGN dentro eram invisíveis, e a única saída era descompactar -- uma gigabase de 8,6 GB
ocupa ~1,5 GB em `.gz`, e pedir 7 GB de disco por um arquivo que a pessoa já tem é o que este item
existe para não pedir. Os `open()` de PGN estavam espalhados em quatro lugares e com três
decodificações diferentes: `games_db.py:543` (`open("r", encoding="utf-8-sig", errors="replace")`,
a busca por nome), `:726` e `:769` (`open("rb")` com `linha.decode("utf-8", "replace")` nos pedaços
da busca por posição), `games_index.py:183` e `:335` (o índice e a consulta por offset). Nenhum
deles registrava a decisão de codificação, e `Kieseritzky` em Latin-1 -- o comum em PGN antigo e em
boa parte do que circula em `.zip` -- saía `Kieseritzk�` na tela: a conferência de sobrenomes
ainda casava, mas o nome mostrado vinha com o losango.

### Solução

**Um leitor, `games_db.FluxoDePGN`/`abrir_pgn_bytes`/`abrir_pgn`.** O arquivo físico é aberto em
bytes e envolvido num `_ArquivoContado`, que conta o que saiu do disco; por cima dele vai
`gzip.GzipFile`, `bz2.BZ2File`, `zipfile.ZipFile(...).open(membro)` ou, se o pacote opcional
`zstandard` estiver instalado, um `BufferedReader` sobre `ZstdDecompressor().stream_reader`. O
resto do módulo não sabe de onde as linhas vieram: `tell()`/`seek()` são do **fluxo
descompactado**, então um offset gravado no índice vale igual para o mesmo arquivo comprimido, e
`bytes_lidos` é a posição **comprimida** -- a única comparável ao tamanho do arquivo, e por isso a
régua do progresso da S-532. `LinhasDePGN` é o mesmo fluxo em texto, linha a linha.

**Um membro de `.zip` é uma base por si**, com um `Path` da forma `pasta/base.zip/dentro/x.pgn`
que não existe no disco -- e é isso que o distingue de um arquivo (`_membro_de_zip`). `nome_da_base`
devolve `base.zip/dentro/x.pgn`, que é a identidade no índice: dois `.zip` podem ter um `games.pgn`
cada, e um `games.pgn` solto ao lado. `existe_base`, `tamanho_da_base` (bytes **no disco**,
`compress_size` para o membro) e `arquivo_fisico` são o `is_file()`/`stat()` que também valem para
o membro; os `is_file()` de `scan_by_positions`, `lookup_pair` e `cli/games._bases` passaram a
usá-los. `database_paths` enxerga `EXTENSOES_DE_BASE` sem ligar para caixa, expande cada `.zip` nos
seus membros `.pgn`, e deixa `.pgn.zst` de fora com aviso quando não há `zstandard` -- listar o que
não se sabe abrir seria uma base que falha na primeira busca.

**A decisão de codificação, em `decodificar_linha` e registrada no docstring dela.** UTF-8 estrito
primeiro (é o caminho rápido em C, e custa o mesmo que `replace` numa linha válida); só a linha que
falha paga a segunda decodificação, em **cp1252** e não latin-1, porque é o que o Windows gravou: as
aspas tipográficas e o travessão dos comentários são controle em latin-1. Por linha e não por
arquivo, porque a gigabase desta máquina mistura as duas coisas no mesmo `.pgn`. A marca de bytes
(`_BOM`) cai antes. Todo `open()` de PGN do projeto passa por aqui: `_collect_players`,
`_scan_positions_chunk`, `build_index`, `_read_game_at`.

**O preço, dito em `EXTENSOES_DE_BASE`.** Um fluxo comprimido não tem `seek` barato: voltar é
recomeçar do zero. `chunk_bounds` trata a base comprimida como **um pedaço só**, `(0, SEM_FIM)` --
ela ocupa um processo enquanto os outros repartem as soltas --, e `lookup_pair` lê os offsets em
**ordem crescente** para pagar uma descompactação por consulta. Quem consulta muito, descompacta;
quem guarda, comprime. O programa aceita os dois.

### Critério de aceite

- `database_paths` lista `.pgn`, `.pgn.gz`, `.pgn.bz2` e cada membro `.pgn` de um `.zip`, em ordem
  por nome; o `.txt` de dentro do `.zip` fica de fora; `.pgn.zst` só com `zstandard`. ✅
- As linhas saem **idênticas** venham de onde vierem, e a pasta fica como estava depois de ler:
  nada é gravado no disco. ✅
- A busca por nome e a busca por posição leem a base comprimida; a comprimida é um pedaço só. ✅
- Um offset do fluxo descompactado leva à mesma partida no `.bz2` que no arquivo solto. ✅
- `bytes_lidos` é menor que o descompactado e não passa do tamanho do arquivo. ✅
- Linha em cp1252 sai sem losango; UTF-8 continua UTF-8; a BOM cai. ✅
- `.zip` ilegível avisa e fica de fora, sem derrubar a listagem. ✅
- **Medido em 2026-09-04**, `Endgame_Study_Database_VI_...pgn` (62 MB, 93.839 partidas)
  comprimido em `.gz` (17,9 MB): índice do zero em 3,4 s contra 7,6 s solto (este último com o `tracemalloc` ligado, que é o que o deixa mais lento; o `.gz` não custa mais do que o solto); a consulta
  por nome numa base `.gz` paga a descompactação até o offset (192 ms) contra
  2 ms na solta. É o preço registrado acima, e é por isso que a régua de progresso é a
  comprimida.

### Testes

- `tests/test_games_db.py::LeitorDePGNTests`: as quatro formas e o membro do `.zip` na listagem;
  linhas iguais; nada gravado no disco; busca por nome no `.gz`; busca por posição no membro do
  `.zip` num pedaço só; bytes lidos são os do disco; `existe_base`/`tamanho_da_base` para o
  membro; cp1252 sem losango e BOM; offset do fluxo descompactado; `.zst` fora sem o pacote; `.zip`
  quebrado avisa.
- `tests/test_games_index.py::IndiceSobreBaseComprimidaTests`: a consulta lê a partida do `.gz` e
  do membro do `.zip` pelo offset; a base comprimida que mudou é relida inteira; o nome no
  manifesto é `pacote.zip/torneio.pgn`.

### O que o crítico recusou

_a preencher pelo crítico_
## S-532 · Índice incremental: só o que mudou é relido, com progresso e cancelamento na janela — ✅ **implementada em 2026-09-04**

### Problema

`games_index.py:135` (`build_index`) nascia inteiro num `.parcial` (`:155`) e era renomeado no fim
(`:212`): qualquer arquivo novo na pasta -- ou um torneio anexado ao `.pgn` de sempre -- custava a
pasta inteira de novo, 18 GB e mais de vinte minutos nesta máquina, porque `files` (`:181`) só
guardava o nome e o número do arquivo era a posição na lista. O `progress` (`:139`) era
`Callable[[int], None]`, chamado a cada 500 mil partidas, sem dizer de que arquivo nem quanto
falta; não havia `cancel`; e a janela só sabia dizer *"se o índice ainda não foi construído:
cvoff-games --build-index"* (`qt/dialogos.py:610`) -- quem acrescentava um torneio e voltava à sala
de estudo descobria que a busca por nome recusou o índice, e a saída era abrir um terminal.

### Solução

**A tabela `files` virou manifesto (`INDEX_VERSION = 4`).** Por base: `name` (o de `nome_da_base`),
`size`, `mtime`, `head` e `tail` -- o `blake2b` dos primeiros e dos últimos `BYTES_DA_MARCA` = 64 KB
--, e `games`. Tamanho igual não diz que o conteúdo é o mesmo, e `mtime` igual não diz nada num
sync de nuvem (a S-113 registra o antivírus que reescreve o carimbo sem tocar num byte): quem
decide são tamanho e as duas marcas, que custam menos de um milissegundo por arquivo. O que
decide reler, arquivo a arquivo: mesmo tamanho e mesmas marcas → **pulado** (só o `mtime` é
atualizado); cresceu, mesma cabeça sobre os bytes que o manifesto mediu e a cauda antiga ainda no
mesmo lugar → lido **a partir do tamanho antigo**, com os offsets velhos intactos; qualquer outra
diferença, ou base comprimida que mudou → as partidas dele saem e ele é relido inteiro; não está
mais na lista → as partidas dele saem. O número do arquivo vem do manifesto e sobrevive à ordem;
um arquivo novo recebe o próximo livre. Um índice v3 é apagado e refeito, como `--build-index`
sempre significou; o `.parcial` de uma versão anterior interrompida vai junto.

**Uma transação por arquivo, e a marca da base só no fim.** O índice é editado **no lugar**, com
`journal_mode=DELETE` (o `TRUNCATE` deixaria um `-journal` vazio ao lado para sempre, e `data/`
tem guarda contra artefato que ninguém declarou). A `meta.database` é apagada **antes** de qualquer
mudança e regravada só quando a rodada termina: é ela que `lookup_pair` confere, então um índice
em obras recusa a consulta em vez de responder menos do que a base tem -- a S-25 sem `.parcial`.
Cancelar (`cancel: threading.Event`, conferido a cada `_LINHAS_POR_CONFERENCIA` = 16 mil linhas,
~1 MB) desfaz só o arquivo em curso e mantém os anteriores; a rodada seguinte continua deles.
`build_index` devolve `Indexacao(partidas, relidas, arquivos_relidos, arquivos_pulados,
arquivos_removidos, cancelado)` -- o item em forma de número, e é isso que o teste afirma.

**`Progresso = (base, bytes_lidos, bytes_totais, partidas)`**, no máximo a cada
`INTERVALO_DE_PROGRESSO` = 0,1 s dentro de um arquivo, mais um aviso final por arquivo com os bytes
cheios -- **também para o pulado**, para a barra do conjunto andar pelo que não precisou ser lido.
Os bytes são os do disco (comprimidos, se a base for), porque são os únicos comparáveis ao
tamanho. `cli/games.py::_index_progress` reduz isso a uma linha a cada 5 s e uma por arquivo: dez
por segundo é o ritmo de uma barra, não o de um terminal.

**A decisão pura, `ui/indice_da_base.py`.** `Andamento` soma o último aviso de cada arquivo (posição
absoluta, não incremento) sobre o total e devolve `POR_MIL`; `frase_de_progresso` (`Lendo
base.pgn: 1,2 GB de 8,6 GB · 1.234.567 partidas`, ou `base.pgn: sem mudança, não foi relido`);
`frase_de_fim`, que diz **o que não foi relido**; e `perde_trabalho_ao_fechar() == False`, porque
cada arquivo é uma transação -- dizer o contrário treinaria a pessoa a ignorar o aviso quando ele
for verdade (a busca por posição).

**A fiação, `qt/indice_da_base.py`.** `IndexadorDaBase(QObject)` roda `build_index` numa `Tarefa`
(o `QThread` de `qt/trabalho.py`); o `progress` é chamado na thread de trabalho e **só emite**
`progresso(str, int, int, int)`; o slot `_somar`, do lado da interface, soma e emite
`avancou(por_mil)`; `terminou(Indexacao)` e `falhou(str, exc)` são os dois fins, e exatamente um
chega. Registra-se no `BusyRegistry` com `loses_work=False`, `cancellable=True` e o `cancel` do
`Event`. `indexar_com_dialogo(parent, bases, caminho)` monta um `QProgressDialog` modal à janela
com Cancelar em cima dele, que fecha sozinho no fim; `frase_final(resultado)` é o que vai ao
rodapé. O módulo não conhece painel nenhum: **quem o chama é um `connect` na sala ou no menu**, e
essa linha não foi escrita neste item porque `qt/painel_de_estudo.py` está sendo editado pela
S-527 na mesma árvore.

### Critério de aceite

- Segunda rodada sobre a mesma pasta: `relidas == 0`, `arquivos_pulados == n`, e a consulta segue
  respondendo. ✅ **Medido em 2026-09-04** sobre `LumbrasGigaBase_OTB_Complete.pgn` (8,6 GB,
  10.355.488 partidas): do zero 539 s na rodada limpa (6,4 avisos/s) e 1.212 s numa segunda rodada com o `tracemalloc` ligado e a suíte rodando ao lado (índice de 235 MB, 7.266 avisos,
  6,0/s); segunda rodada sem mudança **0,006 s** (< 2 s).
- Arquivo anexado: só a cauda é lida. ✅ Medido numa cópia em pasta temporária do
  `Endgame_Study_Database_VI_...pgn` (62 MB, 93.839 partidas): do zero 7,6 s; depois
  de anexar 1 partida, **0,014 s** e `relidas == 1`; a partida anexada é achada em
  2 ms.
- Arquivo removido sai do índice, sem aviso na consulta; arquivo reescrito é relido inteiro sem
  deixar linha velha; o novo ganha o próximo número e os antigos ficam com o deles. ✅
- Cancelamento honrado em < 1 s: com o pedido aos 0,3 s, a rodada volta antes de 1,3 s, a base
  pequena terminada fica, a grande é desfeita, e `lookup_pair` recusa o índice com a instrução de
  refazer até a rodada seguinte terminar -- que retoma do que ficou. ✅
- Progresso ≤ ~10×/s dentro de um arquivo. ✅ (Medido na gigabase: 6,0/s.)
- Pico de memória do índice do zero: 12,8 MB no `tracemalloc` sobre os 62 MB de referência, e 28 MB sobre os 8,6 GB da gigabase --
  o lote de 200 mil linhas, e nada proporcional ao arquivo.
- O Qt: fim e progresso chegam por sinal; o último valor do conjunto é mil; duas rodadas ao
  mesmo tempo são recusadas; cancelar pela API e pelo botão do diálogo para em < 1,5 s e o
  resultado diz; a falha vira sinal e não exceção; o `BusyRegistry` vê a operação enquanto roda,
  com `loses_work` falso, e a solta no fim. ✅
- Nenhum teste toca `data/`; o índice de medição ficou em pasta temporária. ✅
- `qt/janela.py` não é tocado. ✅

### Testes

- `tests/test_games_index.py::IndiceIncrementalTests`: primeira rodada lê tudo; segunda não relê
  nada e o progresso chega uma vez por arquivo com os bytes cheios; `mtime` sozinho não força;
  anexado relê só a cauda e a consulta acha velhas e nova; reescrito relido inteiro sem linha
  velha; removido sai; o novo ganha o próximo número; v3 é refeito; nem `.parcial` nem `-journal`
  sobram. `CancelamentoDoIndiceTests`: < 1 s, a consulta recusa o índice em obras, a rodada
  seguinte retoma, e ≤ 10 avisos/s. `IndiceSobreBaseComprimidaTests` (S-531).
- `tests/test_ui_indice_da_base.py`: a barra do conjunto anda pelo pulado; posição absoluta e não
  incremento; não passa de mil; arquivo não previsto entra no total; as três frases; fechar não
  perde trabalho.
- `tests/test_qt_indice_da_base.py`: fim por sinal com o resultado; progresso por sinal e somado
  por mil; não começa duas; cancelar para em < 1,5 s; falha vira sinal; registra no `BusyRegistry`
  e solta; o diálogo anda com o índice e fecha no fim; o botão Cancelar do diálogo para o índice.
- `tests/test_editor_model.py::SEM_TKINTER` ganhou `indice_da_base.py`; `docs/ARCHITECTURE.md`
  conta treze threads e a tabela ganhou a linha do índice.

### O que o crítico recusou

_a preencher pelo crítico_
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

## S-549 · Guarda genérica: nenhum módulo de `ui/` importa toolkit — ✅ **implementada em 2026-09-04**

### Problema

A regra existe desde o corte do Tk (S-506): `src/chess_diagram_ocr/ui/` é a camada pura e `qt/` é o
toolkit. O que a cobrava eram três guardas, nenhuma genérica:

- `tests/test_ui_comandos.py:495` (`test_o_catalogo_nao_importa_tkinter`) e
  `tests/test_ui_texto_cor.py:138` (`test_o_modulo_de_cor_nao_importa_tkinter`) olham **um módulo
  cada**, e perguntam só por `tkinter`;
- `tests/test_editor_model.py:405` (`SemTkinterTests`, S-137) percorre `ui/` inteira, mas pergunta por
  `tkinter` e `PIL` -- o toolkit que **saiu**. A lista `SEM_TKINTER` é a de 2026-08-12, quando importar
  Tk em `ui/` era o normal e a lista fixava quem tinha decidido não fazê-lo.

Um `from PyQt6.QtCore import Qt` num módulo de `ui/` passava pelas três em verde, e é o import mais
provável de todos hoje, porque o Qt é o único toolkit que resta. Nada perguntava por `PySide6`, por
`ttkbootstrap` (que saiu do `pyproject.toml` no corte) nem pelo caminho indireto -- `from
chess_diagram_ocr.qt import tema`, que não escreve `PyQt6` em linha nenhuma e só abre com o Qt
instalado. E nada perguntava pelo resto do pacote: `service.py`, `detection/`, `text/` e `cli/` são a
promessa da S-31 (*a interface é apresentação*), e a única cobrança dela era a de a S-500 ter conseguido
nascer.

### Solução

`tests/test_ui_fronteira.py`, uma varredura por `ast` com uma função só -- `violacoes(pasta, raiz,
isencoes)` -- apontada três vezes:

1. para `ui/`: nenhum módulo importa `PyQt6`, `PySide6`, `tkinter`, `ttkbootstrap` nem
   `chess_diagram_ocr.qt`;
2. para o pacote inteiro: nada fora de `qt/` importa toolkit, salvo o que `PODEM_IMPORTAR_TOOLKIT`
   isenta **com motivo** -- hoje só `cli/texto_transcrever.py`, a janela Tk de desenvolvimento que
   transcreve as 123 faixas da S-183 e que o corte deixou de propósito;
3. para `qt/`: o **controle** sobre a árvore real -- a mesma função tem de achar o toolkit em todo
   módulo de desenho (31 de 33; `__init__.py` e `preferencias.py` não têm widget de propósito).

A leitura conta `import x`, `from x import y`, o import tardio dentro de função, o de
`TYPE_CHECKING`, o relativo (`from ..qt import tema`, resolvido contra o pacote do arquivo) e o por
nome (`importlib.import_module("PyQt6.QtGui")`). Não conta prosa: os módulos deste projeto citam
`import tkinter` e `PyQt6` em docstring para dizer que aquilo **não** existe ali, e uma varredura de
texto reprovaria a explicação -- é a mesma razão do `ast` em `test_ui_orfaos.py` (S-511).

A isenção é um mapa e não uma lista de perdão, na forma do `SEM_CHAMADOR`:
`test_toda_isencao_ainda_importa_toolkit` exige que quem está isento **continue** importando toolkit,
senão a isenção envelhece apontando para um arquivo que já não precisa dela.

### Critério de aceite

- `violacoes(ui/)` devolve `{}`, e a mensagem de falha nomeia módulo, linha e o que ele importou. ✅
- `violacoes(pacote inteiro, isenções)` devolve `{}`. ✅ Medido em 2026-09-04: **nenhuma violação
  real**. Fora de `qt/`, o único arquivo do pacote que importa toolkit é `cli/texto_transcrever.py`
  (cinco imports tardios de `tkinter`, linhas 50, 51, 280, 351 e 435), isento por decisão do corte.
- A guarda **acha**: oito módulos sintéticos numa pasta temporária cobrem as seis formas de import, a
  prosa que não conta, o nome parecido que não conta (`tkinter_util`, `PyQt6Compat`,
  `chess_diagram_ocr.qtx`) e a isenção que cobre arquivo e pasta e nada mais. E, sobre a árvore
  real, a mesma função apontada para `qt/` acha o toolkit em 31 módulos. ✅
- A varredura não é vácua sobre `ui/`: mais de 45 módulos lidos, com mais imports que módulos. ✅

### Testes

- `tests/test_ui_fronteira.py::DetectorTests` (novo) -- `test_o_import_de_topo_e_acusado_com_a_linha`,
  `test_os_cinco_toolkits_sao_acusados_em_qualquer_forma`, `test_o_import_tardio_e_o_de_tipo_contam`,
  `test_o_import_relativo_do_pacote_de_desenho_e_resolvido`,
  `test_o_relativo_de_um_nivel_dentro_de_ui_nao_e_toolkit`, `test_citar_o_toolkit_na_prosa_nao_e_importa_lo`,
  `test_a_isencao_cobre_o_arquivo_e_a_pasta_e_nada_mais`, `test_um_nome_parecido_nao_e_toolkit`.
- `tests/test_ui_fronteira.py::FronteiraTests` (novo) -- `test_a_varredura_le_a_camada_pura_inteira`,
  `test_a_mesma_varredura_acha_o_toolkit_onde_ele_mora`, `test_nenhum_modulo_de_ui_importa_toolkit`
  (**o critério**), `test_nada_fora_do_pacote_de_desenho_importa_toolkit`,
  `test_toda_isencao_ainda_importa_toolkit`.
- As três guardas de antes ficam: elas afirmam módulos nomeados, e a lista `SEM_TKINTER` continua
  sendo a descrição de cada módulo puro, que esta guarda não tem.

### O que o crítico recusou

_a preencher pelo crítico_

## S-550 · As S-500 a S-506 do corte do Tk ganham seção de spec (dívida de documentação) — ✅ **implementada em 2026-09-04**

### Problema

Os identificadores S-500 a S-506 são citados em docstring de todo `qt/*.py` (`qt/__init__.py:1`, e a
partir dele cada painel), em `app_pyqt.py:1`, em 18 arquivos de `tests/`, em `pyproject.toml`,
`packaging/cvoff.spec`, `.github/workflows/ci.yml`, `CONTRIBUTING.md` e em oito `docs/*.md` -- e
**nenhum tem seção `## S-5NN`** em `docs/SPEC_*.md`. A tabela "Onde mora a spec de cada item"
(`docs/SPEC_SUITE.md:25` e as outras 26 cópias) pulava de `S-452` para `S-507`: quem lia
`(S-503)` num cabeçalho e ia à tabela não encontrava faixa nenhuma. As guardas de `tests/test_docs.py`
não acusavam porque cobram seção só de item **entregue em mensagem de commit**, e o porte inteiro
entrou no git num commit só, `653f88b`, cujo assunto não cita número.

### Solução

As sete seções abaixo, escritas a posteriori a partir do que o código, os testes e o log dizem: os
docstrings de `qt/`, o `git show 653f88b` (o corte, 2026-08-31, único commit em que `qt/` e
`app_pyqt.py` entram na história), o `810072a` do mesmo dia (a conta do catálogo, S-505) e as
narrativas de `docs/ARCHITECTURE.md` ("A escolha de framework, e como ela mudou") e
`docs/SPEC_ESTUDO_QT.md`. A data de todas é **2026-08-31**, porque é a única que o log tem: a
paridade painel a painel (S-500 a S-505) foi feita fora da história e commitada com o corte.

Elas moram **neste** arquivo, e não num `SPEC_QT.md` novo, porque documento novo em `docs/` custa três
guardas (índice do README, tabela de faixas idêntica, isenção dos `ROADMAP*`) e a S-550 é uma dívida de
documentação, não um documento. A linha da tabela passa a dizer `S-500 a S-506, S-527 a S-580`, nas 27
cópias, byte a byte.

### Critério de aceite

- Cada uma das sete tem Problema, Solução, Critério de aceite e Testes, citando testes que **existem**
  no disco de 2026-09-04. ✅
- `tests/test_docs.py` inteiro verde: a tabela de faixas é a mesma nos 27 arquivos, nenhuma célula é
  ilegível, toda seção está no arquivo que o índice declara, e nenhum número nomeia duas coisas. ✅
- Nenhuma outra seção deste arquivo foi tocada. ✅

### Testes

- `tests/test_docs.py::IndiceNaoEVacuoTests::test_todo_item_com_secao_esta_declarado_no_indice` -- é a
  guarda que passaria a reprovar as sete seções sem a faixa nova na tabela.
- `tests/test_docs.py::test_a_tabela_de_faixas_e_a_mesma_em_todos_os_documentos_que_a_trazem` -- as 27
  cópias.
- `tests/test_docs.py::test_a_secao_esta_no_arquivo_que_o_indice_declara` e
  `NumeroDeItemUnicoTests::test_nenhum_numero_de_item_nomeia_duas_coisas`.

### O que o crítico recusou

_a preencher pelo crítico_

---

# O porte para o Qt e o corte do Tk (S-500 a S-506) — escrito a posteriori pela S-550

As sete seções abaixo não têm rodada de crítica: foram reconstruídas em 2026-09-04 a partir do
código, dos testes e do log. Onde um número é citado, ele é o do commit `653f88b` ou de um teste que
existe no disco.

## S-500 · A janela em PyQt6 nasce como versão de teste sobre o mesmo `service.py` — ✅ **implementada em 2026-08-31**

### Problema

A fronteira da S-31 -- *a interface é apresentação; o que dá para testar mora no pacote* -- era uma
promessa com um cliente só. `653f88b^:app_tkinter.py` tinha 2.327 linhas e era a única janela; nada
media se `service.py`, `detection/`, `ui/page_overlay.py` e `ui/viewport.py` eram de fato
independentes do toolkit, porque nunca houve um segundo chamador. A `docs/ARCHITECTURE.md` recomendava
ficar no Tk, com a saída amarrada a dois gatilhos mensuráveis (S-53) -- e nenhum dos dois disparou.

### Solução

O pacote `src/chess_diagram_ocr/qt/` e a entrada `app_pyqt.py`, uma segunda janela sobre exatamente o
mesmo `OcrService`, **somente-leitura por decisão**: abre o livro, navega, marca os diagramas sobre a
página, lê a página e mostra o que leu -- tabuleiro, FEN, confiança, lado a jogar e legalidade -- e
para antes de gravar, porque um teste que escrevesse no `labels.csv` deixaria de ser um teste. Ela
existe para responder com código que roda três perguntas:

1. *A fronteira da S-31 aguenta outro frontend?* Sim: nada em `service.py`, `detection/`,
   `page_overlay.py` ou `viewport.py` precisou mudar para a janela nascer.
2. *Quanto da lógica de tela já estava fora do Tk?* `ui/page_overlay.py` (onde as caixas estão e o
   que um clique nelas significa) e `ui/viewport.py` (roda, zoom, "caber na página") são reusados
   inteiros; o que o pacote escreve do zero é o desenho, `QPainter` no lugar de `create_rectangle`.
3. *O que o Tk carregava sozinho?* O que não deu para reusar aparece como código novo, e é o inventário
   do que uma migração custaria.

O PyQt6 entra como **extra `qt`** do `pyproject.toml`, e `packaging/cvoff.spec` exclui `PyQt6` e filtra
`chess_diagram_ocr.qt` do `collect_submodules`, para não levar ~150 MB de Qt no `.zip` de quem não
pediu segunda janela. PyQt6 e não PyQt5 porque é o que tem roda publicada na faixa `>=3.10,<3.14`
inteira. O título da janela traz uma marca (`TITULO_DA_JANELA`), porque duas janelas do mesmo produto
lado a lado é a situação em que alguém corrige vinte diagramas na errada.

### Critério de aceite

- Nenhum módulo já existente muda para a janela nascer; `qt/` não importa `tkinter`. ✅
- A janela abre o livro, marca, lê e mostra, recebendo o serviço pronto (`servico=`) -- o que permite
  exercitar o caminho de leitura inteiro sem o `models/piece_classifier.pt`. ✅
- O `.exe` não cresce: `PyQt6` no `excludes` do `.spec` e `qt/` fora do varrimento. ✅ (invertido na
  S-506, quando a janela passou a ser esta.)

### Testes

- `tests/test_app_pyqt.py` -- `FracoesDaVistaTests` (a fração do `yview` do Tk a partir de um
  `QScrollBar`), `TabuleiroTests`, `VisorTests`, `JanelaTests` (abrir, navegar, marcar, ler, clicar na
  caixa, a roda no fim da página) e `SelftestTests`.
- `tests/test_packaging.py::SpecTests::test_o_que_nao_e_dependencia_nao_entra_no_bundle` -- a regra
  pela qual o `PyQt6` entrou no `excludes` enquanto era extra.
- `tests/test_page_overlay.py` e `tests/test_viewport.py` continuam sendo os testes das decisões
  reusadas: repeti-las em `qt/` mediria o mesmo código duas vezes.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-501 · O que a versão de teste repetia passa a ser chamado: tema, atalhos, rodapé, tabela, barra, menu, plataforma e tabuleiro — ✅ **implementada em 2026-08-31**

### Problema

A segunda janela repetia decisões em vez de chamá-las, e o cabeçalho de `qt/tabuleiro.py` registrava o
caso mais claro: `BoardGeometry.fit` e `heatmap_color` eram cálculo puro em
`653f88b^:src/chess_diagram_ocr/ui/board_render.py`, e mesmo assim não podiam ser importados, porque
o módulo em que moravam importava `tkinter` e `PIL` na primeira linha -- a incerteza aparecia como
**contorno** na casa em vez de calor, e `UNICODE_PIECES` existia em duas cópias byte a byte. A tabela
de atalhos de `ui/atalhos.py` escrevia tecla na linguagem do Tk (`"<Control-s>"`) e a guarda de foco
da S-20 devolvia `"break"`/`None`. E `recognize_page` rodava o detector de novo sobre a página que o
visualizador acabara de detectar para desenhar os retângulos: o log de uma sessão real mostrava
"Aparado pela moldura" duas vezes por página.

### Solução

Abrir a metade pura de cada módulo do Tk e chamá-la dos dois lados:

- `ui/desenho_do_tabuleiro.py` recebe `BoardGeometry.fit`, `heatmap_color` e `UNICODE_PIECES`, sem
  toolkit; `qt/tabuleiro.py` passa a chamá-los. A incerteza volta a ser calor, com alfa de verdade no
  lugar do `stipple="gray50"` que o canvas do Tk exigia.
- `qt/atalhos.py` **traduz** a tabela de `ui/atalhos.py` numa função pura de 20 linhas em vez de
  redeclará-la em `QKeySequence`, e a guarda vira um `eventFilter` na aplicação -- `True`/`False` é o
  mesmo par de respostas que `"break"`/`None`.
- `qt/tema.py`: a folha de estilo construída por função pura (`folha_de_estilo()`) a partir dos mesmos
  papéis de `ui/tokens.py`; aqui não há `ttkbootstrap`, então *o tema somos nós*, e o eixo de tema
  colapsa -- fica a pele, com o seu `cromo_escuro`.
- `ui/estado_do_rodape.py` (severidade, expiração, descrições) e `qt/rodape.py`; `qt/tabela.py` das
  mesmas `Coluna`; `qt/barra.py` (a barra que quebra em vez de cortar, S-151); `qt/menu.py` da mesma
  declaração (S-161); `qt/legenda.py` (`descricao_completa` passa a ser pública); `qt/plataforma.py`
  (DPI e ícone antes de a janela existir, S-148); `qt/dica.py`.
- `OcrService.recognize_page` aceita a lista de candidatos que quem chamou já detectou: marcar e
  depois ler deixa de varrer a página duas vezes, e o retângulo "3" da tela e o diagrama 3 da lista
  passam a ser o mesmo objeto por construção.

### Critério de aceite

- Nenhuma decisão em duas cópias: `UNICODE_PIECES` é um `assertIs`, e o tabuleiro das duas janelas,
  na mesma área, tem o mesmo tamanho e a mesma origem. ✅
- Nenhuma tecla escrita fora de `ui/atalhos.py`, **também deste lado**. ✅
- F4 (marcar) e depois F5 (ler) não detectam duas vezes. ✅
- A paleta, as peles e as densidades são afirmáveis sem servidor gráfico, porque a folha é texto. ✅

### Testes

- `tests/test_qt_tabuleiro.py` (`test_a_tabela_de_glifos_e_a_do_produto`, `test_a_rampa_de_calor_e_a_do_produto`,
  `test_a_geometria_e_a_do_produto` -- os três `assertIs` que fecharam o achado),
  `tests/test_qt_atalhos.py` (a tradução e "nenhuma tecla escrita fora de `ui/atalhos.py`"),
  `tests/test_qt_tema.py::FolhaDeEstiloTests`, `::PapelDoBotaoTests`, `tests/test_qt_barra.py`,
  `tests/test_qt_menu.py`, `tests/test_qt_legenda.py`, `tests/test_qt_plataforma.py`,
  `tests/test_qt_rodape.py`, `tests/test_qt_tabela.py`, `tests/test_qt_dica.py`.
- `tests/test_service.py::PaginaComCandidatosProntosTests` e
  `tests/test_app_pyqt.py::JanelaTests::test_marcar_duas_vezes_nao_varre_a_pagina_duas_vezes`.
- `tests/test_editor_model.py::SemTkinterTests` -- `desenho_do_tabuleiro.py` e `estado_do_rodape.py`
  entram em `SEM_TKINTER` com a marca `(S-501)`.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-502 · A janela em Qt passa a corrigir e gravar: tabuleiro editável e `Ctrl+S` — ✅ **implementada em 2026-08-31**

### Problema

A S-500 parava, de propósito, antes do que a janela do produto tinha além de ler: editar casa a casa,
salvar amostra, treinar, exportar. Aquilo era certo enquanto o pacote existia para **provar** uma
fronteira. O dono decidiu que o Qt substitui o Tk, e a decisão muda o argumento: uma janela que vai ser a
única não pode recusar o gesto mais repetido do programa -- corrigir, `Ctrl+S`, seta. O risco que a
S-500 evitava era um **segundo caminho de escrita** no `labels.csv`.

### Solução

`qt/tabuleiro_editavel.py`: clique, arrasto e pincel sobre um `BoardModel` -- o que cada gesto
*significa* (`press`, `drop`, `paint`, `erase`, e o `BoardChange` que devolve) continua sendo de
`ui/board_model.py` e `ui/board_edit.py`, e o que o widget escreve é só o roteamento do evento do Qt
para a chamada do modelo. A gravação obedece `ui/editor_model.DiagramEditorModel.save_target()` --
*amostra nova ou regravar a linha existente?*, a regra mais delicada da interface (S-49), pura e com
teste sem janela --, e é isso que atende a cautela: o que existe é um segundo widget sobre o mesmo
caminho, não um segundo caminho. O título deixa de dizer "versão de teste", porque é falso desde aqui;
o que ele precisa dizer é **qual** janela é esta, enquanto houver duas escrevendo no mesmo arquivo.

### Critério de aceite

- A correção vai para o `fen_edits` do editor, e não para o item -- ela sobrevive à ida e volta entre
  diagramas, que é o laço mais repetido do programa. ✅
- A posição gravada é a **corrigida**, e não a que o modelo leu. ✅
- A posição ilegal pergunta; o "não" cancela; a confirmada grava. Um erro no repintar depois da
  gravação não vira "falha ao salvar" sobre uma amostra que está no disco (S-318). ✅
- `mouseReleaseEvent` respeita `allow_deselect`: selecionar não exige dois cliques. ✅
- O `labels.csv` dos testes é temporário (`csv_de_rotulos=`). ✅

### Testes

- `tests/test_qt_tabuleiro_editavel.py` -- o roteamento, com `LIMIAR_DE_ARRASTO`.
- `tests/test_qt_gravacao.py::GravacaoTests` e `::VinculoTests` -- os catorze casos da gravação, do
  vínculo e da origem gravada.
- `tests/test_app_pyqt.py::JanelaTests::test_o_titulo_diz_qual_das_duas_janelas_e_esta`.
- `tests/test_editor_model.py` e `tests/test_board_model.py` continuam sendo os testes da decisão.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-503 · Os painéis portados um a um, e as decisões abertas em módulos puros de `ui/` — ✅ **implementada em 2026-08-31**

### Problema

Depois da S-502 a janela do Qt tinha a lista, o tabuleiro, a FEN e o salvar **embutidos** -- o mesmo
arranjo que a S-31 tirou do `ChessOcrTkApp`: com o estado do PDF, o do editor e o do estudo no mesmo
objeto, um método de navegação de página mexe no que está sendo editado sem que nada diga. E do lado
do Tk cada painel carregava decisão dentro do widget: `653f88b^:src/chess_diagram_ocr/ui/result_panel.py`
tinha 1.402 linhas; os diálogos devolviam pelo atributo `chosen`; a Galeria, o Dataset, a Revisão, a
sala de estudo e a fita decidiam medidas, colunas, tri-estados e contabilidade em código que só rodava
com uma raiz Tk aberta.

### Solução

Um widget por painel, e para cada um a metade pura aberta num módulo de `ui/` que os dois frontends
podiam chamar:

| painel (`qt/`) | decisão aberta em `ui/` |
|---|---|
| `painel_de_resultado.py` | `editor_model`, `historico`, `legality`, `board_edit` (já puros); `_atualizar_tudo` no lugar dos três `update_*` separados |
| `painel_do_pdf.py` · `visor.py` | `leitura_do_pdf.py` (os três números medidos do visualizador e o leitor do sistema, S-330) |
| `painel_da_galeria.py` | `galeria_declarada.py` (medidas, tri-estado do link, contabilidade do lote, S-67) |
| `painel_de_estudo.py` · `tabuleiro_de_jogo.py` | `sala_declarada.py` (tabela comando→método e as seis medidas, S-280) |
| `painel_do_dataset.py` | `resumo_do_dataset.py` (colunas, paginação, textos, S-23) |
| `painel_de_revisao.py` | `varredura_de_revisao.py` (o pedido e o acumulador da fila, S-116/S-119) |
| `dialogos.py` | `escolha_de_bases.py`, `escopo_da_varredura.py`, `lista_de_partidas.py` (o travessão), `pedido_de_treino.py` |
| `fita.py` · `paleta.py` · `icones.py` | `medidas_da_fita.py` (modos, orçamento, grupos), `filtro_de_comandos.py` (inventário e ordem da paleta), `ui/icones.py` |

O modal do Qt é `exec()`, e é onde os dois frontends mais divergem: a função `perguntar_*` de cada
diálogo cabe em três linhas, o atributo continua existindo para o teste, e o `Escape` fecha de graça.

### Critério de aceite

- Cada painel tem o seu `tests/test_qt_*.py` e se testa **sem abrir a janela inteira**. ✅
- `qt/painel_de_resultado.py` tem menos de um terço das 1.402 linhas de `ui/result_panel.py`, e a
  diferença é código chamado, não omitido. ✅
- Toda decisão aberta está em `SEM_TKINTER` com a marca `(S-503)` e tem teste sem janela. ✅
- A janela conversa com o painel por sinal, e não lendo o estado dele. ✅

### Testes

- `tests/test_qt_painel_de_resultado.py`, `tests/test_qt_painel_do_pdf.py`,
  `tests/test_qt_painel_da_galeria.py`, `tests/test_qt_painel_de_estudo.py`,
  `tests/test_qt_painel_do_dataset.py`, `tests/test_qt_painel_de_revisao.py`,
  `tests/test_qt_dialogos.py`, `tests/test_qt_fita.py`, `tests/test_qt_paleta.py`.
- `tests/test_editor_model.py::SemTkinterTests::test_os_doze_continuam_sem_tkinter` -- os onze módulos
  marcados `(S-503)` na lista.
- `tests/test_review_queue.py` -- o alvo do `patch` passa a ser `ui/varredura_de_revisao.py`.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-504 · A aba de texto no Qt: o documento é o estado, e o widget é o desenho — ✅ **implementada em 2026-08-31**

### Problema

`653f88b^:src/chess_diagram_ocr/ui/texto_panel.py` tinha 2.600 linhas, e uma parte delas existia só
para contornar o `tk.Text`: uma etiqueta do Tk dá **uma** fonte ao trecho e a última criada vence --
daí `NEGRITO_ITALICO`, daí `fonte:titulo:bi:2` gerada sob demanda, daí o cache `_fontes_desenhadas`
refeito a cada zoom, e negrito dentro de um título sumia; a pilha de desfazer do Tk guarda índice e
não conteúdo, então todo redesenho exigia `edit_reset()`; e o documento era lido **de volta do
widget**, etiqueta por etiqueta, para gravar (`ui/texto_etiquetas.de_despejo`).

### Solução

`qt/painel_de_texto.py` e `qt/texto_formato.py`. O `QTextCharFormat` guarda peso, pendor e corpo
separados, e os três contornos somem. O documento **é** o estado e o widget é só o desenho dele: toda
ferramenta chama uma função pura de `text/rico.py`, recebe um documento novo e o redesenha -- é o que
faz o negrito sobreviver ao arquivo em vez de existir só enquanto o widget existir. A fronteira
estreita é o deslocamento: as funções puras falam em caractere do *documento*, o `QTextEdit` em
posição do *cursor*, e os dois divergem porque a miniatura do diagrama vale um caractere para o Qt e
nenhum para o documento -- `_Mapa` resolve o que `ui/texto_etiquetas.deslocamento` resolvia
percorrendo o `dump` do widget a cada pergunta. `ui/texto_declarado.py` recebe a tabela
comando→método e o zoom da vista (S-240).

### Critério de aceite

- Negrito, itálico e título convivem no mesmo trecho. ✅
- O negrito aplicado depois do terceiro diagrama cai onde a pessoa clicou, e não três caracteres
  adiante. ✅
- O desfazer vê uma mudança de formato, que não altera caractere nenhum. ✅
- A aba registra as duas operações longas no `BusyRegistry`, como o painel do Tk fazia (fechado na
  S-506, que o achou). ✅

### Testes

- `tests/test_qt_texto.py` -- o formato, o mapa de deslocamento e as ferramentas.
- `tests/test_qt_texto_cauda.py` -- a cauda da aba (S-240 a S-266, S-343): o que o porte da S-502
  tinha parado antes de fazer.
- `tests/test_editor_model.py::SemTkinterTests` -- `texto_declarado.py` com a marca `(S-504)`.

**O que ficou de fora, e virou item.** A digitação no editor do Qt não chegava ao documento -- o
widget recebe o texto e `documento` fica como estava --, medido em 2026-09-02 pela triagem da S-511.
É a **S-521** ([SPEC_EDITOR.md](SPEC_EDITOR.md)), e não um defeito desta seção: o porte trouxe as
ferramentas e o desenho, e o caminho do teclado ao documento ficou para depois.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-505 · A janela reúne os painéis: sete abas, uma tabela de comandos, e toda ação com dono — ✅ **implementada em 2026-08-31**

### Problema

Com os painéis como widgets (S-503), o que falta é quem os ligue: a fiação entre eles, a tabela de
comandos que o menu, a paleta e os atalhos leem, e a entrada do processo. E a guarda que perguntava se
uma ação do catálogo tinha dono era satisfeita por um `lambda: None`: ela perguntava se a ação tinha
entrada na tabela, e um comando que não faz nada **tem**. Três ações do catálogo -- `anotar_pagina`,
`anotar_sem_diagrama`, `tirar_do_campo` -- eram servidas por **botões** da janela do Tk e não pela
tabela `_comandos`, então comparar as duas janelas ação a ação passava em verde sem elas; entre elas
estava o único caminho que faz `data/field_set.jsonl` crescer.

### Solução

`qt/janela.py`, `JanelaPrincipal`: monta as seis abas de trabalho ao lado do visualizador, liga sinal a
sinal e **soma as três tabelas de comandos** (a da janela, a da sala e a da aba de texto) numa só, de
onde saem o menu, a paleta e os atalhos -- a janela traduz widget em parâmetro do serviço, e nada
mais. `qt/exportador.py` (com `ui/exportacao_de_pgn.py`: `ExportSettings` e `describe_report`),
`qt/campo.py` (as três ações do conjunto de campo, com `ui/field_draft.py`) e as quatro origens do
painel de Resultado (`carregar_pagina`, `carregar_item_de_revisao`, `carregar_amostra`,
`carregar_avulsos`), cada uma declarando o vínculo que impede `Ctrl+S` de gravar pelo caminho errado.
`app_pyqt.py` é a entrada: argumentos, log, `QApplication` e o `--selftest`.

A conta do catálogo fecha em duas guardas, e a segunda é o **controle** da primeira: todo comando do
catálogo alcança o menu ou está numa das duas listas que declaram por que não; e a varredura de
inertes lê a **fonte** de `qt/janela.py` por `ast`, provada contra uma fonte de mentira -- a primeira
versão pedia `inspect.getsource` do `lambda`, caía num `except SyntaxError` e passava em verde com um
comando inerte no arquivo. É a lição que `test_ui_orfaos.py` (S-511) cita como "a trava da guarda dos
inertes".

### Critério de aceite

- As seis abas na ordem da spec; o visualizador ao lado delas e não dentro. ✅
- A tabela de comandos é a soma de três; todo item de menu tem comando; nenhum é inerte; todo comando
  do catálogo tem dono chamável nesta janela. ✅
- O detector de inertes acha um comando inerte numa fonte sintética. ✅
- A frase de todo painel chega ao rodapé; as abas dizem quanto trabalho carregam. ✅
- `qt/janela.py` entra na catraca de linhas de `tests/test_packaging.py` no lugar do
  `app_tkinter.py`. ✅

### Testes

- `tests/test_qt_janela.py::MontagemTests` -- `test_as_seis_abas_estao_na_ordem_da_spec`,
  `test_a_tabela_de_comandos_e_a_soma_de_tres`, `test_nenhum_comando_do_menu_e_inerte`,
  `test_a_varredura_de_inertes_acha_um_comando_inerte`, `test_todo_item_de_menu_tem_comando`,
  `test_todo_comando_do_catalogo_tem_dono_nesta_janela`,
  `test_as_tres_acoes_da_linha_de_campo_sao_as_do_catalogo`, `test_a_frase_de_todo_painel_chega_ao_rodape`.
- `tests/test_qt_janela.py::FiacaoTests` -- abrir o livro chega à Galeria, ao Estudo e ao Texto; a
  Revisão manda varrer e quem varre é a Galeria; gravar pinta a caixa e reconta as abas; e o resto.
- `tests/test_ui_comandos.py::CoberturaDoCatalogoTests::test_todo_comando_do_catalogo_alcanca_alguem` e
  `::test_a_conta_do_catalogo_acusa_uma_acao_sem_dono` (commit `810072a`, 2026-08-31).
- `tests/test_app_pyqt.py::SelftestTests` e `tests/test_packaging.py::TamanhoDaJanelaTests`.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-506 · O corte do Tk: a janela do produto passa a ser a do PyQt6 — ✅ **implementada em 2026-08-31**

### Problema

Com a paridade painel a painel fechada (S-503 a S-505), havia duas janelas escrevendo no mesmo
`labels.csv`: `653f88b^:app_tkinter.py` com 2.327 linhas, 28 módulos de `ui/` acoplados ao toolkit,
46 arquivos de teste que só rodavam com uma raiz Tk, o `ttkbootstrap` como dependência, o PyQt6 como
extra e `packaging/cvoff.spec` excluindo justamente o pacote da janela nova. O dono decidiu a migração
em 2026-08-31, e o corte saiu no mesmo dia (`653f88b`).

### Solução

- Sai `app_tkinter.py`; `ui/` vai de 81 para 52 módulos, e nenhum dos que sobram importa toolkit --
  ela é a camada pura que os dois frontends compartilhavam, e agora só tem um. Seis módulos são
  **podados** em vez de apagados, porque o Qt pede a metade pura deles: `barra`, `degradacao`,
  `folha`, `menu`, `plataforma`, `tabela`. `rodape` sai inteiro (`DESLIGADO` e `Dispositivos` sempre
  moraram em `estado_do_rodape`).
- O PyQt6 deixa de ser o extra `qt` e vira dependência de base; o `ttkbootstrap` sai do
  `pyproject.toml` e do `uv.lock`; o `cvoff.spec` aponta para `app_pyqt.py` e passa a **coletar**
  `qt/` em vez de excluí-lo. O CI para de instalar o extra.
- `data/janela.json` no lugar de `app_tkinter_state.json` -- o estado nunca foi do Tk, é da janela --,
  com o arquivo antigo lido **uma vez** quando o novo ainda não existe, porque ele guarda o histórico
  de 50 livros com a página de cada um.
- A remoção de caixa passa a usar o `DroppedBoxes` puro em vez de um conjunto de índices: ele casa por
  bbox, e índice não é identidade -- uma redetecção com outro DPI renumera tudo.
- Fica de fora, de propósito: `cli/texto_transcrever.py`, a janela Tk que transcreve as 123 faixas de
  referência da S-183 -- ferramenta de desenvolvimento com entrada própria, que não abre pelo `.exe`;
  por isso o `tkinter` não entra no `excludes` do `.spec`.

**O que o corte encontrou, e que teria sumido calado:**

1. Três ações do catálogo sem dono (`anotar_pagina`, `anotar_sem_diagrama`, `tirar_do_campo`): quem
   as acusaria era `ui/alcance.perdidos()`, que saiu no mesmo corte por perguntar sobre os três cromos
   do Tk. Portadas em `qt/campo.py`.
2. Uma confirmação perdida: as 20 perguntas modais do Tk foram listadas por `ast` e comparadas com as
   do Qt; faltava a da S-451, "Salvar todos" sobre página cujos diagramas já têm amostra. Portada.
3. **~20 guardas de varredura verdes e vazias.** Elas varriam sintaxe do toolkit (`ttk.Button`,
   `padx=`, `font=(...)`, `messagebox.ask*`, `bind("<Escape>")`, `threading.Thread(`) e nenhuma ficou
   vermelha no corte: todas passaram sobre lista vazia. Traduzidas para o Qt, acharam na hora 5
   `QPushButton` sem papel declarado, 2 hexadecimais cravados em `qt/tabuleiro.py`, um rótulo escrito à
   mão que o catálogo já tinha, o `QThread` que a varredura de threads não via, e a aba de Texto sem
   registrar as duas operações longas no `BusyRegistry`. Daí a regra que as seções seguintes repetem:
   **uma guarda de varredura tem um controle que acha e deixa de achar**.

**O que o corte custou, e é a lição.** Apagar uma camada não apaga código: apaga o **chamador** de
decisões que ficaram. Sete voltaram um mês depois (`adda88f`: estado da janela, recentes, Aparência e
Densidade, fila e fita, conjunto de peças, árbitro do `Ctrl+Z`, os códigos 1, 3, 4 e 5 do `--selftest`),
onze na triagem da S-511, o motor e o OCR de legenda na S-523 -- e nenhuma quebrava teste, porque o
teste de cada uma seguia verde medindo a decisão sozinha. A guarda que faltava é
`tests/test_ui_orfaos.py`; a que fecha a fronteira pelo outro lado é `tests/test_ui_fronteira.py` (S-549).

### Critério de aceite

- Nenhum módulo de `ui/` importa toolkit. ✅ (guarda genérica só na S-549)
- `ttkbootstrap` fora do `pyproject.toml`; `PyQt6` nas dependências de base; `collect_submodules` sem
  filtro e `chess_diagram_ocr.qt` fora do `excludes`. ✅
- `qt/janela.py` na catraca: **1.196** linhas no corte, contra as 2.327 do `app_tkinter.py` -- a
  diferença é a camada pura sendo chamada em vez de reescrita. ✅
- Cada varredura traduzida acha alguma coisa numa fonte de mentira. ✅
- Suíte no corte: 4.282 passam, 3 falham -- as mesmas três de antes (duas contagens de amostra que o
  `docs/` ainda não alcançara, e a guarda S-218, vermelha por decisão desde 2026-08-30). ✅

### Testes

- `tests/test_packaging.py::SpecTests::test_o_pacote_da_janela_entra_no_varrimento` e
  `::TamanhoDaJanelaTests` (a catraca `LIMITE`, com cada subida registrada).
- `tests/test_editor_model.py::SemTkinterTests::test_a_lista_cobre_todo_modulo_de_ui_que_hoje_dispensa_tkinter`
  -- depois do corte, **todo** módulo de `ui/` está na lista.
- As varreduras traduzidas: `tests/test_busy.py` (`ARQUIVOS_COM_THREAD` aponta para `qt/`, com
  `Tarefa(`), `tests/test_ui_estilos.py::TodoBotaoDeclaraPapelTests`,
  `tests/test_ui_texto_cor.py::SemHexadecimalTests`, `tests/test_strings.py` (`CHAMADAS` do
  `QMessageBox`), `tests/conftest.py` (`CAIXAS`), `tests/test_disciplina_da_suite.py::UmaRaizSoTests`,
  `tests/test_docs.py::test_as_threads_citadas_batem_com_as_do_codigo`.
- O que o corte achou e portou: `tests/test_qt_tema.py::DesabilitadoSeVeTests`,
  `tests/test_qt_painel_do_pdf.py::ControlesDoLivroTests`, `tests/test_qt_tabuleiro.py::ConjuntoDePecasTests`,
  `tests/test_qt_janela.py::EstadoEntreSessoesTests::test_o_estado_do_tk_e_herdado_uma_vez_e_nao_reescrito`,
  `::AparenciaTests`, `::DesfazerTests`, `::FiacaoTests::test_ler_melhor_e_ler_pagina_deixaram_de_ser_o_mesmo_comando`,
  `tests/test_app_pyqt.py::SelftestTests` (os códigos que voltaram a ter dono).

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-580 · O fim da faixa reservada — não é item

A mensagem do commit `eb3ba71` cita a faixa "S-527 a S-580", e a guarda `test_todo_item_entregue_tem_secao_em_algum_doc` lê
números em mensagem de commit como entrega. Esta seção existe para dizer que **S-580 é o limite superior da
reserva**, e não um item: quando a faixa for ocupada até aqui, o número recebe a seção de verdade e este parágrafo sai.
