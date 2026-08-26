"""O orçamento por página: quanto o texto soma à varredura, medido por etapa (S-215).

**O número que ninguém tinha.** A S-61 mediu ~2,95 s por página só do pipeline de diagramas, e
extrapolou ~10 h para o acervo (~12 mil páginas). Ler a página inteira como texto **soma** a
isso, e até aqui o quanto era palpite. Este módulo existe para que a descoberta aconteça antes de
a Fase 30 embarcar, e não depois de alguém deixar uma varredura rodando a noite inteira -- é a
regra de sequenciamento nº 3 do `ROADMAP_TEXTO`.

## O instrumento não entra no caminho medido

A tentação óbvia é espalhar `perf_counter()` por `leitor.ler_pagina`. Ela está recusada por dois
motivos, e o segundo é o que decide:

1. o caminho de leitura é o produto, e enchê-lo de contadores para medir uma vez é pagar
   manutenção para sempre;
2. **um caminho instrumentado não é o caminho que roda.** O que se quer saber é o custo do código
   que o usuário executa, e não o de uma variante dele.

Então a medição é por **envoltório temporário**: `medindo()` troca cada função de etapa pela
mesma função com um cronômetro em volta, roda o que lhe pedirem, e devolve tudo ao lugar. Fora do
`with` não sobra nada -- nem um `if` no caminho quente.

## Onde cada envoltório é posto, e por que não é onde a função mora

`leitor.py` faz `from .binarizacao import binarize` no topo: o nome `binarize` passou a ser um
**global do `leitor`**, e trocar `binarizacao.binarize` depois disso não muda a chamada que
`segmentar` faz. Por isso `ETAPAS` declara o módulo em que o nome é **procurado**, que às vezes é
o que define a função e às vezes não. `test_cada_etapa_aponta_para_um_alvo_que_existe` cobra que
o par (módulo, atributo) exista, e `test_o_perfil_separa_as_etapas` cobra que uma leitura de
verdade passe por todos -- que é o que pega o dia em que alguém mudar a forma do import.

## Tempo exclusivo, e por que a soma fecha

Uma etapa pode conter outra: `colados.separar` chama o árbitro, que é o classificador. Se as duas
contassem o intervalo inteiro, a soma das etapas passaria do tempo da página e o perfil mentiria
justamente onde ele deveria acusar. Cada moldura desconta o tempo das molduras que abriram dentro
dela, então o que se soma é **tempo exclusivo** -- e o que sobra entre a soma e o relógio da
página é o campo `nao_instrumentado`, que é resíduo honesto e nunca negativo.

## As duas unidades, e a política que o número escolhe

O item manda publicar segundos por página **e** horas para o acervo, porque as duas respondem a
perguntas diferentes: a primeira diz se a interface trava, a segunda diz se a varredura cabe numa
noite. E o fator sobre o custo de hoje é o que escolhe a política:

    fator = (página com texto) / (página sem texto)

| fator | política |
|---|---|
| até 1,5x | texto em toda varredura |
| 1,5x a 4x | texto sob demanda, por página |
| acima de 4x | texto como comando separado, fora da varredura |

**As duas pontas da divisão são medidas na mesma corrida**, na mesma máquina e nas mesmas páginas.
Dividir por um 2,95 s de agosto seria comparar máquinas, e a contenção entre sessões vale ~40%
nesta -- ver `docs/metrics/field_*.json`.

## A trava é a do `cvoff-census --fail-on-loss`

Regressão de desempenho é regressão. `comparar` recebe o perfil arquivado e o de agora e devolve
o que piorou além da margem; quem chama decide o código de saída. A margem existe porque um
relógio de parede não repete o valor: 10% é maior que a variação vista entre corridas seguidas na
mesma máquina ociosa, e menor que qualquer regressão que valha o nome.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter

logger = logging.getLogger(__name__)

PAGINAS_DO_ACERVO = 12_000
"""O tamanho do acervo em páginas, como a S-61 o extrapolou. Ver `horas_para_o_acervo`.

