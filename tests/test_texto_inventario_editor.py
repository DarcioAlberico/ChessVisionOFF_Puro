"""O inventário do editor: nada de recurso sem comando, atalho e teste (S-256).

**Este plano acrescentou mais de vinte recursos a uma aba que tinha seis controles, e cada um deles
é fácil de fazer errado rápido.** `tag_configure("negrito", font=...)` mais um `tag_add` resolve o
negrito na tela em quatro linhas e entrega, no Salvar, o `.txt` de antes -- o achado 1 do
ROADMAP_EDITOR, que nenhum teste de interface pegaria porque **na tela está tudo certo**.

É a mesma classe de defeito que a S-233 mede para as peles, com um agravante: lá o comando existe e
está escondido; aqui o recurso **existe e não persiste**, que é pior, porque parece funcionar.

O teste que mais paga é o primeiro: ele é **paramétrico sobre `fields(Atributos)`**, então um campo
novo entra nele sozinho -- e quem o acrescentar sem tratar a persistência descobre na suíte, e não
três meses depois no arquivo de quem passou a tarde corrigindo uma página.
"""

from __future__ import annotations

import ast
import json
import tkinter as tk
import unittest
from dataclasses import fields
from pathlib import Path

from ambiente_de_teste import pasta_temporaria, quadro
from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.cli import editor_inventario
from chess_diagram_ocr.text import arquivo, exportacao, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from chess_diagram_ocr.ui import alcance, comandos, menu, texto_panel
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.texto_panel import TextoPanel

RAIZ = Path(__file__).resolve().parents[1]
PAINEL = RAIZ / "src" / "chess_diagram_ocr" / "ui" / "texto_panel.py"

VALOR_DE_TESTE: dict[str, object] = {
    "negrito": True,
    "italico": True,
    "sublinhado": True,
    "tachado": True,
    "cor": "nota",
    "realce": "destaque",
    "estilo": "titulo",
    "alinhamento": "centro",
    "corpo": 2,
    "fora_do_modelo": True,
}
"""Um valor **não padrão** por atributo, para o ciclo ter o que perder.

A tabela é declarada e conferida: um campo novo em `Atributos` sem valor aqui reprova
`test_todo_atributo_tem_valor_de_teste`, que é o que impede o teste paramétrico de passar em verde
sobre um campo que ele não exercita."""


def _pagina(texto: str = "uma folha corrigida") -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas([LinhaLida(texto, (0.0, 0.0, 100.0, 9.0), 1.0, "camada")])
    return PaginaLida(documento="livro.pdf", pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),))


_RAIZ: tk.Tk | None = None


def setUpModule() -> None:
    """A raiz é a do processo (`tests/tk_root.py`), e não uma deste módulo (S-416)."""
    global _RAIZ
    _RAIZ = raiz_do_processo()


class CicloCompletoTests(unittest.TestCase):
    """Editar → salvar → reabrir → exportar, um atributo de cada vez."""

    def _painel(self) -> TextoPanel:
        assert _RAIZ is not None
        return TextoPanel(
            quadro(self, _RAIZ),
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=lambda _m: None,
            busy=BusyRegistry(),
            pasta_de_rascunhos=pasta_temporaria(self),
        )

    def test_todo_atributo_tem_valor_de_teste(self) -> None:
        self.assertEqual({c.name for c in fields(rico.Atributos)}, set(VALOR_DE_TESTE))

    def test_todo_atributo_sobrevive_ao_ciclo(self) -> None:
        """**O teste que mais paga.** Paramétrico sobre os campos: um atributo novo entra sozinho.

        O ciclo é o inteiro -- o documento vai para a tela, volta do widget, é gravado, é lido de
        volta -- porque é assim que o defeito aparece: um atributo que só existe como tag do Tk
        atravessa a tela e morre na gravação, e na tela está tudo certo.
        """
        pasta = pasta_temporaria(self)
        for campo in fields(rico.Atributos):
            with self.subTest(campo=campo.name):
                atributos = rico.Atributos(**{campo.name: VALOR_DE_TESTE[campo.name]})
                doc = rico.DocumentoRico(
                    corridas=(rico.Corrida(texto="um trecho", atributos=atributos, bloco=0),),
                    origem=_pagina(),
                )
                painel = self._painel()
                painel.desenhar_documento(doc)
                da_tela = painel.documento_atual()
                self.assertEqual(
                    getattr(da_tela.corridas[0].atributos, campo.name),
                    VALOR_DE_TESTE[campo.name],
                    "o atributo não sobreviveu à ida e volta pelo widget",
                )

                destino = pasta / f"{campo.name}.cvtxt"
                arquivo.gravar(destino, da_tela)
                do_disco = arquivo.carregar(destino)
                self.assertEqual(
                    getattr(do_disco.corridas[0].atributos, campo.name),
                    VALOR_DE_TESTE[campo.name],
                    "o atributo não sobreviveu ao arquivo",
                )
                painel.destroy()

    def test_todo_atributo_esta_declarado_por_formato(self) -> None:
        """`False` é resposta válida e **explícita**: perda silenciosa é o que o item impede."""
        tabela = exportacao.suporte_por_formato()
        for extensao, suporte in tabela.items():
            with self.subTest(formato=extensao):
                self.assertEqual(set(suporte), {c.name for c in fields(rico.Atributos)})

    def test_todo_atributo_tem_ao_menos_um_formato_que_o_suporta(self) -> None:
        """Um atributo que nenhum formato expressa é trabalho que **nunca** sai da aba."""
        tabela = exportacao.suporte_por_formato()
        orfaos = [
            campo.name
            for campo in fields(rico.Atributos)
            if not any(suporte[campo.name] for suporte in tabela.values())
        ]
        self.assertEqual(orfaos, [])

    def test_o_atributo_perdido_e_contado(self) -> None:
        """Quem não suporta, conta -- e é a conta que o relatório da S-254 mostra."""
        for campo in fields(rico.Atributos):
            with self.subTest(campo=campo.name):
                doc = rico.DocumentoRico(
                    corridas=(
                        rico.Corrida(
                            texto="um trecho",
                            atributos=rico.Atributos(**{campo.name: VALOR_DE_TESTE[campo.name]}),
                        ),
                    )
                )
                for extensao, suporte in exportacao.suporte_por_formato().items():
                    if suporte[campo.name]:
                        continue
                    relatorio = exportacao.exportar(doc, exportacao.formato_de(extensao))
                    self.assertEqual(relatorio.perdas.get(campo.name), 1, f"{extensao} não contou")


