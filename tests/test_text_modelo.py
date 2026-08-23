"""O par (modelo, metadado) que não pode se descasar (S-179).

**O que se está travando aqui não é a carga: é a recusa.** Um `.pt` de outra rodada com o mesmo
número de classes carrega perfeitamente e passa a ler outras letras -- nada levanta, nada avisa.
Todo teste abaixo que espera `ModeloInvalido` existe por causa disso.

Os testes que precisam de pesos **constroem os seus**: uma rede de 3 classes salva num
`tmp_path` custa milissegundos e exercita o caminho inteiro. Os 2,6 MB do modelo de caractere
não vivem no repositório, e um teste que dependesse deles pularia em todo clone limpo -- que é o
mesmo que não existir.
"""

from __future__ import annotations

import json
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from chess_diagram_ocr.text import modelo as mod

META_REAL = Path(__file__).resolve().parents[1] / "models" / "char_meta.json"


def _meta_de(idx_to_char: dict[int, str], pesos: Path | None, **extra: object) -> dict[str, object]:
    dados: dict[str, object] = {
        "schema_version": 2,
        "idx_to_char": {str(i): c for i, c in idx_to_char.items()},
        "label_map": {c: i for i, c in idx_to_char.items()},
        "num_classes": len(idx_to_char),
        "temperatura": 1.5,
        "modelo_sha256": mod.impressao_do_arquivo(pesos) if pesos else "0" * 64,
        "classes_sha256": mod.impressao_das_classes(idx_to_char),
        "treinado_em": "2026-01-01T00:00:00",
    }
    dados.update(extra)
    return dados


def _gravar_rede(destino: Path, num_classes: int, *, semente: int = 0) -> Path:
    import torch

    torch.manual_seed(semente)
    torch.save(mod._construir_rede(num_classes).state_dict(), destino)
    return destino


class MetadadoRealTests(unittest.TestCase):
    """O `models/char_meta.json` que está no disco agora, conferido aqui.

    **A contagem de classes e o valor da temperatura deixaram de ser pinados, e a razão é um
    defeito que este arquivo tinha.** Os dois mudam **por construção** a cada retreino: o porte
    de 2026-08-21 trouxe 292 classes e temperatura 2,5208718319805; o treino de 2026-08-23 sobre
    `training_data/` deu 314 classes e outra temperatura. Um teste que exige o número antigo
    falha exatamente quando alguém faz a coisa certa -- ele vira uma tranca contra retreinar.

    O que continua pinado é o que **não** pode mudar sem que algo esteja quebrado: o metadado
    fecha consigo mesmo, a temperatura não é softmax cru, e as figurinas de xadrez estão lá.
    """

    def setUp(self) -> None:
        if not META_REAL.exists():  # pragma: no cover - checkout sem o metadado
            self.skipTest("models/char_meta.json não existe neste checkout")
        self.meta = mod.ler_metadado(META_REAL)

    def test_o_metadado_do_acervo_carrega_e_fecha_consigo_mesmo(self) -> None:
        self.assertEqual(self.meta.num_classes, len(self.meta.alfabeto))
        self.assertEqual(self.meta.num_classes, len(set(self.meta.idx_to_char)))
        self.assertGreaterEqual(self.meta.num_classes, 292)

    def test_a_temperatura_veio_calibrada_e_nao_e_neutra(self) -> None:
        """Temperatura 1,0 é softmax cru, e é o estado que a S-205 existe para impedir."""
        self.assertGreater(self.meta.temperatura, 0.0)
        self.assertNotAlmostEqual(1.0, self.meta.temperatura, places=6)

    def test_a_forma_canonica_do_hash_de_classes_e_a_mesma_do_projeto_de_origem(self) -> None:
        """Se a forma divergir, o `classes_sha256` gravado lá não pode ser conferido aqui.

        É `"{indice}\\t{caractere}"` por linha, ordenado por índice, unido por `\\n`. Este teste
        é o que impede alguém de "melhorar" a serialização e quebrar a conferência em silêncio.
        """
        bruto = json.loads(META_REAL.read_text(encoding="utf-8"))
        self.assertEqual(bruto["classes_sha256"], mod.impressao_das_classes(self.meta.idx_to_char))

    def test_as_figurinas_de_xadrez_estao_entre_as_classes(self) -> None:
        """É o que torna este modelo diferente de um OCR genérico, e o motivo do porte."""
        for figurina in "♔♕♖♗♘♙":
            self.assertIn(figurina, self.meta.alfabeto)


