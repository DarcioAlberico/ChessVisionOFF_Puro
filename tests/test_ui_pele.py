"""A pele como estado da janela, e a clássica como padrão (S-221).

Não havia onde guardar "qual aparência": o único eixo que existia é o tema, e ele é variável de
ambiente -- escolhido antes de o programa abrir e invisível de dentro dele. O que este item
entrega é o registro, o campo no estado e o submenu; o que ele **não** entrega é diferença
visível, e é isso que a maior parte destes testes afirma.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from chess_diagram_ocr.ui import pele
from chess_diagram_ocr.ui.state import STATE_VERSION, AppState, load_state, save_state, state_from_dict


class RegistroTests(unittest.TestCase):
    def test_a_pele_padrao_e_a_classica(self) -> None:
        """Sem `skin` no disco e sem a variável, a pele é a clássica -- e ela é a janela de hoje."""
        self.assertEqual(pele.CLASSICA, pele.escolhida("", ambiente={}))
        self.assertEqual(pele.CLASSICA, pele.escolhida(ambiente={}))
        self.assertEqual("", AppState().skin, "o padrão do estado é 'nunca escolhida'")

    def test_a_classica_e_a_primeira_e_o_padrao(self) -> None:
        """O que não muda quando o registro cresce. Quando esta S foi escrita havia **uma** pele,
        e o teste dizia isso; a S-223 acrescentou a "Foco" e a S-227 acrescenta a "Fita". O que
        continua valendo é a regra 1: quem nunca abrir `Ver ▸ Aparência` tem a janela de hoje."""
        self.assertEqual(pele.CLASSICA, pele.PELES[0].nome)
        self.assertEqual(pele.CLASSICA, pele.escolhida("", ambiente={}))

    def test_toda_pele_tem_nome_de_chave_e_rotulo_de_gente(self) -> None:
        """Chave e texto de interface não são a mesma coisa, e a S-166 já fixou isso."""
        for registro in pele.PELES:
            with self.subTest(pele=registro.nome):
                self.assertEqual(registro.nome, registro.nome.lower())
                self.assertTrue(registro.nome.isascii(), "o nome vai para o disco: sem acento")
                self.assertTrue(registro.rotulo.strip())
                self.assertIn(registro.densidade, pele.DENSIDADES)

    def test_pele_desconhecida_cai_na_classica_com_aviso(self) -> None:
        """E o aviso **nomeia** a inválida: sem o nome, quem escreveu `CVOFF_SKIN=mosaico` conclui
        que a variável não é lida.

        O nome usado aqui era `fita` até a S-227 registrá-la. Um teste do caminho do inválido
        precisa de um nome que **continue** inválido, e trocá-lo é mais honesto que travar o
        registro de peles para manter o teste de pé.
        """
        with self.assertLogs(pele.logger, level="WARNING") as registro:
            self.assertEqual(pele.CLASSICA, pele.valida("mosaico"))
        self.assertIn("mosaico", "\n".join(registro.output))
        self.assertNotIn("mosaico", pele.por_nome, "escolha um nome que continue inválido")

    def test_nome_vazio_nao_avisa_nada(self) -> None:
        """"Nunca escolheu" não é erro, e um aviso a cada abertura é ruído que ensina a ignorar."""
        with self.assertNoLogs(pele.logger, level="WARNING"):
            self.assertEqual(pele.CLASSICA, pele.valida(""))

    def test_registrada_levanta_para_quem_ja_devia_saber(self) -> None:
        """`valida` é para o que vem de fora; `registrada` é para o código, e aí um nome errado
        é defeito e não entrada."""
        self.assertIs(pele.PELES[0], pele.registrada(pele.CLASSICA))
        with self.assertRaises(KeyError):
            pele.registrada("mosaico")

    def test_o_ambiente_ganha_da_guardada(self) -> None:
        """A diferença em relação a `theme.apply_theme`, e ela é de propósito: lá o argumento é
        de quem chama no código; aqui a guardada é do disco, e uma variável que o disco vencesse
        não serviria para abrir o programa numa aparência a partir de um roteiro."""
        self.assertEqual(
            pele.CLASSICA,
            pele.escolhida("naoexiste", ambiente={pele.PELE_ENV: pele.CLASSICA}),
        )

    def test_densidade_desconhecida_levanta(self) -> None:
        with self.assertRaises(KeyError):
            pele.Pele("teste", "Teste", "classico", densidade="apertada")


class PersistenciaTests(unittest.TestCase):
    """O campo novo no estado, e a promessa de que a versão 2 continua abrindo."""

    def test_a_pele_sobrevive_ao_fechamento(self) -> None:
        with TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "estado.json"
            guardado = AppState()
            guardado.skin = pele.CLASSICA
            save_state(caminho, guardado)
            self.assertEqual(pele.CLASSICA, load_state(caminho).skin)

    def test_estado_da_versao_2_e_lido_sem_perda(self) -> None:
        """A 3 só acrescenta `skin`. Um arquivo da 2 abre com tudo, e sem pele escolhida.

        **O número não é o que se afirma aqui, e ele já subiu**: a S-230 levou o esquema à 4 para
        guardar o conjunto de peças. O que este teste guarda é a propriedade que precisa
        sobreviver a toda subida -- um arquivo antigo abre sem perder campo nenhum, e o que ele
        não tinha cai no padrão em vez de ser adivinhado. `assertGreaterEqual` e não
        `assertEqual` por isso: crescer é esperado, e voltar atrás não.
        """
        self.assertGreaterEqual(STATE_VERSION, 3, "a versão que introduziu `skin`")
        versao_2 = {
            "version": 2,
            "last_pdf": "livro.pdf",
            "last_page": 7,
            "pdf_zoom": 1.2,
            "board_zoom": 0.9,
            "pdf_history": {"livro.pdf": 7},
            "show_heatmap": False,
            "show_diagram_boxes": False,
            "wheel_flips_page": False,
            "review_queue_path": "fila.json",
            "window_geometry": "1700x980+120+40",
            "sash_fraction": 0.42,
            "active_tab": "Resultado",
        }
        lido = state_from_dict(versao_2)
        for campo, esperado in versao_2.items():
            if campo == "version":
                continue
            with self.subTest(campo=campo):
                self.assertEqual(esperado, getattr(lido, campo))
        self.assertEqual("", lido.skin, "a 2 não tinha pele, e inventar uma seria adivinhar")

    def test_a_pele_gravada_volta_no_json(self) -> None:
        self.assertEqual("", AppState().to_dict()["skin"])

    def test_pele_de_tipo_errado_cai_no_padrao(self) -> None:
        """Como todo campo deste arquivo: tipo errado não derruba a leitura inteira."""
        self.assertEqual("", state_from_dict({"version": STATE_VERSION, "skin": 3}).skin)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
