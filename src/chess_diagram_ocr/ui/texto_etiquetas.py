"""A tradução entre o documento e as etiquetas do `tk.Text` -- **nos dois sentidos** (S-238).

**Por que os dois sentidos moram no mesmo arquivo.** Desenhar é `Corrida` -> etiquetas; salvar é
etiquetas -> `Corrida`. São a mesma tabela lida ao contrário, e separá-las em dois módulos daria
duas tabelas que divergem no primeiro atributo novo -- o itálico da S-236 desenhado e não gravado, ou
gravado e não desenhado. Aqui a ida e a volta se olham, e `test_a_ida_e_volta_e_identidade` as trava.

## O widget é o estado vivo, e o documento é a fronteira do arquivo

A S-235 pôs o documento fora do `tkinter`, e o passo seguinte tinha duas saídas: manter um segundo
buffer sincronizado a cada tecla, ou **guardar tudo no próprio widget** e reconstruir o documento na
hora de gravar. É a segunda, e a razão é do Tk:

> *"If tagList is not present, the new text will receive any tags that are present on **both** the
> character before and the character after the insertion point."*

Isso já é a regra que se quer. Digitar **dentro** de um bloco herda `bloco:3` -- e a correção fica
atada ao bloco que ela corrige, que é o que a S-239 precisa entregar à fila da S-212. Digitar na
emenda entre dois blocos não herda nenhum dos dois, e vira texto sem origem, que é o certo. Um
segundo buffer teria de reimplementar essa regra e acertá-la de novo em cada caso.

## O que o desenho acrescenta, a leitura tira

A miniatura do diagrama entra com uma quebra de linha para a marca cair embaixo dela, e essa quebra
**não é do documento** -- é do desenho. Sem marcá-la, ela voltaria como texto no arquivo, e o desenho
seguinte acrescentaria outra: uma quebra a mais a cada salvar-e-reabrir, para sempre. A etiqueta
`DESENHO` é o que a leitura descarta, e ela é a razão de este módulo existir em vez de um
`dump` cru.

## Nada de `tkinter` aqui

O `dump` do Tk devolve uma lista de trincas de `str`, e transformá-la em documento é decisão pura --
afirmável sem abrir janela, como `ui/tokens.py` e `ui/comandos.py`. Quem chama `Text.dump` é o painel.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import fields
from typing import Any

from ..text import documento, rico

logger = logging.getLogger(__name__)

MARCA = "marca"
"""A etiqueta de `[Diagrama N]`. Já existia na aba desde a S-211, e agora também diz o tipo."""

SEPARADOR = "separador"
"""A linha em branco entre dois blocos.

Ela é indistinguível de duas quebras digitadas à mão -- e por isso precisa de etiqueta. Sem ela o
separador voltaria do widget como texto comum, e o documento reaberto não seria igual ao salvo."""

DESENHO = "desenho"
"""O que o desenho acrescenta e o documento não tem. Ver "O que o desenho acrescenta"."""

PREFIXO_DE_BLOCO = "bloco:"
PREFIXO_DE_PROCEDENCIA = "proc:"
"""Etiqueta com valor, no único formato que o Tk aceita: nome de etiqueta é string.

`bloco:3` e `proc:glifo` não são desenháveis -- nenhuma delas tem `tag_configure` -- e é de
propósito: são **dado carregado pelo widget**, não aparência. É o que permite o widget ser o estado
vivo sem um segundo buffer ao lado."""

ETIQUETA_DO_ATRIBUTO: dict[str, str] = {
    "negrito": "negrito",
    "italico": "italico",
    "sublinhado": "sublinhado",
    "fora_do_modelo": "fora_do_modelo",
}
"""Atributo **booleano** de `rico.Atributos` -> etiqueta que o desenha.

Os quatro que existem, e agora nenhum fica de fora: `sublinhado` entrou com a S-241 e
`fora_do_modelo` com a S-247. Os que têm **valor** -- `cor`, `realce`, `estilo` -- não cabem aqui,
porque etiqueta é string e o valor vai no nome: ver `ATRIBUTO_COM_VALOR`."""


SEM_ETIQUETA: tuple[str, ...] = ()
"""Booleanos de `Atributos` que existem no documento e a aba **ainda não desenha**.

Vazio desde a S-241/S-247, e é o estado certo. A tupla fica: `ETIQUETA_DO_ATRIBUTO` mais esta têm
de cobrir todos os booleanos de `rico.Atributos`, e o teste falha quando não cobrem -- é o que faz
um atributo novo exigir uma decisão (desenha-se, ou declara-se que ainda não) em vez de entrar em
silêncio e sumir na gravação."""


ATRIBUTO_COM_VALOR: dict[str, str] = {
    "cor": "cor:",
    "realce": "realce:",
    "estilo": "estilo:",
}
"""Atributo de valor -> prefixo da etiqueta que o carrega (S-242, S-249).