class ComandoEAlcanceTests(unittest.TestCase):
    def test_nenhum_rotulo_a_mao_no_painel(self) -> None:
        """A varredura da S-324, agora sobre `ui/texto_panel.py`."""
        arvore = ast.parse(PAINEL.read_text(encoding="utf-8"))
        achados: list[str] = []
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
                continue
            if no.func.attr not in ("Button", "Checkbutton", "Menubutton"):
                continue
            for chave in no.keywords:
                if chave.arg == "text" and isinstance(chave.value, (ast.Constant, ast.JoinedStr)):
                    escrito = (
                        chave.value.value if isinstance(chave.value, ast.Constant) else "<f-string>"
                    )
                    # O botão de símbolo da paleta é o próprio símbolo, e ele vem do metadado do
                    # modelo (S-246) -- não é rótulo de comando, é o dado.
                    achados.append(f"linha {no.lineno}: {escrito!r}")
        self.assertEqual(achados, [])

    def test_todo_comando_do_editor_esta_no_inventario(self) -> None:
        """A S-233 aplicada ao editor: nenhuma pele esconde um comando sem o menu alcançá-lo."""
        do_editor = set(editor_inventario._APELIDOS)
        self.assertEqual(alcance.perdidos(catalogo=do_editor), {})

    def test_todo_comando_do_editor_tem_dono_no_painel(self) -> None:
        """Comando no catálogo sem método que o atenda é o item de menu inerte da S-161."""
        for acao, metodo in editor_inventario._APELIDOS.items():
            with self.subTest(acao=acao):
                self.assertIn(acao, comandos.por_acao, "comando fora do catálogo")
                self.assertTrue(
                    hasattr(TextoPanel, metodo), f"{acao} aponta para {metodo}, que o painel não tem"
                )

    def test_todo_comando_do_editor_alcanca_o_menu(self) -> None:
        declarados = set(menu.acoes_declaradas())
        fora = sorted(acao for acao in editor_inventario._APELIDOS if acao not in declarados)
        self.assertEqual(fora, [])

    def test_a_aba_declara_as_acoes_que_toma_para_si(self) -> None:
        self.assertTrue(texto_panel.ACOES_PROPRIAS)
        for acao in texto_panel.ACOES_PROPRIAS:
            with self.subTest(acao=acao):
                self.assertIn(acao, comandos.por_acao)


class InventarioPublicadoTests(unittest.TestCase):
    def test_o_inventario_publica_data_e_commit(self) -> None:
        """Na disciplina da S-219: um relatório que não diz quando e com que código foi medido é um
        número que ninguém reproduz."""
        dados = editor_inventario.inventario()
        self.assertRegex(dados["quando"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIn("commit", dados)
        self.assertTrue(dados["comandos_do_editor"])

    def test_o_inventario_no_disco_bate_com_o_de_hoje(self) -> None:
        """O arquivo publicado é o mesmo inventário -- **menos** a data e o commit, que mudam."""
        publicados = sorted((RAIZ / "docs" / "metrics").glob("editor_inventario_*.json"))
        if not publicados:
            self.skipTest("nenhum inventário do editor publicado neste checkout")
        do_disco = json.loads(publicados[-1].read_text(encoding="utf-8"))
        de_hoje = editor_inventario.inventario()
        for chave in ("comandos_do_editor", "atributos_do_documento", "suporte_por_formato"):
            with self.subTest(chave=chave):
                self.assertEqual(do_disco[chave], de_hoje[chave])

    def test_o_inventario_nao_acha_perda(self) -> None:
        """As quatro perguntas do item, respondidas: nada fora do menu, nada sem formato, nenhuma
        pele perdendo comando."""
        dados = editor_inventario.inventario()
        self.assertEqual(dados["comandos_do_editor_fora_do_menu"], [])
        self.assertEqual(dados["atributos_sem_formato_que_os_suporte"], [])
        self.assertEqual(dados["peles_que_perdem_comando"], {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
