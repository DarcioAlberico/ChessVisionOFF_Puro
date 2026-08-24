"""As quatro origens do editor, testadas sem janela (S-49).

Antes deste item, as asserções abaixo só existiam dirigindo o Tk pelo roteiro headless --
e por isso quase não existiam. A regra que elas cobrem é a mais delicada da interface: o que
`Ctrl+S` significa depende de por onde o diagrama entrou, e errar isso cria uma segunda
amostra da mesma imagem deixando o rótulo errado no arquivo (S-23).
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import numpy as np

from chess_diagram_ocr.service import RecognizedDiagram
from chess_diagram_ocr.ui.editor_model import DiagramEditorModel, EditorBinding, SaveKind

PLACEMENT = "4k3/8/8/8/8/8/8/4K3"
OUTRO = "4k3/8/8/8/8/8/8/3QK3"


def _diagrama(placement: str = PLACEMENT, side: str = "w") -> RecognizedDiagram:
    board = np.zeros((64, 64, 3), dtype=np.uint8)
    return RecognizedDiagram.from_label(board, placement, side_to_move=side)


class BindingTests(unittest.TestCase):
    """`load` é o ponto único de troca de vínculo. Antes eram quatro caminhos."""

    def test_abrir_item_da_fila_solta_o_vinculo_com_a_pagina(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.PAGE, page_key=("livro.pdf", 80))
        model.load([_diagrama()], binding=EditorBinding.REVIEW, review_position=3)

        self.assertIs(model.binding, EditorBinding.REVIEW)
        self.assertIsNone(model.page_key)
        self.assertIsNone(model.editing_sample)
        self.assertEqual(model.review_position, 3)

    def test_abrir_amostra_do_dataset_solta_o_vinculo_com_a_fila(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.REVIEW, review_position=3)
        model.load([_diagrama()], binding=EditorBinding.SAMPLE, editing_sample="b1.png")

        self.assertIs(model.binding, EditorBinding.SAMPLE)
        self.assertIsNone(model.review_position, "salvar fecharia um item da fila que ninguém corrigiu")

    def test_um_vinculo_sem_a_ancora_correspondente_e_recusado(self) -> None:
        model = DiagramEditorModel()
        for binding in (EditorBinding.PAGE, EditorBinding.REVIEW, EditorBinding.SAMPLE):
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                model.load([_diagrama()], binding=binding)

    def test_duas_ancoras_ao_mesmo_tempo_sao_recusadas(self) -> None:
        """O estado que o item existe para tornar impossível de construir por acidente."""
        model = DiagramEditorModel()
        with self.assertRaises(ValueError):
            model.load(
                [_diagrama()], binding=EditorBinding.SAMPLE, editing_sample="b1.png", review_position=3
            )

    def test_sem_vinculo_e_o_caso_da_imagem_local(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.NONE)
        self.assertIs(model.binding, EditorBinding.NONE)
        self.assertIsNone(model.page_key)


class SaveTargetTests(unittest.TestCase):
    """A pergunta que antes exigia uma janela: "o que acontece se eu salvar agora?"."""

    def test_abrir_linha_do_dataset_e_salvar_regrava_a_mesma_linha(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.SAMPLE, editing_sample="b1.png")

        alvo = model.save_target()
        self.assertIs(alvo.kind, SaveKind.REWRITE_ROW)
        self.assertEqual(alvo.filename, "b1.png")
        self.assertIsNone(alvo.settle_position)

    def test_abrir_item_da_fila_e_salvar_nao_pode_criar_uma_segunda_amostra(self) -> None:
        """Cria amostra nova, sim -- o item da fila não é uma linha do dataset --, mas
        também fecha o item na fila. É o par que o `ResultPanel` fazia em dois métodos."""
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.REVIEW, review_position=7)

        alvo = model.save_target()
        self.assertIs(alvo.kind, SaveKind.NEW_SAMPLE)
        self.assertEqual(alvo.settle_position, 7)
        self.assertIsNone(alvo.filename)

    def test_resultado_de_pagina_salva_amostra_nova_e_nao_fecha_fila_nenhuma(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.PAGE, page_key=("livro.pdf", 80))

        alvo = model.save_target()
        self.assertIs(alvo.kind, SaveKind.NEW_SAMPLE)
        self.assertIsNone(alvo.settle_position)

    def test_editor_vazio_nao_tem_o_que_salvar(self) -> None:
        self.assertIs(DiagramEditorModel().save_target().kind, SaveKind.NOTHING)

    def test_fechar_o_item_da_fila_desfaz_o_vinculo(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.REVIEW, review_position=7)
        model.settled()

        self.assertIsNone(model.review_position)
        self.assertIsNone(model.save_target().settle_position, "salvar de novo fecharia o item duas vezes")


class RouteTests(unittest.TestCase):
    """A coluna `corrected_by` da S-52: **como** a amostra chegou ao rótulo."""

    def test_amostra_aceita_sem_mexer_e_diferente_de_amostra_corrigida(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.NONE)
        aceita = model.save_target().route

        model.apply_placement(OUTRO)
        corrigida = model.save_target().route
        self.assertNotEqual(aceita, corrigida)

    def test_fen_vinda_da_net_nao_conta_como_trabalho_humano(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.NONE)
        model.apply_placement(OUTRO)
        a_mao = model.save_target().route

        model.load([_diagrama()], binding=EditorBinding.NONE)
        model.mark_net_corrected(0, OUTRO)
        remoto = model.save_target().route

        self.assertNotEqual(a_mao, remoto)

    def test_a_marca_de_net_nao_sobrevive_a_um_carregamento_novo(self) -> None:
        """Os índices são por carregamento: o diagrama 0 da página seguinte é outro."""
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.NONE)
        model.mark_net_corrected(0, OUTRO)
        model.load([_diagrama()], binding=EditorBinding.NONE)
        self.assertEqual(model.net_corrected, set())

    def test_regravar_linha_do_dataset_tem_rota_propria(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.SAMPLE, editing_sample="b1.png")
        self.assertEqual(model.save_target().route, "dataset-recorrigido")


class NavigationTests(unittest.TestCase):
    def test_nas_pontas_a_navegacao_fica_onde_esta(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama(), _diagrama(), _diagrama()], binding=EditorBinding.NONE)

        self.assertEqual(model.step(-1), 0)
        self.assertEqual(model.step(+1), 1)
        self.assertEqual(model.step(+1), 2)
        self.assertEqual(model.step(+1), 2)

    def test_indice_fora_da_faixa_e_limitado_e_nao_estoura(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama(), _diagrama()], binding=EditorBinding.NONE)
        self.assertEqual(model.select(99), 1)
        self.assertEqual(model.select(-5), 0)

    def test_editor_vazio_responde_sem_estourar(self) -> None:
        model = DiagramEditorModel()
        self.assertEqual(model.clamped_index(), 0)
        self.assertEqual(model.fen_at(), "")
        self.assertEqual(model.side_at(), "w")
        self.assertIsNone(model.current)
        self.assertFalse(model.apply_placement(PLACEMENT))
        self.assertFalse(model.set_side("b"))


class EditTests(unittest.TestCase):
    def test_arrastar_uma_peca_marca_edicao_a_mao(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.NONE)
        self.assertFalse(model.has_hand_edits)

        model.apply_placement(OUTRO)
        self.assertTrue(model.has_hand_edits)
        self.assertTrue(model.items[0].edited_by_hand)

    def test_a_leitura_original_sobrevive_a_edicao(self) -> None:
        """`fen_edits[i]` é o que se edita agora; `items[i].placement` é o que o modelo leu."""
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.NONE)
        model.apply_placement(OUTRO)

        self.assertEqual(model.fen_at(0), OUTRO)
        self.assertEqual(model.items[0].placement, PLACEMENT)

    def test_trocar_o_lado_a_jogar_chega_ao_diagrama(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.NONE)
        self.assertTrue(model.set_side("b"))
        self.assertEqual(model.side_at(0), "b")
        self.assertEqual(model.items[0].side_to_move, "b")


class AdoptTests(unittest.TestCase):
    def test_restaurar_do_cache_mantem_as_listas_por_referencia(self) -> None:
        """Copiá-las aqui desfaria a correção feita antes de trocar de página."""
        model = DiagramEditorModel()
        itens = [_diagrama()]
        fens = [OUTRO]
        sides = ["b"]
        model.adopt(itens, fens, sides, page_key=("livro.pdf", 80))

        self.assertIs(model.fen_edits, fens)
        self.assertIs(model.side_edits, sides)
        self.assertIs(model.binding, EditorBinding.PAGE)

    def test_trocar_de_pdf_solta_a_pagina_sem_apagar_o_editor(self) -> None:
        model = DiagramEditorModel()
        model.load([_diagrama()], binding=EditorBinding.PAGE, page_key=("livro.pdf", 80))
        model.unbind_page()

        self.assertIsNone(model.page_key)
        self.assertIs(model.binding, EditorBinding.NONE)
        self.assertEqual(model.count, 1, "o conteúdo continua editável, só não pertence a página nenhuma")


class NoTkinterTests(unittest.TestCase):
    def test_o_modelo_nao_importa_tkinter(self) -> None:
        """O critério de aceite literal da S-49, e o que torna estes testes possíveis.

        A varredura é sobre a **árvore de importação** e não sobre o texto: o docstring do
        módulo cita `import tkinter` para dizer que ele não existe ali, e um `assertNotIn`
        sobre o texto reprovaria a própria explicação.
        """
        import ast
        from pathlib import Path

        from chess_diagram_ocr.ui import editor_model

        arvore = ast.parse(Path(editor_model.__file__).read_text(encoding="utf-8"))
        importados: set[str] = set()
        for node in ast.walk(arvore):
            if isinstance(node, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                importados.add(node.module.split(".")[0])

        self.assertNotIn("tkinter", importados)


if __name__ == "__main__":
    unittest.main()


class SecondOpinionTests(unittest.TestCase):
    """O segundo leitor local (S-66): adota a posição e guarda o que ficou em disputa."""

    def _carregado(self) -> DiagramEditorModel:
        model = DiagramEditorModel()
        model.load([_diagrama(), _diagrama()], binding=EditorBinding.NONE)
        return model

    def test_adota_a_leitura_e_marca_as_casas(self) -> None:
        model = self._carregado()
        parecer = model.mark_second_opinion(0, OUTRO, reader="leitor")

        self.assertIsNotNone(parecer)
        self.assertEqual(model.fen_edits[0], OUTRO)
        self.assertEqual(model.disputed_squares(0), parecer.disputed)
        self.assertNotEqual(model.disputed_squares(0), ())

    def test_a_leitura_do_modelo_principal_e_preservada(self) -> None:
        """`items[i].placement` é o que o modelo local leu, e a S-66 não mexe nisso."""
        model = self._carregado()
        model.mark_second_opinion(0, OUTRO, reader="leitor")
        self.assertEqual(model.items[0].placement, PLACEMENT)

    def test_marca_e_por_diagrama(self) -> None:
        model = self._carregado()
        model.mark_second_opinion(1, OUTRO, reader="leitor")
        self.assertEqual(model.disputed_squares(0), ())
        self.assertNotEqual(model.disputed_squares(1), ())

    def test_indice_fora_do_intervalo_nao_grava_nada(self) -> None:
        """A leitura roda em thread: a página pode ter mudado no meio do caminho."""
        model = self._carregado()
        self.assertIsNone(model.mark_second_opinion(9, OUTRO, reader="leitor"))
        self.assertEqual(model.second_opinion, {})

    def test_procedencia_e_segunda_opiniao(self) -> None:
        model = self._carregado()
        model.mark_second_opinion(0, OUTRO, reader="leitor")
        self.assertEqual(model.label_route(0, OUTRO), "segunda-opiniao")

    def test_diagrama_nao_lido_mantem_a_rota_antiga(self) -> None:
        model = self._carregado()
        model.mark_second_opinion(0, OUTRO, reader="leitor")
        self.assertEqual(model.label_route(1, PLACEMENT), "ocr-aceito")

    def test_trocar_de_pagina_apaga_as_marcas(self) -> None:
        """Os índices são por carregamento: herdá-los marcaria casa de outro diagrama."""
        model = self._carregado()
        model.mark_second_opinion(0, OUTRO, reader="leitor")
        model.load([_diagrama()], binding=EditorBinding.PAGE, page_key=("livro.pdf", 7))
        self.assertEqual(model.second_opinion, {})
        self.assertEqual(model.disputed_squares(0), ())

    def test_leitura_identica_marca_zero_casas_e_ainda_registra_a_rota(self) -> None:
        model = self._carregado()
        parecer = model.mark_second_opinion(0, PLACEMENT, reader="leitor")
        self.assertEqual(parecer.disputed, ())
        self.assertEqual(model.label_route(0, PLACEMENT), "segunda-opiniao")


SEM_TKINTER = {
    "abas.py": "o rótulo de uma aba e a contagem dentro dele (S-162)",
    "atalhos.py": "a tabela de atalhos: tecla, comando e descrição, sem widget (S-161/S-165)",
    "board_edit.py": "as regras de edição do tabuleiro (S-49)",
    "board_model.py": "o estado do tabuleiro, sem widget",
    "busy.py": "o que se perde ao fechar a janela, decidido fora dela (S-60)",
    "editor_model.py": "o que 'salvar' significa, dado o vínculo (S-49)",
    "dispositivos.py": "em que dispositivo cada um dos dois modelos torch está (S-182)",
    "estilos.py": "papel de botão -> nome de estilo ttk (S-144)",
    "formato.py": "número e código do CSV como a tela os escreve (S-169)",
    "field_draft.py": "o rascunho do conjunto de campo (S-41)",
    "gallery_model.py": "a navegação e as anotações da Galeria (S-67)",
    "geometria.py": "o piso da janela, somado e não escolhido a olho (S-150)",
    "legality.py": "a explicação de por que a posição é ilegal",
    "page_overlay.py": "a geometria das caixas sobre a página",
    "page_results.py": "os resultados de uma página, sem tela",
    "state.py": "o estado da aplicação em disco",
    "strings.py": "o vocabulário da interface (S-04)",
    "tipografia.py": "a escala de fontes, derivada do sistema e sem widget (S-149)",
    "tokens.py": "a paleta e o contraste, sem widget (S-145/S-146)",
    "viewport.py": "o zoom e a rolagem, como aritmética",
}
"""Os módulos de `ui/` que **não** podem importar `tkinter`, e o que cada um é (S-137).

