"""A barra da sala de estudo como dado, e a ponte dela com a aba, o catálogo e os traços (S-527).

**O que se afirma sem janela.** Que a tabela cobre a aba inteira e nada além dela; que toda ação
tem grupo, ícone e método; que "principal" e "Mais" são uma partição; que a regra de modo desliga
o que não é do momento; e que `cabem` -- a conta de quem fica na fila -- responde por prioridade e
nunca deixa o "Mais" de fora. O widget que executa isto está em `tests/test_qt_barra_da_sala.py`.
"""

from __future__ import annotations

import ast
import unittest
from collections import Counter
from pathlib import Path

from chess_diagram_ocr.ui import atalhos, barra_da_sala, comandos, icones, sala_declarada


class CoberturaTests(unittest.TestCase):
    """Nos dois sentidos: comando da aba que a barra não desenha, e ação da barra que a aba não tem."""

    def test_a_tabela_cobre_a_aba_inteira_menos_a_navegacao(self) -> None:
        """A S-517 pôs os quatro de navegação sob o tabuleiro; tudo o mais da aba tem de estar aqui,
        senão um comando some da tela sem sair do menu -- o defeito da S-280."""
        da_aba = set(sala_declarada.COMANDOS_DA_ABA) - set(barra_da_sala.NAVEGACAO)
        na_barra = {registro.acao for registro in barra_da_sala.ACOES if registro.no_catalogo}
        self.assertEqual(set(), da_aba - na_barra, "comando da aba sem lugar na barra")
        self.assertEqual(set(), na_barra - da_aba, "ação da barra que a aba não tem")

    def test_o_que_esta_fora_do_catalogo_e_so_o_interruptor_e_o_agrupador(self) -> None:
        fora = sorted(registro.acao for registro in barra_da_sala.ACOES if not registro.no_catalogo)
        self.assertEqual([barra_da_sala.EXPORTAR_ESTUDO, barra_da_sala.SEGUIR_OCR], fora)

    def test_toda_acao_que_faz_algo_tem_metodo_e_o_agrupador_nao(self) -> None:
        """O método é o de `COMANDOS_DA_ABA` ou de `METODOS_PROPRIOS`; o agrupador só abre."""
        for registro in barra_da_sala.ACOES:
            with self.subTest(acao=registro.acao):
                if registro.agrupador:
                    self.assertEqual("", registro.metodo)
                else:
                    self.assertTrue(registro.metodo, "ação sem método")

    def test_ids_unicos_e_nenhum_grupo_vazio(self) -> None:
        repetidos = [acao for acao, vezes in Counter(r.acao for r in barra_da_sala.ACOES).items() if vezes > 1]
        self.assertEqual([], repetidos)
        for grupo in barra_da_sala.GRUPOS:
            with self.subTest(grupo=grupo):
                self.assertTrue(barra_da_sala.do_grupo(grupo), "grupo sem ação")
                self.assertTrue(barra_da_sala.rotulo_do_grupo(grupo))

    def test_principal_e_mais_sao_uma_particao(self) -> None:
        """Toda ação ou tem botão, ou está no "Mais", ou mora num agrupador -- e só uma das três."""
        principais = {r.acao for r in barra_da_sala.principais()}
        no_mais = {r.acao for r in barra_da_sala.secundarias()}
        em_submenu = {r.acao for r in barra_da_sala.ACOES if r.dentro_de}
        self.assertEqual(set(), principais & no_mais)
        self.assertEqual(set(), principais & em_submenu)
        self.assertEqual(set(), no_mais & em_submenu)
        self.assertEqual({r.acao for r in barra_da_sala.ACOES}, principais | no_mais | em_submenu)

    def test_os_tres_formatos_moram_no_exportar(self) -> None:
        """Eram três botões `.md`, `.html`, `.rtf`; viram um "Exportar ▾" porque são a mesma
        pergunta, e não três gestos."""
        agrupador = barra_da_sala.acao(barra_da_sala.EXPORTAR_ESTUDO)
        self.assertTrue(agrupador.agrupador)
        self.assertEqual(
            ("exportar_estudo_md", "exportar_estudo_html", "exportar_estudo_rtf"), agrupador.itens_do_submenu
        )
        for nome in agrupador.itens_do_submenu:
            self.assertEqual(barra_da_sala.EXPORTAR_ESTUDO, barra_da_sala.acao(nome).dentro_de)

    def test_as_prioridades_das_principais_sao_unicas(self) -> None:
        """Duas ações com a mesma prioridade deixariam `cabem` decidir pela posição na tabela, que
        é uma segunda declaração de ordem -- e é dela que a S-324 tirou o programa."""
        prioridades = [r.prioridade for r in barra_da_sala.principais()]
        self.assertTrue(all(p > 0 for p in prioridades), "principal sem prioridade")
        self.assertEqual(len(prioridades), len(set(prioridades)))

    def test_o_motor_so_existe_com_motor(self) -> None:
        sem = {r.grupo for r in barra_da_sala.acoes_para(com_motor=False)}
        com = {r.grupo for r in barra_da_sala.acoes_para(com_motor=True)}
        self.assertNotIn(barra_da_sala.MOTOR, sem)
        self.assertIn(barra_da_sala.MOTOR, com)
        self.assertEqual(set(barra_da_sala.GRUPOS), com)

    def test_acao_desconhecida_levanta(self) -> None:
        with self.assertRaises(KeyError):
            barra_da_sala.acao("lance_anterior")
        with self.assertRaises(KeyError):
            barra_da_sala.rotulo_do_grupo("ESTUDO")


