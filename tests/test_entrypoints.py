"""Os `[project.scripts]` apontam para algo que existe e é chamável (S-128).

**11 dos 15 comandos `cvoff-*` não eram importados por teste nenhum.** Renomear um alvo em
`[project.scripts]`, ou mover um `main`, não quebrava nada até alguém tentar rodar o comando --
e quem tenta rodar é o usuário, no meio de um fluxo de horas.

Roda em qualquer ambiente: só importa módulo e confere que `main` é chamável. Não executa
comando nenhum.
"""

from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _entrypoints() -> dict[str, str]:
    """`[project.scripts]` lido à mão.

    Sem `tomllib`: ele é 3.11+ e o projeto está pinado em `requires-python = "==3.10.*"`. Uma
    dependência nova só para ler oito linhas de uma seção seria pagar caro pela elegância --
    e um parser de `chave = "valor"` numa seção declarada é o que a seção é.
    """
    linhas = (RAIZ / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    dentro = False
    scripts: dict[str, str] = {}
    for linha in linhas:
        if linha.strip().startswith("["):
            dentro = linha.strip() == "[project.scripts]"
            continue
        if not dentro or "=" not in linha or linha.strip().startswith("#"):
            continue
        chave, _, valor = linha.partition("=")
        scripts[chave.strip()] = valor.strip().strip('"')
    return scripts


class EntrypointsTests(unittest.TestCase):
    def test_todo_entrypoint_declarado_e_importavel_e_chamavel(self) -> None:
        quebrados = []
        for comando, alvo in sorted(_entrypoints().items()):
            modulo_nome, _, funcao_nome = alvo.partition(":")
            try:
                modulo = importlib.import_module(modulo_nome)
            except ImportError as exc:
                quebrados.append(f"{comando}: não importa {modulo_nome} ({exc})")
                continue
            funcao = getattr(modulo, funcao_nome, None)
            if not callable(funcao):
                quebrados.append(f"{comando}: {alvo} não é chamável")

        self.assertEqual(quebrados, [], "Entrypoint declarado no pyproject.toml que não resolve.")

    def test_ha_entrypoint_declarado(self) -> None:
        """A guarda da guarda: um `[project.scripts]` vazio faria o teste acima passar sempre."""
        self.assertGreaterEqual(len(_entrypoints()), 15)

    def test_todo_cli_com_main_esta_declarado(self) -> None:
        """O outro sentido: um módulo de CLI que ninguém pode chamar é código morto com cara
        de recurso. Foi assim que `cvoff-gallery` e `cvoff-scan` precisaram ser lembrados no
        `pyproject.toml` -- e é o tipo de esquecimento que só aparece no uso.
        """
        declarados = {alvo.partition(":")[0] for alvo in _entrypoints().values()}
        faltando = []
        for caminho in sorted((RAIZ / "src" / "chess_diagram_ocr" / "cli").glob("*.py")):
            if caminho.name in ("__init__.py", "_ocr.py"):
                continue
            modulo = f"chess_diagram_ocr.cli.{caminho.stem}"
            if "\ndef main(" in caminho.read_text(encoding="utf-8") and modulo not in declarados:
                faltando.append(modulo)

        self.assertEqual(faltando, [], "Módulo de CLI com `main` e sem entrypoint no pyproject.toml.")


class BandeiraVerboseTests(unittest.TestCase):
    """Todo comando aceita `-v` -- porque o programa manda usá-lo (S-377).

    A mensagem de erro da S-126 termina com "Rode de novo com -v para ver o rastro completo", e
    o README garante a bandeira nos 40 comandos. Doze respondiam `error: unrecognized
    arguments: -v`, seis deles sem nem a forma longa. É uma promessa impressa pelo próprio
    programa, e quem a seguia recebia um segundo erro no lugar da resposta.
    """

    def _modulos_de_comando(self) -> list[Path]:
        pasta = RAIZ / "src" / "chess_diagram_ocr" / "cli"
        return [
            caminho
            for caminho in sorted(pasta.glob("*.py"))
            if caminho.name not in ("__init__.py", "_ocr.py")
            and "\ndef main(" in caminho.read_text(encoding="utf-8")
        ]

    def test_todo_comando_declara_a_bandeira(self) -> None:
        sem = [
            caminho.name
            for caminho in self._modulos_de_comando()
            if "add_verbose(parser)" not in caminho.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            sem,
            [],
            "Comando sem `-v`. Chame `add_verbose(parser)` antes do `parse_args`: a mensagem de "
            "erro da S-126 manda o usuário usar a bandeira, e o README a promete nos 40.",
        )

    def test_a_varredura_encontra_os_comandos(self) -> None:
        """A guarda da guarda: uma lista vazia faria o teste acima passar sempre."""
        self.assertGreaterEqual(len(self._modulos_de_comando()), 30)

    def test_a_bandeira_e_vista_quando_ninguem_passa_argv(self) -> None:
        """Como *console script* o `main` é chamado sem argumento: `argv` chega `None` (S-377).

        **Quem diz que houve `-v` é o comando, e não a linha do processo** (S-427): o molde
        aqui é o que os 40 fazem de verdade -- parsear e chamar `configure_logging` com o que
        saiu do `argparse`. Era `sys.argv` que respondia, e ver o teste seguinte para o que
        isso custou.
        """
        from chess_diagram_ocr.cli import run_main
        from chess_diagram_ocr.logging_setup import configure_logging

        def explode(argv: object) -> int:
            configure_logging(verbose=True)
            raise ValueError("falha de teste")

        with self.assertRaises(ValueError):
            run_main(explode, None)

    def test_o_v_do_processo_nao_e_o_do_comando(self) -> None:
        """A CI roda `uv run pytest -v`, e aquele `-v` não é de comando nenhum (S-427).

        Era o defeito que só a CI podia mostrar: com o `sys.argv` do processo como fonte, o
        `run_main` levantava a exceção original em vez de traduzi-la para pt-BR e devolver o
        código de saída -- e dois testes de `test_cli_errors` reprovavam lá e passavam aqui.
        """
        from unittest.mock import patch

        from chess_diagram_ocr.cli import EXIT_BAD_INPUT, run_main
        from chess_diagram_ocr.logging_setup import configure_logging

        def explode(argv: object) -> int:
            configure_logging(verbose=False)
            raise ValueError("falha de teste")

        with patch("sys.argv", ["pytest", "-v", "tests/"]):
            self.assertEqual(EXIT_BAD_INPUT, run_main(explode, None))

    def test_sem_a_bandeira_o_rastro_nao_sobe_a_tela(self) -> None:
        from unittest.mock import patch

        from chess_diagram_ocr.cli import EXIT_BAD_INPUT, run_main

        def explode(argv: object) -> int:
            raise ValueError("falha de teste")

        with patch("sys.argv", ["cvoff-qualquer"]):
            self.assertEqual(run_main(explode, None), EXIT_BAD_INPUT)


class CodigoDeSaidaPelaTabelaTests(unittest.TestCase):
    """Nenhum `main` de CLI devolve número solto diferente de zero (S-378).

    A tabela da S-126 dá **classe** de falha, e classe é o que um script consome:
    `cvoff-scan --all && cvoff-...` precisa distinguir "o livro estava corrompido" de "o modelo
    sumiu" e as duas de "houve um defeito no programa". Um `return 1` escrito à mão não diz de
    qual das três se trata -- e a varredura achou onze lugares em que ele dizia a errada:
    `cvoff-evaluate` e `cvoff-experiment` classificavam "o arquivo que você apontou não existe"
    como defeito do programa, e `cvoff-export-onnx` tinha os dois códigos trocados entre si.

    `return 0` continua permitido como literal: "deu certo" não tem classe para errar, e trocar
    os quarenta por `EXIT_OK` seria ruído sem defeito por trás.
    """

    def _returns_soltos(self) -> list[str]:
        pasta = RAIZ / "src" / "chess_diagram_ocr" / "cli"
        achados = []
        for caminho in sorted(pasta.glob("*.py")):
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            for funcao in [n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef)]:
                if not str(funcao.returns and getattr(funcao.returns, "id", "")) == "int":
                    continue
                for no in ast.walk(funcao):
                    if not isinstance(no, ast.Return):
                        continue
                    for valor in (no.value, *_ramos(no.value)):
                        if isinstance(valor, ast.Constant) and valor.value in (1, 2, 3):
                            achados.append(f"{caminho.name}:{no.lineno}: return {valor.value}")
        return achados

    def test_nenhum_codigo_de_falha_e_numero_solto(self) -> None:
        self.assertEqual(
            self._returns_soltos(),
            [],
            "Código de saída escrito como número. Use EXIT_FAILURE (defeito do programa), "
            "EXIT_BAD_INPUT (o que se apontou não serve) ou EXIT_NO_CHECKPOINT -- a tabela "
            "está no docstring de `cli.EXIT_NO_CHECKPOINT`.",
        )

    def test_as_tres_classes_sao_distintas(self) -> None:
        """A guarda da guarda: três nomes com o mesmo valor não separariam nada."""
        from chess_diagram_ocr.cli import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NO_CHECKPOINT, EXIT_OK

        self.assertEqual(len({EXIT_OK, EXIT_FAILURE, EXIT_BAD_INPUT, EXIT_NO_CHECKPOINT}), 4)


