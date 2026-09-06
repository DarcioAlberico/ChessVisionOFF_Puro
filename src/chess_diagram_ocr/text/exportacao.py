"""A exportação do editor: um lugar só decide o que cada formato faz (S-250 a S-252).

**A pergunta que os quatro formatos responderiam sozinhos, se ninguém decidisse por eles:** o que
acontece com `[Diagrama N]`? Ela não é pequena. `text/documento.py` já explica por que a marca
existe -- *"é o que permite mover o diagrama de lugar no texto, e é o que volta ao arquivo quando
alguém exporta. Um diagrama desenhado sem marca correspondente seria invisível para o texto -- e a
primeira edição o perderia."* Quatro exportadores escritos separadamente dariam quatro respostas, e
três estariam erradas em silêncio.

| formato | o diagrama vira | a marca `[Diagrama N]` |
|---|---|---|
| `.txt` | nada | **fica** -- é a única referência que sobra |
| `.md` | `![Diagrama 3](pasta/diagrama_03.png)` mais a FEN em comentário | fica, como texto alternativo |
| `.html` | `<img>` com a FEN no `alt` e no `data-fen` | fica, no `alt` |
| `.rtf` | imagem embutida quando há recorte; a marca sempre | fica, como texto ao lado |

**A marca nunca desaparece**, nem quando a imagem entra, e o teste afirma isso nos quatro. O quinto
formato -- o PDF pesquisável da S-253 -- mora em `text/pdf_pesquisavel.py`: ele não serializa texto,
escreve uma camada invisível sobre a página original, e a marca **não** entra nela. A tabela da
S-250 já dizia isso ("não se escreve: a página é a de origem"), e a razão é que a camada existe para
espelhar o texto do livro: um `[Diagrama 3]` ali apareceria a quem copiasse a página e nunca esteve
impresso nela.

## Atributo que o formato não tem é perdido **explicitamente**

Cada formato declara o que suporta, e `exportar` conta o que caiu. Uma perda silenciosa é o que faz
alguém descobrir três meses depois que a exportação apagou o trabalho -- e o `.txt`, que é o formato
que mais perde, é justamente o mais usado.

## O `.txt` sai byte a byte igual ao de antes

É a trava de não-regressão do item: o cabeçalho é o mesmo de `documento.texto_para_arquivo`, o corpo
é o texto corrido, e a exportação inteira passou a sair daqui **sem** mudar um caractere do que a aba
já gravava.

Nada de `tkinter` aqui: quem escolhe o arquivo é o painel; quem decide o conteúdo é este módulo.
"""

from __future__ import annotations

import html as _html
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Protocol

from . import documento
from .rico import Atributos, Corrida, DocumentoRico

__all__ = [
    "ALINHAMENTOS_DO_HTML",
    "ATRIBUTOS",
    "CONTROLE_DE_ALINHAMENTO_RTF",
    "FORMATOS",
    "Formato",
    "Html",
    "Markdown",
    "Relatorio",
    "Rtf",
    "Texto",
    "classe_de_corpo",
    "exportar",
    "formato_de",
    "suporte_por_formato",
]

ALINHAMENTOS_DO_HTML: dict[str, str] = {
    "esquerda": "left",
    "centro": "center",
    "direita": "right",
    "justificado": "justify",
}
"""Alinhamento do documento -> `text-align` do CSS (S-259).

**Os quatro saem inteiros aqui, o justificado inclusive** -- e é a diferença entre este formato e a
tela. `JUSTIFICACAO_DO_ALINHAMENTO`, em `ui/texto_panel.py`, deixa cair o justificado porque o
`tk.Text` não sabe esticar espaço entre palavras; o navegador sabe. O atributo atravessa o documento
inteiro e cada saída faz o que pode com ele, que é o que a tabela de perdas deste módulo mede."""

CONTROLE_DE_ALINHAMENTO_RTF: dict[str, str] = {
    "esquerda": "\\ql",
    "centro": "\\qc",
    "direita": "\\qr",
    "justificado": "\\qj",
}
"""O mesmo em RTF. Os quatro existem no formato desde o RTF 1.0, e nenhum é aproximação."""

PREFIXO_DE_CORPO = "corpo"
"""O começo do nome de classe de um degrau de corpo no HTML: `corpo-mais-2`, `corpo-menos-1`."""


