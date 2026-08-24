"""O reconhecedor de glifo atrás do protocolo da S-42 (S-181).

**O que esta suíte trava é a fronteira, não a acurácia.** A pergunta "o glifo lê melhor que o
RapidOCR neste acervo?" é da S-183 e se responde com uma tabela sobre legendas transcritas à mão,
não com `assert`. O que se pode travar aqui é o que a S-181 promete: que o motor novo entra pela
mesma porta que os outros três, e que nada em `ocr_caption.py` ou `pdf_text.py` precisou saber
que ele existe.

Os testes de decodificação usam um classificador **falso** com probabilidades escolhidas, porque
é a única forma de afirmar qual classe venceu e por quê. Os de segmentação usam uma rede de 3
classes construída na hora -- ela não lê nada, e não precisa: o que se mede ali é quantas linhas
saíram e onde.
"""

from __future__ import annotations

import json
import logging
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from chess_diagram_ocr import ocr
from chess_diagram_ocr.settings import OcrSettings
from chess_diagram_ocr.text import modelo as mod
from chess_diagram_ocr.text.recognizer import GlyphRecognizer

RAIZ = Path(__file__).resolve().parents[1]
FONTE = 0  # cv2.FONT_HERSHEY_SIMPLEX, sem importar cv2 no topo


@dataclass
class _MetaFalso:
    idx_to_char: dict[int, str]

    @property
    def num_classes(self) -> int:
        return len(self.idx_to_char)


class _ClassificadorFalso:
    """Responde a mesma linha de probabilidades para todo recorte. Determinístico de propósito."""

    def __init__(self, idx_to_char: dict[int, str], linha: list[float]) -> None:
        self.meta = _MetaFalso(idx_to_char)
        self._linha = np.asarray(linha, dtype=np.float32)

    def probabilidades(self, recortes: list[np.ndarray]) -> np.ndarray:
        if not recortes:
            return np.empty((0, self.meta.num_classes), dtype=np.float32)
        return np.tile(self._linha, (len(recortes), 1))

    def classificar(self, recortes: list[np.ndarray]) -> list[tuple[str, float]]:
        probs = self.probabilidades(recortes)
        if probs.size == 0:
            return []
        indices = probs.argmax(axis=1)
        return [(self.meta.idx_to_char[int(i)], float(probs[j, i])) for j, i in enumerate(indices)]


class _ClassificadorPorRecorte(_ClassificadorFalso):
    """Uma linha de probabilidades por recorte, em ordem. Para o teste da confiança mínima."""

    def __init__(self, idx_to_char: dict[int, str], linhas: list[list[float]]) -> None:
        super().__init__(idx_to_char, linhas[0])
        self._linhas = np.asarray(linhas, dtype=np.float32)

    def probabilidades(self, recortes: list[np.ndarray]) -> np.ndarray:
        if not recortes:
            return np.empty((0, self.meta.num_classes), dtype=np.float32)
        return np.asarray([self._linhas[i % len(self._linhas)] for i in range(len(recortes))], dtype=np.float32)


def _pagina_com_texto(linhas: tuple[str, ...], *, largura: int = 420, altura: int = 160) -> np.ndarray:
    """Uma imagem RGB com texto desenhado. Tinta escura sobre papel claro, como o acervo."""
    import cv2

    imagem = np.full((altura, largura, 3), 245, dtype=np.uint8)
    for i, texto in enumerate(linhas):
        cv2.putText(imagem, texto, (12, 45 + i * 60), FONTE, 1.2, (20, 20, 20), 2, cv2.LINE_AA)
    return imagem