def _ramos(valor: object) -> tuple:
    """Os dois lados de um `return X if cond else Y`, que é como três comandos decidem."""
    return (valor.body, valor.orelse) if isinstance(valor, ast.IfExp) else ()


PARES_DE_VOCABULARIO = (
    ("--limit", "--limite"),
    ("--limit-books", "--limite-livros"),
    ("--apply", "--aplicar"),
    ("--dry-run", "--seco"),
)
"""As três bandeiras que existiam nas duas línguas, em comandos irmãos (S-382).

`cvoff-games --apply` e `cvoff-texto-conflitos --aplicar` fazem a mesma coisa e se escreviam
diferente; `--limit` e `--limite` conviviam em nove comandos; `--dry-run` e `--seco`, em dois.
Quem usa a linha de comando decora o que digitou ontem, e errar a língua da bandeira devolve
`unrecognized arguments` -- que é a mesma parede da S-377, por outro caminho.

**Nenhuma bandeira foi renomeada**: renomear quebraria script e documento. As duas grafias
passaram a ser a mesma bandeira, e é isto que esta lista trava.
"""


class VocabularioDasBandeirasTests(unittest.TestCase):
    def _opcoes_por_arquivo(self) -> dict[str, list[tuple[str, ...]]]:
        pasta = RAIZ / "src" / "chess_diagram_ocr" / "cli"
        por_arquivo: dict[str, list[tuple[str, ...]]] = {}
        for caminho in sorted(pasta.glob("*.py")):
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            chamadas = []
            for no in ast.walk(arvore):
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "add_argument":
                    nomes = tuple(a.value for a in no.args if isinstance(a, ast.Constant) and isinstance(a.value, str))
                    if nomes:
                        chamadas.append(nomes)
            por_arquivo[caminho.name] = chamadas
        return por_arquivo

    def test_quem_declara_uma_grafia_declara_a_outra(self) -> None:
        faltando = []
        for arquivo, chamadas in self._opcoes_por_arquivo().items():
            for nomes in chamadas:
                for uma, outra in PARES_DE_VOCABULARIO:
                    if uma in nomes and outra not in nomes:
                        faltando.append(f"{arquivo}: {uma} sem {outra}")
                    if outra in nomes and uma not in nomes:
                        faltando.append(f"{arquivo}: {outra} sem {uma}")
        self.assertEqual(
            faltando,
            [],
            "Bandeira declarada numa língua só. Declare as duas grafias na mesma "
            "`add_argument` -- o `dest` continua o da primeira, e nenhum script quebra.",
        )

    def test_a_varredura_encontra_as_bandeiras(self) -> None:
        """A guarda da guarda: um scanner que não vê `add_argument` passaria sempre."""
        declaradas = {
            nome
            for chamadas in self._opcoes_por_arquivo().values()
            for nomes in chamadas
            for nome in nomes
        }
        for uma, outra in PARES_DE_VOCABULARIO:
            with self.subTest(par=(uma, outra)):
                self.assertIn(uma, declaradas)
                self.assertIn(outra, declaradas)


