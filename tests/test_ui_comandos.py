"""O catálogo de comandos: um comando declarado uma vez, e quem o consome (S-324).

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

PDF_PANEL = RAIZ / "src" / "chess_diagram_ocr" / "ui" / "barra_do_pdf.py"
"""Onde os controles do painel do PDF são **declarados** desde a S-528. Era
`qt/painel_do_pdf.py`, que os montava à mão."""
TEXTO_PANEL = RAIZ / "src" / "chess_diagram_ocr" / "qt" / "painel_de_texto.py"
JANELA = RAIZ / "src" / "chess_diagram_ocr" / "qt" / "janela.py"
CAMPO = RAIZ / "src" / "chess_diagram_ocr" / "qt" / "campo.py"

COMANDOS_DO_EDITOR: tuple[str, ...] = (
    "abrir_texto",
    "achar",
    "afastar_texto",
    "alinhar_centro",
    "alinhar_direita",
    "alinhar_esquerda",
    "aproximar_texto",
    "aumentar_corpo",
    "capitular",
    "colar",
    "copiar",
    "cor_do_texto",
    "corpo_normal",
    "diminuir_corpo",
    "estilo_legenda",
    "estilo_notacao",
    "estilo_prosa",
    "estilo_titulo",
    "exportar_html",
    "exportar_md",
    "exportar_pdf_pesquisavel",
    "exportar_rtf",
    "exportar_txt",
    "folha_da_pagina_aberta",
    "inserir_avaliacao",
    "inserir_figurina",
    "italico",
    "justificar",
    "ler_folha",
    "limpar_cor",
    "limpar_formato",
    "limpar_marcas_do_lexico",
    "maiusculas",
    "marcar_fora_do_lexico",
    "minusculas",
    "modo_bloco",
    "negrito",
    "paleta_de_glifos",
    "quebrar_linha",
    "realce",
    "recortar",
    "salvar_texto",
    "salvar_texto_como",
    "selecionar_tudo",
    "sublinhado",
    "substituir",
    "substituir_todos",
    "tachado",
    "zoom_do_texto_normal",
)
"""Os comandos do editor de texto -- Fase 37 (S-240), Fase 41 (S-259 a S-262), Fase 42 (S-263 a
S-266).

Escritos aqui e não derivados de propósito: derivar do próprio catálogo faria o teste concordar
com qualquer coisa que ele contivesse, inclusive com um comando que sumisse.

**Os dois agrupadores da barra não estão aqui, e é a mesma decisão de "Alinhar" e "Caixa" não serem
comandos:** eles abrem uma lista, quem age é o item dela, e o rótulo dos dois mora em
`ui/strings.py`. Ver o comentário do bloco da Fase 41 em `ui/comandos.py`."""

WIDGETS_DE_COMANDO = ("QPushButton", "QCheckBox", "QToolButton")
"""Os três que carregam comando. `QLabel`, `QSpinBox` e `QComboBox` mostram ou colhem estado.

