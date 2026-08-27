# Especificação do reconhecimento de texto — Fases 25 a 31 (S-178 a S-217)

Base: [ROADMAP_TEXTO.md](ROADMAP_TEXTO.md), que traz o levantamento dos dois projetos, a decisão
de portar e o sequenciamento. As fases de modelo, detecção e interface não são tocadas por esta
spec.

> **Onde mora a spec de cada item (S-NN).**
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143, S-175 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-327 | [SPEC_REVISAO.md](SPEC_REVISAO.md) |

Cada item tem **Problema**, **Solução**, **Critério de aceite**, **Testes** e **Sonda**. A
convenção é a de sempre: nome de módulo é sugestão, o que importa é a fronteira de
responsabilidade.

A **Sonda** é a novidade desta spec, e existe por um motivo prático: um plano de 38 itens que
atravessa sete fases envelhece, e ninguém lembra o que já entrou. A sonda é o que
`cvoff-texto-status` verifica no disco para dizer se o item existe — e `tests/test_text_status.py`
falha quando o documento e a sonda discordam. O manifesto vive em
`src/chess_diagram_ocr/text_status.py`.

**Quatro regras valem para toda esta spec.**

1. **Nenhum número herdado do PyBoxEditor conta como medição deste projeto.** Onde um item cita
   um, ele está marcado como *(medido lá)* e o próprio item traz a remedição aqui. O
   `ROADMAP_TEXTO` explica por que essa regra existe.
2. **O palpite do modelo nunca entra na base como rótulo.** Vale para a Fase 29 e para a 31, e é
   a cicatriz das duas pontas — 127 amostras mal rotuladas lá, a verdade de referência
   contaminada aqui.
3. **Nada de reconhecimento vive numa interface.** Os módulos portados que tocavam Tk no projeto
   de origem viram função pura aqui, e o widget só desenha o que elas decidem.
4. **O que a página não diz sai `None`.** É a regra da S-16, e vale igual para o que o OCR não
   leu com confiança: campo vazio é melhor que campo inventado, porque o inventado parece dado
   lido.

---

# Fase 25 — A fronteira, e a prova de que o modelo atravessa

> Descobrir com o menor investimento possível se o classificador de lá serve aqui. Nada de
> página inteira, nada de coluna, nada de retreino. A fase termina numa decisão.

## S-178 · O subpacote `text/`, e a procedência do que foi portado ✅ implementada (2026-08-22)

**Problema.** O PyBoxEditor é repositório privado, sem `pyproject`, com módulos que se importam
como `core.*` na raiz. Copiar arquivo por arquivo sem registrar de onde veio produz, em três
meses, um `text/preprocess.py` daqui e um `core/preprocess.py` de lá que divergiram — e ninguém
consegue dizer qual conserto está em qual.

**Solução.** Um subpacote `src/chess_diagram_ocr/text/`, e dentro dele `text/PROCEDENCIA.md`:
uma linha por módulo portado, com o arquivo de origem, o commit de origem, a data e **o que foi
mudado no porte**. A última coluna é a que importa — um porte literal e um porte adaptado
envelhecem de formas diferentes.

O `__init__.py` do subpacote não importa `torch` nem `cv2` no topo. Quem importa
`chess_diagram_ocr.text` num ambiente sem o extra recebe o módulo, não um `ImportError`. É a
mesma regra que `cli/_ocr.py` já segue com o import tardio do `ocr_caption`.

**Critério de aceite.**

- `text/PROCEDENCIA.md` existe e tem uma linha por arquivo `.py` do subpacote, exceto
  `__init__.py`;
- `import chess_diagram_ocr.text` funciona num ambiente sem o extra `texto` instalado;
- nenhum módulo de `text/` importa de `ui/`.

**Testes.** `test_a_procedencia_cobre_todo_modulo_portado`;
`test_importar_o_subpacote_nao_exige_o_extra`; `test_nenhum_modulo_de_texto_importa_a_interface`.

**Sonda.** `arquivo:src/chess_diagram_ocr/text/PROCEDENCIA.md`, `modulo:chess_diagram_ocr.text`.

---

## S-179 · O modelo de 292 classes entra pinado, ou não entra ✅ implementada (2026-08-22)

**Problema.** O reconhecedor de lá é um par: o `.pth` e o `model_meta.json`. O metadado guarda
`label_map`, `idx_to_char`, `num_classes`, `temperatura`, `modelo_sha256` e `classes_sha256`.
Descasar os dois é silencioso e devastador: o modelo devolve o índice 42, o mapa errado o traduz
para outro caractere, e a leitura sai plausível e falsa.

O projeto de origem já tem esse guarda (a F7.3 de lá). Este também tem o seu, na S-40: retomar
uma exportação com o modelo trocado é recusado. **O porte traz o guarda junto, não só o modelo.**

**Solução.** `text/modelo.py`, com uma função de carga que é o único caminho para o
classificador existir:

```python
def carregar_classificador(
    meta: Path, pesos: Path | None = None, *, device: str | None = None
) -> ClassificadorDeGlifo:
    """Recusa por hash antes de carregar. Não devolve None: ou carrega, ou levanta."""
```

`pesos=None` procura o `.pt` ao lado do metadado. O `modelo_sha256` é conferido **antes** do
`torch.load`, e o `classes_sha256` contra o `idx_to_char` reconstruído — porque renomear uma
pasta de classe não pode desalinhar um modelo treinado, e foi assim que a migração de nomes
funcionou lá sem retreino.

`temperatura` é aplicada na saída, sempre. Ela é 2,5209 no metadado de origem, e um
classificador que a ignora reporta confiança que não corresponde a nada — que é o achado nº 2 da
avaliação de agosto deste projeto, na outra ponta.

**Critério de aceite.**

- `.pt` cujo sha256 não bate com o metadado levanta com mensagem em pt-BR que nomeia os dois
  hashes;
- metadado sem `temperatura` levanta em vez de assumir 1,0;
- `num_classes` do metadado e a última camada do modelo carregado batem;
- carregar duas vezes o mesmo par devolve o mesmo objeto (cache por caminho), e trocar o arquivo
  no disco invalida o cache.

**Testes.** `test_o_hash_do_modelo_e_conferido_antes_do_torch_load`;
`test_metadado_sem_temperatura_e_recusado`;
`test_renomear_classe_nao_desalinha_o_modelo_treinado`.

**Sonda.** `simbolo:chess_diagram_ocr.text.modelo:carregar_classificador`,
`arquivo:models/char_meta.json`.

---

## S-180 · `char_to_folder` e `folder_to_char` portados sem uma linha de diferença ✅ implementada (2026-08-22)

**Problema.** As 292 classes não são um alfabeto: são **nomes de pasta do Windows**, e o mapa
entre caractere e pasta é onde a base inteira se ancora. O projeto de origem chegou à forma
atual por três acidentes registrados:

- `sym_f7` guardava 127 imagens da **casa de xadrez `f7`**, não do hexadecimal `÷`. Corrigir o
  rótulo fez o modelo *já treinado* acertar 127 de 127 sem retreinar;
- `folder_to_char` devolvia `"?"` em silêncio quando não entendia a pasta, e foi isso que deixou
  o defeito acima passar. Hoje tem `strict=True`, que levanta;
- a lista de não-alfanuméricos legíveis (`EXTRAS_LEGIVEIS = "+-"`) é **fechada**, e admitir um
  caractere novo custa três checagens: legal como nome de pasta no Windows; inerte no `glob` (o
  padrão é montado com o caminho inteiro, então `*?[]` esvaziariam a classe); e nunca `_`, que é
  o que impede um nome legível de começar por `hex_` e ser lido de volta como hexadecimal.

Alargar essa lista aqui — por parecer arbitrária — faria as duas bases divergirem, e a de 700
mil deixaria de ser legível por este projeto.

**Solução.** Porte literal de `char_to_folder`, `folder_to_char` e `EXTRAS_LEGIVEIS`, com o
comentário de origem preservado, e um teste de ida-e-volta sobre **as 292 classes do metadado**,
não sobre exemplos escolhidos.

O hexadecimal é de largura fixa (`f"{ord(c):04x}"` por caractere): com largura variável a volta
é ambígua, porque `ab`+`c` e `a`+`bc` geram a mesma cadeia.

**Critério de aceite.**

- para os 292 valores de `idx_to_char`, `folder_to_char(char_to_folder(c)) == c`;
- `folder_to_char` com pasta desconhecida levanta `NomeDePastaInvalido`, e nunca devolve `"?"`;
- `EXTRAS_LEGIVEIS` é exatamente `"+-"`, e o teste que trava isso diz **por quê** no docstring;
- nenhum nome de pasta produzido contém `\ / : * ? " < > |`, ponto ou espaço final.

**Testes.** `test_a_volta_fecha_para_as_292_classes_do_metadado`;
`test_pasta_desconhecida_levanta_em_vez_de_devolver_interrogacao`;
`test_a_lista_de_extras_legiveis_e_fechada`; `test_todo_nome_e_legal_no_windows`.

**Sonda.** `simbolo:chess_diagram_ocr.text.classes:char_to_folder`,
`simbolo:chess_diagram_ocr.text.classes:folder_to_char`.

---

## S-181 · `GlyphRecognizer` implementa `TextRecognizer`, e a S-43 não muda ✅ implementada (2026-08-22)

**Problema.** A tentação, ao trazer um OCR novo, é abrir um caminho paralelo: uma função que lê
a página, um resultado com formato próprio, e uma segunda porta de entrada para o texto. Foi
exatamente o que a S-43 recusou fazer com o RapidOCR, e o motivo está escrito lá: o OCR não é uma
via alternativa, é **uma segunda fonte de `TextLine`**, no mesmo formato e nas mesmas
coordenadas. Assim todo o aparato da S-16 continua valendo sem uma linha de mudança.

**Solução.** `text/recognizer.py`, com uma classe que satisfaz o protocolo que já existe:

```python
class GlyphRecognizer:
    """Segmenta o recorte, classifica cada glifo, agrupa em linha, devolve TextBox."""

    def read(self, image: np.ndarray) -> list[TextBox]: ...
```

E `build_recognizer` da S-42 passa a conhecer o nome `glifo` ao lado de `rapidocr`, `easyocr` e
`tesseract`. **Nenhuma linha de `ocr_caption.py` muda**, e é isso que o critério de aceite mede.

Na Fase 25 a agregação em linha é a mais simples que funciona: ordenar por `y` da base, agrupar
por sobreposição vertical, ordenar por `x` dentro do grupo. A leitura por linha de verdade é a
S-188, e ela não é pré-requisito para esta.

A confiança do `TextBox` é a **mínima** dos glifos da linha, não a média. Uma legenda com um
caractere adivinhado no meio não é uma legenda 90% confiável — o `MIN_CONFIDENCE = 0.30` da S-42
existe para cortar legenda adivinhada, e a média o burlaria.

**Critério de aceite.**

- `isinstance(GlyphRecognizer(...), TextRecognizer)` é verdadeiro (o protocolo é
  `runtime_checkable`);
- `git diff` de `ocr_caption.py` e de `pdf_text.py` é vazio nesta entrega;
- `--ocr glifo` funciona em `cvoff-field` e `cvoff-export` sem alteração em `cli/_ocr.py` além do
  nome novo em `KNOWN_ENGINES`;
- com o extra ausente, `build_recognizer("glifo")` devolve `None` e loga em pt-BR o que instalar
  — que é caminho normal, não erro.

**Testes.** `test_o_reconhecedor_de_glifo_satisfaz_o_protocolo`;
`test_a_confianca_da_linha_e_a_minima_e_nao_a_media`;
`test_sem_o_extra_o_construtor_devolve_none_e_avisa`.

**Sonda.** `simbolo:chess_diagram_ocr.text.recognizer:GlyphRecognizer`.

---

## S-182 · Onde moram os pesos, e o que o programa faz quando eles faltam ✅ implementada (2026-08-23)

> **Este item mudou de forma na implementação, e o motivo fica registrado (2026-08-22).**
>
> A versão escrita antes de implementar pedia um **extra `texto`** no `pyproject`, pela regra que
> vale para os cinco que já existem. Ao implementar, o extra saiu **vazio**: o classificador
> traz `torch`, `opencv-python` e `pillow`, e os três já são dependências obrigatórias. Um
> `uv sync --extra texto` que não instala nada é pior que não ter o extra — ele promete um
> portão que não existe, e `test_todo_extra_do_pyproject_aparece_no_README` obrigaria a
> documentá-lo no README como se fosse um.
>
> **O que de fato porteia o recurso é o arquivo de pesos**, e ele já não vinha no repositório.
> Então o item passou a ser sobre isso: onde os pesos moram, como são apontados, e o que o
> programa diz quando faltam. A sonda mudou junto.

**Problema.** O classificador de 292 classes são 2,6 MB de binário, e `models/**/*.pt` está no
`.gitignore` desde a S-29. O metadado que descreve as classes tem 9 KB e **é** versionado. Quem
clona recebe, portanto, um metadado sem o modelo que ele descreve — e é exatamente essa
assimetria que torna o `modelo_sha256` da S-179 necessário.

Falta a outra metade: **como o usuário aponta o arquivo, e o que ele lê quando não apontou.** Sem
isso o motor `glifo` falha com um traceback, ou pior, fica silenciosamente desligado.

**Solução.** `OcrSettings.glyph_model`, no mesmo desenho de `LocalReaderSettings.path` (S-66):
sem padrão embutido, porque um caminho presumido faz o recurso parecer quebrado em toda máquina
que não o tem, em vez de simplesmente ausente. Vazio deixa a S-179 procurar o `.pt` ao lado de
`models/char_meta.json`, que é o caminho de quem já pôs o arquivo lá.

Três lugares dizem a mesma coisa, em pt-BR:

- `OcrSettings.glyph_disabled_reason()` — para a interface desabilitar o botão e explicar;
- `ModeloInvalido`, levantado por `carregar_classificador` — nomeia o caminho tentado, o
  `data/settings.json` e a variável de ambiente;
- o ramo `glifo` de `ocr.build_recognizer` — repassa a mensagem **sem embrulhá-la**. O `glifo` é
  o único motor de casa, e "não foi possível inicializar o motor" por cima esconderia o que
  interessa.

E `CVOFF_OCR_GLYPH_MODEL` vence o arquivo, como as outras: apontar os pesos já é a intenção de
usar, então ela liga o motor junto — a mesma leitura que `CVOFF_REMOTE_FEN_URL` e
`CVOFF_LOCAL_READER_PATH` fazem.

**Critério de aceite.**

- ✅ os testes que dependem dos pesos **constroem os seus** (uma rede de 3 classes num `tmp_path`)
  em vez de pular — pular seria o mesmo que não existir, já que os 2,6 MB nunca estarão num clone
  limpo;
- ✅ sem os pesos, `build_recognizer` devolve `None` e loga o que falta e onde apontar;
- ✅ a variável de ambiente vence o arquivo e liga o motor junto;
- ✅ a barra de status diz qual dispositivo o classificador de caracteres está usando, ao lado do
  que já diz para o de peças;
- ✅ `packaging/cvoff.spec` decide explicitamente se o modelo de caracteres entra no bundle, e o
  `--selftest` cobre a decisão.

> **A sonda ganhou uma terceira entrada em 2026-08-23, e o motivo é um defeito que só aparece
> quando o item começa a dar certo.** `arquivo:models/char_classifier.pt` era **falso em todo
> clone** — os pesos não vêm no repositório —, então o item ficava `parcial` por acidente, sem
> que a sonda medisse nada do que ele ainda deve. No dia em que a S-204 treinou o modelo, o
> arquivo apareceu e o disco passou a dizer `implementada` para um item com dois critérios
> abertos. A sonda nova aponta para um deles, e por isso responde `não` até o item fechar de
> verdade, com ou sem `.pt` no disco.

> **Os dois últimos fecharam em 2026-08-23, na Etapa 1 do [`PLANO_OCR_TEXTO.md`](PLANO_OCR_TEXTO.md).**
>
> **A barra de status.** A zona nova mostra os **dois** modelos -- `peças cuda:0 · texto cpu` --,
> e não só o de caracteres, porque o critério dizia "ao lado do que já diz para o de peças" e a
> janela **não dizia nada sobre nenhum dos dois**: `OcrService.device_label` existia desde a S-30
> e só o `examples/streamlit_demo.py` o exibia. O nome da placa fica na dica, que é onde ele cabe
> sem custar largura à mensagem.
>
> **Três estados, e o terceiro é o que faltava.** "sem pesos" (o `.pt` não está no disco, e a
> dica diz onde apontar) é diferente de "desligado" (os pesos estão lá e o motor escolhido é
> outro, ou o OCR de legenda está desligado). Dizer os dois com a mesma palavra mandaria metade
> das pessoas procurar um arquivo que já está na pasta.
>
> **O empacotamento.** O `packaging/cvoff.spec` já deixava `models/` de fora, e agora nomeia o
> classificador de caracteres na lista, com o motivo próprio dele: um retreino grava um `.pt`
> novo, e um modelo embutido no `.exe` seria o único que o usuário não consegue trocar. O
> `--selftest` diz em qual dos dois estados a instalação está e **não muda o código de saída** --
> ausente não é falha.
>
> **Onde o código foi parar, e por quê.** A cola mora em `ui/dispositivos.py`, e não na janela: o
> rodapé recebe descrições prontas (é o que o faz afirmável sem abrir janela) e `app_tkinter.py`
> tem catraca de tamanho desde a S-31. Ela subiu de 1.776 para 1.788 linhas, com o motivo
> registrado em `tests/test_packaging.py`.

**Testes.** `test_sem_os_pesos_o_construtor_devolve_none_e_diz_o_que_falta`;
`test_o_motivo_da_ausencia_esta_em_pt_br_nas_preferencias`;
`test_pesos_ausentes_dizem_onde_apontar`.

**Sonda.** `simbolo:chess_diagram_ocr.settings:ENV_OCR_GLYPH_MODEL`,
`arquivo:models/char_classifier.pt`,
`simbolo:chess_diagram_ocr.ui.rodape:dispositivo_do_classificador_de_caracteres`.

---

## S-183 · O placar da faixa de legenda: camada de texto, RapidOCR e glifo na mesma tabela ◐ parcial (2026-08-22)

**Problema.** Todo número desta spec atribuído ao PyBoxEditor foi medido no acervo *dele*. O
acervo daqui tem 41 livros e uma composição diferente, e a pergunta que decide a Fase 26 nunca
foi feita: **na faixa de legenda deste acervo, o glifo lê melhor que o RapidOCR?**

Sem essa tabela, as seis fases seguintes se justificam por herança — que é o defeito que a Fase
19 deste projeto veio consertar.

**Solução.** `cvoff-texto-placar`, que roda as três fontes sobre o **mesmo** conjunto de faixas e
grava `docs/metrics/texto_faixa_<data>.json`. As faixas vêm de onde a S-43 já as recorta, com o
interior do diagrama apagado, a 300 DPI.

A régua tem duas colunas, e as duas são necessárias:

| régua | o que mede | por que sozinha não basta |
|---|---|---|
| acerto de caractere | distância de edição normalizada contra a legenda transcrita à mão | um motor que lê 90% dos caracteres e erra o dígito do exercício é pior do que parece |
| campo resolvido | lado a jogar, número, jogadores e evento saem certos? | é o que o programa usa; um motor pode perder em caractere e ganhar aqui |

**O conjunto de referência é transcrito à mão**, e isso é trabalho humano. Mas achar *onde estão
as faixas* não é: `--semear` varre o acervo com o `detect_diagrams` da S-12, escreve uma linha por
diagrama com o `bbox_pt` pronto e pré-preenche `texto` com o que a camada de texto diz. O humano
passa a **conferir** em vez de digitar.

Isso cria um risco óbvio, e três coisas o contêm — as três verificáveis, e todas descritas no topo
de `cli/texto_placar.py`:

1. `"conferido": false` é **recusado pela medição**. A linha semeada não entra na tabela até
   alguém comparar o texto com a página impressa.
2. `texto_semente` fica gravado ao lado. Se ninguém editou, a tabela conta a célula em
   `circulares_camada` — com o número à vista, em vez de uma média que esconde de onde veio.
3. Os livros de scan puro **não têm o que semear**: `texto` sai vazio, e são justamente eles que
   decidem a fase.

> **Executado em 2026-08-22.** `cvoff-texto-placar --semear --por-livro 3` produziu **123 faixas
> em 41 livros** — 83 com semente da camada, 40 em branco (13 livros sem camada de texto nas
> páginas varridas). Nenhuma conferida ainda, e o comando recusa medir enquanto for assim.
>
> **A semeadura desenterrou um defeito de produção da S-16**, e ele não é da semeadura: em
> **19 das 123 faixas, de 7 livros**, o `caption` que `contexts_for_page` devolve contém as filas
> do tabuleiro impresso em fonte de diagrama. `_is_diagram_font_row` só conhece a codificação da
> fonte Merida (`0Z0Z0mkZ`); estes livros usam a do exportador do Lichess (`t+v+t+l+`). **O
> `Polgar` está entre os sete** — que é o livro para o qual o filtro foi escrito. Fica registrado
> aqui e vira item próprio; não foi consertado de passagem porque mexer nesse filtro muda a
> legenda de todo o acervo e precisa da medição dele.
>
> **Corrigido pela S-217 em 2026-08-23, e a medição desmentiu três coisas escritas acima.**
>
> **A causa não é uma, são duas.** Das 19 faixas, **12** trazem só fila de tabuleiro, **3** trazem
> só rótulo de eixo, e **4** trazem as duas. O rótulo de eixo é defeito independente e nenhum
> crivo de codificação o alcançaria: o `Polgar` põe cada dígito de fila no **seu próprio bloco**,
> e o corte por bloco da S-16 pede seis num bloco que tem um.
>
> **E a codificação do Lichess não explica nem as 16 de fonte.** Quinze delas são o `+`/`*` do
> `ChessMerida` e do `Chess-Merida`; a décima sexta é o `Polgar`, em `SkakNew-Diagram` — a Merida
> que o filtro **já conhecia**. `0l0o0ORL` tem três casas vazias e o limiar pedia quatro. Ou seja:
> o filtro também falhava na codificação para a qual foi escrito, e não só nas de fora.
>
> **A lista de sete livros estava trocada em um.** O `Gunderam` não tem fonte de diagrama nenhuma:
> o tabuleiro dele é imagem, e o que suja a legenda é lixo de OCR da camada. Quem ocupa o lugar
> dele é o `Neumann`. Das 19 faixas resta **1**, e é justamente do `Neumann` — mesma natureza que
> o `Gunderam`, e por isso fora do alcance da S-217. Ver a seção dela.
>
> **Consequência para este item: o conjunto de referência no disco ainda é o de 22/08, com os 19
> seeds sujos dentro.** Refazê-lo não custa nada *agora* — as 123 faixas estão todas com
> `conferido: false`, então não há conferência humana a proteger, que é o único motivo pelo qual
> `--semear` recusa sobrescrever. Semeado de novo com o filtro da S-217, o comando devolve **os
> mesmos 123 `bbox_pt`, na mesma ordem**, e dois números deste bloco mudam: **81 com semente da
> camada e 42 em branco**, no lugar de 83 e 40. As duas faixas que trocam de coluna são aquelas
> cuja "legenda" era tabuleiro do começo ao fim, e para as quais vazio é a resposta certa; os
> 13 livros sem camada continuam 13. **Refazer antes de alguém começar a conferir é o que mantém
> a promessa do item** — conferir em vez de digitar. Depois que a conferência começar, o custo de
> refazer deixa de ser zero.

**Critério de aceite.**

- ✅ o comando roda num clone sem os PDFs e diz o que falta, em vez de falhar;
- ✅ a faixa não conferida fica de fora, e a tabela conta as células circulares;
- ✅ cada livro tem linha própria — é nos sem camada de texto que a decisão se toma;
- ⬜ **a tabela em si**, com as três fontes e o `n` de cada célula. Depende de duas coisas que
  não estão nesta máquina: as 123 faixas conferidas, e os pesos de 292 classes;
- ⬜ o documento registra a decisão **e a data**: segue para a Fase 26, ou para aqui.

É por isso que este item está `◐`. O instrumento está pronto e travado por teste; o que falta é
o dado.

**Testes.** `test_faixa_nao_conferida_fica_fora_da_tabela`;
`test_a_faixa_semeada_e_nunca_editada_e_contada_como_circular`;
`test_semear_recusa_sobrescrever_conferencia_humana`;
`test_o_n_de_cada_celula_esta_declarado`; `test_o_livro_tem_linha_propria`.

> **O que trava este item é trabalho humano, e em 2026-08-24 ele ficou barato (Etapa 7 do
> [`PLANO_OCR_TEXTO.md`](PLANO_OCR_TEXTO.md)).** As 123 faixas continuam com `conferido: false`, e
> a medição as recusa -- que é o desenho certo, e não uma pendência de código. O que mudou é o
> custo de transcrevê-las: `cvoff-texto-placar --exportar <pasta>` grava um PNG por faixa, **a
> mesma imagem que os motores leem** (a banda dilatada em `radius_pt`, com o interior do diagrama
> apagado). Transcrever deixou de exigir abrir 27 PDFs nas páginas certas 123 vezes.
>
> **Transcrever de outra imagem produziria uma referência que não corresponde ao que se mede**, e
> é por isso que o export monta exatamente a banda da `CaptionReader.lines_around`.
>
> A regra que sustenta tudo continua: **a referência vem da página, e nunca de um motor.** Se ela
> vier de um, a tabela mede o motor contra ele mesmo -- e as outras três medições desta fase
> (S-186, S-188, S-198) tiveram de usar a camada editorada justamente por isso.

**Sonda.** `simbolo:chess_diagram_ocr.cli.texto_placar:main`,
`metrica:texto_faixa`.

---

## S-217 · O tabuleiro que é texto, nas duas codificações que o acervo tem ✅ implementada (2026-08-23)

**Problema.** É o defeito que a semeadura da S-183 desenterrou, e ele é de produção, não da
semeadura: em **19 das 123 faixas de referência, de 7 livros**, o `caption` que
`contexts_for_page` devolve traz as filas do tabuleiro no lugar da legenda.

`_is_diagram_font_row` decidia pelo **texto**: oito caracteres, quatro deles ao menos `0`, `Z` ou
`z` — as casas vazias da Merida como o `Polgar` a codifica. Medido, isso erra por **duas causas
independentes**, e as duas precisam ser nomeadas porque nenhuma explica a outra:

| causa | faixas | livros |
|---|---:|---:|
| a fila do tabuleiro, que o crivo de texto não pega | 16 | 6 |
| o rótulo de eixo, que a contagem por bloco não alcança | 7 | 3 |
| **união** (4 faixas trazem as duas) | **19** | **7** |

**Causa 1 — o texto não distingue tabuleiro de prosa, e a fonte distingue.** O acervo tem duas
codificações, e a segunda é a de quem exporta o diagrama do Lichess:

| livros | fonte | casa vazia | como a fila chega |
|---|---|---|---|
| `Polgar` | `SkakNew-Diagram` | `0` `Z` | `0Z0Z0mkZ` — inteira |
| 4 livros `_hq` | `ChessMerida` | `+` | `t+v+t+l+` — inteira |
| `Dvoretsky` | `Chess-Merida` | `+` `*` | `*`, `+`, `P`, `k` — **um caractere por linha** |

A terceira linha é a que fecha o argumento: **não há crivo de texto que separe um `P` de tabuleiro
de um `P` de prosa.** E o `Polgar`, para quem o filtro foi escrito, escapava pelo próprio crivo
dele — `0l0o0ORL` tem três casas vazias, e o limiar pedia quatro.

**Solução.** O crivo forte passa a ser o **nome da fonte** (`pdf_text.is_diagram_font`), e o
texto vira a via de recurso, para linha do OCR da S-43 e para fonte sem nome útil. Duas decisões
sustentam isso, e as duas foram medidas antes de escritas:

1. **A figurina é excluída à mão, e não por acidente.** No `Polgar` a família é `SkakNew-Diagram`
   para o tabuleiro e `SkakNew-Figurine` para o lance dentro da prosa; no `Dvoretsky` é
   `SemFigNormal`. As de figurina desenham **1.892 linhas que também têm prosa** — as listas de
   lances —, e descartá-las apagaria o texto que a S-208 vai ler.
2. **A linha só cai se _todas_ as fontes dela forem de diagrama.** Medido, **nenhuma linha do
   acervo mistura** fonte de diagrama com outra (0 de 229.510), então exigir todas não custa nada
   hoje; existe para que um livro ainda não medido perca o glifo e não a legenda.

Sobre as 964 fontes distintas do acervo o nome separa sem sobra: **3 casam**, **2 são excluídas**
por figurina, **959 não casam**. Nenhuma fonte de prosa casa por engano.

**Causa 2 — a borda do diagrama não respeita o bloco.** O `Polgar` põe cada dígito de fila no
**seu próprio bloco**: `8`, `7`, `6` … são oito blocos de uma linha, e `_MIN_AXIS_LABELS >= 6`
nunca dispara num bloco que tem um. As letras `a b c d e f g h`, que o mesmo livro põe num bloco
só, sempre caíram — e é por isso que o defeito passou despercebido.

Contar a **página** em vez do bloco conserta o `Polgar` e quebra o `1937 Kemeri`, cuja tabela de
cruzamento tem dezenas de `1` soltos que são **resultados**: na amostra do acervo isso descartaria
4.904 linhas a mais, e as do `Kemeri` seriam perda de dado. O que separa os dois é o que a borda
de um tabuleiro é de fato — rótulos **alinhados** numa faixa e **distintos**, cada fila uma vez.
A coluna de resultados é alinhada, mas é `1`, `1`, `0`, `1`. Com as duas exigências o `Kemeri` sai
inteiro da conta. A regra nova **soma-se** à de bloco em vez de substituí-la: nada que caía hoje
deixa de cair.

**Medido em 2026-08-23** (`docs/metrics/texto_fonte_diagrama.json`), sobre as mesmas 123 faixas:

| | faixas poluídas | por fonte | por rótulo de eixo |
|---|---:|---:|---:|
| antes | 19 (7 livros) | 16 | 7 |
| depois | **1** (1 livro) | **0** | 1 |