class ContratoDoProtocoloTests(unittest.TestCase):
    def test_o_reconhecedor_de_glifo_satisfaz_o_protocolo(self) -> None:
        reconhecedor = GlyphRecognizer(_ClassificadorFalso({0: "a"}, [1.0]))
        self.assertIsInstance(reconhecedor, ocr.TextRecognizer)
        self.assertEqual("glifo", reconhecedor.name)

    def test_o_glifo_esta_entre_os_motores_conhecidos(self) -> None:
        self.assertIn("glifo", ocr.KNOWN_ENGINES)

    def test_a_s43_nao_precisou_saber_que_o_glifo_existe(self) -> None:
        """A promessa da S-181: o motor novo entra pela porta que já existia.

        `ocr_caption` recorta a faixa e devolve `pdf_text.TextLine`; `pdf_text` agrupa por
        coluna, distribui por diagrama e filtra prosa. Nenhum dos dois pode mencionar um motor
        pelo nome -- no dia em que mencionar, a próxima fonte de texto vai precisar de uma
        segunda porta, que é exatamente o que a S-43 recusou fazer.
        """
        for nome in ("ocr_caption.py", "pdf_text.py"):
            with self.subTest(modulo=nome):
                texto = (RAIZ / "src" / "chess_diagram_ocr" / nome).read_text(encoding="utf-8")
                # O nome do motor **como valor**, e não a palavra "glifo" em prosa: o
                # `ocr_caption` fala de glifos o tempo todo, e com razão.
                self.assertNotIn('"glifo"', texto)
                self.assertNotIn("'glifo'", texto)
                self.assertNotIn("from .text", texto)
                self.assertNotIn("chess_diagram_ocr.text", texto)


class ConstrucaoTests(unittest.TestCase):
    """Sem os pesos, o motor não sobe -- e o que ele diz é o item."""

    def test_sem_os_pesos_o_construtor_devolve_none_e_diz_o_que_falta(self) -> None:
        preferencias = OcrSettings(enabled=True, engine="glifo", glyph_model=str(RAIZ / "models" / "nao_existe.pt"))
        with self.assertLogs("chess_diagram_ocr.ocr", level=logging.WARNING) as capturado:
            self.assertIsNone(ocr.build_recognizer(preferencias))
        mensagem = "\n".join(capturado.output)
        self.assertIn("glyph_model", mensagem)
        self.assertIn("O pipeline segue sem OCR", mensagem)

    def test_desligado_continua_devolvendo_none_sem_tocar_no_modelo(self) -> None:
        self.assertIsNone(ocr.build_recognizer(OcrSettings(enabled=False, engine="glifo")))

    def test_o_motivo_da_ausencia_esta_em_pt_br_nas_preferencias(self) -> None:
        preferencias = OcrSettings(engine="glifo", glyph_model=str(RAIZ / "models" / "nao_existe.pt"))
        motivo = preferencias.glyph_disabled_reason()
        self.assertIn("não estão em", motivo)
        self.assertIn("CVOFF_OCR_GLYPH_MODEL", motivo)


class AllowlistTests(unittest.TestCase):
    """O `allowlist` do glifo restringe o **decodificador**, e é o que ele faz melhor.

    Nos outros três motores ele é filtro posterior, e o comentário de `ocr.filter_by_allowlist`
    diz o que isso custa: *"o motor já escolheu `8` em vez de `B` antes de chegar aqui, e apagar
    o `8` não traz o `B` de volta"*. Aqui traz, e estes testes são a prova.
    """

    def setUp(self) -> None:
        # `8` vence com folga; `B` é a segunda. É o par que a S-44 precisa separar no marcador
        # de lado a jogar, e o exemplo que o comentário do `filter_by_allowlist` usa.
        self.idx = {0: "8", 1: "B", 2: "W", 3: "Wh"}
        self.classificador = _ClassificadorFalso(self.idx, [0.70, 0.20, 0.06, 0.04])

    def test_sem_allowlist_vence_a_classe_mais_provavel(self) -> None:
        caixas = GlyphRecognizer(self.classificador).read(_pagina_com_texto(("A",)))
        self.assertTrue(caixas)
        self.assertEqual({"8"}, set(caixas[0].text.replace(" ", "")))

    def test_o_allowlist_tira_a_classe_proibida_antes_do_argmax(self) -> None:
        caixas = GlyphRecognizer(self.classificador).read(_pagina_com_texto(("A",)), allowlist="WB")
        self.assertTrue(caixas)
        self.assertEqual({"B"}, set(caixas[0].text.replace(" ", "")))
        # E a confiança é a **renormalizada** dentro do permitido, não a original de 0,20.
        self.assertGreater(caixas[0].confidence, 0.20)

    def test_a_ligadura_so_passa_se_todas_as_letras_dela_forem_permitidas(self) -> None:
        """`Wh` não é um `W`: aceitá-la num allowlist de `W` injetaria um `h` no texto."""
        reconhecedor = GlyphRecognizer(self.classificador)
        self.assertIsNone(reconhecedor._colunas_permitidas(""))
        permitidos = reconhecedor._colunas_permitidas("WB")
        assert permitidos is not None
        self.assertEqual({"B", "W"}, {self.idx[int(i)] for i in permitidos})

    def test_allowlist_que_nao_casa_com_nada_le_sem_restricao_e_avisa(self) -> None:
        """Decodificar com zero classes devolveria lixo; a resposta certa é dizer e seguir."""
        with self.assertLogs("chess_diagram_ocr.text.recognizer", level=logging.WARNING):
            caixas = GlyphRecognizer(self.classificador).read(_pagina_com_texto(("A",)), allowlist="ΩΨ")
        self.assertTrue(caixas)


