# Especificação da segunda revisão externa — Fase 79 (S-522 a S-526)

Os itens do `LEIA-ME.md` que chegou de fora em 2026-09-02, **medidos contra este ramo antes de
virarem proposta**. O placar, o que já estava feito, as divergências e o que ficou de fora estão em
[ROADMAP_REVISAO_EXTERNA_2.md](ROADMAP_REVISAO_EXTERNA_2.md).

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

Cada item tem **Problema** (com `arquivo:linha` do estado em `44ce78c`, a ponta da
`triagem-dos-orfaos` no dia da conferência), **Solução**, **Critério de aceite** e **Testes**. As
medições de tela foram feitas com um script que monta os controles com a folha aplicada, sob
`QT_QPA_PLATFORM=windows` (estilo `windows11`) e sob `offscreen` (estilo `fusion`), e lê o pixel da
borda contra o pixel da superfície três pixels ao lado; o número é a razão de contraste WCAG.

---

## S-522 · A moldura que o estilo da plataforma não dá, derivada da superfície — ✅ **implementada em 2026-09-02**

### Problema

A folha de `qt/tema.py` declara `QWidget { background-color: ... }`. No `windows11` -- o estilo que o
Windows entrega -- uma propriedade de folha num widget faz o estilo **parar de desenhar o cromo
nativo dele**: o preenchimento entra, e a moldura não vem de lugar nenhum. Medido na janela de
verdade, borda contra superfície:

| controle | clássica, antes | "Foco", antes | clássica, `offscreen` | "Foco", `offscreen` |
|---|---|---|---|---|
| `QPushButton` | 14,74 (token errado) | 1,17 | 2,02 | 1,10 |
| `QComboBox` | 1,14 | 1,02 | 2,02 | 1,10 |
| `QTableWidget` | 1,14 | 1,02 | 1,72 | 1,09 |
| `QLineEdit` · `QSpinBox` · `QTextEdit` · `QListWidget` | 1,14 | 1,02 | — | — |
| `QGroupBox` | 14,74 (token errado) | 1,04 | — | — |

Seis controles sem moldura nas duas peles. E a CI não podia ver: sob `offscreen` o Qt escolhe o
`fusion`, que desenha o cromo mesmo com folha, e a fotografia dava 2,02 e 1,10 pelo mesmo código.

**A causa raiz é de fronteira, e não de cor.** `qt/tema.py` pintava a moldura do botão comum e do
`QGroupBox` com `moldura = cor(tokens.MOLDURA)`, e `MOLDURA` está em `SUPERFICIES_DE_DOCUMENTO` --
é o anel do tabuleiro, que a S-224 prendeu na paleta medida de propósito. Sobre o cromo claro isso
dá uma linha quase preta (14,74:1); sobre o cromo escuro da "Foco", `#1f1d1b` sobre `#1f2124` --
**1,04:1**. Usar token de documento para pintar cromo é a S-224 atravessada no sentido contrário.

O separador da fila (`qt/fila.py:105`) tinha o mesmo defeito por outro caminho: um `QFrame.VLine`,
que desenha com a cor de **texto** da paleta e não com a da folha -- medido, 2 px em `#848688` na
"Foco" e `#787878` na clássica, com o docstring afirmando o contrário.

### Solução

**A moldura passa a ser derivada da superfície em que é desenhada**, `tokens.moldura_sobre`: a
superfície puxada na direção da letra que se lê sobre ela (`sobre_superficie`), no menor peso que
cruza o piso gráfico de 3:1 (`AA_GRAFICO`). Uma pele nova não tem como nascer com borda invisível,
porque não há valor a esquecer. Resultado: `#8a8a8a` sobre o cromo claro, `#696b6d` sobre o escuro,
`#939389` sobre o balão de dica.

A folha declara `border: 1px solid` para `CONTROLES_COM_MOLDURA` -- `QComboBox`, `QLineEdit`,
`QSpinBox`, `QAbstractItemView` (lista, árvore, tabela), `QTextEdit`, `QPlainTextEdit` -- e troca o
token nas regras que já a tinham (botão comum, `:disabled`, `QGroupBox`, `QToolTip`). O separador
da fila vira um `QWidget` de 1 px com `objectName` `separador-da-fila`, pintado pela folha com a
mesma moldura.

