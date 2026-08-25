"""O ícone declarado como traço, e a ponte dele com o catálogo de comandos (S-220).

Não havia um único ícone no repositório -- `assets/` tem 12 PNGs de peça e um `.ico` --, e as duas
propostas de interface são dirigidas a ícone. O que este item recusa é a saída óbvia: um conjunto
de PNG resolveria a Imagem 2 e quebraria a Imagem 1, porque traço escuro sobre cromo escuro some.
É o defeito que a S-146 mediu no tabuleiro, e `PieceImages.icon` já o documenta nas peças.

A forma é declarada numa caixa `0..100` e a cor vem de quem desenha. Quase tudo aqui se afirma
sem abrir janela: só o cache e o tamanho entregue precisam de um `Tk`, porque `ImageTk.PhotoImage`
precisa.
"""

from __future__ import annotations

import unittest

from tk_root import raiz

from chess_diagram_ocr.ui import comandos, degradacao, icones

PRETO = "#101010"
BRANCO = "#f0f0f0"


class PonteComOCatalogoTests(unittest.TestCase):
    """Nos dois sentidos: comando apontando para nada, e traço que ninguém usa."""

    def test_todo_comando_com_icone_tem_traco(self) -> None:
        faltando = sorted(
            registro.icone for registro in comandos.CATALOGO if registro.icone and registro.icone not in icones.ICONES
        )
        self.assertEqual([], faltando, "comando que declara ícone que não existe")

    def test_nenhum_icone_orfao(self) -> None:
        """Traço desenhado que nenhum comando pede é arte que ninguém vê e que ninguém apaga."""
        usados = {registro.icone for registro in comandos.CATALOGO if registro.icone}
        self.assertEqual([], sorted(set(icones.ICONES) - usados))

    def test_sao_dezessete_e_a_conta_e_das_duas_imagens(self) -> None:
        """Quatro da Imagem 1 e treze da Imagem 2; a união, restrita ao que existia, dava treze.

        O décimo quarto é `diagrama_anterior`, que a Imagem 1 não desenha -- uma seta que só
        existe num sentido deixa metade do grupo de fita sem ícone (S-228).

        Os três últimos são os que a Imagem 2 pedia e o programa não tinha: a S-229 criou
        Desfazer, Refazer e Limpar, e só então o ícone deles deixou de ser arte órfã.
        """
        self.assertEqual(17, len(icones.ICONES))
        for nome in ("desfazer", "refazer", "limpar_tabuleiro"):
            with self.subTest(icone=nome):
                self.assertIn(nome, icones.ICONES)
                self.assertEqual(nome, comandos.comando(nome).icone)

    def test_limpar_nao_reusa_o_traco_do_apagar_casa(self) -> None:
        """Os dois ficam lado a lado no grupo Edição da fita, e apagam coisas diferentes: um
        limpa **uma casa** e o outro esvazia a posição. Dois botões com o mesmo desenho seriam
        dois botões que a pessoa tem de clicar para descobrir qual é qual."""
        self.assertNotEqual(icones.ICONES["apagar_casa"], icones.ICONES["limpar_tabuleiro"])


class GeometriaTests(unittest.TestCase):
    """A caixa `0..100` é o contrato entre quem declara a forma e quem a desenha."""

    def test_todo_traco_cabe_na_caixa(self) -> None:
        fora = []
        for nome, tracos in icones.ICONES.items():
            for traco in tracos:
                x0, y0, x1, y1 = traco.limites()
                if min(x0, y0) < 0 or max(x1, y1) > icones.LADO_DA_CAIXA:
                    fora.append(f"{nome}: {traco!r}")
        self.assertEqual([], fora, "traço que vaza a caixa desenha cortado")

    def test_todo_icone_tem_ao_menos_um_traco(self) -> None:
        vazios = [nome for nome, tracos in icones.ICONES.items() if not tracos]
        self.assertEqual([], vazios)

    def test_poli_recusa_um_ponto_so(self) -> None:
        """Um ponto não é um segmento, e a Pillow desenharia nada em silêncio."""
        with self.assertRaises(ValueError):
            icones.Poli((50, 50))

    def test_o_traco_na_borda_da_caixa_nao_sai_da_imagem(self) -> None:
        """A razão de a caixa encolher pela espessura, e o que acontece sem isso.

        O traço é centrado no caminho: sem o encolhimento, um ponto em `0` desenharia metade
        fora da imagem e o ícone sairia com o lado de cima mais fino que o de baixo --
        assimetria que ninguém atribui à escala, porque não parece recorte, parece desenho ruim.

        **A folga de 5% é do rasterizador, e não do cálculo.** A espessura em pixel costuma ser
        ímpar, e a `ImageDraw` reparte o pixel do meio para um lado só; medido a 48 px, os quatro
        lados ficam a 3% uns dos outros. Exigir igualdade cravaria o arredondamento da Pillow.
        """
        icones.ICONES["_borda"] = (icones.Poli((0, 0), (100, 0), (100, 100), (0, 100), fechado=True),)
        self.addCleanup(icones.ICONES.pop, "_borda")

        lado = 48
        desenho = icones.imagem("_borda", lado, PRETO)
        assert desenho is not None
        alfa = desenho.getchannel("A")
        bordas = {
            "topo": sum(alfa.getpixel((x, 0)) for x in range(lado)),
            "base": sum(alfa.getpixel((x, lado - 1)) for x in range(lado)),
            "esquerda": sum(alfa.getpixel((0, y)) for y in range(lado)),
            "direita": sum(alfa.getpixel((lado - 1, y)) for y in range(lado)),
        }
        for onde, tinta in bordas.items():
            with self.subTest(borda=onde):
                self.assertGreater(tinta, 0, f"a borda {onde} foi cortada inteira")
        self.assertLessEqual(
            (max(bordas.values()) - min(bordas.values())) / max(bordas.values()),
            0.05,
            f"um lado saiu bem mais grosso que o outro: {bordas}",
        )


