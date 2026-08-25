"""A paleta de comandos, que sai do catálogo da S-219 (S-231).

A pele "Foco" tira 23 controles da tela e os põe no menu. Cinco menus com 27 itens é um mapa que
se decora; 50 itens é um mapa em que se procura -- e é a S-161 ao contrário: *"o que não era botão
não existia"* vira "o que não está no menu que eu abri, eu não acho".

**O que estes testes travam é o filtro, e não a janela.** A janela desenha o que o filtro devolve;
o que decide qual comando aparece primeiro quando alguém digita três letras é uma função pura, e
ela é afirmável sem `Tk` -- inclusive nos casos que ninguém repara ao clicar: o acento, o empate,
e a linha cinza que **não pode sumir**.
"""

from __future__ import annotations

import ast
import tkinter as tk
import unittest
from pathlib import Path

from tk_root import raiz

from chess_diagram_ocr.ui import atalhos, comandos, menu, pele
from chess_diagram_ocr.ui import paleta_de_comandos as paleta

MODULO = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "ui" / "paleta_de_comandos.py"


class FiltroPuroTests(unittest.TestCase):
    """Sem uma única janela. É o critério de aceite do item, e é onde os casos difíceis moram."""

    def setUp(self) -> None:
        self.todas = paleta.inventario()

    def test_o_filtro_e_puro(self) -> None:
        """Não guarda estado, não mexe no que recebe, e devolve as **mesmas** entradas.

        As três coisas juntas são o que permite chamá-lo do `trace` do campo a cada tecla sem
        pensar duas vezes -- e o que faz um teste de ordem valer para a janela, e não só para si.
        """
        entrada = list(self.todas)
        primeira = paleta.filtrar("pag", entrada)
        segunda = paleta.filtrar("pag", entrada)
        self.assertEqual(primeira, segunda)
        self.assertEqual(list(self.todas), entrada, "o filtro mexeu na lista que recebeu")
        self.assertTrue(all(any(achada is original for original in entrada) for achada in primeira))

    def test_o_filtro_nao_toca_tkinter(self) -> None:
        """A metade pura é pura no código, e não só na intenção.

        A mesma varredura de `test_ui_comandos::test_o_catalogo_nao_importa_tkinter`: enquanto der
        para alcançar um widget daqui, alguém alcança -- e aí o filtro passa a precisar de uma
        janela aberta para ser conferido, que é como se perde a parte barata do item.
        """
        arvore = ast.parse(MODULO.read_text(encoding="utf-8"))
        puras = {"filtrar", "inventario", "motivos_declarados", "_casamento", "_dobrado", "_em_ordem_de_grupo"}
        nomes = {
            no.id
            for definicao in ast.walk(arvore)
            if isinstance(definicao, ast.FunctionDef) and definicao.name in puras
            for no in ast.walk(definicao)
            if isinstance(no, ast.Name)
        }
        self.assertEqual(set(), nomes & {"tk", "ttk"}, "função pura da paleta alcançando widget")

    def test_consulta_vazia_devolve_tudo_em_ordem_de_grupo(self) -> None:
        """**Aberta, a paleta é o índice do programa, e não um ranking.**

        Reordenar por pontuação com o campo vazio faria a primeira linha parecer "o comando mais
        importante". Em ordem de grupo ela é o que é: a barra de menus deitada.
        """
        tudo = paleta.filtrar("", self.todas)
        self.assertEqual(len(comandos.CATALOGO), len(tudo))
        self.assertEqual(
            [registro.acao for grupo in comandos.GRUPOS for registro in comandos.do_grupo(grupo)],
            [entrada.acao for entrada in tudo],
        )

    def test_a_paleta_cobre_o_catalogo_inteiro(self) -> None:
        """Por construção, e é o que a S-233 vai poder tomar como dado -- sem contar com ela."""
        self.assertEqual(
            {registro.acao for registro in comandos.CATALOGO},
            {entrada.acao for entrada in self.todas},
        )

    def test_o_acento_nao_e_cobrado_de_quem_digita(self) -> None:
        """"pagina" acha "Ler esta página". Cobrar o `í` é o teclado pedindo pedágio."""
        com_acento = [entrada.acao for entrada in paleta.filtrar("página", self.todas)]
        sem_acento = [entrada.acao for entrada in paleta.filtrar("pagina", self.todas)]
        self.assertEqual(com_acento, sem_acento)
        self.assertIn("ler_pagina", sem_acento)

    def test_o_espaco_da_consulta_nao_precisa_casar(self) -> None:
        """"ler pag" e "lerpag" são a mesma pergunta, e quem digita o espaço não pode perder."""
        self.assertEqual(
            [entrada.acao for entrada in paleta.filtrar("ler pag", self.todas)],
            [entrada.acao for entrada in paleta.filtrar("lerpag", self.todas)],
        )

    def test_o_casamento_e_por_subsequencia_e_nao_por_prefixo(self) -> None:
        """"slvr" acha "Salvar a posição": é o que uma paleta de comandos promete."""
        achadas = [entrada.acao for entrada in paleta.filtrar("slvr", self.todas)]
        self.assertIn("salvar", achadas)

    def test_o_vao_ordena_antes_do_rotulo_e_o_ocr_e_a_medida(self) -> None:
        """**O caso que inverteu a chave de ordenação, medido no catálogo de hoje.**

        `"ocr"` casa no *rótulo* de "Devolver as caixas tiradas desta página" -- o…c…r espalhado
        por dezenas de letras -- e no *grupo* de "Ler esta página", cravado em três. Com "casou no
        rótulo" acima do vão, a primeira subia: uma resposta que ninguém lê como certa.
        """
        achadas = [entrada.acao for entrada in paleta.filtrar("ocr", self.todas)]
        self.assertEqual(["ler_pagina", "ler_melhor", "selecionar_area"], achadas[:3])
        self.assertIn("devolver_caixas", achadas)

    def test_a_tecla_desempata_e_so_desempata(self) -> None:
        """A spec pede o comando de atalho subindo; posto acima do casamento ele atrapalha.

        `"l"` casa em início 0 e vão 0 nos dois: "Ler esta página" tem `Ctrl+R`, "Limpar o
        tabuleiro" não tem, e é o desempate. Se a tecla viesse antes da qualidade do casamento,
        "Ajustar à largura" (`Ctrl+0`, casa no `l` da décima letra) passaria os dois.
        """
        achadas = [entrada.acao for entrada in paleta.filtrar("l", self.todas)]
        self.assertEqual(["ler_pagina", "limpar_tabuleiro"], achadas[:2])
        self.assertLess(achadas.index("ler_pagina"), achadas.index("ajustar_largura"))

    def test_comando_desabilitado_aparece_com_motivo(self) -> None:
        """**Não some, e diz por quê.** Sumir responde "não existe" a quem perguntou "por que
        não posso agora?" -- que é o defeito que a S-165 mediu nos 13 controles sem tooltip.

        O motivo **é** o estado: `habilitado` é `not motivo`, então não há como construir uma
        linha cinza e muda.
        """
        amarrados = {registro.acao: (lambda: None) for registro in comandos.CATALOGO}
        del amarrados["treinar"]
        entradas = paleta.inventario(amarrados)
        self.assertEqual(len(comandos.CATALOGO), len(entradas), "a paleta escondeu uma linha")
        por_acao = {entrada.acao: entrada for entrada in entradas}
        self.assertFalse(por_acao["treinar"].habilitado)
        self.assertEqual(paleta.MOTIVO_SEM_FUNCAO, por_acao["treinar"].motivo)
        self.assertIn(paleta.MOTIVO_SEM_FUNCAO, por_acao["treinar"].no_texto)
        self.assertIn(comandos.rotulo("treinar"), por_acao["treinar"].no_texto)

    def test_o_motivo_declarado_ganha_da_amarracao(self) -> None:
        """`aparencia` tem função ligada e não é executável daqui: ela aplica o `StringVar` que o
        `radiobutton` acabou de mudar, e disparada fora desse gesto reaplica a pele que já vale.

        Mostrá-la preta seria prometer um clique que não faz nada -- o defeito que `menu.montar`
        recusa desde a S-161, na outra ponta.
        """
        entradas = {e.acao: e for e in paleta.inventario({r.acao: (lambda: None) for r in comandos.CATALOGO})}
        self.assertEqual(paleta.MOTIVO_SUBMENU, entradas["aparencia"].motivo)
        self.assertEqual(paleta.MOTIVO_SUBMENU, entradas["abrir_recente"].motivo)
        for acao in comandos.NA_LINHA_DE_CAMPO:
            self.assertEqual(paleta.MOTIVO_NA_LINHA_DE_CAMPO, entradas[acao].motivo)

    def test_os_motivos_declarados_saem_de_declaracao_alheia(self) -> None:
        """Nenhuma das duas listas é escrita neste módulo pela segunda vez.

        É o que faz um submenu novo em `menu.MENUS` ganhar o motivo certo sem que ninguém venha
        aqui -- e é a disciplina que a S-219 impôs quando três lugares declaravam comando.
        """
        submenus = {
            item.acao
            for declarado in menu.MENUS
            for item in declarado.itens
            if item.tipo in (menu.RECENTES, menu.APARENCIA, menu.DENSIDADE)
        }
        declarados = paleta.motivos_declarados()
        self.assertEqual(submenus | set(comandos.NA_LINHA_DE_CAMPO), set(declarados))

    def test_o_grupo_casa_por_trecho_e_nao_por_subsequencia(self) -> None:
        """**Uma palavra curta casa qualquer coisa por subsequência, e o resultado é lixo.**

        Medido: `"sal"` é subsequência de "visualizacao" -- o *s*, o *a* e o *l* --, e com a mesma
        régua do rótulo a consulta trazia os catorze comandos daquele grupo atrás de "Salvar a
        posição". Com trecho contíguo, `"ocr"` e `"arquivo"` continuam achando o grupo, que é o
        que alguém digita quando quer o grupo.
        """
        por_sal = [entrada.acao for entrada in paleta.filtrar("sal", self.todas)]
        self.assertEqual(["salvar", "salvar_todos"], por_sal[:2])
        self.assertNotIn("pagina_anterior", por_sal, "o grupo Visualização entrou inteiro por 'sal'")
        self.assertIn("abrir_pdf", [entrada.acao for entrada in paleta.filtrar("arquivo", self.todas)])

    def test_a_linha_cinza_desce_so_no_empate_e_o_anotar_e_a_medida(self) -> None:
        """**A leitura literal de "desabilitado sempre no fim" foi medida e recusada.**

        Com ela, `"anotar"` trazia "Desfazer a última mudança no tabuleiro" -- a…n…o…t…a…r
        espalhado pela frase -- acima de "Anotar página", que é a resposta à pergunta. Enterrar a
        linha cinza sob casamento ruim desfaz o item ao lado, que existe para que ela seja achada
        e diga por quê. Ela desce **entre iguais**, e é o Enter que garante que nada dispare.
        """
        entradas = paleta.inventario({r.acao: (lambda: None) for r in comandos.CATALOGO})
        achadas = paleta.filtrar("anotar", entradas)
        self.assertEqual("anotar_pagina", achadas[0].acao)
        self.assertFalse(achadas[0].habilitado)
        self.assertIn("desfazer", [entrada.acao for entrada in achadas])

        # E o empate, que é onde ela desce: os dois "Tirar" casam igual, e o vivo vem antes.
        por_tirar = [entrada.acao for entrada in paleta.filtrar("tirar", entradas)]
        self.assertEqual(["tirar_caixa", "tirar_do_campo"], por_tirar[:2])

    def test_consulta_que_nao_acha_nada_devolve_vazio_e_nao_tudo(self) -> None:
        self.assertEqual((), paleta.filtrar("zzqx", self.todas))


