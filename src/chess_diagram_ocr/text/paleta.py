"""A paleta de glifos e símbolos, **derivada do metadado do modelo** (S-246/S-247/S-248).

**A solução óbvia é a errada.** Escrever a lista de símbolos à mão cria uma segunda lista ao lado da
que o modelo usa, e a primeira divergência entre as duas é um símbolo que a pessoa insere e que o
OCR nunca poderá ler de volta -- o mesmo defeito que a S-219 tirou dos comandos, agora em símbolo.

Por isso a paleta sai de `models/char_meta.json`, que já traz `idx_to_char` e já é carregado com
verificação de `classes_sha256` (`text/modelo.py`). Medido em 2026-08-24, 314 classes:

    alfanuméricas ASCII      62    não entram: o teclado já as tem
    símbolos ASCII           24    ! " # % & ' ( ) * + , - . / : ; = ? @ [ ] _ | ~
    Unicode fora do ASCII    89    ♔ ♕ ♖ ♗ ♘ ♙ ± ∓ ⩲ ⩱ ∞ ⇄ → ½ – — • e os acentuados
    ligaduras               139    !! !? ?! ?? +- -+ fi ffl ♕x ♗a xf6 e4

## A prateleira é dado declarado, e "não identificado" é resposta

O nome da prateleira de cada símbolo está numa tabela. Símbolo que ninguém classificou **não some**:
cai em "não identificado", que é uma prateleira de verdade e uma lista de trabalho para quem for
auditar a base.

A regra não é teórica. Entre as 89 classes Unicode há `⯹ ⯺ ⯻ ⯼ ⯽ ⨀ ⨼ ⟪ ⮜ ⮞ 🗸 ✝`, resíduo de
mapeamento das fontes de xadrez dos livros de origem -- a mesma família de acidente que a S-180
registra em `sym_f7`, onde 127 imagens da casa `f7` estavam rotuladas como `÷`. Escondê-los faria a
paleta mentir sobre o que o modelo pode devolver; mostrá-los sem nome faria a paleta parecer
quebrada.

## Ligadura não é símbolo de inserir

`xf6` é classe do modelo porque o glifo vem colado no papel, e não porque alguém queira inserir
"xf6" como símbolo -- quem quer digita `x`, `f`, `6`. Elas ficam **fora** da paleta e continuam
declaradas aqui, porque a busca da S-245 as conhece.

## As duas prateleiras da S-247, e por que a segunda é derivada

As seis figurinas do modelo são **só as brancas**: `♔♕♖♗♘♙` são classes, `♚♛♜♝♞♟` não são. Não é
buraco da base -- é o que o acervo imprime, porque em notação figurina o símbolo diz a *peça* e o
número do lance diz a *cor*.

Quem escreve texto novo quer `♞` às vezes; quem corrige uma página de OCR **não**, porque aquele
texto volta para a fila de revisão da S-212 e nenhuma classe pode confirmar o que ele inseriu. Daí
as duas prateleiras -- e a segunda é a **diferença** entre o que se oferece e o que o modelo lê, e
não uma lista à mão: assim ela encolhe sozinha no dia em que um modelo novo aprender as pretas.

## Nada de `tkinter`, e nada de `torch`

`text/modelo.py` importa `torch` só sob `TYPE_CHECKING`, então ler o metadado é barato. Este módulo
é lido na construção da aba, que acontece na abertura da janela -- e pagar um framework de
aprendizado para desenhar uma lista de símbolos atrasaria a janela inteira.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import notacao
from .modelo import CAMINHO_PADRAO_META, MetadadoDeClasses, ModeloInvalido, ler_metadado

__all__ = [
    "EXTRAS_DECLARADOS",
    "MINIMA",
    "NAO_IDENTIFICADO",
    "PRATELEIRA_DO_SIMBOLO",
    "SEQUENCIAS_DECLARADAS",
    "Paleta",
    "Prateleira",
    "SequenciaInvalida",
    "de_metadado",
    "paleta",
]

NAO_IDENTIFICADO = "Não identificado"
"""O nome da prateleira do que ninguém classificou. Ver "A prateleira é dado declarado"."""

FORA_DO_MODELO = "O modelo não lê"
"""A prateleira da S-247: inserir daqui é permitido, e **marca** a corrida."""


PRATELEIRA_DO_SIMBOLO: dict[str, str] = {
    **dict.fromkeys("♔♕♖♗♘♙♚♛♜♝♞♟", "Figurinas"),
    **dict.fromkeys("±∓⩲⩱∞", "Avaliação"),
    **dict.fromkeys("!?+#=", "Anotação de lance"),
    **dict.fromkeys("→↑⇄⇔⇗⬄⟳Δ", "Setas e ideias"),
    **dict.fromkeys("■□△▼○★☆⊞⊥∟⌓✕", "Formas"),
    **dict.fromkeys('"\'(),-./:;[]_|~%&*@', "Pontuação"),
    **dict.fromkeys("–—•©½", "Tipografia"),
    **dict.fromkeys(
        "ÁÃÄÅÈÉËÍÑÓÕÖÚÝàáâãäåçèéêíóôõöúüýĆćČčńŠšŽž",
        "Acentuados",
    ),
    **dict.fromkeys("⯹⯺⯻⯼⯽⨀⨼⟪⮜⮞🗸✝", NAO_IDENTIFICADO),
}
"""Símbolo -> nome da prateleira. **Tabela, e não heurística.**

