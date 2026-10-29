"""Importar imagens de diagrama de fora do programa para o dataset de treino.

Duas fontes, com o mesmo destino (`labels.csv` + `samples/`, pelo `append_training_sample`):

1. **O relatório do ChessMeridaOCR** (plugin do Sigil). Cada livro é uma pasta com um `.html` e uma
   subpasta `imagens/`; o HTML tem um `<article class="chessocr-entry">` por imagem, com o `src`
   da imagem e a FEN que o servidor devolveu. A FEN vem pronta, mas não conferida: o relatório
   traz tabuleiro vazio quando o servidor não leu nada, e a mesma imagem aparece em duas execuções
   com FENs diferentes. Por isso a FEN da fonte só vai direto para o dataset quando **o nosso
   modelo lê a mesma posição** no recorte (`concorda`); o resto fica pendente para conferência.
2. **Uma pasta de imagens sem FEN** (o `chessvision-jbc`, por exemplo). Nada vai para o dataset
   sem uma pessoa olhar: a proposta é a leitura do modelo, e a conferência é imagem a imagem. Se a
   pasta tiver um `index.csv` com as colunas `png` e `to_move` (o formato do jbc), o lado a jogar e
   a legenda vêm dele.

**O recorte é o ponto delicado.** As imagens do Sigil trazem coordenadas em volta, número do
diagrama à esquerda ou a seta de quem joga; as do jbc já vêm recortadas rente às casas, e nelas o
detector de página se perde e devolve três ou quatro casas ampliadas. `recortar` usa o detector e
só aceita o que ele achou quando o quadro cobre boa parte da imagem (`FRACAO_MINIMA_DO_QUADRO`);
senão a imagem inteira é o tabuleiro. A conferência deixa a pessoa trocar um pelo outro.

**O andamento é um arquivo por pasta** (`data/importacao/*.json`): 5.800 imagens não se conferem
numa sessão, e reabrir a mesma pasta tem de continuar de onde parou -- sem gravar duas vezes a
mesma imagem no dataset. A mesma imagem também cai em lotes diferentes quando se abre a pasta de um
livro e depois a de cima dela; por isso o que outro lote já decidiu vale para todos, pelo caminho
inteiro da imagem (`andamento_de_outros_lotes`).

O módulo não importa Qt nem torch no topo: a janela é de `qt/importador_de_imagens.py`, e o modelo
chega por parâmetro.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import numpy as np

from .atomic_io import atomic_write_json, read_image
from .config import BOARD_SIZE, DATA_DIR

logger = logging.getLogger(__name__)

__all__ = [
    "COM_FEN",
    "COM_PGN",
    "COM_FEN_DA_FONTE",
    "DESCARTADO",
    "EXTENSOES",
    "FRACAO_MINIMA_DO_QUADRO",
    "IMPORTADO_COM_FEN",
    "IMPORTADO_CONFERIDO",
    "PENDENTE",
    "PULADO",
    "SALVO",
    "SEM_FEN",
    "ItemDeImportacao",
    "Lote",
    "abrir_lote",
    "andamento_de_outros_lotes",
    "caminho_do_lote",
    "campo_de_pecas",
    "casas_diferentes",
    "com_a_leitura",
    "concorda",
    "gravar_item",
    "ler_imagem",
    "ler_livro_com_pgn",
    "ler_pasta_de_imagens",
    "ler_relatorios_do_chessmeridaocr",
    "recortar",
    "rota_da_conferencia",
]

COM_FEN = "com-fen"
"""Relatório do ChessMeridaOCR: cada imagem chega com a FEN do servidor."""

SEM_FEN = "sem-fen"
"""Pasta de imagens soltas: a FEN é a que a pessoa conferir."""

COM_PGN = "pdf-pgn"
"""O PDF digital e o PGN do livro numa pasta (S-593): cada diagrama casado com o seu nó chega com a
FEN do PGN e o lado a jogar dele. A imagem é a que o livro embute, nos bytes originais."""

COM_FEN_DA_FONTE = (COM_FEN, COM_PGN)
"""As origens em que a fonte traz a FEN -- onde «Importar os que concordam» faz sentido."""

PENDENTE = "pendente"
SALVO = "salvo"
PULADO = "pulado"
DESCARTADO = "descartado"
STATUS = (PENDENTE, SALVO, PULADO, DESCARTADO)

_PESO_DO_STATUS = {SALVO: 0, DESCARTADO: 1, PULADO: 2, PENDENTE: 3}
"""Quando dois lotes decidiram coisas diferentes para a mesma imagem, vale a de menor peso: o que já
está no dataset vence o descarte, e o descarte vence o pulo."""

EXTENSOES = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")

DIRETORIO_DOS_LOTES = DATA_DIR / "importacao"

VERSAO_DO_LOTE = 1

TABULEIRO_VAZIO = "8/8/8/8/8/8/8/8"

FRACAO_MINIMA_DO_QUADRO = 0.45
"""Fração da área da imagem que o quadro detectado precisa cobrir para ser o tabuleiro.