**É uma ordem de grandeza declarada, e não uma contagem.** O acervo tem livros duplicados (o
mesmo título em duas edições de arquivo), então contar páginas de `PDF/*.pdf` conta a mesma
página duas vezes. Quem quiser o número da sua pasta passa `paginas=` -- o padrão existe para
que a segunda unidade do relatório seja comparável com o ~10 h que o plano cita."""

MARGEM_PADRAO = 0.10
"""Quanto o custo por página pode piorar antes de `comparar` acusar. Ver o cabeçalho."""


@dataclass(frozen=True)
class Etapa:
    """Uma etapa do caminho de leitura, e onde pôr o cronômetro em volta dela.

    Cada alvo é `"modulo:atributo"`, e `modulo` é onde o nome é **procurado**, não necessariamente
    onde a função é definida -- ver "Onde cada envoltório é posto" no cabeçalho. O atributo aceita
    um ponto para alcançar método de classe (`ClassificadorDeGlifo.probabilidades`): trocá-lo na
    classe funciona qualquer que seja o import de quem chama.

    **Uma etapa tem uma lista de alvos, e não um só.** "As correções por linha" é uma etapa para
    quem lê o perfil e são seis módulos para quem lê o código; obrigar um alvo por etapa
    espalharia uma linha conceitual em seis linhas de tabela, cada uma pequena demais para
    significar alguma coisa.
    """

    nome: str
    alvos: tuple[str, ...]
    conta: str
    """A unidade que `chamadas` conta nesta etapa: `pagina`, `coluna` ou `linha`.

    Existe porque "0,8 s em classificação" e "0,8 s em 86 chamadas de classificação" respondem a
    perguntas diferentes, e a segunda é a que diz se o gargalo é o modelo ou o laço."""


ETAPAS: tuple[Etapa, ...] = (
    Etapa("renderizacao", ("chess_diagram_ocr.pdf_io:render_pdf_page",), "pagina"),
    Etapa("camada", ("chess_diagram_ocr.text.leitor:linhas_da_camada",), "pagina"),
    Etapa("deteccao", ("chess_diagram_ocr.detection.hybrid:detect_diagrams_in_pdf_page",), "pagina"),
    Etapa("binarizacao", ("chess_diagram_ocr.text.leitor:binarize",), "pagina"),
    Etapa(
        "contornos",
        (
            "chess_diagram_ocr.text.boxes:caixas_de_caractere",
            "chess_diagram_ocr.text.boxes:unir_pingos",
            "chess_diagram_ocr.text.boxes:excluir_diagramas",
            "chess_diagram_ocr.text.empilhados:unir",
            "chess_diagram_ocr.text.empilhados:barras",
        ),
        "pagina",
    ),
    Etapa("colados", ("chess_diagram_ocr.text.colados:separar",), "pagina"),
    Etapa(
        "linhas",
        (
            "chess_diagram_ocr.text.linhas:quebrar_em_linhas",
            "chess_diagram_ocr.text.linhas:ordem_em_faixa",
            "chess_diagram_ocr.text.duas_linhas:descartar_fragmentos",
        ),
        "coluna",
    ),
    Etapa("classificacao", ("chess_diagram_ocr.text.modelo:ClassificadorDeGlifo.probabilidades",), "linha"),
    Etapa(
        "correcoes",
        (
            "chess_diagram_ocr.text.caixa_alta:decidir",
            "chess_diagram_ocr.text.marca_fina:corrigir",
            "chess_diagram_ocr.text.empilhados:corrigir",
            "chess_diagram_ocr.text.italico:declarar",
            "chess_diagram_ocr.text.italico:corrigir",
            "chess_diagram_ocr.text.numero:corrigir",
            "chess_diagram_ocr.text.dicionario:corrigir",
        ),
        "linha",
    ),
    Etapa("leitura_de_linha", ("chess_diagram_ocr.text.leitura_de_linha:em_bloco",), "linha"),
    Etapa("coluna", ("chess_diagram_ocr.text.leitor:montar",), "pagina"),
)
"""As onze etapas, na ordem em que uma página as atravessa.

As cinco que a spec nomeia -- binarização, contornos, classificação, leitura por linha, coluna --
mais seis sem as quais o total não fecha: renderizar a folha, ler a camada do PDF, achar os
diagramas, o separador de colado da S-186 (que roda em `auto` na página e não é de graça), a
quebra em linhas, e as correções por linha.

**As correções entraram porque a primeira medição as deixou no resíduo, e ele saiu com 32% da
página** -- o maior número da tabela, e o único que não dizia nada. `italico.declarar` conta aqui
junto com as correções: ele é a mesma passada por linha, e separar a medição da correção que ela
alimenta daria duas linhas de tabela para um laço só.

**`classificacao` e `correcoes` não contam por página.** As duas rodam uma vez por linha de texto,
e é por isso que `conta` existe: sem o número de chamadas, um perfil não distingue "o modelo é
lento" de "o laço chama o modelo 86 vezes com uma linha de cada vez"."""

NOMES: tuple[str, ...] = tuple(etapa.nome for etapa in ETAPAS)

RESIDUO = "nao_instrumentado"
"""O que sobra entre o relógio da página e a soma das etapas.

Não é enfeite: ele é o que impede o perfil de parecer completo quando não é. Se um dia ele
crescer para metade da página, há etapa nova a declarar -- e se ficar **negativo**, a contabilidade
de tempo exclusivo está errada, que é o que `test_a_soma_das_etapas_nao_passa_do_total` cobra."""


