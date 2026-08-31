"""PNG sob nome que a code page ANSI não representa.

O acervo tem um livro russo, e a varredura dele morria sempre no mesmo lugar:

    O OpenCV não conseguiu gravar
    data/review_cache/_Болеславский_И_Избранные_партии/p00006_d1.png.
    Verifique espaço em disco, permissão de escrita e se a pasta existe.

As três coisas que a mensagem mandava conferir estavam em ordem -- a pasta, inclusive, tinha
acabado de ser criada pela mesma função duas linhas acima. O que falhava era outra coisa:
`cv2.imwrite` recebe o caminho como `std::string` e o repassa ao `fopen` estreito do CRT, que
o converte pela code page ANSI do processo (cp1252 numa máquina brasileira). Cirílico não
existe em cp1252, o `fopen` falha, o `imwrite` devolve `False`. O `mkdir` do Python não sofria
disso porque a `pathlib` usa a API wide do Windows.

`cv2.imread` sofre da mesma conversão, com um agravante: devolve `None`, o mesmo valor que
significa "arquivo não existe". A miniatura teria voltado em branco, sem erro nenhum na tela.

Estes testes passariam sozinhos no Linux, onde a locale é UTF-8 e o `imwrite` nunca teve o
problema. É de propósito -- eles guardam o comportamento, não o defeito.

A guarda da S-111 (`write_image` confere o retorno em vez de seguir adiante) continua aqui,
agora sobre as duas falhas que restaram: a codificação recusada e a escrita que não foi ao
disco. Foi ela que transformou este defeito num diálogo de erro em vez de um PNG faltando.
"""

from __future__ import annotations

import ast
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import numpy as np

from chess_diagram_ocr.atomic_io import read_image, write_image

CIRILICO = "_Болеславский_И_Избранные_партии"
"""O nome exato que quebrava, tirado de `data/review_cache/`."""

NOMES_DIFICEIS = (
    CIRILICO,
    "Δοκιμή",  # grego, também fora da cp1252
    "棋譜",  # japonês, fora de qualquer code page de byte único ocidental
    "400 Quebra-cabeças de Estratégia",  # esse sempre funcionou: cabe na cp1252
)


def _tabuleiro() -> np.ndarray:
    imagem = np.zeros((16, 16, 3), dtype=np.uint8)
    imagem[4:12, 4:12] = (30, 90, 200)  # algo assimétrico, para o round-trip provar conteúdo
    return imagem


class CaminhoForaDaCodePageTests(unittest.TestCase):
    def test_grava_e_le_de_volta_sob_nome_cirilico(self) -> None:
        original = _tabuleiro()
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / CIRILICO / "p00006_d1.png"

            gravado = write_image(destino, original)

            self.assertTrue(gravado.exists())
            self.assertGreater(gravado.stat().st_size, 0)
            np.testing.assert_array_equal(read_image(gravado), original)

    def test_todos_os_alfabetos_que_o_acervo_alcanca(self) -> None:
        original = _tabuleiro()
        for nome in NOMES_DIFICEIS:
            with self.subTest(nome=nome), tempfile.TemporaryDirectory() as tmp:
                destino = Path(tmp) / nome / "p00001_d0.png"
                write_image(destino, original)
                np.testing.assert_array_equal(read_image(destino), original)

    def test_a_pasta_e_criada_quando_nao_existe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / CIRILICO / "sub" / "p00001_d0.png"
            write_image(destino, _tabuleiro())
            self.assertTrue(destino.parent.is_dir())


