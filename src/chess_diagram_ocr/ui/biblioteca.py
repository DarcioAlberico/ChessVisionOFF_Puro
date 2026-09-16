"""O acervo inteiro como uma decisão só -- busca, facetas e a janela que se realiza, sem toolkit.

**O problema que cria este módulo.** O programa abre **um** livro por vez. A pasta `PDF/` desta
máquina tem **46 arquivos e 832 MiB**, e a única forma de trocar de livro é o diálogo de arquivo
do sistema -- que responde "qual arquivo?" e nunca "qual livro?". Nada na janela sabe dizer quais
já foram varridos, quais são de 1870 e quais estão em alemão, e essas três perguntas são as que
decidem o que abrir.

**Por que a decisão mora aqui e não no painel.** A biblioteca é o pedaço do produto onde o número
de itens é a variável: 46 hoje, e o acervo é justamente o que o projeto existe para fazer crescer.
Tudo o que degrada com o tamanho -- a busca a cada tecla, a contagem de cada faceta, e sobretudo
**quais células realizar** -- é conta, não pintura, e conta se afirma sem abrir janela. O painel
do Qt que consome isto pinta o que estas funções decidiram, e não decide nada.

---

**As três medições que desenharam o módulo**, feitas contra os 46 livros de `PDF/` com o PyMuPDF
desta máquina:

1. **O `/Title` do PDF está preenchido em 15 dos 46 (33%)**, e o `/Author` em 13 (28%). Um deles
   -- o `1000 Chess Problems` -- traz `'((0E<0B=K9 C=825@A8B5B)...'`, que é cirílico decodificado
   na tabela errada e ficaria na tela como título "do livro". **O nome do arquivo é a fonte
   primária do título, e o metadado é o suplente** -- o contrário do que a intuição pede, e é o que
   a medição obriga. Ver `titulo_do_arquivo` e `DO_METADADO`.
2. **Nenhum PDF do acervo declara editora.** O `/Producer` está em 46 de 46 e diz `calibre 3.28.0`
   ou `GPL Ghostscript 9.22`: é quem *gerou o arquivo*, não quem *publicou o livro*. Publicá-lo na
   faceta "Editora" daria uma coluna inteira de nomes de software. A editora sai do título, quando
   ele a traz -- **2 dos 46**, `[Quality Chess, 2015]` e `(Bastford, 2005)` --, e nos outros 44 o
   valor é `SEM_EDITORA`, que **é um valor de faceta e não uma ausência** (ver `Faceta`).
3. **O `/CreationDate` não é o ano do livro.** Está em 45 de 46 e diz 2024 para um livro de 2015,
   2021 para um de 1958: é quando o *arquivo* foi feito. O ano sai do título, em **22 dos 46
   (48%)**, e ali a armadilha está medida: um `\\d{4}` ingênuo lê **1001** em
   `1001_Winning_Chess_Sacrifices` e inventa um incunábulo. Ver `ano_no_titulo`.

**A quarta medição é a que mais surpreendeu.** `idioma_provavel`, que é uma tabela de palavras
marcadoras sobre o título dobrado, acerta **45 dos 46** com **zero erros** e um indeciso
(`Dvoretsky's Endgame Manual`, cujo título não tem uma só palavra funcional). Zero erro importa
mais que 45 acertos: uma faceta de idioma que *erra* manda o livro para o balde errado e ele some
da vista de quem filtrou; uma que *não sabe* o deixa em `SEM_IDIOMA`, onde ele continua achável.
É por isso que a tabela exige marcador e não devolve o palpite de maior placar quando o placar é
zero.

---

**A virtualização é o item de engenharia, e ela é O(1).** `janela_visivel` recebe cinco inteiros e
devolve a faixa semiaberta de índices a realizar. Ela não percorre item nenhum -- é divisão
inteira --, e é isso que faz 10.000 capas custarem o mesmo que 46. A alternativa que o Qt oferece
de graça, um `QListView` com 10.000 itens, constrói 10.000 objetos de modelo para mostrar 24; a
medição de quanto isso custa está em `tests/test_qt_painel_da_biblioteca.py`, que conta as células
pintadas em vez de acreditar.

**A banda de sobra não é enfeite.** Sem ela a linha que entra pela borda é realizada no mesmo
quadro em que aparece, e o efeito é a capa surgindo *depois* do lugar dela. Uma linha de cada lado
é o mínimo que esconde isso a 60 Hz, e `SOBRA` é uma constante para o teste poder afirmar a faixa
com sobra zero -- que é a única forma de checar a conta central sem a banda por cima dela.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

__all__ = [
    "COM_RESULTADO",
    "DIAGRAMAS_ROTULOS",
    "DO_METADADO",
    "EIXOS",
    "EIXO_DIAGRAMAS",
    "EIXO_EDITORA",
    "EIXO_ERA",
    "EIXO_ESTADO",
    "EIXO_IDIOMA",
    "IDIOMAS",
    "ORDENS",
    "ORDEM_ANO",
    "ORDEM_AUTOR",
    "ORDEM_DIAGRAMAS",
    "ORDEM_RECENTE",
    "ORDEM_TITULO",
    "PROCESSADO",
    "ROTULOS_DE_EIXO",
    "ROTULOS_DE_ORDEM",
    "SEM_ANO",
    "SEM_EDITORA",
    "SEM_IDIOMA",
    "SEM_RESULTADO",
    "SOBRA",
    "VAZIO",
    "Faceta",
    "FaixaVisivel",
    "Filtro",
    "IndiceDaBiblioteca",
    "ItemDaBiblioteca",
    "NAO_PROCESSADO",
    "Resumo",
    "ValorDeFaceta",
    "altura_do_conteudo",
    "ano_no_titulo",
    "casa_com",
    "colunas_que_cabem",
    "dobrar",
    "editora_no_titulo",
    "era_de",
    "faixa_de_diagramas",
    "idioma_provavel",
    "item_de",
    "janela_visivel",
    "palavras",
    "peso_no_disco",
    "resumo_de",
    "titulo_do_arquivo",
]


# --------------------------------------------------------------------- o texto, dobrado

_COMBINANTES = re.compile("[\u0300-\u036f]")
"""Os diacríticos que a decomposição NFKD solta atrás da letra.

**Escrito com escape e não com o caractere**, porque o que este intervalo casa é *invisível*: um
acento combinante literal no fonte é indistinguível de sujeira entre as aspas, e o próximo editor
que "limpar" a linha desliga a busca sem acento sem que nada acuse."""

_CIRILICO = ("\u0400", "\u04ff")
_SEPARADORES = re.compile(f"[^0-9a-z{_CIRILICO[0]}-{_CIRILICO[1]}]+")
"""Tudo o que não é letra latina sem acento, dígito ou cirílico separa token. Ver `palavras`.