E `cvoff-texto-placar --semear --por-livro 3` rodado de novo devolve **os mesmos 123 `bbox_pt`, na
mesma ordem**: 105 faixas com o texto intocado, 16 com o texto corrigido (`158\nLichess` no lugar
de vinte e quatro linhas de tabuleiro) e 2 esvaziadas — as duas em que a "legenda" era tabuleiro
do começo ao fim, e para as quais vazio é a resposta certa.

**O que sobra, e por que não é deste item.** A faixa restante é o `Neumann` de 1870: um scan cujo
`GlyphLessFont` é camada de OCR, numa página que **é** uma tabela dos nomes das casas. Não há
fonte de diagrama ali e não há tabuleiro desenhado — é o problema da S-17, e resolvê-lo aqui seria
escrever um filtro que adivinha.

**E é por isso que as duas contagens de "7 livros" não são a mesma lista.** A da S-183 foi feita a
olho e traz o `Gunderam`; esta é derivada da fonte de cada linha e traz o `Neumann` no lugar dele.
O `Gunderam` — como o `Euwe` e o `Secrets of Chess`, que uma varredura por densidade de caractere
também acusaria — tem o tabuleiro impresso **como imagem**, e o que suja a legenda é lixo de OCR
da camada: `j£`, `'•dkji"-`, `P #`. Nenhum critério de fonte os alcança, porque fonte de diagrama
não há. Coincidência das duas listas darem 19 faixas: o `Gunderam` entrava com uma e o `Neumann`
entra com uma.

**Critério de aceite.**

- ✅ as três fontes de diagrama do acervo caem, nas duas codificações;
- ✅ as duas de figurina **não** caem, e as 1.892 linhas de lance seguem inteiras;
- ✅ nenhuma legenda legítima é descartada — na varredura de **1.860 páginas**, das 9.203 linhas
  retiradas **7.072 são fonte de diagrama e 2.131 são rótulo de eixo**, e **nenhuma é prosa**;
  nenhuma linha nova aparece;
- ✅ o `numero` do contexto deixa de sair errado onde o rótulo de fila era lido como número de
  exercício: 4 faixas saíam com `8`, e agora saem com `None`;
- ✅ o crivo de texto continua valendo onde não há fonte, que é o caminho do OCR da S-43.

**O falso positivo que este item quase criou, e o teste que o guarda.** No `Dvoretsky`, `B`
sozinho é o **marcador de pretas jogam** — exatamente o dado que a S-16 existe para achar — e é
também o bispo do tabuleiro. Nas páginas 172 e 262 os dois estão na mesma página, e só a fonte os
separa: o `Chess-Merida` cai, o `TimesNewRomanPSMT` fica. Um crivo por caractere teria apagado os
dois em silêncio.

**Testes.** `test_nome_de_fonte_de_diagrama`; `test_nome_que_nao_e_de_diagrama`;
`test_fila_de_tabuleiro_cai_pela_fonte`; `test_legenda_na_fonte_de_prosa_nao_cai`;
`test_linha_que_mistura_fonte_de_diagrama_com_prosa_fica`; `test_sem_fonte_vale_o_crivo_de_texto`;
`test_lichess_nao_ocupa_a_legenda`; `test_marcador_de_lado_sobrevive_ao_bispo_na_mesma_pagina`;
`test_digito_de_fila_em_bloco_proprio_nao_vira_legenda`;
`test_coluna_de_resultados_de_torneio_nao_e_borda_de_tabuleiro`.

**Sonda.** `simbolo:chess_diagram_ocr.pdf_text:is_diagram_font`,
`metrica:texto_fonte_diagrama`.

---

# Fase 26 — Do pixel à linha

> É aqui que está o trabalho de verdade. Medido lá, o classificador sozinho dá 99,83% e o
> pipeline inteiro dá 94,2 de F1 sobre página real: **a distância é de segmentação.**

## S-184 · A binarização que decide pelo resultado, não pelo histograma ✅ implementada (2026-08-22)

**Problema.** Limiar fixo funciona em página limpa e falha em scan com iluminação irregular — o
caso normal em livro digitalizado, onde a borda costuma ficar mais escura que o miolo. Este
projeto já binariza em `preprocess.py`, mas para **casa de tabuleiro**: o recorte é pequeno,
quadrado e de alto contraste. Página inteira é outro problema.

A armadilha registrada lá vale ouro: a primeira versão testava **bimodalidade do histograma** e
errava justamente no caso que interessa. Numa página com sombra de encadernação, o Otsu separa
"metade escura" de "metade clara" — duas classes perfeitamente bimodais — e devolve 47% de tinta,
o que não segmenta nada. Medido nesse cenário: limiar fixo 61% de tinta, Otsu 48%, adaptativo 3%.

**Solução.** `text/binarizacao.py`, com os quatro métodos (`auto`, `otsu`, `adaptive`, `fixed`) e
o critério de escolha do `auto` avaliando o **resultado**: fração de tinta entre 0,05% e 35%.
Texto corrido fica em torno de 3–15%; acima de 35% não é texto, é mancha.

A saída deixa a tinta em **branco** (255) e o fundo em preto, que é o formato que
`cv2.findContours` espera. Isto é convenção, e trocá-la depois quebra tudo o que vem em cima —
por isso está no critério de aceite e não só no docstring.

**Critério de aceite.**

- `auto` escolhe adaptativo na página com sombra sintética e Otsu na página limpa, e o teste usa
  fixture gerada, não imagem de livro (que não vive no repositório);
- `fracao_de_tinta` de uma página em branco é 0,0 e de uma toda preta é 1,0;
- a polaridade é travada por teste: tinta branca, fundo preto.

**Testes.** `test_a_pagina_com_sombra_nao_vai_para_o_otsu`;
`test_a_polaridade_e_tinta_branca_e_fundo_preto`; `test_o_auto_devolve_o_que_o_metodo_escolhido_diz`;
`test_a_janela_do_adaptativo_e_impar`.

**Sonda.** `simbolo:chess_diagram_ocr.text.binarizacao:binarize`.

---

## S-185 · O box de caractere, e a régua que separa respingo de ponto final ✅ implementada (2026-08-22)

**Problema.** Depois de binarizar, `findContours` devolve tudo: caracteres, respingos da régua
decorativa do cabeçalho, moldura de tabela, o tabuleiro inteiro. Sem uma régua, o que sai não é
texto.

A cicatriz registrada lá é específica e cara: **a primeira versão cortava por altura**, e o livro
saía sem pontuação nenhuma — `5.♔xf2` virava `5♔d2`, `G.Levenfish` virava `G Levenfish`. A régua
certa é **área normalizada pela escala do caractere**, e a medição mostra por quê:

    respingo da régua decorativa   0,0021 – 0,0031
    ponto final                    0,0129 – 0,0514
    hífen e travessão              0,0073 – 0,0882
    letra minúscula                0,1570 – 0,3315

O limiar cai no vão entre a primeira faixa e a segunda, com folga dos dois lados. *(medido lá)*

**Solução.** `text/boxes.py`, com `escala_de_texto` (a altura típica do caractere na página,
pesada por tinta e não pela mediana crua — a mediana desaba em página com trama, ver S-196) e
`caixas_de_caractere`, que aplica a régua de área.

O diagrama é excluído **antes**, com margem: `detection/hybrid.py` já devolve o retângulo do
tabuleiro, e os rótulos das casas (`a`–`h` embaixo, `8`–`1` ao lado) moram **fora** dele. Sem
margem eles entram no texto como linhas de um caractere — medido lá, oito linhas contendo só
"8", "7", "6"…

> **A implementação achou uma peça que faltava, e a medição a obrigou (2026-08-22).** Com a régua
> de área no lugar da de altura, o **pingo do `i` passa a sair como caixa própria** -- ele tem o
> tamanho de um ponto final, que é justamente o que a régua de área existe para preservar. Sem
> devolvê-lo ao `i`, `Defensive` sai `Defens1.ve`.
>
> Medido na página 21 do `AAGAARD`, seis linhas, com o modelo de diagnóstico de 155 classes:
>
>     segmentação provisória da Fase 25        CER 0,21
>     S-184/S-185/S-187 sem `unir_pingos`      CER 0,35   <- pior que a provisória
>     com `unir_pingos`, régua = escala        CER 0,46   <- e o erro era meu, ver abaixo
>     com `unir_pingos`, régua = mediana local CER 0,14
>
> **Não é argumento para voltar à altura**: a régua de altura acertava aqui por *descartar* o
> pingo, e o preço dela era descartar junto o ponto final de verdade. A régua certa é área, e o
> que faltava era `unir_pingos`.
>
> **O erro do meio vale registrar porque é o tipo que passa despercebido.** A primeira versão de
> `unir_pingos` mediu "o que é caixa curta" contra a **escala da página** (30 px, perto da altura
> de maiúscula). A haste de um `i` minúsculo tem 18 px: com `0,65 x 30 = 19,5` ela própria conta
> como curta, não sobra base com que unir, e o merge não dispara. A régua tem de ser a **mediana
> local** das caixas presentes. `test_a_regua_e_a_mediana_local_e_nao_a_escala_da_pagina` trava.
>
> **E um achado que não é deste item:** a mesma medição com a faixa dilatada em 2 pt -- que é o
> que `ocr_caption` faz com `radius_pt` -- sobe de 0,14 para 0,22. Os fragmentos de descendente da
> linha de cima entram como caixas próprias. `quebrar_em_linhas` os separa em linha à parte
> corretamente; quem os descarta é o chamador, e isso é da S-198.

**Critério de aceite.**

- ✅ a régua é de área, e existe um teste que falha se alguém a trocar por altura;
- ✅ o limiar de área está no vão entre respingo e pontuação, travado contra a tabela medida;
- ✅ os rótulos das casas não aparecem como texto quando o diagrama é excluído com margem;
- ✅ a escala sobrevive ao painel de meio-tom, e **o ponto em que ela degrada está medido**;
- ✅ o pingo do `i` volta para o `i`, e o ponto final não é unido à letra anterior;
- ✅ a exclusão do diagrama usa o bbox que a S-12 já carrega, e não um detector novo.

### O que entrou em 2026-08-25: o pingo que o itálico deslocava

**A régua de sobreposição é horizontal, e o itálico é uma inclinação: faltava o eixo.** O pingo do
`i` em itálico pousa à *direita* da haste, cai na regra que separa ponto final de pingo — *"o ponto
final vem ao lado e não sobre a letra"* — e fica solto. No texto isso saía assim:

    técnica  ->  técnl'ca        Fischer  ->  Fl'scher        rápida  ->  rápl'da

**E não havia conserto depois da segmentação.** Sondado na página 77 do `Minhas 60 partidas
memoráveis`: na haste o classificador responde `/` com 0,915 e `l` com 0,069; no pingo, `.` com
0,997. **O `i` não está entre os candidatos de caixa nenhuma** — ele só existe na imagem das duas
fundidas, e nenhum léxico alcança uma letra que o modelo nunca propôs. Foi assim que o item chegou
aqui: pela porta do dicionário, que o recusou pelo motivo certo.

`unir_pingos` passa a aceitar a binária e a projetar o x da caixa curta para onde ele estaria se o
glifo fosse reto (`inclinação × vão`) antes de medir. Duas guardas, e cada uma tem um caso atrás:
só a caixa **acima** da base é projetada, e só quando a base é uma **haste** (`HASTE_ESTREITA`) —
o que pousa sobre `a` é acento, e a base de um ponto final costuma ser letra larga.

**O que protege a pontuação é a forma da conta, e não um limiar novo**: o deslocamento é
proporcional ao vão, e o ponto final está na altura da letra — vão ~0, deslocamento ~0.

Medido em 40 páginas de 11 livros, com o dicionário ligado dos dois lados para isolar o efeito:

    CER ........................ 0,1181 -> 0,1173   (7 páginas melhoram, nenhuma piora)
    trocas ..................... 9, todas certas
    apóstrofo interno .......... 46 -> 35
    ponto final no texto ....... 1.140 -> 1.140     <- a guarda, medida na saída
    vírgula no texto ........... 263 -> 263

A grandeza precisou nascer: `pendor_do_box` devolve deslocamento **em larguras de box** — a régua
calibrada da S-236, com corte em 0,05 —, e não inclinação. `inclinacao_do_box` converte
(`2 · pendor · largura / altura`) e vive ao lado dela, porque trocar o que a primeira devolve
recalibraria a S-236 em silêncio.

**Duas coisas que a próxima pessoa vai querer, e as duas são medidas.**

A margem é de um degrau de pixel, e o degrau existe: com coordenada de caixa inteira a
sobreposição só assume múltiplos de `1/largura`, e num pingo de 4 px isso é 0,25 de cada vez. As
quatro caixas do padrão medidas aqui saem em **0,500 cravado** — e as oito que outra sessão contou
em 15 folhas, também. Faltam 0,2 px, a projeção entrega 0,6, e não há degrau de sobra. **Quem
mexer no 0,55 ou no DPI de leitura mexe nisto.**

E `HASTE_ESTREITA` **não é só segurança: é o seletor da população.** Medido lá, separando quem
virou união de quem não virou: das que viraram, 8 de 8 têm haste por baixo; das que não viraram, 1
de 11 — e estar acima da base *não* separa, porque 10 das 11 também estão. Afrouxar a guarda para
"pegar mais casos" traria os 11, que precisam de ~7 px que inclinação nenhuma dá.

O número completo está em `docs/metrics/texto_pingo_italico.json`.

**Testes.** `test_a_regua_e_area_e_nao_altura`; `test_a_mediana_ponderada_sobrevive_a_trama`;
`test_a_ponderada_degrada_quando_a_trama_pesa_tanto_quanto_o_texto`; `test_a_margem_tira_o_rotulo_da_casa`;
`test_o_bloco_grande_fica_fora_da_conta`; `test_o_limiar_de_area_esta_no_vao_entre_respingo_e_pontuacao`;
`test_com_binaria_o_pingo_italico_volta_para_a_haste`; `test_o_ponto_final_nao_e_arrastado_junto`;
`test_a_inclinacao_nao_depende_da_espessura_do_traco_e_o_pendor_depende`.

**Sonda.** `simbolo:chess_diagram_ocr.text.boxes:caixas_de_caractere`,
`simbolo:chess_diagram_ocr.text.boxes:escala_de_texto`.

---

## S-186 · O colado na horizontal, e o árbitro que confirma o corte ✅ implementada (2026-08-24)

**Problema.** Dois caracteres que `findContours` devolve num contorno só. Medido lá: 231
caracteres colados na horizontal em 10 páginas rotuladas.

E aqui há um achado que precisa ser dito antes da implementação, porque ele muda a prioridade:
**as classes de ligadura já absorvem parte disso.** O modelo tem `ligature_e4`, `ligature_xf6`,
`ligature_fi` — pares que o separador nem precisa cortar. Medido lá, com as classes de par
ligadas, a vantagem do árbitro do corte caiu de +0,3 para +0,1 de F1, e os cortes bons de 23 para
13. O separador passou a ser candidato legítimo a **desligar**.

**Solução.** Portar o separador com o árbitro, e **medir aqui antes de ligá-lo por padrão**. A
regra que sustenta o desenho está registrada lá e vale repetir: separar glifo colado sem
classificador que confirme custa 2,3 pontos de F1 — a geometria propõe o corte, o classificador
confirma pela confiança média dos dois pedaços contra a do inteiro.

O modo é `auto` / `sempre` / `nunca`, e o padrão sai da medição desta entrega, não de herança.

**Critério de aceite.**

- ✅ a tabela do modo (`auto`, `sempre`, `nunca`), com CER e contagem de cortes. **A referência não
  é a da S-183** — as 123 faixas ainda não foram transcritas —, e sim a camada editorada da
  S-198, que é independente do que se mede. Quando a humana existir, a tabela pode ser refeita;
- ✅ o padrão escolhido tem a tabela ao lado dele, aqui e em `text/colados.py`;
- ✅ um corte só acontece se o árbitro confirmar — `test_sem_arbitro_nenhum_corte_acontece`.

**Testes.** `test_sem_arbitro_nenhum_corte_acontece`;
`test_o_modo_nunca_deixa_o_colado_inteiro`; `test_a_ligadura_conhecida_nao_e_cortada`.

### A tabela, medida em 2026-08-24 — e o separador fica desligado

`cvoff-texto-colados`, **155 faixas de 11 livros**, as mesmas da S-198:

    modo       CER      cortes   faixas com corte
    nunca     0,2248        0        0            <- o padrão
    auto      0,2400       48       33
    sempre    0,5034      617      127

**O árbitro não salva o separador: ele só reduz o estrago.** `sempre` custa 0,2786 de CER; `auto`
custa 0,0152. Os dois são piores que não mexer — e a suspeita com que o item chegou estava certa.

**E a conclusão não é do limiar.** O braço `auto` foi refeito em cinco larguras suspeitas, e em
todas ele perde para `nunca`:

    largura suspeita   CER do auto   cortes
                1,35        0,2400       48
                1,60        0,2392       31
                1,80        0,2389       28
                2,00        0,2375       25
                2,50        0,2364       20

A curva é monótona e aponta para o óbvio: **quanto menos ele corta, melhor fica** — o limite é
não cortar. Sem a varredura, "o separador piora o CER" seria indistinguível de "o limiar estava
mal escolhido", e este projeto já tem cicatriz de conclusão tirada de um parâmetro.

**Por que ele não paga aqui, e a explicação estava na spec antes da medição:** as classes de
ligadura já absorvem o problema. O modelo lê `fi`, `e4` e `xf6` inteiros; o que o separador acha
para cortar são, em boa parte, glifos que ele já lia bem. É o mesmo movimento que lá derrubou a
vantagem de +0,3 para +0,1 de F1, levado até o fim.

**O padrão é `nunca`, e o código sai assim** (`colados.PADRAO`). O separador fica implementado,
travado por teste e **não chamado** — exatamente como o `separar` da S-198, e pelo mesmo motivo.

### Remedido na página em 2026-08-24, e o padrão não muda

A medição acima é sobre **155 faixas de legenda**. A S-211 pôs a página inteira em uso e a
pergunta reabriu com um caso concreto: numa folha lida na aba de texto, `40` saiu `co` e `44` saiu
`M`. O argumento para reabrir era estrutural e parecia forte — o modelo **não tem nenhuma ligadura
de dois dígitos** (não existe `ligature_40`), então um par colado só poderia sair como uma classe
de um caractere ou como uma ligadura de **letras**, e cortar seria a única saída.

Medido em 12 páginas de 4 livros, com a camada de texto da própria página como referência
(`docs/metrics/texto_pagina.json`, bloco `colados`):

| modo | CER | vs `nunca` | número de lance de 2 dígitos |
|---|---:|---:|---:|
| `nunca` | 0,2696 | — | 97 de 104 (93,3%) |
| `auto` | 0,2688 | −0,0009 | 97 de 104 (93,3%) |
| `sempre` | 0,2826 | +0,0129 | 97 de 104 (93,3%) |

**Idêntico nos três modos**, e a razão é que a hipótese estava errada: os dígitos **não estão
colados**. Só 2,1% das caixas da p30 do `Kemeri` passam do piso de largura, e os números perdidos
não estão entre elas — `10.` sai `1o.`, com o zero lido como `o` minúsculo, em **dois boxes bem
segmentados**; os de dois dígitos que acertam (`12. Ta1`, `16. c4`, `22. Db3`) já vinham separados.
Não há o que cortar.

O erro de diagnóstico é o achado, e por isso ele fica escrito: `40`→`co` **parece** um corte
perdido e são duas confusões de um caractere. Quem for atrás dessa família deve ir para o léxico
da S-209 ou para o treino, e não para a geometria. O separador passa a ser **chamável** por
`text/leitor.py` (`colados=`) e por `cvoff-texto-pagina --colados`.

### E a conclusão desta medição foi revista no mesmo dia

Ela deixou o separador **desligado** na página, e estava errada. O dono do projeto trouxe uma
página de texto **itálico**, e ali a conclusão se inverte: em itálico as letras encostam, e é
justamente onde o separador serve. Três coisas escaparam à primeira medição:

1. **a população** — 12 páginas de prosa **em pé**, sem itálico;
2. **a régua** — CER e recall de número de lance. Nenhuma enxerga `M♔king`, que é um par de letras
   colado lido como símbolo de xadrez: custa dois caracteres num texto de mil e apaga um nome
   próprio;
3. **a ordem** — ela rodou **antes** das quatro correções de geometria.

Remedido em 21 páginas de 7 livros (`docs/metrics/texto_colados_pagina.json`):

| referência | páginas | `nunca` | `auto` | melhoram / pioram |
|---|---:|---:|---:|---:|
| camada editorada (confiável) | 11 | 0,1077 | 0,1071 | 3 / **0** |
| camada de OCR (suspeita) | 10 | 0,2032 | 0,1953 | 6 / 3 |
| só as páginas com itálico | 4 | 0,1227 | 0,1207 | 3 / **0** |

**Na referência confiável o `auto` não piora uma única página.** O ganho de CER é pequeno; a
evidência forte é o caso nomeado — `Thus we s♔ that` vira `Thus we see that`, e `M♔king` vira
`Mecking`.

`leitor.COLADOS_NA_PAGINA` passa a ser `auto`. **`colados.PADRAO` continua `nunca`**, e tem de
continuar: aquele número descreve a faixa de legenda, medida sobre 155 delas. O modo `sempre`
continua fora dos dois, e agora com o motivo à vista — ele parte **figurina correta** (`♘f4` vira
`♘1f4`), que é exatamente o que o árbitro do `auto` recusa.

**Sonda.** `simbolo:chess_diagram_ocr.text.colados:separar`,
`metrica:texto_colados`.

---

## S-187 · A linha, e a ordem de leitura dentro dela ✅ implementada (2026-08-22)

**Problema.** Boxes soltos não são texto. Falta agrupá-los em linha e ordená-los — e ordenar por
`y` e depois por `x` na página inteira é o que mistura as duas colunas de um livro de duas
colunas, que é o defeito que o pedido nomeia.

A ordem de leitura por coluna é a Fase 27. Esta entrega faz a **linha**, que é pré-requisito
dela: a calha da S-190 se acha contando *linhas*, não boxes, e sem linha não há o que contar.

> **A solução escrita antes de implementar era pior que a portada, e a troca fica registrada
> (2026-08-22).** A spec pedia agrupamento por **banda horizontal**, derivando a linha da
> geometria. O projeto de origem chegou ao oposto depois de três fases: **a linha sai da ordem de
> leitura, e não da geometria** — quem já resolveu coluna, elemento transversal e pilha girada é
> a ordenação, e refazer isso por coordenada aqui desfaz o trabalho dela e volta a intercalar as
> duas colunas. A implementação portou o algoritmo medido.

**Solução.** `text/linhas.py`. `quebrar_em_linhas` recebe uma sequência **já em ordem de leitura**
e corta em três situações — a sequência desce, volta para a esquerda, ou **sobe**. Cada uma tem
cicatriz medida atrás, e as três constantes vêm com a tabela que as escolheu:

| constante | o que ela segura | medido |
|---|---|---|
| `CAIXA_CURTA = 0,65` | a caixa curta não fixa a base | linha que *começa* com aspas |
| `FOLGA_DE_LINHA = 0,25` | a vírgula raspa a base | 0,02 contra 0,66-4,88, dois montes sem nada entre eles |
| `FOLGA_DE_COLUNA = 1,0` | o apóstrofo sobe até a ascendente | 0,08-0,14 contra 66-104, vão de 470x |

`ordem_em_faixa` é a ordenação **de faixa** — banda e depois `x` —, e ela é a ordem de leitura de
verdade ali: uma faixa de legenda é o retângulo em volta de um diagrama e não tem coluna. Quando
a S-190 trouxer a ordem de leitura de página, `quebrar_em_linhas` continua valendo sem uma linha
de mudança, porque ele já consome ordem e não coordenada.

**Critério de aceite.**

- ✅ o apóstrofo depois de altura de x não abre linha nova, e a letra depois dele não parece ter
  descido;
- ✅ a vírgula que raspa a base não abre linha;
- ✅ subir para o topo da página abre linha nova — é a troca de coluna;
- ✅ a pilha girada não é cortada por subir (a 90° o texto se lê de baixo para cima);
- ✅ a caixa curta não fixa a base da linha.

**Testes.** `test_o_apostrofo_nao_abre_linha_nova_por_ter_subido`;
`test_a_letra_depois_do_apostrofo_nao_parece_ter_descido`; `test_a_caixa_curta_nao_fixa_a_base_da_linha`;
`test_a_virgula_que_raspa_a_base_nao_abre_linha`; `test_subir_para_o_topo_da_pagina_abre_linha_nova`;
`test_a_pilha_girada_nao_e_cortada_por_subir`; `test_a_folga_de_coluna_e_maior_que_a_de_linha`.

**Sonda.** `simbolo:chess_diagram_ocr.text.linhas:quebrar_em_linhas`.

---

## S-188 · Ler a linha, e não o caractere ✅ implementada (2026-08-24)

**Problema.** Um classificador de glifo isolado descarta o contexto, e o contexto é o que resolve
o que sobra. Medido lá, em 6.953 caracteres de 275 linhas rotuladas:

    por caractere (o melhor que o glifo sozinho dá)   72,8%
    por linha, com alinhamento                         91,2%

Os exemplos dizem o mecanismo melhor que a tabela: `Bib1i0g[aPhY` vira `Bibliography`, `F0reW0rd`
vira `Foreword`, `LeVe1` vira `Level`. **Nenhum desses é decidível olhando um glifo de cada vez**
— `0` e `o` da mesma fonte diferem em altura, e `1` e `l` em quase nada.

**Solução.** Um leitor de linha (CRNN) lê a faixa inteira e devolve uma string; o alinhamento por
distância de edição distribui essa string sobre os boxes, usando a leitura por caractere como
âncora — ela tem, por construção, exatamente um item por box.

Dois detalhes que não são opcionais:

- **o box vazio vira uma marca**, e não string vazia. `"".join` de uma lista com vazio encurta a
  string, o índice do alinhamento deixa de ser o índice do box, e tudo depois dele anda uma casa.
  A marca é um caractere que não existe em página nenhuma e por isso sempre cede a vez;
- **a linha girada ou em negativo não é lida em bloco** — a faixa deixa de ser um retângulo em pé
  e endireitar a faixa inteira é outro problema (S-195, S-197). Essas voltam ao modo por
  caractere.

**A decisão de qual leitor de linha usar está em aberto**, e é a de maior impacto do plano. As
três opções e o que cada uma custa estão no `ROADMAP_TEXTO`, seção de riscos. A recomendação é
começar pelo RapidOCR, que já é extra declarado aqui, e medir — o número de 91,2% é do
`english_g2` do EasyOCR, e não atravessa a troca de modelo sem medição.

**Critério de aceite.**

- ✅ a tabela "por caractere / por linha" refeita **neste** acervo, com o RapidOCR;
- ✅ o box vazio não desloca o alinhamento — `test_o_box_vazio_nao_desloca_o_alinhamento`;
- ✅ linha girada cai no modo por caractere, e o teste prova que o leitor **nem é chamado**;
- ✅ o ganho medido está registrado, e ele é de **0,0018** — a leitura por linha fica desligada,
  com a tabela ao lado.

**Testes.** `test_o_box_vazio_nao_desloca_o_alinhamento`;
`test_a_linha_girada_cai_no_modo_por_caractere`;
`test_a_string_maior_que_os_boxes_descarta_o_excedente`.

### A tabela, medida em 2026-08-24 — e o ganho de 18,4 pontos virou 0,0018

`cvoff-texto-linha`, **155 faixas de 11 livros**, com o RapidOCR como leitor de linha — a
recomendação que o `ROADMAP_TEXTO` registra, medida.

    CER por caractere   0,2248
    CER por linha       0,2230     ganho de +0,0018

**Lá foram 72,8% → 91,2%; aqui é ruído.** E o roadmap já avisava por quê: *"o número de 91,2% é do
`english_g2` do EasyOCR, e não atravessa a troca de modelo sem medição"*. Atravessou como zero.

**A leitura por linha fica desligada, que é o que o critério manda fazer com um ganho assim.** O
módulo fica implementado e travado por teste — e não é desperdício, porque a metade dele que
**paga** é a S-189, abaixo.

> **O que quebrou primeiro, e vale como aviso de forma.** A âncora do alinhamento tinha um
> caractere por box, e as **classes de ligadura devolvem dois** (`fi`, `xf6`, `♗a`): a âncora
> ficava mais longa que a lista de caixas e o `zip` estrito estourava. A correção não é alargar a
> âncora — é lembrar **de que box veio cada posição dela**, e regrupar depois. Uma ligadura ocupa
> duas posições e continua sendo uma caixa.

**Sonda.** `simbolo:chess_diagram_ocr.text.leitura_de_linha:em_bloco`,
`metrica:texto_linha`.

---

## S-189 · A confiança sai da concordância, e ela é calibrada ✅ implementada (2026-08-24)

**Problema.** O leitor de linha devolve **uma** confiança para a faixa inteira. Distribuí-la
igual por todos os boxes seria inventar precisão que não foi medida — e este projeto tem o
achado gêmeo do outro lado: a métrica primária da avaliação de agosto **mede confiança e não
correção**.

**Solução.** A confiança de um caractere é a **concordância entre as duas leituras**: quando
linha e caractere dizem o mesmo, uma corrobora a outra e vale a maior; quando divergem, a linha
venceu mas há dúvida real, e vale a **menor** — que é o que põe o box na fila de revisão.

E a calibração de temperatura da S-179 é aplicada antes de qualquer comparação de confiança.
Duas réguas não calibradas comparadas entre si não medem o que se pensa: lá, a F25 mediu que
**réguas separadas medem pior, e duas vezes**.

**Critério de aceite.**

- ✅ a tabela de acerto por faixa de concordância, e ela separa por **dois**: 98,6% onde as duas
  leituras concordam contra 48,2% onde divergem;
