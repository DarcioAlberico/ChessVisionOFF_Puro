"""A transcrição do scan-ouro: a verdade humana, às cegas, fora do repositório (S-703).

**Verdade ancorada no sistema avaliado não é verdade.** Quem corrige a leitura de um motor vê a leitura, e só mexe no que nota. Por isso a
folha parte da camada de terceiro (ABBYY, Paper Capture: nunca motor nosso) ou do vazio, e nunca do glifo, do Tesseract ou da fusão. A porta
é `CadernoDaPassada.gravar`, que chama `dado_corrigido.exigir_documento_cego` e `procedencia.exigir_transcricao` a cada gravação.

**Um caderno por passada.** A segunda digitação não pode abrir a primeira: o `caderno` de hoje reabre a folha com o que já foi corrigido
(S-612), e aqui esse conforto anularia a medida. `CadernoDaPassada` só conhece o arquivo da sua passada, e **a segunda parte sempre do vazio**:
as duas partindo da mesma camada concordariam nos erros que ninguém viu, e o acordo mediria a camada.

**O acordo é a régua da régua**: ≥ 99,9% de caractere nas folhas duplicadas, dez vezes mais fino que o alvo M3 (1%). Só quem junta as passadas é
`ler_pasta`, usado pelo `cvoff-texto-prosa --conjunto scan-ouro --acordo`, e a tela não a chama.

**Onde mora.** É texto de livro comercial e são ~15 horas de alguém: pasta própria, fora de qualquer repositório, com backup **declarado**
(`declarar_backup`). Sem o backup declarado, o caderno não grava. Cada gravação é uma linha a mais no JSONL (a última de uma folha vale) e uma
cópia do arquivo no backup. A falha do backup não perde a folha, e volta a quem gravou para dizer na tela.

**O relógio mede o custo real**, porque a decisão D3 é sobre horas. Duas folhas bastam para `custo` estimar o resto, e o tempo parado não entra.

Nada aqui lê o glifo, o Tesseract ou a fusão: `linhas_da_folha` é a geometria de `leitor.segmentar`, sem classificador.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from ..atomic_io import atomic_write_bytes
from . import dado_corrigido as _dado_corrigido
from . import procedencia as _procedencia
from . import regua_prosa as _regua
from . import scan_ouro as _scan_ouro
from .pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from .rico import DocumentoRico

logger = logging.getLogger(__name__)

PASSADAS = (1, 2)
VAZIO = "vazio"
CAMADA = "camada"
PARTIDAS = (VAZIO, CAMADA)
ACORDO_MINIMO = 0.999
"""O acordo de caractere que uma folha duplicada tem de ter, ou ela volta para transcrição. Dez vezes mais fino que o alvo M3."""
DPI = 220
"""O da régua (`bancada_prosa.DPI_PADRAO`): a faixa que a pessoa olha é a imagem que os motores vão ler."""
FOLHAS_PARA_ESTIMAR = 2
OCIOSO_MAXIMO = 300.0
"""Uma pausa maior que isto entre duas teclas conta só isto: é café, e não a folha. Cinco minutos cobrem ler um parágrafo difícil."""
ARQUIVO_DO_BACKUP = "backup.json"
FOLGA_DA_FAIXA = 4
"""Pixels em volta da linha na faixa impressa: o acento e a descendente que a caixa cortou."""


class PastaNoRepositorio(ValueError):
    """A transcrição é texto de livro comercial, e o repositório é público."""


class SemBackup(ValueError):
    """São ~15 horas de trabalho humano: sem o backup declarado, nada se grava."""


def recusar_no_repositorio(pasta: str | Path) -> None:
    alvo = Path(pasta).resolve()
    for ancestral in (alvo, *alvo.parents):
        if (ancestral / ".git").exists():
            raise PastaNoRepositorio(f"{alvo} está dentro do repositório {ancestral}: a transcrição mora fora dele.")


def partidas_da_passada(passada: int) -> tuple[str, ...]:
    """A primeira pode partir da camada de terceiro; a segunda só do vazio, ou o acordo mede a camada."""
    return PARTIDAS if passada == PASSADAS[0] else (VAZIO,)


def caminho_da_passada(pasta: str | Path, passada: int) -> Path:
    return Path(pasta) / f"passada_{int(passada)}.jsonl"


def declarar_backup(pasta: str | Path, backup: str | Path, *, hoje: str | None = None) -> None:
    """Escreve onde o backup mora. A declaração fica na própria pasta, e a `--acordo` a confere."""
    recusar_no_repositorio(pasta)
    recusar_no_repositorio(backup)
    if Path(pasta).resolve() == Path(backup).resolve():
        raise SemBackup("o backup é a própria pasta da transcrição: isso não é backup.")
    Path(pasta).mkdir(parents=True, exist_ok=True)
    Path(backup).mkdir(parents=True, exist_ok=True)
    dados = {"backup": str(Path(backup).resolve()), "declarado_em": hoje or date.today().isoformat()}
    atomic_write_bytes(Path(pasta) / ARQUIVO_DO_BACKUP, (json.dumps(dados, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))


def backup_declarado(pasta: str | Path) -> Path | None:
    arquivo = Path(pasta) / ARQUIVO_DO_BACKUP
    if not arquivo.is_file():
        return None
    try:
        return Path(json.loads(arquivo.read_text(encoding="utf-8"))["backup"])
    except (ValueError, KeyError, TypeError):
        # Declaração ilegível é declaração que não há: o caderno recusa gravar, e a tela diz. Levantar aqui mataria o processo num slot.
        logger.warning("A declaração de backup em %s está ilegível.", arquivo)
        return None


def estado_do_backup(pasta: str | Path) -> str:
    """`nao_declarado`, `em_dia` ou `atrasado`: o backup tem os mesmos bytes de cada passada?"""
    backup = backup_declarado(pasta)
    if backup is None:
        return "nao_declarado"
    for passada in PASSADAS:
        original = caminho_da_passada(pasta, passada)
        copia = caminho_da_passada(backup, passada)
        if original.is_file() and (not copia.is_file() or copia.read_bytes() != original.read_bytes()):
            return "atrasado"
    return "em_dia"


@dataclass(frozen=True)
class FolhaDaPassada:
    """Uma linha do JSONL: uma folha, numa passada, como estava quando foi gravada."""

    identidade: str
    folha: int
    """Base 1, como no manifesto."""
    passada: int
    procedencia: str
    linhas: tuple[str, ...]
    partida: str
    sha_imagem: str
    """O sha da imagem renderizada a `dpi`: a faixa que a pessoa olhou."""
    sha_folha: str
    """O sha dos bytes da folha no PDF (`scan_ouro.sha_da_folha`)."""
    dpi: int = DPI
    segundos: float = 0.0
    completa: bool = False
    """A pessoa disse que terminou. A rascunho não mede, não conta no acordo e não estima o custo."""
    gravado_em: str = ""

    @property
    def texto(self) -> str:
        return "\n".join(linha for linha in self.linhas if linha.strip())

    def para_json(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["linhas"] = list(self.linhas)
        return dados

    @classmethod
    def de_json(cls, dados: Mapping[str, Any]) -> FolhaDaPassada:
        campos = dict(dados)
        campos["linhas"] = tuple(campos.get("linhas", ()))
        return cls(**campos)


def _ler_com_ilegiveis(caminho: Path) -> tuple[dict[tuple[str, int], FolhaDaPassada], int]:
    """As folhas, e quantas linhas não se leram. **A linha cortada não derruba nada**: queda de luz e disco cheio cortam a última linha,
    e levantar aqui seria morte do processo a cada abertura do modo (exceção em slot do PyQt6), com as horas de digitação presas no arquivo."""
    if not caminho.is_file():
        return ({}, 0)
    registros: dict[tuple[str, int], FolhaDaPassada] = {}
    ilegiveis = 0
    for linha in caminho.read_bytes().split(b"\n"):
        if not linha.strip():
            continue
        try:
            registro = FolhaDaPassada.de_json(json.loads(linha.decode("utf-8")))
        except (ValueError, TypeError):
            ilegiveis += 1
            continue
        registros[(registro.identidade, registro.folha)] = registro
    if ilegiveis:
        logger.warning("%s: %d linha(s) ilegível(is), ignorada(s).", caminho.name, ilegiveis)
    return (registros, ilegiveis)


def _ler_jsonl(caminho: Path) -> dict[tuple[str, int], FolhaDaPassada]:
    return _ler_com_ilegiveis(caminho)[0]


def linhas_ilegiveis(pasta: str | Path, passada: int) -> int:
    """É o que a tela e o `--acordo` avisam: o que estava nessa linha voltou à gravação anterior da folha."""
    return _ler_com_ilegiveis(caminho_da_passada(pasta, passada))[1]


class CadernoDaPassada:
    """O caderno de **uma** passada. Não há como pedir a ele o texto de outra, e essa é a função dele."""

    def __init__(self, pasta: str | Path, passada: int) -> None:
        if passada not in PASSADAS:
            raise ValueError(f"passada {passada}: as passadas são {PASSADAS}")
        recusar_no_repositorio(pasta)
        self.pasta = Path(pasta)
        self.passada = passada

    @property
    def arquivo(self) -> Path:
        return caminho_da_passada(self.pasta, self.passada)

    def ler(self, identidade: str, folha: int) -> FolhaDaPassada | None:
        return _ler_jsonl(self.arquivo).get((identidade, folha))

    def concluidas(self) -> set[tuple[str, int]]:
        return {(r.identidade, r.folha) for r in self.registros_concluidos()}

    def registros_concluidos(self) -> list[FolhaDaPassada]:
        """As folhas concluídas **desta** passada: é o relógio da tela, e o texto da outra não vem junto."""
        return [registro for registro in _ler_jsonl(self.arquivo).values() if registro.completa]

    def gravar(self, registro: FolhaDaPassada, documento: DocumentoRico) -> bool:
        """Uma linha a mais no JSONL, e a cópia no backup. `False` é o backup que falhou: a folha está gravada, e isso precisa ser dito.

        **As duas portas da S-762 ficam aqui**, e não na tela, para que nenhum caminho de gravação passe sem elas.
        """
        onde = f"scan-ouro, folha {registro.folha}"
        _procedencia.exigir_transcricao(registro.procedencia, onde=onde)
        _dado_corrigido.exigir_documento_cego(documento, onde=onde)
        if registro.passada != self.passada or registro.procedencia != _procedencia.transcricao(self.passada):
            raise ValueError(f"{onde}: a folha é da passada {registro.passada} e este caderno, da {self.passada}.")
        if registro.partida not in partidas_da_passada(self.passada):
            raise ValueError(f"{onde}: a passada {self.passada} não parte de {registro.partida!r}.")
        backup = backup_declarado(self.pasta)
        if backup is None:
            raise SemBackup("declare o backup antes de gravar: são horas de trabalho humano.")
        self.pasta.mkdir(parents=True, exist_ok=True)
        # A linha cortada de antes não pode engolir esta: sem a quebra, as duas virariam uma linha ilegível só.
        cortada = self.arquivo.is_file() and self.arquivo.stat().st_size > 0 and not self.arquivo.read_bytes().endswith(b"\n")
        with self.arquivo.open("a", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(("\n" if cortada else "") + json.dumps(registro.para_json(), ensure_ascii=False) + "\n")
            arquivo.flush()
            os.fsync(arquivo.fileno())
        try:
            backup.mkdir(parents=True, exist_ok=True)
            temporario = caminho_da_passada(backup, self.passada).with_suffix(".tmp")
            shutil.copyfile(self.arquivo, temporario)
            os.replace(temporario, caminho_da_passada(backup, self.passada))
        except OSError:
            return False
        return True


def ler_pasta(pasta: str | Path) -> dict[int, dict[tuple[str, int], FolhaDaPassada]]:
    """As passadas juntas, a última gravação de cada folha. **É de quem mede o acordo**, e a tela não a usa."""
    return {passada: _ler_jsonl(caminho_da_passada(pasta, passada)) for passada in PASSADAS}


def sha_da_imagem(imagem: np.ndarray) -> str:
    resumo = hashlib.sha256(str(imagem.shape).encode())
    resumo.update(np.ascontiguousarray(imagem).tobytes())
    return resumo.hexdigest()[:16]


# ------------------------------------------------------------------------------------- a folha na tela


Caixa = tuple[float, float, float, float]


def linhas_da_folha(imagem: np.ndarray, diagramas: Sequence[Caixa], *, dpi: int = DPI) -> list[Caixa]:
    """As caixas das linhas, em pixels e na ordem de leitura. **Geometria**: região, coluna e banda de `leitor`, sem classificador nenhum."""
    from . import leitor as _leitor
    from .linhas import envolve, quebrar_em_linhas

    _cinza, _binaria, escala, caixas, regioes = _leitor.segmentar(imagem, diagramas, dpi=dpi)
    if not caixas:
        return []
    saida: list[Caixa] = []
    for _regiao, _coluna, tira in _leitor._tiras(caixas, regioes, escala=escala):  # noqa: SLF001
        saida.extend(envolve(linha) for linha in quebrar_em_linhas(tira) if linha)
    return saida


def recorte_da_linha(imagem: np.ndarray, caixa: Caixa) -> np.ndarray:
    """A faixa impressa de uma linha (S-643): a tinta com uma folga, para o acento não sumir."""
    x0, y0, x1, y1 = caixa
    altura, largura = imagem.shape[:2]
    return imagem[
        max(0, int(y0) - FOLGA_DA_FAIXA): min(altura, int(y1) + FOLGA_DA_FAIXA),
        max(0, int(x0) - FOLGA_DA_FAIXA): min(largura, int(x1) + FOLGA_DA_FAIXA),
    ]


def textos_da_camada(palavras: Iterable[Sequence[Any]], caixas: Sequence[Caixa], *, dpi: int = DPI) -> list[str]:
    """As palavras da camada de terceiro, cada uma na linha que contém o centro dela. `palavras` é o `page.get_text("words")`, em pontos."""
    escala = dpi / 72.0
    por_linha: list[list[tuple[float, str]]] = [[] for _ in caixas]
    for palavra in palavras:
        x0, y0, x1, y1, texto = palavra[:5]
        cx, cy = (x0 + x1) / 2 * escala, (y0 + y1) / 2 * escala
        for k, (a0, b0, a1, b1) in enumerate(caixas):
            if a0 <= cx <= a1 and b0 <= cy <= b1:
                por_linha[k].append((float(x0), str(texto)))
                break
    return [" ".join(texto for _x, texto in sorted(linha)) for linha in por_linha]


def documento_da_partida(textos: Sequence[str], caixas: Sequence[Caixa], partida: str, *, indice: int, dpi: int = DPI) -> DocumentoRico:
    """De onde a folha partiu, no formato que `exigir_documento_cego` sabe olhar: sem origem no vazio, com a camada na camada."""
    if partida == VAZIO:
        return DocumentoRico(corridas=(), origem=None)
    escala = 72.0 / dpi
    linhas = tuple(
        LinhaLida(texto, tuple(v * escala for v in caixa), procedencia="camada")  # type: ignore[arg-type]
        for texto, caixa in zip(textos, caixas, strict=True)
    )
    return DocumentoRico(corridas=(), origem=PaginaLida(pagina=indice, colunas=(Coluna(blocos=(BlocoDeTexto(linhas=linhas),)),)))


@dataclass(frozen=True)
class FolhaAberta:
    """A folha pronta para a tela: a imagem que a pessoa olha, as faixas, os shas e o que a camada de terceiro diz."""

    imagem: np.ndarray
    caixas: tuple[Caixa, ...]
    textos_da_camada: tuple[str, ...]
    sha_imagem: str
    sha_folha: str


def abrir_folha(pdf: str | Path, indice: int, *, dpi: int = DPI) -> FolhaAberta:
    """Renderiza a folha e acha as linhas. **Nenhum leitor aqui**: o detector de diagrama é visão, e o texto da camada já está no PDF."""
    import fitz

    from ..detection.hybrid import detect_diagrams_in_pdf_page
    from ..pdf_io import render_pdf_page

    imagem = render_pdf_page(str(pdf), indice, dpi)
    escala = dpi / 72
    diagramas = [(c.bbox_pdf[0] * escala, c.bbox_pdf[1] * escala, c.bbox_pdf[2] * escala, c.bbox_pdf[3] * escala) for c in detect_diagrams_in_pdf_page(str(pdf), indice, imagem)]
    caixas = linhas_da_folha(imagem, diagramas, dpi=dpi)
    with fitz.open(str(pdf)) as doc:
        palavras = doc[indice].get_text("words")
        sha_folha = _scan_ouro.sha_da_folha(doc, indice)
    return FolhaAberta(imagem, tuple(caixas), tuple(textos_da_camada(palavras, caixas, dpi=dpi)), sha_da_imagem(imagem), sha_folha)


# ------------------------------------------------------------------------------------------- o relógio


class Relogio:
    """O tempo de uma folha, que soma entre uma tecla e a seguinte, e nunca mais que `OCIOSO_MAXIMO` de uma vez. Puro: quem passa a hora é a tela."""

    def __init__(self, agora: float, *, inicial: float = 0.0) -> None:
        self._acumulado = float(inicial)
        self._ultima = float(agora)

    def _somado(self, agora: float) -> float:
        return self._acumulado + min(max(0.0, agora - self._ultima), OCIOSO_MAXIMO)

    def atividade(self, agora: float) -> None:
        self._acumulado = self._somado(agora)
        self._ultima = float(agora)

    def segundos(self, agora: float) -> float:
        return self._somado(agora)


def relogio_por_extenso(segundos: float) -> str:
    total = int(segundos)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


@dataclass(frozen=True)
class Custo:
    folhas_medidas: int
    media_em_segundos: float | None
    """`None` antes de `FOLHAS_PARA_ESTIMAR`: uma folha só não estima nada."""
    faltam: int
    """Quantas digitações faltam, as duplas incluídas."""
    horas_que_faltam: float | None
    horas_do_conjunto: float | None


def custo(concluidas: Sequence[FolhaDaPassada], *, folhas: int, duplas: int) -> Custo:
    """O que as folhas concluídas dizem do resto. É a resposta à D3, com o relógio de quem digitou."""
    medidas = [r.segundos for r in concluidas if r.completa and r.segundos > 0]
    total = folhas + duplas
    faltam = max(0, total - len([r for r in concluidas if r.completa]))
    if len(medidas) < FOLHAS_PARA_ESTIMAR:
        return Custo(len(medidas), None, faltam, None, None)
    media = sum(medidas) / len(medidas)
    return Custo(len(medidas), media, faltam, faltam * media / 3600, total * media / 3600)


def custo_por_extenso(c: Custo) -> str:
    if c.media_em_segundos is None:
        return f"Custo: {c.folhas_medidas} folha(s) medida(s); são precisas {FOLHAS_PARA_ESTIMAR} para estimar."
    return (
        f"Custo: {relogio_por_extenso(c.media_em_segundos)} por folha, em {c.folhas_medidas} folhas; "
        f"o conjunto dá {c.horas_do_conjunto:.1f} h, e faltam {c.horas_que_faltam:.1f} h ({c.faltam} digitações)."
    )


# ------------------------------------------------------------------------------------------- o acordo


def acordo_de_caractere(a: str, b: str, lingua: str = _regua.LINGUA_PADRAO) -> float:
    """1 − (S+D+I) / maior comprimento, na normalização `cru`: acento, pontuação e figurina contam."""
    x = unicodedata.normalize("NFC", _regua.normalizar(a, _regua.CRU, lingua))
    y = unicodedata.normalize("NFC", _regua.normalizar(b, _regua.CRU, lingua))
    if not x and not y:
        return 1.0
    erros = sum(1 for i, j in _regua.alinhar(x, y) if i < 0 or j < 0 or x[i] != y[j])
    return 1.0 - erros / max(len(x), len(y))


@dataclass(frozen=True)
class AcordoDaFolha:
    identidade: str
    folha: int
    producao: str
    acordo: float | None
    """`None` é folha que não se compara: as duas passadas olharam imagens diferentes."""
    motivo: str = ""

    @property
    def aprovada(self) -> bool:
        return self.acordo is not None and self.acordo >= ACORDO_MINIMO


@dataclass
class EstadoDaVerdade:
    """O que há de verdade na pasta, e o que falta para M3 e M4 terem número."""

    folhas: int = 0
    duplas: int = 0
    concluidas: dict[int, int] = field(default_factory=dict)
    acordos: list[AcordoDaFolha] = field(default_factory=list)
    prontas: set[tuple[str, int]] = field(default_factory=set)
    """Concluída na primeira passada e, se for dupla, com o acordo cumprido: é o que mede."""
    custo: Custo | None = None

    @property
    def sem_dados(self) -> bool:
        return not any(self.concluidas.values())

    @property
    def tem_numero(self) -> bool:
        return self.folhas > 0 and len(self.prontas) == self.folhas


def estado_da_verdade(manifesto: _scan_ouro.ScanOuro, pastas: Mapping[int, Mapping[tuple[str, int], FolhaDaPassada]]) -> EstadoDaVerdade:
    """Só folhas do manifesto e só as concluídas. Uma folha com o `sha_folha` de outra cópia do livro não conta."""
    estado = EstadoDaVerdade(folhas=len(manifesto.folhas), duplas=sum(f.dupla for f in manifesto.folhas))
    validas: dict[int, dict[tuple[str, int], FolhaDaPassada]] = {}
    for passada in PASSADAS:
        validas[passada] = {}
        for f in manifesto.folhas:
            registro = pastas.get(passada, {}).get((f.identidade, f.folha))
            # Concluída sem uma letra não é verdade: mediria o motor contra o vazio.
            if registro is None or not registro.completa or registro.sha_folha != f.sha_folha or not registro.texto.strip():
                continue
            _procedencia.exigir_transcricao(registro.procedencia, onde=f"scan-ouro, folha {f.folha}")
            validas[passada][(f.identidade, f.folha)] = registro
        estado.concluidas[passada] = len(validas[passada])
    for f in manifesto.folhas:
        chave = (f.identidade, f.folha)
        primeira = validas[PASSADAS[0]].get(chave)
        segunda = validas[PASSADAS[1]].get(chave)
        if not f.dupla:
            if primeira is not None:
                estado.prontas.add(chave)
            continue
        if primeira is None or segunda is None:
            continue
        if primeira.sha_imagem != segunda.sha_imagem:
            estado.acordos.append(AcordoDaFolha(f.identidade, f.folha, f.producao, None, "as passadas olharam imagens diferentes"))
            continue
        acordo = AcordoDaFolha(f.identidade, f.folha, f.producao, acordo_de_caractere(primeira.texto, segunda.texto, f.lingua))
        estado.acordos.append(acordo)
        if acordo.aprovada:
            estado.prontas.add(chave)
    todas = [r for passada in PASSADAS for r in validas[passada].values()]
    estado.custo = custo(todas, folhas=estado.folhas, duplas=estado.duplas)
    return estado


FRASE_SEM_NUMERO = "M3 e M4 sem número"


def relatorio_do_acordo(manifesto: _scan_ouro.ScanOuro, pasta: str | Path | None) -> tuple[list[str], int]:
    """As linhas do `--acordo` e o código de saída: 0 cumprido, 1 há folha que volta, 3 não há o que medir. **Sem dados não é zero**, é dizer."""
    linhas = [f"# scan-ouro: {len(manifesto.folhas)} folhas de {len(manifesto.livros)} livros, {sum(f.dupla for f in manifesto.folhas)} com dupla digitação"]
    if pasta is None or not any(caminho_da_passada(pasta, p).is_file() for p in PASSADAS):
        linhas.append(f"Sem transcrição nenhuma{'' if pasta is None else f' em {pasta}'}: o acordo não tem número, e não é zero.")
        linhas.append(f"{FRASE_SEM_NUMERO}: nenhuma folha tem verdade humana. Quem transcreve é a decisão D3 do roadmap.")
        return (linhas, 3)
    estado = estado_da_verdade(manifesto, ler_pasta(pasta))
    linhas.append(f"backup: {estado_do_backup(pasta)}")
    for passada in PASSADAS:
        ilegiveis = linhas_ilegiveis(pasta, passada)
        if ilegiveis:
            linhas.append(f"passada {passada}: {ilegiveis} linha(s) ilegível(is) ignorada(s); a folha delas volta à gravação anterior")
    linhas.append(f"concluídas: passada 1 {estado.concluidas[1]} de {estado.folhas}; passada 2 {estado.concluidas[2]} de {estado.duplas}")
    if estado.custo is not None:
        linhas.append(custo_por_extenso(estado.custo))
    for a in estado.acordos:
        if a.acordo is None:
            linhas.append(f"{a.identidade[:8]} folha {a.folha} ({a.producao}): volta, {a.motivo}")
        else:
            veredito = "ok" if a.aprovada else "volta para transcrição"
            linhas.append(f"{a.identidade[:8]} folha {a.folha} ({a.producao}): acordo {a.acordo:.4%} {veredito}")
    medidos = [a.acordo for a in estado.acordos if a.acordo is not None]
    if medidos:
        linhas.append(f"acordo: mínimo {min(medidos):.4%} em {len(medidos)} de {estado.duplas} folhas duplicadas; a meta é {ACORDO_MINIMO:.1%} em cada uma")
    else:
        linhas.append(f"acordo: nenhuma das {estado.duplas} folhas duplicadas tem as duas passadas, e o acordo não tem número.")
    if estado.tem_numero:
        linhas.append("Todas as folhas têm verdade: M3 e M4 podem ser medidos com --conjunto scan-ouro --transcricao.")
    else:
        linhas.append(f"{FRASE_SEM_NUMERO}: {len(estado.prontas)} de {estado.folhas} folhas têm verdade pronta.")
    if any(not a.aprovada for a in estado.acordos):
        return (linhas, 1)
    return (linhas, 0 if medidos else 3)


__all__ = [
    "ACORDO_MINIMO",
    "CAMADA",
    "DPI",
    "FRASE_SEM_NUMERO",
    "PASSADAS",
    "VAZIO",
    "AcordoDaFolha",
    "CadernoDaPassada",
    "Custo",
    "EstadoDaVerdade",
    "FolhaAberta",
    "FolhaDaPassada",
    "PastaNoRepositorio",
    "Relogio",
    "SemBackup",
    "abrir_folha",
    "acordo_de_caractere",
    "backup_declarado",
    "custo",
    "custo_por_extenso",
    "declarar_backup",
    "documento_da_partida",
    "estado_da_verdade",
    "estado_do_backup",
    "ler_pasta",
    "linhas_da_folha",
    "linhas_ilegiveis",
    "partidas_da_passada",
    "recorte_da_linha",
    "recusar_no_repositorio",
    "relatorio_do_acordo",
    "relogio_por_extenso",
    "sha_da_imagem",
    "textos_da_camada",
]