class RotuloEDicaTests(unittest.TestCase):
    """Nenhum texto do catálogo é reescrito; só o que o catálogo não tem é declarado aqui."""

    def test_comando_do_catalogo_le_o_rotulo_de_la(self) -> None:
        for registro in barra_da_sala.ACOES:
            if not registro.no_catalogo:
                continue
            with self.subTest(acao=registro.acao):
                self.assertEqual(comandos.rotulo_de_botao(registro.acao), registro.rotulo_curto)
                self.assertEqual(comandos.rotulo(registro.acao), registro.rotulo_longo)
                self.assertEqual(comandos.papel(registro.acao), registro.papel)

    def test_rotulo_proprio_so_fora_do_catalogo(self) -> None:
        with self.assertRaises(ValueError):
            barra_da_sala.Acao("copiar_fen", barra_da_sala.POSICAO, "copiar", rotulo_proprio="Copiar")
        with self.assertRaises(ValueError):
            barra_da_sala.Acao("coisa_nova", barra_da_sala.POSICAO, "copiar")

    def test_a_dica_comeca_pelo_rotulo_longo_e_termina_na_tecla(self) -> None:
        """Uma frase por linha: o que é, como funciona, como se chama pelo teclado."""
        com_tecla = [r for r in barra_da_sala.ACOES if r.no_catalogo and atalhos.acelerador(r.acao)]
        for registro in barra_da_sala.ACOES:
            with self.subTest(acao=registro.acao):
                linhas = barra_da_sala.dica_de(registro).split(chr(10))
                self.assertEqual(registro.rotulo_longo, linhas[0])
                if registro.dica:
                    self.assertIn(registro.dica, barra_da_sala.dica_de(registro))
        for registro in com_tecla:
            with self.subTest(acao=registro.acao):
                self.assertTrue(barra_da_sala.dica_de(registro).endswith(f"Tecla: {atalhos.acelerador(registro.acao)}"))

    def test_quem_alterna_no_metodo_sao_os_marcaveis_do_catalogo(self) -> None:
        """Os quatro com `rotulo_alternado` invertem `isChecked()` no método (S-222); o botão que
        alternasse também alternaria duas vezes -- é o defeito que a medição de 2026-09-04 achou no
        clique de "Treinar". O interruptor próprio é o contrário: o método lê o estado."""
        marcaveis = {r.acao: r for r in barra_da_sala.ACOES if r.marcavel}
        self.assertEqual(
            {"dobrar_variantes", "mostrar_diagrama", "analise_continua", "modo_treino", barra_da_sala.SEGUIR_OCR},
            set(marcaveis),
        )
        for nome, registro in marcaveis.items():
            with self.subTest(acao=nome):
                self.assertEqual(registro.no_catalogo, registro.alterna_no_metodo)
                if registro.no_catalogo:
                    self.assertTrue(comandos.comando(nome).rotulo_alternado)


