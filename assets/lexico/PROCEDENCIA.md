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
