"""O decodificador BZZ do DjVu, só para ler os nomes dentro do `DIRM`.

**Por que existe.** `djvu_io.paginas_soltas` precisa saber qual dicionário cada página cita, e esses
nomes estão comprimidos em BZZ. A `djvu-rs` decodifica BZZ por dentro e não o expõe; os nomes em
cp1251 são justamente o que ela descarta. Casar pela ordem do arquivo não basta: no
`Pachman_1957_.djvu` os dicionários estão fora de ordem, a contagem bate, e o dicionário errado
trocaria letras sem erro nenhum.

**Em Python puro de propósito.** O `DIRM` de um livro tem poucos KB, e um decodificador para o
conteúdo de página, que tem milhões de bits, não teria cabimento aqui. Esse fica na biblioteca.

**Origem.** Portado de `crates/djvu-bzz/src/decode.rs` e `crates/djvu-zp/src/lib.rs` da `djvu-rs`
(https://github.com/matyushkin/djvu-rs), MIT, Copyright (c) 2026 Lev Matyushkin. As tabelas são as
constantes do formato, da especificação DjVu v3 (https://www.sndjvu.org/spec.html), copiadas de
`crates/djvu-zp/src/tables.rs`.
"""

from __future__ import annotations

__all__ = ["decodificar"]

_TETO_DO_BLOCO = 4 * 1024 * 1024
_FOLGA_DEPOIS_DO_FIM = 16
"""Bytes de preenchimento tolerados depois do fim: passar disso é fluxo cortado, e não o fim dele."""

_PROB = (
    32768, 32768, 32768, 27581, 27581, 23877, 23877, 20921, 20921, 18451, 18451, 16341,
    16341, 14513, 14513, 12917, 12917, 11517, 11517, 10277, 10277, 9131, 9131, 8071,
    8071, 7099, 7099, 6213, 6213, 5411, 5411, 4691, 4691, 4047, 4047, 3477,
    3477, 2973, 2973, 2531, 2531, 2145, 2145, 1809, 1809, 1521, 1521, 1273,
    1273, 1061, 1061, 881, 881, 729, 729, 601, 601, 493, 493, 403,
    403, 329, 329, 267, 267, 213, 213, 165, 165, 123, 123, 87,
    87, 59, 59, 35, 35, 19, 19, 7, 7, 1, 1, 22165,
    9454, 32768, 3376, 18458, 1153, 13689, 378, 9455, 123, 6520, 40, 4298,
    13, 2909, 52, 1930, 160, 1295, 279, 856, 490, 564, 324, 371,
    564, 245, 851, 161, 1477, 282, 975, 426, 645, 646, 427, 979,
    282, 1477, 186, 2221, 122, 3276, 491, 4866, 742, 7041, 1118, 9455,
    1680, 10341, 2526, 14727, 3528, 11417, 4298, 15199, 2909, 22165, 1930, 32768,
    1295, 9454, 856, 3376, 564, 1153, 371, 378, 245, 123, 161, 40,
    282, 13, 426, 52, 646, 160, 979, 279, 1477, 490, 2221, 324,
    3276, 564, 4866, 851, 7041, 1477, 9455, 975, 11124, 645, 8221, 427,
    5909, 282, 4023, 186, 2663, 491, 1767, 742, 1174, 1118, 781, 1680,
    518, 2526, 341, 3528, 225, 11124, 148, 8221, 392, 5909, 594, 4023,
    899, 2663, 1351, 1767, 2018, 1174, 3008, 781, 4472, 518, 6618, 341,
    9455, 225, 12814, 148, 17194, 392, 17533, 594, 24270, 899, 32768, 1351,
    18458, 2018, 13689, 3008, 9455, 4472, 6520, 6618, 10341, 9455, 14727, 12814,
    11417, 17194, 15199, 17533, 22165, 24270, 32768, 32768, 22165, 18458, 18458, 32768,
    32768, 32768, 32768, 32768,
)

_THRESHOLD = (
    0, 0, 0, 4261, 4261, 7976, 7976, 11219, 11219, 14051, 14051, 16524,
    16524, 18685, 18685, 20573, 20573, 22224, 22224, 23665, 23665, 24923, 24923, 26021,
    26021, 26978, 26978, 27810, 27810, 28532, 28532, 29158, 29158, 29700, 29700, 30166,
    30166, 30568, 30568, 30914, 30914, 31210, 31210, 31463, 31463, 31678, 31678, 31861,
    31861, 32015, 32015, 32145, 32145, 32254, 32254, 32346, 32346, 32422, 32422, 32486,
    32486, 32538, 32538, 32581, 32581, 32619, 32619, 32653, 32653, 32682, 32682, 32707,
    32707, 32727, 32727, 32743, 32743, 32754, 32754, 32762, 32762, 32767, 32767, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0,
)

