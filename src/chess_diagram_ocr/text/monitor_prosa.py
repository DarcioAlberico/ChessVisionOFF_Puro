"""O monitor da prosa sem referência: os sinais, o alarme que a medição deixou, e a folha-canário (S-763).

**Sinal que não correlaciona no dev não vira alarme.** A concordância glifo × leitor de linha mede o glifo, e não a saída: o *Minhas 60* tem glifo
a 6,92% e fusão a 0,27%. A densidade da S-710 vê perda total, e não texto ruim. Os dois foram medidos contra o CER por folha, por domínio, em
`docs/metrics/texto_confianca_2026-11-06.json`, com a regra escrita antes em `docs/metrics/texto_confianca_2026-11-06/monitor.py`. `ALARMES` é o que passou.

**A folha-canário é por língua, e é da camada.** A referência humana depende da S-703 e da D3, que ninguém transcreveu. Até lá o canário é uma folha de livro
digital admitido, relida a cada versão contra a camada, e **o rótulo diz isso**: `canário de camada, não humano`. Ele vê regressão do motor, e não diz quanto o motor
erra em scan. O manifesto (`assets/texto_prosa/canario.json`) só tem identidades, folhas e números: o texto da referência sai do PDF na hora, e fica fora do repositório.

**Alarme é aviso, e não muda texto.**
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..config import BUNDLE_ROOT
from . import confianca_palavra as _confianca
from . import fusao as _fusao

ROTULO_DO_CANARIO = "canário de camada, não humano"
"""Vai no manifesto, no relatório e na tela. Quando a S-703 tiver verdade, o canário troca de referência e este rótulo sai."""

MARGEM_DO_CANARIO = 0.002
"""Quanto o CER de prosa do canário pode subir, em fração, antes do alarme: duas décimas de ponto. Medido: a mesma versão relida dá diferença zero."""

CANARIO = "canario.json"

ALARMES: dict[str, dict[str, float]] = {}
"""`{domínio: {sinal: corte}}`. **Vazia de propósito, e sem quem a leia:** nenhum sinal passou da régua (ver a spec da S-763). Quem entrar aqui, com a medida, traz junto o chamador
que transforma o sinal em aviso. `test_text_monitor_prosa` compara esta tabela com o relatório."""


def caminho_do_canario() -> Path:
    return BUNDLE_ROOT / "assets" / "texto_prosa" / CANARIO


def _prosa(linhas: Sequence[Sequence[_fusao.Token]]) -> list[_fusao.Token]:
    return [t for linha in linhas for t in linha if _fusao.classe_do_token(t.texto) == _fusao.PROSA]


def concordancia(linhas: Sequence[Sequence[_fusao.Token]]) -> float:
    """A fração das palavras de prosa em que o glifo leu o mesmo que saiu. Sem prosa, `1,0`: não há o que discordar."""
    prosa = _prosa(linhas)
    return sum(1 for t in prosa if t.do_glifo == t.texto) / len(prosa) if prosa else 1.0


def erro_estimado(linhas: Sequence[Sequence[_fusao.Token]], *, existe: Callable[[str], bool], dominio: str) -> float:
    """A probabilidade média de erro das palavras de prosa, pelo calibrador da S-760."""
    prosa = _prosa(linhas)
    return sum(_confianca.erro_de(_confianca.atributos(t, existe=existe), dominio) for t in prosa) / len(prosa) if prosa else 0.0


def fracao_acima_do_corte(linhas: Sequence[Sequence[_fusao.Token]], *, existe: Callable[[str], bool], dominio: str) -> float:
    """Quantas palavras da folha passam do corte da S-761: o que a marca faria nela."""
    regra = _fusao.V3 if dominio == _confianca.SCAN else _fusao.V5
    erros = _confianca.erros_da_folha(linhas, existe=existe, dominio=dominio)
    total = sum(len(e) for e in erros)
    return sum(1 for e in erros for p in e if p >= _fusao.CORTE_DE_REVISAR[regra]) / total if total else 0.0


@dataclass(frozen=True)
class FolhaCanario:
    identidade: str
    folha: int
    """Base 1, como nos relatórios."""
    lingua: str
    cer_de_base: float
    motor: str = "fusao"


@dataclass(frozen=True)
class ResultadoDoCanario:
    folha: FolhaCanario
    cer: float

    @property
    def alarme(self) -> bool:
        return self.cer > self.folha.cer_de_base + MARGEM_DO_CANARIO


def carregar_canario(caminho: Path | str | None = None) -> tuple[FolhaCanario, ...]:
    """As folhas-canário. **Arquivo que diz outro rótulo não é canário de camada**, e a recusa é em voz alta."""
    dados = json.loads(Path(caminho or caminho_do_canario()).read_text(encoding="utf-8"))
    if dados.get("rotulo") != ROTULO_DO_CANARIO:
        raise ValueError(f"o manifesto do canário diz {dados.get('rotulo')!r}, e a referência dele é a camada: {ROTULO_DO_CANARIO}")
    return tuple(FolhaCanario(**f) for f in dados["folhas"])


def com_motor(folhas: Sequence[FolhaCanario], motor: str) -> tuple[FolhaCanario, ...]:
    """As folhas lidas por outro motor, e a linha do relatório diz qual: a regressão de mentira não sai rotulada `fusao`."""
    return tuple(replace(f, motor=motor) for f in folhas) if motor else tuple(folhas)


def conferir_canario(folhas: Sequence[FolhaCanario], medir: Callable[[FolhaCanario], float]) -> list[ResultadoDoCanario]:
    """Relê cada folha e compara com a base. `medir` é quem lê: aqui não há motor, e o teste passa um falso."""
    return [ResultadoDoCanario(f, float(medir(f))) for f in folhas]


def para_relatorio(resultados: Sequence[ResultadoDoCanario]) -> dict[str, Any]:
    """O que se publica: identidades e números, sem texto de livro."""
    return {
        "rotulo": ROTULO_DO_CANARIO,
        "margem": MARGEM_DO_CANARIO,
        "folhas": [
            {
                "identidade": r.folha.identidade, "folha": r.folha.folha, "lingua": r.folha.lingua, "motor": r.folha.motor,
                "cer_de_base": r.folha.cer_de_base, "cer": round(r.cer, 6), "alarme": r.alarme,
            }
            for r in resultados
        ],
    }


__all__ = [
    "ALARMES",
    "CANARIO",
    "MARGEM_DO_CANARIO",
    "ROTULO_DO_CANARIO",
    "FolhaCanario",
    "ResultadoDoCanario",
    "caminho_do_canario",
    "carregar_canario",
    "com_motor",
    "concordancia",
    "conferir_canario",
    "erro_estimado",
    "fracao_acima_do_corte",
    "para_relatorio",
]
