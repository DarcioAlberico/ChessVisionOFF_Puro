# Especificação do editor de texto — Fases 36 a 42 e 51 (S-235 a S-267, S-291 a S-293)

Base: [ROADMAP_EDITOR.md](ROADMAP_EDITOR.md), que traz a medição da aba de hoje, os oito achados e
o sequenciamento. O reconhecimento que alimenta o editor é o das Fases 25 a 31
([SPEC_TEXTO.md](SPEC_TEXTO.md)); a fundação de interface é a das Fases 20 a 24
([SPEC_UI.md](SPEC_UI.md)) e das Fases 32 a 35 ([SPEC_APARENCIA.md](SPEC_APARENCIA.md)).

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
> | S-296 a S-323, S-325 a S-428 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |

Cada item tem **Problema** (com arquivo:linha do estado atual), **Solução**, **Critério de aceite**
e **Testes**. Nome de módulo é sugestão; o que importa é a fronteira de responsabilidade.

**Seis regras valem para toda esta spec.**

1. **O documento é dado; o widget é um desenho dele.** Nenhum atributo de texto — negrito, itálico,
   cor, estilo, faixa — pode existir só como tag do `tk.Text`. É o achado 1 do roadmap, e o que ele
   custa está medido: hoje `texto_atual` devolve `str` e as três tags não sobrevivem ao Salvar.
2. **O que a página diz vem da página; o que a pessoa marca vem da pessoa, e os dois se distinguem
   no arquivo.** É a regra da procedência da S-201 aplicada a atributo em vez de a caractere.
3. **Nenhum item crava cor, fonte ou espaçamento fora dos módulos que os decidem** (`ui/tokens.py`,
   `ui/tipografia.py`, `ui/estilos.py`). É a regra 1 da SPEC_UI e a regra 3 da SPEC_APARENCIA, e
   aqui ela tem um cliente novo e perigoso: a paleta de cor de autor.
4. **Todo comando do editor entra em `ui/comandos.py`.** Um recurso que não é comando fica invisível
   para as três peles das Fases 32 a 35 e para o inventário da S-233 — que é a S-161 outra vez:
   *"o que não era botão não existia"*.
5. **O que a régua não separa não entra ligado.** Vale para o negrito da S-237 como valeu para a
   caixa alta na S-211: item cuja medição não mostra vão declara-se não-medido e entrega o pincel
   manual, em vez de pintar palpite.
6. **O que o modelo não lê, a paleta marca.** Inserir um símbolo que nenhuma classe pode confirmar
   é permitido e sinalizado — nunca silencioso —, porque esse texto volta para a fila de revisão de
   caractere da S-212.

---

# Fase 36 — O documento que sobrevive ao widget

> Ao fim dela a aba está quase igual na tela: o único ganho visível é a página impressa aparecer em
> itálico onde ela é itálica. O que mudou é que existe um documento para as ferramentas editarem, e
> um arquivo que o traz de volta.

## S-235 · O documento rico como dado, e não como tag do widget ✅ implementada (2026-08-24)

**Problema.** O que a aba entrega quando alguém salva é uma `str`:

```python
def texto_atual(self) -> str:
    return self.editor.get("1.0", "end-1c")        # ui/texto_panel.py:381
```

Tudo o mais que está na tela fica de fora. As três tags de faixa são configuradas no widget
(`ui/texto_panel.py:369-370`); as miniaturas vivem numa lista cujo comentário explica que ela só
existe porque *"o Tk não segura a imagem"* (`:117-119`); a `PaginaLida` que originou o texto fica em
`self._pagina` e não entra na saída (`:411`).

Isso hoje é aceitável, porque a aba não tem formatação para perder. **Deixa de ser no primeiro
recurso desta spec:** `tag_configure("negrito", font=...)` resolve o negrito na tela em quatro
linhas e entrega, no botão Salvar, o mesmo `.txt` de antes. O defeito não apareceria em teste
nenhum de interface — apareceria no arquivo de quem passou a tarde corrigindo uma página.

**Solução.** `text/rico.py`, sem `import tkinter`, com o documento como **corridas** de texto:

```python
@dataclass(frozen=True)
class Atributos:
    negrito: bool = False
    italico: bool = False
    sublinhado: bool = False
    cor: str = ""        # papel de ui/tokens.py, nunca hexadecimal (regra 3)
    estilo: str = ""     # PROSA | TITULO | NOTACAO | LEGENDA -- S-249

@dataclass(frozen=True)
class Corrida:
    texto: str
    atributos: Atributos = Atributos()
    faixa: str = documento.TRANQUILO   # a régua de confiança, de outro dono
    bloco: int = -1                    # índice do bloco da PaginaLida; -1 = escrito à mão
    procedencia: Procedencia = "humano"

@dataclass(frozen=True)
class DocumentoRico:
    corridas: tuple[Corrida, ...] = ()
    origem: PaginaLida | None = None
```

Quatro decisões, e as quatro têm dono:

- **`faixa` não entra em `Atributos`.** Confiança é medida do reconhecimento e atributo é escolha
  de quem escreve; juntá-los num campo só faria "pintar de vermelho" e "o motor adivinhou" serem a
  mesma informação, que é o achado 6 do roadmap chegando pela porta dos fundos.
- **`cor` é papel, não hexadecimal.** `tokens.cor` resolve na hora do desenho, e é o que faz o
  documento continuar legível quando o tema muda com a janela aberta — o mesmo motivo pelo qual
  `_pintar_faixas` é chamado no desenho e não na construção (`ui/texto_panel.py:360-366`).
- **`bloco` amarra a corrida à `PaginaLida`.** Sem ele, corrigir uma palavra não tem como dizer
  *sobre que bloco* a correção foi feita — e é isso que a S-239 precisa entregar à S-212.
- **`de_pagina` é a única ponte.** O editor deixa de percorrer `documento.segmentos` direto
  (`ui/texto_panel.py:310-316`) e passa a desenhar o `DocumentoRico`. `documento.py` continua
  decidindo faixa, separador e ordem; `rico.py` não redecide nada disso.

E uma trava de não-regressão que é o que torna o item seguro: **`para_texto()` reproduz byte a byte
o que `texto_atual` devolve hoje.** Enquanto isso valer, trocar a fonte do `.txt` não muda o `.txt`.

**Critério de aceite.**

- `rico.de_pagina(p).para_texto()` é igual, caractere a caractere, a
  `"".join(s.texto for s in documento.segmentos(p))`, para toda página do corpus de teste;
- corridas adjacentes com atributos, faixa e bloco iguais se fundem, e a fusão é idempotente e
  preserva o texto — sem isso, digitar caractere a caractere produz mil corridas de um caractere;
- o documento serializa para JSON e volta sem perda, inclusive com `Atributos()` vazio;
- `cor` fora de `tokens.PAPEIS` levanta `KeyError`, como em `tokens.cor` e em
  `estilos.estilo_de_botao`;
- o módulo não importa `tkinter` — o mesmo teste que a S-145 faz para `tokens`;
- a marca `[Diagrama N]` continua sendo texto de uma corrida, e não um objeto à parte: é o que a
  torna movível e o que a faz sobreviver a copiar, colar e exportar (`text/documento.py:22-27`).

**Testes.** `tests/test_texto_rico.py`: `test_o_documento_reproduz_o_texto_de_hoje`;
`test_corridas_iguais_se_fundem`; `test_a_fusao_e_idempotente`; `test_a_fusao_preserva_o_texto`;
`test_o_documento_serializa_e_volta_sem_perda`; `test_cor_fora_dos_papeis_levanta`;
`test_a_faixa_nao_e_atributo`; `test_a_corrida_sabe_de_que_bloco_veio`;
`test_a_marca_de_diagrama_continua_texto`; `test_o_modulo_nao_importa_tkinter`.

### O que entrou em 2026-08-24

`text/rico.py` com `Atributos`, `Corrida`, `DocumentoRico`, `fundir` e `de_pagina`;
`tests/test_texto_rico.py` com **31 casos**; e o painel desenhando o documento em vez de percorrer
`documento.segmentos` — `desenhar` virou duas linhas sobre `desenhar_documento`, que é o gancho de
que a S-238 vai precisar para abrir um arquivo sem página aberta. `tests/test_ui_texto_editor.py`
afirma, com um `tk.Text` de verdade, que **o texto do widget é idêntico ao `para_texto()`** — que é
a trava de não-regressão do item onde ela realmente vale.

**Quatro decisões que a implementação virou, e as quatro divergem do desenho acima.**

1. **`procedencia` é `Procedencia | None`, e não `"humano"` por padrão.** O separador entre dois
   blocos não foi lido nem escrito por ninguém, e carimbá-lo de humano seria inventar autoria de uma
   linha em branco. `None` é "não veio de leitura" — o mesmo idioma que `LinhaLida.negrito` adotou
   dias antes. Quem carimba `"humano"` de fato é a S-239, no instante da edição.
2. **`cor` não é validado contra `ui/tokens.py`, e sim contra um registro próprio.** Validar contra
   os papéis faria `text/` importar `ui/`, invertendo a camada que este módulo existe para manter. A
   regra que sobra é melhor e é a que a aba já pratica: **o domínio nomeia o conceito, a interface o
   resolve em tinta**, como `PAPEL_DA_FAIXA` faz com `revisar` e `conferir`. `CORES_DE_AUTOR` e
   `ESTILOS` nascem vazios, e nome fora deles levanta.
3. **`Corrida` ganhou `tipo`.** Sem ele o separador e a marca de diagrama não voltam do JSON como o
   que são, e a fusão juntaria uma marca com o parágrafo seguinte. O conjunto é fechado e a conversão
   de `Segmento.tipo` — que é `str` livre — **recusa** o que não conhece, em vez de deixar um tipo
   novo virar parágrafo em silêncio.
4. **O índice do bloco sai por identidade, e não por igualdade.** Dois parágrafos com o mesmo texto,
   a mesma bbox e a mesma confiança são dataclasses **iguais**; casá-los por `==` daria o mesmo
   índice aos dois, e a correção do primeiro iria para o bloco errado sem aviso.
   `test_blocos_iguais_nao_compartilham_indice` congela isso.

**O que não entrou.** `texto_atual()` continua lendo o widget e `salvar` continua gravando `.txt`:
reconstruir o documento **de volta** do `tk.Text` é a S-238, e fazê-lo aqui significaria escrever a
conversão índice-do-Tk → deslocamento sem o formato de arquivo que a consome. O `italico` de
`Atributos` existe e é sempre `False` até a S-236.

---

## S-236 · O itálico que o leitor já mede e joga fora ✅ implementada (2026-08-25)

**Problema.** `text/italico.py` mede o pendor da linha e a medição é boa: 157 linhas da página 311
do `Secrets of Chess Training`, itálico em **+0,116** de mediana contra **+0,000** das linhas em
pé, sem sobreposição, corte no meio do vão em 0,05. `e_italica` devolve `True`, `corrigir` usa a
resposta para trocar `/` por `l` — e o booleano morre ali (`text/italico.py:121`).

`LinhaLida` tem `texto`, `bbox`, `confianca` e `procedencia` (`text/pagina.py:290-293`). Não tem
itálico. **A página sabe, e o editor não pode mostrar.**

**Solução.** Um campo, e o que já se mede passa a ser gravado.

```python
@dataclass(frozen=True)
class LinhaLida:
    texto: str
    bbox: tuple[float, float, float, float]
    confianca: float = 1.0
    procedencia: Procedencia = "camada"
    italico: bool = False      # S-236
    negrito: bool = False      # S-237, se a régua separar
```

`leitor.py` grava o que `italico.e_italica` já respondeu dentro do caminho de correção, e
`rico.de_pagina` traduz para `Atributos(italico=True)`. **Custo de tempo: zero** — a medição já roda
em toda linha, e o que muda é ela deixar de ser descartada.

**Duas honestidades, e as duas ficam escritas no módulo.**

- **A régua é da linha, não da palavra.** O que se mede é o pendor mediano da linha inteira. Uma
  palavra em itálico no meio de uma linha em pé **não** é detectada, e o item registra isso em vez
  de fingir cobertura. Quem quiser marcar a palavra usa o pincel da S-241 — que é justamente por
  que o pincel existe.
- **A camada de texto não declara itálico por esta via.** Ela não passa pela binária, então não tem
  pendor medido, e o campo sai `False`. É a regra 4 da SPEC_TEXTO: campo vazio é melhor que campo
  inventado. O caminho da camada tem uma fonte própria, e ela é o assunto da S-237.

Linha com menos de `MIN_BOXES_PARA_MEDIR` boxes continua não sendo declarada — um número de lance
ou um rótulo de eixo não tem população para medir inclinação nenhuma.

**Critério de aceite.**

- `LinhaLida.italico` serializa para JSON e volta, e uma página gravada antes deste item carrega de
  volta com `italico=False` sem levantar (compatibilidade da S-211);
- na folha 311 do `Secrets of Chess Training`, as linhas do trecho citado voltam com `italico=True`
  e as demais com `False` — é a mesma folha que a S-211 já usa como caso;
- o CER da página **não muda**: `cvoff-texto-pagina` com e sem o campo devolve o mesmo número até o
  quarto decimal. O item acrescenta informação, não muda leitura;
- linha vinda da camada nunca declara itálico por esta via;
- linha com menos boxes que `MIN_BOXES_PARA_MEDIR` não é declarada.

**Testes.** `tests/test_text_italico.py` (ampliado): `test_a_linha_italica_chega_marcada`;
`test_a_linha_em_pe_nao_e_marcada`; `test_a_camada_nao_declara_italico_pela_geometria`;
`test_a_linha_curta_nao_e_declarada`; `test_o_campo_serializa_e_volta`;
`test_a_pagina_antiga_carrega_sem_o_campo`; `test_o_cer_nao_muda_com_o_campo`.

### O que entrou em 2026-08-25

`italico.declarar`, `LinhaLida.italico`, `BlocoDeTexto.italico`, o campo atravessando
`leitor.py` → `documento.py` → `rico.py` → a tag do editor, e **21 casos novos** em
`tests/test_italico.py`, `tests/test_texto_rico.py` e `tests/test_ui_texto_editor.py`. Os testes
foram para `tests/test_italico.py`, que já existia — o nome no plano acima estava errado.

**A medição na folha real, que é o que fecha o item.** Folha 311 do `Secrets of Chess Training`,
motor `glifo`:

| | linhas |
|---|---:|
| declaradas itálicas | **19** |
| declaradas em pé | 54 |
| **não medidas** (`None`) | 4 |

As 19 são a citação de Kasparov sobre Mecking — *"and strong squares. l have played him three
times..."* —, contígua e inteira. As 4 não medidas são fins de parágrafo de uma palavra: `pects.`,
`♘xh5.`, `reached.`, `game.` Elas são a razão do terceiro estado: dizer que `game.` está em pé
seria afirmar sobre o que não se olhou.

**Três decisões que a implementação virou.**

1. **`bool | None`, e não `bool = False`.** A camada de texto não passa pela binária e não tem
   pendor para medir; a linha curta não tem população. Os dois casos são "não se sabe", e achatá-los
   em `False` seria a mesma invenção que a regra 4 da SPEC_TEXTO proíbe. É o idioma que
   `LinhaLida.negrito` adotou dias antes, agora com a razão oposta: **o itálico sai da imagem e o
   negrito não.** `e_italica` continua achatando `None` em `False`, e agora é `declarar(...) is
   True` — porque no caminho da *correção* a dúvida não autoriza trocar `/` por `l`.

2. **O desenho é por linha, e essa foi a medição que mudou o desenho.** O bloco só declara o que
   vale para **todas** as linhas dele, e na página real isso custa tudo: as 19 linhas itálicas da
   folha 311 estão num parágrafo de 38, junto com a prosa em volta — e **nenhum bloco sai itálico**.
   Desenhar por bloco ali seria desenhar nada. `rico.de_pagina` passou a partir o bloco nas corridas
   que o desenham, agrupando linhas vizinhas de mesma tipografia; na folha 311 a citação vira **uma
   corrida de 809 caracteres**. O corte é feito nos pontos em que `bloco.texto` junta as linhas e o
   espaço da junção fica no fim da corrida anterior, então **o texto não muda um caractere** — e há
   uma guarda: se a soma das linhas não bater com o texto do bloco, sai uma corrida só. O texto vale
   mais que o atributo.

3. **Uma medição por linha, e ela serve aos dois usos.** `corrigir` ganhou `italica=`, que recebe a
   resposta já medida. Sem isso o leitor varreria os boxes duas vezes na mesma linha — uma para
   gravar o campo, outra para decidir a troca — e a frase de que este item custa zero de tempo
   deixaria de ser verdade.

**Sobre o critério do CER.** Não rodei `cvoff-texto-pagina` duas vezes: verifiquei o que o implica e
é mais forte. `para_texto()` da folha 311 é **idêntico caractere a caractere** ao que
`documento.segmentos` produzia, e `test_a_medicao_passada_da_o_mesmo_que_medir_dentro` afirma que
`corrigir` com a medição passada devolve o que devolvia medindo por dentro. Texto igual, CER igual.

**Um defeito que este item quase introduziu.** No Tk a prioridade da tag é a ordem de criação, e uma
tag só pode dar **uma** fonte ao trecho: com `negrito` e `italico` como tags irmãs, um trecho com os
dois sairia só itálico, e o negrito que a S-237 lê da camada sumiria da tela sem sumir do documento.
`ui/texto_panel.NEGRITO_ITALICO` é a tag combinada, criada por último. Ela é **desenho e não
documento** — não mapeia atributo nenhum, então `corrida_de` a ignora sozinha na volta, e
`test_a_tag_combinada_nao_vira_atributo_na_volta` trava isso.

**O que não entrou.** O itálico **da camada de texto** — o bit 1 de `span["flags"]` e o nome de
fonte com `italic`/`oblique`. A máquina para isso já existe em `text/negrito.py` (spans → cobertura →
`marcar`), e generalizá-la é o que falta para os livros lidos por `motor="camada"`, que hoje saem com
o campo em `None`. E a régua continua sendo **da linha**: uma palavra em itálico no meio de uma linha
em pé não é detectada, e quem quiser marcá-la usa o pincel da S-241.

---

## S-237 · O negrito: a espessura medida, ou dita não-medida ✅ implementada (2026-08-25)

**Problema.** Não há detecção de negrito em lugar nenhum, e há o contrário: `text/aumento.py:23`
lista `espessura` entre as **augmentações** — *"tinta gorda contra tinta fina: `bold`, papel
absorvente, digitalização escura"* — e o perfil do acervo a liga com probabilidade 0,5
(`aumento.py:113`). O classificador foi ensinado a não distinguir traço gordo de traço fino, e essa
invariância é o que o faz ler scan escuro. **Pedir negrito ao classificador é pedir de volta o que
se pagou para ele apagar.**

**Solução, em duas fontes e um portão.**

**Fonte A — a camada, onde ela declara.** `pdf_text.py` lê `span["font"]` desde a S-217
(`pdf_text.py:521`) e nunca leu `span["flags"]`, onde o PyMuPDF já entrega o bit 1 (itálico) e o
bit 4 (negrito) em toda chamada que o projeto já faz. Medido em 2026-08-24, 4 páginas de cada um
dos 41 livros de `PDF/`:

| | livros |
|---|---:|
| têm camada de texto na amostra | 30 |
| **declaram itálico ou negrito** | **14** |
| têm camada sem estilo | 16 |
| não têm camada | 11 |

Isto resolve 14 livros e **não resolve o problema**: sobram 27. E entre os 14 há camada de OCR de
terceiro — a `Gaprindashvili` é `_OCR_Aprimorar_Aprimorar` e declara 60 negritos que são palpite de
outro motor, não tipografia do livro. A distinção **camada editorada** contra **camada de OCR** já
existe neste projeto (`text/leitor.py:84-85`) e vale igual aqui: só a editorada entra como
declaração, e a de OCR entra como suspeita.

**Fonte B — a geometria, para os 27 restantes.** `text/espessura.py`, na mesma forma do
`italico.py` e por isso barato: para cada box, a largura de traço estimada por **2 × área de tinta ÷
perímetro do contorno** — para um traço de largura `w` e comprimento `L`, a área é `wL` e o
perímetro `2L`, e a razão devolve `w`. Normalizada pela x-height da **linha**, nunca da página, pelo
mesmo motivo pelo qual a caixa alta é decidida por linha na S-211: um título em corpo maior
promoveria a página inteira.

**O portão, e ele é o item.** A régua entra ligada **apenas se a medição mostrar vão**, como o
itálico mostrou (+0,116 contra +0,000) e como a caixa alta mostrou (1,41 contra 1,00). O conjunto de
referência é gratuito e sai da fonte A: as páginas dos livros de camada **editorada** que declaram
negrito, com o `Dvoretsky - Endgame Manual (2025)` à frente — 105 spans em negrito e 16 em itálico
em 4 páginas, digital nativo — e o `Kemeri 1937`, com 445. Mede-se a geometria na página renderizada
e confere-se contra o que a camada declara na mesma página. É exatamente a forma da medição da caixa
alta na S-211.

**Se o vão não aparecer, o item entrega isto:** a fonte A ligada para os 14 livros, a régua
geométrica **desligada**, o número medido publicado em `docs/metrics/texto_espessura.json` e uma
frase na spec dizendo que negrito detectado não foi medido neste acervo. O pincel manual da S-241
continua sendo a resposta. **Um item que se declara não-medido é um item entregue** — a regra 5.

**Critério de aceite.**

- `pdf_text` passa a expor itálico e negrito dos spans, e o número de livros que os declaram é
  publicado com a data e o comando que o mediu;
- camada de OCR nunca entra como declaração de estilo, e o teste prova que a peneira é a mesma de
  `leitor.py`;
- a régua geométrica é afirmada nos dois regimes contra a referência da camada editorada, com
  precisão e recall publicados por página;
- **o corte fica no meio do platô**, e não no mínimo, como o 1,25 da caixa alta;
- o CER da página não muda com o item ligado — ele acrescenta atributo, não muda leitura;
- se a separação não existir, `docs/metrics/texto_espessura.json` registra o número medido e a régua
  entra desligada, com o motivo no módulo.

**Testes.** `tests/test_text_espessura.py`: `test_a_largura_de_traco_e_a_razao_area_perimetro`;
`test_a_normalizacao_e_por_linha_e_nao_por_pagina`; `test_o_negrito_declarado_pela_camada_chega`;
`test_a_camada_de_ocr_nao_declara_estilo`; `test_o_corte_esta_no_meio_do_plato`;
`test_a_regua_desligada_nao_marca_nada`; `test_o_cer_nao_muda_com_o_campo`.

### O que entrou em 2026-08-24, por outro caminho

**A metade do negrito entrou antes desta spec, sob a S-211**, em `text/negrito.py` — e entrou mais
completa do que este item pedia. `LinhaLida` ganhou `negrito: bool | None`, `ler_pagina` o preenche,
`Segmento` o carrega e o editor o desenha. A cobertura medida lá é **13 dos 42 livros** com negrito
na camada, 16 com camada sem negrito e 10 sem camada — e é dessa distribuição que sai o
`bool | None`: um livro que não registra peso nenhum não pode declarar que nada ali é negrito.

**E o portão deste item foi atravessado, com número.** A rota geométrica foi medida sobre 940
palavras rotuladas pela camada, em 3 livros, e **recusada**:

    medida                 melhor acerto    chutar "normal" sempre
    espessura do traço            82,2%              82,7%
    densidade de tinta            85,6%              82,7%

A espessura não passa do acaso; a densidade passa pouco e desaba na curva de precisão (melhor F1
0,60, com metade do que fosse marcado saindo errado). Subir de 220 para 400 dpi não muda. É
exatamente a regra 5 desta spec: **um item que se declara não-medido é um item entregue.**

