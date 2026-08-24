"""As duas réguas lado a lado, e a recusa de publicar só a lisonjeira (S-206).

**Publicar "99,1% de acerto" sobre recorte já segmentado quando a página real dá outro número é a
forma de número enganoso que este projeto já cometeu e corrigiu.** O comando existe para tornar
isso impossível pelo caminho normal.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from chess_diagram_ocr.cli import texto_placar_final as pf

RAIZ = Path(__file__).resolve().parents[1]


class ReguaDoRecorteTests(unittest.TestCase):
    def test_o_relatorio_casa_pelo_sha_e_nao_pela_data(self) -> None:
        """Há quatro relatórios de treino em `docs/metrics/`, e três descrevem outros modelos."""
        meta = RAIZ / "models" / "char_meta.json"
        if not meta.exists():
            self.skipTest("sem models/char_meta.json")
        publicado = json.loads(meta.read_text(encoding="utf-8"))

        regua = pf.regua_do_recorte(publicado["modelo_sha256"])

        self.assertGreater(regua["acuracia"], 0.0)
        self.assertGreater(regua["n"], 0)

    def test_sha_desconhecido_levanta_em_vez_de_pegar_o_mais_recente(self) -> None:
        """Pegar o mais recente publicaria o número de um modelo que não está em `models/`."""
        with self.assertRaises(ValueError):
            pf.regua_do_recorte("nao-existe-este-sha")


class RelatorioPublicadoTests(unittest.TestCase):
    """O arquivo que está em `docs/metrics/`, conferido contra o que o item promete."""

    def _relatorio(self) -> dict:
        caminho = RAIZ / "docs" / "metrics" / "texto_placar_final.json"
        if not caminho.exists():
            self.skipTest("o placar ainda não foi medido: rode `cvoff-texto-placar-final`")
        return json.loads(caminho.read_text(encoding="utf-8"))

    def test_o_relatorio_traz_as_duas_reguas(self) -> None:
        relatorio = self._relatorio()
        self.assertIn("regua_do_recorte", relatorio)
        self.assertIn("regua_da_pagina", relatorio)
        for lado in ("regua_do_recorte", "regua_da_pagina"):
            with self.subTest(lado=lado):
                self.assertGreater(relatorio[lado]["n"], 0, "o `n` de cada célula é declarado")

    def test_o_livro_novo_tem_coluna_propria(self) -> None:
        """Ela é `null` nesta base — e omiti-la faria a tabela parecer completa."""
        livro = self._relatorio()["livro_novo"]
        self.assertIn("por_que_nao_existe", livro)
        self.assertIsNone(livro["cer"])
        self.assertIn("livro", livro["por_que_nao_existe"])

    def test_a_distancia_esta_registrada_e_nomeada(self) -> None:
        distancia = self._relatorio()["distancia"]
        self.assertGreater(distancia["acuracia_do_recorte"], distancia["acerto_na_pagina"])
        self.assertIn("segmenta", distancia["o_que_ela_e"])


class RecusaTests(unittest.TestCase):
    def test_o_relatorio_recusa_publicar_so_a_regua_de_recorte(self) -> None:
        """**O critério de aceite.** A metade lisonjeira sozinha é o defeito que o item evita."""

        class ClassificadorFalso:
            meta = type("M", (), {"num_classes": 4, "temperatura": 1.0, "modelo_sha256": "x"})()

        with TemporaryDirectory() as tmp:
            vazio = Path(tmp)
            with self.assertRaises(ValueError) as erro:
                pf.regua_da_pagina([], por_livro=1, classificador=ClassificadorFalso())
            self.assertIn("recusa", str(erro.exception))
            self.assertFalse(list(vazio.glob("*.json")), "nada foi gravado")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
