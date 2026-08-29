# Roadmap do editor de texto — Fases 36 a 40

O que a aba **Texto** é hoje, o que falta para ela ser um editor, e o plano para chegar lá **sem
que nenhum recurso novo morra junto com o widget**. Especificação item a item em
[SPEC_EDITOR.md](SPEC_EDITOR.md) (S-235 a S-293).

O reconhecimento que alimenta a aba está em [ROADMAP_TEXTO.md](ROADMAP_TEXTO.md) e
[SPEC_TEXTO.md](SPEC_TEXTO.md); a fundação de interface que este plano usa — tokens, tipografia,
estilos, catálogo de comandos, ícones — está em [SPEC_UI.md](SPEC_UI.md) e
[SPEC_APARENCIA.md](SPEC_APARENCIA.md). **Nenhuma fase daqui treina modelo nem mexe em detecção.**

**Data da avaliação:** 2026-08-24 · **Ramo:** `fase-5-modelo-desempenho` · **Aba avaliada:**
`src/chess_diagram_ocr/ui/texto_panel.py`, 416 linhas

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
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |

---

# O pedido, e a frase que ele esconde

> "Analisa a aba 'texto' e cria um editor com mais ferramentas. Como exportar, salvar, negrito,
> itálico, paleta de glifos e símbolos de xadrez, cores de texto etc."

Os seis recursos pedidos têm uma coisa em comum, e ela decide a ordem das fases: **negrito,
itálico, cor, glifo, estilo e faixa de confiança são todos atributos de um trecho de texto — e o
texto desta aba é uma `str`.**

O que a aba devolve quando alguém salva é isto, literalmente:

```python
def texto_atual(self) -> str:
    return self.editor.get("1.0", "end-1c")        # ui/texto_panel.py:381
```

Um `tk.Text` sabe pintar negrito: é uma *tag*. Sabe pintar cor: é uma tag. Sabe sublinhar: tag. E
**tag do Tk não é dado** — ela nasce no widget, vive no widget e morre com ele. Escrever os seis
recursos direto no widget dá um editor que funciona lindamente na tela e entrega, no botão
Salvar, exatamente o mesmo `.txt` de hoje.

Daí a arquitetura inteira deste plano, que é a mesma disciplina que a Fase 6 impôs ao pipeline e a
S-324 impôs aos comandos: **o documento é dado, fora do `tkinter`; o widget é um desenho dele.**
Por isso a Fase 36 não entrega um só botão novo — e é a fase sem a qual as outras quatro não valem
nada.

---

# A aba de hoje, medida

> **Esta tabela é de 2026-08-24, e as cinco fases fecharam em 2026-08-25.** Ela fica como estava
> porque é a medição que motivou o plano -- trocá-la pelos números de agora apagaria o *porquê* de
> cada item. O estado de hoje é publicado por `cvoff-editor-inventario`, em
> [`docs/metrics/editor_inventario_20260825.json`](metrics/editor_inventario_20260825.json): 28
> comandos no catálogo, 7 atributos de documento, 5 formatos de saída, 2 de entrada (`.cvtxt` e o
> rascunho), 124 símbolos na paleta e 3 teclas próprias do editor.


| o que ela tem | onde | quanto |
|---|---|---|
| controles na barra | `ui/texto_panel.py:137-161` | **6** — folha, "Da página aberta", motor, modo bloco, "Ler folha", "Salvar .txt" |
| tags de cor no editor | `ui/texto_panel.py:369-370` | **3** — `revisar`, `conferir`, `marca` |
| formatos de saída | `ui/texto_panel.py:383-412` | **1** — `.txt`, com cabeçalho de procedência |
| formatos de entrada | — | **0** — não existe "abrir" |
| comandos de edição | — | **0** — nenhum negrito, itálico, cor, busca, símbolo |
| comandos no catálogo da S-324 | `ui/comandos.py` | **0 dos 6** — a aba inteira está fora dos 36 do registro |
| atalhos de teclado próprios | — | **0** (e ver o achado 6) |
| decisões testáveis fora da janela | `text/documento.py` | **7 funções e um `Segmento`**, e é o que salva o resto |