- ✅ a curva de calibração dessa confiança está em `docs/metrics/texto_calibracao_<data>.json`;
- ✅ a divergência produz a confiança menor — `test_concordancia_vale_a_maior_e_divergencia_a_menor`.

**Testes.** `test_concordancia_vale_a_maior_e_divergencia_a_menor`;
`test_a_temperatura_e_aplicada_antes_de_comparar`;
`test_a_curva_de_calibracao_e_gravada_com_o_n`.

### A concordância paga, mesmo com o ganho da S-188 sendo zero

Medido junto com a S-188, sobre os mesmos **6.816 caracteres** de 155 faixas:

| as duas leituras | n | na referência | confiança média |
|---|---:|---:|---:|
| **concordam** | 4.935 | **0,9856** | 0,9672 |
| **divergem** | 1.881 | **0,4822** | 0,8405 |

**Onde as duas leituras discordam, metade está errada; onde concordam, 1,4% está.** A regra da
S-189 separa o certo do errado por um fator de dois, e a confiança que ela produz acompanha:
0,967 contra 0,840.

**Isto é o que torna a S-188 valer a pena mesmo com ganho nulo.** A leitura por linha não melhora
o texto neste acervo — mas a **discordância entre as duas leituras** é o melhor sinal de erro que
este projeto tem, e é exatamente o que a fila de revisão da S-212 precisa para ordenar o trabalho
humano. O leitor de linha entra como **segundo opinante**, não como leitor.

> **A régua do acerto aqui é fraca, e ela está declarada.** Sem rótulo por box, o que dá para
> medir é se o caractere lido **existe** na linha de referência — não se ele estava naquela
> posição. A régua forte precisa da anotação que a S-212 vai produzir. A fraca já separa por dois,
> e a forte só pode separar mais.

### E a confiança que sai da concordância **não é calibrada** — a curva diz isso

`docs/metrics/texto_calibracao_<data>.json`, 6.816 caracteres:

    ECE ponderado   0,1490
    ECE por faixa   0,3416

    faixa        n      ele diz   ele acerta
    0,33-0,40     56      0,363      0,982
    0,73-0,80    193      0,761      0,549
    0,87-0,93    534      0,900      0,607
    0,93-1,00  5.314      0,991      0,881

**Ela ordena bem e mede mal, e as duas coisas são verdade ao mesmo tempo.** Como *ranking* a regra
funciona -- 98,6% contra 48,2% entre os dois grupos. Como *probabilidade*, não: onde ela diz 0,99
acerta 0,88, e onde diz 0,36 acerta 0,98.

**A causa está na spec deste item, escrita antes da medição:** *"a calibração de temperatura da
S-179 é aplicada antes de qualquer comparação de confiança. Duas réguas não calibradas comparadas
entre si não medem o que se pensa."* Metade da comparação está calibrada -- o glifo, pela S-205 --
e a outra metade não: a confiança do RapidOCR nunca passou por calibração nenhuma. O `min` e o
`max` entre uma escala calibrada e uma crua produzem uma escala crua.

**Consequência prática, e ela é uma decisão:** a confiança da concordância serve para **ordenar** a
fila da S-212, e **não** para cortar por limiar. Um corte em 0,9 aqui deixaria passar 12% de erro
achando que deixa 1%.

> **E a régua do acerto é a fraca**, como declarado acima: "existe na linha de referência" não é
> "estava naquela posição". A curva refeita sobre anotação por box pode mudar de forma -- o que
> ela não deve mudar é a conclusão de que duas escalas diferentes não se comparam sem calibrar.

**Sonda.** `simbolo:chess_diagram_ocr.text.leitura_de_linha:confianca_por_concordancia`,
`metrica:texto_calibracao`.

---

# Fase 27 — A coluna

> É o que o pedido chama de *"além de colunas no pdf"*. O projeto já ordena por coluna **dentro
> de um bloco da camada de texto**; isso não é o mesmo que saber onde a coluna acaba na imagem.

## S-190 · A calha: onde a coluna acaba, medido na imagem ✅ implementada (2026-08-22)

**Problema.** `pdf_text._split_into_columns` rotula por coluna as linhas de **um bloco** da
camada de texto, unindo as que se sobrepõem na horizontal. Funciona, e resolve o caso do
`Karpov` — legendas de duas colunas num bloco só. Mas depende da camada de texto existir, e nos 7
livros de scan puro ela não existe.

Sem coluna achada na imagem, três coisas quebram, e todas foram medidas lá:

- o último parágrafo da esquerda sai colado no primeiro da direita;
- a margem que abre parágrafo é a mediana das esquerdas, e sem coluna essa mediana não é margem
  de coluna nenhuma;
- o diagrama flutua, porque ele pertence a uma coluna.

**Solução.** `text/colunas.py`, com `calha(linhas, largura)`: a faixa vertical de x em que
**nenhuma linha** entra, larga o bastante e centrada o bastante para ser calha de coluna e não
espaço entre palavras.

**A calha certa é larga, e aí cabe gente dentro dela.** É a lição da F70 de lá: exigir vão
absolutamente vazio é frágil, porque uma única letra o fecha (S-191). O critério é uma **fração
de linhas** que atravessam, não uma proibição.

**Critério de aceite.**

- numa página sintética de duas colunas com 40 linhas, a calha sai no lugar certo, com tolerância
  de uma escala de caractere;
- numa página de coluna única, a saída é "sem calha" e não uma calha inventada no meio;
- a atribuição de coluna é estável quando a página é renderizada a 220 e a 300 DPI.

**Testes.** `test_a_calha_sai_no_lugar_na_pagina_de_duas_colunas`;
`test_coluna_unica_nao_inventa_calha`; `test_a_calha_nao_muda_com_o_dpi`.

**Sonda.** `simbolo:chess_diagram_ocr.text.colunas:calha`.

---

## S-191 · A calha não morre por uma letra de cabeçalho ✅ implementada (2026-08-22)

**Problema.** Este é o defeito mais instrutivo da série de lá, e ele reaparece em qualquer
implementação ingênua: **uma letra do cabeçalho apagava a calha da página inteira.**

A causa não era o limiar. Era um `OR`: o critério perguntava "existe algum box nesta faixa de
x?", e o cabeçalho — que atravessa as duas colunas — responde sim para todas as faixas. Uma
página inteira de duas colunas saía como coluna única por causa de um título.

**Solução.** Contar **linhas**, não boxes, e exigir que uma fração das linhas do corpo atravesse
a faixa antes de descartá-la como calha. O cabeçalho é uma linha entre quarenta; o corpo é as
outras trinta e nove.

E a calha do cabeçalho é um caso à parte, com nome próprio: uma faixa horizontal no topo que
pertence às duas colunas. Ela não vira coluna, vira **cabeçalho** — e é isso que impede o título
de ser adotado como primeiro parágrafo da coluna da esquerda.

**Critério de aceite.**

- a página sintética com cabeçalho atravessando as duas colunas mantém a calha;
- a fração de linhas que fecha a calha está declarada como constante com o motivo no comentário,
  e existe teste que falha se alguém a trocar por "qualquer box";
- o cabeçalho sai marcado como cabeçalho, não como linha da coluna 1.

**Testes.** `test_o_cabecalho_nao_apaga_a_calha`;
`test_o_criterio_conta_linhas_e_nao_boxes`; `test_o_cabecalho_nao_vira_primeiro_paragrafo`.

**Sonda.** `simbolo:chess_diagram_ocr.text.colunas:atribuir_coluna`.

---

## S-192 · O parágrafo, o recuo, e a coluna estreita demais para ser coluna ✅ implementada (2026-08-22)

**Problema.** Ordem não é parágrafo. Saber que a linha 12 vem antes da 13 não diz onde um
parágrafo termina e outro começa, e sem isso o texto exportado é uma parede.

E há um piso que a medição de lá obrigou a acrescentar: **a coluna estreita demais para ser
coluna**. Sem ele, uma margem larga vira coluna e a página sai em três — com uma delas contendo
os números de página.

**Solução.** `text/paragrafos.py`:

- **o corte de parágrafo** é a linha cujo recuo à esquerda foge da margem da coluna, ou a linha
  anterior que termina bem antes da margem direita;
- **a margem da coluna** é a mediana das esquerdas *daquela coluna*, e não da página;
- **o piso de largura** descarta candidata a coluna abaixo de uma fração da largura útil, com a
  fração declarada e justificada.

**Critério de aceite.**

- numa página sintética com três parágrafos por coluna, saem três parágrafos por coluna;
- a margem estreita da página não vira uma terceira coluna;
- o número de página não entra em parágrafo nenhum — ele já tem dono, `pdf_text.running_page_number`,
  e esta entrega reusa esse critério em vez de escrever outro.

**Testes.** `test_o_recuo_abre_paragrafo`; `test_a_margem_nao_vira_coluna`;
`test_o_numero_de_pagina_nao_entra_no_paragrafo`.

**Sonda.** `simbolo:chess_diagram_ocr.text.paragrafos:cortar`.

---

## S-193 · O diagrama é um objeto da coluna, não um buraco nela ✅ implementada (2026-08-22)

**Problema.** Hoje o diagrama e o texto vivem em mundos separados: `detection/hybrid.py` acha o
tabuleiro, `pdf_text.py` acha a legenda, e `assign_lines_to_diagrams` costura os dois **para a
legenda**. Não há nada que diga *em que ponto do fluxo de leitura* o diagrama entra.

Para a FEN isso não importa. Para exportar o livro, importa: o diagrama entre o parágrafo 3 e o
4 tem de sair entre o 3 e o 4.

**Solução.** O diagrama vira um elemento da coluna, com a mesma chave de ordenação das linhas
(topo, e coluna). Ele é excluído da segmentação de texto (S-185) e reinserido na sequência de
leitura — a exclusão e a reinserção usam **o mesmo bbox**, o que a S-12 já carrega, para que não
haja duas verdades sobre onde o diagrama está.

O caso do diagrama que atravessa as duas colunas existe (diagrama largo, centrado) e não é
inventado: ele vira elemento da página, não da coluna, e a leitura o coloca entre a última linha
acima dele e a primeira abaixo.

**Critério de aceite.**

- numa página sintética com diagrama no meio da coluna 1, a sequência de leitura o traz na
  posição certa;
- o diagrama centrado que atravessa as duas colunas sai entre a linha de cima e a de baixo, e não
  no fim da página;
- exclusão e reinserção usam o mesmo bbox, travado por teste.

**Testes.** `test_o_diagrama_entra_na_ordem_da_coluna`;
`test_o_diagrama_largo_e_da_pagina_e_nao_da_coluna`;
`test_a_exclusao_e_a_reinsercao_usam_o_mesmo_bbox`.

**Sonda.** `simbolo:chess_diagram_ocr.text.pagina:sequencia_de_leitura`.

---

## S-194 · O placar da ordem de leitura ✅ implementada (2026-08-22)

**Problema.** As três entregas acima são invisíveis: elas não mudam a FEN, não mudam a legenda e
não aparecem na tela. O único jeito de saber se elas funcionam é medir a ordem — e sem régua,
uma regressão de ordem passa despercebida até alguém exportar um livro e ler.

> **A referência anotada à mão foi substituída por uma melhor, e de graça (2026-08-22).** A spec
> pedia 12 páginas anotadas. Ao implementar apareceu a referência óbvia: nos livros com camada de
> texto, **o próprio PDF já traz a ordem de leitura** -- é a ordem em que o produtor emitiu os
> spans, e ela vem da diagramação, não de medição nossa. A S-190 acha a coluna projetando caixas
> na imagem; nenhum dos dois olha para o outro, e é isso que faz da comparação uma medição em vez
> de um espelho.

**Solução.** `cvoff-texto-ordem` compara a sequência de leitura produzida contra a da camada e
reporta a **distância de Kendall-tau** -- pares invertidos sobre o total de pares. Uma página com
40 linhas e um par fora de ordem não é o mesmo defeito que uma com as duas colunas intercaladas, e
uma régua de "acertou tudo" trataria as duas igual.

> **E a referência precisou de um guarda, achado na primeira execução.** O `tau` médio deu 0,0965
> e o pior caso 0,53 -- como se estivéssemos lendo páginas quase ao contrário. Investigado: no
> `400 Quebra-cabeças ..._hq` a camada emite o rodapé (y=797), depois a metade de baixo
> (y=309..630) e **só então o topo** (y=88..281). Três blocos, cada um internamente ordenado, na
> ordem errada entre si. Nossa saída é estritamente de cima para baixo.
>
> O guarda é geométrico: numa página de **uma** coluna a ordem de leitura é crescente em `y` por
> definição; numa de duas ela desce uma vez. Mais descidas que `colunas - 1` é bloco fora de
> ordem, e ali o `tau` mede a referência.
>
>     sem o guarda    150 páginas, tau médio 0,0965, 37 em ordem exata
>     com o guarda     57 páginas, tau médio **0,0096**, 32 em ordem exata
>
> As 93 páginas excluídas **não somem em silêncio**: entram no relatório em
> `paginas_com_referencia_suspeita`. E o número em si é um achado sobre o acervo -- 62% das
> páginas com camada de texto a emitem fora da ordem de leitura, o que é o argumento mais forte
> que existe para não confiar nela.

**O limite conhecido, medido e não corrigido.** O pior caso que sobrou é o `Karpov`, com `tau`
0,229. Ali a camada emite **linha a linha atravessando as colunas** e nós lemos **coluna a
coluna** -- e as duas ordens são legítimas: a página é uma grade de exercícios numerados da
esquerda para a direita, não prosa em duas colunas. Distinguir grade de prosa precisa de um sinal
próprio (as linhas das duas colunas pareadas no mesmo `y`) e de medição própria; fica registrado
como item futuro em vez de virar palpite agora.

> **Corrigido pela S-216 (2026-08-23), e o palpite acima estava errado em dois pontos.**
>
> **O sinal proposto não existe.** "As linhas das duas colunas pareadas no mesmo `y`" não separa
> grade de prosa — em prosa de duas colunas elas também estão pareadas —, e não é a pergunta
> certa: separar grade de prosa é fácil por geometria, e **a direção não é geométrica**. O
> `Schiller` e o `Karpov` têm grades indistinguíveis numeradas ao contrário uma da outra, e ligar
> "grade ⇒ linha a linha" consertaria o `Karpov` e quebraria o `Schiller`, que tem mais páginas.
> O que decide é o número impresso, e ele é constante por livro.
>
> **E esta referência não é da diagramação onde importa.** Os quatro livros de grade que o
> acervo permite calibrar — `Karpov`, `Schiller`, `Burgess` e `Secrets` — trazem camada do
> `Adobe Acrobat Paper Capture`, e medida contra o número impresso ela erra a direção em 24 de
> 164 páginas, **nos dois sentidos**. O `tau`
> continua valendo como régua de regressão de ordem, que é para o que foi feito; ele não arbitra
> grade de exercício, e ali persegui-lo premiaria a ordem errada. Ver a S-216.

**Critério de aceite.**

- ✅ a métrica existe em `docs/metrics/texto_ordem.json`, por livro e agregada, com o `n`;
- ✅ os livros sem camada de texto aparecem como "sem referência", que é o que são (11 dos 41);
- ✅ a página cuja referência não é ordem de leitura é contada, e não descartada calada;
- ✅ `--baseline` falha quando a ordem piora, no mesmo desenho do `cvoff-census --fail-on-loss`.

**Testes.** `test_a_referencia_com_blocos_fora_de_ordem_e_recusada`;
`test_uma_troca_local_pesa_pouco_e_o_embaralhado_pesa_muito`;
`test_o_bloco_fora_de_ordem_desce_mais_de_uma_vez`; `test_o_baseline_falha_quando_a_ordem_piora`;
`test_o_relatorio_traz_o_livro_sem_camada_de_texto`.

**Sonda.** `simbolo:chess_diagram_ocr.cli.texto_ordem:main`, `metrica:texto_ordem`.

---

## S-216 · A grade de exercícios, e a direção que só o número impresso diz ✅ implementada (2026-08-23)

**Problema.** É o limite que a S-194 registrou e não corrigiu. `sequencia_de_leitura` ordena
sempre **coluna a coluna**: a coluna da esquerda inteira, depois a da direita. É a ordem certa
para prosa em duas colunas, e é a única que ela conhece.

Uma folha de exercícios não é prosa. É uma **grade** de células — um diagrama e uma legenda curta
—, e há livro que a numera atravessando as colunas. Lida coluna a coluna, ela sai fora da ordem
dos próprios números: na página 62 do `Karpov 1` o exercício 311 é seguido de 313, 315, e só
depois vêm 312, 314, 316.

**A hipótese com que este item começou estava errada, e a medição é que disse.** A S-194 supôs
que o sinal fosse geométrico — "as linhas das duas colunas pareadas no mesmo `y`". Medido, ele
não separa nada, e o contraexemplo é limpo:

    Schiller, Big Book of Combinations    89  92     numerado coluna a coluna
                                          90  93
                                          91  94

    Karpov, Chess Combinations 1         311 312     numerado linha a linha
                                         313 314
                                         315 316

Duas colunas nas duas, três fileiras nas duas, legendas pareadas no mesmo `y` nas duas, mesma
densidade vertical nas duas. **Nenhuma régua sobre caixas as separa** — o que as separa é o número
impresso. Ligar "grade ⇒ linha a linha" consertaria o `Karpov` (85 páginas de grade) e o `Burgess`
(18), e quebraria o `Schiller` (91) e o `Secrets` (4).

> **E a régua da S-194 aprovaria a mudança errada.** Medido nas 232 páginas de grade com
> referência utilizável (`docs/metrics/texto_grade.json`, campo `tau`):
>
>     coluna a coluna (o que a S-193 faz)      tau 0,1271
>     tudo lido como grade                     tau 0,0943   <- "melhora", e está errado
>     calibrado, só o que foi confirmado       tau 0,0676
>     calibrado, com a hipótese do Yusupov     tau 0,0328
>
> **A leitura do meio é a armadilha, e ela é o motivo de este item não ser medido por `tau`.**
> Ligar "grade ⇒ linha a linha" para todo mundo faz o número agregado **cair**, e um portão de "o
> `tau` médio tem de cair" a aprovaria — enquanto ela leva o `Schiller` de 0,0004 para 0,1705,
> 426x pior, num livro cuja numeração impressa diz coluna a coluna em 77 de 77 páginas. O agregado
> premia o atalho porque o `Karpov` tem mais páginas de grade que o `Schiller`, e não porque o
> atalho esteja certo.
>
> Livro a livro, e é aqui que o critério mora:
>
>     Karpov     0,2329 -> 0,0456   número impresso
>     Burgess    0,1683 -> 0,0312   número impresso
>     Schiller   0,0004 -> 0,0004   número impresso; inalterado, ele confirma a leitura de hoje
>     Secrets    0,2617 -> 0,2617   número impresso; inalterado, e o tau segue alto -- ali quem
>                                   erra é a camada, e a calibração recusa segui-la
>     Yusupov    0,1809 -> 0,0443   **hipótese**, só a camada
>
> **Nenhum livro piora.** É esse o critério, e não a média.
>
> As duas últimas linhas da tabela de cima são a mesma calibração com e sem o `Yusupov`, e a
> distância entre elas — 0,0676 contra 0,0328 — é **quanto do ganho está apoiado em palpite**.
> Metade. Por isso os dois números são publicados, em vez de só o menor.

**A referência da S-194 não é da diagramação nos livros que interessam, e este item é quem
descobriu.** A S-194 justifica o `tau` dizendo que a ordem dos spans vem do typesetter. Conferido
em 2026-08-23, o acervo é **misto**: parte é editorada de verdade — o `Polgar` sai de LaTeX com a
fonte `SkakNew`, o `Dvoretsky`, o `1001` e o `400 Quebra-cabeças` saem de conversão de ebook — e
parte é digitalização com OCR por cima. **Os quatro livros de grade estão todos do segundo
lado:** `Karpov`, `Schiller`, `Burgess` e `Secrets` trazem camada do `Adobe Acrobat Paper
Capture`. Ou seja,
exatamente onde a pergunta se faz, a "ordem do typesetter" é o palpite de um motor. Medido contra
o número impresso, esse motor erra a direção da grade **nos dois sentidos**:

    Karpov 1     49 páginas de acordo com o número impresso, 17 contra
    Schiller     77 de acordo,  0 contra
    Burgess      14 de acordo,  4 contra
    Secrets       0 de acordo,  3 contra   <- e aqui ela erra o livro inteiro

24 de 164, uma em cada sete. Nessas 24 o `tau` premiaria a ordem errada.

O `Secrets of Chess Training` é o caso mais limpo do acervo, e vale ser específico: as páginas de
grade dele trazem `IV/2 IV/3 IV/4` descendo a coluna da esquerda e `IV/5 IV/6 IV/7` descendo a da
direita — coluna a coluna, sem ambiguidade —, e a camada emitiu as três atravessando. Ali o `tau`
sob a leitura **errada** é 0,014 e sob a certa é 0,262. Uma régua de `tau` escolheria a errada por
18x, num livro em que basta olhar a página para ver qual é qual. A correção do texto da S-194 está
no fim daquela seção.

**Solução.** Duas metades, e elas respondem a perguntas diferentes.

- **A geometria diz se a página é grade**, e nisso ela é confiável: `grade.parece_grade`. O vão
  entre duas fileiras de exercícios é a altura de um tabuleiro e atravessa *todas* as colunas ao
  mesmo tempo; prosa não tem esse vão, porque onde uma coluna tem buraco a outra tem texto. Medido
  nas 276 páginas de 2+ colunas do acervo, `fracao_de_vao` dá 0,000–0,153 em prosa densa (mais uma
  de 0,281, a página 53 do `Neumann`, que não é prosa: são diagramas com a camada de OCR em
  pedaços) e 0,634–0,826 em grade. O limiar fica em 0,30 — 2,0x acima da maior prosa de verdade e
  2,1x abaixo da menor grade, com o outlier abaixo dele. Nenhuma das 103 densas é classificada
  como grade, e nenhuma das 62 grades é perdida.
- **O número impresso diz a direção**, e é o único que a *prova*: `grade.direcao_pela_numeracao`,
  sobre a maior corrida de inteiros consecutivos da página. E ela é **constante por livro** —
  `Karpov` 66 de 66 páginas decidíveis, `Burgess` 18 de 18, `Schiller` 77 de 77, `Secrets` 3 de 3,
  sem uma única contradição em 164 páginas —, o que faz da calibração por livro uma medição barata
  em vez de um palpite por página.
- **Onde não há número impresso, a camada opina — e isso sai rotulado.** `cvoff-texto-grade` tem
  uma segunda urna: se a primeira ficar vazia, a direção vem da preferência da camada de texto,
  medida pelo `tau`, e o livro sai com `"fonte": "camada"` e `"hipotese": true`. É o que dá
  direção às 64 páginas do `Yusupov` sem fingir que ela foi verificada. Ver
  "O livro que o número impresso não alcança", abaixo.

`sequencia_de_leitura` ganha `arranjo: Arranjo = "prosa"`. **Não há detecção automática**, e a
ausência dela é a entrega: o `arranjo` chega calibrado de fora, e o padrão é o lado seguro do
erro. Tratar prosa como grade embaralha quarenta linhas; tratar grade como prosa desordena cinco
elementos. Na dúvida, prosa.

E a segurança não é só o padrão, é estrutural: **prosa não tem vão de fileira**, então
`arranjo="grade"` numa página de prosa não acha onde partir e devolve exatamente a leitura de
prosa. Medido nas páginas de prosa densa do acervo, o `tau` sob os dois arranjos é idêntico até a
última casa.

> **O que este item deliberadamente não faz: calibrar sozinho.** `cvoff-texto-grade` mede a direção
> de cada livro e a grava no relatório; quem lê o relatório e passa o `arranjo` para a varredura é
> a S-211, quando houver modelo de página. Fechar esse laço agora significaria escolher onde mora
> a preferência por livro — e essa decisão é da S-211, não desta.
>
> **De onde vêm os números hoje, e de onde virão depois.** `direcao_pela_numeracao` recebe pares
> `(valor, caixa)` e não sabe o que é PDF. Hoje quem os fornece é a camada de texto; quando a
> S-188 ler a linha da imagem, ela fornece os mesmos pares e nada nesta camada muda. É o que
> permite calibrar os 11 livros sem camada de texto sem reabrir este item.

**O livro que o número impresso não alcança é calibrado pela camada, e sai marcado `hipotese`.**
O `Yusupov` tem 64 páginas de grade e **nenhuma decidível**: o número do exercício não sai da
camada como inteiro isolado. Deixá-lo em `prosa` seria ignorar a única evidência que existe sobre
ele — a camada vota `grade` em 48 páginas contra 6, concordância 0,89 —; tratá-lo como medido
seria mentir sobre a força dela. A saída é a segunda urna: a camada
calibra, e o relatório carrega `"fonte": "camada"` e `"hipotese": true`.

**E a hipótese vem com o preço dela medido.** Nas 144 páginas em que o número impresso pode
conferir o palpite da camada, ela acerta 139 — 96,5%. Esse é o número otimista, e ele não é o que
importa: o que se calibra é o **livro**, e livro a livro a camada acertou **3 de 4**.

    Karpov     49 de 49 páginas de acordo   direção do livro: certa
    Schiller   76 de 76                     certa
    Burgess    14 de 16  (87,5%)            certa
    Secrets     0 de  3  (unânime)          **errada**

**Concordância alta não é acerto**, e o par `Secrets`/`Burgess` prova: o unânime está errado e o
menos unânime está certo. Por isso o piso de concordância da segunda urna
(`CONCORDANCIA_DA_CAMADA = 0,70`) não é um portão de confiança — não teria como ser. Ele só evita
chamar de direção o que é cara ou coroa, e quem carrega a incerteza é o rótulo.

> **E a primeira execução mostrou que só o piso de concordância não basta: ela calibrou o
> `Neumann` com um voto.** Uma página unânime é unânime consigo mesma, e 1 de 1 passa por qualquer
> régua de fração. Daí `VOTOS_MINIMOS_DA_CAMADA = 8`, e ele também é medido: o `Secrets` prova que
> **três votos unânimes da camada podem estar todos errados**, então um tamanho de amostra já
> reprovado não pode passar. O piso fica 2,7x acima dele e 6,8x abaixo do `Yusupov`, que é o único
> livro que o acervo de fato calibra assim.
>
> O piso de votos **não vale para o número impresso**: lá o `Secrets` é calibrado com 3 páginas e
> está certo. Três verdades bastam; três palpites não — é a assimetria inteira desta entrega em
> uma linha.

Três consequências ficam registradas no desenho:

- o número impresso **vence sempre**: onde ele existe, a camada não é consultada para decidir — é
  literalmente o caso do `Secrets`, em que consultá-la inverteria o livro;
- a hipótese **não entra no `acerto`**, que é o que o `--baseline` trava. Uma calibração conferida
  contra o próprio palpite não é uma régua;
- o `tau` sai em duas colunas, `calibrado` e `so_confirmado`, e a diferença entre elas é
  exatamente quanto do ganho está apoiado em palpite. Quem a zera é a S-188, lendo o número da
  imagem — e ela pode tanto confirmar o `Yusupov` quanto desmenti-lo.

Sem hipótese ficam três livros com 1 a 6 páginas de grade cada (`Aagaard`, `Neumann`,
`Niemeijer`) — poucas demais para a camada opinar sobre o livro — e os 10 sem camada de texto
nenhuma.

**Um segundo limite, herdado da S-190.** Numa página de grade esparsa, `detectar_colunas`
super-parte: a página 41 do `Burgess` é uma grade de 2 células de largura e sai com 3 colunas,
porque com 4 bandas o vão entre o número e a legenda se alinha verticalmente em todas elas. Não
estragou nenhuma medição — os números continuam caindo em colunas distintas, e a direção sai
certa —, mas é o mesmo defeito do `LINHAS_PARA_TOLERAR` visto do outro lado, e está registrado
aqui porque quem confiar na *contagem* de colunas numa página esparsa vai tropeçar nele.

**O terceiro limite, medido e não corrigido.** O elemento entra na fileira pelo **topo** dele, e
isso é o certo para os quatro livros de grade do acervo, em que a legenda vem *acima* do
tabuleiro.
Numa diagramação com a legenda *abaixo*, o corte cairia no meio do tabuleiro e o topo o deixaria
na fileira anterior. Nenhum livro daqui diagrama assim, e a regra não foi escrita para um caso que
ninguém pôde medir.

**Critério de aceite.**

- ✅ a página de prosa densa em duas colunas e a folha de exercícios esparsa são separadas por
  geometria, com o limiar entre as duas populações medidas e o número no docstring da constante;
- ✅ a mesma grade numerada nas duas direções produz as duas ordens, e **nenhuma régua geométrica
  do módulo as distingue** — há teste que falha se alguma passar a distinguir;
- ✅ o padrão de `sequencia_de_leitura` continua sendo prosa, e pedir `grade` numa página de prosa
  não muda nada;
- ✅ o livro calibrado **pela camada** sai marcado `hipotese`, o número impresso vence a camada
  onde os dois falam, e a hipótese não entra no `acerto` que o `--baseline` trava;
- ✅ a direção medida por livro está em `docs/metrics/texto_grade.json`, com os votos de cada lado
  à vista e o desacordo entre a camada de texto e o número impresso contado;
- ✅ `--baseline` falha quando o acerto cai, no mesmo desenho do `cvoff-texto-ordem --baseline`.

**Testes.** `test_a_prosa_densa_nao_e_grade`; `test_a_grade_esparsa_e_grade`;
`test_as_duas_grades_sao_geometricamente_iguais`; `test_a_numeracao_atravessando_as_colunas_pede_grade`;
`test_a_numeracao_descendo_a_coluna_pede_prosa`; `test_pedir_grade_numa_pagina_de_prosa_nao_muda_nada`;
`test_qualquer_vao_transformaria_prosa_em_grade`; `test_uma_figura_no_meio_da_prosa_nao_faz_grade`;
`test_o_diagrama_entra_na_fileira_da_celula_dele`;
`test_o_numero_impresso_vence_a_camada_quando_os_dois_falam`;
`test_o_livro_sem_numero_impresso_e_calibrado_por_hipotese`;
`test_a_hipotese_sai_separada_do_numero_confirmado`; `test_a_camada_dividida_nao_vira_hipotese`.