def classe_de_corpo(degrau: int) -> str:
    """O nome de classe daquele degrau (S-260). `+2` -> `corpo-mais-2`, `-1` -> `corpo-menos-1`.

    **Nome com palavra, e não com sinal**, porque `-` abre nome de classe negativo em CSS e `+` não
    é caractere de nome nenhum: `.corpo--1` e `.corpo-+2` são seletores que o navegador descarta em
    silêncio. Uma função e não um `f-string` espalhado porque quem escreve a classe (`_classes`) e
    quem escreve a regra (`ui/texto_panel`) têm de produzir exatamente o mesmo nome."""
    lado = "mais" if degrau > 0 else "menos"
    return f"{PREFIXO_DE_CORPO}-{lado}-{abs(int(degrau))}"


ATRIBUTOS: tuple[str, ...] = tuple(campo.name for campo in fields(Atributos))
"""Os atributos que um formato pode ou não expressar -- **derivados de `Atributos`**.

Recopiar a lista faria um atributo novo entrar sem que nenhum formato dissesse o que faz com ele, e
o teste da S-256 existe justamente para isso não acontecer."""


@dataclass(frozen=True)
class Relatorio:
    """O que a exportação escreveu, o que ela perdeu e o que ela avisa (S-250/S-254)."""

    conteudo: str = ""
    perdas: Mapping[str, int] = field(default_factory=dict)
    """Atributo -> quantas corridas o traziam e o formato não expressa."""

    avisos: tuple[str, ...] = ()
    """O que não é perda e quem recebe o arquivo precisa saber."""

    diagramas: int = 0
    sem_recorte: int = 0
    """Diagramas que o formato desenharia e não tinham imagem no disco."""

    @property
    def perdeu(self) -> bool:
        return any(self.perdas.values())

    def resumo(self) -> str:
        """As perdas em uma linha, em pt-BR. Vazio quando não houve nenhuma."""
        partes = [f"{quantos} {atributo}" for atributo, quantos in sorted(self.perdas.items()) if quantos]
        return ", ".join(partes)


class Formato(Protocol):
    """O contrato de um formato. Quem o cumpre não sabe que existe um arquivo.

    **`montar` e `paragrafo` são opcionais**, e `exportar` os procura com `getattr`. Não é frouxidão:
    é o que permite um formato dizer "não tenho isto" sem escrever um método que devolve o argumento
    intacto. Os dois nasceram assim -- `montar` para o `.txt` sair byte a byte igual ao de antes
    (S-250), `paragrafo` para o alinhamento da S-259, que dois dos quatro formatos não expressam.
    """

    extensao: str
    nome: str
    suporta: frozenset[str]

    def cabecalho(self, doc: DocumentoRico) -> str: ...

    def corrida(self, c: Corrida) -> str: ...

    def diagrama(self, c: Corrida, recorte: Path | None) -> str: ...

    def rodape(self, doc: DocumentoRico) -> str: ...

    def montar(self, cabecalho: str, corpo: str, rodape: str) -> str: ...

    def paragrafo(self, alinhamento: str, corpo: str) -> str: ...


def _cabecalho_de_procedencia(doc: DocumentoRico) -> str:
    """A linha `# livro — folha N`, a mesma que o `.txt` da aba já escrevia desde a S-211."""
    pagina = doc.origem
    if pagina is None:
        return ""
    return documento.texto_para_arquivo(pagina).split("\n\n", 1)[0] + "\n\n"


@dataclass(frozen=True)
class Texto:
    """`.txt`: texto puro, com o cabeçalho de procedência. **Perde tudo o mais, e diz.**"""

    extensao: str = ".txt"
    nome: str = "Texto"
    suporta: frozenset[str] = frozenset()

    def cabecalho(self, doc: DocumentoRico) -> str:
        return _cabecalho_de_procedencia(doc)

    def corrida(self, c: Corrida) -> str:
        return c.texto

    def diagrama(self, c: Corrida, recorte: Path | None) -> str:
        # A marca e nada mais: no texto puro ela é a única referência que sobra ao diagrama.
        return c.texto

    def rodape(self, doc: DocumentoRico) -> str:
        return ""

    def montar(self, cabecalho: str, corpo: str, rodape: str) -> str:
        """**A trava de não-regressão do item**: o `.txt` sai byte a byte igual ao de antes.

        A aba gravava `cabecalho + conteudo.strip() + chr(10)` desde a S-211, e é isso que continua
        saindo -- o corpo aparado nas pontas, o cabeçalho intacto e a quebra final que todo arquivo
        de texto tem. Aparar o conteúdo inteiro tiraria a quebra dupla do cabeçalho.
        """
        return cabecalho + corpo.strip() + chr(10)


