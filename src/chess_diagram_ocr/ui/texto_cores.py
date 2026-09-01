"""A cor do autor, e o canal que ela **não** pode usar (S-242).

**O defeito que este módulo existe para impedir é de significado, e não de gosto.** Na aba de texto
a cor da letra já quer dizer uma coisa: `revisar` sai em `tokens.PROBLEMA` e `conferir` em
`tokens.ATENCAO` (`ui/texto_panel.PAPEL_DA_FAIXA`), com o corte emprestado do `MIN_CONFIDENCE` da
S-42 para a aba não discordar do resto do programa sobre o que é palpite. **Vermelho ali quer dizer
"o motor estava adivinhando".** Um botão de cor de texto com vermelho na paleta produziria duas
tintas iguais e dois significados na mesma linha -- e ninguém desfaz isso olhando: nem quem pintou,
três dias depois, nem quem receber o arquivo.

## Dois canais, dois donos

    confiança (faixa)      cor da LETRA      é o que já é hoje, e mexer nisso mudaria a aba sem pedido
    autor (marcação)       cor do FUNDO      canal livre: realce nunca é lido como "o motor adivinhou"
    autor (ênfase forte)   negrito/itálico   S-241, e sem cor nenhuma

Quem quiser mesmo a **letra** colorida tem a segunda metade da regra: a paleta do autor é de papéis
de `ui/tokens.py`, resolvidos no desenho, e ela **não oferece os papéis que a faixa usa**. `PROBLEMA`
e `ATENCAO` ficam fora por construção, e `test_a_paleta_do_autor_nao_usa_papel_de_faixa` afirma a
interseção vazia -- que é o critério de aceite do item.

## Por que a tabela mora aqui, e não em `text/rico.py`

O domínio nomeia o conceito (`"destaque"`, `"citacao"`) e a interface o resolve em cor. É a mesma
fronteira que `PAPEL_DA_FAIXA` já mantinha com `revisar`/`conferir`, e é o que faz o documento
sobreviver a uma troca de paleta sem que uma linha dele mude. Um hexadecimal escrito no lado do
documento seria a cor de hoje gravada dentro do arquivo de quem corrigiu a página -- e some quando
o fundo muda, que é o que a S-146 mediu no tabuleiro.

Nada de `tkinter` aqui, como em `ui/tokens.py` e `ui/comandos.py`.
"""

from __future__ import annotations

from ..text import documento, rico
from . import tokens

__all__ = [
    "PAPEIS_DA_FAIXA",
    "PAPEL_DA_COR",
    "PAPEL_DO_REALCE",
    "etiqueta_de_cor",
    "etiqueta_de_realce",
    "papel_de_cor",
    "papel_de_realce",
]

PAPEL_DA_COR: dict[str, str] = {
    "destaque": tokens.AUTOR_DESTAQUE,
    "citacao": tokens.AUTOR_CITACAO,
    "nota": tokens.AUTOR_NOTA,
    "variante": tokens.AUTOR_VARIANTE,
}
"""Nome de `rico.CORES_DE_AUTOR` -> papel da **letra**.

As chaves são exatamente `rico.CORES_DE_AUTOR`, e o teste cobra a igualdade nos dois sentidos: um
nome sem papel desenharia sem cor, e um papel sem nome é tinta que ninguém alcança."""

PAPEL_DO_REALCE: dict[str, str] = {
    "destaque": tokens.REALCE_DESTAQUE,
    "citacao": tokens.REALCE_CITACAO,
    "nota": tokens.REALCE_NOTA,
    "variante": tokens.REALCE_VARIANTE,
}
"""O mesmo nome -> papel do **fundo**. É este o canal do autor; o de cima é a concessão."""

PAPEL_DA_FAIXA: dict[str, str] = {
    documento.REVISAR: tokens.PROBLEMA_TEXTO,
    documento.CONFERIR: tokens.ATENCAO,
    documento.TRANQUILO: "",
}
"""O papel de cor de cada faixa de `documento`, resolvido em `ui/tokens.py`.

**É `PROBLEMA_TEXTO` e não `PROBLEMA`, e a troca é o item** (S-295). `PROBLEMA` está declarado em
`tokens.SIGNIFICADO` como marcação de **tabuleiro** -- contorno de casa --, e usá-lo aqui pintava
letra com o papel do contorno: um papel, dois significados, que é o defeito que a S-158 nomeou e a
S-224 separou para o cromo escuro.

Papel e não hexadecimal, pela regra que `tokens` inteiro existe para manter: uma cor cravada aqui
não acompanharia a troca de pele.

**Mora aqui desde a S-504, e a mudança fechou uma nota deste arquivo.** Ela era de
`ui/texto_panel.py`, e `PAPEIS_DA_FAIXA` logo abaixo dizia, por escrito, que não dava para derivá-la
*"porque `ui/texto_panel.PAPEL_DA_FAIXA` importa `tkinter` por tabela, e este módulo não pode"* -- e
por isso as duas eram declaradas separadas e comparadas por teste. O segundo frontend precisava da
mesma tabela e não podia importar aquele arquivo tampouco; descê-la resolveu os dois de uma vez."""

PAPEIS_DA_FAIXA: frozenset[str] = frozenset(papel for papel in PAPEL_DA_FAIXA.values() if papel)
"""Os papéis que a **faixa de confiança** usa na aba. **Derivados**, desde a S-504.

Eram declarados à mão e comparados com `PAPEL_DA_FAIXA` por um teste, porque a tabela morava num
arquivo que este módulo não podia importar. Agora ela mora aqui, e uma faixa nova entra nos dois
lugares sozinha."""

PREFIXO_DE_COR = "cor:"
PREFIXO_DE_REALCE = "realce:"
"""Como os dois viram etiqueta do `tk.Text`. Ver `ui/texto_etiquetas.py`: nome de etiqueta é string,
e atributo com valor precisa carregar o valor no nome."""


def papel_de_cor(nome: str) -> str:
    """O papel de letra daquele nome de cor. Levanta `KeyError` para nome que ninguém desenhou.

    Levanta, como `tokens.cor` e `estilos.estilo_de_botao`: um nome escrito errado que virasse "sem
    cor" é o estado que o campo veio impedir, e ele voltaria sem ninguém notar.
    """
    if nome not in PAPEL_DA_COR:
        raise KeyError(f"cor de autor desconhecida: {nome!r}. As válidas estão em rico.CORES_DE_AUTOR.")
    return PAPEL_DA_COR[nome]


def papel_de_realce(nome: str) -> str:
    """O papel de fundo daquele nome de cor."""
    if nome not in PAPEL_DO_REALCE:
        raise KeyError(f"realce de autor desconhecido: {nome!r}. Os válidos estão em rico.CORES_DE_AUTOR.")
    return PAPEL_DO_REALCE[nome]


def etiqueta_de_cor(nome: str) -> str:
    """`"destaque"` -> `"cor:destaque"`, a etiqueta que o widget carrega."""
    return f"{PREFIXO_DE_COR}{nome}"


def etiqueta_de_realce(nome: str) -> str:
    """`"destaque"` -> `"realce:destaque"`."""
    return f"{PREFIXO_DE_REALCE}{nome}"


def nomes() -> tuple[str, ...]:
    """Os nomes de cor do autor, na ordem em que a paleta os oferece.

    Sai de `rico.CORES_DE_AUTOR` e não de uma segunda lista: o dia em que uma cor nova entrar no
    documento, ela aparece no menu sem que ninguém venha aqui -- e, se ninguém lhe der papel,
    `papel_de_cor` levanta em vez de desenhar cinza.
    """
    return rico.CORES_DE_AUTOR
