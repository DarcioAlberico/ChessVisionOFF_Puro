"""O árbitro de notação: a gramática, a continuidade e a legalidade decidem o lance disputado (S-729, S-743).

**A fusão olha a forma do token, e aqui se olha o que ele tem de ser.** As regras da S-721 dizem "notação fica com tal
leitor". Só que a notação tem um modelo de língua exato, que a prosa não tem: depois de uma peça e de uma coluna vem um
dígito de 1 a 8, depois de `10.` vem `11.`, e o lance tem de ser legal na posição. Três juízes, do mais barato ao mais caro:

1. **A gramática.** O token que não é lance por um caractere, ao lado de leitura que é, ou com o caractere que a gramática
   força: `Dhs` -> `Dh5`, `Kgı` -> `Kg1`, `Tgı-g2` -> `Tg1-g2`, `Io.` -> `10.`, `ASR` -> `A5R`. O dígito de estilo antigo do século
   XIX (S-743) é só um mapa a mais de homóglifos, e **só vale na posição em que o dígito é obrigatório**: fora dela `Das` é palavra.
2. **A continuidade do número de lance.** `21.` contra `27.`, com `26.` antes, é `27.`: a regra de forma da S-721 ficava com o glifo.
3. **A legalidade**, quando quem chama dá a posição do diagrama (`Posicao`). O lance que não cabe na posição, ao lado de leitura
   que cabe. O alcance é pequeno, e é medido: ver a spec da S-729.

**Nada aqui inventa lance.** Toda troca sai de uma leitura de um dos dois leitores, ou de um homóglifo escrito na tabela. Nada
de "parece com" (S-209), e nenhum lance sai do tabuleiro: a posição só escolhe entre o que foi lido.

**A régua fica de fora**, como em `fusao.py`: o teste de grafo de import vale para este módulo também.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import chess

from . import fusao as _fusao
from . import notacao as _notacao

GRAMATICA = True
"""O interruptor da S-729: desligado, valem as regras de forma da S-721, e nada aqui roda."""

DIGITO_FORCADO = True
"""A constante da S-743: o dígito forçado pela gramática na casa e no número de lance."""

CURTA_DE_TRES = 3
"""Letras. Até aqui a curta pede número de lance antes, ou um lance de cada lado (`Dhs`, `RID`), e `lexico.MIN_TAMANHO` não ajuda."""

JANELA_DO_NUMERO = 12
"""Tokens para cada lado, ao procurar o número vizinho."""

MAXIMO_DE_EDICOES = 2
"""Quanto duas leituras do mesmo lugar podem diferir para serem da mesma tinta: `Dro-` contra `Df6.` e `ins` contra `h8` são 3."""

CONTINUIDADE = True
LEGALIDADE = True
"""Só faz efeito quando quem chama passa posições."""

_RANK = {
    "ı": "1", "I": "1", "l": "1", "|": "1", "i": "1", "]": "1",
    "z": "2", "Z": "2",
    "g": "3", "З": "3",
    "q": "4", "A": "4",
    "s": "5", "S": "5", "ö": "5",
    "b": "6", "G": "6", "б": "6",
    "y": "7", "v": "7", "T": "7",
    "B": "8",
}
"""O que a gramática aceita como dígito **na posição da casa**, onde só cabe de 1 a 8. De onde veio: `Kgı`, `Dhs`, `Sbı-cg`, `Tdy-f7`,
`Seö-f3`, `Sf3xeb` no *Bachmann*, `dı-h5` no *Neumann*, `dS` no *Yusupov*; `б` e `З` são os homóglifos do cirílico que a S-729 lista."""

_NUMERO = {"ı": "1", "I": "1", "l": "1", "|": "1", "o": "0", "O": "0", "z": "2", "Z": "2", "s": "5", "S": "5", "B": "8", "G": "6", "y": "7"}
"""O mesmo, no número de lance: lá cabe o zero, e o `g` fica de fora, porque pode ser 3 ou 9 e o número não tem como dizer."""

_ARQUIVO_CIRILICO = {"а": "a", "е": "e", "с": "c", "Ь": "b"}
"""A letra de coluna em cirílico, do Tesseract em russo: só em token que a gramática chama de lance."""

_CIRILICO_NO_LANCE = str.maketrans({**_ARQUIVO_CIRILICO, "х": "x", "В": "B"})
"""O `Вхе4` do Tesseract é `Bxe4`: `В` não é peça em russo, e a peça russa (`К`, `Ф`, `Л`, `С`, `Кр`) fica como o livro a escreve."""

_PECA = "KQRBNDTLSCFAPКФЛСВ♔♕♖♗♘♙♚♛♜♝♞♟"
_CASA_TORTA = rf"[a-hаеЬс](?:[1-8]|[{re.escape(''.join(_RANK))}])"
_SEP = r"[-—–―=<>×xX:~]+"
_NUM = rf"[0-9{re.escape(''.join(_NUMERO))}]{{1,3}}"
_PREFIXO = rf"(?P<abre>[(\[:]?)(?:(?P<num>{_NUM})(?P<ponto>\.{{1,3}}|\))\s*)?"
_SUFIXO = r"(?P<fim>[+#†‡✝t!?.,;:)\]]*)"
_LONGA = re.compile(rf"^{_PREFIXO}(?P<peca>Кр|[{_PECA}]?)(?P<de>{_CASA_TORTA})(?P<sep>{_SEP})(?P<para>{_CASA_TORTA}){_SUFIXO}$")
_CURTA = re.compile(rf"^{_PREFIXO}(?P<peca>Кр|[{_PECA}])(?P<meio>[a-hаеЬс]?[1-8]?[xX:×х]?)(?P<para>{_CASA_TORTA}){_SUFIXO}$")
_PEAO = re.compile(rf"^{_PREFIXO}(?P<peca>)(?P<meio>(?:[a-hаеЬс][xX:×х])?)(?P<para>{_CASA_TORTA}){_SUFIXO}$")
_SO_NUMERO = re.compile(rf"^(?P<abre>[(\[]?)(?P<num>{_NUM})(?P<ponto>\.{{1,3}}|\)){_SUFIXO}$")
_DESCRITIVA = re.compile(
    rf"^{_PREFIXO}(?P<peca>[RDTACP])(?P<rank>[1-8]|[{re.escape(''.join(_RANK))}])(?P<arq>[RDTAC]{{1,2}}R?){_SUFIXO}$"
)
"""A descritiva das línguas latinas: `P4R`, `C3AR`, `R1D`. É a de que a saída da S-729 fala (`R1D` -> `RID`, `P5C` -> `PSC`)."""

_SO_NUMERO_LIMPO = re.compile(r"^[(\[]?\d{1,3}(?:\.{1,3}|\))$|^\.{2,3}$|^…$")
_NUMERO_COLADO = re.compile(r"^[(\[:]?\d{1,3}(?:\.{1,3}|\))")
_NU_DE_PONTA = re.compile(r"^[(\[:]+|[+#†‡✝t!?.,;:)\]]+$")
_ESTRITA = re.compile(
    rf"^[(\[:]?(?:\d{{1,3}}(?:\.{{1,3}}|\))\s*|\.{{1,3}})?(?:"
    rf"[{_PECA}]?[a-h][1-8]{_SEP}[a-h][1-8]"
    rf"|[{_PECA}][a-h]?[1-8]?[xX:×]?[a-h][1-8](?:=?[{_PECA}])?"
    rf"|(?:[a-h][xX:×]?)?[a-h][1-8](?:=?[{_PECA}])?"
    rf"|[RDTACP][1-8][RDTAC]{{1,2}}R?"
    rf"|O-O(?:-O)?|0-0(?:-0)?"
    rf")[+#†‡✝t!?.,;:)\]]*$"
)


def e_estrita(token: str) -> bool:
    """É lance pela gramática, com o dígito no lugar? `Dh5`, `Sg1-f3`, `1...e5`, `P4R`. `Dhs` e `ABR`, não."""
    return _ESTRITA.match(token) is not None


def _posto(char: str) -> str:
    return char if char in "12345678" else _RANK.get(char, char)


def _casa(casa: str) -> str:
    return _ARQUIVO_CIRILICO.get(casa[0], casa[0]) + _posto(casa[1])


def _numero(numero: str | None) -> str:
    return "" if numero is None else "".join(_NUMERO.get(c, c) for c in numero)


def _prefixo(m: re.Match[str]) -> str:
    return f"{m['abre']}{_numero(m['num'])}{m['ponto'] or ''}"


def forcado(token: str) -> tuple[str, str]:
    """O token com os dígitos que a gramática força, e de que forma ele é: `longa`, `curta`, `peao`, `numero`, `descritiva`.

    Nada se decide aqui: `(token, "")` se ele não tem uma dessas formas. Quem decide se a forma basta é `_precisa_de_contexto`.
    """
    if not DIGITO_FORCADO:
        return token, ""
    m = _LONGA.match(token)
    if m:
        return f"{_prefixo(m)}{m['peca'].translate(_CIRILICO_NO_LANCE)}{_casa(m['de'])}{m['sep']}{_casa(m['para'])}{m['fim']}", "longa"
    m = _CURTA.match(token)
    if m:
        return f"{_prefixo(m)}{m['peca'].translate(_CIRILICO_NO_LANCE)}{m['meio'].translate(_CIRILICO_NO_LANCE)}{_casa(m['para'])}{m['fim']}", "curta"
    m = _PEAO.match(token)
    if m:
        return f"{_prefixo(m)}{m['meio'].translate(_CIRILICO_NO_LANCE)}{_casa(m['para'])}{m['fim']}", "peao"
    m = _SO_NUMERO.match(token)
    if m:
        return f"{m['abre']}{_numero(m['num'])}{m['ponto']}{m['fim']}", "numero"
    m = _DESCRITIVA.match(token)
    if m:
        return f"{_prefixo(m)}{m['peca']}{_posto(m['rank'])}{m['arq']}{m['fim']}", "descritiva"
    return token, ""


@dataclass(frozen=True)
class Posicao:
    """A posição de um diagrama, e de onde a leitura dela passa a valer: o token `inicio` da lista achatada da folha."""

    tabuleiro: chess.Board
    inicio: int
    ambos_os_lados: bool = True
    """O lado a jogar lido do diagrama erra: quando vale, tenta-se o outro antes de dizer que o lance é ilegal."""


@dataclass
class Relato:
    """O que o árbitro fez na folha. Conta para a régua: quantos tokens a legalidade alcançou é um número publicado."""

    forcados: int = 0
    pela_outra_leitura: int = 0
    pela_continuidade: int = 0
    pela_legalidade: int = 0
    lances_alcancados: int = 0
    trocas: list[tuple[str, str, str]] | None = None


def _vizinho_de_notacao(token: str) -> bool:
    """Lance, número ou figurina. **`+`, `-` e `=` soltos não contam**: `Tal - Smyslov` é o título de uma partida."""
    if not token:
        return False
    if e_estrita(token) or _tem_figurina(token) or _numero_de(token) is not None:
        return True
    return forcado(token)[1] == "longa" and any(c.isdigit() for c in token)


def _numero_de_lance_antes(lista: Sequence[str], k: int) -> bool:
    return k > 0 and _SO_NUMERO_LIMPO.match(lista[k - 1]) is not None


def _numero_cabe(lista: Sequence[str], k: int, numero: str) -> bool:
    """`B.` só é `8.` com `7.` ou `9.` por perto: `A. B. Keres` tem lance adiante, e não é número."""
    valor = _numero_de(numero)
    if valor is None:
        return False
    if valor == 1:
        return True
    vizinhos = [_numero_de(t) for t in (*lista[max(0, k - JANELA_DO_NUMERO) : k], *lista[k + 1 : k + 1 + JANELA_DO_NUMERO])]
    return any(v is not None and abs(v - valor) <= 1 for v in vizinhos)


def _pode_forcar(forma: str, token: _fusao.Token, lista: Sequence[str], k: int, existe: Callable[[str], bool]) -> bool:
    """O dígito forçado vale aqui? **Nenhuma forma basta sozinha sem um dígito de verdade.**

    O léxico é cego para o que tem menos de 4 letras (`lexico.MIN_TAMANHO`), e `Tal`, `Rei`, `Key`, `Lev`, `Day` e `Say` têm a forma de lance. Sem
    dígito no original, quem diz que ali há um dígito é **o glifo ter lido outra coisa**: dois leitores iguais não são disputa. A partir daí,
    a forma diz quanto contexto basta.
    """
    original = token.texto
    tem_digito = any(c.isdigit() for c in original)
    if not tem_digito and (not token.do_glifo or token.do_glifo.casefold() == original.casefold()):
        return False
    antes = k > 0 and _vizinho_de_notacao(lista[k - 1])
    depois = k + 1 < len(lista) and _vizinho_de_notacao(lista[k + 1])
    if forma == "numero":
        return "ı" in original or (depois and _numero_cabe(lista, k, forcado(original)[0]))
    if forma == "peao":
        # `as` antes de `P-QB4` e `by` antes de `c2-c3`: palavra que existe não é lance de peão, entre o que for.
        return antes and depois and not existe(original)
    if forma == "longa":
        # `Deixei` tem a forma de `De1xe1`. Com dígito, `Tgı-g2` não é outra coisa; sem ele, pede vizinho e não pode ser palavra.
        return tem_digito or ((antes or depois) and not existe(original))
    if forma == "curta" and _NUMERO_COLADO.match(forcado(original)[0]):
        return True
    if len(_NU_DE_PONTA.sub("", original)) <= CURTA_DE_TRES:
        # `Key move`, `Rei + Peão`: três letras são palavra até prova em contrário.
        comeco = _numero_de_lance_antes(lista, k) or (antes and depois)
        return comeco and (not existe(original) or (antes and depois))
    return (antes or depois) and (not existe(original) or (antes and depois))


def _numero_de(token: str) -> int | None:
    m = re.match(r"^[(\[]?(\d{1,3})(?:\.{1,3}|\))", token)
    return int(m.group(1)) if m else None


def _troca_numero(token: str, numero: int) -> str:
    return re.sub(r"^([(\[]?)\d{1,3}", lambda m: f"{m.group(1)}{numero}", token, count=1)


_PECA_POR_LINGUA = {
    "por": str.maketrans("RDTC", "KQRN"),
    "spa": str.maketrans("RDTAC", "KQRBN"),
    "deu": str.maketrans("DTLS", "QRBN"),
    "fra": str.maketrans("RDTFC", "KQRBN"),
    "nld": str.maketrans("DTLP", "QRBN"),
}
"""A letra de peça de cada língua, em inglês. **Só a da língua do livro**: `R` é torre em inglês e rei em português."""


def _lance_nu(token: str, lingua: str = "eng") -> str:
    """O token pronto para o tabuleiro: sem número nem o que vem colado no fim, e com a peça em inglês."""
    nu = token.strip("()[],;:")
    nu = re.sub(r"^\d{1,3}(?:\.{1,3}|\))\s*", "", nu)
    nu = re.sub(r"^\.{2,3}|^…", "", nu)
    if nu[:1] and not "♔" <= nu[:1] <= "♟":
        nu = nu[:1].translate(_PECA_POR_LINGUA.get(lingua, {})) + nu[1:]
    nu = re.sub(r"[-—–―]+", "-", _notacao.para_ingles(nu))
    nu = re.sub(r"[><=×:~]+(?=[a-h])", "x", nu)
    return nu.rstrip("+#†‡✝!?.:;,=±∓⩲⩱∞")


def _legal(tabuleiro: chess.Board, token: str, lingua: str = "eng") -> chess.Move | None:
    try:
        return tabuleiro.parse_san(_lance_nu(token, lingua))
    except (ValueError, chess.IllegalMoveError, chess.InvalidMoveError, chess.AmbiguousMoveError):
        return None


def _candidatos_de_legalidade(token: _fusao.Token) -> list[str]:
    """O que foi lido ali: o texto, a outra leitura, e o dígito forçado de cada um. Sem fabricar nada."""
    saida = []
    for leitura in (token.texto, token.do_glifo, token.do_leitor):
        for forma in (leitura, forcado(leitura)[0]):
            if forma and forma not in saida:
                saida.append(forma)
    return saida


def _pela_legalidade(
    tokens: list[_fusao.Token],
    posicoes: Sequence[Posicao],
    relato: Relato,
    lingua: str,
) -> None:
    """Da posição do diagrama em diante, joga os lances lidos; o primeiro que não cabe olha as outras leituras dele."""
    limites = [p.inicio for p in posicoes[1:]] + [len(tokens)]
    for posicao, fim in zip(posicoes, limites, strict=True):
        lados = [posicao.tabuleiro.copy(stack=False)]
        if posicao.ambos_os_lados:
            outro = posicao.tabuleiro.copy(stack=False)
            outro.turn = not outro.turn
            if outro.is_valid():
                lados.append(outro)
        melhor: list[tuple[int, str]] = []
        melhor_jogados = 0
        for lado in lados:
            jogados, trocas = _jogar_o_trecho(lado, tokens, posicao.inicio, fim, lingua)
            if jogados > melhor_jogados:
                melhor, melhor_jogados = trocas, jogados
        relato.lances_alcancados += melhor_jogados
        for k, novo in melhor:
            relato.pela_legalidade += 1
            if relato.trocas is not None:
                relato.trocas.append(("legalidade", tokens[k].texto, novo))
            tokens[k] = replace(tokens[k], texto=novo)


_FIGURINA_SOLTA = re.compile(r"^[(\[]?(?:\d{1,3}\.{1,3})?[♔-♟]$")


def _jogar_o_trecho(
    tabuleiro: chess.Board, tokens: Sequence[_fusao.Token], inicio: int, fim: int, lingua: str
) -> tuple[int, list[tuple[int, str]]]:
    """Até a primeira palavra que não é lance, ou ao primeiro lance sem leitura legal. `♘ f6+` é um lance só."""
    jogados = 0
    trocas: list[tuple[int, str]] = []
    comecou = False
    peca = ""
    for k in range(inicio, fim):
        token = tokens[k]
        if _FIGURINA_SOLTA.match(token.texto):
            comecou, peca = True, token.texto
            continue
        de_notacao = e_estrita(token.texto) or _fusao.e_notacao(token.texto)
        if not comecou and not de_notacao:
            continue
        comecou = True
        if _SO_NUMERO_LIMPO.match(token.texto):
            continue
        if not de_notacao and not peca:
            break
        escolhido = next(
            ((c, m) for c in _candidatos_de_legalidade(token) if (m := _legal(tabuleiro, peca + c, lingua)) is not None),
            None,
        )
        peca = ""
        if escolhido is None:
            break
        if escolhido[0] != token.texto:
            trocas.append((k, escolhido[0]))
        tabuleiro.push(escolhido[1])
        jogados += 1
    return jogados, trocas


def arbitrar(
    linhas: Sequence[Sequence[_fusao.Token]],
    *,
    existe: Callable[[str], bool],
    posicoes: Sequence[tuple[int, chess.Board]] = (),
    lingua: str = "eng",
    relato: Relato | None = None,
) -> list[list[_fusao.Token]]:
    """As linhas da folha com a notação arbitrada, na mesma ordem. Prosa não é tocada.

    `posicoes` diz, por diagrama, em que **linha** a leitura dele começa, e a posição. Sem elas, só os dois primeiros juízes.
    """
    relato = relato if relato is not None else Relato()
    if not GRAMATICA:
        return [list(linha) for linha in linhas]
    planos = [token for linha in linhas for token in linha]
    _pela_gramatica(planos, existe, relato)
    if CONTINUIDADE:
        _pela_continuidade(planos, relato)
    if LEGALIDADE and posicoes:
        comeco = [0]
        for linha in linhas:
            comeco.append(comeco[-1] + len(linha))
        ordem = sorted((comeco[min(k, len(linhas))], tabuleiro) for k, tabuleiro in posicoes)
        _pela_legalidade(planos, [Posicao(tabuleiro, inicio) for inicio, tabuleiro in ordem], relato, lingua)
    saida: list[list[_fusao.Token]] = []
    k = 0
    for linha in linhas:
        saida.append([t for t in planos[k : k + len(linha)] if t.texto])
        k += len(linha)
    return saida


def _distancia_de_edicao(a: str, b: str) -> int:
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


_PONTOS_INICIAIS = re.compile(r"^\.+")
_NUMERO_DA_OUTRA = re.compile(r"^(\(?\d{1,3})(\.{1,3})")


def _numero_que_faltava(token: str, outra: str) -> str | None:
    """`...h6??` e `1...h6??` dão `1...h6??`; `.♖g6!` e `1.2g6!` dão `1.♖g6!`: só o número vem da outra, e a figurina fica."""
    m = _NUMERO_DA_OUTRA.match(outra)
    if not m or not _PONTOS_INICIAIS.match(token):
        return None
    return f"{m.group(1)}{m.group(2)}{_PONTOS_INICIAIS.sub('', token)}"


def _digitos_soltos_antes(textos: Sequence[str], k: int, numero: str) -> list[int] | None:
    """Os tokens que o glifo deixou antes do lance e que são este número: `1 1 ...♖xh4?` e `11...`. `None` se há número e é outro."""
    acumulado = ""
    indices: list[int] = []
    for j in range(k - 1, max(-1, k - 4), -1):
        if not textos[j].rstrip(".").isdigit():
            break
        acumulado = textos[j].rstrip(".") + acumulado
        indices.append(j)
        if acumulado == numero:
            return indices
    return None if indices else []


def _outra_leitura_vale(token: _fusao.Token, outra: str, textos: Sequence[str], k: int, existe: Callable[[str], bool]) -> bool:
    """A outra leitura é lance, esta não, e as duas são da mesma tinta. Figurina nunca é trocada por letra.

    **O glifo também lê `l` como `1`:** `Tal` contra `Ta1` não é prova de nada, e por isso o token sem dígito pede o mesmo contexto da curta.
    """
    texto = token.texto
    if not outra or not e_estrita(outra) or existe(texto) or not _parece_lance(texto) or _tem_figurina(texto):
        return False
    if _distancia_de_edicao(texto, outra) > MAXIMO_DE_EDICOES or texto.endswith("-"):
        return False
    antes = k > 0 and _vizinho_de_notacao(textos[k - 1])
    depois = k + 1 < len(textos) and _vizinho_de_notacao(textos[k + 1])
    if len(_NU_DE_PONTA.sub("", texto)) <= CURTA_DE_TRES:
        return _numero_de_lance_antes(textos, k) or (antes and depois)
    return antes or depois or any(c.isdigit() for c in texto)


def _tem_figurina(texto: str) -> bool:
    return any("♔" <= c <= "♟" for c in texto)


def _pela_gramatica(tokens: list[_fusao.Token], existe: Callable[[str], bool], relato: Relato) -> None:
    textos = [t.texto for t in tokens]

    def anota(k: int, forma: str, novo: str) -> None:
        if relato.trocas is not None:
            relato.trocas.append((forma, tokens[k].texto, novo))
        tokens[k] = replace(tokens[k], texto=novo)
        textos[k] = novo

    for k, token in enumerate(tokens):
        outra = token.do_glifo if token.origem == "outro" else token.do_leitor
        com_numero = _numero_que_faltava(token.texto, outra) if outra else None
        if com_numero is None and e_estrita(token.texto):
            continue
        if com_numero is not None and e_estrita(com_numero):
            soltos = _digitos_soltos_antes(textos, k, com_numero.lstrip("(").split(".")[0])
            if soltos is not None:
                relato.pela_outra_leitura += 1
                anota(k, "numero_da_outra", com_numero)
                for j in soltos:
                    tokens[j] = replace(tokens[j], texto="")
                    textos[j] = ""
                continue
        if _tem_figurina(token.texto):
            continue
        novo, forma = forcado(token.texto)
        # **O dígito forçado vem antes da outra leitura, salvo na descritiva.** No scan, a letra do Tesseract é a melhor das duas (`Tel,` é
        # `Te1,`, e o glifo leu `Tc1`); mas o rank da descritiva tem `B` por `3` e por `8`, e ali o glifo decide.
        if forma and forma != "descritiva" and novo != token.texto and _pode_forcar(forma, token, textos, k, existe):
            relato.forcados += 1
            anota(k, forma, novo)
            continue
        # `Db6x` e o `b2` seguinte, contra `Db6xb2`: a outra leu junto, e os dois pedaços já estão aqui.
        repete = k + 1 < len(textos) and bool(outra) and outra.endswith(textos[k + 1]) and outra.startswith(token.texto)
        if not repete and _outra_leitura_vale(token, outra, textos, k, existe):
            relato.pela_outra_leitura += 1
            anota(k, "outra_leitura", outra)
            continue
        if forma == "descritiva" and novo != token.texto and _pode_forcar(forma, token, textos, k, existe):
            relato.forcados += 1
            anota(k, forma, novo)


def _parece_lance(token: str) -> bool:
    """Tem cara de lance estragado: curto, sem palavra de verdade dentro, e não é só pontuação."""
    nu = token.strip("()[],;:.!?+#")
    return bool(nu) and len(nu) <= 7 and sum(c.isalpha() for c in nu) <= 4


def _pela_continuidade(tokens: list[_fusao.Token], relato: Relato) -> None:
    """`21.` contra `27.`, com `26.` antes ou `28.` depois: o número que continua a sequência vence a regra de forma."""
    numeros = [_numero_de(t.texto) for t in tokens]
    for k, token in enumerate(tokens):
        if numeros[k] is None:
            continue
        anterior = next((n for n in reversed(numeros[:k]) if n is not None), None)
        seguinte = next((n for n in numeros[k + 1 :] if n is not None), None)

        def cabe(n: int, antes: int | None = anterior, depois: int | None = seguinte) -> bool:
            return (antes is not None and n in (antes, antes + 1)) or (depois is not None and n in (depois, depois - 1))

        atual = numeros[k]
        if atual is None or cabe(atual):
            continue
        for outra in (token.do_glifo, token.do_leitor):
            candidato = _numero_de(outra) if outra else None
            if candidato is not None and candidato != atual and cabe(candidato):
                novo = _troca_numero(token.texto, candidato)
                relato.pela_continuidade += 1
                if relato.trocas is not None:
                    relato.trocas.append(("continuidade", token.texto, novo))
                tokens[k] = replace(token, texto=novo)
                numeros[k] = candidato
                break


__all__ = [
    "CONTINUIDADE",
    "DIGITO_FORCADO",
    "GRAMATICA",
    "LEGALIDADE",
    "Posicao",
    "Relato",
    "arbitrar",
    "e_estrita",
    "forcado",
]
