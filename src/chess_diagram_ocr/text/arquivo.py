"""O arquivo do editor: o que se grava para poder **voltar** (S-238).

**O que a aba gravava, e o que ela perdia.** O botão "Salvar .txt" escreve o texto corrido com um
cabeçalho de procedência, e é uma saída sem volta: sem faixa, sem diagrama, sem `PaginaLida`, e sem
"abrir". A docstring de `salvar` já dizia o que está em jogo -- *"se alguém corrigiu uma palavra, é a
correção que tem valor -- é a única coisa nesta aba que não sai de graça de uma releitura"*. É
exatamente essa coisa que o `.txt` não guarda inteira.

## Três decisões, e as três são sobre o que **não** entra no arquivo

**A `PaginaLida` vai junto, inteira.** Ela já serializa sem perda por critério de aceite da S-211, e
é o que permite reabrir e ainda ter bbox, confiança e diagrama.

**O diagrama não é embutido.** O que se guarda é o bbox e o índice; a miniatura se refaz do PDF
original, pelo mesmo caminho de `_miniatura`. Embutir PNG faria um arquivo de texto pesar megabytes e
duplicaria o que já está no livro -- e o livro é o dado, o recorte é uma vista dele.

**Não se grava data nem motor.** Os dois estavam no desenho da spec e saíram na implementação: a
procedência de cada bloco já diz de que motor ele veio, com granularidade melhor que "a página foi
lida com glifo", e a data de leitura não tem consumidor -- a do arquivo é do sistema de arquivos.
Campo sem quem o leia é o item de menu sem comando da S-161.

## A versão é do arquivo, e não do documento

`text/rico.py` não tem número de versão de propósito: ele é um objeto em memória, e quem envelhece é
o arquivo. Misturar os dois faria aquele módulo ter opinião sobre compatibilidade -- e as duas coisas
mudam em ritmos diferentes.

Um arquivo de versão **maior** é recusado com mensagem em pt-BR, como `ui/state._migrate` já faz com
o estado da janela: abrir um documento que esta versão não entende inteiro e gravar por cima seria
apagar em silêncio o que a versão nova sabia.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from .rico import DocumentoRico

VERSAO = 1
"""A versão do formato. Sobe quando um arquivo gravado hoje deixar de ser legível como hoje.

**Acrescentar campo não sobe a versão**, e é o que `Atributos.para_json` compra ao omitir o que é
padrão: um arquivo da versão 1 continua válido depois de a S-242 acrescentar cor."""

EXTENSAO = ".cvtxt"
NOME_DO_FORMATO = "Texto do ChessVisionOFF"
"""Como o formato se chama no diálogo de arquivo. Fica aqui, e não no widget, pela regra de sempre."""


class ArquivoInvalido(ValueError):
    """O arquivo não é um documento do editor, ou está corrompido."""


class VersaoFutura(ArquivoInvalido):
    """O arquivo foi gravado por uma versão mais nova do programa."""


def para_json(doc: DocumentoRico) -> dict[str, Any]:
    """O documento como o arquivo o guarda: a versão, e ele."""
    return {"versao": VERSAO, "documento": doc.para_json()}


def de_json(dados: Any) -> DocumentoRico:
    """O documento de volta, recusando o que não se sabe ler.

    A recusa é em pt-BR e nomeia os dois números, porque quem a lê é quem abriu o arquivo -- e a
    resposta útil é "atualize o programa", que só se deduz vendo as duas versões lado a lado.
    """
    if not isinstance(dados, dict):
        raise ArquivoInvalido(f"esperava um objeto no topo do arquivo, veio {type(dados).__name__}")
    bruto = dados.get("versao")
    try:
        versao = int(str(bruto))
    except ValueError:
        raise ArquivoInvalido(f"o arquivo não diz de que versão é (veio {bruto!r})") from None
    if versao > VERSAO:
        raise VersaoFutura(
            f"arquivo gravado por uma versão mais nova do ChessVisionOFF "
            f"(versão {versao}; esta lê até a {VERSAO}). Atualize o programa para abri-lo."
        )
    if "documento" not in dados:
        raise ArquivoInvalido("o arquivo não traz documento nenhum")
    return DocumentoRico.de_json(dados["documento"])


def gravar(caminho: Path, doc: DocumentoRico) -> Path:
    """Grava o documento e devolve o caminho. **Atômico**, e a razão é o que está em jogo.

    Uma sessão de correção é a coisa mais cara desta aba, e uma gravação interrompida no meio --
    disco cheio, antivírus, a máquina desligando -- deixaria o arquivo truncado **por cima** do
    anterior. É a mesma regra de `labels.csv` desde a S-111, pelo mesmo motivo: o que está no disco é
    trabalho humano.
    """
    caminho = Path(caminho)
    atomic_write_text(caminho, json.dumps(para_json(doc), ensure_ascii=False, indent=2) + "\n")
    return caminho


def carregar(caminho: Path) -> DocumentoRico:
    """Lê o documento do disco. Levanta `ArquivoInvalido` para o que não é documento do editor."""
    caminho = Path(caminho)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise ArquivoInvalido(f"{caminho.name} não é um arquivo JSON válido: {erro}") from erro
    return de_json(dados)


def sugestao_de_nome(doc: DocumentoRico, *, extensao: str = EXTENSAO) -> str:
    """Como o arquivo se chama por padrão no diálogo: `livro_folha58.cvtxt`.

    Mora aqui, e não no painel, pela regra da Fase 6 -- e porque o `.txt` e o `.cvtxt` passam a
    derivar o nome do **mesmo** lugar, em vez de repetirem a mesma linha com a extensão trocada.
    """
    pagina = doc.origem
    if pagina is None:
        return f"texto{extensao}"
    origem = Path(pagina.documento or "texto").stem or "texto"
    return f"{origem}_folha{pagina.pagina + 1}{extensao}"


def pdf_de(doc: DocumentoRico) -> Path | None:
    """O PDF de onde a página veio, ou `None` se o documento não guarda origem.

    **Não pergunta se ele existe**, e é de propósito: quem abre o arquivo precisa distinguir "este
    documento não tem livro" de "o livro mudou de lugar", e as duas respostas são diferentes na tela.
    """
    pagina = doc.origem
    if pagina is None or not pagina.documento:
        return None
    return Path(pagina.documento)


__all__ = [
    "EXTENSAO",
    "NOME_DO_FORMATO",
    "VERSAO",
    "ArquivoInvalido",
    "DocumentoRico",
    "VersaoFutura",
    "carregar",
    "de_json",
    "gravar",
    "para_json",
    "pdf_de",
    "sugestao_de_nome",
]