Medido nas duas fontes em 2026-10-23: em 120 imagens do Sigil o quadro cobre de 0,65 (coordenadas
dos quatro lados) a 0,98 da imagem; em 150 do jbc os acertos ficam em 0,97 a 1,0 e os recortes
errados, de três ou quatro casas, em 0,12 ou menos. Entre os dois há folga dos dois lados."""

IMPORTADO_COM_FEN = "importado-com-fen"
"""`corrected_by` da amostra que o lote gravou: relatório e modelo leram a mesma posição, e
ninguém olhou. É uma rota de máquina, como `net-remoto`, e não entra nas `ROTAS_HUMANAS`.

Mora aqui e não no vocabulário de `labels.py` pela mesma razão de `transcricao-manual` morar fora
dele: o CSV é vocabulário, não validação -- e `labels.py` está no caminho de medição, que vence os
relatórios de campo a cada mudança."""

IMPORTADO_CONFERIDO = "importado-conferido"
"""`corrected_by` da amostra conferida sem leitura do modelo para comparar (`rota_da_conferencia`)."""

RECORTE_DETECTADO = "detectado"
RECORTE_INTEIRA = "inteira"


# ------------------------------------------------------------------------------------ itens


@dataclass(frozen=True)
class ItemDeImportacao:
    """Uma imagem a importar e o que já se sabe dela."""

    imagem: str
    """Caminho relativo à pasta do lote, com `/`."""

    livro: str
    indice: int
    """Ordem da imagem no livro, a partir de 1. Vai para `source_diagram`."""

    fen_da_fonte: str = ""
    """A FEN que o relatório trouxe (só no `COM_FEN`)."""

    lado: str = ""
    """`w`, `b` ou vazio quando a fonte não diz."""

    legenda: str = ""
    """O que a fonte diz da imagem: seção do livro no Sigil, legenda no jbc."""

    motivos: tuple[str, ...] = ()
    """Por que esta imagem precisa de olho humano. Vazio é "nada contra"."""

    fen_do_modelo: str = ""
    recorte: str = ""
    status: str = PENDENTE
    amostra: str = ""
    """O PNG gravado no `samples/`, depois de salvo."""
    pagina: int = 0
    """A página do livro, a partir de 1, quando a fonte diz (o `COM_PGN`). Vai para `source_page`."""
    candidatos: tuple[str, ...] = ()
    """As FENs que a fonte admite para esta imagem, quando ela não sabe qual (o `COM_PGN`: a mesma
    legenda em duas linhas do capítulo). A leitura do modelo escolhe entre elas (`com_a_leitura`)."""

    @property
    def precisa_de_atencao(self) -> bool:
        return bool(self.motivos)

    def to_dict(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["motivos"] = list(self.motivos)
        dados["candidatos"] = list(self.candidatos)
        return dados

    @classmethod
    def from_dict(cls, dados: dict[str, Any]) -> ItemDeImportacao:
        status = str(dados.get("status", PENDENTE))
        return cls(
            imagem=str(dados.get("imagem", "")),
            livro=str(dados.get("livro", "")),
            indice=int(dados.get("indice", 0) or 0),
            fen_da_fonte=str(dados.get("fen_da_fonte", "")),
            lado=str(dados.get("lado", "")),
            legenda=str(dados.get("legenda", "")),
            motivos=tuple(str(motivo) for motivo in dados.get("motivos", ())),
            fen_do_modelo=str(dados.get("fen_do_modelo", "")),
            recorte=str(dados.get("recorte", "")),
            status=status if status in STATUS else PENDENTE,
            amostra=str(dados.get("amostra", "")),
            pagina=int(dados.get("pagina", 0) or 0),
            candidatos=tuple(str(fen) for fen in dados.get("candidatos", ())),
        )


@dataclass
class Lote:
    """As imagens de uma pasta e o andamento da importação delas."""

    pasta: str
    origem: str
    itens: list[ItemDeImportacao] = field(default_factory=list)
    ausentes: int = 0
    """Entradas do relatório cuja imagem não está no disco -- contadas, não importáveis."""

    criado_em: str = ""

    def __len__(self) -> int:
        return len(self.itens)

    def caminho_da_imagem(self, item: ItemDeImportacao) -> Path:
        return Path(self.pasta) / item.imagem

    def contagem(self) -> Counter[str]:
        return Counter(item.status for item in self.itens)

    def resumo(self) -> str:
        conta = self.contagem()
        atencao = sum(1 for item in self.itens if item.status == PENDENTE and item.precisa_de_atencao)
        partes = [
            f"{len(self.itens)} imagens",
            f"{conta[PENDENTE]} pendentes ({atencao} com aviso)",
            f"{conta[SALVO]} salvas no dataset",
            f"{conta[PULADO]} puladas",
            f"{conta[DESCARTADO]} descartadas",
        ]
        if self.ausentes:
            partes.append(f"{self.ausentes} citadas no relatório sem imagem no disco")
        return ", ".join(partes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "versao": VERSAO_DO_LOTE,
            "pasta": self.pasta,
            "origem": self.origem,
            "ausentes": self.ausentes,
            "criado_em": self.criado_em,
            "itens": [item.to_dict() for item in self.itens],
        }

    def salvar(self, caminho: Path) -> Path:
        atomic_write_json(Path(caminho), self.to_dict(), indent=1)
        return Path(caminho)

    @classmethod
    def carregar(cls, caminho: Path) -> Lote | None:
        """O lote gravado, ou `None` quando não há arquivo ou ele não é deste formato."""
        caminho = Path(caminho)
        if not caminho.exists():
            return None
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("Andamento da importação ilegível, recomeçando (%s): %s", caminho, exc)
            return None
        if not isinstance(dados, dict) or dados.get("versao") != VERSAO_DO_LOTE:
            return None
        return cls(
            pasta=str(dados.get("pasta", "")),
            origem=str(dados.get("origem", "")),
            itens=[ItemDeImportacao.from_dict(item) for item in dados.get("itens", []) if isinstance(item, dict)],
            ausentes=int(dados.get("ausentes", 0) or 0),
            criado_em=str(dados.get("criado_em", "")),
        )


def caminho_do_lote(pasta: Path | str, origem: str, *, diretorio: Path | None = None) -> Path:
    """Onde mora o andamento desta pasta. O nome legível vem da pasta; o hash, do caminho inteiro."""
    pasta = Path(pasta).resolve()
    chave = hashlib.sha1(f"{origem}:{str(pasta).lower()}".encode()).hexdigest()[:10]
    legivel = re.sub(r"[^\w\-]+", "_", pasta.name, flags=re.UNICODE).strip("_")[:40] or "pasta"
    return Path(diretorio if diretorio is not None else DIRETORIO_DOS_LOTES) / f"{legivel}_{origem}_{chave}.json"


def abrir_lote(pasta: Path | str, origem: str, *, diretorio: Path | None = None) -> tuple[Lote, Path]:
    """Lê a pasta e junta com o andamento gravado, se houver.

    A pasta é relida sempre: uma execução nova do plugin acrescenta imagens, e elas têm de
    aparecer. O que já tinha andamento (salvo, pulado, descartado, correção feita) fica como estava
    -- a chave é o caminho da imagem.
    """
    pasta = Path(pasta)
    if origem == COM_FEN:
        novo = ler_relatorios_do_chessmeridaocr(pasta)
    elif origem == SEM_FEN:
        novo = ler_pasta_de_imagens(pasta)
    elif origem == COM_PGN:
        novo = ler_livro_com_pgn(pasta, diretorio=diretorio)
    else:
        raise ValueError(f"Origem desconhecida: {origem!r}")
    caminho = caminho_do_lote(pasta, origem, diretorio=diretorio)
    antigo = Lote.carregar(caminho)
    if antigo is not None:
        por_imagem = {item.imagem: item for item in antigo.itens}
        novo.itens = [_juntar(item, por_imagem.get(item.imagem)) for item in novo.itens]
        novo.criado_em = antigo.criado_em or novo.criado_em
    _herdar_de_outros_lotes(novo, andamento_de_outros_lotes(novo.pasta, origem, diretorio=diretorio))
    return novo, caminho


def _chave_absoluta(pasta: str, imagem: str) -> str:
    """A imagem pelo caminho inteiro, comparado como o sistema compara: é o que dois lotes têm em comum.

    O `imagem` do item é relativo à pasta do lote, e muda com ela: `Livro/x.png` aberto pela pasta
    de cima, `x.png` aberto pela do livro.
    """
    return os.path.normcase(os.path.normpath(os.path.join(pasta, imagem)))


def andamento_de_outros_lotes(
    pasta: Path | str, origem: str, *, diretorio: Path | None = None
) -> dict[str, ItemDeImportacao]:
    """O que os outros lotes gravados já decidiram, por `_chave_absoluta` -- fora o lote desta pasta.

    Só entra o que não está pendente. Se dois lotes discordam, vale `_PESO_DO_STATUS`.
    """
    diretorio = Path(diretorio if diretorio is not None else DIRETORIO_DOS_LOTES)
    proprio = caminho_do_lote(pasta, origem, diretorio=diretorio).name
    decididos: dict[str, ItemDeImportacao] = {}
    if not diretorio.is_dir():
        return decididos
    for arquivo in sorted(diretorio.glob("*.json")):
        if arquivo.name == proprio:
            continue
        lote = Lote.carregar(arquivo)
        if lote is None or not lote.pasta:
            continue
        for item in lote.itens:
            if item.status == PENDENTE:
                continue
            chave = _chave_absoluta(lote.pasta, item.imagem)
            atual = decididos.get(chave)
            if atual is None or _PESO_DO_STATUS[item.status] < _PESO_DO_STATUS[atual.status]:
                decididos[chave] = item
    return decididos


def _herdar_de_outros_lotes(lote: Lote, outros: dict[str, ItemDeImportacao]) -> None:
    """Traz para o lote o que outro lote decidiu, quando pesa mais que o que o próprio lote tem."""
    if not outros:
        return
    for posicao, item in enumerate(lote.itens):
        outro = outros.get(_chave_absoluta(lote.pasta, item.imagem))
        if outro is not None and _PESO_DO_STATUS[outro.status] < _PESO_DO_STATUS[item.status]:
            lote.itens[posicao] = _juntar(item, outro)


def _juntar(lido: ItemDeImportacao, gravado: ItemDeImportacao | None) -> ItemDeImportacao:
    if gravado is None:
        return lido
    escolhida = gravado.fen_da_fonte in lido.candidatos  # a leitura já escolheu entre as da legenda
    if gravado.status == PENDENTE and gravado.fen_da_fonte != lido.fen_da_fonte and not escolhida:
        # O relatório mudou para esta imagem (outra execução do plugin): vale a leitura nova.
        return lido
    return replace(
        lido,
        fen_da_fonte=gravado.fen_da_fonte if escolhida else lido.fen_da_fonte,
        lado=gravado.lado if escolhida else lido.lado,
        status=gravado.status,
        amostra=gravado.amostra,
        fen_do_modelo=gravado.fen_do_modelo,
        recorte=gravado.recorte,
        motivos=tuple(dict.fromkeys((*lido.motivos, *gravado.motivos))),
    )


# ---------------------------------------------------------------------- relatório do Sigil


class _LeitorDoRelatorio(HTMLParser):
    """Tira `(src, fen, seção)` de cada `<article class="chessocr-entry">` do relatório."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entradas: list[tuple[str, str, str]] = []
        self._no_artigo = False
        self._src = ""
        self._secao: list[str] = []
        self._fen: list[str] = []
        self._em: str = ""
        self._no_paragrafo_da_fen = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        atributos = {nome: valor or "" for nome, valor in attrs}
        classes = atributos.get("class", "").split()
        if tag == "article" and "chessocr-entry" in classes:
            self._no_artigo, self._src, self._secao, self._fen = True, "", [], []
            return
        if not self._no_artigo:
            return
        if tag == "img" and not self._src:
            self._src = atributos.get("src", "")
        elif tag == "h3":
            self._em = "h3"
        elif tag == "p" and "chessocr-fen" in classes:
            self._no_paragrafo_da_fen = True
        elif tag == "code" and self._no_paragrafo_da_fen:
            self._em = "code"

    def handle_endtag(self, tag: str) -> None:
        if tag in ("h3", "code"):
            self._em = ""
        elif tag == "p":
            self._no_paragrafo_da_fen = False
        elif tag == "article" and self._no_artigo:
            self._no_artigo = False
            fen = " ".join("".join(self._fen).split())
            if self._src and fen:
                self.entradas.append((self._src, fen, " ".join("".join(self._secao).split())))

    def handle_data(self, data: str) -> None:
        if self._em == "h3":
            self._secao.append(data)
        elif self._em == "code":
            self._fen.append(data)