class LeituraTests(unittest.TestCase):
    """`read_image` devolve `None` onde o `imread` devolvia -- os sete pontos de chamada
    mantiveram o tratamento que já tinham."""

    def test_arquivo_que_nao_existe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_image(Path(tmp) / "nao_existe.png"))

    def test_arquivo_vazio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vazio = Path(tmp) / "vazio.png"
            vazio.touch()
            self.assertIsNone(read_image(vazio))

    def test_arquivo_que_nao_e_imagem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lixo = Path(tmp) / "lixo.png"
            lixo.write_bytes(b"isto aqui e um CSV, nao um PNG\n")
            self.assertIsNone(read_image(lixo))

    def test_diretorio_no_lugar_do_arquivo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_image(Path(tmp)))

    def test_aceita_caminho_em_texto(self) -> None:
        """A janela passa o `str` que o diálogo de arquivo devolveu."""
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / CIRILICO / "escolhido.png"
            write_image(destino, _tabuleiro())
            self.assertIsNotNone(read_image(str(destino)))

    def test_devolve_sempre_tres_canais(self) -> None:
        """Paridade com o `IMREAD_COLOR` que era o padrão do `imread`: quem chama faz
        `cvtColor(..., COLOR_BGR2RGB)` na sequência e um PNG em escala de cinza quebraria."""
        with tempfile.TemporaryDirectory() as tmp:
            import cv2

            cinza = Path(tmp) / "cinza.png"
            _, buffer = cv2.imencode(".png", np.full((16, 16), 128, dtype=np.uint8))
            cinza.write_bytes(buffer.tobytes())

            lido = read_image(cinza)
            self.assertIsNotNone(lido)
            self.assertEqual(lido.shape, (16, 16, 3))