A separação que sustenta toda a testabilidade da interface estava declarada em seis docstrings
e verificada em **quatro** módulos. A lista é o teste: um módulo novo sem Tk que não esteja
aqui não é vigiado, e um daqui que passe a importar `tkinter` falha a suíte.

**Importar `tkinter` não é proibido em `ui/`** -- a maioria dos painéis o faz, e é o que eles
são. O que a lista fixa é o conjunto que decidiu **não** fazê-lo, porque é dele que sai a
possibilidade de testar decisão de interface sem abrir janela."""


class SemTkinterTests(unittest.TestCase):
    """A varredura é sobre a **árvore de importação** e não sobre o texto.

    Vários destes módulos citam `import tkinter` no docstring para dizer que ele não existe
    ali, e um `assertNotIn` sobre o texto reprovaria a própria explicação -- é a razão que o
    `NoTkinterTests` acima já registrava para um módulo só.
    """

    def _importados(self, caminho: Path) -> set[str]:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        nomes: set[str] = set()
        for node in ast.walk(arvore):
            if isinstance(node, ast.Import):
                nomes.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                nomes.add(node.module.split(".")[0])
        return nomes

    def test_os_doze_continuam_sem_tkinter(self) -> None:
        raiz = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "ui"
        culpados = []
        for nome, oque in sorted(SEM_TKINTER.items()):
            caminho = raiz / nome
            if not caminho.exists():
                culpados.append(f"{nome}: declarado sem Tk ({oque}) e não existe")
                continue
            if {"tkinter", "PIL"} & self._importados(caminho):
                culpados.append(f"{nome}: passou a importar tkinter/PIL")

        self.assertEqual(culpados, [], "\n".join(["Módulos que deviam ser testáveis sem janela:", *culpados]))

    def test_a_lista_cobre_todo_modulo_de_ui_que_hoje_dispensa_tkinter(self) -> None:
        """O outro sentido: um módulo novo sem Tk que não entre na lista não é vigiado, e a
        separação volta a ser convenção -- que é o estado que este item conserta."""
        raiz = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "ui"
        fora = [
            caminho.name
            for caminho in sorted(raiz.glob("*.py"))
            if caminho.name not in SEM_TKINTER
            and caminho.name != "__init__.py"
            and not {"tkinter", "PIL"} & self._importados(caminho)
        ]
        self.assertEqual(fora, [], "Módulo de `ui/` sem Tk e fora de SEM_TKINTER.")
