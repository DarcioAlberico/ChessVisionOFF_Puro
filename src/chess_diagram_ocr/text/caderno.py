"""O caderno do livro: cada folha corrigida num arquivo, guardada sem pergunta e nunca podada (S-610).

**O trabalho da aba Texto morava no rascunho, e o rascunho é uma rede, não um lugar.** Ele nasceu
para sobreviver a um travamento entre duas gravações (S-255), e o uso fez dele o único lugar onde a
correção de um livro ficava: a pergunta "descarta as alterações?" a cada troca de folha, a poda a
oito por livro e a oferta de recuperação na releitura eram os três caminhos em que uma tarde de
correção sumia (o D3 de `docs/ROADMAP_MESA_DE_TEXTO.md`).

O caderno é o lugar. A aba continua lendo uma folha por vez -- o custo da leitura não muda --, mas o
que se lê e o que se corrige fica aqui, uma folha por arquivo:

    data/cadernos/<livro>_<identidade>/
        indice.json                 o estado de cada folha, sem abrir os `.cvtxt`
        folha-0012.cvtxt            a folha como ela está
        folha-0012.anterior.cvtxt   como ela estava quando a pessoa chegou da última vez
        folha-0012.lida.cvtxt       o que o motor leu, para "descartar as correções"
        caderno.lock                quem está escrevendo

O número do arquivo é o da folha **como a pessoa o diz** (1-based); a API fala em `pagina`, o
índice 0-based de `PaginaLida.pagina`, como o resto do programa.

## Seis decisões

**O livro é achado pela identidade do conteúdo, e o caminho é apelido.** Pelo caminho, mover o PDF
de pasta órfã o caderno, e o mesmo livro em duas pastas -- o acervo tem livros duplicados -- dá dois
cadernos que divergem. A identidade é o resumo do primeiro MiB do arquivo: o mesmo livro copiado
tem a mesma, e uma gravação incremental do PDF (anotação acrescentada no fim) também. A spec pedia
"número de folhas e resumo das primeiras folhas"; o número de folhas exigiria abrir o PDF com o
PyMuPDF a cada troca de livro, e o primeiro MiB já distingue dois livros -- dois PDFs diferentes não
começam pelos mesmos 1.048.576 bytes. Os caminhos de onde o livro foi aberto ficam no índice como
apelidos, e é por eles que um `.cvtxt` cujo livro sumiu ainda acha o caderno.

**Uma instância escreve.** O programa não tem trava de instância única, e duas janelas no mesmo
livro gravariam a mesma folha, com o índice lido-mudado-gravado pelas duas. O caderno cria
`caderno.lock` com criação exclusiva e o PID dentro; a segunda instância abre **só para leitura** e
diz por quê. A trava de um processo que não existe mais é retomada.

**Grava conferindo.** Em temporário, relê e compara com o que se quis gravar, e só então renomeia
por cima -- a escrita de recuperação do WordCraft. O arquivo anterior só sai quando o novo validou,
e falha de gravação **não apaga nada**: ela sobe como `OSError` para o rodapé.

**A primeira gravação de cada visita guarda a folha de antes** (`visitar`). Gravar sem perguntar
exige uma rede: `Ctrl+A` e `Del` e virar a página gravariam por cima da folha boa. A versão de
quando a pessoa chegou fica em `.anterior.cvtxt`, um nível só, e as gravações seguintes da mesma
visita só reescrevem a atual.

**A folha vazia não é gravada por cima de uma que tem texto** (`RECUSADA_VAZIA`). É o caso mais
barato de errar e o mais caro de perder.

**Sem poda.** O caderno é trabalho, não cache. Uma folha são poucos KB; um livro de 300 folhas cabe
em poucos MB.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_json
from ..config import DATA_DIR
from . import arquivo
from .rico import DocumentoRico

logger = logging.getLogger(__name__)

__all__ = [
    "CONFERIDA",
    "EDITADA",
    "ESPERA_DA_MUDANCA",
    "ESPERA_DO_CURSOR",
    "ESTADOS",
    "GRAVADA",
    "IGUAL",
    "LIDA",
    "PASTA_PADRAO",
    "RECUSADA_VAZIA",
    "SEM_FOLHA",
    "SOMENTE_LEITURA",
    "Caderno",
    "EstadoDaFolha",
    "abre_do_caderno",
    "abrir",
    "correcoes_por_extenso",
    "espera_restante",
    "frase_de_releitura",
    "identidade_de",
]

PASTA_PADRAO = DATA_DIR / "cadernos"
"""Onde os cadernos moram. Derivado de `DATA_DIR`, e não de `RAIZ / "data"`: é o que faz o
`CVOFF_DATA_DIR` da suíte desviá-lo sem linha nova."""

VERSAO_DO_INDICE = 1

LIDA = "lida"
EDITADA = "editada"
CONFERIDA = "conferida"
ESTADOS = (LIDA, EDITADA, CONFERIDA)
"""O estado de uma folha no índice: o motor leu, a mão corrigiu, alguém conferiu."""

GRAVADA = "gravada"
IGUAL = "igual"
RECUSADA_VAZIA = "recusada_vazia"
SOMENTE_LEITURA = "somente_leitura"
SEM_FOLHA = "sem_folha"
"""O que `Caderno.gravar` fez. Só `GRAVADA` e `IGUAL` querem dizer "o trabalho está no disco"."""

ESPERA_DA_MUDANCA = 2.5
ESPERA_DO_CURSOR = 1.5
"""A régua do salvamento automático, a do WordCraft (S-612): grava 2,5 s depois da última mudança
**e** com o cursor parado há 1,5 s. Quem está selecionando para negritar não está terminando."""

_BYTES_DA_IDENTIDADE = 1 << 20
_TAMANHO_DA_IDENTIDADE = 16
_LIMPEZA = re.compile(r"[^A-Za-z0-9_.-]+")
_INDICE = "indice.json"
_TRAVA = "caderno.lock"


def espera_restante(agora: float, *, mudou_em: float, cursor_em: float) -> float:
    """Quantos segundos faltam para o salvamento automático poder gravar. `0.0` é "grave agora"."""
    return max(0.0, mudou_em + ESPERA_DA_MUDANCA - agora, cursor_em + ESPERA_DO_CURSOR - agora)


def abre_do_caderno(estado: EstadoDaFolha, *, motor: str, modo_bloco: bool) -> bool:
    """"Ler folha" sobre uma folha que tem caderno abre o caderno, sem motor? (S-612)

    Sim, salvo num caso: a pessoa trocou o motor ou o modo bloco, e a folha está como o motor a
    deixou, sem correção. Quem mudou o motor quer a leitura nova, e não há trabalho a perder. Com
    correção -- ou conferida, ou sem motor anotado --, abre o caderno, e reler é "Ler de novo".
    """
    if estado.correcoes or estado.estado != LIDA or not estado.motor:
        return True
    return (estado.motor, bool(estado.modo_bloco)) == (motor, bool(modo_bloco))


def correcoes_por_extenso(quantas: int) -> str:
    return f"{quantas} correção" if quantas == 1 else f"{quantas} correções"


def frase_de_releitura(pagina: int, correcoes: int) -> str:
    """A única pergunta que sobra na troca de folha (S-612): **diz o tamanho da perda**."""
    return (
        f"A folha {pagina + 1} tem {correcoes_por_extenso(correcoes)}. Ler de novo guarda esta versão "
        "como anterior e abre a leitura nova."
    )


def identidade_de(pdf: str | Path) -> str | None:
    """O resumo do conteúdo do livro, ou `None` se ele não puder ser lido. Ver o cabeçalho."""
    try:
        with open(pdf, "rb") as fluxo:
            comeco = fluxo.read(_BYTES_DA_IDENTIDADE)
    except OSError as erro:
        logger.debug("O livro %s não pôde ser lido para achar o caderno: %s", pdf, erro)
        return None
    if not comeco:
        return None
    return hashlib.sha1(comeco).hexdigest()[:_TAMANHO_DA_IDENTIDADE]


@dataclass(frozen=True)
class EstadoDaFolha:
    """Uma linha do índice: o que se sabe de uma folha sem abrir o arquivo dela."""

    pagina: int
    estado: str
    motor: str = ""
    modo_bloco: bool = False
    gravada_em: str = ""
    correcoes: int = 0

    def para_json(self) -> dict[str, Any]:
        return {
            "estado": self.estado,
            "motor": self.motor,
            "modo_bloco": self.modo_bloco,
            "gravada_em": self.gravada_em,
            "correcoes": self.correcoes,
        }

    @classmethod
    def de_json(cls, pagina: int, dados: dict[str, Any]) -> EstadoDaFolha:
        estado = str(dados.get("estado", LIDA))
        return cls(
            pagina=pagina,
            estado=estado if estado in ESTADOS else LIDA,
            motor=str(dados.get("motor", "")),
            modo_bloco=bool(dados.get("modo_bloco", False)),
            gravada_em=str(dados.get("gravada_em", "")),
            correcoes=max(0, int(dados.get("correcoes", 0) or 0)),
        )


def _processo_vivo(pid: int) -> bool:
    """O processo `pid` ainda existe? Sem levantar: na dúvida, vivo -- a trava não é tomada à força.

    **No Windows não se usa `os.kill(pid, 0)`**: lá o sinal 0 é o `CTRL_C_EVENT`, e qualquer outro
    valor encerra o processo com `TerminateProcess`. A pergunta é feita ao sistema pelo `OpenProcess`.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        alca = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not alca:
            return False
        try:
            codigo = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(alca, ctypes.byref(codigo)):
                return True
            return codigo.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(alca)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _gravar_conferido(caminho: Path, texto: str) -> None:
    """Grava em temporário, relê e compara, e só então renomeia por cima. Ver o cabeçalho."""
    temporario = caminho.with_name(f".{caminho.name}.tmp")
    try:
        with open(temporario, "w", encoding="utf-8", newline="\n") as fluxo:
            fluxo.write(texto)
            fluxo.flush()
            os.fsync(fluxo.fileno())
        if temporario.read_text(encoding="utf-8") != texto:
            raise OSError(f"a gravação de {caminho.name} não conferiu com o que se quis gravar")
        os.replace(temporario, caminho)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise


