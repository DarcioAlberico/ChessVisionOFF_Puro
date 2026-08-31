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

import json
import unittest
from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.cli import editor_inventario
from chess_diagram_ocr.text import arquivo, exportacao, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

RAIZ = Path(__file__).resolve().parents[1]
PAINEL = RAIZ / "src" / "chess_diagram_ocr" / "qt" / "painel_de_texto.py"

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


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class CicloCompletoTests(unittest.TestCase):
    """Editar → salvar → reabrir → exportar, um atributo de cada vez."""

    def setUp(self) -> None:
        self.app = aplicacao()
        """**Sem isto o processo aborta, e não falha.** Construir um `QWidget` antes de existir uma
        `QApplication` mata o interpretador com código 127 -- dois pontos impressos, nenhuma linha
        de resumo e nenhum nome de teste. É o mesmo modo de falha do nome não-ASCII num `connect`,
        e a guarda contra ele é `test_disciplina_da_suite.UmaRaizSoTests`."""

    def _painel(self) -> PainelDeTexto:
        """O painel do Qt, montado sem tela.

        **O ciclo continua sendo o inteiro, e é por isso que o teste sobreviveu ao corte.** Ele
        media um atributo que existisse só como etiqueta do `tk.Text`; a pergunta não era do
        toolkit -- é "o que a tela devolve é o que entrou?" --, e um `QTextCharFormat` tem
        exatamente as mesmas chances de perder um atributo pelo caminho.
        """
        from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

        montado = PainelDeTexto(dpi=72)
        self.addCleanup(descartar, montado)
        return montado

    def test_todo_atributo_tem_valor_de_teste(self) -> None:
        self.assertEqual({c.name for c in fields(rico.Atributos)}, set(VALOR_DE_TESTE))

    def test_todo_atributo_sobrevive_ao_ciclo(self) -> None:
        """**O teste que mais paga.** Paramétrico sobre os campos: um atributo novo entra sozinho.

        **A perna do widget saiu no corte do Tk, e a razão é de projeto e não de escopo.** O
        defeito medido era um atributo que só existisse como etiqueta do `tk.Text`: lá o documento
        era **reconstruído** a partir do editor (`de_despejo`), e um atributo sem etiqueta
        atravessava a tela certo e morria na gravação. No painel do Qt o documento é o estado e o
        widget é um desenho dele -- não há leitura de volta, e por isso não há onde o atributo se
        perder. O que continua podendo se perder é a **gravação**, e é o que este teste mede;
        que a tela desenha cada atributo é medido em `tests/test_qt_texto.py::FormatoTests`.
        """
        pasta = pasta_temporaria(self)
        painel = self._painel()
        for campo in fields(rico.Atributos):
            with self.subTest(campo=campo.name):
                atributos = rico.Atributos(**{campo.name: VALOR_DE_TESTE[campo.name]})
                doc = rico.DocumentoRico(
                    corridas=(rico.Corrida(texto="um trecho", atributos=atributos, bloco=0),),
                    origem=_pagina(),
                )
                painel.desenhar_documento(doc)

                destino = pasta / f"{campo.name}.cvtxt"
                arquivo.gravar(destino, painel.documento)
                do_disco = arquivo.carregar(destino)
                self.assertEqual(
                    getattr(do_disco.corridas[0].atributos, campo.name),
                    VALOR_DE_TESTE[campo.name],
                    "o atributo não sobreviveu ao arquivo",
                )

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
        """As perguntas do item, respondidas: nada fora do menu, nada sem formato.

        **A terceira saiu no corte do Tk (S-506).** Ela era `peles_que_perdem_comando`, e vinha de
        `ui/alcance.perdidos()` -- que respondia "que ação do catálogo o cromo desta pele não
        alcança". Os três cromos (clássico, foco, fita) eram montagens do Tk, e o inventário
        passou a não ter o que responder ali. Quem cobre o buraco hoje é
        `tests/test_qt_janela.py`, que afirma a mesma propriedade sobre a janela de verdade: todo
        item de menu tem comando, e todo comando das abas aponta para um método que existe.
        """
        dados = editor_inventario.inventario()
        self.assertEqual(dados["comandos_do_editor_fora_do_menu"], [])
        self.assertEqual(dados["atributos_sem_formato_que_os_suporte"], [])
        self.assertNotIn("peles_que_perdem_comando", dados, "a chave voltou sem quem a responda")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