class EscritaTests(unittest.TestCase):
    def test_extensao_sem_codec_levanta_oserror(self) -> None:
        """O `imencode` levanta `cv2.error` aqui; quem chama trata `OSError`."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(OSError) as ctx:
                write_image(Path(tmp) / "board.xyz", _tabuleiro())
            self.assertIn("codificar", str(ctx.exception))

    def test_falha_de_disco_levanta_com_o_caminho_na_mensagem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / CIRILICO / "p00006_d1.png"
            with unittest.mock.patch.object(Path, "write_bytes", side_effect=OSError("disco cheio")):
                with self.assertRaises(OSError) as ctx:
                    write_image(destino, _tabuleiro())

            mensagem = str(ctx.exception)
            self.assertIn("p00006_d1.png", mensagem)
            self.assertIn("disco cheio", mensagem)


class LeiDoProjetoTests(unittest.TestCase):
    """`cv2.imread` e `cv2.imwrite` não podem aparecer em lugar nenhum do repositório (S-432).

    A lei já estava escrita -- em `text/dataset.py`, em `cli/texto_inventario.py`, no docstring
    deste arquivo -- e verificada por dois testes que leem o **texto de dois módulos**
    (`test_texto_inventario.py` e `test_text_dataset.py`). Uma lei que só olha dois arquivos não
    é uma lei: `text/coleta.py` chamava `cv2.imwrite` desde a S-201 e nenhum dos dois olhava para
    lá, então a coleta de revisão de caractere gravava zero PNG e relatava cinco sempre que a
    pasta do projeto -- ou a do bundle que o usuário descompacta -- morava sob um nome com acento.

    Treze arquivos de teste chamavam `cv2.imread`/`cv2.imwrite` pelo mesmo motivo, e ali o preço
    era outro: **31 testes falhavam** num checkout cujo caminho tem acento, com a mensagem
    "Fixture ausente: refaça com gerar.py" apontando para um fixture que estava no lugar. A CI
    roda sob um caminho ASCII, então ela nunca podia ver isso.

    **Por que `ast` e não `grep`.** Metade das ocorrências no repositório são docstrings que
    explicam a proibição -- inclusive as deste arquivo. Um `grep` teria de conviver com uma lista
    de exceções que envelhece; a árvore sintática só vê chamada de verdade.

    **Por que `git ls-files` e não `os.walk` com poda.** A primeira versão desta guarda caminhava
    a partir da raiz podando uma lista fixa (`.venv`, `build`, `dist`, `__pycache__`, ...).
    Medida nesta árvore, ela varria 2.207 arquivos em 21 s e acusava **168** violações -- 147
    delas vindas de `.claude/worktrees/`, sete checkouts de sessões concorrentes cujo código não
    é deste ramo --, e ainda morria com `TabError` dentro de uma pasta de projeto de terceiro que
    o `.gitignore` já exclui: a guarda dava **erro**, e erro de guarda não se lê como achado, se
    lê como suíte quebrada.

    Lista fixa é lista que envelhece. O git já mantém a resposta para "o que é este repositório",
    honra `.gitignore` e `.git/info/exclude` de graça, e o `--others --exclude-standard` ainda vê
    o arquivo **novo e ainda não commitado** -- sem ele bastaria não dar `git add` para escapar da
    lei. Medida da mesma árvore: 430 arquivos em 0,27 s.

    `imencode` e `imdecode` continuam livres: eles são a primitiva que `atomic_io` usa, e a
    conversão de caminho que causa tudo isto não passa por eles.
    """

    PROIBIDOS = frozenset({"imread", "imwrite"})

    RAIZ = Path(__file__).resolve().parents[1]

    ALCANCE_MINIMO = ("janela.py", "coleta.py", "atomic_io.py", "build_windows.py", "gerar.py")
    """Cinco arquivos de cinco cantos: a janela na raiz, o módulo que tinha o defeito, a
    biblioteca que o corrige, o empacotador e o gerador de fixtures. Se a varredura não alcança
    os cinco, ela não está olhando o repositório -- e uma guarda que varre a pasta errada passa
    verde sem ter olhado nada, que é o defeito da S-296."""

    def _arquivos(self) -> list[Path]:
        """Os `.py` que o git reconhece como deste repositório, rastreados ou ainda não."""
        try:
            saida = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "*.py"],
                cwd=self.RAIZ,
                capture_output=True,
                check=True,
                text=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as erro:  # pragma: no cover - fora de um checkout
            self.skipTest(f"sem `git ls-files` para dizer o que é o repositório: {erro}")
        caminhos = [self.RAIZ / nome for nome in saida.split("\x00") if nome]
        if not caminhos:  # pragma: no cover - idem
            self.skipTest("`git ls-files` não devolveu nenhum .py -- isto não é um checkout")
        return caminhos

    def test_ninguem_no_repositorio_chama_imread_nem_imwrite(self) -> None:
        achados: list[str] = []
        ilegiveis: list[str] = []
        for caminho in self._arquivos():
            relativo = caminho.relative_to(self.RAIZ).as_posix()
            try:
                arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
            except (OSError, SyntaxError, UnicodeDecodeError) as erro:
                ilegiveis.append(f"{relativo}: {erro}")
                continue
            for no in ast.walk(arvore):
                if (
                    isinstance(no, ast.Attribute)
                    and no.attr in self.PROIBIDOS
                    and isinstance(no.value, ast.Name)
                    and no.value.id == "cv2"
                ):
                    achados.append(f"{relativo}:{no.lineno}: cv2.{no.attr}")
                elif isinstance(no, ast.ImportFrom) and no.module == "cv2":
                    for nome in no.names:
                        if nome.name in self.PROIBIDOS:
                            achados.append(f"{relativo}:{no.lineno}: from cv2 import {nome.name}")

        self.assertEqual(
            [],
            sorted(ilegiveis),
            "Arquivo do repositório que a guarda não conseguiu ler. Ela não olhou tudo, e uma "
            "guarda que não olhou tudo não pode dizer que não achou nada.",
        )
        self.assertEqual(
            [],
            sorted(achados),
            "Use `atomic_io.write_image` / `atomic_io.read_image`. Ver o docstring desta classe.",
        )

    def test_a_varredura_alcanca_o_codigo_todo_e_nao_so_os_testes(self) -> None:
        nomes = {caminho.name for caminho in self._arquivos()}
        for esperado in self.ALCANCE_MINIMO:
            self.assertIn(esperado, nomes, f"a varredura não alcançou {esperado}")

    def test_a_varredura_para_na_fronteira_do_repositorio(self) -> None:
        """O outro lado do alcance: o que a lista **não** pode conter.

        É o que derrubou a primeira versão desta guarda. Um `os.walk` da raiz entra em
        `.claude/worktrees/` -- checkout de outra sessão, com o mesmo código -- e passa a acusar
        um arquivo que quem lê o relatório não pode consertar, porque ele não é deste ramo.

        Numa árvore sem worktree nem `.venv` este teste é vácuo, e está certo que seja: ele
        afirma uma propriedade da fronteira, e onde não há fronteira não há o que afirmar. Aqui
        há, e foram 147 falsos achados.
        """
        partes = {parte for caminho in self._arquivos() for parte in caminho.relative_to(self.RAIZ).parts}
        for fora in (".claude", ".venv", "build", "dist"):
            self.assertNotIn(fora, partes, f"a varredura passou da fronteira do repositório: {fora}")


if __name__ == "__main__":
    unittest.main()