**Sonda.** `simbolo:chess_diagram_ocr.text.grade:direcao_pela_numeracao`, `metrica:texto_grade`.

---

# Fase 28 — Os casos que apagam texto

> O que une os cinco é a **forma de falha**: o texto não sai errado, ele **não sai**, e nada
> acusa. Um erro que se anuncia custa revisão; um que não se anuncia custa confiança no programa
> inteiro. Esta fase é paralela à 27 e pode esperar por ela.

## S-195 · A tarja: texto claro sobre escuro ✅ implementada (2026-08-22)

**Problema.** Livro de xadrez põe o cabeçalho da partida numa tarja: *"J.Bolbochan –
L.Pachman"* em branco sobre um retângulo preto. A binarização deixa a tinta em branco, então a
tarja inteira vira um borrão, `findContours` com `RETR_EXTERNAL` devolve **um** box e os vinte
caracteres de dentro somem. Medido lá, na página 33 do Yusupov: 6 tarjas, 6 boxes, zero
caracteres. No *Chess Evolution 1* são 264 páginas com tarja em quase toda partida.

**Solução.** `text/negativo.py`. Três decisões que a medição de lá impôs:

1. **A polaridade é do box, não da página.** Inverter a página inteira seria mais simples e está
   descartado: o usuário confere o box contra a página impressa, e mexer no que ele vê para
   consertar o que o modelo lê troca um problema de leitura por um de revisão.
2. **A faixa é aparada antes de ser lida.** Acima da tarja há uma tira decorativa hachurada,
   clara o bastante para virar tinta na inversão; ela encosta no topo das letras e funde meia
   linha num componente só. Linha de retângulo cheio tem ~100% de tinta, linha de tira hachurada
   tem 55%–75%: encolhe-se de fora para dentro até a primeira linha (e coluna) cheia.
3. **O que decide não é o formato da faixa, é o que tem dentro.** Inverte-se e conta-se quantos
   componentes têm tamanho de caractere **em relação à altura da própria faixa** — a régua está
   dentro dela, não na mediana da página, que não é confiável (medido lá: 4 px numa página contra
   18 px na seguinte).

**O limite conhecido, e ele fica registrado e não corrigido:** com o glifo medido contra a altura
da faixa, a razão cai a cada linha a mais. Uma tarja de duas linhas passa raspando; uma de três
não passaria. A correção óbvia — deduzir a altura agrupando os próprios componentes — é também a
que aceitaria a palavra sublinhada.

**Critério de aceite.**

- a tarja sintética de uma linha com 20 caracteres devolve 20 boxes com `negativo=True`;
- a tira hachurada acima da tarja é aparada, e o teste prova pelo perfil de tinta por linha;
- a faixa cheia que **não** é tarja (foto, logotipo) devolve zero boxes;
- o limite das três linhas está no docstring, com o número que o mede.

**Testes.** `test_a_tarja_devolve_os_caracteres_de_dentro`;
`test_a_tira_hachurada_e_aparada`; `test_a_foto_nao_vira_tarja`.

**Sonda.** `simbolo:chess_diagram_ocr.text.negativo:candidatos`.

---

## S-196 · A trama de meio-tom ✅ implementada (2026-08-22)

**Problema.** O quadro de pontuação que fecha cada capítulo é um painel chapado, e o
escaneamento o devolve como uma nuvem de pontos. O estrago é em dois tempos, e o segundo apaga o
texto:

1. **A trama envenena toda régua relativa.** Medido lá na página 18 do *Chess Evolution 1*: 6.765
   contornos, 95,8% deles de 6×6 px ou menos, e a mediana das alturas em **2 px**. Com essa
   mediana, a régua da S-185 joga fora tudo acima de 8 px — isto é, os caracteres.
2. **A trama solda o texto ao fundo.** O painel inteiro sai como **um** contorno de 1049×390.

**Solução.** O primeiro tempo é da S-185 (`escala_de_texto` pesada por tinta, e não mediana
crua). O segundo é `text/trama.py`: rebinarizar o recorte. Na página inteira o papel branco
domina e o Otsu global corta abaixo da trama, que vira tinta e gruda em tudo. Dentro do painel o
papel some da conta e sobram duas populações — trama e texto —, e ali o Otsu corta **acima** da
trama. Medido lá no painel da página 18: 71 componentes com tamanho de caractere onde antes havia
zero.

**A peneira que impede o diagrama de virar 32 boxes de peça é do domínio, e tem margem larga:
tabuleiro é quadrado.** Medido lá, os diagramas medem 578×579, 579×579, 580×584 — proporção 1,00
a 1,01; o painel de pontuação mede 1049×390, proporção 2,69. A cobertura por células diria o
mesmo com margem estreita e por isso não é usada.

**A tolerância não é "mais largo que alto".** Uma tabela pode ser mais alta que larga — a tabela
de finais da página 236 do Nunn mede 1342×1099, razão 1,22 — e a primeira versão da régua, que só
olhava para um lado, fazia as 276 caixas de dentro dela **sumirem sem aviso**.

**Critério de aceite.**

- o painel sintético com trama devolve os caracteres de dentro;
- o tabuleiro não é aberto: proporção entre 0,95 e 1,05 é recusada, nos dois eixos;
- a tabela de razão 1,22 **é** aberta, e o teste cita o caso que a motivou.

**Testes.** `test_o_painel_com_trama_devolve_os_caracteres`;
`test_o_tabuleiro_nao_e_aberto`; `test_a_tabela_mais_alta_que_larga_e_aberta`.

**Sonda.** `simbolo:chess_diagram_ocr.text.trama:candidatos`.

---

## S-197 · O texto girado, que hoje sairia errado em silêncio ✅ implementada (2026-08-23)

**Problema.** Livros põem rótulos girados ao lado do diagrama — *"Analysis diagram"*. Este é o
caso mais perigoso da fase, porque o programa **não falha: ele devolve outra letra, com confiança
de leitura normal**. Medido lá em 10.606 caracteres rotulados: o classificador acerta 94,2% no
recorte de pé e **8,4%** no mesmo recorte girado 90°.

**Solução.** `text/vertical.py`. O ângulo é do **texto**, não do recorte, e segue a convenção do
PDF: 0 normal, 90 o texto sobe, 270 o texto desce. Girar por múltiplo de 90° é **transposição**,
não reamostragem — medido lá, os mesmos 9.987 caracteres que o modelo acerta de pé voltam a ser
acertados depois de ir e voltar.

**A geometria propõe, o classificador dispõe.** A geometria sozinha não distingue um rótulo
girado de uma coluna de primeiras letras de parágrafo: as duas são caixas empilhadas com a mesma
faixa de x. `candidatos` só recolhe pilhas plausíveis (mesma faixa de x, vãos de espaço entre
letras, alta e estreita, e sem vizinha ao lado), e quem decide o ângulo é o classificador, pela
confiança **média da pilha inteira**. Medido lá em 1.312 linhas simuladas nos quatro ângulos, o
argmax da média bate com o ângulo impresso em 99,7%.

**Sem árbitro este módulo não faz nada**, e isso não é cautela: marcar ângulo por geometria pura
mexeria em texto normal para acertar o raro.

**180° não é candidato.** Livro impresso não traz linha de cabeça para baixo, e cada ângulo a
mais é uma chance a mais de virar uma pilha curta pelo lado errado. A medição mostra que o
classificador *saberia* separar 180°; ele não entra por não existir no material.

> **O árbitro é injetado, e não importado (2026-08-22).** `decidir_angulo` recebe um chamável
> que devolve confiança por recorte. Assim este módulo não depende de `torch` para propor
> geometria, e a suíte pode travar o árbitro para afirmar *por que* uma pilha foi aceita. É o que
> permitiu entregar o item sem os pesos de 292 classes.

**Critério de aceite.**

- ✅ `endireitar` é transposição, e a volta fecha byte a byte nos dois ângulos;
- ✅ o recorte devolvido é contíguo (`np.rot90` devolve vista de passo negativo, e o OpenCV a
  recusa adiante no caminho);
- ✅ com o árbitro ausente, **nenhuma** pilha muda de ângulo;
- ✅ numa página só de prosa, zero pilhas propostas — a coluna de primeiras letras é recusada
  pelo vizinho lateral;
- ✅ o mínimo de cinco caixas está declarado com o motivo medido;
- ✅ **a tabela dos quatro ângulos**, refeita neste acervo: `cvoff-texto-vertical`,
  `docs/metrics/texto_vertical.json`.

**Testes.** `test_endireitar_e_transposicao_e_a_volta_fecha`; `test_sem_arbitro_nada_muda`;
`test_a_coluna_de_primeiras_letras_nao_e_pilha`; `test_a_pilha_curta_demais_nao_e_candidata`;
`test_a_folga_precisa_superar_a_margem`; `test_180_nao_e_candidato`.

### A tabela dos quatro ângulos, medida aqui em 2026-08-23

`cvoff-texto-vertical`, 534 linhas de 30 livros, com o classificador de 314 classes que a S-204
treinou. **A linha é girada por transposição** (`vertical.girar`, o avesso de `endireitar`): o
acervo é de texto de pé, e anotar rótulos girados à mão daria dezenas de amostras para uma régua
que separa 94,2% de 8,4%. A ida e a volta fecham byte a byte, então a resposta certa vem ao lado
da leitura sem custar anotação.

**A confiança média, lendo cada linha nos quatro ângulos:**

    lido a       0°       90°      180°     270°
              0,8572   0,5061   0,6992   0,5143

**A matriz é circulante, e isso não é coincidência: é a prova de que a simulação está certa.**
Girar a página permuta as leituras e nada mais, então a fileira do texto impresso a 90 é a mesma
deslocada de uma casa. A consequência prática é que **as quatro fileiras dão o mesmo acerto por
construção** -- há um número, não quatro:

    argmax da média = 0,9363   (500 de 534 linhas)

**São 93,6%, e lá foram 99,7%.** A distância não é do método: é o acervo. Lá as 1.312 linhas
simuladas vinham de páginas rotuladas; aqui elas vêm de 30 livros, com scan de 1870, meio-tom e
fonte de diagrama no meio da prosa.

**O 180° é o segundo colocado, e é ele que explica os erros.** Lido de cabeça para baixo o modelo
ainda dá 0,6992 -- bem acima dos 0,51 de um giro de 90° --, porque o recorte mantém a proporção e
metade dos glifos de texto tem parente ambíguo nessa volta.

### A régua da produção, que é outra e mede o que o programa faz

`decidir_angulo` só tenta 0, 90 e 270, e exige que o vencedor supere o de pé por `MARGEM` (0,05).

| impresso | o que se espera | acerto | o que o erro é |
|---|---|---:|---|
| 0° | não mexer | 0,9775 | 12 linhas de 534 giradas à toa |
| 90° | marcar 90 | 0,9195 | 43 pilhas não reconhecidas |
| 180° | não mexer (não é candidato) | 0,9176 | 44 lidas como 90 ou 270 |
| 270° | marcar 270 | 0,9326 | 36 pilhas não reconhecidas |

**A folga é o que decide, e ela é folgada:** mediana de **+0,3761** a 90 e **+0,3881** a 270,
contra a margem de 0,05 -- e **−0,3537** no texto de pé, que é o controle. A margem herdada não
precisa ser remedida para este modelo, e a razão de ela sobreviver à calibração da S-205 é que a
distância entre acertar e errar o ângulo é sete vezes maior que ela.

> **Uma leitura preliminar de uma única linha disse o contrário, e fica registrada.** Na corrida
> de fumaça, uma linha só, a folga foi de 0,024 -- abaixo da margem -- e a conclusão apressada
> seria que a S-197 é um no-op em produção. Com 534 linhas ela é o oposto: 502 e 508 das 534
> passam da margem a 90 e a 270. Uma amostra é uma anedota, e o item mede porque anedota não
> decide.

**O que a linha do 180° custa, dita por extenso:** 44 linhas de 534 (8,2%) impressas de cabeça
para baixo sairiam marcadas como 90 ou 270 e seriam lidas erradas. Livro impresso não traz linha
assim, que é o motivo declarado de 180 não ser candidato -- a fileira existe para que o preço
dessa decisão esteja escrito em vez de suposto.

**Sonda.** `simbolo:chess_diagram_ocr.text.vertical:candidatos`,
`simbolo:chess_diagram_ocr.text.vertical:recorte_de_pe`, `metrica:texto_vertical`.

---

## S-198 · O box que engoliu duas linhas ✅ implementada (2026-08-23)

**Problema.** O descendente de um `g` ou `p` encosta na linha de baixo, os dois contornos viram
um, e um caractere some. Medido lá, o conserto valeu +0,3 de F1 nas 10 páginas rotuladas — e o
ganho é do corte de linha, não do modelo.

**Solução.** `text/duas_linhas.py`: o box cuja altura é muito maior que a escala do caractere é
candidato a partir. O corte sai do **vale** do perfil horizontal de tinta, e quando não há vale
— porque o descendente preenche a faixa — o corte vai para a fronteira que a banda da linha
(S-187) já conhece.

O árbitro confirma, como na S-186: a confiança média dos dois pedaços contra a do inteiro.

**A régua é uma probabilidade, e por isso ela não atravessa uma calibração.** É o achado da F69
de lá, e ele vale como aviso: se a temperatura do modelo mudar, o limiar do corte precisa ser
remedido. Fica travado por um teste que compara o limiar registrado com a temperatura do
metadado.

> **O item ganhou uma segunda metade, e ela veio da medição da S-185 (2026-08-22).** Além de
> partir o box alto demais, `duas_linhas` agora **descarta a linha que é só fragmento**: a faixa
> dilatada da `ocr_caption` (o `radius_pt`) encosta na linha de cima, e os pedaços de descendente
> que entram custam 8 pontos de CER (0,14 -> 0,22 na mesma página). `quebrar_em_linhas` já os
> separava em linha à parte corretamente; o que faltava era alguém dizer que aquela linha é
> fragmento.

**Critério de aceite.**

- ✅ o box sintético que cobre duas linhas é partido em dois, e os pedaços cobrem o original;
- ✅ **sem árbitro não corta** — a mesma regra da S-197;
- ✅ sem vale no perfil, o corte usa a fronteira da banda; sem fronteira, a caixa fica inteira;
- ✅ a linha que é só fragmento é descartada, e a linha com um ponto final não é;
- ✅ **a tabela do ganho**, refeita aqui: `cvoff-texto-duas-linhas`,
  `docs/metrics/texto_duas_linhas.json`. O corte saiu **negativo**, e é isso que ele vale;
- ✅ o teste que amarra o limiar à temperatura do modelo publicado
  (`LimiarEcalibracaoTests`, em `tests/test_text_duas_linhas.py`).

**Testes.** `test_sem_arbitro_nao_corta`; `test_o_ganho_precisa_superar_a_margem`;
`test_sem_vale_a_fronteira_da_banda_decide`; `test_o_minimo_colado_na_borda_nao_e_vale`;
`test_a_linha_de_texto_com_um_ponto_nao_e_fragmento`.

### O ganho, medido aqui em 2026-08-23 — e um dos dois passos não paga

`cvoff-texto-duas-linhas`, **155 faixas de 11 livros**, cada faixa sendo uma linha da camada de
texto dilatada em **2 pt** -- que é a dilatação com que a S-185 mediu o defeito (0,14 -> 0,22).
Três braços, cada um acrescentando um passo ao anterior:

    cru                 CER 0,2725     o GlyphRecognizer como ele era
    descarte            CER 0,2248     -> ganho de 0,0477
    descarte e corte    CER 0,2337     -> o corte custa 0,0089

**O descarte entrou no caminho de leitura; o corte não.** `descartar_fragmentos` está em
`GlyphRecognizer.read` desde esta medição, com o número no comentário. `separar` continua
implementado, travado por teste e **não chamado**: ele disparou em 15 das 155 faixas, partiu 18
caixas e piorou o CER. O item herdou de lá um +0,3 de F1; aqui ele não paga, e a diferença fica
registrada em vez de suposta.

> **O achado que muda a leitura da própria Fase 26.** A primeira corrida deu CER **0,8644**, e a
> causa não era o motor: **metade deste acervo tem camada de texto gerada por OCR**, e medir CER
> contra ela é comparar dois palpites. `camada_de_ocr` (da S-216) nomeia 20 livros -- `paper
> capture`, `fonte invisível (Tesseract e afins)`, `imagem de página inteira com texto por cima`
> --, e eles saem da medição listados um a um no relatório.
>
> **O `AAGAARD` é um deles, e ele é a página 21 da medição da Fase 26.** O CER 0,14 que este
> plano cita como linha de base da segmentação foi medido contra uma camada do Adobe Paper
> Capture. Isso não invalida a comparação *relativa* que ela fez -- os três números de lá
> saíram contra a mesma referência --, mas o 0,14 **não é erro contra a verdade**, e nenhum
> número deste projeto deve ser lido como se fosse. É a mesma circularidade que a S-183 recusou
> quando decidiu que a legenda de referência seria transcrita à mão.

**Sonda.** `simbolo:chess_diagram_ocr.text.duas_linhas:partir`, `metrica:texto_duas_linhas`.

---

## S-199 · A tabela sai como tabela ✅ implementada (2026-08-22)

**Problema.** A tabela de finais da página 236 do Nunn mede 1342×1099 e tem moldura fechada. Com
`RETR_EXTERNAL`, as 276 caixas de caractere de dentro dela **não saíam fora de ordem: não saíam.**
É a mesma classe de falha da tarja e da trama, e é a que menos se percebe, porque uma tabela
ausente parece uma página sem tabela.

**Solução.** Duas partes, e a ordem importa:

1. **Abrir o bloco** — é a S-196, com a tolerância de proporção corrigida (a razão 1,22 desta
   tabela é o caso que obrigou a correção).
2. **Ler a grade da imagem**, e não por folga arbitrária: as linhas da moldura dão as fronteiras
   de célula. **Dentro da célula não se lê como se lê a página** — a célula tem sua própria
   escala, sua própria margem, e a ordem de leitura é por célula, não por banda horizontal da
   página inteira.

A saída é uma estrutura de tabela (linhas × colunas × conteúdo), e não um bloco de texto com
espaços. Quem exporta decide como desenhá-la.

**Critério de aceite.**

- a tabela sintética 3×5 sai como 3×5, com o conteúdo na célula certa;
- uma célula vazia sai vazia, e não desloca as seguintes;
- a tabela sem moldura (só com alinhamento) **não** é reconhecida como tabela, e isso está
  declarado como limite conhecido em vez de ser tratado por heurística frágil.

**Testes.** `test_a_tabela_sai_com_a_forma_certa`;
`test_a_celula_vazia_nao_desloca_as_seguintes`;
`test_a_tabela_sem_moldura_e_limite_conhecido`.

**Sonda.** `simbolo:chess_diagram_ocr.text.tabela:ler`.

---

# Fase 29 — A base de 608 mil

> A fase de maior risco do plano. Ela **não depende da Fase 26** e deve começar assim que a
> fronteira da Fase 25 existir: o inventário é trabalho de disco e de decisão humana, e nada o
> bloqueia.
>
> A ordem é: inventariar → separar por procedência → deduplicar → **partir por livro** → treinar
> → calibrar → medir honesto. Nenhum passo pode pular a frente do anterior.

> **A base chegou em 2026-08-23, e o número prometido estava errado para menos.** São
> **608.407 recortes** em **314 pastas** de classe, 0,61 GB, e não "cerca de 700 mil" — a
> contagem de 608.408 arquivos inclui um `.learner_cache.npz` que não é recorte. A varredura
> mediu três coisas que reordenam o resto desta fase, e as três estão registradas nos itens
> abaixo:
>
> | o que se mediu | número | onde isso decide |
> |---|---|---|
> | recortes | 608.407 em 314 classes | — |
> | **imagens distintas** | **178.420** | 70,7% da base é cópia byte a byte (S-202) |
> | mesma imagem sob dois rótulos | 83 grupos, 1.557 recortes | rótulo que se contradiz (S-202) |
> | registro de livro ou página | **nenhum** | o split por livro da S-203 não é executável |
>
> **A consequência mais dura é a última linha.** Os recortes se chamam
> `00001b60-272a-46f2-9dbf-044fe779e336.png` — UUID puro, sem sidecar, sem índice em lugar
> nenhum. Sem livro não há o teste do "livro novo", e nenhum número desta fase mede
> generalização de fonte enquanto a procedência não for recuperada na origem. O `mtime` não
> substitui: 70% dos arquivos carregam 2026-02-16, de uma migração que reescreveu todos.

## S-200 · O inventário, antes do primeiro treino ✅ implementada (2026-08-23)

**Problema.** O material prometido é *"as imagens de todas as classes de caracteres já
verificadas manualmente, cerca de 700 mil"*. O `docs/SPEC.md` do PyBoxEditor, §5.2, descreve duas
bases que somam **321.450** imagens:

    training_data/     103 classes, 128.850 imagens   — a base de treino
    training_data_2/    68 classes, 192.600 imagens   — rótulos suspeitos de serem do modelo

**700 mil é mais que o dobro das duas juntas.** A pergunta que decide esta fase inteira é *o que
são as outras ~380 mil, e a `training_data_2` está dentro?* Treinar antes de responder produz um
número alto sobre uma base que se realimenta do próprio erro.

> **Parte da pergunta foi respondida em 2026-08-23.** A `training_data/` desta máquina tem
> **608.407 recortes em 314 classes** — não 103, e não 700 mil. Ela é maior que as duas bases de
> lá somadas, então **absorveu a `training_data_2`** ou o material que a originou; o que a
> varredura não pode dizer é *quais* recortes vieram de onde, porque nenhum deles carrega essa
> marca.
>
> E a suspeita de rótulo-de-modelo que a S-201 herda **não se confirma pelo sinal que a spec de
> lá propôs**: naquele argumento, `digit_1` acima de `lower_e` seria a assinatura do
> classificador confundindo `l`, `i` e `I`. Aqui `lower_a` (63.055) e `lower_e` (33.855) estão os
> dois acima de `digit_1` (26.792), que é a ordem que se espera de texto de livro. Isso **não**
> absolve a base: o sinal era indício e não prova, e a resposta continua dependendo de uma
> procedência que esta pasta não tem.
>
> O que o inventário ainda deve, e por isso o item continua planejado: o `cvoff-texto-inventario`,
> o manifesto em `docs/metrics/` e o achado nomeado por classe. A varredura que existe hoje é a de
> `text/dataset.py`, feita para alimentar o treino — ela conta, nomeia a pasta que não decodifica
> e conta o PNG ilegível, mas não grava manifesto.

Há um segundo sinal que o inventário tem de conferir cedo, e ele é específico do Windows: a
classe `lower_ä` da base de lá ficou **vazia** porque `cv2.imwrite` devolve `False` em caminho
não-ASCII, sem levantar erro. Uma classe vazia num inventário de 700 mil passa despercebida.

**Solução.** `cvoff-texto-inventario`, que varre a pasta e grava um manifesto — sem mover, sem
apagar, sem treinar. Por classe: contagem, tamanho em disco, dimensões distintas, PNGs
ilegíveis, e o caractere para o qual o nome da pasta decodifica (via S-180, `strict=True`).

**Regra que vem de lá e vale como lei aqui:** nunca usar `cv2.imread`/`cv2.imwrite` como teste de
integridade de arquivo. No Windows eles falham em caminho não-ASCII e devolvem `None`/`False`,
indistinguível de "arquivo corrompido" — e a primeira versão da migração de lá caiu nisso e
apagou PNGs válidos. Usar `open()` + `cv2.imdecode`, e **mover para quarentena, nunca apagar**.

**Critério de aceite.**

- ✅ o manifesto sai em `docs/metrics/texto_inventario_<data>.json`, com o total e a contagem por
  classe;
- ✅ classe vazia, classe abaixo do mínimo e nome de pasta que não decodifica aparecem como
  **achados nomeados**, não como linhas iguais às outras;
- ✅ o comando **não escreve nada** dentro da pasta inventariada, travado por teste;
- ✅ PNG ilegível é contado e listado, e o comando termina com sucesso mesmo assim.

**Testes.** `test_o_inventario_nao_escreve_na_pasta`;
`test_classe_vazia_vira_achado_nomeado`;
`test_png_ilegivel_e_contado_e_nao_derruba`;
`test_a_leitura_usa_imdecode_e_nao_imread`.

### O que o manifesto fixou, em 2026-08-23

`cvoff-texto-inventario`, sobre a pasta inteira. **A pasta está limpa nas três coisas que o item
existia para pegar** -- e isso é um resultado, não uma anticlímax: são exatamente os três defeitos
que passam despercebidos entre 314 linhas iguais.

    recortes                                607.713 em 314 pastas
    tamanho em disco                        0,44 GB
    imagens distintas (somadas por classe)  178.370
    classes vazias                          0
    pastas cujo nome não decodifica         0
    PNGs ilegíveis                          0
    classes com menos de 3 recortes         52

**O número que estava divergindo tem explicação, e agora tem manifesto.** O `ROADMAP_TEXTO` cita
178.420 imagens distintas e o relatório de treino gravou 178.370. Nenhum dos dois está errado: os
694 recortes que a S-202 moveu para `data/quarentena_texto/` levaram junto **50 grupos inteiros**,
e a diferença é essa. O mesmo vale para o total -- 608.407 antes da quarentena, 607.713 depois.
Enquanto não havia manifesto, a única forma de saber isso era refazer a conta e lembrar de qual
era qual.

**As 52 classes abaixo de três recortes são o insumo de uma decisão da S-204**, e não um defeito:
são elas que produzem as 58 classes sem uma única amostra no teste. `ligature_a8`, `ligature_ba`,
`ligature_dx`, `ligature_ffl` e outras 12 têm **um** recorte. Cortá-las com `--minimo 3` ou
mantê-las declarando `n=0` é a escolha que o item de treino tem de fazer com o número à vista.

**O tamanho em disco é 0,44 GB e não 0,61 GB**, que é o que o roadmap diz. A diferença é o que se
mede: aqui é a soma de `st_size` dos PNGs; 0,61 GB é o que o sistema de arquivos ocupa com eles,
que numa base de 607 mil arquivos pequenos infla pelo tamanho do bloco.

**Sonda.** `simbolo:chess_diagram_ocr.cli.texto_inventario:main`,
`metrica:texto_inventario`.

---

## S-201 · A procedência: humano, modelo, ou não se sabe ◐ parcial (2026-08-23)

**Problema.** A avaliação de 2026-08-18 deste projeto abriu com quatro achados, e o primeiro é
que **a verdade de referência é a leitura do próprio modelo**. Do outro lado, a spec do
PyBoxEditor descreve a `training_data_2` com a mesma suspeita, e o argumento dela é bom o
bastante para ser repetido:

> A distribuição reforça: a classe maior é `digit_1` (16.962), acima de `lower_e` (16.090) — em
> texto de livro o `e` domina com folga. Um excesso de `1` é a assinatura do classificador
> confundindo `l`, `i` e `I`.

Este projeto já tem a máquina para isto: `provenance.py`, `audit.py` e `data/quarantine.csv`
existem desde a S-19. O que falta é aplicá-la a caractere.

**Solução.** Cada amostra carrega uma procedência em três valores:

| valor | o que significa | onde pode entrar |
|---|---|---|
| `humano` | um humano olhou este recorte e disse qual é o caractere | treino, validação e **teste** |
| `modelo` | o rótulo é o palpite de um classificador | treino, com peso, e nunca teste |
| `desconhecida` | não há registro de quem rotulou | treino, e **nunca** validação nem teste |

**Uma amostra sem procedência não é recusada — ela é marcada.** Recusar 380 mil imagens porque
ninguém sabe de onde vieram desperdiça o ativo; deixá-las entrar no teste torna o número final
sem significado. A regra acima é o meio-termo, e ela é a mesma que este projeto já aplica a
diagramas.

E o diagnóstico automático da distribuição entra junto: se `digit_1` superar `lower_e` num
conjunto que se declara humano, o comando **avisa** — não bloqueia, avisa, com o número ao lado.

**Critério de aceite.**

- ✅ o esquema de procedência está no manifesto e é obrigatório em toda amostra;
- ✅ amostra `modelo` ou `desconhecida` no split de teste faz o `cvoff-audit` falhar;
- ✅ o aviso de distribuição dispara na base sintética em que `digit_1` domina;
- ⬜ a decisão sobre a `training_data_2` está **registrada com data e com quem decidiu**, e o
  documento diz qual foi. **É o que mantém o item `◐`**, e ela não é nossa: o campo
  `decisao_sobre_a_origem` de `docs/metrics/texto_procedencia_<data>.json` existe com
  `resposta: null` para que a ausência tenha lugar em vez de sumir.

**Testes.** `test_amostra_sem_procedencia_fica_fora_do_teste`;
`test_o_aviso_de_distribuicao_dispara`;
`test_o_audit_falha_com_rotulo_de_modelo_no_teste`.

### O que foi entregue em 2026-08-23, e o que continua faltando

**O contrato do arquivo, escrito antes de o arquivo existir.** `text/procedencia.py` define
`data/texto_procedencia.csv` -- `uuid,livro,pagina,procedencia,rotulado_em` --, os três valores e
a regra que eles carregam. Definir o formato depois que a origem responder seria convidar a duas
migrações; definir agora dá alvo ao trabalho que só o `PyBoxEditor_Tkinter` pode fazer.

**Célula vazia é permitida e não é o mesmo que a linha não existir.** A primeira é uma ausência
declarada, a segunda é uma ausência descoberta -- e as duas caem na mesma regra (treino sim,
medição não), mas aparecem separadas no relatório.

**A regra entra no split por uma máscara, e não por um filtro.** `split_por_grupo` e
`split_por_livro` recebem `medivel`, e o **grupo** que contiver uma amostra não-medível fica
inteiro no treino. Filtrar amostra a amostra quebraria a atomicidade do grupo, que é a garantia
mais forte das duas.

