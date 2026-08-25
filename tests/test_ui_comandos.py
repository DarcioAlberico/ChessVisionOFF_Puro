"""O catálogo de comandos: um comando declarado uma vez, e quem o consome (S-219).

Os comandos da janela estavam declarados em três lugares que não se conheciam -- o menu, a tabela
de atalhos e o botão montado à mão --, e nenhum era a lista completa. O sintoma não é duplicação:
é **divergência já consumada**. O mesmo `ler_pagina` se chamava "Ler esta página" no menu e "OCR
todos diagramas" no botão, e nada no programa comparava os dois textos.

Estes testes são a comparação que faltava, e quase todos rodam sem abrir janela -- que é o que
`ui/comandos.py` compra ao não importar `tkinter`.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from chess_diagram_ocr.ui import atalhos, comandos, estilos, menu  # noqa: E402

PDF_PANEL = RAIZ / "src" / "chess_diagram_ocr" / "ui" / "pdf_panel.py"
TEXTO_PANEL = RAIZ / "src" / "chess_diagram_ocr" / "ui" / "texto_panel.py"
JANELA = RAIZ / "app_tkinter.py"

COMANDOS_DO_EDITOR: tuple[str, ...] = (
    "abrir_texto",
    "achar",
    "cor_do_texto",
    "estilo_legenda",
    "estilo_notacao",
    "estilo_prosa",
    "estilo_titulo",
    "exportar_txt",
    "folha_da_pagina_aberta",
    "inserir_avaliacao",
    "inserir_figurina",
    "italico",
    "ler_folha",
    "limpar_cor",
    "limpar_formato",
    "modo_bloco",
    "negrito",
    "paleta_de_glifos",
    "realce",
    "salvar_texto",
    "salvar_texto_como",
    "sublinhado",
    "substituir",
    "substituir_todos",
)
"""Os comandos que a Fase 37 acrescentou (S-240).