@dataclass(frozen=True)
class Markdown:
    """`.md`: **porque ele diffa.**

    Uma página corrigida hoje e recorrigida amanhã produz duas versões comparáveis linha a linha, e
    é assim que se vê o que mudou. Negrito é `**`, itálico é `*`, tachado é `~~`, título é `#`. A cor
    de autor não tem sintaxe e é declarada como perda; a faixa de confiança, o alinhamento e o corpo
    também -- e é por isso que o `.md` **não** é o formato para mandar a folha diagramada a alguém.
    """

    extensao: str = ".md"
    nome: str = "Markdown"
    suporta: frozenset[str] = frozenset({"negrito", "italico", "tachado", "estilo"})
    pasta_de_imagens: str = "diagramas"

    def cabecalho(self, doc: DocumentoRico) -> str:
        return _cabecalho_de_procedencia(doc)

    def corrida(self, c: Corrida) -> str:
        texto = c.texto
        if not texto.strip():
            return texto
        # A ordem importa: `***texto***` é o que o Markdown lê como negrito **e** itálico.
        if c.atributos.italico:
            texto = _cercado(texto, "*")
        if c.atributos.negrito:
            texto = _cercado(texto, "**")
        # `~~` é do GitHub Flavored Markdown e não do Markdown de 2004. Entra assim mesmo: o motivo
        # de este formato existir é diffar, e quem diffa é um servidor de git -- todos os quais o
        # entendem. Alinhamento e corpo **não** têm sintaxe nem no GFM, e saem como perda contada.
        if c.atributos.tachado:
            texto = _cercado(texto, "~~")
        if c.atributos.estilo == "titulo":
            texto = f"# {texto.lstrip()}"
        return texto

    def suporta_valor(self, atributo: str, valor: object) -> bool:
        """O `.md` escreve **um** estilo de parágrafo, e é o título (S-339).

        `suporta` responde por atributo e diz "estilo: sim" por causa do `# `; os outros três --
        prosa, notação e legenda -- não têm sintaxe no Markdown e saíam como texto comum, com o
        relatório dizendo "perdido: nada". Uma perda contada é o que separa "o formato não
        carrega isto" de "o formato carregou".
        """
        return atributo != "estilo" or valor == "titulo"

    def diagrama(self, c: Corrida, recorte: Path | None) -> str:
        alvo = f"{self.pasta_de_imagens}/{recorte.name}" if recorte is not None else ""
        marca = c.texto
        if not alvo:
            return marca
        return f"![{marca}]({alvo})"

    def rodape(self, doc: DocumentoRico) -> str:
        return ""