O texto já chega dobrado, então a classe não precisa das maiúsculas nem dos acentos -- e é por
isso que ela pode ser tão curta."""


def dobrar(texto: object) -> str:
    """`"Análise"` e `"analise"` viram a mesma coisa: sem acento, sem caixa, sem espaço nas pontas.

    **É a função que faz a busca ser usável em pt-BR**, e a razão é de teclado e não de gosto:
    quem digita depressa num acervo não põe acento, e um índice que exige `Combinações` para achar
    `Combinações` responde "nenhum resultado" para a consulta certa. O acervo desta máquina tem
    `Combinações`, `memoráveis`, `Estratégia`, `Eröffnungswege` e `échecs` -- cinco idiomas de
    diacrítico, e uma pessoa só.

    **NFKD e não NFD**, e a diferença aparece no acervo: o `‑` de `dame‑problemen` é um hífen
    não-separável (U+2011), e a decomposição de compatibilidade o aproxima do hífen comum. Pela
    mesma porta entram a ligadura `ﬁ` e os dígitos de largura dupla que os scanners produzem.

    O cirílico **não** é transliterado, e é uma decisão: `Избранные` continua `избранные`. Quem
    tem esses dois livros na estante os procura no alfabeto deles, e uma transliteração inventada
    (`izbrannye`? `izbrannyye`?) seria uma terceira grafia que ninguém digita.
    """
    decomposto = unicodedata.normalize("NFKD", str(texto))
    return _COMBINANTES.sub("", decomposto).casefold().strip()


def palavras(texto: object) -> tuple[str, ...]:
    """Os tokens de um texto já dobrado, na ordem em que aparecem e sem os vazios.

    Separa por *tudo* o que não é letra, dígito ou cirílico -- o que inclui `_`, `,`, `-` e `.`,
    que é exatamente como o acervo separa palavra: `1001_Winning_Chess_Sacrifices_and_
    Combinations,_Fred_Reinfeld,_Bruce_hq`. Um `split()` por espaço devolveria **um** token para
    esse nome inteiro, e a busca por `reinfeld` não acharia o livro do Reinfeld.
    """
    return tuple(parte for parte in _SEPARADORES.split(dobrar(texto)) if parte)


# ------------------------------------------------------------------- o item, e o que o descreve

SEM_IDIOMA = "?"
"""O idioma que ninguém declarou e que a tabela de marcadores não decidiu.

**É um valor de faceta, e não uma ausência**, pela razão medida no cabeçalho: um livro que cai
aqui continua na barra lateral, com contagem, e continua achável. Some-lo da faceta o esconderia
de quem filtra por qualquer idioma -- e o balde do desconhecido é justamente onde mora o livro
sobre o qual se sabe menos, que é o que mais precisa ser encontrado."""

SEM_EDITORA = "(sem editora)"
SEM_ANO = "(sem ano)"
"""Os dois irmãos do de cima, pela mesma regra. `SEM_EDITORA` cobre **44 dos 46** livros do acervo
-- e é por isso que ele não pode ser tratado como caso raro: ele é a maioria da faceta."""

IDIOMAS: dict[str, str] = {
    "pt": "Português",
    "en": "Inglês",
    "es": "Espanhol",
    "de": "Alemão",
    "fr": "Francês",
    "nl": "Neerlandês",
    "it": "Italiano",
    "ro": "Romeno",
    "ru": "Russo",
    SEM_IDIOMA: "Sem idioma",
}
"""`código ISO -> nome em pt-BR`. Os nove idiomas são os do acervo mais o italiano.

**O código é a identidade e o nome é a tela**, e separá-los é o que permite renomear "Neerlandês"
para "Holandês" sem invalidar o filtro que alguém deixou guardado -- que é a mesma armadilha que
`ui/abas.RENOMEADAS` documenta para o rótulo da aba."""

PROCESSADO = "processado"
NAO_PROCESSADO = "nao_processado"
"""Os dois valores do eixo de estado. `"processado"` quer dizer *este livro já foi varrido e os
diagramas dele estão no índice* -- e não "está aberto" nem "tem amostra no `labels.csv`"."""


@dataclass(frozen=True)
class ItemDaBiblioteca:
    """Um livro do acervo, do ponto de vista de quem escolhe qual abrir.

    **Congelado, e é uma decisão de desempenho e não de pureza.** O índice pré-calcula o texto
    dobrado e o conjunto de tokens de cada item na construção; se o item pudesse mudar de título
    depois disso, o pré-cálculo passaria a mentir em silêncio -- a busca acharia pelo nome velho e
    a tela mostraria o novo. Trocar um campo é `dataclasses.replace` e um índice novo, que é
    barato: 10.000 itens indexam em milissegundos, e o disco que os produziu custa ordens de
    grandeza mais.

    **`chave_da_capa` é uma chave e não uma imagem.** O painel guarda os `QPixmap` decodificados
    num LRU e os endereça por esta string; um `bytes` aqui dentro faria o índice inteiro -- que é
    o que a busca percorre a cada tecla -- carregar as capas junto. A chave é derivada do caminho
    e do `mtime` por quem extrai, para que reprocessar um livro invalide a capa dele sem invalidar
    as outras 45.

    **`aberto_em` é `float | None` e não `0.0`**: "nunca aberto" e "aberto em 1970" são duas
    coisas, e `ORDEM_RECENTE` precisa distingui-las para não pôr os livros novos no topo da lista
    de recentes.
    """

    caminho: Path
    titulo: str
    autor: str = ""
    editora: str = ""
    ano: int | None = None
    idioma: str = SEM_IDIOMA
    paginas: int = 0
    diagramas: int = 0
    processado: bool = False
    chave_da_capa: str = ""
    bytes_no_disco: int = 0
    aberto_em: float | None = None

    @property
    def era(self) -> str:
        """A década do livro, como valor de faceta. Ver `era_de`."""
        return era_de(self.ano)

    @property
    def estado(self) -> str:
        return PROCESSADO if self.processado else NAO_PROCESSADO

    @property
    def faixa(self) -> str:
        """O balde de contagem de diagramas. Ver `faixa_de_diagramas`."""
        return faixa_de_diagramas(self.diagramas)

    @property
    def editora_ou_ausente(self) -> str:
        return self.editora.strip() or SEM_EDITORA

    @property
    def idioma_ou_ausente(self) -> str:
        return self.idioma.strip() or SEM_IDIOMA


# ---------------------------------------------------------------- de onde sai cada campo

DO_METADADO: dict[str, str] = {
    "author": "autor",
    "title": "titulo_suplente",
    "language": "idioma",
}
"""`chave do dicionário do PyMuPDF -> campo deste módulo`. **A tabela é curta de propósito.**

O PyMuPDF devolve dez chaves e só estas três dizem alguma coisa sobre o *livro*. As outras sete
falam do *arquivo* -- `producer`, `creator`, `format`, `creationDate`, `modDate`, `encryption` --
ou estão preenchidas em menos de 10% do acervo (`keywords` em 4, `subject` em 3).

**`title` mapeia para `titulo_suplente` e não para `titulo`**, e essa palavra é o item: com 33% de
preenchimento e ao menos um caso de mojibake medido, o `/Title` não é bom o bastante para ser o
nome na tela. Ele entra quando o nome do arquivo não sobra nada -- ver `item_de`.

**A chamada ao PyMuPDF não mora aqui**, e a fronteira é a mesma do resto de `ui/`: este módulo diz
*qual chave vira qual campo*, e quem abre o arquivo é o serviço ou o painel. Sem isso o índice --
que é o que a busca percorre -- passaria a depender de uma biblioteca de C, e os testes de busca
precisariam de PDFs no disco."""

_ANO = re.compile(r"(?<!\d)(1[5-9]\d\d|20[0-2]\d)(?!\d)")
"""Um ano plausível de livro de xadrez: 1500-1999 ou 2000-2029.