O que está em `NAO_IDENTIFICADO` já na declaração é o resíduo de mapeamento que a base carrega e
que ninguém identificou -- ele aparece nomeado como não identificado, que é diferente de cair lá
por esquecimento. Símbolo fora desta tabela cai na mesma prateleira, e o teste afirma que **nenhum
é descartado**.

**As doze figurinas estão aqui, e o modelo só lê seis.** A tabela diz *onde o símbolo mora*, e não
*se ele existe*: as pretas de `EXTRAS_DECLARADOS` entram pela prateleira da S-247 enquanto nenhuma
classe as confirma, e passam para "Figurinas" sozinhas no dia em que um modelo as aprender. Era
esse o critério de aceite -- mover de prateleira **sem tocar em código** --, e ele só se cumpre se
o destino delas já estiver declarado."""


EXTRAS_DECLARADOS: tuple[str, ...] = (
    "♚",
    "♛",
    "♜",
    "♝",
    "♞",
    "♟",
    "…",
    "“",
    "”",
    "‘",
    "’",
)
"""O que o Unicode tem, o acervo usa e a base **não** lê (S-247).

As seis figurinas pretas pelo motivo medido no cabeçalho; as reticências e as aspas tipográficas
porque livro impresso as usa e o modelo só conhece `.` e `'` de ASCII -- quem escreve um texto
próprio nesta aba quer as certas.

**A prateleira "o modelo não lê" não é esta lista**: é esta lista **menos** as classes do modelo.
Um modelo treinado com as pretas as move para a primeira prateleira sem que ninguém venha aqui."""


SEQUENCIAS_DECLARADAS: dict[str, str] = {
    "K": "♔",
    "Q": "♕",
    "R": "♖",
    "B": "♗",
    "N": "♘",
    "P": "♙",
    "k": "♚",
    "q": "♛",
    "r": "♜",
    "b": "♝",
    "n": "♞",
    "p": "♟",
    "+-": "±",
    "-+": "∓",
    "+=": "⩲",
    "=+": "⩱",
    "inf": "∞",
    "...": "…",
}
"""O que vem **depois da barra invertida**: `\\N` vira `♘`, `\\+-` vira `±` (S-248).

**A barra invertida é a marca de escape porque ela é o caractere mais raro do acervo**, e isso foi
medido em 2026-08-24 sobre 141.353 caracteres de camada de texto (4 páginas de cada um dos 41
livros de `PDF/`):

    \\    10 ocorrências, em 6 livros       #    14
    |     5                                ~    11
                                           @    46

