"""A base de caractere no disco: varrer, agrupar a cópia exata, e partir sem deixar vazar (S-202/S-203).

**Este módulo é a S-203 reduzida ao que a pasta permite, e a redução é o achado.** A S-203 pede
split *por livro*, porque uma fonte nova é um livro novo e é isso que mede generalização. Os
recortes de `training_data/` não têm livro: o nome é um UUID puro
(`00001b60-272a-46f2-9dbf-044fe779e336.png`), não há sidecar, não há índice em lugar nenhum, e o
`mtime` não serve de substituto -- 70% dos arquivos carregam a data de 2026-02-16, de uma
migração em massa que reescreveu todos de uma vez.

Consequência, e ela é declarada aqui em vez de ficar implícita num número bonito: **o teste do
"livro novo" não existe nesta base**, e nenhuma acurácia medida sobre ela mede generalização de
fonte. O que este módulo entrega é o degrau abaixo -- o grupo de cópia exata --, que é a parte
do vazamento que dá para eliminar com certeza.

**O que a cópia exata custa e o que ela compra.** Em PDF digital o mesmo glifo sai byte a byte
igual toda vez, e uma base coletada de livros digitais enche de cópias. Sem agrupar, a mesma
imagem cai no treino e no teste, e o modelo mede a própria memória. Agrupar por SHA-256 do
conteúdo do arquivo custa uma passada de leitura -- que já estava sendo paga para decodificar --
e fecha essa porta inteira. O que sobra aberto é a **quase**-duplicata (o mesmo `e` da mesma
fonte em páginas diferentes, que difere em um pixel de antialiasing), e a S-202 é quem a fecha.

**A cópia exata não é apagada nem movida.** A S-202 é explícita: quarentena, nunca lixo. Aqui
nem isso -- ela continua no disco e continua entrando no treino, porque repetição não faz mal a
quem aprende; ela só não pode *atravessar* o split. É por isso que a saída de `varrer` traz
`grupos` e não uma base já podada.

**A leitura nunca usa `cv2.imread`.** É lei neste projeto e vem de um acidente do projeto de
origem: no Windows o `imread`/`imwrite` falha em caminho não-ASCII e devolve `None`/`False`,
indistinguível de "arquivo corrompido" -- e a primeira versão da migração de lá caiu nisso e
apagou PNGs válidos. Aqui a leitura é `open()` + `cv2.imdecode`, e um PNG ilegível é **contado e
nomeado**, não apagado e não fatal.

**O redimensionamento é o mesmo do `modelo.py`, e não pode divergir.** Lá a inferência faz
`cvtColor` -> `resize(32, 32)` -> `/255`, sem preservar proporção. Boa parte dos recortes já
está em 32x32, mas não todos (há `26x35`, `37x9`, `3x20`), e preservar proporção aqui faria o
treino ver uma imagem que a inferência nunca produz. A polaridade também fica como está no
disco: tinta escura sobre papel claro, cinza cru, não binarizado e não invertido.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .classes import NomeDePastaInvalido, char_to_folder, folder_to_char
from .modelo import LADO

logger = logging.getLogger(__name__)

TAREFAS_PADRAO = 16
"""Threads da varredura.