> **Um erro de método que aquela medição registrou, e que vale para a S-236.** A primeira versão
> normalizou a espessura pela **mediana da linha**, o que apaga o sinal justamente quando a linha
> inteira é negrito — título, lance principal. Este item, escrito antes, pedia essa normalização em
> critério de aceite; a medição mostrou que ela é o erro. O texto acima fica como estava, e esta
> nota é a correção.

**O que faltava para o item fechar:** o lado do itálico. Ele entrou em duas etapas — a régua
geométrica na S-236, e a camada de texto na nota "O itálico da camada fecha o item", abaixo.

### O peso lido certo que a montagem do parágrafo perdia (2026-08-25)

**A régua estava certa e a folha saía errada mesmo assim.** Na folha 51 do `Dvoretsky` — a das
posições 1-46 e 1-47, com *Tragicomedies* — a camada marca dez linhas em negrito e
`text/negrito.py` acerta as dez. Ainda assim, **cinco dos oito parágrafos de texto da página
saíam `negrito=None`**, que é a aba dizendo *"o livro não informa"* sobre um livro que informa
cada lance.

O defeito não estava na leitura do peso, e sim no corte do parágrafo. `BlocoDeTexto.de_linhas` só
declara o peso do bloco quando **todas** as linhas concordam — e está certo: não se sabe do todo o
que não se sabe de uma parte. Mas ali o lance em negrito estava *dentro* do parágrafo de prosa:

```
The only saving line starts with a paradoxical move that forces the black pawn to advance.
1.♔c8!! b5                                    ← em negrito, e no mesmo bloco do de cima
```

Naquela página nem o recuo nem o salto de `text/paragrafos.py` veem esse corte. O entrelinhamento é
**constante** — 19 pt de uma linha à seguinte, dentro do parágrafo e entre parágrafos —, e o recuo,
que existe (29 pt de margem contra 40 pt de recuo), está morto por outra razão registrada abaixo.
**O que separa a prosa da notação naquele livro é só o peso da fonte.**

**Solução: uma quarta regra em `paragrafos.cortar` — *o peso mudou*.** Ela só vale entre dois pesos
**conhecidos**: `None` de um lado não abre parágrafo nenhum, e nos 26 livros do acervo cuja camada
não registra peso ela fica inerte. É o mesmo idioma de três estados do resto do item.

Medido em 2026-08-25 sobre 96 folhas dos 12 livros do acervo que registram peso:

| | blocos |
|---|---:|
| blocos de texto na amostra | 1.557 |
| **de peso misto — parágrafo grudado** | **94 (6,0%)** |
| dos 94, parágrafo real que a regra fosse partir ao meio | 0 |

Na folha 51 o efeito é direto: 20 blocos de texto viram 25, os dez negritos ficam cada um no seu
parágrafo, e **nenhum bloco da página sai `None`**. Medido pelo que a aba desenha —
`documento.segmentos` sobre a mesma folha, antes e depois:

| | trechos em negrito na tela |
|---|---:|
| antes | 5 — só os títulos e os números de diagrama |
| depois | **10** |

Os cinco que faltavam eram os lances: `1.♔c8!! b5`, `2.♔d7 b4 3.♔d6 ♗f5`, `4.♔e5! ♗c8 5.♔d4=`,
`1.♔c3? b1=♕ 2.♕xb1+ ♔xb1 3.♔b4` e `3...♔b2! 4.♗xa4 ♔c3, with a draw.` — todos lidos como negrito
pela camada, e todos perdendo o peso na montagem do parágrafo. **O `.cvtxt` salvo os gravava sem
negrito**, que é o defeito chegando ao arquivo de quem passou a tarde corrigindo a página.

> **O defeito vizinho que este item NÃO conserta, e o número dele.** Na mesma folha, dois
> parágrafos de prosa continuam grudados em cada coluna — *"…is hopeless,"* com *"as is 1.♔d6?…"*,
> e *"…stalemate."* com *"But White wins easily…"*. A causa é outra: `metricas_por_coluna` toma a
> **mediana** das esquerdas como margem da coluna, e numa diagramação de recuo de primeira linha
> com parágrafos curtos quase metade das linhas começa no recuo. Ali a mediana devolve 40 pt — o
> recuo — no lugar de 29 pt, e `recuou` fica morto na coluna inteira. Trocar por um quantil baixo
> conserta a folha 51 e mexe em muito mais: medido sobre 54 folhas de 10 livros, o quartil de 25%
> produz **1.046 blocos contra 835**, e blocos de uma linha só passam de 56,2% para 61,9%. Parte
> disso é corte certo e parte é despedaçamento — a distinção precisa de referência rotulada, e é
> a **S-257**, ao fim desta spec: lá estão os três passos e o portão que a decidem.

**Testes.** `test_a_mudanca_de_peso_abre_paragrafo`; `test_sem_o_peso_a_mesma_folha_sai_grudada`;
`test_o_desconhecido_nao_abre_paragrafo`; `test_o_peso_igual_nao_abre_paragrafo`;
`test_a_mudanca_de_peso_corta_o_paragrafo`; `test_sem_peso_conhecido_o_mesmo_fixture_sai_num_bloco_so`.

### O itálico da camada fecha o item (2026-08-25)

**Faltava a outra metade da mesma fonte.** A S-236 trouxe o itálico da **imagem** -- o pendor
medido sobre a binária -- e registrou por escrito o que sobrava: *"o itálico da camada de texto, o
bit 1 de `span["flags"]` e o nome de fonte com `italic`/`oblique`. A máquina para isso já existe em
`text/negrito.py` (spans → cobertura → `marcar`), e generalizá-la é o que falta para os livros
lidos por `motor="camada"`, que hoje saem com o campo em `None`."* É o que este passo faz.

**A máquina saiu do módulo do negrito.** `spans → cobertura → marcar` era geometria genérica
escrita dentro dele; agora mora em `text/camada.py`, e os dois módulos de estilo dizem só *o que*
procurar -- `text/negrito.py` o nome de fonte e o bit `2**4`, `text/italico.py` o nome e o bit
`2**1`. `negrito.py` continua exportando `cobertura` e `marcar`, delegando: quem os importa não
mudou uma linha.

**A precedência é por ausência, e não por preferência.** A régua da imagem responde onde ela roda;
a camada responde onde `italico` ainda é `None`. Nenhuma sobrescreve a outra -- sobrescrever
exigiria decidir qual erra menos, e isso ninguém mediu. Na prática são caminhos disjuntos
(`motor="glifo"` preenche tudo, `motor="camada"` não preenche nada), e a regra escrita assim
continua valendo no dia em que deixarem de ser.

**A medição, e ela desmente o que o item supunha** (`docs/metrics/texto_italico_camada.json`, 4
folhas de cada um dos 42 livros de `PDF/`):

| | livros |
|---|---:|
| têm camada de texto | 32 |
| **declaram itálico** | **12** |
| declaram negrito | 13 |
| camada sem estilo nenhum | 18 |
| não têm camada | 10 |

**Doze, e não mais que o negrito.** Só **um** livro declara itálico sem declarar negrito
(`Vishy_Anand_Great_Chess_Combinations.pdf`); nos outros onze a camada já registrava peso. O ganho
não é alcance novo: é a **outra metade do mesmo livro** -- onde a S-237 já lia negrito e o itálico
saía `None`. E ele é fino: 138 linhas itálicas em 8.379 na amostra (**1,6%**), concentradas em
citação e nome de abertura, com o `Kmoch` no extremo (36 de 310, 11,6%).

**Um caso que a implementação encontrou:** `-it` no nome da fonte precisa da guarda `(?![a-z])`, e
não de `\b`. Com `\b`, `MS-Item` viraria itálico -- a fronteira de palavra existe entre `t` e `e`.

**O que este item deixa de dever.** Nada: a S-237 fecha. O negrito da imagem continua **recusado
com número** (82,2% contra 82,7% de chutar "normal"), que é a outra metade e é uma recusa, não uma
falta.

**Testes.** `tests/test_italico.py::CamadaTests` e `::PrecedenciaTests`, treze casos -- incluindo o
que afirma que a máquina é literalmente a mesma do negrito (`ne.cobertura is camada.cobertura`).

---

## S-238 · O arquivo do editor: salvar e reabrir sem perder diagrama, faixa nem correção ✅ implementada (2026-08-24)

**Problema.** `salvar` grava um `.txt` num lugar escolhido no diálogo, com o cabeçalho de
procedência (`ui/texto_panel.py:383-412`). O que fica de fora: as faixas de confiança, os
diagramas, a `PaginaLida`, e — depois da Fase 37 — negrito, itálico, cor e estilo. **E não existe
"abrir":** o `.txt` é uma saída sem volta. Reler a folha descarta tudo, e a caixa de confirmação de
`ler` (`:224-230`) é o programa avisando que vai fazer isso.

A docstring de `salvar` já diz o que está em jogo: *"se alguém corrigiu uma palavra, é a correção
que tem valor — é a única coisa nesta aba que não sai de graça de uma releitura"* (`:386-388`). Ela
está certa, e é exatamente essa coisa que o `.txt` não guarda inteira.

**Solução.** Um formato de documento do editor, `.cvtxt`, que é **JSON e não binário**:

```json
{
  "versao": 1,
  "documento": "AAGAARD - Practical Chess Defence.pdf",
  "folha": 57,
  "numero_impresso": 58,
  "lido_em": "2026-08-24T10:12:03",
  "motor": "glifo",
  "pagina": { ... a PaginaLida serializada, que já sabe fazer isto (S-211) ... },
  "corridas": [ {"texto": "...", "atributos": {...}, "faixa": "conferir", "bloco": 3,
                 "procedencia": "glifo"} ]
}
```

Três decisões:

- **A `PaginaLida` vai junto, inteira.** Ela já serializa sem perda por critério de aceite da S-211,
  e é o que permite reabrir o arquivo e ainda ter bbox, confiança e diagrama — isto é, recortar a
  miniatura de novo a partir do PDF, em vez de embutir imagem no arquivo.
- **O diagrama não é embutido.** O que se guarda é o bbox e o índice; a miniatura se refaz do PDF
  original, que é o mesmo caminho de `_miniatura` (`ui/texto_panel.py:333-357`). Embutir PNG faria
  um arquivo de texto pesar megabytes e duplicaria o que já está no livro.
- **`atomic_write_text`, como todo o resto do projeto.** Gravar por cima de uma sessão de correção
  com escrita parcial é a pior falha possível deste item.

O `.txt` continua existindo e continua sendo o padrão do botão de exportar rápido — quem quer colar
o texto num e-mail quer o `.txt`. O que muda é haver um formato que **volta**.

**Critério de aceite.**

- salvar e reabrir devolve um `DocumentoRico` igual ao que estava na tela, campo a campo,
  incluindo faixa, atributos, bloco e procedência de cada corrida;
- o arquivo de uma folha com diagramas reabre com as miniaturas no lugar certo, recortadas do PDF
  pelo bbox guardado;
- reabrir com o PDF ausente **não levanta**: o texto abre, as miniaturas faltam, e a barra de status
  diz qual arquivo não foi encontrado — a regra de degradação de `ui/theme.py:12-15`;
- `versao` desconhecida ou maior que a atual recusa com mensagem em pt-BR, como
  `state._migrate` já faz (`ui/state.py:194-195`);
- a gravação é atômica, e o teste prova que uma falha no meio não deixa arquivo truncado;
- `.txt` continua saindo idêntico ao de hoje, com o mesmo cabeçalho.

**Testes.** `tests/test_texto_arquivo.py`: `test_salvar_e_reabrir_preserva_o_documento`;
`test_as_miniaturas_voltam_do_pdf_pelo_bbox`; `test_reabrir_sem_o_pdf_abre_o_texto_e_avisa`;
`test_versao_futura_recusa_em_portugues`; `test_a_gravacao_e_atomica`;
`test_o_txt_continua_igual_ao_de_hoje`.

### O que entrou em 2026-08-24

`text/arquivo.py` (o formato `.cvtxt`), `ui/texto_etiquetas.py` (a tradução documento ↔ etiquetas do
Tk) e três métodos no painel: `documento_atual`, `salvar_documento` e `abrir_documento`. **64 casos
novos** em `tests/test_texto_arquivo.py`, `tests/test_ui_texto_etiquetas.py` e a ampliação de
`tests/test_ui_texto_editor.py`.

**A decisão que organizou o item, e ela não estava no desenho acima: o widget é o estado vivo.**
Havia duas saídas para "reconstruir o documento depois de a pessoa editar" -- manter um segundo
buffer sincronizado a cada tecla, ou guardar tudo no próprio `tk.Text` e reconstruir na hora de
gravar. É a segunda, e o argumento é do Tk:

> *"If tagList is not present, the new text will receive any tags that are present on **both** the
> character before and the character after the insertion point."*

Isso **já é** a regra que se quer. `bloco` e `procedencia` viajam como etiquetas (`bloco:3`,
`proc:glifo`), então digitar **dentro** de um bloco herda a origem dele -- e a correção fica atada ao
bloco que ela corrige, que é exatamente o que a S-239 precisa entregar à fila da S-212. Digitar na
emenda entre dois blocos não herda nenhum dos dois e vira texto sem origem, que também é o certo. Um
segundo buffer teria de reimplementar essa regra e acertá-la de novo em cada caso.
`test_digitar_dentro_do_bloco_mantem_a_origem` e `test_digitar_fora_de_tudo_nao_inventa_origem`
travam as duas metades.

**Um defeito que só apareceu com o ciclo fechado: a quebra que se acumulava.** A miniatura entra
seguida de uma quebra de linha, para a marca cair embaixo dela. Essa quebra é do **desenho**, não do
documento -- e sem dizer isso ela voltaria como texto ao gravar, e o desenho seguinte acrescentaria
outra. Uma quebra a mais a cada salvar-e-reabrir, para sempre. A etiqueta `DESENHO` é o que a leitura
descarta, e `test_a_quebra_nao_se_acumula_a_cada_ciclo` roda o ciclo três vezes.

**Um bug de produção que os testes acharam.** `ImageTk.PhotoImage(recorte)` registra a imagem no
*default root* do `tkinter`, e não no interpretador do widget. Com um `Tk` só -- o programa -- dá no
mesmo; com dois, `image_create` levanta `TclError: image "pyimageN" doesn't exist`. Passou a receber
`master=self.editor`.

**Três coisas do desenho acima que não entraram, e por quê.**

1. **`lido_em` e `motor` saíram do formato.** A procedência de cada bloco já diz de que motor ele
   veio, com granularidade melhor que "a página foi lida com glifo", e a data de leitura não tem
   consumidor -- a do arquivo é do sistema de arquivos. Campo sem quem o leia é o item de menu sem
   comando da S-161.
2. **`documento` e `folha` também saíram**: os dois são derivados de `origem` (`PaginaLida.documento`
   é o caminho do PDF e `PaginaLida.pagina` é a folha), e duplicá-los criaria duas fontes para a
   mesma pergunta.
3. **A versão é do arquivo e não do documento.** `text/rico.py` não ganhou número de versão: ele é um
   objeto em memória, e quem envelhece é o arquivo. E **acrescentar campo não sobe a versão** --
   é o que `Atributos.para_json` compra ao omitir o que é padrão.

**O que mudou fora do item.** A barra da aba virou `BarraFluida`: com "Abrir…" e "Salvar" a fila
passou de oito para dez itens, e `pack(side=LEFT)` numa linha só **não desenha** o que passa da borda
-- o defeito que a S-151 mediu. E a catraca de `tests/test_ui_retorno_modal.py` subiu de **45 para
48**, com o motivo escrito lá: duas caixas de erro (o `.cvtxt` que não gravou e o que não abriu) e
uma pergunta (abrir outro arquivo descarta o que está na tela).

**O que não entrou.** `Ctrl+S` continua sem fazer nada no editor -- é a S-244 --, e os três comandos
novos ainda não estão no catálogo de `ui/comandos.py`, que é a S-240. O `.txt` continua saindo
idêntico ao de antes, e agora deriva o nome do **mesmo** lugar que o `.cvtxt`.

---

## S-239 · A correção humana carimba procedência, e vai para onde a S-212 a espera ✅ implementada (2026-08-24)

**Problema.** `Procedencia` é `Literal["camada", "glifo", "rapidocr", "humano"]`
(`text/pagina.py:198`), e `"humano"` existe desde a S-201 — mas **nada no programa o escreve a
partir do editor**. Uma palavra corrigida à mão sai da aba como texto, no meio de um `.txt`, sem
nada que diga que ali houve intervenção.

E há dois destinos planejados esperando exatamente essa informação: a **S-212** (fila de revisão de
caractere) e a **S-213** (aplicar a todos os semelhantes). As duas precisam de *"o que uma pessoa
corrigiu, e sobre que glifo"*. O editor é o único lugar do programa onde isso acontece, e hoje ele
joga fora.

**Solução.** Toda corrida tocada por edição passa a `procedencia="humano"`, e o documento guarda o
que foi trocado:

```python
@dataclass(frozen=True)
class Correcao:
    bloco: int          # de que bloco da PaginaLida (Corrida.bloco)
    antes: str          # o que o motor leu
    depois: str         # o que a pessoa escreveu
    motor: MotorResolvido   # quem tinha lido: "camada" ou "glifo"
```

Duas regras, e as duas são a cicatriz das duas pontas registrada na regra 2 da SPEC_TEXTO
(*"o palpite do modelo nunca entra na base como rótulo"*), agora do outro lado:

- **A correção é registro, e não rótulo.** Este item **não** escreve em `training_data/` e não
  cria amostra. Ele grava o par no `.cvtxt` e oferece um relatório; quem decide se aquilo vira
  rótulo é a S-212, que tem a fila e o critério. Um editor que alimentasse a base direto seria um
  caminho de rótulo sem revisão — que é exatamente o defeito de que a base já tem cicatriz.
- **Corrida escrita do zero não é correção.** `bloco == -1` significa texto que a pessoa acrescentou,
  e não texto que o motor errou. Contá-lo como correção inflaria qualquer estatística de erro do
  OCR com o que alguém digitou por conta própria.

O relatório sai por um comando, na forma dos outros: `cvoff-texto-correcoes`, que varre `.cvtxt` e
diz quantas correções, sobre que motor, e quais caracteres mais trocaram — que é a lista de
candidatos que a S-212 vai querer.

**Critério de aceite.**

- toda corrida cujo texto mudou em relação ao bloco de origem sai com `procedencia="humano"`;
- corrida intocada mantém a procedência do motor que a leu;
- corrida com `bloco == -1` não conta como correção em relatório nenhum;
- o par `antes`/`depois` sobrevive ao salvar e reabrir;
- **nada é escrito em `training_data/` por este item**, e o teste prova isso varrendo as chamadas;
- `cvoff-texto-correcoes` devolve JSON com o mesmo formato dos outros relatórios de `docs/metrics/`.

**Testes.** `tests/test_texto_correcoes.py`: `test_a_corrida_editada_vira_humano`;
`test_a_corrida_intocada_mantem_o_motor`; `test_o_texto_novo_nao_conta_como_correcao`;
`test_o_par_antes_depois_sobrevive_ao_arquivo`; `test_o_editor_nao_escreve_na_base_de_treino`;
`test_o_relatorio_agrupa_por_caractere`.

### O que entrou em 2026-08-24

`text/correcao.py`, o comando `cvoff-texto-correcoes`, e uma linha em `documento_atual`. **38 casos
novos** em `tests/test_texto_correcoes.py` e na ampliação de `tests/test_ui_texto_editor.py`.

**A decisão que mudou o item: a correção não é gravada, é derivada.** O desenho acima previa um
`Correcao` guardado dentro do `.cvtxt`. A implementação não guarda nada, porque o arquivo **já traz
os dois lados**:

    origem.blocos[N].texto     o que o motor leu     -- a `PaginaLida`, intocada pela edição
    as corridas com bloco N    o que está na tela    -- depois da edição

Gravar o par seria uma **segunda fonte para a mesma pergunta**, e a primeira vez que alguém editasse
o arquivo por fora as duas discordariam sem nada dizendo qual valia. É a mesma razão pela qual a
S-238 tirou `documento` e `folha` do formato. `test_nada_de_correcao_e_gravado_no_arquivo` afirma que
nenhuma chave de correção existe no JSON, e
`test_o_par_antes_depois_sobrevive_ao_arquivo` afirma que a derivação sobrevive assim mesmo.

**O par é mínimo, e não o bloco.** `difflib` sobre o texto do bloco devolve só o que mudou:
`Black,s` → `Black's` vira `(",", "'")`, e não o parágrafo de 400 caracteres em volta. É o que
torna o relatório utilizável pela S-213, que quer saber quantas vezes a vírgula virou apóstrofo —
não quantos parágrafos foram tocados.

**Três coisas ficam fora da conta, e as três por motivo escrito.**

1. **Texto escrito do zero** (`bloco == SEM_BLOCO`) é carimbado `humano` — a mão o escreveu — e
   **não** entra em `correcoes`: contá-lo inflaria a estatística de erro do OCR com o que alguém
   digitou por conta própria.
2. **O separador** não é carimbado: ele é estrutura que o leitor produziu, e ninguém o escreveu.
3. **O diagrama** fica fora: `[Diagrama N]` é referência, não leitura, e apagá-la é editar a
   estrutura do texto. Deixá-la entrar encheria o relatório de pares `("[Diagrama 3]", "")` que
   nenhuma classe de caractere pode consumir.

**A marcação é idempotente por construção**, e precisa ser: `documento_atual` a aplica a cada
gravação, e a comparação que a decide é contra a `PaginaLida` — que a marcação não toca.

**O teste que guarda a regra 2 desta spec teve de aprender a ler.** `test_o_editor_nao_escreve_na_base_de_treino`
varre os cinco módulos do editor atrás de `training_data`, `char_to_folder`, `salvar_amostra` e
`labels.csv` — e reprovava, porque os módulos **falam** de `training_data` justamente para dizer que
não a tocam. A varredura passou a rodar sobre a árvore sintática com as docstrings removidas, e
`test_a_varredura_nao_confunde_prosa_com_codigo` é a guarda da guarda: sem ela, a saída fácil seria
apagar a frase que promete o contrário.

**O que não entrou.** A fila da S-212 e a aplicação em lote da S-213 continuam não existindo — este
item entrega o registro e o relatório, que é o que faltava para elas. E `cvoff-texto-correcoes` é o
33º comando do projeto; a contagem do README subiu junto.

---

# Fase 37 — As ferramentas de edição

> A fase que aparece na tela. Nenhum item dela escreve formatação no widget sem passar pelo
> documento da S-235 — e é a S-256 que faz isso falhar na suíte quando alguém tentar o atalho.

## S-240 · Os comandos do editor entram no catálogo, ou as três peles não os verão ✅ implementada (2026-08-25)

**Problema.** `ui/comandos.py` registra os comandos da janela — 36 em 2026-08-24 — e **nenhum
deles é da aba Texto**. Os seis controles da barra (`ui/texto_panel.py:137-161`) são montados à
mão, com o rótulo em literal — exatamente o estado de que a S-324 tirou `ui/pdf_panel.py`.

Com a aba de hoje isso é dívida pequena: são seis botões numa aba só. **Com os vinte e poucos
comandos desta spec, é a S-161 outra vez** — *"o que não era botão não existia"* —, e agora com três
peles para divergir: a pele "Foco" mostra uma fila curta, a "Fita" mostra grupos, e o que não estiver
no catálogo simplesmente não aparece em nenhuma das duas. O inventário da S-233, que deveria acusar,
passa em verde: ele compara o catálogo com as peles, e um comando fora do catálogo é invisível para
os dois lados da comparação.

**Solução.** Os comandos do editor entram em `CATALOGO`, no grupo `EDICAO`, com ícone da S-220.
Um grupo novo **não** é criado: `GRUPOS` é fechado por decisão da S-324, e "negrito" é edição pela
mesma pergunta que separa `OCR` de `ACERVO` — age sobre o que está aberto agora.

O que entra, agrupado por item desta spec:

| comandos | item |
|---|---|
| `negrito`, `italico`, `sublinhado`, `limpar_formato` | S-241 |
| `cor_do_texto`, `realce`, `limpar_cor` | S-242 |
| `desfazer`, `refazer` | S-243 |
| `salvar_texto`, `salvar_texto_como`, `abrir_texto` | S-238, S-244 |
| `achar`, `substituir`, `substituir_todos` | S-245 |
| `paleta_de_glifos`, `inserir_figurina`, `inserir_avaliacao` | S-246 a S-248 |
| `estilo_titulo`, `estilo_prosa`, `estilo_notacao`, `estilo_legenda` | S-249 |
| `exportar_md`, `exportar_html`, `exportar_rtf`, `exportar_pdf_pesquisavel` | S-250 a S-253 |

**`desfazer` e `refazer` são os mesmos da S-229**, e não um par novo: aquele item os cria para o
tabuleiro, este os aponta para o editor, e quem escolhe o alvo é o foco (S-243). Dois pares de
comandos com o mesmo nome em português seria a divergência que o catálogo existe para impedir.

**Um achado da S-324 volta a valer aqui, e este item o resolve para o editor:** *no máximo um
`PRIMARIO` por grupo*. `EDICAO` já tem o seu — `salvar`, a posição do tabuleiro. Nenhum comando
desta spec pede ênfase, e `salvar_texto` **não** vira primário: são duas ações de salvar em grupos
visualmente vizinhos, e duas ênfases na mesma barra é o mesmo que nenhuma (`ui/estilos.py:22, 29-36`).

**Critério de aceite.**

- todo comando do editor está no catálogo, e a varredura da S-324 continua sem achar rótulo escrito
  à mão — inclusive na aba Texto, que hoje ela não cobre;
- `EDICAO` continua com exatamente um `PRIMARIO`;
- todo comando novo tem ícone declarado em `ui/icones.py`, ou declara `icone=""` de propósito;
- `desfazer` e `refazer` aparecem **uma vez** no catálogo;
- a barra da aba Texto é montada do catálogo, e nenhum rótulo muda em relação ao de hoje para os
  seis controles que já existiam.

**Testes.** `tests/test_ui_comandos.py` (ampliado): `test_a_aba_texto_nao_escreve_rotulo_a_mao`;
`test_os_comandos_do_editor_estao_no_catalogo`; `test_edicao_continua_com_um_primario`;
`test_desfazer_e_refazer_aparecem_uma_vez`; `test_todo_comando_novo_tem_icone_ou_o_declara_vazio`.

### O que a implementação virou (2026-08-25)

**Três decisões divergem do desenho acima, e as três estão registradas aqui.**

**1 · O grupo dos comandos de arquivo é `ARQUIVO`, e não `EDICAO`.** O item escreveu *"no grupo
`EDICAO`"* para os vinte e poucos comandos, com o argumento certo para negrito — *age sobre o que
está aberto agora*. Ele não vale para `abrir_texto`, `salvar_texto` e os exportadores: o critério
que separa os seis grupos é uma pergunta, e a de `ARQUIVO` é **que documento**. `exportar_pgn` já
mora lá; pôr `exportar_rtf` em `EDICAO` seria dois exportadores em dois grupos, que é a divergência
que o catálogo existe para impedir. O critério de aceite que o item pedia junto disso — `EDICAO`
com exatamente um `PRIMARIO` — vale igual, e agora vale nos dois grupos.

**2 · A barra da aba perde a ênfase do botão "Ler folha".** Ele sai em azul hoje
(`style=PRIMARIO`), e `OCR` já tem o seu primário (`ler_melhor`). Manter os dois seria duas ênfases
no mesmo grupo, que `primarios_por_grupo` reprova desde a S-324. O que decide qual sai é o critério
escrito em `ui/estilos.PRIMARIO`: *"a ação que o atalho de teclado também faz"* — e `Ler folha` não
tem tecla. **A ênfase de hoje já contrariava o critério**, e é ela que sai. É a única mudança
visível desta fase na aparência de um controle que já existia.

**3 · Nasce um sexto menu, "Texto".** Os comandos do editor cabem em "Editar" pela pergunta — os
dois mexem no que está aberto agora —, e não cabem pelo desenho: "Editar" tem catorze itens sobre o
**diagrama**, e afogá-los em vinte e oito sobre o **texto** tornaria os dois igualmente difíceis de
achar. O grupo do catálogo continua sendo `EDICAO`/`ARQUIVO`, que é outra pergunta: o grupo diz *o
que o comando é*; o menu diz *onde ele mora*.

**E uma decisão de sequenciamento:** os comandos entram **na fase que os implementa**. A Fase 37
registra dezessete; `paleta_de_glifos`, `inserir_figurina`, `inserir_avaliacao` e os quatro
`estilo_*` entram com a Fase 38, e os quatro exportadores com a Fase 39. Declarar os vinte e oito
agora obrigaria a amarrar função a sete comandos que ainda não existem — e um item de menu que não
faz nada é o defeito que `menu.montar` recusa desde a S-161.

**A conta da janela.** `app_tkinter.py` foi de 1.972 para 2.081 linhas, e a catraca de
`tests/test_packaging.py` subiu junto com o motivo escrito: dezessete linhas são entradas em
`_comandos`, quinze são `_on_texto` e a escolha do desfazível, catorze são `_interruptores`, e o
resto é docstring.

**Testes.** `tests/test_ui_comandos.py::ComandosDoEditorTests`, seis casos, com a varredura de
rótulo à mão agora cobrindo `ui/texto_panel.py`.

---

## S-241 · Negrito, itálico e sublinhado: o atributo, o botão e a tecla que insere tab ✅ implementada (2026-08-25)

**Problema.** Não existem. E a forma óbvia de os fazer é a errada: `tag_configure("negrito",
font=...)` mais um `tag_add` na seleção resolve os três em poucas linhas, na tela, e entrega no
Salvar o mesmo `.txt` de hoje — o achado 1 do roadmap.

Há ainda uma armadilha de teclado que é medida e não opinião. Em `tk8.6/text.tcl:211`:

```tcl
bind Text <Control-i> {
    tk::TextInsert %W \t
}
```

**`Ctrl+I` já insere uma tabulação num `tk.Text`.** E o comentário de `text.tcl:300-302` explica o
que acontece com quem ligar a tecla sem devolver `"break"`: a ligação do widget dispara, a da classe
também, e sai o itálico **mais** o tab. `Ctrl+B` e `Ctrl+U` não têm esse problema — caem em
`bind Text <Control-KeyPress> {# nothing}` (`text.tcl:306`) —, o que torna o `Ctrl+I` o único dos
três que precisa da guarda, e o único que alguém esqueceria.

**Solução.** Três comandos que operam **no documento** e redesenham o widget:

```python
def alternar(doc: DocumentoRico, inicio: int, fim: int, atributo: str) -> DocumentoRico:
    """Liga o atributo no intervalo -- ou desliga, se ele já vale em todo ele."""
```

Pura, em `text/rico.py`, e é ela que os testes afirmam. O painel converte índice do Tk
(`"1.0"`, `"sel.first"`) para deslocamento em caracteres, chama a função, e redesenha. A conversão
é o único pedaço que precisa do widget, e ela é pequena por construção.

Três decisões:

- **Alternar, e não ligar.** Selecionar um trecho já em negrito e apertar `Ctrl+B` desliga — é o que
  todo editor faz, e é o que exige que a decisão seja "vale em **todo** o intervalo?", não "vale no
  primeiro caractere?".
- **Sem seleção, o comando vale para a palavra sob o cursor.** É o comportamento que evita a
  pergunta "por que não aconteceu nada?", e ele é decidido na função pura, com o limite de palavra
  declarado uma vez.
- **A tecla devolve `"break"`, sempre.** Não por precaução genérica: por causa de `text.tcl:211`. O
  teste afirma isso sobre as três teclas, e não só sobre `Ctrl+I`, porque quem acrescentar a quarta
  não vai reler este parágrafo.

Sobre o itálico há uma regra que vem da S-236: **o pincel manual e a régua da linha escrevem no
mesmo campo, e a pessoa ganha.** Um trecho que o leitor marcou como itálico e que alguém desmarcou à
mão fica desmarcado, e a corrida passa a `procedencia="humano"` pela S-239 — porque isso é uma
correção sobre o que o motor leu, e é exatamente o tipo de informação que a S-212 quer.

**Critério de aceite.**

- `alternar` liga quando o atributo não vale em todo o intervalo, e desliga quando vale;
- sem seleção, o alvo é a palavra sob o cursor, e o limite de palavra é declarado num lugar só;
- as três teclas devolvem `"break"`, e o teste prova que `Ctrl+I` não insere tabulação;
- o atributo sobrevive a salvar e reabrir (S-238), e aparece na exportação (S-250);
- desmarcar à mão um itálico detectado pela S-236 vence a detecção e carimba `humano`;
- os botões vêm do catálogo (S-240) e mostram estado ligado/desligado conforme o cursor.

**Testes.** `tests/test_texto_rico.py` (ampliado) e `tests/test_ui_texto_editor.py`:
`test_alternar_liga_quando_o_intervalo_nao_e_uniforme`; `test_alternar_desliga_quando_e_uniforme`;
`test_sem_selecao_vale_a_palavra_sob_o_cursor`; `test_ctrl_i_nao_insere_tabulacao`;
`test_as_tres_teclas_devolvem_break`; `test_desmarcar_o_italico_detectado_carimba_humano`;
`test_o_botao_reflete_o_estado_do_cursor`.

### O que a implementação virou (2026-08-25)

**O formato entra por etiqueta, e não por documento — e a razão foi medida.** O desenho acima diz
que o painel *"chama a função, e redesenha"*. Redesenhar é o que **não** se pode fazer aqui: o
redesenho troca o texto inteiro do widget, e a pilha de desfazer do Tk guarda **índices**, não
conteúdo. Medido nesta máquina: desligar `-undo`, redesenhar e ligar de novo não protege a pilha —
ela sobrevive descrevendo um texto que já não existe, e o `Ctrl+Z` seguinte apaga um pedaço
qualquer. Por isso `desenhar_documento` chama `edit_reset()`, e por isso as ferramentas de formato
escrevem com `tag_add`/`tag_remove`: nenhum caractere muda, o cursor fica onde estava, a rolagem
não salta e o que foi digitado continua desfazível.

**Quem decide continua sendo a função pura.** `rico.intervalo_alvo` responde *onde* (a seleção, ou
a palavra sob o cursor) e `rico.vale_em_todo` responde *ligar ou desligar* — as duas sobre o
documento, e as duas testadas sem janela. O painel só traduz deslocamento em índice do Tk.

**Os botões viraram `Checkbutton` de estilo `Toolbutton`.** O critério de aceite pede que o
controle mostre o estado conforme o cursor, e um `Button` não tem onde dizê-lo. A variável é
espelho: quem a preenche é `_atualizar_ferramentas`, com a mesma `vale_em_todo` que decide a ação —
duas respostas para a mesma pergunta divergiriam, e a que ficaria errada seria a da tela.

**As três teclas são declaradas em `ui/atalhos.TECLAS_DO_EDITOR`**, e não no painel. Elas **não**
são atalhos da janela — só valem dentro do widget, e por isso não entram em `ATALHOS`, que continua
com catorze —, mas neste projeto tecla escrita num painel é o que `test_ui_legenda` proíbe, varrendo
todo o `ui/` atrás de literais `<Control...>`.

**Testes.** `tests/test_texto_rico.py::EdicaoTests` (quinze casos, sem janela) e
`tests/test_ui_texto_editor.py::FerramentasDeFormatoTests` (nove, com widget), incluindo o
`Ctrl+I` que não insere tabulação e o carimbo `humano` sobre o itálico detectado.

---

## S-242 · A cor do autor não pode falar a língua da confiança ✅ implementada (2026-08-25)

**Problema.** A aba já pinta o texto, e a tinta já tem significado. `revisar` sai em
`tokens.PROBLEMA`, `conferir` em `tokens.ATENCAO`, `marca` em `TEXTO_SECUNDARIO`
(`ui/texto_panel.py:64-76, 368-370`), e o corte de baixo é o `MIN_CONFIDENCE` da S-42, emprestado
para a aba não discordar do resto do programa sobre o que é palpite (`text/documento.py:8-20`).

Naquela tela, **vermelho quer dizer "o motor estava adivinhando"**. Um botão de cor de texto com
vermelho na paleta produz duas tintas iguais e dois significados na mesma linha, e ninguém desfaz
isso olhando: nem a pessoa que pintou, três dias depois, nem quem receber o arquivo.

E há o segundo defeito, que já tem medição neste projeto: cor cravada em hexadecimal some quando o
fundo muda. É o que a S-146 mediu no tabuleiro e o que `PieceImages.icon` contorna
(`ui/board_render.py:196-199`), e a pele "Foco" da S-224 é escura.

**Solução.** Separar os dois canais, e dar ao autor um canal que a confiança não usa.

| quem | canal | por quê |
|---|---|---|
| confiança (faixa) | **cor da letra** | é o que já é hoje, e mexer nisso mudaria a aba sem pedido |
| autor (cor escolhida) | **realce atrás da letra** | é um canal livre, e realce nunca é lido como "o motor adivinhou" |
| autor (ênfase forte) | negrito, itálico, sublinhado (S-241) | já resolvido, e sem cor nenhuma |

E, para quem quiser mesmo a **letra** colorida, a segunda metade da regra: a paleta do autor é de
**papéis de `ui/tokens.py`**, resolvidos no desenho — nunca hexadecimal —, e ela **não oferece os
papéis que a faixa usa**. `PROBLEMA` e `ATENCAO` ficam fora da paleta do autor por construção, e o
teste afirma a interseção vazia. É a regra 3 desta spec com um caso concreto.

A paleta que sobra é curta e é o bastante: os papéis existentes que não significam confiança, mais
um conjunto novo declarado em `tokens` para esta finalidade, com o contraste conferido pelos testes
que já existem — `test_ui_semantica_cor.py` e `test_ui_superficies.py` — contra as superfícies das
três peles.

**Critério de aceite.**

- a paleta de cor do autor e o conjunto de papéis usados pela faixa têm **interseção vazia**, e o
  teste afirma isso;
- nenhum hexadecimal aparece no módulo do editor — a varredura é a mesma que a S-145 faz;
- cada papel novo passa no contraste mínimo (`tokens.AA_TEXTO`) sobre as superfícies das peles
  registradas;
- o realce sobrevive a salvar, reabrir e exportar, e no `.txt` **não deixa rastro** — o `.txt` é
  texto puro, e um marcador ali seria lixo;
- trocar o tema com a janela aberta repinta cor de autor e faixa juntas, pelo mesmo caminho de
  `_pintar_faixas` (`ui/texto_panel.py:360-366`);
- "limpar cor" tira a do autor e **não** tira a faixa.

**Testes.** `tests/test_ui_texto_cor.py`: `test_a_paleta_do_autor_nao_usa_papel_de_faixa`;
`test_nenhum_hexadecimal_no_editor`; `test_todo_papel_novo_passa_no_contraste`;
`test_o_realce_sobrevive_ao_arquivo`; `test_o_txt_nao_carrega_marca_de_cor`;
`test_trocar_o_tema_repinta_os_dois_canais`; `test_limpar_cor_nao_apaga_a_faixa`.

### O que a implementação virou (2026-08-25)

**Oito papéis novos, e os valores foram procurados e não escolhidos.** Quatro de letra
(`AUTOR_DESTAQUE`, `AUTOR_CITACAO`, `AUTOR_NOTA`, `AUTOR_VARIANTE`) e quatro de fundo
(`REALCE_*`), com as matizes em 310°, 185°, 130° e 230° — no mínimo 45° entre si e 66° do vermelho
da faixa, que é a régua da S-158. Cada valor de letra é **o mais claro da sua matiz** que ainda
passa 4,8:1 sobre `#f0f0f0` e sobre o branco; cada realce é **o mais saturado** que mantém acima
de 4,7:1 as três tintas que podem cair sobre ele (`PROBLEMA`, `ATENCAO` e o texto normal).

**A régua do realce é ao contrário**, e é o que o item obriga: o que se afirma não é o contraste do
realce, e sim o do que vai por cima dele. Um realce que "passasse no contraste" contra o fundo da
janela e engolisse a letra vermelha da faixa seria o mesmo defeito noutra direção.

**Os quatro nomes dizem intenção, e não cor**: `destaque`, `citacao`, `nota`, `variante`.
"duvidoso" ou "erro" seriam a língua da faixa dita por outra boca — é o que o item proíbe, e ele
proíbe no nome também, não só na tinta.

**A pele escura tem conta própria.** Os oito entram em `NO_CROMO_ESCURO` com a matiz preservada ao
grau, subindo (letra) ou descendo (realce) só em luminosidade — a mesma disciplina que a S-224
impôs aos cinco papéis de texto. Sem isso, uma paleta escolhida contra fundo claro morre na pele
"Foco".

**A interseção vazia é afirmada comparando duas declarações.** `ui/texto_cores.py` não pode
importar o painel (ele traz `tkinter`), então `PAPEIS_DA_FAIXA` é declarado lá e **comparado** com
`texto_panel.PAPEL_DA_FAIXA` no teste: uma faixa nova no painel quebra o teste em vez de aparecer
calada na paleta do autor.

**Testes.** `tests/test_ui_texto_cor.py`, onze casos — interseção vazia, contraste nos dois cromos,
o que cai sobre o realce, separação de matiz e a varredura de hexadecimal nos dois arquivos.

---

## S-243 · Desfazer e refazer que sabem quem tem o foco ✅ implementada (2026-08-25)

**Problema.** O editor tem `undo=True` (`ui/texto_panel.py:169`), e portanto tem a pilha do Tk e as
teclas que o Tk liga a `<<Undo>>`/`<<Redo>>` (`text.tcl:341, 354`). O que ele não tem é **comando,
botão e item de menu** — o desfazer existe e é indescobrível. E `desenhar` chama `edit_reset()` a
cada leitura (`:320`), que é o certo: a pilha da folha anterior não pertence a esta.

Do outro lado, a **S-229** cria desfazer e refazer para o **tabuleiro**, porque a Imagem 2 os
promete e o programa não os tem. Duas pilhas, dois donos, uma tecla só.

**Solução.** Um par de comandos, e o alvo decidido pelo foco:

```python
def alvo_de_desfazer(foco: object, registrados: Sequence[Desfazivel]) -> Desfazivel | None:
    """Quem desfaz agora: o desfazível que contém o widget em foco, ou o último a receber edição."""
```

Pura, testável com objetos de mentira, e é ela que carrega a regra. O painel registra-se como
desfazível; o tabuleiro da S-229 também. Sem foco em nenhum dos dois — o cursor num botão da barra,
por exemplo —, vale **o último que recebeu edição**, e não "nenhum": um `Ctrl+Z` que não faz nada
depois de clicar num botão é o defeito clássico deste desenho.

E a fronteira que este item **não** cruza: a pilha do editor continua sendo a do Tk. Reimplementá-la
sobre o `DocumentoRico` seria refazer o que o widget já faz bem, e a S-235 não exige isso — o
documento é reconstruído do widget quando se salva, e a pilha é do widget porque o gesto de digitar
é do widget.

**Critério de aceite.**

- com o foco no editor, desfazer desfaz a última edição de texto e não toca no tabuleiro;
- com o foco no tabuleiro, desfaz a última edição de posição e não toca no texto;
- sem foco em nenhum dos dois, vale o último que recebeu edição;
- ler a folha de novo limpa a pilha do editor, e não limpa a do tabuleiro;
- os dois comandos aparecem no menu **com o acelerador que o Tk já usa**, em vez de um segundo par;
- o par está uma única vez no catálogo (S-240).

**Testes.** `tests/test_ui_desfazer.py`: `test_o_foco_no_editor_desfaz_texto`;
`test_o_foco_no_tabuleiro_desfaz_posicao`; `test_sem_foco_vale_o_ultimo_editado`;
`test_reler_limpa_so_a_pilha_do_editor`; `test_o_menu_mostra_o_acelerador_do_tk`.

### O que a implementação virou (2026-08-25)

**`ui/desfazivel.py` carrega a regra, e ela é afirmada com objetos de mentira** — foco no editor,
foco no tabuleiro, sem foco em nenhum dos dois, empate e painel que levanta. O `Desfazivel` pede
três coisas: `contem`, `desfazer`/`refazer` e um contador `edicao` que só cresce.

**O contador é a parte que não estava no desenho.** "O último que recebeu edição" precisa de um
número, e ele não pode ser relógio: duas edições no mesmo milissegundo empatariam, e um relógio
depende de a máquina estar com a hora certa. `ResultPanel._registrar_no_historico` conta junto com
a pilha da S-229 — o que entra na pilha é o que conta como edição, e contar num lugar e empilhar
noutro é como os dois divergiriam na próxima origem de mudança de posição.

**A pilha do editor ganhou um instantâneo, e a fronteira mudou de lugar.** O item dizia *"a pilha
do editor continua sendo a do Tk"*, e continua — para o que é digitado. O que a do Tk **não** pode
guardar é a substituição em massa da S-245: ela redesenha, o redesenho zera a pilha (ver a nota da
S-241), e sem um instantâneo do documento anterior desfazer uma troca em massa seria impossível em
vez de ser inteira. `desfazer` esgota a pilha do Tk primeiro e só então volta ao instantâneo — que
é a ordem em que as coisas aconteceram.

**Testes.** `tests/test_ui_desfazer.py`, catorze casos: seis sobre a regra pura, sete sobre a pilha
do painel de verdade e um sobre o acelerador do menu.

---

## S-244 · `Ctrl+S` no editor salva o editor ✅ implementada (2026-08-25)

**Problema.** Hoje ele não faz nada, e são duas camadas somadas.

`shortcuts.TEXT_ENTRY_WIDGETS` inclui `tk.Text`, e `guard` cede a tecla quando o foco está num deles
(`ui/shortcuts.py:19-24, 69-77`). É deliberado desde a S-20 e a razão está escrita lá: `←` dentro de
um campo pertence ao campo, e `Del` apaga um caractere em vez da peça. O efeito é que os dez atalhos
globais **passam direto pelo editor de texto**. Do lado do Tk,
`bind Text <Control-KeyPress> {# nothing}` (`text.tcl:306`) come o que sobrou.

Resultado: com o cursor no texto, `Ctrl+S` não salva a posição — a guarda cedeu — e não salva o
texto — ninguém ligou. **A tecla mais esperada de um editor é um silêncio de duas camadas.**

Tirar a guarda não é opção: ela existe por medição, e `←` no editor tem de continuar movendo o
cursor.

**Solução.** Tornar o ceder **tipado**. O painel em foco declara quais ações são dele, e a guarda
consulta antes de ceder:

```python
class DonoDeAcoes(Protocol):
    def acoes_proprias(self) -> frozenset[str]: ...

def destino(acao: str, foco: object, raiz: object) -> Callable[[], None] | None:
    """A função que atende esta ação agora: a do widget em foco, se ele a declarar; senão a global."""
```

Pura, em `ui/atalhos.py`, ao lado de `ligacoes` — que é onde a tabela de teclas já mora. A aba Texto
declara `{"salvar", "desfazer", "refazer", "achar", "substituir"}`; o painel de resultado não declara
nada e continua atendendo `salvar` como hoje.

Isto é o **oposto** de acrescentar teclas: não entra nenhuma sequência nova em `ATALHOS`. `Ctrl+S`
continua sendo uma tecla só, com um rótulo só na legenda, e o que muda é ela ter destino conforme o
foco — que é o que a pessoa já espera de qualquer programa.

Duas guardas de honestidade:

- **A legenda de atalhos passa a dizer os dois destinos.** Uma tecla que faz duas coisas e uma
  legenda que só conta uma é pior que não ter legenda (`ui/legenda.py`).
