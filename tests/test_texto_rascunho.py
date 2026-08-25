"""O rascunho automático, e a recuperação depois do fechamento (S-255).

**Uma sessão de correção é a coisa mais cara desta aba, e ela vivia só na memória do widget.** Ler a
folha custa ~1 s com o glifo e ~40 s com o modo bloco; corrigir à mão custa a tarde de alguém -- e é
a única coisa da aba que não sai de graça de uma releitura. Fechar a aba, fechar o programa, uma
falha do Tk, e sumia tudo.

Os testes puros trancam a chave estável e a poda; os de janela trancam as três regras que decidem se
o rascunho ajuda ou atrapalha: grava por **inatividade**, só quando está **sujo**, e na abertura
**oferece** -- sem aplicar.
"""

from __future__ import annotations

import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import messagebox

from chess_diagram_ocr.text import arquivo, rascunho, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.texto_panel import TextoPanel


def _pagina(livro: str = "livro.pdf", folha: int = 0, texto: str = "uma folha lida") -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas([LinhaLida(texto, (0.0, 0.0, 100.0, 9.0), 1.0, "camada")])
    return PaginaLida(documento=livro, pagina=folha, colunas=(Coluna(indice=0, blocos=(bloco,)),))


class ChaveTests(unittest.TestCase):
    def test_a_chave_e_estavel(self) -> None:
        primeira = rascunho.chave_de("C:/livros/kemeri.pdf", 57)
        segunda = rascunho.chave_de("C:/livros/kemeri.pdf", 57)
        self.assertEqual(primeira, segunda)

    def test_a_chave_distingue_a_folha(self) -> None:
        self.assertNotEqual(
            rascunho.chave_de("livro.pdf", 3), rascunho.chave_de("livro.pdf", 4)
        )

    def test_a_chave_distingue_documentos_homonimos(self) -> None:
        """Dois livros de mesmo nome em pastas diferentes -- o caso que `state._history_key` trata."""
        um = rascunho.chave_de(Path("um") / "livro.pdf", 0)
        outro = rascunho.chave_de(Path("outro") / "livro.pdf", 0)
        self.assertNotEqual(um, outro)
        self.assertTrue(um.startswith("livro_f1_"))

    def test_a_chave_e_um_nome_de_arquivo_valido(self) -> None:
        """Ela vira nome de arquivo, e o Windows recusa metade da pontuação."""
        chave = rascunho.chave_de("livro: com ? sinais *.pdf", 0)
        self.assertNotIn(":", chave)
        self.assertNotIn("?", chave)
        self.assertNotIn("*", chave)


class DiscoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp())

    def test_grava_e_acha(self) -> None:
        doc = rico.de_pagina(_pagina())
        destino = rascunho.gravar(doc, pasta=self.pasta)
        self.assertIsNotNone(destino)
        achado = rascunho.achar("livro.pdf", 0, pasta=self.pasta)
        self.assertIsNotNone(achado)
        self.assertEqual(rascunho.carregar(achado).para_texto(), doc.para_texto())  # type: ignore[arg-type]

    def test_documento_sem_folha_nao_vira_rascunho(self) -> None:
        """Sem página de origem não há chave estável, e um rascunho que ninguém acha é lixo."""
        self.assertIsNone(rascunho.gravar(rico.de_texto("texto solto"), pasta=self.pasta))

    def test_o_rascunho_e_um_cvtxt(self) -> None:
        """Formato da S-238, e não um formato novo: reabrir um rascunho é reabrir um documento."""
        doc = rico.de_pagina(_pagina())
        destino = rascunho.gravar(doc, pasta=self.pasta)
        assert destino is not None
        self.assertEqual(destino.suffix, arquivo.EXTENSAO)
        self.assertEqual(arquivo.carregar(destino).para_texto(), doc.para_texto())

    def test_descartar_apaga_so_o_daquela_folha(self) -> None:
        rascunho.gravar(rico.de_pagina(_pagina(folha=0)), pasta=self.pasta)
        rascunho.gravar(rico.de_pagina(_pagina(folha=1)), pasta=self.pasta)
        self.assertTrue(rascunho.descartar("livro.pdf", 0, pasta=self.pasta))
        self.assertIsNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))
        self.assertIsNotNone(rascunho.achar("livro.pdf", 1, pasta=self.pasta))

    def test_a_pasta_tem_teto_e_o_mais_antigo_sai(self) -> None:
        for folha in range(6):
            destino = rascunho.gravar(rico.de_pagina(_pagina(folha=folha)), pasta=self.pasta)
            assert destino is not None
            os.utime(destino, (1_700_000_000 + folha, 1_700_000_000 + folha))
        rascunho.podar("livro.pdf", pasta=self.pasta, teto=4)
        sobraram = sorted(c.name for c in self.pasta.glob(f"*{arquivo.EXTENSAO}"))
        self.assertEqual(len(sobraram), 4)
        self.assertIsNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))
        self.assertIsNotNone(rascunho.achar("livro.pdf", 5, pasta=self.pasta))

    def test_a_poda_e_por_documento(self) -> None:
        """Quem trabalha em dois livros não perde o rascunho de um por abrir folhas do outro."""
        rascunho.gravar(rico.de_pagina(_pagina("outro.pdf", 0)), pasta=self.pasta)
        for folha in range(5):
            rascunho.gravar(rico.de_pagina(_pagina("livro.pdf", folha)), pasta=self.pasta)
        rascunho.podar("livro.pdf", pasta=self.pasta, teto=2)
        self.assertIsNotNone(rascunho.achar("outro.pdf", 0, pasta=self.pasta))