@dataclass(frozen=True)
class Html:
    """`.html`: **porque ele abre.**

    É o único formato desta fase que mostra, no navegador de qualquer máquina, exatamente o que a
    aba mostrava: negrito, itálico, cor de autor, faixa de confiança, figurina e diagrama. E é o
    formato para mandar a página corrigida para alguém.

    **A cor sai de `ui/tokens.py`** -- é a única vez em toda a spec do editor em que um hexadecimal
    é escrito, e ele é *derivado*: o exportador recebe o mapa `papel -> cor` pronto e não conhece
    uma cor sequer. O teste afirma que nenhum literal de cor aparece aqui.
    """

    extensao: str = ".html"
    nome: str = "HTML"
    suporta: frozenset[str] = frozenset(ATRIBUTOS)
    cores: Mapping[str, str] = field(default_factory=dict)
    """`nome de cor de autor -> hexadecimal`, e `faixa -> hexadecimal`. Vem de fora."""

    corpos: Mapping[str, str] = field(default_factory=dict)
    """`classe de degrau -> tamanho de fonte`, e ele **vem de fora pela mesma razão que a cor**.

    O documento guarda `corpo=+2`, que é um degrau; quanto isso mede é decisão de
    `ui/tipografia.corpo`, sobre a fonte do sistema de quem exporta. Um `font-size: 11pt` escrito
    aqui seria a regra 3 da SPEC_EDITOR quebrada no mesmo arquivo em que ela já é respeitada para a
    cor -- e o teste que varre este módulo atrás de literais de aparência pegaria os dois.

    Vazio é degradação e não defeito: sem o mapa, o HTML sai sem as regras de corpo, e o texto
    aparece no tamanho do navegador. É o que já acontece com `cores` quando ninguém as passa."""

    pasta_de_imagens: str = "diagramas"
    fontes: str = "'Segoe UI Symbol', 'DejaVu Sans', 'Noto Sans Symbols 2', sans-serif"

    def cabecalho(self, doc: DocumentoRico) -> str:
        titulo = _html.escape(_titulo_de(doc))
        estilo = "\n".join(
            f"    .{nome} {{ {propriedade}: {valor}; }}" for nome, propriedade, valor in self._regras()
        )
        return (
            "<!DOCTYPE html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{titulo}</title>\n<style>\n"
            f"    body {{ font-family: {self.fontes}; max-width: 42em; margin: 2em auto; }}\n"
            "    .diagrama { display: block; margin: 1em 0; }\n"
            # A figura centralizada precisa das duas: o `text-align` do `div` alinha o texto, e a
            # margem automática alinha o bloco da imagem (S-259).
            "    .alinhar-centro .diagrama { margin: 1em auto; }\n"
            "    .alinhar-direita .diagrama { margin: 1em 0 1em auto; }\n"
            f"{estilo}\n</style>\n</head>\n<body>\n"
            f"<!-- {titulo} -->\n"
            "<p class=\"aviso\">As figurinas de xadrez dependem de uma fonte com os glifos "
            "instalada na máquina que abrir este arquivo.</p>\n"
        )

    estilos_do_html: Mapping[str, tuple[str, str]] = field(
        default_factory=lambda: {
            "notacao": ("font-family", "'Consolas', 'DejaVu Sans Mono', monospace"),
            "legenda": ("font-style", "italic"),
        }
    )
    """Como cada estilo de parágrafo se escreve em CSS -- **e por que só dois estão aqui** (S-340).

    `_classes` emitia `estilo-titulo`, `estilo-prosa`, `estilo-notacao` e `estilo-legenda`, e a
    folha de estilo não tinha regra para nenhum deles: quatro classes que não faziam nada, num
    arquivo que existe para mostrar o que a aba mostrava.

    `titulo` sai como `<h2>` e nunca precisou de classe. `prosa` é o padrão do documento, e
    marcá-lo seria dizer "isto é normal" em toda corrida normal da folha. Sobram os dois que
    **são** diferentes e que o editor desenha diferente: a notação, em monoespaçada, e a legenda,
    em itálico -- `PAPEL_DO_ESTILO`, no `ui/texto_panel.py`, é a origem dos dois.

    Tamanho não entra: ele é degrau, mora em `corpos`, e vem de fora como a cor."""

    def regras_de_css(self) -> list[tuple[str, str, str]]:
        """As regras `(classe, propriedade, valor)` da folha de estilo, para quem monta outra folha.

        O EPUB da S-542 escreve o mesmo `<span class="cor-nota">` que `corrida` escreve, e a classe
        só quer dizer algo se a folha dele trouxer a mesma regra. Expor a lista -- e não copiá-la --
        é o que mantém um lugar só decidindo o que `cor-nota` significa.
        """
        return self._regras()

    def _regras(self) -> list[tuple[str, str, str]]:
        regras = [("fora-do-modelo", "border-bottom", "1px dotted currentColor")]
        regras.extend(
            (f"estilo-{estilo}", propriedade, valor)
            for estilo, (propriedade, valor) in sorted(self.estilos_do_html.items())
        )
        for nome, cor in sorted(self.cores.items()):
            propriedade = "background-color" if nome.startswith("realce-") else "color"
            regras.append((nome, propriedade, cor))
        for nome, tamanho in sorted(self.corpos.items()):
            regras.append((nome, "font-size", tamanho))
        for nome in ALINHAMENTOS_DO_HTML:
            regras.append((f"alinhar-{nome}", "text-align", ALINHAMENTOS_DO_HTML[nome]))
        return regras

    def corrida(self, c: Corrida) -> str:
        # **Escapa o que veio do OCR.** A S-211 mediu 96 caracteres espúrios em 13 páginas, e um
        # `<` não escapado engole o resto do arquivo no navegador.
        texto = _html.escape(c.texto).replace("\n", "<br>\n")
        atributos = c.atributos
        if atributos.negrito:
            texto = f"<strong>{texto}</strong>"
        if atributos.italico:
            texto = f"<em>{texto}</em>"
        if atributos.sublinhado:
            texto = f"<u>{texto}</u>"
        if atributos.tachado:
            # `<s>`, e não `<del>`: `del` é *texto removido de uma versão para a outra*, com
            # semântica de revisão de documento. Aqui o trecho continua no documento e está riscado
            # porque quem corrige o marcou assim -- que é exatamente o que o HTML5 define para `s`.
            texto = f"<s>{texto}</s>"
        classes = self._classes(c)
        if classes:
            texto = f'<span class="{" ".join(classes)}">{texto}</span>'
        if atributos.estilo == "titulo":
            texto = f"<h2>{texto}</h2>"
        return texto

    def _classes(self, c: Corrida) -> list[str]:
        classes: list[str] = []
        if c.atributos.cor:
            classes.append(f"cor-{c.atributos.cor}")
        if c.atributos.realce:
            classes.append(f"realce-{c.atributos.realce}")
        if c.faixa != documento.TRANQUILO:
            classes.append(f"faixa-{c.faixa}")
        if c.atributos.fora_do_modelo:
            classes.append("fora-do-modelo")
        # Só os estilos que têm regra: `titulo` é `<h2>` e `prosa` é o padrão (S-340).
        if c.atributos.estilo in self.estilos_do_html:
            classes.append(f"estilo-{c.atributos.estilo}")
        if c.atributos.corpo:
            classes.append(classe_de_corpo(c.atributos.corpo))
        return classes

    def diagrama(self, c: Corrida, recorte: Path | None) -> str:
        marca = _html.escape(c.texto)
        if recorte is None:
            return marca
        return f'<img class="diagrama" src="{self.pasta_de_imagens}/{recorte.name}" alt="{marca}">'

    def paragrafo(self, alinhamento: str, corpo: str) -> str:
        """O trecho alinhado num `<div>` (S-259). **Bloco, porque `text-align` não é de inline.**

        Um `<span style="text-align:center">` não faz nada num navegador -- a propriedade alinha o
        conteúdo de um bloco, e o span não é um. Envolver aqui, e não em `corrida`, é o que faz um
        parágrafo com uma palavra em negrito sair num `div` só em vez de um `div` por corrida: quem
        agrupa as corridas vizinhas de mesmo alinhamento é `exportar`.

        `.diagrama` é `display:block` desde a S-251, e `margin: 0 auto` é o que centraliza um bloco
        de largura fixa. Sem essa segunda regra a figura ficaria à esquerda dentro de um `div`
        centralizado, que é o defeito clássico de centralizar imagem em HTML.
        """
        if not alinhamento:
            return corpo
        return f'<div class="alinhar-{alinhamento}">{corpo}</div>\n'

    def rodape(self, doc: DocumentoRico) -> str:
        return "</body>\n</html>\n"