- **Ação declarada e não implementada levanta na montagem**, como `atalhos.ligacoes` já faz com
  atalho sem comando (`ui/atalhos.py:101-103`). Declarar "eu trato salvar" e não tratar é a promessa
  vazia que aquele módulo veio proibir.

**Critério de aceite.**

- `destino` devolve a função do widget em foco quando ele declara a ação, e a global quando não;
- com o foco no editor, `Ctrl+S` grava o `.cvtxt` (S-238) e não salva posição nenhuma;
- com o foco em qualquer outro lugar, `Ctrl+S` continua salvando a posição, sem diferença nenhuma;
- `←`, `→` e `Del` continuam sendo do editor, pela guarda de sempre;
- ação declarada sem implementação levanta na montagem, nomeando o painel e a ação;
- a legenda de atalhos mostra os dois destinos da tecla;
- nenhuma sequência nova entra em `ATALHOS` por causa deste item.

**Testes.** `tests/test_ui_atalhos_destino.py`: `test_o_foco_escolhe_o_destino`;
`test_sem_declaracao_vale_o_global`; `test_ctrl_s_no_editor_grava_o_documento`;
`test_ctrl_s_fora_do_editor_salva_a_posicao`; `test_as_setas_continuam_do_editor`;
`test_acao_declarada_sem_implementacao_levanta`; `test_a_legenda_mostra_os_dois_destinos`.

### O que a implementação virou (2026-08-25)

**A guarda passou a perguntar antes de ceder, e nada mais mudou.** `shortcuts.guard` descobre a
ação pela **própria sequência** (`atalhos.acao_de`), consulta `atalhos.destino` e, se o painel em
foco declarou aquela ação, chama a função dele e devolve `"break"`. Quando ninguém declarou, o
código antigo roda inteiro: `←` e `Del` continuam sendo do campo de texto, pela medição da S-20.

**Descobrir a ação pela sequência é o que mantém a tabela como única declaração.** A alternativa
era passar o nome da ação em todo `bind`, e aí a ligação tecla→ação estaria escrita duas vezes.

**`conferir_dono` roda em `_bind_shortcuts`**, antes de ligar: um painel que declara `salvar` e não
atende **come a tecla** e não faz nada — pior que não declarar, porque o global também deixa de
responder.

**A legenda ganhou a segunda linha na mesma célula**, e não uma terceira coluna: `linhas()` lê os
rótulos aos pares, e uma coluna a mais faria a janela mentir sobre a própria estrutura.
`Atalho.no_editor` é o campo, e ele está preenchido em três teclas — `Ctrl+S`, `Ctrl+Z` e `Ctrl+Y`.

**Nenhuma sequência nova entrou em `ATALHOS`**, e o teste conta: continuam catorze.

**Testes.** `tests/test_ui_atalhos_destino.py`, treze casos, incluindo os dois que são o item —
`Ctrl+S` no editor grava o documento, `Ctrl+S` fora dele salva a posição — e o
`test_as_setas_continuam_do_editor`, que é a guarda antiga continuando de pé.

---

## S-245 · Achar e substituir, e o que a substituição em massa sabe sobre o OCR ✅ implementada (2026-08-25)

**Problema.** Não existe busca no editor. Numa aba cujo conteúdo é OCR, isso é mais caro do que
parece: **o erro do OCR se repete**. A S-211 mediu, nas 13 páginas de diagnóstico, 241 substituições
de caixa alta e 96 caracteres espúrios sobre espaço; a S-186 mediu o `l` itálico virando `/` em
**16 de 16** ocorrências do mesmo trecho. Quem corrige à mão faz a mesma correção dezenas de vezes na
mesma página, e não tem como saber se pegou todas.

**Solução.** Achar e substituir, com três coisas que este editor tem e um editor genérico não teria.

**1 · A busca conhece as classes do modelo.** Procurar `♘` acha `♘`, e procurar `N` **oferece** achar
também `♘` — porque `text/classes.py` sabe que as duas são a mesma peça em codificações diferentes,
e porque o acervo mistura as duas (a S-211 mediu 360 figurinas contra 212 notações ASCII em 16
páginas). É oferta, e não tradução automática: a caixa tem um interruptor "casar figurina com letra",
desligado por padrão.

**2 · A substituição em massa mostra o que vai trocar, antes.** Não é preciosismo: `substituir todos`
sobre uma página de OCR é a operação que apaga trabalho, e a S-76 é o registro do que custa um botão
destrutivo que não parece um — **1.405 diagramas sobrescritos por um clique**. A lista de ocorrências
com contexto é a confirmação, e ela também é a que permite marcar uma ou outra para ficar de fora.

**3 · Cada troca vira uma `Correcao` da S-239.** Substituir `,` por `'` em oito lugares é oito
correções sobre o mesmo par de classes, e essa é a informação de que a S-213 (*aplicar a todos os
semelhantes*) precisa. A busca não escreve na base — a regra da S-239 vale igual —, mas registra.

O que fica **fora**: expressão regular. O público desta aba corrige texto de livro; `regex` numa
caixa de substituição é a ferramenta com maior razão entre poder e estrago, e o que ela resolveria
aqui é o que o interruptor de figurina já resolve. Fica registrado como recusa, não como esquecimento.

**Critério de aceite.**

- achar percorre o documento, e não o widget: a mesma função responde com a janela fechada;
- a contagem de ocorrências bate com o número de trocas feitas por `substituir todos`;
- com "casar figurina com letra" ligado, procurar `N` acha `♘`, e desligado não acha;
- `substituir todos` mostra a lista antes, e o que for desmarcado não é trocado;
- cada troca gera uma `Correcao` com `antes`, `depois` e o bloco de origem;
- a busca não altera atributo nenhum: trocar uma palavra em negrito devolve a palavra nova em
  negrito;
- desfazer desfaz a substituição em massa **inteira**, e não troca a troca.

**Testes.** `tests/test_texto_busca.py`: `test_achar_percorre_o_documento_sem_widget`;
`test_a_contagem_bate_com_as_trocas`; `test_a_figurina_casa_com_a_letra_quando_ligado`;
`test_o_desmarcado_nao_e_trocado`; `test_cada_troca_vira_correcao`;
`test_a_troca_preserva_o_atributo`; `test_desfazer_desfaz_a_substituicao_inteira`.

### O que a implementação virou (2026-08-25)

**A `Correcao` da S-239 é derivada, e a substituição só precisa não estragá-la.** O item pedia que
cada troca "virasse uma `Correcao`"; a S-239 já decidiu que correção **não se guarda, se calcula** —
a diferença entre o que o motor leu (a `PaginaLida`, intocada) e o que está na tela. O que a
substituição tem de fazer, então, é preservar o `bloco` da corrida, e é o que
`rico.substituir_intervalo` faz: o texto novo herda atributos, faixa e bloco de quem estava ali.
Com o bloco, `correcao.correcoes` vê o par `(",", "'")` com a contagem, que é o que a S-213 quer.

**O casamento de figurina é só do inglês, e é decisão medida em risco.** `KQRBNP` ↔ `♔♕♖♗♘♙♚♛♜♝♞♟`
entram; as outras notações do acervo colidem entre si — `R` é *rook* em inglês e *rei* em
português, `C` é *cavalo* e nada em inglês. Uma tabela com todas ofereceria, na busca por `R`, a
torre **e** o rei — e a oferta que traz o que não se pediu é pior que oferta nenhuma. A tabela mora
em `text/notacao.py`, junto de `FIGURINAS` e `LETRAS_DE_PECA`, e o caminho inverso é derivado.

**A lista da confirmação é `Listbox` com tudo marcado.** Quem quer trocar tudo aperta o botão; quem
não quer **desmarca**. Começar vazia faria o gesto comum custar um clique por ocorrência — e o
público desta aba é alguém corrigindo a mesma troca dezenas de vezes na mesma página.

**A marca do diagrama atravessa a troca inteira.** `[Diagrama 3]` pode casar com a agulha (procurar
`a` acha o `a` de "Diagrama"), e mesmo assim a corrida sai intacta: apagá-la seria a busca editando
a **estrutura** do texto, e a primeira exportação perderia o diagrama.

**Testes.** `tests/test_texto_busca.py`, catorze casos sem janela, mais os três da pilha em
`tests/test_ui_desfazer.py` que afirmam que desfazer reverte a troca **inteira**.

---

# Fase 38 — A paleta de glifos e símbolos de xadrez

> O pedido nomeia esta fase, e o achado 5 do roadmap decide como ela é feita: a paleta já existe, e
> ela é o metadado do modelo.

## S-246 · A paleta sai do `char_meta.json`, e não de uma lista escrita à mão ✅ implementada (2026-08-25)

**Problema.** Não há como inserir `♘`, `±` ou `⩲` no editor sem sair do programa. O teclado não os
tem, e o acervo é feito deles: a S-211 mediu **360 figurinas** contra 212 notações ASCII em 16
páginas de 4 livros.

E a solução óbvia é a errada. Escrever a lista de símbolos à mão cria uma **segunda lista ao lado da
que o modelo usa**, e a primeira divergência entre as duas é um símbolo que a pessoa insere e que o
OCR nunca poderá ler de volta — o mesmo defeito que a S-324 tirou dos comandos, agora em símbolo.

**Solução.** A paleta é **derivada** de `models/char_meta.json`, que já traz `idx_to_char` e já é
carregado com verificação de `classes_sha256` (`text/modelo.py`). Medido em 2026-08-24, 314 classes:

| família | quantas | o que são |
|---|---:|---|
| alfanuméricas ASCII | 62 | não entram na paleta: o teclado já as tem |
| símbolos ASCII | 24 | `! " # % & ' ( ) * + , - . / : ; = ? @ [ ] _ \| ~` |
| Unicode fora do ASCII | 89 | `♔ ♕ ♖ ♗ ♘ ♙ ± ∓ ⩲ ⩱ ∞ ⇄ → ½ – — •` e os acentuados |
| ligaduras | 139 | `!! !? ?! ?? +- -+ fi ffl ♕x ♗a xf6 e4` |

`text/paleta.py` agrupa o que sobra em prateleiras nomeadas — figurinas, avaliação, anotação de
lance, pontuação, tipografia, acentuados —, e o agrupamento é **dado declarado**, não heurística: o
nome da prateleira de cada símbolo fica numa tabela, e símbolo que ninguém classificou cai numa
prateleira **"não identificado"** em vez de sumir.

Essa última regra não é teórica. Entre as 89 classes Unicode há `⯹ ⯺ ⯻ ⯼ ⯽ ⨀ ⨼ ⟪ ⮜ ⮞ 🗸 ✝`, que são
resíduo de mapeamento das fontes de xadrez dos livros de origem — a mesma família de acidente que a
S-180 registra em `sym_f7`, onde 127 imagens da casa `f7` estavam rotuladas como `÷`. Escondê-los
faria a paleta mentir sobre o que o modelo pode devolver; mostrá-los sem nome faria a paleta parecer
quebrada. A prateleira "não identificado" é a resposta honesta, e ela é uma lista de trabalho para
quem for auditar a base.

**Ligaduras não vão para a paleta**, e é decisão: `xf6` é uma classe do modelo porque o glifo vem
colado no papel, não porque alguém queira inserir "xf6" como símbolo — quem quer digita `x`, `f`,
`6`. Elas ficam registradas na tabela para que a busca da S-245 as conheça.

**Critério de aceite.**

- a paleta é gerada do metadado carregado, e não de uma lista literal — o teste falha se aparecer
  literal de símbolo no módulo;
- todo símbolo da paleta é uma classe do modelo, e o teste compara os dois conjuntos;
- símbolo sem prateleira declarada aparece em "não identificado", e nenhum símbolo é descartado em
  silêncio;
- sem `char_meta.json` no disco a paleta **degrada para um conjunto mínimo declarado** e a aba abre
  — a regra de `ui/theme.py:12-15`: aparência não derruba ferramenta;
- as ligaduras não aparecem na paleta e continuam conhecidas pela busca;
- o módulo não importa `tkinter`.

**Testes.** `tests/test_texto_paleta.py`: `test_a_paleta_sai_do_metadado`;
`test_todo_simbolo_e_classe_do_modelo`; `test_simbolo_sem_prateleira_vai_para_nao_identificado`;
`test_nenhum_simbolo_e_descartado`; `test_sem_metadado_a_paleta_degrada`;
`test_as_ligaduras_ficam_fora_da_paleta`; `test_o_modulo_nao_importa_tkinter`.

### O que a implementação virou (2026-08-25)

**As prateleiras ficaram nove, e o nome de cada uma está na tabela.** Figurinas, Avaliação,
Anotação de lance, Setas e ideias, Formas, Pontuação, Tipografia, Acentuados e "Não identificado".
Somadas dão **113 símbolos** -- exatamente os 24 ASCII mais os 89 Unicode do quadro acima, e o
teste afirma que nenhum se perde no caminho.

**A tabela nomeia o destino, e não a existência.** As doze figurinas estão declaradas em
"Figurinas", e o modelo lê seis: as pretas entram pela prateleira da S-247 enquanto nenhuma classe
as confirma, e passam para "Figurinas" **sozinhas** no dia em que um modelo as aprender. Sem o
destino declarado, o critério de aceite da S-247 -- mover de prateleira sem tocar em código -- não
se cumpriria: elas cairiam em "não identificado".

**O módulo não importa `torch`**, e isso precisou ser conferido: ele lê o metadado por
`text/modelo.ler_metadado`, que só importa `torch` sob `TYPE_CHECKING`. A aba é construída na
abertura da janela, e pagar um framework de aprendizado para desenhar uma lista de símbolos
atrasaria a janela inteira -- a mesma razão do import tardio de `text/leitor.py`.

**Testes.** `tests/test_texto_paleta.py`, vinte e um casos, incluindo o que confere as três
famílias contra o `char_meta.json` versionado (314 classes, 139 ligaduras, 62 alfanuméricas).

---

## S-247 · O que o Unicode tem e o modelo não lê: a prateleira marcada ✅ implementada (2026-08-25)

**Problema.** As seis figurinas do modelo são **só as brancas**: `♔♕♖♗♘♙` são classes,
`♚♛♜♝♞♟` não são. Não é buraco da base — é o que o acervo imprime, porque em notação figurina o
símbolo diz a *peça* e o número do lance diz a *cor*.

Mas cria uma assimetria que o editor não pode esconder. Quem escreve um texto novo quer `♞` às
vezes; quem corrige uma página de OCR **não** quer, porque aquele texto volta para a fila de revisão
de caractere da S-212 e nenhuma classe pode confirmar o que ele inseriu. Uma paleta que oferecesse os
doze símbolos lado a lado, iguais, produziria arquivos em que ninguém distingue o que foi lido do que
foi inventado.

**Solução.** Duas prateleiras, e a diferença é visível e persistente.

- **"O modelo lê"** — o que saiu da S-246. Insere e pronto.
- **"O modelo não lê"** — as seis figurinas pretas, os símbolos de avaliação que faltam, o que o
  Unicode tem e a base não. Inserir daqui é permitido e **marca a corrida**: `fora_do_modelo=True`.

A marca não é enfeite, e ela faz três coisas:

- a corrida aparece com um sinal discreto no editor, no canal do realce (S-242) e não na cor da
  letra;
- ela **não entra** em relatório de correção da S-239 como se fosse leitura corrigida — é texto
  novo, e a S-239 já separa `bloco == -1`;
- a exportação a preserva, e o `.cvtxt` a guarda, para que quem receber o arquivo saiba.

**A prateleira não é uma advertência para quem escreve prosa.** Quem está redigindo um texto próprio
insere `♞` e segue a vida; a marca é para quem depois for perguntar *"isto veio da página?"*. É a
mesma regra 4 da SPEC_TEXTO — campo vazio é melhor que campo inventado — aplicada a um caso em que o
campo não pode ficar vazio: então ele fica **declarado**.

**Critério de aceite.**

- as duas prateleiras são disjuntas, e a união cobre o que a paleta oferece;
- inserir da segunda marca a corrida, e a marca sobrevive a salvar, reabrir e exportar;
- a marca não conta como correção de OCR em relatório nenhum;
- o conjunto "o modelo não lê" é **derivado**, e não escrito à mão: é a diferença entre a lista de
  símbolos oferecidos e as classes do metadado — assim ele encolhe sozinho quando o modelo aprender
  classes novas;
- treinar um modelo novo com as figurinas pretas move símbolos da segunda prateleira para a primeira
  sem tocar em código, e o teste prova isso com um metadado de mentira.

**Testes.** `tests/test_texto_paleta.py` (ampliado):
`test_as_prateleiras_sao_disjuntas`; `test_inserir_fora_do_modelo_marca_a_corrida`;
`test_a_marca_sobrevive_ao_arquivo`; `test_a_marca_nao_conta_como_correcao`;
`test_a_prateleira_e_derivada_do_metadado`; `test_um_modelo_novo_move_o_simbolo_de_prateleira`.

### O que a implementação virou (2026-08-25)

**Os extras declarados são onze, e não seis.** As seis figurinas pretas pelo motivo do item, mais
`…` e as quatro aspas tipográficas `“ ” ‘ ’`: livro impresso as usa e o modelo só conhece `.` e `'`
de ASCII. Quem escreve um texto próprio nesta aba quer as certas, e quem corrige uma página quer
saber que elas não vieram de leitura nenhuma.

**A marca não conta como correção, e isso caiu de graça.** `text/correcao.py` já ignora corrida com
`bloco == SEM_BLOCO`, e um símbolo inserido é exatamente isso -- não precisou de regra nova, só do
teste que trava a propriedade.

**Testes.** `tests/test_texto_paleta.py::PrateleiraQueOModeloNaoLeTests` e
`tests/test_ui_texto_editor.py::PaletaNoWidgetTests`, com o metadado de mentira que já conhece as
pretas provando que elas trocam de prateleira sem uma linha de código.

---

## S-248 · Três formas de inserir, e nenhuma tira a mão do texto ✅ implementada (2026-08-25)

**Problema.** Uma paleta que só se abre por botão obriga a ir ao mouse a cada figurina. Numa linha
de notação — `1...♗xb7 2.♗xb7 ♘d7 3.♗xa8 ♕xa8 4.♘f3±` — são seis viagens numa linha só.

**Solução.** A mesma paleta, três entradas:

**1 · O painel lateral**, aberto pelo comando `paleta_de_glifos`. É a forma de descobrir o que
existe, e a única que mostra as prateleiras inteiras. Fica aberto enquanto se digita.

**2 · A sequência de teclado**, para as seis figurinas e os símbolos de avaliação mais frequentes.
`\N` vira `♘`, `\B` vira `♗`, `\+-` vira `±`. A barra invertida é a marca de escape porque ela é o
caractere mais raro do acervo, e isso foi medido em 2026-08-24 sobre 141.353 caracteres de camada de
texto (4 páginas de cada um dos 41 livros de `PDF/`):

    \    10 ocorrências, em 6 livros       #    14
    |     5                                ~    11
                                           @    46

**Dez em 141 mil, e nenhuma delas é tipografia**: as quatro do `AAGAARD` estão numa camada de OCR de
terceiro, que é ruído por origem. Não é zero, e o item não finge que seja — é um caractere que
aparece uma vez a cada catorze mil, contra `@`, que aparece cinco vezes mais. Um prefixo comum no
material transformaria digitação normal em símbolo, e este é o menos comum dos candidatos.

**3 · A paleta de comandos da S-231**, que a Fase 35 cria a partir do catálogo. Os símbolos entram
nela como comandos `inserir_figurina` e `inserir_avaliacao` com argumento, e saem de graça — que é o
mesmo argumento que a S-231 usa para si.

**A tabela de sequências é dado, e ela é derivada da paleta**, não escrita ao lado dela: cada
sequência aponta para um símbolo que a S-246 já ofereceu, e uma sequência que aponte para símbolo
inexistente levanta na montagem. Duas sequências para o mesmo símbolo é permitido; a mesma sequência
para dois símbolos levanta.

**O que fica de fora:** autocompletar enquanto se digita notação (`Nf3` virando `♘f3` sozinho). É
tentador e é uma troca silenciosa sobre texto que veio de OCR — a mesma coisa que a S-209 proíbe ao
léxico com a frase que dá nome ao item: *"o léxico sinaliza, e nunca troca"*.

**Critério de aceite.**

- as três entradas inserem o mesmo símbolo e produzem a mesma corrida, com a mesma marca da S-247;
- a tabela de sequências é derivada da paleta, e sequência para símbolo inexistente levanta na
  montagem;