def _texto_de(doc: DocumentoRico) -> str:
    return json.dumps(arquivo.para_json(doc), ensure_ascii=False, indent=2) + "\n"


def _tem_texto(doc: DocumentoRico) -> bool:
    return bool(doc.para_texto().strip())


class Caderno:
    """O caderno de um livro. Abra com `abrir`; feche com `fechar` para soltar a trava."""

    def __init__(self, pasta: Path, identidade: str, *, somente_leitura: bool = False, motivo: str = "") -> None:
        self.pasta = Path(pasta)
        self.identidade = identidade
        self.somente_leitura = somente_leitura
        """Outra instância do programa está escrevendo neste caderno. Ler pode; gravar não grava."""
        self.motivo = motivo
        """A frase que diz por que o caderno está só para leitura. Vazia quando ele grava."""
        self._folhas: dict[int, EstadoDaFolha] = {}
        self._apelidos: list[str] = []
        self._ultimos: dict[int, DocumentoRico] = {}
        """O que está no disco de cada folha, desde que este caderno o leu ou gravou. É contra ele
        que `difere` compara sem reler o arquivo a cada pausa da digitação."""
        self._por_girar: set[int] = set()
        self._tem_trava = False
        self._ler_indice()

    # --------------------------------------------------------------------------- caminhos

    def caminho(self, pagina: int, *, tipo: str = "") -> Path:
        """`folha-0012.cvtxt`, ou `folha-0012.<tipo>.cvtxt` para `anterior` e `lida`."""
        meio = f".{tipo}" if tipo else ""
        return self.pasta / f"folha-{int(pagina) + 1:04d}{meio}{arquivo.EXTENSAO}"

    @property
    def apelidos(self) -> tuple[str, ...]:
        """Os caminhos de onde este livro foi aberto, do mais antigo ao mais novo."""
        return tuple(self._apelidos)

    # ----------------------------------------------------------------------------- índice

    def _ler_indice(self) -> None:
        caminho = self.pasta / _INDICE
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            folhas = dados["folhas"]
            self._folhas = {int(k) - 1: EstadoDaFolha.de_json(int(k) - 1, v) for k, v in folhas.items()}
            self._apelidos = [str(a) for a in dados.get("apelidos", [])]
        except FileNotFoundError:
            self._refazer_indice()
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as erro:
            # O índice é derivado: os arquivos das folhas são o dado. Refazê-lo perde só o que
            # nenhum arquivo diz -- a marca de conferida e o motor de cada leitura.
            logger.warning("O índice do caderno %s não abriu (%s): refeito a partir das folhas.", self.pasta, erro)
            self._refazer_indice()

    def _refazer_indice(self) -> None:
        self._folhas = {}
        for caminho in sorted(self.pasta.glob(f"folha-[0-9][0-9][0-9][0-9]{arquivo.EXTENSAO}")):
            pagina = int(caminho.stem.split("-", 1)[1]) - 1
            try:
                quando = datetime.fromtimestamp(caminho.stat().st_mtime).isoformat(timespec="seconds")
            except OSError:  # pragma: no cover - arquivo sumiu entre o glob e o stat
                continue
            self._folhas[pagina] = EstadoDaFolha(pagina=pagina, estado=EDITADA, gravada_em=quando)

    def _gravar_indice(self) -> None:
        atomic_write_json(
            self.pasta / _INDICE,
            {
                "versao": VERSAO_DO_INDICE,
                "identidade": self.identidade,
                "apelidos": self._apelidos,
                "folhas": {str(p + 1): self._folhas[p].para_json() for p in sorted(self._folhas)},
            },
        )

    def anotar_apelido(self, pdf: str | Path) -> None:
        """Guarda de onde o livro foi aberto agora. Sem gravar o índice num caderno só de leitura."""
        texto = str(Path(pdf))
        if texto in self._apelidos:
            return
        self._apelidos.append(texto)
        if not self.somente_leitura:
            try:
                self._gravar_indice()
            except OSError as erro:  # o apelido é conforto; o caderno abre igual
                logger.debug("Apelido de %s não anotado: %s", self.pasta, erro)

    # ------------------------------------------------------------------------- consultas

    def folhas(self) -> tuple[EstadoDaFolha, ...]:
        """As folhas que têm caderno, por ordem. **Do índice**: nenhum `.cvtxt` é aberto."""
        return tuple(self._folhas[p] for p in sorted(self._folhas))

    def estado(self, pagina: int) -> EstadoDaFolha | None:
        return self._folhas.get(int(pagina))

    def conferidas(self) -> int:
        return sum(1 for f in self._folhas.values() if f.estado == CONFERIDA)

    def _carregar(self, caminho: Path) -> DocumentoRico | None:
        if not caminho.exists():
            return None
        try:
            return arquivo.carregar(caminho)
        except (OSError, ValueError) as erro:  # `arquivo.ArquivoInvalido` é um `ValueError`
            logger.warning("A folha %s do caderno não abriu: %s", caminho.name, erro)
            return None

    def folha(self, pagina: int) -> DocumentoRico | None:
        """A folha como ela está no caderno, ou `None` se ela não tem caderno."""
        doc = self._carregar(self.caminho(pagina))
        if doc is not None:
            self._ultimos[int(pagina)] = doc
        return doc

    def anterior(self, pagina: int) -> DocumentoRico | None:
        """Como a folha estava quando a pessoa chegou a ela da última vez (S-611)."""
        return self._carregar(self.caminho(pagina, tipo="anterior"))

    def lida(self, pagina: int) -> DocumentoRico | None:
        """O que o motor leu nesta folha, sem correção nenhuma (S-616)."""
        return self._carregar(self.caminho(pagina, tipo="lida"))

    def difere(self, doc: DocumentoRico) -> bool:
        """`doc` é diferente do que o caderno tem desta folha? É a pergunta "há o que gravar?"."""
        if doc.origem is None:
            return False
        pagina = int(doc.origem.pagina)
        if pagina not in self._ultimos:
            guardado = self._carregar(self.caminho(pagina))
            if guardado is None:
                return True
            self._ultimos[pagina] = guardado
        return self._ultimos[pagina] != doc

    # --------------------------------------------------------------------------- gravação

    def visitar(self, pagina: int) -> None:
        """A pessoa chegou a esta folha: a próxima gravação guarda a de antes como `anterior`."""
        self._por_girar.add(int(pagina))

    def gravar(self, doc: DocumentoRico, *, estado: str | None = None, motor: str = "", modo_bloco: bool | None = None, correcoes: int = 0) -> str:
        """Grava a folha deste documento e devolve o que fez -- uma das constantes do módulo.

        `estado` `None` é "o que a conta diz": `editada` com correção, senão o que já estava (ou
        `lida`). `motor` e `modo_bloco` vazios mantêm os da leitura que está no índice. Levanta
        `OSError` quando o disco recusa, **sem** ter apagado nada.
        """
        if doc.origem is None:
            return SEM_FOLHA
        if self.somente_leitura:
            return SOMENTE_LEITURA
        pagina = int(doc.origem.pagina)
        destino = self.caminho(pagina)
        if destino.exists() and not self.difere(doc):
            self._por_girar.discard(pagina)
            return IGUAL
        if not _tem_texto(doc):
            atual = self._ultimos.get(pagina) or self._carregar(destino)
            if atual is not None and _tem_texto(atual):
                return RECUSADA_VAZIA
        self.pasta.mkdir(parents=True, exist_ok=True)
        if pagina in self._por_girar and destino.exists():
            _gravar_conferido(self.caminho(pagina, tipo="anterior"), destino.read_text(encoding="utf-8"))
        _gravar_conferido(destino, _texto_de(doc))
        self._por_girar.discard(pagina)
        self._ultimos[pagina] = doc
        antes = self._folhas.get(pagina)
        if estado is None:
            estado = EDITADA if correcoes else (antes.estado if antes is not None and antes.estado != CONFERIDA else LIDA)
        self._folhas[pagina] = EstadoDaFolha(
            pagina=pagina,
            estado=estado,
            motor=motor or (antes.motor if antes is not None else ""),
            modo_bloco=bool(modo_bloco) if modo_bloco is not None else (antes.modo_bloco if antes is not None else False),
            gravada_em=datetime.now().isoformat(timespec="seconds"),
            correcoes=int(correcoes),
        )
        self._gravar_indice()
        return GRAVADA

    def guardar_leitura(self, doc: DocumentoRico, *, motor: str, modo_bloco: bool) -> str:
        """O motor acabou de ler esta folha: a leitura vira a folha do caderno e a sua `lida`.

        Uma folha que já tinha caderno vai para `anterior` antes -- é o "Ler de novo" (S-612), e a
        pergunta, quando há correção a perder, é de quem chama.
        """
        if doc.origem is None:
            return SEM_FOLHA
        if self.somente_leitura:
            return SOMENTE_LEITURA
        pagina = int(doc.origem.pagina)
        self.visitar(pagina)
        self._ultimos.pop(pagina, None)
        self.pasta.mkdir(parents=True, exist_ok=True)
        _gravar_conferido(self.caminho(pagina, tipo="lida"), _texto_de(doc))
        feito = self.gravar(doc, estado=LIDA, motor=motor, modo_bloco=modo_bloco, correcoes=0)
        if feito == IGUAL:  # a mesma leitura de antes: o índice ainda diz o motor desta
            self.marcar(pagina, LIDA, motor=motor, modo_bloco=modo_bloco)
        return feito

    def marcar(self, pagina: int, estado: str, *, motor: str = "", modo_bloco: bool | None = None) -> bool:
        """Muda o estado de uma folha no índice, sem tocar no arquivo dela. Devolve se mudou."""
        if estado not in ESTADOS:
            raise ValueError(f"estado de folha desconhecido: {estado!r} (são {', '.join(ESTADOS)})")
        antes = self._folhas.get(int(pagina))
        if antes is None or self.somente_leitura:
            return False
        self._folhas[int(pagina)] = EstadoDaFolha(
            pagina=antes.pagina,
            estado=estado,
            motor=motor or antes.motor,
            modo_bloco=antes.modo_bloco if modo_bloco is None else bool(modo_bloco),
            gravada_em=antes.gravada_em,
            correcoes=antes.correcoes,
        )
        self._gravar_indice()
        return True

    def trazer_rascunho(self, doc: DocumentoRico, quando: datetime, *, correcoes: int = 0) -> bool:
        """Um rascunho de antes do caderno (S-615): entra se a folha não tem caderno mais novo."""
        if doc.origem is None or self.somente_leitura:
            return False
        antes = self._folhas.get(int(doc.origem.pagina))
        if antes is not None and antes.gravada_em and antes.gravada_em >= quando.isoformat(timespec="seconds"):
            return False
        self.visitar(int(doc.origem.pagina))
        return self.gravar(doc, correcoes=correcoes) in (GRAVADA, IGUAL)

    # ------------------------------------------------------------------------------ trava

    def _travar(self) -> None:
        """Toma a trava do caderno, ou o põe só para leitura dizendo de quem ela é."""
        self.pasta.mkdir(parents=True, exist_ok=True)
        trava = self.pasta / _TRAVA
        for _tentativa in range(2):
            try:
                with open(trava, "x", encoding="utf-8") as fluxo:
                    fluxo.write(str(os.getpid()))
                self._tem_trava = True
                return
            except FileExistsError:
                try:
                    dono = int(trava.read_text(encoding="utf-8").strip() or 0)
                except (OSError, ValueError):
                    dono = 0
                if dono == os.getpid():
                    self._tem_trava = True
                    return
                if dono and _processo_vivo(dono):
                    self.somente_leitura = True
                    self.motivo = (
                        f"Outra janela do programa (processo {dono}) está gravando o caderno deste "
                        "livro: aqui ele abre só para leitura, e o que se corrigir vai para o rascunho."
                    )
                    return
                logger.info("Trava vencida do caderno %s (processo %s): retomada.", self.pasta, dono or "?")
                trava.unlink(missing_ok=True)
        self.somente_leitura = True  # pragma: no cover - outro processo tomou a trava no meio
        self.motivo = "A trava do caderno deste livro está em disputa: ele abre só para leitura."

    def fechar(self) -> None:
        """Solta a trava. Chamado na troca de livro e no fechamento; chamar duas vezes não faz mal."""
        if not self._tem_trava:
            return
        self._tem_trava = False
        try:
            (self.pasta / _TRAVA).unlink(missing_ok=True)
        except OSError as erro:  # pragma: no cover - arquivo preso pelo antivírus
            logger.debug("Trava do caderno %s não saiu: %s", self.pasta, erro)


def _pasta_do_livro(raiz: Path, pdf: Path, identidade: str) -> Path:
    """A pasta do caderno: a que já existe com esta identidade, ou uma nova com o nome do livro."""
    if raiz.exists():
        for achada in sorted(raiz.glob(f"*_{identidade}")):
            if achada.is_dir():
                return achada
    nome = _LIMPEZA.sub("_", pdf.stem)[:40] or "livro"
    return raiz / f"{nome}_{identidade}"


def abrir(pdf: str | Path, *, pasta: Path | None = None) -> Caderno | None:
    """O caderno do livro `pdf`, com a trava tomada. `None` quando o livro não pode ser lido."""
    raiz = Path(pasta) if pasta is not None else PASTA_PADRAO
    identidade = identidade_de(pdf)
    if identidade is None:
        return None
    caderno = Caderno(_pasta_do_livro(raiz, Path(pdf), identidade), identidade)
    try:
        caderno._travar()
    except OSError as erro:
        logger.warning("O caderno de %s não pôde ser criado: %s", pdf, erro)
        return None
    caderno.anotar_apelido(pdf)
    return caderno
