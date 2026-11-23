"""O modelo de marcas (`modelo_de_marcas.py`): as classes, o sorteio, o treino e o checkpoint."""

from __future__ import annotations

import csv
import threading
import unittest
from pathlib import Path

import numpy as np
import torch
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr import modelo_de_marcas as mm
from chess_diagram_ocr.atomic_io import write_image
from chess_diagram_ocr.augment import TIPOS_DE_MARCA, MarcaEmVazia
from chess_diagram_ocr.checkpoint import check_compatible, load_checkpoint
from chess_diagram_ocr.model import DEFAULT_ARCH


class ClassesTests(unittest.TestCase):
    def test_a_ponte_cobre_as_marcas_de_casa_e_so_tipos_do_aumento(self) -> None:
        self.assertEqual(set(mm.DO_AUMENTO.values()), set(mm.CLASSES_DE_MARCA[1:]))
        self.assertEqual(set(mm.DO_AUMENTO) | set(mm.TRACOS_DE_DISTRACAO), set(TIPOS_DE_MARCA))
        self.assertNotIn(mc.OUTRA, mm.CLASSES_DE_MARCA)

    def test_o_sorteio_devolve_classe_valida_e_traco_e_sem_marca(self) -> None:
        torch.manual_seed(0)
        casa = torch.full((1, 64, 64), 0.95)
        vistas = set()
        for _ in range(300):
            saida, classe = mm.SorteioDeMarca(0.5, 0.3)(casa)
            self.assertEqual(saida.shape, casa.shape)
            vistas.add(classe)
            if classe == 0:
                continue
            self.assertLess(float(saida.mean()), float(casa.mean()))
        self.assertEqual(vistas, set(range(len(mm.CLASSES_DE_MARCA))))
        so_traco = mm.SorteioDeMarca(0.0, 1.0)
        for _ in range(20):
            saida, classe = so_traco(casa)
            self.assertEqual(classe, 0)
        with self.assertRaises(ValueError):
            mm.SorteioDeMarca(0.8, 0.5)


class QuebrasTests(unittest.TestCase):
    def test_vertice_e_pontilhada_imprimem_tinta_e_tipo_desconhecido_levanta(self) -> None:
        casa = torch.full((1, 64, 64), 0.95)
        vertice = mm.desenhar_quebra(casa, "vertice", vertice=(0.0, 0.0), angulos=(0.0, 1.5), espessura=0.08)
        pontilhada = mm.desenhar_quebra(
            casa, "pontilhada", vertice=(0.0, 0.0), angulos=(0.0, 0.0), espessura=0.08, periodo=0.2
        )
        self.assertLess(float(vertice.mean()), 0.95)
        self.assertLess(float(pontilhada.mean()), 0.95)
        # O vértice é meia-reta: o lado oposto às duas direções fica limpo.
        self.assertAlmostEqual(float(vertice[0, 28:36, :20].mean()), 0.95, places=4)
        # A pontilhada tem vãos ao longo da linha.
        linha = pontilhada[0, 32]
        self.assertGreater(int((linha > 0.9).sum()), 10)
        self.assertGreater(int((linha < 0.2).sum()), 10)
        # A ponta termina dentro da casa: do vértice para trás, nada.
        ponta = mm.desenhar_quebra(casa, "ponta", vertice=(0.0, 0.0), angulos=(0.0, 0.0), espessura=0.08)
        self.assertLess(float(ponta[0, 30:34, 40:].mean()), 0.5)
        self.assertAlmostEqual(float(ponta[0, 30:34, :28].mean()), 0.95, places=4)
        with self.assertRaises(ValueError):
            mm.desenhar_quebra(casa, "circulo", vertice=(0.0, 0.0), angulos=(0.0, 0.0), espessura=0.1)

    def test_letra_imprime_tinta_e_as_que_parecem_marca_ficam_de_fora(self) -> None:
        import cv2

        casa = torch.full((1, 64, 64), 0.95)
        letra = mm.desenhar_letra(casa, "D", altura=0.5, centro=(0.0, 0.0), fonte=cv2.FONT_HERSHEY_SIMPLEX, tinta=0.0)
        self.assertLess(float(letra.min()), 0.2)
        self.assertGreater(float(letra[0, :8].mean()), 0.94)  # a letra fica no meio, longe da borda
        for parecida in "Oo0QxX+*":
            self.assertNotIn(parecida, mm.LETRAS_DA_CASA)

    def test_pingo_de_sujeira_e_menor_que_a_menor_bolinha(self) -> None:
        self.assertLess(mm.PINGO_MAXIMO, mm.BOLINHA_MINIMA)
        torch.manual_seed(3)
        for _ in range(30):
            saida = mm._sujeira_sorteada(torch.full((1, 64, 64), 0.95))
            # Cada pingo cobre no máximo um disco de 7% da casa: três deles somam bem menos que uma bolinha.
            self.assertLess(int((saida < 0.6).sum()), 3 * 25)

    def test_o_sorteio_pode_dar_as_quebras_com_rotulo_sem_marca(self) -> None:
        torch.manual_seed(1)
        so_traco = mm.SorteioDeMarca(0.0, 1.0)
        casa = torch.full((1, 64, 64), 0.95)
        for _ in range(50):
            _, classe = so_traco(casa)
            self.assertEqual(classe, 0)