- sequência repetida para símbolos diferentes levanta;
- o prefixo de escape é o candidato mais raro do acervo, com a medição publicada, e a sequência
  só dispara quando ela **fecha** — `\` sozinho continua sendo `\`, e um `\` seguido de tecla que
  não abre sequência devolve os dois caracteres;
- nada é trocado automaticamente enquanto se digita;
- inserir com o painel aberto não tira o foco do editor — o cursor continua onde estava, e a próxima
  tecla digita no texto.

**Testes.** `tests/test_texto_paleta.py` (ampliado) e `tests/test_ui_texto_editor.py`:
`test_as_tres_entradas_produzem_a_mesma_corrida`; `test_a_tabela_de_sequencias_e_derivada`;
`test_sequencia_para_simbolo_inexistente_levanta`; `test_sequencia_repetida_levanta`;
`test_nada_e_trocado_automaticamente`; `test_inserir_nao_tira_o_foco_do_editor`;
`test_a_barra_sozinha_continua_barra`.

### O que a implementação virou (2026-08-25)

**As dezoito sequências saem da paleta, e são conferidas na montagem.** Doze figurinas (maiúscula
para a branca, minúscula para a preta), quatro de avaliação, `\inf` e `\...`. `conferir_sequencias`
levanta para sequência que aponta para símbolo que a paleta não oferece e para a mesma sequência
apontando para dois símbolos -- e o teste que prova a segunda regra **junta duas tabelas** em vez de
escrever um literal repetido, porque um `dict` literal com chave repetida não guarda as duas.

**A sequência fecha por acréscimo, e não por temporizador.** `_fechar_sequencia` roda a cada tecla
solta, olha para trás até o tamanho da maior sequência e só troca quando o que está depois da barra
**é** uma sequência inteira. A barra sozinha continua barra; a barra seguida de tecla que não abre
sequência devolve as duas; e `Nf3` continua `Nf3`.

**A terceira porta é o comando, e ela abre uma lista.** `inserir_figurina` e `inserir_avaliacao` não
inserem um símbolo fixo: abrem o menu junto do ponteiro, com a marca "fora do modelo" escrita ao
lado dos que a carregam. É o mesmo desenho de `aparencia`, que também é um comando que abre uma
escolha.

**O foco é afirmado pelo mecanismo, e não por `focus_get`.** Todo botão da paleta é
`takefocus=False`, e o teste confere isso mais o cursor que continua depois do símbolo inserido --
numa janela retirada da tela o foco de teclado é do sistema, e a resposta dele não diz nada sobre o
desenho.

---

## S-249 · Estilo de parágrafo: título, prosa, notação e legenda ✅ implementada (2026-08-25)

**Problema.** Negrito e itálico são atributos de trecho; o que falta é o atributo do **parágrafo**.
E este projeto tem uma razão específica para o querer, que um editor genérico não tem: o modelo de
página da S-211 já distingue os blocos — `BlocoDeTexto`, `BlocoDeDiagrama`, `BlocoDeTabela`,
`BlocoDeTarja` (`text/pagina.py:316-487`) —, e `BlocoDeTexto` já carrega `recuado` (`:329`), que a
S-199 mediu para separar parágrafo de continuação. **A página chega ao editor já sabendo o que é
título, o que é prosa e o que é tarja, e o editor pinta tudo igual.**

**Solução.** Quatro estilos, e cada um com um dono na página lida:

| estilo | de onde ele vem, quando a página o diz | o que ele muda |
|---|---|---|
| `TITULO` | `BlocoDeTarja` e bloco de uma linha em corpo maior | corpo maior, espaço acima |
| `PROSA` | `BlocoDeTexto` com `recuado` | recuo de primeira linha, entrelinha de leitura |
| `NOTACAO` | linha cuja proporção de figurina e dígito passa do corte | fonte de largura fixa, sem recuo |
| `LEGENDA` | a linha atada a um `BlocoDeDiagrama` (`pdf_text.assign_lines_to_diagrams`) | corpo menor, junto da miniatura |

Duas regras que impedem o item de virar um segundo sistema de layout:

- **O estilo é do documento e resolvido por `ui/tipografia.py`.** Nenhum tamanho de fonte em pixel
  entra no editor: `tipografia` já escala pela fonte do sistema desde a S-147, e cravar `12` aqui
  quebraria quem aumentou a fonte do Windows — o mesmo defeito que `ui/texto.py` corrigiu para o
  `wraplength`.
- **`NOTACAO` é o único estilo com um corte medido, e ele precisa ser medido.** A proporção de
  figurina e dígito numa linha de lances é visivelmente diferente da de prosa, e o número que separa
  as duas sai do mesmo corpus das S-236/S-237. Enquanto não estiver medido, `NOTACAO` só existe
  quando alguém o aplica à mão — a regra 5 desta spec.

**Critério de aceite.**

- os quatro estilos são um conjunto fechado, como `GRUPOS` em `ui/comandos.py`, e estilo desconhecido
  levanta;
- o estilo derivado da página aparece sem ninguém pedir, e aplicá-lo à mão o sobrepõe e carimba
  `humano`;
- nenhum tamanho de fonte é cravado no editor: tudo passa por `ui/tipografia.py`;
- o estilo sobrevive a salvar, reabrir e exportar, e cada formato da Fase 39 declara o que faz com
  cada um;
- `NOTACAO` automático só entra com o corte medido e publicado; sem ele, entra desligado.

**Testes.** `tests/test_texto_estilos.py`: `test_o_conjunto_de_estilos_e_fechado`;
`test_estilo_desconhecido_levanta`; `test_a_tarja_vira_titulo`; `test_o_recuo_vira_prosa`;
`test_a_legenda_segue_o_diagrama`; `test_aplicar_a_mao_sobrepoe_e_carimba_humano`;
`test_nenhum_tamanho_de_fonte_cravado`; `test_notacao_automatica_so_com_corte_medido`.

### O que a implementação virou, na Fase 38 (2026-08-25)

> **Esta nota é do primeiro passo do item, e a `legenda` ainda estava de fora.** O que ela conta --
> por que a fonte não mora na etiqueta do estilo -- continua valendo; o que ela diz sobre a legenda
> foi resolvido no mesmo dia, e está na nota seguinte.

**Dois dos quatro estilos eram derivados da página, e os outros dois entravam pela mão.**

    BlocoDeTarja              -> título    texto claro sobre fundo escuro é cabeçalho (S-195)
    BlocoDeTexto com recuado  -> prosa     o recuo que a S-199 mede para separar parágrafo
    notação                   -- só à mão: o corte não foi medido (regra 5 desta spec)
    legenda                   -- só à mão então; ver a nota seguinte

**`legenda` era a divergência, e ela tinha motivo.** O item aponta para
`pdf_text.assign_lines_to_diagrams`, que é de fato quem casa linha com diagrama -- e ele trabalha
sobre `TextLine`, o tipo da **camada do PDF**, e pede `fitz`. A `PaginaLida` não carrega esse
casamento: ela tem o `BlocoDeDiagrama` e os `BlocoDeTexto` lado a lado, sem o vínculo. Redecidir o
vínculo aqui, com uma regra parecida-mas-diferente ("o bloco logo abaixo do diagrama"), seria a
**segunda declaração da mesma regra** -- que é o defeito que este projeto passa o tempo tirando de
si, e seria uma regra não medida ainda por cima.

**O que faltava para o item fechar:** que a `PaginaLida` passasse a carregar o vínculo que
`assign_lines_to_diagrams` já calcula na leitura. Foi por aí — e ver a nota "A legenda fecha o
item", abaixo: o vínculo é informação da leitura, e gravá-lo no modelo de página serve também à
S-253 e ao `[Caption]` do PGN.

**A fonte não mora na etiqueta do estilo, e essa foi a descoberta da implementação.** No Tk **uma**
etiqueta dá a fonte ao trecho, e três coisas a disputam: o corpo do estilo, o negrito e o itálico.
Com a fonte na etiqueta `estilo:titulo`, uma palavra em negrito dentro de um título sairia sem
negrito -- e o atributo continuaria no documento, invisível. A saída é a mesma da S-236 com
`NEGRITO_ITALICO`, generalizada: `estilo:X` leva **geometria** (recuo, espaço acima) e uma etiqueta
`fonte:X:bi`, criada sob demanda, leva a fonte da combinação.

**Nenhum tamanho é cravado**, e o teste varre o painel atrás de `font=` e `size=` com número
literal. O recuo em pixel é derivado da fonte em uso (`measure("    ")`), e não escolhido: quem
aumentou a fonte do Windows recebe um recuo maior.

### A legenda fecha o item (2026-08-25)

**O que faltava era o vínculo, e ele agora mora na página.** `BlocoDeTexto.legenda_de` guarda o
índice do diagrama de que aquele parágrafo é legenda, e quem o preenche é `leitor._atar_legendas`
chamando **`pdf_text.assign_lines_to_diagrams`** -- o dono daquela pergunta desde a S-16, com a
régua já medida: raio de 60 pt, sobreposição mínima no eixo transversal, lado dominante do livro, e
a distribuição por **grupo** (o parágrafo) e não por linha solta.

Nada foi redecidido: o que mudou é o **destino** da resposta. Até aqui ela morria dentro do caminho
de legenda do PGN, e a `PaginaLida` ficava com o diagrama e os parágrafos lado a lado sem dizer
qual descreve qual. Agora ela sobrevive à leitura, serializa no `.cvtxt` e serve também à S-253 --
que passa a saber que aquele parágrafo é legenda.

**A medição, e a guarda que ela obrigou** (`docs/metrics/texto_legenda.json`, as 68 folhas anotadas
do conjunto de campo, 112 diagramas):

| | diagramas |
|---|---:|
| detectados | 112 |
| **com parágrafo atado** | **83 (74,1%)** |
| dos atados, que são linha de lances | 14 (17%) |
| **que viram estilo `legenda`** | **69 (61,6%)** |

A régua da S-16 mede **distância**, não conteúdo -- e a variante logo abaixo do diagrama fica tão
perto quanto a legenda. Pintar `1...♖a8+! 2.♔b5 g3` com o corpo de legenda seria um erro visível,
então o estilo tem uma guarda: `notacao.e_linha_de_notacao`, a régua de lance que este subpacote já
tinha, aplicada por **maioria** dos tokens. `Ivkov—Dueckstein 1967` traz um número que parece
número de lance e continua sendo legenda; seis lances em dez tokens não.

**O vínculo entra na página mesmo quando o estilo não entra.** São duas perguntas: *"este parágrafo
está atado àquele diagrama?"* é da leitura, e *"ele deve ser desenhado como legenda?"* é do editor.
Guardar só a segunda perderia informação que o PGN e o PDF pesquisável querem.

**`notacao` continua entrando só pela mão, e agora isso é medido e não suposto.** Era a única
coisa que este item deixava de dever: o corte que separa uma linha de lances da prosa **dentro do
corpo do texto**. Ele foi medido em 2026-08-26 contra
`docs/metrics/texto_notacao_referencia.jsonl` — 415 blocos de 24 folhas de 15 livros, lidos pelo
**caminho do editor** (`ler_pagina` com o motor padrão) e rotulados à mão por critério editorial:
*o editor poria este bloco no estilo `notacao`?*

| rótulo | blocos | |
|---|---:|---|
| `lance` | 129 | corrida de lances e seu aparato |
| `prosa` | 176 | frase de língua natural, ainda que cite lances por dentro |
| `misto` | 38 | o leitor colou frase inteira **mais** a linha de lances seguinte — não há estilo certo |
| `ilegivel` | 72 | OCR que não permite dizer |

Os 110 blocos das duas últimas linhas ficam fora de precisão e recall, e a fração deles é
resultado: **em 27% dos blocos desta amostra não há estilo certo a aplicar**, e isso é problema do
corte, que vem antes do estilo.

Sobre os 305 julgáveis, com a régua em uso:

| | |
|---|---:|
| precisão | **0,8899** |
| recall | **0,7519** |

**Não entra.** Onze por cento do que ela estilaria é prosa — e os falsos não são aleatórios: são
título corrente e número de página (`o Level 1 1 71`, `1 70 ♔ Grandmaste`), que virariam notação na
cara de quem lê. Um quarto das linhas de lances ficaria sem estilo, e essas também se concentram:
nos livros que escrevem lance em notação que `LANCE` não conhece — descritiva espanhola (`P4TR`,
`T(5)3A`), cirílica transliterada (`Kpf1`) e alemã de letra minúscula (`sf3`, `Lc3`). É a regra 5
desta spec: régua sem vão medido não entra ligada, e a paleta da S-248 já entrega o pincel.

**A mesma medição mostrou vão para uma troca dentro da régua, e essa entrou.** Pontuação solta
deixou de votar em `e_linha_de_notacao`: `28 . . . b6 ! !` são sete tokens, cinco deles pontuação
que o OCR separou do lance que ela qualifica — e com eles no denominador uma linha de lances
inteira fica em minoria de si mesma.

| régua | precisão | recall | F1 |
|---|---:|---:|---:|
| pontuação votava | 0,8800 | 0,6822 | 0,7686 |
| **pontuação não vota** | **0,8899** | **0,7519** | **0,8151** |

Nove linhas de lances a mais, sem nenhum falso a mais. E como a régua é a guarda da legenda, o
`docs/metrics/texto_legenda.json` foi remedido: os atados que são linha de lances caem de 15 para
14, e os diagramas que ganham estilo `legenda` sobem de 68 para 69 (60,7% → 61,6%).

O relatório está em `docs/metrics/texto_notacao_estilo.json`, com a varredura das duas réguas em
quatro maiorias, a tabela de erros por livro e os falsos escritos por extenso.

**Testes.** `tests/test_leitor_de_pagina.py::VinculoDaLegendaTests` (sete casos, do parágrafo logo
abaixo ao vínculo estragado que recusa) e `tests/test_texto_estilos.py` (a legenda que ganha do
recuo, e a variante que não vira legenda).

---

# Fase 39 — A exportação

> O programa já sabe exportar com thread, progresso, cancelamento e relatório
> (`ui/export_controller.py`, 275 linhas), já escreve PDF com o PyMuPDF que já é dependência, e já
> planeja a camada invisível na S-210. O botão "Salvar .txt" ignora os três.

## S-250 · Um lugar só decide o que cada formato faz com o diagrama ✅ implementada (2026-08-25)

**Problema.** Sai um formato: `.txt`, com cabeçalho de procedência (`ui/texto_panel.py:383-412`). Os
quatro formatos desta fase têm em comum uma pergunta que cada um responderia sozinho se ninguém
decidisse por eles: **o que acontece com `[Diagrama N]`?**

E ela não é pequena. `text/documento.py:22-27` já explica por que a marca existe: *"é o que permite
mover o diagrama de lugar no texto, e é o que volta ao arquivo quando alguém exporta. Um diagrama
desenhado sem marca correspondente seria invisível para o texto — e a primeira edição o perderia."*
Quatro exportadores escritos separadamente dariam quatro respostas, e três delas estariam erradas em
silêncio.

**Solução.** `text/exportacao.py`, com um contrato por formato e o mesmo documento de entrada:

```python
class Formato(Protocol):
    extensao: str
    def cabecalho(self, doc: DocumentoRico) -> str: ...
    def corrida(self, c: Corrida) -> str: ...
    def diagrama(self, bloco: BlocoDeDiagrama, recorte: Path | None) -> str: ...
    def rodape(self, doc: DocumentoRico) -> str: ...
```

E a tabela de decisões fica no módulo, visível de uma vez:

| formato | o diagrama vira | a marca `[Diagrama N]` |
|---|---|---|
| `.txt` | nada | **fica** — é a única referência que sobra |
| `.md` | `![Diagrama 3](pasta/diagrama_03.png)` mais a FEN em comentário | fica, como texto alternativo |
| `.html` | `<img>` com a FEN no `alt` e no `data-fen` | fica, no `alt` |
| `.rtf` | imagem embutida | fica, como texto ao lado |
| PDF pesquisável | **o diagrama original, intocado** | não se escreve: a página é a de origem |

Duas regras que valem para os cinco:

- **A marca nunca desaparece.** Nem quando a imagem entra. É a regra de `documento.py:22-27` acima, e o
  teste a afirma nos cinco formatos.
- **Atributo que o formato não tem é perdido explicitamente, e o relatório diz.** O `.txt` não tem
  negrito; a exportação não finge que tem e **conta** quantos atributos caíram. Uma perda silenciosa
  num formato de texto é o que faz alguém descobrir três meses depois que a exportação apagou o
  trabalho.

**Critério de aceite.**

- os cinco formatos saem do mesmo `DocumentoRico`, e nenhum lê a `PaginaLida` por fora;
- a marca `[Diagrama N]` aparece na saída dos cinco;
- cada formato declara o que **não** suporta, e o relatório de exportação conta as perdas por tipo;
- o `.txt` sai idêntico ao de hoje, cabeçalho incluído — a trava de não-regressão;
- exportar duas vezes o mesmo documento dá o mesmo byte, e o teste prova (sem data no corpo do
  arquivo, só no cabeçalho declarado);
- o módulo não importa `tkinter`.

**Testes.** `tests/test_texto_exportacao.py`: `test_os_formatos_saem_do_mesmo_documento`;
`test_a_marca_aparece_nos_cinco_formatos`; `test_cada_formato_declara_o_que_perde`;
`test_o_relatorio_conta_as_perdas`; `test_o_txt_sai_identico_ao_de_hoje`;
`test_exportar_duas_vezes_da_o_mesmo_byte`; `test_o_modulo_nao_importa_tkinter`.

### O que a implementação virou (2026-08-25)

**São quatro formatos de texto e um que não é texto, e a separação passou a ser física.**
`text/exportacao.py` tem os quatro que serializam (`.txt`, `.md`, `.html`, `.rtf`); o PDF
pesquisável mora em `text/pdf_pesquisavel.py`, porque ele não escreve um arquivo de texto: ele abre
o livro e põe uma camada invisível sobre a página original.

**A regra "a marca aparece nos cinco" vale para os quatro, e a tabela do item já dizia isso.** A
linha do PDF é explícita — *"não se escreve: a página é a de origem"* —, e a razão está no módulo: a
camada existe para espelhar o **texto do livro**, e um `[Diagrama 3]` ali apareceria a quem copiasse
a página sem nunca ter estado impresso nela. As duas frases do item se contradiziam; o que ficou é a
tabela, que é a decisão específica.

**`montar` entrou no contrato**, e ele existe por causa da trava de não-regressão: o `.txt` grava
`cabecalho + corpo.strip() + quebra` desde a S-211, e aparar o conteúdo inteiro tiraria a quebra
dupla do cabeçalho. Os outros três usam o padrão (concatenar), e o `.txt` sobrescreve.

**`ATRIBUTOS` é derivado de `rico.Atributos`.** Recopiar a lista faria um atributo novo entrar sem
que nenhum formato dissesse o que faz com ele — que é o buraco que o inventário da S-256 fecha.

**Testes.** `tests/test_texto_exportacao.py`, vinte e dois casos, incluindo o `.txt` byte a byte e o
"exportar duas vezes dá o mesmo byte" nos quatro.

---

## S-251 · `.md` e `.html`: o que diffa e o que abre no navegador ✅ implementada (2026-08-25)

**Problema.** O `.txt` perde tudo o que a Fase 37 acrescenta. Os dois formatos mais baratos que não
perdem são texto puro e não pedem dependência nenhuma.

**Solução.** Dois formatos, cada um com uma razão de existir que o outro não cobre.

**`.md`** — porque ele **diffa**. Uma página corrigida hoje e recorrigida amanhã produz duas versões
comparáveis linha a linha, e é assim que se vê o que mudou. Negrito é `**`, itálico é `*`, título é
`#`; a cor de autor **não tem sintaxe** e é declarada como perda; a faixa de confiança também. O
diagrama vira imagem com a FEN em comentário HTML, que o Markdown ignora e o olho lê.

**`.html`** — porque ele **abre**. É o único formato desta fase que mostra, no navegador de qualquer
máquina, exatamente o que a aba mostrava: negrito, itálico, cor de autor, faixa de confiança,
figurina e diagrama. E é o formato para mandar a página corrigida para alguém.

Duas decisões que o `.html` obriga a tomar, e as duas já têm dono neste projeto:

- **A cor sai de `ui/tokens.py`, resolvida para o tema claro, e vai para o `<style>` do arquivo.** É
  a única vez em toda esta spec em que um hexadecimal é escrito, e ele é *derivado* — o teste afirma
  que nenhum literal de cor aparece no exportador e que toda cor da saída bate com `tokens.cor`.
- **A figurina precisa de fonte, e o arquivo não a embute.** `♘` depende do que a máquina de destino
  tem instalado, e nenhuma fonte é copiada para cá antes de a licença ser conferida — a mesma trava
  que a S-210 registra. O `<style>` declara uma pilha de fontes com reserva, e o cabeçalho do arquivo
  diz que a figurina depende da máquina. Declarar é o que se pode fazer; embutir não.

**Critério de aceite.**

- o `.md` reabre no editor com negrito, itálico e título intactos — ida e volta afirmada;
- o `.md` declara perda de cor e de faixa, e o relatório as conta;
- o `.html` abre num navegador sem arquivo externo além das imagens de diagrama;
- nenhuma cor literal aparece no exportador: toda cor da saída vem de `tokens.cor`;
- o `.html` escapa `<`, `>` e `&` — inclusive os que vieram do OCR, que produz caractere espúrio por
  medição da S-211;
- o arquivo declara que a figurina depende da fonte da máquina de destino.

**Testes.** `tests/test_texto_exportacao.py` (ampliado): `test_o_md_ida_e_volta_preserva_o_atributo`;
`test_o_md_declara_a_perda_de_cor`; `test_o_html_nao_depende_de_arquivo_externo`;
`test_nenhuma_cor_literal_no_exportador`; `test_o_html_escapa_o_que_veio_do_ocr`;
`test_o_html_avisa_sobre_a_fonte_de_figurina`.

### O que a implementação virou (2026-08-25)

**O `.html` recebe as cores prontas, e não sabe uma sequer.** `Html(cores={...})` é preenchido pelo
painel com `tokens.cor(...)` resolvido **no momento da exportação** — então o arquivo sai com a
paleta do tema em uso, e o teste varre o módulo atrás de literal de cor e não acha nenhum.

**A ida e a volta do `.md` é afirmada pela marcação, e não por um leitor de Markdown.** Escrever um
`parse` de Markdown para provar o ida-e-volta seria um segundo formato dentro do primeiro; o que o
teste afirma é o que o item pede — `**negrito**`, `*itálico*`, `# título` — mais a regra que quase
se perde: `**negrito** ` e não `**negrito **`, porque a segunda forma o Markdown não lê como
negrito.

**O aviso da fonte é uma linha no corpo do arquivo**, e não um comentário: quem abre o `.html` num
navegador sem fonte de xadrez vê quadrados no lugar das figurinas, e a explicação tem de estar onde
ele está olhando.

---

## S-252 · `.rtf`, e por que não `.docx` ✅ implementada (2026-08-25)

**Problema.** Quem recebe uma página corrigida costuma querer abri-la no Word, e nem `.md` nem
`.html` são isso.

**Solução, com a conta explícita.** O `.rtf` é texto puro, escrito com a biblioteca padrão, e o Word,
o LibreOffice e o WordPad abrem os três. Negrito, itálico, sublinhado, cor, corpo e imagem embutida
cabem todos nele. **São ~200 linhas de Python e zero dependência.**

O `.docx` faria o mesmo com `python-docx`, e a conta é a que este projeto já fez três vezes — na S-54
com o `streamlit`, na S-137 com o `pyarrow`, na S-42 com o motor de OCR: **dependência obrigatória
para o que um extra ou nenhuma dependência já cobre é custo puro no que o usuário baixa.** O bundle
já é medido em `docs/metrics/bundle.json`, e a catraca existe.

Registrado, então, como decisão e não como falta: **se o `.rtf` provar insuficiente na prática** — o
sinal seria alguém precisar de tabela, sumário ou estilo nomeado do Word —, `python-docx` entra como
**extra** `docx`, no mesmo molde de `onnx`, `ocr` e `demo`, e o `.docx` vira um formato que avisa em
pt-BR quando a dependência falta. Nunca obrigatória.

Duas armadilhas do formato, e as duas viram teste:

- **RTF é ASCII com escapes.** Todo caractere fora do ASCII vira `\uN?`, com o número **assinado** —
  `♘` (U+2658) é `\u9816?`, e acima de 32767 o número fica negativo. Uma página de xadrez é feita justamente
  desses caracteres, então o caso raro aqui é o caso comum.