@dataclass(frozen=True)
class Rtf:
    """`.rtf`: **porque o Word abre.** Texto puro, biblioteca padrão, zero dependência nova.

    Duas armadilhas do formato, e as duas viram teste:

    - **RTF é ASCII com escapes.** Todo caractere fora do ASCII vira `\\uN?`, com o número
      **assinado** -- `♘` (U+2658) é `\\u9816?`, e acima de 32767 o número fica negativo. Uma página
      de xadrez é feita justamente desses caracteres, então o caso raro aqui é o caso comum;
    - **`{`, `}` e `\\` escapam.** Texto de OCR produz esses caracteres por engano (96 espúrios em
      13 páginas, S-211), e um `}` solto quebra o arquivo inteiro -- não só a linha.
    """

    extensao: str = ".rtf"
    nome: str = "RTF"
    suporta: frozenset[str] = frozenset(
        {"negrito", "italico", "sublinhado", "tachado", "estilo", "alinhamento", "corpo"}
    )
    meio_ponto_por_degrau: int = 2
    """Quantos meios-pontos vale um degrau de corpo. **Dois, porque o RTF conta em meios-pontos.**

    `\\fs20` é corpo 10, e um degrau de `rico` vale um ponto (`ui/tipografia.corpo`): o degrau `+2`
    é `\\fs24`. O número mora aqui e não no corpo do método porque é uma conversão de unidade do
    **formato**, e não uma escolha de tamanho -- a escolha continua sendo do documento."""

    corpo_base: int = 20
    """O `\\fs` do corpo do texto, em meios-pontos. É o `\\fs20` que o cabeçalho já declarava."""

    def cabecalho(self, doc: DocumentoRico) -> str:
        return "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Segoe UI;}}\\fs20\n"

    def corrida(self, c: Corrida) -> str:
        texto = escapar_rtf(c.texto)
        marcas = ""
        if c.atributos.negrito:
            marcas += "\\b "
        if c.atributos.italico:
            marcas += "\\i "
        if c.atributos.sublinhado:
            marcas += "\\ul "
        if c.atributos.tachado:
            marcas += "\\strike "
        if c.atributos.estilo == "titulo":
            marcas += "\\fs28 "
        if c.atributos.corpo:
            # **Depois do `\\fs28` do título, e é a ordem que decide.** No RTF a última declaração
            # do mesmo controle vence, e um título com `+1` tem de sair um degrau acima do título --
            # não do corpo comum. Somar sobre `corpo_base` daria o segundo comportamento.
            base = 28 if c.atributos.estilo == "titulo" else self.corpo_base
            marcas += f"\\fs{base + c.atributos.corpo * self.meio_ponto_por_degrau} "
        return f"{{{marcas}{texto}}}" if marcas else texto

    def paragrafo(self, alinhamento: str, corpo: str) -> str:
        """O grupo alinhado (S-259). `\\qc` e irmãos valem até o `\\par` que fecha o parágrafo.

        Grupo com chaves, e não o controle solto, porque o RTF é de estado: um `\\qc` sem grupo
        alinharia tudo o que vem depois dele até alguém escrever `\\ql` -- e o "alguém" seria o
        parágrafo seguinte, que não pediu nada.
        """
        controle = CONTROLE_DE_ALINHAMENTO_RTF.get(alinhamento, "")
        return f"{{{controle} {corpo}}}" if controle else corpo

    def diagrama(self, c: Corrida, recorte: Path | None) -> str:
        """A marca, e **não** a imagem. O `recorte` é ignorado de propósito (S-341).

        Embutir figura em RTF é o `pict` com o PNG em hexadecimal, e ela viajaria dentro do
        arquivo -- é possível e é outro item. O que este não podia continuar sendo é **mudo**:
        o `exportar` agora conta o recorte descartado e o relatório o diz, em vez de anunciar
        "nenhum diagrama sem recorte" sobre um arquivo em que nenhum diagrama tem imagem.
        """
        return escapar_rtf(c.texto)

    def rodape(self, doc: DocumentoRico) -> str:
        return "}\n"


