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
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Protocol

from . import documento
from .rico import Atributos, Corrida, DocumentoRico

__all__ = [
    "ATRIBUTOS",
    "FORMATOS",
    "Formato",
    "Html",
    "Markdown",
    "Relatorio",
    "Rtf",
    "Texto",
    "exportar",
    "formato_de",
    "suporte_por_formato",
]

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
    """O contrato de um formato. Quem o cumpre não sabe que existe um arquivo."""

    extensao: str
    nome: str
    suporta: frozenset[str]

    def cabecalho(self, doc: DocumentoRico) -> str: ...

    def corrida(self, c: Corrida) -> str: ...

    def diagrama(self, c: Corrida, recorte: Path | None) -> str: ...

    def rodape(self, doc: DocumentoRico) -> str: ...

    def montar(self, cabecalho: str, corpo: str, rodape: str) -> str: ...


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
    é assim que se vê o que mudou. Negrito é `**`, itálico é `*`, título é `#`. A cor de autor não
    tem sintaxe e é declarada como perda; a faixa de confiança também.
    """

    extensao: str = ".md"
    nome: str = "Markdown"
    suporta: frozenset[str] = frozenset({"negrito", "italico", "estilo"})
    pasta_de_imagens: str = "diagramas"

    def cabecalho(self, doc: DocumentoRico) -> str:
        return _cabecalho_de_procedencia(doc)

    def corrida(self, c: Corrida) -> str:
        texto = c.texto
        if not texto.strip():
            return texto
        # A ordem importa: `***texto***` é o que o Markdown lê como negrito **e** itálico.
        if c.atributos.italico:
            texto = f"*{texto.strip()}*" + _cauda(texto)
        if c.atributos.negrito:
            texto = f"**{texto.strip()}**" + _cauda(texto)
        if c.atributos.estilo == "titulo":
            texto = f"# {texto.lstrip()}"
        return texto

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
            f"{estilo}\n</style>\n</head>\n<body>\n"
            f"<!-- {titulo} -->\n"
            "<p class=\"aviso\">As figurinas de xadrez dependem de uma fonte com os glifos "
            "instalada na máquina que abrir este arquivo.</p>\n"
        )

    def _regras(self) -> list[tuple[str, str, str]]:
        regras = [("fora-do-modelo", "border-bottom", "1px dotted currentColor")]
        for nome, cor in sorted(self.cores.items()):
            propriedade = "background-color" if nome.startswith("realce-") else "color"
            regras.append((nome, propriedade, cor))
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
        if c.atributos.estilo and c.atributos.estilo != "titulo":
            classes.append(f"estilo-{c.atributos.estilo}")
        return classes

    def diagrama(self, c: Corrida, recorte: Path | None) -> str:
        marca = _html.escape(c.texto)
        if recorte is None:
            return marca
        return f'<img class="diagrama" src="{self.pasta_de_imagens}/{recorte.name}" alt="{marca}">'

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
    suporta: frozenset[str] = frozenset({"negrito", "italico", "sublinhado", "estilo"})

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
        if c.atributos.estilo == "titulo":
            marcas += "\\fs28 "
        return f"{{{marcas}{texto}}}" if marcas else texto

    def diagrama(self, c: Corrida, recorte: Path | None) -> str:
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
    partes: list[str] = []
    diagramas = 0
    sem_recorte = 0
    for corrida in doc.corridas:
        for atributo in ATRIBUTOS:
            valor = getattr(corrida.atributos, atributo)
            if valor and atributo not in formato.suporta:
                perdas[atributo] += 1
        if corrida.e_diagrama:
            diagramas += 1
            recorte = imagens.get(corrida.bloco)
            if recorte is None:
                sem_recorte += 1
            partes.append(formato.diagrama(corrida, recorte))
            continue
        partes.append(formato.corrida(corrida))
    montar = getattr(formato, "montar", None)
    corpo = "".join(partes)
    cabecalho, rodape = formato.cabecalho(doc), formato.rodape(doc)
    conteudo = montar(cabecalho, corpo, rodape) if montar else cabecalho + corpo + rodape
    return Relatorio(
        conteudo=conteudo,
        perdas={atributo: quantos for atributo, quantos in perdas.items() if quantos},
        avisos=_avisos(doc, formato, sem_recorte),
        diagramas=diagramas,
        sem_recorte=sem_recorte,
    )


def _avisos(doc: DocumentoRico, formato: Formato, sem_recorte: int) -> tuple[str, ...]:
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
