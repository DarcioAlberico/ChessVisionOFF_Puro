"""A barra do painel do PDF como dado, e a forma que ela divide com a barra da sala (S-528).

**O que se afirma sem janela.** Que a tabela cobre `comandos.NAS_BARRAS_DO_PDF` e nada além dela;
que toda ação tem grupo, ícone e método do painel; que "principal" e "Mais" são uma partição; que
a regra de modo poupa o grupo `EXPORTAR` quando o painel está trancado -- que é o que mantém o
cancelar vivo --; e que a forma compartilhada (`ui/barra.Acao`) responde igual para as duas
tabelas sem uma enxergar a outra. O widget que executa isto está em
`tests/test_qt_painel_do_pdf.py`.
"""

from __future__ import annotations

import ast
import unittest
from collections import Counter
from pathlib import Path

from chess_diagram_ocr.ui import atalhos, barra, barra_da_sala, barra_do_pdf, comandos, icones


class CoberturaTests(unittest.TestCase):
    """Nos dois sentidos: comando declarado que a barra não desenha, e ação sem declaração."""

    def test_a_tabela_e_exatamente_o_que_o_catalogo_declara_para_o_painel(self) -> None:
        """`NAS_BARRAS_DO_PDF` é a lista que o inventário lê sem abrir janela, e ela ficou **sem
        leitor** do corte do Tk até a S-506 -- nesse intervalo divergiu em cinco nomes."""
        declarados = set(comandos.NAS_BARRAS_DO_PDF)
        na_barra = {registro.acao for registro in barra_do_pdf.ACOES}
        self.assertEqual(set(), declarados - na_barra, "comando do painel sem lugar na barra")
        self.assertEqual(set(), na_barra - declarados, "ação da barra que o painel não declara")

    def test_toda_acao_esta_no_catalogo_e_tem_metodo_do_painel(self) -> None:
        """Nada aqui é ação própria: ao contrário da sala, o painel do PDF não tem interruptor
        fora do catálogo -- os dois `QCheckBox` eram `marcar_diagramas` e `roda_vira_pagina`, que
        têm item de menu desde sempre."""
        for registro in barra_do_pdf.ACOES:
            with self.subTest(acao=registro.acao):
                self.assertTrue(registro.no_catalogo, "ação fora do catálogo")
                self.assertEqual("", registro.rotulo_proprio)
                self.assertTrue(registro.metodo, "ação sem método do painel")
        self.assertEqual(
            sorted(barra_do_pdf.METODOS_DO_PAINEL),
            sorted(registro.acao for registro in barra_do_pdf.ACOES),
            "método declarado para ação que não existe, ou ação sem método",
        )

    def test_ids_unicos_e_nenhum_grupo_vazio(self) -> None:
        repetidos = [a for a, vezes in Counter(r.acao for r in barra_do_pdf.ACOES).items() if vezes > 1]
        self.assertEqual([], repetidos)
        for grupo in barra_do_pdf.GRUPOS:
            with self.subTest(grupo=grupo):
                self.assertTrue(barra_do_pdf.do_grupo(grupo), "grupo sem ação")
                self.assertTrue(barra_do_pdf.rotulo_do_grupo(grupo))

    def test_principal_e_mais_sao_uma_particao(self) -> None:
        principais = {r.acao for r in barra_do_pdf.principais()}
        no_mais = {r.acao for r in barra_do_pdf.secundarias()}
        self.assertEqual(set(), principais & no_mais)
        self.assertEqual({r.acao for r in barra_do_pdf.ACOES}, principais | no_mais)
        self.assertFalse(any(r.dentro_de for r in barra_do_pdf.ACOES), "esta barra não tem agrupador")

    def test_a_unica_prioridade_repetida_e_o_par_de_pagina(self) -> None:
        """Duas ações com a mesma prioridade são um **par** que entra e sai da fila junto
        (`ui/barra.cabem`); `◀` sem `▶` é meia navegação, e é o gesto mais repetido do painel.
        Fora do par, prioridade repetida deixaria a posição na tabela desempatar."""
        principais = barra_do_pdf.principais()
        self.assertTrue(all(r.prioridade > 0 for r in principais), "principal sem prioridade")
        repetidas = {p for p, vezes in Counter(r.prioridade for r in principais).items() if vezes > 1}
        self.assertEqual(1, len(repetidas), f"prioridades repetidas: {sorted(repetidas)}")
        par = {r.acao for r in principais if r.prioridade in repetidas}
        self.assertEqual({"pagina_anterior", "proxima_pagina"}, par)

    def test_duas_com_texto_e_a_enfase_e_uma_so(self) -> None:
        """A hierarquia do ChessBase: texto no que se lê de longe -- o que se faz antes de tudo e
        o que a tela existe para fazer. A ênfase vem do catálogo (S-324), e é uma por barra."""
        com_texto = {r.acao for r in barra_do_pdf.ACOES if r.com_texto}
        self.assertEqual({"abrir_pdf", "ler_melhor"}, com_texto)
        primarios = [r.acao for r in barra_do_pdf.ACOES if r.papel == "PRIMARIO"]
        self.assertEqual(["ler_melhor"], primarios)
        for registro in barra_do_pdf.ACOES:
            if registro.com_texto:
                self.assertTrue(registro.principal, f"{registro.acao}: texto em quem não tem botão")

    def test_o_par_de_pagina_e_o_mais_prioritario_depois_do_primario(self) -> None:
        """Virar folha é o gesto mais repetido do painel; ler o melhor diagrama é o único que o
        precede. Se a página cair na frente, o `[21 de 289]` some junto -- ele é encaixado nela."""
        self.assertEqual(1, barra_do_pdf.acao("ler_melhor").prioridade)
        self.assertEqual(2, barra_do_pdf.acao("pagina_anterior").prioridade)

    def test_o_zoom_e_as_preferencias_moram_no_mais(self) -> None:
        """Decisão do item, e não corte: o deslizador da S-225 fica logo abaixo da folha, com a
        porcentagem ao lado, e marcar/roda são preferências de uma vez por sessão."""
        no_mais = {r.acao for r in barra_do_pdf.secundarias()}
        self.assertEqual(
            {"abrir_no_leitor", "zoom_menos", "zoom_mais", "marcar_diagramas", "roda_vira_pagina", "tirar_caixa"},
            no_mais,
        )

    def test_acao_e_grupo_desconhecidos_levantam(self) -> None:
        with self.assertRaises(KeyError):
            barra_do_pdf.acao("varrer_livro")
        with self.assertRaises(KeyError):
            barra_do_pdf.rotulo_do_grupo("VISUALIZACAO")