def escapar_rtf(texto: str) -> str:
    """O texto como RTF: chaves e barra escapadas, e todo não-ASCII em `\\uN?` **assinado**."""
    saida: list[str] = []
    for caractere in texto:
        if caractere in "{}\\":
            saida.append("\\" + caractere)
        elif caractere == "\n":
            saida.append("\\par\n")
        elif ord(caractere) < 128:
            saida.append(caractere)
        else:
            ponto = ord(caractere)
            # O número do `\\uN` é **assinado de 16 bits**: acima de 32767 ele vira negativo, e um
            # leitor que receba 39672 no lugar de -25864 desenha outro glifo. Acima do BMP o par
            # substituto é o que o formato aceita.
            for unidade in _unidades_utf16(ponto):
                assinado = unidade - 65536 if unidade > 32767 else unidade
                saida.append(f"\\u{assinado}?")
    return "".join(saida)


def _unidades_utf16(ponto: int) -> list[int]:
    if ponto <= 0xFFFF:
        return [ponto]
    resto = ponto - 0x10000
    return [0xD800 + (resto >> 10), 0xDC00 + (resto & 0x3FF)]


def _cercado(texto: str, marca: str) -> str:
    """`texto` entre as marcas, **com o espaço das duas pontas por fora**.

    O Markdown não abre ênfase antes de um espaço nem a fecha depois de um: `** negrito **` sai
    literal na tela. A saída é aparar as pontas e devolvê-las por fora -- e são as **duas**, e não
    só a final. Cercar só a cauda engolia o espaço da esquerda, e duas corridas vizinhas saíam
    coladas (`um**negrito**`) no meio de uma frase. Aparecia em toda corrida que começa com espaço,
    que é o caso de todo trecho que não abre parágrafo."""
    return _cabeca(texto) + f"{marca}{texto.strip()}{marca}" + _cauda(texto)