### Critério de aceite

- Borda contra superfície ≥ 3:1 nas duas peles, nos oito controles, no `windows11`. ✅ Medido
  depois: **3,03** na clássica e **3,02** na "Foco", os oito iguais.
- O separador da fila tem 1 px e a cor da moldura, nas duas peles. ✅ `#8a8a8a` e `#696b6d`,
  1 pixel pintado, vizinhos na superfície.
- A folha do cromo não cita `tokens.MOLDURA`. ✅

### Testes

- `tests/test_ui_tokens.py::MolduraSobreTests` -- passa no piso sobre o cromo das duas peles e sobre
  **toda** superfície de `tokens.SUPERFICIES`; é a borda mais discreta que cruza o piso; o token de
  documento dá 1,04:1 no escuro.
- `tests/test_qt_tema.py::MolduraDoCromoTests` -- todo controle da lista tem moldura declarada e
  visível nas duas peles; a folha não pinta cromo com o token de documento; a moldura é a derivada;
  a dica tem a da superfície dela; o separador é pintado pela folha; e o controle da leitura
  (acha e deixa de achar), na forma da S-506.
- `tests/test_qt_fila.py` -- toda ação em destaque vira pílula; um separador entre grupos e nenhum
  na ponta; o separador é 1 px da moldura do cromo, **medido no `grab()`** nas duas peles -- aqui o
  pixel vale, porque é a folha quem pinta.

---

## S-523 · O motor e o OCR de legenda chegam à janela pelas preferências — ✅ **implementada em 2026-09-02**

### Problema

`qt/janela.py:204-205` construía o serviço sem leitor de legenda e lia as preferências só para o
OCR de glifos:

    self._servico = servico if servico is not None else OcrService(model_path=DEFAULT_MODEL_PATH)
    self._ocr = load_settings().ocr

Duas consequências, as duas silenciosas por construção:

1. **O motor de análise nunca aparecia.** `PainelDeEstudo` aceita `analyzer` desde o porte e
   `qt/janela.py:352` nunca passava um. `None` **esconde a seção inteira** (S-33, e a decisão está
   certa), então uma máquina com Stockfish mostrava exatamente o que uma máquina sem ele
   mostraria. `find_engine` e `EngineAnalyzer` tinham **zero chamadores** em `src/` -- também em
   `sala-de-estudo-no-qt` e `triagem-dos-orfaos`, que só leem `load_settings().ocr`.
2. **O OCR de legenda (S-43) nunca chegava ao serviço.** `service.py:494` diz por escrito que *quem
   lê a configuração é a interface*; a interface não lia, o `caption_reader` era sempre `None`, e o
   pipeline sem ele é o pipeline de sempre. A perda pesa nos livros sem camada de texto, onde a
   legenda é a única pista do número do lance.

Do lado do Tk as duas ligações existiam (`_build_analyzer`, e o serviço construído com
`caption_reader_from_settings`); o corte as levou sem que nada acusasse. É o padrão da S-500 a
S-512, e o achado é da segunda revisão externa.

### Solução

`qt/preferencias.py`, sem widget: `servico_das_preferencias` (o `OcrService` com o leitor que as
preferências autorizam) e `motor_das_preferencias` (`find_engine` pelo caminho das preferências,
que é o único que alcança um binário fora do `PATH`; `EngineAnalyzer` com `movetime_ms` e
`threads` de lá; o processo **não** abre aqui). A janela recebe `motor: EngineAnalyzer | None |
"preferencias"` -- `None` é "sem motor", e não "procure" -- e passa-o à sala em `analyzer=`. No
`closeEvent`, depois de gravar o estado, `self._motor.close()`: um motor é um processo, não um
widget, e sem isso cada abertura deixaria um `stockfish.exe` vivo.

Os dez sítios de teste que montam a janela passam `motor=None`, pelo mesmo motivo de
`caminho_do_estado`: uma suíte que procurasse binário a cada janela dependeria do `PATH` de quem a
roda. A catraca de `qt/janela.py` sobe 1.788 → 1.805 com o motivo escrito.