O que ela **acerta**, e que este plano não toca: a leitura sai da thread da janela com
`BusyRegistry` e volta por `after`; a miniatura do diagrama entra no fluxo do texto sem apagar a
marca `[Diagrama N]`; a faixa de confiança é papel de `ui/tokens.py` e não hexadecimal; e o que
decide mora em `text/documento.py`, que não importa `tkinter`. **A fundação está certa. O que
falta é o que se constrói em cima dela.**

---

# Oito achados, e o item que cada um vira

**1 · Todo recurso escrito direto no widget morre no botão Salvar.** Já está acima, e é o achado
que ordena as fases. Somando o que a aba tem hoje: `texto_atual` devolve `str`
(`ui/texto_panel.py:381`); as três tags são configuradas no widget (`:369-370`); as miniaturas
vivem numa lista cujo próprio comentário diz por que ela existe — *"o Tk não segura a imagem"*
(`:117-119`); e `salvar` grava a `str` mais um cabeçalho (`:411`). A `PaginaLida` que originou
tudo fica em `self._pagina` e não entra em lugar nenhum da saída. → **S-235**

**2 · O itálico já é medido, e jogado fora.** `text/italico.py` mede o pendor da linha — mediana
do deslocamento do centroide de tinta do topo em relação ao da base — e a medição é boa: em 157
linhas da página 311 do `Secrets of Chess Training`, linha itálica em **+0,116** contra **+0,000**
em pé, sem sobreposição nenhuma. `e_italica` devolve `True`, `corrigir` usa a resposta para trocar
`/` por `l` (`text/italico.py:121`) — e o booleano se perde ali. `LinhaLida` tem `texto`, `bbox`,
`confianca` e `procedencia` (`text/pagina.py:290-293`), e não tem itálico.

O editor **não precisa de um pincel de itálico para mostrar itálico**: precisa de um campo. É o
item mais barato do plano, custa zero de tempo de leitura porque a medição já roda, e é o que faz
a aba mostrar a página como ela é impressa em vez de tudo em romano. → **S-236**

**3 · Negrito não é medido em lugar nenhum — e o classificador foi treinado para o ignorar.**
`grep -rn "negrito\|bold" src/chess_diagram_ocr/text/` devolve acerto em três arquivos, e nenhum é
detecção. O que existe é o contrário: `text/aumento.py:23` lista `espessura` entre as
**augmentações** — *"tinta gorda contra tinta fina: `bold`, papel absorvente, digitalização
escura"* — e o perfil do acervo a liga com probabilidade 0,5 (`aumento.py:113`). O modelo foi
deliberadamente ensinado a **não** distinguir traço gordo de traço fino, porque essa invariância é
o que o faz ler papel amarelado e scan escuro. Pedir negrito ao classificador é pedir de volta o
que se pagou para ele apagar.

A saída é a mesma do itálico: **geometria sobre a binária, fora do classificador.** E aqui há uma
referência de graça — ver o achado 4. → **S-237**

**4 · A camada de texto declara o estilo em 14 dos 41 livros, e é preciso saber quais.** Medido em
2026-08-24, 4 páginas amostradas de cada livro de `PDF/` (164 páginas, `flags` dos spans de
`get_text("dict")`):

| | livros |
|---|---:|
| têm camada de texto na amostra | 30 de 41 |
| **declaram itálico ou negrito** | **14** |
| declaram só o texto, sem estilo | 16 |
| não têm camada nenhuma | 11 |

`pdf_text.py` lê `span["font"]` desde a S-217 (`pdf_text.py:521`) — o **nome** da fonte, para
peneirar fonte de diagrama — e nunca leu `span["flags"]`, onde moram o bit de itálico e o de
negrito. São dois inteiros que o PyMuPDF já entrega em toda chamada que o projeto já faz.

