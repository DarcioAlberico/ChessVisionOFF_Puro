"""Escaneamento simulado de uma folha digital, sem mexer na geometria (S-704).

**A geometria fica intacta** (sem rotação nem deslocamento) para a camada do PDF continuar sendo a referência
exata da mesma tinta. É por isso que esta fatia pode dizer um CER contra a camada sem transcrição humana.

**Duas famílias, com geradores diferentes.** `AUMENTO` é a dos perfis de 2026-10-30 (reduz, desfoca, soma ruído
gaussiano, manchas soltas, JPEG): é a que o aumento de dados da Fase 105 pode ver. `RESERVADA` é outra física, a
da fotocópia (a tinta borra de modo desigual, o fundo tem sombra de baixa frequência, o contraste amassa, a poeira vem em
grumos e o sensor deixa estrias), com outro gerador de números (`MT19937`), e **é só para medir a M5**:
`perfil_de_aumento` recusa os nomes dela. Medir no que o treino viu é jogar em casa.

**O perfil `calibrado` está pendente, e isso é escrito.** Ele depende da S-703: é o perfil que faz o Tesseract errar no
ouro degradado o mesmo que no scan-ouro-dev (±25% relativo), e o scan-ouro são ~15 horas humanas (a decisão D3). Sem ela,
vale o recuo da seção 7 do roadmap: a M5 não tem número, `aplicar(..., "calibrado")` levanta `PerfilPendente`, e o
relatório diz que os perfis publicados **não foram calibrados contra nada**.

Usado só como fatia, nunca somado ao ouro. Sem chamador em produção.
"""

from __future__ import annotations

import hashlib

import cv2
import numpy as np

AUMENTO = "aumento"
RESERVADA = "reservada"

PERFIS: dict[str, tuple[float, float, int, int, int, int]] = {
    #         fator  desfoque ruído jpeg tinta manchas
    "leve": (0.68, 0.6, 6, 60, 0, 0),
    "medio": (0.50, 0.9, 10, 45, 0, 200),
    "pesado": (0.42, 1.1, 14, 35, 0, 600),
    "fina": (0.55, 0.8, 8, 45, -1, 100),
    "grossa": (0.55, 0.8, 8, 45, 1, 100),
}
"""A família `AUMENTO`, com os números de `texto_prosa_2026-10-30/degradar.py`. `tinta`: −1 fina, +1 grossa."""

PERFIS_RESERVADOS: dict[str, tuple[float, float, float, float, float, int]] = {
    #                    sombra borrão contraste estria grumos(por Mpx) tamanho do grumo
    "fotocopia_leve": (18.0, 0.55, 0.92, 1.5, 40.0, 2),
    "fotocopia_media": (32.0, 0.85, 0.82, 3.0, 120.0, 3),
    "fotocopia_pesada": (48.0, 1.15, 0.70, 5.0, 300.0, 4),
}
"""A família `RESERVADA`. Nenhum destes números saiu de scan real: a calibração é o perfil `calibrado`, pendente."""

CALIBRADO = "calibrado"
PENDENCIA_DO_CALIBRADO = (
    "o perfil calibrado depende da S-703 (scan-ouro com verdade humana, decisão D3). Recuo da seção 7 do roadmap: a M5 "
    "fica sem número, e os perfis publicados dizem que não foram calibrados."
)


class PerfilPendente(RuntimeError):
    """O perfil existe no plano e ainda não pode existir aqui."""


def familia_do_perfil(perfil: str) -> str:
    if perfil in PERFIS:
        return AUMENTO
    if perfil in PERFIS_RESERVADOS:
        return RESERVADA
    if perfil == CALIBRADO:
        raise PerfilPendente(PENDENCIA_DO_CALIBRADO)
    raise ValueError(f"perfil de degradação desconhecido: {perfil!r}")


def perfil_de_aumento(perfil: str) -> str:
    """O perfil que o aumento de dados pode usar. O da família reservada levanta: a M5 não pode ter visto o treino."""
    if familia_do_perfil(perfil) != AUMENTO:
        raise ValueError(f"o perfil {perfil!r} é da família reservada à M5, e nenhum treino pode vê-lo")
    return perfil


def semente_da_folha(identidade: str, folha: int) -> int:
    """A semente de uma folha (base 1): não depende da ordem dos livros nem de que outras folhas estão na corrida."""
    resumo = hashlib.sha256(f"{identidade}:{folha}".encode()).digest()
    return int.from_bytes(resumo[:8], "big")