### Critério de aceite

- Com um binário nas preferências (ou no `PATH`), a sala mostra a seção "Motor (nome)". ✅
- Sem binário, nada muda. ✅
- Fechar a janela encerra o motor. ✅
- O serviço do produto nasce com o `caption_reader` de `caption_reader_from_settings`. ✅

### Testes

- `tests/test_qt_preferencias.py` -- sem `QApplication`: o caminho das preferências vira motor sem
  abrir processo (`name` ainda é o nome do arquivo); caminho informado que não existe não cai no
  `PATH`; caminho vazio delega a `find_engine`; OCR desligado dá `caption_reader` `None`; o leitor
  autorizado chega ao serviço.
- `tests/test_qt_janela.py::MotorDasPreferenciasTests` -- o motor injetado chega à sala; sem motor
  a seção não existe; o padrão é `motor_das_preferencias`; fechar a janela encerra o motor; o
  serviço padrão vem de `servico_das_preferencias`.

---

## S-524 · O auto-teste com estado descartável, e sem procurar motor — ✅ **implementada em 2026-09-02**

### Problema

`app_pyqt.py:160` montava a janela do `--selftest` com `JanelaPrincipal(servico=servico)`: o
arquivo de estado do produto (`data/janela.json`), e a procura de motor do produto. A revisão de
fora viu, numa árvore em que a janela gravava a cada gesto, o auto-teste apagar o livro e a página
em que a pessoa estava -- *conferir a instalação apagava a sessão*. Aqui não mordia, porque esta
janela grava só no `closeEvent` e o auto-teste não o dispara; mas "não morde hoje" depende de
*quando* a janela grava, e isso é decisão de outro item.

### Solução

`_janela_do_auto_teste(servico, descartavel)`: `motor=None` e `caminho_do_estado` numa pasta
temporária, apagada no `finally`. A pergunta do auto-teste é "esta instalação lê um diagrama?", e
nem a sessão da pessoa nem um binário de motor fazem parte dela.

### Critério de aceite

- O auto-teste não lê nem grava `data/janela.json`. ✅
- O auto-teste não procura motor. ✅

### Testes

- `tests/test_app_pyqt.py::JanelaDoAutoTesteTests` -- o caminho do estado é o da pasta descartável e
  não `CAMINHO_DO_ESTADO`; a sala não tem motor.

---

## S-525 · A ARCHITECTURE descreve o programa que existe — ✅ **implementada em 2026-09-02**

### Problema

`docs/ARCHITECTURE.md:170` dizia *"A interface é Tkinter + `ttk` + `ttkbootstrap`, ~2.900 linhas em
18 módulos"* e *"A recomendação é ficar no Tk"*, com dois gatilhos para sair -- um mês depois de o
corte ter saído por um terceiro motivo. A tabela de `ui/` (`:137-160`) listava treze módulos que o
corte apagou (`pdf_panel`, `result_panel`, `study_panel`, `board_render`, `theme`...). E
`README.md:74` dava a `qt/janela.py` 1.193 linhas, o número do dia do corte, com a catraca em 1.788.
O achado é o S-510 da revisão de fora, e ele reproduz: nenhum dos três é conferido por guarda, porque
`test_todo_modulo_citado_como_interface_existe` só olha `app_*.py`.

### Solução

A seção da interface passa a descrever `qt/` (uma tabela por responsabilidade, com o que cada
módulo delega a `ui/`) e a regra de `ui/` -- inclusive a segunda pergunta, "quem chama?", e a guarda
`tests/test_ui_orfaos.py`. A seção do framework conta o que aconteceu em vez de recomendar: os dois
gatilhos que não dispararam, o que disparou (a fronteira da S-31 pôde ser testada), o que o corte
custou (os chamadores), e o que continua Tk de propósito. A frase do `labels.csv` fica, porque a
S-135 a confere. O README diz o número de hoje pela catraca, e não por um literal que envelhece.

### Critério de aceite

- Nenhum módulo citado na tabela da interface deixou de existir. ✅
- A ARCHITECTURE não recomenda um toolkit que o produto não usa. ✅
- `tests/test_docs.py` inteiro verde, inclusive os números vivos. ✅