- **A chave e a barra invertida escapam**: `{`, `}` e `\` no texto viram `\{`, `\}` e `\\`. Texto de
  OCR produz esses caracteres por engano — a S-211 mediu 96 caracteres espúrios em 13 páginas —, e um
  `}` não escapado quebra o arquivo inteiro, não só a linha.

**Critério de aceite.**

- o `.rtf` abre no Word e no LibreOffice com negrito, itálico, sublinhado, cor e imagem;
- toda figurina sai como escape Unicode correto, com o número assinado, e o teste cobre acima e
  abaixo de 32767;
- `{`, `}` e `\` do texto são escapados, e o teste usa uma página com caractere espúrio de OCR;
- nenhuma dependência nova entra no `pyproject.toml` por causa deste item;
- se um dia entrar, ela entra como extra e o formato avisa em pt-BR quando falta — o molde de
  `cvoff-export-onnx`.

**Testes.** `tests/test_texto_rtf.py`: `test_a_figurina_vira_escape_assinado`;
`test_o_escape_cobre_acima_de_32767`; `test_a_chave_e_a_barra_sao_escapadas`;
`test_o_arquivo_abre_com_os_atributos`; `test_nenhuma_dependencia_nova`.

### O que a implementação virou (2026-08-25)

**São 60 linhas, e não 200.** O escape assinado é seis linhas; o resto é a marcação de negrito,
itálico, sublinhado e corpo. A imagem embutida **não** entrou: ela pede o PNG do recorte em
hexadecimal dentro do arquivo, e o que se ganharia é o que o `.html` já dá melhor. O que entrou é a
marca `[Diagrama N]` como texto, que é o que o item exige de todos os formatos.

**O par substituto foi o caso que a implementação encontrou.** O item fala de "acima de 32767"; o
que aparece de verdade no acervo é `🗸` (U+1F5F8), **acima do BMP**, que não cabe numa unidade de 16
bits. O RTF aceita o par substituto, e é o que se escreve — duas unidades, as duas assinadas.

**Nenhuma dependência nova**, e o teste trava a decisão varrendo o `pyproject.toml` inteiro atrás de
`docx`.

---

## S-253 · O PDF pesquisável do próprio livro, com o texto já corrigido ✅ implementada (2026-08-25)

**Problema.** O acervo tem livros sem camada de texto — 11 dos 41 na amostra de 2026-08-24 — e
livros cuja camada erra a notação inteira, que é o achado que a S-211 mediu: **zero figurinas** na
camada contra 360 no classificador, com três codificações diferentes em quatro livros. Buscar `Nf3`
num livro de xadrez é a coisa mais óbvia a querer fazer, e não dá.

A **S-210** já planeja a camada invisível, e ela parte do que o motor leu. **Este item é a outra
ponta:** a camada feita do texto que **uma pessoa já corrigiu** — que é a melhor versão daquela
página que vai existir.

**Solução, e ela é curta porque não reimplementa nada.** O exportador do editor entrega à S-210 um
`DocumentoRico` em vez de uma `PaginaLida`, e a S-210 escreve a camada como já escreve. O que este
item acrescenta é a ligação e três regras:

- **A página não muda um pixel.** É o primeiro critério de aceite da S-210, e ele vale igual aqui —
  conferido comparando os pixmaps.
- **A posição vem do bloco, e o texto vem da corrida.** Cada corrida sabe de que bloco veio
  (`Corrida.bloco`, S-235), e o bloco tem bbox. Corrida escrita do zero (`bloco == -1`) **não entra
  na camada**: não há onde a pôr, e inventar posição é pior que não ter o texto.
- **A procedência vai no metadado do PDF.** Um PDF cuja camada foi corrigida à mão é um documento
  diferente de um cuja camada saiu do OCR, e quem o receber precisa poder saber. É a S-219 outra vez:
  o relatório diz com que código e com que modelo foi medido.

**A dependência que trava, e ela é declarada:** a camada com figurina precisa de uma fonte que tenha
os glifos de xadrez, e **nenhuma fonte é copiada para cá antes de a licença ser conferida** — a
mesma trava que a S-210 já registra. Sem fonte redistribuível, este item entrega a camada do alfabeto
latino e escreve, no relatório, quantas figurinas ficaram de fora.

**Critério de aceite.**

- a página de saída é pixel a pixel idêntica à de entrada;
- buscar uma palavra corrigida à mão a encontra, e o retângulo devolvido cobre a palavra na página;
- corrida sem bloco de origem não entra na camada, e o relatório a conta;
- o metadado do PDF declara que a camada tem correção humana, com a data;
- sem fonte de figurina, o item entrega o latino e conta o que ficou de fora — não falha;
- o `--dry-run` diz o que faria sem escrever nada, como na S-210.

**Testes.** `tests/test_texto_pdf_pesquisavel.py`: `test_a_pagina_nao_muda_um_pixel`;
`test_a_busca_encontra_a_palavra_corrigida`; `test_a_corrida_sem_bloco_nao_entra`;
`test_o_metadado_declara_correcao_humana`; `test_sem_fonte_de_figurina_entrega_o_latino`;
`test_o_dry_run_nao_escreve`.

### O que a implementação virou (2026-08-25)

**A S-210 ainda não existe, e este item não esperou por ela.** O desenho dizia *"o exportador
entrega à S-210 um `DocumentoRico` e ela escreve a camada como já escreve"* — só que a S-210 está ⬜
planejada. `text/pdf_pesquisavel.py` escreve a camada por conta própria, em ~60 linhas de PyMuPDF
(que já é dependência), e o que ele **não** faz é reimplementar a S-210: aquele item é sobre o livro
inteiro a partir do que o motor leu; este é sobre **uma folha** a partir do que uma pessoa corrigiu.
Quando a S-210 chegar, o que se compartilha é a escrita da camada.

**O corpo da fonte é escolhido pela caixa, e não fixado.** `insert_textbox` devolve negativo quando
o texto não cabe, e o texto corrigido pode ser mais longo que o impresso — a busca no lugar errado
seria pior que a busca ausente. O laço tenta de 11 pt a 4 pt e para no primeiro que couber.

**A saída tem uma folha, e não o livro.** A aba é da folha aberta; gravar 400 páginas para publicar
uma seria surpresa cara para quem clicou em "exportar".

**Medido aqui:** a página de saída é byte a byte idêntica à de entrada no pixmap a 110 dpi, a busca
por uma palavra corrigida a encontra dentro do retângulo do bloco, e `♘` sai da camada e entra na
contagem — 1 caractere fora, com o motivo (a base 14 não tem figurina, e nenhuma fonte é copiada
para cá antes de a licença ser conferida).

---

## S-254 · Exportar não trava a janela, e diz o que não coube ✅ implementada (2026-08-25)

**Problema.** `salvar` escreve na thread da janela (`ui/texto_panel.py:409-411`). Para um `.txt` de
uma folha isso é imperceptível, e a aba está certa em fazê-lo assim hoje. **Deixa de estar** com o
`.rtf` com imagens embutidas e com o PDF pesquisável, que abre o livro, escreve a camada e grava um
arquivo novo.

E a aba já sabe fazer certo: a leitura roda numa thread, volta por `after`, e o `BusyRegistry`
registra com `loses_work=False` (`ui/texto_panel.py:234-275`). O que falta é a exportação usar o
mesmo caminho.

**Solução.** A exportação vai para o molde que o programa já tem duas vezes — o
`ui/export_controller.py` do PGN e a leitura desta própria aba:

- thread para o trabalho, `after` para voltar, `BusyRegistry` para dizer que há trabalho em curso;
- **cancelamento**, que depois da S-163 mora no rodapé;
- `loses_work=True` **na exportação**, ao contrário da leitura: fechar no meio deixa um arquivo pela
  metade, e o registro precisa dizer isso;
- a mesma guarda de `_na_janela` (`:260-273`): fechar a aba durante uma exportação não pode levantar
  `TclError` dentro da thread.

E o relatório, que é a metade do item que não é infraestrutura. `describe_report` já existe para o
PGN (`ui/export_controller.py:44`), e o do editor responde a três perguntas:

    escrito       docs/saida/aagaard_folha58.rtf, 41 KB
    perdido       12 realces (o formato não tem), 1 diagrama sem recorte no PDF
    avisado       3 símbolos fora do modelo (S-247), 2 corridas sem bloco de origem

**A linha do meio é o item.** Uma exportação que perde coisa e não diz é como a exportação que
apagou trabalho três meses antes de alguém notar — e as perdas por formato já estão declaradas na
S-250, então contá-las é somar o que o exportador já sabe.

**Critério de aceite.**

- nenhuma exportação escreve na thread da janela;
- o `BusyRegistry` recebe `loses_work=True`, e o rodapé mostra progresso e cancelamento;
- cancelar não deixa arquivo pela metade — a escrita é atômica, como em `atomic_io`;
- fechar a aba durante a exportação não levanta, e o token é liberado;
- o relatório traz escrito, perdido e avisado, e o teste afirma as três seções;
- exportar com a aba vazia diz o que falta no rodapé, e não abre diálogo — o critério de
  `tests/test_ui_retorno_modal.py`.

**Testes.** `tests/test_ui_texto_exportacao.py`: `test_a_exportacao_sai_da_thread_da_janela`;
`test_o_registro_declara_que_perde_trabalho`; `test_cancelar_nao_deixa_arquivo_pela_metade`;
`test_fechar_durante_a_exportacao_nao_levanta`; `test_o_relatorio_traz_as_tres_secoes`;
`test_exportar_vazio_avisa_no_rodape`.

### O que a implementação virou (2026-08-25)

**O molde é o da leitura desta própria aba, e não o `ui/export_controller.py`.** Aquele controlador é
do PGN do livro inteiro, com progresso por página e um relatório próprio; aqui o trabalho é um
arquivo só. O que se reusou dele é a forma — thread, `after`, `BusyRegistry`, cancelamento —, e o que
se reusou da leitura é a guarda de `_na_janela`, que impede o `TclError` dentro da thread quando
alguém fecha a aba no meio.

**O cancelamento acontece antes da escrita, e é isso que o torna barato.** Montar o conteúdo é o que
demora; escrever é atômico e instantâneo. `_gravar_exportacao` confere o evento depois de montar e
antes de gravar — então cancelar **nunca** deixa arquivo pela metade, sem precisar de limpeza.

**O relatório vai para o rodapé com as três seções em uma linha**, separadas por `·`. A caixa modal
ficou de fora de propósito: exportação que deu certo não é notícia que interrompe, e a que deu errado
vira mensagem de erro no mesmo lugar (`tests/test_ui_retorno_modal.py`).

**Testes.** `tests/test_ui_texto_exportacao.py`, oito casos com janela de verdade — o arquivo que só
aparece depois de a janela voltar a girar, o `loses_work=True` espiado no registro, o cancelamento
que não escreve, e fechar a aba no meio sem levantar.

---

# Fase 40 — O que sustenta o resto

> Dois itens que só fazem sentido depois de o editor existir, e que são o preço de ele existir.

## S-255 · O rascunho automático, e a recuperação depois do fechamento ✅ implementada (2026-08-25)

**Problema.** Uma sessão de correção custa caro e não é reproduzível. A leitura da folha custa ~1 s
com o glifo e ~40 s com o modo bloco (`docs/metrics/texto_pagina.json`); a correção à mão custa a
tarde de alguém, e **é a única coisa desta aba que não sai de graça de uma releitura**
(`ui/texto_panel.py:386-388`).

Hoje ela vive só na memória do widget até alguém apertar Salvar. Fechar a aba, fechar o programa,
uma falha do Tk, um `TclError` numa thread — e some tudo. O programa **já sabe** que isso é sério:
`BusyRegistry` tem `loses_work` justamente para avisar quando fechar custa trabalho (`ui/busy.py`).

**Solução.** Rascunho automático em `data/rascunhos/`, no formato `.cvtxt` da S-238:

- grava **por inatividade**, e não por relógio: alguns segundos depois da última tecla. Um relógio
  fixo grava no meio da digitação e disputa o disco com quem está trabalhando;
- grava só quando **está sujo** — a aba já rastreia isso (`self._sujo`, `ui/texto_panel.py:372-376`);
- escreve com `atomic_write_text`, pelo mesmo motivo de sempre;
- **um rascunho por folha de cada documento**, com chave estável — o mesmo desenho de
  `state._history_key` (`ui/state.py:176`), que já resolve "que página deste PDF eu estava vendo";
- na abertura da folha, **se houver rascunho mais novo que a leitura, a aba oferece recuperar** —
  oferece, não aplica: sobrescrever o que a pessoa acabou de ler com um rascunho de ontem é o
  contrário do que ela quer.

E a regra que impede a pasta de crescer para sempre: rascunho recuperado ou salvo é apagado; o que
sobra tem teto por documento, e o mais antigo sai primeiro.

**Critério de aceite.**

- o rascunho é gravado depois da inatividade e só com o documento sujo;
- fechar a aba com trabalho não salvo deixa o rascunho no disco;
- reabrir a mesma folha do mesmo documento oferece o rascunho, com a data, e **não** o aplica
  sozinho;
- recusar a oferta não apaga o rascunho; salvar ou recuperar apaga;
- a chave é estável para o mesmo documento e folha, e diferente entre documentos de mesmo nome em
  pastas diferentes — o caso que `state._history_key` já trata;
- a pasta tem teto, e o descarte é do mais antigo.

**Testes.** `tests/test_texto_rascunho.py`: `test_grava_apos_inatividade_e_so_se_sujo`;
`test_fechar_deixa_o_rascunho`; `test_reabrir_oferece_e_nao_aplica`;
`test_recusar_nao_apaga`; `test_salvar_apaga`; `test_a_chave_distingue_documentos_homonimos`;
`test_a_pasta_tem_teto`.

### O que a implementação virou (2026-08-25)

**A chave carrega o nome legível *e* a impressão do caminho.** `ui/state._history_key` resolve o
caminho e usa a string inteira como chave de um dicionário; aqui a chave vira **nome de arquivo**, e
o Windows recusa metade da pontuação de um caminho. O nome fica `kemeri_f58_3f2a1b9c04.cvtxt`: o
`stem` do livro para a pasta ser legível por quem a abrir, a folha em base 1 como a tela a escreve,
e dez hexadecimais do SHA-1 do caminho resolvido -- que é o que separa dois livros de mesmo nome em
pastas diferentes, o caso que aquele módulo já tratava.

**O rascunho é um `.cvtxt`, e não um formato novo.** Recuperar um rascunho é reabrir um documento, e
o formato da S-238 já grava tudo: faixa, atributo, bloco, procedência e a `PaginaLida`.

**A poda é por documento, e não pela pasta.** Quem trabalha em dois livros na mesma semana não pode
perder o rascunho de um porque abriu muitas folhas do outro. Teto de oito por livro, e o mais antigo
sai primeiro.

**A pergunta de recuperação é o quadragésimo nono `messagebox` da interface**, e a catraca de
`tests/test_ui_retorno_modal.py` subiu com o motivo escrito: é **decisão** pela régua daquele
arquivo -- o que está na tela muda conforme a resposta. Por isso ela diz a data: um rascunho de dez
minutos atrás é o trabalho que a pessoa acabou de perder, e um de três semanas é lixo que ela já
esqueceu.

**A oferta acontece depois de desenhar**, e não antes: se a pessoa recusar, o que fica na tela é a
leitura que ela acabou de pedir.

**O painel recebeu `pasta_de_rascunhos=`**, e é por causa da suíte: sem isso os testes leriam
`data/rascunhos/` da máquina de quem os roda, e um rascunho ali abriria a pergunta de recuperação no
meio de um teste -- que trava tudo esperando um clique que ninguém vai dar.

**Testes.** `tests/test_texto_rascunho.py`, dezoito casos: cinco sobre a chave, seis sobre o disco e
sete com a aba de verdade, incluindo o "grava só se sujo", o "recusar não apaga" e o "salvar apaga".

---

## S-256 · O inventário do editor: nada de recurso sem comando, atalho e teste ✅ implementada (2026-08-25)

**Problema.** Este plano acrescenta mais de vinte recursos a uma aba que hoje tem seis controles, e
**cada um deles é fácil de fazer errado rápido**. `tag_configure("negrito", font=...)` mais um
`tag_add` resolve o negrito na tela em quatro linhas e entrega, no Salvar, o `.txt` de hoje — o
achado 1 do roadmap, que nenhum teste de interface pegaria porque na tela está tudo certo.

É a mesma classe de defeito que a S-233 mede para as peles, com um agravante: lá o comando existe e
está escondido; aqui o recurso **existe e não persiste**, que é pior, porque parece funcionar.

**Solução.** Um inventário afirmado por teste, com quatro perguntas:

1. **Todo atributo do `DocumentoRico` sobrevive ao ciclo completo** — editar, salvar, reabrir,
   exportar, reimportar onde o formato permite. O teste é paramétrico sobre os campos de
   `Atributos`, então **um campo novo entra no teste sozinho**, e quem o acrescentar sem tratar a
   persistência descobre na suíte.
2. **Todo recurso do editor é um comando do catálogo** (S-240), com rótulo, grupo e papel — e a
   varredura sintática da S-324 cobre `ui/texto_panel.py`, que hoje ela não cobre.
3. **Todo comando alcançável de algum jeito nas três peles** — é a S-233 aplicada ao editor, e ela
   passa a incluir os comandos desta spec no inventário que já faz.
4. **Todo atributo declarado em algum formato de exportação**, mesmo que a declaração seja "este
   formato não tem isto" (S-250). Perda silenciosa é o que o item existe para impedir.

O teste que carrega a primeira pergunta é o que mais paga:

```python
def test_todo_atributo_sobrevive_ao_ciclo(self) -> None:
    for campo in fields(Atributos):
        with self.subTest(campo=campo.name):
            ...   # editar -> salvar -> reabrir -> comparar
```

**Critério de aceite.**

- o teste de ciclo é paramétrico sobre `fields(Atributos)`, e um campo novo sem persistência o
  reprova;
- nenhum rótulo escrito à mão sobra em `ui/texto_panel.py`;
- todo comando do editor aparece no inventário de alcance da S-233;
- todo atributo aparece na tabela de suporte por formato, com "não suporta" sendo uma resposta
  válida e explícita;
- o inventário é publicado como o dos outros: um JSON em `docs/metrics/`, com data e commit, na
  disciplina da S-219.

**Testes.** `tests/test_texto_inventario_editor.py`: `test_todo_atributo_sobrevive_ao_ciclo`;
`test_nenhum_rotulo_a_mao_no_painel`; `test_todo_comando_do_editor_esta_no_inventario`;
`test_todo_atributo_esta_declarado_por_formato`; `test_o_inventario_publica_data_e_commit`.

### O que a implementação virou (2026-08-25)

**O teste paramétrico ganhou uma tabela de valores, e ela é conferida.** `fields(Atributos)` diz
quais campos existem; o que ele não diz é **que valor não-padrão** usar em cada um -- e um campo novo
sem valor faria o laço passar em verde sem exercitar nada. `VALOR_DE_TESTE` é a tabela, e
`test_todo_atributo_tem_valor_de_teste` cobra que ela cubra os campos.

**O ciclo afirmado é tela → widget → arquivo, e não só arquivo.** O defeito que o item persegue é o
atributo que existe **como tag do Tk** e morre na gravação -- então o documento tem de passar pelo
widget e voltar de lá antes de ir para o disco. É o `documento_atual()` no meio do caminho que faz o
teste valer.

**O inventário é publicado por um comando novo, `cvoff-editor-inventario`.** O
`cvoff-texto-inventario` que já existia é outro assunto (conta recorte de caractere em
`training_data/`), e juntar os dois num só faria um comando que responde a duas perguntas sem
relação. O novo grava `docs/metrics/editor_inventario_AAAAMMDD.json` com data e commit, e **devolve
1** quando alguma pele esconde comando ou algum atributo não tem formato que o suporte -- assim ele
serve de porta de CI, e não só de relatório.

**A tabela comando → método do painel é declarada.** Oito dos vinte e oito divergem no nome
(`ler_folha` é `ler`, `exportar_txt` é `salvar`, `cor_do_texto` é `escolher_cor`), e todos por razão
anterior ao catálogo. Declarar a tabela é o que permite ao teste cobrar que **todo comando do editor
tenha dono** -- e é ela que o inventário publica.

**Um comando ganhou método por causa deste item:** `modo_bloco` apontava para a variável do
`Checkbutton`, que não é dono de nada. Virou `modo_bloco_mudou`, que reage à mudança dizendo o preço
no rodapé -- ~40 s por folha contra ~1 s do glifo. Uma caixa marcada em silêncio é a explicação que
falta quando a leitura seguinte demora quarenta vezes mais.

**O que o inventário publicado diz hoje:** 28 comandos do editor, 7 atributos do documento, 4
formatos de exportação, 124 símbolos na paleta, **nenhuma** pele perdendo comando, **nenhum**
atributo sem formato que o suporte e **nenhum** comando fora do menu.

**Testes.** `tests/test_texto_inventario_editor.py`, treze casos e 54 subtestes.

---

# O item que a Fase 36 mediu e não é do editor

> Um item só, e ele não pertence a nenhuma das cinco fases: saiu da medição da S-237, mexe no
> **leitor** e não no editor, e está aqui porque foi aqui que foi encontrado e medido. Fica com
> número em vez de ficar como observação, porque observação sem número volta como surpresa — é o
> que a S-135 registrou sobre este projeto.

## S-257 · A margem da coluna sai da mediana, e onde há muito recuo ela é o recuo ✅ medida e recusada (2026-08-26)

**Problema.** `paragrafos.metricas_por_coluna` toma a **mediana** das esquerdas das linhas como
margem da coluna, e a regra `recuou` compara cada linha com ela. Numa diagramação de recuo de
primeira linha com parágrafos curtos, quase metade das linhas começa no recuo — e a mediana devolve
o **recuo** no lugar da margem. Com a margem valendo o recuo, `recuou` é falso para **toda** linha
da coluna: a régua não morre num parágrafo, morre na coluna inteira, e em silêncio.

O fenômeno é real e foi confirmado: no `Dvoretsky - Dvoretsky's Endgame Manual (2025)`, folha 50 da
camada, a coluna da esquerda tem margem em 29 pt, recuo em 40 pt, e a mediana devolve 40.

**A medição que faltava.** Trocar a mediana por um quantil baixo é uma linha de código, e o efeito
é grande — mas "mais blocos" é indistinguível de "pior" sem referência: parte dos cortes novos é
parágrafo que estava grudado e passou a sair certo, parte é parágrafo inteiro despedaçado, e as
duas coisas mexem o mesmo contador na mesma direção.

**A referência, e a que foi recusada.** `docs/metrics/texto_paragrafo_referencia.jsonl` — 24 folhas
de 14 livros, 1.675 linhas, das quais **1.273 com referência** e **323 começos de parágrafo**. O
sinal é o **fim da linha**: em texto justificado toda linha alcança a margem direita, menos a última
de cada parágrafo. Ele não olha nem o recuo nem o vão vertical, que são as duas réguas sob medição,
e por isso não é circular. Onde a coluna não é justificada ele não diz nada, e ali a referência é
`null` — declarado, e não escondido.

O que foi **recusado** como referência: o `group_id` da camada do PDF, isto é, o bloco que o
produtor gravou. Parecia a referência de terceiro ideal, e não é. Medido no `AAGAARD - Practical
Chess Defence`: dezoito linhas com quatro parágrafos visíveis saem num bloco só. **O bloco do
produtor é a COLUNA de prosa, não o parágrafo.**

**O resultado.** `docs/metrics/texto_paragrafo_referencia.json`:

| quantil | acertos | falsos | perdidos | precisão | recall | blocos |
|---:|---:|---:|---:|---:|---:|---:|
| 0,10 | 226 | 25 | 97 | 0,9004 | 0,6997 | 484 |
| **0,50** (mediana) | 224 | 25 | 99 | 0,8996 | 0,6935 | 409 |

**Dois acertos em 323**, com o mesmo número de falsos. É a diferença inteira entre os dois
candidatos sobre o que a referência sabe julgar. Os 75 blocos a mais do quantil baixo caem quase
todos em linha que a referência não julga, e por isso são cortes que ninguém mediu — nem a favor,
nem contra.

E não é que os dois candidatos façam a mesma coisa: eles discordam sobre **1.952 linhas em 133 das
226 colunas** do acervo (59%). Mexem muito e empatam.

**Decisão: a mediana fica.** É a regra 5 desta spec — régua sem vão medido não entra ligada —, e
ela vale igual para a troca que parecia óbvia. `QUANTIL_DA_MARGEM` existe como constante, com o
número e a data no módulo, e `metricas_por_coluna(..., quantil=)` existe para a próxima medição
poder varrer candidatos sem monkeypatch.

**O que a medição achou no caminho, e que é maior que o item.** Na folha que originou a S-257, o
recuo mede 11 pt contra uma altura de linha de 14 — 0,79 alturas, logo abaixo do corte de 0,8 de
`RECUO_DE_PARAGRAFO`. Ali o que esconde o parágrafo **não é a margem, é o limiar**: com qualquer
dos dois quantis a folha sai com os mesmos 11 blocos. Varrido o limiar sobre a mesma referência:

| `RECUO_DE_PARAGRAFO` | acertos | falsos | perdidos | precisão | recall |
|---:|---:|---:|---:|---:|---:|
| **0,80** (em uso) | 224 | 25 | 99 | 0,8996 | 0,6935 |
| 0,40 | 249 | 26 | 74 | 0,9055 | 0,7709 |

Vinte e cinco cortes certos a mais por um falso a mais, com um platô largo e chato entre 0,20 e
0,45. É vão de verdade, e é **outro item** — ver a S-258: mexer nele muda o texto que o leitor
entrega, e com ele os relatórios que medem página e legenda.

**Critério de aceite** — cumprido:

- existe conjunto de referência de parágrafo, versionado, com o livro e a folha de cada marca ✅;
- a medição publica precisão e recall **do corte** para a mediana e para os candidatos, sobre o
  mesmo conjunto, em `docs/metrics/` ✅;
- o quantil escolhido é o que a medição apontou ✅ — ela apontou que não há o que trocar;
- sem vão medido, `metricas_por_coluna` fica como está e o item declara-se medido-e-recusado ✅;
- a folha do `Dvoretsky` que originou o item está examinada, com o número que ela dá hoje ✅.

**Testes.** `tests/test_text_paragrafos.py`: `test_a_margem_sai_do_quantil_declarado`;
`test_a_coluna_de_recuo_frequente_perde_a_margem_na_mediana`;
`test_a_referencia_de_paragrafo_esta_versionada_e_bate_com_o_relatorio`.

---

## S-258 · O limiar de recuo é 0,8 altura de linha, e a medição diz 0,4 ✅ implementada (2026-08-26)