**A faixa é o que impede o falso positivo medido.** `\\d{4}` acha `1001` em
`1001_Winning_Chess_Sacrifices` e `5334` em `Polgar_Chess_5334_Problems` -- dois dos 46 --, e o
resultado seria uma faceta "Era" com uma década do século XI. O teto em 2029 é folga deliberada
sobre o hoje: um livro publicado depois disso pede uma linha, e uma faixa aberta traria de volta
os números de página (`145p`) e os de série."""

_ANO_CERCADO = re.compile(r"[\[(][^\[\]()]*?(?<!\d)(1[5-9]\d\d|20[0-2]\d)(?!\d)[^\[\]()]*?[\])]")
_EDITORA = re.compile(r"[\[(]\s*([^\[\](),]{3,40}?)\s*,\s*(?:1[5-9]\d\d|20[0-2]\d)\s*[\])]")


def ano_no_titulo(texto: object) -> int | None:
    """O ano de edição que o título carrega, ou `None`. Prefere o que está entre parênteses.

    **As duas regras concordam nos 22 do acervo que têm ano**, e a cercada foi escolhida pelo que
    acontece *depois*: os nomes deste acervo ganham sufixos com o tempo (`_hq`, `_OCR`,
    `_Aprimorar_Aprimorar`, `_folha49`), e no dia em que um deles terminar com a data da
    digitalização a regra do "último ano da string" passa a publicar o ano do *scan*. A do
    parêntese continua lendo `(1958)`, que é a convenção de edição que este acervo usa.

    Devolve `None` -- e não o ano de hoje, nem zero -- para os 24 sem ano: `SEM_ANO` é um balde de
    faceta com contagem, e um zero se ordenaria junto com o século XVI.
    """
    bruto = str(texto)
    cercado = _ANO_CERCADO.search(bruto)
    if cercado is not None:
        return int(cercado.group(1))
    achados = _ANO.findall(bruto)
    return int(achados[-1]) if achados else None


def editora_no_titulo(texto: object) -> str:
    """A editora que o título declara junto do ano: `[Quality Chess, 2015]` → `Quality Chess`.

    **Dois dos 46**, e mesmo assim vale o código: a alternativa é a faceta "Editora" nascer com o
    `/Producer`, que diria `calibre 3.28.0` para 46 livros. Uma faceta com dois valores
    verdadeiros e 44 honestos é utilizável; uma com 46 valores errados não é.

    O par `nome, ano` é obrigatório no padrão porque é ele que separa editora de subtítulo: sem o
    ano, `(all volumes)` e `(2025)` são a mesma forma, e a coluna encheria de parênteses do título.
    """
    achado = _EDITORA.search(str(texto))
    return achado.group(1).strip() if achado is not None else ""


_MARCADORES: dict[str, frozenset[str]] = {
    "en": frozenset(
        "chess the of winning endgame endgames endings book guide combinations problems openings "
        "training secrets and with how to your play great complete instructive strategy "
        "calculation technique defence gambit manual structures grandmaster games champions "
        "imagination practical simple matter build excelling minor pawnless future school".split()
    ),
    "pt": frozenset(
        "xadrez de do da dos das partidas finais melhores quebra cabecas estrategia memoraveis "
        "combinacoes vencedores minhas sacrificios vitorioso".split()
    ),
    "es": frozenset(
        "ajedrez el la del los las combinacion combinaciones dominio arte metodo brillantes casa "
        "fundamentos".split()
    ),
    "de": frozenset(
        "schach das der die mittelspiel eroeffnung eroeffnungswege bauernopfer grosse "
        "internationale band praktikum neue schachturnier".split()
    ),
    "nl": frozenset("schaken zwarte magie meestertournooi internationaal blind problemen dame".split()),
    "ro": frozenset("sah cartea sahistului inceparator problematica deschiderilor deschideriliol".split()),
    "fr": frozenset("echecs jeu traite elementaire du des".split()),
    "it": frozenset("scacchi il lo gli finali partite aperture".split()),
}
"""Palavras funcionais e de domínio que só aparecem num idioma. Ver `idioma_provavel`.

**Palavras e não n-gramas de caractere**, porque a entrada é um *título*, não um parágrafo: os
títulos deste acervo têm de 3 a 20 palavras, e um classificador estatístico treinado nessa
quantidade de texto é ruído com aparência de método. Uma tabela erra de forma legível -- e é
corrigível com uma linha por palavra."""


def idioma_provavel(texto: object) -> str:
    """O idioma do título pelas palavras que ele usa. `SEM_IDIOMA` quando nada marca.

    **Medido nos 46 nomes de arquivo do acervo: 45 acertos, zero erros, um indeciso.** O indeciso é
    `Dvoretsky - Dvoretsky's Endgame Manual (2025)` -- e ele é indeciso porque `endgame` e `manual`
    entraram na tabela *depois* da medição, o que é a maneira honesta de dizer que a tabela cresce
    com o acervo. O número que vale é o da medição, e ele está afirmado em
    `tests/test_ui_biblioteca.py` contra os mesmos nomes.

    **Zero erro vale mais que os 45 acertos**, e é por isso que o placar zero devolve `SEM_IDIOMA`
    em vez do maior empate: uma faceta que *erra* joga o livro num balde onde ninguém o procura, e
    ele desaparece da vista de quem filtrou por idioma. Uma que *não sabe* o deixa em `SEM_IDIOMA`,
    onde ele continua listado e continua achável pela busca.

    **O cirílico atalha antes da tabela.** Não é preguiça: `Избранные партии` não tem uma palavra
    que se possa comparar com `chess`, e o alfabeto é a evidência mais forte que um título curto
    oferece. Vale para o russo e enganaria para o búlgaro ou o sérvio -- o acervo não tem nenhum
    dos dois, e uma tabela de marcadores cirílicos entra no dia em que tiver.
    """
    bruto = str(texto)
    if any("Ѐ" <= letra <= "ӿ" for letra in bruto):
        return "ru"
    tokens = set(palavras(bruto))
    placar = {codigo: len(tokens & marcadores) for codigo, marcadores in _MARCADORES.items()}
    melhor = max(placar, key=lambda codigo: placar[codigo])
    return melhor if placar[melhor] else SEM_IDIOMA


_SUFIXOS_DE_ARQUIVO = ("_hq", "_ocr", "_aprimorar", "_copia", "- copia")
"""Sufixos que este acervo cola no nome e que não são do livro. Ver `titulo_do_arquivo`."""


def titulo_do_arquivo(caminho: Path | str) -> str:
    """O título legível a partir do nome do arquivo -- que é a fonte **primária** (33% vs. 100%).

    Três limpezas, e cada uma vem de uma família de nome que existe no acervo:

    - **`_` vira espaço.** `1001_Winning_Chess_Sacrifices_and_Combinations` é um título com
      sublinhados, e mostrá-lo assim é publicar o nome do arquivo em vez do nome do livro.
    - **Os sufixos de processamento saem.** `_hq`, `_OCR`, `- Copia` e `_Aprimorar_Aprimorar` dizem
      o que foi feito com o *arquivo*; `Melhores Finais de Capablanca - Irving Chernev pt-br -
      Copia_hq` e o irmão dele são o **mesmo livro** duas vezes, e com o sufixo na tela viram dois
      títulos diferentes na lista ordenada.
    - **O emoji de capa some.** Sete arquivos começam com `📚`, e um caractere que ordena antes de
      todas as letras põe esses sete no fim (ou no começo) da lista alfabética por um motivo que
      não é do livro.

    O que **não** sai é o ano nem o autor: eles são informação e ganham campo próprio, mas tirá-los
    do título faria `Euwe, Kramer - Das Mittelspiel Band 7` e `Band 1-2` perderem o que os
    distingue no meio de uma grade de capas.
    """
    nome = Path(caminho).stem.replace("_", " ")
    nome = "".join(letra for letra in nome if letra.isprintable() and not _e_pictografico(letra))
    limpo = " ".join(nome.split())
    dobrado = dobrar(limpo)
    for sufixo in _SUFIXOS_DE_ARQUIVO:
        if dobrado.endswith(sufixo):
            limpo = limpo[: len(limpo) - len(sufixo)].strip(" -,")
            dobrado = dobrar(limpo)
    return limpo.strip() or Path(caminho).stem


def _e_pictografico(letra: str) -> bool:
    """Se o caractere é emoji/símbolo de bloco alto. Ver a terceira limpeza de `titulo_do_arquivo`."""
    return unicodedata.category(letra) == "So" and ord(letra) > 0x2100


def item_de(
    caminho: Path | str,
    *,
    metadados: Mapping[str, object] | None = None,
    paginas: int = 0,
    diagramas: int = 0,
    processado: bool = False,
    chave_da_capa: str = "",
    bytes_no_disco: int = 0,
    aberto_em: float | None = None,
) -> ItemDaBiblioteca:
    """Monta o item a partir do caminho e do dicionário que o PyMuPDF devolveu.

    **Puro: não abre o arquivo.** `metadados` é o que `fitz.Document.metadata` deu, passado por
    quem já pagou o custo de abrir -- e `None` é um acervo listado sem abrir livro nenhum, que é o
    estado da primeira pintura da grade. Ver o cabeçalho de `DO_METADADO`.

    **A ordem das fontes é a medida, e ela inverte a intuição.** Título: nome do arquivo primeiro,
    `/Title` só se o nome não sobrar nada. Autor: `/Author` primeiro, porque ali não há concorrente
    -- e ele está em 13 dos 46, o que faz 33 livros ficarem sem autor até alguém digitar um. Ano e
    editora: título, nunca metadado, pelas duas medições do cabeçalho.
    """
    alvo = Path(caminho)
    dados = dict(metadados or {})
    titulo = titulo_do_arquivo(alvo)
    if not titulo:
        titulo = str(dados.get("title") or "").strip() or alvo.name
    autor = str(dados.get("author") or "").strip()
    declarado = str(dados.get("language") or "").strip().lower()[:2]
    idioma = declarado if declarado in IDIOMAS else idioma_provavel(titulo)
    return ItemDaBiblioteca(
        caminho=alvo,
        titulo=titulo,
        autor=autor,
        editora=editora_no_titulo(alvo.stem),
        ano=ano_no_titulo(alvo.stem),
        idioma=idioma,
        paginas=int(paginas),
        diagramas=int(diagramas),
        processado=bool(processado),
        chave_da_capa=chave_da_capa,
        bytes_no_disco=int(bytes_no_disco),
        aberto_em=aberto_em,
    )


# ----------------------------------------------------------------------------- as facetas

EIXO_IDIOMA = "idioma"
EIXO_ERA = "era"
EIXO_EDITORA = "editora"
EIXO_ESTADO = "estado"
EIXO_DIAGRAMAS = "diagramas"

EIXOS: tuple[str, ...] = (EIXO_ESTADO, EIXO_IDIOMA, EIXO_ERA, EIXO_DIAGRAMAS, EIXO_EDITORA)
"""Os cinco eixos da barra lateral, **na ordem em que ela os empilha**.