class IconesTests(unittest.TestCase):
    """A ponte com `ui/icones.py`, nos dois sentidos -- como a do catálogo, mas com a outra tabela."""

    def test_toda_acao_que_pode_virar_botao_tem_traco(self) -> None:
        faltando = sorted(
            r.acao
            for r in barra_da_sala.ACOES
            if not r.dentro_de and icones.tracos_de(r.icone) is None
        )
        self.assertEqual([], faltando, "ação com ícone que não existe")
        self.assertIsNotNone(icones.tracos_de(barra_da_sala.ICONE_DO_MAIS))

    def test_nenhum_traco_da_sala_e_orfao(self) -> None:
        usados = {r.icone for r in barra_da_sala.ACOES} | {barra_da_sala.ICONE_DO_MAIS}
        self.assertEqual([], sorted(set(icones.ICONES_DA_SALA) - usados))

    def test_os_tracos_da_sala_nao_repetem_chave_do_catalogo(self) -> None:
        """Uma chave nos dois dicionários faria `tracos_de` responder pelo primeiro em silêncio."""
        self.assertEqual(set(), set(icones.ICONES) & set(icones.ICONES_DA_SALA))

    def test_todo_traco_da_sala_cabe_na_caixa(self) -> None:
        fora = []
        for nome, tracos in icones.ICONES_DA_SALA.items():
            self.assertTrue(tracos, f"{nome} sem traço")
            for traco in tracos:
                x0, y0, x1, y1 = traco.limites()
                if min(x0, y0) < 0 or max(x1, y1) > icones.LADO_DA_CAIXA:
                    fora.append(f"{nome}: {traco!r}")
        self.assertEqual([], fora, "traço que vaza a caixa desenha cortado")

    def test_o_traco_da_sala_desenha(self) -> None:
        for nome in icones.ICONES_DA_SALA:
            with self.subTest(icone=nome):
                desenho = icones.imagem(nome, 16, "#101010")
                assert desenho is not None
                self.assertTrue(any(desenho.getpixel((x, y))[3] > 0 for x in range(16) for y in range(16)))

    def test_o_catalogo_continua_sem_icone_para_a_sala(self) -> None:
        """É a decisão do item: `medidas_da_fita.grupos()` põe na fita da janela todo comando com
        `icone`, e os da sala não agem lá. Só os quatro de navegação (S-520) têm ícone no catálogo."""
        com_icone = sorted(
            r.acao for r in comandos.do_grupo(comandos.ESTUDO) if r.icone
        )
        self.assertEqual(sorted(barra_da_sala.NAVEGACAO), com_icone)


class ModoTests(unittest.TestCase):
    """O que não é do momento fica cinza, e a regra é enunciável."""

    def test_os_tres_modos(self) -> None:
        self.assertEqual(barra_da_sala.SEM_ESTUDO, barra_da_sala.modo(vazio=True, treinando=False))
        self.assertEqual(barra_da_sala.COM_ESTUDO, barra_da_sala.modo(vazio=False, treinando=False))
        self.assertEqual(barra_da_sala.TREINANDO, barra_da_sala.modo(vazio=False, treinando=True))
        self.assertEqual(barra_da_sala.TREINANDO, barra_da_sala.modo(vazio=True, treinando=True))

    def test_sem_estudo_variante_e_exportar_desligam(self) -> None:
        """Não há árvore para editar nem estudo para exportar; o botão diz isso em vez de o rodapé."""
        self.assertEqual(
            {barra_da_sala.VARIANTE, barra_da_sala.EXPORTAR},
            set(barra_da_sala.grupos_desligados(barra_da_sala.SEM_ESTUDO)),
        )

    def test_com_estudo_nada_desliga_e_treinando_so_a_variante(self) -> None:
        self.assertEqual(frozenset(), barra_da_sala.grupos_desligados(barra_da_sala.COM_ESTUDO))
        self.assertEqual({barra_da_sala.VARIANTE}, set(barra_da_sala.grupos_desligados(barra_da_sala.TREINANDO)))

    def test_posicao_e_treino_nunca_desligam(self) -> None:
        """Carregar outro diagrama e parar o treino são as saídas de qualquer modo."""
        for qual in barra_da_sala.MODOS:
            with self.subTest(modo=qual):
                desligados = barra_da_sala.grupos_desligados(qual)
                self.assertNotIn(barra_da_sala.POSICAO, desligados)
                self.assertNotIn(barra_da_sala.TREINO, desligados)

    def test_modo_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            barra_da_sala.grupos_desligados("dormindo")


