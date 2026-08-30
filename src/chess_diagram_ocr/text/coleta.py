"""A coleta em quarentena: o que o modelo não soube ler vira material, com um humano no meio (S-214).

**O que se perde hoje.** Quando um livro inteiro passa pela extração, o modelo já diz onde é
fraco: são os caracteres abaixo do piso de confiança. Medido no projeto de origem, **3.943 deles
em 264 páginas** -- material de treino que é jogado fora e que teria de ser recaçado na tela, um
a um.

## O fluxo tem três etapas, e a do meio é humana

    extração  ──►  revisao_ocr/<palpite>/  ──►  [você olha]  ──►  base de treino

Corrigir um rótulo é **mover o arquivo de pasta**; descartar é apagá-lo. `promover` lê o nome da
pasta como rótulo -- então o que a pessoa fez com o mouse é o que entra na base, e não o que o
modelo achou.

**Gravar direto em `<palpite>/` seria treinar o modelo no próprio erro**, e é a regra nº 2 da
`SPEC_TEXTO`. As duas pontas deste projeto têm a cicatriz: lá, 127 amostras mal rotuladas
treinaram a classe errada sem ninguém notar; aqui, a verdade de referência contaminada é o achado
nº 1 da avaliação de agosto. Por isso `coletar` **não conhece o caminho da base de treino** -- não
é disciplina de quem usa, é falta de argumento na função.

## Três coisas que a experiência de lá mediu, e que entram desde o início

**1. A mesma renderização entrava muitas vezes.** Em PDF digital o mesmo glifo sai byte a byte
igual, e a pasta enchia de cópias -- 300 miniaturas iguais são 300 chances a menos de o intruso
aparecer. Aqui a dedução é dupla: impressão exata (SHA-256, como `dataset.varrer`) **e**
quase-duplicata dentro do mesmo palpite (o descritor da S-202, `dedupe.LIMIAR_PADRAO`). A segunda
pega o mesmo glifo rasterizado com meio pixel de deslocamento, que o hash não vê.

**2. O teto guardava os primeiros N, que são as primeiras páginas.** Teto de 300 dava 300
amostras das páginas 1 a 5: uma fonte, um estado de digitalização, quase sempre rosto e sumário.
Com **amostragem de reservatório**, o que fica é uma amostra do *livro* -- e o teste que trava
isso não olha o código, olha a distribuição de páginas do que sobrou.

**3. "Mais duvidoso primeiro" não funcionava**, porque o nome do arquivo carregava página e
confiança nessa ordem, e o Explorer ordena por nome -- isto é, por página. Aqui a confiança vem
**primeiro**, em milésimos com zeros à esquerda, e ordenar a pasta por nome é ordenar por dúvida.

## O que a promoção registra, e por que isso destrava meio item

`promover` escreve em `data/texto_procedencia.csv` com procedência `humano` (S-201) -- livro,
página e data inclusive, porque o nome do arquivo os carrega. É o que faltava: a S-201 e a S-203
estão paradas porque os 608 mil recortes que já existem têm **UUID puro** e a origem se perdeu.
Isso continua sendo pergunta para o dono dos dados. O que este item resolve é o daqui para a
frente: toda amostra que entrar por aqui entra com procedência, e `Registro.mede` passa a poder
dizer a verdade sobre ela.

Medido lá, no modo "todos": dos arquivos que caem em `revisao_ocr/lower_o/`, **93,7% são um `o`**,
2,6% são outro caractere e 3,7% não têm caractere nenhum ali -- é por isso que a etapa do meio
existe, e é por isso que ela é barata: a maioria já está na pasta certa.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from ..atomic_io import write_image
from ..config import PROJECT_ROOT
from . import procedencia as _procedencia
from .classes import NomeDePastaInvalido, char_to_folder, folder_to_char
from .dedupe import LIMIAR_PADRAO, descritor

logger = logging.getLogger(__name__)

PASTA_PADRAO = PROJECT_ROOT / "revisao_ocr"
"""Onde a quarentena mora. **Fora de `training_data/`, e isso é o item.**