O estado vem primeiro porque é o eixo que responde à pergunta com que se abre a biblioteca -- *o
que falta varrer?* --, e a editora vem por último porque em 44 dos 46 livros ela é
`SEM_EDITORA`: um eixo de um valor só no topo da lateral gastaria a posição mais visível para
dizer o que já se sabe."""

ROTULOS_DE_EIXO: dict[str, str] = {
    EIXO_ESTADO: "Estado",
    EIXO_IDIOMA: "Idioma",
    EIXO_ERA: "Época",
    EIXO_DIAGRAMAS: "Diagramas",
    EIXO_EDITORA: "Editora",
}

DIAGRAMAS_ROTULOS: tuple[tuple[str, str], ...] = (
    ("0", "Nenhum"),
    ("1-99", "Até 99"),
    ("100-499", "100 a 499"),
    ("500-999", "500 a 999"),
    ("1000+", "1.000 ou mais"),
)
"""Os cinco baldes de contagem de diagramas, com o rótulo de cada um.

**Baldes e não um intervalo digitável**, porque a pergunta é comparativa e não exata: ninguém abre
a biblioteca querendo "livros com 347 diagramas". Os cortes são os da distribuição observada -- um
livro de problemas passa de mil, um manual de finais fica na casa das centenas, e um torneio
comentado fica abaixo de cem.