Threads e não processos: o trabalho é leitura de arquivo e `cv2`, e os dois soltam a GIL. Medido
nesta base, 608.407 recortes: 466/s em uma thread (22 min), 8.754/s em dezesseis (1,2 min).
Processos dariam o mesmo ganho e custariam o `spawn` do Windows dentro de teste."""

TREINO, VALIDACAO, TESTE = 0, 1, 2
"""Os três lados do split, como índice. `split_por_grupo` devolve um vetor destes."""


class BaseVazia(RuntimeError):
    """A pasta não tem classe nenhuma legível. Levanta em vez de treinar em nada."""


@dataclass(frozen=True)
class Classe:
    """Uma pasta da base, já decodificada para o caractere que ela ensina."""

    pasta: str
    caractere: str
    total: int
    ilegiveis: int


@dataclass
class Varredura:
    """A base inteira em memória, mais o que a leitura encontrou pelo caminho.

    `X` são os recortes já em 32x32 e achatados (`uint8`, `(n, 1024)`); 608 mil deles ocupam
    623 MB, que cabe em RAM e evita reler o disco a cada época.
    """

    X: np.ndarray
    y: np.ndarray
    grupos: np.ndarray
    classes: list[Classe]
    dims: np.ndarray = field(default_factory=lambda: np.empty((0, 2), np.int16))
    """`(n, 2)` com a altura e a largura **nativas** de cada recorte, antes do redimensionamento.

    `(0, 0)` marca "não se sabe". Nesta base 58% dos recortes chegaram já em 32x32 da origem, e
    para eles a altura e a proporção não são informação -- são o valor que a normalização impôs.
    Ver `ler_recorte` e `dedupe.agrupar`."""

    ilegiveis: list[str] = field(default_factory=list)
    pastas_indecifraveis: list[str] = field(default_factory=list)

    @property
    def alfabeto(self) -> list[str]:
        """Os caracteres, em ordem de índice de classe."""
        return [c.caractere for c in self.classes]

    @property
    def total(self) -> int:
        return int(self.X.shape[0])

    @property
    def copias_exatas(self) -> int:
        """Quantos recortes são cópia byte a byte de outro já visto."""
        return self.total - int(np.unique(self.grupos).size)


def ler_recorte(
    caminho: Path | str, lado: int = LADO
) -> tuple[bytes, np.ndarray | None, tuple[int, int]]:
    """`(conteúdo, recorte em cinza `lado`x`lado`, dimensão nativa)`. A imagem é `None` se não decodifica.

    Devolve os bytes junto porque quem chama precisa deles para o hash de cópia exata, e relê-los
    depois dobraria a passada mais cara da varredura.

    **A dimensão nativa é devolvida porque o redimensionamento a destrói, e ela é informação.**
    A S-202 manda a proporção e a altura entrarem "por fora" do descritor -- e nesta base elas só
    existem para 42% dos recortes: 58% já chegaram em 32x32 da origem, e 167 das 314 classes
    misturam os dois regimes. `(0, 0)` marca "não se sabe" e é o que `dedupe` respeita.
    """
    with open(caminho, "rb") as arquivo:
        bruto = arquivo.read()
    imagem = cv2_imdecode_cinza(bruto)
    if imagem is None:
        return bruto, None, (0, 0)
    nativa = (int(imagem.shape[0]), int(imagem.shape[1]))
    if imagem.shape != (lado, lado):
        import cv2

        imagem = cv2.resize(imagem, (lado, lado), interpolation=cv2.INTER_AREA)
    return bruto, imagem, nativa


def cv2_imdecode_cinza(bruto: bytes) -> np.ndarray | None:
    """`bytes` -> cinza, ou `None`. O ponto de entrada único para a regra de nunca usar `imread`."""
    import cv2

    if not bruto:
        return None
    imagem = cv2.imdecode(np.frombuffer(bruto, np.uint8), cv2.IMREAD_GRAYSCALE)
    return imagem


def _varrer_pasta(
    caminho: Path, lado: int, tarefas: int
) -> tuple[np.ndarray, list[bytes], np.ndarray, list[str]]:
    """Uma classe: `(recortes (n, lado*lado), hashes, dimensões nativas, nomes ilegíveis)`."""
    import cv2

    cv2.setNumThreads(1)  # o paralelismo é nosso, e aninhá-lo derruba a taxa
    nomes = sorted(os.listdir(caminho))

    def um(nome: str) -> tuple[str, bytes | None, np.ndarray | None, tuple[int, int]]:
        try:
            bruto, imagem, nativa = ler_recorte(caminho / nome, lado)
        except OSError:
            return nome, None, None, (0, 0)
        return nome, hashlib.sha256(bruto).digest(), imagem, nativa

    recortes: list[np.ndarray] = []
    hashes: list[bytes] = []
    dims: list[tuple[int, int]] = []
    ilegiveis: list[str] = []
    with ThreadPoolExecutor(max(1, tarefas)) as executor:
        for nome, digest, imagem, nativa in executor.map(um, nomes, chunksize=256):
            if imagem is None or digest is None:
                ilegiveis.append(f"{caminho.name}/{nome}")
                continue
            recortes.append(imagem.reshape(-1))
            hashes.append(digest)
            dims.append(nativa)

    if not recortes:
        return np.empty((0, lado * lado), dtype=np.uint8), [], np.empty((0, 2), np.int16), ilegiveis
    return (
        np.stack(recortes).astype(np.uint8, copy=False),
        hashes,
        np.asarray(dims, dtype=np.int16),
        ilegiveis,
    )


def varrer(
    base: Path,
    *,
    lado: int = LADO,
    tarefas: int = TAREFAS_PADRAO,
    minimo: int = 1,
    progresso: Callable[[str, int, int], None] | None = None,
) -> Varredura:
    """Lê a base inteira para a memória e agrupa as cópias exatas.

    `minimo` descarta classes abaixo do corte -- 0 ou 1 mantém tudo, que é o padrão. Pasta cujo
    nome não decodifica para caractere **não vira classe**: ela é listada como achado, porque
    devolver `"?"` em silêncio é o defeito que fez 127 amostras treinarem a classe errada por
    meses no projeto de origem.
    """
    base = Path(base)
    pastas = sorted(p for p in base.iterdir() if p.is_dir())
    if not pastas:
        raise BaseVazia(f"{base} não tem nenhuma pasta de classe.")

    blocos: list[np.ndarray] = []
    blocos_dims: list[np.ndarray] = []
    rotulos: list[np.ndarray] = []
    classes: list[Classe] = []
    ilegiveis: list[str] = []
    indecifraveis: list[str] = []
    hash_para_grupo: dict[bytes, int] = {}
    grupos: list[int] = []

    for posicao, pasta in enumerate(pastas):
        if progresso is not None:
            progresso(pasta.name, posicao + 1, len(pastas))
        try:
            caractere = folder_to_char(pasta.name, strict=True)
        except NomeDePastaInvalido:
            indecifraveis.append(pasta.name)
            continue
        if char_to_folder(caractere) != pasta.name:
            # A ida-e-volta é o que separa "nome de classe" de "pasta que caiu aqui". O
            # `folder_to_char` tem um ramo de compatibilidade que devolve o próprio nome quando
            # não reconhece o prefixo -- útil no formato antigo, e o bastante para uma pasta
            # solta virar classe calada. Fechar a volta é o teste que a S-180 já aplica ao
            # metadado, aqui aplicado ao disco.
            indecifraveis.append(pasta.name)
            continue

        recortes, hashes, dims_da_classe, sem_ler = _varrer_pasta(pasta, lado, tarefas)
        ilegiveis.extend(sem_ler)
        if recortes.shape[0] == 0:
            # Classe vazia é achado nomeado (S-200): a `lower_ä` de lá ficou assim porque
            # `cv2.imwrite` devolve `False` em caminho não-ASCII, sem levantar.
            logger.warning("Classe %s está vazia (%d ilegíveis).", pasta.name, len(sem_ler))
            continue
        if recortes.shape[0] < minimo:
            logger.info("Classe %s ficou de fora: %d recortes, mínimo %d.", pasta.name, recortes.shape[0], minimo)
            continue

        indice = len(classes)
        classes.append(Classe(pasta.name, caractere, int(recortes.shape[0]), len(sem_ler)))
        blocos.append(recortes)
        blocos_dims.append(dims_da_classe)
        rotulos.append(np.full(recortes.shape[0], indice, dtype=np.int32))
        for digest in hashes:
            grupo = hash_para_grupo.get(digest)
            if grupo is None:
                grupo = len(hash_para_grupo)
                hash_para_grupo[digest] = grupo
            grupos.append(grupo)

    if not classes:
        raise BaseVazia(f"{base} não produziu nenhuma classe utilizável.")

    return Varredura(
        X=np.concatenate(blocos),
        y=np.concatenate(rotulos),
        grupos=np.asarray(grupos, dtype=np.int32),
        classes=classes,
        dims=np.concatenate(blocos_dims),
        ilegiveis=ilegiveis,
        pastas_indecifraveis=indecifraveis,
    )


def grupos_em_conflito(y: np.ndarray, grupos: np.ndarray) -> np.ndarray:
    """Os grupos cuja **mesma imagem, byte a byte** está arquivada sob mais de um rótulo.

    Medido nesta base: 83 grupos, 1.557 recortes -- e os pares são a lista de homóglifos que se
    espera de material de livro: `digit_1`×`lower_l` (13 grupos), `lower_v`×`upper_V` (7),
    `digit_0`×`lower_o` (6), `sym_39`×`sym_44` (5, a apóstrofe e a vírgula).

    **Isto não é duplicata: é rótulo que se contradiz.** As duas cópias não podem estar as duas
    certas, e nenhum modelo pode acertar as duas. É a mesma família do acidente que fez `sym_f7`
    guardar 127 imagens da casa de xadrez `f7` colidindo com o `?` de `sym_63` -- lá o conserto
    do rótulo fez o modelo já treinado acertar 127 de 127.

    Elas continuam no treino, porque tirar 1.557 recortes que a base declara não conserta a
    contradição. O que `split_por_grupo` faz é mantê-las **fora de validação e de teste**: medir
    contra um rótulo que se contradiz produz um erro que não é do modelo.
    """
    ordem = np.argsort(grupos, kind="stable")
    g_ordenado, y_ordenado = grupos[ordem], y[ordem]
    if g_ordenado.size == 0:
        return np.empty(0, dtype=grupos.dtype)
    cortes = np.flatnonzero(np.diff(g_ordenado)) + 1
    culpados = [
        int(g_ordenado[inicio])
        for inicio, fim in zip(np.r_[0, cortes], np.r_[cortes, g_ordenado.size], strict=True)
        if np.unique(y_ordenado[inicio:fim]).size > 1
    ]
    return np.asarray(culpados, dtype=grupos.dtype)


def representantes(grupos: np.ndarray) -> np.ndarray:
    """Máscara com **um** recorte por grupo de cópia exata. O primeiro de cada grupo.

    É o que validação e teste medem. Sem isso, `lower_a` -- 91% de cópia -- entra na conta com
    peso 63.055 quando o que ela tem de distinto são 5.683 imagens, e a métrica passa a ser a
    contagem de cópias e não o acerto.
    """
    mascara = np.zeros(grupos.shape[0], dtype=bool)
    _, primeiros = np.unique(grupos, return_index=True)
    mascara[primeiros] = True
    return mascara


def split_por_grupo(
    y: np.ndarray,
    grupos: np.ndarray,
    *,
    fracoes: tuple[float, float, float] = (0.8, 0.1, 0.1),
    semente: int = 0,
) -> np.ndarray:
    """`(n,)` com `TREINO`/`VALIDACAO`/`TESTE`. Nenhum grupo aparece em dois lados.

    **Atômico por grupo, e o grupo é global.** A versão que estratificava classe a classe deixava
    28 grupos em dois lados nesta base, porque um grupo pode pertencer a **duas** classes -- ver
    `grupos_em_conflito`. O sorteio aqui atribui cada grupo uma vez só, e o grupo contraditório é
    travado no treino antes de qualquer sorteio.

    **Classe pequena cai toda no treino, de propósito.** Com menos de três grupos não há como
    tirar validação sem esvaziar o treino, e uma classe de 1 recorte é exatamente o caso: ela
    entra no modelo (o rótulo passa a ser emitível) e **não** aparece em nenhuma medição. Quem lê
    o número final precisa saber disso, e é `contagem_por_lado` que mostra.
    """
    if y.shape != grupos.shape:
        raise ValueError(f"y tem {y.shape} e grupos tem {grupos.shape}; são o mesmo eixo.")
    if not all(f >= 0 for f in fracoes) or sum(fracoes) <= 0:
        raise ValueError(f"frações inválidas: {fracoes}")

    aleatorio = np.random.default_rng(semente)
    lado = np.full(y.shape[0], TREINO, dtype=np.int8)
    _, val_frac, teste_frac = (f / sum(fracoes) for f in fracoes)

    travados = set(grupos_em_conflito(y, grupos).tolist())
    destino_do_grupo: dict[int, int] = dict.fromkeys(travados, TREINO)

    for classe in np.unique(y):
        da_classe = np.flatnonzero(y == classe)
        livres = np.array(
            sorted({int(g) for g in np.unique(grupos[da_classe])} - destino_do_grupo.keys()),
            dtype=np.int64,
        )
        if livres.size < 3:
            # Menos de três grupos livres: não dá para ter treino, validação e teste ao mesmo
            # tempo, e o treino é o que não pode faltar.
            continue
        embaralhados = aleatorio.permutation(livres)
        n_teste = max(1, int(round(embaralhados.size * teste_frac)))
        n_val = max(1, int(round(embaralhados.size * val_frac)))
        if n_teste + n_val >= embaralhados.size:
            n_teste = n_val = 1
        for grupo in embaralhados[:n_teste]:
            destino_do_grupo[int(grupo)] = TESTE
        for grupo in embaralhados[n_teste : n_teste + n_val]:
            destino_do_grupo[int(grupo)] = VALIDACAO

    if destino_do_grupo:
        chaves = np.fromiter(destino_do_grupo.keys(), dtype=np.int64, count=len(destino_do_grupo))
        valores = np.fromiter(destino_do_grupo.values(), dtype=np.int8, count=len(destino_do_grupo))
        ordem = np.argsort(chaves)
        posicao = np.searchsorted(chaves[ordem], grupos)
        posicao = np.clip(posicao, 0, chaves.size - 1)
        casou = chaves[ordem][posicao] == grupos
        lado[casou] = valores[ordem][posicao][casou]

    return lado


def contagem_por_lado(y: np.ndarray, lado: np.ndarray, n_classes: int) -> np.ndarray:
    """`(n_classes, 3)` com quantos recortes de cada classe caíram em cada lado."""
    tabela = np.zeros((n_classes, 3), dtype=np.int64)
    for destino in (TREINO, VALIDACAO, TESTE):
        indices, contagens = np.unique(y[lado == destino], return_counts=True)
        tabela[indices, destino] = contagens
    return tabela


def vazamento(grupos: np.ndarray, lado: np.ndarray) -> list[int]:
    """Os grupos que aparecem em mais de um lado. Vazio é o que se espera de `split_por_grupo`.

    Existe para ser chamado *depois* do split e virar critério de aceite, e não para ser
    confiança: a S-203 pede um relatório de vazamento que rode de verdade, porque a garantia que
    ninguém confere é a que quebra calada.
    """
    culpados: list[int] = []
    ordem = np.argsort(grupos, kind="stable")
    g_ordenado, l_ordenado = grupos[ordem], lado[ordem]
    inicio = 0
    for fim in range(1, g_ordenado.size + 1):
        if fim == g_ordenado.size or g_ordenado[fim] != g_ordenado[inicio]:
            if np.unique(l_ordenado[inicio:fim]).size > 1:
                culpados.append(int(g_ordenado[inicio]))
            inicio = fim
    return culpados


def gravar_cache(caminho: Path, varredura: Varredura) -> None:
    """Guarda a varredura para não repetir a passada de disco. ~600 MB, e fica fora do git.

    **O split não entra aqui, e a ausência é deliberada.** Ele é função pura de `(y, grupos,
    frações, semente)` e custa um segundo para refazer; guardá-lo criaria a única coisa que um
    cache não pode ter, que é estado capaz de envelhecer em silêncio. A primeira versão o
    guardava, e a consequência apareceu na primeira corrida: um conserto no `split_por_grupo`
    não alcançava o cache, e o comando ia treinar sobre o split defeituoso -- só não foi porque
    a trava de vazamento o barrou.
    """
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        caminho,
        X=varredura.X,
        y=varredura.y,
        grupos=varredura.grupos,
        dims=varredura.dims,
        pastas=np.array([c.pasta for c in varredura.classes]),
        caracteres=np.array([c.caractere for c in varredura.classes]),
        ilegiveis=np.array(varredura.ilegiveis),
        indecifraveis=np.array(varredura.pastas_indecifraveis),
    )


def ler_cache(caminho: Path) -> Varredura:
    """A volta de `gravar_cache`. O split é refeito por quem chama -- ver lá o porquê."""
    dados = np.load(Path(caminho), allow_pickle=False)
    pastas = [str(p) for p in dados["pastas"]]
    caracteres = [str(c) for c in dados["caracteres"]]
    y = dados["y"]
    classes = [
        Classe(pasta, caractere, int((y == i).sum()), 0)
        for i, (pasta, caractere) in enumerate(zip(pastas, caracteres, strict=True))
    ]
    varredura = Varredura(
        X=dados["X"],
        y=y,
        grupos=dados["grupos"],
        classes=classes,
        dims=dados["dims"] if "dims" in dados.files else np.zeros((y.size, 2), np.int16),
        ilegiveis=[str(x) for x in dados["ilegiveis"]],
        pastas_indecifraveis=[str(x) for x in dados["indecifraveis"]],
    )
    return varredura


def resumo(varredura: Varredura, iteravel: Iterable[Classe] | None = None) -> str:
    """Uma linha por número que decide, em pt-BR. Para o log e para a tela."""
    classes = list(iteravel if iteravel is not None else varredura.classes)
    contagens = np.array([c.total for c in classes])
    linhas = [
        f"{varredura.total:,} recortes em {len(classes)} classes".replace(",", "."),
        f"cópias exatas: {varredura.copias_exatas:,}".replace(",", "."),
        f"mediana por classe: {int(np.median(contagens))}",
        f"classes com menos de 20: {int((contagens < 20).sum())}",
    ]
    if varredura.ilegiveis:
        linhas.append(f"PNGs ilegíveis: {len(varredura.ilegiveis)}")
    if varredura.pastas_indecifraveis:
        linhas.append(f"pastas que não decodificam: {len(varredura.pastas_indecifraveis)}")
    return " | ".join(linhas)


__all__ = [
    "TAREFAS_PADRAO",
    "TESTE",
    "TREINO",
    "VALIDACAO",
    "BaseVazia",
    "Classe",
    "Varredura",
    "contagem_por_lado",
    "grupos_em_conflito",
    "gravar_cache",
    "ler_cache",
    "ler_recorte",
    "representantes",
    "resumo",
    "split_por_grupo",
    "varrer",
    "vazamento",
]
