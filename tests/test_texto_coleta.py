"""A coleta em quarentena: o modelo diz onde é fraco, e um humano fica no meio (S-214).

**O teste que mais importa aqui é negativo**: nada é gravado na base de treino por este caminho.
As duas pontas deste projeto têm a cicatriz de rótulo do modelo virando verdade -- 127 amostras
treinando a classe errada por meses --, e a garantia não é lembrar de não fazer: é `coletar` não
receber o caminho da base. O teste afirma isso sobre o disco.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import numpy as np

from chess_diagram_ocr.atomic_io import read_image
from chess_diagram_ocr.text import coleta
from chess_diagram_ocr.text import procedencia as _procedencia
from chess_diagram_ocr.text.coleta import (
    LADO,
    PASTA_PADRAO,
    TETO_PADRAO,
    Recorte,
    coletar,
    promover,
)


def imagem(semente: int) -> np.ndarray:
    """Um recorte 32x32 achatado, distinto para cada semente."""
    return np.random.default_rng(semente).integers(0, 255, LADO * LADO, dtype=np.uint8)


def recorte(
    semente: int,
    *,
    palpite: str = "o",
    confianca: float = 0.2,
    pagina: int = 1,
    livro: str = "Kemeri",
) -> Recorte:
    return Recorte(imagem(semente), palpite=palpite, confianca=confianca, livro=livro, pagina=pagina)


class NomeTests(unittest.TestCase):
    def test_o_nome_do_arquivo_ordena_por_confianca(self) -> None:
        """Lá o nome trazia página e confiança nessa ordem, e o Explorer ordenava por página."""
        nomes = sorted(
            recorte(n, confianca=c, pagina=p).nome()
            for n, (c, p) in enumerate(((0.9, 1), (0.1, 200), (0.5, 90)))
        )
        self.assertEqual([100, 500, 900], [int(nome.split("_")[0]) for nome in nomes])

    def test_a_confianca_cabe_em_quatro_digitos_com_zeros_a_esquerda(self) -> None:
        """Sem os zeros, `900` viria antes de `100` na ordem alfabética."""
        self.assertTrue(recorte(0, confianca=0.05).nome().startswith("0050_"))

    def test_a_confianca_fora_de_zero_um_nao_estoura_o_nome(self) -> None:
        for valor in (-1.0, 0.0, 1.0, 2.5):
            with self.subTest(confianca=valor):
                self.assertTrue(recorte(0, confianca=valor).nome().split("_")[0].isdigit())

    def test_o_nome_do_livro_com_virgula_e_barra_nao_quebra_o_arquivo(self) -> None:
        nome = recorte(0, livro="1001 Winning, Chess/Sacrifices").nome()
        self.assertNotIn("/", nome)
        self.assertNotIn(",", nome)

    def test_a_pasta_e_o_palpite_pela_regua_da_S180(self) -> None:
        self.assertEqual("lower_o", recorte(0, palpite="o").pasta)
        self.assertEqual("upper_O", recorte(0, palpite="O").pasta)


class ColetaTests(unittest.TestCase):
    def test_a_coleta_nunca_grava_na_base_de_treino(self) -> None:
        """A garantia é a função não ter o argumento; o teste é sobre o disco."""
        with TemporaryDirectory() as raiz:
            base = Path(raiz) / "training_data"
            (base / "lower_o").mkdir(parents=True)
            antes = sorted(p.name for p in base.rglob("*"))
            coletar([recorte(n) for n in range(5)], Path(raiz) / "revisao_ocr")
            self.assertEqual(antes, sorted(p.name for p in base.rglob("*")))
            self.assertTrue((Path(raiz) / "revisao_ocr" / "lower_o").is_dir())

    def test_a_pasta_padrao_fica_fora_da_base_de_treino(self) -> None:
        """Uma subpasta de `training_data/` seria lida como classe por qualquer varredura."""
        self.assertNotIn("training_data", PASTA_PADRAO.parts)

    def test_grava_um_arquivo_por_recorte_na_pasta_do_palpite(self) -> None:
        with TemporaryDirectory() as raiz:
            destino = Path(raiz) / "q"
            relatorio = coletar(
                [recorte(0, palpite="o"), recorte(1, palpite="c"), recorte(2, palpite="o")], destino
            )
            self.assertEqual(3, relatorio.gravados)
            self.assertEqual({"lower_o": 2, "lower_c": 1}, relatorio.por_pasta)
            self.assertEqual(2, len(list((destino / "lower_o").glob("*.png"))))

    def test_a_copia_exata_entra_uma_vez_so(self) -> None:
        """Em PDF digital o mesmo glifo sai byte a byte igual, e a pasta enchia de cópias."""
        with TemporaryDirectory() as raiz:
            relatorio = coletar([recorte(0), recorte(0), recorte(0)], Path(raiz) / "q")
            self.assertEqual(1, relatorio.gravados)
            self.assertEqual(2, relatorio.repetidos_exatos)

    def test_a_quase_duplicata_tambem_e_recusada(self) -> None:
        """O mesmo glifo com meio pixel de deslocamento: o hash não vê, o descritor da S-202 vê."""
        base = imagem(0)
        quase = np.clip(base.astype(np.int16) + 1, 0, 255).astype(np.uint8)
        with TemporaryDirectory() as raiz:
            relatorio = coletar([Recorte(base, "o", 0.2), Recorte(quase, "o", 0.2)], Path(raiz) / "q")
            self.assertEqual(1, relatorio.gravados)
            self.assertEqual(1, relatorio.repetidos_parecidos)

    def test_a_quase_duplicata_so_vale_dentro_do_mesmo_palpite(self) -> None:
        """Duas imagens quase iguais com palpites diferentes são homóglifo, e é outro assunto."""
        base = imagem(0)
        quase = np.clip(base.astype(np.int16) + 1, 0, 255).astype(np.uint8)
        with TemporaryDirectory() as raiz:
            relatorio = coletar([Recorte(base, "o", 0.2), Recorte(quase, "c", 0.2)], Path(raiz) / "q")
            self.assertEqual(2, relatorio.gravados)

    def test_o_teto_sorteia_do_livro_inteiro(self) -> None:
        """Teto de 300 dava 300 amostras das páginas 1 a 5: uma fonte, um estado de scan.

        O teste não olha o código: olha a distribuição de páginas do que sobrou. Com 200 recortes
        espalhados por 200 páginas e teto de 20, guardar os primeiros deixaria a página máxima em
        20 -- e o sorteio de reservatório a leva bem além disso.
        """
        recortes = [recorte(n, pagina=n + 1) for n in range(200)]
        with TemporaryDirectory() as raiz:
            destino = Path(raiz) / "q"
            relatorio = coletar(recortes, destino, teto=20, semente=7)
            self.assertEqual(20, relatorio.gravados)
            paginas = sorted(
                int(p.stem.split("_")[-2][1:]) for p in (destino / "lower_o").glob("*.png")
            )
        self.assertGreater(max(paginas), 100, f"a amostra ficou nas primeiras páginas: {paginas}")
        self.assertGreater(len(set(paginas)), 10)

    def test_o_teto_e_por_palpite_e_nao_por_coleta(self) -> None:
        recortes = [recorte(n, palpite="o") for n in range(30)]
        recortes += [recorte(100 + n, palpite="c") for n in range(30)]
        with TemporaryDirectory() as raiz:
            relatorio = coletar(recortes, Path(raiz) / "q", teto=5)
            self.assertEqual({"lower_o": 5, "lower_c": 5}, relatorio.por_pasta)

    def test_o_teto_zero_nao_grava_nada(self) -> None:
        with TemporaryDirectory() as raiz:
            self.assertEqual(0, coletar([recorte(0)], Path(raiz) / "q", teto=0).gravados)

    def test_a_mesma_semente_da_a_mesma_amostra(self) -> None:
        """Duas varreduras do mesmo livro que dessem amostras diferentes não seriam comparáveis."""
        recortes = [recorte(n, pagina=n) for n in range(60)]
        with TemporaryDirectory() as raiz:
            um, dois = Path(raiz) / "a", Path(raiz) / "b"
            coletar(recortes, um, teto=10, semente=3)
            coletar(recortes, dois, teto=10, semente=3)
            self.assertEqual(
                sorted(p.name for p in (um / "lower_o").glob("*.png")),
                sorted(p.name for p in (dois / "lower_o").glob("*.png")),
            )

    def test_o_teto_padrao_e_trezentos(self) -> None:
        self.assertEqual(300, TETO_PADRAO)

    def test_coletar_nada_nao_cria_pasta(self) -> None:
        with TemporaryDirectory() as raiz:
            destino = Path(raiz) / "q"
            self.assertEqual(0, coletar([], destino).gravados)
            self.assertFalse(destino.exists())


class DestinoForaDaCodePageTests(unittest.TestCase):
    """A gravação da coleta, e a promessa de que o relatório não pode mentir (S-431).

    Era `cv2.imwrite`, que devolve `False` sem levantar. A linha seguinte somava
    `len(guardados)` sem olhar o retorno: o `Relatorio` dizia "5 gravado(s)" e o disco tinha zero
    PNG. O destino padrão é `PROJECT_ROOT / "revisao_ocr"`, então bastava a pasta do projeto --
    ou a do bundle que o usuário descompacta -- morar sob um nome com acento.

    **Os dois primeiros testes não dependem da máquina, e é de propósito.** Esta bancada roda com
    a code page ANSI em UTF-8 (`GetACP() == 65001`), e ali o `cv2.imwrite` grava cirílico sem
    reclamar: um teste que só afirmasse "gravados == PNGs no disco" passaria verde **antes e
    depois** da correção, que é a guarda vácua da S-296 outra vez. Então a afirmação é sobre o
    mecanismo -- quem grava, e o que acontece quando a gravação falha.

    O terceiro é o de ponta a ponta, e é o único que depende da code page: numa instalação de
    fábrica (ANSI em `cp1252`) ele é o teste de verdade, e aqui ele é de graça. Ninguém deve ler
    o verde dele como prova.
    """

    CIRILICO = "_Болеславский"
    """O livro russo do acervo, o mesmo que descobriu esta família de defeito na S-111. O acento
    mora na folha, então o teste não depende de onde o checkout está."""

    def test_a_gravacao_passa_pelo_atomic_io(self) -> None:
        """Uma vez por recorte guardado, e nenhuma por `cv2`."""
        with TemporaryDirectory() as raiz:
            destino = Path(raiz) / "revisao_ocr"
            with mock.patch.object(coleta, "write_image", wraps=coleta.write_image) as gravou:
                relatorio = coletar([recorte(n) for n in range(5)], destino)
        self.assertEqual(5, relatorio.gravados)
        self.assertEqual(5, gravou.call_count, "a coleta gravou por fora do atomic_io")

    def test_uma_gravacao_que_falha_nao_vira_relatorio(self) -> None:
        """O `write_image` levanta, e `coletar` propaga em vez de contar o que não foi ao disco.

        É a afirmação inteira do item: com `cv2.imwrite` a falha era um `False` descartado, e a
        função seguia somando. Aqui ela para -- e uma coleta que para vale mais que um relatório
        que mente.
        """
        with TemporaryDirectory() as raiz:
            destino = Path(raiz) / "revisao_ocr"
            with mock.patch.object(coleta, "write_image", side_effect=OSError("disco cheio")):
                with self.assertRaises(OSError):
                    coletar([recorte(n) for n in range(5)], destino)

    def test_o_recorte_volta_do_disco_com_o_conteudo_que_entrou(self) -> None:
        """Gravar o arquivo é menos que gravar a imagem: o round-trip é quem prova as duas.

        Este é o único dos três que depende da code page da máquina -- ver o docstring da classe.
        """
        entrou = recorte(7)
        with TemporaryDirectory() as raiz:
            destino = Path(raiz) / self.CIRILICO / "revisao_ocr"
            relatorio = coletar([entrou], destino)
            no_disco = sorted(destino.rglob("*.png"))
            self.assertEqual(relatorio.gravados, len(no_disco), "o relatório contou o que não foi ao disco")
            (gravado,) = no_disco
            voltou = read_image(gravado)
        self.assertIsNotNone(voltou, "o PNG não voltou do disco")
        assert voltou is not None
        esperado = np.asarray(entrou.imagem, np.uint8).reshape(LADO, LADO)
        np.testing.assert_array_equal(esperado, voltou[:, :, 0])


class PromocaoTests(unittest.TestCase):
    """A terceira etapa, e a que só acontece depois de a segunda -- humana -- ter acontecido."""

    def quarentena(self, raiz: Path) -> Path:
        """Uma quarentena com dois recortes: um na pasta do palpite, e um que a mão moveu."""
        pasta = raiz / "revisao_ocr"
        coletar([recorte(0, palpite="o", pagina=45), recorte(1, palpite="o", pagina=7)], pasta)
        movidos = sorted((pasta / "lower_o").glob("*.png"))
        destino = pasta / "lower_e"
        destino.mkdir()
        movidos[0].rename(destino / movidos[0].name)  # foi isto que a pessoa fez com o mouse
        return pasta

    def test_a_promocao_le_o_rotulo_da_pasta_e_nao_o_palpite(self) -> None:
        with TemporaryDirectory() as raiz:
            pasta = self.quarentena(Path(raiz))
            resultado = promover(pasta)
        self.assertEqual({"e", "o"}, {p.rotulo for p in resultado.promovidos})

    def test_a_promocao_registra_procedencia_humana(self) -> None:
        with TemporaryDirectory() as raiz:
            pasta = self.quarentena(Path(raiz))
            registro = Path(raiz) / "texto_procedencia.csv"
            promover(pasta, Path(raiz) / "training_data", registro=registro, quando="2026-08-26")
            lido = _procedencia.ler(registro)

        self.assertEqual(2, len(lido))
        for uuid, entrada in lido.items():
            with self.subTest(uuid=uuid):
                self.assertEqual(_procedencia.HUMANO, entrada.procedencia)
                self.assertTrue(entrada.mede, "procedência humana é o que deixa a amostra medir")
                self.assertEqual("Kemeri", entrada.livro)
                self.assertEqual("2026-08-26", entrada.rotulado_em)
        self.assertEqual({7, 45}, {e.pagina for e in lido.values()})

    def test_sem_base_de_treino_a_promocao_nao_grava_nada(self) -> None:
        """Uma função que escreve na base não deve fazê-lo porque alguém esqueceu um argumento."""
        with TemporaryDirectory() as raiz:
            pasta = self.quarentena(Path(raiz))
            antes = sorted(p.name for p in pasta.rglob("*.png"))
            resultado = promover(pasta)
            self.assertEqual(2, len(resultado.promovidos))
            self.assertIsNone(resultado.registro)
            self.assertEqual(antes, sorted(p.name for p in pasta.rglob("*.png")))

    def test_o_promovido_sai_da_quarentena(self) -> None:
        """Ficar nos dois lugares o faria voltar na próxima passada, e virar duplicata na base."""
        with TemporaryDirectory() as raiz:
            pasta = self.quarentena(Path(raiz))
            base = Path(raiz) / "training_data"
            promover(pasta, base, registro=Path(raiz) / "p.csv")
            self.assertEqual([], list(pasta.rglob("*.png")))
            self.assertEqual(1, len(list((base / "lower_e").glob("*.png"))))
            self.assertEqual(1, len(list((base / "lower_o").glob("*.png"))))

    def test_copiar_em_vez_de_mover_deixa_os_dois(self) -> None:
        with TemporaryDirectory() as raiz:
            pasta = self.quarentena(Path(raiz))
            promover(pasta, Path(raiz) / "td", registro=Path(raiz) / "p.csv", mover=False)
            self.assertEqual(2, len(list(pasta.rglob("*.png"))))

    def test_pasta_que_nao_decodifica_e_listada_e_nao_vira_interrogacao(self) -> None:
        """É o defeito que fez 127 amostras treinarem a classe errada por meses (S-180).

        `sym_` promete um ponto de código em decimal, e `sym_naoehex` não é um. Sem `strict=True`
        a pasta viraria o rótulo `"?"` -- e a promoção criaria `training_data/sym_63/` com o que
        estivesse ali dentro.
        """
        with TemporaryDirectory() as raiz:
            pasta = Path(raiz) / "revisao_ocr"
            (pasta / "sym_naoehex").mkdir(parents=True)
            resultado = promover(pasta)
        self.assertEqual(("sym_naoehex",), resultado.pastas_indecifraveis)
        self.assertEqual((), resultado.promovidos)

    def test_a_regua_de_pasta_e_a_mesma_do_dataset(self) -> None:
        """A quarentena promove para a base que `dataset.varrer` lê: as duas têm de concordar.

        Nome sem prefixo é **formato antigo** (pasta = caractere), e as duas o aceitam -- recusá-lo
        aqui deixaria `promover` mais estrito que a base para onde ele grava, o que travaria a
        promoção de material legítimo.
        """
        from chess_diagram_ocr.text.classes import NomeDePastaInvalido, folder_to_char

        with TemporaryDirectory() as raiz:
            pasta = Path(raiz) / "revisao_ocr"
            for nome in ("sym_naoehex", "lower_e", "e"):
                (pasta / nome).mkdir(parents=True)
            listadas = set(promover(pasta).pastas_indecifraveis)

        for nome in ("sym_naoehex", "lower_e", "e"):
            with self.subTest(pasta=nome):
                try:
                    folder_to_char(nome, strict=True)
                except NomeDePastaInvalido:
                    self.assertIn(nome, listadas)
                else:
                    self.assertNotIn(nome, listadas)

    def test_arquivo_com_nome_fora_do_padrao_entra_listado_e_sem_inventar_dado(self) -> None:
        """Nunca adivinhar: metade de um nome interpretada como dado é pior que nenhum dado."""
        with TemporaryDirectory() as raiz:
            pasta = Path(raiz) / "revisao_ocr" / "lower_e"
            pasta.mkdir(parents=True)
            (pasta / "copiado-a-mao.png").write_bytes(b"x")
            resultado = promover(pasta.parent)
        self.assertEqual(("lower_e/copiado-a-mao.png",), resultado.nomes_estranhos)
        self.assertEqual("", resultado.promovidos[0].livro)
        self.assertEqual(0, resultado.promovidos[0].pagina)

    def test_quarentena_inexistente_devolve_promocao_vazia(self) -> None:
        with TemporaryDirectory() as raiz:
            self.assertEqual((), promover(Path(raiz) / "nao_existe").promovidos)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
