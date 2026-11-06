"""A degradação sintética (S-704): os mesmos bytes, a mesma geometria, e duas famílias que não se misturam."""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.text import degradacao

RAIZ = Path(__file__).resolve().parents[1]


def _folha() -> np.ndarray:
    """Uma folha branca com "tinta": listras e um quadrado, do tamanho de um recorte pequeno."""
    img = np.full((220, 160, 3), 255, np.uint8)
    img[20:30, 15:145] = 0
    img[50:54, 15:145] = 30
    img[80:140, 40:100] = 0
    return img


def _resumo(img: np.ndarray) -> str:
    return hashlib.sha256(img.tobytes()).hexdigest()


TODOS = (*degradacao.PERFIS, *degradacao.PERFIS_RESERVADOS)


class ReprodutibilidadeTests(unittest.TestCase):
    def test_mesma_folha_e_semente_mesmos_bytes(self) -> None:
        for perfil in TODOS:
            a = degradacao.aplicar(_folha(), perfil, semente=11)
            b = degradacao.aplicar(_folha(), perfil, semente=11)
            self.assertEqual(_resumo(a), _resumo(b), perfil)

    def test_mesmos_bytes_em_outro_processo(self) -> None:
        codigo = (
            "import hashlib,numpy as np;"
            "from chess_diagram_ocr.text import degradacao as d;"
            "i=np.full((220,160,3),255,np.uint8);i[20:30,15:145]=0;i[50:54,15:145]=30;i[80:140,40:100]=0;"
            "print(hashlib.sha256(d.aplicar(i,'medio',11).tobytes()).hexdigest());"
            "print(hashlib.sha256(d.aplicar(i,'fotocopia_media',11).tobytes()).hexdigest())"
        )
        saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(_resumo(degradacao.aplicar(_folha(), "medio", 11)), saida[0])
        self.assertEqual(_resumo(degradacao.aplicar(_folha(), "fotocopia_media", 11)), saida[1])

    def test_semente_diferente_muda_a_imagem(self) -> None:
        for perfil in TODOS:
            a = degradacao.aplicar(_folha(), perfil, semente=1)
            b = degradacao.aplicar(_folha(), perfil, semente=2)
            self.assertNotEqual(_resumo(a), _resumo(b), perfil)

    def test_semente_da_folha_e_fixa_e_nao_depende_da_ordem(self) -> None:
        self.assertEqual(degradacao.semente_da_folha("abc", 3), degradacao.semente_da_folha("abc", 3))
        self.assertNotEqual(degradacao.semente_da_folha("abc", 3), degradacao.semente_da_folha("abc", 4))
        self.assertNotEqual(degradacao.semente_da_folha("abc", 3), degradacao.semente_da_folha("abd", 3))
        self.assertEqual(2799426911787135842, degradacao.semente_da_folha("18d93bd07b7a826c", 155))

    def test_a_entrada_nao_e_alterada(self) -> None:
        folha = _folha()
        antes = _resumo(folha)
        for perfil in TODOS:
            degradacao.aplicar(folha, perfil, 5)
        self.assertEqual(antes, _resumo(folha))


class GeometriaTests(unittest.TestCase):
    def test_o_tamanho_nao_muda(self) -> None:
        for perfil in TODOS:
            self.assertEqual(_folha().shape, degradacao.aplicar(_folha(), perfil, 3).shape, perfil)

    def test_a_tinta_nao_anda(self) -> None:
        """A referência é a camada: uma tinta deslocada faria o CER medir a geometria. O quadrado fica a até 2 px."""
        for perfil in TODOS:
            cinza = cv2.medianBlur(degradacao.aplicar(_folha(), perfil, 3)[:, :, 0], 5)
            _, _, caixas, _ = cv2.connectedComponentsWithStats((cinza < 128).astype(np.uint8))
            x, y, largura, altura, _ = max(caixas[1:], key=lambda c: c[4])
            for achado, esperado in zip((x, y, x + largura, y + altura), (40, 80, 100, 140), strict=True):
                self.assertLessEqual(abs(int(achado) - esperado), 2, perfil)

    def test_a_folha_e_de_fato_degradada(self) -> None:
        for perfil in TODOS:
            self.assertGreater(float(np.abs(degradacao.aplicar(_folha(), perfil, 3).astype(float) - _folha()).mean()), 0.5, perfil)


class FamiliasTests(unittest.TestCase):
    def test_as_familias_nao_tem_nome_em_comum(self) -> None:
        self.assertEqual(set(), set(degradacao.PERFIS) & set(degradacao.PERFIS_RESERVADOS))
        self.assertEqual({degradacao.AUMENTO}, {degradacao.familia_do_perfil(p) for p in degradacao.PERFIS})
        self.assertEqual({degradacao.RESERVADA}, {degradacao.familia_do_perfil(p) for p in degradacao.PERFIS_RESERVADOS})

    def test_o_aumento_recusa_a_familia_reservada(self) -> None:
        self.assertEqual("medio", degradacao.perfil_de_aumento("medio"))
        with self.assertRaises(ValueError):
            degradacao.perfil_de_aumento("fotocopia_media")

    def test_os_geradores_sao_diferentes(self) -> None:
        """A reservada não reduz a folha: o ponto isolado sobrevive, e a do aumento o apaga na redução."""
        folha = np.full((220, 160, 3), 255, np.uint8)
        folha[100:102, 80:82] = 0
        saidas = [degradacao.aplicar(folha, p, 3) for p in ("medio", "fotocopia_leve")]
        self.assertGreater(int(saidas[0][100, 80, 0]), int(saidas[1][100, 80, 0]))

    def test_perfil_desconhecido_levanta(self) -> None:
        with self.assertRaises(ValueError):
            degradacao.aplicar(_folha(), "nenhum")


class CalibradoTests(unittest.TestCase):
    def test_o_calibrado_esta_escrito_como_pendente(self) -> None:
        with self.assertRaisesRegex(degradacao.PerfilPendente, "S-703"):
            degradacao.aplicar(_folha(), degradacao.CALIBRADO)
        self.assertIn("Recuo", degradacao.PENDENCIA_DO_CALIBRADO)


class PrototipoTests(unittest.TestCase):
    def test_a_familia_de_aumento_e_o_prototipo_byte_a_byte(self) -> None:
        caminho = RAIZ / "docs/metrics/texto_prosa_2026-10-30/degradar.py"
        spec = importlib.util.spec_from_file_location("degradar_prototipo", caminho)
        assert spec is not None and spec.loader is not None
        prototipo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prototipo)
        self.assertEqual(prototipo.PERFIS, degradacao.PERFIS)
        for perfil in degradacao.PERFIS:
            self.assertEqual(_resumo(prototipo.aplicar(_folha(), perfil, 154)), _resumo(degradacao.aplicar(_folha(), perfil, 154)), perfil)


if __name__ == "__main__":
    unittest.main()