class ConfiancaTests(unittest.TestCase):
    def test_a_confianca_da_linha_e_a_minima_e_nao_a_media(self) -> None:
        """Uma legenda com um caractere adivinhado no meio não é 72% confiável.

        O `MIN_CONFIDENCE = 0.30` da S-42 corta legenda adivinhada, **e a média o burlaria**:
        com dois glifos a 0,95 e um a 0,25, a média dá 0,72 e passa com folga; o mínimo dá 0,25
        e é recusado. O caractere adivinhado é o mesmo nos dois casos.
        """
        idx = {0: "a", 1: "b", 2: "c", 3: "d", 4: "e"}
        seguro = [0.95, 0.02, 0.01, 0.01, 0.01]
        adivinhado = [0.25, 0.20, 0.20, 0.20, 0.15]
        classificador = _ClassificadorPorRecorte(idx, [seguro, seguro, adivinhado])

        caixas = GlyphRecognizer(classificador).read(_pagina_com_texto(("abc",)))
        self.assertEqual(1, len(caixas))
        self.assertEqual(3, len(caixas[0].text), "a segmentação não achou os três glifos")

        self.assertAlmostEqual(0.25, caixas[0].confidence, places=6)
        self.assertLess(caixas[0].confidence, ocr.MIN_CONFIDENCE)
        media = (0.95 + 0.95 + 0.25) / 3
        self.assertGreater(media, ocr.MIN_CONFIDENCE)


