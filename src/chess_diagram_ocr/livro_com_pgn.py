"""Cada diagrama do PDF digital casado com o nó do PGN do livro (S-587 a S-589).

**A conta que justifica o módulo** (Harikrishna, 2026-10-29, `docs/ROADMAP_PDF_COM_PGN.md`): 1.177
legendas «Position after: 5.dxc5», 1.001 imagens. Das 913 legendas com imagem, a leitura do modelo de
produção é casa por casa a FEN de um candidato do PGN em 877 (96%); 15 diferem em uma casa e 21 em
três ou mais -- e nesses o erro é do modelo (cavalo lido como bispo, peças que somem). E ~176
legendas não têm imagem nenhuma: a conversão EPUB->PDF as perdeu, e só o PGN as pode redesenhar.

## Como um diagrama acha o seu nó

1. **A legenda.** O texto logo abaixo da imagem diz o lance (`lance_da_legenda`). Com o capítulo
   tirado do sumário do PDF (`capitulos_do_sumario`), os candidatos são os nós daquele capítulo com
   aquele rótulo -- um em 70% dos casos.
2. **O modelo desempata.** Quando a legenda se repete no capítulo (a mesma jogada em duas linhas),
   o candidato cujo tabuleiro é o que o modelo leu ganha; sem leitura, o primeiro depois do
   diagrama anterior, que é a ordem do livro.
3. **Sem legenda, a posição.** Livro sem legenda ainda tem o PGN: a leitura do modelo é procurada
   em todas as posições do livro (`IndiceDoLivro.com_posicao`), e a uma casa de um só nó vale como
   correção. No Harikrishna os resultados são os mesmos 877 + 15.

## O estado de cada diagrama

- `CONFERE`: o modelo leu a posição do nó. A FEN do PGN entra, com o lado a jogar dele.
- `CORRIGIDO`: o modelo errou até `CASAS_CORRIGIVEIS` casas. A FEN do PGN entra no lugar.
- `DISCORDA`: errou mais que isso. Pode ser o modelo, pode ser o par imagem-legenda: vai para a
  Revisão, com a FEN do PGN como sugestão, e não entra sozinha.
- `FALTANDO`: a legenda sem imagem. O diagrama é desenhado do PGN (S-591).
- `SEM_NO`: legenda ou leitura sem nó no PGN. O diagrama fica com o reconhecimento de sempre.
- `SEM_LEITURA`: há nó e imagem, mas ninguém leu a imagem ainda -- a FEN do nó é a resposta.

Nada aqui importa Qt nem o modelo: quem lê a imagem passa `ler`, e o teste passa um dicionário.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .config import DATA_DIR
from .pgn_do_livro import IndiceDoLivro, lance_da_legenda

logger = logging.getLogger(__name__)

__all__ = [
    "ARQUIVO_DAS_ASSOCIACOES",
    "CASAS_CORRIGIVEIS",
    "CONFERE",
    "CORRIGIDO",
    "DISCORDA",
    "DiagramaDoLivro",
    "FALTANDO",
    "SEM_LEITURA",
    "SEM_NO",
    "associar",
    "capitulos_do_sumario",
    "casamentos_da_galeria",
    "casar_livro",
    "casas_diferentes",
    "contagem",
    "diagramas_da_pagina",
    "esquecer",
    "legenda_da_linha",
    "nota_do_diagrama",
    "pgn_associado",
]

CONFERE = "confere"
CORRIGIDO = "corrigido"
DISCORDA = "discorda"
FALTANDO = "faltando"
SEM_NO = "sem_no"
SEM_LEITURA = "sem_leitura"

CASAS_CORRIGIVEIS = 2
"""Até quantas casas de diferença a FEN do PGN corrige o modelo sem pedir conferência.