Eram `Button` e `Checkbutton` do `ttk` até o corte do Tk (S-506); o `QToolButton` entrou junto
porque é o botão de barra do Qt, e um comando posto nele escapava da varredura."""


def _rotulos_literais(no: ast.AST) -> list[str]:
    """Os rótulos escritos à mão num botão dentro daquele nó.

    Aceita `ast.Constant` e `ast.JoinedStr`: o botão de exportar era um f-string
    (`f"Exportar PDF {strings.SETA} PGN"`), e uma varredura que só olhasse constante o daria
    por limpo -- que é o modo como uma guarda passa em verde sobre o caso que ela existe para
    pegar.

    **A forma mudou no corte do Tk (S-506), e a guarda quase ficou vácua.** Ela procurava o
    `text=` de um `ttk.Button`; no Qt o rótulo é o **primeiro posicional** de um `QPushButton` ou
    `QCheckBox`. Deixá-la como estava faria ela passar em verde sobre um pacote inteiro sem achar
    um único botão -- que é exatamente o defeito que ela nomeia no docstring acima.
    """
    achados: list[str] = []
    for filho in ast.walk(no):
        if not isinstance(filho, ast.Call):
            continue
        nome = filho.func.id if isinstance(filho.func, ast.Name) else getattr(filho.func, "attr", "")
        if nome not in WIDGETS_DE_COMANDO:
            continue
        primeiro = filho.args[0] if filho.args else None
        if isinstance(primeiro, (ast.Constant, ast.JoinedStr)):
            escrito = primeiro.value if isinstance(primeiro, ast.Constant) else "<f-string>"
            if isinstance(escrito, str) or escrito == "<f-string>":
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


def _acoes_desenhadas(no: ast.AST) -> set[str]:
    """As ações do catálogo que a tabela de uma barra em fila declara, por `ast`.

    **O padrão mudou com a S-528, e traduzi-lo é obrigação.** Enquanto o painel do PDF montava os
    controles à mão, as ações apareciam em `_botao(barra, "abrir_pdf", ...)` e em
    `comandos.rotulo_de_botao("marcar_diagramas")` dentro de `qt/painel_do_pdf.py`; agora elas são
    linhas de `ui/barra_do_pdf.ACOES`, e o painel não escreve nome de comando nenhum. Uma guarda
    ancorada no arquivo antigo passaria em **verde sobre lista vazia** -- que é exatamente o que a
    S-506 mediu vinte vezes no corte do Tk, e o que esta função existe para não fazer.

    A forma agora é `Acao("abrir_pdf", GRUPO, "icone", ...)`: o primeiro posicional de qualquer
    chamada a `Acao`. **Só constante conta**, pela mesma razão de antes.
    """
    achadas: set[str] = set()
    for filho in ast.walk(no):
        if not isinstance(filho, ast.Call):
            continue
        nome = getattr(filho.func, "attr", "") or getattr(filho.func, "id", "")
        alvo: ast.expr | None = None
        if nome == "Acao" and filho.args:
            alvo = filho.args[0]
        if isinstance(alvo, ast.Constant) and isinstance(alvo.value, str):
            achadas.add(alvo.value)
    return achadas


def _funcao(arvore: ast.AST, nome: str) -> ast.FunctionDef:
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return no
    raise AssertionError(f"função {nome} não existe mais em qt/janela.py")


class CoberturaDoCatalogoTests(unittest.TestCase):
    """Os quatro lugares que declaravam comando estão todos cobertos pelo registro.

    **Os dois sentidos.** Daqui para o catálogo -- item de menu ou tecla que ninguém registrou --
    e do catálogo para cá: comando registrado que ninguém alcança. O segundo sentido ficou sem
    guarda no corte do Tk, e é o que `test_todo_comando_do_catalogo_alcanca_alguem` repõe.
    """

    def test_todo_item_de_menu_esta_no_catalogo(self) -> None:
        """O sentido que faltava na trava do menu: item declarado que ninguém registrou."""
        self.assertEqual([], menu.acoes_fora_do_catalogo())

    def test_todo_atalho_esta_no_catalogo(self) -> None:
        """Uma tecla cujo comando o catálogo não conhece é uma pele sem onde desenhá-lo."""
        fora = comandos.acoes_fora_do_catalogo(atalho.acao for atalho in atalhos.ATALHOS)
        self.assertEqual([], fora)

    def test_todo_comando_do_catalogo_alcanca_alguem(self) -> None:
        """**O sentido que o corte do Tk levou junto** (S-506).

        `ui/alcance.perdidos()` respondia "que ação do catálogo ninguém alcança", e saiu no mesmo
        commit que os três cromos do Tk sobre os quais ela perguntava. A outra guarda -- comparar
        as duas janelas ação a ação -- também saiu, e o buraco entre as duas tinha exatamente o
        tamanho de `anotar_pagina`, `anotar_sem_diagrama` e `tirar_do_campo`: elas eram **botões**
        e não itens de menu, então a comparação passava em verde sem elas. Entre as duas estava o
        único caminho que faz o `data/field_set.jsonl` crescer.

        A conta é fechada aqui: todo comando do catálogo alcança o menu, **ou** está numa das duas
        listas que declaram por que ele não alcança. Uma terceira exceção não entra em silêncio --
        ela chega como um nome nesta lista.
        """
        alcancam = set(menu.acoes_declaradas())
        declarados = set(comandos.NA_JANELA_DE_BUSCA) | set(comandos.NA_LINHA_DE_CAMPO)
        perdidos = sorted(
            registro.acao
            for registro in comandos.CATALOGO
            if registro.acao not in alcancam and registro.acao not in declarados
        )
        self.assertEqual(
            [], perdidos, "ação do catálogo que nem o menu alcança nem lista nenhuma declara"
        )

    def test_a_conta_do_catalogo_acusa_uma_acao_sem_dono(self) -> None:
        """O **controle** da guarda de cima, e ele prova o padrão e não um infrator.

        Uma guarda que varre por ausência fica verde quando o que ela varria some: foi o que
        aconteceu com as ~20 varreduras de sintaxe do toolkit no corte -- a lista de infratores
        virou `[]` e o teste passou. Este caso **constrói** a ação perdida em vez de esperar que
        alguma exista, então ele continua provando alguma coisa no dia em que o catálogo estiver
        inteiramente coberto (que é hoje).
        """
        alcancam = set(menu.acoes_declaradas())
        declarados = set(comandos.NA_JANELA_DE_BUSCA) | set(comandos.NA_LINHA_DE_CAMPO)
        orfa = "acao_que_nenhuma_pele_alcanca"
        self.assertNotIn(orfa, alcancam | declarados, "o nome do controle virou comando de verdade")

        candidatas = [registro.acao for registro in comandos.CATALOGO] + [orfa]
        perdidos = sorted(
            acao for acao in candidatas if acao not in alcancam and acao not in declarados
        )
        self.assertEqual([orfa], perdidos)

    def test_as_duas_excecoes_sao_do_catalogo_e_estao_fora_do_menu(self) -> None:
        """As listas de exceção envelhecem em dois sentidos, e os dois são silenciosos.

        Uma ação declarada como exceção que **ganhou** item de menu é uma exceção vencida: ela
        continua dizendo "este comando não alcança o menu" sobre um comando que alcança. E um nome
        que saiu do catálogo deixa a lista apontando para comando nenhum. Nos dois casos a guarda
        de cima segue verde, porque ela só pergunta pelo que falta.
        """
        alcancam = set(menu.acoes_declaradas())
        do_catalogo = {registro.acao for registro in comandos.CATALOGO}
        for nome, lista in (
            ("NA_JANELA_DE_BUSCA", comandos.NA_JANELA_DE_BUSCA),
            ("NA_LINHA_DE_CAMPO", comandos.NA_LINHA_DE_CAMPO),
        ):
            self.assertTrue(lista, f"{nome} vazia: a exceção deixou de existir")
            for acao in lista:
                with self.subTest(lista=nome, acao=acao):
                    self.assertIn(acao, do_catalogo, "exceção que não é comando do catálogo")
                    self.assertNotIn(acao, alcancam, "exceção vencida: o comando alcança o menu")

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
        """O critério de aceite do item, nos dois lugares que a S-324 nomeia.

        `qt/painel_do_pdf.py` inteiro -- as duas barras são os únicos botões dele -- e a linha do
        conjunto de campo, que no corte do Tk (S-506) saiu da janela e virou `qt/campo.py`: ela
        afirma coisas sobre a página exibida, e por isso mora ao lado dela.
        """
        arvore_do_painel = ast.parse(PDF_PANEL.read_text(encoding="utf-8"))
        painel = _rotulos_literais(arvore_do_painel)
        self.assertEqual([], painel, "rótulo de botão escrito à mão em qt/painel_do_pdf.py")

        # E o texto trocado depois, que é por onde o `selecionar_area` escapava (S-222).
        alternados = _rotulos_reconfigurados(arvore_do_painel)
        self.assertEqual([], alternados, "botão que troca o próprio rótulo fora do catálogo")

        campo = ast.parse(CAMPO.read_text(encoding="utf-8"))
        self.assertEqual(
            [], _rotulos_literais(campo), "rótulo de botão escrito à mão na linha de campo"
        )

    def test_a_declaracao_das_barras_bate_com_o_que_o_painel_desenha(self) -> None:
        """**Reposta no lugar da que saiu no corte do Tk** (S-233/S-506).

        `comandos.NAS_BARRAS_DO_PDF` é declarada em `ui/` para o inventário poder lê-la sem abrir
        janela, e o painel monta os controles à mão do outro lado. A distância entre os dois é
        onde a lista apodrece: ela ficou **sem leitor nenhum** do corte até aqui, e nesse intervalo
        divergiu em cinco nomes sem que nada acusasse.

        Quem a cobrava era `test_a_declaracao_das_barras_bate_com_o_que_o_painel_desenha` de
        `tests/test_ui_alcance.py`, que varria o `_montar_barras` de `ui/pdf_panel.py`. O padrão
        mudou duas vezes -- lá era `ttk.Button(text=...)`, depois o ajudante `_botao` de
        `qt/painel_do_pdf.py`, e desde a S-528 é a linha `Acao(...)` de `ui/barra_do_pdf.py` --, e
        é o padrão traduzido que esta guarda usa. Ver `_acoes_desenhadas`.
        """
        desenhadas = _acoes_desenhadas(ast.parse(PDF_PANEL.read_text(encoding="utf-8")))
        self.assertTrue(desenhadas, "a varredura não achou controle nenhum: o padrão mudou de novo")
        self.assertEqual(sorted(comandos.NAS_BARRAS_DO_PDF), sorted(desenhadas))

    def test_a_varredura_das_barras_acha_a_linha_da_tabela(self) -> None:
        """O **controle** da guarda de cima, e ele casa contra exemplos literais.

        Ancorá-lo na tabela de verdade o faria se apagar junto com o defeito: uma varredura que
        deixasse de reconhecer a linha acharia zero ação, a lista declarada teria de encolher para
        zero para o teste passar, e as duas ficariam de acordo sobre nada. O trecho abaixo é a
        forma que `ui/barra_do_pdf.py` usa, escrita à mão aqui -- com a chamada aninhada e o
        parâmetro `acao` que **não** conta, que são os dois casos em que a varredura erraria.
        """
        arvore = ast.parse(
            "ACOES = (\n"
            '    Acao("abrir_pdf", LIVRO, "abrir_pdf", prioridade=6, com_texto=True),\n'
            '    Acao("marcar_diagramas", VISTA, "marcar", principal=False, marcavel=True),\n'
            ")\n"
            "def acao(nome):\n"
            "    return Acao(nome, LIVRO, \"x\")\n"
        )
        self.assertEqual({"abrir_pdf", "marcar_diagramas"}, _acoes_desenhadas(arvore))

    def test_toda_acao_declarada_nas_barras_esta_no_catalogo(self) -> None:
        """Um nome escrito errado na lista faria o painel desenhar botão sem rótulo (`comando`
        levanta), e a guarda de cima o compararia contra o painel sem nunca perguntar se ele
        existe."""
        self.assertEqual([], comandos.acoes_fora_do_catalogo(comandos.NAS_BARRAS_DO_PDF))

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
                # Os da Fase 37 e os da Fase 41 nascem divergentes, e é a divergência certa: o menu diz
                # "Exportar o texto para .txt" porque é onde cabe dizê-lo, e o botão da aba diz
                # "Salvar .txt" porque é o rótulo que a janela mostra hoje -- trocá-lo mudaria a
                # aba sem pedido, que é o achado 1 do ROADMAP_APARENCIA.
                "abrir_texto",
                "afastar_texto",
                # A S-516: o menu diz "Dobrar todas as variantes" porque é onde cabe dizê-lo, e o
                # botão diz "Dobrar" porque ele fica numa fileira que a Fase 76 já vai apertar.
                "dobrar_variantes",
                "alinhar_centro",
                "alinhar_direita",
                "alinhar_esquerda",
                "aproximar_texto",
                "aumentar_corpo",
                "capitular",
                "colar",
                "copiar",
                "corpo_normal",
                "diminuir_corpo",
                "estilo_legenda",
                "estilo_notacao",
                "estilo_prosa",
                "estilo_titulo",
                "exportar_txt",
                "folha_da_pagina_aberta",
                "justificar",
                "ler_folha",
                "limpar_cor",
                "limpar_formato",
                "limpar_marcas_do_lexico",
                "maiusculas",
                "marcar_fora_do_lexico",
                "minusculas",
                "modo_bloco",
                "paleta_de_glifos",
                "quebrar_linha",
                "recortar",
                "salvar_texto",
                "selecionar_tudo",
                "zoom_do_texto_normal",
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
                # Os vinte e três da sala de estudo (S-280) nascem divergentes pela mesma razão: o
                # menu diz "Promover a variante a linha principal" porque é onde cabe dizê-lo, e o
                # botão diz "Principal" porque a barra da sala tem três linhas e vinte e quatro
                # comandos. Os quatro de navegação usam as setas de `ui/strings.py`, que são as
                # mesmas que a aba já mostrava antes de haver catálogo.
                "analisar_posicao",
                "analise_continua",
                # Os dois da Fase 82: o menu diz "Analisar a partida inteira com o motor…" e
                # "Opções do motor de análise…" porque é onde cabe dizê-lo, e a barra da sala tem
                # de caber num botão de 16 px com o rótulo na dica (S-536/S-537).
                "analisar_partida",
                "opcoes_do_motor",
                "apagar_continuacao",
                "apagar_variante",
                "copiar_fen",
                "estudo_aplicar_fen",
                "estudo_da_posicao_inicial",
                "estudo_do_diagrama",
                "fim_da_linha",
                "inicio_da_linha",
                "ir_para_a_pagina",
                "lance_anterior",
                "linha_do_livro",
                "mostrar_diagrama",
                "partidas_da_posicao",
                "promover_a_principal",
                "promover_variante",
                "proximo_lance",
                "rebaixar_variante",
                "salvar_estudo",
                "simbolo_do_lance",
                "trocar_vez",
                "variante_do_motor",
                # Os sete das Fases 49 e 50, pela mesma razão: o menu diz "Exportar o estudo para
                # Markdown…" e o botão diz ".md", porque a barra da sala tem quatro linhas.
                "abrir_pgn",
                "colar_estudo",
                "estudo_para_o_texto",
                "exportar_estudo_html",
                "exportar_estudo_md",
                "exportar_estudo_rtf",
                "modo_treino",
                # A S-527/S-532: o menu diz "Indexar a base de partidas por nome…" e o botão do
                # "Mais" da sala diz "Indexar base", pela mesma razão dos vinte e três acima.
                "indexar_base",
                # E a S-533: o menu diz por que campos se busca ("por jogador, evento, ano, Elo e
                # ECO…") porque é ali que a lista de campos cabe; o botão diz "Buscar partidas".
                "buscar_partidas",
                # E os dois da Fase 83 (S-539/S-540): o menu diz o que o comando faz com o
                # livro inteiro, e o botão do "Mais" diz o nome curto -- "Táticas do livro" e
                # "Revisar hoje", que são como se fala deles.
                "taticas_do_livro",
                "treinar_agenda",
                # E os três da Fase 84 (S-544/S-545), pela razão dos formatos acima: o menu diz
                # "Exportar o estudo para PDF…" e o item do agrupador diz ".pdf", ao lado dos
                # outros três; "Imprimir o estudo…" e "Exportar os diagramas em lote…" viram
                # "Imprimir" e "Diagramas em lote" no "Mais", onde o rótulo longo não caberia.
                "exportar_estudo_pdf",
                "imprimir_estudo",
                "exportar_diagramas_lote",
                # E os dois da segunda rodada da S-542/S-543, pela razão idêntica: o menu diz
                # "Exportar o estudo para EPUB…" e o item do agrupador diz ".epub". Eles chegaram
                # ao catálogo três dias depois dos módulos que os escrevem -- até aqui não havia
                # gesto nenhum que chamasse `epub.py` nem `docx_saida.py`.
                "exportar_estudo_epub",
                "exportar_estudo_docx",
                # E os três que a S-233 registrou como dívida e a terceira barra em fila pagou: o
                # menu diz "Salvar a posição" e o botão da fila diz "Salvar". Enquanto o painel de
                # Resultado escrevia os rótulos à mão eles não declaravam `rotulo_curto`, "que
                # seria uma promessa que ninguém cumpre".
                "salvar",
                "salvar_todos",
                "aplicar_fen",
                # E o da Fase 81 (S-535), pelo mesmo motivo: o menu diz "Árvore de aberturas desta
                # posição" porque é onde cabe dizer de que posição se fala, e o botão do grupo Base
                # diz "Árvore" -- ao lado de "Partidas", que responde a outra pergunta sobre a
                # mesma posição.
                "arvore_de_aberturas",
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

    DENTRO_DA_BUSCA = {
        "Substituir todos": "botão do diálogo de busca, e não comando do catálogo",
        "Diferenciar maiúsculas": "opção da busca: estado, e não ação",
        "A letra casa a figurina": "idem -- «Nf3» achar «♘f3» é uma opção da mesma busca",
    }
    """Os rótulos da `JanelaDeBusca` que **não** vêm do catálogo, e por quê.

    O catálogo declara `achar` e `substituir` -- os comandos que **abrem** o diálogo, e que o
    menu, a paleta e a fita mostram. O que está dentro dele é o formulário: o botão que executa a
    troca e duas opções. Pô-los no catálogo daria três entradas de menu que ninguém pode acionar
    sem o diálogo aberto, que é o oposto do que a S-324 pede.
    """

    def test_a_aba_texto_nao_escreve_rotulo_a_mao(self) -> None:
        """A varredura da S-324 cobre `qt/painel_de_texto.py`, que ela não cobria.

        Com os vinte e poucos comandos desta spec, o rótulo escrito à mão é a S-161 outra vez --
        *"o que não era botão não existia"* --, agora com três peles para divergir.
        """
        arvore = ast.parse(TEXTO_PANEL.read_text(encoding="utf-8"))
        sobraram = [
            achado
            for achado in _rotulos_literais(arvore)
            if not any(f"{rotulo!r}" in achado for rotulo in self.DENTRO_DA_BUSCA)
        ]
        self.assertEqual([], sobraram, "rótulo escrito à mão em qt/painel_de_texto.py")

    def test_a_lista_da_busca_nao_guarda_rotulo_que_sumiu(self) -> None:
        """Isenção que sobra é isenção que esconde: o próximo literal daquele arquivo entraria
        sem ninguém assinar."""
        arvore = ast.parse(TEXTO_PANEL.read_text(encoding="utf-8"))
        escritos = " ".join(_rotulos_literais(arvore))
        orfas = [rotulo for rotulo in self.DENTRO_DA_BUSCA if f"{rotulo!r}" not in escritos]
        self.assertEqual([], orfas, "rótulo declarado na isenção que já não existe no painel")
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
        declaradas = set(menu.acoes_declaradas()) | set(comandos.NA_JANELA_DE_BUSCA)
        fora = sorted(acao for acao in COMANDOS_DO_EDITOR if acao not in declaradas)
        self.assertEqual([], fora, "comando do editor sem casa no menu nem na janela de busca")

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
        """Cinco, e os quatro da sala são interruptores que **não** viraram `Checkbutton`
        (S-222/S-280/S-290).

        Os dois da sala de estudo entraram por uma razão de alcance, e não de estética: um
        `Checkbutton` não é comando, então o estado dele viveria só na barra -- a mesma ação pela
        paleta da S-231 ou pelo menu não teria onde ler o valor de antes, e o clique de lá seria uma
        alternância cega. Com botão que troca de texto, `alternar_recorte` é uma função só, e as três
        portas chamam a mesma.
        """
        alternam = {registro.acao for registro in comandos.CATALOGO if registro.rotulo_alternado}
        self.assertEqual(
            {
                "selecionar_area",
                "mostrar_diagrama",
                "analise_continua",
                "modo_treino",
                # A quinta é a S-516, e ela entra pela mesma razão de alcance das três da sala: a
                # dobra é estado de vista, mas quem a liga tem de poder ligá-la pelo menu e pela
                # paleta também -- e ali não há botão de onde ler o estado de antes.
                "dobrar_variantes",
            },
            alternam,
        )

    def test_quem_nao_alterna_responde_o_proprio_rotulo(self) -> None:
        """`alternado` devolve o texto normal em vez de vazio: quem consome não precisa saber
        se aquele comando alterna, e um `""` chegaria ao botão como botão sem rótulo."""
        for registro in comandos.CATALOGO:
            with self.subTest(acao=registro.acao):
                self.assertTrue(comandos.rotulo_alternado(registro.acao).strip())
                if not registro.rotulo_alternado:
                    self.assertEqual(registro.no_botao, registro.alternado)