Isso **não** resolve o problema, e é importante dizer por quê: os 27 livros restantes continuam
sem estilo, e entre os 14 há camadas de OCR de terceiro — a `Gaprindashvili` é
`_OCR_Aprimorar_Aprimorar` e declara 60 negritos que são palpite de *outro* OCR, não tipografia do
livro. A distinção **camada editorada** contra **camada de OCR** já existe neste projeto
(`text/leitor.py:84-85`), e vale igual aqui.

**Este número e o de `text/negrito.py` respondem a perguntas diferentes**, e os dois valem: aqui
são 4 páginas de 41 livros contando itálico **ou** negrito; lá são 6 páginas de 42 contando só
negrito, e dá 13.

O que os 14 dão é o que faltava para o achado 3: **um conjunto de referência gratuito para
calibrar a régua geométrica.** O `Dvoretsky - Endgame Manual (2025)` é digital nativo e traz 105
spans em negrito e 16 em itálico em 4 páginas; o `Kemeri 1937`, 445 negritos. Medir a espessura do
traço na página renderizada e conferir contra o que a camada declara na mesma página é exatamente
a forma da medição da caixa alta na S-211 — e é o que decide se o negrito **detectado** entra ou
se o item se declara não-medido. → **S-237**

**5 · A paleta de símbolos já existe, e ela é o `models/char_meta.json`.** São 314 classes, e a
contagem por família diz o que a paleta tem para oferecer:

| família | quantas | exemplos |
|---|---:|---|
| alfanuméricas ASCII | 62 | `a`–`z`, `A`–`Z`, `0`–`9` |
| símbolos ASCII | 24 | `! " # % & ' ( ) * + , - . / : ; = ? @ [ ] _ \| ~` |
| Unicode fora do ASCII | 89 | `♔ ♕ ♖ ♗ ♘ ♙ ± ∓ ⩲ ⩱ ∞ ⇄ → ½ – — •` |
| ligaduras | 139 | `!! !? ?! ?? +- -+ fi ffl ♕x ♗a xf6 e4` |

**Escrever a paleta à mão seria escrever uma segunda lista de símbolos ao lado da que o modelo
usa** — e a primeira divergência entre as duas é um símbolo que a pessoa insere e que o OCR nunca
poderá ler de volta. A paleta sai do metadado, como a barra de menus saiu do catálogo na S-324.
→ **S-246**

**E um achado seco que sai da mesma contagem: as seis figurinas são só as brancas.** `♔♕♖♗♘♙` são
classes; `♚♛♜♝♞♟` não são. Isso não é buraco da base — é o que o acervo imprime, porque em notação
figurina o símbolo diz a *peça* e o número do lance diz a *cor*. Mas decide o desenho da paleta: o
que o modelo não lê vai para uma prateleira **marcada**, e não misturado com o resto, porque
inserir `♞` num texto que vai voltar para a fila de revisão de caractere é inserir algo que
nenhuma classe pode confirmar. → **S-247**

**6 · Cor de texto colide com a cor que já significa alguma coisa.** A aba pinta três tags:
`revisar` em `tokens.PROBLEMA`, `conferir` em `tokens.ATENCAO`, `marca` em `TEXTO_SECUNDARIO`
(`ui/texto_panel.py:64-76`). Naquela tela, vermelho quer dizer **"o motor estava adivinhando"** —
o corte é o `MIN_CONFIDENCE` da S-42, emprestado de propósito para a aba não discordar do resto do
programa sobre o que é palpite (`text/documento.py:8-20`).

Dar ao autor um botão de cor com vermelho na paleta produz duas tintas iguais com dois
significados na mesma linha, e ninguém consegue desfazer isso olhando. Pior: um vermelho cravado
em hexadecimal some no tema escuro, que é o defeito que a S-146 mediu no tabuleiro e que a regra 3
da SPEC_APARENCIA proíbe.

A saída não é recusar cor — é **separar os canais**: confiança e autor não podem ocupar o mesmo.
→ **S-242**