def _cabeca(texto: str) -> str:
    """O espaço do começo, que a marcação não pode engolir."""
    return texto[: len(texto) - len(texto.lstrip())]


def _cauda(texto: str) -> str:
    """O espaço final que a marcação não pode engolir: `**negrito** ` e não `**negrito **`."""
    return texto[len(texto.rstrip()) :]


def _titulo_de(doc: DocumentoRico) -> str:
    pagina = doc.origem
    if pagina is None:
        return "Texto do ChessVisionOFF"
    origem = Path(pagina.documento or "texto").name
    return f"{origem} — folha {pagina.pagina + 1}"


FORMATOS: dict[str, type] = {
    ".txt": Texto,
    ".md": Markdown,
    ".html": Html,
    ".rtf": Rtf,
}
"""Extensão -> classe. É a lista que a aba oferece e a que o teste percorre."""


def formato_de(extensao: str, **argumentos: object) -> Formato:
    """O formato daquela extensão. Levanta `KeyError` para o que ninguém escreveu."""
    if extensao not in FORMATOS:
        raise KeyError(f"formato desconhecido: {extensao!r}. Os declarados estão em FORMATOS.")
    return FORMATOS[extensao](**argumentos)  # type: ignore[operator]


def suporte_por_formato() -> dict[str, dict[str, bool]]:
    """A tabela "atributo × formato", com `False` sendo resposta válida e explícita (S-250/S-256).

    É o que o inventário publica: **todo atributo aparece declarado em todo formato**, mesmo que a
    declaração seja "este formato não tem isto". Perda silenciosa é o que o item existe para
    impedir.
    """
    return {
        extensao: {atributo: atributo in classe().suporta for atributo in ATRIBUTOS}
        for extensao, classe in FORMATOS.items()
    }


def exportar(
    doc: DocumentoRico,
    formato: Formato,
    *,
    recortes: Mapping[int, Path] | None = None,
) -> Relatorio:
    """O documento naquele formato, com a conta do que se perdeu.

    `recortes` é `índice do diagrama -> arquivo de imagem`. Sem ele, os formatos que desenhariam a
    imagem escrevem só a marca -- e o relatório conta quantos ficaram sem recorte, que é a diferença
    entre "não havia diagrama" e "havia e não veio".
    """
    imagens = recortes or {}
    perdas = dict.fromkeys(ATRIBUTOS, 0)
    partes: list[tuple[str, str]] = []
    diagramas = 0
    sem_recorte = 0
    imagem_descartada = 0
    # **Formato que não declara pasta de imagens não carrega imagem** -- é o caso do `.txt` e do
    # `.rtf`. Sem isto, passar o recorte a eles zerava `sem_recorte` e o relatório dizia que
    # nenhum diagrama ficou sem imagem, num arquivo em que todos ficaram (S-341).
    desenha_imagem = bool(getattr(formato, "pasta_de_imagens", ""))
    aceita_valor = getattr(formato, "suporta_valor", None)
    for corrida in doc.corridas:
        for atributo in ATRIBUTOS:
            valor = getattr(corrida.atributos, atributo)
            if not valor:
                continue
            # `suporta` responde por atributo; `suporta_valor`, quando o formato o tem, responde
            # pelo **valor** -- o `.md` escreve o estilo `titulo` e não sabe escrever os outros
            # três, e declarar "estilo: sim" por causa de um deles é o que fazia o relatório
            # dizer "perdido: nada" sobre uma legenda que virou prosa (S-339).
            if atributo not in formato.suporta or (aceita_valor and not aceita_valor(atributo, valor)):
                perdas[atributo] += 1
        if corrida.e_diagrama:
            diagramas += 1
            recorte = imagens.get(corrida.bloco)
            if recorte is None:
                sem_recorte += 1
            elif not desenha_imagem:
                imagem_descartada += 1
            partes.append((corrida.atributos.alinhamento, formato.diagrama(corrida, recorte)))
            continue
        partes.append((corrida.atributos.alinhamento, formato.corrida(corrida)))
    montar = getattr(formato, "montar", None)
    corpo = _juntar(partes, formato)
    cabecalho, rodape = formato.cabecalho(doc), formato.rodape(doc)
    conteudo = montar(cabecalho, corpo, rodape) if montar else cabecalho + corpo + rodape
    return Relatorio(
        conteudo=conteudo,
        perdas={atributo: quantos for atributo, quantos in perdas.items() if quantos},
        avisos=_avisos(doc, formato, sem_recorte, imagem_descartada),
        diagramas=diagramas,
        sem_recorte=sem_recorte,
    )