class PortasDaPaletaTests(unittest.TestCase):
    """As três portas: a tecla, o menu, e o catálogo. Nenhuma delas abre janela para ser conferida."""

    def test_a_paleta_existe_nas_tres_peles(self) -> None:
        """**Ela não é da "Foco".** A pele que mais precisa dela é a que esconde 23 controles,
        mas a barra de menus é uma declaração só para as três peles (`ui/menu.py`), e a tecla é
        ligada em `bind_shortcuts`, que não sabe qual pele está valendo.

        A afirmação forte -- *todo* comando alcançável em *toda* pele -- é da S-233, e este teste
        é a parte dela que já dá para cobrar hoje.
        """
        self.assertEqual(3, len(pele.PELES))
        for registro in pele.PELES:
            with self.subTest(pele=registro.nome):
                self.assertIn("paleta_de_comandos", menu.acoes_declaradas())
                self.assertIn("paleta_de_comandos", atalhos.por_acao)

    def test_a_tecla_e_ctrl_shift_p_e_a_maiuscula(self) -> None:
        """Mesma razão do `Ctrl+Shift+S` (S-20): `<Control-Shift-p>` não chega no Windows."""
        self.assertEqual("<Control-P>", atalhos.por_acao["paleta_de_comandos"].sequencia)
        self.assertEqual("Ctrl+Shift+P", atalhos.acelerador("paleta_de_comandos"))

    def test_a_paleta_esta_no_catalogo_e_no_menu_ajuda(self) -> None:
        """Uma paleta sem porta de menu é uma paleta que só quem já sabe a tecla encontra."""
        self.assertEqual(comandos.AJUDA, comandos.comando("paleta_de_comandos").grupo)
        self.assertIn("paleta_de_comandos", menu.acoes_declaradas())

    def test_a_paleta_nao_entra_na_fila_de_destaque(self) -> None:
        """A fila é o gesto do minuto a minuto (S-223); achar comando não é um deles."""
        self.assertNotIn("paleta_de_comandos", [r.acao for r in comandos.em_destaque()])