Uma subpasta da base de treino seria a mesma coisa que gravar na base: qualquer varredura que
percorresse `training_data/*/` a leria como classe."""

TETO_PADRAO = 300
"""Quantos recortes por palpite a coleta guarda. Ver "O teto guardava os primeiros N"."""

LADO = 32
"""O lado do recorte gravado, o mesmo de `dataset.LADO`: a quarentena alimenta aquela base."""


@dataclass(frozen=True)
class Recorte:
    """Um caractere que o modelo leu mal, com de onde ele veio.

    `livro` e `pagina` viajam com ele porque são o que a promoção grava como procedência -- e
    porque a base de 608 mil não os tem, o que é justamente o que trava a S-201 e a S-203.
    """

    imagem: np.ndarray
    palpite: str
    confianca: float
    livro: str = ""
    pagina: int = 0

    @property
    def pasta(self) -> str:
        """`lower_o`, `digit_1`, `sym_46`... O nome de pasta do palpite, pela régua da S-180."""
        return char_to_folder(self.palpite)

    @property
    def impressao(self) -> str:
        """SHA-256 dos bytes do recorte. A dedução exata, a mesma de `dataset.varrer`."""
        return hashlib.sha256(np.ascontiguousarray(self.imagem).tobytes()).hexdigest()

    def nome(self) -> str:
        """`0123_livro_p045_<impressão>.png` -- **a confiança primeiro**, e é o item.

        Ordenar a pasta por nome passa a ser ordenar por dúvida. Com página na frente, como era
        lá, o Explorer agrupava por página e "mais duvidoso primeiro" não funcionava.

        A impressão entra no fim como identidade: ela é a chave que `promover` grava no CSV de
        procedência, e dois recortes idênticos que escapassem da dedução colidiriam de propósito
        em vez de virarem dois arquivos iguais com nomes diferentes.
        """
        milesimos = max(0, min(999, int(round(float(self.confianca) * 1000))))
        livro = _sem_caractere_estranho(self.livro) or "sem-livro"
        return f"{milesimos:04d}_{livro}_p{int(self.pagina):04d}_{self.impressao[:16]}.png"


def _sem_caractere_estranho(valor: str) -> str:
    """O nome do livro reduzido ao que um nome de arquivo aceita nos três sistemas."""
    limpo = "".join(c if (c.isalnum() or c in "-_") else "-" for c in valor.strip())
    while "--" in limpo:
        limpo = limpo.replace("--", "-")
    return limpo.strip("-")[:40]


@dataclass
class Relatorio:
    """O que a coleta fez. Vai para o log e para a tela de quem varreu o livro."""

    vistos: int = 0
    gravados: int = 0
    repetidos_exatos: int = 0
    repetidos_parecidos: int = 0
    descartados_pelo_teto: int = 0
    por_pasta: dict[str, int] = field(default_factory=dict)

    @property
    def pastas(self) -> int:
        return len(self.por_pasta)

    def __str__(self) -> str:
        return (
            f"{self.vistos} recorte(s) abaixo do piso; {self.gravados} gravado(s) em "
            f"{self.pastas} pasta(s); {self.repetidos_exatos} cópia(s) exata(s) e "
            f"{self.repetidos_parecidos} quase-duplicata(s) recusada(s); "
            f"{self.descartados_pelo_teto} fora pelo teto"
        )


class _Reservatorio:
    """Amostragem de reservatório por palpite: o que fica é uma amostra do **livro**.

    O algoritmo é o R clássico: os primeiros `teto` entram; o `k`-ésimo (base 1) entra com
    probabilidade `teto/k`, no lugar de um sorteado. A propriedade que importa aqui é que a
    amostra final é uniforme sobre o **fluxo inteiro**, e não sobre o começo dele -- que é o
    defeito nº 2 do cabeçalho, e o que `test_o_teto_sorteia_do_livro_inteiro` cobra.

    **A semente é argumento e não `default_rng()` puro** porque um teste sobre distribuição
    precisa de corrida reproduzível, e porque duas varreduras do mesmo livro que produzissem
    amostras diferentes não teriam como ser comparadas.
    """

    def __init__(self, teto: int, semente: int) -> None:
        self._teto = max(0, int(teto))
        self._aleatorio = np.random.default_rng(semente)
        self._itens: list[Recorte] = []
        self.vistos = 0
        self.recusados = 0

    def oferecer(self, recorte: Recorte) -> None:
        self.vistos += 1
        if self._teto == 0:
            self.recusados += 1
            return
        if len(self._itens) < self._teto:
            self._itens.append(recorte)
            return
        sorteado = int(self._aleatorio.integers(0, self.vistos))
        if sorteado < self._teto:
            self._itens[sorteado] = recorte
        self.recusados += 1

    @property
    def itens(self) -> list[Recorte]:
        return list(self._itens)


def coletar(
    recortes: Iterable[Recorte],
    destino: Path | str = PASTA_PADRAO,
    *,
    teto: int = TETO_PADRAO,
    semente: int = 0,
    limiar_de_parecido: float = LIMIAR_PADRAO,
) -> Relatorio:
    """Grava os recortes duvidosos em `destino/<palpite>/`, deduplicados e com teto sorteado.

    **Não recebe o caminho da base de treino, e não é esquecimento.** Escrever em
    `training_data/` a partir daqui seria treinar o modelo no palpite dele mesmo, e a forma de
    garantir que isso não aconteça não é lembrar de não fazer: é a função não ter como.
    `test_a_coleta_nunca_grava_na_base_de_treino` afirma isso sobre o disco, não sobre a intenção.

    Quem filtra pelo piso de confiança é quem chama. Este módulo grava o que lhe derem: o piso é
    política da varredura (e a `documento.corte_de_revisar` já a declara num lugar só), e
    duplicá-la aqui daria dois cortes para a mesma decisão.

    **A gravação é `atomic_io.write_image`, e não `cv2.imwrite` (S-431).** Era `cv2.imwrite` até
    aqui, e o defeito é exatamente o do item 3 de `text/classes.py`: em caminho que a code page
    ANSI não representa o `imwrite` devolve `False` **sem levantar**, e a linha seguinte soma
    `len(guardados)` sem olhar o retorno -- então o `Relatorio` saía dizendo "5 gravado(s)" com
    zero PNG no disco. O destino padrão é `PROJECT_ROOT / "revisao_ocr"`, de modo que bastava a
    pasta do projeto -- ou a do bundle que o usuário descompacta -- morar sob um nome com acento
    para a coleta inteira se perder em silêncio.

    O `write_image` levanta `OSError`, e é essa a troca: **uma coleta que para vale mais que um
    relatório que mente**. Quem chamar daqui em diante tem de tratar `OSError` -- hoje não há
    chamador de produção, e é por isso que a hora de mudar é esta.
    """
    pasta = Path(destino)
    relatorio = Relatorio()
    reservatorios: dict[str, _Reservatorio] = {}
    impressoes: set[str] = set()
    parecidos: dict[str, list[np.ndarray]] = {}

    for recorte in recortes:
        relatorio.vistos += 1
        if recorte.impressao in impressoes:
            relatorio.repetidos_exatos += 1
            continue
        chave = recorte.pasta
        assinatura = descritor(np.asarray(recorte.imagem, np.uint8).reshape(1, -1), lado_origem=LADO)[0]
        if _ja_visto_parecido(assinatura, parecidos.get(chave, []), limiar_de_parecido):
            relatorio.repetidos_parecidos += 1
            continue

        impressoes.add(recorte.impressao)
        parecidos.setdefault(chave, []).append(assinatura)
        reservatorios.setdefault(chave, _Reservatorio(teto, semente)).oferecer(recorte)

    for chave, reservatorio in sorted(reservatorios.items()):
        alvo = pasta / chave
        alvo.mkdir(parents=True, exist_ok=True)
        guardados = reservatorio.itens
        relatorio.descartados_pelo_teto += reservatorio.recusados
        for recorte in guardados:
            write_image(alvo / recorte.nome(), np.asarray(recorte.imagem, np.uint8).reshape(LADO, LADO))
        relatorio.por_pasta[chave] = len(guardados)
        relatorio.gravados += len(guardados)

    logger.info("Coleta em quarentena: %s", relatorio)
    return relatorio


def _ja_visto_parecido(assinatura: np.ndarray, vistas: Sequence[np.ndarray], limiar: float) -> bool:
    """A quase-duplicata da S-202, dentro do mesmo palpite. Ver o item 1 do cabeçalho."""
    if not vistas:
        return False
    matriz = np.asarray(vistas, np.float32)
    distancias = np.sqrt(((matriz - assinatura[None, :]) ** 2).mean(axis=1))
    return bool((distancias <= limiar).any())


# --------------------------------------------------------------------------------------
# A promocao: o que a mao moveu e o que entra na base
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Promovido:
    """Um arquivo da quarentena pronto para entrar na base, com o que se sabe dele."""

    origem: Path
    rotulo: str
    """O caractere, lido do **nome da pasta** -- não do palpite que gravou o arquivo."""

    uuid: str
    livro: str
    pagina: int
    confianca: float


@dataclass
class Promocao:
    """O resultado de `promover`: o que entrou, o que não deu para ler, e onde foi parar."""

    promovidos: tuple[Promovido, ...] = ()
    pastas_indecifraveis: tuple[str, ...] = ()
    nomes_estranhos: tuple[str, ...] = ()
    destino: Path | None = None
    registro: Path | None = None

    def __str__(self) -> str:
        partes = [f"{len(self.promovidos)} recorte(s) promovido(s)"]
        if self.pastas_indecifraveis:
            partes.append(f"{len(self.pastas_indecifraveis)} pasta(s) sem caractere")
        if self.nomes_estranhos:
            partes.append(f"{len(self.nomes_estranhos)} nome(s) fora do padrão")
        return "; ".join(partes)


def _do_nome(nome: str) -> tuple[float, str, int, str] | None:
    """`0123_livro_p045_abcdef.png` -> `(confiança, livro, página, uuid)`, ou `None`.

    `None` para o que não veio desta coleta. **Nunca adivinha**: um arquivo que alguém copiou
    para a pasta à mão entra com livro vazio e página 0 pelo caminho de quem chama, e não com
    metade de um nome interpretada como se fosse dado.
    """
    partes = nome.split("_")
    if len(partes) < 4 or not partes[0].isdigit():
        return None
    pagina_bruta = partes[-2]
    if not (pagina_bruta.startswith("p") and pagina_bruta[1:].isdigit()):
        return None
    return (
        int(partes[0]) / 1000.0,
        "_".join(partes[1:-2]),
        int(pagina_bruta[1:]),
        partes[-1],
    )


def promover(
    pasta: Path | str = PASTA_PADRAO,
    base_de_treino: Path | str | None = None,
    *,
    registro: Path | str | None = None,
    quando: str = "",
    mover: bool = True,
) -> Promocao:
    """Leva o que está na quarentena para a base, **lendo o rótulo do nome da pasta**.

    É a terceira etapa do fluxo, e a que só acontece depois de a segunda -- humana -- ter
    acontecido: o que a pessoa moveu de `lower_c/` para `lower_e/` entra como `e`. O palpite do
    modelo não é consultado em lugar nenhum desta função, e é essa a regra nº 2 da spec.

    `base_de_treino=None` **não grava nada** e devolve o que seria promovido. É o modo de conferir
    antes, e é o padrão de propósito: uma função que escreve na base de treino não deve fazê-lo
    porque alguém esqueceu de passar um argumento.

    `mover` tira o arquivo da quarentena depois de copiá-lo. Ligado, porque um recorte que ficasse
    nos dois lugares voltaria a ser promovido na próxima passada -- e viraria duplicata na base,
    que é o que a S-202 gasta 232 linhas para desfazer.
    """
    import shutil

    origem = Path(pasta)
    resultado = Promocao(destino=Path(base_de_treino) if base_de_treino else None)
    if not origem.is_dir():
        logger.info("Quarentena vazia: %s não existe.", origem)
        return resultado

    promovidos: list[Promovido] = []
    indecifraveis: list[str] = []
    estranhos: list[str] = []
    hoje = quando or date.today().isoformat()

    for subpasta in sorted(p for p in origem.iterdir() if p.is_dir()):
        try:
            # **`strict=True`, e é o item.** Sem ele `folder_to_char` devolve o nome da pasta cru
            # para o que não decodifica -- `nao_e_classe` viraria um rótulo de 12 caracteres, e a
            # promoção o gravaria como classe. É o defeito que fez 127 amostras treinarem a classe
            # errada sem ninguém notar (S-180), com o agravante de que aqui ele criaria a pasta.
            rotulo = folder_to_char(subpasta.name, strict=True)
        except NomeDePastaInvalido:
            indecifraveis.append(subpasta.name)
            continue
        if not rotulo:
            indecifraveis.append(subpasta.name)
            continue
        for arquivo in sorted(subpasta.glob("*.png")):
            lido = _do_nome(arquivo.stem)
            if lido is None:
                estranhos.append(f"{subpasta.name}/{arquivo.name}")
                confianca, livro, pagina, uuid = (-1.0, "", 0, arquivo.stem)
            else:
                confianca, livro, pagina, uuid = lido
            promovidos.append(Promovido(arquivo, rotulo, uuid, livro, pagina, confianca))

    resultado = Promocao(
        promovidos=tuple(promovidos),
        pastas_indecifraveis=tuple(indecifraveis),
        nomes_estranhos=tuple(estranhos),
        destino=resultado.destino,
    )
    if resultado.destino is None:
        logger.info("Promoção (ensaio, nada gravado): %s", resultado)
        return resultado

    for item in promovidos:
        alvo = resultado.destino / char_to_folder(item.rotulo)
        alvo.mkdir(parents=True, exist_ok=True)
        (shutil.move if mover else shutil.copy2)(str(item.origem), str(alvo / item.origem.name))

    caminho_do_registro = _procedencia.acrescentar(
        {
            item.uuid: _procedencia.Registro(
                livro=item.livro,
                pagina=item.pagina or None,
                procedencia=_procedencia.HUMANO,
                rotulado_em=hoje,
            )
            for item in promovidos
        },
        registro,
    )
    resultado.registro = caminho_do_registro
    logger.info("Promoção: %s -> %s", resultado, resultado.destino)
    return resultado