**O `0` é um balde e não uma ausência**, pela razão de sempre neste módulo: "varri e não achei
diagrama nenhum" é uma informação sobre o livro, e é ela que separa o PDF de texto puro do que
ainda não foi varrido -- que está no eixo `EIXO_ESTADO` e não neste."""


def faixa_de_diagramas(quantos: int) -> str:
    """Em qual dos cinco baldes de `DIAGRAMAS_ROTULOS` cai esta contagem."""
    if quantos <= 0:
        return "0"
    if quantos < 100:
        return "1-99"
    if quantos < 500:
        return "100-499"
    if quantos < 1000:
        return "500-999"
    return "1000+"


def era_de(ano: int | None) -> str:
    """A década, como `"1950"`, ou `SEM_ANO`.

    **Década e não século, e não o ano cru.** O acervo vai de 1870 a 2025: por ano seriam 22
    valores de faceta para 46 livros -- uma lista de rolagem em que quase todo valor tem contagem
    1, que é o mesmo que não facetar. Por século seriam dois valores, e o de 1900 teria 30 livros.
    A década é o corte em que a contagem começa a discriminar.

    A chave é a década em texto e não em número para caber no mesmo `frozenset[str]` dos outros
    quatro eixos -- um eixo com tipo próprio obrigaria `Filtro.escolhas` a ser heterogêneo, e o
    painel a saber qual é qual.
    """
    if ano is None:
        return SEM_ANO
    return str((int(ano) // 10) * 10)


def _rotulo_de_valor(eixo: str, valor: str) -> str:
    """O que a barra lateral escreve para aquele valor. A chave continua sendo o valor."""
    if eixo == EIXO_IDIOMA:
        return IDIOMAS.get(valor, valor)
    if eixo == EIXO_ESTADO:
        return "Varrido" if valor == PROCESSADO else "A varrer"
    if eixo == EIXO_ERA:
        return valor if valor == SEM_ANO else f"{valor}s"
    if eixo == EIXO_DIAGRAMAS:
        return dict(DIAGRAMAS_ROTULOS).get(valor, valor)
    return valor


def _valor_do_eixo(item: ItemDaBiblioteca, eixo: str) -> str:
    if eixo == EIXO_IDIOMA:
        return item.idioma_ou_ausente
    if eixo == EIXO_ERA:
        return item.era
    if eixo == EIXO_EDITORA:
        return item.editora_ou_ausente
    if eixo == EIXO_ESTADO:
        return item.estado
    if eixo == EIXO_DIAGRAMAS:
        return item.faixa
    raise KeyError(f"eixo de faceta desconhecido: {eixo!r}. Os válidos estão em EIXOS.")


@dataclass(frozen=True)
class ValorDeFaceta:
    """Uma linha da barra lateral: o valor, o que se escreve dele, quantos casam e se está marcado.

    **`contagem` pode ser zero e a linha continua na lista**, e este é o item da S de facetas: uma
    barra lateral que esconde o que zerou muda de altura a cada tecla digitada na busca, e o valor
    sob o ponteiro vira outro entre o olho e o clique. Zero é uma resposta -- *não há nenhum alemão
    entre os já varridos* --, e ela é útil; a linha some é que não pode.
    """

    valor: str
    rotulo: str
    contagem: int
    escolhido: bool


@dataclass(frozen=True)
class Faceta:
    """Um eixo inteiro da barra lateral, com todos os valores que o acervo tem naquele eixo.

    **Os valores são os do acervo inteiro, e as contagens são as do filtro.** Separar as duas
    coisas é o que faz a lateral ficar parada enquanto os números mudam -- ver `ValorDeFaceta`.
    """

    eixo: str
    rotulo: str
    valores: tuple[ValorDeFaceta, ...]

    @property
    def total(self) -> int:
        """A soma das contagens. Existe para o teste afirmar que ela fecha com o filtrado."""
        return sum(valor.contagem for valor in self.valores)


# ------------------------------------------------------------------------------ a ordenação

ORDEM_TITULO = "titulo"
ORDEM_AUTOR = "autor"
ORDEM_ANO = "ano"
ORDEM_RECENTE = "recente"
ORDEM_DIAGRAMAS = "diagramas"

ORDENS: tuple[str, ...] = (ORDEM_TITULO, ORDEM_AUTOR, ORDEM_ANO, ORDEM_RECENTE, ORDEM_DIAGRAMAS)

ROTULOS_DE_ORDEM: dict[str, str] = {
    ORDEM_TITULO: "Título",
    ORDEM_AUTOR: "Autor",
    ORDEM_ANO: "Ano",
    ORDEM_RECENTE: "Abertos há menos tempo",
    ORDEM_DIAGRAMAS: "Mais diagramas",
}


def chave_de_ordem(ordem: str) -> Callable[[ItemDaBiblioteca], Any]:
    """A função de chave daquela ordem. Levanta `KeyError` para ordem desconhecida.

    Levanta -- e não cai no título -- pela disciplina de `tokens.cor`: uma ordem escrita errada que
    silenciosamente virasse alfabética daria uma lista plausível e sem significado, e ninguém
    descobriria por que o botão "Mais diagramas" não faz nada.

    **Nenhuma das cinco usa `reverse=True`, e isso é deliberado.** O decrescente é expresso na
    chave (`-item.diagramas`) porque `sorted(reverse=True)` inverteria também o critério de
    desempate implícito, que é a ordem de entrada: dois livros com 300 diagramas apareceriam na
    ordem inversa da lista dada, e a grade mudaria de arranjo ao se trocar de ordem e voltar. Com a
    chave negativa a estabilidade do `sorted` continua valendo para os empates.

    **Os ausentes vão sempre para o fim**, pelo primeiro elemento booleano da tupla. Sem autor são
    33 dos 46, e um bloco de vazios no topo esconderia os 13 que têm autor -- que são exatamente os
    que a ordem por autor serve para agrupar.
    """
    if ordem == ORDEM_TITULO:
        return lambda item: dobrar(item.titulo)
    if ordem == ORDEM_AUTOR:
        return lambda item: (not item.autor.strip(), dobrar(item.autor))
    if ordem == ORDEM_ANO:
        return lambda item: (item.ano is None, item.ano if item.ano is not None else 0)
    if ordem == ORDEM_RECENTE:
        return lambda item: (item.aberto_em is None, -(item.aberto_em or 0.0))
    if ordem == ORDEM_DIAGRAMAS:
        return lambda item: -item.diagramas
    raise KeyError(f"ordem desconhecida: {ordem!r}. As válidas estão em ORDENS.")


# ---------------------------------------------------------------------------------- o filtro


@dataclass(frozen=True)
class Filtro:
    """O que a pessoa pediu: o texto da busca, o que marcou em cada eixo e por onde ordenar.

    **Congelado e com métodos que devolvem um novo**, e não mutável: o painel guarda o filtro em
    vigor e o troca inteiro a cada interação, o que faz "desfazer o último clique da lateral" ser
    guardar a referência anterior. Um filtro mutável partilhado entre o painel e o índice é a porta
    para a lista mostrar um estado e a lateral outro.
    """

    consulta: str = ""
    escolhas: tuple[tuple[str, frozenset[str]], ...] = ()
    ordem: str = ORDEM_TITULO

    def escolhidos(self, eixo: str) -> frozenset[str]:
        """O que está marcado naquele eixo. Vazio quer dizer *não filtre por este eixo*."""
        for chave, valores in self.escolhas:
            if chave == eixo:
                return valores
        return frozenset()

    def alternar(self, eixo: str, valor: str) -> Filtro:
        """Marca ou desmarca um valor, devolvendo o filtro novo. Não muda este.

        Levanta para eixo desconhecido: um clique na lateral que não casasse com nenhum eixo
        criaria uma escolha que nada consulta, e o efeito seria um botão que marca e não filtra.
        """
        if eixo not in EIXOS:
            raise KeyError(f"eixo de faceta desconhecido: {eixo!r}. Os válidos estão em EIXOS.")
        atuais = set(self.escolhidos(eixo))
        atuais.symmetric_difference_update({valor})
        restantes = [(chave, vals) for chave, vals in self.escolhas if chave != eixo]
        if atuais:
            restantes.append((eixo, frozenset(atuais)))
        # Ordenado **pelo nome do eixo**, e não pelo par: comparar tuplas cairia no `frozenset` do
        # segundo elemento em caso de empate, e a comparação de conjuntos é *inclusão* e não ordem
        # -- dois conjuntos disjuntos são incomparáveis nos dois sentidos, e o `sorted` devolveria
        # uma ordem que depende de qual veio primeiro. Os eixos nunca empatam, mas a armadilha fica
        # armada para quem acrescentar um.
        return replace(self, escolhas=tuple(sorted(restantes, key=lambda par: par[0])))

    def limpar(self) -> Filtro:
        """Sem busca e sem eixo marcado. A ordem **fica**: ela é preferência, não critério."""
        return replace(self, consulta="", escolhas=())

    @property
    def tem_criterio(self) -> bool:
        """Se alguma coisa está filtrando. É o que separa "vazio" de "sem resultado"."""
        return bool(self.consulta.strip() or self.escolhas)


_ENTRE_CAMPOS = "\n"
"""O que separa título, autor e editora dentro do texto de busca. Ver `texto_de_busca`."""


def texto_de_busca(item: ItemDaBiblioteca) -> str:
    """Título, autor e editora dobrados, num texto só. É o que a busca percorre.

    **Os três campos juntos com `\\n`, e o separador não é cosmético.** Sem ele, `Reinfeld` no fim
    do título e `Bruce` no começo do autor formariam o token colado `reinfeldbruce`, e uma busca
    por `dbr` casaria com um livro que não tem essa sequência em campo nenhum. O `\\n` não pode ser
    digitado por acidente: `dobrar` corta as pontas e `_SEPARADORES` o trata como separador, então
    nenhum termo de consulta chega aqui contendo um.

    Pública porque `casa_com` e o índice precisam da **mesma** string, e duas montagens do mesmo
    texto é o defeito que este projeto documenta em `resumo_do_dataset` para a estatística: elas não
    quebram, só passam a discordar no dia em que alguém acrescentar um quarto campo a uma delas.
    """
    return _ENTRE_CAMPOS.join(dobrar(campo) for campo in (item.titulo, item.autor, item.editora))


def casa_com(item: ItemDaBiblioteca, termos: Sequence[str]) -> bool:
    """Se o item satisfaz **todos** os termos da busca. Cada termo é substring do texto dobrado.

    **E, e não OU.** Digitar `reinfeld sacrifices` querendo os dois é o comportamento que toda
    caixa de busca tem; um OU devolveria os 12 livros de sacrifício mais o do Reinfeld, e a lista
    *cresceria* ao se digitar mais -- que é o contrário do que a pessoa está tentando fazer.

    **Substring e não só token inteiro.** `combinac` tem de achar `Combinações` -- é assim que se
    busca digitando, uma letra por vez, e uma busca que só responde a palavras completas fica muda
    justamente enquanto se digita. O custo é uma varredura linear sobre uma string de ~80
    caracteres por item; sobre 10.000 itens isso é medido em `tests/test_ui_biblioteca.py`.

    Sem termo nenhum passa tudo: uma busca vazia não é um filtro que não casa com nada.
    """
    if not termos:
        return True
    texto = texto_de_busca(item)
    return all(termo in texto for termo in termos)


@dataclass
class _Indexado:
    """O item mais o que foi pré-calculado dele. Interno: o índice não publica esta forma."""

    item: ItemDaBiblioteca
    busca: str
    valores: dict[str, str] = field(default_factory=dict)


class IndiceDaBiblioteca:
    """O acervo indexado: busca por substring e token, facetas com contagem viva, e ordem.

    **O pré-cálculo é o que faz a busca ser instantânea, e ele é feito uma vez.** Dobrar acento e
    montar tokens custa por caractere; fazê-lo dentro do laço de busca seria repetir esse custo a
    cada tecla, sobre o acervo inteiro. Aqui cada item dobra o título, o autor e a editora numa
    string só na construção, e a busca vira `termo in texto` -- que é a operação mais rápida que
    Python tem sobre `str`.

    **A string de busca junta os três campos com `\\n`.** Não é cosmético: sem separador,
    `Reinfeld` no fim do título e `Bruce` no começo do autor formariam o token colado
    `reinfeldbruce`, e uma busca por `dbr` casaria com um livro que não tem essa sequência em campo
    nenhum. O `\\n` não aparece em consulta nenhuma -- `dobrar` corta as pontas e
    `_SEPARADORES` o trata como separador --, então ele não pode ser digitado por acidente.

    **As contagens de faceta ignoram o próprio eixo, e é aqui que mora a decisão.** A contagem de
    "Alemão" é feita sobre o conjunto filtrado por *todos os outros* eixos e pela busca, mas **não**
    pelo eixo "Idioma". Contar sobre o conjunto totalmente filtrado faria "Alemão" valer 6 e todos
    os outros idiomas valerem 0 no instante em que se marca Alemão -- números verdadeiros e
    inúteis, porque a pergunta que a lateral responde é *quanto eu ganharia marcando também isto*.
    É o comportamento de facetas de qualquer loja, e a razão dele é essa.
    """

    def __init__(self, itens: Iterable[ItemDaBiblioteca]) -> None:
        self._itens: tuple[_Indexado, ...] = tuple(self._indexar(item) for item in itens)
        self._universo: dict[str, tuple[str, ...]] = {
            eixo: tuple(sorted({indexado.valores[eixo] for indexado in self._itens}, key=_chave_de_valor(eixo)))
            for eixo in EIXOS
        }
        """Todos os valores que o acervo tem em cada eixo, ordenados. **Do acervo e não do filtro**:
        é o que mantém a barra lateral com a mesma altura enquanto os números mudam."""

        self._consulta_em_cache: str | None = None
        self._achados_em_cache: tuple[_Indexado, ...] = ()
        """A última consulta de texto e o que ela achou. **Uma entrada, e ela basta**, porque o
        padrão de chamada é sempre o mesmo: a cada tecla o painel pede `filtrar` e depois as cinco
        `faceta`, isto é, **seis** varreduras de substring sobre a mesma consulta.

        Medido com 10.000 itens nesta máquina: as cinco facetas custavam **19,8 ms** por tecla, o
        que passa do quadro de 16,7 ms -- a busca perceptivelmente atrasada que este módulo existe
        para não ter. Com o cache elas custam o que está afirmado em `tests/test_ui_biblioteca.py`.

        O cache é invalidado por consulta diferente e morre com o índice; um acervo que mude troca
        de índice, e não de conteúdo -- ver o cabeçalho de `ItemDaBiblioteca` sobre o congelamento."""

    @staticmethod
    def _indexar(item: ItemDaBiblioteca) -> _Indexado:
        return _Indexado(
            item=item,
            busca=texto_de_busca(item),
            valores={eixo: _valor_do_eixo(item, eixo) for eixo in EIXOS},
        )

    def __len__(self) -> int:
        return len(self._itens)

    @property
    def itens(self) -> tuple[ItemDaBiblioteca, ...]:
        """O acervo inteiro, sem filtro nem ordem. É a ordem em que os itens foram dados."""
        return tuple(indexado.item for indexado in self._itens)

    def filtrar(self, filtro: Filtro) -> tuple[ItemDaBiblioteca, ...]:
        """Os itens que passam pela busca e por todos os eixos marcados, na ordem pedida.

        **A ordenação é estável**, e não por acaso: `sorted` preserva a ordem de entrada entre
        chaves iguais, e a ordem de entrada é a que o chamador deu -- normalmente alfabética por
        caminho. Sem isso, `ORDEM_DIAGRAMAS` embaralharia entre si os livros com a mesma contagem a
        cada repintura, e a grade "pularia" sob o ponteiro sem que nada tivesse mudado.
        """
        chave = chave_de_ordem(filtro.ordem)
        selecionados = [indexado.item for indexado in self._selecionar(filtro)]
        return tuple(sorted(selecionados, key=chave))

    def facetas(self, filtro: Filtro) -> tuple[Faceta, ...]:
        """Os cinco eixos, na ordem de `EIXOS`, cada um com contagem viva. **Uma passada só.**

        **Por que não são cinco chamadas a `faceta`.** Cada eixo conta sobre o conjunto filtrado
        *pelos outros*, o que sugere cinco varreduras -- e era o que estava aqui. Medido com 10.000
        itens nesta máquina: **19,8 ms por tecla**, contra um quadro de 16,7 ms. Uma busca que
        atrasa a cada letra é exatamente o defeito que este módulo existe para não ter.

        **A passada única sai de uma observação sobre a contagem de reprovações.** Percorrendo o
        resultado da busca uma vez e olhando, para cada item, em **quantos** eixos ativos ele é
        reprovado:

        - reprovado em **nenhum**: ele conta para os cinco eixos -- passa em todos, e portanto
          passaria também na versão de qualquer um deles que ignora a si mesmo;
        - reprovado em **exatamente um** eixo: ele conta **só** para aquele -- é justamente o eixo
          que se ignora ao contá-lo, e é isto que produz o "quanto eu ganharia marcando também
          isto" da barra lateral;
        - reprovado em **dois ou mais**: não conta para nenhum, porque qualquer que seja o eixo
          ignorado ainda sobra outro que o reprova.

        O laço interno sai no segundo insucesso, então o custo é O(n x eixos ativos) e não
        O(n x 5), e na abertura -- sem busca e sem eixo marcado -- ele nem roda: `_TOTAIS` já tem a
        resposta.
        """
        ativos = [(eixo, filtro.escolhidos(eixo)) for eixo in EIXOS if filtro.escolhidos(eixo)]
        achados = self._achados_da_consulta(filtro.consulta)
        if not ativos and len(achados) == len(self._itens):
            contagens = {eixo: dict(self._totais[eixo]) for eixo in EIXOS}
        else:
            contagens = {eixo: dict.fromkeys(self._universo[eixo], 0) for eixo in EIXOS}
            for indexado in achados:
                valores = indexado.valores
                reprovado: str | None = None
                duas_vezes = False
                for eixo, permitidos in ativos:
                    if valores[eixo] not in permitidos:
                        if reprovado is not None:
                            duas_vezes = True
                            break
                        reprovado = eixo
                if duas_vezes:
                    continue
                if reprovado is None:
                    for eixo in EIXOS:
                        contagens[eixo][valores[eixo]] += 1
                else:
                    contagens[reprovado][valores[reprovado]] += 1
        return tuple(self._montar(eixo, contagens[eixo], filtro.escolhidos(eixo)) for eixo in EIXOS)

    def _montar(self, eixo: str, contagens: Mapping[str, int], marcados: frozenset[str]) -> Faceta:
        return Faceta(
            eixo=eixo,
            rotulo=ROTULOS_DE_EIXO[eixo],
            valores=tuple(
                ValorDeFaceta(
                    valor=valor,
                    rotulo=_rotulo_de_valor(eixo, valor),
                    contagem=contagens[valor],
                    escolhido=valor in marcados,
                )
                for valor in self._universo[eixo]
            ),
        )

    def faceta(self, eixo: str, filtro: Filtro) -> Faceta:
        """Um eixo, com a contagem de cada valor sobre o filtrado **pelos outros** eixos.

        Levanta para eixo desconhecido. Ver o cabeçalho da classe para a razão de ignorar o próprio.
        """
        if eixo not in EIXOS:
            raise KeyError(f"eixo de faceta desconhecido: {eixo!r}. Os válidos estão em EIXOS.")
        marcados = filtro.escolhidos(eixo)
        contagens: dict[str, int] = dict.fromkeys(self._universo[eixo], 0)
        for indexado in self._selecionar(filtro, ignorando=eixo):
            contagens[indexado.valores[eixo]] += 1
        return Faceta(
            eixo=eixo,
            rotulo=ROTULOS_DE_EIXO[eixo],
            valores=tuple(
                ValorDeFaceta(
                    valor=valor,
                    rotulo=_rotulo_de_valor(eixo, valor),
                    contagem=contagens[valor],
                    escolhido=valor in marcados,
                )
                for valor in self._universo[eixo]
            ),
        )

    def _achados_da_consulta(self, consulta: str) -> tuple[_Indexado, ...]:
        """Os itens cujo texto casa com a consulta, com uma entrada de cache. Ver `__init__`."""
        if consulta == self._consulta_em_cache:
            return self._achados_em_cache
        termos = palavras(consulta)
        achados = (
            self._itens
            if not termos
            else tuple(
                indexado for indexado in self._itens if all(termo in indexado.busca for termo in termos)
            )
        )
        self._consulta_em_cache, self._achados_em_cache = consulta, achados
        return achados

    def _selecionar(self, filtro: Filtro, *, ignorando: str | None = None) -> list[_Indexado]:
        """O texto primeiro e os eixos depois, e a ordem é de custo.

        A consulta é a parte cara -- varredura de substring sobre cada item -- e é a **única** que
        se repete entre as seis chamadas de uma tecla; os eixos são consulta a um `dict` já
        montado. Filtrar por eixo primeiro tornaria o cache inútil, porque cada faceta ignora um
        eixo diferente e o conjunto de entrada da busca seria outro em cada uma delas.
        """
        ativos = [
            (eixo, filtro.escolhidos(eixo))
            for eixo in EIXOS
            if eixo != ignorando and filtro.escolhidos(eixo)
        ]
        achados = self._achados_da_consulta(filtro.consulta)
        if not ativos:
            return list(achados)
        return [
            indexado
            for indexado in achados
            if all(indexado.valores[eixo] in valores for eixo, valores in ativos)
        ]

    def resumo(self, filtro: Filtro) -> Resumo:
        """O que dizer quando não há grade para mostrar -- e são **dois** estados, não um.

        Ver `Resumo`. O método está aqui e não solto porque ele precisa dos dois números, e os dois
        números são do índice.
        """
        quantos = len(self.filtrar(filtro))
        return resumo_de(total=len(self._itens), visiveis=quantos, filtro=filtro)


def _chave_de_valor(eixo: str) -> Callable[[str], Any]:
    """Como os valores daquele eixo se ordenam na barra lateral.

    A época ordena **decrescente** -- 2020s antes de 1870s -- porque o acervo é comprado de trás
    para a frente e a década recente é a que se consulta. As outras ordenam alfabeticamente pelo
    rótulo visível, e não pela chave: ordenar `IDIOMAS` pelo código ISO poria "Alemão" (`de`) antes
    de "Inglês" (`en`) por coincidência e "Neerlandês" (`nl`) antes de "Português" (`pt`) por outra.

    Os ausentes vão para o fim em todos os eixos -- é a mesma regra de `_chave_de_ordem`, e pela
    mesma razão: um bloco de "sem editora" no topo esconderia as duas editoras que existem.
    """
    ausentes = {SEM_ANO, SEM_EDITORA, SEM_IDIOMA}
    if eixo == EIXO_ERA:
        return lambda valor: (valor in ausentes, -int(valor) if valor not in ausentes else 0)
    if eixo == EIXO_DIAGRAMAS:
        chaves = [chave for chave, _rotulo in DIAGRAMAS_ROTULOS]
        return lambda valor: chaves.index(valor) if valor in chaves else len(chaves)
    if eixo == EIXO_ESTADO:
        return lambda valor: 0 if valor == NAO_PROCESSADO else 1
    return lambda valor: (valor in ausentes, dobrar(_rotulo_de_valor(eixo, valor)))


# ---------------------------------------------------------------------- os estados sem grade

VAZIO = "vazio"
SEM_RESULTADO = "sem_resultado"
COM_RESULTADO = "com_resultado"


@dataclass(frozen=True)
class Resumo:
    """O que a área da grade diz quando ela não tem grade -- e os dois casos são diferentes.

    **"Não há livro nenhum" e "a busca não achou" pedem coisas opostas.** No primeiro a pessoa não
    fez nada de errado e não tem o que corrigir: a orientação é *como pôr livros aqui*. No segundo
    ela fez algo, e o que ela precisa é *o que desfazer* -- porque a lateral pode ter três eixos
    marcados dos quais ela só lembra de um. Um texto só para os dois estados vira "Nenhum livro
    encontrado", que não ajuda em nenhum dos casos.

    `acao` é o rótulo do único botão que o estado oferece, e ele também é diferente: escolher a
    pasta, ou limpar o filtro. `None` no estado com resultado, onde não há painel de estado nenhum.
    """

    estado: str
    titulo: str
    orientacao: str
    acao: str | None
    visiveis: int
    total: int

    @property
    def frase_de_contagem(self) -> str:
        """`46 livros` ou `7 de 46 livros`. O segundo número só aparece quando há filtro.

        Sem o "de 46", filtrar até sobrar um é indistinguível de o acervo ter um livro só -- que é
        o mesmo argumento de `resumo_do_dataset.frase_de_pagina`, e vale aqui por inteiro.
        """
        if self.total == 0:
            return "nenhum livro"
        plural = "livro" if self.total == 1 else "livros"
        if self.visiveis == self.total:
            return f"{self.total} {plural}"
        return f"{self.visiveis} de {self.total} {plural}"


def resumo_de(*, total: int, visiveis: int, filtro: Filtro) -> Resumo:
    """O `Resumo` daqueles números. Puro, e separado do índice para o teste montar os três casos.

    O estado é decidido por **duas** perguntas e não por uma: `visiveis == 0` diz que não há grade,
    e `filtro.tem_criterio` diz de quem é a culpa. Perguntar só a primeira é o que produz a tela
    genérica que o cabeçalho de `Resumo` descreve.
    """
    if visiveis:
        return Resumo(COM_RESULTADO, "", "", None, visiveis, total)
    if not filtro.tem_criterio or total == 0:
        return Resumo(
            estado=VAZIO,
            titulo="Nenhum livro no acervo",
            orientacao=(
                "Aponte a biblioteca para a pasta onde estão os seus PDFs. Nada é copiado nem "
                "movido: o acervo é lido de onde ele já está, e continua sendo seu."
            ),
            acao="Escolher a pasta…",
            visiveis=0,
            total=total,
        )
    return Resumo(
        estado=SEM_RESULTADO,
        titulo="Nenhum livro com esses critérios",
        orientacao=_o_que_desfazer(filtro, total),
        acao="Limpar a busca e os filtros",
        visiveis=0,
        total=total,
    )


def _o_que_desfazer(filtro: Filtro, total: int) -> str:
    """Diz **quais** critérios estão em vigor, por extenso. É a parte que a tela genérica não tem.

    Quem chegou aqui filtrou por até seis coisas -- a busca e cinco eixos --, e a barra lateral
    pode estar rolada para fora da vista. Repetir os critérios no lugar onde a grade estaria é o
    que evita a caçada pelo eixo esquecido, e é o que uma frase de "nenhum resultado" deve fazer.
    """
    partes: list[str] = []
    if filtro.consulta.strip():
        partes.append(f'a busca por "{filtro.consulta.strip()}"')
    for eixo, valores in sorted(filtro.escolhas, key=lambda par: EIXOS.index(par[0])):
        rotulos = ", ".join(sorted(_rotulo_de_valor(eixo, valor) for valor in valores))
        partes.append(f"{ROTULOS_DE_EIXO[eixo]}: {rotulos}")
    if not partes:  # pragma: no cover - `tem_criterio` já garante que há ao menos um
        return f"Os {total} livros do acervo continuam aqui."
    if len(partes) == 1:
        criterios = partes[0]
    else:
        criterios = ", ".join(partes[:-1]) + " e " + partes[-1]
    return f"Estão em vigor {criterios}. Os {total} livros do acervo continuam aqui — solte um critério."


# ------------------------------------------------------------------------- a virtualização

SOBRA = 1
"""Quantas **linhas** realizar acima e abaixo da vista. Ver o quarto bloco do cabeçalho.

