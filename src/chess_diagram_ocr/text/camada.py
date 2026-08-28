"""O que a **camada de texto do PDF** declara sobre a forma da letra, e como isso vira linha.

**Este módulo é a máquina, e não a régua.** Ele não sabe o que é negrito nem o que é itálico: sabe
perguntar à página quais retângulos têm um estilo, medir quanto de cada linha eles cobrem, e
devolver `True`/`False`/`None` por linha. Quem diz *o que* procurar é `text/negrito.py` (peso) e
`text/italico.py` (pendor), cada um com o nome de fonte e o bit que o denunciam.

**Por que ele nasceu separado.** A máquina foi escrita para o negrito na S-237 -- spans → cobertura
→ `marcar` --, e a S-236 registrou por escrito que o itálico da camada precisava dela: *"a máquina
para isso já existe em `text/negrito.py`, e generalizá-la é o que falta"*. Copiá-la para o outro
módulo seria a segunda declaração da mesma regra geométrica, que é o defeito que este projeto passa
o tempo tirando de si. `text/negrito.py` continua exportando os mesmos nomes, agora delegando aqui.

## As três decisões que a máquina carrega, e valem para os dois estilos

**`None` é "não se sabe", e é diferente de `False`.** Um livro cuja camada não registra estilo
nenhum não pode declarar que nada ali é negrito ou itálico -- ele não sabe. Quem separa os dois é o
**documento**, e não a página: uma página de prosa sem itálico num livro que o registra é um `False`
legítimo.

**A unidade era a linha, e a decisão era por maioria da largura.** A `PaginaLida` não tinha unidade
menor que a `LinhaLida`, então uma linha meio em itálico era decidida pela fração dela que o estilo
cobre. Onde o estilo é a linha inteira -- título, citação, variante -- o resultado é exato; onde ele
é uma palavra no meio da prosa, era grosso. Continua valendo para o **campo de linha**, e deixou de
ser a última palavra: ver "A régua desceu ao caractere" abaixo.

**Os trechos cobertos são unidos antes de somar.** Dois spans que se sobrepõem não contam duas
vezes; sem isso uma linha poderia "cobrir" mais que 100% de si mesma.

## A régua desceu ao caractere, e o número é o motivo (S-429)

A maioria da largura erra de duas maneiras opostas, e as duas aparecem na mesma folha: a palavra em
negrito no meio da prosa **some** (cobre menos de 60% e a linha sai normal), e a linha que é quase
toda negrito **incha** (as três palavras em pé no fim dela saem em negrito). Medido em 2026-08-28
sobre 8 folhas de cada um dos 45 PDFs do acervo -- 18.207 linhas de camada, das quais 969 têm peso
e 407 têm pendor:

    estilo     linhas com ele   misturam dentro de si   somem (< 60%)   incham (>= 60%)
    negrito           969            428  (44,2%)         281 (29,0%)      147 (15,2%)
    itálico           407            279  (68,6%)         241 (59,2%)       38  (9,3%)

**Quase metade do negrito e mais de dois terços do itálico do acervo caem numa linha misturada** --
não é o caso raro que a limitação declarada sugeria, é o caso comum. E a informação para acertar
sempre esteve na mão: o span da camada tem o texto **e** o bbox, e a linha é a costura deles.

`linhas_com` devolve a linha da camada com **um bool por caractere**, e `trechos` casa esse texto
com o que o leitor leu -- por `difflib`, e não por posição, porque o motor de glifo lê a mesma linha
com outros caracteres. O que sai são os intervalos `(início, fim)` do estilo dentro do texto da
linha, e é o que a `LinhaLida` passou a carregar em `negrito_em` e `italico_em`.

**Nada disto substitui o campo de linha.** `marcar` continua respondendo o que respondia, e é ele
que `BlocoDeTexto.de_linhas` e `paragrafos.cortar` leem; os intervalos são o detalhe que a régua de
maioria não tem como ter, e quem não os tem -- página sem camada, página girada, layer que discorda
do que foi lido -- volta a ser desenhado pela linha, exatamente como antes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

__all__ = [
    "CASAMENTO_MINIMO",
    "COBERTURA_MINIMA",
    "PAGINAS_DE_AMOSTRA",
    "LinhaDeCamada",
    "Retangulo",
    "Trecho",
    "cobertura",
    "documento_registra",
    "linhas_com",
    "marcar",
    "remapear",
    "spans_com",
    "trechos",
]

Retangulo = tuple[float, float, float, float]

Trecho = tuple[int, int]
"""Um intervalo `[início, fim)` de caracteres dentro do texto de uma linha."""

COBERTURA_MINIMA = 0.60
"""Fração da largura da linha que precisa ter o estilo para a linha inteira contar como tal.