def aplicar(img_rgb: np.ndarray, perfil: str, semente: int = 0) -> np.ndarray:
    """A folha degradada, do mesmo tamanho. Mesma folha, perfil e semente dão os mesmos bytes."""
    if familia_do_perfil(perfil) == AUMENTO:
        return _digitalizacao(img_rgb, perfil, semente)
    return _fotocopia(img_rgb, perfil, semente)


def _digitalizacao(img_rgb: np.ndarray, perfil: str, semente: int) -> np.ndarray:
    """Byte a byte a de 2026-10-30 com a mesma semente: o `degradado_medio` publicado se reproduz por aqui."""
    fator, desfoque, ruido, jpeg, tinta, manchas = PERFIS[perfil]
    rng = np.random.default_rng(semente)
    cinza = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    altura, largura = cinza.shape
    if tinta:
        nucleo = np.ones((2, 2), np.uint8)
        cinza = cv2.dilate(cinza, nucleo) if tinta < 0 else cv2.erode(cinza, nucleo)  # fundo branco: dilatar afina a tinta
    p = cv2.resize(cinza, (int(largura * fator), int(altura * fator)), interpolation=cv2.INTER_AREA)
    p = cv2.GaussianBlur(p, (0, 0), desfoque)
    p = p.astype(np.float32) + rng.normal(0, ruido, p.shape)
    if manchas:
        ys = rng.integers(0, p.shape[0], manchas)
        xs = rng.integers(0, p.shape[1], manchas)
        p[ys, xs] = rng.uniform(0, 120, manchas)
    p = np.clip(p, 0, 255).astype(np.uint8)
    _, codificada = cv2.imencode(".jpg", p, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    lida = cv2.imdecode(codificada, cv2.IMREAD_GRAYSCALE)
    if lida is None:
        raise ValueError("o JPEG que acabou de ser gravado não abriu")
    return cv2.cvtColor(cv2.resize(lida, (largura, altura), interpolation=cv2.INTER_LINEAR), cv2.COLOR_GRAY2RGB)


def _fotocopia(img_rgb: np.ndarray, perfil: str, semente: int) -> np.ndarray:
    """A outra física: nada aqui reduz a folha, e nada passa por JPEG. Ver o cabeçalho."""
    sombra, borrao, contraste, estria, grumos, tamanho = PERFIS_RESERVADOS[perfil]
    rng = np.random.Generator(np.random.MT19937(semente))
    cinza = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    altura, largura = cinza.shape
    # A tinta borra de modo desigual: um mapa de baixa frequência mistura a folha nítida e a borrada.
    borrada = cv2.GaussianBlur(cinza, (0, 0), max(0.3, borrao))
    desigual = _baixa_frequencia(rng, altura, largura, 40)
    desigual = (desigual - desigual.min()) / max(1e-6, float(np.ptp(desigual)))
    p = cinza * (1 - desigual) + borrada * desigual
    # O contraste amassa em torno do branco, e o fundo ganha a sombra da encadernação.
    p = 255 - (255 - p) * contraste
    p = p - _baixa_frequencia(rng, altura, largura, 8) * sombra
    # As estrias do sensor: uma coluna inteira um pouco mais clara ou mais escura.
    p = p + rng.normal(0, estria, largura)[None, :]
    # A poeira vem em grumos, e não em pontos soltos.
    n = int(grumos * altura * largura / 1e6)
    if n:
        ys = rng.integers(0, altura, n)
        xs = rng.integers(0, largura, n)
        lados = rng.integers(1, tamanho + 1, n)
        tons = rng.uniform(20, 140, n)
        for y, x, lado, tom in zip(ys, xs, lados, tons, strict=True):
            p[y: y + lado, x: x + lado] = tom
    p = np.clip(p, 0, 255).astype(np.uint8)
    return cv2.cvtColor(p, cv2.COLOR_GRAY2RGB)


def _baixa_frequencia(rng: np.random.Generator, altura: int, largura: int, celulas: int) -> np.ndarray:
    """Ruído suave em [0, 1]: uma grade pequena sorteada, ampliada com interpolação cúbica."""
    grade = rng.random((celulas, celulas), dtype=np.float32)
    return np.clip(cv2.resize(grade, (largura, altura), interpolation=cv2.INTER_CUBIC), 0.0, 1.0)


__all__ = [
    "AUMENTO",
    "CALIBRADO",
    "PENDENCIA_DO_CALIBRADO",
    "PERFIS",
    "PERFIS_RESERVADOS",
    "RESERVADA",
    "PerfilPendente",
    "aplicar",
    "familia_do_perfil",
    "perfil_de_aumento",
    "semente_da_folha",
]