**Problema.** `paragrafos.RECUO_DE_PARAGRAFO` vale `0.8`: a linha só abre parágrafo se começar
0,8 altura de linha à direita da margem. O número nunca foi medido contra referência — ele veio
com a S-192, quando referência de parágrafo não existia.

Ela existe agora (S-257), e diz que o corte está alto demais:

| `RECUO_DE_PARAGRAFO` | acertos | falsos | perdidos | precisão | recall | F1 |
|---:|---:|---:|---:|---:|---:|---:|
| **0,80** (em uso) | 224 | 25 | 99 | 0,8996 | 0,6935 | 0,7832 |
| 0,50 | 247 | 26 | 76 | 0,9048 | 0,7647 | 0,8289 |
| **0,40** | **249** | 26 | 74 | **0,9055** | **0,7709** | **0,8328** |
| 0,20 | 249 | 26 | 74 | 0,9055 | 0,7709 | 0,8328 |
| 0,15 | 249 | 29 | 74 | 0,8957 | 0,7709 | 0,8286 |

Os dois lados melhoram — 25 cortes certos a mais por um falso a mais —, e o platô entre 0,20 e
0,45 é chato, o que é o sinal de que o valor não está sintonizado num acaso do conjunto. Abaixo de
0,20 a precisão começa a cair.

O `SALTO_DE_PARAGRAFO` foi varrido junto e **não** mostra vão: baixá-lo de 0,6 para 0,3 sobe o
recall para 0,7771 e derruba a precisão para 0,8715. É troca, e não ganho — ele fica.

**Por que é item separado.** Mexer no limiar muda o texto que `ler_pagina` entrega, e com ele:

- `docs/metrics/texto_pagina.json` — o CER de página é medido sobre a montagem;
- `docs/metrics/texto_legenda.json` — o parágrafo atado ao diagrama pode passar a ser outro;
- e o que mais dependa da composição de blocos, que o item tem de levantar antes de trocar.

**Critério de aceite.**

- o valor novo sai da medição da S-257, sobre a mesma referência, e o relatório registra a
  varredura inteira, e não só o vencedor;
- todo relatório que a troca move é remedido no mesmo commit, na disciplina da S-100;
- a referência ganha folhas de livro **sem camada** antes da troca: as 24 de hoje vêm de livros
  que têm camada de texto, porque é dela que sai o sinal do fim de linha — e o leitor roda sobre
  livro que não a tem;
- se a medição ampliada contradisser a de hoje, o número que vale é o dela.

**Testes.** `tests/test_text_paragrafos.py` (ampliado): o caso do recuo curto — 11 pt sobre altura
de 14 — que hoje não abre parágrafo e passaria a abrir.
> **Trocado para 0,4 em 2026-08-26, e a medição ampliada trouxe um achado maior que o item.**
>
> **O instrumento foi versionado primeiro**, e essa era uma dívida: a medição da S-257 saiu de um
> `medir_paragrafo.py` no diretório de trabalho da sessão -- o campo `como_reproduzir` daquele
> relatório diz isso com todas as letras. Um número que só um script perdido reproduz é um número
> que ninguém confere, e o critério de aceite deste item pede a varredura registrada.
> `cvoff-texto-paragrafo` monta a referência e varre os dois cortes.
>
> **A referência ganhou folha de livro sem camada, como o item exige** -- 23 folhas de 16 livros,
> **16 delas lidas pelo glifo**. Ela ficou em arquivo próprio (`texto_paragrafo_ampliada.jsonl`) em
> vez de crescer por cima da de lá: `texto_paragrafo_referencia.jsonl` é a evidência de uma medição
> que **decidiu** -- a S-257 recusou a troca do quantil sobre aquelas 24 folhas --, e sobrescrevê-la
> deixaria aquele relatório citando um conjunto que já não existe.
>
> **E foi por causa dessas folhas que o número saiu.** Separada por motor:
>
> | motor | folhas | precisão | recuo 0,80 | recuo 0,40 |
> |---|---:|---:|---:|---:|
> | camada | 7 | 0,94 | F1 0,7521 | **F1 0,7934** |
> | glifo | 16 | **0,43** | F1 0,5193 | F1 0,5137 |
>
> Onde a referência sabe julgar, ela **confirma** a previsão deste item: quatro cortes certos a
> mais, **sem um falso a mais**, e o platô entre 0,20 e 0,45 continua chato -- o sinal de que o
> valor não está sintonizado num acaso do conjunto. As contagens absolutas diferem das da tabela
> acima porque a referência é outra; a forma e a decisão, não.
>
> **Onde ela não sabe julgar, nenhum candidato se distingue de outro** -- e é esse o achado. Nas
> folhas lidas pelo glifo a precisão é 0,43: `cortar` faz ali mais que o dobro de blocos que a
> referência vê começos, e 0,80 aparece como nominalmente "melhor", que é a assinatura de ruído e
> não de ótimo. O corte não é o problema: **a população de "linha" que a segmentação entrega não é
> a que estas regras descrevem** -- entram cabeçalho, número de página, rótulo de diagrama e
> fragmento, que o modelo de coluna não separou. Está em `varredura_por_motor`, e é item próprio.
>
> **Um filtro teve de entrar na semeadura, e a falta dele quase inverteu a conclusão.** A primeira
> corrida automática deu precisão ~0,47 em *todos* os candidatos. A causa não era o corte: numa
> coluna de **notação** toda linha é curta -- `28. Txe5 Dd7` não alcança margem nenhuma --, então o
> sinal do fim de linha marca começo de parágrafo em quase toda linha. A referência estava medindo
> a própria inadequação dela. Quem separa notação de prosa é `notacao.e_linha_de_notacao`, medida na
> S-249, e ela entrou como `MAX_FRACAO_DE_NOTACAO`.
>
> **Os relatórios que a troca move foram remedidos no mesmo commit**, na disciplina da S-100, e os
> dois melhoraram:
>
> | relatório | régua | antes | depois |
> |---|---|---:|---:|
> | `texto_pagina.json` (S-211) | CER de página, glifo | 0,1397 | **0,1001** |
> | `texto_pagina.json` (S-211) | CER de página, modo bloco | 0,1446 | **0,1331** |
> | `texto_legenda.json` (S-249) | cobertura da legenda | 0,7411 | **0,7679** |
> | `texto_legenda.json` (S-249) | cobertura do estilo | 0,6161 | **0,6429** |
>
> O CER melhorou em **todas as dez folhas**, e a decisão de cada relatório continua a mesma: o modo
> bloco segue não pagando (0,1331 contra 0,1001), e a legenda segue coberta em ~3/4 dos diagramas.
>
> **O modo bloco teve de ser remedido junto, e não copiado.** Ele custa ~50x o tempo, e a tentação
> de carregar o número antigo ao lado do novo é exatamente o defeito que a S-219 nomeia: a decisão
> daquele relatório é a **comparação** entre os dois, e comparar um número fresco com um velho não é
> comparação nenhuma.


---

# Fase 41 — As ferramentas que faltavam na barra

> A Fase 37 entregou os pincéis do **trecho** — negrito, cor, realce — e a S-249 entregou o estilo do
> **parágrafo**. O que nenhuma das duas entregou foi o que se faz com uma folha depois de corrigi-la:
> centralizar o diagrama e a legenda dele, subir o corpo de um título, riscar o que sai, arrumar a
> caixa de um nome que o OCR leu em versalete. São quatro ferramentas, onze comandos, e nenhuma delas
> inventa fronteira nova: as duas primeiras são atributo de parágrafo e de trecho, como o estilo e o
> negrito já eram; a terceira é o quarto booleano de ênfase; a quarta muda texto, pelo caminho que a
> substituição em massa já usava.

## S-259 · Alinhamento é do parágrafo, e a figura dentro dele vai junto ✅ implementada (2026-08-26)

**Problema.** A aba não tem alinhamento nenhum. Tudo sai encostado na margem esquerda — inclusive a
miniatura do diagrama, que `_inserir_miniatura` insere com `image_create(tk.END, ...)` sem etiqueta
alguma. Numa folha de livro de xadrez o diagrama é quase sempre centralizado na coluna, e a legenda
embaixo dele também: exportar a folha corrigida devolvia uma página que não se parece com a página.

O caso é mais estreito do que parece, e é aí que ele fica interessante. A marca `[Diagrama N]` é uma
`Corrida` de tipo `DIAGRAMA`, e `rico._editavel` recusa atributo nela desde a S-235 — com razão
declarada: *"pintar de negrito um `[Diagrama 3]` seria um atributo que morre na primeira gravação"*,
porque `texto_etiquetas.corrida_de` devolve a marca com `PADRAO`. Só que "onde a figura fica na
coluna" **não** é um atributo da marca: é a mesma escolha que alinha o parágrafo em volta dela.

**Solução.** `Atributos.alinhamento`, com `ALINHAMENTOS` fechado em quatro
(`text/rico.py:123`), aplicado por `aplicar_no_paragrafo` (`:808`) — que é `aplicar_estilo`
generalizada, com o mesmo alcance de bloco da S-249. E uma fronteira nova de uma linha:

```python
ATRIBUTOS_DA_MARCA: frozenset[str] = frozenset({"alinhamento"})   # text/rico.py:704
```

A marca **emite e devolve** essa etiqueta e nenhuma outra; os demais nove atributos continuam
recusados. No widget, a etiqueta vai também na **imagem** — o `-justify` do Tk é lido no primeiro
item de cada linha de tela, e o primeiro item da linha da figura é a figura, não a marca embaixo
dela. Uma etiqueta que chegasse só à marca passa num teste de `tag_names` e deixa a imagem na
margem, que é o defeito que este item existe para não ter.

**Duas perdas declaradas, e as duas são de quem desenha.** `JUSTIFICACAO_DO_ALINHAMENTO`
(`ui/texto_panel.py:156`) manda `justificado` para `left`: o `tk.Text` não estica espaço entre
palavras, e justificar de verdade seria um motor de composição dentro de uma aba de correção de OCR.
O atributo continua no documento e sai justificado nos formatos que sabem justificar — `.html` por
`text-align: justify`, `.rtf` por `\qj`. O `.md` não tem sintaxe e conta a perda.

**O alvo de um comando de parágrafo não é `intervalo_alvo`.** Ela cai na *palavra* sob o cursor, e
sobre um caractere que não é de palavra a palavra é vazia — então o comando não fazia nada. Para o
negrito isso é o certo; para o alinhamento é a resposta errada no caso mais comum de todos, que é o
cursor parado no `[` de `[Diagrama 1]`. `intervalo_de_paragrafo` (`text/rico.py:649`) cai no
**caractere** sob o cursor, e quem estende ao bloco é `aplicar_no_paragrafo`. O estilo da S-249 tinha
o mesmo buraco e sai consertado junto.

**Critério de aceite.**

- alinhar uma palavra alinha o parágrafo inteiro, e não o vizinho;
- centralizar um parágrafo que contém um diagrama move **a miniatura e a marca**;
- a marca continua recusando todo atributo que não seja o alinhamento;
- `esquerda` e `""` são estados distintos, e os dois sobrevivem ao arquivo;
- o justificado cai em `left` na tela e sai justificado no `.html` e no `.rtf`.

**Testes.** `tests/test_texto_ferramentas.py::AlinhamentoTests`;
`tests/test_ui_texto_editor.py::FerramentasNoWidgetTests::test_centralizar_pelo_cursor_na_marca_alcanca_a_miniatura`
e `::test_o_cursor_num_caractere_sem_palavra_ainda_alinha_o_paragrafo`.

---

## S-260 · O corpo sobe e desce por degraus, e o degrau nunca é pixel ✅ implementada (2026-08-26)

**Problema.** Não há como aumentar nem diminuir o texto. O estilo de parágrafo da S-249 dá quatro
corpos fixos — título, prosa, notação, legenda —, e é tudo. Um subtítulo que precisa ficar entre o
título e a prosa não tem onde caber, e a legenda de um diagrama de duas linhas não tem como encolher.

A armadilha aqui é a regra 3 da spec. `PAPEL_DO_ESTILO` já diz, em letras grandes, que *"nenhum
tamanho em pixel entra aqui"*: `tipografia` escala pela fonte do sistema desde a S-147, e um `12`
cravado quebra quem aumentou a fonte do Windows. Uma ferramenta de tamanho é justamente o recurso
que convida a cravar um número.

**Solução.** `Atributos.corpo`, um **degrau relativo** inteiro, com faixa fechada de
`CORPO_MINIMO = -3` a `CORPO_MAXIMO = 6`. O degrau vira ponto num lugar só:

```python
def corpo(degrau: int, *, base: int, papel: str = CORPO) -> int:   # ui/tipografia.py:148
    return max(MINIMO_LEGIVEL, escala(base)[papel] + int(degrau))
```

O piso é o `MINIMO_LEGIVEL` que a S-149 já tinha, e é ele que fecha a faixa por baixo — abaixo de
7 pt as hastes de `l`, `i` e `1` colapsam, e distinguir esses três é o trabalho desta janela.

**O degrau soma sobre o que está lá, corrida a corrida** (`text/rico.py:872`). Selecionar um título
(`+2`) junto de duas linhas de prosa (`0`) e apertar "aumentar" sobe os três um degrau, e não achata
os três no mesmo número — a mesma pergunta que `vale_em_todo` responde para o negrito. Corrida que já
está no limite fica onde está e as outras andam; o rodapé diz que o limite chegou, porque um botão
que deixa de fazer efeito em silêncio é o botão que a pessoa aperta mais cinco vezes.

**A origem do degrau não é o papel `CORPO` quando não há estilo**, e isso foi medido: o `tk.Text`
nasce em `TkFixedFont` — Courier New 10 no Windows — enquanto o papel `CORPO` é Segoe UI 9. Derivar
do papel faria "aumentar" trocar a família **e** diminuir o tamanho. `_fonte_do_trecho`
(`ui/texto_panel.py:929`) parte do papel quando há estilo e da fonte do próprio editor quando não há
— a mesma escolha que `_fonte` já fazia para o negrito e o itálico. E parte sempre da **origem**,
nunca do que está desenhado: somar ao tamanho já na tela faria a fonte crescer sozinha a cada
redesenho.

**Critério de aceite.**

- nenhum tamanho em pontos ou pixels aparece fora de `ui/tipografia.py`;
- o degrau soma por corrida e para no limite sem parar o gesto, com aviso no rodapé;
- aumentar e redesenhar não acumula: a fonte da etiqueta é a mesma depois de `desenhar_documento`;
- sem estilo, o degrau mantém a família do editor;
- `.rtf` e `.html` expressam o degrau; `.md` e `.txt` contam a perda.

**Testes.** `tests/test_texto_ferramentas.py::CorpoTests`;
`tests/test_ui_texto_editor.py::FerramentasNoWidgetTests` — `test_o_degrau_nao_se_acumula_a_cada_redesenho`,
`test_o_degrau_sai_da_fonte_do_editor_e_nao_do_papel_corpo`, `test_o_corpo_para_no_limite_e_o_rodape_diz`.

---

## S-261 · O tachado, e por que ele é o quarto e não o quinto ✅ implementada (2026-08-26)

**Problema.** A ênfase tinha três pincéis — negrito, itálico, sublinhado — e nenhum deles diz "isto
sai". Numa aba cuja matéria é OCR corrigido essa é uma marca frequente: um trecho que o motor
inventou, uma linha de cabeçalho que não é do texto, um resto de marca d'água lido como palavra.
Apagar resolve e é irreversível depois do próximo redesenho; riscar não é.

**Solução.** `Atributos.tachado`, e o custo dele é o que o item tem de interessante: **quase nada**.
`BOOLEANOS` é derivado de `fields(Atributos)` desde a S-241, `SEM_ETIQUETA` obriga uma decisão de
desenho para cada booleano novo, `ATRIBUTOS` de `text/exportacao.py` é derivado do mesmo lugar, e o
teste paramétrico da S-256 percorre os campos. O atributo entra, e a suíte cobra sozinha a etiqueta,
a persistência e a declaração por formato. É a S-256 pagando o que prometeu.

No widget ele é `overstrike=True` — **opção de etiqueta, e não de fonte**, e por isso soma com a
etiqueta que dá a fonte ao trecho em vez de disputá-la. Riscar um título em negrito continua sendo um
título em negrito riscado, sem a etiqueta combinada que `NEGRITO_ITALICO` teve de inventar do outro
lado. No `.md` é `~~`, do GitHub Flavored Markdown; no `.html`, `<s>` e não `<del>` — `del` é *texto
removido de uma versão para a outra*, e aqui o trecho continua no documento.

`limpar_formato` passou a ler `ATRIBUTOS_DE_ENFASE` (`ui/texto_panel.py:128`) em vez de uma lista
escrita no corpo do método: o quarto pincel tinha de sair por aquele botão junto dos três, e uma
lista repetida é a que fica para trás. Corpo e alinhamento **não** entram lá, e a constante diz por
quê — cada um tem o seu comando de volta ao normal.

**Critério de aceite.**

- o tachado alterna como os três, e "completa" quando parte do intervalo já está riscado;
- `limpar_formato` o apaga junto dos outros três, e não toca em corpo nem alinhamento;
- o risco não substitui a fonte do trecho.

**Testes.** `tests/test_texto_ferramentas.py::TachadoTests`;
`tests/test_ui_texto_editor.py::FerramentasNoWidgetTests::test_o_tachado_e_risco_e_nao_fonte`.

---

## S-262 · A caixa do trecho, e o que ela não pode tocar ✅ implementada (2026-08-26)

**Problema.** O acervo tem nome próprio lido em versalete, título de capítulo em caixa alta que
deveria ser prosa, e a S-211 já registrou que o resize 32×32 do classificador apaga o que separa `s`
de `S`. Corrigir isso à mão é redigitar a palavra — e redigitar perde o `bloco:` da corrida, que é o
que faz a correção voltar para a fila da S-212 atada ao bloco que ela corrige.

**Solução.** `mudar_caixa` (`text/rico.py:939`), com três modos em `CAIXAS`: alta, baixa e iniciais.
Ela é a única das quatro ferramentas desta fase que **muda o texto**, e por isso vai pelo caminho do
documento: instantâneo antes, redesenho depois — o mesmo de `aplicar_substituicao`, e pela mesma
razão, que o redesenho zera a pilha do Tk.

**Corrida a corrida, e não sobre o texto junto.** Passar o intervalo por `substituir_intervalo` daria
o texto certo com os atributos da primeira corrida em todas — um negrito que engole o parágrafo. E a
marca do diagrama atravessa intacta: `[DIAGRAMA 3]` deixaria de ser a marca que `text/documento.py`
escreve, e o que se perde não é a caixa, é o vínculo entre o texto e a figura.

**As iniciais são o Title Case do Word, e não o de `str.title()`.** Duas regras, e as duas foram
decididas contra o acervo: o apóstrofo **não** abre palavra (`don't` → `Don't`, e não `Don'T`, que é
o que `str.title()` devolve) e o hífen **abre** (`saint-amant` → `Saint-Amant`, porque o jogador se
chama assim e um `Saint-amant` num índice de nomes ninguém revisa depois). O corte não é o de
`palavra_em`, que trata os dois como internos — e `NAO_ABREM_PALAVRA` existe para dizer isso por
escrito, já que reusar a constante da S-241 era o caminho óbvio e errado.

**O carimbo `humano` só vai no que mudou.** Trecho que já estava na caixa pedida não é correção sobre
o que o motor leu — ele não foi corrigido —, e contá-lo inflaria o número que a S-239 mostra no
rodapé ao salvar.

**Critério de aceite.**

- a caixa preserva atributo, faixa e bloco de cada corrida;
- a marca do diagrama e o separador atravessam inteiros;
- `don't` → `Don't` e `saint-amant` → `Saint-Amant`;
- a troca é desfazível **inteira**, e não caractere a caractere;
- a faixa de confiança sobrevive: trocar a caixa não é dizer que o motor acertou.

**Testes.** `tests/test_texto_ferramentas.py::CaixaTests`;
`tests/test_ui_texto_editor.py::FerramentasNoWidgetTests::test_a_troca_de_caixa_e_desfazivel_inteira`.

---

## O que a Fase 41 arrumou de passagem

Três coisas que não são item e ficam registradas porque mudam código que outra pessoa vai ler:

| o que | por quê |
|---|---|
| `app_tkinter._comandos` deixou de repetir quarenta `lambda p: p.negrito()` | o par comando-método passou a sair de `texto_panel.COMANDOS_DA_ABA`, que é onde os métodos estão. Era a segunda declaração do mesmo par, e a janela estava a cinco linhas do limite de tamanho da S-31 |
| `atalhos.SOBREPOSICOES_NO_EDITOR` | `Ctrl+R` está nas duas tabelas de tecla. É aceitável porque a guarda de foco já cedia a sequência a todo widget de texto desde a S-20 — mas isso precisava estar **escrito**, para a próxima sobreposição não entrar em silêncio |
| o espaço engolido pela ênfase do `.md` | `_cauda` devolvia só o espaço final, e `um **negrito**` saía `um**negrito**`. Aparecia em toda corrida que começa com espaço, que é quase toda. `_cercado` devolve as duas pontas |

---

# Fase 42 — O que dois editores prontos ainda tinham a dizer

> Esta fase saiu de uma leitura de código alheio: dois editores de texto pequenos, guardados no
> repositório como referência — um em Tkinter (`Text-Editor-master`) e um em GTK
> (`impress-writer-master`). Nenhum dos dois é melhor que esta aba em nada que importe a um livro de
> xadrez, e é justamente por isso que a comparação foi útil: o que eles têm e ela não tinha é o
> **básico de editor** que o assunto do projeto nunca obrigou a escrever.
>
> Quatro coisas sobreviveram ao filtro. Três são deles quase intactas — área de transferência, zoom
> de leitura, modo de quebra de linha. A quarta é a única do impress-writer que valia a pena, e ela
> chega **virada do avesso**: onde ele corrige a ortografia por consulta à internet, aqui o léxico
> confere e **não** corrige, offline, porque foi isso que a S-209 mediu.

## O que foi lido e o que foi recusado

| do `Text-Editor-master` | decisão |
|---|---|
| Cut / Copy / Paste / Delete / Select All no menu **Edit** | **entra** (S-263). As teclas já funcionavam; o que faltava era comando |
| Align left / center / right / justify | já entrou na Fase 41 (S-259) |
| Bold / Italic / Underline / **Strike** | as três, desde a S-241; o tachado entrou na S-261 |
| Highlight, Change Color | S-242 |
| combobox de **família de fonte** | **fora.** Esta aba desenha uma folha de livro, e a família é de quem a imprimiu -- não de quem a corrige. Um seletor de família convidaria a "consertar" na tela o que a página tem, e o `.cvtxt` guardaria uma escolha que nenhum formato de saída consegue honrar por igual |
| combobox de **tamanho em pontos** | **fora**, e a S-260 diz por quê: tamanho absoluto quebra quem aumentou a fonte do Windows. O que entrou foi o degrau |
| barra com ícones e *tooltips* | **fora**, e já estava decidido: `Comando.icone` é `""` de propósito, porque o repositório não tem um ícone e nome de ícone que ninguém desenha é promessa vazia (S-324) |
| "Clear All" (esvaziar o documento) | **fora.** `Ler folha` refaz a folha inteira e é reversível; um botão que apaga tudo ao lado dele é a S-76 outra vez |

| do `impress-writer-master` | decisão |
|---|---|
| corretor ortográfico que **troca** a palavra | **fora**, e é o único item desta lista que a spec já recusava por escrito. Ver "O que esta spec deliberadamente não faz" |
| a mesma ideia, **sem trocar nada** | **entra** (S-266). É a S-209 tal como ela foi medida |
| dicionário e sinônimos por consulta à web | **fora.** O produto é offline -- é o que o nome dele diz --, e nenhuma outra parte do programa baixa coisa alguma |
| radio de **modo de quebra de linha** | **entra** (S-265), com dois modos em vez de três: "caractere" quebra palavra ao meio, e num texto de OCR isso esconde o erro que se está procurando |
| caixas "Editable" e "Cursor Visible" | **fora.** São estados de demonstração de widget, e não recursos de um editor |
| zoom de leitura | não é dele, é de todo editor -- e faltava (S-264) |