_MPS_NEXT = (
    84, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
    22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41,
    42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61,
    62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81,
    82, 81, 82, 9, 86, 5, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 82, 99, 76, 101,
    70, 103, 66, 105, 106, 107, 66, 109, 60, 111, 56, 69, 114, 65, 116, 61, 118, 57, 120, 53,
    122, 49, 124, 43, 72, 39, 60, 33, 56, 29, 52, 23, 48, 23, 42, 137, 38, 21, 140, 15,
    142, 9, 144, 141, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 70, 157, 66, 81, 62, 75,
    58, 69, 54, 65, 50, 167, 44, 65, 40, 59, 34, 55, 30, 175, 24, 177, 178, 179, 180, 181,
    182, 183, 184, 69, 186, 59, 188, 55, 190, 51, 192, 47, 194, 41, 196, 37, 198, 199, 72, 201,
    62, 203, 58, 205, 54, 207, 50, 209, 46, 211, 40, 213, 36, 215, 30, 217, 26, 219, 20, 71,
    14, 61, 14, 57, 8, 53, 228, 49, 230, 45, 232, 39, 234, 35, 138, 29, 24, 25, 240, 19,
    22, 13, 16, 13, 10, 7, 244, 249, 10, 89, 230, 0, 0, 0, 0, 0,
)

_LPS_NEXT = (
    145, 4, 3, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
    18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37,
    38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57,
    58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77,
    78, 79, 80, 85, 226, 6, 176, 143, 138, 141, 112, 135, 104, 133, 100, 129, 98, 127, 72, 125,
    102, 123, 60, 121, 110, 119, 108, 117, 54, 115, 48, 113, 134, 59, 132, 55, 130, 51, 128, 47,
    126, 41, 62, 37, 66, 31, 54, 25, 50, 131, 46, 17, 40, 15, 136, 7, 32, 139, 172, 9,
    170, 85, 168, 248, 166, 247, 164, 197, 162, 95, 160, 173, 158, 165, 156, 161, 60, 159, 56, 71,
    52, 163, 48, 59, 42, 171, 38, 169, 32, 53, 26, 47, 174, 193, 18, 191, 222, 189, 218, 187,
    216, 185, 214, 61, 212, 53, 210, 49, 208, 45, 206, 39, 204, 195, 202, 31, 200, 243, 64, 239,
    56, 237, 52, 235, 48, 233, 44, 231, 38, 229, 34, 227, 28, 225, 22, 223, 16, 221, 220, 63,
    8, 55, 224, 51, 2, 47, 87, 43, 246, 37, 244, 33, 238, 27, 236, 21, 16, 15, 8, 241,
    242, 7, 10, 245, 2, 1, 83, 250, 2, 143, 246, 0, 0, 0, 0, 0,
)


class _Zp:
    """O decodificador aritmético: cada bit lido estreita um intervalo de 16 bits."""

    def __init__(self, dados: bytes) -> None:
        if len(dados) < 2:
            raise ValueError("fluxo BZZ curto demais")
        self.dados = dados
        self.pos = 0
        self.a = 0
        self.buffer = 0
        self.bits = 0
        self.c = (self._byte() << 8) | self._byte()
        self._encher()
        self.cerca = min(self.c, 0x7FFF)

    def _byte(self) -> int:
        valor = self.dados[self.pos] if self.pos < len(self.dados) else 0xFF
        self.pos += 1
        return valor

    def _encher(self) -> None:
        while self.bits <= 24:
            self.buffer = ((self.buffer << 8) | self._byte()) & 0xFFFFFFFF
            self.bits += 8

    def _depois_do_desvio(self) -> None:
        self.cerca = min(self.c, 0x7FFF)

    def _renormalizar(self) -> None:
        deslocamento = 16 - (~self.a & 0xFFFF).bit_length()
        self.bits -= deslocamento
        self.a = (self.a << deslocamento) & 0xFFFF
        mascara = (1 << deslocamento) - 1
        self.c = ((self.c << deslocamento) | ((self.buffer >> self.bits) & mascara)) & 0xFFFF
        if self.bits < 16:
            self._encher()
        self._depois_do_desvio()

    def _um_bit(self) -> None:
        self.bits -= 1
        self.c = ((self.c << 1) | ((self.buffer >> self.bits) & 1)) & 0xFFFF
        if self.bits < 16:
            self._encher()
        self._depois_do_desvio()

    def bit(self, contextos: list[int], indice: int) -> int:
        estado = contextos[indice]
        provavel = estado & 1
        z = self.a + _PROB[estado]
        if z <= self.cerca:
            self.a = z
            return provavel
        z = min(z, 0x6000 + ((self.a + z) >> 2))
        if z > self.c:
            complemento = 0x10000 - z
            self.a = (self.a + complemento) & 0xFFFF
            self.c = (self.c + complemento) & 0xFFFF
            contextos[indice] = _LPS_NEXT[estado]
            self._renormalizar()
            return 1 - provavel
        if self.a >= _THRESHOLD[estado]:
            contextos[indice] = _MPS_NEXT[estado]
        self.a = (z << 1) & 0xFFFF
        self._um_bit()
        return provavel

    def bit_cru(self) -> int:
        z = (0x8000 + (self.a >> 1)) & 0xFFFF
        if z > self.c:
            complemento = 0x10000 - z
            self.a = (self.a + complemento) & 0xFFFF
            self.c = (self.c + complemento) & 0xFFFF
            self._renormalizar()
            return 1
        self.a = (z * 2) & 0xFFFF
        self._um_bit()
        return 0

    def bits_crus(self, quantos: int) -> int:
        n = 1
        for _ in range(quantos):
            n = (n << 1) | self.bit_cru()
        return n - (1 << quantos)

    def bits_de_contexto(self, contextos: list[int], base: int, quantos: int) -> int:
        n = 1
        for _ in range(quantos):
            n = (n << 1) | self.bit(contextos, base - 1 + n)
        return n - (1 << quantos)


