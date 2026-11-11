# De onde vieram estas listas de palavras

**Este arquivo existe pelo mesmo motivo que `src/chess_diagram_ocr/text/PROCEDENCIA.md`:** dado
que veio de fora envelhece mal sem registro. Daqui a seis meses ninguém lembra qual arquivo saiu
do acervo do projeto e qual chegou numa pasta, e a diferença importa — uma é medição própria, a
outra é material de terceiro.

O que o programa lê está descrito em `src/chess_diagram_ocr/text/dicionario.py`. O que constrói é
`cvoff-texto-lexico`. Aqui está só a origem.

## Os três arquivos

| arquivo | palavras | origem | procedência |
|---|---:|---|---|
| `acervo.txt.gz` | 7.588 | camada de texto **editorada** dos livros do acervo que a têm | **do próprio projeto**, derivada e refazível |
| `idioma.txt.gz` | 10.010 | `Dic-1.txt` e `Novo Documento de Texto.txt` | **de fora, origem não declarada** |
| `nomes.txt.gz` | 349.565 | as mesmas duas, mais `MegaDatabase(Jogadores).txt`, `(Jogadores palavras unicas).txt`, `PGN Bases (nomes de partida).txt` e `Acervo (nomes casados aos livros).txt` | **misto** — ver abaixo |

Os dois últimos entraram em 2026-08-25 e mudaram o perfil do arquivo (medição em
`docs/metrics/texto_lexico_pgn.json`):

| de onde vem cada nome | quantos | do arquivo |
|---|---:|---:|
| **só** das bases de PGN (`PGN Bases (nomes de partida).txt`) | 199.104 | 57,0% |
| **só** da MegaDatabase | 1.433 | 0,4% |
| o resto — listas de origem não declarada, acervo, e o que se repete entre fontes | 149.028 | 42,6% |

`PGN Bases (nomes de partida).txt` é **do próprio material do dono do projeto**: sai dos cabeçalhos
das bases de partidas que já estão em `pgn_database/`, `PGN/` e `PGN_fase2_20260822/`. Aquelas
bases têm procedência própria, e este arquivo herda a delas.

`Acervo (nomes casados aos livros).txt` é **do próprio projeto**: são os nomes que a base já casou
com as páginas dos livros (`data/games_matches_v2.json`, `data/gallery_human.jsonl`).

Os `.txt` de origem ficam em `Lista de Palavras/`, **fora do git** (11 MB, e a mesma regra do
`PDF/`): o que é versionado são os dois `.txt.gz`, reconstruíveis byte a byte.

Uma quarta lista foi **recusada por estar corrompida** — `MegaDatabase(Jogadores with dot).txt`,
cujas linhas são dois nomes partidos e colados (`A.Koros` + `partindras`). Ver `IGNORADOS` em
`cli/texto_lexico.py`.

## O que se sabe e o que não se sabe

**Sabe-se** que nada baixa da rede, aqui como no resto do projeto: os arquivos foram postos na
máquina pelo dono do projeto, e o construtor lê uma pasta local.

**Não se sabe** de onde saíram `Dic-1.txt` e `Novo Documento de Texto.txt` — não trazem cabeçalho,
licença nem README. E o nome de `MegaDatabase(Jogadores)` aponta para a base comercial da
ChessBase, o que faz de `nomes.txt.gz` um extrato de índice de jogadores dela.

**Este projeto já tem uma regra para isso, e ela é sobre fontes:** *"Nenhuma fonte é copiada para
cá antes de a licença ser conferida"* (`docs/ROADMAP_TEXTO.md`, que por causa disso mantém parte
da S-210 bloqueada). A pergunta aqui é a mesma, com outro material.

**O que este arquivo não faz é dar parecer jurídico.** Registra o fato — de onde veio, o que é — e
o custo medido de cada saída, para que a decisão seja barata.

## As oito listas por língua (`linguas/`, S-728)

| arquivo | língua | entradas | linhas no `tessdata` |
|---|---|---:|---:|
| `linguas/eng.txt.gz` | inglês | 87.680 | 338.080 |
| `linguas/por.txt.gz` | português | 52.199 | 145.870 |
| `linguas/spa.txt.gz` | espanhol | 67.361 | 179.447 |
| `linguas/deu.txt.gz` | alemão | 52.854 | 89.378 |
| `linguas/nld.txt.gz` | holandês | 172.929 | 478.341 |
| `linguas/fra.txt.gz` | francês | 31.986 | 74.068 |
| `linguas/ron.txt.gz` | romeno | 74.038 | 185.844 |
| `linguas/rus.txt.gz` | russo | 139.107 | 293.898 |

