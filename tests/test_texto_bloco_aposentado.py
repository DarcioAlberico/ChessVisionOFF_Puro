"""S-726: a leitura em blocos saiu do caminho da página, com quem a usava, e o que estava gravado abre sem ela.

Os nomes das duas chaves são montados aqui de propósito: `grep -rln` nelas, em `src` e `tests`, tem de achar só a migração
do estado. Este arquivo é quem afirma isso, e por isso não pode ser um dos achados.
"""

from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.cli import texto_pagina
from chess_diagram_ocr.text import caderno, leitor, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from chess_diagram_ocr.ui import comandos, fita_do_texto, menu, state, texto_declarado

CHAVE_DO_ESTADO = "texto" + "_bloco"
CHAVE_DO_INDICE = "modo" + "_bloco"
RAIZ = Path(__file__).resolve().parents[1]


class SemRastroTests(unittest.TestCase):
    def test_so_a_migracao_do_estado_cita_as_chaves(self) -> None:
        """É a verificação do item. **Não é vácua**: `ui/state.py` tem de aparecer, e por isso o conjunto é exato."""
        achados = set()
        for pasta in ("src", "tests"):
            for caminho in (RAIZ / pasta).rglob("*"):
                if caminho.is_file() and "__pycache__" not in caminho.parts:
                    conteudo = caminho.read_bytes()
                    if CHAVE_DO_ESTADO.encode() in conteudo or CHAVE_DO_INDICE.encode() in conteudo:
                        achados.add(caminho.relative_to(RAIZ).as_posix())
        self.assertEqual(achados, {"src/chess_diagram_ocr/ui/state.py"})

    def test_nenhum_comando_nenhum_item_de_menu_nenhum_controle(self) -> None:
        self.assertNotIn(CHAVE_DO_INDICE, [c.acao for c in comandos.CATALOGO])
        self.assertNotIn(CHAVE_DO_INDICE, menu.acoes_declaradas())
        self.assertNotIn(CHAVE_DO_INDICE, texto_declarado.COMANDOS_DA_ABA)
        self.assertNotIn(f"@{CHAVE_DO_INDICE}", fita_do_texto.CONTROLES)
        self.assertNotIn(CHAVE_DO_INDICE, fita_do_texto.CONTROLE_DO_COMANDO)
        self.assertNotIn(f"@{CHAVE_DO_INDICE}", fita_do_texto.controles())

    def test_o_leitor_nao_tem_mais_o_parametro(self) -> None:
        for funcao in (leitor.ler_pagina, leitor.linhas_do_glifo):
            with self.subTest(funcao=funcao.__name__):
                self.assertNotIn(CHAVE_DO_INDICE, inspect.signature(funcao).parameters)
        self.assertFalse(hasattr(leitor, "leitor_de_linha_padrao"), "o segundo opinante da página ficou sem quem o chame")

    def test_o_cli_recusa_a_opcao(self) -> None:
        """`--bloco` não pode cair num prefixo de outra opção do argparse: tem de ser erro de uso."""
        with self.assertRaises(SystemExit) as saida, mock.patch("sys.stderr"):
            texto_pagina.main(["livro.pdf", "--bloco"])
        self.assertEqual(saida.exception.code, 2)


class EstadoAntigoTests(unittest.TestCase):
    def test_o_arquivo_antigo_abre_e_a_chave_nao_volta_ao_disco(self) -> None:
        caminho = pasta_temporaria(self) / "janela.json"
        caminho.write_text(
            json.dumps({"version": state.STATE_VERSION, "last_pdf": "livro.pdf", "texto_motor": "glifo", CHAVE_DO_ESTADO: True}),
            encoding="utf-8",
        )
        lido = state.load_state(caminho)
        self.assertEqual((lido.last_pdf, lido.texto_motor), ("livro.pdf", "glifo"), "descartar a chave não custa as outras")
        self.assertFalse(hasattr(lido, CHAVE_DO_ESTADO))
        state.save_state(caminho, lido)
        self.assertNotIn(CHAVE_DO_ESTADO, json.loads(caminho.read_text(encoding="utf-8")))

    def test_a_migracao_descarta_a_chave_e_nao_muda_o_dicionario_de_quem_chamou(self) -> None:
        cru = {"version": 1, "last_pdf": "livro.pdf", CHAVE_DO_ESTADO: True}
        self.assertEqual(state._migrate(cru), {"version": 1, "last_pdf": "livro.pdf"})
        self.assertIn(CHAVE_DO_ESTADO, cru)

    def test_a_versao_nao_subiu(self) -> None:
        """Tirar uma chave não pede versão nova: o programa anterior lê o arquivo sem ela, e com versão nova ele o recusaria."""
        self.assertEqual(state.STATE_VERSION, 7)