**7 · No editor, `Ctrl+S` não faz nada — e `Ctrl+I` insere uma tabulação.** Os dois são
verificáveis sem abrir a janela, e são de donos diferentes.

Do lado do projeto: `shortcuts.TEXT_ENTRY_WIDGETS` inclui `tk.Text`, e `guard` cede a tecla quando
o foco está num deles (`ui/shortcuts.py:19-24, 69-77`). É deliberado desde a S-20, e a razão está
escrita lá: `←` dentro de um campo pertence ao campo. O efeito colateral é que **os dez atalhos
globais passam direto pelo editor de texto**.

Do lado do Tk: `bind Text <Control-KeyPress> {# nothing}` (`tk8.6/text.tcl:306`). Somando os dois,
`Ctrl+S` com o cursor no texto não salva a posição — a guarda cedeu — e não salva o texto — ninguém
ligou. A tecla mais esperada de um editor é hoje um silêncio de duas camadas.

A segunda metade é pior porque é silenciosa:

```tcl
bind Text <Control-i> {              ;# tk8.6/text.tcl:211
    tk::TextInsert %W \t
}
```

**A tecla universal de itálico já é a de tabulação**, e o comentário três seções acima, em
`text.tcl:300-302`, diz o que acontece com quem ligar a tecla sem devolver `"break"`: a ligação do
widget dispara *e* a da classe também, e sai o itálico **mais** um tab.

Nada disso se resolve tirando a guarda — ela existe por medição. Resolve-se tornando o ceder
**tipado**: quem tem o foco declara quais ações são dele, e "Salvar" passa a significar "salvar o
que está em foco". → **S-243 e S-244**

**8 · A correção humana é a única coisa desta aba que não sai de graça de uma releitura, e é a que
o programa não guarda.** A docstring de `salvar` já sabe disso — *"se alguém corrigiu uma palavra,
é a correção que tem valor"* (`ui/texto_panel.py:386-388`). O que ela grava é um `.txt` num lugar
escolhido no diálogo: sem faixa, sem diagrama, sem `PaginaLida`, e **sem volta** — não existe
"abrir" no editor. Reler a folha descarta tudo, e a caixa de confirmação de `ler` (`:224-230`) é o
programa avisando que vai fazer isso.

E há um destino esperando por essa correção que hoje não a recebe: a S-212 (fila de revisão de
caractere) e a S-213 (aplicar a todos os semelhantes) precisam justamente de "o que uma pessoa
corrigiu, e sobre que glifo". O editor é o lugar onde isso acontece, e ele joga fora.
→ **S-238 e S-239**

**E o que já está pronto e o editor não usa.** O programa exporta PGN por um controlador com
thread, progresso, cancelamento e relatório (`ui/export_controller.py`, 275 linhas); abre e escreve
PDF com PyMuPDF, que já é dependência; e tem a S-210 planejada para a camada de texto invisível. O
botão "Salvar .txt" ignora os três. → **S-250 a S-254**

---

# As cinco fases

| fase | itens | o que ela entrega |
|---|---|---|
| **36** — o documento que sobrevive ao widget ✅ | S-235 a S-239 | o texto rico como dado, o itálico que já se mede, o negrito medido ou declarado não-medido, o arquivo que reabre e a procedência da correção |
| **37** — as ferramentas de edição ✅ | S-240 a S-245 | negrito/itálico/sublinhado, cor de autor sem colidir com a confiança, desfazer, `Ctrl+S`, achar e substituir |
| **38** — a paleta de glifos e símbolos ✅ | S-246 a S-249 | a paleta gerada do modelo, a prateleira do que ele não lê, as três formas de inserir e o estilo de parágrafo |
| **39** — a exportação ✅ | S-250 a S-254 | um lugar só decide o diagrama, `.md`/`.html`/`.rtf`, o PDF pesquisável do próprio livro, e nada disso na thread da janela |
| **40** — o que sustenta o resto ✅ | S-255, S-256 | o rascunho automático e o inventário que impede recurso sem comando |