class RotuloEDicaTests(unittest.TestCase):
    """Nenhum texto do catálogo é reescrito, e a tecla não é registrada por esta barra."""

    def test_rotulo_e_papel_saem_do_catalogo(self) -> None:
        for registro in barra_do_pdf.ACOES:
            with self.subTest(acao=registro.acao):
                self.assertEqual(comandos.rotulo_de_botao(registro.acao), registro.rotulo_curto)
                self.assertEqual(comandos.rotulo(registro.acao), registro.rotulo_longo)
                self.assertEqual(comandos.papel(registro.acao), registro.papel)

    def test_a_dica_comeca_pelo_rotulo_longo_com_a_tecla_na_mesma_linha(self) -> None:
        """Num botão só com ícone a dica é o único lugar em que o rótulo aparece, e a tecla é
        parte da mesma resposta -- é a forma que o crítico da S-527 pediu."""
        com_tecla = [r for r in barra_do_pdf.ACOES if atalhos.acelerador(r.acao)]
        self.assertTrue(com_tecla, "nenhuma ação do painel tem tecla")
        for registro in barra_do_pdf.ACOES:
            with self.subTest(acao=registro.acao):
                linhas = barra_do_pdf.dica_de(registro).split(chr(10))
                tecla = atalhos.acelerador(registro.acao)
                esperado = (
                    f"{registro.rotulo_longo}{barra.SEPARADOR_DA_TECLA}{tecla}" if tecla else registro.rotulo_longo
                )
                self.assertEqual(esperado, linhas[0])
                self.assertNotIn("Tecla:", linhas[0])

    def test_a_barra_nao_reivindica_tecla_nenhuma(self) -> None:
        """As dezesseis são da janela e já têm dono no menu. Registrá-las de novo aqui daria duas
        donas para a mesma tecla -- a colisão que `atalhos.conferir_dono` acusa. Na sala é o
        contrário, e é por isso que o gancho existe nas duas tabelas."""
        for registro in barra_do_pdf.ACOES:
            with self.subTest(acao=registro.acao):
                self.assertEqual("", barra_do_pdf.sequencia_de(registro.acao))
        self.assertTrue(
            any(barra_da_sala.sequencia_de(a.acao) for a in atalhos.TECLAS_DA_SALA),
            "a sala parou de declarar tecla própria: o gancho ficou vácuo dos dois lados",
        )

    def test_quem_alterna_no_metodo_e_so_quem_tem_rotulo_alternado(self) -> None:
        """**A régua mudou na S-528**: era "está no catálogo", e as duas preferências do painel são
        do catálogo e **não** invertem o estado -- o método delas lê `isChecked()`. Um botão que
        alternasse além do método alternaria duas vezes, que é o defeito medido em "Treinar"."""
        marcaveis = {r.acao: r for r in barra_do_pdf.ACOES if r.marcavel}
        self.assertEqual({"marcar_diagramas", "roda_vira_pagina", "selecionar_area"}, set(marcaveis))
        self.assertTrue(marcaveis["selecionar_area"].alterna_no_metodo, "o modo da S-396 se inverte sozinho")
        for nome in ("marcar_diagramas", "roda_vira_pagina"):
            with self.subTest(acao=nome):
                self.assertFalse(marcaveis[nome].alterna_no_metodo)
                self.assertEqual("", comandos.comando(nome).rotulo_alternado)