def _posicao_mtf(zp: _Zp, contextos: list[int], ultima: int) -> int:
    """A posição na lista MTF. 256 é o marcador de fim de bloco."""
    nivel = min(ultima, 2)
    if zp.bit(contextos, nivel):
        return 0
    if zp.bit(contextos, 3 + nivel):
        return 1
    deslocamento = 6
    for largura in range(1, 8):
        if zp.bit(contextos, deslocamento):
            return (1 << largura) + zp.bits_de_contexto(contextos, deslocamento + 1, largura)
        deslocamento += 1 << largura
    return 256


def _bloco_mtf(zp: _Zp, contextos: list[int], tamanho: int) -> tuple[bytearray, int]:
    deslocamento_de_frequencia = 0
    if zp.bit_cru():
        deslocamento_de_frequencia = 1 + zp.bit_cru()
    ordem = list(range(256))
    frequencias = [0, 0, 0, 0]
    soma = 4
    ultima = 3
    marcador = -1
    saida = bytearray(tamanho)
    for indice in range(tamanho):
        if zp.pos - len(zp.dados) > _FOLGA_DEPOIS_DO_FIM:
            raise ValueError("fluxo BZZ cortado")
        posicao = _posicao_mtf(zp, contextos, ultima)
        ultima = posicao
        if posicao == 256:
            marcador = indice
            continue
        simbolo = ordem[posicao]
        saida[indice] = simbolo
        soma += soma >> deslocamento_de_frequencia
        if soma > 0x10000000:
            soma >>= 24
            frequencias = [f >> 24 for f in frequencias]
        combinada = soma + (frequencias[posicao] if posicao < 4 else 0)
        destino = posicao
        if destino >= 4:
            ordem[4 : destino + 1] = ordem[3:destino]
            destino = 3
        while destino > 0 and combinada >= frequencias[destino - 1]:
            ordem[destino] = ordem[destino - 1]
            frequencias[destino] = frequencias[destino - 1]
            destino -= 1
        ordem[destino] = simbolo
        frequencias[destino] = combinada
    if marcador < 0:
        raise ValueError("bloco BZZ sem o marcador de fim")
    return saida, marcador


def _bwt_inversa(dados: bytearray, marcador: int) -> bytes:
    contagem = [0] * 256
    ocorrencia = [0] * len(dados)
    for indice, valor in enumerate(dados):
        if indice != marcador:
            ocorrencia[indice] = contagem[valor]
            contagem[valor] += 1
    inicio = [0] * 256
    acumulado = 1  # a posição 0 da ordenação é a do marcador
    for valor in range(256):
        inicio[valor] = acumulado
        acumulado += contagem[valor]
    saida = bytearray(len(dados) - 1)
    seguinte = 0
    for restante in range(len(saida) - 1, -1, -1):
        valor = dados[seguinte]
        saida[restante] = valor
        seguinte = inicio[valor] + ocorrencia[seguinte]
    return bytes(saida)


def decodificar(dados: bytes) -> bytes:
    """Os bytes originais de um fluxo BZZ. `ValueError` se ele estiver malformado."""
    zp = _Zp(dados)
    contextos = [0] * 300  # compartilhados entre os blocos, zerados só no começo do fluxo
    saida = bytearray()
    while True:
        tamanho = zp.bits_crus(24)
        if tamanho == 0:
            return bytes(saida)
        if tamanho > _TETO_DO_BLOCO:
            raise ValueError(f"bloco BZZ de {tamanho} bytes: o fluxo não é BZZ")
        saida += _bwt_inversa(*_bloco_mtf(zp, contextos, tamanho))