### Testes

- Os que já existem em `tests/test_docs.py` (`NumerosVivosTests`, a tabela de persistência, as
  threads). Guarda nova para a tabela de módulos ficou de fora de propósito: a de `app_*.py` já
  mostrou que uma lista de nomes conferida contra o disco pega o módulo apagado e não a descrição
  errada, e é a descrição que este item corrigiu.

---

## S-526 · A régua de alinhamento do recorte, no censo — ✅ **implementada em 2026-09-02**

### Problema

Nenhuma métrica do projeto responde *"o recorte está alinhado com as casas?"*. `board_checker_score`
mede textura de damero, não deslocamento; `field_eval` mede quantos diagramas saíram; a fila de
revisão ordena confiança. Um recorte deslocado de 15 px tem textura de tabuleiro, passa no detector,
e a peça cai na casa vizinha -- para o classificador uma casa é o que o recorte diz que é, e o erro
sai como erro do modelo. A revisão de fora trouxe a régua e o método; o que faltava era o número
desta bancada.

### Solução

`alinhamento.py`, puro: o damero ideal deslizado de −24 a +24 px nos dois eixos sobre o recorte de
800 px; o deslocamento em que as duas paridades mais diferem é o desalinhamento (`Encaixe.dx`,
`.dy`, `.forca`). Imagem integral e 64 médias por deslocamento. `LIMITE_DE_DESALINHAMENTO_PX = 12`
(acima disto a peça começa a cair na casa vizinha); `ALCANCE_PX = 24`, menos de meia casa, porque
a partir dali o damero de uma casa adiante encaixa de novo com as paridades trocadas;
`FORCA_MINIMA = 0,02`, abaixo do qual não há damero e a resposta é `SEM_DAMERO` (−1) em vez de um
deslocamento aleatório.

**A primeira régua da revisão de fora estava errada, e fica registrado:** ela procurava picos de
energia de borda por coluna, e nestes livros as casas são cor sólida enquanto as peças têm a borda
mais forte -- ela dizia 100% de desalinhados numa folha de contato de doze tabuleiros impecáveis.

No censo (`detection_census.py`), a coluna `desalinhamento_px` por candidato, ao lado de `texture`,
medida no recorte entregue; `BookCensus.misaligned` e o total no resumo do `cvoff-census`; e
`read_census_csv` tolera o CSV de antes da coluna, porque é ele que o `--baseline` lê.

**Calibração, em 300 dos 5.833 recortes aprovados de `data/samples/`** (semente 526):

| medida | valor |
|---|---|
| força no melhor encaixe | mín 0,054 · p05 0,102 · mediana 0,200 · máx 0,600 |
| deslocamento 0 px | 25 |
| 1 a 4 px | 256 |
| 5 a 12 px | 18 |
| acima de 12 px | **1** |
| tempo por recorte | 67 ms médio, 80 ms máximo |

O piso de 0,02 fica a 2,7× abaixo do menor tabuleiro real, e uma imagem lisa dá 0. O único recorte
acima do limite é um tabuleiro do Lichess recortado **com a legenda embaixo** -- as oito fileiras
espremidas em ~770 px --, isto é, um recorte de verdade defeituoso que passou pela aprovação humana.

### Critério de aceite

- Damero sintético deslocado de (sx, sy) volta (sx, sy) em pixel, com e sem peças. ✅
- Cor lisa responde `SEM_DAMERO`, e não um número. ✅
- O CSV de antes da coluna continua legível, e o diff da S-82 não muda. ✅
- Cabe no censo: < 100 ms por recorte. ✅

### Testes

- `tests/test_alinhamento.py` -- alinhado encaixa em zero; o deslocamento volta em pixel nos dois
  eixos; peças não enganam a régua; o limite separa alinhado de desalinhado; cor lisa não tem
  damero; recorte pequeno demais não levanta; cinza e RGB dão o mesmo; o alcance é menor que meia
  casa; é rápida o bastante.
- `tests/test_detection_census.py::AlinhamentoNoCensoTests` -- o CSV de antes da coluna ainda é
  lido; a coluna vai e volta; desalinhado é acima do limite, e `SEM_DAMERO` fica de fora da conta.