**O `cvoff-audit` passou a cobrar, e ele lê um relatório porque o split não existe em disco.**
`cvoff-texto-train --so-split` grava `docs/metrics/texto_vazamento.json` em um minuto a partir do
cache; a auditoria reprova rótulo de `modelo` no teste sempre, e rótulo `desconhecido` no teste
**quando há registro no disco**.

> **Sem registro nenhum, a regra esvaziaria a medição -- e o caminho escolhido está aqui por
> extenso.** Hoje as 607.713 amostras são `desconhecida`, e aplicar a regra ao pé da letra
> deixaria validação e teste vazios: não haveria número nenhum. Um comando que não mede não é
> mais honesto que um que mede com ressalva. Então o caminho sem registro **mede assim mesmo** e
> grava a ressalva no relatório de vazamento e no de treino, no campo que é lido junto com o
> número. No dia em que `data/texto_procedencia.csv` existir, a regra passa a valer sozinha, e
> `--desconhecida-no-teste` é o único jeito de desligá-la -- deixando rastro no relatório.
>
> **E o sinal que a spec de lá propôs não dispara nesta base.** `aviso_de_distribuicao` compara
> `digit_1` com `lower_e`, que é a assinatura do classificador confundindo `l`, `i` e `I`: aqui
> `lower_a` (63.055) e `lower_e` (33.855) estão os dois acima de `digit_1` (26.792). Indício de
> que a base não é dominada por rótulo de modelo -- **não é prova**, e a pergunta continua sendo
> do dono dos dados.

**A sonda ganhou uma terceira entrada, e ela é o dado e não o código:**
`arquivo:data/texto_procedencia.csv`. Sem ela o item diria `implementada` com a metade que
importa em aberto -- é a mesma correção que a S-182 recebeu em 2026-08-23, e pelo mesmo motivo.

**Sonda.** `simbolo:chess_diagram_ocr.text.dataset:procedencia_de`,
`metrica:texto_procedencia`, `arquivo:data/texto_procedencia.csv`.

---

## S-202 · A duplicata exata, e a quase-duplicata ✅ implementada (2026-08-23)

> **Um critério de aceite foi cumprido de outra forma, e a troca fica registrada.** A versão
> escrita antes de implementar dizia: *"a duplicata exata é achada por hash e **movida para
> quarentena**"*. As 429.987 cópias **não** foram movidas, e a razão é que mover deixou de ser
> necessário quando o agrupamento passou a existir: `dataset.varrer` dá um grupo por hash,
> `split_por_grupo` o trava atômico, e `representantes` faz val e teste contarem uma imagem por
> grupo. O propósito do critério — *"não ensinam nada ao modelo, inflam a contagem da classe e —
> o pior — atravessam o split"* — está inteiro, e o disco não foi mexido.
>
> **Agrupar é estritamente melhor que mover, e o argumento não é de gosto.** Mover 429.987
> arquivos é uma operação grande e assimétrica: a volta depende de um manifesto sobreviver.
> Agrupar não toca em nada, é recalculado do zero em 10 segundos, e deixa a base como o usuário
> a entregou. A quarentena continua existindo para o caso em que ela é a única saída — o rótulo
> contraditório, que **não** dá para resolver agrupando, porque as duas leituras não podem
> coexistir num grupo.

**Problema.** Em PDF digital o mesmo glifo sai byte a byte igual toda vez. Uma base coletada de
livros digitais enche de cópias: 300 miniaturas que são a mesma miniatura não ensinam nada ao
modelo, inflam a contagem da classe e — o pior — **atravessam o split**, aparecendo no treino e
no teste ao mesmo tempo.

**Solução.** Duas passadas, e são problemas diferentes:

1. **Duplicata exata**, por hash do conteúdo do PNG. Barata e decisiva. A cópia é removida da
   contagem, mas o arquivo vai para quarentena, não para o lixo.
2. **Quase-duplicata**, por descritor de imagem. O critério de lá está medido: descritor de lado
   24 (não 32 — 32 não muda a precisão e custa 78% mais memória), com proporção e altura entrando
   por fora, porque um `.` e um `O` preenchem o mesmo quadrado depois do redimensionamento. Com
   limiar 0,20 e **a mesma leitura** exigida junto, a precisão é 99,29%.

**A precisão não passa de ~99,3%, e isso não é limiar que resolva.** O que sobra são homóglifos
de verdade — `0`×`o`, `9`×`g`, `1`×`i`, `P`×`p` — em que as duas imagens *são* quase iguais.
Consequência de projeto: **a quase-duplicata nunca apaga nada sozinha.** Ela alimenta o split
(S-203), agrupando prováveis irmãs para que caiam do mesmo lado, e alimenta a revisão (S-213).

**Critério de aceite.**

- a duplicata exata é achada por hash e movida para quarentena, nunca apagada;
- o descritor tem lado 24, e o teste que trava isso diz por quê;
- a quase-duplicata **não** remove amostra: o teste prova que a contagem da classe não muda;
- o relatório diz quantas cópias exatas e quantos grupos de quase-duplicatas foram achados.

**Testes.** `test_a_duplicata_exata_vai_para_quarentena_e_nao_para_o_lixo`;
`test_a_quase_duplicata_nao_remove_amostra`;
`test_o_descritor_tem_lado_24`.

**Sonda.** `simbolo:chess_diagram_ocr.text.conflitos:achar`,
`simbolo:chess_diagram_ocr.text.dedupe:agrupar`,
`metrica:texto_dedupe`.

> **Metade deste item foi feita em 2026-08-23, dentro da S-204, e a metade feita mudou o
> tamanho do problema.** A duplicata exata está em `text/dataset.py`: a varredura já lia cada
> arquivo para decodificá-lo, e passar os mesmos bytes por um SHA-256 sai de graça. O resultado
> não é uma nota de rodapé —
>
>     608.407 recortes  →  178.420 imagens distintas  →  429.987 são cópia (70,7%)
>
> — e por classe é pior onde mais dói: `lower_a` tem 63.055 recortes e **5.683** imagens,
> `lower_h` 21.662 e 1.812. Um split aleatório sobre isso põe 7 de cada 10 recortes do teste
> dentro do treino.
>
> **Achado que a spec deste item não previa: 83 grupos estão arquivados sob dois rótulos ao mesmo
> tempo** — 1.557 recortes, a mesma imagem byte a byte em duas pastas. Os pares são a lista de
> homóglifos que se espera do material: `digit_1`×`lower_l` (13 grupos), `lower_v`×`upper_V` (7),
> `digit_0`×`lower_o` (6), `sym_39`×`sym_44` (5, a apóstrofe e a vírgula). Isto **não é
> duplicata, é rótulo que se contradiz**: as duas não podem estar certas, e nenhum modelo pode
> acertar as duas. É a mesma família do `sym_f7` da S-180 — e lá o conserto do rótulo fez o
> modelo já treinado acertar 127 de 127 sem retreinar.

### Os 83 rótulos contraditórios, julgados um a um (2026-08-23)

`cvoff-texto-conflitos`, `text/conflitos.py`, e o julgamento em `data/texto_conflitos.json` —
que é **trabalho humano e é versionado**, com o motivo escrito em cada linha. O comando acha por
hash, desenha os glifos em disputa numa folha de contato, e move o perdedor para
`data/quarentena_texto/` com um manifesto que `--desfazer` lê de volta. **Nada é apagado**, pela
mesma lei da S-200.

    83 grupos julgados
    ├── 33 decididos      o desenho responde: 30 com confiança alta, 3 com média
    └── 50 indecidíveis   o desenho não responde, e não é falta de esforço

    694 recortes movidos (0,11% da base): 66 por rótulo errado, 628 por indecidíveis

**Os 50 indecidíveis são o achado mais duro, e não têm conserto nesta base.** `v` e `V` têm o
*mesmo desenho*; o que os separa é a altura relativa à linha, que o recorte apagou. Foi medido
antes de desistir: os PNGs foram gravados **em 32x32 já na origem**, então nem o tamanho nativo
sobrou para desempatar — o `p10` e o `p90` da altura de `lower_v` e de `upper_V` são 32 e 32.
A mesma imagem **é** as duas coisas, e só o contexto da linha diria qual. Os 50 se distribuem
assim: **25** pares de caixa (`v`/`V`, `s`/`S`, `c`/`C`, `w`/`W`, `x`/`X`, `p`/`P`, `y`/`Y`),
**11** de `1`/`l`/`I`, **8** de `0`/`o`/`O`, **5** de apóstrofe contra vírgula — que diferem só
pela altura na linha, exatamente como os de caixa — e **1** borrão em que não há glifo legível
nenhum.

**A regra da maioria foi tentada e a base a desmente.** A ficha 15 tem **30** recortes em
`lower_f` contra **2** em `ligature_ft`, e o desenho é um "ft" de duas letras: a maioria é que
está errada. Aconteceu quatro vezes nos 83 (fichas 15, 56, 70 e 75). Uma regra automática teria
consagrado o erro em cada uma delas com a confiança de 15 contra 1 — e é por isso que
`text/conflitos.py` **não decide nada** e obedece a um arquivo que um humano escreveu.

Onde o desenho responde, ele responde bem: a coroa da ficha 13 é `♔` e não a letra `K`; o `B` da
ficha 1 é a letra e não o bispo, apesar de 416 contra 1; as fichas 71 e 72 são a ligadura `rv` e
não `N`; a 70 é `z` e não `2`, porque o `2` tem topo curvo e volta.

**O que continua devendo, e é o que mantém o item aberto:** a quase-duplicata. O descritor de
lado 24 com limiar 0,20 não foi implementado, e é ele que pega o mesmo `e` da mesma fonte em
páginas diferentes — que difere em um pixel de antialiasing e por isso escapa do hash. Nesta
base, com 70,7% de cópia *exata*, é razoável esperar que a quase-duplicata ainda seja grande;
enquanto ela não for medida, o número do teste é conservador mas não é honesto.

**Testes.** `test_a_maioria_perde_quando_a_decisao_diz_que_perde`;
`test_o_indecidivel_sai_inteiro`; `test_nada_e_apagado_e_o_desfazer_devolve_tudo`;
`test_o_grupo_que_mudou_no_disco_nao_e_aplicado`;
`test_as_decisoes_do_repositorio_dizem_todas_por_que`.

### O que o conserto mudou no modelo, e o que ele não mudou

Retreino com a mesma semente e os mesmos hiperparâmetros
(`docs/metrics/texto_treino_20260823_s202.json` contra `_s204.json`):

    teste macro       0,9754  →  0,9741      (-0,0013)
    teste acurácia    0,9925  →  0,9928      (+0,0003)
    temperatura       1,8622  →  1,7320
    grupos em conflito    83  →       0

**O número de cima não melhorou, e dizer isso é o item.** Mais: as duas corridas **não** partiram
o mesmo conjunto — a base mudou, então o split mudou (17.840 contra 17.844 imagens no teste), e
elas não são comparação controlada. E a diferença de −0,0013 vale exatamente **um acerto na menor
classe que vota na macro** (0,00130): 62 das 154 classes que votam têm menos de 20 amostras no
teste, e nessa escala a macro balança com uma amostra.

**O que se move de verdade é a lista de classes que o conserto tocou**, e ela se move na direção
prevista:

| classe | antes | depois | n no teste |
|---|---|---|---|
| `ligature_ft` (ficha 15) | 0,7500 | **1,0000** | 4 |
| `sym_44` `,` | 0,8276 | **1,0000** | 29 |
| `lower_z` (ficha 70) | 0,8333 | **1,0000** | 6 |
| `digit_0` | 0,7812 | **0,8750** | 32 |
| `sym_59` `;` | 0,9167 | **1,0000** | 12 |
| `lower_l` | 0,9167 | **0,9752** | 121 |
| `lower_y` | 0,9545 | **1,0000** | 44 |
| `upper_I` | 0,8400 | **0,8800** | 25 |
| `sym_39` `'` | 0,5714 | **0,1429** | 7 |

`lower_l` é a linha que mais importa, porque tem 121 amostras: +0,0585 não é sorteio. As demais
que subiram são as classes que estavam sendo ensinadas com o rótulo trocado — `ligature_ft` é a
ficha 15, e `lower_z` é a 70.

**E `sym_39` desabou, o que é um achado e não um acidente.** Os cinco grupos em disputa entre
apóstrofe e vírgula saíram como indecidíveis, e o que sobrou ensina o modelo a ler aquele desenho
como vírgula: `sym_44` foi a 1,0000 e `sym_39` caiu a 0,1429. **É a resposta certa para a
pergunta errada.** Nestes recortes, apóstrofe e vírgula *são o mesmo desenho* — o que os separa é
a altura na linha, que o recorte não guarda. Antes o modelo chutava entre as duas com o ruído da
contradição; agora ele responde a mais provável, coerentemente. Só a S-211, que devolve a posição
do glifo na linha, pode fazer melhor que isso; enquanto ela não existir, `sym_39` é um limite
conhecido e não um defeito a caçar.

**Conclusão honesta:** o conserto não comprou acurácia. Ele comprou uma base que não se
contradiz, quatro classes que estavam ensinadas errado, e um `sym_39` cujo erro agora tem
explicação em vez de mistério.

### A quase-duplicata: o limiar de lá não serviu, e o daqui foi medido (2026-08-23)

`text/dedupe.py`. O descritor de **lado 24** veio de lá e fica: 32² = 1024 contra 24² = 576 é
exatamente o 78% de memória a mais que a spec de origem cita, sem ganho de precisão medido — e
essa aritmética conferir é o que dá confiança de que o descritor de lá **é** a imagem
redimensionada, e não outra coisa.

**O limiar 0,20 não fica, e recusá-lo é a regra deste projeto aplicada a si mesma.** Ele foi
medido noutra métrica, que não veio junto no porte. Aqui, com distância RMS em [0, 1] sobre o
descritor, 0,20 casa **12% a 24% de todos os pares** de uma classe — juntaria a classe inteira
num grupo só. O que foi medido nesta base, olhando pares amostrados em cada faixa:

    d < 0,03    a mesma renderização, diferindo em antialiasing e contraste
    d ~ 0,05    mesma forma, peso visivelmente diferente
    d > 0,08    o mesmo caractere em outra fonte — amostra legítima, não irmã

**E a régua que fixou o valor não é a inspeção: é o vazamento medido contra o modelo.** Para cada
imagem do teste, a distância até a imagem de treino mais próxima da mesma classe:

| vizinho mais próximo | imagens no teste | acurácia |
|---|---:|---:|
| < 0,01 | 3.390 (19%) | 0,9994 |
| 0,01 – 0,03 | 1.524 | 0,9973 |
| 0,03 – 0,08 | 9.088 | 0,9978 |
| 0,08 – 0,12 | 2.919 | 0,9925 |
| 0,12 – 0,20 | 720 | 0,9681 |
| > 0,20 | 203 | 0,7192 |

**19% do conjunto de teste tinha um gêmeo de treino a menos de 0,01.** Excluir do teste tudo com
vizinho abaixo de 0,03 leva a acurácia de 0,9928 para 0,9906. **Esse é o tamanho do vazamento**
— pequeno, e agora medido em vez de suposto. É também a resposta para a ressalva que este item
carregava: *"o número do teste é conservador mas não é honesto"*. Ele era otimista em ~0,002.

**Só compara dentro da classe, e isso é o critério e não um atalho.** A S-202 exige "a mesma
leitura" junto do limiar; duas imagens quase iguais com leituras diferentes não são irmãs, são
homóglifo ou erro de rótulo — e disso trata `conflitos.py`. A restrição também torna a passada
**exata** viável: o par a par completo sobre 178 mil imagens seria 1,6·10¹⁰ comparações, e por
classe são 4,4·10⁸, que saem por `matmul` em blocos. Custa 10 segundos sobre a base inteira, sem
aproximação, sem LSH.

**O encadeamento foi conferido, porque união-busca é ligação simples e ela costuma estourar.** O
maior grupo depois da fusão tem 9.954 recortes — mas **13 imagens distintas**: o volume vem da
cópia exata, não da fusão. Nenhuma classe grande é engolida por um grupo (o pior é `lower_e` com
29% num grupo só), e 256 das 314 classes continuam com três ou mais grupos, que é o mínimo para
existir treino, validação e teste.

**A proporção e a altura entram por fora, e nesta base só às vezes.** O critério de origem as
exige porque um `.` e um `O` preenchem o mesmo quadrado depois do redimensionamento — caso que
não aparece aqui, já que a comparação é dentro da classe. O que elas ainda separam é um `a`
pequeno de um `a` grande. Só que **58% dos recortes chegaram em 32x32 da origem** (medido: 167
das 314 classes misturam os dois regimes), e para eles a altura é o valor que a normalização
impôs. Então a guarda só decide quando **os dois** recortes do par trazem tamanho nativo.

**Testes.** `test_o_descritor_tem_lado_24`; `test_a_quase_duplicata_nao_remove_amostra`;
`test_a_mesma_imagem_em_classes_diferentes_nao_se_funde`;
`test_a_altura_desconhecida_nao_decide`;
`test_o_limiar_padrao_nao_e_o_do_projeto_de_origem`.

#### O número honesto, e a parada antecipada que quase o escondeu

    s202        macro 0,9741   acuracia 0,9928   teste com 17.844 imagens
    s202quase   macro 0,9679   acuracia 0,9910   teste com 13.693 imagens

**O teste encolheu 23% e o número caiu, e as duas coisas são o item funcionando.** As irmãs que
antes contavam como amostras independentes agora contam uma vez, e as que estavam do lado errado
do split saíram dele. A queda de 0,0062 na macro é o vazamento que existia; a de acurácia,
0,0018, bate com os ~0,002 que a régua de vizinhança tinha previsto antes do retreino.

**A queda se concentra nas classes pequenas, e isso é o previsto.** Nas 147 classes que votam na
macro nas duas corridas: as 44 com 100+ amostras no teste caem de 0,9952 para 0,9928, e as 55 com
menos de 20 caem de 0,9588 para 0,9315. Classe grande tem renderização de sobra; classe pequena,
depois de tirar as irmãs, fica só com o caso difícil. As maiores quedas individuais são as
suspeitas de sempre — `upper_V` 0,857→0,333, `upper_O` 0,750→0,333 — e `lower_l`, que **perdeu
metade do conjunto de teste** (121 → 60 imagens): metade do teste dele era irmã de algo no treino.

> **Uma parada antecipada mal ajustada quase virou "a quase-duplicata custou 0,015".** A primeira
> corrida com o split honesto parou na época 13, com a melhor em 8 e a macro **ainda subindo** —
> teste macro 0,9587. A `PACIENCIA_PADRAO` era 4; o `cvoff-train` deste projeto usa 15, e a recall
> macro oscila entre épocas consecutivas com desvio de **0,0068**. Uma paciência menor que o ruído
> da métrica que a governa mede o sorteio e não a convergência. Com 10, a mesma receita foi até a
> época 25, escolheu a 15, e deu 0,9679 — **+0,0092 sem mudar mais nada**.
>
> O achado que fica não é o valor: é que **um número pior tinha explicação plausível e errada**
> à mão. "O split honesto custou 0,015" é uma frase que se aceita sem conferir, e ela teria
> escondido um defeito de hiperparâmetro atrás de um resultado esperado.

---

## S-203 · O split por livro, e a prova de que não vazou ◐ parcial (2026-08-23)

**Problema.** Este é o item que decide se o número final desta fase vale alguma coisa. A
avaliação de agosto deste projeto nomeia três contaminações ao mesmo tempo: a verdade de
referência é a leitura do modelo, um sexto do conjunto de campo vira treino no próximo retreino,
e **o split de teste também está contaminado**.

Um split aleatório sobre 700 mil recortes de caractere seria a pior versão possível desse
defeito. O mesmo `e` da mesma fonte da mesma página cai no treino e no teste, e o modelo mede a
própria memória.

**Solução.** O split é **por livro**, e depois por página dentro do livro. Uma fonte nova é um
livro novo, e é isso que o teste tem de simular — que é exatamente como o `treino_diagrama` de lá
mede: **deixando um livro inteiro de fora**.

Os grupos de quase-duplicata da S-202 são respeitados: irmãs caem do mesmo lado.

E há um caso que o inventário vai encontrar: amostras **sem livro de origem registrado**. Elas
não podem ir para o teste (não há como provar que não vazaram) e ficam no treino, marcadas.

**Critério de aceite.**

- ✅ nenhum par (livro, página) aparece em dois splits — `split_por_livro` parte por livro
  inteiro, e `livros_em_dois_lados` confere depois;
- ✅ nenhum grupo de quase-duplicata aparece em dois splits;
- ✅ amostra sem livro de origem fica fora de validação e de teste;
- ✅ existe um **relatório de vazamento** que roda depois do split e faz parte do `cvoff-audit`;
- ✅ o conjunto de teste tem pelo menos um livro que **não aparece no treino** — garantido por
  construção, e travado por `test_existe_um_livro_so_do_teste`.

**E mesmo assim o item é `◐`, porque nada disso rodou sobre livro de verdade.** Os cinco critérios
estão cumpridos *no código*, com testes que os afirmam sobre base sintética. A base real não tem
livro, então `split_por_livro` nunca é chamado nela: o comando cai para `split_por_grupo` e grava
a ressalva. A sonda `arquivo:data/texto_procedencia.csv` é o que impede este item de dizer
`implementada` enquanto for assim.

**Testes.** `test_nenhuma_pagina_atravessa_o_split`;
`test_o_grupo_de_quase_duplicata_nao_atravessa`;
`test_existe_um_livro_so_do_teste`;
`test_amostra_sem_livro_fica_fora_do_teste`.

### O que foi entregue em 2026-08-23: o split por livro existe e espera o livro

`dataset.split_por_livro`, e ele é chamado por `cvoff-texto-train` **quando há registro de
livro**; sem ele o comando cai para `split_por_grupo` e escreve por extenso qual dos dois usou.
Três regras, e as três são a mesma vista de ângulos diferentes:

- a amostra **sem livro** fica no treino: não há como provar que ela não vazou;
- a amostra que a S-201 marca como não-medível fica no treino, pelo mesmo motivo;
- o **grupo que atravessa dois livros** volta ao treino inteiro: ele não pode ser atômico e
  livro-puro ao mesmo tempo, e a atomicidade do grupo é a garantia mais forte das duas.

**Um livro de cada lado é reservado antes de distribuir o resto, e isso não é preciosismo.** A
distribuição proporcional pura falha de um jeito que só aparece com livro desigual: com um livro
de 900 amostras e dois de 50, encher o teste até a fração consome dois dos três e **deixa a
validação vazia** -- sem validação não há época escolhida nem temperatura. Reservar primeiro é o
que transforma "existe um livro só do teste" de probabilidade em garantia.

**Menos de três livros levanta em vez de improvisar.** Com dois não há treino, validação e teste
ao mesmo tempo, e escolher qual sacrificar é decisão de quem chama -- decidir aqui esconderia a
decisão.

**O relatório de vazamento saiu do treino e virou artefato próprio.** `cvoff-texto-train
--so-split` parte, confere e grava `docs/metrics/texto_vazamento.json` em um minuto a partir do
cache, sem treinar. O critério pedia um relatório que "rodasse de verdade", e um que só existisse
depois de um treino inteiro não rodaria: ninguém o refaria a cada mudança de semente.

**A ressalva de hoje, como ela sai gravada:**

    "split": "grupo de copia exata",
    "ressalva": "NAO por livro -- a base nao registra livro de origem",
    "livros": {"total": 0, "so_no_teste": [], "sem_livro": 607713}

**Sonda.** `simbolo:chess_diagram_ocr.text.dataset:split_por_livro`,
`metrica:texto_vazamento`, `arquivo:data/texto_procedencia.csv`.

> **Este item continua planejado porque o que ele promete não é executável nesta base, e a
> marcação tem de dizer isso em vez de esconder.** Não há livro. Os recortes se chamam
> `<uuid>.png`, não há sidecar, não há índice, e o `mtime` é lixo (70% em 2026-02-16, de uma
> migração em massa). Sem livro não existe `test_existe_um_livro_so_do_teste`, e **nenhum número
> desta fase mede generalização de fonte** — que era exatamente o ponto do item.
>
> O que foi entregue em 2026-08-23 é o degrau abaixo, e ele está em
> `text/dataset.py:split_por_grupo`: o split é atômico por **grupo**, o relatório de vazamento
> (`vazamento`) roda depois dele, e `cvoff-texto-train` **aborta** se um único grupo aparecer em
> dois lados — antes da primeira época, não como aviso. Val e teste medem uma imagem por grupo
> (`representantes`), senão a métrica pesaria pela contagem de cópias.
>
> **Dos cinco critérios de aceite, dois estão cumpridos e três não podem ser.** O relatório de
> vazamento existe e trava o treino ✅; e *"nenhum grupo de quase-duplicata aparece em dois
> splits"* passou a valer quando a S-202 entregou `dedupe.agrupar` ✅ — os grupos que o split
> recebe já vêm fundidos, e é por isso que a quase-duplicata roda **antes** do split e não
> depois. Os outros três falam de livro, e livro não existe nesta base.
>
> **Treino e medição contam grupos diferentes, e a diferença é deliberada.** Val e teste contam
> um por grupo de **quase-duplicata**: cinco imagens que são a mesma renderização têm de pesar
> uma vez. O treino conta um por **cópia exata**, que é mais grosso — as irmãs quase-iguais
> diferem de verdade e são amostra legítima; elas só não podem *atravessar* o split, e disso quem
> cuida é o split. Contar o treino por quase-duplicata jogaria fora 23% das imagens distintas sem
> ganho nenhum.
>
> **A trava provou que serve na primeira corrida.** A versão inicial estratificava classe a
> classe e deixou 28 grupos em dois lados, porque um grupo pode pertencer a **duas** classes (os
> 83 rótulos contraditórios da S-202). O comando recusou treinar e nomeou o grupo. Na corrida
> seguinte, com o cache velho no disco, ela recusou de novo — e esse segundo "não" apagou uma
> classe inteira de defeito: o cache guardava o split, então um conserto no `split_por_grupo` não
> alcançava quem lia do cache. O split saiu do cache; ele é função pura da semente e custa um
> segundo para refazer.
>
> **O que fecha o item, e a ordem:** recuperar a procedência na origem (`PyBoxEditor_Tkinter`, que
> foi quem recortou), não aqui. Só de lá pode vir o livro de cada UUID. Sem isso, o item fica
> aberto por tempo indeterminado, e o `docs/metrics/texto_treino_*.json` carrega a ressalva em
> `"split"`, escrita por extenso, para que nenhum número seja lido como se ela não existisse.

---

## S-204 · O treino do classificador de caracteres ✅ implementada (2026-08-23)

**Problema.** A base de lá é desbalanceada por natureza — `lower_e` tem 25.218 amostras e classes
de ligadura raras têm dezenas. E a arquitetura de lá foi escolhida para 292 classes de texto, com
uma medição própria que vale herdar como hipótese e não como conclusão:

    rede                          parâmetros   arquivo
    SimpleCNN (a de caracteres)     620.300    2.423 KB
    RedeDiagrama (a de peças)        35.820      140 KB

A `SimpleCNN` gasta 85% dos parâmetros na camada densa de 2.048→256. Para 12 classes de peça isso
não paga; para 292 de texto, paga — mas ninguém mediu com 700 mil amostras.

**Solução.** `cvoff-texto-train`, no mesmo desenho do `cvoff-train` que já existe: semente fixa,
época salva pela métrica que **decide** e não pela que lisonjeia, checkpoint com metadado
pinado (S-179), e o `experiment` para comparar variantes no split `val` — nunca no `test`, que
fica para a confirmação final da vencedora.

O balanceamento é o que já existe aqui (`augment.py`, pesos de classe) aplicado a caractere, com
a ressalva medida na Fase 5 deste projeto: pesos de classe **não ajudaram** para peças. É
hipótese aberta para caractere, e o item mede em vez de assumir.

**Critério de aceite.**

- o treino roda com o split da S-203 e recusa rodar sem ele;
- a métrica que salva a época está declarada e é a que decide, não a que lisonjeia;
- o checkpoint sai com `modelo_sha256`, `classes_sha256`, `temperatura` e a **contagem de
  amostras por procedência** que o alimentaram;
- a grade de variantes (arquitetura, resolução, canais) roda no `val`, e a tabela vai para
  `docs/metrics/`.

**Testes.** `test_o_treino_recusa_split_ausente`;
`test_a_metrica_que_decide_vem_antes_da_que_lisonjeia`;
`test_o_checkpoint_registra_a_procedencia_das_amostras`.

**Sonda.** `simbolo:chess_diagram_ocr.cli.texto_train:main`,
`metrica:texto_treino`, `metrica:texto_variantes`.

### O que foi entregue em 2026-08-23

`cvoff-texto-train`, `text/dataset.py` e `text/treino.py`. **O treino aconteceu porque não havia
alternativa: os pesos de 292 classes nunca estiveram nesta máquina.** O `char_meta.json` exigia um
`.pt` de sha `2009f803…` que não existe em nenhuma cópia local do projeto de origem — as que há
trazem 128, 150 e 155 classes, todas em formato 1, sem calibração. O motor `glifo` nunca chegou a
rodar aqui, e a S-182 estava `parcial` justamente por isso.

Relatório completo em `docs/metrics/texto_treino_20260823_s204.json`. **O resultado, e a ressalva
vem antes dele:** este número **não** mede generalização de fonte, porque a base não tem livro
(S-203). Ele mede acerto em imagem distinta que não passou pelo treino.

> **O modelo que está em `models/` hoje não é o desta corrida.** É o de
> `docs/metrics/texto_treino_20260823_s202quase.json` — teste macro **0,9679** e acurácia
> **0,9910**, temperatura 1,5212 —, treinado no mesmo dia sobre a base já sem os rótulos
> contraditórios e com o split que a quase-duplicata torna honesto. A corrida descrita abaixo é a
> **primeira**, e fica registrada porque é a linha de base contra a qual as duas correções foram
> medidas. As três corridas estão as três em `docs/metrics/`, pelo mesmo motivo que a
> ANALISE_DETECCAO arquiva duas do detector: comparar contra um arquivo que foi sobrescrito não é
> comparar.
>
>     s204        macro 0,9754   acuracia 0,9925   a base como veio
>     s202        macro 0,9741   acuracia 0,9928   sem os rotulos contraditorios
>     s202quase   macro 0,9679   acuracia 0,9910   irmas nao atravessam o split  <- em models/

    treino    142.740 imagens distintas    (497.303 recortes, uma por grupo de cópia exata)
    validação  17.840                       época escolhida e temperatura saem daqui
    teste      17.840                       tocado uma vez, no fim

    época 17 de 25 (parada antecipada na 22)   val macro 0,9752   val acurácia 0,9926
    TESTE                                          macro 0,9754       acurácia 0,9925

