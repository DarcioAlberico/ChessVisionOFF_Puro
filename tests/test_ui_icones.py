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

    def test_sao_vinte_e_dois_e_a_conta_diz_de_onde_veio_cada_um(self) -> None:
        """Quatro da Imagem 1 e treze da Imagem 2; a união, restrita ao que existia, dava treze.

        O décimo quarto é `diagrama_anterior`, que a Imagem 1 não desenha -- uma seta que só
        existe num sentido deixa metade do grupo de fita sem ícone (S-228).

        Os três seguintes são os que a Imagem 2 pedia e o programa não tinha: a S-229 criou
        Desfazer, Refazer e Limpar, e só então o ícone deles deixou de ser arte órfã.

        **Os três últimos são do F9-C6, e eles fecham um defeito medido.** `tirar_caixa`,
        `pagina_anterior` e `proxima_pagina` eram botões só-de-ícone **sem desenho**: o
        `_vestir_de_icone` caía no glifo de texto de `ui/strings.py`, e o crítico do ciclo 5
        mediu o resultado na captura -- o `×` desenhava uma caixa de glifo de **4×5 px dentro de
        um botão de 26 px**, um nono da massa visual do vizinho na mesma fila do visor.

        **Os dois últimos são do F9-C7 (§4.7), e fecham o mesmo defeito nos outros painéis.** A
        varredura do ciclo 6 lia `j.pdf.findChildren` -- a barra do visor e mais nada --, e na
        janela inteira sobravam **onze** glifos de texto fazendo papel de ícone, com caixas de
        tinta de 5x3 a 9x12 px. `inicio_da_linha` e `fim_da_linha` são os dois desenhos que
        faltavam (`|<` e `>|`, primeiro e último); os outros nove botões passaram a usar
        desenhos que já existiam -- `diagrama_anterior` e `proximo_diagrama` chegaram a **quatro**
        comandos, e é por isso que a conta de ícones sobe 2 enquanto a de botões vestidos sobe 11.

        **As mesmas duas chaves nasceram também na sala de estudo** (S-520), e lá a razão não era
        estética: `⏮` e `⏭` não existem na fonte da interface -- `QFontMetrics.inFont` responde
        `False` para os quatro glifos de navegação em Segoe UI --, então o botão desenhava com uma
        fonte de queda, que não é a da janela. Os dois lados chegaram às mesmas duas chaves, e por
        isso elas contam uma vez só. `lance_anterior` e `proximo_lance` **não** ganharam desenho
        próprio: apontam para as setas que já existiam, e são o primeiro caso do que o cabeçalho de
        `ICONES` previa -- dois comandos na mesma chave.
        """
        self.assertEqual(22, len(icones.ICONES))
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
        for nome in ("tirar_caixa", "pagina_anterior", "proxima_pagina"):
            with self.subTest(icone=nome):
                self.assertIn(nome, icones.ICONES)
                self.assertEqual(nome, comandos.comando(nome).icone)


class GradeUnicaTests(unittest.TestCase):
    """**Um peso de traço já havia; faltava uma extensão** (F9-C6, item 4).

    O crítico do ciclo 5 mediu os botões só-de-ícone da barra do visor e achou **cinco caixas de
    glifo diferentes** -- 11×11, 12×12, 12×14, 14×10, 14×12 --, porque cada desenho declarava a
    sua própria extensão dentro do `0..100`: a lupa de 16 a 88, a folha de 10 a 90, as paredes
    do "ajustar à largura" de 22 a 78 na vertical. Um ícone saía 27 % maior que o vizinho ao
    lado dele.

    `na_grade` põe todos na mesma extensão, isotropicamente. O que sobra de diferença entre as
    caixas é a **proporção da forma** -- uma seta é mais estreita que um quadrado --, e essa
    diferença é o desenho, não a grade.
    """

    def test_todo_icone_enche_a_caixa_no_lado_maior(self) -> None:
        for nome, tracos in icones.ICONES.items():
            with self.subTest(icone=nome):
                x0, y0, x1, y1 = icones.caixa_dos_tracos(icones.na_grade(tracos))
                maior = max(x1 - x0, y1 - y0)
                self.assertAlmostEqual(icones.LADO_DA_CAIXA, maior, places=6)
                self.assertGreaterEqual(min(x0, y0), -1e-6)
                self.assertLessEqual(max(x1, y1), icones.LADO_DA_CAIXA + 1e-6)

    def test_a_grade_e_centrada_e_isotropica(self) -> None:
        """Centrada: a folga do lado curto é a mesma dos dois lados. Isotrópica: a proporção fica.

        Sem a segunda metade, "grade única" viraria esticar cada desenho até o quadrado -- e a
        seta da página anterior sairia gorda.
        """
        for nome, tracos in icones.ICONES.items():
            with self.subTest(icone=nome):
                ax0, ay0, ax1, ay1 = icones.caixa_dos_tracos(tracos)
                dx0, dy0, dx1, dy1 = icones.caixa_dos_tracos(icones.na_grade(tracos))
                antes = (ax1 - ax0) / max(1e-9, ay1 - ay0)
                depois = (dx1 - dx0) / max(1e-9, dy1 - dy0)
                self.assertAlmostEqual(antes, depois, places=6)
                self.assertAlmostEqual(dx0, icones.LADO_DA_CAIXA - dx1, places=6)
                self.assertAlmostEqual(dy0, icones.LADO_DA_CAIXA - dy1, places=6)

    def test_as_marcas_ficam_fora_da_grade(self) -> None:
        """O visto e o traço do indeterminado são de tamanhos diferentes **de propósito**.

        *"Ele é horizontal e mais curto que o visto é largo"* -- é a WCAG 1.4.1 que o ciclo 1
        cobrou: duas marcas que só a matiz separasse seriam dois quadrados iguais no papel.
        Normalizá-las desfaria o conserto, e por isso `imagem` só passa `ICONES` por `na_grade`.
        """
        visto = icones.imagem(icones.MARCA_VISTO, 48, PRETO)
        traco = icones.imagem(icones.MARCA_TRACO, 48, PRETO)
        assert visto is not None and traco is not None
        self.assertNotEqual(visto.getchannel("A").getbbox(), traco.getchannel("A").getbbox())

    def test_o_desenho_sai_maior_do_que_saia_antes(self) -> None:
        """A grade não é só uniformidade: ela devolve os pixels que a declaração estreita perdia.

        `zoom_mais` ia de 16 a 88 na caixa de 100 -- **72 %** do que o botão lhe dava.
        """
        posto = icones.na_grade(icones.ICONES["zoom_mais"])
        x0, y0, x1, y1 = icones.caixa_dos_tracos(posto)
        antes = icones.caixa_dos_tracos(icones.ICONES["zoom_mais"])
        self.assertGreater((x1 - x0), (antes[2] - antes[0]))

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


