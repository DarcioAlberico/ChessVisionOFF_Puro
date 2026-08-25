"""A paleta de glifos, derivada do metadado do modelo (S-246/S-247/S-248).

**O defeito que estes testes impedem é uma segunda lista.** Escrever os símbolos à mão criaria uma
lista ao lado da que o modelo usa, e a primeira divergência entre as duas é um símbolo que a pessoa
insere e que o OCR nunca poderá ler de volta — o mesmo defeito que a S-219 tirou dos comandos.

O segundo grupo trava a honestidade da S-247: a prateleira "o modelo não lê" é a **diferença** entre
o que se oferece e o que o modelo conhece, e não uma lista à parte. Um modelo treinado com as
figurinas pretas move os símbolos de prateleira sem que ninguém toque em código — e é isso que
`test_um_modelo_novo_move_o_simbolo_de_prateleira` prova, com um metadado de mentira.
"""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from chess_diagram_ocr.text import paleta as P
from chess_diagram_ocr.text.modelo import MetadadoDeClasses, impressao_das_classes


def _meta(classes: str | list[str]) -> MetadadoDeClasses:
    lista = list(classes)
    idx = dict(enumerate(lista))
    return MetadadoDeClasses(
        idx_to_char=idx,
        num_classes=len(idx),
        temperatura=1.0,
        modelo_sha256="0" * 64,
        classes_sha256=impressao_das_classes(idx),
        treinado_em="2026-08-25",
    )


class DerivadaDoMetadadoTests(unittest.TestCase):
    def test_a_paleta_sai_do_metadado(self) -> None:
        paleta = P.de_metadado(_meta("♘±a1"))
        self.assertEqual(set(paleta.simbolos) & {"♘", "±"}, {"♘", "±"})

    def test_todo_simbolo_e_classe_do_modelo(self) -> None:
        """Menos os da prateleira da S-247, que existem **por não serem** classe."""
        meta = _meta("♔♕♖♗♘♙±∓⩲⩱∞!?")
        paleta = P.de_metadado(meta)
        do_modelo = set(paleta.simbolos) - paleta.fora_do_modelo
        self.assertTrue(do_modelo <= set(meta.alfabeto))

    def test_a_alfanumerica_nao_entra(self) -> None:
        """O teclado já as tem; a paleta é para o que ele não tem."""
        paleta = P.de_metadado(_meta("abcXYZ019♘"))
        self.assertEqual([s for s in paleta.simbolos if s.isascii() and s.isalnum()], [])

    def test_simbolo_sem_prateleira_vai_para_nao_identificado(self) -> None:
        paleta = P.de_metadado(_meta("♘⁂"))
        nao_identificado = [p for p in paleta.prateleiras if p.nome == P.NAO_IDENTIFICADO]
        self.assertEqual(len(nao_identificado), 1)
        self.assertIn("⁂", nao_identificado[0].simbolos)

    def test_nenhum_simbolo_e_descartado(self) -> None:
        """A trava do item, sobre o metadado real: o que o modelo lê e não é alfanumérico nem
        ligadura **aparece**, nem que seja em "não identificado"."""
        from chess_diagram_ocr.text.modelo import ler_metadado

        meta = ler_metadado()
        esperados = {c for c in meta.alfabeto if len(c) == 1 and not (c.isascii() and c.isalnum())}
        paleta = P.de_metadado(meta)
        self.assertEqual(esperados - set(paleta.simbolos), set())

    def test_as_ligaduras_ficam_fora_da_paleta(self) -> None:
        """`xf6` é classe porque o glifo vem colado no papel, e não porque alguém queira inseri-lo."""
        paleta = P.de_metadado(_meta(["♘", "xf6", "!!"]))
        self.assertNotIn("xf6", paleta.simbolos)
        self.assertEqual(paleta.ligaduras, ("!!", "xf6"))

    def test_sem_metadado_a_paleta_degrada(self) -> None:
        """Aparência não derruba ferramenta (`ui/theme.py`): a aba abre com o conjunto mínimo."""
        with tempfile.TemporaryDirectory() as pasta:
            paleta = P.paleta(Path(pasta) / "nao_existe.json")
        self.assertEqual(set(paleta.simbolos), set(P.MINIMA) | set(paleta.fora_do_modelo))
        self.assertIn("♘", paleta.simbolos)

    def test_o_modulo_nao_importa_tkinter(self) -> None:
        arvore = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        importados: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module.split(".")[0])
        self.assertNotIn("tkinter", importados)

    def test_a_prateleira_do_simbolo_so_nomeia_o_que_existe_ou_o_que_se_oferece(self) -> None:
        """Uma tabela que nomeasse símbolo que ninguém oferece seria promessa vazia -- e a
        prateleira apareceria vazia na tela.

        Os declarados em `EXTRAS_DECLARADOS` contam como existentes: eles são oferecidos pela
        prateleira da S-247, e a linha na tabela é o **destino** deles quando um modelo os aprender.
        """
        from chess_diagram_ocr.text.modelo import ler_metadado

        alcancaveis = set(ler_metadado().alfabeto) | set(P.EXTRAS_DECLARADOS)
        orfaos = sorted(s for s in P.PRATELEIRA_DO_SIMBOLO if s not in alcancaveis)
        self.assertEqual(orfaos, [])