**A distância entre macro e acurácia é o item inteiro em dois números.** 0,9925 contra 0,9754 não
é ruído: são 44 classes com 100+ amostras no teste puxando a média (macro 0,9941) contra 143
classes com menos de 10 (macro 0,9008). Salvar a época pela acurácia teria escolhido outra —
a 16 tinha acurácia 0,9917 e macro 0,9705, e a 17 ganha nas duas só porque a macro foi quem
decidiu ao longo do treino.

**As figurinas, que são a razão de ser deste modelo, saíram no topo:** `♔` 0,9904, `♕` 1,0000,
`♖` 1,0000, `♗` 0,9983, `♘` 1,0000, `♙` 1,0000.

**Onde ele erra é exatamente onde a S-202 avisou que erraria** — e é a mesma lista dos 83 grupos
de rótulo contraditório:

| classe | recall | amostras no teste |
|---|---|---|
| `sym_39` (`'`) | 0,571 | 7 |
| `upper_O` | 0,750 | 12 |
| `digit_0` | 0,781 | 32 |
| `sym_44` (`,`) | 0,828 | 29 |
| `upper_I` | 0,840 | 25 |
| `lower_l` | 0,917 | 120 |

Não são classes difíceis: são pares em que a base **ensina as duas respostas para a mesma
imagem**. Consertar o rótulo na origem vale mais que qualquer mudança de arquitetura aqui, e o
precedente é do próprio projeto de origem (S-180: corrigir `sym_f7` fez o modelo já treinado
acertar 127 de 127 sem retreinar).

**O que este número não cobre, e está registrado no relatório por classe:** 56 das 314 classes
**não têm uma única amostra no teste** — têm menos de três imagens distintas, então caem inteiras
no treino. São 82 recortes ao todo. O modelo passa a poder emitir esses rótulos, e ninguém mediu
se ele acerta. Das 258 medidas, 191 têm recall perfeita e 28 ficam abaixo de 0,90.

**O que faltava do critério de aceite fechou em 2026-08-23:** a grade de variantes e o aumento de
dados aplicado a caractere. Ver "A grade de variantes", abaixo.

### Pesos de classe: medidos, e a resposta é a mesma da Fase 5

`docs/metrics/texto_treino_20260823_pesos.json`, mesma semente, mesmo split, mesma receita, só a
perda ponderada por `1/sqrt(contagem)` normalizada:

    val macro       0,9690  ->  0,9781    (+0,0091)
    TESTE macro     0,9679  ->  0,9691    (+0,0013)
    TESTE acurácia  0,9910  ->  0,9903    (-0,0007)

**O ganho no teste é menor que um único acerto.** Nesta base, um acerto a mais na menor classe que
vota na macro vale 0,00136; a diferença medida foi 0,00126. E a acurácia piorou. Os pesos **não
ajudaram** — a mesma conclusão que a Fase 5 deste projeto tinha chegado para peças, agora medida
para caractere em vez de assumida.

Eles fazem exatamente o que prometem, e o problema é que a troca sai no zero a zero:

| classes (por amostras no teste) | sem pesos | com pesos | |
|---|---:|---:|---|
| gordas (100+) | 0,9964 | 0,9941 | −0,0023 |
| médias (20–99) | 0,9790 | 0,9800 | +0,0010 |
| **raras (5–19)** | 0,9433 | **0,9467** | **+0,0034** |

Os pesos levam 42,1% do gradiente das dez maiores classes para 19,4%, e as raras sobem — só que o
que elas ganham as gordas perdem. Por classe, `sym_39` vai de 0,1667 a 0,3333 e `upper_V` de
0,8333 a 1,0000; do outro lado, `upper_K` cai de 1,0000 a 0,8000 e `lower_s` de 0,9878 a 0,9390.

> **O achado de método é o `val` contra o `test`, e ele vale mais que o veredito.** Na validação
> os pesos ganham 0,0091 — sete vezes o que ganham no teste. Quem comparasse os dois braços no
> `val`, que é onde a grade roda, concluiria "pesos ajudam" com folga aparente. Parte disso é
> viés de seleção: a época 34 foi escolhida **porque** maximizava a macro do `val`, então o `val`
> da época escolhida é otimista por construção. É exatamente por isso que o item manda a grade
> rodar no `val` e a vencedora ser **confirmada no `test`**, que fica intocado até o fim.

**O modelo com pesos não foi promovido.** Ele está em `models/experiments/char_pesos.pt`, e
`models/` continua com o de `texto_treino_20260823_s202quase.json`. Trocar o publicado por outro
que empata na métrica que decide e perde na outra seria mexer por mexer.

**Uma decisão que o item não previa: o treino usa uma imagem por grupo de cópia exata**, não os
608.407 recortes. Treinar com as cópias custaria 3,5× por época para reapresentar imagem já
vista, e a duplicação não é distribuição de livro — é redundância de coleta: `lower_a` tem 63.055
recortes e 5.683 imagens. Deduplicar ainda **corrige** parte do desbalanceamento sozinho: em
recortes `lower_a` (63.055) esmaga `digit_2` (21.962); em imagens distintas, `digit_2` (10.610)
passa `lower_a` (5.683). `--todos-os-recortes` roda o outro braço para quem quiser medir.

### A grade de variantes, medida em 2026-08-23 — e ela não achou vencedora

`cvoff-texto-variantes`, seis braços, **10 épocas cada com a mesma semente e o mesmo split**, e o
`test` tocado uma vez só, pela vencedora. Relatório em `docs/metrics/texto_variantes_<data>.json`.

| braço | val macro | val acurácia | parâmetros | segundos |
|---|---:|---:|---:|---:|
| pesos-de-classe | **0,9647** | 0,9871 | 617.216 | 659 |
| controle | 0,9632 | **0,9898** | 617.216 | 626 |
| aumento-leve | 0,9598 | 0,9883 | 617.216 | 714 |
| densa-128 | 0,9554 | 0,9882 | 354.944 | 661 |
| canais-menores | 0,9430 | 0,9835 | 154.496 | **286** |
| aumento-forte | 0,9420 | 0,9851 | 617.216 | 776 |

**A vencedora ganha por 0,0015, e este projeto já mediu que 0,0015 não é nada.** A S-204 registrou
o ruído da recall macro entre épocas consecutivas desta base: **0,0068**. A diferença entre o
primeiro e o segundo colocado é **um quinto** dele — e o segundo colocado ganha na acurácia. A
leitura honesta da tabela não é "os pesos de classe venceram": é **a grade não achou vencedora**,
e o controle continua sendo o controle.

O `test` confirmou a vencedora em macro **0,9543** e acurácia 0,9852, e o número existe para
fechar o protocolo — não para promover nada. **Nada foi promovido**, pelo mesmo motivo que os
pesos de classe não tinham sido em agosto: trocar o publicado por outro que empata dentro do
ruído seria mexer por mexer.

**O aumento de dados não paga, e é a terceira vez que este projeto mede isso.** `aumento-leve`
fica 0,0034 abaixo do controle e `aumento-forte`, 0,0212 — e os dois custam mais tempo por época.
A Fase 5 mediu que o aumento genérico não ajudou para peças; a S-204 mediu que os pesos de classe
não ajudaram para caractere; agora o aumento dirigido também não. **Três hipóteses que todo mundo
assume, três medições, três nãos.**

> **E o módulo de aumento existe mesmo assim, porque ele responde uma pergunta que ninguém tinha
> feito.** `text/aumento.py` não é o `augment.py` de peças aplicado a caractere: **espelhar é a
> degradação mais barata lá e a mais danosa aqui.** Um `b` espelhado é um `d`, um `p` é um `q`, um
> `(` é um `)` — e os pares que ele ensinaria a confundir são exatamente os 83 grupos de rótulo
> contraditório que a S-202 nomeou. O módulo tem sete degradações de scanner e gráfica, nenhuma
> troca de eixo, e dois testes que impedem uma de voltar por engano: um mede a assimetria da tinta
> em 500 recortes, o outro varre a `ast` atrás de `flip`, `transpose` e `rot90`.

**A hipótese da S-204 sobre a forma tem resposta, e ela é um trade-off e não um veredito.** A
densa 2.048→256 são 85% dos parâmetros: cortá-la pela metade (`densa-128`) custa **0,0078** de
macro e economiza 43% dos pesos; cortar os canais junto (`canais-menores`, 16→32→64) custa 0,0202
e economiza 75% — **rodando em 286 s contra 626 s**, menos da metade do tempo. Para esta máquina,
que treina em CPU, isso é uma tarde contra duas. Nenhum dos dois é melhor; os dois são mais
baratos, e agora o preço está medido.

**O terceiro eixo que o critério nomeia — a resolução — não tem braço, e o motivo não é
esquecimento.** `modelo.LADO` é 32 e não é ajustável: **a base inteira foi gravada nesse tamanho**,
e 58% dos recortes já chegaram assim da origem. Treinar em 48 ou 64 significaria ampliar um
recorte de 32, que não acrescenta informação nenhuma — ou reextrair da página, que **esta base não
permite**, porque nenhum recorte sabe de que página veio. É a mesma falta que trava a S-201 e a
S-203, aparecendo pela terceira vez. O eixo fica aberto, e ele só abre quando o registro da origem
chegar.

> **A forma precisou virar dado para esta linha existir.** Até aqui a `SimpleCNN` era cravada em
> `_construir_rede`, e um braço que mudasse canais ou densa produziria pesos que
> `load_state_dict` recusa — que é o comportamento certo. `modelo.Arquitetura` é a saída que a
> própria S-204 já apontava: **a grade muda os dois lados de uma vez ou não muda nenhum.** O
> metadado grava a forma, `carregar_classificador` a lê, e metadado sem o campo carrega como a
> forma padrão, que é literalmente a que ele descreve.

### As 58 classes que nenhuma medição alcança: a decisão, com o número que faltava

O item pedia a decisão e não tinha como tomá-la: 58 classes têm menos de três imagens distintas,
caem inteiras no treino, e **o modelo passa a poder emitir esses rótulos sem que ninguém meça se
ele acerta**. As duas saídas — mantê-las declarando `n=0`, ou cortá-las com `--minimo 3` — só se
separam por um fato: elas *são* emitidas?

**Duas vezes em 13.693 amostras de teste** (`ligature_hex_003f0021` e `sym_200`), com o modelo da
vencedora. É 0,015% das previsões.

**A decisão é mantê-las, declarando `n=0` por classe no relatório**, que é o que o
`docs/metrics/texto_treino_*.json` já faz. Cortá-las tiraria do modelo 99 recortes de trabalho
humano para eliminar duas previsões em treze mil — e a classe cortada não some do mundo: ela
volta como erro na classe vizinha, que é onde ela cairia.

---

## S-205 · A calibração entra no fim do treino, ou não sobrevive a ele ✅ implementada (2026-08-23)

**Problema.** A confiança deste classificador é usada para quatro coisas: cortar legenda
adivinhada (S-181), arbitrar corte de glifo colado (S-186, S-198), escolher ângulo de pilha
(S-197) e ordenar a fila de revisão (S-212). Um modelo mal calibrado desregula as quatro de uma
vez.

E há um defeito de processo, medido lá na F25 e que vale mais que o valor da temperatura: **o
retreino apaga a calibração**, e ninguém nota. O metadado continua trazendo o número antigo, que
passa a descrever outro modelo.

**Solução.** A calibração de temperatura é o **último passo do treino**, dentro do mesmo comando,
e o metadado só é gravado depois dela. Medido lá, custa ~20 segundos.

Duas travas:

- **a calibração nunca derruba o treino**: se ela falhar, o modelo é salvo com temperatura 1,0 e
  um aviso explícito, porque um modelo sem calibração é pior que nenhum modelo apenas se ninguém
  souber;
- **o metadado sem temperatura é recusado na carga** (S-179), o que fecha o laço.

**Critério de aceite.**

- ✅ treinar e não calibrar é impossível pelo caminho normal — o teste prova que o metadado sai
  sempre com uma temperatura;
- ✅ a curva de confiabilidade antes e depois vai para `docs/metrics/`, com o erro de calibração
  esperado (ECE) nos dois momentos;
- ✅ a temperatura gravada corresponde ao modelo gravado, travado pelo `modelo_sha256` — e agora
  **medida**: `cvoff-texto-train --so-calibracao` refaz a temperatura sobre a mesma validação e
  publica as duas lado a lado.

**Testes.** `test_o_metadado_sai_sempre_com_temperatura`;
`test_a_falha_da_calibracao_nao_derruba_o_treino`;
`test_a_temperatura_corresponde_ao_modelo_gravado`.

### A curva, medida em 2026-08-23 — e ela desmente o número que a resumia

`cvoff-texto-train --so-calibracao`, sobre as **13.693 imagens distintas de validação** e o par
que está publicado. O comando não treina: ele carrega o `.pt` e o metadado, refaz os logits crus
e mede. Relatório em `docs/metrics/texto_ece_<data>.json`.

**A trava do item, em número:** temperatura publicada **1,5212**, refeita agora **1,5211**. O
metadado descreve o modelo que está no disco, e agora isso é medido em vez de prometido.

**Os dois ECE, e a distância entre eles é o achado:**

    ECE ponderado    antes 0,0040  ->  depois 0,0037
    ECE por faixa    antes 0,1131  ->  depois 0,1080     <- é este que decide

**Trinta vezes.** O ECE ponderado é a média das faixas pelo tamanho delas, e nesta validação
**96% das amostras caem numa faixa só** — a de 0,93 a 1,00, onde o modelo diz 0,9982 e acerta
0,9979. O número ponderado mede aquela faixa e mais nada, e sai lisonjeiro por construção.

**É a mesma lição da macro contra a acurácia, agora aplicada à calibração** — e é a segunda vez
que ela aparece nesta fase. Lá, 44 classes gordas escondiam 143 raras; aqui, uma faixa de
confiança esconde as outras treze.

**E a faixa que o ponderado esconde é a única em que alguma coisa é decidida.** O corte de
legenda adivinhada da S-42 está em 0,30; os árbitros da S-186, da S-197 e da S-198 comparam
confianças no meio da escala. Nenhum deles consulta a faixa de 0,93 a 1,00.

| faixa | n | ele diz | ele acerta |
|---|---:|---:|---:|
| 0,53–0,60 | 31 | 0,566 | 0,742 |
| 0,60–0,67 | 40 | 0,630 | 0,775 |
| 0,73–0,80 | 69 | 0,769 | 0,913 |
| 0,80–0,87 | 91 | 0,830 | 0,945 |
| 0,87–0,93 | 197 | 0,904 | 0,934 |
| **0,93–1,00** | **13.164** | **0,998** | **0,998** |

**No meio da escala o modelo é pessimista**: onde ele diz 0,83 ele acerta 0,94. Um árbitro que
compare "0,83 contra 0,79" está comparando duas subestimativas, e o corte de 0,30 da S-42
descarta legenda que estaria certa mais vezes do que o número sugere. A temperatura melhorou
isso pouco (0,1131 → 0,1080) porque **ela minimiza a NLL, e não o ECE** — e essa distinção,
antes deste relatório, não tinha como aparecer.

**O que a temperatura fez de fato, visto pela contagem:** ela empurrou **258 amostras** para fora
da faixa do topo (13.422 → 13.164), espalhando-as pelas faixas de 0,53 a 0,93. É exatamente a
região que as quatro decisões consultam, e é por isso que o item pedia a curva e não só o
parâmetro.

### As duas travas, e onde elas estão

**A calibração nunca derruba o treino.** `treinar` chama `calibracao.calibrar` dentro de um
`try`: se ela falhar, o modelo é salvo com temperatura 1,0, o rastro vai para o log e o
resultado carrega `falhou: True`. Um modelo com temperatura 1,0 e um aviso é pior que um
calibrado e muito melhor que nenhum modelo depois de vinte épocas de CPU — o que não pode
acontecer é o número sair sem ninguém saber. Travado por
`test_a_falha_da_calibracao_nao_derruba_o_treino`.

**O metadado sem temperatura é recusado na carga**, o que fecha o laço do outro lado (S-179).

**E o módulo mudou de casa**, como a sonda deste item já mandava: `calibrar`, a curva, os dois
ECE e a prosa moram em `text/calibracao.py`. `text/treino.py` importa. A separação não é
arrumação: a curva é medida sobre um modelo que já existe tantas vezes quanto sobre um recém-
treinado, e enterrá-la no treino obrigaria a retreinar para medir.

**Sonda.** `simbolo:chess_diagram_ocr.text.calibracao:calibrar`,
`metrica:texto_ece`.

> **O defeito de processo fechou primeiro, e a medição veio no mesmo dia.** A
> temperatura é ajustada em `calibracao.calibrar` — busca em grade sobre a NLL da
> validação, com os pesos da **melhor** época e não os da última (calibrar os outros seria gravar
> a temperatura de um modelo que não existe) — e `gravar_checkpoint` grava pesos e metadado
> juntos, os pesos primeiro para que o `modelo_sha256` descreva o arquivo que está no disco. Não
> existe caminho no comando que produza pesos sem temperatura, e `test_o_checkpoint_sai_com_
> calibracao_e_impressao_digital` trava isso.
>
> Os três treinos de 2026-08-23 acharam o modelo **otimista**: temperatura 1,8622, 1,7320 e
> 1,5212, esta última a do modelo que está em `models/`. Nos três casos ela reduz a confiança que
> o modelo reporta. Isso importa mais do que parece — é essa confiança que
> decide o corte de legenda, o árbitro do corte de glifo colado, o ângulo da pilha e a ordem da
> fila de revisão. Um modelo a 0,99 de confiança crua sobre um `'` que ele acerta 57% das vezes
> desregularia as quatro.
>
> **O que mantinha o item aberto, e fechou em 2026-08-23:** a curva de confiabilidade e o ECE
> antes e depois, em `docs/metrics/`. O módulo saiu de `text/treino.py` para
> `text/calibracao.py` no mesmo movimento, como a sonda já mandava. Ver a seção seguinte.

---

## S-206 · O placar honesto: o classificador, e a página ✅ implementada (2026-08-24)

**Problema.** Publicar "99,8% de acerto" sobre recorte já segmentado quando a página real dá 94 é
a forma de número enganoso que este projeto já cometeu e corrigiu. Os dois números são
verdadeiros e medem coisas diferentes, e a distância entre eles **é o trabalho que sobra**.

**Solução.** Um relatório com as duas réguas lado a lado, sempre:

| régua | sobre o quê | o que ela não diz |
|---|---|---|
| acurácia do classificador | recorte já segmentado, split de teste com livro novo | nada sobre achar o recorte |
| F1 da página | página real anotada, precisão e recall de caractere | é a que conta para o usuário |

E uma terceira coluna que o projeto de origem não tinha e este deve ter desde o início: **o
resultado no livro que não estava no treino**, separado do resto. É o único número que fala sobre
fonte nova.

**Critério de aceite.**

- ✅ as duas réguas aparecem sempre juntas, e o comando **falha** se a da página não puder ser
  medida — `test_o_relatorio_recusa_publicar_so_a_regua_de_recorte`;
- ✅ o livro novo tem coluna própria, com `null` e o motivo ao lado: esta base não registra livro
  (S-203). Omiti-la faria a tabela parecer completa;
- ✅ o `n` de cada célula está declarado;
- ✅ a distância está registrada e nomeada — ver abaixo.

**Testes.** `test_o_relatorio_traz_as_duas_reguas`;
`test_o_livro_novo_tem_coluna_propria`;
`test_o_relatorio_recusa_publicar_so_a_regua_de_recorte`.

### As duas réguas, medidas em 2026-08-24 — e a distância entre elas é de 33,5 pontos

`cvoff-texto-placar-final`. **Nenhuma das duas linhas abaixo pode ser publicada sozinha**, e o
comando recusa gravar só a primeira.

| régua | valor | n | o que ela não diz |
|---|---:|---:|---|
| acurácia do classificador | **0,9910** | 13.693 recortes | nada sobre **achar** o recorte |
| macro do classificador | 0,9679 | 13.693 recortes | idem |
| acerto na página (1 − CER) | **0,6555** | 22 páginas | é a que conta para o usuário |
| F1 de caractere na página | 0,7663 | 22 páginas | — |
| **livro novo** | **n/d** | 0 | não existe nesta base (S-203) |

**0,9910 contra 0,6555.** Os dois números são verdadeiros, medem coisas diferentes, e **a
distância entre eles é o trabalho que sobra**: o classificador acerta o recorte que lhe dão; o que
a página perde está em *achar* o recorte. Publicar o primeiro sozinho seria repetir a forma de
número enganoso que este projeto já cometeu e corrigiu na Fase 19.

**A régua da página é a pipeline inteira**, e não uma faixa: renderizar, **detectar o diagrama e
excluí-lo**, binarizar, achar caixa, quebrar em linha, classificar. A referência é a camada de
texto editorada dos 11 livros que não são digitalização com OCR por cima — a mesma escolha da
S-198, pelo mesmo motivo.

**E a página é mais difícil que a faixa, o que também é informação:** o CER da faixa é 0,2248
(S-198) e o da página é 0,3445. A diferença é tudo o que uma página tem e uma faixa não —
cabeçalho, número de página, título corrido, e o que sobra de diagrama que o detector não pegou.

> **Um defeito que a primeira corrida escondeu, e o número mudou quando ele foi consertado.** O
> detector era chamado com `page.parent` — um `fitz.Document` — onde ele espera o **caminho**; a
> abertura falhava, o `except` engolia, e a página era medida **sem exclusão de diagrama**. O erro
> era silencioso por construção: aquele `except` existe justamente para a detecção não derrubar a
> medição.

**Os itens que atacam a distância estão nomeados no relatório**, e depois desta fase eles são
menos do que se esperava: a S-186 mediu que o separador de colado **piora**, e a S-188 que a
leitura por linha **empata**. O que sobra apontando para o meio da distância é a segmentação
(S-185), o texto girado (S-197) e o que a S-212 vier a corrigir com trabalho humano.

**Sonda.** `metrica:texto_placar_final`.

---

# Fase 30 — O que o texto lido serve

> Aqui o texto vira produto. Nada desta fase embarca antes da S-215, que mede o custo por página.

## S-207 · O lado a jogar deixa de depender de motor de fora ✅ implementada (2026-08-26)

**Problema.** Hoje o lado a jogar tem oito fontes declaradas em `semantics.SideSource` (dez depois deste item), e para os
7 livros sem camada de texto a que sobra é `default` — o palpite. A S-42 abriu o caminho do OCR
para eles, com RapidOCR, opt-in e desligado por padrão.

**Solução.** `glifo` entra como fonte de lado a jogar, ao lado das que já existem, com as mesmas
duas regras da S-43: o PGN sai com `[SideToMoveSource "glifo"]` — **nunca disfarçado de camada de
texto** — e com `[SideToMoveConfidence]` ao lado quando houve dúvida.

O que muda em relação à S-43 é só a qualidade da leitura, e por isso este item é barato: toda a
costura já existe. O que ele acrescenta é a **medição por livro** — quantos diagramas dos 7
livros deixam de sair `default`, e em quantos a leitura contradiz a semântica da S-17.

**A contradição é informação, não erro a esconder.** Quando o texto diz "pretas jogam" e a
S-17 diz que quem não joga estaria em xeque, o par vai para a fila de revisão marcado, e não é
resolvido por prioridade fixa.

**Critério de aceite.**

- `SideSource` ganha o valor novo, e o `README` explica o que ele significa —
  `tests/test_docs.py::test_as_fontes_do_lado_a_jogar_batem_com_o_Literal` já cobra isso;
- a tabela por livro: diagramas com lado lido, com lado `default`, e com contradição;
- a contradição vai para a fila, e o teste prova que ela não é resolvida em silêncio.

**Testes.** `test_o_glifo_entra_como_fonte_declarada`;
`test_a_contradicao_vai_para_a_fila_e_nao_e_resolvida_calada`.
> **A costura existia, e o que faltava era honestidade e medição (2026-08-26).**
>
> **O disfarce não era o que a spec supunha.** Ela diz "nunca disfarçado de camada de texto", e
> disso o programa já se defendia: uma legenda lida por motor saía `ocr`, e não `text`. O disfarce
> real era outro -- **o classificador desta casa saía como `ocr`, indistinguível do RapidOCR**.
> Duas qualidades muito diferentes no mesmo valor de header, que é o oposto do que a Fase 3 quer.
>
> `SideSource` foi de 8 para 10 valores: `glifo` e `glifo-page-scope`. **Os dois, e não um.** O
> caminho de escopo de página (`page_scope_declaration`) usa o mesmo motor, e deixar só o de
> legenda distinto faria o cabeçalho lido pelo classificador sair dizendo `ocr-page-scope` -- um
> item que existe para acabar com o disfarce não pode deixar metade disfarçada.
>
> **E a implementação esbarrou numa regra da S-181, que estava certa.**
> `test_a_s43_nao_precisou_saber_que_o_glifo_existe` cobra que `ocr_caption.py` e `pdf_text.py`
> **não mencionem motor nenhum pelo nome** -- porque no dia em que mencionarem, a próxima fonte de
> texto vai precisar de uma segunda porta. Um `if nome == "glifo"` a quebraria; um `Literal` com
> `"glifo"` escrito dentro, também. A resposta foi `procedencias.py`: o vocabulário
> (`LineOrigin`, `SideOrigin`, `procedencia_do_motor`, `escopo_de_pagina`) mora num lugar só, os
> dois módulos genéricos passam o nome do motor e recebem a procedência, e continuam sem saber
> quais existem. O escopo de página é **sufixo**, e por isso não há uma segunda tabela para
> divergir da primeira.
>
> **A medição encontrou um defeito de leitura que não é deste item, e o consertou.** A faixa de
> legenda tem 60 pt de raio, e `_blank_region` apagava **só o diagrama alvo**: numa folha de quatro
> problemas, a faixa contém pedaços dos outros três. As peças ficam, e a leitura de glifo mede a
> escala do texto por massa de tinta -- uma peça tem 86 px de altura contra 23 de uma letra, e a
> peneira de área descarta todas as letras. É o mesmo defeito que `escala_fora_dos_diagramas`
> corrige na página inteira. Medido na página 17 do `1000 Chess Problems`:
>
>     apagando só o alvo     8 caixas, todas figurina e ruído -- nenhum texto
>     apagando os quatro     3 caixas, e uma é a legenda: `MaT B 2 xoua 4+3`
>
> `lines_around` passou a receber os vizinhos, opcionais e vazios por omissão. **O caminho do
> RapidOCR ganha o mesmo conserto de graça.**
>
> **A tabela por livro, que é o que o item acrescenta à S-43.** 10 livros, 8 páginas com diagrama
> de cada, 172 diagramas, com as duas pontas na mesma corrida:
>
>     lado a jogar          sem motor de legenda    com o glifo
>     lido pelo glifo                          0              3
>     de outra fonte                          26             26
>     continuou `default`                    146            143
>     contradições                             0              0
>
> **3 de 146 diagramas assumidos deixam de sair `default` (2,1%), e 2 dos 3 vêm abaixo do piso de
> confiança** -- saem com `[SideToMoveConfidence]` ao lado, que é a segunda regra da S-43.
>
> **O número é pequeno, e o motivo está na tabela e não no motor.** Os livros que declaram o lado
> por diagrama (`400 Quebra-cabeças`, `Kemeri`, `AAGAARD`) **já têm camada de texto**, e ali o
> motor nem chega a ser chamado -- `_lines_with_ocr` só o aciona onde a camada calou. Os que calam
> ou não declaram (`A Matter of Endgame Technique`: 61 diagramas, nenhuma declaração) ou estão
> num alfabeto que o classificador não tem: o `1000 Chess Problems` é **russo**, e a spec já
> declarava que "um livro em russo não é lido por ele" -- o `MaT B 2 xoua` acima é `Мат в 2 хода`
> transliterado por um modelo que só tem latino.
>
> **Nenhuma contradição apareceu nesta amostra**, e a máquina que a trataria está de pé e testada:
> `infer_side_to_move` marca `conflicting`, a legalidade vence, e a fila da S-22 pontua com
> `WEIGHT_SOURCES_DISAGREE`. `test_a_contradicao_vai_para_a_fila_e_nao_e_resolvida_calada` a
> exercita com xeque invertido, porque um caminho que só roda quando o acervo colabora é um caminho
> que ninguém sabe se funciona.
>
> Tudo em `docs/metrics/texto_lado.json`, com as duas tabelas lado a lado.


**Sonda.** `simbolo:chess_diagram_ocr.text.lado:lado_por_glifo`,
`metrica:texto_lado`.

---

## S-208 · A notação validada pelas regras, e o PGN que sai dela ✅ implementada (2026-08-26)

**Problema.** O projeto exporta PGN **de posições**: cada diagrama vira um `[FEN]`. A partida
impressa em volta dele — `1...♗xb7 2.♗xb7 ♘d7 3.♗xa8 ♕xa8 4.♘f3±` — é ignorada.

E ela é justamente onde a camada de texto de fábrica destes livros mais erra. Medido lá, a mesma
linha da página 11 do Yusupov:

    camada do PDF   '•. hb7 2.hb7 l2Jd7 3.ha8 Wlxa8 4.c!LJ£3;!;'
    o OCR de glifo  '1...♗xb7 2.♗xb7 ♘d7 3.♗xa8 ♕xa8 4.♘f3²'

**Solução.** `text/notacao.py`, e a peça central é **fatiar**: separar o que é lance do que é
prosa, antes de qualquer correção. Aplicar lista de palavras a `Bxf6` destruiria a parte do livro
que o programa existe para ler.