**Fora das cinco fases, dois itens de medição.** Eles não entregam recurso: entregam número sobre
uma régua que o editor já usa.

| item | estado | o que ela disse |
|---|---|---|
| **S-257** · a margem da coluna: mediana ou quantil baixo | ✅ medida e **recusada** | dois acertos em 323 separam os dois candidatos — a mediana fica. No caminho, achou a régua vizinha que **tem** vão |
| **S-258** · o limiar de recuo é 0,8, e a medição diz 0,4 | ⬜ planejada | 25 cortes certos a mais por um falso a mais. Mexe no texto que o leitor entrega, e por isso é item com remedição junto |

A referência de parágrafo que as duas usam está versionada em
`docs/metrics/texto_paragrafo_referencia.jsonl`, e a de notação, que fechou a dívida da S-249, em
`docs/metrics/texto_notacao_referencia.jsonl`.

## Fase 36 — O documento que sobrevive ao widget

Vem primeiro porque **as outras quatro escrevem nela**, e porque é a única cujo valor não aparece
na tela: ao fim dela a aba está quase igual — só o itálico da página impressa passa a aparecer —
e o que mudou é que existe um documento para as ferramentas editarem.

- **S-235** · O documento rico como dado, e não como tag do widget — ✅ **implementada em 2026-08-24**
- **S-236** · O itálico que o leitor já mede e joga fora — ✅ **implementada em 2026-08-25**
- **S-237** · O negrito: a espessura medida, ou dita não-medida — ◐ **parcial**: a camada entrou, a
  rota geométrica foi medida e recusada, o itálico não entrou
- **S-238** · O arquivo do editor: salvar e reabrir sem perder diagrama, faixa nem correção —
  ✅ **implementada em 2026-08-24**
- **S-239** · A correção humana carimba procedência, e vai para onde a S-212 a espera —
  ✅ **implementada em 2026-08-24**