**Origem.** O componente `lstm-word-dawg` dos `.traineddata` que vieram com o Tesseract 5.5 desta máquina (`tessdata`
fast, `C:\Program Files\Tesseract-OCR\tessdata`), extraído com o `combine_tessdata -u` e o `dawg2wordlist` da mesma
instalação. As oito línguas estavam lá, `ron` e `nld` inclusive. **Nada baixado, e nada da camada dos livros do acervo.**
`linguas/manifesto.json` traz, por língua, o sha do `.traineddata`, a versão gravada nele, as contagens e o sha da lista.
`cvoff-texto-lexico --linguas-de <pasta do Tesseract>` refaz tudo byte a byte; um clone sem o Tesseract fica com as listas
versionadas e não as refaz.

**Licença.** Apache-2.0. A cópia em `linguas/LICENSE.tessdata` é o `doc/LICENSE` da instalação, posta ao lado porque
`assets/` vai no bundle e a licença pede que a cópia acompanhe o que se redistribui. O `.traineddata` não traz licença
própria dentro dele: o que se conferiu no disco é a licença que a instalação declara. Estas listas são **derivadas**: o
que mudou é a régua abaixo.

**A régua** (`cli/texto_lexico.py`, `aceita_na_lingua`). Só a minúscula, com ao menos `MIN_TAMANHO` letras, sem dígito e
sem lance; no alemão, também a inicial maiúscula, porque lá é assim que o substantivo se escreve.

**O que estas listas não são: listas limpas de uma língua só.** O corpus de onde o Tesseract as tirou é da web. Medido
depois da régua: `after`, `with`, `para` e `avec` estão em sete das oito; `fixes`, um dos vetos errados da G1(a), está em
`por`. **O que falta cada uma tem pouco, e o que sobra é muito**: `peão`, `peón`, `după` e `после` só estão na própria
língua, e `pawn` só no inglês; mas a lista não serve para dizer que uma palavra é de **outra** língua, e não barra sozinha
`Pas`, `Das` ou `fixes` num livro em português. Quem precisar disso para a S-721 precisa de outra regra.

**O perfil do glifo não as lê.** Nenhuma delas está em `PERFIS`, e o `dicionario` continua decidindo pelos três arquivos de
cima: **zero** folhas diferentes em 28 do ouro-dev, contra o commit de antes (`docs/metrics/texto_lingua_2026-11-06/medir.py`).

## O que um clone limpo **não** reconstrói

`cvoff-texto-lexico` lê uma pasta local, e `Lista de Palavras/` não é versionada. Quem clonar este
repositório tem os três `.txt.gz` — que é o que o programa lê — e **não** consegue refazê-los. A
reprodutibilidade byte a byte vale para quem tem a pasta, e é o que o teste do comando afirma.

## O custo de tirar, medido

Em 40 páginas de 11 livros (`docs/metrics/texto_dicionario.json`), com o dicionário ligado:

    lista           efeito no texto que sai     efeito no que o dicionário protege
    idioma          nenhum caractere            39 palavras saem de "desconhecida"
    nomes           nenhum caractere            22 palavras saem de "desconhecida"

**Tirar os nomes não muda uma letra do que o leitor entrega hoje.** O que se perde é proteção: a
primeira guarda de `escolher` é *a palavra já está no léxico?*, e palavra conhecida é palavra que o
dicionário nunca reescreve. É um seguro, e é pequeno.

Três saídas, e o custo de cada uma:

1. **Ficar como está.** Custo zero de trabalho; a pergunta de procedência fica em aberto e escrita.
2. **Tirar `nomes.txt.gz`.** `carregar(nomes=False)` já existe e é o único ponto a mudar. Perde-se
   o seguro de 22 palavras em 40 páginas. **Depois de 2026-08-25 esta saída ficou mais cara e a
   pergunta ficou menor**: só 1.433 nomes (0,4%) dependem exclusivamente da MegaDatabase — tirar
   apenas o arquivo dela custa quase nada —, enquanto 57,0% do léxico de nomes vem das bases de
   PGN, cuja procedência é a das próprias bases. O que continua de origem não declarada são as
   duas listas soltas.
3. **Reconstruir a partir de fonte declarada.** Uma lista de nomes com licença explícita, ou os
   nomes que o próprio acervo já traz na camada editorada — que é o que `acervo.txt.gz` faz e é
   material derivado do que o dono do projeto já possui.

**Decisão: pendente do dono do projeto.** Enquanto ela não vem, os três arquivos estão no
repositório e o programa os lê.