class IconesTests(unittest.TestCase):
    """A ponte com `ui/icones.py`, nos dois sentidos -- a terceira tabela de traços."""

    def test_toda_acao_tem_traco(self) -> None:
        faltando = sorted(r.acao for r in barra_do_pdf.ACOES if icones.tracos_de(r.icone) is None)
        self.assertEqual([], faltando, "ação com ícone que não existe")

    def test_nenhum_traco_do_pdf_e_orfao(self) -> None:
        usados = {r.icone for r in barra_do_pdf.ACOES}
        self.assertEqual([], sorted(set(icones.ICONES_DO_PDF) - usados))

    def test_os_tres_dicionarios_nao_repetem_chave(self) -> None:
        """Uma chave em dois deles faria `tracos_de` responder pelo primeiro em silêncio."""
        self.assertEqual(set(), set(icones.ICONES) & set(icones.ICONES_DO_PDF))
        self.assertEqual(set(), set(icones.ICONES_DA_SALA) & set(icones.ICONES_DO_PDF))

    def test_nove_acoes_reusam_o_traco_do_catalogo(self) -> None:
        """Aqueles ícones foram desenhados na S-220 para estes mesmos comandos: um segundo desenho
        seria a mesma arte em dois lugares, que é o que a S-501 desduplicou neste pacote."""
        reusados = sorted(r.icone for r in barra_do_pdf.ACOES if r.icone in icones.ICONES)
        self.assertEqual(9, len(reusados), reusados)

    def test_todo_traco_do_pdf_cabe_na_caixa(self) -> None:
        fora = []
        for nome, tracos in icones.ICONES_DO_PDF.items():
            self.assertTrue(tracos, f"{nome} sem traço")
            for traco in tracos:
                x0, y0, x1, y1 = traco.limites()
                if min(x0, y0) < 0 or max(x1, y1) > icones.LADO_DA_CAIXA:
                    fora.append(f"{nome}: {traco!r}")
        self.assertEqual([], fora, "traço que vaza a caixa desenha cortado")

    PIXELS_FORTES = 8
    GLIFO_MINIMO = 12

    def test_a_16_px_todo_traco_tem_pixel_forte_e_glifo_de_12_px(self) -> None:
        """A régua do achado 5 do crítico da S-527, aplicada à tabela nova: desenhados a 32 e
        reduzidos a 16 os traços saem esmaecidos. Medido em 2026-09-04: o mais fraco destes sete
        tem 28 pixels fortes."""
        for nome in sorted({r.icone for r in barra_do_pdf.ACOES}):
            with self.subTest(icone=nome):
                desenho = icones.imagem(nome, 16, "#101010")
                assert desenho is not None
                alfa = desenho.getchannel("A")
                fortes = sum(1 for x in range(16) for y in range(16) if alfa.getpixel((x, y)) >= 200)
                self.assertGreaterEqual(fortes, self.PIXELS_FORTES, "traço esmaecido")
                x0, y0, x1, y1 = alfa.getbbox()
                self.assertGreaterEqual(max(x1 - x0, y1 - y0), self.GLIFO_MINIMO, "glifo pequeno demais")