> **Onde a fase está.** A S-235 entregou `text/rico.py` — `Atributos`, `Corrida`, `DocumentoRico`,
> `fundir`, `de_pagina` —, 31 casos em `tests/test_texto_rico.py` e o painel desenhando o documento
> em vez de percorrer `documento.segmentos`. A trava de não-regressão é afirmada com um `tk.Text` de
> verdade em `tests/test_ui_texto_editor.py`: **o texto do widget é idêntico ao `para_texto()`**.
>
> Quatro decisões da implementação divergem do desenho e estão escritas na spec; a que mais importa
> é que `cor` **não** valida contra `ui/tokens.py` — isso faria `text/` importar `ui/` e inverteria a
> camada. O domínio nomeia, a interface resolve em tinta, como `PAPEL_DA_FAIXA` já fazia.
>
> A S-237 chegou por outro caminho e antes desta spec: `text/negrito.py`, escrito sob a S-211, traz o
> negrito da camada e **mediu a rota geométrica antes de recusá-la** — espessura do traço em 82,2%
> contra 82,7% de chutar "normal" sempre. É o portão do item, atravessado com número. Falta o lado do
> itálico, que é a S-236.
>
> **Ao fim da S-235 a tela é a mesma**, e é o combinado: a fundação se prova quando ela não muda
> nada. O que mudou é que existe um documento para as ferramentas da Fase 37 editarem.
>
> A S-238 fechou o ciclo: `text/arquivo.py` grava o `.cvtxt`, `ui/texto_etiquetas.py` traduz o
> documento em etiquetas do Tk **nos dois sentidos**, e a aba ganhou "Abrir…" e "Salvar". A decisão
> que organizou o item não estava na spec e é a que mais importa: **o widget é o estado vivo**, com
> `bloco:` e `proc:` viajando como etiquetas — porque a regra de herança de etiqueta do Tk já é a que
> se quer, e digitar dentro de um bloco fica atado ao bloco que se está corrigindo.
>
> Dois achados da implementação: uma quebra de linha que se **acumulava** a cada salvar-e-reabrir (a
> que põe a marca embaixo da miniatura, agora marcada como desenho e descartada na leitura), e um bug
> de produção que os testes acharam — `ImageTk.PhotoImage` registrava a miniatura no *default root*
> do `tkinter` em vez do interpretador do widget.
>
> A S-239 entregou `text/correcao.py` e o comando `cvoff-texto-correcoes` — o 33º do projeto. A
> decisão que mudou o item: **a correção não é gravada, é derivada**. O `.cvtxt` já traz os dois
> lados (a `PaginaLida` que o motor leu e as corridas que estão na tela), e a diferença entre eles é
> a correção; gravá-la seria uma segunda fonte para a mesma pergunta. O par sai **mínimo**, por
> `difflib`: `Black,s` → `Black's` vira `(",", "'")`, que é o que a S-213 consome.
>
> Um teste teve de aprender a ler: a varredura que garante que o editor não escreve em
> `training_data/` reprovava porque os módulos **falam** de `training_data` para dizer que não a
> tocam. Ela passou a rodar sobre a árvore sintática sem as docstrings — e ganhou uma guarda da
> guarda, para que a saída fácil não fosse apagar a frase.
>
> **A fase fechou em 2026-08-25.** A S-236 foi o último item: `LinhaLida.italico`, o campo
> atravessando o leitor até a tag do editor, e a medição na folha real que mudou o desenho.
>
> Na folha 311 do `Secrets of Chess Training` são **19 linhas itálicas, 54 em pé e 4 não medidas** --
> e as 19 são a citação de Kasparov sobre Mecking, contígua e inteira. As 4 não medidas são fins de
> parágrafo de uma palavra, e são a razão de o campo ser `bool | None`: dizer que `game.` está em pé
> seria afirmar sobre o que não se olhou.
>
> **O achado que mudou o desenho.** O bloco só declara o que vale para todas as linhas dele, e ali
> isso custa tudo: as 19 linhas estão num parágrafo de 38, junto com a prosa em volta, e **nenhum
> bloco sai itálico**. Desenhar por bloco seria desenhar nada. A ponte passou a partir o bloco nas
> corridas que o desenham -- e a citação vira uma corrida de 809 caracteres, com o texto da página
> idêntico caractere a caractere ao de antes.
>
> Fica aberto o itálico **da camada de texto**, para os livros lidos com `motor="camada"`: a máquina
> já existe em `text/negrito.py`, e generalizá-la é o que falta. Hoje esses livros saem com o campo
> em `None`, que é a resposta honesta.

## Fase 37 — As ferramentas de edição

- **S-240** · Os comandos do editor entram no catálogo, ou as três peles não os verão
- **S-241** · Negrito, itálico e sublinhado: o atributo, o botão e a tecla que insere tab
- **S-242** · A cor do autor não pode falar a língua da confiança
- **S-243** · Desfazer e refazer que sabem quem tem o foco
- **S-244** · `Ctrl+S` no editor salva o editor
- **S-245** · Achar e substituir, e o que a substituição em massa sabe sobre o OCR

## Fase 38 — A paleta de glifos e símbolos de xadrez

- **S-246** · A paleta sai do `char_meta.json`, e não de uma lista escrita à mão
- **S-247** · O que o Unicode tem e o modelo não lê: a prateleira marcada
- **S-248** · Três formas de inserir, e nenhuma tira a mão do texto
- **S-249** · Estilo de parágrafo: título, prosa, notação e legenda

## Fase 39 — A exportação

- **S-250** · Um lugar só decide o que cada formato faz com o diagrama
- **S-251** · `.md` e `.html`: o que diffa e o que abre no navegador
- **S-252** · `.rtf`, e por que não `.docx`
- **S-253** · O PDF pesquisável do próprio livro, com o texto já corrigido
- **S-254** · Exportar não trava a janela, e diz o que não coube