A validação é por **legalidade**, com o `chess` que já é dependência: `Nf3` é válido numa posição
e impossível na seguinte, e é isso que faz do tabuleiro um dicionário melhor que qualquer lista.
O contrato é o da S-15 deste projeto: **propõe, marca, não reescreve calado** — lance que não
fecha vai para o `.review.pgn` com o motivo.

A ambiguidade branca/preta das figurinas é **insolúvel visualmente** — o livro usa um único
conjunto de glifos para os dois lados, e quem decide é a paridade do número do lance. É trabalho
da validação, não do classificador.

**Critério de aceite.**

- uma linha de notação sintética com figurinas vira lances válidos, com o lado certo por paridade;
- lance ilegal na posição corrente não é reescrito: vai para revisão com o motivo;
- prosa no meio da linha não é tratada como notação, e notação no meio da prosa não é tratada como
  palavra;
- o PGN de partida sai separado do PGN de posições, e o header diz qual é qual.

**Testes.** `test_a_figurina_ganha_o_lado_pela_paridade`;
`test_o_lance_ilegal_vai_para_revisao_e_nao_e_reescrito`;
`test_prosa_e_lance_sao_fatiados_antes_de_qualquer_correcao`.

### O que entrou em 2026-08-24: `fatiar`, e o número de lance partido

Entrou a **peça central**, e só ela: `fatiar`. Não entrou `validar` -- a legalidade pela posição,
com o `chess`, e o `.review.pgn` de quem não fecha --, e é ela que dá o PGN de partida. Por isso o
item fica **parcial** e não implementado.

O que `fatiar` já resolve sozinho é o **número de lance partido em dois**: `15 0-0?!` saía
`1 5 0-0?!`, 44 vezes em 23 páginas. Ele **não** era consertável por geometria, e isso tinha sido
medido antes: o vão entre os dois dígitos de `15` e o vão entre duas palavras têm o mesmo tamanho
(dígito p10 0,46 · mediana 0,79 · p90 1,17; palavra p10 0,62 · mediana 0,86 · p90 1,60), e um
corte em 0,55 juntaria 12 dos 44 e **destruiria 49 espaços de verdade**.

A regra que só a notação permite: **em notação de xadrez não existem dois números seguidos.** Um
número de lance é sempre seguido de lance ou de reticência, então dois tokens de dígito lado a lado
*dentro de uma fatia de notação* são um número que a segmentação partiu. Fora dela a mesma
sequência é legítima — `In 1968 he lost`, `capítulo 3 4`.

| referência | páginas | `sem` | `com` | melhoram / pioram | partidos |
|---|---:|---:|---:|---:|---:|
| camada editorada (confiável) | 11 | 0,1065 | 0,1058 | 4 / 1 | 13 → 4 |
| camada de OCR (suspeita) | 12 | 0,2326 | 0,2326 | 2 / 2 | 31 → 11 |
| todas | 23 | 0,1723 | 0,1720 | 6 / 3 | **44 → 15** |

**O CER quase não se move, e há uma razão medida**: nos livros de camada de OCR a *própria camada*
parte o número — no `AAGAARD` ela escreve `4 1 .` e `1 7` —, então juntar nos afasta de uma
referência que também está errada.

**Duas guardas saíram de regressão medida**, e as duas ficam escritas porque cada uma custou um
falso positivo: a fatia precisa de um **lance de verdade** e não só de números (sem isso `capítulo
3 4 do livro` virava notação), e só **um dígito à esquerda** (sem isso `15 2 f3 xg5`, na notação
espaçada do `Capablanca`, virava `152`).

**O falso positivo que sobra**, e ele é honesto: `Capablanca` p72, `7` + `2` → `72`. É
estruturalmente idêntico ao caso que se quer consertar — dígito, dígito, lance —, e só a
**legalidade** separaria os dois: existe lance 72 nesta partida? Isso é `validar`.

### O que entrou em 2026-08-26: `validar`, e a metade que dá o PGN de partida

Entrou a metade que faltava, e ela entrou porque **apareceu o cliente**: a sala de estudo da Fase 47
(S-283). Uma linha impressa só vira lance quando há uma posição sobre a qual jogá-la, e a posição é
a raiz do estudo daquele diagrama -- que só passou a existir na S-268.

`validar(tokens, board)` devolve uma `LinhaValidada`: os lances que fecharam, e **onde parou** quando
parou. O contrato é o da S-15, dito na assinatura em vez de na prosa: não há caminho por onde um
lance ilegal seja reescrito, porque a função não reescreve nada -- ela para.

**O tabuleiro é o dicionário**, e é isso que separa os dois falsos positivos que a metade de cima
registrou. `Capablanca` p72, `7` + `2` → `72`: a fatia é *estruturalmente idêntica* ao caso que
`juntar_numero_de_lance` existe para consertar -- dígito, dígito, lance --, e nenhuma régua de
geometria ou de lista de palavras os separa. A legalidade separa: ou existe lance 72 nesta partida,
ou não existe.

**A figurina ganha o lado pela posição, e não pela paridade.** A S-208 escreveu que "quem decide é a
paridade do número do lance", e com um tabuleiro na mão isso vira um caso particular de uma coisa
mais forte: `♗xb7` é o bispo de quem está a jogar, e o tabuleiro sabe quem é. `para_ingles` troca a
figurina pela inicial inglesa (`LETRA_DA_FIGURINA`, que já existia para a busca da S-245) e o
`parse_san` faz o resto. O número impresso continua sendo lido -- e é **conferido, não obedecido**:
um `15.` numa posição de pretas para a linha com o motivo, porque isso vale mais dito que corrigido.

**As iniciais de outras línguas continuam fora**, pela razão que `FIGURINAS_DA_LETRA` já registrava:
`R` é *rook* em inglês e *rei* em português, `C` é *cavalo* e nada em inglês. Traduzi-las exigiria
saber a língua do livro, e errar a língua troca uma peça por outra **num lance que o tabuleiro
aceita** -- o pior defeito possível aqui, porque ele não levanta.

**O `.review.pgn` não entrou, e a razão é que ele deixou de ser o lugar certo.** A spec o previa
como o destino do que não fecha, e quem consome `validar` hoje é uma aba: ela mostra o lance que
travou e o motivo no rodapé, com os lances anteriores já na árvore, e quem lê decide na hora --
que é melhor que um arquivo que alguém abriria depois. O arquivo volta a fazer sentido quando
houver um comando de linha que valide o livro inteiro de uma vez; até lá, seria formato sem cliente.

**Sonda.** `simbolo:chess_diagram_ocr.text.notacao:fatiar`,
`simbolo:chess_diagram_ocr.text.notacao:validar`.

---

## S-209 · O léxico sinaliza, e nunca troca ✅ implementada (2026-08-26)

**Problema.** Depois de fatiar, sobra a prosa. Um `Bib1i0g[aPhY` na prosa é um erro que o
dicionário vê e a legalidade não.

**Solução.** `text/lexico.py`, com duas listas empacotadas (idioma e nomes próprios), separadas
porque a troca entre elas está medida: só o idioma dá 58,5% de recall com 12,1% de alarme falso;
com os nomes, 53,8% e 5,8%. **Nome próprio baixa o alarme e esconde erro**, e quem escolhe é o
perfil do livro. *(medido lá)*

**A regra é a que contraria o instinto, e é o que dá valor ao item: palavra fora do dicionário é
sinalizada, nunca aproximada da mais parecida.** `Nimzowitsch` não está em lista alguma, e forçar
a troca entregaria prosa limpa e falsa. Medido lá: dos 18 lances tão maltratados que escapam do
fatiador e caem no léxico, **nenhum** está no dicionário; com correção automática, seriam 18
lances reescritos como palavra.

O que o dicionário **decide** são as duas fronteiras de palavra, porque nas duas ele é o próprio
critério e não precisa de limiar: juntar hifenizadas na quebra de linha (`em-` + `barrassment`) e
partir coladas (`ofthe` → `of` `the`). Medido lá sobre a verdade: 6 de 6 junções certas, com as 2
que não devem juntar recusadas; 7 de 7 partições certas, e nenhuma das 51 palavras boas que
também decomporiam foi partida — porque a primeira condição é a palavra **não** estar no
dicionário.

**Critério de aceite.**

- palavra desconhecida sai marcada e **idêntica**, travado por teste;
- as duas listas são arquivos de dados, escolhidos por perfil, e trocá-las não exige mudar código;
- junção e partição só acontecem quando o dicionário decide, e o teste cobre os dois casos que
  **não** devem acontecer (`Xue-Fierro`, `some` → `so`+`me`).

**Testes.** `test_palavra_desconhecida_sai_identica_e_marcada`;
`test_o_nome_proprio_hifenizado_nao_e_juntado`;
`test_a_palavra_boa_que_decomporia_nao_e_partida`.

### O que entrou em 2026-08-25: as duas listas, e uma partição recusada

Entrou a metade de **dados** do item, e ela é a que o critério de aceite descreve como *"as duas
listas são arquivos de dados, escolhidos por perfil, e trocá-las não exige mudar código"*:

| arquivo | palavras | de onde |
|---|---:|---|
| `assets/lexico/idioma.txt.gz` | 10.002 | as listas entregues, o que começa em minúscula |
| `assets/lexico/nomes.txt.gz` | 150.186 | as mesmas listas, o que começa em maiúscula |

`cvoff-texto-lexico` empacota uma pasta de listas nos dois arquivos, e reconstruir dá byte a byte
o mesmo resultado. Quem as consome hoje é `text/dicionario.py` — que **não** é este item, e cujo
cabeçalho explica a diferença. Uma lista foi **recusada por estar corrompida**, e o motivo está no
cabeçalho do comando: `MegaDatabase(Jogadores with dot).txt` traria 39.409 palavras falsas como
`Cortesulio`, e palavra falsa no léxico é pior que palavra faltando — a que falta só deixa de
corrigir, a falsa vira **alvo**.

**A partição de colada foi medida, e ela não paga neste acervo.** O item a prevê (`ofthe` → `of`
`the`), e a régua é a certa — só parte o que não está no dicionário. Sobre 40 páginas de 11
livros: **0 partições certas contra 5 erradas**, e as erradas vêm dos nomes — `carrying` vira
`carr ying`, porque `Carr` e `Ying` são sobrenomes de jogador. As colagens reais (`ofthe`,
`timefor`) têm metade com menos de 4 letras, e baixar esse piso é exatamente o que abre a porta
para as cinco. Fica **fora** até haver referência que a justifique; o número está em
`docs/metrics/texto_dicionario.json`.

### Depois, no mesmo dia: as bases de PGN entram na lista de nomes

A tabela acima é a **primeira** empacotagem. No mesmo 2026-08-25 as bases de partidas entraram na
lista de nomes, e o que está no disco hoje é isto:

| arquivo | palavras | o que mudou |
|---|---:|---|
| `assets/lexico/acervo.txt.gz` | 7.588 | nada neste passo |
| `assets/lexico/idioma.txt.gz` | 10.010 | +8 |
| `assets/lexico/nomes.txt.gz` | **349.565** | **+199.379** |

Desses 349.565 nomes, **199.104 (57,0%) só existem nas bases de PGN** — nenhuma das listas
anteriores os trazia. E a conta se inverteu: os nomes que **só** vêm da MegaDatabase caíram para
**1.433 (0,4%)**, contra os 75.872 (51%) que a empacotagem anterior media.

De onde saem: 6 bases de `pgn_database/` mais os PGN de `PGN/` e `PGN_fase2_20260822/` — 18,3 GB,
21.232.058 partidas, sete campos de cabeçalho (`White`, `Black`, `Event`, `Site`, `Annotator`,
`Composer`, `Source`), 1.850.926 valores distintos, 362.273 tokens aceitos contra 1.281.942
recusados.

**Só o que começa em maiúscula entra**, e os 8.024 tokens minúsculos ficam de fora com o motivo
medido: não são palavras nem nomes — são handles de servidor de xadrez e códigos de torneio
(`hiredgoon`, `dXsGKXJU`, `beercan`, `ch-IBCA`, `op-FIDE`). Eles entrariam em `idioma.txt.gz`, que
é a lista que vale mesmo com `carregar(nomes=False)`, e deixá-los de fora não custou nada
mensurável: as quatro palavras que o léxico novo passa a aceitar e a camada desmente vêm **todas**
de nome maiúsculo.

**O resultado, e ele é o contrário do que o tamanho sugere.** Medido sobre 36 folhas de 4 livros de
camada editorada, 2.036 tokens, contra a camada da própria página:

| | correções tentadas | confirmadas pela camada | **não** confirmadas |
|---|---:|---:|---:|
| léxico antigo | 9 | 6 | **3** |
| léxico com PGN | 6 | 6 | **0** |

O léxico maior não corrige *mais*: corrige **menos e erra menos**. `escolher()` devolve `None`
quando a palavra já é conhecida, então um nome a mais no léxico **impede** uma tentativa de
correção — e nas 36 folhas as três tentativas impedidas eram todas erradas (`afer`→`aTer`,
`pate.`→`Date.`, `p:te:`→`oTte:`).

**O custo, publicado junto:** quatro leituras erradas que o léxico novo passa a aceitar como
palavra (`certal`, `afer`, `pate.`, `gande`). Duas delas o léxico antigo também não consertava —
ele as *piorava* —, e as outras duas ele também deixava passar. Saldo nestas 36 folhas: nenhuma
saída piorou. A amostra é pequena, e o relatório diz o que isso implica: o efeito de esconder erro
cresce com o tamanho do léxico, e o de evitar correção errada não. **Remedir quando houver conjunto
maior.**

**O que esta atualização não alcança**, e está escrito no relatório: nome acentuado. As bases de
PGN são ASCII — `Prokes` está lá, `Prokeš` não —, e por isso ela não move o par `š`/`Š` da S-211.

Números, conjunto e reprodução em [`docs/metrics/texto_lexico_pgn.json`](metrics/texto_lexico_pgn.json).
**Um clone limpo não reconstrói estes dois `.txt.gz`**: as listas de origem vivem em
`Lista de Palavras/`, que não é versionada — ver `assets/lexico/PROCEDENCIA.md`.


### O que fechou o item em 2026-08-26: `text/lexico.py`, a sinalização e a junção

**O módulo nasceu tirando código de `dicionario.py`, e não escrevendo código novo.** A fronteira
entre os dois é o que autoriza os dois a existirem, e ela agora é estrutural em vez de estar só
escrita:

    lexico.py       o que o dicionário SABE, e o que ele DECIDE sozinho
                    -- a lista, a palavra desconhecida, a hifenizada da quebra de linha
    dicionario.py   o que ele DESEMPATA entre os candidatos que o modelo já pôs no topo

`carregar`, `conhecida`, `e_palavra`, `palavras_de` e `desconhecidas` **mudaram de arquivo, não de
comportamento** -- `dicionario` as importa e reexporta, e as medições da S-209 e da S-266 não se
movem. Duas cópias de `e_palavra` divergiriam no primeiro ajuste, e a divergência sairia como marca
na tela discordando da correção no texto.

**O perfil virou dado, que é o critério de aceite.** `PERFIS` mapeia nome -> tupla de arquivos, e
acrescentar uma lista é acrescentar uma linha ali. Os quatro: `completo`, `sem-nomes`, `so-idioma`,
`so-acervo`.

#### A sinalização precisou de uma porta mais larga que a da correção, e o motivo é o exemplo do próprio item