class AjudaDeTodoArgumentoTests(unittest.TestCase):
    """`--help` explica os 373 argumentos, e não 262 deles (S-384).

    Cento e onze argumentos não tinham `help`, e o `--help` os listava como nome e nada mais --
    entre eles `--epochs`, `--batch-size` e `--lr` do `cvoff-train`, que são os três que alguém
    ajusta antes de um treino de duas horas. Um argumento sem ajuda é um argumento cujo efeito
    só se descobre lendo o fonte.
    """

    def _sem_ajuda(self) -> list[str]:
        pasta = RAIZ / "src" / "chess_diagram_ocr" / "cli"
        achados = []
        for caminho in sorted(pasta.glob("*.py")):
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "add_argument":
                    if any(k.arg == "help" for k in no.keywords):
                        continue
                    nomes = [a.value for a in no.args if isinstance(a, ast.Constant)]
                    achados.append(f"{caminho.name}:{no.lineno}: {nomes or '(posicional)'}")
        return achados

    def test_todo_argumento_declara_help(self) -> None:
        self.assertEqual(
            self._sem_ajuda(),
            [],
            "Argumento sem `help`. Quem digita o comando não lê o fonte -- descreva o efeito "
            "numa linha, e o padrão quando ele não for óbvio.",
        )

    def test_a_varredura_ve_os_argumentos(self) -> None:
        """A guarda da guarda: um scanner cego passaria sempre."""
        pasta = RAIZ / "src" / "chess_diagram_ocr" / "cli"
        total = 0
        for caminho in sorted(pasta.glob("*.py")):
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            total += sum(
                1
                for no in ast.walk(arvore)
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "add_argument"
            )
        self.assertGreater(total, 300)