class MetadadoRecusadoTests(unittest.TestCase):
    """Cada caso aqui é um jeito de o par ficar trocado sem ninguém perceber."""

    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def _escrever(self, dados: object) -> Path:
        caminho = self.raiz / "meta.json"
        caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return caminho

    def test_formato_1_e_recusado(self) -> None:
        dados = _meta_de({0: "a"}, None)
        dados["schema_version"] = 1
        with self.assertRaisesRegex(mod.ModeloInvalido, "formato 1"):
            mod.ler_metadado(self._escrever(dados))

    def test_metadado_sem_temperatura_e_recusado(self) -> None:
        dados = _meta_de({0: "a"}, None)
        del dados["temperatura"]
        with self.assertRaisesRegex(mod.ModeloInvalido, "temperatura"):
            mod.ler_metadado(self._escrever(dados))

    def test_temperatura_nao_positiva_e_recusada(self) -> None:
        for valor in (0, -1.0, "quente"):
            with self.subTest(valor=valor):
                dados = _meta_de({0: "a"}, None)
                dados["temperatura"] = valor
                with self.assertRaises(mod.ModeloInvalido):
                    mod.ler_metadado(self._escrever(dados))

    def test_temperatura_neutra_carrega_mas_avisa_alto(self) -> None:
        """**Ausência e 1,0 são coisas diferentes**: uma é silêncio, a outra é declaração.

        Recusar o 1,0 impediria de usar um modelo que o dono sabe que está sem calibração; aceitá-lo
        calado é como o projeto de origem rodou um dia inteiro em softmax cru sem ninguém notar.
        """
        dados = _meta_de({0: "a"}, None)
        dados["temperatura"] = 1.0
        caminho = self._escrever(dados)
        with self.assertLogs("chess_diagram_ocr.text.modelo", level=logging.WARNING) as capturado:
            meta = mod.ler_metadado(caminho)
        self.assertEqual(1.0, meta.temperatura)
        self.assertIn("softmax cru", "\n".join(capturado.output))

    def test_temperatura_calibrada_nao_avisa(self) -> None:
        """O aviso que dispara sempre é um aviso que ninguém lê."""
        with self.assertNoLogs("chess_diagram_ocr.text.modelo", level=logging.WARNING):
            mod.ler_metadado(self._escrever(_meta_de({0: "a"}, None)))

    def test_metadado_sem_impressao_do_modelo_e_recusado(self) -> None:
        dados = _meta_de({0: "a"}, None)
        dados["modelo_sha256"] = ""
        with self.assertRaisesRegex(mod.ModeloInvalido, "modelo_sha256"):
            mod.ler_metadado(self._escrever(dados))

    def test_contagem_de_classes_que_nao_bate_com_o_mapa_e_recusada(self) -> None:
        dados = _meta_de({0: "a", 1: "b"}, None)
        dados["num_classes"] = 3
        with self.assertRaises(mod.ModeloInvalido):
            mod.ler_metadado(self._escrever(dados))

    def test_buraco_no_mapa_de_indices_e_recusado(self) -> None:
        """A saída da rede é indexada de 0 a n-1; um buraco vira um caractere errado."""
        dados = _meta_de({0: "a", 2: "b"}, None)
        dados["num_classes"] = 2
        with self.assertRaisesRegex(mod.ModeloInvalido, "buraco"):
            mod.ler_metadado(self._escrever(dados))

    def test_metadado_editado_depois_de_gravado_e_recusado(self) -> None:
        """Trocar uma classe à mão e esquecer o hash é como a lista silenciosamente diverge."""
        dados = _meta_de({0: "a", 1: "b"}, None)
        dados["idx_to_char"] = {"0": "a", "1": "c"}
        with self.assertRaisesRegex(mod.ModeloInvalido, "editado"):
            mod.ler_metadado(self._escrever(dados))

    def test_json_invalido_e_arquivo_ausente_dizem_qual_e_o_problema(self) -> None:
        quebrado = self.raiz / "quebrado.json"
        quebrado.write_text("{ nao é json", encoding="utf-8")
        with self.assertRaises(mod.ModeloInvalido):
            mod.ler_metadado(quebrado)
        with self.assertRaises(mod.ModeloInvalido):
            mod.ler_metadado(self.raiz / "nao_existe.json")