class Cronometro:
    """Tempo exclusivo e número de chamadas por etapa. Ver "Tempo exclusivo" no cabeçalho.

    **Uma thread, e é contrato e não descuido.** A pilha de molduras é uma lista só: medir duas
    páginas em paralelo com o mesmo cronômetro daria desconto na moldura errada. Quem mede roda
    página a página -- que é como a varredura roda, e portanto é o que se quer medir.
    """

    def __init__(self) -> None:
        self.segundos: dict[str, float] = dict.fromkeys(NOMES, 0.0)
        self.chamadas: dict[str, int] = dict.fromkeys(NOMES, 0)
        self.total = 0.0
        """O relógio de parede em volta de tudo que rodou dentro do `with`."""
        self._pilha: list[float] = []

    @contextmanager
    def moldura(self, nome: str) -> Iterator[None]:
        """Abre uma moldura de etapa. O tempo das molduras aninhadas é descontado desta."""
        self._pilha.append(0.0)
        inicio = perf_counter()
        try:
            yield
        finally:
            decorrido = perf_counter() - inicio
            aninhado = self._pilha.pop()
            self.segundos[nome] = self.segundos.get(nome, 0.0) + decorrido - aninhado
            self.chamadas[nome] = self.chamadas.get(nome, 0) + 1
            if self._pilha:
                # A moldura de fora mediu este intervalo junto: ele sai de lá, inteiro.
                self._pilha[-1] += decorrido

    @property
    def residuo(self) -> float:
        """`total` menos a soma das etapas. Nunca negativo -- ver `RESIDUO`."""
        return max(0.0, self.total - sum(self.segundos.values()))


def _alcancar(declarado: str) -> tuple[object, str]:
    """`"modulo:atributo"` -> `(o objeto que tem o atributo, o nome final)`.

    Resolve o ponto do método de classe: `modelo:ClassificadorDeGlifo.probabilidades` desce até
    a classe e devolve o nome do método, que é onde o `setattr` tem de cair.
    """
    modulo, _, atributo = declarado.partition(":")
    alvo: object = importlib.import_module(modulo)
    partes = atributo.split(".")
    for parte in partes[:-1]:
        alvo = getattr(alvo, parte)
    return (alvo, partes[-1])


@contextmanager
def medindo(etapas: tuple[Etapa, ...] = ETAPAS) -> Iterator[Cronometro]:
    """Envolve cada etapa num cronômetro pela duração do bloco, e desfaz tudo ao sair.

    O `finally` devolve os originais mesmo quando o corpo levanta: uma medição que estoura no meio
    não pode deixar o processo com envoltórios pendurados, porque a próxima página mediria o
    cronômetro da anterior por cima.
    """
    relogio = Cronometro()
    originais: list[tuple[object, str, object]] = []

    for etapa in etapas:
        for alvo in etapa.alvos:
            dono, nome_final = _alcancar(alvo)
            original = getattr(dono, nome_final)
            originais.append((dono, nome_final, original))

            def envolver(funcao: object = original, chave: str = etapa.nome) -> object:
                def medida(*args: object, **kwargs: object) -> object:
                    with relogio.moldura(chave):
                        return funcao(*args, **kwargs)  # type: ignore[operator]

                medida.__name__ = getattr(funcao, "__name__", chave)
                medida.__doc__ = getattr(funcao, "__doc__", None)
                return medida

            setattr(dono, nome_final, envolver())

    inicio = perf_counter()
    try:
        yield relogio
    finally:
        relogio.total = perf_counter() - inicio
        for dono, nome_final, original in originais:
            setattr(dono, nome_final, original)


# --------------------------------------------------------------------------------------
# O perfil, e as duas unidades
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Perfil:
    """O custo de uma amostra de páginas, por etapa e por página.

    Tudo aqui é **por página** e não total: um perfil de 8 páginas e um de 40 têm de poder ser
    comparados, e é o número por página que a política lê.
    """

    paginas: int
    segundos_por_pagina: float
    etapas: Mapping[str, float]
    chamadas: Mapping[str, float]

    @classmethod
    def de_cronometro(cls, relogio: Cronometro, paginas: int) -> Perfil:
        """O que o cronômetro acumulou, dividido pelas páginas que passaram por ele.

        Chame **depois** do `with`: `total` só é fechado quando o bloco sai, e o resíduo sai
        zerado para quem perguntar antes disso.
        """
        n = max(1, int(paginas))
        etapas = {nome: relogio.segundos.get(nome, 0.0) / n for nome in NOMES}
        etapas[RESIDUO] = relogio.residuo / n
        return cls(
            paginas=int(paginas),
            segundos_por_pagina=relogio.total / n,
            etapas=etapas,
            chamadas={nome: relogio.chamadas.get(nome, 0) / n for nome in NOMES},
        )

    @property
    def maior_etapa(self) -> str:
        """A etapa que mais custa. Vazia só quando nada rodou."""
        sem_residuo = {k: v for k, v in self.etapas.items() if k != RESIDUO}
        return max(sem_residuo, key=lambda k: sem_residuo[k], default="")

    def para_json(self) -> dict[str, object]:
        return {
            "paginas": self.paginas,
            "segundos_por_pagina": round(self.segundos_por_pagina, 4),
            "etapas": {nome: round(valor, 4) for nome, valor in self.etapas.items()},
            "chamadas": {nome: round(valor, 2) for nome, valor in self.chamadas.items()},
        }