class ModoTests(unittest.TestCase):
    """O que não é do momento fica cinza, e a regra é enunciável."""

    def test_os_tres_modos(self) -> None:
        self.assertEqual(barra_do_pdf.SEM_LIVRO, barra_do_pdf.modo(livro=False, trancado=False))
        self.assertEqual(barra_do_pdf.COM_LIVRO, barra_do_pdf.modo(livro=True, trancado=False))
        self.assertEqual(barra_do_pdf.TRANCADO, barra_do_pdf.modo(livro=True, trancado=True))
        self.assertEqual(barra_do_pdf.TRANCADO, barra_do_pdf.modo(livro=False, trancado=True))

    def test_sem_livro_so_o_grupo_do_livro_fica_de_pe(self) -> None:
        """"Abrir PDF" é a saída deste modo: desligar o grupo dele deixaria a tela sem porta."""
        desligados = barra_do_pdf.grupos_desligados(barra_do_pdf.SEM_LIVRO)
        self.assertNotIn(barra_do_pdf.LIVRO, desligados)
        self.assertEqual(
            {barra_do_pdf.PAGINA, barra_do_pdf.VISTA, barra_do_pdf.LEITURA, barra_do_pdf.EXPORTAR},
            set(desligados),
        )

    def test_trancado_poupa_o_exportar_e_so_ele(self) -> None:
        """O cancelar só existe durante a exportação, que é justamente quando tudo o mais está
        trancado: obedecer à trava faria o botão ficar cinza na única situação em que ele serve."""
        desligados = barra_do_pdf.grupos_desligados(barra_do_pdf.TRANCADO)
        self.assertNotIn(barra_do_pdf.EXPORTAR, desligados)
        self.assertEqual(set(barra_do_pdf.GRUPOS) - {barra_do_pdf.EXPORTAR}, set(desligados))

    def test_com_livro_nada_desliga(self) -> None:
        self.assertEqual(frozenset(), barra_do_pdf.grupos_desligados(barra_do_pdf.COM_LIVRO))

    def test_modo_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            barra_do_pdf.grupos_desligados("exportando")


class FormaCompartilhadaTests(unittest.TestCase):
    """A forma é uma, e as duas tabelas não se enxergam (S-528)."""

    def test_as_duas_tabelas_tem_vocabularios_de_grupo_proprios(self) -> None:
        """`GRUPOS` é `ClassVar` da subclasse: um grupo da sala numa ação do PDF tem de levantar,
        senão a validação de `__post_init__` estaria medindo a tabela errada."""
        self.assertEqual(barra_do_pdf.GRUPOS, barra_do_pdf.Acao.GRUPOS)
        self.assertEqual(barra_da_sala.GRUPOS, barra_da_sala.Acao.GRUPOS)
        with self.assertRaises(KeyError):
            barra_do_pdf.Acao("abrir_pdf", barra_da_sala.POSICAO, "abrir_pdf")
        with self.assertRaises(KeyError):
            barra_da_sala.Acao("copiar_fen", barra_do_pdf.VISTA, "copiar")

    def test_cada_tabela_responde_pelos_proprios_metodos(self) -> None:
        """`METODOS` também é `ClassVar`: o mesmo comando nas duas barras aponta para o método do
        painel de cada uma. `abrir_pgn` é da sala e `abrir_pdf` é do PDF, e nenhum é dos dois."""
        self.assertEqual("abrir_pdf", barra_do_pdf.acao("abrir_pdf").metodo)
        self.assertEqual("load_from_recognized", barra_da_sala.acao("estudo_do_diagrama").metodo)
        self.assertEqual(set(), set(barra_do_pdf.METODOS_DO_PAINEL) & set(barra_da_sala.METODOS_PROPRIOS))

    def test_a_forma_e_a_mesma_classe(self) -> None:
        self.assertTrue(issubclass(barra_do_pdf.Acao, barra.Acao))
        self.assertTrue(issubclass(barra_da_sala.Acao, barra.Acao))
        self.assertIs(barra.cabem, barra_do_pdf.cabem)
        self.assertIs(barra.cabem, barra_da_sala.cabem)

    def test_o_agrupador_de_uma_tabela_nao_vaza_para_a_outra(self) -> None:
        """`IRMAS` é por tabela: "Exportar ▾" abre três itens na sala, e no PDF ninguém é
        agrupador -- se a lista fosse global, `exportar_pgn` do PDF viraria um menu vazio."""
        self.assertTrue(barra_da_sala.acao(barra_da_sala.EXPORTAR_ESTUDO).agrupador)
        self.assertFalse(barra_do_pdf.acao("exportar_pgn").agrupador)
        self.assertEqual((), barra_do_pdf.acao("exportar_pgn").itens_do_submenu)


class PurezaTests(unittest.TestCase):
    def test_os_dois_modulos_nao_importam_toolkit(self) -> None:
        for modulo in (barra_do_pdf, barra):
            with self.subTest(modulo=modulo.__name__):
                arvore = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))
                nomes = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
                nomes |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
                self.assertEqual(set(), nomes & {"PyQt6", "tkinter"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