Uma de cada lado, e não três: cada linha de sobra é `colunas` capas decodificadas que ninguém vê,
e numa grade de 6 colunas três linhas de sobra de cada lado são 36 capas de custo por 24
visíveis -- mais que o dobro do trabalho para esconder o mesmo quadro."""


@dataclass(frozen=True)
class FaixaVisivel:
    """Quais índices realizar, e onde a primeira linha deles começa.

    `[inicio, fim)` é semiaberto pela mesma razão de `range`: `fim - inicio` é a contagem, e o laço
    que pinta não precisa de um `+1` que alguém vai esquecer.

    `topo` é a coordenada Y da primeira linha realizada **no conteúdo**, e não na vista. Quem pinta
    subtrai o deslocamento; publicá-lo já subtraído faria a faixa depender de qual das duas origens
    o chamador usa, e o painel e o teste usam origens diferentes.
    """

    inicio: int
    fim: int
    primeira_linha: int
    linhas: int
    topo: int

    def __len__(self) -> int:
        return self.fim - self.inicio

    def __iter__(self) -> Iterator[int]:
        return iter(range(self.inicio, self.fim))

    @property
    def vazia(self) -> bool:
        return self.fim <= self.inicio


def janela_visivel(
    *,
    deslocamento: int,
    altura_da_vista: int,
    altura_do_item: int,
    colunas: int,
    total: int,
    sobra: int = SOBRA,
) -> FaixaVisivel:
    """A faixa de índices a realizar. **O(1)**: cinco divisões inteiras, e nenhum item é tocado.

    É a função que faz 10.000 capas responderem como 46. Ela não recebe os itens de propósito --
    receber a lista convidaria a fatiá-la, e uma fatia de 10.000 é uma cópia de 10.000 ponteiros
    por quadro de rolagem. Quem pinta indexa a lista pela faixa.

    **Os quatro casos de borda, e o que cada um devolve:**

    - `total == 0` → faixa vazia em `inicio == fim == 0`. Não é erro: é o acervo do primeiro dia, e
      quem chama pinta o `Resumo` no lugar da grade.
    - `total == 1` → uma linha, mesmo com 6 colunas. `linhas` conta linhas ocupadas, não a grade
      inteira.
    - a vista cabe tudo → `fim == total`, e a sobra não empurra `fim` além disso. Uma faixa que
      passasse do total viraria `IndexError` no primeiro laço que a usasse cru.
    - `altura_da_vista <= 0` → faixa vazia. É o widget antes do primeiro `resize`, e realizar a
      banda de sobra ali decodificaria capas para uma vista que ainda não tem tamanho.

    Levanta `ValueError` para `altura_do_item <= 0` ou `colunas <= 0`: os dois são divisores, e um
    zero ali seria `ZeroDivisionError` num `paintEvent` -- isto é, no lugar do programa onde uma
    exceção não tem para onde subir. `deslocamento` negativo é grampeado em zero, porque a barra de
    rolagem do Qt entrega isso durante o *overscroll* de um trackpad, e ali é estado e não erro.
    """
    if altura_do_item <= 0:
        raise ValueError(f"altura_do_item tem de ser positiva, e veio {altura_do_item!r}.")
    if colunas <= 0:
        raise ValueError(f"colunas tem de ser positivo, e veio {colunas!r}.")
    total = max(0, int(total))
    if total == 0 or altura_da_vista <= 0:
        return FaixaVisivel(0, 0, 0, 0, 0)

    deslocamento = max(0, int(deslocamento))
    linhas_no_total = (total + colunas - 1) // colunas
    primeira_visivel = min(deslocamento // altura_do_item, linhas_no_total - 1)
    ultima_visivel = min((deslocamento + altura_da_vista - 1) // altura_do_item, linhas_no_total - 1)

    sobra = max(0, int(sobra))
    primeira = max(0, primeira_visivel - sobra)
    ultima = min(linhas_no_total - 1, ultima_visivel + sobra)

    inicio = primeira * colunas
    fim = min(total, (ultima + 1) * colunas)
    return FaixaVisivel(
        inicio=inicio,
        fim=fim,
        primeira_linha=primeira,
        linhas=ultima - primeira + 1,
        topo=primeira * altura_do_item,
    )


def altura_do_conteudo(total: int, *, colunas: int, altura_do_item: int) -> int:
    """A altura que a grade inteira teria. É o alcance da barra de rolagem, e é O(1).

    Existe separada de `janela_visivel` porque quem a chama é outro: a barra é ajustada quando o
    acervo ou a largura mudam, e a faixa é pedida a cada pixel rolado. Calcular as duas juntas
    obrigaria a rolagem a refazer a conta da barra 60 vezes por segundo para descartá-la.
    """
    if colunas <= 0:
        raise ValueError(f"colunas tem de ser positivo, e veio {colunas!r}.")
    linhas = (max(0, int(total)) + colunas - 1) // colunas
    return linhas * max(0, int(altura_do_item))


def colunas_que_cabem(largura: int, *, largura_do_item: int, folga: int, minimo: int = 1) -> int:
    """Quantas capas cabem lado a lado nesta largura, contando a folga **entre** elas.

    `n` capas têm `n - 1` folgas e não `n`, e a diferença aparece no ponto de virada: com 200 px de
    capa e 12 de folga, uma largura de 624 px cabe 3 (600 + 24 de folga interna) e não cabe 3 pela
    conta errada (3 x 212 = 636). Errar isso faz a última coluna sair pela borda direita
    exatamente numa largura de janela -- o tipo de defeito que só aparece redimensionando devagar.

    **Nunca devolve zero.** Numa janela mais estreita que uma capa a grade mostra uma coluna e a
    capa é cortada pela vista, que é ruim e legível; zero colunas seria divisão por zero em
    `janela_visivel`, isto é, uma janela que não pinta.
    """
    if largura_do_item <= 0:
        raise ValueError(f"largura_do_item tem de ser positiva, e veio {largura_do_item!r}.")
    passo = largura_do_item + max(0, folga)
    cabem = (max(0, int(largura)) + max(0, folga)) // passo
    return max(int(minimo), int(cabem))


# ------------------------------------------------------------------------------- os números

_UNIDADES = ("B", "KiB", "MiB", "GiB")


def peso_no_disco(bytes_no_disco: int) -> str:
    """`832 MiB`, `18,4 MiB`, `—` para zero. Vírgula decimal, que é o separador de pt-BR.

    **Binário e não decimal** (`MiB` e não `MB`), porque é o que o explorador do Windows mostra
    para o mesmo arquivo -- e a biblioteca fica ao lado dele na tela de quem confere se copiou o
    livro certo. Duas réguas para o mesmo arquivo é a família de defeito que `ui/tokens.py`
    documenta para as cores, com outra unidade.

    Uma casa decimal só abaixo de 100, porque `832,4 MiB` tem quatro dígitos significativos para
    um número que ninguém soma -- e a grade de capas tem largura contada.
    """
    valor = float(max(0, int(bytes_no_disco)))
    if valor <= 0:
        return "—"
    unidade = 0
    while valor >= 1024 and unidade < len(_UNIDADES) - 1:
        valor /= 1024
        unidade += 1
    if unidade == 0 or valor >= 100:
        return f"{round(valor)} {_UNIDADES[unidade]}"
    return f"{valor:.1f}".replace(".", ",") + f" {_UNIDADES[unidade]}"