class CabemTests(unittest.TestCase):
    """A conta de quem fica na fila. É a S-151 sem quebrar: o que não cabe vai para o "Mais"."""

    def itens(self) -> list[barra_da_sala.Item]:
        item = barra_da_sala.Item
        return [item(100, 1, "a"), item(100, 3, "a"), item(100, 2, "b"), item(100, 4, "c")]

    def test_tudo_cabe_quando_ha_largura(self) -> None:
        dentro = barra_da_sala.cabem(self.itens(), 1000, reserva=50, espaco=2, separador=1)
        self.assertEqual({0, 1, 2, 3}, set(dentro))

    def test_sai_primeiro_quem_tem_menor_prioridade(self) -> None:
        """Prioridade 1 fica; 4 sai primeiro; e a resposta é um prefixo da ordem de prioridade."""
        # 3 itens: 300 + 3*2 (vãos) + 1 separador (a|b) + 2 + 50 (Mais) = 359
        dentro = barra_da_sala.cabem(self.itens(), 360, reserva=50, espaco=2, separador=1)
        self.assertEqual({0, 1, 2}, set(dentro), "os três de maior prioridade")
        # 2 itens de grupos diferentes: 200 + 2*2 + (1 + 2) + 50 = 257.
        dentro = barra_da_sala.cabem(self.itens(), 257, reserva=50, espaco=2, separador=1)
        self.assertEqual({0, 2}, set(dentro), "1 e 2 ficam, 3 e 4 vão para o Mais")
        dentro = barra_da_sala.cabem(self.itens(), 256, reserva=50, espaco=2, separador=1)
        self.assertEqual({0}, set(dentro), "um pixel a menos, e o segundo grupo inteiro vai para o Mais")

    def test_o_mais_nunca_sai(self) -> None:
        """A reserva entra na conta antes do primeiro item: com menos largura que ela, ninguém cabe."""
        self.assertEqual(frozenset(), barra_da_sala.cabem(self.itens(), 40, reserva=50, espaco=2, separador=1))
        self.assertEqual(frozenset(), barra_da_sala.cabem([], 1000, reserva=50, espaco=2, separador=1))

    def test_o_separador_entra_na_conta(self) -> None:
        """Dois itens de grupos diferentes pedem um separador a mais que dois do mesmo grupo."""
        item = barra_da_sala.Item
        mesmo = [item(100, 1, "a"), item(100, 2, "a")]
        outro = [item(100, 1, "a"), item(100, 2, "b")]
        # 200 + 2*2 + 50 = 254 cabe em 254 para o mesmo grupo; o outro pede 254 + 1 + 2 = 257.
        self.assertEqual({0, 1}, set(barra_da_sala.cabem(mesmo, 254, reserva=50, espaco=2, separador=1)))
        self.assertEqual({0}, set(barra_da_sala.cabem(outro, 254, reserva=50, espaco=2, separador=1)))
        self.assertEqual({0, 1}, set(barra_da_sala.cabem(outro, 257, reserva=50, espaco=2, separador=1)))

    def test_e_um_prefixo_e_nao_um_encaixe(self) -> None:
        """Um item menos prioritário e mais estreito **não** pula na frente de um que não coube:
        a resposta tem de ser enunciável -- "os n de maior prioridade" -- e não mudar de forma a
        cada pixel."""
        item = barra_da_sala.Item
        itens = [item(200, 1, "a"), item(200, 2, "a"), item(20, 3, "a")]
        # Cabem 200 + 2 + 50 = 252; o segundo (200) não cabe; o terceiro (20) caberia, e não entra.
        self.assertEqual({0}, set(barra_da_sala.cabem(itens, 300, reserva=50, espaco=2, separador=1)))


class PurezaTests(unittest.TestCase):
    def test_o_modulo_nao_importa_toolkit(self) -> None:
        arvore = ast.parse(Path(barra_da_sala.__file__).read_text(encoding="utf-8"))
        nomes = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
        nomes |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
        self.assertEqual(set(), nomes & {"PyQt6", "tkinter"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