class CadernoAntigoTests(unittest.TestCase):
    def setUp(self) -> None:
        raiz = pasta_temporaria(self)
        self.pasta = raiz / "cadernos"
        self.pdf = raiz / "livro.pdf"
        self.pdf.write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 64)

    def abrir(self) -> caderno.Caderno:
        aberto = caderno.abrir(self.pdf, pasta=self.pasta)
        assert aberto is not None
        self.addCleanup(aberto.fechar)
        return aberto

    def test_a_folha_lida_em_blocos_abre_do_caderno_e_o_indice_perde_a_chave(self) -> None:
        livro = self.abrir()
        bloco = BlocoDeTexto.de_linhas([LinhaLida("lida em blocos", (0.0, 0.0, 100.0, 9.0), 0.5, "glifo")])  # type: ignore[arg-type]
        doc = rico.de_pagina(PaginaLida(documento=str(self.pdf), pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),)))
        livro.guardar_leitura(doc, motor="glifo")
        indice = livro.pasta / "indice.json"
        dados = json.loads(indice.read_text(encoding="utf-8"))
        dados["folhas"]["1"][CHAVE_DO_INDICE] = True
        indice.write_text(json.dumps(dados), encoding="utf-8")
        livro.fechar()

        reaberto = self.abrir()
        guardada = reaberto.estado(0)
        assert guardada is not None
        self.assertEqual(guardada.motor, "glifo")
        self.assertTrue(caderno.abre_do_caderno(guardada, motor="glifo"), "a pessoa não pediu reler: a folha está lá")
        self.assertFalse(caderno.abre_do_caderno(guardada, motor="fusao:eng"), "trocar de motor segue relendo")
        reaberto.marcar(0, caderno.CONFERIDA)
        self.assertNotIn(CHAVE_DO_INDICE, json.loads(indice.read_text(encoding="utf-8"))["folhas"]["1"])


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FiacaoTests(unittest.TestCase):
    """Teste de fiação afirma efeito: o que o leitor recebe, e o que a aba deixa no estado."""

    def setUp(self) -> None:
        from chess_diagram_ocr.qt import painel_de_texto as qt_texto

        self.qt_texto = qt_texto
        self.app = aplicacao()
        self.painel = qt_texto.PainelDeTexto(dpi=72, pasta_de_rascunhos=pasta_temporaria(self) / "rascunhos")
        self.addCleanup(descartar, self.painel)

    def test_o_estado_antigo_chega_a_aba_e_o_que_ela_grava_nao_tem_a_chave(self) -> None:
        antigo = state.state_from_dict({"version": 7, "texto_motor": "glifo", CHAVE_DO_ESTADO: True})
        self.painel.aplicar_estado(antigo)
        self.assertEqual(self.painel.motor, "glifo")
        self.painel.anotar_estado(antigo)
        self.assertNotIn(CHAVE_DO_ESTADO, antigo.to_dict())

    def test_a_aba_nao_tem_a_caixa(self) -> None:
        self.assertFalse(hasattr(self.painel, "caixa_de_bloco"))
        self.assertFalse(hasattr(self.painel, CHAVE_DO_INDICE))

    def test_o_que_a_aba_manda_o_leitor_aceita(self) -> None:
        """`autospec` confere a assinatura de verdade: um argumento que o leitor não tem levanta aqui."""
        lida = PaginaLida(documento="livro.pdf", pagina=0)
        with mock.patch("chess_diagram_ocr.text.leitor.ler_pagina", autospec=True, return_value=lida) as ler:
            self.qt_texto._ler(Path("livro.pdf"), 0, dpi=72, motor="glifo", imagem_rgb=None)
        ler.assert_called_once()
        self.assertEqual(ler.call_args.kwargs["motor"], "glifo")


if __name__ == "__main__":
    unittest.main()