`cor:destaque` e `estilo:titulo` são o mesmo desenho de `bloco:3` e `proc:glifo`: nome de etiqueta
no Tk é string, e um atributo que não é sim-ou-não precisa carregar o valor no próprio nome. A
diferença é que estes **são** desenháveis -- quem os configura é `ui/texto_panel._pintar_faixas`,
com a cor vinda de `ui/texto_cores.py` e o corpo de `ui/tipografia.py`."""


def _booleanos_de_atributo() -> tuple[str, ...]:
    """Os campos booleanos de `rico.Atributos`, em ordem de declaração.

    Derivado e não recopiado: é o que faz `test_todo_booleano_de_atributo_tem_etiqueta` acusar o
    dia em que a S-236 acrescentar `italico` e ninguém lembrar de mapeá-lo aqui."""
    return tuple(campo.name for campo in fields(rico.Atributos) if campo.type in ("bool", bool))


def etiquetas_de(corrida: rico.Corrida) -> tuple[str, ...]:
    """As etiquetas do `tk.Text` que desenham e descrevem esta corrida.

    A ordem é fixa -- tipo, faixa, atributos, bloco, procedência -- porque ela é comparada em teste,
    e porque a última etiqueta é a que vence no Tk quando duas pintam a mesma coisa.

    A marca do diagrama **não leva faixa**: ela é referência ao diagrama, e não texto lido do livro,
    então a régua de confiança não se aplica a ela.
    """
    etiquetas: list[str] = []
    if corrida.tipo == rico.DIAGRAMA:
        etiquetas.append(MARCA)
    elif corrida.tipo == rico.SEPARADOR:
        etiquetas.append(SEPARADOR)
    else:
        etiquetas.append(corrida.faixa)
        for atributo, etiqueta in ETIQUETA_DO_ATRIBUTO.items():
            if getattr(corrida.atributos, atributo, False):
                etiquetas.append(etiqueta)
        for atributo, prefixo in ATRIBUTO_COM_VALOR.items():
            valor = getattr(corrida.atributos, atributo, "")
            if valor:
                etiquetas.append(f"{prefixo}{valor}")
    if corrida.bloco != rico.SEM_BLOCO:
        etiquetas.append(f"{PREFIXO_DE_BLOCO}{corrida.bloco}")
    if corrida.procedencia is not None:
        etiquetas.append(f"{PREFIXO_DE_PROCEDENCIA}{corrida.procedencia}")
    return tuple(etiquetas)


def corrida_de(texto: str, etiquetas: Iterable[str]) -> rico.Corrida:
    """A corrida que aquelas etiquetas descrevem. O caminho de volta de `etiquetas_de`.

    **Perdoa o que não entende, e não levanta.** Etiqueta desconhecida, `bloco:` que não é número,
    `proc:` fora das quatro -- tudo isso vira o valor padrão e um registro no log. O motivo é duro:
    esta função roda no caminho de *salvar*, e uma etiqueta estragada que impedisse a gravação
    trocaria um defeito cosmético por perda do trabalho de quem estava corrigindo a página.
    """
    presentes = set(etiquetas)
    tipo = rico.DIAGRAMA if MARCA in presentes else rico.SEPARADOR if SEPARADOR in presentes else rico.TEXTO
    faixas = [f for f in documento.FAIXAS if f in presentes]
    ligados: dict[str, Any] = {
        atributo: True
        for atributo, etiqueta in ETIQUETA_DO_ATRIBUTO.items()
        if etiqueta in presentes
    }
    ligados.update(_com_valor(presentes))
    atributos = _atributos(ligados)
    return rico.Corrida(
        texto=texto,
        atributos=atributos if tipo == rico.TEXTO else rico.PADRAO,
        faixa=faixas[0] if tipo == rico.TEXTO and faixas else documento.TRANQUILO,
        bloco=_bloco_de(presentes),
        procedencia=_procedencia_de(presentes),
        tipo=tipo,
    )


def _com_valor(etiquetas: set[str]) -> dict[str, Any]:
    """Os atributos de valor que aquelas etiquetas trazem: `cor:destaque` -> `{"cor": "destaque"}`.

    Etiqueta repetida do mesmo atributo -- duas cores no mesmo trecho, que o Tk permite -- é
    resolvida pela **ordem alfabética**, para a volta ser determinística. Na prática ela não
    acontece: quem aplica cor tira a anterior no mesmo gesto (`ui/texto_panel.pintar`).
    """
    achados: dict[str, Any] = {}
    for atributo, prefixo in ATRIBUTO_COM_VALOR.items():
        valores = sorted(e[len(prefixo) :] for e in etiquetas if e.startswith(prefixo))
        if valores:
            achados[atributo] = valores[0]
    return achados


def _atributos(ligados: dict[str, Any]) -> rico.Atributos:
    """`Atributos` com o que veio das etiquetas, **perdoando o valor que o domínio recusa**.

    `rico.Atributos` levanta para cor ou estilo que ninguém declarou, e aqui isso não pode
    acontecer: esta função roda no caminho de *salvar*. Uma etiqueta de uma versão mais nova --
    ou estragada -- viraria perda do trabalho de quem estava corrigindo a página. Cai no padrão
    daquele campo e registra no log, como o resto do módulo.
    """
    try:
        return rico.Atributos(**ligados)
    except KeyError as erro:
        logger.debug("Atributo de valor recusado pelo domínio (%s): o trecho fica sem ele.", erro)
        for atributo in ATRIBUTO_COM_VALOR:
            ligados.pop(atributo, None)
        return rico.Atributos(**ligados)


def _bloco_de(etiquetas: set[str]) -> int:
    for etiqueta in etiquetas:
        if not etiqueta.startswith(PREFIXO_DE_BLOCO):
            continue
        try:
            return int(etiqueta[len(PREFIXO_DE_BLOCO) :])
        except ValueError:
            logger.debug("Etiqueta de bloco ilegível (%s): a corrida fica sem origem.", etiqueta)
    return rico.SEM_BLOCO


def _procedencia_de(etiquetas: set[str]):  # noqa: ANN202 - Procedencia | None
    for etiqueta in etiquetas:
        if not etiqueta.startswith(PREFIXO_DE_PROCEDENCIA):
            continue
        nome = etiqueta[len(PREFIXO_DE_PROCEDENCIA) :]
        if nome in rico.PROCEDENCIAS:
            return nome
        logger.debug("Procedência desconhecida na etiqueta (%s): a corrida fica sem ela.", etiqueta)
    return None


def deslocamento(itens: Sequence[Sequence[str]]) -> int:
    """Quantos caracteres **do documento** há naquele despejo (S-241).

    É a metade que falta para o editor: o painel converte um índice do Tk (`"sel.first"`) em
    deslocamento de caractere, e é com deslocamento que as funções puras de `text/rico.py` falam.

    A conta não é `len(texto)` do widget, e é essa a razão de a função existir: a miniatura do
    diagrama conta **um** caractere para o Tk e **zero** para o documento, e a quebra de linha que
    o desenho acrescenta embaixo dela não é do documento tampouco. Somar os dois daria um
    deslocamento adiantado, e o negrito cairia uma letra à frente a cada diagrama da página.
    """
    abertas: set[str] = set()
    total = 0
    for item in itens:
        chave, valor = str(item[0]), str(item[1])
        if chave == "tagon":
            abertas.add(valor)
        elif chave == "tagoff":
            abertas.discard(valor)
        elif chave == "text" and DESENHO not in abertas:
            total += len(valor)
    return total


def de_despejo(itens: Sequence[Sequence[str]], origem=None) -> rico.DocumentoRico:  # noqa: ANN001
    """O documento reconstruído do `Text.dump` -- que é o que a pessoa realmente tem na tela.

    O `dump` devolve trincas `(chave, valor, índice)` em ordem: `tagon`, `tagoff`, `text`, `image`,
    `mark`. O que se faz com cada uma:

        tagon / tagoff   abrem e fecham etiquetas; o conjunto aberto descreve o texto seguinte
        text             vira corrida, com o conjunto aberto naquele ponto
        image            a miniatura -- ignorada, porque ela se refaz do PDF (S-238)
        mark             `insert` e `current`, que são a posição do cursor e não conteúdo

    **A imagem é ignorada e a marca não**, e é a assimetria que faz o diagrama sobreviver: a
    miniatura morre com o widget, `[Diagrama N]` é texto e volta inteiro.

    `origem` é a `PaginaLida`, que o widget não tem como devolver -- quem a guarda é o painel.
    """
    abertas: set[str] = set()
    corridas: list[rico.Corrida] = []
    for item in itens:
        chave, valor = str(item[0]), str(item[1])
        if chave == "tagon":
            abertas.add(valor)
        elif chave == "tagoff":
            abertas.discard(valor)
        elif chave == "text":
            if DESENHO in abertas:
                continue
            corridas.append(corrida_de(valor, abertas))
    return rico.DocumentoRico(corridas=rico.fundir(corridas), origem=origem)


__all__ = [
    "ATRIBUTO_COM_VALOR",
    "DESENHO",
    "ETIQUETA_DO_ATRIBUTO",
    "MARCA",
    "PREFIXO_DE_BLOCO",
    "PREFIXO_DE_PROCEDENCIA",
    "SEM_ETIQUETA",
    "SEPARADOR",
    "corrida_de",
    "de_despejo",
    "deslocamento",
    "etiquetas_de",
]