class CosturaTests(unittest.TestCase):
    """O que este módulo faz depois da S-184/S-185/S-187: costurar, e nada mais.

    A segmentação em si é medida nos testes dos três módulos dela. Aqui trava-se só o que a
    costura promete -- uma `TextBox` por linha, no formato do protocolo.
    """

    def setUp(self) -> None:
        self.reconhecedor = GlyphRecognizer(_ClassificadorFalso({0: "x"}, [1.0]))

    def test_duas_linhas_desenhadas_saem_como_duas_caixas(self) -> None:
        caixas = self.reconhecedor.read(_pagina_com_texto(("ABC", "DEF")))
        self.assertEqual(2, len(caixas), f"saíram {[c.text for c in caixas]}")
        primeira, segunda = sorted(caixas, key=lambda c: c.bbox[1])
        self.assertLess(primeira.bbox[3], segunda.bbox[1] + 1.0)

    def test_o_vao_largo_vira_espaco_e_o_estreito_nao(self) -> None:
        colado = self.reconhecedor.read(_pagina_com_texto(("AB",)))
        separado = self.reconhecedor.read(_pagina_com_texto(("A     B",)))
        self.assertTrue(colado and separado)
        self.assertNotIn(" ", colado[0].text)
        self.assertIn(" ", separado[0].text)

    def test_a_imagem_vazia_devolve_lista_vazia_e_nao_levanta(self) -> None:
        for imagem in (np.zeros((0, 0, 3), dtype=np.uint8), np.full((40, 40, 3), 245, dtype=np.uint8)):
            with self.subTest(forma=imagem.shape):
                self.assertEqual([], self.reconhecedor.read(imagem))

    def test_a_escala_da_pagina_vence_a_da_faixa(self) -> None:
        """Uma faixa de três letras não tem população para medir escala nenhuma.

        Sem poder passar a escala de fora, a régua de área varia de faixa para faixa -- e duas
        faixas do mesmo livro passam a ser medidas com réguas diferentes.
        """
        faixa = _pagina_com_texto(("AB",), largura=160, altura=70)
        # Uma escala absurdamente grande faz a peneira de área descartar tudo: é a prova de que
        # o parâmetro chega até `caixas_de_caractere`.
        self.assertEqual([], self.reconhecedor.read(faixa, escala=400))
        self.assertTrue(self.reconhecedor.read(faixa))

    def test_a_linha_que_e_so_fragmento_nao_vira_texto(self) -> None:
        """S-198: a faixa dilatada encosta na linha de cima, e o que entra são pedaços de tinta.

        Eles viravam texto **com confiança de leitura normal**, que é a forma de erro que este
        projeto trata como a pior. Medido em 155 faixas de camada editorada: CER 0,2725 -> 0,2248
        (`docs/metrics/texto_duas_linhas.json`).
        """
        import cv2

        imagem = np.full((190, 420, 3), 245, dtype=np.uint8)
        cv2.putText(imagem, "ABCDEFGH", (12, 60), FONTE, 1.2, (20, 20, 20), 2, cv2.LINE_AA)
        for i in range(8):  # o renque de fragmentos, abaixo da linha e baixo demais para ser letra
            imagem[168:174, 16 + i * 46 : 16 + i * 46 + 26] = 20

        lidas = self.reconhecedor.read(imagem)

        self.assertEqual(1, len(lidas), f"saíram {[c.text for c in lidas]}")
        self.assertLess(lidas[0].bbox[3], 160.0)

    def test_o_diagrama_e_excluido_com_margem(self) -> None:
        """O que está dentro do tabuleiro não é texto -- e os rótulos das casas moram fora dele."""
        imagem = _pagina_com_texto(("ABC",))
        tudo = self.reconhecedor.read(imagem)
        self.assertTrue(tudo)
        sem = self.reconhecedor.read(imagem, diagramas=[(0.0, 0.0, 420.0, 160.0)])
        self.assertEqual([], sem)


class ComOModeloDeVerdadeTests(unittest.TestCase):
    """O caminho inteiro, com uma rede de 3 classes construída na hora.

    Ela não lê nada -- 3 classes aleatórias não são um OCR --, e não precisa: o que se prova aqui
    é que `carregar_classificador` -> `GlyphRecognizer` -> `read` atravessa sem levantar, com
    `torch` de verdade no meio.
    """

    def setUp(self) -> None:
        import torch

        self._dir = TemporaryDirectory()
        raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)
        self.addCleanup(mod.limpar_cache)
        mod.limpar_cache()

        idx = {0: "a", 1: "b", 2: "c"}
        pesos = raiz / "char_classifier.pt"
        torch.manual_seed(3)
        torch.save(mod._construir_rede(len(idx)).state_dict(), pesos)
        meta = raiz / "char_meta.json"
        meta.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "idx_to_char": {str(i): c for i, c in idx.items()},
                    "num_classes": len(idx),
                    "temperatura": 2.0,
                    "modelo_sha256": mod.impressao_do_arquivo(pesos),
                    "classes_sha256": mod.impressao_das_classes(idx),
                    "treinado_em": "2026-01-01T00:00:00",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.meta, self.pesos, self.idx = meta, pesos, idx

    def test_o_caminho_inteiro_atravessa(self) -> None:
        from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

        reconhecedor = build_glyph_recognizer(self.pesos, self.meta)
        caixas = reconhecedor.read(_pagina_com_texto(("abc", "cab")))
        self.assertEqual(2, len(caixas))
        for caixa in caixas:
            self.assertTrue(set(caixa.text.replace(" ", "")) <= set(self.idx.values()))
            self.assertGreater(caixa.confidence, 0.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