---

## S-263 · Recortar, copiar, colar e selecionar tudo — o que era tecla e não era comando ✅ implementada (2026-08-26)

**Problema.** O menu **Texto** tem vinte e nove linhas e nenhuma delas é "Copiar". As teclas
funcionam — o `tk.Text` liga `<<Cut>>`, `<<Copy>>` e `<<Paste>>` a `Ctrl+X/C/V` de fábrica —, e é
esse justamente o problema que a S-161 registra numa frase: *"o que não era botão não existia"*. Quem
não sabe que a tecla existe não tem onde descobrir, e um menu de edição sem "Copiar" diz, sem
querer, que a aba não copia.

E uma delas **não** funcionava. `Ctrl+A` no `tk.Text` leva o cursor ao **início da linha** — herança
de Emacs que nenhum programa de Windows faz —, e "selecionar tudo" não tinha tecla nem comando. Quem
apertava `Ctrl+A` para selecionar a folha via o cursor pular e concluía que a aba não fazia aquilo.
Com as ferramentas da Fase 41 isso passou a custar caro: "selecionar tudo e centralizar" e
"selecionar tudo e pôr em maiúsculas" são os dois gestos mais naturais que existem sobre uma folha
recém-lida.

**Solução.** Quatro comandos no catálogo, quatro itens no menu, e **uma** tecla nova:
`selecionar_tudo` em `Ctrl+A`. As outras três não entram em `TECLAS_DO_EDITOR`, e isso é decisão: o
Tk já as liga, e declará-las de novo seria a segunda declaração da mesma tecla — o defeito que
aquela tabela existe para impedir.

Recortar, copiar e colar disparam o **evento virtual** do Tk (`_area_de_transferencia`) em vez de
uma implementação própria. O Tk já resolve a seleção, a área de transferência do sistema e o
desfazer; um segundo caminho divergiria do `Ctrl+C` no primeiro caso de canto — e o caso de canto de
um editor com imagem embutida no meio do texto é justamente o que ninguém testa.

**O que o texto colado traz, e o que ele não traz.** Ele herda os atributos dos dois lados do
cursor, que é a regra do próprio Tk e já era a regra da digitação desde a S-238: colar dentro de um
bloco herda `bloco:3`, e a correção fica atada ao bloco que ela corrige — que é o que a fila da
S-212 precisa receber. O que **não** vem junto é formatação de outro programa: a área de
transferência do Tk carrega texto, e não corridas.

**Critério de aceite.**

- os quatro têm comando, item de menu e método no painel;
- `Ctrl+A` seleciona a folha inteira **sem** a quebra final que o Tk mantém e o documento não tem;
- selecionar tudo e aplicar uma ferramenta age sobre a folha inteira;
- recortar e colar continuam sendo os eventos virtuais do Tk.

**Testes.** `tests/test_ui_texto_editor.py::VistaESelecaoTests` — `test_selecionar_tudo_pega_a_folha_sem_a_quebra_final`,
`test_selecionar_tudo_e_depois_uma_ferramenta_pega_a_folha`,
`test_copiar_e_colar_passam_pelo_evento_virtual_do_tk`.

---

## S-264 · O zoom da vista, que não é o corpo do trecho ✅ implementada (2026-08-26)

**Problema.** A S-260 deu corpo por degraus ao **trecho**, e ela resolve hierarquia: um título maior
que a prosa. Não resolve o outro caso, que é mais frequente e mais banal — **enxergar**. Quem confere
uma folha de scan ruim quer a letra maior por dez minutos e depois quer ela de volta, e nada disso
tem a ver com o documento. Fazer isso com a ferramenta de corpo seria gravar, no `.cvtxt` e em toda
exportação, uma decisão que era da vista de quem estava lendo.

**Solução.** `aproximar_texto` / `afastar_texto` / `zoom_do_texto_normal`, em degraus de
`ZOOM_MINIMO` a `ZOOM_MAXIMO`, sobre a fonte do **widget**. Nada entra no documento, nada é
exportado, nada é gravado — e é o teste `test_o_zoom_muda_a_fonte_do_editor_e_nao_o_documento` que
mantém isso assim.

Os rótulos longos dizem "(não muda o documento)", e é a única confusão possível entre dois pares de
comandos que fazem a letra crescer na tela. O grupo também separa: zoom é `VISUALIZACAO`, corpo é
`EDICAO`.

**Duas armadilhas, e as duas viram teste.**

- **Sem redesenhar.** Redesenhar zera a pilha de desfazer do Tk (o cabeçalho de `ui/texto_panel.py`
  explica por quê), e perder o desfazer da digitação por ter aproximado a letra seria uma troca
  ruim. `_aplicar_zoom` troca a fonte do editor e **reconfigura** as etiquetas de fonte que já
  existem — e é para isso que `_fontes_desenhadas` passou de `set` a `dict`, guardando os atributos
  que geraram cada uma. Decompor o nome da etiqueta de volta era a alternativa, e é a forma de
  acoplamento que se descobre quebrada meses depois.
- **A conta parte sempre da fonte original.** Reler a fonte do editor a cada zoom devolveria a **já
  ampliada**, e dois cliques dariam `+1` e depois `+2` sobre o `+1`. É o mesmo defeito que
  `_fonte_do_trecho` evita do lado do documento, e a defesa é a mesma: guardar a origem
  (`_fonte_original_do_editor`) em vez de medir o que está na tela.

**Critério de aceite.**

- o zoom muda a fonte do editor e **não** muda o documento;
- dois cliques dão exatamente dois degraus, e "normal" volta à fonte de origem;
- o zoom não zera o desfazer da digitação;
- para no limite com aviso no rodapé, como o corpo.

**Testes.** `tests/test_ui_texto_editor.py::VistaESelecaoTests` — `test_o_zoom_muda_a_fonte_do_editor_e_nao_o_documento`,
`test_o_zoom_parte_sempre_da_fonte_original`, `test_o_zoom_nao_zera_o_desfazer`,
`test_o_zoom_para_no_limite_e_o_rodape_diz`.

---

## S-265 · A quebra de linha é escolha, e a notação é o caso ✅ implementada (2026-08-26)

**Problema.** O editor nasceu em `wrap=tk.WORD` e nunca teve outra opção. Para prosa é o certo. Para
**notação** não: uma linha de lances quebrada no meio deixa de ser uma linha de lances, e comparar a
tela com a folha impressa — que é o trabalho de quem corrige — passa a exigir contar de novo onde a
linha começava.

**Solução.** Um interruptor, com dois modos e não três: quebra na largura da janela, ou linha
inteira com rolagem horizontal. O terceiro modo do `impress-writer` — quebrar no **caractere** —
fica de fora porque ele parte palavra ao meio, e num texto de OCR isso esconde exatamente o erro que
se está procurando.

A barra de rolagem horizontal existe desde a montagem e só é **empacotada** quando a quebra é
desligada. Criá-la sob demanda daria um widget novo a cada troca de modo, e o `pack` de um widget
novo entra depois dos que já estavam — a barra apareceria embaixo do editor na primeira vez e no
lugar certo na segunda. Uma barra que não rola também não fica: com `wrap=word` nenhuma linha passa
da largura, e ela ficaria ali inteira e imóvel.

**Critério de aceite.**

- o interruptor troca o `wrap` do editor e a rolagem horizontal aparece com ele;
- a quebra **não** entra no documento;
- o rodapé diz o que mudou, como `modo_bloco` faz.

**Testes.** `tests/test_ui_texto_editor.py::VistaESelecaoTests::test_a_quebra_troca_o_wrap_e_a_rolagem_horizontal`
e `::test_a_quebra_nao_entra_no_documento`.

---

## S-266 · O léxico marca o que ele não conhece — e não corrige nada ✅ implementada (2026-08-26)

**Problema.** O acervo tem um léxico de **363.799 palavras** empacotado (`text/dicionario.py`), e a
aba de texto nunca perguntou nada a ele. O léxico é usado no caminho da *leitura*, para desempatar
entre os candidatos que o próprio classificador já pôs no topo da lista; depois que a folha está na
tela, ele fica calado. Quem corrige uma página procura `smdy` com o olho.

`smdy` é o exemplo real: `study` sai `smdy` porque a barra do `t` encosta no `u` e o par vira `m`
(registrado desde a S-186). É invisível numa leitura rápida e é exatamente o que um dicionário acha
em milissegundos.

**Solução, e o que ela deliberadamente não faz.** `marcar_fora_do_lexico` marca; e só. A frase da
S-209 é a especificação inteira do comando:

> *"Palavra fora do dicionário é sinalizada, nunca aproximada da mais parecida."*

Ela não é preferência: dos 18 lances tão maltratados que escapam do fatiador e caem no léxico,
**nenhum** está no dicionário — com correção automática seriam 18 lances reescritos como palavra. É
por isso que o botão que existe é "Conferir palavras", e não "Corrigir ortografia"; e é por isso que
o rótulo longo do comando diz as duas coisas, porque a segunda é a que dá confiança para usar a
primeira sobre uma folha de OCR.

**A marca não é do documento, e é a única desta aba que não é.** Faixa, atributo, bloco e
procedência descrevem o texto e voltam de `texto_etiquetas.corrida_de`; esta é **derivada** do texto
e do léxico. Gravá-la daria um `.cvtxt` com as marcas de um léxico que já mudou — pior que nenhuma
marca. Como `corrida_de` ignora etiqueta que não conhece, ela atravessa a gravação sem deixar
rastro, e `test_a_marca_do_lexico_nao_entra_no_documento` é o item inteiro numa asserção.

**O canal de desenho é a borda, e ele estava livre.** A cor da letra é a faixa de confiança
(S-211), o fundo é o realce do autor (S-242), a fonte é o estilo mais o corpo, e
negrito/itálico/sublinhado/tachado são os quatro pincéis de ênfase. Uma quinta marca em qualquer um
deles seria a mesma tinta com dois significados na mesma linha — o defeito que a S-242 gastou um
item inteiro para não ter.

**Três coisas que a conferência não marca**, e cada uma tem um caso atrás:

- **notação.** `Nf3`, `1.d4`, `15`, `0-0`: `e_palavra` já os recusa, pela guarda 1 do módulo. Sem
  isso a folha inteira acenderia, e uma marca que acende em tudo não distingue coisa nenhuma;
- **a marca do diagrama.** `[Diagrama 3]` é referência que o **programa** escreveu; marcá-la seria a
  aba avisando sobre si mesma, em toda folha que tenha diagrama. Quem sabe o que é marca é o
  documento, então o veto entra por parâmetro (`ignorar`) e não por regra dentro do dicionário — a
  mesma fronteira que mantém `text/` sem saber o que é um widget;
- **caixa errada.** `poSition` passa como conhecida, porque o léxico compara em `casefold`. E é o
  certo: quem separa `s` de `S` é a altura do box na S-211, **com medição** (CER 0,1434 → 0,1114), e
  uma segunda régua discordando dela na tela seria pior que nenhuma.

**A conta vai para o rodapé** porque ela é o resultado: "3 de 412" e "80 de 412" pedem coisas
diferentes de quem está conferindo a folha. O denominador sai do mesmo laço do numerador
(`palavras_de`), porque duas contagens com réguas diferentes dariam uma fração que não fecha.

**Custo medido:** 0,16 s para carregar os três arquivos comprimidos, uma vez por sessão, guardado
depois. É o que faz este comando caber na thread da janela em vez de pedir uma segunda — ao
contrário da leitura da folha, que custa de 1 s a 40 s.

**Critério de aceite.**

- nenhuma palavra é trocada, em nenhum caminho;
- notação, marca de diagrama e caixa errada não são marcadas;
- a marca não sobrevive à gravação, e o documento é idêntico antes e depois de conferir;
- conferir duas vezes dá o mesmo resultado;
- a conta aparece no rodapé com o denominador.

**Testes.** `tests/test_texto_lexico.py::ConferenciaSemCorrecaoTests`;
`tests/test_ui_texto_editor.py::LexicoNaAbaTests`.

---

# Fase 51 — As quatro pontas que as Fases 41 e 42 deixaram

> Nenhum comando novo entra aqui. Os quatro itens fecham buracos que as duas fases anteriores
> deixaram visíveis — dois deles **anteriores** a elas, e descobertos só porque a barra cresceu o
> bastante para a falta aparecer: uma declaração que não fazia nada, um estado que não sobrevivia ao
> fechamento, dois controles que não diziam o que valia sob o cursor, e uma marcação que se apagava
> justamente no gesto que ela existe para servir.

## S-267 · `Ctrl+F` e `Ctrl+H`, e a declaração que não fazia nada ✅ implementada (2026-08-26)

**Problema.** `texto_panel.ACOES_PROPRIAS` declara, desde a S-244, que a aba atende `achar` e
`substituir` "enquanto tem o foco". Só que `ATALHOS` **não tinha essas teclas** — nem `Ctrl+F` nem
`Ctrl+H` existiam na janela. A declaração descrevia um roteamento de tecla para uma tecla que
ninguém apertava: `atalhos.destino` só é consultado a partir de uma sequência, e não havia
sequência. As duas linhas existiam e não faziam nada, que é a S-161 outra vez — *"o que não era
botão não existia"* — com o agravante de que aqui **parecia** existir.

E é a falta mais visível de todas: com 49 comandos na aba, `Ctrl+F` não abrir a busca é o primeiro
gesto que qualquer pessoa tenta.

**Solução, e a medição que decidiu as duas teclas.** As duas entram em `ATALHOS`, com uma
assimetria que **foi medida em 2026-08-26** e não é gosto:

| tecla | classe `Text` do Tk faz | decisão |
|---|---|---|
| `Ctrl+F` | **nada** nesta versão | só `ATALHOS`. O `bind_all` basta |
| `Ctrl+H` | **backspace** — apaga um caractere | `ATALHOS` **e** `TECLAS_DO_EDITOR` |

O `Ctrl+H` é herança de terminal, e as bindtags do Tk são `widget, classe, toplevel, all`, nessa
ordem: um `bind_all` roda **depois** da classe. Ligada só na janela, a tecla apagaria um caractere e
**então** abriria a substituição, toda vez. O `bind` no widget roda primeiro e devolve `"break"`, que
mata os dois de baixo — verificado nos dois sentidos: com o `bind`, o texto fica intacto e
`substituir` é chamado; sem ele, `abcdef` vira `abdef`.

**Elas não têm `no_editor`, e é o oposto do `Ctrl+S`.** Ali a mesma tecla tem dois destinos conforme
o foco; aqui ela tem um só, porque a janela tem **uma** busca e ela é a do texto da folha. Fora do
editor, `Ctrl+F` abre a mesma janela — que é melhor que não fazer nada, e é o que um programa com
uma busca só deve fazer.

**`SOBREPOSICOES_NO_EDITOR` passou a declarar o motivo**, e não só a ação, porque agora há dois
motivos diferentes para a mesma tabela: `CEDIDA_PELA_GUARDA` (a tecla é da janela e a guarda de foco
já a cedia dentro do editor — `Ctrl+R`) e `GANHA_DO_TK` (a mesma ação nos dois lados, e o `bind` do
widget existe para vencer a classe `Text` — `Ctrl+H`). Os dois têm teste próprio, e o sinal que os
separa é objetivo: a ação estar ou não em `ACOES_PROPRIAS`.

**Um teste que passava sem exercitar nada, achado no caminho.** `test_as_tres_teclas_devolvem_break`
gerava o evento numa janela `withdraw`n — e ali `event_generate` de teclado não entrega a ninguém,
porque não há foco de verdade. O texto ficava igual porque **nada disparava**, e o teste passava em
verde sobre nove teclas sem exercitar uma. Ele foi trocado pelo que é afirmável sem janela na tela:
que cada sequência tem `bind` **no próprio widget** e que ele devolve `"break"`.

**Critério de aceite.**

- toda ação de `ACOES_PROPRIAS` tem tecla na janela — e é um teste, não uma revisão;
- `Ctrl+H` dentro do editor abre a substituição **sem** apagar caractere;
- toda sobreposição entre as duas tabelas declara qual dos dois motivos ela é.

**Testes.** `tests/test_ui_atalhos_destino.py` — `test_toda_acao_propria_da_aba_tem_tecla`,
`test_a_tecla_que_ganha_do_tk_faz_a_mesma_acao_nos_dois_lados`;
`tests/test_ui_texto_editor.py::test_toda_tecla_do_editor_esta_ligada_no_widget`.

---

## S-291 · O zoom e a quebra sobrevivem ao fechamento ✅ implementada (2026-08-26)

**Problema.** A S-264 acrescentou o **terceiro** zoom do programa, e foi o único que a janela não
lembra. `pdf_zoom` e `board_zoom` estão em `AppState` desde a versão 1 do formato, e o próprio
arquivo diz por quê, em `show_diagram_boxes`: *"essa escolha tem de sobreviver ao fechamento da
janela — senão ela vira uma tarefa a refazer toda vez"*. Quem confere um scan ruim com a letra dois
degraus maior a refazia a cada abertura. O mesmo vale para a quebra de linha da S-265: quem trabalha
notação a desliga uma vez, não uma vez por sessão.

**Solução.** `AppState.texto_zoom` e `AppState.texto_quebra`, gravados e lidos como os vizinhos, e
`TextoPanel.restaurar_vista(zoom=, quebra=)` — um contrato só, no molde de `pdf_panel.set_zoom`, para
a janela continuar amarrando nome a método em vez de conhecer o widget por dentro.

**Duas decisões pequenas.**

- **A restauração é silenciosa.** `_aplicar_zoom(avisar=False)`: o rodapé é para quem acabou de
  apertar um botão, e uma janela que abre dizendo "zoom +2" fala de algo que ninguém acabou de fazer.
- **`ui/state.py` valida só o tipo.** Os limites do zoom são da aba que o desenha, e repeti-los no
  arquivo de estado os declararia num segundo lugar — a mesma regra que aquele módulo já segue para
  a pele, a geometria e o conjunto de peças. Quem grampeia um `texto_zoom: 900` de arquivo estragado
  é `_aplicar_zoom`, e agora ele grampeia (antes só `_mudar_zoom` o fazia).

**Critério de aceite.**

- o zoom e a quebra voltam como estavam na sessão anterior;
- a restauração não escreve no rodapé;
- valor absurdo no arquivo cai no limite da aba, e não derruba a abertura.

**Testes.** `tests/test_ui_texto_editor.py::VistaGuardadaTests`.

---

## S-292 · A barra diz o alinhamento e o degrau que valem sob o cursor ✅ implementada (2026-08-26)

**Problema.** A S-241 fixou a regra para os pincéis de ênfase, e a escreveu assim: *"um botão que
diz 'negrito' onde o texto não é negrito é pior que um botão sem estado nenhum"*. Os quatro
interruptores a cumprem. Os dois controles de valor que a Fase 41 acrescentou, não: a lista "Alinhar"
mostra quatro itens iguais num parágrafo já centralizado, e `A+`/`A-` não dizem em que degrau o
trecho está. Quem quer voltar ao normal não sabe de onde está voltando.

**Solução.** `rico.valor_em_todo` — o irmão de `vale_em_todo` para atributo que não é sim-ou-não —,
e ela existe pela mesma razão que aquele: quem responde à barra tem de ser a **mesma** função que
decide, porque duas respostas para a mesma pergunta divergem e a que fica errada é a da tela.

**`None` e `""` são respostas diferentes, e a distinção é o item.** `""` é "todo o intervalo está sem
alinhamento"; `None` é "há mais de um aqui". Sem separá-las, a lista marcaria um item que vale em
metade da seleção. O mesmo vale para o corpo, e por isso o mostrador tem três estados — `0`, `+2`,
e a meia-risca de "não há um só degrau": mostrar `0` onde há dois seria o mostrador afirmando o que
ele não sabe.

**A lista de alinhamento virou `add_radiobutton`; a de caixa não.** Alinhamento é **estado** do
parágrafo e tem de aparecer marcado; caixa não é estado — um trecho não "está em maiúsculas", ele
foi posto em maiúsculas e virou texto.

**O alinhamento é lido do parágrafo, e não da palavra sob o cursor.** Perguntar sobre
`intervalo_alvo` diria "sem alinhamento" num parágrafo centralizado sempre que o cursor caísse fora
de uma palavra — que é o mesmo buraco que a S-259 fechou do lado de quem aplica, agora do lado de
quem mostra.

**Critério de aceite.**

- a lista marca o alinhamento do parágrafo, mesmo com o cursor fora de uma palavra;
- o mostrador segue o cursor e distingue "zero" de "mais de um";
- nenhum dos dois é fonte: quem decide continua sendo a função pura.

**Testes.** `tests/test_texto_ferramentas.py::ValorEmTodoTests`;
`tests/test_ui_texto_editor.py::EstadoNaBarraTests`.

---

## S-293 · A conferência do léxico se refaz depois do redesenho ✅ implementada (2026-08-26)

**Problema.** `marcar_fora_do_lexico` marcava **uma vez**. Toda ferramenta que muda texto redesenha,
e o redesenho apaga a marcação inteira — então corrigir a primeira palavra marcada apagava as
outras, e a pessoa tinha de reconferir a cada correção. É exatamente o gesto que a conferência existe
para servir: achar as suspeitas e corrigi-las uma a uma.

**Solução.** O comando **liga** a conferência em vez de marcar uma vez, e `desenhar_documento` a
refaz no fim. Quem a desliga é `limpar_marcas_do_lexico`, que passou a ser um interruptor de saída e
não só uma limpeza.

**Três detalhes que a implementação obriga.**

- **Depois do `finally`.** A conferência lê o documento pelo `dump` do widget, e o widget só está
  pronto quando o laço de desenho terminou.
- **Sem reescrever o rodapé.** A conta já foi dita quando se ligou; repeti-la a cada redesenho seria
  ruído — e pior, esconderia o que a ferramenta que acabou de rodar tinha a dizer (a substituição
  conta as trocas, o corpo avisa o limite).
- **Continua fora do documento.** Refazer-se sozinha não pode ter virado gravação: a marca segue
  derivada, e o teste compara o documento antes e depois de um redesenho com a conferência ligada.

**Critério de aceite.**

- corrigir uma palavra marcada **não** apaga as marcas das outras;
- limpar desliga, e o redesenho seguinte não as traz de volta;
- a reconferência não escreve no rodapé;
- o documento continua idêntico com a conferência ligada.

**Testes.** `tests/test_ui_texto_editor.py::ConferenciaQueSeRefazTests`.

---

# O que esta spec deliberadamente não faz

| não faz | por quê |
|---|---|
| tabela editável no texto | `BlocoDeTabela` existe (`text/pagina.py:433`) e o editor a mostra como texto. Editar célula a célula é um segundo editor dentro deste, e o acervo tem poucas tabelas — a S-198 mediu quantas |
| montar o livro inteiro numa aba | a aba é da folha aberta, por decisão de custo já registrada em `sincronizar_com_a_pagina`. Nada aqui impede a folha seguinte; o que não entra é a montagem |
| corretor ortográfico **que troca a palavra** | o acervo é multilíngue por página e cheio de notação. O que faz sentido é o léxico de xadrez da S-209, que sinaliza e nunca troca -- e é o que a **S-266** entrega: ele marca, e a correção continua sendo de quem lê |
| autocompletar notação enquanto se digita | troca silenciosa sobre texto de OCR — a S-209 outra vez, e a S-248 registra a recusa |
| expressão regular na substituição | maior razão entre poder e estrago da lista; o que ela resolveria aqui, o casamento de figurina da S-245 já resolve |
| exportar PGN a partir do texto | é a S-208, que valida a notação contra as regras. O editor entrega o texto; quem o transforma em partida é aquele item |
