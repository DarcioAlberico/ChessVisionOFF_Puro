"""O ambiente instalado aponta para esta árvore (S-37).

O `pythonpath = ["src"]` do `pyproject.toml` faz a suíte rodar num checkout sem instalação.
Isso é bom para o teste e **insuficiente para o produto**: `app_tkinter.py` e os comandos
`cvoff-*` importam o pacote do ambiente, não do `sys.path` do pytest. Um `.venv` cujo
ponteiro editável ficou no diretório antigo deixa a suíte verde e o programa quebrado -- que
foi exatamente o estado encontrado na análise da Fase 7.

Este arquivo fecha essa fresta. É o mesmo que o último passo do CI faz ("verificar que o
pacote é importável fora do diretório do projeto"), trazido para a máquina de quem
desenvolve, onde o problema de fato acontece.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from conftest import DISTRIBUICAO, RAIZ, caminhos_pth_inexistentes

_SONDA = "import chess_diagram_ocr, pathlib; print(pathlib.Path(chess_diagram_ocr.__file__).resolve())"

# **O piso do interpretador (S-830, D5 da solidez: 3.13, e a CI so nele).** O 3.10 saiu de suporte
# em outubro de 2026, e o bundle do PyInstaller embarca o interpretador: um `.venv` velho gera um
# `.exe` que distribui Python sem correcao de seguranca. A decisao mora no `requires-python`; este
# numero e a guarda dela, e os testes abaixo conferem que o resto da configuracao concorda.
PISO = (3, 13)


def _ler_pyproject() -> dict[str, object]:
    try:  # Python 3.11+ tem no stdlib; 3.10 usa o backport que já é dependência do pytest.
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - só no 3.10
        import tomli as tomllib  # type: ignore[no-redef]

    return tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))


class PisoDoInterpretadorTests(unittest.TestCase):
    def test_o_interpretador_que_roda_a_suite_esta_no_piso(self) -> None:
        """O `.venv` de quem desenvolve é o interpretador que vai dentro do `.exe`.

        É o teste que acusa a máquina que não foi recriada depois da troca de piso: a suíte inteira
        ainda roda num 3.10, e só esta linha diz que o ambiente ficou para trás.
        """
        real = sys.version_info[:2]
        if real < PISO:
            piso = ".".join(map(str, PISO))
            self.fail(
                f"Este ambiente roda Python {real[0]}.{real[1]}, abaixo do piso {piso} do projeto (S-830).\n"
                f"    interpretador: {sys.executable}\n"
                f"Feche o programa e recrie o ambiente a partir deste checkout:\n"
                f"    cd {RAIZ}\n"
                f"    uv sync --extra dev --extra onnx --extra ocr --python {piso}"
            )

    def test_a_configuracao_inteira_declara_o_mesmo_piso(self) -> None:
        """`requires-python`, `.python-version`, `ruff` e `mypy` dizem a mesma versão.

        Um deles para trás é o defeito que este item fecha: o `.python-version` em 3.10 fazia todo
        `uv sync` criar um ambiente de 3.10 enquanto a faixa já aceitava 3.13, e o `ruff`/`mypy`
        mirando a ponta velha recusariam a sintaxe que o piso novo permite.
        """
        piso = ".".join(map(str, PISO))
        config = _ler_pyproject()
        projeto = config.get("project", {})
        ferramentas = config.get("tool", {})
        assert isinstance(projeto, dict) and isinstance(ferramentas, dict)

        declarado = {
            "requires-python (piso)": str(projeto.get("requires-python", "")).split(",")[0].strip(),
            ".python-version": (RAIZ / ".python-version").read_text(encoding="utf-8").strip(),
            "[tool.ruff] target-version": ferramentas.get("ruff", {}).get("target-version"),
            "[tool.mypy] python_version": ferramentas.get("mypy", {}).get("python_version"),
        }
        esperado = {
            "requires-python (piso)": f">={piso}",
            ".python-version": piso,
            "[tool.ruff] target-version": f"py{PISO[0]}{PISO[1]}",
            "[tool.mypy] python_version": piso,
        }
        self.assertEqual(declarado, esperado, f"a configuração tem de declarar o piso {piso} (S-830)")


class AmbienteTests(unittest.TestCase):
    def test_o_pacote_instalado_resolve_para_esta_arvore(self) -> None:
        """Importado de fora do projeto e sem `PYTHONPATH`, o pacote tem de sair daqui.

        Pula quando não há distribuição instalada: rodar a suíte num clone limpo, só com o
        `pythonpath` do pytest, é um uso legítimo e não deve falhar por isso.
        """
        try:
            distribution(DISTRIBUICAO)
        except PackageNotFoundError:
            self.skipTest(f"`{DISTRIBUICAO}` não está instalada; a suíte roda pelo pythonpath do pytest.")

        ambiente = {**os.environ, "PYTHONPATH": ""}
        resultado = subprocess.run(
            [sys.executable, "-c", _SONDA],
            # Fora da árvore de propósito: dentro dela, `src/` poderia ser encontrado por acaso
            # e o teste passaria medindo a coisa errada.
            cwd=tempfile.gettempdir(),
            env=ambiente,
            capture_output=True,
            text=True,
            check=False,
        )

        if resultado.returncode != 0:
            quebrados = caminhos_pth_inexistentes()
            detalhe = (
                "\n".join(f"    {arquivo.name}: {alvo}" for arquivo, alvo in quebrados)
                if quebrados
                else "    (nenhum arquivo .pth aponta para caminho inexistente)"
            )
            self.fail(
                "O pacote instalado não é importável fora do diretório do projeto.\n"
                f"{resultado.stderr.strip()}\n\n"
                f"Caminhos mortos no ambiente:\n{detalhe}\n\n"
                f"O projeto foi movido depois de instalado? Rode:\n"
                f"    cd {RAIZ}\n"
                f"    uv sync --extra dev"
            )

        resolvido = Path(resultado.stdout.strip())
        self.assertTrue(
            resolvido.is_relative_to(RAIZ),
            f"O ambiente importa `chess_diagram_ocr` de outra árvore.\n"
            f"    instalado aponta para: {resolvido}\n"
            f"    este checkout é:       {RAIZ}\n"
            f"Rode `uv sync --extra dev` a partir deste diretório.",
        )

    def test_o_detector_acha_pth_apontando_para_diretorio_morto(self) -> None:
        """A parte com lógica do diagnóstico, exercitada contra um `site-packages` sintético.

        Reproduz o arquivo real encontrado na análise -- um `.pth` de instalação editável
        cujo destino sumiu -- ao lado de uma linha `import ...` (que é código, não caminho) e
        de um caminho válido, que são os dois falsos positivos possíveis.
        """
        with tempfile.TemporaryDirectory() as raiz:
            pasta = Path(raiz) / "site-packages"
            pasta.mkdir()
            valido = Path(raiz) / "existe"
            valido.mkdir()
            morto = str(Path(raiz) / "sumiu" / "src")
            (pasta / "__editable__.exemplo-0.1.0.pth").write_text(f"{morto}\n", encoding="utf-8")
            (pasta / "outro.pth").write_text(f"import sys\n{valido}\n\n", encoding="utf-8")

            sys.path.insert(0, str(pasta))
            try:
                achados = caminhos_pth_inexistentes()
            finally:
                sys.path.remove(str(pasta))

        deste_teste = [(arquivo, alvo) for arquivo, alvo in achados if alvo == morto]
        self.assertEqual(len(deste_teste), 1, f"esperado achar só o caminho morto; achou {achados}")
        self.assertEqual(deste_teste[0][0].name, "__editable__.exemplo-0.1.0.pth")

    def test_a_suite_nao_depende_da_instalacao(self) -> None:
        """`pythonpath = ["src"]` precisa continuar declarado.

        É a guarda que faz a suíte sobreviver a um diretório movido. Sem ela, o próximo
        `.pth` obsoleto volta a produzir 33 erros de coleta em vez de uma falha nomeada.
        """
        ferramentas = _ler_pyproject().get("tool", {})
        assert isinstance(ferramentas, dict)
        pytest_ini = ferramentas.get("pytest", {}).get("ini_options", {})
        self.assertIn(
            "src",
            pytest_ini.get("pythonpath", []),
            "`[tool.pytest.ini_options] pythonpath` precisa conter 'src' (S-37).",
        )


if __name__ == "__main__":
    unittest.main()