`e_palavra` proíbe **qualquer dígito** -- guarda certa no caminho da *correção*, e é a cicatriz que
esta spec registra: lance maltratado não pode virar palavra. Só que a mesma proibição derruba o
exemplo com que este item abre:

    Bib1i0g[aPhY     dois dígitos entre dez letras -- e `e_palavra` o descarta antes de olhar

Então o item entregaria uma sinalização que não sinaliza o caso que a motiva. **A pergunta certa
não é "tem dígito?", é "isto é notação?"** -- e essa já tinha sido respondida com medição pela
S-208. `suspeita` troca o veto de dígito por `notacao.peso_de_notacao`, e `sinalizar` é a entrada
do item; `desconhecidas` fica como está, com a porta estreita, porque é ela que o editor usa desde
a S-266 e mudá-la em silêncio mudaria o que a aba sublinha.

**O que autoriza duas portas é o custo de errar ser diferente dos dois lados**: marcar um lance por
engano custa um sublinhado que a pessoa ignora; *corrigir* um lance por engano custa um lance
reescrito no PGN.

#### O alarme falso foi remedido aqui, e ele confirma o número de lá

Sobre 5 livros de camada **editorada** -- onde o texto está certo, e portanto toda marca é falso
alarme --, 4.038 linhas, 2.918 tokens candidatos:

| perfil | listas | alarme falso |
|---|---|---:|
| `completo` | acervo + idioma + nomes | **5,65%** |
| `sem-nomes` | acervo + idioma | 6,79% |
| `so-acervo` | acervo | 7,09% |
| `so-idioma` | idioma | **60,01%** |

**A S-209 citou 5,8% com os nomes e 12,1% sem, *medido lá*. Aqui o `completo` dá 5,65%** -- a
direção e quase a magnitude se confirmam, e a regra nº 1 desta spec fica satisfeita com número
próprio.

**E um achado que o plano não previa: a lista de idioma sozinha não serve neste acervo.** 60% de
alarme falso, contra 7,09% do acervo sozinho. As 10.010 palavras de `idioma.txt.gz` são de listas
de fora e não cobrem os oito idiomas das páginas; quem carrega o peso é `acervo.txt.gz`, que saiu
da camada editorada destes livros. Não muda decisão nenhuma -- o padrão é `completo` --, mas
desmente a leitura de que as duas listas empacotadas são a espinha do léxico.

#### A junção fecha, e o terceiro guarda é o que salva a prosa de xadrez

As três condições: a linha da esquerda termina em hífen, **a junção sem o hífen está no léxico**, e
**a forma com o hífen não está**.

A segunda recusa `Xue-` + `Fierro` e `Saint-` + `Amant`, que são os dois casos que o critério de
aceite nomeia. A terceira não estava no plano e é a que mais trabalha neste acervo: **das 5 quebras
hifenizadas das camadas editoradas, as 5 são termo de xadrez ou lance** -- `f-pawn`, `a-pawn`,
`h-file`, `h6-h5`, `a2-♗` --, e três delas *juntariam* (`fpawn`, `apawn` e `hfile` estão na lista,
porque saíram da camada do próprio acervo). Sem a terceira condição, a passada apagaria a grafia
que o livro escolheu na construção mais comum da prosa de xadrez.

**A população da hifenização não está na camada editorada, e a medição teve de ir buscá-la.** As
camadas editoradas do acervo vêm de conversão de ebook: **5 quebras em 4.038 linhas**, e as 5 são
as de xadrez do parágrafo acima. Onde a hifenização de diagramação mora é o livro tipografado de
coluna justificada, lido pelo classificador -- e ali, em 8 folhas do `AAGAARD` e do `Euwe`
(466 linhas), **9 quebras hifenizadas e 2 junções**: `keines-`+`wegs` e `ei-`+`nen`, as duas
certas.

**As 7 recusadas são, na maioria, quebras legítimas cujo segundo pedaço o OCR leu errado**
(`s♔ne1l`, `Co11e-`, `m6g-`): o léxico não confirma a junção, e por isso não junta -- que é a regra
do item funcionando, e não uma falta dela. O teto da junção neste acervo é, portanto, o **teto da
leitura**: ela conserta a quebra quando as duas metades saíram legíveis, e cala quando não. Numa
folha em que o CER caia, a junção sobe junto, sem uma linha de código.

`cvoff-texto-lexico --medir --com-glifo` refaz as duas tabelas;
[`docs/metrics/texto_lexico.json`](metrics/texto_lexico.json) as guarda.

**Sonda.** `simbolo:chess_diagram_ocr.text.lexico:carregar`,
`arquivo:assets/lexico/idioma.txt.gz`.

---

## S-210 · A camada de texto invisível: o PDF pesquisável ✅ implementada (2026-08-26)

**Problema.** Os livros do acervo ou não têm camada de texto, ou têm uma que erra a notação
inteira. Um leitor não consegue buscar `Nf3` num livro de xadrez — que é a coisa mais óbvia a
querer buscar num livro de xadrez.

**Solução.** Uma camada de texto invisível sobre a página, no mesmo desenho do `searchable_pdf`
de lá: **a página não muda um pixel**, e o que se acrescenta é texto sem tinta, posicionado sobre
cada box.

Há um caminho vizinho e mais barato que serve a um subconjunto dos livros, e ele vale ser
mencionado porque a decisão entre os dois é do dono: quando o PDF **já é digital** e o defeito é
só de mapeamento (fontes Type0/Identity-H em que o produtor escreveu `U+FFFD` para cada
figurina), dá para reescrever **só a tabela `ToUnicode`** e o texto passa a copiar e buscar
certo, sem OCR nenhum. Medido lá: 216 pares (fonte, glifo) marcados assim no Yusupov, 101 no
Aagaard.

**Duas travas herdadas, e as duas são de honestidade:**

- **propõe, marca, não reescreve calado** — glifo cuja votação não fecha continua `U+FFFD` e vai
  para o relatório com o motivo. Trocar `U+FFFD` por um palpite errado é pior que deixar como
  está: o losango pelo menos se vê;
- **o glifo é classificado de várias amostras, não de uma** — um glifo aparece dezenas de vezes
  no livro, e o símbolo só entra na tabela com votação folgada.

**A fonte é um bloqueio conhecido.** A camada invisível com figurinas precisa de uma fonte que
tenha os glifos de xadrez, e **nenhuma fonte é copiada para cá antes de a licença ser
conferida** — ver a lista de riscos do `ROADMAP_TEXTO`. Sem fonte redistribuível, o item entrega
a camada só para o alfabeto latino e registra o limite.

**Critério de aceite.**

- a página do PDF de saída é **pixel a pixel idêntica** à de entrada, conferido comparando os
  pixmaps;
- a busca por uma palavra da página a encontra, e o retângulo devolvido cobre a palavra;
- glifo sem votação folgada não entra, e aparece no relatório com o motivo;
- o modo `dry-run` diz o que faria sem escrever nada.

**Testes.** `test_a_pagina_nao_muda_um_pixel`;
`test_a_busca_encontra_a_palavra_no_lugar_certo`;
`test_o_glifo_sem_votacao_folgada_nao_entra`; `test_o_dry_run_nao_escreve`.
> **O caminho vizinho não tem material neste acervo, e a medição é o que sustenta a recusa
> (2026-08-26).** A spec descreve o `ToUnicode` como o caminho mais barato para o PDF já digital
> cujo defeito é só de mapeamento, e cita 216 pares no Yusupov e 101 no Aagaard -- *medido lá*.
>
> Medido aqui, 40 folhas de cada um dos 14 primeiros livros do acervo: **zero `U+FFFD`.** Nenhum,
> em nenhum deles. O defeito de mapeamento **deste** acervo é outro, e a S-211 já o tinha medido:
> a camada não devolve losango, devolve o **codepoint cru da fonte de xadrez** -- `2.♘xd4` sai como
> `2.l0xd4` no AAGAARD. Não há o que reescrever numa tabela que existe e está preenchida com outra
> coisa.
>
> Então o reescritor **não foi construído**, e `pdf_pesquisavel.pares_sem_mapeamento` é a medição
> que sustenta a recusa -- regra nº 1 desta spec. Ela fica no disco porque um acervo com um livro à
> la Yusupov faria o número deixar de ser zero, e `cvoff-texto-pesquisavel` a roda em toda corrida:
> se um livro trouxer pares, ele os imprime.
>
> **A trava herdada mudou de matéria, e não de regra.** *"Glifo cuja votação não fecha continua
> `U+FFFD` e vai para o relatório com o motivo"* existe porque trocar o losango por um palpite
> errado é pior que o losango, que pelo menos se vê. A matéria aqui é a **linha lida**, e a regra
> cai igual: linha abaixo de `PISO_DA_CAMADA` não entra, e o relatório diz por quê. O argumento é o
> mesmo e é mais forte, porque a camada é **invisível**: quem busca `Nf3` e recebe um acerto
> acredita no acerto, e não há nada na tela para desmenti-lo. O piso é o `ocr.MIN_CONFIDENCE` da
> S-42, e não um número novo.
>
> **A camada é por LINHA, e é isso que faz o segundo critério de aceite ser verdade.** A `camada`
> da S-253 escreve por bloco, e ali é o certo -- o `DocumentoRico` só tem bbox de bloco. Aqui a
> `PaginaLida` tem bbox de linha, e com um retângulo de parágrafo a busca acharia a palavra e
> devolveria o parágrafo inteiro, que é a mesma coisa que não saber onde ela está. Medido nas
> folhas 58-60 do `AAGAARD`: a busca por `Nf3` devolve **um** retângulo de 12,4 x 11,0 pt --
> tamanho de palavra.
>
> **E a fonte, que a spec declara como bloqueio, foi contornada sem quebrar a declaração.** A base
> 14 do PDF cobre Latin-1 e não tem `♘`; nenhuma fonte é copiada para cá antes de a licença ser
> conferida, e isso continua valendo. O que mudou é o que se escreve: **a camada é um índice, e não
> uma renderização**, então `♘` entra nela como `N`. A página continua mostrando a figurina; o que
> muda é o que a busca encontra -- e "buscar `Nf3` num livro de xadrez" é literalmente o problema
> com que o item abre.
>
> A ambiguidade está declarada: a letra depende do idioma (`N`/`S`/`C`/`T`), e a tabela escolhe o
> **inglês**, que é a única convenção comum entre os oito idiomas do acervo. `--sem-figurinas`
> desliga a troca, com a contagem ao lado.
>
> Medido nas folhas 58-60 do `AAGAARD`: 122 linhas na camada, **168 figurinas como letra**, 65
> linhas fora pelo piso, 31 caracteres fora da fonte. Sem a troca, as 168 entrariam nos 31.
>
> **Uma terceira coisa que a implementação teve de decidir, e que a spec não previa: a folha que já
> tem camada.** Não dá para tirar a de origem -- num PDF digital ela **é** o conteúdo da página, e
> removê-la mudaria o pixel, que é o primeiro critério de aceite. Então a nossa **soma** à dela, o
> relatório conta as folhas em que isso aconteceu e avisa, e `--so-sem-camada` pula essas folhas
> para quem quiser um livro sem texto duplicado. O padrão escreve, porque a S-211 mediu que a
> camada de origem não representa figurina: para notação ela não é alternativa à nossa.
>
> Os quatro critérios de aceite viram quatro testes com o nome que a spec deu, e o primeiro compara
> os **pixmaps** de antes e depois -- não o código.


**Sonda.** `simbolo:chess_diagram_ocr.text.pdf_pesquisavel:escrever_camada`.

---

## S-211 · O modelo de página: coluna → bloco → linha → texto | diagrama | tabela ✅ implementada (2026-08-24)

**Problema.** Hoje `service.RecognizedDiagram` é o que a UI recebe, e **a página não existe como
objeto**. Cada destino — PGN, dataset, fila de revisão — parte do mesmo diagrama, e isso funciona
enquanto o produto for diagrama. Com texto, coluna e tabela, três consumidores passariam a
recompor a página cada um do seu jeito, que é exatamente o defeito que a Fase 6 deste projeto
consertou quando havia duas telas implementando o pipeline duas vezes.

**Solução.** `text/pagina.py`, com um `PaginaLida` imutável:

```
PaginaLida
├── colunas: tuple[Coluna, ...]
│   └── elementos: tuple[Paragrafo | Diagrama | Tabela | Tarja, ...]
├── cabecalho: Linha | None
├── rodape: Linha | None
└── numero_impresso: int | None      ← já existe: pdf_text.running_page_number
```

Cada elemento carrega bbox, confiança e **procedência** (camada de texto, glifo, RapidOCR,
humano). O `RecognizedDiagram` de hoje passa a ser o conteúdo de um `Diagrama`, sem mudar de
forma — quem já consome continua consumindo.

**Nada aqui decide apresentação.** A ordem de leitura é do domínio; como desenhar é da interface,
e a regra que organiza este projeto vale igual.

**Critério de aceite.**

- `PaginaLida` é imutável e serializável para JSON sem perda;
- todo elemento tem bbox, confiança e procedência — sem exceção, travado por teste;
- os três consumidores (PGN, dataset, fila) leem de `PaginaLida` e nenhum recompõe a página;
- uma página só de diagramas produz uma `PaginaLida` equivalente ao que a UI recebe hoje, e o
  teste prova a equivalência.

**Testes.** `test_todo_elemento_traz_bbox_confianca_e_procedencia`;
`test_a_pagina_serializa_e_volta_sem_perda`;
`test_a_pagina_so_de_diagramas_equivale_ao_de_hoje`;
`test_nenhum_consumidor_recompoe_a_pagina`.

**Sonda.** `simbolo:chess_diagram_ocr.text.pagina:PaginaLida`.

### O que entrou em 2026-08-24, e o que **não** entrou

Entrou: `PaginaLida` e os quatro blocos em `text/pagina.py`; o leitor de página em
`text/leitor.py`, com os dois motores; o modelo do editor em `text/documento.py`; o comando
`cvoff-texto-pagina`; e a aba **Texto** em `ui/texto_panel.py`, que é o primeiro consumidor.

**Não** entrou o terceiro critério de aceite — *"os três consumidores (PGN, dataset, fila) leem de
`PaginaLida` e nenhum recompõe a página"*. O PGN, o dataset e a fila continuam partindo de
`service.RecognizedDiagram`, exatamente como antes. Não é esquecimento e não é bloqueio técnico: é
uma migração de três caminhos medidos que não cabe no mesmo passo que criar o modelo, e fazê-la
junto significaria mexer neles sem nada para comparar. `test_nenhum_consumidor_recompoe_a_pagina`
**não existe** pelo mesmo motivo — ele passaria hoje só por vacuidade.

O item fica marcado como implementado porque a sonda é o modelo e o modelo está de pé, e este
parágrafo é o que impede que "implementado" seja lido como "os quatro consumidores migraram".

### Dois defeitos que só apareceram com a página inteira, e os dois eram de ordem

Nenhum deles era de reconhecimento, e é isso que os torna interessantes: o classificador acerta
99,8% em `lower_l` na base, e mesmo assim a página saía ilegível.

1. **A escala era medida antes de excluir o diagrama.** A escala é mediana ponderada por massa de
   tinta, e as peças de um tabuleiro impresso têm 86 px contra 23 de uma letra. Medido na página 20
   do `Reinfeld 1001`: escala 86, e a peneira de área descartou 438 das 441 componentes da página.
   A página lia **uma linha**. Correção: `leitor.escala_fora_dos_diagramas`.

2. **A linha era quebrada antes de a coluna existir.** `GlyphRecognizer.read` é um leitor de
   **faixa**: ele agrupa em linhas sobre a imagem toda, e numa página de duas colunas as duas
   linhas que compartilham a banda viram uma. Medido na página 58 do `AAGAARD`, contra a camada de
   texto da mesma página: **CER 0,7861 com o texto intercalado, 0,1559 depois de a coluna ser
   achada nas caixas de caractere**. Correção: `leitor.segmentar`.

### O quarto defeito, e o maior: a caixa alta é decidida por uma informação que o modelo não recebe

Oito letras do alfabeto latino — `c o s u v w x z` — têm maiúscula e minúscula com a **mesma
forma**, mudando só o tamanho. E `ClassificadorDeGlifo._entrada` faz `cv2.resize(recorte, (32,
32))` em todo glifo: depois disso as duas são a mesma imagem. O modelo não erra por ser fraco; ele
erra porque a informação que decide foi apagada antes de ele ver o recorte.

Diagnosticado em 13 páginas de 3 livros de camada **editorada**, 212 linhas casadas contra a
camada, 617 substituições:

| família | n | o que é |
|---|---:|---|
| `♔`→`K`, `♖`→`R`, `♕`→`Q` | 192 | **não é erro** — o glifo acerta a figurina, a camada usa ASCII |
| caixa alta (`S`→`s`, `V`→`v`, `W`→`w`…) | 241 | isto |
| caractere espúrio onde há espaço | 96 | segmentação |
| dígito lido como letra (`0`→`o`) | 3 | — |

Duas medições fecham o caso: **a classe certa está em rank 2 em 237 de 237 casos** — o modelo diz
`S` com 0,96 e `s` com 0,03, sempre nessa ordem —, e **a altura separa**: minúscula mede 1,00 da
mediana de altura da linha, maiúscula 1,41.

`text/caixa_alta.py` escolhe entre as duas classes do par pela altura do box relativa à x-height
da **linha** (e nunca da página: um título em corpo maior promoveria todas as letras). Medido
ponta a ponta pelo caminho de produção (`docs/metrics/texto_caixa_alta.json`):

    CER 0,1434 -> 0,1114   (-22,3%)   11 páginas melhoram, nenhuma piora, sem custo de tempo

**Entra ligado** — o único dos três interruptores da página que entra assim. O corte é 1,25,
escolhido no **meio do platô** (1,10 a 1,30 empatam até o quarto decimal; 1,40 e 1,50 degradam), e
não no mínimo: o meio do platô é o que tem margem dos dois lados.

**A ressalva, e ela é séria.** A amostra de maiúscula tem 25 casos contra 1.001 de minúscula —
prosa é quase toda minúscula. O que está bem medido é que minúscula fica em 1,00; o lado que
decide se o corte rebaixa maiúscula legítima está medido em 25 casos.

### O quinto: o apóstrofo, e um item cujo CER não se move de propósito

Mesmo defeito de fundo do anterior, outra geometria. `'`, `,` e `.` só diferem por **onde
assentam na linha**, e o recorte é o bbox apertado: isolados e redimensionados, são a mesma mancha.
`Black's` saía `Black,s`.

Medido nas mesmas 13 páginas, sobre 355 marcas finas casadas com a camada:

| marca | n | topo do box, em alturas de linha |
|---|---:|---|
| alta (`'` `’` `”`) | 13 | p10 0,00 · mediana 0,03 · p90 0,03 |
| baixa (`,` `.` `;` `:`) | 342 | p10 0,79 · mediana 0,85 · p90 0,87 |

Não há sobreposição; o corte fica em 0,30. **Uma segunda guarda entrou depois de dois falsos
positivos**: `Qualquer` saía `Qua'quer` porque um `l` que o classificador já lia como vírgula
também começa no topo da linha. A marca de verdade vai até 0,35 da altura da linha e a letra mede
0,97, então o teto de altura fica em 0,50 — no meio do vão.

**O teto deste item é baixo, e a spec diz por quê.** O modelo não tem as aspas curvas: `’ ‘ “ ”`
não são classes. Dos 28 erros de marca fina, **13 são de classe ausente** — não há resposta que o
decodificador pudesse dar. O módulo escreve `'`, que é o certo para **ler**, e continua contando
como erro contra uma camada que escreveu `’`.

    CER 0,1114 -> 0,1115    (ruído, e previsto)
    palavras quebradas por vírgula ou ponto no meio: 10 -> 2

**Entra ligado, e não pelo CER.** É o primeiro item deste plano cuja justificativa não é a régua
principal: `Black,s` está errado de um jeito que salta aos olhos, e `Black's` não. Quem julgar o
item pelo CER vai concluir, corretamente, que ele não mexeu no CER.

### O sexto: `:`, `;` e `=` nunca chegavam inteiros ao classificador

    caractere   na camada   no glifo   recall
    :                   9          0       0%
    ;                   4          0       0%
    =                  14          0       0%
    .                 362        469     130%     <- os dois-pontos partidos ao meio

Zero nos três, e **não por falta de classe**: `:` tem 1.449 amostras na base, `;` tem 225 e `=`
tem 164. O modelo sabe os três; ninguém nunca os mostrou a ele inteiros. Os três são **dois
contornos**, e chegavam separados — `defense: he` saía `defense.. he`, e `g1=♕` saía `g1 ♕`.

`unir_pingos` (S-185) une pingo a uma **base alta**, e a docstring dela já dizia o que ficava de
fora: *"dois pontos e ponto e vírgula, que não têm base alta com que se unir"*. `text/empilhados.py`
é essa exceção virada de regra.

**As duas metades chegam por caminhos diferentes.** O ponto de `:` passa pela peneira da S-185; a
barra do `=` **não** — ela tem proporção 8 a 12 de largura sobre altura, e `PROPORCAO_MAXIMA` corta
em 6,0 para separar glifo de filete. `barras()` recolhe o que aquela régua rejeitou, e **só devolve
ao texto o que casa com um par vertical**: barra sozinha continua sendo filete. Medido: 38
contornos rejeitados, 28 com parceiro — isto é, 14 pares, exatamente os 14 `=` da camada.

**E fundir não bastou.** O resize para 32x32 apaga a **proporção** junto com o tamanho, então duas
barras largas e dois pontos viram a mesma imagem: metade dos `=` saía `:`. Medido, `=` fica entre
2,40 e 2,67 de largura sobre altura e `:`/`;` entre 0,24 e 0,25 — fator de dez, e o corte fica no
quadrado.

    recall depois:  :  9/9      ;  4/4      =  14/14
    CER 0,1115 -> 0,1078   (-3,3%)   7 páginas melhoram, nenhuma piora

A medição está em `docs/metrics/texto_pagina.json`, e ela também é o que decidiu **desligar** o
modo bloco da S-188 na página: ele custa ~50x o tempo e, no livro nativo digital, piora 22,5%.

### O terceiro defeito, e este era de premissa: a camada de texto não codifica figurina

`MOTOR_PADRAO` nasceu `auto`, preferindo a **camada de texto do PDF** onde ela existisse -- 25 dos
42 livros --, com o argumento de que a camada não é OCR e vale 1,0 de confiança. O argumento vale
para prosa e é falso para notação de xadrez. Medido em 2026-08-24 sobre 16 páginas de 4 livros que
**têm** camada:

| fonte | figurinas Unicode (♔-♟) | notação ASCII (Nf3, Bxd4) |
|---|---:|---:|
| camada de texto | **0** | 212 |
| classificador de glifo | **360** | 52 |

Zero. Onde o livro imprime `♘`, a camada traz o codepoint cru da fonte de xadrez: `2.♘xd4 dxc2!`
sai como `2.l0xd4 dxc2!`, e `33.♕a6!` como `33.fta6!`. O texto **parece** prosa e passa por
qualquer verificação de "esta página tem texto?" -- e foi por isso que a premissa atravessou a
primeira versão sem ninguém tropeçar nela.

E não há convenção comum: nos mesmos 4 livros a camada usa três codificações diferentes. O padrão
passou a ser `glifo`; `camada` continua acessível, e `auto` é o glifo com a camada como reserva
declarada para quando os pesos não carregam.

---

# Fase 31 — O que faz a base crescer

> Este projeto já tem o laço para diagramas: reconhecer → corrigir no tabuleiro → `Ctrl+S` →
> dataset. Para caractere o laço não existe, e sem ele as 700 mil imagens são um número que só
> perde valor com o tempo.

## S-212 · A fila de revisão de caractere ✅ implementada (2026-08-26)

**Problema.** Uma página tem ~2.000 caracteres. A 98% de acerto, são 40 erros por página, e
achá-los a olho é o que torna a revisão inviável. A S-22 resolveu isso para diagramas ordenando
por **valor de informação**; para caractere a fila não existe.

**Solução.** `text/fila.py`, ordenando por valor de informação, e a régua principal já está
definida na S-189: **a divergência entre a leitura por linha e a por caractere**. Medido lá, é
onde o erro se concentra.

Duas coisas que a série de fases de lá mediu e que economizam trabalho aqui:

- **a margem não ganha da confiança.** Duas fases de lá concluíram que sim e estavam medindo
  errado; a F47 refez com os defeitos corrigidos e a margem perdeu. Não implementar ordenação por
  margem sem antes medir aqui;
- **a fila sobrevive a salvar e reabrir.** Lá, salvar zerava a fila, e o defeito estava
  documentado como desenho por meses.

**Critério de aceite.**

- a fila ordena por divergência, e o teste prova que o item de maior divergência vem primeiro;
- salvar e reabrir preserva a fila, incluindo o que já foi revisado;
- a cor do box na tela e a posição na fila **concordam** — lá elas discordaram, e um box verde no
  topo da fila destrói a confiança na fila inteira;
- a ordenação por margem só entra com tabela ao lado.

**Testes.** `test_a_fila_ordena_por_divergencia`;
`test_salvar_e_reabrir_preserva_a_fila`;
`test_a_cor_do_box_e_a_posicao_na_fila_concordam`.
> **A régua não foi reinventada, e essa é a decisão do item (2026-08-26).** A "divergência entre a
> leitura por linha e a por caractere" já é um número: a S-189 a transformou em confiança --
> `max` quando as duas concordam, `min` quando divergem. Ordenar por `1 - confiança` **é** ordenar
> por divergência, com a calibração que já foi medida. Um segundo escalar de divergência daria
> dois números para a mesma pergunta, e a primeira vez que discordassem não haveria como dizer
> qual estava certo.
>
> **E é isso que faz a cor e a posição concordarem por construção, e não por disciplina.** A cor
> sai de `documento.faixa_de_confianca`; a fila ordena pelo mesmo número, pela mesma função. O
> critério de aceite negativo -- *nunca um box verde no topo* -- não depende de ninguém lembrar.
>
> **A tentação recusada foi a banda de peso da S-22.** Pôr a divergência numa faixa acima da
> confiança poria um box divergente de 0,99 na frente de um de 0,10, isto é, um box verde no topo
> -- exatamente o que o item proíbe.
>
> **Mas a admissão não é a ordenação, e a primeira versão perdia informação por confundi-las.**
> Um box em que o glifo leu `c`, o leitor de linha leu `e` e a confiança combinada ficou em 0,90
> tem faixa `tranquilo` e **não entrava na fila** -- só que 0,90 divergente quer dizer que as
> *duas* leituras estavam confiantes e ainda assim discordaram, que é a informação mais forte que
> a página produz. Ele passou a entrar, e entra no **fim** da fila, onde a confiança dele o põe.
>
> **A régua muda quando o leitor de linha não roda, e a fila diz qual usou.** `modo_bloco` está
> desligado por padrão desde a S-188 (~50x o tempo na página inteira), e sem ele não há segunda
> leitura -- todo box tem `do_glifo == do_bloco`, e a fila ordena pela confiança do classificador
> sozinho. `Fila.regua` declara em qual dos dois mundos ela foi montada, e o valor viaja no JSON.
>
> **A margem ficou de fora, como o item manda.** `ClassificadorDeGlifo.margem` existe e custa zero,
> viaja em `Item.margem` para que a tabela possa ser feita sem remontar a fila, e **não é lida por
> `ordenar`** -- é a recusa que o próprio docstring dela já registrava.
>
> **Duas granularidades, e nenhuma delas mente.** A `PaginaLida` guarda `LinhaLida`; os boxes de
> caractere são consumidos dentro de `linhas_do_glifo` e descartados, e guardá-los custaria ~2.000
> registros por página -- que a S-215 acabou de pôr preço. Então `de_lidos` serve quem tem os boxes
> na mão (o leitor, durante a leitura) e `de_pagina` serve quem tem só o arquivo, e o campo `box`
> (`-1` para linha) diz qual é qual em vez de a fila fingir que são a mesma coisa.
>
> **E `distribuicao` responde a uma pergunta que estava aberta desde a S-242:**
> `documento.CORTE_DE_CONFERIR` (0,75) foi declarado com um comentário dizendo que quem decidiria
> se ele está no lugar certo seria esta S-212. A contagem por faixa é o instrumento.


**Sonda.** `simbolo:chess_diagram_ocr.text.fila:ordenar`.

---

## S-213 · Aplicar a todos os semelhantes ✅ implementada (2026-08-26)

**Problema.** Corrigir um `e` lido como `c` e ter de repetir a correção nos outros 300 é o que faz
uma página custar horas.

**Solução.** `text/semelhanca.py`, reusando o descritor da S-202. E a decisão principal do item
é o critério: **é a imagem, não o caractere lido.** Casar por caractere acharia os 300 `c`
errados, mas junto viriam os `c` legítimos — e o lote os estragaria.

Medido lá, sobre todos os pares de boxes de 9 páginas rotuladas:

| critério | limiar | precisão | cobertura |
|---|---|---:|---:|
| imagem | 0,20 | 98,91% | 64,6% |
| imagem + mesma leitura | 0,20 | **99,29%** | 64,5% |
| imagem + mesma leitura | 0,30 | **99,30%** | 69,1% |

A segunda condição segura a precisão quando se afrouxa o limiar: com ela, ir de 0,20 a 0,30 sobe
4,5 pontos de cobertura de graça.

**A consequência de projeto é a decisão principal, e ela é de interface: um em cada ~145 boxes do
lote sairia errado, então aplicar em silêncio está fora de questão.** O resultado vai para uma
pré-visualização com os recortes à vista, e a lista sai **ordenada por distância** — o duvidoso
fica no fim, que é onde o olho deve parar.

**Critério de aceite.**

- o lote nunca é aplicado sem pré-visualização, travado por teste na função pura que decide;
- a lista sai ordenada por distância crescente;
- o rigor (`estrito` / `normal` / `amplo`) é escolha de cobertura, não de risco, e o documento diz
  isso com a tabela ao lado;
- a precisão medida **neste** acervo está em `docs/metrics/`, e se ficar abaixo de ~99% o item
  entrega a pré-visualização e não o lote.

**Testes.** `test_o_lote_exige_previsualizacao`;
`test_a_lista_sai_ordenada_por_distancia`;
`test_a_mesma_leitura_segura_a_precisao_no_limiar_frouxo`.
> **A tabela foi refeita nesta base, e ela desmente os limiares de lá e confirma a segunda
> condição com folga (2026-08-26).** 3.000 recortes de 299 classes de `training_data/`, amostrados
> por classe com semente 0, par a par completo -- 4,5 milhões de pares:
>
>     limiar |  imagem só          |  imagem + mesma leitura
>            |  precisão cobertura |  precisão cobertura
>      0,03  |  1,0000   0,0599    |  1,0000   0,0599
>      0,10  |  0,9999   0,1124    |  1,0000   0,1124
>      0,14  |  0,9986   0,2180    |  1,0000   0,2180     <- estrito
>      0,18  |  0,9930   0,3055    |  0,9994   0,3055
>      0,22  |  0,9828   0,3829    |  0,9991   0,3829     <- normal
>      0,26  |  0,9569   0,4788    |  0,9983   0,4787
>      0,30  |  0,8276   0,5683    |  0,9971   0,5682     <- amplo
>      0,35  |  0,6983   0,6563    |  0,9968   0,6562
>      0,40  |  0,4540   0,7445    |  0,9969   0,7444
>
> **A segunda condição vale muito mais aqui do que lá.** No projeto de origem ela comprava 0,4
> ponto de precisão; nesta base, no limiar de 0,30, ela leva a precisão de **82,76% para 99,71%**
> -- e a cobertura fica igual até a quarta casa (0,5683 contra 0,5682). Isto é: ela remove quase
> **só** os pares errados. A tabela de lá dizia que ela "segura a precisão quando se afrouxa o
> limiar"; aqui ela é o que torna o afrouxamento possível.
>
> **Os três rigores saem daí, e o critério de aceite passa a ter dentes.** Com a segunda condição
> ligada -- o padrão de `semelhantes` -- os três ficam acima do piso de 99%. **Desligada, só o
> `estrito` fica**, e é por isso que `Placar.entrega_lote` responde por rigor e não por módulo.
>
> **E o limiar de 0,03 -- o `dedupe.LIMIAR_PADRAO` -- foi recusado com número.** A primeira versão
> deste módulo o usava, por ser o único já medido: ele entrega 100% de precisão com **6% de
> cobertura**, isto é, um lote que quase nunca alcança nada. Os dois assuntos usam a mesma régua e
> não o mesmo corte -- lá é quase-duplicata (a mesma renderização com meio pixel de deslocamento),
> aqui é o mesmo glifo que saiu da classe.
>
> **A cobertura é metade da de lá, e a diferença é de material, não de código.** Em 0,18 a precisão
> bate com a que lá se mediu em 0,20 (99,30% contra 98,91%), mas a cobertura é 30,6% contra 64,6%.
> A amostra de lá eram 9 páginas de um livro; esta são 299 classes do acervo inteiro, onde os pares
> da mesma classe são muito mais heterogêneos. Herdar o número de lá teria produzido uma tabela que
> descreve outro material.
>
> **A pré-visualização não é conselho: é tipo.** `aplicar` só aceita uma `Previsao`, e `Previsao`
> só sai de `previsualizar` com `olhada=False`. Um lote sem pré-visualização não é expressável, e
> o teste ainda cobra o valor -- a trava do tipo pega o descuido, a do valor pega a esperteza.
>
> Tudo em `docs/metrics/texto_semelhanca.json`, com a curva inteira ao lado dos três rigores.


**Sonda.** `simbolo:chess_diagram_ocr.text.semelhanca:semelhantes`,
`metrica:texto_semelhanca`.

---

## S-214 · A coleta em quarentena ✅ implementada (2026-08-26)

**Problema.** Quando um livro inteiro passa pela extração, o modelo já diz onde é fraco: são os
caracteres abaixo do piso de confiança. Medido lá, **3.943 deles em 264 páginas** — material de
treino que hoje é jogado fora e que teria de ser recaçado na tela, um a um.

**Solução.** O fluxo tem três etapas, e a do meio é humana:

    extração  ──►  revisao_ocr/<palpite>/  ──►  [você olha]  ──►  base de treino

Corrigir um rótulo é **mover o arquivo de pasta**; descartar é apagá-lo. A promoção lê o nome da
pasta como rótulo — então o que o usuário fizer com o mouse é o que entra na base.

**Gravar direto em `<palpite>/` seria treinar o modelo no próprio erro**, e é a regra nº 2 desta
spec. As duas pontas têm a cicatriz.

Três coisas que a F93 de lá mediu e que servem à etapa humana, e todas entram desde o início
porque nenhuma é cara:

1. **A mesma renderização entrava muitas vezes.** Em PDF digital o mesmo glifo sai byte a byte
   igual, e a pasta enchia de cópias — 300 miniaturas iguais são 300 chances a menos de o intruso
   aparecer. Deduplicar por impressão (S-202).
2. **O teto guardava os primeiros N, que são as primeiras páginas.** Teto de 300 dava 300
   amostras das páginas 1 a 5: uma fonte, um estado de scan. Com amostragem de reservatório, o
   que fica é uma amostra do **livro**.
3. **"Mais duvidoso primeiro" não funcionava**, porque o nome do arquivo carregava página e
   confiança nessa ordem e o Explorer ordenava por página. Trocar a ordem no nome resolve.

Medido lá, no modo "todos": dos arquivos que caem em `revisao_ocr/lower_o/`, **93,7% são um `o`**,
2,6% são outro caractere e 3,7% não têm caractere nenhum ali.

**Critério de aceite.**

- nada é gravado na base de treino por este caminho — só na pasta de revisão, travado por teste;
- a promoção lê o nome da pasta como rótulo e registra procedência `humano` (S-201);
- o teto sorteia por reservatório, e o teste prova que a amostra não é das primeiras páginas;
- o nome do arquivo ordena por confiança quando ordenado por nome.

**Testes.** `test_a_coleta_nunca_grava_na_base_de_treino`;
`test_a_promocao_registra_procedencia_humana`;
`test_o_teto_sorteia_do_livro_inteiro`;
`test_o_nome_do_arquivo_ordena_por_confianca`.
> **O fluxo entrou inteiro, e a etapa do meio continua sendo a mão (2026-08-26).** `coletar` grava
> em `revisao_ocr/<palpite>/` e **não recebe o caminho da base de treino** -- não é disciplina de
> quem chama, é falta de argumento na função. `test_a_coleta_nunca_grava_na_base_de_treino` afirma
> isso sobre o disco, e não sobre a intenção.
>
> **As três lições de lá entraram desde o início, e cada uma tem um teste que não olha o código:**
>
> | lição | como entrou | o que o teste olha |
> |---|---|---|
> | a mesma renderização enchia a pasta | impressão SHA-256 **e** quase-duplicata da S-202 dentro do mesmo palpite | duas cópias e uma quase-cópia viram um arquivo |
> | o teto guardava as primeiras páginas | amostragem de reservatório, semente declarada | a **distribuição de páginas** do que sobrou, e não o algoritmo |
> | "mais duvidoso primeiro" não funcionava | confiança em milésimos com zeros à esquerda, **antes** da página, no nome | ordenar por nome é ordenar por dúvida |
>
> A quase-duplicata só vale **dentro do mesmo palpite**: duas imagens quase iguais lidas de dois
> jeitos são homóglifo, e isso é assunto de `conflitos.py`, não de coleta.
>
> **`promover` lê o rótulo do nome da pasta, e o palpite do modelo não é consultado em lugar
> nenhum dela.** `base_de_treino=None` é o padrão e não grava nada -- uma função que escreve na
> base de treino não deve fazê-lo porque alguém esqueceu um argumento.
>
> **E o `strict=True` de `folder_to_char` é o item, não detalhe.** Sem ele, uma pasta cujo nome não
> decodifica devolve `"?"`, e a promoção **criaria** `training_data/sym_63/` com o que estivesse
> ali dentro -- o defeito da S-180 (127 amostras na classe errada) com o agravante de fabricar a
> classe. Um teste cobra que a régua daqui seja **a mesma** de `dataset.varrer`: mais estrita, a
> promoção travaria material legítimo em formato antigo; mais frouxa, inventaria classe.
>
> **A promoção destrava metade da S-201, e a outra metade continua sendo pergunta do dono dos
> dados.** `procedencia.acrescentar` nasceu aqui -- o módulo só tinha `ler` --, e toda amostra que
> entrar por este caminho entra com livro, página, data e `humano`, porque quem a rotulou moveu a
> pasta com a mão. Os 608 mil recortes que já existem continuam com UUID puro e origem perdida:
> isso é o que trava a S-201 e a S-203, e não é código.
>
> Um detalhe achado ao escrever: um livro do acervo tem **vírgula no nome**, e o CSV de procedência
> não cita campo. Escrito cru, ele partiria a linha em seis campos e `ler` levantaria
> `ArquivoInvalido` sobre um arquivo que o próprio módulo escreveu.


**Sonda.** `simbolo:chess_diagram_ocr.text.coleta:coletar`,
`simbolo:chess_diagram_ocr.text.coleta:promover`.

---

## S-215 · O orçamento por página, e o teto que a varredura respeita ✅ implementada (2026-08-26)

**Problema.** A S-61 mediu ~2,95 s por página só do pipeline de diagramas, e a varredura do
acervo leva ~10 h. OCR de glifo em página inteira **soma** a isso — e o número que ninguém tem é
quanto.

Este item existe para que a descoberta aconteça **antes** de a Fase 30 embarcar, e não depois de
alguém deixar uma varredura rodando a noite inteira.

**Solução.** `cvoff-texto-custo`, que mede por etapa — binarização, contornos, classificação,
leitura por linha, coluna — sobre uma amostra de páginas de cada livro, e grava o perfil.

E o resultado alimenta uma decisão de escopo que precisa ser tomada com o número na mão:

| política | quando faz sentido |
|---|---|
| texto em toda varredura | se o custo somado ficar abaixo de ~1,5× do de hoje |
| texto sob demanda, por página | se ficar entre 1,5× e 4× |
| texto como comando separado, fora da varredura | acima disso |

**A trava é a mesma do `cvoff-census --fail-on-loss`**: um `--baseline` que falha quando o custo
por página piora além de uma margem. Regressão de desempenho é regressão.

**Critério de aceite.**

- o perfil por etapa está em `docs/metrics/texto_custo_<data>.json`, com o `n` de páginas;
- o número aparece nas duas unidades que importam: segundos por página, e horas para o acervo;
- a política escolhida está registrada **com o número que a escolheu**;
- `--baseline` falha quando o custo piora, e o teste prova que falha.

**Testes.** `test_o_perfil_separa_as_etapas`;
`test_o_baseline_falha_quando_o_custo_piora`;
`test_o_relatorio_traz_as_duas_unidades`.
> **O número saiu, e ele escolhe `sob-demanda` (2026-08-26).** 18 páginas de 6 livros, amostradas
> por passo constante ao longo de cada livro, com as duas pontas medidas na mesma corrida:
>
>     hoje (só diagramas)   0,377 s/página     1,26 h para o acervo
>     o texto soma          0,456 s/página     1,52 h
>     total                 0,833 s/página     2,78 h      fator 2,21x
>
> **Fator 2,21 cai na faixa do meio da tabela deste item, e a política é `sob-demanda`** -- texto
> por página, e não em toda varredura.
>
> **O `hoje` não é o 2,95 s/página da S-61, e nenhum dos dois está errado.** Aquele perfil é de uma
> página do `Karpov` com **6 diagramas**, e a inferência -- que é 76% do tempo -- escala com o
> número deles. A amostra daqui atravessa 6 livros com passo constante, e a média de diagramas por
> página é muito menor. Os dois números descrevem páginas diferentes, e é por isso que o fator é
> medido contra a **mesma amostra** e não contra o número arquivado.
>
> **A primeira medição errou com o sinal cômodo, e vale registrar.** Ela deixava
> `iter_pdf_diagrams` carregar o `.pt` de peças por página -- 18 linhas de "Modelo carregado" no
> log de 18 páginas. Uma varredura de verdade paga essa carga uma vez por livro, então contá-la por
> página **inflava o lado `hoje`** e fazia o fator sair menor do que é. Corrigido com o mesmo
> `model_session` que a fila da S-22 usa.
>
> **E o perfil por etapa desmentiu a intuição.** Não é o modelo o gargalo do texto:
>
>     etapa              s/página   chamadas/página
>     renderizacao         0,0452       1,00
>     deteccao             0,1719       1,00
>     binarizacao          0,0056       1,00
>     contornos            0,1862       4,72     <- a maior etapa de texto
>     colados              0,0037       1,00
>     linhas               0,0027       5,00
>     classificacao        0,1557      85,61
>     correcoes            0,0299     175,83
>     leitura_de_linha     0,0000       0,00     <- desligada por padrão (S-188)
>     coluna               0,0005       1,00
>     nao_instrumentado    0,0721
>
> **`contornos` (0,186) custa mais que `classificacao` (0,156)** -- a segmentação, e não a rede. E
> as duas etapas que mais pesam do lado do texto (`contornos` e `correcoes`) **não existiam na
> primeira lista de etapas**: elas caíam no resíduo, que saiu com 0,267 s/página, 32% da folha. Um
> perfil cujo maior número é "não sei" não serve para escolher escopo; declaradas, o resíduo caiu
> para 0,072 (8,7%).
>
> Tudo em `docs/metrics/texto_custo_20260826.json`, com o `n`, os livros e a política ao lado do
> fator que a escolheu.


**Sonda.** `simbolo:chess_diagram_ocr.cli.texto_custo:main`,
`metrica:texto_custo`.

---

# O que esta spec deliberadamente não faz

Registrado aqui para que a ausência seja decisão e não esquecimento.

**Não exporta EPUB nem DOCX.** O projeto de origem exporta, e a tentação de trazer junto é real —
mas exportar livro é um produto diferente de ler livro, e ele depende de fonte redistribuível
(ver riscos). Fica fora até que alguém peça.

**Não redesenha o diagrama a partir da FEN.** Lá, a F58 trocou o recorte por um desenho com fonte
de xadrez, e é bonito. Aqui não serve a nada que exista: o consumidor da FEN é o PGN, e o do
recorte é a revisão.

**Não trata manuscrito, nem texto em imagem colorida, nem página torta.** Nada disso aparece no
acervo medido. Página torta (skew) é o mais provável de aparecer, e quando aparecer vira item
próprio — endireitar antes de segmentar muda todas as réguas desta spec de uma vez, e não é
mudança que se faça de passagem.

**Não promete os quatro idiomas.** O classificador de 292 classes tem acentuação latina
(`ç`, `ã`, `ñ`, `č`, `š`, `ž`), o que cobre português, espanhol e as transliterações eslavas dos
nomes. Não tem alfabeto cirílico nem grego, e um livro em russo não é lido por ele.