_RAIZ: tk.Tk | None = None


def setUpModule() -> None:
    global _RAIZ
    try:
        _RAIZ = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - maquina sem display
        raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
    _RAIZ.withdraw()


def tearDownModule() -> None:
    global _RAIZ
    if _RAIZ is not None:
        _RAIZ.destroy()
        _RAIZ = None


class NaAbaTests(unittest.TestCase):
    def setUp(self) -> None:
        assert _RAIZ is not None
        self.pasta = Path(tempfile.mkdtemp())
        self.avisos: list[str] = []
        self.painel = TextoPanel(
            _RAIZ,
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=self.avisos.append,
            busy=BusyRegistry(),
            pasta_de_rascunhos=self.pasta,
        )

    def _responder(self, resposta: bool) -> None:
        original = messagebox.askyesno
        messagebox.askyesno = lambda *_a, **_k: resposta  # type: ignore[assignment]
        self.addCleanup(setattr, messagebox, "askyesno", original)

    def test_grava_apos_inatividade_e_so_se_sujo(self) -> None:
        """Duas regras num teste porque elas são a mesma decisão: **quando** gravar."""
        self.painel.desenhar(_pagina())
        self.assertIsNone(self.painel.gravar_rascunho(), "gravou com a aba limpa")

        self.painel.editor.insert("end", " corrigido à mão")
        self.painel.update()
        self.assertTrue(self.painel._sujo)
        destino = self.painel.gravar_rascunho()
        self.assertIsNotNone(destino)
        self.assertIn("corrigido", arquivo.carregar(destino).para_texto())  # type: ignore[arg-type]

    def test_a_tecla_reagenda_em_vez_de_gravar_na_hora(self) -> None:
        """Por inatividade, e não por relógio: um relógio fixo grava no meio da digitação."""
        self.painel.desenhar(_pagina())
        self.painel.editor.insert("end", "a")
        self.painel.update()
        self.assertIsNotNone(self.painel._rascunho_agendado, "a tecla não agendou nada")
        self.assertIsNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta), "gravou antes da pausa")

    def test_fechar_deixa_o_rascunho(self) -> None:
        self.painel.desenhar(_pagina())
        self.painel.editor.insert("end", " trabalho não salvo")
        self.painel.update()
        self.painel.gravar_rascunho()
        self.painel.destroy()
        self.assertIsNotNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))

    def test_reabrir_oferece_e_nao_aplica(self) -> None:
        """**Oferece**: sobrescrever o que a pessoa acabou de ler com um rascunho de ontem é o
        contrário do que ela quer."""
        rascunho.gravar(rico.de_pagina(_pagina(texto="versão do rascunho")), pasta=self.pasta)
        self._responder(False)
        self.painel.desenhar(_pagina(texto="versão recém-lida"))
        self.assertIn("recém-lida", self.painel.texto_atual())

    def test_aceitar_a_oferta_traz_o_rascunho(self) -> None:
        rascunho.gravar(rico.de_pagina(_pagina(texto="versão do rascunho")), pasta=self.pasta)
        self._responder(True)
        self.painel.desenhar(_pagina(texto="versão recém-lida"))
        self.assertIn("rascunho", self.painel.texto_atual())

    def test_recusar_nao_apaga(self) -> None:
        rascunho.gravar(rico.de_pagina(_pagina(texto="versão do rascunho")), pasta=self.pasta)
        self._responder(False)
        self.painel.desenhar(_pagina())
        self.assertIsNotNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))

    def test_recuperar_apaga(self) -> None:
        """Recuperado é trabalho que chegou a um lugar melhor -- a tela."""
        rascunho.gravar(rico.de_pagina(_pagina(texto="versão do rascunho")), pasta=self.pasta)
        self._responder(True)
        self.painel.desenhar(_pagina())
        self.assertIsNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))

    def test_salvar_apaga(self) -> None:
        from tkinter import filedialog

        self.painel.desenhar(_pagina())
        self.painel.editor.insert("end", " corrigido")
        self.painel.update()
        self.painel.gravar_rascunho()
        self.assertIsNotNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))

        original = filedialog.asksaveasfilename
        destino = self.pasta / "salvo.cvtxt"
        filedialog.asksaveasfilename = lambda **_k: str(destino)  # type: ignore[assignment]
        self.addCleanup(setattr, filedialog, "asksaveasfilename", original)
        self.painel.salvar_documento()

        self.assertTrue(destino.exists())
        self.assertIsNone(rascunho.achar("livro.pdf", 0, pasta=self.pasta))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
