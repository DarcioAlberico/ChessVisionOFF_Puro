# Roadmap da segunda revisão externa — Fase 79

Uma segunda revisão independente, do mesmo autor da primeira ([ROADMAP_REVISAO_EXTERNA.md](ROADMAP_REVISAO_EXTERNA.md),
Fases 66 a 68), escrita em 2026-09-01 sobre o `corte-do-tk` (653f88b) integrado com a `main`
(f124370) e recebida aqui em 2026-09-02. Especificação item a item em
[SPEC_REVISAO_EXTERNA_2.md](SPEC_REVISAO_EXTERNA_2.md) (S-522 a S-526).

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

Este documento não propõe recurso novo. Ele é o que sobrou de seis itens e um teste de acervo
**depois de cada um ser conferido contra este ramo** -- que está três PRs à frente do que a revisão
viu (#27, #29 e #30).

**Data da conferência:** 2026-09-02 · **Ramo:** `triagem-dos-orfaos` · **HEAD:** `44ce78c` ·
**Método:** cada afirmação do `LEIA-ME.md` reproduzida ou refutada nesta árvore, com o comando
registrado. O item principal foi **remedido no estilo `windows11`** com o método do próprio
relatório -- razão de contraste entre a borda do controle e a superfície atrás dele, pixel a pixel
-- e depois sob `offscreen`, para saber o que a CI vê. Nada foi aplicado: o material recebido é
dado, não instrução.

---

# O que chegou

| arquivo | o que é |
|---|---|
| `LEIA-ME.md` | 16 KB: seis itens sobre a janela do Qt (S-507 a S-512 na numeração dele), um teste em cinco livros do acervo, e as instruções de aplicação |

Só isso. O documento cita `patches/*.patch`, `docs/SPEC_JANELA_DO_QT.md`, `antes-e-depois/` e
`recortes-do-acervo/`, e **nenhum deles veio** -- não há o que aplicar com `git am`, só ideias para
conferir. A pasta `Perego/` continua fora do git (17ba228), como na primeira revisão.

Sobre a qualidade do que veio, vale o mesmo que na primeira: o relatório mede o que afirma, e desta
vez registra a própria régua errada antes de a certa -- *"o número errado quase virou um achado"*.
A observação que ele repete quatro vezes, **guarda ajustada ao defeito** (`lambda: None` satisfaz
"todo item de menu tem comando"; seis abas cravadas contra a tupla de sete), é a mesma que a triagem
da S-511 fez daqui, um dia antes, sem que um soubesse do outro.

---

# O placar

| item dele | o que é | veredito nesta árvore | virou |
|---|---|---|---|
| S-507 | a moldura que o `windows11` não desenha | **reproduz exato**: 1,19/1,14/1,14 na clássica e 1,03/1,02/1,02 na "Foco" para botão, combo e tabela, mais quatro controles que ele não mediu; a CI vê 2,02 e 1,10 pelo mesmo código | **S-522** |
| S-508 | as três peles voltam a existir | **já feito** (PR #25 e #27: `qt/fila.py`, `_remontar_cromo`, `menu.escolhido`, `aplicar_tema` com pele e densidade). O detalhe do separador em `#848688` reproduz e entrou na S-522 | — |
| S-509 | a janela lembra onde a sessão parou | **já feito** (`data/janela.json`, `remember_page` a cada página, `showEvent` para o divisor, guarda `isVisible`). As três armadilhas de ordem dele estão tratadas, por outro desenho: ver as divergências | — |
| S-510 | o documento descrevia o programa de antes do corte | **confirmado**: `docs/ARCHITECTURE.md:170` dizia "A interface é Tkinter + ttk + ttkbootstrap" e recomendava ficar no Tk | **S-525** |
| S-511 | o motor e o OCR de legenda nunca chegam à janela | **confirmado, e em todos os ramos**: zero chamadores de `find_engine` e `EngineAnalyzer` em `src/`; `PainelDeEstudo` sem `analyzer`; `OcrService` sem `caption_reader` | **S-523** |
| S-512 | os quatro campos do arranjo sem dono | **já feito** (`definir_quebra`, `reabrir_por_chave`, `texto_zoom`, `estudo_divisor`; `show_heatmap`, `piece_set`, `piece_dir` e `review_queue_path` também). Só `board_zoom` fica de fora, e é omissão deliberada | — |
| a régua | alinhamento do recorte pelo damero deslizado | **sem equivalente aqui** (`board_checker_score` mede textura, não deslocamento); implementada e **calibrada em 300 recortes aprovados** | **S-526** |
| o `--selftest` | gravava o livro e a página da pessoa | **não morde aqui** -- esta janela grava só no `closeEvent`, que o auto-teste não dispara --, e custa uma linha fechar de vez | **S-524** |
| `test_field_eval` vermelho | a impressão digital dos relatórios de campo | **já verde**: remedição num worktree limpo (fdf99e4, PR #27) | — |
| a sétima aba | `abas.ABAS` declara Configuração e a janela monta seis | **aberto, e já tratado na triagem** (PR #30: a janela lê a tupla, e a Configuração saiu dela). O item grande -- DPI, máximo de diagramas, caminhos, em `config.py` -- continua aberto | fora |

---

# As quatro divergências

O que uma revisão de fora não pode ver é o que a bancada de fora não tem: os três PRs seguintes.

1. **A numeração dele colide.** S-507 a S-512 são, aqui, as Fases 73 a 77 (a sala de estudo no Qt),
   e a S-521 já é a digitação que chega ao documento. Os itens aceitos entram como **S-522 a S-526**.
   As S-452 e S-455 que ele cita como a correção do enviesamento do Traxler não existem aqui com
   esse sentido -- a S-452 é o `--dedupe`, e a S-455 não existe.
2. **Esta janela grava a sessão no `closeEvent`, e a dele grava a cada gesto.** É o que faz a
   terceira armadilha de ordem dele (`abriu_pdf` gravando `last_page = 0` antes de restaurar a
   página) não existir aqui, e é o que fazia o `--selftest` dele apagar a sessão e o daqui não. O
   outro lado da moeda é que uma queda do processo perde a sessão inteira aqui. **É decisão de
   desenho, e fica registrada em vez de tomada**: gravar por gesto reabre as três armadilhas, e
   nenhuma delas tem guarda hoje.
3. **A CI mede o `fusion`.** Sob `QT_QPA_PLATFORM=offscreen` o Qt escolhe um estilo que desenha o
   cromo mesmo com folha aplicada; a fotografia da CI dava 2,02:1 (clássica) e 1,10:1 ("Foco") para
   os mesmos controles que no `windows11` davam 1,14 e 1,02. É a forma da S-325 e da S-506, de
   novo: a guarda da S-522 afirma a **folha**, não o pixel, e a medição de pixel fica na spec com
   o comando -- ela só vale na máquina.
4. **O que ele mediu como faltando já tinha entrado**, três vezes (S-508, S-509, S-512), porque a
   revisão viu o `corte-do-tk` e não os PRs #25, #27, #29 e #30. Não é defeito da revisão: é o
   preço de revisar um ramo que anda. Fica como regra para a próxima: dizer ao revisor qual é a
   ponta.

---

# O que ficou de fora, e por quê

- **A sétima aba (Configuração).** É o maior item aberto, e continua sendo: DPI, máximo de
  diagramas por página, orientação, caminho do modelo e conjunto de peças são constantes em
  `config.py`, sem como mudar sem editar código. Merece plano próprio com medição, e não um item
  no fim de uma revisão -- a triagem (PR #30) já tirou a aba da tupla para a guarda parar de
  mentir, que é a metade que cabia agora.
- **A gravação por gesto** (divergência 2): decisão de desenho, com as três armadilhas de ordem
  para guardar antes de mudar.
- **As folhas de contato e os recortes do acervo dele.** Não vieram; o teste no acervo foi
  refeito com o que existe aqui -- os 5.833 recortes aprovados de `data/samples/` -- e a
  calibração está na S-526.
- **O risco do rodapé.** `qt/rodape.py:86` desenha o traço de cima com um `QFrame.HLine`, a mesma
  forma que o separador da fila tinha. Não foi medido; fica nomeado para quem for lá.

---

# A ordem, e o que cada fase entrega

**Fase 79 — a segunda revisão externa.** Cinco commits, um por item, cada um com o seu teste; o
sexto é este documento e a spec.

- **S-522** · A moldura derivada da superfície (`tokens.moldura_sobre`), declarada para os seis
  controles que o `windows11` deixou sem ela, e o separador da fila de 1 px pintado pela folha.
  Medido depois: 3,03:1 e 3,02:1 nas duas peles, nos oito controles.
- **S-523** · `qt/preferencias.py`: o serviço com o OCR de legenda e o motor pelo caminho das
  preferências; a janela recebe `motor=` injetável, passa-o à sala e o fecha no `closeEvent`.
- **S-524** · O auto-teste monta a janela com estado descartável e `motor=None`.
- **S-525** · `ARCHITECTURE.md` descreve o `qt/` e o `ui/` de hoje; o README deixa de citar um
  número de linhas de um mês atrás.
- **S-526** · `alinhamento.py`, a régua do damero deslizado, e a coluna `desalinhamento_px` no
  censo -- com o CSV de antes da coluna ainda legível.