class DesenharTests(unittest.TestCase):
    def test_o_forward_segue_com_a_mesma_sequencia_do_rng(self) -> None:
        """O modelo de peças treina com o `forward`: separar o `desenhar` não pode mudar o que ele vê."""
        casa = torch.full((1, 64, 64), 0.9)
        # p < 1, para o `_should` sortear de verdade: com p = 1 ele nem consome o RNG.
        torch.manual_seed(7)
        pelo_forward = MarcaEmVazia(0.99)(casa)
        torch.manual_seed(7)
        self.assertLess(float(torch.rand(())), 0.99)  # o sorteio de `_should`, que esta semente aprova
        tipo = TIPOS_DE_MARCA[int(torch.randint(len(TIPOS_DE_MARCA), ()).item())]
        pelo_desenhar = MarcaEmVazia(1.0).desenhar(casa, tipo)
        self.assertTrue(torch.equal(pelo_forward, pelo_desenhar))

    def test_tipo_desconhecido_e_recusado(self) -> None:
        with self.assertRaises(ValueError):
            MarcaEmVazia(1.0).desenhar(torch.zeros((1, 64, 64)), "triangulo")


class TreinoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.samples = self.pasta / "samples"
        self.samples.mkdir()
        self.csv = self.pasta / "labels.csv"
        nomes = ["t1.png", "t2.png", "v1.png", "teste.png"]
        tabuleiro = np.full((800, 800, 3), 235, dtype=np.uint8)
        for fila in range(8):
            for coluna in range(8):
                if (fila + coluna) % 2:
                    tabuleiro[fila * 100 : (fila + 1) * 100, coluna * 100 : (coluna + 1) * 100] = 170
        with self.csv.open("w", encoding="utf-8", newline="") as handle:
            escritor = csv.writer(handle)
            escritor.writerow(["filename", "fen"])
            for nome in nomes:
                write_image(self.samples / nome, tabuleiro)
                escritor.writerow([nome, "4k3/8/8/8/8/8/8/4K3 w - - 0 1"])
        self.splits = {"t1.png": "train", "t2.png": "train", "v1.png": "val", "teste.png": "train"}

    def test_treina_tira_o_teste_e_grava_um_checkpoint_que_o_modelo_de_pecas_recusa(self) -> None:
        saida = self.pasta / "marcas.pt"
        resultado = mm.treinar(
            csv_path=self.csv,
            samples_dir=self.samples,
            splits=self.splits,
            saida=saida,
            excluidas=["teste.png"],
            epocas=1,
            lote=64,
            workers=0,
            device="cpu",
            tabuleiros_val=None,
        )
        self.assertEqual((resultado.tabuleiros_treino, resultado.tabuleiros_val, resultado.excluidos), (2, 1, 1))
        self.assertTrue(saida.exists())

        modelo = mm.carregar(saida)
        probabilidades = modelo.probabilidades(np.full((400, 400, 3), 235, dtype=np.uint8))
        self.assertEqual(probabilidades.shape, (64, len(mm.CLASSES_DE_MARCA)))
        np.testing.assert_allclose(probabilidades.sum(axis=1), 1.0, rtol=1e-5)
        self.assertIsInstance(modelo.ler(np.full((400, 400, 3), 235, dtype=np.uint8), limiar=1.01), mc.MarcasDoDiagrama)
        self.assertTrue(modelo.ler(np.full((400, 400, 3), 235, dtype=np.uint8), limiar=1.01).vazia)

        with self.assertRaisesRegex(ValueError, "outras classes"):
            check_compatible(load_checkpoint(saida), DEFAULT_ARCH.version)

    def test_carregar_recusa_o_checkpoint_de_outro_modelo(self) -> None:
        from chess_diagram_ocr.checkpoint import save_checkpoint
        from chess_diagram_ocr.model import PieceClassifier

        caminho = self.pasta / "pecas.pt"
        save_checkpoint(caminho, PieceClassifier().state_dict(), metadata={"arch_version": DEFAULT_ARCH.version})
        with self.assertRaises(ValueError):
            mm.carregar(caminho)

    def treinar(
        self,
        saida: Path,
        *,
        epocas: int,
        progresso: mm.Progresso | None = None,
        cancelar: threading.Event | None = None,
    ) -> mm.ResultadoDoTreino:
        return mm.treinar(
            csv_path=self.csv,
            samples_dir=self.samples,
            splits=self.splits,
            saida=saida,
            excluidas=["teste.png"],
            lote=64,
            workers=0,
            device="cpu",
            tabuleiros_val=None,
            epocas=epocas,
            progresso=progresso,
            cancelar=cancelar,
        )

    def test_o_progresso_conta_a_epoca_e_traz_o_f1_no_fim_dela(self) -> None:
        chamadas: list[tuple[int, int, float, float | None]] = []
        self.treinar(self.pasta / "m.pt", epocas=2, progresso=lambda *a: chamadas.append(a))
        fins = [c for c in chamadas if c[3] is not None]
        self.assertEqual([(c[0], c[1], c[2]) for c in fins], [(1, 2, 1.0), (2, 2, 1.0)])
        validando = [c for c in chamadas if c[2] == 1.0 and c[3] is None]
        self.assertEqual([c[0] for c in validando], [1, 2], "cada época avisa quando a validação começa")
        self.assertTrue(all(0 < c[2] <= 1 for c in chamadas))

    def test_cancelado_antes_da_primeira_epoca_nao_grava(self) -> None:
        parar = threading.Event()
        parar.set()
        saida = self.pasta / "m.pt"
        resultado = self.treinar(saida, epocas=2, cancelar=parar)
        self.assertTrue(resultado.cancelado)
        self.assertFalse(saida.exists())

    def test_instalar_guarda_o_anterior_e_recusa_o_modelo_de_pecas(self) -> None:
        from chess_diagram_ocr.checkpoint import save_checkpoint
        from chess_diagram_ocr.model import PieceClassifier

        novo = self.pasta / "novo.pt"
        self.treinar(novo, epocas=1)
        destino = self.pasta / "models" / "marcas.pt"
        self.assertIsNone(mm.instalar(novo, destino, quando="1"), "sem anterior, sem cópia")
        self.assertEqual(destino.read_bytes(), novo.read_bytes())
        destino.write_bytes(b"o anterior")
        copia = mm.instalar(novo, destino, quando="2")
        assert copia is not None
        self.assertEqual((copia.name, copia.read_bytes()), ("marcas_antes_2.pt", b"o anterior"))

        pecas = self.pasta / "pecas.pt"
        save_checkpoint(pecas, PieceClassifier().state_dict(), metadata={"arch_version": DEFAULT_ARCH.version})
        with self.assertRaises(ValueError):
            mm.instalar(pecas, destino, quando="3")
        self.assertEqual(destino.read_bytes(), novo.read_bytes(), "a recusa não tocou no instalado")


if __name__ == "__main__":
    unittest.main()