class BlocoDeMedicaoTests(unittest.TestCase):
    """O bloco de argumentos de medição é declarado num lugar só (S-383).

    `--csv`, `--samples`, `--splits`, `--model`, `--dpi` e `--accept-threshold` eram copiados à
    mão comando a comando, e a cópia divergia: o caminho da partição estava escrito **seis
    vezes**, sob dois nomes e por duas fórmulas. Iguais hoje; o dia em que deixassem de ser não
    teria sintoma nenhum além de dois comandos medirem conjuntos diferentes.
    """

    def test_nenhum_comando_declara_o_bloco_a_mao(self) -> None:
        pasta = RAIZ / "src" / "chess_diagram_ocr" / "cli"
        do_bloco = {"--csv", "--samples", "--splits", "--model", "--dpi", "--accept-threshold"}
        a_mao = []
        for caminho in sorted(pasta.glob("*.py")):
            if caminho.name in ("__init__.py", "census.py"):
                continue  # o `--csv` do censo é saída, e não o dataset: outro argumento, mesmo nome
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "add_argument":
                    nomes = {a.value for a in no.args if isinstance(a, ast.Constant)}
                    if nomes & do_bloco:
                        a_mao.append(f"{caminho.name}:{no.lineno}: {sorted(nomes & do_bloco)}")
        self.assertEqual(
            a_mao,
            [],
            "Argumento do bloco de medição declarado à mão. Use `add_dataset_arguments`, "
            "`add_model_argument`, `add_dpi_argument` ou `add_accept_threshold_argument`.",
        )

    def test_o_caminho_da_particao_tem_um_dono_so(self) -> None:
        pasta = RAIZ / "src" / "chess_diagram_ocr" / "cli"
        donos = [
            caminho.name
            for caminho in sorted(pasta.glob("*.py"))
            if "DEFAULT_SPLITS" in caminho.read_text(encoding="utf-8").replace("DEFAULT_SPLITS_PATH,", "")
            and caminho.name != "__init__.py"
        ]
        self.assertEqual(donos, [], "O caminho da partição mora em `config.DEFAULT_SPLITS_PATH`.")


if __name__ == "__main__":
    unittest.main()