class UmaGradeSoNaBarraDoVisorTests(unittest.TestCase):
    """Os botões só-de-ícone da barra do visor vêm todos da mesma grade óptica (F9-C6, item 4).

    **O defeito medido pelo crítico do ciclo 5, na captura:** sete botões só-de-ícone,
    **cinco caixas de glifo** (14×10, 14×8, 12×14, 12×12, 11×11) e tinta de 30,6 % a 65,7 % --
    *"traço fino e sólido lado a lado, e um 'ícone' de 4×5 px num botão de 26 px"*. Carta §3.3,
    *"ícones de origens diferentes misturados (peso, estilo, grade)"*.

    Três coisas passam a ser afirmadas aqui, e as três eram falsas: todo botão só-de-ícone da
    barra tem **desenho declarado** (três caíam no caractere de texto), todo desenho enche a
    grade no lado maior, e a caixa de glifo dos nove é **quadrada** -- é ela que decide o tamanho
    óptico que o olho compara na fila.
    """

    SO_DE_ICONE = (
        "ler_pagina",
        "tirar_caixa",
        "selecionar_area",
        "pagina_anterior",
        "proxima_pagina",
        "zoom_menos",
        "zoom_mais",
        "ajustar_largura",
        "ajustar_pagina",
    )

    def test_todo_botao_so_de_icone_da_barra_tem_desenho(self) -> None:
        """Sem desenho, `qt/painel_do_pdf._vestir_de_icone` cai no glifo de texto -- 4×5 px."""
        sem_desenho = [nome for nome in self.SO_DE_ICONE if not comandos.comando(nome).icone]
        self.assertEqual([], sem_desenho)

    def test_os_nove_partilham_a_mesma_caixa_de_glifo(self) -> None:
        """Quadrada e do mesmo tamanho: é o que faz um ícone não sair maior que o vizinho.

        A tolerância é de uma unidade em cem -- meio pixel a 16 px --, e não zero, porque as
        coordenadas são declaradas em números redondos e a normalização é aritmética de ponto
        flutuante.
        """
        for nome in self.SO_DE_ICONE:
            with self.subTest(icone=nome):
                x0, y0, x1, y1 = icones.caixa_dos_tracos(icones.na_grade(icones.ICONES[nome]))
                self.assertAlmostEqual(x1 - x0, y1 - y0, delta=1.0)
                self.assertAlmostEqual(icones.LADO_DA_CAIXA, x1 - x0, delta=1.0)

    def test_a_seta_de_pagina_nao_e_a_seta_de_diagrama(self) -> None:
        """Duas famílias de seta na mesma janela, e a proporção é o que as separa.

        A de **página** é larga e fechada (lê como o `◀` que ela substituiu); a de **diagrama**
        é estreita e alta. Iguais, seriam dois botões que a pessoa clica para descobrir qual é
        qual -- a mesma razão pela qual `limpar_tabuleiro` não reusa o traço de `apagar_casa`.
        """
        for pagina, diagrama in (
            ("pagina_anterior", "diagrama_anterior"),
            ("proxima_pagina", "proximo_diagrama"),
        ):
            with self.subTest(par=(pagina, diagrama)):
                self.assertNotEqual(icones.ICONES[pagina], icones.ICONES[diagrama])
                px0, py0, px1, py1 = icones.caixa_dos_tracos(icones.ICONES[pagina])
                dx0, dy0, dx1, dy1 = icones.caixa_dos_tracos(icones.ICONES[diagrama])
                self.assertGreater(
                    (px1 - px0) / (py1 - py0),
                    (dx1 - dx0) / (dy1 - dy0),
                    "a seta de página deixou de ser mais larga que a de diagrama",
                )
