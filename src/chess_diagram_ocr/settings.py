"""Configuração do usuário — o que precisa ser declarado, não presumido (S-32).

**O problema que este módulo existe para resolver.** O botão "Corrigir Net" fazia upload da
imagem do tabuleiro para `helpman.komtera.lt` -- um host de terceiro, sem contrato -- sem
opt-in, sem configuração e sem uma linha no README. Quem clicava não tinha como saber que a
imagem saía da máquina, e quem não clicava não tinha como saber que o botão fazia isso.

**A regra aqui é: o padrão não envia nada.** Sem configuração explícita, o recurso está
desligado e o botão desabilitado. Habilitá-lo exige **declarar o endpoint** -- não há um
padrão embutido para ligar, porque um endpoint padrão é exatamente o que tornava a
dependência invisível. Quem quiser o serviço antigo escreve o endereço dele.

**Duas fontes, e a variável de ambiente ganha.** `data/settings.json` é o que a interface
grava; `CVOFF_REMOTE_FEN_URL` e `CVOFF_REMOTE_FEN_ENABLED` são para uso em script e CI, e
precisam poder desligar o recurso sem editar arquivo -- inclusive para o teste que prova
que nenhuma requisição parte no uso padrão.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

from .atomic_io import atomic_write_json
from .config import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "data" / "settings.json"

ENV_REMOTE_URL = "CVOFF_REMOTE_FEN_URL"
ENV_REMOTE_ENABLED = "CVOFF_REMOTE_FEN_ENABLED"

ENV_OCR_ENABLED = "CVOFF_OCR_ENABLED"
ENV_OCR_ENGINE = "CVOFF_OCR_ENGINE"
ENV_OCR_GLYPH_MODEL = "CVOFF_OCR_GLYPH_MODEL"

ENV_LOCAL_READER_PATH = "CVOFF_LOCAL_READER_PATH"
ENV_LOCAL_READER_ENABLED = "CVOFF_LOCAL_READER_ENABLED"

SETTINGS_VERSION = 1


@dataclass(frozen=True)
class RemoteFenSettings:
    """Segunda opinião de um serviço externo para a FEN de um diagrama.

    Todos os campos têm padrão desligado e vazio. Não é conservadorismo: um endpoint com
    valor padrão faria o recurso voltar a existir sem ninguém pedir, que era o defeito.
    """

    enabled: bool = False
    endpoint: str = ""
    timeout: float = 30.0

    acknowledged: bool = False
    """O usuário já viu o aviso de que a imagem sai da máquina e marcou "não perguntar
    novamente". Fica gravado por endpoint implicitamente: trocar o endereço zera o
    reconhecimento, porque o aviso nomeia o host."""

    @property
    def host(self) -> str:
        """O host do endpoint, que é o que o aviso mostra. Vazio se não há endpoint."""
        if not self.endpoint:
            return ""
        return urlparse(self.endpoint).netloc or self.endpoint

    @property
    def is_usable(self) -> bool:
        """Se o recurso pode ser acionado. Ligado **e** com endereço: um sem o outro não é."""
        return bool(self.enabled and self.endpoint.strip())

    def disabled_reason(self) -> str:
        """Por que o botão está desabilitado, em pt-BR, para o tooltip.

        Distingue "não configurado" de "configurado e desligado": são situações diferentes
        e a saída de cada uma é diferente.
        """
        if not self.endpoint.strip():
            return (
                "Correção remota não configurada. Ela envia a imagem do diagrama para um "
                "serviço externo, então precisa ser habilitada por você: informe o endpoint "
                f"em data/settings.json ou na variável de ambiente {ENV_REMOTE_URL}."
            )
        if not self.enabled:
            return f"Correção remota desligada. O endpoint configurado é {self.host}."
        return ""

    def consent_message(self) -> str:
        """O texto do aviso mostrado antes do primeiro envio. Nomeia o host de propósito."""
        return (
            f"A correção remota envia a imagem do diagrama para {self.host}.\n\n"
            "É um serviço de terceiro, fora do seu controle: a imagem deixa esta máquina e "
            "o que acontece com ela lá não é decidido por este programa.\n\n"
            "O reconhecimento local funciona sem isso. Deseja enviar?"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "endpoint": self.endpoint,
            "timeout": self.timeout,
            "acknowledged": self.acknowledged,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RemoteFenSettings:
        return cls(
            enabled=bool(data.get("enabled", False)),
            endpoint=str(data.get("endpoint", "") or "").strip(),
            timeout=_flutuante(data, "timeout", 30.0),
            acknowledged=bool(data.get("acknowledged", False)),
        )


def _inteiro(data: Mapping[str, object], chave: str, padrao: int) -> int:
    """O campo como `int`, ou o padrão **daquele campo**, com aviso nomeando-o (S-124).

    **Por campo, e não um `except ValueError` em volta do arquivo inteiro.** Um `movetime_ms`
    com `"rápido"` dentro não pode zerar também o `endpoint`, que é trabalho do usuário e a
    única preferência do arquivo que ninguém consegue recuperar sozinho.

    O que isto conserta é uma janela que **não abre**: `load_settings` capturava `OSError` e
    `json.JSONDecodeError`, mas `int(str(...))` levanta `ValueError` sobre um JSON
    sintaticamente perfeito. `app_tkinter` a chama no `__init__`, antes de a janela existir, e
    no bundle da S-55 (`console=False`) o traceback não aparece em lugar nenhum -- o programa
    simplesmente não abre.
    """
    bruto = data.get(chave)
    if bruto is None or bruto == "":
        return padrao
    try:
        return int(str(bruto))
    except (TypeError, ValueError):
        logger.warning("settings.json: %r não é um número inteiro em %r; usando %r.", bruto, chave, padrao)
        return padrao


def _flutuante(data: Mapping[str, object], chave: str, padrao: float) -> float:
    """Idem para `float`. Ver `_inteiro` para por que a coerção é por campo."""
    bruto = data.get(chave)
    if bruto is None or bruto == "":
        return padrao
    try:
        return float(str(bruto))
    except (TypeError, ValueError):
        logger.warning("settings.json: %r não é um número em %r; usando %r.", bruto, chave, padrao)
        return padrao


@dataclass(frozen=True)
class EngineSettings:
    """Motor de análise UCI (S-33). Caminho vazio significa "procurar sozinho"."""

    path: str = ""
    """Binário informado pelo usuário. Vazio: `engine.find_engine` procura no PATH e nos
    lugares conhecidos, e o recurso simplesmente não aparece se não achar."""

    movetime_ms: int = 800
    threads: int = 1

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "movetime_ms": self.movetime_ms, "threads": self.threads}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> EngineSettings:
        return cls(
            path=str(data.get("path", "") or "").strip(),
            movetime_ms=_inteiro(data, "movetime_ms", 800),
            threads=_inteiro(data, "threads", 1),
        )


DEFAULT_OCR_LANGUAGES: tuple[str, ...] = ("pt", "en", "es", "de")
"""Os quatro idiomas do acervo. Nem todo motor os usa -- ver `OcrSettings.languages`."""


@dataclass(frozen=True)
class OcrSettings:
    """Motor de OCR para as páginas sem camada de texto (S-42).

    **Desligado por padrão, e não por conservadorismo.** 20 dos 27 livros do acervo têm
    camada de texto; para eles o OCR é custo puro, porque a camada responde melhor e de
    graça. Ligá-lo é uma decisão de quem tem os 7 livros que não têm.

    O padrão de `engine` é `rapidocr` pelo motivo que a S-42 mede: é o único motor que não
    baixa nada na primeira execução -- os modelos vêm no wheel, e o `onnxruntime` que ele
    usa já é a dependência opcional da S-30. `easyocr` baixa ~100 MB no primeiro uso, o que
    contradiz a promessa do README de que nada sai da máquina no uso padrão; por isso ele é
    escolha explícita e nunca padrão.
    """

    enabled: bool = False
    engine: str = "rapidocr"
    languages: tuple[str, ...] = DEFAULT_OCR_LANGUAGES
    """Idiomas pedidos ao motor. **Só o `easyocr` os usa**: o RapidOCR embarca um modelo de
    reconhecimento fixo e o Tesseract precisa dos `traineddata` instalados à parte. Fica na
    configuração mesmo assim porque é a informação certa a declarar, e trocar de motor não
    deveria obrigar a redeclará-la."""

    glyph_model: str = ""
    """Os pesos do classificador de caracteres, para o motor `glifo` (S-179/S-182).

    **Sem padrão embutido, pela mesma razão do `LocalReaderSettings.path`**: um caminho presumido
    faz o recurso parecer quebrado em toda máquina que não o tem, em vez de simplesmente ausente.
    Vazio deixa `carregar_classificador` procurar o `.pt` ao lado de `models/char_meta.json` --
    que é o caminho de quem já pôs o arquivo lá.

    O que **não** é opcional é o metadado: `models/char_meta.json` é versionado, tem 10 KB e é o
    que descreve as classes -- **quantas** elas são vem dele, e muda a cada retreino (292 no porte
    de 2026-08-21, 314 no treino de 2026-08-23). É a assimetria entre os dois que torna o
    `modelo_sha256` necessário -- ver `text/modelo.py`."""

    def glyph_disabled_reason(self) -> str:
        """Por que o motor `glifo` não vai subir, em pt-BR. Vazio quando ele vai."""
        from .config import PROJECT_ROOT

        meta = PROJECT_ROOT / "models" / "char_meta.json"
        if not meta.exists():
            return (
                f"O motor `glifo` precisa de {meta.name}, que descreve as classes de "
                "caractere, e ele não está em models/."
            )
        candidato = Path(self.glyph_model.strip()) if self.glyph_model.strip() else meta.parent / "char_classifier.pt"
        if not candidato.exists():
            return (
                f"Os pesos do classificador de caracteres não estão em {candidato}. Eles não vêm "
                "no repositório (2,6 MB de binário; `*.pt` é ignorado). Aponte o arquivo em "
                f"data/settings.json (`ocr.glyph_model`) ou em {ENV_OCR_GLYPH_MODEL}."
            )
        return ""

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "engine": self.engine,
            "languages": list(self.languages),
            "glyph_model": self.glyph_model,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> OcrSettings:
        bruto = data.get("languages")
        idiomas = tuple(str(item).strip() for item in bruto if str(item).strip()) if isinstance(bruto, list) else ()
        return cls(
            enabled=bool(data.get("enabled", False)),
            engine=str(data.get("engine", "") or "rapidocr").strip().lower(),
            languages=idiomas or DEFAULT_OCR_LANGUAGES,
            glyph_model=str(data.get("glyph_model", "") or "").strip(),
        )


@dataclass(frozen=True)
class LocalReaderSettings:
    """Segunda opinião **local** para a posição de um diagrama (S-66).

    Irmã da `RemoteFenSettings` e diferente dela no que importa: aqui **nada sai da máquina**,
    então não há consentimento a pedir nem host a nomear. O que sobra de justificativa para
    ela ser opt-in é outro: são 232,8 MiB de pesos, e carregá-los sem ninguém pedir custa
    memória e ~7 s na primeira leitura.

    `path` aponta para um clone de `tsoj/Chess_diagram_to_FEN` com os pesos já baixados. Sem
    padrão embutido pela mesma razão do endpoint remoto: um caminho presumido faria o recurso
    parecer quebrado em toda máquina que não o tivesse, em vez de simplesmente ausente.
    """

    enabled: bool = False
    path: str = ""

    @property
    def is_usable(self) -> bool:
        return bool(self.enabled and self.path.strip())

    def disabled_reason(self) -> str:
        """Por que o botão está desabilitado, em pt-BR. Distingue as duas situações."""
        if not self.path.strip():
            return (
                "Segunda opinião não configurada. Ela lê o diagrama com um segundo modelo, "
                "local e offline: aponte um clone de tsoj/Chess_diagram_to_FEN com os pesos "
                f"baixados em data/settings.json ou em {ENV_LOCAL_READER_PATH}."
            )
        if not self.enabled:
            return f"Segunda opinião desligada. O leitor configurado está em {self.path}."
        return ""

    def to_dict(self) -> dict[str, object]:
        return {"enabled": self.enabled, "path": self.path}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> LocalReaderSettings:
        return cls(
            enabled=bool(data.get("enabled", False)),
            path=str(data.get("path", "") or "").strip(),
        )


@dataclass(frozen=True)
class Settings:
    """As preferências do usuário que não são estado de janela."""

    remote_fen: RemoteFenSettings = RemoteFenSettings()
    engine: EngineSettings = EngineSettings()
    ocr: OcrSettings = OcrSettings()
    local_reader: LocalReaderSettings = LocalReaderSettings()

    def to_dict(self) -> dict[str, object]:
        return {
            "version": SETTINGS_VERSION,
            "remote_fen": self.remote_fen.to_dict(),
            "engine": self.engine.to_dict(),
            "ocr": self.ocr.to_dict(),
            "local_reader": self.local_reader.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Settings:
        def _secao(chave: str) -> Mapping[str, object]:
            bruto = data.get(chave)
            return bruto if isinstance(bruto, Mapping) else {}

        return cls(
            remote_fen=RemoteFenSettings.from_dict(_secao("remote_fen")),
            engine=EngineSettings.from_dict(_secao("engine")),
            ocr=OcrSettings.from_dict(_secao("ocr")),
            local_reader=LocalReaderSettings.from_dict(_secao("local_reader")),
        )


def apply_environment(settings: Settings, env: Mapping[str, str] | None = None) -> Settings:
    """Deixa as variáveis de ambiente vencerem o arquivo.

    `CVOFF_REMOTE_FEN_ENABLED=0` desliga o recurso mesmo com o arquivo dizendo o contrário
    -- é o que permite a um script ou à CI garantir que nada sai da máquina sem depender do
    que está gravado em disco.
    """
    env = os.environ if env is None else env
    remoto = settings.remote_fen

    url = env.get(ENV_REMOTE_URL, "").strip()
    if url:
        # Endpoint vindo do ambiente é uma declaração explícita: liga junto, senão exigiria
        # duas variáveis para uma intenção só.
        remoto = replace(remoto, endpoint=url, enabled=True)

    ligado = _flag(env.get(ENV_REMOTE_ENABLED, ""))
    if ligado is not None:
        remoto = replace(remoto, enabled=ligado)

    ocr = settings.ocr
    motor = env.get(ENV_OCR_ENGINE, "").strip().lower()
    if motor:
        # Declarar o motor e ainda ter de ligá-lo seriam duas variáveis para uma intenção
        # só -- a mesma leitura que `CVOFF_REMOTE_FEN_URL` faz do endpoint.
        ocr = replace(ocr, engine=motor, enabled=True)

    glifo = env.get(ENV_OCR_GLYPH_MODEL, "").strip()
    if glifo:
        # Apontar os pesos ja e a intencao de usar o motor de glifo -- a mesma leitura que o
        # endpoint remoto, o motor de OCR e o caminho do leitor local fazem.
        ocr = replace(ocr, glyph_model=glifo, engine="glifo", enabled=True)

    ocr_ligado = _flag(env.get(ENV_OCR_ENABLED, ""))
    if ocr_ligado is not None:
        ocr = replace(ocr, enabled=ocr_ligado)

    leitor = settings.local_reader
    caminho = env.get(ENV_LOCAL_READER_PATH, "").strip()
    if caminho:
        # Mesma leitura que o endpoint e o motor de OCR: declarar o caminho ja e a intencao
        # de usar, e exigir uma segunda variavel so para ligar seria burocracia.
        leitor = replace(leitor, path=caminho, enabled=True)

    leitor_ligado = _flag(env.get(ENV_LOCAL_READER_ENABLED, ""))
    if leitor_ligado is not None:
        leitor = replace(leitor, enabled=leitor_ligado)

    return replace(settings, remote_fen=remoto, ocr=ocr, local_reader=leitor)


def _flag(raw: str) -> bool | None:
    """`True`/`False` para as grafias aceitas, `None` quando a variável não diz nada."""
    valor = raw.strip().lower()
    if valor in ("0", "false", "no", "off"):
        return False
    if valor in ("1", "true", "yes", "on"):
        return True
    return None


def load_settings(
    path: Path = DEFAULT_SETTINGS_PATH,
    *,
    env: Mapping[str, str] | None = None,
) -> Settings:
    """Lê as preferências. Arquivo ausente ou corrompido cai no padrão, que não envia nada.

    Falhar para o lado do padrão é seguro aqui exatamente porque o padrão é "desligado":
    um JSON truncado não pode ligar um envio para fora.
    """
    dados: Mapping[str, object] = {}
    if path.exists():
        try:
            carregado = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(carregado, Mapping):
                dados = carregado
            else:
                logger.warning("settings.json nao contem um objeto; usando os padroes.")
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Nao foi possivel ler %s (%s); usando os padroes.", path, exc)

    try:
        return apply_environment(Settings.from_dict(dados), env=env)
    except Exception:  # noqa: BLE001 - ver abaixo: preferencia nenhuma vale a janela nao abrir
        # **Rede de seguranca, e nao o conserto** (S-124). O conserto e a coercao por campo
        # (`_inteiro`, `_flutuante`), que preserva o resto do arquivo; isto aqui cobre a forma
        # que ninguem previu -- uma secao que e lista, um valor que e dicionario -- e existe
        # porque o custo do erro e desproporcional: `app_tkinter` chama isto no `__init__`,
        # antes de a janela existir, e no bundle da S-55 (`console=False`) o traceback nao
        # aparece em lugar nenhum. O programa nao abre e nao diz por que.
        logger.exception("settings.json tem uma forma inesperada; abrindo com os padroes.")
        return apply_environment(Settings(), env=env)


def save_settings(path: Path, settings: Settings) -> None:
    """Grava as preferências de forma atômica (S-25)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, settings.to_dict())