class JanelaTests(unittest.TestCase):
    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.pai = tk.Toplevel(self.root)
        self.addCleanup(self.pai.destroy)
        self.chamados: list[str] = []
        self.amarrados = {
            registro.acao: (lambda acao=registro.acao: self.chamados.append(acao))
            for registro in comandos.CATALOGO
            if registro.acao != "treinar"
        }

    def _janela(self) -> paleta.JanelaDaPaleta:
        janela = paleta.JanelaDaPaleta(self.pai, self.amarrados)
        self.addCleanup(lambda: janela.winfo_exists() and janela.destroy())
        return janela

    def test_a_janela_desenha_o_que_o_filtro_devolve(self) -> None:
        janela = self._janela()
        self.assertEqual(len(comandos.CATALOGO), len(janela.lista.get_children()))
        janela.digitar("salv")
        self.assertEqual(
            ["salvar", "salvar_todos"],
            [entrada.acao for entrada in janela.visiveis()],
        )
        self.assertEqual(len(janela.visiveis()), len(janela.lista.get_children()))

    def test_a_linha_cinza_leva_a_marca_e_o_motivo_na_coluna(self) -> None:
        janela = self._janela()
        janela.digitar("treinar")
        alvo = janela.lista.get_children()[0]
        self.assertIn(paleta.TAG_DESABILITADO, janela.lista.item(alvo, "tags"))
        self.assertIn(paleta.MOTIVO_SEM_FUNCAO, janela.lista.item(alvo, "values")[0])

    def test_a_coluna_da_direita_e_o_grupo_e_a_do_meio_e_a_tecla(self) -> None:
        janela = self._janela()
        janela.digitar("ler esta")
        comando, tecla, grupo = janela.lista.item(janela.lista.get_children()[0], "values")
        self.assertEqual(comandos.rotulo("ler_pagina"), comando)
        self.assertEqual("Ctrl+R", tecla)
        self.assertEqual(comandos.rotulo_do_grupo(comandos.OCR), grupo)

    def test_as_teclas_da_paleta_estao_ligadas_no_campo(self) -> None:
        """**A outra metade do teste de teclado, e a razão de ela ser separada.**

        A S-117 registrou por que não se dirige o Tk com `event_generate` numa suíte: sem foco de
        verdade o evento não chega, e com `focus_force` o teste passa a medir o gerenciador de
        janelas. Então a decisão é conferida chamando `executar`, `mover` e `fechar`, e o que
        sobra -- que a tecla chega neles -- é esta afirmação.
        """
        janela = self._janela()
        for sequencia in ("<Return>", "<Escape>", "<Up>", "<Down>"):
            with self.subTest(tecla=sequencia):
                self.assertTrue(janela.ligada(sequencia), "tecla da paleta não ligada no campo")

    def test_enter_executa_o_primeiro(self) -> None:
        janela = self._janela()
        janela.digitar("salvar a")
        janela.executar()
        self.assertEqual(["salvar"], self.chamados)

    def test_a_paleta_fecha_ao_executar(self) -> None:
        """Metade destes comandos abre uma caixa de diálogo, e duas janelas pedindo resposta ao
        mesmo tempo é a pergunta que ninguém sabe qual responder."""
        janela = self._janela()
        janela.digitar("salvar a")
        janela.executar()
        self.assertFalse(janela.winfo_exists())

    def test_as_setas_navegam_e_o_enter_executa_o_selecionado(self) -> None:
        janela = self._janela()
        janela.digitar("salvar")
        self.assertEqual("salvar", janela.selecionada().acao)
        janela.mover(1)
        self.assertEqual("salvar_todos", janela.selecionada().acao)
        janela.mover(-1)
        self.assertEqual("salvar", janela.selecionada().acao)
        janela.executar()
        self.assertEqual(["salvar"], self.chamados)

    def test_a_seta_nao_passa_da_ponta(self) -> None:
        """Uma lista que dá a volta faz a última linha parecer a primeira em qualquer rolagem."""
        janela = self._janela()
        janela.digitar("salvar")
        janela.mover(-1)
        self.assertEqual("salvar", janela.selecionada().acao)
        for _ in range(5):
            janela.mover(1)
        self.assertEqual("salvar_todos", janela.selecionada().acao)

    def test_esc_fecha_sem_executar(self) -> None:
        janela = self._janela()
        janela.digitar("salvar a")
        janela.fechar()
        self.assertFalse(janela.winfo_exists())
        self.assertEqual([], self.chamados)

    def test_enter_sobre_linha_cinza_nao_faz_nada_e_nao_fecha(self) -> None:
        """Ela está lá para ser lida, e não para ser clicada -- e um `KeyError` aqui seria a
        paleta derrubando a janela por causa de um comando que ela mesma marcou como fora."""
        janela = self._janela()
        janela.digitar("treinar")
        janela.executar()
        self.assertEqual([], self.chamados)
        self.assertTrue(janela.winfo_exists())

    def test_consulta_sem_resultado_nao_tem_selecao_e_o_enter_nao_estoura(self) -> None:
        janela = self._janela()
        janela.digitar("zzqx")
        self.assertEqual((), janela.visiveis())
        self.assertIsNone(janela.selecionada())
        janela.executar()
        self.assertEqual([], self.chamados)

    def test_abrir_duas_vezes_traz_a_mesma_janela(self) -> None:
        """A tecla que abre é a mesma que se aperta quando nada pareceu acontecer."""
        primeira = paleta.abrir(self.pai, self.amarrados)
        self.addCleanup(lambda: primeira.winfo_exists() and primeira.destroy())
        primeira.digitar("salv")
        segunda = paleta.abrir(self.pai, self.amarrados)
        self.assertIs(primeira, segunda)
        self.assertEqual("salv", segunda.consulta.get(), "a paleta reaberta perdeu a consulta")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