def _juntar(partes: Sequence[tuple[str, str]], formato: Formato) -> str:
    """Junta os pedaços, agrupando os **vizinhos de mesmo alinhamento** (S-259).

    Um formato sem `paragrafo` recebe a concatenação de sempre, e é por isso que o `.txt` e o `.md`
    saem byte a byte iguais ao que saíam. Os que o têm recebem um grupo por corrida contígua de mesmo
    alinhamento -- e a contiguidade é o que importa: um parágrafo com uma palavra em negrito são três
    corridas, e três `<div>` no lugar de um seriam três parágrafos na tela de quem abre o arquivo.

    Alinhamento vazio atravessa sem grupo. É o parágrafo que ninguém alinhou, e envolvê-lo num
    `<div>` mudaria o HTML de toda folha exportada por um atributo que ninguém usou.
    """
    envolver = getattr(formato, "paragrafo", None)
    if envolver is None:
        return "".join(pedaco for _alinhamento, pedaco in partes)
    saida: list[str] = []
    grupo: list[str] = []
    atual = ""
    for alinhamento, pedaco in partes:
        if alinhamento != atual:
            if grupo:
                saida.append(envolver(atual, "".join(grupo)) if atual else "".join(grupo))
            grupo, atual = [], alinhamento
        grupo.append(pedaco)
    if grupo:
        saida.append(envolver(atual, "".join(grupo)) if atual else "".join(grupo))
    return "".join(saida)


def _avisos(doc: DocumentoRico, formato: Formato, sem_recorte: int, imagem_descartada: int = 0) -> tuple[str, ...]:
    """O que não é perda e quem recebe o arquivo precisa saber (S-254)."""
    avisos: list[str] = []
    fora = sum(1 for c in doc.corridas if c.atributos.fora_do_modelo)
    if fora:
        avisos.append(f"{fora} trecho(s) com símbolo que o modelo não lê (S-247)")
    sem_bloco = sum(1 for c in doc.corridas if not c.da_pagina and c.texto.strip())
    if sem_bloco:
        avisos.append(f"{sem_bloco} corrida(s) sem bloco de origem")
    if sem_recorte:
        avisos.append(f"{sem_recorte} diagrama(s) sem recorte no disco")
    if imagem_descartada:
        avisos.append(f"{imagem_descartada} diagrama(s) com recorte que o {formato.nome} não carrega")
    return tuple(avisos)


def escrever(caminho: Path, relatorio: Relatorio) -> Path:
    """Grava o conteúdo do relatório, **atomicamente** -- cancelar não deixa arquivo pela metade."""
    from ..atomic_io import atomic_write_text

    atomic_write_text(Path(caminho), relatorio.conteudo)
    return Path(caminho)


def texto_do_relatorio(caminho: Path, relatorio: Relatorio, tamanho: int | None = None) -> str:
    """As três seções que a S-254 pede: **escrito**, **perdido** e **avisado**."""
    kb = f", {tamanho // 1024} KB" if tamanho is not None else ""
    linhas = [f"escrito   {caminho}{kb}"]
    linhas.append(f"perdido   {relatorio.resumo() or 'nada'}")
    linhas.append(f"avisado   {'; '.join(relatorio.avisos) or 'nada'}")
    return "\n".join(linhas)


def _iter_corridas(doc: DocumentoRico) -> Iterable[Corrida]:  # pragma: no cover - conveniência
    return doc.corridas