def horas_para_o_acervo(segundos_por_pagina: float, paginas: int = PAGINAS_DO_ACERVO) -> float:
    """A segunda unidade do relatório. Ver `PAGINAS_DO_ACERVO` para o que o padrão vale."""
    return segundos_por_pagina * max(0, int(paginas)) / 3600.0


# --------------------------------------------------------------------------------------
# A política, escolhida pelo fator e não pelo gosto
# --------------------------------------------------------------------------------------

POLITICAS: tuple[tuple[str, float, str], ...] = (
    ("varredura", 1.5, "texto em toda varredura"),
    ("sob-demanda", 4.0, "texto sob demanda, por página"),
    ("comando-separado", float("inf"), "texto como comando separado, fora da varredura"),
)
"""`(chave, teto do fator, o que ela quer dizer)` -- a tabela da S-215, como dado.

Os dois cortes são da spec e não foram remedidos aqui: 1,5x é o quanto uma varredura suporta
crescer sem virar outra decisão de agenda, e 4x é onde uma noite vira duas."""


def politica_para(fator: float) -> tuple[str, str]:
    """`(chave, frase)` da política que este fator escolhe. Ver `POLITICAS`.

    **O fator entra pronto, e vem de uma divisão medida na mesma corrida** -- página com texto
    sobre página sem texto. Dividir por um número de outro dia mediria a máquina.
    """
    for chave, teto, frase in POLITICAS:
        if fator <= teto:
            return (chave, frase)
    return POLITICAS[-1][0], POLITICAS[-1][2]  # pragma: no cover - o último teto é infinito


# --------------------------------------------------------------------------------------
# A trava: regressao de desempenho e regressao
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Piora:
    """Uma etapa que ficou mais cara que o arquivado, além da margem."""

    onde: str
    antes: float
    agora: float

    @property
    def fator(self) -> float:
        return float("inf") if self.antes <= 0 else self.agora / self.antes

    def __str__(self) -> str:
        return f"{self.onde}: {self.antes:.4f} s -> {self.agora:.4f} s ({self.fator:.2f}x)"


TOTAL = "segundos_por_pagina"
"""A chave que `comparar` sempre olha, esteja ou não a etapa no arquivo antigo."""


def comparar(
    baseline: Mapping[str, object],
    atual: Perfil,
    *,
    margem: float = MARGEM_PADRAO,
) -> list[Piora]:
    """O que piorou além da margem. Lista vazia é passe livre.

    **O total vem primeiro, e ele sozinho decide o código de saída de quem chama.** As etapas
    entram depois porque elas dizem *onde*, e porque uma etapa pode piorar enquanto outra melhora
    sem que a página custe mais -- o que é otimização, não regressão. Uma etapa que existe agora e
    não existia no arquivo é ignorada em silêncio: ela é etapa nova, e comparar contra zero
    acusaria toda medição que declarasse uma.

    `baseline` é o dicionário que `Perfil.para_json` gravou, e não um `Perfil`: o arquivo é a
    fonte, e reconstruir o objeto só para desmontá-lo de novo esconderia o caso do arquivo
    truncado, que aqui simplesmente não acusa nada.
    """
    limite = 1.0 + max(0.0, float(margem))
    achados: list[Piora] = []

    antes_total = _numero(baseline.get(TOTAL))
    if antes_total > 0 and atual.segundos_por_pagina > antes_total * limite:
        achados.append(Piora(TOTAL, antes_total, atual.segundos_por_pagina))

    etapas_antes = baseline.get("etapas")
    if isinstance(etapas_antes, Mapping):
        for nome, valor in sorted(atual.etapas.items()):
            if nome == RESIDUO or nome not in etapas_antes:
                continue
            antes = _numero(etapas_antes.get(nome))
            if antes > 0 and valor > antes * limite:
                achados.append(Piora(nome, antes, valor))
    return achados


def _numero(valor: object) -> float:
    """Float do que veio do JSON, e `0.0` para o que não é número.

    Zero é "não dá para comparar", e `comparar` pula tudo que sai zero daqui: um arquivo de
    baseline com campo faltando ou estragado não pode reprovar uma medição sã."""
    try:
        return float(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
