"""O ícone declarado como traço, e a ponte dele com o catálogo de comandos (S-220).

Não havia um único ícone no repositório -- `assets/` tem 12 PNGs de peça e um `.ico` --, e as duas
propostas de interface são dirigidas a ícone. O que este item recusa é a saída óbvia: um conjunto
de PNG resolveria a Imagem 2 e quebraria a Imagem 1, porque traço escuro sobre cromo escuro some.
É o defeito que a S-146 mediu no tabuleiro, e `PieceImages.icon` já o documenta nas peças.

A forma é declarada numa caixa `0..100` e a cor vem de quem desenha. Tudo aqui se afirma sem
abrir janela: o módulo desenha em PIL, e a última perna para o toolkit é de `qt/icones.py`.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui import comandos, icones

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

    def test_sao_dezenove_e_a_conta_e_das_duas_imagens_mais_a_sala(self) -> None:
        """Quatro da Imagem 1 e treze da Imagem 2; a união, restrita ao que existia, dava treze.

        O décimo quarto é `diagrama_anterior`, que a Imagem 1 não desenha -- uma seta que só
        existe num sentido deixa metade do grupo de fita sem ícone (S-228).

        Os três seguintes são os que a Imagem 2 pedia e o programa não tinha: a S-229 criou
        Desfazer, Refazer e Limpar, e só então o ícone deles deixou de ser arte órfã.

        **Os dois últimos são as pontas da linha da sala** (S-520), e a razão deles não é estética:
        `⏮` e `⏭` não existem na fonte da interface -- `QFontMetrics.inFont` responde `False` para
        os quatro glifos de navegação em Segoe UI --, então o botão desenhava com uma fonte de
        queda, que não é a da janela. `lance_anterior` e `proximo_lance` **não** ganharam desenho
        próprio: apontam para as setas que já existiam, e são o primeiro caso do que o cabeçalho de
        `ICONES` previa -- dois comandos na mesma chave.
        """
        self.assertEqual(19, len(icones.ICONES))
        for nome in ("inicio_da_linha", "fim_da_linha"):
            with self.subTest(icone=nome):
                self.assertIn(nome, icones.ICONES)
                self.assertEqual(nome, comandos.comando(nome).icone)
        self.assertEqual("diagrama_anterior", comandos.comando("lance_anterior").icone)
        self.assertEqual("proximo_diagrama", comandos.comando("proximo_lance").icone)
        for nome in ("desfazer", "refazer", "limpar_tabuleiro"):
            with self.subTest(icone=nome):
                self.assertIn(nome, icones.ICONES)
                self.assertEqual(nome, comandos.comando(nome).icone)

    def test_limpar_nao_reusa_o_traco_do_apagar_casa(self) -> None:
        """Os dois ficam lado a lado no grupo Edição da fita, e apagam coisas diferentes: um
        limpa **uma casa** e o outro esvazia a posição. Dois botões com o mesmo desenho seriam
        dois botões que a pessoa tem de clicar para descobrir qual é qual."""
        self.assertNotEqual(icones.ICONES["apagar_casa"], icones.ICONES["limpar_tabuleiro"])


class LegibilidadeNoTamanhoDeUsoTests(unittest.TestCase):
    """Os três traços que o crítico não distinguiu a 20 px (S-554, terceira rodada).

    **Um ícone que só se lê a 96 px não é um ícone**: a fita e a barra da sala desenham a 16 e a
    20, e é nesse tamanho que a diferença tem de existir.
    """

    TAMANHOS = (16, 20, 24)
    """Os três em que a janela pede ícone hoje. `LADO_DO_ICONE_DA_SALA` é 16; a navegação da sala
    pede o dobro; a fita pede 20."""

    def alfa(self, nome: str, lado: int) -> list[int]:
        desenho = icones.imagem(nome, lado, PRETO)
        assert desenho is not None
        return list(desenho.convert("RGBA").getchannel("A").get_flattened_data())

    def test_desfazer_e_refazer_se_distinguem_no_tamanho_de_uso(self) -> None:
        """**O que o crítico mediu**: a 20 px os dois eram "dois rabiscos quase iguais". O arco é
        o mesmo nos dois de propósito -- é o mesmo gesto em sentidos opostos --, e a única coisa
        que dizia o sentido era uma cotovelada de três segmentos que o antialias comia: **24 px de
        50 de traço**, 48%. Com a ponta de seta fechada, passa de 80% em todos os três tamanhos.
        """
        for lado in self.TAMANHOS:
            um, outro = self.alfa("desfazer", lado), self.alfa("refazer", lado)
            traco = sum(1 for valor in um if valor > 32)
            difere = sum(1 for a, b in zip(um, outro, strict=True) if abs(a - b) > 32)
            with self.subTest(lado=lado):
                self.assertGreater(traco, 0, "o ícone saiu sem traço nenhum: nada foi medido")
                self.assertGreater(
                    difere / traco, 0.8, f"a {lado} px os dois desenham quase o mesmo: {difere}/{traco}"
                )

    def test_limpar_tabuleiro_nao_e_um_retangulo_com_linhas_de_texto(self) -> None:
        """**O crítico leu o ícone como "lista de texto"**, e com razão: três traços horizontais
        paralelos ao lado de um retângulo é o que qualquer programa desenha para parágrafo. Eles
        queriam dizer movimento. A régua é a forma declarada, e não o pixel: nenhum par de traços
        deste ícone pode ser dois segmentos horizontais paralelos de mesmo comprimento.
        """
        horizontais = [
            traco
            for traco in icones.ICONES["limpar_tabuleiro"]
            if isinstance(traco, icones.Poli)
            and len(traco.pontos) == 2
            and traco.pontos[0][1] == traco.pontos[1][1]
        ]
        self.assertLessEqual(
            len(horizontais), 1, "voltaram os traços paralelos que se leem como linhas de texto"
        )

    def test_a_ponta_de_seta_e_fechada_nos_tres(self) -> None:
        """A mesma ponta nos três: um vocabulário e não três desenhos parecidos (S-501)."""
        for nome in ("desfazer", "refazer", "limpar_tabuleiro"):
            pontas = [
                traco
                for traco in icones.ICONES[nome]
                if isinstance(traco, icones.Poli) and traco.fechado and len(traco.pontos) == 3
            ]
            with self.subTest(icone=nome):
                self.assertEqual(1, len(pontas), "o ícone não tem uma ponta de seta fechada")


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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