Dez em 141 mil, e nenhuma delas é tipografia -- as quatro do `AAGAARD` estão numa camada de OCR de
terceiro, que é ruído por origem. Não é zero, e o item não finge que seja: é um caractere que
aparece uma vez a cada catorze mil, contra `@`, que aparece cinco vezes mais.

**A tabela é conferida contra a paleta na montagem** (`conferir_sequencias`): sequência que aponta
para símbolo que a paleta não oferece levanta, e a mesma sequência para dois símbolos levanta.
Duas sequências para o **mesmo** símbolo é permitido -- `\\N` e `\\n` chegam à mesma peça em
livros de notação figurina."""


MINIMA: tuple[str, ...] = ("♔", "♕", "♖", "♗", "♘", "♙", "±", "∓", "⩲", "⩱", "∞", "–", "—", "…")
"""O conjunto mínimo para quando `char_meta.json` não está no disco.

É a regra de `ui/theme.py:12-15` -- **aparência não derruba ferramenta**: sem metadado a aba abre,
a paleta encolhe e o que sobra é o que um livro de xadrez sempre precisa. Um clone sem os modelos é
o caso comum: o metadado é versionado, mas o `.pt` não, e nada garante que quem clonou tenha os
dois."""


class SequenciaInvalida(ValueError):
    """A tabela de sequências aponta para símbolo que a paleta não oferece, ou se repete."""


@dataclass(frozen=True)
class Prateleira:
    """Um grupo nomeado de símbolos, na ordem em que a paleta os mostra."""

    nome: str
    simbolos: tuple[str, ...]
    do_modelo: bool = True
    """`False` na prateleira da S-247: inserir dali marca a corrida com `fora_do_modelo`."""


@dataclass(frozen=True)
class Paleta:
    """O que a aba oferece para inserir, já agrupado."""

    prateleiras: tuple[Prateleira, ...] = ()
    ligaduras: tuple[str, ...] = ()
    """As classes de mais de um caractere. **Não entram na paleta** -- ver o cabeçalho."""

    @property
    def simbolos(self) -> tuple[str, ...]:
        """Todos os símbolos oferecidos, na ordem das prateleiras."""
        return tuple(s for prateleira in self.prateleiras for s in prateleira.simbolos)

    @property
    def fora_do_modelo(self) -> frozenset[str]:
        """Os que nenhuma classe pode confirmar. É o que decide a marca da S-247."""
        return frozenset(
            s for prateleira in self.prateleiras if not prateleira.do_modelo for s in prateleira.simbolos
        )

    def marca(self, simbolo: str) -> bool:
        """Inserir este símbolo marca a corrida? Ver `Atributos.fora_do_modelo`."""
        return simbolo in self.fora_do_modelo

    def sequencias(self) -> dict[str, str]:
        """As sequências de teclado válidas **nesta** paleta, conferidas (S-248).

        Derivadas e não escritas ao lado: cada uma aponta para um símbolo que a paleta já oferece,
        e uma que aponte para símbolo inexistente levanta em vez de virar tecla morta.
        """
        return conferir_sequencias(SEQUENCIAS_DECLARADAS, self.simbolos)


def conferir_sequencias(declaradas: dict[str, str], oferecidos: tuple[str, ...]) -> dict[str, str]:
    """As sequências válidas, levantando o que a S-248 manda levantar.

    Duas regras, e as duas são do critério de aceite: sequência para símbolo que a paleta não
    oferece **levanta** (é tecla que não faz nada, e a legenda a prometeria), e a mesma sequência
    para dois símbolos **levanta** (a segunda apagaria a primeira em silêncio).
    """
    conjunto = set(oferecidos)
    vistas: dict[str, str] = {}
    for sequencia, simbolo in declaradas.items():
        if simbolo not in conjunto:
            raise SequenciaInvalida(
                f"a sequência \\{sequencia} aponta para {simbolo!r}, que a paleta não oferece."
            )
        if sequencia in vistas and vistas[sequencia] != simbolo:
            raise SequenciaInvalida(
                f"a sequência \\{sequencia} aponta para {vistas[sequencia]!r} e para {simbolo!r}."
            )
        vistas[sequencia] = simbolo
    return vistas


def _familia(classe: str) -> str:
    """A que família aquela classe pertence: `ligadura`, `alfanumerica` ou `simbolo`."""
    if len(classe) != 1:
        return "ligadura"
    if classe.isascii() and classe.isalnum():
        return "alfanumerica"
    return "simbolo"


def de_metadado(meta: MetadadoDeClasses) -> Paleta:
    """A paleta daquele metadado. É a única forma de construir uma com o modelo real.

    A ordem das prateleiras é a de `PRATELEIRA_DO_SIMBOLO`, e dentro delas a de declaração -- e não
    a do índice da classe, que é ordem de treino e não diz nada a quem procura uma figurina.
    """
    classes = set(meta.alfabeto)
    ligaduras = tuple(sorted(c for c in meta.alfabeto if _familia(c) == "ligadura"))
    simbolos = [c for c in meta.alfabeto if _familia(c) == "simbolo"]
    return _montar(simbolos, classes, ligaduras)


def _montar(simbolos: list[str], classes: set[str], ligaduras: tuple[str, ...]) -> Paleta:
    ordem = list(dict.fromkeys(PRATELEIRA_DO_SIMBOLO.values())) + [NAO_IDENTIFICADO]
    por_prateleira: dict[str, list[str]] = {nome: [] for nome in ordem}
    for declarado in PRATELEIRA_DO_SIMBOLO:
        if declarado in simbolos:
            por_prateleira[PRATELEIRA_DO_SIMBOLO[declarado]].append(declarado)
    # **Nenhum símbolo é descartado em silêncio**: o que a tabela não nomeia cai em "não
    # identificado", que é resposta e não esquecimento.
    for simbolo in simbolos:
        if simbolo not in PRATELEIRA_DO_SIMBOLO:
            por_prateleira[NAO_IDENTIFICADO].append(simbolo)

    prateleiras = [
        Prateleira(nome=nome, simbolos=tuple(itens)) for nome, itens in por_prateleira.items() if itens
    ]
    faltantes = tuple(s for s in EXTRAS_DECLARADOS if s not in classes)  # a diferença é a S-247
    if faltantes:
        prateleiras.append(Prateleira(nome=FORA_DO_MODELO, simbolos=faltantes, do_modelo=False))
    return Paleta(prateleiras=tuple(prateleiras), ligaduras=ligaduras)


def paleta(caminho: Path | None = None) -> Paleta:
    """A paleta do modelo instalado, ou a mínima quando o metadado não está no disco.

    **Degradar e não levantar**: a aba abre igual, com menos símbolos, e quem quiser o resto instala
    o modelo. É o contrato de `ui/theme.py` -- aparência não derruba ferramenta.
    """
    try:
        meta = ler_metadado(caminho or CAMINHO_PADRAO_META)
    except (ModeloInvalido, OSError):
        return _montar(list(MINIMA), set(MINIMA), ())
    return de_metadado(meta)


def figurinas(paleta_atual: Paleta) -> tuple[str, ...]:
    """As figurinas oferecidas -- as do modelo e as que ele não lê, nesta ordem.

    Serve ao comando `inserir_figurina` (S-248), que é o mesmo símbolo por três portas: o painel, a
    sequência de teclado e a paleta de comandos da S-231.
    """
    todas = notacao.FIGURINAS
    return tuple(s for s in paleta_atual.simbolos if s in todas)


def avaliacoes(paleta_atual: Paleta) -> tuple[str, ...]:
    """Os símbolos de avaliação oferecidos, para o comando `inserir_avaliacao`."""
    return tuple(
        s
        for prateleira in paleta_atual.prateleiras
        if prateleira.nome == "Avaliação"
        for s in prateleira.simbolos
    )