Maioria, e não qualquer sobreposição: uma linha de prosa com **um** lance em negrito no meio não é
uma linha em negrito, e marcá-la assim seria pior que não marcar."""

PAGINAS_DE_AMOSTRA = 6
"""Quantas páginas se olham para decidir se o **documento** registra aquele estilo.

A pergunta não é da página -- ver "As três decisões" no cabeçalho."""

CASAMENTO_MINIMO = 0.5
"""Quanto do texto lido precisa casar com o da camada para os intervalos valerem.

**A guarda existe porque as duas leituras podem ser de textos diferentes.** O motor de glifo lê a
imagem, e a camada daquela mesma folha pode ser o palpite de *outro* OCR -- o
`Gaprindashvili ... _OCR_Aprimorar_Aprimorar` do acervo é exatamente isso. Quando as duas mal se
parecem, `difflib` ainda acha coincidências curtas, e marcá-las emboldeceria pedaços de palavra ao
acaso. Abaixo do meio, os intervalos saem vazios e quem desenha volta ao campo de linha, que é o
comportamento de antes -- degradar para o que já existia é melhor que pintar palpite."""


def spans_com(page: object, e_do_estilo: Callable[[dict], bool]) -> list[Retangulo]:
    """Os retângulos daquele estilo na página, em **pontos do PDF**. Vazio quando não há nenhum.

    Pontos e não pixels, como todo bbox da `PaginaLida`: quem converte é quem tem o DPI.
    """
    try:
        dicionario = page.get_text("dict")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - página sem camada nenhuma
        return []
    saida: list[Retangulo] = []
    for bloco in dicionario.get("blocks", []):
        for linha in bloco.get("lines", []):
            for span in linha.get("spans", []):
                if e_do_estilo(span):
                    x0, y0, x1, y1 = span["bbox"]
                    saida.append((float(x0), float(y0), float(x1), float(y1)))
    return saida


@dataclass(frozen=True)
class LinhaDeCamada:
    """Uma linha da camada de texto, com **um bool por caractere** do que ela escreve (S-429).

    **Por caractere, e não por span.** O span é a unidade do PDF, e ela não é a unidade de ninguém
    mais: um `1.e4 **Nf3** e5` pode vir em três spans ou em sete, conforme o gerador, e casar
    "span" com "palavra do texto lido" seria refazer a costura que a própria camada já fez. Um
    bool por caractere torna o casamento com o texto lido uma questão de índice, e `difflib`
    resolve índice.
    """

    bbox: Retangulo
    """A caixa da linha, em **pontos do PDF** -- a mesma unidade de `spans_com`."""

    texto: str
    """O que a linha escreve, com os spans concatenados e **sem normalizar espaço**.

    Sem normalizar porque as `marcas` são por caractere: colapsar espaço aqui deslocaria todas as
    marcas depois do primeiro espaço duplo. Quem normaliza é o casamento, que é tolerante."""

    marcas: tuple[bool, ...]
    """Um por caractere de `texto`: aquele caractere está no estilo procurado?"""


def linhas_com(page: object, e_do_estilo: Callable[[dict], bool]) -> list[LinhaDeCamada]:
    """As linhas da camada com a marca de estilo caractere a caractere. Ver `LinhaDeCamada`.

    É o irmão fino de `spans_com`: aquele devolve retângulos e serve à régua de maioria, este
    devolve texto e serve aos intervalos. Os dois leem o mesmo `get_text("dict")`, e por isso a
    mesma página responde a mesma coisa às duas perguntas.
    """
    try:
        dicionario = page.get_text("dict")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - página sem camada nenhuma
        return []
    saida: list[LinhaDeCamada] = []
    for bloco in dicionario.get("blocks", []):
        for linha in bloco.get("lines", []):
            partes: list[str] = []
            marcas: list[bool] = []
            for span in linha.get("spans", []):
                texto = str(span.get("text", ""))
                if not texto:
                    continue
                partes.append(texto)
                marcas.extend([e_do_estilo(span)] * len(texto))
            if not partes:
                continue
            x0, y0, x1, y1 = linha["bbox"]
            saida.append(
                LinhaDeCamada(
                    bbox=(float(x0), float(y0), float(x1), float(y1)),
                    texto="".join(partes),
                    marcas=tuple(marcas),
                )
            )
    return saida


def _sobrepoe(a: Retangulo, b: Retangulo) -> bool:
    """As duas caixas descrevem a mesma faixa de texto?

    Metade da altura da **menor** na vertical, e qualquer toque na horizontal. A altura decide
    porque é ela que separa uma linha da de baixo; a largura não, porque a linha lida pelo motor de
    glifo pode ser mais curta que a da camada (uma palavra que a binarização comeu) sem deixar de
    ser a mesma linha.
    """
    alto = min(a[3] - a[1], b[3] - b[1])
    if alto <= 0:
        return False
    return (min(a[3], b[3]) - max(a[1], b[1])) >= alto / 2 and min(a[2], b[2]) > max(a[0], b[0])


def trechos(
    bbox: Retangulo,
    texto: str,
    linhas: Sequence[LinhaDeCamada],
    *,
    minimo: float = CASAMENTO_MINIMO,
) -> tuple[Trecho, ...]:
    """Onde, dentro de `texto`, está o estilo que a camada declara. Vazio quando não dá para dizer.

    **A costura é por texto, e a seleção é por geometria.** A geometria acha quais linhas da camada
    são esta linha; o `difflib` diz qual caractere lido corresponde a qual caractere da camada. Os
    dois são necessários: só geometria daria a fração da largura, que é a régua grossa que este item
    existe para superar; só texto casaria a linha com outra igual em outro canto da folha.

    **`difflib` e não posição.** No caminho da camada os dois textos são o mesmo e o casamento é
    trivial; no caminho do glifo o motor lê `smdy` onde está escrito `study`, e um casamento por
    índice deslocaria a marcação da linha inteira a partir do primeiro erro. Só os blocos que casam
    recebem marca -- o que o motor leu diferente fica de fora, que é a resposta honesta.

    Vazio é o "não sei", e ele tem três causas, todas legítimas: a folha não tem camada, a caixa não
    encontra nenhuma linha da camada (página girada -- ver `spans_com`, que também não gira), ou os
    textos discordam demais (`CASAMENTO_MINIMO`). Nos três, quem desenha volta ao campo de linha.
    """
    if not texto:
        return ()
    candidatas = [linha for linha in linhas if _sobrepoe(bbox, linha.bbox)]
    if not candidatas:
        return ()
    candidatas.sort(key=lambda linha: linha.bbox[0])
    # Um espaço entre duas linhas da camada, como `bloco.texto` junta as linhas lidas: sem ele
    # `...calculation` e `The rook...` virariam `...calculationThe rook...` e o casamento perderia
    # a costura das duas palavras da emenda.
    da_camada = " ".join(linha.texto for linha in candidatas)
    marcas: list[bool] = []
    for i, linha in enumerate(candidatas):
        if i:
            marcas.append(False)
        marcas.extend(linha.marcas)

    tem_estilo = [False] * len(texto)
    casados = 0
    for i, j, n in SequenceMatcher(None, texto, da_camada, autojunk=False).get_matching_blocks():
        casados += n
        for k in range(n):
            tem_estilo[i + k] = marcas[j + k]
    if casados < len(texto) * minimo:
        return ()
    return _intervalos(texto, tem_estilo)


def remapear(intervalos: Sequence[Trecho], antigo: str, novo: str) -> tuple[Trecho, ...]:
    """Os mesmos intervalos, sobre um texto que foi reescrito depois de eles serem achados.

    **Existe porque a linha ainda muda depois da leitura** (S-429). `_sem_hifen_de_quebra` junta a
    palavra que a diagramação partiu -- `em-` mais `barrassment` --, e isso acontece **depois** de
    os intervalos serem casados: sem remapear, um negrito de duas palavras no fim da linha ficaria
    apontando para onde o texto já não está, e desenharia peso no meio de outra palavra.

    Mesma ferramenta do casamento original, pela mesma razão: `difflib` acha o que sobreviveu à
    reescrita sem precisar saber que reescrita foi essa. O que a edição comeu não vira intervalo em
    lugar nenhum, e é o certo -- caractere que sumiu não tem estilo.
    """
    if not intervalos or antigo == novo:
        return tuple(intervalos)
    tem_estilo = [False] * len(novo)
    marcado_no_antigo = [False] * len(antigo)
    for inicio, fim in intervalos:
        for i in range(max(0, inicio), min(len(antigo), fim)):
            marcado_no_antigo[i] = True
    for j, i, n in SequenceMatcher(None, antigo, novo, autojunk=False).get_matching_blocks():
        for k in range(n):
            tem_estilo[i + k] = marcado_no_antigo[j + k]
    return _intervalos(novo, tem_estilo)


def _palavras(texto: str) -> list[Trecho]:
    """Os intervalos de não-branco de `texto`, na ordem. A unidade em que o estilo é decidido."""
    saida: list[Trecho] = []
    comeco: int | None = None
    for i, caractere in enumerate(texto):
        if caractere.isspace():
            if comeco is not None:
                saida.append((comeco, i))
                comeco = None
        elif comeco is None:
            comeco = i
    if comeco is not None:
        saida.append((comeco, len(texto)))
    return saida


def _intervalos(texto: str, tem_estilo: Sequence[bool]) -> tuple[Trecho, ...]:
    """Os `True` vizinhos como intervalos, decididos **por palavra** e não por caractere.

    **A palavra é a unidade, e o motivo é o erro de leitura.** O casamento marca só o que casou, e o
    motor de glifo lê `smdy` onde a camada escreve `study` (S-186): ali o `t` e o `u` não casam, e
    marcar caractere a caractere devolveria `s` e `dy` em negrito com um `m` em pé no meio -- uma
    palavra rachada, que é pior na tela do que a linha grossa que este item veio consertar. Maioria
    dos caracteres da palavra decide a palavra inteira, e nenhuma palavra sai partida.

    Nenhum PDF do acervo troca de fonte no meio de uma palavra; onde a mudança é de verdade -- o
    `1.e4` em negrito seguido do `!?` em pé -- ela cai numa palavra só e a maioria a resolve para o
    lado de quem tem mais letra, que é o que se lê na folha.

    **O espaço entre duas palavras marcadas entra, e o das pontas não.** Entra porque um negrito que
    para no espaço e recomeça sairiam dois trechos onde a folha tem um; não entra nas pontas porque
    um trecho que começa num espaço desenha o realce um caractere antes da letra -- que é o mesmo
    cuidado que `rico._corridas_do_segmento` toma com o espaço da junção das linhas.
    """
    marcado = [False] * len(texto)
    for inicio, fim in _palavras(texto):
        quantos = sum(1 for i in range(inicio, fim) if tem_estilo[i])
        if quantos * 2 >= fim - inicio:
            for i in range(inicio, fim):
                marcado[i] = True

    # O branco entre duas palavras marcadas vira marcado. Uma passada, olhando para trás.
    inicio_do_branco = None
    for i, caractere in enumerate(texto):
        if caractere.isspace() and not marcado[i]:
            if inicio_do_branco is None:
                inicio_do_branco = i
            continue
        if inicio_do_branco is not None and marcado[i] and inicio_do_branco > 0 and marcado[inicio_do_branco - 1]:
            for k in range(inicio_do_branco, i):
                marcado[k] = True
        inicio_do_branco = None

    saida: list[Trecho] = []
    comeco: int | None = None
    for i in range(len(texto) + 1):
        se_marcado = i < len(texto) and marcado[i]
        if se_marcado and comeco is None:
            comeco = i
        elif not se_marcado and comeco is not None:
            fim = i
            while comeco < fim and texto[comeco].isspace():
                comeco += 1
            while fim > comeco and texto[fim - 1].isspace():
                fim -= 1
            if fim > comeco:
                saida.append((comeco, fim))
            comeco = None
    return tuple(saida)


_RESPOSTAS: dict[tuple[str, str, float, int], bool] = {}
"""A resposta de `documento_registra` por (marca, arquivo, mtime, amostra). Ver o docstring dela."""


def _identidade(doc: object) -> tuple[str, float] | None:
    """`(caminho, mtime)` do PDF, ou `None` quando ele não tem identidade estável no disco.

    `PdfSource` aceita `bytes` e um documento já aberto, e nesses casos `doc.name` é vazio: um
    cache chaveado por nome vazio devolveria a resposta de **outro** documento. Sem identidade,
    sem memória -- e a conta volta a ser a de antes, que é correta e só é lenta.

    O `mtime` entra na chave porque um PDF reescrito no lugar é outro livro com o mesmo nome.
    """
    nome = str(getattr(doc, "name", "") or "")
    if not nome:
        return None
    try:
        return nome, Path(nome).stat().st_mtime
    except OSError:  # pragma: no cover - arquivo sumiu entre abrir e perguntar
        return None


def documento_registra(
    doc: object,
    e_do_estilo: Callable[[dict], bool],
    *,
    amostra: int = PAGINAS_DE_AMOSTRA,
    marca: str = "",
) -> bool:
    """Este documento registra aquele estilo em algum lugar? Ver `PAGINAS_DE_AMOSTRA`.

    **É a pergunta que separa `False` de `None`.** Uma página sem itálico num livro que o registra é
    "aqui não tem"; num livro que não o registra é "não se sabe", e as duas não podem virar a mesma
    coisa.

    **É uma pergunta sobre o LIVRO, e era refeita a cada folha (S-313).** Ela abre uma amostra de
    páginas e varre os spans delas; `ler_pagina` a fazia duas vezes por folha, uma para o peso e
    outra para o pendor. Medido no `A Matter of Endgame Technique` (898 folhas): 1,612 s + 1,300 s
    = **2,912 s por folha**, contra 0,233 s + 0,166 s da leitura dos spans da folha em si. Nos 45
    PDFs do acervo, onze livros custam mais de 0,5 s por folha só nestas duas perguntas.

    `marca` é o nome do estilo, e é o que torna a memória possível: `e_do_estilo` é uma função, e
    duas funções diferentes com o mesmo comportamento não têm chave comum. Sem `marca`, não há
    cache -- é o padrão, para que nenhum chamador ganhe memória sem pedir.
    """
    identidade = _identidade(doc) if marca else None
    if identidade is not None:
        chave = (marca, identidade[0], identidade[1], amostra)
        guardada = _RESPOSTAS.get(chave)
        if guardada is not None:
            return guardada
    try:
        total = int(doc.page_count)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        return False
    if total <= 0:
        return False
    passos = max(1, total // (amostra + 1))
    resposta = False
    for indice in range(passos, total, passos):
        try:
            if spans_com(doc[indice], e_do_estilo):  # type: ignore[index]
                resposta = True
                break
        except Exception:  # pragma: no cover - página ilegível
            continue
    if identidade is not None:
        _RESPOSTAS[(marca, identidade[0], identidade[1], amostra)] = resposta
    return resposta


def esquecer_documentos() -> None:
    """Apaga a memória de `documento_registra`. Para os testes, e para quem reabre o acervo."""
    _RESPOSTAS.clear()


def cobertura(bbox: Retangulo, spans: Sequence[Retangulo]) -> float:
    """Fração da **largura** da linha coberta pelos spans. `0.0` quando não há sobreposição.

    Largura e não área porque a linha e o span têm a mesma altura por construção -- os dois vêm da
    mesma linha de texto --, e comparar áreas só acrescentaria ruído de arredondamento vertical.
    """
    x0, y0, x1, y1 = bbox
    largura = x1 - x0
    if largura <= 0:
        return 0.0

    partes: list[tuple[float, float]] = []
    for sx0, sy0, sx1, sy1 in spans:
        if min(y1, sy1) - max(y0, sy0) <= 0:
            continue
        a, b = max(x0, sx0), min(x1, sx1)
        if b > a:
            partes.append((a, b))
    if not partes:
        return 0.0

    partes.sort()
    total = 0.0
    atual_a, atual_b = partes[0]
    for a, b in partes[1:]:
        if a > atual_b:
            total += atual_b - atual_a
            atual_a, atual_b = a, b
        else:
            atual_b = max(atual_b, b)
    total += atual_b - atual_a
    return min(1.0, total / largura)


def marcar(
    bboxes: Sequence[Retangulo],
    spans: Sequence[Retangulo],
    *,
    registra: bool,
    minimo: float = COBERTURA_MINIMA,
) -> list[bool | None]:
    """Uma resposta por linha: `True`, `False`, ou `None` quando o documento não registra o estilo.

    `registra=False` devolve `None` para todas, e é o caminho dos livros do acervo que não têm a
    informação. **Devolver `False` ali seria afirmar que nada tem aquele estilo**, que é uma
    afirmação que ninguém mediu.
    """
    if not registra:
        return [None] * len(bboxes)
    return [cobertura(b, spans) >= minimo for b in bboxes]
