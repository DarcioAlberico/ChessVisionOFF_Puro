"""A mesma imagem sob dois rótulos: achar, julgar, mover, desfazer (S-202).

**Os testes daqui montam a base no disco.** O que este módulo pode errar é mover o arquivo
errado, mover o certo para o lugar errado, ou aplicar uma decisão que descreve outra base — e os
três só aparecem com arquivo de verdade.

E há um teste que não é sobre código: `test_as_decisoes_do_repositorio_dizem_todas_por_que`
lê o `data/texto_conflitos.json` real. Ele existe porque aquele arquivo é **julgamento humano**,
e o defeito que ele pode ter não é de sintaxe: é uma linha sem motivo, que daqui a seis meses
ninguém consegue distinguir de um chute.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from chess_diagram_ocr.text.conflitos import (
    Conflito,
    DecisaoInvalida,
    achar,
    aplicar,
    conferir,
    desfazer,
    ler_decisoes,
)

DECISOES_REAIS = Path(__file__).resolve().parents[1] / "data" / "texto_conflitos.json"


def png(imagem: np.ndarray) -> bytes:
    import cv2

    ok, buffer = cv2.imencode(".png", imagem)
    assert ok
    return bytes(buffer.tobytes())


class BaseDeTeste(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        self.base = self.raiz / "base"
        self.quarentena = self.raiz / "quarentena"
        self.addCleanup(self._tmp.cleanup)
        self.aleatorio = np.random.default_rng(0)

    def escrever(self, classe: str, nome: str, imagem: np.ndarray) -> Path:
        pasta = self.base / classe
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"{nome}.png"
        caminho.write_bytes(png(imagem))
        return caminho

    def ruido(self) -> np.ndarray:
        return self.aleatorio.integers(0, 255, (32, 32), dtype=np.uint8)

    def base_com_um_conflito(self) -> np.ndarray:
        """`digit_1` com 3 cópias da mesma imagem, `lower_l` com 1 cópia dela e mais uma sua."""
        disputada = np.full((32, 32), 77, np.uint8)
        for i in range(3):
            self.escrever("digit_1", f"d{i}", disputada)
        self.escrever("lower_l", "l0", disputada)
        self.escrever("lower_l", "l1", self.ruido())
        self.escrever("digit_1", "d9", self.ruido())
        return disputada


class AcharTests(BaseDeTeste):
    def test_acha_a_mesma_imagem_em_duas_classes(self) -> None:
        self.base_com_um_conflito()
        achados = achar(self.base, tarefas=2)
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0].rotulos, {"digit_1": 3, "lower_l": 1})
        self.assertEqual(achados[0].total, 4)

    def test_copia_dentro_da_mesma_classe_nao_e_conflito(self) -> None:
        """Redundância não é contradição -- é o eixo inteiro deste módulo."""
        igual = np.full((32, 32), 10, np.uint8)
        for i in range(5):
            self.escrever("lower_a", f"a{i}", igual)
        self.assertEqual(achar(self.base, tarefas=2), [])

    def test_imagem_parecida_mas_nao_identica_nao_e_conflito(self) -> None:
        """O critério é byte a byte. A quase-duplicata é outro item (S-202, segunda metade)."""
        base = np.full((32, 32), 10, np.uint8)
        quase = base.copy()
        quase[0, 0] = 11
        self.escrever("lower_a", "a", base)
        self.escrever("lower_o", "o", quase)
        self.assertEqual(achar(self.base, tarefas=2), [])

    def test_pasta_que_nao_e_classe_e_ignorada(self) -> None:
        disputada = self.base_com_um_conflito()
        pasta = self.base / "uma pasta qualquer"
        pasta.mkdir(parents=True)
        (pasta / "x.png").write_bytes(png(disputada))
        achados = achar(self.base, tarefas=2)
        self.assertEqual(achados[0].rotulos, {"digit_1": 3, "lower_l": 1})


class DecisoesTests(BaseDeTeste):
    def _decisoes(self, **campos: object) -> Path:
        achados = achar(self.base, tarefas=2)
        linha = {"sha256": achados[0].sha256, "rotulos": achados[0].rotulos, "motivo": "porque sim"}
        linha.update(campos)
        caminho = self.raiz / "decisoes.json"
        caminho.write_text(json.dumps([linha]), encoding="utf-8")
        return caminho

    def test_a_decisao_sem_motivo_e_recusada(self) -> None:
        """Uma decisão sem motivo é indistinguível de um chute, e o arquivo é trabalho humano."""
        self.base_com_um_conflito()
        caminho = self._decisoes(vencedor="digit_1", motivo="   ")
        with self.assertRaises(DecisaoInvalida) as erro:
            ler_decisoes(caminho)
        self.assertIn("por quê", str(erro.exception))

    def test_o_json_quebrado_diz_o_que_esta_errado_em_pt_br(self) -> None:
        caminho = self.raiz / "d.json"
        caminho.write_text("{isto nao e json", encoding="utf-8")
        with self.assertRaises(DecisaoInvalida) as erro:
            ler_decisoes(caminho)
        self.assertIn("JSON", str(erro.exception))

    def test_o_grupo_que_mudou_no_disco_nao_e_aplicado(self) -> None:
        """A trava que impede aplicar um julgamento a uma base que não é a julgada.

        Se a contagem por classe mudou, a decisão descreve outra coisa -- e mover assim mesmo
        tiraria da base arquivo que ninguém olhou.
        """
        self.base_com_um_conflito()
        caminho = self._decisoes(vencedor="digit_1")
        self.escrever("digit_1", "d_novo", np.full((32, 32), 77, np.uint8))  # muda a contagem
        plano = conferir(achar(self.base, tarefas=2), ler_decisoes(caminho))
        self.assertEqual(len(plano.divergentes), 1)
        self.assertEqual(plano.mover, [])

    def test_o_grupo_sem_decisao_nao_e_aplicado(self) -> None:
        self.base_com_um_conflito()
        plano = conferir(achar(self.base, tarefas=2), {})
        self.assertEqual(len(plano.sem_decisao), 1)
        self.assertEqual(plano.mover, [])


class AplicarTests(BaseDeTeste):
    def test_o_perdedor_sai_e_o_vencedor_fica(self) -> None:
        self.base_com_um_conflito()
        achados = achar(self.base, tarefas=2)
        decisoes = {achados[0].sha256: {"vencedor": "digit_1", "rotulos": achados[0].rotulos, "motivo": "e um 1"}}
        aplicar(conferir(achados, decisoes), self.base, self.quarentena)

        self.assertEqual(len(list((self.base / "digit_1").iterdir())), 4)
        self.assertEqual([p.name for p in (self.base / "lower_l").iterdir()], ["l1.png"])
        self.assertTrue((self.quarentena / "lower_l" / "l0.png").exists())

    def test_a_maioria_perde_quando_a_decisao_diz_que_perde(self) -> None:
        """A ficha 15 da base real: 30 recortes em `lower_f` contra 2 em `ligature_ft`, e o
        desenho é um "ft". Uma regra de maioria consagraria o erro com 15 contra 1."""
        self.base_com_um_conflito()
        achados = achar(self.base, tarefas=2)
        decisoes = {achados[0].sha256: {"vencedor": "lower_l", "rotulos": achados[0].rotulos, "motivo": "e um l"}}
        aplicar(conferir(achados, decisoes), self.base, self.quarentena)
        self.assertEqual([p.name for p in (self.base / "digit_1").iterdir()], ["d9.png"])
        self.assertEqual(len(list((self.quarentena / "digit_1").iterdir())), 3)

    def test_o_indecidivel_sai_inteiro(self) -> None:
        """Sem vencedor, os dois lados saem: metade dos 83 da base real é assim.

        Custa **uma** amostra ao treino, porque o treino usa um recorte por grupo de cópia
        exata -- e deixar a contradição custa mais.
        """
        self.base_com_um_conflito()
        achados = achar(self.base, tarefas=2)
        decisoes = {achados[0].sha256: {"vencedor": None, "rotulos": achados[0].rotulos, "motivo": "1 ou l"}}
        plano = conferir(achados, decisoes)
        self.assertEqual(plano.por_motivo, {"indecidivel": 4})
        aplicar(plano, self.base, self.quarentena)
        self.assertEqual(achar(self.base, tarefas=2), [])
        self.assertEqual([p.name for p in (self.base / "digit_1").iterdir()], ["d9.png"])

    def test_nada_e_apagado_e_o_desfazer_devolve_tudo(self) -> None:
        """A lei desta fase: quarentena, nunca lixo. E a volta tem de existir de verdade."""
        self.base_com_um_conflito()
        antes = sorted(p.relative_to(self.base).as_posix() for p in self.base.rglob("*.png"))
        achados = achar(self.base, tarefas=2)
        decisoes = {achados[0].sha256: {"vencedor": "digit_1", "rotulos": achados[0].rotulos, "motivo": "e um 1"}}
        manifesto = aplicar(conferir(achados, decisoes), self.base, self.quarentena)

        self.assertEqual(desfazer(manifesto), 1)
        depois = sorted(p.relative_to(self.base).as_posix() for p in self.base.rglob("*.png"))
        self.assertEqual(antes, depois)

    def test_o_manifesto_registra_o_que_de_fato_saiu(self) -> None:
        self.base_com_um_conflito()
        achados = achar(self.base, tarefas=2)
        decisoes = {achados[0].sha256: {"vencedor": "digit_1", "rotulos": achados[0].rotulos, "motivo": "e um 1"}}
        manifesto = aplicar(conferir(achados, decisoes), self.base, self.quarentena)
        dados = json.loads(manifesto.read_text(encoding="utf-8"))
        self.assertEqual(dados["movidos"], [{"classe": "lower_l", "arquivo": "l0.png"}])
        self.assertEqual(dados["por_motivo"], {"rotulo errado": 1})


class DecisoesReaisTests(unittest.TestCase):
    """O `data/texto_conflitos.json` do repositório. Não é código: é julgamento humano."""

    def setUp(self) -> None:
        if not DECISOES_REAIS.exists():  # pragma: no cover - checkout sem o arquivo
            self.skipTest("data/texto_conflitos.json não existe neste checkout")
        self.decisoes = ler_decisoes(DECISOES_REAIS)

    def test_as_decisoes_do_repositorio_dizem_todas_por_que(self) -> None:
        """`ler_decisoes` já recusa a linha sem motivo; aqui a garantia é sobre o arquivo real."""
        self.assertEqual(83, len(self.decisoes))
        for sha, decisao in self.decisoes.items():
            self.assertTrue(str(decisao["motivo"]).strip(), sha)

    def test_o_vencedor_e_sempre_um_dos_rotulos_em_disputa(self) -> None:
        """Um vencedor que não está em disputa moveria os dois lados e não deixaria nada."""
        for sha, decisao in self.decisoes.items():
            vencedor = decisao.get("vencedor")
            if vencedor:
                self.assertIn(vencedor, decisao["rotulos"], sha)

    def test_o_indecidivel_diz_que_e_indecidivel(self) -> None:
        """Sem vencedor **e** com confiança de decidido seria uma linha que se contradiz."""
        for sha, decisao in self.decisoes.items():
            if not decisao.get("vencedor"):
                self.assertEqual("indecidivel", decisao.get("confianca"), sha)
            else:
                self.assertIn(decisao.get("confianca"), {"alta", "media"}, sha)

    def test_todo_grupo_em_disputa_tem_pelo_menos_duas_classes(self) -> None:
        for sha, decisao in self.decisoes.items():
            self.assertGreaterEqual(len(decisao["rotulos"]), 2, sha)


class ConflitoTests(unittest.TestCase):
    def test_os_rotulos_saem_ordenados_e_a_comparacao_ignora_a_ordem(self) -> None:
        a = Conflito("a" * 64, {"lower_l": ["x"], "digit_1": ["y", "z"]})
        self.assertEqual(list(a.rotulos), ["digit_1", "lower_l"])
        self.assertEqual(a.rotulos, {"lower_l": 1, "digit_1": 2})
        self.assertEqual(a.total, 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