class CorDoChamadorTests(unittest.TestCase):
    """O item inteiro: nenhum ícone tem cor própria, e por isso os catorze servem às três peles."""

    def test_o_traco_sai_na_cor_pedida(self) -> None:
        for pedida in (PRETO, BRANCO):
            with self.subTest(cor=pedida):
                desenho = icones.imagem("aplicar_fen", 32, pedida)
                assert desenho is not None
                opacos = [
                    desenho.getpixel((x, y))[:3]
                    for x in range(32)
                    for y in range(32)
                    if desenho.getpixel((x, y))[3] > 250
                ]
                self.assertTrue(opacos, "o ícone não desenhou nada")
                esperado = tuple(int(pedida[i : i + 2], 16) for i in (1, 3, 5))
                self.assertEqual({esperado}, set(opacos))

    def test_a_mesma_forma_em_duas_cores_sao_dois_desenhos(self) -> None:
        """Se a cor entrasse no desenho e não no chamador, isto seria a mesma imagem."""
        claro = icones.imagem("salvar", 24, BRANCO)
        escuro = icones.imagem("salvar", 24, PRETO)
        assert claro is not None and escuro is not None
        self.assertNotEqual(claro.tobytes(), escuro.tobytes())


class DesenhoNoTkTests(unittest.TestCase):
    """O que precisa de interpretador Tcl vivo: `ImageTk.PhotoImage` e o cache dele."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        icones.limpar_cache()
        self.addCleanup(icones.limpar_cache)

    def test_o_tamanho_pedido_e_o_entregue(self) -> None:
        """Exato, e não "aproximadamente": a fita da S-228 tem orçamento de altura em pixel."""
        for tamanho in (16, 20, 24, 32, 48):
            with self.subTest(tamanho=tamanho):
                foto = icones.icone("abrir_pdf", tamanho, PRETO)
                assert foto is not None
                self.assertEqual((tamanho, tamanho), (foto.width(), foto.height()))

    def test_o_cache_devolve_o_mesmo_objeto(self) -> None:
        """Não é só economia: a fita redesenha treze ícones a cada mudança de densidade.

        E há a razão do Tk: uma `PhotoImage` sem referência viva é recolhida, e o widget fica
        com um nome de imagem que o interpretador não conhece mais.
        """
        primeiro = icones.icone("salvar", 24, PRETO)
        segundo = icones.icone("salvar", 24, PRETO)
        self.assertIs(primeiro, segundo)
        self.assertEqual(1, icones.cache_de_icones())

    def test_trocar_a_cor_ou_o_tamanho_devolve_outro(self) -> None:
        base = icones.icone("salvar", 24, PRETO)
        self.assertIsNot(base, icones.icone("salvar", 24, BRANCO))
        self.assertIsNot(base, icones.icone("salvar", 32, PRETO))
        self.assertEqual(3, icones.cache_de_icones())

    def test_limpar_cache_esquece_tudo(self) -> None:
        """A troca de pele (S-222) chama isto, porque a cor do cromo mudou."""
        icones.icone("salvar", 24, PRETO)
        icones.limpar_cache()
        self.assertEqual(0, icones.cache_de_icones())

    def test_icone_desconhecido_nao_levanta(self) -> None:
        """Regra 4: nem ícone que não desenhou pode impedir a janela de abrir.

        Devolve `None` e registra -- ao contrário de `tokens.cor` e `estilos.estilo_de_botao`,
        que levantam. A diferença é o que acontece depois: papel de botão errado desenha um botão
        que mente sobre a própria importância; ícone que falta desenha um botão só com texto,
        que é legível.
        """
        # O aviso é **uma vez por nome** desde a S-234, e este processo pode já ter avisado
        # este: sem zerar, o `assertLogs` mediria o silêncio correto e reprovaria.
        degradacao.esquecer_avisos()
        with self.assertLogs(icones.logger, level="WARNING") as registro:
            self.assertIsNone(icones.icone("nao_existe", 24, PRETO))
        self.assertIn("nao_existe", "\n".join(registro.output))
        self.assertEqual(0, icones.cache_de_icones(), "o que não desenhou não entra no cache")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