class PrateleiraQueOModeloNaoLeTests(unittest.TestCase):
    def test_as_prateleiras_sao_disjuntas(self) -> None:
        paleta = P.paleta()
        do_modelo = [s for p in paleta.prateleiras if p.do_modelo for s in p.simbolos]
        self.assertEqual(set(do_modelo) & paleta.fora_do_modelo, set())
        self.assertEqual(set(do_modelo) | paleta.fora_do_modelo, set(paleta.simbolos))

    def test_a_prateleira_e_derivada_do_metadado(self) -> None:
        """Ela é a diferença entre o que se oferece e o que o modelo lê -- e não uma lista à mão."""
        paleta = P.de_metadado(_meta("♔♕♖♗♘♙"))
        self.assertEqual(paleta.fora_do_modelo, {"♚", "♛", "♜", "♝", "♞", "♟", "…", "“", "”", "‘", "’"})

    def test_um_modelo_novo_move_o_simbolo_de_prateleira(self) -> None:
        """**Sem tocar em código.** É o critério de aceite, e a prova é um metadado de mentira que
        já conhece as figurinas pretas."""
        paleta = P.de_metadado(_meta("♔♕♖♗♘♙♚♛♜♝♞♟"))
        self.assertEqual(paleta.fora_do_modelo & set("♚♛♜♝♞♟"), set())
        figurinas = [p for p in paleta.prateleiras if p.nome == "Figurinas"][0]
        self.assertIn("♞", figurinas.simbolos)

    def test_a_marca_diz_o_que_precisa_ser_declarado(self) -> None:
        paleta = P.paleta()
        self.assertTrue(paleta.marca("♞"))
        self.assertFalse(paleta.marca("♘"))


class SequenciasTests(unittest.TestCase):
    def test_a_tabela_de_sequencias_e_derivada(self) -> None:
        """Cada sequência aponta para um símbolo que a paleta **já oferece**."""
        paleta = P.paleta()
        oferecidos = set(paleta.simbolos)
        for sequencia, simbolo in paleta.sequencias().items():
            with self.subTest(sequencia=sequencia):
                self.assertIn(simbolo, oferecidos)

    def test_sequencia_para_simbolo_inexistente_levanta(self) -> None:
        with self.assertRaises(P.SequenciaInvalida):
            P.conferir_sequencias({"z": "⁂"}, ("♘",))

    def test_sequencia_repetida_levanta(self) -> None:
        """A mesma sequência para dois símbolos: a segunda apagaria a primeira em silêncio.

        Como um `dict` literal não guarda a chave repetida, o caso chega por junção de tabelas --
        que é como ele apareceria de verdade, com alguém acrescentando uma linha noutro lugar.
        """
        with self.assertRaises(P.SequenciaInvalida):
            P.conferir_sequencias({**{"N": "♘"}, "N ": "♞"}, ("♘",))
        juntas = dict(P.SEQUENCIAS_DECLARADAS)
        juntas["N"] = "♞"
        with self.assertRaises(P.SequenciaInvalida):
            P.conferir_sequencias(juntas, ("♘",))

    def test_duas_sequencias_para_o_mesmo_simbolo_sao_permitidas(self) -> None:
        """`\\N` e `\\n` chegam à mesma peça em livros de notação figurina."""
        self.assertEqual(P.conferir_sequencias({"N": "♘", "cavalo": "♘"}, ("♘",)), {"N": "♘", "cavalo": "♘"})

    def test_o_prefixo_de_escape_e_o_candidato_mais_raro(self) -> None:
        """A medição está no docstring da tabela: 10 ocorrências em 141.353 caracteres, contra 46
        do `@` e 14 do `#`. O teste trava o **número publicado**, que é o que a S-135 cobra."""
        fonte = Path(P.__file__).read_text(encoding="utf-8")
        self.assertIn("141.353", fonte)
        self.assertIn("10 ocorrências", fonte)


class PortasDeInsercaoTests(unittest.TestCase):
    """As três entradas da S-248 chegam ao mesmo símbolo -- a parte que não precisa de janela."""

    def test_as_tres_entradas_apontam_para_a_mesma_lista(self) -> None:
        paleta = P.paleta()
        do_painel = set(paleta.simbolos)
        por_comando = set(P.figurinas(paleta)) | set(P.avaliacoes(paleta))
        por_sequencia = set(paleta.sequencias().values())
        self.assertTrue(por_comando <= do_painel)
        self.assertTrue(por_sequencia <= do_painel)

    def test_as_figurinas_saem_da_notacao_e_nao_de_uma_lista_nova(self) -> None:
        from chess_diagram_ocr.text import notacao

        for simbolo in P.figurinas(P.paleta()):
            with self.subTest(simbolo=simbolo):
                self.assertIn(simbolo, notacao.FIGURINAS)


class MetadadoRealTests(unittest.TestCase):
    def test_a_paleta_do_disco_tem_as_familias_medidas(self) -> None:
        """Os números do cabeçalho do módulo, conferidos contra o `char_meta.json` versionado."""
        bruto = json.loads((Path(P.CAMINHO_PADRAO_META)).read_text(encoding="utf-8"))
        classes = list(bruto["idx_to_char"].values())
        self.assertEqual(len(classes), 314)
        self.assertEqual(sum(1 for c in classes if len(c) > 1), 139)
        self.assertEqual(sum(1 for c in classes if len(c) == 1 and c.isascii() and c.isalnum()), 62)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
