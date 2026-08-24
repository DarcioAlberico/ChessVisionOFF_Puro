"""A varredura da base de caractere e o split que não pode vazar (S-202/S-203).

**Os testes daqui montam a base no disco em vez de simular a leitura.** O que este módulo pode
errar não é aritmética: é ler um PNG que não decodifica, é aceitar uma pasta cujo nome não é
classe, e é deixar a mesma imagem cair nos dois lados do split. Nenhum dos três aparece com
`numpy` de mentira -- os três aparecem com arquivo de verdade.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from chess_diagram_ocr.text.dataset import (
    TESTE,
    TREINO,
    VALIDACAO,
    BaseVazia,
    aviso_de_distribuicao,
    codigos_de_procedencia,
    contagem_por_lado,
    gravar_cache,
    grupos_em_conflito,
    ler_cache,
    ler_recorte,
    livros_de,
    livros_em_dois_lados,
    procedencia_de,
    representantes,
    split_por_grupo,
    split_por_livro,
    varrer,
    vazamento,
)
from chess_diagram_ocr.text.procedencia import CODIGO, DESCONHECIDA, HUMANO, MODELO, Registro


def png(imagem: np.ndarray) -> bytes:
    import cv2

    ok, buffer = cv2.imencode(".png", imagem)
    assert ok
    return bytes(buffer.tobytes())


def escrever(pasta: Path, nome: str, imagem: np.ndarray) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    caminho.write_bytes(png(imagem))
    return caminho


class VarreduraTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.aleatorio = np.random.default_rng(0)

    def _classe(self, nome: str, n: int, *, iguais: bool = False) -> None:
        for i in range(n):
            imagem = (
                np.full((32, 32), 128, np.uint8)
                if iguais
                else self.aleatorio.integers(0, 255, (32, 32), dtype=np.uint8)
            )
            escrever(self.base / nome, f"{i:04d}.png", imagem)

    def test_a_varredura_nao_escreve_na_pasta(self) -> None:
        """Ler a base não pode mexer nela. É a regra da S-200, e aqui ela é conferida por mtime."""
        self._classe("lower_a", 4)
        antes = {p: p.stat().st_mtime_ns for p in self.base.rglob("*")}
        varrer(self.base, tarefas=2)
        depois = {p: p.stat().st_mtime_ns for p in self.base.rglob("*")}
        self.assertEqual(antes, depois)

    def test_png_ilegivel_e_contado_e_nao_derruba(self) -> None:
        """Um arquivo corrompido vira achado nomeado, e a varredura termina com sucesso."""
        self._classe("lower_a", 3)
        (self.base / "lower_a" / "lixo.png").write_bytes(b"isto nao e um png")
        varredura = varrer(self.base, tarefas=2)
        self.assertEqual(varredura.total, 3)
        self.assertEqual(varredura.ilegiveis, ["lower_a/lixo.png"])

    def test_a_leitura_usa_imdecode_e_nao_imread(self) -> None:
        """`ler_recorte` decodifica de bytes.

        A regra vem de um acidente: no Windows `cv2.imread` falha em caminho não-ASCII e devolve
        `None`, indistinguível de arquivo corrompido -- e a migração de lá apagou PNGs válidos
        por causa disso. O teste é o caso que separa os dois: um nome não-ASCII que **abre**.
        """
        caminho = escrever(self.base / "lower_a", "acentuação.png", np.full((32, 32), 7, np.uint8))
        bruto, imagem, nativa = ler_recorte(caminho)
        self.assertTrue(bruto.startswith(b"\x89PNG"))
        assert imagem is not None
        self.assertEqual(imagem.shape, (32, 32))
        self.assertEqual(nativa, (32, 32))

    def test_a_dimensao_nativa_sobrevive_ao_redimensionamento(self) -> None:
        """O `resize` destrói a altura e a proporção, e a S-202 precisa das duas."""
        caminho = escrever(self.base / "lower_a", "estreito.png", np.full((26, 35), 90, np.uint8))
        _, imagem, nativa = ler_recorte(caminho)
        assert imagem is not None
        self.assertEqual(imagem.shape, (32, 32))
        self.assertEqual(nativa, (26, 35))

    def test_pasta_que_nao_fecha_a_ida_e_volta_vira_achado(self) -> None:
        """Nome que não é classe não pode virar classe calada -- ver `classes.py`."""
        self._classe("lower_a", 3)
        self._classe("uma pasta qualquer", 3)
        varredura = varrer(self.base, tarefas=2)
        self.assertEqual([c.pasta for c in varredura.classes], ["lower_a"])
        self.assertEqual(varredura.pastas_indecifraveis, ["uma pasta qualquer"])

    def test_o_recorte_fora_de_32_e_redimensionado_para_32(self) -> None:
        """A inferência só vê 32x32, e treinar noutro tamanho compara maçã com laranja."""
        escrever(self.base / "lower_a", "a.png", np.full((26, 35), 90, np.uint8))
        varredura = varrer(self.base, tarefas=1)
        self.assertEqual(varredura.X.shape, (1, 32 * 32))

    def test_a_base_sem_classe_nenhuma_levanta(self) -> None:
        with self.assertRaises(BaseVazia):
            varrer(self.base, tarefas=1)

    def test_a_copia_exata_cai_no_mesmo_grupo(self) -> None:
        self._classe("lower_a", 6, iguais=True)
        varredura = varrer(self.base, tarefas=2)
        self.assertEqual(varredura.total, 6)
        self.assertEqual(np.unique(varredura.grupos).size, 1)
        self.assertEqual(varredura.copias_exatas, 5)

    def test_o_cache_fecha_a_volta_e_nao_guarda_o_split(self) -> None:
        """Ida-e-volta do cache. O split fica **de fora**: guardá-lo é estado que envelhece."""
        self._classe("lower_a", 5)
        self._classe("digit_1", 4)
        varredura = varrer(self.base, tarefas=2)
        alvo = self.base / "cache.npz"
        gravar_cache(alvo, varredura)
        de_volta = ler_cache(alvo)
        np.testing.assert_array_equal(varredura.X, de_volta.X)
        np.testing.assert_array_equal(varredura.y, de_volta.y)
        np.testing.assert_array_equal(varredura.grupos, de_volta.grupos)
        self.assertEqual(varredura.alfabeto, de_volta.alfabeto)
        self.assertNotIn("lado", np.load(alvo).files)


class ProcedenciaTests(unittest.TestCase):
    """A S-201 no lado da varredura: marcar, e nunca recusar."""

    REGISTRO = {
        "a1": Registro(livro="Yusupov", pagina=1, procedencia=HUMANO),
        "a2": Registro(livro="Yusupov", pagina=2, procedencia=MODELO),
        "a3": Registro(livro="", pagina=None, procedencia=DESCONHECIDA),
    }

    def test_sem_registro_tudo_e_desconhecida(self) -> None:
        """Não é o mesmo que recusar: a amostra entra no treino, e só não mede o modelo."""
        self.assertEqual(DESCONHECIDA, procedencia_de("a1"))
        self.assertEqual(DESCONHECIDA, procedencia_de("a1", {}))

    def test_o_nome_que_o_registro_nao_menciona_e_desconhecida(self) -> None:
        self.assertEqual(DESCONHECIDA, procedencia_de("nao-existe", self.REGISTRO))

    def test_os_codigos_saem_na_ordem_das_amostras(self) -> None:
        nomes = np.array(["a2", "a1", "zz"])
        np.testing.assert_array_equal(
            np.array([CODIGO[MODELO], CODIGO[HUMANO], CODIGO[DESCONHECIDA]], dtype=np.int8),
            codigos_de_procedencia(nomes, self.REGISTRO),
        )

    def test_o_livro_vira_indice_e_o_sem_livro_fica_em_menos_um(self) -> None:
        indices, nomes = livros_de(np.array(["a1", "a3", "a2"]), self.REGISTRO)
        self.assertEqual(["Yusupov"], nomes)
        np.testing.assert_array_equal(np.array([0, -1, 0], dtype=np.int32), indices)

    def test_amostra_sem_procedencia_fica_fora_do_teste(self) -> None:
        """A regra inteira da S-201, do lado do split: o grupo dela é travado no treino."""
        y = np.repeat(np.arange(4), 40).astype(np.int32)
        grupos = np.arange(y.size, dtype=np.int32)
        medivel = np.zeros(y.size, dtype=bool)
        medivel[::2] = True

        lado = split_por_grupo(y, grupos, medivel=medivel, semente=3)

        self.assertEqual({TREINO}, set(lado[~medivel].tolist()))
        self.assertIn(TESTE, set(lado[medivel].tolist()))

    def test_o_aviso_de_distribuicao_dispara(self) -> None:
        """`digit_1` acima de `lower_e` é a assinatura do classificador confundindo l, i e I."""
        from chess_diagram_ocr.text.dataset import Classe

        suspeita = [Classe("digit_1", "1", 16962, 0), Classe("lower_e", "e", 16090, 0)]
        normal = [Classe("digit_1", "1", 26792, 0), Classe("lower_e", "e", 33855, 0)]

        self.assertIn("digit_1", aviso_de_distribuicao(suspeita))
        self.assertEqual("", aviso_de_distribuicao(normal))

    def test_o_aviso_nao_dispara_sem_uma_das_duas_classes(self) -> None:
        from chess_diagram_ocr.text.dataset import Classe

        self.assertEqual("", aviso_de_distribuicao([Classe("digit_1", "1", 10, 0)]))


class SplitPorLivroTests(unittest.TestCase):
    """A S-203: livros inteiros de um lado só, e o teste com livro que o treino não viu."""

    def _base(self, n_livros: int = 5, por_livro: int = 40):
        n = n_livros * por_livro
        y = np.tile(np.arange(4), n // 4).astype(np.int32)
        grupos = np.arange(n, dtype=np.int32)
        livros = np.repeat(np.arange(n_livros), por_livro).astype(np.int32)
        return y, grupos, livros

    def test_nenhuma_pagina_atravessa_o_split(self) -> None:
        """Página vive dentro de livro: livro inteiro de um lado é a garantia mais forte."""
        y, grupos, livros = self._base()
        lado = split_por_livro(y, grupos, livros, semente=1)
        self.assertEqual([], livros_em_dois_lados(livros, lado))
        self.assertEqual([], vazamento(grupos, lado))

    def test_existe_um_livro_so_do_teste(self) -> None:
        """É o único número que fala sobre fonte nova, e sem ele a fase não mede o que promete."""
        y, grupos, livros = self._base()
        lado = split_por_livro(y, grupos, livros, semente=1)
        no_teste = set(livros[lado == TESTE].tolist())
        no_treino = set(livros[lado == TREINO].tolist())
        self.assertTrue(no_teste)
        self.assertTrue(no_teste.isdisjoint(no_treino))

    def test_validacao_e_teste_existem_mesmo_com_livro_grande(self) -> None:
        """Um livro que estoura as duas frações de uma vez deixaria a validação vazia."""
        y = np.tile(np.arange(4), 250).astype(np.int32)
        grupos = np.arange(y.size, dtype=np.int32)
        livros = np.array([0] * 900 + [1] * 50 + [2] * 50, dtype=np.int32)
        lado = split_por_livro(y, grupos, livros, semente=0)
        self.assertTrue((lado == VALIDACAO).any())
        self.assertTrue((lado == TESTE).any())

    def test_amostra_sem_livro_fica_fora_do_teste(self) -> None:
        y, grupos, livros = self._base()
        livros[:40] = -1
        lado = split_por_livro(y, grupos, livros, semente=1)
        self.assertEqual({TREINO}, set(lado[livros == -1].tolist()))

    def test_o_grupo_de_quase_duplicata_nao_atravessa(self) -> None:
        """Irmã em dois livros não pode ser atômica e livro-pura ao mesmo tempo: volta ao treino."""
        y, grupos, livros = self._base()
        grupos[40] = grupos[0]  # une uma amostra do livro 0 com uma do livro 1
        lado = split_por_livro(y, grupos, livros, semente=1)
        self.assertEqual(TREINO, lado[0])
        self.assertEqual(TREINO, lado[40])
        self.assertEqual([], vazamento(grupos, lado))

    def test_o_livro_e_atomico_e_a_regra_da_procedencia_nao_o_parte(self) -> None:
        """**A trava pegou isto na primeira corrida sobre base com livro.**

        A versão anterior recebia a máscara da S-201 e mandava a amostra não-medível para o
        treino. Com rótulo de modelo espalhado -- um a cada sete, no caso -- isso punha o mesmo
        livro dos dois lados: `livros_em_dois_lados` acusou dois livros, e o comando recusou
        treinar. Quem tira a amostra da conta é quem monta os índices de medição, depois.
        """
        y, grupos, livros = self._base()
        lado = split_por_livro(y, grupos, livros, semente=1)

        for livro in np.unique(livros):
            with self.subTest(livro=int(livro)):
                self.assertEqual(1, len(set(lado[livros == livro].tolist())))

    def test_menos_de_tres_livros_levanta_em_vez_de_esvaziar_a_validacao(self) -> None:
        y, grupos, livros = self._base(n_livros=2)
        with self.assertRaises(BaseVazia):
            split_por_livro(y, grupos, livros)

    def test_sem_livro_nenhum_levanta_para_quem_chama_decidir(self) -> None:
        """Decidir aqui esconderia a decisão de cair para o split por grupo."""
        y, grupos, livros = self._base()
        with self.assertRaises(BaseVazia):
            split_por_livro(y, grupos, np.full_like(livros, -1))


class SplitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aleatorio = np.random.default_rng(7)

    def test_nenhum_grupo_de_copia_exata_atravessa_o_split(self) -> None:
        """O critério de aceite da S-203, na forma que esta base permite conferir."""
        y = np.repeat(np.arange(8), 60).astype(np.int32)
        grupos = (np.arange(y.size) // 4).astype(np.int32)
        lado = split_por_grupo(y, grupos, semente=1)
        self.assertEqual(vazamento(grupos, lado), [])

    def test_a_mesma_imagem_sob_dois_rotulos_fica_no_treino(self) -> None:
        """83 grupos desta base estão arquivados sob dois caracteres ao mesmo tempo.

        Um rótulo que se contradiz não pode ser medido: o modelo erraria por definição. Ele
        continua ensinando (a base é o que é) e sai de validação e de teste.
        """
        y = np.repeat(np.arange(4), 40).astype(np.int32)
        grupos = np.arange(y.size, dtype=np.int32)
        grupos[0] = grupos[40] = 9999  # a mesma imagem sob as classes 0 e 1
        lado = split_por_grupo(y, grupos, semente=3)
        self.assertEqual(list(grupos_em_conflito(y, grupos)), [9999])
        self.assertTrue((lado[grupos == 9999] == TREINO).all())
        self.assertEqual(vazamento(grupos, lado), [])

    def test_a_classe_com_menos_de_tres_grupos_fica_toda_no_treino(self) -> None:
        """Sem três grupos não há como ter os três lados, e o treino é o que não pode faltar."""
        y = np.array([0, 0, 1, 1, 1, 1, 1, 1], dtype=np.int32)
        grupos = np.array([0, 1, 2, 3, 4, 5, 6, 7], dtype=np.int32)
        lado = split_por_grupo(y, grupos, semente=0)
        self.assertTrue((lado[y == 0] == TREINO).all())
        self.assertTrue((lado[y == 1] != TREINO).any())

    def test_o_split_e_reprodutivel_pela_semente(self) -> None:
        y = np.repeat(np.arange(5), 50).astype(np.int32)
        grupos = np.arange(y.size, dtype=np.int32)
        a = split_por_grupo(y, grupos, semente=11)
        b = split_por_grupo(y, grupos, semente=11)
        c = split_por_grupo(y, grupos, semente=12)
        np.testing.assert_array_equal(a, b)
        self.assertFalse(np.array_equal(a, c))

    def test_representantes_da_exatamente_um_por_grupo(self) -> None:
        grupos = np.array([3, 3, 3, 4, 5, 5], dtype=np.int32)
        mascara = representantes(grupos)
        self.assertEqual(int(mascara.sum()), 3)
        self.assertEqual(np.unique(grupos[mascara]).size, 3)

    def test_a_contagem_por_lado_soma_o_total(self) -> None:
        y = np.repeat(np.arange(3), 30).astype(np.int32)
        grupos = np.arange(y.size, dtype=np.int32)
        lado = split_por_grupo(y, grupos, semente=5)
        tabela = contagem_por_lado(y, lado, 3)
        self.assertEqual(int(tabela.sum()), y.size)
        for destino in (TREINO, VALIDACAO, TESTE):
            self.assertEqual(int(tabela[:, destino].sum()), int((lado == destino).sum()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