def _relatorios_em(pasta: Path) -> list[Path]:
    """Os `.html` do relatório: na própria pasta (um livro) ou um nível abaixo (vários)."""
    proprios = sorted(pasta.glob("*.html"))
    if proprios:
        return proprios
    return sorted(caminho for sub in sorted(pasta.iterdir()) if sub.is_dir() for caminho in sub.glob("*.html"))


def ler_relatorios_do_chessmeridaocr(pasta: Path | str) -> Lote:
    """Um lote com as imagens de todos os relatórios da pasta, uma entrada por imagem.

    A mesma imagem aparece mais de uma vez quando o plugin rodou de novo sobre o livro. Fica a
    última FEN (a execução mais nova vem depois no arquivo); se as execuções discordaram, o item
    leva o motivo e vai para conferência em vez de entrar sozinho.
    """
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")
    itens: list[ItemDeImportacao] = []
    ausentes = 0
    relatorios = _relatorios_em(pasta)
    if not relatorios:
        raise FileNotFoundError(f"Nenhum relatório .html do ChessMeridaOCR em {pasta}")
    for relatorio in relatorios:
        leitor = _LeitorDoRelatorio()
        leitor.feed(relatorio.read_text(encoding="utf-8", errors="replace"))
        livro = relatorio.parent.name if relatorio.parent != pasta else pasta.name
        por_imagem: dict[str, list[tuple[str, str]]] = {}
        for src, fen, secao in leitor.entradas:
            por_imagem.setdefault(src, []).append((fen, secao))
        for src, leituras in por_imagem.items():
            arquivo = relatorio.parent / src
            if not arquivo.is_file():
                ausentes += 1
                continue
            fen, secao = leituras[-1]
            motivos: list[str] = []
            diferentes = list(dict.fromkeys(campo_de_pecas(leitura) for leitura, _ in leituras))
            if len(diferentes) > 1:
                motivos.append(f"o relatório tem {len(diferentes)} FENs diferentes para esta imagem")
            if campo_de_pecas(fen) == TABULEIRO_VAZIO:
                motivos.append("o relatório deu tabuleiro vazio")
            partes = fen.split()
            itens.append(
                ItemDeImportacao(
                    imagem=arquivo.relative_to(pasta).as_posix(),
                    livro=livro,
                    indice=0,
                    fen_da_fonte=fen,
                    lado=partes[1] if len(partes) > 1 and partes[1] in ("w", "b") else "",
                    legenda=secao,
                    motivos=tuple(motivos),
                )
            )
    return Lote(
        pasta=str(pasta.resolve()),
        origem=COM_FEN,
        itens=_numerar(itens),
        ausentes=ausentes,
        criado_em=_agora(),
    )