Medido: das 36 discordâncias do Harikrishna, 15 eram de uma casa e nenhuma de duas; acima disso o
par imagem-legenda pode estar errado (era o caso das legendas sem imagem antes da S-588), e decidir
sozinho trocaria um erro do modelo por um erro de pareamento."""

PADROES_DE_LEGENDA: tuple[re.Pattern[str], ...] = (
    re.compile(r"Position after:?\s*(\S+)", re.IGNORECASE),
    re.compile(r"Posi[çc][ãa]o (?:ap[óo]s|depois de):?\s*(\S+)", re.IGNORECASE),
    re.compile(r"Stellung nach:?\s*(\S+)", re.IGNORECASE),
    re.compile(r"Posici[óo]n (?:tras|despu[ée]s de):?\s*(\S+)", re.IGNORECASE),
)
"""As formas de legenda conhecidas. A do Harikrishna (Thinkers Publishing) é a primeira; as outras
são as mesmas palavras nas línguas em que este projeto lê livros."""

LARGURA_MINIMA_DA_IMAGEM = 80.0
"""Em pontos do PDF. Abaixo disso a imagem é vinheta, ícone ou o símbolo de um figurino."""


@dataclass(frozen=True)
class DiagramaDoLivro:
    """Um diagrama (ou a legenda de um que faltou) e o nó do PGN que ele mostra."""

    pagina: int
    """A página em que o diagrama aparece (a da imagem; sem imagem, a da legenda). 1 = a primeira,
    como o sumário e o rodapé do livro contam."""
    legenda: str = ""
    pagina_da_legenda: int = 0
    """Difere de `pagina` quando a legenda abre a página seguinte à da imagem."""
    caixa: tuple[float, float, float, float] | None = None
    """A imagem, em pontos do PDF; `None` quando ela faltou."""
    capitulo: str = ""
    candidatos: tuple[int, ...] = ()
    no: int | None = None
    """Índice em `IndiceDoLivro.nos`."""
    fen: str = ""
    """A FEN do nó, com lado a jogar; vazia sem nó."""
    lido: str = ""
    """O campo de peças que o modelo leu na imagem; vazio sem leitura."""
    estado: str = SEM_LEITURA
    casas: tuple[int, ...] = field(default=())
    """As casas (0 = a8) em que o modelo e o PGN discordam."""


def casas_diferentes(campo_a: str, campo_b: str) -> tuple[int, ...]:
    """Índices (0 = a8) das casas em que dois campos de peças discordam; as 64 se um for ilegível."""
    from .fen_utils import labels_from_fen

    try:
        a, b = labels_from_fen(campo_a), labels_from_fen(campo_b)
    except ValueError:
        return tuple(range(64))
    return tuple(casa for casa, (x, y) in enumerate(zip(a, b, strict=True)) if x != y)


# ---------------------------------------------------------------- o PDF


def capitulos_do_sumario(sumario: Sequence[Sequence[Any]], capitulos: Iterable[str]) -> list[tuple[int, str]]:
    """`(primeira página, capítulo do PGN)` para cada entrada do sumário que casa com um capítulo.

    `sumario` é o `get_toc()` do PyMuPDF (`[nível, título, página]`). Casar é o título começar pelo
    nome do capítulo («Chapter 1 – Odd 3rd moves» e `Chapter 1`) ou o nome terminar pelo título
    (`Chapter Introduction` e «Introduction»). Sem número no fim do nome, «Chapter 1» casaria com
    «Chapter 10»: a comparação é por palavra inteira.
    """
    nomes = [c for c in capitulos if c]
    achados: list[tuple[int, str]] = []
    for entrada in sumario:
        titulo, pagina = str(entrada[1]).strip(), int(entrada[2])
        baixo = titulo.lower()
        for nome in nomes:
            n = nome.lower()
            if re.match(re.escape(n) + r"(?![\w])", baixo) or (len(baixo) > 3 and n.endswith(baixo)):
                achados.append((pagina, nome))
                break
    return sorted(achados)


def capitulo_da_pagina(pagina: int, inicios: Sequence[tuple[int, str]]) -> str:
    """O capítulo do PGN em que cai a página; vazio antes do primeiro ou sem sumário."""
    atual = ""
    for primeira, nome in inicios:
        if primeira <= pagina:
            atual = nome
    return atual


def legenda_da_linha(texto: str) -> str:
    """O lance que uma linha de legenda diz («5.dxc5»), ou `""` quando ela não é legenda."""
    for padrao in PADROES_DE_LEGENDA:
        achado = padrao.search(texto)
        if achado:
            return achado.group(1)
    return ""


def _legendas(dicionario: dict[str, Any]) -> list[tuple[tuple[float, float, float, float], str]]:
    achadas = []
    for bloco in dicionario.get("blocks", []):
        if bloco.get("type") != 0:
            continue
        for linha in bloco.get("lines", []):
            lance = legenda_da_linha("".join(span.get("text", "") for span in linha.get("spans", [])))
            if lance:
                achadas.append((tuple(linha["bbox"]), lance))
    return achadas


def _imagens(dicionario: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    return [
        tuple(b["bbox"])
        for b in dicionario.get("blocks", [])
        if b.get("type") == 1 and b["bbox"][2] - b["bbox"][0] >= LARGURA_MINIMA_DA_IMAGEM
    ]


def diagramas_da_pagina(
    dicionario: dict[str, Any],
    pagina: int,
    *,
    sobra_da_anterior: tuple[float, float, float, float] | None = None,
) -> tuple[list[DiagramaDoLivro], tuple[float, float, float, float] | None]:
    """Os diagramas da página (`page.get_text("dict")`), cada imagem com a legenda logo abaixo.

    A imagem de uma legenda é a mais baixa acima dela **sem outra legenda no meio** -- com outra no
    meio, a imagem é da outra, e a desta faltou no PDF (S-588: era o que fazia 130 legendas
    parecerem erro do modelo). Uma legenda no alto da página sem imagem acima pega a imagem que
    sobrou no pé da página anterior (`sobra_da_anterior`).

    Devolve os diagramas em ordem de leitura e a imagem que sobrou sem legenda no pé desta página.
    Imagens sem legenda no meio da página também viram diagrama (sem legenda): o livro sem
    legendas é casado pela posição.
    """
    legendas = sorted(_legendas(dicionario), key=lambda x: x[0][1])
    imagens = sorted(_imagens(dicionario), key=lambda r: r[3])
    usadas: set[int] = set()
    saida: list[DiagramaDoLivro] = []
    for caixa_da_legenda, texto in legendas:
        topo = caixa_da_legenda[1]
        acima = [k for k, im in enumerate(imagens) if im[3] <= topo + 4 and k not in usadas]
        escolhida: tuple[float, float, float, float] | None = None
        pagina_da_imagem = pagina
        if acima:
            k = max(acima, key=lambda i: imagens[i][3])
            entre = any(imagens[k][3] <= outra[1] < topo for outra, _ in legendas)
            if not entre:
                escolhida = imagens[k]
                usadas.add(k)
        elif sobra_da_anterior is not None and not any(outra[1] < topo for outra, _ in legendas):
            escolhida, pagina_da_imagem = sobra_da_anterior, pagina - 1
            sobra_da_anterior = None
        saida.append(
            DiagramaDoLivro(pagina=pagina_da_imagem, legenda=texto, pagina_da_legenda=pagina, caixa=escolhida)
        )
    restantes = [im for k, im in enumerate(imagens) if k not in usadas]
    ultima_legenda = max((c[3] for c, _ in legendas), default=-1.0)
    sobra = None
    if restantes and restantes[-1][1] > ultima_legenda:
        sobra = restantes.pop()  # pode ser a imagem cuja legenda abre a próxima página
    for im in restantes:
        saida.append(DiagramaDoLivro(pagina=pagina, caixa=im))
    saida.sort(key=lambda d: (d.caixa[1] if d.caixa else 1e9))
    return saida, sobra


# ---------------------------------------------------------------- o casamento


def _resolver(
    diagrama: DiagramaDoLivro,
    indice: IndiceDoLivro,
    ultimo: dict[str, int],
    ler: Callable[[DiagramaDoLivro], str] | None,
) -> DiagramaDoLivro:
    lido = ler(diagrama) if (ler is not None and diagrama.caixa is not None) else ""
    lance = lance_da_legenda(diagrama.legenda) if diagrama.legenda else None
    if lance:
        candidatos = indice.com_rotulo(diagrama.capitulo, lance) if diagrama.capitulo else []
        if not candidatos:
            candidatos = [k for cap in indice.capitulos for k in indice.com_rotulo(cap, lance)]
    elif lido:
        candidatos = indice.com_posicao(lido)
        if not candidatos:
            candidatos = _vizinhos(indice, lido)
    else:
        candidatos = []
    if not candidatos:
        return replace(diagrama, lido=lido, estado=SEM_NO)
    chave = diagrama.capitulo
    preferidos = candidatos
    if lido:
        # o mais perto da leitura, e não o primeiro na ordem: com o modelo errando uma casa nenhum
        # candidato é exato, e a ordem sozinha escolhia o nó de outra partida, a 15 casas
        distancia = {k: len(casas_diferentes(indice.nos[k].campo_de_pecas, lido)) for k in candidatos}
        menor = min(distancia.values())
        preferidos = [k for k in candidatos if distancia[k] == menor]
    depois = [k for k in preferidos if k > ultimo.get(chave, -1)]
    no = (depois or preferidos)[0]
    ultimo[chave] = no
    registro = indice.nos[no]
    casas: tuple[int, ...] = ()
    if diagrama.caixa is None:
        estado = FALTANDO
    elif not lido:
        estado = SEM_LEITURA
    else:
        casas = casas_diferentes(registro.campo_de_pecas, lido)
        estado = CONFERE if not casas else CORRIGIDO if len(casas) <= CASAS_CORRIGIVEIS else DISCORDA
    return replace(
        diagrama, candidatos=tuple(candidatos), no=no, fen=registro.fen, lido=lido, estado=estado, casas=casas
    )


def _vizinhos(indice: IndiceDoLivro, lido: str) -> list[int]:
    """Os nós a até `CASAS_CORRIGIVEIS` casas da leitura, se a posição mais perto for uma só."""
    melhor: list[str] = []
    menor = CASAS_CORRIGIVEIS + 1
    for campo in indice.posicoes():
        distancia = len(casas_diferentes(campo, lido))
        if distancia < menor:
            menor, melhor = distancia, [campo]
        elif distancia == menor:
            melhor.append(campo)
    return indice.com_posicao(melhor[0]) if len(melhor) == 1 else []


def casar_livro(
    paginas: Iterable[tuple[int, dict[str, Any]]],
    indice: IndiceDoLivro,
    *,
    sumario: Sequence[Sequence[Any]] = (),
    ler: Callable[[DiagramaDoLivro], str] | None = None,
) -> list[DiagramaDoLivro]:
    """Todos os diagramas das páginas, cada um com o seu nó e o seu estado. Ver o docstring do módulo.

    `paginas` são `(número da página, page.get_text("dict"))` em ordem; `ler(diagrama)` devolve o
    campo de peças que o modelo lê na caixa daquela página (ou vazio).
    """
    inicios = capitulos_do_sumario(sumario, indice.capitulos)
    ultimo: dict[str, int] = {}
    saida: list[DiagramaDoLivro] = []
    sobra: tuple[float, float, float, float] | None = None
    anterior = 0

    def sem_dono(pagina: int, caixa: tuple[float, float, float, float] | None) -> None:
        # a imagem do pé da página que a seguinte não reclamou: diagrama sem legenda da sua página
        if caixa is not None:
            diagrama = DiagramaDoLivro(pagina=pagina, caixa=caixa, capitulo=capitulo_da_pagina(pagina, inicios))
            saida.append(_resolver(diagrama, indice, ultimo, ler))

    for numero, dicionario in paginas:
        if numero != anterior + 1:
            sem_dono(anterior, sobra)
            sobra = None  # a imagem do pé de uma página só serve à seguinte
        diagramas, nova = diagramas_da_pagina(dicionario, numero, sobra_da_anterior=sobra)
        if sobra is not None and not any(d.caixa == sobra and d.pagina == numero - 1 for d in diagramas):
            sem_dono(anterior, sobra)
        anterior, sobra = numero, nova
        capitulo = capitulo_da_pagina(numero, inicios)
        for diagrama in diagramas:
            saida.append(_resolver(replace(diagrama, capitulo=capitulo), indice, ultimo, ler))
    sem_dono(anterior, sobra)
    return saida


def contagem(diagramas: Iterable[DiagramaDoLivro]) -> dict[str, int]:
    """Quantos diagramas em cada estado -- a frase da janela e o relatório da medição."""
    total: dict[str, int] = {}
    for diagrama in diagramas:
        total[diagrama.estado] = total.get(diagrama.estado, 0) + 1
    return total


def nota_do_diagrama(diagrama: DiagramaDoLivro, indice: IndiceDoLivro) -> str:
    """A frase que o Resultado mostra: «Chapter 1 · Game 3 · 5.dxc5 -- o PGN corrigiu 1 casa»."""
    if diagrama.no is None:
        return ""
    registro = indice.nos[diagrama.no]
    onde = " · ".join(x for x in (registro.capitulo, registro.secao, registro.rotulo) if x)
    estado = {
        CONFERE: "confere com a leitura",
        CORRIGIDO: f"o PGN corrigiu {len(diagrama.casas)} casa(s) da leitura",
        DISCORDA: f"discorda da leitura em {len(diagrama.casas)} casas; conferir",
        SEM_LEITURA: "posição do PGN",
        FALTANDO: "o diagrama falta no PDF",
    }.get(diagrama.estado, "")
    return f"{onde} -- {estado}" if estado else onde


# ---------------------------------------------------------------- a Galeria (S-594)

VAZIOS_DE_HEADER = frozenset({"", "?", "????.??.??", "*"})
"""O que um PGN escreve quando não sabe -- e que não é informação para levar à Galeria."""


def casamentos_da_galeria(
    entradas: Iterable[Any], diagramas: Iterable[DiagramaDoLivro], indice: IndiceDoLivro
) -> tuple[list[Any], int]:
    """Cada diagrama varrido pela Galeria que é, casa por casa, um nó do livro: `(casamentos, discordam)`.

    Os casamentos são `games_db.DiagramMatch`, os mesmos que a base de partidas produz, e entram
    pelo mesmo `GalleryModel.apply_matches` -- que preenche só o que está vazio e nunca sobrescreve
    o que a pessoa escreveu. O livro é tratado como uma base de uma partida só por diagrama, com a
    legenda confirmando: é a evidência mais forte que a Galeria conhece.

    **Só a posição exata casa.** O `confirmed_from` diz que as 64 casas aconteceram num tabuleiro
    de verdade; uma leitura a uma casa do nó não aconteceu, e quem a corrige é o Resultado (S-590),
    que troca a posição -- a Galeria só anota. `discordam` conta as entradas de páginas com
    diagrama do livro que não bateram com nenhum candidato: são as que a leitura errou.
    """
    from .games_db import DiagramMatch

    por_pagina: dict[int, list[DiagramaDoLivro]] = {}
    for diagrama in diagramas:
        if diagrama.caixa is not None and diagrama.candidatos:
            por_pagina.setdefault(diagrama.pagina, []).append(diagrama)
    casamentos, discordam = [], 0
    for entrada in entradas:
        da_pagina = por_pagina.get(int(entrada.page_index) + 1, [])
        achado = next(
            (
                (diagrama, k)
                for diagrama in da_pagina
                for k in diagrama.candidatos
                if indice.nos[k].campo_de_pecas == entrada.placement
            ),
            None,
        )
        if achado is None:
            discordam += bool(da_pagina)
            continue
        diagrama, k = achado
        registro = indice.nos[k]
        jogo = indice.partidas[registro.partida]
        casamentos.append(
            DiagramMatch(
                page_index=int(entrada.page_index),
                diagram_index=int(entrada.diagram_index),
                move_number=int(registro.fen.split()[5]),
                side_to_move=registro.lado,
                headers={nome: valor for nome, valor in jogo.headers.items() if valor not in VAZIOS_DE_HEADER},
                game_label="PGN do livro: " + " · ".join(x for x in (registro.capitulo, registro.secao, registro.rotulo) if x),
                caption_confirmed=bool(diagrama.legenda),
            )
        )
    return casamentos, discordam


# ---------------------------------------------------------------- o livro e o seu PGN (S-590)

ARQUIVO_DAS_ASSOCIACOES = DATA_DIR / "livros_com_pgn.json"
"""Qual `.pgn` acompanha qual PDF. A chave é a identidade do conteúdo do PDF (a do caderno da aba
Texto, `text.caderno.identidade_de`), e não o caminho: o livro movido ou copiado continua com o
seu PGN."""


def _associacoes(arquivo: Path) -> dict[str, dict[str, str]]:
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def pgn_associado(pdf: str | Path, *, arquivo: Path | None = None) -> Path | None:
    """O `.pgn` associado a este PDF, se houver e se ele ainda existir."""
    from .text.caderno import identidade_de

    identidade = identidade_de(pdf)
    if identidade is None:
        return None
    registro = _associacoes(arquivo or ARQUIVO_DAS_ASSOCIACOES).get(identidade)
    caminho = Path(registro["pgn"]) if registro and registro.get("pgn") else None
    return caminho if caminho is not None and caminho.is_file() else None


def associar(pdf: str | Path, pgn: str | Path, *, arquivo: Path | None = None) -> bool:
    """Lembra que este `.pgn` acompanha este PDF. `False` se o PDF não puder ser lido."""
    from .text.caderno import identidade_de

    identidade = identidade_de(pdf)
    if identidade is None:
        return False
    destino = arquivo or ARQUIVO_DAS_ASSOCIACOES
    dados = _associacoes(destino)
    dados[identidade] = {"pdf": Path(pdf).name, "pgn": str(Path(pgn).resolve())}
    destino.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(destino, dados)
    return True


def esquecer(pdf: str | Path, *, arquivo: Path | None = None) -> bool:
    """Desfaz a associação deste PDF. `False` se não havia nenhuma."""
    from .text.caderno import identidade_de

    identidade = identidade_de(pdf)
    destino = arquivo or ARQUIVO_DAS_ASSOCIACOES
    dados = _associacoes(destino)
    if identidade is None or identidade not in dados:
        return False
    del dados[identidade]
    atomic_write_json(destino, dados)
    return True
