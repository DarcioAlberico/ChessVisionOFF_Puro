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
            timeout=float(str(data.get("timeout") or 30.0)),
            acknowledged=bool(data.get("acknowledged", False)),
        )


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
            movetime_ms=int(str(data.get("movetime_ms") or 800)),
            threads=int(str(data.get("threads") or 1)),
        )


@dataclass(frozen=True)
class Settings:
    """As preferências do usuário que não são estado de janela."""

    remote_fen: RemoteFenSettings = RemoteFenSettings()
    engine: EngineSettings = EngineSettings()

    def to_dict(self) -> dict[str, object]:
        return {
            "version": SETTINGS_VERSION,
            "remote_fen": self.remote_fen.to_dict(),
            "engine": self.engine.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Settings:
        def _secao(chave: str) -> Mapping[str, object]:
            bruto = data.get(chave)
            return bruto if isinstance(bruto, Mapping) else {}

        return cls(
            remote_fen=RemoteFenSettings.from_dict(_secao("remote_fen")),
            engine=EngineSettings.from_dict(_secao("engine")),
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

    ligado = env.get(ENV_REMOTE_ENABLED, "").strip().lower()
    if ligado in ("0", "false", "no", "off"):
        remoto = replace(remoto, enabled=False)
    elif ligado in ("1", "true", "yes", "on"):
        remoto = replace(remoto, enabled=True)

    return replace(settings, remote_fen=remoto)


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

    return apply_environment(Settings.from_dict(dados), env=env)


def save_settings(path: Path, settings: Settings) -> None:
    """Grava as preferências de forma atômica (S-25)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, settings.to_dict())