Escritos aqui e não derivados de propósito: derivar do próprio catálogo faria o teste concordar
com qualquer coisa que ele contivesse, inclusive com um comando que sumisse."""

WIDGETS_DE_COMANDO = ("Button", "Checkbutton")
"""Os dois que carregam comando. `Label`, `Spinbox` e `Combobox` mostram ou colhem estado."""


def _rotulos_literais(no: ast.AST) -> list[str]:
    """Os `text=` escritos à mão em `ttk.Button`/`ttk.Checkbutton` dentro daquele nó.

    Aceita `ast.Constant` e `ast.JoinedStr`: o botão de exportar era um f-string
    (`f"Exportar PDF {strings.SETA} PGN"`), e uma varredura que só olhasse constante o daria
    por limpo -- que é o modo como uma guarda passa em verde sobre o caso que ela existe para
    pegar.
    """
    achados: list[str] = []
    for filho in ast.walk(no):
        if not isinstance(filho, ast.Call) or not isinstance(filho.func, ast.Attribute):
            continue
        if filho.func.attr not in WIDGETS_DE_COMANDO:
            continue
        for chave in filho.keywords:
            if chave.arg == "text" and isinstance(chave.value, (ast.Constant, ast.JoinedStr)):
                escrito = chave.value.value if isinstance(chave.value, ast.Constant) else "<f-string>"
                achados.append(f"linha {filho.lineno}: {escrito!r}")
    return achados


def _rotulos_reconfigurados(no: ast.AST) -> list[str]:
    """Os `text=` escritos à mão em `self.btn_*.configure(...)` dentro daquele nó.

    **O buraco que a S-222 encontrou.** A varredura acima olha o construtor, e um botão que
    alterna troca o próprio texto depois: o `selecionar_area` virava "Cancelar seleção" por
    `configure`, e dois literais passavam por limpos. Quem alterna declara os dois rótulos no
    catálogo, em `rotulo_alternado`.

    O crivo é o prefixo `btn_`, que é a convenção deste painel: `lbl_pdf` e `lbl_zoom` também
    recebem `config(text=...)`, e o texto deles é **dado** -- o nome do livro, a porcentagem do
    zoom --, não rótulo de comando.
    """
    achados: list[str] = []
    for filho in ast.walk(no):
        if not isinstance(filho, ast.Call) or not isinstance(filho.func, ast.Attribute):
            continue
        if filho.func.attr not in ("configure", "config"):
            continue
        alvo = filho.func.value
        if not isinstance(alvo, ast.Attribute) or not alvo.attr.startswith("btn_"):
            continue
        for chave in filho.keywords:
            if chave.arg == "text" and isinstance(chave.value, (ast.Constant, ast.JoinedStr)):
                escrito = chave.value.value if isinstance(chave.value, ast.Constant) else "<f-string>"
                achados.append(f"linha {filho.lineno}: {alvo.attr}.configure(text={escrito!r})")
    return achados


def _funcao(arvore: ast.AST, nome: str) -> ast.FunctionDef:
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return no
    raise AssertionError(f"função {nome} não existe mais em app_tkinter.py")


class CoberturaDoCatalogoTests(unittest.TestCase):
    """Os quatro lugares que declaravam comando estão todos cobertos pelo registro."""

    def test_todo_item_de_menu_esta_no_catalogo(self) -> None:
        """O sentido que faltava na trava do menu: item declarado que ninguém registrou."""
        self.assertEqual([], menu.acoes_fora_do_catalogo())

    def test_todo_atalho_esta_no_catalogo(self) -> None:
        """Uma tecla cujo comando o catálogo não conhece é uma pele sem onde desenhá-lo."""
        fora = comandos.acoes_fora_do_catalogo(atalho.acao for atalho in atalhos.ATALHOS)
        self.assertEqual([], fora)

    def test_o_menu_mostra_o_rotulo_do_catalogo(self) -> None:
        """`MENUS` deixou de repetir o texto: ele agora **sai** daqui, e o menu só o exibe."""
        for declarado in menu.MENUS:
            for item in declarado.itens:
                if item.tipo == menu.SEPARADOR:
                    self.assertEqual("", item.rotulo, "separador não tem rótulo")
                    continue
                with self.subTest(acao=item.acao):
                    self.assertEqual(comandos.rotulo(item.acao), item.rotulo)

    def test_nenhum_rotulo_de_botao_escrito_a_mao(self) -> None:
        """O critério de aceite do item, nos dois lugares que a S-219 nomeia.

        `ui/pdf_panel.py` inteiro -- as duas barras são os únicos botões dele -- e a linha do
        conjunto de campo, que mora em `_build_field_row` porque é a janela que a monta.
        """
        arvore_do_painel = ast.parse(PDF_PANEL.read_text(encoding="utf-8"))
        painel = _rotulos_literais(arvore_do_painel)
        self.assertEqual([], painel, "rótulo de botão escrito à mão em ui/pdf_panel.py")

        # E o texto trocado depois, que é por onde o `selecionar_area` escapava (S-222).
        alternados = _rotulos_reconfigurados(arvore_do_painel)
        self.assertEqual([], alternados, "botão que troca o próprio rótulo fora do catálogo")

        janela = ast.parse(JANELA.read_text(encoding="utf-8"))
        linha_de_campo = _rotulos_literais(_funcao(janela, "_build_field_row"))
        self.assertEqual([], linha_de_campo, "rótulo de botão escrito à mão na linha de campo")

    def test_os_rotulos_que_divergem_do_menu_estao_registrados(self) -> None:
        """**O defeito que este item fecha, virado teste.**

        O botão e o menu dizem coisas diferentes sobre o mesmo comando em catorze casos. Nenhum
        deles é acidente -- "OCR todos diagramas" é o texto que a janela mostra hoje, e trocá-lo
        seria mudar a pele clássica, que a regra 1 da SPEC_APARENCIA proíbe. O que era acidente
        era **ninguém saber quais eram**. Agora um décimo-quinto caso não entra em silêncio.

        Os três da S-229 nascem já divergentes, e é a divergência certa: o menu diz "Desfazer a
        última mudança no tabuleiro" porque é onde cabe dizê-lo, e o botão de fita diz "Desfazer"
        porque um rótulo de nove palavras embaixo de um ícone é uma fita de duas linhas.
        """
        divergem = {registro.acao for registro in comandos.CATALOGO if registro.rotulo_curto}
        self.assertEqual(
            {
                # Os oito da Fase 37 nascem divergentes, e é a divergência certa: o menu diz
                # "Exportar o texto para .txt" porque é onde cabe dizê-lo, e o botão da aba diz
                # "Salvar .txt" porque é o rótulo que a janela mostra hoje -- trocá-lo mudaria a
                # aba sem pedido, que é o achado 1 do ROADMAP_APARENCIA.
                "abrir_texto",
                "estilo_legenda",
                "estilo_notacao",
                "estilo_prosa",
                "estilo_titulo",
                "exportar_txt",
                "folha_da_pagina_aberta",
                "ler_folha",
                "limpar_cor",
                "limpar_formato",
                "modo_bloco",
                "paleta_de_glifos",
                "salvar_texto",
                "abrir_pdf",
                "cancelar_exportacao",
                "desfazer",
                "exportar_pgn",
                "limpar_tabuleiro",
                "ler_melhor",
                "ler_pagina",
                "marcar_diagramas",
                "refazer",
                "roda_vira_pagina",
                "selecionar_area",
                "tirar_caixa",
                "zoom_mais",
                "zoom_menos",
            },
            divergem,
        )


class DisciplinaDoRegistroTests(unittest.TestCase):
    """As regras que o catálogo torna afirmáveis sem montar um único widget."""

    def test_um_primario_por_grupo(self) -> None:
        """A regra de `ui/estilos.py:31-36` -- *uma ênfase por barra, nunca duas* -- verificável.

        Enquanto a ênfase morava no `style=` de cada botão, contá-la exigia abrir a janela e ler
        os widgets, e por isso ninguém a contava.
        """
        for grupo, primarios in comandos.primarios_por_grupo().items():
            with self.subTest(grupo=grupo):
                self.assertLessEqual(len(primarios), 1, f"duas ênfases no grupo {grupo}: {primarios}")

    def test_papel_desconhecido_levanta(self) -> None:
        """Como `estilos.estilo_de_botao`, e pela mesma razão: papel errado desenharia cinza."""
        with self.assertRaises(KeyError):
            comandos.Comando("inventado", "Inventado", comandos.ARQUIVO, "ROXO")

    def test_grupo_desconhecido_levanta(self) -> None:
        """O conjunto dos seis é fechado: um sétimo grupo é uma fita com um cabeçalho órfão."""
        with self.assertRaises(KeyError):
            comandos.Comando("inventado", "Inventado", "FERRAMENTAS", estilos.NEUTRO)

    def test_o_grupo_de_todo_comando_e_um_dos_seis(self) -> None:
        for registro in comandos.CATALOGO:
            with self.subTest(acao=registro.acao):
                self.assertIn(registro.grupo, comandos.GRUPOS)
                self.assertIn(registro.papel, estilos.PAPEIS_DE_BOTAO)
                self.assertTrue(registro.rotulo.strip(), "comando sem rótulo")

    def test_comando_desconhecido_levanta(self) -> None:
        """Nome escrito errado levanta em vez de virar botão sem texto (`tokens.cor`)."""
        with self.assertRaises(KeyError):
            comandos.comando("ler_pagina_de_novo")

    def test_os_grupos_cobrem_o_catalogo_inteiro(self) -> None:
        """`do_grupo` percorrido pelos seis devolve todo o catálogo, sem sobra e sem repetição."""
        reunidos = [registro.acao for grupo in comandos.GRUPOS for registro in comandos.do_grupo(grupo)]
        self.assertEqual(sorted(reunidos), sorted(registro.acao for registro in comandos.CATALOGO))

    def test_todo_grupo_tem_rotulo_legivel(self) -> None:
        """`"VISUALIZACAO"` não é texto de interface, e a fita da S-227 põe o grupo num cabeçalho."""
        for grupo in comandos.GRUPOS:
            with self.subTest(grupo=grupo):
                self.assertTrue(comandos.rotulo_do_grupo(grupo).strip())

    def test_o_catalogo_nao_importa_tkinter(self) -> None:
        """A mesma varredura da S-145 sobre `ui/tokens.py`, e pelo mesmo motivo: o que decide
        precisa ser afirmável sem janela, e é isso que faz cada teste acima caber num
        `assertEqual`."""
        arvore = ast.parse(Path(comandos.__file__).read_text(encoding="utf-8"))
        importados: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module.split(".")[0])
        self.assertNotIn("tkinter", importados)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ComandosDoEditorTests(unittest.TestCase):
    """A aba Texto entra no catálogo, ou as três peles não a verão (S-240)."""

    def test_os_comandos_do_editor_estao_no_catalogo(self) -> None:
        self.assertEqual([], comandos.acoes_fora_do_catalogo(COMANDOS_DO_EDITOR))

    def test_a_aba_texto_nao_escreve_rotulo_a_mao(self) -> None:
        """A varredura da S-219 passa a cobrir `ui/texto_panel.py`, que ela não cobria.

        Com os vinte e poucos comandos desta spec, o rótulo escrito à mão é a S-161 outra vez --
        *"o que não era botão não existia"* --, agora com três peles para divergir.
        """
        arvore = ast.parse(TEXTO_PANEL.read_text(encoding="utf-8"))
        self.assertEqual([], _rotulos_literais(arvore), "rótulo escrito à mão em ui/texto_panel.py")
        self.assertEqual([], _rotulos_reconfigurados(arvore))

    def test_edicao_continua_com_um_primario(self) -> None:
        """`EDICAO` já tem o seu -- `salvar`, a posição do tabuleiro --, e nenhum comando do editor
        pede ênfase: duas ações de salvar em grupos vizinhos, as duas em azul, é o mesmo que
        nenhuma (`ui/estilos.py`)."""
        self.assertEqual(comandos.primarios_por_grupo()[comandos.EDICAO], ["salvar"])
        self.assertEqual(comandos.primarios_por_grupo()[comandos.ARQUIVO], [])

    def test_desfazer_e_refazer_aparecem_uma_vez(self) -> None:
        """A S-229 os cria para o tabuleiro e a S-243 os aponta para o editor conforme o foco.
        Dois pares com o mesmo nome em português seria a divergência que o catálogo impede."""
        acoes = [registro.acao for registro in comandos.CATALOGO]
        self.assertEqual(acoes.count("desfazer"), 1)
        self.assertEqual(acoes.count("refazer"), 1)

    def test_todo_comando_novo_tem_icone_ou_o_declara_vazio(self) -> None:
        """`icone=""` é declaração e não esquecimento: a fita desenha o cromo da **janela**, e
        estes moram na barra da própria aba e no menu Texto."""
        for acao in COMANDOS_DO_EDITOR:
            with self.subTest(acao=acao):
                self.assertEqual(comandos.comando(acao).icone, "")

    def test_todo_comando_do_editor_alcanca_o_menu(self) -> None:
        """A regra 2 da SPEC_APARENCIA: o que a pele esconde, o menu alcança."""
        declaradas = set(menu.acoes_declaradas())
        fora = sorted(acao for acao in COMANDOS_DO_EDITOR if acao not in declaradas)
        self.assertEqual([], fora)

    def test_o_rotulo_do_botao_da_aba_nao_mudou(self) -> None:
        """Nenhum rótulo muda em relação ao de hoje para os controles que já existiam (S-240).

        É o achado 1 do ROADMAP_APARENCIA: as propostas são visuais, não são propostas de texto.
        """
        self.assertEqual(comandos.rotulo_de_botao("ler_folha"), "Ler folha")
        self.assertEqual(comandos.rotulo_de_botao("folha_da_pagina_aberta"), "Da página aberta")
        self.assertEqual(comandos.rotulo_de_botao("modo_bloco"), "Modo bloco (lento)")
        self.assertEqual(comandos.rotulo_de_botao("exportar_txt"), "Salvar .txt")
        self.assertEqual(comandos.rotulo_de_botao("salvar_texto"), "Salvar")
        self.assertEqual(comandos.rotulo_de_botao("abrir_texto"), "Abrir…")


class RotuloAlternadoTests(unittest.TestCase):
    """O texto de "ligado", para os comandos que alternam (S-222)."""

    def test_so_alterna_quem_precisa(self) -> None:
        """Um por enquanto, e é o único botão da janela que troca o próprio texto."""
        alternam = {registro.acao for registro in comandos.CATALOGO if registro.rotulo_alternado}
        self.assertEqual({"selecionar_area"}, alternam)

    def test_quem_nao_alterna_responde_o_proprio_rotulo(self) -> None:
        """`alternado` devolve o texto normal em vez de vazio: quem consome não precisa saber
        se aquele comando alterna, e um `""` chegaria ao botão como botão sem rótulo."""
        for registro in comandos.CATALOGO:
            with self.subTest(acao=registro.acao):
                self.assertTrue(comandos.rotulo_alternado(registro.acao).strip())
                if not registro.rotulo_alternado:
                    self.assertEqual(registro.no_botao, registro.alternado)