class CargaTests(unittest.TestCase):
    """O caminho feliz, e as duas recusas que dependem dos pesos."""

    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)
        self.addCleanup(mod.limpar_cache)
        mod.limpar_cache()

        self.idx = {0: "a", 1: "b", 2: "♗"}
        self.pesos = _gravar_rede(self.raiz / "char_classifier.pt", len(self.idx))
        self.meta = self.raiz / "char_meta.json"
        self.meta.write_text(json.dumps(_meta_de(self.idx, self.pesos), ensure_ascii=False), encoding="utf-8")

    def test_o_par_certo_carrega_e_classifica(self) -> None:
        classificador = mod.carregar_classificador(self.meta, self.pesos)
        recortes = [np.full((20, 12), 200, dtype=np.uint8), np.full((18, 10), 30, dtype=np.uint8)]
        lidos = classificador.classificar(recortes)
        self.assertEqual(2, len(lidos))
        for char, confianca in lidos:
            self.assertIn(char, set(self.idx.values()))
            self.assertGreaterEqual(confianca, 0.0)
            self.assertLessEqual(confianca, 1.0)

    def test_o_hash_do_modelo_e_conferido_e_o_par_trocado_e_recusado(self) -> None:
        """Mesma contagem de classes, ordem diferente: é o caso que só o hash pega."""
        outro = _gravar_rede(self.raiz / "outro.pt", len(self.idx), semente=7)
        with self.assertRaises(mod.ModeloInvalido) as capturado:
            mod.carregar_classificador(self.meta, outro)
        mensagem = str(capturado.exception)
        self.assertIn("não é o modelo descrito", mensagem)
        self.assertIn(mod.impressao_do_arquivo(outro)[:16], mensagem)

    def test_pesos_ausentes_dizem_onde_apontar(self) -> None:
        with self.assertRaises(mod.ModeloInvalido) as capturado:
            mod.carregar_classificador(self.meta, self.raiz / "nao_existe.pt")
        mensagem = str(capturado.exception)
        self.assertIn("glyph_model", mensagem)
        self.assertIn("CVOFF_OCR_GLYPH_MODEL", mensagem)

    def test_o_pt_e_procurado_ao_lado_do_metadado(self) -> None:
        """`pesos=None` é o caminho de quem simplesmente pôs o arquivo em `models/`."""
        self.assertIsNotNone(mod.carregar_classificador(self.meta))

    def test_carregar_duas_vezes_devolve_o_mesmo_objeto(self) -> None:
        primeiro = mod.carregar_classificador(self.meta, self.pesos)
        self.assertIs(primeiro, mod.carregar_classificador(self.meta, self.pesos))

    def test_trocar_o_arquivo_no_disco_invalida_o_cache(self) -> None:
        """Sem isto, retreinar em sessão deixaria o modelo antigo respondendo com o mapa novo.

        É o descasamento que este módulo inteiro existe para impedir, entrando pela porta dos
        fundos -- e ele não daria erro nenhum.
        """
        primeiro = mod.carregar_classificador(self.meta, self.pesos)
        _gravar_rede(self.pesos, len(self.idx), semente=99)
        self.meta.write_text(json.dumps(_meta_de(self.idx, self.pesos), ensure_ascii=False), encoding="utf-8")
        self.assertIsNot(primeiro, mod.carregar_classificador(self.meta, self.pesos))

    def test_a_temperatura_muda_a_confianca_e_nao_a_classe(self) -> None:
        """É o que a calibração faz, e é por isso que ela não desarruma quem já decidiu."""
        recorte = [np.full((16, 16), 120, dtype=np.uint8)]
        quente = mod.carregar_classificador(self.meta, self.pesos)
        char_quente, conf_quente = quente.classificar(recorte)[0]

        mod.limpar_cache()
        dados = _meta_de(self.idx, self.pesos)
        dados["temperatura"] = 20.0
        dados["classes_sha256"] = mod.impressao_das_classes(self.idx)
        self.meta.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        frio = mod.carregar_classificador(self.meta, self.pesos)
        char_frio, conf_frio = frio.classificar(recorte)[0]

        self.assertEqual(char_quente, char_frio)
        self.assertNotAlmostEqual(conf_quente, conf_frio, places=4)

    def test_o_lote_vazio_devolve_lista_vazia(self) -> None:
        classificador = mod.carregar_classificador(self.meta, self.pesos)
        self.assertEqual([], classificador.classificar([]))
        self.assertEqual([], classificador.margem([]))
        self.assertEqual(0, classificador.probabilidades([]).size)

    def test_a_margem_fica_entre_zero_e_um(self) -> None:
        classificador = mod.carregar_classificador(self.meta, self.pesos)
        for margem in classificador.margem([np.full((16, 16), 90, dtype=np.uint8)]):
            self.assertGreaterEqual(margem, 0.0)
            self.assertLessEqual(margem, 1.0)


class PastasDoMetadadoTests(unittest.TestCase):
    def test_o_mapa_de_pastas_cobre_toda_classe(self) -> None:
        if not META_REAL.exists():  # pragma: no cover - checkout sem o metadado
            self.skipTest("models/char_meta.json não existe neste checkout")
        meta = mod.ler_metadado(META_REAL)
        pastas = mod.pastas_do_metadado(meta)
        self.assertEqual(meta.num_classes, len(pastas), "duas classes caíram na mesma pasta")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
