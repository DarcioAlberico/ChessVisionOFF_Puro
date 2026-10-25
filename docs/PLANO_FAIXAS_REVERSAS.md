# Plano — texto claro sobre faixa preta na aba Texto

**2026-10-11.** Um item, medido e entregue no mesmo dia; a evidência vem da suíte
(`Suite_de_Edicao_de_Xadrez`, commit `f369954`), que recebeu o mesmo método um dia antes para o
importador.

## A queixa

As páginas «Solutions» do `Yusupov — Build Up Your Chess` trazem o cabeçalho de cada exercício
(«E.Jackson – D.Baird») em letras brancas sobre uma faixa preta. «Ler folha» na aba Texto não
devolve nenhum dos nove cabeçalhos da folha 19: para `binarize` a faixa é um bloco de tinta de
440 × 38 px (a 200 dpi), as letras são buracos nele, e `caixas_de_caractere` não tira contorno
de letra de um buraco. A camada de texto do próprio PDF carrega «E. ackson» para a mesma linha,
então o motor `camada` também não serve de muleta.

## S-527 · A faixa de texto claro vira tinta sobre papel antes da binária

**Spec.** `text/faixas.py`: `achar_faixas(cinza, dpi)` devolve as faixas e uma máscara da página;
`desinverter_faixas(cinza, dpi)` devolve a página em cinza com cada faixa invertida. `segmentar`
ganha `dpi: int | None = None` e, quando o recebe, passa o cinza por `desinverter_faixas` **antes**
de `binarize`; `linhas_do_glifo` recebe o mesmo `dpi` de `ler_pagina`. Sem DPI nada é tocado — a
régua é física e o `cli/texto_colunas.py`, que chama sem DPI, continua lendo o que lia.

**O critério, cada parte contra um vizinho.** Otsu, fechamento de 0,03 pol sobre a tinta (engole
os traços claros; a faixa vira um componente sólido, o título preto vira borrão de palavra). Fica
o componente largo e baixo (razão ≥ 2,5; altura entre 0,06 e 0,75 pol), sólido (≥ 80 % da caixa
depois do fechamento) e escuro (≥ 55 % de tinta na caixa antes dele). O título em negrito é largo
e baixo mas tem no máximo 45 % de tinta; o diagrama é metade escuro mas quadrado; o filete é largo
e escuro mas mais fino que 0,06 pol; a foto é escura mas mais alta que 0,75 pol.

**A franja.** O scanner deixa uma tira de textura na borda de cima da faixa, **dentro** da caixa
dela, e ela não se separa por densidade (0,45–0,83 de tinta por linha, contra 0,65–0,92 nas linhas
com texto). O núcleo vai da primeira à última linha **inteiramente** de tinta (≥ 0,95 da largura):
a faixa tem sempre uma entrelinha sólida acima e abaixo do texto (1,00), e a franja nunca passa de
0,85. O resto da caixa é franja e vai para papel — deixada, vira depois da inversão uma tira de
ruído que o leitor toma por uma linha («vccnarpamegscn» no Tesseract). A primeira régua, as
margens laterais sólidas a 0,9, deixava passar a última linha da franja (sólida nas pontas, textura
no meio), e a primeira linha inteira ainda tem 5 % de buracos: invertidas, as duas viravam um
tracejado de 1 px que o glifo lia como «—» entre as letras («E. Ia—— C— kS——O— —n—»). Por isso o
núcleo perde 0,012 pol de cada lado (3 px a 220 dpi, 4 a 300) — a entrelinha tem ≥ 0,04 pol e as
pontas ≥ 0,1 pol de faixa sem texto.

**Só a faixa é invertida, não a caixa.** A legenda colada embaixo («England – USA 1896») fica
tinta sobre papel; os 2 px serrilhados em volta vão para papel, para não sobrar moldura.

**Medido** (na suíte, folha 19 a 200 dpi): 9 de 9 faixas em 26 ms; o Tesseract de página inteira
passa de «EJackson» e «ECanal — iia» a «E.Jackson — D.Baird» e «E.Canal — N.N.». **No tronco**,
`ler_pagina(motor="glifo", dpi=220)` na folha 19: sem o item, 55 linhas, **0 de 9** cabeçalhos e a
folha em coluna única com as duas intercaladas («siegen olympiad 1970 1.♕:h6✝!») — o bloco preto
da faixa fechava a calha; com o item, 72 linhas, 4 colunas (as duas do corpo mais título e fólio),
os nove cabeçalhos lidos como palavras e **6 de 9** exatos («M.Marco — Salter», «E.Canal — N.N.»,
«M.Gurevich — N.Short», «E.Lobron — S.Bouaziz»…); os três restantes são confusões do classificador
no negrito («E.Iackson», «K.Oianen», «V.KuDreichik»), não da faixa. O corpo da folha também sai
limpo pela primeira vez («Black resigned, in view of 1 ...♔xf8 2.♖e8✝»). Testes em
`tests/test_text_faixas.py`: a faixa achada onde foi desenhada (núcleo sem a franja), o cabeçalho
virado contra a referência em preto (F1 > 0,95), nenhum pixel fora da faixa mudado, a franja
apagada, título/filete/diagrama recusados, a régua física (metade da resolução a metade do DPI),
e `segmentar` com DPI rendendo as letras do cabeçalho como caixas de caractere — sem DPI, nenhuma.

**O que fica de fora.** `GlyphRecognizer.read` (a faixa de legenda da `ocr_caption`) não sabe o
DPI e não passa por aqui; a legenda de diagrama em vídeo reverso é outro item, se aparecer.