# ------------------------------------------------------------------ pasta de imagens sem FEN


def _indice_do_jbc(pasta: Path) -> dict[str, dict[str, str]]:
    """`{caminho relativo: linha}` do `index.csv`, quando a pasta tem um com a coluna `png`."""
    indice = pasta / "index.csv"
    if not indice.is_file():
        return {}
    try:
        with indice.open(encoding="utf-8-sig", newline="") as arquivo:
            linhas = list(csv.DictReader(arquivo))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        logger.warning("index.csv ilegível em %s: %s", pasta, exc)
        return {}
    return {linha["png"].replace("\\", "/"): linha for linha in linhas if linha.get("png")}


def ler_pasta_de_imagens(pasta: Path | str) -> Lote:
    """Um lote com cada imagem da pasta e das subpastas (fora as ocultas, como `.git`)."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")
    indice = _indice_do_jbc(pasta)
    itens: list[ItemDeImportacao] = []
    for arquivo in sorted(pasta.rglob("*")):
        relativo = arquivo.relative_to(pasta)
        if any(parte.startswith(".") for parte in relativo.parts):
            continue
        if arquivo.suffix.lower() not in EXTENSOES or not arquivo.is_file():
            continue
        chave = relativo.as_posix()
        linha = indice.get(chave, {})
        titulo = " ".join(parte for parte in (linha.get("title", ""), linha.get("year", "")) if parte)
        livro = titulo or (relativo.parts[0] if len(relativo.parts) > 1 else pasta.name)
        lado = linha.get("to_move", "").strip().lower()
        legenda = linha.get("caption", "").strip()
        itens.append(
            ItemDeImportacao(
                imagem=chave,
                livro=livro,
                indice=0,
                lado=lado if lado in ("w", "b") else "",
                legenda=legenda,
            )
        )
    return Lote(pasta=str(pasta.resolve()), origem=SEM_FEN, itens=_numerar(itens), criado_em=_agora())


def _par_do_livro(pasta: Path) -> tuple[Path, Path]:
    """O `.pdf` e o `.pgn` da pasta. Com mais de um de cada, o par é o de nomes que se contêm --
    o PDF do acervo costuma ter um prefixo («📚Autor. Título.pdf») que o PGN não tem."""
    pdfs, pgns = sorted(pasta.glob("*.pdf")), sorted(pasta.glob("*.pgn"))
    if not pdfs or not pgns:
        raise FileNotFoundError(f"A pasta precisa de um .pdf e do .pgn dele: {pasta}")
    if len(pdfs) == 1 and len(pgns) == 1:
        return pdfs[0], pgns[0]
    for pdf in pdfs:
        for pgn in pgns:
            if pgn.stem.lower() in pdf.stem.lower() or pdf.stem.lower() in pgn.stem.lower():
                return pdf, pgn
    raise ValueError(f"Nenhum .pgn da pasta tem o nome de um dos PDFs: {pasta}")


def ler_livro_com_pgn(pasta: Path | str, *, diretorio: Path | None = None) -> Lote:
    """Um lote com cada diagrama do PDF casado com o seu nó do PGN (S-593).

    O casamento é o de `livro_com_pgn` pela legenda, sem o modelo: quem confere é a importação,
    como em qualquer lote com FEN. A imagem de cada diagrama é gravada **como o livro a embute**
    (o `get_text("dict")` traz os bytes), em `<diretorio>/<livro>_<identidade>/` -- sem rasterizar
    página nenhuma, o que deixaria a janela parada um minuto num livro de mil diagramas. Os que o
    casamento não resolve (sem nó, sem imagem) ficam fora: sem FEN e sem imagem não há o que importar.
    """
    import fitz

    from .livro_com_pgn import FALTANDO, SEM_NO, casar_livro
    from .pgn_do_livro import IndiceDoLivro
    from .text.caderno import identidade_de

    pasta = Path(pasta)
    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")
    pdf, pgn = _par_do_livro(pasta)
    indice = IndiceDoLivro.do_arquivo(pgn)
    livro = re.sub(r"^\W+", "", pdf.stem).strip() or pdf.stem
    destino = (diretorio or DIRETORIO_DOS_LOTES) / f"{_nome_de_arquivo(livro)}_{identidade_de(pdf) or 'livro'}"
    destino.mkdir(parents=True, exist_ok=True)
    blocos: dict[int, list[dict[str, Any]]] = {}

    def paginas(documento: Any) -> Iterable[tuple[int, dict[str, Any]]]:
        for k in range(documento.page_count):
            dicionario = documento[k].get_text("dict")
            blocos[k + 1] = [b for b in dicionario.get("blocks", []) if b.get("type") == 1]
            yield k + 1, dicionario

    itens: list[ItemDeImportacao] = []
    with fitz.open(pdf) as documento:
        diagramas = casar_livro(paginas(documento), indice, sumario=documento.get_toc())
    for diagrama in diagramas:
        if diagrama.estado in (FALTANDO, SEM_NO) or diagrama.caixa is None or not diagrama.fen:
            continue
        bloco = next((b for b in blocos.get(diagrama.pagina, []) if tuple(b["bbox"]) == diagrama.caixa), None)
        if bloco is None or not bloco.get("image"):
            continue
        arquivo = destino / f"p{diagrama.pagina:04d}_{int(diagrama.caixa[1]):04d}.{bloco.get('ext') or 'png'}"
        if not arquivo.exists():
            arquivo.write_bytes(bloco["image"])
        itens.append(
            ItemDeImportacao(
                imagem=arquivo.as_posix(),
                livro=livro,
                indice=0,
                fen_da_fonte=diagrama.fen,
                lado=diagrama.fen.split()[1],
                legenda=f"Position after: {diagrama.legenda}" if diagrama.legenda else "",
                pagina=diagrama.pagina,
                candidatos=_candidatos(diagrama, indice),
            )
        )
    return Lote(pasta=str(pasta.resolve()), origem=COM_PGN, itens=_numerar(itens), criado_em=_agora())


def _candidatos(diagrama: Any, indice: Any) -> tuple[str, ...]:
    """As FENs distintas dos nós que a legenda admite; vazio quando só há uma."""
    fens = tuple(dict.fromkeys(indice.nos[k].fen for k in diagrama.candidatos))
    return fens if len({fen.split()[0] for fen in fens}) > 1 else ()


def _nome_de_arquivo(texto: str) -> str:
    return re.sub(r"[^\w.-]+", "_", texto, flags=re.UNICODE).strip("_")[:60] or "livro"


def _numerar(itens: list[ItemDeImportacao]) -> list[ItemDeImportacao]:
    """`indice` sequencial dentro de cada livro, na ordem em que as imagens vieram."""
    contadores: Counter[str] = Counter()
    numerados = []
    for item in itens:
        contadores[item.livro] += 1
        numerados.append(replace(item, indice=contadores[item.livro]))
    return numerados


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------------- FEN e recorte


def campo_de_pecas(fen: str) -> str:
    """O primeiro campo da FEN, que é o que a imagem mostra."""
    return fen.split()[0] if fen and fen.split() else ""


def casas_diferentes(fen_a: str, fen_b: str) -> list[int]:
    """Índices (0 = a8) das casas em que os dois campos de peças discordam."""
    from .fen_utils import labels_from_fen

    try:
        a, b = labels_from_fen(campo_de_pecas(fen_a)), labels_from_fen(campo_de_pecas(fen_b))
    except ValueError:
        return list(range(64))
    return [casa for casa, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]


def com_a_leitura(item: ItemDeImportacao, lida: str, recorte: str) -> ItemDeImportacao:
    """O item com a leitura do modelo -- e, quando a fonte admite mais de uma FEN, com a mais perto
    dela como `fen_da_fonte`.

    É o que o casamento do livro (S-588) faz com o modelo à mão, feito aqui porque o lote é casado
    sem ele: com a mesma legenda em duas linhas do capítulo, a ordem do livro sozinha escolhia a
    linha errada em ~40% dos casos, e o item caía na conferência com a sugestão errada.
    """
    novo = replace(item, fen_do_modelo=lida, recorte=recorte)
    if len(item.candidatos) > 1 and lida:
        melhor = min(item.candidatos, key=lambda fen: len(casas_diferentes(fen, lida)))
        novo = replace(novo, fen_da_fonte=melhor, lado=melhor.split()[1])
    return novo


def concorda(item: ItemDeImportacao) -> bool:
    """A FEN da fonte pode ir para o dataset sem conferência humana.

    Três condições: o modelo leu a mesma posição no recorte, a posição não é fatalmente ilegal e o
    relatório não levantou nenhuma suspeita (`motivos`).
    """
    from .fen_utils import check_position

    if item.motivos or not item.fen_da_fonte or not item.fen_do_modelo:
        return False
    if campo_de_pecas(item.fen_da_fonte) != campo_de_pecas(item.fen_do_modelo):
        return False
    return not check_position(item.fen_da_fonte).is_fatal


def ler_imagem(caminho: Path | str) -> np.ndarray:
    """A imagem em RGB, ou `ValueError` quando ela não abre."""
    import cv2

    bgr = read_image(caminho)
    if bgr is None:
        raise ValueError(f"Não foi possível abrir a imagem: {caminho}")
    if bgr.ndim == 2:
        return cv2.cvtColor(bgr, cv2.COLOR_GRAY2RGB)
    if bgr.shape[2] == 4:
        return cv2.cvtColor(bgr, cv2.COLOR_BGRA2RGB)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def recortar(imagem_rgb: np.ndarray, modo: str = "") -> tuple[np.ndarray, str]:
    """O tabuleiro de `BOARD_SIZE`×`BOARD_SIZE` dentro da imagem, e qual recorte foi usado.

    `modo` vazio decide sozinho (ver o docstring do módulo); `"detectado"` e `"inteira"` forçam.
    Pedir o detectado numa imagem em que o detector não acha nada devolve a inteira.
    """
    import cv2

    from .board_detection import detect_boards, tighten_board

    if modo != RECORTE_INTEIRA:
        achados = detect_boards(imagem_rgb, max_boards=1, warn_on_cap=False, recall=None)
        if achados:
            tabuleiro, quad = achados[0]
            if modo == RECORTE_DETECTADO or _fracao_do_quadro(quad, imagem_rgb.shape) >= FRACAO_MINIMA_DO_QUADRO:
                return tabuleiro, RECORTE_DETECTADO
    inteira = cv2.resize(imagem_rgb, (BOARD_SIZE, BOARD_SIZE), interpolation=cv2.INTER_AREA)
    return tighten_board(inteira), RECORTE_INTEIRA


def _fracao_do_quadro(quad: np.ndarray | None, forma: tuple[int, ...]) -> float:
    if quad is None:
        return 0.0
    pontos = np.asarray(quad, dtype=np.float64).reshape(-1, 2)
    largura = float(pontos[:, 0].max() - pontos[:, 0].min())
    altura = float(pontos[:, 1].max() - pontos[:, 1].min())
    return (largura * altura) / float(max(1, forma[0] * forma[1]))


# ---------------------------------------------------------------------------- gravação


def origem_da_amostra(lote: Lote, item: ItemDeImportacao) -> str:
    """O `source_pdf` da amostra: a fonte e o livro, para o Dataset filtrar e o split agrupar."""
    if lote.origem == COM_PGN:
        return item.livro  # o livro, como as amostras que a janela grava dele: o split agrupa as duas
    fonte = "ChessMeridaOCR" if lote.origem == COM_FEN else Path(lote.pasta).name
    return f"{fonte}: {item.livro}"


def gravar_item(
    lote: Lote,
    posicao: int,
    tabuleiro_rgb: np.ndarray,
    fen: str,
    *,
    lado: str,
    recorte: str,
    csv_path: Path,
    samples_dir: Path,
    corrected_by: str,
    allow_illegal: bool = False,
    diretorio: Path | None = None,
    outros: dict[str, ItemDeImportacao] | None = None,
) -> ItemDeImportacao:
    """Grava a amostra no dataset e marca o item como salvo. Devolve o item novo.

    Recusa gravar duas vezes a mesma imagem: o item salvo já tem `amostra`, e uma segunda linha no
    `labels.csv` com a mesma imagem só pesaria em dobro no treino, e com `source_pdf` diferente se
    cada lote a gravou. Vale também para a imagem que **outro lote** já gravou: `outros` é o `andamento_de_outros_lotes`, lido de `diretorio` quando não vem pronto.
    """
    from .dataset import append_training_sample

    item = lote.itens[posicao]
    if item.status == SALVO:
        raise ValueError(f"Esta imagem já foi gravada no dataset ({item.amostra}).")
    if outros is None:
        outros = andamento_de_outros_lotes(lote.pasta, lote.origem, diretorio=diretorio)
    outro = outros.get(_chave_absoluta(lote.pasta, item.imagem))
    if outro is not None and outro.status == SALVO:
        raise ValueError(f"Esta imagem já foi gravada no dataset por outro lote ({outro.amostra}).")
    caminho = append_training_sample(
        tabuleiro_rgb,
        fen,
        csv_path,
        samples_dir,
        allow_illegal=allow_illegal,
        side_to_move=lado if lado in ("w", "b") else None,
        source_pdf=origem_da_amostra(lote, item),
        source_page=item.pagina or "",
        source_diagram=item.indice,
        detection_source=f"importacao-{recorte}" if recorte else "importacao",
        corrected_by=corrected_by,
    )
    salvo = replace(item, status=SALVO, amostra=Path(caminho).name, recorte=recorte)
    lote.itens[posicao] = salvo
    return salvo


def marcar(lote: Lote, posicao: int, status: str) -> ItemDeImportacao:
    """Pula ou descarta (ou devolve a pendente) um item que ainda não foi gravado."""
    if status not in (PENDENTE, PULADO, DESCARTADO):
        raise ValueError(f"Status inválido para marcar: {status!r}")
    item = lote.itens[posicao]
    if item.status == SALVO:
        raise ValueError("Esta imagem já está no dataset; tire-a pela aba Dataset.")
    lote.itens[posicao] = replace(item, status=status)
    return lote.itens[posicao]


def importar_os_que_concordam(
    lote: Lote,
    *,
    ler: Callable[[np.ndarray], str],
    csv_path: Path,
    samples_dir: Path,
    corrected_by: str,
    progresso: Callable[[int, int, int], None] | None = None,
    cancelar: Callable[[], bool] | None = None,
    gravar_andamento: Callable[[], None] | None = None,
    a_cada: int = 25,
    diretorio: Path | None = None,
) -> Counter[str]:
    """Passa pelos pendentes com FEN da fonte: recorta, lê com o modelo e grava os que concordam.

    `ler` recebe o recorte e devolve a FEN que o modelo leu -- é o único ponto que precisa do
    modelo, e por isso chega de fora. Quem discorda fica pendente, com o motivo e a leitura do
    modelo guardados, para a conferência abrir sem ler de novo.

    Devolve a contagem: `salvos`, `discordam`, `com_aviso` (não foram lidos: o relatório já tinha
    levantado suspeita), `falhas` (a imagem não abriu ou não gravou).

    O andamento dos outros lotes (em `diretorio`) é lido uma vez, no começo: o que outro lote já
    decidiu deixa de ser pendente aqui, e não é lido nem gravado de novo.
    """
    conta: Counter[str] = Counter()
    outros = andamento_de_outros_lotes(lote.pasta, lote.origem, diretorio=diretorio)
    _herdar_de_outros_lotes(lote, outros)
    alvos = [
        posicao
        for posicao, item in enumerate(lote.itens)
        if item.status == PENDENTE and item.fen_da_fonte
    ]
    for passo, posicao in enumerate(alvos, start=1):
        if cancelar is not None and cancelar():
            break
        item = lote.itens[posicao]
        if item.motivos:
            conta["com_aviso"] += 1
        else:
            try:
                tabuleiro, recorte = recortar(ler_imagem(lote.caminho_da_imagem(item)), item.recorte)
                lida = ler(tabuleiro)
                item = com_a_leitura(item, lida, recorte)
                lote.itens[posicao] = item
                if concorda(item):
                    gravar_item(
                        lote,
                        posicao,
                        tabuleiro,
                        item.fen_da_fonte,
                        lado=item.lado,
                        recorte=recorte,
                        csv_path=csv_path,
                        samples_dir=samples_dir,
                        corrected_by=corrected_by,
                        outros=outros,
                    )
                    conta["salvos"] += 1
                else:
                    diferentes = len(casas_diferentes(item.fen_da_fonte, lida))
                    motivo = (
                        f"o modelo leu outra posição ({diferentes} casas diferentes)"
                        if diferentes
                        else "posição ilegal"
                    )
                    lote.itens[posicao] = replace(item, motivos=(*item.motivos, motivo))
                    conta["discordam"] += 1
            except (OSError, ValueError) as exc:
                logger.warning("Importação: %s ficou de fora: %s", item.imagem, exc)
                lote.itens[posicao] = replace(item, motivos=(*item.motivos, f"falhou: {exc}"))
                conta["falhas"] += 1
        if progresso is not None:
            progresso(passo, len(alvos), conta["salvos"])
        if gravar_andamento is not None and passo % a_cada == 0:
            gravar_andamento()
    if gravar_andamento is not None:
        gravar_andamento()
    return conta


def rota_da_conferencia(item: ItemDeImportacao, fen: str) -> str:
    """O `corrected_by` de uma amostra gravada pela conferência.

    Com a leitura do modelo ao lado, é a pergunta da S-52 e a mesma resposta: gravou o que o modelo
    leu, `ocr-aceito`; mudou alguma casa, `ocr-corrigido` -- e entra nas rotas humanas do treino.
    Sem leitura para comparar, `importado-conferido`.
    """
    from .labels import OCR_ACEITO, OCR_CORRIGIDO

    if not item.fen_do_modelo:
        return IMPORTADO_CONFERIDO
    return OCR_ACEITO if campo_de_pecas(fen) == campo_de_pecas(item.fen_do_modelo) else OCR_CORRIGIDO


def posicoes(lote: Lote, filtro: str) -> list[int]:
    """As posições do lote que a conferência percorre com este filtro."""
    if filtro == "aviso":
        return [p for p, item in enumerate(lote.itens) if item.status == PENDENTE and item.precisa_de_atencao]
    if filtro == "pendentes":
        return [p for p, item in enumerate(lote.itens) if item.status == PENDENTE]
    if filtro == "puladas":
        return [p for p, item in enumerate(lote.itens) if item.status == PULADO]
    return list(range(len(lote.itens)))


def livros(itens: Iterable[ItemDeImportacao]) -> list[str]:
    return list(dict.fromkeys(item.livro for item in itens))