## Fase 40 — O que sustenta o resto

- **S-255** · O rascunho automático, e a recuperação depois do fechamento
- **S-256** · O inventário do editor: nada de recurso sem comando, atalho e teste

---

# O que foi considerado e recusado

Para que a ausência seja decisão, e não esquecimento.

| recusado | por quê |
|---|---|
| **Trocar o `tk.Text` por um widget de terceiros** (editor HTML embutido, `QTextEdit`) | O `tk.Text` já faz tag, imagem embutida, desfazer e busca. A troca custaria dependência nova e romperia o contrato de degradação de `ui/theme.py:12-15` — aparência não derruba ferramenta. Os dois gatilhos de porte do `ARCHITECTURE.md:163-168` continuam sem disparar. |
| **Editar Markdown puro no widget** (a pessoa vê `**negrito**`) | Perde a faixa de confiança, que não tem sintaxe em Markdown, e obriga quem corrige OCR a ler marcação. A faixa é a razão de a aba existir. |
| **`.docx` como formato de saída** | Dependência nova (`python-docx`) para um formato que o `.rtf` cobre com zero dependências e que o Word abre igual. Registrado na S-252, com a conta. |
| **Um segundo modelo para negrito e itálico** | O classificador foi treinado para ignorar espessura (achado 3). A resposta é geometria sobre a binária, como o pendor do itálico já é — não uma segunda rede. |
| **Deixar negrito e itálico só manuais** | Seria não usar o que o leitor já mede, e faria o editor mostrar uma página **menos** fiel que a que o OCR leu. O pincel continua existindo (S-241) para o que a régua da linha não alcança. |
| **Editar o livro inteiro numa aba só** | A aba é da folha aberta, por decisão de custo já registrada em `sincronizar_com_a_pagina`. O modelo de documento não impede a página seguinte; o que este plano não entrega é a montagem de livro. |
| **Colaboração, comentários, controle de versão do texto** | Fora de escopo. O acervo é local e de um dono, que é a premissa do projeto inteiro. |
| **Corretor ortográfico** | O texto é multilíngue por página (o acervo tem 8 idiomas) e cheio de notação, que nenhum dicionário aceita. O que faz sentido aqui é o léxico de xadrez da S-209, que já está planejado e sinaliza sem trocar. |

---

# Custo, risco e ordem

| fase | esforço | risco | o que trava se der errado |
|---|---|---|---|
| 36 | 5 a 6 dias | **médio** — mexe em `LinhaLida`, que é serializada | as ferramentas não têm onde escrever; a aba continua a de hoje |
| 37 | 4 a 5 dias | baixo — tudo novo, nada some | os botões não aparecem; o documento fica sem editor à altura |
| 38 | 3 a 4 dias | baixo | a paleta não sai; negrito e itálico seguem funcionando |
| 39 | 4 a 5 dias | médio — o `.rtf` e o PDF são formatos de terceiros | fica o `.txt` de hoje, mais `.md` se a S-251 tiver entrado |
| 40 | 2 dias | baixo | o rascunho não existe; o inventário não trava recurso órfão |

**Total: ~3,5 a 4,5 semanas.** As fases 38 e 39 são independentes entre si e podem trocar de ordem
ou sair em paralelo; as duas dependem da 36, e a 37 é o caminho mais curto até algo visível.

**O maior risco é de disciplina, e tem nome.** Cada recurso desta lista é fácil de fazer errado
rápido: um `tag_configure("negrito", font=...)` resolve o negrito na tela em quatro linhas, e é
exatamente o defeito do achado 1 — funciona até alguém salvar. A S-256 existe para que isso falhe
na suíte e não no arquivo de quem passou a tarde corrigindo uma página.

**A regra que vale para as cinco fases:** o que o editor mostra tem de sobreviver ao arquivo, e o
que o arquivo guarda tem de voltar para o editor. Recurso que só existe enquanto a janela está
aberta não é recurso de editor — é enfeite com custo de manutenção.
